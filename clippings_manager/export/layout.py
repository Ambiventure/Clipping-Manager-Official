"""Page geometry for the newspad.

Two ways of placing a clipping, because the two are wanted for different reasons:

*   **Fit the page** (the default). One clipping per page, centred, scaled up or
    down to fill the printable area. A small Lucknow cutting is 208x457 pixels; at
    a fixed print resolution that lands as a stamp in the corner of an A4 sheet,
    which is not a page anybody wants to read.
*   **Original size.** Placed at 220 DPI against the left margin, top aligned. This
    reproduces the existing newspad exactly: across the 165 content pages of the
    real 26.08.2026 file, 148 of the images sit at left = 17.88pt at 220 DPI.

The image sits directly under its caption, not centred in the space below it: a
heading half a page away from the clipping it names reads as two unrelated things.
Enlargement is capped, because past a point a 130-pixel cutting is only bigger, not
clearer. It grows until it fills the page or hits the cap, whichever comes first.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.models import SECTION_NAMES

# --- paper -------------------------------------------------------------------
# Every face the panel offers. The exporters each map these to something they
# can draw with; anything not on this list is refused before it reaches them.
FAMILY_NAMES = (
    "sans", "serif", "mono", "book", "text",
    "arial", "calibri", "times", "georgia", "cambria", "garamond",
    "bookantiqua", "segoe", "tahoma", "verdana", "trebuchet", "couriernew",
    "comic",
)

PAGE_SIZES = {
    "a4": (595.28, 841.89),
    "letter": (612.0, 792.0),
}
DEFAULT_PAGE = "a4"

# --- how the heading is set --------------------------------------------------


@dataclass
class HeadingStyle:
    """What the caption above each clipping looks like, and the paper it sits on.

    Centred and not bold, as the newspad has always been. The size is the one
    exception: it was raised from 15 to 18 because a caption has to carry a whole
    sheet and 15 did not. Anyone can set any size in the panel.
    """

    page: str = DEFAULT_PAGE
    family: str = "sans"
    # 18, not the 15 the code used for years: under a clipping that fills an A4
    # sheet, 15pt reads small. CAPTION_SIZE stays 15 because it is the reference
    # the leading ratio and the original-size geometry are measured against - it
    # is a constant of the layout, not a preference.
    size: float = 18.0
    bold: bool = False
    align: str = "center"
    page_numbers: bool = False

    @classmethod
    def from_settings(cls, data) -> "HeadingStyle":
        """Build one from the panel's saved dictionary, ignoring anything odd."""
        if not isinstance(data, dict):
            return cls()
        style = cls()
        page = str(data.get("page", style.page))
        if page in PAGE_SIZES:
            style.page = page
        family = str(data.get("family", style.family))
        if family in FAMILY_NAMES:
            style.family = family
        try:
            size = float(data.get("size", style.size))
            if 6.0 <= size <= 72.0:
                style.size = size
        except (TypeError, ValueError):
            pass
        align = str(data.get("align", style.align))
        if align in ("left", "center", "right"):
            style.align = align
        style.bold = bool(data.get("bold", style.bold))
        style.page_numbers = bool(data.get("page_numbers", style.page_numbers))
        return style

    def leading(self) -> float:
        """Line spacing follows the type size, as it always did at 15pt."""
        return self.size * (CAPTION_LEADING / CAPTION_SIZE)


# --- margins -----------------------------------------------------------------
# Deliberately narrow on all four edges: the page exists to carry the clipping,
# not to frame it in white.
MARGIN_SIDE = 18.0
MARGIN_TOP = 18.0
MARGIN_BOTTOM = 18.0
CAPTION_SIZE = 15.0
CAPTION_LEADING = 20.0
CAPTION_GAP = 4.0           # between the bottom of the caption and the image

