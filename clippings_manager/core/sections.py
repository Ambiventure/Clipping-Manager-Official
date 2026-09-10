"""The headings that print over a run of clippings, and how they look.

WHAT THIS IS FOR. The 360 Degree document heads two runs - ELECTRONIC MEDIA and
SOCIAL MEDIA - in a red line above the first clipping of each. The application
reproduced those two and nothing else, because they were the only two anybody
had ever seen. Two things were wrong with that.

*   **Digital clippings were heading nothing.** ``Section.DIGITAL`` is not in
    ``SECTION_NAMES``, so both passes of ``section_banners`` skipped it. A
    heading typed onto a Digital clipping was carried, saved, shown on the card
    - and then dropped at export. Measured over the sample corpus: the Lucknow
    document files seven Digital clippings on an ordinary morning and prints no
    heading over any of them.
*   **The list was not the department's to change.** A heading they wanted and
    we had not thought of could not be added at all.

WHY NOT JUST ADD TO ``Section``. Because ``Section`` is two things at once, and
only one of them is about printing:

*   it decides the heading (here);
*   it decides which of the four columns a clipping sits in on the Sentiment
    Board, through ``sentiment.column_for``.

``column_for`` ends ``return Section.NEUTRAL``, and ``session.py`` does the same
for any value it does not recognise. So a new member added for the sake of a
heading would file every clipping carrying it onto Neutral - silently, with no
warning, on the board and again on any older build that opened the session. A
printing choice would quietly move somebody's work.

So the heading is its own field, ``Clip.section_key``, and a plain string. The
board never reads it and cannot be moved by it.

WHY NOT ADD TO ``SECTION_NAMES`` EITHER. It looks like the natural home, and it
is a trap: ``profiles.py`` reads the same dictionary as the "do not split this
caption into paper and city" switch. One dictionary, two unrelated jobs. Add a
word to it and captions start being parsed differently. It is left exactly as it
is, and everything here routes around it.

THE STYLE IS ONE SETTING FOR THE WHOLE REPORT, not one per heading and not one
per clipping. A report with ELECTRONIC MEDIA at 16pt red and SOCIAL MEDIA at
28pt blue is not a report anybody wants to hand to the General Manager, and the
second pass prints a heading over a clipping that was never given one - which
would then have no style of its own to read.

WHAT IS SHIPPED AND WHAT IS THEIRS. Same shape as ``categories.py``: the
defaults live in the program folder and are never written to, and the overlay in
%APPDATA% records CHANGES - what was added, what was removed, what the style was
set to - rather than a snapshot. A later version that ships a fourth default
heading still delivers it to somebody who has added two of their own.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

#: What is shipped. Electronic and Social are the two the 360 Degree document
#: uses; Digital is the one that has been carried and dropped all along.
SHIPPED = (
    ("electronic", "ELECTRONIC MEDIA"),
    ("social", "SOCIAL MEDIA"),
    ("digital", "DIGITAL MEDIA"),
)

#: The red the 360 Degree document heads its runs in.
DEFAULT_COLOUR = "#C00000"

#: 16pt, which is what every report built so far has used. Kept as the default
#: so that a copy nobody has touched prints pages identical to yesterday's.
DEFAULT_SIZE = 16.0

#: The sizes offered. Not a free number box: a heading is one line across the
#: top of a sheet, and above about 30pt a long one stops fitting and MuPDF
#: quietly shrinks it back down - so the size asked for is not the size printed
#: and nothing says so. These all fit.
SIZES = (12.0, 14.0, 16.0, 18.0, 20.0, 24.0, 28.0)

#: Offered on the colour menu. Any hex can be set; these are the ones worth a
#: single click.
COLOURS = (
    ("Report red", "#C00000"),
    ("Black", "#000000"),
    ("Dark blue", "#1F3864"),
    ("Dark green", "#1E5631"),
    ("Grey", "#595959"),
)

_TIDY = re.compile(r"\s+")


def tidy(words: str) -> str:
    """One line, no double spaces, upper case - a heading is a heading."""
    return _TIDY.sub(" ", str(words or "").strip()).upper()


def key_for(words: str) -> str:
    """A stable name for a heading the department typed in themselves.

    Derived from the words rather than counted, so the same heading typed on two
    machines - or typed again after being removed - is the same heading, and a
    clipping carrying it still matches after a setup file is moved across.
    """
    plain = re.sub(r"[^a-z0-9]+", "-", tidy(words).lower()).strip("-")
    return plain or "heading"


# ------------------------------------------------------------------ storage

def _store() -> Path:
    from ..ui.export_dialog import settings_dir

    return settings_dir() / "sections.json"


def _read(path: Path) -> dict:
    try:
        found = json.loads(Path(path).read_text(encoding="utf-8"))
        return found if isinstance(found, dict) else {}
    except Exception:  # noqa: BLE001 - absent, half-written, or not ours
        return {}


def _write(payload: dict) -> None:
    where = _store()
    where.parent.mkdir(parents=True, exist_ok=True)
    # Written beside and moved into place, so a machine that loses power
    # half-way through leaves the old file rather than half a new one.
    temp = where.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    temp.replace(where)


def _mine() -> dict:
    found = _read(_store())
    return {
        "added": [row for row in found.get("added", []) if isinstance(row, dict)],
        "removed": [str(k) for k in found.get("removed", [])],
        "renamed": {str(k): str(v) for k, v
                    in (found.get("renamed") or {}).items()},
        "size": found.get("size"),
        "colour": found.get("colour"),
    }


# -------------------------------------------------------------- the list

class Headings:
    """The headings on offer, in the order they are shown."""

    def __init__(self, rows: list, size: float, colour: str):
        self.rows = rows              # [{"key": ..., "words": ...}]
        self.size = size
        self.colour = colour

    def words_for(self, key: str) -> str:
        for row in self.rows:
            if row["key"] == key:
                return row["words"]
        return ""

    def keys(self) -> list:
        return [row["key"] for row in self.rows]

    def all_words(self) -> list:
        return [row["words"] for row in self.rows]

    def key_of_words(self, words: str) -> str:
        """Which heading these words are, if they are one of ours."""
        wanted = tidy(words)
        for row in self.rows:
            if row["words"] == wanted:
                return row["key"]
        return ""


def load() -> Headings:
    """The shipped headings, with the department's changes laid over them."""
    mine = _mine()
    dropped = set(mine["removed"])
    renamed = mine["renamed"]

    rows, seen = [], set()
    for key, words in SHIPPED:
        if key in dropped:
            continue
        rows.append({"key": key, "words": tidy(renamed.get(key, words))})
        seen.add(key)
    for row in mine["added"]:
        key = str(row.get("key") or key_for(row.get("words", "")))
        if key in dropped or key in seen:
            continue
        words = tidy(renamed.get(key, row.get("words", "")))
        if not words:
            continue
        rows.append({"key": key, "words": words})
        seen.add(key)

    size = mine["size"]
    size = float(size) if isinstance(size, (int, float)) else DEFAULT_SIZE
    colour = mine["colour"] if _is_colour(mine["colour"]) else DEFAULT_COLOUR
    return Headings(rows, size, colour)


