"""The sentiment interface: six divisions, four columns of coverage.

The standard report answers "what goes in today's newspad, in what order". This
answers a different question: for a given division, how did the day's coverage
split between positive, neutral, negative and digital.

Most of the sorting is already done by the time a clipping arrives. The division
comes from the file name and the category from the headings inside the document, so
a morning's imports drop into the right columns on their own. Dragging a card to
another column is a correction, not the main job.

The four columns are four virtualised list views over the same clippings the
standard report uses - there is one set of clippings in this application, not two -
so a name typed in either place is the same name.
"""

from __future__ import annotations


from typing import Optional

from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QMimeData,
    QModelIndex,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    Signal,
    QTimer,
)
from PySide6.QtGui import QColor, QDrag, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from ..core import sentiment
from ..core.models import Section
from . import icons, theme
from .fluid import ElidedLabel, FlowLayout
from .layout_card import HeadingLayoutCard
from .scroll import (
    WHEEL_PIXELS,
    PageScroll,
    SideScroll,
    WideScroll,
    smooth,
)
from .sentiment_cover_card import SentimentCoverCard

# Wording taken from the live prototype so the two read the same.
COLUMN_META = {
    "Positive": {
        "title": "Positive News (+)",
        "subtitle": "Achievements, safety, passenger praise",
        "empty": "No positive clips yet",
        "icon": "thumbs_up",
        "hint": "Click or drag & drop PDF / Word / image clippings,\n"
                "or hover and press Ctrl+V to paste a screenshot",
    },
    "Neutral": {
        "title": "Neutral News (●)",
        "subtitle": "Informational updates, schedules, operations",
        "empty": "No neutral clips yet",
        "icon": "minus",
        "hint": "Click or drag & drop PDF / Word / image clippings,\n"
                "or hover and press Ctrl+V to paste a screenshot",
    },
    "Negative": {
        "title": "Negative News (−)",
        "subtitle": "Delays, complaints, track/operational issues",
        "empty": "No negative clips yet",
        "icon": "thumbs_down",
        "hint": "Click or drag & drop PDF / Word / image clippings,\n"
                "or hover and press Ctrl+V to paste a screenshot",
    },
    "Digital": {
        "title": "Digital News",
        "subtitle": "Web portals, social media & online coverage",
        "empty": "No digital news clips yet",
        "icon": "globe",
        "hint": "Upload a news screenshot or hover and press Ctrl+V to paste one,\n"
                "then paste the article link onto the card",
    },
}
CARD_MIME = "application/x-clippings-cards"
# A card is a tile now, not a row: the clipping sits in its own framed box with
# the headline box directly under it, which is where the eye expects to type.
CARD_WIDTH = 320
CARD_PAD = 10
CARD_HEAD = 24
CARD_IMAGE = 150
CARD_TITLE = 30
CARD_ACTIONS = 26
# Room for a second strip under the first, always. What sits on it is either the
# other field or the small button that asks for it, and both are the same height
# - so a card never changes size when the button is pressed, and the field turns
# up exactly where the button was.
CARD_SECOND = 30
CARD_HEIGHT = (CARD_PAD * 2 + CARD_HEAD + CARD_IMAGE + CARD_TITLE + CARD_SECOND
               + CARD_ACTIONS + 14)
CARD_GAP = 10
THUMB = 76
ALL_DIVISIONS = "__all__"


# --------------------------------------------------------------------- model


class ColumnModel(QAbstractListModel):
    """The clippings currently sitting in one column."""

    def __init__(self, section: Section, parent=None):
        super().__init__(parent)
        self.section = section
        self.rows: list = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        if role == Qt.UserRole:
            return self.rows[index.row()]
        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemIsDropEnabled
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled

    def set_rows(self, rows: list) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()


# ------------------------------------------------------------------ painting


def strips_for(clip, section) -> tuple:
    """Which of the two strips this card shows: (headline, address).

    The column decides which one is always there. Positive, Neutral and Negative
    are newspaper cuttings and are identified by their headline; Digital is a
    screenshot of a web page and is identified by where it came from, so there
    the address is the one that is always on the card.

    The other strip appears once it has something in it, or once it has been
    asked for - which is what the small button on the second line does.
    """
    web = section is Section.DIGITAL
    has_title = bool(clip.effective_label.strip()) or bool(
        getattr(clip, "show_title_box", False))
    has_url = bool((clip.url or "").strip()) or bool(
        getattr(clip, "show_url_box", False))
    if web:
        return has_title, True
    return True, has_url


def card_geometry(rect: QRect) -> dict:
    """Every part of a card, named. Paint and hit-test both read this."""
    card = QRect(rect.left() + 8, rect.top() + CARD_GAP // 2,
                 max(140, rect.width() - 18), CARD_HEIGHT)
    inner = card.adjusted(CARD_PAD, CARD_PAD, -CARD_PAD, -CARD_PAD)

    y = inner.top()
    head = QRect(inner.left(), y, inner.width(), CARD_HEAD)
    grip = QRect(head.left(), head.top() + 4, 12, 16)
    check = QRect(grip.right() + 6, head.top() + 4, 16, 16)
    badge = QRect(check.right() + 7, head.top() + 3, 30, 18)
    caption = QRect(badge.right() + 7, head.top() + 3,
                    max(20, head.right() - badge.right() - 7), 18)

    y = head.bottom() + 6
    image = QRect(inner.left(), y, inner.width(), CARD_IMAGE)

    y = image.bottom() + 8
    title = QRect(inner.left(), y, inner.width(), CARD_TITLE - 6)
    clear = QRect(title.right() - 22, title.top() + 3, 18, 18)

    y = title.bottom() + 6
    second = QRect(inner.left(), y, inner.width(), CARD_TITLE - 6)
    clear_second = QRect(second.right() - 22, second.top() + 3, 18, 18)
    # The button that asks for the second field sits at the left of the line the
    # field will occupy, so pressing it does not move anything.
    add = QRect(second.left(), second.top() + 3, 92, 18)

    y = second.bottom() + 8
    actions = QRect(inner.left(), y, inner.width(), CARD_ACTIONS - 6)

    chips = []
    x = actions.left() + 38
    for name, width in (("Neu", 40), ("Neg", 40), ("Dig", 40)):
        chips.append((name, QRect(x, actions.top(), width, 20)))
        x += width + 5

    icons_x = actions.right()
    buttons = []
    for name in ("delete", "rotate"):
        icons_x -= 22
        buttons.append((name, QRect(icons_x, actions.top(), 20, 20)))

    return {
        "card": card, "head": head, "grip": grip, "check": check,
        "badge": badge, "caption": caption, "image": image, "title": title,
        "clear": clear, "second": second, "clear_second": clear_second,
        "add": add, "actions": actions, "chips": chips, "buttons": buttons,
    }


