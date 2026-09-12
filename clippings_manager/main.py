"""Clippings Manager — entry point.

Fully offline. Nothing here opens a socket.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow both "python -m clippings_manager.main" and a frozen one-file build.
if __package__ in (None, ""):  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QLockFile, QTimer  # noqa: E402
from PySide6.QtGui import QFont, QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from clippings_manager.core import newspads  # noqa: E402
from clippings_manager.ui import scroll, theme  # noqa: E402
from clippings_manager.ui.main_window import MainWindow  # noqa: E402

#: Said to whoever opens a second copy. The four newspads are the way to work on
#: more than one morning at once; a second copy would share their folders.
ALREADY_OPEN = ("Clippings Manager is already open — use the Newspad button at "
                "the top to work on another newspad.")


def _one_copy_only(app):
    """Take the lock that lets one copy run. Returns (lock, carry_on).

    Two copies open at once would each save their own list into the same
    newspad folder and tidy away each other's pictures - measured, the first
    copy's pictures went from 3 to 0. So a second copy says so and leaves.

    A restart is the one second copy that must be let in: the copy it replaces
    still holds the lock while it finishes closing, so the new one waits for it
    rather than giving up. And a lock that cannot be made at all - a permission
    problem, a full disk - never stops the program opening on a working morning.
    """
    restarted = os.environ.pop("CM_RESTARTED", None) is not None
    try:
        where = newspads.root()
        where.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None, True
    lock = QLockFile(str(where / "running.lock"))
    # Never time a lock out while its owner lives. A lock whose owner has died
    # is recognised as stale by its process id, straight away.
    lock.setStaleLockTime(0)
    if lock.tryLock(30000 if restarted else 500):
        return lock, True
    if lock.error() == QLockFile.LockFailedError:
        if app.platformName() != "offscreen":
            QMessageBox.information(None, "Clippings Manager", ALREADY_OPEN)
        return None, False
    return None, True


def _own_the_taskbar_button() -> None:
    """Tell Windows this is its own application, before any window exists.

    Windows groups taskbar buttons by an "application user model ID". A packaged
    Python program that never sets one is filed under the interpreter that
    launched it, and the button then shows a generic icon instead of ours - which
    is what one machine was showing while another, whose icon cache happened to
    be warm, looked right.

    Must run before the first window is created, or Windows has already decided.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "NorthernRailwayPR.ClippingsManager")
    except Exception:  # noqa: BLE001 - a plain icon is not worth a crash
        pass


def main() -> int:
    # A packaged windowed build has nowhere to print to, so a missing piece shows up
    # as "nothing happened". --selftest exercises the parts most likely to be left
    # out of a bundle and reports what it found.
    if "--selftest" in sys.argv:
        from clippings_manager.selftest import main as selftest

        return selftest(sys.argv[1:])

    _own_the_taskbar_button()

    # How big to draw everything. This has to happen before the QApplication is
    # made: Qt reads the display scale once, at that moment, and there is no way
    # to change it afterwards. It is the only thing that scales the painted
    # clipping cards along with the widgets.
    from clippings_manager.ui import zoom

    zoom.apply_to_environment()

    # The browser inside the program is prepared before the application
    # exists: Qt reads its port and its flags once, and QtWebEngineWidgets
    # has to be imported before a QApplication is made (it sets the OpenGL
    # sharing the application needs). Nothing opens until it is used.
    from clippings_manager.ui import embedded

    embedded.prepare()

    app = QApplication(sys.argv)
    app.setApplicationName("Clippings Manager")
    app.setOrganizationName("Northern Railway PR")

    lock, carry_on = _one_copy_only(app)
    if not carry_on:
        return 0

    # The .ico first: it carries all seven sizes Windows picks from, where the
    # .png carries one 320px image that has to be scaled down for a 16px taskbar
    # and looks it. The .png stays as the fallback for anywhere that cannot read
    # an .ico.
    badge = theme.app_icon_path("icon.ico") or theme.app_icon_path()
    if badge:
        app.setWindowIcon(QIcon(badge))

    family = theme.load_fonts()
    font = QFont(family, 10)
    fallbacks = [f for f in (theme.devanagari_family(),) if f]
    if fallbacks:
        # Devanagari mastheads must never render as empty boxes.
        font.setFamilies([family, *fallbacks])
    app.setFont(font)
    app.setStyleSheet(theme.stylesheet())

    # One rule for the mouse wheel, for the whole application: it scrolls the
    # page, and a control under the pointer does not quietly change its own
    # value instead. See ui/scroll.WheelGuard - the report date is why.
    scroll.guard_the_wheel(app)

    window = MainWindow()
    window.show()
    # After the window is up, not before: building QPixmaps needs the
    # application, and a restore done inside the constructor would leave the
    # screen blank for seconds while it worked.
    QTimer.singleShot(0, window.restore_session)
    code = app.exec()
    # Here, not left to the interpreter's shutdown: a lock released that late
    # was measured still on disk afterwards.
    if lock is not None:
        lock.unlock()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
