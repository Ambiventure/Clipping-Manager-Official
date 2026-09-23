"""The strip that decides what the clipping list shows, and in what order.

Two separate controls, kept apart on purpose. **Show** narrows: pick Regional,
then pick Hindi or English on top of it, and each choice can only take away from
what the one before it left. **Arrange** reorders what survived, and does
nothing else - so somebody can sort the whole morning by size without hiding a
single clipping, or hide everything but the English papers and leave them in the
order they put them in. One drop-down doing both would have made those two
things the same gesture, and they are not.

**Arranging is two questions, not one.** "By language" on its own put Hindi
first, because that is the order the axis happens to be written in, and there
was nowhere to say otherwise: somebody who wanted the English papers on top
found them at the bottom with nothing on screen to explain why. So choosing what
to arrange by opens a second row asking which comes first - click English, then
Punjabi, and that is the order; everything not clicked follows as it would have.

**And a filter is a lens, never an edit.** What is hidden is still in the
report. That sentence is on the strip itself, because the alternative - somebody
filtering to the regional papers, exporting, and finding the national ones gone
- is a mistake that is only discovered after the file has been sent.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
                               QLabel, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

from ..core import arrange
from . import theme
from .fluid import ElidedLabel, FlowLayout

#: The axes offered for filtering, in the order they are offered. Newspaper
#: last: it is the longest list and the most specific question, so it belongs
#: after the ones that describe a KIND of paper.
AXES = ["reach", "language", "stature", "medium", arrange.BY_NAME]

#: What each axis is called on the strip when it has no label of its own.
NAMES = {arrange.BY_NAME: "Newspaper"}

#: WHAT THE TWO HALVES DO, for the "i". Written for somebody who has the strip
#: in front of them and cannot tell which half does what - which is a fair
#: question, because the two halves look the same and do opposite things.
HELP = """
<p style="margin:0 0 10px 0"><b>Two controls that do different things.</b>
<b>Show</b> decides which clippings you can see. <b>Arrange</b> decides what
order they are in. Neither one changes the report.</p>

<p style="margin:0 0 4px 0"><b>Show — narrowing down</b></p>
<ul style="margin:0 0 10px 0">
<li>Each row is one question: Reach, Language, Size, Medium, Newspaper.</li>
<li>Click a chip to keep only those. Click it again to let them go.</li>
<li>Rows <b>stack</b>. Pick <i>Regional</i> on Reach and then <i>Hindi</i> on
Language and you are left with the clippings that are <b>both</b> — not the
regional ones plus the Hindi ones.</li>
<li>Picking two chips in the <b>same</b> row is "either of these": Hindi
<b>or</b> English.</li>
<li>A row with nothing clicked is not asking anything, so it hides nothing.</li>
</ul>

<p style="margin:0 0 4px 0"><b>Arrange — putting them in order</b></p>
<ul style="margin:0 0 10px 0">
<li>Pick one. <i>As I arranged them</i> leaves your own order exactly alone.</li>
<li>Most choices then ask <b>which comes first</b> in a second row. Click
English, then Punjabi, and that is the order they go in; anything you do not
click follows behind in its usual order.</li>
<li>Arranging never hides anything, and hiding never reorders anything.</li>
</ul>

<p style="margin:0 0 4px 0"><b>What it does not do</b></p>
<ul style="margin:0 0 10px 0">
<li><b>The report is not affected.</b> A clipping you have hidden is still
exported, still numbered, and still on its page. This is a way of looking at
the morning, not a way of editing it.</li>
<li>Nothing here deletes or unticks a clipping. To leave one out of the report,
untick it in the list.</li>
<li><b>Show all again</b> puts everything back and returns to your own order.</li>
</ul>

<p style="margin:0"><b>Which papers are which</b> is where you say what counts
as regional, which are Hindi, which are the big ones. Those are what the chips
above are made from, and your own edits are kept when the program is
updated.</p>
"""


class FilterHelp(QDialog):
    """What Show and Arrange each do. Read-only; nothing here changes a thing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Show and Arrange — how they work")
        self.setModal(True)
        self.resize(560, 560)
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
        # Scrolled rather than stretched: the window opens over the strip and
        # must not grow taller than a laptop screen.
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

