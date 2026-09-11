"""The cover page panel: two templates, chosen from a dropdown.

The department's newspad opens with the same cover every day, carrying only two
lines that change: how many clippings there are, and today's date. Option 1 keeps
that habit - the office artwork is chosen once for each newspad, remembered on this
machine, and the
two lines are composited onto it wherever the user clicks. Option 2 is for the days
there is no artwork: a blank A4 page built from a heading, a logo and a date.

Both previews call the same renderer the exporter calls, so what is on screen is
the page that comes out. That is the whole point of rendering the cover to a picture
in :mod:`clippings_manager.core.cover_render` rather than laying it out twice.

Every stylesheet rule here is scoped with an ``#objectName``: an unqualified
``border`` on a frame is inherited by every label inside it, which is what made the
earlier panels look boxed-in.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QDate, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFontMetricsF,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core import cover_render
from . import icons, theme
from .datefield import DayEdit, refuse_future  # noqa: F401
from .design_file import DesignFile

# The preview has to be big enough to read. A 24pt caption on a 1240px-wide
# scan is 30px tall - 1.7% of the page - so at the old 300px box it landed at
# about three pixels. These are the measured sizes at which the caption and
# the generated page's date become legible on a 96 DPI screen.
CANVAS_HEIGHT = 480
CANVAS_MAX_HEIGHT = 640
PREVIEW_HEIGHT = 560
# A QHBoxLayout's minimum is the plain sum of its children's - stretch factors
# have no say in it - so this number is added directly to the controls column's
# floor. The A4 sheet scales to whatever it is given, so it can afford to be the
# one that gives way.
PREVIEW_MIN_WIDTH = 260

SIZES_AVAILABLE = [14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 36, 40, 48]

TEXT_SIZES = [
    (14, "14pt (Compact)"), (16, "16pt"), (18, "18pt"), (20, "20pt"),
    (22, "22pt"), (24, "24pt (Standard)"), (26, "26pt"), (28, "28pt"),
    (30, "30pt"), (32, "32pt (Prominent)"), (36, "36pt"),
    (40, "40pt (Extra Large)"), (48, "48pt (Huge)"),
]

HEADING_SIZES = [
    (32, "32pt (Modest)"), (40, "40pt"), (48, "48pt (Standard Big)"),
    (56, "56pt"), (64, "64pt (Full Bleed)"), (72, "72pt"), (80, "80pt (Poster)"),
    (96, "96pt"), (112, "112pt"), (128, "128pt (Enormous)"),
]

DATE_SIZES = [
    (14, "14pt (Quiet)"), (16, "16pt"), (18, "18pt"),
    (20, "20pt (Prominent)"), (24, "24pt (Large)"), (28, "28pt"),
    (32, "32pt"), (40, "40pt"), (48, "48pt (Headline-sized)"),
]

LOGO_SIZES = [(120, "Small"), (180, "Medium"), (240, "Large"), (300, "Extra large")]

HEADING_COLOURS = ["#122A52", "#E8792F", "#111827", "#2563EB", "#9F1239"]

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp)"


def settings_dir() -> Path:
    """User settings live outside the program, so an update never wipes them."""
    import os
    import sys

    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    folder = base / "ClippingsManager"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _file() -> Path:
    return settings_dir() / "cover.json"


def icon_pixmap(name: str, colour: str, size: int = 15) -> QPixmap:
    """One of the painted icons as a pixmap, for putting inside a QLabel."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    drawer = getattr(icons, name, None)
    if drawer is not None:
        drawer(painter, QRectF(0, 0, size, size), QColor(colour))
    painter.end()
    return pixmap


def field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: #4B5563; font-size: 11px; font-weight: 700;"
        f" background: transparent; border: none;"
    )
    return label


def group_heading(text: str, icon: str) -> QWidget:
    """A small icon plus a bold caption - the header of one settings group."""
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    badge = QLabel()
    badge.setPixmap(icon_pixmap(icon, theme.ORANGE, 15))
    badge.setStyleSheet("background: transparent; border: none;")
    caption = QLabel(text)
    caption.setStyleSheet(
        f"color: {theme.NAVY}; font-size: 11px; font-weight: 800;"
        f" background: transparent; border: none;"
    )
    layout.addWidget(badge)
    layout.addWidget(caption)
    layout.addStretch(1)
    return row


_group_serial = 0


