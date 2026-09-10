"""Which of the two interfaces is showing, as a switch rather than a list.

It used to be a drop-down. A drop-down is the wrong control for this and it was
wrong in the way that matters most: it hides the choice. The header read

    INTERFACE   [ Standard Press Report Interface  (30 clips)  v ]

and there is nothing there to say that a second interface exists at all, let
alone what it is called or what is in it. Somebody who had never been shown the
sentiment board had no reason to click. And having clicked, they were reading a
list of two - one of them the thing already on screen - which is a menu doing the
work of a switch.

So both interfaces are on the header now, side by side, with the one in use
filled in and the other one plainly there to be pressed. The count sits on each,
so the board says how many clippings it is holding without being opened. Nothing
has to be clicked to find out what the application can do.

Kept narrow on purpose: the header wraps its controls on a small screen, and this
is the widest thing on it.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from . import icons, theme

# The two interfaces, in the order they are offered: what each is called, the
# mark that goes on it, and the word used when there is no room for the name.
INTERFACES = (
    ("standard", "Press Report", "Report", "paperclip"),
    ("sentiment", "Sentiment Board", "Sentiment", "layers"),
)


def _mark(name: str, colour: str, size: int = 14) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    drawer = getattr(icons, name, None)
    if drawer is not None:
        drawer(painter, QRectF(0, 0, size, size), QColor(colour))
    painter.end()
    return QIcon(pixmap)


class ModeSwitch(QWidget):
    """Two interfaces, both on screen, one of them in use."""

    #: The interface somebody has just asked for: "standard" or "sentiment".
    changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ModeSwitch")
        # Darker than the crown it sits on, not lighter. On the crown's own
        # tone the container disappeared and the two halves read as a label
        # beside a button rather than as one control with two positions - which
        # is the whole thing this replaced a drop-down to fix.
        self.setStyleSheet(
            f"#ModeSwitch {{ background: {theme.CROWN_WELL};"
            f" border: 1px solid {theme.SLATE_LINE}; border-radius: 12px; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(3)

        self._mode = "standard"
        self._counts = {"standard": 0, "sentiment": 0}
        self._buttons: dict = {}
        self._names: dict = {}
        for value, name, short, mark in INTERFACES:
            button = QPushButton(name)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setIcon(_mark(mark, theme.CROWN_SUB))
            button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            button.clicked.connect(
                lambda _checked=False, which=value: self._pressed(which))
            row.addWidget(button)
            self._buttons[value] = button
            self._names[value] = (name, short, mark)
        self._repaint()

    # ------------------------------------------------------------- the state
    def mode(self) -> str:
        return self._mode

    def set_mode(self, value: str, announce: bool = False) -> None:
        """Show this interface as the one in use. Silent unless asked."""
        value = value if value in self._buttons else "standard"
        changed = value != self._mode
        self._mode = value
        self._repaint()
        if changed and announce:
            self.changed.emit(value)

    def set_counts(self, standard: int, sentiment: int) -> None:
        """How many clippings each interface is holding, shown on the switch.

        Two numbers, not one. They are different piles: a clipping dragged onto
        the board is not in the press report, and labelling both with one total
        told somebody the board held thirty when it held none.
        """
        wanted = {"standard": int(standard), "sentiment": int(sentiment)}
        if wanted != self._counts:
            self._counts = wanted
            self._repaint()

    def _pressed(self, value: str) -> None:
        if value == self._mode:
            # Pressing the one already in use is not a change; put its checked
            # state back so it cannot be left looking switched off.
            self._repaint()
            return
        self.set_mode(value, announce=True)

    # -------------------------------------------------------------- painting
    def _repaint(self) -> None:
        for value, button in self._buttons.items():
            name, _short, mark = self._names[value]
            here = value == self._mode
            count = self._counts.get(value, 0)
            button.setText(f"{name}  {count}" if count else name)
            button.setChecked(here)
            button.setIcon(_mark(mark, theme.NAVY if here else theme.CROWN_SUB))
            button.setToolTip(
                f"{name} — {count} clipping{'s' if count != 1 else ''}"
                if count else f"{name} — nothing in it yet")
            # Styled per button rather than through one sheet with a :checked
            # rule, because the mark has to be repainted in the other colour
            # anyway and the two have to agree.
            if here:
                button.setStyleSheet(
                    f"QPushButton {{ background: {theme.SURFACE};"
                    f" color: {theme.NAVY}; border: none; border-radius: 9px;"
                    " padding: 5px 13px; font-size: 11px; font-weight: 800;"
                    " text-align: left; }"
                )
            else:
                button.setStyleSheet(
                    f"QPushButton {{ background: {theme.CROWN_RAISED};"
                    f" color: {theme.CROWN_SUB};"
                    f" border: 1px solid {theme.SLATE_LINE};"
                    " border-radius: 9px; padding: 5px 13px; font-size: 11px;"
                    " font-weight: 700; text-align: left; }"
                    f"QPushButton:hover {{ background: {theme.CROWN_HOVER};"
                    f" color: white; border-color: {theme.CROWN_AMBER}; }}"
                )

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt name
        hint = super().sizeHint()
        return QSize(hint.width(), max(hint.height(), 34))


class ZoomButtons(QWidget):
    """Smaller, the size it is now, bigger - as one control.

    They were three separate header buttons carrying the characters "\u2212" and
    "+". At the width a header button gets, the minus was clipped to a dot and
    the plus to a tick: two controls that said nothing about what they did. The
    signs are painted now, inside a magnifier, which is what everything else
    that zooms looks like.
    """

    #: -1 for smaller, +1 for bigger.
    stepped = Signal(int)
    #: The percentage in the middle was pressed: back to the normal size.
    reset = Signal()
    #: A size was chosen from the list outright. Getting to a size used to mean
    #: stepping to it, and every step is a restart - three of them to go from
    #: 100% to 70%. Choosing is one.
    picked = Signal(float)

    def __init__(self, percent: str = "100%", parent=None):
        super().__init__(parent)
        self.setObjectName("ZoomButtons")
        self.setStyleSheet(
            f"#ZoomButtons {{ background: {theme.CROWN_WELL};"
            f" border: 1px solid {theme.SLATE_LINE}; border-radius: 12px; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(3)

        self.smaller = self._button("zoom_out", "Make everything smaller, so "
                                    "more fits on a small screen", "-")
        self.smaller.clicked.connect(lambda: self.stepped.emit(-1))
        row.addWidget(self.smaller)

        self.percent = QPushButton(percent)
        self.percent.setCursor(Qt.PointingHandCursor)
        self.percent.setToolTip(
            "Choose a size.\n\nThe application restarts once to change it - "
            "your clippings are saved first and come straight back.")
        self.percent.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {theme.CROWN_SUB};"
            " border: none; border-radius: 9px; padding: 5px 8px;"
            " font-size: 11px; font-weight: 800; }"
            f"QPushButton:hover {{ color: white; }}"
        )
        self.percent.clicked.connect(self._offer_sizes)
        row.addWidget(self.percent)

        self.bigger = self._button("zoom_in", "Make everything bigger", "+")
        self.bigger.clicked.connect(lambda: self.stepped.emit(1))
        row.addWidget(self.bigger)

    def _button(self, _name: str, tip: str, sign: str) -> QPushButton:
        button = QPushButton()
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(tip)
        button.setFixedWidth(30)
        pixmap = QPixmap(15, 15)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        icons.zoom(painter, QRectF(0, 0, 15, 15), QColor(theme.CROWN_SUB), sign)
        painter.end()
        button.setIcon(QIcon(pixmap))
        button.setStyleSheet(
            f"QPushButton {{ background: {theme.CROWN_RAISED};"
            f" border: 1px solid {theme.SLATE_LINE}; border-radius: 9px;"
            " padding: 5px 4px; }"
            f"QPushButton:hover {{ background: {theme.CROWN_HOVER};"
            f" border-color: {theme.CROWN_AMBER}; }}"
        )
        return button

    def _offer_sizes(self) -> None:
        """Every size, so any of them is one press and one restart."""
        from PySide6.QtWidgets import QMenu

        from . import zoom

        here = zoom.level()
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        for size in zoom.LEVELS:
            said = zoom.as_percent(size)
            if abs(size - zoom.NORMAL) < 0.001:
                said += "   (normal)"
            if abs(size - here) < 0.001:
                said += "   \u2713"
            action = menu.addAction(said)
            action.setEnabled(abs(size - here) >= 0.001)
            action.triggered.connect(
                lambda _checked=False, value=size: self.picked.emit(value))
        menu.exec(self.percent.mapToGlobal(
            self.percent.rect().bottomLeft()))

    def set_percent(self, text: str) -> None:
        self.percent.setText(text)
