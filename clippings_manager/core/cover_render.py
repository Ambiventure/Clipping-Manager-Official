"""Rasterise the two standard-report cover templates to a QImage.

The PDF and Word builders both want a cover as a single finished picture they can
drop onto page 1 full-bleed: PyMuPDF and python-docx each lay text out their own
way, and reproducing the same cover twice in two different engines is how the two
formats drift apart. Painting it once here means the Word cover and the PDF cover
are the same pixels.

Option 1 composites the count and the date onto artwork the user supplies, at the
artwork's own resolution, so nothing is resampled before the builder places it.
Option 2 draws a whole A4 page at 200 DPI from scratch.

The geometry is a port of the browser prototype's canvas code, so every number is
in CSS pixels on those canvases. That is why sizes go through ``setPixelSize`` and
never ``setPointSize`` - a point size would be re-scaled by the screen's DPI and
the layout would stop matching the prototype. For the same reason text is drawn at
``y + ascent``: the prototype sets ``textBaseline = 'top'``, and Qt's drawText
takes a baseline.

QtGui only. No widgets, no dialogs, no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QBuffer, QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QGuiApplication,
    QImage,
    QPainter,
    QPen,
)

# A4 portrait at 200 DPI, the size the prototype's canvas used.
PAGE_WIDTH = 1654
PAGE_HEIGHT = 2338

CONTENT_TOP = 160
CONTENT_BOTTOM = 2288  # inside the outer decorative frame
TEXT_MAX_WIDTH = PAGE_WIDTH - 240
CENTRE_X = PAGE_WIDTH / 2
LEFT_X = 140
RIGHT_X = PAGE_WIDTH - 140

MIN_SCALE = 0.3  # below this the overflow guard would make the cover unreadable

SUBTITLE_COLOUR = "#4B5563"
COUNT_COLOUR = "#6B7280"

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Devanagari first: a Hindi heading rendered in a Latin-only face comes out as
# empty boxes, and Qt only falls back per-family, not per-glyph, when asked.
# The cover is painted by Qt and then embedded into the report as a picture, so
# whatever font this machine has is what the printed cover carries. Naming three
# Devanagari faces and nothing else meant a machine with only Aparajita or Kokila
# produced a cover with the Hindi lines as empty boxes - inside a PDF that is
# otherwise independent of the machine.
PREFERRED_FAMILIES = (
    "Noto Sans Devanagari",
    "Nirmala UI",
    "Mangal",
    "Plus Jakarta Sans",
    "Segoe UI",
    "Arial",
)


def _any_devanagari() -> list[str]:
    """Whatever else on this machine can set Devanagari, best effort."""
    try:
        from PySide6.QtGui import QFontDatabase

        return [f for f in QFontDatabase.families()
                if QFontDatabase.WritingSystem.Devanagari
                in QFontDatabase.writingSystems(f)]
    except Exception:  # noqa: BLE001 - no Qt yet, or none to be had
        return []

_families_cache: Optional[list[str]] = None
_owned_app: Optional[QGuiApplication] = None


@dataclass
class CoverText:
    font_pt: int = 24
    bold: bool = True
    colour: str = "white"
    align: str = "center"  # left|center|right


@dataclass
class Marker:
    x_pct: float  # 0-100 of the artwork width
    y_pct: float  # 0-100 of the artwork height


@dataclass
class Option2:
    logo_path: str = ""
    logo_size: int = 180  # 120|180|240|300
    background_path: str = ""
    background_opacity: float = 0.15
    title: str = "DAILY PRESS CLIPPINGS REPORT"
    subtitle: str = ""
    title_pt: int = 48
    title_weight: str = "bold"  # normal|bold|extra-bold
    title_colour: str = "#122A52"
    title_align: str = "center"
    date_pt: int = 20
    show_clip_count: bool = True
    show_border: bool = True
    background_colour: str = "#FFFFFF"

    # Where the three movable blocks sit, as a shift away from where the
    # automatic flow puts them, in per cent of the sheet. Nought means "leave it
    # where the layout put it", which is what every cover did before these
    # existed - so an old saved cover opens looking exactly as it did.
    #
    # A shift rather than a position on purpose. The heading still wraps, still
    # obeys its alignment and still shrinks to fit; moving it only moves the
    # finished block, so none of that has to be worked out twice.
    logo_dx: float = 0.0
    logo_dy: float = 0.0
    title_dx: float = 0.0
    title_dy: float = 0.0
    date_dx: float = 0.0
    date_dy: float = 0.0


@dataclass
class _TextOp:
    """One laid-out line, ready to paint once the flow has settled."""

    text: str
    x: float
    y: float
    px: int
    weight: int
    colour: str
    align: str
    group: str = "heading"      # which movable block this line belongs to


def _note(warnings: Optional[list[str]], message: str) -> None:
    if warnings is not None:
        warnings.append(message)


def _ensure_gui() -> None:
    """A QPainter on a QImage still needs a QGuiApplication for font loading."""
    global _owned_app
    if QGuiApplication.instance() is not None:
        return
    try:
        _owned_app = QGuiApplication([])
    except Exception:  # noqa: BLE001 - a headless box without a platform plugin
        _owned_app = None


def _families() -> list[str]:
    global _families_cache
    if _families_cache is not None:
        return _families_cache

    bundled: list[str] = []
    if FONT_DIR.is_dir():
        # Regular and Bold only - the same two the packaged build carries.
        for path in sorted(FONT_DIR.glob("*.tt[fc]")) + sorted(FONT_DIR.glob("*.otf")):
            if not path.stem.endswith(("-Regular", "-Bold")):
                continue
            if any(word in path.stem
                   for word in ("Condensed", "Italic", "VariableFont")):
                continue
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id >= 0:
                bundled.extend(QFontDatabase.applicationFontFamilies(font_id))

    try:
        installed = set(QFontDatabase.families())
    except Exception:  # noqa: BLE001
        installed = set()

    # The cover's own typeface leads; the Devanagari faces follow it as
    # fallbacks. Bundling Noto Sans Devanagari and putting it first set the
    # cover's English in a Devanagari face - the same words, 11% shorter in the
    # capitals, because a Devanagari font's Latin is drawn to sit beside Hindi
    # rather than to lead a page. Qt falls through the list per glyph, so Hindi
    # still finds a face; it just is not the one setting the headline.
    devanagari = [f for f in PREFERRED_FAMILIES
                  if f in installed and "Devanagari" in f]
    ordered = [*(f for f in PREFERRED_FAMILIES
                 if f in installed and f not in devanagari),
               *devanagari, *bundled, *_any_devanagari()]
    _families_cache = list(dict.fromkeys(ordered)) or [QFont().defaultFamily()]
    return _families_cache


def _font(px: int, weight: int) -> QFont:
    font = QFont()
    font.setFamilies(_families())
    font.setPixelSize(max(1, int(px)))
    font.setWeight(QFont.Weight(weight))
    return font


def preview_font(px: int, weight: int) -> QFont:
    """The face the cover is drawn with, for the on-screen preview to match."""
    return _font(px, weight)


def _anchor(x: float, width: float, align: str) -> float:
    if align == "center":
        return x - width / 2
    if align == "right":
        return x - width
    return x


def _draw_text(
    painter: QPainter,
    op: _TextOp,
    *,
    dx: float = 0.0,
    dy: float = 0.0,
    colour: Optional[QColor] = None,
) -> None:
    font = _font(op.px, op.weight)
    metrics = QFontMetricsF(font)
    left = _anchor(op.x, metrics.horizontalAdvance(op.text), op.align)
    painter.setFont(font)
    painter.setPen(colour if colour is not None else QColor(op.colour))
    painter.drawText(QPointF(left + dx, op.y + metrics.ascent() + dy), op.text)


def _wrap(text: str, metrics: QFontMetricsF, max_width: float) -> list[str]:
    """Greedy word wrap that keeps explicit newlines, blank lines included."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        words = paragraph.split()
        current = words[0]
        for word in words[1:]:
            probe = f"{current} {word}"
            if metrics.horizontalAdvance(probe) > max_width:
                lines.append(current)
                current = word
            else:
                current = probe
        lines.append(current)
    return lines


