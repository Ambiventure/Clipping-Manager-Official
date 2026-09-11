"""The list model behind the review view.

One flat list of entries feeds a single ``QListView``: a group header for each run
of clippings that came from the same file, then the clipping rows underneath it.
Keeping the groups inside the same list rather than nesting scroll areas is what
lets Qt virtualise the whole thing — only the rows on screen are ever painted, so
165 clippings scroll like five.

Thumbnails are rendered once at display size when a clipping is imported and cached
as QPixmaps. The full resolution image is never scaled for display.
"""

from __future__ import annotations

import itertools

import io
from dataclasses import dataclass, field
from typing import Iterable, Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication

from ..core.models import Clip
from ..core import arrange, imageops
from ..core.profiles import NameIndex, apply_to_clip

# Big enough for the sentiment card's picture box, which shows the clipping at
# about 300px wide - a 180px thumbnail upscaled into it looked soft.
THUMB_SIZE = QSize(340, 340)

ENTRY_GROUP = "group"
ENTRY_CLIP = "clip"

# Everything dropped or pasted by hand shares one group and sits at the top of the
# list, in the order it arrived. A new group per drop would scatter a morning's
# WhatsApp images across a dozen one-item brackets.
LOOSE_KEY = "__loose__"
LOOSE_TITLE = "Clipboard images"


def thumbnail_png(clip: Clip, size: QSize = THUMB_SIZE) -> Optional[bytes]:
    """The clipping rendered down to display size, as PNG bytes.

    Kept rather than thrown away: rebuilding 163 of these from the full images
    costs about four seconds on the UI thread, and reloading the saved PNGs costs
    about two tenths. The bytes were already being produced here - only the
    keeping of them is new.
    """
    try:
        image = clip.render()
    except Exception:  # noqa: BLE001 - a broken image must not stop the import
        return None
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    image.thumbnail((size.width(), size.height()))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def pixmap_from_png(data: Optional[bytes]) -> Optional[QPixmap]:
    if not data:
        return None
    pixmap = QPixmap()
    return pixmap if pixmap.loadFromData(data, "PNG") else None


def make_thumbnail(clip: Clip, size: QSize = THUMB_SIZE) -> Optional[QPixmap]:
    """Render one clip down to display size, once, at import."""
    return pixmap_from_png(thumbnail_png(clip, size))


@dataclass
class Row:
    """A clip plus the view-only state that hangs off it."""

    clip: Clip
    id: int
    thumbnail: Optional[QPixmap] = None
    source_kind: str = "image"     # word | pdf | clipboard | image
    source_name: str = ""          # the file it came from
    group_key: str = ""            # rows sharing this sit under one bracket
    # The PNG the thumbnail was built from, kept so restoring a session does not
    # have to re-render every clipping from its full-size image.
    thumb_png: Optional[bytes] = None
    # What this picture is stored under, and the exact bytes that name was
    # worked out from. The name is a digest of the whole picture, so working it
    # out again on every save was a hundred megabytes of reading on the window's
    # thread - measured at 788ms per save on one morning. See _encode_pool.
    blob_name: str = ""
    blob_of: Optional[bytes] = None


@dataclass
class Group:
    """A run of consecutive rows that came from the same file.

    ``key`` alone is not an identity. Once a drop can move a clipping into another
    file's bracket, one key can end up owning two separate runs, and anything that
    addresses a group by key alone - delete, collapse, move - would silently act on
    both. ``occurrence`` numbers the runs sharing a key, and ``ident`` is what the
    rest of the app should use.
    """

    key: str
    title: str
    source_kind: str
    rows: list[Row] = field(default_factory=list)
    collapsed: bool = False
    occurrence: int = 0
    # How many clippings this run really holds, when a filter is showing only
    # some of them. The header then says "3 of 12" rather than claiming 3, which
    # is the same mistake the board made once: a filtered count read as a total.
    total: int = 0

    @property
    def count(self) -> int:
        return len(self.rows)

    @property
    def ident(self) -> str:
        return f"{self.key}#run{self.occurrence}"

    @property
    def row_ids(self) -> list[int]:
        return [r.id for r in self.rows]


@dataclass
class Entry:
    """One line in the flat list: either a group header, or a clipping."""

    kind: str
    group: Optional[Group] = None
    row: Optional[Row] = None
    index_in_all: int = 0          # 1-based position among clippings
    first_in_group: bool = False
    last_in_group: bool = False
    # Whether this row may offer to be stitched to the one below it. False
    # under a lens: the clipping shown underneath may not be the clipping that
    # is actually underneath, and merging the wrong pair is not undoable in any
    # way somebody would notice.
    can_merge: bool = True


