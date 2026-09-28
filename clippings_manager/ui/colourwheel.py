"""A colour wheel: the colour chosen by where it is on a circle.

Round, as asked for (2.0.62) - the colour dialog Qt has is a square field and
a strip, which is a different thing to point at. Around the circle runs the
hue, from the middle out the strength of it, and the bar under the circle sets
how light or dark it is. Painted from three gradients, so it is exactly the
colour under the pointer: a hue ring, white fading out from the middle, and
black laid over the whole at the darkness the bar asks for.

And the one colour the program keeps from it today: the frame round a
clipping's picture in the preview when that clipping is selected in the list.
Kept in the shared export settings (export.json), which every writer merges
into and a saved setup carries - never in display.json, which the zoom writes
over whole.
"""

from __future__ import annotations

import math
import re

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QConicalGradient, QLinearGradient, QPainter,
                           QPen, QRadialGradient)
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import theme

#: Where the frame's colour is kept, and what it is until somebody changes it.
OUTLINE_KEY = "preview_selected_outline"
OUTLINE_DEFAULT = theme.HIGHLIGHT
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def outline_colour() -> str:
    """The frame's colour, as #RRGGBB - yellow unless it was changed."""
    try:
        from .export_dialog import load_settings

        said = str(load_settings().get(OUTLINE_KEY, "") or "")
    except Exception:  # noqa: BLE001 - no settings yet is the default
        return OUTLINE_DEFAULT
    return said.upper() if _HEX.match(said) else OUTLINE_DEFAULT


def set_outline_colour(colour: str) -> str:
    """Keep the frame's colour. Returns what was kept."""
    wanted = str(colour or "").strip()
    wanted = wanted.upper() if _HEX.match(wanted) else OUTLINE_DEFAULT
    try:
        from .export_dialog import load_settings, save_settings

        save_settings({**load_settings(), OUTLINE_KEY: wanted})
    except Exception:  # noqa: BLE001 - a preference, never a crash
        pass
    return wanted


