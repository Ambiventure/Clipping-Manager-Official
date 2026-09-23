"""Hindi read back out of a PDF by glyph number, and checked by drawing it again.

Every PDF this program exports is written by MuPDF, which shapes Devanagari
properly - but the text map it writes beside the glyphs only names the glyphs
the font's character map names. Everything the font's substitution table
(GSUB) makes - the vowel-sign width variants, half letters, the reph, the
conjuncts, e with a nasal mark over it - goes into the file with no character
at all. get_texttrace() reports those as U+FFFD, and get_text() hands back the
glyph NUMBER as if it were a letter. The office's own 11.09 report came back
reading "दैनə क जागरण दɘ Ėली" for "दैनिक जागरण दिल्ली", which the name lookup
took for Dainik Jagran with an edition of "दɘ Ėली"; 06.09's "पंजाब केसरी"
came back as "पंजाब केसरʟ". Neither is caught by assemble.unreadable - "ə"
and "ʟ" are ordinary letters to Python - so neither went near glyphmap.

The way back is the one glyphmap takes for Latin, done with the font the page
was really drawn in, which MuPDF embeds whole: name each glyph through that
font's character map, or through its substitution table read backwards, and
keep the glyphs in the order they are stored. MuPDF stores them in the order
they were typed, so - unlike a Word file, which devanagari.reorder exists for -
nothing is moved. Read through devanagari.decode's reordering the same glyphs
come out "दैनकि" and "दल्लिी".

A glyph can nearly always be read more than one way, so no reading is believed
on its face. Every spelling is drawn again with the same font, by the same
MuPDF, and kept only if it comes out as exactly the glyphs on the page. A line
is replaced only when every word in it checks out; otherwise it is left exactly
as it was.

Measured. The 126 Hindi names and captions of the newspaper list, drawn by the
exporter's own _draw_line in all six heading families, bold and regular, came
back 1,512 of 1,512 exact, none wrong and none refused, where get_text() alone
had 404. The office's 11.09, 06.09 and Water Safety reports read "दैनिक जागरण
दिल्ली", "पंजाब केसरी" and "हिंदुस्तान". The Word-made 26.08 press report is
never looked at - its Hindi is Mangal under the name "CIDFont+F3", the rest
Arial, Times and more CIDFonts - and when its 820 unnamed words were put to
the checker anyway, in whatever font drew them, every one was refused.

What it costs, both ends of it. The 254-page 18.09 report costs 6 ms, because
nothing on it has to be drawn at all - every glyph on its Devanagari pages is
named - and the office's own three Hindi reports cost 14 to 18 ms, because a
newspaper's name repeats and is worked out once. A made-up report whose 120
captions are 120 DIFFERENT Hindi phrases costs 4.2 s, on top of the 1.1 s the
import took without it, and an import runs on the window's own thread. That is
what MOST_SECONDS is for.
"""

from __future__ import annotations

import hashlib
import html
import itertools
import re
import time
import unicodedata
from collections import Counter
from typing import Optional

import pymupdf

from . import devanagari, glyphmap

# What get_texttrace() reports for a glyph the PDF's text map does not name.
UNNAMED = 0xFFFD

# How many ways of reading one word are tried. A word in the office's reports
# has at most a few unnamed glyphs with a few readings each; a word that
# offers more than this is refused rather than half searched, because a
# spelling that checks out is only trusted when it is the ONLY one that does.
MOST_READINGS = 512

# How long one document may spend DRAWING spellings before the rest of its
# Hindi is left exactly as it arrived. Every real report measured here spends
# milliseconds - 18 ms for the office's Water Safety report, 6 ms for the
# 254-page 18.09 - because a newspaper's name repeats and is only worked out
# once. A made-up report whose 120 captions were 120 different Hindi phrases
# cost 4.2 s, and an import runs on the window's own thread, so the window
# would sit still for it. Past this the words are refused rather than drawn:
# those captions come in unnamed and counted, which is what a refusal means
# everywhere else here, and never a name that might be wrong.
MOST_SECONDS = 5.0

