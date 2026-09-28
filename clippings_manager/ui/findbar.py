"""Finding a clipping by what it says.

A morning is a hundred and sixty clippings on one long page, and the question
somebody actually has is "where is the one about the hydrogen train?". Scrolling
for it means reading a hundred and sixty thumbnails.

WHAT IS SEARCHED. Everything a clipping says about itself, in this order of
preference: the headline that prints above it, the headline read off the picture
by the reader, the newspaper, the edition, and the address a link came from. A
clipping matches if any of them does, and the one that matched is what the
result shows - so it is always clear WHY something came up.

HOW IT MATCHES. Two letters are enough. A plain "contains" first, on text with
its case, its punctuation and its Devanagari matras folded away, so "hydrogen"
finds "Hydrogen" and "रेलवे" finds "रेलवे," - and then, only for anything that
did not match that way, a fuzzy pass (rapidfuzz) that forgives a letter or two,
because a headline read off a picture is never read perfectly. The fuzzy pass
needs four letters before it will guess: on two it matched half the morning.
And related words (2.0.62): another form of an English word - "derailment"
finds "derailed" - or the same name spelt a letter apart. See RELATED_STEM.

WHAT A RESULT SHOWS (2.0.62). The words found are marked in yellow on the line
shown, and the line shown is the field holding most of what was looked for.
Under it: which field that is, "close match" when it was only guessed at, and
where the clipping came from - its column on the board, and its division.

IT IS A LENS, NOT AN EDIT. Nothing is hidden, reordered, ticked or unticked -
the list underneath is exactly as it was. Picking a result scrolls to that
clipping and opens it. Closing the box leaves nothing behind.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPixmap, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (QCheckBox, QCompleter, QDialog,
                               QDialogButtonBox, QFrame,
                               QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QPushButton, QScrollArea,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from . import theme

#: Fewer letters than this and nothing is looked for: one letter matches
#: almost every clipping of the morning, which is not an answer.
LEAST_LETTERS = 2
#: And the forgiving pass waits until there is enough to forgive from.
LEAST_FUZZY = 4
#: How alike a fuzzy match has to be, out of a hundred.
FUZZY_AT = 78
#: Never more than this many results: past it the box is a second list rather
#: than an answer, and the one that is wanted is not in it either.
MOST_RESULTS = 40
#: How long after the last keystroke the search runs. Long enough that typing
#: a word does not search five times.
AFTER_TYPING_MS = 140
#: How many searches back the field remembers, and where they are kept. Install
#: wide, beside the rest of the settings, because a search is about the
#: clippings rather than about one newspad - the same story is looked for in
#: whichever newspad it is being compiled into.
RECENT_KEPT = 8
RECENT_KEY = "recent_searches"
#: The padding the offer's own panel carries, which has to be added back when
#: it is sized - see offer_recent.
OFFER_PAD = 4
#: The last line of the offer, which empties it. On the list itself rather than
#: hidden on a right-click, because a list somebody wants rid of is a list they
#: are looking at - and a search typed by mistake, or one with somebody's name
#: in it, should not need to be hunted for.
CLEAR_ROW = "\u00d7   Clear all recent searches"


def recent() -> list:
    """What was searched for lately, newest first."""
    try:
        from .export_dialog import load_settings

        kept = load_settings().get(RECENT_KEY) or []
    except Exception:  # noqa: BLE001 - no settings yet is no history
        return []
    out = []
    for one in kept:
        words = str(one or "").strip()
        if words and words not in out:
            out.append(words)
    return out[:RECENT_KEPT]


def remember(wanted: str) -> None:
    """Keep one search, at the front, without repeating it."""
    words = str(wanted or "").strip()
    if len(fold(words).replace(" ", "")) < LEAST_LETTERS:
        return
    try:
        from .export_dialog import load_settings, save_settings

        kept = [one for one in recent() if one.casefold() != words.casefold()]
        save_settings({**load_settings(),
                       RECENT_KEY: [words, *kept][:RECENT_KEPT]})
    except Exception:  # noqa: BLE001 - a convenience, never a crash
        pass

#: Devanagari vowel signs, nukta and virama - the marks that make one spelling
#: of a word two. Folded away so a headline read off a picture, which often
#: loses them, still finds the one that has them.
_MARKS = re.compile(r"[ऀ-ःऺ-ॏ॑-ॗॢॣ]")
_QUIET = re.compile(r"[^\wऀ-ॿ]+", re.UNICODE)


def fold(words: str) -> str:
    """One line of text, as the search compares it."""
    plain = unicodedata.normalize("NFKD", str(words or "")).casefold()
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    plain = _MARKS.sub("", plain)
    return _QUIET.sub(" ", plain).strip()


#: What is looked at, and what each is called in a result.
FIELDS = (
    ("printed_caption", "label"),
    ("label", "label"),
    ("ocr_text", "OCR headline"),
    ("newspaper", "newspaper"),
    ("edition", "edition"),
    ("url", "link"),
)


def _said(clip, name: str) -> str:
    try:
        value = getattr(clip, name, "")
    except Exception:  # noqa: BLE001
        return ""
    return str(value or "").strip()


#: A field can be asked for by name, the way a search engine lets you:
#: paper:jagran, headline:kavach, link:indianexpress, label:jagran.
BY_NAME = {
    # The HEADLINE is what the OCR reads off the picture; the label is the
    # newspaper's name. "title:" still means the label, as it always did.
    "headline": ("ocr_text",),
    "label": ("printed_caption", "label"),
    "title": ("printed_caption", "label"),
    "read": ("ocr_text",),
    "ocr": ("ocr_text",),
    "paper": ("newspaper",),
    "newspaper": ("newspaper",),
    "edition": ("edition",),
    "city": ("edition",),
    "link": ("url",),
    "url": ("url",),
}

_TOKENS = re.compile(r'"[^"]*"|\S+')


@dataclass
class Term:
    """One thing asked for: some words, where to look, and whether it must
    NOT be there."""

    words: str
    fields: tuple = ()
    negated: bool = False
    phrase: bool = False


def parse(wanted: str) -> list:
    """A query as groups of terms: [[Term, ...], ...], the groups joined by OR
    and the terms inside a group joined by AND.

    The syntax somebody already knows from a search box:

        hydrogen train        both words, anywhere
        hydrogen OR train     either one
        "vande bharat"        those words in that order
        -cricket              not that
        paper:jagran          only in the newspaper

    OR must be capitals, so a headline with the word "or" in it is still just
    a word. Everything else is a word to look for.
    """
    groups: list = [[]]
    for raw in _TOKENS.findall(str(wanted or "")):
        piece = raw.strip()
        if not piece:
            continue
        if piece == "OR":
            if groups[-1]:
                groups.append([])
            continue
        negated = piece.startswith("-") and len(piece) > 1
        if negated:
            piece = piece[1:]
        fields: tuple = ()
        if ":" in piece and not piece.startswith('"'):
            name, _sep, rest = piece.partition(":")
            found = BY_NAME.get(name.strip().lower())
            if found and rest.strip():
                fields, piece = found, rest.strip()
        phrase = piece.startswith('"') and piece.endswith('"') and len(piece) > 1
        if phrase:
            piece = piece[1:-1]
        piece = piece.strip()
        if not piece:
            continue
        groups[-1].append(Term(piece, fields, negated, phrase))
    return [group for group in groups if group]


def _looked_at(clip, term: Term, folded: Optional[dict] = None) -> list:
    """[(its place in FIELDS, what it is called, what it says, folded)] for
    the fields a term asks about - all of them when it asks for none.

    ``folded`` keeps what each text folds to for the length of one search: a
    field is folded once however many words are looked for in it, where it
    used to be folded again for every one - an eleven-word headline sent by a
    find button folded every field of the morning eleven times.
    """
    wanted = term.fields
    out = []
    for place, (name, called) in enumerate(FIELDS):
        if wanted and name not in wanted:
            continue
        says = _said(clip, name)
        if not says:
            continue
        if folded is None:
            plain = fold(says)
        else:
            plain = folded.get(says)
            if plain is None:
                plain = folded[says] = fold(says)
        out.append((place, called, says, plain))
    return out


#: RELATED WORDS (2.0.62). Beyond forgiving a misread letter, a word can be
#: another form of the one looked for: "electrification" finds "electrified",
#: "derailment" finds "derailed", "inspection" finds "inspected", and a paper
#: spelt "Jagaran" in one file finds "Jagran" in another. Two words are related
#: when they share a stem - the start they have in common runs to within four
#: letters of the shorter, and is at least five letters long, and the shorter
#: is at least three fifths the length of the longer - AND what is left of
#: each after it is an English ending, one of them at least a plain one (the
#: word as it is, a plural, a past tense, an -ing: RELATED_PLAIN); or when
#: they are one spelling apart at six letters or more (rapidfuzz, 88 of 100).
#:
#: Each rule is there for a pair it had to keep apart. The length: "india"
#: and "indianexpress". The endings: "passed" and "passenger", "transfer" and
#: "transport", "election" and "electricity", which share five letters and
#: nothing else. The plain one: two derived endings meet on unrelated words -
#: "department" and "departure", "government" and "governor", "position" and
#: "positive" - where a derived and a plain one meet on the same word:
#: "diversion" and "diverted", "suspension" and "suspended", "collision" and
#: "collided". Measured on four hundred words of railway news.
#:
#: For English words of five letters or more only. A Hindi word is already
#: matched in all its forms, because folding takes the vowel signs off it
#: (यात्री finds यात्रियों). Measured on every English word in the office's
#: saved newspads and a list of the searches a railway office makes: 88 keeps
#: "resumes" away from "rescues" (86), and the stem rule's worst catch was
#: "stationery" for "stations".
RELATED_STEM = 5
RELATED_SLACK = 4
RELATED_SHARE = 0.6
#: The plain endings: the word itself, its plural, its past, its -ing - with
#: the doubled letter a short word takes before them (transfer, transferred).
RELATED_PLAIN = frozenset((
    "", "s", "es", "e", "d", "ed", "ded", "ted", "sed", "led", "red", "ped",
    "ned", "ged", "ing", "ings", "ling", "ring", "ting", "ning", "ping",
    "ging", "ies", "ied"))
#: And the derived ones, which may meet a plain one but never each other.
#: Not -er or -or: an agent is somebody else - the director is not what was
#: directed, the engineer not the engine, the counter not the count.
RELATED_DERIVED = frozenset((
    "ion", "ions", "tion", "tions", "sion", "sions", "ption", "ation",
    "ations", "ication", "ications", "lation", "lations", "ment", "ments",
    "ement", "ements", "ery", "al", "ally", "ly", "ity", "ified", "ify",
    "ive", "ist", "ists", "ise", "ised", "ize", "ized", "isation",
    "ization", "ure", "ance", "ence", "ant", "ent", "age"))
RELATED_ENDINGS = RELATED_PLAIN | RELATED_DERIVED
#: A "y" meets only the plural and the past that replace it: facility and
#: facilities, injury and injuries - never police and policy.
RELATED_Y = frozenset(("ies", "ied", "ier", "iest"))
#: The railway's own everyday words, whose longer forms mean something else
#: - "training" is not a train, "boarding" not the Railway Board, "department"
#: not a departure. Nearly every clipping holds one of these, so a search for
#: the longer word would bring back the whole morning. They are found as
#: typed, and by the forgiving pass, but never as another word's form.
RELATED_NEVER = ("train", "track", "board", "drive", "engine", "count",
                 "press", "coach", "depart", "govern", "gener", "posit",
                 "hospital", "polic", "station", "servic", "direct",
                 "conduct", "divers", "stat")
RELATED_TYPO = 88
RELATED_TYPO_LETTERS = 6
_LATIN_WORD = re.compile(r"[a-z]+")


def _common_start(one: str, other: str) -> int:
    count = 0
    for a, b in zip(one, other):
        if a != b:
            break
        count += 1
    return count


def related_word(wanted: str, word: str) -> bool:
    """Whether a word on a clipping is a form of the word looked for - see
    RELATED_STEM. Both folded; the same word is not "related", it is found."""
    if wanted == word or len(wanted) < RELATED_STEM or len(word) < RELATED_STEM:
        return False
    if not (_LATIN_WORD.fullmatch(wanted) and _LATIN_WORD.fullmatch(word)):
        return False
    shorter, longer = sorted((len(wanted), len(word)))
    shared = _common_start(wanted, word)
    stem = wanted[:shared]
    everyday = any(stem.startswith(base) and shared <= len(base) + 2
                   for base in RELATED_NEVER)
    if (not everyday
            and shared >= max(RELATED_STEM, shorter - RELATED_SLACK)
            and shorter >= RELATED_SHARE * longer):
        # The cut may sit up to two letters back from where the two part:
        # electrifi|cation and electrifi|ed meet as electrif|ication, |ied.
        for cut in range(shared, max(shared - 3, 3), -1):
            one, other = wanted[cut:], word[cut:]
            if (one in RELATED_ENDINGS and other in RELATED_ENDINGS
                    and (one in RELATED_PLAIN or other in RELATED_PLAIN)):
                return True
            if (one == "y" and other in RELATED_Y) or (
                    other == "y" and one in RELATED_Y):
                return True
    if everyday:
        return False
    if min(len(wanted), len(word)) < RELATED_TYPO_LETTERS:
        return False
    try:
        from rapidfuzz import fuzz
    except Exception:  # noqa: BLE001 - without it, stems alone
        return False
    return fuzz.ratio(wanted, word) >= RELATED_TYPO


def _related_in(wanted: str, plain: str) -> bool:
    """Whether a folded field holds a word related to a one-word term."""
    return any(related_word(wanted, word) for word in plain.split())


def _field_hits(clip, term: Term, folded: Optional[dict] = None,
                related: bool = True) -> dict:
    """{place in FIELDS: "exact" or "close"} - every field this term is in.

    Exact first: where the words are there as typed, those are the answer and
    nothing is guessed at. Otherwise, for a word that is not a quoted phrase
    and has four letters to go on, the forgiving pass - a letter or two misread
    (partial_ratio) - and for a single English word its other forms
    (related_word). ``related`` False keeps a -word to the old rule, so a
    minus leaves out what it always left out and no more.
    """
    wanted = fold(term.words)
    if not wanted:
        return {}
    looked = _looked_at(clip, term, folded)
    exact = {place: "exact" for place, _c, _s, plain in looked if wanted in plain}
    if exact:
        return exact
    # A phrase is asked for exactly; only a loose word is guessed at.
    if term.phrase or len(wanted.replace(" ", "")) < LEAST_FUZZY:
        return {}
    try:
        from rapidfuzz import fuzz
    except Exception:  # noqa: BLE001 - without it, the plain pass is the search
        return {}
    close = {}
    single = related and " " not in wanted
    for place, _called, _says, plain in looked:
        if fuzz.partial_ratio(wanted, plain) >= FUZZY_AT or (
                single and _related_in(wanted, plain)):
            close[place] = "close"
    return close


def _term_hit(clip, term: Term) -> tuple:
    """(does this term match, which field, what it says) - the first field in
    FIELDS order it is in. Kept for anything that asks one term at a time."""
    hits = _field_hits(clip, term, related=not term.negated)
    if not hits:
        return False, "", ""
    place = min(hits)
    name, called = FIELDS[place]
    return True, called, _said(clip, name)


def match_detail(clip, wanted: str, folded: Optional[dict] = None,
                 groups: Optional[list] = None) -> tuple:
    """(does it match, which field, what it says, found only by guessing).

    A group matches when every plain term in it does and no negated one does;
    the query matches when any group does. The field reported - the line the
    result shows - is the one that holds most of what was looked for, words
    found as typed counting for more than words guessed at, the earlier field
    winning a tie: so the line on show is the one with the most of it to mark.
    """
    groups = parse(wanted) if groups is None else groups
    if not groups:
        return False, "", "", False
    asked = "".join(fold(term.words).replace(" ", "")
                    for group in groups for term in group if not term.negated)
    if len(asked) < LEAST_LETTERS:
        return False, "", "", False
    # A side of an OR found only by guessing is kept in reserve: a later side
    # found as typed is the answer - its line, and no "close match" - whichever
    # order the two were typed in.
    reserve = None
    for group in groups:
        scores: dict = {}
        held, guessed = True, False
        for term in group:
            hits = _field_hits(clip, term, folded, related=not term.negated)
            if term.negated:
                if hits:
                    held = False
                    break
                continue
            if not hits:
                held = False
                break
            if all(kind == "close" for kind in hits.values()):
                guessed = True
            for place, kind in hits.items():
                scores[place] = scores.get(place, 0) + (2 if kind == "exact" else 1)
        if held and scores:
            place = max(scores, key=lambda at: (scores[at], -at))
            name, called = FIELDS[place]
            answer = (True, called, _said(clip, name), guessed)
            if not guessed:
                return answer
            if reserve is None:
                reserve = answer
    return reserve or (False, "", "", False)


def matches(clip, wanted: str) -> tuple:
    """(does it match, which field, what that field says) for one clipping.
    See match_detail, which also says whether it was only found by guessing."""
    hit, which, says, _guessed = match_detail(clip, wanted)
    return hit, which, says


def search_detail(rows, wanted: str) -> tuple:
    """([(row, which, says, guessed)], how many matched in all), in list order.

    Never more than MOST_RESULTS. When more matched than that, the ones found
    as typed are kept before the ones guessed at - a looser match must not
    push a real one off the end of the box - and what is kept is shown in
    list order all the same: the order is the list's, and the preview walks
    it (MainWindow._go_to_clip).
    """
    groups = parse(wanted)
    folded: dict = {}
    found = []
    for row in rows:
        clip = getattr(row, "clip", None)
        if clip is None:
            continue
        hit, which, says, guessed = match_detail(clip, wanted, folded, groups)
        if hit:
            found.append((row, which, says, guessed))
    total = len(found)
    if total > MOST_RESULTS:
        sure = [one for one in found if not one[3]]
        keep = sure[:MOST_RESULTS]
        if len(keep) < MOST_RESULTS:
            spare = MOST_RESULTS - len(keep)
            keep_ids = {id(one) for one in keep}
            keep += [one for one in found
                     if one[3] and id(one) not in keep_ids][:spare]
        order = {id(one): at for at, one in enumerate(found)}
        found = sorted(keep, key=lambda one: order[id(one)])
    return found, total


def search(rows, wanted: str) -> list:
    """[(row, which field matched, what it says)], in list order."""
    found, _total = search_detail(rows, wanted)
    return [(row, which, says) for row, which, says, _guessed in found]


# ------------------------------------------------------ marking the words
#: The characters a word is made of, for widening a mark to whole words: a
#: mark that began or ended inside a Devanagari cluster would change how the
#: cluster is shaped (measured: 315 px of line became 330).
_WORD_CHARS = re.compile(r"[\wऀ-ॿ̀-ͯ‌‍]", re.UNICODE)


def fold_map(text: str) -> tuple:
    """(what fold() makes of the text, and for each of its characters the
    place in the text it came from) - so a word found in the folded text can
    be marked where it stands in the text as written."""
    source = str(text or "")
    chars: list = []
    origin: list = []
    for place, char in enumerate(source):
        piece = unicodedata.normalize("NFKD", char).casefold()
        piece = "".join(ch for ch in piece if not unicodedata.combining(ch))
        piece = _MARKS.sub("", piece)
        for ch in piece:
            chars.append(ch)
            origin.append(place)
    out: list = []
    where: list = []
    quiet = False
    for ch, place in zip(chars, origin):
        if _QUIET.fullmatch(ch):
            if not quiet:
                out.append(" ")
                where.append(place)
            quiet = True
            continue
        quiet = False
        out.append(ch)
        where.append(place)
    while out and out[0] == " ":
        out.pop(0)
        where.pop(0)
    while out and out[-1] == " ":
        out.pop()
        where.pop()
    return "".join(out), where


def _near_word(part: str, plain: str) -> list:
    """Where one word of a search sits in a folded line: as typed, or the
    forgiving pass's window trimmed to the one word it covers."""
    out = [(hit.start(), hit.end())
           for hit in re.finditer(re.escape(part), plain)]
    if out:
        return out
    try:
        from rapidfuzz import fuzz

        near = fuzz.partial_ratio_alignment(part, plain)
    except Exception:  # noqa: BLE001
        return []
    if near is None or near.score < FUZZY_AT:
        return []
    pieces = [(near.dest_start + piece.start(), near.dest_start + piece.end())
              for piece in re.finditer(r"[^ ]+",
                                       plain[near.dest_start:near.dest_end])]
    return [max(pieces, key=lambda span: span[1] - span[0])] if pieces else []


