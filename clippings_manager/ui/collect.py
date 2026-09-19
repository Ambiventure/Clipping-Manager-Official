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

Right-click the button for Collect's options (ui/collect_options.py). Every
default is the rule above. A person may relax it for the session - a new
caption replacing a copied one, a caption copied just before its photo going
on it (within two minutes), the caption going on the one ticked clipping - and
may name every photo from the session's newspaper and city. A photo named that
way still takes the next caption copied for it. A story link no photo is
waiting for - none yet, or the newest already has a newspaper or a link - goes
to the links list rather than being lost.

It never takes focus from Chrome, never opens a box, and when something needs
attention while the window is behind Chrome, the taskbar button flashes.

What a copy IS lives in ui/clipwatch.py (the clipboard) and core/copied.py
(what text means). This decides what to do with each.
"""

from __future__ import annotations

from datetime import datetime

import hashlib
import re
import time
import traceback
from dataclasses import dataclass, replace
from typing import Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout)

from ..core import copied
from ..core.models import Section
from . import collect_options, commands, theme
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
TIP_MENU = "\n\nRight-click for the newspaper list and Collect's options."

START = ("In WhatsApp Web: right-click a photo and choose Copy image, then select "
         "its caption and press Ctrl+C.")
ADDED = "Photo added as {which}. Now copy its caption."
ADDED_BOARD = "Photo added to {column}. Now copy its caption."
ADDED_HIDDEN = "Photo added as {which} — it is hidden by the filter that is on."
ADDED_NAMED = ("Photo added as {which}, named {display} from this session's "
               "settings — a copied caption still replaces it.")
ADDED_BOARD_NAMED = ("Photo added to {column}, named {display} from this session's "
                     "settings — a copied caption still replaces it.")
#: With captions sent to the ticked clipping, "now copy its caption" would
#: send the person's next caption somewhere it does not go.
ADDED_TICKED = "Photo added as {which}."
ADDED_TICKED_NAMED = ("Photo added as {which}, named {display} from this session's "
                      "settings.")
NOTE_TICKED = (" Captions go on the one clipping ticked in the list, as Collect's "
               "options say.")
NOTE_HIDDEN = " It is hidden by the filter that is on."
NOTE_COLUMN_HIDDEN = (" The board is showing only {focused}, so it is not in view "
                      "— Collect's options send photos to {column}.")
SMALL = (" It is only {w} × {h} pixels — if it looks blurred, open the photo in "
         "WhatsApp and copy it again.")
BY_HAND = "{which} was added by hand. Copy its caption in WhatsApp and it goes on it."
TOGETHER = ("{k} photos arrived together, so a copied caption will not go on any "
            "of them by itself.")
NAMED = "“{display}” put on {which}."
NAMED_LINK = "“{display}” and its link put on {which}."
REPLACED = "“{display}” replaced “{old}” on {which}."
LINK_ADDED = "Link put under {which} ({site})."
NOTE_EDITION = " {edition} is not on the newspaper list — check the spelling."
NOTE_PAPER = (" “{paper}” was spelt out from the Hindi and is not on the newspaper "
              "list — check it, or add the paper to the list to have it read "
              "every time.")
NOTE_PAPER_TYPED = (" “{paper}” is not on the newspaper list, so it was kept as "
                    "typed — check it, or add the paper to the list to have it "
                    "read every time.")
NOTE_BARE_PAGE = " The page came from the number at the end."
NOTE_LINK_SKIPPED = " The link was not used — {which} already has one."
NOTE_LINK_OFF = " The link was not used — links are off."
NOTE_NO_PAPER = " No newspaper was named — type it, or set one for this session."
NOTE_DIVISION = " Filed under {name} division ({code})."
NOTE_DIVISION_KEPT = (" {code} is {name} division — the clipping stays under "
                      "{kept}, the division it already had.")
NOTE_DIVISION_KEPT_BOARD = (" {code} is {name} division — the card stays under "
                            "{kept}, the division the board is showing.")
NOTE_DIVISION_KEPT_CARD = (" {code} is {name} division — the card stays under "
                           "{kept}, the division it already had.")
SAME_AGAIN = "Already used — that was the same caption again."
ALREADY = "That photo is already in the list as {which}, so it was not added again."
ALREADY_NEXT = " The next caption you copy will go on it."
PRIVATE = ("That copy was marked private (a password, or a Chrome Incognito or "
           "Guest window), so it was left alone.")
FILES = ("Files copied in Explorer are not collected. Drag them in, or use the "
         "Add buttons.")
TOOK_BACK = "Took back: {what}."
PHOTOS_OFF = "Not collected — photos are switched off in Collect's options."
CAPTIONS_OFF = "Not used — captions are switched off in Collect's options."
LINKS_OFF = "Not used — links are switched off in Collect's options."
LINK_TO_LIST = ("No photo was waiting, so the link went to the links list "
                "({many} link{s} there).")
LINK_TO_LIST_TAKEN = ("{which} already has a newspaper or a link, so the link went "
                      "to the links list ({many} link{s} there).")
LINK_LISTED = "That link is already in the links list."
#: The links window is not put in front of Chrome: it waits for the person.
LIST_WHEN_BACK = " The links window opens when you come back to this program."
#: After "Put the link on No. N" for a link that also went to the links list.
NOTE_LINK_TAKEN_OUT = " It was taken out of the links list, so Capture does not make it twice."
NOTE_LINK_STILL_LISTED = (" It is still in the links list — untick it there, or Capture "
                          "makes a second clipping of it.")
#: Ctrl+V of a link Collect has already dealt with.
PASTE_LINK_ON = "That link is already on {which}, so it was not listed again."
PASTE_LINK_LISTED = "That link is already in the links list, so it was not listed twice."
#: The session's division, not put on a card that would then be hidden.
NOTE_SESSION_DIVISION = (" It stays under {kept}, the division the board is showing — "
                         "this session's {code} goes only on photos collected into the "
                         "press report, or while the board shows All divisions.")
#: One line in What was copied... for a Reset, however many options it undid.
OPTIONS_RESET = "all options back to their defaults"
EARLY_USED = ("Photo added as {which}, and the caption copied just before it went "
              "on it: “{display}”.")
EARLY_USED_BOARD = ("Photo added to {column}, and the caption copied just before "
                    "it went on it: “{display}”.")
PICK_ONE = ("Tick one clipping for the caption to go on — Collect's options send "
            "captions to the ticked clipping.")

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
OPTIONS_ON = " Your changed options are on — see the bar."
FLASH_OFF = "Stopped collecting — {p} photo{ps} added, {c} named from their captions."
FLASH_SWITCH = ("Newspad {n} is open. Collecting was switched off for the change "
                "— click Collect from WhatsApp to carry on.")
FLASH_DROPPED = " {k} copies made just before were not added — copy them again."
PASTE_NOT_NEEDED = ("Collect has already taken what you copied, so Ctrl+V is not "
                    "needed. Switch Collect off to paste by hand.")
DROP_SUFFIX = "or copy its caption in WhatsApp."


TIDIED = (" The phone's bars were trimmed off it — Trim… then Whole "
          "picture puts them back.")
NEITHER = ("That copy held neither a picture nor any text, so there was "
           "nothing to add.")
HISTORY = "What was copied…"
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

AS_TYPED = ("“{shown}” printed as typed on {which} — it did not read as a "
            "newspaper and a city ({reason}), so it prints as written. Check "
            "it, or type over it.")
PRINT_AS_TYPED = "Print it as typed on {which}"


def as_typed(text: str, auto_words: int = AS_TYPED_WORDS,
             button_words: int = AS_TYPED_BUTTON_WORDS) -> tuple[str, str]:
    """(how, the words) for a copy the reader refused: "auto" to print it as
    typed at once, "button" to offer it, "" to leave it refused.

    The words are the copy with WhatsApp's furniture taken off, one bubble
    only. Not a single token - a copied password is one token and must never
    be printed on a card - and not an address, not chat, not mostly numbers.
    The two limits are Collect's options; a 0 means that way is never used.
    """
    words = copied.as_typed_words(text)
    if not words:
        return "", ""
    tokens = words.split()
    if len(tokens) <= auto_words:
        return "auto", words
    if len(tokens) <= button_words:
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
            if "ऀ" <= ch <= "ॿ":
                scripts.add("Hindi")
            elif "਀" <= ch <= "੿":
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


def _indic(text: str) -> bool:
    return any("ऀ" <= ch <= "੿" for ch in (text or ""))


def _elide(text: str, most: int = 40) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= most else text[:most - 1].rstrip() + "…"


def _capital(text: str) -> str:
    """A message that starts with the clipping's name starts a sentence: on the
    board that name is "the card in Negative"."""
    return text[:1].upper() + text[1:]


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
    # A caption refused because no photo was waiting yet, and when: with the
    # option on, the photo copied next takes it by itself, if soon enough.
    early: bool = False
    made: float = 0.0
    # A link that went to the links list and is kept for the button too: put
    # on a photo with it, it comes back out of the list.
    listed: bool = False


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
    #: Changes of options are kept apart from copies, so a morning of changes
    #: and a Reset never push the copies out of What was copied...
    OPTIONS_HISTORY_MAX = 12
    #: Long side, in pixels. A copy of WhatsApp's blurred chat preview is tiny;
    #: a photo opened full-screen and copied is not. The refusal is one of
    #: Collect's options; this is its default.
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
        # Collect's options for this session: in memory only, never saved,
        # kept through Collect off and on and through a newspad switch.
        self.options = collect_options.DEFAULTS
        # Photos Collect named from the session's settings, by clipping id:
        # (the row, what was stamped). Only these take a caption on top.
        self._preset: dict = {}
        self._menu = None
        self._defaults_box = None
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
        self._preset.clear()
        self._say(START)
        self._show_bar(True)
        self._window_changed()
        w._flash(FLASH_ON + (OPTIONS_ON if self.changed_options() else ""), "info")
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
        """The board column a collected photo goes in: the one Collect's
        options name, else the one opened out, else Neutral - as a paste does."""
        chosen = self.options.board_column
        if chosen:
            try:
                return Section(chosen)
            except ValueError:
                pass
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
                    self._say(_capital(BY_HAND.format(which=self._which(pool, rows[0]))))
            elif rows:
                self.target = None
                if self.pending is not None:
                    self.pending.target = None
                if self.is_on:
                    self._say(TOGETHER.format(k=len(rows)))
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ options
    def set_options(self, new) -> None:
        """Collect's options from now on - the next copy taken uses them,
        including copies that arrived while the menu was open."""
        if not isinstance(new, collect_options.CollectOptions) or new == self.options:
            return
        old = self.options
        self.options = new
        # One line for one change, however many options it moved. A line per
        # option let a Reset push every copy out of the history, which is
        # there to answer "it missed the caption".
        self._remember_copy("options", OPTIONS_RESET if new == collect_options.DEFAULTS
                            else "; ".join(collect_options.change_lines(old, new)))
        self._render()
        self._window_changed()

    def reset_options(self) -> None:
        self.set_options(collect_options.DEFAULTS)

    def changed_options(self) -> list:
        return collect_options.changes(self.options)

    def options_tip(self) -> str:
        """The button's tooltip ending: how to reach the options, and which
        are changed."""
        said = self.changed_options()
        tip = TIP_MENU
        if said:
            tip += " Changed for this session: " + "; ".join(said) + "."
        return tip

    def show_menu(self, anchor, global_pos=None):
        """The options menu, as a popup: nothing waits on it."""
        old = self._menu
        if old is not None:
            try:
                old.close()
            except RuntimeError:
                pass
        menu = collect_options.build_menu(self, anchor)
        menu.setAttribute(Qt.WA_DeleteOnClose, True)
        self._menu = menu
        menu.popup(global_pos if global_pos is not None else QCursor.pos())
        return menu

    def show_defaults(self, parent=None):
        """The small window for the session's newspaper, city, page and
        division. Opened with open(), so nothing waits on it either."""
        box = collect_options.SessionDefaultsDialog(self, self.window)
        box.setAttribute(Qt.WA_DeleteOnClose, True)
        self._defaults_box = box
        box.open()
        return box

    def _options_link(self, _href: str = "") -> None:
        self.show_menu(self.options_line, QCursor.pos())

    def _stamped(self, row) -> Optional[dict]:
        kept = self._preset.get(getattr(row, "id", None))
        return kept[1] if kept is not None and kept[0] is row else None

    def _is_preset(self, row) -> bool:
        """Whether this clipping's name is still only the session's settings."""
        stamped = self._stamped(row)
        clip = row.clip
        return (stamped is not None and clip.name_source == "copied"
                and not clip.caption_raw.strip()
                and clip.newspaper == stamped["newspaper"]
                and clip.edition == stamped["edition"])

    def _caption_open(self, row) -> bool:
        """caption_open, where a photo named from the session's settings
        still counts as waiting for its caption."""
        return caption_open(row.clip) or self._is_preset(row)

    def _copied_label(self, clip) -> bool:
        """Whether the headline box holds words a copy put there, rather than
        a headline somebody typed."""
        label, raw = clip.label.strip(), clip.caption_raw.strip()
        return bool(label and raw) and (label == raw or label == copied.as_typed_words(raw))

    def _pair(self):
        """(pool, row, target) that a copied caption or link goes on, or None.

        The newest photo, as always - or, when the options say so and the
        press report is showing, the one clipping ticked there."""
        w = self.window
        if self.options.pair_with == "ticked" and w.pool() is w.model:
            ids = [r.id for r in w.model.rows if r.id in w.model.selected]
            if len(ids) != 1:
                return None
            row = w.model.row_for(ids[0])
            if row is None or row.clip is None:
                return None
            return w.model, row, Target(w.model, row, w._newspad_gen)
        found = self._valid(self.target)
        return (found[0], found[1], self.target) if found is not None else None

    def _ticking(self) -> bool:
        w = self.window
        return self.options.pair_with == "ticked" and w.pool() is w.model

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
            if not self.options.captions:
                self._say(CAPTIONS_OFF)
                self._remember_copy("text", "not used (captions are off)")
                return
            self._say(NOT_USED.format(reason="it is too long to be a caption") + AGAIN,
                      problem=True)
            self._alert()
            self._remember_copy("text", "not used: too long to be a caption")
        elif code == "unreadable":
            self._no_photo_waiting()
            self._say(COULD_NOT_READ, problem=True)
            self._alert()
            self._remember_copy("a picture that never arrived", "could not be read")
        elif code == "nothing":
            self._say(NEITHER)
            self._remember_copy("neither a picture nor text", "nothing to do")

    def _remember_copy(self, what: str, became: str) -> None:
        """One line of history: when, what kind of copy, what became of it."""
        stamp = datetime.now().strftime("%H:%M:%S")
        self.history.append(f"{stamp}  {what} → {became}")
        self._trim_history()
        box = self._history_box
        if box is not None:
            try:
                if box.isVisible():
                    box.words.setPlainText("\n".join(self.history))
            except RuntimeError:
                self._history_box = None

    def _trim_history(self) -> None:
        """The newest HISTORY_MAX copies and OPTIONS_HISTORY_MAX changes of
        options, still in the order they happened. Counted apart, so changing
        options never takes a copy's line away."""
        for options, most in ((False, self.HISTORY_MAX), (True, self.OPTIONS_HISTORY_MAX)):
            kind = [at for at, line in enumerate(self.history)
                    if ("  options → " in line) == options]
            for at in reversed(kind[:max(0, len(kind) - most)]):
                del self.history[at]

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
                    if self.options.photos:
                        self._take_picture(queued.item)
                    else:
                        # Said, never flashed: the person switched photos off.
                        # But a picture copied and not taken leaves no photo
                        # waiting, as every refused picture does: the caption
                        # copied next is that picture's, and landing on the
                        # photo before would shift every caption after it.
                        self._no_photo_waiting()
                        if self.pending is not None:
                            self.pending.target = None
                        self._say(PHOTOS_OFF)
                        self._remember_copy(_picture_shape(queued.item),
                                            "not collected (photos are off)")
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
        opts = self.options
        digest = hashlib.sha1(item.data).hexdigest()
        pool = w.pool()
        if opts.same_photo != "again":
            for row in pool.rows:
                if row.clip is not None and row.clip.image_hash == digest:
                    target = Target(pool, row, w._newspad_gen)
                    self.target = target
                    if self.pending is not None:
                        self.pending.target = target
                    message = ALREADY.format(which=self._which(pool, row))
                    if self._caption_open(row) and not self._ticking():
                        message += ALREADY_NEXT
                    self._thumb_row = row
                    self._say(message)
                    self._remember_copy(_picture_shape(item),
                                        f"already {self._which(pool, row)}")
                    return
        try:
            clip = w._clip_from_bytes(item.data, item.name)
        except Exception:  # noqa: BLE001 - not a picture after all
            self._no_photo_waiting()
            self._say(NOT_A_PICTURE, problem=True)
            self._alert()
            self._remember_copy(_picture_shape(item), "not a picture after all")
            return
        width, height = clip.native_width, clip.native_height
        refuse = opts.refuse_under
        if refuse and max(width, height) < refuse:
            self._no_photo_waiting()
            self._say(TOO_SMALL.format(w=width, h=height), problem=True)
            self._alert()
            self._remember_copy(f"picture {width}x{height} px", "too small to be a clipping")
            return
        clip.image_hash = digest
        on_board = pool is w.board_model
        if on_board:
            clip.section = self.column()
        board = getattr(w, "board", None)
        showing_all = getattr(board, "active", "") in ("", collect_options.ALL_DIVISIONS)
        # Named from the session's settings before it is added, so the photo
        # and its name are one undo step. A division only where it cannot hide
        # the card from the board being compiled.
        division_allowed = not on_board or showing_all
        named = collect_options.stamp_preset(clip, opts, w.name_index,
                                             division_allowed=division_allowed)
        focused = getattr(board, "focused", None) if on_board else None
        # The options' column while another is opened out: the card lands out
        # of sight, so the page is not asked to bring it into view.
        out_of_view = bool(on_board and focused and focused != clip.section.value)
        # Never use up a column that a board button armed for its own import.
        # On the board the photo arms the column worked out above instead, so
        # a category opened out never takes a photo the options send elsewhere.
        saved = getattr(w, "_pending_section", None)
        w._pending_section = clip.section if on_board else None
        self._adding = True
        try:
            rows = w._add_loose(
                [clip], quiet=True,
                tidy=None if opts.trim == "layout" else opts.trim == "always",
                reveal=opts.reveal and not out_of_view) or []
        finally:
            w._pending_section = saved
            self._adding = False
        if not rows:
            return
        row = rows[0]
        if named:
            self._preset[row.id] = (row, {
                "newspaper": row.clip.newspaper, "edition": row.clip.edition,
                "page": row.clip.page, "confidence": row.clip.name_confidence})
        self._photos += 1
        self._remember(w.stack_for(pool))
        self._thumb_row = row
        # The photo's own notes are kept apart from its message, so a caption
        # copied just before it can say them too.
        notes = ""
        if on_board:
            message = (ADDED_BOARD_NAMED if named else ADDED_BOARD).format(
                column=row.clip.section.value, display=named)
            kept = row.clip.division or getattr(board, "active", "")
            if (opts.default_division and not division_allowed and kept
                    and kept != opts.default_division):
                # Not put on, so the card stays on the board being compiled -
                # but the options line says every photo gets it, so say why
                # this one did not (review of A2, round 2).
                notes += NOTE_SESSION_DIVISION.format(
                    kept=collect_options.division_name(kept, w.config),
                    code=opts.default_division)
            if out_of_view:
                notes += NOTE_COLUMN_HIDDEN.format(focused=focused,
                                                   column=row.clip.section.value)
        elif pool.entry_row_for_clip(row.id) < 0:
            message = ADDED_HIDDEN.format(which=self._which(pool, row))
        elif self._ticking():
            message = (ADDED_TICKED_NAMED if named else ADDED_TICKED).format(
                which=self._which(pool, row), display=named) + NOTE_TICKED
        else:
            message = (ADDED_NAMED if named else ADDED).format(
                which=self._which(pool, row), display=named)
        if max(width, height) < self.WARN_LONG_SIDE:
            notes += SMALL.format(w=width, h=height)
        if not row.clip.crop.is_identity:
            notes += TIDIED
        self._say(message + notes)
        self._remember_copy(f"picture {width}x{height} px",
                            (f"added as {self._which(pool, row)}"
                             if not on_board else
                             f"added to {row.clip.section.value}")
                            + (", named from this session's settings" if named else ""))
        self._take_early_caption(pool, row, notes)

    def _take_early_caption(self, pool, row, photo_notes: str = "") -> None:
        """A caption copied a moment before its photo, when the options say
        it goes on the photo that follows it."""
        pending = self.pending
        if (not self.options.early_caption or self._ticking() or pending is None
                or not pending.early or pending.link_only or pending.typed
                or time.monotonic() - pending.made > collect_options.EARLY_CAPTION_SECONDS):
            return
        found = self._valid(pending.target)
        if found is None or found[1] is not row:
            return
        said = self._put_pending(pool, row, pending)
        clip = row.clip
        if said is None or clip.caption_raw != pending.reading.text:
            return
        which = self._which(pool, row)
        on_board = pool is self.window.board_model
        # One message for the two copies, so it carries what each would have
        # said alone: the caption's notes (the division filed, or the card
        # kept under the board's) and the photo's (small, trimmed, out of view).
        hidden = "" if on_board or pool.entry_row_for_clip(row.id) >= 0 else NOTE_HIDDEN
        self._say((EARLY_USED_BOARD if on_board else EARLY_USED).format(
            which=which, column=clip.section.value,
            display=_elide(clip.display_caption or pending.reading.display))
            + self._reading_notes(pending.reading) + said[1] + photo_notes + hidden)
        self._remember_copy("text", f"caption copied just before its photo, onto {which}")

    def _off(self, item, message: str, why: str) -> None:
        """A copy of a kind the person switched off: said, never flashed."""
        self._say(message)
        self._remember_copy(f"text, {_shape(item.text)}", f"not used ({why})")

    def _take_text(self, item) -> None:
        w = self.window
        opts = self.options
        reading = copied.read(item.text, w.name_index, collect_options.reader_rules(opts))
        if reading.kind == "picture-address":
            # The previous photo is no longer waiting: the next caption must
            # not land on it just because this copy missed.
            self._no_photo_waiting()
            self._say(PICTURE_ADDRESS, problem=True)
            self._alert()
            self._remember_copy("a picture's address", "not used")
            return
        notes = ""
        # What the person switched off is not used, and a copy holding both a
        # caption and a link keeps the half that is still on.
        if reading.kind == "caption+link" and not (opts.captions and opts.links):
            if opts.captions:
                reading = replace(reading, kind="caption", url="")
                notes += NOTE_LINK_OFF
            elif opts.links:
                reading = replace(reading, kind="link")
            else:
                self._off(item, CAPTIONS_OFF, "captions and links are off")
                return
        if reading.kind == "caption" and not opts.captions:
            self._off(item, CAPTIONS_OFF, "captions are off")
            return
        if reading.kind == "link" and not opts.links:
            self._off(item, LINKS_OFF, "links are off")
            return
        if reading.kind == "nothing":
            reason = reading.reason or "it did not look like a caption"
            if not opts.captions and reason not in NOT_A_CAPTION_AT_ALL:
                self._off(item, CAPTIONS_OFF, "captions are off")
                return
            # A caption the reader could not take apart is still the caption
            # the office copied. With a photo waiting for one, short and made
            # of words, it is printed as typed - the report needs the words
            # above the picture more than it needs them in separate fields -
            # and flagged amber, because nobody has checked them.
            how, words = (("", "") if reason in NOT_A_CAPTION_AT_ALL else
                          as_typed(item.text, *collect_options.as_typed_limits(opts)))
            if how and self._ticking() and self._pair() is None:
                # Captions go on the ticked clipping and not one is ticked:
                # that is the reason, and copying the words again cannot help.
                self.pending = Pending(reading, None, PICK_ONE, False, PRINT_AS_TYPED,
                                       typed=words, raw=item.text, made=time.monotonic())
                self._say(PICK_ONE, problem=True)
                self._alert()
                self._remember_copy(f"text, {_shape(item.text)}",
                                    "not used: not one clipping is ticked")
                return
            pair = self._pair() if how else None
            if pair is not None and not self._caption_open(pair[1]):
                pair = None
            if pair is not None and pair[1].clip.label.strip():
                pair = None
            if pair is not None and how == "auto":
                pool, row, _target = pair
                which = self._which(pool, row)
                self._fill_as_typed(pool, row, words, item.text)
                self._say(AS_TYPED.format(shown=_elide(words), which=which, reason=reason))
                self._remember_copy(f"text, {_shape(item.text)}",
                                    f"printed as typed on {which} ({reason})")
                return
            if pair is not None and how == "button":
                self.pending = Pending(reading, pair[2],
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
        pair = self._pair()
        if pair is None:
            # Asked first: with captions sent to the ticked clipping, not one
            # ticked is the answer for a link too, not the links list.
            if self._ticking():
                self._refuse(reading, None, PICK_ONE, link_only=not has_caption)
                return
            if has_link and not has_caption and opts.links_to_list:
                self._to_links_list(item, reading)
                return
            self._refuse(reading, None, NO_PHOTO, link_only=not has_caption,
                         early=has_caption)
            return
        pool, row, target = pair
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
        command = None
        replaced = ""
        if has_caption:
            if clip.name_source == "manual":
                self._refuse(reading, target, _capital(TYPED.format(which=which)),
                             USE_INSTEAD)
                return
            if not self._caption_open(row):
                if opts.replace_caption and clip.name_source == "copied":
                    replaced = clip.display_caption or clip.label.strip() or "its caption"
                else:
                    self._refuse(reading, target,
                                 _capital(HAS_CAPTION.format(
                                     which=which, display=_elide(clip.display_caption))),
                                 USE_INSTEAD)
                    return
            fields, said, command = self._caption_put(reading, pool, row,
                                                      replacing=bool(replaced))
            values.update(fields)
            notes += said
            if has_link and link_open(clip):
                values.update({"url": reading.url, "show_url_box": True})
            elif has_link:
                notes += NOTE_LINK_SKIPPED.format(which=which)
        else:
            if not (link_open(clip) and (not clip.newspaper.strip() or self._is_preset(row))):
                if opts.links_to_list:
                    # No photo is waiting for this link either: the newest is
                    # a newspaper's clipping, or has its link already. This is
                    # the usual order - photo, caption, then the story's link -
                    # and refused here the link was lost with the next photo.
                    # 2.0.31's button is kept as well, without the alarm: the
                    # link may still be that photo's (review of A2, round 2).
                    self.pending = Pending(reading, target, LINK_NOT_USED.format(which=which),
                                           True, USE_LINK, listed=True)
                    self._to_links_list(item, reading, taken=which)
                    return
                self._refuse(reading, target, LINK_NOT_USED.format(which=which),
                             USE_LINK, link_only=True)
                return
            values.update({"url": reading.url, "show_url_box": True})

        step = self._step_name(has_caption, "url" in values)
        if command is commands.CaptionAsTyped and values.get("label") and "url" not in values:
            step = "Caption copied as typed"
        self._fill(pool, row, values, step, command=command)
        self.pending = None
        self._thumb_row = row
        self._say(self._named(reading, which, has_caption, "url" in values,
                              display=clip.display_caption, replaced=replaced) + notes)
        self._remember_copy(f"text, {_shape(item.text)}",
                            f"{step.lower()} onto {which}"
                            + (" (it replaced a copied caption)" if replaced else ""))

    def _caption_put(self, reading, pool, row, replacing: bool = False):
        """(values, notes, command) for a caption going on this clipping.

        The caption's own fields; on a photo named from the session's settings
        the fields the caption leaves empty keep those; the division its short
        form names, when the clipping has none and it cannot hide the card; and
        the words printed above the picture when the options ask for that.
        """
        w = self.window
        opts = self.options
        clip = row.clip
        values = dict(copied.caption_values(reading))
        notes = ""
        command = None
        stamped = self._stamped(row)
        if stamped is not None:
            used = False
            for key, field in (("newspaper", "newspaper"), ("edition", "edition"),
                               ("page", "page")):
                if not str(values.get(field, "")).strip() and stamped.get(key):
                    values[field] = stamped[key]
                    used = True
            if used:
                values["name_confidence"] = min(values.get("name_confidence", 1.0),
                                                stamped.get("confidence", 1.0))
        if not str(values.get("newspaper", "")).strip():
            notes += NOTE_NO_PAPER
        if opts.set_division:
            code = collect_options.division_used(reading, w.name_index)
            if code:
                name = collect_options.division_name(code, w.config)
                on_board = pool is w.board_model
                showing = getattr(getattr(w, "board", None), "active", "")
                showing_all = showing in ("", collect_options.ALL_DIVISIONS)
                current = clip.division
                if not current and (not on_board or showing_all or code == showing):
                    values["division"] = code
                    notes += NOTE_DIVISION.format(name=name, code=code)
                elif current == code:
                    pass
                elif on_board and not showing_all and (current or showing) == showing:
                    # Only a card under the one division on show is kept for
                    # the board's sake; on All divisions it is its own.
                    kept = collect_options.division_name(showing, w.config)
                    notes += NOTE_DIVISION_KEPT_BOARD.format(code=code, name=name, kept=kept)
                elif current:
                    kept = collect_options.division_name(current, w.config)
                    notes += (NOTE_DIVISION_KEPT_CARD if on_board else NOTE_DIVISION_KEPT
                              ).format(code=code, name=name, kept=kept)
        if replacing and self._copied_label(clip):
            # The words a copy printed above the picture go with the caption
            # they came from; a headline somebody typed is never touched.
            values["label"] = ""
            command = commands.CaptionAsTyped
        if opts.caption_into == "fields+headline" and (not clip.label.strip()
                                                      or values.get("label") == ""):
            values["label"] = reading.text
            command = commands.CaptionAsTyped
        return values, notes, command

    def _to_links_list(self, item, reading, taken: str = "") -> None:
        """A story link no photo is waiting for: into the links list, where
        Capture takes it, instead of being lost. ``taken`` names the newest
        photo when it was there but already had a newspaper or a link.

        The list is added to - also when its window was only closed, so the
        links and marks left in it stay - and the window is not put in front
        of Chrome: it opens when the person comes back (MainWindow.open_links).
        """
        from ..core import links

        w = self.window
        url = reading.url
        try:
            if any(found.url.lower() == url.lower() for found in links.find(w.links_kept())):
                self._say(LINK_LISTED)
                self._remember_copy(f"text, {_shape(item.text)}",
                                    "link already in the links list")
                return
            w.open_links(url, quiet=True)
            many = len(links.find(w.links_kept())) or 1
            dialog = getattr(w, "links_dialog", None)
            later = dialog is not None and not dialog.isVisible()
        except RuntimeError:
            return
        s = "s" if many != 1 else ""
        self._say((_capital(LINK_TO_LIST_TAKEN.format(which=taken, many=many, s=s)) if taken
                   else LINK_TO_LIST.format(many=many, s=s))
                  + (LIST_WHEN_BACK if later else ""))
        self._remember_copy(f"text, {_shape(item.text)}", "link added to the links list"
                            + (f" ({taken} already had a newspaper or a link)" if taken else ""))

    def _take_out_of_list(self, url: str) -> str:
        """A link Collect listed, now put on a photo with the button: out of
        the links list again, so Capture does not make a second clipping of
        it. Returns the note the bar adds, "" when the list never had it."""
        from ..core import links

        w = self.window
        key = (url or "").lower()
        try:
            if not any(found.url.lower() == key for found in links.find(w.links_kept())):
                return ""
            dialog = getattr(w, "links_dialog", None)
            if dialog is not None and dialog.take_out(url):
                return NOTE_LINK_TAKEN_OUT
        except RuntimeError:
            return ""
        return NOTE_LINK_STILL_LISTED

    def _no_photo_waiting(self) -> None:
        """A copied picture was refused or not collected: no photo is waiting.

        The caption copied next is that picture's, so it must not land on the
        photo before. And a caption copied just before it was that picture's
        too, so the photo after must not take it by itself: it gets 2.0.31's
        button instead (review of A2, round 2)."""
        self.target = None
        if self.pending is not None:
            self.pending.early = False

    def links_not_taken(self, words: str) -> str:
        """A Ctrl+V of story links while Collect is on and has dealt with this
        copy: the words less any link already on a clipping or in the links
        list, or "" once nothing is left, said on the window's message line.
        Listed again, Capture would make a second clipping of the story."""
        from ..core import links

        w = self.window
        try:
            found = links.find(words)
            kept = {row.url.lower() for row in links.find(w.links_kept())}
            on = {}
            for pool in (w.model, w.board_model):
                for row in pool.rows:
                    url = getattr(row.clip, "url", "") if row.clip is not None else ""
                    if url.strip():
                        on.setdefault(url.strip().lower(), (pool, row))
        except RuntimeError:
            return words
        left = [row for row in found
                if row.url.lower() not in kept and row.url.lower() not in on]
        if len(left) == len(found):
            return words
        if left:
            return "\n".join((f"{row.label}\n" if row.label else "") + row.url for row in left)
        # In the list first: that is where Ctrl+V of a link was going, and
        # the window with it in opens.
        first = found[0].url.lower() if found else ""
        if first in kept or first not in on:
            w._flash(PASTE_LINK_LISTED, "info")
            w.open_links()
        else:
            w._flash(PASTE_LINK_ON.format(which=self._which(*on[first])), "info")
        return ""

    def _step_name(self, caption: bool, link: bool) -> str:
        if caption and link:
            return "Caption and link copied"
        return "Caption copied" if caption else "Link copied"

    def _named(self, reading, which: str, caption: bool, link: bool,
               display: str = "", replaced: str = "") -> str:
        if not caption:
            return LINK_ADDED.format(which=which, site=_site(reading.url))
        self._captions += 1
        shown = _elide(display or reading.display)
        if replaced:
            message = REPLACED.format(display=shown, old=_elide(replaced), which=which)
        else:
            message = (NAMED_LINK if link else NAMED).format(display=shown, which=which)
        return message + self._reading_notes(reading)

    @staticmethod
    def _reading_notes(reading) -> str:
        """What a caption's reading adds after the message: a paper or city
        not on the list, a page read from a bare number."""
        said = ""
        if not getattr(reading, "paper_known", True):
            said += (NOTE_PAPER if _indic(reading.text) else NOTE_PAPER_TYPED).format(
                paper=reading.newspaper)
        if reading.edition and not reading.edition_known:
            said += NOTE_EDITION.format(edition=reading.edition)
        if reading.page_from_bare_number:
            said += NOTE_BARE_PAGE
        return said

    def _fill_as_typed(self, pool, row, words: str, raw: str) -> None:
        """The copied words printed above the picture as they are."""
        values = {
            "label": words, "no_title": False,
            "caption_raw": (raw or "").strip()[:300],
            "name_source": "copied", "name_confidence": AS_TYPED_CONFIDENCE,
        }
        if self._is_preset(row):
            # The session's newspaper, city and page only stood in for the
            # caption. These words are the caption, so the fields must not
            # go on naming another paper than the page prints - the coverage
            # summary counts papers from them. The same step, so one undo
            # brings the session's name back.
            values.update({"newspaper": "", "edition": "", "page": ""})
        self._captions += 1
        self._thumb_row = row
        self.pending = None
        self._fill(pool, row, values, "Caption copied as typed",
                   command=commands.CaptionAsTyped)

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
                link_only: bool = False, early: bool = False) -> None:
        """Say why a copy was not used, and keep it for the one button."""
        self.pending = Pending(reading, target, why, link_only, button,
                               early=early, made=time.monotonic())
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
            if self._caption_open(row) and not row.clip.label.strip():
                which = self._which(pool, row)
                self._fill_as_typed(pool, row, pending.typed, pending.raw)
                self._say(AS_TYPED.format(shown=_elide(pending.typed), which=which,
                                          reason=reading.reason or "it did not read"))
                self._remember_copy("text", f"printed as typed on {which}, on the button")
            self._render()
            return
        said = self._put_pending(pool, row, pending)
        if said is None:
            self.pending = None
            self._render()
            return
        # A link that also went to the links list is that photo's after all.
        listed = self._take_out_of_list(reading.url) if pending.listed else ""
        self._say(said[0] + said[1] + listed)

    def _put_pending(self, pool, row, pending):
        """A refused caption or link onto this clipping, as one undo step.

        Returns (what the bar says, the caption's notes after it), or None
        when the copy had nothing this clipping can take."""
        reading = pending.reading
        caption = reading.kind in ("caption", "caption+link") and not pending.link_only
        values: dict = {}
        notes = ""
        command = None
        if caption:
            fields, notes, command = self._caption_put(reading, pool, row)
            values.update(fields)
        if reading.url and (pending.link_only or not row.clip.url.strip()):
            values.update({"url": reading.url, "show_url_box": True})
        if not values:
            return None
        step = self._step_name(caption, "url" in values)
        if command is commands.CaptionAsTyped and values.get("label") and "url" not in values:
            step = "Caption copied as typed"
        self._fill(pool, row, values, step, command=command)
        self.pending = None
        self._thumb_row = row
        return (self._named(reading, self._which(pool, row), caption,
                            "url" in values, display=row.clip.display_caption), notes)

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
        if not self.options.alert:
            return
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
        # The options that differ from the defaults, on a line of their own so
        # the message above keeps its exact words. Hidden while none do.
        self.options_line = QLabel()
        self.options_line.setObjectName("CollectOptionsLine")
        self.options_line.setWordWrap(True)
        self.options_line.setTextFormat(Qt.RichText)
        self.options_line.setTextInteractionFlags(Qt.LinksAccessibleByMouse
                                                  | Qt.LinksAccessibleByKeyboard)
        self.options_line.setOpenExternalLinks(False)
        self.options_line.setToolTip("Collect's options for this session. They "
                                     "last until the program closes and are "
                                     "never saved.")
        self.options_line.linkActivated.connect(self._options_link)
        self.options_line.hide()
        words.addWidget(self.headline)
        words.addWidget(self.message)
        words.addWidget(self.options_line)
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
            line = collect_options.options_html(self.options)
            if self.options_line.text() != line:
                self.options_line.setText(line)
            self.options_line.setVisible(bool(line))
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
