"""Full-size preview of one clipping, with the actions you want while looking at it.

Opened by clicking a thumbnail. Deciding whether to keep a clipping means reading it,
and reading it means seeing it large, so the actions live here rather than forcing a
trip back to the list: zoom, rotate, split, exclude, delete, and the fields.

Left and right arrows walk the whole list without closing, which is how a division
gets checked quickly.
"""

from __future__ import annotations

import io

from PySide6.QtCore import (QEvent, QSize, QStringListModel, Qt, QTimer,
                            Signal)
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..core import sections as section_list
from ..core import imageops
from ..core.models import (PRIORITIES, UNASSIGNED, CropRect, Section,
                           priority_of)
from . import theme
from .cover_card import icon_pixmap
from .trimming import TrimCanvas
from .fluid import ElidedLabel
from .scroll import WHEEL_PIXELS, smooth

def _not_saved(parent, error) -> None:
    """A write to the settings folder failed. Said, never swallowed: a list
    somebody believes they changed, and did not, is worse than a message."""
    QMessageBox.warning(
        parent, "Could not save",
        f"That change could not be saved ({error.strerror or error}).\n\n"
        "Nothing was changed. Try again in a moment - if it keeps happening, "
        "the settings folder may be full or locked by another program.")


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


#: The column beside the picture that shows the clipping a badged one
#: repeats, and how tall its picture may be.
TWIN_WIDTH = 340
TWIN_PICTURE_TALL = 420

#: The five priority bubbles at the top of the window. One press files the
#: clipping at that level and the list re-sorts around it - priority 1 first,
#: down to 5, everything with no priority under them - so the whole of setting
#: a morning's order is a number and the arrow to the next clipping.
#:
#: Round, and drawn as nothing until they are chosen: an unset bubble is the
#: dark bar it sits on with a hairline round it, and the one in force is filled
#: with its own colour. Nothing else on this bar is a circle, so five circles
#: read as one control without a label or a box round them.
BUBBLE = 32         # the height of every other button on this bar
#: The same five colours the card's own badge uses, so a bubble pressed here
#: and the badge that appears on the card are plainly the same thing.
BUBBLE_COLOURS = theme.PRIORITY_COLOURS
BUBBLE_STYLE = """
QPushButton {{
    background: {rest}; border: 1px solid {edge}; border-radius: {radius}px;
    padding: 0px; margin: 0px; color: {ink}; font-size: 13px; font-weight: 600;
}}
QPushButton:hover {{ border-color: {accent}; color: #FFFFFF; }}
"""


