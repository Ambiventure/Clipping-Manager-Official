"""Build the division sentiment dossier, as PDF and as Word.

The standard newspad is a running order: cover, then every clipping of the day in
the sequence the user arranged. The dossier answers a different question, the one
the DRM's office actually asks - how did *this* division's coverage split between
positive, neutral, negative and digital. So the clippings are regrouped under the
four category headings and the page is given over to the clipping itself: a uniform
28pt margin all round rather than the newspad's narrow frame, no caption unless one
is asked for, no footer.

Digital items are the exception, and the reason this file is not simply the standard
builder with different margins. A screenshot of a web page is useless without the
address it came from, so each one carries a link pill under the image with a real
annotation behind it, and two short screenshots share a page rather than wasting
half a sheet each. The pairing rule is deliberately conservative: a tall clipping
never pairs, because two portrait strips squeezed onto one page are unreadable in
print, which is where these end up.

Anything that can fail does so for one clipping only - a bad image, an unreadable
cover, a URL that will not set - and is reported in plain language on the Result.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import pymupdf
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml.ns import qn
from docx.oxml.shared import OxmlElement
from docx.shared import Pt, RGBColor

from .. import version
from ..core import assemble, ourfiles, reportrecord
from ..core import sentiment as sentiment_core
from ..core.models import Clip, Section
from . import layout
from .build_docx import DEVANAGARI_FONT, _add_hyperlink, _place_picture
from .build_pdf import Result, Typeface, _draw_line, _image_bytes

Progress = Optional[Callable[[int, int, str], None]]

# --- page furniture ----------------------------------------------------------
MARGIN = 28.0                # uniform, unlike the newspad's asymmetric frame
BOTTOM_SPACE = 8.0
HEADER_HEIGHT = 36.0
HEADER_BASELINE = 23.0
HEADER_BOTTOM = 44.0
HEADER_SIZE = 10.0
CATEGORY_SIZE = 30.0
CATEGORY_ADVANCE = 36.0
#: The platform's own line, under the category's. Smaller, because the
#: category is what the section IS and the platform says which run of it this
#: is: at the same size the two read as two headings for one page.
PLATFORM_SIZE = 17.0
PLATFORM_ADVANCE = 23.0


def platform_line(clip) -> str:
    """The heading a clipping's platform run carries here, or "".

    The words the clipping itself carries win, which is what "Group social by
    platform" writes onto it and what the press report prints - so a heading
    renamed once reads the same in both documents. Nothing is worked out from
    the address here: a dossier is not to start naming platforms that the
    report has not been told to name.
    """
    return str(getattr(clip, "section_title", "") or "").strip()
TITLE_SIZE = 11.0
# What the dossier has always done with a clipping title. The panel starts here,
# so a dossier built without touching it is unchanged.
# The fallback for a dossier built without a panel - kept in step with the panel's
# own default so a headless build and the application agree.
DOSSIER_HEADING = dict(size=16.0, align="left", bold=True, family="sans")

# The order the dossier reads in: all the positive coverage, then neutral, then
# negative, then digital. It was digital before negative until the department
# said otherwise; this is the order they asked for, and it happens to be the
# left-to-right order of the columns on the board as well, so the document now
# reads the way the work surface looks. Anything not listed here still gets
# printed, after these, so a new category cannot vanish.
REPORT_ORDER = (Section.POSITIVE, Section.NEUTRAL, Section.NEGATIVE,
                Section.DIGITAL)


def report_columns() -> tuple:
    """Every category, in reading order, with any newcomer on the end."""
    rest = tuple(c for c in sentiment_core.COLUMNS if c not in REPORT_ORDER)
    return tuple(c for c in REPORT_ORDER if c in sentiment_core.COLUMNS) + rest


def printed_columns(options: SentimentOptions) -> tuple:
    """((category, printed at all, says Nil when empty), ...) for this dossier.

    With a print order set on the sentiment page, that order and its switches:
    a category switched on is printed, and prints "Nil - no clips" when it
    holds nothing; one switched off is not printed at all, whether it holds
    anything or not - which is what the switch says it does, and what the
    export warns about when it drops clippings.

    Without a print order - a dossier built by something older, or by a test -
    every category that holds a clipping, in the reading order, and nothing at
    all for the ones that do not: exactly as before this existed.
    """
    plan = getattr(options, "print_plan", ()) or ()
    if plan:
        known = {column.value: column for column in sentiment_core.COLUMNS}
        out = []
        for value, on in plan:
            column = known.get(str(getattr(value, "value", value)))
            if column is not None:
                out.append((column, bool(on), bool(on)))
        if out:
            return tuple(out)
    return tuple((column, True, False) for column in report_columns())


def _left_out(column: Section, items) -> str:
    """What the export says about a category somebody switched off."""
    heading, _colour = _category_style(column)
    return (f"{heading} is switched off in the print order, so "
            f"{len(items)} clipping{'s were' if len(items) != 1 else ' was'} "
            f"left out of the dossier.")


def nil_line(options: SentimentOptions, column: Section) -> str:
    """What an empty category prints. The category names itself when the
    coloured headers are switched off and nothing else would say which one
    this page is."""
    if options.include_category_headers:
        return NIL_WORDS
    heading, _colour = _category_style(column)
    return f"{heading} - {NIL_WORDS}"
DOCX_ALIGNMENTS = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
}
TITLE_GAP = 8.0
NAVY = "#122A52"
TITLE_COLOUR = "#1A1F2B"

# --- the digital link pill ---------------------------------------------------
# The pill is sized from its text rather than the other way round, so raising the
# type raises the box around it instead of crowding it.
PILL_TEXT_SIZE = 13.0
PILL_PADDING = 12.0
PILL_HEIGHT = PILL_TEXT_SIZE + PILL_PADDING
PILL_TRAIL = 8.0
LINK_BLOCK = PILL_HEIGHT + PILL_TRAIL
PILL_RADIUS = 4.0
PILL_FILL = "#F3F4F6"
PILL_STROKE = "#CBD5E1"
PILL_STROKE_WIDTH = 0.8
PILL_PREFIX = "Article Link: "
PREFIX_COLOUR = "#475569"
URL_COLOUR = "#1D4ED8"
URL_MIN_CHARS = 25
URL_TRIM_STEP = 4
UNDERLINE_DROP = 1.5
UNDERLINE_WIDTH = 0.75

# --- pairing two short digital clippings onto one page -----------------------
TALL_FRACTION = 0.56         # of the usable height
TALL_ASPECT = 0.8            # narrower than this is a portrait strip
PAIR_BUDGET = 1.25           # of the usable height, before both are scaled down
PAIR_SPACING = 18.0
PAIR_GAP_ABOVE_LINK = 5.0
PAIR_GAP_BEFORE_RULE = 3.0
PAIR_GAP_AFTER_RULE = 7.0
DIVIDER_INSET = 36.0
DIVIDER_COLOUR = "#E2E8F0"
DIVIDER_WIDTH = 0.6

# Word cannot be measured, only estimated: these are the vertical costs of the
# furniture paragraphs, plus slack so a full-height image never spills onto a
# second page and pushes the whole document out of step.
DOCX_HEADER_COST = 26.0
DOCX_CATEGORY_COST = 46.0
DOCX_TITLE_COST = 22.0          # kept for the pair path, which draws no title
DOCX_TITLE_AFTER = 6.0          # the space_after set on a title paragraph
DOCX_LINE_SPACING = 1.32        # Word's single spacing, near enough to measure by
# Roughly how wide a character is as a fraction of the point size. Devanagari
# conjuncts run wider than Latin, so this errs high on purpose: over-reserving
# costs a few points of picture, under-reserving costs a whole page.
DOCX_CHAR_WIDTH = 0.52


def _docx_title_cost(text: str, size: float, usable_width: float) -> float:
    """How much vertical room a title paragraph will take in Word.

    This used to be the constant DOCX_TITLE_COST, from when every title printed
    at one fixed size. The size is the person's choice now, and a long Hindi
    masthead at 16pt wraps to two lines - so the constant under-reserved by more
    than twenty points, the picture was sized to fill room that was not there,
    and Word moved it to a page of its own, leaving the headline stranded on the
    page before. Which is exactly what was reported.
    """
    words = (text or "").strip()
    if not words:
        return 0.0
    per_line = max(8.0, usable_width / max(1.0, size * DOCX_CHAR_WIDTH))
    lines = max(1, int(len(words) / per_line) + (1 if len(words) % per_line else 0))
    return lines * size * DOCX_LINE_SPACING + DOCX_TITLE_AFTER
# What one link paragraph costs a Word page. Follows the type size, so raising
# the address does not quietly push a picture onto the next sheet.
DOCX_LINK_COST = PILL_TEXT_SIZE + 16.0
# Word needs real headroom, not a token. The arithmetic here reserves the title
# and the picture, but Word also charges for things this code never sees: the
# empty paragraph that carries the page break takes a line of its own on the new
# page, the picture's own paragraph has a line height, and the document style adds
# spacing after each one. At 14pt of slack the sums came out exactly at the page
# limit, so any of those tipped the picture onto a page by itself and left its
# headline stranded on the page before - which is what was reported. 48 buys about
# 34pt of picture and buys back the page.
DOCX_SLACK = 48.0
DOCX_DIVIDER = ourfiles.DIVIDER_MARK * 44

_FALLBACK_STYLES = {
    Section.POSITIVE: ("Positive", "#16A34A"),
    Section.NEUTRAL: ("Neutral", "#2563EB"),
    Section.NEGATIVE: ("Negative", "#DC2626"),
    Section.DIGITAL: ("Digital News", "#7C3AED"),
    Section.ADVERTISEMENT: ("Advertisement", "#B45309"),
}

#: What an empty category says on its own page when it is switched on. The
#: words live in core/ourfiles because the reader has to know them too: read
#: back, that page is furniture rather than a caption without a clipping.
NIL_WORDS = ourfiles.NIL_WORDS
NIL_SIZE = 16.0


@dataclass
class SentimentOptions:
    """Everything the export dialog lets the user decide about a dossier."""

    include_cover: bool = False
    include_division_header: bool = False
    include_category_headers: bool = True
    # True: the headline typed on a card exists nowhere else, so a dossier built
    # without it loses the naming work entirely.
    include_clip_titles: bool = True
    custom_division_heading: str = ""
    custom_report_title: str = ""
    page: str = "a4"
    cover_config: object | None = None
    # The dossier's own heading settings, from the panel on the sentiment page.
    # It governs the clipping titles and the paper - not the coloured category
    # headers, which are the dossier's identity rather than a typographic choice.
    heading: object | None = None
    # ((category value, print it even when empty), ...) - the print order card
    # on the sentiment page. Empty means the old behaviour: every category that
    # holds something, in the reading order, and nothing for the ones that do
    # not (see printed_columns).
    print_plan: tuple = ()


# --------------------------------------------------------------- small helpers


def _rgb(colour: str) -> tuple[float, float, float]:
    value = (colour or "").lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    try:
        number = int(value, 16)
    except ValueError:
        number = 0x122A52
    return ((number >> 16 & 255) / 255.0, (number >> 8 & 255) / 255.0,
            (number & 255) / 255.0)


def _titles(options: SentimentOptions, code: str, report_date: date, total: int
            ) -> tuple[str, str]:
    """Document title and subject, which is where the two custom headings land.

    The dossier prints nothing of its own above the clippings - any cover text is
    the cover designer's - so these settings would otherwise have nowhere to go.
    """
    stamp = report_date.strftime("%d.%m.%Y")
    title = (
        options.custom_report_title.strip()
        or f"{code or 'Northern Railway'} News Report - {stamp}"
    )
    subject = (
        options.custom_division_heading.strip()
        or f"Northern Railway media coverage, {total} clippings"
    )
    return title, subject


def _hex_pair(colour: str) -> str:
    value = (colour or "").lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    return value.upper()[:6] or "122A52"


def _category_style(column: Section) -> tuple[str, str]:
    """The heading text and colour for one column.

    Deferred because ``ui.theme`` is the UI's file: an export run on a machine
    where the theme cannot load should still produce a correctly coloured dossier.
    """
    label, colour = _FALLBACK_STYLES.get(column, ("News", NAVY))
    try:
        from ..ui import theme

        style = theme.SENTIMENT_STYLES[column.value]
        label, colour = style["label"], style["colour"]
    except Exception:  # noqa: BLE001 - the fallback carries the same colours
        pass
    # "Positive" prints as "Positive News"; an advertisement is not news and
    # prints as itself.
    if column is Section.ADVERTISEMENT or label.lower().endswith("news"):
        return label, colour
    return f"{label} News", colour


def _division_code(division: Any) -> str:
    if division is None:
        return ""
    return str(getattr(division, "code", division) or "").strip()


def _banner_name(division: Any, options: SentimentOptions) -> str:
    """What the navy strip across the top of each page says.

    The board's own heading field wins; otherwise the division's full name, which
    reads better on a report than the three-letter code the clippings are filed
    under.
    """
    custom = options.custom_division_heading.strip()
    if custom:
        return custom
    full = str(getattr(division, "full_name", "") or "").strip()
    return full or _division_code(division) or "All divisions"


def _buckets(clips: Sequence[Clip], code: str) -> dict[Section, list[Clip]]:
    """The included clippings for this division, split into the four columns."""
    found: dict[Section, list[Clip]] = {c: [] for c in sentiment_core.COLUMNS}
    for clip in clips:
        if not clip.include:
            continue
        if code and clip.division and clip.division != code:
            continue
        found[sentiment_core.column_for(clip.section)].append(clip)
    return found


def _natural(clip: Clip) -> tuple[float, float]:
    width, height = clip.rendered_size()
    if width <= 0 or height <= 0:
        width = height = 1
    return width * layout.POINTS_PER_PIXEL, height * layout.POINTS_PER_PIXEL


def _fit(clip: Clip, box_width: float, box_height: float) -> tuple[float, float]:
    """Size one clipping into a box by the standard report's rules."""
    natural_width, natural_height = _natural(clip)
    scale = min(box_width / natural_width, box_height / natural_height,
                layout.MAX_UPSCALE)
    return natural_width * scale, natural_height * scale


