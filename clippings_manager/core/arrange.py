"""Which clippings to show, and what order to show them in.

Two separate questions, deliberately kept apart. Filtering decides what is on
screen; arranging decides the order it appears in. Somebody can do either, both,
or neither, and turning one off never disturbs the other - which is why they are
two controls and not one drop-down with eleven entries in it.

**A lens, not an edit.** Nothing in this module changes a clipping or the list
it sits in. It answers "which of these, in what order" and hands back plain
indexes; the caller draws them. That is not fastidiousness, it is the only
design that can promise the thing actually being asked for - a Clear button that
gives back exactly the view that was there before. The order the clippings are
really in is the export order, the file brackets, the section headings and which
copy of a repeated cutting survives; a filter that rewrote it would be quietly
deciding all four.

**How several filters stack.** Within one axis the choices are alternatives -
Hindi OR English. Across axes they are conditions - Regional AND (Hindi OR
English). So each axis can only ever narrow what the one before it left, which
is what makes "regional, then Hindi or English" behave the way it reads, and
means the order they are applied in cannot change the answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import categories

# The pseudo-axis that is not a property of the publication but the publication
# itself. Kept here rather than in categories.json because its values are
# whatever papers this particular morning happens to contain.
BY_NAME = "paper"

#: The arrangements, in the order they are offered. The empty key is first
#: because it is the one that changes nothing.
ARRANGEMENTS = [
    ("", "As I arranged them"),
    ("importance", "Biggest publications first"),
    ("paper", "Newspaper"),
    ("language", "Language"),
    ("reach", "Reach"),
    ("stature", "Size"),
    ("medium", "Medium"),
]

#: The arrangements that then ask "which first?". "Biggest first" is a fixed
#: idea - by size, then by reach - and asking would only muddle it.
ASKS_WHICH_FIRST = {"paper", "language", "reach", "stature", "medium"}

ARRANGEMENT_KEYS = {key for key, _label in ARRANGEMENTS}


@dataclass
class Lens:
    """What is being shown, and in what order. A view state, never a change."""

    #: axis -> the values picked on it. An axis with nothing picked is not
    #: filtering; an axis is never stored with an empty list.
    picked: dict = field(default_factory=dict)
    #: One of ARRANGEMENT_KEYS. Empty means leave the order exactly alone.
    order: str = ""
    #: For an arrangement that asks which first: the values put at the top, in
    #: the order they were chosen. Anything not here follows in the axis's own
    #: order, and clippings with no paper on them come last whatever is chosen.
    first: list = field(default_factory=list)

    @property
    def filtering(self) -> bool:
        return any(self.picked.values())

    @property
    def arranging(self) -> bool:
        return bool(self.order)

    @property
    def busy(self) -> bool:
        """Is this lens doing anything at all? What the Clear button turns on."""
        return self.filtering or self.arranging

    def pick(self, axis: str, values) -> None:
        values = [str(v) for v in (values or []) if str(v)]
        if values:
            self.picked[axis] = values
        else:
            self.picked.pop(axis, None)

    def cleared(self) -> "Lens":
        return Lens()

    def copy(self) -> "Lens":
        return Lens({k: list(v) for k, v in self.picked.items()}, self.order,
                    list(self.first))

    def put_first(self, value: str) -> None:
        """Rank this value next, or take it out of the ranking if it is in."""
        value = str(value)
        if value in self.first:
            self.first.remove(value)
        else:
            self.first.append(value)


def _value(clip, axis: str, book) -> str:
    """One clipping's value on one axis."""
    if axis == BY_NAME:
        return (getattr(clip, "newspaper", "") or "").strip() or categories.UNKNOWN
    return book.value(getattr(clip, "newspaper", "") or "", axis)


def keeps(clip, lens: Lens, book) -> bool:
    """Does this clipping survive the filter?"""
    for axis, wanted in lens.picked.items():
        if not wanted:
            continue
        if _value(clip, axis, book) not in wanted:
            return False
    return True


def shown(clips, lens: Lens, book) -> list:
    """The positions of the clippings this lens shows, in the order it shows
    them. Positions into the list handed in, never the clippings themselves -
    the caller owns those and this module does not touch them."""
    keep = [index for index, clip in enumerate(clips) if keeps(clip, lens, book)]
    if not lens.order:
        return keep
    ranks = _ranker(lens.order, book, lens.first)
    # Sorted on the rank alone, with the position as the tiebreak, so the sort
    # is stable: two clippings from the same paper stay in the order somebody
    # put them in. An unstable sort would scramble a morning's hand arrangement
    # every time the list was looked at a different way.
    return sorted(keep, key=lambda index: (ranks(clips[index]), index))