def _looks_like(want: str, words: str) -> bool:
    """Whether a marked stretch resembles what was searched: it holds it, or
    it is near it - a letter or two misread (rapidfuzz ratio over 70), or
    another form of it."""
    if not words:
        return False
    if want in words or words in want:
        return True
    try:
        from rapidfuzz import fuzz
    except Exception:  # noqa: BLE001 - without it, keep the mark
        return True
    for part in want.split():
        for word in words.split():
            if (part in word or fuzz.ratio(part, word) >= 70
                    or related_word(part, word)):
                return True
    return False


def _widen(text: str, start: int, end: int) -> tuple:
    """Out to the edges of the words the span touches."""
    while start > 0 and _WORD_CHARS.match(text[start - 1]):
        start -= 1
    while end < len(text) and _WORD_CHARS.match(text[end]):
        end += 1
    return start, end


#: The fields a term asking by name is allowed to mark, by what a result calls
#: the field it shows.
_CALLED = {
    "label": ("printed_caption", "label"),
    "OCR headline": ("ocr_text",),
    "newspaper": ("newspaper",),
    "edition": ("edition",),
    "link": ("url",),
}


def marks(says: str, wanted: str, which: str = "") -> list:
    """[(start, end)] in ``says``: the words the search found there, as whole
    words, for marking in yellow.

    Every plain term, found as typed; where a term was not, what the forgiving
    pass matched and its related forms. A minus term is never marked. A term
    of one letter (की and के fold to one) marks nothing, and one of two marks
    only the words it starts, or every word of a Hindi line would light up.
    """
    text = str(says or "")
    if not text:
        return []
    plain, origin = fold_map(text)
    if not plain:
        return []
    names = _CALLED.get(which, ())
    spans: list = []
    for group in parse(wanted):
        for term in group:
            if term.negated:
                continue
            if term.fields and names and not set(term.fields) & set(names):
                continue
            want = fold(term.words)
            letters = len(want.replace(" ", ""))
            if letters < 2:
                continue
            found: list = []
            for hit in re.finditer(re.escape(want), plain):
                start, end = hit.start(), hit.end()
                if letters == 2 and start > 0 and plain[start - 1] != " ":
                    continue            # two letters: only where a word starts
                found.append((start, end))
            if not found and not term.phrase and letters >= LEAST_FUZZY:
                if " " in want:
                    # Words looked for together - a route, "delhi-ambala" -
                    # each found on its own: one window over both carried the
                    # mark of a short reading on to the word beside it.
                    for part in want.split():
                        if len(part) >= LEAST_FUZZY:
                            found.extend(_near_word(part, plain))
                else:
                    # The forgiving pass's window, trimmed to the one word it
                    # covers (see _near_word), and the word's other forms.
                    found.extend(_near_word(want, plain))
                    at = 0
                    for word in plain.split(" "):
                        if related_word(want, word):
                            found.append((at, at + len(word)))
                        at += len(word) + 1
            for start, end in found:
                if end <= start or start >= len(origin):
                    continue
                first = origin[start]
                last = origin[min(end, len(origin)) - 1] + 1
                first, last = _widen(text, first, last)
                # A mark on a word that looks nothing like what was searched
                # - the forgiving pass matched across two words, "ch in" in
                # "Kavach installation" for "chain" - marks nothing.
                if not _looks_like(want, fold(text[first:last])):
                    continue
                spans.append((first, last))
    spans.sort()
    merged: list = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