def _column_size(clip: Clip, usable_width: float) -> tuple[float, float]:
    """Size when the clipping is given the full column width, upscale still capped."""
    natural_width, natural_height = _natural(clip)
    scale = min(usable_width / natural_width, layout.MAX_UPSCALE)
    return natural_width * scale, natural_height * scale


def _link_height(clip: Clip) -> float:
    return LINK_BLOCK if (clip.url or "").strip() else 0.0


def _full_url(url: str) -> str:
    clean = (url or "").strip()
    if not clean:
        return ""
    lowered = clean.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return clean
    return f"https://{clean}"


_SIEVE = None


def _sieve():
    """The word list, built once per run of the program rather than per caption.

    Rebuilt whenever the list is edited: `forget_sieve` is called from the
    editor. Compiling a dozen patterns for every caption on a two-hundred
    clipping morning is work nobody needs done twice.
    """
    global _SIEVE
    if _SIEVE is None:
        from ..core import wordlist

        _SIEVE = wordlist.Sieve()
    return _SIEVE


def forget_sieve() -> None:
    global _SIEVE
    _SIEVE = None


def prints_a_title(clip, column) -> bool:
    """Whether a heading goes above this clipping on the page.

    Digital coverage used to be excluded outright, and that was right at the
    time: the one strip a digital card had held the article link, so its
    "title" WAS the address and printing it over the picture said the same
    thing twice in two places.

    A digital card carries a headline of its own now - asked for with the Add
    title button beside the link - so a headline that has been typed there is a
    real heading and belongs on the page. One that is only the address again is
    still not.
    """
    title = clip.effective_label.strip()
    if not title:
        return False
    if column is not Section.DIGITAL:
        return True
    return title != (clip.url or "").strip()


