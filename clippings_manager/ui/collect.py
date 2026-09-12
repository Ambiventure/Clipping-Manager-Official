"""Collect from WhatsApp: clippings taken as they are copied.

The morning's loose clippings arrive in WhatsApp Web as photos with a caption
under each - "Amar ujala jalandhar", "NBT Lucknow". Adding them used to mean,
for every one: copy or drag the photo, come back to this window, type the
newspaper. With Collect switched on, somebody stays in Chrome:

    right-click the photo > Copy image     -> a new clipping appears here
    select its caption > Ctrl+C            -> that clipping is named

Four actions a clipping, and no window switching.

HOW COPIES ARE PAIRED - and the one rule that matters: nothing is guessed. A
caption goes on the photo that was added most recently, and only if that photo
has no name yet. Anything else - a caption with no photo waiting, a second
caption for a photo that already has one, text that is not clearly a caption -
is refused out loud, with one button that puts it where it was probably meant.
So one missed photo copy cannot quietly shift every caption after it along by
one, which is the mistake that would print a wrong newspaper on a morning's
worth of clippings. Every photo and every naming is one undo step.

It never takes focus from Chrome, never opens a box, and when something needs
attention while the window is behind Chrome, the taskbar button flashes.

What a copy IS lives in ui/clipwatch.py (the clipboard) and core/copied.py
(what text means). This decides what to do with each.
"""

from __future__ import annotations

from datetime import datetime

import hashlib
import re
import traceback
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout)

from ..core import copied
from ..core.models import Section
from . import commands, theme
from .clipwatch import ClipboardWatcher

# ------------------------------------------------------------------ words
LABEL_OFF = "Collect from WhatsApp"
LABEL_ON = "● Collecting"
TIP_OFF = (
    "Add clippings without leaving WhatsApp Web.\n\n"
    "Switch this on, then in WhatsApp Web right-click a photo and choose Copy "
    "image: it becomes a new clipping here. Then select the photo's caption and "
    "press Ctrl+C: its newspaper, city and page are filled in.\n\n"
    "While this is on, the program looks at what you copy, on this computer "
    "only. Any picture you copy becomes a clipping. Copies marked private "
    "(passwords, Incognito or Guest windows) are left alone. It switches itself "
    "off when you change newspad or close the program.")
TIP_ON = "Collecting what you copy. Click to stop."
TIP_READ_ONLY = "This newspad cannot save, so nothing can be collected into it."

START = ("In WhatsApp Web: right-click a photo and choose Copy image, then select "
         "its caption and press Ctrl+C.")
ADDED = "Photo added as {which}. Now copy its caption."
ADDED_BOARD = "Photo added to {column}. Now copy its caption."
ADDED_HIDDEN = "Photo added as {which} — it is hidden by the filter that is on."
SMALL = (" It is only {w} × {h} pixels — if it looks blurred, open the photo in "
         "WhatsApp and copy it again.")
BY_HAND = "{which} was added by hand. Copy its caption in WhatsApp and it goes on it."
TOGETHER = ("{k} photos arrived together, so a copied caption will not go on any "
            "of them by itself.")
NAMED = "“{display}” put on {which}."
NAMED_LINK = "“{display}” and its link put on {which}."
LINK_ADDED = "Link put under {which} ({site})."
NOTE_EDITION = " {edition} is not on the newspaper list — check the spelling."
NOTE_PAPER = (" “{paper}” was spelt out from the Hindi and is not on the newspaper "
              "list — check it, or add the paper to the list to have it read "
              "every time.")
NOTE_BARE_PAGE = " The page came from the number at the end."
NOTE_LINK_SKIPPED = " The link was not used — {which} already has one."
SAME_AGAIN = "Already used — that was the same caption again."
ALREADY = "That photo is already in the list as {which}, so it was not added again."
ALREADY_NEXT = " The next caption you copy will go on it."
PRIVATE = ("That copy was marked private (a password, or a Chrome Incognito or "
           "Guest window), so it was left alone.")
FILES = ("Files copied in Explorer are not collected. Drag them in, or use the "
         "Add buttons.")
TOOK_BACK = "Took back: {what}."

