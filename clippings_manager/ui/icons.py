"""Vector icons drawn straight onto the painter.

The rows are painted rather than built from widgets, so the icons have to be
paintable too. These are simple stroked paths in the Lucide manner: 1.6px strokes,
round caps, drawn inside whatever square rectangle they are handed.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen


def _pen(color: QColor, width: float = 1.6) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _unit(painter: QPainter, box: QRectF):
    """Scale so icon paths can be written in a 24x24 space."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.translate(box.center())
    scale = min(box.width(), box.height()) / 24.0
    painter.scale(scale, scale)
    painter.translate(-12, -12)
    return scale


def grip(painter: QPainter, box: QRectF, color: QColor) -> None:
    """Six dots, the universal 'drag me' handle."""
    _unit(painter, box)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    for x in (9, 15):
        for y in (6, 12, 18):
            painter.drawEllipse(QPointF(x, y), 1.5, 1.5)
    painter.restore()


def check(painter: QPainter, box: QRectF, color: QColor, width: float = 2.6) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, width))
    path = QPainterPath(QPointF(5, 12.5))
    path.lineTo(10, 17.5)
    path.lineTo(19, 6.5)
    painter.drawPath(path)
    painter.restore()


def _chevron(painter: QPainter, box: QRectF, color: QColor, direction: str,
             width: float = 1.9) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, width))
    points = {
        "up": [(6, 15), (12, 9), (18, 15)],
        "down": [(6, 9), (12, 15), (18, 9)],
        "left": [(15, 6), (9, 12), (15, 18)],
        "right": [(9, 6), (15, 12), (9, 18)],
    }[direction]
    path = QPainterPath(QPointF(*points[0]))
    for point in points[1:]:
        path.lineTo(QPointF(*point))
    painter.drawPath(path)
    painter.restore()


def chevron_up(painter, box, color, width=1.9):
    _chevron(painter, box, color, "up", width)


def chevron_down(painter, box, color, width=1.9):
    _chevron(painter, box, color, "down", width)


def chevron_left(painter, box, color, width=1.9):
    _chevron(painter, box, color, "left", width)


def chevron_right(painter, box, color, width=1.9):
    _chevron(painter, box, color, "right", width)


def chevrons_up(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.9))
    for offset in (0, 6):
        path = QPainterPath(QPointF(6, 13 + offset))
        path.lineTo(12, 7 + offset)
        path.lineTo(18, 13 + offset)
        painter.drawPath(path)
    painter.restore()


def chevrons_down(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.9))
    for offset in (0, 6):
        path = QPainterPath(QPointF(6, 5 + offset))
        path.lineTo(12, 11 + offset)
        path.lineTo(18, 5 + offset)
        painter.drawPath(path)
    painter.restore()


def trash(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color))
    painter.drawLine(QPointF(4, 6.5), QPointF(20, 6.5))
    painter.drawLine(QPointF(9.5, 6.5), QPointF(9.5, 4.5))
    painter.drawLine(QPointF(9.5, 4.5), QPointF(14.5, 4.5))
    painter.drawLine(QPointF(14.5, 4.5), QPointF(14.5, 6.5))
    path = QPainterPath(QPointF(6, 6.5))
    path.lineTo(7, 19.5)
    path.lineTo(17, 19.5)
    path.lineTo(18, 6.5)
    painter.drawPath(path)
    painter.drawLine(QPointF(10, 10), QPointF(10, 16))
    painter.drawLine(QPointF(14, 10), QPointF(14, 16))
    painter.restore()


def rotate(painter: QPainter, box: QRectF, color: QColor) -> None:
    """Clockwise refresh arrow."""
    _unit(painter, box)
    painter.setPen(_pen(color))
    rect = QRectF(4.5, 4.5, 15, 15)
    painter.drawArc(rect, 70 * 16, -280 * 16)
    head = QPainterPath(QPointF(14.6, 3.2))
    head.lineTo(18.6, 6.0)
    head.lineTo(14.8, 8.4)
    painter.drawPath(head)
    painter.restore()


def maximize(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 2.0))
    painter.drawLine(QPointF(4, 9), QPointF(4, 4))
    painter.drawLine(QPointF(4, 4), QPointF(9, 4))
    painter.drawLine(QPointF(15, 4), QPointF(20, 4))
    painter.drawLine(QPointF(20, 4), QPointF(20, 9))
    painter.drawLine(QPointF(20, 15), QPointF(20, 20))
    painter.drawLine(QPointF(20, 20), QPointF(15, 20))
    painter.drawLine(QPointF(9, 20), QPointF(4, 20))
    painter.drawLine(QPointF(4, 20), QPointF(4, 15))
    painter.restore()


