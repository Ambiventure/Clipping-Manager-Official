"""The cover sheet of the division sentiment dossier, drawn once for two callers.

The dossier's cover is the one page in the whole application whose look is argued
over: which emblem, which shade of navy, where the date sits, whether the clipping
count belongs under the title or up in a corner. That argument is only settleable if
what the user sees while dragging things around is the same page that comes out of
the PDF, so there is exactly one implementation of the layout here and both the live
preview and the exporters call it. The only difference between a 340-pixel preview
and a 300-DPI export page is the ``scale`` argument: every measurement below is in
PostScript points at the real page size, and the scale is applied once, by the
painter, at the end.

The emblem is drawn as vector paint rather than shipped as a bitmap, because the
same routine has to serve a 24-pixel thumbnail and a full-bleed export without
either one looking chewed. The arc lettering warps an already-shaped text outline
around the ring instead of placing glyphs one by one: Devanagari matras sit beside
the consonant they belong to only if the shaper has run first, and glyph-by-glyph
placement would spell "भारतीय" as something no reader would accept.

Qt only - no PIL, no Qt widgets, so this is safe to call from an export worker.
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QGuiApplication,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
)

from ..export import layout

# --- fixed geometry, in points at the real page size -------------------------
MARGIN = 28.0
FLOW_TOP = 58.0                  # margin + 30, where the first block starts
TEXT_INSET = 10.0                # text column is inset this much inside the margin

LOGO_GAP = 22.0
ORG_SIZE = 14.0
ORG_ADVANCE = 24.0
RULE_WIDTH = 120.0
RULE_STROKE = 1.2
RULE_ADVANCE = 28.0
DIVISION_SIZE = 17.0
DIVISION_ADVANCE = 32.0
TITLE_SIZE = 21.0
TITLE_ADVANCE = 28.0
SUBTITLE_SIZE = 11.0
SUBTITLE_ADVANCE = 24.0

DATE_BOX = (210.0, 26.0, 13.0)   # width, height, corner radius
DATE_SIZE = 10.5
DATE_ADVANCE = 32.0
COUNT_BOX = (190.0, 24.0, 12.0)
COUNT_SIZE = 10.0
COUNT_ADVANCE = 30.0
PILL_EDGE_PAD = 5.0              # how close a placed pill may come to the margin
# How far the two bubbles may be taken from their drawn size. Half is still
# legible on a printed sheet; past double they start to crowd the title above.
PILL_SCALE_MIN = 0.5
PILL_SCALE_MAX = 2.5


def _scaled_pill(box: tuple[float, float, float], size: float, scale: float):
    """A pill's box and type size at the scale the person chose."""
    try:
        factor = float(scale)
    except (TypeError, ValueError):
        factor = 1.0
    factor = max(PILL_SCALE_MIN, min(PILL_SCALE_MAX, factor))
    width, height, radius = box
    return (width * factor, height * factor, radius * factor, size * factor)

FOOTER_FROM_BOTTOM = 73.0
FOOTER_RULE_GAP = 12.0
FOOTER_RULE_INSET = 20.0
PREPARED_SIZE = 10.0
NOTES_SIZE = 8.5
NOTES_ADVANCE = 16.0

# --- fixed colours -----------------------------------------------------------
TITLE_COLOUR = "#111827"
SUBTITLE_COLOUR = "#4B5563"
DATE_FILL = "#F3F4F6"
DATE_STROKE = "#D1D5DB"
COUNT_FILL = "#F8FAFC"
COUNT_STROKE = "#CBD5E1"
FOOTER_RULE_COLOUR = "#E5E7EB"
PREPARED_COLOUR = "#1F2937"
NOTES_COLOUR = "#6B7280"
FALLBACK_THEME = "#122A52"

