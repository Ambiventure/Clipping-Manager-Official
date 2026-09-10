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

def _boundary(word: str) -> re.Pattern:
    """A pattern matching this word only where it stands as a word.

    ``\\b`` is defined on word characters, and Python's ``re`` counts Devanagari
    letters as word characters - so this works for Hindi as well, and a word
    inside a longer Hindi word is left alone exactly as an English one is.

    Where a "word" is really a phrase, the spaces inside it are allowed to be
    any run of space, because a caption read out of a document can carry a
    non-breaking space where a plain one is expected.
    """
    parts = [re.escape(bit) for bit in tidy(word).split(" ") if bit]
    if not parts:
        return re.compile(r"(?!)")          # matches nothing
    middle = r"[\s ]+".join(parts)
    # A leading or trailing character that is not a letter or digit does not
    # need a boundary before or after it - "Sr. No." would never match if it
    # did, because "." is not a word character.
    start = r"\b" if _wordish(tidy(word)[0]) else ""
    end = r"\b" if _wordish(tidy(word)[-1]) else ""
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
    out = _LOOSE_PUNCT.sub(r"\1", out)
    out = _OPEN_PUNCT.sub(r"\1", out)
    # A line that is now nothing but punctuation is not a caption.
    if not any(_wordish(ch) for ch in out):
        return ""
    return out.strip(" \t -–—,;:")