def _dmy(value: date) -> str:
    return f"{value.day:02d}.{value.month:02d}.{value.year:04d}"


def _load(path: str | Path) -> QImage:
    image = QImage(str(path))
    return image


# --------------------------------------------------------------------- option 1


def render_option1(
    artwork_path: str | Path | QImage,
    marker: Optional[Marker],
    text: CoverText,
    clip_count: int,
    report_date: date,
    warnings: Optional[list[str]] = None,
) -> Optional[QImage]:
    """Composite the count and date onto the user's own cover artwork.

    Returns ``None`` only when the artwork itself cannot be read - the caller then
    has nothing to place, which is different from a cover that merely failed to
    get its caption.
    """
    _ensure_gui()

    # A caller that already holds the decoded artwork can hand it over; the copy
    # matters because the caption is painted onto whatever it is given.
    artwork = (artwork_path if isinstance(artwork_path, QImage)
               else _load(artwork_path))
    if artwork.isNull():
        _note(warnings, f"Cover artwork could not be read: {artwork_path}")
        return None

    canvas = artwork.convertToFormat(QImage.Format_ARGB32)
    if canvas.isNull():
        _note(warnings, f"Cover artwork is in a format Qt cannot paint on: {artwork_path}")
        return None

    width = canvas.width()
    height = canvas.height()
    font_px = max(16, round(width / 1000 * max(1, int(text.font_pt))))

    align = text.align if text.align in ("left", "center", "right") else "center"
    if marker is None:
        # No marker: sit the block in the lower third, centred, whatever the
        # alignment setting says - there is no anchor for it to align against.
        x = width / 2
        y = height * 0.84
        align = "center"
    else:
        x = marker.x_pct / 100 * width
        y = marker.y_pct / 100 * height

    is_white = str(text.colour).strip().lower() != "black"
    ink = QColor("#FFFFFF" if is_white else "#111111")
    shadow = QColor(0, 0, 0, 191) if is_white else QColor(255, 255, 255, 217)
    weight = 700 if text.bold else 400

    lines = [
        f"NUMBER OF CLIPPINGS: {clip_count}",
        f"DATE: {_dmy(report_date)}",
    ]

    painter = QPainter()
    if not painter.begin(canvas):
        _note(warnings, "Cover caption could not be drawn; the artwork is used as it is.")
        return canvas
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        # Qt has no shadowBlur, so the prototype's soft shadow is approximated by a
        # faint halo around the hard (1,1) drop - enough to keep white text legible
        # over a light patch of artwork without looking like an outline.
        halo = QColor(shadow)
        halo.setAlpha(max(1, round(shadow.alpha() * 0.32)))
        radius = max(1, round(font_px * 0.1))
        ring = [(-radius, 0), (radius, 0), (0, -radius), (0, radius)]

        for index, line in enumerate(lines):
            op = _TextOp(
                text=line,
                x=x,
                y=y + font_px * 1.35 * index,
                px=font_px,
                weight=weight,
                colour=ink.name(),
                align=align,
            )
            for offset_x, offset_y in ring:
                _draw_text(painter, op, dx=1 + offset_x, dy=1 + offset_y, colour=halo)
            _draw_text(painter, op, dx=1, dy=1, colour=shadow)
            _draw_text(painter, op, colour=ink)
    except Exception as error:  # noqa: BLE001 - keep the artwork even if text fails
        _note(warnings, f"Cover caption could not be drawn ({error}); artwork used as it is.")
    finally:
        painter.end()

    return canvas


