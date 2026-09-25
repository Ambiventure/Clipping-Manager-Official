"""Whether the OCR headline is shown, and the switch that decides it.

One setting, read wherever the OCR box is drawn - the row in the list and the
preview - and kept with the rest of the settings, so it is the same the next
time the program starts.

Only the FIELD is switched off. The duplicate check goes on reading every
picture regardless, because comparing two headlines is half of how it tells a
repeat from two stories that happen to share a photograph; and the search
still looks in what was read. Nothing is lost by turning it off, and turning it
back on shows every reading exactly as it was.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import (QEasingCurve, QRectF, QSize, Qt, QVariantAnimation,
                            Signal)
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import theme

#: Where it is kept among the settings.
SETTING = "ocr_headline"

#: The two colours the switch is asked to show: on is green, off is red.
ON = QColor("#16A34A")
OFF = QColor("#DC2626")

_on: Optional[bool] = None


def is_on() -> bool:
    """Whether the OCR box is shown. On unless somebody has turned it off."""
    global _on
    if _on is None:
        try:
            from .export_dialog import load_settings

            _on = bool(load_settings().get(SETTING, True))
        except Exception:  # noqa: BLE001 - no settings yet means the default
            _on = True
    return _on


def set_on(value: bool) -> None:
    """Remember it, for this run and the next."""
    global _on
    _on = bool(value)
    try:
        from .export_dialog import load_settings, save_settings

        save_settings({**load_settings(), SETTING: _on})
    except Exception:  # noqa: BLE001 - the switch still works for this run
        pass


def forget() -> None:
    """Read the setting again next time. For tests."""
    global _on
    _on = None


class SwitchRow(QWidget):
    """"OCR headline" and a switch, as one line of a menu.

    Painted, not built from a label and a button: a menu item made of widgets
    takes its colours from wherever it sits, and a button inside a menu grows a
    frame and a hover of its own - two edges and two highlights on one line.
    Painted, it is one row with one hover, drawn the same as the menu's own.

    The whole line is the target, and pressing it does NOT close the menu: the
    point of a switch is to see it change.
    """

    toggled = Signal(bool)

    TRACK_W = 46
    TRACK_H = 22
    KNOB = 16

    def __init__(self, text: str, on: bool, parent=None):
        super().__init__(parent)
        self.text = text
        self.on = bool(on)
        self._hover = False
        # Where the knob is, 0 (left, off) to 1 (right, on) - animated between.
        self._at = 1.0 if self.on else 0.0
        self._slide = QVariantAnimation(self)
        self._slide.setDuration(150)
        self._slide.setEasingCurve(QEasingCurve.OutCubic)
        self._slide.valueChanged.connect(self._moved)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip(
            "Show or hide the OCR headline - what was read off each picture - "
            "on every clipping and in the preview. The duplicate check reads "
            "the pictures either way.")

    # ------------------------------------------------------------- state
    def set_on(self, on: bool, animate: bool = True) -> None:
        on = bool(on)
        if on == self.on and not self._slide.state():
            self._at = 1.0 if on else 0.0
            self.update()
            return
        self.on = on
        self._slide.stop()
        if animate:
            self._slide.setStartValue(float(self._at))
            self._slide.setEndValue(1.0 if on else 0.0)
            self._slide.start()
        else:
            self._at = 1.0 if on else 0.0
            self.update()

    def _moved(self, value) -> None:
        self._at = float(value)
        self.update()

    # ------------------------------------------------------------ size
    def sizeHint(self) -> QSize:  # noqa: N802 - Qt's name
        return QSize(250, 34)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt's name
        return QSize(190, 34)

    # ----------------------------------------------------------- input
    def enterEvent(self, event):  # noqa: N802 - Qt's name
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 - Qt's name
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802 - Qt's name
        # Taken here, so the menu never sees the press and stays open.
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802 - Qt's name
        if event.button() == Qt.LeftButton and self.rect().contains(
                event.position().toPoint()):
            self.set_on(not self.on)
            self.toggled.emit(self.on)
        event.accept()

    def keyPressEvent(self, event):  # noqa: N802 - Qt's name
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.set_on(not self.on)
            self.toggled.emit(self.on)
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------- paint
    def _track(self) -> QRectF:
        return QRectF(self.width() - 14 - self.TRACK_W,
                      (self.height() - self.TRACK_H) / 2,
                      self.TRACK_W, self.TRACK_H)

    def paintEvent(self, event):  # noqa: N802 - Qt's name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        whole = QRectF(self.rect())
        # The menu's own hover, so this line lights up like the others do.
        if self._hover:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.NAVY_SELECT))
            painter.drawRoundedRect(whole.adjusted(0, 1, 0, -1), 8, 8)

        font = QFont(self.font())
        font.setPixelSize(12)
        painter.setFont(font)
        painter.setPen(QColor(theme.NAVY) if self._hover else QColor(theme.INK))
        track = self._track()
        painter.drawText(QRectF(14, 0, track.left() - 22, self.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, self.text)

        # The track: green when on, red when off, the colour moving with the
        # knob so the two never disagree half way through the slide.
        colour = QColor(
            int(OFF.red() + (ON.red() - OFF.red()) * self._at),
            int(OFF.green() + (ON.green() - OFF.green()) * self._at),
            int(OFF.blue() + (ON.blue() - OFF.blue()) * self._at))
        painter.setPen(Qt.NoPen)
        painter.setBrush(colour)
        radius = track.height() / 2
        painter.drawRoundedRect(track, radius, radius)

        small = QFont(font)
        small.setPixelSize(9)
        small.setBold(True)
        painter.setFont(small)
        painter.setPen(QColor(255, 255, 255, 235))
        if self._at >= 0.5:
            painter.drawText(QRectF(track.left() + 6, track.top(),
                                    track.width() / 2, track.height()),
                             Qt.AlignVCenter | Qt.AlignLeft, "ON")
        else:
            painter.drawText(QRectF(track.center().x() - 3, track.top(),
                                    track.width() / 2 - 3, track.height()),
                             Qt.AlignVCenter | Qt.AlignRight, "OFF")

        travel = track.width() - self.KNOB - 6
        knob = QRectF(track.left() + 3 + travel * self._at,
                      track.center().y() - self.KNOB / 2, self.KNOB, self.KNOB)
        painter.setBrush(QColor("#FFFFFF"))
        painter.setPen(QColor(0, 0, 0, 30))
        painter.drawEllipse(knob)
        painter.end()
