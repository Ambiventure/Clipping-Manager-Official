"""Everything this copy has been taught and told, in one file.

There are now several things the application remembers between mornings, and
they have arrived one at a time: which papers are regional and which are Hindi,
what has been judged about repeats, the cover artwork settings, the heading
layout, where exports go, how big the window is drawn. Each lives in its own
small file in the app-data folder.

**On the same machine, none of this needs doing.** The app-data folder is not
inside the application folder, and an update is a folder copy - so an update
already leaves all of it alone. That is worth saying plainly, because the
obvious worry is that an update wipes it, and it does not.

What this is for is the other three cases: moving to another PC, handing a
colleague what you have set up, and having a copy in case the machine dies.

**One file, not one per feature.** The alternative was a Save button on the
category editor and another on the trainer and another wherever the next thing
lands, and then somebody has three files, two of them from March. What a person
actually wants is "give me my setup" and "put my setup back".

**What travels and what does not.** Settings and judgements travel, and they
are small: measured on a working machine, everything here comes to 25KB. A
morning's work does not travel. The session is 34MB of newspaper photographs -
a thousand times the size of everything else - it is the papers' copyright
material rather than anything anybody set, and it is deliberately transient:
yesterday's newspad is not this morning's problem. Nor does anything that names
the machine or the person - the paths in the older verdicts store are stripped
on the way out, because a file meant to be emailed should not carry a Windows
account name and somebody's folder tree.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

#: Bumped when what travels changes in a way a reader must know about.
SCHEMA = 1

KIND = "clippings-manager/settings"

#: Every file that carries something a person set or taught, and what it is
#: called when the screen says what it is about to do. The session folder is
#: deliberately absent - see the module docstring.
CARRIED = (
    ("categories.json", "which papers are which"),
    ("sections.json", "your section headings, and how they print"),
    ("duplicate_training.jsonl", "what you have taught it about repeats"),
    ("duplicate_verdicts.jsonl", "duplicate decisions from the review screen"),
    ("cover.json", "cover page settings"),
    ("heading_standard.json", "press report heading layout"),
    ("heading_sentiment.json", "dossier heading layout"),
    ("sentiment_cover.json", "dossier cover settings"),
    ("export.json", "export preferences"),
    ("display.json", "the size the window is drawn at"),
)

#: Fields scrubbed out of any row on the way into a backup, wherever they
#: appear. `file` is a full path in the older verdicts store - on the office PC
#: that reads C:\\Users\\<the officer's name>\\... - and a backup is a file
#: people send to each other.
STRIPPED = ("file",)


# ------------------------------------------------------- keeping a copy safe
#
# WHY THERE IS NO GOOGLE DRIVE IN HERE, and why that is the better answer
# rather than the easier one.
#
# The application reaches the network in exactly one place - the Check for
# updates button, which asks GitHub for a version number when it is pressed and
# at no other time. Talking to Drive would be a different thing entirely: it
# means an account sign-in, a token kept
# on a departmental PC, and a promise broken on the first screen.
#
# It would also be WORSE at the job. Google Drive, OneDrive and Dropbox all
# work by syncing a folder: anything written into that folder is uploaded by
# the client that is already installed, already signed in, and already trusted
# by whoever administers the machine. So the application writes a file - which
# it can do with the cable unplugged, which an upload cannot - and the sync
# client carries it. Nothing to sign in to, no token to leak, nothing to
# rewrite when an API changes, and it still works on a morning with no
# internet, which is the morning it matters most.
#
# All this has to do, then, is offer to put the file in the right place and
# keep it up to date.

#: Folders a sync client may put in somebody's home folder, and what to call
#: each on screen.
SYNC_PLACES = (
    ("My Drive", "Google Drive"),
    ("Google Drive", "Google Drive"),
    ("GoogleDrive", "Google Drive"),
    ("OneDrive", "OneDrive"),
    ("OneDrive - Personal", "OneDrive"),
    ("OneDrive - Business", "OneDrive"),
    ("Dropbox", "Dropbox"),
    ("iCloudDrive", "iCloud Drive"),
)

#: And the folders a sync client makes when it mounts itself as a DRIVE rather
#: than a folder, which is what Google Drive for Desktop does by default - it
#: takes a spare letter, usually G:, and puts "My Drive" inside it. Looking only
#: in the home folder finds nothing on a machine where Drive is installed and
#: working, which would make it look as though the feature did not work.
MOUNTED_AS = (
    ("My Drive", "Google Drive"),
    ("Shared drives", "Google Drive (shared)"),
)

#: The name the kept copy always has. Deliberately not dated: every one of
#: these services keeps its own history of a file that is written over, so one
#: name gives a copy that can be rolled back, where dated names give a folder
#: filling up with setups from March that nobody dares delete.
KEPT_NAME = "ClippingsManager-setup.json"


def _letters() -> list:
    """Every drive letter that is actually there, without asking Windows twice.

    Deliberately plain: a letter either has a folder on it or it does not, and
    anything that throws while being looked at is simply not offered.
    """
    import string

    out = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        try:
            if root.is_dir():
                out.append(root)
        except Exception:  # noqa: BLE001 - a disconnected share, a locked drive
            continue
    return out


def sync_places() -> list:
    """[(what it is called, the folder)] for every sync folder on this machine.

    Two places to look, because the clients do two different things. OneDrive
    and Dropbox make a folder in the home folder. Google Drive for Desktop
    mounts itself as a DRIVE - it takes a spare letter, usually G:, and puts
    "My Drive" inside it - so looking only in the home folder finds nothing on
    a machine where Drive is installed and working perfectly.

    Only folders that actually exist are offered. A machine with none gets an
    empty list and an ordinary folder to browse to instead: a network drive, a
    memory stick, anything already backed up by somebody else.
    """
    found, seen = [], set()

    def offer(said, where):
        try:
            if where.is_dir() and where not in seen:
                seen.add(where)
                found.append((said, where))
        except Exception:  # noqa: BLE001 - an unreadable drive is not a crash
            pass

    home = Path.home()
    for name, said in SYNC_PLACES:
        offer(said, home / name)
    # The system drive is skipped for the mounted kind: C:\My Drive is not
    # something Drive for Desktop makes, and a folder somebody happens to have
    # called that is not a sync folder.
    system = Path(os.environ.get("SystemDrive", "C:") + "\\")
    for root in _letters():
        if root == system:
            continue
        for name, said in MOUNTED_AS:
            offer(said, root / name)
    return found


def _kept_setting() -> Path:
    return _folder() / "backup_copy.json"


def kept_where() -> Optional[Path]:
    """The folder a copy is being kept in, or None if nobody has asked for one."""
    try:
        found = json.loads(_kept_setting().read_text(encoding="utf-8"))
        where = Path(str(found.get("folder") or ""))
        return where if str(where) and where != Path("") else None
    except Exception:  # noqa: BLE001 - not asked for
        return None


def last_kept() -> str:
    """When a copy was last written, as it was written down. Empty if never.

    A backup nobody can see is worth very little: the failure everybody has had
    is the copy that quietly stopped months ago. So the time is kept and shown.
    """
    try:
        found = json.loads(_kept_setting().read_text(encoding="utf-8"))
        return str(found.get("last") or "")
    except Exception:  # noqa: BLE001 - never written
        return ""


def keep_copies_in(folder) -> None:
    """Keep a copy of the setup here from now on. None to stop."""
    payload = {"folder": str(folder) if folder else "",
               "last": last_kept() if folder else ""}
    try:
        _write_atomic_text(_kept_setting(), json.dumps(payload, indent=1))
    except Exception:  # noqa: BLE001 - not being able to save is not fatal
        pass


def _write_atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def keep_a_copy() -> Optional[Path]:
    """Write the copy, if one was asked for. Returns where, or None.

    Called when the application closes. It must never be the reason a close
    fails or hangs: a folder that has gone - an unplugged stick, a network
    share that is not there this morning - is a shrug, not an error.
    """
    where = kept_where()
    if where is None:
        return None
    try:
        if not where.is_dir():
            return None
        target = where / KEPT_NAME
        save_to(target)
        try:
            _write_atomic_text(_kept_setting(), json.dumps(
                {"folder": str(where),
                 "last": datetime.now().isoformat(timespec="seconds")},
                indent=1))
        except Exception:  # noqa: BLE001 - the copy is written either way
            pass
        return target
    except Exception:  # noqa: BLE001 - a copy that cannot be written is not
        return None    # worth stopping anything for


def _folder() -> Path:
    from ..ui.export_dialog import settings_dir

    return settings_dir()


def _clean(value):
    """A settings value with anything machine-identifying taken out."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in STRIPPED and isinstance(item, str):
                out[key] = os.path.basename(item)
            else:
                out[key] = _clean(item)
        return out
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, str) and (":\\" in value or value.startswith("\\\\")):
        # A stray absolute path in a settings file - the export folder, say.
        # The name is useful, the path is somebody's machine.
        return os.path.basename(value)
    return value