# --------------------------------------------------------------------- option 2


# The sheet is drawn at 200 DPI, so a real printer's point is this many pixels
# on it. Going through this rather than through a made-up ratio is what makes
# the number on the setting the number that comes out.
PIXELS_PER_POINT = 200.0 / 72.0


def _title_px(config: Option2) -> int:
    """The heading in pixels on the 200 DPI sheet, from its size in points.

    It used to be `pt / 24 * 44`, which is about 1.83 pixels to the point - and
    a pixel here is 0.36 of a point once the sheet is placed on A4, so every
    size came out at about two thirds of what it said. Asking for 96pt printed
    at 63pt, in the PDF and in Word alike. Nobody could see it in the PDF; in
    Word the size is written in the ribbon, which is where it was noticed.
    """
    return max(10, round(max(1, int(config.title_pt)) * PIXELS_PER_POINT))


def _date_px(config: Option2) -> int:
    return max(8, round(max(1, int(config.date_pt)) * PIXELS_PER_POINT))


def _title_weight(config: Option2) -> int:
    if config.title_weight == "extra-bold":
        return 900
    if config.title_weight == "normal":
        return 500
    return 700


def _flow(
    config: Option2,
    clip_count: int,
    report_date: date,
    start_y: float,
    scale: float,
) -> tuple[list[_TextOp], float, float]:
    """Lay the text block out at ``scale``. Returns ops, divider y and bottom y.

    Every font size and every gap is multiplied by ``scale`` so shrinking keeps the
    proportions; only the divider's own 600x3 geometry stays fixed, being furniture
    rather than text.
    """
    ops: list[_TextOp] = []
    y = start_y

    align = config.title_align if config.title_align in ("left", "center", "right") else "center"
    text_x = CENTRE_X
    if align == "left":
        text_x = LEFT_X
    elif align == "right":
        text_x = RIGHT_X

    colour = config.title_colour or "#122A52"

    title_px = max(10, round(_title_px(config) * scale))
    title_font = _font(title_px, _title_weight(config))
    title = config.title if config.title.strip() else "DAILY PRESS CLIPPINGS REPORT"
    for line in _wrap(title, QFontMetricsF(title_font), TEXT_MAX_WIDTH):
        if line:
            ops.append(
                _TextOp(line, text_x, y, title_px, _title_weight(config), colour, align)
            )
        y += title_px * 1.32

    subtitle = config.subtitle.strip()
    if subtitle:
        y += 24 * scale
        subtitle_px = max(10, round(max(18, round(_title_px(config) * 0.45)) * scale))
        # Wrapped, like the heading above it. It never was, and nobody saw it
        # while the sizes were quietly two thirds of what they said: at a real
        # 96pt heading the sub-heading is 43pt, and "NORTHERN RAILWAY / CPRO
        # OFFICE" ran off both edges of the sheet with its middle showing. The
        # shrink-to-fit guard could not catch it either, because that measures
        # height and this was too wide.
        subtitle_font = _font(subtitle_px, 600)
        for line in _wrap(subtitle, QFontMetricsF(subtitle_font), TEXT_MAX_WIDTH):
            if line:
                ops.append(_TextOp(line, text_x, y, subtitle_px, 600,
                                   SUBTITLE_COLOUR, align))
            y += subtitle_px * 1.32
        y += subtitle_px * 0.18

    y += 40 * scale
    divider_y = y

    y += 60 * scale
    date_px = max(10, round(_date_px(config) * scale))
    # The date is always centred, whatever the heading alignment is: it reads as a
    # caption for the whole page rather than as part of the heading block.
    ops.append(
        _TextOp(f"DATE: {_dmy(report_date)}", CENTRE_X, y, date_px, 700, colour,
                "center", "date")
    )
    bottom = y + date_px * 1.32

    if config.show_clip_count:
        y += date_px * 1.45
        count_px = max(9, round(date_px * 0.85))
        ops.append(
            _TextOp(
                f"NUMBER OF CLIPPINGS: {clip_count}",
                CENTRE_X,
                y,
                count_px,
                600,
                COUNT_COLOUR,
                "center",
                "date",
            )
        )
        bottom = y + count_px * 1.32

    return ops, divider_y, bottom


