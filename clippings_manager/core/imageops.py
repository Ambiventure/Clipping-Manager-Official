"""Merging and splitting clipping images.

Two things the morning routine actually needs:

*   **Merge.** A story that runs across two cuttings belongs on one page, so several
    clippings stitch into one image, widths matched to the widest.
*   **Split.** One scan often holds two separate articles side by side or stacked.
    Splitting makes two clippings out of one, either down the middle or at the
    quietest gap the image offers.

Neither touches the source document. Both produce new image bytes, and the originals
stay on the clips they came from until the undo stack drops them.
"""

from __future__ import annotations

import io
from typing import Iterable, Literal

from PIL import Image

from .models import Clip, Section

Direction = Literal["vertical", "horizontal", "auto"]

GAP = 14
BACKGROUND = (255, 255, 255)


def _as_rgb(clip: Clip) -> Image.Image:
    image = clip.render()
    return image if image.mode == "RGB" else image.convert("RGB")


def _to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


def stitch(clips: Iterable[Clip]) -> Clip:
    """Stack clippings into one image, top to bottom, widths matched.

    The result inherits the first clip's division, section and label, because that
    is the one the user was working from when they asked for the merge. It also
    keeps the first address and the first section heading found among the parts:
    both print in the report, and losing one to a merge would drop something from
    the page with nothing said about it.
    """
    clips = list(clips)
    if not clips:
        raise ValueError("nothing to merge")
    if len(clips) == 1:
        return clips[0]

    images = [_as_rgb(clip) for clip in clips]
    width = max(image.width for image in images)

    scaled = []
    for image in images:
        if image.width != width:
            height = max(1, round(image.height * width / image.width))
            image = image.resize((width, height), Image.LANCZOS)
        scaled.append(image)

    total = sum(image.height for image in scaled) + GAP * (len(scaled) - 1)
    canvas = Image.new("RGB", (width, total), BACKGROUND)
    y = 0
    for image in scaled:
        canvas.paste(image, (0, y))
        y += image.height + GAP

    first = clips[0]
    labels = [c.effective_label for c in clips if c.effective_label]
    return Clip(
        source_file=first.source_file,
        source_ref=f"merged from {len(clips)} clippings",
        division=first.division,
        doc_index=first.doc_index,
        section=first.section,
        image_bytes=_to_png(canvas),
        image_ext=".png",
        native_width=canvas.width,
        native_height=canvas.height,
        caption_raw=first.caption_raw,
        newspaper=first.newspaper,
        edition=first.edition,
        page=first.page,
        name_source=first.name_source,
        name_confidence=first.name_confidence,
        label=labels[0] if labels else "",
        # Merging must not lose what the parts carried: the address the report
        # prints under the picture, and the section the first of them opened.
        # Losing either drops something from the report with nothing said.
        url=next((c.url for c in clips if c.url), ""),
        section_title=next(
            (c.section_title for c in clips
             if c.section_title and (c.section is first.section
                                     or c.section_key)), ""),
        # The key travels with the words. Carried apart, a merged clipping
        # keeps a heading it can no longer be matched to, and the picker shows
        # nothing while the report still prints it.
        section_key=next(
            (c.section_key for c in clips
             if c.section_key and c.section_title), ""),
    )


def _quietest_cut(image: Image.Image, axis: str) -> int:
    """Find the emptiest line to cut along, using a simple ink projection.

    Newsprint is dense texture; the gutter between two articles is a band of near
    white. Summing darkness per row or column finds it without needing OpenCV.
    """
    import numpy as np

    grey = np.asarray(image.convert("L"), dtype=np.float32)
    ink = 255.0 - grey
    profile = ink.sum(axis=1) if axis == "horizontal" else ink.sum(axis=0)

    length = len(profile)
    if length < 40:
        return length // 2
    # Only consider the middle 60%, so a white margin is never chosen as the cut.
    lo, hi = int(length * 0.2), int(length * 0.8)
    window = profile[lo:hi]
    return lo + int(window.argmin())