def scissors(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QPointF(6.5, 18), 2.6, 2.6)
    painter.drawEllipse(QPointF(17.5, 18), 2.6, 2.6)
    painter.drawLine(QPointF(8.4, 16.1), QPointF(18, 4))
    painter.drawLine(QPointF(15.6, 16.1), QPointF(6, 4))
    painter.restore()


def combine(painter: QPainter, box: QRectF, color: QColor) -> None:
    """Two blocks merging into one, for the merge action."""
    _unit(painter, box)
    painter.setPen(_pen(color))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(3.5, 3.5, 8, 6), 1.5, 1.5)
    painter.drawRoundedRect(QRectF(3.5, 14.5, 8, 6), 1.5, 1.5)
    painter.drawLine(QPointF(12.5, 6.5), QPointF(16, 6.5))
    painter.drawLine(QPointF(12.5, 17.5), QPointF(16, 17.5))
    painter.drawLine(QPointF(16, 6.5), QPointF(16, 17.5))
    painter.drawLine(QPointF(16, 12), QPointF(20.5, 12))
    head = QPainterPath(QPointF(18.5, 10))
    head.lineTo(21, 12)
    head.lineTo(18.5, 14)
    painter.drawPath(head)
    painter.restore()


def undo(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.9))
    painter.drawArc(QRectF(4, 6, 16, 13), 20 * 16, 160 * 16)
    head = QPainterPath(QPointF(4, 5))
    head.lineTo(4, 11)
    head.lineTo(10, 11)
    painter.drawPath(head)
    painter.restore()


def redo(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.9))
    painter.drawArc(QRectF(4, 6, 16, 13), 0 * 16, 160 * 16)
    head = QPainterPath(QPointF(20, 5))
    head.lineTo(20, 11)
    head.lineTo(14, 11)
    painter.drawPath(head)
    painter.restore()


def paperclip(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.8))
    path = QPainterPath(QPointF(16.5, 8))
    path.lineTo(8.5, 16)
    path.cubicTo(QPointF(6.5, 18), QPointF(4, 15.5), QPointF(6, 13.5))
    path.lineTo(15, 4.5)
    path.cubicTo(QPointF(17.5, 2), QPointF(21.5, 6), QPointF(19, 8.5))
    path.lineTo(10.5, 17)
    painter.drawPath(path)
    painter.restore()


def file_word(painter: QPainter, box: QRectF, color: QColor) -> None:
    _file(painter, box, color, "W")


def file_pdf(painter: QPainter, box: QRectF, color: QColor) -> None:
    _file(painter, box, color, "P")


def _file(painter: QPainter, box: QRectF, color: QColor, letter: str) -> None:
    scale = _unit(painter, box)
    painter.setPen(_pen(color, 1.7))
    path = QPainterPath(QPointF(6, 3))
    path.lineTo(14, 3)
    path.lineTo(19, 8)
    path.lineTo(19, 21)
    path.lineTo(6, 21)
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawLine(QPointF(14, 3), QPointF(14, 8))
    painter.drawLine(QPointF(14, 8), QPointF(19, 8))
    font = painter.font()
    font.setPixelSize(8)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRectF(6, 11, 13, 9), Qt.AlignCenter, letter)
    painter.restore()


def image(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.7))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(3.5, 5, 17, 14), 2, 2)
    painter.drawEllipse(QPointF(9, 10), 1.6, 1.6)
    path = QPainterPath(QPointF(5, 17))
    path.lineTo(10, 12)
    path.lineTo(14, 15.5)
    path.lineTo(16.5, 13)
    path.lineTo(19, 15.5)
    painter.drawPath(path)
    painter.restore()


def upload_cloud(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.7))
    path = QPainterPath(QPointF(7, 17))
    path.cubicTo(QPointF(2.5, 17), QPointF(2.5, 10.5), QPointF(7.2, 10.4))
    path.cubicTo(QPointF(8.2, 5.2), QPointF(15.6, 4.6), QPointF(16.6, 10.2))
    path.cubicTo(QPointF(21.5, 10.4), QPointF(21.5, 17), QPointF(17, 17))
    painter.drawPath(path)
    painter.drawLine(QPointF(12, 12), QPointF(12, 21))
    head = QPainterPath(QPointF(9, 15))
    head.lineTo(12, 12)
    head.lineTo(15, 15)
    painter.drawPath(head)
    painter.restore()


