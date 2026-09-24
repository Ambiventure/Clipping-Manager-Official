"""Finding a clipping by what it says.

A morning is a hundred and sixty clippings on one long page, and the question
somebody actually has is "where is the one about the hydrogen train?". Scrolling
for it means reading a hundred and sixty thumbnails.

WHAT IS SEARCHED. Everything a clipping says about itself, in this order of
preference: the headline that prints above it, the headline read off the picture
by the reader, the newspaper, the edition, and the address a link came from. A
clipping matches if any of them does, and the one that matched is what the
result shows - so it is always clear WHY something came up.

HOW IT MATCHES. Two letters are enough. A plain "contains" first, on text with
its case, its punctuation and its Devanagari matras folded away, so "hydrogen"
finds "Hydrogen" and "रेलवे" finds "रेलवे," - and then, only for anything that
did not match that way, a fuzzy pass (rapidfuzz) that forgives a letter or two,
because a headline read off a picture is never read perfectly. The fuzzy pass
needs four letters before it will guess: on two it matched half the morning.

IT IS A LENS, NOT AN EDIT. Nothing is hidden, reordered, ticked or unticked -
the list underneath is exactly as it was. Picking a result scrolls to that
clipping and opens it. Closing the box leaves nothing behind.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from PySide6.QtCore import (QEvent, QPoint, QStringListModel, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QCompleter, QDialog,
                               QDialogButtonBox, QFrame,
                               QHBoxLayout, QLabel, QLineEdit, QMenu,
                               QPushButton, QScrollArea, QToolButton,
                               QVBoxLayout, QWidget)

from . import theme

#: Fewer letters than this and nothing is looked for: one letter matches
#: almost every clipping of the morning, which is not an answer.
LEAST_LETTERS = 2
#: And the forgiving pass waits until there is enough to forgive from.
LEAST_FUZZY = 4
#: How alike a fuzzy match has to be, out of a hundred.
FUZZY_AT = 78
#: Never more than this many results: past it the box is a second list rather
#: than an answer, and the one that is wanted is not in it either.
MOST_RESULTS = 40
#: How long after the last keystroke the search runs. Long enough that typing
#: a word does not search five times.
AFTER_TYPING_MS = 140
#: How many searches back the field remembers, and where they are kept. Install
#: wide, beside the rest of the settings, because a search is about the
#: clippings rather than about one newspad - the same story is looked for in
#: whichever newspad it is being compiled into.
RECENT_KEPT = 8
RECENT_KEY = "recent_searches"
#: The padding the offer's own panel carries, which has to be added back when
#: it is sized - see offer_recent.
OFFER_PAD = 4


def recent() -> list:
    """What was searched for lately, newest first."""
    try:
        from .export_dialog import load_settings

        kept = load_settings().get(RECENT_KEY) or []
    except Exception:  # noqa: BLE001 - no settings yet is no history
        return []
    out = []
    for one in kept:
        words = str(one or "").strip()
        if words and words not in out:
            out.append(words)
    return out[:RECENT_KEPT]


def remember(wanted: str) -> None:
    """Keep one search, at the front, without repeating it."""
    words = str(wanted or "").strip()
    if len(fold(words).replace(" ", "")) < LEAST_LETTERS:
        return
    try:
        from .export_dialog import load_settings, save_settings

        kept = [one for one in recent() if one.casefold() != words.casefold()]
        save_settings({**load_settings(),
                       RECENT_KEY: [words, *kept][:RECENT_KEPT]})
    except Exception:  # noqa: BLE001 - a convenience, never a crash
        pass

#: Devanagari vowel signs, nukta and virama - the marks that make one spelling
#: of a word two. Folded away so a headline read off a picture, which often
#: loses them, still finds the one that has them.
_MARKS = re.compile(r"[ऀ-ःऺ-ॏ॑-ॗॢॣ]")
_QUIET = re.compile(r"[^\wऀ-ॿ]+", re.UNICODE)


def fold(words: str) -> str:
    """One line of text, as the search compares it."""
    plain = unicodedata.normalize("NFKD", str(words or "")).casefold()
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    plain = _MARKS.sub("", plain)
    return _QUIET.sub(" ", plain).strip()


#: What is looked at, and what each is called in a result.
FIELDS = (
    ("printed_caption", "headline"),
    ("label", "headline"),
    ("ocr_text", "read from the picture"),
    ("newspaper", "newspaper"),
    ("edition", "edition"),
    ("url", "link"),
)


def _said(clip, name: str) -> str:
    try:
        value = getattr(clip, name, "")
    except Exception:  # noqa: BLE001
        return ""
    return str(value or "").strip()


#: A field can be asked for by name, the way a search engine lets you:
#: paper:jagran, read:kavach, link:indianexpress, headline:hydrogen.
BY_NAME = {
    "headline": ("printed_caption", "label"),
    "title": ("printed_caption", "label"),
    "read": ("ocr_text",),
    "ocr": ("ocr_text",),
    "paper": ("newspaper",),
    "newspaper": ("newspaper",),
    "edition": ("edition",),
    "city": ("edition",),
    "link": ("url",),
    "url": ("url",),
}

_TOKENS = re.compile(r'"[^"]*"|\S+')


@dataclass
class Term:
    """One thing asked for: some words, where to look, and whether it must
    NOT be there."""

    words: str
    fields: tuple = ()
    negated: bool = False
    phrase: bool = False


def parse(wanted: str) -> list:
    """A query as groups of terms: [[Term, ...], ...], the groups joined by OR
    and the terms inside a group joined by AND.

    The syntax somebody already knows from a search box:

        hydrogen train        both words, anywhere
        hydrogen OR train     either one
        "vande bharat"        those words in that order
        -cricket              not that
        paper:jagran          only in the newspaper

    OR must be capitals, so a headline with the word "or" in it is still just
    a word. Everything else is a word to look for.
    """
    groups: list = [[]]
    for raw in _TOKENS.findall(str(wanted or "")):
        piece = raw.strip()
        if not piece:
            continue
        if piece == "OR":
            if groups[-1]:
                groups.append([])
            continue
        negated = piece.startswith("-") and len(piece) > 1
        if negated:
            piece = piece[1:]
        fields: tuple = ()
        if ":" in piece and not piece.startswith('"'):
            name, _sep, rest = piece.partition(":")
            found = BY_NAME.get(name.strip().lower())
            if found and rest.strip():
                fields, piece = found, rest.strip()
        phrase = piece.startswith('"') and piece.endswith('"') and len(piece) > 1
        if phrase:
            piece = piece[1:-1]
        piece = piece.strip()
        if not piece:
            continue
        groups[-1].append(Term(piece, fields, negated, phrase))
    return [group for group in groups if group]


def _looked_at(clip, term: Term) -> list:
    """[(what it is called, what it says, folded)] for the fields a term asks
    about - all of them when it asks for none."""
    wanted = term.fields
    out = []
    for name, called in FIELDS:
        if wanted and name not in wanted:
            continue
        says = _said(clip, name)
        if says:
            out.append((called, says, fold(says)))
    return out


def _term_hit(clip, term: Term) -> tuple:
    """(does this term match, which field, what it says)."""
    folded = fold(term.words)
    if not folded:
        return False, "", ""
    looked = _looked_at(clip, term)
    for called, says, plain in looked:
        if folded in plain:
            return True, called, says
    # A phrase is asked for exactly; only a loose word is guessed at.
    if term.phrase or len(folded.replace(" ", "")) < LEAST_FUZZY:
        return False, "", ""
    try:
        from rapidfuzz import fuzz
    except Exception:  # noqa: BLE001 - without it, the plain pass is the search
        return False, "", ""
    for called, says, plain in looked:
        if fuzz.partial_ratio(folded, plain) >= FUZZY_AT:
            return True, called, says
    return False, "", ""


def matches(clip, wanted: str) -> tuple:
    """(does it match, which field, what that field says) for one clipping.

    A group matches when every plain term in it does and no negated one does;
    the query matches when any group does. What is reported as the reason is
    the first field that actually matched, so the result always says why.
    """
    groups = parse(wanted)
    if not groups:
        return False, "", ""
    asked = "".join(fold(term.words).replace(" ", "")
                    for group in groups for term in group if not term.negated)
    if len(asked) < LEAST_LETTERS:
        return False, "", ""
    for group in groups:
        why_field, why_says = "", ""
        held = True
        for term in group:
            hit, called, says = _term_hit(clip, term)
            if term.negated:
                if hit:
                    held = False
                    break
                continue
            if not hit:
                held = False
                break
            if not why_field:
                why_field, why_says = called, says
        if held and why_field:
            return True, why_field, why_says
    return False, "", ""


def search(rows, wanted: str) -> list:
    """[(row, which field matched, what it says)], in list order."""
    found = []
    for row in rows:
        clip = getattr(row, "clip", None)
        if clip is None:
            continue
        hit, which, says = matches(clip, wanted)
        if hit:
            found.append((row, which, says))
            if len(found) >= MOST_RESULTS:
                break
    return found


class Result(QFrame):
    """One clipping in the results: its number, its picture, what it says."""

    picked = Signal(int)
    ticked = Signal()

    def __init__(self, number: int, row, which: str, says: str, parent=None):
        super().__init__(parent)
        self.row_id = row.id
        self.number = number
        self.setObjectName("FindResult")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "#FindResult { background: rgba(255, 255, 255, 0.55);"
            " border: 1px solid rgba(15, 23, 42, 0.08); border-radius: 10px; }"
            "#FindResult:hover { background: rgba(255, 255, 255, 0.92);"
            f" border-color: {theme.NAVY}55; }}"
            "#FindResult QLabel { background: transparent; border: none; }")
        line = QHBoxLayout(self)
        line.setContentsMargins(9, 7, 11, 7)
        line.setSpacing(10)

        self.tick = QCheckBox()
        self.tick.setToolTip("Pick this one out, to send it somewhere")
        self.tick.toggled.connect(lambda _on: self.ticked.emit())
        line.addWidget(self.tick)

        tag = QLabel(f"{number}")
        tag.setFixedWidth(30)
        tag.setAlignment(Qt.AlignCenter)
        tag.setStyleSheet(
            f"color: {theme.NAVY}; font-size: 12px; font-weight: 800;")
        line.addWidget(tag)

        picture = QLabel()
        picture.setFixedSize(54, 40)
        picture.setAlignment(Qt.AlignCenter)
        thumb = getattr(row, "thumbnail", None)
        if isinstance(thumb, QPixmap) and not thumb.isNull():
            picture.setPixmap(thumb.scaled(54, 40, Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation))
        picture.setStyleSheet("border-radius: 4px;")
        line.addWidget(picture)

        words = QVBoxLayout()
        words.setSpacing(1)
        head = QLabel(says[:150])
        head.setStyleSheet(
            f"color: {theme.INK}; font-size: 12px; font-weight: 600;")
        head.setWordWrap(False)
        said_where = QLabel(which)
        said_where.setStyleSheet(
            f"color: {theme.MUTED}; font-size: 10px; font-weight: 700;")
        words.addWidget(head)
        words.addWidget(said_where)
        line.addLayout(words, 1)

    def mousePressEvent(self, event):  # noqa: N802 - Qt name
        # The tick box is its own control: clicking it picks the clipping OUT,
        # it does not open it.
        if (event.button() == Qt.LeftButton
                and not self.tick.geometry().contains(event.position().toPoint())):
            self.picked.emit(self.row_id)
        super().mousePressEvent(event)


class FindBox(QFrame):
    """The translucent panel of results, floating over the page."""

    picked = Signal(int)
    #: (row ids, newspad number) - put copies of the ticked results there.
    shiftWanted = Signal(list, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FindBox")
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(
            # Translucent, as asked, but over a pale page - so the words on it
            # keep their contrast. Anything thinner and the thumbnails behind
            # it start reading as part of a result.
            "#FindBox { background: rgba(244, 246, 250, 0.96);"
            " border: 1px solid rgba(15, 23, 42, 0.14);"
            " border-radius: 14px; }")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 9, 10, 10)
        outer.setSpacing(7)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.said = QLabel()
        self.said.setStyleSheet(
            f"color: {theme.MUTED}; font-size: 11px; font-weight: 700;"
            " background: transparent; border: none;")
        head.addWidget(self.said, 1)

        self.all_btn = QPushButton("Select all")
        self.all_btn.setCursor(Qt.PointingHandCursor)
        self.all_btn.setToolTip("Tick every one of these results.")
        self.all_btn.clicked.connect(self._tick_all)
        head.addWidget(self.all_btn)

        # SHIFT TO, on the results themselves. Searching for the stories that
        # belong in a second newspad and then having to find them again in the
        # list to send them is the long way round; from here the ones that came
        # up ARE the selection.
        self.shift_btn = QPushButton("Shift to: ▾")
        self.shift_btn.setCursor(Qt.PointingHandCursor)
        self.shift_btn.setToolTip(
            "Put a copy of the ticked results into another newspad. They stay "
            "here as well.")
        self.shift_menu = QMenu(self)
        self.shift_menu.aboutToShow.connect(self._fill_shift)
        self.shift_btn.setMenu(self.shift_menu)
        head.addWidget(self.shift_btn)
        for button in (self.all_btn, self.shift_btn):
            button.setStyleSheet(
                f"QPushButton {{ background: {theme.SURFACE};"
                f" border: 1px solid {theme.HAIRLINE_STRONG};"
                f" border-radius: 9px; padding: 3px 10px; font-size: 11px;"
                f" font-weight: 700; color: {theme.NAVY}; }}"
                f"QPushButton:hover {{ border-color: {theme.NAVY}; }}"
                "QPushButton:disabled { color: #9AA6B8; }"
                "QPushButton::menu-indicator { image: none; width: 0; }")
        outer.addLayout(head)

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.NoFrame)
        self.area.setStyleSheet("background: transparent;")
        self.holder = QWidget()
        self.holder.setStyleSheet("background: transparent;")
        self.column = QVBoxLayout(self.holder)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(5)
        self.column.addStretch(1)
        self.area.setWidget(self.holder)
        outer.addWidget(self.area, 1)
        self.hide()

    #: Every result on show, in order.
    def results(self) -> list:
        return [self.column.itemAt(i).widget()
                for i in range(self.column.count())
                if isinstance(self.column.itemAt(i).widget(), Result)]

    def chosen(self) -> list:
        """The row ids that have been ticked."""
        return [r.row_id for r in self.results() if r.tick.isChecked()]

    def _tick_all(self) -> None:
        results = self.results()
        wanted = not all(r.tick.isChecked() for r in results) if results else False
        for result in results:
            result.tick.setChecked(wanted)

    def _count_changed(self) -> None:
        many = len(self.chosen())
        self.shift_btn.setEnabled(bool(many))
        self.all_btn.setText("Select all" if not self.results()
                             or not all(r.tick.isChecked()
                                        for r in self.results())
                             else "Select none")
        self.shift_btn.setText(
            f"Shift {many} to: ▾" if many else "Shift to: ▾")

    def _fill_shift(self) -> None:
        from ..core import newspads

        self.shift_menu.clear()
        here = newspads.active()
        for number in range(1, newspads.COUNT + 1):
            found = newspads.summary(number)
            words = newspads.describe(number, *(found or ()))
            if number == here:
                action = self.shift_menu.addAction(f"{words}   (this one)")
                action.setEnabled(False)
                continue
            action = self.shift_menu.addAction(words)
            action.triggered.connect(
                lambda _c=False, n=number: self.shiftWanted.emit(self.chosen(), n))

    def show_results(self, found: list, numbers) -> None:
        while self.column.count() > 1:
            item = self.column.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not found:
            self.said.setText("Nothing matches that.")
        else:
            self.said.setText(
                f"{len(found)} clipping{'s' if len(found) != 1 else ''}"
                + (f", showing the first {MOST_RESULTS}"
                   if len(found) >= MOST_RESULTS else ""))
        for row, which, says in found:
            result = Result(numbers(row.id), row, which, says, self.holder)
            result.picked.connect(self.picked.emit)
            result.ticked.connect(self._count_changed)
            self.column.insertWidget(self.column.count() - 1, result)
        self._count_changed()
        self.show()
        self.raise_()


#: What the operators do, for the "i". Written for somebody who has the box
#: in front of them and wants to do something cleverer than one word.
HELP = """
<p style="margin:0 0 10px 0">Type a word or two and it looks in the headline
that prints, the headline read off the picture, the newspaper, the edition and
the link. <b>Two letters are enough.</b> It only finds &mdash; nothing is
hidden, reordered, ticked or unticked.</p>

