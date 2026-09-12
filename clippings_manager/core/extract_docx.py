"""Extract newspaper clippings from a division .docx.

python-docx cannot see legacy VML shapes or ``a:srcRect`` crops, so this walks
``word/document.xml`` directly with lxml and resolves relationships by hand. The
result is an ordered :class:`~.assemble.Event` stream; everything after that --
sections, captions, junk flags -- is shared with the PDF path in ``assemble.py``.

Three things this gets right that a naive walk does not:

*   **VML shapes.** Ferozpur stores 2 of its 9 clippings as legacy ``<v:imagedata>``
    shapes rather than DrawingML ``<a:blip>``. A parser that only walks ``a:blip``
    drops them silently, with no error.
*   **Interleaving inside a paragraph.** Delhi puts a section header and 39 images in
    a single paragraph, so text and images have to be sequenced at run level, not
    paragraph level, or every clip inherits the wrong section.
*   **AlternateContent fallbacks.** Word often writes the same picture twice, as a
    DrawingML ``mc:Choice`` and a VML ``mc:Fallback``. Counting both double-counts
    the clip, so a fallback is skipped whenever its sibling choice holds a picture.
"""

from __future__ import annotations

import argparse
import html
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Optional

from lxml import etree

from .assemble import (  # noqa: F401  (re-exported for callers and tools)
    Event,
    ExtractionError,
    build_clips,
    detect_division,
    load_config,
    match_section,
)
from .models import Clip, CropRect
from .assemble import made_here

# --------------------------------------------------------------------------- XML

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}


def _q(prefix: str, tag: str) -> str:
    return "{%s}%s" % (NS[prefix], tag)


W_BODY = _q("w", "body")
W_P = _q("w", "p")
W_T = _q("w", "t")
W_HYPERLINK = _q("w", "hyperlink")
A_BLIP = _q("a", "blip")
A_SRCRECT = _q("a", "srcRect")
A_BLIPFILL = _q("pic", "blipFill")
V_IMAGEDATA = _q("v", "imagedata")
MC_ALTERNATE = _q("mc", "AlternateContent")
MC_CHOICE = _q("mc", "Choice")
MC_FALLBACK = _q("mc", "Fallback")
R_EMBED = _q("r", "embed")
R_LINK = _q("r", "link")
R_ID = _q("r", "id")


# ---------------------------------------------------------------------- walker


class _Walker:
    """Depth-first walk of the body producing a strictly document-ordered stream."""

    def __init__(self, rels: dict[str, dict]):
        self.rels = rels
        self.events: list[Event] = []
        self._buf: list[str] = []

    def _flush(self) -> None:
        text = "".join(self._buf).strip()
        self._buf.clear()
        if text:
            self.events.append(Event("text", text=text))

    @staticmethod
    def _contains_picture(element) -> bool:
        return (
            element.find(".//" + A_BLIP) is not None
            or element.find(".//" + V_IMAGEDATA) is not None
        )

    def _crop_for_blip(self, blip) -> CropRect:
        """Find the ``a:srcRect`` that belongs to this blip.

        srcRect is a sibling of the blip inside ``<pic:blipFill>``; looking it up by
        parent avoids picking up a crop that belongs to a different picture.
        """
        parent = blip.getparent()
        while parent is not None:
            src = parent.find(A_SRCRECT)
            if src is not None:
                return CropRect.from_src_rect(dict(src.attrib))
            if parent.tag == A_BLIPFILL or parent.tag.endswith("}blipFill"):
                break
            parent = parent.getparent()
        return CropRect()

    def _emit_image(self, rel_id: str, crop: CropRect, is_vml: bool) -> None:
        rel = self.rels.get(rel_id)
        target = "" if (rel is None or rel.get("external")) else rel["target"]
        self.events.append(
            Event("image", ref=target, crop=crop, is_vml=is_vml)
        )

    def walk(self, element) -> None:
        tag = element.tag

        if tag is etree.Comment or tag is etree.ProcessingInstruction:
            return

        if tag == MC_ALTERNATE:
            # Prefer the modern DrawingML choice; only fall back if it has no picture.
            choice = element.find(MC_CHOICE)
            fallback = element.find(MC_FALLBACK)
            if choice is not None and self._contains_picture(choice):
                self.walk(choice)
            elif fallback is not None:
                self.walk(fallback)
            elif choice is not None:
                self.walk(choice)
            return

        if tag == W_T:
            self._buf.append(element.text or "")
            return

        if tag == A_BLIP:
            rel_id = element.get(R_EMBED) or element.get(R_LINK) or ""
            self._flush()
            self._emit_image(rel_id, self._crop_for_blip(element), is_vml=False)
            return

        if tag == V_IMAGEDATA:
            rel_id = element.get(R_ID) or element.get(R_EMBED) or ""
            self._flush()
            self._emit_image(rel_id, CropRect(), is_vml=True)
            return

        if tag == W_HYPERLINK:
            rel_id = element.get(R_ID) or ""
            rel = self.rels.get(rel_id)
            if rel and rel.get("external"):
                self.events.append(Event("link", url=rel["target"]))

        if tag == W_P:
            for child in element:
                self.walk(child)
            self._flush()
            return

        for child in element:
            self.walk(child)