NOT_USED = "Not used — {reason}."
AGAIN = " Select the whole caption and copy it again."
#: Refusals where copying the caption again is not the answer - it was a link,
#: or nothing at all - so the advice would only confuse.
NOT_A_CAPTION_AT_ALL = (copied.WHY_WHATSAPP_LINK, copied.WHY_TWO_ADDRESSES,
                        copied.WHY_NOT_A_STORY, copied.WHY_EMPTY,
                        copied.WHY_HAS_PICTURE_ADDRESS)
NO_PHOTO = ("No photo is waiting for that caption. Copy the photo first, then its "
            "caption.")
HAS_CAPTION = ("{which} already has a caption (“{display}”). To change it, press "
               "the button, or copy the photo again and use the button.")
TYPED = ("{which}'s newspaper was typed by hand, so the copied caption was not "
         "put on it.")
LINK_NOT_USED = ("That link was not put on {which}, because it already has a "
                 "newspaper or a link.")
PICTURE_ADDRESS = ("That copied the picture's address, not the picture. "
                   "Right-click the photo and choose Copy image.")
NOT_A_PICTURE = "That picture could not be read. Copy it again."
TOO_SMALL = ("That picture is very small ({w} × {h}) — probably the blurred "
             "preview. Click the photo in WhatsApp to open it, then copy it again.")
COULD_NOT_READ = "Could not read that copy. Please copy it again."
NOT_APPLIED = "That copy could not be used."

USE_ON = "Put it on {which}"
USE_INSTEAD = "Put it on {which} instead"
USE_LINK = "Put the link on {which}"
UNDO = "Undo that"

FLASH_ON = ("Collecting. In WhatsApp Web, right-click a photo and choose Copy "
            "image, then select its caption and press Ctrl+C. There is no need "
            "to come back here.")
FLASH_OFF = "Stopped collecting — {p} photo{ps} added, {c} named from their captions."
FLASH_SWITCH = ("Newspad {n} is open. Collecting was switched off for the change "
                "— click Collect from WhatsApp to carry on.")
FLASH_DROPPED = " {k} copies made just before were not added — copy them again."
PASTE_NOT_NEEDED = ("Collect has already taken what you copied, so Ctrl+V is not "
                    "needed. Switch Collect off to paste by hand.")
DROP_SUFFIX = "or copy its caption in WhatsApp."


TIDIED = (" The phone's bars were trimmed off it \u2014 Trim\u2026 then Whole "
          "picture puts them back.")
NEITHER = ("That copy held neither a picture nor any text, so there was "
           "nothing to add.")
HISTORY = "What was copied\u2026"
HISTORY_FOOT = ("Only what kind of copy each was and what became of it - never "
                "the words, which may be anything the clipboard carried.")


#: A copied caption the reader could not take apart is still a caption when
#: it is short and made of words. Up to this many words it is printed as
#: typed without asking; up to the second, the bar offers it on a button;
#: beyond that it is a pasted paragraph, not a caption.
AS_TYPED_WORDS = 16
AS_TYPED_BUTTON_WORDS = 60
#: What is printed as typed is amber on the card: nobody has checked it.
AS_TYPED_CONFIDENCE = 0.5

AS_TYPED = ("\u201c{shown}\u201d printed as typed on {which} \u2014 it did not read as a "
            "newspaper and a city ({reason}), so it prints as written. Check "
            "it, or type over it.")
PRINT_AS_TYPED = "Print it as typed on {which}"


def as_typed(text: str) -> tuple[str, str]:
    """(how, the words) for a copy the reader refused: "auto" to print it as
    typed at once, "button" to offer it, "" to leave it refused.

    The words are the copy with WhatsApp's furniture taken off, one bubble
    only. Not a single token - a copied password is one token and must never
    be printed on a card - and not an address, not chat, not mostly numbers.
    """
    words = copied.as_typed_words(text)
    if not words:
        return "", ""
    tokens = words.split()
    if len(tokens) <= AS_TYPED_WORDS:
        return "auto", words
    if len(tokens) <= AS_TYPED_BUTTON_WORDS:
        return "button", words
    return "", ""


