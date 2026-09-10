"""Undo commands. Every change to a clipping goes through one of these.

Nothing mutates the model directly. A misdrag that reorders 165 clippings with no
way back is the difference between a tool someone trusts and one they don't, so the
reorder, the batch delete and the merge are all commands like everything else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from PySide6.QtGui import QUndoCommand

from ..core import imageops

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
    return {r.id: (r.group_key, r.source_kind, r.source_name) for r in rows}


def _restore(rows, identity: dict) -> None:
    for row in rows:
        remembered = identity.get(row.id)
        if remembered:
            row.group_key, row.source_kind, row.source_name = remembered


def reparent(rows, clip_ids, group_key: str, source_kind: str, source_name: str) -> None:
    """Move rows into another file's bracket, in place."""
    wanted = set(clip_ids)
    for row in rows:
        if row.id in wanted:
            row.group_key = group_key
            row.source_kind = source_kind
            row.source_name = source_name


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


def move_to(model: "ClipModel", clip_ids: Iterable[int], target: int) -> list:
    """Row order with the given clippings lifted out and dropped at ``target``."""
    ids = set(clip_ids)
    moving = [r for r in model.rows if r.id in ids]
    rest = [r for r in model.rows if r.id not in ids]
    above = sum(1 for r in model.rows[:target] if r.id in ids)
    at = max(0, min(target - above, len(rest)))
    return rest[:at] + moving + rest[at:]


def move_relative(model: "ClipModel", clip_ids: Iterable[int], where: str) -> list:
    """Row order after nudging a selection to the top, up, down or the bottom."""
    ids = set(clip_ids)
    moving = [r for r in model.rows if r.id in ids]
    rest = [r for r in model.rows if r.id not in ids]
    if not moving:
        return list(model.rows)

    positions = [i for i, r in enumerate(model.rows) if r.id in ids]
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
                        where: str) -> list:
    """Row order after moving one whole file past the file next to it.

    The arrows on a file's header used to call move_relative, which nudges a
    selection by a single row. On a file of twenty clippings that moved the
    whole run one place - so one clipping of the file above ended up below it,
    the two files interleaved, and the header split in two. Twenty clicks did
    what one was expected to do, and the list looked broken on the way.

    A file moves past a file. Anything that is not exactly one whole run falls
    back to the old behaviour, which is right for a hand-picked selection.
    """
    ids = set(clip_ids)
    rows = list(model.rows)
    runs = _runs(rows)
    here = next((i for i, run in enumerate(runs)
                 if {r.id for r in run} == ids), None)
    if here is None:
        return move_relative(model, clip_ids, where)

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

    def redo(self) -> None:
        if self.at >= 0:
            self.model.insert(self.new_rows, self.at)
        else:
            self.model.append(self.new_rows)

    def undo(self) -> None:
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
    """

    def __init__(self, source, target, clip_ids: list[int], text: str):
        super().__init__(source, text)
        self.source = source
        self.target = target
        self.ids = [i for i in clip_ids if source.row_for(i) is not None]
        self.moving = [source.row_for(i) for i in self.ids]
        self.before_source = list(source.rows)
        self.before_target = list(target.rows)
        self.selection = set(source.selected)

    def redo(self) -> None:
        self.source.selected -= set(self.ids)
        self.source.replace_all(
            [r for r in self.source.rows if r.id not in set(self.ids)]
        )
        self.target.replace_all(list(self.target.rows) + self.moving)

    def undo(self) -> None:
        self.target.replace_all(list(self.before_target))
        self.source.replace_all(list(self.before_source))
        self.source.selected = set(self.selection)
        self.source.selectionChanged.emit()


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
        at = self.model.position_of(self.clip_id)
        keep = [r for r in self.model.rows if r.id != self.clip_id]
        for piece in self.pieces:
            self.model.by_id_map[piece.id] = piece
        self.model.selected.discard(self.clip_id)
        self.model.replace_all(keep[:at] + list(self.pieces) + keep[at:])

    def undo(self) -> None:
        self.model.replace_all(list(self.before))
