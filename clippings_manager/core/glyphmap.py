"""Read text out of a PDF whose fonts were stripped of their character map.

Some PDFs - the department's combined press report is one - embed every font as
a subset with no ``cmap`` table and no ``/ToUnicode``. The page still draws
correctly, because the drawing only needs outlines, but the text layer is glyph
NUMBERS rather than characters. Extracted, "The Times of India, Delhi" comes back
as ``dŚĞ\\x03dŝŵĞƐ\\x03ŽĨ\\x03/ŶĚŝĂ͕\\x03\\x18ĞůŚŝ`` and "Amar Ujala" as
``$PDU\\x038MDOD``. On one real document that is 578 captions.

The way back is that the subsetter kept the ORIGINAL font's glyph numbering.
Take an unsubsetted copy of the same font off this machine, read its character
map, invert it, and glyph 100 is "T" again. Two different manglings in that one
document turned out to be nothing more than two different fonts: Calibri's glyph
order and the ASCII-ordered one Times New Roman and Arial share.

Nothing here guesses. A repair is used only when the result reads like real text
and beats the alternatives clearly; anything less and the caption stays empty, so
a clipping arrives unnamed rather than confidently wrong.
"""

from __future__ import annotations

import os
import struct
import unicodedata
from pathlib import Path
from typing import Iterable, Optional

from . import devanagari

# Where Windows keeps its fonts. A per-user install puts them in the second one.
FONT_FOLDERS = (
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts",
)

# The faces these documents are actually set in. Two glyph orders cover both
# manglings seen so far; the rest are here because the same office produces
# documents in them and they cost nothing to try.
CANDIDATES = (
    ("calibri", "calibri.ttf"),
    ("calibri-bold", "calibrib.ttf"),
    ("times", "times.ttf"),
    ("times-bold", "timesbd.ttf"),
    ("arial", "arial.ttf"),
    ("arial-bold", "arialbd.ttf"),
    ("cambria", "cambria.ttc"),
    ("segoe", "segoeui.ttf"),
    ("verdana", "verdana.ttf"),
    ("tahoma", "tahoma.ttf"),
)

# What a font's name in the PDF suggests. The subset prefix ("AAAAAA+") is cut
# off before matching, and the match is loose because the names vary:
# "TimesNewRomanPS-BoldMT", "Arial-BoldMT", "Calibri-Bold".
HINTS = (
    ("calibri", ("calibri", "carlito")),
    ("times", ("times", "timesnewroman", "tinos")),
    ("arial", ("arial", "helvetica", "liberationsans")),
    ("cambria", ("cambria", "caladea")),
    ("segoe", ("segoe",)),
    ("verdana", ("verdana",)),
    ("tahoma", ("tahoma",)),
)

# A repair has to be this readable to be believed, and this much better than the
# next best guess. Both were chosen against the real document: the right font
# scores 1.0 there and every wrong one below 0.5.
MIN_READABLE = 0.80
MIN_MARGIN = 0.15

_cache: dict[str, dict] = {}


# --------------------------------------------------------------- the font file


def _tables(buf: bytes) -> dict:
    """Where each sfnt table starts, for a .ttf or the first face of a .ttc."""
    base = struct.unpack(">I", buf[12:16])[0] if buf[:4] == b"ttcf" else 0
    count = struct.unpack(">H", buf[base + 4:base + 6])[0]
    found = {}
    for index in range(count):
        at = base + 12 + index * 16
        tag = buf[at:at + 4].decode("latin-1")
        start, length = struct.unpack(">II", buf[at + 8:at + 16])
        found[tag] = (start, length)
    return found


def _from_format_4(buf: bytes, sub: int) -> dict:
    seg_bytes = struct.unpack(">H", buf[sub + 6:sub + 8])[0]
    segments = seg_bytes // 2
    ends = sub + 14
    starts = ends + seg_bytes + 2
    deltas = starts + seg_bytes
    ranges = deltas + seg_bytes
    mapping: dict[int, str] = {}
    for index in range(segments):
        end = struct.unpack(">H", buf[ends + index * 2:ends + index * 2 + 2])[0]
        start = struct.unpack(">H", buf[starts + index * 2:starts + index * 2 + 2])[0]
        delta = struct.unpack(">h", buf[deltas + index * 2:deltas + index * 2 + 2])[0]
        offset = struct.unpack(">H", buf[ranges + index * 2:ranges + index * 2 + 2])[0]
        if start == 0xFFFF:
            continue
        for code in range(start, min(end, 0xFFFE) + 1):
            if offset == 0:
                glyph = (code + delta) & 0xFFFF
            else:
                at = ranges + index * 2 + offset + (code - start) * 2
                if at + 2 > len(buf):
                    continue
                glyph = struct.unpack(">H", buf[at:at + 2])[0]
                if glyph:
                    glyph = (glyph + delta) & 0xFFFF
            if glyph and glyph not in mapping:
                mapping[glyph] = chr(code)
    return mapping


