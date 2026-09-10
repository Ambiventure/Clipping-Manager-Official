"""What kind of publication each masthead is, so clippings can be sorted by it.

A morning is a hundred and fifty cuttings from twenty papers, and the questions
somebody actually asks of it are "what did the regional press say", "show me the
English papers", "put the big ones first". None of that can be answered from a
clipping, because a clipping only knows the name of the paper it came out of. So
the knowledge lives here: four axes, one value each per paper.

    reach     National / Regional / Local
    language  Hindi / English / Punjabi / Urdu / Other
    stature   Major / Mid / Small
    medium    Newspaper / Television / Website / Social

One value per axis, never a list. That is what makes filters stack without
contradicting each other: "Regional and Hindi" is an intersection of two sets
that each partition the whole, so the result can never be larger than either.

The fourth axis exists because not everything in a morning's clippings is a
newspaper. "Aaj Tak", "Times Now" and "Babushahi.com" arrive in the same caption
slots as the papers, and forcing a television channel into a language-and-reach
scheme built for print makes every count that follows wrong.

**The defaults ship read-only and the user's corrections do not.** The list that
travels with the application is the department's starting point, not their
answer; they know these papers and this file does not. So an edit is written to
the app-data folder as a record of WHAT CHANGED - "you moved Dainik Savera to
Major", "you deleted Mail Today" - and never as a copy of the whole list. That
distinction is the whole design:

  * a snapshot in the app-data folder is complete, so it wins outright, so a
    paper added to the defaults in a later version could never reach anybody who
    had ever edited anything. The list would silently freeze on the day it was
    first touched.
  * a record of changes is applied ON TOP of whatever the new version ships. New
    papers arrive; the user's own decisions survive; and a paper they deleted
    stays deleted even if a later version ships it again, which is the case
    nobody would ever notice going wrong.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# The value every axis falls back to when the paper is not known - and, just as
# often, when the clipping has no paper on it yet. On a real morning that is 85
# clippings out of 142, because the loose WhatsApp images have not been named.
#
# It is a real value rather than a blank so it can be PICKED: choosing "Not
# known" under Newspaper is how somebody finds every clipping still waiting to be
# named. A filter that could only hide them would have thrown that away.
UNKNOWN = "Not known"

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalise(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace. Unicode-aware.

    The same rule :mod:`profiles` matches names by, and it has to stay the same
    rule: a paper is looked up here by the name the review grid put on the
    clipping, so "Amar Ujala " and "amar ujala" must be one paper and not two.
    Exact after normalising, never fuzzy - a near-miss here would quietly file a
    clipping under a category nobody chose for it.
    """
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", (text or "").lower())).strip()


def _store() -> Path:
    from ..ui.export_dialog import settings_dir

    return settings_dir() / "categories.json"


