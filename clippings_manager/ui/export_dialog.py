"""The export screen: date, formats, name, folder, then build.

Settings persist to the user's app-data folder, so tomorrow the dialog opens with
last time's output folder and formats already filled in. The cover is not chosen
here: it is the newspad's cover card's, at the top of the page.
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
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QToolButton,
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

#: How many names of their own the office may keep. Five because the box is a
#: menu and a menu of five is read at a glance; more than that and it wants
#: searching, which is a different control.
CUSTOM_NAMES = 5

#: Where the five live in export.json. One list, in slot order, with "" for a
#: slot nobody has filled - so slot 3 stays slot 3 when slot 2 is emptied.
CUSTOM_KEY = "custom_names"


def custom_names(key: str = CUSTOM_KEY) -> list:
    """The office's own names, always CUSTOM_NAMES long. ``key`` picks which
    five: the press report's, or the sentiment report's (report_builder)."""
    kept = load_settings().get(key) or []
    names = [str(one or "").strip() for one in kept][:CUSTOM_NAMES]
    return names + [""] * (CUSTOM_NAMES - len(names))


def save_custom_names(names: list, key: str = CUSTOM_KEY) -> None:
    saved = load_settings()
    saved[key] = [str(one or "").strip() for one in names][:CUSTOM_NAMES]
    save_settings(saved)


class CustomNamesDialog(QDialog):
    """The five names, to be typed in and corrected.

    Only the words are kept: the date is put on the end when one is chosen, so
    a name typed today still dates itself right tomorrow. Anything Windows
    will not have in a file name is taken out when the file is written
    (clean_name), and the box says so rather than refusing the typing.
    """

    def __init__(self, names: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("My names for the file")
        self.setModal(True)
        self.resize(520, 0)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(12)

        note = QLabel(
            "Five names of your own. Choosing one puts it in the file name box "
            "with the date on the end, so there is no need to type the date "
            "here. Leave a line empty and it is not offered.")
        note.setWordWrap(True)
        note.setObjectName("CardHint")
        outer.addWidget(note)

        self.fields: list = []
        for slot in range(CUSTOM_NAMES):
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{slot + 1}."))
            field = QLineEdit(names[slot] if slot < len(names) else "")
            field.setPlaceholderText("e.g. DAILY PRESS CLIPPINGS — DELHI DIVISION")
            field.setMaxLength(120)
            row.addWidget(field, 1)
            self.fields.append(field)
            outer.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def names(self) -> list:
        return [field.text().strip() for field in self.fields]


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


def _select_in_explorer(path: Path) -> bool:
    """Open an Explorer window on the file's folder with the file selected,
    through SHOpenFolderAndSelectItems. False when the shell cannot find the
    file or refuses, so the caller can open the folder plainly."""
    import ctypes
    from ctypes import wintypes

    try:
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        shell32.ILCreateFromPathW.restype = ctypes.c_void_p
        shell32.ILCreateFromPathW.argtypes = [wintypes.LPCWSTR]
        shell32.ILFree.argtypes = [ctypes.c_void_p]
        shell32.SHOpenFolderAndSelectItems.restype = ctypes.c_long
        shell32.SHOpenFolderAndSelectItems.argtypes = [
            ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p, wintypes.DWORD]
        ole32.CoInitializeEx.restype = ctypes.c_long
    except Exception:  # noqa: BLE001 - not Windows after all
        return False
    # The window's thread already has COM; this only balances what it adds.
    started = ole32.CoInitializeEx(None, 0x2)          # COINIT_APARTMENTTHREADED
    try:
        item = shell32.ILCreateFromPathW(str(path))
        if not item:
            return False
        try:
            return shell32.SHOpenFolderAndSelectItems(item, 0, None, 0) == 0
        finally:
            shell32.ILFree(item)
    finally:
        if started in (0, 1):                          # S_OK, S_FALSE
            ole32.CoUninitialize()


class ExportDialog(QDialog):
    """Choose what to build, then build it."""

    def __init__(self, clips: list, parent=None, prefer: str = "pdf",
                 report_date=None, cover_image=None, heading: str = "",
                 cover_baked: bool = False, layout_style: dict | None = None,
                 cover_blocks: list | None = None, name_suffix: str = "",
                 summary=None, with_cover: bool = True):
        super().__init__(parent)
        self.clips = clips
        # The day counted up (export/summary.Summary), for the optional last
        # page. None when the caller has nothing to count.
        self.summary = summary
        self.heading = heading
        # " - Newspad 2" for newspads 2 to 4, nothing for Newspad 1: two
        # newspads exported on one day must not suggest the same file name.
        self.name_suffix = name_suffix or ""
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
        # The cover card's switch. False and neither builder writes a cover
        # sheet, whatever picture the card holds.
        self.with_cover = bool(with_cover)
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
        name_row.setSpacing(7)
        # Which name the date is being put on the end of: "" is the
        # department's standing one, anything else is one of their five. Kept
        # so that changing the date re-dates the name they CHOSE, rather than
        # dropping them back on the standard one.
        self._name_base = ""
        self.file_name = QLineEdit(self._usual_name())
        self.file_name.setCursorPosition(0)
        self.file_name.setToolTip(
            "The name both files are saved under. The extension is added for "
            "you, so there is no need to type .pdf or .docx.")
        # Narrower than it was: the two buttons beside it are what the name is
        # usually set with, and a box wide enough for the whole standing name
        # left no room for them. It still scrolls to show a long name.
        self.file_name.setMinimumWidth(180)
        reset = QPushButton("Standard name")
        reset.setToolTip("Put the department's usual name back.")
        reset.clicked.connect(self._standard_name)
        self.custom_btn = QToolButton()
        # No arrow in the words: a QToolButton set to InstantPopup draws one
        # itself, and the two together read as "My names ▾ ▾".
        self.custom_btn.setText("My names")
        self.custom_btn.setCursor(Qt.PointingHandCursor)
        self.custom_btn.setToolTip(
            "Five names of your own. Choosing one puts it in the box with the "
            "date on the end.")
        self.custom_btn.setPopupMode(QToolButton.InstantPopup)
        self.custom_btn.clicked.connect(self._show_custom_menu)
        # Change the date and the suggested name follows it - unless the name
        # has been typed over, in which case it is theirs and is left alone.
        self._name_is_ours = True
        self.file_name.textEdited.connect(self._name_typed)
        self.date.dateChanged.connect(self._date_changed)
        name_row.addWidget(QLabel("File name"))
        name_row.addWidget(self.file_name, 1)
        name_row.addWidget(reset)
        name_row.addWidget(self.custom_btn)
        layout.addLayout(name_row)
        self._build_custom_menu()

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
        # The newspad's own cover card's, chosen at the top of the page, and
        # nothing else. This window had a second place to pick a cover picture;
        # the office asked for it to go (2.0.58): two places to set one thing,
        # and a picture chosen here silently replaced the card's built cover.
        self.cover_path = str(cover_image or "")
        self.cover_note = QLabel(self._cover_words())
        self.cover_note.setObjectName("SubtleHint")
        self.cover_note.setWordWrap(True)
        layout.addWidget(self.cover_note)

        # The optional last page. Off unless it was ticked last time: a
        # summary is for the days somebody asks for one.
        self.summary_box = QCheckBox("Add a coverage summary page at the end")
        self.summary_box.setToolTip(
            "One page after the clippings: how many, of what kind, from which "
            "division, in which newspapers - and the sentiment board's split "
            "when it has been used.")
        self.summary_box.setChecked(bool(saved.get("summary_page", False)))
        self.summary_box.setEnabled(summary is not None)
        layout.addWidget(self.summary_box)

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
        # The file, selected in its folder, ready to be dragged onto a mail or
        # a chat - the step after every export.
        self.show_folder = QCheckBox("Show it in its folder")
        self.show_folder.setChecked(saved.get("show_folder", True))
        buttons.addWidget(self.show_folder)
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
    def _usual_name(self) -> str:
        stamp = self.date.date().toPython()
        base = getattr(self, "_name_base", "") or REPORT_NAME
        return f"{base} {stamp.strftime('%d.%m.%Y')}{self.name_suffix}"

    def _standard_name(self) -> None:
        self._name_base = ""
        self._name_is_ours = True
        self.file_name.setText(self._usual_name())
        # Show the START of the name. The box is narrower than the standing
        # name, and setText leaves the view at the end of it, so what was on
        # screen was "…E OVER NORTHERN RAILWAYS 23.09.2026" - the tail of a
        # name nobody could see the front of.
        self.file_name.setCursorPosition(0)

    # ----------------------------------------------------- the office's five
    def _build_custom_menu(self) -> None:
        """The menu under My names. Rebuilt whenever the five change, so a name
        typed in the editor is on the menu the moment it is saved."""
        menu = QMenu(self)
        names = custom_names()
        for slot, name in enumerate(names, 1):
            if name:
                action = menu.addAction(f"{slot}.  {name}")
                action.triggered.connect(
                    lambda _checked=False, words=name: self._use_custom(words))
            else:
                action = menu.addAction(f"{slot}.  (empty)")
                action.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Edit my names…").triggered.connect(self._edit_custom)
        self.custom_btn.setMenu(menu)

    def _show_custom_menu(self) -> None:
        self.custom_btn.showMenu()

    def _use_custom(self, words: str) -> None:
        self._name_base = words
        self._name_is_ours = True      # so the date keeps following the box
        self.file_name.setText(self._usual_name())
        self.file_name.setCursorPosition(0)

    def _edit_custom(self) -> None:
        box = CustomNamesDialog(custom_names(), self)
        if box.exec() != QDialog.Accepted:
            return
        names = box.names()
        save_custom_names(names)
        self._build_custom_menu()
        # A name that was chosen and has now been retyped follows its own
        # change; one that was emptied falls back to the standing name.
        if self._name_base and self._name_base not in names:
            was = self._name_base
            self._name_base = next(
                (new for old, new in zip(custom_names(), names) if old == was and new),
                "")
            self.file_name.setText(self._usual_name())
        self._name_is_ours = True

    def _may_replace(self, folder: Path, base: str) -> bool:
        """Ask once before a build would write over files already there.

        Re-exporting the same morning under the same name is ordinary, so it is
        one click, not a refusal - but it is never silent.
        """
        from PySide6.QtWidgets import QMessageBox

        wanted = [("pdf", self.want_pdf), ("docx", self.want_docx)]
        there = [f"{base}.{ext}" for ext, box in wanted
                 if box.isChecked() and (folder / f"{base}.{ext}").exists()]
        if not there:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Replace the existing file?")
        box.setIcon(QMessageBox.Question)
        if len(there) == 1:
            box.setText(f"A file called {there[0]} already exists in {folder}.")
        else:
            box.setText(f"Files called {there[0]} and {there[1]} already exist "
                        f"in {folder}.")
        box.setInformativeText("Replace it with the newspad being built now?"
                               if len(there) == 1 else
                               "Replace them with the newspad being built now?")
        replace = box.addButton("Replace", QMessageBox.AcceptRole)
        cancel = box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        return box.clickedButton() is replace

    def _name_typed(self, _text: str) -> None:
        self._name_is_ours = False

    def _date_changed(self, *_args) -> None:
        if self._name_is_ours:
            self._standard_name()

    def _cover_words(self) -> str:
        """Which cover the files will carry - said, not offered: it is chosen
        on the cover card at the top of the page."""
        if not self.with_cover:
            return ("No cover sheet: it is switched off on the cover card at "
                    "the top of the page.")
        if self.cover_baked:
            return ("The cover is the one on the cover card at the top of the "
                    "page, with the date and the clipping count already on it.")
        if self.cover_path:
            return ("The cover is the picture chosen on the cover card at the "
                    "top of the page.")
        return ("The cover carries the count and the date. A cover picture is "
                "chosen on the cover card at the top of the page.")

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Where should the newspad go?", self.folder.text()
        )
        if folder:
            self.folder.setText(folder)

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
        cover = self.cover_path or None
        if cover and not Path(cover).exists():
            self.status.setText("The cover picture chosen on the cover card is "
                                "not there any more. Choose it again there.")
            return

        base = clean_name(self.file_name.text())
        if not base:
            base = f"{getattr(self, '_name_base', '') or REPORT_NAME} "\
                   f"{stamp.strftime('%d.%m.%Y')}{self.name_suffix}"
        # Before anything is written - the settings included - so Cancel leaves
        # everything exactly as it was.
        if not self._may_replace(folder, base):
            self.status.setText("Nothing was built. Change the name, or build "
                                "again and choose Replace.")
            return

        page = self.page_size.currentData()
        fit = self.fit_page.isChecked()
        # The panel and this dialog both offer a paper size. They are kept in
        # step - the dialog opens showing the panel's choice - and whichever the
        # person touched last is the one that prints.
        style = export_layout.HeadingStyle.from_settings(
            {**self.layout_style, "page": page})
        # Merged into what is there, not written over it. The old form wrote
        # only these seven keys, so every export silently deleted
        # "auto_duplicates" - "Check automatically" - which lives in the same
        # file. Measured: it did not survive a single export.
        # No "cover": a cover belongs to its newspad, and this file is shared
        # by all four. One an older build left here is dropped.
        kept = {key: value for key, value in load_settings().items()
                if key != "cover"}
        save_settings(
            {
                **kept,
                "pdf": self.want_pdf.isChecked(),
                "docx": self.want_docx.isChecked(),
                "folder": str(folder),
                "open_after": self.open_after.isChecked(),
                "show_folder": self.show_folder.isChecked(),
                "summary_page": self.summary_box.isChecked(),
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
                    summary=self._summary_wanted(),
                    with_cover=self.with_cover,
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
                    summary=self._summary_wanted(),
                    with_cover=self.with_cover,
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
        if self.show_folder.isChecked() and made:
            self._show_in_folder(made[0])
        if warnings:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Built, with some pages skipped")
            box.setText(message)
            box.setDetailedText("\n\n".join(warnings))
            box.exec()
        self.accept()

    def _summary_wanted(self):
        return self.summary if self.summary_box.isChecked() else None

    @staticmethod
    def _show_in_folder(path: Path) -> None:
        """The folder the file was saved into, with the file selected in it.

        Not "explorer /select,<path>" through subprocess: given a list, Python
        quotes the whole "/select,C:\\...\\PRESS MEDIA COVERAGE 12.09.2026.pdf"
        argument because the name has spaces in it, Explorer does not read a
        quoted switch, and it opens Documents instead - which is what the
        office saw, whatever folder the report had gone to. The shell's own
        call takes the path as a path, spaces, commas and all.
        """
        path = Path(path).resolve()
        try:
            if sys.platform == "win32":
                if _select_in_explorer(path):
                    return
                # The shell could not select it: the folder itself, never Documents.
                os.startfile(str(path.parent if path.parent.is_dir() else path))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path.parent)])
        except Exception:  # noqa: BLE001 - showing is a convenience, not the job
            pass

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
