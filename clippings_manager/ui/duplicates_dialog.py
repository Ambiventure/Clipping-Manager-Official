"""Looking at two clippings that seem to be the same, and deciding.

The matching is good but it is not certain, and the cost of the two mistakes is
not the same. A repeat that slips through is printed twice and somebody notices.
A cutting wrongly called a repeat is dropped from the report and nobody notices
at all - which is why nothing here deletes anything until a person has seen both
pictures side by side and said so.

The headline each one was matched on is shown under its picture, because "these
two are the same" is not a claim anybody should have to take on trust: if the
match is wrong, the reason is usually visible in the two lines of text.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import theme

PICTURE = 380


def _pixmap(clip, width: int = PICTURE) -> QPixmap:
    picture = QPixmap()
    try:
        picture.loadFromData(QByteArray(clip.image_bytes or b""))
    except Exception:  # noqa: BLE001 - a picture that will not load is not fatal
        return QPixmap()
    if picture.isNull():
        return picture
    return picture.scaledToWidth(width, Qt.SmoothTransformation)


class Side(QWidget):
    """One of the two clippings, with what was read off it."""

    def __init__(self, heading: str, parent=None):
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)

        self.role = QLabel(heading)
        self.role.setStyleSheet(
            f"color: {theme.INK}; font-size: 12px; font-weight: 800;")
        column.addWidget(self.role)

        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.picture.setMinimumHeight(240)
        self.picture.setStyleSheet(
            f"background: {theme.SURFACE};"
            f" border: 1px solid {theme.HAIRLINE_STRONG}; border-radius: 8px;")
        column.addWidget(self.picture, 1)

        self.source = QLabel()
        self.source.setWordWrap(True)
        self.source.setStyleSheet(
            f"color: {theme.INK}; font-size: 11px; font-weight: 700;")
        column.addWidget(self.source)

        # The words the two were actually matched on. Without this the screen
        # only says "trust me".
        read = QLabel("read off the picture")
        read.setStyleSheet(f"color: {theme.MUTED}; font-size: 10px;"
                           " font-weight: 700; letter-spacing: 0.6px;")
        column.addWidget(read)

        self.headline = QLabel()
        self.headline.setWordWrap(True)
        self.headline.setMinimumHeight(46)
        self.headline.setAlignment(Qt.AlignTop)
        self.headline.setStyleSheet(
            f"background: {theme.SURFACE_SUNK if hasattr(theme, 'SURFACE_SUNK') else theme.SURFACE};"
            f" color: {theme.INK}; border: 1px solid {theme.HAIRLINE};"
            " border-radius: 6px; padding: 6px 8px; font-size: 12px;")
        column.addWidget(self.headline)

    def show_clip(self, clip, source: str) -> None:
        picture = _pixmap(clip)
        if picture.isNull():
            self.picture.setText("(the picture could not be shown)")
        else:
            self.picture.setPixmap(picture)
        bits = [b for b in (clip.title_text, source) if b]
        self.source.setText("  ·  ".join(bits) or "unnamed")
        self.headline.setText(clip.ocr_text or "(nothing could be read)")


class DuplicatesDialog(QDialog):
    """Step through the suspected repeats and decide on each."""

    def __init__(self, pairs, source_of, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Suspected duplicates")
        self.setModal(True)
        self.resize(980, 760)

        self.pairs = list(pairs)
        self.source_of = source_of
        self.at = 0
        # What the user decided, by the uid of the copy: True to delete it,
        # False to keep it. Nothing is acted on until the dialog is accepted.
        self.verdicts: dict = {}
        # Set by Delete All. See swept().
        self._swept = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.setSpacing(10)

        self.position = QLabel()
        self.position.setStyleSheet(
            f"color: {theme.INK}; font-size: 13px; font-weight: 800;")
        outer.addWidget(self.position)

        self.why = QLabel()
        self.why.setWordWrap(True)
        self.why.setStyleSheet(f"color: {theme.MUTED}; font-size: 11px;")
        outer.addWidget(self.why)

        body = QWidget()
        pair_row = QHBoxLayout(body)
        pair_row.setContentsMargins(0, 0, 0, 0)
        pair_row.setSpacing(16)
        self.left = Side("Keeping this one")
        self.right = Side("Suspected repeat")
        pair_row.addWidget(self.left, 1)
        pair_row.addWidget(self.right, 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self.verdict = QLabel()
        self.verdict.setStyleSheet(
            f"color: {theme.ORANGE_INK}; font-size: 11px; font-weight: 800;")
        outer.addWidget(self.verdict)

        decide = QHBoxLayout()
        self.back = QPushButton("‹ Previous")
        self.forward = QPushButton("Next ›")
        self.back.clicked.connect(lambda: self.step(-1))
        self.forward.clicked.connect(lambda: self.step(1))
        decide.addWidget(self.back)
        decide.addWidget(self.forward)
        decide.addStretch(1)

        self.keep_btn = QPushButton("Not a Duplicate")
        self.keep_btn.setToolTip(
            "Put it back in the list and in the report, and never flag it again.")
        self.drop_btn = QPushButton("Confirm Duplicate")
        self.drop_btn.setToolTip("Delete this copy when you close this window.")
        self.drop_btn.setObjectName("OrangeFilled")
        self.keep_btn.clicked.connect(lambda: self.decide(False))
        self.drop_btn.clicked.connect(lambda: self.decide(True))
        decide.addWidget(self.keep_btn)
        decide.addWidget(self.drop_btn)
        outer.addLayout(decide)

        rule = QFrame()
        rule.setFrameShape(QFrame.HLine)
        rule.setStyleSheet(f"color: {theme.HAIRLINE};")
        outer.addWidget(rule)

        finish = QHBoxLayout()
        self.sweep = QPushButton("Delete All Duplicates")
        self.sweep.setToolTip("Delete every clipping still flagged, in one go.")
        self.sweep.clicked.connect(self.delete_all)
        finish.addWidget(self.sweep)
        finish.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.done_btn = QPushButton("Done")
        self.done_btn.setObjectName("OrangeFilled")
        self.done_btn.setMinimumWidth(110)
        self.done_btn.clicked.connect(self.accept)
        finish.addWidget(cancel)
        finish.addWidget(self.done_btn)
        outer.addLayout(finish)

        self.show_pair()

    # ------------------------------------------------------------- stepping
    def show_pair(self) -> None:
        if not self.pairs:
            self.position.setText("Nothing is flagged as a duplicate.")
            for widget in (self.back, self.forward, self.keep_btn,
                           self.drop_btn, self.sweep):
                widget.setEnabled(False)
            return
        self.at = max(0, min(self.at, len(self.pairs) - 1))
        pair = self.pairs[self.at]
        self.position.setText(
            f"Duplicate {self.at + 1} of {len(self.pairs)}")
        self.why.setText(
            f"Matched on {pair.why}. The one on the left came in first, so it "
            f"is the one the report keeps.")
        self.left.show_clip(pair.primary, self.source_of(pair.primary))
        self.right.show_clip(pair.copy, self.source_of(pair.copy))
        self.back.setEnabled(self.at > 0)
        self.forward.setEnabled(self.at < len(self.pairs) - 1)
        self._say_verdict(pair)

    def _say_verdict(self, pair) -> None:
        choice = self.verdicts.get(pair.copy.uid)
        if choice is True:
            self.verdict.setText("Marked to be deleted when you press Done.")
        elif choice is False:
            self.verdict.setText("Marked as not a duplicate - it stays in.")
        else:
            self.verdict.setText(
                "Not decided. Left alone, it stays flagged and is kept out of "
                "the report.")

    def step(self, by: int) -> None:
        self.at += by
        self.show_pair()

    def decide(self, is_duplicate: bool) -> None:
        if not self.pairs:
            return
        pair = self.pairs[self.at]
        self.verdicts[pair.copy.uid] = is_duplicate
        if self.at < len(self.pairs) - 1:
            self.at += 1
        self.show_pair()

    def swept(self) -> bool:
        """Whether the lot were dealt with in one press rather than one by one.

        It matters to what the application learns from this. "Delete all" is a
        single decision about a pile; judging each pair on its own is one
        decision each. Recorded so the bulk one can be weighed at nothing -
        otherwise one impatient press would teach it more than a morning of
        careful looking.
        """
        return self._swept

    # --------------------------------------------------------------- sweep
    def delete_all(self) -> None:
        outstanding = [p for p in self.pairs
                       if self.verdicts.get(p.copy.uid) is not False]
        if not outstanding:
            QMessageBox.information(
                self, "Nothing left to delete",
                "Every flagged clipping has been marked as not a duplicate.")
            return
        answer = QMessageBox.question(
            self, "Delete all duplicates",
            f"This will delete {len(outstanding)} duplicate clipping(s) "
            f"from the list." + '\n\n' + "Ctrl+Z brings them "
            "back if you change your mind.",
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        for pair in outstanding:
            self.verdicts[pair.copy.uid] = True
        self._swept = True
        self.accept()

    # -------------------------------------------------------------- result
    def to_delete(self) -> list:
        return [p.copy for p in self.pairs if self.verdicts.get(p.copy.uid) is True]

    def to_keep(self) -> list:
        return [p.copy for p in self.pairs if self.verdicts.get(p.copy.uid) is False]