def _read(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a missing or broken file is just defaults
        return {}


def _write(path: Path, payload: dict) -> None:
    """Temp file, then replace. A kill mid-write leaves one whole file or the
    other, never half of either - this is a list somebody typed by hand."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    os.replace(temp, path)


class Axis:
    """One question that can be asked of a publication."""

    __slots__ = ("key", "label", "help", "values")

    def __init__(self, key: str, raw: dict):
        self.key = key
        self.label = raw.get("label") or key.title()
        self.help = raw.get("help") or ""
        self.values = [str(v) for v in raw.get("values", []) if str(v).strip()]

    @property
    def choices(self) -> list:
        """Every value that can be picked, including the one for papers the app
        does not know. Always last, because it is not a kind of paper."""
        return [*self.values, UNKNOWN]


class Book:
    """The classification, defaults and the user's corrections already merged."""

    def __init__(self, axes: dict, papers: list, touched: Optional[set] = None):
        self.axes: dict = axes
        self.papers: list = papers
        # Which papers the user has had a hand in, so the editor can say so.
        self.touched: set = touched or set()
        self._by_norm: dict = {}
        for paper in papers:
            self._by_norm[normalise(paper.get("name", ""))] = paper

    # -- looking a paper up ------------------------------------------------
    def paper(self, name: str) -> Optional[dict]:
        """The row for this masthead, or None. Aliases resolve through the same
        name list the rest of the application matches on, so a clipping labelled
        "Jagran" and one labelled "Dainik Jagran" are one paper here too."""
        if not name:
            return None
        found = self._by_norm.get(normalise(name))
        if found is not None:
            return found
        canonical = _alias_map().get(normalise(name))
        if canonical:
            return self._by_norm.get(normalise(canonical))
        return None

    def value(self, name: str, axis: str) -> str:
        paper = self.paper(name)
        if paper is None:
            return UNKNOWN
        return str(paper.get(axis) or UNKNOWN)

    def of(self, clip) -> dict:
        """Every axis for one clipping, in one lookup rather than four."""
        paper = self.paper(getattr(clip, "newspaper", "") or "")
        if paper is None:
            return {key: UNKNOWN for key in self.axes}
        return {key: str(paper.get(key) or UNKNOWN) for key in self.axes}

    @property
    def names(self) -> list:
        return sorted((p.get("name", "") for p in self.papers), key=str.casefold)

    def names_in(self, axis: str, value: str) -> list:
        """Every paper filed under this value - what the category editor shows
        when somebody opens "Regional"."""
        return sorted((p.get("name", "") for p in self.papers
                       if str(p.get(axis) or UNKNOWN) == value),
                      key=str.casefold)

    def unsure(self) -> list:
        """The papers nobody could confirm. These are the first rows worth a
        person's attention, and saying so is more use than a confident guess."""
        return sorted((p.get("name", "") for p in self.papers
                       if p.get("checked") == "unsure"), key=str.casefold)


# ------------------------------------------------------------------ loading

_ALIASES: Optional[dict] = None


def _alias_map() -> dict:
    """normalised alias -> canonical newspaper name, from the shipped name list.

    Read once. It is the same file :mod:`profiles` reads, so a paper spelled in
    Devanagari on a burned-in masthead finds its category the same way it finds
    its name.
    """
    global _ALIASES
    if _ALIASES is not None:
        return _ALIASES
    found: dict = {}
    raw = _read(CONFIG_DIR / "newspapers.json")
    for entry in raw.get("newspapers", []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "")
        if not name:
            continue
        for spelling in [name, *entry.get("aliases", [])]:
            key = normalise(spelling)
            if key and key not in found:
                found[key] = name
    _ALIASES = found
    return found


def _defaults() -> dict:
    return _read(CONFIG_DIR / "categories.json")


def _clean(row: dict, axes: dict) -> Optional[dict]:
    """One row, checked against the axes before anything is allowed to use it.

    A value from a newer build, or from a file somebody edited by hand, must not
    reach the list - it would appear in no filter and be impossible to pick.
    """
    if not isinstance(row, dict):
        return None
    name = str(row.get("name", "") or "").strip()
    if not name:
        return None
    out = {"name": name,
           "checked": str(row.get("checked", "") or "known"),
           "note": str(row.get("note", "") or "")}
    if out["checked"] not in ("verified", "known", "unsure"):
        out["checked"] = "known"
    for key, axis in axes.items():
        value = str(row.get(key, "") or "")
        out[key] = value if value in axis.values else (axis.values[0]
                                                       if axis.values else UNKNOWN)
    return out


def load() -> Book:
    """The shipped list with the user's changes applied on top."""
    shipped = _defaults()
    axes = {key: Axis(key, raw)
            for key, raw in (shipped.get("axes") or {}).items()}

    rows, order = {}, []
    for raw in shipped.get("papers", []):
        row = _clean(raw, axes)
        if row is None:
            continue
        key = normalise(row["name"])
        if key not in rows:
            order.append(key)
        rows[key] = row

    mine = _read(_store())
    touched: set = set()

    # Papers the user deleted. Kept as names, and kept forever: if a later
    # version ships the paper again, their decision still stands. An update
    # quietly putting back a paper somebody removed is a mistake nobody notices
    # until it prints.
    for name in mine.get("removed", []) or []:
        key = normalise(str(name))
        rows.pop(key, None)
        touched.add(key)

    # Fields the user changed, one field at a time rather than one paper at a
    # time. So a later version can correct a paper's language without undoing
    # the size the user set on it.
    for name, changes in (mine.get("changed") or {}).items():
        key = normalise(str(name))
        row = rows.get(key)
        if row is None or not isinstance(changes, dict):
            continue
        for axis_key, value in changes.items():
            axis = axes.get(axis_key)
            if axis is not None and str(value) in axis.values:
                row[axis_key] = str(value)
                touched.add(key)

    # Papers the user added themselves.
    for raw in mine.get("added", []) or []:
        row = _clean(raw, axes)
        if row is None:
            continue
        key = normalise(row["name"])
        row["checked"] = "yours"
        if key not in rows:
            order.append(key)
        rows[key] = row
        touched.add(key)

    return Book(axes, [rows[k] for k in order if k in rows], touched)


# ------------------------------------------------------------------ editing
#
# Every one of these writes a CHANGE, never the list. See the module docstring.


def _mine() -> dict:
    raw = _read(_store())
    return {"_version": 1,
            "changed": dict(raw.get("changed") or {}),
            "added": list(raw.get("added") or []),
            "removed": list(raw.get("removed") or [])}


def set_value(name: str, axis: str, value: str) -> None:
    """Put this paper under this value - which is what "add it to Regional"
    means when a paper has exactly one reach."""
    name = (name or "").strip()
    if not name:
        return
    mine = _mine()
    key = normalise(name)

    # A paper the user added themselves is theirs outright: change the row, not
    # a note about the row, or the change would be recorded against a default
    # that does not exist.
    for row in mine["added"]:
        if normalise(str(row.get("name", ""))) == key:
            row[axis] = value
            _write(_store(), mine)
            return

    shipped = None
    for row in _defaults().get("papers", []):
        if normalise(str(row.get("name", ""))) == key:
            shipped = row
            break
    changes = dict(mine["changed"].get(name) or {})
    if shipped is not None and str(shipped.get(axis, "")) == value:
        # Back to what the app ships. Drop the note rather than record it, so a
        # later version is free to correct this field again.
        changes.pop(axis, None)
    else:
        changes[axis] = value
    if changes:
        mine["changed"][name] = changes
    else:
        mine["changed"].pop(name, None)
    _write(_store(), mine)


def add_paper(name: str, values: dict) -> None:
    """A paper the shipped list does not have."""
    name = (name or "").strip()
    if not name:
        return
    mine = _mine()
    key = normalise(name)
    mine["removed"] = [n for n in mine["removed"] if normalise(str(n)) != key]
    mine["added"] = [r for r in mine["added"]
                     if normalise(str(r.get("name", ""))) != key]
    mine["added"].append({"name": name, "checked": "yours", **dict(values)})
    _write(_store(), mine)


def remove_paper(name: str) -> None:
    """Take a paper out of the list for good."""
    name = (name or "").strip()
    if not name:
        return
    mine = _mine()
    key = normalise(name)
    was_mine = any(normalise(str(r.get("name", ""))) == key
                   for r in mine["added"])
    mine["added"] = [r for r in mine["added"]
                     if normalise(str(r.get("name", ""))) != key]
    mine["changed"].pop(name, None)
    # A paper the user added themselves leaves no gravestone: it was never in
    # the defaults, so there is nothing a later version could bring back.
    if not was_mine and not any(normalise(str(n)) == key
                                for n in mine["removed"]):
        mine["removed"].append(name)
    _write(_store(), mine)


def forget() -> bool:
    """Throw away every correction and go back to the list the app ships."""
    path = _store()
    try:
        if path.exists():
            path.unlink()
            return True
    except Exception:  # noqa: BLE001 - never let bookkeeping break anything
        pass
    return False


def edited() -> bool:
    """Has anything been changed at all? For the Reset button to know."""
    raw = _read(_store())
    return bool(raw.get("changed") or raw.get("added") or raw.get("removed"))
