"""Settings: the program's own housekeeping, in one place.

Opened from Settings in the menu at the top left of the window. What it holds
today is Clean up - the things a program that has been open all morning, every
morning, accumulates and does not need:

  * the duplicate check's measurements of every clipping - the picture prints,
    the ink profile and the headline read off the picture. They are worked out
    once and kept, which is what makes the check quick, and a measurement taken
    before a clipping was trimmed or turned, or by an older version of the
    program, describes a picture that is not the one on screen. Forgotten here
    and taken again from scratch: the duplicate RULE is not touched, only what
    it is fed.
  * the pages the browser inside the app has kept to open quicker. Its sign-ins
    are kept.
  * memory the program is holding on to.
  * the program's own temporary files.

Nothing a person made is touched by any of it: no clipping, no name, no crop,
no priority, no setting, no saved newspad.
"""

from __future__ import annotations

import gc
import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmapCache
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout)

from ..core import duplicates, imageops
from . import theme

#: What the program leaves in the system's temporary folder, and nothing else.
#: The self-check's files, the cover rendered for an export, and the scratch
#: folders the self-check makes. Named here so that nothing of anybody else's
#: can ever be matched.
TEMP_FILES = ("clippings-manager-*",)
TEMP_FOLDERS = ("clippings-jpeg-*", "clippings-session-*", "ClippingsManager")


def _size_of(path: Path) -> int:
    try:
        if path.is_file():
            return path.stat().st_size
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    except OSError:
        return 0


def _megabytes(size: int) -> str:
    return f"{size / 1_000_000:.1f} MB" if size >= 100_000 else f"{max(size, 0) // 1000} KB"


# ------------------------------------------------------------------ the jobs


def refresh_duplicate_data(window) -> int:
    """Forget every clipping's measurements, and check the report again.

    Both the press report and the sentiment board are forgotten; the report is
    checked again at once, and a category of the board is measured again the
    next time its own check runs. Returns how many clippings were forgotten.
    """
    clips = [row.clip for pool in (window.model, window.board_model)
             for row in pool.rows if row.clip is not None]
    count = duplicates.forget_measurements(clips)
    # The prints are parsed and remembered for speed (imageops._as_number);
    # every one of them is about to be taken again.
    imageops._as_number.cache_clear()
    if any(row.clip is not None for row in window.model.rows):
        try:
            window.check_duplicates_now()
        except Exception:  # noqa: BLE001 - the forgetting is the job; the check follows
            pass
    return count


def clear_browser_cache() -> int:
    """Empty the browser's saved pages, keeping its sign-ins.

    Returns the size removed, or -1 when the browser is open and has been asked
    to empty its own (it does that in the background, and says nothing back).
    """
    from . import embedded

    if embedded.Host.made():
        embedded.Host.get().clear_cache()
        return -1
    cache = embedded.profile_home() / "cache"
    size = _size_of(cache)
    shutil.rmtree(cache, ignore_errors=True)
    return size


def free_memory() -> None:
    """Let go of what the program is holding and does not need."""
    QPixmapCache.clear()
    imageops._as_number.cache_clear()
    gc.collect()


def delete_temp_files() -> tuple:
    """(how many, how much) of the program's own temporary files removed."""
    temp = Path(tempfile.gettempdir())
    count = size = 0
    for pattern in TEMP_FILES:
        for item in temp.glob(pattern):
            if item.is_file():
                try:
                    size += item.stat().st_size
                    item.unlink()
                    count += 1
                except OSError:
                    pass                  # in use; it goes next time
    for pattern in TEMP_FOLDERS:
        for item in temp.glob(pattern):
            if item.is_dir():
                size += _size_of(item)
                shutil.rmtree(item, ignore_errors=True)
                count += 1
    return count, size


# ------------------------------------------------------------------ the window


class SettingsDialog(QDialog):
    """Settings, opened from the menu at the top left of the window."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 18)
        outer.setSpacing(12)

        title = QLabel("Clean up")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {theme.NAVY};")
        outer.addWidget(title)
        said = QLabel(
            "Clears out what the program collects while it runs, so it works "
            "like it has just been installed. Your clippings, their names, "
            "trims and priorities, your settings and your saved newspads are "
            "not touched.")
        said.setWordWrap(True)
        said.setStyleSheet(f"color: {theme.MUTED};")
        outer.addWidget(said)

        self.refresh_box = QCheckBox(
            "Measure every clipping again for the duplicate check")
        self.refresh_box.setToolTip(
            "Forgets each clipping's picture fingerprint and the headline read "
            "off it, and checks for duplicates again from scratch. A clipping "
            "trimmed or turned since it was measured, or measured by an older "
            "version, is compared as it looks now. The duplicate rule itself "
            "does not change.")
        self.browser_box = QCheckBox(
            "Empty the browser's saved pages (your sign-ins stay)")
        self.memory_box = QCheckBox("Free memory the program is holding")
        self.temp_box = QCheckBox("Delete the program's temporary files")
        for box in (self.refresh_box, self.browser_box, self.memory_box, self.temp_box):
            box.setChecked(True)
            box.setCursor(Qt.PointingHandCursor)
            outer.addWidget(box)

        row = QHBoxLayout()
        self.clean_btn = QPushButton("Clean up now")
        self.clean_btn.setObjectName("NavyFilled")
        self.clean_btn.setCursor(Qt.PointingHandCursor)
        self.clean_btn.clicked.connect(self.clean_up)
        row.addWidget(self.clean_btn)
        row.addStretch(1)
        outer.addLayout(row)

        self.result = QLabel("")
        self.result.setWordWrap(True)
        self.result.setStyleSheet(f"color: {theme.INK};")
        self.result.hide()
        outer.addWidget(self.result)

        rule = QFrame()
        rule.setFrameShape(QFrame.HLine)
        rule.setStyleSheet(f"color: {theme.HAIRLINE};")
        outer.addWidget(rule)

        from .. import version
        from .export_dialog import settings_dir

        about = QLabel(f"Clippings Manager {version.describe()}\n"
                       f"Kept in: {settings_dir()}")
        about.setTextInteractionFlags(Qt.TextSelectableByMouse)
        about.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px;")
        outer.addWidget(about)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close = QPushButton("Close")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.accept)
        close_row.addWidget(close)
        outer.addLayout(close_row)

    def clean_up(self) -> list:
        """Do what is ticked, and say what was done. Returns the lines said."""
        said = []
        if self.refresh_box.isChecked():
            count = refresh_duplicate_data(self.window)
            said.append(f"{count} clipping{'s' if count != 1 else ''} will be measured "
                        "again - the duplicate check is running now.")
        if self.browser_box.isChecked():
            try:
                freed = clear_browser_cache()
                said.append("The browser is emptying its saved pages."
                            if freed < 0 else
                            f"The browser's saved pages removed ({_megabytes(freed)}).")
            except Exception:  # noqa: BLE001 - one job never stops the others
                said.append("The browser's saved pages could not be removed just now.")
        if self.temp_box.isChecked():
            count, size = delete_temp_files()
            said.append(f"{count} temporary item{'s' if count != 1 else ''} deleted "
                        f"({_megabytes(size)})." if count else
                        "No temporary files to delete.")
        if self.memory_box.isChecked():
            free_memory()
            said.append("Memory tidied.")
        if not said:
            said.append("Nothing was ticked, so nothing was done.")
        self.result.setText("\n".join(said))
        self.result.show()
        return said