#: How much of a line a result shows, and how far before the first marked
#: word it starts when that word is further along than this.
SHOWN = 150
LEAD = 40


def marked_html(says: str, spans: list, colour: str = "",
                ink: str = "") -> str:
    """The line as rich text, the marked words on yellow. Every piece of the
    text is escaped - a headline that happens to hold "<b>" is words.

    Long lines are cut to SHOWN characters at a word, and when the first mark
    lies further along than LEAD the line starts a few words before it, after
    an ellipsis: a result is one line, and a mark out of sight is no mark.
    """
    import html as _html

    text = str(says or "")
    colour = colour or theme.HIGHLIGHT
    ink = ink or theme.HIGHLIGHT_INK
    begin = 0
    if spans and spans[0][0] > LEAD:
        begin = spans[0][0] - LEAD // 2
        space = text.rfind(" ", 0, begin)
        begin = space + 1 if space >= 0 else begin
    end = min(len(text), begin + SHOWN)
    if end < len(text):
        space = text.rfind(" ", begin, end)
        if space > begin + SHOWN // 2:
            end = space
    out = ["… " if begin > 0 else ""]
    at = begin
    for start, stop in spans:
        if stop <= begin or start >= end:
            continue
        start, stop = max(start, begin), min(stop, end)
        out.append(_html.escape(text[at:start]))
        out.append(
            f'<span style="background-color:{colour}; color:{ink};'
            f' font-weight:800;">{_html.escape(text[start:stop])}</span>')
        at = stop
    out.append(_html.escape(text[at:end]))
    if end < len(text):
        out.append(" …")
    return "".join(out)


