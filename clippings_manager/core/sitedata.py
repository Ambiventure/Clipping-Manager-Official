"""What a browser of the program's own keeps for the sites it has opened.

Two browsers of the program's own can be signed in to a site: the browser
inside the app (Qt's engine, ui/embedded.py) and the hidden Chrome on the
program's own folder (core/webshot.py). A site keeps somebody signed in with
a cookie, so "which sites am I signed in to, and what have they kept" is a
question about cookies - and it is answered here from their names, sites,
paths and dates only.

Never a value. A cookie's value is the key to the account it belongs to:
nothing here reads one, there is no field for one, and the query that reads
a cookie file names the columns it wants so the value columns are never
fetched. The person's own everyday Chrome is never read either: the only
files opened are the two browsers' own, whose paths the callers pass in.

"Signed in" is decided by the NAME of a site's sign-in cookie (auth_token on
X, c_user on Facebook, sessionid on Instagram...), not by the site having any
cookie at all: merely opening x.com sets guest_id and three others, which the
old any-cookie rule called signed in (measured, NOTES: "Choosing how to
capture").

Plain Python and sqlite, no network, no Qt: test_sitedata reads all of it.
"""

from __future__ import annotations

import functools
import json
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

#: The cookie that is there only while somebody is signed in, by site.
SIGN_IN_COOKIES = {
    "x.com": ("auth_token",),
    "twitter.com": ("auth_token",),
    "facebook.com": ("c_user",),
    "instagram.com": ("sessionid",),
    "threads.net": ("sessionid",),
    "threads.com": ("sessionid",),
    "linkedin.com": ("li_at",),
    "youtube.com": ("LOGIN_INFO",),
    "google.com": ("SID", "__Secure-1PSID"),
}

#: What a person calls each of those sites.
SITE_NAMES = {
    "x.com": "X",
    "twitter.com": "X (Twitter)",
    "facebook.com": "Facebook",
    "instagram.com": "Instagram",
    "threads.net": "Threads",
    "threads.com": "Threads",
    "linkedin.com": "LinkedIn",
    "youtube.com": "YouTube",
    "google.com": "Google",
}

#: Where each of the three sites the morning's posts come from is signed in to.
LOGIN_PAGES = {
    "x.com": "https://x.com/login",
    "facebook.com": "https://www.facebook.com/login/",
    "instagram.com": "https://www.instagram.com/accounts/login/",
}

#: Endings that take three labels to name a site: pib.gov.in, not gov.in.
_TWO_LEVEL = ("co.in", "gov.in", "nic.in", "org.in", "ac.in", "net.in",
              "co.uk", "com.au")

#: Chrome counts time in microseconds from the first day of 1601.
_CHROME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class CookieFact:
    """One cookie, as far as anybody here may know it. There is deliberately
    no value field: nothing built on this can show or keep one."""

    name: str
    domain: str
    path: str = "/"
    expires: Optional[datetime] = None
    created: Optional[datetime] = None
    session: bool = False


@dataclass(frozen=True)
class SiteSummary:
    """One site's line in the list of what the browser keeps."""

    site: str
    count: int
    names: tuple = field(default_factory=tuple)
    until: Optional[datetime] = None
    signed_in: bool = False
    signed_in_until: Optional[datetime] = None

    @property
    def title(self) -> str:
        return name_of(self.site)


@functools.lru_cache(maxsize=8192)
def site_of(domain: str) -> str:
    """The site a cookie's domain belongs to: ".m.facebook.com" is
    facebook.com, "www.indianexpress.com" is indianexpress.com, "pib.gov.in"
    stays pib.gov.in.

    Remembered, because it is asked of every cookie each time the side panel
    is filled and a news site's jar holds a few thousand of them from a few
    hundred domains (review of step B)."""
    host = (domain or "").strip().lower().lstrip(".").rstrip(".")
    if not host:
        return ""
    if host.replace(".", "").isdigit() or ":" in host or "." not in host:
        return host                        # 127.0.0.1, localhost
    labels = host.split(".")
    while len(labels) > 2 and labels[0] in ("www", "m"):
        labels = labels[1:]
    keep = 3 if ".".join(labels[-2:]) in _TWO_LEVEL else 2
    return ".".join(labels[-keep:])


def name_of(site: str) -> str:
    return SITE_NAMES.get(site, site)


