"""Watching the clipboard while Collect is switched on - and only then.

Collect lets somebody stay in WhatsApp Web: they copy a photo, then its caption,
and the program takes each copy as it happens. This is the part that notices
the copies. It is careful in four ways, because the clipboard is shared with
every program on the machine and some of what passes through it is private:

*   **Off means off.** Nothing is connected to the clipboard until Collect is
    switched on, and it is disconnected when Collect stops. A copy made while
    it is off is never looked at.
*   **Private copies are left alone.** Password managers mark their copies
    "do not monitor", and Chrome marks every copy made in an Incognito or
    Guest window "not for clipboard history". Both are honoured: such a copy is
    not read at all.
*   **Read later, never inside the notification.** Qt's "the clipboard changed"
    signal arrives while the copying program may still be writing. The watcher
    only notes that something changed, waits a moment, and reads then - and if
    another program is holding the clipboard open, it waits and tries again
    rather than freezing the window. Nothing here sleeps or pumps events.
*   **Only what is needed is read.** Pictures, plain text, and a list of files
    (to say that files are not collected). Formats a browser renders on demand
    are never requested, remote addresses are never fetched, files are never
    opened, and nothing copied is logged or kept.

What a copy MEANS is decided elsewhere: core/copied.py reads text, and the
Collector (ui/collect.py) decides what to do with each copy.
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QTextDocumentFragment

from ..core.assemble import address_in
from . import dropped

WINDOWS_MIME = dropped.WINDOWS_MIME

#: Marks a copy as not for any clipboard watcher: password managers set these.
PRIVATE_FORMATS = {
    WINDOWS_MIME % "ExcludeClipboardContentFromMonitorProcessing",
    WINDOWS_MIME % "Clipboard Viewer Ignore",
}
#: A four-byte zero here means "not for clipboard history": Chrome sets it on
#: every copy from an Incognito or Guest window, and on copied passwords.
HISTORY = WINDOWS_MIME % "CanIncludeInClipboardHistory"

PICTURE_FORMATS = {
    "application/x-qt-image",
    WINDOWS_MIME % "PNG",
    WINDOWS_MIME % "JFIF",
    WINDOWS_MIME % "image/png",
    WINDOWS_MIME % "image/jpeg",
}


@dataclass(frozen=True)
class Copied:
    """One copy, as read. kind is "picture" (data, name) or "text" (text)."""

    kind: str
    data: bytes = b""
    name: str = ""
    text: str = ""


def _only_an_address(text: str) -> bool:
    """Chrome puts the picture's address beside a copied picture as text. That
    is not a caption, and it must not stop the picture being taken."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        return False
    line = lines[0]
    return (line.lower().startswith(("blob:", "data:", "file:", "http://", "https://"))
            or bool(address_in(line)))


def classify(mime, fmts: set):
    """What a copy is: a Copied, a short code for a note, "retry" or
    "retry-text" (read it again in a moment), or None.

    Codes: "private" and "private-history" (left alone), "files" (a copy in
    Explorer), "too-long" (text far too long to be a caption).
    """
    if fmts & PRIVATE_FORMATS:
        return "private"
    if HISTORY in fmts:
        try:
            if bytes(mime.data(HISTORY))[:4] == b"\0\0\0\0":
                return "private-history"
        except Exception:  # noqa: BLE001 - unreadable flag: treat as private
            return "private-history"
    # Never hasText(): Qt answers True for a copy that carries only addresses.
    has_text = any(f.startswith("text/plain") for f in fmts)
    text = mime.text() if has_text else ""
    has_picture = bool(fmts & PICTURE_FORMATS) or any(f.startswith("image/") for f in fmts)
    if not has_text and not has_picture and "text/html" in fmts:
        # Formatted text and no plain copy of it. A page's own copy handler
        # can do that, and the words are the same words: read them off the
        # markup, here, with nothing fetched - a fragment is parsed, never
        # loaded.
        try:
            text = QTextDocumentFragment.fromHtml(mime.html()).toPlainText()
        except Exception:  # noqa: BLE001 - markup that will not parse
            text = ""
        has_text = bool(text.strip())
    if has_picture and (not text.strip() or _only_an_address(text)):
        got = dropped.read_picture(mime, fmts)
        if got:
            return Copied("picture", data=got[0], name=got[1])
        return "retry"
    if has_text:
        if not text.strip():
            return "retry-text"      # still being written, or genuinely empty
        if len(text) > ClipboardWatcher.MAX_TEXT:
            return "too-long"
        return Copied("text", text=text)
    if "text/uri-list" in fmts:
        try:
            if any(url.isLocalFile() for url in mime.urls()):
                return "files"
        except Exception:  # noqa: BLE001
            pass
    return None


