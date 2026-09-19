"""The newspaper and city lists Collect reads captions against: the ones that
come with the program, and what somebody has added to them, changed or taken off.

Collect from WhatsApp names a photo from its caption only when the caption
starts with a newspaper on the list (core/copied.py). The list that comes with
the program is Northern Railway's papers, and a paper from any other state was
refused until somebody typed its name by hand - and typed it again the next
morning, because a name typed by hand lasted only until the program closed.
Manage Newspaper List, on Collect's right-click menu, is where the list is
looked through and added to, and what is done there is kept.

WHAT IS KEPT IS WHAT A PERSON DID, NEVER THE WHOLE LIST. newspaper_list.json in
the settings folder holds the papers and cities added, the ones changed and the
ones taken off. The list that comes with the program is read fresh each time
and those changes are laid over it, so a paper a later version adds still
arrives, and a name somebody changed stays changed. It is one list for the
whole program - every newspad, both interfaces - and it survives closing,
updating and restarting. The file travels with "Save my setup to a file"
(core/backup.py), like every other thing a person set.

NOT A SESSION SETTING. Collect's options last until the program closes on
purpose (ui/collect_options.py): "every photo today is Dainik Jagran, Lucknow"
is this morning's fact and would mis-name tomorrow's clippings. This is the
other kind of thing - which newspapers exist and how people spell them - and
that is as true tomorrow as it is today.

A NAME TYPED INTO A CLIPPING IS STILL NOT WRITTEN HERE. The review list adds
what is typed into a Newspaper box to the reader's list for the session
(NameIndex.add_newspaper), and that stays a session's: a typing slip saved for
good would be read as a newspaper every morning after. Only this editor writes
the file.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .profiles import CONFIG_DIR

#: In the settings folder, beside the other things a person set.
FILE = "newspaper_list.json"

#: The two lists, as this module calls them -> as newspapers.json calls them.
KINDS = {"newspapers": "newspapers", "cities": "editions"}

#: What a spelling is split on when several are typed into one box.
SEPARATORS = (",", ";", "،")


@dataclass(frozen=True)
class Entry:
    """One newspaper or city: the name that prints, and the other ways it is
    typed. ``was`` is its name on the list that came with the program, or ""
    for one added here - which is how a change is told from an addition."""

    name: str
    aliases: tuple = ()
    was: str = ""


# ------------------------------------------------------------------ cleaning
def clean_name(text) -> str:
    """A name with its spacing tidied: " Amar  Ujala " is "Amar Ujala"."""
    return " ".join(str(text or "").split())


def _key(text) -> str:
    return clean_name(text).casefold()


def split_spellings(text) -> list:
    """"अमर उजाला, Amarujala; AU" - the spellings typed into one box."""
    text = str(text or "")
    for mark in SEPARATORS[1:]:
        text = text.replace(mark, SEPARATORS[0])
    return [clean_name(part) for part in text.split(SEPARATORS[0]) if clean_name(part)]


def clean_aliases(values, name: str = "") -> tuple:
    """The other spellings, each once, none the same as the name itself."""
    if isinstance(values, str):
        values = split_spellings(values)
    seen = {_key(name)} if name else set()
    kept = []
    for value in values or ():
        if not isinstance(value, str):
            continue
        spelling = clean_name(value)
        if spelling and _key(spelling) not in seen:
            seen.add(_key(spelling))
            kept.append(spelling)
    return tuple(kept)


def spellings_text(aliases: Iterable[str]) -> str:
    return ", ".join(aliases)


# ------------------------------------------------------------ the two sources
def shipped(kind: str, path: Optional[Path] = None) -> list:
    """The list that came with the program, as it is on disk now."""
    try:
        data = json.loads(Path(path or CONFIG_DIR / "newspapers.json")
                          .read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - no list, nothing to lay changes over
        return []
    out = []
    for item in data.get(KINDS[kind]) or []:
        if isinstance(item, dict):
            name, aliases = clean_name(item.get("name")), item.get("aliases") or []
        else:
            name, aliases = clean_name(item), []
        if name:
            # Kept exactly as the file has them: an entry nobody touched must
            # compare equal to itself, or opening and saving the editor would
            # record a change nobody made.
            out.append(Entry(name, tuple(a for a in aliases if isinstance(a, str)), name))
    return out


def folder() -> Path:
    from ..ui.export_dialog import settings_dir

    return settings_dir()


def where(place: Optional[Path] = None) -> Path:
    return Path(place or folder()) / FILE


def _blank() -> dict:
    return {"added": [], "changed": [], "removed": []}


def load_changes(place: Optional[Path] = None) -> dict:
    """{kind: {"added": [...], "changed": [...], "removed": [...]}} from the
    file, or nothing changed when there is no file or it cannot be read - the
    list that came with the program is then the list, as before this existed."""
    out = {kind: _blank() for kind in KINDS}
    try:
        data = json.loads(where(place).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - never set, or unreadable
        return out
    if not isinstance(data, dict):
        return out
    for kind in KINDS:
        part = data.get(kind)
        if not isinstance(part, dict):
            continue
        for bit in ("added", "changed", "removed"):
            rows = part.get(bit)
            if isinstance(rows, list):
                out[kind][bit] = [row for row in rows
                                  if isinstance(row, (dict, str))]
    return out


# ------------------------------------------------------------------ merging
def _find(order: list, name: str) -> int:
    key = _key(name)
    return next((at for at, entry in enumerate(order) if _key(entry.name) == key), -1)


def _put(order: list, entry: Entry, at: int = -1) -> None:
    """Into the list by name, whatever its case. ``at`` is the place of the
    entry this one replaces; a name already elsewhere on the list gains these
    spellings rather than appearing twice."""
    there = _find(order, entry.name)
    if there >= 0 and there != at:
        old = order[there]
        order[there] = Entry(entry.name,
                             clean_aliases((*old.aliases, *entry.aliases), entry.name),
                             old.was or entry.was)
        if at >= 0:
            order.pop(at)
    elif at >= 0:
        order[at] = entry
    else:
        order.append(entry)


def merged(base: list, changes: dict) -> list:
    """The list that came with the program with these changes laid over it.

    In the program's own order, a changed entry where it was and an added one
    at the end - never re-sorted. The name index settles an exact tie between
    two names by which comes first, so a list nobody changed has to reach it
    in the order it always has (the cities are not alphabetical)."""
    order = list(base)
    changes = changes if isinstance(changes, dict) else {}
    gone = {_key(name) for name in changes.get("removed") or [] if isinstance(name, str)}
    order = [entry for entry in order if _key(entry.name) not in gone]
    for row in changes.get("changed") or []:
        if not isinstance(row, dict):
            continue
        was, name = clean_name(row.get("was")), clean_name(row.get("name"))
        if not name:
            continue
        at = _find(order, was) if was else -1
        _put(order, Entry(name, clean_aliases(row.get("aliases"), name),
                          order[at].was if at >= 0 else ""), at)
    for row in changes.get("added") or []:
        if isinstance(row, dict) and clean_name(row.get("name")):
            name = clean_name(row.get("name"))
            _put(order, Entry(name, clean_aliases(row.get("aliases"), name), ""))
    return order


def alphabetical(entries: list) -> list:
    """For showing: by name, whatever its case."""
    return sorted(entries, key=lambda entry: _key(entry.name))


def changes_between(base: list, entries: list) -> dict:
    """What was done to the list that came with the program to make this one."""
    came = {entry.name: entry for entry in base}
    added, changed, kept = [], [], set()
    for entry in entries:
        source = came.get(entry.was) if entry.was else None
        if source is None:
            added.append({"name": entry.name, "aliases": list(entry.aliases)})
            continue
        kept.add(source.name)
        if entry.name == source.name and tuple(entry.aliases) == tuple(source.aliases):
            continue
        changed.append({"was": source.name, "name": entry.name,
                        "aliases": list(entry.aliases)})
    removed = [entry.name for entry in base if entry.name not in kept]
    # In name order, whatever order the editor held them in: the same list
    # saved twice is the same file twice.
    added.sort(key=lambda row: _key(row["name"]))
    changed.sort(key=lambda row: _key(row["was"]))
    return {"added": added, "changed": changed, "removed": removed}


def whose(base: list, entry: Entry) -> str:
    """"" for an entry as it came, "added" or "changed" for somebody's."""
    came = {item.name: item for item in base}
    source = came.get(entry.was) if entry.was else None
    if source is None:
        return "added"
    if entry.name != source.name or tuple(entry.aliases) != tuple(source.aliases):
        return "changed"
    return ""


