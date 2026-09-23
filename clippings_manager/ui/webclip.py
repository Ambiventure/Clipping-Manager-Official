"""Clippings made from links: paste the message, get the cuttings.

The morning's coverage often arrives as one WhatsApp message with a numbered
list of stories in it. This is the window where that message is pasted: it
lists the links it found, in the order they were sent, and captures each one as
a clipping - the headline, the picture and the first inches of the story.

Two ways to capture, chosen on the window and remembered (2.0.32):

*   **Browser inside the app** - the program's own browser, in the background,
    signed in as the person is there. Without that browser (a build without
    it, or the offscreen suites) the same button uses the hidden Chrome on
    the program's own folder, as before.
*   **My Chrome** - the person's own Chrome, signed in as they already are,
    pictured from the screen when they say (ui/fromchrome.py).

Each link keeps what has happened to it by its address - waiting, captured
(and how, and as which number), failed and why, needs a sign-in - so pasting
more, or editing the box, never wipes a tick; and a captured clipping that is
undone makes its link available again.

The capturing happens on a thread of its own, because a page takes a few
seconds and the window has to stay usable. The browser is started once for the
whole list and closed at the end, so twelve links cost one startup, not twelve.
"""

from __future__ import annotations

import html
import re
import sys
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QTextCursor
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QDialog, QFrame,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QToolButton, QVBoxLayout)

from ..core import links, sitedata, webshot
from . import embedded, fromchrome, theme

PASTE_HINT = ("Paste a link, or the whole WhatsApp message with the morning's "
              "list in it. Every link in it is found, in the order it was sent, "
              "and each link goes on its own line however it arrives - pasted "
              "or dragged.")
NOTHING_YET = "No links yet — paste a message above."
INSIDE_NAME = "Browser inside the app"
CHROME_NAME = "My Chrome"
#: Kept under its old name for anything that still asks for it.
INSIDE = INSIDE_NAME
SIGN_IN_TIP = ("A post on X, Facebook, Instagram, Threads or LinkedIn is "
               "captured with nobody signed in to anything: the program asks "
               "the site for the post's own public card - the one a newspaper "
               "quoting it would put in its page - so there is no wall and no "
               "feed round it. Signing in is only for a post that is not "
               "public at all, and for a paper that wants an account before it "
               "shows a story. Your everyday Chrome is not touched, and the "
               "program never sees your password.")
INSIDE_TIP = ("The browser inside the program. Posts are captured without "
              "signing in to anything - the program asks each site for the "
              "post's own public card - with nothing on the screen while twelve "
              "links are captured. It has no ad-blocker, and it clears "
              "\"Ad-Blocker Detected\" boxes and cookie notices itself. Your "
              "everyday Chrome is not touched. Double-click a link to look at it "
              "there and capture it as you see it; right-click Browser inside the "
              "app for sign-ins and what the sites have saved.")
CHROME_TIP = fromchrome.TAKE_TIP
NEEDS_SIGN_IN = "{count} {needs} a sign-in: {choices}."
#: A post the site will not show anybody: taken down, or never public. No
#: sign-in of the program's own reaches it, so the only thing worth offering
#: is the Chrome they are already signed in to.
NOT_PUBLIC = "{count} {is_} not public: {choices}."
WALLED_WHY = "needs a sign-in"
NOT_PUBLIC_WHY = "not public"
AD_BLOCK_ROW = "   · your Chrome may show an Ad-Blocker Detected box"

#: Remembered in the export settings file, like the phone-bar tidy switch.
METHOD_KEY = "links_capture_with"
TRIM_KEY = "chrome_trim_after"

#: A why that talks about a sign-in, for a failure that came without a kind.
_SIGN_WORDS = re.compile(r"(?i)\bsign(?:ed)?[- ]?in\b")

_HOW = {"background": "captured in the background",
        "browser": "from the browser window",
        "chrome": "from your Chrome",
        "chrome-retry": "taken with Chrome"}


def _setting(key: str, default):
    from .export_dialog import load_settings

    try:
        return load_settings().get(key, default)
    except Exception:  # noqa: BLE001 - no settings yet
        return default


def _remember(key: str, value) -> None:
    from .export_dialog import load_settings, save_settings

    try:
        save_settings({**load_settings(), key: value})
    except Exception:  # noqa: BLE001 - a preference, never a crash
        pass


def capture_with() -> str:
    """Which way the links window captures: "inside" or "chrome". My Chrome
    is a Windows way only."""
    way = _setting(METHOD_KEY, "inside")
    return "chrome" if way == "chrome" and sys.platform == "win32" else "inside"


def set_capture_with(way: str) -> None:
    _remember(METHOD_KEY, "chrome" if way == "chrome" else "inside")


def trim_after() -> bool:
    """Whether My Chrome opens the trim after each picture. On unless
    switched off: the picture is the whole Chrome window."""
    return bool(_setting(TRIM_KEY, True))


def set_trim_after(on: bool) -> None:
    _remember(TRIM_KEY, bool(on))


def _chrome_open() -> bool:
    try:
        return webshot.chrome_running()
    except Exception:  # noqa: BLE001 - only the words of a note
        return False


@dataclass
class Caught:
    """One finished link: the picture, or why there is none."""

    found: links.Found
    shot: object = None
    why: str = ""
    kind: str = ""


@dataclass
class LinkState:
    """What has happened to one link, kept by its address so that editing
    the box never loses it. status: new, queued, capturing, retrying, done,
    failed, walled or skipped."""

    status: str = "new"
    why: str = ""
    clip_id: object = None
    how: str = ""
    #: Why it failed, in one word, as core/webshot named it - so the count
    #: line can tell a post with no public card from a page that would not
    #: open at all.
    kind: str = ""


