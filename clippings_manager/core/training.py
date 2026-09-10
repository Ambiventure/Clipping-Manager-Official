"""What the department has taught the machine about repeats, kept and portable.

The review dialog already records a judgement every time somebody presses
Confirm or Not-a-duplicate, in :mod:`verdicts`. This is a different thing and it
has its own file, for a reason worth stating before anything else.

**Why not the same file.** :func:`verdicts.suggestion_cutoff` works by backing
off from the NEAREST pair anybody ever called "not a duplicate". That is sound
for a store fed only by the review dialog, which never shows anything far apart.
The trainer deliberately asks about pairs across the whole range, so the first
"no" on a close-looking pair collapses the cutoff. Measured, from a healthy
store of five confirmed repeats:

    five confirmed repeats                    cutoff 60
      + one trainer "no" at distance 5        cutoff  2
      + a thirty-five pair trainer sweep      cutoff  1

- and the suggestion feature stops suggesting anything. A field on the row
cannot fix it either, because a build that shipped before the field existed
cannot honour it: today's :func:`verdicts._weighed` filters on ``how`` and
``d.fine`` only, so it would count a trainer row and read the cutoff as 4.

So there are two files. ``duplicate_verdicts.jsonl`` keeps exactly the meaning
it has always had and is not touched by anything here.

**What this is for.** Not a model. Three mornings of labelled pairs - 23,333 of
them, 306 genuine repeats - say plainly that there is nothing here to fit: the
two populations are interleaved on every measurement the application takes, not
merely overlapping. A true repeat sits 27 apart on the picture with headlines
scoring 100/100, while a pair of DIFFERENT cuttings sits 17 apart scoring 92/73
- the false pair closer on every count than the true one. Logistic regression on
two and a half thousand perfectly sampled labels still makes hundreds of wrong
drops, and the learning curve is flat from ten labels to two thousand five
hundred.

What the labels ARE good for is evidence. They say what THIS department calls a
repeat, in a form a later release can fit its constants against - ten real
mornings instead of three - and they say it in a file that can be sent to
somebody. That is what "the learning carries on to future builds" means here: a
person reads the corpus and sets the numbers, in a release anybody can audit,
rather than a copy of the application quietly moving a number on its own.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime
from typing import Optional

#: Bumped when the shape of a row changes in a way a reader must know about.
#: The one field whose absence cannot be repaired later.
SCHEMA = 1

#: What the export calls itself, so a file picked up in a year is identifiable.
KIND = "clippings-manager/duplicate-training"

# ------------------------------------------------------------ where it lives


def _folder():
    from ..ui.export_dialog import settings_dir

    return settings_dir()


def _store():
    return _folder() / "duplicate_training.jsonl"


def _origin_file():
    return _folder() / "training_origin.txt"


def origin() -> str:
    """An opaque name for this copy of the application.

    Minted once and kept. It exists so a merge can tell three people agreeing
    from one person clicking three times - never so anybody can find out who
    got a pair wrong. It is NOT the username, the machine name or anything
    derived from them, and it must not become so: a shared corpus that records
    whose judgement was wrong changes what people click, and a hesitation
    biases exactly the labels this file exists to collect honestly.
    """
    path = _origin_file()
    try:
        found = path.read_text(encoding="utf-8").strip()
        if found:
            return found[:16]
    except Exception:  # noqa: BLE001 - not minted yet
        pass
    made = uuid.uuid4().hex[:8]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(made, encoding="utf-8")
    except Exception:  # noqa: BLE001 - a store we cannot write is not a crash
        pass
    return made


def _write_atomic(path, text: str) -> None:
    """Temp file, then replace: a kill mid-write leaves one whole file or the
    other. This is a corpus somebody typed by hand, one judgement at a time."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


# ------------------------------------------------------------- naming a pair


