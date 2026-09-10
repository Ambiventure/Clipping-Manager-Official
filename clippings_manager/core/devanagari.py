"""Reading Hindi back out of a PDF that stored it as glyph numbers.

:mod:`glyphmap` recovers Latin captions from these documents by inverting a real
font's character map: glyph 100 is "T" again. Hindi does not come back that
easily, for two reasons, and both have to be dealt with or the answer is wrong
rather than merely missing.

**Half the glyphs have no character map entry at all.** A Devanagari font reaches
its half-forms and conjuncts - म्, ल्, स्, and the reph र् that rides above a
letter - through GSUB, the substitution table a text shaper drives. Those glyphs
are not characters, so no cmap names them. They can be named the other way
round: read GSUB, invert it, and a ligature glyph traces back to the glyphs it
was made from, which the cmap does know.

**The order on the page is not the order in Unicode.** A PDF text layer is in
drawing order. Devanagari draws the short-i sign ि *before* the consonant it
belongs to and stores it *after*; the reph is drawn last and stored first. Read
straight through, "दिल्ली" comes out as "िदल्ली" and "जगमार्ग" as "जगमागर्" -
which look almost right, match nothing, and would quietly fail every name lookup
in the application.

So: name each glyph, note which feature produced it, then put the pieces back
into the order Unicode stores them in.

Nothing here guesses. One glyph the font cannot name and the whole caption is
refused, exactly as :mod:`glyphmap` refuses an uncertain Latin one.
"""

from __future__ import annotations

import struct
import unicodedata
from typing import Iterable, Optional

# The two features that both decode to <RA, VIRAMA> and belong at opposite ends
# of their cluster. Codepoints cannot tell them apart; the feature tag can.
REPH = "rphf"
RAKAR = "blwf"

VIRAMA = "्"
RA = "र"
NUKTA = "़"
PRE_BASE = "ि"                 # the only vowel sign drawn before its letter

BELOW = set("ुूृॄॢॣ")
POST = set("ाीॅॆेैॉॊोौ"
           "ॎॏॕॖॗ")
MARKS = set("ऀँंःऺऻ॒॑॓॔")

DEVANAGARI = range(0x0900, 0x0980)
DOTTED_CIRCLE = "◌"


# --------------------------------------------------------------- sfnt plumbing


def _u16(buf: bytes, at: int) -> int:
    return struct.unpack_from(">H", buf, at)[0]


def _i16(buf: bytes, at: int) -> int:
    return struct.unpack_from(">h", buf, at)[0]


def _u32(buf: bytes, at: int) -> int:
    return struct.unpack_from(">I", buf, at)[0]


def _tables(buf: bytes, face: int = 0) -> dict:
    """Where each sfnt table starts. Kept here rather than borrowed from
    glyphmap so that module can import this one without a circle."""
    if buf[:4] == b"ttcf":
        base = _u32(buf, 12 + 4 * min(face, _u32(buf, 8) - 1))
    else:
        base = 0
    found = {}
    for index in range(_u16(buf, base + 4)):
        at = base + 12 + index * 16
        start, length = struct.unpack_from(">II", buf, at + 8)
        found[buf[at:at + 4].decode("latin-1")] = (start, length)
    return found


def _coverage(buf: bytes, at: int) -> list:
    """Which glyphs a lookup applies to, in coverage-index order."""
    kind = _u16(buf, at)
    if kind == 1:
        return [_u16(buf, at + 4 + i * 2) for i in range(_u16(buf, at + 2))]
    if kind == 2:
        # A RangeRecord is (first, last, startCoverageIndex), and glyph g sits
        # AT index startCoverageIndex + (g - first). Appending the index
        # instead - the obvious mistake - decomposes Mangal's half-sa from
        # glyph 0x18 ("6") rather than glyph 0xa0 (स), which reads as a
        # plausible word and is completely wrong.
        slots = {}
        for i in range(_u16(buf, at + 2)):
            first, last, start = struct.unpack_from(">HHH", buf, at + 4 + i * 6)
            for glyph in range(first, last + 1):
                slots[start + (glyph - first)] = glyph
        return ([slots.get(i, 0) for i in range(max(slots) + 1)]
                if slots else [])
    return []


