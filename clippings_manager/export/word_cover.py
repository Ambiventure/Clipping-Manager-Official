"""The generated cover, written into Word as text rather than as a picture.

The PDF takes its cover as one finished image, which is right for a PDF: nobody
edits a PDF, and an image guarantees the printed page is exactly the page that
was arranged on screen. Word is different. The department edits the Word file
after it is built, and a cover pasted in as a picture cannot be edited at all -
the heading cannot be corrected, the date cannot be moved, and a typo means going
back to the application and building the whole report again.

So for Word the same layout is written out as real text: one floating box for the
heading, one for the date, and the logo as a picture. Every one of them is a Word
shape, so each can be clicked, retyped, restyled and dragged somewhere else
inside Word itself, and the words are words - they search, they spell-check, and
they survive a copy into another document.

Only the text and the logo are carried over, which is what was asked for. The
decorative frame and the watermark are drawn furniture; they belong to the
picture, and reproducing them here would give Word an uneditable image again.

The geometry arrives from :mod:`clippings_manager.core.cover_render` in page
pixels at 200 DPI, so this module is only arithmetic and XML: nothing about
where anything goes is decided here, which is what keeps the Word cover and the
on-screen preview showing the same sheet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence
from xml.sax.saxutils import escape

from docx.oxml import parse_xml
from docx.oxml.ns import qn
from docx.shared import Emu

# The cover is laid out on an A4 sheet at 200 DPI. Points are what Word wants.
PX_TO_PT = 72.0 / 200.0
EMU_PER_PT = 12700

# The face the cover is drawn in on screen is Devanagari-capable, and a heading
# in Hindi is ordinary here. Naming it in the complex-script slot as well is what
# stops Word choosing a Latin-only face and printing empty boxes.
COVER_FONT = "Nirmala UI"

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
_XMLNS = " ".join(f'xmlns:{k}="{v}"' for k, v in NS.items())

# Where a shape is anchored from. "page" means the sheet itself, so the numbers
# worked out for the preview can be used unchanged - anchoring to a margin or a
# paragraph would make them relative to something Word moves about.
_TEXTBOX_URI = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"


def _hex(colour: str) -> str:
    body = (colour or "").strip().lstrip("#")
    if len(body) == 6:
        try:
            int(body, 16)
            return body.upper()
        except ValueError:
            pass
    return "000000"


def _half_points(px: float, scale: float) -> int:
    """Word measures type in half-points, and refuses anything under 1pt."""
    return max(2, int(round(px * PX_TO_PT * scale * 2)))


def _twips(points: float) -> int:
    return max(0, int(round(points * 20)))


def _paragraph_xml(
    text: str,
    px: float,
    weight: int,
    colour: str,
    align: str,
    space_before_pt: float,
    scale: float,
) -> str:
    """One line of cover text, with the gap above it that the preview drew."""
    size = _half_points(px, scale)
    # Exact line spacing, so a heading occupies the same height in Word as it
    # does in the picture. Word's own "single" spacing is font-dependent and
    # would drift the block down the page line by line.
    line = _twips(px * 1.32 * PX_TO_PT * scale)
    bold = "<w:b/><w:bCs/>" if weight >= 600 else ""
    return (
        "<w:p><w:pPr>"
        f'<w:spacing w:before="{_twips(space_before_pt)}" w:after="0"'
        f' w:line="{line}" w:lineRule="exact"/>'
        f'<w:jc w:val="{align if align in ("left", "center", "right") else "center"}"/>'
        "<w:rPr>"
        f'<w:rFonts w:ascii="{COVER_FONT}" w:hAnsi="{COVER_FONT}"'
        f' w:cs="{COVER_FONT}"/>{bold}'
        f'<w:color w:val="{_hex(colour)}"/>'
        f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
        "</w:rPr></w:pPr>"
        "<w:r><w:rPr>"
        f'<w:rFonts w:ascii="{COVER_FONT}" w:hAnsi="{COVER_FONT}"'
        f' w:cs="{COVER_FONT}"/>{bold}'
        f'<w:color w:val="{_hex(colour)}"/>'
        f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
        "</w:rPr>"
        f'<w:t xml:space="preserve">{escape(text)}</w:t>'
        "</w:r></w:p>"
    )


def _rule_xml(colour: str, width_pt: float, box_width_pt: float,
              space_before_pt: float) -> str:
    """The short divider under the heading, as a ruled paragraph.

    A bottom border rather than a drawn line: a border belongs to the paragraph,
    so it stays with the heading when the heading is dragged or retyped in Word,
    which a separate line shape would not.
    """
    side = max(0.0, (box_width_pt - width_pt) / 2)
    return (
        "<w:p><w:pPr>"
        f'<w:spacing w:before="{_twips(space_before_pt)}" w:after="0"'
        ' w:line="20" w:lineRule="exact"/>'
        f'<w:ind w:left="{_twips(side)}" w:right="{_twips(side)}"/>'
        "<w:pBdr>"
        f'<w:bottom w:val="single" w:sz="18" w:space="0" w:color="{_hex(colour)}"/>'
        "</w:pBdr>"
        "</w:pPr></w:p>"
    )


def _anchor_xml(left_pt: float, top_pt: float, width_pt: float,
                height_pt: float, z: int, name: str, inner: str) -> str:
    left = int(round(left_pt * EMU_PER_PT))
    top = int(round(top_pt * EMU_PER_PT))
    width = max(EMU_PER_PT, int(round(width_pt * EMU_PER_PT)))
    height = max(EMU_PER_PT, int(round(height_pt * EMU_PER_PT)))
    return (
        f"<wp:anchor {_XMLNS} distT=\"0\" distB=\"0\" distL=\"0\" distR=\"0\""
        f' simplePos="0" relativeHeight="{z}" behindDoc="0" locked="0"'
        ' layoutInCell="1" allowOverlap="1">'
        '<wp:simplePos x="0" y="0"/>'
        '<wp:positionH relativeFrom="page">'
        f"<wp:posOffset>{left}</wp:posOffset></wp:positionH>"
        '<wp:positionV relativeFrom="page">'
        f"<wp:posOffset>{top}</wp:posOffset></wp:positionV>"
        f'<wp:extent cx="{width}" cy="{height}"/>'
        '<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        "<wp:wrapNone/>"
        f'<wp:docPr id="{z}" name="{escape(name)}"/>'
        "<wp:cNvGraphicFramePr/>"
        f"{inner}"
        "</wp:anchor>"
    )


def _textbox_xml(width_pt: float, height_pt: float, body: str) -> str:
    width = max(EMU_PER_PT, int(round(width_pt * EMU_PER_PT)))
    height = max(EMU_PER_PT, int(round(height_pt * EMU_PER_PT)))
    return (
        "<a:graphic>"
        f'<a:graphicData uri="{_TEXTBOX_URI}">'
        "<wps:wsp>"
        '<wps:cNvSpPr txBox="1"/>'
        "<wps:spPr>"
        f'<a:xfrm><a:off x="0" y="0"/><a:ext cx="{width}" cy="{height}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        "<a:noFill/><a:ln><a:noFill/></a:ln>"
        "</wps:spPr>"
        f"<wps:txbx><w:txbxContent>{body}</w:txbxContent></wps:txbx>"
        '<wps:bodyPr rot="0" vert="horz" wrap="square" lIns="0" tIns="0"'
        ' rIns="0" bIns="0" anchor="t" anchorCtr="0"><a:noAutofit/></wps:bodyPr>'
        "</wps:wsp></a:graphicData></a:graphic>"
    )


def _float_picture(paragraph, path: str, left_pt: float, top_pt: float,
                   width_pt: float, height_pt: float, z: int) -> None:
    """Place the logo as a floating picture at an exact spot on the sheet.

    The picture itself is added the ordinary way first, so python-docx does the
    fiddly part - storing the image, giving it a part and a relationship - and
    only then is the inline wrapper swapped for an anchored one. Writing the
    anchor from scratch would mean writing all of that by hand as well.
    """
    run = paragraph.add_run()
    shape = run.add_picture(str(path), width=Emu(int(round(width_pt * EMU_PER_PT))),
                            height=Emu(int(round(height_pt * EMU_PER_PT))))
    inline = shape._inline
    drawing = inline.getparent()
    graphic = inline.find(qn("a:graphic"))
    anchor = parse_xml(_anchor_xml(left_pt, top_pt, width_pt, height_pt,
                                   z, "Cover logo", ""))
    drawing.remove(inline)
    anchor.append(graphic)          # graphic goes last, as the schema requires
    drawing.append(anchor)


def add_cover(document, blocks: Sequence, page_width_pt: float,
              page_height_pt: float,
              warnings: Optional[list] = None) -> bool:
    """Write the option-2 cover onto page one as text and one picture.

    Returns False when there was nothing to write, so the caller can fall back
    to placing the picture.
    """
    blocks = [b for b in blocks if b is not None]
    if not blocks:
        return False

    from ..core import cover_render

    # The cover is laid out on A4. On Letter the sheet is a different shape, so
    # the whole thing is scaled by one factor and centred rather than stretched:
    # stretching would change the type size in one direction only.
    sheet_w = cover_render.PAGE_WIDTH * PX_TO_PT
    sheet_h = cover_render.PAGE_HEIGHT * PX_TO_PT
    scale = min(page_width_pt / sheet_w, page_height_pt / sheet_h)
    pad_x = (page_width_pt - sheet_w * scale) / 2
    pad_y = (page_height_pt - sheet_h * scale) / 2

    def to_pt(px: float, vertical: bool = False) -> float:
        return (px * PX_TO_PT * scale) + (pad_y if vertical else pad_x)

    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_after = Emu(0)

    written = False
    z = 10
    # Pictures first, so the caption sits on top of the artwork rather than
    # under it. Word paints anchored shapes in the order they appear.
    for item in blocks:
        if item.kind != "logo" or not item.path:
            continue
        if not Path(item.path).is_file():
            continue
        try:
            _float_picture(
                paragraph, item.path, to_pt(item.x), to_pt(item.y, True),
                item.width * PX_TO_PT * scale, item.height * PX_TO_PT * scale, z)
            written = True
            z += 1
        except Exception as exc:  # noqa: BLE001 - a cover without its logo
            if warnings is not None:
                warnings.append(
                    f"The cover logo could not be placed in the Word file "
                    f"({type(exc).__name__}); the rest of the cover was written."
                )

    # One box per movable block, so dragging one in Word moves the whole thing
    # rather than one line out of it.
    box_left = 120.0                       # the text column the layout wraps to
    box_width = float(cover_render.TEXT_MAX_WIDTH)
    for group in ("heading", "date", "caption"):
        parts = [b for b in blocks if b.group == group and b.kind != "logo"]
        if not parts:
            continue
        parts.sort(key=lambda b: b.y)
        top = min(b.y for b in parts)
        bottom = max(b.y + b.height for b in parts)
        # A block may name its own box. The generated cover's heading and date
        # do not - they belong in the middle column the layout wraps to - but a
        # caption dropped onto somebody's own artwork sits wherever they put it.
        own_left = max((b.box_x for b in parts if b.box_x >= 0), default=-1.0)
        own_width = max((b.box_w for b in parts if b.box_w > 0), default=-1.0)
        # A sideways drag moves the BOX, never the text inside it: a centred
        # heading nudged to the right is still centred, just centred somewhere
        # else. The lines keep their own alignment within the box.
        shift = parts[0].dx
        body: list[str] = []
        cursor = top
        for part in parts:
            gap = max(0.0, part.y - cursor) * PX_TO_PT * scale
            if part.kind == "rule":
                body.append(_rule_xml(part.colour, part.width * PX_TO_PT * scale,
                                      box_width * PX_TO_PT * scale, gap))
                cursor = part.y + part.height
                continue
            body.append(_paragraph_xml(
                part.text, part.px, part.weight, part.colour, part.align,
                gap, scale))
            cursor = part.y + part.px * 1.32
        if not body:
            continue
        here_width = own_width if own_width > 0 else box_width
        here_left = own_left if own_left >= 0 else box_left + shift
        box_w_pt = here_width * PX_TO_PT * scale
        box_h_pt = max(24.0, (bottom - top) * PX_TO_PT * scale) + 12.0
        anchor = _anchor_xml(
            to_pt(here_left), to_pt(top, True), box_w_pt, box_h_pt,
            z, f"Cover {group}",
            _textbox_xml(box_w_pt, box_h_pt, "".join(body)),
        )
        run = parse_xml(f"<w:r {_XMLNS}><w:drawing/></w:r>")
        run.find(qn("w:drawing")).append(parse_xml(anchor))
        paragraph._p.append(run)
        written = True
        z += 1
    return written
