"""Where the burned-headline report goes, and in which formats.

The board's other three buttons each build one thing, so the plain Save box
Windows provides is enough for them. This one is different. It is the report the
department forwards on, and it is wanted as a PDF to send *and* as a Word file
to edit afterwards - usually both, from the same click, carrying the same name
so the pair sits together in a folder.

A Save box cannot do that: it offers one file, one name, one extension. So this
asks once - name, folder, formats - and the caller builds every format that was
ticked from a single burn, which is also the slow part and worth doing once.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from . import theme
from .export_dialog import (FORBIDDEN, clean_name,  # noqa: F401
                            load_settings, save_settings)


class BurnedReportDialog(QDialog):
    """Name it, say where it goes, and tick the formats wanted."""

    def __init__(self, parent=None, suggested: str = "Report",
                 clippings: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Report with burned headlines")
        self.setModal(True)
        self.setMinimumWidth(560)

        saved = load_settings()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(11)

        blurb = QLabel(
            f"Each of the {clippings} clipping(s) is drawn as one picture with "
            f"its headline and address printed into it, so the words travel "
            f"with the image. Both files are built from the same pictures."
            if clippings else
            "Each clipping is drawn as one picture with its headline and "
            "address printed into it, so the words travel with the image."
        )
        blurb.setObjectName("CardHint")
        blurb.setWordWrap(True)
        layout.addWidget(blurb)

        # --- name ----------------------------------------------------------
        name_row = QHBoxLayout()
        self.name = QLineEdit(suggested)
        self.name.setToolTip(
            "The name both files take. The extension is added for you."
        )
        self.name.selectAll()
        name_row.addWidget(QLabel("File name"))
        name_row.addWidget(self.name, 1)
        layout.addLayout(name_row)

        # --- folder --------------------------------------------------------
        folder_row = QHBoxLayout()
        self.folder = QLineEdit(
            saved.get("burned_folder")
            or saved.get("folder")
            or str(Path.home() / "Documents")
        )
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._pick_folder)
        folder_row.addWidget(QLabel("Save into"))
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)
        layout.addLayout(folder_row)

        rule = QFrame()
        rule.setFrameShape(QFrame.HLine)
        rule.setStyleSheet(f"color: {theme.HAIRLINE};")
        layout.addWidget(rule)

        # --- formats -------------------------------------------------------
        # Both on by default, because both is what the ask was: one to send and
        # one to edit, out of a single click.
        self.want_pdf = QCheckBox("PDF  (to send on)")
        self.want_docx = QCheckBox("Word (.docx)  — for editing afterwards")
        self.want_pdf.setChecked(saved.get("burned_pdf", True))
        self.want_docx.setChecked(saved.get("burned_docx", True))
        layout.addWidget(self.want_pdf)
        layout.addWidget(self.want_docx)

        self.warn = QLabel()
        self.warn.setObjectName("CardHint")
        self.warn.setWordWrap(True)
        self.warn.setStyleSheet(f"color: {theme.ORANGE_INK}; font-weight: 700;")
        self.warn.hide()
        layout.addWidget(self.warn)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.open_after = QCheckBox("Open when finished")
        self.open_after.setChecked(saved.get("burned_open_after", True))
        buttons.addWidget(self.open_after)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.export_btn = QPushButton("Export")
        self.export_btn.setObjectName("OrangeFilled")
        self.export_btn.setMinimumWidth(120)
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self._accept_if_sound)
        buttons.addWidget(cancel)
        buttons.addWidget(self.export_btn)
        layout.addLayout(buttons)

    # ------------------------------------------------------------- choosing
    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Where should the report go?", self.folder.text()
        )
        if folder:
            self.folder.setText(folder)

    def targets(self) -> list[tuple[str, Path]]:
        """(format, path) for every format ticked, in the order they build."""
        folder = Path(self.folder.text().strip() or ".")
        base = clean_name(self.name.text()) or "Report"
        wanted = []
        if self.want_pdf.isChecked():
            wanted.append(("pdf", folder / f"{base}.pdf"))
        if self.want_docx.isChecked():
            wanted.append(("docx", folder / f"{base}.docx"))
        return wanted

    def opens_after(self) -> bool:
        return self.open_after.isChecked()

    def _accept_if_sound(self) -> None:
        """Everything a Save box would have checked, since there isn't one."""
        if not (self.want_pdf.isChecked() or self.want_docx.isChecked()):
            self.warn.setText("Tick at least one format to export.")
            self.warn.show()
            return

        if not clean_name(self.name.text()):
            self.warn.setText("Give the file a name.")
            self.warn.show()
            return

        folder = Path(self.folder.text().strip() or ".")
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - a bad path is a normal mistake
            self.warn.setText(
                f"That folder cannot be written to ({type(exc).__name__}). "
                f"Choose another one."
            )
            self.warn.show()
            return

        # A Save box asks before it overwrites; nothing else here would.
        already = [path for _kind, path in self.targets() if path.exists()]
        if already:
            names = "\n".join(f"  {p.name}" for p in already)
            answer = QMessageBox.question(
                self, "Replace what is already there?",
                f"This will overwrite:\n{names}\n\nGo ahead?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        saved = load_settings()
        saved.update({
            "burned_folder": str(folder),
            "burned_pdf": self.want_pdf.isChecked(),
            "burned_docx": self.want_docx.isChecked(),
            "burned_open_after": self.open_after.isChecked(),
        })
        save_settings(saved)
        self.accept()

    @staticmethod
    def open_file(path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:  # noqa: BLE001 - opening is a convenience, not the job
            pass
