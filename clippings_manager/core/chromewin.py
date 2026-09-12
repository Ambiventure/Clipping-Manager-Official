"""The person's own Chrome window, found on the screen, for a picture of what
it is showing.

Chrome keeps the profile it has open to itself. No second program may drive
it, and its cookies are bound to it: a cookie row copied out of a profile is
thrown away by a Chrome started on any other folder (measured, 2.0.25, with
the app-bound "v20" cookies every profile on the office machine has). So a
post that only a signed-in person may see is taken the way the office takes
it today - from the screen, with the person's own Chrome showing it - only
without the Snipping Tool. The program opens the link in their Chrome, waits
for them to say the post is on screen, and pictures the Chrome window.

Nothing on the site is done by the program: the person scrolls, the person
says when. Chrome is only ever asked to open a link, which is what a click on
one in WhatsApp asks of it.

Windows only. Elsewhere the finder finds nothing and the opener says so.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from . import webshot

#: Every top-level Chrome window has this class - and so does every Electron
#: program (Claude, WhatsApp Desktop, VS Code). The window title tells them
#: apart: Chrome's ends in its own name.
CHROME_CLASS = "Chrome_WidgetWin_1"
TITLE_TAILS = (" - Google Chrome", " - Microsoft Edge", " - Chromium")

#: DWMWA_EXTENDED_FRAME_BOUNDS: the frame as drawn, without the invisible
#: resize border Windows 10 and 11 keep around a window (7 pixels a side at
#: 100%). GetWindowRect includes that border and the picture would too.
_FRAME_BOUNDS = 9


@dataclass(frozen=True)
class Window:
    """One Chrome window on the screen."""

    handle: int
    title: str        # the page's title, with the browser's name taken off
    frame: tuple      # left, top, right, bottom in screen pixels
    browser: str      # "Google Chrome", "Microsoft Edge", "Chromium"

    @property
    def width(self) -> int:
        return self.frame[2] - self.frame[0]

    @property
    def height(self) -> int:
        return self.frame[3] - self.frame[1]


def windows() -> list[Window]:
    """Chrome's windows, front first. Minimised ones are not on the screen
    and are left out. Off Windows there are none."""
    if sys.platform != "win32":
        return []
    import ctypes
    import ctypes.wintypes as wt

    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    found: list[Window] = []

    def each(handle, _lparam):
        if not user32.IsWindowVisible(handle) or user32.IsIconic(handle):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(handle, cls, 64)
        if cls.value != CHROME_CLASS:
            return True
        length = user32.GetWindowTextLengthW(handle)
        words = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(handle, words, length + 1)
        title = words.value
        tail = next((t for t in TITLE_TAILS if title.endswith(t)), "")
        if not tail:
            return True
        rect = wt.RECT()
        got = dwmapi.DwmGetWindowAttribute(handle, _FRAME_BOUNDS, ctypes.byref(rect),
                                           ctypes.sizeof(rect))
        if got != 0:
            user32.GetWindowRect(handle, ctypes.byref(rect))
        if rect.right - rect.left < 80 or rect.bottom - rect.top < 80:
            return True
        found.append(Window(int(handle), title[:-len(tail)],
                            (rect.left, rect.top, rect.right, rect.bottom),
                            tail[3:]))
        return True

    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(each)
    user32.EnumWindows(proc, 0)
    return found


def front_window() -> Window | None:
    """The Chrome window in front of the others, or None when none is open."""
    found = windows()
    return found[0] if found else None


def open_link(url: str) -> bool:
    """Ask the person's own Chrome to open the link - in the window and the
    profile they already have open, signed in as they are. False when there
    is no Chrome to ask."""
    path = webshot.find_browser()
    if not path:
        return False
    try:
        subprocess.Popen([path, url], close_fds=True)
    except OSError:
        return False
    return True