def is_sign_in(fact: CookieFact) -> bool:
    """Whether this cookie is its site's sign-in cookie - so a cookie that
    arrives or goes can change who is signed in only if this is true."""
    return fact.name in _SIGN_IN_NAMES and fact.name in SIGN_IN_COOKIES.get(site_of(fact.domain), ())


_SIGN_IN_NAMES = frozenset(name for names in SIGN_IN_COOKIES.values() for name in names)


def origin_for(fact: CookieFact) -> str:
    """The address a cookie belongs to - which Qt's engine must be given to
    remove a saved cookie: given none, it removes nothing (measured)."""
    return f"https://{(fact.domain or '').lstrip('.')}{fact.path or '/'}"


def chrome_time(microseconds) -> Optional[datetime]:
    """A time out of a Chrome cookie file, or None for "never set"."""
    try:
        value = int(microseconds or 0)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    try:
        return _CHROME_EPOCH + timedelta(microseconds=value)
    except OverflowError:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(when: Optional[datetime]) -> Optional[datetime]:
    if when is None:
        return None
    return when if when.tzinfo is not None else when.replace(tzinfo=timezone.utc)


class Jar:
    """The cookies a browser keeps, by (name, domain, path) - the same key
    the browser itself uses, so a cookie announced twice is counted once."""

    def __init__(self, facts: Iterable[CookieFact] = ()):
        self._facts: dict = {}
        for fact in facts:
            self.add(fact)

    def __len__(self) -> int:
        return len(self._facts)

    def add(self, fact: CookieFact) -> None:
        self._facts[(fact.name, (fact.domain or "").lower(), fact.path or "/")] = fact

    def remove(self, name: str, domain: str, path: str = "/") -> None:
        self._facts.pop((name, (domain or "").lower(), path or "/"), None)

    def clear(self) -> None:
        self._facts.clear()

    def facts(self, now: Optional[datetime] = None) -> list:
        """Every cookie still in force: one that has run out is not kept."""
        now = now or _now()
        return [fact for fact in self._facts.values()
                if fact.expires is None or _aware(fact.expires) > now]

    def facts_for(self, site: str, now: Optional[datetime] = None) -> list:
        return [fact for fact in self.facts(now) if site_of(fact.domain) == site]

    def by_site(self, now: Optional[datetime] = None) -> dict:
        """Every cookie still in force, grouped by site, in one pass. The
        side panel used to ask facts_for once per site, each a pass over the
        whole jar: 1.1 s for 300 sites and 3,001 cookies, on the main thread,
        on every cookie change (review of step B)."""
        grouped: dict = {}
        for fact in self.facts(now):
            site = site_of(fact.domain)
            if site:
                grouped.setdefault(site, []).append(fact)
        return grouped

    def signed_in_sites(self, now: Optional[datetime] = None) -> list:
        found = set()
        for fact in self.facts(now):
            if fact.name in _SIGN_IN_NAMES:
                site = site_of(fact.domain)
                if fact.name in SIGN_IN_COOKIES.get(site, ()):
                    found.add(site)
        return sorted(found)

    def summary(self, now: Optional[datetime] = None, grouped: Optional[dict] = None) -> list:
        """One line per site: signed-in sites first, then the most cookies.
        `grouped` is by_site() when the caller has it already."""
        by_site = grouped if grouped is not None else self.by_site(now)
        out = []
        for site, facts in by_site.items():
            if not site:
                continue
            dates = [_aware(f.expires) for f in facts if f.expires is not None]
            sign = [f for f in facts if f.name in SIGN_IN_COOKIES.get(site, ())]
            sign_dates = [_aware(f.expires) for f in sign if f.expires is not None]
            out.append(SiteSummary(
                site=site, count=len(facts),
                names=tuple(sorted({f.name for f in facts})),
                until=max(dates) if dates else None,
                signed_in=bool(sign),
                signed_in_until=max(sign_dates) if sign_dates else None))
        out.sort(key=lambda s: (not s.signed_in, -s.count, s.site))
        return out


