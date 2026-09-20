"""Print order: which categories the dossier prints, and in what order.

Opened from Print order… on the Heading & Document Layout card of the
sentiment page. The dossier used to read Positive, Neutral, Negative, Digital,
in that order and no other, and a category with nothing in it simply was not
there - a reader could not tell "no negative coverage today" from "nobody
looked".

Each category is a row that can be dragged above or below the others, with a
switch in front of it:

*   on - the category is printed. With no clippings in it, it prints its
    heading and the words "Nil - no clips", which is the department's own way
    of reporting a category with nothing in it.
*   off - the category is left out of the dossier altogether, empty or not.

The order and the switches are kept with the rest of that newspad's dossier
layout (ui/layout_card.py), so each newspad has its own and they survive
closing the program; the exporter reads them through
core/sentiment.printing_plan.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout)

from ..core import sentiment
from . import theme

VALUE_ROLE = Qt.UserRole


def _swatch(colour: str) -> QPixmap:
    """The category's own colour, so a row is known at a glance."""
    pixmap = QPixmap(14, 14)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(colour))
    painter.drawRoundedRect(1, 1, 12, 12, 3, 3)
    painter.end()
    return pixmap


def label_for(column) -> str:
    style = theme.SENTIMENT_STYLES.get(column.value, {})
    return str(style.get("label") or column.value)


def colour_for(column) -> str:
    style = theme.SENTIMENT_STYLES.get(column.value, {})
    return str(style.get("colour") or theme.NAVY)


class PrintOrderDialog(QDialog):
    """The categories, in the order they print, each with its switch."""

    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Print order")
        self.setModal(True)
        self.setMinimumWidth(430)
        # Tall enough for every category at once: a list somebody has to drag
        # rows around in must not open with the last one half off the bottom.
        self.resize(460, 540)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(10)
        title = QLabel("The order the dossier prints in")
        title.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {theme.NAVY};")
        outer.addWidget(title)
        lead = QLabel(
            "Drag a category up or down to change where it prints. Switched on, "
            "it is printed even when it holds nothing - it says “Nil - no "
            "clips”. Switched off, it is left out of the dossier altogether, "
            "and so is anything filed under it.")
        lead.setWordWrap(True)
        lead.setStyleSheet(f"color: {theme.MUTED};")
        outer.addWidget(lead)

        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setAlternatingRowColors(True)
        self.list.setIconSize(QSize(14, 14))
        # The row being moved has to stay readable: the default highlight
        # writes white on a pale background here.
        self.list.setStyleSheet(
            "QListWidget::item { padding: 7px 4px; }"
            f"QListWidget::item:selected {{ background: {theme.NAVY_SELECT};"
            f" color: {theme.INK}; }}")
        self.list.setMinimumHeight(len(sentiment.COLUMNS) * 38 + 12)
        self.fill(plan)
        outer.addWidget(self.list, 1)

        # Dragging is the quick way; the buttons are the sure way, and they are
        # how somebody working from the keyboard moves a category at all.
        moves = QHBoxLayout()
        self.up_btn = QPushButton("Move up")
        self.up_btn.clicked.connect(lambda: self.move_row(-1))
        self.down_btn = QPushButton("Move down")
        self.down_btn.clicked.connect(lambda: self.move_row(1))
        self.original_btn = QPushButton("Put back as it was")
        self.original_btn.setToolTip(
            "Every category on, in the order the dossier has always read: "
            + ", ".join(label_for(column) for column in sentiment.COLUMNS) + ".")
        self.original_btn.clicked.connect(self.put_back)
        for button in (self.up_btn, self.down_btn, self.original_btn):
            button.setCursor(Qt.PointingHandCursor)
            moves.addWidget(button)
        moves.addStretch(1)
        outer.addLayout(moves)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.use_btn = QPushButton("Use this order")
        self.use_btn.setObjectName("NavyFilled")
        self.use_btn.setDefault(True)
        self.use_btn.clicked.connect(self.accept)
        for button in (cancel, self.use_btn):
            button.setCursor(Qt.PointingHandCursor)
            buttons.addWidget(button)
        outer.addLayout(buttons)

    # ------------------------------------------------------------------ rows
    def fill(self, plan) -> None:
        self.list.clear()
        for column, on in sentiment.printing_plan(
                [getattr(c, "value", c) for c, _on in plan],
                {getattr(c, "value", c): state for c, state in plan}):
            item = QListWidgetItem(label_for(column))
            item.setData(VALUE_ROLE, column.value)
            item.setIcon(_swatch(colour_for(column)))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if on else Qt.Unchecked)
            item.setToolTip(
                f"{label_for(column)} prints "
                + ("in this place, and says “Nil - no clips” when it is empty."
                   if on else "nowhere: neither it nor its clippings are in "
                              "the dossier."))
            self.list.addItem(item)
        self.list.setCurrentRow(0)

    def move_row(self, step: int) -> None:
        """One row up or down. Never called move(): that is QWidget's own, and
        taking the name breaks every place Qt puts the window somewhere."""
        at = self.list.currentRow()
        wanted = at + step
        if at < 0 or not 0 <= wanted < self.list.count():
            return
        item = self.list.takeItem(at)
        self.list.insertItem(wanted, item)
        self.list.setCurrentRow(wanted)

    def put_back(self) -> None:
        self.fill(tuple((column, True) for column in sentiment.COLUMNS))

    def plan(self) -> tuple:
        """((category value, printed even when empty), ...), as it reads now."""
        out = []
        for row in range(self.list.count()):
            item = self.list.item(row)
            out.append((str(item.data(VALUE_ROLE)),
                        item.checkState() == Qt.Checked))
        return tuple(out)
