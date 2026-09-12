"""Undo commands. Every change to a clipping goes through one of these.

Nothing mutates the model directly. A misdrag that reorders 165 clippings with no
way back is the difference between a tool someone trusts and one they don't, so the
reorder, the batch delete and the merge are all commands like everything else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


class FillFromCopy(_Base):
    """A caption or a link copied in WhatsApp, put on one clipping in one step.

    Everything it may change is recorded before and after, so undo puts back
    exactly what was there. It never merges with anything: one copy, one step,
    so "undo that" means the copy and nothing else. The printed headline is not
    among the fields - a headline somebody typed keeps printing, with the page
    added after it.
    """

    FIELDS = ("caption_raw", "newspaper", "edition", "page", "name_source",
              "name_confidence", "no_title", "url", "show_url_box")

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


def move_to(model: "ClipModel", clip_ids: Iterable[int], target: int) -> list:
    """Row order with the given clippings lifted out and dropped at ``target``."""
    ids = set(clip_ids)
    moving = [r for r in model.rows if r.id in ids]
    rest = [r for r in model.rows if r.id not in ids]
    above = sum(1 for r in model.rows[:target] if r.id in ids)
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
    ordered = [r.id for r in model.rows if r.id in wanted]
    plan = MovePlan(
        run_ident=run.ident, run_key=run.key, run_title=run.title,
        run_kind=run.source_kind,
        moving=[i for i in ordered if i not in in_run],
        already=[i for i in ordered if i in in_run],
        rows_after=list(model.rows),
    )
    if not plan.moving:
        return plan
    plan.rows_after = move_to(model, plan.moving,
                              model.position_of(run.rows[-1].id) + 1)
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
               fallback: dict) -> tuple:
    """(collapsed_groups, collapsed_row_ids) for the rows in their new order.

    Moved clippings take the state of the bracket they arrive in - an open file
    shows them at its end, a folded one simply counts them - and everything
    else keeps its own. The run sets are worked out again from the rows, never
    carried over: idents are numbered by order of appearance, so a move can
    renumber them, and an ident left behind would fold a different bracket.
    """
    folded = set(folded_now) - movers
    for run in model.file_runs(new_rows):
        staying = [r.id for r in run.rows if r.id not in movers]
        arriving = [r.id for r in run.rows if r.id in movers]
        if not arriving:
            continue
        if staying:
            if any(i in folded_now for i in staying):
                folded |= set(arriving)
        else:
            folded |= {i for i in arriving if fallback.get(i)}
    # Clippings not in the list just now - deleted, or sent to the board, and
    # waiting further back in the history - keep their fold for when they
    # return. Their ids are their own, so they cannot fold anything else.
    present = {r.id for r in new_rows}
    folded |= {i for i in folded_now if i not in present}
    groups = {run.ident for run in model.file_runs(new_rows)
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
            model, rows, set(self.moving), folded_now, fallback)
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