def _read(name: str) -> Optional[object]:
    path = _folder() / name
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 - not set on this machine
        return None
    if name.endswith(".jsonl"):
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(_clean(json.loads(line)))
            except ValueError:
                continue
        return rows
    try:
        return _clean(json.loads(text))
    except ValueError:
        return None


def _write(name: str, value) -> bool:
    path = _folder() / name
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".jsonl"):
            body = "".join(json.dumps(row, ensure_ascii=False) + "\n"
                           for row in (value or []))
        else:
            body = json.dumps(value, indent=2, ensure_ascii=False)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(body, encoding="utf-8")
        os.replace(temp, path)
        return True
    except Exception:  # noqa: BLE001 - one file failing is not the lot failing
        return False


def what_is_here() -> list:
    """[(name, description, how much)] for everything set on this machine."""
    out = []
    for name, said in CARRIED:
        value = _read(name)
        if value is None:
            continue
        size = len(value) if isinstance(value, list) else 1
        out.append((name, said, size))
    return out


def save_to(path) -> dict:
    """Write one file carrying everything this copy has been set up with."""
    from .. import version

    settings = {}
    for name, _said in CARRIED:
        value = _read(name)
        if value is not None:
            settings[name] = value
    body = json.dumps(settings, ensure_ascii=False, sort_keys=True)
    payload = {
        "kind": KIND,
        "schema": SCHEMA,
        "app": version.__version__,
        "digest": version.digest(),
        "saved": datetime.now().isoformat(timespec="seconds"),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "settings": settings,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=1, ensure_ascii=False),
                    encoding="utf-8")
    os.replace(temp, path)
    return {"files": len(settings),
            "what": [said for name, said in CARRIED if name in settings]}


