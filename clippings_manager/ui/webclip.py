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

from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout,
                               QLabel, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QProgressBar, QPushButton,
                               QVBoxLayout)

from ..core import links, webshot
from . import theme

PASTE_HINT = ("Paste a link, or the whole WhatsApp message with the morning's "
              "list in it. Every link in it is found, in the order it was sent.")
NOTHING_YET = "No links yet — paste a message above."
SIGN_IN_TIP = ("X and Facebook only show a post to somebody signed in. This "
               "opens a browser window of the program's own, where you sign in "
               "once. Your everyday Chrome is not touched, and the program "
               "never sees your password.")


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
        self.sign_in.setToolTip(SIGN_IN_TIP)
        self._say_signed_in()
        self.sign_in.setCursor(Qt.PointingHandCursor)
        self.sign_in.clicked.connect(self._sign_in)
        row.addWidget(self.sign_in)
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
        self.box.setReadOnly(True)
        self.count.setText(f"Capturing {len(wanted)}… the window stays usable.")

        self.thread = QThread(self)
        self.catcher = Catcher(wanted)
        self.catcher.moveToThread(self.thread)
        self.thread.started.connect(self.catcher.run)
        self.catcher.caught.connect(self._one_done)
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
        left = sum(1 for index in range(self.list.count())
                   if self.list.item(index).checkState() == Qt.Checked)
        self.count.setText(
            f"{self.made} clipping{'s' if self.made != 1 else ''} added"
            + (f" — {left} still ticked" if left else "") + ".")

    # --------------------------------------------------------------- other
    def _say_signed_in(self) -> None:
        """Which sites the program's own browser can already see posts on.

        Read from the names in its cookie file, never the values - those are
        the keys to those accounts.
        """
        try:
            known = webshot.signed_in_sites()
        except Exception:  # noqa: BLE001 - only the words on a button
            known = []
        self.sign_in.setText("Sign in for captures…" if not known else
                             "Signed in: " + ", ".join(known))

    def _sign_in(self) -> None:
        try:
            webshot.sign_in()
        except webshot.ShotError as bad:
            self.count.setText(str(bad))
            return
        self.count.setText("A browser window is open: sign in there, close it, "
                           "and capture again.")
        QTimer.singleShot(30000, self._say_signed_in)

    def closeEvent(self, event):  # noqa: N802 - Qt's name
        if self.catcher is not None:
            self.catcher.stop()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(6000)
            self.thread = None
        super().closeEvent(event)