def close_x(painter: QPainter, box: QRectF, color: QColor, width: float = 2.0) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, width))
    painter.drawLine(QPointF(6, 6), QPointF(18, 18))
    painter.drawLine(QPointF(18, 6), QPointF(6, 18))
    painter.restore()


def zoom(painter: QPainter, box: QRectF, color: QColor, sign: str = "+") -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.8))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QPointF(10.5, 10.5), 6.2, 6.2)
    painter.drawLine(QPointF(15.2, 15.2), QPointF(20, 20))
    painter.drawLine(QPointF(7.5, 10.5), QPointF(13.5, 10.5))
    if sign == "+":
        painter.drawLine(QPointF(10.5, 7.5), QPointF(10.5, 13.5))
    painter.restore()


def wand(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.7))
    painter.drawLine(QPointF(5, 19), QPointF(16, 8))
    painter.drawLine(QPointF(14, 6), QPointF(18, 10))
    for cx, cy, r in ((18.5, 4.5, 1.6), (7, 6, 1.3), (20, 14, 1.3)):
        painter.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
        painter.drawLine(QPointF(cx, cy - r), QPointF(cx, cy + r))
    painter.restore()


def shield(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.7))
    path = QPainterPath(QPointF(12, 3))
    path.lineTo(19.5, 6)
    path.lineTo(19.5, 12)
    path.cubicTo(QPointF(19.5, 17), QPointF(15.5, 20), QPointF(12, 21))
    path.cubicTo(QPointF(8.5, 20), QPointF(4.5, 17), QPointF(4.5, 12))
    path.lineTo(4.5, 6)
    path.closeSubpath()
    painter.drawPath(path)
    painter.restore()


def square(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.9))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(4, 4, 16, 16), 3, 3)
    painter.restore()


def check_square(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(QRectF(4, 4, 16, 16), 3, 3)
    pen = _pen(QColor("white"), 2.4)
    painter.setPen(pen)
    path = QPainterPath(QPointF(8, 12))
    path.lineTo(11, 15)
    path.lineTo(16.5, 8.5)
    painter.drawPath(path)
    painter.restore()


def dash_square(painter: QPainter, box: QRectF, color: QColor) -> None:
    """Partially-selected group indicator."""
    _unit(painter, box)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(QRectF(4, 4, 16, 16), 3, 3)
    painter.setPen(_pen(QColor("white"), 2.4))
    painter.drawLine(QPointF(8, 12), QPointF(16, 12))
    painter.restore()


def thumbs_up(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.8))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(3, 10, 5, 10), 1.2, 1.2)
    path = QPainterPath(QPointF(9, 20))
    path.lineTo(9, 10)
    path.lineTo(12.5, 3.5)
    path.cubicTo(QPointF(15, 3), QPointF(16, 5), QPointF(15.2, 7))
    path.lineTo(14, 10)
    path.lineTo(19.5, 10)
    path.cubicTo(QPointF(21.5, 10), QPointF(21.5, 12.5), QPointF(20.6, 14))
    path.lineTo(18.6, 19)
    path.cubicTo(QPointF(18.1, 20), QPointF(17, 20), QPointF(16, 20))
    path.closeSubpath()
    painter.drawPath(path)
    painter.restore()


def thumbs_down(painter: QPainter, box: QRectF, color: QColor) -> None:
    painter.save()
    painter.translate(box.center())
    painter.rotate(180)
    painter.translate(-box.center())
    thumbs_up(painter, box, color)
    painter.restore()


def minus(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 2.6))
    painter.drawLine(QPointF(5, 12), QPointF(19, 12))
    painter.restore()


def plus(painter: QPainter, box: QRectF, color: QColor, width: float = 2.2) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, width))
    painter.drawLine(QPointF(5, 12), QPointF(19, 12))
    painter.drawLine(QPointF(12, 5), QPointF(12, 19))
    painter.restore()


def globe(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.7))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QPointF(12, 12), 8.6, 8.6)
    painter.drawLine(QPointF(3.4, 12), QPointF(20.6, 12))
    # the two meridians that make a flat circle read as a sphere
    painter.drawArc(QRectF(7.6, 3.4, 8.8, 17.2), 90 * 16, 180 * 16)
    painter.drawArc(QRectF(7.6, 3.4, 8.8, 17.2), 270 * 16, 180 * 16)
    painter.restore()


