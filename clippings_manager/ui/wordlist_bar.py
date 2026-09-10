"""The strip under the cover, and the list it opens.

WHERE IT IS AND WHY. Directly under the cover card, which is where the
department asked for it. A word here is a decision about the whole report rather
than about any one clipping, and the cover is the part of the screen that is
about the whole report - so it reads as belonging to what is above it.

It is a strip and not a chip that unfolds, because a folded control that is
doing something is a control nobody can see doing it. When the list holds
words, the strip says so and says how many, in its own colour. When it is empty
it says that too. Either way it can be read at a glance without being opened.

WHAT IT SAYS ABOUT WHAT IT CANNOT DO. A report is a page of PICTURES. The story
is inside the JPEG. What the program prints as text is the caption under each
clipping, the heading over a section, and the two lines on the cover - and that
is the whole of what a word list can act on. The dialog says so in as many
words, because the natural assumption is the opposite one, and somebody who
assumed it had cleaned a whole report would be wrong in a way nothing would
tell them about.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
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
    QWidget,
)

from ..core import wordlist
from . import theme

STRIP = """
QFrame#WordStrip, QWidget#WordStrip {
    background: %(back)s;
    border: 1px solid %(edge)s;
    border-radius: 10px;
}
"""


class WordListBar(QWidget):
    """One line under the cover: what the list holds, and a way in."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WordStrip")
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)

        self.dot = QLabel("●")
        self.dot.setFixedWidth(12)
        row.addWidget(self.dot)

        self.words = QLabel()
        self.words.setWordWrap(False)
        row.addWidget(self.words, 1)

        self.open_btn = QPushButton("Words kept out of the report…")
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.clicked.connect(self.open_editor)
        row.addWidget(self.open_btn)

        self.refresh()

    def refresh(self) -> None:
        held = wordlist.load()
        if held:
            shown = ", ".join(held[:6])
            if len(held) > 6:
                shown += f", and {len(held) - 6} more"
            self.words.setText(
                f"<b>{len(held)} word{'s' if len(held) != 1 else ''}</b> "
                f"will not be printed: {shown}")
            self.dot.setStyleSheet("color: #E8B14C; font-size: 15px;")
        else:
            self.words.setText(
                "No words are being kept out of the report. "
                "Anything you add here is left out when it prints.")
            self.dot.setStyleSheet("color: #4B5563; font-size: 15px;")
        self.setStyleSheet(STRIP % {
            "back": "rgba(184,115,10,0.10)" if held else theme.DARK_PANEL,
            "edge": "rgba(184,115,10,0.35)" if held else "rgba(255,255,255,0.08)",
        })

    def open_editor(self) -> None:
        screen = WordListDialog(self)
        screen.exec()
        self.refresh()
        self.changed.emit()


class WordListDialog(QDialog):
    """Add a word, take one off, and be told plainly what it will reach."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Words kept out of the report")
        self.resize(620, 560)
        self.setStyleSheet(f"QDialog {{ background: {theme.DARK_PANEL}; }}")

        column = QVBoxLayout(self)
        column.setContentsMargins(20, 18, 20, 18)
        column.setSpacing(12)

        title = QLabel("Words that will not be printed")
        title.setStyleSheet("font-size: 17px; font-weight: 600;")
        column.addWidget(title)

        # The honest paragraph. It is first, not last, and it is not in a
        # tooltip: somebody who adds a list of subject words and assumes the
        # report has been cleaned would be wrong, and nothing else on this
        # screen would tell them.
        told = QLabel(
            "A word on this list is taken out of the text the report prints: "
            "the caption under a clipping, the heading over a section, and the "
            "headline burned into a picture when you export one that way.\n\n"
            "It cannot reach the words inside a clipping. A clipping is a "
            "photograph of newsprint, and the story in it is part of the "
            "picture - so a word in the body of an article stays there. The "
            "address under a clipping is never touched either, because real "
            "addresses contain ordinary words and shortening one breaks the "
            "link.\n\n"
            "Nothing is changed on your clippings. Take a word off this list "
            "and it prints again.")
        told.setWordWrap(True)
        told.setStyleSheet(
            "color: #C7CBD1; background: rgba(255,255,255,0.04);"
            " border: 1px solid rgba(255,255,255,0.08);"
            " padding: 12px 14px; border-radius: 10px; font-size: 12px;")
        column.addWidget(told)

        entry = QHBoxLayout()
        entry.setSpacing(8)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Type a word or a phrase, then press Add")
        self.entry.returnPressed.connect(self.add_word)
        entry.addWidget(self.entry, 1)
        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self.add_word)
        entry.addWidget(self.add_btn)
        column.addLayout(entry)

        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        column.addWidget(self.list, 1)

        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #8A9099; font-size: 11px;")
        column.addWidget(self.note)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.remove_btn = QPushButton("Take the chosen word off")
        self.remove_btn.clicked.connect(self.remove_word)
        buttons.addWidget(self.remove_btn)
        buttons.addStretch(1)
        close = QPushButton("Done")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        column.addLayout(buttons)

        self._fill()

    def _fill(self) -> None:
        held = wordlist.load()
        self.list.clear()
        for word in held:
            QListWidgetItem(word, self.list)
        self.remove_btn.setEnabled(bool(held))
        self.note.setText(
            f"{len(held)} word{'s' if len(held) != 1 else ''} on the list. "
            "Whole words only, so a word inside a longer one is left alone - "
            "“man” does not come out of “manager”. "
            "Capital letters make no difference."
            if held else
            "The list is empty, so every report prints exactly as it does now.")

    def add_word(self) -> None:
        try:
            wordlist.add(self.entry.text())
        except ValueError as error:
            QMessageBox.information(self, "Nothing to add", str(error))
            return
        self.entry.clear()
        self._fill()
        self._forget_cached()

    def remove_word(self) -> None:
        item = self.list.currentItem()
        if item is None:
            QMessageBox.information(
                self, "Choose a word first",
                "Click the word you want to take off the list.")
            return
        wordlist.remove(item.text())
        self._fill()
        self._forget_cached()

    @staticmethod
    def _forget_cached() -> None:
        """The dossier keeps a built copy; it has to be told the list moved."""
        from ..export import build_sentiment

        build_sentiment.forget_sieve()