def _offset(config: Option2, group: str) -> tuple[float, float]:
    """How far this block has been dragged, in page pixels."""
    if group == "logo":
        dx, dy = config.logo_dx, config.logo_dy
    elif group == "date":
        dx, dy = config.date_dx, config.date_dy
    else:
        dx, dy = config.title_dx, config.title_dy
    return dx / 100.0 * PAGE_WIDTH, dy / 100.0 * PAGE_HEIGHT


def _compose(
    config: Option2,
    clip_count: int,
    report_date: date,
    logo_dims: Optional[tuple[int, int]],
    warnings: Optional[list[str]] = None,
) -> tuple[list[_TextOp], float, Optional[QRectF]]:
    """Work out where everything goes, without drawing any of it.

    The picture and the Word cover are both built from this, so the sheet
    arranged on screen is the sheet that comes out of either one.
    """
    y = float(CONTENT_TOP)
    logo_rect: Optional[QRectF] = None
    if config.logo_path and logo_dims:
        box = max(1, int(config.logo_size or 180)) * 2.2
        fit = min(box / logo_dims[0], box / logo_dims[1])
        logo_w = logo_dims[0] * fit
        logo_h = logo_dims[1] * fit
        logo_rect = QRectF((PAGE_WIDTH - logo_w) / 2, y, logo_w, logo_h)
        y += logo_h + 60
    elif config.logo_path:
        y += 80                     # a logo was asked for and would not load
    else:
        y += 120

    # The prototype has no overflow guard: a long 72pt heading simply runs off
    # the bottom of the page. Lay the block out, and if it would pass the inner
    # frame, shrink every size and gap by one factor until it fits. A single
    # ratio step would overshoot badly, because a smaller face also wraps into
    # fewer lines - the height of the block falls roughly with the square of the
    # scale - so the largest scale that still fits is found by bisection.
    ops, divider_y, bottom = _flow(config, clip_count, report_date, y, 1.0)
    if bottom > CONTENT_BOTTOM:
        low, high = MIN_SCALE, 1.0
        best = _flow(config, clip_count, report_date, y, low)
        for _ in range(12):
            middle = (low + high) / 2
            trial = _flow(config, clip_count, report_date, y, middle)
            if trial[2] <= CONTENT_BOTTOM:
                best = trial
                low = middle
            else:
                high = middle
        ops, divider_y, _ = best
        _note(
            warnings,
            "The cover heading was too tall for the page and was scaled down to fit.",
        )
    return ops, divider_y, logo_rect


