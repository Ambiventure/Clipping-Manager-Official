"""Undo commands. Every change to a clipping goes through one of these.

Nothing mutates the model directly. A misdrag that reorders 165 clippings with no
way back is the difference between a tool someone trusts and one they don't, so the
reorder, the batch delete and the merge are all commands like everything else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable, Optional

from PySide6.QtGui import QUndoCommand

from ..core import imageops
from ..core.models import (LAST_BAND, UNASSIGNED, arrival_of,
                           priority_of, sort_band)

if TYPE_CHECKING:  # pragma: no cover
    from .model import ClipModel, Row


class _Base(QUndoCommand):
    def __init__(self, model: "ClipModel", text: str):
        super().__init__(text)
        self.model = model


class EditUrl(_Base):
    """Change the address printed under a digital clipping.

    Digital coverage is a screenshot of a web page: what has to travel with it is
    the link, and the link belongs under the picture rather than over it. It gets
    its own command so undo reads honestly, and so the two fields cannot be
    confused for one another.

    It touches the address and nothing else. It used to clear the headline as
    well, back when one box on the card had to serve for both and had to guess
    from what was typed which of them was meant; the card has a box for each of
    them now, so a clipping can carry a headline and an address at once - which
    the 360 Degree document's clippings do.
    """

    def __init__(self, model: "ClipModel", clip_id: int, value: str):
        super().__init__(model, "Link changed")
        self.clip_id = clip_id
        self.new_value = value
        self.old_value = model.by_id(clip_id).url

    def id(self) -> int:  # noqa: A003 - Qt's name
        return 3000 + (self.clip_id & 0xFFFF)

    def mergeWith(self, other: QUndoCommand) -> bool:
        if isinstance(other, EditUrl) and other.clip_id == self.clip_id:
            self.new_value = other.new_value
            return True
        return False

    def redo(self) -> None:
        self.model.by_id(self.clip_id).url = self.new_value
        self.model.refresh_clip(self.clip_id)

    def undo(self) -> None:
        self.model.by_id(self.clip_id).url = self.old_value
        self.model.refresh_clip(self.clip_id)


class EditLabel(_Base):
    """Change the caption that prints above a clipping.

    Consecutive keystrokes in the same field merge into one undo step; otherwise
    undo walks back a character at a time and is useless.
    """

    def __init__(self, model: "ClipModel", clip_id: int, value: str):
        super().__init__(model, "Label changed")
        self.clip_id = clip_id
        self.new_value = value
        self.old_value = model.by_id(clip_id).label
        # Emptying the box is a decision, not an absence. Recorded here so undo
        # restores the caption along with the typing.
        self.was_titleless = model.by_id(clip_id).no_title
        self.now_titleless = not (value or "").strip()

    def id(self) -> int:  # noqa: A003 - Qt's name
        return 1000 + (self.clip_id & 0xFFFF)

    def mergeWith(self, other: QUndoCommand) -> bool:
        if isinstance(other, EditLabel) and other.clip_id == self.clip_id:
            self.new_value = other.new_value
            self.now_titleless = other.now_titleless
            return True
        return False

    def redo(self) -> None:
        clip = self.model.by_id(self.clip_id)
        clip.label = self.new_value
        clip.no_title = self.now_titleless
        self.model.refresh_clip(self.clip_id)

    def undo(self) -> None:
        clip = self.model.by_id(self.clip_id)
        clip.label = self.old_value
        clip.no_title = self.was_titleless
        self.model.refresh_clip(self.clip_id)


# What the undo menu calls each field. Without this a field whose attribute
# name has an underscore reads as "Section_Title changed".
FIELD_NAMES = {
    "newspaper": "Newspaper",
    "edition": "Edition",
    "page": "Page",
    "section": "Section",
    "section_title": "Section heading",
    "section_key": "Section heading",
    "url": "Link",
}


class EditField(_Base):
    """Change newspaper / edition / page / section on one clipping."""

    def __init__(self, model: "ClipModel", clip_id: int, field: str, value: Any):
        super().__init__(
            model, f"{FIELD_NAMES.get(field, field.title())} changed")
        clip = model.by_id(clip_id)
        self.clip_id = clip_id
        self.field = field
        self.new_value = value
        self.old_value = getattr(clip, field)
        self.old_source = clip.name_source
        self.old_confidence = clip.name_confidence

    def id(self) -> int:  # noqa: A003
        return 2000 + (hash((self.clip_id, self.field)) & 0xFFFF)

    def mergeWith(self, other: QUndoCommand) -> bool:
        if (
            isinstance(other, EditField)
            and (other.clip_id, other.field) == (self.clip_id, self.field)
        ):
            self.new_value = other.new_value
            return True
        return False

    def redo(self) -> None:
        clip = self.model.by_id(self.clip_id)
        setattr(clip, self.field, self.new_value)
        if self.field in ("newspaper", "edition", "page"):
            clip.name_source = "manual"
            clip.name_confidence = 1.0
        self.model.refresh_clip(self.clip_id)

    def undo(self) -> None:
        clip = self.model.by_id(self.clip_id)
        setattr(clip, self.field, self.old_value)
        clip.name_source = self.old_source
        clip.name_confidence = self.old_confidence
        self.model.refresh_clip(self.clip_id)


class FillFromCopy(_Base):
    """A caption or a link copied in WhatsApp, put on one clipping in one step.

    Everything it may change is recorded before and after, so undo puts back
    exactly what was there. It never merges with anything: one copy, one step,
    so "undo that" means the copy and nothing else. The printed headline is not
    among the fields - a headline somebody typed keeps printing, with the page
    added after it.
    """

    # The division too: a caption typed with a division's short form ("HT
    # LKO") files a clipping that had none under that division, and one undo
    # has to take back the caption and the division together.
    FIELDS = ("caption_raw", "newspaper", "edition", "page", "name_source",
              "name_confidence", "no_title", "url", "show_url_box", "division")

    def __init__(self, model: "ClipModel", clip_id: int, values: dict,
                 text: str = "Caption copied"):
        super().__init__(model, text)
        clip = model.by_id(clip_id)
        self.clip_id = clip_id
        self.before = {name: getattr(clip, name) for name in self.FIELDS}
        self.after = {**self.before,
                      **{key: value for key, value in values.items()
                         if key in self.FIELDS}}

    def _put(self, values: dict) -> None:
        row = self.model.row_for(self.clip_id)
        if row is None:
            return
        for key, value in values.items():
            setattr(row.clip, key, value)
        self.model.refresh_clip(self.clip_id)
        # A card that gains its link box as well is a taller row.
        self.model.layoutChanged.emit()

    def redo(self) -> None:
        self._put(self.after)

    def undo(self) -> None:
        self._put(self.before)


class CaptionAsTyped(FillFromCopy):
    """A copied caption the reader could not take apart, printed as written.

    The headline box is the one field that prints anything above the picture
    exactly as typed, so that is where the words go - flagged, because nobody
    has checked them, and one undo step like every other copy.
    """

    FIELDS = FillFromCopy.FIELDS + ("label",)

    def __init__(self, model: "ClipModel", clip_id: int, values: dict,
                 text: str = "Caption copied as typed"):
        super().__init__(model, clip_id, values, text)


class PutInEnglish(FillFromCopy):
    """A card's Hindi put into English, in one step: the caption out of the
    headline box and into the fields, or the fields themselves respelt.

    The headline IS among the fields here, unlike a copied caption: this is
    the one action that deliberately empties it, because what it held was a
    caption and not a headline. Undo puts the Hindi back exactly.
    """

    FIELDS = ("label", "no_title", "caption_raw", "newspaper", "edition",
              "page", "name_source", "name_confidence")

    def __init__(self, model: "ClipModel", clip_id: int, values: dict,
                 text: str = "Put in English"):
        super().__init__(model, clip_id, values, text)


class SetFieldOnMany(_Base):
    """Set one field across a selection, in a single undo step."""

    def __init__(self, model: "ClipModel", clip_ids: Iterable[int], field: str, value):
        ids = list(clip_ids)
        super().__init__(model, f"{field.title()} set on {len(ids)} clippings")
        self.ids = ids
        self.field = field
        self.value = value
        self.previous = [
            (getattr(model.by_id(i), field), model.by_id(i).name_source,
             model.by_id(i).name_confidence)
            for i in ids
        ]

    def redo(self) -> None:
        for clip_id in self.ids:
            clip = self.model.by_id(clip_id)
            setattr(clip, self.field, self.value)
            if self.field in ("newspaper", "edition", "page"):
                clip.name_source = "manual"
                clip.name_confidence = 1.0
        self.model.refresh_all()

    def undo(self) -> None:
        for clip_id, (value, source, confidence) in zip(self.ids, self.previous):
            clip = self.model.by_id(clip_id)
            setattr(clip, self.field, value)
            clip.name_source = source
            clip.name_confidence = confidence
        self.model.refresh_all()


class SetIncluded(_Base):
    """Include or exclude clippings."""

    def __init__(self, model: "ClipModel", clip_ids: Iterable[int], included: bool):
        ids = list(clip_ids)
        verb = "included" if included else "excluded"
        super().__init__(
            model, f"{len(ids)} clippings {verb}" if len(ids) > 1 else f"Clipping {verb}"
        )
        self.ids = ids
        self.included = included
        self.previous = [model.by_id(i).include for i in ids]
        # What the duplicate check thought, so undo can put that back too.
        self.was_duplicate = [
            (model.by_id(i).duplicate_of, model.by_id(i).not_duplicate,
             model.by_id(i).excluded_as_duplicate) for i in ids
        ]

    def redo(self) -> None:
        for clip_id in self.ids:
            clip = self.model.by_id(clip_id)
            clip.include = self.included
            if self.included and (clip.duplicate_of
                                  or clip.excluded_as_duplicate):
                # Ticking a flagged repeat back on says the same thing as
                # pressing "Not a Duplicate" in the review window: keep it.
                # It has to be written down, or the check that runs a moment
                # later simply switches it off again and the tick appears not
                # to work.
                clip.not_duplicate = True
                clip.duplicate_of = None
                clip.excluded_as_duplicate = False
        self.model.refresh_all()

    def undo(self) -> None:
        for clip_id, was, dupe in zip(self.ids, self.previous,
                                      self.was_duplicate):
            clip = self.model.by_id(clip_id)
            clip.include = was
            clip.duplicate_of, clip.not_duplicate, clip.excluded_as_duplicate = dupe
        self.model.refresh_all()


class Rotate(_Base):
    """Turn clippings 90 degrees. Rotation is applied on render, never baked in."""

    def __init__(self, model: "ClipModel", clip_ids: Iterable[int], degrees: int = 90):
        ids = list(clip_ids)
        super().__init__(
            model, f"{len(ids)} clippings rotated" if len(ids) > 1 else "Clipping rotated"
        )
        self.ids = ids
        self.degrees = degrees

    def _turn(self, degrees: int) -> None:
        from .model import pixmap_from_png, thumbnail_png

        for clip_id in self.ids:
            row = self.model.row_for(clip_id)
            if row is None:
                continue
            row.clip.rotation = (row.clip.rotation + degrees) % 360
            # Keep the bytes in step with the picture, or a restored session
            # would show the clipping at its old angle.
            row.thumb_png = thumbnail_png(row.clip)
            row.thumbnail = pixmap_from_png(row.thumb_png)
        self.model.refresh_all()

    def redo(self) -> None:
        self._turn(self.degrees)

    def undo(self) -> None:
        self._turn(-self.degrees)


def _identity(rows) -> dict:
    """Which bracket each row belongs to, captured by value."""
    return {r.id: (r.group_key, r.source_kind, r.source_name,
                   getattr(r, "home_title", ""), getattr(r, "home_kind", ""))
            for r in rows}


def _restore(rows, identity: dict) -> None:
    for row in rows:
        remembered = identity.get(row.id)
        if remembered:
            (row.group_key, row.source_kind, row.source_name,
             row.home_title, row.home_kind) = remembered


def reparent(rows, clip_ids, group_key: str, source_kind: str, source_name: str) -> None:
    """Move rows into another file's bracket, in place."""
    wanted = set(clip_ids)
    for row in rows:
        if row.id in wanted:
            row.group_key = group_key
            row.source_kind = source_kind
            row.source_name = source_name