class Catcher(QObject):
    """Captures a list of links, one after another, off the window's thread."""

    caught = Signal(object)          # a Caught, as each one finishes
    progress = Signal(int, int, str)  # done, total, what it is on now
    finished = Signal()

    def __init__(self, wanted: list):
        super().__init__()
        self.wanted = list(wanted)
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    @Slot()
    def run(self) -> None:
        browser = webshot.Browser()
        total = len(self.wanted)
        try:
            try:
                browser.start()
            except webshot.ShotError as bad:
                for row in self.wanted:
                    self.caught.emit(Caught(found=row, why=str(bad), kind=bad.kind))
                return
            for done, row in enumerate(self.wanted):
                if self._stop:
                    break
                self.progress.emit(done, total, row.site)
                try:
                    shot = browser.capture(row.url)
                    self.caught.emit(Caught(found=row, shot=shot))
                except webshot.ShotError as bad:
                    self.caught.emit(Caught(found=row, why=str(bad),
                                            kind=getattr(bad, "kind", "")))
                except Exception as bad:  # noqa: BLE001 - one link, never the lot
                    self.caught.emit(Caught(found=row, why=f"it could not be read ({bad})"))
                self.progress.emit(done + 1, total, row.site)
        finally:
            browser.stop()
            self.finished.emit()
            # The thread ends itself, from inside, needing nothing from the
            # window - see ui/reader.py for what happens when it does not.
            here = QThread.currentThread()
            if here is not None:
                here.quit()


class LinkBox(QPlainTextEdit):
    """The paste box, where every link lands on a line of its own.

    Pasted links used to run together - "https://a…https://b…" - when the
    next paste came straight after the last, because nothing put a line
    between them. One override catches every way text arrives: Ctrl+V, the
    right-click Paste, and a drag from Chrome's address bar or a page
    (measured: a drop carrying only addresses, with no text, comes here too).
    Words with no link in them, and a drag that starts inside the box, are
    left to the box's ordinary behaviour.
    """

    #: The whole text was replaced from outside - a fresh list.
    replaced = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._inner_drop = False

    def setPlainText(self, text: str) -> None:  # noqa: N802 - Qt's name
        self.replaced.emit()
        super().setPlainText(text)

    @staticmethod
    def words_of(source) -> str:
        """The words a paste or drop carries: its text, or when it has none,
        the web addresses in it one to a line."""
        text = source.text() if source.hasText() else ""
        if not text.strip():
            text = "\n".join(u.toString() for u in source.urls() if not u.isLocalFile())
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def canInsertFromMimeData(self, source) -> bool:  # noqa: N802 - Qt's name
        if source is None:
            return False
        return (source.hasText() or any(not u.isLocalFile() for u in source.urls())
                or super().canInsertFromMimeData(source))

    def dropEvent(self, event):  # noqa: N802 - Qt's name
        # Words dragged about inside the box are the box's own business.
        self._inner_drop = event.source() in (self, self.viewport())
        try:
            super().dropEvent(event)
        finally:
            self._inner_drop = False

    def insertFromMimeData(self, source) -> None:  # noqa: N802 - Qt's name
        words = self.words_of(source) if source is not None else ""
        if self._inner_drop or not words.strip() or not links.find(words):
            super().insertFromMimeData(source)
            return
        self.put_links(words)

    def put_links(self, text: str, at_end: bool = False) -> None:
        """Put words holding links in on lines of their own, as one undo step.

        In the middle of a line the words go after it - put at the cursor they
        cut an address in two ("https" / "://a…", in the probe). A line break
        goes before them when the line already has words on it, and after them
        when the box ends there or words follow; otherwise the cursor steps to
        the next line. So there is never a blank line, and the next paste
        always starts a line of its own. Words that name a link stay with it:
        a paste on those words, or between them and their link, never goes in
        between.
        """
        lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            return
        body = "\n".join(lines)
        cursor = self.textCursor()
        if at_end:
            cursor.movePosition(QTextCursor.End)
        cursor.beginEditBlock()
        try:
            if cursor.hasSelection():
                cursor.removeSelectedText()
            below = None if at_end else self._link_line_below(cursor)
            named = None if at_end or below is not None else self._label_line_above(cursor)
            if below is not None:
                # On the words that name a link further down: after that
                # link. Put straight after the words, the new link took them
                # as its own label - the sender's words on the wrong story,
                # and none on theirs (review of step B).
                cursor.setPosition(below.position())
                cursor.movePosition(QTextCursor.EndOfBlock)
            elif named is not None:
                # Just before a link whose words are on a line above - at the
                # start of the link's line, or on a blank line between: before
                # those words, which stay with their link. Put in between, the
                # new link took them, as above (review of step B, round 3).
                cursor.setPosition(named.position())
            elif not cursor.atBlockStart() and not cursor.atBlockEnd():
                cursor.movePosition(QTextCursor.EndOfBlock)
            if cursor.block().text()[:cursor.positionInBlock()].strip():
                cursor.insertText("\n")
            cursor.insertText(body)
            if cursor.block().text()[cursor.positionInBlock():].strip():
                cursor.insertText("\n")
            elif cursor.atEnd():
                cursor.insertText("\n")
            else:
                cursor.movePosition(QTextCursor.NextBlock)
        finally:
            cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    @staticmethod
    def _link_line_below(cursor):
        """The line whose link the words at the cursor are the label of, or
        None. Only for a line of words with no link, with the cursor past its
        start, when a link comes below before any other words would take the
        label (core/links.find gives a label to the first link after it, over
        blank lines). A label typed at the end of the box, waiting for the
        next link, has none."""
        block = cursor.block()
        words = block.text()
        if cursor.atBlockStart() or not words.strip() or links.find(words):
            return None
        below = block.next()
        while below.isValid():
            if below.text().strip():
                return below if links.find(below.text()) else None
            below = below.next()
        return None

    @staticmethod
    def _label_line_above(cursor):
        """The line of words naming the link the cursor is just before, or
        None: for a cursor at the start of that link's line, or anywhere on a
        blank line between the two. The words name it when they are the
        nearest line above with anything on it and the link has no words of
        its own - asked of core/links.find itself, so the rule is never
        written twice."""
        block = cursor.block()
        if block.text().strip():
            if not cursor.atBlockStart():
                return None
            link = block
        else:
            link = block.next()
            while link.isValid() and not link.text().strip():
                link = link.next()
            if not link.isValid():
                return None
        own = links.find(link.text())
        if not own or own[0].label:
            return None
        above = block.previous()
        while above.isValid() and not above.text().strip():
            above = above.previous()
        if not above.isValid() or links.find(above.text()):
            return None
        named = links.find(above.text() + "\n" + link.text())
        return above if named and named[0].label else None