# --------------------------------------------------------------------- package


def _made_here(archive: zipfile.ZipFile) -> bool:
    """Whether this Word file is one of the program's own reports.

    The exporter writes its name into the document's comments, which Word
    keeps in docProps/core.xml as dc:description. Read as text, not parsed:
    a missing or odd core.xml is simply not ours.
    """
    try:
        core = archive.read("docProps/core.xml").decode("utf-8", "replace")
    except (KeyError, OSError, ValueError):
        return False
    found = re.search(r"<dc:description[^>]*>([^<]*)</dc:description>", core)
    return bool(found) and made_here(html.unescape(found.group(1)))


def _read_relationships(archive: zipfile.ZipFile) -> dict[str, dict]:
    """Map relationship id -> {target, external} for word/document.xml."""
    try:
        xml = etree.fromstring(archive.read("word/_rels/document.xml.rels"))
    except KeyError:
        return {}
    rels: dict[str, dict] = {}
    for node in xml:
        rel_id = node.get("Id")
        target = node.get("Target") or ""
        external = (node.get("TargetMode") or "").lower() == "external"
        if not rel_id:
            continue
        if not external:
            target = target.replace("\\", "/")
            if target.startswith("/"):
                target = target.lstrip("/")
            elif not target.startswith("word/"):
                target = "word/" + target.lstrip("./")
        rels[rel_id] = {"target": target, "external": external}
    return rels


def _image_size(data: bytes) -> tuple[int, int]:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        return image.width, image.height


# ------------------------------------------------------------------- extractor


def extract_docx(
    path: str | os.PathLike,
    division: Optional[str] = None,
    config: Optional[dict] = None,
) -> tuple[list[Clip], list[str]]:
    """Extract every clipping from one division document.

    Returns ``(clips, warnings)``. Warnings are plain-language strings safe to show
    in the UI; a per-image failure never aborts the whole document.
    """
    path = Path(path)
    config = config or load_config()
    warnings: list[str] = []

    if not path.exists():
        raise ExtractionError(f"{path.name}: file not found.")

    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ExtractionError(f"{path.name}: not a readable Word file ({exc}).") from exc

    with archive:
        try:
            document_xml = archive.read("word/document.xml")
        except KeyError as exc:
            raise ExtractionError(
                f"{path.name}: no document body found inside the file."
            ) from exc

        rels = _read_relationships(archive)
        try:
            root = etree.fromstring(document_xml)
        except etree.XMLSyntaxError as exc:
            raise ExtractionError(f"{path.name}: damaged document XML ({exc}).") from exc

        body = root.find(W_BODY)
        if body is None:
            raise ExtractionError(f"{path.name}: no document body found inside the file.")

        walker = _Walker(rels)
        walker.walk(body)
        events = walker.events

        # Resolve the image bytes before assembly; a failure here is reported and
        # skipped rather than aborting the document.
        ordinal = 0
        for event in events:
            if event.kind != "image":
                continue
            ordinal += 1
            if not event.ref:
                warnings.append(
                    f"{path.name}: clipping {ordinal} is a link to an image stored "
                    f"outside the document, so it could not be imported."
                )
                continue
            try:
                data = archive.read(event.ref)
            except KeyError:
                warnings.append(
                    f"{path.name}: clipping {ordinal} points at '{event.ref}', "
                    f"which is missing from the file."
                )
                continue
            try:
                event.width, event.height = _image_size(data)
            except Exception as exc:  # noqa: BLE001 - any decoder failure is reportable
                warnings.append(
                    f"{path.name}: clipping {ordinal} ({event.ref}) could not be read "
                    f"as an image ({type(exc).__name__}); it was skipped."
                )
                continue
            event.data = data
            event.ext = os.path.splitext(event.ref)[1].lower() or ".png"

        code = division or detect_division(path.name, config) or ""
        clips = build_clips(events, str(path), code, config, warnings,
                            own=_made_here(archive))

    return clips, warnings


