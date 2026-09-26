"""The application window.

Starts empty. Every morning brings different documents and different loose images,
so the tool opens ready to receive today's, by whichever route is nearest to hand:
a Word file, a PDF, a folder of photos, a drag from Explorer, or Ctrl+V straight out
of WhatsApp Web.
"""

from __future__ import annotations

import functools
import io
import itertools
import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import (QEvent, QPoint, QRectF, QSize, Qt, QTimer,
                            QUrl)
from PySide6.QtGui import (QImage, 
    QAction,
    QColor,
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
    QWidgetAction,
)

from ..core.assemble import (ExtractionError, detect_division, is_advisory,
                             load_config, looks_like_url)
from ..core.extract_docx import extract_docx
from ..core.extract_pdf import extract_pdf
from ..core import (copied, duplicates, links, newspads, ocr, paperlist,
                    sentiment, training, wordlist)
from ..core.models import Clip, Section
from ..core.profiles import NameIndex

#: Said after a paste that lost its phone bars, so the crop is no surprise.
TIDIED_NOTE = (" The phone's bars were trimmed off - Trim… then Whole picture "
               "puts them back.")
from .. import version
from ..core.session import SessionStore, decode_clip, encode_clip
from . import (collect, commands, datefield, dropped, export_dialog, findbar,
               icons, ocrfield, reader, theme, webclip, win_drop, zoom)
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
    Scope,
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


