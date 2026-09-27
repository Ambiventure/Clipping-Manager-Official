"""The text box that opens over a painted field, set exactly as the field was.

A row in the list and a card on the board do not carry real text boxes: their
LABEL, OCR and URL boxes are painted, and a real one is put over the box only
while somebody types in it. That box used to take the application's own look
for a text field - 12px, semi-bold, its words starting at the far left - over a
field painted at 13 or 14px in bold, a size and a half bigger again for Hindi,
with its words after the tag. So pressing a field shrank its words, moved them
to the left and hid the tag, and pressing Esc made them jump back.

This box is set from the same numbers the field was painted with: the same
faces, size and weight (both following what is typed, Hindi a size up, as the
painting does), the same ink, its words starting at the same place, and the
tag drawn where it was. Opening it changes nothing on screen but the edge and
the caret.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QLineEdit, QWidget

from . import theme

#: How far inside its contents a line edit starts its words, and how far down
#: it keeps them - Qt's own, QLineEditPrivate::horizontalMargin. Taken off
#: the padding, so the words land where the painting put them.
QT_TEXT_MARGIN = 2


class FieldEditor(QLineEdit):
    """A line edit that looks like the painted field it is typed over.

    ``text_x`` is where the painted words start and ``right`` how far their
    room ends from the right edge, both measured from the box's own edges.
    ``size`` is the pixel size for English and for an empty box; with
    ``lift`` a Devanagari line is set theme.reading_size bigger, as the
    painting sets it. ``filled_weight`` is the weight of words, and the
    placeholder is ``empty_weight``. The tag is drawn in ``tag_rect``: on a
    grey chip when ``tag_fill`` is given (the list's rows), as plain letters
    when it is not (the board's cards).
    """

    def __init__(self, parent: QWidget, *, font: Optional[QFont] = None,
                 text_x: int = 12, right: int = 10, size: int = 13,
                 lift: bool = True, filled_weight: int = 700,
                 empty_weight: int = 400, ink: str = theme.INK,
                 background: str = theme.SURFACE, border: str = theme.NAVY,
                 border_px: int = 1, radius: int = 10, tag: str = "",
                 tag_rect: Optional[QRectF] = None, tag_px: int = 9,
                 tag_ink: str = "#64748B", tag_fill: Optional[str] = None,
                 tag_radius: float = 5.0, tag_centred: bool = True):
        super().__init__(parent)
        if font is not None:
            # The painted field's own faces, Devanagari chain and all - set
            # before the sheet, which then changes only the size and weight.
            self.setFont(font)
        theme.apply_font(self)
        self._text_x, self._right = int(text_x), int(right)
        self._size, self._lift = int(size), bool(lift)
        self._filled_weight, self._empty_weight = filled_weight, empty_weight
        self._ink, self._background = ink, background
        self._border, self._border_px, self._radius = border, border_px, radius
        self._tag, self._tag_rect = tag, tag_rect
        self._tag_px, self._tag_ink, self._tag_fill = tag_px, tag_ink, tag_fill
        self._tag_radius, self._tag_centred = tag_radius, tag_centred
        self._look = None
        self.textChanged.connect(lambda _text: self._restyle())
        self._restyle()

    def looks(self) -> tuple:
        """(pixel size, weight) as set now - for the tests."""
        return self._look or (self._size, self._empty_weight)

    def _restyle(self) -> None:
        """Size and weight after what is in the box, as the painting does.

        Set again only when either changes: a sheet set on every keystroke
        re-polishes the box each time for nothing.
        """
        text = self.text()
        filled = bool(text.strip())
        size = (theme.reading_size(text, self._size)
                if filled and self._lift else self._size)
        weight = self._filled_weight if filled else self._empty_weight
        if (size, weight) == self._look:
            return
        self._look = (size, weight)
        left = max(0, self._text_x - self._border_px - QT_TEXT_MARGIN)
        right = max(0, self._right - self._border_px - QT_TEXT_MARGIN)
        # Padding top and bottom nil: the words are centred in the box, as
        # the painting centres them. Selection colours are left to the
        # application's sheet - navy on these white boxes reads well.
        self.setStyleSheet(
            f"QLineEdit {{ background: {self._background};"
            f" border: {self._border_px}px solid {self._border};"
            f" border-radius: {self._radius}px;"
            f" padding: 0px {right}px 0px {left}px;"
            f" font-size: {size}px; font-weight: {weight};"
            f" color: {self._ink}; }}")

    def paintEvent(self, event):  # noqa: N802 - Qt name
        super().paintEvent(event)
        if not self._tag or self._tag_rect is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        if self._tag_fill:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(self._tag_fill))
            painter.drawRoundedRect(self._tag_rect, self._tag_radius,
                                    self._tag_radius)
        font = QFont(self.font())
        font.setPixelSize(self._tag_px)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(self._tag_ink))
        painter.drawText(
            self._tag_rect,
            Qt.AlignCenter if self._tag_centred
            else Qt.AlignVCenter | Qt.AlignLeft,
            self._tag)
        painter.end()

    def select_from_start(self) -> None:
        """Everything selected, with the caret at the START, so a line longer
        than the box shows its beginning - where the painting showed it -
        rather than scrolling to its end."""
        length = len(self.text())
        self.setCursorPosition(0)
        if length:
            self.setSelection(length, -length)
