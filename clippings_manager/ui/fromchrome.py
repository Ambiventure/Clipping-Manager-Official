"""A post taken from the person's own Chrome, with their own sign-in.

The small panel that runs it stays on top while the person's Chrome shows
the link: they scroll until the post is on the screen and press Take it. The
panel steps out of the way for the picture, pictures the Chrome window, adds
the clipping, and opens it in the preview with the trim already started - the
picture is the whole browser window, tabs and all, and the post is cut out of
it the way a cutting is cut out of a page. Then the next link.

Why not the program's own browser, signed in once? It is still there, and it
is the better way for a site that lets a signed-in browser read posts in the
background. This is for what the person asked for - "it has my login already"
- and it is the honest version of it: Chrome will not lend an open profile to
anybody, so the program borrows the screen instead. See core/chromewin.py.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

from ..core import chromewin, webshot
from . import theme

#: Stand-ins the suites replace: the finder, the opener and the picture.
front_window = chromewin.front_window
open_link = chromewin.open_link

#: The panel steps out of the picture and Windows is given this long to
#: repaint what was under it before the screen is read.
OUT_OF_THE_WAY_MS = 260

TAKE_TIP = ("Opens each ticked link in your own Chrome, signed in as you "
            "already are, and takes the picture from the screen when you say "
            "the post is showing. The program only asks Chrome to open the "
            "link — you do the scrolling.")
NO_CHROME = "No Chrome window is open to take the picture from."
NO_BROWSER = "Chrome was not found on this computer."


def picture(window: chromewin.Window) -> bytes:
    """The Chrome window as it is on the screen, as PNG bytes."""
    from PySide6.QtCore import QBuffer, QIODevice

    left, top, right, bottom = window.frame
    screen = (QGuiApplication.screenAt(QPoint(left, top))
              or QGuiApplication.primaryScreen())
    ratio = screen.devicePixelRatio() or 1.0
    # The frame is in the screen's own pixels; Qt asks in device-independent
    # ones and hands back a picture at the screen's scale.
    x, y = int(left / ratio), int(top / ratio)
    w, h = int((right - left) / ratio), int((bottom - top) / ratio)
    shot = screen.grabWindow(0, x, y, w, h)
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    shot.save(buffer, "PNG")
    return bytes(buffer.data())


class TakeItDialog(QDialog):
    """One link after another: open it in Chrome, wait, take it, trim it."""

    taken = Signal(str, int)      # url, the clipping's id
    skipped = Signal(str)
    done = Signal(int)            # how many were taken

    def __init__(self, window, wanted: list, parent=None):
        super().__init__(parent or window)
        self.window = window
        self.wanted = list(wanted)
        self.at = -1
        self.count = 0
        self.stage = "waiting"
        self.setWindowTitle("Take from my Chrome")
        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint
                            | Qt.CustomizeWindowHint | Qt.WindowTitleHint
                            | Qt.WindowCloseButtonHint)
        self.setModal(False)
        self.setMinimumWidth(420)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 12)
        outer.setSpacing(8)
        self.which = QLabel()
        self.which.setStyleSheet("font-weight: 700;")
        self.which.setWordWrap(True)
        outer.addWidget(self.which)
        self.say = QLabel()
        self.say.setWordWrap(True)
        self.say.setStyleSheet(f"color: {theme.INK};")
        outer.addWidget(self.say)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet(f"color: {theme.DANGER};")
        self.note.hide()
        outer.addWidget(self.note)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.take = QPushButton("Take it")
        self.take.setObjectName("NavyFilled")
        self.take.clicked.connect(self._take)
        self.skip = QPushButton("Skip this one")
        self.skip.clicked.connect(self._skip)
        self.next = QPushButton("Next link")
        self.next.setObjectName("NavyFilled")
        self.next.clicked.connect(self._next)
        self.stop = QPushButton("Stop")
        self.stop.clicked.connect(self.close)
        for button in (self.take, self.skip, self.next, self.stop):
            button.setCursor(Qt.PointingHandCursor)
        row.addWidget(self.take)
        row.addWidget(self.skip)
        row.addWidget(self.next)
        row.addStretch(1)
        row.addWidget(self.stop)
        outer.addLayout(row)

    # --------------------------------------------------------------- steps
    def start(self) -> None:
        self.show()
        self._next()

    @property
    def current(self):
        return self.wanted[self.at] if 0 <= self.at < len(self.wanted) else None

    def _next(self) -> None:
        self.at += 1
        found = self.current
        if found is None:
            self.close()            # closing says how many were taken
            return
        self.stage = "waiting"
        self.note.hide()
        self.which.setText(f"{self.at + 1} of {len(self.wanted)} — {found.site}")
        if open_link(found.url):
            self.say.setText("Opened in your Chrome. Scroll until the post is on "
                             "the screen, then press Take it.")
        else:
            self.say.setText(NO_BROWSER + " Open the link yourself, then press "
                             "Take it with the post on the screen.")
        self._buttons()

    def _buttons(self) -> None:
        waiting = self.stage == "waiting"
        self.take.setVisible(waiting)
        self.skip.setVisible(waiting)
        self.next.setVisible(not waiting)
        self.next.setText("Next link" if self.at + 1 < len(self.wanted) else "Done")

    def _skip(self) -> None:
        found = self.current
        if found is not None:
            self.skipped.emit(found.url)
        self._next()

    def _take(self) -> None:
        if self.current is None or self.stage != "waiting":
            return
        # Out of the picture first: the panel stays on top of everything,
        # Chrome included, and would be in its own photograph.
        self.hide()
        QTimer.singleShot(OUT_OF_THE_WAY_MS, self._snap)

    def _snap(self) -> None:
        found = self.current
        taken = False
        try:
            window = front_window()
            if window is None:
                self.note.setText(NO_CHROME)
                self.note.show()
                return
            png = picture(window)
            shot = webshot.Shot(png=png, url=found.url, title=window.title,
                                site=found.site, kind="post",
                                width=window.width, height=window.height)
            clip_id = self.window.clip_from_link(shot, found)
            if clip_id is None:
                self.note.setText("The picture could not be read.")
                self.note.show()
                return
            self.count += 1
            self.stage = "taken"
            taken = True
            self.taken.emit(found.url, clip_id)
            position = self.window.pool().position_of(clip_id) + 1
            self.say.setText(f"Taken as No. {position}. In the preview, drag the "
                             "edges in around the post and press Keep this — "
                             "then come back here for the next one.")
            self._buttons()
            self.window.open_preview(clip_id)
            preview = getattr(self.window, "preview", None)
            if preview is not None:
                preview._trim_start()
        finally:
            # Back on top either way - but the preview keeps the keyboard
            # when there is a trim to do, so the next thing pressed is its
            # edge and not this panel.
            self.show()
            if not taken:
                self.raise_()
                self.activateWindow()

    def closeEvent(self, event):  # noqa: N802 - Qt's name
        self.done.emit(self.count)
        super().closeEvent(event)