def _picture_shape(item) -> str:
    return f"picture, {len(item.data) // 1024} KB"


def _shape(text: str) -> str:
    """"3 words, Hindi": what a copy looked like, with none of it repeated."""
    words = (text or "").split()
    scripts = set()
    for word in words:
        for ch in word:
            if "\u0900" <= ch <= "\u097f":
                scripts.add("Hindi")
            elif "\u0a00" <= ch <= "\u0a7f":
                scripts.add("Punjabi")
            elif ch.isascii() and ch.isalpha():
                scripts.add("English")
    lines = len([line for line in (text or "").splitlines() if line.strip()])
    said = f"{len(words)} word{'s' if len(words) != 1 else ''}"
    if lines > 1:
        said += f" on {lines} lines"
    if scripts:
        said += ", " + ("mixed" if len(scripts) > 1 else next(iter(scripts)))
    return said


def _elide(text: str, most: int = 40) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= most else text[:most - 1].rstrip() + "…"


def _site(url: str) -> str:
    match = re.match(r"^(?:[a-z][a-z0-9+.-]*://)?(?:[^@/\s]+@)?([^/:?#\s]+)",
                     url or "", re.I)
    host = (match.group(1) if match else "").lower()
    return host[4:] if host.startswith("www.") else host


def caption_open(clip) -> bool:
    """Whether a copied caption may name this clipping without being asked."""
    return clip.name_source not in ("manual", "copied") and not clip.newspaper.strip()


def link_open(clip) -> bool:
    return not clip.url.strip()


@dataclass
class Target:
    """A clipping a copy may go on - as long as it is still THAT clipping."""

    pool: object
    row: object
    gen: int


@dataclass
class Pending:
    """A copy that was refused, kept for the one button that can place it."""

    reading: object
    target: Optional[Target]
    why: str
    link_only: bool = False
    button: Optional[str] = None     # its words, with {which} still to fill
    # For a copy that could not be read but can be printed as written: the
    # words, and the copy they came from.
    typed: str = ""
    raw: str = ""


@dataclass
class Queued:
    item: object
    gen: int