@dataclass
class Placed:
    """One finished thing on the cover, in page pixels at 200 DPI.

    The Word builder turns these into real paragraphs and one picture, so the
    cover of a .docx can be edited afterwards instead of being a flat image.
    """

    kind: str                # "logo" | "text" | "rule"
    group: str               # "logo" | "heading" | "date"
    x: float                 # left edge
    y: float                 # top edge
    width: float
    height: float
    text: str = ""
    px: int = 0
    weight: int = 700
    colour: str = "#122A52"
    align: str = "center"
    path: str = ""
    dx: float = 0.0          # how far this block was dragged, in page pixels
    dy: float = 0.0
    # Where the box holding this block starts and how wide it is, in page
    # pixels. The generated cover leaves these alone and gets the middle column;
    # the caption on somebody's own artwork sits wherever they put it.
    box_x: float = -1.0
    box_w: float = -1.0


def blocks_option2(
    config: Option2,
    clip_count: int,
    report_date: date,
    warnings: Optional[list[str]] = None,
) -> list[Placed]:
    """Everything on the option-2 cover, already moved to where it belongs."""
    _ensure_gui()

    logo_dims: Optional[tuple[int, int]] = None
    if config.logo_path:
        try:
            logo = _load(config.logo_path)
            if logo.isNull() or not logo.width() or not logo.height():
                raise ValueError("unreadable image")
            logo_dims = (logo.width(), logo.height())
        except Exception as error:  # noqa: BLE001
            _note(warnings, f"Cover logo could not be used ({error}); "
                            f"the cover was drawn without it.")

    ops, divider_y, logo_rect = _compose(
        config, clip_count, report_date, logo_dims, warnings)
    colour = config.title_colour or "#122A52"

    out: list[Placed] = []
    if logo_rect is not None:
        dx, dy = _offset(config, "logo")
        out.append(Placed(
            kind="logo", group="logo",
            x=logo_rect.x() + dx, y=logo_rect.y() + dy,
            width=logo_rect.width(), height=logo_rect.height(),
            path=config.logo_path, dx=dx, dy=dy,
        ))

    dx, dy = _offset(config, "heading")
    out.append(Placed(
        kind="rule", group="heading",
        x=527 + dx, y=divider_y + dy, width=600, height=3, colour=colour,
        dx=dx, dy=dy,
    ))

    for op in ops:
        dx, dy = _offset(config, op.group)
        metrics = QFontMetricsF(_font(op.px, op.weight))
        width = metrics.horizontalAdvance(op.text)
        out.append(Placed(
            kind="text", group=op.group,
            x=_anchor(op.x, width, op.align) + dx, y=op.y + dy,
            width=width, height=metrics.height(),
            text=op.text, px=op.px, weight=op.weight,
            colour=QColor(op.colour).name(), align=op.align, dx=dx, dy=dy,
        ))
    return out