THEMES: dict[str, str] = {
    "NR Navy": "#122A52",
    "IR Maroon": "#8B1E1E",
    "Slate Dark": "#0F172A",
    "Forest Green": "#065F46",
    "Classic Black": "#111827",
}

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
# Nirmala UI ships with Windows and covers both scripts; the rest are the usual
# stand-ins on a machine that has neither it nor a bundled face.
# Faces that set BOTH scripts well come first - Nirmala UI and Mangal ship with
# Windows and read properly in English and in Hindi. Noto Sans Devanagari goes
# last because its Latin is drawn to sit beside Devanagari rather than to lead a
# page: put it first and the cover's English loses a tenth of its cap height.
SYSTEM_FAMILIES = (
    "Nirmala UI",
    "Mangal",
    "Segoe UI",
    "Arial",
    "Helvetica",
    "Noto Sans Devanagari",
)
DEVANAGARI_PROBE = "भ"      # भ - if this is missing, the arc drops to Latin
MAX_ARC_SWEEP = 132.0       # degrees of ring the badge legend may occupy


@dataclass
class SentimentCoverConfig:
    """Everything the cover sheet can be told. Empty text means "leave it out"."""

    enabled: bool = False
    show_logo: bool = True
    logo_path: str = ""
    logo_height: float = 78.0
    organisation_text: str = "INDIAN RAILWAYS / भारतीय रेल"
    division_text: str = ""
    report_title: str = "DAILY MEDIA CLIPPINGS DOSSIER"
    subtitle_text: str = "Media Coverage, Monitoring & Public Sentiment Highlights"
    date_text: str = ""
    date_pos: tuple[float, float] | None = None
    date_scale: float = 1.0
    show_clip_count: bool = True
    clip_count_text: str = ""
    clip_count_pos: tuple[float, float] | None = None
    clip_count_scale: float = 1.0
    prepared_by_text: str = "Public Relations Office"
    additional_notes: str = "For Internal Railway Administrative Circulation Only"
    theme_colour: str = "#122A52"
    border_style: str = "classic"
    text_align: str = "center"


PRESETS: dict[str, dict] = {
    "Official Division Dossier": {
        "organisation_text": "INDIAN RAILWAYS / भारतीय रेल",
        "report_title": "DAILY MEDIA CLIPPINGS DOSSIER",
        "subtitle_text": "Print & Digital Press Coverage Compilation",
        "prepared_by_text": "Public Relations Department",
        "additional_notes": "Strictly for Internal Official Circulation • Office of DRM",
        "theme_colour": "#122A52",
        "border_style": "classic",
        "text_align": "center",
        "show_logo": True,
        "show_clip_count": True,
    },
    "Executive Sentiment Brief": {
        "organisation_text": "NORTHERN RAILWAY / उत्तर रेलवे",
        "report_title": "MEDIA SENTIMENT ANALYSIS REPORT",
        "subtitle_text": "High-Priority News Monitoring & Tone Assessment",
        "prepared_by_text": "Senior Divisional Commercial Manager / PRO",
        "additional_notes": "Confidential • Media Monitoring Cell",
        "theme_colour": "#8B1E1E",
        "border_style": "modern",
        "text_align": "center",
        "show_logo": True,
        "show_clip_count": True,
    },
    "Bilingual Hindi & English": {
        "organisation_text": "उत्तर रेलवे  •  NORTHERN RAILWAY",
        "report_title": "दैनिक समाचार संकलन एवं समीक्षा\nDAILY PRESS CLIPPINGS DOSSIER",
        "subtitle_text": "मुद्रित एवं इलेक्ट्रॉनिक मीडिया कवरेज",
        "prepared_by_text": "जनसंपर्क कार्यालय",
        "additional_notes": "केवल विभागीय उपयोग हेतु • मंडल रेल प्रबंधक कार्यालय",
        "theme_colour": "#122A52",
        "border_style": "double",
        "text_align": "center",
        "show_logo": True,
        "show_clip_count": True,
    },
    "Clean Minimalist Sheet": {
        "organisation_text": "INDIAN RAILWAYS",
        "report_title": "Press Clippings Dossier",
        "subtitle_text": "",
        "prepared_by_text": "Public Relations Office",
        "additional_notes": "",
        "theme_colour": "#0F172A",
        "border_style": "none",
        "text_align": "center",
        "show_logo": True,
        "show_clip_count": False,
    },
}