class Collector(QObject):
    """Takes copies while switched on, pairs them, and says what it did."""

    changed = Signal()

    DRAIN_MS = 250
    QUEUE_MAX = 50
    HISTORY_MAX = 40
    #: Long side, in pixels. A copy of WhatsApp's blurred chat preview is tiny;
    #: a photo opened full-screen and copied is not.
    REFUSE_LONG_SIDE = 200
    WARN_LONG_SIDE = 600
    ALERT_MS = 3000

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.watcher = ClipboardWatcher(self)
        self.watcher.copied.connect(self._on_copied)
        self.watcher.note.connect(self._on_note)
        self._drain_timer = QTimer(self)
        self._drain_timer.setSingleShot(True)
        self._drain_timer.setInterval(self.DRAIN_MS)
        self._drain_timer.timeout.connect(self._drain)
        self._queue: list = []
        self.target: Optional[Target] = None
        self.pending: Optional[Pending] = None
        self._record = None              # (stack, index) of Collect's last push
        self._photos = 0
        self._captions = 0
        self._message = ""
        self._problem = False
        self._thumb_row = None
        self._adding = False
        self.alert_hook = None           # a test stands in for the taskbar here
        self.bar = None
        # What each copy was and what became of it, newest last - never the
        # words themselves. For the morning when "it missed the caption" has
        # to be answered from something other than memory.
        self.history: list = []
        self._history_box = None
        for stack in (window.undo_stack, window.board_undo):
            stack.indexChanged.connect(
                lambda _index, moved=stack: self._stack_moved(moved))

    # ---------------------------------------------------------------- state
    @property
    def is_on(self) -> bool:
        return self.watcher.is_on()

    def start(self) -> bool:
        w = self.window
        if w._read_only:
            w._refuse_if_read_only()
            return False
        if (getattr(w, "_stuck", False) or w._switching or w._restoring
                or getattr(w, "_closing", False)):
            return False
        self.watcher.set_on(True)
        self._queue = []
        self.target = None
        self.pending = None
        self._record = None
        self._photos = self._captions = 0
        self._thumb_row = None
        self._say(START)
        self._show_bar(True)
        self._window_changed()
        w._flash(FLASH_ON, "info")
        return True

    def stop(self, why: str = "") -> int:
        """Switch off. Returns how many copies were waiting and are dropped."""
        was_on = self.is_on
        self.watcher.set_on(False)
        self._drain_timer.stop()
        dropped = len(self._queue)
        self._queue = []
        self.target = None
        self.pending = None
        self._record = None
        self._show_bar(False)
        self._window_changed()
        if was_on and why == "":
            p = self._photos
            self.window._flash(FLASH_OFF.format(p=p, ps="s" if p != 1 else "",
                                                c=self._captions), "info")
        return dropped

    def refresh(self) -> None:
        self._render()

    def column(self) -> Section:
        """The board column a collected photo goes in: the one opened out, or
        Neutral - as a paste does."""
        focused = getattr(self.window.board, "focused", None)
        try:
            return Section(focused) if focused else Section.NEUTRAL
        except ValueError:
            return Section.NEUTRAL

    def note_arrival(self, pool, rows: list) -> None:
        """Every clipping added by hand passes through here, whatever the route.

        Never raises: a drop from Chrome swallows whatever its handler raises.
        """
        try:
            if len(rows) == 1:
                target = Target(pool, rows[0], self.window._newspad_gen)
                self.target = target
                if self.pending is not None:
                    self.pending.target = target
                if self.is_on and not self._adding:
                    self._thumb_row = rows[0]
                    self._say(BY_HAND.format(which=self._which(pool, rows[0])))
            elif rows:
                self.target = None
                if self.pending is not None:
                    self.pending.target = None
                if self.is_on:
                    self._say(TOGETHER.format(k=len(rows)))
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------- copies
    def _on_copied(self, item) -> None:
        if not self.is_on:
            return
        if len(self._queue) >= self.QUEUE_MAX:
            self._queue.pop(0)
            self._say(COULD_NOT_READ, problem=True)
        self._queue.append(Queued(item, self.window._newspad_gen))
        self._drain()

    def _on_note(self, code: str) -> None:
        if code in ("private", "private-history"):
            self._say(PRIVATE)
            self._remember_copy("a private copy", "left alone")
        elif code == "files":
            self._say(FILES)
            self._remember_copy("files", "not collected")
        elif code == "too-long":
            self._say(NOT_USED.format(reason="it is too long to be a caption") + AGAIN,
                      problem=True)
            self._alert()
            self._remember_copy("text", "not used: too long to be a caption")
        elif code == "unreadable":
            self.target = None
            self._say(COULD_NOT_READ, problem=True)
            self._alert()
            self._remember_copy("a picture that never arrived", "could not be read")
        elif code == "nothing":
            self._say(NEITHER)
            self._remember_copy("neither a picture nor text", "nothing to do")

    def _remember_copy(self, what: str, became: str) -> None:
        """One line of history: when, what kind of copy, what became of it."""
        stamp = datetime.now().strftime("%H:%M:%S")
        self.history.append(f"{stamp}  {what} \u2192 {became}")
        del self.history[:-self.HISTORY_MAX]
        box = self._history_box
        if box is not None:
            try:
                if box.isVisible():
                    box.words.setPlainText("\n".join(self.history))
            except RuntimeError:
                self._history_box = None

    def show_history(self) -> None:
        """The last copies and what became of each, in a small window."""
        from .english import show_summary

        lines = list(self.history) or ["Nothing has been copied since Collect was switched on."]
        self._history_box = show_summary(
            self.window, lines,
            "What was copied while Collect was on, and what became of it",
            title="What was copied", foot=HISTORY_FOOT)

    def _idle(self) -> bool:
        """Whether a copy may be applied now. While an import or an export is
        running, a switch is under way, or a box is up, copies wait - in order."""
        w = self.window
        if (w._pumping or w._switching or w._restoring
                or getattr(w, "_closing", False) or w._read_only):
            return False
        return (QApplication.activeModalWidget() is None
                and QApplication.activePopupWidget() is None)

    def _drain(self) -> None:
        self._drain_timer.stop()
        while self._queue:
            if not self._idle():
                self._drain_timer.start()
                self._render()
                return
            queued = self._queue.pop(0)
            if queued.gen != self.window._newspad_gen:
                continue                 # made before a newspad switch
            try:
                if queued.item.kind == "picture":
                    self._take_picture(queued.item)
                else:
                    self._take_text(queued.item)
            except Exception:  # noqa: BLE001 - one copy, never the program
                traceback.print_exc()
                self._say(NOT_APPLIED, problem=True)
        self._render()

    def _valid(self, target: Optional[Target]):
        """(live pool, row) if the target is still that clipping, else None."""
        if target is None or target.gen != self.window._newspad_gen:
            return None
        pool = self.window.pool_for(target.row.id)
        if pool is None or pool.row_for(target.row.id) is not target.row:
            return None
        return pool, target.row

    def _which(self, pool, row) -> str:
        if pool is self.window.board_model:
            return f"the card in {row.clip.section.value}"
        return f"No. {pool.position_of(row.id) + 1}"

    def _take_picture(self, item) -> None:
        w = self.window
        digest = hashlib.sha1(item.data).hexdigest()
        pool = w.pool()
        for row in pool.rows:
            if row.clip is not None and row.clip.image_hash == digest:
                target = Target(pool, row, w._newspad_gen)
                self.target = target
                if self.pending is not None:
                    self.pending.target = target
                message = ALREADY.format(which=self._which(pool, row))
                if caption_open(row.clip):
                    message += ALREADY_NEXT
                self._thumb_row = row
                self._say(message)
                self._remember_copy(_picture_shape(item), f"already {self._which(pool, row)}")
                return
        try:
            clip = w._clip_from_bytes(item.data, item.name)
        except Exception:  # noqa: BLE001 - not a picture after all
            self.target = None
            self._say(NOT_A_PICTURE, problem=True)
            self._alert()
            self._remember_copy(_picture_shape(item), "not a picture after all")
            return
        width, height = clip.native_width, clip.native_height
        if max(width, height) < self.REFUSE_LONG_SIDE:
            self.target = None
            self._say(TOO_SMALL.format(w=width, h=height), problem=True)
            self._alert()
            self._remember_copy(f"picture {width}x{height} px", "too small to be a clipping")
            return
        clip.image_hash = digest
        if pool is w.board_model:
            clip.section = self.column()
        # Never use up a column that a board button armed for its own import.
        saved = getattr(w, "_pending_section", None)
        w._pending_section = None
        self._adding = True
        try:
            rows = w._add_loose([clip], quiet=True) or []
        finally:
            w._pending_section = saved
            self._adding = False
        if not rows:
            return
        row = rows[0]
        self._photos += 1
        self._remember(w.stack_for(pool))
        self._thumb_row = row
        if pool is w.board_model:
            message = ADDED_BOARD.format(column=row.clip.section.value)
        elif pool.entry_row_for_clip(row.id) < 0:
            message = ADDED_HIDDEN.format(which=self._which(pool, row))
        else:
            message = ADDED.format(which=self._which(pool, row))
        if max(width, height) < self.WARN_LONG_SIDE:
            message += SMALL.format(w=width, h=height)
        if not row.clip.crop.is_identity:
            message += TIDIED
        self._say(message)
        self._remember_copy(f"picture {width}x{height} px",
                            f"added as {self._which(pool, row)}"
                            if pool is not w.board_model else
                            f"added to {row.clip.section.value}")

    def _take_text(self, item) -> None:
        w = self.window
        reading = copied.read(item.text, w.name_index)
        if reading.kind == "picture-address":
            # The previous photo is no longer waiting: the next caption must
            # not land on it just because this copy missed.
            self.target = None
            self._say(PICTURE_ADDRESS, problem=True)
            self._alert()
            self._remember_copy("a picture's address", "not used")
            return
        if reading.kind == "nothing":
            reason = reading.reason or "it did not look like a caption"
            # A caption the reader could not take apart is still the caption
            # the office copied. With a photo waiting for one, short and made
            # of words, it is printed as typed - the report needs the words
            # above the picture more than it needs them in separate fields -
            # and flagged amber, because nobody has checked them.
            how, words = ("", "") if reason in NOT_A_CAPTION_AT_ALL else as_typed(item.text)
            found = self._valid(self.target) if how else None
            if found is not None and not caption_open(found[1].clip):
                found = None
            if found is not None and found[1].clip.label.strip():
                found = None
            if found is not None and how == "auto":
                pool, row = found
                which = self._which(pool, row)
                self._fill_as_typed(pool, row, words, item.text)
                self._say(AS_TYPED.format(shown=_elide(words), which=which, reason=reason))
                self._remember_copy(f"text, {_shape(item.text)}",
                                    f"printed as typed on {which} ({reason})")
                return
            if found is not None and how == "button":
                self.pending = Pending(reading, self.target,
                                       NOT_USED.format(reason=f"{reason} ({_shape(item.text)})"),
                                       False, PRINT_AS_TYPED, typed=words, raw=item.text)
                self._say(self.pending.why, problem=True)
                self._alert()
                self._remember_copy(f"text, {_shape(item.text)}",
                                    f"not used: {reason} (kept for the button)")
                return
            # The shape of what arrived - how many words, which script - and
            # never the words: that is enough to tell what went wrong without
            # ever showing a copied password back on screen.
            self._say(NOT_USED.format(reason=f"{reason} ({_shape(item.text)})")
                      + ("" if reason in NOT_A_CAPTION_AT_ALL else AGAIN), problem=True)
            self._alert()
            self._remember_copy(f"text, {_shape(item.text)}", f"not used: {reason}")
            return
        has_caption = reading.kind in ("caption", "caption+link")
        has_link = reading.kind in ("link", "caption+link")
        found = self._valid(self.target)
        if found is None:
            self._refuse(reading, None, NO_PHOTO, link_only=not has_caption)
            return
        pool, row = found
        clip = row.clip
        which = self._which(pool, row)
        if (has_caption and clip.name_source == "copied"
                and clip.caption_raw == reading.text
                and (not has_link or clip.url.strip() == reading.url)):
            self._say(SAME_AGAIN)
            return
        if not has_caption and clip.url.strip() and clip.url.strip() == reading.url:
            self._say(SAME_AGAIN)
            return

        values: dict = {}
        notes = ""
        if has_caption:
            if clip.name_source == "manual":
                self._refuse(reading, self.target, TYPED.format(which=which),
                             USE_INSTEAD)
                return
            if not caption_open(clip):
                self._refuse(reading, self.target,
                             HAS_CAPTION.format(which=which,
                                                display=_elide(clip.display_caption)),
                             USE_INSTEAD)
                return
            values.update(copied.caption_values(reading))
            if has_link and link_open(clip):
                values.update({"url": reading.url, "show_url_box": True})
            elif has_link:
                notes += NOTE_LINK_SKIPPED.format(which=which)
        else:
            if not (link_open(clip) and not clip.newspaper.strip()):
                self._refuse(reading, self.target, LINK_NOT_USED.format(which=which),
                             USE_LINK, link_only=True)
                return
            values.update({"url": reading.url, "show_url_box": True})

        self._fill(pool, row, values, self._step_name(has_caption, "url" in values))
        self.pending = None
        self._thumb_row = row
        self._say(self._named(reading, which, has_caption, "url" in values) + notes)
        self._remember_copy(f"text, {_shape(item.text)}",
                            f"{self._step_name(has_caption, 'url' in values).lower()} "
                            f"onto {which}")

    def _step_name(self, caption: bool, link: bool) -> str:
        if caption and link:
            return "Caption and link copied"
        return "Caption copied" if caption else "Link copied"

    def _named(self, reading, which: str, caption: bool, link: bool) -> str:
        if not caption:
            return LINK_ADDED.format(which=which, site=_site(reading.url))
        self._captions += 1
        message = (NAMED_LINK if link else NAMED).format(
            display=_elide(reading.display), which=which)
        if not getattr(reading, "paper_known", True):
            message += NOTE_PAPER.format(paper=reading.newspaper)
        if reading.edition and not reading.edition_known:
            message += NOTE_EDITION.format(edition=reading.edition)
        if reading.page_from_bare_number:
            message += NOTE_BARE_PAGE
        return message

    def _fill_as_typed(self, pool, row, words: str, raw: str) -> None:
        """The copied words printed above the picture as they are."""
        self._captions += 1
        self._thumb_row = row
        self.pending = None
        self._fill(pool, row, {
            "label": words, "no_title": False,
            "caption_raw": (raw or "").strip()[:300],
            "name_source": "copied", "name_confidence": AS_TYPED_CONFIDENCE,
        }, "Caption copied as typed", command=commands.CaptionAsTyped)

    def _fill(self, pool, row, values: dict, text: str,
              command=None) -> None:
        """One copy onto one clipping, as one undo step.

        An open headline box on that clipping is put away first - committed if
        somebody typed in it, cancelled if not. Left open and untouched, its
        empty text would later be taken for "no headline" and hide the name.
        """
        w = self.window
        if pool is w.board_model:
            w.board.settle_editors(row.id)
        else:
            w.list.settle_editor(row.id)
        if pool.row_for(row.id) is not row:
            return
        stack = w.stack_for(pool)
        stack.push((command or commands.FillFromCopy)(pool, row.id, values, text))
        self._remember(stack)
        if pool is w.board_model:
            w._refresh_board()
        preview = getattr(w, "preview", None)
        if (preview is not None and preview.isVisible()
                and getattr(preview, "row", None) is row):
            w._refresh_preview(row.id)
        w._refresh_filter_choices()

    def _refuse(self, reading, target, why: str, button: Optional[str] = None,
                link_only: bool = False) -> None:
        """Say why a copy was not used, and keep it for the one button."""
        self.pending = Pending(reading, target, why, link_only, button)
        self._say(why, problem=True)
        self._alert()
        self._remember_copy("text", "not used: " + why.split(". ")[0].rstrip(".")
                            + " (kept for the button)")

    def use_pending(self) -> None:
        """The button: put the refused copy where the person says it goes."""
        pending = self.pending
        if pending is None:
            return
        found = self._valid(pending.target)
        if found is None:
            self.pending = None
            self._render()
            return
        pool, row = found
        reading = pending.reading
        if pending.typed:
            # The button for a copy printed as typed.
            self.pending = None
            if caption_open(row.clip) and not row.clip.label.strip():
                which = self._which(pool, row)
                self._fill_as_typed(pool, row, pending.typed, pending.raw)
                self._say(AS_TYPED.format(shown=_elide(pending.typed), which=which,
                                          reason=reading.reason or "it did not read"))
                self._remember_copy("text", f"printed as typed on {which}, on the button")
            self._render()
            return
        caption = reading.kind in ("caption", "caption+link") and not pending.link_only
        values: dict = {}
        if caption:
            values.update(copied.caption_values(reading))
        if reading.url and (pending.link_only or not row.clip.url.strip()):
            values.update({"url": reading.url, "show_url_box": True})
        if not values:
            self.pending = None
            self._render()
            return
        self._fill(pool, row, values, self._step_name(caption, "url" in values))
        self.pending = None
        self._thumb_row = row
        self._say(self._named(reading, self._which(pool, row), caption,
                              "url" in values))

    def undo_that(self) -> None:
        record = self._record
        if record is None:
            return
        stack, index = record
        self._record = None
        if stack.index() != index:
            self._render()
            return
        what = stack.undoText()
        stack.undo()
        self._say(TOOK_BACK.format(what=what))

    def _remember(self, stack) -> None:
        self._record = (stack, stack.index())
        self._render()

    def _stack_moved(self, moved) -> None:
        record = self._record
        if record is None:
            return
        if record[0] is not moved or moved.index() != record[1]:
            self._record = None
            self._render()

    # ------------------------------------------------------------ telling
    def _say(self, message: str, problem: bool = False) -> None:
        self._message = message
        self._problem = problem
        self._render()

    def _alert(self) -> None:
        if self.alert_hook is not None:
            self.alert_hook()
            return
        try:
            if not self.window.isActiveWindow():
                QApplication.alert(self.window, self.ALERT_MS)
        except RuntimeError:
            pass

    def _window_changed(self) -> None:
        w = self.window
        sync = getattr(w, "_sync_collect_button", None)
        if callable(sync):
            sync()
        try:
            w.setWindowTitle(w._title())
        except RuntimeError:
            pass

    def build_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("CollectBar")
        bar.setAttribute(Qt.WA_StyledBackground, True)
        bar.setProperty("problem", False)
        bar.setStyleSheet(
            f"#CollectBar {{ background: {theme.NAVY_WASH};"
            f" border: 1px solid {theme.NAVY_BAND_LINE}; border-radius: 10px; }}"
            f"#CollectBar QLabel {{ color: {theme.NAVY}; background: transparent; }}"
            f"#CollectBar[problem=\"true\"] {{ background: {theme.FLAG_WASH};"
            f" border: 1px solid {theme.ORANGE_INK}; }}"
            f"#CollectBar[problem=\"true\"] QLabel {{ color: {theme.INK}; }}")
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 8, 10, 8)
        row.setSpacing(10)
        self.thumb = QLabel()
        self.thumb.setFixedSize(40, 40)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.hide()
        row.addWidget(self.thumb)
        words = QVBoxLayout()
        words.setSpacing(2)
        self.headline = QLabel()
        self.headline.setStyleSheet("font-weight: 700;")
        self.headline.setWordWrap(True)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setMinimumWidth(160)
        words.addWidget(self.headline)
        words.addWidget(self.message)
        row.addLayout(words, 1)
        self.action = QPushButton()
        self.action.setCursor(Qt.PointingHandCursor)
        self.action.clicked.connect(self.use_pending)
        self.action.hide()
        row.addWidget(self.action)
        self.undo = QPushButton(UNDO)
        self.undo.setCursor(Qt.PointingHandCursor)
        self.undo.clicked.connect(self.undo_that)
        self.undo.setEnabled(False)
        row.addWidget(self.undo)
        self.history_btn = QPushButton(HISTORY)
        self.history_btn.setCursor(Qt.PointingHandCursor)
        self.history_btn.setToolTip(
            "Every copy since Collect was switched on - what kind it was and "
            "what became of it. Never the words themselves.")
        self.history_btn.clicked.connect(self.show_history)
        row.addWidget(self.history_btn)
        bar.hide()
        self.bar = bar
        return bar

    def _show_bar(self, on: bool) -> None:
        if self.bar is not None:
            self.bar.setVisible(on)
            if on:
                self._render()

    def _render(self) -> None:
        bar = self.bar
        if bar is None:
            return
        try:
            w = self.window
            p, c = self._photos, self._captions
            counts = (f"{p} photo{'s' if p != 1 else ''}, "
                      f"{c} caption{'s' if c != 1 else ''}.")
            if w.mode == "sentiment":
                head = (f"Collecting into the sentiment board, {self.column().value} "
                        f"column — {counts}")
            else:
                head = f"Collecting into the press report — {counts}"
            if self._queue:
                head += f" {len(self._queue)} waiting to be added."
            self.headline.setText(head)
            self.message.setText(self._message)
            if bool(bar.property("problem")) != self._problem:
                bar.setProperty("problem", self._problem)
                bar.style().unpolish(bar)
                bar.style().polish(bar)
            row = self._thumb_row
            pixmap = getattr(row, "thumbnail", None) if row is not None else None
            if pixmap is not None and not pixmap.isNull():
                self.thumb.setPixmap(pixmap.scaledToHeight(40, Qt.SmoothTransformation))
                self.thumb.show()
            else:
                self.thumb.hide()
            pending = self.pending
            found = self._valid(pending.target) if pending is not None else None
            if found is not None:
                label = pending.button or (USE_LINK if pending.link_only else USE_ON)
                self.action.setText(label.format(which=self._which(*found)))
                self.action.show()
            else:
                self.action.hide()
            live = self._record is not None
            self.undo.setEnabled(live)
            self.undo.setToolTip(("Take back: " + self._record[0].undoText())
                                 if live else "")
            self.changed.emit()
        except RuntimeError:
            pass
