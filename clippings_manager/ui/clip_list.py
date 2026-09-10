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
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QDrag, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QLineEdit, QListView

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

        self._press_point: QPoint | None = None
        self._press_hit = None
        self._press_row = -1
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

    def _match_content_height(self) -> None:
        if not self._follows_content:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            return
        model = self.model()
        tall = 0
        if model is not None:
            for row in range(model.rowCount()):
                tall += self.sizeHintForRow(row)
        tall += 2 * self.frameWidth()
        self.setFixedHeight(max(1, tall))

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

        if hit.name in ("label", "url"):
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
        if obj is self._editor and event.type() == QEvent.FocusOut:
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
        else:
            self.labelEdited.emit(clip_id, text)

    def cancel_editor(self) -> None:
        if self._editor is None:
            return
        editor = self._editor
        self._editor, self._editing_id = None, None
        editor.removeEventFilter(self)
        editor.deleteLater()

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

        self._press_point = None
        self._press_hit = None
        self.delegate.dragging_ids = set(ids)
        self.viewport().update()

        mime = QMimeData()
        mime.setData(MIME, ",".join(str(i) for i in ids).encode("ascii"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self._drag_pixmap(len(ids)))
        drag.exec(Qt.MoveAction)
        self._clear_drop_line()

    def _drag_pixmap(self, count: int) -> QPixmap:
        text = f"{count} clipping" + ("s" if count != 1 else "")
        pixmap = QPixmap(150, 34)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.QNAVY)
        painter.drawRoundedRect(0, 0, 150, 34, 10, 10)
        painter.setPen(Qt.white)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        painter.end()
        return pixmap

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
        """Show where the dragged clippings would land."""
        index = self.indexAt(point)
        if index.isValid():
            rect = self.visualRect(index)
            row, below = index.row(), point.y() > rect.center().y()
        elif self.model().rowCount():
            row, below = self.model().rowCount() - 1, True
        else:
            row, below = -1, False
        if (row, below) != (self.delegate.drop_row, self.delegate.drop_below):
            self.delegate.drop_row = row
            self.delegate.drop_below = below
            self.viewport().update()

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
        self.viewport().update()
        super().dragLeaveEvent(event)

    def _clear_drop_line(self) -> None:
        self.delegate.drop_row = -1
        self.delegate.dragging_ids = set()
        self.viewport().update()

    def dropEvent(self, event):
        self._drag_edge_timer().stop()
        self._drag_point = None
        if not event.mimeData().hasFormat(MIME):
            window = self.window()
            event.acceptProposedAction()
            if hasattr(window, "accept_payload"):
                window.accept_payload(event.mimeData())
            return
        raw = bytes(event.mimeData().data(MIME)).decode("ascii")
        ids = [int(part) for part in raw.split(",") if part]
        model = self.model()

        point = event.position().toPoint()
        index = self.indexAt(point)
        if index.isValid():
            entry = index.data(Qt.UserRole)
            rect = self.visualRect(index)
            below = point.y() > rect.center().y()
            if entry is not None and entry.kind == ENTRY_CLIP:
                target = model.position_of(entry.row.id) + (1 if below else 0)
            elif entry is not None and entry.group is not None:
                first = entry.group.rows[0].id if entry.group.rows else None
                target = model.position_of(first) if first is not None else len(model.rows)
            else:
                target = len(model.rows)
        else:
            target = len(model.rows)

        self._clear_drop_line()
        self.reorderRequested.emit(ids, target)
        event.acceptProposedAction()