<p style="margin:0 0 4px 0"><b>Asking for more than one thing</b></p>
<table cellpadding="3" style="margin:0 0 10px 0">
<tr><td><code>hydrogen train</code></td>
    <td>&mdash; both words, in any order, anywhere on the clipping</td></tr>
<tr><td><code>hydrogen OR train</code></td>
    <td>&mdash; either one. <b>OR must be capitals</b>, so a headline with the
        word "or" in it is still just a word</td></tr>
<tr><td><code>"vande bharat"</code></td>
    <td>&mdash; those words, in that order, as written</td></tr>
<tr><td><code>hydrogen -cricket</code></td>
    <td>&mdash; has the first, does not have the second</td></tr>
</table>

<p style="margin:0 0 4px 0"><b>Asking one field only</b></p>
<table cellpadding="3" style="margin:0 0 10px 0">
<tr><td><code>paper:jagran</code></td><td>&mdash; the newspaper</td></tr>
<tr><td><code>headline:hydrogen</code></td><td>&mdash; the printed headline</td></tr>
<tr><td><code>read:kavach</code></td>
    <td>&mdash; only what was read off the picture</td></tr>
<tr><td><code>edition:delhi</code></td><td>&mdash; the edition or city</td></tr>
<tr><td><code>link:indianexpress</code></td><td>&mdash; the web address</td></tr>
</table>

