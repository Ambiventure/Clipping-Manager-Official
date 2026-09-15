"""The browser inside the program: Qt's own Chromium, kept for captures.

Two things it does that the headless Chrome of core/webshot cannot:

*   **Sign in once, inside the program.** X and Facebook show a post only to
    somebody signed in. The person signs in here, in a window of the
    program's own on the program's own profile, and every capture after that
    is signed in. Their everyday Chrome is never touched - Chrome would not
    lend its sign-in anyway, as core/chromewin.py records.
*   **Capture twelve links with nothing on the screen.** The page that does
    the capturing lives in a window parked off the edge of the desktop. It
    is driven over Chromium's own debugging protocol by the same code that
    drives the headless browser (webshot.capture_over), so a story comes out
    the same whichever engine took it. Measured: a page with no window at
    all gives no picture, ever; a window parked off the desktop gives one in
    half a second.

The debugging port is chosen free at startup and opened by Chromium when the
first page is made, on 127.0.0.1 only. Its protocol server answers from the
thread that owns the browser - Qt's main thread - so every call over it is
made from a worker thread, never from the main one: a call made there waits
on itself for ever (measured, the first probe).

Two things measured about the parked page (NOTES: "Capture quality"):

*   **Its scrollbars are off.** Qt draws a scrollbar inside the page, which
    made the page 805 pixels wide instead of 820 - narrower cuttings than
    headless Chrome's, with the scrollbar at their right edge. The window
    somebody browses in keeps its scrollbars.
*   **A page can stop it answering.** hindustantimes.com stops Qt's engine
    running scripts about nine seconds after it opens, and it never recovers
    by itself. Sending the page to about:blank unsticks it at once; if even
    that fails, `Host.renew()` puts a fresh page in the parked window. Either
    way one bad page fails its own link, in plain words, and the next link
    captures normally. The same is done at the start of a list, because the
    page can stop answering after its own list has finished (HT captures in
    six seconds and stops at nine): left alone, every later list failed.

The browser window (2.0.32) tours the links of the message - Previous, Next,
pick any - and "Capture this page" pictures the page as it is on the screen,
over that page's own debugging target, without loading it again: its pictures
have loaded and a pop-up somebody closed stays closed. What it keeps - the
sign-ins, the sites' cookies, permissions - is in its ☰ side panel
(ui/sitepanel.py), read from core/sitedata.py by name and date, never value.

What was measured about the cookie store of QtWebEngine 6.11.2 (NOTES:
"Choosing how to capture"): loadAllCookies never announces anything; the
Cookies file is locked while the engine runs and readable before it starts;
deleteCookie removes a saved cookie only when given the site's address; and
the store does nothing until a page exists. So the Host reads the Cookies
file before it makes the profile, then follows cookieAdded and cookieRemoved.

The browser reaches out only when a capture or the sign-in window asks it
to, like the other two modules allowed to (NOTES: the offline rule).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (QCoreApplication, QEvent, QEventLoop, QObject, QThread, QTimer, QUrl,
                            Qt, Signal, Slot)
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QProgressBar, QPushButton, QSplitter,
                               QVBoxLayout, QWidget)

try:  # a build without the browser keeps the headless path
    from PySide6.QtWebEngineCore import (QWebEngineNewWindowRequest, QWebEnginePage,
                                         QWebEngineProfile, QWebEngineSettings)
    from PySide6.QtWebEngineWidgets import QWebEngineView
    AVAILABLE = True
except Exception:  # noqa: BLE001
    AVAILABLE = False

#: How long a worker waits for a renewed parked page to be listed on the port.
RENEW_SECONDS = 8.0
#: How long the page has to be made ready at the start of a list before it is
#: taken to have stopped answering.
ATTACH_SECONDS = 5.0
#: The longest the program's end waits, with the events still turning, for a
#: capture it has cut: longer than the slowest step of attaching, so a page
#: slow to answer is still waited out rather than left running.
END_SECONDS = ATTACH_SECONDS + 3.0
NOT_ANSWERING = "the browser inside the program did not answer"

from ..core import links, sitedata, webshot
from . import theme

PROFILE_NAME = "clippings"
#: Where the person's sign-ins live: beside the other settings, never in Chrome.
PROFILE_FOLDER = "webprofile"
SIGN_INS_FILE = "signed-in.json"
SOCIAL = ("x.com", "twitter.com", "facebook.com", "instagram.com", "threads.net")
LOGIN_PAGES = sitedata.LOGIN_PAGES
#: The parked window: off every edge of any desktop, and it never takes focus.
PARK_AT = (-12000, -12000)
#: Left by Remove everything: what pages saved for themselves is removed the
#: next time the program starts, because the engine locks those files while it
#: runs and has no way to clear them site by site.
WIPE_MARK = "wipe-on-start"
STORAGE_TO_WIPE = ("Local Storage", "Session Storage", "IndexedDB", "Service Worker",
                   "File System", "blob_storage", "WebStorage")

#: The browser window's own preferences, beside the others in export.json.
THEN_NEXT_KEY = "browser_capture_then_next"
PANEL_KEY = "browser_panel_open"

#: The watch on the page somebody is looking at: asked to run "1" every
#: WATCH_MS, it has stopped responding when HUNG_SECONDS pass unanswered -
#: never in the first WATCH_GRACE_SECONDS of a page opening, when a heavy
#: page is only busy.
WATCH_MS = 2000
HUNG_SECONDS = 5.0
WATCH_GRACE_SECONDS = 6.0

STUCK_WORDS = "This page stopped responding."
CRASHED_WORDS = "This page's browser process stopped."

#: The port the browser will answer on, chosen once, before the application.
PORT = 0

if AVAILABLE:
    class QuietPage(QWebEnginePage):
        """The parked page. A page's own alert, confirm and prompt boxes are
        answered "no" here and never shown: Qt's own box for an "Ad blocker
        detected" alert opened at the top left of the screen, blocked the
        whole program, and failed that link and the next one while it stayed
        open (review of step C). Nobody can see this page to answer it. A
        "leave this page?" box is let go, so the next link can open."""

        def javaScriptAlert(self, securityOrigin, msg):  # noqa: N802,N803 - Qt's names
            return None

        def javaScriptConfirm(self, securityOrigin, msg):  # noqa: N802,N803
            return str(msg or "").startswith("Are you sure you want to leave this page")

        def javaScriptPrompt(self, securityOrigin, msg, defaultValue):  # noqa: N802,N803
            return False, ""

    class TourPage(QWebEnginePage):
        """The page somebody browses in the browser window.

        It notes when the person went somewhere of their own - clicked a link,
        sent a form - so a capture of that page is filed as a new clipping,
        not under the link from the message. Permission prompts (camera,
        notifications, location) are refused without asking: nothing the
        morning's sites show needs one."""

        def __init__(self, profile, parent=None):
            super().__init__(profile, parent)
            self.left_tour = False
            #: How many times the person went somewhere of their own on this
            #: page. left_tour alone cannot say it: taking a deleted link's page
            #: off the tour sets it too.
            self.moves = 0
            self.permissionRequested.connect(_refuse)

        def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # noqa: N802 - Qt's name
            # Back and Forward count too: while the tour's link is still
            # loading, wherever the page gets to is taken to be that link -
            # its redirects can go to another site (twitter.com to x.com) -
            # so a Back pressed then must not be filed under it.
            kinds = QWebEnginePage.NavigationType
            if is_main_frame and nav_type in (kinds.NavigationTypeLinkClicked,
                                              kinds.NavigationTypeFormSubmitted,
                                              kinds.NavigationTypeBackForward):
                self.left_tour = True
                self.moves += 1
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)