# The spellings a glyph-by-glyph reading gets wrong in a way that still draws
# right, put back the way they are typed. A font draws the o sign as the aa
# sign plus a mark on top, so the mark reads as e and "ो" comes back "ाे";
# Noto Sans draws ii as i with a reph-shaped mark; and a reph fused with the e
# sign arrives in front of the letter it sits on. Each rewrite is only a
# CANDIDATE - it is drawn again like every other spelling, and kept only if
# the drawing matches.
_CONSONANTS = "".join(sorted(devanagari.CONSONANTS))
_RESPELL = [
    (re.compile("\u093e([\u0902\u0901]?)\u0947"), "\u094b\\1"),
    (re.compile("\u093e([\u0902\u0901]?)\u0948"), "\u094c\\1"),
    (re.compile("\u093e\u0947([\u0902\u0901])"), "\u094b\\1"),
    (re.compile("\u093e\u0948([\u0902\u0901])"), "\u094c\\1"),
    (re.compile("\u0907\u0930\u094d(?![" + _CONSONANTS + "])"), "\u0908"),
    (re.compile("\u0947\u0930\u094d([" + _CONSONANTS + "])\u093e"),
     "\u0930\u094d\\1\u094b"),
    (re.compile("\u0947\u0930\u094d([" + _CONSONANTS + "])"),
     "\u0930\u094d\\1\u0947"),
]

# The scratch page spellings are drawn on. Each spelling gets a line of its
# own, three font-sizes apart, so a mark the font nudges up or down can never
# be counted on the line above or below.
_SIZE = 20
_PITCH = 3 * _SIZE


def _key(name: str) -> str:
    """A font's name the way both the font list and the text spans spell it.

    The page's font list says "Noto Sans Devanagari Bold", its text says
    "NotoSansDevanagari-Bold", and a subset carries a "BAAAAA+" in front.
    """
    return re.sub(r"[\s\-_]", "", (name or "").split("+", 1)[-1]).lower()


def is_devanagari(name: str) -> bool:
    return "devanagari" in _key(name)


def worth_reading(font_names) -> bool:
    """Whether a page is set in a Devanagari face at all.

    The only pages this module ever looks at. Every Devanagari face this
    program's PDFs are drawn in says so in its name - the bundled Noto Sans
    Devanagari and MuPDF's own Noto Serif Devanagari - and a Word file's
    Mangal or anonymised "CIDFont+F3" does not, so a division's document is
    not even traced, let alone changed.
    """
    return any(is_devanagari(name) for name in font_names or ())


def as_typed(text: str) -> str:
    """The reading with the format characters a character map named put right.

    A font's map often offers more than one codepoint for a glyph and MuPDF
    picks one of them. Times New Roman, Arial, Georgia, Verdana, Tahoma,
    Courier New and Book Antiqua all name their hyphen glyph U+00AD, the SOFT
    hyphen, which is a format character; one of those in a twenty-letter
    caption is five per cent, and assemble.unreadable throws a line away at
    two. So "दैनिक जागरण - दिल्ली", read back here letter for letter in the
    user's own heading style, was dropped as mojibake where 2.0.39 had kept
    it - the one thing this module must never do.

    Drawing a spelling again confirms which GLYPHS are on the page, never
    which of the map's codepoints MuPDF chose to name them by, so the choice
    is the one thing here that is ours to put right: the soft hyphen is the
    hyphen it draws as, and any other format character - none of which draws
    anything at all - goes.
    """
    if not any(unicodedata.category(ch) == "Cf" for ch in text):
        return text
    kept = []
    for ch in text:
        if ch == "\u00ad":
            kept.append("-")
        elif unicodedata.category(ch) != "Cf":
            kept.append(ch)
    return "".join(kept)


class Budget:
    """What is left of one document's drawing time (MOST_SECONDS)."""

    def __init__(self, seconds: float = MOST_SECONDS) -> None:
        self.left = seconds

    def spent(self) -> bool:
        return self.left <= 0.0