# How many pictures are shrunk at once. Pillow lets go of the interpreter while
# it decodes and resizes, so this really is parallel. Measured on the worst file
# of a real morning - a division with 33 clippings - the longest the window went
# unresponsive was 0.771s doing them one at a time, 0.286s with four, 0.216s
# with six, and 0.216s with eight. Six is where it stops paying.
SHRINK_LANES = 6


def _shrink_all(rows: list) -> list:
    """Every row's thumbnail bytes, made by a few threads rather than one.

    Falls back to doing them one at a time if threads cannot be started, because
    a slow import is a great deal better than no import.
    """
    if len(rows) < 2:
        return [thumbnail_png(row.clip) for row in rows]
    try:
        from concurrent.futures import ThreadPoolExecutor

        lanes = min(SHRINK_LANES, len(rows))
        with ThreadPoolExecutor(max_workers=lanes) as pool:
            return list(pool.map(lambda row: thumbnail_png(row.clip), rows))
    except Exception:  # noqa: BLE001 - one at a time, then
        return [thumbnail_png(row.clip) for row in rows]


class ClipModel(QAbstractListModel):
    """Ordered list of clippings. This order is the export order."""

    countsChanged = Signal()
    selectionChanged = Signal()

    def __init__(self, name_index: NameIndex, config: dict, parent=None,
                 ids=None):
        """``ids`` lets several pools share one counter.

        Two pools each starting at 1 would mint the same clip id, and every
        signal in the app carries a bare id - a card dragged on the board would
        resolve to a different clipping of the same id in the report and quietly
        rewrite it. With one counter a foreign id resolves to nothing instead.
        """
        super().__init__(parent)
        self.rows: list[Row] = []
        # row id -> the section heading that row will print. Empty for almost
        # every row: only the one that opens a section carries one.
        self.section_openers: dict[int, str] = {}
        self.by_id_map: dict[int, Row] = {}
        self.selected: set[int] = set()
        self.collapsed_groups: set[str] = set()
        self.collapsed_row_ids: set[int] = set()
        self.name_index = name_index
        self.config = config
        # What is being shown and in what order. A view state: it is never
        # saved, never undoable, and never reaches an exporter. See core/arrange.
        self.lens = arrange.Lens()
        self._book = None
        # Folding while a lens is on is kept apart from the real fold state, so
        # closing the lens gives back exactly the brackets that were open.
        self._lens_collapsed: set = set()
        self._entries: list[Entry] = []
        self._ids = ids if ids is not None else itertools.count(1)
        self._undo_stack = None
        self.duplicate_files = {}

    # ------------------------------------------------------------ plumbing
    # {group_key: the file it repeats}. Filled by the duplicate check; read
    # by the delegate, which paints those file headers dark red. Set per model
    # in __init__ - declared here it was ONE dict shared by both pools, and
    # would have been shared by every newspad as well.
    duplicate_files: dict

    @property
    def book(self):
        """What kind of publication each masthead is. Read once and kept; the
        category editor calls forget_book() when somebody changes it."""
        if self._book is None:
            from ..core import categories

            self._book = categories.load()
        return self._book

    def forget_book(self) -> None:
        self._book = None

    def set_lens(self, lens) -> None:
        """Show this much of the list, in this order. Nothing else changes."""
        self.lens = lens
        if not lens.busy:
            self._lens_collapsed.clear()
        self.rebuild()

    def clear_lens(self) -> None:
        self.set_lens(arrange.Lens())

    def visible_rows(self) -> list:
        """The rows on screen, in the order they are on screen.

        The same list rebuild() draws from, so anything that has to agree with
        what somebody can actually see - selecting a span, counting what is
        shown - asks here rather than working it out again.
        """
        if not self.lens.busy:
            return list(self.rows)
        order = arrange.shown([r.clip for r in self.rows], self.lens, self.book)
        return [self.rows[index] for index in order]

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._entries)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._entries):
            return None
        if role == Qt.UserRole:
            return self._entries[index.row()]
        if role == Qt.ToolTipRole:
            return self._why_flagged(self._entries[index.row()])
        return None

    def _why_flagged(self, entry) -> Optional[str]:
        """Hovering a greyed clipping should say what it repeats.

        The badge says THAT it is a repeat; this says of what. Without it the
        only way to find the other one is to scroll the list looking for a
        picture that resembles this one.
        """
        row = getattr(entry, "row", None)
        clip = getattr(row, "clip", None) if row is not None else None
        if clip is None or not clip.duplicate_of:
            return None
        for other in self.rows:
            if other.clip is not None and other.clip.uid == clip.duplicate_of:
                where = other.source_name or other.clip.source_file or "the list"
                name = other.clip.title_text or "an unnamed clipping"
                break_ = chr(10)
                return (f"Looks like the same cutting as: {name}"
                        + break_ + f"from {where}." + break_ + break_
                        + "Read off this one: "
                        + (clip.ocr_text[:120] or '(nothing could be read)'))
        return "Flagged as a duplicate."

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def entry_at(self, row: int) -> Optional[Entry]:
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    # --------------------------------------------------------- section names
    def recompute_openers(self) -> None:
        """Which rows will carry a section heading when the report is built.

        Decided by the exporter's own rule, on the clippings that are actually
        ticked, so the card cannot promise a heading the report will not print -
        or stay silent about one it will. The card used to read the clipping's
        stored heading instead, which showed nothing at all for a clipping that
        came out of a session saved before the field existed, even though the
        report would still have headed its section.
        """
        from ..export.layout import section_banners

        included = [r for r in self.rows if r.clip.include]
        found = section_banners([r.clip for r in included])
        self.section_openers = {
            included[index].id: text for index, text in found.items()
        }

    def opener_for(self, row_id: int) -> str:
        """The section heading this row will print, or nothing."""
        return getattr(self, "section_openers", {}).get(row_id, "")

    # ------------------------------------------------------------- grouping
    def _file_groups(self) -> list:
        """The brackets: each maximal run of consecutive rows from one file.

        Worked out over the WHOLE list, before any filter, and that is
        deliberate. A run's occurrence number - and therefore its identity, the
        thing collapse and delete and move are addressed by - is assigned by
        order of first appearance. Working it out over the visible rows instead
        would renumber every bracket the moment something was hidden, and a
        gesture aimed at one file would land on another.
        """
        groups: list = []
        seen_keys: dict[str, int] = {}
        for row in self.rows:
            if groups and groups[-1].key == row.group_key:
                groups[-1].rows.append(row)
            else:
                occurrence = seen_keys.get(row.group_key, 0)
                seen_keys[row.group_key] = occurrence + 1
                groups.append(
                    Group(
                        key=row.group_key,
                        title=row.source_name or "Added by hand",
                        source_kind=row.source_kind,
                        rows=[row],
                        occurrence=occurrence,
                    )
                )
        for group in groups:
            group.total = group.count
        return groups

    def _arranged_groups(self, rows: list) -> list:
        """The brackets while an arrangement is on: one per run of the sort key.

        The file brackets are meaningless here - a file's clippings are no
        longer together - so the list is headed by what it is actually sorted
        by. Newspaper, or size and reach, or whatever was chosen.
        """
        groups: list = []
        seen: dict = {}
        for row in rows:
            title = arrange.heading_for(row.clip, self.lens, self.book) or "Everything else"
            if groups and groups[-1].title == title:
                groups[-1].rows.append(row)
                continue
            occurrence = seen.get(title, 0)
            seen[title] = occurrence + 1
            groups.append(Group(key=f"arranged:{title}", title=title,
                                source_kind="arranged", rows=[row],
                                occurrence=occurrence))
        for group in groups:
            group.total = group.count
        return groups

    def rebuild(self) -> None:
        """Recompute the flat entry list from the current row order.

        The order it draws from may be a lens over self.rows, but the numbers it
        writes on the cards are always true positions in self.rows: card 37 has
        to mean page 37 of the report whether or not something is being hidden.
        """
        self.recompute_openers()
        self.beginResetModel()
        entries: list[Entry] = []

        # The true export position of every row, worked out once, before any
        # filtering. This is what goes on the card.
        place = {row.id: index + 1 for index, row in enumerate(self.rows)}

        if self.lens.arranging:
            groups = self._arranged_groups(self.visible_rows())
            folded = self._lens_collapsed
        else:
            groups = self._file_groups()
            folded = None
            if self.lens.filtering:
                keep = {row.id for row in self.visible_rows()}
                for group in groups:
                    group.rows = [r for r in group.rows if r.id in keep]
                groups = [g for g in groups if g.rows]

        for group in groups:
            if folded is None:
                # Collapse follows the rows, not the key: a re-parenting drop can
                # split or merge runs, and the state should stay with the clippings.
                group.collapsed = group.ident in self.collapsed_groups or any(
                    r.id in self.collapsed_row_ids for r in group.rows
                )
            else:
                group.collapsed = group.ident in folded
            entries.append(Entry(ENTRY_GROUP, group=group))
            if group.collapsed:
                continue
            for offset, row in enumerate(group.rows):
                entries.append(
                    Entry(
                        ENTRY_CLIP,
                        group=group,
                        row=row,
                        index_in_all=place.get(row.id, 0),
                        first_in_group=(offset == 0),
                        last_in_group=(offset == group.count - 1),
                        can_merge=not self.lens.busy,
                    )
                )
        self._entries = entries
        self.endResetModel()
        self.countsChanged.emit()

    def group_by_ident(self, ident: str) -> Optional[Group]:
        """The one contiguous run with this identity, or None if it is gone."""
        for entry in self._entries:
            if entry.kind == ENTRY_GROUP and entry.group.ident == ident:
                return entry.group
        return None

    def toggle_group_collapsed(self, ident: str) -> None:
        group = self.group_by_ident(ident)
        # While an arrangement is on the brackets are the sort key's, not the
        # files', so folding them is kept in a set of its own. Closing the lens
        # throws it away and gives back exactly the brackets that were open.
        if self.lens.arranging:
            if ident in self._lens_collapsed:
                self._lens_collapsed.discard(ident)
            else:
                self._lens_collapsed.add(ident)
            self.rebuild()
            return
        ids = set(group.row_ids) if group else set()
        if ident in self.collapsed_groups or (ids & self.collapsed_row_ids):
            self.collapsed_groups.discard(ident)
            self.collapsed_row_ids -= ids
        else:
            self.collapsed_groups.add(ident)
            self.collapsed_row_ids |= ids
        self.rebuild()

    def set_all_collapsed(self, collapsed: bool) -> None:
        """Fold every bracket, or open every one.

        One rebuild at the end rather than one per group: a morning's import is
        six or seven documents, and rebuilding the list that many times in a row
        is visible.
        """
        idents = [entry.group.ident for entry in self._entries
                  if entry.kind == ENTRY_GROUP and entry.group is not None]
        if not idents:
            return
        # While an arrangement is on, these are the sort key's brackets and not
        # the files'. Folding them is kept apart so the real ones come back
        # exactly as they were. See toggle_group_collapsed.
        if self.lens.arranging:
            self._lens_collapsed = set(idents) if collapsed else set()
            self.rebuild()
            return
        if collapsed:
            for ident in idents:
                group = self.group_by_ident(ident)
                self.collapsed_groups.add(ident)
                if group:
                    self.collapsed_row_ids |= set(group.row_ids)
        else:
            self.collapsed_groups.clear()
            self.collapsed_row_ids.clear()
        self.rebuild()

    def shown_count(self) -> int:
        """How many clippings the lens is showing. Never what is exported."""
        return len(self.visible_rows())

    def group_count(self) -> int:
        """How many brackets the list has, collapsed or not."""
        return sum(1 for entry in self._entries if entry.kind == ENTRY_GROUP)

    def all_collapsed(self) -> bool:
        idents = [entry.group.ident for entry in self._entries
                  if entry.kind == ENTRY_GROUP and entry.group is not None]
        return bool(idents) and all(i in self.collapsed_groups for i in idents)

    # -------------------------------------------------------------- reading
    def by_id(self, clip_id: int) -> Clip:
        return self.by_id_map[clip_id].clip

    def row_for(self, clip_id: int) -> Optional[Row]:
        return self.by_id_map.get(clip_id)

    def position_of(self, clip_id: int) -> int:
        for i, row in enumerate(self.rows):
            if row.id == clip_id:
                return i
        return -1

    def entry_row_for_clip(self, clip_id: int) -> int:
        for i, entry in enumerate(self._entries):
            if entry.kind == ENTRY_CLIP and entry.row.id == clip_id:
                return i
        return -1

    @property
    def clip_count(self) -> int:
        return len(self.rows)

    @property
    def included_count(self) -> int:
        return sum(1 for r in self.rows if r.clip.include)

    @property
    def unnamed_count(self) -> int:
        """Clippings still needing a caption typed. Ones whose masthead is printed
        on the picture do not count: those pages carry their own title."""
        return sum(
            1 for r in self.rows
            if not r.clip.title_text and not r.clip.title_in_image
        )

    # ------------------------------------------------------------ selection
    def set_selected(self, ids: Iterable[int], selected: bool) -> None:
        for clip_id in ids:
            if selected:
                self.selected.add(clip_id)
            else:
                self.selected.discard(clip_id)
        self.refresh_all()
        self.selectionChanged.emit()

    def select_only(self, ids: Iterable[int]) -> None:
        self.selected = set(ids)
        self.refresh_all()
        self.selectionChanged.emit()

    def clear_selection(self) -> None:
        if not self.selected:
            return
        self.selected.clear()
        self.refresh_all()
        self.selectionChanged.emit()

    def select_range(self, from_id: int, to_id: int) -> None:
        # Across the rows on screen, not across the list. With a filter on, the
        # two ends of a shift-click can have hidden clippings between them, and
        # selecting those would mean a delete aimed at four cards took twelve.
        shown = self.visible_rows()
        where = {row.id: index for index, row in enumerate(shown)}
        a, b = where.get(from_id, -1), where.get(to_id, -1)
        if a < 0 or b < 0:
            return
        lo, hi = min(a, b), max(a, b)
        self.selected.update(r.id for r in shown[lo : hi + 1])
        self.refresh_all()
        self.selectionChanged.emit()

    def is_selected(self, clip_id: int) -> bool:
        return clip_id in self.selected

    # -------------------------------------------------------- list surgery
    def make_rows(
        self,
        clips: list[Clip],
        source_kind: str,
        source_name: str,
        group_key: str,
    ) -> list[Row]:
        """Wrap raw clips as rows, parse their captions and build thumbnails."""
        rows = []
        for clip in clips:
            apply_to_clip(clip, self.config, self.name_index)
            # No fingerprints here any more. They are cheap each - about
            # thirteen thousandths - but a morning is a hundred and twenty
            # clippings, and taking two of them per clipping put three seconds
            # of dead window in the middle of an import. The background reader
            # takes them alongside the headline, and duplicates._ensure_prints
            # catches anything that reaches a comparison without one.
            if clip.probable_junk:
                clip.include = False
            rows.append(Row(
                clip=clip,
                id=next(self._ids),
                source_kind=source_kind,
                source_name=source_name,
                group_key=group_key,
            ))

        # The pictures are shrunk by several threads at once, and only the last
        # step - handing the finished bytes to Qt - is done here. Measured on a
        # real morning: shrinking was 2.35s of dead window in blocks of up to
        # three quarters of a second, and what is left on this thread is 0.20s
        # for a hundred and forty clippings.
        for row, png in zip(rows, _shrink_all(rows)):
            row.thumb_png = png
            row.thumbnail = pixmap_from_png(png)
        return rows

    def append(self, rows: list[Row]) -> None:
        if not rows:
            return
        self.rows.extend(rows)
        for row in rows:
            self.by_id_map[row.id] = row
        self.rebuild()

    def insert(self, rows: list[Row], at: int) -> None:
        if not rows:
            return
        at = max(0, min(at, len(self.rows)))
        self.rows[at:at] = rows
        for row in rows:
            self.by_id_map[row.id] = row
        self.rebuild()

    def loose_insert_point(self) -> int:
        """Where the next hand-added clipping goes: after the last loose one.

        Drop three images and they land first, second, third at the top of the
        list rather than at the bottom behind the division documents.
        """
        last = -1
        for i, row in enumerate(self.rows):
            if row.group_key == LOOSE_KEY:
                last = i
        return last + 1

    def replace_all(self, rows: list[Row]) -> None:
        self.rows = list(rows)
        self.by_id_map = {r.id: r for r in self.rows}
        self.selected = {i for i in self.selected if i in self.by_id_map}
        self.rebuild()

    def refresh_clip(self, clip_id: int) -> None:
        # Changing one clipping's section, or unticking it, can move a heading
        # onto a different row, so the whole map is worked out again and the
        # whole list repainted. It is one pass over the rows on an edit, which
        # is not something a person can type fast enough to notice.
        before = dict(getattr(self, "section_openers", {}))
        self.recompute_openers()
        if before != self.section_openers:
            self.refresh_all()
            return
        row = self.entry_row_for_clip(clip_id)
        if row >= 0:
            index = self.index(row, 0)
            self.dataChanged.emit(index, index)
        self.countsChanged.emit()

    def refresh_all(self) -> None:
        self.recompute_openers()
        if self._entries:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._entries) - 1, 0)
            )
        self.countsChanged.emit()

    # ---------------------------------------------------------------- misc
    def undo_stack(self):
        return self._undo_stack

    def set_undo_stack(self, stack) -> None:
        self._undo_stack = stack
