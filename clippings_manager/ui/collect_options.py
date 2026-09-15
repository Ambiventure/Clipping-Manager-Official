"""Collect from WhatsApp's options: what it takes, and how, for one session.

Right-click the Collect from WhatsApp button for them. They are a person's
choice for the morning in front of them - "every photo today is Dainik
Jagran, Lucknow", "a city on its own is a caption" - so they live on the
Collector in memory, last until the program closes, and are never written
anywhere. A newspaper name remembered overnight is exactly the setting that
would quietly mis-name tomorrow's clippings.

Every default is what Collect has always done. Each option that lets through
something the reader would refuse is off until a person switches it on, and
while any option differs from its default the Collect bar lists it, the
button has an amber edge, and What was copied... records each change.

Kept out of ui/collect.py on purpose: that module may ask core/copied for
read, caption_values and as_typed_words only (test_copied pins it), so the
reader rules and the name lists are reached from here.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, fields, replace
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QIntValidator
from PySide6.QtWidgets import (QComboBox, QCompleter, QDialog, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QPushButton, QVBoxLayout)

from ..core import copied
from ..core.models import Section
from . import theme

#: A caption copied just before its photo goes on that photo only this soon
#: after it was copied. Longer, and it is a caption for a photo that never came.
EARLY_CAPTION_SECONDS = 120

#: What the sentiment board shows when no division is picked. The same string
#: as sentiment_board.ALL_DIVISIONS, which is not imported here because the
#: board module is heavy and this one is loaded with the window's header.
ALL_DIVISIONS = "__all__"

AS_TYPED_CHOICES = ("auto16", "auto6", "button", "never")
CAPTION_INTO_CHOICES = ("fields", "fields+headline")
TRIM_CHOICES = ("layout", "always", "never")
SAME_PHOTO_CHOICES = ("point", "again")
PAIR_CHOICES = ("newest", "ticked")
REFUSE_CHOICES = (200, 400, 600, 0)
COLUMN_CHOICES = ("", Section.POSITIVE.value, Section.NEUTRAL.value,
                  Section.NEGATIVE.value, Section.DIGITAL.value)


@dataclass(frozen=True)
class CollectOptions:
    """One session's choices for Collect. The defaults are 2.0.31's Collect,
    with the division short forms read - the fix the office asked for."""

    # What to collect.
    photos: bool = True
    captions: bool = True
    links: bool = True
    #: A story link copied with no photo waiting used to be refused and then
    #: lost when the next photo came. It goes to the links list instead.
    links_to_list: bool = True

    # Reading captions.
    division_codes: bool = True
    set_division: bool = True
    city_alone: bool = False
    unlisted_paper_in_english: bool = False
    towns_as_typed: bool = True
    as_typed: str = "auto16"
    caption_into: str = "fields"

    # Every photo Collect adds.
    default_newspaper: str = ""
    default_city: str = ""
    default_page: str = ""
    default_division: str = ""
    board_column: str = ""

    # Photos.
    refuse_under: int = 200
    trim: str = "layout"
    same_photo: str = "point"

    # Pairing.
    replace_caption: bool = False
    early_caption: bool = False
    pair_with: str = "newest"

    # While collecting.
    reveal: bool = True
    alert: bool = True

    @property
    def has_preset(self) -> bool:
        """Whether photos arrive already named."""
        return bool(self.default_newspaper.strip() or self.default_city.strip()
                    or self.default_page.strip())


DEFAULTS = CollectOptions()


# ------------------------------------------------------------ what they mean
def reader_rules(opts: CollectOptions) -> copied.ReaderRules:
    """The reader's rules for these options."""
    if not isinstance(opts, CollectOptions):
        opts = DEFAULTS
    return copied.ReaderRules(
        division_codes=opts.division_codes,
        city_alone=opts.city_alone,
        unlisted_paper_in_english=opts.unlisted_paper_in_english,
        towns_as_typed=opts.towns_as_typed)