def _origin(origins: Optional[dict], clip: Clip) -> tuple:
    """The clipping this one was made from, and the band burned onto it.

    A burned dossier is handed copies whose names have been cleared, because
    the names are inside the pictures now (build_burned.flatten). The record
    has to carry what was burned in, so the names come from the original and
    the band says where to crop it back to. Anything else - the ordinary
    dossier - is its own origin and has no band.
    """
    if origins:
        found = origins.get(getattr(clip, "uid", ""))
        if found:
            return found
    return clip, None


def _pairs_with(
    first: Clip, second: Optional[Clip], usable_width: float, usable_height: float
) -> bool:
    """Whether two digital clippings may share a page.

    Both must be short and neither may be a portrait strip; then the two images and
    their link pills together must be within a quarter over the page, which is the
    most that can be scaled back down without either becoming unreadable.
    """
    if second is None:
        return False
    for clip in (first, second):
        width, height = _column_size(clip, usable_width)
        aspect = width / height if height else 1.0
        if height > usable_height * TALL_FRACTION or aspect < TALL_ASPECT:
            return False
    combined = (
        _column_size(first, usable_width)[1]
        + _link_height(first)
        + _column_size(second, usable_width)[1]
        + _link_height(second)
        + PAIR_SPACING
    )
    return combined <= usable_height * PAIR_BUDGET


