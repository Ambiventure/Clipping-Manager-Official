"""Clippings whose headline and address are part of the picture.

The ordinary dossier prints a heading, then the picture, then the address, as
three separate things on the page. That is right for a report somebody reads,
and wrong for one that gets forwarded: paste a page into a message, or lift the
picture out of the Word file, and the heading stays behind.

This builds each clipping as ONE image with the headline burned in above it and
the address burned in below, then hands those to the ordinary dossier builders.
The report that comes out has the same cover, the same category order and the
same page geometry as always - but every clipping on it is a single picture, and
nothing on it is selectable text.

The text is drawn by the same ``_draw_line`` the report uses, so Devanagari is
shaped properly and the Heading & Document Layout panel governs the face, the
size, the weight and the alignment exactly as it does everywhere else.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

import pymupdf

from ..core import imageops
from ..core.models import Clip
from . import build_pdf, layout

# Room around the burned-in text, in points at the composing size. The picture
# is rasterised afterwards, so these are relative to the clipping's own width.
PAD_SIDE = 10.0
PAD_TOP = 10.0
GAP_ABOVE = 8.0
GAP_BELOW = 8.0
PAD_BOTTOM = 10.0

# Below which the header text has nowhere to sit; a 208px Lucknow cutting is the
# narrowest thing the department sends.
MIN_WIDTH = 420.0

INK = "#1A1F2B"
LINK_INK = "#0F5F76"
# The address is set smaller than the headline, in the same proportion the
# printed report uses.
LINK_RATIO = 0.62
QUALITY = 88


@dataclass
class Burned:
    """What one composed clipping cost, for the caller's warnings."""

    clip: Clip
    width: int
    height: int


def _measure(page, typeface, text, width, size, style, colour, bold):
    """How tall a line comes out once it is set - measured, not guessed."""
    box = pymupdf.Rect(PAD_SIDE, PAD_TOP, width - PAD_SIDE, 4000)
    return build_pdf._draw_line(
        page, typeface, text, box, size, align=style.align, colour=colour,
        bold=bold, family=style.family)


def compose(clip: Clip, typeface: "build_pdf.Typeface",
            heading: Optional[layout.HeadingStyle] = None,
            dpi: int = 200) -> bytes:
    """One clipping, its headline and its address, as a single JPEG.

    Returns the picture bytes. The headline goes above and the address below,
    which is where the printed report puts them - so a burned clipping and a
    printed one read the same way round.
    """
    style = heading or layout.HeadingStyle()
    # The burned picture carries the headline INSIDE the JPEG, so a word left
    # in here is the one that would survive being sent on as a photograph.
    from ..core import wordlist as _wordlist

    title = _wordlist.Sieve().clean(clip.effective_label.strip())
    address = (clip.url or "").strip()
    link_size = max(7.0, style.size * LINK_RATIO)

    data = imageops.encode_for_export(clip)
    picture = pymupdf.open(stream=data, filetype="jpeg")
    rect = picture[0].rect if picture.page_count else pymupdf.Rect(0, 0, 400, 300)
    picture.close()
    width = max(float(rect.width), MIN_WIDTH)

    # Measured on a scratch page first: a long masthead wraps to two lines and a
    # 125-character address to three, and the bands have to be as tall as the
    # text actually turned out rather than as tall as one line was assumed to be.
    scratch = pymupdf.open()
    probe = scratch.new_page(width=width, height=4000)
    title_height = (_measure(probe, typeface, title, width, style.size, style,
                             INK, style.bold) if title else 0.0)
    link_height = (_measure(probe, typeface, address, width, link_size, style,
                            LINK_INK, False) if address else 0.0)
    scratch.close()

    above = (PAD_TOP + title_height + GAP_ABOVE) if title else PAD_TOP
    below = (GAP_BELOW + link_height + PAD_BOTTOM) if address else PAD_BOTTOM
    height = above + float(rect.height) + below

    sheet = pymupdf.open()
    page = sheet.new_page(width=width, height=height)
    page.draw_rect(page.rect, color=None, fill=pymupdf.pdfcolor["white"])

    if title:
        build_pdf._draw_line(
            page, typeface, title,
            pymupdf.Rect(PAD_SIDE, PAD_TOP, width - PAD_SIDE,
                         PAD_TOP + title_height + 4),
            style.size, align=style.align, colour=INK, bold=style.bold,
            family=style.family)

    # Centred when the sheet had to be widened to fit the text, flush otherwise.
    left = (width - float(rect.width)) / 2.0
    page.insert_image(
        pymupdf.Rect(left, above, left + float(rect.width),
                     above + float(rect.height)),
        stream=data,
    )

    if address:
        top = above + float(rect.height) + GAP_BELOW
        build_pdf._draw_line(
            page, typeface, address,
            pymupdf.Rect(PAD_SIDE, top, width - PAD_SIDE, top + link_height + 4),
            link_size, align=style.align, colour=LINK_INK, family=style.family)

    pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB)
    out = pixmap.tobytes("jpeg", jpg_quality=QUALITY)
    sheet.close()
    return out


def flatten(clips: Sequence[Clip],
            heading: Optional[layout.HeadingStyle] = None,
            dpi: int = 200,
            warnings: Optional[list] = None) -> list[Clip]:
    """Copies of ``clips`` whose picture already contains the words.

    The headline and the address are cleared on the copies, because they are in
    the picture now: left in place the report would print each of them twice,
    once as text above and once inside the image below it.

    The originals are untouched - this is an export, and a person's board must
    look the same after it as before.
    """
    warnings = warnings if warnings is not None else []
    typeface = build_pdf.Typeface()
    burned: list[Clip] = []
    for number, clip in enumerate(clips, start=1):
        one = copy.copy(clip)
        try:
            data = compose(clip, typeface, heading, dpi)
        except Exception as exc:  # noqa: BLE001 - one bad picture costs one page
            warnings.append(
                f"Clipping {number} ({clip.effective_label or 'unnamed'}) could "
                f"not have its headline burned in ({type(exc).__name__}); it was "
                f"used as it is, with the headline printed above it instead."
            )
            burned.append(one)
            continue
        with pymupdf.open(stream=data, filetype="jpeg") as check:
            size = check[0].rect if check.page_count else None
        one.image_bytes = data
        one.image_ext = ".jpg"
        one.native_width = int(size.width) if size else clip.native_width
        one.native_height = int(size.height) if size else clip.native_height
        one.crop = type(clip.crop)()      # the crop is baked into the picture
        one.rotation = 0                  # and so is the rotation
        one.label = ""
        one.newspaper = ""
        one.edition = ""
        one.url = ""
        one.section_title = clip.section_title
        burned.append(one)
    return burned
