"""What the user has already decided about repeats, and what it teaches.

Every time somebody presses "Not a duplicate" or confirms one in the review
dialog they are labelling an example, and those labels are the only ones that
describe THIS department's papers. This keeps them, and uses them.

**What it is not.** There is no model here in the machine-learning sense, no
agent, no network, and nothing that could not be worked out with a pencil. That
is deliberate: the application runs with the cable unplugged and ships no
network libraries at all. It is also, measured, the right answer - see below.

**Why not a classifier.** Logistic regression and a nearest-neighbour vote were
both tried on the sample mornings and both were catastrophic: at five recorded
verdicts they made nine and a half thousand wrong drops on a corpus of sixteen
thousand pairs. The reason is not the model, it is the data. Verdicts only ever
come from pairs the application ALREADY showed somebody - the ones it had
already decided were close. Nothing is ever labelled about the thousands of
pairs it silently rejected, so a model trained on that sample thinks the whole
world looks like the review dialog, and starts flagging everything.

**So it learns one number.** How close two pictures have to be, on the finer
256-bit print, before the pair is worth a person's attention. One parameter, fit
to one biased-but-relevant sample, is a thing that sample can honestly support.

**And it may only ever suggest.** This is the rule everything else follows from.
A repeat that slips through is printed twice and somebody notices. A clipping
wrongly called a repeat is dropped from the report and nobody notices at all -
and the shipped rule makes that mistake zero times on every labelled pair there
is. So what is learned here NEVER excludes a clipping. It puts extra candidates
in front of somebody in the review dialog, where a wrong call costs a glance.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

# Below this many judgements the shipped setting stands. Five is what the sample
# mornings needed before a fitted threshold beat the default, and it is also
# about the point at which one careless click stops dominating the answer.
ENOUGH = 5

# A bulk "delete all of them" is one decision, not one per pair, so it is
# recorded and then weighed at nothing. Nothing else in the store is that cheap.
BULK = "sweep"
ONE_BY_ONE = "one-by-one"

# The furthest apart two pictures may be, on the 256-bit print, before the
# suggestion is not worth making however many verdicts point that way. The
# learned number is clamped to this; without a ceiling one unlucky run of
# verdicts could widen the net indefinitely.
#
# Measured on a real morning, which is stricter than it first looked. Two
# DIFFERENT stories out of one newspaper come as close as 71 apart on this print
# - they share a masthead, a column width and a typeface - so anything at or
# past 71 is in the zone where a suggestion would be wrong. 68 is the last value
# clear of it.
CEILING = 68

# Where it starts before anything has been learned.
#
# Deliberately well inside the ceiling, and worth being honest about why it is
# so low. This print does NOT separate repeats from non-repeats on a real
# morning: a genuine repeat of one cutting - the same story, photographed rather
# than scanned, cropped differently - was measured 116 apart, while two
# different stories from one paper were 71 apart. The populations overlap
# completely, so no cut-off on this print alone can decide anything.
#
# What it CAN do is recognise the very close ones with confidence. So it is used
# for nothing but suggestions, at a distance where being wrong is unlikely and
# costs a glance in any case. The real deciding is still done by the headline,
# which is what actually tells two stories apart.
START = 60


def _store():
    from ..ui.export_dialog import settings_dir

    return settings_dir() / "duplicate_verdicts.jsonl"


def _measurements(first, second) -> dict:
    """Everything numeric about a pair, for a later version to learn from."""
    from . import imageops, ocr

    try:
        from rapidfuzz import fuzz

        left = ocr.normalise(getattr(first, "ocr_text", "") or "")
        right = ocr.normalise(getattr(second, "ocr_text", "") or "")
        words = {"tsr": round(fuzz.token_set_ratio(left, right), 1),
                 "ratio": round(fuzz.ratio(left, right), 1)}
    except Exception:  # noqa: BLE001 - the words are not always readable
        words = {"tsr": 0.0, "ratio": 0.0}

    def prints(clip):
        return {
            "whole": getattr(clip, "picture_hash", ""),
            "lower": getattr(clip, "picture_hash_lower", ""),
            "fine": getattr(clip, "picture_hash_fine", ""),
            "box": [getattr(clip, "content_w", 0), getattr(clip, "content_h", 0)],
            "div": getattr(clip, "division", ""),
            "file": getattr(clip, "source_file", ""),
        }

    return {
        # The prints themselves, not only the distances between them. They are
        # a hundred characters, and keeping them means a later version can work
        # out something nobody has thought of yet from verdicts already given,
        # instead of asking for them all over again.
        "a": prints(first),
        "b": prints(second),
        "d": {
            "whole": imageops.pictures_apart(
                getattr(first, "picture_hash", ""),
                getattr(second, "picture_hash", "")),
            "lower": imageops.pictures_apart(
                getattr(first, "picture_hash_lower", ""),
                getattr(second, "picture_hash_lower", "")),
            "fine": imageops.pictures_apart(
                getattr(first, "picture_hash_fine", ""),
                getattr(second, "picture_hash_fine", "")),
            "shape": round(imageops.shapes_apart(
                (getattr(first, "content_w", 0), getattr(first, "content_h", 0)),
                (getattr(second, "content_w", 0),
                 getattr(second, "content_h", 0))), 4),
            "ink": round(imageops.ink_apart(
                getattr(first, "ink_profile", ""),
                getattr(second, "ink_profile", "")), 4),
            "same_file": (getattr(first, "source_file", "")
                          == getattr(second, "source_file", "")),
            "same_div": (getattr(first, "division", "")
                         == getattr(second, "division", "")),
            **words,
        },
    }


def record(first, second, duplicate: bool, how: str = ONE_BY_ONE) -> None:
    """Write down one judgement. Never raises: this is a convenience."""
    try:
        row = {"at": datetime.now().isoformat(timespec="seconds"),
               "verdict": "duplicate" if duplicate else "not-duplicate",
               "how": how}
        row.update(_measurements(first, second))
        with _store().open("a", encoding="utf-8") as out:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - never let bookkeeping break a decision
        pass


def all_verdicts() -> list:
    try:
        text = _store().read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001 - nothing recorded yet
        return []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:      # a half-written line from a crash
            continue
    return rows


def forget() -> int:
    """Throw the lot away and go back to the shipped setting."""
    count = len(all_verdicts())
    try:
        _store().unlink()
    except Exception:  # noqa: BLE001 - nothing to remove
        pass
    return count


def _weighed(rows: list) -> list:
    """Only the judgements somebody actually made one at a time."""
    return [row for row in rows
            if row.get("how") != BULK
            and isinstance(row.get("d"), dict)
            and isinstance(row["d"].get("fine"), int)
            and row["d"]["fine"] >= 0]


def suggestion_cutoff() -> int:
    """How close two pictures must be, on the fine print, to be worth showing.

    The widest cut-off that makes no mistake on what has been judged so far,
    with a margin, and never past the ceiling. "Makes no mistake" means it does
    not reach any pair that was called NOT a duplicate: those are the ones
    somebody has already looked at and rejected, and reaching them again would
    be asking the same question twice.
    """
    rows = _weighed(all_verdicts())
    if len(rows) < ENOUGH:
        return START

    same = sorted(row["d"]["fine"] for row in rows
                  if row["verdict"] == "duplicate")
    different = sorted(row["d"]["fine"] for row in rows
                       if row["verdict"] == "not-duplicate")

    # Start from the shipped setting and WIDEN it to reach the furthest apart a
    # confirmed repeat has ever been, so everything already confirmed would be
    # caught again. Starting from the confirmations instead was wrong in a way
    # that only showed on real numbers: a morning where every confirmed repeat
    # happened to be nearly identical put the cut-off at nought, and learning
    # from five correct answers made the feature suggest nothing at all.
    wanted = max([START] + same)
    # Then stop short of the nearest pair that was rejected. Two bits of margin,
    # because the next rejected pair will not be at exactly the same distance as
    # the last one.
    if different:
        wanted = min(wanted, different[0] - 3)
    return max(0, min(CEILING, int(wanted)))


def learned_from(rows: Optional[list] = None) -> dict:
    """What the store amounts to, in words, for the settings screen."""
    rows = all_verdicts() if rows is None else rows
    counted = _weighed(rows)
    confirmed = sum(1 for row in counted if row["verdict"] == "duplicate")
    rejected = len(counted) - confirmed
    return {
        "verdicts": len(rows),
        "counted": len(counted),
        "confirmed": confirmed,
        "rejected": rejected,
        "cutoff": suggestion_cutoff(),
        "learning": len(counted) >= ENOUGH,
    }
