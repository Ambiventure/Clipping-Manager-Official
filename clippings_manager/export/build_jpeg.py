"""Each clipping as its own JPEG, with the newspaper name burned into the picture.

The dossier and the newspad are documents. This is the other thing the department
sends: single images, forwarded one at a time on WhatsApp, where nothing carries
the caption except the picture itself. So the masthead, the date and the page are
drawn into the image rather than printed beside it.

**Why this goes through PyMuPDF and not Pillow.** Roughly half these newspapers are
Hindi, and Pillow in this build has no Raqm - ``features.check("raqm")`` is False,
so is harfbuzz - which means it cannot shape Devanagari. It would draw the letters
in code-point order with the matras and conjuncts in the wrong places: not a
crash, just wrong, and wrong in a script most of the office reads. PyMuPDF shapes
it correctly, and it is already the thing that draws every caption in the PDF
export, so the header on a JPEG and the caption in the newspad come out of the
same code and look the same.

The page is built at the clipping's own pixel size so nothing is resampled: the
picture that comes out is the picture that went in, with a band added on top.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Optional, Sequence

import pymupdf

from ..core import imageops
from ..core.models import Clip, Section
from . import build_pdf, layout

Progress = Optional[Callable[[int, int, str], None]]

# The band above the picture, in points at 72dpi against the clipping's own pixels.
PAD_SIDE = 10.0
PAD_TOP = 8.0
PAD_BOTTOM = 6.0
# The masthead takes the size the panel asks for; the date and page line sits a
# fixed proportion below it, so the two keep their relationship at any size.
SECOND_LINE_RATIO = 12.5 / 15.0
LINE_GAP = 3.0
INK = "#111111"
GROUND = "#FFFFFF"
QUALITY = 92

# A clipping narrower than this gets a page wider than itself, so the header has
# somewhere to sit. Measured against the smallest cuttings the divisions send
# (208px wide from Lucknow) - below about 380 the masthead wraps to three lines.
MIN_WIDTH = 420

# What each category is called on disk. Short, because it becomes a folder name
# and the front of every file name inside it.
CATEGORY_LETTERS = {
    Section.POSITIVE: "P",
    Section.NEUTRAL: "N",
    Section.DIGITAL: "D",
    Section.NEGATIVE: "Neg",
    Section.ELECTRONIC: "E",
    Section.SOCIAL: "S",
}
# The same order the report reads in, so a folder of pictures and the document
# they came from are arranged alike.
CATEGORY_ORDER = ("P", "N", "Neg", "D", "E", "S")
FORBIDDEN = re.compile(r'[<>:"/\\|?*]')


def category_letter(clip: Clip) -> str:
    """P, N, D or Neg - which pile this clipping belongs in."""
    return CATEGORY_LETTERS.get(getattr(clip, "section", None), "N")


def safe_name(text: str, fallback: str = "clipping") -> str:
    """A name Windows will accept, with the spacing tidied."""
    cleaned = FORBIDDEN.sub(" ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned or fallback)[:120]


def folder_name(division: str, when: date) -> str:
    """The parent folder: the division, then the day it covers."""
    return safe_name(f"{division}-News Clips-{when.strftime('%d.%m.%Y')}",
                     "News Clips")


@dataclass
class Result:
    folder: Path
    files: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.files)


def _site(url: str) -> str:
    """The site an address belongs to: 'indianexpress.com', 'facebook.com'."""
    host = (url or "").strip()
    host = host.split("//", 1)[-1].split("/", 1)[0].split("?", 1)[0]
    if host.lower().startswith("www."):
        host = host[4:]
    return host


def header_lines(clip: Clip, when: date) -> tuple[str, str]:
    """The two lines burned in above a clipping.

    Line one names the paper, line two dates it and says which page. The user's
    own typed headline wins over a parsed newspaper name, because if they retyped
    it the parse was wrong.
    """
    masthead = " ".join(
        part for part in (clip.newspaper.strip(), clip.edition.strip()) if part
    ).strip()
    if not masthead:
        masthead = clip.effective_label.strip()
    if not masthead:
        # A screenshot of a web page has no masthead. What names it is where it
        # came from, so the site does: without this a whole run of them came out
        # as "clipping", "clipping (2)", "clipping (3)" in one pile.
        masthead = _site(clip.url)
    stamp = when.strftime("%d-%m-%y")
    page = clip.page.strip()
    second = f"{stamp}    Page-{page}" if page else stamp
    return masthead, second


def file_name(clip: Clip, when: date) -> str:
    """The category, the newspaper, then the date.

    The category leads so that a pile of these still sorts into its groups once
    they have been copied somewhere else, which is what happens the moment they
    are forwarded.
    """
    masthead, _second = header_lines(clip, when)
    masthead = masthead.strip() or "clipping"
    return safe_name(
        f"{category_letter(clip)} - {masthead} - {when.strftime('%d.%m.%Y')}")


def _unique(folder: Path, stem: str, taken: set) -> Path:
    """Two clippings from the same paper on the same day both need a name.

    Uniqueness is per pile, not across the whole export: the same newspaper can
    appear once under P and once under Neg, and neither should be renamed for the
    other's sake.
    """
    candidate, number = stem, 2
    while (folder.name, candidate.lower()) in taken:
        candidate = f"{stem} ({number})"
        number += 1
    taken.add((folder.name, candidate.lower()))
    return folder / f"{candidate}.jpg"


def render(clip: Clip, when: date, typeface: "build_pdf.Typeface",
           dpi: int = 150,
           heading: Optional[layout.HeadingStyle] = None) -> bytes:
    """One clipping with its header burned in, as JPEG bytes.

    The header is set the way the Heading & Document Layout panel asks, so a
    clipping sent as a picture is titled the same as the same clipping printed in
    the dossier. It was ranged left whatever the panel said, which is what made a
    centred setting look ignored.
    """
    style = heading or layout.HeadingStyle(**{
        "size": 15.0, "align": "left", "bold": True, "family": "sans"})
    line_one = style.size
    line_two = max(7.0, style.size * SECOND_LINE_RATIO)
    data = imageops.encode_for_export(clip)
    picture = pymupdf.open(stream=data, filetype="png")
    rect = picture[0].rect if picture.page_count else pymupdf.Rect(0, 0, 400, 300)
    picture.close()

    width = max(float(rect.width), float(MIN_WIDTH))
    masthead, second = header_lines(clip, when)

    # Measure the header by drawing it onto a scratch page first: a long masthead
    # wraps, and the band has to be as tall as the text actually came out.
    scratch = pymupdf.open()
    probe = scratch.new_page(width=width, height=400)
    box = pymupdf.Rect(PAD_SIDE, PAD_TOP, width - PAD_SIDE, 300)
    first_height = build_pdf._draw_line(
        probe, typeface, masthead, box, line_one, align=style.align, colour=INK,
        bold=style.bold, family=style.family)
    second_height = 0.0
    if second:
        second_box = pymupdf.Rect(PAD_SIDE, PAD_TOP + first_height + LINE_GAP,
                                  width - PAD_SIDE, 380)
        second_height = build_pdf._draw_line(
            probe, typeface, second, second_box, line_two, align=style.align,
            colour=INK, family=style.family)
    scratch.close()

    band = PAD_TOP + first_height + (LINE_GAP + second_height if second else 0.0)
    band += PAD_BOTTOM

    sheet = pymupdf.open()
    page = sheet.new_page(width=width, height=band + float(rect.height))
    page.draw_rect(page.rect, color=None, fill=pymupdf.pdfcolor["white"])

    build_pdf._draw_line(
        page, typeface, masthead,
        pymupdf.Rect(PAD_SIDE, PAD_TOP, width - PAD_SIDE, PAD_TOP + first_height + 4),
        line_one, align=style.align, colour=INK, bold=style.bold,
        family=style.family)
    if second:
        top = PAD_TOP + first_height + LINE_GAP
        build_pdf._draw_line(
            page, typeface, second,
            pymupdf.Rect(PAD_SIDE, top, width - PAD_SIDE, top + second_height + 4),
            line_two, align=style.align, colour=INK, family=style.family)

    # Centred if the page had to be widened for the header; otherwise flush.
    left = (width - float(rect.width)) / 2.0
    page.insert_image(
        pymupdf.Rect(left, band, left + float(rect.width), band + float(rect.height)),
        stream=data,
    )

    pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB)
    out = pixmap.tobytes("jpeg", jpg_quality=QUALITY)
    sheet.close()
    return out


def build(
    clips: Sequence[Clip],
    folder: str | Path,
    report_date: Optional[date] = None,
    progress: Progress = None,
    dpi: int = 150,
    heading: Optional[layout.HeadingStyle] = None,
) -> Result:
    """Write one JPEG per clipping, filed by category, under ``folder``.

    Each category gets its own sub-folder - P, N, D, Neg - so a day's positive
    coverage is one place you can select all of and send.
    """
    when = report_date or date.today()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    typeface = build_pdf.Typeface()
    result = Result(folder=folder)
    taken: set = set()

    for number, clip in enumerate(clips, start=1):
        if progress:
            progress(number, len(clips), clip.effective_label or "clipping")
        pile = folder / category_letter(clip)
        pile.mkdir(parents=True, exist_ok=True)
        target = _unique(pile, file_name(clip, when), taken)
        try:
            target.write_bytes(
                render(clip, when, typeface, dpi=dpi, heading=heading))
            result.files.append(target)
        except Exception as exc:  # noqa: BLE001 - one bad picture costs one file
            result.warnings.append(
                f"{clip.effective_label or 'A clipping'} could not be written "
                f"({type(exc).__name__})."
            )
    return result
