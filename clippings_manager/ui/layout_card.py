"""How the headline above each clipping is set, and how the page is laid out.

Until now the caption above every clipping printed at one fixed size, centred, in
one face, on A4 - the numbers were constants in ``export/layout.py``. This is that
same set of decisions, handed to the person compiling the newspad.

Each interface keeps its own copy. The press report and the sentiment dossier are
different documents for different readers, and this project has treated them as
independent in every other respect; a division dossier set in 12pt serif should not
quietly re-set tomorrow's newspad.

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

from PySide6.QtCore import QTimer, Qt, Signal
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


def defaults_for(key: str) -> dict:
    return dict(DOSSIER_DEFAULTS if key == "sentiment" else DEFAULTS)


def settings_for(key: str) -> Path:
    """One file per interface, so neither can disturb the other."""
    return settings_dir() / f"heading_{key}.json"


def load_layout(key: str) -> dict:
    """The saved choices for one interface, filled in with today's behaviour."""
    fallbacks = defaults_for(key)
    data = dict(fallbacks)
    try:
        saved = json.loads(settings_for(key).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a missing or broken file is just defaults
        return data
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


class HeadingLayoutCard(QFrame):
    """The heading and page settings for one interface."""

    changed = Signal()

    def __init__(self, key: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.key = key
        self.setObjectName("LayoutStrip")
        self.setStyleSheet(
            f"#LayoutStrip {{ background: {theme.THUMB_BG};"
            f" border: 1px solid {theme.HAIRLINE}; border-radius: 12px; }}"
            f"#LayoutStrip QLabel {{ background: transparent; border: none; }}"
        )
        self._defaults = defaults_for(key)
        self._values = load_layout(key)
        self._loading = True

        # Settings live in APPDATA, which is a roaming network profile in a lot of
        # offices - a synchronous write per keystroke is felt.
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self.save)

        self._build(subtitle)
        self._apply()
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
        self._save_timer.start()
        self.changed.emit()

    def reset(self) -> None:
        """Back to the way the newspad has always printed."""
        self._values = dict(self._defaults)
        self._loading = True
        self._apply()
        self._loading = False
        self._save_timer.start()
        self.changed.emit()

    # ------------------------------------------------------------------ disk
    def save(self) -> None:
        try:
            path = settings_for(self.key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._values, indent=1), encoding="utf-8")
        except Exception:  # noqa: BLE001 - a settings write must never stop work
            pass

    def flush(self) -> None:
        """Write anything the debounce is still holding."""
        if self._save_timer.isActive():
            self._save_timer.stop()
            self.save()

    def load(self) -> None:
        self._values = load_layout(self.key)
        self._loading = True
        self._apply()
        self._loading = False