def clip_name(clip) -> str:
    """What identifies a clipping's PICTURE, across imports and across builds.

    The three prints, not the uid. A uid is minted fresh every import, so a
    judgement keyed on one would be forgotten the next morning; the prints come
    off the picture itself. Tested against a real re-import: none of the 142
    uids survived, all 142 pictures were still recognised, and all 10,011 pairs
    kept their names.
    """
    return "|".join((getattr(clip, "picture_hash", "") or "",
                     getattr(clip, "picture_hash_lower", "") or "",
                     getattr(clip, "picture_hash_fine", "") or ""))


def pair_name(first, second) -> str:
    """One name for a pair, whichever way round it is handed over."""
    left, right = sorted((clip_name(first), clip_name(second)))
    return hashlib.sha256(f"{left}::{right}".encode("utf-8")).hexdigest()[:16]


def nameable(clip) -> bool:
    """A picture that would not print has no name and cannot be judged."""
    return bool((getattr(clip, "picture_hash", "") or "").strip())


# --------------------------------------------------------------- the strata
#
# Which of the rule's gates a pair falls at. This is recorded WITH the verdict
# and it is the single most valuable field on the row, because it says how the
# machine came to show this pair - the sampling frame. Without it the corpus is
# a bag of labels drawn at six wildly different rates with nothing to say which
# was which, and anything fitted to it believes the world looks like whatever
# the trainer happened to ask about most.
#
# It cannot be worked out afterwards from what verdicts.py stores, and that is
# measured rather than assumed: membership turns on duplicates.readable(),
# which needs headline_confidence and ocr_engine, and _measurements() records
# neither. A pair whose headline could not be READ is indistinguishable there
# from one whose headline read cleanly and disagreed - which is precisely the
# distinction carrying the teaching value.

FLAGGED = "flagged"          # the rule already calls it a repeat
WORD_EDGE = "word-edge"      # the headlines nearly agree, and missed the gate
PICTURE_EDGE = "picture-edge"  # the words agree, a picture gate refused it
BLIND = "blind"              # the pictures agree and a headline would not read
NEAR = "near"                # close on the finer print, nothing else to say
FIELD = "field"              # drawn from the rest, so the corpus has a floor

STRATA = (FLAGGED, WORD_EDGE, PICTURE_EDGE, BLIND, NEAR, FIELD)

#: How many of each to offer in one sitting, filled in this order, any
#: shortfall spilling into the next. Measured on real mornings: a batch drawn
#: this way holds about a dozen genuine repeats, where fifty drawn uniformly
#: hold 0.03 - fifty consecutive "no" answers, and a sitting nobody finishes.
QUOTAS = {FLAGGED: 8, WORD_EDGE: 8, PICTURE_EDGE: 4, BLIND: 12, NEAR: 8,
          FIELD: 10}


# ------------------------------------------------------------------ the rows


def _row(first, second, duplicate: bool, stratum: str, seen: dict) -> dict:
    from .. import version

    def side(clip):
        return {
            "whole": getattr(clip, "picture_hash", "") or "",
            "lower": getattr(clip, "picture_hash_lower", "") or "",
            "fine": getattr(clip, "picture_hash_fine", "") or "",
            "box": [getattr(clip, "content_w", 0), getattr(clip, "content_h", 0)],
            "div": getattr(clip, "division", "") or "",
            # The name only, never the path. The full path names a Windows
            # account and the department's folder tree, and this file is meant
            # to be sendable.
            "file": os.path.basename(getattr(clip, "source_file", "") or ""),
            # The headline itself, capped. verdicts.py keeps only the two
            # scores computed from it, so no later version can try a different
            # text measure on judgements already given - the very situation the
            # decision to keep the raw prints was taken to avoid. Capped so a
            # future reader that starts returning whole articles cannot quietly
            # turn this into an archive of the papers.
            "head": (getattr(clip, "ocr_text", "") or "")[:120],
            "read": int(getattr(clip, "headline_confidence", 0) or 0),
            "by": getattr(clip, "ocr_engine", "") or "",
        }

    return {
        "schema": SCHEMA,
        "at": datetime.now().isoformat(timespec="seconds"),
        "app": version.__version__,
        "digest": version.digest(),
        "origin": origin(),
        "pair": pair_name(first, second),
        "stratum": stratum,
        "verdict": "duplicate" if duplicate else "not-duplicate",
        "a": side(first),
        "b": side(second),
        "d": dict(seen or {}),
    }


