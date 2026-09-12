"""How the headline above each clipping is set, and how the page is laid out.

Until now the caption above every clipping printed at one fixed size, centred, in
one face, on A4 - the numbers were constants in ``export/layout.py``. This is that
same set of decisions, handed to the person compiling the newspad.

Each interface keeps its own copy, and each newspad its own copy of both. The
press report and the sentiment dossier are different documents for different
readers, and this project has treated them as independent in every other respect;
a division dossier set in 12pt serif should not quietly re-set tomorrow's newspad,
and one report's headline style should not re-set another's.

**The defaults are today's behaviour, exactly.** 15pt because that is what
``layout.CAPTION_SIZE`` has always been - not the 11pt a word processor would
suggest - centred, not bold, A4, no page numbers. A newspad exported with this panel
untouched comes out the same as one exported before it existed. That matters more
than a tidy default: the department has a year of newspads that look a particular
way.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSignalBlocker, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .cover_card import Segmented, settings_dir
from .design_file import DesignFile
from .fluid import ElidedLabel, FlowLayout

# Every choice, and what it is called on screen.
PAGES = [("a4", "A4  (210 x 297 mm)"), ("letter", 'Letter  (8.5 x 11")')]
# The fonts a Word user expects, by name. Naming one in CSS is not enough on its
# own - MuPDF knows a handful of built-in faces and quietly draws one of those for
# anything else - so the PDF exporter embeds the real file from this machine's own
# font folder, which is what Word does with the same file. A face this machine
# does not have simply does not appear in the list.
#
# "Standard (Sans)" stays first and stays the default: it is the behaviour every
# newspad has had, and choosing nothing must not change anything.
FAMILIES = [("sans", "Standard (Sans)"),
            ("arial", "Arial"),
            ("calibri", "Calibri"),
            ("times", "Times New Roman"),
            ("georgia", "Georgia"),
            ("cambria", "Cambria"),
            ("garamond", "Garamond"),
            ("bookantiqua", "Book Antiqua"),
            ("segoe", "Segoe UI"),
            ("tahoma", "Tahoma"),
            ("verdana", "Verdana"),
            ("trebuchet", "Trebuchet MS"),
            ("couriernew", "Courier New"),
            ("comic", "Comic Sans MS"),
            ("serif", "Classic (Serif)"),
            ("mono", "Courier (Mono)"),
            ("book", "Book (Rounded Serif)"),
            ("text", "Text (Noto Serif)")]


def offered_families() -> list:
    """The faces to show, with anything this machine lacks left out."""
    try:
        from ..export.build_pdf import WINDOWS_FACES, available_faces

        here = available_faces()
        return [(key, label) for key, label in FAMILIES
                if key not in WINDOWS_FACES or key in here]
    except Exception:  # noqa: BLE001 - if we cannot tell, offer everything
        return list(FAMILIES)
SIZES = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 24, 26, 28,
         30, 32, 36, 40, 44, 48]
ALIGNMENTS = [("left", "Left"), ("center", "Centre"), ("right", "Right")]

# What a fresh installation starts with. These are the sizes asked for after
# looking at real pages: 15pt was the number the code had always used and it reads
# small under a clipping that fills a sheet. Anyone can set any size in the panel;
# this is only where the dial starts.
DEFAULTS = {
    "page": "a4",           # layout.DEFAULT_PAGE
    "family": "sans",       # the system sans stack the captions have always used
    "size": 18,             # a caption has to carry a whole A4 sheet
    "bold": False,          # _draw_line's default
    "align": "center",      # _draw_line's default
    "page_numbers": False,  # there were none
}

# The dossier still sets its titles its own way - ranged left and bold, which is
# how a dossier reads - but no longer at 11pt, which was too small to carry a page.
# The two panels stay separate: they are different documents.
DOSSIER_DEFAULTS = {**DEFAULTS, "size": 16, "align": "left", "bold": True}


#: Pasted phone screenshots lose their status and navigation bars as a
#: crop. On unless switched off: the bars are never the clipping.
TIDY_KEY = "tidy_screenshots"


def tidy_wanted() -> bool:
    from .export_dialog import load_settings

    try:
        return bool(load_settings().get(TIDY_KEY, True))
    except Exception:  # noqa: BLE001 - no settings yet
        return True


def set_tidy_wanted(on: bool) -> None:
    from .export_dialog import load_settings, save_settings

    try:
        save_settings({**load_settings(), TIDY_KEY: bool(on)})
    except Exception:  # noqa: BLE001 - a preference, never a crash
        pass


def defaults_for(key: str) -> dict:
    return dict(DOSSIER_DEFAULTS if key == "sentiment" else DEFAULTS)


def settings_for(key: str) -> Path:
    """Newspad 1's file for one interface, so neither can disturb the other. The
    other newspads' are in their design folders - see DesignFile.adopt."""
    return settings_dir() / f"heading_{key}.json"