def as_typed_limits(opts: CollectOptions) -> tuple[int, int]:
    """(words printed as typed at once, words offered on the button). A 0
    means that tier is never used."""
    return {"auto16": (16, 60), "auto6": (6, 60),
            "button": (0, 60), "never": (0, 0)}.get(opts.as_typed, (16, 60))


def division_used(reading, index) -> str:
    """The division short form a caption's city was read from, or ""."""
    try:
        return copied.division_used(reading, index)
    except Exception:  # noqa: BLE001 - a code missed is a division not filed
        return ""


def division_name(code: str, config: Optional[dict] = None) -> str:
    """"Lucknow" for "LKO", as divisions.json names it; the code itself when
    the file does not know it."""
    from ..core import sentiment

    try:
        found = sentiment.division_by_code(code, config)
    except Exception:  # noqa: BLE001
        found = None
    return found.name if found is not None else code


def preset_display(opts: CollectOptions) -> str:
    """"Dainik Jagran, Lucknow, Page 3": what a preset photo prints."""
    parts = [p for p in (opts.default_newspaper.strip(), opts.default_city.strip()) if p]
    if parts and opts.default_page.strip():
        parts.append(f"Page {opts.default_page.strip()}")
    return ", ".join(parts) or (f"Page {opts.default_page.strip()}"
                                if opts.default_page.strip() else "")


def preset_confidence(opts: CollectOptions, index) -> float:
    """1.0 for names on the lists. A session newspaper not on the list is
    flagged amber, as an unlisted paper read from a caption is; a city not on
    the list is kept as typed at the reader's 0.8."""
    confidence = 1.0
    paper = opts.default_newspaper.strip()
    if paper and not copied.listed_paper(paper, index):
        confidence = min(confidence, copied.UNLISTED_PAPER_CONFIDENCE)
    city = opts.default_city.strip()
    if city and not copied.listed_city(city, index):
        confidence = min(confidence, 0.8)
    return confidence


def stamp_preset(clip, opts: CollectOptions, index, division_allowed: bool) -> str:
    """Name a photo Collect is about to add from the session's settings.

    Returns what it prints ("" when nothing was named). The name is stamped as
    a copied one, with no copied caption behind it, so the next caption copied
    still replaces it (Collector._caption_open) and merging never re-guesses
    it (profiles.apply_to_clip). The division goes on only where it cannot hide
    the photo: in the press report, or on a board showing every division.
    """
    if division_allowed and opts.default_division and not clip.division:
        clip.division = opts.default_division
    if not opts.has_preset:
        return ""
    clip.newspaper = opts.default_newspaper.strip()
    clip.edition = opts.default_city.strip()
    clip.page = opts.default_page.strip()
    clip.caption_raw = ""
    clip.name_source = "copied"
    clip.name_confidence = preset_confidence(opts, index)
    clip.no_title = False
    return preset_display(opts)


# ------------------------------------------------------------- how they read
def _preset_phrase(opts: CollectOptions, config=None) -> str:
    said = preset_display(opts)
    if opts.default_division:
        division = f"{opts.default_division} division"
        said = f"{said}, {division}" if said else division
    return said


#: field -> (the label in the menu, how a value reads). Used for the bar, the
#: tooltip and What was copied... - never holding anything copied.
def _on(value) -> str:
    return "on" if value else "off"


_AS_TYPED_SAID = {"auto16": "up to 16 words at once", "auto6": "up to 6 words at once",
                  "button": "only on the button", "never": "refused"}
_TRIM_SAID = {"layout": "as the Layout card says", "always": "always trimmed",
              "never": "never trimmed"}


def _refuse_said(value: int) -> str:
    return f"under {value} px" if value else "never"