class SetCrop(_Base):
    """Trim a clipping, or put its edges back.

    The picture itself is never cut: the crop is a rectangle stored with the
    clipping and applied when it is drawn, so undo is exact and nothing is
    lost. The thumbnail is rebuilt here, or the list would go on showing the
    untrimmed picture until the session was reopened.
    """

    def __init__(self, model: "ClipModel", clip_id: int, crop, text: str = "Trimmed"):
        super().__init__(model, text)
        self.clip_id = clip_id
        self.after = crop
        self.before = model.by_id(clip_id).crop

    def _put(self, crop) -> None:
        from .model import pixmap_from_png, thumbnail_png

        row = self.model.row_for(self.clip_id)
        if row is None:
            return
        row.clip.crop = crop
        row.thumb_png = thumbnail_png(row.clip)
        row.thumbnail = pixmap_from_png(row.thumb_png)
        self.model.refresh_clip(self.clip_id)
        self.model.layoutChanged.emit()

    def redo(self) -> None:
        self._put(self.after)

    def undo(self) -> None:
        self._put(self.before)


class Reorder(_Base):
    """Any change of order, and any change of which bracket a row sits in.

    Rows are shared objects, so restoring the order alone is not enough: a drop
    that re-files a clipping into another document's bracket mutates the row
    itself. Undo would then put it back in position but leave it filed under the
    wrong document for good - a corruption only noticed at export. So the bracket
    identity is snapshotted by value on both sides and restored with the order.
    """

    def __init__(self, model: "ClipModel", new_rows: list, text: str):
        super().__init__(model, text)
        self.before = list(model.rows)
        self.after = list(new_rows)
        self.identity_before = _identity(self.before)
        self.identity_after = _identity(self.after)

    def capture_after(self) -> None:
        """Re-read the identities, for a caller that re-parents after constructing."""
        self.identity_after = _identity(self.after)

    def redo(self) -> None:
        _restore(self.after, self.identity_after)
        self.model.replace_all(list(self.after))

    def undo(self) -> None:
        _restore(self.before, self.identity_before)
        self.model.replace_all(list(self.before))