def inspect(path) -> dict:
    """What a backup holds, and what restoring it would replace."""
    try:
        found = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "why": f"That file could not be read ({error})."}
    if not isinstance(found, dict) or found.get("kind") != KIND:
        return {"ok": False,
                "why": "That is not a Clippings Manager settings file."}
    settings = found.get("settings")
    if not isinstance(settings, dict):
        return {"ok": False, "why": "That file carries no settings."}
    body = json.dumps(settings, ensure_ascii=False, sort_keys=True)
    if found.get("sha256") and found["sha256"] != hashlib.sha256(
            body.encode("utf-8")).hexdigest():
        return {"ok": False,
                "why": "That file is damaged or was only partly copied."}

    said = dict(CARRIED)
    coming, over = [], []
    for name in settings:
        if name not in said:
            continue                       # from a later version; leave it
        coming.append(said[name])
        if (_folder() / name).exists():
            over.append(said[name])
    return {"ok": True, "app": found.get("app", ""),
            "saved": found.get("saved", ""), "schema": found.get("schema", 0),
            "coming": coming, "over": over, "_settings": settings}


def restore_from(path) -> dict:
    """Put a backup back. Replaces what it carries; leaves the rest alone.

    Deliberately a REPLACE and not a merge, and the difference matters. The
    trainer's own Load button merges judgements, because two people judging
    different pairs both have something to add. This is "put my setup back",
    which is a different question with a different right answer: half of one
    machine's category list mixed with half of another's is a list nobody chose.

    A morning's work is never touched - the session is not carried and not
    replaced, so restoring a backup on a machine mid-morning does not lose it.
    """
    looked = inspect(path)
    if not looked.get("ok"):
        return looked
    settings = looked.pop("_settings", {})
    known = dict(CARRIED)
    put, failed = [], []
    for name, value in settings.items():
        if name not in known:
            continue
        (put if _write(name, value) else failed).append(known[name])
    looked["restored"] = put
    looked["failed"] = failed
    return looked