def sliders(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.8))
    for x, cy in ((6, 9), (12, 15), (18, 7)):
        painter.drawLine(QPointF(x, 3), QPointF(x, cy - 2.2))
        painter.drawLine(QPointF(x, cy + 2.2), QPointF(x, 21))
        painter.drawEllipse(QPointF(x, cy), 2.2, 2.2)
    painter.restore()


def layers(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.7))
    for offset in (0, 4.6, 9.2):
        path = QPainterPath(QPointF(12, 3 + offset))
        path.lineTo(21, 7 + offset)
        path.lineTo(12, 11 + offset)
        path.lineTo(3, 7 + offset)
        path.closeSubpath()
        painter.drawPath(path)
    painter.restore()


def crosshair(painter: QPainter, box: QRectF, color: QColor) -> None:
    """The 'click to place' marker, matching the browser's placement hint."""
    _unit(painter, box)
    painter.setPen(_pen(color, 1.7))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QPointF(12, 12), 9, 9)
    for x1, y1, x2, y2 in ((22, 12, 18, 12), (6, 12, 2, 12),
                           (12, 6, 12, 2), (12, 22, 12, 18)):
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    painter.restore()


def type_letter(painter: QPainter, box: QRectF, color: QColor) -> None:
    """A serif 'T' - the heading field's badge."""
    _unit(painter, box)
    painter.setPen(_pen(color, 1.8))
    painter.drawLine(QPointF(4, 7), QPointF(4, 4))
    painter.drawLine(QPointF(4, 4), QPointF(20, 4))
    painter.drawLine(QPointF(20, 4), QPointF(20, 7))
    painter.drawLine(QPointF(12, 4), QPointF(12, 20))
    painter.drawLine(QPointF(8, 20), QPointF(16, 20))
    painter.restore()


def calendar(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.6))
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(QRectF(3, 5, 18, 16), 2.5, 2.5)
    painter.drawLine(QPointF(3, 10), QPointF(21, 10))
    painter.drawLine(QPointF(8, 3), QPointF(8, 7))
    painter.drawLine(QPointF(16, 3), QPointF(16, 7))
    painter.restore()


def sparkles(painter: QPainter, box: QRectF, color: QColor) -> None:
    """Two four-pointed stars - the 'optional flourish' badge."""
    _unit(painter, box)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    for cx, cy, r in ((10, 10, 6.5), (18, 17, 4.0)):
        star = QPainterPath(QPointF(cx, cy - r))
        star.quadTo(cx + r * 0.18, cy - r * 0.18, cx + r, cy)
        star.quadTo(cx + r * 0.18, cy + r * 0.18, cx, cy + r)
        star.quadTo(cx - r * 0.18, cy + r * 0.18, cx - r, cy)
        star.quadTo(cx - r * 0.18, cy - r * 0.18, cx, cy - r)
        painter.drawPath(star)
    painter.restore()


def _align(painter: QPainter, box: QRectF, color: QColor, mode: str) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 2.0))
    full, short = (4.0, 20.0), (4.0, 14.0)
    for index, y in enumerate((6.0, 10.5, 15.0, 19.5)):
        x1, x2 = full if index % 2 == 0 else short
        if index % 2:
            if mode == "center":
                width = x2 - x1
                x1 = 12 - width / 2
                x2 = 12 + width / 2
            elif mode == "right":
                width = x2 - x1
                x1, x2 = 20 - width, 20.0
        painter.drawLine(QPointF(x1, y), QPointF(x2, y))
    painter.restore()


def align_left(painter: QPainter, box: QRectF, color: QColor) -> None:
    _align(painter, box, color, "left")


def align_center(painter: QPainter, box: QRectF, color: QColor) -> None:
    _align(painter, box, color, "center")


def align_right(painter: QPainter, box: QRectF, color: QColor) -> None:
    _align(painter, box, color, "right")


def dot_solid(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(QPointF(12, 12), 8, 8)
    painter.restore()


def dot_hollow(painter: QPainter, box: QRectF, color: QColor) -> None:
    _unit(painter, box)
    painter.setPen(_pen(color, 1.8))
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QPointF(12, 12), 7.5, 7.5)
    painter.restore()