def record(first, second, duplicate: bool, stratum: str = FIELD,
           seen: Optional[dict] = None) -> bool:
    """Write down one judgement made in the trainer. Never raises."""
    if not (nameable(first) and nameable(second)):
        return False
    try:
        row = _row(first, second, duplicate, stratum, seen or measure_pair(first, second))
        with _store().open("a", encoding="utf-8") as out:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception:  # noqa: BLE001 - never let bookkeeping break a decision
        return False


def measure_pair(first, second) -> dict:
    """Every distance between two clippings, for a later version to fit on."""
    from . import imageops

    out = {}
    try:
        from rapidfuzz import fuzz

        from . import ocr

        left = ocr.normalise(getattr(first, "ocr_text", "") or "")
        right = ocr.normalise(getattr(second, "ocr_text", "") or "")
        out["tsr"] = round(float(fuzz.token_set_ratio(left, right)), 1)
        out["ratio"] = round(float(fuzz.ratio(left, right)), 1)
    except Exception:  # noqa: BLE001 - the words are not always readable
        out["tsr"] = out["ratio"] = 0.0
    for key, left, right in (
            ("whole", "picture_hash", "picture_hash"),
            ("lower", "picture_hash_lower", "picture_hash_lower"),
            ("fine", "picture_hash_fine", "picture_hash_fine")):
        out[key] = imageops.pictures_apart(getattr(first, left, "") or "",
                                           getattr(second, right, "") or "")
    try:
        out["shape"] = round(imageops.shapes_apart(
            (getattr(first, "content_w", 0), getattr(first, "content_h", 0)),
            (getattr(second, "content_w", 0), getattr(second, "content_h", 0))), 4)
        out["ink"] = round(imageops.ink_apart(
            getattr(first, "ink_profile", "") or "",
            getattr(second, "ink_profile", "") or ""), 4)
    except Exception:  # noqa: BLE001
        pass
    out["same_file"] = (getattr(first, "source_file", "")
                        == getattr(second, "source_file", ""))
    out["same_div"] = (getattr(first, "division", "")
                       == getattr(second, "division", ""))
    return out


def all_rows() -> list:
    """Everything judged in the trainer, this copy's own and any imported."""
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
            found = json.loads(line)
        except ValueError:      # a half-written line from a crash
            continue
        if isinstance(found, dict) and found.get("pair"):
            rows.append(found)
    return rows


def judged() -> dict:
    """pair name -> what is known about it.

    Resolution happens HERE, at read time, and never at write time. The file
    holds observations; the moment a merge writes down "the answer for this
    pair is X" it has thrown away that two people disagreed, and a disagreement
    is the most valuable thing in the corpus - it is the strongest possible
    signal that somebody needs to look at that pair.
    """
    found: dict = {}
    for row in all_rows():
        name = row.get("pair")
        said = row.get("verdict") == "duplicate"
        seat = found.setdefault(name, {"yes": 0, "no": 0, "who": set(),
                                       "row": row})
        seat["yes" if said else "no"] += 1
        seat["who"].add(row.get("origin", ""))
    for seat in found.values():
        seat["disputed"] = bool(seat["yes"]) and bool(seat["no"])
        seat["verdict"] = None if seat["disputed"] else bool(seat["yes"])
    return found


def summary() -> dict:
    """What the corpus amounts to, in words, for the screen to say honestly."""
    seats = judged()
    duplicates = sum(1 for s in seats.values() if s["verdict"] is True)
    separate = sum(1 for s in seats.values() if s["verdict"] is False)
    disputed = sum(1 for s in seats.values() if s["disputed"])
    rows = all_rows()
    return {
        "rows": len(rows),
        "pairs": len(seats),
        "duplicates": duplicates,
        "separate": separate,
        "disputed": disputed,
        "origins": len({row.get("origin", "") for row in rows}),
    }