class ColourWheel(QWidget):
    """The wheel and, under it, the bar for how light or dark.

    ``changed`` goes on every move, for showing the colour as it is chosen;
    ``picked`` once the button is let go, which is when it is kept.
    """

    changed = Signal(QColor)
    picked = Signal(QColor)

    WHEEL = 176
    BAR = 16
    GAP = 14
    #: Room round the wheel for the marker, which is drawn over the rim.
    MARGIN = 10

    def __init__(self, colour: str = OUTLINE_DEFAULT, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # Never squeezed: the wheel and the bar are drawn at fixed places.
        self.setMinimumSize(self.sizeHint())
        self._dragging = ""            # "wheel", "bar" or nothing
        start = QColor(colour)
        if not start.isValid():
            start = QColor(OUTLINE_DEFAULT)
        hue, sat, val, _alpha = start.getHsvF()
        self._hue = max(0.0, hue)      # -1 for a grey: any hue will do
        self._sat, self._val = sat, val

    # ----------------------------------------------------------- the colour
    def colour(self) -> QColor:
        return QColor.fromHsvF(self._hue, self._sat, self._val)

    def set_colour(self, colour) -> None:
        """Show this colour, without saying anything."""
        chosen = QColor(colour)
        if not chosen.isValid():
            return
        hue, sat, val, _alpha = chosen.getHsvF()
        if hue >= 0:
            self._hue = hue
        self._sat, self._val = sat, val
        self.update()

    # ------------------------------------------------------------- geometry
    def sizeHint(self) -> QSize:  # noqa: N802 - Qt name
        return QSize(self.WHEEL + 2 * self.MARGIN,
                     self.WHEEL + self.GAP + self.BAR + 2 * self.MARGIN)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt name
        return self.sizeHint()

    def _wheel_rect(self) -> QRectF:
        return QRectF(self.MARGIN, self.MARGIN, self.WHEEL, self.WHEEL)

    def _bar_rect(self) -> QRectF:
        return QRectF(self.MARGIN, self.MARGIN + self.WHEEL + self.GAP,
                      self.WHEEL, self.BAR)

    def _from_wheel(self, point) -> None:
        rect = self._wheel_rect()
        centre = rect.center()
        dx, dy = point.x() - centre.x(), centre.y() - point.y()
        radius = rect.width() / 2.0
        # Anticlockwise from three o'clock, as the conical gradient runs.
        self._hue = (math.degrees(math.atan2(dy, dx)) % 360.0) / 360.0
        self._sat = min(1.0, math.hypot(dx, dy) / radius)
        # A colour picked on a black wheel would stay black: pointing at the
        # wheel means a colour is wanted, so it is brought up to be seen.
        if self._val < 0.15:
            self._val = 1.0

    def _from_bar(self, point) -> None:
        rect = self._bar_rect()
        self._val = min(1.0, max(0.0, (point.x() - rect.left()) / rect.width()))

    # ---------------------------------------------------------------- mouse
    def mousePressEvent(self, event):  # noqa: N802 - Qt name
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        point = event.position()
        rect = self._wheel_rect()
        if math.hypot(point.x() - rect.center().x(),
                      point.y() - rect.center().y()) <= rect.width() / 2.0 + 2:
            self._dragging = "wheel"
            self._from_wheel(point)
        elif self._bar_rect().adjusted(-4, -6, 4, 6).contains(point):
            self._dragging = "bar"
            self._from_bar(point)
        else:
            return super().mousePressEvent(event)
        self.update()
        self.changed.emit(self.colour())

    def mouseMoveEvent(self, event):  # noqa: N802 - Qt name
        if not self._dragging:
            return super().mouseMoveEvent(event)
        if self._dragging == "wheel":
            self._from_wheel(event.position())
        else:
            self._from_bar(event.position())
        self.update()
        self.changed.emit(self.colour())

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt name
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = ""
            self.picked.emit(self.colour())
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):  # noqa: N802 - Qt name
        # Never the wheel's: the dialog it sits in scrolls on it (see the
        # rule that no control may take the mouse wheel).
        event.ignore()

    # ---------------------------------------------------------------- paint
    def paintEvent(self, _event):  # noqa: N802 - Qt name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self._wheel_rect()
        centre = rect.center()

        ring = QConicalGradient(centre, 0.0)
        for step in range(7):
            ring.setColorAt(step / 6.0, QColor.fromHsvF((step % 6) / 6.0, 1.0, 1.0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(ring)
        painter.drawEllipse(rect)
        # Strength: white in the middle, fading out to the pure hue at the rim.
        middle = QRadialGradient(centre, rect.width() / 2.0)
        middle.setColorAt(0.0, QColor(255, 255, 255, 255))
        middle.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(middle)
        painter.drawEllipse(rect)
        # Lightness: the whole wheel darkened as far as the bar says.
        painter.setBrush(QColor(0, 0, 0, int(round((1.0 - self._val) * 255))))
        painter.drawEllipse(rect)
        painter.setPen(QPen(QColor(theme.HAIRLINE_STRONG), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(rect)

        # Where the colour is, on the wheel.
        radius = rect.width() / 2.0
        angle = math.radians(self._hue * 360.0)
        spot = QPointF(centre.x() + math.cos(angle) * self._sat * radius,
                       centre.y() - math.sin(angle) * self._sat * radius)
        painter.setPen(QPen(QColor("#FFFFFF"), 3))
        painter.setBrush(self.colour())
        painter.drawEllipse(spot, 7, 7)
        painter.setPen(QPen(QColor(theme.INK), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(spot, 8.5, 8.5)

        # The bar: from black to the colour at full lightness.
        bar = self._bar_rect()
        shade = QLinearGradient(bar.topLeft(), bar.topRight())
        shade.setColorAt(0.0, QColor(0, 0, 0))
        shade.setColorAt(1.0, QColor.fromHsvF(self._hue, self._sat, 1.0))
        painter.setPen(QPen(QColor(theme.HAIRLINE_STRONG), 1))
        painter.setBrush(shade)
        painter.drawRoundedRect(bar, bar.height() / 2.0, bar.height() / 2.0)
        x = bar.left() + self._val * bar.width()
        knob = QRectF(x - 6, bar.top() - 3, 12, bar.height() + 6)
        painter.setPen(QPen(QColor(theme.INK), 1.2))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(knob, 4, 4)
        painter.end()