def _ranker(order: str, book, first=None):
    """A function giving each clipping its sort key under this arrangement.

    ``first`` is what the person put at the top, in the order they chose it.
    A value in it ranks by its place there; anything else ranks after all of
    them, in the axis's own order - so choosing "English" alone means English,
    then everything else exactly as it would have been.
    """
    chosen = {str(value): index for index, value in enumerate(first or [])}
    after = len(chosen)

    if order == "paper":
        def rank(clip):
            name = _value(clip, BY_NAME, book)
            # Clippings with no paper on them yet go last whatever the
            # arrangement: they are work still to do, not a category.
            if name == categories.UNKNOWN:
                return (2, 0, name.casefold())
            if name in chosen:
                return (0, chosen[name], name.casefold())
            return (1, 0, name.casefold())
        return rank

    if order == "importance":
        big = _steps(book, "stature")
        far = _steps(book, "reach")

        def rank(clip):
            name = _value(clip, BY_NAME, book)
            unknown = 1 if book.paper(name) is None else 0
            return (unknown,
                    big.get(_value(clip, "stature", book), 99),
                    far.get(_value(clip, "reach", book), 99),
                    name.casefold())
        return rank

    steps = _steps(book, order)

    def rank(clip):
        value = _value(clip, order, book)
        place = chosen.get(value)
        if place is None:
            place = after + steps.get(value, 99)
        return (place, value.casefold(), _value(clip, BY_NAME, book).casefold())
    return rank


def _steps(book, axis: str) -> dict:
    """value -> where it sits on this axis, in the order the axis declares.

    The order in categories.json is meaningful: National before Regional before
    Local, Major before Mid before Small. Alphabetical would put Local first and
    Major after Mid, and "biggest first" would read as nonsense.
    """
    found = book.axes.get(axis)
    values = found.values if found is not None else []
    steps = {value: index for index, value in enumerate(values)}
    steps[categories.UNKNOWN] = len(steps) + 1
    return steps


def heading_for(clip, lens: Lens, book) -> str:
    """The words over the run this clipping belongs to, while arranged.

    While an arrangement is on, the file brackets are wrong - a file's clippings
    are no longer together - so the list is headed by what it is actually sorted
    by instead.
    """
    if not lens.order:
        return ""
    if lens.order == "paper":
        return _value(clip, BY_NAME, book)
    if lens.order == "importance":
        size = _value(clip, "stature", book)
        reach = _value(clip, "reach", book)
        if size == categories.UNKNOWN:
            return categories.UNKNOWN
        return f"{size} · {reach}"
    return _value(clip, lens.order, book)


def tally(clips, axis: str, book) -> dict:
    """How many clippings sit under each value of one axis.

    Shown beside every choice, so somebody can see there are four English
    clippings before picking English and finding four - and so an axis with
    nothing under it can say so instead of looking broken.
    """
    counts: dict = {}
    for clip in clips:
        value = _value(clip, axis, book)
        counts[value] = counts.get(value, 0) + 1
    return counts


def choices(clips, axis: str, book) -> list:
    """Every value worth offering on one axis, in the axis's own order, each
    with its count. Values nothing falls under are left out - a filter that can
    only ever return nothing is not worth a line on screen."""
    counts = tally(clips, axis, book)
    if axis == BY_NAME:
        names = sorted((n for n in counts if n != categories.UNKNOWN),
                       key=str.casefold)
    else:
        found = book.axes.get(axis)
        names = [v for v in (found.values if found is not None else [])
                 if v in counts]
    out = [(name, counts[name]) for name in names]
    if counts.get(categories.UNKNOWN):
        out.append((categories.UNKNOWN, counts[categories.UNKNOWN]))
    return out


def order_words(lens: Lens, book) -> str:
    """The arrangement in words: "by language — English first, then Punjabi"."""
    if not lens.order:
        return ""
    if lens.order == "importance":
        return "biggest publications first"
    found = book.axes.get(lens.order)
    label = (found.label if found is not None else "newspaper").lower()
    if not lens.first:
        return f"by {label}, in the usual order"
    if len(lens.first) == 1:
        return f"by {label} — {lens.first[0]} first"
    return (f"by {label} — {lens.first[0]} first, then "
            + ", then ".join(lens.first[1:]))


def describe(lens: Lens, book) -> str:
    """The lens in words, for the strip to say what it is doing."""
    if not lens.busy:
        return ""
    parts = []
    for axis, wanted in lens.picked.items():
        if not wanted:
            continue
        found = book.axes.get(axis)
        label = found.label if found is not None else "Newspaper"
        parts.append(f"{label}: " + " or ".join(wanted))
    said = ", then ".join(parts)
    if lens.order:
        how = order_words(lens, book)
        said = f"{said} — {how}" if said else how[0].upper() + how[1:]
    return said
