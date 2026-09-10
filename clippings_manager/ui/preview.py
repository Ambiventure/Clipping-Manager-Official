"""Full-size preview of one clipping, with the actions you want while looking at it.

Opened by clicking a thumbnail. Deciding whether to keep a clipping means reading it,
and reading it means seeing it large, so the actions live here rather than forcing a
trip back to the list: zoom, rotate, split, exclude, delete, and the fields.

Left and right arrows walk the whole list without closing, which is how a division
gets checked quickly.
"""

from __future__ import annotations

import io

from PySide6.QtCore import QSize, QStringListModel, Qt, Signal
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QCompleter,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core import sections as section_list
from ..core.models import Section
from . import theme
from .fluid import ElidedLabel
from .scroll import WHEEL_PIXELS, smooth

ZOOM_STEPS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0]

DARK_BUTTON = """
QPushButton {
    background: #1E293B; border: 1px solid #33415A; border-radius: 9px;
    padding: 7px 12px; color: #E2E8F0; font-size: 12px; font-weight: 600;
}
QPushButton:hover { background: #2A3A55; border-color: #4A5B78; color: #FFFFFF; }
QPushButton:disabled { color: #55627A; border-color: #2A3346; }
"""

DANGER_BUTTON = """
QPushButton {
    background: rgba(127,29,29,0.35); border: 1px solid rgba(153,27,27,0.7);
    border-radius: 9px; padding: 7px 12px; color: #FCA5A5; font-size: 12px;
    font-weight: 600;
}
QPushButton:hover { background: rgba(153,27,27,0.6); color: #FEE2E2; }
"""