_PHRASES: dict[str, Callable[[CollectOptions], str]] = {
    "photos": lambda o: "photos are not collected",
    "captions": lambda o: "captions are not used",
    "links": lambda o: "links are not used",
    "links_to_list": lambda o: "a link with no photo waiting is not put in the links list",
    "division_codes": lambda o: "LKO, MB and the other short forms are not read",
    "set_division": lambda o: "short forms do not file the division",
    "city_alone": lambda o: "a city on its own is a caption",
    "unlisted_paper_in_english": lambda o: "a newspaper not on the list, in English, is read",
    "towns_as_typed": lambda o: "only cities on the list are taken",
    "as_typed": lambda o: f"captions that cannot be read: {_AS_TYPED_SAID.get(o.as_typed, o.as_typed)}",
    "caption_into": lambda o: "captions also print as copied",
    "board_column": lambda o: f"photos go to the {o.board_column} column",
    "refuse_under": lambda o: (f"pictures under {o.refuse_under} px are refused"
                               if o.refuse_under else "small pictures are never refused"),
    "trim": lambda o: f"the phone's bars are {_TRIM_SAID.get(o.trim, o.trim)}",
    "same_photo": lambda o: "a photo already in the list is added again",
    "replace_caption": lambda o: "a new caption replaces a copied one",
    "early_caption": lambda o: "a caption copied just before its photo goes on it",
    "pair_with": lambda o: "captions go on the one clipping ticked in the press report",
    "reveal": lambda o: "new photos are not brought into view",
    "alert": lambda o: "the taskbar does not flash",
}

_PRESET_FIELDS = ("default_newspaper", "default_city", "default_page", "default_division")

_LABELS = {
    "photos": ("photos", _on),
    "captions": ("captions", _on),
    "links": ("links to web stories", _on),
    "links_to_list": ("a link with no photo waiting goes to the links list", _on),
    "division_codes": ("read LKO, MB, UMB, DLI, JAT, FZR as the division's city", _on),
    "set_division": ("file the clipping under that division", _on),
    "city_alone": ("a city on its own is a caption", _on),
    "unlisted_paper_in_english": ("a newspaper not on the list, in English, before a listed city", _on),
    "towns_as_typed": ("keep a town not on the city list as typed", _on),
    "as_typed": ("captions that cannot be read", lambda v: _AS_TYPED_SAID.get(v, v)),
    "caption_into": ("where a caption goes",
                     lambda v: "the boxes, and printed as copied" if v == "fields+headline"
                     else "the newspaper, city and page boxes"),
    "board_column": ("board column", lambda v: v or "the column opened out, else Neutral"),
    "refuse_under": ("refuse small pictures", _refuse_said),
    "trim": ("phone's bars", lambda v: _TRIM_SAID.get(v, v)),
    "same_photo": ("a photo already in the list",
                   lambda v: "add it again" if v == "again" else "point at it"),
    "replace_caption": ("a new caption replaces one already copied", _on),
    "early_caption": ("a caption copied just before its photo goes on it", _on),
    "pair_with": ("caption goes on",
                  lambda v: ("the one clipping ticked in the press report" if v == "ticked"
                             else "the newest photo")),
    "reveal": ("bring each new photo into view", _on),
    "alert": ("flash the taskbar when a copy is not used", _on),
}


def changes(opts: CollectOptions) -> list[str]:
    """Short plain phrases for every option that differs from its default."""
    if not isinstance(opts, CollectOptions):
        return []
    said = []
    for field in fields(CollectOptions):
        name = field.name
        if name in _PRESET_FIELDS:
            continue
        if getattr(opts, name) != getattr(DEFAULTS, name):
            said.append(_PHRASES[name](opts))
    if any(getattr(opts, name) != getattr(DEFAULTS, name) for name in _PRESET_FIELDS):
        said.insert(0, f"every photo: {_preset_phrase(opts)}")
    return said


def change_lines(old: CollectOptions, new: CollectOptions) -> list[str]:
    """What a change of options did, one line each, for What was copied..."""
    lines = []
    for field in fields(CollectOptions):
        name = field.name
        if name in _PRESET_FIELDS:
            continue
        if getattr(old, name) != getattr(new, name):
            label, how = _LABELS[name]
            lines.append(f"{label}: {how(getattr(new, name))}")
    if any(getattr(old, name) != getattr(new, name) for name in _PRESET_FIELDS):
        lines.insert(0, "every photo: " + (_preset_phrase(new) or "nothing set"))
    return lines