def apply_preset(config: SentimentCoverConfig, name: str) -> SentimentCoverConfig:
    """A copy of ``config`` with one preset laid over it.

    Division-specific wording is deliberately not part of a preset: the caller owns
    ``division_text``, and a preset that cleared it would undo the user's division
    every time they tried a different look.
    """
    preset = PRESETS.get(name)
    if not preset:
        return config
    known = {f.name for f in fields(SentimentCoverConfig)}
    updated = SentimentCoverConfig(**{f.name: getattr(config, f.name) for f in fields(config)})
    for key, value in preset.items():
        if key in known:
            setattr(updated, key, value)
    return updated


# --- Qt plumbing -------------------------------------------------------------
_app_holder: list[QGuiApplication] = []
_families_cache: Optional[list[str]] = None


def _ensure_app() -> None:
    """Qt refuses to measure text without an application object.

    The UI always has one long before it asks for a preview; this is for the export
    worker and for scripts, which otherwise crash inside the first QFontMetrics.
    """
    if QGuiApplication.instance() is not None:
        return
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app_holder.append(QGuiApplication(sys.argv[:1] or [""]))


def _families() -> list[str]:
    """Font families to try, bundled faces first."""
    global _families_cache
    if _families_cache is not None:
        return _families_cache

    bundled: list[str] = []
    if FONT_DIR.is_dir():
        # Regular and Bold only, matching what the packaged build carries.
        for path in sorted(FONT_DIR.glob("*.ttf")) + sorted(FONT_DIR.glob("*.otf")):
            if not path.stem.endswith(("-Regular", "-Bold")):
                continue
            if any(word in path.stem
                   for word in ("Condensed", "Italic", "VariableFont")):
                continue
            try:
                handle = QFontDatabase.addApplicationFont(str(path))
            except Exception:  # noqa: BLE001 - a bad font file must not stop the page
                continue
            if handle >= 0:
                bundled.extend(QFontDatabase.applicationFontFamilies(handle))
    # The page's own faces first and the bundled Devanagari behind them: it is
    # there so Hindi always has glyphs, not to set the English.
    found: list[str] = list(SYSTEM_FAMILIES)
    found.extend(bundled)
    # And anything else here that covers Devanagari. Naming three faces meant a
    # machine with only Aparajita or Kokila drew the Hindi lines of the cover as
    # boxes - and the cover is painted by Qt and embedded as a picture, so those
    # boxes went into the PDF and printed.
    try:
        from PySide6.QtGui import QFontDatabase as _FD

        found.extend(f for f in _FD.families()
                     if _FD.WritingSystem.Devanagari in _FD.writingSystems(f))
    except Exception:  # noqa: BLE001 - best effort, never fatal
        pass
    _families_cache = found
    return found


def _font(size: float, bold: bool, dpi_fix: float) -> QFont:
    font = QFont()
    font.setFamilies(_families())
    # Point sizes are converted to device pixels through the paint device's DPI; the
    # correction pins one point to one unit of our page coordinate system, whatever
    # that device happens to claim.
    font.setPointSizeF(max(0.5, size * dpi_fix))
    font.setBold(bold)
    # Hinting snaps stems to whole device pixels, which at preview scale shifts
    # letters away from where the point measurements put them.
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return font


def _colour(value: str, fallback: str = FALLBACK_THEME) -> QColor:
    colour = QColor(value or "")
    if not colour.isValid():
        colour = QColor(fallback)
    return colour


def _dpi_fix(device) -> float:
    try:
        dpi = float(device.logicalDpiY())
    except Exception:  # noqa: BLE001
        dpi = 72.0
    return 72.0 / dpi if dpi > 0 else 1.0


# --- the emblem --------------------------------------------------------------
def railway_emblem(size: int, colour: str) -> QImage:
    """The Indian Railways badge - ring, winged wheel, arc lettering - as vectors.

    Drawn in a 400-unit space and scaled, so one routine serves a list thumbnail and
    an export page without a bitmap in sight.
    """
    _ensure_app()
    side = max(8, int(size))
    image = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter()
    if not painter.begin(image):
        return image
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.scale(side / 400.0, side / 400.0)
        body = _colour(colour)
        white = QColor("#FFFFFF")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(body)
        painter.drawEllipse(QRectF(4, 4, 392, 392))

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(white, 3.0))
        painter.drawEllipse(QRectF(8, 8, 384, 384))
        faded = QColor(white)
        faded.setAlphaF(0.6)
        painter.setPen(QPen(faded, 1.5))
        painter.drawEllipse(QRectF(15, 15, 370, 370))

        _arc_text(painter, image, white)
        _ring_stars(painter, white)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(white, 3.5))
        painter.drawEllipse(QRectF(74, 74, 252, 252))
        painter.setPen(QPen(white, 1.5))
        painter.drawEllipse(QRectF(80, 80, 240, 240))

        _winged_wheel(painter, white, body)
    finally:
        painter.end()
    return image