# ------------------------------------------------------------ cookie files
def in_use(path: Path) -> bool:
    """Whether a browser has this file open now. Chromium opens its cookie
    file for itself alone while it runs, so even reading it is refused
    (measured on Qt's engine: PermissionError at 2 s and at 34 s)."""
    path = Path(path)
    if not path.is_file():
        return False
    try:
        with open(path, "rb") as handle:
            handle.read(1)
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def read_cookie_file(path) -> list:
    """The cookies in a Chromium cookie file - names, sites, paths and dates,
    never a value - or [] when there is no file, it is open in a browser, or
    it cannot be read. Read from a copy, so the browser's own file is never
    held open by the program.

    The connection is closed on every path, a failed query included. A
    `with sqlite3.connect()` block only commits or rolls back: it never
    closes. When the query failed (a damaged file, or a table of another
    shape) the connection stayed open in a reference cycle, the temporary
    folder could not be removed, and a whole copy of the cookie file was
    left in the temporary folder (review of step B, round 2)."""
    path = Path(path) if path else None
    if path is None or not path.is_file():
        return []
    try:
        with tempfile.TemporaryDirectory(prefix="cm-cookies-", ignore_cleanup_errors=True) as folder:
            copy = Path(folder) / "Cookies"
            try:
                shutil.copyfile(path, copy)
                with closing(sqlite3.connect(f"file:{copy.as_posix()}?mode=ro", uri=True)) as db:
                    columns = {row[1] for row in db.execute("PRAGMA table_info(cookies)")}
                    persistent = "is_persistent" if "is_persistent" in columns else "has_expires"
                    if persistent not in columns:
                        persistent = "0"
                    # The columns are named, so the value columns are never fetched.
                    rows = db.execute(
                        f"SELECT host_key, name, path, creation_utc, expires_utc, {persistent} "
                        "FROM cookies").fetchall()
            finally:
                # The copy exists only to be read, so it goes whatever happened.
                try:
                    copy.unlink(missing_ok=True)
                except OSError:
                    pass
    except Exception:  # noqa: BLE001 - locked, missing, or not a cookie file
        return []
    out = []
    for host, name, cookie_path, created, expires, kept in rows:
        out.append(CookieFact(
            name=str(name or ""), domain=str(host or ""), path=str(cookie_path or "/"),
            expires=chrome_time(expires), created=chrome_time(created),
            session=not bool(kept) and not chrome_time(expires)))
    return out


def remove_cookies(path, site: str = "") -> int:
    """Delete one site's cookies from a cookie file - or every cookie, with no
    site - and answer how many. Only for the program's own Chrome, and only
    while it is not running: a browser that has the file open is never
    written behind its back, and nothing is done (-1).

    The file is let go on every path. Held after a failed query, it was still
    open when the program's Chrome was started on it (review of step B,
    round 2)."""
    path = Path(path)
    if not path.is_file():
        return 0
    if in_use(path):
        return -1
    try:
        with closing(sqlite3.connect(str(path))) as db:
            with db:                       # one transaction: all of them, or none
                doomed = [rowid for rowid, host in db.execute("SELECT rowid, host_key FROM cookies")
                          if not site or site_of(host) == site]
                db.executemany("DELETE FROM cookies WHERE rowid = ?", [(r,) for r in doomed])
        return len(doomed)
    except Exception:  # noqa: BLE001 - locked after all, or not a cookie file
        return -1


def mark_for_next_start(mark: Path, site: str = "") -> None:
    """Remember to remove a site's cookies ("" for all) the next time the
    browser is about to start, because it is running now."""
    mark = Path(mark)
    try:
        data = json.loads(mark.read_text(encoding="utf-8"))
        sites = set(data.get("sites", []))
    except Exception:  # noqa: BLE001 - no mark yet
        sites = set()
    sites.add(site or "*")
    try:
        mark.write_text(json.dumps({"sites": sorted(sites)}), encoding="utf-8")
    except OSError:
        pass


def marked_sites(mark: Path) -> list:
    try:
        return sorted(json.loads(Path(mark).read_text(encoding="utf-8")).get("sites", []))
    except Exception:  # noqa: BLE001
        return []


def apply_mark(mark: Path, path) -> bool:
    """Carry out a mark left by mark_for_next_start, before the browser starts.
    True when there was one and it is done; the mark stays when the file is
    still in use."""
    mark = Path(mark)
    sites = marked_sites(mark)
    if not sites:
        return False
    for site in sites:
        if remove_cookies(path, "" if site == "*" else site) < 0:
            return False
    try:
        mark.unlink()
    except OSError:
        pass
    return True