# ------------------------------------------------------------------- the menu
class StayOpenMenu(QMenu):
    """A menu that stays open when a tick is toggled, so several options can
    be set in one go. A choice among several (a radio) and every other item
    close it as a menu always does."""

    @staticmethod
    def _stays(action) -> bool:
        return (action is not None and action.isEnabled() and action.isCheckable()
                and action.menu() is None
                and (action.actionGroup() is None or not action.actionGroup().isExclusive()))

    #: Whether a press landed on this menu since its last release, and on
    #: which item. QMenu takes a release only when its press was on the menu;
    #: a release on its own - a press that began outside or in another menu -
    #: must not flip an option such as Photos without anybody seeing it.
    _press_seen = False
    _pressed = None

    def mousePressEvent(self, event):  # noqa: N802 - Qt name
        pos = event.position().toPoint()
        self._press_seen = self.rect().contains(pos)
        self._pressed = self.actionAt(pos) if self._press_seen else None
        super().mousePressEvent(event)

    def _over_menu_before(self, event) -> bool:
        """Whether a release is over a menu this one was opened from. While a
        submenu is open Qt gives it every click, and QMenu hands a click over
        the menu below on to that menu, where its press landed."""
        where = event.globalPosition().toPoint()
        below = self.parentWidget()
        while isinstance(below, QMenu):
            if below.isVisible() and below.rect().contains(below.mapFromGlobal(where)):
                return True
            below = below.parentWidget()
        return False

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt name
        action = self.actionAt(event.position().toPoint())
        seen, pressed = self._press_seen, self._pressed
        self._press_seen, self._pressed = False, None
        if not seen and self._over_menu_before(event):
            # A click on the menu below while this submenu is open: its press
            # went down there, so its release must too. Dropped here, a tick
            # clicked with a submenu open did nothing (review of A2, round 2).
            # That menu's own record of the press still drops a lone release.
            super().mouseReleaseEvent(event)
            return
        if not seen:
            # Not handed to QMenu either. A tick taken here never reaches
            # QMenu's release, so QMenu still counts that earlier press as
            # its own and would act on this lone release (measured: it ticked
            # Photos and closed the menu).
            event.accept()
            return
        if action is not None and action is pressed and self._stays(action):
            action.trigger()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):  # noqa: N802 - Qt name
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            action = self.activeAction()
            if self._stays(action):
                action.trigger()
                event.accept()
                return
        super().keyPressEvent(event)


MENU_TITLE = "Collect's options - for as long as the program is open"