def _ring_stars(painter: QPainter, white: QColor) -> None:
    """Twelve dots around the lower ring, where the official badge carries stars."""
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(white)
    for index in range(12):
        angle = math.radians(8.0 + index * (164.0 / 11.0))
        x = 200 + 152 * math.cos(angle)
        y = 200 + 152 * math.sin(angle)
        painter.drawEllipse(QRectF(x - 4.5, y - 4.5, 9.0, 9.0))


def _arc_text(painter: QPainter, device: QImage, white: QColor) -> None:
    """Bend the badge legend around the top of the ring.

    The string is turned into an outline first and only then bent, so the shaper has
    already put every matra where it belongs. If no installed face can set
    Devanagari the Latin half is drawn alone - a legible half is worth more than a
    row of empty boxes.
    """
    dpi_fix = _dpi_fix(device)
    text = "भारतीय रेल  •  INDIAN RAILWAYS"
    try:
        if not QFontMetricsF(_font(21.5, True, dpi_fix)).inFont(DEVANAGARI_PROBE):
            text = "INDIAN RAILWAYS"
    except Exception:  # noqa: BLE001
        text = "INDIAN RAILWAYS"

    radius = 148.0
    try:
        # Shrink until the legend sits on the top arc. Letting it run further round
        # brings the last words up the far side upside down.
        size = 21.5
        while size > 9.0:
            font = _font(size, True, dpi_fix)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, size * 0.10)
            advance = QFontMetricsF(font).horizontalAdvance(text)
            if advance / radius <= math.radians(MAX_ARC_SWEEP):
                break
            size -= 0.5
        if advance <= 0:
            return

        path = QPainterPath()
        path.addText(0.0, 0.0, font, text)
        if path.elementCount() == 0:
            return

        sweep = advance / radius
        start = -math.pi / 2.0 - sweep / 2.0

        bent = QPainterPath(path)
        for index in range(bent.elementCount()):
            element = bent.elementAt(index)
            theta = start + float(element.x) / radius
            distance = radius - float(element.y)
            bent.setElementPositionAt(
                index,
                200.0 + distance * math.cos(theta),
                200.0 + distance * math.sin(theta),
            )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(white)
        painter.drawPath(bent)
    except Exception:  # noqa: BLE001 - a malformed arc is worse than no arc
        return


def _winged_wheel(painter: QPainter, white: QColor, body: QColor) -> None:
    """Wheel, hub, spokes and three feathers a side, in the 400-unit space."""
    cx, cy = 200.0, 206.0

    # Roots sit inside the wheel's opaque disc so the blunt end of each feather is
    # hidden behind it rather than poking out as a spur.
    root_x = 40.0
    feathers = ((92.0, 18.0, 30.0), (72.0, 15.0, 40.0), (52.0, 12.0, 48.0))
    for direction in (1.0, -1.0):
        for index, (length, thickness, lift) in enumerate(feathers):
            base_y = cy - 24.0 + index * 16.0
            root = cx + direction * root_x
            tip = cx + direction * (root_x + length)
            feather = QPainterPath()
            feather.moveTo(root, base_y)
            feather.quadTo(
                cx + direction * (root_x + length * 0.5), base_y - lift * 0.75,
                tip, base_y - lift,
            )
            feather.quadTo(
                cx + direction * (root_x + length * 0.62), base_y - lift * 0.35,
                cx + direction * (root_x + length * 0.55), base_y - lift * 0.10,
            )
            feather.lineTo(root, base_y + thickness)
            feather.closeSubpath()
            painter.setPen(QPen(body, 1.6))
            painter.setBrush(white)
            painter.drawPath(feather)

    # The wheel is opaque so the roots of the feathers disappear behind it.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(body)
    painter.drawEllipse(QRectF(cx - 49, cy - 49, 98, 98))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(white, 8.0))
    painter.drawEllipse(QRectF(cx - 52, cy - 52, 104, 104))
    painter.setPen(QPen(white, 3.0))
    painter.drawEllipse(QRectF(cx - 38, cy - 38, 76, 76))

    painter.setPen(QPen(white, 4.0))
    for index in range(8):
        angle = math.radians(index * 45.0)
        painter.drawLine(_at(cx, cy, angle, 13.0), _at(cx, cy, angle, 36.0))

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(white)
    painter.drawEllipse(QRectF(cx - 12, cy - 12, 24, 24))
    painter.setBrush(body)
    painter.drawEllipse(QRectF(cx - 5, cy - 5, 10, 10))


