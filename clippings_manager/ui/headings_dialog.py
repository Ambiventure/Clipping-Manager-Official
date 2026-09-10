"""Adding and removing the section headings on offer.

WHY THIS EXISTS AT ALL. Headings used to be added by typing into the picker in
the preview window. That picker was an editable combo wired to a signal which
fires on every keystroke, and every keystroke was written to disk as a heading.
Typing seven letters saved seven headings; deleting the placeholder saved nine
more. There was no confirmation step because there was no step - the saving
happened while a person was still deciding what to type.

So adding is its own act now, in its own dialog, and it happens when somebody
presses Add. The picker beside it only chooses.

THE COLOURS ARE LIGHT, and that is deliberate rather than incidental. The first
version of the neighbouring word-list dialog painted itself with
``theme.DARK_PANEL`` and then let its title label take the global ``theme.INK``
for text. Those two are #1E293B and #1A1F2B - a contrast ratio of 1.13 to 1, so
the heading of the dialog was, precisely, the same colour as the dialog. Every
rule here that sets a background sets a colour in the same rule, and the only
dark surface in this program is the preview viewport.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..core import sections as section_list
from . import theme


class HeadingsDialog(QDialog):
    """The list of headings, with a way in and a way out."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.changed = False
        self.setWindowTitle("Section headings")
        self.resize(560, 540)
        self.setStyleSheet(
            f"QDialog {{ background: {theme.CANVAS}; color: {theme.INK}; }}"
            f"QLabel {{ color: {theme.INK}; background: transparent; }}"
            f"QLineEdit {{ background: {theme.SURFACE}; color: {theme.INK};"
            f" border: 1px solid {theme.HAIRLINE_STRONG}; border-radius: 8px;"
            f" padding: 8px 10px; }}"
            f"QLineEdit:focus {{ border-color: {theme.NAVY}; }}"
            f"QListWidget {{ background: {theme.SURFACE}; color: {theme.INK};"
            f" border: 1px solid {theme.HAIRLINE_STRONG}; border-radius: 8px;"
            f" outline: none; }}"
            f"QListWidget::item {{ padding: 7px 9px; color: {theme.INK}; }}"
            f"QListWidget::item:selected {{ background: {theme.NAVY_SELECT};"
            f" color: {theme.NAVY}; }}"
            f"QPushButton {{ background: {theme.SURFACE}; color: {theme.INK};"
            f" border: 1px solid {theme.HAIRLINE_STRONG}; border-radius: 8px;"
            f" padding: 8px 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ border-color: {theme.NAVY}; }}"
            f"QPushButton:disabled {{ color: {theme.MUTED};"
            f" border-color: {theme.HAIRLINE_STRONG}; }}"
        )

        column = QVBoxLayout(self)
        column.setContentsMargins(20, 18, 20, 18)
        column.setSpacing(12)

        title = QLabel("Section headings")
        title.setStyleSheet(
            f"font-size: 17px; font-weight: 600; color: {theme.INK};")
        column.addWidget(title)

        told = QLabel(
            "A heading prints in one line above the first clipping of its run, "
            "once per report. Choose which clipping carries it in the box "
            "beside the picker.\n\n"
            "Taking a heading off this list does not remove it from a clipping "
            "that already carries it, and does not stop it printing.")
        told.setWordWrap(True)
        told.setStyleSheet(
            f"color: {theme.SLATE_TEXT_LIGHT}; background: {theme.PANEL};"
            f" border: 1px solid {theme.HAIRLINE_STRONG};"
            f" padding: 11px 13px; border-radius: 9px; font-size: 12px;")
        column.addWidget(told)

        entry = QHBoxLayout()
        entry.setSpacing(8)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Type a heading, then press Add")
        # Nothing is saved while this is being typed. Add is the moment.
        self.entry.returnPressed.connect(self.add_heading)
        self.entry.textChanged.connect(self._entry_changed)
        entry.addWidget(self.entry, 1)
        self.add_btn = QPushButton("Add")
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self.add_heading)
        entry.addWidget(self.add_btn)
        column.addLayout(entry)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._row_changed)
        column.addWidget(self.list, 1)

        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet(
            f"color: {theme.SLATE_TEXT_LIGHT}; font-size: 11px;"
            f" background: transparent;")
        column.addWidget(self.note)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.remove_btn = QPushButton("Take the chosen heading off")
        self.remove_btn.setEnabled(False)
        self.remove_btn.clicked.connect(self.remove_heading)
        buttons.addWidget(self.remove_btn)
        self.reset_btn = QPushButton("Put the standard three back")
        self.reset_btn.clicked.connect(self.reset_headings)
        buttons.addWidget(self.reset_btn)
        buttons.addStretch(1)
        done = QPushButton("Done")
        done.setDefault(True)
        done.setCursor(Qt.PointingHandCursor)
        done.clicked.connect(self.accept)
        buttons.addWidget(done)
        column.addLayout(buttons)

        self._fill()

    # ----------------------------------------------------------------- state
    def _fill(self) -> None:
        known = section_list.load()
        self.list.clear()
        for row in known.rows:
            item = QListWidgetItem(row["words"], self.list)
            item.setData(Qt.UserRole, row["key"])
        self.remove_btn.setEnabled(False)
        self.note.setText(
            f"{len(known.rows)} heading"
            f"{'s' if len(known.rows) != 1 else ''} on the list. "
            "Printed in capitals, in one line, at "
            f"{known.size:g}pt.")

    def _entry_changed(self, text: str) -> None:
        self.add_btn.setEnabled(bool(section_list.tidy(text)))

    def _row_changed(self, row: int) -> None:
        self.remove_btn.setEnabled(row >= 0)

    # ---------------------------------------------------------------- actions
    def add_heading(self) -> None:
        try:
            section_list.add(self.entry.text())
        except ValueError as error:
            QMessageBox.information(self, "That is not a heading", str(error))
            return
        self.entry.clear()
        self.changed = True
        self._fill()

    def remove_heading(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        words = item.text()
        asked = QMessageBox.question(
            self, "Take this heading off?",
            f"“{words}” will no longer be offered in the picker.\n\n"
            "Any clipping already carrying it keeps it and still prints it. A "
            "report never quietly loses a heading somebody chose.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if asked != QMessageBox.Yes:
            return
        section_list.remove(item.data(Qt.UserRole))
        self.changed = True
        self._fill()

    def reset_headings(self) -> None:
        asked = QMessageBox.question(
            self, "Put the standard headings back?",
            "The list goes back to Electronic Media, Social Media and Digital "
            "Media, and the size and colour go back to what was shipped.\n\n"
            "Anything you have added here is forgotten. Clippings keep the "
            "headings they carry.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if asked != QMessageBox.Yes:
            return
        section_list.forget()
        self.changed = True
        self._fill()