_PLAIN = (
    f"QPushButton {{ background: {theme.SURFACE}; color: {theme.NAVY};"
    f" border: 1px solid {theme.HAIRLINE_STRONG};"
    " border-radius: 11px; padding: 4px 12px;"
    " font-size: 11px; font-weight: 700; }"
    f"QPushButton:hover {{ background: {theme.NAVY_WASH};"
    f" border-color: {theme.NAVY}; }}"
    f"QPushButton:disabled {{ color: {theme.MUTED};"
    f" border-color: {theme.HAIRLINE}; }}"
)
_LIT = (
    f"QPushButton {{ background: {theme.NAVY}; color: #FFFFFF;"
    f" border: 1px solid {theme.NAVY};"
    " border-radius: 11px; padding: 4px 12px;"
    " font-size: 11px; font-weight: 800; }"
)


def _chip(text: str, tip: str = "") -> QPushButton:
    """A button in the same clothes as the ones already on the select bar."""
    button = QPushButton(text)
    button.setCursor(Qt.PointingHandCursor)
    if tip:
        button.setToolTip(tip)
    button.setStyleSheet(_PLAIN)
    return button


def _paint(button: QPushButton, on: bool) -> None:
    # Painted per button rather than through one sheet with a :checked rule,
    # the way the interface switch does it, so a chip cannot end up looking
    # picked while the list says it is not.
    button.setChecked(on)
    sheet = _LIT if on else _PLAIN
    # Only when it changes: a sheet set again is parsed and laid out again,
    # and the strip is repainted after every step while it is open.
    if button.styleSheet() != sheet:
        button.setStyleSheet(sheet)


def _lead(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {theme.ORANGE_INK}; font-size: 11px; font-weight: 900;"
        " letter-spacing: .06em; background: transparent; border: none;")
    return label


def _empty(flow: FlowLayout) -> None:
    while flow.count():
        item = flow.takeAt(0)
        gone = item.widget() if item is not None else None
        if gone is not None:
            gone.setParent(None)
            gone.deleteLater()


class ChipRow(QWidget):
    """A lead word and a row of chips that wraps. The base for all three rows.

    Chips rather than a list or a drop-down, for two reasons that are both
    about this application rather than about taste. A list view inside the page
    would take the mouse wheel, and on a page that is one long scroll that means
    the page stops moving and a setting changes that nobody meant to touch. And
    the count beside each value is the useful half - being able to see there
    are four English clippings before picking English is what stops the filter
    feeling like a guess.
    """

    changed = Signal()

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        self.lead = _lead(label.upper())
        self.lead.setMinimumWidth(64)
        box.addWidget(self.lead, 0, Qt.AlignTop)
        self.flow = FlowLayout(spacing=5, vertical_spacing=4)
        box.addLayout(self.flow, 1)
        self._buttons: dict = {}


class PickList(ChipRow):
    """One filter axis: any number of its values may be on at once."""

    def __init__(self, axis: str, label: str, parent=None):
        super().__init__(label, parent)
        self.axis = axis
        self.chosen: list = []
        self._offered = None

    def offer(self, choices: list) -> None:
        """Rebuild the chips for the values this morning actually contains.

        Not when they are the chips already there. The strip is offered again
        after every step while it is open - a headline typed, a rotate, a
        Ctrl+Z - and nearly none of those changes a paper or a count. Rebuilt
        anyway, every chip was deleted and made again and the row laid out
        from nothing: Enter in a headline box took 130-200ms instead of 15.
        What is picked cannot be stale when nothing on offer changed, since a
        pick is only ever made from a chip that was offered."""
        choices = list(choices)
        if choices == self._offered:
            return
        self._offered = choices
        _empty(self.flow)
        self._buttons = {}
        # Anything picked that is no longer on offer is dropped, or the filter
        # would go on hiding everything with nothing on screen to say why.
        offered = {name for name, _count in choices}
        self.chosen = [c for c in self.chosen if c in offered]
        for name, count in choices:
            button = _chip(f"{name} · {count}",
                           f"Show only the {count} clipping(s) under {name}. "
                           "Pick more than one to show either.")
            button.setCheckable(True)
            _paint(button, name in self.chosen)
            button.clicked.connect(
                lambda _checked=False, value=name: self._picked(value))
            self.flow.addWidget(button)
            self._buttons[name] = button
        self.setVisible(bool(choices))

    def _picked(self, value: str) -> None:
        if value in self.chosen:
            self.chosen.remove(value)
        else:
            self.chosen.append(value)
        for name, button in self._buttons.items():
            _paint(button, name in self.chosen)
        self.changed.emit()

    def clear(self) -> None:
        self.chosen = []
        for button in self._buttons.values():
            _paint(button, False)