def _from_format_12(buf: bytes, sub: int) -> dict:
    groups = struct.unpack(">I", buf[sub + 12:sub + 16])[0]
    at = sub + 16
    mapping: dict[int, str] = {}
    for _group in range(groups):
        first, last, glyph = struct.unpack(">III", buf[at:at + 12])
        at += 12
        for step in range(min(last - first, 0xFFFF) + 1):
            if (glyph + step) not in mapping:
                mapping[glyph + step] = chr(first + step)
    return mapping


def glyph_to_unicode(path: Path) -> dict:
    """A real font's character map, inverted: glyph number -> character."""
    buf = path.read_bytes()
    where = _tables(buf).get("cmap")
    if not where:
        return {}
    base = where[0]
    count = struct.unpack(">H", buf[base + 2:base + 4])[0]
    chosen = None
    for index in range(count):
        at = base + 4 + index * 8
        platform, encoding, offset = struct.unpack(">HHI", buf[at:at + 8])
        sub = base + offset
        kind = struct.unpack(">H", buf[sub:sub + 2])[0]
        if kind in (4, 12) and (platform, encoding) in (
                (3, 1), (3, 10), (0, 3), (0, 4), (0, 6)):
            chosen = (kind, sub)
            if kind == 12:
                break
    if chosen is None:
        return {}
    kind, sub = chosen
    return _from_format_4(buf, sub) if kind == 4 else _from_format_12(buf, sub)


def _file(name: str) -> Optional[Path]:
    for folder in FONT_FOLDERS:
        try:
            candidate = folder / name
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _map_for(key: str, name: str) -> dict:
    if key not in _cache:
        path = _file(name)
        try:
            _cache[key] = glyph_to_unicode(path) if path else {}
        except Exception:  # noqa: BLE001 - a font we cannot parse is no use
            _cache[key] = {}
    return _cache[key]


# ------------------------------------------------------------------- repairing


# The punctuation a newspaper's name or a web address actually contains. The
# rest of ASCII - "!", "[", "|", "~" - is rare in a caption and common in a bad
# decode, so counting it as readable is how "!a!w ÜW![!" once scored 0.94
# against the correct "AMAR UJALA AMBALA" and the two could not be told apart.
PLAIN_PUNCTUATION = " .,:;/-_()&'‘’“”–—"

# The characters that are really spacing, as opposed to the ones Python
# merely calls whitespace. 0x1c-0x1f are letters in a glyph-number run -
# glyph 28 is "E" - so stripping by Python's default rule ate the capital
# off "Indian Express".
SPACES = " \t\r\n\xa0"


def readable(text: str) -> float:
    """How much of this reads like a name or an address, 0 to 1.

    Letters, digits and the punctuation those actually use. Deliberately not
    "is it ASCII" and not "is it alphanumeric": decoded through the wrong font
    the glyph numbers come out as Latin Extended - every character of which is a
    letter - or as a spray of ASCII punctuation, and both scored as highly as
    the right answer.
    """
    body = (text or "").strip()
    if not body:
        return 0.0
    good = 0
    for ch in body:
        if ch in PLAIN_PUNCTUATION:
            good += 1
        elif ch.isascii() and ch.isalnum():
            good += 1
    return good / len(body)


def _preferred(fonts: Iterable[str]) -> list[str]:
    """The candidate keys the page's own font names point at, best first."""
    wanted: list[str] = []
    for raw in fonts:
        name = (raw or "").split("+")[-1].replace(" ", "").lower()
        for key, needles in HINTS:
            if any(needle in name for needle in needles) and key not in wanted:
                wanted.append(key)
    return wanted


