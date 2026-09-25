"""Reading the headline off a clipping.

A clipping is a picture. Nothing in the source documents carries the article's
own words - the only text a Word or PDF file holds is the caption the division
typed above the picture ("Dainik Bhaskar page no- 2 Firozpur"), which names the
newspaper and says nothing about what the story is. So the only way to tell that
two clippings from two different files are the same cutting is to read them.

What is wanted is the HEADLINE, not the article. The body text is long, dense,
and comes out of OCR differently every time; the headline is a handful of words
set in the largest type on the cutting, and it is what makes one story distinct
from another. So this reads the top of the picture, measures how tall each line
of type is, and keeps only the tallest - which is the headline and nothing else.

That distinction is not cosmetic. Measured on one day of real files: matching on
the whole top of the cutting scored two genuine copies of the same Punjab Kesari
article at 70 out of 100, because the two scans carry different masthead strips
("edition: ambala, page no. 8" against "ludhiana sep 06, 2026"), while two
DIFFERENT papers covering the same story scored 73. The two were inseparable.
Matching on the headline alone puts the genuine copies at 100.

Nothing here is required for the application to run. If the engine or its
language data is missing - somebody running from source without it - every
function quietly answers "I could not read this", and the clipping is simply
never considered for duplication.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Where the language data lives. Found the same way the Devanagari display font
# is, so it travels inside the packaged application and needs nothing installed
# on the machine it lands on.
TESSDATA = Path(__file__).resolve().parent.parent / "assets" / "tessdata"

# Hindi first: these are Hindi newspapers, and the language listed first is the
# one Tesseract leans towards when a shape could be either script.
LANGUAGES = "hin+eng"

# How much of the picture to look at, and how big to make it. A headline is at
# the top by definition, and reading the whole cutting costs several times as
# long for text that is then thrown away. 1200px across is where accuracy stops
# improving on this material - below about 900 the Devanagari conjuncts start
# to break up, above 1600 it is only slower.
TOP_BAND = 0.40
# Where to look if the first band held nothing but the paper's own name. Some
# divisions send a whole page rather than a cutting, and on those the story's
# headline can sit below the top four-tenths. Looking deeper costs a second
# reading, so it is only done when the first found nothing.
DEEPER_BAND = 0.72
TARGET_WIDTH = 1200
MIN_WIDTH = 240
#: Under this there is no picture to enlarge - see _prepare. It replaced
#: MIN_WIDTH as the floor, which was turning away narrow cuttings entirely.
TINY_WIDTH = 40
#: A reading this poor is treated as doubtful, and is what makes the program
#: try the picture the other ways up. Measured over the office's own cuttings:
#: the right way up they come back at 96, and the wrong way up at 0, 26, 39
#: and 75 - and the 39 is confident-looking nonsense off a sideways cutting,
#: which is exactly the case this exists for. So the line is drawn above it.
POOR_READING = 55.0
#: ...and another way up only REPLACES what we have when it is clearly better,
#: not merely better. A wrong way up can score 75 on a cutting whose columns
#: happen to read as lines, so a one-point win is not evidence of anything.
CLEARLY_BETTER = 15.0

# A line counts as part of the headline only if it is nearly as tall as the
# tallest line found. This is set high on purpose, and the reason is stability
# rather than tidiness.
#
# A headline that runs over two lines has both lines at the SAME size, so they
# are both kept. What sits just below the headline is the kicker - the small
# line naming what the story is about - and at 0.62 it was picked up in one
# rendering of a cutting and missed in another. Two readings of the SAME
# picture then came out as "डीआरएम ने अधिकारियों संग परखी व्यवस्थाएं" and
# "आलमनगर, अमौसी और लखनऊ स्टेशन का निरीक्षण डीआरएम ने अधिकारियों संग परखी
# व्यवस्थाएं", which score 68 against each other - under the cutoff, so a plain
# repeat went unflagged.
#
# Measured over 89 cuttings that appear in this folder in both formats: at 0.62
# only 55% of them read identically twice, at 0.85 it is 68%. It also pushes
# the two DIFFERENT cuttings apart, because the kicker was the text they had in
# common - one such pair falls from 85 to 64.
TALL_ENOUGH = 0.85

# How near the anchor's size a line must be to belong to the same headline, and
# how big a gap may sit between them, as a share of a line's own height.
#
# These replace TALL_ENOUGH as the rule that decides, and the pair of them is
# the point: SIZE alone cannot tell a second line of headline from the kicker
# under it, because the two overlap. POSITION can. A headline's second line sits
# directly beneath the first at normal leading; a kicker sits after a visible
# break, and is smaller as well.
#
# Measured against every line the old rule dropped on one real morning:
#     genuine second lines   0.76 to 0.83 of the anchor, gaps 0.01 to 0.24
#     kickers and bylines    0.66 to 0.70, or gaps of 0.55 and more
# so 0.75 and 0.35 sit in the space between the two populations, with room
# either side. TALL_ENOUGH is kept for the very tall anchor line itself and for
# anything still comparing against the old behaviour.
SAME_BLOCK = 0.75
BLOCK_GAP = 0.35


# A date, however the reader mangles the separators - "06.09.2026", "08I09I2026",
# "06-09-2026", "25 09 2026". Dates belong to mastheads; headlines do not
# carry them. THE SEPARATORS MUST BE THERE: without them any four figures in
# a row were a date - "अभियान-2026", "22.256 किलो", train 12005, "94.35
# फीसदी" - and the line of the headline holding them was thrown away as a
# stamped date. On the office's report pages that cost the first line of
# every "स्वच्छता ही सेवा अभियान-2026" headline.
_DATE_GAP = r"(?:\s*[^\w\s]{1,2}\s*|\s+|\s*[Il]\s*)"
# And the date in words a dateline opens the story with - "Jammu, 23
# September 2026:", "24 सितंबर, 2026" - day, month and year all three. A
# headline's "13 सितंबर से" has no year, and stays a headline.
_MONTHS = ("jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|"
           "\u091c\u0928\u0935\u0930\u0940|\u092b\u0930\u0935\u0930\u0940|"
           "\u092e\u093e\u0930\u094d\u091a|\u0905\u092a\u094d\u0930\u0948\u0932|"
           "\u092e\u0908|\u091c\u0942\u0928|\u091c\u0941\u0932\u093e\u0908|"
           "\u0905\u0917\u0938\u094d\u0924|\u0938\u093f\u0924\u0902\u092c\u0930|"
           "\u0938\u093f\u0924\u092e\u094d\u092c\u0930|"
           "\u0905\u0915\u094d\u091f\u0942\u092c\u0930|"
           "\u0905\u0915\u094d\u0924\u0942\u092c\u0930|"
           "\u0928\u0935\u0902\u092c\u0930|\u0928\u0935\u092e\u094d\u092c\u0930|"
           "\u0926\u093f\u0938\u0902\u092c\u0930|\u0926\u093f\u0938\u092e\u094d\u092c\u0930")
DATED = re.compile(r"(?<!\d)\d{1,2}" + _DATE_GAP + r"\d{1,2}" + _DATE_GAP
                   + r"\d{2,4}(?!\d)"
                   + r"|(?<!\d)\d{1,2}\s*(?:" + _MONTHS + r")\w*\.?\s*,?\s*\d{4}(?!\d)",
                   re.IGNORECASE)

# Above that, a line with a lot of digits and few letters is a strip of
# furniture rather than a sentence.
MASTHEAD_DIGITS = 6
MASTHEAD_LETTERS = 24


_names: list = []


def _known_names() -> list:
    """Every newspaper and city name the application knows, folded for compare.

    The application already keeps these, in both scripts - "Amar Ujala" and
    "अमर उजाला", "Dainik Jagran" and "दैनिक जागरण" - because the importer needs
    them to work out which paper a caption names. The same list says whether a
    line of a cutting is the paper's own name rather than the story's headline.
    """
    global _names
    if _names:
        return _names
    try:
        import json

        where = (Path(__file__).resolve().parent.parent / "config"
                 / "newspapers.json")
        data = json.loads(where.read_text(encoding="utf-8"))
        found = set()
        for group in ("newspapers", "editions"):
            for item in data.get(group) or []:
                if isinstance(item, dict):
                    found.add(item.get("name") or "")
                    for alias in item.get("aliases") or []:
                        found.add(alias)
                elif isinstance(item, str):
                    found.add(item)
        _names = [normalise(name) for name in found
                  if name and len(name.strip()) >= 3]
    except Exception:  # noqa: BLE001 - without the list, only the other rules
        _names = []
    return _names


# How close a line has to be to a known name to be treated as the masthead
# rather than the headline. Compared whole-line, so a headline that merely
# mentions a paper is not thrown away - only a line that IS the name.
NAME_MATCH = 82
NAME_MAX_LENGTH = 46
# How much of a short line has to be made of those words before it is
# furniture. Four words out of five: a headline of five words that are all
# newspaper names does not exist.
NAME_WORD_SHARE = 0.8


def _is_name(text: str, starting: bool = True) -> bool:
    """Is this a paper's or a city's name? ``starting`` also counts a short
    line that merely begins with one - right for a whole reading, wrong for
    one line of a headline: "Chandigarh for over a month" is not a name."""
    body = normalise(text)
    if not body or len(body) > NAME_MAX_LENGTH:
        return False
    try:
        from rapidfuzz import fuzz
    except Exception:  # noqa: BLE001
        return False
    for name in _known_names():
        if fuzz.ratio(body, name) >= NAME_MATCH:
            return True
        if (starting and len(name) >= 6
                and fuzz.partial_ratio(name, body) >= 92
                and len(body) <= len(name) * 2):
            return True
    # "अमर उजाला नई दिल्ली" is the paper AND the city on one line - neither
    # match on its own, but between them they account for the whole line. A
    # short line built entirely out of words that only ever appear in
    # newspaper and city names is furniture, whichever way it is arranged.
    words = body.split()
    if 1 < len(words) <= 6:
        known = _name_words()
        covered = sum(1 for word in words if word in known)
        if covered / len(words) >= NAME_WORD_SHARE:
            return True
    return False


_words: set = set()


def _name_words() -> set:
    """Every word that appears in a paper's name or a city's."""
    global _words
    if not _words:
        _words = {word for name in _known_names() for word in name.split()
                  if len(word) >= 2}
    return _words


def _is_furniture(text: str) -> bool:
    """Is this line the paper's own name and date, rather than the headline?

    Divisions stamp their scans: a band across the top of the picture carrying
    the masthead, the city and the date - "अमर उजाला / नई दिल्ली / 08I09I2026".
    It is often set larger than the headline underneath it, so picking the
    tallest line lands on the masthead and the story's own words are never read.

    Worse, that band is the SAME on every cutting the division sends that day,
    so two entirely different stories both read as "पंजाब केसरी नई
    दिल्ली 06.09.2026" and match each other at 98 out of 100. That is not a
    near miss; it is the report silently dropping a story nobody looked at.
    """
    body = (text or "").strip()
    if not body:
        return True
    if DATED.search(body):
        return True
    if _is_name(body):
        return True
    letters = sum(1 for ch in body if ch.isalpha())
    digits = sum(1 for ch in body if ch.isdigit())
    return digits >= MASTHEAD_DIGITS and letters <= MASTHEAD_LETTERS


@dataclass
class Headline:
    """What was read off the top of a clipping."""

    text: str = ""
    confidence: int = 0
    engine: str = ""

    @property
    def usable(self) -> bool:
        """Enough to compare against another clipping.

        Both halves matter. A caption of four characters matches half the
        document by accident; and a low confidence means the shapes were not
        really recognised, which is how "पंजाब केसरी नई दिल्ली 06.09.2026" -
        the masthead, read at confidence 45 because there was no headline in
        the band at all - matched a completely different cutting from the same
        paper at 98 out of 100.
        """
        return (len(self.text) >= MIN_CHARACTERS
                and self.confidence >= MIN_CONFIDENCE
                and sum(1 for ch in self.text if ch.isalpha()) >= MIN_LETTERS)


MIN_CHARACTERS = 14
MIN_CONFIDENCE = 60
MIN_LETTERS = 10


_engine = None
_looked = False
# Why there is no engine, when there is none. A packaged build once shipped the
# engine's libraries but not the package that loads them, so the application
# reported "no engine" and did no duplicate checking at all while every other
# check passed. "No engine" is not a diagnosis; this is.
_trouble = ""


#: What the reader mistakes a 1 for inside a number - i, l, I, |, ! and
#: the Hindi full stops । and ॥ are all a single upright stroke - and what it
#: mistakes a 0 for.
_ONE_LIKE = "iIl|!\u0964\u0965"
_ZERO_LIKE = "oO"


def _fix_digits(text: str) -> str:
    """A 1 read as i inside a number is a 1: "i00" is 100, "॥2" is 12.

    Only where the stroke stands AGAINST a digit - in front of one, or
    between two. A full stop after a number ("2026।") is a full stop, and a
    word is left alone however many i's it has.
    """
    if not text or not any(ch.isdigit() for ch in text):
        return text
    chars = list(text)
    for at, ch in enumerate(chars):
        if ch not in _ONE_LIKE and ch not in _ZERO_LIKE:
            continue
        after = chars[at + 1] if at + 1 < len(chars) else ""
        before = chars[at - 1] if at else ""
        digit_after = after.isascii() and after.isdigit()
        digit_before = before.isascii() and before.isdigit()
        if ch in _ONE_LIKE and digit_after and not (before.isalpha()):
            chars[at] = "1"
        elif ch in _ZERO_LIKE and (digit_after or digit_before) and not (
                before.isalpha() and before not in _ZERO_LIKE):
            chars[at] = "0"
    return "".join(chars)


def normalise(text: str) -> str:
    """One spelling, so two readings of the same words compare equal.

    Composed form, because Devanagari has more than one way to write the same
    letter and OCR does not always pick the same one; folded case, which only
    affects the Latin half and does nothing to Devanagari; and single spaces,
    because line breaks in a headline are a matter of column width. And a 1
    read as an i inside a number is put back - see _fix_digits.
    """
    text = _fix_digits(unicodedata.normalize("NFC", text or ""))
    return " ".join(text.split()).lower()


def available() -> bool:
    """Is there an engine and language data to read with?"""
    return _open() is not None


def engine_name() -> str:
    api = _open()
    if api is None:
        return ""
    try:
        import tesserocr

        return f"tesseract {tesserocr.tesseract_version().split()[1]}"
    except Exception:  # noqa: BLE001
        return "tesseract"


def _open():
    """The engine, made once and kept.

    Building it reads the language data off disk, which is most of a second -
    paid once for a morning's import rather than once per clipping.
    """
    global _engine, _looked, _trouble
    if _looked:
        return _engine
    _looked = True
    try:
        import tesserocr

        if not TESSDATA.is_dir():
            _trouble = f"no language data at {TESSDATA}"
            _engine = None
            return None
        _engine = tesserocr.PyTessBaseAPI(path=str(TESSDATA), lang=LANGUAGES)
    except Exception as exc:  # noqa: BLE001 - no engine is a state, not a fault
        _trouble = f"{type(exc).__name__}: {exc}"
        _engine = None
    return _engine


def why_not() -> str:
    """What stopped the engine loading, if it did not load."""
    _open()
    return _trouble


def close() -> None:
    """Let the engine go. Only the tests need this."""
    global _engine, _looked
    if _engine is not None:
        try:
            _engine.End()
        except Exception:  # noqa: BLE001
            pass
    _engine, _looked, _trouble = None, False, ""


# How dark a row has to average before it counts as part of a stamped-on band,
# and how many ordinary rows have to follow before the band is judged over. The
# run matters: the band usually carries a white sticker or white lettering, and
# stopping at the first light row cuts off in the middle of it.
BAND_DARK = 110
BAND_LIGHT = 145
BAND_CLEAR_ROWS = 6
#: Never eat more than this much of the picture.
#:
#: It was 0.35, and the office sent in a pair it could not see past: the same
#: Rajasthan Patrika cutting twice, one copy stamped with a black band carrying
#: the paper, the city and the date. That band is 48.5% of the picture, so the
#: stripper gave up, the band stayed, and the two were never matched - the
#: reader read the stamp instead of the story ("" against the story's own
#: headline), and the prints measured 32 and 33 apart, on the very edge of both
#: gates.
#:
#: With it at 0.50 the band comes off and both copies read the story's own
#: headline, the prints fall to 18 and 20, and the pair is found. The six clear
#: rows the search still insists on are what keeps this honest: a dark
#: PHOTOGRAPH at the top of a cutting does not end in a clean light edge, and
#: what is left has to be a real cutting - see BAND_LEAVES.
#: A row this much black is band, whatever its average - see strip_band.
BAND_BLACK = 0.35
#: And a row of the cutting itself is never more than this much black.
BAND_PAPER = 0.18
BAND_LIMIT = 0.50
#: And what remains after a band is taken off is never less than this much of
#: the picture. A stamp is furniture above the cutting; if taking it would
#: leave less than half, it was not a stamp.
BAND_LEAVES = 0.45


def strip_band(image):
    """Cut a stamped-on masthead band off the top of the cutting.

    Several divisions stamp their scans with a solid black strip carrying the
    paper, the city and the date on separate lines. That strip is frequently
    set larger than the story's own headline, so measuring the tallest line
    reads "अमर उजाला" and the story below is never seen - and since the strip is
    identical on every cutting that division sends, two unrelated stories then
    read as the same words.

    Dropping single lines by their content is not enough on its own: the paper
    and the date sit on separate lines, so the date goes and the name stays.
    This removes the whole band before anything is read.
    """
    grey = image.convert("L")
    width, height = grey.size
    if width < 40 or height < 40:
        return image
    rows = grey.resize((1, height))          # one pixel per row: the row mean
    means = list(rows.getdata())
    # And how much of each row is black. A white LABEL inside the band - the
    # rounded "samachar post New Delhi / 15|09|2026" some divisions use -
    # lifts a row's average over the line that said "paper", and the band was
    # cut 59 pixels into 170, leaving the rest of the stamp on the cutting.
    # Half of such a row is still solid black; half of a row of print never is.
    black = [share / 255.0 for share in
             grey.point(lambda v: 255 if v < 70 else 0).resize(
                 (1, height), resample=4).getdata()]
    if not means or (means[0] > BAND_DARK and black[0] < BAND_BLACK):
        return image                          # nothing dark at the top

    cut, clear = 0, 0
    ceiling = int(height * BAND_LIMIT)
    for y in range(min(len(means), ceiling)):
        if means[y] >= BAND_LIGHT and black[y] < BAND_PAPER:
            clear += 1
            if clear >= BAND_CLEAR_ROWS:
                cut = y - BAND_CLEAR_ROWS + 1
                break
        else:
            clear = 0
    if cut <= 0:
        return image
    # What is left has to be a cutting, not a sliver.
    if (height - cut) < height * BAND_LEAVES:
        return image
    return image.crop((0, cut, width, height))


#: A DIVISION'S STAMP. Some divisions lay a black box - or a stack of them -
#: over the top of the cutting with the paper, the city, the date and the
#: page set in white on it: "THESE DAYS / NEW DELHI / 24-09-2026 / PG-9".
#: It is not a strip across the top, so strip_band never sees it, and the old
#: way read it as the headline - "pg-9", "these days", "lok satya". Each
#: number below is what tells such a box from the things that look like it.
STAMP_DARK = 80          # grey below which a pixel is the stamp's black
STAMP_WIDE = 0.06        # it is at least this share of the picture across
STAMP_TALL = 0.025       # and this share down
STAMP_TOP = 0.5          # it starts in the top half of the cutting
STAMP_FILL = 0.65        # its outline fills its box: stacked boxes 0.73
STAMP_BLACK = 0.45       # mostly black, with type on it...
STAMP_WHITE = 0.10       # ...white type: a night photograph has none
STAMP_TWO_TONE = 0.88    # and hardly any grey between: not a photograph
STAMP_LETTERS = 8        # white letters inside it. The nine stamps on the
                         # office's pages held 13 to 35; the loops inside a
                         # bold headline word - "स्वच्छ", which passed every
                         # other test - held 4.
STAMP_HOLE = 0.10        # none bigger than letter size: a black page with
                         # a white box of story on it is not a stamp
STAMP_CONVEX = 0.80      # a box's outline bulges nowhere: stamps 0.83-0.99,
                         # that word 0.72
STAMP_MARGIN = 0.9       # and the white type sits a letter's height inside
                         # the black: stamps 1.08-1.73, the word 0.68
STAMP_GREY = 40          # the black is black - a red kicker box is not
STAMP_SPECK = 12         # a white shape smaller than this is JPEG dust


def blank_stamps(image):
    """The cutting with any stamped black box painted out.

    Only boxes that pass every test above are touched, and only inside their
    own outline - nothing round them is changed. Without OpenCV the picture
    is handed back as it came.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image
    except Exception:  # noqa: BLE001 - no OpenCV, no stamps found
        return image
    try:
        rgb = np.asarray(image.convert("RGB"))
        grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        height, width = grey.shape
        dark = (grey < STAMP_DARK).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(dark, 8)
        out = None
        for i in range(1, count):
            x, y, w, h = (int(v) for v in stats[i][:4])
            if (w < STAMP_WIDE * width or h < STAMP_TALL * height
                    or y > STAMP_TOP * height):
                continue
            piece = (labels[y:y + h, x:x + w] == i).astype(np.uint8)
            outlines, _ = cv2.findContours(piece, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
            if not outlines:
                continue
            whole = np.zeros_like(piece)
            cv2.drawContours(whole, outlines, -1, 1, thickness=-1)
            inside = whole.astype(bool)
            area = int(inside.sum())
            if area < STAMP_FILL * w * h:
                continue
            levels = grey[y:y + h, x:x + w][inside]
            black = float((levels < STAMP_DARK).mean())
            white = float((levels > 175).mean())
            if (black < STAMP_BLACK or white < STAMP_WHITE
                    or black + white < STAMP_TWO_TONE):
                continue
            holes = (inside & (piece == 0)).astype(np.uint8)
            n, _, hole_stats, _ = cv2.connectedComponentsWithStats(holes, 8)
            sizes = hole_stats[1:, cv2.CC_STAT_AREA] if n > 1 else np.array([])
            letters = hole_stats[1:][sizes >= STAMP_SPECK] if n > 1 else []
            if (len(letters) < STAMP_LETTERS
                    or float(sizes.max()) > STAMP_HOLE * area):
                continue
            hull = cv2.convexHull(max(outlines, key=cv2.contourArea))
            if area < STAMP_CONVEX * max(1.0, cv2.contourArea(hull)):
                continue
            letter = float(np.median(letters[:, 3]))
            inset = min(int(letters[:, 0].min()),
                        w - int((letters[:, 0] + letters[:, 2]).max()))
            if inset < STAMP_MARGIN * letter:
                continue
            ink = rgb[y:y + h, x:x + w][inside & (piece == 1)].astype(int)
            if len(ink) and float((ink.max(axis=1) - ink.min(axis=1)).mean()) > STAMP_GREY:
                continue
            if out is None:
                out = rgb.copy()
            grown = cv2.dilate(whole, np.ones((5, 5), np.uint8)).astype(bool)
            out[y:y + h, x:x + w][grown] = 255
        if out is None:
            return image
        return Image.fromarray(out)
    except Exception:  # noqa: BLE001 - a picture the check cannot look at
        return image


def ready_to_read(image):
    """The cutting as the headline is looked for on it: the division's
    stamped strip cut away, and any stamped box painted out.

    NOT TRIMMED OF ITS WHITE EDGES. That was tried on the office's report
    pages - cuttings on white A4 - and measured: the finder looks at every
    picture at one working width, so trimming moved the scale, and a scale
    change flips the close calls both ways. 39 pages read better and 23
    worse, most of those a word lost; of the office's own cuttings, which
    have next to no margin, it changed one. The finder already passes over
    blank paper, so the white is left where it is.
    """
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    return blank_stamps(strip_band(image))


def band_text(image) -> str:
    """Every word on one strip of a picture, read as a single block.

    For the band a burned report draws its headline onto (export/build_burned,
    found again by core/reportrecord.recover_bands). It is not a page: it is one
    line of this program's own type on white, so the reader is told to read a
    block rather than go looking for a layout - a wide strip with a short
    centred title on it is exactly the shape that makes layout analysis invent
    columns. The mode is put back afterwards because this engine is shared with
    the duplicate check, which reads whole cuttings and wants the layout found.

    Nothing is scaled or trimmed first. Measured on the one burned report that
    exists: ten bands of ten came back exactly as they were drawn, in Hindi and
    in English, whether the strip was read at its own size or at half, so it is
    read as it is and the picture is left alone.

    What comes back goes through the same invisible-character table a caption
    read off a page does. The reader puts a zero-width joiner inside a
    Devanagari word often enough to matter: three Hindi titles burned at every
    heading size the panel offers came back with one in 5 of the 12 readings,
    at 12, 18, 24 and 28 point alike. A name off a band goes into caption_raw
    and from there onto the department's own newspaper list, and a name with a
    character in it that nobody can see is a name that never matches again. All
    12 read right once the table has been through them.
    """
    api = _open()
    if api is None or image is None:
        return ""
    try:
        import tesserocr

        from .assemble import _tidy

        before = api.GetPageSegMode()
        api.SetPageSegMode(tesserocr.PSM.SINGLE_BLOCK)
        try:
            api.SetImage(image)
            return " ".join(_tidy(api.GetUTF8Text()).split())
        finally:
            api.SetPageSegMode(before)
    except Exception:  # noqa: BLE001 - never let OCR break an import
        return ""


def build_engines(count: int) -> list:
    """Make several readers, for reading several clippings at once.

    MUST be called from the main thread. tesserocr installs a signal handler
    while it starts up and Python only permits that on the main thread; from a
    worker it raises "signal only works in main thread of the main
    interpreter". Building them here and handing them to a worker is fine -
    only the making is restricted.
    """
    made = []
    try:
        import tesserocr

        if not TESSDATA.is_dir():
            return []
        for _ in range(max(1, count)):
            made.append(tesserocr.PyTessBaseAPI(path=str(TESSDATA),
                                                lang=LANGUAGES))
    except Exception:  # noqa: BLE001 - fall back to the one shared reader
        pass
    return made


def close_engines(engines) -> None:
    for api in engines or ():
        try:
            api.End()
        except Exception:  # noqa: BLE001
            pass


#: How many of the finder's candidates are ever read. The best one, nearly
#: always; the next only when the best reads as nothing, or as a paper's name
#: or a date rather than a story.
CANDIDATES_READ = 3

#: Words a newspaper's nameplate carries and a headline almost never does -
#: "daily", "published from", edition, price, page, year and issue. TWO of
#: them make a nameplate; one alone does not, or a story about a book being
#: published would be thrown away.
NAMEPLATE_WORDS = ("दैनिक", "प्रकाशित", "संस्करण", "मूल्य", "पृष्ठ", "वर्ष",
                   "अंक", "daily", "edition", "price", "pages", "rs.")


def _nameplate(text: str) -> bool:
    """Does this read as a paper's nameplate rather than a story?"""
    folded = (text or "").casefold()
    return sum(1 for word in NAMEPLATE_WORDS if word in folded) >= 2


def two_stage(api, image):
    """Find the headline by looking, then read only that. (finding, reading)

    1. The part of the picture that is not the article goes first - the
       division's stamped strip with the paper, the city and the date.
    2. OpenCV finds where the headline is: the bold type that sits on the
       article, not the office's label above a gap, not the paper's name, not
       a photograph. Nothing is read to find it.
    3. Only that region is read.

    ``finding`` is None when there is no OpenCV, or nothing on the picture
    that looks like a headline; the caller then reads the old way.
    """
    from . import headfind

    if api is None or image is None or not headfind.available():
        return None, Headline()
    try:
        image = ready_to_read(image)
        finding = headfind.find(image)
    except Exception:  # noqa: BLE001 - a picture the finder cannot look at
        return None, Headline()
    if not finding.candidates:
        return None, Headline()
    def story(found) -> bool:
        letters = sum(1 for ch in found.text if ch.isalpha())
        return bool(found.text and letters >= 4
                    and not _label_like(found.text)
                    and not _SENTENCES.search(found.text))

    for region in finding.candidates[:CANDIDATES_READ]:
        found, bare = _read_region(api, image, region)
        if story(found) and not _repeats_label(api, image, finding, found.text):
            finding.chosen = region
            return finding, found
        # A LABEL SET ON TOP OF THE HEADLINE. The office types its own
        # "हिंदुस्तान वाराणसी 06-09-26 page-8" straight above the story, at
        # nearly the headline's size and with no gap, and the two were found
        # as one two-line headline - whose date then, rightly, made the whole
        # of it read as furniture. Read such a block a line at a time and keep
        # every line that is a story.
        kept = [line for line in (read_region(api, image, part)
                                  for part in getattr(region, "lines", ()))
                if story(line)]
        if kept:
            finding.chosen = region
            words = normalise(" ".join(line.text for line in kept))
            confidence = int(sum(line.confidence for line in kept) / len(kept))
            return finding, Headline(words, confidence, kept[0].engine)
        # ONE BLOCK THAT CANNOT BE READ A LINE AT A TIME, with the label in
        # it - "State Vision, Page 1" over "Temporary augmentation of coach".
        # Its label lines are dropped, and what is left is taken only when it
        # reads cleanly: dropping them from a block of scraps let a column of
        # junk with the headline's tail in it beat the headline itself.
        if (not getattr(region, "lines", ()) and bare and bare != found.text
                and found.confidence >= POOR_READING and not _scrappy(bare)):
            trimmed = Headline(bare, found.confidence, found.engine)
            if story(trimmed):
                finding.chosen = region
                return finding, trimmed
    return finding, Headline()


def headline_with(api, data: bytes) -> Headline:
    """The headline, read with a reader of the caller's own.

    Same work as :func:`headline`, but against an engine that belongs to one
    thread, so several clippings can be read at once without them treading on
    each other.

    TWO STAGES FIRST - see two_stage - and when they read cleanly and are
    sure, that is the answer and nothing else runs: seven clippings in ten.

    The old way below reads a fixed slice of the top of the picture and keeps
    its tallest line, which is how a photograph, the office's label and a
    paper's nameplate were read as headlines. It is asked only for a SECOND
    OPINION, when the two stages found no headline or read one they were not
    sure of, and the cleaner of the two readings is kept. Measured on 336 of
    the office's cuttings: 41 read as gibberish the old way alone, 29 by two
    stages alone, and 15 this way; 5, 36 and 4 read as nothing.
    """
    if api is None or not data:
        return Headline()
    found = Headline()
    finding, picture = None, None
    try:
        from PIL import Image

        picture = Image.open(io.BytesIO(data))
        picture.load()
        finding, found = two_stage(api, picture)
        if found.text and found.confidence >= SURE and not _scrappy(found.text):
            return Headline(found.text, found.confidence, stamp())
    except Exception:  # noqa: BLE001 - the old way still stands
        found = Headline()
    old = _old_way(api, data)
    # THE SECOND OPINION MAY NOT BRING BACK WHAT THE FINDER THREW OUT. The old
    # way reads the biggest line at the top of the picture - which, on a
    # cutting the office has labelled, IS the label. The finder had rejected
    # "जनसंदेश टाइम्स लखनऊ / 15-09-26 Page- 3" as sitting above the article,
    # read the headline under it at 80, and the old way's 95 for the label
    # won the comparison. So the old reading is refused when it reads like a
    # label, or when it is the words of a block the finder rejected -
    # but that second only while the finder's own reading is sound. A
    # headline over a photograph sits above a gap too: on two of the
    # office's cuttings the finder turned the real headline away, read "nes
    # gies)" at 32 and "glege" at 17 instead, and the old way's reading of
    # the headline is then the one to keep, not to refuse.
    finder_sound = (found.text and found.confidence >= POOR_READING
                    and not _scrappy(found.text))
    short = len(old.text.split()) <= LABEL_WORDS
    if old.text and (_label_like(old.text)
                     or ((finder_sound or short) and _is_rejected_header(
                         api, picture, finding, old.text))):
        old = Headline()
    chosen = _cleaner(found, old)
    return Headline(chosen.text, chosen.confidence, stamp())


#: A page number, "my city", or a date in figures: the office's label, or a
#: paper's own furniture - never the words of a story's headline. The page
#: number as the report pages print it too - "Pg 7", "pg.03", "PG-9", "Page
#: No. 3", and "page i]" where the reader took a 1 for an i.
_LABELISH = re.compile(
    r"(?<![a-z])(page|pg|\u092a\u0947\u091c|\u092a\u0943\u0937\u094d\u0920)"
    r"\s*(no\.?)?\s*[-\u2013:.]?\s*[\dil|!\]]{1,3}(?![a-z])"
    r"|my\s*city"
    r"|(?<![a-z])edition\s*:"
    r"|(?<![a-z])(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
    r"\s*\d{1,2},?\s*\d{4}"
    r"|\d{1,2}\s*[-./|\u0964]\s*\d{1,2}\s*[-./|\u0964]\s*\d{2,4}",
    re.IGNORECASE)

#: THE FURNITURE OF A POST AND OF A FORWARDED LINK. A Facebook or X post is
#: headed by the account and the time - "Northern Railway 11 hours ago" -
#: and that, the tallest clean line on the picture, was read as the post's
#: headline on eleven of the sixteen posts in the office's report. A link
#: forwarded on WhatsApp brings "पूरा समाचार पढ़ने के लिए नीचे दिए लिंक पर
#: क्लिक करें" with it, and a news app's card "ऐप इनस्टॉल करें". None of it
#: is ever a story's words.
_POST_FURNITURE = re.compile(
    r"\b(hours?|hrs?|mins?|minutes?|days?|weeks?)\s+ago\b"
    r"|northernrailway"
    r"|see\s+translation|translated\s+from|for\s+news\s+on\s+the\s+go"
    r"|\u0915\u094d\u0932\u093f\u0915\s+\u0915\u0930\u0947\u0902"          # क्लिक करें
    r"|\u0932\u093f\u0902\u0915\s+\u092a\u0930"                              # लिंक पर
    r"|\u092a\u0942\u0930\u093e\s+\u0938\u092e\u093e\u091a\u093e\u0930"      # पूरा समाचार
    r"|\u0928\u0940\u091a\u0947\s+\u0926\u093f\u090f"                        # नीचे दिए
    r"|\u0907\u0928\u0938\u094d\u091f\u0949\u0932\s+\u0915\u0930\u0947\u0902"  # इनस्टॉल करें
    r"|\u0907\u0902\u0938\u094d\u091f\u0949\u0932\s+\u0915\u0930\u0947\u0902", # इंस्टॉल करें
    re.IGNORECASE)

#: The words of a platform's name and an account's, which a post's header is
#: built of. A reading made of nothing else - "Facebook:", "SOCIAL MEDIA",
#: "Northern Railway @" - is the header; one with a story in it is not.
_PLATFORM_WORDS = frozenset((
    "facebook", "twitter", "instagram", "youtube", "whatsapp", "threads",
    "linkedin", "koo", "x", "social", "media", "electronic", "northern",
    "northem", "railway", "railways", "india"))


def _platform_only(body: str) -> bool:
    """A few words, every one of them a platform's or the account's."""
    words = re.findall(r"[^\W\d_]+", body.casefold())
    return bool(words) and len(words) <= 4 and all(
        word in _PLATFORM_WORDS for word in words)


def _label_like(text: str) -> bool:
    """Does a reading look like the office's label rather than a headline?"""
    body = text or ""
    return bool(_is_furniture(body) or _nameplate(body)
                or _LABELISH.search(body) or _POST_FURNITURE.search(body)
                or _platform_only(body))


#: A web address is never a headline's words either: "... का डीआरएम ने
#: लिया जायजा https://dhunt.in/75s" is the headline and the link it came with.
_ADDRESS = re.compile(r"(https?://|www\.)\S*", re.IGNORECASE)


def _without_labels(text: str) -> str:
    """A reading's lines without the label lines at its top and foot.

    The finder's region, or the old way's band, sometimes takes in the line
    above the headline - "Amar Ujala, Jalandhar, Page 12" - or the account a
    post came from. Such a line is dropped when a line of story is left; a
    reading that is ALL label is handed back whole, for the caller to refuse.
    """
    lines = [_ADDRESS.sub("", line).strip() for line in (text or "").splitlines()]
    lines = [line for line in lines if line]
    while len(lines) > 1 and _label_line(lines[0]):
        lines.pop(0)
    while len(lines) > 1 and _label_line(lines[-1]):
        lines.pop()
    return "\n".join(lines)


def _label_line(line: str) -> bool:
    """One line of a reading that is label, not story. As _label_like, but a
    name must be the WHOLE line - see _is_name."""
    body = normalise(line)
    if not body:
        return True
    return bool(DATED.search(body) or _is_name(body, starting=False)
                or _nameplate(body) or _LABELISH.search(body)
                or _POST_FURNITURE.search(body) or _platform_only(body))


def _is_rejected_header(api, picture, finding, words: str) -> bool:
    """Are these words those of a block the finder rejected as not the story?

    Only the blocks turned away for their PLACE - above the article past a
    gap, beside it, below it - which is where labels and nameplates are. Each
    is read (they are few, and small) and compared loosely: the old way reads
    the label's first line, the block holds the whole label.
    """
    if picture is None or finding is None or not words:
        return False
    try:
        from rapidfuzz import fuzz

        mine = normalise(words)
        return any(fuzz.partial_ratio(mine, theirs) >= 75
                   for theirs in _placed_words(api, picture, finding))
    except Exception:  # noqa: BLE001 - when in doubt, the old way may speak
        return False


def _placed_words(api, picture, finding, seen=None) -> list:
    """The readings of the blocks the finder turned away for their PLACE.

    Read once per picture and kept on the finding: both readers are held up
    against them. ``seen`` is the picture as the finder looked at it, when
    the caller has it already.
    """
    kept = finding.placed_words
    if kept is not None:
        return kept
    kept = []
    if seen is None:
        seen = ready_to_read(picture)
    for region in getattr(finding, "rejected", ()):
        if region.note.startswith(("above a gap", "beside the article",
                                   "below the article")):
            theirs = _read_region(api, seen, region)[0].text
            if theirs:
                kept.append(theirs)
    finding.placed_words = kept
    return kept


#: A reading this short that repeats a turned-away label is that label again:
#: the paper's name, as the label printed it and as the paper's own masthead
#: repeats it under the label.
LABEL_WORDS = 3


def _repeats_label(api, image, finding, words: str) -> bool:
    """Is this short reading the words of a label the finder turned away?"""
    if not words or len(words.split()) > LABEL_WORDS + 2:
        return False
    try:
        from rapidfuzz import fuzz

        mine = normalise(words)
        return any(len(theirs.split()) <= LABEL_WORDS + 3
                   and fuzz.partial_ratio(mine, theirs) >= 75
                   for theirs in _placed_words(api, None, finding, seen=image))
    except Exception:  # noqa: BLE001
        return False


#: Two stages this sure, reading this cleanly, need no second opinion.
SURE = 80


def _scrappy(text: str) -> bool:
    """Does a reading look like scraps rather than a sentence?

    Latin fragments in the middle of Hindi ("रेल ब्लाक: करनाल की 2 cal के"),
    stray symbols, or hardly any letters at all - what a reading of the wrong
    region, or of a photograph, looks like.
    """
    body = text or ""
    letters = sum(1 for ch in body if ch.isalpha() or "\u0900" <= ch <= "\u097f")
    if letters < 6:
        return True
    devanagari = sum(1 for ch in body if "\u0900" <= ch <= "\u097f")
    latin_words = [w for w in body.split()
                   if any(ch.isascii() and ch.isalpha() for ch in w)]
    if devanagari >= 10 and len(latin_words) >= 2:
        return True
    odd = sum(1 for ch in body
              if not (ch.isalnum() or ch.isspace() or "\u0900" <= ch <= "\u097f"
                      or ch in ",.:;-'\"!?()|%/&\u2018\u2019\u201c\u201d\u2013\u2014"))
    return odd >= 3


def _cleaner(two: Headline, old: Headline) -> Headline:
    """Of two readings of one picture, the one that reads as a sentence.

    Clean beats scrappy; then the surer one wins, with the two stages given a
    small start - their region is the headline by construction, the old way's
    is only the top of the picture.
    """
    if _fuller(two, old) or _outweighs(two, old) or _paragraph_against(two, old):
        return two
    candidates = [(not _scrappy(h.text), h.confidence + bonus, n, h)
                  for n, (h, bonus) in enumerate(((two, 3), (old, 0)))
                  if h.text]
    if not candidates:
        return two if two.text else old
    return max(candidates, key=lambda c: (c[0], c[1], -c[2]))[3]


#: How much of the old way's reading must be found inside the two stages'
#: for the two to be one headline read twice.
SAME_WORDS = 90
#: And how much longer the two stages' reading has to be to count as more.
FULLER = 1.2


def _fuller(two: Headline, old: Headline) -> bool:
    """Did the two stages read the SAME headline as the old way, and more of it?

    The old way reads lines one at a time and keeps a block of them; on a
    headline in two lines of slightly different sizes it kept the first -
    "दीवाली से पहले कई" at 96, where the two stages had "दीवाली से पहले कई
    ट्रेनोंमें जगह नहीं" at 76 - and the surer one won. A reading that holds
    the other one whole, reads cleanly and says more is the better reading of
    the same words, however sure the shorter one is.
    """
    if not two.text or not old.text or _scrappy(two.text):
        return False
    try:
        from rapidfuzz import fuzz
    except Exception:  # noqa: BLE001
        return False
    letters = lambda text: sum(1 for ch in text if ch.isalpha())  # noqa: E731
    if letters(two.text) < FULLER * letters(old.text):
        return False
    return fuzz.partial_ratio(normalise(old.text), normalise(two.text)) >= SAME_WORDS


def _outweighs(two: Headline, old: Headline) -> bool:
    """A headline read with some noise, against a scrap that is not in it.

    On a cutting taken off a paper's e-paper, the page's own header sits over
    it - "Ferozpur Kesari / Sep 25, 2026" - and the old way read that, garbled,
    as "see rozpur kesari" or "ao) kesari": short, and clean enough to beat
    two stages that had read the whole headline with a stray word or two in
    it. A reading of three words or fewer that shares nothing with a sure
    reading of six or more is a scrap of something else on the picture.
    """
    if not two.text or not old.text or two.confidence < POOR_READING:
        return False
    if len(old.text.split()) > 3 or len(two.text.split()) < 6:
        return False
    try:
        from rapidfuzz import fuzz
    except Exception:  # noqa: BLE001
        return False
    return fuzz.partial_ratio(normalise(old.text), normalise(two.text)) < 50


#: A reading with a Hindi full stop inside it, words after it, is sentences:
#: body text, a byline, a dateline's "लखनऊ।". A headline has none. (Not the
#: English full stop: "4.0", "v.s." and "Rs." are all inside headlines.) Nor
#: does a headline run to this many words.
_SENTENCES = re.compile(r"[\u0964]\s*\S")
PARAGRAPH_WORDS = 40


def _paragraph_against(two: Headline, old: Headline) -> bool:
    """The old way read a paragraph; the two stages read a headline, roughly.

    With the label taken out of the old way's reach, its tallest remaining
    lines were sometimes the body - "उपयोग करें। कार्यक्रम में ठोस उपयोग और
    उनके महत्व के ..." at 87 - and a clean paragraph beat the two stages'
    rough but right "रेशवे स्टेशन ue te गया ... जागरुकता अभियान" at 65. Body
    text is never the headline, however cleanly it reads.
    """
    if not two.text or not old.text or two.confidence < POOR_READING:
        return False
    if len(two.text.split()) < 3:
        return False
    return bool(_SENTENCES.search(old.text)
                or len(old.text.split()) > PARAGRAPH_WORDS)


def _old_way(api, data: bytes) -> Headline:
    """The reading as it was before the two stages: slices of the top."""
    found = _read_band(api, data, TOP_BAND)
    if not found.text:
        found = _read_band(api, data, DEEPER_BAND)
    if not found.text:
        # THE WHOLE PICTURE, AS A LAST RESORT. The two bands above are the top
        # of the cutting, which is where a headline is - but not always: a
        # cutting turned on its side, one whose headline sits beside the
        # photograph rather than over it, or a page furniture strip with the
        # words down at the foot, all come back empty from both. Reading the
        # whole thing is slower and gives a worse headline, so it is only ever
        # asked after the other two have said nothing at all.
        found = _read_band(api, data, 1.0)
    if found.text and found.confidence >= POOR_READING:
        return found
    # AND THE OTHER THREE WAYS UP. A photograph taken on a phone arrives
    # sideways and a scan is sometimes fed in upside down; read as it lies,
    # either gives nothing or gives nonsense, which is the "nothing is read on
    # a picture I can read perfectly well" the office saw.
    #
    # Only from here, and only ever to REPLACE nothing: a picture that already
    # read well never reaches this line, so a good reading can never be
    # swapped for a worse one. Measured, the right way up wins every time -
    # 96 against 0, 26, 39 and 75 on the office's own cuttings - but the rule
    # is "better than what we have", not "best of four", so the cost of being
    # wrong is a reading where there was none.
    best = found
    for turn in _TURNS:
        try:
            other = _read_band(api, _turned(data, turn), TOP_BAND)
        except Exception:  # noqa: BLE001 - one way up that will not read
            continue
        if other.text and other.confidence >= best.confidence + CLEARLY_BETTER:
            best = other
    return best


#: The three other ways up, as PIL names them.
_TURNS = (90, 180, 270)


def _turned(data: bytes, degrees: int) -> bytes:
    """The same picture, turned. Used only to rescue one that read as nothing."""
    from PIL import Image

    image = Image.open(io.BytesIO(data))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    out = io.BytesIO()
    image.rotate(degrees, expand=True).save(out, "PNG")
    return out.getvalue()


def _prepare(data: bytes, portion: float = TOP_BAND):
    """The band of picture the headline is in, at a size worth reading."""
    from PIL import Image

    image = ready_to_read(Image.open(io.BytesIO(data)))
    band = (image if portion >= 1.0 else
            image.crop((0, 0, image.width,
                        max(60, int(image.height * portion)))))
    # A NARROW PICTURE IS ENLARGED, NOT REFUSED. This used to hand back None
    # below 240 across, and a clipping cut narrow - one column of a page, a
    # single-column brief - was then never read at all, which is the "nothing
    # is read" on a picture anybody can read with their eyes. Tesseract wants
    # about 1200 across whatever it started at, and enlarging is exactly what
    # the line below already does for everything else; there was no reason for
    # a floor beyond it. Under about 40 across there is nothing to enlarge, so
    # that is where it now stops.
    if band.width < TINY_WIDTH or band.height < TINY_WIDTH // 4:
        return None
    scale = TARGET_WIDTH / band.width
    if abs(scale - 1.0) > 0.05:
        band = band.resize((max(1, int(band.width * scale)),
                            max(1, int(band.height * scale))), Image.LANCZOS)
    return band


#: What ocr_engine says when the reading was typed rather than read. The
#: field names which reader produced the words, and a person is one of them -
#: which is what keeps a typed correction from being read over on the next
#: check, and from being thrown out with the measurements.
BY_HAND = "hand"

#: Every reading made since the headline has been FOUND before it is read
#: carries this on its engine stamp. One without it was made by the old way -
#: a slice off the top, the biggest line kept - and is read again: that is how
#: the office's label, a paper's nameplate or a photograph stayed as a
#: clipping's "headline" long after the reader stopped making that mistake.
#:
#: The number is the reader's generation, raised when it has learned enough
#: that what it read before should be read again - once, at the next
#: duplicate check. " +found" was 2.0.52 to 2.0.55; " +found2" is 2.0.56,
#: which learned the divisions' stamps, labels, post headers and dates with
#: figures in them from the office's own report pages. A reading typed, or
#: read with the OCR box, is the person's (BY_HAND) and is never read again.
FOUND_FIRST = " +found2"


def stamp() -> str:
    """What a reading made now is stamped with."""
    return f"{engine_name() or 'tesseract'}{FOUND_FIRST}"


def current(engine: str) -> bool:
    """Is a reading stamped like this one to keep?

    Typed ones always; read ones only if the headline finder made them.
    """
    engine = str(engine or "")
    return engine == BY_HAND or engine.endswith(FOUND_FIRST)


def headline(data: bytes) -> Headline:
    """The headline printed on this clipping, or an empty reading.

    Never raises. A clipping that cannot be read is not an error - it is a
    clipping that will not take part in duplicate matching, which is the right
    outcome and the one the user asked for.
    """
    api = _open()
    if api is None or not data:
        return Headline()
    # ONE PATH, headline_with's. This used to carry its own copy of the
    # two-band search, so anything added to headline_with - the whole-picture
    # last resort, the other three ways up - was never reached by the reading
    # the program actually does, which goes through here.
    return headline_with(api, data)


def _read_band(api, data: bytes, portion: float) -> Headline:
    try:
        import tesserocr

        band = _prepare(data, portion)
        if band is None:
            return Headline()
        api.SetImage(band)
        api.Recognize()
        walk = api.GetIterator()
        if walk is None:
            return Headline()

        level = tesserocr.RIL.TEXTLINE
        lines = []
        while True:
            try:
                box = walk.BoundingBox(level)
                text = walk.GetUTF8Text(level)
                confidence = walk.Confidence(level)
            except Exception:  # noqa: BLE001 - a line that will not read
                box, text, confidence = None, "", 0.0
            text = _ADDRESS.sub("", text or "").strip()
            if box and text:
                lines.append((box[1], box[3] - box[1], text, confidence))
            if not walk.Next(level):
                break
        if not lines:
            return Headline()

        # The masthead band goes first, before anything is measured. It is
        # frequently the biggest type on the cutting, so leaving it in and
        # picking the tallest line reads the paper's name instead of the story.
        lines = [row for row in lines if not _label_like(row[2])]
        if not lines:
            return Headline()

        kept = _headline_block(lines)
        if not kept:
            return Headline()
        found = normalise(" ".join(text for _top, text, _conf in kept))
        confidence = int(sum(conf for _t, _x, conf in kept) / max(1, len(kept)))
        return Headline(found, confidence, engine_name())
    except Exception:  # noqa: BLE001 - never let OCR break an import
        return Headline()


#: The headline's letters are brought to about this height before they are
#: read. Tesseract's models are happiest with type a few dozen pixels tall;
#: a headline found at 18 px on a phone capture reads as guesswork, and one
#: at 140 px on a scan reads slowly for nothing.
READ_TYPE_HEIGHT = 56


def read_box(data: bytes, box: tuple, api=None) -> Headline:
    """The words inside one box somebody drew over a picture.

    The preview's OCR box: the person has put it round the headline, so there
    is nothing to find - only the size of the type inside it, which is what
    the reading is scaled by, and that is measured, not guessed.
    """
    api = api if api is not None else _open()
    if api is None or not data:
        return Headline()
    try:
        from PIL import Image

        from . import headfind

        picture = Image.open(io.BytesIO(data))
        picture.load()
        if picture.mode not in ("RGB", "L"):
            picture = picture.convert("RGB")
        left, top, right, bottom = (int(v) for v in box)
        left, top = max(0, left), max(0, top)
        right = min(picture.width, max(left + 1, right))
        bottom = min(picture.height, max(top + 1, bottom))
        # THE FINDER'S HEADLINE LINES THAT FALL INSIDE THE BOX. A box laid
        # over a headline in a column takes in slivers of the columns either
        # side and half a line above - "ttar", "ress", "AS", "outcome." - and
        # read as it stood that came back as ".,, nr extends periodicity |]
        # aes of special trains". Looking at the WHOLE picture, the finder
        # knows exactly which ink is the headline's - it has the body text to
        # measure it against, which a box that is nearly all headline does
        # not - so the lines it found inside the box are read, each cleared
        # of everything that is not on it, and nothing else.
        if headfind.available():
            finding = headfind.find(picture)
            def within(blocks):
                kept = []
                for r in blocks:
                    x0, y0 = max(r.left, left), max(r.top, top)
                    x1, y1 = min(r.right, right), min(r.bottom, bottom)
                    if x1 <= x0 or y1 <= y0:
                        continue
                    if (x1 - x0) * (y1 - y0) >= 0.35 * max(1, r.width * r.height):
                        parts = []
                        for part in getattr(r, "lines", ()) or ():
                            px0, py0 = max(part.left, left), max(part.top, top)
                            px1 = min(part.right, right)
                            py1 = min(part.bottom, bottom)
                            if px1 > px0 and py1 > py0:
                                parts.append(headfind.Region(
                                    px0, py0, px1, py1,
                                    type_height=part.type_height,
                                    core=part.core))
                        kept.append(headfind.Region(
                            x0, y0, x1, y1, type_height=r.type_height,
                            core=r.core, lines=tuple(parts)))
                return kept

            # The headlines it accepted, first. Large type it turned away -
            # a label, a strip across a picture - is read only when the box
            # holds nothing else, so that a sloppy box over a real headline
            # does not drag a coloured kicker strip into it as noise.
            inside = within(finding.candidates) or within(
                [r for r in finding.rejected
                 if not r.note.startswith(("a lone mark", "inside a picture"))])
            texts, sure = [], []
            for r in sorted(inside, key=lambda r: (r.top, r.left)):
                found = read_region(api, picture, r)
                if found.text and (_is_furniture(found.text)
                                   or _nameplate(found.text)) and r.lines:
                    # The office's label typed on top of the headline, found
                    # with it as one block: a line at a time, keeping the story.
                    for part in r.lines:
                        line = read_region(api, picture, part)
                        if (line.text and not _is_furniture(line.text)
                                and not _nameplate(line.text)):
                            texts.append(line.text)
                            sure.append(line.confidence)
                    continue
                if found.text:
                    texts.append(found.text)
                    sure.append(found.confidence)
            if texts:
                return Headline(normalise(" ".join(texts)),
                                int(sum(sure) / len(sure)), engine_name())
        # Framed round something the finder does not take for a headline:
        # read what the box holds, less what its edges cut through.
        crop = picture.crop((left, top, right, bottom))
        crop, size = _clear_box_edges(crop)
        region = headfind.Region(0, 0, crop.width, crop.height,
                                 type_height=size or crop.height / 2.5)
        return read_region(api, crop, region)
    except Exception:  # noqa: BLE001 - a box that will not read reads empty
        return Headline()


def _clear_box_edges(crop):
    """White out what a drawn box's edges cut through. (picture, type size)

    The type the box is mostly of is measured - the letter height that
    covers the most width - and then three kinds of ink go:

      * anything cut by the left or right edge that is smaller than that
        type: the next column's words, of which the box caught a sliver;
      * anything cut by the top or bottom edge that is smaller than it: the
        line above or below, of which the box caught the bottom or the top;
      * a tall thin stroke the height of the box: a column rule.

    Ink of the headline's own size that the edge happens to clip is kept - a
    box drawn a little tight should still read its first and last letters.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        gray = np.asarray(crop.convert("L")).copy()
        height, width = gray.shape[:2]
        if width < 12 or height < 8:
            return crop, 0.0
        if float((gray > 150).mean()) < 0.3:
            gray = 255 - gray                  # white type on a dark strip
        _, ink = cv2.threshold(gray, 0, 255,
                               cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
        pieces = [tuple(int(v) for v in stats[i][:4]) + (i,)
                  for i in range(1, count) if stats[i][4] >= 6]
        if not pieces:
            return crop, 0.0
        # The type the box is mostly of: the height covering the most width.
        weights = {}
        for _x, _y, w, h, _i in pieces:
            if h >= 6:
                bucket = int(h // 3) * 3
                weights[bucket] = weights.get(bucket, 0) + w
        size = float(max(weights, key=weights.get) + 1.5) if weights else 0.0
        for x, y, w, h, i in pieces:
            at_side = x <= 1 or x + w >= width - 1
            at_end = y <= 1 or y + h >= height - 1
            rule = h >= 0.8 * height and w <= max(3, 0.12 * h)
            cut = (at_side or at_end) and size and h < 0.8 * size
            if rule or cut:
                gray[labels == i] = 255
        return Image.fromarray(gray), size
    except Exception:  # noqa: BLE001 - a box left as it was still reads
        return crop, 0.0


def _clear_edges(crop, region):
    """White out ink in the box that is not on the headline's own lines.

    The box is padded so the tops and tails of the headline's letters are not
    cut off - and the padding takes in the bottom half of the line above it,
    the top of a byline or a photograph below, and sometimes the first letter
    of the next column. Half-letters read as nonsense, and the nonsense went
    into the middle of an otherwise good reading. So anything whose CENTRE is
    off the headline's lines goes; the headline's own vowel signs and dots
    have their centres on it, and stay.
    """
    core = getattr(region, "core", ()) or ()
    if len(core) != 4:
        return crop
    try:
        import cv2
        import numpy as np
        from PIL import Image

        gray = np.asarray(crop).copy()
        _, ink = cv2.threshold(gray, 0, 255,
                               cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        count, labels, stats, centres = cv2.connectedComponentsWithStats(ink, 8)
        size = max(1.0, float(region.type_height or 0))
        top = core[1] - region.top - 0.15 * size
        bottom = core[3] - region.top + 0.15 * size
        left = core[0] - region.left - 0.1 * size
        right = core[2] - region.left + 0.1 * size
        for i in range(1, count):
            cx, cy = centres[i]
            if not (top <= cy <= bottom and left <= cx <= right):
                gray[labels == i] = 255
        return Image.fromarray(gray)
    except Exception:  # noqa: BLE001 - a crop left as it was still reads
        return crop


_digits_api = None
_digits_tried = False


def _digits_engine():
    """A second reader that knows only English digits - see _numbers_again.

    Made once, and only where making one is allowed: on a program's main
    thread, which in a helper process is where every reading happens.
    """
    global _digits_api, _digits_tried
    if _digits_tried:
        return _digits_api
    import threading

    if threading.current_thread() is not threading.main_thread():
        return None
    _digits_tried = True
    try:
        import tesserocr

        if (TESSDATA / "eng.traineddata").is_file():
            engine = tesserocr.PyTessBaseAPI(path=str(TESSDATA), lang="eng")
            engine.SetVariable("tessedit_char_whitelist", "0123456789.,:-/")
            engine.SetPageSegMode(tesserocr.PSM.SINGLE_LINE)
            _digits_api = engine
    except Exception:  # noqa: BLE001 - without it, numbers read as they read
        _digits_api = None
    return _digits_api


def _numbers_again(api, crop, text: str) -> str:
    """Read every number in a headline again, with a reader that only knows
    digits. "रेलवे के 12 कर्मचारियों" came back as "2", or "42": the Hindi and
    English reader, reading both at once, took this paper's thin "1" for
    nothing at all, or for a 4.

    Each word that holds a digit is cut out a little wider than the reader
    said it was - out to the words either side, where a lost "1" sits - and
    read again as digits alone. The new reading is taken only when it is
    sure and loses none of the digits it replaces.
    """
    if not text or not any(ch.isdigit() for ch in text):
        return text
    engine = _digits_engine()
    if engine is None:
        return text
    try:
        import tesserocr

        level = tesserocr.RIL.WORD
        words = []
        walk = api.GetIterator()
        if walk is None:
            return text
        while True:
            try:
                said = walk.GetUTF8Text(level) or ""
                box = walk.BoundingBox(level)
            except Exception:  # noqa: BLE001
                said, box = "", None
            if box:
                words.append([said, box])
            if not walk.Next(level):
                break
        if not any(any(ch.isdigit() for ch in w[0]) for w in words):
            return text
        changed = False
        for at, (said, box) in enumerate(words):
            digits = "".join(ch for ch in said if ch.isascii() and ch.isdigit())
            if not digits:
                continue
            x0, y0, x1, y1 = box
            tall = max(4, y1 - y0)
            # Out to the neighbours on this line, where a dropped "1" sits.
            left = x0 - int(0.8 * tall)
            right = x1 + int(0.8 * tall)
            for other_said, (ox0, oy0, ox1, oy1) in (words[at - 1:at] +
                                                   words[at + 1:at + 2]):
                if min(y1, oy1) - max(y0, oy0) < 0.4 * tall:
                    continue
                if ox1 <= x0:
                    left = max(left, ox1 + 1)
                elif ox0 >= x1:
                    right = min(right, ox0 - 1)
            left, right = max(0, left), min(crop.width, right)
            top, bottom = max(0, y0 - tall // 4), min(crop.height, y1 + tall // 4)
            if right - left < 4 or bottom - top < 4:
                continue
            piece = crop.crop((left, top, right, bottom))
            from PIL import ImageOps

            engine.SetImage(ImageOps.expand(piece, border=12, fill=255))
            again = (engine.GetUTF8Text() or "").strip().replace(" ", "")
            sure = int(engine.MeanTextConf() or 0)
            again_digits = "".join(ch for ch in again if ch.isdigit())
            if (again and again_digits and sure >= 60
                    and len(again_digits) >= len(digits)
                    and all(ch in "0123456789.,:-/" for ch in again)):
                if again != said:
                    words[at][0] = again
                    changed = True
        if not changed:
            return text
        return " ".join(w[0] for w in words if w[0])
    except Exception:  # noqa: BLE001 - the first reading stands
        return text


def read_region(api, image, region) -> Headline:
    """Read ONE region of a picture - the one the finder says is the headline.

    The region is read as a single block of text: one to three lines of the
    same size, which is what a headline is. Nothing outside it is seen, so a
    photograph, the office's label or the paper's nameplate cannot end up in
    the words - and a label line the region did take in, at its top or foot,
    is dropped (_without_labels).
    """
    whole, bare = _read_region(api, image, region)
    return Headline(bare, whole.confidence, whole.engine) if bare else Headline()


def _read_region(api, image, region):
    """(the reading, the same reading without its label lines)."""
    if api is None or image is None or region is None:
        return Headline(), ""
    try:
        import tesserocr
        from PIL import Image, ImageOps

        crop = image.crop(region.box())
        if crop.width < 8 or crop.height < 8:
            return Headline(), ""
        crop = crop.convert("L")
        crop = _clear_edges(crop, region)
        # Reversed type, white on a dark strip, the ordinary way round.
        histogram = crop.histogram()
        half = sum(histogram) / 2
        running, median = 0, 255
        for level, many in enumerate(histogram):
            running += many
            if running >= half:
                median = level
                break
        if median < 100:
            crop = ImageOps.invert(crop)
        scale = READ_TYPE_HEIGHT / max(1.0, float(region.type_height or 0) or
                                       crop.height / 2.0)
        scale = max(0.4, min(4.0, scale))
        if abs(scale - 1.0) > 0.05:
            crop = crop.resize((max(1, int(crop.width * scale)),
                                max(1, int(crop.height * scale))),
                               Image.LANCZOS)
        crop = ImageOps.expand(crop, border=24, fill=255)
        was = api.GetPageSegMode()
        try:
            api.SetPageSegMode(tesserocr.PSM.SINGLE_BLOCK)
            api.SetImage(crop)
            text = api.GetUTF8Text() or ""
            confidence = int(api.MeanTextConf() or 0)
            text = _numbers_again(api, crop, text)
        finally:
            api.SetPageSegMode(was)
        whole = normalise(text)
        if not whole:
            return Headline(), ""
        return (Headline(whole, confidence, engine_name()),
                normalise(_without_labels(text)))
    except Exception:  # noqa: BLE001 - never let a reading break anything
        return Headline(), ""


def _headline_block(lines: list) -> list:
    """The lines that make up the headline: [(top, text, confidence)].

    ``lines`` is [(top, height, text, confidence)] in whatever order the reader
    handed them over. The tallest line is the headline's anchor - that much the
    old rule had right - and the rest of the headline is whatever is stacked
    directly against it in nearly the same size. See SAME_BLOCK and BLOCK_GAP
    for the measurement behind the two numbers.
    """
    if not lines:
        return []
    rows = sorted(lines, key=lambda row: row[0])
    tallest = max(height for _top, height, _text, _conf in rows)
    anchor = max(range(len(rows)), key=lambda i: rows[i][1])
    taken = [anchor]

    for step in (-1, 1):
        at = anchor
        while True:
            nxt = at + step
            if not 0 <= nxt < len(rows):
                break
            here, other = rows[at], rows[nxt]
            if other[1] < SAME_BLOCK * tallest:
                break                       # a different size: not this headline
            # The gap between the two, whichever of them is on top.
            upper, lower = (other, here) if step < 0 else (here, other)
            if (lower[0] - (upper[0] + upper[1])) > BLOCK_GAP * upper[1]:
                break                       # a visible break: not this headline
            taken.append(nxt)
            at = nxt

    return [(rows[i][0], rows[i][2], rows[i][3]) for i in sorted(taken)]


def _as_printed(clip) -> bytes:
    """The clipping as the report shows it - trimmed and turned.

    It used to be read from the bytes it arrived as, which is the picture
    BEFORE any of that. A clipping turned ninety degrees was read on its side
    and came back with nothing; one trimmed down to its headline was read with
    everything the trim took off still in the way, and the headline the reader
    picked was whatever the old top of the picture held.

    Falls back to the bytes it arrived as, because a picture that will not
    render is still worth a try.
    """
    raw = getattr(clip, "image_bytes", b"") or b""
    if not raw:
        return raw
    crop = getattr(clip, "crop", None)
    turned = int(getattr(clip, "rotation", 0) or 0) % 360
    if (crop is None or crop.is_identity) and not turned:
        return raw                      # nothing was done to it
    try:
        image = clip.render()
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        out = io.BytesIO()
        image.save(out, "PNG")
        return out.getvalue()
    except Exception:  # noqa: BLE001 - a picture we cannot render reads as it came
        return raw


def read_into(clip, force: bool = False) -> Headline:
    """Read a clipping's headline and remember it on the clipping.

    Kept on the clip so it is read once and once only: it survives a save and
    reload, and a list that redraws a hundred times does not re-read anything.
    The fields were already in the model, declared for an OCR pass that was
    never built.
    """
    from . import imageops

    # The fingerprints come FIRST, before the "already read" shortcut below.
    # They are cheap, and a clipping can easily have been read by a build that
    # did not take one of them - every clipping in a session saved before the
    # lower-part print existed is in exactly that state. Taking them after the
    # shortcut meant those clippings never got one, and a missing lower print
    # counts as "the pictures agree", so two different stories under one
    # newspaper's masthead banner were flagged as copies all over again on any
    # list restored from an older save.
    if not (clip.picture_hash and clip.picture_hash_lower
            and getattr(clip, "ink_profile", "")
            and getattr(clip, "content_w", 0)):
        seen = imageops.measure_clip(clip)
        clip.picture_hash = clip.picture_hash or seen["whole"]
        clip.picture_hash_lower = clip.picture_hash_lower or seen["lower"]
        clip.picture_hash_fine = (getattr(clip, "picture_hash_fine", "")
                                  or seen["fine"])
        clip.ink_profile = getattr(clip, "ink_profile", "") or seen["ink"]
        if not getattr(clip, "content_w", 0):
            clip.content_w = seen["width"]
            clip.content_h = seen["height"]

    if clip.ocr_engine == BY_HAND and not force:
        # Typed by somebody. Never read over, never scored again: their words
        # are the answer until they ask for another reading.
        return Headline(clip.ocr_text, clip.headline_confidence, BY_HAND)
    if current(clip.ocr_engine) and not force:
        return Headline(clip.ocr_text, clip.headline_confidence,
                        clip.ocr_engine)
    found = headline(_as_printed(clip))
    clip.ocr_text = found.text
    clip.headline_confidence = found.confidence
    # Stamped even when nothing was read, so a clipping that cannot be read is
    # not read again on every import.
    clip.ocr_engine = stamp()
    return found
