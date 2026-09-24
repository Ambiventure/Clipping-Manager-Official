"""Tidying a pasted screenshot: the phone's bars and the blank margins.

A screenshot off a phone carries the phone with it - the status bar with the
time and the battery along the top, the navigation bar or its gesture pill
along the bottom - and a picture pasted out of a chat often carries a strip
of blank colour round it. None of that is the clipping. This finds those
bands and hands back a crop, which the clipping carries the way a trim drawn
by hand does: the picture itself is never altered, and "Whole picture" in the
preview puts everything back.

Conservative on purpose, in three rules:

*   A **bar** is a band at the top or bottom edge that is one colour with a
    few small marks in it - the time, the icons, the gesture pill - between
    a little over one per cent and a few per cent of the height, and that
    stops at a plain edge. It is cut only off a phone's own screenshot:
    taller than wide, and not tiny. On any other picture a band of that
    shape is left alone entirely.
*   A **margin** is a band at any edge that is truly blank - pure white or
    pure black, nothing in it - and not most of the picture. A scan's paper
    is neither pure nor blank, so a scan is left alone.
*   When in doubt, nothing is trimmed. A missed bar costs a moment with the
    trim tool; a wrong trim costs a piece of the story.
"""

from __future__ import annotations

import io
from typing import Optional

from PIL import Image, ImageChops, ImageOps

from .models import CropRect

#: How far a pixel may sit from a band's colour and still be "that colour".
TOLERANCE = 18
#: A margin is pure: this light or lighter, this dark or darker.
WHITE_FROM = 236
BLACK_TO = 24
#: A margin thinner than this fraction of the side is noise, not a margin...
LEAST_MARGIN = 0.006
#: ...and past this much of the picture it is not a margin, it is the picture.
MOST_MARGIN = 0.25
#: A status bar is this tall, as a fraction of the picture's height.
BAR_LEAST, BAR_MOST = 0.012, 0.075
#: The navigation bar or gesture strip along the bottom may be a little taller.
NAV_MOST = 0.10
#: A bar's rows are this much one colour - the gesture pill takes a third of
#: its row, the time and the icons far less...
BAR_ROW_SHARE = 0.55
#: ...and across the band those marks are a small part, but never nothing:
#: nothing at all is a margin, and the margin rule decides that.
BAR_MARKS_LEAST, BAR_MARKS_MOST = 0.0005, 0.30
#: Only a phone's own screenshot has bars cut off: taller than wide, and wide.
PHONE_LEAST_WIDTH = 480
#: AND SHAPED LIKE A PHONE. "Taller than wide" is not enough: a newspaper
#: cutting is usually taller than wide too, and one of the office's own - a
#: Times of India story 493 x 700 - was read as a phone screenshot and had the
#: first line of its headline cut off as a status bar. A white band with a few
#: dark marks in it is exactly what a headline's first line looks like. A phone
#: screen is far longer than that: 16:9 is 1.78 and today's are 19.5:9 (2.17)
#: to 21:9 (2.33). The cutting is 1.42, which is not a phone by any of them.
PHONE_LEAST_TALL, PHONE_MOST_TALL = 1.60, 2.60
#: How far back from the first ink a margin is cut, as a fraction of the side.
#: The glyphs' edges fade into the paper, and a cut placed exactly on the first
#: pixel that counts as ink shaves the tops off the letters.
MARGIN_SAFETY = 0.004
#: What counts as ink when a margin is being measured - stricter than the
#: TOLERANCE above, so the faint edge of a letter is ink and is kept.
INK_TOLERANCE = 8
#: Work on a picture no wider than this; the answer is in fractions anyway.
WORK_WIDTH = 480


