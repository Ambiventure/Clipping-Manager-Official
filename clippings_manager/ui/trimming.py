"""Trimming a clipping by dragging its edges in, on the full-size view.

A capture from a link, or a photo taken at arm's length, often carries a strip
of something else along its edge. This is the box that takes it off: drag an
edge or a corner, or drag inside the box to move it, and what is left is the
clipping.

Nothing is cut from the picture itself. The box becomes the clipping's crop,
which is applied when it is drawn and when it is exported, and Ctrl+Z puts it
back - the original pixels are never touched. See core/models.CropRect.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QLabel

from . import theme

#: How near an edge the pointer has to be, in pixels, to take hold of it.
GRIP = 14
#: The smallest box that can be dragged out, as a fraction of the picture.
LEAST = 0.04

_EDGES = ("left", "top", "right", "bottom")


class TrimCanvas(QLabel):
    """The picture, and while trimming is on, the box drawn over it."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.trimming = False
        self.box = [0.0, 0.0, 1.0, 1.0]      # left, top, right, bottom (0-1)
        self._holding = ""
        self._from = QPoint()
        self._began: list = []
        self.setMouseTracking(True)

    # ------------------------------------------------------------- the box
    def start_trim(self) -> None:
        self.trimming = True
        self.box = [0.0, 0.0, 1.0, 1.0]
        self.setCursor(Qt.CrossCursor)
        self.update()

    def stop_trim(self) -> None:
        self.trimming = False
        self._holding = ""
        self.unsetCursor()
        self.update()

    def where(self) -> tuple:
        """The box, as fractions of the picture on screen."""
        return tuple(self.box)

    # ----------------------------------------------------------- geometry
    def _picture(self) -> QRect:
        """Where the picture actually sits inside this widget."""
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return QRect()
        ratio = pixmap.devicePixelRatio() or 1.0
        size = pixmap.size() / ratio
        inside = self.contentsRect()
        left = inside.left() + max(0, (inside.width() - size.width()) // 2)
        top = inside.top() + max(0, (inside.height() - size.height()) // 2)
        return QRect(int(left), int(top), int(size.width()), int(size.height()))

    def _box_rect(self) -> QRect:
        picture = self._picture()
        if picture.isNull():
            return QRect()
        left, top, right, bottom = self.box
        return QRect(
            picture.left() + int(left * picture.width()),
            picture.top() + int(top * picture.height()),
            max(1, int((right - left) * picture.width())),
            max(1, int((bottom - top) * picture.height())),
        )

    def _grip_at(self, point: QPoint) -> str:
        rect = self._box_rect()
        if rect.isNull():
            return ""
        near_left = abs(point.x() - rect.left()) <= GRIP
        near_right = abs(point.x() - rect.right()) <= GRIP
        near_top = abs(point.y() - rect.top()) <= GRIP
        near_bottom = abs(point.y() - rect.bottom()) <= GRIP
        inside_x = rect.left() - GRIP <= point.x() <= rect.right() + GRIP
        inside_y = rect.top() - GRIP <= point.y() <= rect.bottom() + GRIP
        if near_left and near_top:
            return "left top"
        if near_right and near_top:
            return "right top"
        if near_left and near_bottom:
            return "left bottom"
        if near_right and near_bottom:
            return "right bottom"
        if near_left and inside_y:
            return "left"
        if near_right and inside_y:
            return "right"
        if near_top and inside_x:
            return "top"
        if near_bottom and inside_x:
            return "bottom"
        if rect.contains(point):
            return "move"
        return ""

    @staticmethod
    def _cursor_for(grip: str):
        if grip in ("left", "right"):
            return Qt.SizeHorCursor
        if grip in ("top", "bottom"):
            return Qt.SizeVerCursor
        if grip in ("left top", "right bottom"):
            return Qt.SizeFDiagCursor
        if grip in ("right top", "left bottom"):
            return Qt.SizeBDiagCursor
        if grip == "move":
            return Qt.SizeAllCursor
        return Qt.CrossCursor

    # -------------------------------------------------------------- mouse
    def mousePressEvent(self, event):  # noqa: N802 - Qt's name
        if not self.trimming or event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        point = event.position().toPoint()
        self._holding = self._grip_at(point) or "new"
        self._from = point
        self._began = list(self.box)
        if self._holding == "new":
            picture = self._picture()
            if picture.isNull():
                self._holding = ""
                return
            across = (point.x() - picture.left()) / max(1, picture.width())
            down = (point.y() - picture.top()) / max(1, picture.height())
            across = min(1.0, max(0.0, across))
            down = min(1.0, max(0.0, down))
            self.box = [across, down, across, down]
            self._began = list(self.box)
            self._holding = "right bottom"
        self.update()

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt's name
        point = event.position().toPoint()
        if not self.trimming:
            super().mouseMoveEvent(event)
            return
        if not self._holding:
            self.setCursor(QCursor(self._cursor_for(self._grip_at(point))))
            return
        picture = self._picture()
        if picture.isNull():
            return
        across = (point.x() - self._from.x()) / max(1, picture.width())
        down = (point.y() - self._from.y()) / max(1, picture.height())
        left, top, right, bottom = self._began
        if self._holding == "move":
            across = max(-left, min(1.0 - right, across))
            down = max(-top, min(1.0 - bottom, down))
            self.box = [left + across, top + down, right + across, bottom + down]
        else:
            held = self._holding.split()
            if "left" in held:
                left = min(max(0.0, left + across), right - LEAST)
            if "right" in held:
                right = max(min(1.0, right + across), left + LEAST)
            if "top" in held:
                top = min(max(0.0, top + down), bottom - LEAST)
            if "bottom" in held:
                bottom = max(min(1.0, bottom + down), top + LEAST)
            self.box = [left, top, right, bottom]
        self.changed.emit()
        self.update()

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt's name
        if self.trimming and self._holding:
            self._holding = ""
            self.changed.emit()
            self.update()
            return
        super().mouseReleaseEvent(event)

    # -------------------------------------------------------------- paint
    def paintEvent(self, event):  # noqa: N802 - Qt's name
        super().paintEvent(event)
        if not self.trimming:
            return
        picture, rect = self._picture(), self._box_rect()
        if picture.isNull() or rect.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        # What is being thrown away, dimmed; what is kept, plain.
        shade = QColor(0, 0, 0, 120)
        painter.fillRect(QRect(picture.left(), picture.top(), picture.width(),
                               rect.top() - picture.top()), shade)
        painter.fillRect(QRect(picture.left(), rect.bottom() + 1, picture.width(),
                               picture.bottom() - rect.bottom()), shade)
        painter.fillRect(QRect(picture.left(), rect.top(),
                               rect.left() - picture.left(), rect.height()), shade)
        painter.fillRect(QRect(rect.right() + 1, rect.top(),
                               picture.right() - rect.right(), rect.height()), shade)
        painter.setPen(QPen(QColor(theme.ORANGE), 2))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        # Thirds, the way a camera shows them - a help in placing a cutting.
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1))
        for step in (1, 2):
            x = rect.left() + rect.width() * step // 3
            y = rect.top() + rect.height() * step // 3
            painter.drawLine(x, rect.top(), x, rect.bottom())
            painter.drawLine(rect.left(), y, rect.right(), y)
        painter.setPen(QPen(QColor("#FFFFFF"), 1))
        painter.setBrush(QColor(theme.ORANGE))
        for x in (rect.left(), rect.center().x(), rect.right()):
            for y in (rect.top(), rect.center().y(), rect.bottom()):
                if x == rect.center().x() and y == rect.center().y():
                    continue
                painter.drawRect(QRect(x - 4, y - 4, 8, 8))
        painter.end()
