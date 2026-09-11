"""Four newspads: where each one lives, and which one is open.

WHAT A NEWSPAD IS. One report in progress, and the look of that report: the
clippings on both screens, the press report's date, the dossier cover's date,
count, division and prepared-by lines - and its two cover pages and the headline
style and paper of both interfaces. Two reports with different titles need two
different covers; that is what four newspads are for. Everything else - the
section headings, the newspaper list, the words kept out, the export folder and
every duplicate decision the program has learned - belongs to the install, and
all four newspads share it.

WHY ONE WINDOW WITH ONE NEWSPAD LOADED, and not four windows. Three designs were
measured against this code, and the one that keeps a single copy of every
settings panel, cache, shortcut and background worker is the only one where
none of these can happen:

*   two copies of a settings panel each saving the whole file, so whichever
    saved last silently undid the other - measured, a heading size of 48 went
    back to 18 and the cover artwork path was wiped;
*   one window's shutdown stopping another window's duplicate check - measured,
    0 of 40 results delivered;
*   two sessions sharing one picture folder deleting each other's pictures.

So a switch saves the outgoing newspad, empties the window, points it at the
incoming newspad's own folder and loads that through the same restore the
program has always used on launch.

WHERE THEY LIVE. Newspad 1 is today's ``session`` folder, untouched - so the
morning on this machine the day this ships comes through as Newspad 1 with
nothing moved. Newspads 2-4 get ``session-2`` to ``session-4``, created the
first time each is opened and never by merely looking.

EACH NEWSPAD'S LOOK is four small files, one per panel - never one file for
all four, which is the measured hazard above. Newspad 1's are cover.json,
sentiment_cover.json, heading_standard.json and heading_sentiment.json in the
settings folder, where every older build reads them. Newspads 2-4 keep the same
four names in ``design-2`` to ``design-4``: beside their session folders, never
inside them, so Start fresh, the tidy-up and setting unreadable work aside
cannot reach them. A newspad with no look of its own is given a copy of the one
on screen the first time it is opened, and only a copy that could be trusted.

NOTHING HERE MAKES A FOLDER. ``session_dir()`` and ``SessionStore()`` both
create folders as a side effect, which is why this module reads paths and files
directly and never calls either. Opening the menu to see what the other three
newspads hold must not leave three empty folders behind.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

#: How many newspads there are. Four, as asked for.
COUNT = 4

#: The file that remembers which newspad was open. Install-wide, never inside a
#: session - an older build rebuilds session.json from scratch when it saves and
#: would drop anything it did not know about.
POINTER = "instances.json"

#: Said in the menu, on the empty-newspad note and in the "what is shared" box,
#: so the answer to "is this shared?" is the same wherever somebody asks it.
WHAT_IS_SHARED = (
    "Each newspad is its own report. It has its own clippings in both "
    "interfaces, its own press report date, its own dossier date, count, "
    "division and prepared-by lines, its board division and report options, "
    "and which screen it was on.\n\n"
    "Each newspad also has its own look: the press report's cover page, the "
    "dossier's cover page, and the headline style and paper of both reports. "
    "A newspad opened for the first time starts with a copy of the look of "
    "the newspad you were in; after that, a change made in one newspad stays "
    "in that newspad.\n\n"
    "Shared by all four - change it in one and it changes in all: the section "
    "headings (their size and colour; their font follows each newspad's "
    "headline style), the newspaper list, words kept out of the report, the "
    "export folder and formats, Check automatically, zoom, and everything the "
    "duplicate check has learned.\n\n"
    "Switching newspads clears undo, filters and selection, the same as "
    "closing the program does.")

#: One line, for the button's tooltip.
SHARED_IN_ONE_LINE = (
    "Four separate reports. Clippings, dates, the dossier's lines, both cover "
    "pages and the headline style and paper are each newspad's own; sections, "
    "the newspaper list, the word list and duplicate learning are shared.")

#: The four files that make a newspad's look, one per panel. The same names in
#: every newspad: Newspad 1's in the settings folder, the others' in design-N.
DESIGN_FILES = ("cover.json", "sentiment_cover.json", "heading_standard.json",
                "heading_sentiment.json")


def root() -> Path:
    """%APPDATA%\\ClippingsManager, resolved exactly as session_dir() does.

    Never created here. See the module note: a path is not a promise to make
    the folder.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA",
                                   Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME",
                                   Path.home() / ".config"))
    return base / "ClippingsManager"