def _at(cx: float, cy: float, angle: float, distance: float) -> QPointF:
    return QPointF(cx + distance * math.cos(angle), cy + distance * math.sin(angle))


# --- the cover ---------------------------------------------------------------
def render(
    config: SentimentCoverConfig,
    clip_count: int,
    page: str = "a4",
    scale: float = 1.0,
) -> QImage:
    """Draw the cover sheet at ``page`` size, ``scale`` device pixels to the point.

    ``scale`` is the only thing separating a live preview from an export page, so a
    thing that looks right in the panel is the thing that prints. Anything that goes
    wrong for one element is recorded on the returned image under the text key
    ``warnings`` (``image.text("warnings")``); nothing is allowed to abort the page.
    """
    _ensure_app()
    warnings: list[str] = []
    # Where the two pills actually landed, in page points, so a live preview can
    # hit-test them without re-deriving the flow.
    spots: dict[str, tuple[float, float, float, float]] = {}

    page_w, page_h = layout.page_size(page)
    factor = max(0.02, float(scale))
    # Opaque, because it is a sheet of paper: an alpha channel here only invites a
    # consumer that flattens transparency to black.
    image = QImage(
        max(1, int(round(page_w * factor))),
        max(1, int(round(page_h * factor))),
        QImage.Format.Format_RGB32,
    )
    image.fill(QColor("#FFFFFF"))

    painter = QPainter()
    if not painter.begin(image):
        image.setText("warnings", "The cover page could not be drawn at all.")
        return image
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.scale(factor, factor)
        _paint(painter, image, config, clip_count, page_w, page_h, factor,
               warnings, spots)
    except Exception as error:  # noqa: BLE001
        warnings.append(f"The cover page was only partly drawn ({error}).")
    finally:
        painter.end()

    if warnings:
        image.setText("warnings", " ".join(warnings))
    for key, box in spots.items():
        image.setText(f"{key}_box", ",".join(f"{v:.2f}" for v in box))
    return image


