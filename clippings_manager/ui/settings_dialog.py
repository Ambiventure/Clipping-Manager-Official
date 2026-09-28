"""Settings: the program's own housekeeping, in one place.

Opened from Settings in the menu at the top left of the window. It holds the
colour of the frame the preview puts round a clipping selected in the list
(2.0.62) - chosen on a colour wheel - and Clean up: the things a program that
has been open all morning, every morning, accumulates and does not need:

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
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

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

        # Everything but Close scrolls. The colour wheel made the window taller
        # than a 768-line screen has room for, and a window held shorter than
        # its contents squeezed the wheel until its lightness bar was gone.
        frame = QVBoxLayout(self)
        frame.setContentsMargins(0, 0, 0, 0)
        frame.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        outer = QVBoxLayout(body)
        outer.setContentsMargins(22, 20, 22, 8)
        outer.setSpacing(12)
        scroll.setWidget(body)
        frame.addWidget(scroll, 1)
        self._body = body
        self._scroll = scroll

        self._build_outline(outer)
        top_rule = QFrame()
        top_rule.setFrameShape(QFrame.HLine)
        top_rule.setStyleSheet(f"color: {theme.HAIRLINE};")
        outer.addWidget(top_rule)

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
        close_row.setContentsMargins(22, 8, 22, 16)
        close_row.addStretch(1)
        close = QPushButton("Close")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.accept)
        close_row.addWidget(close)
        frame.addLayout(close_row)
        # Enter and Space close the window. Neither may land on "Back to
        # yellow", the first button in it, which would throw a chosen colour
        # away without asking - nor on "Clean up now".
        close.setDefault(True)
        close.setFocus()
        self.close_btn = close

        # As tall as what is in it, as far as the screen allows; past that it
        # scrolls rather than squeezing anything.
        try:
            need = outer.totalHeightForWidth(520) + 60
            screen = self.screen().availableGeometry().height()
            self.resize(560, max(360, min(need, screen - 80)))
        except Exception:  # noqa: BLE001 - Qt's own size then
            pass

    # ------------------------------------------------ the selected clipping
    def _build_outline(self, outer) -> None:
        """The colour of the frame round a selected clipping in the preview."""
        from .colourwheel import ColourWheel, outline_colour

        title = QLabel("Selected clipping in the preview")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {theme.NAVY};")
        outer.addWidget(title)
        said = QLabel(
            "A clipping selected in the list is framed in this colour when it "
            "is open in the preview, so you can see at a glance which ones "
            "you have picked out. Choose the colour on the wheel; the bar "
            "under it makes it lighter or darker.")
        said.setWordWrap(True)
        said.setStyleSheet(f"color: {theme.MUTED};")

        row = QHBoxLayout()
        row.setSpacing(18)
        self.wheel = ColourWheel(outline_colour())
        self.wheel.changed.connect(self._outline_moving)
        self.wheel.picked.connect(self._outline_picked)
        row.addWidget(self.wheel, 0, Qt.AlignTop)

        # The words beside the wheel rather than over it, where there is room
        # going spare: over it they made the section too tall for the window.
        side = QVBoxLayout()
        side.setSpacing(8)
        side.addWidget(said)
        # What it will look like: a small dark window with a picture framed.
        self.outline_sample = QLabel()
        self.outline_sample.setFixedSize(150, 96)
        side.addWidget(self.outline_sample)
        self.outline_code = QLabel()
        self.outline_code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.outline_code.setStyleSheet(
            f"color: {theme.INK}; font-size: 12px; font-weight: 700;")
        side.addWidget(self.outline_code)
        self.outline_reset = QPushButton("Back to yellow")
        self.outline_reset.setCursor(Qt.PointingHandCursor)
        self.outline_reset.setToolTip("The frame's own colour, the yellow it "
                                      "starts as.")
        self.outline_reset.clicked.connect(self._outline_reset)
        self.outline_reset.setAutoDefault(False)
        side.addWidget(self.outline_reset, 0, Qt.AlignLeft)
        side.addStretch(1)
        row.addLayout(side, 1)
        outer.addLayout(row)
        self._show_outline(outline_colour())

    def _show_outline(self, colour: str) -> None:
        """The sample and the colour's code, for this colour."""
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

        sample = QPixmap(self.outline_sample.size())
        sample.fill(QColor(theme.DARK_VIEWPORT))
        painter = QPainter(sample)
        painter.setRenderHint(QPainter.Antialiasing, True)
        picture = QRectF(40, 20, 70, 56)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#F8F6F1"))
        painter.drawRect(picture)
        painter.setBrush(QColor("#1F2937"))
        painter.drawRect(QRectF(46, 26, 58, 9))
        painter.setBrush(QColor("#9CA3AF"))
        for line in range(4):
            painter.drawRect(QRectF(46, 40 + line * 8, 58 - line * 9, 4))
        painter.setPen(QPen(QColor(colour), 4))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(picture.adjusted(-5, -5, 5, 5), 4, 4)
        painter.end()
        self.outline_sample.setPixmap(sample)
        self.outline_code.setText(colour.upper())

    def _outline_to_preview(self, colour: str) -> None:
        preview = getattr(self.window, "preview", None)
        if preview is not None and hasattr(preview, "set_ring_colour"):
            preview.set_ring_colour(colour)

    def _outline_moving(self, colour) -> None:
        # Shown as it is chosen - on the sample and on an open preview - and
        # kept only once the button is let go.
        name = colour.name().upper()
        self._show_outline(name)
        self._outline_to_preview(name)

    def _outline_picked(self, colour) -> None:
        from .colourwheel import set_outline_colour

        kept = set_outline_colour(colour.name())
        self._show_outline(kept)
        self._outline_to_preview(kept)

    def _outline_reset(self) -> None:
        from .colourwheel import OUTLINE_DEFAULT, set_outline_colour

        kept = set_outline_colour(OUTLINE_DEFAULT)
        self.wheel.set_colour(kept)
        self._show_outline(kept)
        self._outline_to_preview(kept)

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
        # Brought into view: on a short screen the window scrolls, and the
        # lines saying what was done came in below the fold, so pressing the
        # button looked like nothing had happened.
        scroll = getattr(self, "_scroll", None)
        if scroll is not None:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, lambda: scroll.ensureWidgetVisible(
                self.result, 0, 8))
        return said