class Result(QFrame):
    """One clipping in the results: its number, its picture, what it says."""

    picked = Signal(int)
    ticked = Signal()

    def __init__(self, number: int, row, which: str, says: str, parent=None,
                 where: str = "", wanted: str = "", guessed: bool = False):
        super().__init__(parent)
        self.row_id = row.id
        self.number = number
        self.setObjectName("FindResult")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "#FindResult { background: rgba(255, 255, 255, 0.55);"
            " border: 1px solid rgba(15, 23, 42, 0.08); border-radius: 10px; }"
            "#FindResult:hover { background: rgba(255, 255, 255, 0.92);"
            f" border-color: {theme.NAVY}55; }}"
            "#FindResult QLabel { background: transparent; border: none; }")
        line = QHBoxLayout(self)
        line.setContentsMargins(9, 7, 11, 7)
        line.setSpacing(10)

        self.tick = QCheckBox()
        self.tick.setToolTip("Pick this one out, to send it somewhere")
        self.tick.toggled.connect(lambda _on: self.ticked.emit())
        line.addWidget(self.tick)

        tag = QLabel(f"{number}")
        tag.setFixedWidth(30)
        tag.setAlignment(Qt.AlignCenter)
        tag.setStyleSheet(
            f"color: {theme.NAVY}; font-size: 12px; font-weight: 800;")
        line.addWidget(tag)

        picture = QLabel()
        picture.setFixedSize(54, 40)
        picture.setAlignment(Qt.AlignCenter)
        thumb = getattr(row, "thumbnail", None)
        if isinstance(thumb, QPixmap) and not thumb.isNull():
            picture.setPixmap(thumb.scaled(54, 40, Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation))
        picture.setStyleSheet("border-radius: 4px;")
        line.addWidget(picture)

        words = QVBoxLayout()
        words.setSpacing(1)
        # THE WORDS FOUND, MARKED IN YELLOW - the same yellow as selected text
        # in the preview - as whole words, so a Hindi cluster is never cut in
        # two by a mark. Rich text, every piece of it escaped.
        self.spans = marks(says, wanted, which) if wanted else []
        head = QLabel()
        head.setTextFormat(Qt.RichText)
        head.setText(marked_html(says, self.spans))
        # Hindi a size larger, the same as the boxes on a row - a headline in
        # Devanagari at the size the English is set at reads smaller than it,
        # and a result is read at a glance or it is no use.
        head.setStyleSheet(
            f"color: {theme.INK};"
            f" font-size: {theme.reading_size(says, 12)}px;"
            " font-weight: 600;")
        head.setWordWrap(False)
        # Never wider than the box it is in: a one-line label otherwise asks
        # for its whole length, and the words marked at the end of a long
        # headline sat past a sideways scroll.
        head.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        head.setMinimumWidth(40)
        self.head = head
        # Where it is, when the number alone does not say: on the board's four
        # columns every column counts from 1, so "3" is three clippings; and
        # the division it came from, which the file it was imported in says.
        parts = [which]
        if guessed:
            parts.append("close match")
        if where:
            parts.append(where)
        said_where = QLabel("  \u00b7  ".join(part for part in parts if part))
        said_where.setStyleSheet(
            f"color: {theme.MUTED}; font-size: 10px; font-weight: 700;")
        said_where.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        source = str(getattr(row, "source_name", "") or "").strip()
        if source:
            said_where.setToolTip(f"From {source}")
        self.said_where = said_where
        words.addWidget(head)
        words.addWidget(said_where)
        line.addLayout(words, 1)

    def mousePressEvent(self, event):  # noqa: N802 - Qt name
        # The tick box is its own control: clicking it picks the clipping OUT,
        # it does not open it.
        if (event.button() == Qt.LeftButton
                and not self.tick.geometry().contains(event.position().toPoint())):
            self.picked.emit(self.row_id)
        super().mousePressEvent(event)


