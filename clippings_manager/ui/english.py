"""The summary shown after every card's Hindi was put into English.

One line per card, in the order they sit in the list: the Hindi as it was, the
English it became, and a note where a name was spelt out by rule and wants a
look. A change made to twenty cards at once should be readable afterwards,
not just done.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QVBoxLayout)

from . import theme


def show_summary(parent, lines: list, said: str, title: str = "Put in English",
                 foot: str = "") -> QDialog:
    box = QDialog(parent)
    box.setWindowTitle(title)
    box.setModal(False)
    box.resize(720, 460)
    outer = QVBoxLayout(box)
    outer.setContentsMargins(18, 16, 18, 14)
    outer.setSpacing(10)
    head = QLabel(said)
    head.setWordWrap(True)
    head.setStyleSheet("font-weight: 700;")
    outer.addWidget(head)
    words = QPlainTextEdit()
    words.setReadOnly(True)
    words.setPlainText("\n".join(lines) if lines else "Nothing to do.")
    words.setStyleSheet(f"font-size: 13px; color: {theme.INK};")
    outer.addWidget(words, 1)
    note = QLabel(foot or (
        "A name marked \u201cspelt out by rule\u201d is not on the "
        "newspaper list: check it on the card, or add the paper to the "
        "list to have it read exactly every time."))
    note.setWordWrap(True)
    note.setStyleSheet(f"color: {theme.MUTED};")
    outer.addWidget(note)
    box.words = words
    row = QHBoxLayout()
    row.addStretch(1)
    close = QPushButton("Close")
    close.setCursor(Qt.PointingHandCursor)
    close.clicked.connect(box.close)
    row.addWidget(close)
    outer.addLayout(row)
    box.show()
    return box