def load_layout(key: str, path: Optional[Path] = None) -> dict:
    """The saved choices for one interface, filled in with today's behaviour.

    Newspad 1's file unless another is named."""
    try:
        saved = json.loads(Path(path or settings_for(key)).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a missing or broken file is just defaults
        saved = {}
    return normalise_layout(key, saved)


def normalise_layout(key: str, saved) -> dict:
    """Whatever a file said, made into choices the exporter can use."""
    fallbacks = defaults_for(key)
    data = dict(fallbacks)
    if not isinstance(saved, dict):
        return data
    for name, fallback in fallbacks.items():
        value = saved.get(name, fallback)
        if isinstance(fallback, bool):
            data[name] = bool(value)
        elif isinstance(fallback, int):
            try:
                data[name] = int(value)
            except (TypeError, ValueError):
                data[name] = fallback
        else:
            data[name] = str(value)
    # A value from a newer build, or a hand-edited file, must not reach the exporter.
    if data["page"] not in dict(PAGES):
        data["page"] = fallbacks["page"]
    # Against the faces THIS machine has, not against the whole list. A settings
    # file naming a font that is installed on one laptop and not on another
    # otherwise reaches the exporter unchallenged: the panel shows "Standard
    # (Sans)", because that is all it can offer, while the report is set in
    # whatever the fallback chain lands on - so the same settings produce
    # differently sized captions, and differently scaled pictures, on the two
    # machines, with nothing on screen to say why.
    if data["family"] not in {key for key, _label in offered_families()}:
        data["family"] = fallbacks["family"]
    if data["align"] not in dict(ALIGNMENTS):
        data["align"] = fallbacks["align"]
    if not 6 <= data["size"] <= 72:
        data["size"] = fallbacks["size"]
    return data


class HeadingLayoutCard(QFrame, DesignFile):
    """The heading and page settings for one interface, in one newspad.

    A bare HeadingLayoutCard(key) is Newspad 1's, reading heading_{key}.json in
    the settings folder as every older build does. See ui/design_file.py.
    """

    changed = Signal()
    designProblem = Signal(str)

    def __init__(self, key: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.key = key
        self.design_name = f"heading_{key}.json"
        self._init_design()
        self.setObjectName("LayoutStrip")
        self.setStyleSheet(
            f"#LayoutStrip {{ background: {theme.THUMB_BG};"
            f" border: 1px solid {theme.HAIRLINE}; border-radius: 12px; }}"
            f"#LayoutStrip QLabel {{ background: transparent; border: none; }}"
        )
        self._defaults = defaults_for(key)
        self._values = dict(self._defaults)
        self._loading = True

        # Settings live in APPDATA, which is a roaming network profile in a lot of
        # offices - a synchronous write per keystroke is felt.
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self.save)

        self._build(subtitle)
        self.load()
        self._loading = False

    # ------------------------------------------------------------------ build
    def _build(self, subtitle: str) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 11, 14, 12)
        outer.setSpacing(9)

        row = QHBoxLayout()
        row.setSpacing(14)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        lead = QLabel("Heading & Document Layout")
        lead.setStyleSheet(
            f"color: {theme.INK}; font-size: 12px; font-weight: 800;")
        titles.addWidget(lead)
        note = ElidedLabel(
            subtitle or "Sets the headline above each clipping and the paper it "
                        "prints on.",
            floor=140,
        )
        note.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px;")
        titles.addWidget(note)
        row.addLayout(titles, 1)

        # Wrapped, not a fixed row: six controls abreast is what pinned the window
        # open before, and this panel sits inside a card that already scrolls.
        controls = FlowLayout(spacing=10, vertical_spacing=7)

        self.page_pick = self._combo(PAGES, "page", 118)
        controls.addWidget(self._labelled("Page", self.page_pick))

        self.family_pick = self._combo(offered_families(), "family", 150)
        controls.addWidget(self._labelled("Font", self.family_pick))

        self.size_pick = QComboBox()
        for points in SIZES:
            self.size_pick.addItem(
                f"{points}pt" + ("  (Standard)"
                                 if points == self._defaults["size"] else ""),
                points)
        self._dress(self.size_pick, 104)
        self.size_pick.currentIndexChanged.connect(lambda _i: self._read())
        controls.addWidget(self._labelled("Size", self.size_pick))

        self.bold_box = QCheckBox("Bold")
        self.page_box = QCheckBox("Page numbers")
        # Not a layout value: a preference, kept in the export settings file
        # that every newspad shares, and only shown here. The layout values
        # are HeadingStyle's own keywords and nothing else may sit among them.
        self.tidy_box = QCheckBox("Trim phone bars")
        self.tidy_box.setToolTip(
            "A pasted phone screenshot loses its status bar, its navigation "
            "bar and any blank margin, as a crop - the picture is untouched, "
            "and Trim\u2026 then Whole picture puts them back.")
        self.tidy_box.setCursor(Qt.PointingHandCursor)
        self.tidy_box.setStyleSheet(
            f"QCheckBox {{ color: {theme.INK}; font-size: 11px;"
            f" font-weight: 700; background: transparent; }}")
        self.tidy_box.setChecked(tidy_wanted())
        self.tidy_box.toggled.connect(set_tidy_wanted)
        controls.addWidget(self.tidy_box)
        for box in (self.bold_box, self.page_box):
            box.setCursor(Qt.PointingHandCursor)
            box.setStyleSheet(
                f"QCheckBox {{ color: {theme.INK}; font-size: 11px;"
                f" font-weight: 700; background: transparent; }}")
            box.toggled.connect(lambda _v: self._read())
            controls.addWidget(box)

        self.align_pick = Segmented(ALIGNMENTS, self._values["align"],
                                    icon_only=True)
        self.align_pick.changed.connect(lambda _v: self._read())
        self.align_pick.setMinimumWidth(120)
        controls.addWidget(self._labelled("Align", self.align_pick))

        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        holder.setLayout(controls)
        row.addWidget(holder, 0)
        outer.addLayout(row)

    def _combo(self, options, field: str, width: int) -> QComboBox:
        combo = QComboBox()
        for key, label in options:
            combo.addItem(label, key)
        self._dress(combo, width)
        combo.currentIndexChanged.connect(lambda _i: self._read())
        return combo

    def _dress(self, combo: QComboBox, width: int) -> None:
        combo.setCursor(Qt.PointingHandCursor)
        combo.setStyleSheet(
            f"QComboBox {{ background: {theme.SURFACE};"
            f" border: 1px solid {theme.HAIRLINE_STRONG}; border-radius: 9px;"
            f" padding: 4px 8px; color: {theme.INK}; font-size: 11px;"
            f" font-weight: 700; }}"
            f"QComboBox::drop-down {{ border: none; width: 18px; }}"
            + theme.COMBO_POPUP
        )
        combo.setMinimumWidth(min(width, 96))
        combo.setMaximumWidth(width + 40)

    @staticmethod
    def _labelled(text: str, control: QWidget) -> QWidget:
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        line = QHBoxLayout(holder)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        caption = QLabel(text + ":")
        caption.setStyleSheet(
            f"color: {theme.MUTED}; font-size: 11px; font-weight: 700;"
            f" background: transparent;")
        line.addWidget(caption)
        line.addWidget(control)
        return holder

    # ------------------------------------------------------------- the values
    def settings(self) -> dict:
        """What the exporter should use. A copy, so nobody edits ours."""
        return dict(self._values)

    def _apply(self) -> None:
        """Put the saved values onto the controls."""
        self.page_pick.setCurrentIndex(
            max(0, self.page_pick.findData(self._values["page"])))
        self.family_pick.setCurrentIndex(
            max(0, self.family_pick.findData(self._values["family"])))
        self.size_pick.setCurrentIndex(
            max(0, self.size_pick.findData(self._values["size"])))
        self.bold_box.setChecked(bool(self._values["bold"]))
        self.page_box.setChecked(bool(self._values["page_numbers"]))
        self.align_pick.set_value(self._values["align"])

    def _read(self) -> None:
        """Take the values off the controls and remember them."""
        if self._loading:
            return
        self._values = {
            "page": self.page_pick.currentData() or self._defaults["page"],
            "family": self.family_pick.currentData() or self._defaults["family"],
            "size": self.size_pick.currentData() or self._defaults["size"],
            "bold": self.bold_box.isChecked(),
            "align": self.align_pick.value(),
            "page_numbers": self.page_box.isChecked(),
        }
        self._changed_design()
        self.changed.emit()

    def reset(self) -> None:
        """Back to the way the newspad has always printed."""
        self._values = dict(self._defaults)
        self._loading = True
        self._apply()
        self._loading = False
        self._changed_design()
        self.changed.emit()

    # ------------------------------------------------------------------ disk
    # save(), flush(), load(), adopt() and hold() are DesignFile's.
    def _root_file(self) -> Path:
        return settings_for(self.key)

    def _design_state(self) -> dict:
        return dict(self._values)

    def _design_dump(self, state: dict) -> str:
        return json.dumps(state, indent=1)

    def _take_design(self, data: dict) -> None:
        """Put a heading file's choices on the controls. _loading AND blocked
        signals: _read takes every control at once, so a single stray signal
        part-way through would save a mix of two newspads' choices."""
        self._values = normalise_layout(self.key, data)
        was = self._loading
        self._loading = True
        blockers = [QSignalBlocker(control) for control in (
            self.page_pick, self.family_pick, self.size_pick, self.bold_box,
            self.page_box, self.align_pick)]
        try:
            self._apply()
        finally:
            for blocker in blockers:
                blocker.unblock()
            self._loading = was
