"""Clippings made from links: paste the message, get the cuttings.

The morning's coverage often arrives as one WhatsApp message with a numbered
list of stories in it. This is the window where that message is pasted: it
lists the links it found, in the order they were sent, and captures each one as
a clipping - the headline, the picture and the first inches of the story.

The capturing happens on a thread of its own, because a page takes a few
seconds and the window has to stay usable. The browser is started once for the
whole list and closed at the end, so twelve links cost one startup, not twelve.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QProgressBar, QPushButton,
                               QVBoxLayout)

from ..core import links, webshot
from . import embedded, fromchrome, theme

PASTE_HINT = ("Paste a link, or the whole WhatsApp message with the morning's "
              "list in it. Every link in it is found, in the order it was sent.")
NOTHING_YET = "No links yet — paste a message above."
SIGN_IN_TIP = ("X and Facebook only show a post to somebody signed in. This "
               "opens a browser window of the program's own, where you sign in "
               "once; after that those posts are captured in the background. "
               "Your everyday Chrome is not touched, and the program never "
               "sees your password. Chrome will not lend the program the "
               "sign-in you already have - for that, use Take from my Chrome.")
INSIDE_TIP = ("The browser inside the program. Sign in there once - X, "
              "Facebook - and every capture after that is signed in, with "
              "nothing on the screen while twelve links are captured. Your "
              "everyday Chrome is not touched. You can also look at a page "
              "there and capture it by hand.")
INSIDE = "Browser inside the app\u2026"
NEEDS_SIGN_IN = ("{count} could not be read without a sign-in: press Take from "
                 "my Chrome to take {them} from your own Chrome, or Sign in for "
                 "captures once.")


@dataclass
class Caught:
    """One finished link: the picture, or why there is none."""

    found: links.Found
    shot: object = None
    why: str = ""


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
                    self.caught.emit(Caught(found=row, why=str(bad)))
                return
            for done, row in enumerate(self.wanted):
                if self._stop:
                    break
                self.progress.emit(done, total, row.site)
                try:
                    shot = browser.capture(row.url)
                    self.caught.emit(Caught(found=row, shot=shot))
                except webshot.ShotError as bad:
                    self.caught.emit(Caught(found=row, why=str(bad)))
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


class LinksDialog(QDialog):
    """Paste a message, choose the links, capture them as clippings."""

    def __init__(self, window, parent=None):
        super().__init__(parent or window)
        self.window = window
        self.found: list = []
        self.thread = None
        self.catcher = None
        self.made = 0
        self.setWindowTitle("Add clippings from links")
        self.setModal(False)
        self.resize(760, 620)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(10)

        hint = QLabel(PASTE_HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.MUTED};")
        outer.addWidget(hint)

        self.box = QPlainTextEdit()
        self.box.setPlaceholderText(
            "https://indianexpress.com/article/…\n\n"
            "…or the whole message:\n"
            "1. Rajdhani, Vande Bharat among 120 trains affected\n"
            "https://indianexpress.com/article/…")
        self.box.setMinimumHeight(130)
        self.box.textChanged.connect(self._reread)
        outer.addWidget(self.box)

        self.count = QLabel(NOTHING_YET)
        self.count.setStyleSheet("font-weight: 700;")
        outer.addWidget(self.count)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.list.setAlternatingRowColors(True)
        outer.addWidget(self.list, 1)

        self.bar = QProgressBar()
        self.bar.hide()
        outer.addWidget(self.bar)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.sign_in = QPushButton("Sign in for captures…")
        self.sign_in.setToolTip(INSIDE_TIP if embedded.usable() else SIGN_IN_TIP)
        self.browser = None
        self._say_signed_in()
        self.sign_in.setCursor(Qt.PointingHandCursor)
        self.sign_in.clicked.connect(self._sign_in)
        row.addWidget(self.sign_in)
        # The other way to a post behind a sign-in: the person's own Chrome,
        # already signed in, pictured from the screen when they say.
        self.from_chrome = QPushButton("Take from my Chrome…")
        self.from_chrome.setToolTip(fromchrome.TAKE_TIP)
        self.from_chrome.setCursor(Qt.PointingHandCursor)
        self.from_chrome.setEnabled(False)
        self.from_chrome.clicked.connect(self._from_chrome)
        self.from_chrome.setVisible(sys.platform == "win32")
        row.addWidget(self.from_chrome)
        self.taker = None
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

        self._reread()

    # ------------------------------------------------------------- the list
    def _reread(self) -> None:
        """What links the pasted words hold, as they are typed or pasted."""
        if self.thread is not None:
            return                     # not while a capture is running
        self.found = links.find(self.box.toPlainText())
        self.list.clear()
        for row in self.found:
            item = QListWidgetItem(self._words(row))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, row.url)
            item.setToolTip(row.url)
            self.list.addItem(item)
        many = len(self.found)
        self.count.setText(
            NOTHING_YET if not many else
            f"{many} link{'s' if many != 1 else ''} found"
            + (" — numbered as they were sent" if links.numbered(self.found) else ""))
        self.capture.setText(f"Capture {many}" if many else "Capture")
        self.capture.setEnabled(bool(many))
        self.from_chrome.setEnabled(bool(many))

    @staticmethod
    def _words(row: links.Found) -> str:
        number = f"{row.number}. " if row.number else ""
        label = row.label or row.url
        return f"{number}{label}   —   {row.site}"

    def _ticked(self) -> list:
        out = []
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.checkState() == Qt.Checked:
                out.append(self.found[index])
        return out

    # ---------------------------------------------------------- the capture
    def _capture(self) -> None:
        wanted = self._ticked()
        if not wanted or self.thread is not None:
            return
        self.made = 0
        self.bar.setRange(0, len(wanted))
        self.bar.setValue(0)
        self.bar.show()
        self.capture.setEnabled(False)
        self.from_chrome.setEnabled(False)
        self.box.setReadOnly(True)
        self.count.setText(f"Capturing {len(wanted)}… the window stays usable.")

        self.thread = QThread(self)
        if embedded.usable():
            # The browser inside the program: the same capture, signed in
            # as the person is there, with nothing on the screen.
            host = embedded.Host.get()
            self.catcher = embedded.Catcher(wanted, embedded.PORT, host.target_id)
            self.catcher.caught.connect(self._one_caught)
        else:
            self.catcher = Catcher(wanted)
            self.catcher.caught.connect(self._one_done)
        self.catcher.moveToThread(self.thread)
        self.thread.started.connect(self.catcher.run)
        self.catcher.progress.connect(self._progress)
        self.catcher.finished.connect(self._all_done)
        self.thread.start()

    @Slot(int, int, str)
    def _progress(self, done: int, total: int, site: str) -> None:
        self.bar.setValue(done)
        self.count.setText(f"Capturing {done + 1 if done < total else total} of "
                           f"{total} — {site}")

    @Slot(object)
    def _one_done(self, caught: Caught) -> None:
        row = self._row_of(caught.found.url)
        if caught.shot is not None:
            self.made += 1
            self.window.clip_from_link(caught.shot, caught.found)
            if row is not None:
                row.setCheckState(Qt.Unchecked)
                row.setText("✓  " + self._words(caught.found))
        elif row is not None:
            row.setText("✕  " + self._words(caught.found) + f"   ({caught.why})")
            row.setForeground(theme.QDANGER)
            row.setToolTip(caught.why)
            if "sign" in caught.why.casefold():
                row.setData(Qt.UserRole + 1, "sign-in")

    @Slot(object, object, str)
    def _one_caught(self, found, shot, why: str) -> None:
        self._one_done(Caught(found=found, shot=shot, why=why))

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
        self.bar.hide()
        self.box.setReadOnly(False)
        self._say_signed_in()
        self.capture.setEnabled(bool(self.found))
        self.from_chrome.setEnabled(bool(self.found))
        left = sum(1 for index in range(self.list.count())
                   if self.list.item(index).checkState() == Qt.Checked)
        walled = sum(1 for index in range(self.list.count())
                     if self.list.item(index).data(Qt.UserRole + 1) == "sign-in")
        self.count.setText(
            f"{self.made} clipping{'s' if self.made != 1 else ''} added"
            + (f" — {left} still ticked" if left else "") + "."
            + ("  " + NEEDS_SIGN_IN.format(count=walled, them="them" if walled != 1 else "it")
               if walled and sys.platform == "win32" else ""))

    # --------------------------------------------------------------- other
    def _say_signed_in(self) -> None:
        """Which sites the program's own browser can already see posts on.

        Read from the names in its cookie file, never the values - those are
        the keys to those accounts.
        """
        try:
            known = (embedded.known_sign_ins() if embedded.usable()
                     else webshot.signed_in_sites())
        except Exception:  # noqa: BLE001 - only the words on a button
            known = []
        inside = embedded.usable()
        self.sign_in.setText(
            (INSIDE if inside else "Sign in for captures…") if not known else
            "Signed in: " + ", ".join(known) + (" \u2014 open" if inside else ""))

    def _sign_in(self) -> None:
        if embedded.usable():
            self._open_inside()
            return
        try:
            webshot.sign_in()
        except webshot.ShotError as bad:
            self.count.setText(str(bad))
            return
        self.count.setText("A browser window is open: sign in there, close it, "
                           "and capture again.")
        QTimer.singleShot(30000, self._say_signed_in)

    def _open_inside(self, url: str = "") -> None:
        """The browser inside the program, at the first ticked link or the
        sign-in page. One window; opening it again brings it forward."""
        if self.browser is None:
            ticked = self._ticked()
            where = url or (ticked[0].url if ticked else "https://x.com/login")
            try:
                self.browser = embedded.BrowserWindow(self.window, where, parent=self)
            except Exception as bad:  # noqa: BLE001 - the browser did not start
                self.count.setText(f"The browser inside the program could not open ({bad}).")
                return
            self.browser.finished.connect(self._inside_closed)
            self.browser.captured.connect(lambda _id: self._say_signed_in())
            self.count.setText("Sign in in the window that opened if a post needs it, "
                               "then capture here - or capture a page there by hand.")
        elif url:
            self.browser.open(url)
        self.browser.show()
        self.browser.raise_()
        self.browser.activateWindow()

    def _inside_closed(self, *_args) -> None:
        self.browser = None
        self._say_signed_in()

    def _from_chrome(self) -> None:
        """The ticked links, one after another, from the person's own Chrome."""
        wanted = self._ticked()
        if not wanted or self.thread is not None or self.taker is not None:
            return
        self.taker = fromchrome.TakeItDialog(self.window, wanted, parent=self)
        self.taker.taken.connect(self._taken)
        self.taker.done.connect(self._taker_done)
        self.count.setText(f"Taking {len(wanted)} from your Chrome — the small "
                           "panel says what to do.")
        self.taker.start()

    def _taken(self, url: str, _clip_id: int) -> None:
        self.made += 1
        row = self._row_of(url)
        if row is not None:
            row.setCheckState(Qt.Unchecked)
            row.setData(Qt.UserRole + 1, "")
            row.setForeground(theme.QINK)
            found = next((f for f in self.found if f.url == url), None)
            if found is not None:
                row.setText("✓  " + self._words(found) + "   (from your Chrome)")

    def _taker_done(self, count: int) -> None:
        taker, self.taker = self.taker, None
        if taker is not None:
            taker.deleteLater()
        self.count.setText(f"{count} clipping{'s' if count != 1 else ''} taken "
                           "from your Chrome.")

    def closeEvent(self, event):  # noqa: N802 - Qt's name
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