def forget_pair(name: str) -> int:
    """Take back the most recent judgement THIS copy made about one pair.

    For the Undo button, and only that. It drops the last row this copy wrote
    about the pair and leaves anybody else's alone: somebody correcting their
    own slip must not silently delete a colleague's answer, which would be the
    same overwrite the merge rule refuses.
    """
    rows = all_rows()
    mine = origin()
    for at in range(len(rows) - 1, -1, -1):
        if rows[at].get("pair") == name and rows[at].get("origin") == mine:
            del rows[at]
            try:
                _write_atomic(_store(), "".join(
                    json.dumps(row, ensure_ascii=False) + "\n"
                    for row in rows))
                return 1
            except Exception:  # noqa: BLE001
                return 0
    return 0


def forget() -> int:
    """Throw the whole corpus away. Only ever on an explicit ask."""
    count = len(all_rows())
    try:
        _store().unlink()
    except Exception:  # noqa: BLE001 - nothing to remove
        pass
    return count


# --------------------------------------------------------- choosing a pair
#
# The whole point of asking somebody anything is to ask about pairs whose
# answer is not already obvious, and to ask about ALL SIX KINDS - because a
# corpus made only of near-misses teaches only about near-misses.
#
# A morning is ten thousand pairs and perhaps seven of them are repeats: one in
# fourteen hundred. Fifty pairs drawn at random would be fifty "no" answers,
# and a sitting nobody finishes. Fifty drawn by which gate the pair falls at
# holds about a dozen real repeats.


def _readable(clip) -> bool:
    from . import duplicates

    return duplicates.readable(clip)


def stratum_of(first, second, seen: dict, flagged: bool) -> Optional[str]:
    """Which kind of question this pair is, or None if it is not worth asking."""
    from . import duplicates, imageops

    if flagged:
        return FLAGGED
    tsr, ratio = seen.get("tsr", 0.0), seen.get("ratio", 0.0)
    whole, lower, fine = seen.get("whole", -1), seen.get("lower", -1), seen.get("fine", -1)
    words_agree = tsr >= duplicates.SIMILARITY and ratio >= duplicates.OVERALL
    pictures_agree = (0 <= whole <= imageops.PICTURE_APART
                      and 0 <= lower <= imageops.LOWER_APART)
    could_read = _readable(first) and _readable(second)

    if could_read and not words_agree and (
            duplicates.SIMILARITY > tsr >= 70.0
            or (tsr >= duplicates.SIMILARITY and 55.0 <= ratio < duplicates.OVERALL)):
        return WORD_EDGE
    if words_agree and not pictures_agree:
        return PICTURE_EDGE
    if pictures_agree and not could_read:
        # The rule's own blind spot, and the biggest one it has: the pictures
        # all but coincide and it cannot act because a headline would not read.
        # On the morning where independent truth exists, 26 of the rule's 27
        # misses are here.
        return BLIND
    if 0 <= fine <= 105:
        return NEAR
    return FIELD


def candidates(clips, pairs=None, wanted: int = 50) -> list:
    """A sitting's worth of pairs to judge: [(first, second, stratum, seen)].

    Filled by quota in the order STRATA declares, any shortfall spilling into
    what comes after, and never asking twice about a pair already judged - by
    the trainer, or by the review dialog, or in a corpus somebody imported.
    """
    from . import duplicates

    clips = [c for c in clips if nameable(c)]
    flagged = set()
    for pair in (pairs or []):
        flagged.add(pair_name(pair.primary, pair.copy))
    settled = set(judged())

    piles = {name: [] for name in STRATA}
    for index, first in enumerate(clips):
        for second in clips[index + 1:]:
            name = pair_name(first, second)
            if name in settled:
                continue                 # already answered; do not ask again
            if name == pair_name(first, first):
                continue                 # the same picture twice
            seen = measure_pair(first, second)
            kind = stratum_of(first, second, seen, name in flagged)
            if kind is None:
                continue
            piles[kind].append((seen.get("fine", 999), first, second, kind, seen))

    # Closest first inside every pile. The finer print is a poor decider - it
    # cannot separate the populations - but it is a good ORDERER, and the
    # productive depth is shallow: on a real morning the repeats in the blind
    # spot sit in the first dozen.
    for pile in piles.values():
        pile.sort(key=lambda row: row[0])

    out, spare = [], 0
    for name in STRATA:
        room = QUOTAS.get(name, 0) + spare
        taking = piles[name][:room]
        spare = room - len(taking)
        out.extend(taking)
        if len(out) >= wanted:
            break
    return [(first, second, kind, seen)
            for _near, first, second, kind, seen in out[:wanted]]