<p style="margin:0 0 10px 0"><b>Putting them together.</b> Words next to each
other are joined by "and", and <code>OR</code> splits the whole query into
sides &mdash; so <code>vande bharat OR paper:jagran</code> finds the clippings
that say both those words, plus everything from that paper.</p>

<p style="margin:0"><b>A misread headline still turns up.</b> A reading taken
off a picture is never perfect, so anything four letters or longer is also
matched forgivingly &mdash; <code>hydrogen</code> finds
<code>hydr0gen</code>. A quoted phrase is not: that is asked for exactly.</p>
"""


class FindHelp(QDialog):
    """What the search box understands. Read-only."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Finding a clipping — what you can type")
        self.setModal(True)
        self.resize(580, 560)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(12)
        words = QLabel(HELP)
        words.setWordWrap(True)
        words.setTextFormat(Qt.RichText)
        words.setAlignment(Qt.AlignTop)
        words.setStyleSheet(
            f"color: {theme.INK}; font-size: 12px; background: transparent;"
            " border: none;")
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setWidget(words)
        area.setStyleSheet("background: transparent;")
        outer.addWidget(area, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        outer.addWidget(buttons)


class FindBar(QWidget):
    """The field itself, and the box of results under it."""

    #: A clipping was picked out of the results (a row id).
    picked = Signal(int)
    #: (row ids, newspad number) - copies of the ticked results, sent on.
    shiftWanted = Signal(list, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FindBar")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.field = QLineEdit()
        self.field.setPlaceholderText(
            "Find a clipping — hydrogen train, \"vande bharat\", a OR b, -cricket, paper:jagran")
        self.field.setClearButtonEnabled(True)
        self.field.setObjectName("FindField")
        self.field.setToolTip(
            "Searches the headline, the headline read off the picture, "
            "the newspaper and the link.\n\n"
            "hydrogen train \u2014 both words\n"
            "hydrogen OR train \u2014 either one\n"
            '"vande bharat" \u2014 those words in that order\n'
            "-cricket \u2014 leave those out\n"
            "paper:jagran \u2014 only in the newspaper "
            "(also read:, link:, headline:, edition:)\n\n"
            "Nothing is hidden or reordered: this only finds.")
        row.addWidget(self.field, 1)

        self.help_btn = QToolButton()
        self.help_btn.setText("i")
        self.help_btn.setFixedSize(26, 26)
        self.help_btn.setCursor(Qt.PointingHandCursor)
        self.help_btn.setToolTip(
            "What you can type here: and, OR, \"a phrase\", -leave out, "
            "paper: and the rest.")
        self.help_btn.setStyleSheet(
            f"QToolButton {{ background: {theme.SURFACE};"
            f" border: 1px solid {theme.HAIRLINE_STRONG}; border-radius: 13px;"
            f" color: {theme.MUTED}; font-size: 12px; font-weight: 800;"
            " font-style: italic; padding: 0; }"
            f"QToolButton:hover {{ border-color: {theme.NAVY};"
            f" color: {theme.NAVY}; }}")
        self.help_btn.clicked.connect(lambda: FindHelp(self).exec())
        row.addWidget(self.help_btn, 0)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(AFTER_TYPING_MS)
        self._timer.timeout.connect(self._look)
        self.field.textChanged.connect(self._typed)
        self.field.returnPressed.connect(self._look)

        # WHAT WAS LOOKED FOR LATELY, offered on a press in an empty field.
        # The same search is run over and over across a morning - one story
        # chased through four divisions' files - and typing it again each time
        # is what is being saved.
        #
        # A completer rather than a dropped-down menu, and driven by hand
        # rather than attached to the field: a menu takes the keyboard while
        # it is up, so a press followed straight away by typing - which is
        # what anybody does - would lose the first letters into the menu. A
        # completer's popup leaves the keys with the field. Driven by hand
        # because attached it would also pop up WHILE typing, over the results
        # panel, which is two floating things at once over the same spot.
        self._recent_list = QStringListModel([], self)
        self._recent = QCompleter(self._recent_list, self)
        self._recent.setWidget(self.field)
        self._recent.setCaseSensitivity(Qt.CaseInsensitive)
        self._recent.activated.connect(self._use_recent)
        offer = self._recent.popup()
        offer.setStyleSheet(
            f"QAbstractItemView {{ background: {theme.SURFACE};"
            f" border: 1px solid {theme.HAIRLINE_STRONG}; border-radius: 10px;"
            f" padding: {OFFER_PAD}px; outline: none; font-size: 12.5px;"
            f" color: {theme.NAVY}; }}"
            "QAbstractItemView::item { padding: 7px 9px; border-radius: 7px; }"
            f"QAbstractItemView::item:selected {{ background: #E8F0FE;"
            f" color: {theme.NAVY}; }}")
        offer.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.field.installEventFilter(self)
        #: Kept only while the query is worth keeping - see _look.
        self._remembered = ""

        self.box = None
        self._rows = lambda: []
        self._numbers = lambda _id: 0

    def serve(self, rows, numbers) -> None:
        """Where the clippings come from, and what each one is numbered."""
        self._rows = rows
        self._numbers = numbers

    def _ensure_box(self):
        if self.box is None:
            top = self.window()
            self.box = FindBox(top)
            self.box.picked.connect(self._chose)
            self.box.shiftWanted.connect(self.shiftWanted.emit)
            top.installEventFilter(self)
        return self.box

    def _chose(self, row_id: int) -> None:
        # THE BOX STAYS OPEN, and so does what was typed. Looking at one result
        # is almost never the end of it - the next thing is the next result -
        # and closing the box meant typing the words again every time.
        self.picked.emit(row_id)

    def close_box(self) -> None:
        if self.box is not None:
            self.box.hide()

    def _look(self) -> None:
        wanted = self.field.text().strip()
        if len(fold(wanted).replace(" ", "")) < LEAST_LETTERS:
            self.close_box()
            return
        found = search(self._rows(), wanted)
        box = self._ensure_box()
        box.show_results(found, self._numbers)
        self._place()
        # Remembered only when it found something. A search that matched
        # nothing is not worth offering back, and half a word typed on the way
        # to a whole one would otherwise fill the list.
        if found and wanted != self._remembered:
            self._remembered = wanted
            remember(wanted)

    def offer_recent(self) -> None:
        """What was looked for lately, under the field."""
        kept = recent()
        if not kept or self.field.text().strip():
            return
        self._recent_list.setStringList(kept)
        self._recent.setCompletionPrefix("")
        self._recent.complete()
        # SIZED HERE. A completer measures its popup from the rows alone and
        # knows nothing of the padding the stylesheet puts round them, so it
        # comes up a few pixels short and hangs a scrollbar beside four items.
        offer = self._recent.popup()
        row = offer.sizeHintForRow(0)
        if row > 0:
            offer.setFixedHeight(row * len(kept) + 2 * OFFER_PAD
                                 + 2 * offer.frameWidth())

    def hide_recent(self) -> None:
        popup = self._recent.popup()
        if popup is not None and popup.isVisible():
            popup.hide()

    def _typed(self, _text: str = "") -> None:
        # Typing puts the offer away: from the first letter the field is
        # searching, and the results belong under it.
        self.hide_recent()
        self._timer.start()

    def _use_recent(self, words: str) -> None:
        self.hide_recent()
        self.field.setText(words)
        self._look()

    def _forget_recent(self) -> None:
        self._recent_list.setStringList([])
        try:
            from .export_dialog import load_settings, save_settings

            save_settings({**load_settings(), RECENT_KEY: []})
        except Exception:  # noqa: BLE001
            pass

    def _place(self) -> None:
        """Against the field, as wide as it, and always inside the window.

        Under the field while there is room for it there, and above the field
        when there is not - which is what happens once the page has been
        scrolled far enough to carry the field towards the foot. Pinned at a
        floor and allowed to overflow, it hung off the bottom of the window
        with its last results out of reach.
        """
        if self.box is None or not self.box.isVisible():
            return
        top = self.window()
        width = max(320, self.field.width())
        wanted = 74 + 62 * max(1, self.box.column.count() - 1)

        below = self.field.mapTo(top, QPoint(0, self.field.height() + 6))
        room_below = top.height() - below.y() - 14
        # Always downwards. The field is pinned above the page now, so there
        # is always room under it - and it never moves, so the panel never has
        # to chase it or flip over it, which is what read as a glitch.
        tall = max(80, min(room_below, wanted))
        self.box.setGeometry(below.x(), below.y(), width, tall)
        self.box.raise_()

    def follow(self, scroller) -> None:
        """Keep the panel under the field while the page scrolls.

        The field scrolls away with the page it sits on; the panel is a child
        of the WINDOW, so it does not move on its own and was left behind. It
        follows now - and because the room it is given is measured from wherever
        the field has got to, it grows taller as the field goes up the screen,
        which is exactly when more of it can be seen.
        """
        for bar in (scroller.verticalScrollBar(), scroller.horizontalScrollBar()):
            if bar is not None:
                bar.valueChanged.connect(lambda _v: self._place())

    def moveEvent(self, event):  # noqa: N802 - Qt name
        self._place()
        super().moveEvent(event)

    def resizeEvent(self, event):  # noqa: N802 - Qt name
        self._place()
        super().resizeEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.window() and event.type() in (
                QEvent.Resize, QEvent.Move):
            self._place()
        # Pressed while empty: offer what was searched for lately. Only on a
        # press, and only while empty, so it never gets in the way of typing.
        if (watched is self.field
                and event.type() == QEvent.MouseButtonPress
                and not self.field.text().strip()):
            QTimer.singleShot(0, self.offer_recent)
        # And a way to clear them, on the field's own right-click menu, where
        # the rest of what can be done to the field already is.
        if watched is self.field and event.type() == QEvent.ContextMenu:
            menu = self.field.createStandardContextMenu()
            menu.addSeparator()
            forget = menu.addAction("Forget recent searches")
            forget.setEnabled(bool(recent()))
            forget.triggered.connect(self._forget_recent)
            menu.exec(event.globalPos())
            menu.deleteLater()
            return True
        return super().eventFilter(watched, event)