# ------------------------------------------------------------------- the cover


# The cover is drawn at print resolution, then placed as one picture - the same
# arrangement the press report's cover uses.
COVER_DPI = 200.0


def _cover_png(
    config: object, clip_count: int, page: str, warnings: list[str],
) -> Optional[bytes]:
    """Rasterise the designed cover, or explain why there is no cover.

    ``render`` takes the count of clippings and the name of a paper size - it
    prints the count on the sheet. It used to be reached through a shim that
    guessed between three call shapes, and the shape it guessed first passed the
    page WIDTH where the count belongs and the page HEIGHT where the paper's name
    belongs. That raised AttributeError rather than TypeError, so the shim did not
    fall through to the next shape either: every dossier came out with no cover
    and a warning nobody was shown.
    """
    try:
        from ..core import sentiment_cover
    except Exception:  # noqa: BLE001 - the designer is optional
        warnings.append(
            "The cover page designer is not available, so the dossier was written "
            "without a cover."
        )
        return None
    try:
        rendered = sentiment_cover.render(
            config, int(clip_count), page, COVER_DPI / 72.0)
        return _as_png(rendered)
    except Exception as exc:  # noqa: BLE001 - a cover is never worth the document
        warnings.append(
            f"The cover page could not be drawn ({type(exc).__name__}: {exc}); "
            f"the dossier starts at the first clipping."
        )
        return None


def _as_png(rendered: Any) -> bytes:
    """Whatever the cover came back as, hand back PNG bytes."""
    if isinstance(rendered, (bytes, bytearray)):
        return bytes(rendered)
    if isinstance(rendered, (str, Path)):
        return Path(rendered).read_bytes()

    from PySide6.QtCore import QBuffer, QByteArray
    from PySide6.QtGui import QImage

    image = rendered.toImage() if hasattr(rendered, "toImage") else rendered
    if isinstance(image, QImage):
        store = QByteArray()
        buffer = QBuffer(store)
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        if not image.save(buffer, "PNG"):
            raise RuntimeError("the cover image could not be encoded")
        buffer.close()
        return bytes(store)
    if hasattr(rendered, "save"):  # a PIL image
        stream = io.BytesIO()
        rendered.save(stream, "PNG")
        return stream.getvalue()
    raise TypeError(f"unsupported cover image of type {type(rendered).__name__}")


# --------------------------------------------------------------------- the PDF


def _pdf_text(
    sheet, typeface: Typeface, text: str, x: float, baseline: float, size: float,
    colour: str, bold: bool, width: float = 400.0,
) -> None:
    """One short line at a known baseline, shaped when it has to be.

    The base-14 fonts cover Latin-1 and nothing else, and MuPDF does not object
    when asked for anything outside it: it quietly substitutes a middle dot for
    each character it cannot set, and reports success. So a division name typed
    in Hindi came out as a row of dots across the top of every page of the
    dossier, and the fallback below - which is the correct, shaped path - never
    ran, because there was no exception to catch.

    Whether the text is Latin-1 is the question, so that is what is asked. The
    exception branch stays for the ordinary failures it was written for.
    """
    try:
        text.encode("latin-1")
    except UnicodeEncodeError:
        _draw_line(
            sheet, typeface, text,
            pymupdf.Rect(x, baseline - size, x + width, baseline + size * 0.6),
            size, align="left", colour=colour, bold=bold,
        )
        return
    try:
        sheet.insert_text(
            (x, baseline), text, fontname="hebo" if bold else "helv",
            fontsize=size, color=_rgb(colour),
        )
    except Exception:  # noqa: BLE001 - a base-14 font cannot set every character
        _draw_line(
            sheet, typeface, text,
            pymupdf.Rect(x, baseline - size, x + width, baseline + size * 0.6),
            size, align="left", colour=colour, bold=bold,
        )


def _pdf_division_strip(
    sheet, typeface: Typeface, page_width: float, banner: str, column: Section,
) -> None:
    sheet.draw_rect(
        pymupdf.Rect(0, 0, page_width, HEADER_HEIGHT),
        color=None, fill=_rgb(NAVY),
    )
    _pdf_text(
        sheet, typeface, f"NORTHERN RAILWAY  |  {banner}", MARGIN,
        HEADER_BASELINE,
        HEADER_SIZE, "#FFFFFF", bold=True,
        width=page_width - MARGIN * 2,
    )
    # No category badge here. This strip is drawn on every page, and the category
    # is already announced once, in its own heading, at the top of its section -
    # stamping it again on all thirty sheets is what made the report read as
    # though it changed category on every page.