# ----------------------------------------------------------------------- CLI


def dump(clips: list[Clip], out_dir: Path, prefix: str) -> list[dict]:
    """Write each clip as an image file and return manifest records."""
    out_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for clip in clips:
        name = f"{prefix}_{clip.doc_index + 1:03d}{clip.image_ext}"
        target = out_dir / name
        if clip.crop.is_identity:
            target.write_bytes(clip.image_bytes)
        else:
            # Crop applied on the way out so the cropped result is what gets reviewed.
            image = clip.render()
            if image.mode in ("P", "RGBA") and target.suffix in (".jpg", ".jpeg"):
                image = image.convert("RGB")
            image.save(target)
        records.append(clip.to_manifest(image_path=name))
    return records


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="extract_docx",
        description="Dump every clipping from a division .docx to a folder plus a "
                    "JSON manifest.",
    )
    parser.add_argument("inputs", nargs="+", help=".docx files, or a folder of them")
    parser.add_argument("-o", "--out", default="extracted", help="output folder")
    parser.add_argument("--division", help="force a division code (DLI, MB, UMB, ...)")
    parser.add_argument("--config", help="path to divisions.json")
    args = parser.parse_args(argv)

    config = load_config(Path(args.config)) if args.config else load_config()

    files: list[Path] = []
    for item in args.inputs:
        p = Path(item)
        if p.is_dir():
            files.extend(sorted(p.glob("*.docx")))
        else:
            files.append(p)
    files = [f for f in files if not f.name.startswith("~$")]

    out_root = Path(args.out)
    summary, total, failures = [], 0, 0

    for file in files:
        code = args.division or detect_division(file.name, config)
        try:
            clips, warnings = extract_docx(file, division=args.division, config=config)
        except ExtractionError as exc:
            failures += 1
            print(f"  !! {exc}", file=sys.stderr)
            summary.append({"file": file.name, "error": str(exc)})
            continue

        folder = out_root / (code or "unknown") / file.stem
        records = dump(clips, folder, code or "UNK")
        (folder / "manifest.json").write_text(
            json.dumps(
                {
                    "source_file": str(file),
                    "division": code,
                    "division_name": config["divisions"].get(code, {}).get("name", ""),
                    "caption_position": config["divisions"]
                    .get(code, {})
                    .get("caption_position", ""),
                    "clip_count": len(clips),
                    "warnings": warnings,
                    "clips": records,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        vml = sum(1 for c in clips if c.is_vml)
        cropped = sum(1 for c in clips if not c.crop.is_identity)
        junk = sum(1 for c in clips if c.probable_junk)
        captioned = sum(1 for c in clips if c.caption_raw)
        total += len(clips)

        print(
            f"{file.name}\n"
            f"    division={code or '(unknown)'}  clips={len(clips)}  "
            f"captions={captioned}  vml={vml}  cropped={cropped}  flagged={junk}\n"
            f"    -> {folder}"
        )
        for warning in warnings:
            print(f"    ! {warning}")
        summary.append(
            {"file": file.name, "division": code, "clips": len(clips),
             "captions": captioned, "vml": vml, "cropped": cropped, "flagged": junk}
        )

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nTotal clippings extracted: {total} from {len(files)} file(s), "
          f"{failures} unreadable.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