# ------------------------------------------------------------ sending it on


def export_to(path) -> dict:
    """Write the corpus as one complete document, safe to send.

    A document rather than a log: an export is complete or it is not, whereas
    the live store is appended to. The digest of the rows is carried so a
    truncated copy is refused rather than half-imported.
    """
    from pathlib import Path

    from .. import version

    rows = all_rows()
    body = json.dumps(rows, ensure_ascii=False, sort_keys=True)
    payload = {
        "kind": KIND,
        "schema": SCHEMA,
        "app": version.__version__,
        "digest": version.digest(),
        "origin": origin(),
        "exported": datetime.now().isoformat(timespec="seconds"),
        "rows": len(rows),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "training": rows,
    }
    _write_atomic(Path(path), json.dumps(payload, indent=1, ensure_ascii=False))
    return {"rows": len(rows), "pairs": len(judged())}


def inspect(path) -> dict:
    """What a file holds, and what importing it would do. Changes nothing."""
    from pathlib import Path

    try:
        found = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "why": f"That file could not be read ({error})."}
    if not isinstance(found, dict) or found.get("kind") != KIND:
        return {"ok": False,
                "why": "That is not a Clippings Manager training file."}
    rows = found.get("training")
    if not isinstance(rows, list):
        return {"ok": False, "why": "That file carries no judgements."}
    body = json.dumps(rows, ensure_ascii=False, sort_keys=True)
    if found.get("sha256") and found["sha256"] != hashlib.sha256(
            body.encode("utf-8")).hexdigest():
        return {"ok": False,
                "why": "That file is damaged or was only partly copied."}

    mine = all_rows()
    seen = {(row.get("pair"), row.get("origin"), row.get("at")) for row in mine}
    settled = judged()
    fresh, already, clash = [], 0, 0
    for row in rows:
        if not isinstance(row, dict) or not row.get("pair"):
            continue
        if (row.get("pair"), row.get("origin"), row.get("at")) in seen:
            already += 1
            continue
        fresh.append(row)
        seat = settled.get(row.get("pair"))
        if seat is not None and seat["verdict"] is not None:
            if seat["verdict"] != (row.get("verdict") == "duplicate"):
                clash += 1
    return {"ok": True, "rows": len(rows), "new": len(fresh),
            "already": already, "disagree": clash,
            "origin": found.get("origin", ""), "app": found.get("app", ""),
            "schema": found.get("schema", 0), "_fresh": fresh}


def import_from(path) -> dict:
    """Merge another copy's judgements in. Set union, nothing overwritten.

    A row never replaces a row. Where two judgements about one pair disagree
    the pair becomes disputed, counts for nothing, and goes to the front of the
    trainer's queue - because two people disagreeing is not a tie to be settled
    by whichever file was imported second. Last-write-wins would let one
    careless click quietly delete a correct call, which is exactly the kind of
    mistake nobody ever sees.
    """
    looked = inspect(path)
    if not looked.get("ok"):
        return looked
    fresh = looked.pop("_fresh", [])
    if fresh:
        try:
            with _store().open("a", encoding="utf-8") as out:
                for row in fresh:
                    out.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "why": f"Could not write them in ({error})."}
    looked["added"] = len(fresh)
    return looked
