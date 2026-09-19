"""Manage Newspaper List: the newspapers and cities Collect knows in a caption.

Opened from the right-click menu on Collect from WhatsApp. Collect names a
photo from its caption only when the caption starts with a newspaper on this
list, and what follows has to be a city - on the list, or a known town - so
this is where a paper from any state is added, a spelling people use is
taught (Hindi, Punjabi, any script, or short, like DJ), and a name that prints
wrongly is corrected.

EVERYTHING COLLECT ALREADY READS IS HERE when it opens: every newspaper and
city on the program's own list, with the changes kept from before. The short
forms the reader knows by itself (DJ, HT, NBT...) are shown on their papers
and found by the search. Names typed into a clipping this session are read
until the program closes; they are offered with one button rather than saved
without anybody seeing them, because a typing slip saved for good would be
read as a newspaper every morning after.

One search bar at the top looks through both lists at once.

What is saved here is kept for good and is the same for every newspad; see
core/paperlist.py for how, and why only the changes are written down.

Opened with open(), never exec(): nothing waits on it, and while it is up
Collect holds copies in order, as it does for any box.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTableWidget, QTableWidgetItem,
                               QTabWidget, QVBoxLayout, QWidget)

from ..core import copied, paperlist
from ..core.paperlist import Entry
from . import theme

NAME, SPELLINGS, WHOSE = range(3)

#: On the name cell: the reader's own short forms for the row, for the search.
SHORT_ROLE = Qt.UserRole + 1

WORDS = {
    "newspapers": {"one": "newspaper", "many": "newspapers", "title": "Newspapers",
                   "column": "Newspaper - as it prints",
                   "example": "e.g. Rajasthan Patrika, Lokmat, The Hindu",
                   "spellings": "e.g. राजस्थान पत्रिका, Patrika"},
    "cities": {"one": "city", "many": "cities", "title": "Cities",
               "column": "City - as it prints",
               "example": "e.g. Latur, Bhilwara",
               "spellings": "e.g. लातूर"},
}

WHOSE_SAID = {"added": "Added", "changed": "Changed", "": ""}

#: How many typed names the offer lists before "and N more".
OFFER_NAMES = 6


def short_forms() -> dict:
    """Newspaper -> the short forms the reader knows for it by itself."""
    found: dict = {}
    for short, name in getattr(copied, "SHORTHAND", {}).items():
        found.setdefault(name, []).append(short.upper())
    return found


class ListTable(QWidget):
    """One list - the newspapers or the cities - to look through and change."""

    changed = Signal()
    #: Asked for before a new row is added: the search must not hide it.
    wants_everything = Signal()

    def __init__(self, kind: str, base: list, entries: list, typed=(),
                 shorthand: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.base = base
        self.words = WORDS[kind]
        self.shorthand = shorthand or {}
        self._filling = False
        self._needle = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.setSpacing(8)

        # Names typed into a clipping this session: read until the program
        # closes, and offered here so that keeping them is one press.
        self.offer = QFrame()
        self.offer.setObjectName("TypedOffer")
        self.offer.setStyleSheet(
            f"#TypedOffer {{ background: {theme.NAVY_WASH}; border: 1px solid "
            f"{theme.HAIRLINE}; border-radius: 8px; }}")
        offer_row = QHBoxLayout(self.offer)
        offer_row.setContentsMargins(12, 8, 8, 8)
        self.offer_text = QLabel()
        self.offer_text.setWordWrap(True)
        offer_row.addWidget(self.offer_text, 1)
        self.offer_btn = QPushButton("Add them to the list")
        self.offer_btn.setCursor(Qt.PointingHandCursor)
        self.offer_btn.clicked.connect(self.take_typed)
        offer_row.addWidget(self.offer_btn)
        outer.addWidget(self.offer)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            [self.words["column"], "Other spellings - commas between", ""])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked
                                   | QAbstractItemView.EditKeyPressed
                                   | QAbstractItemView.AnyKeyPressed)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(NAME, QHeaderView.Interactive)
        header.setSectionResizeMode(SPELLINGS, QHeaderView.Stretch)
        header.setSectionResizeMode(WHOSE, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(NAME, 240)
        self.table.itemChanged.connect(self._edited)
        outer.addWidget(self.table, 1)

        row = QHBoxLayout()
        self.add_btn = QPushButton(f"Add a {self.words['one']}")
        self.add_btn.setToolTip(
            f"A new row at the end: the {self.words['one']} as it should print "
            f"({self.words['example']}), then how else it is typed "
            f"({self.words['spellings']}).")
        self.add_btn.clicked.connect(self.add)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setToolTip(f"Take the selected {self.words['many']} off the list.")
        self.remove_btn.clicked.connect(self.remove)
        for button in (self.add_btn, self.remove_btn):
            button.setCursor(Qt.PointingHandCursor)
            row.addWidget(button)
        row.addStretch(1)
        self.count = QLabel()
        self.count.setStyleSheet(f"color: {theme.MUTED};")
        row.addWidget(self.count)
        outer.addLayout(row)

        self.typed = [name for name in typed if isinstance(name, str) and name.strip()]
        self.fill(entries)

    # ---------------------------------------------------------------- rows
    def fill(self, entries: list) -> None:
        self._filling = True
        try:
            self.table.setRowCount(0)
            for entry in entries:
                self._add_row(entry)
        finally:
            self._filling = False
        self._filter()
        self._recount()

    def _add_row(self, entry: Optional[Entry]) -> int:
        at = self.table.rowCount()
        self.table.insertRow(at)
        name = QTableWidgetItem(entry.name if entry else "")
        name.setData(Qt.UserRole, entry)
        spellings = QTableWidgetItem(paperlist.spellings_text(entry.aliases) if entry else "")
        short = self.shorthand.get(entry.name, []) if entry else []
        if short:
            # Read by the reader itself, not from this list: shown and found,
            # never written - so it cannot be taken off here by mistake.
            name.setData(SHORT_ROLE, " ".join(short))
            spellings.setToolTip(f"Collect also reads {', '.join(short)} for "
                                 f"{entry.name}, by itself.")
        whose = QTableWidgetItem("")
        whose.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        whose.setForeground(QColor(theme.MUTED))
        self.table.setItem(at, NAME, name)
        self.table.setItem(at, SPELLINGS, spellings)
        self.table.setItem(at, WHOSE, whose)
        self._mark(at)
        return at

    def entry_at(self, row: int) -> Optional[Entry]:
        """The row as an entry, or None for a row left blank. A row nobody
        edited is the very entry it was filled from, so saving an untouched
        list writes no change."""
        name_item, spell_item = self.table.item(row, NAME), self.table.item(row, SPELLINGS)
        if name_item is None or spell_item is None:
            return None
        original = name_item.data(Qt.UserRole)
        name_text, spell_text = name_item.text(), spell_item.text()
        same_spellings = (original is not None
                          and spell_text == paperlist.spellings_text(original.aliases))
        if original is not None and same_spellings and name_text == original.name:
            return original
        name = paperlist.clean_name(name_text)
        if not name and not paperlist.split_spellings(spell_text):
            return None
        aliases = (original.aliases if same_spellings
                   else paperlist.clean_aliases(spell_text, name))
        return Entry(name, tuple(aliases), original.was if original is not None else "")

    def entries(self) -> list:
        found = (self.entry_at(row) for row in range(self.table.rowCount()))
        return [entry for entry in found if entry is not None]

    def _mark(self, row: int) -> None:
        entry = self.entry_at(row)
        said = WHOSE_SAID[paperlist.whose(self.base, entry)] if entry is not None else ""
        item = self.table.item(row, WHOSE)
        if item is not None and item.text() != said:
            was = self.table.blockSignals(True)
            item.setText(said)
            self.table.blockSignals(was)

    def _edited(self, item) -> None:
        if self._filling or item.column() == WHOSE:
            return
        self._mark(item.row())
        self._recount()
        self.changed.emit()

    # ------------------------------------------------------------- actions
    def add(self) -> int:
        """A new blank row at the end, ready to type its name into."""
        self.wants_everything.emit()
        self._filling = True
        try:
            at = self._add_row(None)
        finally:
            self._filling = False
        self.table.scrollToItem(self.table.item(at, NAME))
        self.table.setCurrentCell(at, NAME)
        self.table.editItem(self.table.item(at, NAME))
        self._recount()
        self.changed.emit()
        return at

    def remove(self) -> int:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
        if rows:
            self._recount()
            self.changed.emit()
        return len(rows)

    def not_listed(self) -> list:
        """The names typed this session that the list does not have."""
        listed = {paperlist.clean_name(entry.name).casefold() for entry in self.entries()}
        return [name for name in self.typed
                if paperlist.clean_name(name).casefold() not in listed]

    def take_typed(self) -> int:
        """Put the names typed this session onto the list, to be saved with it."""
        names = self.not_listed()
        if not names:
            return 0
        self.wants_everything.emit()
        self._filling = True
        try:
            for name in names:
                self._add_row(Entry(paperlist.clean_name(name), (), ""))
        finally:
            self._filling = False
        self.table.scrollToBottom()
        self._recount()
        self.changed.emit()
        return len(names)

    # -------------------------------------------------------------- search
    def set_filter(self, text: str) -> None:
        self._needle = paperlist.clean_name(text).casefold()
        self._filter()

    def _filter(self) -> None:
        for row in range(self.table.rowCount()):
            name = self.table.item(row, NAME)
            words = " ".join(
                [self.table.item(row, column).text() for column in (NAME, SPELLINGS)
                 if self.table.item(row, column) is not None]
                + [str(name.data(SHORT_ROLE) or "") if name is not None else ""]).casefold()
            self.table.setRowHidden(row, bool(self._needle) and self._needle not in words)

    def shown(self) -> int:
        """How many rows the search leaves showing."""
        return sum(1 for row in range(self.table.rowCount())
                   if not self.table.isRowHidden(row))

    def _recount(self) -> None:
        entries = self.entries()
        marks = [paperlist.whose(self.base, entry) for entry in entries]
        said = [f"{len(entries)} {self.words['many']}"]
        if marks.count("added"):
            said.append(f"{marks.count('added')} added")
        if marks.count("changed"):
            said.append(f"{marks.count('changed')} changed")
        removed = len(paperlist.changes_between(self.base, entries)["removed"])
        if removed:
            said.append(f"{removed} taken off")
        self.count.setText(" · ".join(said))
        waiting = self.not_listed()
        if waiting:
            names = ", ".join(waiting[:OFFER_NAMES])
            more = f" and {len(waiting) - OFFER_NAMES} more" if len(waiting) > OFFER_NAMES else ""
            self.offer_text.setText(
                f"Typed into clippings this session, and read until the program "
                f"closes - not on the list yet: {names}{more}.")
        self.offer.setVisible(bool(waiting))


class NewspaperListDialog(QDialog):
    """The two lists, to look through, add to and correct; kept for good."""

    def __init__(self, window, parent=None):
        super().__init__(parent or window)
        self.window = window
        self.setWindowTitle("Newspaper List")
        self.setModal(True)
        self.resize(820, 620)
        self._dirty = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 14)
        outer.setSpacing(10)
        title = QLabel("The newspapers Collect from WhatsApp knows")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {theme.NAVY};")
        outer.addWidget(title)

        # One search, at the top, through both lists.
        self.search = QLineEdit()
        self.search.setObjectName("ListSearch")
        self.search.setPlaceholderText(
            "Search newspapers and cities - a name, a spelling, or a short form like DJ")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(34)
        self.search.textChanged.connect(self._search)
        outer.addWidget(self.search)

        lead = QLabel(
            "Every newspaper and city Collect already reads is here. A caption is "
            "read when it starts with a newspaper on this list; the name is what "
            "prints above the clipping, and other spellings are how people type it "
            "- Hindi, Punjabi, any language, or short. Add papers from any state, "
            "and under Cities any town a caption names that is not read yet. Kept "
            "on this computer for every newspad, after the program is closed.")
        lead.setWordWrap(True)
        lead.setStyleSheet(f"color: {theme.MUTED};")
        outer.addWidget(lead)

        index = getattr(window, "name_index", None)
        typed = {
            "newspapers": index.typed_newspapers() if hasattr(index, "typed_newspapers") else [],
            "cities": index.typed_editions() if hasattr(index, "typed_editions") else [],
        }
        changes = paperlist.load_changes()
        self.tabs = QTabWidget()
        self.lists: dict[str, ListTable] = {}
        for kind in paperlist.KINDS:
            base = paperlist.shipped(kind)
            table = ListTable(kind, base,
                              paperlist.alphabetical(paperlist.merged(base, changes[kind])),
                              typed[kind],
                              short_forms() if kind == "newspapers" else None)
            table.changed.connect(self._touched)
            table.wants_everything.connect(self.search.clear)
            self.lists[kind] = table
            self.tabs.addTab(table, "")
        self._retitle()
        outer.addWidget(self.tabs, 1)

        buttons = QHBoxLayout()
        self.original_btn = QPushButton("Put the lists back as they came")
        self.original_btn.setToolTip(
            "Takes off every newspaper and city added here and undoes every "
            "change. Nothing is saved until you press Save.")
        self.original_btn.clicked.connect(self.put_back)
        buttons.addWidget(self.original_btn)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("NavyFilled")
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self.save)
        for button in (self.original_btn, cancel, self.save_btn):
            button.setCursor(Qt.PointingHandCursor)
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_btn)
        outer.addLayout(buttons)
        self.search.setFocus()

    def _touched(self) -> None:
        self._dirty = True
        self._retitle()

    def _search(self, text: str) -> None:
        for table in self.lists.values():
            table.set_filter(text)
        self._retitle()
        # Found only on the other list: show that one, rather than an empty table.
        current = self.tabs.currentWidget()
        if text.strip() and isinstance(current, ListTable) and not current.shown():
            for at, table in enumerate(self.lists.values()):
                if table.shown():
                    self.tabs.setCurrentIndex(at)
                    break

    def _retitle(self) -> None:
        searching = bool(self.search.text().strip())
        for at, (kind, table) in enumerate(self.lists.items()):
            total = len(table.entries())
            said = f"{table.shown()} of {total}" if searching else f"{total}"
            self.tabs.setTabText(at, f"{WORDS[kind]['title']} ({said})")

    def put_back(self) -> None:
        asked = QMessageBox.question(
            self, "Put the lists back as they came?",
            "Every newspaper and city added here is taken off, and every change "
            "is undone. Nothing is saved until you press Save.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if asked != QMessageBox.Yes:
            return
        for table in self.lists.values():
            table.fill(paperlist.alphabetical(table.base))
        self._touched()

    def save(self) -> bool:
        """Check, write, and put the lists to use straight away."""
        gathered = {kind: table.entries() for kind, table in self.lists.items()}
        said = []
        for kind, entries in gathered.items():
            said += paperlist.problems(
                kind, self.lists[kind].base, entries,
                copied.SHORTHAND if kind == "newspapers" else None)
        if said:
            more = f"\n\n…and {len(said) - 6} more." if len(said) > 6 else ""
            QMessageBox.warning(self, "Not saved yet",
                                "\n\n".join(said[:6]) + more)
            return False
        changes = {kind: paperlist.changes_between(self.lists[kind].base, entries)
                   for kind, entries in gathered.items()}
        try:
            paperlist.save(changes)
        except OSError as error:
            QMessageBox.warning(self, "Not saved",
                                f"The list could not be written ({error}).")
            return False
        counts = paperlist.apply(self.window.name_index)
        try:
            self.window._flash(
                f"Newspaper list saved: {counts.get('newspapers', 0)} newspapers, "
                f"{counts.get('cities', 0)} cities.", "info")
        except Exception:  # noqa: BLE001 - saved either way
            pass
        self._dirty = False
        self.accept()
        return True

    def reject(self) -> None:
        if self._dirty:
            asked = QMessageBox.question(
                self, "Close without saving?",
                "Your changes to the list have not been saved.",
                QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
            if asked != QMessageBox.Yes:
                return
        super().reject()
