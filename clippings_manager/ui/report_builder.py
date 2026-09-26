"""The sentiment board's report window: what to build, what to call it, and
where it goes. The board's one "Build report" button opens it.

The board used to carry all of this on its bottom bar - a heading, the count,
a status line, a panel of layout options and four download buttons - as tall
as a card, and with a progress sentence from somewhere else left standing in
it. The office asked for one button there and the choices in a window of their
own, the way the press report does it: the four things that can be built as
four cards to tick, the file's name with the department's usual one and five
names of their own, the folder, and the report's layout.

Nothing is built here. The window says what was chosen and the main window
builds it, with the same code the board has always used.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import icons, theme
from .export_dialog import (CustomNamesDialog, clean_name, custom_names,
                            load_settings, save_custom_names, save_settings)

#: The board's own five names, kept apart from the press report's five: a
#: dossier is one division's, and goes by other names.
NAMES_KEY = "dossier_custom_names"

#: What can be built, in the order the cards stand: key, title, what it is.
OUTPUTS = (
    ("pdf", "PDF report", "To send on, print or file"),
    ("docx", "Word report", "The same report, to edit"),
    ("burned", "Burned headlines", "Headline drawn into each picture"),
    ("jpeg", "JPEG pictures", "One picture per clipping"),
)

#: What a burned report's files and a folder of pictures add to the name, so
#: each sits apart from the plain report built beside it.
BURNED_TAIL = " (burned headlines)"
PICTURES_TAIL = " (pictures)"


class ChoiceTile(QWidget):
    """One thing that can be built, as a card ticked by pressing anywhere on it.

    Painted rather than assembled from a check box and two labels: a check box
    is a small target, and a card that is the whole target reads at a glance
    as "pick one or more of these".
    """

    toggled = Signal(bool)

    def __init__(self, key: str, title: str, blurb: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.title = title
        self.blurb = blurb
        self._on = False
        self._hover = False
        # A ring only when the keyboard brought the focus here: drawn for a
        # click too, it sat on top of the tick's own border as a second one.
        self._keyed = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMinimumSize(250, 66)
        self.setToolTip(f"{title}: {blurb}. Press to build it, again to leave it out.")

    # ------------------------------------------------------------- state
    def isChecked(self) -> bool:  # noqa: N802 - the name every Qt check uses
        return self._on

    def setChecked(self, on: bool) -> None:  # noqa: N802
        on = bool(on)
        if on == self._on:
            return
        self._on = on
        self.update()
        self.toggled.emit(on)

    # ------------------------------------------------------------- input
    def mousePressEvent(self, event):  # noqa: N802 - Qt's name
        if event.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            self.setChecked(not self._on)
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):  # noqa: N802 - Qt's name
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.setChecked(not self._on)
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event):  # noqa: N802 - Qt's name
        self._keyed = event.reason() in (Qt.TabFocusReason,
                                         Qt.BacktabFocusReason)
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):  # noqa: N802 - Qt's name
        self._keyed = False
        self.update()
        super().focusOutEvent(event)

    def enterEvent(self, event):  # noqa: N802 - Qt's name
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 - Qt's name
        self._hover = False
        self.update()
        super().leaveEvent(event)

    # ------------------------------------------------------------- paint
    def paintEvent(self, event):  # noqa: N802 - Qt's name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        card = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        if self._on:
            painter.setPen(QPen(theme.QNAVY, 2))
            painter.setBrush(QColor(theme.NAVY_SELECT))
        else:
            painter.setPen(QPen(QColor(theme.HAIRLINE_STRONG if self._hover
                                       else theme.HAIRLINE), 1.2))
            painter.setBrush(QColor(theme.SURFACE))
        painter.drawRoundedRect(card, 12, 12)
        if self.hasFocus() and self._keyed:
            painter.setPen(QPen(QColor(theme.ORANGE), 1.2, Qt.DotLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(card.adjusted(3, 3, -3, -3), 9, 9)

        # The picture of the thing, in a soft disc.
        disc = QRectF(card.left() + 12, card.center().y() - 18, 36, 36)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(theme.ORANGE_WASH if self.key in ("pdf", "burned")
                                else theme.NAVY_WASH))
        painter.drawEllipse(disc)
        mark = disc.adjusted(9, 9, -9, -9)
        colour = QColor(theme.ORANGE_INK if self.key in ("pdf", "burned")
                        else theme.NAVY)
        {"pdf": icons.file_pdf, "docx": icons.file_word,
         "burned": icons.type_letter, "jpeg": icons.image}.get(
             self.key, icons.file_text)(painter, mark, colour)

        # The words.
        left = disc.right() + 12
        right = card.right() - 36
        title_font = QFont(self.font())
        title_font.setPixelSize(13)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(theme.QINK)
        painter.drawText(QRectF(left, card.top() + 12, right - left, 20),
                         Qt.AlignLeft | Qt.AlignVCenter, self.title)
        blurb_font = QFont(self.font())
        blurb_font.setPixelSize(11)
        painter.setFont(blurb_font)
        painter.setPen(theme.QMUTED)
        painter.drawText(QRectF(left, card.top() + 32, right - left, 18),
                         Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(
                             self.blurb, Qt.ElideRight, int(right - left)))

        # The tick, top right: filled when chosen, an empty ring when not.
        ring = QRectF(card.right() - 28, card.top() + 10, 18, 18)
        if self._on:
            painter.setPen(Qt.NoPen)
            painter.setBrush(theme.QNAVY)
            painter.drawEllipse(ring)
            icons.check(painter, ring.adjusted(4, 4, -4, -4), QColor("white"), 2.2)
        else:
            painter.setPen(QPen(QColor(theme.HAIRLINE_STRONG), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(ring)
        painter.end()


class BoardReportDialog(QDialog):
    """Tick what to build, name it, say where it goes, and build."""

    def __init__(self, parent=None, *, clippings: int, where: str, stamp,
                 standard: str, suffix: str = "", choices: dict | None = None,
                 cover_on: bool = False):
        """``where`` is how the division is written ("Lucknow(LKO)"),
        ``standard`` the department's usual name for the file, date and all,
        ``choices`` the board's layout choices (see SentimentBoard
        .export_choices), and ``cover_on`` the board's cover card switch."""
        super().__init__(parent)
        self.setWindowTitle("Build the sentiment report")
        self.setModal(True)
        self.setMinimumWidth(700)
        self.setStyleSheet(theme.stylesheet())
        self.stamp = stamp
        self.suffix = suffix or ""
        self.standard = standard
        saved = load_settings()
        choices = dict(choices or {})

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        heading = QLabel(
            f"<b style='font-size:15px'>{where}</b>"
            f"<span style='color:{theme.MUTED}; font-size:13px'>"
            f"  ·  {clippings} clipping{'s' if clippings != 1 else ''} ready"
            f"</span>")
        layout.addWidget(heading)
        note = QLabel("Choose what to build — one, or several at once. "
                      "Everything is built from the board, in the order its "
                      "columns show.")
        note.setWordWrap(True)
        note.setObjectName("CardHint")
        layout.addWidget(note)

        # --- what to build ------------------------------------------------
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        wanted = set(saved.get("dossier_outputs") or ["pdf"])
        self.tiles: dict = {}
        for n, (key, title, blurb) in enumerate(OUTPUTS):
            tile = ChoiceTile(key, title, blurb, self)
            tile.setChecked(key in wanted)
            tile.toggled.connect(self._outputs_changed)
            self.tiles[key] = tile
            grid.addWidget(tile, n // 2, n % 2)
        layout.addLayout(grid)

        # The burned report is wanted as a PDF to send AND a Word file to
        # edit, usually both - so it says which, under its card.
        self.burned_row = QWidget()
        burned = QHBoxLayout(self.burned_row)
        burned.setContentsMargins(4, 0, 0, 0)
        burned.setSpacing(14)
        burned.addWidget(QLabel("Burned headlines as"))
        self.burned_pdf = QCheckBox("PDF")
        self.burned_docx = QCheckBox("Word")
        self.burned_pdf.setChecked(saved.get("burned_pdf", True))
        self.burned_docx.setChecked(saved.get("burned_docx", True))
        burned.addWidget(self.burned_pdf)
        burned.addWidget(self.burned_docx)
        burned.addStretch(1)
        layout.addWidget(self.burned_row)

        # --- name ----------------------------------------------------------
        # The department's usual name, or one of their five with the date on
        # the end - the press report's own arrangement, with a separate five.
        self._name_base = ""
        self._name_is_ours = True
        name_row = QHBoxLayout()
        name_row.setSpacing(7)
        self.file_name = QLineEdit(self._usual_name())
        self.file_name.setCursorPosition(0)
        self.file_name.setMinimumWidth(200)
        self.file_name.setToolTip(
            "The name the report is saved under. The extension is added for "
            "you; a burned report adds “(burned headlines)”, and "
            "the pictures go into a folder of their own.")
        self.file_name.textEdited.connect(self._name_typed)
        standard_btn = QPushButton("Standard name")
        standard_btn.setToolTip("Put the department's usual name back.")
        standard_btn.clicked.connect(self._standard_name)
        self.names_btn = QToolButton()
        self.names_btn.setText("My names")
        self.names_btn.setCursor(Qt.PointingHandCursor)
        self.names_btn.setToolTip(
            "Five names of your own for this report. Choosing one puts it in "
            "the box with the date on the end.")
        self.names_btn.setPopupMode(QToolButton.InstantPopup)
        name_row.addWidget(QLabel("File name"))
        name_row.addWidget(self.file_name, 1)
        name_row.addWidget(standard_btn)
        name_row.addWidget(self.names_btn)
        layout.addLayout(name_row)
        self._build_names_menu()

        # --- folder --------------------------------------------------------
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit(
            saved.get("dossier_folder") or saved.get("folder")
            or str(Path.home() / "Documents"))
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._pick_folder)
        folder_row.addWidget(QLabel("Save into"))
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse)
        layout.addLayout(folder_row)

        # --- layout --------------------------------------------------------
        # What was the board's "Report layout options" panel.
        rule = QFrame()
        rule.setFrameShape(QFrame.HLine)
        rule.setStyleSheet(f"color: {theme.HAIRLINE};")
        layout.addWidget(rule)
        caption = QLabel("REPORT LAYOUT")
        caption.setStyleSheet(
            f"color: {theme.ORANGE}; font-size: 10px; font-weight: 800;"
            f" letter-spacing: .06em;")
        layout.addWidget(caption)
        boxes = QHBoxLayout()
        boxes.setSpacing(16)
        self.option_boxes: dict = {}
        for key, title, blurb in (
                ("banner", "Division header banner",
                 "A navy NORTHERN RAILWAY | CODE strip on every page"),
                ("headings", "Sentiment section titles",
                 "A heading before each category"),
                ("titles", "Headline above each picture",
                 "Prints the headline typed on each card above its picture")):
            box = QCheckBox(title)
            box.setToolTip(blurb)
            box.setChecked(bool(choices.get(key, key != "banner")))
            self.option_boxes[key] = box
            boxes.addWidget(box)
        boxes.addStretch(1)
        layout.addLayout(boxes)
        overrides = QHBoxLayout()
        overrides.setSpacing(9)
        self.custom_heading = QLineEdit(str(choices.get("custom_heading") or ""))
        self.custom_heading.setPlaceholderText("Division heading (optional)")
        self.custom_title = QLineEdit(str(choices.get("custom_title") or ""))
        self.custom_title.setPlaceholderText("Report title (optional)")
        overrides.addWidget(self.custom_heading)
        overrides.addWidget(self.custom_title)
        layout.addLayout(overrides)
        cover = QLabel(
            "Cover page: " + ("on" if cover_on else "off") + " — switched "
            "on the board's cover card, where it is designed.")
        cover.setObjectName("SubtleHint")
        layout.addWidget(cover)

        self.warn = QLabel()
        self.warn.setWordWrap(True)
        self.warn.setStyleSheet(f"color: {theme.ORANGE_INK}; font-weight: 700;")
        self.warn.hide()
        layout.addWidget(self.warn)

        # --- go ------------------------------------------------------------
        buttons = QHBoxLayout()
        self.open_after = QCheckBox("Open when finished")
        self.open_after.setChecked(saved.get("dossier_open_after", True))
        self.show_folder = QCheckBox("Show it in its folder")
        self.show_folder.setChecked(saved.get("dossier_show_folder", True))
        buttons.addWidget(self.open_after)
        buttons.addWidget(self.show_folder)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        self.build_btn = QPushButton("Build")
        self.build_btn.setObjectName("OrangeFilled")
        self.build_btn.setMinimumWidth(120)
        self.build_btn.setCursor(Qt.PointingHandCursor)
        self.build_btn.setDefault(True)
        self.build_btn.clicked.connect(self._accept_if_sound)
        buttons.addWidget(cancel)
        buttons.addWidget(self.build_btn)
        layout.addLayout(buttons)

        self._outputs_changed()

    # ------------------------------------------------------------- names
    def _usual_name(self) -> str:
        if not self._name_base:
            return self.standard
        return f"{self._name_base} {self.stamp.strftime('%d.%m.%Y')}{self.suffix}"

    def _standard_name(self) -> None:
        self._name_base = ""
        self._name_is_ours = True
        self.file_name.setText(self._usual_name())
        self.file_name.setCursorPosition(0)

    def _name_typed(self, _text: str) -> None:
        self._name_is_ours = False

    def _build_names_menu(self) -> None:
        """The menu under My names; rebuilt when the five change."""
        menu = QMenu(self)
        for slot, name in enumerate(custom_names(NAMES_KEY), 1):
            if name:
                action = menu.addAction(f"{slot}.  {name}")
                action.triggered.connect(
                    lambda _checked=False, words=name: self._use_name(words))
            else:
                action = menu.addAction(f"{slot}.  (empty)")
                action.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Edit my names…").triggered.connect(self._edit_names)
        self.names_btn.setMenu(menu)

    def _use_name(self, words: str) -> None:
        self._name_base = words
        self._name_is_ours = True
        self.file_name.setText(self._usual_name())
        self.file_name.setCursorPosition(0)

    def _edit_names(self) -> None:
        box = CustomNamesDialog(custom_names(NAMES_KEY), self)
        box.setWindowTitle("My names for the sentiment report")
        if box.exec() != QDialog.Accepted:
            return
        names = box.names()
        save_custom_names(names, NAMES_KEY)
        self._build_names_menu()
        if self._name_base and self._name_base not in names:
            self._name_base = ""
            self.file_name.setText(self._usual_name())
        self._name_is_ours = True

    # ------------------------------------------------------------ choosing
    def _outputs_changed(self, *_args) -> None:
        self.burned_row.setVisible(self.tiles["burned"].isChecked())
        self.build_btn.setEnabled(bool(self.outputs()))
        self.warn.hide()

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Where should the report go?", self.folder_edit.text())
        if folder:
            self.folder_edit.setText(folder)

    def outputs(self) -> list:
        """What was ticked, in the order the cards stand."""
        return [key for key, _t, _b in OUTPUTS if self.tiles[key].isChecked()]

    def burned_formats(self) -> list:
        return [fmt for fmt, box in (("pdf", self.burned_pdf),
                                     ("docx", self.burned_docx))
                if box.isChecked()]

    def base(self) -> str:
        return clean_name(self.file_name.text())

    def folder(self) -> Path:
        return Path(self.folder_edit.text().strip() or ".")

    def targets(self, kind: str) -> list:
        """(format, path) for one kind of report, in the order they build."""
        folder, base = self.folder(), self.base()
        if kind == "pdf":
            return [("pdf", folder / f"{base}.pdf")]
        if kind == "docx":
            return [("docx", folder / f"{base}.docx")]
        if kind == "burned":
            return [(fmt, folder / f"{base}{BURNED_TAIL}.{fmt}")
                    for fmt in self.burned_formats()]
        return []

    def pictures_folder(self, usual: str) -> Path:
        """Where the JPEGs go: under the usual folder name while the report
        has its usual name - the name the office already files them under -
        and under the report's own name once it has been given another."""
        standard = clean_name(self.standard)
        name = usual if self.base() == standard else f"{self.base()}{PICTURES_TAIL}"
        return self.folder() / name

    def choices(self) -> dict:
        """The layout, as SentimentBoard.set_export_choices takes it."""
        out = {key: box.isChecked() for key, box in self.option_boxes.items()}
        out["custom_heading"] = self.custom_heading.text()
        out["custom_title"] = self.custom_title.text()
        return out

    def opens_after(self) -> bool:
        return self.open_after.isChecked()

    def shows_folder(self) -> bool:
        return self.show_folder.isChecked()

    def _say(self, words: str) -> None:
        self.warn.setText(words)
        self.warn.show()

    def _accept_if_sound(self) -> None:
        """Everything a Save box would have checked, since there isn't one."""
        chosen = self.outputs()
        if not chosen:
            self._say("Tick at least one thing to build.")
            return
        if "burned" in chosen and not self.burned_formats():
            self._say("Say whether the burned headlines report is a PDF, a "
                      "Word file, or both.")
            return
        if not self.base():
            self._say("Give the report a name — or press Standard name.")
            self.file_name.setFocus()
            return
        folder = self.folder()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - a bad path is a normal mistake
            self._say(f"That folder cannot be written to "
                      f"({type(exc).__name__}). Choose another one.")
            return
        # A Save box asks before it writes over a file; nothing else here would.
        already = [path for kind in chosen for _fmt, path in self.targets(kind)
                   if path.exists()]
        if already:
            names = "\n".join(f"  {path.name}" for path in already)
            answer = QMessageBox.question(
                self, "Replace what is already there?",
                f"This will write over:\n{names}\n\nGo ahead?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        saved = load_settings()
        saved.update({
            "dossier_outputs": chosen,
            "dossier_folder": str(folder),
            "dossier_open_after": self.open_after.isChecked(),
            "dossier_show_folder": self.show_folder.isChecked(),
            "burned_pdf": self.burned_pdf.isChecked(),
            "burned_docx": self.burned_docx.isChecked(),
        })
        save_settings(saved)
        self.accept()