class FindBox(QFrame):
    """The translucent panel of results, floating over the page."""

    picked = Signal(int)
    #: (row ids, newspad number) - put copies of the ticked results there.
    shiftWanted = Signal(list, int)
    #: (row ids, level) - give the ticked results this priority; 0 clears it.
    priorityWanted = Signal(list, int)
    #: (row ids, "top" or "bottom") - send the ticked results to that end.
    arrangeWanted = Signal(list, str)
    #: (menu, row ids) - the Move to menu is opening; the window fills it,
    #: because only the window knows which files are in the list.
    moveMenuOpening = Signal(object, list)

    PRIORITY_TIP = ("Give every ticked result the same priority - or clear "
                    "it. They move to where that priority sits in the list, "
                    "as one step that Ctrl+Z takes back.")
    TOP_TIP = ("Send the ticked results to the top of the list, in the order "
               "they are in now.")
    BOTTOM_TIP = ("Send the ticked results to the bottom of the list, in the "
                  "order they are in now.")
    MOVE_TIP = ("Move the ticked results into another file's group, at its "
                "end - exactly as Move to on the selection bar does.")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FindBox")
        self.setFrameShape(QFrame.NoFrame)
        # NOT PART OF THE PAGE. It used to be the page's own colour at 96
        # per cent over the page, with a hairline round it, which is almost the
        # definition of not being told apart: a panel and the thing behind it
        # were the same grey and the eye had one faint line to go on. It keeps
        # its translucency - the page still shows through - but it is white
        # over a grey page, it is carried on a shadow, and it is headed by the
        # same navy band the top of the window uses, so there is no moment
        # where a result reads as a clipping on the page.
        self.setStyleSheet(
            "#FindBox { background: rgba(255, 255, 255, 0.97);"
            " border: 1px solid rgba(18, 42, 82, 0.34);"
            " border-radius: 14px; }"
            f"#FindHead {{ background: {theme.NAVY};"
            " border-top-left-radius: 13px; border-top-right-radius: 13px; }}")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(15, 23, 42, 105))
        self.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.band = QFrame()
        self.band.setObjectName("FindHead")
        head = QHBoxLayout(self.band)
        head.setContentsMargins(12, 8, 10, 8)
        head.setSpacing(8)
        self.said = QLabel()
        self.said.setStyleSheet(
            f"color: {theme.CROWN_SUB}; font-size: 11px; font-weight: 700;"
            " background: transparent; border: none;")
        head.addWidget(self.said, 1)

        self.all_btn = QPushButton("Select all")
        self.all_btn.setCursor(Qt.PointingHandCursor)
        self.all_btn.setToolTip("Tick every one of these results.")
        self.all_btn.clicked.connect(self._tick_all)
        head.addWidget(self.all_btn)

        # SHIFT TO, on the results themselves. Searching for the stories that
        # belong in a second newspad and then having to find them again in the
        # list to send them is the long way round; from here the ones that came
        # up ARE the selection.
        self.shift_btn = QPushButton("Shift to: ▾")
        self.shift_btn.setCursor(Qt.PointingHandCursor)
        self.shift_btn.setToolTip(
            "Put a copy of the ticked results into another newspad. They stay "
            "here as well.")
        self.shift_menu = QMenu(self)
        self.shift_menu.aboutToShow.connect(self._fill_shift)
        self.shift_btn.setMenu(self.shift_menu)

        # EVERYTHING ELSE THE SELECTION BAR DOES TO SEVERAL CLIPPINGS, done to
        # the ticked results: a priority for all of them at once, the top or
        # the bottom of the list, and another file's group. The search is how
        # the twelve stories about one subject are found; having found them,
        # doing something to them should not mean finding them all again in
        # a list of a hundred and sixty.
        self.priority_btn = QPushButton("Priority ▾")
        self.priority_btn.setToolTip(self.PRIORITY_TIP)
        self.priority_menu = QMenu(self)
        self.priority_menu.aboutToShow.connect(self._fill_priority)
        self.priority_btn.setMenu(self.priority_menu)
        self.top_btn = QPushButton("Top")
        self.top_btn.setToolTip(self.TOP_TIP)
        self.top_btn.clicked.connect(
            lambda: self.arrangeWanted.emit(self.chosen(), "top"))
        self.bottom_btn = QPushButton("Bottom")
        self.bottom_btn.setToolTip(self.BOTTOM_TIP)
        self.bottom_btn.clicked.connect(
            lambda: self.arrangeWanted.emit(self.chosen(), "bottom"))
        self.move_btn = QPushButton("Move to ▾")
        self.move_btn.setToolTip(self.MOVE_TIP)
        self.move_menu = QMenu(self)
        self.move_menu.setToolTipsVisible(True)
        self.move_menu.aboutToShow.connect(
            lambda: self.moveMenuOpening.emit(self.move_menu, self.chosen()))
        self.move_btn.setMenu(self.move_menu)
        for button in (self.priority_btn, self.top_btn, self.bottom_btn,
                       self.move_btn, self.shift_btn):
            head.addWidget(button)
        for button in (self.all_btn, self.priority_btn, self.top_btn,
                       self.bottom_btn, self.move_btn, self.shift_btn):
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                f"QPushButton {{ background: {theme.CROWN_RAISED};"
                f" border: 1px solid {theme.SLATE_LINE};"
                f" border-radius: 9px; padding: 3px 10px; font-size: 11px;"
                f" font-weight: 700; color: #FFFFFF; }}"
                f"QPushButton:hover {{ background: {theme.CROWN_HOVER};"
                " border-color: #7C93C0; }"
                "QPushButton:disabled { color: #8CA0C2;"
                " background: rgba(255,255,255,0.06); border-color: #3C5280; }"
                "QPushButton::menu-indicator { image: none; width: 0; }")
        outer.addWidget(self.band)

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.NoFrame)
        self.area.setStyleSheet("background: transparent;")
        self.holder = QWidget()
        self.holder.setStyleSheet("background: transparent;")
        self.column = QVBoxLayout(self.holder)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(5)
        self.column.addStretch(1)
        self.area.setWidget(self.holder)
        body = QVBoxLayout()
        body.setContentsMargins(10, 9, 10, 10)
        body.addWidget(self.area, 1)
        outer.addLayout(body, 1)
        #: Whether Priority, Top, Bottom and Move to can act here. They act on
        #: a LIST - the press report's, or a category of the board opened out
        #: as one - and over the board's four columns of cards there is none.
        self.list_actions = True
        self.hide()

    #: Every result on show, in order.
    def results(self) -> list:
        return [self.column.itemAt(i).widget()
                for i in range(self.column.count())
                if isinstance(self.column.itemAt(i).widget(), Result)]

    def chosen(self) -> list:
        """The row ids that have been ticked."""
        return [r.row_id for r in self.results() if r.tick.isChecked()]

    def _tick_all(self) -> None:
        results = self.results()
        wanted = not all(r.tick.isChecked() for r in results) if results else False
        for result in results:
            result.tick.setChecked(wanted)

    def _fill_priority(self) -> None:
        """The five levels and a way back, each with the colour its badge has."""
        from PySide6.QtGui import QIcon, QPainter

        self.priority_menu.clear()
        many = len(self.chosen())
        self.priority_menu.addAction(
            f"Priority for {many} clipping{'s' if many != 1 else ''}:"
        ).setEnabled(False)
        colours = list(getattr(theme, "PRIORITY_COLOURS", ()) or ())
        for level in range(1, 6):
            dot = QPixmap(12, 12)
            dot.fill(Qt.transparent)
            if level - 1 < len(colours):
                painter = QPainter(dot)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(colours[level - 1]))
                painter.drawEllipse(1, 1, 10, 10)
                painter.end()
            action = self.priority_menu.addAction(QIcon(dot), f"Priority {level}")
            action.triggered.connect(
                lambda _c=False, n=level: self.priorityWanted.emit(
                    self.chosen(), n))
        self.priority_menu.addSeparator()
        self.priority_menu.addAction("Clear priority").triggered.connect(
            lambda _c=False: self.priorityWanted.emit(self.chosen(), 0))

    #: Said on the four buttons while there is no list for them to act on.
    NO_LIST = ("Open a category as a list first - over the four columns of "
               "cards there is no list order to change.")

    def _count_changed(self) -> None:
        many = len(self.chosen())
        self.shift_btn.setEnabled(bool(many))
        for button, tip in ((self.priority_btn, self.PRIORITY_TIP),
                            (self.top_btn, self.TOP_TIP),
                            (self.bottom_btn, self.BOTTOM_TIP),
                            (self.move_btn, self.MOVE_TIP)):
            button.setEnabled(bool(many) and self.list_actions)
            button.setToolTip(tip if self.list_actions else self.NO_LIST)
        self.all_btn.setText("Select all" if not self.results()
                             or not all(r.tick.isChecked()
                                        for r in self.results())
                             else "Select none")
        self.shift_btn.setText(
            f"Shift {many} to: ▾" if many else "Shift to: ▾")

    def _fill_shift(self) -> None:
        from ..core import newspads

        self.shift_menu.clear()
        here = newspads.active()
        for number in range(1, newspads.COUNT + 1):
            found = newspads.summary(number)
            words = newspads.describe(number, *(found or ()))
            if number == here:
                action = self.shift_menu.addAction(f"{words}   (this one)")
                action.setEnabled(False)
                continue
            action = self.shift_menu.addAction(words)
            action.triggered.connect(
                lambda _c=False, n=number: self.shiftWanted.emit(self.chosen(), n))

    def show_results(self, found: list, numbers, places=None,
                     list_actions: bool = True, wanted: str = "",
                     total: Optional[int] = None) -> None:
        """``places``: row id -> a word on where it is, or None for none.
        ``found`` is search_detail's (row, which, says, guessed) - or the
        older (row, which, says); ``total`` how many matched in all."""
        self.list_actions = bool(list_actions)
        while self.column.count() > 1:
            item = self.column.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        total = len(found) if total is None else max(int(total), len(found))
        if not found:
            self.said.setText("Nothing matches that.")
        else:
            self.said.setText(
                f"{total} clipping{'s' if total != 1 else ''}"
                + (f", showing {len(found)}" if total > len(found) else ""))
        for one in found:
            row, which, says = one[0], one[1], one[2]
            guessed = bool(one[3]) if len(one) > 3 else False
            where = places(row.id) if places is not None else ""
            result = Result(numbers(row.id), row, which, says, self.holder,
                            where=where or "", wanted=wanted, guessed=guessed)
            result.picked.connect(self.picked.emit)
            result.ticked.connect(self._count_changed)
            self.column.insertWidget(self.column.count() - 1, result)
        self._count_changed()
        self.show()
        self.raise_()


