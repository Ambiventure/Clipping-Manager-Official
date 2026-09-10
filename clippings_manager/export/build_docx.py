"""Build the newspad as a Word document.

Same shape as the PDF: a cover carrying the count and the date, then one clipping
per page with its caption above it, at the same measured geometry. Word is the
format the department edits by hand afterwards, so the images go in at the size
they should print rather than at whatever Word would guess.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Optional, Sequence

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from .. import version
from ..core import imageops
from ..core.models import Clip

from . import layout, word_cover

Progress = Optional[Callable[[int, int, str], None]]

# Word lays a page out itself, and it rounds line heights its own way, so the
# picture is given a little less room than the arithmetic says is free. Without
# it a page that fits to the point in theory spills its picture onto the next
# one, leaving the heading alone above an empty half-sheet. Measured against
# Word: the shortfall is a couple of points, and this is comfortably clear of it
# while costing a full-height clipping about 3% of its height.
DOCX_SLACK = 24.0


DEVANAGARI_FONT = "Nirmala UI"

# What each choice means in Word. The complex-script slot always stays Nirmala UI:
# Word picks the face for a run by script, so setting only the Latin face lets an
# English masthead be serif while a Hindi one still has glyphs to draw with.
# What each face becomes in Word. Word has real system fonts, so these are
# chosen to look like what the PDF drew rather than to be the same file.
# Word has the real fonts, so a named face is simply itself. The five older
# abstract names stay so a setting saved before the named fonts existed still
# opens and still prints the same.
LATIN_FACES = {
    "sans": "Nirmala UI",
    "serif": "Times New Roman",
    "mono": "Courier New",
    "book": "Georgia",
    "text": "Cambria",
    "arial": "Arial",
    "calibri": "Calibri",
    "times": "Times New Roman",
    "georgia": "Georgia",
    "cambria": "Cambria",
    "garamond": "Garamond",
    "bookantiqua": "Book Antiqua",
    "segoe": "Segoe UI",
    "tahoma": "Tahoma",
    "verdana": "Verdana",
    "trebuchet": "Trebuchet MS",
    "couriernew": "Courier New",
    "comic": "Comic Sans MS",
}

ALIGNMENTS = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
}


def _set_faces(run, latin: str, complex_script: str = DEVANAGARI_FONT) -> None:
    """Latin text in the chosen face, Devanagari always in one that has glyphs.

    ``run.font.name`` writes only w:ascii and w:hAnsi. Word chooses a font per
    script, and Devanagari is a complex script, so without w:cs a Hindi masthead
    falls back to whatever Word feels like - historically empty boxes.
    """
    run.font.name = latin
    properties = run._element.get_or_add_rPr()
    fonts = properties.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        properties.append(fonts)
    fonts.set(qn("w:ascii"), latin)
    fonts.set(qn("w:hAnsi"), latin)
    fonts.set(qn("w:cs"), complex_script)


@dataclass
class Result:
    path: Path
    clippings: int
    warnings: list[str]


def _add_hyperlink(paragraph, url: str, text: str,
                   size: Optional[float] = None) -> None:
    """Insert a real clickable hyperlink.

    python-docx has no API for this, so the relationship and the ``w:hyperlink``
    element are written directly. ``size`` is in points and defaults to the one
    the PDF uses, so the two reports print the address at the same size.
    """
    from docx.oxml.ns import qn
    from docx.oxml.shared import OxmlElement

    part = paragraph.part
    r_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)

    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    colour = OxmlElement("w:color")
    colour.set(qn("w:val"), "0F5F76")
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    points = layout.LINK_SIZE if size is None else size
    size_element = OxmlElement("w:sz")
    size_element.set(qn("w:val"), str(int(round(points * 2))))   # half-points
    properties.append(colour)
    properties.append(underline)
    properties.append(size_element)
    run.append(properties)

    text_element = OxmlElement("w:t")
    text_element.text = text
    run.append(text_element)
    link.append(run)
    paragraph._p.append(link)


def _image_bytes(clip: Clip) -> bytes:
    return imageops.encode_for_export(clip)


def _normalised(clip: Clip, as_png: bool = False) -> bytes:
    """Re-encode through Pillow, which rewrites the headers cleanly.

    The same bytes the PDF embeds, by the same rule - a picture that Word will
    not draw is a picture Acrobat will not draw either, and one answer is easier
    to trust than two.
    """
    if as_png:
        image = clip.render()
        buffer = io.BytesIO()
        image.save(buffer, "PNG", optimize=True)
        return buffer.getvalue()
    return imageops.encode_for_export(clip)


def _place_picture(run, clip: Clip, width, height) -> None:
    """Insert the image, working around python-docx's fragile header parser.

    Word itself opens these files happily, but python-docx reads the JPEG markers
    with its own small parser and rejects around one in sixteen of the division
    images. Re-encoding through Pillow rewrites the headers and it accepts them, so
    the pass-through is tried first and the clean copy is the fallback.
    """
    attempts = (
        lambda: _image_bytes(clip),
        lambda: _normalised(clip, as_png=False),
        lambda: _normalised(clip, as_png=True),
    )
    last: Exception | None = None
    for produce in attempts:
        try:
            run.add_picture(io.BytesIO(produce()), width=width, height=height)
            return
        except Exception as exc:  # noqa: BLE001 - try the next encoding
            last = exc
    raise last if last else RuntimeError("image could not be placed")


def build(
    clips: Sequence[Clip],
    output: str | Path,
    report_date: Optional[date] = None,
    cover_image: Optional[str | Path] = None,
    progress: Progress = None,
    page: str = layout.DEFAULT_PAGE,
    fit_page: bool = True,
    cover_title: str = "",
    draw_cover_text: bool = True,
    heading: Optional[layout.HeadingStyle] = None,
    cover_blocks: Optional[Sequence] = None,
) -> Result:
    """Write the newspad as .docx, in the order the user arranged.

    Both cover templates are rasterised to one picture by
    :mod:`clippings_manager.core.cover_render`, which paints the count and the date
    into the image itself. ``draw_cover_text=False`` says so: drawing them again
    here would print each line twice.

    ``cover_blocks`` is that same cover handed over as a layout rather than as a
    picture - which is what the generated cover sends, because a Word file is
    edited afterwards and a picture cannot be. See
    :mod:`clippings_manager.export.word_cover`.
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_date = report_date or date.today()
    warnings: list[str] = []

    style = heading or layout.HeadingStyle(page=page)
    page_width, page_height = layout.page_size(style.page)
    document = Document()
    section = document.sections[0]
    section.page_width = Pt(page_width)
    section.page_height = Pt(page_height)
    if fit_page:
        section.left_margin = Pt(layout.MARGIN_SIDE)
        section.right_margin = Pt(layout.MARGIN_SIDE)
        section.top_margin = Pt(layout.MARGIN_TOP)
        section.bottom_margin = Pt(layout.MARGIN_BOTTOM)
    else:
        section.left_margin = Pt(layout.LEGACY_LEFT)
        section.right_margin = Pt(
            max(18.0, page_width - layout.LEGACY_LEFT - layout.LEGACY_MAX_WIDTH)
        )
        section.top_margin = Pt(layout.LEGACY_TOP_PLAIN)
        section.bottom_margin = Pt(max(18.0, page_height - layout.LEGACY_BOTTOM))

    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(0)

    # ------------------------------------------------------------ cover page
    # Text first, when there is a layout to write. The picture is the fallback,
    # not the preference: everything on a Word cover should be editable.
    laid_out = False
    if cover_blocks:
        try:
            laid_out = word_cover.add_cover(
                document, cover_blocks, page_width, page_height, warnings)
        except Exception as exc:  # noqa: BLE001 - fall back to the picture
            laid_out = False
            warnings.append(
                f"The cover could not be written as text "
                f"({type(exc).__name__}); the picture was used instead."
            )

    if cover_image and not laid_out:
        try:
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.add_run().add_picture(
                str(cover_image),
                width=Pt(page_width - layout.MARGIN_SIDE * 2),
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"The cover image could not be placed ({type(exc).__name__}); "
                f"a plain cover was used instead."
            )

    cover_lines = []
    if draw_cover_text and not laid_out:
        if cover_title.strip():
            cover_lines.append(cover_title.strip())
        cover_lines += [
            f"NUMBER OF CLIPPINGS: {len(clips)}",
            f"DATE : {report_date.strftime('%d.%m.%Y')}",
        ]
    for text in cover_lines:
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run(text)
        run.bold = True
        run.font.size = Pt(layout.COVER_TEXT_SIZE)

    # -------------------------------------------------------- clipping pages
    written = 0
    banners = layout.section_banners(clips)
    from ..core import sections as section_list

    heading_style = section_list.load()
    heading_band = layout.section_band(heading_style.size)
    # The department's list of words that must not appear in a printed report.
    # Built once. An empty list is the normal case and costs nothing: `clean`
    # returns the line it was handed without touching it.
    from ..core import wordlist as _wordlist

    sieve = _wordlist.Sieve()

    for number, clip in enumerate(clips, start=1):
        if progress:
            progress(number, len(clips), clip.effective_label or "clipping")

        # The page break goes ON the first paragraph of the clipping rather than
        # into an empty paragraph of its own. An empty paragraph is still a line,
        # and that line came off the top of every single page - which is most of
        # why a full-height picture no longer fitted beside its heading.
        opening = []

        # The same heading, in the same place, decided by the same rule as the
        # PDF - so the two reports of one day's work never disagree.
        section_name = sieve.clean(banners.get(number - 1, ""))
        if section_name:
            banner = document.add_paragraph()
            opening.append(banner)
            banner.alignment = ALIGNMENTS[style.align]
            run = banner.add_run(section_name)
            run.font.size = Pt(heading_style.size)
            run.bold = True
            # Was a hard-coded 0xC00000 here. One string now drives both
            # exporters, so a colour chosen in the program cannot ship working
            # in the PDF and silently ignored in the Word file.
            run.font.color.rgb = RGBColor.from_string(
                heading_style.colour.lstrip("#").upper())
            _set_faces(run, LATIN_FACES[style.family])
            banner.paragraph_format.space_after = Pt(layout.CAPTION_GAP)
            # Never let Word part a heading from what it heads.
            banner.paragraph_format.keep_with_next = True

        caption = sieve.clean(clip.printed_caption.strip())
        if caption:
            paragraph = document.add_paragraph()
            opening.append(paragraph)
            paragraph.alignment = ALIGNMENTS[style.align]
            run = paragraph.add_run(caption)
            run.font.size = Pt(style.size)
            run.bold = style.bold
            run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
            _set_faces(run, LATIN_FACES[style.family])
            paragraph.paragraph_format.space_after = Pt(layout.CAPTION_GAP)
            paragraph.paragraph_format.keep_with_next = True

        # The address prints under the picture here exactly as it does in the
        # PDF, and it needs the same band kept clear for it. Word was never told,
        # so on every page carrying one the picture was drawn a line too tall and
        # Word moved it to the next page.
        tail = DOCX_SLACK + (layout.LINK_BAND if clip.url else 0.0)
        placement = layout.place(
            *clip.rendered_size(), has_caption=bool(caption),
            page=style.page, fit_page=fit_page,
            caption_leading=style.leading(),
            # The site that gets forgotten. If the PDF reserves a taller
            # band and this does not, Word draws the picture a line too tall on
            # exactly the pages that carry a heading, and pushes it onto the
            # next sheet.
            header=heading_band if section_name else 0.0,
            footer=tail,
        )
        try:
            image_paragraph = document.add_paragraph()
            opening.append(image_paragraph)
            image_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _place_picture(
                image_paragraph.add_run(), clip,
                Pt(placement.width), Pt(placement.height),
            )
        except Exception as exc:  # noqa: BLE001 - one bad image costs one page
            warnings.append(
                f"Clipping {number} ({caption or 'unnamed'}) could not be placed "
                f"({type(exc).__name__}); its page was left blank."
            )
            continue

        if clip.url:
            link_paragraph = document.add_paragraph()
            link_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _add_hyperlink(link_paragraph, clip.url, clip.url)
        if opening:
            opening[0].paragraph_format.page_break_before = True
        written += 1

    # The same stamp the PDF carries, in the properties Word already has.
    properties = document.core_properties
    properties.title = f"Press media coverage {report_date.strftime('%d.%m.%Y')}"
    properties.author = "Northern Railway"
    properties.comments = f"Clippings Manager {version.describe()}"

    document.save(str(output))
    # A word list that quietly edits a report is the dangerous version of this
    # feature. It says what it did, every time it did anything, and says
    # nothing at all when the list is empty.
    if sieve.changed:
        told = ", ".join(f"{word} ({count})"
                         for word, count in sorted(sieve.hits.items()))
        warnings.append(
            f"{sieve.changed} line(s) had words left out, as your list asks: "
            f"{told}. Nothing was changed on the clippings themselves - take a "
            f"word off the list and it prints again.")

    return Result(path=output, clippings=written, warnings=warnings)
