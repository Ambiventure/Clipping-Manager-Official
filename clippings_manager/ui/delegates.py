"""Painting for the review list.

Two kinds of line share one delegate: a file group header, and a clipping row. Both
are drawn straight onto the painter and hit-tested against :mod:`rowlayout`, which
is what keeps the view fast enough to scroll 165 clippings without stutter while
still carrying per-row buttons.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate

from . import icons, rowlayout, theme
from .model import ENTRY_CLIP, ENTRY_GROUP, Entry

HOVER_NONE = (-1, "")


def fields_for(clip) -> tuple[bool, bool]:
    """Which of the two boxes a clipping shows: (headline, address).

    Whichever it has something in, plus whichever has been asked for. A clipping
    with neither shows the headline box, because that is the one a person
    reaches for first and because a card with no box at all would have nowhere
    to start typing.

    The headline box used to be hidden the moment a clipping had an address -
    which was fine while the headline was the only box anybody could ask for,
    and became a trap the day Add URL arrived: pressing it on an unnamed
    clipping took the headline box away, so the headline could never be typed.
    """
    title = (bool(clip.effective_label.strip())
             or bool(getattr(clip, "show_title_box", False)))
    address = bool(clip.url.strip()) or bool(getattr(clip, "show_url_box", False))
    return (title or not address), address


def _site(url: str) -> str:
    """The site an address belongs to: 'indianexpress.com', 'facebook.com'."""
    host = (url or "").strip()
    host = host.split("//", 1)[-1].split("/", 1)[0].split("?", 1)[0]
    return host[4:] if host.lower().startswith("www.") else host


class EntryDelegate(QStyledItemDelegate):
    """Draws group headers and clipping rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hover = HOVER_NONE          # (view row, region name)
        self.drop_row = -1               # row the insertion line is drawn against
        self.drop_below = False          # line under that row rather than over it
        self.dragging_ids: set[int] = set()

    # ------------------------------------------------------------ measuring
    def sizeHint(self, option, index) -> QSize:
        entry: Entry = index.data(Qt.UserRole)
        if entry is None:
            return QSize(option.rect.width(), rowlayout.ROW_HEIGHT)
        if entry.kind == ENTRY_GROUP:
            return QSize(
                option.rect.width(),
                rowlayout.GROUP_HEIGHT + rowlayout.GROUP_GAP * 2,
            )
        title, address = fields_for(entry.row.clip)
        height = (rowlayout.ROW_HEIGHT_TWO if (title and address)
                  else rowlayout.ROW_HEIGHT)
        return QSize(option.rect.width(), height + rowlayout.ROW_GAP)

    def geometry_for(self, option_rect: QRect, entry: Entry):
        if entry.kind == ENTRY_GROUP:
            top = QRect(option_rect)
            top.adjust(0, rowlayout.GROUP_GAP, 0, 0)
            return rowlayout.group_row(top, top.width())
        top = QRect(option_rect)
        top.adjust(0, rowlayout.ROW_GAP // 2, 0, 0)
        # The last clipping of a file gets no "Merge down" pill: its neighbour
        # belongs to a different document, and stitching across that boundary is
        # never what was meant. (This read `and False`, so the pill was drawn on
        # every row and a cross-file merge was one click away.)
        title, address = fields_for(entry.row.clip)
        return rowlayout.clip_row(
            top, in_group=True,
            is_last=entry.last_in_group or not entry.can_merge,
            show_title=title, show_url=address,
        )

    # -------------------------------------------------------------- painting
    def paint(self, painter: QPainter, option, index) -> None:
        entry: Entry = index.data(Qt.UserRole)
        if entry is None:
            return
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        if entry.kind == ENTRY_GROUP:
            self._paint_group(painter, option, index, entry)
        else:
            self._paint_clip(painter, option, index, entry)
        painter.restore()

    # -- group header ------------------------------------------------------
    def _paint_group(self, painter, option, index, entry: Entry) -> None:
        group = entry.group
        geo = self.geometry_for(option.rect, entry)
        model = index.model()
        ids = [r.id for r in group.rows]
        all_selected = bool(ids) and all(model.is_selected(i) for i in ids)
        some_selected = any(model.is_selected(i) for i in ids)

        style = theme.SOURCE_STYLES.get(group.source_kind, theme.SOURCE_STYLES["image"])

        # A whole file that repeats another whole file - the same division's
        # report imported once as Word and once as PDF. Every clipping in it is
        # a repeat, so saying it ninety times on ninety cards is the wrong
        # shape. It is said once, here, in a colour that means "delete this".
        repeats = getattr(model, "duplicate_files", {}).get(group.key, "")

        if repeats:
            fill, line = QColor("#3B0A0A"), QColor("#7F1D1D")
        elif all_selected:
            fill, line = QColor("#EAF0FB"), theme.QNAVY
        else:
            fill, line = QColor("#FFFFFF"), theme.QHAIRLINE
        painter.setPen(QPen(line, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(geo.card).adjusted(0.5, 0.5, -0.5, -0.5), 13, 13)

        hover_row, hover_name = self.hover
        this_row = index.row()

        icons.grip(painter, QRectF(geo.grip), theme.QNAVY if some_selected else theme.QFAINT)

        if all_selected:
            icons.check_square(painter, QRectF(geo.check), theme.QNAVY)
        elif some_selected:
            icons.dash_square(painter, QRectF(geo.check), theme.QNAVY)
        else:
            icons.square(painter, QRectF(geo.check), QColor("#94A3B8"))

        # source badge
        painter.setPen(QPen(QColor(style["line"]), 1))
        painter.setBrush(QColor(style["bg"]))
        painter.drawRoundedRect(QRectF(geo.badge).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        icon_box = QRectF(geo.badge.left() + 5, geo.badge.center().y() - 7, 14, 14)
        drawer = {
            "word": icons.file_word, "pdf": icons.file_pdf,
            "clipboard": icons.image, "image": icons.image,
        }[group.source_kind]
        drawer(painter, icon_box, QColor(style["fg"]))
        font = painter.font()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(style["fg"]))
        painter.drawText(
            QRect(geo.badge.left() + 22, geo.badge.top(), geo.badge.width() - 24,
                  geo.badge.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            style["label"],
        )

        # file name
        font.setPixelSize(12)
        painter.setFont(font)
        painter.setPen(QColor("#FFE4E4") if repeats else theme.QINK)
        metrics = QFontMetrics(font)
        name = group.title
        if repeats:
            name = f"{group.title}   —   ALREADY IMPORTED AS {repeats}"
        painter.drawText(
            geo.title,
            Qt.AlignVCenter | Qt.AlignLeft,
            metrics.elidedText(name, Qt.ElideMiddle, geo.title.width()),
        )

        # count pill
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#7F1D1D") if repeats else theme.QHAIRLINE, 1))
        painter.setBrush(QColor("#5B1111") if repeats else QColor("#F8FAFC"))
        painter.drawRoundedRect(QRectF(geo.count).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        painter.setPen(QColor("#FFD5D5") if repeats else theme.QMUTED)
        # "3 of 12" while a filter is hiding some of a file, never a bare 3.
        # A filtered count read as the total is exactly the mistake the board
        # made once, and it is invisible until somebody acts on it.
        total = getattr(group, "total", 0) or group.count
        if total > group.count:
            said = f"{group.count} of {total}"
        else:
            said = f"{group.count} clip" + ("s" if group.count != 1 else "")
        painter.drawText(geo.count, Qt.AlignCenter, said)

        for hit in geo.buttons:
            hovered = hover_row == this_row and hover_name == hit.name
            self._paint_group_button(painter, hit, hovered, group)

    def _paint_group_button(self, painter, hit, hovered, group) -> None:
        rect = QRectF(hit.rect)
        if hovered:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#EEF2F7"))
            painter.drawRoundedRect(rect, 7, 7)
        box = QRectF(rect.center().x() - 8, rect.center().y() - 8, 16, 16)
        colour = theme.QMUTED if not hovered else theme.QNAVY
        if hit.name == "group_rotate":
            icons.rotate(painter, box, colour)
        elif hit.name == "group_top":
            icons.chevrons_up(painter, box, theme.QORANGE if hovered else colour)
        elif hit.name == "group_up":
            icons.chevron_up(painter, box, colour)
        elif hit.name == "group_down":
            icons.chevron_down(painter, box, colour)
        elif hit.name == "group_bottom":
            icons.chevrons_down(painter, box, theme.QORANGE if hovered else colour)
        elif hit.name == "group_delete":
            icons.trash(painter, box, theme.QDANGER)
        elif hit.name == "group_collapse":
            if group.collapsed:
                icons.chevron_down(painter, box, theme.QORANGE)
            else:
                icons.chevron_up(painter, box, colour)

    # -- clipping row ------------------------------------------------------
    def _paint_clip(self, painter, option, index, entry: Entry) -> None:
        row = entry.row
        clip = row.clip
        model = index.model()
        geo = self.geometry_for(option.rect, entry)
        selected = model.is_selected(row.id)
        dragging = row.id in self.dragging_ids
        hover_row, hover_name = self.hover
        this_row = index.row()

        self._paint_bracket(painter, geo.bracket, entry, selected)

        # --- card ---------------------------------------------------------
        if dragging:
            pen = QPen(theme.QORANGE, 2, Qt.DashLine)
            fill = QColor("#FFF8F3")
        elif selected:
            pen = QPen(theme.QNAVY, 2)
            fill = QColor(theme.NAVY_SELECT)
        else:
            pen = QPen(theme.QHAIRLINE, 1)
            fill = theme.QSURFACE
        painter.setPen(pen)
        painter.setBrush(fill)
        painter.drawRoundedRect(
            QRectF(geo.card).adjusted(1, 1, -1, -1), rowlayout.CARD_RADIUS,
            rowlayout.CARD_RADIUS,
        )

        if not clip.include:
            painter.setOpacity(0.42)

        # --- checkbox -----------------------------------------------------
        if selected:
            icons.check_square(painter, QRectF(geo.check), theme.QNAVY)
        else:
            painter.setPen(QPen(QColor("#CBD5E1"), 1.4))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(geo.check).adjusted(1, 1, -1, -1), 5, 5)

        icons.grip(
            painter, QRectF(geo.grip),
            theme.QNAVY if selected else QColor("#9CA3AF"),
        )

        # --- index --------------------------------------------------------
        font = painter.font()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(theme.QNAVY if selected else theme.QMUTED)
        painter.drawText(geo.index, Qt.AlignCenter, str(entry.index_in_all))

        # --- thumbnail ----------------------------------------------------
        self._paint_thumb(painter, geo.thumb, row, selected,
                          hovered=(hover_row == this_row and hover_name == "thumb"))

        # --- label field --------------------------------------------------
        self._paint_fields(painter, geo, clip, selected)

        # --- sub line -----------------------------------------------------
        self._paint_subline(painter, geo.sub, row, clip,
                            index.model().opener_for(entry.row.id))

        # --- action buttons -----------------------------------------------
        painter.setOpacity(1.0 if clip.include else 0.42)
        for hit in geo.buttons:
            hovered = hover_row == this_row and hover_name == hit.name
            if hit.name in ("add_url", "add_title"):
                self._paint_add(painter, hit, hovered,
                                "url" if hit.name == "add_url" else "title")
                continue
            self._paint_clip_button(painter, hit, hovered, entry)

        painter.setOpacity(1.0)

        if self.drop_row == this_row:
            self._paint_drop_line(painter, geo.card, self.drop_below)

    def _paint_drop_line(self, painter, card, below: bool) -> None:
        """Where the clippings will land: a line, with a cap at each end."""
        y = (card.bottom() + rowlayout.ROW_GAP // 2) if below else (
            card.top() - rowlayout.ROW_GAP // 2
        )
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(theme.QORANGE, 3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(card.left() + 8, y, card.right() - 8, y)
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.QORANGE)
        for x in (card.left() + 8, card.right() - 8):
            painter.drawEllipse(QPoint(x, y), 4, 4)
        painter.restore()

    def _paint_bracket(self, painter, rect: QRect, entry: Entry, selected: bool) -> None:
        """The curly-bracket spine that ties one file's clippings together."""
        colour = theme.QNAVY if selected else QColor("#BFC8D6")
        painter.setPen(QPen(colour, 2))
        painter.setBrush(Qt.NoBrush)
        x = rect.left() + 13
        top, bottom = rect.top(), rect.bottom()
        if entry.first_in_group:
            painter.drawArc(QRect(x, top + 2, 14, 14), 90 * 16, 90 * 16)
            painter.drawLine(x + 7, top + 9, x, top + 9)
            painter.drawLine(x, top + 9, x, bottom)
        elif entry.last_in_group:
            painter.drawArc(QRect(x, bottom - 16, 14, 14), 180 * 16, 90 * 16)
            painter.drawLine(x + 7, bottom - 9, x, bottom - 9)
            painter.drawLine(x, top, x, bottom - 9)
        else:
            painter.drawLine(x, top, x, bottom)

    def _paint_thumb(self, painter, rect: QRect, row, selected, hovered) -> None:
        painter.setPen(QPen(theme.QNAVY if selected else theme.QHAIRLINE, 1))
        painter.setBrush(QColor("#F8FAFC"))
        painter.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)

        pixmap = row.thumbnail
        if pixmap and not pixmap.isNull():
            painter.save()
            path_rect = QRectF(rect).adjusted(2, 2, -2, -2)
            scaled = pixmap.scaled(
                path_rect.size().toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            target = QRect(0, 0, scaled.width(), scaled.height())
            target.moveCenter(rect.center())
            painter.drawPixmap(target, scaled)
            painter.restore()
        else:
            painter.setPen(theme.QFAINT)
            font = painter.font()
            font.setPixelSize(9)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, "no\npreview")

        if hovered:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 105))
            painter.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
            box = QRectF(rect.center().x() - 9, rect.center().y() - 9, 18, 18)
            icons.maximize(painter, box, QColor("white"))

        # A dimmed card alone does not say WHY it is dimmed - a clipping held
        # back as junk and one held back as a repeat look identical. This says
        # which, on the picture itself, where the eye already is.
        if row.clip.duplicate_of:
            self._paint_duplicate_badge(painter, rect)

    def _paint_duplicate_badge(self, painter, rect: QRect) -> None:
        painter.save()
        painter.setOpacity(1.0)          # legible even though the card is dimmed
        font = painter.font()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        text = "DUPLICATE"
        width = painter.fontMetrics().horizontalAdvance(text) + 12
        tag = QRectF(rect.left() + 4, rect.top() + 4, min(width, rect.width() - 8), 15)
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.QDANGER)
        painter.drawRoundedRect(tag, 7, 7)
        painter.setPen(QColor("white"))
        painter.drawText(tag, Qt.AlignCenter, text)
        painter.restore()

    def _paint_fields(self, painter, geo, clip, selected) -> None:
        """The headline box, the address box, or whichever of them there is."""
        if not geo.label.isNull() and geo.label.isValid():
            self._paint_field(
                painter, geo.label, clip, selected, "TITLE",
                clip.effective_label,
                "Headline — leave blank for a clean clipping",
                theme.QINK,
            )
        if not geo.url.isNull() and geo.url.isValid():
            self._paint_field(
                painter, geo.url, clip, selected, "URL", clip.url,
                "Web address — prints under the image",
                QColor("#1D4ED8"),
            )

    def _paint_field(self, painter, rect: QRect, clip, selected, tag: str,
                     text: str, placeholder: str, ink) -> None:
        # The tag is inside the box, at the left, so it reads as part of the
        # field rather than as another line of the card. Without it the two
        # boxes are the same shape and there is nothing to say which is which.
        needs = (tag == "TITLE" and not clip.title_text
                 and not clip.title_in_image)
        if needs:
            border = QColor(theme.FLAG)
        elif selected:
            border = QColor("#93C5FD")
        else:
            border = theme.QHAIRLINE
        painter.setPen(QPen(border, 1))
        painter.setBrush(theme.QSURFACE)
        painter.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)

        tag_font = painter.font()
        tag_font.setPixelSize(9)
        tag_font.setBold(True)
        painter.setFont(tag_font)
        tag_metrics = QFontMetrics(tag_font)
        tag_width = tag_metrics.horizontalAdvance(tag) + 12
        tag_rect = QRectF(rect.left() + 5, rect.top() + 6,
                          tag_width, rect.height() - 12)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#EEF2F7"))
        painter.drawRoundedRect(tag_rect, 5, 5)
        painter.setPen(QColor("#64748B"))
        painter.drawText(tag_rect, Qt.AlignCenter, tag)

        font = painter.font()
        font.setPixelSize(13)
        font.setBold(bool(text.strip()))
        painter.setFont(font)
        metrics = QFontMetrics(font)
        text_rect = rect.adjusted(int(tag_width) + 12, 0, -10, 0)
        if text.strip():
            painter.setPen(theme.QNAVY if selected else ink)
        elif clip.title_in_image and tag == "TITLE":
            painter.setPen(QColor("#8A939B"))
            text = "title already on the clipping — leave blank"
        else:
            painter.setPen(QColor("#B0B7BF"))
            text = placeholder
        painter.drawText(
            text_rect,
            Qt.AlignVCenter | Qt.AlignLeft,
            metrics.elidedText(text, Qt.ElideRight, text_rect.width()),
        )

    def _paint_add(self, painter, hit, hovered: bool, field: str) -> None:
        """The little offer under a card that is missing one of its two boxes."""
        rect = QRectF(hit.rect)
        ink = QColor("#1D4ED8") if field == "url" else theme.QNAVY
        painter.save()
        painter.setPen(QPen(ink, 1))
        painter.setBrush(QColor("#EFF4FF") if hovered else theme.QSURFACE)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
        mark = QRectF(rect.left() + 4, rect.center().y() - 5.5, 11, 11)
        (icons.globe if field == "url" else icons.type_letter)(painter, mark, ink)
        font = painter.font()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(ink)
        painter.drawText(
            QRectF(mark.right() + 3, rect.top(), rect.width() - 20, rect.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            "Add URL" if field == "url" else "Add title")
        painter.restore()

    def _paint_subline(self, painter, rect: QRect, row, clip, opens="") -> None:
        # A clipping that opens a section says so, in the red the report prints
        # it in. Without this the heading existed only inside the export and
        # there was no way to tell, before generating it, that the report would
        # carry one - or which clipping was carrying it.
        if opens:
            font = painter.font()
            font.setPixelSize(10)
            font.setBold(True)
            painter.setFont(font)
            metrics = QFontMetrics(font)
            width = metrics.horizontalAdvance(opens) + 12
            chip = QRectF(rect.left(), rect.top() + 1, min(width, rect.width()),
                          max(13, rect.height() - 2))
            painter.setPen(QPen(theme.QDANGER, 1))
            painter.setBrush(QColor("#FEF2F2"))
            painter.drawRoundedRect(chip.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
            painter.drawText(chip, Qt.AlignCenter,
                             metrics.elidedText(opens, Qt.ElideRight,
                                                int(chip.width()) - 8))
            rect = QRect(rect.left() + int(chip.width()) + 6, rect.top(),
                         max(0, rect.width() - int(chip.width()) - 6),
                         rect.height())

        style = theme.SOURCE_STYLES.get(row.source_kind, theme.SOURCE_STYLES["image"])
        bits = [f"[{style['label']}]"]
        if clip.division:
            bits.append(clip.division)
        bits.append(clip.section.value)
        # Only when the headline above does not already say it. With nothing
        # typed the caption now reads "Ajit, Amritsar, Page 5", and repeating
        # the page here is noise; with a headline typed over it, this line is
        # the only place the page still shows.
        if clip.page and clip.label.strip():
            bits.append(f"p.{clip.page}")
        # Where a clipping came from is part of what it is, and the report
        # prints it under the picture. Showing the site here is how you can tell
        # at a glance that the address was read at all.
        if clip.url.strip():
            bits.append("· " + _site(clip.url))
        if clip.probable_junk:
            bits.append("· probably not a clipping")
        elif clip.title_in_image and not clip.label.strip():
            bits.append("· title is printed on the clipping")
        elif clip.name_source == "caption":
            bits.append("· read from the caption")
        elif clip.name_source == "ocr":
            bits.append("· read from the image")
        elif clip.name_source == "manual":
            bits.append("· typed")

        font = painter.font()
        font.setPixelSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(theme.QDANGER if clip.probable_junk else theme.QFAINT)
        metrics = QFontMetrics(font)
        text = "  ".join(bits)
        painter.drawText(
            rect,
            Qt.AlignVCenter | Qt.AlignLeft,
            metrics.elidedText(text, Qt.ElideRight, rect.width()),
        )

    def _paint_clip_button(self, painter, hit, hovered, entry) -> None:
        rect = QRectF(hit.rect)
        name = hit.name

        if name == "movepad":
            painter.setPen(QPen(theme.QHAIRLINE, 1))
            painter.setBrush(QColor("#F8FAFC"))
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
            return

        if name in ("move_top", "move_up", "move_down", "move_bottom"):
            if hovered:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#FFFFFF"))
                painter.drawRoundedRect(rect, 5, 5)
            box = QRectF(rect.center().x() - 7, rect.center().y() - 7, 14, 14)
            colour = theme.QNAVY if hovered else theme.QMUTED
            {"move_top": icons.chevrons_up, "move_up": icons.chevron_up,
             "move_down": icons.chevron_down,
             "move_bottom": icons.chevrons_down}[name](
                painter, box,
                theme.QORANGE if (hovered and name in ("move_top", "move_bottom"))
                else colour,
            )
            return

        if name == "delete":
            if hovered:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#FEF2F2"))
                painter.drawRoundedRect(rect, 7, 7)
            box = QRectF(rect.center().x() - 8, rect.center().y() - 8, 16, 16)
            icons.trash(painter, box, theme.QDANGER)
            return

        if name == "rotate":
            if hovered:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#EEF2F7"))
                painter.drawRoundedRect(rect, 7, 7)
            box = QRectF(rect.center().x() - 8, rect.center().y() - 8, 16, 16)
            icons.rotate(painter, box, theme.QNAVY if hovered else theme.QMUTED)
            return

        # pill buttons: Split and Merge
        font = painter.font()
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        if name == "merge":
            fg = QColor("white") if hovered else theme.QORANGE
            bg = theme.QORANGE if hovered else QColor(theme.ORANGE_WASH)
            line = QColor(theme.ORANGE)
            label, drawer = "Merge", icons.combine
        else:
            fg = theme.QNAVY
            bg = QColor("#EEF2F7") if hovered else QColor("#F1F5F9")
            line = theme.QHAIRLINE
            label, drawer = "Split", icons.scissors
        painter.setPen(QPen(line, 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        box = QRectF(rect.left() + 7, rect.center().y() - 7, 14, 14)
        drawer(painter, box, fg if name == "merge" else theme.QORANGE)
        painter.setPen(fg)
        painter.drawText(
            QRect(hit.rect.left() + 24, hit.rect.top(), hit.rect.width() - 28,
                  hit.rect.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            label + (" ↓" if name == "merge" else ""),
        )

    # ------------------------------------------------------------ hit test
    def hit_at(self, option_rect: QRect, entry: Entry, point: QPoint):
        """Which named region of a row a point falls in, if any."""
        geo = self.geometry_for(option_rect, entry)
        for hit in geo.hits():
            if hit.name == "movepad":
                continue
            if hit.rect.contains(point):
                return hit
        return None

    def label_rect(self, option_rect: QRect, entry: Entry,
                   field: str = "label") -> QRect:
        geometry = self.geometry_for(option_rect, entry)
        return geometry.url if field == "url" else geometry.label