def repair(text: str, fonts: Iterable[str] = ()) -> str:
    """The words behind a run of glyph numbers, or "" if we cannot be sure.

    ``fonts`` are the font names the page declares. They are a hint, not the
    answer: the names are often anonymised to "CIDFont+F1", and a document can
    set one paragraph in a face it never names. Every candidate is scored and
    the best one has to win clearly.
    """
    body = text or ""
    # Emptiness judged on real spaces only. Python's own idea of whitespace
    # includes 0x1c-0x1f, which here are letters, and "".strip() on a run that
    # begins with one quietly loses it.
    if not body.strip(SPACES):
        return ""

    hinted = _preferred(fonts)
    order = ([(key, name) for key, name in CANDIDATES if key in hinted]
             + [(key, name) for key, name in CANDIDATES if key not in hinted])

    # Grouped by what they SAY, not by which font said it. Five fonts that share
    # a glyph order all decode "Amar Ujala" identically; that is corroboration,
    # and treating it as a tie - which an earlier version did - threw the answer
    # away. What must not happen is two DIFFERENT readings that are equally
    # plausible, and that is what the margin below is guarding.
    readings: dict[str, float] = {}
    for key, name in order:
        mapping = _map_for(key, name)
        if not mapping:
            continue
        # A real space is left alone. The extractor puts ordinary U+0020 between
        # runs, and decoding one as "glyph 32" turned "India, Delhi" into
        # "India,Ě Delhi" - a stray letter in the middle of a name.
        #
        # It is not free: in the ASCII-ordered face, glyph 32 is "=", so a
        # decoded web address reads "?s 20" where it should read "?s=20". That
        # is the right way round to be wrong. Addresses are taken from the
        # page's link annotations, which are stored as plain text and come
        # through perfectly; this decoded text is only ever a caption, and a
        # caption is a newspaper's name, where a lost letter would show.
        out = "".join(" " if ch in SPACES
                      else mapping.get(ord(ch), "�") for ch in body)
        if "�" in out:
            continue                    # a glyph this font does not have
        score = readable(out)
        if key in hinted:
            # The document named this face; that is worth a nudge, no more.
            score = min(1.0, score + 0.01)
        stripped = out.strip()
        readings[stripped] = max(readings.get(stripped, 0.0), score)

    if not readings:
        # No Latin face could even name every glyph in the run. That is what a
        # Hindi masthead looks like from here.
        return repair_hindi(body)
    ranked = sorted(readings.items(), key=lambda pair: pair[1], reverse=True)
    best_text, best_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0

    if best_score < MIN_READABLE:
        return repair_hindi(body)
    if runner_up and best_score - runner_up < MIN_MARGIN:
        # Two different readings, neither clearly right. A caption that might be
        # wrong is worse than one that is missing.
        return ""
    # The glyph stream carries its own spacing as well as the extractor's, so a
    # repaired line arrives with doubled spaces: "The Times of India,  Delhi".
    return " ".join(best_text.split())


# ------------------------------------------------------------------- the Hindi

# The Devanagari faces these documents are set in. The press report's Hindi
# mastheads are Mangal Bold, which is a Windows core font for Hindi and so is on
# every machine the department uses; the others are here because they cost
# nothing to try and a different document may well use one. A wrong one cannot
# win: it has to name every glyph in the run AND read as Hindi.
DEVANAGARI_CANDIDATES = (
    ("mangal-bold", "mangalb.ttf"),
    ("mangal", "mangal.ttf"),
    ("nirmala", "Nirmala.ttf"),
    ("aparajita", "aparaj.ttf"),
    ("kokila", "kokila.ttf"),
    ("utsaah", "utsaah.ttf"),
    ("sanskrit", "Sanskr.ttf"),
)

_deva_cache: dict = {}


def _deva_tables(key: str, name: str):
    """A Devanagari font's character map and its inverted substitutions."""
    if key not in _deva_cache:
        path = _file(name)
        if path is None:
            _deva_cache[key] = None
        else:
            try:
                buf = path.read_bytes()
                _deva_cache[key] = (glyph_to_unicode(path),
                                    devanagari.read_gsub(buf))
            except Exception:  # noqa: BLE001 - unreadable font, no use to us
                _deva_cache[key] = None
    return _deva_cache[key]


def _runs(body: str) -> list:
    """The glyph runs, with the extractor's own spacing taken out."""
    out, current = [], []
    for ch in body:
        if ch in SPACES:
            if current:
                out.append(current)
                current = []
        else:
            current.append(ord(ch))
    if current:
        out.append(current)
    return out


def repair_hindi(text: str) -> str:
    """The Hindi behind a run of glyph numbers, or "" if we cannot be sure.

    Tried only after every Latin candidate has failed, so this cannot disturb a
    caption that already reads. A run is decoded word by word: the reordering
    is per syllable and must not reach across a space.
    """
    body = text or ""
    if not body.strip(SPACES):
        return ""

    readings: dict[str, float] = {}
    for key, name in DEVANAGARI_CANDIDATES:
        tables = _deva_tables(key, name)
        if tables is None:
            continue
        cmap, gsub = tables
        if not cmap:
            continue
        words, whole = [], True
        for run in _runs(body):
            word = devanagari.decode(run, cmap, gsub)
            if word is None:
                whole = False
                break
            words.append(word)
        if not whole:
            continue
        out = " ".join(" ".join(words).split())
        readings[out] = max(readings.get(out, 0.0), devanagari.score(out))

    if not readings:
        return ""
    ranked = sorted(readings.items(), key=lambda pair: pair[1], reverse=True)
    best_text, best_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    if best_score < MIN_READABLE:
        return ""
    if runner_up and best_score - runner_up < MIN_MARGIN:
        return ""
    return best_text