def _in_scope(model) -> bool:
    """Whether the model is showing one category of the board (model.Scope)."""
    return getattr(model, "scope", None) is not None


def _holds(model, row) -> bool:
    return not _in_scope(model) or model.in_scope(row)


def _weave(model: "ClipModel", scoped_new: list) -> list:
    """The whole pool, with the scope's rows laid back in their new order.

    A gesture in an opened-out category decides an order among that
    category's clippings and nothing else. So its rows go back into the slots
    they already hold, in the new order, and every clipping of another
    category or division keeps its exact place - the place the other three
    columns and the dossier read. It lives here, inside the ordering helpers,
    so no caller can build an order from the category's rows and forget to
    put the rest back.
    """
    slots = [index for index, row in enumerate(model.rows) if model.in_scope(row)]
    # Only a helper's own reordering of the scope comes here. Anything else
    # is taken as no change rather than losing a clipping - and that has to
    # be judged by which rows, not how many: a list of the right length with
    # one row twice, or one from another category, would lay a clipping
    # into two slots and drop another from the pool.
    if sorted(map(id, scoped_new)) != sorted(id(model.rows[i]) for i in slots):
        return list(model.rows)
    woven = list(model.rows)
    for index, row in zip(slots, scoped_new):
        woven[index] = row
    return woven


# ------------------------------------------------------------------ priority
#
# THE LIST IS A SORT. What is on screen, and what is exported with it, is
# always the clippings in order of (priority, arrival): priority 1 first, down
# to 5, and then everything with no priority set, in the order it came in.
# Nothing else decides where a clipping sits.
#
# Two numbers, and they do different jobs. The PRIORITY is what the bubbles in
# the preview set, and setting one never touches the other number - which is
# why pressing the lit bubble again drops the clipping back exactly where it
# arrived. The ARRIVAL is given once, when the clipping comes in, and is
# rewritten only when somebody moves that clipping by hand: a move puts its
# number between its new neighbours' numbers, so the sort produces the
# arrangement they just made, and no other clipping is touched.
#
# A list nobody has set a priority on is one block in arrival order, which is
# the list exactly as it was before any of this existed.


def band_of(row) -> int:
    """Which block of the list this row sits in: 1 to 5, then 6 for unset."""
    return sort_band(getattr(row, "clip", None))


def arrival_of_row(row) -> float:
    return arrival_of(getattr(row, "clip", None))


def banded(rows: list, bands: Optional[dict] = None,
           arrivals: Optional[dict] = None) -> list:
    """These rows in the order the list shows them.

    ``bands`` and ``arrivals`` override the block and the arrival number of
    some row ids - what a change about to be made would do to them - so the
    order after it can be worked out before any of it is written down.
    """
    bands, arrivals = bands or {}, arrivals or {}

    def key(row):
        return (bands.get(row.id, band_of(row)),
                arrivals.get(row.id, arrival_of_row(row)))

    return sorted(rows, key=key)


def in_levels(source: list, clip_ids: Iterable[int], within) -> list:
    """Reorder each block the selection touches, leaving every other row put.

    ``within`` is handed one block's rows and returns them in a new order. The
    blocks are contiguous in a sorted list, so this is "move it among its own
    priority and no further" - what the arrows and the move pad do.
    """
    ids = set(clip_ids)
    out = list(source)
    levels = sorted({band_of(row) for row in source if row.id in ids})
    for level in levels:
        slots = [i for i, row in enumerate(source) if band_of(row) == level]
        arranged = within([source[i] for i in slots])
        if sorted(map(id, arranged)) != sorted(id(source[i]) for i in slots):
            continue        # a helper that lost or gained a row changes nothing
        for index, row in zip(slots, arranged):
            out[index] = row
    return out