def folder(number: int) -> Path:
    """The session folder that holds this newspad. Nothing is created."""
    number = _clamp(number)
    if number == 1:
        return root() / "session"
    return root() / f"session-{number}"


def design_folder(number: int) -> Path:
    """Where this newspad's look lives. Nothing is created.

    Raises for a number that is not a newspad, rather than clamping it: a
    caller's mistake quietly turned into Newspad 1 would write one report's
    look into another's files, which is exactly what this exists to prevent.
    """
    if not isinstance(number, int) or not 1 <= number <= COUNT:
        raise ValueError(f"there is no newspad {number!r}")
    return root() if number == 1 else root() / f"design-{number}"


def design_file(number: int, name: str) -> Path:
    """One of this newspad's four design files. Nothing is created."""
    if name not in DESIGN_FILES:
        raise ValueError(f"{name!r} is not a design file")
    return design_folder(number) / name


def design_key(number: int, name: str) -> str:
    """How a saved setup names this file: the name for Newspad 1, as every
    older setup did, and design-N/name for the others."""
    return name if design_folder(number) == root() else f"design-{number}/{name}"


def write_design(target: Path, text: str) -> None:
    """Write a design file whole or not at all.

    Written beside and moved into place, after being flushed to the disk, the
    way the pointer and the session manifest are. A settings folder can roam
    over a network and a machine can lose power; a design file left half
    written reads as nothing, and nothing would then be copied into another
    newspad as if it were a design.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + ".part")
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, target)


def _clamp(number) -> int:
    try:
        value = int(number)
    except (TypeError, ValueError):
        return 1
    return value if 1 <= value <= COUNT else 1


def active() -> int:
    """Which newspad was open last. Anything wrong with the file means 1.

    A missing file is the ordinary case on the first launch after an update,
    and it has to mean exactly what the program did before newspads existed:
    open the one session there is.
    """
    try:
        found = json.loads((root() / POINTER).read_text(encoding="utf-8"))
        return _clamp(found.get("active", 1)) if isinstance(found, dict) else 1
    except Exception:  # noqa: BLE001 - missing, half-written, or not ours
        return 1


def remember(number: int) -> None:
    """Record which newspad is open, so the next launch opens the same one.

    Written beside and moved into place, the way the session manifest is, so a
    machine that loses power mid-write keeps the old pointer rather than half a
    new one.
    """
    target = root() / POINTER
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".part")
    body = json.dumps({"version": 1, "active": _clamp(number)}).encode("utf-8")
    with open(temp, "wb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, target)


def summary(number: int) -> Optional[tuple]:
    """(clipping count, when it was last saved) for a newspad not on screen.

    Read straight off its manifest, never by building a SessionStore - that
    would create the folder, and would read every picture's name to no purpose.
    None when the newspad has never been used or its manifest cannot be read.
    """
    path = folder(number) / "session.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    pools = payload.get("pools") or {}
    count = sum(len(pools.get(key) or []) for key in ("standard", "sentiment"))
    when = None
    try:
        when = datetime.fromisoformat(str(payload.get("saved_at", "")))
    except ValueError:
        pass
    return count, when


def describe(number: int, count: Optional[int] = None,
             when: Optional[datetime] = None) -> str:
    """One menu line: "Newspad 2 - 24 clippings · today 09:43"."""
    head = f"Newspad {_clamp(number)}"
    if count is None:
        return head
    if not count:
        return f"{head} — empty"
    said = f"{head} — {count} clipping{'s' if count != 1 else ''}"
    if when is not None:
        if when.date() == datetime.now().date():
            said += f" · today {when:%H:%M}"
        else:
            said += f" · {when:%a} {when.day} {when:%b}"
    return said