def _refuse(permission) -> None:
    try:
        permission.deny()
    except Exception:  # noqa: BLE001 - never a crash for a refused prompt
        pass


def _setting(key: str, default):
    from .export_dialog import load_settings

    try:
        return load_settings().get(key, default)
    except Exception:  # noqa: BLE001
        return default


def _remember(key: str, value) -> None:
    from .export_dialog import load_settings, save_settings

    try:
        save_settings({**load_settings(), key: value})
    except Exception:  # noqa: BLE001 - a preference, never a crash
        pass


def prepare() -> bool:
    """Before the QApplication is made: the port, and the flags. Nothing
    opens until the first page is made, and the port is loopback only."""
    global PORT
    if not AVAILABLE:
        return False
    if not PORT:
        PORT = webshot.free_port()
        os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = webshot.debugging_address(PORT)
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        if "--mute-audio" not in flags:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (flags + " --mute-audio").strip()
    return True


def usable() -> bool:
    """Whether the browser inside the program can capture here: it is in
    this build, and there is a screen for its parked window to be drawn on
    - an offscreen platform gives it no surface, so nothing to picture."""
    if not AVAILABLE:
        return False
    try:
        app = QGuiApplication.instance()
        return app is not None and app.platformName() != "offscreen"
    except Exception:  # noqa: BLE001
        return False


def plain_agent(agent: str) -> str:
    """The browser's name without the QtWebEngine token: it is the same
    Chromium, and a site that reads the token serves the odd page."""
    return re.sub(r"\s*QtWebEngine/[\d.]+", "", agent or "").strip()


def profile_home() -> Path:
    from .export_dialog import settings_dir

    home = Path(settings_dir()) / PROFILE_FOLDER
    home.mkdir(parents=True, exist_ok=True)
    return home


def cookie_file() -> Path:
    return profile_home() / "storage" / "Cookies"


def known_sign_ins() -> list:
    """Which sites the program's browser is signed in to, by the name of each
    site's sign-in cookie - from the host when it is running, otherwise from
    its cookie file (names and dates only), so nothing has to open to answer."""
    if Host.made():
        return Host.get().signed_in()
    store = cookie_file()
    if not store.is_file():
        return []
    facts = sitedata.read_cookie_file(store)
    if facts:
        return sitedata.Jar(facts).signed_in_sites()
    try:  # the file could not be read: the note the host keeps
        data = json.loads((profile_home() / SIGN_INS_FILE).read_text(encoding="utf-8"))
        return sorted(str(h) for h in data.get("sites", []) if h in sitedata.SIGN_IN_COOKIES)
    except Exception:  # noqa: BLE001 - never signed in, or not ours
        return []


def _wipe_if_marked(home: Path) -> bool:
    mark = home / WIPE_MARK
    if not mark.is_file():
        return False
    for name in STORAGE_TO_WIPE:
        shutil.rmtree(home / "storage" / name, ignore_errors=True)
    try:
        mark.unlink()
    except OSError:
        pass
    return True


def _fact(cookie) -> sitedata.CookieFact:
    """A cookie as the jar keeps it: its name, site, path and dates. Its value
    is never read."""
    expires = cookie.expirationDate()
    when = None
    if expires.isValid():
        try:
            when = expires.toUTC().toPython().replace(tzinfo=timezone.utc)
        except Exception:  # noqa: BLE001
            when = None
    return sitedata.CookieFact(
        name=bytes(cookie.name().data()).decode("utf-8", "replace"),
        domain=cookie.domain() or "", path=cookie.path() or "/",
        expires=when, created=datetime.now(timezone.utc),
        session=cookie.isSessionCookie())


class Host(QObject):
    """The profile, the parked window and the page that captures - made once,
    on the main thread, the first time anything needs the browser."""

    _one: Optional["Host"] = None
    #: Asked from a worker thread when the parked page stopped answering even
    #: after it was sent to a blank page; answered on the main thread.
    renew_wanted = Signal()
    #: What the sites keep changed (a quarter of a second after the last change).
    jarChanged = Signal()
    signedInChanged = Signal(list)
    cacheCleared = Signal()
    visitedForgotten = Signal()
    #: A site's Sign out left cookies behind: the site, how many.
    signOutLeft = Signal(str, int)

    @classmethod
    def get(cls) -> "Host":
        if cls._one is None:
            cls._one = Host()
        return cls._one

    @classmethod
    def made(cls) -> bool:
        return cls._one is not None

    def __init__(self) -> None:
        super().__init__()
        if not AVAILABLE:
            raise webshot.ShotError("the browser inside the program is not in this build")
        prepare()
        home = profile_home()
        # In this order: a wipe left by Remove everything, then the cookie
        # file - readable only before the engine starts, which locks it -
        # then the profile, the page and its settings, then the connections.
        self.wiped = _wipe_if_marked(home)
        self.jar = sitedata.Jar(sitedata.read_cookie_file(home / "storage" / "Cookies"))
        self.sites: set = set(self.jar.signed_in_sites())
        self.profile = QWebEngineProfile(PROFILE_NAME)
        self.profile.setPersistentStoragePath(str(home / "storage"))
        self.profile.setCachePath(str(home / "cache"))
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.setHttpUserAgent(plain_agent(self.profile.httpUserAgent()))
        store = self.profile.cookieStore()
        self._jar_timer = QTimer(self)
        self._jar_timer.setSingleShot(True)
        self._jar_timer.setInterval(250)
        self._jar_timer.timeout.connect(self.jarChanged)

        self.parking = QWidget()
        self.parking.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint
                                    | Qt.WindowDoesNotAcceptFocus)
        self.parking.setAttribute(Qt.WA_ShowWithoutActivating, True)
        box = QVBoxLayout(self.parking)
        box.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView()
        self.page = self._new_page()
        self.view.setPage(self.page)
        box.addWidget(self.view)
        self.parking.resize(webshot.PAGE_WIDE, 700)
        self.parking.move(*PARK_AT)
        self.parking.show()
        self.parking.move(*PARK_AT)
        self.target_id = self.page.devToolsId()
        self.renew_wanted.connect(self.renew)
        # Names of sites only, as cookies arrive and go - never a value, which
        # is the key to the account.
        store.cookieAdded.connect(self._cookie_added)
        store.cookieRemoved.connect(self._cookie_removed)
        self.profile.clearHttpCacheCompleted.connect(self.cacheCleared)
        self._write_sites()

    @property
    def store(self):
        """The profile's cookie store, asked for each time it is used.

        A Python handle kept for it can go dead while the store itself lives
        on: a page asked for its profile, then deleted - as closing the
        browser window and renew() delete pages - leaves that handle "already
        deleted" (measured offscreen, fixB/repro/probe_profile_owner.py;
        test_embedded section 8 failed on it after section 4 closed its
        window). Asked again, the profile hands out one that works."""
        return self.profile.cookieStore()

    def _new_page(self) -> "QWebEnginePage":
        """The parked page, with its settings. Everything a page needs -
        settings and any signal connected to it - is done here, so a page made
        by renew() has it too."""
        page = QuietPage(self.profile, self.view)
        # No scrollbars on the page that captures: Qt's took 15 pixels of the
        # 820 and showed at the right edge of the cutting.
        page.settings().setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
        # Nobody can see this page to answer a permission prompt.
        page.permissionRequested.connect(_refuse)
        return page

    @Slot()
    def renew(self) -> str:
        """A fresh parked page in place of one that stopped answering. Main
        thread only. Answers the new page's debugging target id.

        The old page is deleted there and then, and its renderer - a script
        still spinning, a whole core of the office PC - goes with it. Left to
        deleteLater it went only when the event loop next came round at its
        own level: while a loop turned inside another (a wait, a pump of
        processEvents) the hung page stayed listed and kept its core busy
        (measured, NOTES: "Capture quality")."""
        old = self.page
        self.page = self._new_page()
        self.view.setPage(self.page)
        self.target_id = self.page.devToolsId()
        if old is not None:
            _delete_now(old)
        return self.target_id

    # ------------------------------------------------------------ sign-ins
    def _cookie_added(self, cookie) -> None:
        fact = _fact(cookie)
        self.jar.add(fact)
        self._changed(sitedata.is_sign_in(fact))

    def _cookie_removed(self, cookie) -> None:
        fact = _fact(cookie)
        self.jar.remove(fact.name, fact.domain, fact.path)
        self._changed(sitedata.is_sign_in(fact))

    def _changed(self, sign_in: bool = True) -> None:
        """What the sites keep changed. Who is signed in is worked out again
        only when the cookie was a sign-in cookie: a news page sets hundreds
        of others as it loads, and going over the whole jar for each cost a
        third of a second per hundred on a well-used profile (review of step
        B)."""
        self._jar_timer.start()
        if not sign_in:
            return
        now = set(self.jar.signed_in_sites())
        if now != self.sites:
            self.sites = now
            self._write_sites()
            self.signedInChanged.emit(sorted(now))

    def _write_sites(self) -> None:
        try:
            (profile_home() / SIGN_INS_FILE).write_text(
                json.dumps({"sites": sorted(self.sites)}), encoding="utf-8")
        except OSError:
            pass

    def signed_in(self) -> list:
        return self.jar.signed_in_sites()

    def sign_out(self, site: str) -> int:
        """Every cookie of one site removed - signed out of it. Answers how
        many were asked to go. Each is removed with its own site's address:
        given none, the engine removes nothing (measured)."""
        facts = self.jar.facts_for(site)
        for fact in facts:
            cookie = self._cookie_for(fact)
            self.store.deleteCookie(cookie, QUrl(sitedata.origin_for(fact)))
        QTimer.singleShot(1500, lambda s=site: self._check_left(s))
        return len(facts)

    @staticmethod
    def _cookie_for(fact):
        from PySide6.QtNetwork import QNetworkCookie

        cookie = QNetworkCookie(fact.name.encode("utf-8"), b"")
        cookie.setDomain(fact.domain)
        cookie.setPath(fact.path or "/")
        return cookie

    def _check_left(self, site: str) -> None:
        left = len(self.jar.facts_for(site))
        if left:
            self.signOutLeft.emit(site, left)

    def forget_sign_ins(self) -> None:
        """Every cookie gone, so the next capture is signed out."""
        self.store.deleteAllCookies()
        self.jar.clear()
        self._changed()

    def clear_cache(self) -> None:
        self.profile.clearHttpCache()

    def forget_visited(self) -> None:
        self.profile.clearAllVisitedLinks()
        try:
            self.page.history().clear()
        except Exception:  # noqa: BLE001
            pass
        self.visitedForgotten.emit()

    def permissions(self) -> list:
        try:
            return list(self.profile.listAllPermissions())
        except Exception:  # noqa: BLE001
            return []

    def remove_everything(self) -> None:
        """Every sign-in, stored page, visited page and permission - now; and
        what pages saved for themselves, the next time the program starts."""
        self.forget_sign_ins()
        self.clear_cache()
        self.forget_visited()
        for permission in self.permissions():
            try:
                permission.reset()
            except Exception:  # noqa: BLE001
                pass
        try:
            (profile_home() / WIPE_MARK).write_text("remove site storage before the "
                                                    "browser starts\n", encoding="utf-8")
        except OSError:
            pass
        self.jarChanged.emit()