def arrivals_for(arrangement: list, moved_ids: Iterable[int],
                 bands: Optional[dict] = None) -> dict:
    """The arrival numbers that make this arrangement what the sort produces.

    Only the rows that moved get a new number, and each gets one between its
    new neighbours in its own block. Everything else keeps the number it came
    in with - which is the whole reason a cleared priority puts a clipping back
    where it arrived rather than wherever it had been lifted to.
    """
    moved = set(moved_ids)
    bands = bands or {}

    def block(row):
        return bands.get(row.id, band_of(row))

    plan: dict = {}
    index, count = 0, len(arrangement)
    while index < count:
        if arrangement[index].id not in moved:
            index += 1
            continue
        first = index
        while index < count and arrangement[index].id in moved:
            index += 1
        run = arrangement[first:index]
        here = block(run[0])
        above = next((arrival_of_row(row) for row in reversed(arrangement[:first])
                      if row.id not in moved and block(row) == here), None)
        below = next((arrival_of_row(row) for row in arrangement[index:]
                      if row.id not in moved and block(row) == here), None)
        if above is None and below is None:
            above, below = 0.0, float(len(run) + 1)
        elif above is None:
            above = below - 1.0
        elif below is None:
            below = above + 1.0
        step = (below - above) / (len(run) + 1)
        for place, row in enumerate(run, start=1):
            plan[row.id] = above + step * place
    return plan


def level_at(rows: list, clip_ids: Iterable[int]) -> Optional[int]:
    """The priority a block of rows has landed among, or None if it is alone.

    What a drag and drop means: put here. Here has a priority - the clippings
    around the place it was dropped - and the dropped clipping takes it, which
    is the only reading that keeps the list in order after a drop. The row
    ABOVE decides when the block straddles a boundary, because a clipping is
    dropped underneath the one it was dragged past. 6, the block with no
    priority set, comes back as 0.
    """
    ids = set(clip_ids)
    places = [index for index, row in enumerate(rows) if row.id in ids]
    if not places:
        return None
    above = next((band_of(rows[i]) for i in range(places[0] - 1, -1, -1)
                  if rows[i].id not in ids), None)
    below = next((band_of(rows[i]) for i in range(places[-1] + 1, len(rows))
                  if rows[i].id not in ids), None)
    if above is None and below is None:
        return None
    # A DROP ONLY CHANGES THE PRIORITY WHEN THE PLACE ASKS FOR IT.
    #
    # The list is sorted, so most drops land somewhere the clipping could sit
    # anyway - at the top of the unassigned run, say, with the last priority 5
    # above it. Reading the one above as the answer would have made that a
    # demotion to 5, which is not what anybody dragging it there meant. So the
    # clipping keeps its own priority whenever its own priority still fits
    # between the neighbours, and takes one only when it cannot: dropped in
    # among the 1s it becomes a 1, dragged down into the unassigned it loses
    # its priority.
    here = {band_of(rows[i]) for i in places}
    own = here.pop() if len(here) == 1 else None
    fits = (own is not None
            and (above is None or above <= own)
            and (below is None or own <= below))
    if fits:
        landed = own
    else:
        landed = below if above is None else above
    return 0 if landed == LAST_BAND else landed


def ensure_arrivals(model: "ClipModel") -> int:
    """Give every clipping without an arrival number one, moving nothing.

    A session saved before 2.0.34 has no arrival numbers at all, and its
    clippings come back through the session reader, not through make_rows -
    so every one of them sat at 0 and tied with every other. The sort kept
    ties where they stood, which meant that taking a priority off left the
    clipping wherever the priority had lifted it to, instead of putting it
    back in its place in the list.

    Numbered from the list as it stands, so nothing on screen moves: when
    none has a number they are counted 1, 2, 3 down the list, and when only
    some lack one each gets a number between its neighbours. Returns how many
    were given one.
    """
    rows = [row for row in model.rows if getattr(row, "clip", None) is not None]
    missing = [row for row in rows if not arrival_of(row.clip)]
    if not missing:
        return 0
    if len(missing) == len(rows):
        for place, row in enumerate(rows, start=1):
            row.clip.order_seq = float(place)
        return len(rows)
    for row_id, arrival in arrivals_for(model.rows, [r.id for r in missing]).items():
        clip = model.by_id(row_id)
        if clip is not None:
            clip.order_seq = arrival
    return len(missing)


class Arrange(Reorder):
    """One step: an order, the arrival numbers that hold it, and a priority.

    Everything that moves a clipping comes through here, because the three go
    together. A priority with no reorder would leave the list unsorted; a
    reorder with no numbers would be undone by the next sort; and two steps in
    the history would make Ctrl+Z take back half of what somebody did.
    """

    def __init__(self, model: "ClipModel", rows: list, text: str,
                 moved_ids: Iterable[int] = (), level: Optional[int] = None,
                 level_ids: Optional[Iterable[int]] = None):
        ensure_arrivals(model)
        moved = [i for i in moved_ids if model.row_for(i) is not None]
        # Which clippings take the new level is not always which ones moved: a
        # bubble gives a level to a clipping that is renumbered by nothing,
        # and a drop does both to the same one.
        self.ids = [i for i in (moved if level_ids is None else level_ids)
                    if model.row_for(i) is not None]
        self.level = level
        self.was_level = {i: priority_of(model.by_id(i)) for i in self.ids}
        bands = ({i: (level or LAST_BAND) for i in self.ids}
                 if level is not None else {})
        self.arrivals = arrivals_for(rows, moved, bands)
        self.was_arrival = {i: arrival_of(model.by_id(i)) for i in self.arrivals}
        # Sorted on what the change is about to make true, not on what is still
        # written on the clippings - otherwise the arrangement somebody just
        # made is undone by the very sort that is meant to hold it.
        super().__init__(model, banded(rows, bands, self.arrivals), text)

    def _write(self, levels: dict, arrivals: dict) -> None:
        for clip_id, level in levels.items():
            clip = self.model.by_id(clip_id)
            if clip is not None:
                clip.priority = level
        for clip_id, arrival in arrivals.items():
            clip = self.model.by_id(clip_id)
            if clip is not None:
                clip.order_seq = arrival

    def redo(self) -> None:
        self._write({i: self.level for i in self.ids} if self.level is not None
                    else {}, self.arrivals)
        super().redo()

    def undo(self) -> None:
        self._write(self.was_level if self.level is not None else {},
                    self.was_arrival)
        super().undo()