def caption_lines(clip_count: int, report_date: date) -> list:
    """The two lines the Option 1 caption carries. One place, so the screen,
    the picture and the Word file cannot say different things."""
    return [f"NUMBER OF CLIPPINGS: {clip_count}",
            f"DATE: {_dmy(report_date)}"]


def caption_box(marker: Optional[Marker], text: CoverText, clip_count: int,
                report_date: date, width: float, height: float) -> QRectF:
    """Where the caption sits on artwork of this size, and how big it is.

    One piece of arithmetic, used by the preview that is dragged, by the picture
    that is composited, and by the Word file - so the ghost box on screen is the
    box that comes out.
    """
    font_px = max(16, round(width / 1000 * max(1, int(text.font_pt))))
    lines = caption_lines(clip_count, report_date)
    metrics = QFontMetricsF(_font(font_px, 700 if text.bold else 400))
    widest = max(metrics.horizontalAdvance(line) for line in lines)
    box_w = widest + font_px * 0.9
    box_h = font_px * 1.35 * len(lines) + font_px * 0.5

    align = text.align if text.align in ("left", "center", "right") else "center"
    if marker is None:
        x, y, align = width / 2, height * 0.84, "center"
    else:
        x = marker.x_pct / 100 * width
        y = marker.y_pct / 100 * height
    left = {"left": x, "right": x - box_w}.get(align, x - box_w / 2)
    return QRectF(left, y - font_px * 0.25, box_w, box_h)


def blocks_option1(artwork_path: str, marker: Optional[Marker],
                   text: CoverText, clip_count: int, report_date: date,
                   warnings: Optional[list] = None) -> list:
    """The Option 1 cover as artwork plus text, for Word to be able to edit it.

    The PDF gets the composited picture, as it always has - nobody edits a PDF
    and one picture guarantees the printed page is the page on screen. Word gets
    the artwork as a picture and the caption as a real text box on top of it, so
    the count and the date can be corrected without coming back here.
    """
    _ensure_gui()
    if not artwork_path:
        return []
    try:
        artwork = _load(artwork_path)
        if artwork.isNull() or not artwork.width() or not artwork.height():
            raise ValueError("unreadable image")
    except Exception as error:  # noqa: BLE001
        _note(warnings, f"Cover artwork could not be read ({error}).")
        return []

    # The artwork fills the sheet, which is how the builders place it, so the
    # caption's position on the artwork is its position on the page.
    out = [Placed(kind="logo", group="artwork", x=0.0, y=0.0,
                  width=float(PAGE_WIDTH), height=float(PAGE_HEIGHT),
                  path=str(artwork_path))]

    box = caption_box(marker, text, clip_count, report_date,
                      PAGE_WIDTH, PAGE_HEIGHT)
    font_px = max(16, round(PAGE_WIDTH / 1000 * max(1, int(text.font_pt))))
    white = str(text.colour).strip().lower() != "black"
    ink = "#FFFFFF" if white else "#111111"
    align = text.align if text.align in ("left", "center", "right") else "center"
    y = box.top() + font_px * 0.25
    for line in caption_lines(clip_count, report_date):
        out.append(Placed(
            kind="text", group="caption", x=box.left(), y=y,
            width=box.width(), height=font_px * 1.35,
            text=line, px=font_px, weight=700 if text.bold else 400,
            colour=ink, align=align,
            box_x=box.left(), box_w=box.width(),
        ))
        y += font_px * 1.35
    return out


def bounds_option2(
    config: Option2, clip_count: int, report_date: date
) -> dict:
    """One rectangle per movable block, so the preview can let them be dragged."""
    boxes: dict = {}
    for item in blocks_option2(config, clip_count, report_date):
        rect = QRectF(item.x, item.y, max(item.width, 1.0), max(item.height, 1.0))
        boxes[item.group] = (rect if item.group not in boxes
                             else boxes[item.group].united(rect))
    return boxes