def current(kind: str, place: Optional[Path] = None) -> list:
    """The list as it stands: the program's, with the saved changes over it."""
    return merged(shipped(kind), load_changes(place)[kind])


# ---------------------------------------------------------------- checking
def problems(kind: str, base: list, entries: list, shorthand: Optional[dict] = None) -> list:
    """What is wrong with a list before it is saved, in plain sentences.

    Two newspapers with one name, and one spelling under two newspapers: the
    reader could not tell which is meant, so it would refuse both. Only a
    clash that involves somebody's own entry is said - the list that came
    with the program is not theirs to answer for. ``shorthand`` is the
    reader's own two-letter forms ("DJ" for Dainik Jagran), which count as
    spellings of the papers they stand for.
    """
    word = "newspaper" if kind == "newspapers" else "city"
    said = []
    theirs = {id(entry) for entry in entries if whose(base, entry)}
    named, twice = {}, set()
    for entry in entries:
        key = _key(entry.name)
        if not key:
            said.append(f"A {word} has other spellings but no name.")
            continue
        if key in named:
            said.append(f"“{entry.name}” is on the list twice.")
            twice.add(id(entry))
            continue
        named[key] = entry
    spelt: dict = {}
    for entry in entries:
        if id(entry) in twice:
            continue                  # said once already, as a name
        spellings = [entry.name, *entry.aliases]
        for short, stands_for in (shorthand or {}).items():
            if _key(stands_for) == _key(entry.name):
                spellings.append(short)
        for spelling in spellings:
            key = _key(spelling)
            other = spelt.get(key)
            if other is None:
                spelt[key] = entry
            elif other is not entry and (id(entry) in theirs or id(other) in theirs):
                said.append(f"“{spelling}” is written for both {other.name} and "
                            f"{entry.name}. A spelling can belong to one {word} only.")
    return list(dict.fromkeys(said))


