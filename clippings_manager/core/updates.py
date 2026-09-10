"""Asking, once, whether a newer version has been published.

**This is the only thing in the application that touches the network, and it
only does it when somebody presses a button.** Nothing here runs at startup,
nothing runs on a timer, and nothing runs while a report is being made. That is
what keeps the badge on the crown honest: the program does not reach out on its
own, ever. Press "Check for updates" and it makes exactly one request; press
nothing and it makes none.

**Nothing is installed.** It reads a small file, compares a version number, and
- if there is a newer one - offers to open the download page in a browser. It
does not download, unpack or replace anything. On Windows a running program
holds its own files open, so replacing an installation from inside it needs a
second program that waits for the first to close, swaps the folders and starts
it again; that is real work with a real way of leaving somebody with half an
installation. Telling somebody there is an update and letting them fetch it is
honest, and it cannot break what they already have.

**No token, and nothing that needs one.** It reads a plain file from a public
repository over https. An application that is handed out as a zip cannot keep a
secret - anything embedded in it can be read straight back out - so it is built
to need none.

**Nothing is added to the program to do this.** urllib is part of Python. No
package, nothing new in the bundle, and nothing that stops working when a
library changes under it.
"""

from __future__ import annotations

import json
import re
from typing import Optional

#: Where the published version is announced. A plain file on the default
#: branch rather than the releases API: the API allows sixty unauthenticated
#: requests an hour from one address, which a department behind one office
#: connection can reach, and raw files are served from a cache with no such
#: limit. It also needs no token, which is the point.
OWNER = "Ambiventure"
REPO = "Clipping-Manager-Official"
BRANCH = "main"
NOTICE = (f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/"
          "latest.json")

#: Where somebody is sent to fetch it.
RELEASES = f"https://github.com/{OWNER}/{REPO}/releases"

#: How long to wait before giving up. Short on purpose: this happens with
#: somebody watching, and a button that sits there for half a minute reads as a
#: broken program rather than a slow network.
PATIENCE = 6.0

_NUMBERS = re.compile(r"\d+")


def as_numbers(version: str) -> tuple:
    """"2.0.15" -> (2, 0, 15), so 2.0.9 sorts before 2.0.15.

    Comparing the strings would put "2.0.9" after "2.0.15", which is the whole
    reason this exists rather than a straight comparison.
    """
    found = _NUMBERS.findall(str(version or ""))
    return tuple(int(part) for part in found[:4]) or (0,)


def is_newer(there: str, here: str) -> bool:
    return as_numbers(there) > as_numbers(here)


def check(timeout: float = PATIENCE) -> dict:
    """Ask once whether there is a newer version. Never raises.

    Returns a dict that always carries ``ok``. When something goes wrong -
    no connection, a proxy in the way, nothing published yet - ``ok`` is False
    and ``why`` is a sentence a person can read. Being unable to check is not
    an error worth a warning triangle: it is Tuesday.
    """
    from .. import version

    here = version.__version__
    try:
        import urllib.request

        ask = urllib.request.Request(
            NOTICE,
            headers={"User-Agent": f"ClippingsManager/{here}",
                     "Cache-Control": "no-cache"})
        with urllib.request.urlopen(ask, timeout=timeout) as answer:
            raw = answer.read(64 * 1024).decode("utf-8", "replace")
    except Exception as error:  # noqa: BLE001 - offline, blocked, or not there
        return {"ok": False, "here": here,
                "why": _plainly(error)}

    try:
        found = json.loads(raw)
        if not isinstance(found, dict):
            raise ValueError("not a version notice")
    except Exception:  # noqa: BLE001
        return {"ok": False, "here": here,
                "why": "The answer from the update page could not be read."}

    there = str(found.get("version") or "").strip()
    if not there:
        return {"ok": False, "here": here,
                "why": "No version has been published yet."}

    return {
        "ok": True,
        "here": here,
        "there": there,
        "newer": is_newer(there, here),
        "download": str(found.get("download") or RELEASES),
        "notes": str(found.get("notes") or ""),
        "published": str(found.get("published") or ""),
    }


def _plainly(error: Exception) -> str:
    """What went wrong, in words somebody can act on."""
    import socket
    import urllib.error

    if isinstance(error, urllib.error.HTTPError):
        if error.code == 404:
            return ("Nothing has been published to check against yet.")
        return f"The update page answered with an error ({error.code})."
    if isinstance(error, (socket.timeout, TimeoutError)):
        return ("The update page did not answer in time. The program is fine; "
                "only the check failed.")
    if isinstance(error, urllib.error.URLError):
        return ("Could not reach the update page. That usually means no "
                "internet connection at the moment.")
    return f"Could not check for updates ({type(error).__name__})."


def notice_for(stamp: dict) -> dict:
    """The file to publish alongside a build, so a copy in the field can see it.

    Written by build.py into dist/ next to the zip. Commit it to the top of the
    repository and every installed copy sees the new version the next time
    somebody presses the button.
    """
    version = stamp.get("version", "")
    return {
        "version": version,
        "published": stamp.get("built", ""),
        # The release PAGE, not a direct link to the zip inside it. GitHub
        # rewrites spaces in an uploaded asset's name to full stops, so a link
        # built from the file name on this machine - "Clippings Manager
        # 2.0.16.zip" - points at something GitHub has stored as
        # "Clippings.Manager.2.0.16.zip", and lands on a 404 that looks for all
        # the world like the update itself is broken. The page always shows
        # whatever the asset ended up being called.
        "download": f"https://github.com/{OWNER}/{REPO}/releases/tag/v{version}",
        "releases": RELEASES,
        "notes": "",
    }
