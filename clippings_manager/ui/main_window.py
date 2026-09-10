"""The application window.

Starts empty. Every morning brings different documents and different loose images,
so the tool opens ready to receive today's, by whichever route is nearest to hand:
a Word file, a PDF, a folder of photos, a drag from Explorer, or Ctrl+V straight out
of WhatsApp Web.
"""

from __future__ import annotations

import itertools
import os
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (QEvent, QPoint, QRectF, QSize, Qt, QTimer,
                            QUrl)
from PySide6.QtGui import (
    QAction,
    QCursor,
    QGuiApplication,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
    QUndoGroup,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.assemble import (ExtractionError, detect_division, is_advisory,
                             load_config, looks_like_url)
from ..core.extract_docx import extract_docx
from ..core.extract_pdf import extract_pdf
from ..core import duplicates, ocr, sentiment, training, wordlist
from ..core.models import Clip, Section
from ..core.profiles import NameIndex
from .. import version
from ..core.session import SessionStore, decode_clip, encode_clip
from . import (commands, datefield, dropped, export_dialog, icons, reader,
               theme, win_drop, zoom)
from .clip_list import ClipList
from .cover_card import CoverCard
from .fluid import ElidedLabel, FlowLayout, ShrinkingCombo
from .layout_card import HeadingLayoutCard
from . import scroll
from .scroll import CardScroll
from .model import (
    LOOSE_KEY,
    LOOSE_TITLE,
    ClipModel,
    Row,
    make_thumbnail,
    pixmap_from_png,
    thumbnail_png,
)
from .modeswitch import ModeSwitch, ZoomButtons
from .preview import PreviewDialog
from .sentiment_board import SentimentBoard
from .wordlist_bar import WordListBar

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


class IconButton(QPushButton):
    """A round floating button that paints one of our vector icons."""

    def __init__(self, drawer, tooltip: str, parent=None, diameter: int = 42):
        super().__init__(parent)
        self.drawer = drawer
        self.setFixedSize(diameter, diameter)
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE};"
            f" border: 1px solid {theme.HAIRLINE_STRONG}; border-radius: {diameter//2}px; }}"
            f"QPushButton:hover {{ background: {theme.NAVY}; border-color: {theme.NAVY}; }}"
            f"QPushButton:disabled {{ background: {theme.SURFACE};"
            f" border-color: {theme.HAIRLINE}; }}"
        )

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        colour = theme.QNAVY
        if not self.isEnabled():
            colour = theme.QFAINT
        elif self.underMouse():
            colour = Qt.white
        size = self.width() * 0.46
        box = QRectF(
            (self.width() - size) / 2, (self.height() - size) / 2, size, size
        )
        self.drawer(painter, box, colour)
        painter.end()


