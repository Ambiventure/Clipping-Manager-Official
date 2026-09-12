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

The browser reaches out only when a capture or the sign-in window asks it
to, like the other two modules allowed to (NOTES: the offline rule).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, QUrl, Qt, Signal, Slot
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

try:  # a build without the browser keeps the headless path
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    AVAILABLE = True
except Exception:  # noqa: BLE001
    AVAILABLE = False

from ..core import webshot
from . import theme

PROFILE_NAME = "clippings"
#: Where the person's sign-ins live: beside the other settings, never in Chrome.
PROFILE_FOLDER = "webprofile"
SIGN_INS_FILE = "signed-in.json"
SOCIAL = ("x.com", "twitter.com", "facebook.com", "instagram.com", "threads.net")
#: The parked window: off every edge of any desktop, and it never takes focus.
PARK_AT = (-12000, -12000)

#: The port the browser will answer on, chosen once, before the application.
PORT = 0


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
        from PySide6.QtGui import QGuiApplication

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


def known_sign_ins() -> list:
    """Which of the social sites the program's browser has been signed in to
    - from the note the host keeps, so nothing has to open to answer."""
    try:
        data = json.loads((profile_home() / SIGN_INS_FILE).read_text(encoding="utf-8"))
        return sorted(str(h) for h in data.get("sites", []) if h in SOCIAL)
    except Exception:  # noqa: BLE001 - never signed in, or not ours
        return []


class Host(QObject):
    """The profile, the parked window and the page that captures - made once,
    on the main thread, the first time anything needs the browser."""

    _one: Optional["Host"] = None

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
        self.profile = QWebEngineProfile(PROFILE_NAME)
        self.profile.setPersistentStoragePath(str(home / "storage"))
        self.profile.setCachePath(str(home / "cache"))
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.setHttpUserAgent(plain_agent(self.profile.httpUserAgent()))
        self.sites: set = set(known_sign_ins())
        # Names of hosts only, as cookies arrive - never a value, which is the
        # key to the account. It is how the button can say "Signed in: x.com".
        self.profile.cookieStore().cookieAdded.connect(self._cookie_added)

        self.parking = QWidget()
        self.parking.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint
                                    | Qt.WindowDoesNotAcceptFocus)
        self.parking.setAttribute(Qt.WA_ShowWithoutActivating, True)
        box = QVBoxLayout(self.parking)
        box.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView()
        self.page = QWebEnginePage(self.profile, self.view)
        self.view.setPage(self.page)
        box.addWidget(self.view)
        self.parking.resize(webshot.PAGE_WIDE, 700)
        self.parking.move(*PARK_AT)
        self.parking.show()
        self.parking.move(*PARK_AT)
        self.target_id = self.page.devToolsId()

    # ------------------------------------------------------------ sign-ins
    def _cookie_added(self, cookie) -> None:
        host = cookie.domain().lstrip(".").lower()
        for known in SOCIAL:
            if host == known or host.endswith("." + known):
                if known not in self.sites:
                    self.sites.add(known)
                    self._write_sites()

    def _write_sites(self) -> None:
        try:
            (profile_home() / SIGN_INS_FILE).write_text(
                json.dumps({"sites": sorted(self.sites)}), encoding="utf-8")
        except OSError:
            pass

    def signed_in(self) -> list:
        return sorted(self.sites)

    def forget_sign_ins(self) -> None:
        """Every cookie gone, so the next capture is signed out."""
        self.profile.cookieStore().deleteAllCookies()
        self.sites.clear()
        self._write_sites()


class Catcher(QObject):
    """Captures a list of links over the parked page, off the main thread.

    The same shape as webclip.Catcher, so the links window drives either.
    """

    caught = Signal(object, object, str)      # found, shot or None, why
    progress = Signal(int, int, str)
    finished = Signal()

    def __init__(self, wanted: list, port: int, target_id: str):
        super().__init__()
        self.wanted = list(wanted)
        self.port = port
        self.target_id = target_id
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    @Slot()
    def run(self) -> None:
        wire = None
        total = len(self.wanted)
        try:
            try:
                wire = webshot.attach(self.port, self.target_id)
            except Exception as bad:  # noqa: BLE001 - the browser did not answer
                for row in self.wanted:
                    self.caught.emit(row, None, f"the browser inside the program did not answer ({bad})")
                return
            for done, row in enumerate(self.wanted):
                if self._stop:
                    break
                self.progress.emit(done, total, row.site)
                try:
                    self.caught.emit(row, webshot.capture_over(wire, row.url), "")
                except webshot.ShotError as bad:
                    self.caught.emit(row, None, str(bad))
                except Exception as bad:  # noqa: BLE001 - one link, never the lot
                    self.caught.emit(row, None, f"it could not be read ({bad})")
                self.progress.emit(done + 1, total, row.site)
        finally:
            if wire is not None:
                wire.close()
            self.finished.emit()
            here = QThread.currentThread()
            if here is not None:
                here.quit()