def _pdf_link_pill(
    sheet, typeface: Typeface, url: str, x: float, y: float, max_width: float,
) -> float:
    """Draw the pill and the annotation behind it. Returns the height it used."""
    clean = (url or "").strip()
    if not clean:
        return 0.0

    prefix_width = pymupdf.get_text_length(
        PILL_PREFIX, fontname="hebo", fontsize=PILL_TEXT_SIZE
    )
    shown = clean
    room = max_width - prefix_width - 28.0
    while (
        pymupdf.get_text_length(shown, fontname="helv", fontsize=PILL_TEXT_SIZE) > room
        and len(shown) > URL_MIN_CHARS
    ):
        shown = shown[: len(shown) - URL_TRIM_STEP] + "..."

    url_width = pymupdf.get_text_length(shown, fontname="helv", fontsize=PILL_TEXT_SIZE)
    pill_width = min(max_width, round(prefix_width + url_width + 24.0))
    pill_x = round(x + (max_width - pill_width) / 2.0)
    pill_y = round(y)
    pill = pymupdf.Rect(pill_x, pill_y, pill_x + pill_width, pill_y + PILL_HEIGHT)

    sheet.draw_rect(
        pill, color=_rgb(PILL_STROKE), fill=_rgb(PILL_FILL),
        width=PILL_STROKE_WIDTH,
        radius=min(0.5, PILL_RADIUS / min(pill_width, PILL_HEIGHT)),
    )

    # Centred in the pill: half the box, plus roughly a third of the type for
    # the drop below the baseline. Written out rather than measured because the
    # pill is a fixed shape and this is what keeps the text sitting in it.
    baseline = pill_y + PILL_HEIGHT / 2.0 + PILL_TEXT_SIZE * 0.36
    _pdf_text(sheet, typeface, PILL_PREFIX, pill_x + 10, baseline, PILL_TEXT_SIZE,
              PREFIX_COLOUR, bold=True)
    url_x = pill_x + 10 + prefix_width
    _pdf_text(sheet, typeface, shown, url_x, baseline, PILL_TEXT_SIZE, URL_COLOUR,
              bold=False)
    sheet.draw_line(
        pymupdf.Point(url_x, baseline + UNDERLINE_DROP),
        pymupdf.Point(url_x + url_width, baseline + UNDERLINE_DROP),
        color=_rgb(URL_COLOUR), width=UNDERLINE_WIDTH,
    )
    sheet.insert_link({"kind": pymupdf.LINK_URI, "from": pill, "uri": _full_url(clean)})
    return LINK_BLOCK


def _pdf_head(
    sheet, typeface: Typeface, options: SentimentOptions, page_width: float,
    banner: str, column: Section, first_in_category: bool,
    platform: str = "", style=None,
) -> float:
    """Draw the page furniture. Returns the y the content may start at."""
    cursor = MARGIN
    if options.include_division_header:
        _pdf_division_strip(sheet, typeface, page_width, banner, column)
        cursor = HEADER_BOTTOM
    if options.include_category_headers and first_in_category:
        heading, colour = _category_style(column)
        _draw_line(
            sheet, typeface, heading,
            pymupdf.Rect(MARGIN, cursor, page_width - MARGIN,
                         cursor + CATEGORY_SIZE * 1.5),
            CATEGORY_SIZE, align="left", colour=colour, bold=True,
        )
        cursor += CATEGORY_ADVANCE
    if platform:
        # In the colour the headings panel is set to, so the platform lines in
        # the dossier and in the press report are the same colour.
        ink = getattr(style, "colour", "") or _category_style(column)[1]
        _draw_line(
            sheet, typeface, platform,
            pymupdf.Rect(MARGIN, cursor, page_width - MARGIN,
                         cursor + PLATFORM_SIZE * 1.5),
            PLATFORM_SIZE, align="left", colour=ink, bold=True,
        )
        cursor += PLATFORM_ADVANCE
    return cursor