class CardDelegate(QStyledItemDelegate):
    """One clipping as a tile: the picture in a frame, the headline below it."""

    def __init__(self, section: Section, parent=None):
        super().__init__(parent)
        self.section = section
        self.selected_ids: set[int] = set()
        self.editing_id: Optional[int] = None
        # Which of the two strips is being typed into, so the other one goes on
        # being painted while the editor is open over its neighbour.
        self.editing_field: str = ""
        self.hover_hit: Optional[str] = None

    def sizeHint(self, option, index) -> QSize:
        # Capped at CARD_WIDTH so a focused column lays the cards out as a grid
        # instead of stretching one across the whole page - but never wider than
        # the column it is in. A fixed 320 meant the delete and rotate buttons,
        # which are anchored to the card's right edge, sat outside the viewport
        # on a narrow window: painted, but past every mouse coordinate that
        # exists, and with horizontal scrolling off there was no way to them.
        view = self.parent()
        room = CARD_WIDTH
        if isinstance(view, QAbstractItemView):
            room = min(CARD_WIDTH, max(180, view.viewport().width() - 4))
        return QSize(room, CARD_HEIGHT + CARD_GAP)

    # ------------------------------------------------------------ hit test
    def fields(self) -> tuple:
        """(the strip this column is for, the other one)."""
        return (("url", "title") if self.section is Section.DIGITAL
                else ("title", "url"))

    def hit_at(self, rect: QRect, point: QPoint, clip=None) -> Optional[str]:
        geometry = card_geometry(rect)
        for name in ("grip", "check", "image"):
            if geometry[name].contains(point):
                return name

        first, second = self.fields()
        title_on, url_on = ((True, True) if clip is None
                            else strips_for(clip, self.section))
        showing = {"title": title_on, "url": url_on}

        # The clear crosses sit inside their strips, so they are asked about
        # first or they could never be hit.
        if geometry["clear"].contains(point):
            return f"clear:{first}"
        if showing[second]:
            if geometry["clear_second"].contains(point):
                return f"clear:{second}"
            if geometry["second"].contains(point):
                return f"field:{second}"
        elif geometry["add"].contains(point):
            return f"add:{second}"
        if geometry["title"].contains(point):
            return f"field:{first}"

        for name, box in geometry["chips"]:
            if box.contains(point):
                return f"move:{name}"
        for name, box in geometry["buttons"]:
            if box.contains(point):
                return name
        return None

    def field_rect(self, rect: QRect, field: str = "") -> QRect:
        """Where a named strip is drawn, for the editor to sit exactly on it."""
        geometry = card_geometry(rect)
        first, _second = self.fields()
        return geometry["title"] if (not field or field == first) \
            else geometry["second"]

    # --------------------------------------------------------------- paint
    def _paint_strip(self, painter, box: QRect, cross: QRect, field: str,
                     clip) -> None:
        """One field strip: its tag, what is in it, and the cross to empty it."""
        font = painter.font()
        painter.setPen(QPen(QColor("#E7EAF0"), 1))
        painter.setBrush(QColor(theme.PANEL))
        painter.drawRoundedRect(QRectF(box).adjusted(0.5, 0.5, -0.5, -0.5), 7, 7)
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#9AA4AB"))
        painter.drawText(QRect(box.left() + 8, box.top(), 34, box.height()),
                         Qt.AlignVCenter | Qt.AlignLeft,
                         "LINK:" if field == "url" else "TITLE:")
        font.setPixelSize(11)
        font.setBold(False)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        if field == "url":
            shown = (clip.url or "").strip()
            name = shown or "click to paste the article link"
            ink = QColor("#1D4ED8")
        else:
            shown = clip.effective_label
            name = shown or ("title on the clipping" if clip.title_in_image
                             else "click to add a headline")
            ink = theme.QINK
        painter.setPen(ink if shown else QColor("#9AA4AB"))
        room = QRect(box.left() + 46, box.top(), box.width() - 74, box.height())
        painter.drawText(room, Qt.AlignVCenter | Qt.AlignLeft,
                         metrics.elidedText(name, Qt.ElideRight, room.width()))
        if shown:
            icons.close_x(painter, QRectF(cross).adjusted(4, 4, -4, -4),
                          QColor("#9AA4AB"), width=1.6)

    def _paint_add(self, painter, box: QRect, field: str,
                   hovered: bool) -> None:
        """The small button that asks for the strip this card has not got."""
        ink = QColor("#1D4ED8") if field == "url" else QColor(theme.NAVY)
        painter.setPen(QPen(ink, 1))
        painter.setBrush(QColor("#EFF4FF") if hovered else QColor(theme.SURFACE))
        painter.drawRoundedRect(QRectF(box).adjusted(0.5, 0.5, -0.5, -0.5), 9, 9)
        mark = QRectF(box.left() + 5, box.center().y() - 5.5, 11, 11)
        drawer = icons.globe if field == "url" else icons.type_letter
        drawer(painter, mark, ink)
        font = painter.font()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(ink)
        painter.drawText(
            QRectF(mark.right() + 4, box.top(), box.width() - 22, box.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            "Add URL" if field == "url" else "Add title")

    def paint(self, painter: QPainter, option, index) -> None:
        row = index.data(Qt.UserRole)
        if row is None:
            return
        clip = row.clip
        style = theme.SENTIMENT_STYLES[self.section.value]
        geometry = card_geometry(option.rect)
        card = geometry["card"]

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        selected = row.id in self.selected_ids
        painter.setPen(QPen(QColor(style["colour"]) if selected
                            else QColor("#E7EAF0"), 2 if selected else 1))
        painter.setBrush(QColor(theme.SURFACE))
        painter.drawRoundedRect(QRectF(card).adjusted(0.5, 0.5, -0.5, -0.5), 13, 13)

        if not clip.include:
            painter.setOpacity(0.45)

        font = painter.font()

        # --- the header row ------------------------------------------------
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#CBD5E1"))
        for column in range(2):
            for dot in range(3):
                painter.drawEllipse(
                    QPointF(geometry["grip"].left() + 2 + column * 6,
                            geometry["grip"].top() + 3 + dot * 5), 1.4, 1.4)

        box = geometry["check"]
        painter.setPen(QPen(QColor(style["colour"]) if selected
                            else QColor("#CBD5E1"), 1.5))
        painter.setBrush(QColor(style["colour"]) if selected
                         else QColor(theme.SURFACE))
        painter.drawRoundedRect(QRectF(box).adjusted(1, 1, -1, -1), 4, 4)
        if selected:
            icons.check(painter, QRectF(box).adjusted(3, 3, -3, -3),
                        QColor("#FFFFFF"), width=2.0)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(style["bg"]))
        painter.drawRoundedRect(QRectF(geometry["badge"]), 8, 8)
        font.setPixelSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(style["badge"]))
        painter.drawText(geometry["badge"], Qt.AlignCenter,
                         f"#{index.row() + 1}")

        font.setPixelSize(10)
        font.setBold(False)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        source = row.source_name or clip.source_ref or ""
        painter.setPen(QColor("#9AA4AB"))
        painter.drawText(
            geometry["caption"], Qt.AlignVCenter | Qt.AlignLeft,
            metrics.elidedText(str(source), Qt.ElideMiddle,
                               geometry["caption"].width()))

        # --- the picture, in its own frame ----------------------------------
        image = geometry["image"]
        painter.setPen(QPen(QColor("#E7EAF0"), 1))
        painter.setBrush(QColor(theme.THUMB_BG))
        painter.drawRoundedRect(QRectF(image).adjusted(0.5, 0.5, -0.5, -0.5), 9, 9)
        pixmap = row.thumbnail
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(image.size() - QSize(10, 10),
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation)
            target = QRect(0, 0, scaled.width(), scaled.height())
            target.moveCenter(image.center())
            painter.drawPixmap(target, scaled)

        tag = QRect(image.right() - 48, image.bottom() - 20, 42, 15)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 140))
        painter.drawRoundedRect(QRectF(tag), 4, 4)
        font.setPixelSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(tag, Qt.AlignCenter,
                         "LINK" if clip.url else "IMAGE")

        # --- the two strips --------------------------------------------------
        # Digital coverage is a screenshot of a web page, and what has to travel
        # with it is the address, not a headline - so that column leads with the
        # link and the other three lead with the headline. Whichever is not the
        # column's own is on the line underneath, or is one button away.
        first, second = self.fields()
        title_on, url_on = strips_for(clip, self.section)
        showing = {"title": title_on, "url": url_on}
        places = (
            (first, geometry["title"], geometry["clear"]),
            (second, geometry["second"], geometry["clear_second"]),
        )
        for field, box, cross in places:
            if not showing[field]:
                continue
            if self.editing_id == row.id and self.editing_field == field:
                continue          # a real text box is sitting on top of it
            self._paint_strip(painter, box, cross, field, clip)
        if not showing[second]:
            self._paint_add(painter, geometry["add"], second,
                            self.hover_hit == f"add:{second}")

        # --- move chips and the two actions ---------------------------------
        actions = geometry["actions"]
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#9AA4AB"))
        painter.drawText(QRect(actions.left(), actions.top(), 34,
                               actions.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, "Move:")

        for name, box in geometry["chips"]:
            other = {"Neu": "Neutral", "Neg": "Negative", "Dig": "Digital"}[name]
            if other == self.section.value:
                continue
            chip = theme.SENTIMENT_STYLES[other]
            hovered = self.hover_hit == f"move:{name}"
            painter.setPen(QPen(QColor(chip["colour"]), 1))
            painter.setBrush(QColor(chip["bg"]) if not hovered
                             else QColor(chip["colour"]))
            painter.drawRoundedRect(QRectF(box), 8, 8)
            painter.setPen(QColor("#FFFFFF") if hovered
                           else QColor(chip["badge"]))
            painter.drawText(box, Qt.AlignCenter, name)

        for name, box in geometry["buttons"]:
            hovered = self.hover_hit == name
            colour = (QColor(theme.DANGER) if name == "delete"
                      else QColor(theme.NAVY))
            drawer = icons.trash if name == "delete" else icons.rotate
            drawer(painter, QRectF(box).adjusted(3, 3, -3, -3),
                   colour if hovered else QColor("#9AA4AB"))

        painter.setOpacity(1.0)
        painter.restore()


# ------------------------------------------------------------------- column


class SentimentColumn(QListView):
    """One of the four columns. Accepts cards dragged from the others."""

    cardsDropped = Signal(list, str)      # clip ids, target section value
    cardOpened = Signal(int)
    cardToggled = Signal(int, bool)
    titleEdited = Signal(int, str)       # clip id, new headline
    urlEdited = Signal(int, str)         # clip id, new web address
    cardDeleted = Signal(int)
    cardRotated = Signal(int)

    def __init__(self, section: Section, parent=None):
        super().__init__(parent)
        # The stylesheet strips the application font's family list off
        # every item view, and the Devanagari fallback goes with it.
        theme.apply_font(self)
        self.section = section
        self.setModel(ColumnModel(section, self))
        self.delegate = CardDelegate(section, self)
        self.setItemDelegate(self.delegate)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QListView.NoFrame)
        self.setResizeMode(QListView.Adjust)
        self.setUniformItemSizes(True)
        # A wrapping grid of fixed-width tiles. Movement stays Static: the
        # column does its own drag and drop and must not let Qt move items.
        self.setViewMode(QListView.IconMode)
        self.setMovement(QListView.Static)
        self.setWrapping(True)
        self.setSpacing(2)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self._press: Optional[QPoint] = None
        self._hot = False
        self._editor: Optional[QLineEdit] = None
        self._editing_id: Optional[int] = None
        self._editing_field: str = ""

        # After the fields above, not before: asking for the scrollbar delivers
        # an event straight into this view's own event filter, which reads them.
        # Left to itself a column moved 7px a notch - a card is 264px, so a wheel
        # spin barely stirred it.
        self.verticalScrollBar().setSingleStep(WHEEL_PIXELS // 2)
        smooth(self)

        style = theme.SENTIMENT_STYLES[section.value]
        self.setObjectName(f"SentList{section.value}")
        self.setStyleSheet(
            f"#SentList{section.value} {{ background: {style['bg']}; border: none;"
            f" border-bottom-left-radius: 15px; border-bottom-right-radius: 15px; }}"
            f"#SentList{section.value} QScrollBar:vertical {{ background: transparent;"
            f" width: 10px; margin: 6px 2px 6px 0; }}"
            f"#SentList{section.value} QScrollBar::handle:vertical {{"
            f" background: {style['line']}; border-radius: 5px; min-height: 36px; }}"
            f"#SentList{section.value} QScrollBar::handle:vertical:hover {{"
            f" background: {style['colour']}; }}"
            f"#SentList{section.value} QScrollBar::add-line,"
            f"#SentList{section.value} QScrollBar::sub-line {{ height: 0; }}"
            f"#SentList{section.value} QScrollBar::add-page,"
            f"#SentList{section.value} QScrollBar::sub-page {{ background: none; }}"
        )
        self.setContentsMargins(0, 0, 0, 0)

    # -- dragging out ------------------------------------------------------
    def mousePressEvent(self, event):
        point = event.position().toPoint()
        self._press = point
        index = self.indexAt(point)
        row = index.data(Qt.UserRole) if index.isValid() else None
        if row is None or event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)

        hit = self.delegate.hit_at(self.visualRect(index), point, row.clip)
        if hit and hit.startswith("field:"):
            self.open_editor_for(row.id, hit.split(":", 1)[1])
            return
        if hit and hit.startswith("clear:"):
            self.commit_editor()
            field = hit.split(":", 1)[1]
            signal = self.urlEdited if field == "url" else self.titleEdited
            signal.emit(row.id, "")
            return
        if hit and hit.startswith("add:"):
            # Asking for the other strip. The flag is only about what the card
            # shows, so it is set here rather than pushed onto the undo stack -
            # nothing about the report has changed until something is typed.
            self.commit_editor()
            field = hit.split(":", 1)[1]
            if field == "url":
                row.clip.show_url_box = True
            else:
                row.clip.show_title_box = True
            self.viewport().update()
            self.open_editor_for(row.id, field)
            return
        if hit == "check":
            self.commit_editor()
            self.cardToggled.emit(row.id, True)
            return
        if hit == "delete":
            self.commit_editor()
            self.cardDeleted.emit(row.id)
            return
        if hit == "rotate":
            self.commit_editor()
            self.cardRotated.emit(row.id)
            return
        if hit and hit.startswith("move:"):
            self.commit_editor()
            target = {"Neu": "Neutral", "Neg": "Negative",
                      "Dig": "Digital"}[hit.split(":", 1)[1]]
            self.cardsDropped.emit([row.id], target)
            return
        self.commit_editor()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        index = self.indexAt(event.position().toPoint())
        row = index.data(Qt.UserRole) if index.isValid() else None
        if row is not None:
            self.cardOpened.emit(row.id)
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            point = event.position().toPoint()
            index = self.indexAt(point)
            row = index.data(Qt.UserRole) if index.isValid() else None
            hit = (self.delegate.hit_at(self.visualRect(index), point,
                                        row.clip if row is not None else None)
                   if index.isValid() else None)
            if hit != self.delegate.hover_hit:
                self.delegate.hover_hit = hit
                self.viewport().update()
            self.setCursor(Qt.PointingHandCursor if hit else Qt.ArrowCursor)
        if self._press is None or not (event.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(event)
        if (event.position().toPoint() - self._press).manhattanLength() < 12:
            return super().mouseMoveEvent(event)

        index = self.indexAt(self._press)
        row = index.data(Qt.UserRole) if index.isValid() else None
        if row is None:
            return super().mouseMoveEvent(event)
        grabbed = self.delegate.hit_at(self.visualRect(index), self._press,
                                       row.clip)
        if grabbed in ("check", "delete", "rotate") or (
                grabbed and grabbed.split(":", 1)[0] in
                ("field", "clear", "add")):
            return super().mouseMoveEvent(event)

        self._press = None
        mime = QMimeData()
        mime.setData(CARD_MIME, str(row.id).encode("ascii"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self._chip(row))
        drag.exec(Qt.MoveAction)

    # -- typing the headline ----------------------------------------------
    def open_editor_for(self, clip_id: int, field: str = "") -> None:
        """Put a real text box over one of the card's strips and focus it."""
        for row in range(self.model().rowCount()):
            index = self.model().index(row, 0)
            entry = index.data(Qt.UserRole)
            if entry is None or entry.id != clip_id:
                continue
            self.commit_editor()
            self.scrollTo(index, QAbstractItemView.EnsureVisible)
            wanted = field or self.delegate.fields()[0]
            rect = self.delegate.field_rect(self.visualRect(index), wanted)
            editor = QLineEdit(self.viewport())
            editor.setGeometry(rect)
            web = wanted == "url"
            editor.setText((entry.clip.url or "").strip() if web
                           else entry.clip.effective_label)
            editor.setPlaceholderText(
                "Paste the article link" if web
                else "Headline for this clipping")
            editor.setStyleSheet(
                f"background: {theme.SURFACE}; border: 2px solid"
                f" {theme.SENTIMENT_STYLES[self.section.value]['colour']};"
                f" border-radius: 7px; padding: 2px 8px; font-size: 11px;"
                f" color: {theme.INK};"
            )
            editor.selectAll()
            editor.show()
            editor.setFocus()
            editor.returnPressed.connect(self.commit_editor)
            editor.installEventFilter(self)
            self._editor = editor
            self._editing_id = clip_id
            self._editing_field = wanted
            self.delegate.editing_id = clip_id
            self.delegate.editing_field = wanted
            self.viewport().update()
            return

    def editing_id(self):
        return self._editing_id

    def commit_editor(self) -> None:
        if self._editor is None:
            return
        editor, clip_id = self._editor, self._editing_id
        field = self._editing_field or self.delegate.fields()[0]
        self._editor, self._editing_id, self._editing_field = None, None, ""
        self.delegate.editing_id = None
        self.delegate.editing_field = ""
        text = editor.text().strip()
        editor.removeEventFilter(self)
        editor.deleteLater()
        self.viewport().update()
        if clip_id is not None:
            signal = self.urlEdited if field == "url" else self.titleEdited
            signal.emit(clip_id, text)

    def cancel_editor(self) -> None:
        if self._editor is None:
            return
        editor = self._editor
        self._editor, self._editing_id, self._editing_field = None, None, ""
        self.delegate.editing_id = None
        self.delegate.editing_field = ""
        editor.removeEventFilter(self)
        editor.deleteLater()
        self.viewport().update()

    def eventFilter(self, obj, event):
        if obj is getattr(self, "_editor", None) and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.cancel_editor()
                return True
        if obj is self._editor and event.type() == QEvent.FocusOut:
            # A drop hands focus back to the window a moment after the box
            # opens; committing on that would close it before anything is typed.
            if event.reason() in (Qt.ActiveWindowFocusReason,
                                  Qt.PopupFocusReason, Qt.OtherFocusReason):
                return super().eventFilter(obj, event)
            self.commit_editor()
        return super().eventFilter(obj, event)

    def _chip(self, row) -> QPixmap:
        style = theme.SENTIMENT_STYLES[self.section.value]
        pixmap = QPixmap(190, 34)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(style["colour"]))
        painter.drawRoundedRect(0, 0, 190, 34, 9, 9)
        painter.setPen(Qt.white)
        font = painter.font()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        name = row.clip.effective_label or "Clipping"
        painter.drawText(pixmap.rect().adjusted(10, 0, -10, 0),
                         Qt.AlignVCenter | Qt.AlignLeft,
                         QFontMetrics(font).elidedText(name, Qt.ElideRight, 170))
        painter.end()
        return pixmap

    # -- dropping in -------------------------------------------------------
    def _wants(self, mime) -> bool:
        return mime.hasFormat(CARD_MIME) or mime.hasUrls() or mime.hasImage()

    def dragEnterEvent(self, event):
        if self._wants(event.mimeData()):
            self._hot = True
            self.viewport().update()
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self._wants(event.mimeData()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._hot = False
        self.viewport().update()

    def dropEvent(self, event):
        self._hot = False
        self.viewport().update()
        mime = event.mimeData()
        if mime.hasFormat(CARD_MIME):
            try:
                clip_id = int(bytes(mime.data(CARD_MIME)).decode("ascii"))
            except ValueError:
                return
            event.acceptProposedAction()
            self.cardsDropped.emit([clip_id], self.section.value)
            return
        window = self.window()
        if hasattr(window, "accept_payload_into"):
            event.acceptProposedAction()
            window.accept_payload_into(mime, self.section)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._hot:
            style = theme.SENTIMENT_STYLES[self.section.value]
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(QColor(style["colour"]), 3, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(
                QRectF(self.viewport().rect()).adjusted(4, 4, -4, -4), 10, 10
            )
            painter.end()
        elif not self.model().rowCount():
            meta = COLUMN_META[self.section.value]
            style = theme.SENTIMENT_STYLES[self.section.value]
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.Antialiasing, True)
            rect = self.viewport().rect()

            disc = QRectF(rect.center().x() - 22, rect.top() + 54, 44, 44)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(style["colour"]))
            painter.drawEllipse(disc)
            drawer = getattr(icons, meta["icon"], None)
            if drawer is not None:
                drawer(painter, disc.adjusted(11, 11, -11, -11), QColor("white"))

            font = painter.font()
            font.setPixelSize(13)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(theme.QINK)
            painter.drawText(QRect(rect.left(), rect.top() + 110, rect.width(), 20),
                             Qt.AlignHCenter | Qt.AlignTop, meta["empty"])

            font.setPixelSize(11)
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(theme.QFAINT)
            painter.drawText(QRect(rect.left() + 16, rect.top() + 134,
                                   rect.width() - 32, 62),
                             Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                             meta["hint"])
            painter.end()


# -------------------------------------------------------------------- board


class SentimentBoard(QWidget):
    """The whole sentiment interface: division bar, totals, four columns."""

    assignRequested = Signal(list, str)   # clip ids, section value
    previewRequested = Signal(int)
    divisionChanged = Signal(str)
    addRequested = Signal(str)            # section value to import into
    exportRequested = Signal(str)   # "pdf" | "docx" | "jpeg" | "burned"
    clearRequested = Signal(str)    # the division code to empty
    titleEdited = Signal(int, str)
    urlEdited = Signal(int, str)
    cardDeleted = Signal(int)
    cardRotated = Signal(int)
    optionsChanged = Signal()

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.divisions = sentiment.divisions(config)
        self.active = self.divisions[0].code if self.divisions else ""
        self.focused: Optional[str] = None
        self._rows: list = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 14, 20, 12)
        outer.setSpacing(13)

        # The top matter is part of the same document as the columns below it:
        # one scrollbar for the whole board, the way a web page scrolls. It used
        # to have a scroll of its own inside a half of the window, which meant
        # one turn of the wheel did different things depending on where the
        # pointer happened to be, and coming back to the cover card meant finding
        # a second scrollbar.
        top = QWidget()
        top.setObjectName("BoardTop")
        top.setStyleSheet("#BoardTop { background: transparent; }")
        stack = QVBoxLayout(top)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.setSpacing(13)
        stack.addWidget(self._build_heading())
        stack.addWidget(self._build_division_bar())
        stack.addWidget(self._build_totals())
        self.cover = SentimentCoverCard()
        self.cover.changed.connect(self._mirror_cover_switch)
        self.cover.foldChanged.connect(self._cover_folded)
        stack.addWidget(self.cover)
        # Everything above the columns is set up once a day; the columns are
        # where the work happens. They sit one above the other on a single page,
        # and the wheel takes the set-up out of the way when it is not wanted.
        settings = QWidget()
        settings.setObjectName("BoardSettings")
        settings.setStyleSheet("#BoardSettings { background: transparent; }")
        settings_stack = QVBoxLayout(settings)
        settings_stack.setContentsMargins(0, 0, 0, 0)
        settings_stack.setSpacing(11)
        # Wider than the window is allowed; taller than itself is not. See
        # WideScroll - it is what keeps one wheel scrolling one page while the
        # set-up is still free to be 1760px wide.
        self.settings_scroll = WideScroll("BoardScroll", top)
        settings_stack.addWidget(self.settings_scroll)

        work = QWidget()
        work.setObjectName("BoardWork")
        work.setStyleSheet("#BoardWork { background: transparent; }")
        work_stack = QVBoxLayout(work)
        work_stack.setContentsMargins(0, 0, 0, 0)
        work_stack.setSpacing(9)
        work_stack.addWidget(self._build_column_bar())
        # Directly under the focus strip, as asked. The dossier is a different
        # document from the press report and keeps its own heading settings -
        # these two interfaces share nothing.
        self.heading = HeadingLayoutCard(
            "sentiment",
            "Sets the headline printed above each clipping in the dossier, and "
            "the page it is built on.",
        )
        settings_stack.addWidget(self.heading)
        # Four columns that each need 275px cannot honestly fit a narrow window,
        # and shrinking them past that point is what put the delete button on a
        # card beyond the mouse. So the board scrolls sideways instead, the way a
        # board with more columns than screen always has: every column keeps a
        # width its cards actually work at, and the window is free to be as narrow
        # as the person wants.
        # One whole card plus its column header, so the board is always a place
        # to put a clipping and not just four coloured titles.
        self.column_scroll = SideScroll("ColumnScroll", self._build_columns(),
                                        min_height=CARD_HEIGHT + 96)
        work_stack.addWidget(self.column_scroll, 1)

        # One page, scrolled by the wheel. The columns are kept at least as tall
        # as the window, so turning the wheel to the bottom takes the set-up off
        # the top and hands the whole window to the cards - which is what was
        # actually wanted, rather than a handle to drag or a button to find.
        page = QWidget()
        page.setObjectName("BoardPage")
        page.setStyleSheet("#BoardPage { background: transparent; }")
        page_stack = QVBoxLayout(page)
        page_stack.setContentsMargins(0, 0, 0, 0)
        page_stack.setSpacing(11)
        page_stack.addWidget(settings)
        page_stack.addWidget(work)

        # No ceiling on the set-up half. Capping it made the board scroll in two
        # places - the page, and the set-up within its own frame - which is the
        # section-wise scrolling this is meant to be rid of. The columns are
        # still kept at least as tall as the window, so scrolling to the bottom
        # hands the whole of it to the cards.
        self.page = PageScroll("BoardPageScroll", page, work)
        self.page.verticalScrollBar().valueChanged.connect(
            lambda _v: self._sync_setup_button())
        outer.addWidget(self.page, 1)
        outer.addWidget(self._build_export_row())
        QTimer.singleShot(0, self._sync_setup_button)
        # The cover customiser may already be open when the board is built, and
        # the room it needs is decided the same way then as later.
        QTimer.singleShot(0, lambda: self._cover_folded(
            self.cover.body.isVisibleTo(self.cover), opening=False))

    # --------------------------------------------- the scrolling page
    def settings_shown(self) -> bool:
        """True while any of the set-up is still on screen."""
        return not self.page.at_work()

    def show_settings(self, showing: bool = True) -> None:
        """Scroll the set-up back into view, or out of the way.

        The same thing the wheel does, for people who would rather press a
        button - and for the tests, which cannot turn a wheel.
        """
        if showing:
            self.page.to_top()
        else:
            self.page.to_work()
        self._sync_setup_button()

    def toggle_settings(self) -> None:
        self.show_settings(not self.settings_shown())

    def _sync_setup_button(self) -> None:
        """Say which way the button will go, and look like the current state."""
        button = getattr(self, "setup_btn", None)
        if button is None:
            return
        shown = self.settings_shown()
        button.setText("Hide setup  \u25b2" if shown else "Show setup  \u25bc")
        base = theme.NAVY_WASH if shown else theme.ORANGE_WASH
        ink = theme.NAVY if shown else theme.ORANGE_INK
        edge = theme.NAVY_BAND_LINE if shown else theme.ORANGE
        button.setStyleSheet(
            f"QPushButton {{ background: {base}; color: {ink};"
            f" border: 1px solid {edge}; border-radius: 9px;"
            " padding: 3px 10px; font-size: 11px; font-weight: 800; }"
            f"QPushButton:hover {{ border-color: {ink}; }}"
        )

    def _build_heading(self) -> QWidget:
        strip = QWidget()
        strip.setStyleSheet("background: transparent;")
        row = QHBoxLayout(strip)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(9)
        title = QLabel("NORTHERN RAILWAY DIVISION SENTIMENT INTERFACE")
        title.setStyleSheet(
            "color: " + theme.INK + "; font-size: 13px; font-weight: 800;"
            " letter-spacing: .04em; background: transparent;"
        )
        hint = QLabel(
            "Positive, neutral, negative and digital coverage for the division "
            "you are working on"
        )
        hint.setObjectName("SubtleHint")
        row.addWidget(title)
        row.addWidget(hint)
        row.addStretch(1)
        self.division_clips = QLabel("0 division clips")
        self.division_clips.setObjectName("CountPill")
        row.addWidget(self.division_clips)
        return strip

    def _build_export_row(self) -> QWidget:
        """The dossier export bar, plus the formatting switches that feed it."""
        strip = QFrame()
        strip.setObjectName("ExportStrip")
        # Kept, so the floating buttons can be placed above it rather than on
        # top of it - they were covering the right-hand end of Download PDF.
        self.export_strip = strip
        strip.setStyleSheet(
            f"#ExportStrip {{ background: {theme.SURFACE};"
            f" border: 1px solid {theme.HAIRLINE_STRONG};"
            f" border-top: 3px solid {theme.ORANGE_DEEP};"
            f" border-radius: 16px; }}"
            f"#ExportStrip QLabel {{ background: transparent; border: none; }}"
        )
        outer = QVBoxLayout(strip)
        outer.setContentsMargins(18, 13, 16, 14)
        outer.setSpacing(11)

        row = QHBoxLayout()
        row.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        lead = QLabel("EXPORT SENTIMENT DOSSIER")
        lead.setStyleSheet(
            f"color: {theme.ORANGE}; font-size: 11px; font-weight: 800;"
            f" letter-spacing: .05em;"
        )
        self.status = QLabel()
        self.status.setObjectName("BoardStatus")
        self.status.setStyleSheet(
            f"#BoardStatus {{ color: {theme.NAVY}; background: {theme.NAVY_WASH};"
            f" border: 1px solid {theme.NAVY_BAND_LINE}; border-radius: 9px;"
            f" padding: 4px 10px; font-size: 11px; font-weight: 700; }}"
        )
        self.status.hide()

        # It carries the division name and the clipping count, so it grows with
        # the longest division. Elided rather than wrapped: the strip is a single
        # bar and a second line would push the Download buttons about.
        self.export_label = ElidedLabel(floor=120)
        self.export_label.setStyleSheet(
            f"color: {theme.SLATE_TEXT_LIGHT}; font-size: 12px;"
        )
        titles.addWidget(lead)
        titles.addWidget(self.export_label)
        titles.addWidget(self.status)
        row.addLayout(titles)
        # No stretch between the two: the buttons' own layout takes what is left
        # and ranges them right, so they keep one line for as long as one line
        # fits and only then wrap.

        self.options_btn = QPushButton("Report layout options")
        self.options_btn.setCheckable(True)
        self.options_btn.setCursor(Qt.PointingHandCursor)
        # The translucent orange was mixed for a black ground; on white the
        # same alpha composites to a washed-out smear.
        self.options_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.ORANGE_WASH};"
            f" color: {theme.ORANGE_INK}; border: 1px solid {theme.ORANGE};"
            " border-radius: 11px; padding: 8px 14px; font-size: 12px;"
            " font-weight: 700; }"
            f"QPushButton:hover {{ background: #FBE4D2; }}"
            f"QPushButton:checked {{ background: #FBE4D2;"
            f" border: 1px solid {theme.ORANGE_DEEP}; }}"
        )
        self.options_btn.toggled.connect(self._toggle_options)
        # The five buttons wrap rather than sitting in one unbreakable line.
        # A FlowLayout's minimum width is its widest single button, not the sum,
        # and the sum is what pins a window open: adding the burned-headlines
        # button to a plain row raised the board's floor far enough that the
        # columns could no longer be squeezed into overflowing, which is the
        # behaviour the window has to keep at 721px.
        buttons = FlowLayout(spacing=8, vertical_spacing=6,
                             alignment=Qt.AlignRight)
        buttons.addWidget(self.options_btn)

        word = QPushButton("Download Word")
        word.setCursor(Qt.PointingHandCursor)
        # Navy, not blue: #2563EB is the Neutral column's colour, and on a light
        # strip the collision reads as a category chip rather than a button.
        word.setStyleSheet(
            f"QPushButton {{ background: {theme.NAVY}; color: white;"
            " border: none; border-radius: 11px; padding: 9px 16px;"
            " font-size: 12px; font-weight: 700; }"
            f"QPushButton:hover {{ background: {theme.NAVY_HOVER}; }}"
        )
        pdf = QPushButton("Download PDF")
        pdf.setCursor(Qt.PointingHandCursor)
        # White on brand ORANGE is 2.9:1 - this button was never readable.
        pdf.setStyleSheet(
            f"QPushButton {{ background: {theme.ORANGE_INK}; color: white;"
            " border: none; border-radius: 11px; padding: 9px 16px;"
            " font-size: 12px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {theme.ORANGE_DEEP}; }}"
        )
        # The third way the department sends coverage: single pictures, forwarded
        # on WhatsApp, where the masthead has to be in the image or it is lost.
        jpegs = QPushButton("Download JPEGs")
        jpegs.setCursor(Qt.PointingHandCursor)
        jpegs.setToolTip(
            "One JPEG per clipping, with the newspaper, date and page printed "
            "into the picture."
        )
        jpegs.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE}; color: {theme.NAVY};"
            f" border: 2px solid {theme.NAVY}; border-radius: 11px;"
            " padding: 7px 14px; font-size: 12px; font-weight: 700; }"
            f"QPushButton:hover {{ background: {theme.NAVY_WASH}; }}"
        )
        # The fourth way: the same report, but with each clipping's headline
        # and address drawn INTO the picture. A page of it can be forwarded, or
        # a picture lifted out of the Word file, and the words come too - which
        # they do not when the heading is text sitting above the image.
        burned = QPushButton("Report with Burned \U0001F525 Headlines")
        burned.setCursor(Qt.PointingHandCursor)
        burned.setToolTip("Report with Images with Headlines as one")
        burned.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE};"
            f" color: {theme.ORANGE_INK};"
            f" border: 2px solid {theme.ORANGE_INK}; border-radius: 11px;"
            " padding: 7px 14px; font-size: 12px; font-weight: 700; }"
            f"QPushButton:hover {{ background: {theme.ORANGE_WASH}; }}"
        )
        # Clearing the board for a division. A morning is compiled division by
        # division, and starting the next one means getting the last one off
        # the board - which otherwise meant selecting a screenful of clippings
        # and deleting them by hand.
        wipe = QPushButton("Clear this division")
        wipe.setCursor(Qt.PointingHandCursor)
        wipe.setToolTip(
            "Remove every clipping showing here, so the next division can be "
            "started. Ctrl+Z brings them back.")
        wipe.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE};"
            f" color: {theme.DANGER};"
            f" border: 1px solid {theme.DANGER}; border-radius: 11px;"
            " padding: 7px 14px; font-size: 12px; font-weight: 700; }"
            f"QPushButton:hover {{ background: {theme.SURFACE};"
            f" border-color: {theme.DANGER}; }}"
        )
        wipe.clicked.connect(lambda: self.clearRequested.emit(self.active))
        self.clear_division_btn = wipe
        buttons.addWidget(wipe)

        burned.clicked.connect(lambda: self.exportRequested.emit("burned"))
        jpegs.clicked.connect(lambda: self.exportRequested.emit("jpeg"))
        word.clicked.connect(lambda: self.exportRequested.emit("docx"))
        pdf.clicked.connect(lambda: self.exportRequested.emit("pdf"))
        buttons.addWidget(jpegs)
        buttons.addWidget(burned)
        buttons.addWidget(word)
        buttons.addWidget(pdf)
        row.addLayout(buttons, 1)
        outer.addLayout(row)

        outer.addWidget(self._build_options_panel())
        return strip

    def _build_options_panel(self) -> QWidget:
        """Exactly what the exported dossier carries. Off by default: the useful
        output is the clippings alone, with nothing repeated on top of them."""
        panel = QWidget()
        panel.setObjectName("OptionsPanel")
        panel.setStyleSheet(
            "#OptionsPanel { background: transparent; }"
            "#OptionsPanel QLabel { background: transparent; border: none; }"
            f"#OptionsPanel QCheckBox {{ color: {theme.INK}; font-size: 11px;"
            " font-weight: 700; background: transparent; spacing: 8px; }"
            f"#OptionsPanel QLineEdit {{ background: {theme.SURFACE};"
            f" border: 1px solid {theme.HAIRLINE_STRONG};"
            f" border-radius: 9px; padding: 7px 10px; color: {theme.INK};"
            " font-size: 11px; }"
            "#OptionsPanel QLineEdit:focus { border-color: #E8792F; }"
        )
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 4, 0, 0)
        column.setSpacing(9)

        caption = QLabel(
            "Control exactly what the exported dossier carries"
        )
        caption.setStyleSheet("color: #8A97AD; font-size: 11px;")
        column.addWidget(caption)

        boxes = QHBoxLayout()
        boxes.setSpacing(9)
        self.option_boxes = {}
        for key, title, blurb, default in (
            ("cover", "Custom division cover page",
             "Follows the Enable Cover Page switch on the card above", False),
            ("banner", "Division header banner",
             "Prints a navy NORTHERN RAILWAY | CODE strip on every page", False),
            ("headings", "Sentiment section titles",
             "A heading before each category", True),
            # On by default. A headline typed onto a card is the only place that
            # wording exists - it is not repeated from anywhere - so defaulting
            # this off meant the work of naming every clipping was thrown away at
            # export, silently, which is what was reported.
            ("titles", "Text headline above image",
             "Prints the headline you typed on the card above its picture", True),
        ):
            box = QCheckBox(title)
            box.setChecked(default)
            box.setToolTip(blurb)
            box.setCursor(Qt.PointingHandCursor)
            box.toggled.connect(lambda _v: self.optionsChanged.emit())
            self.option_boxes[key] = box
            holder = QFrame()
            holder.setObjectName(f"Opt{key}")
            holder.setStyleSheet(
                f"#Opt{key} {{ background: rgba(30,41,59,0.65);"
                f" border: 1px solid #2A3346; border-radius: 11px; }}"
                f"#Opt{key} QLabel {{ background: transparent; border: none; }}"
            )
            inner = QVBoxLayout(holder)
            inner.setContentsMargins(11, 9, 11, 10)
            inner.setSpacing(2)
            inner.addWidget(box)
            note = QLabel(blurb)
            note.setWordWrap(True)
            note.setStyleSheet("color: #7C8AA3; font-size: 10px;")
            inner.addWidget(note)
            boxes.addWidget(holder, 1)
        column.addLayout(boxes)

        overrides = QHBoxLayout()
        overrides.setSpacing(9)
        self.custom_heading = QLineEdit()
        self.custom_heading.setPlaceholderText(
            "Division heading override (optional)"
        )
        self.custom_title = QLineEdit()
        self.custom_title.setPlaceholderText("Report title override (optional)")
        overrides.addWidget(self.custom_heading)
        overrides.addWidget(self.custom_title)
        column.addLayout(overrides)

        panel.hide()
        self.options_panel = panel
        return panel

    def _toggle_options(self, shown: bool) -> None:
        self.options_panel.setVisible(shown)

    def _cover_folded(self, opened: bool, opening: bool = True) -> None:
        """Bring the cover customiser into view when it is opened.

        It is a full-height job, and it sits some way down a page that is one
        long document, so opening it scrolls to it rather than leaving somebody
        to go looking.

        ``opening=False`` is the call the board makes while it is being built,
        which only wants to know the state - the customiser may well already be
        open from yesterday, and scrolling to it then would mean the board opened
        halfway down itself for no reason anybody asked for.
        """
        page = getattr(self, "page", None)
        if page is None:
            return
        if opened and opening:
            page.to_top()
            QTimer.singleShot(0, self._show_cover)

    def _show_cover(self) -> None:
        page = getattr(self, "page", None)
        if page is not None:
            page.ensureWidgetVisible(self.cover, 0, 0)

    def _mirror_cover_switch(self) -> None:
        """Keep the options panel showing what the card actually says."""
        box = self.option_boxes.get("cover") if hasattr(self, "option_boxes") else None
        if box is None:
            return
        wanted = bool(self.cover.cover_config().enabled)
        if box.isChecked() != wanted:
            blocked = box.blockSignals(True)
            box.setChecked(wanted)
            box.blockSignals(blocked)

    def export_options(self) -> dict:
        """What the export builder needs, read off the switches."""
        return {
            # Read from the card, not from this panel's own tick: the card is
            # where the switch lives and where anyone looks for it.
            "include_cover": bool(self.cover.cover_config().enabled),
            "include_division_header": self.option_boxes["banner"].isChecked(),
            "include_category_headers": self.option_boxes["headings"].isChecked(),
            "include_clip_titles": self.option_boxes["titles"].isChecked(),
            "custom_division_heading": self.custom_heading.text().strip(),
            "custom_report_title": self.custom_title.text().strip(),
        }

    # -- division bar ------------------------------------------------------
    def _build_division_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("DivisionBar")
        bar.setStyleSheet(
            f"#DivisionBar {{ background: {theme.NAVY_BAND};"
            f" border: 1px solid {theme.NAVY_BAND_LINE};"
            f" border-radius: 16px; }}"
            f"#DivisionBar QLabel {{ background: transparent; border: none; }}"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 12, 18, 12)
        row.setSpacing(12)

        # Load-bearing, not ornament: the pale band is only a shade off the
        # canvas, and without this rail it dissolves into the page.
        rail = QFrame()
        rail.setObjectName("DivisionRail")
        rail.setFixedWidth(5)
        row.addWidget(rail)

        lead = QLabel("ACTIVE DIVISION")
        lead.setObjectName("DivisionLead")
        row.addWidget(lead)

        self.division_name = QLabel()
        self.division_name.setObjectName("DivisionName")
        self.division_code = QLabel()
        self.division_code.setObjectName("DivisionCode")
        self.division_hindi = QLabel()
        self.division_hindi.setObjectName("DivisionHindi")
        row.addWidget(self.division_name)
        row.addWidget(self.division_code)
        row.addWidget(self.division_hindi)
        row.addStretch(1)

        switch = QLabel("SWITCH DIVISION")
        switch.setObjectName("DivisionLead")
        row.addWidget(switch)
        self.division_pick = QComboBox()
        self.division_pick.setObjectName("DivisionPick")
        self.division_pick.setCursor(Qt.PointingHandCursor)
        self.division_pick.currentIndexChanged.connect(self._division_picked)
        row.addWidget(self.division_pick)
        return bar

    # -- totals ------------------------------------------------------------
    def _build_totals(self) -> QWidget:
        strip = QWidget()
        strip.setStyleSheet("background: transparent;")
        row = QHBoxLayout(strip)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(11)

        self.total_tile = self._tile("TOTAL CLIPPINGS", theme.NAVY, theme.NAVY_WASH,
                                     None)
        row.addWidget(self.total_tile["frame"])
        self.tiles: dict[str, dict] = {}
        for section in sentiment.COLUMNS:
            style = theme.SENTIMENT_STYLES[section.value]
            meta = COLUMN_META[section.value]
            tile = self._tile(style["label"].upper(), style["colour"], style["bg"],
                              meta["icon"])
            self.tiles[section.value] = tile
            row.addWidget(tile["frame"])
        return strip

    _tile_serial = 0

    @classmethod
    def _tile(cls, label: str, colour: str, wash: str, icon: str | None) -> dict:
        """One count tile. Scoped by object name so the frame's border and fill
        stay on the frame instead of being inherited by the labels inside it."""
        cls._tile_serial += 1
        name_id = f"KpiTile{cls._tile_serial}"
        frame = QFrame()
        frame.setObjectName(name_id)
        frame.setMinimumHeight(64)
        frame.setStyleSheet(
            f"#{name_id} {{ background: {wash}; border: 1px solid {colour}2E;"
            f" border-radius: 14px; }}"
            f"#{name_id} QLabel {{ background: transparent; border: none; }}"
        )
        outer = QHBoxLayout(frame)
        outer.setContentsMargins(15, 9, 13, 10)
        outer.setSpacing(8)

        column = QVBoxLayout()
        column.setSpacing(0)
        count = QLabel("0")
        count.setStyleSheet(
            f"color: {colour}; font-size: 23px; font-weight: 800;"
            f" letter-spacing: -0.01em;"
        )
        caption = QLabel(label)
        caption.setStyleSheet(
            f"color: {theme.MUTED}; font-size: 10px; font-weight: 700;"
            f" letter-spacing: .03em;"
        )
        column.addWidget(count)
        column.addWidget(caption)
        outer.addLayout(column)
        outer.addStretch(1)

        if icon:
            badge = QLabel()
            badge.setFixedSize(26, 26)
            pixmap = QPixmap(26, 26)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            drawer = getattr(icons, icon, None)
            if drawer is not None:
                drawer(painter, QRectF(3, 3, 20, 20), QColor(colour))
            painter.end()
            badge.setPixmap(pixmap)
            outer.addWidget(badge, 0, Qt.AlignVCenter)

        return {"frame": frame, "count": count}

    # -- columns -----------------------------------------------------------
    def _build_columns(self) -> QWidget:
        holder = QWidget()
        holder.setStyleSheet("background: transparent;")
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        self.columns: dict[str, SentimentColumn] = {}
        self.column_counts: dict[str, QLabel] = {}
        self.column_panels: dict[str, QFrame] = {}
        self.expand_buttons: dict[str, QPushButton] = {}

        for section in sentiment.COLUMNS:
            style = theme.SENTIMENT_STYLES[section.value]
            meta = COLUMN_META[section.value]
            slug = section.value

            panel = QFrame()
            panel.setObjectName(f"SentPanel{slug}")
            panel.setStyleSheet(
                f"#SentPanel{slug} {{ background: {style['bg']};"
                f" border: 1px solid {style['line']}; border-radius: 16px; }}"
            )
            column_layout = QVBoxLayout(panel)
            column_layout.setContentsMargins(1, 1, 1, 1)
            column_layout.setSpacing(0)

            header = QFrame()
            header.setObjectName(f"SentHead{slug}")
            header.setStyleSheet(
                f"#SentHead{slug} {{ background: {style['colour']};"
                f" border: none; border-top-left-radius: 15px;"
                f" border-top-right-radius: 15px; }}"
                f"#SentHead{slug} QLabel {{ background: transparent; border: none; }}"
            )
            head_col = QVBoxLayout(header)
            head_col.setContentsMargins(13, 8, 10, 9)
            head_col.setSpacing(2)

            head_row = QHBoxLayout()
            head_row.setSpacing(8)
            title = QLabel(meta["title"])
            title.setStyleSheet(
                "color: white; font-size: 13px; font-weight: 800;"
            )
            count = QLabel("0")
            count.setMinimumWidth(26)
            count.setAlignment(Qt.AlignCenter)
            count.setStyleSheet(
                "color: white; background: rgba(255,255,255,0.26); border: none;"
                " border-radius: 10px; padding: 2px 9px; font-size: 11px;"
                " font-weight: 800;"
            )

            expand = QPushButton("Expand")
            expand.setCursor(Qt.PointingHandCursor)
            expand.setToolTip(
                f"Show only {meta['title']} and hide the other three columns"
            )
            expand.setStyleSheet(
                "QPushButton { background: rgba(255,255,255,0.92); border: none;"
                " border-radius: 10px; padding: 4px 12px; color: #1F2937;"
                " font-size: 11px; font-weight: 700; }"
                "QPushButton:hover { background: #FFFFFF; }"
            )
            expand.clicked.connect(
                lambda _checked=False, sec=section: self.toggle_focus(sec.value)
            )
            self.expand_buttons[slug] = expand

            add = QPushButton("Add")
            add.setCursor(Qt.PointingHandCursor)
            add.setStyleSheet(
                "QPushButton { background: rgba(255,255,255,0.22); border: none;"
                " border-radius: 10px; padding: 4px 14px; color: white;"
                " font-size: 11px; font-weight: 700; }"
                "QPushButton:hover { background: rgba(255,255,255,0.38); }"
            )
            add.clicked.connect(
                lambda _checked=False, sec=section: self.addRequested.emit(sec.value)
            )

            head_row.addWidget(title)
            head_row.addWidget(count)
            head_row.addStretch(1)
            head_row.addWidget(expand)
            head_row.addWidget(add)
            head_col.addLayout(head_row)

            subtitle = QLabel(meta["subtitle"] + "  \u00b7  " + style["hindi"])
            # A QLabel that cannot wrap reports its whole text width as its
            # minimum, and four of these set the window's minimum width to 2434.
            subtitle.setWordWrap(True)
            subtitle.setStyleSheet(
                "color: rgba(255,255,255,0.80); font-size: 10px;"
            )
            head_col.addWidget(subtitle)
            column_layout.addWidget(header)

            view = SentimentColumn(section)
            view.cardsDropped.connect(self.assignRequested)
            view.cardOpened.connect(self.previewRequested)
            view.titleEdited.connect(self.titleEdited)
            view.urlEdited.connect(self.urlEdited)
            view.cardDeleted.connect(self.cardDeleted)
            view.cardRotated.connect(self.cardRotated)
            column_layout.addWidget(view, 1)

            self.columns[slug] = view
            self.column_counts[slug] = count
            # 150 was a promise the column could not keep: its contents need
            # roughly twice that, so the layout allowed widths at which every
            # card was clipped. 275 is the measured width below which a card's
            # chips and its action buttons start to overlap.
            panel.setMinimumWidth(275)
            self.column_panels[slug] = panel
            row.addWidget(panel, 1)
        return holder

    def _build_column_bar(self) -> QWidget:
        """Two states in one slot: the quiet strip, or the dark focus bar."""
        holder = QWidget()
        holder.setObjectName("ColumnBar")
        holder.setStyleSheet("#ColumnBar { background: transparent; }")
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_strip_header())
        layout.addWidget(self._build_focus_bar())
        self.focus_bar.hide()
        return holder

    def _build_strip_header(self) -> QWidget:
        self.strip = QWidget()
        self.strip.setObjectName("ColumnStrip")
        self.strip.setStyleSheet("#ColumnStrip { background: transparent; }"
                                 "#ColumnStrip QLabel { background: transparent;"
                                 " border: none; }")
        row = QHBoxLayout(self.strip)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(8)

        # The one control that matters here: everything above this bar is set up
        # once a day, and this gets it out of the way for the rest of the morning.
        # It used to be a drag handle only, which nobody could be expected to find.
        self.setup_btn = QPushButton()
        self.setup_btn.setCursor(Qt.PointingHandCursor)
        self.setup_btn.setToolTip(
            "Fold away the division, cover page and layout settings so the "
            "columns have the whole window. They are set once a day."
        )
        self.setup_btn.clicked.connect(self.toggle_settings)
        row.addWidget(self.setup_btn)

        mark = QLabel()
        mark.setPixmap(self._icon("layers", theme.NAVY, 15))
        row.addWidget(mark)
        self.strip_title = ElidedLabel(floor=110)
        self.strip_title.setStyleSheet(
            "color: #1F2937; font-size: 12px; font-weight: 800;"
        )
        row.addWidget(self.strip_title)
        # Guidance, not instruction: it trims before it pushes the board open.
        hint = ElidedLabel(
            "(use Expand on any column to focus on it, or drag clippings "
            "between columns)",
            floor=90,
        )
        hint.setStyleSheet("color: #6B7280; font-size: 11px;")
        row.addWidget(hint, 1)
        row.addStretch(0)

        row.addWidget(self._quiet_label("Quick focus:"))
        self.quick_chips: dict[str, QPushButton] = {}
        for section in sentiment.COLUMNS:
            style = theme.SENTIMENT_STYLES[section.value]
            chip = QPushButton(section.value)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setToolTip(f"Show only {COLUMN_META[section.value]['title']}")
            chip.setStyleSheet(
                f"QPushButton {{ background: {style['bg']};"
                f" color: {style['colour']}; border: 1px solid {style['line']};"
                f" border-radius: 8px; font-size: 10px; font-weight: 800;"
                f" padding: 3px 9px; }}"
                f"QPushButton:hover {{ border-color: {style['colour']}; }}"
            )
            chip.clicked.connect(
                lambda _c=False, v=section.value: self.toggle_focus(v)
            )
            self.quick_chips[section.value] = chip
            row.addWidget(chip)
        return self.strip

    def _build_focus_bar(self) -> QWidget:
        self.focus_bar = QFrame()
        self.focus_bar.setObjectName("FocusBar")
        self.focus_bar.setStyleSheet(
            f"#FocusBar {{ background: {theme.ORANGE_WASH};"
            f" border: 2px solid {theme.ORANGE_DEEP}; border-radius: 14px; }}"
            f"#FocusBar QLabel {{ background: transparent; border: none; }}"
        )
        row = QHBoxLayout(self.focus_bar)
        row.setContentsMargins(14, 9, 12, 9)
        row.setSpacing(9)

        mark = QLabel()
        mark.setPixmap(self._icon("maximize", theme.ORANGE_INK, 14))
        row.addWidget(mark)
        # The bar names the category now. It used to be the heaviest thing on
        # screen, which is what stopped a filtered count being read as the
        # division total; a quieter bar has to say so in words instead.
        self.focus_lead = QLabel("FOCUS:")
        self.focus_lead.setStyleSheet(
            f"color: {theme.ORANGE_INK}; font-size: 11px; font-weight: 900;"
            f" letter-spacing: .06em;"
        )
        row.addWidget(self.focus_lead)
        # Elided, like the strip it replaces. Left plain it measured 289px and
        # made the focus bar demand MORE room than the strip - so toggling focus
        # mode could widen the window's floor under the user's hands.
        hint = ElidedLabel(
            "Click any bubble to switch category, or Show all to see all four",
            floor=90,
        )
        hint.setStyleSheet(
            f"color: {theme.SLATE_TEXT_LIGHT}; font-size: 11px;"
        )
        row.addWidget(hint, 1)
        row.addStretch(0)

        self.bubbles: dict[str, dict] = {}
        for section in sentiment.COLUMNS:
            meta = COLUMN_META[section.value]
            bubble = QPushButton()
            bubble.setCursor(Qt.PointingHandCursor)
            bubble.setMinimumHeight(30)
            bubble.setIconSize(QSize(14, 14))
            bubble.clicked.connect(
                lambda _c=False, v=section.value: self.toggle_focus(v)
            )
            self.bubbles[section.value] = {"button": bubble, "icon": meta["icon"]}
            row.addWidget(bubble)

        self.overview_btn = QPushButton("All four")
        self.overview_btn.setCursor(Qt.PointingHandCursor)
        self.overview_btn.setToolTip("Show all four columns again")
        self.overview_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE}; color: {theme.NAVY};"
            f" border: 1px solid {theme.NAVY}; border-radius: 11px;"
            f" font-size: 11px; font-weight: 800; padding: 6px 13px; }}"
            f"QPushButton:hover {{ background: {theme.NAVY}; color: white; }}"
        )
        self.overview_btn.clicked.connect(lambda: self.toggle_focus(self.focused))
        row.addWidget(self.overview_btn)
        return self.focus_bar

    @staticmethod
    def _icon(name: str, colour: str, size: int) -> QPixmap:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        drawer = getattr(icons, name, None)
        if drawer is not None:
            drawer(painter, QRectF(0, 0, size, size), QColor(colour))
        painter.end()
        return pixmap

    @staticmethod
    def _quiet_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            "color: #6B7280; font-size: 11px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        return label

    def _refresh_bubbles(self) -> None:
        for value, parts in self.bubbles.items():
            style = theme.SENTIMENT_STYLES[value]
            button = parts["button"]
            count = self.column_counts[value].text()
            active = self.focused == value
            button.setText(f"  {value}   {count}")
            button.setIcon(
                self._icon(parts["icon"],
                           "#FFFFFF" if active else style["badge"], 14)
            )
            button.setToolTip(
                f"Currently showing {COLUMN_META[value]['title']} on its own"
                if active else
                f"Show only {COLUMN_META[value]['title']}"
            )
            # The active fill is the badge colour, not the bright column
            # colour: white on Positive #16A34A is only 3.3:1, and this is
            # 11px text.
            button.setStyleSheet(
                (f"QPushButton {{ background: {style['badge']}; color: white;"
                 f" border: 1.5px solid {style['badge']}; border-radius: 11px;"
                 f" font-size: 11px; font-weight: 800; padding: 6px 13px; }}")
                if active else
                (f"QPushButton {{ background: {style['bg']};"
                 f" color: {style['badge']};"
                 f" border: 1.5px solid {style['colour']}; border-radius: 11px;"
                 f" font-size: 11px; font-weight: 700; padding: 6px 13px; }}"
                 f"QPushButton:hover {{ background: {theme.SURFACE}; }}")
            )

    def toggle_focus(self, value: str) -> None:
        """Show one column on its own, or bring all four back.

        With four columns a long positive run is a narrow strip; focusing gives it
        the whole width without moving anything.
        """
        self.focused = None if self.focused == value else value
        for key, panel in self.column_panels.items():
            panel.setVisible(self.focused is None or key == self.focused)
            self.expand_buttons[key].setText(
                "Show all" if self.focused == key else "Expand"
            )
        self.strip.setVisible(self.focused is None)
        self.focus_bar.setVisible(self.focused is not None)
        if self.focused:
            self.focus_lead.setText(f"FOCUS: {self.focused.upper()}")
        self._refresh_bubbles()

    # -- data --------------------------------------------------------------
    def set_rows(self, rows: list) -> None:
        """Hand the board the full set of clippings; it filters by division."""
        self._rows = list(rows)
        self._refresh_divisions()
        self._refresh_columns()

    def _refresh_divisions(self) -> None:
        self.division_pick.blockSignals(True)
        self.division_pick.clear()
        for division in self.divisions:
            n = sum(1 for r in self._rows if r.clip.division == division.code)
            self.division_pick.addItem(
                f"{division.full_name} ({division.code})   ·   {n} clip"
                f"{'s' if n != 1 else ''}",
                division.code,
            )
        loose = sum(1 for r in self._rows if not r.clip.division)
        self.division_pick.addItem(
            f"All divisions   ·   {len(self._rows)} clip"
            f"{'s' if len(self._rows) != 1 else ''}"
            + (f"   ({loose} unassigned)" if loose else ""),
            ALL_DIVISIONS,
        )
        at = self.division_pick.findData(self.active)
        self.division_pick.setCurrentIndex(at if at >= 0 else 0)
        self.division_pick.blockSignals(False)

        division = sentiment.division_by_code(self.active, self.config)
        if division:
            self.division_name.setText(division.full_name)
            self.division_code.setText(f"({division.code})")
            self.division_hindi.setText(division.hindi_name)
        else:
            self.division_name.setText("All divisions")
            self.division_code.setText("")
            self.division_hindi.setText("")

    def visible_clips(self) -> list:
        """The clippings the board is showing, in the order the columns show
        them - which is the order the dossier prints them in."""
        ordered = []
        for section in sentiment.COLUMNS:
            for row in self._visible_rows():
                if sentiment.column_for(row.clip.section) is section:
                    ordered.append(row.clip)
        return ordered

    def active_division(self):
        return sentiment.division_by_code(self.active, self.config)

    def _visible_rows(self) -> list:
        if self.active == ALL_DIVISIONS:
            return self._rows
        # Unassigned clippings stay visible, or they would be unreachable here.
        return [r for r in self._rows
                if r.clip.division == self.active or not r.clip.division]

    def _refresh_columns(self) -> None:
        visible = self._visible_rows()
        buckets: dict[str, list] = {s.value: [] for s in sentiment.COLUMNS}
        for row in visible:
            buckets[sentiment.column_for(row.clip.section).value].append(row)

        for value, rows in buckets.items():
            self.columns[value].model().set_rows(rows)
            self.column_counts[value].setText(str(len(rows)))
            self.tiles[value]["count"].setText(str(len(rows)))
        self.total_tile["count"].setText(str(len(visible)))

        division = sentiment.division_by_code(self.active, self.config)
        where = division.full_name if division else "All divisions"
        plural = "s" if len(visible) != 1 else ""
        self.division_clips.setText(str(len(visible)) + " division clip" + plural)
        self.export_label.setText(
            where + " media sentiment report  \u00b7  " + str(len(visible))
            + " clipping" + plural
        )
        self.strip_title.setText(f"Four sentiment columns for {where}")
        self._refresh_bubbles()
        self.cover.set_division(division)
        self.cover.set_counts(
            len(visible),
            {value: len(rows) for value, rows in buckets.items()},
        )

    def begin_rename(self, clip_id: int) -> None:
        """Open the headline box on a card, whichever column it landed in."""
        for view in self.columns.values():
            for row in range(view.model().rowCount()):
                entry = view.model().index(row, 0).data(Qt.UserRole)
                if entry is not None and entry.id == clip_id:
                    view.open_editor_for(clip_id)
                    return

    def select_division(self, code: str) -> None:
        """Show a division by code - used when a saved session is restored."""
        at = self.division_pick.findData(code)
        if at < 0:
            return
        self.active = code
        self.division_pick.blockSignals(True)
        self.division_pick.setCurrentIndex(at)
        self.division_pick.blockSignals(False)
        self._refresh_divisions()
        self._refresh_columns()

    def scroll_columns(self, top: bool = True) -> None:
        """Send every visible column to one end - the floating buttons use this."""
        for value, view in self.columns.items():
            if self.focused is not None and value != self.focused:
                continue
            bar = view.verticalScrollBar()
            bar.setValue(bar.minimum() if top else bar.maximum())

    def set_selection(self, ids: set) -> None:
        for view in self.columns.values():
            view.delegate.selected_ids = set(ids)
            view.viewport().update()

    def _division_picked(self, index: int) -> None:
        code = self.division_pick.itemData(index)
        if code and code != self.active:
            self.active = code
            self._refresh_divisions()
            self._refresh_columns()
            self.divisionChanged.emit(code)
