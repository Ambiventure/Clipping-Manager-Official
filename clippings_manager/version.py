"""Which build this is.

A report built on one machine and a report built on another have to be
comparable, and until now nothing in the application, the executable or the
exported file said which build produced it. When two laptops disagreed there was
no way to tell whether they were running the same code - so the first question
after any "it works here but not there" had no answer.

Three things carry the stamp now:

*   the window, next to the title, so it can be read without opening anything;
*   the executable's own file properties, so it can be read without running it;
*   the exported PDF and Word file, in their document properties, so a report
    that has been emailed on can still say what made it.

``digest`` is a hash of the packaged source, so two builds of identical code
carry the same stamp and two builds of different code never do.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# Raised by build.py on every packaged build: the last number goes up by one,
# 1.7.1 -> 1.7.2 -> 1.7.3. It is not a judgement anybody has to make and not a
# thing anybody can forget - which is how four builds went out as "1.5.0" on one
# afternoon, and how the number then jumped 1.5 -> 1.6 -> 1.7 for what were three
# ordinary rounds of fixes. Raise the first two numbers by hand, here, only when
# something genuinely large changes.
__version__ = "2.0.19"

_HERE = Path(__file__).resolve().parent
_STAMP_FILE = _HERE / "_buildstamp.json"

# What goes into the digest: everything that can change what a report looks like.
_HASHED = ("*.py", "*/*.py", "config/*.json")


def source_digest(root: Path | None = None) -> str:
    """A short hash of the packaged source, stable across machines."""
    root = root or _HERE
    digest = hashlib.sha256()
    names: list[Path] = []
    for pattern in _HASHED:
        names.extend(sorted(root.glob(pattern)))
    for path in sorted(set(names), key=lambda p: str(p).lower()):
        try:
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
        except OSError:
            continue
    return digest.hexdigest()[:12]


def _packaged() -> bool:
    """Whether this is the built executable rather than the source tree."""
    return bool(getattr(sys, "frozen", False))


def _stamp() -> dict:
    """The recorded stamp - trusted only in a packaged build.

    The file is written into the source tree at build time, so it is still
    sitting there afterwards while the code around it is edited. Trusting it
    from source would report the last build's identity for code that has since
    changed, which is exactly the kind of wrong answer this whole thing exists
    to prevent.
    """
    if not _packaged():
        return {}
    try:
        return json.loads(_STAMP_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def build_date() -> str:
    """The day the executable was built, or "" when running from source."""
    return str(_stamp().get("built", ""))


def packaged_version() -> str:
    """The version this build was packaged as, or the source's own."""
    return str(_stamp().get("version") or __version__)


def digest() -> str:
    """The source hash: the one recorded at build time, or the live one."""
    return str(_stamp().get("digest") or source_digest())


def describe() -> str:
    """One line: "1.7.2 · a1b2c3d4e5f6", or "1.7.2 (from source) · ...".

    No date. The version counts up on every build, so it already answers "which
    is newer" on its own, and a date in the name of an application is noise -
    two builds on one afternoon carry the same date and different code.
    """
    version = packaged_version()
    if not _packaged():
        version += " (from source)"
    return f"{version} · {digest()}"


def matches(other: str) -> bool:
    """Whether another machine's stamp is the same build as this one."""
    return digest() in (other or "")