def split(clip: Clip, direction: Direction = "auto") -> list[Clip]:
    """Cut one clipping into two.

    ``vertical`` cuts left/right, ``horizontal`` cuts top/bottom, and ``auto`` picks
    whichever the image's shape suggests: a wide image is usually two columns.
    """
    image = _as_rgb(clip)
    if direction == "auto":
        direction = "vertical" if image.width >= image.height else "horizontal"

    if direction == "vertical":
        cut = _quietest_cut(image, "vertical")
        cut = max(20, min(cut, image.width - 20))
        boxes = [(0, 0, cut, image.height), (cut, 0, image.width, image.height)]
        suffixes = ("left", "right")
    else:
        cut = _quietest_cut(image, "horizontal")
        cut = max(20, min(cut, image.height - 20))
        boxes = [(0, 0, image.width, cut), (0, cut, image.width, image.height)]
        suffixes = ("top", "bottom")

    pieces: list[Clip] = []
    for index, (box, suffix) in enumerate(zip(boxes, suffixes)):
        piece = image.crop(box)
        pieces.append(
            Clip(
                source_file=clip.source_file,
                source_ref=f"{clip.source_ref} ({suffix})",
                division=clip.division,
                doc_index=clip.doc_index,
                section=clip.section,
                image_bytes=_to_png(piece),
                image_ext=".png",
                native_width=piece.width,
                native_height=piece.height,
                caption_raw=clip.caption_raw,
                newspaper=clip.newspaper,
                edition=clip.edition,
                page=clip.page,
                name_source=clip.name_source,
                name_confidence=clip.name_confidence,
                label=clip.label,
                # The heading opens the section, so it stays on the piece that
                # comes first. Copied onto both, the same words would be
                # printed twice - which is the one thing section_banners
                # exists to prevent.
                section_title=clip.section_title if index == 0 else "",
                section_key=clip.section_key if index == 0 else "",
            )
        )
    return pieces