class SetPriority(Arrange):
    """A priority bubble: the level, and the place in the list it means.

    Nothing is renumbered. The clipping sorts into its new block by the number
    it came in with, so a clipping given priority 1 sits among the other 1s in
    arrival order, and one whose priority is cleared drops back among the
    unassigned exactly where it arrived.
    """

    def __init__(self, model: "ClipModel", clip_ids: Iterable[int], level: int,
                 text: str = ""):
        # Before anything is sorted: a clipping with no arrival number has no
        # place to go back to, and would sort to the top of whichever block it
        # lands in.
        ensure_arrivals(model)
        ids = [i for i in clip_ids if model.row_for(i) is not None]
        bands = {i: (level or LAST_BAND) for i in ids}
        said = text or (
            ("Priority cleared" if level == UNASSIGNED else f"Priority {level}")
            if len(ids) == 1 else
            (f"Priority cleared for {len(ids)} clippings" if level == UNASSIGNED
             else f"Priority {level} for {len(ids)} clippings"))
        super().__init__(model, banded(model.rows, bands), said,
                         moved_ids=(), level=level, level_ids=ids)


def move_to(model: "ClipModel", clip_ids: Iterable[int], target: int,
            rows: list | None = None) -> list:
    """Row order with the given clippings lifted out and dropped at ``target``.

    ``target`` is a place in ``rows``, which is the whole pool unless given.
    Under a scope it is still a place in the whole pool - what a drop on the
    list works out - and is turned into a place in the category first.
    """
    if rows is None and _in_scope(model):
        inside = sum(1 for r in model.rows[:target] if model.in_scope(r))
        return _weave(model, move_to(model, clip_ids, inside,
                                     rows=model.scoped_rows()))
    source = model.rows if rows is None else rows
    ids = set(clip_ids)
    moving = [r for r in source if r.id in ids]
    rest = [r for r in source if r.id not in ids]
    above = sum(1 for r in source[:target] if r.id in ids)
    at = max(0, min(target - above, len(rest)))
    return rest[:at] + moving + rest[at:]


# ------------------------------------------------------------ Move to a file
#
# "Move to:" on the selection bar files the ticked clippings under another
# file's bracket, at its end - what the earlier AI Studio version called moving
# them to another category. Two things make it more than a reorder.
#
# The bracket is Row.group_key and nothing else. The file name and kind on the
# row say where the picture really came from - the card's tag, the preview, the
# duplicate review all show them - so they are left alone.
#
# And a section heading belongs to ONE clipping, while which clippings print
# under it depends only on order. Moving the clipping that opens ELECTRONIC MEDIA
# would take the heading with it, and the clippings it leaves behind would print
# under whatever came before. So the heading is handed to the next clipping that
# stays, and a move that would still change where any heading prints is refused.
# Every clipping that stays prints under exactly the heading it did before.

@dataclass
class MovePlan:
    """What a move into a file would do, worked out without doing any of it."""

    run_ident: str
    run_key: str
    run_title: str
    run_kind: str
    moving: list                 # ids that change file, in list order
    already: list                # ticked ids already in that file: they stay put
    rows_after: list
    fields: list = field(default_factory=list)    # (clip id, field, old, new)
    handoffs: list = field(default_factory=list)  # (from id, to id, words)
    now_under: str = ""          # the heading the moved ones print under after
    was_under: list = field(default_factory=list)
    refused: str = ""            # why not, in words for the person
    refused_words: str = ""      # the heading that stopped it


def _stored_words(clip, chosen) -> str:
    """The heading words a clipping carries, printing or not."""
    return (clip.section_title or "").strip() or (
        chosen.words_for(clip.section_key) if clip.section_key else "")