def build_menu(collector, parent) -> QMenu:
    """The options menu, reflecting the collector's options as they are.

    Every item sets one option through collector.set_options, and the menu's
    ticks, choices and Reset follow straight away, so a change made with the
    menu open shows in it."""
    menu = StayOpenMenu(parent)
    menu.setObjectName("CollectOptionsMenu")
    menu.setToolTipsVisible(True)
    bindings: list = []          # (action, lambda options -> checked)
    window = collector.window

    def head(target: QMenu, text: str) -> None:
        action = target.addAction(text)
        action.setEnabled(False)

    def sync() -> None:
        opts = collector.options
        for action, checked in bindings:
            try:
                was = action.blockSignals(True)
                action.setChecked(bool(checked(opts)))
                action.blockSignals(was)
            except RuntimeError:
                pass
        try:
            reset.setEnabled(bool(changes(opts)))
            clear.setEnabled(any(getattr(opts, n) != getattr(DEFAULTS, n)
                                 for n in _PRESET_FIELDS))
        except RuntimeError:
            pass

    def tick(target: QMenu, text: str, name: str, tip: str = "") -> QAction:
        action = target.addAction(text)
        action.setCheckable(True)
        action.setChecked(bool(getattr(collector.options, name)))
        if tip:
            action.setToolTip(tip)
        action.toggled.connect(
            lambda on, n=name: (collector.set_options(replace(collector.options, **{n: on})),
                                sync()))
        bindings.append((action, lambda o, n=name: getattr(o, n)))
        return action

    def choice(target: QMenu, title: str, name: str, items: list, tip: str = "",
               in_effect: Optional[Callable] = None) -> QMenu:
        """A submenu of radios. ``in_effect`` gives the value that is really
        used where the menu was opened, when that can differ from the option."""
        in_effect = in_effect or (lambda o, n=name: getattr(o, n))
        sub = StayOpenMenu(title, target)
        sub.setToolTipsVisible(True)
        if tip:
            sub.menuAction().setToolTip(tip)
        group = QActionGroup(sub)
        group.setExclusive(True)
        for value, text, *rest in items:
            action = sub.addAction(text)
            action.setCheckable(True)
            action.setActionGroup(group)
            action.setChecked(in_effect(collector.options) == value)
            if rest and rest[0] is False:
                action.setEnabled(False)
            action.triggered.connect(
                lambda _on=False, n=name, v=value: (
                    collector.set_options(replace(collector.options, **{n: v})), sync()))
            bindings.append((action, lambda o, v=value: in_effect(o) == v))
        target.addMenu(sub)
        return sub

    head(menu, MENU_TITLE)
    menu.addSeparator()

    head(menu, "What to collect")
    tick(menu, "Photos", "photos",
         "A picture you copy becomes a clipping. Switched off, a copied picture "
         "is still looked at to know it is a picture, but nothing is added.")
    tick(menu, "Captions", "captions")
    tick(menu, "Links to web stories", "links")
    tick(menu, "A link with no photo waiting goes to the links list", "links_to_list",
         "A photo waits for a link only while it has no newspaper and no link - so "
         "a link copied after its photo's caption goes to the list too. Switched "
         "off, it is refused and kept only for the button.")
    menu.addSeparator()

    head(menu, "Reading captions")
    tick(menu, "Read LKO, MB, UMB, DLI, JAT, FZR as the division's city", "division_codes",
         "\"HT LKO\" is Hindustan Times, Lucknow. JAT and MB only in capitals.")
    tick(menu, "File the clipping under that division", "set_division",
         "Only when the clipping has no division yet. A card on the sentiment "
         "board keeps the division the board is showing.")
    tick(menu, "A city on its own is a caption", "city_alone",
         "\"LKO\" or \"Lucknow page 3\" names the photo's city, with the newspaper "
         "left empty and flagged - or taken from this session's newspaper.")
    tick(menu, "A newspaper not on the list, in English, before a listed city",
         "unlisted_paper_in_english",
         "\"Veer Arjun Delhi\" is named as typed and flagged, as a Hindi paper not "
         "on the list already is.")
    tick(menu, "Keep a town not on the city list as typed", "towns_as_typed")
    choice(menu, "Captions that cannot be read", "as_typed", [
        ("auto16", "Print as typed, up to 16 words at once"),
        ("auto6", "Print as typed, up to 6 words at once"),
        ("button", "Only offer them on the button"),
        ("never", "Refuse them"),
    ])
    choice(menu, "Where a caption goes", "caption_into", [
        ("fields", "Newspaper, city and page boxes"),
        ("fields+headline", "Those boxes, and printed above the picture exactly as copied"),
    ])
    menu.addSeparator()

    head(menu, "Every photo Collect adds")
    preset = menu.addAction("Newspaper, city, page and division for this session…")
    preset.triggered.connect(lambda: collector.show_defaults(parent))
    clear = menu.addAction("Clear them")
    clear.triggered.connect(lambda: (collector.set_options(replace(
        collector.options, **{n: getattr(DEFAULTS, n) for n in _PRESET_FIELDS})), sync()))
    choice(menu, "Board column", "board_column", [
        ("", "The column opened out, else Neutral"),
        *[(value, value) for value in COLUMN_CHOICES[1:]],
    ])
    menu.addSeparator()

    head(menu, "Photos")
    choice(menu, "Refuse small pictures", "refuse_under", [
        (200, "Under 200 px"), (400, "Under 400 px"), (600, "Under 600 px"), (0, "Never"),
    ])
    tidy_now = "trimmed"
    try:
        from .layout_card import tidy_wanted
        tidy_now = "trimmed" if tidy_wanted() else "left"
    except Exception:  # noqa: BLE001
        pass
    choice(menu, "Phone's bars", "trim", [
        ("layout", f"As the Layout card says (now: {tidy_now})"),
        ("always", "Always trim"),
        ("never", "Never trim"),
    ], "For photos Collect adds only - the Layout card's own setting is not changed.")
    choice(menu, "A photo already in the list", "same_photo", [
        ("point", "Point at it, add nothing"),
        ("again", "Add it again"),
    ])
    menu.addSeparator()

    head(menu, "Pairing")
    tick(menu, "A new caption replaces one already copied onto the photo", "replace_caption",
         "A name typed by hand is still never replaced.")
    tick(menu, "A caption copied just before its photo goes on it", "early_caption",
         f"Within {EARLY_CAPTION_SECONDS // 60} minutes.")
    on_report = getattr(window, "mode", "standard") != "sentiment"
    # On the board the newest photo is what really happens, so that is what
    # is ticked there: a menu showing the other would say the opposite.
    choice(menu, "Caption goes on", "pair_with", [
        ("newest", "The newest photo"),
        ("ticked", "The one clipping ticked in the press report", on_report),
    ], "Ticking is in the press report. On the sentiment board a caption goes on "
       "the newest photo whatever is chosen here.",
        in_effect=lambda o: o.pair_with if on_report else "newest")
    menu.addSeparator()

    head(menu, "While collecting")
    tick(menu, "Bring each new photo into view", "reveal")
    tick(menu, "Flash the taskbar when a copy is not used", "alert")
    menu.addSeparator()

    history = menu.addAction("What was copied…")
    history.triggered.connect(collector.show_history)
    reset = menu.addAction("Reset all options")
    reset.triggered.connect(lambda: (collector.reset_options(), sync()))
    menu.aboutToShow.connect(sync)
    sync()
    menu.bindings = bindings
    menu.reset_action = reset
    menu.clear_action = clear
    menu.preset_action = preset
    menu.history_action = history
    return menu