def _on_windows() -> bool:
    return sys.platform == "win32" and QGuiApplication.platformName() == "windows"


def _held_by_another_program() -> bool:
    """Whether some program has the clipboard open right now (Windows only)."""
    if not _on_windows():
        return False
    try:
        user32 = ctypes.windll.user32
        user32.GetOpenClipboardWindow.restype = ctypes.c_void_p
        return bool(user32.GetOpenClipboardWindow())
    except Exception:  # noqa: BLE001
        return False


def _system_seq() -> int:
    """Windows' own count of clipboard changes, to notice a change mid-read."""
    if not _on_windows():
        return 0
    try:
        user32 = ctypes.windll.user32
        user32.GetClipboardSequenceNumber.restype = ctypes.c_uint32
        return int(user32.GetClipboardSequenceNumber())
    except Exception:  # noqa: BLE001
        return 0


class ClipboardWatcher(QObject):
    """Notices copies while switched on, and hands each one over, once."""

    copied = Signal(object)     # a Copied
    #: "private", "private-history", "files", "too-long", "unreadable" - and
    #: "nothing": a copy that held neither a picture nor any text, said so
    #: that a copy which went nowhere is never a mystery.
    note = Signal(str)

    SETTLE_MS = 150
    RETRY_MS = (150, 300, 600, 1200)
    MAX_TEXT = 1000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._on = False
        self._connected = False
        self.changes = 0          # copies noticed while on
        self.read_at = -1         # the last of them that has been dealt with
        self._tries = 0
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.timeout.connect(self._read)
        # Seams, so a test can stand in for Windows.
        self.owns = lambda: QGuiApplication.clipboard().ownsClipboard()
        self.held = _held_by_another_program
        self.system_seq = _system_seq

    def is_on(self) -> bool:
        return self._on

    def set_on(self, on: bool) -> None:
        clipboard = QGuiApplication.clipboard()
        if on and not self._connected:
            clipboard.dataChanged.connect(self._changed)
            self._connected = True
        if not on and self._connected:
            try:
                clipboard.dataChanged.disconnect(self._changed)
            except (RuntimeError, TypeError):
                pass
            self._connected = False
        self._on = bool(on)
        self._settle.stop()
        self._tries = 0

    def already_read(self) -> bool:
        """Whether the copy now on the clipboard has already been dealt with -
        so Ctrl+V does not add it a second time."""
        return self._on and self.changes > 0 and self.read_at == self.changes

    def _changed(self) -> None:
        if not self._on:
            return
        self.changes += 1
        self._tries = 0
        self._settle.start(self.SETTLE_MS)

    def _read(self) -> None:
        if not self._on:
            return
        try:
            if self.owns():
                self.read_at = self.changes      # our own copy, not the user's
                return
        except Exception:  # noqa: BLE001
            pass
        if self.held():
            self._again(picture=True)
            return
        mime = QGuiApplication.clipboard().mimeData()
        if mime is None:
            self.read_at = self.changes
            return
        before = self.system_seq()
        try:
            fmts = set(mime.formats())
            result = classify(mime, fmts)
        except Exception:  # noqa: BLE001 - a half-written copy
            result = "retry"
        if before and self.system_seq() != before:
            self._again(picture=True)            # it changed while we read
            return
        if result in ("retry", "retry-text"):
            # A picture that never arrives is said; text that stays empty is not.
            self._again(picture=result == "retry")
            return
        self.read_at = self.changes
        if isinstance(result, Copied):
            self.copied.emit(result)
        elif isinstance(result, str):
            self.note.emit(result)
        else:
            self.note.emit("nothing")

    def _again(self, picture: bool) -> None:
        if self._tries < len(self.RETRY_MS):
            self._settle.start(self.RETRY_MS[self._tries])
            self._tries += 1
            return
        self.read_at = self.changes
        if picture:
            self.note.emit("unreadable")