class _ClickLabel(QLabel):
    """A picture that can be pressed."""

    clicked = Signal()

    def mousePressEvent(self, event):  # noqa: N802 - Qt's name
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


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
    #: (clip id, CropRect) - a trim applied, or put back.
    cropChanged = Signal(int, object)
    #: (row id, level 1-5) - a priority bubble was pressed. The window moves
    #: the clipping into that level; this window only asks.
    priorityPicked = Signal(int, int)
    navigate = Signal(int)
    #: Show this clipping instead (a row id) - the one a badged clipping
    #: repeats, or the one that repeats it.
    jumpRequested = Signal(int)
    #: Open the duplicates review, to decide about the pair on screen.
    reviewRequested = Signal()
    #: Put this clipping's picture on the clipboard (a row id).
    copyRequested = Signal(int)
    #: (row id, newspad number) - put a COPY of this clipping into that
    #: newspad's saved work. The window does it; this only asks.
    sendToNewspad = Signal(int, int)
    #: Read this clipping's headline off the picture again (a row id). The
    #: reading is slow and needs the engine, so the window does it.
    rereadRequested = Signal(int)
    #: (row id, words) - what was read off the picture, edited by hand.
    ocrEdited = Signal(int, str)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.row = None
        # Which file a clipping came in from, in the window's words; the
        # window sets it. Without it the clipping's own file name is used.
        self.source_of = None
        self._twin_id = None
        # Which screen this window is serving. The board sets it; the press
        # report leaves it false. It decides what the Section control means,
        # so it is set BEFORE the row is shown, never after.
        self.for_board = False
        self._loading = False
        self._connected = False
        self._zoom_index = ZOOM_STEPS.index(1.0)
        self._position = self._total = 0
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
        # 1 to 5 press the priority bubbles - the same as a click, so pressing
        # the lit one's number takes the priority off. Not while a box has the
        # keyboard: a 5 typed into the Page box is a page number.
        for level in PRIORITIES:
            QShortcut(QKeySequence(str(level)), self,
                      lambda want=level: self._key_pick(want))
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
        row.addSpacing(10)
        row.addWidget(self._build_bubbles())

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

    def _build_bubbles(self) -> QWidget:
        """The five priority bubbles, 1 to 5, with 1 first.

        Beside the walk arrows, because they are used together: look at the
        clipping, press a number, press the arrow for the next one. The one in
        force is filled in and the others are outlines, so the level a clipping
        is at can be read at a glance without a word of explanation.
        """
        holder = QWidget()
        # The bar behind it is dark and the application's own sheet paints
        # every plain widget the page colour, which put a white block under
        # the five circles.
        holder.setStyleSheet("background: transparent;")
        line = QHBoxLayout(holder)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(6)
        self.bubbles = {}
        for level in PRIORITIES:
            bubble = QPushButton(str(level))
            bubble.setCursor(Qt.PointingHandCursor)
            bubble.setFixedSize(BUBBLE, BUBBLE)
            bubble.setFlat(True)
            bubble.setToolTip(
                f"Priority {level}" + (
                    " - first in the report" if level == 1 else
                    " - last in the report" if level == 5 else "")
                + f" (key {level}). Press it again to take the priority off, "
                "and the clipping goes back where it came in. Clippings with "
                "no priority sit under all five, in the order they arrived.")
            bubble.clicked.connect(lambda _checked=False, want=level: self._pick(want))
            self.bubbles[level] = bubble
            line.addWidget(bubble)
        self._paint_bubbles(UNASSIGNED)
        return holder

    def _paint_bubbles(self, level: int) -> None:
        """Fill the one in force; the rest are the bar with a hairline round it."""
        for number, bubble in getattr(self, "bubbles", {}).items():
            colour = BUBBLE_COLOURS[number]
            here = number == level
            # The widget's own size is the circle's size (setFixedSize): a
            # min-width in the sheet is the CONTENT box, so the border made it
            # two pixels wider than the radius it was given and the circle came
            # out very slightly square.
            bubble.setStyleSheet(BUBBLE_STYLE.format(
                rest=colour if here else "transparent",
                accent=colour,
                edge=colour if here else "#39465F",
                ink="#FFFFFF" if here else "#8A97AC",
                radius=BUBBLE // 2))
            bubble.setDown(False)

    def _key_pick(self, level: int) -> None:
        from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QPlainTextEdit, QTextEdit

        focus = QApplication.focusWidget()
        typing = (isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit,
                                     QAbstractSpinBox))
                  or (isinstance(focus, QComboBox) and focus.isEditable()))
        if typing:
            return
        self._pick(level)

    def _pick(self, level: int) -> None:
        """A bubble was pressed: that level, or none if it was already lit."""
        if self.row is None or self._loading:
            return
        # Pressing the lit one takes the priority off. It is the only way back
        # to "no priority", and it is where somebody's hand already is.
        wanted = UNASSIGNED if priority_of(self.row.clip) == level else level
        # Painted at once. The window will send the row back through show_row
        # when it has moved it, but the press has to look answered now.
        self._paint_bubbles(wanted)
        self.priorityPicked.emit(self.row.id, wanted)

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
        self.canvas = TrimCanvas()
        self.canvas.changed.connect(self._trim_moved)
        self.canvas.setAlignment(Qt.AlignCenter)
        self.canvas.setStyleSheet(f"background: {theme.DARK_VIEWPORT}; padding: 18px;")
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.scroll.setWidget(self.canvas)
        # The picture, and beside it - only when the clipping is badged as a
        # repeat - the one it repeats, so the two can be compared here without
        # opening the review. Hidden otherwise: the picture has the room.
        holder = QWidget()
        side_by_side = QHBoxLayout(holder)
        side_by_side.setContentsMargins(0, 0, 0, 0)
        side_by_side.setSpacing(0)
        side_by_side.addWidget(self.scroll, 1)
        self.twin = self._build_twin()
        self.twin.hide()
        side_by_side.addWidget(self.twin)
        # The two things done to a clipping FROM here rather than to it: take a
        # copy of the picture, and put a copy in another newspad. Neither
        # changes the clipping, so neither belongs among Rotate, Split, Trim
        # and Exclude at the foot. They ride on the edge of the picture itself,
        # where the picture is what they are about.
        self._rail = self._build_rail(holder)
        holder.installEventFilter(self)
        return holder

    #: The rail's buttons, and the room it leaves round them.
    RAIL_BUTTON = 38
    RAIL_PAD = 6

    def _build_rail(self, holder) -> QWidget:
        """A tab of two buttons riding on the right edge of the picture.

        Fixed to the edge and rounded on the left only, so it reads as part of
        the window rather than as a pair of buttons left on top of it: the
        straight right side IS the window's edge. Over the dark viewport it is
        a lighter pane of the same dark, which is how the zoom controls and the
        rest of that area are drawn.
        """
        rail = QFrame(holder)
        rail.setObjectName("PreviewRail")
        rail.setCursor(Qt.ArrowCursor)
        rail.setStyleSheet(
            "#PreviewRail { background: rgba(255, 255, 255, 0.10);"
            " border: 1px solid rgba(255, 255, 255, 0.14); border-right: none;"
            " border-top-left-radius: 13px; border-bottom-left-radius: 13px;"
            " border-top-right-radius: 0; border-bottom-right-radius: 0; }"
            "#PreviewRail QToolButton { background: transparent; border: none;"
            " border-radius: 9px; padding: 0; color: #E8EDF5;"
            " font-size: 12px; font-weight: 800; letter-spacing: .02em; }"
            "#PreviewRail QToolButton:hover {"
            " background: rgba(255, 255, 255, 0.16); }"
            "#PreviewRail QToolButton:pressed {"
            " background: rgba(255, 255, 255, 0.24); }"
            "#PreviewRail QToolButton::menu-indicator { image: none;"
            " width: 0; height: 0; }")
        column = QVBoxLayout(rail)
        column.setContentsMargins(self.RAIL_PAD, self.RAIL_PAD,
                                  self.RAIL_PAD, self.RAIL_PAD)
        column.setSpacing(4)

        self.copy_btn = QToolButton(rail)
        self.copy_btn.setFixedSize(self.RAIL_BUTTON, self.RAIL_BUTTON)
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setIcon(icon_pixmap("copy_pages", "#E8EDF5", 19))
        self.copy_btn.setIconSize(QSize(19, 19))
        self.copy_btn.setToolTip(
            "Copy this clipping's picture, as it prints, to the clipboard - "
            "ready to paste into WhatsApp, an email or a document.")
        self.copy_btn.clicked.connect(self._copy_picture)
        column.addWidget(self.copy_btn)

        # ONE BUTTON PER NEWSPAD, rather than a menu. Sending a clipping on is
        # something done over and over while a second newspad is built, and a
        # menu costs a press and a read every time; N2, N3, N4 is one press and
        # no reading. The newspad that is open is not offered - the clipping is
        # already in it.
        line = QFrame(rail)
        line.setFixedHeight(1)
        line.setStyleSheet("background: rgba(255, 255, 255, 0.16);"
                           " border: none;")
        column.addWidget(line)

        from ..core import newspads

        self.newspad_btns = {}
        here = newspads.active()
        for number in range(1, newspads.COUNT + 1):
            if number == here:
                continue
            button = QToolButton(rail)
            button.setFixedSize(self.RAIL_BUTTON, self.RAIL_BUTTON)
            button.setCursor(Qt.PointingHandCursor)
            button.setText(f"N{number}")
            button.setToolTip(
                f"Put a copy of this clipping into Newspad {number}. It stays "
                "here too, and it is there when you switch to that newspad.")
            button.clicked.connect(
                lambda _checked=False, n=number: self._send_to(n))
            self.newspad_btns[number] = button
            column.addWidget(button)
        rail.adjustSize()
        rail.raise_()
        return rail

    #: How long the bubble stays up after a clipping is sent.
    TOLD_FOR_MS = 1500

    def told(self, words: str) -> None:
        """A small pale bubble over the picture, for a second and a half.

        Said here rather than on the window's status line: the preview covers
        the window, so a message put there while this is open is read by
        nobody.
        """
        bubble = getattr(self, "_bubble", None)
        if bubble is None:
            bubble = QLabel(self._rail.parentWidget())
            bubble.setObjectName("PreviewTold")
            bubble.setAlignment(Qt.AlignCenter)
            bubble.setStyleSheet(
                "#PreviewTold { background: rgba(250, 250, 248, 0.97);"
                " color: #1A1F2B; border: 1px solid rgba(0, 0, 0, 0.10);"
                " border-radius: 15px; padding: 8px 16px;"
                " font-size: 12px; font-weight: 700; }")
            self._bubble = bubble
            self._bubble_timer = QTimer(self)
            self._bubble_timer.setSingleShot(True)
            self._bubble_timer.timeout.connect(bubble.hide)
        bubble.setText(words)
        bubble.adjustSize()
        holder = bubble.parentWidget()
        bubble.move(max(0, (holder.width() - bubble.width()) // 2),
                    max(0, holder.height() - bubble.height() - 26))
        bubble.show()
        bubble.raise_()
        self._bubble_timer.start(self.TOLD_FOR_MS)

    def eventFilter(self, watched, event):
        rail = getattr(self, "_rail", None)
        if rail is not None and event.type() == QEvent.Resize \
                and watched is rail.parentWidget():
            self._place_rail()
        return super().eventFilter(watched, event)

    def _place_rail(self) -> None:
        """Against the right edge, half way down the picture."""
        rail = getattr(self, "_rail", None)
        if rail is None or rail.parentWidget() is None:
            return
        holder = rail.parentWidget()
        rail.adjustSize()
        rail.move(max(0, holder.width() - rail.width()),
                  max(0, (holder.height() - rail.height()) // 2))
        rail.raise_()

    def _copy_picture(self) -> None:
        if self.row is not None:
            self.copyRequested.emit(self.row.id)

    def _send_to(self, number: int) -> None:
        if self.row is not None:
            self.sendToNewspad.emit(self.row.id, number)

    def _build_twin(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Twin")
        panel.setFixedWidth(TWIN_WIDTH)
        panel.setStyleSheet(
            f"#Twin {{ background: {theme.DARK_PANEL};"
            " border-left: 1px solid #26324A; }")
        column = QVBoxLayout(panel)
        column.setContentsMargins(14, 12, 14, 12)
        column.setSpacing(8)

        badge_row = QHBoxLayout()
        self.twin_badge = QLabel("SUSPECTED DUPLICATE")
        self.twin_badge.setStyleSheet(
            f"background: {theme.DANGER}; color: white; border-radius: 4px;"
            " padding: 2px 8px; font-size: 10px; font-weight: 800;"
            " letter-spacing: 0.6px;")
        badge_row.addWidget(self.twin_badge)
        badge_row.addStretch(1)
        column.addLayout(badge_row)

        self.twin_words = QLabel()
        self.twin_words.setWordWrap(True)
        self.twin_words.setStyleSheet("color: #E2E8F0; font-size: 12px;")
        column.addWidget(self.twin_words)

        self.twin_picture = _ClickLabel()
        self.twin_picture.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.twin_picture.setMinimumHeight(160)
        self.twin_picture.setCursor(Qt.PointingHandCursor)
        self.twin_picture.setToolTip("Open this one in the preview instead.")
        self.twin_picture.setStyleSheet(
            f"background: {theme.DARK_VIEWPORT}; border: 1px solid #26324A;"
            " border-radius: 6px; padding: 6px;")
        self.twin_picture.clicked.connect(self._jump_to_twin)
        column.addWidget(self.twin_picture, 1)

        self.twin_files = QLabel()
        self.twin_files.setWordWrap(True)
        self.twin_files.setStyleSheet("color: #94A3B8; font-size: 11px;")
        column.addWidget(self.twin_files)

        # One under the other: the column is narrow and each label is a
        # sentence, and a label cut short reads as a fault.
        buttons = QVBoxLayout()
        buttons.setSpacing(6)
        self.twin_open = QPushButton("Open the other one")
        self.twin_open.setStyleSheet(DARK_BUTTON)
        self.twin_open.clicked.connect(self._jump_to_twin)
        self.twin_review = QPushButton("Compare in the review\u2026")
        self.twin_review.setStyleSheet(DARK_BUTTON)
        self.twin_review.setToolTip(
            "Open the duplicates review: both pictures side by side, with "
            "the words they were matched on, and the decision.")
        self.twin_review.clicked.connect(lambda: self.reviewRequested.emit())
        buttons.addWidget(self.twin_open)
        buttons.addWidget(self.twin_review)
        column.addLayout(buttons)
        return panel

    # ---------------------------------------------------------------- twin
    def _partner_of(self, row):
        """(the row this one repeats or is repeated by, how, how many more)."""
        clip = row.clip
        # The list on show: a category of the board opened out holds only its
        # own clippings, and a partner outside it is not beside it there.
        scoped = getattr(self.model, "scoped_rows", None)
        source = scoped() if callable(scoped) else self.model.rows
        rows = [r for r in source if r.clip is not None and r is not row]
        if clip.duplicate_of:
            for other in rows:
                if other.clip.uid == clip.duplicate_of:
                    return other, "repeat of", 0
            return None, "", 0
        copies = [other for other in rows if other.clip.duplicate_of == clip.uid]
        if copies:
            return copies[0], "repeated by", len(copies) - 1
        return None, "", 0

    def _file_of(self, row) -> str:
        if callable(self.source_of):
            try:
                said = self.source_of(row.clip)
                if said:
                    return str(said)
            except Exception:  # noqa: BLE001 - the name is a courtesy
                pass
        return (row.source_name or row.clip.source_file
                or row.clip.source_ref or "")

    def _show_twin(self, row) -> None:
        """The clipping this one repeats (or is repeated by), or nothing."""
        self._twin_id = None
        if self.for_board and getattr(self.model, "scope", None) is None:
            # A board card over four columns: the check and its review belong
            # to a category opened out as a list, not to the cards.
            self.twin.hide()
            return
        try:
            partner, how, more = self._partner_of(row)
        except Exception:  # noqa: BLE001 - never let this cost the preview
            partner = None
        if partner is None:
            self.twin.hide()
            return
        self._twin_id = partner.id
        # Called by the numbers the list shows - in a category, its own.
        number_of = getattr(self.model, "number_of", None)
        if callable(number_of):
            mine, theirs = number_of(row.id), number_of(partner.id)
        else:
            mine = self.model.position_of(row.id) + 1
            theirs = self.model.position_of(partner.id) + 1
        keeps = "dossier" if self.for_board else "report"
        if how == "repeat of":
            words = (f"No. {mine} is flagged as a repeat of No. {theirs}, shown "
                     f"here. The {keeps} keeps No. {theirs} unless you decide "
                     "otherwise in the review.")
        else:
            words = (f"No. {theirs}, shown here, is flagged as a repeat of this "
                     "one" + (f" \u2014 and {more} more" if more else "")
                     + f". This one is the one the {keeps} keeps.")
        self.twin_words.setText(words)
        self.twin_files.setText(
            f"This one came from: {self._file_of(row) or 'unknown'}\n"
            f"The other came from: {self._file_of(partner) or 'unknown'}")
        picture = self._render_quiet(partner.clip)
        if picture is None or picture.isNull():
            self.twin_picture.setPixmap(QPixmap())
            self.twin_picture.setText("(the picture could not be shown)")
        else:
            self.twin_picture.setText("")
            self.twin_picture.setPixmap(picture.scaled(
                TWIN_WIDTH - 44, TWIN_PICTURE_TALL, Qt.KeepAspectRatio,
                Qt.SmoothTransformation))
        self.twin.show()

    def _render_quiet(self, clip):
        """The clipping as it prints, or None - never a word on the canvas."""
        try:
            image = clip.render()
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, "PNG")
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue(), "PNG")
            return pixmap
        except Exception:  # noqa: BLE001
            return None

    def _jump_to_twin(self) -> None:
        if self._twin_id is not None:
            self.jumpRequested.emit(self._twin_id)

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
        # WHAT THE READER MADE OF THE PICTURE, in a box of its own.
        #
        # It was already being read - the duplicate check matches on it and the
        # search looks in it - and it was the one thing about a clipping that
        # could not be seen or corrected. A misread headline quietly stopped a
        # repeat being found and a search finding anything, with nothing on
        # screen to say so.
        #
        # It is NOT the headline that prints. That is the box above, which
        # somebody types; this is what the picture says, and the second button
        # is how one becomes the other.
        read_row = QHBoxLayout()
        read_row.setSpacing(8)
        self.ocr_edit = self._field(
            "Headline read from the picture", read_row, 1)
        self.ocr_edit.setPlaceholderText(
            "Not read yet — press the round button to read it")
        self.ocr_edit.setToolTip(
            "What the reader made of this picture. The duplicate check and "
            "the search both use it, so correcting a misreading here makes "
            "both of them better.")
        self.reread_btn = self._round_button(
            "rotate", "Read this picture again",
            "Read the headline off the picture again. Worth doing when what "
            "is in the box is nonsense - a crooked scan often reads better "
            "after it has been straightened or trimmed.")
        self.reread_btn.clicked.connect(self._reread)
        self.use_read_btn = self._round_button(
            "check", "Use this as the headline",
            "Put these words into the headline box above, which is the one "
            "that prints above the clipping in the report.")
        self.use_read_btn.clicked.connect(self._use_reading)
        # Level with the box, not with its caption.
        pads = QVBoxLayout()
        pads.setContentsMargins(0, 0, 0, 0)
        pads.setSpacing(0)
        pads.addSpacing(17)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addWidget(self.reread_btn)
        buttons.addWidget(self.use_read_btn)
        pads.addLayout(buttons)
        read_row.addLayout(pads, 0)
        body.addLayout(read_row)

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
        # A capture from a link, or a photo taken at arm's length, often has a
        # strip of something else along one edge.
        self.trim_btn = QPushButton("Trim…")
        self.trim_btn.setToolTip(
            "Drag the edges in to keep only part of this clipping. The picture "
            "itself is not cut - Ctrl+Z puts the edges back.")
        self.trim_apply = QPushButton("Keep this")
        self.trim_cancel = QPushButton("Cancel")
        self.trim_reset = QPushButton("Whole picture")
        self.trim_reset.setToolTip("Put back everything a trim took off.")
        self.exclude_btn = QPushButton("Exclude")
        for button in (self.rotate_btn, self.split_btn, self.trim_btn,
                       self.trim_apply, self.trim_cancel, self.trim_reset):
            button.setStyleSheet(DARK_BUTTON)
        self.exclude_btn.setStyleSheet(DANGER_BUTTON)
        actions.addWidget(self.rotate_btn)
        actions.addWidget(self.split_btn)
        actions.addWidget(self.trim_btn)
        actions.addWidget(self.trim_apply)
        actions.addWidget(self.trim_cancel)
        actions.addWidget(self.trim_reset)
        actions.addStretch(1)
        actions.addWidget(self.exclude_btn)
        body.addLayout(actions)

        self.rotate_btn.clicked.connect(self._rotate)
        self.split_btn.clicked.connect(self._split)
        self.exclude_btn.clicked.connect(self._toggle_include)
        self.trim_btn.clicked.connect(self._trim_start)
        self.trim_apply.clicked.connect(self._trim_keep)
        self.trim_cancel.clicked.connect(self._trim_stop)
        self.trim_reset.clicked.connect(self._trim_whole)
        self._show_trim_buttons(False)
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

    #: The round buttons beside the read box.
    ROUND = 30

    def _round_button(self, icon: str, tip_short: str, tip: str):
        """One small round button, dark like the panel it sits on."""
        button = QToolButton()
        button.setFixedSize(self.ROUND, self.ROUND)
        button.setCursor(Qt.PointingHandCursor)
        button.setIcon(icon_pixmap(icon, "#DCE5F2", 15))
        button.setIconSize(QSize(15, 15))
        button.setToolTip(tip)
        button.setAccessibleName(tip_short)
        button.setStyleSheet(
            f"QToolButton {{ background: rgba(255, 255, 255, 0.07);"
            f" border: 1px solid rgba(255, 255, 255, 0.16);"
            f" border-radius: {self.ROUND // 2}px; padding: 0; }}"
            "QToolButton:hover { background: rgba(255, 255, 255, 0.15); }"
            "QToolButton:pressed { background: rgba(255, 255, 255, 0.22); }"
            "QToolButton:disabled { background: rgba(255, 255, 255, 0.03);"
            " border-color: rgba(255, 255, 255, 0.08); }")
        return button

    def _reread(self) -> None:
        if self.row is not None:
            self.rereadRequested.emit(self.row.id)

    def _use_reading(self) -> None:
        """What the picture said becomes what the report prints."""
        words = self.ocr_edit.text().strip()
        if not words or self.row is None:
            return
        self.label_edit.setText(words)
        self._emit_label()
        self.told("Put into the headline")

    def _ocr_typed(self, words: str) -> None:
        """A correction typed into the read box. It is the clipping's own
        reading from then on - the duplicate check and the search both read
        the same field, so a correction helps both."""
        self.use_read_btn.setEnabled(bool(words.strip()))
        if self.row is not None:
            self.ocrEdited.emit(self.row.id, words)

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
        try:
            section_list.set_style(size=size, colour=colour)
        except OSError as error:
            _not_saved(self, error)
            return
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
        # Kept so the view can draw this same clipping again after a trim.
        self._position, self._total = position, total
        if self.canvas.trimming:
            self.canvas.stop_trim()
            self._show_trim_buttons(False)

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
        self._show_twin(row)
        self._paint_bubbles(priority_of(clip))
        if total:
            self.position.setText(f"{position} / {total}")
            self.prev_btn.setEnabled(position > 1)
            self.next_btn.setEnabled(position < total)

        self.label_edit.setText(clip.title_text)
        was = self.ocr_edit.blockSignals(True)
        try:
            self.ocr_edit.setText(str(getattr(clip, "ocr_text", "") or "").strip())
        finally:
            self.ocr_edit.blockSignals(was)
        self.use_read_btn.setEnabled(bool(self.ocr_edit.text().strip()))
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
                "Which of the board's categories this clipping is filed under.")
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
            where = ("Caption copied" if clip.name_source == "copied"
                     else "Caption in the document")
            notes.append(f"{where}: {clip.caption_raw}")
        # What the picture says has a box of its own now, right above this
        # one, so repeating it here was the same sentence twice on one panel.
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
        self.ocr_edit.textEdited.connect(self._ocr_typed)
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

    # ---------------------------------------------------------------- trim
    def _show_trim_buttons(self, trimming: bool) -> None:
        """While trimming, the bar offers only what a trim can do."""
        self.trim_btn.setVisible(not trimming)
        self.rotate_btn.setVisible(not trimming)
        self.split_btn.setVisible(not trimming)
        self.exclude_btn.setVisible(not trimming)
        self.trim_apply.setVisible(trimming)
        self.trim_cancel.setVisible(trimming)
        clip = self.row.clip if self.row is not None else None
        self.trim_reset.setVisible(
            trimming and clip is not None and not clip.crop.is_identity)

    def _trim_start(self) -> None:
        if self.row is None:
            return
        self.canvas.start_trim()
        self._show_trim_buttons(True)
        self.notice.setText("Drag the edges in, then press Keep this.")
        self.notice.show()

    def _trim_stop(self) -> None:
        self.canvas.stop_trim()
        self._show_trim_buttons(False)
        self.notice.hide()
        if self.row is not None:
            self.show_row(self.row, self._position, self._total)

    def _trim_moved(self) -> None:
        """What the box is worth, said while it is being dragged."""
        if not self.canvas.trimming or self.row is None:
            return
        left, top, right, bottom = self.canvas.where()
        across, down = self.row.clip.rendered_size()
        self.notice.setText(
            f"Keeping {int((right - left) * across)} × "
            f"{int((bottom - top) * down)} pixels of "
            f"{int(across)} × {int(down)}.")

    def _trim_keep(self) -> None:
        if self.row is None:
            return
        box = self.canvas.where()
        clip_id = self.row.id
        self.canvas.stop_trim()
        self._show_trim_buttons(False)
        self.notice.hide()
        if not imageops.worth_trimming(box):
            return                      # the whole picture: nothing to do
        self.cropChanged.emit(clip_id, imageops.crop_from_view(self.row.clip, box))

    def _trim_whole(self) -> None:
        if self.row is None:
            return
        clip_id = self.row.id
        self.canvas.stop_trim()
        self._show_trim_buttons(False)
        self.notice.hide()
        self.cropChanged.emit(clip_id, CropRect())

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