#: What the operators do, for the "i". Written for somebody who has the box
#: in front of them and wants to do something cleverer than one word.
HELP = """
<p style="margin:0 0 10px 0">Type a word or two and it looks in the headline
that prints, the headline read off the picture, the newspaper, the edition and
the link. <b>Two letters are enough.</b> It only finds &mdash; nothing is
hidden, reordered, ticked or unticked.</p>

<p style="margin:0 0 4px 0"><b>Asking for more than one thing</b></p>
<table cellpadding="3" style="margin:0 0 10px 0">
<tr><td><code>hydrogen train</code></td>
    <td>&mdash; both words, in any order, anywhere on the clipping</td></tr>
<tr><td><code>hydrogen OR train</code></td>
    <td>&mdash; either one. <b>OR must be capitals</b>, so a headline with the
        word "or" in it is still just a word</td></tr>
<tr><td><code>"vande bharat"</code></td>
    <td>&mdash; those words, in that order, as written</td></tr>
<tr><td><code>hydrogen -cricket</code></td>
    <td>&mdash; has the first, does not have the second</td></tr>
</table>

<p style="margin:0 0 4px 0"><b>Asking one field only</b></p>
<table cellpadding="3" style="margin:0 0 10px 0">
<tr><td><code>paper:jagran</code></td><td>&mdash; the newspaper</td></tr>
<tr><td><code>headline:hydrogen</code></td>
    <td>&mdash; the OCR headline, read off the picture</td></tr>
<tr><td><code>label:jagran</code></td>
    <td>&mdash; the label: the newspaper's name that prints above it</td></tr>
<tr><td><code>edition:delhi</code></td><td>&mdash; the edition or city</td></tr>
<tr><td><code>link:indianexpress</code></td><td>&mdash; the web address</td></tr>
</table>

<p style="margin:0 0 10px 0"><b>Putting them together.</b> Words next to each
other are joined by "and", and <code>OR</code> splits the whole query into
sides &mdash; so <code>vande bharat OR paper:jagran</code> finds the clippings
that say both those words, plus everything from that paper.</p>

<p style="margin:0 0 10px 0"><b>A misread headline still turns up.</b> A
reading taken off a picture is never perfect, so anything four letters or
longer is also matched forgivingly &mdash; <code>hydrogen</code> finds
<code>hydr0gen</code>. A quoted phrase is not: that is asked for exactly.</p>

<p style="margin:0 0 10px 0"><b>And its related words.</b> An English word
finds its other forms: <code>derailment</code> finds <i>derailed</i>,
<code>electrification</code> finds <i>electrified</i>, and a name spelt a
letter apart &mdash; <code>jagaran</code>, <i>Jagran</i>. Hindi finds its
forms already: <code>यात्री</code> finds <i>यात्रियों</i>. A result found only
this way says <i>close match</i>.</p>

<p style="margin:0">The words found are <b>marked in yellow</b>, and under
each result is where it came from: its division, and on the board its
column.</p>
"""