class LinksDialog(QDialog):
    """Paste a message, choose the links and the way, capture them."""

    methodChanged = Signal(str)

    def __init__(self, window, parent=None):
        super().__init__(parent or window)
        self.window = window
        self.found: list = []
        self.thread = None
        self.catcher = None
        self.taker = None
        self.browser = None
        self.made = 0
        self.states: dict = {}           # url.lower() -> LinkState
        self.ticks: dict = {}            # url.lower() -> the person's own tick
        self._painting = False
        self._reread_later = False
        self._engine = ""                # what is running: inside, headless, retry
        self._wanted: list = []
        self._retry: list = []
        self._kinds: dict = {}
        self._at_url = ""
        self._menu = None
        self.setWindowTitle("Add clippings from links")
        self.setModal(False)
        self.resize(780, 660)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)

        hint = QLabel(PASTE_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.MUTED};")
        outer.addWidget(hint)

        self.box = LinkBox()
        self.box.setPlaceholderText(
            "https://indianexpress.com/article/…\n\n"
            "…or the whole message:\n"
            "1. Rajdhani, Vande Bharat among 120 trains affected\n"
            "https://indianexpress.com/article/…")
        self.box.setMinimumHeight(130)
        self.box.textChanged.connect(self._reread)
        self.box.replaced.connect(self.ticks.clear)
        outer.addWidget(self.box)

        self.count = QLabel(NOTHING_YET)
        self.count.setStyleSheet("font-weight: 700;")
        self.count.setWordWrap(True)
        self.count.setTextFormat(Qt.PlainText)
        self.count.linkActivated.connect(self._count_link)
        outer.addWidget(self.count)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.list.setAlternatingRowColors(True)
        self.list.itemChanged.connect(self._item_changed)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._row_menu)
        self.list.itemDoubleClicked.connect(self._row_double_clicked)
        outer.addWidget(self.list, 1)

        self.bar = QProgressBar()
        self.bar.hide()
        outer.addWidget(self.bar)

        # Capture with: [Browser inside the app] [My Chrome] ⋯ - then the
        # one Capture button, which uses whichever way is chosen.
        row = QHBoxLayout()
        row.setSpacing(8)
        switch = QFrame()
        switch.setObjectName("MethodSwitch")
        inside = QHBoxLayout(switch)
        inside.setContentsMargins(10, 4, 4, 4)
        inside.setSpacing(4)
        label = QLabel("Capture with:")
        label.setStyleSheet(f"color: {theme.SLATE_TEXT_LIGHT};")
        inside.addWidget(label)
        self.method_inside = QPushButton(INSIDE_NAME)
        self.method_chrome = QPushButton(CHROME_NAME)
        self.method_group = QButtonGroup(self)
        self.method_group.setExclusive(True)
        for name, button, tip in (("inside", self.method_inside, INSIDE_TIP),
                                  ("chrome", self.method_chrome, CHROME_TIP)):
            button.setObjectName("MethodChoice")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(tip + "\n\nRight-click for more.")
            button.setContextMenuPolicy(Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, n=name, b=button: self._show_menu(n, b, pos))
            self.method_group.addButton(button)
            inside.addWidget(button)
        self.method_chrome.setVisible(sys.platform == "win32")
        self.method_group.buttonClicked.connect(
            lambda b: self.set_method("chrome" if b is self.method_chrome else "inside"))
        row.addWidget(switch)
        self.method_more = QToolButton()
        self.method_more.setObjectName("MethodMore")
        self.method_more.setText("⋯")
        self.method_more.setToolTip("More for the chosen way: sign-ins, what the "
                                    "sites keep, how it works")
        self.method_more.setCursor(Qt.PointingHandCursor)
        self.method_more.clicked.connect(
            lambda: self._show_menu(self.method, self.method_more))
        row.addWidget(self.method_more)
        row.addStretch(1)
        self.capture = QPushButton("Capture")
        self.capture.setObjectName("NavyFilled")
        self.capture.setCursor(Qt.PointingHandCursor)
        self.capture.setEnabled(False)
        self.capture.clicked.connect(self._capture)
        row.addWidget(self.capture)
        self.close_btn = QPushButton("Close")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.clicked.connect(self.close)
        row.addWidget(self.close_btn)
        outer.addLayout(row)

        self.method_note = QLabel()
        self.method_note.setWordWrap(True)
        self.method_note.setStyleSheet(f"color: {theme.MUTED};")
        outer.addWidget(self.method_note)

        # A captured clipping that is undone gives its link back - noticed a
        # moment after the undo, never on every step of a burst of them.
        self._states_timer = QTimer(self)
        self._states_timer.setSingleShot(True)
        self._states_timer.setInterval(150)
        self._states_timer.timeout.connect(self._refresh_states)
        for stack in (getattr(window, "undo_stack", None), getattr(window, "board_undo", None)):
            if stack is not None:
                stack.indexChanged.connect(self._states_timer.start)

        (self.method_chrome if capture_with() == "chrome" else self.method_inside).setChecked(True)
        self._refresh_method_note()
        self._reread()

    # ------------------------------------------------------------- the way
    @property
    def method(self) -> str:
        return ("chrome" if self.method_chrome.isChecked() and sys.platform == "win32"
                else "inside")

    def set_method(self, name: str, remember: bool = True) -> None:
        name = "chrome" if name == "chrome" and sys.platform == "win32" else "inside"
        (self.method_chrome if name == "chrome" else self.method_inside).setChecked(True)
        if remember:
            set_capture_with(name)
        self._repaint_rows()
        self._sync_capture_button()
        self._refresh_method_note()
        self.methodChanged.emit(name)

    def _busy(self) -> bool:
        return self.thread is not None or self.taker is not None

    def _sync_capture_button(self) -> None:
        many = len(self._ticked())
        if self.method == "chrome":
            text = f"Take {many} from Chrome" if many else "Take from Chrome"
        else:
            text = f"Capture {many}" if many else "Capture"
        self.capture.setText(text)
        busy = self._busy()
        self.capture.setEnabled(bool(many) and not busy)
        self.method_inside.setEnabled(not busy)
        self.method_chrome.setEnabled(not busy)

    def _refresh_method_note(self) -> None:
        """One line under the choice: what the chosen way does, and which
        sites the program's browser is signed in to - from the names in its
        cookie file, never the values."""
        if self.method == "chrome":
            text = ("Opens each ticked link in your own Chrome, signed in as you are, "
                    "and takes the picture when you say. Close any Ad-Blocker Detected "
                    "box first.")
        else:
            inside = embedded.usable()
            try:
                known = embedded.known_sign_ins() if inside else webshot.signed_in_sites()
            except Exception:  # noqa: BLE001 - only the words of a note
                known = []
            names = ", ".join(sitedata.name_of(site) for site in known)
            text = ("Captures in the background in the browser inside the app"
                    if inside else "Captures in the background with the program's own Chrome")
            if known:
                text += f" — signed in to {names}."
            elif not inside and _chrome_open():
                text += " — its sign-ins show once the program's Chrome is closed."
            else:
                text += " — not signed in anywhere yet; right-click it to sign in."
        self.method_note.setText(text)

    # --------------------------------------------------------------- menus
    def _show_menu(self, name: str, anchor, pos=None) -> None:
        """A way's menu, from a right-click or the ⋯ button. Shown with
        popup(), never exec(): nothing waits on it."""
        menu = self.menu_for(name)
        # Deleted when it closes. Built fresh for every right-click as a child
        # of this window, each one was left behind - a hundred after 25
        # rounds, for as long as the program ran (review of step B, round 3).
        menu.setAttribute(Qt.WA_DeleteOnClose, True)
        self._menu = menu                   # the one on the screen
        at = pos if pos is not None else QPoint(0, anchor.height())
        menu.popup(anchor.mapToGlobal(at))

    def _act(self, menu: QMenu, text: str, key: str, enabled: bool = True,
             checkable: bool = False, checked: bool = False, tip: str = ""):
        action = menu.addAction(text)
        action.setData(key)
        action.setEnabled(enabled)
        if tip:
            action.setToolTip(tip)
        if checkable:
            action.setCheckable(True)
            action.setChecked(checked)
        action.triggered.connect(lambda _on=False, k=key, a=action: self.choose(k, a))
        return action

    def menu_for(self, name: str) -> QMenu:
        """The menu of one way, built fresh each time. Every action carries
        its key as its data, so what it does can be asked for by name."""
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        if name == "chrome":
            ticked = len(self._ticked())
            self._act(menu, f"Take the ticked links now ({ticked})" if ticked
                      else "Take the ticked links now", "take", enabled=bool(ticked) and not self._busy())
            walled = self._walled()
            self._act(menu, f"Take only the ones that need a sign-in ({len(walled)})" if walled
                      else "Take only the ones that need a sign-in", "take-walled",
                      enabled=bool(walled) and not self._busy())
            menu.addSeparator()
            self._act(menu, "Open the trim after each picture", "trim-after",
                      checkable=True, checked=trim_after())
            menu.addSeparator()
            self._act(menu, "How this way works", "how-chrome")
            return menu
        if embedded.usable():
            known = self._known_inside()
            self._act(menu, "Open the browser at these links" if self.found else "Open the browser",
                      "open")
            menu.addSeparator()
            for site in sitedata.LOGIN_PAGES:
                title = sitedata.name_of(site)
                self._act(menu, f"Signed in to {title} ✓" if site in known else f"Sign in to {title}",
                          f"sign-in:{site}")
            self._act(menu, "Saved sign-ins and site data…", "saved")
            out = menu.addMenu("Sign out of")
            out.setEnabled(bool(known))
            for site in known:
                self._act(out, sitedata.name_of(site), f"sign-out:{site}")
            self._act(menu, "Sign out of everything…", "sign-out-all", enabled=bool(known))
        else:
            try:
                known = webshot.signed_in_sites()
            except Exception:  # noqa: BLE001
                known = []
            for site in sitedata.LOGIN_PAGES:
                title = sitedata.name_of(site)
                self._act(menu, f"Signed in to {title} ✓" if site in known else f"Sign in to {title}",
                          f"sign-in:{site}")
            menu.addSeparator()
            if known:
                where = ", ".join(sitedata.name_of(s) for s in known)
            elif _chrome_open():
                # Its cookie file is locked while it is open: not "nowhere".
                where = "not known while the program's Chrome is open"
            else:
                where = "nowhere yet"
            said = menu.addAction("Signed in: " + where)
            said.setEnabled(False)
            out = menu.addMenu("Sign the program's Chrome out of")
            out.setEnabled(bool(known))
            for site in known:
                self._act(out, sitedata.name_of(site), f"chrome-sign-out:{site}")
        menu.addSeparator()
        self._act(menu, "How this way works", "how-inside")
        return menu

    def choose(self, key: str, action=None) -> None:
        """What a menu item does, by its key."""
        if key == "open":
            self.open_browser()
        elif key.startswith("sign-in:"):
            site = key.split(":", 1)[1]
            self._sign_in(site)
        elif key == "saved":
            self.open_browser(panel=True)
        elif key.startswith("sign-out:"):
            site = key.split(":", 1)[1]
            try:
                embedded.Host.get().sign_out(site)
                self.method_note.setText(f"Signed out of {sitedata.name_of(site)} in the browser "
                                         "inside the app.")
            except Exception as bad:  # noqa: BLE001
                self.method_note.setText(f"Could not sign out ({bad}).")
            QTimer.singleShot(1500, self._refresh_method_note)
        elif key == "sign-out-all":
            answer = QMessageBox.question(
                self, "Sign out of everything",
                "Sign the browser inside the app out of every site? Posts that need "
                "a sign-in will not capture until you sign in again.")
            if answer == QMessageBox.Yes:
                embedded.Host.get().forget_sign_ins()
                self.method_note.setText("Signed out of everything in the browser inside the app.")
        elif key.startswith("chrome-sign-out:"):
            site = key.split(":", 1)[1]
            done = webshot.sign_out_of_chrome(site)
            self.method_note.setText(
                f"The program's Chrome is signed out of {sitedata.name_of(site)}." if done == "done"
                else f"The program's Chrome is open: it is signed out of "
                     f"{sitedata.name_of(site)} before it next starts.")
        elif key == "take":
            self._take_from_chrome(self._ticked())
        elif key == "take-walled":
            self._take_from_chrome(self._walled())
        elif key == "trim-after":
            on = action.isChecked() if action is not None else not trim_after()
            set_trim_after(on)
            self.method_note.setText("My Chrome opens the trim after each picture."
                                     if on else "My Chrome adds each picture without opening the trim.")
        elif key == "how-chrome":
            self.method_note.setText(CHROME_TIP)
        elif key == "how-inside":
            self.method_note.setText(INSIDE_TIP if embedded.usable() else SIGN_IN_TIP)
        elif key == "row-capture" and action is not None:
            found = self._found_by_url(action.property("url"))
            if found is not None:
                self._capture_background([found])
        elif key == "row-chrome" and action is not None:
            found = self._found_by_url(action.property("url"))
            if found is not None:
                self._take_from_chrome([found])
        elif key == "row-browser" and action is not None:
            self.open_browser(at_url=action.property("url"))
        elif key == "row-open-chrome" and action is not None:
            fromchrome.open_link(action.property("url"))
        elif key == "row-show" and action is not None:
            state = self.states.get(str(action.property("url")).lower())
            if state is not None and state.clip_id is not None:
                self.window.open_preview(state.clip_id)

    def _sign_in(self, site: str) -> None:
        login = sitedata.LOGIN_PAGES.get(site, f"https://{site}/")
        if embedded.usable():
            self.open_browser(login=login)
            return
        try:
            webshot.sign_in(login)
        except webshot.ShotError as bad:
            self.method_note.setText(str(bad))
            return
        self.method_note.setText("A browser window is open: sign in there, close it, "
                                 "and capture again.")
        QTimer.singleShot(30000, self._refresh_method_note)

    def _known_inside(self) -> list:
        try:
            return embedded.known_sign_ins()
        except Exception:  # noqa: BLE001
            return []

    # ------------------------------------------------------------- the list
    def start_over(self, words: str) -> None:
        """A fresh list: what was captured before is forgotten."""
        self.states.clear()
        self.ticks.clear()
        self.box.setPlainText(words)

    def add_words(self, words: str) -> None:
        """More links, after the ones already listed, on lines of their own."""
        self.box.put_links(words, at_end=True)

    def take_out(self, url: str) -> bool:
        """Take a link back out of the list, as one undo step in the box.
        Returns whether it went.

        For Collect from WhatsApp: it listed the link, then the person put it
        on a photo with Collect's button, and left in the list Capture would
        make a second clipping of that story. Only a line holding that link
        and nothing else, with no words of the sender's above naming it, and
        only while nothing is capturing and the link has not been captured:
        a clipping already made from it is left to show for itself.
        """
        key = (url or "").strip().lower()
        if not key or self.thread is not None:
            return False
        state = self.states.get(key)
        if state is not None and state.status != "new":
            return False
        text = self.box.toPlainText()
        if any(found.url.lower() == key and found.label for found in links.find(text)):
            return False
        document = self.box.document()
        lines = []
        block = document.firstBlock()
        while block.isValid():
            if block.text().strip().lower() == key:
                lines.append(block)
            block = block.next()
        if not lines:
            return False
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        try:
            # From the bottom up, so the lines above keep their positions.
            for block in reversed(lines):
                start, end = block.position(), block.position() + block.length() - 1
                if block.next().isValid():
                    end += 1                      # its own line break
                elif block.previous().isValid():
                    start -= 1                    # the last line: the break before it
                cursor.setPosition(start)
                cursor.setPosition(end, QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
        finally:
            cursor.endEditBlock()
        self.states.pop(key, None)
        self.ticks.pop(key, None)
        return True

    def _reread(self) -> None:
        """What links the pasted words hold, as they are typed or pasted."""
        if self.thread is not None:
            self._reread_later = True      # after the capture that is running
            return
        self.found = links.find(self.box.toPlainText())
        self._refresh_states(repaint=False)
        self._painting = True
        try:
            self.list.clear()
            for row in self.found:
                item = QListWidgetItem()
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setData(Qt.UserRole, row.url)
                self.list.addItem(item)
                self._paint_row(item, row)
        finally:
            self._painting = False
        many = len(self.found)
        done = sum(1 for row in self.found if self._state(row).status == "done")
        self._plain_count(
            NOTHING_YET if not many else
            f"{many} link{'s' if many != 1 else ''} found"
            + (" — numbered as they were sent" if links.numbered(self.found) else "")
            + (f" — {done} already captured" if done else ""))
        self._sync_capture_button()
        if self.browser is not None:
            try:
                self.browser.update_tour(self.found)
                for row in self.found:
                    self.browser.mark(row.url, self._state(row).status == "done")
            except Exception:  # noqa: BLE001 - the browser window went away
                pass

    @staticmethod
    def _words(row: links.Found) -> str:
        number = f"{row.number}. " if row.number else ""
        label = row.label or row.url
        return f"{number}{label}   —   {row.site}"

    def _state(self, found) -> LinkState:
        key = found.url.lower()
        state = self.states.get(key)
        if state is None:
            state = self.states[key] = LinkState()
        return state

    def _found_by_url(self, url) -> "links.Found | None":
        url = str(url or "").lower()
        return next((row for row in self.found if row.url.lower() == url), None)

    def _done_words(self, state: LinkState) -> str:
        how = _HOW.get(state.how, "captured")
        pool = self.window.pool_for(state.clip_id) if state.clip_id is not None else None
        if pool is None:
            return how
        try:
            # The number the list shows it by; in a category of the board
            # opened out, a clipping filed in another category has none in
            # view and is named by its column.
            number = pool.number_of(state.clip_id)
            if number:
                return f"No. {number} — {how}"
            from ..core import sentiment

            row = pool.row_for(state.clip_id)
            return (f"{sentiment.column_for(row.clip.section).value} — {how}"
                    if row is not None else how)
        except Exception:  # noqa: BLE001
            return how

    def _paint_row(self, item, found) -> None:
        key = found.url.lower()
        state = self.states.get(key) or LinkState()
        words = self._words(found)
        status = state.status
        if status == "done":
            text = f"✓  {words}   ({self._done_words(state)})"
        elif status == "failed":
            text = f"✕  {words}   ({state.why})"
        elif status == "walled":
            text = f"✕  {words}   ({WALLED_WHY})"
        elif status == "capturing":
            text = f"…  {words}"
        elif status == "retrying":
            text = f"…  {words}   (trying again in Chrome)"
        elif status == "queued":
            text = f"{words}   (waiting)"
        elif status == "skipped":
            text = f"–  {words}   (skipped)"
        else:
            text = words
        walls = fromchrome.walls_ad_blockers(found.site)
        if walls and self.method == "chrome" and status != "done":
            text += AD_BLOCK_ROW
        was = self._painting
        self._painting = True
        try:
            item.setText(text)
            item.setForeground(theme.QDANGER if status in ("failed", "walled") else theme.QINK)
            tip = found.url + (f"\n{state.why}" if state.why and status != "done" else "")
            if walls:
                tip += "\n" + fromchrome.AD_BLOCKER_TIP
            item.setToolTip(tip)
            item.setCheckState(Qt.Checked if self.ticks.get(key, status != "done") else Qt.Unchecked)
            item.setBackground(QBrush(QColor(theme.NAVY_WASH)) if key == self._at_url else QBrush())
        finally:
            self._painting = was

    def _repaint_rows(self) -> None:
        for index in range(min(self.list.count(), len(self.found))):
            self._paint_row(self.list.item(index), self.found[index])

    def _repaint(self, url: str) -> None:
        key = url.lower()
        for index in range(min(self.list.count(), len(self.found))):
            if self.found[index].url.lower() == key:
                self._paint_row(self.list.item(index), self.found[index])
        if self.browser is not None:
            state = self.states.get(key)
            try:
                self.browser.mark(url, state is not None and state.status == "done")
            except Exception:  # noqa: BLE001
                pass

    def _item_changed(self, item) -> None:
        if self._painting:
            return
        url = item.data(Qt.UserRole)
        if url:
            self.ticks[str(url).lower()] = item.checkState() == Qt.Checked
        self._sync_capture_button()

    def _ticked(self) -> list:
        out = []
        for index in range(min(self.list.count(), len(self.found))):
            if self.list.item(index).checkState() == Qt.Checked:
                out.append(self.found[index])
        return out

    def _walled(self) -> list:
        return [row for row in self.found if self._state(row).status == "walled"]

    def _not_public(self) -> list:
        """The posts whose card came back saying there is no public post - and
        whose own page, tried after it, said no more."""
        return [row for row in self.found
                if self._state(row).status == "failed"
                and (self._state(row).kind or "") == "card-gone"]

    def _refresh_states(self, repaint: bool = True) -> None:
        """A clipping made from a link that has since been undone or deleted
        gives the link back, ticked; one redone takes it again - in the
        browser window too."""
        changed = []
        pool_for = getattr(self.window, "pool_for", None)
        if pool_for is None:
            return
        for key, state in self.states.items():
            if state.clip_id is None:
                continue
            here = pool_for(state.clip_id) is not None
            if state.status == "done" and not here:
                state.status = "new"
                self.ticks.pop(key, None)
                changed.append(key)
            elif state.status == "new" and here:
                state.status = "done"
                self.ticks.pop(key, None)
                changed.append(key)
        if changed and self.browser is not None:
            # Its picker and chip as well, even while a list runs here: they
            # are cheap to mark, somebody touring is looking at them, and they
            # went on saying "Captured ✓" for a story that had been undone
            # (review of step B, round 3).
            for key in changed:
                try:
                    self.browser.mark(key, self.states[key].status == "done")
                except Exception:  # noqa: BLE001 - the browser window went away
                    pass
        if changed and repaint and self.thread is None:
            self._repaint_rows()
            self._sync_capture_button()

    def showEvent(self, event):  # noqa: N802 - Qt's name
        self._refresh_states()
        super().showEvent(event)

    def changeEvent(self, event):  # noqa: N802 - Qt's name
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self._refresh_states()
        super().changeEvent(event)

    def _row_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        menu = self.row_menu_for(item)
        menu.setAttribute(Qt.WA_DeleteOnClose, True)    # as a way's menu is
        self._menu = menu
        menu.popup(self.list.viewport().mapToGlobal(pos))

    def row_menu_for(self, item) -> QMenu:
        """What can be done with one link. Keys: row-capture, row-chrome,
        row-browser, row-open-chrome, row-show."""
        url = str(item.data(Qt.UserRole) or "")
        found = self._found_by_url(url)
        state = self._state(found) if found is not None else LinkState()
        menu = QMenu(self)
        busy = self._busy()
        for text, key, show, enabled in (
                ("Capture this one", "row-capture", True, not busy),
                ("Take this one from my Chrome", "row-chrome", sys.platform == "win32", not busy),
                ("Open it in the browser inside the app", "row-browser", embedded.usable(), True),
                ("Open it in my Chrome", "row-open-chrome", True, True),
                ("Show its clipping", "row-show", state.status == "done", True)):
            if show:
                action = self._act(menu, text, key, enabled=enabled)
                action.setProperty("url", url)
        return menu

    def _row_double_clicked(self, item) -> None:
        url = str(item.data(Qt.UserRole) or "")
        if not url:
            return
        if embedded.usable():
            self.open_browser(at_url=url)
        else:
            fromchrome.open_link(url)

    def _plain_count(self, text: str) -> None:
        self.count.setTextFormat(Qt.PlainText)
        self.count.setText(text)

    # ---------------------------------------------------------- the capture
    def _capture(self) -> None:
        """Capture, the chosen way."""
        wanted = self._ticked()
        if not wanted or self._busy():
            return
        if self.method == "chrome":
            self._take_from_chrome(wanted)
        else:
            self._capture_background(wanted)

    def _capture_background(self, wanted: list) -> None:
        if not wanted or self._busy():
            return
        self.made = 0
        self._retry = []
        engine = "headless"
        if embedded.usable():
            try:
                embedded.Host.get()
                engine = "inside"
            except Exception:  # noqa: BLE001 - the browser inside did not start
                engine = "headless"
        self._start_run(wanted, engine)

    def _start_run(self, wanted: list, engine: str) -> None:
        self._wanted = list(wanted)
        self._engine = engine
        self._kinds = {}
        for row in wanted:
            state = self._state(row)
            state.status, state.why = ("retrying" if engine == "retry" else "queued"), state.why
        self.bar.setRange(0, len(wanted))
        self.bar.setValue(0)
        self.bar.show()
        self.box.setReadOnly(True)
        self._plain_count(f"Capturing {len(wanted)}… the window stays usable." if engine != "retry"
                          else f"Trying {len(wanted)} again with Chrome…")
        self.thread = QThread(self)
        if engine == "inside":
            # The browser inside the program: the same capture, signed in
            # as the person is there, with nothing on the screen.
            host = embedded.Host.get()
            self.catcher = embedded.Catcher(wanted, embedded.PORT, host.target_id)
            self.catcher.caught.connect(self._one_caught)
            self.catcher.troubled.connect(self._troubled)
        else:
            self.catcher = Catcher(wanted)
            self.catcher.caught.connect(self._one_done)
        self.catcher.moveToThread(self.thread)
        self.thread.started.connect(self.catcher.run)
        self.catcher.progress.connect(self._progress)
        self.catcher.finished.connect(self._all_done)
        self._repaint_rows()
        self._sync_capture_button()
        self.thread.start()

    @Slot(int, int, str)
    def _progress(self, done: int, total: int, site: str) -> None:
        self.bar.setValue(done)
        self._plain_count(f"Capturing {done + 1 if done < total else total} of "
                          f"{total} — {site}")
        if done < len(self._wanted):
            row = self._wanted[done]
            state = self._state(row)
            if state.status in ("queued", "retrying", "new"):
                state.status = "capturing"
                self._repaint(row.url)

    @Slot(str, str)
    def _troubled(self, url: str, kind: str) -> None:
        self._kinds[url.lower()] = kind

    @Slot(object)
    def _one_done(self, caught: Caught) -> None:
        found = caught.found
        state = self._state(found)
        key = found.url.lower()
        if caught.shot is not None:
            clip_id = self.window.clip_from_link(caught.shot, found)
            if clip_id is not None:
                self.made += 1
                state.status, state.why, state.clip_id = "done", "", clip_id
                state.how = "chrome-retry" if self._engine == "retry" else "background"
                self.ticks.pop(key, None)
            else:
                state.status, state.why = "failed", "its picture could not be read"
        elif self._is_walled(caught):
            state.status, state.why, state.clip_id = "walled", caught.why, None
        elif (caught.kind == "stopped" and self._engine == "inside"
                and webshot.find_browser()):
            # The browser inside the app stopped on this page: tried once
            # more, quietly, in the program's own Chrome at the end.
            state.status, state.why = "retrying", caught.why
            self._retry.append(found)
        else:
            state.status, state.why, state.clip_id = "failed", caught.why, None
            state.kind = caught.kind or ""
        self._repaint(found.url)

    @staticmethod
    def _is_walled(caught: Caught) -> bool:
        if caught.kind:
            return caught.kind == "sign-in"
        return bool(_SIGN_WORDS.search(caught.why or ""))

    @Slot(object, object, str)
    def _one_caught(self, found, shot, why: str) -> None:
        kind = self._kinds.pop(found.url.lower(), "") if shot is None else ""
        self._one_done(Caught(found=found, shot=shot, why=why, kind=kind))

    def _row_of(self, url: str):
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.data(Qt.UserRole) == url:
                return item
        return None

    @Slot()
    def _all_done(self) -> None:
        thread, self.thread = self.thread, None
        self.catcher = None
        if thread is not None:
            thread.quit()
            thread.wait(4000)
            thread.deleteLater()
        if self._retry and thread is not None:
            retry, self._retry = self._retry, []
            self._start_run(retry, "retry")
            return
        for row in self._retry:
            state = self._state(row)
            state.status = "failed"
        self._retry = []
        for row in self._wanted:
            state = self._state(row)
            if state.status in ("queued", "capturing", "retrying"):
                state.status = "new"
        self._engine = ""
        self.bar.hide()
        self.box.setReadOnly(False)
        self._refresh_method_note()
        if self._reread_later:
            self._reread_later = False
            self._reread()
        else:
            self._repaint_rows()
        self._sync_capture_button()
        left = len(self._ticked())
        self._say_with_walls(
            f"{self.made} clipping{'s' if self.made != 1 else ''} added"
            + (f" — {left} still ticked" if left else "") + ".")

    def _say_with_walls(self, text: str) -> None:
        """The count line, and when posts hit a sign-in wall, the two ways past
        it as links that do it."""
        walled = self._walled()
        if not walled:
            gone = self._not_public()
            if gone and sys.platform == "win32":
                many = len(gone)
                self.count.setTextFormat(Qt.RichText)
                self.count.setText(html.escape(text) + "  " + NOT_PUBLIC.format(
                    count=many, is_="are" if many != 1 else "is",
                    choices=(f"<a href='chrome-gone'>take "
                             f"{'them' if many != 1 else 'it'} from my Chrome</a>")))
                return
            self._plain_count(text)
            return
        site = sitedata.site_of(walled[0].site)
        many = len(walled)
        where = " in the browser inside the app" if embedded.usable() else ""
        choices = f"<a href='sign-in'>sign in to {html.escape(site)}{where}</a>"
        if sys.platform == "win32":
            choices += (f" or <a href='chrome'>take {'them' if many != 1 else 'it'} "
                        "from my Chrome</a>")
        self.count.setTextFormat(Qt.RichText)
        self.count.setText(html.escape(text) + "  " + NEEDS_SIGN_IN.format(
            count=many, needs="need" if many != 1 else "needs", choices=choices))

    def _count_link(self, href: str) -> None:
        if href == "chrome-gone":
            gone = self._not_public()
            if gone:
                self._take_from_chrome(gone)
            return
        walled = self._walled()
        if not walled:
            return
        if href == "chrome":
            self._take_from_chrome(walled)
        elif href == "sign-in":
            site = sitedata.site_of(walled[0].site)
            login = sitedata.LOGIN_PAGES.get(site, f"https://{site}/")
            if embedded.usable():
                self.open_browser(at_url=walled[0].url, login=login)
            else:
                self._sign_in(site)

    # ------------------------------------------------------- the browser
    def _tour_index(self, at_url: str = "") -> int:
        if at_url:
            for index, row in enumerate(self.found):
                if row.url.lower() == str(at_url).lower():
                    return index
        ticked = {row.url.lower() for row in self._ticked()}
        for index, row in enumerate(self.found):
            if row.url.lower() in ticked and self._state(row).status != "done":
                return index
        for index, row in enumerate(self.found):
            if self._state(row).status != "done":
                return index
        return 0

    def open_browser(self, at_url: str = "", panel: bool = False, login: str = "") -> None:
        """The browser inside the program, touring the listed links from the
        first ticked one not yet captured (or at_url) - or at a sign-in page
        first, with the links waiting.

        One window for the links window. Closing it puts it away, and opening
        it again shows the same window, touring as a new one would: a new
        window each time left every old one alive, its page loaded and its
        panel still filled on every cookie (review of step B). Asked only for
        its panel ("Saved sign-ins and site data…") over a page somebody has
        open, it opens the panel and leaves the page where it is."""
        if not embedded.usable():
            if login:
                self._sign_in(sitedata.site_of(login.split("://", 1)[-1].split("/", 1)[0]))
            elif at_url:
                fromchrome.open_link(at_url)
            return
        index = self._tour_index(at_url)
        fresh = self.browser is None
        back = not fresh and not self.browser.isVisible()
        if fresh:
            try:
                self.browser = embedded.BrowserWindow(
                    self.window, parent=self, tour=self.found, at=index, panel=panel, login=login)
            except Exception as bad:  # noqa: BLE001 - the browser did not start
                self._plain_count(f"The browser inside the program could not open ({bad}).")
                return
            self.browser.finished.connect(self._inside_closed)
            self.browser.captured.connect(lambda _id: self._refresh_method_note())
            self.browser.linkCaptured.connect(self._browser_captured)
            self.browser.linkFailed.connect(self._browser_failed)
            self.browser.atLink.connect(self._browser_at)
        else:
            only_panel = panel and not (at_url or login) and not self.browser.is_blank()
            if self.found and not only_panel and (at_url or back or not login):
                self.browser.set_tour(self.found, index, open_now=not login)
            if login:
                self.browser.open_login(login)
            if panel:
                self.browser.show_panel(True, remember=False)
        if fresh or back:
            for row in self.found:
                self.browser.mark(row.url, self._state(row).status == "done")
            self._plain_count("Look at each link in the browser window and press Capture this "
                              "page - or sign in there if a post needs it.")
        self.browser.show()
        self.browser.raise_()
        self.browser.activateWindow()

    def _browser_captured(self, url: str, clip_id: int) -> None:
        found = self._found_by_url(url)
        if found is None:
            return
        state = self._state(found)
        state.status, state.why, state.clip_id, state.how = "done", "", clip_id, "browser"
        self.ticks.pop(found.url.lower(), None)
        self._repaint(found.url)
        self._sync_capture_button()

    def _browser_failed(self, url: str, why: str, kind: str) -> None:
        found = self._found_by_url(url)
        if found is None:
            return
        state = self._state(found)
        state.status = "walled" if kind == "sign-in" else "failed"
        state.why, state.clip_id = why, None
        self._repaint(found.url)

    def _browser_at(self, url: str) -> None:
        self._at_url = str(url or "").lower()
        self._repaint_rows()

    def _inside_closed(self, *_args) -> None:
        """The browser window was closed: put away, and kept for next time."""
        self._at_url = ""
        self._repaint_rows()
        self._refresh_method_note()

    # ---------------------------------------------------------- My Chrome
    def _take_from_chrome(self, wanted: list) -> None:
        """Links, one after another, from the person's own Chrome."""
        if not wanted or self._busy():
            return
        self.taker = fromchrome.TakeItDialog(self.window, wanted, parent=self,
                                             trim_after=trim_after())
        self.taker.taken.connect(self._taken)
        self.taker.skipped.connect(self._skipped)
        self.taker.showing.connect(self._taker_showing)
        self.taker.done.connect(self._taker_done)
        for row in wanted:
            self._state(row).status = "queued"
        self._repaint_rows()
        self._sync_capture_button()
        self._plain_count(f"Taking {len(wanted)} from your Chrome — the small panel says "
                          "what to do.")
        self.taker.start()

    def _taker_showing(self, url: str) -> None:
        found = self._found_by_url(url)
        if found is not None and self._state(found).status == "queued":
            self._state(found).status = "capturing"
            self._repaint(found.url)

    def _taken(self, url: str, clip_id: int) -> None:
        self.made += 1
        found = self._found_by_url(url)
        if found is None:
            return
        state = self._state(found)
        state.status, state.why, state.clip_id, state.how = "done", "", clip_id, "chrome"
        self.ticks.pop(found.url.lower(), None)
        self._repaint(found.url)

    def _skipped(self, url: str) -> None:
        found = self._found_by_url(url)
        if found is not None:
            self._state(found).status = "skipped"
            self._repaint(found.url)

    def _taker_done(self, count: int) -> None:
        taker, self.taker = self.taker, None
        if taker is not None:
            for row in taker.wanted:
                state = self._state(row)
                if state.status in ("queued", "capturing"):
                    state.status = "new"
            taker.deleteLater()
        self._repaint_rows()
        self._sync_capture_button()
        self._plain_count(f"{count} clipping{'s' if count != 1 else ''} taken "
                          "from your Chrome.")

    def closeEvent(self, event):  # noqa: N802 - Qt's name
        self._retry = []
        if self.browser is not None:
            self.browser.close()
        if self.taker is not None:
            self.taker.close()
        if self.catcher is not None:
            self.catcher.stop()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(6000)
            self.thread = None
        super().closeEvent(event)
