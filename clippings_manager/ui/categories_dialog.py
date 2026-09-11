"""Saying which papers are regional, which are Hindi, which are the big ones.

The list the application ships with is a starting point and nothing more. It was
put together from what the department's own reports actually contain, and a
third of it could not be confirmed at all - small city sheets that leave no trace
anywhere, and which the person compiling the newspad every morning knows better
than any list ever will. So the list is theirs to correct, and the corrections
are kept: they live in the app-data folder as a record of what was changed, so
an update can add new papers without undoing any of it.

The papers this morning actually contains are shown first, with their counts.
That is the difference between a settings screen somebody has to hunt through
and one where the row they want is already at the top.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from ..core import arrange, backup, categories
from . import theme
from .fluid import ElidedLabel, FlowLayout, ShrinkingCombo
from .scroll import CardScroll

def _not_saved(parent, error) -> None:
    """A write to the settings folder failed. Said, never swallowed: a list
    somebody believes they changed, and did not, is worse than a message."""
    QMessageBox.warning(
        parent, "Could not save",
        f"That change could not be saved ({error.strerror or error}).\n\n"
        "Nothing was changed. Try again in a moment - if it keeps happening, "
        "the settings folder may be full or locked by another program.")



class PaperRow(QWidget):
    """One publication, and a drop-down for each axis."""

    def __init__(self, name: str, book, count: int, screen, parent=None):
        super().__init__(parent)
        self.name = name
        self._screen = screen
        self._quiet = True
        paper = book.paper(name)

        box = QHBoxLayout(self)
        box.setContentsMargins(10, 6, 10, 6)
        box.setSpacing(8)

        said = f"{name}" + (f"   · {count} today" if count else "")
        label = ElidedLabel(said, floor=110)
        label.setStyleSheet(
            f"color: {theme.INK}; font-size: 12px; font-weight: 700;"
            " background: transparent; border: none;")
        if paper is not None and paper.get("note"):
            label.setToolTip(paper["note"])
        box.addWidget(label, 1)

        checked = (paper or {}).get("checked", "")
        if checked in ("unsure", "yours"):
            flag = QLabel("not confirmed" if checked == "unsure" else "yours")
            flag.setStyleSheet(
                f"color: {theme.ORANGE_INK}; font-size: 10px; font-weight: 800;"
                f" background: {theme.ORANGE_WASH};"
                f" border: 1px solid {theme.ORANGE_DEEP}; border-radius: 8px;"
                " padding: 1px 7px;")
            flag.setToolTip(
                "Nobody could confirm this paper, so its categories are a "
                "guess. Yours will be better." if checked == "unsure"
                else "A paper you added yourself.")
            box.addWidget(flag)

        self.picks = {}
        for key, axis in book.axes.items():
            pick = ShrinkingCombo(floor=104)
            for value in axis.values:
                pick.addItem(value, value)
            here = (paper or {}).get(key, "")
            if here:
                pick.setCurrentIndex(max(0, pick.findData(here)))
            pick.setToolTip(f"{axis.label} — {axis.help}")
            pick.currentIndexChanged.connect(
                lambda _index, k=key, p=pick: self._chose(k, p))
            self.picks[key] = pick
            box.addWidget(pick)

        drop = QPushButton("Remove")
        drop.setObjectName("Quiet")
        drop.setCursor(Qt.PointingHandCursor)
        drop.setToolTip(f"Take {name} out of the list altogether. It stays out "
                        "when the program is updated.")
        drop.clicked.connect(lambda: screen.drop_paper(name))
        box.addWidget(drop)
        self._quiet = False

    def _chose(self, axis: str, pick) -> None:
        if self._quiet:
            return
        try:
            categories.set_value(self.name, axis, pick.currentData())
        except OSError as error:
            _not_saved(self, error)
            return
        self._screen.touched()


class CategoriesDialog(QDialog):
    """The whole list, this morning's papers first."""

    def __init__(self, clips=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Which papers are which")
        self.setModal(True)
        self.resize(940, 620)
        self._clips = list(clips or [])
        self._changed = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(10)

        head = QLabel("Which papers are which")
        head.setStyleSheet(
            f"color: {theme.INK}; font-size: 15px; font-weight: 800;")
        outer.addWidget(head)

        why = ElidedLabel(
            "These decide what the Filter and arrange strip can do. Change any "
            "of them - what is set here is kept when the program is updated.",
            floor=140)
        why.setStyleSheet(f"color: {theme.SLATE_TEXT_LIGHT}; font-size: 11px;")
        outer.addWidget(why)

        self.inner = QWidget()
        self.rows = QVBoxLayout(self.inner)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(4)
        # Its own scrolling surface, so the drop-downs inside it hand the wheel
        # to this list rather than changing themselves under the pointer.
        self.scroll = CardScroll("CategoriesScroll", self.inner)
        outer.addWidget(self.scroll, 1)

        # --------------------------------------------------------- adding
        add = QHBoxLayout()
        add.setSpacing(8)
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText("A paper that is not on the list…")
        self.new_name.returnPressed.connect(self.add_paper)
        add.addWidget(self.new_name, 1)
        self.new_picks = {}
        book = categories.load()
        for key, axis in book.axes.items():
            pick = ShrinkingCombo(floor=104)
            for value in axis.values:
                pick.addItem(value, value)
            pick.setToolTip(axis.label)
            self.new_picks[key] = pick
            add.addWidget(pick)
        made = QPushButton("Add")
        made.setCursor(Qt.PointingHandCursor)
        made.clicked.connect(self.add_paper)
        add.addWidget(made)
        outer.addLayout(add)

        # --------------------------------------------------------- the feet
        feet = FlowLayout(spacing=8, vertical_spacing=6)
        # One file for the lot, not one per feature. Somebody who wants their
        # setup on a second machine wants THEIR SETUP, not a category file and
        # a trainer file and whatever the next thing adds. See core/backup.
        self.save_btn = QPushButton("Save my setup to a file…")
        self.save_btn.setObjectName("Quiet")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setToolTip(
            "Write everything this copy has been set up with to one file - "
            "this list, what the trainer has been taught, the cover and "
            "heading settings, and where exports go."
            + "\n\n"
            + "You do NOT need this to update the program: an update leaves "
            "all of it alone. This is for moving to another PC, handing your "
            "setup to somebody else, or keeping a copy somewhere safe.")
        self.save_btn.clicked.connect(self.save_setup)
        feet.addWidget(self.save_btn)

        self.load_btn = QPushButton("Put a saved setup back…")
        self.load_btn.setObjectName("Quiet")
        self.load_btn.setCursor(Qt.PointingHandCursor)
        self.load_btn.setToolTip(
            "Read a setup file back in. It tells you what it will replace "
            "before it does anything, and never touches the clippings you are "
            "working on.")
        self.load_btn.clicked.connect(self.load_setup)
        feet.addWidget(self.load_btn)

        self.keep_btn = QPushButton("Keep a copy in…")
        self.keep_btn.setObjectName("Quiet")
        self.keep_btn.setCursor(Qt.PointingHandCursor)
        self.keep_btn.setToolTip(
            "Write a fresh copy of your setup into a folder every time you "
            "close the program."
            + "\n\n"
            + "Point it at your Google Drive or OneDrive folder and the copy "
            "is in your account without the program ever going online - the "
            "sync program you already have carries it. That is why there is no "
            "sign-in here: nothing to log into, nothing to leak, and it still "
            "works on a morning with no internet.")
        self.keep_btn.clicked.connect(self.choose_kept_folder)
        feet.addWidget(self.keep_btn)

        self.reset_btn = QPushButton("Back to the shipped list")
        self.reset_btn.setObjectName("Quiet")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.setToolTip(
            "Throw away every change made here and start again from the list "
            "the program came with.")
        self.reset_btn.clicked.connect(self.reset_all)
        feet.addWidget(self.reset_btn)
        done = QPushButton("Done")
        done.setCursor(Qt.PointingHandCursor)
        done.setDefault(True)
        done.clicked.connect(self.accept)
        feet.addWidget(done)
        line = QHBoxLayout()
        self.note = ElidedLabel("", floor=140)
        self.note.setStyleSheet(
            f"color: {theme.SLATE_TEXT_LIGHT}; font-size: 11px;")
        line.addWidget(self.note, 1)
        line.addLayout(feet)
        outer.addLayout(line)

        self._fill()

    # ---------------------------------------------------------------- filling
    def _fill(self) -> None:
        while self.rows.count():
            item = self.rows.takeAt(0)
            gone = item.widget() if item is not None else None
            if gone is not None:
                gone.setParent(None)
                gone.deleteLater()

        book = categories.load()
        counts = arrange.tally(self._clips, arrange.BY_NAME, book)
        # Resolved through the book, so a clipping labelled "Jagran" counts
        # towards Dainik Jagran rather than towards nothing.
        tally: dict = {}
        for name, count in counts.items():
            paper = book.paper(name)
            if paper is not None:
                tally[paper["name"]] = tally.get(paper["name"], 0) + count

        here = sorted((n for n in book.names if tally.get(n)),
                      key=lambda n: (-tally.get(n, 0), n.casefold()))
        rest = [n for n in book.names if not tally.get(n)]

        if here:
            self.rows.addWidget(self._heading(
                f"In this morning's clippings ({len(here)})"))
            for name in here:
                self.rows.addWidget(PaperRow(name, book, tally.get(name, 0), self))
        unsure = [n for n in rest if (book.paper(n) or {}).get("checked") == "unsure"]
        known = [n for n in rest if n not in set(unsure)]
        if unsure:
            self.rows.addWidget(self._heading(
                f"Nobody could confirm these ({len(unsure)}) — worth a look"))
            for name in unsure:
                self.rows.addWidget(PaperRow(name, book, 0, self))
        if known:
            self.rows.addWidget(self._heading(f"Everything else ({len(known)})"))
            for name in known:
                self.rows.addWidget(PaperRow(name, book, 0, self))
        self.rows.addStretch(1)
        self._say()

    def _heading(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {theme.ORANGE_INK}; font-size: 11px; font-weight: 900;"
            " letter-spacing: .06em; padding: 10px 2px 2px 2px;")
        return label

    def _say(self) -> None:
        self.note.setText("Your own corrections are being kept."
                          if categories.edited()
                          else "Nothing changed yet — this is the list the "
                               "program ships with.")
        self.reset_btn.setEnabled(categories.edited())

    # ---------------------------------------------------------------- actions
    def touched(self) -> None:
        self._changed = True
        self._say()

    def add_paper(self) -> None:
        name = self.new_name.text().strip()
        if not name:
            return
        try:
            categories.add_paper(
                name, {key: pick.currentData()
                       for key, pick in self.new_picks.items()})
        except OSError as error:
            _not_saved(self, error)
            return
        self.new_name.clear()
        self._changed = True
        self._fill()

    def drop_paper(self, name: str) -> None:
        asked = QMessageBox(self)
        asked.setIcon(QMessageBox.Question)
        asked.setWindowTitle("Remove this paper?")
        asked.setText(f"Take {name} out of the list?")
        asked.setInformativeText(
            "Clippings from it will still be in the report — it just stops "
            "having a category, so it will show up under “Not known”.")
        asked.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        asked.setDefaultButton(QMessageBox.Cancel)
        if asked.exec() != QMessageBox.Yes:
            return
        try:
            categories.remove_paper(name)
        except OSError as error:
            _not_saved(self, error)
            return
        self._changed = True
        self._fill()

    # ------------------------------------------------------ the whole setup
    #
    # The work is in ui/backup_actions, not here, because the crown needs these
    # too - and the crown is the only place that is ALWAYS on screen. This
    # editor is opened from the Filter and arrange strip, which lives on the
    # select bar, which hides itself when there are no clippings. Somebody
    # restoring a setup onto a fresh machine has no clippings by definition.

    def save_setup(self) -> None:
        from .backup_actions import save_setup

        save_setup(self)

    def load_setup(self) -> None:
        from .backup_actions import load_setup

        if load_setup(self):
            categories.load()
            self._changed = True
            self._fill()

    def choose_kept_folder(self) -> None:
        from .backup_actions import choose_kept_folder

        choose_kept_folder(self)

    def reset_all(self) -> None:
        asked = QMessageBox(self)
        asked.setIcon(QMessageBox.Warning)
        asked.setWindowTitle("Start again?")
        asked.setText("Throw away every change made here?")
        asked.setInformativeText(
            "The list goes back to the one the program came with. Nothing else "
            "is affected.")
        asked.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        asked.setDefaultButton(QMessageBox.Cancel)
        if asked.exec() != QMessageBox.Yes:
            return
        try:
            categories.forget()
        except OSError as error:
            _not_saved(self, error)
            return
        self._changed = True
        self._fill()
