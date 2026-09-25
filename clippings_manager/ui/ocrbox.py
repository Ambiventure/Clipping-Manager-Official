"""The preview's OCR box: put a glass over the headline and read just that.

When the reader comes back with nonsense - a photograph read as words, the
wrong line picked - the fastest fix is to SHOW it where the headline is. This
is a clear box laid over the picture:

  * it magnifies what is under it a little, like a reading glass, so the words
    it will read are the words it is showing;
  * the white dot with the black ring in its middle is the handle: take hold
    of it with the hand and the box goes where the hand goes;
  * its edges and corners pull out and push in;
  * a double press on the dot reads it. A line sweeps down the glass while it
    reads, so nobody wonders whether anything is happening; the words then go
    into the headline box.

The box is kept as fractions of the picture on screen, so zooming the preview
or opening the next clipping never leaves it pointing at the wrong place.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QCursor, QLinearGradient, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import QWidget

#: How much the glass magnifies what is under it.
MAGNIFY = 1.22
#: The handle: its radius, and how far round it still counts as on it.
DOT = 8
DOT_REACH = 16
#: How near an edge the pointer has to be to take hold of it.
EDGE = 9
#: The smallest box, in screen pixels.
LEAST_W, LEAST_H = 60, 22


class OcrBox(QWidget):
    """The glass, laid over the whole picture area of the preview."""

    #: The box, in the picture's own pixels: (left, top, right, bottom).
    readWanted = Signal(tuple)
    #: The box was closed with Esc.
    closed = Signal()

    def __init__(self, canvas, full_pixmap, parent=None):
        """``canvas`` is the TrimCanvas; ``full_pixmap`` returns the picture
        at full size - what the glass magnifies, and what the box measures in."""
        super().__init__(parent if parent is not None else canvas)
        self.canvas = canvas
        self.full = full_pixmap
        # Across most of the picture, a third of the way down: where the
        # headline most often is, and easy to move from anywhere.
        self.box = [0.08, 0.10, 0.92, 0.24]
        self._hold = ""
        self._from = QPoint()
        self._began: list = []
        self._busy = False
        self._phase = 0.0
        self._glow = 0.0
        self._flash = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip("Drag the dot to move the box, pull an edge to size "
                        "it, and double-click the dot to read the headline "
                        "inside it.")
        canvas.installEventFilter(self)
        self.follow()

    # ------------------------------------------------------------ geometry
    def follow(self) -> None:
        """Cover the canvas exactly, however it has been zoomed or resized."""
        self.setGeometry(self.canvas.rect())
        self.raise_()
        self.update()

    def eventFilter(self, watched, event):  # noqa: N802 - Qt's name
        if watched is self.canvas and event.type() in (event.Type.Resize,
                                                       event.Type.Show):
            self.follow()
        return super().eventFilter(watched, event)

    def _picture(self) -> QRect:
        return self.canvas._picture()

    def rect_on_screen(self) -> QRect:
        picture = self._picture()
        if picture.isNull():
            return QRect()
        left, top, right, bottom = self.box
        return QRect(picture.left() + int(left * picture.width()),
                     picture.top() + int(top * picture.height()),
                     max(1, int((right - left) * picture.width())),
                     max(1, int((bottom - top) * picture.height())))

    def box_in_picture(self) -> tuple:
        """The box in the full-size picture's own pixels."""
        full = self.full()
        if full is None or full.isNull():
            return (0, 0, 0, 0)
        ratio = full.devicePixelRatio() or 1.0
        width, height = full.width() / ratio, full.height() / ratio
        left, top, right, bottom = self.box
        return (int(left * width), int(top * height),
                int(math.ceil(right * width)), int(math.ceil(bottom * height)))

    def _dot(self) -> QPointF:
        return QRectF(self.rect_on_screen()).center()

    def _grip(self, point: QPoint) -> str:
        """What the pointer would take hold of here."""
        area = self.rect_on_screen()
        if area.isNull():
            return ""
        centre = self._dot()
        if math.hypot(point.x() - centre.x(), point.y() - centre.y()) <= DOT_REACH:
            return "move"
        near_left = abs(point.x() - area.left()) <= EDGE
        near_right = abs(point.x() - area.right()) <= EDGE
        near_top = abs(point.y() - area.top()) <= EDGE
        near_bottom = abs(point.y() - area.bottom()) <= EDGE
        inside_x = area.left() - EDGE <= point.x() <= area.right() + EDGE
        inside_y = area.top() - EDGE <= point.y() <= area.bottom() + EDGE
        grip = ""
        if near_top and inside_x:
            grip += "top"
        elif near_bottom and inside_x:
            grip += "bottom"
        if near_left and inside_y:
            grip += "left"
        elif near_right and inside_y:
            grip += "right"
        if grip:
            return grip
        if area.contains(point):
            return "move"
        return ""

    @staticmethod
    def _cursor_for(grip: str):
        if grip == "move":
            return Qt.OpenHandCursor
        if grip in ("left", "right"):
            return Qt.SizeHorCursor
        if grip in ("top", "bottom"):
            return Qt.SizeVerCursor
        if grip in ("topleft", "bottomright"):
            return Qt.SizeFDiagCursor
        if grip in ("topright", "bottomleft"):
            return Qt.SizeBDiagCursor
        return Qt.ArrowCursor

    # --------------------------------------------------------------- input
    def mousePressEvent(self, event):  # noqa: N802 - Qt's name
        if event.button() != Qt.LeftButton or self._busy:
            return
        point = event.position().toPoint()
        self._hold = self._grip(point)
        self._from = point
        self._began = list(self.box)
        if self._hold == "move":
            self.setCursor(Qt.ClosedHandCursor)
        self.setFocus(Qt.MouseFocusReason)

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt's name
        point = event.position().toPoint()
        if not self._hold:
            self.setCursor(self._cursor_for(self._grip(point)))
            return
        picture = self._picture()
        if picture.isNull():
            return
        dx = (point.x() - self._from.x()) / float(max(1, picture.width()))
        dy = (point.y() - self._from.y()) / float(max(1, picture.height()))
        left, top, right, bottom = self._began
        least_w = LEAST_W / float(max(1, picture.width()))
        least_h = LEAST_H / float(max(1, picture.height()))
        if self._hold == "move":
            wide, tall = right - left, bottom - top
            left = min(max(0.0, left + dx), 1.0 - wide)
            top = min(max(0.0, top + dy), 1.0 - tall)
            right, bottom = left + wide, top + tall
        else:
            if "left" in self._hold:
                left = min(max(0.0, left + dx), right - least_w)
            if "right" in self._hold:
                right = max(min(1.0, right + dx), left + least_w)
            if "top" in self._hold:
                top = min(max(0.0, top + dy), bottom - least_h)
            if "bottom" in self._hold:
                bottom = max(min(1.0, bottom + dy), top + least_h)
        self.box = [left, top, right, bottom]
        self.update()

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt's name
        was = self._hold
        self._hold = ""
        point = event.position().toPoint()
        self.setCursor(self._cursor_for(self._grip(point)) if was else
                       self._cursor_for(self._grip(point)))

    def mouseDoubleClickEvent(self, event):  # noqa: N802 - Qt's name
        if event.button() != Qt.LeftButton or self._busy:
            return
        centre = self._dot()
        point = event.position()
        if math.hypot(point.x() - centre.x(), point.y() - centre.y()) <= DOT_REACH:
            self.read()

    def keyPressEvent(self, event):  # noqa: N802 - Qt's name
        if event.key() == Qt.Key_Escape:
            self.closed.emit()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not self._busy:
            self.read()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------- reading
    def read(self) -> None:
        box = self.box_in_picture()
        if box[2] - box[0] < 4 or box[3] - box[1] < 4:
            return
        self.busy(True)
        self.readWanted.emit(box)

    def busy(self, on: bool) -> None:
        """The sweep while it reads; a green flash when the words are back."""
        self._busy = bool(on)
        if on:
            self._phase = 0.0
            self._timer.start()
            self.setCursor(Qt.BusyCursor)
        else:
            self._flash = 18
            self.setCursor(self._cursor_for(
                self._grip(self.mapFromGlobal(QCursor.pos()))))
        self.update()

    def _tick(self) -> None:
        if self._busy:
            self._phase = (self._phase + 0.022) % 1.0
            self._glow = 0.5 + 0.5 * math.sin(self._phase * math.tau * 2)
        elif self._flash > 0:
            self._flash -= 1
        else:
            self._timer.stop()
        self.update()

    # --------------------------------------------------------------- paint
    def paintEvent(self, event):  # noqa: N802 - Qt's name
        area = QRectF(self.rect_on_screen())
        if area.isEmpty():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # Everything but the glass a little dimmer, so the box is what is
        # looked at.
        outside = QPainterPath()
        outside.addRect(QRectF(self._picture()))
        hole = QPainterPath()
        hole.addRoundedRect(area, 8, 8)
        painter.fillPath(outside.subtracted(hole), QColor(9, 16, 30, 70))

        # The glass: what is under it, a little larger.
        full = self.full()
        picture = self._picture()
        if full is not None and not full.isNull() and not picture.isEmpty():
            ratio = full.devicePixelRatio() or 1.0
            scale_x = (full.width() / ratio) / picture.width()
            scale_y = (full.height() / ratio) / picture.height()
            centre = area.center()
            source_w = area.width() * scale_x / MAGNIFY
            source_h = area.height() * scale_y / MAGNIFY
            source = QRectF(
                (centre.x() - picture.left()) * scale_x - source_w / 2,
                (centre.y() - picture.top()) * scale_y - source_h / 2,
                source_w, source_h)
            clip = QPainterPath()
            clip.addRoundedRect(area, 8, 8)
            painter.save()
            painter.setClipPath(clip)
            painter.fillRect(area, QColor("#FFFFFF"))
            painter.drawPixmap(area, full, QRectF(
                source.left() * ratio, source.top() * ratio,
                source.width() * ratio, source.height() * ratio))
            # A faint sheen, so it reads as glass rather than as a cut-out.
            sheen = QLinearGradient(area.topLeft(), area.bottomLeft())
            sheen.setColorAt(0.0, QColor(255, 255, 255, 38))
            sheen.setColorAt(0.5, QColor(255, 255, 255, 0))
            painter.fillRect(area, sheen)
            if self._busy:
                # THE SWEEP: a bright line going down the glass while it reads.
                y = area.top() + self._phase * area.height()
                band = QLinearGradient(QPointF(0, y - 18), QPointF(0, y + 2))
                band.setColorAt(0.0, QColor(56, 189, 248, 0))
                band.setColorAt(1.0, QColor(56, 189, 248, 120))
                painter.fillRect(QRectF(area.left(), y - 18, area.width(), 20),
                                 band)
                painter.setPen(QPen(QColor(125, 211, 252, 235), 2))
                painter.drawLine(QPointF(area.left() + 4, y),
                                 QPointF(area.right() - 4, y))
            painter.restore()

        # The rim: blue and breathing while it reads, green for a moment when
        # the words are back, white otherwise.
        if self._busy:
            rim = QColor(56, 189, 248, int(150 + 105 * self._glow))
            width = 2.5 + 1.5 * self._glow
        elif self._flash > 0:
            rim = QColor(34, 197, 94, int(255 * self._flash / 18))
            width = 3.0
        else:
            rim = QColor(255, 255, 255, 235)
            width = 2.0
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 90), width + 2.5))
        painter.drawRoundedRect(area, 8, 8)
        painter.setPen(QPen(rim, width))
        painter.drawRoundedRect(area, 8, 8)

        # Corner ticks, so the edges plainly pull.
        painter.setPen(QPen(QColor(255, 255, 255, 230), 3, Qt.SolidLine,
                            Qt.RoundCap))
        tick = 10.0
        for cx, cy, sx, sy in ((area.left(), area.top(), 1, 1),
                               (area.right(), area.top(), -1, 1),
                               (area.left(), area.bottom(), 1, -1),
                               (area.right(), area.bottom(), -1, -1)):
            painter.drawLine(QPointF(cx, cy + sy * 3), QPointF(cx, cy + sy * tick))
            painter.drawLine(QPointF(cx + sx * 3, cy), QPointF(cx + sx * tick, cy))

        # The handle: a white dot in a black ring.
        centre = area.center()
        grow = 1.5 * self._glow if self._busy else 0.0
        painter.setPen(QPen(QColor(0, 0, 0), 2.2))
        painter.setBrush(QColor(255, 255, 255))
        painter.drawEllipse(centre, DOT + grow, DOT + grow)
        painter.end()