class HeaderIconButton(QPushButton):
    """A header button with one of our vector icons in place of words.

    Styled as the header's own buttons are (#HeaderButton) so it sits among
    them as one of them, and named for screen readers.
    """

    def __init__(self, drawer, name: str, parent=None, width: int = 40, height: int = 34):
        super().__init__(parent)
        self.drawer = drawer
        self.setObjectName("HeaderButton")
        self.setAccessibleName(name)
        self.setFixedSize(width, height)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        size = min(self.width(), self.height()) * 0.58
        box = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)
        self.drawer(painter, box, QColor("#FFFFFF"))
        painter.end()


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
        # With whatever somebody has added to the list, changed on it or taken
        # off it (Manage Newspaper List, on Collect's right-click menu).
        paperlist.apply(self.name_index)
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
        # The same for a category of the sentiment board opened out as a list,
        # which is checked over its own clippings and nothing else (see
        # _duplicate_clips). One background pass at a time serves both lists:
        # _duplicate_pool says whose it is, _duplicate_scope which category it
        # was started over, and a list asking while the other's pass is under
        # way waits in _duplicates_waiting rather than being forgotten.
        self._board_duplicate_pairs: list = []
        self._board_duplicate_hints: list = []
        self._board_duplicate_timer = None
        self._board_out_loud = False
        # Check for Duplicates starts from scratch, but only when that list's
        # own pass starts: True for the report, the Scope pressed over for the
        # board. See _run_duplicate_check.
        self._fresh_report = False
        self._fresh_board = None
        self._duplicate_pool = None
        self._duplicate_scope = None
        self._duplicates_waiting: set = set()
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
        # The dossier prints no section headings, so the board's pool has none
        # to show on a row or to refuse a move for (see ClipModel.headings_print).
        self.board_model.headings_print = False
        self.preview: PreviewDialog | None = None
        # The clipping to walk to next, when a priority has just moved
        # the one on show out from under the place in the list.
        # (the clipping the preview is on, the one that was below it when it
        # got there). See _remember_after.
        self._preview_at: tuple = (None, None)
        self._group_serial = itertools.count(1)
        self._last_clicked_id: int | None = None
        # The other end of a shift-click run in a board category's list. Its
        # own, so a run started in the press report never ends on the board.
        self._board_last_clicked_id: int | None = None
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
                    # A session from before arrival numbers existed brings
                    # every clipping back without one; given here, in the
                    # order they were saved in, so taking a priority off puts
                    # a clipping back where it was (commands.ensure_arrivals).
                    commands.ensure_arrivals(pool)

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
        # Built here because the strip below is laid out before the panel that
        # creates the rest of it, and this has to be in hand to be pinned.
        self.find_bar = findbar.FindBar()
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
        # The search field sits above the page and does not scroll with it -
        # see where it is built.
        standard_layout.addWidget(self.find_bar)
        standard_layout.addWidget(self.body_scroll, 1)
        self.list.hide()
        self.pages.addWidget(standard)

        self.board = SentimentBoard(self.config)
        # A category opened out is the press report's own list, shown over the
        # board's own pool - the same clippings its cards show, not a copy.
        self.board.focus_list.setModel(self.board_model)
        self._build_board_list_bar()
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
        # The menu, in the top left corner: the program's own things - its
        # settings and housekeeping, the Duplicates Trainer, the zoom, where its
        # files are kept. The top bar holds only what the morning's work uses
        # all the time (which newspad, which report, Collect); everything else
        # that used to share the bar with them is in here.
        self.menu_btn = HeaderIconButton(icons.menu_lines, "Menu")
        self.menu_btn.setToolTip("Menu - Settings, the Duplicates Trainer, zoom, "
                                 "and where your files are kept")
        self.menu_btn.setStyleSheet(
            "QPushButton::menu-indicator { image: none; width: 0px; }")
        self.main_menu = QMenu(self.menu_btn)
        self.main_menu.setToolTipsVisible(True)
        self.settings_action = self.main_menu.addAction("Settings…")
        self.settings_action.setToolTip(
            "Clean up: measure every clipping again for the duplicate check, "
            "empty the browser's saved pages, free memory and delete "
            "temporary files. Your clippings and settings are not touched.")
        self.settings_action.triggered.connect(self.open_settings)
        self.main_menu.addSeparator()
        self.trainer_action = self.main_menu.addAction("Duplicates Trainer…")
        self.trainer_action.setToolTip(
            "Teach it which cuttings are the same story and which are not.")
        self.trainer_action.triggered.connect(self.open_trainer)
        # THE OCR HEADLINE, ON OR OFF. A switch on a line of its own, green
        # when on and red when off, that stays open when pressed so the change
        # is seen. It hides the OCR box on every clipping and in the preview;
        # the duplicate check reads the pictures either way - see ocrfield.
        self.ocr_switch = ocrfield.SwitchRow("OCR headline", ocrfield.is_on())
        self.ocr_switch.toggled.connect(self._ocr_field_switched)
        self.ocr_switch_action = QWidgetAction(self.main_menu)
        self.ocr_switch_action.setDefaultWidget(self.ocr_switch)
        self.main_menu.addAction(self.ocr_switch_action)
        # How big everything is drawn. Each size asks first, then starts the
        # program again at it, as the zoom on the bar always did.
        self.zoom_menu = self.main_menu.addMenu("Zoom")
        self.main_menu.aboutToShow.connect(self._fill_zoom_menu)
        self._fill_zoom_menu()
        self.main_menu.addSeparator()
        self.kept_action = self.main_menu.addAction(
            "Runs offline - where your files are kept, and updates…")
        self.kept_action.setToolTip(
            "Every document is read on this machine. Nothing is uploaded, and "
            "nothing reaches the network unless you ask it to.")
        self.kept_action.triggered.connect(self.where_things_are_kept)
        self.menu_btn.setMenu(self.main_menu)
        top.addWidget(self.menu_btn, 0, Qt.AlignTop)
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
        # must scroll the page, never quietly switch somebody's newspad. No
        # caption beside it, nor beside the switch: each says what it is.
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
        self.collect_btn.setToolTip(collect.TIP_OFF + collect.TIP_MENU)
        self.collect_btn.clicked.connect(self._toggle_collect)
        # Right-click for Collect's options for the session. A popup, never
        # exec(): nothing waits on the menu, and copies made while it is open
        # are held and applied in order once it closes.
        self.collect_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self.collect_btn.customContextMenuRequested.connect(self._collect_menu)
        controls.addWidget(self.collect_btn)

        # Off the bar since 2.0.36 - the Duplicates Trainer, the zoom and Runs
        # offline are in the menu at the top left. The buttons are still made,
        # connected and named, because the rest of the window and its tests use
        # them, but they live in a holder that is never shown: nothing can put
        # one back on the header by showing it.
        self._parked = QWidget(content)
        self._parked.hide()

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
        self.trainer_btn.setParent(self._parked)

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
        self.zoom_buttons.setParent(self._parked)

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
        self.offline_note.setParent(self._parked)

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
    def _fill_zoom_menu(self) -> None:
        """The menu's Zoom: every size, the one in use ticked."""
        current = zoom.level()
        self.zoom_menu.clear()
        self.zoom_menu.setTitle(f"Zoom - {zoom.as_percent(current)}")
        for size in zoom.LEVELS:
            words = zoom.as_percent(size)
            if abs(size - zoom.NORMAL) < 0.001:
                words += "  (actual size)"
            action = self.zoom_menu.addAction(words)
            action.setCheckable(True)
            action.setChecked(abs(size - current) < 0.001)
            action.triggered.connect(lambda _on=False, s=size: self._zoom_to(s))

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
        self.heading.groupSocial.connect(lambda: self._group_social(self.model))
        layout.addWidget(self.heading)

        # FINDING ONE CLIPPING ON A PAGE OF A HUNDRED AND SIXTY. It only
        # finds: nothing is hidden, reordered or unticked, which is what the
        # Show and Arrange strip is for.
        #
        # PINNED ABOVE THE PAGE, not laid on it. On the page it scrolled away
        # with everything else, and its results - which hang off the window
        # rather than off the page - had to chase it down the screen and then
        # flip above it when they ran out of room, which read as a glitch.
        # Pinned, the field is always in the same place, the results always
        # hang downwards, and they have the whole window to fill.
        self.find_bar.serve(lambda: list(self.pool().rows),
                            lambda row_id: self.pool().number_of(row_id))
        self.find_bar.picked.connect(self._go_to_clip)
        self.find_bar.shiftWanted.connect(self._shift_found_to)
        self.find_bar.priorityWanted.connect(self._found_priority)
        self.find_bar.arrangeWanted.connect(self._found_arrange)
        self.find_bar.moveMenuOpening.connect(
            lambda menu, ids: self._fill_move_menu(menu, ids))

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
        bar, parts = self._make_list_bar(for_board=False)
        self.select_all_btn = parts.select_all
        self.select_hint = parts.hint
        self.collapse_all_btn = parts.collapse_all
        self.expand_all_btn = parts.expand_all
        self.english_btn = parts.english
        self.duplicates_btn = parts.duplicates
        self.check_dupes_btn = parts.check_dupes
        self.auto_dupes = parts.auto_dupes
        self.filter_btn = parts.filter_btn
        self.clear_selection_btn = parts.clear_selection
        self.select_bar = bar
        bar.hide()
        return bar

    def _build_board_list_bar(self) -> None:
        """The same bar over a category of the sentiment board opened out as
        a list, whose buttons do the same things to that category - the
        duplicate buttons included, checking that category's clippings."""
        from .filter_bar import FilterBar

        bar, parts = self._make_list_bar(for_board=True)
        self.board_list_bar = bar
        self.board_select_all = parts.select_all
        self.board_select_hint = parts.hint
        self.board_collapse_all = parts.collapse_all
        self.board_expand_all = parts.expand_all
        self.board_english = parts.english
        self.board_duplicates_btn = parts.duplicates
        self.board_check_dupes = parts.check_dupes
        self.board_auto_dupes = parts.auto_dupes
        self.board_filter_btn = parts.filter_btn
        self.board_clear_selection = parts.clear_selection
        self.board_filter_bar = FilterBar()
        self.board_filter_bar.hide()
        self.board.set_list_bar(bar, self.board_filter_bar)

    def _make_list_bar(self, for_board: bool = False):
        """The bar over a list: Select all, the hint, and its bubbles.

        Returns (bar, parts). ``for_board`` is the copy over a category of the
        sentiment board, whose buttons the window wires to the board's pool
        (see _wire) - the duplicate buttons here, since they are made here.
        """
        bar = QWidget()
        bar.setStyleSheet("background: transparent;")
        row = QHBoxLayout(bar)
        # 64 on the right, not 4: the floating scroll and undo buttons hover in
        # that gutter, and anything ending flush with the edge disappears under
        # them.
        row.setContentsMargins(4, 0, 64, 0)
        row.setSpacing(12)

        select_all = QPushButton("Select all")
        select_all.setObjectName("LinkNavy")
        select_all.setCursor(Qt.PointingHandCursor)
        row.addWidget(select_all)

        # Elided, not plain. A QLabel refuses to be narrower than its whole
        # sentence, and this sentence is 469px of it - the widest thing in the
        # row, and the reason the row could not shrink. The full text stays on
        # its own tooltip.
        hint = ElidedLabel(
            "Hold Ctrl to pick several, Shift for a run, or drag the handle to "
            "move a block anywhere",
            floor=90,
        )
        hint.setObjectName("SubtleHint")
        row.addWidget(hint)
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
        collapse_all = QPushButton("Collapse all")
        collapse_all.setToolTip("Fold every document down to its name")
        expand_all = QPushButton("Expand all")
        expand_all.setToolTip("Open every document again")
        for button, filled in ((collapse_all, False),
                               (expand_all, False)):
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
        if not for_board:
            collapse_all.clicked.connect(lambda: self._fold_all(True))
            expand_all.clicked.connect(lambda: self._fold_all(False))

        # Every card's Hindi into English at once, with a list of what was
        # done to which. Shown only while some card has Hindi in a field the
        # report prints: a button that does nothing is worse than no button.
        english = QPushButton("Hindi to English")
        english.setCursor(Qt.PointingHandCursor)
        english.setToolTip(
            "Read every card's Hindi or Punjabi the way a copied caption is "
            "read, and write the newspaper and city into the fields in "
            "English. A Hindi headline that is not a caption is left alone. "
            "Ctrl+Z puts it all back.")
        english.setStyleSheet(collapse_all.styleSheet())
        if not for_board:
            # Through a lambda: clicked's "checked" would otherwise arrive as
            # the pool the handler now takes.
            english.clicked.connect(lambda: self._put_all_in_english())
        english.hide()
        bubbles.addWidget(english)

        # Made for both lists. Through lambdas: clicked's "checked" would
        # otherwise arrive as the pool these handlers now take.
        board_pool = getattr(self, "board_model", None) if for_board else None
        # The third bubble, in the same style as its neighbours. It is not
        # shown at all when nothing is flagged: a button that does nothing
        # is worse than no button, and on most mornings there are no repeats.
        duplicates = QPushButton("Preview and Delete Duplicates")
        duplicates.setCursor(Qt.PointingHandCursor)
        duplicates.setToolTip(
            "Look at each suspected repeat beside the clipping it repeats, "
            "and decide.")
        duplicates.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE};"
            f" color: {theme.DANGER};"
            f" border: 1px solid {theme.DANGER};"
            " border-radius: 11px; padding: 4px 12px;"
            " font-size: 11px; font-weight: 700; }"
            f"QPushButton:hover {{ background: {theme.SURFACE};"
            f" border-color: {theme.DANGER}; }}"
        )
        duplicates.clicked.connect(
            lambda: self.review_duplicates(pool=board_pool))
        duplicates.hide()
        bubbles.addWidget(duplicates)

        # The check runs by itself on every change, quietly. This is for
        # being sure: it looks again on demand, from scratch, and says what
        # it found either way - because "nothing flagged" and "never looked"
        # are the same thing on screen otherwise.
        check_dupes = QPushButton("Check for Duplicates")
        check_dupes.setCursor(Qt.PointingHandCursor)
        check_dupes.setToolTip(
            "Look again now, from scratch, and say what was found." + '\n\n'
            + "The check already runs by itself on every import, and "
            "remembers what it has read - so it never re-reads the same "
            "clipping twice. This throws all of that away and does the "
            "lot again, which takes a moment on a full morning. Worth it "
            "after cropping or straightening, when what was read before "
            "no longer matches the picture.")
        check_dupes.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE};"
            f" color: {theme.NAVY};"
            f" border: 1px solid {theme.HAIRLINE_STRONG};"
            " border-radius: 11px; padding: 4px 12px;"
            " font-size: 11px; font-weight: 700; }"
            f"QPushButton:hover {{ background: {theme.NAVY_WASH};"
            f" border-color: {theme.NAVY}; }}"
        )
        check_dupes.clicked.connect(
            lambda: self.check_duplicates_now(pool=board_pool))
        check_dupes.hide()
        bubbles.addWidget(check_dupes)

        # Beside the button it governs, so what it turns off is obvious.
        # With it off nothing is checked until the button is pressed -
        # which is what somebody wants when they are importing six files
        # one after another and would rather the machine left them alone
        # until they have finished.
        auto_dupes = QCheckBox("Check automatically")
        auto_dupes.setCursor(Qt.PointingHandCursor)
        auto_dupes.setToolTip(
            "On: every import is checked for repeats by itself.\n"
            "Off: nothing is checked until you press Check for Duplicates.\n\n"
            "The button works either way.")
        auto_dupes.setStyleSheet(
            f"QCheckBox {{ color: {theme.MUTED}; font-size: 11px;"
            " font-weight: 700; spacing: 5px; }"
            f"QCheckBox:hover {{ color: {theme.NAVY}; }}"
        )
        auto_dupes.setChecked(self._auto_duplicates)
        auto_dupes.toggled.connect(self._auto_duplicates_toggled)
        auto_dupes.hide()
        bubbles.addWidget(auto_dupes)

        # In the bubbles rather than the crown, for two reasons that are both
        # about this window. The crown is not inside a scroll area, so a
        # drop-down up there would keep the mouse wheel and change itself while
        # somebody tried to scroll the page. And this row already hides itself
        # when there is nothing in the list, so the control cannot exist when
        # there is nothing to filter.
        filter_btn = QPushButton("Filter and arrange")
        filter_btn.setCursor(Qt.PointingHandCursor)
        filter_btn.setCheckable(True)
        filter_btn.setToolTip(
            "Show only some of the clippings, or put them in another order - "
            "by regional or national, by language, by how big the paper is."
            + "\n\n"
            + "It changes what you see, never what is exported, and never the "
            "order the clippings are really in.")
        filter_btn.setStyleSheet(
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
        if not for_board:
            filter_btn.toggled.connect(self._filter_bar_shown)
        bubbles.addWidget(filter_btn)

        clear_selection = QPushButton("Clear selection")
        clear_selection.setObjectName("Quiet")
        clear_selection.hide()
        bubbles.addWidget(clear_selection)

        return bar, SimpleNamespace(
            select_all=select_all, hint=hint, collapse_all=collapse_all,
            expand_all=expand_all, english=english, duplicates=duplicates,
            check_dupes=check_dupes, auto_dupes=auto_dupes,
            filter_btn=filter_btn, clear_selection=clear_selection)

    def _build_filter_bar(self):
        from .filter_bar import FilterBar

        self.filter_bar = FilterBar()
        self.filter_bar.changed.connect(self._lens_changed)
        self.filter_bar.editCategories.connect(self.edit_categories)
        self.filter_bar.hide()
        return self.filter_bar

    def _list_parts(self, pool=None) -> SimpleNamespace:
        """One list and what belongs to it: the pool it shows, the view, its
        filter strip and the buttons on its bar. A board category's for the
        board's pool; the press report's otherwise, over the pool on show, as
        the report's own handlers have always read it."""
        board = getattr(self, "board", None)
        if (pool is not None and board is not None
                and pool is getattr(self, "board_model", None)
                and hasattr(self, "board_select_all")):
            return SimpleNamespace(
                board=True, pool=pool, view=board.focus_list,
                filter_bar=self.board_filter_bar, filter_btn=self.board_filter_btn,
                select_all=self.board_select_all, hint=self.board_select_hint,
                collapse_all=self.board_collapse_all,
                expand_all=self.board_expand_all, english=self.board_english,
                clear_selection=self.board_clear_selection)
        return SimpleNamespace(
            board=False, pool=self.pool(), view=self.list,
            filter_bar=getattr(self, "filter_bar", None),
            filter_btn=getattr(self, "filter_btn", None),
            select_all=getattr(self, "select_all_btn", None),
            hint=getattr(self, "select_hint", None),
            collapse_all=getattr(self, "collapse_all_btn", None),
            expand_all=getattr(self, "expand_all_btn", None),
            english=getattr(self, "english_btn", None),
            clear_selection=getattr(self, "clear_selection_btn", None))

    def _filter_bar_shown(self, shown: bool, pool=None) -> None:
        """The chip opens and shuts the strip.

        Shutting it clears the lens rather than leaving it on out of sight.
        A list quietly hiding half its clippings with no control on screen to
        say why is the one state this feature must never be able to reach.
        ``pool`` is the board's for the strip over a category's list.
        """
        parts = self._list_parts(pool)
        bar, model = parts.filter_bar, parts.pool
        if shown:
            # Shown first, then filled. The refresh declines to do anything
            # for a strip that is not on screen, so the other way round opened
            # the strip with every row empty.
            bar.show()
            self._refresh_filter_choices()
        else:
            bar.hide()
            if model.lens.busy:
                bar.clear()

    def _refresh_filter_choices(self) -> None:
        """Rebuild the chips from what is actually in the list right now -
        the press report's, and a board category's opened out as a list, whose
        chips are that category's papers and whose total is its clippings.

        A pick whose last clipping has gone - moved to another category, put
        in English, given another paper - is dropped quietly as the chips are
        rebuilt. The list is then handed the strip's lens again. Without that
        it went on hiding every clipping under a pick nobody could see or
        take off, with Show all again greyed out: the state _filter_bar_shown
        says must never be reached. Never run inside a chip's own click (see
        _say_filter_counts), so working the list out again here is safe.
        """
        bar = getattr(self, "filter_bar", None)
        if bar is not None and bar.isVisible():
            pool = self.pool()
            bar.offer([row.clip for row in pool.rows], pool.book)
            if bar.lens() != pool.lens:
                self._lens_changed()
            bar.say(pool.shown_count(), len(pool.rows))
        board_bar = getattr(self, "board_filter_bar", None)
        if board_bar is not None and board_bar.isVisible():
            held = self.board_model.scoped_rows()
            board_bar.offer([row.clip for row in held], self.board_model.book)
            if board_bar.lens() != self.board_model.lens:
                self._lens_changed(pool=self.board_model)
            board_bar.say(self.board_model.shown_count(), len(held))

    def _say_filter_counts(self) -> None:
        """Only the words under each open strip - how many are showing, of
        how many - asked on every recount.

        A clipping moved to another category, deleted, or brought back by
        Ctrl+Z changes the numbers without touching the chips, and the strip
        went on saying "Showing 5 of 12" over a list of four. The chips are
        not rebuilt here: a recount runs inside a chip's own click, and
        rebuilding the row would take the button away from under it.
        """
        bar = getattr(self, "filter_bar", None)
        if bar is not None and bar.isVisible():
            bar.say(self.model.shown_count(), len(self.model.rows))
        board_bar = getattr(self, "board_filter_bar", None)
        if board_bar is not None and board_bar.isVisible():
            board_bar.say(self.board_model.shown_count(),
                          len(self.board_model.scoped_rows()))

    def _lens_changed(self, pool=None) -> None:
        if pool is not None and pool is self.board_model:
            bar, view = self.board_filter_bar, self.board.focus_list
        else:
            pool = self.pool()
            bar, view = self.filter_bar, self.list
        view.commit_editor()
        pool.set_lens(bar.lens())
        bar.say(pool.shown_count(), len(pool.scoped_rows()))
        self._sync_fold_buttons()
        self._update_counts()
        view.refresh_height()

    def edit_categories(self, pool=None) -> None:
        """Say which papers are regional, which are Hindi, which are the big
        ones. What is set here is kept when the program is updated."""
        from .categories_dialog import CategoriesDialog

        board = pool is not None and pool is self.board_model
        pool = pool if board else self.pool()
        screen = CategoriesDialog([row.clip for row in pool.scoped_rows()], self)
        if board:
            # open(), never exec(): nothing the board shows may hold up the
            # window. It is still modal to the window, so the list cannot
            # change under it; what it changed is read once it closes.
            screen.setAttribute(Qt.WA_DeleteOnClose, True)
            screen.finished.connect(
                lambda _result: self._categories_edited(pool, board=True))
            screen.open()
            return
        screen.exec()
        self._categories_edited(pool, board=False)

    def _categories_edited(self, pool, board: bool) -> None:
        """After Which papers are which: the papers' categories are read
        again, and a filter on is worked out again under what was changed."""
        pool.forget_book()
        self.board_model.forget_book()
        self._refresh_filter_choices()
        if pool.lens.busy:
            self._lens_changed(pool=pool if board else None)

    def _fold_all(self, collapsed: bool, pool=None) -> None:
        """Shut every document in the list, or open every one - in a
        category's list, that category's documents only."""
        board = pool is not None and pool is self.board_model
        pool = pool if board else self.pool()
        if pool.group_count() == 0:
            return
        view = self.board.focus_list if board else self.list
        view.commit_editor()
        pool.set_all_collapsed(collapsed)
        if collapsed:
            if board:
                # The list stands in the page: its top is where the page's
                # working half starts.
                self.board.show_settings(False)
            else:
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
        if hasattr(self, "board_collapse_all"):
            pool = self.board_model
            groups = pool.group_count() if pool.scope is not None else 0
            for button in (self.board_collapse_all, self.board_expand_all):
                button.setVisible(groups > 0)
        if hasattr(self, "board_check_dupes"):
            # As the report's: there while the category has clippings.
            held = bool(self._duplicate_clips(self.board_model))
            self.board_check_dupes.setVisible(held)
            self.board_auto_dupes.setVisible(held)

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
        label.setWordWrap(True)      # never the thing that sets the window's width
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
        self.ready.setWordWrap(True)
        # It wraps rather than pushing the bar wide - "ready for export" goes
        # onto a second line long before the buttons are shoved off the edge.
        self.ready.setMinimumWidth(96)
        row.addWidget(self.ready, 0)

        # WHAT WAS LAST DONE TO THIS NEWSPAD, between the count and the export
        # buttons. The undo stack already knows it and already steps back on
        # Ctrl+Z - undoText() is the thing that WOULD be undone, which is the
        # last thing done - so this is that sentence and nothing more. It takes
        # the room the stretch used to, and elides instead of pushing the
        # buttons off a narrow window.
        self.last_action = ElidedLabel(floor=70)
        self.last_action.setObjectName("FooterLast")
        self.last_action.setAlignment(Qt.AlignCenter)
        self.last_action.setStyleSheet(
            f"#FooterLast {{ color: {theme.SLATE_TEXT_LIGHT}; font-size: 11px;"
            f" background: transparent; border: none; }}")
        row.addWidget(self.last_action, 1)

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

    #: Clear of the bottom edge, so the newest row is seen whole - and clear
    #: of the batch bar that may be floating over the foot of the page.
    REVEAL_GAP = 28

    def _reveal_on_page(self, clip_id: int) -> None:
        """Bring a clipping the person did not put there by hand into view.

        The list stands at its full height inside the page, so it is the PAGE
        that has to move (see _scroll_to_top); asking the list to scroll did
        nothing, and a collected photo landed one row under the fold. And not
        yet: the row was inserted a moment ago, and the page's range only
        grows once the list has laid it out - a scroll made now reaches the
        old bottom, one row short of the new one (measured: the row sat
        exactly under the visible edge). So twice - once the layout has run,
        and again once the range has caught up.
        """
        def go() -> None:
            page = self._page_showing()
            if page is None or self.mode != "standard":
                return
            at_row = self.model.entry_row_for_clip(clip_id)
            if at_row < 0:
                return
            rect = self.list.visualRect(self.model.index(at_row, 0))
            if not rect.isValid():
                return
            top = self.list.viewport().mapTo(page.widget(), rect.topLeft()).y()
            bar = page.verticalScrollBar()
            room = page.viewport().height()
            # At the foot of the view, so the ones before it stay in sight
            # above - that is where the next caption's eye goes.
            wanted = top + rect.height() - room + self.REVEAL_GAP
            bar.setValue(max(0, min(bar.maximum(), wanted)))

        for wait_ms in (0, 160, 450):
            QTimer.singleShot(wait_ms, self._deferred(go))

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

        # MERGE IS NOT HERE ANY MORE. It is on every card's own menu, which is
        # where merging two cuttings is decided - looking at them - and the
        # room on this bar was wanted for Shift to.
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
        # INTO ANOTHER NEWSPAD, all of them at once. Building a second newspad
        # means putting the same twenty cuttings in it, and doing that one
        # clipping at a time through the preview is twenty windows. Like
        # "Move to", a button with a menu rather than a combo box: a combo on
        # this bar would take the wheel from the list scrolling under it.
        self.batch_shift_to = QPushButton("Shift to: ▾")
        self.batch_shift_to.setObjectName("BatchShift")
        self.batch_shift_to.setToolTip(
            "Put a copy of every ticked clipping into another newspad. They "
            "stay here as well - this copies, it does not take them away - and "
            "they are there when you switch to that newspad.")
        self.batch_shift_menu = QMenu(self)
        self.batch_shift_menu.setToolTipsVisible(True)
        self.batch_shift_menu.aboutToShow.connect(
            lambda: self._fill_shift_menu(self.batch_shift_menu))
        self.batch_shift_to.setMenu(self.batch_shift_menu)
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
            self.batch_name, self.batch_top, self.batch_up,
            self.batch_down, self.batch_bottom, self.batch_move_to,
            self.batch_shift_to,
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
        # NO FRAME OF ITS OWN. A QFrame draws a box by default, and the box
        # sat inside the rounded navy as a second, squarer edge - the
        # "unwanted edges" on a bubble that should be one shape.
        self.move_note.setFrameShape(QFrame.NoFrame)
        self.move_note.setAttribute(Qt.WA_TranslucentBackground, False)
        self.move_note.setStyleSheet(
            # Translucent, but not so much that white type on it stops being
            # readable: at 0.93 over the page's own pale grey the text keeps
            # well past the 4.5:1 it needs.
            f"#BatchNote {{ background: rgba(16, 32, 63, 0.93);"
            f" border: 1px solid rgba(255, 255, 255, 0.10);"
            f" border-radius: 13px; }}"
            f"#BatchNote QLabel {{ color: #EEF2F8; font-size: 11.5px;"
            f" font-weight: 600; background: transparent; border: none; }}")
        note_row = QHBoxLayout(self.move_note)
        note_row.setContentsMargins(13, 8, 13, 8)
        self.move_note_text = QLabel()
        self.move_note_text.setWordWrap(True)
        # Narrow enough to read in one glance. Left to itself the bubble ran
        # the width of the window and the sentence became three long lines.
        self.move_note_text.setMaximumWidth(430)
        note_row.addWidget(self.move_note_text)
        self.move_note.hide()
        self._move_note_above = False
        self._move_note_timer = QTimer(self)
        self._move_note_timer.setSingleShot(True)
        # Shorter than it was: six seconds is long enough to feel like
        # something left behind.
        self._move_note_timer.setInterval(3600)
        self._move_note_timer.timeout.connect(self._hide_move_note)

    # -------------------------------------------------------------- wiring
    def _wire(self) -> None:
        self.btn_word.clicked.connect(lambda: self._choose("word"))
        self.btn_pdf.clicked.connect(lambda: self._choose("pdf"))
        self.btn_photos.clicked.connect(lambda: self._choose("photos"))
        self.btn_links.clicked.connect(self.open_links)
        self.clear_all_btn.clicked.connect(self._clear_all)
        self.collapse_btn.clicked.connect(self._toggle_card)

        # Through a lambda: clicked's "checked" would otherwise arrive as the
        # pool the handler now takes, and a False pool acts on nothing.
        self.select_all_btn.clicked.connect(lambda: self._toggle_select_all())
        self.clear_selection_btn.clicked.connect(self.model.clear_selection)

        self.list.clipAction.connect(self._on_clip_action)
        self.list.groupAction.connect(self._on_group_action)
        self.list.labelEdited.connect(self._on_label_edited)
        self.list.urlEdited.connect(self._on_url_edited)
        self.list.readEdited.connect(self._ocr_corrected)
        # The results panel rides with the field as the page scrolls. Wired
        # here rather than where the bar is built: the page it scrolls in does
        # not exist yet at that point, so the connection was quietly made to
        # nothing and the panel stayed behind.
        page = getattr(self, "body_scroll", None)
        if page is not None:
            self.find_bar.follow(page)
        self.list.previewRequested.connect(self.open_preview)
        self.list.reorderRequested.connect(self._on_reorder)
        self.list.selectionToggled.connect(self._on_selection_toggled)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)

        # A category of the sentiment board opened out is the same list over
        # the board's pool. Every gesture on it reaches the same handler, told
        # which pool it is for - and so the board's own history.
        listed = self.board.focus_list
        board_pool = self.board_model
        listed.clipAction.connect(
            functools.partial(self._on_clip_action, pool=board_pool))
        listed.groupAction.connect(
            functools.partial(self._on_group_action, pool=board_pool))
        listed.labelEdited.connect(
            functools.partial(self._on_label_edited, pool=board_pool))
        listed.urlEdited.connect(
            functools.partial(self._on_url_edited, pool=board_pool))
        listed.previewRequested.connect(self.open_preview)
        listed.reorderRequested.connect(
            functools.partial(self._on_reorder, pool=board_pool))
        listed.selectionToggled.connect(
            functools.partial(self._on_selection_toggled, pool=board_pool))
        listed.setContextMenuPolicy(Qt.CustomContextMenu)
        listed.customContextMenuRequested.connect(
            functools.partial(self._context_menu, pool=board_pool))
        self.board_select_all.clicked.connect(
            lambda: self._toggle_select_all(pool=board_pool))
        self.board_clear_selection.clicked.connect(board_pool.clear_selection)
        self.board_collapse_all.clicked.connect(
            lambda: self._fold_all(True, pool=board_pool))
        self.board_expand_all.clicked.connect(
            lambda: self._fold_all(False, pool=board_pool))
        self.board_english.clicked.connect(
            lambda: self._put_all_in_english(pool=board_pool))
        self.board_filter_btn.toggled.connect(
            lambda on: self._filter_bar_shown(on, pool=board_pool))
        self.board_filter_bar.changed.connect(
            lambda: self._lens_changed(pool=board_pool))
        self.board_filter_bar.editCategories.connect(
            lambda: self.edit_categories(pool=board_pool))
        self.board.focusChanged.connect(lambda _value: self._board_focus_changed())
        board_pool.selectionChanged.connect(self._hide_move_note)
        self.board_undo.indexChanged.connect(self._hide_move_note)

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
        # A step done, undone or done again can take a paper's last clipping
        # away or bring it back without passing anything that rebuilds the
        # filter's chips: Ctrl+Z brought a clipping back and its paper was not
        # offered, so it could be neither picked nor taken off. Rebuilt a
        # moment later, once whatever pushed the step has finished - never
        # inside a chip's own click - and only for a strip that is open (see
        # _refresh_filter_choices). Several steps together ask once.
        self._offer_timer = QTimer(self)
        self._offer_timer.setSingleShot(True)
        self._offer_timer.setInterval(0)
        self._offer_timer.timeout.connect(self._refresh_filter_choices)
        self.undo_stack.indexChanged.connect(lambda _i: self._offer_timer.start())
        self.board_undo.indexChanged.connect(lambda _i: self._offer_timer.start())
        self.undo_stack.indexChanged.connect(lambda _i: self._say_last_action())
        self.board_undo.indexChanged.connect(lambda _i: self._say_last_action())

        self.mode_switch.changed.connect(self.set_mode)
        self.board.assignRequested.connect(self._assign_sentiment)
        self.board.previewRequested.connect(self.open_preview)
        self.board.divisionChanged.connect(lambda _c: self._refresh_board())
        self.board.addRequested.connect(self._add_into_section)
        self.board.exportRequested.connect(self._export_dossier)
        self.board.buildRequested.connect(self._build_board_report)
        self.board.clearRequested.connect(self._clear_division)
        self.board.heading.groupSocial.connect(
            lambda: self._group_social(self.board_model))
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
        # The board's history, for a category opened out as a list: its check
        # is asked on the same terms (and does nothing over four columns).
        self.board_undo.indexChanged.connect(
            lambda _i: self.recheck_duplicates(pool=self.board_model))
        # And its review button counted again: a step can take one side of a
        # pair out of the category, or bring it back.
        self.board_undo.indexChanged.connect(lambda _i: self._count_board_review())
        self.float_undo.setEnabled(False)
        self.float_redo.setEnabled(False)

        self.batch_name.clicked.connect(lambda: self._bulk_field("newspaper"))
        self.batch_top.clicked.connect(lambda: self._batch_move("top"))
        self.batch_up.clicked.connect(lambda: self._batch_move("up"))
        self.batch_down.clicked.connect(lambda: self._batch_move("down"))
        self.batch_bottom.clicked.connect(lambda: self._batch_move("bottom"))
        self.batch_exclude.clicked.connect(self._batch_exclude)
        self.batch_delete.clicked.connect(self._batch_delete)
        self.batch_close.clicked.connect(
            lambda: (self._list_pool() or self.model).clear_selection())

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
        QShortcut(QKeySequence("Home"), self, lambda: self._list_end(True))
        QShortcut(QKeySequence("End"), self, lambda: self._list_end(False))
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
                self._native_drop_empty, on_link=self._native_link_dropped,
            )
        if self._native_drop is None and win_drop.Available:
            self.drop.setAcceptDrops(True)

    def _native_link_dropped(self, words: str) -> None:
        """A link dragged onto the drop panel when only the panel could be
        taken over: to the links window, as a link dropped anywhere else is.
        Words with no story link in them - a picture's own address - came with
        a picture that did not: its advice, never a silent nothing."""
        if not (words and links.story_links(words)):
            self._native_drop_empty()
            return
        if self._refuse_if_read_only():
            return
        self._links_arrived(words, "drop")

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
                    # A list standing in for a column - a category opened
                    # out on the board - says which one it is.
                    listed = getattr(widget, "drop_section", None)
                    if listed is not None:
                        return listed
                    section = getattr(widget, "section", None)
                    if section is not None and hasattr(widget, "cardsDropped"):
                        return section
                    widget = widget.parentWidget()
        except Exception:  # noqa: BLE001 - fall back to the ordinary route
            return None
        return None

    def _focused_section(self) -> "Section | None":
        """The category opened out as a list on the board, or None - in the
        press report, over four columns, or for a value that is not one."""
        board = getattr(self, "board", None)
        focused = getattr(board, "focused", None) if board is not None else None
        if self.mode != "sentiment" or not focused:
            return None
        try:
            return Section(focused)
        except ValueError:
            return None

    def _native_files_dropped(self, files: list, point=None) -> None:
        """Images pulled straight out of a browser drag."""
        section = self._section_under(point)
        if section is None:
            # With a category opened out, only it is on show: a picture let go
            # over its header, the focus bar or the page's margin is meant for
            # it, as one let go on its list is.
            section = self._focused_section()
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
        if section is None and on_board:
            # A category opened out as a list is the only one on show, so a
            # clipping that arrives with no column of its own goes into it -
            # where the person is looking, and where its headline box opens.
            # Collect and a captured link choose their own column and arm it
            # before they come here, so this never overrides them.
            section = self._focused_section()
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

    def _add_loose(self, clips: list[Clip], quiet: bool = False,
                   tidy: bool | None = None, reveal: bool = True) -> list:
        """Hand-added clippings share one group and land at the top, in order.

        ``quiet`` is Collect from WhatsApp, where the person is in Chrome, not
        here: nothing comes forward, no headline box opens, nothing takes the
        keyboard - the clipping simply appears. Returns the rows added.

        ``tidy`` overrides the Layout card's "trim the phone's bars" for these
        clippings only (None: as the card says), and ``reveal`` False leaves
        the page where it is - both Collect's options for the session.
        """
        if self._refuse_if_read_only():
            return []
        target = self.pool()
        self._stamp_pending(clips)
        tidied = self._tidy_screenshots(clips, tidy)
        rows = target.make_rows(clips, "clipboard", LOOSE_TITLE, LOOSE_KEY)
        at = target.loose_insert_point()
        scope = getattr(target, "scope", None)
        if (target is getattr(self, "board_model", None) and scope is not None
                and clips and all(scope.holds(clip) for clip in clips)):
            # Into a category opened out as a list: at the top of ITS loose
            # clippings, as the press report puts them. The pool's own rule is
            # kept for a clipping that went to another category (Collect's
            # column option), which would otherwise be put among this one's,
            # and scoped_insert_point falls back to it in an empty category.
            at = target.scoped_insert_point()
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
                # A category opened out as a list follows the arrival, as the
                # press report's page does - and not when Collect's options
                # say to leave the page be, or it landed in another category.
                if rows and reveal:
                    self._reveal_in_board_list(rows[-1].id)
            else:
                self._show_list()
                # The list follows the newest arrival, wherever the person is
                # looking: the caption they copy next goes on it, and they
                # asked to see it land. Put at the foot of the view, so the
                # ones before it stay in sight above. Unless Collect's options
                # say to leave the page where the person put it.
                if rows and reveal:
                    self._reveal_on_page(rows[-1].id)
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
            f"{headline}" + (TIDIED_NOTE if tidied else ""),
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

    def open_links(self, words: str = "", quiet: bool = False) -> None:
        """The window where links are pasted and captured.

        ``words`` fills the box - a message pasted with Ctrl+V arrives here
        rather than in the "nothing to add" box. With the window already open
        they go under the links already listed, on lines of their own, and
        every tick stays: a second link pasted used to replace the first.
        Closed, it starts afresh with just what came.

        ``quiet`` is Collect from WhatsApp, with the person still in Chrome.
        The link goes under what the list holds - also when its window was
        only closed in this newspad, so the links and marks left there are
        not wiped by a copy the person made elsewhere. The window is never
        brought forward nor given the keyboard, and it is shown only while
        this window is the one in use: measured on the real window platform,
        a window shown without activating still lands on top of the one in
        front, which would have been WhatsApp. Otherwise it waits and opens
        when the person comes back (changeEvent).
        """
        if self._refuse_if_read_only():
            return
        dialog = getattr(self, "links_dialog", None)
        if dialog is None:
            dialog = self.links_dialog = webclip.LinksDialog(self)
        if words:
            # Links Collect put there while the person was away, not yet seen,
            # are never wiped by their own paste either.
            if dialog.isVisible() or ((quiet or getattr(self, "_links_waiting", False))
                                      and self.links_kept()):
                dialog.add_words(words)
            else:
                dialog.start_over(words)
        self._links_gen = self._newspad_gen
        if quiet:
            if dialog.isVisible():
                return
            if self.isActiveWindow():
                self._show_links_quietly(dialog)
            else:
                self._links_waiting = True
            return
        self._links_waiting = False
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def links_kept(self) -> str:
        """The words of the links list a link from Collect goes under: the
        box while its window is open, or while it was last used in this
        newspad and only closed. "" when the next link starts a fresh list."""
        dialog = getattr(self, "links_dialog", None)
        if dialog is None:
            return ""
        try:
            if (dialog.isVisible()
                    or getattr(self, "_links_gen", None) == self._newspad_gen):
                return dialog.box.toPlainText()
        except RuntimeError:
            pass
        return ""

    @staticmethod
    def _show_links_quietly(dialog) -> None:
        """Shown, never activated. The flag goes on the native window too when
        one already exists: measured on the real window platform, a native
        window made before its first show (anything asking for its winId, as
        win_drop does for the windows it takes drops on) keeps the flag it was
        made with, and the show then took the keyboard from the window in use.
        Qt passes the widget's attribute on only when it makes the window."""
        made = dialog.windowHandle()
        dialog.setAttribute(Qt.WA_ShowWithoutActivating, True)
        if made is not None:
            made.setProperty("_q_showWithoutActivating", True)
        try:
            dialog.show()
        finally:
            dialog.setAttribute(Qt.WA_ShowWithoutActivating, False)
            handle = dialog.windowHandle()
            if handle is not None:
                handle.setProperty("_q_showWithoutActivating", False)

    def _show_waiting_links(self) -> None:
        """The links window Collect filled while the person was in Chrome,
        shown now they are back in this window - still without taking the
        keyboard from whatever they came back to do."""
        self._links_waiting = False
        dialog = getattr(self, "links_dialog", None)
        if (dialog is None or self._read_only or self._switching
                or getattr(self, "_closing", False) or not self.links_kept().strip()):
            return
        try:
            if not dialog.isVisible():
                self._show_links_quietly(dialog)
        except RuntimeError:
            pass

    def clip_from_link(self, shot, found):
        """One captured page, added as a clipping where the person is working.
        Returns the clipping's id, or None when the picture could not be read.

        The picture already carries the headline, so nothing is typed over it:
        the caption is the publication's name, and the link prints underneath
        as it does for any digital coverage.
        """
        try:
            clip = self._clip_from_bytes(shot.png, f"{found.site}.png")
        except Exception:  # noqa: BLE001 - one link, never the morning
            self._flash(f"That page's picture could not be read ({found.site}).",
                        "bad")
            return None
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
        on_board = pool is getattr(self, "board_model", None)
        saved = self._pending_section
        if on_board:
            # A web page is digital coverage whichever category is opened out:
            # armed with its own column, so the opened one does not take it.
            # A column a board button armed for its own import is put back.
            self._pending_section = clip.section
        try:
            rows = self._add_loose([clip], quiet=True) or []
        finally:
            if on_board:
                self._pending_section = saved
        if rows and not on_board:
            self._flash(f"Captured {shot.site} — No. "
                        f"{pool.number_of(rows[0].id)}.", "good")
        elif rows:
            # Said by column, which is where it is on the board: a number is
            # only a place in the category's list, and it may not be the one
            # on show.
            column = sentiment.column_for(rows[0].clip.section).value
            number = pool.number_of(rows[0].id) if pool.scope is not None else 0
            focused = self._focused_section()
            if number:
                said = f"Captured {shot.site} — No. {number} in {column}."
            elif focused is not None:
                said = (f"Captured {shot.site} into {column} — the board is "
                        f"showing only {focused.value}.")
            else:
                said = f"Captured {shot.site} into {column}."
            self._flash(said, "good")
        return rows[0].id if rows else None

    def _tidy_screenshots(self, clips: list, wanted: bool | None = None) -> int:
        """Take the phone's bars and the blank margins off pasted pictures, as
        a crop each carries - the picture itself is never altered, and the
        preview's Whole picture puts it back. Only when the layout card says
        so - or ``wanted`` does, for Collect's "always" and "never" - and only
        on pictures that arrived by hand. Returns how many."""
        from .layout_card import tidy_wanted

        if not (tidy_wanted() if wanted is None else wanted):
            return 0
        from ..core import tidy

        done = 0
        for clip in clips:
            if clip.source_file != "clipboard" or not clip.crop.is_identity:
                continue
            box = tidy.tidy_crop(clip.image_bytes)
            if box is not None:
                clip.crop = box
                done += 1
        return done

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

    #: A web address that is a picture rather than a story: "…/photo.jpg",
    #: "…/media/X?format=jpg". Dragged, it keeps the "copy the image" advice.
    #: Kept in core/links, because win_drop's drop target asks the same.
    _PICTURE_ADDRESS = links.PICTURE_ADDRESS

    @classmethod
    def _links_in(cls, mime, payload=None) -> str:
        """The words of a drop or paste that carries story links and nothing
        else - no files, no picture - or "" when it is not that.

        A link dragged from Chrome's address bar, or copied, arrives as text,
        or as addresses with no text at all. A link to a picture, a blob: or a
        data: address is not a story, and keeps today's advice.
        """
        if mime is None:
            return ""
        if payload is None:
            payload = dropped.read(mime)
        if payload.files or payload.images:
            return ""
        words = mime.text() if mime.hasText() else ""
        if not links.find(words):
            words = "\n".join(url.toString() for url in mime.urls() if not url.isLocalFile())
        return words if links.story_links(words) else ""

    def _links_arrived(self, words: str, how: str) -> None:
        """Links from a paste or a drop, into the links window, and said."""
        many = len(links.find(words))
        was_open = bool(getattr(self, "links_dialog", None) is not None
                        and self.links_dialog.isVisible())
        self.open_links(words)
        if how == "clipboard":
            self._flash(f"{many} link{'s' if many != 1 else ''} on the "
                        f"clipboard — press Capture to take "
                        f"{'them' if many != 1 else 'it'}.", "info")
        else:
            self._flash(f"{many} link{'s' if many != 1 else ''} "
                        f"{'added to' if was_open else 'put in'} the links window "
                        f"— press Capture to take {'them' if many != 1 else 'it'}.", "info")

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
            # A story link dragged here - from Chrome's address bar, a page, or
            # a message - is not a picture that failed to come through: it
            # opens the links window with the link in it. The same whether it
            # lands on the window, the list or a board column.
            words = self._links_in(mime, payload)
            if words and not self._read_only:
                self._links_arrived(words, "drop")
                return True
            if words:
                self.open_links(words)      # says why it cannot
                return False
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
        # A link on the clipboard is not a picture, and the "nothing to add"
        # box was the wrong answer to it: what somebody pasting a story link
        # wants is the story. The list opens with it already in, so they can
        # see what was found before anything is captured. Before Collect's
        # "already taken" below: with Collect on, a pasted link used to be
        # answered "Ctrl+V is not needed" and never reached the links window.
        mime = QGuiApplication.clipboard().mimeData()
        words = self._links_in(mime)
        collector = getattr(self, "collector", None)
        taken = bool(collector is not None and collector.is_on
                     and collector.watcher.already_read())
        if words and taken:
            # Collect has already dealt with this copy. A link it put on a
            # photo, or in the links list, is not listed again: Capture would
            # make a second clipping of a story already on the page (review
            # of A2, round 2). What is left - a link Collect did not take -
            # still reaches the links window.
            words = collector.links_not_taken(words)
            if not words:
                return
        if words:
            if self._refuse_if_read_only():
                return
            self._links_arrived(words, "clipboard")
            return
        # Collect has already taken what is on the clipboard: pasting it too
        # would add it twice - and a copied caption would open the "nothing to
        # add" box.
        if taken:
            self._flash(collect.PASTE_NOT_NEEDED, "info")
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
        focused = self._focused_section()
        if focused is not None:
            # Nothing under the pointer took it - the category's header, the
            # focus bar, the page's margin - and the category opened out is
            # the only one on show.
            self.accept_payload_into(event.mimeData(), focused)
            return
        self.accept_payload(event.mimeData())

    # ------------------------------------------------------------- actions
    # Every handler below serves two lists: the press report's, and a category
    # of the sentiment board opened out as a list (see _list_pool). ``pool`` is
    # the board's pool when the gesture came from that list and None for the
    # press report, so the report's own calls are exactly what they were. The
    # history and the list on screen follow the pool.
    def _list_pool(self):
        """The clippings the list on screen, the navy bar and the list's
        keys act on: the press report's in its own interface, the board's
        while one of its categories is opened out as a list, and nothing at
        all while the board shows its four columns of cards."""
        if self.mode == "standard":
            return self.model
        board = getattr(self, "board", None)
        if self.mode == "sentiment" and board is not None and board.focused:
            return self.board_model
        return None

    def _list_for(self, pool):
        """The list that shows a pool: a category's, for the board's."""
        board = getattr(self, "board", None)
        if (board is not None and pool is not None
                and pool is getattr(self, "board_model", None)):
            return board.focus_list
        return self.list

    def _sync_board_scope(self) -> bool:
        """Show in the category's list what the board is showing: one
        category, in the division on show - or the whole pool, closed.

        Asked often (every focus change, division change and recount) and
        does nothing unless the answer changed. A change starts the list
        afresh: the text half typed in it is kept, and the ticks, the filter
        and the shift-click anchor belong to what it showed before. Returns
        True when it changed the scope, having counted everything again.
        """
        board = getattr(self, "board", None)
        pool = getattr(self, "board_model", None)
        if (board is None or pool is None
                or getattr(self, "_scope_changing", False)):
            return False
        wanted = None
        if board.focused:
            try:
                # The board's own division as it is: "" and ALL_DIVISIONS
                # are two different things to a Scope (see model.Scope).
                wanted = Scope(Section(board.focused), board.active)
            except ValueError:
                wanted = None
        if wanted == pool.scope:
            return False
        # Not "was": the filter bar's blockSignals below reuses that name.
        left_scope = pool.scope
        self._scope_changing = True
        try:
            board.focus_list.commit_editor()
            pool.set_scope(wanted)
        finally:
            self._scope_changing = False
        bar = getattr(self, "board_filter_bar", None)
        if bar is not None:
            was = bar.blockSignals(True)
            try:
                bar.clear()
            finally:
                bar.blockSignals(was)
            bar.hide()
        button = getattr(self, "board_filter_btn", None)
        if button is not None and button.isChecked():
            was = button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(was)
        self._board_last_clicked_id = None
        # Pairs found over the category that was on show are not this one's:
        # its review would delete clippings nobody can see.
        self._forget_board_duplicates()
        self._let_board_request_go(left_scope, wanted)
        if wanted is not None:
            self._offer_board_marks()
        board.focus_list.refresh_height()
        self._update_counts()
        if wanted is not None:
            self.recheck_duplicates(pool=pool)
        return True

    def _let_board_request_go(self, was, now) -> None:
        """A category's check that has not started yet belongs to the category
        it was asked over, and goes when that category does.

        Letting it go only while it waited in _duplicates_waiting was not
        enough. Once the press report's pass ends, _pass_over puts it on the
        board's timer, and a category opened in those 400ms was checked in its
        place: answered out loud as if its own button had been pressed, and
        with Check automatically off, read though nobody asked (D3 review). So
        the timer is stopped as well; Check automatically asks afresh for the
        category now on show (_sync_board_scope). A pass already under way is
        left to its finish, which sees the change (_finish_board_check).
        """
        waiting = "board" in self._duplicates_waiting
        self._duplicates_waiting.discard("board")
        timer = self._board_duplicate_timer
        armed = timer is not None and timer.isActive()
        if armed:
            timer.stop()
        # Nothing was forgotten for it: that happens when its pass starts.
        self._fresh_board = None
        if self._is_board(self._duplicate_pool):
            return
        pressed, self._board_out_loud = self._board_out_loud, False
        if pressed and (waiting or armed) and was is not None:
            # Said, because the button was pressed and is otherwise never
            # answered.
            self._flash(f"{was.column.value}'s duplicate check was not run: "
                        f"{self._scope_change_words(was, now)}.", "info")

    @staticmethod
    def _scope_change_words(was, now) -> str:
        """Why a category's check was dropped, in the words of the screen."""
        if now is None:
            return "the category was closed"
        if now.column != was.column:
            return f"{now.column.value} was opened"
        return "the division changed"

    def _board_focus_changed(self) -> None:
        """A category opened or closed, or the division changed."""
        if not self._sync_board_scope():
            self._sync_fold_buttons()
            self._sync_english_button()
            self._update_selection_ui()
            self._place_floating()
        # Collect's bar names the column a collected photo goes in, which is
        # the one opened out.
        collector = getattr(self, "collector", None)
        if collector is not None:
            collector.refresh()

    def _reveal_in_board_list(self, clip_id: int) -> None:
        """Bring a clipping that arrived without a hand on it - collected from
        WhatsApp, or a captured link - into view in a category's list. The
        list stands in the board's page, so it is the page that moves, and
        not yet: see _reveal_on_page for why three times."""
        def go() -> None:
            board = getattr(self, "board", None)
            if self.mode != "sentiment" or board is None or not board.focused:
                return
            at_row = self.board_model.entry_row_for_clip(clip_id)
            if at_row < 0:
                return
            board.focus_list.scrollTo(self.board_model.index(at_row, 0))

        for wait_ms in (0, 160, 450):
            QTimer.singleShot(wait_ms, self._deferred(go))

    def _list_end(self, top: bool) -> None:
        """Home and End: to the ends of the list on screen."""
        if self._list_pool() is self.board_model:
            page = self.board.page
            if top:
                page.to_work()
            else:
                bar = page.verticalScrollBar()
                bar.setValue(bar.maximum())
            return
        if top:
            self.list.scrollToTop()
        else:
            self.list.scrollToBottom()

    def _on_clip_action(self, name: str, clip_id: int, pool=None) -> None:
        model = pool if pool is not None else self.model
        if pool is not None and model.row_for(clip_id) is None:
            return
        stack = self.stack_for(model)
        view = self._list_for(model)
        if name == "reread":
            self._reread_headline(clip_id)
            return
        if name == "find_read":
            self._find_reading(clip_id)
            return
        if name == "delete":
            stack.push(commands.RemoveClips(model, [clip_id]))
            self._flash("Clipping deleted — Ctrl+Z brings it back.", "info")
        elif name == "rotate":
            stack.push(commands.Rotate(model, [clip_id]))
        elif name == "split":
            stack.push(commands.Split(model, clip_id))
            self._flash("Split in two — Ctrl+Z undoes it.", "info")
        elif name == "merge":
            # The clipping the list shows under this one. In a category of
            # the board that is the next one in the category: the next one in
            # the pool is as likely to be another category's.
            below = model.neighbour_below(clip_id)
            if below is None:
                return
            stack.push(commands.Merge(model, [clip_id, below]))
        elif name == "english":
            self._put_in_english([clip_id], pool=pool)
        elif name == "add_title":
            row = model.entry_row_for_clip(clip_id)
            if row >= 0:
                view.edit_field(row, "label")
        elif name in ("edit_url", "add_url"):
            # Reachable even on a card with no address box showing, which is
            # every freshly pasted screenshot - otherwise there is nowhere to
            # put the link the story came from.
            row = model.entry_row_for_clip(clip_id)
            if row >= 0:
                view.edit_field(row, "url")
        elif name in ("move_top", "move_up", "move_down", "move_bottom"):
            if self._lens_holds(model):
                return
            where = name.replace("move_", "")
            # Within the category, in a category's list: the helper works the
            # order out over its clippings and leaves every other one in place.
            rows = commands.move_relative(model, [clip_id], where)
            stack.push(commands.Arrange(model, rows, "Clipping reordered",
                                        moved_ids=[clip_id]))

    def _on_group_action(self, name: str, ident: str, pool=None) -> None:
        """Act on the one run of clippings under the header that was clicked.

        Addressing by key alone would sweep up a second run elsewhere in the list
        that happens to share it, which a re-filing drop can easily create.
        """
        model = pool if pool is not None else self.model
        stack = self.stack_for(model)
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
            stack.push(commands.Rotate(model, ids))
        elif name == "group_delete":
            if self._confirm_delete(len(ids)):
                stack.push(commands.RemoveClips(model, ids))
        elif name in ("group_top", "group_up", "group_down", "group_bottom"):
            # Never under a lens. move_group_relative matches a file by its
            # clippings being one unbroken run; hide one of them and the match
            # fails, and it quietly degrades to nudging a single row - the exact
            # twenty-clicks-for-one bug its own comment records was fixed.
            if self._lens_holds(model):
                return
            rows = commands.move_group_relative(
                model, ids, name.replace("group_", ""))
            stack.push(commands.Arrange(model, rows, "File reordered",
                                        moved_ids=ids))

    def _on_label_edited(self, clip_id: int, text: str, pool=None) -> None:
        """The headline, which prints above the picture.

        The card has a box for this and a box for the address, so neither has to
        guess at the other from what was typed. That guessing is what made a
        half-typed address - "https:/", before the second slash - land as a
        headline for as long as it took to type the next character.
        """
        model = pool if pool is not None else self.model
        # The box can be committed by the switch that replaces its newspad, and
        # arrive after the clipping it belonged to has left the window.
        if model.row_for(clip_id) is None:
            return
        clip = model.by_id(clip_id)
        stack = self.stack_for(model)

        # A web address typed into the headline box is an address, whatever box
        # it was typed into. Screenshots arrive with no caption and no link, so
        # the card shows only the headline box - and that is where somebody
        # pasting the story's address will put it. Left as a headline it prints
        # above the picture as if it were the story's title, and the real link
        # prints underneath as well: the same address twice on the page.
        typed = (text or "").strip()
        if typed and looks_like_url(typed):
            if typed != clip.url.strip():
                stack.push(commands.EditUrl(model, clip_id, typed))
                self._flash("That looks like a web address, so it has gone in "
                            "the link box — it prints under the picture.", "info")
            if clip.label.strip():
                # and it must not stay in the headline as well
                stack.push(commands.EditLabel(model, clip_id, ""))
            # The boxes follow the text. Opening the headline box on an unnamed
            # clipping had switched that box on, and nothing switched it off
            # when what was typed into it turned out to be an address - so the
            # card was left with an empty headline box above the link, for no
            # reason anybody could see. Put away the box that was emptied and
            # show the one that was filled.
            if not clip.effective_label.strip():
                clip.show_title_box = False
            clip.show_url_box = True
            model.refresh_clip(clip_id)
            self._list_for(model).refresh_height()
            return

        if text == clip.effective_label:
            return
        stack.push(commands.EditLabel(model, clip_id, text))

    def _on_url_edited(self, clip_id: int, text: str, pool=None) -> None:
        """The address, which prints under the picture as a working link."""
        model = pool if pool is not None else self.model
        if model.row_for(clip_id) is None:
            return
        clip = model.by_id(clip_id)
        if text.strip() == clip.url.strip():
            return
        self.stack_for(model).push(
            commands.EditUrl(model, clip_id, text.strip()))

    def _on_reorder(self, ids: list[int], target: int, pool=None) -> None:
        model = pool if pool is not None else self.model
        if pool is not None:
            # A drop on a category's list: only its own clippings, and never
            # while a filter is on - what is on screen is not the real order.
            ids = [i for i in ids if model.row_for(i) is not None]
            if not ids or self._lens_holds(model):
                return
        # ``target`` is a place in the whole pool, as the list works it out;
        # in a category the helper turns it into a place in the category.
        rows = commands.move_to(model, ids, target)
        many = f"{len(ids)} clippings reordered" if len(ids) > 1 else "Clipping reordered"
        # A drop says "put it here", and here has a priority. Dropped among the
        # 1s it becomes a 1 - otherwise the list would come straight back out
        # of order, because the list IS the sort. Dropped among its own
        # priority, which is every drop until somebody sets one, only the place
        # changes.
        landed = commands.level_at(rows, ids)
        levels = {commands.priority_of(model.by_id(i)) for i in ids
                  if model.by_id(i) is not None}
        moved = landed is not None and levels != {landed}
        self.stack_for(model).push(commands.Arrange(
            model, rows,
            f"{many}, priority {landed}" if moved and landed else
            (f"{many}, priority cleared" if moved else many),
            moved_ids=ids, level=landed if moved else None))
        if moved:
            self._flash(
                (f"Moved into priority {landed} — Ctrl+Z puts it back." if landed
                 else "Moved, and its priority cleared — Ctrl+Z puts it back."), "info")
            return
        self._flash("Moved — Ctrl+Z puts it back.", "info")

    def _on_selection_toggled(self, clip_id: int, additive: bool, ranged: bool,
                              pool=None) -> None:
        model = pool if pool is not None else self.model
        # Each list keeps its own end of a shift-click run.
        board = model is getattr(self, "board_model", None)
        if board and model.row_for(clip_id) is None:
            return
        last = self._board_last_clicked_id if board else self._last_clicked_id
        if ranged and last is not None:
            model.select_range(last, clip_id)
        elif additive:
            model.set_selected([clip_id], not model.is_selected(clip_id))
        else:
            model.select_only([clip_id])
        if board:
            self._board_last_clicked_id = clip_id
        else:
            self._last_clicked_id = clip_id

    # -------------------------------------------------------------- batch
    def _selected_ids(self, pool=None) -> list[int]:
        """The ticked clippings of a list, in the order it shows them - by
        default the list the navy bar acts on (see _list_pool)."""
        if pool is None:
            pool = self._list_pool() or self.model
        return [r.id for r in pool.scoped_rows() if r.id in pool.selected]

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

    def _put_in_english(self, ids: list, summarise: bool = False, pool=None) -> list:
        """Each card's Hindi into English, one undo step per card - or one
        for the lot when several are done together. Returns the lines said."""
        model = pool if pool is not None else self.model
        stack = self.stack_for(model)
        plans = []
        for clip_id in ids:
            if model.row_for(clip_id) is None:
                continue
            plan = copied.english_for(model.by_id(clip_id), self.name_index)
            plans.append((clip_id, plan))
        doing = [(clip_id, plan) for clip_id, plan in plans if plan.changes]
        # One line per card that had Hindi on it - done or left alone, and
        # why - in list order. A card with no Hindi is not a line. Numbered as
        # the list numbers it: in a category of the board, its place there.
        lines = [f"No. {model.number_of(clip_id)}: {plan.said}."
                 for clip_id, plan in plans if not plan.nothing]
        if not doing:
            self._flash("Nothing on that card is in Hindi." if len(ids) == 1
                        else "No card has Hindi in a field the report prints.",
                        "info")
            return lines
        if len(doing) > 1:
            stack.beginMacro(f"{len(doing)} cards put in English")
        try:
            for clip_id, plan in doing:
                stack.push(commands.PutInEnglish(
                    model, clip_id,
                    {field: new for field, (_old, new) in plan.changes.items()}))
        finally:
            if len(doing) > 1:
                stack.endMacro()
        self._refresh_filter_choices()
        self._list_for(model).viewport().update()
        flagged = sum(1 for _i, plan in doing if plan.flagged)
        said = (f"Put {len(doing)} card{'s' if len(doing) != 1 else ''} in English"
                + (f" — {flagged} spelt out by rule, flagged for a check"
                   if flagged else "") + ". Ctrl+Z puts the Hindi back.")
        self._flash(said, "good")
        if summarise:
            from .english import show_summary
            show_summary(self, lines, said)
        return lines

    def _put_all_in_english(self, pool=None) -> None:
        # Every card of the list: in a category of the board, that category's
        # and nobody else's.
        model = pool if pool is not None else self.model
        ids = [row.id for row in model.scoped_rows()
               if row.clip is not None and copied.needs_english(row.clip)]
        self._put_in_english(ids, summarise=True, pool=pool)

    def _sync_english_button(self) -> None:
        button = getattr(self, "english_btn", None)
        if button is not None:
            button.setVisible(self.mode == "standard" and any(
                row.clip is not None and copied.needs_english(row.clip)
                for row in self.model.rows))
        board_button = getattr(self, "board_english", None)
        if board_button is not None:
            pool = self.board_model
            board_button.setVisible(pool.scope is not None and any(
                row.clip is not None and copied.needs_english(row.clip)
                for row in pool.scoped_rows()))

    def _found_priority(self, ids: list, level: int) -> None:
        """A priority for every ticked search result at once. One step."""
        pool = self._list_pool()
        if pool is None:
            return
        ids = [i for i in ids if pool.row_for(i) is not None]
        if not ids:
            return
        self.stack_for(pool).push(commands.SetPriority(pool, ids, level))
        self._update_counts()
        self.find_bar.refresh()

    def _found_arrange(self, ids: list, where: str) -> None:
        """The ticked search results to the top or the bottom of the list."""
        self._batch_move(where, ids)
        self.find_bar.refresh()

    def _batch_move(self, where: str, ids: list | None = None) -> None:
        pool = self._list_pool()
        if ids is None:
            ids = self._selected_ids(pool) if pool is not None else []
        elif pool is not None:
            ids = [i for i in ids if pool.row_for(i) is not None]
        if not ids or pool is None:
            return
        if self._lens_holds(pool):
            return
        rows = commands.move_relative(pool, ids, where)
        self.stack_for(pool).push(
            commands.Arrange(pool, rows, f"{len(ids)} clippings moved"
                             if len(ids) != 1 else "Clipping moved",
                             moved_ids=ids)
        )

    def _all_excluded(self, ids: list, pool=None) -> bool:
        pool = pool if pool is not None else (self._list_pool() or self.model)
        held = [i for i in ids if pool.row_for(i) is not None]
        return bool(held) and not any(pool.by_id(i).include for i in held)

    def _batch_exclude(self) -> None:
        self._toggle_included(self._selected_ids())

    def _toggle_included(self, ids: list, pool=None) -> None:
        """Take these clippings out of the report - or, when every one of them
        is out already, put them all back. The button and the menu say which.

        A mixed selection is taken OUT, never put back in. Putting back a
        clipping the duplicate check left out also marks it "not a duplicate"
        for good (see SetIncluded), and nobody who ticked five clippings and
        pressed a button meant that for the one among them they had not
        noticed was out.
        """
        listed = self._list_pool()
        pool = pool if pool is not None else listed
        if not ids or pool is None or pool is not listed:
            return              # the bar and the list menu act on the list on show
        ids = [i for i in ids if pool.row_for(i) is not None]
        if not ids:
            return
        stack = self.stack_for(pool)
        if self._all_excluded(ids, pool):
            stack.push(commands.SetIncluded(pool, ids, True))
            return
        going = [i for i in ids if pool.by_id(i).include]
        stack.push(commands.SetIncluded(pool, going, False))
        if len(going) != len(ids):
            out = len(ids) - len(going)
            self._flash(
                f"Excluded {len(going)} — the other {out} "
                f"{'were' if out != 1 else 'was'} already out of the report.",
                "info")

    def _sync_exclude_button(self) -> None:
        pool = self._list_pool() or self.model
        back = self._all_excluded(self._selected_ids(pool), pool)
        self.batch_exclude.setText("Include" if back else "Exclude")
        self.batch_exclude.setToolTip(
            "Put these back into the report" if back else
            "Leave these out of the report — they stay in the list, greyed")

    @staticmethod
    def _elide_middle(text: str, most: int) -> str:
        return text if len(text) <= most else (
            text[:most - 20].rstrip() + " … " + text[-17:].lstrip())

    def _move_line(self, run, ids: list, part: str, number_it: bool, pool=None):
        """One file's line in the Move to list: (words, can it be chosen, tip).

        The file's own header words on the left - '&' doubled, or Qt would take
        it for a keyboard shortcut and swallow it - and on the right, after a
        tab, how many it holds and anything that stops a move there.
        """
        model = pool if pool is not None else self.model
        name = self._elide_middle(run.title, 56).replace("&", "&&") + part
        count = f"{run.count} clip" + ("s" if run.count != 1 else "")
        if number_it:
            first = model.number_of(run.rows[0].id)
            last = model.number_of(run.rows[-1].id)
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

    def _fill_category_actions(self, menu: QMenu, ids: list) -> None:
        """The board's other three categories, for clippings of the one opened
        out: the list's way of doing what dragging a card to another column
        does, since the other columns are not on screen to drag to. (How many
        ticked clippings a filter hides is said once, at the top of the
        right-click menu, since every entry there leaves them alone.)"""
        scope = self.board_model.scope
        menu.addAction("Another category:").setEnabled(False)
        for column in sentiment.COLUMNS:
            if scope is not None and column is scope.column:
                continue
            label = theme.SENTIMENT_STYLES[column.value]["label"]
            action = menu.addAction(label)
            action.setEnabled(bool(ids))
            action.setToolTip(f"File these under {label}. They leave this list; "
                              "Ctrl+Z brings them back.")
            action.triggered.connect(
                lambda _checked=False, value=column.value, chosen=list(ids):
                self._assign_sentiment(chosen, value))

    def _fill_move_menu(self, menu: QMenu, ids: list, pool=None,
                        categories: bool = True) -> None:
        """The file groups these clippings can be moved into, as they are now.

        What the earlier AI Studio version called its categories: every file in
        the list, and "Clipboard images" for everything added by hand, in list
        order. Filled as the menu opens, so it is always the list as it stands.

        For a category of the board opened out as a list, the other three
        categories come first (unless ``categories`` is False, for a menu that
        offers them elsewhere) and then that category's own files.
        """
        menu.clear()
        model = pool if pool is not None else (self._list_pool() or self.model)
        if model.lens.busy:
            menu.addAction("Clear the filter first — while one is on, what you "
                           "see is not the real order").setEnabled(False)
            return
        wanted = set(ids)
        ids = [r.id for r in model.scoped_rows() if r.id in wanted]
        n = len(ids)
        menu.addAction(f"Move {n} clipping{'s' if n != 1 else ''} to:").setEnabled(False)
        menu.addSeparator()
        runs = model.file_runs()
        if model is self.board_model:
            if categories:
                self._fill_category_actions(menu, ids)
                if len(runs) <= 1:
                    return
                menu.addSeparator()
            column = model.scope.column.value if model.scope is not None else ""
            menu.addAction(f"Another file in {column}:" if column
                           else "Another file:").setEnabled(False)
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
            text, enabled, tip = self._move_line(run, ids, part, number_it, model)
            headed = headed or text.split("\t")[-1].startswith("would move")
            action = menu.addAction(text)
            action.setEnabled(enabled and n > 0)
            action.setToolTip(tip)
            action.triggered.connect(
                lambda _checked=False, ident=run.ident, first=run.rows[0].id,
                into=model: self._move_into(ids, ident, first, pool=into))
        if headed:
            menu.addSeparator()
            menu.addAction("Greyed: moving them there would change where a "
                           "heading prints in the report.").setEnabled(False)

    def _move_into(self, ids: list, ident: str, first_id: int = -1, pool=None) -> None:
        """File these clippings under another file's group, at its end.

        One undo step (MoveIntoFile). Refused, and said so, when it would
        change where any section heading prints - see plan_move_into.
        """
        listed = self._list_pool()
        model = pool if pool is not None else listed
        if model is None or model is not listed:
            return              # the bar and its menu belong to the list on show
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
        self.stack_for(model).push(commands.MoveIntoFile(model, plan, text))
        # After the push: the push moves the undo index, which hides the note.
        said = self._move_message(plan, model)
        self._flash(said, "good")
        self._show_move_note(said)

    def _move_message(self, plan, pool=None) -> str:
        model = pool if pool is not None else self.model
        n = len(plan.moving)
        places = [model.number_of(i) for i in plan.moving]
        where = (f"No. {min(places)}–{max(places)}" if n > 1
                 else f"No. {places[0]}")
        said = (f"Moved {n} into {self._elide_middle(plan.run_title, 48)} — now "
                f"{where}. Ctrl+Z puts {'them' if n != 1 else 'it'} back.")
        for _from_id, to_id, words in plan.handoffs:
            said += f" {words} now prints over No. {model.number_of(to_id)}."
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

    def _shift_found_to(self, row_ids: list, number: int) -> None:
        """The ticked search results, copied into another newspad.

        The same copy the selection bar and the preview make - the clippings
        stay where they are - so a cutting that belongs in two reports is
        found once and sent once.
        """
        pool = self.pool()
        which = "sentiment" if pool is getattr(self, "board_model", None) else "standard"
        try:
            self.save_session()
        except Exception:  # noqa: BLE001
            pass
        sent, trouble = 0, ""
        for clip_id in list(row_ids):
            row = pool.row_for(clip_id)
            if row is None or row.clip is None:
                continue
            try:
                newspads.deliver(
                    number, row.clip, pool=which,
                    thumb_png=getattr(row, "thumb_png", b"") or b"",
                    source_name=f"Newspad {self.newspad}")
                sent += 1
            except newspads.HandoverError as bad:
                trouble = str(bad)
                break
            except Exception as bad:  # noqa: BLE001
                trouble = f"{type(bad).__name__}: {bad}"
                break
        if trouble and not sent:
            self._flash(trouble, "bad")
            return
        said = (f"{sent} found clipping{'s' if sent != 1 else ''} copied into "
                f"Newspad {number} — still here too.")
        if trouble:
            said += f" The rest stopped: {trouble}"
        self._flash(said, "good" if not trouble else "bad")

    def _go_to_clip(self, row_id: int) -> None:
        """Scroll the list to a clipping and open it - what picking a search
        result does. The clipping is not selected or ticked: finding one is
        not the same as choosing it."""
        pool = self.pool()
        if pool.row_for(row_id) is None:
            return
        view = self.list if self.mode == "standard" else None
        if view is not None:
            try:
                # The list is one long page of entries; the clipping's own
                # entry is the one carrying its row.
                model = view.model()
                for place in range(model.rowCount()):
                    index = model.index(place, 0)
                    entry = index.data(Qt.UserRole)
                    row = getattr(entry, "row", None)
                    if row is not None and getattr(row, "id", None) == row_id:
                        view.scrollTo(index)
                        break
            except Exception:  # noqa: BLE001 - a view that cannot, still opens
                pass
        self.open_preview(row_id)

    def _say_last_action(self) -> None:
        """The last thing done on the interface that is open.

        Straight off that interface's own undo stack, so it is always the
        step Ctrl+Z would take back, and one Ctrl+Z later it is the step
        before it. Each interface has its own stack, so the board and the
        press report each report their own work.
        """
        line = getattr(self, "last_action", None)
        if line is None:
            return
        stack = self.stack_for(self.pool())
        said = ""
        try:
            if stack is not None and stack.canUndo():
                said = str(stack.undoText() or "").strip()
        except Exception:  # noqa: BLE001 - a caption is never worth a crash
            said = ""
        if said:
            # The commands name themselves in the past tense already
            # ("Grouped 5 posts by platform", "All clippings cleared").
            line.setText(f"Last: {said[0].upper()}{said[1:]}")
            line.setToolTip(f"The last thing done here: {said}. Ctrl+Z takes "
                            "it back, and this then says the one before it.")
        else:
            line.setText("")
            line.setToolTip("Nothing has been done to this newspad yet.")

    def _hide_move_note(self, *_args) -> None:
        note = getattr(self, "move_note", None)
        if note is not None and note.isVisible():
            self._move_note_timer.stop()
            note.hide()

    def _batch_delete(self) -> None:
        pool = self._list_pool()
        if pool is None:
            return          # the batch bar belongs to the list on show
        self._delete_many(self._selected_ids(pool), pool)

    def _delete_many(self, ids: list, pool) -> None:
        """Several clippings out of a list in one step, once asked: the navy
        bar's ticks, or the clippings a category's right-click menu names -
        under a filter, the ticked ones on screen and not those it hides."""
        if pool is None or pool is not self._list_pool():
            return          # the bar and the list menu act on the list on show
        ids = [i for i in ids if pool.row_for(i) is not None]
        if not ids:
            return
        if self._confirm_delete(len(ids)):
            self.stack_for(pool).push(commands.RemoveClips(pool, ids))
            self._flash(f"{len(ids)} deleted — Ctrl+Z brings them back.", "info")

    def _merge_selected(self) -> None:
        pool = self._list_pool()
        if pool is None:
            return
        ids = self._selected_ids(pool)
        if len(ids) < 2:
            self._flash("Pick at least two clippings to merge.", "info")
            return
        self.stack_for(pool).push(commands.Merge(pool, ids))
        self._flash(f"{len(ids)} merged into one — Ctrl+Z undoes it.", "good")

    def _bulk_field(self, field: str, ids: list | None = None) -> None:
        """Set newspaper or Set edition on the ticked clippings - or, from a
        category's right-click menu, on ``ids``: the row clicked when nothing
        is ticked."""
        pool = self._list_pool()
        if pool is None:
            return
        if ids is None or pool is not self.board_model:
            ids = self._selected_ids(pool)
        else:
            ids = [i for i in ids if pool.row_for(i) is not None]
        if not ids:
            return
        options = (
            self.name_index.newspaper_names if field == "newspaper"
            else self.name_index.edition_names
        )
        current = getattr(pool.by_id(ids[0]), field)
        if pool is self.board_model:
            # open(), never exec(): nothing the board shows may hold up the
            # window. Modal to the window, so the ticks cannot change under
            # it; the clippings are fixed now and applied when it is answered.
            box = QInputDialog(self)
            box.setWindowTitle(f"Set {field}")
            box.setLabelText(f"{field.title()} for {len(ids)} clipping(s):")
            box.setComboBoxItems(options)
            box.setComboBoxEditable(True)
            box.setTextValue(current if current in options
                             else (options[0] if options else ""))
            box.textValueSelected.connect(
                lambda value, chosen=list(ids):
                self._set_field_on(pool, chosen, field, value))
            box.finished.connect(box.deleteLater)
            box.open()
            return
        value, ok = QInputDialog.getItem(
            self, f"Set {field}", f"{field.title()} for {len(ids)} clipping(s):",
            options, options.index(current) if current in options else 0, True,
        )
        if not ok:
            return
        self._set_field_on(pool, ids, field, value)

    def _set_field_on(self, pool, ids: list, field: str, value: str) -> None:
        """One step naming every one of these clippings' newspaper or edition.
        Any deleted while the picker was open is left out."""
        ids = [i for i in ids if pool.row_for(i) is not None]
        if not ids:
            return
        value = value.strip()
        if field == "newspaper":
            self.name_index.add_newspaper(value)
        else:
            self.name_index.add_edition(value)
        self.stack_for(pool).push(
            commands.SetFieldOnMany(pool, ids, field, value)
        )

    def _select_all(self) -> None:
        pool = self._list_pool()
        if pool is None:
            return          # the batch bar belongs to the list on show
        # Everything ON SCREEN. With a filter on, "all" cannot mean the
        # clippings it is hiding: somebody who has narrowed the list to the
        # regional papers, pressed this and then pressed Delete would lose the
        # whole morning, and there would have been nothing on screen to warn
        # them. So it selects what they can see, and says how many that was.
        # In a category of the board, "all" is that category's.
        shown = pool.visible_rows()
        pool.select_only([r.id for r in shown])
        if pool.lens.busy:
            self._flash(f"Selected the {len(shown)} clipping(s) on screen. "
                        f"The other {len(pool.scoped_rows()) - len(shown)} are "
                        f"hidden by the filter and were not touched.", "info")

    def _toggle_select_all(self, pool=None) -> None:
        listed = self._list_pool()
        pool = pool if pool is not None else listed
        if pool is None or pool is not listed:
            return          # the batch bar belongs to the list on show
        shown = pool.visible_rows()
        if shown and len(pool.selected) == len(shown):
            pool.clear_selection()
        else:
            self._select_all()

    def _clear_all(self) -> None:
        """Clear the interface on show, not always the press report."""
        if self.mode == "sentiment" and getattr(self, "board", None) is not None:
            # Clear all is on the press report's card, which is not on show
            # while the board is, so this is only ever reached by a call. It
            # must not then empty the board's whole pool - every division,
            # behind a box saying "from the list" over a category of four. The
            # board's own clear answers instead: what the board is showing,
            # asked the way the board asks.
            self._clear_division(self.board.active)
            return
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
    def _reread_headline(self, clip_id: int) -> None:
        """Read this clipping's headline off its picture again.

        As it PRINTS - trim and turn and all - because that is the picture the
        report shows and the one a second reading should be of: a crooked scan
        straightened, or a strip of the neighbouring column trimmed away, is
        exactly why somebody presses this.
        """
        pool = self.pool_for(clip_id)
        row = pool.row_for(clip_id) if pool is not None else None
        if row is None or row.clip is None:
            return
        from ..core import ocr, ocrworker

        if not ocr.available():
            self._flash(f"The reader is not available ({ocr.why_not()}).", "bad")
            return
        # NEVER ON THIS THREAD. It used to read right here, and the window
        # stopped until it was done - a second, or five on a big scan. The
        # picture goes to a helper process (see core/ocrworker), the same two
        # stages as every other reading: find the headline by looking, then
        # read only that. The answer comes back to _reread_done.
        busy = self.__dict__.setdefault("_reading_now", set())
        if clip_id in busy:
            return                  # already being read: one press is enough
        busy.add(clip_id)
        was = str(getattr(row.clip, "ocr_text", "") or "")
        data = ocr._as_printed(row.clip)
        preview = getattr(self, "preview", None)
        if (preview is not None and preview.isVisible()
                and preview.row is not None and preview.row.id == clip_id):
            preview.reading(True)
        # A reader of its own, made here on the main thread, only for when no
        # helper will start - building one anywhere else is not allowed.
        engine = None
        if not ocrworker.available():
            made = ocr.build_engines(1)
            engine = made[0] if made else None
        relay = self._reading_relay()

        def work():
            found = ocrworker.read_headline(data)
            if found is None:
                try:
                    found = (ocr.headline_with(engine, data)
                             if engine is not None else ocr.Headline())
                except Exception:  # noqa: BLE001 - it will not read
                    found = ocr.Headline()
            if engine is not None:
                ocr.close_engines([engine])
            relay.done.emit(clip_id, found.text, int(found.confidence),
                            found.engine or "", was)

        import threading

        threading.Thread(target=work, name="read-again", daemon=True).start()

    def _read_box(self, clip_id: int, box: tuple) -> None:
        """Read the words inside the preview's OCR box - never on this thread."""
        pool = self.pool_for(clip_id)
        row = pool.row_for(clip_id) if pool is not None else None
        if row is None or row.clip is None:
            return
        from ..core import ocr, ocrworker

        data = ocr._as_printed(row.clip)
        engine = None
        if not ocrworker.available():
            made = ocr.build_engines(1)
            engine = made[0] if made else None
        relay = self._reading_relay()

        def work():
            found = ocrworker.read_box(data, box)
            if found is None:
                try:
                    found = ocr.read_box(data, box, api=engine)
                except Exception:  # noqa: BLE001 - it will not read
                    found = ocr.Headline()
            if engine is not None:
                ocr.close_engines([engine])
            relay.boxed.emit(clip_id, found.text)

        import threading

        threading.Thread(target=work, name="read-box", daemon=True).start()

    def _box_done(self, clip_id: int, words: str) -> None:
        preview = getattr(self, "preview", None)
        if (preview is not None and preview.row is not None
                and preview.row.id == clip_id):
            preview.box_read(words)

    def _reading_relay(self):
        """What carries a reading back from its thread to this one."""
        relay = getattr(self, "_relay", None)
        if relay is None:
            from PySide6.QtCore import QObject, Signal

            class _Relay(QObject):
                done = Signal(int, str, int, str, str)
                boxed = Signal(int, str)

            relay = self._relay = _Relay(self)
            relay.done.connect(self._reread_done)
            relay.boxed.connect(self._box_done)
        return relay

    def _reread_done(self, clip_id: int, text: str, confidence: int,
                     engine: str, was: str) -> None:
        """A reading has come back: put it on the clipping and say so."""
        from ..core import ocr

        getattr(self, "_reading_now", set()).discard(clip_id)
        pool = self.pool_for(clip_id)
        row = pool.row_for(clip_id) if pool is not None else None
        preview = getattr(self, "preview", None)
        showing = (preview is not None and preview.isVisible()
                   and preview.row is not None and preview.row.id == clip_id)
        if preview is not None and showing:
            preview.reading(False)
        if row is None or row.clip is None:
            return
        row.clip.ocr_text = text
        row.clip.headline_confidence = confidence
        row.clip.ocr_engine = engine or ocr.stamp()
        now = text.strip()
        if showing:
            preview.ocr_edit.setText(now)
            preview.find_read_btn.setEnabled(bool(now))
            preview.told("Read again" if now else "Nothing could be read")
        pool.refresh_all()
        self.touch_session()
        if not now:
            self._flash("Nothing could be read off that picture.", "info")
        elif now == was.strip():
            self._flash("Read again — the same words came back.", "info")
        else:
            self._flash(f"Read again: {now[:70]}", "good")

    def _find_reading(self, clip_id: int) -> None:
        """Search the list for this clipping's headline.

        It used to COPY the headline into the label, and the label is for
        the newspaper's name: nothing puts a headline there any more. What a
        headline is good for is finding the same story again - sent twice,
        or by two divisions.
        """
        pool = self.pool_for(clip_id)
        row = pool.row_for(clip_id) if pool is not None else None
        if row is None or row.clip is None:
            return
        words = str(getattr(row.clip, "ocr_text", "") or "").strip()
        if not words:
            self._flash("There is nothing read off that picture yet.", "info")
            return
        self._find_words(words)

    def _find_words(self, words: str) -> None:
        """Put these words in the search field and look."""
        bar = getattr(self, "find_bar", None)
        if bar is None:
            return
        bar.field.setText(" ".join(words.split()))
        bar._look()
        bar.field.setFocus()

    def _ocr_field_switched(self, on: bool) -> None:
        """The OCR headline switched on or off: every row and the preview.

        The rows change height with it - a row with its OCR box is one box
        taller - so the list is laid out again rather than only repainted,
        or the rows would keep the old heights with the boxes gone from them.
        """
        ocrfield.set_on(on)
        for view in (self.list, getattr(self.board, "focus_list", None)):
            if view is None:
                continue
            try:
                view.scheduleDelayedItemsLayout()
                view.viewport().update()
            except Exception:  # noqa: BLE001 - a view that is not there yet
                pass
        if self.preview is not None:
            self.preview.show_ocr(on)
        self._flash("OCR headline shown" if on else
                   "OCR headline hidden - the duplicate check still reads "
                   "the pictures")

    def _ocr_corrected(self, clip_id: int, words: str) -> None:
        """A reading corrected by hand. Kept on the clipping, so the duplicate
        check and the search both use the corrected words."""
        pool = self.pool_for(clip_id)
        row = pool.row_for(clip_id) if pool is not None else None
        if row is None or row.clip is None:
            return
        row.clip.ocr_text = words
        # MARKED AS THEIRS. Two things hang on the mark: the reader does not
        # read over it on the next check, and the check's own housekeeping
        # does not throw it out when the picture is turned or trimmed - which
        # it used to, taking a correction somebody had just typed with it.
        if words.strip():
            row.clip.ocr_engine = ocr.BY_HAND
            # The most reliable reading there is, so it is not held out of the
            # word comparison by a confidence left over from the machine.
            row.clip.headline_confidence = 100
        else:
            # Emptied on purpose: let the next check read the picture again.
            row.clip.ocr_engine = ""
            row.clip.headline_confidence = 0
        self.touch_session()

    def _copy_clip_picture(self, clip_id: int) -> None:
        """This clipping's picture, as it prints, on the clipboard.

        As it PRINTS, not as it arrived: clip.render() is the same call the
        exporters make, so a trimmed or turned clipping is copied trimmed and
        turned. Somebody pasting it into WhatsApp gets what the report would
        have shown them.
        """
        pool = self.pool_for(clip_id)
        row = pool.row_for(clip_id) if pool is not None else None
        if row is None or row.clip is None:
            return
        try:
            image = row.clip.render()
            if image.mode not in ("RGB", "RGBA", "L"):
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, "PNG")
            picture = QImage()
            picture.loadFromData(buffer.getvalue(), "PNG")
            if picture.isNull():
                raise ValueError("the picture could not be read")
            QApplication.clipboard().setImage(picture)
        except Exception as bad:  # noqa: BLE001 - one clipping, never the morning
            self._flash(f"That picture could not be copied ({bad}).", "bad")
            return
        self._flash("Picture copied — paste it wherever you need it.", "good")

    def _send_clip_to_newspad(self, clip_id: int, number: int) -> None:
        """A COPY of this clipping into another newspad's saved work.

        It is a copy: the clipping stays where it is. The other newspad is not
        loaded - only one ever is - so it is written into that newspad's own
        manifest and pictures, and it is there when somebody switches to it.
        Which list it joins is the one it is in here, so a board clipping
        arrives on that newspad's board.
        """
        pool = self.pool_for(clip_id)
        row = pool.row_for(clip_id) if pool is not None else None
        if row is None or row.clip is None:
            return
        which = "sentiment" if pool is getattr(self, "board_model", None) else "standard"
        # Its own newspad is saved first, so a picture it has never written to
        # disk is not the one thing the copy is missing.
        try:
            self.save_session()
        except Exception:  # noqa: BLE001 - the copy is what matters here
            pass
        try:
            held = newspads.deliver(
                number, row.clip, pool=which,
                thumb_png=getattr(row, "thumb_png", b"") or b"",
                source_name=f"Newspad {self.newspad}")
        except newspads.HandoverError as bad:
            self._flash(str(bad), "bad")
            return
        except Exception as bad:  # noqa: BLE001
            self._flash(f"It could not be put in Newspad {number} ({bad}).", "bad")
            return
        where = "board" if which == "sentiment" else "list"
        self._flash(
            f"Copied into Newspad {number}'s {where} — {held} clipping"
            f"{'s' if held != 1 else ''} there now. It is still here too.",
            "good")
        # Said on the preview as well, because the preview covers the window:
        # a message on the status line behind it is read by nobody.
        told = getattr(getattr(self, "preview", None), "told", None)
        if callable(told) and self.preview.isVisible():
            told(f"Sent to Newspad {number}")

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
            self.preview.priorityPicked.connect(self._preview_priority)
            self.preview.navigate.connect(self._preview_navigate)
            # A badged clipping shows the one it repeats beside it, named by
            # the file each came from; either can be opened, or the pair
            # taken to the review.
            self.preview.source_of = self._source_of
            self.preview.jumpRequested.connect(self.open_preview)
            # The review of the list the previewed clipping is in.
            self.preview.copyRequested.connect(self._copy_clip_picture)
            self.preview.rereadRequested.connect(self._reread_headline)
            self.preview.boxReadRequested.connect(self._read_box)
            self.preview.findRequested.connect(self._find_words)
            self.preview.ocrEdited.connect(self._ocr_corrected)
            self.preview.sendToNewspad.connect(self._send_clip_to_newspad)
            # Which newspad is open, asked every time a clipping is shown: the
            # window outlives a switch, and its newspad buttons must not.
            self.preview.newspad_here = lambda: self.newspad
            self.preview.reviewRequested.connect(
                lambda: self.review_duplicates(pool=self._preview_pool()))
        # Set before the row is shown: it decides whether the Section control
        # is the heading picker or the board's sentiment control, and showing
        # the row is what reads it.
        self.preview.for_board = model is getattr(self, "board_model", None)
        # And the pool it is in: the preview was made once, for whichever
        # opened it first, and the clipping beside a repeat - and the numbers
        # the two are called by - are looked up in this one.
        self.preview.model = model
        at, walk = self._preview_place(clip_id)
        # The counter must count what is on screen. With a filter on it used to
        # read "3 / 40" while the list showed nine.
        position = (at + 1) if at is not None else 0
        self.preview.show_row(row, position, len(walk))
        # Opening on a clipping is arriving at a place in the list.
        self._remember_after(clip_id)
        self.preview.show()
        self.preview.raise_()
        self.preview.activateWindow()

    def _refresh_preview(self, clip_id: int) -> None:
        row = self._preview_pool().row_for(clip_id)
        if self.preview and self.preview.isVisible() and row is not None:
            at, walk = self._preview_place(clip_id)
            self.preview.show_row(
                row, (at + 1) if at is not None else 0, len(walk))
            # Arriving at another clipping fixes a new place; drawing the same
            # one again - after a priority, a trim, a rename - does not.
            if clip_id != self._preview_at[0]:
                self._remember_after(clip_id)

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
        board = getattr(self, "board", None)
        if board is not None:
            board.focus_list.viewport().update()

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
        pool = self._preview_pool()
        position = pool.position_of(clip_id)
        if getattr(pool, "scope", None) is None:
            # The press report, and a card's preview over four columns: the
            # pool's own next row, filter or not, as it has always been.
            self._preview_stack().push(commands.RemoveClips(pool, [clip_id]))
            if pool.rows:
                following = pool.rows[min(position, len(pool.rows) - 1)]
                self._refresh_preview(following.id)
            elif self.preview:
                self.preview.close()
            return
        # A category of the board opened out as a list: the next clipping in
        # what the arrows walk, which is that category's. The pool's next row
        # is as likely another category's, and the preview would then go on
        # editing a clipping that is not on screen.
        at, _walk = self._preview_place(clip_id)
        self._preview_stack().push(commands.RemoveClips(pool, [clip_id]))
        walk = self._preview_walk()
        following = None
        if walk and at is not None:
            following = walk[min(at, len(walk) - 1)]
        elif walk:
            # It had already left the category - its Sentiment was changed
            # here - so it had no place in the walk. The first of the
            # category's clippings that stood after it, else the last.
            where = {row.id: index for index, row in enumerate(pool.rows)}
            following = next((row for row in walk
                              if where.get(row.id, -1) >= position), walk[-1])
        if following is not None:
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
        self._list_for(pool).refresh_height()
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
        if shown is not None and getattr(pool, "scope", None) is not None:
            # A category opened out as a list walks that category alone, even
            # when its last clipping has just left it: the whole board's pool
            # is not what was on screen.
            return list(shown)
        return list(shown) if shown else list(pool.rows)

    def _preview_place(self, row_id: int):
        """Where this clipping sits in the walk, or None if it is filtered out."""
        walk = self._preview_walk()
        for index, row in enumerate(walk):
            if row.id == row_id:
                return index, walk
        return None, walk

    def _remember_after(self, row_id: int) -> None:
        """The place in the list the preview has just arrived at: this clipping,
        and the one below it as the list stands now.

        Somebody going down a morning setting priorities is at a PLACE in the
        list, not on a clipping, and the place is fixed when they get there.
        Work it out when a bubble is pressed instead and the second press is
        wrong: the first press has already moved the clipping to the top, so
        "the one below it" becomes the clipping now shown as No. 2 - which is
        one they have already seen. Pressing a second bubble (or pressing the
        lit one to clear it) must not change which clipping comes next.
        """
        at, walk = self._preview_place(row_id)
        after = walk[at + 1].id if at is not None and at + 1 < len(walk) else None
        self._preview_at = (row_id, after)

    def _preview_priority(self, row_id: int, level: int) -> None:
        """A priority bubble was pressed in the preview.

        Two things happen and they are one step: the clipping is given the
        level, and it moves to where that level sits in the list. The walk does
        NOT follow it - see _remember_after for where the next one comes from.
        """
        pool = self._preview_pool()
        if pool.row_for(row_id) is None:
            return
        self.stack_for(pool).push(commands.SetPriority(pool, [row_id], level))
        # A trim half drawn over the picture is not thrown away for this. The
        # clipping has moved in the list; the picture on screen and the box
        # being dragged over it have not changed, and showing the row again
        # would stop the trim (see PreviewDialog.show_row).
        preview = self.preview
        if preview is None or not getattr(preview.canvas, "trimming", False):
            self._refresh_preview(row_id)
        self._update_counts()

    def _preview_navigate(self, step: int) -> None:
        if self.preview is None or self.preview.row is None:
            return
        # The clipping that was below this one when the preview arrived here,
        # whatever has moved since. Forwards only: a step back walks the list as
        # it now stands, and arriving anywhere fixes a new place.
        here, waiting = self._preview_at
        if step > 0 and waiting is not None and here == self.preview.row.id:
            at, _walk = self._preview_place(waiting)
            if at is not None:
                self._refresh_preview(waiting)
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

    def _context_menu(self, point: QPoint, pool=None) -> None:
        model = pool if pool is not None else self.model
        on_board = model is self.board_model
        view = self._list_for(model)
        index = view.indexAt(point)
        if not index.isValid():
            return
        entry = index.data(Qt.UserRole)
        if entry is None or entry.row is None:
            return
        clip_id = entry.row.id
        ticked = self._selected_ids(model)
        ids = ticked or [clip_id]
        hidden = 0
        if on_board and model.lens.busy:
            # Under a filter a category's menu acts on what is on screen: the
            # ticked rows showing, or the row clicked when none of those is
            # ticked - ticks made before the filter went on stay as they are,
            # as Select all leaves them. Worked out once, for every entry.
            # Only Move to category used to follow the screen, so Exclude,
            # Set newspaper, Merge and Delete in the same menu took ticks the
            # filter hid while Rotate took the row clicked: one menu, two
            # different clippings, and no label said which.
            shown = {row.id for row in model.visible_rows()}
            on_screen = [i for i in ticked if i in shown]
            hidden = len(ticked) - len(on_screen)
            ids = on_screen or [clip_id]
        many = len(ids) > 1
        clip = model.by_id(ids[0])
        # Whom a category's entries act on, in their words. "The ticked one"
        # when a single tick elsewhere is what they take rather than the row
        # under the mouse, which Open full size, Split and Rotate still act on.
        whom = ""
        if on_board:
            whom = (f" these {len(ids)}" if many
                    else " the ticked one" if ids[0] != clip_id else "")

        menu = QMenu(self)
        # Every entry belongs to the menu, not the window, so it goes when the
        # menu does: parented to the window, each right-click on a category's
        # list left seven of them behind for good.
        if hidden:
            # Said once, over the lot, since nothing in the menu touches them.
            note = QAction(
                f"{hidden} more ticked {'are' if hidden != 1 else 'is'} hidden by "
                f"the filter and left as {'they are' if hidden != 1 else 'it is'}",
                menu)
            note.setEnabled(False)
            menu.addAction(note)
            menu.addSeparator()
        menu.addAction(QAction("Open full size", menu,
                               triggered=lambda: self.open_preview(clip_id)))
        menu.addSeparator()
        if on_board:
            # A category's list has no press report to send to - its clippings
            # are the board's. What it has instead is the other three
            # categories, which dragging a card to another column reached, and
            # the other columns are not on screen to drag to.
            categories = menu.addMenu(f"Move{whom} to category")
            categories.setToolTipsVisible(True)
            self._fill_category_actions(categories, ids)
            menu.addSeparator()
            if len(model.file_runs()) > 1:
                move = menu.addMenu("Move to")
                move.setToolTipsVisible(True)
                self._fill_move_menu(move, ids, pool=model, categories=False)
        else:
            # The two interfaces keep separate clippings, so there has to be a
            # way to hand one over without importing it twice.
            send = (f"Send these {len(ids)} to the sentiment board" if many
                    else "Send to the sentiment board")
            menu.addAction(QAction(send, menu,
                                   triggered=lambda: self._send_to_board(ids)))
            menu.addSeparator()
            # Apart from the send above it, so a slip of the mouse cannot take
            # clippings out of the report when they were only meant to change
            # file.
            if len(self.model.file_runs()) > 1:
                move = menu.addMenu("Move to")
                move.setToolTipsVisible(True)
                self._fill_move_menu(move, ids)
        menu.addSeparator()
        # The same rule as the bar's button. This used to push "included" for
        # any group of clippings, so "Exclude these 3" put them back in.
        back = self._all_excluded(ids, model)
        if many:
            label = (f"Include these {len(ids)} again" if back
                     else f"Exclude these {len(ids)}")
        else:
            label = "Include again" if back else "Exclude"
        if whom == " the ticked one":
            label = "Include the ticked one again" if back else "Exclude the ticked one"
        menu.addAction(QAction(label, menu,
                               triggered=lambda: self._toggle_included(ids, pool=pool)))
        # In a category, for the clippings worked out above; the press
        # report's reads its ticks, as ever.
        menu.addAction(QAction(f"Set newspaper for{whom}…" if whom else "Set newspaper…",
                               menu, triggered=lambda: self._bulk_field(
                                   "newspaper", ids if on_board else None)))
        menu.addAction(QAction(f"Set edition for{whom}…" if whom else "Set edition…",
                               menu, triggered=lambda: self._bulk_field(
                                   "edition", ids if on_board else None)))
        menu.addSeparator()
        if many:
            merge = QAction(f"Merge these {len(ids)} into one", menu,
                            triggered=self._merge_selected)
            if on_board and model.lens.busy:
                # Refused, as the row's merge pill is: under a filter or an
                # arrangement the order on screen is not the order they would
                # be joined in, and ticks the filter hides would go in too.
                merge.setText(f"Merge these {len(ids)} into one "
                              "(clear the filter first)")
                merge.setEnabled(False)
            menu.addAction(merge)
        menu.addAction(QAction("Split in two", menu,
                               triggered=lambda: self._on_clip_action(
                                   "split", clip_id, pool=pool)))
        menu.addAction(QAction("Rotate 90°", menu,
                               triggered=lambda: self._on_clip_action(
                                   "rotate", clip_id, pool=pool)))
        menu.addSeparator()
        if on_board:
            # The same clippings as Exclude above it, never the ticks alone.
            target = ids[0]
            menu.addAction(QAction(
                f"Delete {len(ids)} clippings" if many
                else "Delete the ticked one" if target != clip_id
                else "Delete clipping", menu,
                triggered=(lambda: self._delete_many(ids, model)) if many
                else lambda: self._on_clip_action("delete", target, pool=pool)))
        else:
            menu.addAction(QAction(f"Delete {len(ids)} clippings" if many
                                   else "Delete clipping", menu,
                                   triggered=self._batch_delete if many
                                   else lambda: self._on_clip_action(
                                       "delete", clip_id, pool=pool)))
        if on_board:
            # A popup, not exec(): nothing waits on the menu.
            menu.setAttribute(Qt.WA_DeleteOnClose, True)
            menu.popup(view.viewport().mapToGlobal(point))
            return
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
        leaving_board = self.mode == "sentiment" and mode != "sentiment"
        if leaving_board and getattr(self, "board", None) is not None:
            # A headline half typed in a category's list is kept.
            self.board.focus_list.commit_editor()
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
            self._refresh_board()
        # The navy bar follows the list on show: the report's ticks in the
        # report, a category's in its list, and nothing over four columns.
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
        self._sync_board_scope()

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
        moving = [i for i in clip_ids if self.board_model.row_for(i) is not None
                  and self.board_model.by_id(i).section != section]
        if not moving:
            return
        style = theme.SENTIMENT_STYLES[section.value]
        # a clipping filed under a division stays with it; an unassigned one adopts
        # whichever division is being worked on
        unassigned = []
        if self.board.active and self.board.active != "__all__":
            unassigned = [i for i in moving if not self.board_model.by_id(i).division]
        # One Ctrl+Z for the move, whichever way it was made. As two steps, the
        # first Ctrl+Z took the division back and left the clipping in the
        # category it was sent to - out of the list it came from, with nothing
        # on screen to say it had not come back.
        stack = self.board_undo
        if unassigned:
            stack.beginMacro(f"Moved {len(moving)} into {style['label']}")
        try:
            stack.push(
                commands.SetFieldOnMany(self.board_model, moving, "section", section)
            )
            if unassigned:
                stack.push(
                    commands.SetFieldOnMany(
                        self.board_model, unassigned, "division", self.board.active
                    )
                )
        finally:
            if unassigned:
                stack.endMacro()
        # Gone from a category's list: a tick or a fold made there is not
        # theirs in the category they went to.
        ticked = [i for i in moving if i in self.board_model.selected]
        if ticked:
            self.board_model.set_selected(ticked, False)
        self.board_model.collapsed_row_ids -= set(moving)
        # A paper whose last clipping here has gone is no longer a choice.
        self._refresh_filter_choices()
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
        if getattr(self, "_scope_changing", False):
            return      # _sync_board_scope counts again once the scope is set
        if self._sync_board_scope():
            return      # it has just counted everything, under the new scope
        self._sync_fold_buttons()
        self._sync_english_button()
        self._say_filter_counts()
        total = self.model.clip_count
        included = self.model.included_count
        self.count_pill.setText(f"{total} clip" + ("s" if total != 1 else ""))
        self.cover.set_count(included)
        self.ready.setText(
            f"<b>{included}</b> clipping{'s' if included != 1 else ''} ready for export"
        )
        self.btn_pdf_out.setEnabled(included > 0)
        self.btn_docx_out.setEnabled(included > 0)
        self._say_last_action()
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
        # The bar acts on the list on show (see _list_pool): the report's
        # ticks in the report, a category's ticks in its list on the board.
        listed = self._list_pool()
        source = listed if listed is not None else self.model
        ticked = len(source.selected)
        self.batch_count.setText(str(ticked))
        self._sync_exclude_button()
        # Somewhere else to go only when there is more than one file - or,
        # for a board category, always: the other three categories.
        self.batch_move_to.setVisible(ticked > 0 and (
            source is self.board_model or len(source.file_runs()) > 1))
        self._sync_board_list_bar()
        count = len(self.model.selected)
        self.clear_selection_btn.setVisible(count > 0)
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
        # Shown only over the list its ticks belong to. On the board's four
        # columns it used to come back whenever anything recounted, with an
        # Exclude that changed clippings nobody could see.
        if ticked and listed is not None:
            self.batch.adjustSize()
            self.batch.show()
            self.batch.raise_()
            self._place_floating()
        else:
            self.batch.hide()
            board = getattr(self, "board", None)
            if board is not None:
                board.set_foot_room(0)

    def _sync_board_list_bar(self) -> None:
        """Select all and its hint over a board category's list, from the
        category's own ticks."""
        button = getattr(self, "board_select_all", None)
        if button is None:
            return
        pool = self.board_model
        ticked = len(pool.selected)
        shown = len(pool.visible_rows()) if pool.scope is not None else 0
        button.setText("Deselect all" if ticked and ticked == shown else "Select all")
        self.board_clear_selection.setVisible(ticked > 0)
        self.board_select_hint.setText(
            f"{ticked} selected — use the bar below, or drag any one of them "
            f"to move the block" if ticked else
            "Hold Ctrl to pick several, Shift for a run, or drag the handle to "
            "move a block anywhere")

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
        # ONE PER STRIP. There are two - the report's, and the board's bar -
        # and one shared timer was handed to whichever spoke last: a message
        # on the report's strip took the board's away from it, and the
        # board's last sentence then stood there for good.
        timers = getattr(self, "_status_timers", None)
        if timers is None:
            timers = self._status_timers = {}
        timer = timers.get(strip)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(strip.hide)
            timers[strip] = timer
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
        from ..export import summary as coverage

        board_clips = [row.clip for row in self.board_model.rows
                       if row.clip is not None]
        dialog = ExportDialog(
            clips, self, prefer=prefer,
            summary=coverage.Summary.of(clips, board_clips, self.config),
            report_date=self.cover.report_date(),
            cover_image=built or self.cover.cover_image(),
            heading="" if built else self.cover.heading(),
            cover_baked=bool(built),
            layout_style=self.heading.settings(),
            cover_blocks=self.cover.cover_blocks(),
            name_suffix=self._export_suffix(),
            with_cover=self.cover.wants_cover(),
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
    def _export_jpegs(self, clips: list, where: str, stamp, into=None,
                      reveal: bool = True):
        """One picture per clipping, with the masthead burned in.

        A folder rather than a file: these go out one at a time on WhatsApp, and
        each carries its own newspaper name and date in the file name so it can be
        found again after it has been forwarded twice.

        ``into`` is the folder already chosen - Build report's window names it
        - and no folder is asked for. The folder written, or None.
        """
        from ..export import build_jpeg
        from ..export import layout as export_layout

        # The same panel the dossier's PDF and Word use, so a clipping sent as a
        # picture is titled exactly like the same clipping printed in the report.
        style = export_layout.HeadingStyle.from_settings(
            self.board.heading.settings())

        if into is not None:
            folder = Path(into)
        else:
            chosen = QFileDialog.getExistingDirectory(
                self, "Where should the JPEGs go?", str(Path.home() / "Documents"),
            )
            if not chosen:
                return None
            folder = Path(chosen) / (build_jpeg.folder_name(self._division_tag(),
                                                            stamp)
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
            return None
        progress.setValue(len(clips))

        if not result.count:
            self._flash("No pictures could be written.", "bad")
            return None
        note = f"Wrote {result.count} JPEG{'s' if result.count != 1 else ''} to "
        note += folder.name + "."
        if result.warnings:
            note += f" {len(result.warnings)} could not be written."
        self._flash(note, "good" if not result.warnings else "info")
        if reveal:
            self._reveal(folder)
        return folder

    def _reveal(self, folder: Path) -> None:
        """Open the folder, so the pictures can be picked up straight away."""
        try:
            os.startfile(str(folder))  # noqa: S606 - Windows shell open
        except Exception:  # noqa: BLE001 - the files are written either way
            pass

    def _group_social(self, pool=None) -> None:
        """Gather the posts by platform, and head each run with its platform.

        One step in the history: the order and the headings go together (see
        commands.GroupSocial). Nothing is hidden, nothing is deleted, and a
        newspaper's story is not moved - only the posts, and only into the
        place the first post of their platform already held.
        """
        pool = pool if pool is not None else self.pool()
        rows = list(pool.rows)
        if not rows:
            self._flash("There is nothing to group.", "info")
            return
        order, marks = commands.social_grouping(rows)
        if not marks:
            self._flash("No posts to group - these are all newspaper stories.",
                        "info")
            return
        moved = sum(1 for place, row in enumerate(order) if rows[place] is not row)
        self.stack_for(pool).push(
            commands.GroupSocial(pool, order, marks,
                                 f"Grouped {len(marks)} posts by platform"))
        names = sorted({words for _key, words in marks.values()})
        self._flash(
            f"{len(marks)} post{'s' if len(marks) != 1 else ''} grouped under "
            + ", ".join(names[:4]) + ("…" if len(names) > 4 else "")
            + (f"; {moved} moved." if moved else "; already in order."), "good")

    def _fill_shift_menu(self, menu) -> None:
        """The newspads a selection can be copied into, filled as it opens so
        the counts are what is on disk now."""
        menu.clear()
        here = self.newspad
        for number in range(1, newspads.COUNT + 1):
            found = newspads.summary(number)
            words = newspads.describe(number, *(found or ()))
            if number == here:
                action = menu.addAction(f"{words}   (this one)")
                action.setEnabled(False)
                continue
            action = menu.addAction(words)
            action.triggered.connect(
                lambda _checked=False, n=number: self._shift_selection_to(n))

    def _shift_selection_to(self, number: int) -> None:
        """Every ticked clipping copied into another newspad, in one go.

        A copy, like the preview's own buttons: the clippings stay where they
        are, because the whole point is a cutting that belongs in two reports.
        Each keeps the list it is in, so board clippings arrive on that
        newspad's board and the report's on its list.
        """
        ids = self._selected_ids()
        if not ids:
            return
        pool = self.pool()
        which = "sentiment" if pool is getattr(self, "board_model", None) else "standard"
        # Saved first, so a picture the window has not written to disk yet is
        # not the one thing the copies are missing.
        try:
            self.save_session()
        except Exception:  # noqa: BLE001
            pass
        sent = 0
        trouble = ""
        for clip_id in ids:
            row = pool.row_for(clip_id)
            if row is None or row.clip is None:
                continue
            try:
                newspads.deliver(
                    number, row.clip, pool=which,
                    thumb_png=getattr(row, "thumb_png", b"") or b"",
                    source_name=f"Newspad {self.newspad}")
                sent += 1
            except newspads.HandoverError as bad:
                trouble = str(bad)
                break
            except Exception as bad:  # noqa: BLE001
                trouble = f"{type(bad).__name__}: {bad}"
                break
        if trouble and not sent:
            self._flash(trouble, "bad")
            return
        where = "board" if which == "sentiment" else "list"
        said = (f"{sent} clipping{'s' if sent != 1 else ''} copied into "
                f"Newspad {number}'s {where} — still here too.")
        if trouble:
            said += f" The rest stopped: {trouble}"
        self._flash(said, "good" if not trouble else "bad")
        self._show_move_note(said, above_bar=True)

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
        # The board holds sentiment.ALL_DIVISIONS while every division is on
        # show. This compared with "ALL", which it never holds, so the question
        # named the division "__all__".
        where = (code if code and code != sentiment.ALL_DIVISIONS
                 else "the board")
        words = f"Remove {len(ids)} clipping(s) from {where}?"
        focused = self._focused_section()
        if focused is not None:
            # With a category opened out, its list is the only one on show,
            # and a count several times the length of it reads as a mistake.
            # The button clears the division, so the question says the other
            # categories go too.
            listed = sum(1 for clip in showing
                         if sentiment.shows(clip, focused, code))
            words += (f"\n\nThat is every category in it, not only the "
                      f"{listed} in {focused.value} on show.")
        answer = QMessageBox.question(
            self, "Clear this division",
            words + "\n\nCtrl+Z brings them back.",
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

    def _dossier_ready(self):
        """(clippings, division, date) for a report off the board, or None
        when there is nothing to build or a date on it will not do."""
        clips = [c for c in self.board.visible_clips() if c.include]
        if not clips:
            self._flash("There is nothing on the board to export.", "bad")
            return None
        division = self.board.active_division()
        stamp = self.cover.report_date()
        # BOTH dates, as _export_dossier explains.
        if not datefield.refuse_future(self, stamp, "dossier"):
            return None
        if not self.board.cover.date_is_sound(self):
            return None
        return clips, division, stamp

    def _dossier_stem(self, stamp, burned: bool = False) -> str:
        """The department's usual name for a report off the board."""
        tail = " (burned headlines)" if burned else ""
        return (f"News Coverage - {self._division_tag()} - "
                f"{stamp.strftime('%d.%m.%Y')}{tail}{self._export_suffix()}")

    def _build_board_report(self) -> None:
        """The board's Build report: its window, then everything it chose.

        One window for all four - PDF, Word, burned headlines and pictures -
        with the file's name, its folder and the report's layout; the
        building is the board's own, the same that its Download buttons did.
        """
        from ..export import build_jpeg
        from .report_builder import BoardReportDialog

        ready = self._dossier_ready()
        if ready is None:
            return
        clips, division, stamp = ready
        ask = BoardReportDialog(
            self, clippings=len(clips), where=self._division_tag(),
            stamp=stamp, standard=self._dossier_stem(stamp),
            suffix=self._export_suffix(),
            choices=self.board.export_choices(),
            cover_on=bool(self.board.cover.cover_config().enabled))
        if ask.exec() != QDialog.Accepted:
            return
        # The layout goes back on the board, where the session keeps it.
        self.board.set_export_choices(ask.choices())
        self.touch_session()

        made: list = []
        for kind in ask.outputs():
            if kind == "jpeg":
                usual = (build_jpeg.folder_name(self._division_tag(), stamp)
                         + self._export_suffix())
                folder = self._export_jpegs(
                    clips, division.code if division else "ALL", stamp,
                    into=ask.pictures_folder(usual),
                    reveal=ask.shows_folder() and not made)
                if folder is not None and not made:
                    made.append(folder)
                continue
            made.extend(self._build_dossier(
                clips, division, stamp, ask.targets(kind),
                burned=kind == "burned"))
        files = [path for path in made if Path(path).is_file()]
        if files and ask.opens_after():
            from .burned_dialog import BurnedReportDialog

            BurnedReportDialog.open_file(files[0])
        if files and ask.shows_folder():
            from .export_dialog import ExportDialog

            ExportDialog._show_in_folder(Path(files[0]))

    def _export_dossier(self, kind: str) -> None:
        """Build the sentiment dossier for the division the board is showing.

        A dossier is one division, grouped by sentiment, and it takes its
        settings from the board's report layout rather than the cover card.
        The board's Build report comes in by _build_board_report; this one
        asks for one kind at a time, with a Save box.
        """
        ready = self._dossier_ready()
        if ready is None:
            return
        clips, division, stamp = ready

        # The strict rule, on the way out (_dossier_ready). The fields refuse
        # a future date as it is typed; that catches one that arrived any other
        # way - a session saved on another day, or a clock that was wrong and
        # has since been put right. BOTH dates, because they are two different
        # dates: the stamp dates the file; the dossier's own cover carries its
        # own, set on the board's cover card, and checking only the first one
        # left the second unchecked on every route out.
        where = division.code if division else "ALL"

        if kind == "jpeg":
            self._export_jpegs(clips, where, stamp)
            return

        # The burned report is the same document with the words drawn into the
        # pictures, so it is named apart from the ordinary one - they are two
        # different things to send and the file names have to say which is which.
        burned = kind == "burned"
        suffix = "docx" if kind == "docx" else "pdf"
        stem = self._dossier_stem(stamp, burned)

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

        made = self._build_dossier(clips, division, stamp, targets,
                                   burned=burned)
        if made and open_after:
            from .burned_dialog import BurnedReportDialog

            BurnedReportDialog.open_file(made[0])

    def _build_dossier(self, clips: list, division, stamp, targets: list,
                       burned: bool = False) -> list:
        """Write one report off the board in every format of ``targets``
        [(format, path)], from one burn when it is burned. The paths written."""
        from ..export import build_sentiment
        from ..export import layout as export_layout

        if not targets:
            return []
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
        # Which categories this dossier prints, and in what order - the Print
        # order window on the same card.
        chosen["print_plan"] = tuple(
            (column.value, on) for column, on in self.board.heading.print_plan())
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
        # Where each burned picture came from, and where its bands are. The
        # dossier only ever sees the copies, whose names have been cleared
        # because the names are inside the pictures now, so this is what the
        # record inside the file is written from (core/reportrecord). It is the
        # only way a burned report can be imported again with its names.
        origins: dict = {}
        if burned:
            from ..export import build_burned

            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                clips = build_burned.flatten(clips, board_style,
                                             warnings=burn_warnings,
                                             origins=origins)
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
                    result = builder(clips, path, division, stamp, options,
                                     origins=origins or None)
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
            return []

        names = ", ".join(Path(r.path).name for r in made)
        note = f"Built {names} ({made[0].clippings} clippings)."
        if notes:
            note += f" {len(notes)} note"
            note += "s." if len(notes) != 1 else "."
        self._flash(note, "good")
        return [Path(r.path) for r in made]

    # ------------------------------------------------------ the same twice
    def _is_board(self, pool) -> bool:
        """Whether a pool handed to the duplicate check is the board's."""
        return pool is not None and pool is getattr(self, "board_model", None)

    def _duplicate_clips(self, pool=None) -> list:
        """The clippings a duplicate check compares: the press report's, or
        the category of the board opened out as a list - its clippings in the
        division on show, and nothing else. None over four columns.

        The category rather than the whole board, because the review deletes:
        a pair with one side in a category not on screen would take away a
        clipping nobody could see, which the list's every other action was
        changed not to do.
        """
        if self._is_board(pool):
            if pool.scope is None:
                return []
            return [row.clip for row in pool.scoped_rows() if row.clip is not None]
        return [row.clip for row in self.model.rows if row.clip is not None]

    def _recheck_board_duplicates(self, force: bool = False) -> None:
        """Ask for the check over the category opened out on the board.

        Only while one is: over four columns of cards there is no list to
        badge and no review to offer, so nothing is read for them. On the same
        terms as the report's - Check automatically, or asked for - and run
        once, a moment later, on a timer of its own, so neither list's request
        restarts the other's wait.
        """
        if not self._auto_duplicates and not force:
            return
        if getattr(self.board_model, "scope", None) is None:
            return
        if self._board_duplicate_timer is None:
            self._board_duplicate_timer = QTimer(self)
            self._board_duplicate_timer.setSingleShot(True)
            self._board_duplicate_timer.timeout.connect(
                lambda: self._run_duplicate_check(pool=self.board_model))
        self._board_duplicate_timer.start(DUPLICATE_SETTLE_MS)

    def _forget_board_duplicates(self) -> None:
        """The board's pairs, suggestions, file marks and button, gone: they
        were worked out over a category that is no longer the one on show.
        The badges stay on the clippings, as the report's do across a restore,
        until the next check over that category looks again."""
        self._board_duplicate_pairs = []
        self._board_duplicate_hints = []
        pool = getattr(self, "board_model", None)
        if pool is not None:
            pool.duplicate_files = {}
        button = getattr(self, "board_duplicates_btn", None)
        if button is not None:
            button.setVisible(False)

    def _offer_board_marks(self) -> None:
        """The pairs the opened category's clippings are already marked as,
        offered again - the review button and the file marks - with nothing
        compared and nothing read.

        Forgetting the pairs on a category change left the badges, which stay
        on the clippings as the report's do. A copy's preview then said it was
        flagged, and "Compare in the review" said nothing was, until Check for
        Duplicates was pressed again. These are exactly the pairs the badge
        and the preview name, so the three agree. Suggestions are not remade
        here; the next check makes them.
        """
        pool = getattr(self, "board_model", None)
        if pool is None or pool.scope is None:
            return
        clips = self._duplicate_clips(pool)
        try:
            pairs = duplicates.marked_pairs(clips)
            self._mark_duplicate_files(clips, pool=pool)
        except Exception:  # noqa: BLE001 - never let this break the list
            pairs = []
        self._board_duplicate_pairs = pairs
        self._board_duplicate_hints = []
        button = getattr(self, "board_duplicates_btn", None)
        if button is not None:
            button.setVisible(bool(pairs))
            if pairs:
                button.setText(f"Preview and Delete Duplicates ({len(pairs)})")

    def _board_pairs_on_show(self) -> tuple:
        """(pairs, suggestions) of the open category whose two clippings are
        both in its list now.

        They were worked out when the check ran, and a history step since - a
        Sentiment set in the preview, a delete - can have taken one side out of
        the category. Offered anyway, the review opened on a clipping nobody
        could see, deleted nothing when told to, and said "Duplicates: deleted
        1." (D3 review). Kept whole and looked at each time rather than pruned,
        so a Ctrl+Z bringing the clipping back offers the pair again.
        """
        pool = getattr(self, "board_model", None)
        if (pool is None or pool.scope is None
                or not (self._board_duplicate_pairs or self._board_duplicate_hints)):
            return [], []
        held = {row.clip.uid for row in pool.scoped_rows() if row.clip is not None}

        def both(pair) -> bool:
            return (getattr(pair.primary, "uid", None) in held
                    and getattr(pair.copy, "uid", None) in held)

        return ([pair for pair in self._board_duplicate_pairs if both(pair)],
                [pair for pair in self._board_duplicate_hints if both(pair)])

    def _count_board_review(self) -> None:
        """The category's review button, counting what _board_pairs_on_show
        would offer. Asked after every step on the board's history, and does
        nothing while there are no pairs, which is almost always."""
        button = getattr(self, "board_duplicates_btn", None)
        if button is None:
            return
        if not (self._board_duplicate_pairs or self._board_duplicate_hints):
            return
        pairs, hints = self._board_pairs_on_show()
        found, hinted = len(pairs), len(hints)
        button.setVisible(found > 0 or hinted > 0)
        if found or hinted:
            button.setText(
                f"Preview and Delete Duplicates ({found})" if found
                else f"Look at {hinted} possible duplicate(s)")

    def _pass_over(self) -> None:
        """A check has finished: the pass is nobody's, and a list that asked
        while the other list's pass was running is asked for now."""
        self._duplicate_pool = None
        self._duplicate_scope = None
        waiting, self._duplicates_waiting = self._duplicates_waiting, set()
        if "report" in waiting:
            self.recheck_duplicates(force=True)
        if "board" in waiting:
            self.recheck_duplicates(force=True, pool=self.board_model)

    def recheck_duplicates(self, force: bool = False, pool=None) -> None:
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

        ``pool`` is the board's for a category opened out as a list, checked
        over that category alone (see _duplicate_clips); None is the press
        report, exactly as it always was.
        """
        if not hasattr(self, "duplicates_btn"):
            return
        if self._is_board(pool):
            self._recheck_board_duplicates(force)
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

    def _run_duplicate_check(self, pool=None) -> None:
        """Look over the whole list for cuttings that repeat one another.

        The slow half - reading a headline off each picture, about half a
        second each - happens on another thread. The window stays alive, and
        the answer arrives in the status strip when it is ready. Doing it here
        meant a minute of dead application immediately after an import, which
        is the moment somebody most wants to look at what they have just
        brought in.

        ``pool`` is the board's for a category opened out as a list.
        """
        board = self._is_board(pool)
        if self._switching:
            return          # the restore at the end of the switch asks again
        if self._still_winding_down():
            # A pass stopped by a switch has not let go of its thread yet. Two
            # at once raised the window's worst pause to 338ms, measured - so
            # wait for it, and try again in a moment.
            timer = self._board_duplicate_timer if board else self._duplicate_timer
            if timer is not None:
                timer.start(DUPLICATE_SETTLE_MS)
            return
        if self._duplicates_running:
            if self._is_board(self._duplicate_pool) != board:
                # The other list's pass is under way, and one pass serves
                # both. Dropped here, this list would never be looked at: its
                # turn comes when that pass ends (_pass_over).
                self._duplicates_waiting.add("board" if board else "report")
            return
        if board:
            if self.board_model.scope is None:
                return
            clips = self._duplicate_clips(self.board_model)
            # Only over the category it was pressed in; a category change
            # lets the request go before this (_let_board_request_go).
            fresh = (self._fresh_board is not None
                     and self._fresh_board == self.board_model.scope)
            self._fresh_board = None
            if not clips:
                self._forget_board_duplicates()
                return
            self._duplicate_scope = self.board_model.scope
        else:
            rows = [row for row in self.model.rows if row.clip is not None]
            clips = [row.clip for row in rows]
            fresh, self._fresh_report = self._fresh_report, False
            if not clips:
                self._duplicate_pairs = []
                self.duplicates_btn.setVisible(False)
                return
        if fresh:
            self._forget_readings(clips)
        self._duplicate_pool = self.board_model if board else self.model

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
            self._start_pass(unprinted,
                             functools.partial(self._prints_taken,
                                               pool=self.board_model)
                             if board else self._prints_taken,
                             read_headlines=False)
            return
        if board:
            self._read_the_shortlist(pool=self.board_model)
        else:
            self._read_the_shortlist()

    @staticmethod
    def _forget_readings(clips) -> None:
        """Forget everything worked out before about these clippings, for a
        check that looks again from scratch.

        Every measurement, not only the two the comparison happens to use
        today. Clearing just those two left the finer print, the ink profile
        and the content box sitting at their pre-crop values for the rest of
        the session, because _ensure_prints saw them filled in and skipped the
        clipping. Silently, and against check_duplicates_now's own promise
        that anything that still matters is read again.
        """
        duplicates.forget_measurements(clips)

    def _report_pass_on_board(self) -> bool:
        """The press report's own check, running while the board is on show.

        The other way round from _quiet_board_pass_off_screen, and the same
        trouble: _flash writes to the strip of the screen on show, so the
        report's "Reading clippings… 24 of 40" went up on the board's bar -
        where nobody had imported anything, and where it then stood long
        after the reading had finished. The report's strip hears it instead
        when the report is on show again."""
        pool = self._duplicate_pool
        return (pool is not None and not self._is_board(pool)
                and self.mode == "sentiment")

    def _quiet_board_pass_off_screen(self) -> bool:
        """A category's automatic check running while the press report is on
        show. _flash writes to the strip of the screen on show, so anything it
        said would read as the report's."""
        return (self._is_board(self._duplicate_pool) and not self._board_out_loud
                and self.mode != "sentiment")

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
        # Both pools: a pass over a category of the board read the board's
        # clippings. Every clipping's uid is its own, whichever pool holds it.
        pools = [self.model]
        board_pool = getattr(self, "board_model", None)
        if board_pool is not None:
            pools.append(board_pool)
        by_uid = {row.clip.uid: row.clip for each in pools for row in each.rows
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

    def _prints_taken(self, results, pool=None) -> None:
        """Copy back the fingerprints, then go on to the reading.

        Only the fingerprints. This pass never opened a headline reader, so what
        it hands back about the words is silence, not an answer - writing that
        onto a clipping would wipe a reading taken earlier in the morning.
        """
        if self._gone():
            return
        self._copy_back(results, headlines=False)
        self._duplicates_running = False
        if self._is_board(pool):
            self._read_the_shortlist(pool=pool)
        else:
            self._read_the_shortlist()

    def _read_the_shortlist(self, pool=None) -> None:
        """Read the headline off the few clippings that could be repeats."""
        if self._duplicates_running or self._gone():
            return
        board = self._is_board(pool)
        if board and pool.scope != self._duplicate_scope:
            # Another category was opened while the prints were taken: its
            # clippings are not the ones measured. The finish says so.
            self._finish_duplicate_check([], pool=pool)
            return
        clips = (self._duplicate_clips(pool) if board else
                 [row.clip for row in self.model.rows if row.clip is not None])
        try:
            wanted = duplicates.to_read(clips)
        except Exception:  # noqa: BLE001 - never let this break the list
            wanted = []
        unread = [(c.uid, c.image_bytes) for c in wanted]
        if not unread or not ocr.available():
            if board:
                self._finish_duplicate_check([], pool=pool)
            else:
                self._finish_duplicate_check([])
            return

        self._duplicates_running = True
        if not self._quiet_board_pass_off_screen():
            self._flash(f"Looking at {len(unread)} clipping(s) for duplicates…",
                        "info")
        # measure=False: every one of these was measured by the pass that
        # picked them out, moments ago. Measuring them again cost a 767ms pause
        # the instant the reading began, because four threads decoded four
        # pictures at once.
        self._start_pass(unread,
                         functools.partial(self._duplicate_readings, pool=pool)
                         if board else self._duplicate_readings,
                         measure=False)

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
        if self._quiet_board_pass_off_screen() or self._report_pass_on_board():
            return
        said = f"Reading clippings… {done} of {total}"
        if said == getattr(self, "_last_progress", ""):
            return
        self._last_progress = said
        self._flash(said, "info")

    def _duplicate_readings(self, results, pool=None) -> None:
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
        if self._is_board(pool):
            self._finish_duplicate_check(results, pool=pool)
        else:
            self._finish_duplicate_check(results)

    def _finish_duplicate_check(self, results, pool=None) -> None:
        """Compare everything and say what was found. Fast: no reading here."""
        # FIRST, before the guard below. A bar left up after the window has
        # started closing is a bar that never comes down.
        self._work_end()
        if self._gone():
            return
        try:
            if self._is_board(pool):
                self._finish_board_check(results)
            else:
                self._finish_report_check(results)
        finally:
            self._pass_over()

    def _finish_board_check(self, results) -> None:
        """The report's finish, for a category of the board opened out as a
        list: its own pairs, file marks and button, on its own pool."""
        pool = self.board_model
        if pool.scope is None or pool.scope != self._duplicate_scope:
            # Another category, or none, is on show now. What was read stays
            # on the clippings (_copy_back), so looking again costs little -
            # but pairs worked out over the category that was left must never
            # be offered over this one, where its review would delete them.
            left = self._duplicate_scope
            if self._board_out_loud and left is not None:
                # Pressed, so answered: silence read as a check still going.
                self._flash(f"{left.column.value}'s duplicate check was not "
                            f"finished: {self._scope_change_words(left, pool.scope)}.",
                            "info")
            self._board_out_loud = False
            if pool.scope is not None:
                self.recheck_duplicates(pool=pool)
            return
        clips = self._duplicate_clips(pool)
        try:
            pairs = duplicates.apply(clips)
            self._mark_duplicate_files(clips, pool=pool)
        except Exception:  # noqa: BLE001 - never let this break the list
            pairs = []
        try:
            hints = duplicates.suggestions(clips, pairs)
        except Exception:  # noqa: BLE001 - a suggestion is never worth a crash
            hints = []
        self._board_duplicate_pairs, self._board_duplicate_hints = pairs, hints
        found, hinted = len(pairs), len(hints)
        button = getattr(self, "board_duplicates_btn", None)
        if button is not None:
            button.setVisible(found > 0 or hinted > 0)
            if found or hinted:
                button.setText(
                    f"Preview and Delete Duplicates ({found})" if found
                    else f"Look at {hinted} possible duplicate(s)")
        pool.layoutChanged.emit()
        self._update_counts()
        self._preview_follow_duplicates(pool)
        where = pool.scope.column.value
        if self._board_out_loud:
            # Answered at this finish whatever it read. The report waits for
            # a pass that read something, because its button can find an
            # automatic pass already under way; the board's refuses to start
            # while any pass runs (check_duplicates_now), so the pass ending
            # now is the one the button started.
            self._board_out_loud = False
            if found:
                self._flash(
                    f"Checked {len(clips)} clippings in {where} — {found} "
                    f"{'look' if found != 1 else 'looks'} like a repeat. "
                    f"Badged, and still in the dossier until you look at them.",
                    "info")
            else:
                unread = sum(1 for c in clips if not duplicates.readable(c))
                note = f"Checked {len(clips)} clippings in {where} — no duplicates found."
                if unread:
                    note += f" {unread} could not be read well enough to compare."
                self._flash(note, "good")
        elif results and self.mode == "sentiment":
            # The quiet answer, said only while the board is the screen on
            # show. _flash writes to the strip of whatever screen that is, and
            # a bare "No duplicates found." on the press report's read as the
            # report's answer to a check it never had (D3 review). The button
            # on the category's bar stays for when the board is back.
            if found:
                self._flash(
                    f"{found} clipping(s) in {where} look like repeats — badged, "
                    f"and still in the dossier until you look at them.", "info")
            else:
                self._flash(f"No duplicates found in {where}.", "good")

    def _finish_report_check(self, results) -> None:
        """_finish_duplicate_check for the press report."""
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
        self._preview_follow_duplicates()
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
        elif results and not self._report_pass_on_board():
            # Only worth saying when something was actually read. A check that
            # found nothing new to look at should pass without comment - and
            # never on the board's bar: this is the press report's news.
            if found:
                self._flash(
                    f"{found} clipping(s) look like repeats — badged, and "
                    f"still in the report until you look at them.", "info")
            else:
                self._flash("No duplicates found.", "good")

    def _preview_follow_duplicates(self, pool=None) -> None:
        """A check that just finished may have badged or cleared the clipping
        on the preview: show it again so the column beside it is right. Never
        while a trim is being drawn - showing the row again would drop it.
        Only the preview of the list that was checked: ``pool`` is the board's
        after a check over a category opened out as a list."""
        preview = getattr(self, "preview", None)
        if preview is None or not preview.isVisible() or preview.row is None:
            return
        if preview.canvas.trimming or bool(preview.for_board) != self._is_board(pool):
            return
        if preview.for_board and self.board_model.scope is None:
            return          # a card's preview over four columns has no twin
        try:
            self._refresh_preview(preview.row.id)
        except Exception:  # noqa: BLE001 - a courtesy, never a crash
            pass

    def _read_one(self, clip) -> None:
        """Read one clipping's headline, keeping the window alive while it does."""
        from ..core import ocr

        try:
            ocr.read_into(clip)
            QApplication.processEvents()
        except Exception:  # noqa: BLE001 - a clipping that will not read
            pass

    def _source_of(self, clip) -> str:
        """Which file a clipping came in from, for the review screen - the
        press report's clippings first, then the board's."""
        board_pool = getattr(self, "board_model", None)
        for pool in (self.model, board_pool):
            if pool is None:
                continue
            for row in pool.rows:
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

    def _mark_duplicate_files(self, clips: list, pool=None) -> None:
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
        # A category of the board opened out as a list marks its own brackets,
        # from its own clippings: a file's bracket there holds only them.
        model = pool if self._is_board(pool) else self.model
        rows = model.scoped_rows() if self._is_board(pool) else self.model.rows
        for row in rows:
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
        model.duplicate_files = {
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
        # One setting and two boxes - the press report's bar and the bar over
        # a board category - so the one not clicked follows the one that was.
        for box in (getattr(self, "auto_dupes", None),
                    getattr(self, "board_auto_dupes", None)):
            if box is not None and box.isChecked() != self._auto_duplicates:
                was = box.blockSignals(True)
                box.setChecked(self._auto_duplicates)
                box.blockSignals(was)
        settings = export_dialog.load_settings()
        settings["auto_duplicates"] = self._auto_duplicates
        export_dialog.save_settings(settings)
        if on:
            self._flash("Imports will be checked for duplicates.", "info")
            self.recheck_duplicates()
            self.recheck_duplicates(pool=self.board_model)
        else:
            self._flash(
                "Automatic duplicate checking is off — use Check for "
                "Duplicates when you want it.", "info")

    def check_duplicates_now(self, pool=None) -> None:
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

        ``pool`` is the board's from the bar over a category opened out as a
        list: that category's clippings, looked at again from scratch.
        """
        from ..core import ocr

        board = self._is_board(pool)
        if board and pool.scope is None:
            return          # only a category opened out has this button
        # One pass serves both lists. Under way for THIS list, it is already
        # looking. Under way for the other list, this one takes its turn when
        # that pass ends: "Already looking" said then meant the list whose
        # button was pressed was never looked at, and never answered.
        others = (self._duplicates_running
                  and self._is_board(self._duplicate_pool) != board)
        if (self._duplicates_running and not others) or self._still_winding_down():
            self._flash("Already looking — one moment.", "info")
            return
        clips = (self._duplicate_clips(pool) if board else
                 [row.clip for row in self.model.rows if row.clip is not None])
        if not clips:
            self._flash("There are no clippings to check.", "info")
            return
        if not ocr.available():
            words = ("The headline reader is not available on this machine, so "
                     "clippings cannot be compared by what they say.\n\n"
                     + (ocr.why_not() or "It was not installed with the app."))
            if board:
                # open(), never exec(): nothing the board shows holds up the
                # window. The press report's box below waits, as it always has.
                box = QMessageBox(QMessageBox.Warning, "Cannot check for duplicates",
                                  words, QMessageBox.Ok, self)
                box.setAttribute(Qt.WA_DeleteOnClose, True)
                box.open()
                return
            QMessageBox.warning(self, "Cannot check for duplicates", words)
            return

        # From scratch: everything worked out before is forgotten
        # (_forget_readings) - when this list's own pass starts, not here.
        # Forgotten at the press, a request waiting for the other list's pass
        # and then let go by a category change left its clippings unread and
        # still paired, the hover saying nothing could be read (D3 review).
        if board:
            self._fresh_board = pool.scope
        else:
            self._fresh_report = True

        if others:
            # Kept in _duplicates_waiting, asked for by _pass_over when the
            # other list's pass ends, and answered out loud at its own finish.
            self._duplicates_waiting.add("board" if board else "report")
            if board:
                self._board_out_loud = True
                self._flash(f"Checking the press report first — "
                            f"{pool.scope.column.value} is next.", "info")
            else:
                running = getattr(self._duplicate_scope, "column", None)
                self._recheck_out_loud = True
                # Answered whatever its pass reads. The report's button waits
                # for a pass that read something because an automatic pass of
                # its own may already be under way; none can be while the
                # board's runs, so the pass that serves this is this one.
                self._answer_even_if_nothing_read = True
                self._flash(
                    f"Checking {running.value if running is not None else 'the board'}"
                    f" first — the press report is next.", "info")
            return
        if board:
            self._board_out_loud = True
            self._flash(f"Looking at all {len(clips)} clippings in "
                        f"{pool.scope.column.value} again…", "info")
            self._run_duplicate_check(pool=pool)
            return
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
                          else (collect.TIP_ON if on else collect.TIP_OFF)
                          + collector.options_tip())
        # An amber edge while Collect's options differ from the defaults. The
        # edge's colour only, so the header's floor stays where it is.
        tuned = bool(collector.changed_options())
        if bool(button.property("tuned")) != tuned:
            button.setProperty("tuned", tuned)
            button.style().unpolish(button)
            button.style().polish(button)

    def _collect_menu(self, point: QPoint) -> None:
        """Right-click on Collect from WhatsApp: its options for the session."""
        collector = getattr(self, "collector", None)
        button = getattr(self, "collect_btn", None)
        if collector is None or button is None or self._read_only:
            return
        collector.show_menu(button, button.mapToGlobal(point))

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
        # A board category's check is not carried across: it is asked again
        # when a category is opened out in the newspad that comes back.
        board_timer = self._board_duplicate_timer
        if board_timer is not None and board_timer.isActive():
            board_timer.stop()
        board_pass = self._is_board(self._duplicate_pool)
        if "report" in self._duplicates_waiting:
            pending = "quiet"
        self._duplicates_waiting = set()
        self._board_out_loud = False
        self._fresh_board = None
        if self._fresh_report:
            # The report's Check for Duplicates pressed, its pass not started.
            # It is carried across as "loud", which does not forget again, so
            # what the press would have forgotten is forgotten now, before
            # these clippings are saved - as it was when the press did it.
            self._fresh_report = False
            self._forget_readings(
                [row.clip for row in self.model.rows if row.clip is not None])
        if self._duplicates_running:
            if not board_pass:
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
        self._duplicate_pool = None
        self._duplicate_scope = None
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
        board_bar = getattr(self, "board_filter_bar", None)
        for each in (bar, board_bar):
            if each is None:
                continue
            was = each.blockSignals(True)
            try:
                each.clear()
            finally:
                each.blockSignals(was)
        if board_bar is not None:
            board_bar.hide()
            button = self.board_filter_btn
            was = button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(was)
        self._board_last_clicked_id = None
        for pool in (self.model, self.board_model):
            pool.reset_view()
            pool.replace_all([])
        self._duplicate_pairs = []
        self._duplicate_hints = []
        self.model.duplicate_files = {}
        self.duplicates_btn.setVisible(False)
        self._forget_board_duplicates()
        # After the stacks are cleared: clearing them stirs _after_undo_change,
        # which re-arms this very timer - and the board's history re-arms the
        # board's.
        if self._duplicate_timer is not None:
            self._duplicate_timer.stop()
        if self._board_duplicate_timer is not None:
            self._board_duplicate_timer.stop()
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

    def open_newspaper_list(self):
        """Manage Newspaper List, from Collect's right-click menu. Opened with
        open(), so nothing waits on it; Collect holds copies while it is up."""
        from .newspaper_list import NewspaperListDialog

        box = NewspaperListDialog(self)
        box.setAttribute(Qt.WA_DeleteOnClose, True)
        self._newspaper_list_box = box
        box.open()
        return box

    def newspaper_list_after_restore(self, restored_names=None) -> None:
        """A saved setup put the newspaper list back: read it again."""
        wanted = set(restored_names or [])
        if not wanted or paperlist.FILE in wanted:
            paperlist.apply(self.name_index)

    def open_settings(self) -> None:
        from .settings_dialog import SettingsDialog

        SettingsDialog(self).exec()

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

    def review_duplicates(self, pool=None) -> None:
        """Show each suspected repeat beside the one it repeats.

        ``pool`` is the board's from a category opened out as a list: its own
        pairs, deleted on the board's history. That review opens with open(),
        never exec() - nothing the board shows may hold up the window - and is
        acted on when it closes. The press report's waits, as it always has.
        """
        from .duplicates_dialog import DuplicatesDialog

        board = self._is_board(pool)
        if board:
            # Only pairs with both clippings in the category's list now.
            pairs, hints = self._board_pairs_on_show()
        else:
            pairs = list(getattr(self, "_duplicate_pairs", []))
            # The suggestions come along for the ride, at the end, where they
            # read as "and these might be worth a look" rather than as more of
            # the same.
            hints = list(getattr(self, "_duplicate_hints", []))
        if not pairs and not hints:
            if board:
                self._count_board_review()
            self._flash("Nothing is flagged as a duplicate.", "info")
            return
        pairs = pairs + hints

        screen = DuplicatesDialog(pairs, self._source_of, self)
        if board:
            screen.setAttribute(Qt.WA_DeleteOnClose, True)
            screen.finished.connect(
                lambda result: self._duplicates_reviewed(screen, pairs, pool)
                if result == QDialog.Accepted else None)
            screen.open()
            return
        if screen.exec() != QDialog.Accepted:
            return
        self._duplicates_reviewed(screen, pairs, self.model)

    def _duplicates_reviewed(self, screen, pairs, pool) -> None:
        """What the review decided, acted on - for the list it was opened
        over. The verdicts, "not a duplicate", and one undoable delete."""
        board = self._is_board(pool)
        # Every judgement is written down before anything is acted on. It is
        # the only labelled data that describes THIS department's papers, and
        # it is what makes the check better at finding the repeats it misses -
        # see core/verdicts.
        from ..core import verdicts

        # On the board, only the category the review was opened over: every
        # pair came from it, and nothing out of sight is ever deleted.
        rows = (pool.scoped_rows() if board and pool.scope is not None
                else pool.rows if board else self.model.rows)
        by_uid = {row.clip.uid: row.clip for row in rows
                  if row.clip is not None}
        kept = {clip.uid for clip in screen.to_keep()}
        removed = {clip.uid for clip in screen.to_delete()}
        how = verdicts.BULK if getattr(screen, "swept", lambda: False)() \
            else verdicts.ONE_BY_ONE

        def on_show(clip) -> bool:
            # On the board, a clipping that has left the category since the
            # review opened is neither judged, spared nor deleted: nothing out
            # of sight is acted on. The press report's list holds them all.
            return not board or getattr(clip, "uid", None) in by_uid

        # The dialog's own pairs, not the list handed in: a pair the person
        # turned round is judged the way round they judged it.
        for pair in getattr(screen, "pairs", pairs):
            if not (on_show(pair.primary) and on_show(pair.copy)):
                continue
            copy_uid = getattr(pair.copy, "uid", None)
            if copy_uid in kept:
                verdicts.record(pair.primary, pair.copy, False, how)
            elif copy_uid in removed:
                verdicts.record(pair.primary, pair.copy, True, how)

        # "Not a duplicate" is remembered on the clipping, so the next check
        # does not simply flag it again the moment anything else changes. For
        # a pair the person turned round, on both of them - see to_spare.
        for clip in getattr(screen, "to_spare", screen.to_keep)():
            if not on_show(clip):
                continue
            clip.not_duplicate = True
            clip.duplicate_of = None
            clip.include = True

        # Deleted through the same command every other deletion in the app
        # uses, so Ctrl+Z brings them back. The confirmation says so: telling
        # somebody a thing cannot be undone when it can is its own kind of bug.
        doomed = {clip.uid for clip in screen.to_delete()}
        if doomed:
            ids = [row.id for row in rows
                   if row.clip is not None and row.clip.uid in doomed]
            if ids:
                (self.board_undo if board else self.undo_stack).push(
                    commands.RemoveClips(
                        pool if board else self.model, ids,
                        f"{len(ids)} duplicate(s) deleted" if len(ids) > 1
                        else "Duplicate deleted"))

        if board:
            self.recheck_duplicates(pool=pool)
        else:
            self.recheck_duplicates()
        said = []
        if board:
            # What was done, not what was asked: a copy that had left the
            # category was said to be deleted when nothing was (D3 review).
            deleted = len(ids) if doomed else 0
            kept_now = sum(1 for clip in screen.to_keep() if on_show(clip))
        else:
            deleted, kept_now = len(doomed), len(screen.to_keep())
        if deleted:
            said.append(f"deleted {deleted}")
        if kept_now:
            said.append(f"kept {kept_now}")
        self._flash("Duplicates: " + (", ".join(said) if said
                                      else "nothing changed") + ".", "good")

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt name
        super().changeEvent(event)
        # Only activation is looked at, and only while a link from Collect is
        # waiting, so every other change passes straight through. Shown once
        # the activation is over: shown inside it, on the real window platform
        # the links window took the activation from this window.
        if (event.type() == QEvent.ActivationChange
                and getattr(self, "_links_waiting", False) and self.isActiveWindow()):
            self._links_waiting = False
            QTimer.singleShot(0, self._show_waiting_links)

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
            wanted = ((self.batch.height() + 26)
                      if self.batch.isVisible() and self.mode == "standard" else 0)
            left, top, right, bottom = shape.getContentsMargins()
            if bottom != wanted:
                shape.setContentsMargins(left, top, right, wanted)
        # The same room on the board's page, while the bar floats over a
        # category's list.
        board = getattr(self, "board", None)
        if board is not None and hasattr(board, "set_foot_room"):
            board.set_foot_room(
                (self.batch.height() + 26)
                if self.batch.isVisible() and self._list_pool() is self.board_model
                else 0)

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
            # HUGS ITS OWN WORDS. It used to be pinned at up to 680 wide
            # whatever it said, so a short sentence sat in the middle of a
            # wide navy slab. The label wraps at 430, so the bubble is that
            # plus its padding - or less, when the sentence is shorter.
            # HUGS ITS OWN WORDS. It used to be pinned at up to 680 wide
            # whatever it said, so a short sentence sat in the middle of a wide
            # navy slab. A wrapped label's sizeHint is its MINIMUM, not its
            # natural width, so the sentence is measured as one line and capped.
            words = self.move_note_text.text()
            natural = self.move_note_text.fontMetrics().boundingRect(words).width()
            note.setFixedWidth(max(240, min(456, self.width() - 16,
                                            natural + 30)))
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