# --- original-size mode, measured off the real newspad -----------------------
LEGACY_LEFT = 17.88
LEGACY_MAX_WIDTH = 540.24
LEGACY_BOTTOM = 756.12
LEGACY_TOP_PLAIN = 35.88
LEGACY_TOP_CAPTIONED = 71.16
LEGACY_CAPTION_TOP = 36.18
TARGET_DPI = 220.0
POINTS_PER_PIXEL = 72.0 / TARGET_DPI

# How far a small clipping may be enlarged. Several divisions send cuttings only a
# couple of hundred pixels across; at their true print size those are postage
# stamps on an A4 sheet, so they are allowed to grow a long way.
MAX_UPSCALE = 8.0

# --- page numbers ------------------------------------------------------------
# A strip at the foot, reserved only when numbers are asked for. The margins here
# are 18pt and a fit-page clipping runs right down to them, so without this the
# number would print on the picture.
# A section name is printed once, over the first item of its run, in the red the
# 360 Degree document uses. The band is the room that costs the clipping below it.
SECTION_BAND = 34.0
SECTION_SIZE = 16.0
SECTION_COLOUR = "#C00000"


def section_band(size: float = SECTION_SIZE) -> float:
    """The room a heading of this size costs the clipping below it.

    Measured rather than guessed. Across 12/14/16/18/20/24/28pt in all three
    families, the drawn height of a one-line heading plus the gap under it comes
    to size * 1.25 + 14, and at the shipped 16pt that is exactly the 34.0 every
    report built so far has used - so a copy nobody has restyled prints pages
    identical to yesterday's.

    Three places have to agree about this number, and the third is easy to
    forget: the PDF reserves it, the PDF draws into it, and Word reserves it
    too (build_docx). Word was once left out of a change like this, and it drew
    every picture on a heading page one line too tall and pushed it onto the
    next sheet.
    """
    return round(float(size) * 1.25 + 14.0, 2)

def section_banners(clips) -> dict:
    """Which clipping opens which section, and the words it opens it with.

    Keyed by position in the list, so the two exporters cannot disagree.

    A clipping carries the heading the source document printed over it, and the
    heading goes wherever the clipping goes: that is what "taken along with the
    first image" means, and it survives the list being reordered. If the
    clipping that carried it has been left out, the section is still named -
    over whichever clipping now comes first - because a report that silently
    loses a heading is worse than one that puts it a page along. Either way a
    section is named once.
    """
    from ..core import sections as section_list

    banners: dict = {}
    opened: set = set()
    # Pass 0 - a heading a person chose in the preview window, which is the only
    # kind that can say DIGITAL MEDIA or anything the department has added
    # themselves. It comes first because it is the one somebody asked for by
    # hand, and because the two passes below can only ever produce the two
    # headings the 360 Degree document uses.
    #
    # Keyed on the WORDS rather than the key, so that renaming a heading to
    # words another one already prints still names it once. The one-heading-once
    # guarantee is the whole point of this function.
    chosen = section_list.load()
    for index, clip in enumerate(clips):
        key = getattr(clip, "section_key", "")
        if not key:
            continue
        # The words on the clipping win over the list, so a heading still
        # prints after the department removes it from their list - a report
        # that silently drops a heading somebody typed is the thing being
        # avoided here.
        words = (clip.section_title.strip()
                 or chosen.words_for(key))
        if words and words not in opened:
            opened.add(words)
            # Its own section is spoken for as well. Without this line a
            # clipping whose heading was retyped - ELECTRONIC MEDIA changed to
            # ELECTRONIC COVERAGE - printed the new words here and then the
            # THIRD pass, finding "Electronic" still unnamed, printed
            # ELECTRONIC MEDIA over the next electronic clipping as well. The
            # same section headed twice, in two different sets of words, which
            # is the exact fault the gate below this was written to prevent.
            if clip.section.value in SECTION_NAMES:
                opened.add(clip.section.value)
                opened.add(SECTION_NAMES[clip.section.value])
            banners[index] = words
    # A heading only prints where headings belong. Without that gate, a clipping
    # re-filed under Positive in the panel - or handed a heading by a merge -
    # took its words with it, and the section it had left was then named a
    # second time by the loop below: the same red heading on two pages, and a
    # red heading in a division report, which must never happen.
    for index, clip in enumerate(clips):
        name = clip.section.value
        if getattr(clip, "section_key", ""):
            continue          # already spoken for above
        if (clip.section_title.strip() and name in SECTION_NAMES
                and name not in opened and index not in banners):
            opened.add(name)
            opened.add(clip.section_title.strip())
            banners[index] = clip.section_title.strip()
    for index, clip in enumerate(clips):
        name = clip.section.value
        if (name in SECTION_NAMES and name not in opened
                and SECTION_NAMES[name] not in opened
                and index not in banners):
            opened.add(name)
            opened.add(SECTION_NAMES[name])
            banners[index] = SECTION_NAMES[name]
    return banners