# ------------------------------------------------------------- reading GSUB


def _subtable(buf: bytes, at: int, kind: int, out: dict, tag: str) -> None:
    if kind == 7:
        # An Extension lookup is only a wrapper round a real one. Mangal wraps
        # all sixty of its lookups this way, so a parser that does not unwrap
        # sees sixty lookups of "type 7" and no substitutions whatsoever.
        _subtable(buf, at + _u32(buf, at + 4), _u16(buf, at + 2), out, tag)
        return

    if kind == 1:                                   # Single
        shape = _u16(buf, at)
        covered = _coverage(buf, at + _u16(buf, at + 2))
        if shape == 1:
            delta = _i16(buf, at + 4)
            for glyph in covered:
                out["single"].setdefault((glyph + delta) & 0xFFFF,
                                         []).append((glyph, tag))
        else:
            count = _u16(buf, at + 4)
            for index, glyph in enumerate(covered):
                if index < count:
                    out["single"].setdefault(_u16(buf, at + 6 + index * 2),
                                             []).append((glyph, tag))

    elif kind == 3:                                 # Alternate
        covered = _coverage(buf, at + _u16(buf, at + 2))
        count = _u16(buf, at + 4)
        for index, glyph in enumerate(covered):
            if index >= count:
                break
            set_at = at + _u16(buf, at + 6 + index * 2)
            for k in range(_u16(buf, set_at)):
                out["single"].setdefault(_u16(buf, set_at + 2 + k * 2),
                                         []).append((glyph, tag))

    elif kind == 4:                                 # Ligature
        covered = _coverage(buf, at + _u16(buf, at + 2))
        count = _u16(buf, at + 4)
        for index, first in enumerate(covered):
            if index >= count:
                break
            set_at = at + _u16(buf, at + 6 + index * 2)
            for k in range(_u16(buf, set_at)):
                lig_at = set_at + _u16(buf, set_at + 2 + k * 2)
                made, parts = _u16(buf, lig_at), _u16(buf, lig_at + 2)
                sequence = [first] + [_u16(buf, lig_at + 4 + n * 2)
                                      for n in range(parts - 1)]
                out["ligature"].setdefault(made, []).append(
                    (tuple(sequence), tag))


def read_gsub(buf: bytes, face: int = 0) -> dict:
    """Inverted substitutions: which glyphs each made-up glyph was made from.

    Every lookup is read, not only the ones a feature points at. Mangal's twelve
    ि width variants and three ी variants live in lookups no feature references
    - Windows' own shaper picks them by index - and two of those orphans are
    exactly what the department's press report uses.
    """
    out: dict = {"single": {}, "ligature": {}}
    try:
        where = _tables(buf, face).get("GSUB")
        if not where:
            return out
        base = where[0]
        features = base + _u16(buf, base + 6)
        lookups = base + _u16(buf, base + 8)

        tag_of: dict = {}
        for i in range(_u16(buf, features)):
            at = features + 2 + i * 6
            tag = buf[at:at + 4].decode("latin-1")
            record = features + _u16(buf, at + 4)
            for k in range(_u16(buf, record + 2)):
                tag_of.setdefault(_u16(buf, record + 4 + k * 2), tag)

        for i in range(_u16(buf, lookups)):
            at = lookups + _u16(buf, lookups + 2 + i * 2)
            kind = _u16(buf, at)
            for k in range(_u16(buf, at + 4)):
                _subtable(buf, at + _u16(buf, at + 6 + k * 2), kind, out,
                          tag_of.get(i, ""))
    except Exception:  # noqa: BLE001 - a font we cannot parse is simply no use
        return {"single": {}, "ligature": {}}
    return out


# ------------------------------------------------------- naming a single glyph


