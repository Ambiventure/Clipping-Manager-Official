"""PaddleOCR and Tesseract, one headline: the better of the two, word by word.

Both engines read the same region - the one OpenCV found (core/headfind) - and
they go wrong in different ways, which is why the two together beat either:

  * PaddleOCR drops the marks of Devanagari. The र् that sits over a letter,
    the anusvara, a matra: "ट्रेनें" comes back "ट्रनें" or "ट्ेनें",
    "यार्ड" as "या्ड", "में" as "मे". Many of those cannot even be written -
    a virama after a vowel sign is not Devanagari. It also runs words
    together ("मेंडूबी") and adds scraps of noise ("ऋ", "उ", "s").
  * Tesseract turns whole Hindi words into English letters - "ve" for रद्द,
    "fequar" for टिप्पण, "zens" for स्टाफ - reads ठ for ट, and invents words
    in the edges of photographs.

So PaddleOCR reads first and Tesseract reads the same region, and where the
two disagree the word that can be written, is a real word, and was read
surely is kept. Measured on the office's own headlines where the two
disagreed, each checked by eye against the print, the whole reader start to
finish: of 140, Tesseract alone (2.0.57) read 71 exactly right and the two
together 110, letters wrong falling from 4.0 in a hundred to 1.1; and of 40
more cuttings, held back while these rules were made, 12 against 25, 7.1
letters in a hundred against 2.0 - better on 22, worse on none. PaddleOCR
alone read 31 of the 140 exactly: on its own it is the worse reader of
Hindi, and together the better one.

The real words are Tesseract's own word lists (langdata_lstm, Apache 2.0) -
the words its dictionary was built from - kept in assets/ppocr.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

WORDS = Path(__file__).resolve().parent.parent / "assets" / "ppocr"


@dataclass
class Word:
    """One word of a reading, as normalised, and how sure its engine was."""

    text: str
    sure: float = 0.0


#: A word read this unsurely loses to one read this surely, whatever else is
#: said for it: a real word read at 0.29 is a coincidence ("रोना" for
#: "फिरोजपुर", "यार" for "यार्ड").
DOUBTFUL = 0.5
CONFIDENT = 0.75
#: A word only Tesseract saw is kept at this certainty or more - PaddleOCR's
#: detector finds type in noise well, so what it did not see is usually the
#: edge of a photograph ("एटा" at 0.40 over a masthead).
T_ALONE = 0.6
#: A word only PaddleOCR saw is kept at this certainty or more, and with at
#: least two letters: its lone letters are noise.
P_ALONE = 0.5


# ------------------------------------------------------------ the letters
def kind(ch: str) -> str:
    """C consonant, V vowel, M vowel sign, H virama, N nukta, B bindu or
    visarga, D figure, L Latin letter, Z joiner, O other Devanagari, P the
    rest."""
    o = ord(ch)
    if 0x0915 <= o <= 0x0939 or 0x0958 <= o <= 0x095F or 0x0978 <= o <= 0x097F:
        return "C"
    if 0x0904 <= o <= 0x0914 or 0x0960 <= o <= 0x0961 or 0x0972 <= o <= 0x0977:
        return "V"
    if (0x093E <= o <= 0x094C or 0x094E <= o <= 0x094F or 0x0955 <= o <= 0x0957
            or 0x0962 <= o <= 0x0963 or 0x093A <= o <= 0x093B):
        return "M"
    if o == 0x094D:
        return "H"
    if o == 0x093C:
        return "N"
    if 0x0900 <= o <= 0x0903:
        return "B"
    if 0x0966 <= o <= 0x096F or ch.isdigit():
        return "D"
    if o in (0x200C, 0x200D):
        return "Z"
    if 0x0900 <= o <= 0x097F:
        return "O"
    if ch.isalpha():
        return "L"
    return "P"


def well_formed(word: str) -> bool:
    """Could this be written in Devanagari at all? A virama follows only a
    consonant, a vowel sign only a consonant, a nukta only a consonant, and a
    bindu never starts a word. Latin, figures and punctuation pass."""
    before = ""
    for ch in word:
        k = kind(ch)
        if k == "H" and before not in ("C", "N"):
            return False
        if k == "M" and before not in ("C", "N", "Z"):
            return False
        if k == "N" and before != "C":
            return False
        if k == "B" and before not in ("C", "N", "M", "V", "B"):
            return False
        if k != "Z":
            before = k
    return True


def _devanagari(text: str) -> int:
    return sum(1 for ch in text if "ऀ" <= ch <= "ॿ")


def _latin(text: str) -> int:
    return sum(1 for ch in text if ch.isascii() and ch.isalpha())


_PARTS = re.compile(r"[^\wऀ-ॿ]+")


def _parts(text: str) -> list:
    """The words inside a token: "अमृतसर-मुंबई'वंदे" holds three."""
    return [p for p in _PARTS.split(text) if p]


def _squeezed(words) -> str:
    return "".join(ch for w in words for ch in w.text if kind(ch) not in "PZ")


def _base(words) -> str:
    return "".join(ch for w in words for ch in w.text if kind(ch) in "CVDL")


def _marks(words) -> int:
    return sum(1 for w in words for ch in w.text if kind(ch) in "MHNB")


# ------------------------------------------------------------- the words
_lexicon = None


def lexicon():
    """(the words, each word's place in its list - its commonness)."""
    global _lexicon
    if _lexicon is None:
        ranks = {}
        for name in ("words-hin.txt", "words-eng.txt"):
            try:
                listed = (WORDS / name).read_text(encoding="utf-8").split()
            except OSError:
                listed = []
            for place, word in enumerate(listed):
                word = unicodedata.normalize("NFC", word).lower()
                ranks.setdefault(word, place)
        _lexicon = ranks
    return _lexicon


def _known(part: str, hindi: bool) -> bool:
    if hindi and _latin(part):
        return False        # English letters prove nothing in a Hindi headline
    return part in lexicon()


def _known_share(words, hindi: bool) -> float:
    pieces = [p for w in words for p in _parts(w.text)]
    total = sum(len(p) for p in pieces)
    if not total:
        return 0.0
    return sum(len(p) for p in pieces if _known(p, hindi)) / total


def _rarest(words) -> int:
    ranks = lexicon()
    places = [ranks.get(p, 10 ** 6) for w in words for p in _parts(w.text)]
    return max(places) if places else 10 ** 6


def _scrap(word: Word, hindi: bool) -> bool:
    """A lone letter, figure or sign that noise was read as."""
    letters = "".join(_parts(word.text))
    if not letters:
        return True
    if not any(kind(ch) in "CVL" for ch in letters) and not (
            letters.isdigit() and len(letters) > 1):
        return True
    if hindi and _latin(letters) and len(letters) <= 2:
        return True
    return len(letters) == 1 and kind(letters) in "LD"


def _junk(word: Word, hindi: bool) -> bool:
    """Tesseract's reading of ink that is not type: mostly punctuation,
    English letters in a Hindi headline, or a word that cannot be written."""
    letters = "".join(_parts(word.text))
    if len(letters) * 2 < len(word.text):
        return True
    if hindi and _latin(letters) > _devanagari(letters):
        return True
    return not well_formed(word.text)


def _surest(words) -> float:
    return min((w.sure for w in words), default=0.0)


def _letters(word: Word) -> int:
    return sum(1 for ch in word.text if kind(ch) in "CVLD")


# ------------------------------------------------------------- choosing
def _clean(words: list, hindi: bool) -> bool:
    """Every word can be written and none is a scrap, half its letters are
    real words, and in a Hindi headline it is Devanagari."""
    if not words or any(not well_formed(w.text) or _scrap(w, hindi) for w in words):
        return False
    if hindi and sum(_latin(w.text) for w in words) > sum(_devanagari(w.text) for w in words):
        return False
    return _known_share(words, hindi) >= 0.5


#: At most this many letters cut off the end of a word - a syllable.
CUT_OFF = 3

#: A stretch this many times the other's letters, and clean, is the one that
#: saw the words: "400 यात्रियों का सुरक्षित परिवहन सुनिश्चित" against
#: Tesseract's lone "और" in a line it read as junk.
FULLER = 2.0


def _key(word: Word) -> str:
    return "".join(_parts(word.text))


def _choose(t: list, p: list, hindi: bool, seen: frozenset = frozenset()) -> list:
    """One stretch the two read differently: Tesseract's words or Paddle's.
    ``seen`` is every word of PaddleOCR's whole reading."""
    if not p:
        # A word Paddle read elsewhere in the headline is Tesseract reading
        # it twice: "...की करवाई 44 मालगाड़ियों की करवाई लोडिंग". When half
        # the stretch is such words, all of it is the second reading - its
        # "44" too, a garbled copy of the "14" before it.
        if 2 * sum(1 for w in t if _key(w) in seen) >= len(t):
            return []
        return [w for w in t if not _junk(w, hindi) and w.sure >= T_ALONE
                and _letters(w) >= 2 and _key(w) not in seen]
    if not t:
        kept = [w for w in p if not _scrap(w, hindi) and well_formed(w.text)
                and w.sure >= P_ALONE and _letters(w) >= 2]
        if hindi:
            kept = [w for w in kept if _devanagari(w.text) >= _latin(w.text)]
        return kept
    # The same letters with the spaces in different places: the way that
    # makes real words ("में डूबी", "ट्रेन मैनेजर"); else the more words,
    # since both engines run words together far more than they split them.
    if _squeezed(t) == _squeezed(p):
        t_known, p_known = _known_share(t, hindi), _known_share(p, hindi)
        if t_known != p_known:
            return t if t_known > p_known else p
        return t if len(t) >= len(p) else p
    # Where both put a space at the same letter, the stretch is two
    # stretches: "में हिंदी fequar" against "मेंहिंदी टिप्पण" is the spacing
    # of the first two words and then a word apiece - decided together, the
    # real words of the first half carried Tesseract's "fequar" in with them.
    pieces = _split_where_both_break(t, p)
    if len(pieces) > 1:
        out = []
        for t_piece, p_piece in pieces:
            out += _choose(t_piece, p_piece, hindi, seen)
        return out
    # As many words each: word against word.
    if len(t) == len(p) and len(t) > 1:
        out = []
        for one, other in zip(t, p):
            out += _choose([one], [other], hindi, seen)
        return out
    if hindi:
        t_english = sum(_latin(w.text) for w in t) > sum(_devanagari(w.text) for w in t)
        p_english = sum(_latin(w.text) for w in p) > sum(_devanagari(w.text) for w in p)
        if t_english != p_english:
            return p if t_english else t
    t_bad = sum(1 for w in t if not well_formed(w.text))
    p_bad = sum(1 for w in p if not well_formed(w.text))
    if t_bad != p_bad:
        return p if t_bad > p_bad else t
    t_scraps = sum(1 for w in t if _scrap(w, hindi))
    p_scraps = sum(1 for w in p if _scrap(w, hindi))
    if t_scraps != p_scraps:
        return p if t_scraps > p_scraps else t
    t_long, p_long = len(_squeezed(t)), len(_squeezed(p))
    if p_long >= FULLER * max(1, t_long) and _clean(p, hindi):
        return p
    if t_long >= FULLER * max(1, p_long) and _clean(t, hindi):
        return t
    t_sure, p_sure = _surest(t), _surest(p)
    if t_sure < DOUBTFUL and p_sure >= CONFIDENT:
        return p
    if p_sure < DOUBTFUL and t_sure >= CONFIDENT:
        return t
    # One is the other with its ending cut off - "पहुंचा" for "पहुंचाया",
    # "छूट" for "छूटा", "जुटी" for "जुटीं": the engines drop a word's
    # grammatical ending, a vowel sign or a bindu, far more often than they
    # invent one. A bare letter added is not an ending: Tesseract's "लोगज"
    # for "लोग" is the next word's first letter.
    t_text, p_text = _squeezed(t), _squeezed(p)
    if t_text != p_text and (t_text.startswith(p_text) or p_text.startswith(t_text)):
        longer, shorter = (t, p) if len(t_text) > len(p_text) else (p, t)
        ending = _squeezed(longer)[len(_squeezed(shorter)):]
        if (len(ending) <= CUT_OFF
                and (any(kind(ch) in "MB" for ch in ending)
                     or all(kind(ch) == "L" for ch in ending))
                and all(well_formed(w.text) for w in longer)
                and _surest(longer) >= CONFIDENT):
            return longer
    if not hindi:
        # English: PaddleOCR's own certainty is the better guide - Tesseract
        # reads "sp!" for "Spl" and "itr" for "ltr" sure of itself.
        return p if p_sure >= t_sure else t
    t_known, p_known = _known_share(t, hindi), _known_share(p, hindi)
    if t_known != p_known:
        return t if t_known > p_known else p
    # The same letters, Tesseract's with more marks on them: PaddleOCR drops
    # marks far more often than Tesseract invents them.
    if _base(t) == _base(p) and _marks(t) > _marks(p):
        return t
    if t_known == 1.0:
        t_rank, p_rank = _rarest(t), _rarest(p)
        if t_rank != p_rank:
            return t if t_rank < p_rank else p
    return p if p_sure > t_sure else t


def _split_where_both_break(t: list, p: list) -> list:
    """[(Tesseract's words, Paddle's words)], cut wherever both readings end
    a word at the same letter - the letters matched up by difflib, on
    either side of the break."""
    def ends(words):
        at, found = 0, []
        for word in words[:-1]:
            at += len("".join(ch for ch in word.text if kind(ch) not in "PZ"))
            found.append(at)
        return found

    after, before = {}, {}
    match = difflib.SequenceMatcher(None, _squeezed(t), _squeezed(p),
                                    autojunk=False)
    for op, i1, i2, j1, j2 in match.get_opcodes():
        if op == "equal":
            for step in range(i2 - i1):
                after[i1 + step + 1] = j1 + step + 1    # just after a matched letter
                before[i1 + step] = j1 + step           # just before one
    p_ends = ends(p)
    cuts = []
    for ti, t_end in enumerate(ends(t)):
        for pi, p_end in enumerate(p_ends):
            if after.get(t_end) == p_end or before.get(t_end) == p_end:
                if not cuts or (ti > cuts[-1][0] and pi > cuts[-1][1]):
                    cuts.append((ti, pi))
    if not cuts:
        return [(t, p)]
    pieces, t_from, p_from = [], 0, 0
    for ti, pi in cuts:
        pieces.append((t[t_from:ti + 1], p[p_from:pi + 1]))
        t_from, p_from = ti + 1, pi + 1
    pieces.append((t[t_from:], p[p_from:]))
    return [(a, b) for a, b in pieces if a or b]


def merge(t_words: list, p_words: list) -> list:
    """Tesseract's words and PaddleOCR's for one region, as one reading.

    Where the two agree, the word stands, as sure as the surer of them;
    where they do not, _choose decides. Either list may be empty, and the
    other is then the reading as it is.
    """
    if not p_words:
        return list(t_words)
    if not t_words:
        return list(p_words)
    both = " ".join(w.text for w in list(t_words) + list(p_words))
    hindi = _devanagari(both) >= _latin(both)

    seen = frozenset(_key(w) for w in p_words)
    match = difflib.SequenceMatcher(None, [_key(w) for w in t_words],
                                    [_key(w) for w in p_words], autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in match.get_opcodes():
        if op == "equal":
            for one, other in zip(t_words[i1:i2], p_words[j1:j2]):
                out.append(Word(one.text, max(one.sure, other.sure)))
        else:
            out += _choose(list(t_words[i1:i2]), list(p_words[j1:j2]), hindi, seen)
    return out

