"""Two pieces that let the interface get narrow without losing anything.

A window that cannot shrink is not a cosmetic problem. When the content demands
more width than the window allows, Qt does not scroll to it and does not hide it -
it simply cuts it off at the edge, and a button that is cut off cannot be clicked.
That is how the Collapse button and the Black colour swatch became unreachable on
a 1366x768 office laptop.

Two things cause it, and there is one piece here for each.

**Long labels.** A QLabel with word wrap off reports a minimum width equal to its
entire text. One sentence of guidance therefore sets a floor under the whole window:
the three hints across the top of the header were holding it at 985px between them.
``ElidedLabel`` keeps the sentence when there is room and trims it with an ellipsis
when there is not, so guidance costs nothing.

**Rows of controls.** A QHBoxLayout of buttons cannot do anything when it runs out of
room; it just overflows. ``FlowLayout`` moves what does not fit onto the next line,
which is what a person expects a toolbar to do, and every button stays clickable.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLayout,
    QSizePolicy,
    QWidgetItem,
)


class ElidedLabel(QLabel):
    """A label that gives way instead of forcing the window open.

    It keeps the full text for tooltips and for measuring, paints as much of it as
    fits, and reports a minimum width of ``floor`` pixels rather than the width of
    the whole sentence. Set ``floor`` to something that still reads: a label that
    can shrink to nothing shrinks to nothing.
    """

    def __init__(self, text: str = "", parent=None, *, floor: int = 60,
                 mode: Qt.TextElideMode = Qt.ElideRight):
        super().__init__(text, parent)
        self._full = text
        self._floor = floor
        self._mode = mode
        # Preferred, not Ignored: Qt hands out sizeHint when there is room and
        # only shrinks towards minimumSizeHint when there is not, so a sentence
        # with space around it is never trimmed for no reason.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        if text:
            self.setToolTip(text)

    # -- text -------------------------------------------------------------
    def setText(self, text: str) -> None:  # noqa: N802 - Qt name
        self._full = text
        self.setToolTip(text)
        super().setText(text)
        self._retrim()

    def full_text(self) -> str:
        """What it would say with room, whatever is currently painted."""
        return self._full

    # -- sizing -----------------------------------------------------------
    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt name
        hint = super().minimumSizeHint()
        return QSize(min(self._floor, hint.width()), hint.height())

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt name
        metrics = QFontMetrics(self.font())
        return QSize(metrics.horizontalAdvance(self._full) + 2,
                     super().sizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt name
        super().resizeEvent(event)
        self._retrim()

    def _retrim(self) -> None:
        metrics = QFontMetrics(self.font())
        room = max(0, self.width() - 2)
        shown = metrics.elidedText(self._full, self._mode, room) if room else ""
        if shown != super().text():
            # Qt's own setText, so this does not recurse through ours.
            QLabel.setText(self, shown)


class FlowLayout(QLayout):
    """A row of widgets that wraps onto the next line when it runs out of room.

    The standard Qt flow layout, kept deliberately plain. Two details matter here:
    ``hasHeightForWidth`` is what tells a parent layout that this one gets taller
    as it gets narrower, and ``minimumSize`` is the widest single item rather than
    the sum - that is the whole point, since the sum is what pins a window open.
    """

    def __init__(self, parent=None, margin: int = 0, spacing: int = 8,
                 vertical_spacing: int | None = None,
                 alignment: Qt.Alignment = Qt.AlignLeft):
        super().__init__(parent)
        self._items: list[QWidgetItem] = []
        self._spacing = spacing
        self._vspacing = spacing if vertical_spacing is None else vertical_spacing
        self._align = alignment
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        while self._items:
            self._items.pop()

    # -- QLayout plumbing --------------------------------------------------
    def addItem(self, item) -> None:  # noqa: N802 - Qt name
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802 - Qt name
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):  # noqa: N802 - Qt name
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802 - Qt name
        return Qt.Orientations(Qt.Orientation(0))

    # -- the wrapping itself ----------------------------------------------
    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt name
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt name
        return self._lay(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt name
        super().setGeometry(rect)
        self._lay(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt name
        left, top, right, bottom = self.getContentsMargins()
        width = height = 0
        for item in self._items:
            hint = item.sizeHint()
            width += hint.width() + self._spacing
            height = max(height, hint.height())
        return QSize(max(0, width - self._spacing) + left + right,
                     height + top + bottom)

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt name
        # The widest single item, never the sum: the sum is what stops a window
        # closing, and every item can sit on a line of its own if it has to.
        left, top, right, bottom = self.getContentsMargins()
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return QSize(size.width() + left + right, size.height() + top + bottom)

    def _lay(self, rect: QRect, *, apply: bool) -> int:
        """Place the items, or just work out how tall they would be.

        Two passes per line rather than one: a line has to be complete before it
        can be centred, because centring needs the total width of everything on
        it. Laying out as it goes would left-align, which is what happened to the
        three import buttons when this layout replaced their stretch-padded row.
        """
        left, top, right, bottom = self.getContentsMargins()
        area = rect.adjusted(left, top, -right, -bottom)
        y, lines, line, line_width, line_height = area.y(), [], [], 0, 0

        for item in self._items:
            widget = item.widget()
            if widget is not None and widget.isHidden():
                continue
            hint = item.sizeHint()
            wanted = line_width + (self._spacing if line else 0) + hint.width()
            if line and wanted > area.width():
                lines.append((line, line_width, line_height))
                line, line_width, line_height = [], 0, 0
                wanted = hint.width()
            line.append((item, hint))
            line_width = wanted
            line_height = max(line_height, hint.height())
        if line:
            lines.append((line, line_width, line_height))

        for row, width, height in lines:
            x = area.x()
            if self._align & Qt.AlignHCenter:
                x += max(0, (area.width() - width) // 2)
            elif self._align & Qt.AlignRight:
                x += max(0, area.width() - width)
            for item, hint in row:
                if apply:
                    item.setGeometry(QRect(QPoint(x, y), hint))
                x += hint.width() + self._spacing
            y += height + self._vspacing

        if lines:
            y -= self._vspacing
        return y - rect.y() + bottom


class ShrinkingCombo(QComboBox):
    """A dropdown that asks for its longest entry but settles for less.

    A QComboBox sized to its contents reports a *minimum* as wide as its longest
    entry, so one long option name - "Standard Press Report Interface" - put a
    300px floor under the header. Setting a smaller minimumWidth cannot help:
    an explicit minimum only ever raises the floor Qt computes, never lowers it.
    So the hint itself has to give. The full width is still what it asks for when
    there is room; the text elides on its own once there is not.
    """

    def __init__(self, parent=None, *, floor: int = 140):
        super().__init__(parent)
        self._floor = floor
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt name
        hint = super().minimumSizeHint()
        return QSize(min(self._floor, hint.width()), hint.height())
