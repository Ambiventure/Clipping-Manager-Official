"""The review list: hover, clicks, inline editing and drag reordering.

The rows are painted by :mod:`delegates`, so this is where a painted button becomes
a real one. Every region is hit-tested against the same geometry that drew it.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEvent,
    QMimeData,
    QPoint,
    QRect,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (QColor, QDrag, QFont, QGuiApplication, QPainter,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QAbstractItemView, QLineEdit, QListView,
                               QStyleOptionViewItem)

from . import rowlayout, theme
from .scroll import WHEEL_PIXELS, page_under, smooth
from .delegates import EntryDelegate
from .model import ENTRY_CLIP, ENTRY_GROUP

MIME = "application/x-clippings-rows"


class ClipList(QListView):
    """Virtualised list of group headers and clipping rows."""

    clipAction = Signal(str, int)          # action name, clip id
    groupAction = Signal(str, str)         # action name, group identity
    labelEdited = Signal(int, str)         # clip id, new headline
    urlEdited = Signal(int, str)           # clip id, new address
    #: (clip id, words) - a reading corrected by hand. Its own signal, because
    #: what the picture says is not what the report prints.
    readEdited = Signal(int, str)
    previewRequested = Signal(int)
    reorderRequested = Signal(list, int)   # clip ids, target position
    selectionToggled = Signal(int, bool, bool)   # clip id, additive, ranged

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setUniformItemSizes(False)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QListView.NoFrame)
        self.setResizeMode(QListView.Adjust)
        self.setSpacing(0)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)

        self.delegate = EntryDelegate(self)
        self.setItemDelegate(self.delegate)

        # When the whole page scrolls as one, the list stops scrolling itself
        # and simply stands at its full height inside the page. See
        # follow_content().
        self._follows_content = False
        # Set while the list stands in for one of the board's columns - a
        # category opened out. A file or picture dropped on it then lands in
        # that category, not wherever the window would have put it. None for
        # the press report's list, which behaves as it always has.
        self.drop_section = None
        # Words drawn in the middle of the list while it has nothing in it.
        # Empty for the press report's list, which has a drop zone of its own.
        self.empty_hint = ""

        self._press_point: QPoint | None = None
        self._press_hit = None
        self._press_row = -1
        # A drag's gap: where it is opening (a boundary - "before row k", the
        # row count for the very end - or -1), how far each boundary is open
        # now and how far it is meant to be, how tall it opens, and what is
        # carried, whose card the slot drawn in it matches. See _open_gap.
        self._gap_at = -1
        self._gap_now: dict = {}
        self._gap_wanted: dict = {}
        self._gap_size = 0
        self._slot_entry = None
        # Room added at the foot while a drag is on, when the list stands at
        # full height in the page: the gap pushes the last rows down, and
        # without it they, and a slot opened at the very end, would be cut off.
        self._drag_extra = 0
        # The stylesheet strips the application font's family list off every
        # item view, taking the Devanagari fallback with it. Put it back, or a
        # Hindi masthead is boxes on any machine that has only one such font.
        theme.apply_font(self)
        self._editor: QLineEdit | None = None
        # Which of the two boxes is open. The headline and the address are
        # separate fields and each keeps what is typed into it, so the editor
        # has to know which one it was opened on.
        self._editing_field = "label"
        self._editing_id: int | None = None

        # Last, not first: asking for the scrollbar delivers an event that
        # reaches this view's own event filter, and that filter reads fields
        # which do not exist yet at the top of __init__.
        # Per-pixel scrolling alone is not smooth - Qt still multiplies a 58px
        # step by the system's line count, which came to four whole rows a notch.
        self.verticalScrollBar().setSingleStep(WHEEL_PIXELS // 2)
        smooth(self)

    # ---------------------------------------------------------------- hover
    def setModel(self, model) -> None:  # noqa: N802 - Qt name
        """Keep the list's height tied to what is in it.

        Standing at full height inside a scrolling page only works if the
        height is kept up to date - a document folded, a clipping deleted, a
        file imported all change how tall the list is, and a stale height
        leaves either a gap at the bottom of the page or rows the page cannot
        scroll down to.
        """
        super().setModel(model)
        if model is None:
            return
        for signal in ("layoutChanged", "modelReset", "rowsInserted",
                       "rowsRemoved"):
            hook = getattr(model, signal, None)
            if hook is not None:
                hook.connect(self.refresh_height)

    def edit_field(self, row: int, field: str = "label") -> None:
        """Open one of the two boxes for typing, from outside the list.

        The address box is only drawn when a clipping already has an address,
        so on a pasted screenshot there is nothing to click. This opens it
        anyway, which is what the card's own "Add web address" reaches for.
        """
        index = self.model().index(row, 0)
        entry = self.model().entry_at(row)
        if entry is None or entry.row is None:
            return
        # Draw the box first: there is nothing to click on a card that has not
        # got that box, so nothing to type into either.
        if field == "url" and not entry.row.clip.url.strip():
            entry.row.clip.show_url_box = True
            self.model().layoutChanged.emit()
            self.refresh_height()
        elif field == "label" and not entry.row.clip.effective_label.strip():
            entry.row.clip.show_title_box = True
            self.model().layoutChanged.emit()
            self.refresh_height()
        self.scrollTo(index)
        self._open_editor(index, entry, field)

    def scrollTo(self, index, hint=QAbstractItemView.EnsureVisible) -> None:  # noqa: N802 - Qt name
        """Bring a row into view - by moving the PAGE, when the list is part of it.

        Standing at full height inside the page (see follow_content), the list
        has no scrolling of its own, so the inherited scrollTo did nothing at
        all: a clipping dropped in from WhatsApp opened its headline box off
        screen and the person saw nothing happen. The page is what moves.
        """
        # Qt asks for a scroll from inside the QListView constructor, before
        # this object has finished being set up, so the flag may not exist yet.
        if not getattr(self, "_follows_content", False):
            super().scrollTo(index, hint)
            return
        page = page_under(self)
        if page is None or not index.isValid():
            return
        rect = self.visualRect(index)
        if not rect.isValid() or rect.height() <= 0:
            return
        inner = page.widget()
        if inner is None:
            return
        top = self.viewport().mapTo(inner, rect.topLeft())
        bar = page.verticalScrollBar()
        if hint == QAbstractItemView.PositionAtTop:
            # The thing just dropped should be what is looked at, not merely on
            # screen somewhere: put it at the top, with a little of the row
            # above showing so it does not look cut off.
            bar.setValue(max(bar.minimum(), min(bar.maximum(), top.y() - 12)))
            return
        # EnsureVisible: only move if it is actually out of view, and then by
        # as little as will do - a box that is being typed into should not
        # jump around the screen on every Enter.
        seen_top = bar.value()
        seen_bottom = seen_top + page.viewport().height()
        row_top, row_bottom = top.y(), top.y() + rect.height()
        if row_top < seen_top:
            bar.setValue(max(bar.minimum(), row_top - 12))
        elif row_bottom > seen_bottom:
            bar.setValue(min(bar.maximum(),
                             row_bottom - page.viewport().height() + 12))

    def follow_content(self, on: bool = True) -> None:
        """Stand at full height instead of scrolling inside a fixed frame.

        One page, one scrollbar. A list that scrolls inside a page that also
        scrolls gives two bars for one gesture: the wheel stops at the bottom
        of the list rather than carrying on down the page, and getting back to
        the cards at the top means finding the outer bar. The reference the
        user asked this to behave like scrolls as a single document, so the
        list becomes part of that document rather than a window onto its own.

        Qt still only paints the rows actually on screen, so a list ten
        thousand pixels tall costs no more to draw than one screen of it.
        """
        self._follows_content = bool(on)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff if on else Qt.ScrollBarAsNeeded)
        self._match_content_height()

    #: How tall an empty list stands when it has words to show, so the words
    #: can be read. A list standing at its content's height is otherwise one
    #: pixel tall with nothing in it.
    EMPTY_HINT_HEIGHT = 120

    def _match_content_height(self) -> None:
        if not self._follows_content:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            return
        model = self.model()
        tall = 0
        rows = model.rowCount() if model is not None else 0
        for row in range(rows):
            tall += self.sizeHintForRow(row)
        if not rows and getattr(self, "empty_hint", ""):
            tall = self.EMPTY_HINT_HEIGHT
        tall += getattr(self, "_drag_extra", 0)
        tall += 2 * self.frameWidth()
        self.setFixedHeight(max(1, tall))

    def paintEvent(self, event):  # noqa: N802 - Qt name
        super().paintEvent(event)
        if getattr(self, "_gap_now", None):
            self._paint_slots()
        hint = getattr(self, "empty_hint", "")
        model = self.model()
        if not hint or (model is not None and model.rowCount()):
            return
        painter = QPainter(self.viewport())
        painter.setPen(theme.QFAINT)
        painter.drawText(self.viewport().rect().adjusted(24, 12, -24, -12),
                         Qt.AlignCenter | Qt.TextWordWrap, hint)
        painter.end()

    def refresh_height(self) -> None:
        """The list changed, so how tall it stands changed with it."""
        self._match_content_height()

    def mouseMoveEvent(self, event):
        if self._press_point is not None and self._press_hit is not None:
            if self._press_hit.name in ("grip", "group_grip"):
                distance = (event.position().toPoint() - self._press_point).manhattanLength()
                if distance >= QGuiApplication.styleHints().startDragDistance():
                    self._begin_drag()
                    return
        self._update_hover(event.position().toPoint())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self.delegate.hover != (-1, ""):
            self.delegate.hover = (-1, "")
            self.viewport().update()
        super().leaveEvent(event)

    def _update_hover(self, point: QPoint) -> None:
        index = self.indexAt(point)
        found = (-1, "")
        if index.isValid():
            entry = index.data(Qt.UserRole)
            if entry is not None:
                hit = self.delegate.hit_at(self.visualRect(index), entry, point)
                if hit is not None:
                    found = (index.row(), hit.name)
                    self.setToolTip(hit.tooltip)
                else:
                    self.setToolTip("")
        if found != self.delegate.hover:
            self.delegate.hover = found
            self.viewport().update()

    # --------------------------------------------------------------- clicks
    def mousePressEvent(self, event):
        point = event.position().toPoint()
        index = self.indexAt(point)
        self._press_point = point
        self._press_hit = None
        self._press_row = index.row() if index.isValid() else -1

        if not index.isValid():
            self.commit_editor()
            return

        entry = index.data(Qt.UserRole)
        if entry is None:
            return
        hit = self.delegate.hit_at(self.visualRect(index), entry, point)
        self._press_hit = hit

        if event.button() != Qt.LeftButton:
            return

        if entry.kind == ENTRY_GROUP:
            if hit and hit.name != "group_grip":
                self.groupAction.emit(hit.name, entry.group.ident)
            return

        clip_id = entry.row.id
        if hit is None:
            self.commit_editor()
            return

        if hit.name in ("label", "url", "read"):
            self._open_editor(index, entry, hit.name)
            return
        if hit.name == "thumb":
            self.commit_editor()
            self.previewRequested.emit(clip_id)
            return
        if hit.name == "check":
            self.commit_editor()
            self.selectionToggled.emit(
                clip_id, True, bool(event.modifiers() & Qt.ShiftModifier)
            )
            return
        if hit.name == "grip":
            return          # a drag may be starting
        if hit.name == "movepad":
            return

        self.commit_editor()
        self.clipAction.emit(hit.name, clip_id)

    def mouseReleaseEvent(self, event):
        point = event.position().toPoint()
        index = self.indexAt(point)
        if (
            event.button() == Qt.LeftButton
            and index.isValid()
            and index.row() == self._press_row
            and self._press_hit is None
        ):
            entry = index.data(Qt.UserRole)
            if entry is not None and entry.kind == ENTRY_CLIP:
                modifiers = event.modifiers()
                additive = bool(modifiers & (Qt.ControlModifier | Qt.MetaModifier))
                ranged = bool(modifiers & Qt.ShiftModifier)
                if additive or ranged:
                    self.selectionToggled.emit(entry.row.id, additive, ranged)
        self._press_point = None
        self._press_hit = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        if index.isValid():
            entry = index.data(Qt.UserRole)
            if entry is not None and entry.kind == ENTRY_CLIP:
                hit = self.delegate.hit_at(
                    self.visualRect(index), entry, event.position().toPoint()
                )
                if hit is None or hit.name in ("label", "url"):
                    # Double-clicking anywhere soft on the card opens the
                    # headline; double-clicking a box opens that box.
                    self._open_editor(
                        index, entry, hit.name if hit else "label")
                    return
        super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------- editing
    def open_editor_for(self, clip_id: int) -> None:
        """Open the label editor by clip id, resolving the row afresh.

        Rows shift when something is inserted above them, so a stored index can be
        pointing at a group header by the time a deferred call runs.
        """
        row = self.model().entry_row_for_clip(clip_id)
        if row < 0:
            return
        index = self.model().index(row, 0)
        entry = index.data(Qt.UserRole)
        if entry is not None and entry.kind == ENTRY_CLIP:
            # PositionAtTop, not EnsureVisible: a clipping that has just been
            # dropped should be the thing you are looking at, not merely on
            # screen somewhere.
            self.scrollTo(index, QAbstractItemView.PositionAtTop)
            self._open_editor(index, entry)
            QTimer.singleShot(
                60, lambda i=index: self.scrollTo(
                    i, QAbstractItemView.PositionAtTop) if i.isValid() else None)

    def _open_editor(self, index, entry, field: str = "label") -> None:
        if entry is None or entry.kind != ENTRY_CLIP:
            return
        # A call scheduled a moment ago can arrive after the list was emptied
        # and refilled by a newspad switch. Its row is no longer in the list.
        if self.model().row_for(entry.row.id) is not entry.row:
            return
        self.commit_editor()
        rect: QRect = self.delegate.label_rect(self.visualRect(index), entry,
                                               field)
        if not rect.isValid():
            return
        self._editing_field = field
        editor = QLineEdit(self.viewport())
        editor.setGeometry(rect)
        if field == "url":
            editor.setText(entry.row.clip.url)
            editor.setPlaceholderText("Web address — prints under the image")
        elif field == "read":
            editor.setText(str(getattr(entry.row.clip, "ocr_text", "") or ""))
            editor.setPlaceholderText("What the reader made of this picture")
        else:
            editor.setText(entry.row.clip.effective_label)
            editor.setPlaceholderText("Headline — prints above the image")
        editor.selectAll()
        editor.show()
        editor.setFocus()
        editor.returnPressed.connect(self._commit_and_advance)
        editor.installEventFilter(self)
        self._editor = editor
        self._editing_id = entry.row.id
        # The box is a plain child of the viewport at absolute coordinates, so
        # nothing moves it when the row underneath moves. Follow the row.
        self.verticalScrollBar().valueChanged.connect(self._place_editor)

    def _place_editor(self, *_args) -> None:
        """Keep an open headline box on top of the row it belongs to.

        Its geometry was set once, when it opened. Resize the window while typing
        and the box stayed where it was - which at a narrow window meant most of
        the field you were typing into sat off the right-hand edge.
        """
        if self._editor is None or self._editing_id is None:
            return
        row = self.model().entry_row_for_clip(self._editing_id)
        if row < 0:
            return
        entry = self.model().entry_at(row)
        if entry is None or entry.kind != ENTRY_CLIP:
            return
        rect = self.delegate.label_rect(
            self.visualRect(self.model().index(row, 0)), entry,
            getattr(self, "_editing_field", "label"))
        if rect.isValid():
            self._editor.setGeometry(rect)

    def resizeEvent(self, event):  # noqa: N802 - Qt name
        super().resizeEvent(event)
        self._place_editor()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "_editor", None) and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.cancel_editor()
                return True
            if event.key() in (Qt.Key_Down, Qt.Key_Tab):
                self._commit_and_advance()
                return True
            if event.key() == Qt.Key_Up:
                self._commit_and_advance(step=-1)
                return True
        # getattr, as above: the view's own scroll bars reach this filter
        # while __init__ is still running, before there is an _editor.
        if obj is getattr(self, "_editor", None) and event.type() == QEvent.FocusOut:
            # Not every focus-out means the user has finished. A drop from a
            # browser hands focus back to the window a moment after the editor
            # opens, and committing on that closed the box before anything could
            # be typed. Only a genuine move to another widget commits.
            if event.reason() in (
                Qt.ActiveWindowFocusReason, Qt.PopupFocusReason,
                Qt.OtherFocusReason,
            ):
                return super().eventFilter(obj, event)
            self.commit_editor()
        return super().eventFilter(obj, event)

    def editing_id(self):
        """Which clipping's headline box is open, if any."""
        return self._editing_id

    def commit_editor(self) -> None:
        if self._editor is None:
            return
        editor, clip_id = self._editor, self._editing_id
        field = getattr(self, "_editing_field", "label")
        self._editor, self._editing_id = None, None
        text = editor.text().strip()
        editor.removeEventFilter(self)
        editor.deleteLater()
        if clip_id is None:
            return
        # Which box was open decides which field is written. The two are
        # different things - one prints over the picture, one under it - so
        # neither guesses at the other from what was typed.
        if field == "url":
            self.urlEdited.emit(clip_id, text)
        elif field == "read":
            self.readEdited.emit(clip_id, text)
        else:
            self.labelEdited.emit(clip_id, text)

    def cancel_editor(self) -> None:
        if self._editor is None:
            return
        editor = self._editor
        self._editor, self._editing_id = None, None
        editor.removeEventFilter(self)
        editor.deleteLater()

    def settle_editor(self, clip_id: int) -> None:
        """Put away an open headline box on this clipping before something else
        names it.

        Typed in: committed - the person's words win, as their own undo step.
        Untouched: cancelled. Committed untouched, its empty text would be
        taken as "no headline" and hide the caption about to be put there,
        because a box opened on an unnamed clipping starts empty and switching
        to another window does not close it.
        """
        if self._editor is None or self._editing_id != clip_id:
            return
        if self._editor.isModified():
            self.commit_editor()
        else:
            self.cancel_editor()

    def _commit_and_advance(self, step: int = 1) -> None:
        """Enter commits and drops into the next clipping's label box."""
        clip_id = self._editing_id
        self.commit_editor()
        if clip_id is None:
            return
        model = self.model()
        start = model.entry_row_for_clip(clip_id)
        row = start + step
        while 0 <= row < model.rowCount():
            index = model.index(row, 0)
            entry = index.data(Qt.UserRole)
            if entry is not None and entry.kind == ENTRY_CLIP:
                self.scrollTo(index, QAbstractItemView.EnsureVisible)
                QTimer.singleShot(0, lambda i=index, e=entry: self._open_editor(i, e))
                return
            row += step

    # ------------------------------------------------------------ dragging
    def _begin_drag(self) -> None:
        # A drag is aimed at a gap between two rows on screen, and under a lens
        # that gap is not a place in the list: there can be hidden clippings in
        # it, or the two rows can be from opposite ends. So there is nothing to
        # drag until the lens is cleared.
        model = self.model()
        lens = getattr(model, "lens", None)
        if lens is not None and lens.busy:
            return
        index = self.indexAt(self._press_point)
        if not index.isValid():
            return
        entry = index.data(Qt.UserRole)
        model = self.model()
        if entry is None:
            return

        if entry.kind == ENTRY_GROUP:
            ids = [r.id for r in entry.group.rows]
        else:
            clip_id = entry.row.id
            if model.is_selected(clip_id) and len(model.selected) > 1:
                ids = [r.id for r in model.rows if r.id in model.selected]
            else:
                ids = [clip_id]

        grab = self._press_point
        self._press_point = None
        self._press_hit = None

        # THE ROW ITSELF GOES WITH THE POINTER. It used to be a small navy
        # label saying "1 clipping", and a file dragged by its handle with the
        # list folded up showed nothing else moving at all: the file's own
        # header drew no insertion line and no sign of being carried. Now the
        # row that was taken hold of is carried, see-through, at the very
        # place it was held; it is left greyed where it was; and the rows
        # part to show where it will land (_open_gap).
        pixmap, hotspot = self._ghost(index, entry, len(ids), grab)
        rect = self.visualRect(index)
        self._gap_size = max(24, min(rect.height(), self.GAP_MOST))
        self._slot_entry = entry
        if self._follows_content:
            self._drag_extra = self._gap_size
            self._match_content_height()
        self.delegate.dragging_ids = set(ids)
        self.viewport().update()

        mime = QMimeData()
        mime.setData(MIME, ",".join(str(i) for i in ids).encode("ascii"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(pixmap)
        drag.setHotSpot(hotspot)
        drag.exec(Qt.MoveAction)
        self._clear_drop_line()

    #: The widest the carried row is drawn: the width of a card on a wide
    #: window is more than anybody needs to see under a pointer.
    GHOST_WIDEST = 720
    #: The tallest a gap opens, whatever is carried.
    GAP_MOST = 160
    #: Each frame the gap goes this much of the rest of the way, every
    #: GAP_TICK_MS: about a tenth of a second to open or close, eased.
    GAP_EASE = 0.32
    GAP_TICK_MS = 16

    def _ghost(self, index, entry, count: int, grab) -> tuple:
        """The row as it is drawn in the list, lifted off it: see-through,
        with a soft shadow, a stack behind it and the count when more than
        one clipping is carried. (pixmap, the point the pointer holds it by)"""
        rect = self.visualRect(index)
        width = max(160, min(rect.width(), self.GHOST_WIDEST))
        height = max(24, rect.height())
        pad = 18
        stack = 10 if count > 1 else 0
        ratio = max(1.0, float(self.devicePixelRatioF() or 1.0))
        pixmap = QPixmap(int((width + 2 * pad + stack) * ratio),
                         int((height + 2 * pad + stack) * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        option = QStyleOptionViewItem()
        self.initViewItemOption(option)
        option.rect = QRect(pad, pad, width, height)
        # The card as the list draws it inside its row - inset from the row's
        # slot, and for a clipping clear of the file's bracket line - so the
        # shadow and the stack fit the card, not the slot round it.
        card = QRectF(self.delegate.geometry_for(option.rect, entry).card)

        # A soft shadow, lower than the card: lifted, not stuck on.
        painter.setPen(Qt.NoPen)
        for step, alpha in enumerate((22, 16, 11, 7, 4)):
            grow = 2 + 3 * step
            painter.setBrush(QColor(15, 23, 42, alpha))
            painter.drawRoundedRect(
                card.adjusted(-grow, -grow + 5, grow + stack, grow + 5 + stack),
                14 + grow, 14 + grow)
        # More than one: the others, as cards stacked under it.
        for offset in ((stack, stack), (stack / 2, stack / 2)) if stack else ():
            painter.setPen(QPen(QColor(theme.HAIRLINE_STRONG), 1))
            painter.setBrush(QColor(theme.SURFACE))
            painter.drawRoundedRect(card.translated(*offset).adjusted(2, 2, -2, -2),
                                    13, 13)

        # The row, drawn by the list's own painter at the ghost's width -
        # plainly, not greyed and not shifted, whatever the list is doing -
        # and only the card of it.
        kept = (self.delegate.dragging_ids, self.delegate.hover,
                self.delegate.shifts)
        self.delegate.dragging_ids, self.delegate.shifts = set(), []
        self.delegate.hover = (-1, "")
        painter.save()
        try:
            painter.setClipRect(card.adjusted(-1, -1, 1, 1))
            painter.setOpacity(0.9)
            self.delegate.paint(painter, option, index)
        finally:
            painter.restore()
            (self.delegate.dragging_ids, self.delegate.hover,
             self.delegate.shifts) = kept

        if count > 1:
            words = f"{count} clippings"
            font = QFont(self.font())
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)
            wide = painter.fontMetrics().horizontalAdvance(words) + 20
            badge = QRectF(card.right() - wide + stack - 4, card.top() - 9,
                           wide, 22)
            painter.setPen(QPen(QColor("white"), 1.5))
            painter.setBrush(theme.QORANGE)
            painter.drawRoundedRect(badge, 11, 11)
            painter.setPen(QColor("white"))
            painter.drawText(badge, Qt.AlignCenter, words)
        painter.end()

        held = grab if grab is not None else rect.center()
        spot = QPoint(pad + min(max(held.x() - rect.left(), 10), width - 10),
                      pad + min(max(held.y() - rect.top(), 6), height - 6))
        return pixmap, spot

    # --------------------------------------------------------- the gap
    def _drop_place(self, point: QPoint) -> tuple:
        """Where a drop here lands: (the gap's boundary in the list, the place
        in the order). ONE answer for both, so the gap drawn is exactly where
        the clippings go.

        On a clipping: over it or under it, by which half is under the
        pointer. On a folded file's header likewise - before the file, or
        after it; on an open one, before it, since under its header is inside
        it. Anywhere past the last row: the very end."""
        model = self.model()
        rows = model.rowCount() if model is not None else 0
        index = self.indexAt(point)
        if model is None or not index.isValid():
            return rows, len(model.rows) if model is not None else 0
        entry = index.data(Qt.UserRole)
        rect = self.visualRect(index)
        row = index.row()
        below = point.y() > rect.center().y()
        if entry is not None and entry.kind == ENTRY_CLIP:
            step = 1 if below else 0
            return row + step, model.position_of(entry.row.id) + step
        if entry is not None and entry.group is not None:
            group = entry.group
            if below and group.collapsed and group.rows:
                return row + 1, model.position_of(group.rows[-1].id) + 1
            if group.rows:
                return row, model.position_of(group.rows[0].id)
        return rows, len(model.rows)

    def _gap_timer(self) -> QTimer:
        timer = getattr(self, "_gap_clock", None)
        if timer is None:
            timer = QTimer(self)
            timer.setInterval(self.GAP_TICK_MS)
            timer.timeout.connect(self._gap_tick)
            self._gap_clock = timer
        return timer

    def _open_gap(self, boundary: int) -> None:
        """Part the rows at ``boundary``, or close up with -1. Where it was
        closes as the new one opens, so the rows glide rather than jump."""
        if boundary == self._gap_at:
            return
        self._gap_at = boundary
        self._gap_wanted = ({boundary: float(self._gap_size)}
                            if boundary >= 0 and self._gap_size else {})
        if not self._gap_timer().isActive():
            self._gap_timer().start()

    def _gap_tick(self) -> None:
        moving = False
        for key in set(self._gap_now) | set(self._gap_wanted):
            want = self._gap_wanted.get(key, 0.0)
            now = self._gap_now.get(key, 0.0)
            now += (want - now) * self.GAP_EASE
            if abs(want - now) < 0.6:
                now = want
            else:
                moving = True
            if now:
                self._gap_now[key] = now
            else:
                self._gap_now.pop(key, None)
        self._apply_shifts()
        if not moving:
            self._gap_timer().stop()
        self.viewport().update()

    def _apply_shifts(self) -> None:
        """How far down each row is drawn: everything open above it."""
        model = self.model()
        rows = model.rowCount() if model is not None else 0
        if not self._gap_now:
            self.delegate.shifts = []
            return
        shifts, run = [], 0.0
        for row in range(rows + 1):
            run += self._gap_now.get(row, 0.0)
            shifts.append(run)
        self.delegate.shifts = shifts

    def _close_gap_now(self) -> None:
        """Gone at once - the list is about to be laid out afresh."""
        self._gap_timer().stop()
        self._gap_at = -1
        self._gap_now, self._gap_wanted = {}, {}
        self._slot_entry = None
        self.delegate.shifts = []
        if self._drag_extra:
            self._drag_extra = 0
            self._match_content_height()

    def _paint_slots(self) -> None:
        """The open gap: a soft slot with a dashed edge, where it will land."""
        model = self.model()
        rows = model.rowCount() if model is not None else 0
        shifts = self.delegate.shifts
        # As wide as the card of what is carried, at the list's width now.
        left, right = 8, self.viewport().width() - 8
        if self._slot_entry is not None:
            card = self.delegate.geometry_for(
                QRect(0, 0, self.viewport().width(), max(24, self._gap_size)),
                self._slot_entry).card
            left, right = card.left(), card.right()
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, True)
        for boundary, amount in self._gap_now.items():
            if amount < 10 or boundary > rows:
                continue
            above = shifts[boundary] - amount if boundary < len(shifts) else 0.0
            if boundary < rows:
                y = self.visualRect(model.index(boundary, 0)).top() + above
            elif rows:
                y = self.visualRect(model.index(rows - 1, 0)).bottom() + 1 + above
            else:
                y = 0.0
            slot = QRectF(left + 2, y + 5, (right - left) - 4, amount - 10)
            painter.setOpacity(min(1.0, amount / max(1.0, self._gap_size)))
            painter.setPen(QPen(theme.QORANGE, 2, Qt.DashLine))
            painter.setBrush(QColor(232, 121, 47, 26))
            painter.drawRoundedRect(slot, 13, 13)
        painter.end()

    def dragEnterEvent(self, event):
        # An external drop landing on the list is still a drop on the window, so it
        # is accepted here and handed up rather than silently swallowed.
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat(MIME):
            event.acceptProposedAction()
            return
        point = event.position().toPoint()
        self._update_drop_line(point)
        self._autoscroll(point)
        event.acceptProposedAction()

    def _update_drop_line(self, point: QPoint) -> None:
        """Show where the dragged clippings would land: the rows part there."""
        boundary, _place = self._drop_place(point)
        rows = self.model().rowCount()
        # Also said as "against this row, over or under it", for anything
        # that asks the delegate.
        if boundary < rows:
            row, below = boundary, False
        else:
            row, below = (rows - 1, True) if rows else (-1, False)
        self.delegate.drop_row = row
        self.delegate.drop_below = below
        self._open_gap(boundary)

    #: How close to the top or bottom of what is on screen counts as "held
    #: at the edge", in pixels, and how often the page moves while it is.
    DRAG_MARGIN = 56
    DRAG_TICK_MS = 40

    def _autoscroll(self, point: QPoint) -> None:
        """Keep scrolling while the pointer is held near an edge.

        Without this a clipping cannot be dragged past the visible page, which on a
        165-row list means it cannot be moved anywhere useful.

        Standing inside the page (see follow_content) the list has no scrollbar
        of its own, so it is the page that is nudged, and against the edges of
        what is actually on screen rather than the edges of the whole list. And
        it keeps nudging while the pointer is held there: Qt only reports a drag
        when the pointer moves, so a hand held still at the top of the screen
        used to sit there with nothing happening.
        """
        margin = self.DRAG_MARGIN
        page = page_under(self) if getattr(self, "_follows_content", False) else None
        if page is None:
            bar = self.verticalScrollBar()
            height = self.viewport().height()
            y = point.y()
        else:
            bar = page.verticalScrollBar()
            height = page.viewport().height()
            y = self.viewport().mapTo(page.viewport(), point).y()

        if y < margin:
            bar.setValue(bar.value() - max(6, (margin - y) // 2))
        elif y > height - margin:
            bar.setValue(bar.value() + max(6, (y - (height - margin)) // 2))
        else:
            self._drag_edge_timer().stop()
            return
        self._drag_point = point
        if not self._drag_edge_timer().isActive():
            self._drag_edge_timer().start()

    def _drag_edge_timer(self) -> QTimer:
        timer = getattr(self, "_edge_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setInterval(self.DRAG_TICK_MS)
            timer.timeout.connect(self._drag_edge_tick)
            self._edge_timer = timer
        return timer

    def _drag_edge_tick(self) -> None:
        point = getattr(self, "_drag_point", None)
        if point is None:
            self._drag_edge_timer().stop()
            return
        # The pointer has not moved, but the page has, so the row under it is
        # a different row now: keep the drop line honest as well.
        self._autoscroll(point)
        self._update_drop_line(point)

    def dragLeaveEvent(self, event):
        self._drag_edge_timer().stop()
        self._drag_point = None
        self.delegate.drop_row = -1
        # Out of the list - onto a category's bubble, or off the window: the
        # rows close up again, and part again if it comes back.
        self._open_gap(-1)
        self.viewport().update()
        super().dragLeaveEvent(event)

    def _clear_drop_line(self) -> None:
        self.delegate.drop_row = -1
        self.delegate.dragging_ids = set()
        self._close_gap_now()
        self.viewport().update()

    def dropEvent(self, event):
        self._drag_edge_timer().stop()
        self._drag_point = None
        if not event.mimeData().hasFormat(MIME):
            window = self.window()
            from .sentiment_board import CARD_MIME

            if event.mimeData().hasFormat(CARD_MIME):
                # A card dragged off the board is not something to import.
                # Handed on, it came back as "Nothing to add" over a drop
                # that was only let go in the wrong place.
                event.ignore()
                return
            event.acceptProposedAction()
            if (self.drop_section is not None
                    and hasattr(window, "accept_payload_into")):
                window.accept_payload_into(event.mimeData(), self.drop_section)
            elif hasattr(window, "accept_payload"):
                window.accept_payload(event.mimeData())
            return
        raw = bytes(event.mimeData().data(MIME)).decode("ascii")
        ids = [int(part) for part in raw.split(",") if part]

        # Where the gap was drawn, by the same rule.
        _boundary, target = self._drop_place(event.position().toPoint())

        self._clear_drop_line()
        self.reorderRequested.emit(ids, target)
        event.acceptProposedAction()
