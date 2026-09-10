"""Finding the same cutting twice.

Six divisions send in their own file every morning and the same story is often
in more than one of them - so the same cutting arrives twice, from two different
documents, and without this it is printed twice in the report.

The two copies are rarely the same picture. One division scans the cutting
plainly; another adds a black masthead band across the top with the paper's name
and the date, and crops it differently. Comparing the pictures does not work
well enough for that, so what is compared is the words: the headline, read off
each cutting by :mod:`ocr`.

The threshold was measured, not guessed. On one day of real files - 194
clippings from 15 documents, 14,585 cross-file pairs - scoring headline against
headline puts genuine copies of the same cutting at 90 and above (most at 100,
the rest held down only by OCR mistaking a letter here and there), and the
highest-scoring pair that was NOT the same cutting sat at 88: two different
papers running the same story about railway quarters, under headlines that share
their first six words. Ninety is the gap between those two populations.

Nothing is ever deleted here. A clipping is marked as suspected, and the person
compiling the report decides - which matters, because the pair at 88 and the
pair at 90 look much the same from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from . import imageops, ocr

# Imported here rather than inside _score. It was inside, and _score is called
# once per pair - five thousand times per check - so the import machinery alone
# cost about ten milliseconds of every comparison, on the drawing thread.
try:
    from rapidfuzz import fuzz as _fuzz
except Exception:  # noqa: BLE001 - without it, only exact matches
    _fuzz = None

# How alike two headlines have to be, on two counts that catch different
# mistakes. Both are named so either can be moved.
#
# SIMILARITY is forgiving about one reading catching a word the other missed:
# one scan often picks up a line of the sub-heading that the other drops, and
# that should not stop two copies of the same cutting matching.
#
# OVERALL is the guard against exactly that forgiveness. Two DIFFERENT stories
# about the same event share their nouns - "डीआरएम ने आलमनगर, अमौसी एवं लखनऊ
# स्टेशन का लिया जायजा" against "मंडल रेल प्रबंधक ने आलमनगर, अमौसी एवं लखनऊ
# स्टेशन..." - the same official under two names in two papers. On the
# forgiving count those score 93; on this one, 64.
#
# Measured over one morning of real files: 68 pairs known to be the same
# cutting, 832 pairs of different cuttings inside one file, 9,160 pairs across
# divisions. The pair of numbers below finds 84% of the known repeats and gets
# none of the others wrong. The forgiving count on its own finds 87% and
# wrongly flags two - and a wrong flag is a story dropped from the report that
# nobody ever looked at, so the three points are worth paying.
SIMILARITY = 90.0
OVERALL = 70.0

# And the pictures have to agree as well as the words. This is not belt and
# braces; it is the only thing that works on the case the words cannot reach.
#
# Two DIFFERENT cuttings of one story - the same paper, the same morning, the
# headline word for word identical - score 100 on both counts above. Nothing
# about the text distinguishes them, because there is nothing to distinguish.
# What is different is the cutting itself: a different column layout, a
# different photograph, a pull-quote in one and not the other. Their pictures
# are 41 apart out of 64, while the same cutting scanned twice is 0 or 1.
MATCH_PICTURES = True


@dataclass
class Pair:
    """One suspected copy and the clipping it appears to repeat."""

    primary: object
    copy: object
    score: float
    # A pair the rule did not flag but the user's own past verdicts say is
    # worth a look. A suggestion is shown in the review dialog and NEVER
    # excluded from the report - see core/verdicts for why that asymmetry is
    # the whole design.
    suggested: bool = False

    @property
    def why(self) -> str:
        return f"{self.score:.0f}% of the same headline"


def _score(first: str, second: str) -> tuple:
    """(forgiving, overall) - how alike two headlines are, each 0 to 100."""
    if _fuzz is not None:
        try:
            return (float(_fuzz.token_set_ratio(first, second)),
                    float(_fuzz.ratio(first, second)))
        except Exception:  # noqa: BLE001 - fall through to the exact test
            pass
    exact = 100.0 if first == second else 0.0
    return (exact, exact)


def _same_picture(first, second) -> bool:
    """Do the two cuttings look alike, not merely read alike?

    A clipping with no fingerprint - a picture that would not open - is let
    through on the words alone rather than being silently excused from the
    check; the headline test is still doing its work in that case.
    """
    apart = imageops.pictures_apart(getattr(first, "picture_hash", ""),
                                    getattr(second, "picture_hash", ""))
    if apart < 0:
        return True
    if apart > imageops.PICTURE_APART:
        return False
    # And below the masthead banner, where two stories from one paper stop
    # having anything in common. Without this, two different reports in the
    # same paper agree on the quarter of the picture the banner occupies and
    # come out inside the cut-off.
    below = imageops.pictures_apart(getattr(first, "picture_hash_lower", ""),
                                    getattr(second, "picture_hash_lower", ""))
    if below < 0:
        return True
    return below <= imageops.LOWER_APART


# WHY THE SHAPE AND INK MEASUREMENTS ARE NOT USED HERE.
#
# Both were tried as rejectors, on numbers that looked convincing: on the 6
# September documents, where every division file exists as both .docx and .pdf
# and the same cutting is therefore in the corpus twice, a shape gate at 30%
# throws away 74% of pairs that are not repeats and loses 1 of 71 that are, and
# an ink gate at 0.90 loses none of them at all.
#
# On a real morning they cost three of the seven repeats that were being found.
# The 6 September pairs are the EASY population - the same cutting extracted
# twice out of two renderings of one document - and the hard population is a
# WhatsApp photograph of a cutting against the same cutting inside a report.
# Measured on those: shape reaches 2.2 and ink reaches 1.1 on pairs whose
# pictures are 20 bits apart out of 64, which is well inside what this file
# already calls the same picture.
#
# So the trade was: about one second off a seventeen-second background stage,
# against three repeats in seven going unnoticed. A repeat that slips through is
# printed twice and somebody sees it. A clipping wrongly called a repeat is
# dropped from the report and nobody sees it - and the shipped rule makes that
# mistake zero times on every labelled pair there is. That is not a trade worth
# making, so the measurements are taken and stored, and nothing is decided on
# them automatically. They are what the review dialog learns from instead, where
# a wrong call is on screen in front of somebody.


def readable(clip) -> bool:
    """Can this clipping take part in matching at all?

    A cutting whose headline could not be read is left alone. Two unreadable
    cuttings have empty headlines, which are identical - and flagging them as
    copies of each other would be the worst kind of wrong, because the report
    would then quietly drop a clipping nobody ever looked at.
    """
    reading = ocr.Headline(getattr(clip, "ocr_text", "") or "",
                           getattr(clip, "headline_confidence", 0) or 0)
    return reading.usable


def spared(clip) -> bool:
    """Has the user already said this one is not a repeat?

    Their word is final, but only about this clipping being a COPY of
    something. It can still be the one that stays while a later arrival is
    marked against it - otherwise saying "not a duplicate" once would quietly
    stop the same cutting being caught when it turned up a third time.
    """
    return bool(getattr(clip, "not_duplicate", False))


def _ensure_prints(clips: list) -> None:
    """Every clipping has both picture prints, whoever made it."""
    from . import imageops

    for clip in clips:
        data = getattr(clip, "image_bytes", b"") or b""
        if not data:
            continue
        # One decode for all of them. Taking the two prints separately meant
        # decoding and trimming the same picture twice, and the trimming is the
        # expensive half - measured at 17ms a clipping against 8.8ms for one
        # pass, which is a second and a half on a full morning.
        if (getattr(clip, "picture_hash", "")
                and getattr(clip, "picture_hash_lower", "")
                and getattr(clip, "ink_profile", "")
                and getattr(clip, "content_w", 0)):
            continue
        try:
            # Of the picture as it PRINTS, crop and all - see measure_clip.
            found = imageops.measure_clip(clip)
        except Exception:  # noqa: BLE001 - a picture we cannot print
            continue
        clip.picture_hash = clip.picture_hash or found["whole"]
        clip.picture_hash_lower = clip.picture_hash_lower or found["lower"]
        clip.picture_hash_fine = (getattr(clip, "picture_hash_fine", "")
                                  or found["fine"])
        clip.ink_profile = getattr(clip, "ink_profile", "") or found["ink"]
        if not getattr(clip, "content_w", 0):
            clip.content_w = found["width"]
            clip.content_h = found["height"]


def _looks_like_anything(clips: list) -> set:
    """Which clippings resemble at least one other, by picture alone.

    This is the cheap half of the test and it runs first, which matters more
    than it looks. Reading a headline costs about half a second; taking a
    picture's fingerprint costs a few thousandths. On a morning of ninety
    clippings, checking the pictures first turns "read all ninety" into "read
    the four that could possibly be repeats" - three quarters of a minute off
    every import, for the same answer.
    """
    if not MATCH_PICTURES:
        return {clip.uid for clip in clips}
    close = set()
    for index, first in enumerate(clips):
        for second in clips[index + 1:]:
            if _same_picture(first, second):
                close.add(first.uid)
                close.add(second.uid)
    return close


def to_read(clips: Iterable) -> list:
    """The clippings whose headline is worth reading, and no others.

    Reading a headline costs about half a second; a picture fingerprint costs a
    few thousandths. So the pictures are compared first, and only a clipping
    that already LOOKS like another one is worth the half second.

    **How much that saves in practice: on a real morning, nothing.** Measured on
    142 clippings, 10,011 pairs: 36% of pairs pass the picture gate, and since a
    clipping needs only ONE partner to be worth reading, all 142 are shortlisted.
    The saving was real when the gate was 12 (20 of 142) - and at 12 the check
    missed five of the seven repeats it now finds. The sweep:

        gate  pairs   shortlist   real repeats lost
          12     14      20/142        5 of 7
          20    286     118/142        3 of 7
          24   1257     142/142        2 of 7
          28   3162     142/142        0 of 7   <- shipped

    So the gate cannot be tightened to shortlist fewer without losing repeats,
    and every clipping is read. This still costs nothing and is still the right
    shape - on a morning where half the clippings ARE distinctive it would save
    half the reading - but nobody should plan around a saving it does not make.

    :func:`find` does this internally through its ``read`` callback, which is
    right when the reading happens there and then. It cannot be used when the
    reading happens on another thread, because the answer is wanted before the
    reading starts rather than during it - hence this.
    """
    clips = list(clips)
    _ensure_prints(clips)
    close = _looks_like_anything(clips)
    return [clip for clip in clips
            if clip.uid in close
            and not getattr(clip, "ocr_engine", "")
            and getattr(clip, "image_bytes", b"")]


def find(clips: Iterable, threshold: float = SIMILARITY,
         overall: float = OVERALL, read=None) -> list:
    """Mark the repeats and return the pairs, in list order.

    The first clipping of a group is the one that stays - it is the one the
    person has already scrolled past - and every later one that matches it is
    marked as a copy of it. That also settles what happens with three or more of
    the same cutting: one primary, the rest copies of that same primary, rather
    than a chain where the third is a copy of the second.
    """
    clips = list(clips)
    for clip in clips:
        # Everything except the importer's own finding. flag_junk marks a
        # byte-identical repeat inside one document at import and points it at
        # what it repeats; clearing that here threw the pointer away, so the
        # badge and the "duplicate of what?" hover went blank on exactly the
        # clippings the importer had already been sure about.
        if not getattr(clip, "probable_junk", False):
            clip.duplicate_of = None

    # Make sure every clipping has both its prints before anything is compared.
    # They cost a few thousandths each, and correctness depends on them: a
    # MISSING lower print counts as "the pictures agree", so a clipping without
    # one is compared on the whole picture alone - which is how two different
    # stories under one newspaper's masthead banner were called copies. Relying
    # on the caller's read callback to fill them in left every clipping from an
    # older saved session in exactly that state.
    _ensure_prints(clips)

    close = _looks_like_anything(clips)
    if read is not None:
        for clip in clips:
            if clip.uid in close:
                read(clip)

    groups: list = []          # [(primary, normalised headline)]
    pairs: list[Pair] = []
    for clip in clips:
        if clip.uid not in close or not readable(clip):
            continue
        text = ocr.normalise(getattr(clip, "ocr_text", ""))
        best, best_score = None, 0.0
        for primary, head in groups:
            forgiving, whole = _score(text, head)
            if not (forgiving >= threshold and whole >= overall):
                continue
            if MATCH_PICTURES and not _same_picture(clip, primary):
                continue
            if forgiving > best_score:
                best, best_score = primary, forgiving
        if best is None or spared(clip):
            # Either nothing matches it, or the user has already ruled on it.
            # Both ways it stays, and both ways it can be the one a later
            # arrival is matched against.
            groups.append((clip, text))
        else:
            clip.duplicate_of = best.uid
            pairs.append(Pair(best, clip, best_score))
    return pairs


# How many second looks are worth offering. Enough to be useful on a morning
# where the check missed several, few enough that the dialog is still a
# few decisions rather than an afternoon.
MOST_SUGGESTIONS = 25

# How alike two headlines must be before a picture is allowed to suggest the
# pair, when BOTH of them could be read.
#
# A suggestion is made on the picture alone, which is the point of it - it
# catches the repeats the words miss. But two cuttings that are both a narrow
# column of type under a bold line resemble one another to a difference hash
# whatever they say, and putting two plainly different stories in front of
# somebody wastes the glance and teaches them to stop looking.
#
# Deliberately low. This is not a second opinion on whether the pair is a
# repeat - the words having missed it is WHY the suggestion is being made. It
# only refuses the pairs whose words actively disagree. Measured on a real
# morning: the weakest pair the headline rule genuinely flagged scores 74.6, and
# the only suggestion made that morning scores 69.0 and is a real repeat, so
# nothing that morning is lost. The reported wrong pair scores 51.7.
#
# A clipping that could not be read has no opinion, and is never refused on
# these grounds: silence is not disagreement.
#
# Set at 70, which is where a suggestion stops being worth making. A suggestion
# exists for the pairs the WORDS missed, so by construction every one of them
# scores under the rule's own gate; the question here is only whether they
# missed narrowly - two readings of one cutting that disagree - or whether they
# are two different stories that happen to be laid out alike. The reported pair
# scores 69.2, which is close to the line, and the line is where it is because
# 69 on a six-word headline is not "nearly agreed": those two share only "will
# run", "special" and "trains".
#
# Measured after the headline fix, on the 7 September morning: ten real repeats
# flagged, the weakest at 86.1, and no suggestions made at all - so on that
# morning this refuses nothing whatever it is set to. The genuinely ambiguous
# pairs are what the trainer is for, and a verdict there tightens the picture
# distance so the same pair is never offered twice.
WORDS_DISAGREE = 70.0


def suggestions(clips: Iterable, pairs: list) -> list:
    """Pairs worth a second look, learned from what the user has already said.

    Only ever ADDED to the review dialog, never acted on. The shipped rule makes
    no wrong drops on any labelled pair there is, so there is nothing here to
    make safer; what these are for is the repeats it MISSES, which on the sample
    mornings is nearly four in ten.
    """
    from . import imageops, verdicts

    clips = list(clips)
    cutoff = verdicts.suggestion_cutoff()
    already = {(id(pair.primary), id(pair.copy)) for pair in pairs}
    already |= {(id(pair.copy), id(pair.primary)) for pair in pairs}
    flagged = {id(pair.copy) for pair in pairs}

    found = []
    for index, first in enumerate(clips):
        for second in clips[index + 1:]:
            if (id(first), id(second)) in already:
                continue
            if id(second) in flagged or id(first) in flagged:
                continue
            if spared(second) or spared(first):
                continue        # already ruled on, do not ask twice
            apart = imageops.pictures_apart(
                getattr(first, "picture_hash_fine", ""),
                getattr(second, "picture_hash_fine", ""))
            if 0 <= apart <= cutoff and not _words_object(first, second):
                found.append((apart, Pair(first, second,
                                          100.0 - apart * 100.0 / 256.0,
                                          suggested=True)))
    # Closest first, and not too many. A review dialog with two hundred
    # suggestions in it is not a help, it is a second job - and since none of
    # these is acted on, the ones worth anybody's time are the near ones.
    found.sort(key=lambda item: item[0])
    return [pair for _apart, pair in found[:MOST_SUGGESTIONS]]


def _words_object(first, second) -> bool:
    """Do these two cuttings plainly say different things?

    Only when BOTH could be read. An unreadable clipping is not disagreeing, it
    is silent, and refusing a suggestion on silence would take away exactly the
    case the suggestion exists for. See WORDS_DISAGREE.
    """
    if not (readable(first) and readable(second)):
        return False
    left = ocr.normalise(getattr(first, "ocr_text", "") or "")
    right = ocr.normalise(getattr(second, "ocr_text", "") or "")
    if not left or not right:
        return False
    _forgiving, overall = _score(left, right)
    # The plain ratio, not the forgiving one. The forgiving count is a set
    # comparison: two different stories that share "will run", "special" and
    # "trains" score 74 on it however plainly they differ. It is the wrong
    # instrument for asking whether two headlines DISAGREE, which is the only
    # question here.
    return overall < WORDS_DISAGREE


def apply(clips: Iterable, threshold: float = SIMILARITY,
          overall: float = OVERALL, read=None) -> list:
    """Find the repeats and mark them. Nothing is removed from the report here.

    It used to switch `include` off, so a flagged clipping was out of every
    export the moment the check ran. That is exactly the mistake that cannot be
    seen: measured on one real morning, three of the six clippings it removed
    were separate pieces of coverage, and nothing on screen said a clipping had
    gone. The department's instruction, in their words, was "never remove
    silently, always ask me".

    So the flag is a flag now. The clipping is badged as a suspected repeat,
    the card says what it repeats, and it stays in the report until somebody
    looks at the pair and presses Delete in the review screen.

    Anything this check switched off in an earlier build is switched back on -
    a clipping sitting outside the report because a previous version decided so
    on its own is the very thing being fixed.
    """
    clips = list(clips)
    pairs = find(clips, threshold, overall, read)
    for clip in clips:
        if getattr(clip, "excluded_as_duplicate", False):
            clip.include = True
            clip.excluded_as_duplicate = False
    return pairs


# How much of a file has to repeat another file before the file itself is
# called a repeat. Not all of it: one clipping in twenty may fail to read, or
# be cropped differently, and the file is still plainly the same file.
WHOLE_FILE_SHARE = 0.8
WHOLE_FILE_LEAST = 3


def whole_files(clips: Iterable, group_of) -> dict:
    """Which whole files are repeats of another whole file.

    The same division's report arriving twice - once as the Word file and once
    as the PDF of it - is not ninety separate duplicate clippings. It is one
    mistake, made once, and the useful thing to say is "this file is already
    here" so it can go in one action rather than ninety.

    ``group_of`` takes a clipping and returns which file it came in from.
    Returns {file: the file it repeats}, and only for files where nearly every
    clipping repeats that same one - a file sharing two clippings with another
    is two divisions covering the same story, which is ordinary and expected.
    """
    from collections import Counter, defaultdict

    where = defaultdict(list)
    for clip in clips:
        where[group_of(clip)].append(clip)

    primary_of = {clip.uid: clip for clip in clips}
    repeats = {}
    for name, members in where.items():
        if len(members) < WHOLE_FILE_LEAST:
            continue
        points_at = Counter()
        for clip in members:
            other = primary_of.get(clip.duplicate_of or "")
            if other is not None:
                points_at[group_of(other)] += 1
        if not points_at:
            continue
        target, count = points_at.most_common(1)[0]
        if target != name and count / len(members) >= WHOLE_FILE_SHARE:
            repeats[name] = target
    return repeats


def summary(pairs: list) -> str:
    """What to put on the button."""
    if not pairs:
        return ""
    return f"{len(pairs)} duplicate{'s' if len(pairs) != 1 else ''}"