def render_option2(
    config: Option2,
    clip_count: int,
    report_date: date,
    warnings: Optional[list[str]] = None,
) -> QImage:
    """Draw the blank-page cover: logo, big heading, divider, date, count."""
    _ensure_gui()

    canvas = QImage(PAGE_WIDTH, PAGE_HEIGHT, QImage.Format_ARGB32)
    canvas.fill(QColor(config.background_colour or "#FFFFFF"))

    painter = QPainter()
    if not painter.begin(canvas):
        _note(warnings, "The generated cover page could not be drawn.")
        return canvas

    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        colour = QColor(config.title_colour or "#122A52")

        if config.background_path:
            try:
                backdrop = _load(config.background_path)
                if backdrop.isNull() or not backdrop.width() or not backdrop.height():
                    raise ValueError("unreadable image")
                opacity = min(1.0, max(0.02, float(config.background_opacity)))
                fit = max(
                    PAGE_WIDTH / backdrop.width(), PAGE_HEIGHT / backdrop.height()
                )
                draw_w = backdrop.width() * fit
                draw_h = backdrop.height() * fit
                painter.setOpacity(opacity)
                painter.drawImage(
                    QRectF(
                        (PAGE_WIDTH - draw_w) / 2,
                        (PAGE_HEIGHT - draw_h) / 2,
                        draw_w,
                        draw_h,
                    ),
                    backdrop,
                )
                painter.setOpacity(1.0)
            except Exception as error:  # noqa: BLE001
                painter.setOpacity(1.0)
                _note(
                    warnings,
                    f"Cover background image could not be used ({error}); "
                    "the cover was drawn without it.",
                )

        if config.show_border:
            pen = QPen(colour)
            pen.setWidthF(6)
            pen.setJoinStyle(Qt.MiterJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(50, 50, PAGE_WIDTH - 100, PAGE_HEIGHT - 100))
            pen.setWidthF(2)
            painter.setPen(pen)
            painter.drawRect(QRectF(64, 64, PAGE_WIDTH - 128, PAGE_HEIGHT - 128))
            for corner_x, corner_y in (
                (50, 50),
                (PAGE_WIDTH - 50, 50),
                (50, PAGE_HEIGHT - 50),
                (PAGE_WIDTH - 50, PAGE_HEIGHT - 50),
            ):
                painter.fillRect(QRectF(corner_x - 7, corner_y - 7, 14, 14), colour)

        logo_image: Optional[QImage] = None
        logo_dims: Optional[tuple[int, int]] = None
        if config.logo_path:
            try:
                logo_image = _load(config.logo_path)
                if (logo_image.isNull() or not logo_image.width()
                        or not logo_image.height()):
                    raise ValueError("unreadable image")
                logo_dims = (logo_image.width(), logo_image.height())
            except Exception as error:  # noqa: BLE001
                logo_image = None
                _note(
                    warnings,
                    f"Cover logo could not be used ({error}); "
                    "the cover was drawn without it.",
                )

        ops, divider_y, logo_rect = _compose(
            config, clip_count, report_date, logo_dims, warnings)

        if logo_image is not None and logo_rect is not None:
            dx, dy = _offset(config, "logo")
            painter.drawImage(logo_rect.translated(dx, dy), logo_image)

        dx, dy = _offset(config, "heading")
        pen = QPen(colour)
        pen.setWidthF(3)
        painter.setPen(pen)
        painter.drawLine(QPointF(527 + dx, divider_y + dy),
                         QPointF(1127 + dx, divider_y + dy))
        painter.fillRect(
            QRectF(CENTRE_X - 6 + dx, divider_y - 6 + dy, 12, 12), colour)

        for op in ops:
            try:
                shift_x, shift_y = _offset(config, op.group)
                _draw_text(painter, op, dx=shift_x, dy=shift_y)
            except Exception as error:  # noqa: BLE001 - one bad line, not a lost cover
                _note(warnings, f"A line of cover text could not be drawn ({error}).")
    finally:
        painter.end()

    return canvas


# ----------------------------------------------------------------------- output


def to_png_bytes(image: QImage) -> bytes:
    """PNG bytes for whichever builder is placing the cover."""
    if image is None or image.isNull():
        return b""
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)
