"""The export screen: date, formats, folder, cover, then build.

Settings persist to the user's app-data folder, so tomorrow the dialog opens with
last time's output folder and cover template already filled in.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..export import build_docx, build_pdf
from ..export import layout as export_layout
from . import theme
from .datefield import DayEdit, refuse_future, today_button


# What the day's press report is called on disk. The PDF and the Word file take
# the same name so the pair sits together in a folder, and the date is written
# the way the department writes it. The dossier is named differently on purpose:
# that one is per division and says so.
REPORT_NAME = "PRESS MEDIA COVERAGE OVER NORTHERN RAILWAYS"


# Windows will not accept these in a file name, and a masthead occasionally
# carries one - "Amar Ujala: Delhi" would be rejected by the operating system
# rather than by us, with a message nobody can act on.
FORBIDDEN = '\\/:*?"<>|'


def clean_name(text: str) -> str:
    """A file name Windows will accept, without silently renaming their file.

    Only the characters the operating system refuses are removed. Spaces,
    brackets, full stops and dashes are all left alone: the department's names
    are full of them and they are what makes the file recognisable in a folder.
    """
    kept = "".join(" " if ch in FORBIDDEN else ch for ch in (text or ""))
    return " ".join(kept.split()).strip(" .")


def keeping_folder() -> Path:
    """Where a file somebody wants to KEEP should be offered to them.

    The folder the reports already go to - Documents until it is changed - so
    anything saved to keep lands beside the newspads rather than in whichever
    folder the application happened to be started from. That folder, on a
    frozen copy, is the program's own, which is exactly the place a file that
    has to survive an update must not be.
    """
    import json as _json

    try:
        saved = _json.loads(
            (settings_dir() / "export.json").read_text(encoding="utf-8"))
        where = Path(str(saved.get("folder") or ""))
        if where.is_dir():
            return where
    except Exception:  # noqa: BLE001 - nothing saved, or not a folder any more
        pass
    documents = Path.home() / "Documents"
    return documents if documents.is_dir() else Path.home()


def settings_dir() -> Path:
    """Where user edits live, so an app update never wipes them."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    folder = base / "ClippingsManager"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _settings_file() -> Path:
    return settings_dir() / "export.json"


