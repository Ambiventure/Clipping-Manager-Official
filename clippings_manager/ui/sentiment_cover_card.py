"""The sentiment dossier's cover sheet, and the panel that designs it.

A division dossier opens with a blank sheet carrying the Indian Railways emblem, the
division's name, the report title, the date and the clipping count. Only two of those
change from day to day, so the rest is set once and remembered on this machine.

The date and the count are the awkward part: every office wants them somewhere
slightly different, and describing a position in words is hopeless. So they are
dragged straight onto the A4 sheet in the preview, or dropped by clicking it.

The preview is not an impression of the page - it is the page, rendered by
:func:`clippings_manager.core.sentiment_cover.render` at a smaller scale. The only
difference between what is on screen and what prints is the scale factor.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QDate, QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..core import sentiment_cover
from . import icons, theme
from .cover_card import icon_pixmap, settings_dir

PREVIEW_SCALE = 0.665            # A4 at this scale is 396 x 560, which fits the panel
SHEET_MIN_WIDTH = 300

DATE_PRESETS = [
    ("Centre", None),
    ("Top-Left", (23, 8)),
    ("Top-Right", (77, 8)),
    ("Bottom-Left", (23, 92)),
    ("Bottom-Right", (77, 92)),
]

COUNT_PRESETS = [
    ("Centre", None),
    ("Top-Left", (22, 8)),
    ("Top-Right", (78, 8)),
    ("Bottom-Left", (22, 92)),
    ("Bottom-Centre", (50, 92)),
]

BORDER_STYLES = [("none", "None"), ("classic", "Classic"),
                 ("modern", "Modern"), ("double", "Double")]

PRESET_NOTES = {
    "Official Division Dossier":
        "Formal Indian Railways format with division name, press compilation "
        "title and a classic border.",
    "Executive Sentiment Brief":
        "High-contrast maroon styling for DRM and ADRM executive tone "
        "assessment.",
    "Bilingual Hindi & English":
        "Full bilingual layout with Hindi and English titles for official "
        "departmental reporting.",
    "Clean Minimalist Sheet":
        "Uncluttered blank sheet with a crisp centre emblem and clean "
        "typography.",
}

PRESET_ICONS = {
    "Official Division Dossier": ("building", theme.NAVY),
    "Executive Sentiment Brief": ("layers", "#8B1E1E"),
    "Bilingual Hindi & English": ("file_text", "#B45309"),
    "Clean Minimalist Sheet": ("sparkles", "#4B5563"),
}

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.svg *.tif *.tiff *.webp)"


def _file() -> Path:
    return settings_dir() / "sentiment_cover.json"


#: The five values that belong to ONE MORNING rather than to the install. They
#: live in each newspad's own session now; sentiment_cover.json keeps only the
#: dossier's design. See legacy_morning for the one-time hand-over.
MORNING = ("iso_date", "date_text", "clip_count_text", "division_text",
           "prepared_by_text")
_MORNING_TEXT = MORNING[1:]


def legacy_morning():
    """The five morning values as an older build left them in the file.

    Read once, at startup, before the dossier card exists - because the moment
    it exists, any design save rewrites the file without them. Used only to hand
    Newspad 1 the date and division lines it had yesterday, the first time the
    new build opens it. None when the file is missing or never held them.
    """
    try:
        data = json.loads(_file().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - nothing saved, or not ours
        return None
    if not isinstance(data, dict):
        return None
    found = {key: data[key] for key in MORNING
             if key in data and data[key] is not None}
    return found or None


def small_label(text: str, colour: str = "#4B5563", size: int = 11,
                weight: int = 700, *, wrap: bool | None = None) -> QLabel:
    """A small caption. Anything sentence-length wraps rather than pin the card.

    A QLabel with wrap off reports its entire text as its minimum width, so one
    two-sentence caption in the Presets tab was setting the floor for the whole
    four-tab card - and a stacked layout takes the widest page whether it is
    showing or not.
    """
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {colour}; font-size: {size}px; font-weight: {weight};"
        f" background: transparent; border: none;"
    )
    label.setWordWrap(len(text) > 46 if wrap is None else wrap)
    return label


def caps_label(text: str) -> QLabel:
    label = small_label(text, "#6B7280", 10, 700)
    label.setStyleSheet(label.styleSheet() + " letter-spacing: .04em;")
    return label


_panel_serial = 0


def sub_panel() -> tuple[QFrame, QVBoxLayout]:
    """A pale rounded group inside a tab."""
    global _panel_serial
    _panel_serial += 1
    name = f"CoverSub{_panel_serial}"
    frame = QFrame()
    frame.setObjectName(name)
    frame.setStyleSheet(
        f"#{name} {{ background: {theme.THUMB_BG};"
        f" border: 1px solid {theme.HAIRLINE}; border-radius: 12px; }}"
    )
    column = QVBoxLayout(frame)
    column.setContentsMargins(13, 11, 13, 12)
    column.setSpacing(9)
    return frame, column


class SheetPreview(QWidget):
    """The A4 sheet: the real cover, drawn small, with two pills you can move."""

    placed = Signal(str, int, int)      # kind, x percent, y percent
    armedChanged = Signal(object)       # "date" | "count" | None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SentimentSheet")
        self.setStyleSheet("#SentimentSheet { background: transparent; }")
        self.setMinimumWidth(SHEET_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.setMouseTracking(True)

        self._image: Optional[QImage] = None
        self._boxes: dict[str, tuple[float, float, float, float]] = {}
        self._page = ("a4", 595.28, 841.89)
        self.armed: Optional[str] = None
        self.dragging: Optional[str] = None
        self.enabled_look = False

    # ------------------------------------------------------------ painting
    def show_cover(self, image: Optional[QImage], enabled: bool) -> None:
        self._image = None if image is None or image.isNull() else image
        self.enabled_look = enabled
        self._boxes = {}
        if self._image is not None:
            for kind in ("date", "count"):
                raw = self._image.text(f"{kind}_box")
                if raw:
                    try:
                        x, y, w, h = (float(v) for v in raw.split(","))
                        self._boxes[kind] = (x, y, w, h)
                    except ValueError:
                        pass
        self.update()

    def _target(self) -> Optional[QRectF]:
        if self._image is None:
            return None
        area = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        scale = min(area.width() / self._image.width(),
                    area.height() / self._image.height())
        width = self._image.width() * scale
        height = self._image.height() * scale
        return QRectF(area.center().x() - width / 2, area.top(), width, height)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        target = self._target()
        if target is None:
            painter.setPen(QColor(theme.MUTED))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "The cover sheet could not be drawn.")
            painter.end()
            return

        if not self.enabled_look:
            painter.setOpacity(0.6)
        painter.drawImage(target, self._image)
        painter.setOpacity(1.0)

        # A ring says the sheet is live: amber while a pill is waiting to be
        # placed, navy when the cover is switched on, nothing otherwise.
        if self.armed:
            painter.setPen(QColor("#FBBF24"))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(target.adjusted(-1.5, -1.5, 1.5, 1.5))
            painter.drawRect(target.adjusted(-2.5, -2.5, 2.5, 2.5))
        elif self.enabled_look:
            painter.setPen(QColor(18, 42, 82, 60))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(target.adjusted(-1.5, -1.5, 1.5, 1.5))

        # A dashed outline round whichever pill is under the pointer, so it is
        # discoverable that they can be dragged at all.
        under = self.dragging or self._pill_at(self.mapFromGlobal(QCursor.pos()))
        if under and under in self._boxes:
            rect = self._pill_rect(under, target)
            if rect is not None:
                pen = painter.pen()
                pen.setColor(QColor("#E8792F"))
                pen.setStyle(Qt.DashLine)
                pen.setWidthF(1.4)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 6, 6)
        painter.end()

    # ------------------------------------------------------------ geometry
    def _pill_rect(self, kind: str, target: QRectF) -> Optional[QRectF]:
        box = self._boxes.get(kind)
        if box is None:
            return None
        _, page_w, page_h = self._page
        x, y, w, h = box
        return QRectF(
            target.left() + x / page_w * target.width(),
            target.top() + y / page_h * target.height(),
            w / page_w * target.width(), h / page_h * target.height(),
        )

    def _pill_at(self, point: QPoint) -> Optional[str]:
        target = self._target()
        if target is None:
            return None
        for kind in ("date", "count"):
            rect = self._pill_rect(kind, target)
            if rect is not None and rect.adjusted(-3, -3, 3, 3).contains(point):
                return kind
        return None

    def _percent(self, point, kind: str) -> tuple[int, int]:
        target = self._target()
        x_pct = (point.x() - target.left()) / target.width() * 100
        y_pct = (point.y() - target.top()) / target.height() * 100
        return sentiment_cover.clamp_pill(kind, x_pct, y_pct, self._page[0])

    # -------------------------------------------------------------- input
    def arm(self, kind: Optional[str]) -> None:
        self.armed = kind
        self.setCursor(Qt.CrossCursor if kind else Qt.ArrowCursor)
        self.armedChanged.emit(kind)
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt name
        target = self._target()
        if target is None or not target.contains(event.position()):
            return
        if self.armed:
            x, y = self._percent(event.position(), self.armed)
            self.placed.emit(self.armed, x, y)
            self.arm(None)
            return
        kind = self._pill_at(event.position().toPoint())
        if kind:
            self.dragging = kind
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt name
        if self.dragging:
            x, y = self._percent(event.position(), self.dragging)
            self.placed.emit(self.dragging, x, y)
            return
        if not self.armed:
            over = self._pill_at(event.position().toPoint())
            self.setCursor(Qt.OpenHandCursor if over else Qt.ArrowCursor)
        self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt name
        if self.dragging:
            self.dragging = None
            self.setCursor(Qt.OpenHandCursor)
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt name
        self.update()


class SentimentCoverCard(QFrame):
    """Designs the dossier's cover sheet, and keeps the settings on this machine."""

    changed = Signal()
    # Raised when the customiser is opened or shut, so whatever is holding this
    # card can make room for it. Carries True when it has just been opened.
    foldChanged = Signal(bool)
    # One of the five morning values changed. Kept apart from `changed` on
    # purpose: set_division runs on every recount, and emitting `changed` from
    # there loops back through the window's refresh into set_division again.
    morningChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SentimentCoverCard")
        self.setStyleSheet(
            f"#SentimentCoverCard {{ background: {theme.SURFACE};"
            f" border: 1px solid {theme.HAIRLINE}; border-radius: 16px; }}"
        )
        # Never taller than it needs to be: in a vertical stack a Preferred
        # widget soaks up spare height, which stretched the collapsed header.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.config = sentiment_cover.SentimentCoverConfig()
        self.iso_date = date.today()
        self.division = None
        self._count = 0
        self._breakdown: dict = {}
        self._loading = False

        # 6ms a render is cheap, but a drag would fire it a hundred times.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(24)
        self._debounce.timeout.connect(self._repaint)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self.save)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())

        self.body = QWidget()
        self.body.setObjectName("SentimentCoverBody")
        self.body.setStyleSheet(
            "#SentimentCoverBody { background: transparent; }"
        )
        spread = QHBoxLayout(self.body)
        spread.setContentsMargins(16, 14, 16, 16)
        spread.setSpacing(16)
        spread.addWidget(self._build_controls(), 7)
        # The sheet scales to its height, so beyond a point extra width is dead
        # space taken from the controls beside it. 4 keeps the page comfortably
        # large without starving them.
        spread.addWidget(self._build_preview(), 4)
        outer.addWidget(self.body)

        self.load()

    # --------------------------------------------------------------- header
    def _build_header(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("SentimentCoverHead")
        bar.setStyleSheet(
            f"#SentimentCoverHead {{ background: {theme.NAVY_BAND};"
            f" border: none; border-bottom: 1px solid {theme.NAVY_BAND_LINE};"
            " border-top-left-radius: 15px; border-top-right-radius: 15px; }"
            "#SentimentCoverHead QLabel { background: transparent;"
            " border: none; }"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 12, 14, 12)
        row.setSpacing(11)

        badge = QLabel()
        badge.setFixedSize(32, 32)
        badge.setAlignment(Qt.AlignCenter)
        badge.setPixmap(icon_pixmap("file_text", theme.ORANGE_INK, 17))
        badge.setStyleSheet(
            f"background: {theme.SURFACE};"
            f" border: 1px solid {theme.HAIRLINE_STRONG}; border-radius: 10px;"
        )
        row.addWidget(badge)

        column = QVBoxLayout()
        column.setSpacing(1)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel("Custom Division Cover Page")
        title.setStyleSheet(
            f"color: {theme.NAVY}; font-size: 13px; font-weight: 800;"
            " letter-spacing: .01em;"
        )
        dossier = QLabel("SENTIMENT DOSSIER")
        dossier.setStyleSheet(
            f"color: {theme.ORANGE_INK}; background: {theme.ORANGE_WASH};"
            f" border: 1px solid {theme.ORANGE_DEEP}; border-radius: 9px;"
            " padding: 2px 8px; font-size: 9px; font-weight: 900;"
            " letter-spacing: .05em;"
        )
        title_row.addWidget(title)
        title_row.addWidget(dossier)
        title_row.addStretch(1)
        column.addLayout(title_row)
        hint = QLabel(
            "Blank-page cover with Indian Railways emblem, movable date, "
            "movable clip count and division name"
        )
        hint.setStyleSheet(
            f"color: {theme.SLATE_TEXT_LIGHT}; font-size: 11px;"
        )
        # The single widest thing in the header: left unwrapped it held the head
        # at 787px and pushed the Enable tick and the collapse chevron off the
        # right edge, where neither could be clicked.
        hint.setWordWrap(True)
        column.addWidget(hint)
        row.addLayout(column, 1)

        self.enable_box = QCheckBox("Enable Cover Page")
        self.enable_box.setCursor(Qt.PointingHandCursor)
        self.enable_box.setStyleSheet(
            f"QCheckBox {{ color: {theme.INK}; font-size: 11px;"
            f" font-weight: 700; background: {theme.SURFACE};"
            f" border: 1px solid {theme.HAIRLINE_STRONG}; border-radius: 10px;"
            " padding: 6px 11px; spacing: 7px; }"
            f"QCheckBox:hover {{ background: {theme.NAVY_SELECT}; }}"
            "QCheckBox::indicator { width: 14px; height: 14px;"
            f" border-radius: 4px; border: 1.5px solid {theme.HAIRLINE_STRONG};"
            f" background: {theme.SURFACE}; }}"
            f"QCheckBox::indicator:checked {{ background: {theme.ORANGE};"
            f" border-color: {theme.ORANGE}; }}"
        )
        self.enable_box.toggled.connect(self._enable_toggled)
        row.addWidget(self.enable_box)

        self.collapse_btn = QPushButton()
        self.collapse_btn.setObjectName("SentimentCoverCollapse")
        self.collapse_btn.setCursor(Qt.PointingHandCursor)
        self.collapse_btn.setFixedSize(28, 28)
        self.collapse_btn.setIcon(
            icon_pixmap("chevron_up", theme.SLATE_TEXT_LIGHT, 15)
        )
        self.collapse_btn.setToolTip("Collapse cover customiser")
        self.collapse_btn.setStyleSheet(
            "#SentimentCoverCollapse { background: transparent; border: none;"
            " border-radius: 8px; }"
            f"#SentimentCoverCollapse:hover {{ background: {theme.NAVY_SELECT}; }}"
        )
        self.collapse_btn.clicked.connect(self._toggle)
        row.addWidget(self.collapse_btn)
        return bar

    def _toggle(self) -> None:
        showing = self.body.isVisibleTo(self)
        self.body.setVisible(not showing)
        self.collapse_btn.setIcon(
            icon_pixmap("chevron_down" if showing else "chevron_up",
                        theme.SLATE_TEXT_LIGHT, 15)
        )
        self.collapse_btn.setToolTip(
            "Expand cover customiser" if showing else "Collapse cover customiser"
        )
        self.foldChanged.emit(not showing)

    # ---------------------------------------------------------- tab plumbing
    def _build_controls(self) -> QWidget:
        holder = QWidget()
        holder.setObjectName("SentimentCoverControls")
        holder.setStyleSheet(
            "#SentimentCoverControls { background: transparent; }"
        )
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(11)

        bar = QFrame()
        bar.setObjectName("SentimentTabBar")
        bar.setStyleSheet(
            "#SentimentTabBar { background: #E5E7EB; border: none;"
            " border-radius: 12px; }"
        )
        tabs = QHBoxLayout(bar)
        tabs.setContentsMargins(4, 4, 4, 4)
        tabs.setSpacing(4)

        self.tab_buttons: list[QPushButton] = []
        for index, (label, icon) in enumerate((
            ("Division & Text", "building"),
            ("Date & Clip Count Placement", "move"),
            ("Logo & Styling", "palette"),
            ("Presets", "sparkles"),
        )):
            # "&" in a button label is Qt's mnemonic marker and disappears
            # unless it is doubled.
            button = QPushButton(label.replace("&", "&&"))
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(30)
            button.setProperty("iconName", icon)
            button.setProperty("plainText", label)
            button.clicked.connect(
                lambda _checked=False, at=index: self._show_tab(at)
            )
            self.tab_buttons.append(button)
            tabs.addWidget(button, 1)
        column.addWidget(bar)

        self.tabs = QStackedWidget()
        self.tabs.setObjectName("SentimentTabs")
        self.tabs.setStyleSheet("#SentimentTabs { background: transparent; }")
        self.tabs.addWidget(self._build_text_tab())
        self.tabs.addWidget(self._build_placement_tab())
        self.tabs.addWidget(self._build_design_tab())
        self.tabs.addWidget(self._build_presets_tab())
        self.tabs.currentChanged.connect(self._fit_tabs)
        column.addWidget(self.tabs, 1)
        self._show_tab(0)
        return holder

    def _fit_tabs(self, *_args) -> None:
        for index in range(self.tabs.count()):
            page = self.tabs.widget(index)
            policy = page.sizePolicy()
            policy.setVerticalPolicy(
                QSizePolicy.Preferred if index == self.tabs.currentIndex()
                else QSizePolicy.Ignored
            )
            page.setSizePolicy(policy)
        self.tabs.updateGeometry()

    def _show_tab(self, index: int) -> None:
        self.tabs.setCurrentIndex(index)
        for at, button in enumerate(self.tab_buttons):
            picked = at == index
            name = button.property("iconName")
            button.setIcon(
                icon_pixmap(name, theme.NAVY if picked else "#4B5563", 14)
            )
            button.setStyleSheet(
                (f"QPushButton {{ background: {theme.SURFACE};"
                 f" color: {theme.NAVY}; border: none; border-radius: 9px;"
                 f" font-size: 11px; font-weight: 800; padding: 5px 8px; }}")
                if picked else
                ("QPushButton { background: transparent; color: #4B5563;"
                 " border: none; border-radius: 9px; font-size: 11px;"
                 " font-weight: 700; padding: 5px 8px; }"
                 "QPushButton:hover { color: #111827; }")
            )

    @staticmethod
    def _page(spacing: int = 11) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(spacing)
        return page, column

    # ------------------------------------------------------ tab 1: the text
    def _build_text_tab(self) -> QWidget:
        page, column = self._page()
        grid = QGridLayout()
        grid.setHorizontalSpacing(13)
        grid.setVerticalSpacing(4)

        grid.addWidget(small_label("1. Railway Zone / Authority Text"), 0, 0)
        self.org_edit = QLineEdit()
        self.org_edit.setPlaceholderText("e.g. NORTHERN RAILWAY / उत्तर रेलवे")
        self.org_edit.textEdited.connect(lambda _t: self._read())
        grid.addWidget(self.org_edit, 1, 0)

        division_head = QHBoxLayout()
        division_head.setSpacing(6)
        division_head.addWidget(small_label("2. Division / Office Name"))
        division_head.addStretch(1)
        self.sync_btn = QPushButton("Sync")
        self.sync_btn.setObjectName("SentimentSync")
        self.sync_btn.setCursor(Qt.PointingHandCursor)
        self.sync_btn.setToolTip(
            "Rewrite this from the division the board is showing"
        )
        self.sync_btn.setStyleSheet(
            f"#SentimentSync {{ background: transparent; border: none;"
            f" color: {theme.NAVY}; font-size: 10px; font-weight: 800; }}"
            f"#SentimentSync:hover {{ color: {theme.ORANGE_DEEP}; }}"
        )
        self.sync_btn.clicked.connect(self._sync_division)
        division_head.addWidget(self.sync_btn)
        grid.addLayout(division_head, 0, 1)
        self.division_edit = QLineEdit()
        self.division_edit.textEdited.connect(lambda _t: self._read())
        grid.addWidget(self.division_edit, 1, 1)

        grid.addWidget(small_label("3. Dossier / Report Title"), 2, 0)
        # A text box, not a line edit: the bilingual preset writes a two-line
        # title and the sheet honours the break.
        self.title_edit = QTextEdit()
        self.title_edit.setAcceptRichText(False)
        self.title_edit.setFixedHeight(52)
        self.title_edit.textChanged.connect(self._read)
        grid.addWidget(self.title_edit, 3, 0)

        grid.addWidget(small_label("4. Subtitle / Period Description"), 2, 1)
        self.subtitle_edit = QTextEdit()
        self.subtitle_edit.setAcceptRichText(False)
        self.subtitle_edit.setFixedHeight(52)
        self.subtitle_edit.textChanged.connect(self._read)
        grid.addWidget(self.subtitle_edit, 3, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        column.addLayout(grid)

        panel, inner = sub_panel()
        head = QHBoxLayout()
        head.setSpacing(7)
        stamp = QLabel()
        stamp.setPixmap(icon_pixmap("calendar", theme.NAVY, 15))
        stamp.setStyleSheet("background: transparent; border: none;")
        head.addWidget(stamp)
        head.addWidget(small_label("5. Dossier Date Reference", theme.NAVY))
        head.addStretch(1)
        self.today_btn = QPushButton("Set to today")
        self.today_btn.setObjectName("SentimentToday")
        self.today_btn.setCursor(Qt.PointingHandCursor)
        self.today_btn.setStyleSheet(
            f"#SentimentToday {{ background: {theme.SURFACE};"
            f" border: 1px solid {theme.NAVY}; border-radius: 9px;"
            f" color: {theme.NAVY}; font-size: 10px; font-weight: 800;"
            f" padding: 4px 10px; }}"
            f"#SentimentToday:hover {{ background: {theme.NAVY_WASH}; }}"
        )
        self.today_btn.clicked.connect(self._set_today)
        head.addWidget(self.today_btn)
        inner.addLayout(head)

        dates = QGridLayout()
        dates.setHorizontalSpacing(13)
        dates.setVerticalSpacing(4)
        dates.addWidget(small_label("Select via calendar"), 0, 0)
        from .datefield import DayEdit

        self.date_edit = DayEdit(what="dossier")
        self.date_edit.dateChanged.connect(self._date_picked)
        dates.addWidget(self.date_edit, 1, 0)
        dates.addWidget(small_label("Display date text"), 0, 1)
        self.date_text = QLineEdit()
        self.date_text.setPlaceholderText("Date: 05.09.2026")
        self.date_text.textEdited.connect(lambda _t: self._read())
        dates.addWidget(self.date_text, 1, 1)
        dates.setColumnStretch(0, 1)
        dates.setColumnStretch(1, 1)
        inner.addLayout(dates)
        column.addWidget(panel)

        footer = QGridLayout()
        footer.setHorizontalSpacing(13)
        footer.setVerticalSpacing(4)
        footer.addWidget(small_label("6. Prepared By / Department"), 0, 0)
        self.prepared_edit = QLineEdit()
        self.prepared_edit.textEdited.connect(lambda _t: self._read())
        footer.addWidget(self.prepared_edit, 1, 0)
        footer.addWidget(small_label("7. Additional Notes / Circulation"), 0, 1)
        self.notes_edit = QLineEdit()
        self.notes_edit.textEdited.connect(lambda _t: self._read())
        footer.addWidget(self.notes_edit, 1, 1)
        footer.setColumnStretch(0, 1)
        footer.setColumnStretch(1, 1)
        column.addLayout(footer)
        column.addStretch(1)
        return page

    # ------------------------------------------------- tab 2: the placement
    def _build_placement_tab(self) -> QWidget:
        page, column = self._page()

        tip = QFrame()
        tip.setObjectName("SentimentTip")
        tip.setStyleSheet(
            "#SentimentTip { background: #FFFBEB; border: 1px solid #FDE68A;"
            " border-radius: 12px; }"
            "#SentimentTip QLabel { background: transparent; border: none; }"
        )
        tip_row = QHBoxLayout(tip)
        tip_row.setContentsMargins(12, 10, 12, 10)
        tip_row.setSpacing(9)
        mark = QLabel()
        mark.setPixmap(icon_pixmap("move", "#B45309", 16))
        mark.setAlignment(Qt.AlignTop)
        tip_row.addWidget(mark)
        words = QLabel(
            "<b>Movable elements:</b> the date and the clip count can go "
            "anywhere on the cover. Pick a preset below, use the sliders, or "
            "<b>drag them straight on the A4 sheet</b>."
        )
        words.setWordWrap(True)
        words.setStyleSheet("color: #78350F; font-size: 11px;")
        tip_row.addWidget(words, 1)
        column.addWidget(tip)

        self.date_controls = self._placement_panel(
            "date", "Date position", "calendar", DATE_PRESETS,
            "Default (centre flow)",
        )
        column.addWidget(self.date_controls["panel"])

        self.count_controls = self._placement_panel(
            "count", "Clip count position", "hash_sign", COUNT_PRESETS,
            "Default (below title)", with_toggle=True,
        )
        column.addWidget(self.count_controls["panel"])
        column.addStretch(1)
        return page

    def _placement_panel(self, kind: str, title: str, icon: str, presets: list,
                         default_text: str, with_toggle: bool = False) -> dict:
        panel, inner = sub_panel()
        head = QHBoxLayout()
        head.setSpacing(7)

        if with_toggle:
            self.count_box = QCheckBox("Show number of clips")
            self.count_box.setStyleSheet(
                f"QCheckBox {{ color: {theme.NAVY}; font-size: 11px;"
                f" font-weight: 800; background: transparent; }}"
            )
            self.count_box.toggled.connect(lambda _v: self._read())
            head.addWidget(self.count_box)
        else:
            mark = QLabel()
            mark.setPixmap(icon_pixmap(icon, theme.NAVY, 15))
            mark.setStyleSheet("background: transparent; border: none;")
            head.addWidget(mark)
            head.addWidget(small_label(title, theme.NAVY))

        status = QLabel(default_text)
        status.setStyleSheet(
            "color: #374151; background: #E5E7EB; border: none;"
            " border-radius: 7px; padding: 2px 8px; font-size: 10px;"
            " font-weight: 700;"
        )
        head.addWidget(status)
        head.addStretch(1)

        place = QPushButton("Click to place")
        place.setCursor(Qt.PointingHandCursor)
        place.setToolTip("Then click the sheet where this should sit")
        place.clicked.connect(lambda _c=False, k=kind: self._arm(k))
        head.addWidget(place)

        reset = QPushButton("Reset")
        reset.setObjectName(f"SentimentReset{kind}")
        reset.setCursor(Qt.PointingHandCursor)
        reset.setStyleSheet(
            f"#SentimentReset{kind} {{ background: transparent; border: none;"
            f" color: {theme.DANGER}; font-size: 10px; font-weight: 700; }}"
        )
        reset.clicked.connect(lambda _c=False, k=kind: self._reset_pos(k))
        head.addWidget(reset)
        inner.addLayout(head)

        if with_toggle:
            text_row = QHBoxLayout()
            text_row.setSpacing(7)
            self.count_text = QLineEdit()
            self.count_text.setPlaceholderText("e.g. Total Clippings: 12")
            self.count_text.textEdited.connect(lambda _t: self._read())
            text_row.addWidget(self.count_text, 1)
            self.total_btn = QPushButton("Total")
            self.total_btn.setCursor(Qt.PointingHandCursor)
            self.total_btn.clicked.connect(self._count_total)
            text_row.addWidget(self.total_btn)
            self.breakdown_btn = QPushButton("Breakdown")
            self.breakdown_btn.setCursor(Qt.PointingHandCursor)
            self.breakdown_btn.setToolTip(
                "Write the four sentiment counts instead of the total"
            )
            self.breakdown_btn.clicked.connect(self._count_breakdown)
            text_row.addWidget(self.breakdown_btn)
            inner.addLayout(text_row)

        inner.addWidget(caps_label("POSITION PRESETS"))
        chips = QHBoxLayout()
        chips.setSpacing(6)
        buttons = {}
        for label, value in presets:
            chip = QPushButton(label)
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(
                lambda _c=False, k=kind, v=value: self._preset_pos(k, v)
            )
            buttons[label] = (chip, value)
            chips.addWidget(chip, 1)
        inner.addLayout(chips)

        sliders = QGridLayout()
        sliders.setHorizontalSpacing(13)
        sliders.setVerticalSpacing(3)
        x_min, x_max, y_min, y_max = sentiment_cover.pill_bounds(kind)
        horizontal = QSlider(Qt.Horizontal)
        horizontal.setRange(int(x_min + 0.5), int(x_max))
        vertical = QSlider(Qt.Horizontal)
        vertical.setRange(int(y_min + 0.5), int(y_max))
        x_read = small_label("", "#6B7280", 10, 600)
        y_read = small_label("", "#6B7280", 10, 600)
        for at, (name, slider, read) in enumerate(
            (("Horizontal", horizontal, x_read), ("Vertical", vertical, y_read))
        ):
            label_row = QHBoxLayout()
            label_row.setSpacing(4)
            label_row.addWidget(small_label(name, "#6B7280", 10, 600))
            label_row.addStretch(1)
            label_row.addWidget(read)
            sliders.addLayout(label_row, 0, at)
            sliders.addWidget(slider, 1, at)
            sliders.setColumnStretch(at, 1)
        horizontal.valueChanged.connect(
            lambda v, k=kind: self._slider_moved(k, v, None)
        )
        vertical.valueChanged.connect(
            lambda v, k=kind: self._slider_moved(k, None, v)
        )
        inner.addLayout(sliders)

        # Size, on its own row under the two position sliders. The bubbles could
        # already be put anywhere; they could not be made to fit what was put in
        # them, so a long "Total Clippings" line or a wanted-larger date had
        # nowhere to go.
        size_row = QHBoxLayout()
        size_row.setSpacing(7)
        size_row.addWidget(small_label("Size", "#6B7280", 10, 600))
        size = QSlider(Qt.Horizontal)
        size.setRange(int(sentiment_cover.PILL_SCALE_MIN * 100),
                      int(sentiment_cover.PILL_SCALE_MAX * 100))
        size.setValue(100)
        size.setToolTip("How large the bubble is drawn on the sheet")
        size_read = small_label("100%", "#6B7280", 10, 600)
        size.valueChanged.connect(
            lambda v, k=kind: self._size_moved(k, v)
        )
        smaller = QPushButton("Reset size")
        smaller.setCursor(Qt.PointingHandCursor)
        smaller.setToolTip("Back to the drawn size")
        smaller.clicked.connect(lambda _c=False, k=kind: self._reset_size(k))
        size_row.addWidget(size, 1)
        size_row.addWidget(size_read)
        size_row.addWidget(smaller)
        inner.addLayout(size_row)

        return {
            "panel": panel, "status": status, "place": place, "reset": reset,
            "presets": buttons, "x": horizontal, "y": vertical,
            "size": size, "size_read": size_read,
            "x_read": x_read, "y_read": y_read, "default_text": default_text,
        }

    # ---------------------------------------------------- tab 3: the styling
    def _build_design_tab(self) -> QWidget:
        page, column = self._page()

        panel, inner = sub_panel()
        head = QHBoxLayout()
        head.setSpacing(7)
        head.addWidget(small_label("Indian Railways centre emblem", theme.NAVY))
        head.addWidget(small_label("positioned at the top", "#6B7280", 10, 600))
        head.addStretch(1)
        self.logo_box = QCheckBox("Show emblem")
        self.logo_box.setStyleSheet(
            "QCheckBox { color: #374151; font-size: 11px; font-weight: 700;"
            " background: transparent; }"
        )
        self.logo_box.toggled.connect(lambda _v: self._read())
        head.addWidget(self.logo_box)
        inner.addLayout(head)

        logo_row = QHBoxLayout()
        logo_row.setSpacing(8)
        self.logo_btn = QPushButton("Upload custom emblem")
        self.logo_btn.setObjectName("SentimentLogo")
        self.logo_btn.setCursor(Qt.PointingHandCursor)
        self.logo_btn.setIcon(icon_pixmap("upload_cloud", "#FFFFFF", 14))
        self.logo_btn.setStyleSheet(
            f"#SentimentLogo {{ background: {theme.NAVY}; color: white;"
            f" border: none; border-radius: 9px; font-size: 11px;"
            f" font-weight: 800; padding: 6px 12px; }}"
            f"#SentimentLogo:hover {{ background: #1E3A8A; }}"
        )
        self.logo_btn.clicked.connect(self._choose_logo)
        logo_row.addWidget(self.logo_btn)
        self.logo_reset = QPushButton("Back to the official emblem")
        self.logo_reset.setCursor(Qt.PointingHandCursor)
        self.logo_reset.setIcon(icon_pixmap("rotate", "#374151", 14))
        self.logo_reset.clicked.connect(self._clear_logo)
        logo_row.addWidget(self.logo_reset)
        logo_row.addStretch(1)
        inner.addLayout(logo_row)
        column.addWidget(panel)

        column.addWidget(small_label("Theme colour"))
        self.theme_buttons: dict[str, QPushButton] = {}
        themes = QHBoxLayout()
        themes.setSpacing(7)
        for name, value in sentiment_cover.THEMES.items():
            button = QPushButton(name)
            button.setCursor(Qt.PointingHandCursor)
            button.setIcon(icon_pixmap("dot_solid", value, 13))
            button.clicked.connect(
                lambda _c=False, v=value: self._set_field("theme_colour", v)
            )
            self.theme_buttons[value] = button
            themes.addWidget(button, 1)
        column.addLayout(themes)

        column.addWidget(small_label("Border frame style"))
        self.border_buttons: dict[str, QPushButton] = {}
        borders = QHBoxLayout()
        borders.setSpacing(7)
        for value, label in BORDER_STYLES:
            button = QPushButton(label)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda _c=False, v=value: self._set_field("border_style", v)
            )
            self.border_buttons[value] = button
            borders.addWidget(button, 1)
        column.addLayout(borders)

        column.addWidget(small_label("Text alignment"))
        self.align_buttons: dict[str, QPushButton] = {}
        aligns = QHBoxLayout()
        aligns.setSpacing(7)
        for value, label, icon in (("center", "Centred", "align_center"),
                                   ("left", "Left aligned", "align_left")):
            button = QPushButton(label)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("iconName", icon)
            button.clicked.connect(
                lambda _c=False, v=value: self._set_field("text_align", v)
            )
            self.align_buttons[value] = button
            aligns.addWidget(button, 1)
        column.addLayout(aligns)
        column.addStretch(1)
        return page

    # ---------------------------------------------------- tab 4: the presets
    def _build_presets_tab(self) -> QWidget:
        page, column = self._page(9)
        column.addWidget(
            small_label(
                "A ready-made layout for division press monitoring. Your date, "
                "clip count and emblem are left alone.",
                "#6B7280", 11, 500,
            )
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        for at, name in enumerate(sentiment_cover.PRESETS):
            grid.addWidget(self._preset_card(name), at // 2, at % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        column.addLayout(grid)
        column.addStretch(1)
        return page

    def _preset_card(self, name: str) -> QWidget:
        icon, colour = PRESET_ICONS.get(name, ("sparkles", theme.NAVY))
        button = QPushButton()
        button.setObjectName(f"Preset{abs(hash(name)) % 10000}")
        button.setCursor(Qt.PointingHandCursor)
        button.setMinimumHeight(70)
        button.setStyleSheet(
            f"#{button.objectName()} {{ background: {theme.THUMB_BG};"
            f" border: 1px solid {theme.HAIRLINE}; border-radius: 12px;"
            f" text-align: left; padding: 10px 12px; }}"
            f"#{button.objectName()}:hover {{ background: {theme.NAVY_WASH};"
            f" border-color: {colour}; }}"
        )
        layout = QVBoxLayout(button)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)
        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(small_label(name, colour, 11, 800))  # a QLabel, so "&" is safe
        head.addStretch(1)
        mark = QLabel()
        mark.setPixmap(icon_pixmap(icon, colour, 15))
        mark.setStyleSheet("background: transparent; border: none;")
        head.addWidget(mark)
        layout.addLayout(head)
        note = QLabel(PRESET_NOTES.get(name, ""))
        note.setWordWrap(True)
        note.setStyleSheet(
            "color: #6B7280; font-size: 10px; background: transparent;"
            " border: none;"
        )
        layout.addWidget(note)
        button.clicked.connect(lambda _c=False, key=name: self._apply_preset(key))
        return button

    # --------------------------------------------------------- the preview
    def _build_preview(self) -> QWidget:
        holder = QWidget()
        holder.setObjectName("SentimentPreviewHolder")
        holder.setStyleSheet(
            "#SentimentPreviewHolder { background: transparent; }"
        )
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(6)
        watch = QLabel()
        watch.setPixmap(icon_pixmap("eye", theme.NAVY, 14))
        watch.setStyleSheet("background: transparent; border: none;")
        head.addWidget(watch)
        head.addWidget(small_label("Cover page live preview (A4 sheet)",
                                   "#374151"))
        head.addStretch(1)
        self.include_note = QLabel()
        head.addWidget(self.include_note)
        column.addLayout(head)

        strip = QFrame()
        strip.setObjectName("SentimentSheetBar")
        strip.setStyleSheet(
            f"#SentimentSheetBar {{ background: {theme.THUMB_BG};"
            f" border: 1px solid {theme.HAIRLINE_STRONG}; border-bottom: none;"
            " border-top-left-radius: 9px; border-top-right-radius: 9px; }"
            "#SentimentSheetBar QLabel { background: transparent;"
            " border: none; }"
        )
        bar = QHBoxLayout(strip)
        bar.setContentsMargins(9, 5, 9, 5)
        bar.setSpacing(6)
        grip = QLabel()
        grip.setPixmap(icon_pixmap("move", theme.ORANGE_INK, 12))
        bar.addWidget(grip)
        bar.addWidget(small_label("Drag the pills, or click the sheet to place",
                                  theme.INK, 10, 700))
        bar.addStretch(1)
        self.arm_note = small_label(
            "Interactive", theme.SLATE_TEXT_LIGHT, 10, 600)
        bar.addWidget(self.arm_note)
        column.addWidget(strip)

        self.sheet = SheetPreview()
        self.sheet.placed.connect(self._pill_placed)
        self.sheet.armedChanged.connect(self._armed_changed)
        column.addWidget(self.sheet, 1)
        return holder

    # ----------------------------------------------------------- behaviour
    def _arm(self, kind: str) -> None:
        self.sheet.arm(None if self.sheet.armed == kind else kind)

    def _armed_changed(self, kind) -> None:
        names = {"date": "Placing the date", "count": "Placing the clip count"}
        if kind:
            self.arm_note.setText(names.get(kind, "Placing"))
            self.arm_note.setStyleSheet(
                f"color: {theme.ORANGE_INK}; font-size: 10px; font-weight: 800;"
                f" background: {theme.ORANGE_WASH}; border: none;"
                " border-radius: 6px; padding: 1px 6px;"
            )
        else:
            self.arm_note.setText("Interactive")
            self.arm_note.setStyleSheet(
                f"color: {theme.SLATE_TEXT_LIGHT}; font-size: 10px;"
                " font-weight: 600; background: transparent; border: none;"
            )
        for key, controls in (("date", self.date_controls),
                              ("count", self.count_controls)):
            live = kind == key
            controls["place"].setText(
                "Click the sheet" if live else "Click to place"
            )
            controls["place"].setStyleSheet(
                (f"QPushButton {{ background: {theme.ORANGE_INK};"
                 f" color: white; border: 1px solid {theme.ORANGE_INK};"
                 " border-radius: 9px; font-size: 10px; font-weight: 800;"
                 " padding: 4px 10px; }}")
                if live else
                (f"QPushButton {{ background: {theme.SURFACE}; color: #374151;"
                 f" border: 1px solid {theme.HAIRLINE_STRONG};"
                 f" border-radius: 9px; font-size: 10px; font-weight: 700;"
                 f" padding: 4px 10px; }}"
                 f"QPushButton:hover {{ background: {theme.PANEL}; }}")
            )

    def _pill_placed(self, kind: str, x_pct: int, y_pct: int) -> None:
        if kind == "date":
            self.config.date_pos = (x_pct, y_pct)
        else:
            self.config.clip_count_pos = (x_pct, y_pct)
        self._write_placement()
        self._touch()

    def _preset_pos(self, kind: str, value) -> None:
        if value is not None:
            value = sentiment_cover.clamp_pill(kind, value[0], value[1])
        if kind == "date":
            self.config.date_pos = value
        else:
            self.config.clip_count_pos = value
        self._write_placement()
        self._touch()

    def _reset_pos(self, kind: str) -> None:
        self._preset_pos(kind, None)

    def _pill_block(self, kind: str):
        """The controls for one bubble - date or count."""
        return getattr(self, "date_controls" if kind == "date"
                       else "count_controls", None)

    # ------------------------------------------------------------ pill sizing
    def _size_moved(self, kind: str, value: int) -> None:
        """The slider is in percent; the config carries a plain multiplier."""
        if self._loading:
            return
        scale = max(sentiment_cover.PILL_SCALE_MIN,
                    min(sentiment_cover.PILL_SCALE_MAX, value / 100.0))
        if kind == "date":
            self.config.date_scale = scale
        else:
            self.config.clip_count_scale = scale
        self._show_size(kind, scale)
        self._touch()

    def _reset_size(self, kind: str) -> None:
        widgets = self._pill_block(kind)
        if widgets and widgets.get("size") is not None:
            widgets["size"].setValue(100)
        else:
            self._size_moved(kind, 100)

    def _show_size(self, kind: str, scale: float) -> None:
        widgets = self._pill_block(kind)
        if widgets and widgets.get("size_read") is not None:
            widgets["size_read"].setText(f"{int(round(scale * 100))}%")

    def _slider_moved(self, kind: str, x_value, y_value) -> None:
        if self._loading:
            return
        current = (self.config.date_pos if kind == "date"
                   else self.config.clip_count_pos) or (50, 50)
        x = current[0] if x_value is None else x_value
        y = current[1] if y_value is None else y_value
        self._preset_pos(kind, (x, y))

    def _count_total(self) -> None:
        self.count_text.setText(f"Total Clippings: {self._count}")
        self._read()
        self.morningChanged.emit()

    def _count_breakdown(self) -> None:
        parts = self._breakdown or {}
        self.count_text.setText(
            f"{parts.get('Positive', 0)} Pos • {parts.get('Neutral', 0)} Neu"
            f" • {parts.get('Negative', 0)} Neg"
            f" • {parts.get('Digital', 0)} Dig"
        )
        self._read()
        self.morningChanged.emit()

    def _set_today(self) -> None:
        self.date_edit.setDate(QDate.currentDate())

    # A date written into the free-text box: "Date: 05.09.2026", "05-09-2026",
    # "Week ending 5/9/2026". Loose about the separators because the box is
    # there precisely so somebody can word it their own way.
    _WRITTEN_DATE = re.compile(
        r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b")

    def written_date(self):
        """The date somebody typed into the display box, if there is one."""
        found = self._WRITTEN_DATE.search(self.date_text.text() or "")
        if not found:
            return None
        day, month, year = (int(part) for part in found.groups())
        try:
            return date(year, month, day)
        except ValueError:      # 31.02.2026 and the like - not a date at all
            return None

    def date_is_sound(self, parent=None) -> bool:
        """True when nothing on this cover is dated later than today.

        Two dates live on this card and they are not the same thing. The picker
        sets :attr:`iso_date`. The box beside it is free text and is printed on
        the cover verbatim - which means "Date: 25.12.2099" typed into it goes
        straight onto a finished dossier, however carefully the picker is
        guarded. Both are checked here, and this is the only place that checks
        the second one at all.
        """
        from .datefield import is_future, refuse_future

        parent = parent or self.window()
        if not refuse_future(parent, self.iso_date, "dossier"):
            return False
        written = self.written_date()
        if written is not None and is_future(written):
            QMessageBox.warning(
                parent, "That date has not happened yet",
                f"The cover's date line reads "
                f"\u201c{self.date_text.text().strip()}\u201d, which is dated "
                f"{written.strftime('%d.%m.%Y')} - in the future.\n\n"
                f"Nothing was built. Correct the date line and try again.")
            return False
        return True

    def _date_picked(self, value: QDate) -> None:
        # Read it back from the field rather than trusting the argument. A
        # signal argument is a snapshot of a moment that may already have been
        # corrected - which is exactly how a refused date once got through.
        value = self.date_edit.date()
        self.iso_date = value.toPython()
        stamp = self.iso_date.strftime("%d.%m.%Y")
        # Only overwrite the display text when it still looks generated, so a
        # hand-written line like "Week ending 05.09.2026" survives a date change.
        current = self.date_text.text().strip()
        if not current or current.startswith("Date: "):
            self.date_text.setText(f"Date: {stamp}")
        self._read()
        self.morningChanged.emit()

    def _sync_division(self) -> None:
        if self.division is None:
            return
        self.division_edit.setText(
            f"{self.division.full_name.upper()} ({self.division.code})"
        )
        self.prepared_edit.setText(
            f"Public Relations Office, {self.division.full_name}"
        )
        self._read()

    def _choose_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose the emblem", self.config.logo_path or "", IMAGE_FILTER
        )
        if path:
            self.config.logo_path = path
            self.config.show_logo = True
            self.logo_box.setChecked(True)
            self._touch()
            self._refresh_state()

    def _clear_logo(self) -> None:
        self.config.logo_path = ""
        self.config.show_logo = True
        self.logo_box.setChecked(True)
        self._touch()
        self._refresh_state()

    def _set_field(self, name: str, value) -> None:
        setattr(self.config, name, value)
        self._refresh_state()
        self._touch()

    def _apply_preset(self, name: str) -> None:
        values = sentiment_cover.PRESETS.get(name)
        if not values:
            return
        self._loading = True
        for key, value in values.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        if self.division is not None:
            self.config.division_text = (
                f"{self.division.full_name.upper()} ({self.division.code})"
            )
        self._write_widgets()
        self._loading = False
        self._refresh_state()
        self._touch()

    def _enable_toggled(self, on: bool) -> None:
        self.config.enabled = on
        self._refresh_state()
        self._touch()

    # ------------------------------------------------------------- plumbing
    def _read(self, *_args) -> None:
        """Pull every text field into the config."""
        if self._loading:
            return
        self.config.organisation_text = self.org_edit.text()
        self.config.division_text = self.division_edit.text()
        self.config.report_title = self.title_edit.toPlainText()
        self.config.subtitle_text = self.subtitle_edit.toPlainText()
        self.config.date_text = self.date_text.text()
        self.config.prepared_by_text = self.prepared_edit.text()
        self.config.additional_notes = self.notes_edit.text()
        self.config.show_clip_count = self.count_box.isChecked()
        self.config.clip_count_text = self.count_text.text()
        self.config.show_logo = self.logo_box.isChecked()
        self._touch()

    def _apply_pill_sizes(self) -> None:
        """Put the saved sizes onto the two sliders."""
        for kind, scale in (("date", getattr(self.config, "date_scale", 1.0)),
                            ("count",
                             getattr(self.config, "clip_count_scale", 1.0))):
            widgets = self._pill_block(kind)
            if not widgets or widgets.get("size") is None:
                continue
            slider = widgets["size"]
            blocked = slider.blockSignals(True)
            slider.setValue(int(round(float(scale) * 100)))
            slider.blockSignals(blocked)
            self._show_size(kind, float(scale))

    def _touch(self) -> None:
        if self._loading:
            return
        self._save_timer.start()
        self._debounce.start()
        self.changed.emit()

    def set_division(self, division) -> None:
        """Follow the board's division, unless the user has typed over it."""
        previous = self.division
        self.division = division
        if division is None:
            return
        generated = (
            "" if previous is None
            else f"{previous.full_name.upper()} ({previous.code})"
        )
        wanted = f"{division.full_name.upper()} ({division.code})"
        current = self.config.division_text.strip()
        # Follow the board only while the user has not typed their own wording,
        # and only when it would actually change something. This runs on every
        # recount, and emitting `changed` here loops back through the window's
        # refresh and straight into this method again.
        if current != wanted and (not current or current == generated):
            self._loading = True
            self._sync_division_quietly()
            self._loading = False
            # The division line belongs to the newspad now, not to the design
            # file, so it is the newspad's session that has to hear about it.
            self.morningChanged.emit()
            self._debounce.start()
        self.sync_btn.setText(f"Sync {division.code}")
        self._refresh_state()

    def _sync_division_quietly(self) -> None:
        self.config.division_text = (
            f"{self.division.full_name.upper()} ({self.division.code})"
        )
        self.config.prepared_by_text = (
            f"Public Relations Office, {self.division.full_name}"
        )
        self.division_edit.setText(self.config.division_text)
        self.prepared_edit.setText(self.config.prepared_by_text)

    def set_counts(self, total: int, breakdown: dict) -> None:
        self._count = total
        self._breakdown = breakdown or {}
        self.total_btn.setText(f"Total ({total})")
        self._debounce.start()

    def cover_config(self) -> sentiment_cover.SentimentCoverConfig:
        return self.config

    # ------------------------------------------------------------ rendering
    def _repaint(self) -> None:
        try:
            image = sentiment_cover.render(
                self.config, self._count, "a4", PREVIEW_SCALE
            )
        except Exception:  # noqa: BLE001 - a preview must never break the app
            image = None
        self.sheet.show_cover(image, self.config.enabled)

    def _refresh_state(self) -> None:
        if self.config.enabled:
            self.include_note.setText("● Included in export")
            self.include_note.setStyleSheet(
                f"color: {theme.GREEN}; font-size: 10px; font-weight: 800;"
                f" background: transparent; border: none;"
            )
        else:
            self.include_note.setText("Disabled — tick to include")
            self.include_note.setStyleSheet(
                "color: #9CA3AF; font-size: 10px; background: transparent;"
                " border: none;"
            )

        for value, button in self.theme_buttons.items():
            picked = value == self.config.theme_colour
            button.setStyleSheet(
                (f"QPushButton {{ background: {theme.SURFACE}; color: #1F2937;"
                 f" border: 2px solid #111827; border-radius: 9px;"
                 f" font-size: 10px; font-weight: 800; padding: 5px 6px; }}")
                if picked else
                (f"QPushButton {{ background: {theme.SURFACE}; color: #374151;"
                 f" border: 1px solid {theme.HAIRLINE}; border-radius: 9px;"
                 f" font-size: 10px; font-weight: 700; padding: 5px 6px; }}"
                 f"QPushButton:hover {{ border-color: #9CA3AF; }}")
            )
        self._pick_style(self.border_buttons, self.config.border_style)
        self._pick_style(self.align_buttons, self.config.text_align, icon=True)
        self.logo_reset.setVisible(bool(self.config.logo_path))
        self._write_placement()

    def _pick_style(self, buttons: dict, value: str, icon: bool = False) -> None:
        for key, button in buttons.items():
            picked = key == value
            button.setStyleSheet(
                (f"QPushButton {{ background: {theme.NAVY}; color: white;"
                 f" border: 1px solid {theme.NAVY}; border-radius: 9px;"
                 f" font-size: 11px; font-weight: 800; padding: 5px 8px; }}")
                if picked else
                (f"QPushButton {{ background: {theme.SURFACE}; color: #374151;"
                 f" border: 1px solid {theme.HAIRLINE_STRONG};"
                 f" border-radius: 9px; font-size: 11px; font-weight: 700;"
                 f" padding: 5px 8px; }}"
                 f"QPushButton:hover {{ background: {theme.PANEL}; }}")
            )
            if icon:
                name = button.property("iconName")
                if name:
                    button.setIcon(
                        icon_pixmap(name, "#FFFFFF" if picked else "#374151", 14)
                    )

    def _write_placement(self) -> None:
        """Mirror the two positions onto their status chips, chips and sliders."""
        for kind, controls, position in (
            ("date", self.date_controls, self.config.date_pos),
            ("count", self.count_controls, self.config.clip_count_pos),
        ):
            if position is None:
                controls["status"].setText(controls["default_text"])
                controls["status"].setStyleSheet(
                    "color: #374151; background: #E5E7EB; border: none;"
                    " border-radius: 7px; padding: 2px 8px; font-size: 10px;"
                    " font-weight: 700;"
                )
                controls["x_read"].setText("—")
                controls["y_read"].setText("—")
            else:
                controls["status"].setText(
                    f"X {int(position[0])}%   Y {int(position[1])}%"
                )
                controls["status"].setStyleSheet(
                    f"color: {theme.NAVY}; background: {theme.NAVY_WASH};"
                    f" border: none; border-radius: 7px; padding: 2px 8px;"
                    f" font-size: 10px; font-weight: 800;"
                )
                controls["x_read"].setText(f"{int(position[0])}%")
                controls["y_read"].setText(f"{int(position[1])}%")

            controls["reset"].setVisible(position is not None)
            was = self._loading
            self._loading = True
            if position is not None:
                controls["x"].setValue(int(position[0]))
                controls["y"].setValue(int(position[1]))
            self._loading = was

            for label, (chip, value) in controls["presets"].items():
                if value is None:
                    picked = position is None
                else:
                    wanted = sentiment_cover.clamp_pill(kind, value[0], value[1])
                    picked = (position is not None
                              and (int(position[0]), int(position[1])) == wanted)
                chip.setStyleSheet(
                    (f"QPushButton {{ background: {theme.NAVY}; color: white;"
                     f" border: 1px solid {theme.NAVY}; border-radius: 8px;"
                     f" font-size: 10px; font-weight: 800; padding: 4px 4px; }}")
                    if picked else
                    (f"QPushButton {{ background: {theme.SURFACE};"
                     f" color: #374151; border: 1px solid {theme.HAIRLINE};"
                     f" border-radius: 8px; font-size: 10px; font-weight: 700;"
                     f" padding: 4px 4px; }}"
                     f"QPushButton:hover {{ background: {theme.PANEL}; }}")
                )

    # -------------------------------------------------------------- storage
    def _state(self) -> dict:
        """The DESIGN only. The five morning values go with the newspad."""
        data = {}
        for field in sentiment_cover.SentimentCoverConfig.__dataclass_fields__:
            if field in MORNING:
                continue
            value = getattr(self.config, field)
            data[field] = list(value) if isinstance(value, tuple) else value
        return data

    # ------------------------------------------------ this newspad's morning
    def morning(self) -> dict:
        """The five values that belong to this newspad, for its session."""
        return {
            "iso_date": self.iso_date.isoformat(),
            "date_text": self.config.date_text,
            "clip_count_text": self.config.clip_count_text,
            "division_text": self.config.division_text,
            "prepared_by_text": self.config.prepared_by_text,
        }

    def set_morning(self, values) -> None:
        """Put a newspad's morning back, or start a fresh one with None.

        Nothing here starts the design save: none of these five are design.
        """
        defaults = sentiment_cover.SentimentCoverConfig()
        self._loading = True
        try:
            if values:
                try:
                    when = date.fromisoformat(str(values.get("iso_date", "")))
                except ValueError:
                    when = date.today()
                self.iso_date = min(when, date.today())
                for field in _MORNING_TEXT:
                    setattr(self.config, field,
                            str(values.get(field) or getattr(defaults, field)))
            else:
                self.iso_date = date.today()
                self.config.date_text = ""
                for field in ("clip_count_text", "division_text",
                              "prepared_by_text"):
                    setattr(self.config, field, getattr(defaults, field))
                if self.division is not None:
                    self._sync_division_quietly()
            if not self.config.date_text.strip():
                self.config.date_text = (
                    f"Date: {self.iso_date.strftime('%d.%m.%Y')}")
            self._write_widgets()
        finally:
            self._loading = False
        self._refresh_state()
        self._debounce.start()

    def save(self) -> None:
        try:
            _file().write_text(
                json.dumps(self._state(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001 - settings are a convenience
            pass

    def flush(self) -> None:
        if self._save_timer.isActive():
            self._save_timer.stop()
            self.save()

    def load(self) -> None:
        try:
            data = json.loads(_file().read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - nothing saved yet
            data = {}

        self._loading = True
        fresh = sentiment_cover.SentimentCoverConfig()
        for field in sentiment_cover.SentimentCoverConfig.__dataclass_fields__:
            # The five morning values are never read from this file. They
            # belong to a newspad and come from its session, so restoring a
            # setup file, or reading the design again, can never overwrite the
            # morning somebody is working on.
            if field in MORNING:
                continue
            if field in data and data[field] is not None:
                value = data[field]
                if field in ("date_pos", "clip_count_pos") and value:
                    value = (int(value[0]), int(value[1]))
                setattr(fresh, field, value)
        # Carry the morning that is on the card across the reload.
        for field in _MORNING_TEXT:
            setattr(fresh, field, getattr(self.config, field))
        self.config = fresh
        if self.iso_date > date.today():
            self.iso_date = date.today()
        if not self.config.date_text.strip():
            self.config.date_text = f"Date: {self.iso_date.strftime('%d.%m.%Y')}"

        self._write_widgets()
        self._apply_pill_sizes()
        self._loading = False
        self._refresh_state()
        self._debounce.start()

    def _write_widgets(self) -> None:
        self.enable_box.setChecked(bool(self.config.enabled))
        self.org_edit.setText(self.config.organisation_text)
        self.division_edit.setText(self.config.division_text)
        self.title_edit.setPlainText(self.config.report_title)
        self.subtitle_edit.setPlainText(self.config.subtitle_text)
        self.date_edit.setDate(
            QDate(self.iso_date.year, self.iso_date.month, self.iso_date.day)
        )
        self.date_text.setText(self.config.date_text)
        self.prepared_edit.setText(self.config.prepared_by_text)
        self.notes_edit.setText(self.config.additional_notes)
        self.count_box.setChecked(bool(self.config.show_clip_count))
        self.count_text.setText(self.config.clip_count_text)
        self.logo_box.setChecked(bool(self.config.show_logo))
