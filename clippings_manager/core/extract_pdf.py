"""Extract clippings from a PDF: division reports and the 360 Degree document.

A PDF has no paragraph order, so reading order is recovered from geometry: every
image and every text block on a page is sorted by vertical position, then by
horizontal position for anything side by side. That produces the same ordered
:class:`~.assemble.Event` stream the .docx walk produces, so sections, captions and
junk flagging are shared code and behave identically in both formats.

Two details that matter:

*   **A caption can be split across text blocks.** Jammu writes 'DAINIK JAGARAN' and
    'JAMMU 9' as two separate blocks; the assembler joins a contiguous run, so the
    caption comes back whole.
*   **URLs come from link annotations, not from the visible text.** The 360 Degree
    document uses a subsetted font with no ToUnicode map, so the URL text extracts
    as garbage that looks plausible and is wrong. ``page.get_links()`` is clean.

Damaged files are expected: the sample 360 document has a broken xref that PyMuPDF
recovers from. Every page is read inside its own try/except so one bad page costs
one page, not the import.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import pymupdf

from . import imageops
from . import glyphmap
from .assemble import (
    Event,
    ExtractionError,
    build_clips,
    detect_division,
    load_config,
    looks_like_url,
    match_section,
    unreadable,
)
from .models import Clip
from .assemble import made_here

# Images smaller than this on the page are rules, bullets and spacer artwork.
MIN_PLACED_POINTS = 24.0

# A masthead strip sits directly on top of the article it belongs to: the Indian
# Express bar ends at y327.1 and the screenshot starts at y330.5. Two pictures
# that close together, over the same part of the page, are one clipping the
# source happened to store as two images - so they are stacked back into one
# rather than exported as a bare logo followed by a headless article.
STACK_GAP_POINTS = 14.0
STACK_OVERLAP = 0.55


def _repair_by_span(spans, page_fonts) -> str:
    """Read a line whose words were set in more than one font.

    "अमर उजाला, दिल्ली" is drawn as five pieces: the masthead in Mangal, a space,
    the rest of the masthead in Mangal, the comma in Calibri, and the city in
    Mangal again. Decoded as one run through any single font it cannot come out,
    because no single font drew it - the comma is glyph 853, which is a comma in
    Calibri and the letter "ù" in Mangal.

    Each span carries its own face, so each is read on its own and the line is
    put back together. Tried only after the whole line has failed, so a caption
    that already reads is never affected: a short span is easier to misread than
    a long one, and there is no reason to take that risk unless the plain way
    has already come to nothing.
    """
    pieces, mended = [], False
    for span in spans:
        raw = span.get("text", "")
        if not raw:
            continue
        if not unreadable(raw):
            pieces.append(raw)
            continue
        got = glyphmap.repair(raw, page_fonts)
        if got:
            pieces.append(got)
            mended = True
        elif not any(ch.isprintable() and not ch.isspace() and ord(ch) > 32
                     for ch in raw):
            pieces.append(" ")          # spacing between words; nothing is lost
        else:
            return ""                   # a span nobody can read: refuse it all
    if not mended:
        return ""
    # Each piece was tidied on its own, so the spacing around punctuation has to
    # be put right once at the end: the comma arrives as its own word.
    out = re.sub(r"\s+", " ", "".join(pieces)).strip()
    out = re.sub(r"\s+([,;:.])", r"\1", out)
    out = re.sub(r"([,;:])(\S)", r"\1 \2", out)
    return "" if unreadable(out) else out


def _join_wrapped_urls(lines):
    """Put a web address that wrapped across lines back together.

    The 360 Degree document prints the address under each screenshot and lets it
    run onto a second line. Left split, the tail reads as ordinary text and gets
    swept into the next clipping's caption. A continuation never contains a
    space, which is what tells it apart from a caption that follows an address.
    """
    joined = []
    index = 0
    while index < len(lines):
        text, box = lines[index]
        index += 1
        if looks_like_url(text):
            while index < len(lines):
                tail = lines[index][0]
                if " " in tail or looks_like_url(tail):
                    break
                text += tail
                index += 1
        joined.append((text, box))
    return joined


def _overlap(first, second) -> float:
    """How much of the narrower picture the two share horizontally, 0 to 1."""
    shared = min(first[2], second[2]) - max(first[0], second[0])
    narrower = min(first[2] - first[0], second[2] - second[0])
    return (shared / narrower) if narrower > 0 else 0.0


def _stack_runs(pictures):
    """Group pictures that sit one directly above the other into single items."""
    runs = []
    for picture in pictures:
        previous = runs[-1][-1] if runs else None
        if (
            previous is not None
            and not previous["furniture"]
            and not picture["furniture"]
            and -4.0 <= picture["box"][1] - previous["box"][3] <= STACK_GAP_POINTS
            and _overlap(previous["box"], picture["box"]) >= STACK_OVERLAP
        ):
            runs[-1].append(picture)
        else:
            runs.append([picture])
    return runs


def _open(path: Path):
    try:
        return pymupdf.open(path)
    except Exception as exc:  # noqa: BLE001 - PyMuPDF raises several types here
        raise ExtractionError(
            f"{path.name}: could not be opened as a PDF ({exc})."
        ) from exc


def _image_bytes(document, xref: int) -> tuple[bytes, str, int, int]:
    """Pull one embedded image out by xref, preserving its original encoding."""
    info = document.extract_image(xref)
    data = info["image"]
    ext = "." + (info.get("ext") or "png").lower()
    width = int(info.get("width") or 0)
    height = int(info.get("height") or 0)
    if not width or not height:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            width, height = image.width, image.height
    return data, ext, width, height


def _page_events(
    document,
    page,
    page_number: int,
    warnings: list[str],
    config: Optional[dict] = None,
) -> list[Event]:
    """Every image and text block on one page, in reading order."""
    items: list[tuple[float, float, Event]] = []
    # Where the section headers sit. The 360 Degree document draws each one over
    # a piece of artwork - a coloured banner, a speech bubble - and that artwork
    # is a picture like any other as far as the page is concerned.
    header_bands: list[tuple[float, float]] = []

    # Line by line, not block by block. A PDF block happily bundles a section header
    # and the caption beneath it into one lump; flattened, that lump is too long to
    # recognise as a header and 15 Moradabad clippings inherit the wrong section.
    # The assembler rejoins a caption that wraps, so splitting finer is safe.
    try:
        text_page = page.get_text("dict")
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            f"page {page_number}: text could not be read ({type(exc).__name__}); "
            f"any captions on it were skipped."
        )
        text_page = {"blocks": []}

    # Which faces this page is set in. A PDF that embedded its fonts without a
    # character map has a text layer of glyph NUMBERS rather than words, and the
    # font's name is the best clue to which font those numbers belong to.
    try:
        page_fonts = [entry[3] for entry in page.get_fonts()]
    except Exception:  # noqa: BLE001 - a hint, never a requirement
        page_fonts = []

    for block in text_page.get("blocks", []):
        if block.get("type") != 0:
            continue
        lines = []
        for line in block.get("lines", []):
            raw = "".join(span.get("text", "") for span in line.get("spans", []))
            text = " ".join(raw.split())
            if not text:
                continue
            if unreadable(text):
                # Glyph numbers, not words. Read them back through a real copy
                # of the font if we can be sure of the answer; if we cannot, the
                # line stays as it is and is dropped later, so a clipping comes
                # in unnamed rather than confidently wrong.
                #
                # Decoded from the RAW spans, not from the tidied text above.
                # Python counts 0x1c-0x1f as whitespace, and in a glyph-number
                # run those are ordinary letters - glyph 28 is "E" - so tidying
                # first turned "Indian Express" into "Indian xpress".
                mended = glyphmap.repair(raw, page_fonts)
                if not mended:
                    mended = _repair_by_span(line.get("spans", []), page_fonts)
                if mended:
                    text = mended
            lines.append((text, tuple(line.get("bbox") or (0, 0, 0, 0))))
        for text, box in _join_wrapped_urls(lines):
            if match_section(text, config) is not None:
                header_bands.append((box[1], box[3]))
            items.append((box[1], box[0], Event("text", text=text, page=page_number)))

    try:
        placed = page.get_image_info(xrefs=True)
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            f"page {page_number}: images could not be listed "
            f"({type(exc).__name__}); the page was skipped."
        )
        placed = []

    seen_on_page: set[int] = set()
    pictures = []
    for index, info in enumerate(placed, start=1):
        xref = info.get("xref") or 0
        box = tuple(info.get("bbox") or (0, 0, 0, 0))
        if max(box[2] - box[0], box[3] - box[1]) < MIN_PLACED_POINTS:
            continue
        if xref and xref in seen_on_page:
            continue          # the same image painted twice on one page
        seen_on_page.add(xref)
        try:
            data, ext, width, height = _image_bytes(document, xref)
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"page {page_number}: image {index} could not be decoded "
                f"({type(exc).__name__}); it was skipped."
            )
            continue
        pictures.append({
            "box": box,
            "xref": xref,
            "data": data,
            "ext": ext,
            "width": width,
            "height": height,
            # A section header printed across a picture means the picture is
            # the header's backdrop, not a clipping.
            "furniture": any(box[1] < bottom and top < box[3]
                             for top, bottom in header_bands),
        })

    pictures.sort(key=lambda picture: (picture["box"][1], picture["box"][0]))
    for run in _stack_runs(pictures):
        lead = run[0]
        data, ext = lead["data"], lead["ext"]
        native = (lead["width"], lead["height"])
        refs = str(lead["xref"])
        if len(run) > 1:
            try:
                stacked = imageops.stitch([
                    Clip(image_bytes=part["data"], image_ext=part["ext"],
                         native_width=part["width"], native_height=part["height"])
                    for part in run
                ])
            except Exception as exc:  # noqa: BLE001 - keep them separate instead
                warnings.append(
                    f"page {page_number}: the masthead and the article below it "
                    f"could not be joined ({type(exc).__name__}); they were kept "
                    f"as separate clippings."
                )
                for part in run[1:]:
                    items.append((part["box"][1], part["box"][0], Event(
                        "image",
                        ref=f"page {page_number} / xref {part['xref']}",
                        data=part["data"], ext=part["ext"],
                        width=part["width"], height=part["height"],
                        page=page_number, furniture=part["furniture"])))
            else:
                data, ext = stacked.image_bytes, stacked.image_ext
                native = (stacked.native_width, stacked.native_height)
                refs = " + ".join(str(part["xref"]) for part in run)
        items.append((lead["box"][1], lead["box"][0], Event(
            "image",
            ref=f"page {page_number} / xref {refs}",
            data=data, ext=ext, width=native[0], height=native[1],
            page=page_number, furniture=lead["furniture"])))

    try:
        for link in page.get_links():
            uri = link.get("uri")
            if not uri:
                continue
            rect = link.get("from") or pymupdf.Rect(0, 0, 0, 0)
            items.append((rect.y0, rect.x0, Event("link", url=uri, page=page_number)))
    except Exception:  # noqa: BLE001 - links are a bonus, never fatal
        pass

    # Sort top-to-bottom, then left-to-right for anything side by side. The small
    # vertical tolerance keeps a caption and its image from swapping when their
    # boxes overlap by a point or two.
    items.sort(key=lambda item: (round(item[0] / 4.0), item[1]))
    return [event for _y, _x, event in items]


def extract_pdf(
    path: str | os.PathLike,
    division: Optional[str] = None,
    config: Optional[dict] = None,
) -> tuple[list[Clip], list[str]]:
    """Extract every clipping from one PDF.

    Returns ``(clips, warnings)``, matching :func:`extract_docx.extract_docx`.
    """
    path = Path(path)
    config = config or load_config()
    warnings: list[str] = []

    if not path.exists():
        raise ExtractionError(f"{path.name}: file not found.")

    document = _open(path)
    events: list[Event] = []
    with document:
        if document.needs_pass:
            raise ExtractionError(
                f"{path.name}: the PDF is password protected, so it cannot be read."
            )
        for number in range(document.page_count):
            try:
                page = document.load_page(number)
            except Exception as exc:  # noqa: BLE001
                warnings.append(
                    f"{path.name}: page {number + 1} is damaged "
                    f"({type(exc).__name__}) and was skipped."
                )
                continue
            page_warnings: list[str] = []
            events.extend(
                _page_events(document, page, number + 1, page_warnings, config))
            warnings.extend(f"{path.name}: {w}" for w in page_warnings)

        code = division or detect_division(path.name, config) or ""
        try:
            stamps = document.metadata or {}
        except Exception:  # noqa: BLE001 - metadata is a courtesy
            stamps = {}
        own = made_here(stamps.get("creator"), stamps.get("producer"))
        clips = build_clips(events, str(path), code, config, warnings, own=own)

    return clips, warnings


# ----------------------------------------------------------------------- CLI


def main(argv: Optional[list[str]] = None) -> int:
    from .extract_docx import dump

    parser = argparse.ArgumentParser(
        prog="extract_pdf",
        description="Dump every clipping from a PDF to a folder plus a JSON manifest.",
    )
    parser.add_argument("inputs", nargs="+", help="PDF files, or a folder of them")
    parser.add_argument("-o", "--out", default="extracted_pdf", help="output folder")
    parser.add_argument("--division", help="force a division code (DLI, MB, UMB, ...)")
    args = parser.parse_args(argv)

    config = load_config()
    files: list[Path] = []
    for item in args.inputs:
        p = Path(item)
        files.extend(sorted(p.glob("*.pdf")) if p.is_dir() else [p])

    out_root = Path(args.out)
    total, failures = 0, 0
    for file in files:
        code = args.division or detect_division(file.name, config)
        try:
            clips, warnings = extract_pdf(file, division=args.division, config=config)
        except ExtractionError as exc:
            failures += 1
            print(f"  !! {exc}", file=sys.stderr)
            continue

        folder = out_root / (code or "unknown") / file.stem
        records = dump(clips, folder, code or "UNK")
        (folder / "manifest.json").write_text(
            json.dumps(
                {"source_file": str(file), "division": code,
                 "clip_count": len(clips), "warnings": warnings, "clips": records},
                indent=2, ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        captioned = sum(1 for c in clips if c.caption_raw)
        linked = sum(1 for c in clips if c.url)
        junk = sum(1 for c in clips if c.probable_junk)
        total += len(clips)
        print(f"{file.name}\n    division={code or '(unknown)'}  clips={len(clips)}  "
              f"captions={captioned}  links={linked}  flagged={junk}\n    -> {folder}")
        for warning in warnings[:8]:
            print(f"    ! {warning}")

    print(f"\nTotal clippings extracted: {total} from {len(files)} file(s), "
          f"{failures} unreadable.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
