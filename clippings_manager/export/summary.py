"""The coverage summary: the day's clippings counted up, for the optional
last page of the report.

Who asks "how much did we get today, and from where?" is the office that
compiled it and the officer it goes to, and neither wants to count 257
pages by hand. One page at the end answers it: how many clippings, of what
kind, from which division, in which newspapers - and, when the sentiment
board has been used, how the day split between positive, neutral and
negative. Counted here once, so the PDF and the Word file say the same.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Optional

from ..core.models import Section

#: What each section prints as on the summary. Anything not named here is a
#: print clipping - the ordinary case, filed under Neutral by the import.
KIND_OF = {
    Section.ELECTRONIC: "Electronic",
    Section.DIGITAL: "Digital",
    Section.SOCIAL: "Social",
    Section.ADVERTISEMENT: "Advertisement",
}
KIND_ORDER = ("Print", "Electronic", "Digital", "Social", "Advertisement")
BOARD_ORDER = (Section.POSITIVE, Section.NEUTRAL, Section.NEGATIVE)

#: The newspaper list is long on a big day; past this many the rest are one line.
MOST_NEWSPAPERS = 20
BY_HAND = "Added by hand / WhatsApp"
NOT_NAMED = "Not named"


@dataclass
class Tally:
    """One table on the page: a title and (label, count) rows."""

    title: str
    rows: list

    @property
    def total(self) -> int:
        return sum(count for _label, count in self.rows)


@dataclass
class Summary:
    """The day counted up. `total` is every clipping in the report."""

    total: int
    tallies: list

    @classmethod
    def of(cls, clips: Iterable, board_clips: Iterable = (),
           config: Optional[dict] = None) -> "Summary":
        clips = [c for c in clips if c is not None]
        tallies: list = []

        kinds = Counter(KIND_OF.get(c.section, "Print") for c in clips)
        rows = [(kind, kinds[kind]) for kind in KIND_ORDER if kinds.get(kind)]
        if rows:
            tallies.append(Tally("By kind", rows))

        names = _division_names(config)
        by_division = Counter((c.division or "").strip() for c in clips)
        rows = [(names.get(code, code) if code else BY_HAND, count)
                for code, count in by_division.most_common()]
        rows.sort(key=lambda row: (-row[1], row[0]))
        if rows:
            tallies.append(Tally("By division", rows))

        by_paper = Counter(" ".join((c.newspaper or "").split()) or NOT_NAMED for c in clips)
        rows = sorted(by_paper.items(), key=lambda row: (-row[1], row[0]))
        if len(rows) > MOST_NEWSPAPERS:
            rest = rows[MOST_NEWSPAPERS:]
            rows = rows[:MOST_NEWSPAPERS] + [
                (f"{len(rest)} other newspapers", sum(count for _n, count in rest))]
        if rows:
            tallies.append(Tally("By newspaper", rows))

        board = Counter(c.section for c in board_clips if c is not None)
        rows = [(section.value, board[section]) for section in BOARD_ORDER
                if board.get(section)]
        if rows:
            tallies.append(Tally("Sentiment board", rows))

        return cls(total=len(clips), tallies=tallies)

    def lines(self) -> list:
        """The page as plain lines, for anything that only wants the words."""
        out = [f"{self.total} clipping{'s' if self.total != 1 else ''}"]
        for tally in self.tallies:
            out.append("")
            out.append(tally.title)
            out.extend(f"{label}: {count}" for label, count in tally.rows)
        return out


def _division_names(config: Optional[dict]) -> dict:
    """{code: full name} from the divisions the program knows."""
    try:
        from ..core import sentiment

        return {d.code: d.full_name for d in sentiment.divisions(config)}
    except Exception:  # noqa: BLE001 - the code is a fine name on its own
        return {}