def expand(glyph: int, cmap: dict, gsub: dict, depth: int = 0,
           seen: frozenset = frozenset()) -> Optional[tuple]:
    """(text, feature tag) for one glyph number, or None if nothing names it."""
    if depth > 8:
        return None
    if glyph in cmap:
        return (cmap[glyph], "")            # a real character always wins

    here = seen | {glyph}
    best = None                             # (text, tag, all real, length)

    for sequence, tag in gsub["ligature"].get(glyph, ()):
        parts, direct = [], 0
        for part in sequence:
            if part in here:
                parts = None
                break
            named = expand(part, cmap, gsub, depth + 1, here)
            if named is None:
                parts = None
                break
            parts.append(named[0])
            direct += 1 if part in cmap else 0
        if parts is None:
            continue
        # Prefer the decomposition whose every component is a real character.
        # That is what picks rkrf's <ka, virama, ra> over vatu's <ka, rakar>:
        # the second expands to "ka ra virama" - the right letters in an order
        # that is not a word.
        candidate = ("".join(parts), tag, direct == len(sequence),
                     len("".join(parts)))
        if best is None or (candidate[2], candidate[3]) > (best[2], best[3]):
            best = candidate

    for source, tag in gsub["single"].get(glyph, ()):
        if source in here:
            continue
        named = expand(source, cmap, gsub, depth + 1, here)
        if named is None:
            continue
        candidate = (named[0], named[1] or tag, source in cmap, len(named[0]))
        if best is None or (candidate[2], candidate[3]) > (best[2], best[3]):
            best = candidate

    return (best[0], best[1]) if best else None


def role_of(text: str, tag: str) -> str:
    """What this piece is, for the purpose of putting it back in order."""
    if tag == REPH:
        return "reph"
    if tag == RAKAR:
        return "rakar"
    if not text:
        return "base"
    if text[0] == PRE_BASE:
        return "pre"
    if text[0] in BELOW:
        return "below"
    if text[0] in POST:
        return "post"
    if text[0] in MARKS:
        return "mark"
    if text[0] == NUKTA:
        return "nukta"
    if len(text) >= 2 and text[-1] == VIRAMA:
        return "half"                       # a half letter, drawn before base
    return "base"


# ------------------------------------------------ drawing order to Unicode order


def reorder(atoms: Iterable[tuple]) -> str:
    """[(role, text)] as drawn -> the string Unicode would store.

    One syllable is open at a time. A second base letter, or a pre-base sign
    arriving after a base, closes it. A closed syllable is written out as
    reph, then half letters, then the base, then its nukta, then the short-i,
    then everything else - which is Unicode's own order.
    """
    out: list = []
    open_now: dict = {}

    def start():
        open_now.update(reph="", halves=[], base=None, pre="", tail=[])

    def close():
        if (open_now["base"] is None and not open_now["halves"]
                and not open_now["pre"] and not open_now["tail"]
                and not open_now["reph"]):
            return
        out.append(open_now["reph"] + "".join(open_now["halves"])
                   + (open_now["base"] or "") + open_now["pre"]
                   + "".join(open_now["tail"]))
        start()

    start()
    for role, text in atoms:
        if role in ("pre", "half"):
            if open_now["base"] is not None:
                close()
            if role == "pre":
                open_now["pre"] += text
            else:
                open_now["halves"].append(text)
        elif role == "base":
            if open_now["base"] is not None:
                close()
            open_now["base"] = text
        elif role == "reph":
            open_now["reph"] = text             # <RA, VIRAMA>, already logical
        elif role == "rakar":
            open_now["tail"].append(VIRAMA + RA)   # decoded the other way round
        elif role == "nukta":
            open_now["base"] = (open_now["base"] or "") + text
        else:
            open_now["tail"].append(text)
    close()
    return "".join(out)


def decode(glyphs: Iterable[int], cmap: dict, gsub: dict) -> Optional[str]:
    """Glyph numbers as drawn -> Hindi, or None if any glyph has no name.

    Fails closed, the way :func:`glyphmap.repair` does: a caption that might be
    wrong is worse than one that is missing.
    """
    atoms = []
    for glyph in glyphs:
        named = expand(glyph, cmap, gsub)
        if named is None:
            return None
        atoms.append((role_of(*named), named[0]))
    # Normalised, because the same letter can be spelt two ways - ढ़ is either
    # one codepoint or ढ plus a nukta - and the application looks its
    # newspapers up by name.
    return unicodedata.normalize("NFC", reorder(atoms))