def build_pdf(
    clips: Sequence[Clip],
    output: str | Path,
    division: Any = None,
    report_date: Optional[date] = None,
    options: Optional[SentimentOptions] = None,
    progress: Progress = None,
    origins: Optional[dict] = None,
) -> Result:
    """Write the division sentiment dossier as a PDF.

    ``origins`` is the map build_burned.flatten fills when the pictures have
    had their headlines burned into them - see _origin.
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_date = report_date or date.today()
    options = options or SentimentOptions()
    warnings: list[str] = []

    code = _division_code(division)
    banner = _banner_name(division, options)
    buckets = _buckets(clips, code)
    total = sum(len(items) for items in buckets.values())

    document = pymupdf.open()
    typeface = Typeface()
    style = getattr(options, "heading", None) or layout.HeadingStyle(
        page=options.page, **DOSSIER_HEADING)
    page_width, page_height = layout.page_size(style.page)
    usable_width = page_width - MARGIN * 2

    title, subject = _titles(options, code, report_date, total)
    document.set_metadata({
        "title": title,
        "subject": subject,
        "author": "Northern Railway Media Monitoring Cell",
        "creator": f"Clippings Manager {version.describe()}",
        "producer": f"Clippings Manager {version.describe()}",
        "keywords": assemble.MADE_HERE,
    })

    # What this dossier is made of, written into the file itself
    # (core/reportrecord). A burned dossier has no text on it at all, so
    # without this there is nothing for an import to read.
    record = reportrecord.Record(
        "dossier-burned" if origins else "dossier", "pdf", report_date,
        division=code)

    if options.include_cover:
        if options.cover_config is None:
            warnings.append(
                "A cover page was asked for but no cover settings were supplied; "
                "the dossier starts at the first clipping."
            )
        else:
            data = _cover_png(options.cover_config, len(clips), style.page,
                              warnings)
            if data:
                cover = document.new_page(width=page_width, height=page_height)
                try:
                    cover.insert_image(
                        pymupdf.Rect(0, 0, page_width, page_height), stream=data
                    )
                    record.cover = True
                except Exception as exc:  # noqa: BLE001
                    warnings.append(
                        f"The cover page could not be placed "
                        f"({type(exc).__name__}); it was left blank."
                    )

    written = 0
    done = 0
    for column, printed, says_nil in printed_columns(options):
        items = buckets.get(column) or []
        if not printed:
            if items:
                warnings.append(_left_out(column, items))
            continue
        if not items:
            if not says_nil:
                continue
            # Switched on and holding nothing: one page that says so, so the
            # reader knows the category was looked at and was empty.
            sheet = document.new_page(width=page_width, height=page_height)
            cursor = _pdf_head(sheet, typeface, options, page_width, banner,
                               column, True)
            _draw_line(
                sheet, typeface, nil_line(options, column),
                pymupdf.Rect(MARGIN, cursor, page_width - MARGIN,
                             cursor + NIL_SIZE * 2.0),
                NIL_SIZE, align="left", colour=TITLE_COLOUR, bold=False,
            )
            record.nil.append(column.value)
            continue

        first_in_category = True
        # Each platform named once inside the category, over the first of its
        # run - the same rule the press report's headings follow.
        named_here: set = set()
        index = 0
        while index < len(items):
            clip = items[index]
            done += 1
            if progress:
                progress(done, total, clip.effective_label or "clipping")

            platform = platform_line(clip)
            if platform in named_here:
                platform = ""
            elif platform:
                named_here.add(platform)
            sheet = document.new_page(width=page_width, height=page_height)
            cursor = _pdf_head(sheet, typeface, options, page_width, banner,
                               column,
                               first_in_category, platform, style)
            first_in_category = False

            # A title belongs to one clipping, so two titled clippings never share a
            # page: the second heading would read as a subtitle of the first.
            partner: Optional[Clip] = None
            if column is Section.DIGITAL and not options.include_clip_titles:
                usable_height = page_height - cursor - MARGIN - BOTTOM_SPACE
                candidate = items[index + 1] if index + 1 < len(items) else None
                if _pairs_with(clip, candidate, usable_width, usable_height):
                    partner = candidate

            # The title is measured now and drawn later, once the picture's
            # size is known. It used to be drawn here, at the top of the space,
            # while the picture was centred in what was left - which put the
            # headline half a page above the clipping it names.
            title_text = ""
            title_height = 0.0
            if options.include_clip_titles and prints_a_title(clip, column):
                title_text = _sieve().clean(clip.printed_caption.strip())
                if title_text:
                    scratch = pymupdf.open()
                    measuring = scratch.new_page(width=page_width,
                                                 height=page_height)
                    title_height = _draw_line(
                        measuring, typeface, title_text,
                        pymupdf.Rect(MARGIN, MARGIN, page_width - MARGIN,
                                     MARGIN + style.leading() * 3.4),
                        style.size, align=style.align, colour=TITLE_COLOUR,
                        bold=style.bold, family=style.family,
                    )
                    scratch.close()
            title_block = (title_height + TITLE_GAP) if title_text else 0.0

            usable_height = page_height - cursor - MARGIN - BOTTOM_SPACE
            # Whether an item shows a link is a fact about the item, not about
            # the column it was dropped into: an electronic or social clipping
            # imported from the 360 Degree document is identified by its address
            # wherever the user files it.
            linked = bool((clip.url or "").strip())

            if partner is not None:
                pair = (clip, partner)
                budget = max(1.0, usable_height - _link_height(clip)
                             - _link_height(partner) - PAIR_SPACING)
                sizes = [_column_size(one, usable_width) for one in pair]
                stacked = sizes[0][1] + sizes[1][1]
                if stacked > budget and stacked > 0:
                    shrink = budget / stacked
                    sizes = [(w * shrink, h * shrink) for w, h in sizes]

                for number, (one, (draw_width, draw_height)) in enumerate(
                    zip(pair, sizes)
                ):
                    if number:
                        cursor += PAIR_GAP_BEFORE_RULE
                        sheet.draw_line(
                            pymupdf.Point(MARGIN + DIVIDER_INSET, cursor),
                            pymupdf.Point(page_width - MARGIN - DIVIDER_INSET, cursor),
                            color=_rgb(DIVIDER_COLOUR), width=DIVIDER_WIDTH,
                        )
                        cursor += PAIR_GAP_AFTER_RULE
                    left = MARGIN + (usable_width - draw_width) / 2.0
                    try:
                        data = _image_bytes(one)
                        sheet.insert_image(
                            pymupdf.Rect(left, cursor, left + draw_width,
                                         cursor + draw_height),
                            stream=data,
                        )
                        written += 1
                    except Exception as exc:  # noqa: BLE001
                        warnings.append(_image_warning(one, exc))
                    else:
                        source, band = _origin(origins, one)
                        record.add(source, data, sheet=sheet.number,
                                   slot=number, printed="", band=band)
                    cursor += draw_height + PAIR_GAP_ABOVE_LINK
                    if (one.url or "").strip():
                        try:
                            cursor += _pdf_link_pill(sheet, typeface, one.url, MARGIN,
                                                     cursor, usable_width)
                        except Exception as exc:  # noqa: BLE001
                            warnings.append(_link_warning(one, exc))
                index += 2
                done += 1
                continue

            room = usable_height - (_link_height(clip) if linked else 0.0)
            draw_width, draw_height = _fit(
                clip, usable_width, max(1.0, room - title_block))
            left = MARGIN + (usable_width - draw_width) / 2.0

            # Heading and clipping are one block, and the block is centred.
            offset = max(0.0, (room - title_block - draw_height) / 2.0)
            if title_text:
                _draw_line(
                    sheet, typeface, title_text,
                    pymupdf.Rect(MARGIN, cursor + offset, page_width - MARGIN,
                                 cursor + offset + title_height + 4),
                    style.size, align=style.align, colour=TITLE_COLOUR,
                    bold=style.bold, family=style.family,
                )
            top = cursor + offset + title_block
            try:
                data = _image_bytes(clip)
                sheet.insert_image(
                    pymupdf.Rect(left, top, left + draw_width, top + draw_height),
                    stream=data,
                )
                written += 1
            except Exception as exc:  # noqa: BLE001 - one bad image costs one page
                warnings.append(_image_warning(clip, exc))
            else:
                source, band = _origin(origins, clip)
                record.add(source, data, sheet=sheet.number,
                           printed=title_text, band=band)

            if linked and (clip.url or "").strip():
                try:
                    _pdf_link_pill(sheet, typeface, clip.url, MARGIN,
                                   top + draw_height + BOTTOM_SPACE, usable_width)
                except Exception as exc:  # noqa: BLE001
                    warnings.append(_link_warning(clip, exc))
            index += 1

    if document.page_count == 0:
        document.new_page(width=page_width, height=page_height)
        warnings.append("There were no clippings to export, so the dossier is empty.")

    reportrecord.attach_pdf(document, record, warnings)
    document.save(str(output), garbage=4, deflate=True, clean=True)
    pages = document.page_count
    document.close()
    return Result(path=output, pages=pages, clippings=written, warnings=warnings)


def _image_warning(clip: Clip, exc: Exception) -> str:
    name = clip.effective_label.strip() or clip.source_ref or "unnamed"
    return (f"The clipping '{name}' could not be drawn ({type(exc).__name__}); "
            f"its place on the page was left blank.")


def _link_warning(clip: Clip, exc: Exception) -> str:
    name = clip.effective_label.strip() or clip.source_ref or "unnamed"
    return (f"The article link for '{name}' could not be added "
            f"({type(exc).__name__}); the clipping itself is unaffected.")


# -------------------------------------------------------------------- the Word


def _shade(paragraph, colour: str) -> None:
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:fill"), _hex_pair(colour))
    paragraph._p.get_or_add_pPr().append(shading)


def _docx_run(paragraph, text: str, size: float, colour: str, bold: bool = False):
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    value = _hex_pair(colour)
    run.font.color.rgb = RGBColor(int(value[0:2], 16), int(value[2:4], 16),
                                  int(value[4:6], 16))
    return run


def _docx_head(
    document, options: SentimentOptions, banner: str, column: Section,
    first_in_category: bool, platform: str = "", style=None,
) -> float:
    """Write the page furniture. Returns the vertical space it is expected to eat."""
    used = 0.0
    if options.include_division_header:
        paragraph = document.add_paragraph()
        _shade(paragraph, NAVY)
        _docx_run(paragraph, f"  NORTHERN RAILWAY  |  {banner}", HEADER_SIZE,
                  "#FFFFFF", bold=True)
        paragraph.paragraph_format.space_after = Pt(6)
        used += DOCX_HEADER_COST
    if options.include_category_headers and first_in_category:
        heading, colour = _category_style(column)
        paragraph = document.add_paragraph()
        _docx_run(paragraph, heading, CATEGORY_SIZE, colour, bold=True)
        paragraph.paragraph_format.space_after = Pt(8)
        used += DOCX_CATEGORY_COST
    if platform:
        ink = getattr(style, "colour", "") or _category_style(column)[1]
        paragraph = document.add_paragraph()
        _docx_run(paragraph, platform, PLATFORM_SIZE, ink, bold=True)
        paragraph.paragraph_format.space_after = Pt(6)
        used += PLATFORM_ADVANCE
    return used


def _docx_image(document, clip: Clip, width: float, height: float) -> bytes:
    """Place one clipping. Returns the bytes that actually went in, which is
    what the report's record is keyed on."""
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(4)
    return _place_picture(paragraph.add_run(), clip, Pt(width), Pt(height))