def _paint(
    painter: QPainter,
    device: QImage,
    config: SentimentCoverConfig,
    clip_count: int,
    page_w: float,
    page_h: float,
    factor: float,
    warnings: list[str],
    _spots: dict,
) -> None:
    theme = _colour(config.theme_colour)
    dpi_fix = _dpi_fix(device)
    align = "left" if (config.text_align or "center").lower() == "left" else "center"

    _draw_border(painter, config.border_style, theme, page_w, page_h, warnings)

    y = FLOW_TOP
    if config.show_logo:
        try:
            y = _draw_logo(painter, config, theme, page_w, y, factor, warnings)
        except Exception as error:  # noqa: BLE001
            warnings.append(f"The cover emblem could not be drawn ({error}).")
            y += config.logo_height + LOGO_GAP

    organisation = (config.organisation_text or "").strip()
    if organisation:
        y += _block(
            painter, organisation, y, ORG_SIZE, True,
            theme.name(), align, page_w, dpi_fix, ORG_ADVANCE, warnings,
        )
        painter.setPen(QPen(theme, RULE_STROKE))
        rule_x = (page_w - RULE_WIDTH) / 2.0
        painter.drawLine(QPointF(rule_x, y), QPointF(rule_x + RULE_WIDTH, y))
        y += RULE_ADVANCE

    division = (config.division_text or "").strip()
    if division:
        y += _block(
            painter, division, y, DIVISION_SIZE, True,
            theme.name(), align, page_w, dpi_fix, DIVISION_ADVANCE, warnings,
        )

    title = (config.report_title or "").strip()
    if title:
        y += _block(
            painter, title, y, TITLE_SIZE, True,
            TITLE_COLOUR, align, page_w, dpi_fix, TITLE_ADVANCE, warnings,
        )

    subtitle = (config.subtitle_text or "").strip()
    if subtitle:
        y += _block(
            painter, subtitle, y, SUBTITLE_SIZE, False,
            SUBTITLE_COLOUR, align, page_w, dpi_fix, SUBTITLE_ADVANCE, warnings,
        )

    date_text = (config.date_text or "").strip()
    if date_text:
        box_w, box_h, radius, type_size = _scaled_pill(
            DATE_BOX, DATE_SIZE, getattr(config, "date_scale", 1.0))
        placed = _pill_origin(config.date_pos, box_w, box_h, page_w, page_h, y)
        _spots["date"] = (placed[0], placed[1], box_w, box_h)
        _pill(
            painter, date_text, placed, box_w, box_h, radius,
            DATE_FILL, DATE_STROKE, type_size, theme.name(), dpi_fix, warnings,
        )
        if config.date_pos is None:
            y += DATE_ADVANCE * (box_h / DATE_BOX[1])

    if config.show_clip_count:
        # An empty clip_count_text is a request for the generated tally, not a
        # request to hide the badge - hiding is what show_clip_count is for.
        count_text = (config.clip_count_text or "").strip()
        if not count_text:
            try:
                count_text = f"Total Clippings: {max(0, int(clip_count))}"
            except (TypeError, ValueError):
                count_text = "Total Clippings: 0"
                warnings.append("The clipping count was not a number, so it reads zero.")
        box_w, box_h, radius, type_size = _scaled_pill(
            COUNT_BOX, COUNT_SIZE, getattr(config, "clip_count_scale", 1.0))
        placed = _pill_origin(config.clip_count_pos, box_w, box_h, page_w, page_h, y)
        _spots["count"] = (placed[0], placed[1], box_w, box_h)
        _pill(
            painter, count_text, placed, box_w, box_h, radius,
            COUNT_FILL, COUNT_STROKE, type_size, theme.name(), dpi_fix, warnings,
        )
        if config.clip_count_pos is None:
            y += COUNT_ADVANCE * (box_h / COUNT_BOX[1])

    _draw_footer(painter, config, page_w, page_h, align, dpi_fix, warnings)


def _draw_border(
    painter: QPainter,
    style: str,
    theme: QColor,
    page_w: float,
    page_h: float,
    warnings: list[str],
) -> None:
    kind = (style or "classic").lower()
    if kind not in ("none", "classic", "modern", "double"):
        warnings.append(
            f'"{style}" is not a border style, so the cover was drawn without a frame.'
        )
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "classic":
        painter.setPen(QPen(theme, 2.2))
        painter.drawRect(QRectF(20, 20, page_w - 40, page_h - 40))
        painter.setPen(QPen(theme, 0.75))
        painter.drawRect(QRectF(24, 24, page_w - 48, page_h - 48))
    elif kind == "modern":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme)
        painter.drawRect(QRectF(0, 0, page_w, 14))
        painter.drawRect(QRectF(0, page_h - 12, page_w, 12))
        painter.setBrush(Qt.BrushStyle.NoBrush)
    elif kind == "double":
        painter.setPen(QPen(theme, 3.0))
        painter.drawRect(QRectF(22, 22, page_w - 44, page_h - 44))


