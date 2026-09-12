"""Build the newspad PDF.

A cover page carrying the clipping count and the date, then exactly one clipping
per page at the geometry measured from the real output. Digital, electronic and
social items keep their link as a real clickable annotation rather than as text
that merely looks like one.

Text goes through ``insert_htmlbox`` rather than ``insert_text`` because Devanagari
needs a shaping engine: drawn glyph by glyph, ``दैनिक`` comes out as ``दैनकि`` with
the vowel sign in the wrong place. The HTML box lays the line out properly and
centres it for us.

Nothing here goes near the network.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path
from typing import Callable, Optional, Sequence

import pymupdf

from .. import version
from ..core import imageops
from ..core.models import Clip
from . import layout

Progress = Optional[Callable[[int, int, str], None]]

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
SYSTEM_FAMILIES = "'Nirmala UI', Mangal, 'Noto Sans Devanagari', sans-serif"

# Roughly half these newspapers are Hindi, and Devanagari resolves through the
# system families above. So a chosen face is put IN FRONT of that chain, never in
# place of it: Latin text picks up the serif or the monospace, and any Devanagari
# the chosen face cannot draw still falls through to Nirmala UI as before. "sans"
# is the chain exactly as it was, so the default changes nothing.
def _stack(*faces: str) -> str:
    """A chosen face in front, the Devanagari stack always behind it."""
    return ", ".join(list(faces) + [SYSTEM_FAMILIES])


# Where Windows keeps its fonts. A per-user install puts them in the second one.
FONT_FOLDERS = (
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts",
)

# The faces the panel offers by name, and the files they live in. Naming a font
# in CSS is not enough on its own: MuPDF knows a handful of built-in faces and
# quietly draws one of those for everything else, so asking for Calibri got
# Nimbus Sans and nobody was told. These are embedded from the machine's own font
# folder instead - which is what Word does with the same files - and then MuPDF
# really does draw them.
WINDOWS_FACES = {
    "arial": ("Arial", "arial.ttf", "arialbd.ttf"),
    "calibri": ("Calibri", "calibri.ttf", "calibrib.ttf"),
    "times": ("Times New Roman", "times.ttf", "timesbd.ttf"),
    "georgia": ("Georgia", "georgia.ttf", "georgiab.ttf"),
    "verdana": ("Verdana", "verdana.ttf", "verdanab.ttf"),
    "tahoma": ("Tahoma", "tahoma.ttf", "tahomabd.ttf"),
    "segoe": ("Segoe UI", "segoeui.ttf", "segoeuib.ttf"),
    "trebuchet": ("Trebuchet MS", "trebuc.ttf", "trebucbd.ttf"),
    "garamond": ("Garamond", "GARA.TTF", "GARABD.TTF"),
    "couriernew": ("Courier New", "cour.ttf", "courbd.ttf"),
    "bookantiqua": ("Book Antiqua", "BOOKOS.TTF", "BOOKOSB.TTF"),
    "comic": ("Comic Sans MS", "comic.ttf", "comicbd.ttf"),
    # Cambria ships as a collection on some builds; the bold file is a plain TTF
    # and MuPDF reads it, so it stands in for the regular where that is the case.
    "cambria": ("Cambria", "cambria.ttc", "cambriab.ttf"),
}


def available_faces() -> set:
    """Which named faces this machine actually has the files for.

    The panel asks before offering them: a face that is not installed would be a
    choice that quietly prints as something else, which is the whole thing this
    was meant to stop.
    """
    return {key for key, (_family, regular, _bold) in WINDOWS_FACES.items()
            if _font_file(regular) is not None}


def _weighted(candidates: list, want: str) -> Optional[Path]:
    """The file for one weight, ignoring the widths beside it.

    Noto ships as a family: nine weights, each in four widths, thirty-eight
    files. Only the upright normal-width Regular and Bold are wanted; a name
    carrying Condensed, Italic or a variable axis is one of the others.
    """
    for path in candidates:
        stem = path.stem
        if any(word in stem for word in ("Condensed", "Italic", "VariableFont")):
            continue
        if stem.endswith("-" + want):
            return path
    return None


def _font_file(name: str) -> Optional[Path]:
    """Where a font file is on this machine, if it is here at all."""
    for folder in FONT_FOLDERS:
        try:
            candidate = folder / name
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


# The names on the left of each stack are the ones MuPDF answers to. It draws
# NimbusSans for Helvetica, NimbusRoman for Times, NimbusMonoPS for Courier,
# CharisSIL for the bare "serif" keyword and NotoSerif for Noto Serif - five
# faces, and anything it does not recognise becomes one of them without saying
# so. Each entry here is one of the five.
# Used when a named face is not installed on this machine, so a dossier built on
# a stripped-down PC still comes out with something sensible rather than nothing.
FAMILY_STACKS = {
    "sans": SYSTEM_FAMILIES,
    "serif": _stack("Times", "'Times New Roman'"),
    "mono": _stack("Courier", "'Courier New'", "monospace"),
    "book": _stack("'Charis SIL'", "serif"),
    "text": _stack("'Noto Serif'", "serif"),
    "arial": SYSTEM_FAMILIES,
    "calibri": SYSTEM_FAMILIES,
    "segoe": SYSTEM_FAMILIES,
    "tahoma": SYSTEM_FAMILIES,
    "verdana": SYSTEM_FAMILIES,
    "trebuchet": SYSTEM_FAMILIES,
    "comic": SYSTEM_FAMILIES,
    "times": _stack("Times", "'Times New Roman'"),
    "couriernew": _stack("Courier", "monospace"),
    "georgia": _stack("'Charis SIL'", "serif"),
    "cambria": _stack("'Charis SIL'", "serif"),
    "garamond": _stack("'Charis SIL'", "serif"),
    "bookantiqua": _stack("'Charis SIL'", "serif"),
}


@dataclass
class Result:
    path: Path
    pages: int
    clippings: int
    warnings: list[str]


class Typeface:
    """Resolves a font that can set both Latin and Devanagari.

    A bundled face is preferred so a packaged build never depends on what happens
    to be installed; otherwise the system families are named and MuPDF finds one.
    """

    def __init__(self) -> None:
        self.archive: Optional[pymupdf.Archive] = None
        self.face_css = f"* {{ font-family: {SYSTEM_FAMILIES}; }}"
        self.bundled: Optional[str] = None

        # Every named face that this machine actually has, embedded so MuPDF
        # draws the real thing rather than its own nearest guess.
        self.embedded: dict[str, str] = {}
        self._face_css: list[str] = []
        found: list[tuple[str, str]] = []
        for key, (family, regular, bold) in WINDOWS_FACES.items():
            path = _font_file(regular)
            if path is None:
                continue
            self.embedded[key] = family
            found.append((path.name, str(path)))
            self._face_css.append(
                f"@font-face {{ font-family: '{family}'; src: url({path.name}); }}")
            heavy = _font_file(bold)
            if heavy is not None:
                found.append((heavy.name, str(heavy)))
                self._face_css.append(
                    f"@font-face {{ font-family: '{family}'; font-weight: bold;"
                    f" src: url({heavy.name}); }}")
        if found:
            try:
                self.faces = pymupdf.Archive()
                for stored_as, real in found:
                    self.faces.add(real, stored_as)
            except Exception:  # noqa: BLE001 - fall back to the built-in faces
                self.faces = None
                self.embedded = {}
                self._face_css = []
        else:
            self.faces = None

        if FONT_DIR.is_dir():
            candidates = sorted(FONT_DIR.glob("*.ttf")) + sorted(FONT_DIR.glob("*.otf"))
            # "the first file found" sorted Noto's family to Black, which would
            # have set every Hindi masthead in the heaviest weight there is.
            # Name the weights wanted instead.
            regular = _weighted(candidates, "Regular")
            heavy = _weighted(candidates, "Bold")
            if regular is not None:
                self.bundled = regular.name
                try:
                    self.archive = pymupdf.Archive(str(FONT_DIR))
                    bold_rule = (
                        f"@font-face {{ font-family: npad; font-weight: bold;"
                        f" src: url({heavy.name}); }} " if heavy is not None
                        else "")
                    self.face_css = (
                        f"@font-face {{ font-family: npad;"
                        f" src: url({self.bundled}); }} {bold_rule}"
                        f"* {{ font-family: npad, {SYSTEM_FAMILIES}; }}"
                    )
                except Exception:  # noqa: BLE001 - fall back to system families
                    self.archive = None

    def archive_for(self, family: str):
        """The archive a family needs - the embedded faces, or the bundled one."""
        if family in self.embedded and self.faces is not None:
            return self.faces
        return self.archive

    def css(self, size: float, align: str, colour: str, bold: bool = False,
            family: str = "sans") -> str:
        face = self.face_css
        if family in self.embedded:
            # A real Windows face, embedded. The Devanagari stack still follows
            # it, so a Hindi masthead is drawn by a font that has the glyphs even
            # when the Latin is set in Calibri.
            name = self.embedded[family]
            face = (" ".join(self._face_css)
                    + f" * {{ font-family: '{name}', {SYSTEM_FAMILIES}; }}")
        elif family != "sans":
            # The bundled-font rule, if there is one, still wins for Devanagari;
            # this only re-points the general family.
            face = f"{face} * {{ font-family: {FAMILY_STACKS[family]}; }}"
        return (
            f"{face} "
            f"* {{ font-size: {size}px; text-align: {align}; color: {colour}; "
            f"font-weight: {'bold' if bold else 'normal'}; "
            f"line-height: 1.25; margin: 0; }}"
        )


def _image_bytes(clip: Clip) -> bytes:
    """Image data ready to embed, crop and rotation already applied."""
    return imageops.encode_for_export(clip)


def _draw_line(
    page,
    typeface: Typeface,
    text: str,
    rect: pymupdf.Rect,
    size: float,
    align: str = "center",
    colour: str = "#000000",
    bold: bool = False,
    family: str = "sans",
) -> float:
    """Lay one line of text into ``rect``. Returns how tall it actually came out.

    The box is always given generous room so a long masthead can wrap rather than
    vanish; the height that comes back is what the caller uses to sit the image
    directly beneath it, with no reserved space in between.
    """
    if not text.strip():
        return 0.0
    try:
        spare = page.insert_htmlbox(
            rect,
            f"<div>{html.escape(text)}</div>",
            css=typeface.css(size, align, colour, bold, family),
            archive=typeface.archive_for(family),
        )
        # insert_htmlbox returns (unused height, scale); negative means it did not fit
        unused = spare[0] if isinstance(spare, (tuple, list)) else 0.0
        if unused < 0:
            return rect.height
        return max(size * 1.2, rect.height - unused)
    except Exception:  # noqa: BLE001 - a text failure must not cost the page
        try:
            # The base-14 fallback, used only when the HTML box itself failed.
            # Anything without a base-14 equivalent falls back to Helvetica.
            # The base-14 fallback, used only when the HTML box itself failed.
            base = {"serif": ("tibo", "tiro"), "book": ("tibo", "tiro"),
                    "text": ("tibo", "tiro"),
                    "mono": ("cobo", "cour")}.get(family, ("hebo", "helv"))
            page.insert_text(
                (rect.x0, rect.y0 + size), text,
                fontname=base[0] if bold else base[1], fontsize=size,
            )
        except Exception:  # noqa: BLE001
            pass
        return size * 1.25


def _number_pages(document, typeface: "Typeface", style, width: float,
                  height: float) -> None:
    """Put a page number at the foot of every sheet except the cover.

    The margins here are deliberately narrow - 18pt - and a clipping is scaled to
    fill the page, so a number placed inside the margin would sit on the picture.
    It goes in the bottom margin itself, small and grey, and counts from the first
    clipping: the cover is not page one of anything.
    """
    size = layout.PAGE_NUMBER_SIZE
    for index in range(1, document.page_count):
        sheet = document[index]
        box = pymupdf.Rect(layout.MARGIN_SIDE, height - layout.MARGIN_BOTTOM,
                           width - layout.MARGIN_SIDE, height - 2.0)
        try:
            _draw_line(sheet, typeface, str(index), box, size, align="center",
                       colour=layout.PAGE_NUMBER_COLOUR, family=style.family)
        except Exception:  # noqa: BLE001 - a number must never cost a page
            pass


def measure_caption(typeface: Typeface, caption: str,
                    style: layout.HeadingStyle) -> Optional[float]:
    """How tall this caption comes out once set - on a scratch page, in the
    typeface and at the size the report prints it, wrapped to the page's
    width. None when it could not be measured, and the caller falls back to
    one line. Both exporters ask this, so a masthead that wraps to two lines
    in the PDF is given two lines in Word as well."""
    caption = (caption or "").strip()
    if not caption:
        return None
    page_width, page_height = layout.page_size(style.page)
    probe = layout.place(1000, 1000, has_caption=True, page=style.page,
                         caption_leading=style.leading())
    if probe.caption_rect is None:
        return None
    left, top, right, bottom = probe.caption_rect
    scratch = pymupdf.open()
    try:
        measuring = scratch.new_page(width=page_width, height=page_height)
        return _draw_line(
            measuring, typeface, caption,
            pymupdf.Rect(left, layout.MARGIN_TOP, right,
                         layout.MARGIN_TOP + (bottom - top)),
            style.size, align=style.align, bold=style.bold, family=style.family,
        )
    except Exception:  # noqa: BLE001 - one line's worth of room is the fallback
        return None
    finally:
        scratch.close()


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
) -> Result:
    """Write the newspad. ``clips`` is already in the order the user arranged.

    Both cover templates are rasterised to one picture by
    :mod:`clippings_manager.core.cover_render`, which paints the count and the date
    into the image itself. ``draw_cover_text=False`` says so: drawing them again
    here would print each line twice.
    """
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report_date = report_date or date.today()
    warnings: list[str] = []

    document = pymupdf.open()
    typeface = Typeface()
    # The panel's page choice wins when one was made; the argument stays for the
    # export dialog, which has had its own page picker since before the panel.
    style = heading or layout.HeadingStyle(page=page)
    page_width, page_height = layout.page_size(style.page)
    # A numbered sheet gives up a strip at the foot, so the number never lands on
    # the clipping. Costs a height-bound clipping about 1.8% of its size, and only
    # when the box is ticked.
    footer = layout.PAGE_NUMBER_BAND if style.page_numbers else 0.0

    def new_page():
        return document.new_page(width=page_width, height=page_height)

    # ------------------------------------------------------------ cover page
    cover = new_page()
    if cover_image:
        try:
            cover.insert_image(
                pymupdf.Rect(0, 0, page_width, page_height),
                filename=str(cover_image),
                keep_proportion=False,
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"The cover image could not be placed ({type(exc).__name__}); "
                f"a plain cover was used instead."
            )

    first_y, second_y = layout.cover_lines(page)
    line_height = layout.COVER_TEXT_SIZE * 1.7
    if draw_cover_text and cover_title.strip():
        _draw_line(
            cover, typeface, cover_title.strip(),
            pymupdf.Rect(0, first_y - line_height * 1.5, page_width,
                         first_y - line_height * 0.3),
            layout.COVER_TEXT_SIZE * 1.15,
        )
    if draw_cover_text:
        _draw_line(
            cover, typeface, f"NUMBER OF CLIPPINGS: {len(clips)}",
            pymupdf.Rect(0, first_y, page_width, first_y + line_height),
            layout.COVER_TEXT_SIZE,
        )
        _draw_line(
            cover, typeface, f"DATE : {report_date.strftime('%d.%m.%Y')}",
            pymupdf.Rect(0, second_y, page_width, second_y + line_height),
            layout.COVER_TEXT_SIZE,
        )

    # -------------------------------------------------------- clipping pages
    written = 0
    # Worked out once, up front, so the heading lands on the clipping that
    # carries it rather than on whichever one happens to come first.
    banners = layout.section_banners(clips)
    # Read once for the whole report, not once per page: the size and colour
    # are one setting for the document, so every heading in it matches.
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

        sheet = new_page()
        caption = sieve.clean(clip.printed_caption.strip())

        section_name = sieve.clean(banners.get(number - 1, ""))
        band = heading_band if section_name else 0.0
        # The address prints under the picture, so the picture stops short
        # of it rather than being written over.
        tail = footer + (layout.LINK_BAND if clip.url else 0.0)

        # The caption's real height decides where the whole block sits, so it is
        # measured before anything is drawn - onto a scratch page, not this one.
        # Drawing it first and placing afterwards is what left the heading at the
        # top of the sheet while the picture moved to the middle.
        caption_height = measure_caption(typeface, caption, style) if caption else None

        placement = layout.place(
            *clip.rendered_size(), has_caption=bool(caption),
            page=style.page, fit_page=fit_page, caption_height=caption_height,
            caption_leading=style.leading(), footer=tail, header=band,
        )

        if section_name:
            # The box is the band the picture below has already given up, so
            # the heading can never be drawn over the clipping it heads.
            _draw_line(
                sheet, typeface, section_name,
                pymupdf.Rect(layout.MARGIN_SIDE, layout.MARGIN_TOP,
                             page_width - layout.MARGIN_SIDE,
                             layout.MARGIN_TOP + heading_band),
                heading_style.size, align=style.align,
                colour=heading_style.colour, bold=True, family=style.family,
            )

        # Now that the block's position is settled, set the caption for real.
        if caption and placement.caption_rect is not None:
            _draw_line(
                sheet, typeface, caption,
                pymupdf.Rect(*placement.caption_rect),
                style.size, align=style.align, bold=style.bold,
                family=style.family,
            )

        try:
            sheet.insert_image(pymupdf.Rect(*placement.rect), stream=_image_bytes(clip))
        except Exception as exc:  # noqa: BLE001 - one bad image costs one page
            warnings.append(
                f"Clipping {number} ({caption or 'unnamed'}) could not be drawn "
                f"({type(exc).__name__}); its page was left blank."
            )
            continue

        if clip.url:
            link_top = min(
                placement.y + placement.height + layout.LINK_GAP,
                page_height - layout.MARGIN_BOTTOM - layout.LINK_BOX,
            )
            box = pymupdf.Rect(
                layout.MARGIN_SIDE, link_top,
                page_width - layout.MARGIN_SIDE, link_top + layout.LINK_BOX,
            )
            _draw_line(
                sheet, typeface, clip.url, box, layout.LINK_SIZE,
                align="center", colour="#0F5F76",
            )
            sheet.insert_link(
                {"kind": pymupdf.LINK_URI, "from": box, "uri": clip.url}
            )
        written += 1

    if style.page_numbers:
        _number_pages(document, typeface, style, page_width, page_height)

    # Which build wrote this. It is in the document properties rather than on a
    # page, so it changes nothing a reader sees, but a report that has been
    # emailed on can still say what made it - which is the only way to tell two
    # machines' output apart when they disagree.
    document.set_metadata({
        "title": f"Press media coverage {report_date.strftime('%d.%m.%Y')}",
        "author": "Northern Railway",
        "creator": f"Clippings Manager {version.describe()}",
        "producer": f"Clippings Manager {version.describe()}",
    })

    # Each text box embeds its own font reference, so a 165-page run ends up with
    # dozens of copies of the same face. garbage=4 with clean folds them into one
    # and takes about 9MB off the file.
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

    document.save(str(output), garbage=4, deflate=True, clean=True)
    pages = document.page_count
    document.close()
    return Result(path=output, pages=pages, clippings=written, warnings=warnings)