def group_box(title: str, icon: str) -> tuple[QFrame, QVBoxLayout]:
    """A pale rounded panel with a heading, for one cluster of settings."""
    global _group_serial
    _group_serial += 1
    name = f"CoverGroup{_group_serial}"
    frame = QFrame()
    frame.setObjectName(name)
    frame.setStyleSheet(
        f"#{name} {{ background: {theme.THUMB_BG};"
        f" border: 1px solid {theme.HAIRLINE}; border-radius: 12px; }}"
        f"#{name} > QLabel {{ background: transparent; border: none; }}"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(13, 10, 13, 12)
    layout.setSpacing(9)
    layout.addWidget(group_heading(title, icon))
    return frame, layout


def combo(items: list[tuple[int, str]], value: int) -> QComboBox:
    box = QComboBox()
    box.setCursor(Qt.PointingHandCursor)
    # A popup is a child of its combo, so an ancestor's unqualified
    # `background: transparent` would repaint it black. A widget's own sheet
    # outranks every ancestor's, which is the only placement that holds.
    box.setStyleSheet(theme.COMBO_POPUP)
    for number, label in items:
        box.addItem(label, number)
    index = box.findData(value)
    box.setCurrentIndex(index if index >= 0 else 0)
    return box


def line_edit(placeholder: str = "") -> QLineEdit:
    field = QLineEdit()
    field.setPlaceholderText(placeholder)
    return field


class Segmented(QWidget):
    """A row of mutually exclusive flat buttons - the browser's little toggles."""

    changed = Signal(str)

    def __init__(self, options, value=None, icon_only=False, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._options = list(options)
        self._value = value if value is not None else self._options[0][0]
        self._buttons: dict[str, QPushButton] = {}

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        for key, label in self._options:
            button = QPushButton("" if icon_only else label)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(28)
            if icon_only:
                button.setToolTip(label)
                button.setIconSize(QSize(15, 15))
            button.clicked.connect(
                lambda _checked=False, k=key: self.set_value(k, emit=True)
            )
            self._buttons[key] = button
            row.addWidget(button, 1)
        self._icon_only = icon_only
        self._restyle()

    def _restyle(self) -> None:
        for key, button in self._buttons.items():
            picked = key == self._value
            if picked:
                button.setStyleSheet(
                    f"QPushButton {{ background: {theme.NAVY}; color: white;"
                    f" border: 1px solid {theme.NAVY}; border-radius: 9px;"
                    f" font-size: 11px; font-weight: 800; padding: 4px 8px; }}"
                )
            else:
                button.setStyleSheet(
                    f"QPushButton {{ background: {theme.SURFACE}; color: #374151;"
                    f" border: 1px solid {theme.HAIRLINE_STRONG};"
                    f" border-radius: 9px; font-size: 11px; font-weight: 600;"
                    f" padding: 4px 8px; }}"
                    f"QPushButton:hover {{ background: {theme.PANEL}; }}"
                )
            if self._icon_only:
                name = {"left": "align_left", "center": "align_center",
                        "right": "align_right"}.get(key, "align_center")
                button.setIcon(
                    icon_pixmap(name, "#FFFFFF" if picked else "#374151", 15)
                )

    def value(self) -> str:
        return self._value

    def set_value(self, value: str, emit: bool = False) -> None:
        if value not in self._buttons:
            return
        self._value = value
        self._restyle()
        if emit:
            self.changed.emit(value)


class ColourChoice(QWidget):
    """White / Black for the caption ink, drawn the way the browser draws it."""

    changed = Signal(str)

    def __init__(self, value: str = "white", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._value = value
        self._buttons: dict[str, QPushButton] = {}

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        for key, label in (("white", "White"), ("black", "Black")):
            button = QPushButton(label)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(28)
            button.clicked.connect(
                lambda _checked=False, k=key: self.set_value(k, emit=True)
            )
            self._buttons[key] = button
            row.addWidget(button, 1)
        self._restyle()

    def _restyle(self) -> None:
        for key, button in self._buttons.items():
            picked = key == self._value
            ring = theme.ORANGE if picked else theme.HAIRLINE_STRONG
            width = 2 if picked else 1
            if key == "white":
                button.setStyleSheet(
                    f"QPushButton {{ background: #FFFFFF; color: #374151;"
                    f" border: {width}px solid {ring}; border-radius: 9px;"
                    f" font-size: 11px; font-weight: 700; padding: 4px 8px;"
                    f" text-align: center; }}"
                )
                button.setIcon(icon_pixmap("dot_hollow", "#9CA3AF", 13))
            else:
                button.setStyleSheet(
                    f"QPushButton {{ background: #111827; color: #FFFFFF;"
                    f" border: {width}px solid {ring}; border-radius: 9px;"
                    f" font-size: 11px; font-weight: 700; padding: 4px 8px;"
                    f" text-align: center; }}"
                )
                button.setIcon(icon_pixmap("dot_solid", "#FFFFFF", 13))

    def value(self) -> str:
        return self._value

    def set_value(self, value: str, emit: bool = False) -> None:
        if value not in self._buttons:
            return
        self._value = value
        self._restyle()
        if emit:
            self.changed.emit(value)


class Swatches(QWidget):
    """Round colour chips for the big heading."""

    changed = Signal(str)

    def __init__(self, colours: list[str], value: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._colours = colours
        self._value = value if value in colours else colours[0]
        self._chips: dict[str, QPushButton] = {}

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        for colour in colours:
            chip = QPushButton()
            chip.setCursor(Qt.PointingHandCursor)
            chip.setFixedSize(24, 24)
            chip.setToolTip(colour)
            chip.clicked.connect(
                lambda _checked=False, c=colour: self.set_value(c, emit=True)
            )
            self._chips[colour] = chip
            row.addWidget(chip)
        row.addStretch(1)
        self._restyle()

    def _restyle(self) -> None:
        for colour, chip in self._chips.items():
            picked = colour == self._value
            chip.setStyleSheet(
                f"QPushButton {{ background: {colour}; border-radius: 12px;"
                f" border: {'3px solid ' + theme.ORANGE if picked else '1px solid ' + theme.HAIRLINE_STRONG}; }}"
            )

    def value(self) -> str:
        return self._value

    def set_value(self, value: str, emit: bool = False) -> None:
        if value not in self._chips:
            return
        self._value = value
        self._restyle()
        if emit:
            self.changed.emit(value)


class CoverCanvas(QWidget):
    """The Option 1 preview: the artwork itself, with the caption drawn on top.

    The exported cover composites the caption at the artwork's own resolution - a
    24pt caption on a 1240px-wide scan comes out 30px tall, which is 1.7% of the
    page height. Scaling that finished picture down into a preview box left the
    text about three pixels high and unreadable, so the preview now shows the raw
    artwork and paints the caption itself at a size chosen for the screen.

    Nothing about the exported page changes. The badge is drawn from the marker
    downward, exactly where the real block starts, but at a size chosen to be read
    on screen rather than at true scale.
    """

    markerPlaced = Signal(float, float)
    #: The caption was stretched: the new text size, in points.
    sizeChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CoverCanvas")
        self.setMinimumHeight(CANVAS_HEIGHT)
        self.setMaximumHeight(CANVAS_MAX_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("#CoverCanvas { background: transparent; }")
        self._image: Optional[QImage] = None
        self._marker: Optional[cover_render.Marker] = None
        # Which part of the caption box is being held, if any, and where the
        # drag started. See _grab_at.
        self._holding = ""
        self._over = False
        self._from = None
        self._start_pt = 24
        # Where the box WAS when the mouse went down, and how wide it was.
        #
        # A drag has to be measured from where it began, not from the previous
        # event. The per-event form threw away every step whose repaint had not
        # landed - and with the repaint on a 140ms debounce, that was all of
        # them: measured, 119 of 120 steps lost and the box moving 0 pixels
        # while the pointer moved 120.
        self._start_marker = None
        self._start_width = 0.0
        self.setMouseTracking(True)
        self._text = cover_render.CoverText()
        self._count = 0
        self._date = date.today()
        self._empty = "No cover artwork chosen yet."
        self.setToolTip(
            "Click to place the date and clip count block.\n"
            "The dotted outline is the size it will print at."
        )
        self.setAccessibleName("Cover artwork preview")
        self._sync_cursor()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt name
        return QSize(560, CANVAS_HEIGHT)

    def has_artwork(self) -> bool:
        return self._image is not None and not self._image.isNull()

    def _sync_cursor(self) -> None:
        """A crosshair over an empty box invites a click that does nothing."""
        self.setCursor(Qt.CrossCursor if self.has_artwork() else Qt.ArrowCursor)

    def show_image(self, image: Optional[QImage],
                   marker: Optional[cover_render.Marker]) -> None:
        self._image = image
        self._marker = marker
        self._sync_cursor()
        self.update()

    def set_caption(self, text: cover_render.CoverText, count: int,
                    report_date: date) -> None:
        self._text = text
        self._count = count
        self._date = report_date
        self.update()

    def set_empty_text(self, text: str) -> None:
        self._empty = text
        self.update()

    def _lines(self) -> list[str]:
        return [
            f"NUMBER OF CLIPPINGS: {self._count}",
            f"DATE: {self._date.strftime('%d.%m.%Y')}",
        ]

    #: How near a corner counts as grabbing it rather than the box.
    GRIP = 10

    def caption_rect(self, target: QRectF) -> Optional[QRectF]:
        """Where the caption sits on screen, from the same arithmetic the page
        uses - so the box being dragged is the box that prints."""
        if self._image is None or self._image.isNull():
            return None
        box = cover_render.caption_box(
            self._marker, self._text, self._count, self._date,
            self._image.width(), self._image.height())
        scale = target.width() / max(1, self._image.width())
        return QRectF(target.left() + box.left() * scale,
                      target.top() + box.top() * scale,
                      box.width() * scale, box.height() * scale)

    def _corners(self, box: QRectF) -> dict:
        half = self.GRIP / 2
        return {
            "tl": QRectF(box.left() - half, box.top() - half, self.GRIP, self.GRIP),
            "tr": QRectF(box.right() - half, box.top() - half, self.GRIP, self.GRIP),
            "bl": QRectF(box.left() - half, box.bottom() - half, self.GRIP, self.GRIP),
            "br": QRectF(box.right() - half, box.bottom() - half, self.GRIP, self.GRIP),
        }

    def _draw_caption(self, painter: QPainter, target: QRectF) -> None:
        """The caption as a box that can be taken hold of.

        It used to be a solid dark badge that could only be re-placed by
        clicking somewhere else, which is a strange way to move something. It is
        drawn as a frame now - see through, so the artwork underneath it can be
        judged - and it is dragged, and stretched by its corners.
        """
        box = self.caption_rect(target)
        if box is None:
            return
        lines = self._lines()
        white = str(self._text.colour).strip().lower() != "black"
        active = self._holding or self._over

        # A wash rather than a solid fill: dark enough to keep the text legible
        # over a light patch of artwork, light enough to see what is behind it.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 90) if white
                         else QColor(255, 255, 255, 150))
        painter.drawRoundedRect(box, 5, 5)

        edge = QPen(QColor(theme.ORANGE) if active else QColor(255, 255, 255, 170),
                    1.5 if active else 1.0)
        if not active:
            edge.setStyle(Qt.DashLine)
            edge.setDashPattern([4, 3])
        painter.setPen(edge)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(box, 5, 5)

        px = max(7, round(box.height() / (len(lines) * 1.55)))
        font = cover_render.preview_font(px, 700 if self._text.bold else 400)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF") if white else QColor("#111111"))
        line_height = box.height() / len(lines)
        for index, line in enumerate(lines):
            painter.drawText(
                QRectF(box.left() + 4, box.top() + line_height * index,
                       box.width() - 8, line_height),
                Qt.AlignVCenter | Qt.AlignHCenter, line,
            )

        # The corners are only drawn when the box is being pointed at, so a
        # preview nobody is touching still shows the cover rather than furniture.
        if active:
            painter.setPen(QPen(QColor(theme.ORANGE), 1.2))
            painter.setBrush(QColor("#FFFFFF"))
            for handle in self._corners(box).values():
                painter.drawRect(handle)

    def _target(self) -> Optional[QRectF]:
        if self._image is None or self._image.isNull():
            return None
        area = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        scale = min(area.width() / self._image.width(),
                    area.height() / self._image.height())
        width = self._image.width() * scale
        height = self._image.height() * scale
        return QRectF(area.center().x() - width / 2,
                      area.center().y() - height / 2, width, height)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        target = self._target()

        # The dashed frame hugs the artwork. Drawn around the whole widget it
        # left a portrait cover marooned in a very wide empty letterbox, which
        # read as a broken preview.
        frame = (QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
                 if target is None else target.adjusted(-8, -8, 8, 8))
        pen = QPen(theme.QHAIRLINE_STRONG)
        pen.setStyle(Qt.DashLine)
        pen.setDashPattern([4, 4])
        painter.setPen(pen)
        painter.setBrush(QColor(theme.THUMB_BG))
        painter.drawRoundedRect(frame, 12, 12)

        if target is None:
            painter.setPen(QColor(theme.MUTED))
            painter.drawText(
                QRectF(self.rect()).adjusted(24, 12, -24, -12),
                Qt.AlignCenter | Qt.TextWordWrap, self._empty,
            )
            painter.end()
            return

        painter.drawImage(target, self._image)
        self._draw_caption(painter, target)
        painter.end()

    def _grab_at(self, point) -> str:
        """What is under the pointer: a corner, the box itself, or nothing."""
        target = self._target()
        if target is None:
            return ""
        box = self.caption_rect(target)
        if box is None:
            return ""
        for name, handle in self._corners(box).items():
            if handle.contains(point):
                return name
        return "move" if box.adjusted(-2, -2, 2, 2).contains(point) else ""

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt name
        target = self._target()
        if target is None or not target.contains(event.position()):
            return
        self._holding = self._grab_at(event.position())
        self._from = event.position()
        if self._holding:
            self._start_pt = int(self._text.font_pt)
            self._start_marker = self._marker or cover_render.Marker(50.0, 84.0)
            box = self.caption_rect(target)
            # Frozen for the whole gesture. Read fresh, it is a function of the
            # type size, which is the thing the pull is changing - size to width
            # to divisor to size, a loop that oscillates instead of growing.
            self._start_width = float(box.width()) if box is not None else 0.0
            self.update()
            return
        # Nothing under the pointer: put the caption here. Clicking an empty
        # part of the artwork is still the quickest way to move it a long way.
        x_pct = (event.position().x() - target.left()) / target.width() * 100
        y_pct = (event.position().y() - target.top()) / target.height() * 100
        self.markerPlaced.emit(
            min(100.0, max(0.0, x_pct)), min(100.0, max(0.0, y_pct))
        )

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt name
        target = self._target()
        if target is None:
            return
        if not self._holding:
            over = bool(self._grab_at(event.position()))
            if over != self._over:
                self._over = over
                self.update()
            self.setCursor(Qt.SizeAllCursor if over else Qt.CrossCursor)
            return

        if self._holding == "move":
            # Total travel since the press, against the marker as it was then.
            began = self._start_marker or cover_render.Marker(50.0, 84.0)
            moved = event.position() - self._from
            dx = moved.x() / target.width() * 100
            dy = moved.y() / target.height() * 100
            x_pct = min(100.0, max(0.0, began.x_pct + dx))
            y_pct = min(100.0, max(0.0, began.y_pct + dy))
            # Drawn NOW, on this frame. Waiting for the debounced re-render of
            # the whole cover is what made the box sit still under the pointer.
            self._marker = cover_render.Marker(x_pct=x_pct, y_pct=y_pct)
            self.update()
            self.markerPlaced.emit(x_pct, y_pct)
            return

        # A corner. How far it was dragged along the box's diagonal, as a share
        # of the box, is how much bigger the type becomes - which is what makes
        # stretching the frame and choosing a size the same fact told two ways.
        # The width as it was at the press, not as it is now. See _start_width.
        width = self._start_width
        if width < 1:
            box = self.caption_rect(target)
            if box is None or box.width() < 1:
                return
            width = float(box.width())
        # Both axes, so a corner behaves like a corner. Dragging AWAY from the
        # box grows it, whichever corner is held - which means each axis is read
        # in the direction that corner points. Reading only x, as this used to,
        # made the top-right and bottom-left corners feel dead when pulled the
        # way they look like they should be pulled.
        sideways = -1.0 if self._holding in ("tl", "bl") else 1.0
        upright = -1.0 if self._holding in ("tl", "tr") else 1.0
        pull = (sideways * (event.position().x() - self._from.x())
                + upright * (event.position().y() - self._from.y())) / 2.0
        wanted = self._start_pt * (1 + pull / max(40.0, width))
        self.sizeChanged.emit(int(round(max(8, min(72, wanted)))))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt name
        if self._holding:
            self._holding = ""
            self._start_marker = None
            self._start_width = 0.0
            self.update()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt name
        if self._over:
            self._over = False
            self.update()
        super().leaveEvent(event)


class PagePreview(QLabel):
    """The Option 2 preview: the real rendered page, as large as it will go.

    A QLabel's size hint is its pixmap, so scaling to the label's own height
    pinned the page at whatever it was first drawn at - it never grew with the
    window and never re-scaled on resize. The source image is kept instead, and
    both dimensions are used.
    """

    BASE_STYLE = (
        f"#PagePreview {{ background: {theme.THUMB_BG};"
        f" border: 1px solid {theme.HAIRLINE}; border-radius: 12px;"
        f" color: {theme.MUTED}; font-size: 11px; }}"
    )
    ERROR_STYLE = (
        f"#PagePreview {{ background: {theme.RED_WASH};"
        f" border: 1px solid {theme.RED}; border-radius: 12px;"
        f" color: {theme.RED}; font-size: 12px; font-weight: 600; }}"
    )

    # Dragged a block: which one, and how far, in per cent of the sheet.
    moved = Signal(str, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PagePreview")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(PREVIEW_HEIGHT)
        self.setMinimumWidth(PREVIEW_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setWordWrap(True)
        self.setStyleSheet(self.BASE_STYLE)
        self.setMouseTracking(True)
        self._source: Optional[QImage] = None
        # Where each movable block sits on the sheet, in page pixels, so a click
        # can be matched to one. Empty until the card says otherwise, which is
        # what keeps Option 1 - a different preview entirely - unaffected.
        self._blocks: dict = {}
        self._dragging: str = ""
        self._from = None

    def set_blocks(self, blocks: dict) -> None:
        self._blocks = dict(blocks or {})
        self._sync_cursor()

    def _sheet(self):
        """Where the page is drawn inside this widget, and at what scale."""
        picture = self.pixmap()
        if self._source is None or picture is None or picture.isNull():
            return None
        scale = picture.width() / max(1, self._source.width())
        left = (self.width() - picture.width()) / 2
        top = (self.height() - picture.height()) / 2
        return left, top, scale

    def _at(self, point):
        """The page-pixel position under this widget point, or None."""
        sheet = self._sheet()
        if sheet is None:
            return None
        left, top, scale = sheet
        if scale <= 0:
            return None
        return QPointF((point.x() - left) / scale, (point.y() - top) / scale)

    def _block_at(self, point) -> str:
        spot = self._at(point)
        if spot is None:
            return ""
        # Generous, because a line of text is a thin target on a preview a
        # quarter of the real size. Smallest block first, so a date sitting
        # inside the heading area is still reachable.
        for name, rect in sorted(self._blocks.items(),
                                 key=lambda kv: kv[1].width() * kv[1].height()):
            if rect.adjusted(-14, -14, 14, 14).contains(spot):
                return name
        return ""

    def _sync_cursor(self) -> None:
        self.setCursor(Qt.SizeAllCursor if self._blocks else Qt.ArrowCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt name
        if event.button() == Qt.LeftButton:
            self._dragging = self._block_at(event.position())
            self._from = self._at(event.position())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt name
        if self._dragging and self._from is not None:
            now = self._at(event.position())
            if now is not None:
                dx = (now.x() - self._from.x()) / cover_render.PAGE_WIDTH * 100
                dy = (now.y() - self._from.y()) / cover_render.PAGE_HEIGHT * 100
                if abs(dx) > 0.02 or abs(dy) > 0.02:
                    self._from = now
                    self.moved.emit(self._dragging, dx, dy)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt name
        self._dragging = ""
        self._from = None
        super().mouseReleaseEvent(event)

    def show_image(self, image: Optional[QImage]) -> None:
        self._source = None if image is None or image.isNull() else image
        if self._source is None:
            self.setPixmap(QPixmap())
            self.setStyleSheet(self.ERROR_STYLE)
            self.setText("The cover page could not be drawn.")
            return
        self.setStyleSheet(self.BASE_STYLE)
        self._rescale()

    def _rescale(self) -> None:
        if self._source is None:
            return
        self.setPixmap(
            QPixmap.fromImage(self._source).scaled(
                max(1, self.width() - 20), max(1, self.height() - 20),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt name
        super().resizeEvent(event)
        self._rescale()


class CoverCard(QFrame, DesignFile):
    """Cover artwork and page settings, with a live preview of the real cover.

    One newspad's own: which file it reads and writes is set by adopt(), and a
    bare CoverCard() is Newspad 1's, reading cover.json exactly as every older
    build does. See ui/design_file.py for the rules a switch depends on.
    """

    changed = Signal()
    designProblem = Signal(str)
    design_name = "cover.json"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.cover_path: str = ""
        self.template: int = 1
        self.marker: Optional[cover_render.Marker] = None
        self.text = cover_render.CoverText()
        self.option2 = cover_render.Option2()
        self._count = 0
        self._loading = False
        self._artwork_cache: tuple[str, Optional[QImage]] = ("", None)
        self._init_design()

        # Rendering the whole A4 page on every keystroke would make typing feel
        # sticky, so edits coalesce into one repaint.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(140)
        self._debounce.timeout.connect(self._repaint_preview)

        # Settings live in APPDATA, which is a roaming network profile in a lot
        # of offices - a synchronous write per keypress is felt while typing.
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self.save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 15)
        layout.setSpacing(11)
        layout.addLayout(self._build_header())

        self.body = QWidget()
        self.body.setObjectName("CoverBody")
        # Scoped: an unqualified rule here reaches every descendant, including
        # combo popups and calendar popups, which then paint black.
        self.body.setStyleSheet("#CoverBody { background: transparent; }")
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        body.addWidget(self._build_template_strip())

        self.pages = QStackedWidget()
        self.pages.setObjectName("CoverPages")
        self.pages.setStyleSheet("#CoverPages { background: transparent; }")
        self.pages.addWidget(self._build_option1())
        self.pages.addWidget(self._build_option2())
        # A stack is as tall as its tallest page unless the hidden ones are told
        # to stop asking for room, which left Option 1's rows spread down the
        # height of Option 2.
        self.pages.currentChanged.connect(self._fit_pages)
        body.addWidget(self.pages)
        layout.addWidget(self.body)

        self._fit_pages()
        self.load()
        self.set_count(0)

    # --------------------------------------------------------------- header
    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(9)
        step = QLabel("1")
        step.setObjectName("StepNumber")
        step.setFixedSize(24, 24)
        step.setAlignment(Qt.AlignCenter)
        title = QLabel("Cover Page Template")
        title.setObjectName("CardTitle")
        # Each newspad keeps its own cover - see _mark_what_is_whose, which
        # says so in the tooltip.
        self.saved_note = QLabel("(Optional / Per newspad)")
        self.saved_note.setObjectName("SubtleHint")
        header.addWidget(step)
        header.addWidget(title)
        header.addWidget(self.saved_note)
        header.addStretch(1)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setObjectName("CoverReset")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.setIcon(icon_pixmap("trash", theme.DANGER, 14))
        self.reset_btn.setToolTip("Clear the cover template and start again")
        self.reset_btn.setStyleSheet(
            f"#CoverReset {{ background: transparent; border: none;"
            f" color: {theme.DANGER}; font-size: 11px; font-weight: 700;"
            f" padding: 4px 6px; }}"
            f"#CoverReset:hover {{ color: #A21622; }}"
        )
        self.reset_btn.clicked.connect(self._reset)
        header.addWidget(self.reset_btn)

        self.collapse_btn = QPushButton("Collapse")
        self.collapse_btn.setObjectName("Quiet")
        self.collapse_btn.clicked.connect(self._toggle)
        header.addWidget(self.collapse_btn)
        return header

    def _build_template_strip(self) -> QWidget:
        strip = QFrame()
        strip.setObjectName("CoverTemplateStrip")
        strip.setStyleSheet(
            f"#CoverTemplateStrip {{ background: {theme.THUMB_BG};"
            f" border: 1px solid {theme.HAIRLINE}; border-radius: 12px; }}"
            f"#CoverTemplateStrip QLabel {{ background: transparent;"
            f" border: none; }}"
        )
        row = QHBoxLayout(strip)
        row.setContentsMargins(13, 10, 13, 10)
        row.setSpacing(12)

        column = QVBoxLayout()
        column.setSpacing(1)
        column.addWidget(group_heading("Cover Page Template Option:", "layers"))
        hint = QLabel(
            "Choose Option 1 for your custom image graphic, or Option 2 for a "
            "full-page big heading and centre logo."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6B7280; font-size: 11px;")
        column.addWidget(hint)
        row.addLayout(column, 1)

        self.template_pick = QComboBox()
        self.template_pick.setObjectName("CoverTemplatePick")
        self.template_pick.setCursor(Qt.PointingHandCursor)
        self.template_pick.addItem("Option 1: Standard Cover Image", 1)
        self.template_pick.addItem(
            "Option 2: Blank Page with Big Heading & Centre Logo", 2
        )
        self.template_pick.setStyleSheet(
            f"#CoverTemplatePick {{ background: {theme.SURFACE};"
            f" border: 2px solid {theme.NAVY}; border-radius: 11px;"
            f" padding: 6px 12px; color: {theme.NAVY}; font-size: 11px;"
            f" font-weight: 800; min-width: 180px; }}"
            f"#CoverTemplatePick::drop-down {{ border: none; width: 22px; }}"
            f"#CoverTemplatePick QAbstractItemView {{ background: {theme.SURFACE};"
            f" border: 1px solid {theme.HAIRLINE}; border-radius: 10px;"
            f" selection-background-color: {theme.NAVY_WASH};"
            f" selection-color: {theme.NAVY}; padding: 4px; }}"
        )
        self.template_pick.currentIndexChanged.connect(self._template_picked)
        row.addWidget(self.template_pick, 0, Qt.AlignVCenter)
        return strip

    # ------------------------------------------------------------- option 1
    def _build_option1(self) -> QWidget:
        """Preview on the left, settings on the right - the same arrangement as
        Option 2, so switching template does not rearrange the whole panel."""
        page = QWidget()
        page.setObjectName("CoverPage1")
        page.setStyleSheet("#CoverPage1 { background: transparent; }")
        spread = QHBoxLayout(page)
        spread.setContentsMargins(0, 0, 0, 0)
        spread.setSpacing(16)

        # ---------------------------------------------------- the artwork
        preview = QWidget()
        preview.setObjectName("CoverPage1Preview")
        preview.setStyleSheet("#CoverPage1Preview { background: transparent; }")
        left = QVBoxLayout(preview)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(7)

        # The hint travels with the thing it is about.
        self.place_hint = QWidget()
        self.place_hint.setObjectName("CoverPlaceHint")
        self.place_hint.setStyleSheet(
            "#CoverPlaceHint { background: transparent; }"
        )
        hint_row = QHBoxLayout(self.place_hint)
        hint_row.setContentsMargins(0, 0, 0, 0)
        hint_row.setSpacing(6)
        crosshair = QLabel()
        crosshair.setPixmap(icon_pixmap("crosshair", theme.ORANGE, 15))
        crosshair.setStyleSheet("background: transparent; border: none;")
        hint = QLabel("Drag the box to move it, or pull a corner to resize it")
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {theme.NAVY}; font-size: 11px; font-weight: 600;"
            f" background: transparent; border: none;"
        )
        hint_row.addWidget(crosshair)
        hint_row.addWidget(hint, 1)
        left.addWidget(self.place_hint)

        self.canvas = CoverCanvas()
        self.canvas.markerPlaced.connect(self._marker_placed)
        self.canvas.sizeChanged.connect(self._caption_stretched)
        left.addWidget(self.canvas, 1)
        spread.addWidget(preview, 2)

        # ---------------------------------------------------- the settings
        holder = QWidget()
        holder.setObjectName("CoverPage1Controls")
        holder.setStyleSheet("#CoverPage1Controls { background: transparent; }")
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)

        blurb = QLabel(
            "Upload your standard cover page image with your brand or logo. Once "
            "chosen it is saved on this computer for this newspad."
        )
        blurb.setWordWrap(True)
        blurb.setStyleSheet(
            "color: #6B7280; font-size: 11px; background: transparent;"
            " border: none;"
        )
        column.addWidget(blurb)

        actions = QHBoxLayout()
        actions.setSpacing(9)
        self.choose_btn = QPushButton("Change Cover Image")
        self.choose_btn.setObjectName("CoverChoose")
        self.choose_btn.setCursor(Qt.PointingHandCursor)
        self.choose_btn.setIcon(icon_pixmap("image", theme.NAVY, 15))
        self.choose_btn.setStyleSheet(
            f"#CoverChoose {{ background: {theme.SURFACE};"
            f" border: 2px solid {theme.NAVY}; border-radius: 11px;"
            f" color: {theme.NAVY}; font-size: 12px; font-weight: 700;"
            f" padding: 7px 15px; }}"
            f"#CoverChoose:hover {{ background: {theme.NAVY_WASH}; }}"
        )
        self.choose_btn.clicked.connect(self._choose_cover)
        actions.addWidget(self.choose_btn)

        self.active_pill = QLabel("Option 1 template active")
        self.active_pill.setStyleSheet(
            f"color: {theme.GREEN}; background: {theme.GREEN_WASH};"
            f" border: none; border-radius: 8px; padding: 5px 10px;"
            f" font-size: 11px; font-weight: 700;"
        )
        actions.addWidget(self.active_pill)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setObjectName("Quiet")
        self.remove_btn.clicked.connect(self._clear_cover)
        actions.addWidget(self.remove_btn)
        actions.addStretch(1)
        column.addLayout(actions)

        rule = QFrame()
        rule.setObjectName("CoverRule")
        rule.setFixedHeight(1)
        rule.setStyleSheet(f"#CoverRule {{ background: {theme.HAIRLINE}; }}")
        column.addWidget(rule)

        column.addWidget(self._build_option1_controls())
        column.addStretch(1)
        spread.addWidget(holder, 3)
        return page

    def _build_option1_controls(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("CoverControls")
        panel.setStyleSheet(
            f"#CoverControls {{ background: {theme.THUMB_BG};"
            f" border: 1px solid {theme.HAIRLINE}; border-radius: 12px; }}"
            f"#CoverControls QLabel {{ background: transparent; border: none; }}"
        )
        grid = QGridLayout(panel)
        grid.setContentsMargins(13, 11, 13, 12)
        grid.setHorizontalSpacing(13)
        grid.setVerticalSpacing(6)

        date_head = QHBoxLayout()
        date_head.setSpacing(6)
        date_head.addWidget(field_label("Report Date"))
        date_head.addStretch(1)
        self.today_btn = QPushButton("Today")
        self.today_btn.setObjectName("CoverToday")
        self.today_btn.setCursor(Qt.PointingHandCursor)
        # ORANGE on the pale panel is 2.8:1; ORANGE_DEEP clears the floor and
        # leaves the brighter orange to mean hover.
        self.today_btn.setToolTip("Set the report date to today")
        self.today_btn.setStyleSheet(
            f"#CoverToday {{ background: transparent; border: none;"
            f" color: {theme.ORANGE_DEEP}; font-size: 10px; font-weight: 800; }}"
            f"#CoverToday:hover {{ color: {theme.ORANGE}; }}"
        )
        self.today_btn.clicked.connect(
            lambda: self.date_edit.setDate(QDate.currentDate())
        )
        date_head.addWidget(self.today_btn)
        grid.addLayout(date_head, 0, 0)

        self.date_edit = DayEdit(what="newspad")
        self.date_edit.dateChanged.connect(self._touch)
        grid.addWidget(self.date_edit, 1, 0)

        grid.addWidget(field_label("Text Size"), 0, 1)
        self.size_pick = combo(TEXT_SIZES, self.text.font_pt)
        self.size_pick.currentIndexChanged.connect(self._read_option1)
        grid.addWidget(self.size_pick, 1, 1)

        grid.addWidget(field_label("Font Weight"), 2, 0)
        self.weight_pick = Segmented(
            [("bold", "Bold"), ("regular", "Regular")],
            "bold" if self.text.bold else "regular",
        )
        self.weight_pick.changed.connect(lambda _v: self._read_option1())
        grid.addWidget(self.weight_pick, 3, 0)

        grid.addWidget(field_label("Text Colour"), 2, 1)
        self.ink_pick = ColourChoice(self.text.colour)
        self.ink_pick.changed.connect(lambda _v: self._read_option1())
        grid.addWidget(self.ink_pick, 3, 1)

        grid.addWidget(field_label("Alignment"), 4, 0, 1, 2)
        self.align_pick = Segmented(
            [("left", "Left"), ("center", "Centre"), ("right", "Right")],
            self.text.align, icon_only=True,
        )
        self.align_pick.changed.connect(lambda _v: self._read_option1())
        grid.addWidget(self.align_pick, 5, 0, 1, 2)

        # Two across rather than five: the column is now about a third of the
        # card, and five abreast left every control too narrow to read.
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowMinimumHeight(1, 30)
        grid.setRowMinimumHeight(3, 30)
        grid.setRowMinimumHeight(5, 30)
        return panel

    # ------------------------------------------------------------- option 2
    def _build_option2(self) -> QWidget:
        page = QWidget()
        page.setObjectName("CoverPage2")
        page.setStyleSheet("#CoverPage2 { background: transparent; }")
        # The page preview sits beside the controls rather than above them: the
        # controls only need about 840px of the card's width, and putting the A4
        # sheet in the leftover column makes it tall enough to read while making
        # the card shorter overall.
        spread = QHBoxLayout(page)
        spread.setContentsMargins(0, 0, 0, 0)
        spread.setSpacing(14)

        sheet = QVBoxLayout()
        sheet.setContentsMargins(0, 0, 0, 0)
        sheet.setSpacing(6)
        self.preview = PagePreview()
        self.preview.moved.connect(self._block_moved)
        sheet.addWidget(self.preview, 1)

        moving = QHBoxLayout()
        moving.setSpacing(8)
        drag_hint = QLabel("Drag the logo, the heading or the date to move it")
        drag_hint.setObjectName("CardHint")
        drag_hint.setWordWrap(True)
        moving.addWidget(drag_hint, 1)
        self.reset_positions_btn = QPushButton("Reset")
        self.reset_positions_btn.setObjectName("Quiet")
        self.reset_positions_btn.setToolTip(
            "Put the logo, the heading and the date back where the layout puts "
            "them.")
        self.reset_positions_btn.clicked.connect(self._reset_positions)
        moving.addWidget(self.reset_positions_btn)
        sheet.addLayout(moving)
        spread.addLayout(sheet, 2)

        holder = QWidget()
        holder.setObjectName("CoverOption2Controls")
        holder.setStyleSheet("#CoverOption2Controls { background: transparent; }")
        spread.addWidget(holder, 3)
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)

        logo_box, logo_layout = group_box("Centre Logo", "image")
        logo_row = QHBoxLayout()
        logo_row.setSpacing(9)
        self.logo_btn = QPushButton("Upload Centre Logo")
        self.logo_btn.setObjectName("CoverLogo")
        self.logo_btn.setCursor(Qt.PointingHandCursor)
        self.logo_btn.setIcon(icon_pixmap("upload_cloud", theme.ORANGE, 15))
        self.logo_btn.setStyleSheet(
            f"#CoverLogo {{ background: {theme.SURFACE};"
            f" border: 1.5px solid {theme.ORANGE}; border-radius: 10px;"
            f" color: {theme.ORANGE_DEEP}; font-size: 11px; font-weight: 700;"
            f" padding: 6px 13px; }}"
            f"#CoverLogo:hover {{ background: {theme.ORANGE_WASH}; }}"
        )
        self.logo_btn.clicked.connect(self._choose_logo)
        logo_row.addWidget(self.logo_btn)

        self.logo_clear = QPushButton("Remove")
        self.logo_clear.setObjectName("Quiet")
        self.logo_clear.clicked.connect(self._clear_logo)
        logo_row.addWidget(self.logo_clear)
        logo_row.addSpacing(8)
        logo_row.addWidget(field_label("Size"))
        self.logo_size = combo(LOGO_SIZES, self.option2.logo_size)
        self.logo_size.setFixedWidth(130)
        self.logo_size.currentIndexChanged.connect(self._read_option2)
        logo_row.addWidget(self.logo_size)
        logo_row.addStretch(1)
        logo_layout.addLayout(logo_row)
        column.addWidget(logo_box)

        head_box, head_layout = group_box(
            "Big Heading (Full Page Display)", "type_letter"
        )
        self.title_edit = QTextEdit()
        # Pasting a heading out of Word otherwise carries Word's formatting into
        # the box, so the field stops matching the page it is previewing.
        self.title_edit.setAcceptRichText(False)
        # A fixed 56px clipped the third line of a heading that renders fine.
        self.title_edit.setMinimumHeight(58)
        self.title_edit.setMaximumHeight(96)
        self.title_edit.setPlaceholderText("DAILY PRESS CLIPPINGS REPORT")
        self.title_edit.textChanged.connect(self._read_option2)
        head_layout.addWidget(self.title_edit)

        head_layout.addWidget(field_label("Sub-Heading / Organisation (Optional)"))
        self.subtitle_edit = line_edit("e.g. NORTHERN RAILWAY / CPRO OFFICE")
        self.subtitle_edit.textEdited.connect(lambda _t: self._read_option2())
        head_layout.addWidget(self.subtitle_edit)

        grid = QGridLayout()
        grid.setHorizontalSpacing(13)
        grid.setVerticalSpacing(6)
        grid.addWidget(field_label("Heading Size"), 0, 0)
        self.title_size = combo(HEADING_SIZES, self.option2.title_pt)
        self.title_size.currentIndexChanged.connect(self._read_option2)
        grid.addWidget(self.title_size, 1, 0)

        grid.addWidget(field_label("Font Weight"), 0, 1)
        self.title_weight = QComboBox()
        self.title_weight.setStyleSheet(theme.COMBO_POPUP)
        for key, label in (("normal", "Normal (500)"), ("bold", "Bold (700)"),
                           ("extra-bold", "Extra Bold (900)")):
            self.title_weight.addItem(label, key)
        self.title_weight.setCurrentIndex(1)
        self.title_weight.currentIndexChanged.connect(self._read_option2)
        grid.addWidget(self.title_weight, 1, 1)

        grid.addWidget(field_label("Heading Colour"), 0, 2)
        self.title_colour = Swatches(HEADING_COLOURS, self.option2.title_colour)
        self.title_colour.changed.connect(lambda _v: self._read_option2())
        grid.addWidget(self.title_colour, 1, 2)

        grid.addWidget(field_label("Alignment"), 0, 3)
        self.title_align = Segmented(
            [("left", "Left"), ("center", "Centre"), ("right", "Right")],
            self.option2.title_align, icon_only=True,
        )
        self.title_align.changed.connect(lambda _v: self._read_option2())
        grid.addWidget(self.title_align, 1, 3)
        for index in range(4):
            grid.setColumnStretch(index, 1)
        head_layout.addLayout(grid)
        column.addWidget(head_box)

        meta_box, meta_layout = group_box("Date & Report Metadata", "calendar")
        meta_row = QHBoxLayout()
        meta_row.setSpacing(13)

        date_column = QVBoxLayout()
        date_column.setSpacing(5)
        date_head = QHBoxLayout()
        date_head.setSpacing(6)
        date_head.addWidget(field_label("Report Date"))
        date_head.addStretch(1)
        self.today2_btn = QPushButton("Today")
        self.today2_btn.setObjectName("CoverToday2")
        self.today2_btn.setCursor(Qt.PointingHandCursor)
        self.today2_btn.setToolTip("Set the report date to today")
        self.today2_btn.setStyleSheet(
            f"#CoverToday2 {{ background: transparent; border: none;"
            f" color: {theme.ORANGE_DEEP}; font-size: 10px; font-weight: 800; }}"
            f"#CoverToday2:hover {{ color: {theme.ORANGE}; }}"
        )
        self.today2_btn.clicked.connect(
            lambda: self.date_mirror.setDate(QDate.currentDate())
        )
        date_head.addWidget(self.today2_btn)
        date_column.addLayout(date_head)
        self.date_mirror = DayEdit(what="newspad")
        self.date_mirror.dateChanged.connect(self._mirror_date)
        date_column.addWidget(self.date_mirror)
        meta_row.addLayout(date_column, 1)

        size_column = QVBoxLayout()
        size_column.setSpacing(5)
        size_column.addWidget(field_label("Date Size"))
        self.date_size = combo(DATE_SIZES, self.option2.date_pt)
        self.date_size.currentIndexChanged.connect(self._read_option2)
        size_column.addWidget(self.date_size)
        meta_row.addLayout(size_column, 1)

        self.show_count = QCheckBox("Show clip count badge")
        self.show_count.setChecked(True)
        self.show_count.toggled.connect(lambda _v: self._read_option2())
        meta_row.addWidget(self.show_count, 1, Qt.AlignBottom)
        meta_layout.addLayout(meta_row)
        column.addWidget(meta_box)

        back_box, back_layout = group_box(
            "Background Image & Framing (Optional)", "sparkles"
        )
        back_row = QHBoxLayout()
        back_row.setSpacing(9)
        self.background_btn = QPushButton("Add Background Image (Watermark)")
        self.background_btn.setObjectName("Quiet")
        self.background_btn.clicked.connect(self._choose_background)
        back_row.addWidget(self.background_btn)
        self.background_clear = QPushButton("Remove")
        self.background_clear.setObjectName("Quiet")
        self.background_clear.clicked.connect(self._clear_background)
        back_row.addWidget(self.background_clear)
        back_row.addStretch(1)
        self.show_border = QCheckBox("Decorative border frame")
        self.show_border.setChecked(True)
        self.show_border.toggled.connect(lambda _v: self._read_option2())
        back_row.addWidget(self.show_border)
        back_layout.addLayout(back_row)
        column.addWidget(back_box)
        column.addStretch(1)
        return page

    # ----------------------------------------------------------- behaviour
    def _fit_pages(self, *_args) -> None:
        """Only the option on show asks the card for room.

        A stacked layout takes the largest minimum across every page, shown or
        not - in both directions. Constraining only the vertical axis left the
        hidden Option 2, which needs 1021px, setting the width of the card while
        Option 1 was showing, and the overflow was cut off at the window edge
        with no way to reach it.
        """
        for index in range(self.pages.count()):
            page = self.pages.widget(index)
            policy = page.sizePolicy()
            showing = index == self.pages.currentIndex()
            policy.setVerticalPolicy(
                QSizePolicy.Preferred if showing else QSizePolicy.Ignored)
            policy.setHorizontalPolicy(
                QSizePolicy.Preferred if showing else QSizePolicy.Ignored)
            page.setSizePolicy(policy)
        self.pages.updateGeometry()

    def _toggle(self) -> None:
        # isVisibleTo, not isVisible: the latter is false whenever an ancestor is
        # hidden, which would make the first click expand an already-open card.
        showing = self.body.isVisibleTo(self)
        self.body.setVisible(not showing)
        self.collapse_btn.setText("Collapse" if not showing else "Expand")

    def _template_picked(self, index: int) -> None:
        self.template = self.template_pick.itemData(index) or 1
        self.pages.setCurrentIndex(0 if self.template == 1 else 1)
        self._touch()
        # At once, not on the debounce. The page just brought forward still shows
        # whatever it last drew - after a newspad switch, another report's cover
        # - and 140ms of that is long enough to be seen.
        if not self._loading:
            self._debounce.stop()
            self._repaint_preview()

    def _choose_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose the cover artwork", self.cover_path or "", IMAGE_FILTER
        )
        if path:
            self.cover_path = path
            self._artwork_cache = ("", None)
            self._touch()

    def _clear_cover(self) -> None:
        self.cover_path = ""
        self.marker = None
        self._artwork_cache = ("", None)
        self._touch()

    def _choose_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose the centre logo", self.option2.logo_path or "",
            IMAGE_FILTER,
        )
        if path:
            self.option2.logo_path = path
            self._touch()

    def _clear_logo(self) -> None:
        self.option2.logo_path = ""
        self._touch()

    def _choose_background(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose the background watermark",
            self.option2.background_path or "", IMAGE_FILTER,
        )
        if path:
            self.option2.background_path = path
            self._touch()

    def _clear_background(self) -> None:
        self.option2.background_path = ""
        self._touch()

    def _reset(self) -> None:
        """Back to a plain Option 1 with nothing chosen."""
        self._loading = True
        self.date_edit.setDate(QDate.currentDate())
        self.date_mirror.setDate(QDate.currentDate())
        self.cover_path = ""
        self.marker = None
        self.text = cover_render.CoverText()
        self.option2 = cover_render.Option2()
        self._artwork_cache = ("", None)
        self.template = 1
        self.template_pick.setCurrentIndex(0)
        self.pages.setCurrentIndex(0)
        self._write_widgets()
        self._loading = False
        self._touch()

    def _caption_stretched(self, points: int) -> None:
        """The caption box was pulled bigger or smaller on the preview.

        The box and the size are one fact told two ways, so stretching the frame
        moves the Text Size list and choosing from the list resizes the frame.
        Two controls that disagreed about the same thing would be worse than
        either of them alone.
        """
        wanted = min(SIZES_AVAILABLE, key=lambda size: abs(size - points))
        if wanted == self.text.font_pt:
            return
        self.text.font_pt = wanted
        at = self.size_pick.findData(wanted)
        if at >= 0:
            self._loading = True
            self.size_pick.setCurrentIndex(at)
            self._loading = False
        self._touch()
        self._debounce.stop()
        self._repaint_preview()

    def _marker_placed(self, x_pct: float, y_pct: float) -> None:
        self.marker = cover_render.Marker(x_pct=x_pct, y_pct=y_pct)
        self._touch()

    def _read_option1(self, *_args) -> None:
        if self._loading:
            return
        self.text = cover_render.CoverText(
            font_pt=int(self.size_pick.currentData() or 24),
            bold=self.weight_pick.value() == "bold",
            colour=self.ink_pick.value(),
            align=self.align_pick.value(),
        )
        self._touch()

    def _read_option2(self, *_args) -> None:
        if self._loading:
            return
        self.option2.logo_size = int(self.logo_size.currentData() or 180)
        self.option2.title = self.title_edit.toPlainText().strip()
        self.option2.subtitle = self.subtitle_edit.text().strip()
        self.option2.title_pt = int(self.title_size.currentData() or 48)
        self.option2.title_weight = self.title_weight.currentData() or "bold"
        self.option2.title_colour = self.title_colour.value()
        self.option2.title_align = self.title_align.value()
        self.option2.date_pt = int(self.date_size.currentData() or 20)
        self.option2.show_clip_count = self.show_count.isChecked()
        self.option2.show_border = self.show_border.isChecked()
        self._touch()

    def _mirror_date(self, value: QDate) -> None:
        """The two date pickers are one date shown twice."""
        if self._loading or self.date_edit.date() == value:
            return
        self.date_edit.setDate(value)

    def _touch(self, *_args) -> None:
        if self._loading:
            return
        if self.date_mirror.date() != self.date_edit.date():
            self._loading = True
            self.date_mirror.setDate(self.date_edit.date())
            self._loading = False
        # Only a change to the DESIGN is saved. The date comes through here too,
        # and it is the newspad's own value, kept in its session.
        self._changed_design()
        self._refresh_state()
        self._debounce.start()
        self.changed.emit()

    def set_count(self, count: int) -> None:
        self._count = count
        self._refresh_state()
        self._debounce.start()

    def _refresh_state(self) -> None:
        has_art = bool(self.cover_path and Path(self.cover_path).exists())
        self.remove_btn.setVisible(has_art)
        self.active_pill.setVisible(has_art)
        self.place_hint.setVisible(has_art)
        # Immediately, not on the debounced repaint: for 140ms after clearing the
        # artwork the canvas would otherwise still invite a click.
        self.canvas.setCursor(Qt.CrossCursor if has_art else Qt.ArrowCursor)
        self.choose_btn.setText(
            "Change Cover Image" if has_art else "Choose Cover Image"
        )
        self.logo_clear.setVisible(bool(self.option2.logo_path))
        self.background_clear.setVisible(bool(self.option2.background_path))
        self.background_btn.setText(
            "Change Background Image (Watermark)"
            if self.option2.background_path
            else "Add Background Image (Watermark)"
        )

    # ------------------------------------------------------------ rendering
    def _artwork(self) -> Optional[QImage]:
        """The chosen artwork, kept between repaints - decoding a 4 MB JPEG on
        every keystroke is what makes a preview feel slow."""
        if not self.cover_path or not Path(self.cover_path).exists():
            return None
        if self._artwork_cache[0] == self.cover_path:
            return self._artwork_cache[1]
        image = QImage(self.cover_path)
        self._artwork_cache = (self.cover_path, None if image.isNull() else image)
        return self._artwork_cache[1]

    def render_cover(self) -> Optional[QImage]:
        """The finished cover, exactly as the exporter will place it."""
        if self.template == 2:
            return cover_render.render_option2(
                self.option2, self._count, self.report_date()
            )
        artwork = self._artwork()
        if artwork is None:
            return None
        # Hand over the decoded image rather than the path: re-reading a large
        # office scan was 30ms of every repaint, and the cache existed only to
        # answer whether the file was there.
        return cover_render.render_option1(
            artwork, self.marker, self.text, self._count, self.report_date(),
        )

    def _block_moved(self, group: str, dx: float, dy: float) -> None:
        """A block was dragged on the preview. Nudge it and redraw.

        Held inside the sheet with a good margin: a block dragged off the edge
        would vanish from the report with nothing on screen to say where it
        went, and no way to get hold of it again.
        """
        pairs = {"logo": ("logo_dx", "logo_dy"),
                 "heading": ("title_dx", "title_dy"),
                 "date": ("date_dx", "date_dy")}
        names = pairs.get(group)
        if not names or self._loading:
            return
        for name, delta in zip(names, (dx, dy)):
            setattr(self.option2, name,
                    max(-45.0, min(45.0, getattr(self.option2, name) + delta)))
        self._touch()
        # Dragging wants to feel immediate, so the repaint that a keystroke
        # coalesces happens at once here.
        self._debounce.stop()
        self._repaint_preview()

    def _reset_positions(self) -> None:
        for name in ("logo_dx", "logo_dy", "title_dx", "title_dy",
                     "date_dx", "date_dy"):
            setattr(self.option2, name, 0.0)
        self._touch()
        self._debounce.stop()
        self._repaint_preview()

    def cover_blocks(self) -> list:
        """The option-2 cover as a layout, for the Word builder to set as text.

        Empty for Option 1, whose cover is the artwork the user supplied and has
        nothing to lay out.
        """
        try:
            if self.template == 2:
                return cover_render.blocks_option2(
                    self.option2, self._count, self.report_date())
            # Option 1 is the department's own artwork with the count and the
            # date on it. Word gets the artwork as a picture and those two lines
            # as a text box on top, so the numbers can be corrected there.
            return cover_render.blocks_option1(
                self.cover_path, self.marker, self.text, self._count,
                self.report_date())
        except Exception:  # noqa: BLE001 - a cover, not a crash
            return []

    def _repaint_preview(self) -> None:
        try:
            if self.template == 2:
                self.preview.show_image(self.render_cover())
                try:
                    self.preview.set_blocks(cover_render.bounds_option2(
                        self.option2, self._count, self.report_date()))
                except Exception:  # noqa: BLE001 - dragging is a convenience
                    self.preview.set_blocks({})
            else:
                # The canvas paints its own caption at a readable size, so it
                # wants the raw artwork - not the composite, whose caption would
                # be three pixels tall once scaled to fit.
                self.canvas.set_caption(self.text, self._count,
                                        self.report_date())
                self.canvas.show_image(self._artwork(), self.marker)
                self.canvas.set_empty_text(
                    "No cover artwork chosen yet - the report will open with a "
                    "plain page carrying the count and the date."
                )
        except Exception:  # noqa: BLE001 - a preview must never break the app
            if self.template == 2:
                self.preview.show_image(None)
            else:
                self.canvas.show_image(None, None)

    # ---------------------------------------------------------------- values
    def report_date(self) -> date:
        return self.date_edit.date().toPython()

    def set_report_date(self, value) -> None:
        """Put a newspad's own press date back, without saving the design.

        Both pickers, because they are one date shown twice and setting only
        one leaves the other behind - measured, 02.09 against 08.09. Under
        _loading, because the mirror normally syncs inside _touch, which would
        also start the cover.json save - and cover.json holds no date.

        Never later than today: no report may be dated tomorrow.
        """
        today = date.today()
        if value is None or value > today:
            value = today
        wanted = QDate(value.year, value.month, value.day)
        self._loading = True
        try:
            self.date_edit.setDate(wanted)
            self.date_mirror.setDate(wanted)
        finally:
            self._loading = False
        self._refresh_state()
        self._debounce.start()

    def heading(self) -> str:
        """Only for the fallback path: Option 2 bakes its own heading."""
        return self.option2.title.strip() if self.template == 2 else ""

    def cover_image(self) -> Optional[str]:
        if self.cover_path and Path(self.cover_path).exists():
            return self.cover_path
        return None

    def rendered_cover(self, count: Optional[int] = None) -> Optional[str]:
        """Write the finished cover to a temporary PNG for the builders.

        Returns ``None`` when there is nothing to place - Option 1 with no artwork -
        and the caller then falls back to the plain cover page it has always drawn.
        """
        if count is not None:
            self._count = count
        try:
            image = self.render_cover()
        except Exception:  # noqa: BLE001
            return None
        if image is None or image.isNull():
            return None
        folder = Path(tempfile.gettempdir()) / "ClippingsManager"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "cover_page.png"
        return str(target) if image.save(str(target), "PNG") else None

    # -------------------------------------------------------------- storage
    def _state(self) -> dict:
        return {
            "template": self.template,
            "cover": self.cover_path,
            "heading": self.option2.title,
            "marker": (
                None if self.marker is None
                else {"x": self.marker.x_pct, "y": self.marker.y_pct}
            ),
            "text": {
                "font_pt": self.text.font_pt,
                "bold": self.text.bold,
                "colour": self.text.colour,
                "align": self.text.align,
            },
            # Every field of the layout, listed by the dataclass rather than by
            # hand: a setting added to Option2 and forgotten here is a setting
            # that silently fails to survive closing the application.
            "option2": asdict(self.option2),
        }

    # save(), flush(), load(), adopt() and hold() are DesignFile's: which
    # newspad's file this is, and when it may be written, are decided there.
    def _root_file(self) -> Path:
        return _file()

    def _design_state(self) -> dict:
        return self._state()

    def _repaint_now(self) -> None:
        self._debounce.stop()
        self._repaint_preview()

    def _take_design(self, data: dict) -> None:
        """Put a cover.json on the panel. Checked value by value, and all of it
        at once, so a bad value can never leave half of one newspad's cover and
        half of another's on screen."""
        def words(value, default=""):
            return value if isinstance(value, str) else default

        try:
            template = 2 if int(data.get("template", 1) or 1) == 2 else 1
        except (TypeError, ValueError):
            template = 1

        # Always reset. Keeping the marker when a file had none carried one
        # newspad's caption position into the next newspad's cover.
        marker = None
        spot = data.get("marker")
        if isinstance(spot, dict):
            try:
                marker = cover_render.Marker(
                    x_pct=min(100.0, max(0.0, float(spot["x"]))),
                    y_pct=min(100.0, max(0.0, float(spot["y"]))))
            except (KeyError, TypeError, ValueError):
                marker = None

        stored_text = data.get("text") if isinstance(data.get("text"), dict) else {}
        try:
            font_pt = int(stored_text.get("font_pt", 24))
        except (TypeError, ValueError):
            font_pt = 24
        align = stored_text.get("align")
        text = cover_render.CoverText(
            font_pt=font_pt,
            bold=bool(stored_text.get("bold", True)),
            colour=("black" if str(stored_text.get("colour", "white")).lower()
                    == "black" else "white"),
            align=align if align in ("left", "center", "right") else "center",
        )

        stored = data.get("option2") if isinstance(data.get("option2"), dict) else {}
        fresh = cover_render.Option2()
        for key, value in stored.items():
            if not hasattr(fresh, key) or value is None:
                continue
            default = getattr(fresh, key)
            if isinstance(default, bool):
                ok = isinstance(value, bool)
            elif isinstance(default, int):
                ok = isinstance(value, int) and not isinstance(value, bool)
            elif isinstance(default, float):
                ok = isinstance(value, (int, float)) and not isinstance(value, bool)
                value = float(value) if ok else value
            else:
                ok = isinstance(value, str)
            if ok:
                setattr(fresh, key, value)
        if fresh.title_align not in ("left", "center", "right"):
            fresh.title_align = "center"
        # An older settings file only knew one heading field.
        if not stored and words(data.get("heading")):
            fresh.title = data["heading"]

        was = self._loading
        self._loading = True
        try:
            self.cover_path = words(data.get("cover"))
            self.template = template
            self.marker = marker
            self.text = text
            self.option2 = fresh
            self._write_widgets()
        finally:
            self._loading = was
        self._refresh_state()
        self._debounce.start()

    def _write_widgets(self) -> None:
        """Push the loaded state onto the controls, without echoing back."""
        index = self.template_pick.findData(self.template)
        self.template_pick.setCurrentIndex(max(0, index))
        self.pages.setCurrentIndex(0 if self.template == 1 else 1)

        size = self.size_pick.findData(self.text.font_pt)
        self.size_pick.setCurrentIndex(size if size >= 0 else 5)
        self.weight_pick.set_value("bold" if self.text.bold else "regular")
        self.ink_pick.set_value(
            "black" if str(self.text.colour).lower() == "black" else "white"
        )
        self.align_pick.set_value(self.text.align)

        logo = self.logo_size.findData(self.option2.logo_size)
        self.logo_size.setCurrentIndex(logo if logo >= 0 else 1)
        self.title_edit.setPlainText(self.option2.title)
        self.subtitle_edit.setText(self.option2.subtitle)
        title_size = self.title_size.findData(self.option2.title_pt)
        self.title_size.setCurrentIndex(title_size if title_size >= 0 else 2)
        weight = self.title_weight.findData(self.option2.title_weight)
        self.title_weight.setCurrentIndex(weight if weight >= 0 else 1)
        if self.option2.title_colour not in HEADING_COLOURS:
            # Only a hand-edited settings file can get here; the palette on
            # screen is the palette, so fall back rather than show no selection.
            self.option2.title_colour = HEADING_COLOURS[0]
        self.title_colour.set_value(self.option2.title_colour)
        self.title_align.set_value(self.option2.title_align)
        date_size = self.date_size.findData(self.option2.date_pt)
        self.date_size.setCurrentIndex(date_size if date_size >= 0 else 3)
        self.show_count.setChecked(bool(self.option2.show_clip_count))
        self.show_border.setChecked(bool(self.option2.show_border))