# ----------------------------------------------------- is it really Hindi


CONSONANTS = set(chr(c) for c in range(0x0915, 0x093A))
CONSONANTS |= set(chr(c) for c in range(0x0958, 0x0960))
CONSONANTS |= set(chr(c) for c in range(0x0978, 0x0980))
VOWELS = set(chr(c) for c in range(0x0904, 0x0915))
VOWELS |= {"ॠ", "ॡ"}
VOWELS |= set(chr(c) for c in range(0x0972, 0x0978))
# PRE_BASE belongs here too. It is handled apart when REORDERING, because
# it is the one sign drawn before its letter - but to a reader checking
# whether a word is well formed it is an ordinary vowel sign, and leaving
# it out condemned every word containing दिल्ली or दैनिक.
MATRAS = BELOW | POST | {PRE_BASE, "ऺ", "ऻ"}
SIGNS = set("ऀँंः") | set("॒॑॓॔")
DIGITS = set(chr(c) for c in range(0x0966, 0x0970)) | set("0123456789")
PUNCTUATION = " .,:;/-_()&'‘’“”–—।॥"


def _word_holds_up(word: str) -> bool:
    """Does this parse as Hindi syllables, or only look like Hindi?

    This is the whole difference between a right answer and a confident wrong
    one. Decoded through the wrong Devanagari font, a masthead comes back as
    "य़क्ष्॰ण़्र्" - every character genuinely in the Devanagari block, so
    counting characters scores it 1.00, exactly like the correct "जम्मू".

    What separates them is shape. Hindi is written in syllables:
    half-letters, then a letter, then at most one vowel sign, then marks. That
    string is a half-letter with nothing after it, an abbreviation sign in the
    middle of a word, and a virama hanging off the end - none of which can
    happen in a word anybody has ever printed.
    """
    body = word.strip(PUNCTUATION)
    if not body:
        return True
    if all(ch in DIGITS or ch in PUNCTUATION for ch in body):
        return True                     # "2", a page number, is a fine word
    if any(ord(ch) not in DEVANAGARI for ch in body):
        return False                    # Latin, or a stray combining mark
    if any(ch in DIGITS for ch in body):
        return False                    # digits do not sit inside a word

    at, size = 0, len(body)
    while at < size:
        began = at
        # any number of half-letters: consonant, optional nukta, virama
        while at < size and body[at] in CONSONANTS:
            step = at + 1
            if step < size and body[step] == NUKTA:
                step += 1
            if step < size and body[step] == VIRAMA:
                at = step + 1
                continue
            break
        # then the letter the syllable is built on
        if at < size and body[at] in CONSONANTS:
            at += 1
            if at < size and body[at] == NUKTA:
                at += 1
        elif at < size and body[at] in VOWELS:
            at += 1
        else:
            return False                # a virama with nothing after it
        # at most one vowel sign, then any marks
        if at < size and body[at] in MATRAS:
            at += 1
        while at < size and body[at] in SIGNS:
            at += 1
        if at == began:
            return False
    return True


def well_formed(text: str) -> bool:
    """Every word of it reads as Hindi."""
    return all(_word_holds_up(word) for word in (text or "").split())


def score(text: str) -> float:
    """How much of this reads as Hindi, 0 to 1.

    A dotted circle is the shaper's way of saying "this mark has nothing to
    attach to", so its presence means the order came out wrong even if every
    letter is right.
    """
    body = (text or "").strip()
    if not body or DOTTED_CIRCLE in body:
        return 0.0
    letters = sum(1 for ch in body if ord(ch) in DEVANAGARI)
    if letters < 2:
        return 0.0
    if not well_formed(body):
        # Devanagari-shaped, but not Hindi. This is what a wrong font produces,
        # and character-counting alone cannot tell it from the right answer.
        return 0.0
    good = sum(1 for ch in body
               if ord(ch) in DEVANAGARI or ch.isspace()
               or ch in " .,:;/-_()&'‘’“”–—")
    return good / len(body)