def _delete_now(page) -> None:
    try:
        import shiboken6

        shiboken6.delete(page)
    except Exception:  # noqa: BLE001 - never worse than before
        page.deleteLater()


class Catcher(QObject):
    """Captures a list of links over a page of this browser, off the main
    thread: the parked page, or - `as_is` - the page somebody is looking at
    in the browser window, pictured as it is without loading it again.

    The same shape as webclip.Catcher, so the links window drives either.
    """

    caught = Signal(object, object, str)      # found, shot or None, why
    progress = Signal(int, int, str)
    finished = Signal()
    #: Before a failure's `caught`: its address and ShotError kind.
    troubled = Signal(str, str)
    #: Before `caught`, for a post behind a sign-in wall.
    walled = Signal(str)

    def __init__(self, wanted: list, port: int, target_id: str, as_is: bool = False):
        super().__init__()
        self.wanted = list(wanted)
        self.port = port
        self.target_id = target_id
        self.as_is = as_is
        self._stop = False
        self._cut = False
        self._wire = None
        self._lock = threading.Lock()

    def stop(self, now: bool = False) -> None:
        """Stop after the link being captured - or, `now`, straight away: the
        wire is cut, so a call waiting on the page returns at once.

        `now` is for the browser window being closed while it captures. The
        page answers from Qt's main thread, so a capture could not end while
        that thread waited for it: the close held the program for six
        seconds, then failed the link as "stopped answering" (review of step
        B, round 2)."""
        self._stop = True
        if not now:
            return
        with self._lock:
            self._cut = True
            wire = self._wire
        if wire is not None:
            wire.abort()

    def _hold(self, wire):
        """The wire now in use, kept where stop(now=True) can cut it - and cut
        at once if that was asked while it was being made."""
        with self._lock:
            self._wire = wire
            cut = self._cut
        if cut and wire is not None:
            wire.abort()
        return wire

    def _fail(self, row, why: str, kind: str = "") -> None:
        self.troubled.emit(row.url, kind or "")
        if kind == "sign-in":
            self.walled.emit(row.url)
        self.caught.emit(row, None, why)

    @Slot()
    def run(self) -> None:
        wire = None
        total = len(self.wanted)
        try:
            wire, why = self._first_wire()
            self._hold(wire)
            if wire is None:
                for row in self.wanted:
                    self._fail(row, why, "stopped")
                return
            for done, row in enumerate(self.wanted):
                if self._stop:
                    break
                self.progress.emit(done, total, row.site)
                for attempt in (1, 2):
                    try:
                        if wire is None:
                            raise webshot.ShotError(NOT_ANSWERING, kind="stopped")
                        shot = (webshot.capture_current(wire, row.url) if self.as_is
                                else webshot.capture_over(wire, row.url))
                        self.caught.emit(row, shot, "")
                    except webshot.ShotError as bad:
                        # Stuck on the page before, this link was never
                        # opened: it is tried once more on the recovered
                        # page rather than blamed.
                        again = attempt == 1 and bad.kind == "stopped" and bad.unopened
                        if not again:
                            self._fail(row, str(bad), bad.kind)
                        if bad.kind == "stopped" and not self._stop:
                            # One page that stopped answering never poisons
                            # the rest of the list: a fresh wire, and if the
                            # page is still stuck, a fresh page.
                            wire = self._hold(self._fresh_wire(wire))
                        if again:
                            if wire is not None and not self._stop:
                                continue
                            self._fail(row, str(bad), bad.kind)
                    except Exception as bad:  # noqa: BLE001 - one link, never the lot
                        self._fail(row, f"it could not be read ({bad})")
                    break
                self.progress.emit(done + 1, total, row.site)
        finally:
            if wire is not None:
                wire.close()
            self.finished.emit()
            here = QThread.currentThread()
            if here is not None:
                here.quit()

    def _first_wire(self):
        """A wire to the page that answers, before the first link - or None
        and the words to fail the links with.

        The parked page can be left stuck by the list before: Hindustan Times
        captures in six seconds and stops answering at nine, after the list
        has finished. Attached with the old 30 s limits, every link of every
        later list failed until the program was closed. So the page gets a
        few seconds to answer, and one that does not is unstuck, or replaced,
        first. The page in a browser window is attached to by its own id
        only - never mistaken for another page.

        The wire is handed to _hold the moment it is connected, before the
        page is asked anything, and a cut asked for meanwhile ends the capture
        here. Held only once this had returned, a stop(now=True) in the
        capture's first moment - the program ending - had nothing to cut, and
        the thread outlived the program (review of step B, round 3)."""
        if self._cut:
            return None, NOT_ANSWERING
        try:
            wire = webshot.attach(self.port, self.target_id, exact=self.as_is,
                                  seconds=ATTACH_SECONDS, hold=self._hold)
        except webshot.ShotError as bad:
            if self._cut or bad.kind != "stopped":
                return None, f"{NOT_ANSWERING} ({bad})"
            wire = None
        except Exception as bad:  # noqa: BLE001 - the port did not answer
            return None, f"{NOT_ANSWERING} ({bad})"
        if self._cut:
            if wire is not None:
                wire.close()
            return None, NOT_ANSWERING
        if wire is not None:
            if webshot.answers(wire, 3.0):
                return wire, ""
            wire.close()
        wire = self._fresh_wire(None)
        if wire is None:
            return None, f"{NOT_ANSWERING} ({webshot.WIRE_STOPPED})"
        return wire, ""

    def _fresh_wire(self, old):
        """A wire that answers, after a page stopped answering: the same page
        re-attached, or - for the parked page only, never a window somebody
        is reading - the page sent to a blank page, or a new page made in its
        place. None if none of them answers."""
        stuck = old is None or getattr(old, "stuck", True)
        if old is not None:
            old.close()
        if not stuck:
            try:
                wire = webshot.attach(self.port, self.target_id, exact=True, seconds=ATTACH_SECONDS)
                if webshot.answers(wire, 3.0):
                    return wire
                wire.close()
            except Exception:  # noqa: BLE001 - try a new page instead
                pass
        host = Host._one
        if host is None or host.target_id != self.target_id:
            return None
        # A blank page unsticks a page stuck in a script at once, needing
        # nothing of the stuck page - unless the capture has just tried it.
        if old is None or not getattr(old, "stuck", False):
            wire = webshot.revive(self.port, self.target_id)
            if wire is not None:
                return wire
        was = host.target_id
        host.renew_wanted.emit()               # made on the main thread
        until = time.time() + RENEW_SECONDS
        while time.time() < until and not self._stop:
            now = host.target_id
            if now != was:
                try:
                    wire = webshot.attach(self.port, now, exact=True)
                    if webshot.answers(wire, 3.0):
                        self.target_id = now
                        return wire
                    wire.close()
                except Exception:  # noqa: BLE001 - not listed yet
                    pass
            time.sleep(0.2)
        return None