class BrowserWindow(QDialog):
    """A window of the program's own to sign in, look, and capture from.

    The page shown here and the parked page that captures share one profile,
    so a sign-in made here is the sign-in every capture has. "Capture this
    page" captures the address in the bar through the parked page - the same
    path as a pasted link - and adds the clipping to the list.
    """

    captured = Signal(object)          # the clipping id

    def __init__(self, window, url: str = "", parent=None):
        super().__init__(parent or window)
        self.window = window
        self.host = Host.get()
        self.thread = None
        self.catcher = None
        self.setWindowTitle("Browser inside the program")
        self.setModal(False)
        self.resize(1040, 780)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 8)
        outer.setSpacing(6)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.back = QPushButton("‹")
        self.back.setFixedWidth(34)
        self.reload = QPushButton("↻")
        self.reload.setFixedWidth(34)
        self.address = QLineEdit()
        self.address.setPlaceholderText("Type an address and press Enter")
        self.go = QPushButton("Go")
        self.capture = QPushButton("Capture this page")
        self.capture.setObjectName("NavyFilled")
        self.capture.setToolTip(
            "The story, or the post, cut out of this page the way a pasted "
            "link is - signed in as you are here.")
        for button in (self.back, self.reload, self.go, self.capture):
            button.setCursor(Qt.PointingHandCursor)
        bar.addWidget(self.back)
        bar.addWidget(self.reload)
        bar.addWidget(self.address, 1)
        bar.addWidget(self.go)
        bar.addWidget(self.capture)
        outer.addLayout(bar)

        self.view = QWebEngineView()
        self.page = QWebEnginePage(self.host.profile, self.view)
        self.view.setPage(self.page)
        outer.addWidget(self.view, 1)

        foot = QHBoxLayout()
        self.note = QLabel(
            "Sign in here once - X, Facebook - and every capture after that "
            "is signed in. Your everyday Chrome is not touched.")
        self.note.setWordWrap(True)
        self.note.setStyleSheet(f"color: {theme.MUTED};")
        foot.addWidget(self.note, 1)
        self.forget = QPushButton("Sign out of everything")
        self.forget.setCursor(Qt.PointingHandCursor)
        self.forget.clicked.connect(self._forget)
        foot.addWidget(self.forget)
        close = QPushButton("Close")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.close)
        foot.addWidget(close)
        outer.addLayout(foot)

        self.back.clicked.connect(self.view.back)
        self.reload.clicked.connect(self.view.reload)
        self.go.clicked.connect(self._go)
        self.address.returnPressed.connect(self._go)
        self.capture.clicked.connect(self._capture)
        self.view.urlChanged.connect(lambda where: self.address.setText(where.toString()))
        self.view.titleChanged.connect(self._retitle)
        if url:
            self.open(url)

    def open(self, url: str) -> None:
        if "://" not in url:
            url = "https://" + url
        self.address.setText(url)
        self.view.setUrl(QUrl(url))

    def _go(self) -> None:
        typed = self.address.text().strip()
        if typed:
            self.open(typed)

    def _retitle(self, title: str) -> None:
        self.setWindowTitle(f"{title} — browser inside the program" if title
                            else "Browser inside the program")

    def _forget(self) -> None:
        self.host.forget_sign_ins()
        self.note.setText("Signed out of everything. Sign in again here when a "
                          "post needs it.")

    # ------------------------------------------------------------ capture
    def _capture(self) -> None:
        if self.thread is not None:
            return
        url = self.view.url().toString() or self.address.text().strip()
        if not url or url == "about:blank":
            return
        from ..core import links

        found = links.Found(url=url, label=self.view.title() or "")
        self.capture.setEnabled(False)
        self.note.setText(f"Capturing {found.site}…")
        self.thread = QThread(self)
        self.catcher = Catcher([found], PORT, self.host.target_id)
        self.catcher.moveToThread(self.thread)
        self.thread.started.connect(self.catcher.run)
        self.catcher.caught.connect(self._caught)
        self.catcher.finished.connect(self._done)
        self.thread.start()

    @Slot(object, object, str)
    def _caught(self, found, shot, why: str) -> None:
        if shot is None:
            self.note.setText(f"Not captured: {why}")
            return
        clip_id = self.window.clip_from_link(shot, found)
        if clip_id is not None:
            self.captured.emit(clip_id)
            self.note.setText(f"Captured {shot.site} — it is in the list.")

    @Slot()
    def _done(self) -> None:
        thread, self.thread = self.thread, None
        self.catcher = None
        if thread is not None:
            thread.quit()
            thread.wait(4000)
            thread.deleteLater()
        self.capture.setEnabled(True)

    def closeEvent(self, event):  # noqa: N802 - Qt's name
        if self.catcher is not None:
            self.catcher.stop()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(6000)
            self.thread = None
        super().closeEvent(event)