def plainly_drawable(data: bytes) -> bool:
    """Whether these bytes are a picture every program can draw.

    Baseline JPEG, eight bits, grey or RGB, nothing to rotate. That is the one
    encoding no reader has an opinion about.

    The exclusions are the ones that actually go wrong. A CMYK JPEG - which is
    what a print-workflow PDF hands over - is drawn by Pillow and by MuPDF and
    by nothing else in an office: Word shows a blank frame and Acrobat is
    unreliable, so a page comes out with its heading and no picture. JPEG 2000
    is worse and comes out of the same PDFs. A progressive JPEG and an EXIF
    orientation are milder but still read differently in different programs.
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "JPEG":
                return False
            if image.mode not in ("RGB", "L"):
                return False        # CMYK, YCCK, 16-bit, palette
            if image.info.get("progression") or image.info.get("progressive"):
                return False
            orientation = (image.getexif() or {}).get(274, 1)
            if orientation not in (0, 1, None):
                return False        # a reader that honours EXIF turns it
    except Exception:  # noqa: BLE001 - anything unreadable is not plain
        return False
    return True


def encode_for_export(clip: Clip) -> bytes:
    """Image bytes ready to embed, in a form every reader can draw.

    A picture that is already the plainest kind of JPEG goes in exactly as it
    arrived - no re-encode, no generation loss, no bloat. Everything else is
    re-encoded to that, because a report is opened in Word, in Acrobat, in
    whatever PDF viewer the office happens to have, and on a machine that is not
    this one. It used to be enough for the file name to end in .jpg, which is
    not a fact about the bytes: a CMYK JPEG lifted out of a source PDF has that
    name, went straight into the report untouched, and was drawn by nothing but
    the two libraries here - so a page arrived with its heading and a blank
    space where the clipping should be.

    Transparency is flattened onto white rather than carried through as an
    alpha channel. The page is white, so it looks the same, and it removes the
    soft mask - the other thing a strict reader draws as nothing at all.
    """
    untouched = clip.crop.is_identity and not clip.rotation % 360
    if untouched and plainly_drawable(clip.image_bytes):
        return clip.image_bytes

    image = clip.render()
    if image.mode == "P":
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
    if image.mode in ("RGBA", "LA"):
        flat = Image.new("RGB", image.size, BACKGROUND)
        flat.paste(image, mask=image.getchannel("A"))
        image = flat
    if image.mode != "RGB":
        image = image.convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=88, optimize=True, subsampling=0,
               progressive=False)
    return buffer.getvalue()


# ------------------------------------------------- is it the same picture?

# How far apart two fingerprints may be and still be the same cutting.
#
# Set from cases the user judged by eye, which is the only authority there is
# for what counts as "the same cutting". Every pair in one morning's files
# whose headlines matched, with their verdict:
#
#      0 apart   the same cutting                      flag
#     18 apart   the same cutting, two divisions       flag
#     19 apart   the same cutting, two divisions       flag
#     ---------------------------------- nothing in between
#     37 apart   two different cuttings, one story     keep
#     41 apart   two different cuttings, one story     keep
#
# Anything from 20 to 34 gives that answer; 28 is the middle of the gap, so it
# is as far as possible from either mistake. An earlier 12 was drawn from the
# spread of pictures known to be identical and was too tight - the same cutting
# scanned by two divisions, cropped differently and stamped with different
# mastheads, is further from itself than that.
#
# What the number is really guarding is the other direction. Those two pairs at
# 37 and 41 score 100 out of 100 on their words - the headline identical, word
# for word - so nothing about the text could ever have told them apart.
PICTURE_APART = 28

# And the same again for the lower part of the cutting alone. A newspaper's own
# masthead banner sits across the top - the title, the strapline, the colour -
# and it is IDENTICAL on every cutting from that paper. Two entirely different
# stories from one paper therefore start out agreeing on a quarter of the whole
# picture before anything about the stories is considered, which brought two of
# them to 27 apart: inside the cut-off, and wrong.
#
# Below the banner they have nothing in common, and the numbers say so. On the
# pairs judged by eye across two mornings: the same cutting scores 4 to 28 on
# its lower part, and those two different stories score 34. Thirty-one sits
# between them.
#
# This survives a WhatsApp forward, which was the thing to check - all six
# forwards that matched a cutting inside a division's report still match.
LOWER_APART = 31

# How much of the cutting counts as "lower". Enough to clear a masthead banner,
# which runs to about a quarter of the height on the papers that use one.
LOWER_KEEP = 0.70


def content_box(image):
    """The printed matter, without the blank paper around it.

    One division scans the cutting tight and another leaves a centimetre of
    white all round; trimming to the ink makes the two comparable.
    """
    from PIL import Image as _Image

    grey = image.convert("L").point(lambda v: 0 if v < 200 else 255)
    box = _Image.eval(grey, lambda v: 255 - v).getbbox()
    return image.crop(box) if box else image


def fingerprint_lower(data: bytes) -> str:
    """The same print, of the lower part of the cutting only.

    What this leaves out is the newspaper's masthead banner, which is the same
    on every cutting that paper prints and so makes unrelated stories look
    alike. What it keeps is the story: its columns, its photograph, its shape.
    """
    return _print_of(data, lower=True)


def fingerprint(data: bytes) -> str:
    """A short print of what a cutting LOOKS like, as hex.

    A difference hash: shrink to nine by eight, then record whether each pixel
    is lighter than the one to its right. What survives is the arrangement of
    dark and light - the columns, the photograph, the headline block - and what
    does not is the size, the paper colour and the JPEG quality. So a cutting
    rescanned, re-cropped and stamped with a masthead band still prints nearly
    the same, while a different cutting of the same story does not.
    """
    return _print_of(data, lower=False)


# How far apart two ink profiles may be and still be the same cutting. The
# worst genuine rescan measured on the sample mornings sits at 0.838; 0.85 was
# tried and rejected as too close to it. A missed repeat prints a story twice
# and somebody notices; a repeat wrongly found deletes a clipping and nobody
# does - so the margin goes on the safe side even though a tighter cut-off
# would reject more pairs.
INK_APART = 0.90

# Content boxes further apart in shape than this are different cuttings. It
# rejects the pair the picture prints get most badly wrong on a real morning -
# two unrelated cuttings 8 bits apart out of 64, but 137% apart in shape.
SHAPE_APART = 0.30


def _prepared(data: bytes):
    """Decode, strip the masthead band, trim to the content box. Once.

    This used to be done twice - fingerprint() and fingerprint_lower() each
    decoded the same bytes and each ran strip_band and content_box over them -
    and the preprocessing is the expensive half: 12.7ms of the 15ms, paid twice
    per clipping. On a hundred and forty clipping morning that is nearly two
    seconds spent working out the same thing again.
    """
    from PIL import Image as _Image

    from . import ocr

    image = _Image.open(io.BytesIO(data))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    return content_box(ocr.strip_band(image))


def _dhash(image, columns: int, rows: int) -> str:
    """The classic difference hash: is each pixel lighter than its neighbour."""
    from PIL import Image as _Image

    grey = image.convert("L").resize((columns + 1, rows), _Image.LANCZOS)
    pixels = list(grey.getdata())
    bits = 0
    for row in range(rows):
        base = row * (columns + 1)
        for column in range(columns):
            bits = (bits << 1) | (1 if pixels[base + column]
                                  > pixels[base + column + 1] else 0)
    return f"{bits:0{(columns * rows + 3) // 4}x}"


def _lower_part(image):
    cut = image.crop((0, int(image.height * (1 - LOWER_KEEP)),
                      image.width, image.height))
    return cut if cut.height >= 8 and cut.width >= 8 else None


def measure_clip(clip) -> dict:
    """Everything worth knowing about one clipping's picture, AS IT PRINTS.

    Prefer this to measure() anywhere a Clip is to hand. A Word picture often
    carries a crop - the srcRect Word stored with it - and render() applies it
    while the raw bytes do not. Measuring the raw bytes describes pixels that
    are cropped away before anything is printed, so two copies of one cutting
    cropped differently measured as two different cuttings. On the sample data
    that moved a print by up to 11 bits of 64, against a budget of 28.

    Falls back to the raw bytes for anything that will not render, which is the
    same answer the old code gave and never worse.
    """
    data = getattr(clip, "image_bytes", b"") or b""
    if not data:
        return {"whole": "", "lower": "", "fine": "", "width": 0,
                "height": 0, "ink": ""}
    crop = getattr(clip, "crop", None)
    turned = getattr(clip, "rotation", 0) % 360
    if (crop is None or crop.is_identity) and not turned:
        return measure(data)          # nothing to apply: the cheap path
    try:
        return _measured(clip.render())
    except Exception:  # noqa: BLE001 - a picture that will not render
        return measure(data)


def measure(data: bytes) -> dict:
    """Everything worth knowing about one picture, from a single decode.

    Returns the two prints the comparison has always used, the finer 256-bit
    print, the size of the content box, and the ink profile - all off one pass,
    because the decode and the trimming are what the time goes on.

    Takes raw bytes, so it knows nothing about a crop. Where there is a Clip,
    use measure_clip.
    """
    from PIL import Image as _Image

    try:
        image = _Image.open(io.BytesIO(data))
        image.load()
    except Exception:  # noqa: BLE001 - a picture we cannot print is not a fault
        return {"whole": "", "lower": "", "fine": "", "width": 0,
                "height": 0, "ink": ""}
    return _measured(image)


def _measured(image) -> dict:
    """The measurements, off an already-decoded picture."""
    from . import ocr

    blank = {"whole": "", "lower": "", "fine": "", "width": 0, "height": 0,
             "ink": ""}
    try:
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image = content_box(ocr.strip_band(image))
    except Exception:  # noqa: BLE001
        return blank
    try:
        out = dict(blank)
        out["whole"] = _dhash(image, 8, 8)
        out["fine"] = _dhash(image, 16, 16)
        out["width"], out["height"] = image.width, image.height
        lower = _lower_part(image)
        out["lower"] = _dhash(lower, 8, 8) if lower is not None else ""
        out["ink"] = _ink_profile(image)
        return out
    except Exception:  # noqa: BLE001
        return blank


def _ink_profile(image) -> str:
    """Where the ink sits: the mean darkness of every row and every column.

    A thumbnail hash asks what the picture looks like squinted at. This asks
    where the words and pictures actually are on it - two cuttings of different
    stories from one newspaper can squint alike and still put their columns and
    headline in different places.

    Normalised to a unit vector so it is a shape rather than a brightness, and
    written as text so a saved session stays plain JSON.
    """
    from PIL import Image as _Image

    try:
        import numpy as np

        grey = image.convert("L").resize((64, 64), _Image.LANCZOS)
        ink = 255.0 - np.asarray(grey, dtype=np.float32)
        parts = []
        for line in (ink.mean(axis=1), ink.mean(axis=0)):
            line = line - line.mean()
            size = float(np.linalg.norm(line))
            parts.append(line / size if size > 1e-6 else line)
        return ",".join(f"{value:.4f}" for value in
                        np.concatenate(parts).tolist())
    except Exception:  # noqa: BLE001 - the profile is an extra, never required
        return ""


def ink_apart(first: str, second: str) -> float:
    """How differently two pictures lay their ink out. 0 is identical.

    Returns 0.0 when either profile is missing, so a clipping from an older
    saved session is never rejected for want of one.
    """
    if not first or not second:
        return 0.0
    try:
        left = [float(value) for value in first.split(",")]
        right = [float(value) for value in second.split(",")]
    except ValueError:
        return 0.0
    if len(left) != len(right) or len(left) != 128:
        return 0.0
    # A half that carries no information is left out of the average rather than
    # counted as disagreement. A picture whose rows are all the same darkness -
    # a plain scan, a chart, a photograph with an even sky - has a flat profile
    # for that half, and scoring it as zero agreement put two IDENTICAL pictures
    # at 0.5, halfway to being called different. Measured on a flat test image:
    # 0.500 before, 0.000 after.
    scores = []
    for start in (0, 64):
        first_half = left[start:start + 64]
        second_half = right[start:start + 64]
        if (not any(first_half)) or (not any(second_half)):
            continue
        scores.append(sum(a * b for a, b in zip(first_half, second_half)))
    if not scores:
        return 0.0
    return 1.0 - sum(scores) / len(scores)


def shapes_apart(first: tuple, second: tuple) -> float:
    """How differently shaped two content boxes are. 0 is the same shape.

    Content boxes, never raw pixels: a genuine rescan pair differs by 56% on
    raw dimensions - one copy carries a typed caption band above the cutting -
    and by 2.8% once both are trimmed to what is actually on them.
    """
    try:
        left = first[0] / first[1]
        right = second[0] / second[1]
    except (TypeError, ZeroDivisionError, IndexError):
        return 0.0
    if left <= 0 or right <= 0:
        return 0.0
    return abs(left - right) / min(left, right)


def _print_of(data: bytes, lower: bool) -> str:
    """One print, for callers that only want one. See measure() for both."""
    found = measure(data)
    return found["lower"] if lower else found["whole"]


def pictures_apart(first: str, second: str) -> int:
    """How many of the sixty-four differ. -1 when either has no print.

    int.bit_count rather than counting the ones in a binary string: this is
    called once per pair, and a morning of a hundred and fifty clippings is ten
    thousand pairs on the thread that draws the window. Measured 3x faster on
    the 64-bit prints and 11x on the 256-bit ones, for the same answers.
    """
    if not first or not second:
        return -1
    try:
        return (int(first, 16) ^ int(second, 16)).bit_count()
    except ValueError:
        return -1