def plan_move_into(model: "ClipModel", clip_ids: Iterable[int], run) -> MovePlan:
    """Work out moving these clippings to the end of ``run``. Changes nothing."""
    from ..core import sections as section_list
    from .model import heading_over, openers_of

    wanted = set(clip_ids)
    in_run = set(run.row_ids)
    # Under a scope only the category's own clippings can move. One outside
    # it would be filed under the bracket without being moved at all.
    ordered = [r.id for r in model.rows if r.id in wanted and _holds(model, r)]
    plan = MovePlan(
        run_ident=run.ident, run_key=run.key, run_title=run.title,
        run_kind=run.source_kind,
        moving=[i for i in ordered if i not in in_run],
        already=[i for i in ordered if i in in_run],
        rows_after=list(model.rows),
    )
    if not plan.moving:
        return plan
    if _in_scope(model):
        scoped = model.scoped_rows()
        places = [r.id for r in scoped]
        last = run.rows[-1].id
        at = places.index(last) + 1 if last in places else len(scoped)
        plan.rows_after = _weave(model, move_to(model, plan.moving, at,
                                                rows=scoped))
    else:
        plan.rows_after = move_to(model, plan.moving,
                                  model.position_of(run.rows[-1].id) + 1)
    # A pool that prints no section headings - the board's, whose dossier has
    # none - has no heading to hand on and no move to refuse for one.
    if not getattr(model, "headings_print", True):
        return plan
    movers = set(plan.moving)
    before = openers_of(model.rows)
    expected = {i: w for i, w in before.items() if i not in movers}
    overrides: dict = {}
    chosen = section_list.load()
    included = [r for r in model.rows if r.clip.include]
    place = {r.id: n + 1 for n, r in enumerate(model.rows)}

    for index, row in enumerate(included):
        if row.id not in movers or row.id not in before:
            continue
        words = before[row.id]
        successor = None
        for later in included[index + 1:]:
            if later.id in before:
                break                   # the next heading starts: nobody stays
            if later.id not in movers:
                successor = later
                break
        if successor is None:
            plan.refused = (f"these are all the clippings under {words}, so the "
                            f"heading would go with them")
            plan.refused_words = words
            return plan
        carried = _stored_words(successor.clip, chosen)
        if carried and carried != words:
            plan.refused = (f"{words} could not be passed on to No. "
                            f"{place[successor.id]}, which has a heading of its own")
            plan.refused_words = words
            return plan
        expected[successor.id] = words
        plan.handoffs.append((row.id, successor.id, words))
        clip = row.clip
        if (clip.section_key or clip.section_title) and not carried:
            overrides[successor.id] = (clip.section_key, clip.section_title)
            for name in ("section_key", "section_title"):
                plan.fields.append((successor.id, name,
                                    getattr(successor.clip, name),
                                    getattr(clip, name)))
        if clip.section_key or clip.section_title:
            overrides[row.id] = ("", "")
            for name in ("section_key", "section_title"):
                plan.fields.append((row.id, name, getattr(clip, name), ""))

    # A moved clipping that carries heading words without printing them - left
    # out, or a second carrier of words already printed higher up - drops them
    # too. Kept, they would print in the new file the moment it was ticked back
    # in, and take the heading off the clippings that never moved.
    for rid in plan.moving:
        clip = model.row_for(rid).clip
        if rid in overrides or not (clip.section_key or clip.section_title):
            continue
        overrides[rid] = ("", "")
        for name in ("section_key", "section_title"):
            plan.fields.append((rid, name, getattr(clip, name), ""))

    after = openers_of(plan.rows_after, overrides)
    if after != expected:
        now = {r.id: n + 1 for n, r in enumerate(plan.rows_after)}
        for rid, words in after.items():
            if expected.get(rid) != words:
                plan.refused_words = words
                if words in expected.values():
                    plan.refused = f"{words} would move to No. {now[rid]}"
                else:
                    plan.refused = f"{words} would start printing over No. {now[rid]}"
                return plan
        gone = next(w for rid, w in expected.items() if after.get(rid) != w)
        plan.refused_words = gone
        plan.refused = f"{gone} would no longer print"
        return plan
    # Only for the ones that print at all: a clipping left out of the report
    # prints under nothing, wherever it goes.
    printing = [i for i in plan.moving if model.row_for(i).clip.include]
    if printing:
        plan.now_under = heading_over(plan.rows_after, after, printing[0])
        plan.was_under = sorted({heading_over(model.rows, before, i)
                                 for i in printing} - {""})
    return plan


def _fold_sets(model: "ClipModel", new_rows: list, movers: set, folded_now: set,
               fallback: dict, scope=None, groups_now=()) -> tuple:
    """(collapsed_groups, collapsed_row_ids) for the rows in their new order.

    Moved clippings take the state of the bracket they arrive in - an open file
    shows them at its end, a folded one simply counts them - and everything
    else keeps its own. The run sets are worked out again from the rows, never
    carried over: idents are numbered by order of appearance, so a move can
    renumber them, and an ident left behind would fold a different bracket.

    ``scope`` is the category the move was made in, and the brackets are that
    category's whichever one is open when the move is undone or redone. Worked
    out under another, the movers sat in no bracket at all, and an undo run
    while Negative was open came back with a Positive file drawn open. Every
    other category and division with a folded bracket in ``groups_now`` has its
    identities worked out again too, or a move in Positive threw away Negative's
    Collapse all.
    """
    from .model import Scope

    folded = set(folded_now) - movers
    placed: set = set()
    for run in model.file_runs(new_rows, scope=scope):
        staying = [r.id for r in run.rows if r.id not in movers]
        arriving = [r.id for r in run.rows if r.id in movers]
        placed.update(arriving)
        if not arriving:
            continue
        if staying:
            if any(i in folded_now for i in staying):
                folded |= set(arriving)
        else:
            folded |= {i for i in arriving if fallback.get(i)}
    # A mover no bracket of that category holds keeps its own fold rather than
    # losing it: there is nothing to take one from.
    folded |= {i for i in movers if i not in placed and fallback.get(i)}
    # Clippings not in the list just now - deleted, or sent to the board, and
    # waiting further back in the history - keep their fold for when they
    # return. Their ids are their own, so they cannot fold anything else.
    present = {r.id for r in new_rows}
    folded |= {i for i in folded_now if i not in present}
    scopes = {scope} | {Scope.of_ident(ident) for ident in groups_now} - {None}
    groups = set()
    for each in scopes:
        groups |= {run.ident for run in model.file_runs(new_rows, scope=each)
                   if any(r.id in folded for r in run.rows)}
    return groups, folded


class MoveIntoFile(_Base):
    """Clippings filed under another file's bracket, at its end, in one step.

    Undo puts back all of it: the order, the bracket each row was under, any
    heading handed on, which brackets were folded, and the ticks.
    """

    def __init__(self, model: "ClipModel", plan: MovePlan, text: str):
        super().__init__(model, text)
        self.before = list(model.rows)
        self.after = list(plan.rows_after)
        self.identity_before = _identity(self.before)
        self.moving = list(plan.moving)
        movers = set(self.moving)
        # The movers take the bracket's key and its name and badge - kept apart
        # from their own source, which does not change.
        self.identity_after = {
            rid: ((plan.run_key, kind, name, plan.run_title, plan.run_kind)
                  if rid in movers else (key, kind, name, title, badge))
            for rid, (key, kind, name, title, badge)
            in self.identity_before.items()}
        self.fields = list(plan.fields)
        self.ticks = set(plan.moving) | set(plan.already)
        self.selection_before = set(model.selected)
        # Each moved clipping's own fold state, for undo when the bracket it
        # goes back to has nothing else left in it.
        self.folded_before = {i: i in model.collapsed_row_ids for i in self.moving}
        # The category the move was made in, for its fold sets: see _fold_sets.
        self.scope = getattr(model, "scope", None)

    def _write(self, forwards: bool) -> None:
        steps = self.fields if forwards else list(reversed(self.fields))
        for clip_id, name, old, new in steps:
            row = self.model.row_for(clip_id)
            if row is not None:
                setattr(row.clip, name, new if forwards else old)

    def _apply(self, rows: list, identity: dict, fallback: dict,
               forwards: bool) -> None:
        model = self.model
        # Each row's own fold, as it was set - not the list as drawn. Drawn, a
        # bracket that two parts of one file had joined into counts every row
        # in it as folded, and undoing the join folded the part left open.
        folded_now = set(model.collapsed_row_ids)
        self._write(forwards)
        _restore(rows, identity)
        model.collapsed_groups, model.collapsed_row_ids = _fold_sets(
            model, rows, set(self.moving), folded_now, fallback,
            scope=self.scope, groups_now=set(model.collapsed_groups))
        if forwards:
            model.selected -= self.ticks
        else:
            model.selected = set(self.selection_before)
        model.replace_all(list(rows))
        model.selectionChanged.emit()

    def redo(self) -> None:
        self._apply(self.after, self.identity_after, {}, True)

    def undo(self) -> None:
        self._apply(self.before, self.identity_before, self.folded_before, False)