def _draw_logo(
    painter: QPainter,
    config: SentimentCoverConfig,
    theme: QColor,
    page_w: float,
    top: float,
    factor: float,
    warnings: list[str],
) -> float:
    side = max(8.0, float(config.logo_height or 78.0))
    # Rendered at twice the device size it will occupy: downsampling a clean vector
    # is cheap, and it keeps the ring smooth on both a preview and a print page.
    pixels = max(48, int(math.ceil(side * factor * 2)))

    art: Optional[QImage] = None
    path = (config.logo_path or "").strip()
    if path:
        loaded = QImage(path)
        if loaded.isNull():
            warnings.append(
                f'The logo file "{path}" could not be read, '
                "so the standard railway emblem was used instead."
            )
        else:
            art = loaded
    if art is None:
        art = railway_emblem(pixels, theme.name())

    box = QRectF((page_w - side) / 2.0, top, side, side)
    scaled = art.scaled(
        max(1, int(round(side * factor * 2))),
        max(1, int(round(side * factor * 2))),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    ratio = scaled.width() / scaled.height() if scaled.height() else 1.0
    draw_w = side if ratio >= 1.0 else side * ratio
    draw_h = side if ratio <= 1.0 else side / ratio
    painter.drawImage(
        QRectF(
            box.center().x() - draw_w / 2.0,
            box.center().y() - draw_h / 2.0,
            draw_w,
            draw_h,
        ),
        scaled,
    )
    return top + side + LOGO_GAP


def _cap_offset(metrics: QFontMetricsF) -> float:
    """Distance from a block's top edge down to its first baseline.

    The gaps in this layout were measured against a renderer where a line of N-point
    text is about N points tall. A Devanagari-capable face reserves a lot more room
    above the capitals than that for matras, and hanging the block off its full
    ascent drops every line far enough to push the separator rule into the words
    above it. Sitting it mostly on the cap height puts the type back where the
    measurements expect it, with a little of the overhang kept so a Hindi line still
    has somewhere to put its vowel signs.
    """
    cap = metrics.capHeight()
    return cap + (metrics.ascent() - cap) * 0.35


def _wrap(text: str, metrics: QFontMetricsF, width: float) -> list[str]:
    """Break ``text`` at explicit newlines and then at spaces to fit ``width``."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            if metrics.horizontalAdvance(trial) <= width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _fill_text(
    painter: QPainter,
    lines: list[str],
    font: QFont,
    metrics: QFontMetricsF,
    left: float,
    width: float,
    first_baseline: float,
    align: str,
    colour: QColor,
) -> None:
    """Set the lines as filled outlines rather than through ``drawText``.

    Qt hands text on Windows to a font engine that antialiases against the RGB
    stripes of a monitor, which puts orange and violet fringes on every grey
    caption - fine on screen, wrong on a page that is about to be printed, and it
    ignores NoSubpixelAntialias. Filling the glyph outlines antialiases in grey and
    looks the same everywhere.
    """
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    baseline = first_baseline
    for line in lines:
        if line:
            advance = metrics.horizontalAdvance(line)
            x = left if align != "center" else left + (width - advance) / 2.0
            path = QPainterPath()
            path.addText(x, baseline, font, line)
            painter.drawPath(path)
        baseline += metrics.lineSpacing()
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _block(
    painter: QPainter,
    text: str,
    top: float,
    size: float,
    bold: bool,
    colour: str,
    align: str,
    page_w: float,
    dpi_fix: float,
    advance: float,
    warnings: list[str],
) -> float:
    """Draw one flowed block and return how far the cursor should move down.

    The advance is the fixed one from the layout, plus whatever a wrapped or
    multi-line block actually spilled over - otherwise a bilingual two-line title
    would print straight through the subtitle underneath it.
    """
    try:
        font = _font(size, bold, dpi_fix)
        metrics = QFontMetricsF(font)
        left = MARGIN + TEXT_INSET
        width = max(1.0, page_w - left * 2)
        lines = _wrap(text, metrics, width)
        _fill_text(
            painter, lines, font, metrics, left, width,
            top + _cap_offset(metrics), align, _colour(colour, "#000000"),
        )
        return advance + max(0, len(lines) - 1) * metrics.lineSpacing()
    except Exception as error:  # noqa: BLE001
        warnings.append(f'The line "{text[:40]}" could not be set ({error}).')
        return advance


def pill_bounds(kind: str, page: str = "a4") -> tuple[float, float, float, float]:
    """The centre percentages a pill can actually take: (x_min, x_max, y_min, y_max).

    A drag has to be clamped to this and not to some nominal range, or the pill the
    user drops is not the pill that gets drawn - _pill_origin clamps the corner
    afterwards, so anything outside these bounds silently snaps back on the next
    render. Derived from the same constants, so it stays true if they move.
    """
    page_w, page_h = layout.page_size(page)
    box_w, box_h = (COUNT_BOX[0], COUNT_BOX[1]) if kind == "count" else (
        DATE_BOX[0], DATE_BOX[1])
    left = MARGIN + PILL_EDGE_PAD + box_w / 2.0
    right = page_w - MARGIN - PILL_EDGE_PAD - box_w / 2.0
    top = MARGIN + PILL_EDGE_PAD + box_h / 2.0
    bottom = page_h - MARGIN - PILL_EDGE_PAD - box_h / 2.0
    return (left / page_w * 100.0, right / page_w * 100.0,
            top / page_h * 100.0, bottom / page_h * 100.0)


def clamp_pill(kind: str, x_pct: float, y_pct: float,
               page: str = "a4") -> tuple[int, int]:
    """A dragged position, rounded to whole percents and pulled inside the bounds."""
    x_min, x_max, y_min, y_max = pill_bounds(kind, page)
    x = min(x_max, max(x_min, float(x_pct)))
    y = min(y_max, max(y_min, float(y_pct)))
    return (int(round(x)), int(round(y)))


def _pill_origin(
    position: tuple[float, float] | None,
    box_w: float,
    box_h: float,
    page_w: float,
    page_h: float,
    flow_y: float,
) -> tuple[float, float]:
    """Where a pill's top-left corner goes.

    A percentage names the pill's *centre*, which is what the user is aiming at when
    they drop it on the sheet, so it is converted to a corner here and clamped so a
    pill dragged to the very edge still prints inside the margin.
    """
    if position is None:
        return ((page_w - box_w) / 2.0, flow_y)
    x_pct, y_pct = float(position[0]), float(position[1])
    x = x_pct / 100.0 * page_w - box_w / 2.0
    y = y_pct / 100.0 * page_h - box_h / 2.0
    x = max(MARGIN + PILL_EDGE_PAD, min(page_w - MARGIN - box_w - PILL_EDGE_PAD, x))
    y = max(MARGIN + PILL_EDGE_PAD, min(page_h - MARGIN - box_h - PILL_EDGE_PAD, y))
    return (x, y)


def _pill(
    painter: QPainter,
    text: str,
    origin: tuple[float, float],
    box_w: float,
    box_h: float,
    radius: float,
    fill: str,
    stroke: str,
    size: float,
    colour: str,
    dpi_fix: float,
    warnings: list[str],
) -> None:
    try:
        box = QRectF(origin[0], origin[1], box_w, box_h)
        painter.setBrush(_colour(fill, "#FFFFFF"))
        painter.setPen(QPen(_colour(stroke, "#D1D5DB"), 0.8))
        painter.drawRoundedRect(box, radius, radius)
        font = _font(size, True, dpi_fix)
        metrics = QFontMetricsF(font)
        # One line, centred on the pill's optical middle rather than its box middle.
        baseline = box.center().y() + (metrics.ascent() - metrics.descent()) / 2.0
        _fill_text(
            painter, [text], font, metrics, box.left(), box_w,
            baseline, "center", _colour(colour),
        )
    except Exception as error:  # noqa: BLE001
        warnings.append(f'The badge "{text[:40]}" could not be drawn ({error}).')


def _draw_footer(
    painter: QPainter,
    config: SentimentCoverConfig,
    page_w: float,
    page_h: float,
    align: str,
    dpi_fix: float,
    warnings: list[str],
) -> None:
    prepared = (config.prepared_by_text or "").strip()
    notes = (config.additional_notes or "").strip()
    if not prepared and not notes:
        return

    footer_y = page_h - FOOTER_FROM_BOTTOM
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(_colour(FOOTER_RULE_COLOUR, "#E5E7EB"), 0.8))
    rule_y = footer_y - FOOTER_RULE_GAP
    painter.drawLine(
        QPointF(MARGIN + FOOTER_RULE_INSET, rule_y),
        QPointF(page_w - MARGIN - FOOTER_RULE_INSET, rule_y),
    )

    if prepared:
        _block(
            painter, prepared, footer_y, PREPARED_SIZE, True,
            PREPARED_COLOUR, align, page_w, dpi_fix, 0.0, warnings,
        )
        footer_y += NOTES_ADVANCE
    if notes:
        _block(
            painter, notes, footer_y, NOTES_SIZE, False,
            NOTES_COLOUR, align, page_w, dpi_fix, 0.0, warnings,
        )
