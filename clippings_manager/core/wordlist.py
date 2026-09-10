"""Words the department does not want appearing in a printed report.

WHAT IT CAN REACH, AND WHAT IT CANNOT. This is the part to be honest about,
because the obvious expectation is wrong and quietly so.

A report is a page of PICTURES. The story is inside the JPEG - it is a
photograph of newsprint, and nothing in this program reads the words in it. What
the program prints as TEXT is a short list:

*   the caption or headline under each clipping;
*   the section heading over the first clipping of a run;
*   the two lines on the cover.

That is the whole of what a word list can act on. A word in the body of an
article is in the picture, and taking it out would mean editing a photograph.
Measured on a real morning: a plausible twenty-three word list of subject words
matched none of a hundred and forty-two clippings, because none of those words
were ever in the text the program prints. The screen says so in as many words,
so nobody adds a list and assumes a report has been cleaned when it has not.

THE ADDRESS IS NEVER TOUCHED. Two independent reasons, both measured. A real
Bhaskar link contains "news" and "local" as whole words, so an ordinary list
would silently break the address. And a shortened address rewraps: the report
draws every link at exactly 12.5pt and MuPDF quietly shrinks one that no longer
fits its box, so the addresses that changed would also be the ones printed
smaller, with nothing said.

IT IS NEVER SILENT. This is the thing that makes the feature safe rather than
dangerous. A list that edits text at drawing time and writes nothing back is
invisible by construction: the card is unchanged, the session is unchanged,
there is nothing on the undo stack, and the printed page simply has a hole in it
that nobody can find again. So:

*   an EMPTY list changes not one byte of the report - the code path is not
    entered at all;
*   a list that changed anything says so at export, with the count, before the
    file is written;
*   what was changed can be listed clipping by clipping;
*   nothing is ever written back to the clipping. Clearing the list puts every
    word back, because they were never taken away in the first place.

WHOLE WORDS ONLY. "Man" must not be cut out of the middle of "Manager", and a
Devanagari conjunct must not be split down the middle. Matching is on word
boundaries, the comparison is case-insensitive, and Devanagari text is left
whole unless the whole word matches.

NOTHING IS SHIPPED IN THE LIST. It starts empty. Which words a government
department considers non-inclusive is theirs to decide and not ours to guess.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

#: Nothing. See the note above - this list is the department's own.
SHIPPED: tuple = ()

#: What a run of one or more removed words is replaced with. Nothing: the
#: word goes and the spaces around it are closed up.
_TIDY = re.compile(r"[ \t ]{2,}")
#: "Amar Ujala, Ambala, Page 1" with "Ambala" on the list printed
#: "Amar Ujala,, Page 1". The backreference matters: a repeat of the SAME mark
#: is the hole where a word used to be, whereas ", ;" is two different marks and
#: collapsing those would be a guess about what somebody meant.
_RUN = re.compile(r"([,;:])(?:\s*\1)+")
_LOOSE_PUNCT = re.compile(r"\s+([,;:.!?)\]])")
_OPEN_PUNCT = re.compile(r"([(\[])\s+")


def _store() -> Path:
    from ..ui.export_dialog import settings_dir

    return settings_dir() / "wordlist.json"


def _read() -> dict:
    try:
        found = json.loads(_store().read_text(encoding="utf-8"))
        return found if isinstance(found, dict) else {}
    except Exception:  # noqa: BLE001 - absent, half-written, or not ours
        return {}


def _write(payload: dict) -> None:
    where = _store()
    where.parent.mkdir(parents=True, exist_ok=True)
    temp = where.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    temp.replace(where)


def tidy(word: str) -> str:
    """One word or phrase, no surrounding space, no doubled spaces inside."""
    return _TIDY.sub(" ", str(word or "").replace("\n", " ").strip())


def load() -> list:
    """The words, in the order they were added."""
    found = _read()
    out, seen = [], set()
    for word in list(SHIPPED) + list(found.get("words") or []):
        word = tidy(word)
        folded = word.casefold()
        if word and folded not in seen:
            out.append(word)
            seen.add(folded)
    dropped = {tidy(w).casefold() for w in (found.get("removed") or [])}
    return [w for w in out if w.casefold() not in dropped]


def add(word: str) -> None:
    word = tidy(word)
    if not word:
        raise ValueError("Type a word first.")
    found = _read()
    words = [tidy(w) for w in (found.get("words") or [])]
    if word.casefold() not in {w.casefold() for w in words}:
        words.append(word)
    found["words"] = words
    found["removed"] = [w for w in (found.get("removed") or [])
                        if tidy(w).casefold() != word.casefold()]
    _write(found)


def remove(word: str) -> None:
    word = tidy(word)
    found = _read()
    found["words"] = [w for w in (found.get("words") or [])
                      if tidy(w).casefold() != word.casefold()]
    # Recorded as a removal as well, so that a word taken out deliberately
    # stays out if a later version ever ships a default list.
    removed = [w for w in (found.get("removed") or [])
               if tidy(w).casefold() != word.casefold()]
    removed.append(word)
    found["removed"] = removed
    _write(found)


def forget() -> bool:
    where = _store()
    if not where.exists():
        return False
    where.unlink()
    return True


# ------------------------------------------------------------- the matching

#: What counts as "still inside a word" on either side of a match.
#:
#: THE FAULT THIS FIXES, which could damage a printed page. Python's \\b
#: is defined on \\w, and \\w does NOT include a Devanagari vowel sign -
#: those are combining marks, category Mn and Mc. So a listed Hindi word
#: sitting inside a longer one matched anyway, the cut landed between a
#: consonant and the matra belonging to it, and what printed was U+25CC, a
#: dotted circle where a letter should be. On the burned-JPEG path that is
#: baked into the picture and cannot be undone by taking the word off the
#: list again.
#:
#: Gurmukhi is here for the same reason, before anybody trips over it:
#: Ambala and Ferozpur carry Punjabi papers and its matras break in exactly
#: the same way. There is no Gurmukhi in the sample documents, so that half
#: is reasoned rather than measured - written down here rather than left to
#: be discovered by a broken report.
_JOINS = (r"\w"
          r"\u0900-\u0903\u093a-\u094f\u0951-\u0957\u0962-\u0963"
          r"\u0a01-\u0a03\u0a3c-\u0a51"
          r"\ua8e0-\ua8ff\u1cd0-\u1cff"
          r"\u200c\u200d")
_JOINS_ONE = re.compile(f"[{_JOINS}]")


def _boundary(word: str) -> re.Pattern:
    """A pattern matching this word only where it stands as a word.

    See _JOINS above for why this is not \\b. The short version: \\b cannot
    see a Devanagari matra, so it calls the middle of a Hindi word a
    boundary and the report prints a broken letter.

    Where a "word" is really a phrase, the spaces inside it are allowed to
    be any run of space, because a caption read out of a document can carry
    a non-breaking space where a plain one is expected.
    """
    parts = [re.escape(bit) for bit in tidy(word).split(" ") if bit]
    if not parts:
        return re.compile(r"(?!)")          # matches nothing
    middle = r"[\s ]+".join(parts)
    # A leading or trailing character that cannot join a word needs no
    # guard - "Sr. No." would never match if it had one, because "." is not
    # a word character. Tested with _JOINS_ONE and NOT _wordish, and that is
    # the half that saves a Hindi word ending in a matra: such a word ends
    # in a combining mark, which _wordish calls punctuation, so it was given
    # no guard on its right and matched happily inside longer words.
    said = tidy(word)
    start = f"(?<![{_JOINS}])" if _JOINS_ONE.match(said[0]) else ""
    end = f"(?![{_JOINS}])" if _JOINS_ONE.match(said[-1]) else ""
    return re.compile(start + middle + end, re.IGNORECASE | re.UNICODE)


def _wordish(character: str) -> bool:
    return unicodedata.category(character)[0] in ("L", "N")


class Sieve:
    """Built once per report, then asked about each line.

    Built once because compiling a dozen patterns for every caption on a
    two-hundred clipping morning is work nobody needs doing twice, and because
    an empty list has to cost exactly nothing: `holds_nothing` is checked by
    the exporters before any of this is entered at all.
    """

    def __init__(self, words=None):
        self.words = [w for w in (load() if words is None else
                                  [tidy(w) for w in words]) if w]
        self.patterns = [(w, _boundary(w)) for w in self.words]
        self.changed = 0            # how many lines this sieve altered
        self.hits: dict = {}        # word -> how many times it was taken out

    @property
    def holds_nothing(self) -> bool:
        return not self.patterns

    def clean(self, text: str) -> str:
        """The line as it should print. Never used on an address."""
        if not text or self.holds_nothing:
            return text
        out = text
        for word, pattern in self.patterns:
            out, count = pattern.subn("", out)
            if count:
                self.hits[word] = self.hits.get(word, 0) + count
        if out == text:
            return text
        self.changed += 1
        return _neaten(out)

    def would_change(self, text: str) -> list:
        """Which words are in this line, without changing it."""
        if not text or self.holds_nothing:
            return []
        return [word for word, pattern in self.patterns
                if pattern.search(text)]


def _neaten(text: str) -> str:
    """Close up the hole a removed word leaves behind."""
    out = _TIDY.sub(" ", text)
    # Before the space-tidying, because taking a word out from between two
    # commas leaves ", ," and the run has to be seen as a run.
    out = _RUN.sub(r"\1", out)
    out = _LOOSE_PUNCT.sub(r"\1", out)
    out = _OPEN_PUNCT.sub(r"\1", out)
    # A line that is now nothing but punctuation is not a caption.
    if not any(_wordish(ch) for ch in out):
        return ""
    return out.strip(" \t -–—,;:")