# ------------------------------------------------------------ the window
class AddressBar(QLineEdit):
    """The browser's address bar. A link dropped on it, or pasted into it
    while it is empty or wholly selected, opens at once; a paste into the
    middle of a typed address stays a paste. The right-click menu has
    Paste and go."""

    go = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setPlaceholderText("Type an address, or drop or paste a link")

    @staticmethod
    def link_in(mime) -> str:
        if mime is None:
            return ""
        text = mime.text() if mime.hasText() else ""
        found = links.find(text) or links.find(
            "\n".join(u.toString() for u in mime.urls() if not u.isLocalFile()))
        return found[0].url if found else ""

    def _open_on_paste(self) -> bool:
        return not self.text().strip() or self.selectedText() == self.text()

    def dragEnterEvent(self, event):  # noqa: N802 - Qt's name
        if self.link_in(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802 - Qt's name
        if self.link_in(event.mimeData()):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802 - Qt's name
        url = self.link_in(event.mimeData())
        if not url:
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        self.setText(url)
        self.go.emit(url)

    def keyPressEvent(self, event):  # noqa: N802 - Qt's name
        if event.matches(QKeySequence.Paste) and self._open_on_paste() and self.paste_and_go():
            event.accept()
            return
        super().keyPressEvent(event)

    def paste_and_go(self) -> bool:
        """The link on the clipboard, opened. False when there is none."""
        url = self.link_in(QGuiApplication.clipboard().mimeData())
        if not url:
            return False
        self.setText(url)
        self.go.emit(url)
        return True

    def menu(self):
        menu = self.createStandardContextMenu()
        action = QAction("Paste and go", menu)
        action.setData("paste-and-go")
        action.setEnabled(bool(self.link_in(QGuiApplication.clipboard().mimeData())))
        action.triggered.connect(self.paste_and_go)
        first = menu.actions()[0] if menu.actions() else None
        menu.insertAction(first, action)
        if first is not None:
            menu.insertSeparator(first)
        return menu

    def contextMenuEvent(self, event):  # noqa: N802 - Qt's name
        menu = self.menu()
        menu.setAttribute(Qt.WA_DeleteOnClose, True)
        menu.popup(event.globalPos())


#: Pages that say which video or post they are in the query, not the path -
#: and the keys that say it. YouTube and Facebook go on to another video or
#: post with history.pushState, which no navigation request announces, so
#: without these keys another video was filed under the link that was sent,
#: with the sender's words, and that link ticked as captured (review of step
#: B, round 2). Only these keys count, and only when both addresses carry
#: one: a site rewrites the rest of its query once the page has loaded (a
#: Facebook share link drops rdid, Times of India adds from=mdr), which must
#: not make the link that was sent "another page".
_STORY_IN_QUERY = {
    "watch": ("v",),                           # youtube.com/watch?v=, facebook.com/watch/?v=
    "video.php": ("v",),
    "story.php": ("story_fbid", "id"),
    "permalink.php": ("story_fbid", "id"),
    "photo": ("fbid",),
    "photo.php": ("fbid",),
}


def _page_key(url: str):
    rest = (url or "").split("://", 1)[-1].split("#", 1)[0]
    rest, _, query = rest.partition("?")
    host, _, path = rest.partition("/")
    host = host.lower()
    host = host[4:] if host.startswith("www.") else host
    path = path.rstrip("/")
    wanted = _STORY_IN_QUERY.get(path.rsplit("/", 1)[-1].lower(), ())
    said = {}
    for pair in query.split("&") if wanted else ():
        name, _, value = pair.partition("=")
        if name in wanted and value:
            said[name] = value
    return host, path, said


def _same_page(one: str, two: str) -> bool:
    if not (one and two):
        return False
    host, path, said = _page_key(one)
    other_host, other_path, other_said = _page_key(two)
    return ((host, path) == (other_host, other_path)
            and all(said[name] == other_said[name] for name in said.keys() & other_said.keys()))


class PopupWindow(QDialog):
    """A page's own pop-up - "Sign in with Google" - in a small window on the
    same profile, so the sign-in it makes is the browser's. It closes when
    the page closes it."""

    def __init__(self, profile, parent=None):
        super().__init__(parent)
        self.setModal(False)
        self.setWindowTitle("Sign in")
        self.resize(520, 680)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        self.page = QWebEnginePage(profile, self.view)
        self.page.permissionRequested.connect(_refuse)
        self.page.windowCloseRequested.connect(self.close)
        self.page.newWindowRequested.connect(lambda request: self.page.setUrl(request.requestedUrl()))
        self.page.titleChanged.connect(lambda title: self.setWindowTitle(title or "Sign in"))
        self.view.setPage(self.page)
        box.addWidget(self.view)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    def keyPressEvent(self, event):  # noqa: N802 - Qt's name
        # Esc belongs to the sign-in page (closing its own box). Passed on,
        # QDialog hid the pop-up without closing it, so it was never deleted.
        if event.key() == Qt.Key_Escape:
            event.accept()
            return
        super().keyPressEvent(event)


class BrowserWindow(QDialog):
    """A window of the program's own to sign in, look, and capture from.

    The page shown here and the parked page that captures share one profile,
    so a sign-in made here is the sign-in every capture has. Opened from the
    links window it tours the message's links, and "Capture this page"
    pictures the page as it is shown, filed under the link from the message
    with the sender's words - unless the person went to another page, which
    is filed as a new clipping of its own.

    The links window keeps one of these. Closing it - Close, the window's own
    close button, or Esc outside the page - puts it away: its watch stops, a
    capture is stopped, its pop-ups close and its page is replaced by a blank
    one, so no news page goes on running behind it; opening it again shows the
    same window. A new window each time left every old one alive with its page
    loaded and its panel still filled on every cookie (review of step B).
    """

    captured = Signal(object)          # the clipping id
    linkCaptured = Signal(str, object)  # the link from the message, the clipping id
    linkFailed = Signal(str, str, str)  # the link, why, the ShotError kind
    atLink = Signal(str)               # the tour moved to this link

    def __init__(self, window, url: str = "", parent=None, tour=None, at: int = 0,
                 panel: bool = False, login: str = ""):
        super().__init__(parent or window)
        from .sitepanel import SitePanel

        self.window = window
        self.host = Host.get()
        self.thread = None
        self.catcher = None
        self.tour: list = []
        self.at = 0
        self.pending_login = False
        #: Where the link on the screen was, once it has gone from the links
        #: window's list: the place of the link that took its place, which
        #: Next opens (len(tour) when there is none). None while the page on
        #: the screen is one of the list's links, or the person's own.
        self._gone = None
        #: While _gone is set: the link that went, and how its page stood then
        #: - so the page goes back on the tour if the link comes back.
        self._gone_was = None
        self._done: dict = {}
        self._landed = ""
        self._tour_load = False
        self._capturing = None
        self._last_kind = ""
        self._succeeded = False
        self._popups: list = []
        self._page_token = 0
        self._asked = 0.0
        self._load_began = time.monotonic()
        self._stuck_kind = ""
        self._away = False             # closed, and kept to be shown again
        self._closing = False          # inside closeEvent: reject may hide now
        self._ending = False           # the program is ending: no fresh page
        self.setWindowTitle("Browser inside the program")
        self.setModal(False)
        self.resize(1180, 820)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 8)
        outer.setSpacing(6)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.menu_btn = QPushButton("☰")
        self.menu_btn.setCheckable(True)
        self.menu_btn.setFixedWidth(38)
        self.menu_btn.setToolTip("Sign-ins and what the sites have saved")
        self.back = QPushButton("‹")
        self.back.setFixedWidth(34)
        self.back.setToolTip("Back (Alt+Left)")
        self.forward = QPushButton("›")
        self.forward.setFixedWidth(34)
        self.forward.setToolTip("Forward (Alt+Right)")
        self.reload = QPushButton("↻")
        self.reload.setFixedWidth(34)
        self.reload.setToolTip("Reload (F5)")
        self.address = AddressBar()
        self.go = QPushButton("Go")
        self.capture = QPushButton("Capture this page")
        self.capture.setObjectName("NavyFilled")
        self.capture.setToolTip(
            "The story, or the post, cut out of this page as you see it now - its "
            "pictures loaded, any pop-up you closed still closed (Ctrl+Enter).")
        for button in (self.menu_btn, self.back, self.forward, self.reload, self.go, self.capture):
            button.setCursor(Qt.PointingHandCursor)
        for widget in (self.menu_btn, self.back, self.forward, self.reload):
            bar.addWidget(widget)
        bar.addWidget(self.address, 1)
        bar.addWidget(self.go)
        bar.addWidget(self.capture)
        outer.addLayout(bar)

        self.loading = QProgressBar()
        self.loading.setTextVisible(False)
        self.loading.setFixedHeight(3)
        self.loading.setRange(0, 100)
        self.loading.hide()
        outer.addWidget(self.loading)

        # The link tour: Previous | 3 of 12 · site · headline | Next, and
        # whether this link is captured yet.
        self.tour_strip = QFrame()
        self.tour_strip.setObjectName("TourStrip")
        strip = QHBoxLayout(self.tour_strip)
        strip.setContentsMargins(8, 4, 8, 4)
        strip.setSpacing(6)
        self.prev_link = QPushButton("‹ Previous")
        self.tour_pick = QComboBox()
        self.tour_pick.setMinimumContentsLength(40)
        self.tour_pick.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.next_link_btn = QPushButton("Next ›")
        self.tour_chip = QLabel()
        self.tour_chip.setObjectName("TourChip")
        self.then_next = QCheckBox("Then open the next link")
        self.then_next.setChecked(bool(_setting(THEN_NEXT_KEY, True)))
        self.then_next.setToolTip("After a capture, the next link opens by itself.")
        for button in (self.prev_link, self.next_link_btn):
            button.setCursor(Qt.PointingHandCursor)
        strip.addWidget(self.prev_link)
        strip.addWidget(self.tour_pick, 1)
        strip.addWidget(self.next_link_btn)
        strip.addWidget(self.tour_chip)
        strip.addWidget(self.then_next)
        self.tour_strip.hide()
        outer.addWidget(self.tour_strip)

        # A page that stopped responding, or whose process stopped.
        self.stuck = QFrame()
        self.stuck.setObjectName("StuckNote")
        stuck = QHBoxLayout(self.stuck)
        stuck.setContentsMargins(10, 4, 6, 4)
        self.stuck_words = QLabel(STUCK_WORDS)
        self.stuck_reload = QPushButton("Reload")
        self.stuck_skip = QPushButton("Skip to the next link")
        for button in (self.stuck_reload, self.stuck_skip):
            button.setCursor(Qt.PointingHandCursor)
        stuck.addWidget(self.stuck_words, 1)
        stuck.addWidget(self.stuck_reload)
        stuck.addWidget(self.stuck_skip)
        self.stuck.hide()
        outer.addWidget(self.stuck)

        self.view = QWebEngineView()
        self.page = self._make_page()
        self.view.setPage(self.page)
        self.panel = SitePanel(self.host, self)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.panel)
        self.splitter.addWidget(self.view)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([330, 850])
        self.splitter.setChildrenCollapsible(False)
        # Esc on the page, or in the panel, is not "close the browser": a
        # page's own box or picture viewer closes on Esc, and the key the
        # page did not use comes back up through here to the window.
        self.splitter.installEventFilter(self)
        outer.addWidget(self.splitter, 1)
        #: Kept for anything that still presses the old footer button.
        self.forget = self.panel.forget_all

        foot = QHBoxLayout()
        self.note = QLabel(
            "Sign in here once - X, Facebook, Instagram - and every capture after that "
            "is signed in. Your everyday Chrome is not touched.")
        self.note.setWordWrap(True)
        self.note.setStyleSheet(f"color: {theme.MUTED};")
        foot.addWidget(self.note, 1)
        close = QPushButton("Close")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.close)
        foot.addWidget(close)
        outer.addLayout(foot)

        self.menu_btn.toggled.connect(self._panel_toggled)
        self.back.clicked.connect(self.view.back)
        self.forward.clicked.connect(self.view.forward)
        self.reload.clicked.connect(self.view.reload)
        self.go.clicked.connect(self._go)
        self.address.returnPressed.connect(self._go)
        self.address.go.connect(self._open_typed)
        self.capture.clicked.connect(self._capture)
        self.prev_link.clicked.connect(self.previous_link)
        self.next_link_btn.clicked.connect(self.next_link)
        self.tour_pick.activated.connect(self.go_to)
        self.then_next.toggled.connect(lambda on: _remember(THEN_NEXT_KEY, bool(on)))
        self.stuck_reload.clicked.connect(self._reload_stuck)
        self.stuck_skip.clicked.connect(self._skip_stuck)
        # A sign-in from the panel keeps the tour's link waiting, as the
        # links window's Sign in does: Next › brings it back afterwards. As a
        # typed address it was skipped, and "Capture again" took the wrong page.
        self.panel.openAddress.connect(self.open_login)
        self.host.visitedForgotten.connect(self._forget_history)
        self.view.urlChanged.connect(self._url_changed)
        self.view.titleChanged.connect(self._retitle)
        self.view.loadStarted.connect(self._load_started)
        self.view.loadProgress.connect(self.loading.setValue)
        self.view.loadFinished.connect(self._load_finished)
        self.view.renderProcessTerminated.connect(self._process_ended)
        for keys, call in (("Alt+Left", self.view.back), ("Alt+Right", self.view.forward),
                           ("Alt+PgDown", self.next_link), ("Alt+PgUp", self.previous_link),
                           ("Ctrl+Return", self._capture), ("Ctrl+Enter", self._capture),
                           ("F5", self.view.reload)):
            QShortcut(QKeySequence(keys), self, call)

        self._watch = QTimer(self)
        self._watch.setInterval(WATCH_MS)
        self._watch.timeout.connect(self._watch_tick)
        self._watch.start()
        # A capture given up when the window closed ends by itself within a
        # moment; this makes certain it has ended before the program does,
        # because a thread still running then ends the process with a crash.
        app = QGuiApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._end_capture)

        self.show_panel(bool(panel) or bool(_setting(PANEL_KEY, False)), remember=False)
        if tour:
            self.set_tour(tour, at, open_now=not (url or login))
        if login:
            self.open_login(login)
        elif url:
            self.open(url)

    def _make_page(self):
        page = TourPage(self.host.profile, self.view)
        page.newWindowRequested.connect(self._new_window)
        return page

    # ---------------------------------------------------------- browsing
    def open(self, url: str) -> None:
        if "://" not in url and not url.startswith(("about:", "data:")):
            url = "https://" + url
        self.address.setText(url)
        self.view.setUrl(QUrl(url))

    def _go(self) -> None:
        typed = self.address.text().strip()
        if typed:
            self._open_typed(typed)

    def open_login(self, url: str) -> None:
        """A site's sign-in page first, with the tour's current link waiting:
        Next › opens that link once the person has signed in."""
        self.pending_login = bool(self.tour)
        self.page.moves += 1
        self.open(url)
        self._sync_tour()

    def _open_typed(self, url: str) -> None:
        """An address the person typed, dropped or chose: their own page, not
        the tour's link."""
        self.page.left_tour = True
        self.page.moves += 1
        self.open(url)
        self._sync_tour()

    def _url_changed(self, where) -> None:
        url = where.toString()
        self.address.setText("" if url == "about:blank" else url)
        if self._tour_load and not self.page.left_tour:
            # The tour's link on its way - through its redirects.
            self._landed = url
        was = self._gone_was
        if was is not None and was["loading"] and not was["left"] and was["page"] is self.page:
            # Its link gone from the list while it loads: followed as ever,
            # in case the link comes back.
            was["landed"] = url
        self._sync_tour()

    def _retitle(self, title: str) -> None:
        self.setWindowTitle(f"{title} — browser inside the program"
                            if title and title != "about:blank" else "Browser inside the program")

    def is_blank(self) -> bool:
        """No page open: a new window, or one put away when it was closed."""
        return self.view.url().toString() in ("", "about:blank")

    def _load_started(self) -> None:
        self.loading.setValue(0)
        self.loading.show()
        self._load_began = time.monotonic()
        self._page_token += 1          # a question to the page before is void
        self._asked = 0.0
        if self._stuck_kind == "stopped":
            self._hide_stuck()

    def _load_finished(self, _ok: bool) -> None:
        self.loading.hide()
        if self._tour_load:
            self._tour_load = False
            self._landed = self.view.url().toString()
        was = self._gone_was
        if was is not None and was["loading"] and was["page"] is self.page:
            was["loading"] = False
            was["landed"] = self.view.url().toString()
        self._sync_tour()

    def _new_window(self, request) -> None:
        """A page's pop-up (a sign-in with Google) in a small window of its
        own on the same profile; a link meant for a new tab, here."""
        kinds = QWebEngineNewWindowRequest.DestinationType
        if request.destination() in (kinds.InNewDialog, kinds.InNewWindow):
            popup = PopupWindow(self.host.profile, self)
            geometry = request.requestedGeometry()
            if geometry.isValid() and geometry.width() > 200 and geometry.height() > 200:
                popup.resize(geometry.width(), geometry.height())
            self._popups.append(popup)
            popup.destroyed.connect(lambda _=None, p=popup: self._popups.remove(p)
                                    if p in self._popups else None)
            request.openIn(popup.page)
            popup.show()
            return
        self._open_typed(request.requestedUrl().toString())

    def _forget_history(self) -> None:
        try:
            self.page.history().clear()
        except Exception:  # noqa: BLE001
            pass

    def show_panel(self, on: bool, remember: bool = True) -> None:
        """The ☰ panel shown or hidden - remembered for the next window only
        when `remember`. The button is set without its signal: its signal is
        the person pressing ☰, which is always remembered, and it saved the
        panel as open when "Saved sign-ins and site data…" opened it (review
        of step B). The panel fills itself when it is shown."""
        on = bool(on)
        self.menu_btn.blockSignals(True)
        try:
            self.menu_btn.setChecked(on)
        finally:
            self.menu_btn.blockSignals(False)
        self.panel.setVisible(on)
        if remember:
            _remember(PANEL_KEY, on)

    def _panel_toggled(self, on: bool) -> None:
        self.panel.setVisible(bool(on))
        _remember(PANEL_KEY, bool(on))

    # ------------------------------------------------------------ the tour
    def set_tour(self, found: list, at: int = 0, open_now: bool = True) -> None:
        self.tour = list(found or [])
        self._gone = self._gone_was = None
        self.tour_strip.setVisible(bool(self.tour))
        if not self.tour:
            self._fill_pick()
            return
        self.at = max(0, min(int(at), len(self.tour) - 1))
        self._fill_pick()
        if open_now:
            self.go_to(self.at)
        else:
            self._sync_tour()

    def update_tour(self, found: list) -> None:
        """The links window's list changed: the same link stays current.

        When the link on the screen has gone from the list - its lines were
        deleted, or its address edited - the page on the screen is no longer
        any link's. It is taken off the tour, so Capture this page files it as
        a new clipping, and Next opens the link that took its place. Kept at
        its old place in the list, the link after it was taken for this page:
        Capture filed this page's picture under it with its sender's words and
        ticked it, and Next skipped it (review of step B, round 2).

        A slip put right at once brings it back. One keystroke typed back, or
        Ctrl+Z after its lines were deleted, left the page off the tour for
        good: filed as a new clipping with the page's title, its row
        unticked, and skipped by Next (review of step B, round 3). So when the
        link is in the list again, and the person has not gone anywhere of
        their own on this page meanwhile, the page is that link again, as it
        stood."""
        old = self.tour
        self.tour = list(found or [])
        self.tour_strip.setVisible(bool(self.tour))
        if self._gone is not None:
            if not self._gone_back():
                self._gone = self._place(old, self._gone)
        else:
            current = old[self.at].url if 0 <= self.at < len(old) else ""
            where = self._index_of(current)
            if where is not None:
                self.at = where
            elif current:
                self._gone_was = {"url": current, "page": self.page, "moves": self.page.moves,
                                  "left": self.page.left_tour, "loading": self._tour_load,
                                  "landed": self._landed, "login": self.pending_login}
                self._gone = self._place(old, self.at)
                self.page.left_tour = True
                self._tour_load = False
                self._landed = ""
                self.pending_login = False
        if self._gone is not None:
            self.at = self._gone
        self.at = max(0, min(self.at, len(self.tour) - 1))
        self._fill_pick()
        self._sync_tour()

    def _gone_back(self) -> bool:
        """Whether the link that went from the list is back in it, its page
        still the one on the screen and untouched by the person - and if so,
        that page is put back on the tour as it stood."""
        was = self._gone_was
        if was is None:
            return False
        where = self._index_of(was["url"])
        if where is None or was["page"] is not self.page or self.page.moves != was["moves"]:
            return False
        self.at = where
        self._gone = self._gone_was = None
        self.page.left_tour = was["left"]
        self._tour_load = was["loading"]
        self._landed = was["landed"]
        self.pending_login = was["login"]
        return True

    def _index_of(self, url: str):
        key = str(url or "").lower()
        if not key:
            return None
        return next((i for i, row in enumerate(self.tour) if row.url.lower() == key), None)

    def _place(self, old: list, index: int) -> int:
        """Where, in the list as it is now, the link at `index` of the old
        list is - or the first link after it that is still there, or the place
        after the last one before it that is. len(tour) when none is."""
        for row in old[index:]:
            where = self._index_of(row.url)
            if where is not None:
                return where
        for row in reversed(old[:index]):
            where = self._index_of(row.url)
            if where is not None:
                return where + 1
        return min(index, len(self.tour))

    def _after_index(self):
        """The link Next opens after the page on the screen: the next in the
        list - or, when the link on the screen has gone from the list, the
        one that took its place. None at the end."""
        if self._gone is not None:
            return self._gone if self._gone < len(self.tour) else None
        return self.at + 1 if self.at + 1 < len(self.tour) else None

    def _before_index(self):
        if self._gone is not None:
            return self._gone - 1 if 0 < self._gone <= len(self.tour) else None
        return self.at - 1 if self.at > 0 else None

    def _fill_pick(self) -> None:
        self.tour_pick.blockSignals(True)
        try:
            self.tour_pick.clear()
            many = len(self.tour)
            for index, row in enumerate(self.tour):
                done = self._done.get(row.url.lower(), False)
                label = (row.label or row.url)[:70]
                self.tour_pick.addItem(f"{'✓ ' if done else ''}{index + 1} of {many} · "
                                       f"{row.site} · {label}", row.url)
            if self.tour:
                self.tour_pick.setCurrentIndex(self.at)
        finally:
            self.tour_pick.blockSignals(False)

    def go_to(self, index: int) -> None:
        if not 0 <= int(index) < len(self.tour):
            return
        self.at = int(index)
        self._gone = self._gone_was = None
        self.pending_login = False
        self.page.left_tour = False
        self._tour_load = True
        self._landed = ""
        self.open(self.tour[self.at].url)
        self._sync_tour()
        self.atLink.emit(self.tour[self.at].url)

    def next_link(self) -> None:
        if not self.tour:
            return
        if self.pending_login and self._gone is None:
            self.go_to(self.at)            # signed in: now the link that waited
            return
        after = self._after_index()
        if after is None:
            self.note.setText("That was the last link.")
        else:
            self.go_to(after)

    def previous_link(self) -> None:
        before = self._before_index() if self.tour else None
        if before is not None:
            self.go_to(before)

    def mark(self, url: str, done: bool) -> None:
        key = str(url or "").lower()
        if self._done.get(key, False) == bool(done):
            return
        self._done[key] = bool(done)
        self._fill_pick()
        self._sync_tour()

    def on_tour_link(self) -> bool:
        """Whether the page on the screen is the tour's current link - as it
        was sent, or where it landed after its redirects - and not a page the
        person went to themselves.

        Where it landed may be another site: youtu.be goes on to youtube.com,
        fb.watch to facebook.com, twitter.com to x.com. The same-site test
        that came first here filed every one of those as a new clipping, with
        the page's title instead of the sender's words, left the row unticked
        and never moved on (review of step B). What the person did themselves
        - a link clicked, a form sent, Back or Forward, an address typed - is
        noted on the page as it happens (TourPage.left_tour)."""
        if (not self.tour or not 0 <= self.at < len(self.tour) or self.pending_login
                or self._gone is not None):
            return False
        if self.page.left_tour:
            return False
        if self._tour_load:
            return True                    # still on its way to the link
        here = self.view.url().toString()
        return _same_page(here, self.tour[self.at].url) or _same_page(here, self._landed)

    def _sync_tour(self) -> None:
        if not self.tour:
            return
        self.tour_pick.blockSignals(True)
        self.tour_pick.setCurrentIndex(self.at)
        self.tour_pick.blockSignals(False)
        self.prev_link.setEnabled(self._before_index() is not None)
        self.next_link_btn.setEnabled((self.pending_login and self._gone is None)
                                      or self._after_index() is not None)
        self.stuck_skip.setVisible(self._after_index() is not None)
        done = self._done.get(self.tour[self.at].url.lower(), False)
        if self.pending_login:
            text = "Sign in, then press Next › for the link"
        elif not self.on_tour_link():
            text = "Another page — Capture files it as a new clipping"
        else:
            text = "Captured ✓" if done else "Not captured yet"
        self.tour_chip.setText(text)
        self.tour_chip.setProperty("done", bool(done) and text.startswith("Captured"))
        self.tour_chip.style().unpolish(self.tour_chip)
        self.tour_chip.style().polish(self.tour_chip)

    # ------------------------------------------------------------ capture
    def _capture(self) -> None:
        if self.thread is not None:
            return
        url = self.view.url().toString() or self.address.text().strip()
        if not url or url == "about:blank":
            return
        tagged = self.on_tour_link()
        found = (self.tour[self.at] if tagged
                 else links.Found(url=url, label=self.view.title() or ""))
        self._capturing = (found, tagged)
        self._last_kind = ""
        self._succeeded = False
        self.capture.setEnabled(False)
        self.note.setText(f"Capturing {found.site} as you see it…"
                          + (f" (filed as link {self.at + 1})" if tagged else ""))
        self.thread = QThread(self)
        self.catcher = Catcher([found], PORT, self.page.devToolsId(), as_is=True)
        self.catcher.moveToThread(self.thread)
        self.thread.started.connect(self.catcher.run)
        self.catcher.troubled.connect(self._troubled)
        self.catcher.caught.connect(self._caught)
        self.catcher.finished.connect(self._done_capturing)
        self.thread.start()

    @Slot(str, str)
    def _troubled(self, _url: str, kind: str) -> None:
        self._last_kind = kind

    @Slot(object, object, str)
    def _caught(self, found, shot, why: str) -> None:
        if self._capturing is None:
            # Given up when the window was closed: its answer is not wanted,
            # neither a clipping nor a failure to mark the link with.
            return
        tagged = bool(self._capturing and self._capturing[1])
        if shot is None:
            if tagged:
                self.linkFailed.emit(found.url, why, self._last_kind)
            if self._last_kind == "sign-in":
                site = sitedata.site_of(found.site)
                name = sitedata.name_of(site)
                how = (f"☰ → Sign in to {name}" if site in sitedata.LOGIN_PAGES
                       else f"sign in on {name}'s own page here")
                # After signing in the post is no longer on the screen, so
                # "Capture again" would have taken the sign-in page.
                then = ("then press Next › to come back to this post and capture it" if tagged
                        else "then open the post again and capture it")
                self.note.setText(f"This post needs a sign-in: {how}, {then}.")
            else:
                self.note.setText(f"Not captured: {why}")
            return
        clip_id = self.window.clip_from_link(shot, found)
        if clip_id is not None:
            self._succeeded = True
            self.captured.emit(clip_id)
            if tagged:
                self.mark(found.url, True)
                self.linkCaptured.emit(found.url, clip_id)
            self.note.setText(f"Captured {shot.site} — it is in the list.")

    @Slot()
    def _done_capturing(self) -> None:
        """A capture ended - or one given up when the window was closed. The
        thread is let go only here, after every answer it sent has arrived:
        until then Capture this page does nothing, so an answer of the capture
        given up can never be taken for a new one's."""
        thread, self.thread = self.thread, None
        self.catcher = None
        if thread is not None:
            thread.quit()
            thread.wait(4000)              # it has finished: nothing is left to wait for
            thread.deleteLater()
        self.capture.setEnabled(True)
        given_up = self._capturing is None
        tagged = bool(self._capturing and self._capturing[1])
        self._capturing = None
        if given_up:
            self.note.setText("The capture was stopped when the window was closed.")
        if self._away:
            # Closed while it ran: the blank page, and the news page and its
            # renderer deleted, now that nothing is capturing over them - but
            # no fresh page made while the program itself ends.
            if not self._ending:
                self._renew_page()
            return
        if (self._succeeded and tagged and self.then_next.isChecked()
                and self._after_index() is not None and self.isVisible()):
            self.next_link()

    def _end_capture(self) -> None:
        """The program is ending: a capture still running is cut, and waited
        for with the events still turning.

        In its first moment a capture is still finding the page and attaching
        to it, and the page answers that from this thread. A plain wait here
        could not be answered, the cut had no wire yet to cut, and the wait
        ran out after 3 s with the thread still running: deleting the window
        then ended the process with a crash, 0xC0000409 (review of step B,
        round 3). With the events turning the page answers, the wire is made
        and cut at once, and the thread ends in a moment. Its answers are not
        wanted, and no fresh page is put in."""
        thread = self.thread
        if thread is None:
            return
        self._ending = True
        self._capturing = None
        if self.catcher is not None:
            self.catcher.stop(now=True)
        until = time.monotonic() + END_SECONDS
        others = QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
        try:
            while self.thread is thread and thread.isRunning() and time.monotonic() < until:
                QCoreApplication.processEvents(others, 50)
                thread.wait(20)
        except RuntimeError:               # let go and deleted meanwhile: it had ended
            pass

    # ------------------------------------------------------- the watchdog
    def _watch_tick(self) -> None:
        """Whether the page on the screen still runs a script. The engine can
        stop answering on a page and never recover (hindustantimes.com, step
        C); somebody looking at it is told, with Reload and Skip."""
        if not self.isVisible() or self.thread is not None:
            return
        now = time.monotonic()
        if self._asked:
            if (now - self._asked >= HUNG_SECONDS
                    and now - self._load_began >= WATCH_GRACE_SECONDS):
                self._show_stuck("stopped")
            return
        self._asked = now
        token = self._page_token
        _ask(self.page, lambda _value, t=token: self._answered(t))

    def _answered(self, token: int) -> None:
        if token != self._page_token:
            return
        self._asked = 0.0
        if self._stuck_kind == "stopped":
            self._hide_stuck()

    def _process_ended(self, status, _code=0) -> None:
        try:
            normal = status == QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus
        except Exception:  # noqa: BLE001
            normal = False
        if not normal:
            self._show_stuck("crashed")

    def _show_stuck(self, kind: str) -> None:
        self._stuck_kind = kind
        self.stuck_words.setText(STUCK_WORDS if kind == "stopped" else CRASHED_WORDS)
        self.stuck_skip.setVisible(bool(self.tour) and self._after_index() is not None)
        self.stuck.show()

    def _hide_stuck(self) -> None:
        self._stuck_kind = ""
        self.stuck.hide()

    def _renew_page(self) -> None:
        """A fresh page in the window in place of one that stopped - the
        stuck one, and its renderer, deleted there and then."""
        old = self.page
        self.page = self._make_page()
        self.view.setPage(self.page)
        self._page_token += 1
        self._asked = 0.0
        _delete_now(old)

    def _reload_stuck(self) -> None:
        url = self.view.url().toString() or self.address.text().strip()
        was_tour = self.on_tour_link() if self.tour else False
        self._hide_stuck()
        self._renew_page()
        if was_tour:
            self.go_to(self.at)
        elif url:
            self.open(url)

    def _skip_stuck(self) -> None:
        self._hide_stuck()
        self._renew_page()
        self.next_link()

    # ------------------------------------------------- closing, and again
    def eventFilter(self, obj, event):  # noqa: N802 - Qt's name
        if (obj is self.splitter and event.type() == QEvent.KeyPress
                and event.key() == Qt.Key_Escape):
            event.accept()
            return True
        return super().eventFilter(obj, event)

    def reject(self) -> None:
        """Esc: through close(), so the window is put away as a close puts it
        away. QDialog's own Esc only hid it - its watch went on running, and a
        capture and the pop-ups were left open (review of step B). QDialog's
        closeEvent calls reject() itself, which then really hides."""
        if self._closing:
            super().reject()
        else:
            self.close()

    def closeEvent(self, event):  # noqa: N802 - Qt's name
        self._put_away()
        self._closing = True
        try:
            super().closeEvent(event)
        finally:
            self._closing = False

    def showEvent(self, event):  # noqa: N802 - Qt's name
        super().showEvent(event)
        self._away = False
        self._asked = 0.0
        self._load_began = time.monotonic()
        if not self._watch.isActive():
            self._watch.start()

    def _put_away(self) -> None:
        """Closed: kept to be shown again, doing nothing meanwhile."""
        if self._away:
            return
        self._away = True
        self._watch.stop()
        if self.thread is not None:
            # A capture running is given up, never waited for. The page
            # answers it from this thread, so a wait here could only run out:
            # the close held the program for six seconds and then failed the
            # link as "stopped answering" (review of step B, round 2). Its
            # wire is cut, so it ends in a moment by itself; its answer is not
            # wanted; and the thread is kept until _done_capturing, which puts
            # the blank page in then.
            self._capturing = None
            if self.catcher is not None:
                self.catcher.stop(now=True)
        for popup in list(self._popups):
            popup.close()
        self._hide_stuck()
        self.pending_login = False
        self._tour_load = False
        self._landed = ""
        self._gone = self._gone_was = None
        if self.thread is None:
            # A fresh blank page, the old one and its renderer deleted now: a
            # news page left loaded behind a hidden window goes on running
            # its scripts.
            self._renew_page()
        self.address.clear()
        self.setWindowTitle("Browser inside the program")


def _ask(page, callback) -> None:
    """Ask a page to run "1" and call back - in whichever form this build of
    PySide takes the callback."""
    try:
        page.runJavaScript("1", 0, callback)
    except TypeError:
        page.runJavaScript("1", callback)