def find_action(menu: QMenu, text: str) -> Optional[QAction]:
    """The item with this text, in the menu or any of its submenus."""
    for action in menu.actions():
        if action.text() == text:
            return action
        if action.menu() is not None:
            found = find_action(action.menu(), text)
            if found is not None:
                return found
    return None


# ------------------------------------------------------------ the session box
class SessionDefaultsDialog(QDialog):
    """Newspaper, city, page and division for every photo Collect adds.

    Opened with open(), never exec(): nothing waits on it, and while it is up
    Collect holds copies in order, as it does for any box.
    """

    ON_LIST = "On the list."
    NOT_ON_LIST = "Not on the list - it prints as typed, flagged amber."

    def __init__(self, collector, parent=None):
        super().__init__(parent or collector.window)
        self.collector = collector
        window = collector.window
        index = window.name_index
        self.setWindowTitle("Every photo Collect adds")
        self.setModal(True)
        opts = collector.options
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(10)
        lead = QLabel("Every photo Collect adds from now on arrives with these, until "
                      "the program closes. A copied caption still replaces them; "
                      "what the caption leaves out keeps these.")
        lead.setWordWrap(True)
        outer.addWidget(lead)
        form = QFormLayout()
        form.setSpacing(6)

        def completer(names) -> QCompleter:
            done = QCompleter(sorted(set(names)), self)
            done.setCaseSensitivity(Qt.CaseInsensitive)
            done.setFilterMode(Qt.MatchContains)
            return done

        self.newspaper = QLineEdit(opts.default_newspaper)
        self.newspaper.setPlaceholderText("Dainik Jagran, or DJ")
        self.newspaper.setCompleter(completer(getattr(index, "newspaper_names", [])))
        self.paper_note = QLabel()
        self.paper_note.setStyleSheet(f"color: {theme.MUTED};")
        form.addRow("Newspaper", self.newspaper)
        form.addRow("", self.paper_note)
        self.city = QLineEdit(opts.default_city)
        self.city.setPlaceholderText("Lucknow, or LKO")
        self.city.setCompleter(completer(getattr(index, "edition_names", [])))
        self.city_note = QLabel()
        self.city_note.setStyleSheet(f"color: {theme.MUTED};")
        form.addRow("City", self.city)
        form.addRow("", self.city_note)
        self.page = QLineEdit(opts.default_page)
        self.page.setValidator(QIntValidator(1, 999, self))
        self.page.setPlaceholderText("none")
        form.addRow("Page", self.page)
        self.division = QComboBox()
        self.division.setStyleSheet(theme.COMBO_POPUP)
        self.division.addItem("None", "")
        try:
            from ..core import sentiment
            for division in sentiment.divisions(window.config):
                self.division.addItem(f"{division.name} ({division.code})", division.code)
        except Exception:  # noqa: BLE001 - no divisions file, no division
            pass
        at = self.division.findData(opts.default_division)
        self.division.setCurrentIndex(max(0, at))
        form.addRow("Division", self.division)
        outer.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.use_btn = QPushButton("Use for this session")
        self.use_btn.setDefault(True)
        self.use_btn.clicked.connect(self.accept)
        for button in (self.clear_btn, cancel, self.use_btn):
            button.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(button)
        outer.addLayout(buttons)

        # The notes follow typing, a moment after it stops: each asks the
        # reader's name lists, and nothing should run on every keystroke.
        self._notes = QTimer(self)
        self._notes.setSingleShot(True)
        self._notes.setInterval(150)
        self._notes.timeout.connect(self.refresh_notes)
        self.newspaper.textChanged.connect(lambda _t: self._notes.start())
        self.city.textChanged.connect(lambda _t: self._notes.start())
        self.refresh_notes()

    def refresh_notes(self) -> None:
        index = self.collector.window.name_index
        paper = self.newspaper.text().strip()
        listed = copied.listed_paper(paper, index) if paper else ""
        if not paper:
            self.paper_note.setText("None - a copied caption names it.")
        elif listed and listed.casefold() != paper.casefold():
            self.paper_note.setText(f"{paper} is {listed}. {self.ON_LIST}")
        else:
            self.paper_note.setText(self.ON_LIST if listed else self.NOT_ON_LIST)
        city = self.city.text().strip()
        found = copied.listed_city(city, index) if city else ""
        if not city:
            self.city_note.setText("None - a copied caption names it.")
        elif found and found.casefold() != city.casefold():
            self.city_note.setText(f"{city} is {found}. {self.ON_LIST}")
        else:
            self.city_note.setText(self.ON_LIST if found else self.NOT_ON_LIST)

    def values(self) -> dict:
        """The four settings, names spelt the way the lists spell them."""
        index = self.collector.window.name_index
        paper = " ".join(self.newspaper.text().split())
        city = " ".join(self.city.text().split())
        page = self.page.text().strip()
        return {
            "default_newspaper": (copied.listed_paper(paper, index) or paper) if paper else "",
            "default_city": (copied.listed_city(city, index) or city) if city else "",
            "default_page": page if page.isdecimal() and 1 <= int(page) <= 999 else "",
            "default_division": self.division.currentData() or "",
        }

    def clear(self) -> None:
        self.newspaper.clear()
        self.city.clear()
        self.page.clear()
        self.division.setCurrentIndex(0)

    def accept(self) -> None:
        self.collector.set_options(replace(self.collector.options, **self.values()))
        super().accept()


def options_html(opts: CollectOptions) -> str:
    """The Collect bar's second line: the changed options, and Change..."""
    said = changes(opts)
    if not said:
        return ""
    return ("Options changed: " + html.escape("; ".join(said)) + ". "
            f"<a href=\"change\" style=\"color: {theme.NAVY}; font-weight: 700;\">"
            "Change…</a>")
