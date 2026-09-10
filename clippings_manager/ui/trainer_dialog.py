"""Teaching the machine what this department calls a repeat.

One question at a time: two cuttings side by side, and two answers. Not because
the application is going to work out a rule from them - measured over three
mornings and twenty-three thousand labelled pairs, there is no rule there to
find; the two populations are interleaved on every measurement it takes - but
because what somebody decides here is EVIDENCE, and it is the only evidence in
existence about the papers this department actually reads.

What that evidence is for is stated plainly on the screen and again in
:mod:`core.training`: it goes into a file, the file can be sent, and a later
release sets its constants against it - ten real mornings instead of three, by
a person, in a build anybody can audit. Nothing the trainer collects moves a
number in the copy running on somebody's desk.

**Which pairs it asks about matters more than the screen.** A morning is ten
thousand pairs and perhaps seven are repeats. Fifty asked at random is fifty
"no" answers and a sitting nobody finishes; fifty chosen by which of the rule's
gates the pair falls at holds about a dozen. See :func:`core.training.candidates`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QProgressBar, QPushButton,
                               QVBoxLayout, QWidget)

from ..core import training
from . import theme
from .duplicates_dialog import Side
from .fluid import ElidedLabel, FlowLayout

#: What each kind of question is called on screen. The person judging should be
#: told why they are being shown this pair - it is the difference between a
#: question and a guessing game.
WHY = {
    training.FLAGGED: "The program already calls these a repeat",
    training.WORD_EDGE: "Their headlines nearly match, but not quite enough",
    training.PICTURE_EDGE: "The words match, the pictures do not",
    training.BLIND: "The pictures match, but a headline could not be read",
    training.NEAR: "Close on the finer print, with nothing else to go on",
    training.FIELD: "Picked from the rest, so the record is not all near-misses",
}


def _chip(text: str, tip: str = "") -> QPushButton:
    button = QPushButton(text)
    button.setCursor(Qt.PointingHandCursor)
    if tip:
        button.setToolTip(tip)
    button.setStyleSheet(
        f"QPushButton {{ background: {theme.SURFACE}; color: {theme.NAVY};"
        f" border: 1px solid {theme.HAIRLINE_STRONG};"
        " border-radius: 11px; padding: 5px 13px;"
        " font-size: 11px; font-weight: 700; }"
        f"QPushButton:hover {{ background: {theme.NAVY_WASH};"
        f" border-color: {theme.NAVY}; }}"
        f"QPushButton:disabled {{ color: {theme.MUTED};"
        f" border-color: {theme.HAIRLINE}; }}")
    return button


class TrainerDialog(QDialog):
    """Step through chosen pairs and say, of each, whether it is a repeat."""

    def __init__(self, clips, pairs, source_of, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Duplicates Trainer")
        self.setModal(True)
        self.resize(1180, 760)
        self._source_of = source_of
        self._done: list = []          # what was answered, so it can be undone

        # Every pair is named by its pictures, so a clipping with no print
        # cannot be asked about at all. The window measures them before opening
        # this, but the screen does not depend on its caller having done so -
        # opened on an unmeasured list it would simply come up empty, which
        # looks exactly like "there is nothing to do" and is not.
        if any(c.image_bytes and not c.picture_hash for c in clips):
            try:
                from ..core import duplicates

                duplicates._ensure_prints(clips)
            except Exception:  # noqa: BLE001 - never let this stop the screen
                pass

        self.queue = training.candidates(clips, pairs, wanted=50)
        self.at = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 15, 18, 14)
        outer.setSpacing(10)

        head = QLabel("Duplicates Trainer")
        head.setStyleSheet(
            f"color: {theme.INK}; font-size: 16px; font-weight: 800;")
        outer.addWidget(head)

        self.why = ElidedLabel("", floor=160)
        self.why.setStyleSheet(
            f"color: {theme.ORANGE_INK}; font-size: 11px; font-weight: 800;"
            " letter-spacing: .04em;")
        outer.addWidget(self.why)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        self.bar.setStyleSheet(
            f"QProgressBar {{ background: {theme.HAIRLINE}; border: none;"
            " border-radius: 3px; }"
            f"QProgressBar::chunk {{ background: {theme.ORANGE};"
            " border-radius: 3px; }}")
        outer.addWidget(self.bar)

        middle = QHBoxLayout()
        middle.setSpacing(16)
        self.left = Side("This one")
        self.right = Side("and this one")
        middle.addWidget(self.left, 1)
        middle.addWidget(self.right, 1)
        outer.addLayout(middle, 1)

        self.numbers = QLabel()
        self.numbers.setStyleSheet(
            f"color: {theme.SLATE_TEXT_LIGHT}; font-size: 11px;")
        outer.addWidget(self.numbers)

        # ------------------------------------------------------- the answers
        answers = QHBoxLayout()
        answers.setSpacing(10)
        self.same_btn = QPushButton("Same cutting  (Y)")
        self.same_btn.setCursor(Qt.PointingHandCursor)
        self.same_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.NAVY}; color: #FFFFFF;"
            f" border: 1px solid {theme.NAVY}; border-radius: 12px;"
            " padding: 9px 22px; font-size: 13px; font-weight: 800; }}")
        self.same_btn.clicked.connect(lambda: self.decide(True))
        answers.addWidget(self.same_btn)

        self.apart_btn = QPushButton("Different  (N)")
        self.apart_btn.setCursor(Qt.PointingHandCursor)
        self.apart_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE}; color: {theme.INK};"
            f" border: 1px solid {theme.HAIRLINE_STRONG};"
            " border-radius: 12px; padding: 9px 22px;"
            " font-size: 13px; font-weight: 800; }"
            f"QPushButton:hover {{ border-color: {theme.NAVY}; }}")
        self.apart_btn.clicked.connect(lambda: self.decide(False))
        answers.addWidget(self.apart_btn)

        self.skip_btn = _chip("Not sure — skip  (S)",
                              "Leave it unanswered. A guess is worse than "
                              "nothing here: it goes into the record as if "
                              "somebody knew.")
        self.skip_btn.clicked.connect(self.skip)
        answers.addWidget(self.skip_btn)

        self.undo_btn = _chip("Undo the last one  (Ctrl+Z)")
        self.undo_btn.clicked.connect(self.undo)
        self.undo_btn.setEnabled(False)
        answers.addWidget(self.undo_btn)
        answers.addStretch(1)
        outer.addLayout(answers)

        # ---------------------------------------------------------- the foot
        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.learned = ElidedLabel("", floor=150)
        self.learned.setStyleSheet(
            f"color: {theme.SLATE_TEXT_LIGHT}; font-size: 11px;")
        foot.addWidget(self.learned, 1)

        tail = FlowLayout(spacing=8, vertical_spacing=6)
        self.send_btn = _chip("Save to a file…",
                              "Write everything judged here to one file, to "
                              "keep, to move to another PC, or to send back so "
                              "a later version can be set against it.")
        self.send_btn.clicked.connect(self.export)
        tail.addWidget(self.send_btn)
        self.take_btn = _chip("Load from a file…",
                              "Merge in judgements from another copy. Nothing "
                              "is overwritten, and anything the two disagree "
                              "about is put back in front of you.")
        self.take_btn.clicked.connect(self.do_import)
        tail.addWidget(self.take_btn)
        done = _chip("Done")
        done.clicked.connect(self.accept)
        tail.addWidget(done)
        foot.addLayout(tail)
        outer.addLayout(foot)

        for keys, what in (("Y", lambda: self.decide(True)),
                           ("D", lambda: self.decide(True)),
                           ("N", lambda: self.decide(False)),
                           ("S", self.skip),
                           ("Ctrl+Z", self.undo)):
            QShortcut(QKeySequence(keys), self, what)

        self.show_pair()

    # ----------------------------------------------------------------- state
    def _pair(self):
        if 0 <= self.at < len(self.queue):
            return self.queue[self.at]
        return None

    def show_pair(self) -> None:
        found = self._pair()
        self.bar.setMaximum(max(1, len(self.queue)))
        self.bar.setValue(self.at)
        self._say_learned()
        if found is None:
            self.why.setText("Nothing left to look at.")
            self.numbers.setText("")
            for button in (self.same_btn, self.apart_btn, self.skip_btn):
                button.setEnabled(False)
            self.left.picture.setText("")
            self.right.picture.setText("")
            self.left.source.setText("")
            self.right.source.setText("")
            self.left.headline.setText("")
            self.right.headline.setText("")
            return
        first, second, kind, seen = found
        for button in (self.same_btn, self.apart_btn, self.skip_btn):
            button.setEnabled(True)
        self.why.setText(f"{self.at + 1} of {len(self.queue)}   ·   "
                         f"{WHY.get(kind, kind)}")
        self.left.show_clip(first, self._source_of(first))
        self.right.show_clip(second, self._source_of(second))
        self.numbers.setText(
            f"pictures {seen.get('whole', -1)} apart of 64   ·   "
            f"below the masthead {seen.get('lower', -1)}   ·   "
            f"finer print {seen.get('fine', -1)} of 256   ·   "
            f"headlines {seen.get('tsr', 0):.0f} / {seen.get('ratio', 0):.0f}")

    def _say_learned(self) -> None:
        said = training.summary()
        if not said["rows"]:
            self.learned.setText(
                "Nothing recorded yet. What you decide here is kept, and can "
                "be saved to a file.")
            return
        bits = [f"{said['pairs']} pair(s) judged",
                f"{said['duplicates']} the same",
                f"{said['separate']} different"]
        if said["disputed"]:
            bits.append(f"{said['disputed']} disagreed about")
        if said["origins"] > 1:
            bits.append(f"from {said['origins']} copies")
        self.learned.setText(
            "  ·  ".join(bits)
            + ".  This is kept as evidence — it does not change the check by "
              "itself.")

    # --------------------------------------------------------------- answers
    def decide(self, same: bool) -> None:
        found = self._pair()
        if found is None:
            return
        first, second, kind, seen = found
        if training.record(first, second, same, kind, seen):
            self._done.append(self.at)
            self.undo_btn.setEnabled(True)
        self.at += 1
        self.show_pair()

    def skip(self) -> None:
        """Move on without writing anything down.

        Deliberately not a third verdict. A guess recorded here is worse than
        no answer at all: a year later nobody can tell it from one somebody was
        sure of, and there is no way to find out.
        """
        if self._pair() is None:
            return
        self.at += 1
        self.show_pair()

    def undo(self) -> None:
        """Take back the last answer. Somebody will press the wrong one."""
        if not self._done:
            return
        where = self._done.pop()
        found = self.queue[where] if 0 <= where < len(self.queue) else None
        if found is not None:
            training.forget_pair(training.pair_name(found[0], found[1]))
        self.at = where
        self.undo_btn.setEnabled(bool(self._done))
        self.show_pair()

    # ------------------------------------------------------------- the files
    def export(self) -> None:
        from datetime import date

        from .export_dialog import keeping_folder

        stamp = date.today().strftime("%Y%m%d")
        suggested = keeping_folder() / (
            f"ClippingsManager-training-{training.origin()}-{stamp}.json")
        where, _picked = QFileDialog.getSaveFileName(
            self, "Save what has been taught", str(suggested),
            "Training file (*.json)")
        if not where:
            return
        try:
            said = training.export_to(where)
        except Exception as error:  # noqa: BLE001
            QMessageBox.warning(self, "It could not be saved", str(error))
            return
        QMessageBox.information(
            self, "Saved",
            f"{said['rows']} judgement(s) about {said['pairs']} pair(s) "
            f"written to:\n\n{where}\n\nKeep this file. Loading it into a "
            f"later version puts everything decided here back, and sending it "
            f"back is how the next version gets set against real mornings."
            f"\n\nYou do not need it to update the program - what you have "
            f"taught it is kept outside the program's own folder and an update "
            f"leaves it alone.")

    def do_import(self) -> None:
        from .export_dialog import keeping_folder

        where, _picked = QFileDialog.getOpenFileName(
            self, "Load what was taught elsewhere", str(keeping_folder()),
            "Training file (*.json)")
        if not where:
            return
        looked = training.inspect(where)
        if not looked.get("ok"):
            QMessageBox.warning(self, "That file cannot be used",
                                looked.get("why", "It could not be read."))
            return
        lines = [f"That file holds {looked['rows']} judgement(s).",
                 f"{looked['already']} you already have.",
                 f"{looked['new']} are new."]
        if looked["disagree"]:
            lines.append(
                f"{looked['disagree']} disagree with judgements already made — "
                f"those will be put back in front of you rather than decided "
                f"here.")
        asked = QMessageBox(self)
        asked.setIcon(QMessageBox.Question)
        asked.setWindowTitle("Load these judgements?")
        asked.setText("\n".join(lines))
        asked.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        asked.setDefaultButton(QMessageBox.Yes)
        if asked.exec() != QMessageBox.Yes:
            return
        got = training.import_from(where)
        QMessageBox.information(self, "Loaded",
                                f"{got.get('added', 0)} judgement(s) added.")
        self._say_learned()