def move_relative(model: "ClipModel", clip_ids: Iterable[int], where: str,
                  rows: list | None = None) -> list:
    """Row order after nudging a selection to the top, up, down or the bottom.

    Worked out over ``rows`` when given, else the whole pool. Under a scope it
    is worked out over the category and woven back: in the pool the row above
    a Positive clipping is as likely to be a Negative one, and stepping over
    that moved nothing anybody could see.
    """
    if rows is None and _in_scope(model):
        return _weave(model, move_relative(model, clip_ids, where,
                                           rows=model.scoped_rows()))
    source = model.rows if rows is None else rows
    # Inside its own priority, and no further: the top of the list is the top
    # of the clipping's own level. A list nobody has set a priority on is one
    # level from end to end, so this is the whole list, as it always was.
    return in_levels(source, clip_ids,
                     lambda band: _nudged(band, clip_ids, where))


def _nudged(source: list, clip_ids: Iterable[int], where: str) -> list:
    """One run of rows with the selection stepped to the top, up, down or the end."""
    ids = set(clip_ids)
    moving = [r for r in source if r.id in ids]
    rest = [r for r in source if r.id not in ids]
    if not moving:
        return list(source)

    positions = [i for i, r in enumerate(source) if r.id in ids]
    first, last = positions[0], positions[-1]

    if where == "top":
        return moving + rest
    if where == "bottom":
        return rest + moving
    if where == "up":
        at = max(0, first - 1)
    else:
        at = min(len(rest), last + 2 - len(moving))
    return rest[:at] + moving + rest[at:]


def _runs(rows: list) -> list:
    """The contiguous stretches the list draws as one file, in order."""
    runs, start = [], 0
    for index in range(1, len(rows) + 1):
        if index == len(rows) or rows[index].group_key != rows[start].group_key:
            runs.append(rows[start:index])
            start = index
    return runs


def move_group_relative(model: "ClipModel", clip_ids: Iterable[int],
                        where: str, rows: list | None = None) -> list:
    """Row order after moving one whole file past the file next to it.

    The arrows on a file's header used to call move_relative, which nudges a
    selection by a single row. On a file of twenty clippings that moved the
    whole run one place - so one clipping of the file above ended up below it,
    the two files interleaved, and the header split in two. Twenty clicks did
    what one was expected to do, and the list looked broken on the way.

    A file moves past a file. Anything that is not exactly one whole run falls
    back to the old behaviour, which is right for a hand-picked selection.

    Under a scope the runs are the category's own brackets: one file's
    Positive clippings are not one unbroken run of the pool, so matched there
    the whole-file move could never be found.
    """
    if rows is None and _in_scope(model):
        return _weave(model, move_group_relative(model, clip_ids, where,
                                                 rows=model.scoped_rows()))
    source = list(model.rows if rows is None else rows)
    # Level by level, each part of the file past the file beside it inside
    # that level - the same rule the single-clipping arrows follow, so no
    # arrow can take a clipping out of the priority somebody gave it. A file
    # whose clippings are all at one priority - which is every file until
    # somebody presses a bubble - is moved exactly as it was before.
    return in_levels(source, clip_ids,
                     lambda band: _grouped(band, clip_ids, where))


def _grouped(source: list, clip_ids: Iterable[int], where: str) -> list:
    """One run of rows with a whole file's bracket stepped past its neighbour.

    Anything that is not exactly one whole bracket is nudged instead, which is
    right for a hand-picked selection.
    """
    ids = {row.id for row in source} & set(clip_ids)
    runs = _runs(source)
    here = next((i for i, run in enumerate(runs)
                 if {r.id for r in run} == ids), None)
    if here is None:
        return _nudged(source, ids, where)

    order = list(runs)
    run = order.pop(here)
    if where == "top":
        order.insert(0, run)
    elif where == "bottom":
        order.append(run)
    elif where == "up":
        order.insert(max(0, here - 1), run)
    else:
        order.insert(min(len(order), here + 1), run)
    return [row for group in order for row in group]


class AddClips(_Base):
    """Add imported or pasted clippings. ``at`` inserts instead of appending."""

    def __init__(self, model: "ClipModel", rows: list, text: str = "", at: int = -1):
        count = len(rows)
        super().__init__(
            model,
            text or (f"{count} clippings imported" if count != 1 else "Clipping added"),
        )
        self.new_rows = rows
        self.at = at
        self.before = None

    def redo(self) -> None:
        # The list exactly as it was, so undo puts back the order and not
        # merely the rows: the numbering below can move what was already there.
        self.before = list(self.model.rows)
        if self.at >= 0:
            self.model.insert(self.new_rows, self.at)
        else:
            self.model.append(self.new_rows)
        # A clipping arrives with no priority, so it belongs at the end of the
        # list - under everything anybody has given a priority to. Put in at a
        # place (Collect drops a photo after the last loose one), it takes a
        # number between its new neighbours instead, so the sort keeps it
        # there. On a list where nobody has set a priority this is the list
        # exactly as it was.
        arriving = [row.id for row in self.new_rows]
        for row_id, arrival in arrivals_for(self.model.rows, arriving).items():
            clip = self.model.by_id(row_id)
            if clip is not None:
                clip.order_seq = arrival
        order = banded(self.model.rows)
        if [row.id for row in order] != [row.id for row in self.model.rows]:
            self.model.replace_all(order)

    def undo(self) -> None:
        if self.before is not None:
            self.model.replace_all(list(self.before))
            return
        ids = {r.id for r in self.new_rows}
        self.model.replace_all([r for r in self.model.rows if r.id not in ids])