class OneOf(ChipRow):
    """A row where exactly one chip is on: what to arrange by."""

    def __init__(self, label: str, options: list, parent=None):
        super().__init__(label, parent)
        self.key = ""
        for key, text in options:
            tip = ("Leave the clippings exactly as you arranged them."
                   if not key else
                   "Group the clippings by this. You then choose which "
                   "comes first." if key in arrange.ASKS_WHICH_FIRST else
                   "The biggest publications at the top, then by reach.")
            button = _chip(text, tip)
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked=False, value=key: self.choose(value))
            self.flow.addWidget(button)
            self._buttons[key] = button
        self._show()

    def choose(self, key: str, quietly: bool = False) -> None:
        self.key = key if key in self._buttons else ""
        self._show()
        if not quietly:
            self.changed.emit()

    def _show(self) -> None:
        for key, button in self._buttons.items():
            _paint(button, key == self.key)


class RankList(ChipRow):
    """Which comes first: click the values in the order wanted.

    A chip shows its place once it has one - "1 · English · 4" - so the order
    is readable at a glance and not only from the list underneath. Clicking a
    ranked chip takes it out again; whatever is not ranked follows in the
    axis's own order.
    """

    def __init__(self, parent=None):
        super().__init__("First", parent)
        self.ranked: list = []
        self._counts: dict = {}
        self._offered = None

    def offer(self, choices: list) -> None:
        # Rebuilt only when the values or their counts changed, as the pick
        # rows are. The chips are still repainted: a new arrangement empties
        # the ranking before offering, and the same values offered again
        # would otherwise go on showing the old places.
        choices = list(choices)
        if choices == self._offered:
            self._show()
            return
        self._offered = choices
        _empty(self.flow)
        self._buttons = {}
        self._counts = dict(choices)
        offered = set(self._counts)
        self.ranked = [r for r in self.ranked if r in offered]
        for name, _count in choices:
            button = _chip("", "Put these at the top. Click several in the "
                               "order you want them.")
            button.setCheckable(True)
            button.clicked.connect(
                lambda _checked=False, value=name: self._ranked(value))
            self.flow.addWidget(button)
            self._buttons[name] = button
        self._show()
        self.setVisible(bool(choices))

    def _ranked(self, value: str) -> None:
        if value in self.ranked:
            self.ranked.remove(value)
        else:
            self.ranked.append(value)
        self._show()
        self.changed.emit()

    def _show(self) -> None:
        for name, button in self._buttons.items():
            count = self._counts.get(name, 0)
            if name in self.ranked:
                place = self.ranked.index(name) + 1
                button.setText(f"{place} · {name} · {count}")
                _paint(button, True)
            else:
                button.setText(f"{name} · {count}")
                _paint(button, False)

    def clear(self) -> None:
        self.ranked = []
        self._show()