PAGE_NUMBER_BAND = 14.0
PAGE_NUMBER_SIZE = 8.5
PAGE_NUMBER_COLOUR = "#6B7280"

# --- cover -------------------------------------------------------------------
COVER_TEXT_SIZE = 20.0
COVER_BLOCK_FROM_BOTTOM = 131.33     # where the two lines sit on the real cover

# --- links -------------------------------------------------------------------
# 12.5, not the 9.5 it was: at 9.5 the address under a clipping was legible on
# screen and small on paper, and it is the part of a digital clipping a reader is
# most likely to want to type out. The band below grows with it, so the picture
# gives up the room rather than the address being printed over it.
LINK_SIZE = 12.5
LINK_GAP = 8.0
# A clipping that prints an address under it has to leave room for one.
# Without this the picture grows to the foot of the sheet and the address
# is drawn across the bottom of it.
# Two lines of it. A full article address runs to 125 characters and does not fit
# across a sheet at this size; given one line's worth of box, MuPDF quietly
# shrank the longest ones to 10.7pt to make them fit, so the addresses that most
# needed the size increase were the ones that did not get it. Given two lines,
# they wrap and stay at the size asked for.
LINK_BOX = LINK_SIZE * 2.8
LINK_BAND = LINK_GAP + LINK_BOX


def page_size(name: str = DEFAULT_PAGE) -> tuple[float, float]:
    return PAGE_SIZES.get((name or DEFAULT_PAGE).lower(), PAGE_SIZES[DEFAULT_PAGE])


@dataclass
class Placement:
    """Where one clipping's image and caption go on its page."""

    x: float
    y: float
    width: float
    height: float
    caption_rect: tuple[float, float, float, float] | None
    page_width: float
    page_height: float

    @property
    def rect(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)


