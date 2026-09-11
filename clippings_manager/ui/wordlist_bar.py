"""The strip under the cover, and the list it opens.

WHERE IT IS AND WHY. Directly under the cover card, which is where the
department asked for it. A word here is a decision about the whole report rather
than about any one clipping, and the cover is the part of the screen that is
about the whole report - so it reads as belonging to what is above it.

It is a strip and not a chip that unfolds, because a folded control that is
doing something is a control nobody can see doing it. When the list holds words,
the strip says so and says how many, in its own colour. When it is empty it says
that too. Either way it can be read at a glance without being opened.

WHAT IT SAYS ABOUT WHAT IT CANNOT DO. A report is a page of PICTURES. The story
is inside the JPEG. What the program prints as text is the caption under each
clipping, the heading over a section, and the two lines on the cover - and that
is the whole of what a word list can act on. The dialog says so in as many
words, because the natural assumption is the opposite one, and somebody who
assumed it had cleaned a whole report would be wrong in a way nothing would tell
them about.

WHY EVERY RULE BELOW SETS A COLOUR AS WELL AS A BACKGROUND. The first version of
this file painted the dialog with ``theme.DARK_PANEL`` and then let the title
label take its text colour from the global sheet, which is ``theme.INK``. Those
are #1E293B and #1A1F2B: a contrast ratio of 1.13 to 1. The heading of the
dialog was, precisely, the same colour as the dialog behind it, and the first
person to open it could not read it.

Two rules came out of that and both are kept here:

*   a rule that sets ``background`` sets ``color`` in the same rule;
*   ``DARK_PANEL``, ``DARK_BAR`` and ``DARK_VIEWPORT`` belong to the preview
    window's viewport and to nothing else. Everything inside the scrolling page
    is light. ``theme.py`` says so at its own definition; this file ignored it.

THE OTHER HALF OF THAT BUG, which is subtler and was invisible rather than
unreadable. ``WordListBar`` is a *subclass* of ``QWidget``, and Qt enables
``WA_StyledBackground`` automatically only for exact ``QWidget`` instances. For a
subclass, a stylesheet's ``background``, ``border`` and ``border-radius`` are all
silently dropped - so the strip had no box at all, and the dark fill that would
have made its label unreadable simply never painted. Setting the attribute is
what makes the box appear, and it is the reason the colours below had to be put
right in the same change: fixing one without the other turns an invisible box
into an unreadable one.
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

def _not_saved(parent, error) -> None:
    """A write to the settings folder failed. Said, never swallowed: a list
    somebody believes they changed, and did not, is worse than a message."""
    QMessageBox.warning(
        parent, "Could not save",
        f"That change could not be saved ({error.strerror or error}).\n\n"
        "Nothing was changed. Try again in a moment - if it keeps happening, "
        "the settings folder may be full or locked by another program.")


STRIP = """
QWidget#WordStrip {
    background: %(back)s;
    border: 1px solid %(edge)s;
    border-radius: 10px;
}
QWidget#WordStrip > QLabel {
    color: %(text)s;
    background: transparent;
}
"""


class WordListBar(QWidget):
    """One line under the cover: what the list holds, and a way in."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WordStrip")
        # Without this the stylesheet's background, border and border-radius are
        # all dropped, because Qt sets this automatically for a plain QWidget
        # and not for a subclass. The strip drew no box at all until this line.
        self.setAttribute(Qt.WA_StyledBackground, True)

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
            # ORANGE_INK, not the brighter ORANGE: measured 5.68:1 on the warm
            # wash, where the brighter one is 1.79:1 and effectively invisible.
            self.dot.setStyleSheet(
                f"color: {theme.ORANGE_INK}; font-size: 15px;"
                " background: transparent;")
        else:
            self.words.setText(
                "No words are being kept out of the report. "
                "Anything you add here is left out when it prints.")
            self.dot.setStyleSheet(
                f"color: {theme.MUTED}; font-size: 15px;"
                " background: transparent;")
        self.setStyleSheet(STRIP % {
            "back": theme.FLAG_WASH if held else theme.PANEL,
            "edge": theme.ORANGE_INK if held else theme.HAIRLINE_STRONG,
            "text": theme.INK,
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
        self.resize(620, 580)
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
            f"QPushButton:disabled {{ color: {theme.MUTED}; }}"
        )

        column = QVBoxLayout(self)
        column.setContentsMargins(20, 18, 20, 18)
        column.setSpacing(12)

        title = QLabel("Words that will not be printed")
        title.setStyleSheet(
            f"font-size: 17px; font-weight: 600; color: {theme.INK};")
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
            f"color: {theme.SLATE_TEXT_LIGHT}; background: {theme.PANEL};"
            f" border: 1px solid {theme.HAIRLINE_STRONG};"
            f" padding: 12px 14px; border-radius: 10px; font-size: 12px;")
        column.addWidget(told)

        entry = QHBoxLayout()
        entry.setSpacing(8)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Type a word or a phrase, then press Add")
        self.entry.returnPressed.connect(self.add_word)
        self.entry.textChanged.connect(self._entry_changed)
        entry.addWidget(self.entry, 1)
        self.add_btn = QPushButton("Add")
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self.add_word)
        entry.addWidget(self.add_btn)
        column.addLayout(entry)

        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._row_changed)
        column.addWidget(self.list, 1)

        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet(
            f"color: {theme.SLATE_TEXT_LIGHT}; font-size: 11px;"
            " background: transparent;")
        column.addWidget(self.note)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.remove_btn = QPushButton("Take the chosen word off")
        self.remove_btn.setEnabled(False)
        self.remove_btn.clicked.connect(self.remove_word)
        buttons.addWidget(self.remove_btn)
        buttons.addStretch(1)
        close = QPushButton("Done")
        close.setDefault(True)
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        column.addLayout(buttons)

        self._fill()

    def _fill(self) -> None:
        held = wordlist.load()
        self.list.clear()
        for word in held:
            QListWidgetItem(word, self.list)
        self.remove_btn.setEnabled(False)
        self.note.setText(
            f"{len(held)} word{'s' if len(held) != 1 else ''} on the list. "
            "Whole words only, so a word inside a longer one is left alone - "
            "“man” does not come out of “manager”. "
            "Capital letters make no difference."
            if held else
            "The list is empty, so every report prints exactly as it does now.")

    def _entry_changed(self, text: str) -> None:
        self.add_btn.setEnabled(bool(wordlist.tidy(text)))

    def _row_changed(self, row: int) -> None:
        self.remove_btn.setEnabled(row >= 0)

    def add_word(self) -> None:
        try:
            wordlist.add(self.entry.text())
        except ValueError as error:
            QMessageBox.information(self, "Nothing to add", str(error))
            return
        except OSError as error:
            _not_saved(self, error)
            return
        self.entry.clear()
        self._fill()
        self._forget_cached()

    def remove_word(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        try:
            wordlist.remove(item.text())
        except OSError as error:
            _not_saved(self, error)
            return
        self._fill()
        self._forget_cached()

    @staticmethod
    def _forget_cached() -> None:
        """The dossier keeps a built copy; it has to be told the list moved."""
        from ..export import build_sentiment

        build_sentiment.forget_sieve()