# ------------------------------------------------------------------ keeping
def save(changes: dict, place: Optional[Path] = None) -> Path:
    """Write what was done to both lists. Nothing done at all is an empty file
    of changes, never a missing one, so "put the list back as it came" is kept
    as surely as an addition is."""
    body = {
        "_version": 1,
        "_about": ("What was added to, changed on or taken off the newspaper and "
                   "city lists Collect from WhatsApp reads captions against. The "
                   "lists that come with the program are not copied here, so a "
                   "newer version's additions still arrive."),
    }
    for kind in KINDS:
        part = (changes or {}).get(kind) or _blank()
        body[kind] = {bit: list(part.get(bit) or []) for bit in ("added", "changed", "removed")}
    target = where(place)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, target)
    return target


def apply(index, place: Optional[Path] = None) -> dict:
    """Put the lists as they stand into the reader's name index. Never fails:
    with no file, or one that cannot be read, the index keeps the list that
    came with the program. Returns how many of each are on the lists now."""
    counts = {}
    for kind, setter in (("newspapers", "set_newspapers"), ("cities", "set_editions")):
        try:
            entries = current(kind, place)
            if entries:
                getattr(index, setter)([(entry.name, list(entry.aliases))
                                        for entry in entries])
            counts[kind] = len(entries)
        except Exception:  # noqa: BLE001 - a broken file costs the changes, never the lists
            counts[kind] = 0
    return counts