def _docx_link(document, url: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_after = Pt(6)
    _docx_run(paragraph, PILL_PREFIX, PILL_TEXT_SIZE, PREFIX_COLOUR, bold=True)
    _add_hyperlink(paragraph, _full_url(url), url.strip(), PILL_TEXT_SIZE)


def build_docx(
    clips: Sequence[Clip],
    output: str | Path,
    division: Any = None,
    report_date: Optional[date] = None,
    options: Optional[SentimentOptions] = None,
    progress: Progress = None,
    origins: Optional[dict] = None,
) -> Result:
    """Write the division sentiment dossier as a Word document.

    ``origins`` is the map build_burned.flatten fills when the pictures have
    had their headlines burned into them - see _origin.
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_date = report_date or date.today()
    options = options or SentimentOptions()
    warnings: list[str] = []

    code = _division_code(division)
    banner = _banner_name(division, options)
    buckets = _buckets(clips, code)
    total = sum(len(items) for items in buckets.values())

    style = getattr(options, "heading", None) or layout.HeadingStyle(
        page=options.page, **DOSSIER_HEADING)
    page_width, page_height = layout.page_size(style.page)
    usable_width = page_width - MARGIN * 2
    document = Document()
    section = document.sections[0]
    section.page_width = Pt(page_width)
    section.page_height = Pt(page_height)
    section.left_margin = section.right_margin = Pt(MARGIN)
    section.top_margin = section.bottom_margin = Pt(MARGIN)

    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(0)

    title, subject = _titles(options, code, report_date, total)
    document.core_properties.title = title
    document.core_properties.subject = subject
    document.core_properties.author = "Northern Railway Media Monitoring Cell"
    # The same two stamps the press report's Word file carries, so a dossier
    # imported back - into the press report or anywhere else - is known for
    # one of ours and read as one. Without them its clippings came back under
    # a division's rules. Word keeps the keywords through a save; a tool that
    # rewrites the description leaves them, and the other way about.
    document.core_properties.comments = f"Clippings Manager {version.describe()}"
    document.core_properties.keywords = assemble.MADE_HERE

    # The same record the dossier's PDF carries (core/reportrecord).
    record = reportrecord.Record(
        "dossier-burned" if origins else "dossier", "docx", report_date,
        division=code)

    pages = 0
    started = False

    if options.include_cover:
        if options.cover_config is None:
            warnings.append(
                "A cover page was asked for but no cover settings were supplied; "
                "the dossier starts at the first clipping."
            )
        else:
            # Text first: a Word file is edited afterwards, and a picture
            # cannot be. The picture is the fallback, not the preference.
            laid_out = False
            try:
                from ..core import sentiment_cover
                from . import word_cover

                laid_out = word_cover.add_cover(
                    document,
                    sentiment_cover.blocks(options.cover_config, len(clips), warnings),
                    page_width, page_height, warnings)
            except Exception as exc:  # noqa: BLE001 - fall back to the picture
                laid_out = False
                warnings.append(
                    f"The cover could not be written as text "
                    f"({type(exc).__name__}); the picture was used instead."
                )
            if laid_out:
                pages += 1
                started = True
                record.cover = True
            data = b"" if laid_out else _cover_png(
                options.cover_config, len(clips), style.page, warnings)
            if data:
                try:
                    paragraph = document.add_paragraph()
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    box_height = page_height - MARGIN * 2
                    width = min(usable_width, box_height * page_width / page_height)
                    paragraph.add_run().add_picture(io.BytesIO(data), width=Pt(width))
                    pages += 1
                    started = True
                    record.cover = True
                except Exception as exc:  # noqa: BLE001
                    warnings.append(
                        f"The cover page could not be placed "
                        f"({type(exc).__name__}); it was left out."
                    )

    written = 0
    done = 0
    # Counted the way the reader counts them, so the sheet number in the record
    # means the same thing at both ends: the cover picture is picture one.
    placed = len(document.element.body.findall(".//" + qn("a:blip")))
    for column, printed, says_nil in printed_columns(options):
        items = buckets.get(column) or []
        if not printed:
            if items:
                warnings.append(_left_out(column, items))
            continue
        if not items:
            if not says_nil:
                continue
            if started:
                document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            started = True
            pages += 1
            _docx_head(document, options, banner, column, True)
            paragraph = document.add_paragraph()
            _docx_run(paragraph, nil_line(options, column), NIL_SIZE,
                      TITLE_COLOUR)
            record.nil.append(column.value)
            continue

        first_in_category = True
        # Each platform named once inside the category - the PDF's rule.
        named_here: set = set()
        index = 0
        while index < len(items):
            clip = items[index]
            done += 1
            if progress:
                progress(done, total, clip.effective_label or "clipping")

            if started:
                document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            started = True
            pages += 1

            platform = platform_line(clip)
            if platform in named_here:
                platform = ""
            elif platform:
                named_here.add(platform)
            used = _docx_head(document, options, banner, column,
                              first_in_category, platform, style)
            first_in_category = False

            partner: Optional[Clip] = None
            if column is Section.DIGITAL and not options.include_clip_titles:
                free = page_height - MARGIN * 2 - used - DOCX_SLACK
                candidate = items[index + 1] if index + 1 < len(items) else None
                if _pairs_with(clip, candidate, usable_width, free):
                    partner = candidate

            caption = ""
            if options.include_clip_titles and prints_a_title(clip, column):
                caption = _sieve().clean(clip.printed_caption.strip())
                paragraph = document.add_paragraph()
                paragraph.alignment = DOCX_ALIGNMENTS[style.align]
                run = _docx_run(paragraph, caption, style.size, TITLE_COLOUR,
                                bold=style.bold)
                run.font.name = DEVANAGARI_FONT
                paragraph.paragraph_format.space_after = Pt(DOCX_TITLE_AFTER)
                # Measured from the title that was actually written, at the size
                # it was actually written at - so the picture below it is sized to
                # the room that is really left and stays on the same page.
                used += _docx_title_cost(caption, style.size, usable_width)

            linked = bool((clip.url or "").strip())
            free = page_height - MARGIN * 2 - used - DOCX_SLACK

            if partner is not None:
                pair = (clip, partner)
                budget = max(1.0, free - PAIR_SPACING - sum(
                    DOCX_LINK_COST for one in pair if (one.url or "").strip()
                ))
                sizes = [_column_size(one, usable_width) for one in pair]
                stacked = sizes[0][1] + sizes[1][1]
                if stacked > budget and stacked > 0:
                    shrink = budget / stacked
                    sizes = [(w * shrink, h * shrink) for w, h in sizes]

                for number, (one, (draw_width, draw_height)) in enumerate(
                    zip(pair, sizes)
                ):
                    if number:
                        rule = document.add_paragraph()
                        rule.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        _docx_run(rule, DOCX_DIVIDER, 9, DIVIDER_COLOUR)
                        rule.paragraph_format.space_after = Pt(6)
                    try:
                        data = _docx_image(document, one, draw_width, draw_height)
                        written += 1
                    except Exception as exc:  # noqa: BLE001
                        warnings.append(_image_warning(one, exc))
                    else:
                        source, band = _origin(origins, one)
                        record.add(source, data, sheet=placed, slot=number,
                                   printed="", band=band)
                        placed += 1
                    if (one.url or "").strip():
                        try:
                            _docx_link(document, one.url)
                        except Exception as exc:  # noqa: BLE001
                            warnings.append(_link_warning(one, exc))
                index += 2
                done += 1
                continue

            if linked and (clip.url or "").strip():
                free -= DOCX_LINK_COST
            draw_width, draw_height = _fit(clip, usable_width, max(1.0, free))
            try:
                data = _docx_image(document, clip, draw_width, draw_height)
                written += 1
            except Exception as exc:  # noqa: BLE001 - one bad image costs one page
                warnings.append(_image_warning(clip, exc))
            else:
                source, band = _origin(origins, clip)
                record.add(source, data, sheet=placed, printed=caption,
                           band=band)
                placed += 1

            if linked and (clip.url or "").strip():
                try:
                    _docx_link(document, clip.url)
                except Exception as exc:  # noqa: BLE001
                    warnings.append(_link_warning(clip, exc))
            index += 1

    if pages == 0:
        pages = 1
        warnings.append("There were no clippings to export, so the dossier is empty.")

    reportrecord.attach_docx(document, record, warnings)
    document.save(str(output))
    return Result(path=output, pages=pages, clippings=written, warnings=warnings)