def load_settings() -> dict:
    try:
        return json.loads(_settings_file().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a missing or broken file just means defaults
        return {}


def save_settings(data: dict) -> None:
    try:
        _settings_file().write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:  # noqa: BLE001
        pass


class ExportDialog(QDialog):
    """Choose what to build, then build it."""

    def __init__(self, clips: list, parent=None, prefer: str = "pdf",
                 report_date=None, cover_image=None, heading: str = "",
                 cover_baked: bool = False, layout_style: dict | None = None,
                 cover_blocks: list | None = None):
        super().__init__(parent)
        self.clips = clips
        self.heading = heading
        # The generated cover, handed over as a layout as well as a picture. The
        # PDF takes the picture - nobody edits a PDF - and Word takes the layout,
        # so its cover arrives as text that can be corrected afterwards.
        self.cover_blocks = list(cover_blocks or [])
        # How the caption above each clipping is set, from the panel on the page
        # behind this dialog. ``heading`` above is the cover title - a different
        # thing that happened to want the same word.
        self.layout_style = dict(layout_style or {})
        # A baked cover already carries its count and date, painted into the
        # picture by the cover card. Saying so keeps the builders from printing
        # both lines a second time on top of it.
        self.cover_baked = cover_baked
        self._baked_path = str(cover_image or "") if cover_baked else ""
        self.results: list[str] = []
        self.setWindowTitle("Build the newspad")
        self.setModal(True)
        self.resize(620, 0)
        self.setStyleSheet(theme.stylesheet())

        saved = load_settings()
        if self.layout_style.get("page"):
            saved = {**saved, "page": self.layout_style["page"]}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(15)

        heading = QLabel(
            f"<b style='font-size:15px'>{len(clips)} clipping"
            f"{'s' if len(clips) != 1 else ''} ready</b>"
        )
        layout.addWidget(heading)
        note = QLabel(
            "One clipping per page, in exactly the order shown in the list, with a "
            "cover carrying the count and the date."
        )
        note.setWordWrap(True)
        note.setObjectName("CardHint")
        layout.addWidget(note)

        # --- date ----------------------------------------------------------
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("Date on the cover"))
        self.date = DayEdit(what="newspad")
        if report_date:
            self.date.setDate(
                QDate(report_date.year, report_date.month, report_date.day))
        date_row.addWidget(self.date)
        self.today_btn = today_button(self.date, "ExportToday")
        date_row.addWidget(self.today_btn)
        date_row.addSpacing(18)

        date_row.addWidget(QLabel("Paper"))
        self.page_size = QComboBox()
        self.page_size.addItem("A4  (210 x 297 mm)", "a4")
        self.page_size.addItem("Letter  (8.5 x 11 in)", "letter")
        wanted = saved.get("page", "a4")
        self.page_size.setCurrentIndex(0 if wanted == "a4" else 1)
        date_row.addWidget(self.page_size)
        date_row.addStretch(1)
        layout.addLayout(date_row)

        self.fit_page = QCheckBox(
            "Fit each clipping to its page, centred  (recommended)"
        )
        self.fit_page.setChecked(saved.get("fit", True))
        self.fit_page.setToolTip(
            "Off: place at the original newspad size - 220 DPI against the left "
            "margin. Small cuttings then sit in the top corner of the sheet."
        )
        layout.addWidget(self.fit_page)

        # --- formats -------------------------------------------------------
        self.want_pdf = QCheckBox("PDF  (the newspad itself)")
        self.want_docx = QCheckBox("Word (.docx)  — for editing afterwards")
        self.want_pdf.setChecked(saved.get("pdf", prefer == "pdf"))
        self.want_docx.setChecked(saved.get("docx", prefer == "docx"))
        layout.addWidget(self.want_pdf)
        layout.addWidget(self.want_docx)

        # --- name ----------------------------------------------------------
        # The department's own name for the day's file, if they have one. The
        # default is the standing one with the date on the end, which is what
        # every file was called before this box existed; typing over it renames
        # BOTH files, so the PDF and the Word document go on being a pair.
        name_row = QHBoxLayout()
        self.file_name = QLineEdit(
            f"{REPORT_NAME} {self.date.date().toPython().strftime('%d.%m.%Y')}")
        self.file_name.setToolTip(
            "The name both files are saved under. The extension is added for "
            "you, so there is no need to type .pdf or .docx.")
        reset = QPushButton("Standard name")
        reset.setToolTip("Put the department's usual name back.")
        reset.clicked.connect(self._standard_name)
        # Change the date and the suggested name follows it - unless the name
        # has been typed over, in which case it is theirs and is left alone.
        self._name_is_ours = True
        self.file_name.textEdited.connect(self._name_typed)
        self.date.dateChanged.connect(self._date_changed)
        name_row.addWidget(QLabel("File name"))
        name_row.addWidget(self.file_name, 1)
        name_row.addWidget(reset)
        layout.addLayout(name_row)

        # --- folder --------------------------------------------------------
        folder_row = QHBoxLayout()
        self.folder = QLineEdit(saved.get("folder", str(Path.home() / "Documents")))
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._pick_folder)
        folder_row.addWidget(QLabel("Save into"))
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)
        layout.addLayout(folder_row)

        # --- cover ---------------------------------------------------------
        cover_row = QHBoxLayout()
        self.cover = QLineEdit(cover_image or saved.get("cover", ""))
        self.cover.setPlaceholderText("optional — your standard cover artwork")
        pick_cover = QPushButton("Choose…")
        clear_cover = QPushButton("Clear")
        pick_cover.clicked.connect(self._pick_cover)
        clear_cover.clicked.connect(lambda: self.cover.setText(""))
        # Choosing a different picture here replaces the built cover, so the
        # count and date have to come back as drawn text.
        self.cover.textEdited.connect(self._cover_replaced)
        pick_cover.clicked.connect(self._cover_replaced)
        clear_cover.clicked.connect(self._cover_replaced)
        cover_row.addWidget(QLabel("Cover image"))
        cover_row.addWidget(self.cover, 1)
        cover_row.addWidget(pick_cover)
        cover_row.addWidget(clear_cover)
        layout.addLayout(cover_row)

        self.cover_note = QLabel(
            "Built from the Cover Page Template, with the date and clipping "
            "count already placed on it."
        )
        self.cover_note.setObjectName("SubtleHint")
        self.cover_note.setVisible(self.cover_baked)
        layout.addWidget(self.cover_note)

        rule = QFrame()
        rule.setFrameShape(QFrame.HLine)
        rule.setStyleSheet(f"color: {theme.HAIRLINE};")
        layout.addWidget(rule)

        self.progress = QProgressBar()
        self.progress.setRange(0, max(1, len(clips)))
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.status = QLabel()
        self.status.setObjectName("CardHint")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.open_after = QCheckBox("Open when finished")
        self.open_after.setChecked(saved.get("open_after", True))
        buttons.addWidget(self.open_after)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.build_btn = QPushButton("Build")
        self.build_btn.setObjectName("OrangeFilled")
        self.build_btn.setMinimumWidth(120)
        self.build_btn.clicked.connect(self._build)
        buttons.addWidget(cancel)
        buttons.addWidget(self.build_btn)
        layout.addLayout(buttons)

    # ------------------------------------------------------------- choosing
    def _standard_name(self) -> None:
        stamp = self.date.date().toPython()
        self.file_name.setText(f"{REPORT_NAME} {stamp.strftime('%d.%m.%Y')}")
        self._name_is_ours = True

    def _name_typed(self, _text: str) -> None:
        self._name_is_ours = False

    def _date_changed(self, *_args) -> None:
        if self._name_is_ours:
            self._standard_name()

    def _cover_replaced(self, *_args) -> None:
        """Re-check rather than simply clear the flag: cancelling the file
        dialog leaves the built cover in place, and it still carries its text."""
        self.cover_baked = bool(
            self._baked_path and self.cover.text().strip() == self._baked_path
        )
        self.cover_note.setVisible(self.cover_baked)

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Where should the newspad go?", self.folder.text()
        )
        if folder:
            self.folder.setText(folder)

    def _pick_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose the cover artwork", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)",
        )
        if path:
            self.cover.setText(path)

    # -------------------------------------------------------------- building
    def _build(self) -> None:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if not (self.want_pdf.isChecked() or self.want_docx.isChecked()):
            self.status.setText("Choose PDF, Word, or both.")
            return
        folder = Path(self.folder.text().strip() or ".")
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001
            self.status.setText(
                f"That folder cannot be written to ({type(exc).__name__}). "
                f"Pick another one."
            )
            return

        if not refuse_future(self, self.date.date().toPython(), "newspad"):
            return

        if not clean_name(self.file_name.text()):
            self.status.setText(
                "Give the file a name - or press Standard name.")
            self.file_name.setFocus()
            return

        stamp = self.date.date().toPython()
        cover = self.cover.text().strip() or None
        if cover and not Path(cover).exists():
            self.status.setText("That cover image is not there any more.")
            return

        page = self.page_size.currentData()
        fit = self.fit_page.isChecked()
        # The panel and this dialog both offer a paper size. They are kept in
        # step - the dialog opens showing the panel's choice - and whichever the
        # person touched last is the one that prints.
        style = export_layout.HeadingStyle.from_settings(
            {**self.layout_style, "page": page})
        save_settings(
            {
                "pdf": self.want_pdf.isChecked(),
                "docx": self.want_docx.isChecked(),
                "folder": str(folder),
                "cover": "" if self.cover_baked else (cover or ""),
                "open_after": self.open_after.isChecked(),
                "page": page,
                "fit": fit,
            }
        )

        self.build_btn.setEnabled(False)
        self.progress.show()
        warnings: list[str] = []
        made: list[Path] = []

        def tick(number: int, total: int, _label: str) -> None:
            self.progress.setValue(number)
            QApplication.processEvents()

        base = clean_name(self.file_name.text())
        if not base:
            base = f"{REPORT_NAME} {stamp.strftime('%d.%m.%Y')}"
        try:
            if self.want_pdf.isChecked():
                self.status.setText("Building the PDF…")
                QApplication.processEvents()
                result = build_pdf.build(
                    self.clips, folder / f"{base}.pdf", stamp, cover, tick,
                    page=page, fit_page=fit,
                    cover_title="" if self.cover_baked else self.heading,
                    draw_cover_text=not self.cover_baked,
                    heading=style,
                )
                warnings.extend(result.warnings)
                made.append(result.path)

            if self.want_docx.isChecked():
                self.progress.setValue(0)
                self.status.setText("Building the Word document…")
                QApplication.processEvents()
                result = build_docx.build(
                    self.clips, folder / f"{base}.docx", stamp, cover, tick,
                    page=page, fit_page=fit,
                    cover_title="" if self.cover_baked else self.heading,
                    draw_cover_text=not self.cover_baked,
                    heading=style,
                    cover_blocks=self.cover_blocks,
                )
                warnings.extend(result.warnings)
                made.append(result.path)
        except Exception as exc:  # noqa: BLE001 - never show a raw traceback
            self.build_btn.setEnabled(True)
            self.progress.hide()
            QMessageBox.warning(
                self, "The newspad could not be built",
                f"{type(exc).__name__}: {exc}\n\n"
                f"Nothing was lost — your clippings are still in the list.",
            )
            return

        self.results = [str(p) for p in made]
        self.progress.hide()
        names = "\n".join(f"  {p.name}" for p in made)
        message = f"Built {len(made)} file(s) in {folder}:\n{names}"
        if warnings:
            message += f"\n\n{len(warnings)} page(s) had a problem."
        self.status.setText(message)

        if self.open_after.isChecked() and made:
            self._open(made[0])
        if warnings:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Built, with some pages skipped")
            box.setText(message)
            box.setDetailedText("\n\n".join(warnings))
            box.exec()
        self.accept()

    @staticmethod
    def _open(path: Path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:  # noqa: BLE001 - opening is a convenience, not the job
            pass