def _is_colour(value) -> bool:
    return bool(value) and bool(re.fullmatch(r"#[0-9A-Fa-f]{6}", str(value)))


# ------------------------------------------------------------------ editing

def add(words: str) -> str:
    """Add a heading. Returns its key; adding one that is there is not an error."""
    words = tidy(words)
    if not words:
        raise ValueError("A heading needs some words.")
    key = key_for(words)
    mine = _read(_store())
    # Adding back one that was removed is un-removing it, not a second copy.
    mine["removed"] = [k for k in mine.get("removed", []) if k != key]
    added = [r for r in mine.get("added", []) if isinstance(r, dict)]
    if key not in {r.get("key") for r in added} and key not in dict(SHIPPED):
        added.append({"key": key, "words": words})
    mine["added"] = added
    _write(mine)
    return key


def remove(key: str) -> None:
    """Take a heading off the list.

    Recorded as a removal even for one we shipped, so it stays gone when a later
    version ships the same defaults again - and so that a heading somebody
    deliberately took out does not quietly come back after an update.
    """
    mine = _read(_store())
    mine["added"] = [r for r in mine.get("added", [])
                     if isinstance(r, dict) and r.get("key") != key]
    removed = [k for k in mine.get("removed", []) if k != key]
    removed.append(key)
    mine["removed"] = removed
    _write(mine)


def rename(key: str, words: str) -> None:
    """Change the words a heading prints, keeping clippings pointed at it."""
    words = tidy(words)
    if not words:
        raise ValueError("A heading needs some words.")
    mine = _read(_store())
    renamed = dict(mine.get("renamed") or {})
    renamed[key] = words
    mine["renamed"] = renamed
    _write(mine)


def set_style(size: Optional[float] = None,
              colour: Optional[str] = None) -> None:
    """How every heading in the report is printed."""
    mine = _read(_store())
    if size is not None:
        mine["size"] = float(size)
    if colour is not None:
        if not _is_colour(colour):
            raise ValueError(f"{colour!r} is not a colour like #C00000.")
        mine["colour"] = str(colour).upper()
    _write(mine)


def forget() -> bool:
    """Put everything back the way it was shipped."""
    where = _store()
    if not where.exists():
        return False
    where.unlink()
    return True


def edited() -> bool:
    """Has anything here been changed from what was shipped?"""
    mine = _mine()
    return bool(mine["added"] or mine["removed"] or mine["renamed"]
                or mine["size"] is not None or mine["colour"] is not None)