# How long to let things settle before looking for repeats. Long enough
# that a run of edits costs one check, short enough that the button
# appears while the user is still looking at what they imported.
DUPLICATE_SETTLE_MS = 400


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # The build is in the title because the first question after "it works
        # on my laptop but not on that one" is which build each of them is
        # running, and until this there was nothing anywhere that could answer
        # it. Two machines showing the same digest are running the same code.
        self.setWindowTitle(f"Clippings Manager  —  {version.describe()}")
        self._open_at_a_size_that_fits()
        self.setAcceptDrops(True)

        self.config = load_config()
        self.name_index = NameIndex.load(settings=self.config.get("name_matching"))
        # One stack per interface. They are independent in every sense: undoing
        # on the board must never reach back into the press report, and the
        # export's "history clears on export" must only clear its own.
        self.undo_group = QUndoGroup(self)
        self.undo_stack = QUndoStack(self)
        # The duplicate check is asked for from many places and run
        # once, a moment later. See recheck_duplicates.
        self._duplicate_timer = None
        self._duplicates_running = False
        # Pairs the shipped rule did not flag but the user's own past verdicts
        # say are worth a second look. Never excluded from the report.
        self._duplicate_hints: list = []
        # Set the moment the window starts closing. The duplicate check runs on
        # another thread and finishes when it finishes; close the window while
        # one is in flight and its finishing callbacks land on a model Qt has
        # already deleted. That surfaces as "Signal source has been deleted"
        # and, from inside a slot, as the whole process going down without a
        # word - which is how it was found.
        self._closing = False
        # Whether an import checks itself. Remembered between runs: somebody who
        # turns it off has decided how they want to work, and being asked again
        # tomorrow morning would be its own annoyance.
        self._auto_duplicates = bool(
            export_dialog.load_settings().get("auto_duplicates", True))
        self._duplicate_pairs: list = []
        self._reader_thread = None
        self._reader = None
        self.board_undo = QUndoStack(self)
        for stack in (self.undo_stack, self.board_undo):
            stack.setUndoLimit(200)
            self.undo_group.addStack(stack)
        self.undo_stack.setActive(True)

        # Two pools, deliberately separate: the press report and the sentiment
        # board each own what was added while they were showing. They share one
        # id counter so an id from one can never resolve inside the other.
        self._clip_ids = itertools.count(1)
        self.model = ClipModel(self.name_index, self.config, self,
                               ids=self._clip_ids)
        self.board_model = ClipModel(self.name_index, self.config, self,
                                     ids=self._clip_ids)
        self.model.set_undo_stack(self.undo_stack)
        self.board_model.set_undo_stack(self.board_undo)
        self.preview: PreviewDialog | None = None
        self._group_serial = itertools.count(1)
        self._last_clicked_id: int | None = None
        self.mode = "standard"

        # A morning's work is written as it goes: the pictures once, the rest on
        # a short delay, so a sudden close costs nothing.
        # The wheel rule belongs to the window, not only to main.py. It is
        # installed on the application, so it holds for every control on every
        # card - and putting it here means anything that builds a MainWindow
        # gets it, which main.py alone did not guarantee.
        scroll.guard_the_wheel()

        self.store = SessionStore()
        self._restoring = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1500)
        self._save_timer.timeout.connect(self.save_session)

        self._build()
        self._wire()
        self._update_counts()
        self._native_drop = None
        QTimer.singleShot(0, self._install_native_drop)

    def stack(self, mode: str | None = None) -> QUndoStack:
        """The undo history of the named interface - by default, the one showing."""
        return (self.board_undo if (mode or self.mode) == "sentiment"
                else self.undo_stack)

    def stack_for(self, pool) -> QUndoStack:
        """The history that owns a pool's changes."""
        return self.board_undo if pool is self.board_model else self.undo_stack

    def pool(self, mode: str | None = None):
        """The clippings the named interface owns - by default, the one showing."""
        return (self.board_model if (mode or self.mode) == "sentiment"
                else self.model)

    def pool_for(self, clip_id: int):
        """Which pool a clipping belongs to, for signals that carry a bare id."""
        if self.model.row_for(clip_id) is not None:
            return self.model
        if self.board_model.row_for(clip_id) is not None:
            return self.board_model
        return None

    # ------------------------------------------------------- saved session
    def touch_session(self) -> None:
        """Something changed - write the manifest shortly."""
        if not self._restoring:
            self._save_timer.start()

    def _encode_pool(self, pool) -> list:
        """One pool's rows, with the pictures put in the blob folder."""
        rows = []
        for row in pool.rows:
            data = row.clip.image_bytes or b""
            # Worked out once per picture. The test is on the bytes themselves,
            # not on whether they look the same: if anything ever does replace a
            # clipping's picture, this notices and names it again.
            if data and row.blob_name and row.blob_of is data:
                blob = row.blob_name
            else:
                blob = self.store.put_blob(data) if data else ""
                row.blob_name = blob
                row.blob_of = data if blob else None
                if blob and row.thumb_png:
                    self.store.put_thumb(blob, row.thumb_png)
            rows.append({
                "id": row.id,
                "source_kind": row.source_kind,
                "source_name": row.source_name,
                "group_key": row.group_key,
                "blob": blob,
                "clip": encode_clip(row.clip),
            })
        return rows

    def save_session(self) -> None:
        """Write the manifest, then drop pictures nothing refers to."""
        if self._restoring:
            return
        try:
            standard = self._encode_pool(self.model)
            sentiment = self._encode_pool(self.board_model)
            self.store.save({
                "mode": self.mode,
                "division": getattr(self.board, "active", ""),
                # Both counters have to survive. A restarted group serial
                # re-mints a key a restored group already holds and the two runs
                # merge into one bracket; a restarted clip id collides across the
                # two pools, which is the very thing one shared counter prevents.
                "next_clip_id": self._peek_clip_id(),
                "next_group_serial": self._peek_group_serial(),
                "pools": {"standard": standard, "sentiment": sentiment},
            })
            self.store.collect(
                {r["blob"] for r in standard + sentiment if r["blob"]}
            )
        except Exception:  # noqa: BLE001 - a failed save must not stop the work
            pass

    def _peek_clip_id(self) -> int:
        """The next id the shared counter would hand out, without spending one."""
        value = next(self._clip_ids)
        self._clip_ids = itertools.count(value)
        return value

    def _peek_group_serial(self) -> int:
        value = next(self._group_serial)
        self._group_serial = itertools.count(value)
        return value

    # --------------------------------------------------------- restoring it
    def _wanted(self, payload: dict) -> bool:
        """Whether to put the saved work back, or start the day clean.

        The newspad is a daily job. Work saved earlier the same day is a crash to
        recover from, and comes back without a word. Work saved on an earlier day
        is yesterday's newspad, already exported - reopening tomorrow morning to
        180 of yesterday's clippings and having to clear them by hand would be a
        chore every single day. So that one case asks, and defaults to keeping
        the work, because losing a morning is the worse mistake of the two.
        """
        counts = payload.get("pools", {})
        total = sum(len(counts.get(key, [])) for key in ("standard", "sentiment"))
        if not total:
            return False

        stamp = str(payload.get("saved_at", ""))
        try:
            when = datetime.fromisoformat(stamp)
        except ValueError:
            return True                      # no readable date: keep the work
        if when.date() == datetime.now().date():
            return True                      # earlier today - a crash, recover it

        day = when.strftime("%A %d %B").replace(" 0", " ")
        box = QMessageBox(self)
        box.setWindowTitle("Clippings Manager")
        box.setIcon(QMessageBox.Question)
        box.setText(f"You have {total} clipping{'s' if total != 1 else ''} "
                    f"left from {day}.")
        box.setInformativeText("Open them again, or start today's newspad with "
                               "an empty list?")
        keep = box.addButton("Open them again", QMessageBox.AcceptRole)
        box.addButton("Start fresh", QMessageBox.DestructiveRole)
        box.setDefaultButton(keep)
        box.exec()
        return box.clickedButton() is keep


    def restore_session(self, ask: bool = True) -> int:
        """Put back whatever was open when the application last closed."""
        payload = self.store.load()
        if not payload:
            return 0
        # Worked out before anything is restored, because the answer is about the
        # manifest on disk rather than about what ends up in the list.
        stale = self.store.saved_by_another_build()
        if ask and not self._wanted(payload):
            self.store.clear()
            return 0

        # A full morning is ~50MB of pictures and takes a couple of seconds to
        # read back. That happens once, after the window is already on screen,
        # so an hourglass is enough - it should read as work, not as a hang.
        self._restoring = True
        restored, lost = 0, 0
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for key, pool in (("standard", self.model),
                              ("sentiment", self.board_model)):
                rows = []
                for saved in payload.get("pools", {}).get(key, []):
                    blob = saved.get("blob") or ""
                    data = self.store.get_blob(blob) if blob else b""
                    if blob and data is None:
                        lost += 1          # one clipping, not the whole morning
                        continue
                    clip = decode_clip(saved.get("clip", {}), data or b"")
                    row = Row(
                        clip=clip,
                        id=int(saved.get("id", 0)),
                        source_kind=saved.get("source_kind", "image"),
                        source_name=saved.get("source_name", ""),
                        group_key=saved.get("group_key", ""),
                    )
                    row.thumb_png = self.store.get_thumb(blob) if blob else None
                    if row.thumb_png is None:
                        row.thumb_png = thumbnail_png(clip)
                    row.thumbnail = pixmap_from_png(row.thumb_png)
                    rows.append(row)
                    restored += 1
                if rows:
                    pool.replace_all(rows)

            # Resume both counters above anything restored, whatever the
            # manifest claimed - a stale number is worse than a wasted one.
            highest = max(
                [0]
                + [r.id for r in self.model.rows]
                + [r.id for r in self.board_model.rows]
            )
            self._clip_ids = itertools.count(
                max(int(payload.get("next_clip_id", 1)), highest + 1)
            )
            self.model._ids = self._clip_ids
            self.board_model._ids = self._clip_ids
            self._group_serial = itertools.count(
                max(1, int(payload.get("next_group_serial", 1)))
            )

            division = payload.get("division") or ""
            if division and hasattr(self.board, "select_division"):
                self.board.select_division(division)
        except Exception:  # noqa: BLE001 - never let a bad file stop the app
            restored = 0
        finally:
            QApplication.restoreOverrideCursor()
            self._restoring = False

        if restored:
            self._update_counts()
            if self.model.rows:
                self._show_list()
            self._refresh_board()
            note = (f"Restored {restored} clipping"
                    f"{'s' if restored != 1 else ''} from your last session.")
            if lost:
                note += f" {lost} could not be read and were left out."
            if stale:
                # The pictures are fine; what came from an older build is what
                # the importer made of the document - the section headings, the
                # captions, whether a masthead was joined to its article. Those
                # are settled at import and re-importing is the only thing that
                # picks up the current rules, so say so rather than let a report
                # come out looking like last month's.
                note += (" These were read by a different build of the app — "
                         "import the documents again if the report comes out "
                         "wrong.")
            self._flash(note, "good" if not (lost or stale) else "info")
        # The clippings come back carrying last time's verdicts, including
        # which were switched off as repeats. That was true of the list as
        # it was; ask again for the list as it is now.
        self.recheck_duplicates()
        return restored

    def _fit_pages(self, *_args) -> None:
        """Only the page on show asks the window for room."""
        current = self.pages.currentIndex()
        for index in range(self.pages.count()):
            page = self.pages.widget(index)
            policy = page.sizePolicy()
            wanted = (QSizePolicy.Preferred if index == current
                      else QSizePolicy.Ignored)
            policy.setHorizontalPolicy(wanted)
            policy.setVerticalPolicy(wanted)
            page.setSizePolicy(policy)
        self.pages.adjustSize()

    # ------------------------------------------------------------- building
    def _build(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_header())

        # Two interfaces share one set of clippings: the standard press report,
        # and the division sentiment board. The dropdown in the header swaps them.
        self.pages = QStackedWidget()

        standard = QWidget()
        standard_layout = QVBoxLayout(standard)
        standard_layout.setContentsMargins(0, 0, 0, 0)
        standard_layout.setSpacing(0)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(18, 14, 18, 8)
        body_layout.setSpacing(12)
        self.cover = CoverCard()
        body_layout.addWidget(self.cover, 1)
        # Directly under the cover, where the department asked for it. A word
        # kept out of the report is a decision about the whole report, and the
        # cover is the part of this screen that is about the whole report.
        self.word_bar = WordListBar()
        self.word_bar.changed.connect(self._word_list_changed)
        body_layout.addWidget(self.word_bar)
        body_layout.addWidget(self._build_import_card())
        body_layout.addWidget(self._build_select_bar())
        # Under the bar that opens it, inside the page, so it scrolls away with
        # everything else and its drop-down surrenders the wheel to the page.
        body_layout.addWidget(self._build_filter_bar())
        self.list = ClipList()
        self.list.setModel(self.model)
        self.empty = self._build_empty_state()

        # One page, one scrollbar - the cards and the clippings in a single
        # document, the way a web page scrolls. Before this the cards scrolled
        # in their own frame and the list scrolled in another, so one turn of
        # the wheel did different things depending on where the pointer
        # happened to be, and coming back to the cover card meant finding a
        # different scrollbar. The list stands at its full height inside this
        # (ClipList.follow_content) rather than being a window onto itself;
        # Qt still only paints the rows on screen, so length costs nothing.
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        page_layout.addWidget(body)
        page_layout.addWidget(self.list)
        page_layout.addWidget(self.empty)
        page_layout.addStretch(0)

        self.body_scroll = CardScroll("StandardScroll", page)
        self.body_scroll.setSizePolicy(QSizePolicy.Expanding,
                                       QSizePolicy.Expanding)
        self.list.follow_content(True)
        standard_layout.addWidget(self.body_scroll, 1)
        self.list.hide()
        self.pages.addWidget(standard)

        self.board = SentimentBoard(self.config)
        self.pages.addWidget(self.board)

        layout.addWidget(self.pages, 1)
        layout.addWidget(self._build_footer())
        # A stacked layout takes the largest minimum across ALL pages, so the
        # hidden sentiment board was setting the window's minimum width even
        # while the press-report page was showing.
        self.pages.currentChanged.connect(self._fit_pages)
        self._fit_pages()
        self.setCentralWidget(root)

        self._build_floating(root)

    def _open_at_a_size_that_fits(self) -> None:
        """Open large, but never larger than the screen it opens on.

        It used to open at a flat 1500x950. On the 1366x768 laptops these offices
        run, that is wider and taller than the whole desktop: the window comes up
        with its right-hand edge past the edge of the screen, so the export
        buttons are somewhere the mouse cannot go and dragging the frame narrower
        is the only recovery. Which is exactly what was reported.
        """
        wanted = QSize(1500, 950)
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            room = screen.availableGeometry()
            wanted = QSize(min(wanted.width(), room.width() - 40),
                           min(wanted.height(), room.height() - 40))
        self.resize(wanted.expandedTo(QSize(720, 480)))

    # -- dark header -------------------------------------------------------
    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("Header")
        outer = QHBoxLayout(header)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        content = QWidget()
        content.setObjectName("HeaderContent")
        content.setStyleSheet("#HeaderContent { background: transparent; }")
        column = QVBoxLayout(content)
        column.setContentsMargins(20, 12, 20, 10)
        column.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(12)

        logo = QLabel()
        logo.setObjectName("Logo")
        logo.setFixedSize(40, 40)
        badge = theme.app_icon_path("icon_128.png")
        if badge:
            # The real mark, scaled down. It is already round with a transparent
            # surround, so it needs no frame of its own.
            logo.setPixmap(QPixmap(badge).scaled(
                34, 34, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            logo.setAlignment(Qt.AlignCenter)
            logo.setStyleSheet("background: transparent; border: none;")
        else:
            pixmap = QPixmap(40, 40)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            icons.paperclip(painter, QRectF(9, 9, 22, 22), theme.QORANGE)
            painter.end()
            logo.setPixmap(pixmap)
        top.addWidget(logo)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        # The badges drop under the title when the header runs out of room,
        # rather than the three of them together holding it 381px open.
        name_row = FlowLayout(spacing=8, vertical_spacing=2)
        name = QLabel("Clippings Manager")
        name.setObjectName("AppName")
        badge = QLabel("Northern Railway")
        badge.setObjectName("Badge")
        mode = QLabel("Daily newspad")
        mode.setObjectName("BadgeBlue")
        self.mode_badge = mode
        name_row.addWidget(name)
        name_row.addWidget(badge)
        name_row.addWidget(mode)
        # Elided rather than plain: a QLabel with wrap off reports a minimum
        # width equal to its whole sentence, and this one alone put a 430px floor
        # under the window.
        tagline = ElidedLabel(
            "Reads the division documents, works out the newspaper, and builds "
            "the newspad.",
            floor=120,
        )
        tagline.setObjectName("AppTagline")
        self.tagline = tagline
        titles.addLayout(name_row)
        titles.addWidget(tagline)
        top.addLayout(titles, 1)

        # The controls wrap onto a second line rather than holding the window
        # open. In a plain row every one of them adds its full width to the
        # window's minimum, and between them the interface switch, the zoom
        # buttons and the offline note put a 1171px floor under a program that
        # has to work on a 1366x768 laptop - which is what "the elements crop on
        # the right" turned out to be. A FlowLayout asks for the widest single
        # item instead of the sum of all of them.
        controls = FlowLayout(spacing=8, vertical_spacing=6)

        interface_label = QLabel("INTERFACE")
        interface_label.setObjectName("ModeLabel")
        controls.addWidget(interface_label)

        # Both interfaces on the header, side by side, rather than one of them
        # hidden inside a drop-down with the other. See ui/modeswitch.py.
        self.mode_switch = ModeSwitch()
        self.mode_switch.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        controls.addWidget(self.mode_switch)

        # Beside the interface switch rather than inside it, and the difference
        # is measured. A FlowLayout asks for the width of its WIDEST item, and
        # the switch is already that item, so every pixel a third entry added
        # to it would land on the window's own minimum width one for one: 579px
        # today, 737px with a third entry. As a button of its own it is
        # narrower than the switch and costs the floor nothing at all. That
        # matters here because main_window has a 1171px floor already, and
        # "the elements crop on the right" is a bug that has been reported.
        #
        # It is also not an interface. Both halves of the switch say how many
        # clippings they are holding; the trainer holds none, owns no pool, and
        # is a thing you open rather than a place you are. And it can be hidden
        # when there is nothing to train on, which a switch position cannot -
        # a three-way control that is sometimes two-way is one nobody learns.
        self.trainer_btn = QPushButton("Duplicates Trainer")
        self.trainer_btn.setObjectName("HeaderButton")
        self.trainer_btn.setCursor(Qt.PointingHandCursor)
        self.trainer_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.trainer_btn.setToolTip(
            "Teach it which cuttings are the same story and which are not."
            + "\n\n"
            + "It shows you pairs it is unsure about, a few at a time. What "
            "you decide is written down and can be saved to a file - it is "
            "evidence for setting the program's numbers in a later version, "
            "not something that changes the check while you are working.")
        self.trainer_btn.clicked.connect(self.open_trainer)
        controls.addWidget(self.trainer_btn)

        # Zoom. The office laptops are 1366x768 and the cards, the list and the
        # footer together want more room than that, so the whole application can
        # be drawn smaller. It has to be the whole application: most of what is
        # on screen is painted rather than laid out, so a bigger font moves
        # nothing - see ui/zoom.py.
        self.zoom_buttons = ZoomButtons(zoom.as_percent(zoom.level()))
        self.zoom_buttons.stepped.connect(self._zoom_by)
        self.zoom_buttons.reset.connect(self._zoom_normal)
        self.zoom_buttons.picked.connect(self._zoom_to)
        # The names the rest of the window and the tests use.
        self.zoom_out_btn = self.zoom_buttons.smaller
        self.zoom_in_btn = self.zoom_buttons.bigger
        self.zoom_label = self.zoom_buttons.percent
        controls.addWidget(self.zoom_buttons)

        self.offline_note = QPushButton("Runs offline")
        self.offline_note.setObjectName("HeaderButton")
        self.offline_note.setCursor(Qt.PointingHandCursor)
        # The wording is exact on purpose. The program does the whole morning's
        # work with the cable unplugged, and that is the promise worth keeping;
        # but there is now one button that asks GitHub whether a newer version
        # exists, and a badge that flatly said "nothing reaches the network"
        # would have been untrue the moment somebody pressed it.
        self.offline_note.setToolTip(
            "Every document is read on this machine. Nothing is uploaded, and "
            "nothing reaches the network unless you ask it to.\n\nPress to see "
            "where your settings are kept, to have a copy written somewhere "
            "that is backed up, and to check for a newer version.")
        self.offline_note.clicked.connect(self.where_things_are_kept)
        controls.addWidget(self.offline_note)
        top.addLayout(controls)
        column.addLayout(top)

        rule = QWidget()
        rule.setObjectName("HeaderRule")
        rule.setFixedHeight(1)
        column.addWidget(rule)

        # Three sentences of guidance in a plain row were holding the whole
        # window open at 985px between them. They wrap onto a second line when
        # the window is narrow, and trim only when even that is not enough.
        hints = FlowLayout(spacing=22, vertical_spacing=2)
        for text in (
            "Word and PDF both import — the division is read from the file name",
            "Ctrl+V pastes a clipping straight out of WhatsApp Web",
            "Ctrl+Z undoes anything, including a misdrag",
        ):
            label = ElidedLabel("•  " + text, floor=150)
            label.setObjectName("HeaderHint")
            hints.addWidget(label)
        column.addLayout(hints)

        outer.addWidget(content, 1)
        accent = QWidget()
        accent.setObjectName("HeaderAccent")
        accent.setFixedWidth(4)
        outer.addWidget(accent)
        return header

    # -- how big everything is drawn ---------------------------------------
    def _zoom_by(self, steps: int) -> None:
        self._zoom_to(zoom.step(zoom.level(), steps))

    def _zoom_normal(self) -> None:
        self._zoom_to(zoom.NORMAL)

    def _zoom_to(self, size: float) -> None:
        """Draw everything at this size, from the next start of the program.

        Qt reads its display scale once, when the application object is made,
        and offers no way to change it afterwards - and the display scale is the
        only thing that scales the painted clipping cards along with the
        widgets. So the choice is written down and the application is started
        again, with the morning's work saved first and restored on the way back
        in, which is the same path a normal close and reopen takes.
        """
        current = zoom.level()
        if abs(size - current) < 0.001:
            self._flash(
                "Already at " + zoom.as_percent(current) + ".", "info")
            return

        answer = QMessageBox.question(
            self, "Change the size of the application",
            f"Everything will be drawn at {zoom.as_percent(size)} instead of "
            f"{zoom.as_percent(current)}.\n\n"
            f"The application has to start again for this, because the size is "
            f"fixed when it opens. Your clippings are saved first and come "
            f"straight back.\n\nGo ahead?",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return

        zoom.remember(size)
        self.zoom_label.setText(zoom.as_percent(size))
        if not self._restart():
            # The size is written down and stands; only the restart failed. Say
            # exactly that, rather than leaving somebody to wonder why nothing
            # happened - and rather than quietly putting the old size back,
            # which would throw away a choice they have already made.
            QMessageBox.information(
                self, "Close and open the application to see the new size",
                f"The size is set to {zoom.as_percent(size)}, but the "
                f"application could not restart itself.\n\nClose it and open "
                f"it again and it will come back at the new size, with your "
                f"clippings where you left them.")

    def _restart(self) -> bool:
        """Save everything, start a second copy, and let this one go."""
        import subprocess

        for card in (self.cover, self.board.cover, self.heading,
                     getattr(self.board, "heading", None)):
            try:
                if card is not None:
                    card.flush()
            except Exception:  # noqa: BLE001
                pass
        try:
            self._save_timer.stop()
            self.save_session()
        except Exception:  # noqa: BLE001 - a restart must not lose the morning
            QMessageBox.warning(
                self, "Your work could not be saved",
                "The application was not restarted, because the clippings "
                "could not be written down first.")
            return False

        try:
            if getattr(sys, "frozen", False):
                command = [sys.executable, *sys.argv[1:]]
            else:
                command = [sys.executable, *sys.argv]
            # A child inherits this process's environment, and this process has
            # QT_SCALE_FACTOR set to the size it is drawing at. Handing that on
            # would tell the new copy to draw at the OLD size. It reads the size
            # it should use from the settings itself, so the variable is taken
            # out of what it inherits.
            fresh = dict(os.environ)
            fresh.pop(zoom.VARIABLE, None)
            subprocess.Popen(command, cwd=str(Path.cwd()), close_fds=True,
                             env=fresh)
        except Exception:  # noqa: BLE001
            return False
        # Quit rather than close: the new copy is already starting, and the
        # session has been written, so there is nothing left to ask about.
        QTimer.singleShot(120, QApplication.quit)
        return True

    # -- import card -------------------------------------------------------
    def _build_import_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 13, 16, 15)
        layout.setSpacing(11)

        title_row = QHBoxLayout()
        title_row.setSpacing(9)
        step = QLabel("2")
        step.setObjectName("StepNumber")
        step.setFixedSize(24, 24)
        step.setAlignment(Qt.AlignCenter)
        title = QLabel("Add today's clippings")
        title.setObjectName("CardTitle")
        self.count_pill = QLabel("0 clips")
        self.count_pill.setObjectName("CountPill")
        title_row.addWidget(step)
        title_row.addWidget(title)
        title_row.addWidget(self.count_pill)
        title_row.addStretch(1)

        self.clear_all_btn = QPushButton("Clear all")
        self.clear_all_btn.setObjectName("LinkDanger")
        self.collapse_btn = QPushButton("Collapse")
        self.collapse_btn.setObjectName("Quiet")
        title_row.addWidget(self.clear_all_btn)
        title_row.addWidget(self.collapse_btn)
        layout.addLayout(title_row)

        self.drop = QFrame()
        self.drop.setObjectName("DropZone")
        drop_layout = QVBoxLayout(self.drop)
        drop_layout.setContentsMargins(16, 20, 16, 20)
        drop_layout.setSpacing(11)

        # Centred while they fit on one line, stacked when they do not. These
        # three are the way documents get in, so they must never be the controls
        # that fall off the edge.
        buttons = FlowLayout(spacing=10, vertical_spacing=8,
                             alignment=Qt.AlignHCenter)
        self.btn_photos = QPushButton("+  Add photos")
        self.btn_photos.setObjectName("NavyFilled")
        self.btn_word = QPushButton("+  From Word (.docx)")
        self.btn_word.setObjectName("NavyOutline")
        self.btn_pdf = QPushButton("+  From PDF (.pdf)")
        self.btn_pdf.setObjectName("OrangeOutline")
        for button in (self.btn_photos, self.btn_word, self.btn_pdf):
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(38)
            buttons.addWidget(button)
        drop_layout.addLayout(buttons)

        # Elided, not wrapped. Wrapping solved the width - the sentence was a
        # 645px floor under the card - but a wrapped QLabel reports a taller hint
        # even while it sits on one line, and those 32px were enough to push the
        # whole card stack past the viewport and stop the cover preview growing
        # with the window.
        hint = ElidedLabel(
            "Drag images straight from WhatsApp Web onto this panel — or drop "
            "photos, Word and PDF files here, or paste with Ctrl+V",
            floor=180,
        )
        hint.setObjectName("CardHint")
        hint.setAlignment(Qt.AlignCenter)
        drop_layout.addWidget(hint)
        layout.addWidget(self.drop)

        # Under the drop zone, inside the same card - the caption above every
        # clipping and the paper it prints on, in one place, next to the step
        # that puts the clippings in.
        self.heading = HeadingLayoutCard(
            "standard",
            "Sets the headline printed above each clipping, and the page the "
            "newspad is built on.",
        )
        layout.addWidget(self.heading)

        self.status = QLabel()
        self.status.setObjectName("StatusInfo")
        self.status.setWordWrap(True)
        self.status.hide()
        layout.addWidget(self.status)

        self.import_card = card
        return card

    # -- select-all bar ----------------------------------------------------
    def _build_select_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet("background: transparent;")
        row = QHBoxLayout(bar)
        # 64 on the right, not 4: the floating scroll and undo buttons hover in
        # that gutter, and anything ending flush with the edge disappears under
        # them.
        row.setContentsMargins(4, 0, 64, 0)
        row.setSpacing(12)

        self.select_all_btn = QPushButton("Select all")
        self.select_all_btn.setObjectName("LinkNavy")
        self.select_all_btn.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.select_all_btn)

        # Elided, not plain. A QLabel refuses to be narrower than its whole
        # sentence, and this sentence is 469px of it - the widest thing in the
        # row, and the reason the row could not shrink. The full text stays on
        # its own tooltip.
        self.select_hint = ElidedLabel(
            "Hold Ctrl to pick several, Shift for a run, or drag the handle to "
            "move a block anywhere",
            floor=90,
        )
        self.select_hint.setObjectName("SubtleHint")
        row.addWidget(self.select_hint)
        row.addStretch(1)

        # The bubbles wrap onto a second line rather than forcing the window
        # wider than the screen. A FlowLayout asks for the width of its widest
        # single item, not the sum of them all - which is what stopped this row
        # shrinking once there were five buttons on it. With repeats found and
        # a selection live, the old row wanted 1374px: wider than the 1366px
        # laptops this is used on, so it cropped even maximised.
        bubbles = FlowLayout(spacing=12, vertical_spacing=6)
        row.addLayout(bubbles)

        # Above the per-row chevrons, because that is what they do to the whole
        # list. A morning is six or seven documents and a hundred clippings; being
        # able to shut them all and open the one being worked on is the difference
        # between a list and a wall.
        self.collapse_all_btn = QPushButton("Collapse all")
        self.collapse_all_btn.setToolTip("Fold every document down to its name")
        self.expand_all_btn = QPushButton("Expand all")
        self.expand_all_btn.setToolTip("Open every document again")
        for button, filled in ((self.collapse_all_btn, False),
                               (self.expand_all_btn, False)):
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton {{ background: {theme.SURFACE};"
                f" color: {theme.NAVY};"
                f" border: 1px solid {theme.HAIRLINE_STRONG};"
                " border-radius: 11px; padding: 4px 12px;"
                " font-size: 11px; font-weight: 700; }"
                f"QPushButton:hover {{ background: {theme.NAVY_WASH};"
                f" border-color: {theme.NAVY}; }}"
            )
            bubbles.addWidget(button)
        self.collapse_all_btn.clicked.connect(lambda: self._fold_all(True))
        self.expand_all_btn.clicked.connect(lambda: self._fold_all(False))

        # The third bubble, in the same style as its neighbours. It is not
        # shown at all when nothing is flagged: a button that does nothing is
        # worse than no button, and on most mornings there are no repeats.
        self.duplicates_btn = QPushButton("Preview and Delete Duplicates")
        self.duplicates_btn.setCursor(Qt.PointingHandCursor)
        self.duplicates_btn.setToolTip(
            "Look at each suspected repeat beside the clipping it repeats, "
            "and decide.")
        self.duplicates_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE};"
            f" color: {theme.DANGER};"
            f" border: 1px solid {theme.DANGER};"
            " border-radius: 11px; padding: 4px 12px;"
            " font-size: 11px; font-weight: 700; }"
            f"QPushButton:hover {{ background: {theme.SURFACE};"
            f" border-color: {theme.DANGER}; }}"
        )
        self.duplicates_btn.clicked.connect(self.review_duplicates)
        self.duplicates_btn.hide()
        bubbles.addWidget(self.duplicates_btn)

        # The check runs by itself on every change, quietly. This is for being
        # sure: it looks again on demand, from scratch, and says what it found
        # either way - because "nothing flagged" and "never looked" are the
        # same thing on screen otherwise.
        self.check_dupes_btn = QPushButton("Check for Duplicates")
        self.check_dupes_btn.setCursor(Qt.PointingHandCursor)
        self.check_dupes_btn.setToolTip(
            "Look again now, from scratch, and say what was found." + '\n\n'
            + "The check already runs by itself on every import, and "
            "remembers what it has read - so it never re-reads the same "
            "clipping twice. This throws all of that away and does the "
            "lot again, which takes a moment on a full morning. Worth it "
            "after cropping or straightening, when what was read before "
            "no longer matches the picture.")
        self.check_dupes_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE};"
            f" color: {theme.NAVY};"
            f" border: 1px solid {theme.HAIRLINE_STRONG};"
            " border-radius: 11px; padding: 4px 12px;"
            " font-size: 11px; font-weight: 700; }"
            f"QPushButton:hover {{ background: {theme.NAVY_WASH};"
            f" border-color: {theme.NAVY}; }}"
        )
        self.check_dupes_btn.clicked.connect(self.check_duplicates_now)
        self.check_dupes_btn.hide()
        bubbles.addWidget(self.check_dupes_btn)

        # Beside the button it governs, so what it turns off is obvious. With it
        # off nothing is checked until the button is pressed - which is what
        # somebody wants when they are importing six files one after another and
        # would rather the machine left them alone until they have finished.
        self.auto_dupes = QCheckBox("Check automatically")
        self.auto_dupes.setCursor(Qt.PointingHandCursor)
        self.auto_dupes.setToolTip(
            "On: every import is checked for repeats by itself.\n"
            "Off: nothing is checked until you press Check for Duplicates.\n\n"
            "The button works either way.")
        self.auto_dupes.setStyleSheet(
            f"QCheckBox {{ color: {theme.MUTED}; font-size: 11px;"
            " font-weight: 700; spacing: 5px; }"
            f"QCheckBox:hover {{ color: {theme.NAVY}; }}"
        )
        self.auto_dupes.setChecked(self._auto_duplicates)
        self.auto_dupes.toggled.connect(self._auto_duplicates_toggled)
        self.auto_dupes.hide()
        bubbles.addWidget(self.auto_dupes)

        # In the bubbles rather than the crown, for two reasons that are both
        # about this window. The crown is not inside a scroll area, so a
        # drop-down up there would keep the mouse wheel and change itself while
        # somebody tried to scroll the page. And this row already hides itself
        # when there is nothing in the list, so the control cannot exist when
        # there is nothing to filter.
        self.filter_btn = QPushButton("Filter and arrange")
        self.filter_btn.setCursor(Qt.PointingHandCursor)
        self.filter_btn.setCheckable(True)
        self.filter_btn.setToolTip(
            "Show only some of the clippings, or put them in another order - "
            "by regional or national, by language, by how big the paper is."
            + "\n\n"
            + "It changes what you see, never what is exported, and never the "
            "order the clippings are really in.")
        self.filter_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE};"
            f" color: {theme.NAVY};"
            f" border: 1px solid {theme.HAIRLINE_STRONG};"
            " border-radius: 11px; padding: 4px 12px;"
            " font-size: 11px; font-weight: 700; }"
            f"QPushButton:hover {{ background: {theme.NAVY_WASH};"
            f" border-color: {theme.NAVY}; }}"
            f"QPushButton:checked {{ background: {theme.NAVY};"
            f" color: #FFFFFF; border-color: {theme.NAVY}; }}"
        )
        self.filter_btn.toggled.connect(self._filter_bar_shown)
        bubbles.addWidget(self.filter_btn)

        self.clear_selection_btn = QPushButton("Clear selection")
        self.clear_selection_btn.setObjectName("Quiet")
        self.clear_selection_btn.hide()
        bubbles.addWidget(self.clear_selection_btn)

        self.select_bar = bar
        bar.hide()
        return bar

    def _build_filter_bar(self):
        from .filter_bar import FilterBar

        self.filter_bar = FilterBar()
        self.filter_bar.changed.connect(self._lens_changed)
        self.filter_bar.editCategories.connect(self.edit_categories)
        self.filter_bar.hide()
        return self.filter_bar

    def _filter_bar_shown(self, shown: bool) -> None:
        """The chip opens and shuts the strip.

        Shutting it clears the lens rather than leaving it on out of sight.
        A list quietly hiding half its clippings with no control on screen to
        say why is the one state this feature must never be able to reach.
        """
        if shown:
            # Shown first, then filled. The refresh declines to do anything
            # for a strip that is not on screen, so the other way round opened
            # the strip with every row empty.
            self.filter_bar.show()
            self._refresh_filter_choices()
        else:
            self.filter_bar.hide()
            if self.pool().lens.busy:
                self.filter_bar.clear()

    def _refresh_filter_choices(self) -> None:
        """Rebuild the chips from what is actually in the list right now."""
        bar = getattr(self, "filter_bar", None)
        if bar is None or not bar.isVisible():
            return
        pool = self.pool()
        bar.offer([row.clip for row in pool.rows], pool.book)
        bar.say(pool.shown_count(), len(pool.rows))

    def _lens_changed(self) -> None:
        pool = self.pool()
        self.list.commit_editor()
        pool.set_lens(self.filter_bar.lens())
        self.filter_bar.say(pool.shown_count(), len(pool.rows))
        self._sync_fold_buttons()
        self._update_counts()
        self.list.refresh_height()

    def edit_categories(self) -> None:
        """Say which papers are regional, which are Hindi, which are the big
        ones. What is set here is kept when the program is updated."""
        from .categories_dialog import CategoriesDialog

        pool = self.pool()
        screen = CategoriesDialog([row.clip for row in pool.rows], self)
        screen.exec()
        pool.forget_book()
        self.board_model.forget_book()
        self._refresh_filter_choices()
        if pool.lens.busy:
            self._lens_changed()

    def _fold_all(self, collapsed: bool) -> None:
        """Shut every document in the list, or open every one."""
        pool = self.pool()
        if pool.group_count() == 0:
            return
        self.list.commit_editor()
        pool.set_all_collapsed(collapsed)
        if collapsed:
            self.list.scrollToTop()
        self._update_counts()

    def _sync_fold_buttons(self) -> None:
        """They belong to documents; loose clippings have nothing to fold."""
        if not hasattr(self, "collapse_all_btn"):
            return
        groups = self.model.group_count()
        for button in (self.collapse_all_btn, self.expand_all_btn):
            button.setVisible(groups > 0)
        # Not tied to documents: loose clippings pasted from WhatsApp repeat
        # one another as readily as imported ones do.
        if hasattr(self, "check_dupes_btn"):
            self.check_dupes_btn.setVisible(self.model.clip_count > 0)
        if hasattr(self, "auto_dupes"):
            self.auto_dupes.setVisible(self.model.clip_count > 0)

    def _build_empty_state(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setAlignment(Qt.AlignCenter)
        label = QLabel(
            "No clippings yet.\n\n"
            "Use + Add photos, + From Word or + From PDF above,\n"
            "or drop files anywhere in this window."
        )
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(
            f"color: {theme.MUTED}; font-size: 13px; line-height: 170%;"
        )
        layout.addWidget(label)
        return panel

    # -- footer ------------------------------------------------------------
    def _build_footer(self) -> QWidget:
        bar = QWidget()
        self.footer = bar
        bar.setObjectName("Footer")
        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 11, 20, 11)
        row.setSpacing(12)

        self.ready = QLabel()
        self.ready.setObjectName("FooterCount")
        row.addWidget(self.ready)
        row.addStretch(1)

        self.btn_docx_out = QPushButton("Word (.docx)")
        self.btn_docx_out.setObjectName("NavyOutline")
        self.btn_pdf_out = QPushButton("Generate PDF")
        self.btn_pdf_out.setObjectName("OrangeFilled")
        for button in (self.btn_docx_out, self.btn_pdf_out):
            button.setMinimumHeight(38)
            button.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.btn_docx_out)
        row.addWidget(self.btn_pdf_out)
        return bar

    # -- floating layers ---------------------------------------------------
    def _page_showing(self):
        """The one long page the wheel scrolls, for the interface on screen."""
        if self.mode == "sentiment":
            return getattr(self.board, "page", None)
        return getattr(self, "body_scroll", None)

    def _scroll_to_top(self) -> None:
        """Whichever interface is showing scrolls, and it is the PAGE that does.

        This used to scroll the clipping list in one interface and the sentiment
        columns in the other. Neither is the thing that scrolls any more: both
        interfaces are one long page now, the list stands at its full height
        inside it, and a column only scrolls its own cards. So the button did
        nothing at all in the standard interface, and in the sentiment one it
        moved four columns while leaving the page where it was.
        """
        page = self._page_showing()
        if page is not None:
            page.verticalScrollBar().setValue(0)
        if self.mode == "sentiment":
            self.board.scroll_columns(top=True)

    def _scroll_to_bottom(self) -> None:
        page = self._page_showing()
        if page is not None:
            bar = page.verticalScrollBar()
            bar.setValue(bar.maximum())
        if self.mode == "sentiment":
            self.board.scroll_columns(top=False)

    def _build_floating(self, parent: QWidget) -> None:
        # right-hand stack: to top, undo, redo, to bottom
        self.float_top = IconButton(icons.chevron_up, "Back to the top (Home)", parent)
        self.float_undo = IconButton(icons.undo, "Undo (Ctrl+Z)", parent)
        self.float_redo = IconButton(icons.redo, "Redo (Ctrl+Y)", parent)
        self.float_bottom = IconButton(
            icons.chevron_down, "Jump to the bottom (End)", parent
        )
        self.floaters = [
            self.float_top, self.float_undo, self.float_redo, self.float_bottom
        ]
        for button in self.floaters:
            button.hide()

        # batch bar
        self.batch = QFrame(parent)
        self.batch.setObjectName("BatchBar")
        self.batch.setStyleSheet(
            f"#BatchBar {{ background: {theme.NAVY}; border-radius: 16px; }}"
            f"QLabel {{ color: white; font-size: 12px; font-weight: 700;"
            f" background: transparent; }}"
            f"QPushButton {{ background: rgba(255,255,255,0.12); border: none;"
            f" border-radius: 9px; padding: 6px 11px; color: white; font-size: 11px;"
            f" font-weight: 600; }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,0.24); }}"
            f"QPushButton#BatchMerge {{ background: {theme.ORANGE}; font-weight: 700; }}"
            f"QPushButton#BatchMerge:hover {{ background: {theme.ORANGE_DEEP}; }}"
            f"QPushButton#BatchDelete {{ background: #DC2626; font-weight: 700; }}"
            f"QPushButton#BatchDelete:hover {{ background: #B91C1C; }}"
        )
        row = QHBoxLayout(self.batch)
        row.setContentsMargins(14, 9, 10, 9)
        row.setSpacing(7)

        self.batch_count = QLabel("0")
        self.batch_count.setStyleSheet(
            f"background: {theme.ORANGE}; border-radius: 9px; padding: 2px 9px;"
            f" color: white; font-weight: 800; font-size: 11px;"
        )
        row.addWidget(self.batch_count)
        row.addWidget(QLabel("selected"))
        row.addSpacing(6)

        self.batch_merge = QPushButton("Merge into one")
        self.batch_merge.setObjectName("BatchMerge")
        self.batch_name = QPushButton("Set newspaper")
        self.batch_top = QPushButton("Top")
        self.batch_up = QPushButton("Up")
        self.batch_down = QPushButton("Down")
        self.batch_bottom = QPushButton("Bottom")
        self.batch_rotate = QPushButton("Rotate")
        self.batch_exclude = QPushButton("Exclude")
        self.batch_delete = QPushButton("Delete")
        self.batch_delete.setObjectName("BatchDelete")
        self.batch_close = QPushButton("✕")
        self.batch_close.setFixedWidth(30)
        for button in (
            self.batch_merge, self.batch_name, self.batch_top, self.batch_up,
            self.batch_down, self.batch_bottom, self.batch_rotate,
            self.batch_exclude, self.batch_delete, self.batch_close,
        ):
            button.setCursor(Qt.PointingHandCursor)
            row.addWidget(button)
        self.batch.hide()

    # -------------------------------------------------------------- wiring
    def _wire(self) -> None:
        self.btn_word.clicked.connect(lambda: self._choose("word"))
        self.btn_pdf.clicked.connect(lambda: self._choose("pdf"))
        self.btn_photos.clicked.connect(lambda: self._choose("photos"))
        self.clear_all_btn.clicked.connect(self._clear_all)
        self.collapse_btn.clicked.connect(self._toggle_card)

        self.select_all_btn.clicked.connect(self._toggle_select_all)
        self.clear_selection_btn.clicked.connect(self.model.clear_selection)

        self.list.clipAction.connect(self._on_clip_action)
        self.list.groupAction.connect(self._on_group_action)
        self.list.labelEdited.connect(self._on_label_edited)
        self.list.urlEdited.connect(self._on_url_edited)
        self.list.previewRequested.connect(self.open_preview)
        self.list.reorderRequested.connect(self._on_reorder)
        self.list.selectionToggled.connect(self._on_selection_toggled)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)

        self.model.countsChanged.connect(self._update_counts)
        self.model.selectionChanged.connect(self._update_selection_ui)
        self.board_model.countsChanged.connect(self._update_counts)
        self.board_model.selectionChanged.connect(self._update_selection_ui)

        # Anything that changes a clipping goes through one of these.
        self.model.countsChanged.connect(self.touch_session)
        self.board_model.countsChanged.connect(self.touch_session)
        self.undo_stack.indexChanged.connect(lambda _i: self.touch_session())
        self.board_undo.indexChanged.connect(lambda _i: self.touch_session())

        self.mode_switch.changed.connect(self.set_mode)
        self.board.assignRequested.connect(self._assign_sentiment)
        self.board.previewRequested.connect(self.open_preview)
        self.board.divisionChanged.connect(lambda _c: self._refresh_board())
        self.board.addRequested.connect(self._add_into_section)
        self.board.exportRequested.connect(self._export_dossier)
        self.board.clearRequested.connect(self._clear_division)
        self.board.titleEdited.connect(self._on_board_title)
        self.board.urlEdited.connect(self._on_board_url)
        self.board.cardDeleted.connect(self._on_board_delete)
        self.board.cardRotated.connect(self._on_board_rotate)
        # Deliberately NOT connected to _update_counts: the dossier cover does
        # not change any clipping count, and routing it through the recount put
        # set_division and _touch in a loop.

        self.float_top.clicked.connect(self._scroll_to_top)
        self.float_bottom.clicked.connect(self._scroll_to_bottom)
        self.float_undo.clicked.connect(self.undo_group.undo)
        self.float_redo.clicked.connect(self.undo_group.redo)
        self.undo_group.canUndoChanged.connect(self.float_undo.setEnabled)
        self.undo_group.canRedoChanged.connect(self.float_redo.setEnabled)
        self.undo_stack.indexChanged.connect(self._after_undo_change)
        self.float_undo.setEnabled(False)
        self.float_redo.setEnabled(False)

        self.batch_merge.clicked.connect(self._merge_selected)
        self.batch_name.clicked.connect(lambda: self._bulk_field("newspaper"))
        self.batch_top.clicked.connect(lambda: self._batch_move("top"))
        self.batch_up.clicked.connect(lambda: self._batch_move("up"))
        self.batch_down.clicked.connect(lambda: self._batch_move("down"))
        self.batch_bottom.clicked.connect(lambda: self._batch_move("bottom"))
        self.batch_rotate.clicked.connect(self._batch_rotate)
        self.batch_exclude.clicked.connect(self._batch_exclude)
        self.batch_delete.clicked.connect(self._batch_delete)
        self.batch_close.clicked.connect(self.model.clear_selection)

        self.btn_pdf_out.clicked.connect(lambda: self._export("pdf"))
        self.btn_docx_out.clicked.connect(lambda: self._export("docx"))

        QShortcut(QKeySequence.Undo, self, self.undo_stack.undo)
        QShortcut(QKeySequence.Redo, self, self.undo_stack.redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, self.undo_stack.redo)
        QShortcut(QKeySequence.Paste, self, self.paste_clipboard)
        QShortcut(QKeySequence("Ctrl+A"), self, self._select_all)
        QShortcut(QKeySequence("Home"), self, lambda: self.list.scrollToTop())
        QShortcut(QKeySequence("End"), self, lambda: self.list.scrollToBottom())
        QShortcut(QKeySequence(Qt.Key_Delete), self, self._batch_delete)
        QShortcut(QKeySequence(Qt.Key_Escape), self,
                  lambda: self.pool().clear_selection())

        self.list.verticalScrollBar().valueChanged.connect(self._place_floating)

    def _install_native_drop(self) -> None:
        """Read drags the way Explorer does, anywhere in the window.

        Chrome delivers a dragged image as a COM stream that Qt will not read, so
        the picture never arrives. Reading it needs a real IDropTarget on a window
        handle - and the whole window, not just the dotted panel, because a photo
        dropped an inch below it should still land.

        Ours chains in front of Qt's rather than replacing it: Qt's own drags run
        through the same OLE loop, so a target that simply took over would stop
        rows reordering and cards moving between sentiment columns. Only the drag
        Qt cannot read is claimed; everything else is forwarded untouched.
        """
        self._native_drop = win_drop.install_window(
            self, self._native_files_dropped, self._native_drag_hover,
            self._native_drop_empty,
        )
        if self._native_drop is None:
            # Could not get in front of Qt safely - keep the old panel-only
            # registration rather than losing the browser drag altogether.
            self._native_drop = win_drop.install(
                self.drop, self._native_files_dropped, self._native_drag_hover,
                self._native_drop_empty,
            )
        if self._native_drop is None and win_drop.Available:
            self.drop.setAcceptDrops(True)

    def _native_drop_empty(self) -> None:
        QMessageBox.information(
            self, "Nothing came with that drop",
            "The drag was accepted but carried no picture.\n\n"
            "Right-click the image in WhatsApp Web, choose Copy image, then press "
            "Ctrl+V here.",
        )

    def _native_drag_hover(self, active: bool) -> None:
        self.drop.setProperty("hot", bool(active))
        self.drop.style().unpolish(self.drop)
        self.drop.style().polish(self.drop)

    def _section_under(self, point) -> "Section | None":
        """Which sentiment column, if any, the pointer was over when it let go."""
        if point is None or self.mode != "sentiment":
            return None
        try:
            from PySide6.QtCore import QPoint

            where = QPoint(int(point[0]), int(point[1]))
            # widgetAt asks the window system what is on top at that point, which
            # during a drag can be the browser's own drag image or any window
            # that happens to overlap - it answers None and the drop forgets
            # which column it landed on. Our own hit test does not care what is
            # stacked above us, so it is the one to trust when the first is
            # silent.
            candidates = [QApplication.widgetAt(where),
                          self.childAt(self.mapFromGlobal(where))]
            for widget in candidates:
                while widget is not None:
                    section = getattr(widget, "section", None)
                    if section is not None and hasattr(widget, "cardsDropped"):
                        return section
                    widget = widget.parentWidget()
        except Exception:  # noqa: BLE001 - fall back to the ordinary route
            return None
        return None

    def _native_files_dropped(self, files: list, point=None) -> None:
        """Images pulled straight out of a browser drag."""
        section = self._section_under(point)
        if section is not None:
            self._pending_section = section
        clips = []
        for data, name in files:
            try:
                clips.append(self._clip_from_bytes(data, name))
            except Exception:  # noqa: BLE001 - skip anything unreadable
                continue
        if not clips:
            # A drag that carried nothing readable would otherwise leave its
            # column armed, and the next paste would quietly go there.
            self._pending_section = None
        if clips:
            self._add_loose(clips)
        else:
            self._flash("Those files were not images.", "bad")

    # ----------------------------------------------------------- importing
    def _choose(self, kind: str) -> None:
        filters = {
            "word": ("Choose the division Word files", "Word documents (*.docx)"),
            "pdf": ("Choose the division PDF files", "PDF documents (*.pdf)"),
            "photos": (
                "Choose clipping images",
                "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)",
            ),
        }[kind]
        paths, _ = QFileDialog.getOpenFileNames(self, filters[0], "", filters[1])
        if paths:
            self.import_paths([Path(p) for p in paths])

    def import_paths(self, paths: list[Path]) -> None:
        # Whatever is on screen owns what arrives: the press report and the
        # sentiment board keep separate sets of clippings.
        target = self.pool()
        files: list[Path] = []
        for path in paths:
            if path.is_dir():
                files.extend(
                    sorted(
                        p for p in path.iterdir()
                        if p.suffix.lower() in IMAGE_SUFFIXES
                        or p.suffix.lower() in (".docx", ".pdf")
                    )
                )
            else:
                files.append(path)
        files = [f for f in files if not f.name.startswith("~$")]
        if not files:
            return

        progress = QProgressDialog("Reading documents…", "Stop", 0, len(files), self)
        progress.setWindowTitle("Importing")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(300)

        added: list = []
        problems: list[str] = []
        # Kept apart from the problems: a document whose captions are
        # glyph numbers still imported perfectly, so it has no business
        # stopping the work with a box on every single import.
        advisories: list[str] = []
        loose: list[Clip] = []

        for number, path in enumerate(files):
            if progress.wasCanceled():
                break
            progress.setValue(number)
            progress.setLabelText(f"Reading {path.name}…")
            QApplication.processEvents()

            suffix = path.suffix.lower()
            try:
                if suffix == ".docx":
                    clips, warnings = extract_docx(path, config=self.config)
                    kind = "word"
                elif suffix == ".pdf":
                    clips, warnings = extract_pdf(path, config=self.config)
                    kind = "pdf"
                elif suffix in IMAGE_SUFFIXES:
                    loose.append(self._clip_from_image(path))
                    continue
                else:
                    problems.append(f"{path.name}: not a Word file, a PDF or an image.")
                    continue
            except ExtractionError as exc:
                problems.append(str(exc))
                continue
            except Exception as exc:  # noqa: BLE001 - never show a raw traceback
                problems.append(
                    f"{path.name}: could not be read ({type(exc).__name__})."
                )
                continue

            for note in warnings:
                (advisories if is_advisory(note) else problems).append(note)
            if not clips:
                problems.append(f"{path.name}: no clippings found inside it.")
                continue
            division = detect_division(path.name, self.config) or ""
            title = path.name + (f"  ·  {division}" if division else "")
            added.extend(
                target.make_rows(
                    clips, kind, title, f"{path}#{next(self._group_serial)}"
                )
            )

        progress.setValue(len(files))

        if loose:
            self._add_loose(loose)
        if not added and loose:
            return

        if added:
            self.stack_for(target).push(commands.AddClips(target, added))
            unnamed = sum(1 for r in added if not r.clip.title_text)
            message = f"Imported {len(added)} clippings from {len(files)} file(s)."
            if unnamed:
                message += f" {unnamed} still need a name."
            # The count of unnamed clippings is already in the message, which
            # is the part anybody acts on. The reason goes on the tooltip: it is
            # there to be read when wanted, and costs the strip no width - and
            # that strip does not wrap, so a long note would push the export
            # buttons off the side of the board.
            self._flash(message, "good" if not problems else "info",
                        detail="\n\n".join(advisories))
            if target is self.model:
                self._show_list()
                row = self.model.entry_row_for_clip(added[0].id)
                if row >= 0:
                    self.list.scrollTo(self.model.index(row, 0))
            else:
                self._refresh_board()
        elif not problems:
            self._flash("Nothing to import from those files.", "info")

        # New clippings, so new chances for one to repeat another. Cheap: the
        # headlines were read as the rows were made and are just compared here.
        self.recheck_duplicates()

        if problems:
            self._report(problems)

    def _stamp_pending(self, clips: list) -> None:
        """Put freshly imported clippings into the column that asked for them.

        Anything added while the board is showing also takes the division on
        show if it has none of its own - otherwise it would appear under every
        division at once, which is what an undivided clipping does.
        """
        section = getattr(self, "_pending_section", None)
        self._pending_section = None
        on_board = self.mode == "sentiment"
        division = self.board.active if self.board.active not in ("", "__all__") else ""
        for clip in clips:
            if section is not None:
                clip.section = section
            if (section is not None or on_board) and not clip.division:
                clip.division = division

    def _clip_from_image(self, path: Path) -> Clip:
        from PIL import Image

        data = path.read_bytes()
        with Image.open(path) as image:
            width, height = image.width, image.height
        return Clip(
            source_file=str(path),
            source_ref=path.name,
            image_bytes=data,
            image_ext=path.suffix.lower(),
            native_width=width,
            native_height=height,
            section=Section.NEUTRAL,
        )

    def _add_loose(self, clips: list[Clip]) -> None:
        """Hand-added clippings share one group and land at the top, in order."""
        target = self.pool()
        self._stamp_pending(clips)
        rows = target.make_rows(clips, "clipboard", LOOSE_TITLE, LOOSE_KEY)
        at = target.loose_insert_point()
        self.stack_for(target).push(
            commands.AddClips(
                target, rows,
                f"{len(rows)} clippings added" if len(rows) != 1 else "Clipping added",
                at=at,
            )
        )
        if target is not self.model:
            self._refresh_board()
            # Name the column. A paste that lands silently gives nobody anything
            # to check against, so "it went to the wrong one" and "it went where
            # I asked" look identical until the board is scrolled.
            where = {r.clip.section.value for r in rows}
            into = f" into {', '.join(sorted(where))}" if where else ""
            self._flash(
                f"Added {len(rows)} clipping{'s' if len(rows) != 1 else ''}"
                f"{into}. Type the headline and press Enter.",
                "good",
            )
            first = rows[0].id
            self.raise_()
            self.activateWindow()
            QTimer.singleShot(80, lambda: self.board.begin_rename(first))
            return

        self._show_list()
        self._flash(
            f"Added {len(rows)} clipping{'s' if len(rows) != 1 else ''} at the top. "
            f"Type the headline and press Enter.",
            "good",
        )
        first = rows[0].id
        # After a drag out of a browser the window is often not the active one,
        # so an editor opened now would never really hold the keyboard.
        self.raise_()
        self.activateWindow()
        self.list.setFocus()
        QTimer.singleShot(80, lambda: self._begin_rename(first))

    def _begin_rename(self, clip_id: int) -> None:
        """Open the headline box on a newly added clipping, and mean it.

        A single attempt is not reliable straight after a drop: the list may
        still be laying out, and the window may only just have become active.
        """
        self.activateWindow()
        self.list.open_editor_for(clip_id)
        if self.list.editing_id() != clip_id:
            QTimer.singleShot(140, lambda: self.list.open_editor_for(clip_id))

    def _clip_from_bytes(self, data: bytes, name: str) -> Clip:
        from PIL import Image
        import io as _io

        with Image.open(_io.BytesIO(data)) as image:
            width, height = image.width, image.height
            fmt = (image.format or "PNG").lower()
        suffix = dropped.sniff(data) or {"jpeg": ".jpg"}.get(fmt, f".{fmt}")
        return Clip(
            source_file="clipboard",
            source_ref=name,
            image_bytes=data,
            image_ext=suffix,
            native_width=width,
            native_height=height,
            section=Section.NEUTRAL,
        )

    def accept_payload(self, mime) -> bool:
        """Take whatever a drop or a paste carried. Returns True if anything landed."""
        payload = dropped.read(mime)
        if payload.files:
            self.import_paths(payload.files)
        if payload.images:
            self._add_loose(
                [self._clip_from_bytes(data, name) for data, name in payload.images]
            )
        if payload.empty:
            QMessageBox.information(self, "Nothing to add", payload.note)
            return False
        return True

    def paste_clipboard(self) -> None:
        """Ctrl+V straight out of WhatsApp Web.

        On the board it lands where you are looking: the column under the
        pointer, or the one being focused on if the pointer is somewhere else.
        It used to land wherever the last drag happened to leave things, which
        is not something a person can see, so a paste went somewhere they had
        not chosen and had to be dragged back.
        """
        section = None
        if self.mode == "sentiment":
            # A pair, not a QPoint: _section_under indexes what it is given,
            # and a QPoint is not subscriptable - the mistake would have been
            # swallowed by its own except and quietly answered "no column".
            where = QCursor.pos()
            section = self._section_under((where.x(), where.y()))
            if section is None and getattr(self.board, "focused", None):
                try:
                    section = Section(self.board.focused)
                except ValueError:
                    section = None
        self._pending_section = section
        try:
            self.accept_payload(QGuiApplication.clipboard().mimeData())
        finally:
            # Nothing on the clipboard means nothing was stamped, and a column
            # left set here is exactly how the next paste went astray.
            self._pending_section = None

    # ------------------------------------------------------------ drag/drop
    @staticmethod
    def _looks_droppable(mime) -> bool:
        return (
            mime.hasUrls() or mime.hasImage() or mime.hasHtml()
            or mime.hasFormat(dropped.FILE_CONTENTS)
        )

    def dragEnterEvent(self, event):
        if self._looks_droppable(event.mimeData()):
            self.drop.setProperty("hot", True)
            self.drop.style().unpolish(self.drop)
            self.drop.style().polish(self.drop)
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self._looks_droppable(event.mimeData()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.drop.setProperty("hot", False)
        self.drop.style().unpolish(self.drop)
        self.drop.style().polish(self.drop)

    def dropEvent(self, event):
        self.dragLeaveEvent(event)
        event.acceptProposedAction()
        self.accept_payload(event.mimeData())

    # ------------------------------------------------------------- actions
    def _on_clip_action(self, name: str, clip_id: int) -> None:
        model = self.model
        if name == "delete":
            self.undo_stack.push(commands.RemoveClips(model, [clip_id]))
            self._flash("Clipping deleted — Ctrl+Z brings it back.", "info")
        elif name == "rotate":
            self.undo_stack.push(commands.Rotate(model, [clip_id]))
        elif name == "split":
            self.undo_stack.push(commands.Split(model, clip_id))
            self._flash("Split in two — Ctrl+Z undoes it.", "info")
        elif name == "merge":
            position = model.position_of(clip_id)
            if position < 0 or position + 1 >= len(model.rows):
                return
            below = model.rows[position + 1].id
            self.undo_stack.push(commands.Merge(model, [clip_id, below]))
        elif name == "add_title":
            row = model.entry_row_for_clip(clip_id)
            if row >= 0:
                self.list.edit_field(row, "label")
        elif name in ("edit_url", "add_url"):
            # Reachable even on a card with no address box showing, which is
            # every freshly pasted screenshot - otherwise there is nowhere to
            # put the link the story came from.
            row = model.entry_row_for_clip(clip_id)
            if row >= 0:
                self.list.edit_field(row, "url")
        elif name in ("move_top", "move_up", "move_down", "move_bottom"):
            if self._lens_holds(model):
                return
            where = name.replace("move_", "")
            rows = commands.move_relative(model, [clip_id], where)
            self.undo_stack.push(commands.Reorder(model, rows, "Clipping reordered"))

    def _on_group_action(self, name: str, ident: str) -> None:
        """Act on the one run of clippings under the header that was clicked.

        Addressing by key alone would sweep up a second run elsewhere in the list
        that happens to share it, which a re-filing drop can easily create.
        """
        model = self.model
        group = model.group_by_ident(ident)
        ids = group.row_ids if group else []
        # Clicking the file name is the same as clicking its chevron - it is
        # the obvious target, and it was doing nothing at all.
        if name == "group_title":
            name = "group_collapse"
        if not ids and name != "group_collapse":
            return

        if name == "group_collapse":
            model.toggle_group_collapsed(ident)
        elif name == "group_check":
            all_selected = all(model.is_selected(i) for i in ids)
            model.set_selected(ids, not all_selected)
        elif name == "group_rotate":
            self.undo_stack.push(commands.Rotate(model, ids))
        elif name == "group_delete":
            if self._confirm_delete(len(ids)):
                self.undo_stack.push(commands.RemoveClips(model, ids))
        elif name in ("group_top", "group_up", "group_down", "group_bottom"):
            # Never under a lens. move_group_relative matches a file by its
            # clippings being one unbroken run; hide one of them and the match
            # fails, and it quietly degrades to nudging a single row - the exact
            # twenty-clicks-for-one bug its own comment records was fixed.
            if self._lens_holds(model):
                return
            rows = commands.move_group_relative(
                model, ids, name.replace("group_", ""))
            self.undo_stack.push(commands.Reorder(model, rows, "File reordered"))

    def _on_label_edited(self, clip_id: int, text: str) -> None:
        """The headline, which prints above the picture.

        The card has a box for this and a box for the address, so neither has to
        guess at the other from what was typed. That guessing is what made a
        half-typed address - "https:/", before the second slash - land as a
        headline for as long as it took to type the next character.
        """
        clip = self.model.by_id(clip_id)

        # A web address typed into the headline box is an address, whatever box
        # it was typed into. Screenshots arrive with no caption and no link, so
        # the card shows only the headline box - and that is where somebody
        # pasting the story's address will put it. Left as a headline it prints
        # above the picture as if it were the story's title, and the real link
        # prints underneath as well: the same address twice on the page.
        typed = (text or "").strip()
        if typed and looks_like_url(typed):
            if typed != clip.url.strip():
                self.undo_stack.push(commands.EditUrl(self.model, clip_id, typed))
                self._flash("That looks like a web address, so it has gone in "
                            "the link box — it prints under the picture.", "info")
            if clip.label.strip():
                # and it must not stay in the headline as well
                self.undo_stack.push(commands.EditLabel(self.model, clip_id, ""))
            # The boxes follow the text. Opening the headline box on an unnamed
            # clipping had switched that box on, and nothing switched it off
            # when what was typed into it turned out to be an address - so the
            # card was left with an empty headline box above the link, for no
            # reason anybody could see. Put away the box that was emptied and
            # show the one that was filled.
            if not clip.effective_label.strip():
                clip.show_title_box = False
            clip.show_url_box = True
            self.model.refresh_clip(clip_id)
            self.list.refresh_height()
            return

        if text == clip.effective_label:
            return
        self.undo_stack.push(commands.EditLabel(self.model, clip_id, text))

    def _on_url_edited(self, clip_id: int, text: str) -> None:
        """The address, which prints under the picture as a working link."""
        clip = self.model.by_id(clip_id)
        if text.strip() == clip.url.strip():
            return
        self.undo_stack.push(
            commands.EditUrl(self.model, clip_id, text.strip()))

    def _on_reorder(self, ids: list[int], target: int) -> None:
        rows = commands.move_to(self.model, ids, target)
        self.undo_stack.push(
            commands.Reorder(
                self.model, rows,
                f"{len(ids)} clippings reordered" if len(ids) > 1
                else "Clipping reordered",
            )
        )
        self._flash("Moved — Ctrl+Z puts it back.", "info")

    def _on_selection_toggled(self, clip_id: int, additive: bool, ranged: bool) -> None:
        model = self.model
        if ranged and self._last_clicked_id is not None:
            model.select_range(self._last_clicked_id, clip_id)
        elif additive:
            model.set_selected([clip_id], not model.is_selected(clip_id))
        else:
            model.select_only([clip_id])
        self._last_clicked_id = clip_id

    # -------------------------------------------------------------- batch
    def _selected_ids(self) -> list[int]:
        return [r.id for r in self.model.rows if r.id in self.model.selected]

    def _lens_holds(self, model=None) -> bool:
        """True when a filter or an arrangement is on, so nothing may be moved.

        Said out loud rather than silently ignored: a button that does nothing
        and explains nothing is worse than a button that is not there.
        """
        model = model if model is not None else self.model
        lens = getattr(model, "lens", None)
        if lens is None or not lens.busy:
            return False
        self._flash("Clear the filter before moving clippings — while one is on, "
                    "what you see is not the order they are really in.", "bad")
        return True

    def _batch_move(self, where: str) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        if self._lens_holds(self.model):
            return
        rows = commands.move_relative(self.model, ids, where)
        self.undo_stack.push(
            commands.Reorder(self.model, rows, f"{len(ids)} clippings moved")
        )

    def _batch_rotate(self) -> None:
        ids = self._selected_ids()
        if ids:
            self.undo_stack.push(commands.Rotate(self.model, ids))

    def _batch_exclude(self) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        want = not all(self.model.by_id(i).include for i in ids)
        self.undo_stack.push(commands.SetIncluded(self.model, ids, want))

    def _batch_delete(self) -> None:
        if self.mode != "standard":
            return          # the batch bar belongs to the press report
        ids = self._selected_ids()
        if not ids:
            return
        if self._confirm_delete(len(ids)):
            self.undo_stack.push(commands.RemoveClips(self.model, ids))
            self._flash(f"{len(ids)} deleted — Ctrl+Z brings them back.", "info")

    def _merge_selected(self) -> None:
        ids = self._selected_ids()
        if len(ids) < 2:
            self._flash("Pick at least two clippings to merge.", "info")
            return
        self.undo_stack.push(commands.Merge(self.model, ids))
        self._flash(f"{len(ids)} merged into one — Ctrl+Z undoes it.", "good")

    def _bulk_field(self, field: str) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        options = (
            self.name_index.newspaper_names if field == "newspaper"
            else self.name_index.edition_names
        )
        current = getattr(self.model.by_id(ids[0]), field)
        value, ok = QInputDialog.getItem(
            self, f"Set {field}", f"{field.title()} for {len(ids)} clipping(s):",
            options, options.index(current) if current in options else 0, True,
        )
        if not ok:
            return
        value = value.strip()
        if field == "newspaper":
            self.name_index.add_newspaper(value)
        else:
            self.name_index.add_edition(value)
        self.undo_stack.push(
            commands.SetFieldOnMany(self.model, ids, field, value)
        )

    def _select_all(self) -> None:
        if self.mode != "standard":
            return          # the batch bar belongs to the press report
        # Everything ON SCREEN. With a filter on, "all" cannot mean the
        # clippings it is hiding: somebody who has narrowed the list to the
        # regional papers, pressed this and then pressed Delete would lose the
        # whole morning, and there would have been nothing on screen to warn
        # them. So it selects what they can see, and says how many that was.
        shown = self.model.visible_rows()
        self.model.select_only([r.id for r in shown])
        if self.model.lens.busy:
            self._flash(f"Selected the {len(shown)} clipping(s) on screen. "
                        f"The other {len(self.model.rows) - len(shown)} are "
                        f"hidden by the filter and were not touched.", "info")

    def _toggle_select_all(self) -> None:
        if self.mode != "standard":
            return          # the batch bar belongs to the press report
        shown = self.model.visible_rows()
        if shown and len(self.model.selected) == len(shown):
            self.model.clear_selection()
        else:
            self._select_all()

    def _clear_all(self) -> None:
        """Clear the interface on show, not always the press report."""
        target = self.pool()
        if not target.rows:
            return
        if self._confirm_delete(len(target.rows), everything=True):
            self.stack_for(target).push(
                commands.RemoveClips(
                    target, [r.id for r in target.rows], "All clippings cleared"
                )
            )

    def _confirm_delete(self, count: int, everything: bool = False) -> bool:
        answer = QMessageBox.question(
            self,
            "Delete clippings?" if not everything else "Clear everything?",
            f"{count} clipping(s) will be removed from the list.\n"
            f"Ctrl+Z brings them back.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        return answer == QMessageBox.Yes

    # ------------------------------------------------------------- preview
    def _preview_pool(self):
        """Whichever pool the open preview belongs to."""
        return getattr(self, "preview_model", None) or self.model

    def open_preview(self, clip_id: int) -> None:
        # Opened from the list and from a board card, so the id could belong to
        # either pool.
        model = self.pool_for(clip_id)
        if model is None:
            return
        self.preview_model = model
        row = model.row_for(clip_id)
        if row is None:
            return
        if self.preview is None:
            self.preview = PreviewDialog(model, self)
            self.preview.fieldChanged.connect(self._preview_field)
            self.preview.headingPicked.connect(self._preview_heading)
            self.preview.headingListChanged.connect(self._headings_changed)
            self.preview.headingStyleChanged.connect(self._headings_changed)
            self.preview.labelChanged.connect(self._on_label_edited)
            self.preview.excludeRequested.connect(self._preview_include)
            self.preview.deleteRequested.connect(self._preview_delete)
            self.preview.rotateRequested.connect(self._preview_rotate)
            self.preview.splitRequested.connect(self._preview_split)
            self.preview.navigate.connect(self._preview_navigate)
        # Set before the row is shown: it decides whether the Section control
        # is the heading picker or the board's sentiment control, and showing
        # the row is what reads it.
        self.preview.for_board = model is getattr(self, "board_model", None)
        position = model.position_of(clip_id) + 1
        self.preview.show_row(row, position, len(model.rows))
        self.preview.show()
        self.preview.raise_()
        self.preview.activateWindow()

    def _refresh_preview(self, clip_id: int) -> None:
        row = self._preview_pool().row_for(clip_id)
        if self.preview and self.preview.isVisible() and row is not None:
            self.preview.show_row(
                row,
                self._preview_pool().position_of(clip_id) + 1,
                len(self._preview_pool().rows),
            )

    def _preview_heading(self, clip_id: int, key: str, words: str) -> None:
        """A heading was chosen for one clipping in the press report preview.

        The key and the words go on together, under ONE undo step. Written
        apart, a session saved between the two carries half a heading, and
        Ctrl+Z takes back half of what was one action to the person who did it.
        """
        pool = self._preview_pool()
        clip = pool.by_id(clip_id)
        if clip is None:
            return
        if (getattr(clip, "section_key", "") == key
                and clip.section_title == words):
            return
        self.undo_stack.beginMacro("Section heading")
        self.undo_stack.push(
            commands.EditField(pool, clip_id, "section_key", key))
        self.undo_stack.push(
            commands.EditField(pool, clip_id, "section_title", words))
        self.undo_stack.endMacro()
        # The card chip and the report have to agree about which clipping opens
        # which section, and both read the same recomputed map.
        pool.recompute_openers()
        self._refresh_preview(clip_id)

    def _headings_changed(self) -> None:
        """The list of headings, or how they are printed, was changed."""
        for pool in (self.model, getattr(self, "board_model", None)):
            if pool is not None:
                pool.recompute_openers()
        # The card chip promises which clipping opens which section, and it
        # reads the same recomputed map the report does - so a heading added,
        # removed or restyled has to reach both or the card starts promising a
        # heading the report will not print.
        self.list.viewport().update()

    def _preview_field(self, clip_id: int, field: str, value) -> None:
        if field == "section":
            try:
                value = Section(value)
            except ValueError:
                return
        elif field == "newspaper" and value:
            self.name_index.add_newspaper(value)
        elif field == "edition" and value:
            self.name_index.add_edition(value)
        if getattr(self._preview_pool().by_id(clip_id), field) == value:
            return
        self.undo_stack.push(commands.EditField(self._preview_pool(), clip_id, field, value))

    def _preview_include(self, clip_id: int, included: bool) -> None:
        self.undo_stack.push(commands.SetIncluded(self._preview_pool(), [clip_id], included))
        self._refresh_preview(clip_id)

    def _preview_delete(self, clip_id: int) -> None:
        if not self._confirm_delete(1):
            return
        position = self._preview_pool().position_of(clip_id)
        self.undo_stack.push(commands.RemoveClips(self._preview_pool(), [clip_id]))
        if self._preview_pool().rows:
            following = self._preview_pool().rows[min(position, len(self._preview_pool().rows) - 1)]
            self._refresh_preview(following.id)
        elif self.preview:
            self.preview.close()

    def _preview_rotate(self, clip_id: int) -> None:
        self.undo_stack.push(commands.Rotate(self._preview_pool(), [clip_id]))
        self._refresh_preview(clip_id)

    def _preview_split(self, clip_id: int) -> None:
        position = self._preview_pool().position_of(clip_id)
        self.undo_stack.push(commands.Split(self._preview_pool(), clip_id))
        if 0 <= position < len(self._preview_pool().rows):
            self._refresh_preview(self._preview_pool().rows[position].id)

    def _preview_navigate(self, step: int) -> None:
        if self.preview is None or self.preview.row is None:
            return
        position = self._preview_pool().position_of(self.preview.row.id) + step
        if 0 <= position < len(self._preview_pool().rows):
            self._refresh_preview(self._preview_pool().rows[position].id)

    # ------------------------------------------------------- context menu
    def _send_to_board(self, clip_ids: list) -> None:
        """Move clippings from the press report over to the sentiment board."""
        ids = [i for i in clip_ids if self.model.row_for(i) is not None]
        if not ids:
            return
        self.undo_stack.push(
            commands.MoveToInterface(
                self.model, self.board_model, ids,
                f"{len(ids)} sent to the sentiment board" if len(ids) != 1
                else "Clipping sent to the sentiment board",
            )
        )
        self._refresh_board()
        self._update_counts()
        self._flash(
            f"Moved {len(ids)} clipping{'s' if len(ids) != 1 else ''} to the "
            f"sentiment board. Ctrl+Z brings {'them' if len(ids) != 1 else 'it'} "
            f"back.",
            "good",
        )

    def _context_menu(self, point: QPoint) -> None:
        index = self.list.indexAt(point)
        if not index.isValid():
            return
        entry = index.data(Qt.UserRole)
        if entry is None or entry.row is None:
            return
        clip_id = entry.row.id
        ids = self._selected_ids() or [clip_id]
        many = len(ids) > 1
        clip = self.model.by_id(ids[0])

        menu = QMenu(self)
        menu.addAction(QAction("Open full size", self,
                               triggered=lambda: self.open_preview(clip_id)))
        menu.addSeparator()
        # The two interfaces keep separate clippings, so there has to be a way
        # to hand one over without importing it twice.
        send = (f"Send these {len(ids)} to the sentiment board" if many
                else "Send to the sentiment board")
        menu.addAction(QAction(send, self,
                               triggered=lambda: self._send_to_board(ids)))
        menu.addSeparator()
        label = (f"Exclude these {len(ids)}" if many
                 else ("Exclude" if clip.include else "Include again"))
        menu.addAction(QAction(label, self, triggered=lambda: self.undo_stack.push(
            commands.SetIncluded(self.model, ids, many or not clip.include))))
        menu.addAction(QAction("Set newspaper…", self,
                               triggered=lambda: self._bulk_field("newspaper")))
        menu.addAction(QAction("Set edition…", self,
                               triggered=lambda: self._bulk_field("edition")))
        menu.addSeparator()
        if many:
            menu.addAction(QAction(f"Merge these {len(ids)} into one", self,
                                   triggered=self._merge_selected))
        menu.addAction(QAction("Split in two", self,
                               triggered=lambda: self._on_clip_action("split", clip_id)))
        menu.addAction(QAction("Rotate 90°", self,
                               triggered=lambda: self._on_clip_action("rotate", clip_id)))
        menu.addSeparator()
        menu.addAction(QAction(f"Delete {len(ids)} clippings" if many
                               else "Delete clipping", self,
                               triggered=self._batch_delete if many
                               else lambda: self._on_clip_action("delete", clip_id)))
        menu.exec(self.list.viewport().mapToGlobal(point))

    # -------------------------------------------------------------- chrome
    def _show_list(self) -> None:
        self.empty.hide()
        self.list.show()
        self.select_bar.show()
        for button in self.floaters:
            button.setVisible(self.pool().clip_count > 0)
        self._place_floating()

    # ---------------------------------------------------------------- modes
    def _mode_picked(self, index: int) -> None:
        self.set_mode(index or "standard")

    def set_mode(self, mode: str) -> None:
        """Swap between the press report and the sentiment board."""
        self.mode = mode if mode in ("standard", "sentiment") else "standard"
        sentiment_mode = self.mode == "sentiment"
        self.pages.setCurrentIndex(1 if sentiment_mode else 0)

        self.mode_switch.set_mode(self.mode)

        # The export footer is the press report's. The floating controls are not -
        # both interfaces scroll and both have a history to walk back.
        self.footer.setVisible(not sentiment_mode)
        self.stack(self.mode).setActive(True)
        for button in self.floaters:
            button.setVisible(self.pool().clip_count > 0)
        self._place_floating()
        if sentiment_mode:
            self.batch.hide()
            self._refresh_board()
        else:
            self._update_selection_ui()

        self.mode_badge.setText(
            "Division sentiment" if sentiment_mode else "Daily newspad"
        )
        self.tagline.setText(
            "Sorts each division's coverage into positive, neutral, negative and "
            "digital."
            if sentiment_mode else
            "Reads the division documents, works out the newspaper, and builds "
            "the newspad."
        )

    def _refresh_board(self) -> None:
        self.board.set_rows(self.board_model.rows)
        self.board.set_selection(self.board_model.selected)

    def _on_board_title(self, clip_id: int, text: str) -> None:
        """A headline typed straight onto a card.

        Which strip it came from is settled before this: a card carries both, and
        the column only decides which one it leads with. Working that out here
        from the section was what made the digital column a special case - and
        meant a headline typed on a digital card was filed as its address.
        """
        row = self.board_model.row_for(clip_id)
        if row is None or text == row.clip.effective_label:
            return
        self.board_undo.push(
            commands.EditLabel(self.board_model, clip_id, text))
        self._refresh_board()

    def _on_board_url(self, clip_id: int, text: str) -> None:
        """A web address typed straight onto a card."""
        row = self.board_model.row_for(clip_id)
        if row is None or text.strip() == (row.clip.url or "").strip():
            return
        self.board_undo.push(
            commands.EditUrl(self.board_model, clip_id, text.strip()))
        self._refresh_board()

    def _on_board_delete(self, clip_id: int) -> None:
        if self.board_model.row_for(clip_id) is None:
            return
        if self._confirm_delete(1):
            self.board_undo.push(
                commands.RemoveClips(self.board_model, [clip_id])
            )
            self._refresh_board()
            self._flash("Clipping deleted — Ctrl+Z brings it back.", "info")

    def _on_board_rotate(self, clip_id: int) -> None:
        if self.board_model.row_for(clip_id) is None:
            return
        self.board_undo.push(commands.Rotate(self.board_model, [clip_id]))
        self._refresh_board()

    def _assign_sentiment(self, clip_ids: list, section_value: str) -> None:
        """A card dragged into another column changes its category."""
        try:
            section = Section(section_value)
        except ValueError:
            return
        moving = [i for i in clip_ids if self.board_model.by_id(i).section != section]
        if not moving:
            return
        self.board_undo.push(
            commands.SetFieldOnMany(self.board_model, moving, "section", section)
        )
        # a clipping filed under a division stays with it; an unassigned one adopts
        # whichever division is being worked on
        if self.board.active and self.board.active != "__all__":
            unassigned = [i for i in moving if not self.board_model.by_id(i).division]
            if unassigned:
                self.board_undo.push(
                    commands.SetFieldOnMany(
                        self.board_model, unassigned, "division", self.board.active
                    )
                )
        style = theme.SENTIMENT_STYLES[section.value]
        self._flash(
            f"Moved {len(moving)} clipping"
            + ("s" if len(moving) != 1 else "")
            + f" into {style['label']}.",
            "good",
        )

    def _add_into_section(self, section_value: str) -> None:
        """The Add button on a column: import straight into that category.

        Word and PDF as well as photos - the column's own hint promises all
        three, and now that the board keeps its own clippings it can no longer
        borrow them from an import done on the report side.
        """
        try:
            self._pending_section = Section(section_value)
        except ValueError:
            self._pending_section = None
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose clippings for this column", "",
            "Clippings (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff "
            "*.docx *.pdf)",
        )
        if paths:
            self.import_paths([Path(p) for p in paths])
        self._pending_section = None

    def accept_payload_into(self, mime, section) -> None:
        """A file or image dropped onto one of the four columns."""
        self._pending_section = section
        try:
            self.accept_payload(mime)
        finally:
            self._pending_section = None

    def _update_counts(self) -> None:
        self._sync_fold_buttons()
        total = self.model.clip_count
        included = self.model.included_count
        self.count_pill.setText(f"{total} clip" + ("s" if total != 1 else ""))
        self.cover.set_count(included)
        self.ready.setText(
            f"<b>{included}</b> clipping{'s' if included != 1 else ''} ready for export"
        )
        self.btn_pdf_out.setEnabled(included > 0)
        self.btn_docx_out.setEnabled(included > 0)
        self.clear_all_btn.setVisible(total > 0)
        if getattr(self, "board", None) is not None:
            self.board.set_rows(self.board_model.rows)
            # Each entry counts its OWN interface: they hold separate
            # clippings now, and labelling both with one total said the board
            # had three when it had none.
            self.mode_switch.set_counts(total, self.board_model.clip_count)
        if total == 0:
            self.list.hide()
            self.empty.show()
            self.select_bar.hide()
            self.batch.hide()
        if self.mode == "sentiment":
            self.footer.hide()
        for button in self.floaters:
            button.setVisible(self.pool().clip_count > 0)
        self._place_floating()
        self._update_selection_ui()

    def _update_selection_ui(self) -> None:
        if getattr(self, "board", None) is not None:
            self.board.set_selection(self.board_model.selected)
        count = len(self.model.selected)
        self.batch_count.setText(str(count))
        self.clear_selection_btn.setVisible(count > 0)
        self.batch_merge.setVisible(count >= 2)
        self.select_all_btn.setText(
            "Deselect all"
            if count and count == self.model.clip_count
            else "Select all"
        )
        if count:
            self.select_hint.setText(
                f"{count} selected — use the bar below, or drag any one of them "
                f"to move the block"
            )
            self.batch.adjustSize()
            self.batch.show()
            self.batch.raise_()
            self._place_floating()
        else:
            self.select_hint.setText(
                "Hold Ctrl to pick several, Shift for a run, or drag the handle to "
                "move a block anywhere"
            )
            self.batch.hide()

    def _after_undo_change(self) -> None:
        text = self.undo_stack.undoText()
        if text:
            self.float_undo.setToolTip(f"Undo {text} (Ctrl+Z)")
        # Undoing a deletion can put a clipping back that something else was a
        # repeat of, so the whole question has to be asked again.
        self.recheck_duplicates()

    def _toggle_card(self) -> None:
        collapsed = self.drop.isVisible()
        self.drop.setVisible(not collapsed)
        self.collapse_btn.setText("Expand" if collapsed else "Collapse")

    def _flash(self, message: str, kind: str = "info",
               detail: str = "") -> None:
        # The report's status line lives inside its import card, which is not on
        # screen in sentiment mode - without this an import done on the board is
        # completely silent, successes and failures alike.
        if self.mode == "sentiment" and getattr(self.board, "status", None):
            self.board.status.setText(message)
            self.board.status.setToolTip(detail)
            self.board.status.show()
            QTimer.singleShot(9000, self.board.status.hide)
            return
        self.status.setObjectName(
            {"info": "StatusInfo", "good": "StatusGood", "bad": "StatusBad"}[kind]
        )
        self.status.setStyleSheet("")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.setText(message)
        self.status.setToolTip(detail)
        self.status.show()
        QTimer.singleShot(9000, self.status.hide)

    def _report(self, problems: list[str]) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Some things could not be imported")
        box.setText(
            f"{len(problems)} problem(s). Everything else was imported normally."
        )
        box.setDetailedText("\n\n".join(problems))
        box.exec()

    def _export(self, prefer: str) -> None:
        """Build the newspad from the included clippings, in the order shown."""
        from .export_dialog import ExportDialog

        clips = [r.clip for r in self.model.rows if r.clip.include]
        if not clips:
            self._flash("Nothing is ticked to export.", "bad")
            return

        # Before the cover is drawn, not after: the date is painted into the
        # cover picture, so finding out at the last moment would mean the
        # preview and the file had already been made with the wrong day on them.
        if not datefield.refuse_future(self, self.cover.report_date(), "newspad"):
            return

        # Delhi and Lucknow print the masthead into the picture, so those pages are
        # meant to go out with no caption above them. Only ask about the rest.
        unnamed = sum(
            1 for c in clips if not c.title_text and not c.title_in_image
        )
        if unnamed:
            answer = QMessageBox.question(
                self, "Some clippings have no headline",
                f"{unnamed} of the {len(clips)} clippings have no headline, so "
                f"their pages will carry the image with no caption above it.\n\n"
                f"Build anyway?",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return

        # The cover card renders whichever template is chosen to one finished
        # picture, so the PDF cover and the Word cover are the same pixels.
        built = self.cover.rendered_cover(len(clips))
        dialog = ExportDialog(
            clips, self, prefer=prefer,
            report_date=self.cover.report_date(),
            cover_image=built or self.cover.cover_image(),
            heading="" if built else self.cover.heading(),
            cover_baked=bool(built),
            layout_style=self.heading.settings(),
            cover_blocks=self.cover.cover_blocks(),
        )
        if dialog.exec() and dialog.results:
            names = ", ".join(Path(p).name for p in dialog.results)
            self._flash(f"Built {names}.", "good")
            # The brief: undo history clears on export, not on import.
            self.undo_stack.clear()   # the report's history only

    def _division_tag(self) -> str:
        """How a division is written on a file: "Lucknow(LKO)".

        Both sentiment exports carry it, and they have to agree - a folder of
        pictures and the report they came from are filed next to each other.
        """
        division = self.board.active_division()
        if division is None:
            return "All Divisions"
        return f"{division.name}({division.code})"

    def _export_jpegs(self, clips: list, where: str, stamp) -> None:
        """One picture per clipping, with the masthead burned in.

        A folder rather than a file: these go out one at a time on WhatsApp, and
        each carries its own newspaper name and date in the file name so it can be
        found again after it has been forwarded twice.
        """
        from ..export import build_jpeg
        from ..export import layout as export_layout

        # The same panel the dossier's PDF and Word use, so a clipping sent as a
        # picture is titled exactly like the same clipping printed in the report.
        style = export_layout.HeadingStyle.from_settings(
            self.board.heading.settings())

        chosen = QFileDialog.getExistingDirectory(
            self, "Where should the JPEGs go?", str(Path.home() / "Documents"),
        )
        if not chosen:
            return

        folder = Path(chosen) / build_jpeg.folder_name(self._division_tag(), stamp)
        progress = QProgressDialog(
            "Writing the pictures…", "Stop", 0, len(clips), self)
        progress.setWindowTitle("Exporting JPEGs")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(300)

        def tick(number: int, total: int, _label: str) -> None:
            progress.setMaximum(total)
            progress.setValue(number)
            QApplication.processEvents()

        try:
            result = build_jpeg.build(clips, folder, stamp, tick, heading=style)
        except Exception as exc:  # noqa: BLE001 - never show a raw traceback
            progress.close()
            QMessageBox.warning(
                self, "The pictures could not be written",
                f"{type(exc).__name__}: {exc}\n\n"
                f"Nothing was lost — your clippings are still on the board.",
            )
            return
        progress.setValue(len(clips))

        if not result.count:
            self._flash("No pictures could be written.", "bad")
            return
        note = f"Wrote {result.count} JPEG{'s' if result.count != 1 else ''} to "
        note += folder.name + "."
        if result.warnings:
            note += f" {len(result.warnings)} could not be written."
        self._flash(note, "good" if not result.warnings else "info")
        self._reveal(folder)

    def _reveal(self, folder: Path) -> None:
        """Open the folder, so the pictures can be picked up straight away."""
        try:
            os.startfile(str(folder))  # noqa: S606 - Windows shell open
        except Exception:  # noqa: BLE001 - the files are written either way
            pass

    def _clear_division(self, code: str) -> None:
        """Take every clipping the board is showing off it.

        A morning is compiled one division at a time, and starting the next one
        meant selecting a screenful by hand and deleting them. It asks first,
        and it goes on the undo stack like every other deletion, so a mistaken
        press is one Ctrl+Z rather than a re-import.
        """
        showing = self.board.visible_clips()
        if not showing:
            self._flash("There is nothing on the board to clear.", "info")
            return
        wanted = {clip.uid for clip in showing}
        ids = [row.id for row in self.board_model.rows
               if row.clip is not None and row.clip.uid in wanted]
        if not ids:
            return
        where = code if code and code != "ALL" else "the board"
        answer = QMessageBox.question(
            self, "Clear this division",
            f"Remove {len(ids)} clipping(s) from {where}?"
            + chr(10) + chr(10) + "Ctrl+Z brings them back.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        # The board keeps its own undo history, separate from the report's.
        self.stack_for(self.board_model).push(commands.RemoveClips(
            self.board_model, ids, f"{len(ids)} clipping(s) cleared"))
        self._refresh_board()
        self.recheck_duplicates()
        self._flash(f"Cleared {len(ids)} clipping(s) — Ctrl+Z brings them back.",
                    "info")

    def _export_dossier(self, kind: str) -> None:
        """Build the sentiment dossier for the division the board is showing.

        The board's own Download buttons come here rather than to the newspad
        dialog: a dossier is one division, grouped by sentiment, and it takes its
        settings from the report layout panel instead of the cover card.
        """
        from ..export import build_sentiment
        from ..export import layout as export_layout

        clips = [c for c in self.board.visible_clips() if c.include]
        if not clips:
            self._flash("There is nothing on the board to export.", "bad")
            return

        division = self.board.active_division()
        stamp = self.cover.report_date()
        # The strict rule, on the way out. The fields refuse a future date as it
        # is typed; this catches one that arrived any other way - a session saved
        # on another day, or a clock that was wrong and has since been put right.
        #
        # BOTH dates, because they are two different dates. The stamp above dates
        # the file; the dossier's own cover carries its own, set on the board's
        # cover card, and checking only the first one left the second unchecked
        # on every route out - PDF, Word, burned and pictures alike.
        if not datefield.refuse_future(self, stamp, "dossier"):
            return
        if not self.board.cover.date_is_sound(self):
            return
        where = division.code if division else "ALL"

        if kind == "jpeg":
            self._export_jpegs(clips, where, stamp)
            return

        # The burned report is the same document with the words drawn into the
        # pictures, so it is named apart from the ordinary one - they are two
        # different things to send and the file names have to say which is which.
        burned = kind == "burned"
        suffix = "docx" if kind == "docx" else "pdf"
        tail = " (burned headlines)" if burned else ""
        stem = (f"News Coverage - {self._division_tag()} - "
                f"{stamp.strftime('%d.%m.%Y')}{tail}")

        open_after = False
        if burned:
            # This one is wanted as a PDF to send AND a Word file to edit, from
            # the same click and under the same name. A Save box offers one file
            # and one extension, so it cannot ask that - and burning the words
            # into the pictures is the slow part, worth doing once for both.
            from .burned_dialog import BurnedReportDialog

            ask = BurnedReportDialog(self, suggested=stem, clippings=len(clips))
            if ask.exec() != QDialog.Accepted:
                return
            targets = ask.targets()
            open_after = ask.opens_after()
        else:
            target, _ = QFileDialog.getSaveFileName(
                self, "Save the sentiment dossier",
                str(Path.home() / "Documents" / f"{stem}.{suffix}"),
                f"{suffix.upper()} (*.{suffix})",
            )
            if not target:
                return
            targets = [(suffix, Path(target))]

        chosen = self.board.export_options()
        cover = self.board.cover.cover_config()
        # The card's own "Enable Cover Page" is the switch, and the only one.
        # This used to turn the cover OFF when the card was unticked but never
        # ON when it was ticked, so the decision fell through to a second box in
        # the options panel that defaults to unticked - and a person who ticked
        # the obvious switch got a dossier with no cover and nothing to explain
        # why.
        chosen["include_cover"] = bool(cover.enabled)
        # The dossier's own heading panel, which is not the press report's.
        board_style = export_layout.HeadingStyle.from_settings(
            self.board.heading.settings())
        chosen["page"] = board_style.page
        if burned:
            # The words are in the pictures now, so the report must not set them
            # again: a heading above the image and the same heading inside it is
            # the same sentence twice, an inch apart.
            chosen["include_clip_titles"] = False
        options = build_sentiment.SentimentOptions(
            **chosen, cover_config=cover if cover.enabled else None,
            heading=board_style,
        )

        burn_warnings: list = []
        if burned:
            from ..export import build_burned

            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                clips = build_burned.flatten(clips, board_style,
                                             warnings=burn_warnings)
            finally:
                QApplication.restoreOverrideCursor()

        # One burn, then every format that was ticked. A format that fails is
        # named and the others are still written - losing the Word file is no
        # reason to lose the PDF as well.
        made: list = []
        notes: list[str] = list(burn_warnings)
        failed: list[str] = []
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for fmt, path in targets:
                builder = (
                    build_sentiment.build_docx if fmt == "docx"
                    else build_sentiment.build_pdf
                )
                try:
                    result = builder(clips, path, division, stamp, options)
                except Exception as exc:  # noqa: BLE001 - never a raw traceback
                    failed.append(f"{path.name}: {type(exc).__name__}: {exc}")
                    continue
                made.append(result)
                notes.extend(result.warnings)
        finally:
            QApplication.restoreOverrideCursor()

        if failed:
            QMessageBox.warning(
                self,
                "The dossier could not be built" if not made
                else "One of the files could not be built",
                "\n\n".join(failed) + "\n\nNothing was lost — your clippings "
                "are still on the board.",
            )
        if not made:
            return

        names = ", ".join(Path(r.path).name for r in made)
        note = f"Built {names} ({made[0].clippings} clippings)."
        if notes:
            note += f" {len(notes)} note"
            note += "s." if len(notes) != 1 else "."
        self._flash(note, "good")

        if open_after:
            from .burned_dialog import BurnedReportDialog

            BurnedReportDialog.open_file(made[0].path)

    # ------------------------------------------------------ the same twice
    def recheck_duplicates(self) -> None:
        """Ask for the duplicate check. It runs once, shortly, not now.

        This is called from everywhere the list can change, and one of those
        places is the undo stack, which stirs on every single edit - every
        headline typed, every tick, every reorder. Running the check there and
        then meant a fresh comparison of every clipping against every other,
        and a fresh reading of any that resembled one, on every keystroke's
        worth of work. From the outside the application simply never stopped
        thinking.

        So the request is collected and answered once the user has stopped
        doing things. Ten edits in a row cost one check, not ten.
        """
        if not hasattr(self, "duplicates_btn"):
            return
        if not self._auto_duplicates:
            # Switched off. The button still works, and what has already been
            # flagged stays flagged - turning the check off is not the same as
            # saying the repeats it found are not repeats.
            return
        if self._duplicate_timer is None:
            self._duplicate_timer = QTimer(self)
            self._duplicate_timer.setSingleShot(True)
            self._duplicate_timer.timeout.connect(self._run_duplicate_check)
        self._duplicate_timer.start(DUPLICATE_SETTLE_MS)

    def _run_duplicate_check(self) -> None:
        """Look over the whole list for cuttings that repeat one another.

        The slow half - reading a headline off each picture, about half a
        second each - happens on another thread. The window stays alive, and
        the answer arrives in the status strip when it is ready. Doing it here
        meant a minute of dead application immediately after an import, which
        is the moment somebody most wants to look at what they have just
        brought in.
        """
        if self._duplicates_running:
            return
        rows = [row for row in self.model.rows if row.clip is not None]
        clips = [row.clip for row in rows]
        if not clips:
            self._duplicate_pairs = []
            self.duplicates_btn.setVisible(False)
            return

        # Two passes, cheap one first. Fingerprinting a picture takes a few
        # thousandths of a second and reading a headline off it takes about half
        # of one, so everything is measured and only the clippings that already
        # LOOK like a repeat are read. On the 7 September folder that is six
        # readings instead of a hundred and fifty - which is the difference
        # between the machine being busy for half a minute after an import and
        # being busy for a moment.
        unprinted = [(c.uid, c.image_bytes) for c in clips
                     if c.image_bytes
                     and (not c.picture_hash or not c.picture_hash_lower)]
        if unprinted:
            self._duplicates_running = True
            self._reader_thread, self._reader = reader.start(
                unprinted, self._duplicate_progress, self._prints_taken, self,
                read_headlines=False)
            return
        self._read_the_shortlist()

    def _gone(self) -> bool:
        """True once this window is on its way out. Nothing may touch it then."""
        if getattr(self, "_closing", False):
            return True
        try:
            self.model.rowCount()
        except RuntimeError:      # the C++ side is already deleted
            return True
        return False

    def _prints_taken(self, results) -> None:
        """Copy back the fingerprints, then go on to the reading.

        Only the fingerprints. This pass never opened a headline reader, so what
        it hands back about the words is silence, not an answer - writing that
        onto a clipping would wipe a reading taken earlier in the morning.
        """
        if self._gone():
            return
        by_uid = {row.clip.uid: row.clip for row in self.model.rows
                  if row.clip is not None}
        for got in results or ():
            clip = by_uid.get(got.uid)
            if clip is None:
                continue
            if got.print_all:
                clip.picture_hash = got.print_all
            if got.print_low:
                clip.picture_hash_lower = got.print_low
            if getattr(got, "print_fine", ""):
                clip.picture_hash_fine = got.print_fine
            if getattr(got, "ink", ""):
                clip.ink_profile = got.ink
            if getattr(got, "width", 0):
                clip.content_w = got.width
                clip.content_h = got.height
        self._duplicates_running = False
        self._read_the_shortlist()

    def _read_the_shortlist(self) -> None:
        """Read the headline off the few clippings that could be repeats."""
        if self._duplicates_running or self._gone():
            return
        clips = [row.clip for row in self.model.rows if row.clip is not None]
        try:
            wanted = duplicates.to_read(clips)
        except Exception:  # noqa: BLE001 - never let this break the list
            wanted = []
        unread = [(c.uid, c.image_bytes) for c in wanted]
        if not unread or not ocr.available():
            self._finish_duplicate_check([])
            return

        self._duplicates_running = True
        self._flash(f"Looking at {len(unread)} clipping(s) for duplicates…",
                    "info")
        # measure=False: every one of these was measured by the pass that
        # picked them out, moments ago. Measuring them again cost a 767ms pause
        # the instant the reading began, because four threads decoded four
        # pictures at once.
        self._reader_thread, self._reader = reader.start(
            unread, self._duplicate_progress, self._duplicate_readings, self,
            measure=False)

    def _duplicate_progress(self, done: int, total: int) -> None:
        # Quietly, on the strip that is already there. No dialog: the user did
        # not ask for this and should not have to dismiss it.
        #
        # Only when the words would actually change. The reader says how far it
        # has got several times a second, and a count sitting still on a
        # multiple of eight used to rewrite the strip every single time - 1628
        # rewrites and 716ms of the window's own thread in one check, to say the
        # same sentence over and over.
        if done != total and done % 8:
            return
        said = f"Reading clippings… {done} of {total}"
        if said == getattr(self, "_last_progress", ""):
            return
        self._last_progress = said
        self._flash(said, "info")

    def _duplicate_readings(self, results) -> None:
        """Copy what the reader worked out back onto the clippings.

        Done here, on the window's thread, because these objects are painted
        from it. The reader never touches a Clip - it is given bytes and hands
        back values - so there is no moment when a clipping is half written
        while the list is drawing it.
        """
        if self._gone():
            return
        by_uid = {row.clip.uid: row.clip for row in self.model.rows
                  if row.clip is not None}
        for got in results or ():
            clip = by_uid.get(got.uid)
            if clip is None:
                continue        # deleted while we were reading; nothing to do
            clip.ocr_text = got.text
            clip.headline_confidence = got.confidence
            clip.ocr_engine = got.engine
            if got.print_all:
                clip.picture_hash = got.print_all
            if got.print_low:
                clip.picture_hash_lower = got.print_low
            if getattr(got, "print_fine", ""):
                clip.picture_hash_fine = got.print_fine
            if getattr(got, "ink", ""):
                clip.ink_profile = got.ink
            if getattr(got, "width", 0):
                clip.content_w = got.width
                clip.content_h = got.height
        self._duplicates_running = False
        self._finish_duplicate_check(results)

    def _finish_duplicate_check(self, results) -> None:
        """Compare everything and say what was found. Fast: no reading here."""
        if self._gone():
            return
        clips = [row.clip for row in self.model.rows if row.clip is not None]
        try:
            self._duplicate_pairs = duplicates.apply(clips)
            self._mark_duplicate_files(clips)
        except Exception:  # noqa: BLE001 - never let this break the list
            self._duplicate_pairs = []
        # Then the ones the user's own past verdicts say are worth a look.
        # Kept APART from the flagged ones, because everything in
        # _duplicate_pairs is out of the report and badged as a repeat, and a
        # suggestion is neither of those things. They are put in front of
        # somebody in the review dialog and nowhere else.
        try:
            self._duplicate_hints = duplicates.suggestions(
                clips, self._duplicate_pairs)
        except Exception:  # noqa: BLE001 - a suggestion is never worth a crash
            self._duplicate_hints = []

        found = len(self._duplicate_pairs)
        hints = len(getattr(self, "_duplicate_hints", []))
        self.duplicates_btn.setVisible(found > 0 or hints > 0)
        if found or hints:
            self.duplicates_btn.setText(
                f"Preview and Delete Duplicates ({found})" if found
                else f"Look at {hints} possible duplicate(s)")
        self.model.layoutChanged.emit()
        self._update_counts()
        # Asked for out loud, so answered out loud - whether or not anything
        # was found, because "nothing flagged" and "never looked" are the same
        # thing on screen otherwise. That is the whole point of the button.
        # Only once something has actually been read. A pass that read nothing
        # is not the answer the button was pressed for, and consuming the flag
        # on it left the direct answer to be overwritten a moment later by the
        # quiet one.
        if getattr(self, "_recheck_out_loud", False) and results:
            self._recheck_out_loud = False
            if found:
                self._flash(
                    f"Checked {len(clips)} clippings — {found} "
                    f"{'look' if found != 1 else 'looks'} like a repeat. "
                    f"Badged, and still in the report until you look at them.",
                    "info")
            else:
                unread = sum(1 for c in clips if not duplicates.readable(c))
                note = f"Checked {len(clips)} clippings — no duplicates found."
                if unread:
                    # Honest about its own reach: a cutting whose headline could
                    # not be read was never compared with anything.
                    note += f" {unread} could not be read well enough to compare."
                self._flash(note, "good")
        elif results:
            # Only worth saying when something was actually read. A check that
            # found nothing new to look at should pass without comment.
            if found:
                self._flash(
                    f"{found} clipping(s) look like repeats — badged, and "
                    f"still in the report until you look at them.", "info")
            else:
                self._flash("No duplicates found.", "good")

    def _read_one(self, clip) -> None:
        """Read one clipping's headline, keeping the window alive while it does."""
        from ..core import ocr

        try:
            ocr.read_into(clip)
            QApplication.processEvents()
        except Exception:  # noqa: BLE001 - a clipping that will not read
            pass

    def _source_of(self, clip) -> str:
        """Which file a clipping came in from, for the review screen."""
        for row in self.model.rows:
            if row.clip is clip:
                return row.source_name or clip.source_file or ""
        return clip.source_file or ""

    def recheck_after_restore(self) -> None:
        """Look again once a saved session is back on screen.

        The clippings come back with whatever was decided last time, including
        which were switched off as repeats. That was true of the list as it
        was; it has to be established again for the list as it is.
        """
        self.recheck_duplicates()

    def _mark_duplicate_files(self, clips: list) -> None:
        """Notice when a whole file repeats another whole file.

        The same division's report can arrive twice - once as the Word file and
        once as the PDF made from it - and then every clipping in it is a
        repeat. Ninety red badges is the wrong way to say that. It is one
        mistake, made once, and what wants saying is "this whole file is
        already here", so it can go in a single action.
        """
        where = {}
        titles = {}
        for row in self.model.rows:
            if row.clip is None:
                continue
            where[row.clip.uid] = row.group_key
            titles.setdefault(row.group_key, row.source_name or row.group_key)
        try:
            repeats = duplicates.whole_files(
                clips, lambda clip: where.get(clip.uid, ""))
        except Exception:  # noqa: BLE001 - never let this break the list
            repeats = {}
        self.model.duplicate_files = {
            key: titles.get(other, "another file")
            # Never the loose bracket. Clippings dragged in from WhatsApp all
            # share one heading, but that heading is not a FILE - it is a pile
            # of unrelated pictures that happen to sit together. If most of a
            # morning's forwards happened to repeat one division's report,
            # marking the bracket "already imported" would invite deleting the
            # lot, and the ones that were not repeats would go with them.
            for key, other in repeats.items()
            if key and key != LOOSE_KEY and other != LOOSE_KEY
        }

    def _auto_duplicates_toggled(self, on: bool) -> None:
        self._auto_duplicates = bool(on)
        settings = export_dialog.load_settings()
        settings["auto_duplicates"] = self._auto_duplicates
        export_dialog.save_settings(settings)
        if on:
            self._flash("Imports will be checked for duplicates.", "info")
            self.recheck_duplicates()
        else:
            self._flash(
                "Automatic duplicate checking is off — use Check for "
                "Duplicates when you want it.", "info")

    def check_duplicates_now(self) -> None:
        """Look again, now, and say plainly what was found.

        The automatic check is quiet on purpose: it puts a button up when there
        is something to look at and stays out of the way when there is not.
        That is right for working, but it leaves no way to be SURE it has
        looked - silence and "nothing found" are the same thing on screen.

        So this looks on demand and reports either way, and it does not trust
        anything it worked out earlier. A clipping that has been cropped, or
        turned the right way up, since it came in is a different picture from
        the one that was read, and whatever was read off it then is stale.

        **It goes the same way round as the automatic check**, which it did not
        used to. It printed every picture twice - fingerprint() and
        fingerprint_lower() each decode and trim the whole image again - and
        then read every headline one at a time on the drawing thread. Measured
        on a real morning: 68.9 seconds of frozen window, 134 pauses over a
        tenth of a second, the longest 1.7 seconds. That is the failure
        ui/reader.py exists to prevent, and this path had simply never been
        moved onto it. Now it is: one measurement per picture, four readers at
        once, on threads that stand aside for the window.
        """
        from ..core import ocr

        if self._duplicates_running:
            self._flash("Already looking — one moment.", "info")
            return
        clips = [row.clip for row in self.model.rows if row.clip is not None]
        if not clips:
            self._flash("There are no clippings to check.", "info")
            return
        if not ocr.available():
            QMessageBox.warning(
                self, "Cannot check for duplicates",
                "The headline reader is not available on this machine, so "
                "clippings cannot be compared by what they say.\n\n"
                + (ocr.why_not() or "It was not installed with the app."))
            return

        # Forget everything worked out before - every measurement, not only the
        # two the comparison happens to use today. Clearing just those two left
        # the finer print, the ink profile and the content box sitting at their
        # pre-crop values for the rest of the session, because _ensure_prints
        # saw them filled in and skipped the clipping. Silently, and against
        # this function's own promise that anything that still matters is read
        # again.
        for clip in clips:
            clip.picture_hash = ""
            clip.picture_hash_lower = ""
            clip.picture_hash_fine = ""
            clip.ink_profile = ""
            clip.content_w = 0
            clip.content_h = 0
            clip.ocr_text = ""
            clip.ocr_engine = ""
            clip.headline_confidence = 0

        self._recheck_out_loud = True
        self._flash(f"Looking at all {len(clips)} clippings again…", "info")
        self._run_duplicate_check()

    def where_things_are_kept(self) -> None:
        """What the program keeps, where it keeps it, and how to have a copy."""
        from .. import version
        from ..core import backup

        where = backup.kept_where()
        last = backup.last_kept()
        here = backup.what_is_here()

        lines = [
            f"Clippings Manager {version.describe()}",
            "",
            "Nothing in this program reaches the network by itself. Every "
            "document is read on this machine, and nothing is sent anywhere. "
            "The one exception is the button below, which asks once - only "
            "when you press it - whether a newer version has been published.",
            "",
            "WHAT IT REMEMBERS BY ITSELF",
            "   " + (", ".join(said for _n, said, _s in here)
                     if here else "nothing set up yet"),
            f"   kept in {backup._folder()}",
            "   That folder is not inside the program's own folder, so "
            "updating the program never touches it. There is nothing you "
            "need to do.",
            "",
            "A COPY SOMEWHERE THAT IS BACKED UP",
        ]
        if where is None:
            lines += [
                "   Not set up.",
                "",
                "   If you install Google Drive or use OneDrive, point this at "
                "that folder and a fresh copy of your setup is written there "
                "every time you close the program. The program still does not "
                "go online - it writes a file, and the sync program you "
                "already have carries it into your account.",
            ]
        else:
            lines += [f"   {where / backup.KEPT_NAME}"]
            if last:
                lines += [f"   last written {last.replace('T', ' at ')}"]
            else:
                lines += ["   not written yet — it is written when you close "
                          "the program"]
            if not where.is_dir():
                lines += ["", "   THAT FOLDER IS NOT THERE AT THE MOMENT. "
                              "Nothing is being copied."]
            lines += ["", "   Your clippings are not copied there: they are a "
                          "morning's work rather than a setting, and they are "
                          "the newspapers' own pictures."]

        asked = QMessageBox(self)
        asked.setIcon(QMessageBox.Information)
        asked.setWindowTitle("Where your things are kept")
        asked.setText("\n".join(lines))
        updates = asked.addButton("Check for updates",
                                  QMessageBox.AcceptRole)
        change = asked.addButton(
            "Change where the copy goes…" if where is not None
            else "Keep a copy somewhere…", QMessageBox.AcceptRole)
        save = asked.addButton("Save my setup to a file…",
                               QMessageBox.AcceptRole)
        # Reachable from here because THIS is where somebody on a fresh machine
        # will be: no clippings, so no select bar, so no Filter and arrange
        # strip and no category editor. The crown is always on screen.
        load = asked.addButton("Put a saved setup back…",
                               QMessageBox.AcceptRole)
        asked.addButton("Close", QMessageBox.RejectRole)
        asked.exec()

        from . import backup_actions

        pressed = asked.clickedButton()
        if pressed is updates:
            self.check_for_updates()
        elif pressed is change:
            backup_actions.choose_kept_folder(self)
        elif pressed is save:
            backup_actions.save_setup(self)
        elif pressed is load:
            if backup_actions.load_setup(self):
                # A restored newspaper list has to reach the filter strip, and
                # the trainer has to see any judgements that came with it.
                self.model.forget_book()
                self.board_model.forget_book()
                self._refresh_filter_choices()

    def _word_list_changed(self) -> None:
        """The list of words kept out of the report was edited.

        Nothing on any clipping changes - the list is applied when a report is
        drawn and never written back - so there is nothing to undo and nothing
        to save. Taking a word off the list puts it back in the report, because
        it was never removed from the clipping in the first place.
        """
        from ..export import build_sentiment

        build_sentiment.forget_sieve()
        held = len(wordlist.load())
        self._flash(
            f"{held} word(s) will be left out when the report prints."
            if held else "No words are being kept out of the report.", "info")

    def check_for_updates(self) -> None:
        """Ask once whether a newer version has been published.

        Only from here, only when pressed. Nothing checks on its own: a program
        that phones home while somebody is working is a different program from
        the one on the crown that says it does not.
        """
        from ..core import updates

        self._flash("Asking whether there is a newer version…", "info")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            found = updates.check()
        finally:
            QApplication.restoreOverrideCursor()

        if not found.get("ok"):
            # Not being able to check is not a fault worth a warning triangle.
            self._flash(f"Could not check for updates — {found.get('why', '')}",
                        "info")
            QMessageBox.information(
                self, "Could not check for updates",
                found.get("why", "")
                + f"\n\nYou are running {found.get('here', '')}. Nothing is "
                  f"wrong with it - only the check failed.")
            return

        if not found.get("newer"):
            self._flash(f"You have the latest version ({found['here']}).",
                        "good")
            QMessageBox.information(
                self, "You are up to date",
                f"You are running {found['here']}, and that is the newest "
                f"version published.")
            return

        asked = QMessageBox(self)
        asked.setIcon(QMessageBox.Information)
        asked.setWindowTitle("There is a newer version")
        asked.setText(f"Version {found['there']} has been published.\n\n"
                      f"You are running {found['here']}.")
        told = found.get("notes", "").strip()
        asked.setInformativeText(
            (told + "\n\n" if told else "")
            + "Nothing is downloaded or changed here - pressing Open takes you "
              "to the download page in your browser.\n\nYour settings, your "
              "newspaper list and everything the trainer has been taught are "
              "kept outside the program's own folder, so updating leaves all "
              "of it exactly where it is.")
        open_it = asked.addButton("Open the download page",
                                  QMessageBox.AcceptRole)
        asked.addButton("Not now", QMessageBox.RejectRole)
        asked.exec()
        if asked.clickedButton() is open_it:
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl(found.get("download")
                                          or updates.RELEASES))

    def open_trainer(self) -> None:
        """Show pairs to judge, and write down what is decided about them."""
        from .trainer_dialog import TrainerDialog

        clips = [row.clip for row in self.model.rows if row.clip is not None]
        if len(clips) < 2:
            self._flash("Import some clippings first — the trainer compares "
                        "them against each other.", "info")
            return
        if self._duplicates_running:
            self._flash("Still looking through the clippings — one moment.",
                        "info")
            return

        # Every pair needs its prints, and the trainer asks about pairs the
        # check never looks at, so anything unmeasured has to be measured now.
        missing = [c for c in clips if c.image_bytes and not c.picture_hash_fine]
        if missing:
            self._flash(f"Measuring {len(missing)} clipping(s) first…", "info")
            QApplication.processEvents()
            try:
                duplicates._ensure_prints(clips)
            except Exception:  # noqa: BLE001 - never let this stop the screen
                pass

        screen = TrainerDialog(clips, list(getattr(self, "_duplicate_pairs", [])),
                               self._source_of, self)
        screen.exec()
        said = training.summary()
        if said["rows"]:
            self._flash(
                f"{said['pairs']} pair(s) judged so far — "
                f"{said['duplicates']} the same, {said['separate']} different. "
                f"Saved on this machine; use Save to a file to keep or send it.",
                "good")

    def review_duplicates(self) -> None:
        """Show each suspected repeat beside the one it repeats."""
        from .duplicates_dialog import DuplicatesDialog

        pairs = list(getattr(self, "_duplicate_pairs", []))
        # The suggestions come along for the ride, at the end, where they read
        # as "and these might be worth a look" rather than as more of the same.
        hints = list(getattr(self, "_duplicate_hints", []))
        if not pairs and not hints:
            self._flash("Nothing is flagged as a duplicate.", "info")
            return
        pairs = pairs + hints

        screen = DuplicatesDialog(pairs, self._source_of, self)
        if screen.exec() != QDialog.Accepted:
            return

        # Every judgement is written down before anything is acted on. It is
        # the only labelled data that describes THIS department's papers, and
        # it is what makes the check better at finding the repeats it misses -
        # see core/verdicts.
        from ..core import verdicts

        by_uid = {row.clip.uid: row.clip for row in self.model.rows
                  if row.clip is not None}
        kept = {clip.uid for clip in screen.to_keep()}
        removed = {clip.uid for clip in screen.to_delete()}
        how = verdicts.BULK if getattr(screen, "swept", lambda: False)() \
            else verdicts.ONE_BY_ONE
        for pair in pairs:
            copy_uid = getattr(pair.copy, "uid", None)
            if copy_uid in kept:
                verdicts.record(pair.primary, pair.copy, False, how)
            elif copy_uid in removed:
                verdicts.record(pair.primary, pair.copy, True, how)

        # "Not a duplicate" is remembered on the clipping, so the next check
        # does not simply flag it again the moment anything else changes.
        for clip in screen.to_keep():
            clip.not_duplicate = True
            clip.duplicate_of = None
            clip.include = True

        # Deleted through the same command every other deletion in the app
        # uses, so Ctrl+Z brings them back. The confirmation says so: telling
        # somebody a thing cannot be undone when it can is its own kind of bug.
        doomed = {clip.uid for clip in screen.to_delete()}
        if doomed:
            ids = [row.id for row in self.model.rows
                   if row.clip is not None and row.clip.uid in doomed]
            if ids:
                self.undo_stack.push(commands.RemoveClips(
                    self.model, ids,
                    f"{len(ids)} duplicate(s) deleted" if len(ids) > 1
                    else "Duplicate deleted"))

        self.recheck_duplicates()
        said = []
        if doomed:
            said.append(f"deleted {len(doomed)}")
        if screen.to_keep():
            said.append(f"kept {len(screen.to_keep())}")
        self._flash("Duplicates: " + (", ".join(said) if said
                                      else "nothing changed") + ".", "good")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt name
        """Flush everything deferred: settings, and the session itself."""
        # Before anything else, so a background pass that finishes during the
        # close finds the door shut rather than a half-deleted window.
        self._closing = True
        reader_thread = getattr(self, "_reader", None)
        if reader_thread is not None:
            try:
                reader_thread.stop()
            except Exception:  # noqa: BLE001 - it may already be finished
                pass
        for card in (self.cover, self.board.cover, self.heading,
                     getattr(self.board, "heading", None)):
            try:
                if card is not None:
                    card.flush()
            except Exception:  # noqa: BLE001 - never block a close
                pass
        try:
            self._save_timer.stop()
            self.save_session()
        except Exception:  # noqa: BLE001
            pass
        # A copy of the setup, if one was asked for - into a Drive or OneDrive
        # folder, usually, where the sync program that is already installed
        # carries it into somebody's account. It is 25KB and it never talks to
        # anything, so it cannot hang a close; a folder that has gone is a
        # shrug. See core/backup.
        try:
            from ..core import backup

            backup.keep_a_copy()
        except Exception:  # noqa: BLE001 - never let a backup block a close
            pass
        super().closeEvent(event)

    # ------------------------------------------------------------ placement
    def _bottom_chrome(self) -> int:
        """How much of the window's bottom edge is not the page.

        Measured rather than assumed. It used to be the number 60, which is
        about right for the standard interface's footer and nowhere near the
        sentiment board's export strip - so on that interface the round buttons
        were drawn on top of the strip and swallowed clicks meant for the
        right-hand end of Download PDF.
        """
        room = 0
        footer = getattr(self, "footer", None)
        if footer is not None and footer.isVisible():
            room += footer.height()
        if self.mode == "sentiment":
            strip = getattr(self.board, "export_strip", None)
            if strip is not None and strip.isVisible():
                room += strip.height() + 10
        return max(60, room)

    def _place_floating(self, *_args) -> None:
        margin = 18
        footer = self._bottom_chrome()
        x = self.width() - 42 - margin
        y = self.height() - footer - 42 - margin
        for button in reversed(self.floaters):
            button.move(x, y)
            button.raise_()
            y -= 50

        # Room at the foot of the page for whatever is floating over it, so the
        # last clipping can always be scrolled clear of the bar rather than
        # ending up underneath it with nowhere further to go.
        page = getattr(self, "body_scroll", None)
        inner = page.widget() if page is not None else None
        shape = inner.layout() if inner is not None else None
        if shape is not None:
            wanted = (self.batch.height() + 26) if self.batch.isVisible() else 0
            left, top, right, bottom = shape.getContentsMargins()
            if bottom != wanted:
                shape.setContentsMargins(left, top, right, wanted)

        if self.batch.isVisible():
            # The bar is positioned by hand, not by a layout, so nothing else
            # stops it hanging off the edge of a narrow window - and its close
            # button is the last thing on it.
            self.batch.setMaximumWidth(max(240, self.width() - 16))
            self.batch.adjustSize()
            self.batch.move(
                max(8, (self.width() - self.batch.width()) // 2),
                self.height() - footer - self.batch.height() - 14,
            )
            self.batch.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_floating()
