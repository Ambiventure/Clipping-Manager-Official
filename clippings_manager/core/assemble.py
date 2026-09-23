"""Turn a document-ordered stream of text and pictures into Clips.

Both extractors reduce their format to the same thing: a list of Events in reading
order. Word gives that order from the XML; a PDF gives it from the position of each
item on the page. Everything after that -- which section a clip belongs to, which
line is its caption, whether it looks like a logo rather than a clipping -- is the
same problem in both formats and lives here, once.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from . import glyphmap, ourfiles
from .models import Clip, CropRect, Section

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class ExtractionError(Exception):
    """Raised when a document cannot be read at all. Always names the file."""


# --------------------------------------------------------------------- events


@dataclass
class Event:
    """One item in reading order: a run of text, a picture, or a hyperlink."""

    kind: str                       # "text" | "image" | "link"
    text: str = ""
    ref: str = ""                   # where it came from, for the manifest
    data: Optional[bytes] = None    # image bytes, already resolved
    ext: str = ".png"
    width: int = 0
    height: int = 0
    crop: CropRect = field(default_factory=CropRect)
    is_vml: bool = False
    url: str = ""
    page: int = 0                   # 1-based page number, PDFs only
    furniture: bool = False         # section artwork, not a clipping
    furniture_note: str = ""        # and what it is, when we know (ourfiles)
    garbled: bool = False           # Hindi glyphtext could not read back


# --------------------------------------------------------------------- config

_config_cache: dict[str, dict] = {}


def load_config(path: Optional[Path] = None) -> dict:
    """Load divisions.json, cached. Falls back to the bundled copy."""
    path = Path(path) if path else CONFIG_DIR / "divisions.json"
    key = str(path)
    if key not in _config_cache:
        with open(path, encoding="utf-8") as handle:
            _config_cache[key] = json.load(handle)
    return _config_cache[key]


def detect_division(filename: str, config: Optional[dict] = None) -> Optional[str]:
    """Guess the division code from a filename.

    Alias matching is bounded and longest-first, so 'MB' does not fire inside
    'AMBALA' or 'UMB'.
    """
    config = config or load_config()
    stem = Path(filename).stem.upper()
    best: tuple[int, Optional[str]] = (0, None)
    for code, profile in config["divisions"].items():
        for alias in list(profile.get("filename_aliases", [])) + [code]:
            pattern = r"(?<![A-Z])%s(?![A-Z])" % re.escape(alias.upper())
            if re.search(pattern, stem) and len(alias) > best[0]:
                best = (len(alias), code)
    return best[1]


# ------------------------------------------------------------------- sections

_NUMBER_PREFIX = re.compile(r"^\s*\d+\s*[.)\-:]\s*")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def _normalise(text: str) -> str:
    text = _NUMBER_PREFIX.sub("", text)
    text = _PUNCT.sub(" ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def match_section(text: str, config: Optional[dict] = None) -> Optional[Section]:
    """Fuzzy-match a line against the known section headers.

    Real documents contain 'POSITIVE NEWS :-', '2. Nerutral News:-' (misspelled in
    the original) and 'Negative Nil', so exact comparison is not enough.
    """
    from rapidfuzz import fuzz

    config = config or load_config()
    settings = config["sections"]
    normalised = _normalise(text)
    if not normalised or len(normalised.split()) > 6:
        return None

    threshold = settings.get("fuzzy_threshold", 82)
    best_score, best_section = 0.0, None
    for name, aliases in settings["aliases"].items():
        for alias in aliases:
            score = fuzz.ratio(normalised, alias)
            if score > best_score:
                best_score, best_section = score, name
    if best_score >= threshold and best_section:
        return Section(best_section)
    return None


_URL_LIKE = re.compile(r'^(?:https?://|www\.)[^\s]+$', re.IGNORECASE)

#: The second line of a web address that wrapped: no spaces, and the marks an
#: address is made of - "measures-following-cag-report",
#: "across-stns/articleshow/134395717.cms". A caption has spaces, or none of
#: these marks.
_ADDRESS_TAIL = re.compile(r'^[^\s]{3,}$')
_ADDRESS_MARKS = re.compile(r'[-/._=?&%#~]')


def _mark_address_tails(events: list) -> int:
    """In one of our own PDFs, mark the second line of every wrapped address.

    The report prints a clipping's address under it, and a long one wraps onto
    a second line that is written as a text block of its own - so the joiner
    in extract_pdf, which works inside one block, never sees the two together.
    The tail then read as the next clipping's caption: "measures-following-
    cag-report The Times of India". Marked as furniture here, on the same page
    as the address it follows, it is neither a caption nor anything else.
    """
    marked = 0
    last_text = None
    for event in events:
        if event.kind == "link":
            continue
        if event.kind != "text":
            last_text = None
            continue
        words = (event.text or "").strip()
        if (last_text is not None and not event.furniture
                and getattr(event, "page", 0) == getattr(last_text, "page", 0)
                and (address_in(last_text.text) or last_text.furniture_note
                     == "the rest of a web address")
                and _ADDRESS_TAIL.match(words) and _ADDRESS_MARKS.search(words)
                and not looks_like_url(words)):
            event.furniture = True
            event.furniture_note = "the rest of a web address"
            marked += 1
        last_text = event
    return marked

# A line that BEGINS with an address, whatever follows it. PDF text extraction
# breaks a long link across two lines, and the caption walk joins a run of lines
# with a space - so what arrives is the address with its own tail stuck on the
# end. It is still an address, and what matters is that it is not read as a
# headline.
_SCHEME_START = re.compile(r'^(?:https?://|www\.)\S', re.IGNORECASE)

# The same thing written without the scheme, which is how people actually paste
# them: "abplive.com/news/india/x", "bit.ly/3xYz", "indianexpress.com". Word
# links these as hyperlinks and shows the bare text, so the text was read as a
# CAPTION and printed above the picture while the hyperlink behind it printed
# below - the same address twice on the page, once as a heading.
#
# Deliberately strict about what counts as a domain. It has to be one unbroken
# token, and it has to end in something that looks like a real top-level domain,
# so a caption is never mistaken for an address: "Dainik Bhaskar page no- 2
# Firozpur" has spaces, "M.B." has no plausible ending, and "Negative News:-Nil"
# has neither.
#
# The endings are listed rather than "any word after the last dot" on purpose.
# Newspaper names are full of dots, and a rule that accepted any ending would
# turn a masthead into a link. Word-like endings that really do exist as domains
# - .times, .post, .one, .page - are deliberately left out for the same reason:
# missing one costs a link somebody types by hand, and a false one costs a
# masthead silently deleted from the report.
_BARE_URL = re.compile(
    r'^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+'      # one or more labels
    r'(?:com|net|org|edu|gov|mil|int|info|biz|news|live|tv|in|co|uk|us|io|me|ly|be|app|site|online|press|media|today|world|asia|xyz|link|ai|dev|blog|tech|wiki|pro|shop|store|digital|social|video|network)'                                      # a plausible ending
    r'(?:[/?#][^\s]*)?$',                                # an optional path
    re.IGNORECASE)

# Any two-letter country ending - .au, .de, .fr - but only with a path after it.
# The path is what keeps "M.B." out: an address somebody pasted goes somewhere.
_COUNTRY_URL = re.compile(
    r'^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2}[/?#][^\s]*$',
    re.IGNORECASE)


# An address with a word in front of it: "Article Link: https://...". The
# sentiment report prints exactly that under every digital clipping, and when
# one of those reports is imported back into the standard interface the line has
# to be understood as an ADDRESS and not as a name. Read as a name it does two
# wrong things at once - it becomes the heading printed above the NEXT picture
# (the caption walk runs backwards and nothing stopped it), and the same address
# then prints again underneath as the link, so the page carries it twice.
#
# The label may be up to three short words and must end in a colon or a dash;
# what follows it has to pass the address test on its own, which is what keeps a
# real caption safe. "Punjab Kesari, Jalandhar - Page 3" has a label and a dash
# and is still a caption, because "Page 3" is not an address.
_LABELLED = re.compile(
    r'^[^\s:]{1,24}(?:\s+[^\s:]{1,24}){0,2}\s*[:\-\u2013\u2014]\s*(.+)$')

# Characters a PDF sprinkles through extracted text that are not really there:
# zero-width spaces and joiners, the byte-order mark, a soft hyphen. Left in,
# they break every match above and the address becomes a caption again.
_INVISIBLE = dict.fromkeys(
    map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)

# Decoration around an address: brackets, quotes, and the punctuation a sentence
# leaves on the end. Taken off the ends only - a full stop kept on the end of a
# link is a link that does not open.
_EDGES = " \t\r\n\u00a0\"'\u201c\u201d\u2018\u2019()[]{}<>\u00ab\u00bb,;:.!?"

# How much of a line an address has to account for before the line counts as an
# address rather than as a sentence that mentions one. "Amar Ujala,
# amarujala.com, Page 3" is a caption - the address is a third of it.
# "(https://long/address)" is an address: it is nearly all of it.
ADDRESS_SHARE = 0.60


def _tidy(text: str) -> str:
    return (text or "").translate(_INVISIBLE).replace("\u00a0", " ").strip()


def _ends_cleanly(token: str) -> str:
    """The address without the punctuation a sentence left on the end of it."""
    return token.strip().rstrip(".,;:!?'\"\u201d\u2019)]}>\u00bb")


def _is_address(token: str) -> bool:
    return bool(_URL_LIKE.match(token) or _BARE_URL.match(token)
                or _COUNTRY_URL.match(token))


def address_in(text: str) -> str:
    """The web address this line carries, or "" if it is not one.

    Answers for the whole line, not for part of it: a caption that happens to
    mention a site in the middle of a sentence is still a caption, and printing
    that as a link would lose the caption.

    A wrapped address gives back only its first piece. Rejoining the halves
    would mean guessing where the break fell, and a guessed link that goes to
    the wrong page is worse than a short one anybody can see is short - but the
    line is still recognised, which is what stops it becoming a headline.
    """
    line = _tidy(text)
    if not line:
        return ""

    # The whole line, once any brackets or quotes around it are taken off.
    bare = line.strip(_EDGES)
    if _is_address(bare):
        return _ends_cleanly(bare)

    # It begins with an address and has a tail: a link the extractor wrapped.
    if _SCHEME_START.match(line):
        return _ends_cleanly(line.split()[0])

    # A short label in front of it: "Article Link: https://...".
    labelled = _LABELLED.match(line)
    if labelled:
        rest = labelled.group(1).strip(_EDGES)
        if _is_address(rest):
            return _ends_cleanly(rest)
        if _SCHEME_START.match(rest):
            return _ends_cleanly(rest.split()[0])

    # An address with decoration around it, and not much else on the line.
    found = [piece for piece in
             (part.strip(_EDGES) for part in line.split()) if _is_address(piece)]
    if found:
        longest = max(found, key=len)
        if len(longest) >= len(line) * ADDRESS_SHARE:
            return _ends_cleanly(longest)
    return ""


def unreadable(text: str) -> bool:
    """Whether this is mojibake rather than words.

    Some PDFs embed their fonts as a subset with no character map, and then the
    text layer is not text at all - it is glyph numbers. "The Times of India,
    Delhi" extracts as "\x03 d\u015a\u011e\x03d\u0177..." and one real
    document does this on 161 of its 167 clippings.

    Left alone that becomes the headline and gets printed, which is worse than
    printing nothing: a clipping with no name is flagged amber in the review
    grid and gets typed in, while a clipping with a nonsense name looks done.

    A control character is the reliable tell - real text, in any script, has
    none. Devanagari is combining marks and letters, categories Mn, Mc and Lo,
    so it is never caught by this.
    """
    body = (text or "").strip()
    if not body:
        return False
    odd = sum(1 for ch in body
              if (ord(ch) < 32 and ch not in " \t\n\r")
              or unicodedata.category(ch) in ("Cc", "Cf", "Co", "Cn", "Cs"))
    return odd > 0 and odd / len(body) > 0.02


def _unread(text: str) -> bool:
    """Did this line come through as nothing anybody can read?

    Narrower than :func:`unreadable`, and deliberately so - this is what the
    warning counts, and a number told to the user has to be the number of
    things actually lost.

    Two kinds of line fail the readability test without being lost. A page of
    the affected document holds dozens of empty runs, which is how counting
    every failure once announced "578 captions" about a document with 146. And
    a wrapped web address arrives with a few glyph-space characters stuck on
    the end - the address itself read perfectly, out of the page's link
    annotation, which is stored as plain text - which is how the same count
    then said 20 about a document with 13.
    """
    if not unreadable(text):
        return False
    body = "".join(ch for ch in text
                   if unicodedata.category(ch) not in ("Cc", "Cf"))
    if not any(ch.isprintable() and not ch.isspace() and ord(ch) > 32
               for ch in body):
        return False                    # padding, and nothing else
    return glyphmap.readable(body) < glyphmap.MIN_READABLE


# The mark of the one import warning that is not a failure. The document read
# perfectly; some captions in it are glyph numbers rather than words, so those
# clippings arrive unnamed. That belongs on the status strip, not in a box to be
# dismissed on every single import of the same file.
#
# The message above is built out of this same phrase, so the two cannot drift
# apart and quietly turn the warning back into a blocking one.
NO_CHARMAP = "carry no character map"

# The same mark, for what the report's own record has to say about itself
# (core/reportrecord): a clipping it could not match, or a caption somebody
# edited after the report was made. Both are notes about a document that read
# perfectly well, and both would otherwise open the blocking box on every
# single import of the same file. Written once here and quoted into the
# messages themselves, so the two cannot drift apart.
FROM_RECORD = "the report's own record"

# And the same again for a burned report of ours that carries no record - the
# headline is inside the picture, so it is read back off the picture and the
# band taken away (core/reportrecord.recover_bands). Nothing is lost there
# either: the report read perfectly, and this is a note about names that were
# recovered rather than about anything that was not.
FROM_BAND = "read off the picture"


def is_advisory(warning: str) -> bool:
    """True when a warning is about names rather than about anything lost."""
    words = warning or ""
    return NO_CHARMAP in words or FROM_RECORD in words or FROM_BAND in words


#: What flag_junk calls a picture with no caption that sits above the first
#: captioned one. Named here because build_clips has to undo this one mark,
#: and only this one: in a report of ours a clipping whose printed caption we
#: could not READ has the same shape as a letterhead and is not one.
UNCAPTIONED_LETTERHEAD = ("no caption, and sits above the first captioned "
                          "clipping - probably a logo or letterhead")


def looks_like_url(text: str) -> bool:
    """Whether a relationship target is really a web address.

    Word turns some plain text into a hyperlink relationship of its own accord:
    a Moradabad heading reading "Negative News:-Nil" arrives as a link whose
    target is the literal string "News:-Nil". Attaching that to a clipping puts a
    nonsense link on the exported page, so anything that is not plausibly an
    address is dropped.
    """
    body = (text or '').strip()
    if _URL_LIKE.match(body):
        return True
    # A bare domain counts too, but only on its own: an address embedded in a
    # sentence is part of the sentence, and a caption that merely mentions a
    # site is still a caption.
    return bool(_BARE_URL.match(body))


def _ignore_patterns(config: dict) -> list[re.Pattern]:
    return [re.compile(p, re.I) for p in config.get("ignore_caption_patterns", [])]


# ------------------------------------------------------------------- assembly


#: What the program writes into every report it makes - the PDF's creator
#: and producer, the Word file's comments. A file that carries it is one of
#: ours coming back, and its pictures have all been clippings once already.
MADE_HERE = "Clippings Manager"


def made_here(*stamps) -> bool:
    """Whether any of these metadata strings is the program's own stamp."""
    return any(str(stamp or "").strip().startswith(MADE_HERE) for stamp in stamps)