class FilterBar(QFrame):
    """Show and Arrange, and the one button that puts everything back."""

    changed = Signal()
    editCategories = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FilterBar")
        self.setStyleSheet(
            f"#FilterBar {{ background: {theme.ORANGE_WASH};"
            f" border: 2px solid {theme.ORANGE_DEEP}; border-radius: 14px; }}"
            "#FilterBar QLabel { background: transparent; border: none; }"
            f"#FilterBar QFrame#Rule {{ background: {theme.ORANGE_DEEP};"
            " border: none; max-height: 1px; min-height: 1px; }")
        self._book = None
        self._clips: list = []
        self._quiet = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(7)

        # ------------------------------------------------------------ show
        self.picks: dict = {}
        for axis in AXES:
            widget = PickList(axis, NAMES.get(axis, axis.title()))
            widget.changed.connect(self._stirred)
            self.picks[axis] = widget
            outer.addWidget(widget)

        rule = QFrame()
        rule.setObjectName("Rule")
        rule.setFrameShape(QFrame.NoFrame)
        outer.addWidget(rule)

        # --------------------------------------------------------- arrange
        self.order_row = OneOf("Arrange", arrange.ARRANGEMENTS)
        self.order_row.changed.connect(self._order_changed)
        outer.addWidget(self.order_row)

        self.first_row = RankList()
        self.first_row.changed.connect(self._stirred)
        self.first_row.hide()
        outer.addWidget(self.first_row)

        # ------------------------------------------------------- the foot
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(8)
        self.said = ElidedLabel("Filtering changes what you see, never what is "
                                "exported.", floor=110)
        self.said.setStyleSheet(
            f"color: {theme.SLATE_TEXT_LIGHT}; font-size: 11px;"
            " background: transparent; border: none;")
        bottom.addWidget(self.said, 1)

        tail = FlowLayout(spacing=8, vertical_spacing=5)
        self.help_btn = _chip("i  How this works",
                              "What Show does, what Arrange does, and why "
                              "neither of them changes the report.")
        self.help_btn.clicked.connect(self._explain)
        tail.addWidget(self.help_btn)
        self.edit_btn = _chip("Which papers are which",
                              "Say which papers count as regional, which are "
                              "Hindi, which are the big ones. Yours are kept "
                              "when the program is updated.")
        self.edit_btn.clicked.connect(self.editCategories.emit)
        tail.addWidget(self.edit_btn)
        self.clear_btn = _chip("Show all again",
                               "Put every clipping back, in the order they "
                               "were in before any of this was touched.")
        self.clear_btn.clicked.connect(self.clear)
        tail.addWidget(self.clear_btn)
        bottom.addLayout(tail)
        outer.addLayout(bottom)

    def _explain(self) -> None:
        FilterHelp(self).exec()

    # ------------------------------------------------------------- the lens
    def lens(self) -> arrange.Lens:
        made = arrange.Lens()
        for axis, widget in self.picks.items():
            made.pick(axis, widget.chosen)
        made.order = self.order_row.key
        if made.order in arrange.ASKS_WHICH_FIRST:
            made.first = list(self.first_row.ranked)
        return made

    def offer(self, clips: list, book) -> None:
        """Rebuild the chips from the clippings actually in the list."""
        self._book = book
        self._clips = list(clips)
        self._quiet = True
        try:
            for axis, widget in self.picks.items():
                found = book.axes.get(axis)
                widget.lead.setText(
                    (found.label if found is not None
                     else NAMES.get(axis, axis.title())).upper())
                widget.offer(arrange.choices(clips, axis, book))
            self._offer_first()
        finally:
            self._quiet = False

    def _offer_first(self) -> None:
        """The second question, for the arrangements that ask it."""
        key = self.order_row.key
        if key in arrange.ASKS_WHICH_FIRST and self._book is not None:
            self.first_row.offer(arrange.choices(self._clips, key, self._book))
            self.first_row.show()
        else:
            self.first_row.clear()
            self.first_row.hide()

    def _order_changed(self) -> None:
        # A new axis means a new set of values to rank; the old ranking would
        # be nonsense against it.
        self.first_row.ranked = []
        self._offer_first()
        self._stirred()

    def say(self, shown: int, total: int) -> None:
        lens = self.lens()
        if not lens.busy:
            self.said.setText("Filtering changes what you see, never what is "
                              "exported.")
        else:
            words = arrange.describe(lens, self._book) if self._book else ""
            self.said.setText(
                f"Showing {shown} of {total}. {words}. What is hidden is still "
                "in the report." if lens.filtering
                else f"{words}. This changes what you see, not the report.")
        self.clear_btn.setEnabled(lens.busy)

    def clear(self) -> None:
        self._quiet = True
        try:
            for widget in self.picks.values():
                widget.clear()
            self.order_row.choose("", quietly=True)
            self.first_row.ranked = []
            self._offer_first()
        finally:
            self._quiet = False
        self.changed.emit()

    def _stirred(self) -> None:
        if not self._quiet:
            self.changed.emit()