class FindHelp(QDialog):
    """What the search box understands. Read-only."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Finding a clipping — what you can type")
        self.setModal(True)
        self.resize(580, 560)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(12)
        words = QLabel(HELP)
        words.setWordWrap(True)
        words.setTextFormat(Qt.RichText)
        words.setAlignment(Qt.AlignTop)
        words.setStyleSheet(
            f"color: {theme.INK}; font-size: 12px; background: transparent;"
            " border: none;")
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setWidget(words)
        area.setStyleSheet("background: transparent;")
        outer.addWidget(area, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        outer.addWidget(buttons)


class FindBar(QWidget):
    """The field itself, and the box of results under it."""

    #: A clipping was picked out of the results (a row id).
    picked = Signal(int)
    #: (row ids, newspad number) - copies of the ticked results, sent on.
    shiftWanted = Signal(list, int)
    #: The rest of what can be done to the ticked results - see FindBox.
    priorityWanted = Signal(list, int)
    arrangeWanted = Signal(list, str)
    moveMenuOpening = Signal(object, list)
    #: The results were put away - the field emptied, or down to one letter.
    #: The preview stops walking them then: there are none on screen.
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FindBar")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.field = QLineEdit()
        self.field.setPlaceholderText(
            "Find a clipping — hydrogen train, \"vande bharat\", a OR b, -cricket, paper:jagran")
        self.field.setClearButtonEnabled(True)
        self.field.setObjectName("FindField")
        self.field.setToolTip(
            "Searches the OCR headline, the label, the newspaper and "
            "the link.\n\n"
            "hydrogen train \u2014 both words\n"
            "hydrogen OR train \u2014 either one\n"
            '"vande bharat" \u2014 those words in that order\n'
            "-cricket \u2014 leave those out\n"
            "paper:jagran \u2014 only in the newspaper "
            "(also headline:, label:, link:, edition:)\n\n"
            "Nothing is hidden or reordered: this only finds.")
        row.addWidget(self.field, 1)

        self.help_btn = QToolButton()
        self.help_btn.setText("i")
        self.help_btn.setFixedSize(26, 26)
        self.help_btn.setCursor(Qt.PointingHandCursor)
        self.help_btn.setToolTip(
            "What you can type here: and, OR, \"a phrase\", -leave out, "
            "paper: and the rest.")
        self.help_btn.setStyleSheet(
            f"QToolButton {{ background: {theme.SURFACE};"
            f" border: 1px solid {theme.HAIRLINE_STRONG}; border-radius: 13px;"
            f" color: {theme.MUTED}; font-size: 12px; font-weight: 800;"
            " font-style: italic; padding: 0; }"
            f"QToolButton:hover {{ border-color: {theme.NAVY};"
            f" color: {theme.NAVY}; }}")
        self.help_btn.clicked.connect(lambda: FindHelp(self).exec())
        row.addWidget(self.help_btn, 0)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(AFTER_TYPING_MS)
        self._timer.timeout.connect(self._look)
        self.field.textChanged.connect(self._typed)
        self.field.returnPressed.connect(self._look)

        # WHAT WAS LOOKED FOR LATELY, offered on a press in an empty field.
        # The same search is run over and over across a morning - one story
        # chased through four divisions' files - and typing it again each time
        # is what is being saved.
        #
        # A completer rather than a dropped-down menu, and driven by hand
        # rather than attached to the field: a menu takes the keyboard while
        # it is up, so a press followed straight away by typing - which is
        # what anybody does - would lose the first letters into the menu. A
        # completer's popup leaves the keys with the field. Driven by hand
        # because attached it would also pop up WHILE typing, over the results
        # panel, which is two floating things at once over the same spot.
        self._recent_list = QStandardItemModel(self)
        self._recent = QCompleter(self._recent_list, self)
        self._recent.setWidget(self.field)
        self._recent.setCaseSensitivity(Qt.CaseInsensitive)
        self._recent.activated.connect(self._use_recent)
        offer = self._recent.popup()
        offer.setStyleSheet(
            f"QAbstractItemView {{ background: {theme.SURFACE};"
            f" border: 1px solid {theme.HAIRLINE_STRONG}; border-radius: 10px;"
            f" padding: {OFFER_PAD}px; outline: none; font-size: 12.5px;"
            f" color: {theme.NAVY}; }}"
            "QAbstractItemView::item { padding: 7px 9px; border-radius: 7px; }"
            f"QAbstractItemView::item:selected {{ background: #E8F0FE;"
            f" color: {theme.NAVY}; }}")
        offer.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.field.installEventFilter(self)
        #: Kept only while the query is worth keeping - see _look.
        self._remembered = ""

        self.box = None
        self._rows = lambda: []
        self._numbers = lambda _id: 0
        self._places = None
        self._list_actions = lambda: True

    def serve(self, rows, numbers, places=None, list_actions=None) -> None:
        """Where the clippings come from, and what each one is numbered.

        ``places`` names where a result is when its number alone does not;
        ``list_actions`` says whether the results' Priority, Top, Bottom and
        Move to have a list to act on. Both are asked at every search, since
        the answer changes with what is on screen.
        """
        self._rows = rows
        self._numbers = numbers
        self._places = places
        if list_actions is not None:
            self._list_actions = list_actions

    def result_ids(self) -> list:
        """The results on show, in their order - empty when the box is shut."""
        box = self.box
        if box is None or not box.isVisible():
            return []
        return [result.row_id for result in box.results()]

    def look_again(self) -> None:
        """Search again because what is on screen changed - the other
        interface, another division, a category opened or closed. Only while
        results are up: a shut box stays shut."""
        box = self.box
        if box is not None and box.isVisible():
            self._look()

    def _ensure_box(self):
        if self.box is None:
            top = self.window()
            self.box = FindBox(top)
            self.box.picked.connect(self._chose)
            self.box.shiftWanted.connect(self.shiftWanted.emit)
            self.box.priorityWanted.connect(self.priorityWanted.emit)
            self.box.arrangeWanted.connect(self.arrangeWanted.emit)
            self.box.moveMenuOpening.connect(self.moveMenuOpening.emit)
            top.installEventFilter(self)
        return self.box

    def refresh(self) -> None:
        """Look again, keeping what was ticked ticked.

        Called after something was done to the results: they are the same
        clippings, but moved, so every number on the panel is out of date.
        """
        box = self.box
        if box is None or not box.isVisible():
            return
        ticked = set(box.chosen())
        self._look()
        for result in box.results():
            if result.row_id in ticked:
                result.tick.setChecked(True)

    def _chose(self, row_id: int) -> None:
        # THE BOX STAYS OPEN, and so does what was typed. Looking at one result
        # is almost never the end of it - the next thing is the next result -
        # and closing the box meant typing the words again every time.
        self.picked.emit(row_id)

    def close_box(self) -> None:
        if self.box is not None:
            was = self.box.isVisible()
            self.box.hide()
            if was:
                self.closed.emit()

    def _look(self) -> None:
        wanted = self.field.text().strip()
        if len(fold(wanted).replace(" ", "")) < LEAST_LETTERS:
            self.close_box()
            return
        found, total = search_detail(self._rows(), wanted)
        box = self._ensure_box()
        try:
            acts = bool(self._list_actions())
        except Exception:  # noqa: BLE001 - a question, never a crash
            acts = True
        box.show_results(found, self._numbers, self._places, acts,
                         wanted=wanted, total=total)
        self._place()
        # Remembered only when it found something. A search that matched
        # nothing is not worth offering back, and half a word typed on the way
        # to a whole one would otherwise fill the list.
        if found and wanted != self._remembered:
            self._remembered = wanted
            remember(wanted)

    def offer_recent(self) -> None:
        """What was looked for lately, under the field."""
        kept = recent()
        if not kept or self.field.text().strip():
            return
        self._recent_list.clear()
        for words in kept:
            self._recent_list.appendRow(QStandardItem(words))
        clear = QStandardItem(CLEAR_ROW)
        # Red and bold, not a tinted band: a background set on the row itself
        # is ignored the moment the list carries a stylesheet, and this list
        # does.
        clear.setForeground(QColor(theme.RED))
        weight = clear.font()
        weight.setBold(True)
        clear.setFont(weight)
        clear.setToolTip("Forget every search remembered here.")
        self._recent_list.appendRow(clear)
        self._recent.setCompletionPrefix("")
        self._recent.complete()
        # SIZED HERE. A completer measures its popup from the rows alone and
        # knows nothing of the padding the stylesheet puts round them, so it
        # comes up a few pixels short and hangs a scrollbar beside four items.
        offer = self._recent.popup()
        row = offer.sizeHintForRow(0)
        if row > 0:
            offer.setFixedHeight(row * self._recent_list.rowCount()
                                 + 2 * OFFER_PAD + 2 * offer.frameWidth())

    def hide_recent(self) -> None:
        popup = self._recent.popup()
        if popup is not None and popup.isVisible():
            popup.hide()

    def _typed(self, _text: str = "") -> None:
        # Typing puts the offer away: from the first letter the field is
        # searching, and the results belong under it.
        self.hide_recent()
        self._timer.start()

    def _use_recent(self, words: str) -> None:
        self.hide_recent()
        if words == CLEAR_ROW:
            self._forget_recent()
            return
        self.field.setText(words)
        self._look()

    def _forget_recent(self) -> None:
        self._recent_list.clear()
        try:
            from .export_dialog import load_settings, save_settings

            save_settings({**load_settings(), RECENT_KEY: []})
        except Exception:  # noqa: BLE001
            pass

    def _place(self) -> None:
        """Against the field, as wide as it, and always inside the window.

        Under the field while there is room for it there, and above the field
        when there is not - which is what happens once the page has been
        scrolled far enough to carry the field towards the foot. Pinned at a
        floor and allowed to overflow, it hung off the bottom of the window
        with its last results out of reach.
        """
        if self.box is None or not self.box.isVisible():
            return
        top = self.window()
        width = max(320, self.field.width())
        wanted = 74 + 62 * max(1, self.box.column.count() - 1)

        below = self.field.mapTo(top, QPoint(0, self.field.height() + 6))
        room_below = top.height() - below.y() - 14
        # Always downwards. The field is pinned above the page now, so there
        # is always room under it - and it never moves, so the panel never has
        # to chase it or flip over it, which is what read as a glitch.
        tall = max(80, min(room_below, wanted))
        self.box.setGeometry(below.x(), below.y(), width, tall)
        self.box.raise_()

    def follow(self, scroller) -> None:
        """Keep the panel under the field while the page scrolls.

        The field scrolls away with the page it sits on; the panel is a child
        of the WINDOW, so it does not move on its own and was left behind. It
        follows now - and because the room it is given is measured from wherever
        the field has got to, it grows taller as the field goes up the screen,
        which is exactly when more of it can be seen.
        """
        for bar in (scroller.verticalScrollBar(), scroller.horizontalScrollBar()):
            if bar is not None:
                bar.valueChanged.connect(lambda _v: self._place())

    def moveEvent(self, event):  # noqa: N802 - Qt name
        self._place()
        super().moveEvent(event)

    def resizeEvent(self, event):  # noqa: N802 - Qt name
        self._place()
        super().resizeEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.window() and event.type() in (
                QEvent.Resize, QEvent.Move):
            self._place()
        # Pressed while empty: offer what was searched for lately. Only on a
        # press, and only while empty, so it never gets in the way of typing.
        if (watched is self.field
                and event.type() == QEvent.MouseButtonPress
                and not self.field.text().strip()):
            QTimer.singleShot(0, self.offer_recent)
        # And a way to clear them, on the field's own right-click menu, where
        # the rest of what can be done to the field already is.
        if watched is self.field and event.type() == QEvent.ContextMenu:
            menu = self.field.createStandardContextMenu()
            menu.addSeparator()
            forget = menu.addAction("Forget recent searches")
            forget.setEnabled(bool(recent()))
            forget.triggered.connect(self._forget_recent)
            menu.exec(event.globalPos())
            menu.deleteLater()
            return True
        return super().eventFilter(watched, event)