def build_clips(
    events: list[Event],
    source_file: str,
    division: str,
    config: dict,
    warnings: Optional[list[str]] = None,
    own: bool = False,
    cover: Optional[bool] = None,
    known: Iterable[str] = (),
) -> list[Clip]:
    """Assemble Clips from an ordered event stream.

    ``own`` says the file was made by this program (see made_here): the
    size-and-shape rules that catch icons and rules in a division's document
    are not applied, because every picture in one of our reports was accepted
    as a clipping by the person who exported it.

    ``cover`` is what the report's own record says about whether it has one
    (core/reportrecord). None means nobody said, which is every division's
    document and every report made before the record existed, and the cover is
    then guessed off the page exactly as before.

    ``known`` is the sha1 of every picture that record names. It only ever
    stops a picture being called furniture, and it is empty for every file
    that carries no record of ours.
    """
    warnings = warnings if warnings is not None else []
    profile = config.get("divisions", {}).get(division, {})
    position = profile.get("caption_position", "before")
    ignores = _ignore_patterns(config)
    default_section = Section(config["sections"].get("default", "Neutral"))

    # One of our own reports coming back. Its cover, its page numbers and its
    # coverage summary are marked before a single line is read off it: they are
    # not captions, not section headers, and the cover picture is not a
    # clipping. See core/ourfiles for what went wrong without this.
    #
    # OURS BY ITS WORDS AND OURS BY ITS SHEETS ARE TWO DIFFERENT THINGS, so
    # there are two answers here. Nearly everything below needs only the first,
    # and ourfiles.looks_like_ours settles it from what is printed on the page:
    # a report made before the stamp existed, or one a tool has rewritten the
    # metadata of, is still ours.
    #
    # Three rules need the second. They read the SHEETS - a caption never
    # crosses a page edge, a caption is all of it or none of it, a link comes
    # only off the clipping's own page - and they hold because our exporter
    # lays out one clipping to a sheet, its caption above it and its address
    # below. Only the stamp says the sheets were laid out here. The
    # department's own 26.08 Word report prints "NUMBER OF CLIPPINGS:" on its
    # cover, which is all looks_like_ours asks for, but its pages FLOW: a
    # caption sits at the foot of the sheet before its picture and a link a
    # page earlier still. Measured against 2.0.39, those rules took five names
    # and one link off it - 89 captions down to 84 - and that is a division's
    # document reading differently, which is not allowed.
    stamped = bool(own)
    own = bool(own) or ourfiles.looks_like_ours(events)
    if own:
        ourfiles.mark_furniture(events, cover, known)
        # OUR CAPTION IS ALWAYS ABOVE ITS PICTURE, whatever the file is called.
        # The division profile comes from the file name, and a report of ours
        # is often named for a division - "Press Media Coverage Regarding Delhi
        # Division ..." - so it was read by Delhi's rules. Delhi's captions are
        # burned into the pictures, so every printed caption was ignored: 17 of
        # 17 came back with no name, from a report exported that same morning.
        # A name mentioning Ambala or Jammu ("after") would have handed each
        # caption to the picture above it. Our exporters print the caption
        # directly above the clipping, always, and that is how it is read.
        position = "before"
        _mark_address_tails(events)

    image_positions = [i for i, e in enumerate(events) if e.kind == "image"]
    last_image = image_positions[-1] if image_positions else -1

    # A HEADER WITH NOTHING UNDER IT IS NOT A HEADER.
    #
    # A section header announces the clippings that follow it, so a line that
    # matches one but has no picture after it anywhere is a line that happens
    # to use the word - "Digital  29" on a coverage summary page, a word in a
    # sign-off, a stray footer. Taking it for the document's first header made
    # every picture in the document "above the first section header", which is
    # how a whole report came in flagged. Costs nothing on a division's file,
    # where every header has its run underneath it.
    header_positions = [
        i for i, e in enumerate(events)
        if e.kind == "text" and not e.furniture
        and match_section(e.text, config) is not None
        and i < last_image
    ]
    headers = set(header_positions)

    # Which section is in force at each point in the stream, and the words the
    # document used to announce it. The words are kept as well as the enum
    # because the report is expected to read the way the source reads: the 360
    # Degree document prints "ELECTRONIC MEDIA" over its first electronic item,
    # and that is what has to come out the other end.
    sections: list[Section] = []
    headings: list[str] = []
    current = default_section
    current_heading = ""
    for index, event in enumerate(events):
        if index in headers:
            current = match_section(event.text, config)
            current_heading = " ".join(event.text.split())
        sections.append(current)
        headings.append(current_heading)

    first_header = header_positions[0] if header_positions else None

    def usable(event: Event) -> bool:
        if event.kind != "text" or not event.text.strip():
            return False
        # Our own cover, page numbers and summary page (ourfiles). None of it
        # is a caption, and the page number at the foot of the sheet above is
        # what used to arrive glued to the front of the next caption.
        if event.furniture:
            return False
        # Hindi in one of our own reports that glyphtext could not read back.
        # What get_text() gave for it is glyph numbers posing as letters -
        # "दैनə क जागरण दɘ Ėली" - which the name lookup happily took for
        # Dainik Jagran with an edition of "दɘ Ėली". Unnamed is better than
        # that. A division's document keeps its lines exactly as they were.
        if own and event.garbled:
            return False
        if match_section(event.text, config) is not None:
            return False
        # A printed web address belongs under the picture, not over it. It also
        # marks the end of the item above, so letting the caption walk run past
        # one is how 'Dainik Bhaskar' ended up captioned with the previous
        # page's Indian Express link.
        if address_in(event.text):
            return False
        if unreadable(event.text):
            return False
        return not any(rx.search(event.text) for rx in ignores)

    def refused(event: Event) -> bool:
        """Did this line fail usable() because it could not be READ?

        The caption walk also stops at a picture, a section heading, a printed
        address and the ignore list, and every one of those is the caption
        ending where it should. These two are words lost.
        """
        return bool(event.kind == "text"
                    and ((own and event.garbled) or unreadable(event.text)))

    #: Clippings whose caption walk a line we could not read cut short. In one
    #: of our own files they come in unnamed, and the advisory counts them.
    cut: set[int] = set()

    def caption_for(stream_index: int, ordinal: int) -> str:
        """Caption text for one image, taken only from its own window.

        A PDF often splits one caption across two text blocks -- Jammu writes
        'DAINIK JAGARAN' and 'JAMMU 9' separately -- so a contiguous run of usable
        lines is joined. The run stops at the first line that is a section header or
        document furniture, which keeps a title from being glued onto a caption.
        """
        if position == "burned":
            return ""
        parts: list[str] = []
        if position == "before":
            start = image_positions[ordinal - 1] + 1 if ordinal else 0
            here = getattr(events[stream_index], "page", 0)
            for i in range(stream_index - 1, start - 1, -1):
                if events[i].kind == "image":
                    break
                # Our own report prints a clipping's caption on the clipping's
                # own sheet. Whatever is on the sheet before belongs to the
                # clipping before - its address, a heading's page - and walking
                # back across the page edge is how an address's second line
                # became the next clipping's name. A Word file has no pages
                # (0 throughout), so this never stops a Word caption. Only for
                # a stamped file: see the note at the top of build_clips.
                if stamped and getattr(events[i], "page", 0) != here:
                    break
                if events[i].kind == "link":
                    continue
                if not usable(events[i]):
                    # A CAPTION OF OURS IS ALL OF IT OR NONE OF IT. The walk
                    # runs backwards, so what it has collected when a line
                    # stops it is the caption's TAIL - and the name is at the
                    # front. A caption that wrapped over three lines with the
                    # middle one refused arrived as "सफाई अभियान और यात्रियों
                    # को दी सुविधाएं आज सुबह", which apply_to_clip wrote into
                    # the newspaper and edition boxes: a plausible Hindi name
                    # that is not a name at all, while the advisory said the
                    # clipping had come in unnamed. Unnamed is what the plan
                    # asks for, so unnamed is what it gets. Only for a stamped
                    # file: see the note at the top of build_clips. The 26.08
                    # Word report's captions are glyph numbers on 161 of its
                    # 167 clippings, and it keeps every partial run it has
                    # always had.
                    if stamped and refused(events[i]):
                        cut.add(ordinal)
                        return ""
                    break
                parts.append(events[i].text.strip())
            parts.reverse()
        else:
            end = (
                image_positions[ordinal + 1]
                if ordinal + 1 < len(image_positions)
                else len(events)
            )
            for i in range(stream_index + 1, end):
                if events[i].kind == "image":
                    break
                if events[i].kind == "link":
                    continue
                if not usable(events[i]):
                    break
                parts.append(events[i].text.strip())
        return " ".join(p for p in parts if p)

    def link_for(stream_index: int, ordinal: int) -> str:
        end = (
            image_positions[ordinal + 1]
            if ordinal + 1 < len(image_positions)
            else len(events)
        )
        start = image_positions[ordinal - 1] + 1 if ordinal else 0
        forward = range(stream_index + 1, end)
        backward = range(start, stream_index)
        if stamped:
            # Our report prints a clipping's address UNDER it, on its own
            # sheet. Looking back as well handed the clipping after a linked
            # one that clipping's address: "Lucknow News" arrived carrying
            # sachkahoon.com from the page before. Only for a stamped file:
            # see the note at the top of build_clips.
            here = getattr(events[stream_index], "page", 0)
            forward = [i for i in forward
                       if getattr(events[i], "page", 0) == here]
            backward = []
        for i in list(forward) + list(backward):
            if events[i].kind == "link" and looks_like_url(events[i].url):
                return events[i].url
        # No annotation on this page: fall back to the address printed under the
        # picture. Read forward only - the one above belongs to the item above.
        for i in forward:
            if events[i].kind == "text":
                printed = address_in(events[i].text)
                if printed:
                    return printed
        return ""

    # Only the sections a document announces on the page itself carry their name
    # into the report. The six division documents head their runs too - "POSITIVE
    # NEWS :-" and the rest - and those have never been printed and must not
    # start being printed now.
    titled = {Section(name) for name in config["sections"].get("titled", [])}

    clips: list[Clip] = []
    opened: set = set()
    refused_names: list[Clip] = []      # the clippings `cut` cost a name
    for ordinal, stream_index in enumerate(image_positions):
        event = events[stream_index]
        if not event.data:
            continue
        clip = Clip(
            source_file=source_file,
            source_ref=event.ref,
            division=division,
            doc_index=ordinal,
            section=sections[stream_index],
            image_bytes=event.data,
            image_ext=event.ext,
            native_width=event.width,
            native_height=event.height,
            crop=event.crop or CropRect(),
            is_vml=event.is_vml,
            caption_raw=caption_for(stream_index, ordinal),
            url=(event.url if looks_like_url(event.url)
                 else link_for(stream_index, ordinal)),
            image_hash=hashlib.sha1(event.data).hexdigest(),
            sort_position=ordinal,
            title_in_image=(position == "burned"),
        )
        if ordinal in cut:
            refused_names.append(clip)
        # The first real clipping of a titled run opens it, and keeps the words.
        # In one of our own reports every heading on the page was put there by
        # the person who exported it, so all of them come back the same way and
        # print again if the report is rebuilt.
        section = sections[stream_index]
        if ((own or section in titled) and section not in opened
                and not event.furniture and headings[stream_index]):
            opened.add(section)
            clip.section_title = headings[stream_index]
        if event.furniture:
            clip.probable_junk = True
            clip.junk_reason = (event.furniture_note
                                or "decorative section artwork, not a clipping")
        elif (first_header is not None and stream_index < first_header
                and not own):
            # NEVER IN ONE OF OUR OWN REPORTS. The rule is for a division's
            # document, where the pictures above the first header are the
            # letterhead. In our own report every picture above it is a
            # clipping somebody accepted and exported, printed with no heading
            # because they asked for none - and the report prints its headings
            # only where they asked for them. Measured on the office's own
            # 18.09.2026 report: it prints ELECTRONIC MEDIA near the end, so
            # 239 of its 254 clippings came back flagged "probably not a
            # clipping", with their ticks cleared. The cover is still furniture
            # (ourfiles), which is what this rule was catching here.
            clip.probable_junk = True
            clip.junk_reason = "appears above the first section header"
        clips.append(clip)

    # Say so once, rather than leaving somebody to wonder why a whole file came
    # in unnamed. It is a fact about the document, not about this machine.
    #
    # What the number counts differs, because what is lost differs. In a
    # document that is not ours to the letter - a division's, or the 26.08
    # Word report that only looks like ours - a line that cannot be read is a
    # line, and this is the count it has always printed. In a report of ours
    # the thing lost is a NAME: MuPDF breaks "हिंदुस्तान" into two dict lines
    # of its own accord and a caption that wrapped runs to three, and all of
    # that is still one name. So ours counts the clippings whose caption a
    # line we could not read cut short - exactly the ones that came in unnamed
    # for this reason, which is what the words below promise. Hindi glyphtext
    # refused comes in through the same door (usable), and the cover and the
    # summary page never count, because nothing on them was going to be a name.
    if stamped:
        garbled = len(cut)
    else:
        garbled = 0
        previous = None
        for e in events:
            if e.kind == "link":
                continue
            if e.kind == "text":
                unread_line = own and e.garbled and not e.furniture
                if _unread(e.text) or (unread_line and not (
                        previous is not None and previous.garbled
                        and previous.page == e.page)):
                    garbled += 1
            previous = e
    if garbled and clips:
        warnings.append(
            f"{garbled} caption(s) could not be read: this document's fonts "
            f"{NO_CHARMAP}, so those names are stored as glyph numbers rather "
            f"than text. Those clippings came in unnamed and need naming by "
            f"hand - the rest were recovered."
        )

    flag_junk(clips, config, position, own=own,
              had_caption={id(clip) for clip in refused_names})

    return clips