def _respellings(text: str) -> list:
    found = {text}
    frontier = {text}
    for _round in range(3):
        fresh = set()
        for spelling in frontier:
            for pattern, replacement in _RESPELL:
                changed = pattern.sub(replacement, spelling)
                if changed != spelling:
                    fresh.add(changed)
        fresh -= found
        if not fresh:
            break
        found |= fresh
        frontier = fresh
    return sorted(found)


class Face:
    """One font the PDF embedded: what its glyphs are, and how it draws."""

    def __init__(self, buf: bytes, ext: str,
                 budget: Optional[Budget] = None) -> None:
        self.digest = hashlib.sha1(buf).hexdigest()
        self.budget = budget if budget is not None else Budget()
        self.cmap = glyphmap.cmap_of(buf)
        self.gsub = devanagari.read_gsub(buf)
        stored_as = "face.otf" if ext in ("otf", "cff") else "face.ttf"
        self.archive = pymupdf.Archive()
        self.archive.add((buf, stored_as))
        self.css = (f"@font-face {{ font-family: glyphtext; src: url({stored_as}); }} "
                    f"* {{ font-family: glyphtext; font-size: {_SIZE}px; margin: 0; "
                    f"line-height: {_PITCH / _SIZE}; }}")
        self._readings: dict = {}
        self._drawn: dict = {}
        self._alone: dict = {}
        self.words: dict = {}

    def readings(self, glyph: int, depth: int = 0,
                 seen: frozenset = frozenset()) -> list:
        """Every (text, feature) this glyph could have been made from.

        All of them, not the likeliest one as devanagari.expand gives: the
        drawing decides between them, and it can only choose the right one if
        the right one is on the list.
        """
        if not depth and glyph in self._readings:
            return self._readings[glyph]
        found = []
        if glyph in self.cmap:
            found.append((self.cmap[glyph], ""))
        elif depth < 6:
            here = seen | {glyph}
            for sequence, tag in self.gsub["ligature"].get(glyph, ()):
                if any(part in here for part in sequence):
                    continue
                parts = [self.readings(part, depth + 1, here) for part in sequence]
                if not all(parts):
                    continue
                for combo in itertools.islice(itertools.product(*parts), 8):
                    found.append(("".join(text for text, _tag in combo),
                                  tag or combo[0][1]))
            for source, tag in self.gsub["single"].get(glyph, ()):
                if source in here:
                    continue
                for text, inner in self.readings(source, depth + 1, here):
                    found.append((text, inner or tag))
        found = list(dict.fromkeys(found))
        if not depth:
            self._readings[glyph] = found
        return found

    def draw(self, spellings: list) -> list:
        """What MuPDF draws each spelling as: [(font names, glyph numbers)].

        All on one scratch page, one line each - an HTML box costs about 5 ms
        however little is in it, so two hundred spellings drawn together cost
        10 ms where one at a time they cost a second. If the lines do not come
        back one for one, each spelling is drawn on its own instead.
        """
        wanted = [s for s in dict.fromkeys(spellings) if s not in self._drawn]
        if len(wanted) > 1:
            drawn = self._draw_together(wanted)
            if drawn is not None:
                self._drawn.update(zip(wanted, drawn))
        for spelling in wanted:
            if spelling not in self._drawn:
                self._drawn[spelling] = self.draw_alone(spelling)
        return [self._drawn[s] for s in spellings]

    def draw_alone(self, spelling: str):
        """One spelling on a page to itself, as the last word on a reading.

        Drawing many together is how the right spelling is found; drawing it
        alone is what it is believed on, so nothing about sharing a page with
        two hundred others can ever be what made it match.
        """
        if spelling not in self._alone:
            drawn = self._draw_together([spelling])
            self._alone[spelling] = drawn[0] if drawn else None
        return self._alone[spelling]

    def _draw_together(self, spellings: list) -> Optional[list]:
        if self.budget.spent():
            return None     # this document has had its MOST_SECONDS
        started = time.perf_counter()
        try:
            with pymupdf.open() as scratch:
                page = scratch.new_page(width=2000,
                                        height=_PITCH * (len(spellings) + 1))
                page.insert_htmlbox(
                    page.rect,
                    "".join(f"<div>{html.escape(s)}</div>" for s in spellings),
                    css=self.css, archive=self.archive)
                lines: dict = {}
                for span in page.get_texttrace():
                    for char in span["chars"]:
                        if char[1] < 0:
                            continue        # a second character of one glyph
                        slot = int(char[2][1] // _PITCH)
                        fonts, glyphs = lines.setdefault(slot, (set(), []))
                        fonts.add(span["font"])
                        glyphs.append(char[1])
        except Exception:  # noqa: BLE001 - a drawing that fails confirms nothing
            return None
        finally:
            self.budget.left -= time.perf_counter() - started
        if sorted(lines) != list(range(len(spellings))):
            return None
        return [(frozenset(lines[n][0]), tuple(lines[n][1]))
                for n in range(len(spellings))]


def read_word(glyphs: list, face: Face, font: str) -> Optional[str]:
    """One word as stored - [(character, glyph)] in ``font`` - or None.

    Every way of reading its unnamed glyphs is spelt out and drawn, and the
    word is the spelling that draws exactly these glyphs in exactly this font.
    Two spellings can draw alike - the o sign and aa followed by e are the same
    three glyphs - and only one of those is Hindi, so a well-formed spelling
    beats one that is not. If two well-formed spellings both draw it, or
    none does, the word is not read: a name that might be wrong is worse than
    one that is missing.
    """
    key = (font, tuple(glyphs))
    if key in face.words:
        return face.words[key]
    face.words[key] = None

    choices = []
    for code, glyph in glyphs:
        if code == UNNAMED:
            named = face.readings(glyph) if glyph >= 0 else []
            if not named:
                return None
            choices.append(named)
        else:
            choices.append([(chr(code), "")])
    ways = 1
    for choice in choices:
        ways *= len(choice)
    if ways > MOST_READINGS:
        return None

    spellings = []
    for combo in itertools.product(*choices):
        plain = "".join(
            devanagari.VIRAMA + devanagari.RA
            if tag == devanagari.RAKAR and text == devanagari.RA + devanagari.VIRAMA
            else text
            for text, tag in combo)
        for spelling in _respellings(plain):
            spellings.append(unicodedata.normalize("NFC", spelling))
    spellings = list(dict.fromkeys(spellings))

    target = (frozenset([font]), tuple(g for _c, g in glyphs if g >= 0))
    matched = [s for s, drawn in zip(spellings, face.draw(spellings))
               if drawn == target]
    hindi = [s for s in matched if devanagari.well_formed(s)]
    pool = hindi or matched
    if len(pool) != 1 or face.draw_alone(pool[0]) != target:
        return None
    # The glyphs are settled; how the map spells them is not (as_typed). A
    # rewrite is only taken if it draws the same glyphs in the same font, so
    # nothing here is believed on anything but the page.
    chosen = pool[0]
    plain = as_typed(chosen)
    if plain != chosen and face.draw_alone(plain) == target:
        chosen = plain
    face.words[key] = chosen
    return chosen


def _budget(faces: dict) -> Budget:
    """This document's drawing time. One per faces cache, so one per file."""
    if "budget" not in faces:
        faces["budget"] = Budget()
    return faces["budget"]


def _load(document, xref: int, faces: dict) -> Optional[Face]:
    """The font behind one xref, shared with every other copy of it.

    MuPDF embeds the font afresh for every caption it draws, so a document
    that has not been saved with garbage collection holds a copy per caption -
    which a report of ours does not, because build_pdf saves with garbage=4
    and clean=True and those fold into one. It is the round-trip file the
    suite writes page by page that had 1,404 of them, and reading each copy's
    tables and drawing its words again made that file take 21 s rather than 6.
    One Face per distinct font means a word is only ever worked out once.
    """
    try:
        _name, ext, _kind, buf = document.extract_font(xref)
    except Exception:  # noqa: BLE001 - a font we cannot read confirms nothing
        return None
    if not buf:
        return None
    digest = ("font", hashlib.sha1(buf).hexdigest())
    if digest not in faces:
        try:
            faces[digest] = Face(buf, ext, _budget(faces))
        except Exception:  # noqa: BLE001
            faces[digest] = None
    return faces[digest]


def _face(document, xrefs: list, faces: dict) -> Optional[Face]:
    """The embedded font behind a name, or None if the name is not enough.

    Two fonts of one name with different contents - two reports merged into
    one file - cannot be told apart from the text, so neither is used.
    """
    found = []
    for xref in xrefs:
        if xref not in faces:
            faces[xref] = _load(document, xref, faces)
        found.append(faces[xref])
    if not found or any(f is None or f.digest != found[0].digest for f in found):
        return None
    return found[0]


def _letters(chars) -> Counter:
    return Counter(ch for ch in chars if not ch.isspace())


def _read_row(glyphs: list, document, fonts: dict, faces: dict) -> Optional[str]:
    """The words of one line of glyphs, in the order stored, or None."""
    out: list = []
    word: list = []

    def finish() -> bool:
        pieces: list = []
        for glyph in word:
            if pieces and pieces[-1][0] == glyph[2]:
                pieces[-1][1].append(glyph)
            else:
                pieces.append((glyph[2], [glyph]))
        for font, piece in pieces:
            if not any(code == UNNAMED for code, _g, _f in piece):
                # Named throughout, so nothing here is drawn again - but the
                # codepoint the map named is still MuPDF's pick, and a Times
                # hyphen arrives as the soft hyphen (as_typed). A line this
                # module has just CONFIRMED skips the repair branch in
                # extract_pdf, so a format character left in it would go
                # straight past assemble.unreadable and cost the caption.
                out.append(as_typed("".join(chr(code) for code, _g, _f in piece)))
                continue
            if not is_devanagari(font):
                return False
            face = _face(document, fonts.get(_key(font), []), faces)
            if face is None:
                return False
            text = read_word([(code, g) for code, g, _f in piece], face, font)
            if text is None:
                return False
            out.append(text)
        word.clear()
        return True

    for code, glyph, font in glyphs:
        if code != UNNAMED and chr(code).isspace():
            if not finish():
                return None
            out.append(" ")
        else:
            word.append((code, glyph, font))
    if not finish():
        return None
    return " ".join("".join(out).split())


def _horizontal(direction) -> bool:
    dx, dy = direction or (1.0, 0.0)
    return abs(dx - 1.0) < 1e-3 and abs(dy) < 1e-3


def mend(document, page, blocks: list, faces: dict) -> dict:
    """What to do with each text line of the page that holds unnamed Hindi.

    ``blocks`` are the page's get_text("dict") blocks, ``faces`` a cache the
    caller keeps for the whole document. The answer is keyed by (block, line)
    and only names the lines concerned:

    * ("text", words, box) - the line reads as ``words``. MuPDF sometimes
      breaks one word across two dict lines, because the short i is drawn
      before the letter it follows ("हिंदुस्तान" came back as "ह" and
      "Ȭ ˷ǧĀतान"), so the words replace every line on that row and the box is
      all of theirs;
    * ("drop",) - one of those other lines, now said by the first;
    * ("garbled",) - it could not be read, and stays exactly as it is.

    The glyphs are matched to their lines by the baseline they sit on, and a
    line is only rebuilt when the glyphs found for it account for every letter
    get_text() gave for it, an unnamed glyph counted as the glyph number
    get_text() shows in its place. The one thing allowed over is an unnamed
    glyph get_text() left out: the reph fused with the o sign in "सूर्योदय" is
    drawn back over the letter before it, and get_text() drops it rather than
    place it - which is how that masthead read "सू" and "यादय".

    THE JOIN IS BELIEVED, NOT CHECKED. Drawing the words again confirms the
    GLYPHS; it says nothing about whether two dict lines on one baseline are
    one caption. They are here because our exporter prints one caption to a
    baseline, and because a page is only looked at when it is set in a
    Devanagari face - which, on every file on this machine, means one of our
    own reports and the office's own 06.09. In a document laid out in columns
    a table cell and the count beside it would share a baseline and be run
    together into one line under one box. Geometry does not tell them apart:
    the pieces MuPDF makes of one word do not reliably overlap either ("आ"
    ends where "र्थिक" begins, because the short i that made MuPDF split is
    drawn after the आ), and a rule that wanted them to overlap refused 178 of
    the round trip's 1,512 lines. If such a document ever has to be read, the
    thing to add is the columns, not a margin.
    """
    try:
        spans = page.get_texttrace()
    except Exception:  # noqa: BLE001 - nothing read, nothing changed
        return {}
    glyphs = []
    for span in spans:
        if not _horizontal(span.get("dir")):
            continue
        font = span.get("font", "")
        for char in span.get("chars", ()):
            glyphs.append((char[2][0], char[2][1], char[0], char[1], font))
    if not any(g[2] == UNNAMED and is_devanagari(g[4]) for g in glyphs):
        return {}

    try:
        fonts: dict = {}
        for entry in page.get_fonts():
            fonts.setdefault(_key(entry[3]), []).append(entry[0])
    except Exception:  # noqa: BLE001
        fonts = {}

    verdicts: dict = {}
    for b, block in enumerate(blocks):
        if block.get("type") != 0:
            continue
        x0, y0, x1, y1 = block.get("bbox") or (0, 0, 0, 0)
        inside = [g for g in glyphs
                  if x0 - 1 <= g[0] <= x1 + 1 and y0 - 1 <= g[1] <= y1 + 1]
        if not any(g[2] == UNNAMED and is_devanagari(g[4]) for g in inside):
            continue
        rows: list = []                 # [baseline, tolerance, line numbers]
        lines = block.get("lines", [])
        for n, line in enumerate(lines):
            spans_here = line.get("spans") or []
            if not spans_here or not _horizontal(line.get("dir")):
                continue
            base = spans_here[0]["origin"][1]
            tolerance = max(0.5, 0.25 * float(spans_here[0].get("size") or 0))
            for row in rows:
                if abs(row[0] - base) <= min(row[1], tolerance):
                    row[2].append(n)
                    break
            else:
                rows.append([base, tolerance, [n]])

        for base, tolerance, members in rows:
            mine = [g for g in inside if abs(g[1] - base) <= tolerance]
            if not any(g[2] == UNNAMED and is_devanagari(g[4]) for g in mine):
                continue
            printed = _letters(ch for n in members for span in lines[n]["spans"]
                               for ch in span.get("text", ""))
            traced = _letters(chr(g[3]) if g[2] == UNNAMED and g[3] >= 0
                              else chr(g[2]) for g in mine)
            unnamed = _letters(chr(g[3]) for g in mine
                               if g[2] == UNNAMED and g[3] >= 0)
            words = None
            if not printed - traced and not (traced - printed) - unnamed:
                words = _read_row([(g[2], g[3], g[4]) for g in mine],
                                  document, fonts, faces)
            if not words:
                for n in members:
                    verdicts[(b, n)] = ("garbled",)
                continue
            boxes = [lines[n].get("bbox") or (0, 0, 0, 0) for n in members]
            box = (min(r[0] for r in boxes), min(r[1] for r in boxes),
                   max(r[2] for r in boxes), max(r[3] for r in boxes))
            verdicts[(b, members[0])] = ("text", words, box)
            for n in members[1:]:
                verdicts[(b, n)] = ("drop",)
    return verdicts
