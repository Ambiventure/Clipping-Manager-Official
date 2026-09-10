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
# "06-09-2026". Dates belong to mastheads; headlines do not carry them.
DATED = re.compile(r"\d{1,2}\s*[^\w\s]{0,2}\s*\d{1,2}\s*[^\w\s]{0,2}\s*\d{2,4}")

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


def _is_name(text: str) -> bool:
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
        if len(name) >= 6 and fuzz.partial_ratio(name, body) >= 92 and                 len(body) <= len(name) * 2:
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


def normalise(text: str) -> str:
    """One spelling, so two readings of the same words compare equal.

    Composed form, because Devanagari has more than one way to write the same
    letter and OCR does not always pick the same one; folded case, which only
    affects the Latin half and does nothing to Devanagari; and single spaces,
    because line breaks in a headline are a matter of column width.
    """
    return " ".join(unicodedata.normalize("NFC", text or "").split()).lower()


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
BAND_LIMIT = 0.35            # never eat more than this much of the picture


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
    if not means or means[0] > BAND_DARK:
        return image                          # nothing dark at the top

    cut, clear = 0, 0
    ceiling = int(height * BAND_LIMIT)
    for y in range(min(len(means), ceiling)):
        if means[y] >= BAND_LIGHT:
            clear += 1
            if clear >= BAND_CLEAR_ROWS:
                cut = y - BAND_CLEAR_ROWS + 1
                break
        else:
            clear = 0
    if cut <= 0:
        return image
    return image.crop((0, cut, width, height))


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


def headline_with(api, data: bytes) -> Headline:
    """The headline, read with a reader of the caller's own.

    Same work as :func:`headline`, but against an engine that belongs to one
    thread, so several clippings can be read at once without them treading on
    each other.
    """
    if api is None or not data:
        return Headline()
    found = _read_band(api, data, TOP_BAND)
    if not found.text:
        found = _read_band(api, data, DEEPER_BAND)
    return found


def _prepare(data: bytes, portion: float = TOP_BAND):
    """The band of picture the headline is in, at a size worth reading."""
    from PIL import Image

    image = Image.open(io.BytesIO(data))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    image = strip_band(image)
    band = image.crop((0, 0, image.width,
                       max(60, int(image.height * portion))))
    if band.width < MIN_WIDTH:
        return None
    scale = TARGET_WIDTH / band.width
    if abs(scale - 1.0) > 0.05:
        band = band.resize((max(1, int(band.width * scale)),
                            max(1, int(band.height * scale))), Image.LANCZOS)
    return band


def headline(data: bytes) -> Headline:
    """The headline printed on this clipping, or an empty reading.

    Never raises. A clipping that cannot be read is not an error - it is a
    clipping that will not take part in duplicate matching, which is the right
    outcome and the one the user asked for.
    """
    api = _open()
    if api is None or not data:
        return Headline()
    found = _read_band(api, data, TOP_BAND)
    if not found.text:
        # Nothing but furniture in the top of the picture. On a whole page
        # rather than a cutting the headline can be further down, and coming
        # back with nothing is worse than a second look.
        found = _read_band(api, data, DEEPER_BAND)
    return found


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
            if box and text and text.strip():
                lines.append((box[1], box[3] - box[1], text.strip(),
                              confidence))
            if not walk.Next(level):
                break
        if not lines:
            return Headline()

        # The masthead band goes first, before anything is measured. It is
        # frequently the biggest type on the cutting, so leaving it in and
        # picking the tallest line reads the paper's name instead of the story.
        lines = [row for row in lines if not _is_furniture(row[2])]
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

    if clip.ocr_engine and not force:
        return Headline(clip.ocr_text, clip.headline_confidence,
                        clip.ocr_engine)
    found = headline(getattr(clip, "image_bytes", b"") or b"")
    clip.ocr_text = found.text
    clip.headline_confidence = found.confidence
    # Stamped even when nothing was read, so a clipping that cannot be read is
    # not read again on every import.
    clip.ocr_engine = found.engine or (engine_name() or "none")
    return found