class RemoveClips(_Base):
    """Delete clippings from the list."""

    def __init__(self, model: "ClipModel", clip_ids: Iterable[int], text: str = ""):
        ids = set(clip_ids)
        super().__init__(
            model,
            text or (f"{len(ids)} clippings deleted" if len(ids) > 1
                     else "Clipping deleted"),
        )
        self.ids = ids
        self.before = list(model.rows)
        self.selection_before = set(model.selected)

    def redo(self) -> None:
        self.model.selected -= self.ids
        self.model.replace_all([r for r in self.model.rows if r.id not in self.ids])

    def undo(self) -> None:
        self.model.replace_all(list(self.before))
        self.model.selected = set(self.selection_before)
        self.model.selectionChanged.emit()


class MoveToInterface(_Base):
    """Hand clippings from one interface's pool to the other.

    The Row object itself moves, so its id, thumbnail and clip all survive and
    anything already holding that id keeps resolving to the same clipping.

    It is recorded on the source's history but changes the target as well, and
    the target keeps a history of its own made of whole-list snapshots. So two
    rules. The rows are moved one by one, never put back from a snapshot of
    either list: a snapshot of the target taken at the send brought back a
    card deleted on the board since. And every time rows cross, either way,
    ``forget`` is called to clear the target's history: its snapshots stop
    being true the moment they do, and undone later they put a sent clipping
    in both screens at once, as one shared object.
    """

    def __init__(self, source, target, clip_ids: list[int], text: str,
                 forget=None):
        super().__init__(source, text)
        self.source = source
        self.target = target
        self.ids = [i for i in clip_ids if source.row_for(i) is not None]
        self.moving = [source.row_for(i) for i in self.ids]
        # Where each one stood, to stand there again on undo.
        self.places = [source.position_of(i) for i in self.ids]
        self.selection = set(source.selected)
        self.forget = forget

    def _crossed(self) -> None:
        if self.forget is not None:
            self.forget()

    def redo(self) -> None:
        moving = {id(r) for r in self.moving}
        self.source.selected -= set(self.ids)
        self.source.replace_all(
            [r for r in self.source.rows if id(r) not in moving]
        )
        there = {id(r) for r in self.target.rows}
        self.target.replace_all(
            list(self.target.rows) + [r for r in self.moving if id(r) not in there]
        )
        self._crossed()

    def undo(self) -> None:
        moving = {id(r) for r in self.moving}
        self.target.replace_all(
            [r for r in self.target.rows if id(r) not in moving]
        )
        rows = [r for r in self.source.rows if id(r) not in moving]
        for place, row in sorted(zip(self.places, self.moving), key=lambda p: p[0]):
            rows.insert(min(max(place, 0), len(rows)), row)
        self.source.replace_all(rows)
        self.source.selected = set(self.selection)
        self.source.selectionChanged.emit()
        self._crossed()


class Merge(_Base):
    """Stitch several clippings into one, in place of the first of them."""

    def __init__(self, model: "ClipModel", clip_ids: Iterable[int]):
        ids = [r.id for r in model.rows if r.id in set(clip_ids)]
        super().__init__(model, f"{len(ids)} clippings merged into one")
        self.ids = ids
        self.before = list(model.rows)
        self.selection_before = set(model.selected)
        self.merged_row = None

    def redo(self) -> None:
        rows = [self.model.row_for(i) for i in self.ids]
        rows = [r for r in rows if r is not None]
        if len(rows) < 2:
            return
        if self.merged_row is None:
            clip = imageops.stitch([r.clip for r in rows])
            first = rows[0]
            self.merged_row = self.model.make_rows(
                [clip], first.source_kind, first.source_name, first.group_key
            )[0]
            # The bracket it was filed under, if a Move to put it there.
            self.merged_row.home_title = first.home_title
            self.merged_row.home_kind = first.home_kind
            # stitch() already carried the fields across; do not re-parse them
            self.merged_row.clip.label = clip.label

        at = self.model.position_of(rows[0].id)
        keep = [r for r in self.model.rows if r.id not in set(self.ids)]
        insert = min(max(0, at), len(keep))
        self.model.by_id_map[self.merged_row.id] = self.merged_row
        self.model.selected -= set(self.ids)
        self.model.replace_all(keep[:insert] + [self.merged_row] + keep[insert:])

    def undo(self) -> None:
        self.model.replace_all(list(self.before))
        self.model.selected = set(self.selection_before)
        self.model.selectionChanged.emit()


class Split(_Base):
    """Cut one clipping into two, in place."""

    def __init__(self, model: "ClipModel", clip_id: int, direction: str = "auto"):
        super().__init__(model, "Clipping split in two")
        self.clip_id = clip_id
        self.direction = direction
        self.before = list(model.rows)
        self.pieces: list = []

    def redo(self) -> None:
        row = self.model.row_for(self.clip_id)
        if row is None:
            return
        if not self.pieces:
            clips = imageops.split(row.clip, self.direction)
            self.pieces = self.model.make_rows(
                clips, row.source_kind, row.source_name, row.group_key
            )
            for piece, source in zip(self.pieces, clips):
                piece.clip.label = source.label
                piece.home_title, piece.home_kind = row.home_title, row.home_kind
        at = self.model.position_of(self.clip_id)
        keep = [r for r in self.model.rows if r.id != self.clip_id]
        for piece in self.pieces:
            self.model.by_id_map[piece.id] = piece
        self.model.selected.discard(self.clip_id)
        self.model.replace_all(keep[:at] + list(self.pieces) + keep[at:])

    def undo(self) -> None:
        self.model.replace_all(list(self.before))