def place(
    pixel_width: int,
    pixel_height: int,
    has_caption: bool,
    page: str = DEFAULT_PAGE,
    fit_page: bool = True,
    caption_height: float | None = None,
    *,
    caption_leading: float = CAPTION_LEADING,
    footer: float = 0.0,
    header: float = 0.0,
) -> Placement:
    """Work out where one clipping sits on its own page.

    ``header`` reserves a strip at the top for a section name, the way the 360
    Degree document prints ELECTRONIC MEDIA over the first item of its section.
    It is zero on every other page, so nothing else moves.

    ``caption_height`` is how tall the caption actually turned out once it was set,
    which the caller measures after drawing it. Reserving a fixed block instead
    leaves invisible padding between a heading and the clipping it names.
    """
    if pixel_width <= 0 or pixel_height <= 0:
        pixel_width = pixel_height = 1

    width_pt, height_pt = page_size(page)

    if not fit_page:
        return _legacy(pixel_width, pixel_height, has_caption, width_pt, height_pt,
                       caption_leading=caption_leading, header=header)

    if has_caption:
        text_height = caption_leading if caption_height is None else caption_height
        caption_block = text_height + CAPTION_GAP
    else:
        caption_block = 0.0
    box_left = MARGIN_SIDE
    box_width = width_pt - MARGIN_SIDE * 2
    top = MARGIN_TOP + header
    available = height_pt - top - MARGIN_BOTTOM - footer
    box_height = available - caption_block

    natural = pixel_width * POINTS_PER_PIXEL, pixel_height * POINTS_PER_PIXEL
    scale = min(box_width / natural[0], box_height / natural[1])
    scale = min(scale, MAX_UPSCALE)          # never blow a small cutting to mush

    draw_width = natural[0] * scale
    draw_height = natural[1] * scale

    # The heading and the clipping are one thing, and that thing sits in the
    # middle of the sheet. Pinned to the top margin, a clipping that fills only
    # half the page left its masthead stranded at the top of an empty sheet with
    # the picture a long way below - which reads as two unrelated items rather
    # than a headline and the cutting it names.
    block = caption_block + draw_height
    offset = max(0.0, (available - block) / 2.0)
    caption_top = top + offset
    box_top = caption_top + caption_block

    # Centred left to right, but sitting directly under its caption rather than
    # floating in the middle of the sheet: a heading half a page away from the
    # clipping it names reads as two unrelated things.
    x = box_left + (box_width - draw_width) / 2.0
    y = box_top

    caption_rect = None
    if has_caption:
        # Room for three lines, so a long masthead wraps instead of being shrunk to
        # fit. Only the height it actually uses affects where the image goes.
        caption_rect = (
            MARGIN_SIDE,
            caption_top,
            width_pt - MARGIN_SIDE,
            caption_top + caption_leading * 3.4,
        )

    return Placement(
        x=x, y=y, width=draw_width, height=draw_height,
        caption_rect=caption_rect, page_width=width_pt, page_height=height_pt,
    )


def _legacy(
    pixel_width: int,
    pixel_height: int,
    has_caption: bool,
    width_pt: float,
    height_pt: float,
    caption_leading: float = CAPTION_LEADING,
    header: float = 0.0,
) -> Placement:
    """The original newspad placement: 220 DPI, left margin, top aligned."""
    # LEGACY_TOP_CAPTIONED was measured off the real newspad with a 15pt caption.
    # Only the gap it leaves for the text scales with the type size - the 36.18pt
    # above it is where the caption starts on the real sheets, and moving that
    # would stop this reproducing them. At the default size the sum is exactly
    # the measured 71.16.
    if has_caption:
        grown = (LEGACY_TOP_CAPTIONED - LEGACY_CAPTION_TOP) * (
            caption_leading / CAPTION_LEADING)
        top = LEGACY_CAPTION_TOP + grown
    else:
        top = LEGACY_TOP_PLAIN
    # A section name takes a band off the top here as well. Without this the
    # heading was drawn at the margin while the picture stayed pinned at the
    # measured offset, and the two overlapped.
    caption_top = LEGACY_CAPTION_TOP + header
    top += header
    bottom = min(LEGACY_BOTTOM, height_pt - 36.0)
    max_width = min(LEGACY_MAX_WIDTH, width_pt - LEGACY_LEFT - 36.0)

    width = pixel_width * POINTS_PER_PIXEL
    height = pixel_height * POINTS_PER_PIXEL
    shrink = min(1.0, max_width / width, (bottom - top) / height)

    caption_rect = None
    if has_caption:
        caption_rect = (
            LEGACY_LEFT, caption_top,
            LEGACY_LEFT + max_width, caption_top + caption_leading * 1.6,
        )

    return Placement(
        x=LEGACY_LEFT, y=top,
        width=width * shrink, height=height * shrink,
        caption_rect=caption_rect, page_width=width_pt, page_height=height_pt,
    )


def cover_lines(page: str = DEFAULT_PAGE) -> tuple[float, float]:
    """Y positions of the two cover lines for this paper size."""
    _width, height = page_size(page)
    first = height - COVER_BLOCK_FROM_BOTTOM
    return first, first + COVER_TEXT_SIZE * 1.62
