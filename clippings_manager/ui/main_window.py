"""The application window.

Starts empty. Every morning brings different documents and different loose images,
so the tool opens ready to receive today's, by whichever route is nearest to hand:
a Word file, a PDF, a folder of photos, a drag from Explorer, or Ctrl+V straight out
of WhatsApp Web.
"""

from __future__ import annotations

import functools
import itertools
import json
import os
import sys
from contextlib import contextmanager
from datetime import date, datetime
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
    QProgressBar,
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
from ..core import (duplicates, links, newspads, ocr, sentiment, training,
                    wordlist)
from ..core.models import Clip, Section
from ..core.profiles import NameIndex
from .. import version
from ..core.session import SessionStore, decode_clip, encode_clip
from . import (collect, commands, datefield, dropped, export_dialog, icons,
               reader, theme, webclip, win_drop, zoom)
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
from .sentiment_cover_card import MORNING, legacy_morning
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


def _pumps(method):
    """For work that runs its own event loop - an import's progress, an export,
    the trainer. The newspad button is held while it runs: a switch from inside
    one would swap the lists out from under the work. A decorator rather than a
    wrapper around a renamed body, so each keeps its own name and its own body.
    """
    @functools.wraps(method)
    def held(self, *args, **kwargs):
        with self._busy():
            return method(self, *args, **kwargs)
    return held


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # FIRST, before any card exists. The dossier cover's morning values -
        # its date, count, division and prepared-by lines - used to live in the
        # shared sentiment_cover.json, and now live in each newspad's session.
        # Newspad 1 inherits them once, from the file, the first time this build
        # opens it. This has to be read before the card is built, because the
        # card saves its design within moments of existing and that save no
        # longer carries these five.
        self._legacy_dossier = legacy_morning()
        # Which of the four newspads is in the window, and the machinery that
        # keeps a switch between them from mixing one newspad's work into
        # another's. See switch_newspad.
        self.newspad = newspads.active()
        self._switching = False
        self._newspad_gen = 0       # bumped by every switch; see _deferred
        self._pass_gen = 0          # bumped when a reading pass is settled
        self._pumping = 0           # >0 while something runs its own event loop
        self._opened = {self.newspad}
        self._read_only = False
        # Read-only because a switch went wrong part-way, rather than because
        # saved work could not be read. See _back_to.
        self._stuck = False
        self._winding_down: list = []
        self._check_pending = ""
        self._resume_check = ""
        self._answer_even_if_nothing_read = False
        # What a switch has to say when it is over, said once, together - see
        # _after_switch. The arrival note carries warnings (clippings that
        # could not be read, work from another build) and must never be
        # replaced by a later, cheerier message.
        self._arrival = None
        self._design_notes: list = []
        # "Collecting was switched off for the change", said with the rest.
        self._collect_note = ""
        # The board column an Add button, a drop onto a column or a paste has
        # asked for, until the import it started has stamped it. Set here, not
        # first by a paste: Collect reads it before every photo it adds.
        self._pending_section = None
        # A switch refused because a cover or headline setting would not save.
        # Asked for again, the switch goes ahead without that change.
        self._design_refused = None
        # The build is in the title because the first question after "it works
        # on my laptop but not on that one" is which build each of them is
        # running, and until this there was nothing anywhere that could answer
        # it. Two machines showing the same digest are running the same code.
        self.setWindowTitle(self._title())
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

        # Each newspad's own folder. Newspad 1 is the one session folder there
        # has always been, so the morning on this machine the day this ships
        # comes through untouched.
        self.store = SessionStore(newspads.folder(self.newspad))
        self._restoring = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(1500)
        self._save_timer.timeout.connect(self.save_session)

        # Collect from WhatsApp. Made before the window is built, because the
        # header holds its button and its bar. Off at every launch, and never
        # remembered: it reads the clipboard only when somebody asks it to.
        self.collector = collect.Collector(self)
        self._build()
        # Before _wire and before the window is shown: from here on the four
        # design panels are this newspad's, so nothing edited in the first
        # second can land in another newspad's files.
        self._point_designs_at_launch()
        self._wire()
        self._mark_what_is_whose()
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
    def _title(self) -> str:
        """The build stays in the title: two machines showing the same digest
        are running the same code. The newspad is there so it is never in
        doubt which one is open."""
        collecting = getattr(getattr(self, "collector", None), "is_on", False)
        return (f"Clippings Manager  —  Newspad {self.newspad}  —  "
                f"{version.describe()}" + ("  —  Collecting" if collecting else ""))

    def touch_session(self) -> None:
        """Something changed - write the manifest shortly.

        Not during a switch: the lists are being emptied and refilled, and a
        save armed then would write whichever newspad is half on screen into
        whichever store is current. Not for a newspad that cannot be read
        either - see _read_only.
        """
        if self._restoring or self._switching or self._read_only:
            return
        self._save_timer.start()

    def _encode_pool(self, pool) -> list:
        """One pool's rows, with the pictures put in the blob folder."""
        rows = []
        for row in pool.rows:
            data = row.clip.image_bytes or b""
            # Worked out once per picture. The test is on the bytes themselves,
            # not on whether they look the same: if anything ever does replace a
            # clipping's picture, this notices and names it again.
            #
            # And only while the file is still there. A clipping deleted, saved,
            # and brought back with Ctrl+Z still remembers its name, but the
            # tidy-up after that save had removed the picture; trusting the name
            # wrote a manifest pointing at nothing, and the clipping was gone at
            # the next launch.
            if (data and row.blob_name and row.blob_of is data
                    and self.store.has_blob(row.blob_name)):
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
                "home_title": row.home_title,
                "home_kind": row.home_kind,
                "blob": blob,
                "clip": encode_clip(row.clip),
            })
        return rows

    def save_session(self, strict: bool = False) -> None:
        """Write the manifest, then drop pictures nothing refers to.

        ``strict`` is for a newspad switch, which must not go ahead unless the
        outgoing newspad is safely on disk: a failed save raises instead of
        being shrugged off. Tidying away unused pictures is still allowed to
        fail quietly, because once the manifest is written that is housekeeping.

        Never for a newspad whose saved work could not be read. An empty save
        there would tidy away every picture of a morning still waiting to be
        rescued.
        """
        if self._restoring or self._read_only:
            return
        if self._switching and not strict:
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
                # Everything else that belongs to THIS newspad rather than to
                # the install. One additive key: VERSION stays 1, because
                # bumping it made an older build's close wipe the session.
                "newspad": self._newspad_values(),
            })
        except Exception:  # noqa: BLE001 - a failed save must not stop the work
            if strict:
                raise
            return
        try:
            self.store.collect(
                {r["blob"] for r in standard + sentiment if r["blob"]}
            )
        except Exception:  # noqa: BLE001 - the manifest is safe; this is tidying
            pass

    def _newspad_values(self) -> dict:
        """This newspad's own values, for its session."""
        return {
            "press_date": self.cover.report_date().isoformat(),
            "dossier": self.board.cover.morning(),
            "board": self.board.export_choices(),
            "duplicate_check": getattr(self, "_check_pending", ""),
        }

    def _apply_newspad_values(self, payload, arriving: bool = False) -> None:
        """Put a newspad's own values back - or a fresh newspad's, with None.

        Run with _restoring set, so putting a date back is not mistaken for
        somebody changing it and does not start a save of its own.
        """
        payload = payload or {}
        values = payload.get("newspad") or {}
        was = self._restoring
        self._restoring = True
        try:
            # The press date comes back only if it was saved TODAY. That keeps
            # today's behaviour, where a report opens on today's date: work
            # left from an earlier day is yesterday's newspad, and dating a
            # fresh morning's report yesterday would be wrong.
            press = None
            try:
                saved = datetime.fromisoformat(str(payload.get("saved_at", "")))
                if saved.date() == datetime.now().date():
                    press = date.fromisoformat(str(values.get("press_date")))
            except (TypeError, ValueError):
                press = None
            self.cover.set_report_date(press)

            dossier = values.get("dossier")
            if not dossier and self.newspad == 1:
                # The one-time hand-over from the old shared file.
                dossier = self._legacy_dossier
            self.board.cover.set_morning(dossier)

            if arriving:
                self.board.set_export_choices(values.get("board"))
                self.set_mode(payload.get("mode") or "standard")
            self._resume_check = str(values.get("duplicate_check") or "")
        finally:
            self._restoring = was

    def _peek_clip_id(self) -> int:
        """The next id the shared counter would hand out, without spending one.

        Peeking replaces the counter, so both pools have to be handed the new
        one, exactly as restore_session already does. Left on the old one, they
        went on minting from where it stood while the saved next_clip_id stayed
        frozen - measured, an id handed out twice.
        """
        value = next(self._clip_ids)
        self._clip_ids = itertools.count(value)
        self.model._ids = self._clip_ids
        self.board_model._ids = self._clip_ids
        return value

    def _peek_group_serial(self) -> int:
        value = next(self._group_serial)
        self._group_serial = itertools.count(value)
        return value

    # --------------------------------------------------------- restoring it
    def _asked(self, payload: dict) -> bool:
        """_wanted, with every save held off while its question is on screen.

        The question box runs an event loop of its own, and at launch it comes
        up with the window still EMPTY - nothing has been put back yet - while
        the session timer is already running: building the window arms it
        (the board's first recount sets the dossier's division line, which
        counts as a change). In 2.0.20 that timer fired behind the box, saved
        the empty window over the morning being asked about, and the tidy-up
        after the save deleted every one of its pictures. Measured: answer
        "Open them again" after three seconds and 0 of 6 clippings came back.

        So the timer is stopped, and nothing may arm a save or save - not the
        timer, not a close, not a logoff - until the question is answered.
        """
        self._save_timer.stop()
        was = self._restoring
        self._restoring = True
        try:
            return self._wanted(payload)
        finally:
            self._restoring = was

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


    def restore_session(self, ask: bool = True, arriving: bool = False) -> int:
        """Put back whatever was open when the application last closed.

        Every way out of here puts the newspad's own values back - its dates and
        its dossier lines - including the ways that restore no clippings, so a
        fresh newspad starts on its own fresh values rather than keeping
        whatever the last one had.
        """
        payload = self.store.load()
        if not payload:
            if self.store.unreadable():
                # There IS saved work and it cannot be read. Saving an empty
                # newspad over it would tidy away every one of its pictures, so
                # this newspad saves nothing until somebody sets the old work
                # aside - see _set_aside_unreadable.
                self._read_only = True
                self._show_read_only(True)
            self._apply_newspad_values(None, arriving)
            return 0
        # Worked out before anything is restored, because the answer is about the
        # manifest on disk rather than about what ends up in the list.
        stale = self.store.saved_by_another_build()
        if ask and not self._asked(payload):
            self.store.clear()
            self._apply_newspad_values(None, arriving)
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
                        home_title=saved.get("home_title", ""),
                        home_kind=saved.get("home_kind", ""),
                        # The picture's stored name comes back with it. Without
                        # this, no restored row carried one - measured, 0 of 163
                        # - so the first save after every restore hashed every
                        # picture again: 788ms on the office machine. Once a
                        # window can switch newspads, every switch is a restore.
                        blob_name=blob,
                        blob_of=data if blob else None,
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
            # Part of it may already be in the list. A save now would keep that
            # part and tidy away every picture of the rest, so the newspad is
            # held read-only until its old work has been set aside.
            self._read_only = True
        finally:
            QApplication.restoreOverrideCursor()
            self._restoring = False
        if self._read_only:
            self._show_read_only(True)
            # Whatever did come back stays on screen: it can still be looked at
            # and exported, and once the old work is set aside it is saved.
            if self.model.rows or self.board_model.rows:
                self._update_counts()
                if self.model.rows:
                    self._show_list()
                self._refresh_board()
        # After the division, because selecting the board's division is what
        # moves the dossier's generated division line - and a newspad's own
        # saved line has to be the one that ends up on the card.
        try:
            self._apply_newspad_values(payload, arriving)
        except Exception:  # noqa: BLE001 - a bad value must not stop a restore
            pass

        if restored:
            self._update_counts()
            if self.model.rows:
                self._show_list()
            self._refresh_board()
            plural = "s" if restored != 1 else ""
            note = (f"Newspad {self.newspad}: {restored} clipping{plural}."
                    if arriving else
                    f"Restored {restored} clipping{plural} from your last "
                    f"session.")
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
            self._arrive(note, "good" if not (lost or stale) else "info")
        elif self._design_notes and not self._switching:
            notes, self._design_notes = self._design_notes, []
            self._flash(" ".join(notes), "bad")
        # The clippings come back carrying last time's verdicts, including
        # which were switched off as repeats. That was true of the list as
        # it was; ask again for the list as it is now.
        resume, self._resume_check = self._resume_check, ""
        if resume == "loud":
            # The button had been pressed. It is answered out loud when the
            # check finishes - even if everything was read before the switch
            # and there is nothing left to read now.
            self._recheck_out_loud = True
            self._answer_even_if_nothing_read = True
        self.recheck_duplicates(force=bool(resume))
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
        # One-time cleanup of headings the old picker saved a letter at a time.
        # Wrapped, because a settings file on a locked-down share that cannot be
        # written must not stop the program opening.
        try:
            from ..core import sections as _sections

            dropped = _sections.repair_once()
            if dropped:
                print(f"  cleared {dropped} heading(s) saved by mistake")
        except Exception:  # noqa: BLE001 - a read-only settings folder
            pass

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

        # Which of the four newspads is open. A button with a menu, never a
        # combo box: a combo takes the wheel, and a wheel turned over the header
        # must scroll the page, never quietly switch somebody's newspad.
        newspad_label = QLabel("NEWSPAD")
        newspad_label.setObjectName("ModeLabel")
        controls.addWidget(newspad_label)
        self.newspad_btn = QPushButton(f"Newspad {self.newspad} ▾")
        self.newspad_btn.setObjectName("HeaderButton")
        self.newspad_btn.setCursor(Qt.PointingHandCursor)
        self.newspad_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.newspad_btn.setToolTip(newspads.SHARED_IN_ONE_LINE)
        self.newspad_btn.setStyleSheet(
            "QPushButton::menu-indicator { image: none; width: 0px; }")
        self.newspad_menu = QMenu(self.newspad_btn)
        self.newspad_menu.aboutToShow.connect(self._fill_newspad_menu)
        self.newspad_btn.setMenu(self.newspad_menu)
        controls.addWidget(self.newspad_btn)

        interface_label = QLabel("INTERFACE")
        interface_label.setObjectName("ModeLabel")
        controls.addWidget(interface_label)

        # Both interfaces on the header, side by side, rather than one of them
        # hidden inside a drop-down with the other. See ui/modeswitch.py.
        self.mode_switch = ModeSwitch()
        self.mode_switch.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        controls.addWidget(self.mode_switch)

        # Collect from WhatsApp: a button, never a switch position or a combo -
        # it is a way of working, not a place, and a combo here would take the
        # wheel. Narrower than the interface switch, so the header's floor does
        # not move. Checked and green while collecting.
        self.collect_btn = QPushButton(collect.LABEL_OFF)
        self.collect_btn.setObjectName("HeaderButton")
        self.collect_btn.setCheckable(True)
        self.collect_btn.setCursor(Qt.PointingHandCursor)
        self.collect_btn.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.collect_btn.setToolTip(collect.TIP_OFF)
        self.collect_btn.clicked.connect(self._toggle_collect)
        controls.addWidget(self.collect_btn)

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
        # In the header, not between it and the page: it has to be seen on both
        # interfaces, and nothing but the header, the footer and the overlays
        # may sit outside the page and take its room. Hidden, it takes none.
        column.addWidget(self._build_read_only_banner())
        # What Collect has just done, and what it needs. In the header, like the
        # banner above: on screen on both interfaces, never scrolled away.
        column.addWidget(self.collector.build_bar())

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

        self.collector.stop("closing")

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
            # Only one copy may run at a time (see main.py), and this one still
            # holds the lock until it has finished closing. Told it is a
            # restart, the new copy waits for the lock instead of reporting that
            # the program is already open and leaving.
            fresh["CM_RESTARTED"] = "1"
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
        # Digital coverage arrives as links, not files: one button for a link
        # and for a whole message full of them.
        self.btn_links = QPushButton("+  From links")
        self.btn_links.setObjectName("NavyOutline")
        self.btn_links.setToolTip(
            "Paste a link, or a whole WhatsApp message with a list of them, and "
            "each story is captured as a clipping.")
        for button in (self.btn_photos, self.btn_word, self.btn_pdf,
                       self.btn_links):
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

        # A bar for work that takes long enough to wonder about. Above the
        # status strip, so the sentence and the bar read as one thing.
        self.work_bar = QProgressBar()
        self.work_bar.setObjectName("WorkBar")
        self.work_bar.setTextVisible(False)
        self.work_bar.setFixedHeight(6)
        self.work_bar.hide()
        layout.addWidget(self.work_bar)

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
            # The arrow is in the words; Qt's own would sit on top of them.
            f"QPushButton::menu-indicator {{ image: none; width: 0px; }}"
            f"QPushButton#BatchMove:open {{ background: rgba(255,255,255,0.24); }}"
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
        # Into another file's group, at its end. A button with a menu rather
        # than a combo box: a combo on this bar would take the wheel from the
        # list scrolling under it. The menu is filled as it opens, so it is
        # always the list as it is now.
        self.batch_move_to = QPushButton("Move to: ▾")
        self.batch_move_to.setObjectName("BatchMove")
        self.batch_move_to.setToolTip(
            "Move the ticked clippings into another file's group - to its end, "
            "in the order they are in now. Nothing that stays is moved, and no "
            "heading changes place.")
        # Parented to the window, not the button: the bar's navy stylesheet
        # must never reach into it, and it looks like every other menu.
        self.batch_move_menu = QMenu(self)
        self.batch_move_menu.setToolTipsVisible(True)
        self.batch_move_menu.aboutToShow.connect(
            lambda: self._fill_move_menu(self.batch_move_menu,
                                         self._selected_ids()))
        self.batch_move_to.setMenu(self.batch_move_menu)
        # No Rotate here: turning a picture is something done to one clipping
        # while looking at it, and every card has its own button for it.
        # "Exclude" reads "Include" when every ticked clipping is already out -
        # see _sync_exclude_button.
        self.batch_exclude = QPushButton("Exclude")
        self.batch_delete = QPushButton("Delete")
        self.batch_delete.setObjectName("BatchDelete")
        self.batch_close = QPushButton("✕")
        self.batch_close.setFixedWidth(30)
        for button in (
            self.batch_merge, self.batch_name, self.batch_top, self.batch_up,
            self.batch_down, self.batch_bottom, self.batch_move_to,
            self.batch_exclude, self.batch_delete, self.batch_close,
        ):
            button.setCursor(Qt.PointingHandCursor)
            row.addWidget(button)
        self.batch.hide()

        # What a move did, said where the bar was. The status line lives at
        # the top of the page, scrolled away while somebody works down the
        # list, so a move reported only there would look like nothing happened.
        self.move_note = QFrame(parent)
        self.move_note.setObjectName("BatchNote")
        self.move_note.setStyleSheet(
            f"#BatchNote {{ background: {theme.NAVY}; border-radius: 16px; }}"
            f"QLabel {{ color: white; font-size: 12px; font-weight: 600;"
            f" background: transparent; }}")
        note_row = QHBoxLayout(self.move_note)
        note_row.setContentsMargins(16, 10, 16, 10)
        self.move_note_text = QLabel()
        self.move_note_text.setWordWrap(True)
        note_row.addWidget(self.move_note_text)
        self.move_note.hide()
        self._move_note_above = False
        self._move_note_timer = QTimer(self)
        self._move_note_timer.setSingleShot(True)
        self._move_note_timer.setInterval(6000)
        self._move_note_timer.timeout.connect(self._hide_move_note)

    # -------------------------------------------------------------- wiring
    def _wire(self) -> None:
        self.btn_word.clicked.connect(lambda: self._choose("word"))
        self.btn_pdf.clicked.connect(lambda: self._choose("pdf"))
        self.btn_photos.clicked.connect(lambda: self._choose("photos"))
        self.btn_links.clicked.connect(self.open_links)
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
        # A move's note goes as soon as anything else happens to the list.
        self.model.selectionChanged.connect(self._hide_move_note)
        self.undo_stack.indexChanged.connect(self._hide_move_note)
        self.board_model.countsChanged.connect(self._update_counts)
        self.board_model.selectionChanged.connect(self._update_selection_ui)

        # A cover or headline panel that could not write its file says so.
        for card in self._design_cards():
            signal = getattr(card, "designProblem", None)
            if signal is not None:
                signal.connect(self._design_problem)

        # This newspad's own values. Saved with its session rather than in a
        # shared settings file, so each has to tell the session it moved.
        # touch_session only starts a timer, so none of these can loop.
        self.cover.date_edit.dateChanged.connect(
            lambda *_args: self.touch_session())
        self.board.cover.changed.connect(self.touch_session)
        self.board.cover.morningChanged.connect(self.touch_session)
        for key in ("banner", "headings", "titles"):
            box = self.board.option_boxes.get(key)
            if box is not None:
                box.toggled.connect(lambda _on: self.touch_session())
        self.board.custom_heading.textChanged.connect(
            lambda _t: self.touch_session())
        self.board.custom_title.textChanged.connect(
            lambda _t: self.touch_session())

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
        self.batch_exclude.clicked.connect(self._batch_exclude)
        self.batch_delete.clicked.connect(self._batch_delete)
        self.batch_close.clicked.connect(self.model.clear_selection)

        self.btn_pdf_out.clicked.connect(lambda: self._export("pdf"))
        self.btn_docx_out.clicked.connect(lambda: self._export("docx"))

        # Through the group, which follows the interface on screen (set_mode
        # makes its stack the active one). Bound straight to undo_stack, as it
        # was, Ctrl+Z pressed on the sentiment board quietly undid work on the
        # press report instead.
        QShortcut(QKeySequence.Undo, self, self.undo_group.undo)
        QShortcut(QKeySequence.Redo, self, self.undo_group.redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, self.undo_group.redo)
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

    @contextmanager
    def _busy(self):
        """Hold the newspad button while something runs its own event loop.
        See _pumps."""
        self._pumping += 1
        self._sync_newspad_button()
        try:
            yield
        finally:
            self._pumping = max(0, self._pumping - 1)
            self._sync_newspad_button()

    def _refuse_if_read_only(self) -> bool:
        if not self._read_only:
            return False
        self._flash("Nothing can be added until the program is opened again."
                    if self._stuck else
                    "This newspad cannot save — set its old work aside first.",
                    "bad")
        return True

    @_pumps
    def import_paths(self, paths: list[Path]) -> None:
        if self._refuse_if_read_only():
            return
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

    def _add_loose(self, clips: list[Clip], quiet: bool = False) -> list:
        """Hand-added clippings share one group and land at the top, in order.

        ``quiet`` is Collect from WhatsApp, where the person is in Chrome, not
        here: nothing comes forward, no headline box opens, nothing takes the
        keyboard - the clipping simply appears. Returns the rows added.
        """
        if self._refuse_if_read_only():
            return []
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
        # Every route in comes through here, so this is where Collect learns
        # which clipping a copied caption belongs to - dragged in or collected.
        collector = getattr(self, "collector", None)
        if collector is not None:
            collector.note_arrival(target, rows)
        if quiet:
            if target is not self.model:
                self._refresh_board()
            else:
                self._show_list()
                # The list follows the newest arrival, wherever the person is
                # looking: the caption they copy next goes on it, and they
                # asked to see it land. Put at the foot of the view, so the
                # ones before it stay in sight above.
                if rows:
                    at_row = self.model.entry_row_for_clip(rows[-1].id)
                    if at_row >= 0:
                        from PySide6.QtWidgets import QAbstractItemView
                        self.list.scrollTo(self.model.index(at_row, 0),
                                           QAbstractItemView.PositionAtBottom)
                self.list._place_editor()
            return rows
        headline = ("Type the headline and press Enter, "
                    + collect.DROP_SUFFIX
                    if collector is not None and collector.is_on else
                    "Type the headline and press Enter.")
        if target is not self.model:
            self._refresh_board()
            # Name the column. A paste that lands silently gives nobody anything
            # to check against, so "it went to the wrong one" and "it went where
            # I asked" look identical until the board is scrolled.
            where = {r.clip.section.value for r in rows}
            into = f" into {', '.join(sorted(where))}" if where else ""
            self._flash(
                f"Added {len(rows)} clipping{'s' if len(rows) != 1 else ''}"
                f"{into}. {headline}",
                "good",
            )
            first = rows[0].id
            self.raise_()
            self.activateWindow()
            QTimer.singleShot(80, self._deferred(
                lambda: self.board.begin_rename(first)))
            return rows

        self._show_list()
        self._flash(
            f"Added {len(rows)} clipping{'s' if len(rows) != 1 else ''} at the top. "
            f"{headline}",
            "good",
        )
        first = rows[0].id
        # After a drag out of a browser the window is often not the active one,
        # so an editor opened now would never really hold the keyboard.
        self.raise_()
        self.activateWindow()
        self.list.setFocus()
        QTimer.singleShot(80, self._deferred(lambda: self._begin_rename(first)))
        return rows

    def _begin_rename(self, clip_id: int) -> None:
        """Open the headline box on a newly added clipping, and mean it.

        A single attempt is not reliable straight after a drop: the list may
        still be laying out, and the window may only just have become active.
        """
        self.activateWindow()
        self.list.open_editor_for(clip_id)
        if self.list.editing_id() != clip_id:
            QTimer.singleShot(140, self._deferred(
                lambda: self.list.open_editor_for(clip_id)))

    def _deferred(self, call):
        """Wrap a call that carries a bare clipping id, to run a moment later.

        Ids are only unique within a newspad: newspad 1 and newspad 2 can both
        have a clipping 5. A call scheduled just before a switch fires just
        after it, and would open the headline box on the other newspad's
        clipping 5. So it remembers which newspad it was made in, and does
        nothing if that is no longer the one in the window.
        """
        made_in = self._newspad_gen

        def run():
            if made_in == self._newspad_gen:
                call()

        return run

    def open_links(self, words: str = "") -> None:
        """The window where links are pasted and captured.

        ``words`` fills the box - a message pasted with Ctrl+V arrives here
        rather than in the "nothing to add" box.
        """
        if self._refuse_if_read_only():
            return
        dialog = getattr(self, "links_dialog", None)
        if dialog is None:
            dialog = self.links_dialog = webclip.LinksDialog(self)
        if words:
            dialog.box.setPlainText(words)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def clip_from_link(self, shot, found) -> None:
        """One captured page, added as a clipping where the person is working.

        The picture already carries the headline, so nothing is typed over it:
        the caption is the publication's name, and the link prints underneath
        as it does for any digital coverage.
        """
        try:
            clip = self._clip_from_bytes(shot.png, f"{found.site}.png")
        except Exception:  # noqa: BLE001 - one link, never the morning
            self._flash(f"That page's picture could not be read ({found.site}).",
                        "bad")
            return
        clip.source_file = "link"
        clip.source_ref = shot.url
        clip.url = shot.url
        clip.show_url_box = True
        clip.outlet = shot.site
        clip.caption_raw = (found.label or shot.title or "")[:300]
        clip.section = (Section.SOCIAL if links.is_social(shot.site)
                        else Section.DIGITAL)
        paper = links.paper_for_site(shot.site, self.name_index)
        if paper:
            clip.newspaper = paper
            clip.name_confidence = 1.0
        clip.name_source = "link"
        pool = self.pool()
        rows = self._add_loose([clip], quiet=True) or []
        if rows:
            self._flash(f"Captured {shot.site} — No. "
                        f"{pool.position_of(rows[0].id) + 1}.", "good")

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
        # Collect has already taken what is on the clipboard: pasting it too
        # would add it twice - and a copied caption would open the "nothing to
        # add" box.
        collector = getattr(self, "collector", None)
        if (collector is not None and collector.is_on
                and collector.watcher.already_read()):
            self._flash(collect.PASTE_NOT_NEEDED, "info")
            return
        # A link on the clipboard is not a picture, and the "nothing to add"
        # box was the wrong answer to it: what somebody pasting a story link
        # wants is the story. The list opens with it already in, so they can
        # see what was found before anything is captured.
        mime = QGuiApplication.clipboard().mimeData()
        carried = dropped.read(mime) if mime is not None else None
        if carried is not None and not carried.images and not carried.files:
            words = mime.text() if mime.hasText() else ""
            found = links.find(words) if words else []
            if found:
                self.open_links(words)
                many = len(found)
                self._flash(f"{many} link{'s' if many != 1 else ''} on the "
                            f"clipboard — press Capture to take "
                            f"{'them' if many != 1 else 'it'}.", "info")
                return
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
        # The box can be committed by the switch that replaces its newspad, and
        # arrive after the clipping it belonged to has left the window.
        if self.model.row_for(clip_id) is None:
            return
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
        if self.model.row_for(clip_id) is None:
            return
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
        if not ids or self.mode != "standard":
            return
        if self._lens_holds(self.model):
            return
        rows = commands.move_relative(self.model, ids, where)
        self.undo_stack.push(
            commands.Reorder(self.model, rows, f"{len(ids)} clippings moved"
                             if len(ids) != 1 else "Clipping moved")
        )

    def _all_excluded(self, ids: list) -> bool:
        return bool(ids) and not any(self.model.by_id(i).include for i in ids)

    def _batch_exclude(self) -> None:
        self._toggle_included(self._selected_ids())

    def _toggle_included(self, ids: list) -> None:
        """Take these clippings out of the report - or, when every one of them
        is out already, put them all back. The button and the menu say which.

        A mixed selection is taken OUT, never put back in. Putting back a
        clipping the duplicate check left out also marks it "not a duplicate"
        for good (see SetIncluded), and nobody who ticked five clippings and
        pressed a button meant that for the one among them they had not
        noticed was out.
        """
        if not ids or self.mode != "standard":
            return              # the bar and the list menu are the report's
        if self._all_excluded(ids):
            self.undo_stack.push(commands.SetIncluded(self.model, ids, True))
            return
        going = [i for i in ids if self.model.by_id(i).include]
        self.undo_stack.push(commands.SetIncluded(self.model, going, False))
        if len(going) != len(ids):
            out = len(ids) - len(going)
            self._flash(
                f"Excluded {len(going)} — the other {out} "
                f"{'were' if out != 1 else 'was'} already out of the report.",
                "info")

    def _sync_exclude_button(self) -> None:
        back = self._all_excluded(self._selected_ids())
        self.batch_exclude.setText("Include" if back else "Exclude")
        self.batch_exclude.setToolTip(
            "Put these back into the report" if back else
            "Leave these out of the report — they stay in the list, greyed")

    @staticmethod
    def _elide_middle(text: str, most: int) -> str:
        return text if len(text) <= most else (
            text[:most - 20].rstrip() + " … " + text[-17:].lstrip())

    def _move_line(self, run, ids: list, part: str, number_it: bool):
        """One file's line in the Move to list: (words, can it be chosen, tip).

        The file's own header words on the left - '&' doubled, or Qt would take
        it for a keyboard shortcut and swallow it - and on the right, after a
        tab, how many it holds and anything that stops a move there.
        """
        model = self.model
        name = self._elide_middle(run.title, 56).replace("&", "&&") + part
        count = f"{run.count} clip" + ("s" if run.count != 1 else "")
        if number_it:
            first = model.position_of(run.rows[0].id) + 1
            last = model.position_of(run.rows[-1].id) + 1
            count += f" · No. {first}–{last}" if last != first else f" · No. {first}"
        inside = [i for i in ids if i in set(run.row_ids)]
        tip = run.title
        if ids and len(inside) == len(ids):
            n = len(ids)
            return f"{name}\t{'all ' + str(n) if n != 1 else 'it is'} already here", \
                False, tip
        if run.key in getattr(model, "duplicate_files", {}):
            return (f"{name}\ta repeat of another file", False,
                    "This whole file repeats another one - clear it rather than "
                    "fill it.")
        plan = commands.plan_move_into(model, ids, run)
        if plan.refused:
            words = plan.refused_words.replace("&", "&&")
            return (f"{name}\twould move {words}", False,
                    f"Not here: {plan.refused}.")
        if inside:
            count += f" · {len(inside)} of the {len(ids)} already here"
        return f"{name}\t{count}", True, tip

    def _fill_move_menu(self, menu: QMenu, ids: list) -> None:
        """The file groups these clippings can be moved into, as they are now.

        What the earlier AI Studio version called its categories: every file in
        the list, and "Clipboard images" for everything added by hand, in list
        order. Filled as the menu opens, so it is always the list as it stands.
        """
        menu.clear()
        model = self.model
        if model.lens.busy:
            menu.addAction("Clear the filter first — while one is on, what you "
                           "see is not the real order").setEnabled(False)
            return
        ids = [r.id for r in model.rows if r.id in set(ids)]
        n = len(ids)
        menu.addAction(f"Move {n} clipping{'s' if n != 1 else ''} to:").setEnabled(False)
        menu.addSeparator()
        runs = model.file_runs()
        parts: dict = {}
        shown: dict = {}
        for run in runs:
            parts[run.key] = parts.get(run.key, 0) + 1
            # Counted on the words as shown: two long names that differ only
            # in the middle shorten to the same line, and have to be told apart.
            seen = self._elide_middle(run.title, 56)
            shown[seen] = shown.get(seen, 0) + 1
        headed = False
        for run in runs:
            part = f" — part {run.occurrence + 1}" if parts[run.key] > 1 else ""
            number_it = (parts[run.key] > 1
                         or shown[self._elide_middle(run.title, 56)] > 1)
            text, enabled, tip = self._move_line(run, ids, part, number_it)
            headed = headed or text.split("\t")[-1].startswith("would move")
            action = menu.addAction(text)
            action.setEnabled(enabled and n > 0)
            action.setToolTip(tip)
            action.triggered.connect(
                lambda _checked=False, ident=run.ident, first=run.rows[0].id:
                self._move_into(ids, ident, first))
        if headed:
            menu.addSeparator()
            menu.addAction("Greyed: moving them there would change where a "
                           "heading prints in the report.").setEnabled(False)

    def _move_into(self, ids: list, ident: str, first_id: int = -1) -> None:
        """File these clippings under another file's group, at its end.

        One undo step (MoveIntoFile). Refused, and said so, when it would
        change where any section heading prints - see plan_move_into.
        """
        model = self.model
        if self.mode != "standard":
            return              # the bar and its menu belong to the press report
        if self._lens_holds(model):
            return
        run = next((g for g in model.file_runs() if g.ident == ident), None)
        if run is None or (first_id >= 0 and run.rows[0].id != first_id):
            self._flash("The list changed while the menu was open — nothing was "
                        "moved.", "info")
            return
        if run.key in getattr(model, "duplicate_files", {}):
            self._flash("That file repeats another one, so nothing is moved into "
                        "it.", "bad")
            return
        plan = commands.plan_move_into(model, ids, run)
        if plan.refused:
            said = f"Not moved — {plan.refused}."
            self._flash(said, "bad")
            self._show_move_note(said, above_bar=True)
            return
        if not plan.moving:
            self._flash(f"Those clippings are already in {run.title}.", "info")
            return
        n = len(plan.moving)
        title = self._elide_middle(run.title, 40)
        text = (f"{n} clippings moved to {title}" if n != 1
                else f"Clipping moved to {title}")
        self.undo_stack.push(commands.MoveIntoFile(model, plan, text))
        # After the push: the push moves the undo index, which hides the note.
        said = self._move_message(plan)
        self._flash(said, "good")
        self._show_move_note(said)

    def _move_message(self, plan) -> str:
        model = self.model
        n = len(plan.moving)
        places = [model.position_of(i) + 1 for i in plan.moving]
        where = (f"No. {min(places)}–{max(places)}" if n > 1
                 else f"No. {places[0]}")
        said = (f"Moved {n} into {self._elide_middle(plan.run_title, 48)} — now "
                f"{where}. Ctrl+Z puts {'them' if n != 1 else 'it'} back.")
        for _from_id, to_id, words in plan.handoffs:
            said += f" {words} now prints over No. {model.position_of(to_id) + 1}."
        if plan.now_under and plan.now_under not in plan.was_under:
            said += f" They now print under {plan.now_under}." if n != 1 else \
                f" It now prints under {plan.now_under}."
        gone = [w for w in plan.was_under if w != plan.now_under]
        if gone:
            said += (f" {'They' if n != 1 else 'It'} no longer "
                     f"print{'' if n != 1 else 's'} under {', '.join(gone)}.")
        if plan.already:
            k = len(plan.already)
            said += (f" {k} {'were' if k != 1 else 'was'} already there and "
                     f"stayed put.")
        return said

    def _show_move_note(self, text: str, above_bar: bool = False) -> None:
        self.move_note_text.setText(text)
        self._move_note_above = above_bar
        self.move_note.show()
        self._place_floating()
        self._move_note_timer.start()

    def _hide_move_note(self, *_args) -> None:
        note = getattr(self, "move_note", None)
        if note is not None and note.isVisible():
            self._move_note_timer.stop()
            note.hide()

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
        if self.mode != "standard":
            return
        if len(ids) < 2:
            self._flash("Pick at least two clippings to merge.", "info")
            return
        self.undo_stack.push(commands.Merge(self.model, ids))
        self._flash(f"{len(ids)} merged into one — Ctrl+Z undoes it.", "good")

    def _bulk_field(self, field: str) -> None:
        ids = self._selected_ids()
        if not ids or self.mode != "standard":
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
            self.preview.labelChanged.connect(self._preview_label)
            self.preview.excludeRequested.connect(self._preview_include)
            self.preview.deleteRequested.connect(self._preview_delete)
            self.preview.rotateRequested.connect(self._preview_rotate)
            self.preview.splitRequested.connect(self._preview_split)
            self.preview.cropChanged.connect(self._preview_crop)
            self.preview.navigate.connect(self._preview_navigate)
        # Set before the row is shown: it decides whether the Section control
        # is the heading picker or the board's sentiment control, and showing
        # the row is what reads it.
        self.preview.for_board = model is getattr(self, "board_model", None)
        at, walk = self._preview_place(clip_id)
        # The counter must count what is on screen. With a filter on it used to
        # read "3 / 40" while the list showed nine.
        position = (at + 1) if at is not None else 0
        self.preview.show_row(row, position, len(walk))
        self.preview.show()
        self.preview.raise_()
        self.preview.activateWindow()

    def _refresh_preview(self, clip_id: int) -> None:
        row = self._preview_pool().row_for(clip_id)
        if self.preview and self.preview.isVisible() and row is not None:
            at, walk = self._preview_place(clip_id)
            self.preview.show_row(
                row, (at + 1) if at is not None else 0, len(walk))

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
        stack = self.stack_for(pool)
        stack.beginMacro("Section heading")
        stack.push(commands.EditField(pool, clip_id, "section_key", key))
        stack.push(commands.EditField(pool, clip_id, "section_title", words))
        stack.endMacro()
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
        self._preview_stack().push(
            commands.EditField(self._preview_pool(), clip_id, field, value))

    def _preview_stack(self):
        """The history of the screen the previewed clipping belongs to.

        Ctrl+Z undoes on the screen being looked at. A board card's edit made
        here and put on the report's history was skipped by Ctrl+Z on the
        board, which undid the step before it instead, and undoing it later
        from the report reached into the board's list.
        """
        return self.stack_for(self._preview_pool())

    def _preview_label(self, clip_id: int, text: str) -> None:
        """A headline typed in the preview, for whichever screen it belongs to.
        A board card's used to go to the press report's handler, which could
        not find it there and dropped it without a word."""
        if self._preview_pool() is getattr(self, "board_model", None):
            self._on_board_title(clip_id, text)
        else:
            self._on_label_edited(clip_id, text)

    def _preview_include(self, clip_id: int, included: bool) -> None:
        self._preview_stack().push(
            commands.SetIncluded(self._preview_pool(), [clip_id], included))
        self._refresh_preview(clip_id)

    def _preview_delete(self, clip_id: int) -> None:
        if not self._confirm_delete(1):
            return
        position = self._preview_pool().position_of(clip_id)
        self._preview_stack().push(commands.RemoveClips(self._preview_pool(), [clip_id]))
        if self._preview_pool().rows:
            following = self._preview_pool().rows[min(position, len(self._preview_pool().rows) - 1)]
            self._refresh_preview(following.id)
        elif self.preview:
            self.preview.close()

    def _preview_crop(self, clip_id: int, crop) -> None:
        """A trim dragged out in the full-size view, or put back.

        One undo step on the history of the screen the clipping belongs to.
        The picture keeps all its pixels: what is stored is the rectangle to
        show, so Ctrl+Z gives the edges back exactly.
        """
        pool = self._preview_pool()
        clip = pool.by_id(clip_id) if pool.row_for(clip_id) is not None else None
        if clip is None or crop == clip.crop:
            return
        whole = getattr(crop, "is_identity", False)
        self._preview_stack().push(commands.SetCrop(
            pool, clip_id, crop, "Trim put back" if whole else "Trimmed"))
        if pool is getattr(self, "board_model", None):
            self._refresh_board()
        self.list.refresh_height()
        self._refresh_preview(clip_id)
        self._flash("Trim put back — the whole picture again." if whole else
                    "Trimmed — Ctrl+Z puts the edges back.", "good")

    def _preview_rotate(self, clip_id: int) -> None:
        self._preview_stack().push(commands.Rotate(self._preview_pool(), [clip_id]))
        self._refresh_preview(clip_id)

    def _preview_split(self, clip_id: int) -> None:
        at, _walk = self._preview_place(clip_id)
        self._preview_stack().push(commands.Split(self._preview_pool(), clip_id))
        walk = self._preview_walk()
        if at is not None and 0 <= at < len(walk):
            self._refresh_preview(walk[at].id)

    def _preview_walk(self) -> list:
        """The rows the arrows should walk: what is on screen, in that order.

        The lens is a view projection and never rewrites `model.rows`, because
        that list IS the export order. So the list on screen and the list the
        preview was walking were two different things, and with a filter on the
        arrows wandered off through clippings nobody could see.
        """
        pool = self._preview_pool()
        shown = pool.visible_rows() if hasattr(pool, "visible_rows") else None
        return list(shown) if shown else list(pool.rows)

    def _preview_place(self, row_id: int):
        """Where this clipping sits in the walk, or None if it is filtered out."""
        walk = self._preview_walk()
        for index, row in enumerate(walk):
            if row.id == row_id:
                return index, walk
        return None, walk

    def _preview_navigate(self, step: int) -> None:
        if self.preview is None or self.preview.row is None:
            return
        at, walk = self._preview_place(self.preview.row.id)
        if at is None:
            # Opened on a clipping the filter hides - from the board, or because
            # the lens changed while this window was open. Stepping from it has
            # no meaning, so go to whichever end the arrow points at rather than
            # doing nothing and looking broken.
            if not walk:
                return
            self._refresh_preview(walk[0 if step > 0 else -1].id)
            return
        position = at + step
        if 0 <= position < len(walk):
            self._refresh_preview(walk[position].id)

    # ------------------------------------------------------- context menu
    def _send_to_board(self, clip_ids: list) -> None:
        """Move clippings from the press report over to the sentiment board."""
        ids = [i for i in clip_ids if self.model.row_for(i) is not None]
        if not ids:
            return
        # The send lives on the report's history; the board's own history is
        # cleared whenever clippings cross, because its snapshots of the board
        # stop being true. See MoveToInterface.
        self.undo_stack.push(
            commands.MoveToInterface(
                self.model, self.board_model, ids,
                f"{len(ids)} sent to the sentiment board" if len(ids) != 1
                else "Clipping sent to the sentiment board",
                forget=self.board_undo.clear,
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
        # Apart from the send above it, so a slip of the mouse cannot take
        # clippings out of the report when they were only meant to change file.
        if len(self.model.file_runs()) > 1:
            move = menu.addMenu("Move to")
            move.setToolTipsVisible(True)
            self._fill_move_menu(move, ids)
        menu.addSeparator()
        # The same rule as the bar's button. This used to push "included" for
        # any group of clippings, so "Exclude these 3" put them back in.
        back = self._all_excluded(ids)
        if many:
            label = (f"Include these {len(ids)} again" if back
                     else f"Exclude these {len(ids)}")
        else:
            label = "Include again" if back else "Exclude"
        menu.addAction(QAction(label, self,
                               triggered=lambda: self._toggle_included(ids)))
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
        self._hide_move_note()
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
        collector = getattr(self, "collector", None)
        if collector is not None:
            collector.refresh()          # the bar names where photos now go
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
        self._sync_exclude_button()
        # Somewhere else to go only when there is more than one file.
        self.batch_move_to.setVisible(count > 0 and len(self.model.file_runs()) > 1)
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
        else:
            self.select_hint.setText(
                "Hold Ctrl to pick several, Shift for a run, or drag the handle to "
                "move a block anywhere"
            )
        # The bar acts on the press report's ticks, so it is shown only there.
        # On the board it used to come back whenever anything recounted, with
        # an Exclude that changed clippings nobody could see.
        if count and self.mode == "standard":
            self.batch.adjustSize()
            self.batch.show()
            self.batch.raise_()
            self._place_floating()
        else:
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
            self._hide_status_later(self.board.status)
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
        self._hide_status_later(self.status)

    #: How long a message stays up once nothing new has replaced it.
    QUIET_FOR = 9000

    def _hide_status_later(self, strip) -> None:
        """Take the message down nine seconds after the LAST one, not each one.

        This used to be `QTimer.singleShot(9000, strip.hide)`, once per message.
        A one-shot timer cannot be cancelled, so a run that reports progress -
        the duplicate check reports every few clippings - stacked up a hundred
        of them. Each fired nine seconds after its own message and hid a line
        that a later message had just put up, and the strip blinked on and off
        for the whole run.

        One timer, restarted. While messages keep arriving it never fires; nine
        seconds after they stop, the strip comes down once.
        """
        timer = getattr(self, "_status_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            self._status_timer = timer
        else:
            timer.stop()
            try:
                timer.timeout.disconnect()
            except (RuntimeError, TypeError):
                pass
        timer.timeout.connect(strip.hide)
        timer.start(self.QUIET_FOR)

    def _report(self, problems: list[str]) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Some things could not be imported")
        box.setText(
            f"{len(problems)} problem(s). Everything else was imported normally."
        )
        box.setDetailedText("\n\n".join(problems))
        box.exec()

    @_pumps
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
            name_suffix=self._export_suffix(),
        )
        if dialog.exec() and dialog.results:
            names = ", ".join(Path(p).name for p in dialog.results)
            self._flash(f"Built {names}.", "good")
            # The brief: undo history clears on export, not on import.
            self.undo_stack.clear()   # the report's history only

    def _export_suffix(self) -> str:
        """What a file's name carries to say which newspad it came from.

        Nothing for Newspad 1, so the files a morning has always produced keep
        exactly the names they have always had. Two newspads exporting on the
        same day would otherwise suggest the same name, and the second would
        replace the first.
        """
        return "" if self.newspad == 1 else f" - Newspad {self.newspad}"

    def _division_tag(self) -> str:
        """How a division is written on a file: "Lucknow(LKO)".

        Both sentiment exports carry it, and they have to agree - a folder of
        pictures and the report they came from are filed next to each other.
        """
        division = self.board.active_division()
        if division is None:
            return "All Divisions"
        return f"{division.name}({division.code})"

    @_pumps
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

        folder = Path(chosen) / (build_jpeg.folder_name(self._division_tag(), stamp)
                                 + self._export_suffix())
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
                f"{stamp.strftime('%d.%m.%Y')}{tail}{self._export_suffix()}")

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
    def recheck_duplicates(self, force: bool = False) -> None:
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
        # force: a check that was already under way when this newspad was
        # switched away from. It was asked for, so it finishes, whether or not
        # checking automatically is switched on.
        if not self._auto_duplicates and not force:
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
        if self._switching:
            return          # the restore at the end of the switch asks again
        if self._still_winding_down():
            # A pass stopped by a switch has not let go of its thread yet. Two
            # at once raised the window's worst pause to 338ms, measured - so
            # wait for it, and try again in a moment.
            if self._duplicate_timer is not None:
                self._duplicate_timer.start(DUPLICATE_SETTLE_MS)
            return
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
            self._start_pass(unprinted, self._prints_taken,
                             read_headlines=False)
            return
        self._read_the_shortlist()

    def _start_pass(self, work, on_finished, **options) -> None:
        """Start a background pass whose answers are dropped if it is settled.

        Every pass is stamped with the generation it started in. A newspad
        switch settles the pass and bumps the generation, so when the pass's
        answer does arrive - it is queued, and arrives after the switch - it is
        recognised as belonging to a newspad no longer in the window and
        ignored. Measured without this: the late answer ran its follow-on step
        against the NEW newspad, a 3062ms block, and wiped its flags.
        """
        gen = self._pass_gen

        def progress(done, total, gen=gen):
            if gen == self._pass_gen:
                self._duplicate_progress(done, total)

        def finished(results, gen=gen):
            if gen == self._pass_gen:
                on_finished(results)

        self._reader_thread, self._reader = reader.start(
            work, progress, finished, self, **options)

    def _still_winding_down(self) -> bool:
        """Whether a pass stopped by a switch still holds its thread."""
        alive = []
        for thread in self._winding_down:
            try:
                if thread.isRunning():
                    alive.append(thread)
            except RuntimeError:        # the thread object is already gone
                continue
        self._winding_down = alive
        return bool(alive)

    def _copy_back(self, results, headlines: bool) -> None:
        """Put what a pass measured - and, if it read them, the headlines -
        back onto the clippings in the window.

        Only when there is something to put: an empty measurement is silence,
        not an answer, and writing it over a clipping would wipe a reading
        taken earlier in the morning.
        """
        by_uid = {row.clip.uid: row.clip for row in self.model.rows
                  if row.clip is not None}
        for got in results or ():
            clip = by_uid.get(got.uid)
            if clip is None:
                continue        # deleted while we were reading; nothing to do
            if headlines:
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
        self._copy_back(results, headlines=False)
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
        self._start_pass(unread, self._duplicate_readings, measure=False)

    def _work_begin(self, said: str, total: int) -> None:
        """Put the bar up for a job whose size is known."""
        bar = getattr(self, "work_bar", None)
        if bar is None:
            return
        bar.setRange(0, max(1, total))
        bar.setValue(0)
        bar.show()
        self._flash(said, "info")

    def _work_end(self) -> None:
        """Take it down. Called on every way out, including the unhappy ones."""
        bar = getattr(self, "work_bar", None)
        if bar is not None:
            bar.hide()
        self._last_progress = ""

    def _duplicate_progress(self, done: int, total: int) -> None:
        # Quietly, in the card that is already there. No dialog: the user did
        # not ask for this and should not have to dismiss it.
        bar = getattr(self, "work_bar", None)
        if bar is not None:
            if bar.maximum() != max(1, total):
                bar.setRange(0, max(1, total))
            if not bar.isVisible():
                bar.show()
            # The bar itself is cheap and can take every step, so it moves
            # smoothly rather than in jumps of eight.
            bar.setValue(done)

        # The SENTENCE is throttled, not the bar. The reader says how far it has
        # got several times a second, and rewriting a wrapping label that often
        # cost 1628 rewrites and 716ms of the window's own thread in one check -
        # to say the same sentence over and over.
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
        self._copy_back(results, headlines=True)
        self._duplicates_running = False
        self._finish_duplicate_check(results)

    def _finish_duplicate_check(self, results) -> None:
        """Compare everything and say what was found. Fast: no reading here."""
        # FIRST, before the guard below. A bar left up after the window has
        # started closing is a bar that never comes down.
        self._work_end()
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
        if getattr(self, "_recheck_out_loud", False) and (
                results or self._answer_even_if_nothing_read):
            self._recheck_out_loud = False
            self._answer_even_if_nothing_read = False
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
        # Files holding a clipping moved in from somewhere else ("Move to") that
        # is not itself a repeat. Marked red, their one-click delete would take
        # that clipping with them - the same reason the loose bracket is never
        # marked, below.
        foreign = set()
        for row in self.model.rows:
            if row.clip is None:
                continue
            where[row.clip.uid] = row.group_key
            titles.setdefault(row.group_key,
                              row.home_title or row.source_name or row.group_key)
            if (row.home_title and row.home_title != row.source_name
                    and not row.clip.duplicate_of):
                foreign.add(row.group_key)
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
            and key not in foreign
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

        if self._duplicates_running or self._still_winding_down():
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

    # ------------------------------------------------------------ newspads
    def _mark_what_is_whose(self) -> None:
        """Say, where it is typed, which values belong to this newspad alone.

        The two covers' design is this newspad's own too, but it is set once
        rather than every morning, so it is said once, on the press cover's
        header, rather than on every control. A tooltip added to, never
        written over: the date pickers already explain why a future day is
        refused, and that must stay.
        """
        note = getattr(self.cover, "saved_note", None)
        if note is not None:
            note.setToolTip(
                "Each newspad keeps its own cover pages and headline style. A "
                "newspad opened for the first time starts with a copy of the "
                "one you were in; after that, changes stay in that newspad.")
        own = "This newspad's own - each newspad keeps its own."
        cover, dossier = self.cover, self.board.cover
        for widget in (getattr(cover, "date_edit", None),
                       getattr(cover, "date_mirror", None),
                       getattr(dossier, "date_edit", None),
                       getattr(dossier, "date_text", None),
                       getattr(dossier, "count_text", None),
                       getattr(dossier, "division_edit", None),
                       getattr(dossier, "prepared_edit", None)):
            if widget is None:
                continue
            said = widget.toolTip()
            widget.setToolTip(f"{said}\n\n{own}" if said else own)

    def _toggle_collect(self, checked: bool) -> None:
        if checked:
            self.collector.start()
        else:
            self.collector.stop()
        self._sync_collect_button()

    def _sync_collect_button(self) -> None:
        """The button says what Collect is doing, and cannot start it in a
        newspad that cannot save."""
        button = getattr(self, "collect_btn", None)
        collector = getattr(self, "collector", None)
        if button is None or collector is None:
            return
        on = collector.is_on
        was = button.blockSignals(True)
        try:
            button.setChecked(on)
        finally:
            button.blockSignals(was)
        button.setText(collect.LABEL_ON if on else collect.LABEL_OFF)
        button.setEnabled(not self._read_only)
        button.setToolTip(collect.TIP_READ_ONLY if self._read_only
                          else collect.TIP_ON if on else collect.TIP_OFF)

    def _sync_newspad_button(self) -> None:
        button = getattr(self, "newspad_btn", None)
        if button is None:
            return
        button.setText(f"Newspad {self.newspad} ▾")
        button.setEnabled(self._pumping == 0 and not self._switching)

    def _fill_newspad_menu(self) -> None:
        """Built each time it opens, so the counts are the counts now."""
        menu = self.newspad_menu
        menu.clear()
        for number in range(1, newspads.COUNT + 1):
            if number == self.newspad:
                count = len(self.model.rows) + len(self.board_model.rows)
                said = newspads.describe(number, count) + "  (open)"
            else:
                # Read off its manifest by path. Never by building a store,
                # which would create the folder just by looking.
                seen = newspads.summary(number)
                if seen:
                    said = newspads.describe(number, *seen)
                elif (newspads.folder(number) / "session.json").exists():
                    # Saved work that will not read. Never "empty": that
                    # would invite somebody to use it for a fresh morning.
                    said = f"Newspad {number} — could not be read"
                else:
                    said = newspads.describe(number, 0)
            action = menu.addAction(said)
            action.setCheckable(True)
            action.setChecked(number == self.newspad)
            action.triggered.connect(
                lambda _on=False, n=number: self.switch_newspad(n))
        menu.addSeparator()
        share = menu.addAction("What the four newspads share…")
        share.triggered.connect(self._show_what_is_shared)

    def _show_what_is_shared(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("What the four newspads share")
        box.setIcon(QMessageBox.Information)
        box.setText(newspads.WHAT_IS_SHARED)
        box.setAttribute(Qt.WA_DeleteOnClose)
        # open(), never exec(): nothing here should hold up the window.
        box.open()

    def _build_read_only_banner(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("ReadOnlyBanner")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        bar.setStyleSheet(
            f"#ReadOnlyBanner {{ background: {theme.FLAG_WASH};"
            f" border: 1px solid {theme.ORANGE_INK}; border-radius: 10px; }}"
            f"#ReadOnlyBanner QLabel {{ color: {theme.INK};"
            f" background: transparent; }}")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 9, 10, 9)
        row.setSpacing(12)
        self.read_only_text = QLabel()
        self.read_only_text.setWordWrap(True)
        row.addWidget(self.read_only_text, 1)
        button = QPushButton("Set it aside and start empty")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(self._set_aside_unreadable)
        row.addWidget(button)
        self.read_only_button = button
        bar.hide()
        self.read_only_banner = bar
        return bar

    def _show_read_only(self, on: bool, stuck: bool = False) -> None:
        """The note above the lists while this newspad saves nothing.

        ``stuck`` is the one case with nothing to set aside: a switch went wrong
        part-way and the window can no longer be trusted to match any folder.
        """
        collector = getattr(self, "collector", None)
        if on and collector is not None:
            collector.stop("read-only")
        banner = getattr(self, "read_only_banner", None)
        if banner is None:
            return
        if on and stuck:
            self.read_only_text.setText(
                "Something went wrong while changing newspads. Your work was "
                "saved just before it. Close the program and open it again to "
                "carry on - nothing is saved until then.")
        elif on:
            self.read_only_text.setText(
                f"Newspad {self.newspad}'s saved work could not be read. "
                f"Nothing is saved in this newspad until it is set aside - "
                f"the old files are kept, renamed, not deleted.")
        self.read_only_button.setVisible(on and not stuck)
        banner.setVisible(on)
        self._sync_collect_button()

    def _set_aside_unreadable(self) -> None:
        """Rename the unreadable folder out of the way, and start this newspad
        empty. Renamed, never deleted: whatever is in it may still be rescued."""
        folder = newspads.folder(self.newspad)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        aside = folder.with_name(f"{folder.name}.unreadable-{stamp}")
        try:
            os.replace(folder, aside)
        except OSError as error:
            self._flash(f"Could not set it aside: {error}", "bad")
            return
        self.store = SessionStore(newspads.folder(self.newspad))
        self._read_only = False
        self._show_read_only(False)
        if self.model.rows or self.board_model.rows:
            # What could be read is still in the window; from now on it is
            # saved, into the fresh folder.
            said = "what could be read is kept and saved from now on"
            self.touch_session()
        else:
            said = f"Newspad {self.newspad} is empty and saves normally"
        self._flash(f"The old work was kept as {aside.name}; {said}.", "info")

    def switch_newspad(self, number: int) -> bool:
        """Put this newspad away and open another. Synchronous, and in order.

        1. Commit any headline being typed and hide the preview, so late edits
           land in the newspad they were made in.
        2. Settle the duplicate check: stop it, keep whatever it had read,
           remember it was under way.
        3. Save this newspad STRICTLY. If that fails, nothing else happens -
           the switch is refused and this newspad stays open.
        4. Record which newspad is open, for the next launch.
        5. Empty the window: undo, filters, selection, both lists.
        6. Point the window at the other newspad's own folder.
        7. Load it through the same restore the program has always used.

        Nothing between 5 and 7 processes events, except the question about
        work left from an earlier day, and while that is up every save and
        every check is held off. So no timer can ever pair one newspad's lists
        with another newspad's folder.
        """
        if (number == self.newspad or self._switching or self._pumping
                or not 1 <= int(number) <= newspads.COUNT):
            return False
        outgoing = self.newspad
        # Collect never follows a switch: what is copied next belongs to
        # whichever newspad the person chooses to collect into.
        was_collecting = self.collector.is_on
        dropped_copies = self.collector.stop("newspad")
        dialog = getattr(self, "links_dialog", None)
        if dialog is not None:
            dialog.close()
        self._hide_move_note()
        self._collect_note = ""
        if was_collecting:
            self._collect_note = collect.FLASH_SWITCH.format(n=number) + (
                collect.FLASH_DROPPED.format(k=dropped_copies)
                if dropped_copies else "")
        self._switching = True
        self._sync_newspad_button()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            # 1 ---------------------------------------------- commit and hide
            for commit in (self.list.commit_editor, self.board.commit_editors):
                try:
                    commit()
                except Exception:  # noqa: BLE001 - never block a switch on this
                    pass
            if self.preview is not None:
                try:
                    self.preview.hide()
                except RuntimeError:
                    pass
            self.preview_model = None

            # 2 ------------------------------------------- settle the check
            self._settle_reader()

            # 3 ----------------------------------------------------- save out
            # The covers and headline styles first, each into the outgoing
            # newspad's OWN files, while every panel still points there. Then
            # the clippings, strictly. Then - only if both are safe - a copy of
            # this look for a newspad that has none yet. Nothing has moved
            # until all three have worked; any of them failing refuses the
            # switch with nothing changed.
            self._save_timer.stop()
            self._arrival = None
            refusal = None
            forgive = self._design_refused == (outgoing, number)
            try:
                dropped = self._flush_designs(outgoing, forgive=forgive)
            except Exception:  # noqa: BLE001 - refuse, and say how to go on
                self._design_refused = (outgoing, number)
                refusal = (f"Newspad {outgoing}'s cover page or headline "
                           f"settings could not be saved, so it stayed open. "
                           f"Switch again to leave without that last change.")
            else:
                self._design_refused = None
                if dropped:
                    self._design_notes.append(
                        f"The last change to Newspad {outgoing}'s "
                        f"{', '.join(dropped)} could not be saved and was left "
                        f"behind.")
            if refusal is None and not self._read_only:
                try:
                    self.save_session(strict=True)
                except Exception:  # noqa: BLE001 - refuse rather than lose it
                    refusal = (f"Newspad {outgoing} could not be saved, so it "
                               f"stayed open.")
            seeded = False
            if refusal is None:
                try:
                    seeded = self._seed_designs(outgoing, number)
                except Exception:  # noqa: BLE001
                    refusal = (f"Newspad {number}'s cover pages could not be set "
                               f"up, so Newspad {outgoing} stayed open.")
            if refusal is not None:
                # The cursor goes back in the finally below, once.
                self._switching = False
                self._sync_newspad_button()
                self._design_notes = []
                self._collect_note = ""
                self._flash(refusal, "bad")
                self.touch_session()
                if self._check_pending:
                    self._check_pending = ""
                    self.recheck_duplicates(force=True)
                return False

            try:
                # 4 -------------------------------------------------- pointer
                try:
                    newspads.remember(number)
                except OSError:
                    pass      # costs only which newspad the next launch opens

                # 5 --------------------------------------------------- empty it
                self._clear_for_switch()

                # 6 -------------------------------------------------- new store
                self.newspad = int(number)
                self.store = SessionStore(newspads.folder(self.newspad))
                self._read_only = False
                self._stuck = False
                self._show_read_only(False)
                self._check_pending = ""

                # 6b ------------------------------------------- its own look
                # Before the restore, whose earlier-day question is the one
                # event loop in a switch: by then every panel points at, and
                # shows, the incoming newspad's look, and no panel save is armed.
                self._adopt_designs(self.newspad, seed=True, back_to=outgoing)

                # 7 ----------------------------------------------------- load
                ask = self.newspad not in self._opened
                self.restore_session(ask=ask, arriving=True)
                # Only once it has worked. Added before, a first open that
                # failed would skip the earlier-day question the next time.
                self._opened.add(self.newspad)
                switched = True
            except Exception:  # noqa: BLE001 - never leave it half switched
                self._back_to(outgoing, number)
                switched = False
        finally:
            self._switching = False
            QApplication.restoreOverrideCursor()
        self._after_switch(seeded_from=outgoing if (switched and seeded) else None)
        return switched

    # ------------------------------------------------ each newspad's look
    def _design_cards(self) -> list:
        """The four panels that make a newspad's look."""
        board = getattr(self, "board", None)
        return [card for card in (
            getattr(self, "cover", None), getattr(board, "cover", None),
            getattr(self, "heading", None), getattr(board, "heading", None))
            if card is not None]

    @staticmethod
    def _design_label(card) -> str:
        return {"cover.json": "press cover page",
                "sentiment_cover.json": "dossier cover page",
                "heading_standard.json": "press headline style",
                "heading_sentiment.json": "dossier headline style",
                }.get(card.design_name, "design")

    def _flush_designs(self, outgoing: int, forgive: bool = False) -> list:
        """Write every panel's pending edit into the OUTGOING newspad's files.

        Returns the panels whose change had to be left behind - only ever when
        ``forgive`` is set, which is the second time somebody asks for the same
        switch after being told the first one could not save.
        """
        dropped = []
        for card in self._design_cards():
            if card.design_file() != card.file_for(outgoing):
                # Only reachable after a switch that went wrong part-way: a
                # panel pointing at another newspad's file must write nothing.
                card.hold()
                continue
            try:
                card.flush(strict=True)
                # A newspad 2-4 panel with no file yet gets one now, so that
                # "missing" keeps meaning "never had a look of its own".
                if (outgoing != 1 and card.trusted
                        and not card.design_file().exists()):
                    card.save(strict=True)
            except Exception:
                if not forgive:
                    raise
                card.drop_pending()
                dropped.append(self._design_label(card))
        return dropped

    def _seed_designs(self, outgoing: int, number: int) -> bool:
        """Give a newspad seen for the first time a copy of the look on screen.

        Only files that are not there - an existing file is that newspad's own,
        whatever it holds. Only a look that can be trusted: a panel showing the
        defaults because its own file would not read is never copied, or a
        newspad would inherit "DAILY PRESS CLIPPINGS REPORT" for good. Then the
        outgoing newspad's file itself is copied, if IT reads; otherwise
        nothing is. Returns whether anything was copied.
        """
        if number == 1:
            return False
        wrote = False
        for card in self._design_cards():
            target = card.file_for(number)
            if target.exists():
                continue
            if card.trusted:
                card.save(strict=True, to=target)
                wrote = True
                continue
            try:
                data = json.loads(card.file_for(outgoing).read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - nothing trustworthy to copy
                continue
            if not isinstance(data, dict):
                continue
            if card.design_name == "sentiment_cover.json":
                for key in MORNING:
                    data.pop(key, None)
            newspads.write_design(target, json.dumps(data, indent=2,
                                                     ensure_ascii=False))
            wrote = True
        return wrote

    def _adopt_designs(self, number: int, seed: bool, back_to=None) -> None:
        """Point all four panels at a newspad's files, and show them.

        If any panel fails, they are all pointed back at ``back_to`` before the
        error goes on, so the rollback starts from panels that agree with each
        other - never some on one newspad's files and some on another's.
        """
        cards = self._design_cards()
        try:
            for card in cards:
                card.adopt(card.file_for(number), seed=seed and number != 1)
        except Exception:
            if back_to is not None:
                for card in cards:
                    try:
                        card.adopt(card.file_for(back_to), seed=False)
                    except Exception:  # noqa: BLE001
                        card.hold()
            raise
        finally:
            # The board's "cover" tick follows the dossier card only when it
            # is edited, and a load is not an edit.
            mirror = getattr(self.board, "_mirror_cover_switch", None)
            if callable(mirror):
                try:
                    mirror()
                except Exception:  # noqa: BLE001
                    pass
        for card in cards:
            if getattr(card, "_unreadable", False):
                self._design_notes.append(
                    f"Newspad {number}'s {self._design_label(card)} could not "
                    f"be read, so it shows its defaults; the file is kept and "
                    f"is only set aside if you change it.")

    def _point_designs_at_launch(self) -> None:
        """At launch the panels were built reading Newspad 1's files. If the
        program opens on another newspad, point them at its own before anything
        can be edited. A failure never stops the program opening: the panels
        that are not on the right files are held, and it says so."""
        if self.newspad == 1:
            for card in self._design_cards():
                if getattr(card, "_unreadable", False):
                    self._design_notes.append(
                        f"Newspad 1's {self._design_label(card)} could not be "
                        f"read, so it shows its defaults; the file is kept and "
                        f"is only set aside if you change it.")
            return
        try:
            self._adopt_designs(self.newspad, seed=True)
        except Exception:  # noqa: BLE001 - the program must still open
            for card in self._design_cards():
                if card.design_file() != card.file_for(self.newspad):
                    card.hold()
            self._design_notes.append(
                f"Newspad {self.newspad}'s cover pages could not be opened, so "
                f"changes to them are not being saved. Close the program and "
                f"open it again.")

    def _design_problem(self, message: str) -> None:
        """A panel could not write its file while somebody was working."""
        if self._switching:
            self._design_notes.append(message)
        else:
            self._flash(message, "bad")

    def _arrive(self, note: str, kind: str) -> None:
        """Say what a restore brought back - now, or with the rest of a switch."""
        if self._switching:
            self._arrival = (note, kind)
            return
        if self._design_notes:
            notes, self._design_notes = self._design_notes, []
            note = " ".join([note, *notes])
            kind = "bad"
        self._flash(note, kind)

    def designs_before_restore(self) -> None:
        """A saved setup is about to be put back: write what is pending first."""
        for card in self._design_cards():
            try:
                card.flush()
            except Exception:  # noqa: BLE001 - the restore replaces it anyway
                pass

    def designs_after_restore(self, restored_names=None) -> None:
        """Show what a saved setup just put back - never write over it."""
        wanted = set(restored_names or [])
        for card in self._design_cards():
            key = newspads.design_key(self.newspad, card.design_name)
            if wanted and key not in wanted:
                continue
            try:
                card.reload()
            except Exception:  # noqa: BLE001
                card.hold()
        mirror = getattr(self.board, "_mirror_cover_switch", None)
        if callable(mirror):
            mirror()

    def _back_to(self, outgoing: int, wanted: int) -> None:
        """A switch failed after the outgoing newspad was safely saved.

        The window may be half emptied by now, and a half-emptied window must
        never be saved - the tidy-up after a save deletes every picture the
        manifest no longer names. So the newspad that was open is put back, from
        the save made a moment ago. If even that fails, nothing more is saved
        at all until the program is opened again.
        """
        try:
            newspads.remember(outgoing)
        except OSError:
            pass
        try:
            # The panels first: they may already point at the other newspad's
            # files, and must never save the outgoing look into them.
            self._adopt_designs(outgoing, seed=False)
            self._clear_for_switch()
            self.newspad = outgoing
            self.store = SessionStore(newspads.folder(outgoing))
            self._read_only = False
            self._show_read_only(False)
            self.restore_session(ask=False, arriving=True)
            self._arrival = (f"Newspad {wanted} could not be opened, so Newspad "
                             f"{outgoing} stayed open.", "bad")
        except Exception:  # noqa: BLE001
            for card in self._design_cards():
                card.hold()
            self._read_only = True
            self._stuck = True
            self._show_read_only(True, stuck=True)

    def _settle_reader(self) -> None:
        """Stop a duplicate check that is under way, keeping what it read.

        The pass is stopped and waited for (half a second, measured), and its
        readings are copied onto this newspad's clippings before they leave the
        window - so coming back later reads only what was not reached, rather
        than starting again. Its late answer, when it arrives, is ignored: the
        generation it belongs to is over.
        """
        pending = ""
        timer = self._duplicate_timer
        if timer is not None and timer.isActive():
            timer.stop()
            pending = "quiet"
        if self._duplicates_running:
            pending = "quiet"
            self._pass_gen += 1
            worker, thread = self._reader, self._reader_thread
            headlines = bool(getattr(worker, "_read_headlines", False))
            try:
                worker.stop()
            except Exception:  # noqa: BLE001 - it may already be finished
                pass
            finished = False
            try:
                finished = bool(thread.wait(3000))
            except (RuntimeError, AttributeError):
                finished = True
            if finished:
                self._copy_back(getattr(worker, "kept", []) or [], headlines)
            elif thread is not None:
                self._winding_down.append(thread)
            self._duplicates_running = False
        if getattr(self, "_recheck_out_loud", False):
            pending = "loud"
            self._recheck_out_loud = False
        self._work_end()
        self._check_pending = pending

    def _clear_for_switch(self) -> None:
        """Empty the window of one newspad before the next is loaded into it.

        Cleared, never replaced: the undo stacks and the models are the same
        objects throughout, so the shortcuts and the list keep the wiring they
        were built with.
        """
        self._newspad_gen += 1
        self.undo_stack.clear()
        self.board_undo.clear()
        bar = getattr(self, "filter_bar", None)
        if bar is not None:
            was = bar.blockSignals(True)
            try:
                bar.clear()
            finally:
                bar.blockSignals(was)
        for pool in (self.model, self.board_model):
            pool.reset_view()
            pool.replace_all([])
        self._duplicate_pairs = []
        self._duplicate_hints = []
        self.model.duplicate_files = {}
        self.duplicates_btn.setVisible(False)
        # After the stacks are cleared: clearing them stirs _after_undo_change,
        # which re-arms this very timer.
        if self._duplicate_timer is not None:
            self._duplicate_timer.stop()
        self.board.reset_view()
        if getattr(self.board, "divisions", None):
            self.board.select_division(self.board.divisions[0].code)
        for glide in self.findChildren(scroll.SmoothWheel):
            try:
                glide.halt()
            except Exception:  # noqa: BLE001
                pass
        self._last_clicked_id = None
        self._refresh_board()
        self._update_counts()

    def _after_switch(self, seeded_from=None) -> None:
        """One message for the whole switch.

        What the restore said comes first and keeps its warnings; the note
        about a copied look and anything a panel could not do are added to it,
        never put in its place - the status strip shows only the last message.
        """
        self.setWindowTitle(self._title())
        self._sync_newspad_button()
        # The strip, if it is open, offers what is in THIS newspad's list.
        self._refresh_filter_choices()
        self.list.refresh_height()
        arrival, self._arrival = self._arrival, None
        notes, self._design_notes = self._design_notes, []
        n = self.newspad
        empty = (not self._read_only and not self.model.rows
                 and not self.board_model.rows)
        parts, kind = [], "info"
        if arrival is not None:
            parts.append(arrival[0])
            kind = arrival[1]
        elif empty:
            parts.append(f"Newspad {n} is empty.")
        if seeded_from is not None:
            parts.append(f"Its cover pages and headline style start as a copy "
                         f"of Newspad {seeded_from}'s - changes made here stay "
                         f"in Newspad {n}.")
        elif empty and arrival is None:
            parts.append("Its cover pages and headline style are its own; "
                         "sections, the newspaper list, the word list and "
                         "duplicate learning are shared by all four newspads.")
        if notes:
            parts.extend(notes)
            kind = "bad"
        if self._collect_note:
            parts.append(self._collect_note.replace(
                f"Newspad {n} is open. ", "", 1) if parts else self._collect_note)
            self._collect_note = ""
        if parts:
            self._flash(" ".join(parts), kind)

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
            "   " + (", ".join(dict.fromkeys(said for _n, said, _s in here))
                     if here else "nothing set up yet"),
            f"   kept in {backup._folder()}",
            "   That folder is not inside the program's own folder, so "
            "updating the program never touches it. There is nothing you "
            "need to do.",
            "",
            "THE FOUR NEWSPADS - each one's clippings, cover pages and "
            "headline style",
        ]
        for number in range(1, newspads.COUNT + 1):
            place = newspads.folder(number)
            state = ("open now" if number == self.newspad
                     else "in use" if place.exists() else "not used yet")
            lines.append(f"   Newspad {number}: {place}  ({state})")
            look = newspads.design_folder(number)
            lines.append(
                f"      cover pages and headline style: {look}"
                if number == 1 or look.exists() else
                "      cover pages and headline style: copied from the newspad "
                "you are in, the first time it is opened")
        lines += [
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

    @_pumps
    def open_trainer(self) -> None:
        """Show pairs to judge, and write down what is decided about them."""
        from .trainer_dialog import TrainerDialog

        clips = [row.clip for row in self.model.rows if row.clip is not None]
        if len(clips) < 2:
            self._flash("Import some clippings first — the trainer compares "
                        "them against each other.", "info")
            return
        if self._duplicates_running or self._still_winding_down():
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
        collector = getattr(self, "collector", None)
        if collector is not None:
            collector.stop("closing")
        dialog = getattr(self, "links_dialog", None)
        if dialog is not None:
            dialog.close()
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

        # What a move did: where the bar was, or just above it when the bar is
        # still there because the move was refused and the ticks stayed.
        note = getattr(self, "move_note", None)
        if note is not None and note.isVisible():
            note.setFixedWidth(max(240, min(680, self.width() - 16)))
            note.adjustSize()
            x = max(8, (self.width() - note.width()) // 2)
            if self.batch.isVisible():
                y = self.batch.y() - note.height() - 8
            else:
                y = self.height() - footer - note.height() - 14
            note.move(x, y)
            note.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_floating()
