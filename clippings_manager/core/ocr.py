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
    # What is left has to be a cutting, not a sliver.
    if (height - cut) < height * BAND_LEAVES:
        return image
    return image.crop((0, cut, width, height))


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
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image = strip_band(image)
        finding = headfind.find(image)
    except Exception:  # noqa: BLE001 - a picture the finder cannot look at
        return None, Headline()
    if not finding.candidates:
        return None, Headline()
    def story(found) -> bool:
        letters = sum(1 for ch in found.text if ch.isalpha())
        return bool(found.text and letters >= 4
                    and not _is_furniture(found.text)
                    and not _nameplate(found.text))

    for region in finding.candidates[:CANDIDATES_READ]:
        found = read_region(api, image, region)
        if story(found):
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
    try:
        from PIL import Image

        picture = Image.open(io.BytesIO(data))
        picture.load()
        _finding, found = two_stage(api, picture)
        if found.text and found.confidence >= SURE and not _scrappy(found.text):
            return found
    except Exception:  # noqa: BLE001 - the old way still stands
        found = Headline()
    return _cleaner(found, _old_way(api, data))


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
    candidates = [(not _scrappy(h.text), h.confidence + bonus, n, h)
                  for n, (h, bonus) in enumerate(((two, 3), (old, 0)))
                  if h.text]
    if not candidates:
        return two if two.text else old
    return max(candidates, key=lambda c: (c[0], c[1], -c[2]))[3]


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

    image = Image.open(io.BytesIO(data))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    image = strip_band(image)
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
        crop = picture.crop((left, top, right, bottom))
        size = 0.0
        if headfind.available():
            finding = headfind.find(crop)
            if finding.best is not None:
                size = finding.best.type_height
        region = headfind.Region(0, 0, crop.width, crop.height,
                                 type_height=size or crop.height / 2.5)
        return read_region(api, crop, region)
    except Exception:  # noqa: BLE001 - a box that will not read reads empty
        return Headline()


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


def read_region(api, image, region) -> Headline:
    """Read ONE region of a picture - the one the finder says is the headline.

    The region is read as a single block of text: one to three lines of the
    same size, which is what a headline is. Nothing outside it is seen, so a
    photograph, the office's label or the paper's nameplate cannot end up in
    the words.
    """
    if api is None or image is None or region is None:
        return Headline()
    try:
        import tesserocr
        from PIL import Image, ImageOps

        crop = image.crop(region.box())
        if crop.width < 8 or crop.height < 8:
            return Headline()
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
        finally:
            api.SetPageSegMode(was)
        text = normalise(text)
        if not text:
            return Headline()
        return Headline(text, confidence, engine_name())
    except Exception:  # noqa: BLE001 - never let a reading break anything
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
    if clip.ocr_engine and not force:
        return Headline(clip.ocr_text, clip.headline_confidence,
                        clip.ocr_engine)
    found = headline(_as_printed(clip))
    clip.ocr_text = found.text
    clip.headline_confidence = found.confidence
    # Stamped even when nothing was read, so a clipping that cannot be read is
    # not read again on every import.
    clip.ocr_engine = found.engine or (engine_name() or "none")
    return found