def flag_junk(clips: list[Clip], config: dict, position: str = "before",
              own: bool = False, had_caption: Optional[set] = None) -> None:
    """Mark likely non-clippings. Never deletes: the user decides in the review grid.

    ``own``: the file is one of the program's own reports. The size and shape
    rules are for a division's document, where a tiny picture is a logo and a
    long thin one is a rule; in our own report a tiny picture is a phone
    screenshot of a headline and a long thin one is a website strip, both put
    there on purpose. Measured: re-importing a report flagged a 1200x140 strip
    and a 380x110 screenshot as "not a clipping". The repeat rule and the
    letterhead rule still apply - the cover picture is not a clipping.
    """
    rules = config.get("junk_filter", {})
    min_dim = rules.get("min_dimension_px", 120)
    small_max = rules.get("small_max_dimension_px", 400)
    max_aspect = rules.get("max_aspect_ratio", 8.0)

    seen: dict[str, Clip] = {}
    for clip in clips:
        width, height = clip.rendered_size()
        # Small in one direction only is normal: digital-news screenshots are wide
        # strips. Only something small in both directions is an icon or a spacer.
        if own:
            pass
        elif min(width, height) < min_dim and max(width, height) < small_max:
            clip.probable_junk = True
            clip.junk_reason = f"very small ({width}x{height} px)"
        elif height and max(width / height, height / width) > max_aspect:
            clip.probable_junk = True
            clip.junk_reason = f"extreme shape ({width}x{height} px)"

        first = seen.get(clip.image_hash)
        if first is not None:
            # The clipping itself, not a description of where it sat: the
            # review screen has to be able to put the two side by side, and it
            # can only do that if this points at something it can find.
            clip.duplicate_of = first.uid
            clip.probable_junk = True
            clip.junk_reason = clip.junk_reason or (
                f"identical to clipping {first.doc_index + 1} in the same file"
            )
        else:
            seen[clip.image_hash] = clip

    # Letterheads and logos sit above the first real caption. Jammu leads with the
    # Northern Railway logo and has no section headers at all, so the "before the
    # first section header" rule cannot catch it; this one can.
    if rules.get("flag_uncaptioned_before_first_caption", True) and position in (
        "before",
        "after",
    ):
        # A CLIPPING WHOSE CAPTION WE COULD NOT READ STILL HAD ONE, and it
        # counts as the first captioned clipping. ``had_caption`` holds those
        # (a Hindi name the glyph reader refused, say). Lifting the mark
        # afterwards was not enough: the boundary itself moved, so the next
        # genuinely uncaptioned clipping - which had been safely before it -
        # was flagged instead, and arrived with its tick cleared. One clipping
        # to the right is the same harm.
        had_caption = had_caption or set()
        first_captioned = next(
            (i for i, c in enumerate(clips)
             if c.caption_raw or id(c) in had_caption), None)
        if first_captioned:
            for clip in clips[:first_captioned]:
                if not clip.caption_raw and id(clip) not in had_caption:
                    clip.probable_junk = True
                    clip.junk_reason = clip.junk_reason or UNCAPTIONED_LETTERHEAD