def tidy_box(image: Image.Image, bars: bool = False) -> Optional[CropRect]:
    """The crop that takes the blank margins off, or None.

    `bars` also takes a phone's status and navigation bars off, and NOTHING IN
    THE PROGRAM ASKS FOR IT. The office's clippings are cuttings, not phone
    screens - in a year's use not one of them has carried a status bar - and
    the rule cost them a headline: a white band with a few dark marks in it is
    what a status bar looks like AND what the first line of a headline looks
    like, and a 493 x 700 cutting is "taller than wide" just as a phone is.
    Switching "Trim phone bars" off was the office's own workaround before this.

    Telling the two apart properly means recognising a battery and a signal
    meter, which every phone draws its own way and which are a dozen pixels
    across on a pasted picture - a great deal of machinery for something that
    has never once been needed. So the code stays, proven and tested, and the
    program simply never turns it on.
    """
    width, height = image.size
    if width < 120 or height < 120:
        return None
    work = image.convert("RGB")
    if width > WORK_WIDTH:
        work = work.resize((WORK_WIDTH, max(1, round(height * WORK_WIDTH / width))),
                           Image.Resampling.BILINEAR)
    w, h = work.size
    tall = height / width if width else 0.0
    phone = (width >= PHONE_LEAST_WIDTH
             and PHONE_LEAST_TALL <= tall <= PHONE_MOST_TALL)
    posterised = ImageOps.posterize(work, 5)

    # Bars first. Found on any picture, cut only off a phone's; where one is
    # found, the edge is the bar's and no margin is looked for there.
    top_bar = _bar(posterised, from_top=True)
    bottom_bar = _bar(posterised, from_top=False)
    phone = phone and bars
    top = top_bar if phone else 0
    bottom = bottom_bar if phone else 0

    left, m_top, right, m_bottom = _margins(work)
    # A BAR ONLY SPEAKS FOR ITS EDGE WHEN IT IS BEING CUT. The rule is "where a
    # bar is found the edge is the bar's, and no margin is looked for there" -
    # but a bar is only cut off a phone's screenshot, so on anything else a
    # bar that was FOUND and not cut was silently cancelling the margin as
    # well, and the edge came away untrimmed. Measured on the office's Times of
    # India cutting: its headline's first line reads as a bar, the cutting is
    # not a phone, and the white margin above it was therefore left on.
    if not (top_bar and phone):
        top = m_top
    if not (bottom_bar and phone):
        bottom = m_bottom

    box = CropRect(left=round(left / w, 6), top=round(top / h, 6),
                   right=round(right / w, 6), bottom=round(bottom / h, 6))
    if box.is_identity:
        return None
    if box.left + box.right > 0.6 or box.top + box.bottom > 0.6:
        return None                     # nothing left worth the name
    return box


def tidy_crop(image_bytes: bytes, bars: bool = False) -> Optional[CropRect]:
    """The same, for a clipping's bytes. Never raises."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.load()
            return tidy_box(image, bars=bars)
    except Exception:  # noqa: BLE001 - a picture that will not open is left alone
        return None


# ----------------------------------------------------------------- margins
def _pure(colour: tuple) -> bool:
    return all(v >= WHITE_FROM for v in colour) or all(v <= BLACK_TO for v in colour)


def _margins(work: Image.Image) -> tuple:
    """(left, top, right, bottom) in work pixels of blank border, each side."""
    w, h = work.size

    def blank_from(corner) -> Optional[tuple]:
        if not _pure(corner):
            return None
        plain = Image.new("RGB", work.size, corner)
        marks = ImageChops.difference(work, plain).convert("L").point(
            lambda v: 255 if v > INK_TOLERANCE else 0)
        return marks.getbbox()          # the box of everything NOT that colour

    def kept(band: int, span: int) -> int:
        # Back off from the first ink before anything is decided. A letter's
        # edge fades into the paper, so the first pixel dark enough to count is
        # already inside the glyph; cutting there takes the tops off the
        # letters, which is what the office saw.
        band = max(0, band - max(2, round(span * MARGIN_SAFETY)))
        share = band / span
        return band if LEAST_MARGIN <= share <= MOST_MARGIN else 0

    left = top = right = bottom = 0
    at_top = blank_from(work.getpixel((0, 0)))
    if at_top is not None:
        left, top = kept(at_top[0], w), kept(at_top[1], h)
    at_bottom = blank_from(work.getpixel((w - 1, h - 1)))
    if at_bottom is not None:
        right, bottom = kept(w - at_bottom[2], w), kept(h - at_bottom[3], h)
    return left, top, right, bottom


# -------------------------------------------------------------------- bars
def _row_signature(work: Image.Image, y: int) -> tuple:
    """(dominant colour, its share of the row) for one row."""
    w = work.size[0]
    colours = work.crop((0, y, w, y + 1)).getcolors(w) or []
    if not colours:
        return (0, 0, 0), 0.0
    count, colour = max(colours, key=lambda item: item[0])
    return colour, count / w


def _close(a: tuple, b: tuple) -> bool:
    return all(abs(x - y) <= TOLERANCE for x, y in zip(a, b))


def _bar(work: Image.Image, from_top: bool) -> int:
    """How many rows the bar at that edge takes, or 0 when there is none."""
    w, h = work.size
    most = int(h * (BAR_MOST if from_top else NAV_MOST))
    least = max(3, int(h * BAR_LEAST))
    rows = range(0, min(h, most + 2)) if from_top else range(h - 1, max(-1, h - most - 3), -1)
    colour = None
    run = marks = 0
    ended_plainly = False
    for y in rows:
        dominant, share = _row_signature(work, y)
        if colour is None:
            colour = dominant
        if share >= BAR_ROW_SHARE and _close(dominant, colour):
            run += 1
            marks += round((1.0 - share) * w)
            continue
        ended_plainly = True            # content, or a differently coloured strip
        break
    if not ended_plainly or run < least or run > most:
        return 0
    pixels = run * w
    if not (BAR_MARKS_LEAST * pixels <= marks <= BAR_MARKS_MOST * pixels):
        return 0
    return run