def file_text(painter: QPainter, box: QRectF, color: QColor) -> None:
    """A document with ruled lines - the dossier badge."""
    _unit(painter, box)
    painter.setPen(_pen(color, 1.7))
    painter.setBrush(Qt.NoBrush)
    path = QPainterPath(QPointF(14, 2))
    path.lineTo(6, 2)
    path.quadTo(4, 2, 4, 4)
    path.lineTo(4, 20)
    path.quadTo(4, 22, 6, 22)
    path.lineTo(18, 22)
    path.quadTo(20, 22, 20, 20)
    path.lineTo(20, 8)
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawLine(QPointF(14, 2), QPointF(14, 8))
    painter.drawLine(QPointF(14, 8), QPointF(20, 8))
    for y in (13, 17):
        painter.drawLine(QPointF(8, y), QPointF(16, y))
    painter.restore()


def building(painter: QPainter, box: QRectF, color: QColor) -> None:
    """An office block - the division and text tab."""
    _unit(painter, box)
    painter.setPen(_pen(color, 1.6))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(QRectF(6, 3, 12, 18))
    painter.drawRect(QRectF(18, 9, 4, 12))
    for y in (7, 11, 15):
        painter.drawLine(QPointF(9, y), QPointF(11, y))
        painter.drawLine(QPointF(13, y), QPointF(15, y))
    painter.drawLine(QPointF(10, 21), QPointF(10, 18))
    painter.drawLine(QPointF(14, 21), QPointF(14, 18))
    painter.drawLine(QPointF(10, 18), QPointF(14, 18))
    painter.restore()


def palette(painter: QPainter, box: QRectF, color: QColor) -> None:
    """A painter's palette - the logo and styling tab."""
    _unit(painter, box)
    painter.setPen(_pen(color, 1.6))
    painter.setBrush(Qt.NoBrush)
    path = QPainterPath(QPointF(12, 3))
    path.cubicTo(19, 3, 21, 8, 21, 12)
    path.cubicTo(21, 16, 17, 16, 15, 16)
    path.cubicTo(13, 16, 13, 19, 14, 20)
    path.cubicTo(15, 21, 13, 21, 12, 21)
    path.cubicTo(7, 21, 3, 17, 3, 12)
    path.cubicTo(3, 7, 7, 3, 12, 3)
    painter.drawPath(path)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    for x, y in ((8, 9), (12, 7), (16, 10)):
        painter.drawEllipse(QPointF(x, y), 1.3, 1.3)
    painter.restore()


def hash_sign(painter: QPainter, box: QRectF, color: QColor) -> None:
    """A number sign - the clip count section."""
    _unit(painter, box)
    painter.setPen(_pen(color, 1.8))
    painter.drawLine(QPointF(9, 3), QPointF(7, 21))
    painter.drawLine(QPointF(17, 3), QPointF(15, 21))
    painter.drawLine(QPointF(4, 9), QPointF(20, 9))
    painter.drawLine(QPointF(3, 15), QPointF(19, 15))
    painter.restore()


def eye(painter: QPainter, box: QRectF, color: QColor) -> None:
    """The live preview heading."""
    _unit(painter, box)
    painter.setPen(_pen(color, 1.6))
    painter.setBrush(Qt.NoBrush)
    path = QPainterPath(QPointF(2, 12))
    path.quadTo(7, 5, 12, 5)
    path.quadTo(17, 5, 22, 12)
    path.quadTo(17, 19, 12, 19)
    path.quadTo(7, 19, 2, 12)
    painter.drawPath(path)
    painter.drawEllipse(QPointF(12, 12), 3.2, 3.2)
    painter.restore()


def move(painter: QPainter, box: QRectF, color: QColor) -> None:
    """Four-way arrows - the placement tab and the drag hint."""
    _unit(painter, box)
    painter.setPen(_pen(color, 1.7))
    painter.drawLine(QPointF(12, 2), QPointF(12, 22))
    painter.drawLine(QPointF(2, 12), QPointF(22, 12))
    for tip, a, b in (((12, 2), (9, 5), (15, 5)), ((12, 22), (9, 19), (15, 19)),
                      ((2, 12), (5, 9), (5, 15)), ((22, 12), (19, 9), (19, 15))):
        painter.drawLine(QPointF(*a), QPointF(*tip))
        painter.drawLine(QPointF(*tip), QPointF(*b))
    painter.restore()