class PreviewDialog(QDialog):
    """One clipping, big, with actions."""

    excludeRequested = Signal(int, bool)
    deleteRequested = Signal(int)
    rotateRequested = Signal(int)
    splitRequested = Signal(int)
    fieldChanged = Signal(int, str, str)
    #: A heading was chosen for one clipping: (row id, key, words). Its own
    #: signal rather than two fieldChanged emissions, because the key and the
    #: words have to land on the clipping together or a session saved between
    #: them carries half a heading.
    headingPicked = Signal(int, str, str)
    #: The list of headings on offer gained one, so anything showing it should
    #: look again.
    headingListChanged = Signal()
    #: The size or colour every heading prints at changed.
    headingStyleChanged = Signal()
    labelChanged = Signal(int, str)
    navigate = Signal(int)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.row = None
        # Which screen this window is serving. The board sets it; the press
        # report leaves it false. It decides what the Section control means,
        # so it is set BEFORE the row is shown, never after.
        self.for_board = False
        self._loading = False
        self._connected = False
        self._zoom_index = ZOOM_STEPS.index(1.0)
        self._pixmap: QPixmap | None = None

        self.setWindowTitle("Clipping")
        self.setModal(False)
        self.resize(1080, 840)
        self.setStyleSheet(f"QDialog {{ background: {theme.DARK_PANEL}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_top_bar())
        outer.addWidget(self._build_viewport(), 1)
        outer.addWidget(self._build_detail_panel())

        QShortcut(QKeySequence(Qt.Key_Left), self, lambda: self.navigate.emit(-1))
        QShortcut(QKeySequence(Qt.Key_Right), self, lambda: self.navigate.emit(1))
        QShortcut(QKeySequence("Ctrl++"), self, lambda: self._zoom(1))
        QShortcut(QKeySequence("Ctrl+-"), self, lambda: self._zoom(-1))
        QShortcut(QKeySequence("Ctrl+0"), self, self._zoom_reset)

    # ------------------------------------------------------------- building
    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("PreviewBar")
        bar.setStyleSheet(
            f"#PreviewBar {{ background: {theme.DARK_BAR};"
            f" border-bottom: 1px solid #26324A; }}"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(8)

        self.prev_btn = QPushButton("‹")
        self.next_btn = QPushButton("›")
        self.position = QLabel("1 / 1")
        self.position.setStyleSheet(
            f"color: {theme.ORANGE}; font-size: 12px; font-weight: 700;"
        )
        for button in (self.prev_btn, self.next_btn):
            button.setFixedWidth(34)
            button.setStyleSheet(DARK_BUTTON)
        row.addWidget(self.prev_btn)
        row.addWidget(self.position)
        row.addWidget(self.next_btn)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        # A long headline used to set the preview window's minimum width - one
        # clipping with a wordy caption and the window would not resize at all.
        self.heading = ElidedLabel(floor=140)
        self.heading.setStyleSheet("color: white; font-size: 13px; font-weight: 700;")
        self.provenance = ElidedLabel(floor=140)
        self.provenance.setStyleSheet("color: #94A3B8; font-size: 11px;")
        titles.addWidget(self.heading)
        titles.addWidget(self.provenance)
        row.addSpacing(10)
        row.addLayout(titles, 1)

        self.zoom_out = QPushButton("−")
        self.zoom_label = QPushButton("100%")
        self.zoom_in = QPushButton("+")
        for button in (self.zoom_out, self.zoom_label, self.zoom_in):
            button.setStyleSheet(DARK_BUTTON)
        self.zoom_out.setFixedWidth(34)
        self.zoom_in.setFixedWidth(34)
        self.zoom_label.setFixedWidth(62)
        row.addWidget(self.zoom_out)
        row.addWidget(self.zoom_label)
        row.addWidget(self.zoom_in)

        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setStyleSheet(DANGER_BUTTON)
        close = QPushButton("Close")
        close.setStyleSheet(DARK_BUTTON)
        row.addWidget(self.delete_btn)
        row.addWidget(close)

        self.prev_btn.clicked.connect(lambda: self.navigate.emit(-1))
        self.next_btn.clicked.connect(lambda: self.navigate.emit(1))
        self.zoom_out.clicked.connect(lambda: self._zoom(-1))
        self.zoom_in.clicked.connect(lambda: self._zoom(1))
        self.zoom_label.clicked.connect(self._zoom_reset)
        self.delete_btn.clicked.connect(self._delete)
        close.clicked.connect(self.close)
        return bar

    def _build_viewport(self) -> QWidget:
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignCenter)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(
            f"QScrollArea {{ background: {theme.DARK_VIEWPORT}; border: none; }}"
        )
        # The same gliding wheel as everywhere else, on both axes: a zoomed-in
        # clipping is panned as much sideways as down.
        self.scroll.verticalScrollBar().setSingleStep(WHEEL_PIXELS // 2)
        self.scroll.horizontalScrollBar().setSingleStep(WHEEL_PIXELS // 2)
        smooth(self.scroll)
        smooth(self.scroll, Qt.Horizontal)
        self.canvas = QLabel()
        self.canvas.setAlignment(Qt.AlignCenter)
        self.canvas.setStyleSheet(f"background: {theme.DARK_VIEWPORT}; padding: 18px;")
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.scroll.setWidget(self.canvas)
        return self.scroll

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("PreviewPanel")
        panel.setStyleSheet(
            f"#PreviewPanel {{ background: {theme.DARK_BAR};"
            f" border-top: 1px solid #26324A; }}"
            f"QLabel {{ color: #94A3B8; font-size: 11px; background: transparent; }}"
            f"QLineEdit, QComboBox {{ background: #1E293B; border: 1px solid #33415A;"
            f" border-radius: 8px; padding: 7px 9px; color: #E2E8F0; font-size: 12px; }}"
            f"QLineEdit:focus, QComboBox:focus {{ border-color: {theme.ORANGE}; }}"
            # The popup comes from theme.py by name now. Written by hand here,
            # it set a selection background and no selection colour - and Qt
            # merges stylesheet properties one at a time, so the missing pen
            # fell through to the global sheet's near-black NAVY and landed on
            # this slate ground at 1.03:1. The two are one token pair and are
            # never written apart.
            + theme.COMBO_POPUP_SLATE
        )
        body = QVBoxLayout(panel)
        body.setContentsMargins(18, 14, 18, 14)
        body.setSpacing(11)

        label_row = QHBoxLayout()
        label_row.setSpacing(12)
        self.label_edit = self._field(
            "Headline / label that prints above the image", label_row, 2
        )
        body.addLayout(label_row)

        # The address the import read from under the picture. It gets a whole
        # row because addresses are long, and its own field because until now
        # the only way to see one was on a clipping that had no headline - which
        # the 360 Degree document's clippings do have.
        link_row = QHBoxLayout()
        link_row.setSpacing(12)
        self.link = self._field(
            "Link printed under the image, and clickable in the report",
            link_row, 1
        )
        body.addLayout(link_row)

        fields = QHBoxLayout()
        fields.setSpacing(12)
        self.newspaper = self._combo("Newspaper", fields, 3)
        self.edition = self._combo("Edition / city", fields, 2)
        self.page = self._field("Page", fields, 1)
        # ONE control, two jobs, and which job it is doing depends on which
        # screen opened this window - the same dialog serves the press report
        # list and the Sentiment Board.
        #
        #   Press report: it is the heading picker. The only thing section ever
        #   did to a printed report was decide this heading, so on the report
        #   screen that is what it says and that is all it offers.
        #
        #   Board: it is the sentiment control, and must stay the seven values,
        #   because that is how a clipping is filed into a column.
        #
        # The label changes with it. A control that means two different things
        # under one word is how somebody sets a heading and moves a clipping to
        # Negative in the same click.
        self.section, self.section_label = self._plain_combo(
            "Section", fields, 2, [s.value for s in Section]
        )
        # NEVER editable, on either screen. It picks from a list and that is
        # all it does. It used to be typable on the press report, wired to
        # currentTextChanged - which fires on every keystroke - and every one of
        # those keystrokes was saved as a new heading. Headings are added in
        # their own dialog now, behind the List... button, where pressing Add is
        # the moment a person means it.
        self.section.setEditable(False)

        # Beside it, and only on the press report: how every heading in the
        # report is printed. Report-wide rather than per clipping - two
        # headings at different sizes in one report is not a report anybody
        # wants to hand over.
        self.heading_size_btn = QPushButton("Size")
        self.heading_size_btn.setStyleSheet(DARK_BUTTON)
        self.heading_size_btn.setToolTip(
            "How big every section heading in the report is printed.")
        self.heading_colour_btn = QPushButton("Colour")
        self.heading_colour_btn.setStyleSheet(DARK_BUTTON)
        self.heading_colour_btn.setToolTip(
            "What colour every section heading in the report is printed.")
        style_column = QVBoxLayout()
        style_column.setSpacing(4)
        self.heading_style_label = QLabel("Heading size and colour")
        style_column.addWidget(self.heading_style_label)
        style_row = QHBoxLayout()
        style_row.setSpacing(6)
        # The only way in or out of the list. Adding used to happen by typing
        # into the picker, which saved a heading per keystroke.
        self.heading_list_btn = QPushButton("Headings…")
        self.heading_list_btn.setStyleSheet(DARK_BUTTON)
        self.heading_list_btn.setToolTip(
            "Add a heading to the list, or take one off. The picker beside "
            "this chooses between them.")
        self.heading_list_btn.clicked.connect(self._manage_headings)
        style_row.addWidget(self.heading_size_btn)
        style_row.addWidget(self.heading_colour_btn)
        style_row.addWidget(self.heading_list_btn)
        style_column.addLayout(style_row)
        fields.addLayout(style_column, 2)
        self.heading_size_btn.clicked.connect(self._offer_heading_sizes)
        self.heading_colour_btn.clicked.connect(self._offer_heading_colours)

        body.addLayout(fields)

        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet(
            "color: #FCD9A8; background: rgba(184,115,10,0.16);"
            " border: 1px solid rgba(184,115,10,0.4);"
            " padding: 8px 10px; border-radius: 8px; font-size: 11px;"
        )
        self.notice.hide()
        body.addWidget(self.notice)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.rotate_btn = QPushButton("Rotate 90°")
        self.split_btn = QPushButton("Split in two")
        self.exclude_btn = QPushButton("Exclude")
        for button in (self.rotate_btn, self.split_btn):
            button.setStyleSheet(DARK_BUTTON)
        self.exclude_btn.setStyleSheet(DANGER_BUTTON)
        actions.addWidget(self.rotate_btn)
        actions.addWidget(self.split_btn)
        actions.addStretch(1)
        actions.addWidget(self.exclude_btn)
        body.addLayout(actions)

        self.rotate_btn.clicked.connect(self._rotate)
        self.split_btn.clicked.connect(self._split)
        self.exclude_btn.clicked.connect(self._toggle_include)
        return panel

    def _labelled(self, text, layout, stretch):
        column = QVBoxLayout()
        column.setSpacing(4)
        column.addWidget(QLabel(text))
        layout.addLayout(column, stretch)
        return column

    def _field(self, label, layout, stretch) -> QLineEdit:
        column = self._labelled(label, layout, stretch)
        edit = QLineEdit()
        column.addWidget(edit)
        return edit

    def _combo(self, label, layout, stretch) -> QComboBox:
        column = self._labelled(label, layout, stretch)
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        column.addWidget(combo)
        return combo

    def _plain_combo(self, label, layout, stretch, items):
        """Returns the combo AND its label - this one's label changes."""
        column = QVBoxLayout()
        column.setSpacing(4)
        caption = QLabel(label)
        column.addWidget(caption)
        layout.addLayout(column, stretch)
        combo = QComboBox()
        combo.addItems(items)
        column.addWidget(combo)
        return combo, caption

    # ------------------------------------------------- the heading, and its look
    NO_HEADING = "— no heading —"

    def _heading_choices(self) -> list:
        return [self.NO_HEADING] + section_list.load().all_words()

    def _offer_heading_sizes(self) -> None:
        """Whole points only, and only sizes that actually fit on the line.

        Not a number box. A heading is one line across the top of a sheet, and
        past about 30pt a long one stops fitting - at which point MuPDF quietly
        shrinks it to make it fit and nothing tells anybody the size asked for
        is not the size printed.
        """
        now = section_list.load()
        menu = QMenu(self)
        for size in section_list.SIZES:
            action = menu.addAction(f"{size:g} pt"
                                    + ("      ✓" if size == now.size else ""))
            action.triggered.connect(
                lambda _checked=False, value=size: self._set_heading_style(
                    size=value))
        menu.exec(self.heading_size_btn.mapToGlobal(
            self.heading_size_btn.rect().bottomLeft()))

    def _offer_heading_colours(self) -> None:
        now = section_list.load()
        menu = QMenu(self)
        for said, hexcode in section_list.COLOURS:
            action = menu.addAction(
                said + ("      ✓" if hexcode.upper() == now.colour.upper()
                        else ""))
            action.triggered.connect(
                lambda _checked=False, value=hexcode: self._set_heading_style(
                    colour=value))
        menu.addSeparator()
        picked = menu.addAction("Choose another colour…")
        picked.triggered.connect(self._pick_heading_colour)
        menu.exec(self.heading_colour_btn.mapToGlobal(
            self.heading_colour_btn.rect().bottomLeft()))

    def _pick_heading_colour(self) -> None:
        from PySide6.QtGui import QColor

        now = section_list.load()
        chosen = QColorDialog.getColor(QColor(now.colour), self,
                                       "Colour for section headings")
        if chosen.isValid():
            self._set_heading_style(colour=chosen.name().upper())

    def _manage_headings(self) -> None:
        """Add a heading, or take one off. The only route to the stored list."""
        from .headings_dialog import HeadingsDialog

        screen = HeadingsDialog(self)
        screen.exec()
        if screen.changed:
            self.headingListChanged.emit()
            self.headingStyleChanged.emit()
            if self.row is not None:
                self.show_row(self.row)

    def _set_heading_style(self, size=None, colour=None) -> None:
        section_list.set_style(size=size, colour=colour)
        self._show_heading_style()
        self.headingStyleChanged.emit()

    def _show_heading_style(self) -> None:
        now = section_list.load()
        self.heading_size_btn.setText(f"{now.size:g} pt")
        self.heading_colour_btn.setText("Colour")
        # The button wears the colour it sets, which is quicker to read than
        # any words for it and does not need translating.
        self.heading_colour_btn.setStyleSheet(
            DARK_BUTTON + f"QPushButton {{ color: {now.colour}; }}")

    # -------------------------------------------------------------- loading
    def show_row(self, row, position: int = 0, total: int = 0) -> None:
        self.row = row
        clip = row.clip
        self._loading = True

        self._pixmap = self._render(clip)
        self._apply_zoom()

        name = clip.title_text or "Not named yet"
        self.heading.setText(name)
        width, height = clip.rendered_size()
        bits = [clip.section.value]
        if clip.division:
            bits.append(clip.division)
        # As on the card: the heading above already carries the page unless a
        # headline has been typed over it.
        if clip.page and clip.label.strip():
            bits.append(f"page {clip.page}")
        bits.append(f"{width}x{height} px")
        bits.append(row.source_name or clip.source_ref)
        self.provenance.setText("  ·  ".join(str(b) for b in bits if b))
        if total:
            self.position.setText(f"{position} / {total}")
            self.prev_btn.setEnabled(position > 1)
            self.next_btn.setEnabled(position < total)

        self.label_edit.setText(clip.title_text)
        self.link.setText(clip.url)
        self._fill(self.newspaper, self.model.name_index.newspaper_names, clip.newspaper)
        self._fill(self.edition, self.model.name_index.edition_names, clip.edition)
        self.page.setText(clip.page)
        self.section.blockSignals(True)
        self.section.clear()
        if self.for_board:
            self.section_label.setText("Sentiment (which board column)")
            self.section.addItems([s.value for s in Section])
            self.section.setCurrentIndex(
                max(0, self.section.findText(clip.section.value)))
            self.section.setToolTip(
                "Which of the four columns this clipping is filed under.")
        else:
            self.section_label.setText(
                "Section heading printed over this clipping")
            choices = self._heading_choices()
            here = section_list.tidy(clip.section_title)
            # The heading this clipping carries MUST be one of the choices,
            # even if it has since been taken off the list. Otherwise
            # setCurrentIndex finds nothing, the box shows "no heading", and
            # the next interaction writes that back - silently throwing away a
            # heading the report is still printing.
            if here and here not in choices:
                choices.append(here)
            self.section.addItems(choices)
            self.section.setCurrentIndex(
                max(0, self.section.findText(here or self.NO_HEADING)))
            self.section.setToolTip(
                "Printed in a line above this clipping, once per heading. "
                "Use the Headings button to add one to this list.")
        self.section.blockSignals(False)
        for widget in (self.heading_size_btn, self.heading_colour_btn,
                       self.heading_list_btn, self.heading_style_label):
            widget.setVisible(not self.for_board)
        if not self.for_board:
            self._show_heading_style()

        notes = []
        if clip.probable_junk:
            notes.append(f"Flagged: {clip.junk_reason}")
        if clip.caption_raw:
            notes.append(f"Caption in the document: {clip.caption_raw}")
        if clip.ocr_text:
            notes.append(f"Read from the image: {clip.ocr_text}")
        if notes:
            self.notice.setText("\n".join(notes))
            self.notice.show()
        else:
            self.notice.hide()

        self.exclude_btn.setText("Exclude" if clip.include else "Include again")
        self.setWindowTitle(name)
        self._loading = False
        self._connect_once()

    def _fill(self, combo: QComboBox, items: list[str], value: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(items)

        # ONE completer per combo, made once and refilled. It used to be built
        # fresh for every clipping, and setCompleter does not delete the one it
        # replaces - so walking a division of two hundred clippings piled up two
        # hundred completers, each owning a popup view.
        completer = combo.completer()
        if completer is None or completer.parent() is not combo:
            completer = QCompleter(combo)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            combo.setCompleter(completer)
            # The suggestion list is a TOP-LEVEL QListView with no parent, so
            # no "QComboBox QAbstractItemView" selector can reach it - not this
            # program's, and not any theming library's. It is styled here, on
            # the widget, or it is not styled at all.
            popup = completer.popup()
            if popup is not None:
                popup.setStyleSheet(theme.COMPLETER_POPUP_SLATE)
        completer.setModel(QStringListModel(items, completer))

        combo.setEditText(value)
        combo.blockSignals(False)

    def _connect_once(self) -> None:
        if self._connected:
            return
        # activated fires when a name is PICKED from the list; editingFinished
        # when typing stops. Between them that is one undo step per correction.
        #
        # These were on currentTextChanged, which on an editable combo fires per
        # keystroke - so correcting a misread newspaper name pushed one undo
        # step per letter, and Ctrl+Z had to be pressed once per character to
        # take it back. Same signal, same mistake, as the heading picker; it
        # simply cost less because these do not write to disk.
        self.newspaper.activated.connect(
            lambda _index: self._emit("newspaper",
                                      self.newspaper.currentText()))
        self.newspaper.lineEdit().editingFinished.connect(
            lambda: self._emit("newspaper", self.newspaper.currentText()))
        self.edition.activated.connect(
            lambda _index: self._emit("edition", self.edition.currentText()))
        self.edition.lineEdit().editingFinished.connect(
            lambda: self._emit("edition", self.edition.currentText()))
        self.page.textEdited.connect(lambda text: self._emit("page", text))
        # currentIndexChanged, NOT currentTextChanged. The latter fires on
        # every keystroke of an editable combo, which is what saved a heading
        # per letter typed.
        self.section.currentIndexChanged.connect(self._section_picked)
        self.label_edit.textEdited.connect(self._emit_label)
        self.link.textEdited.connect(lambda text: self._emit("url", text))
        self._connected = True

    def _section_picked(self, index: int) -> None:
        """A line was chosen. Which field it writes depends on the screen.

        Takes an INDEX, not text. clear() followed by addItems() fires this with
        -1 and then 0 while a row is being loaded, so the guard below matters as
        much as the _loading flag does.

        It never adds a heading to the list. Choosing is choosing; adding is a
        separate, deliberate act behind the Headings button.
        """
        if self._loading or self.row is None or index < 0:
            return
        text = self.section.itemText(index)
        if self.for_board:
            self._emit("section", text)
            return
        words = section_list.tidy(text)
        if not words or words == section_list.tidy(self.NO_HEADING):
            self.headingPicked.emit(self.row.id, "", "")
            return
        # It is on the list, or it is the one this clipping already carried and
        # show_row appended for exactly this reason. Either way it has a key.
        key = section_list.load().key_of_words(words) or section_list.key_for(words)
        self.headingPicked.emit(self.row.id, key, words)

    def _emit(self, field: str, value: str) -> None:
        if self._loading or self.row is None:
            return
        self.fieldChanged.emit(self.row.id, field, value.strip())

    def _emit_label(self, value: str) -> None:
        if self._loading or self.row is None:
            return
        self.labelChanged.emit(self.row.id, value.strip())

    # ----------------------------------------------------------------- zoom
    def _render(self, clip) -> QPixmap | None:
        try:
            image = clip.render()
        except Exception:  # noqa: BLE001
            self.canvas.setText("This image could not be displayed.")
            return None
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.getvalue(), "PNG")
        return pixmap

    def _zoom(self, step: int) -> None:
        self._zoom_index = max(0, min(len(ZOOM_STEPS) - 1, self._zoom_index + step))
        self._apply_zoom()

    def _zoom_reset(self) -> None:
        self._zoom_index = ZOOM_STEPS.index(1.0)
        self._apply_zoom()

    def _apply_zoom(self) -> None:
        if not self._pixmap:
            return
        factor = ZOOM_STEPS[self._zoom_index]
        self.zoom_label.setText(f"{int(factor * 100)}%")
        area = self.scroll.viewport().size() - QSize(48, 48)
        if area.width() < 60 or area.height() < 60:
            return
        # 100% means "fit the window", which is what a reader expects here; the other
        # steps scale relative to that fit.
        fitted = self._pixmap
        if fitted.width() > area.width() or fitted.height() > area.height():
            fitted = fitted.scaled(area, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if factor == 1.0:
            self.canvas.setPixmap(fitted)
        else:
            self.canvas.setPixmap(
                self._pixmap.scaled(
                    fitted.size() * factor, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
        self.canvas.adjustSize()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_zoom()

    # -------------------------------------------------------------- actions
    def _rotate(self) -> None:
        if self.row:
            self.rotateRequested.emit(self.row.id)

    def _split(self) -> None:
        if self.row:
            self.splitRequested.emit(self.row.id)

    def _toggle_include(self) -> None:
        if self.row:
            self.excludeRequested.emit(self.row.id, not self.row.clip.include)

    def _delete(self) -> None:
        if self.row:
            self.deleteRequested.emit(self.row.id)
