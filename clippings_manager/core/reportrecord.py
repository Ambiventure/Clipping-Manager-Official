"""The record a report carries inside it of the clippings it is made of.

WHY A REPORT HAS TO CARRY ONE
-----------------------------

A report is a page of pictures with a line of text over each one, and that line
is all the importer has to go on when the report comes back. It is not enough,
and three separate measurements say so:

*   Of the office's 18.09.2026 report, 88 of 254 sheets carry no text at all.
    Those clippings had no printed name when the report was made - no label, no
    newspaper, or "no title" ticked - so no reader of the page can ever get one
    back. What was lost was never on the page.
*   Hindi captions written by ``insert_htmlbox`` extract as glyph numbers,
    because MuPDF writes no character map for a glyph its substitution rules
    produced. "दैनिक जागरण दिल्ली" comes back as "दैनə क जागरण दɘ Ėली".
*   A burned report has no text on it whatsoever: the headline is inside the
    JPEG, and the picture grew a band to hold it.

None of that can be fixed by reading the page harder. So every report this
program writes from now on carries a small JSON record of what went into it,
and the importer reads that back. What the record holds is what the report was
MEANT to say - the name, the page number, the address, the heading - so a report
sent out and imported again comes back whole.

WHAT IS IN IT, AND WHAT IS DELIBERATELY NOT
-------------------------------------------

For the file: which build wrote it, what kind of report it is, its date, whether
it has a cover and a summary, and which categories printed as Nil. For each
clipping: where it sits, two ways of recognising its picture, and the fields a
person filled in.

Nothing that identifies a machine goes in. No file paths, no uid, no priority,
no notes. A report is forwarded outside the department, and whatever it carries
goes with it - so it carries what the report is meant to contain and no more.

Every string goes through the same word list the page does (core/wordlist).
Otherwise a word the department's list takes off the printed page would still be
sitting inside the file, which is the whole of what that feature exists to stop.

HOW A CLIPPING IS FOUND AGAIN
-----------------------------

By the sha1 of the exact bytes embedded in the file, first. Those bytes were
measured to survive the save, ``garbage=4``, the extract, a PDFium re-save and a
Word SaveAs unchanged, so it is an exact key rather than a guess. Where that
fails - somebody's tool re-encoded the pictures - the fingerprint
(core/imageops) still matches, and where that fails too the order does, but only
when the counts agree and nothing found so far is out of sequence. Anything left
over is simply not named from the record, and the import goes on as it always
did.

WHERE IT IS STORED
------------------

In a PDF, as an embedded file attachment; in a Word file, as a customXml part in
our own namespace. Both were measured to survive being re-saved by the tools the
office actually uses, including a page being deleted. Word renumbers customXml
parts, so the reader looks for the namespace rather than for a file name.

Nothing about the record is printed, and nothing about it changes how the report
looks.

WHEN THERE IS NO RECORD AND THE WORDS ARE IN THE PICTURE
--------------------------------------------------------

Every report written from now on carries one. The ones already sent do not, and
the worst of those is the burned dossier: its headline was drawn INTO the JPEG,
so the page holds no text at all and there is nothing whatever to read back.

There is, though - it is drawn on the picture, in this program's own ink, on a
white strip of a size this program chose. ``recover_bands`` finds that strip by
its geometry and its colour, reads the words off it, and takes it off again, so
the clipping comes back with its name. The strip, and only the strip: the crop
goes where the export drew the picture, not where the clipping's first ink
happens to fall, so a cutting keeps its own white margins instead of losing them
with the band. Measured over 250 real clippings burned by this build and read
back again: not one of them comes back short of where the export put it, and not
one loses a single inked pixel of itself. The one thing it cannot tell apart is
white at the SIDES of a cutting too narrow to hold the words, because there the
report's white and the cutting's are the same white - up to 33 px of it goes,
and all of it is white.

It runs only on a file of ours that has no record, and only on pictures that
carry our ink at an edge: measured, 10 bands of 10 found on the one burned
report that exists, in both its formats, and 0 found on the 1,611 pictures of
every other report and every sample document there is.

The crop matters as much as the name. It is put on before the list makes its
rows, because the crop is what the thumbnail shows and what the duplicate check
measures - and left on, every clipping of a paper would be compared band against
band.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zlib
from typing import Optional

from . import imageops, ocr, ourfiles, wordlist
from .assemble import FROM_BAND, FROM_RECORD
from .models import CropRect, Section

#: What the record says it is. Anything whose format is not exactly this is not
#: read, whatever else it may contain.
FORMAT = "clippings-manager/report-record"
VERSION = 1

#: What it is called inside a PDF, and what the attachments panel shows for it.
PDF_NAME = "clippings-record.json"
PDF_DESC = ("What this report is made of, so that importing it back into "
            "Clippings Manager brings the names with it. Nothing on the page "
            "depends on it.")

#: The Word part. The namespace is what the reader looks for: Word renumbers
#: customXml items on save - item7.xml came back as item2.xml - so a reader
#: that went by the file name would find nothing after the first Word save.
DOCX_NS = "https://clippings-manager.local/ns/report-record/1"
DOCX_ITEM_ID = "{9B3E4A61-0C77-4E2A-9E6A-3B4C1D5F7A20}"
_DOCX_ITEM = re.compile(r"customXml/item(\d+)\.xml$")

#: Nobody sends a two hundred megabyte record. A record larger than this is a
#: file that has been tampered with or a name collision, and is not read.
MAX_BYTES = 8 * 1024 * 1024

#: How far apart two fingerprints may be and still be the same picture
#: re-encoded. Deliberately far tighter than imageops.PICTURE_APART (28), which
#: answers a different question - whether two DIFFERENT scans are the same
#: cutting. Here the two are the same picture by construction, and only the
#: JPEG quality is in question: re-encoding this program's own exports at
#: quality 75 moves the print by 0 to 2 bits of 64. Six leaves room and is
#: nowhere near the distance between two different clippings.
RE_ENCODED = 6

#: And how much clearer the best match must be than the next one. Two entries
#: that a picture matches equally well are two entries it might belong to, and
#: putting the wrong name on a clipping is worse than leaving it unnamed.
CLEAR_BY = 4


# ------------------------------------------------------------------ the picture

#: Fingerprints already worked out, by the sha1 of the bytes they were taken
#: from. A morning is exported twice - the PDF to send and the Word file to
#: edit - and the burned dossier writes both from one burn, so the same picture
#: is measured up to four times for one click. Measured at about 15ms each,
#: that is four seconds of a two hundred clipping export spent working out the
#: same numbers again.
_PRINTS: dict[str, str] = {}


def picture_print(data: bytes, digest: str) -> str:
    """The fingerprint of these bytes, worked out once per export run."""
    found = _PRINTS.get(digest)
    if found is None:
        try:
            found = imageops.fingerprint(data)
        except Exception:  # noqa: BLE001 - a picture we cannot measure is not a fault
            found = ""
        if len(_PRINTS) > 4096:
            _PRINTS.clear()
        _PRINTS[digest] = found
    return found


# -------------------------------------------------------------- writing it


def entry(clip, data: bytes, *, n: int, sheet: int, slot: int = 0,
          printed: Optional[str] = None, band: Optional[dict] = None,
          sieve: Optional[wordlist.Sieve] = None) -> dict:
    """One clipping's record.

    ``clip`` is the clipping whose FIELDS are wanted and ``data`` the bytes
    actually embedded in the file. For a burned report the two come from
    different places: the picture is the composed one with the headline inside
    it, and the names are the original's, because build_burned.flatten clears
    them on the copies it hands the dossier.

    ``printed`` is what the page really carries above the picture - "" where
    nothing was printed, which is how the reader can tell a caption somebody
    edited afterwards from one that was never there.

    ``n``, ``sheet`` and ``slot`` say where the clipping was put - which one it
    is, which sheet it went on, and which half of a dossier sheet. Nothing
    reads them back: the pairing goes by the picture, not by the position. They
    are kept, and kept even when they are zero, because they are what makes the
    record readable by a person looking at a file that has gone wrong - "entry
    41, sheet 22, bottom half" is a place to look at - and because the later
    phases have to be able to say which sheet a clipping came off.

    Every other value that is empty is left out. On a 250 clipping report that
    is the difference between a 112KB record and a much smaller one, and it
    costs nothing to read: every reader below asks with a default.
    """
    digest = hashlib.sha1(data).hexdigest()
    clean = sieve.clean if sieve is not None else (lambda text: text)
    said = clip.printed_caption.strip() if printed is None else (printed or "")
    made = {
        "n": int(n),
        "sheet": int(sheet),
        "slot": int(slot),
        "sha1": digest,
        "phash": picture_print(data, digest),
        "printed": clean(said),
        "newspaper": clean((clip.newspaper or "").strip()),
        "edition": clean((clip.edition or "").strip()),
        "page": (clip.page or "").strip(),
        "label": clean((clip.label or "").strip()),
        "no_title": bool(clip.no_title),
        "title_in_image": bool(clip.title_in_image),
        # The address is never put through the word list. Two measured reasons
        # in core/wordlist: a real link contains ordinary words, and an edited
        # one goes nowhere.
        "url": (clip.url or "").strip(),
        "show_url_box": bool(clip.show_url_box),
        "section": getattr(clip.section, "value", str(clip.section or "")),
        "section_title": clean((clip.section_title or "").strip()),
        "division": (clip.division or "").strip(),
        "name_source": (clip.name_source or "").strip(),
        "name_confidence": round(float(clip.name_confidence or 0.0), 3),
    }
    if band:
        made["band"] = band
    return {key: value for key, value in made.items()
            if value or key in ("n", "sheet", "slot")}


class Record:
    """The record for one report, filled in as the report is written.

    Built inside the builder's own loop rather than from the list beforehand,
    so what it says is what was actually put on the page: a picture that failed
    to draw gets no entry, a category switched off contributes nothing, and a
    dossier pair notes which half of the sheet each clipping went on - written
    down for a person reading the file, not read back (see ``entry``).
    """

    def __init__(self, kind: str, file: str, report_date=None,
                 division: str = "", cover: bool = False,
                 summary: bool = False) -> None:
        self.kind = kind                  # press | dossier | dossier-burned
        self.file = file                  # pdf | docx
        self.date = report_date.isoformat() if report_date else ""
        self.division = division
        self.cover = bool(cover)
        self.summary = bool(summary)
        self.nil: list[str] = []          # categories that printed as Nil
        self.clips: list[dict] = []
        # Its own sieve, not the exporter's. The count the export reports is
        # the number of lines changed ON THE PAGE, and running the same strings
        # through that sieve again would double it.
        self.sieve = wordlist.Sieve()

    def add(self, clip, data: bytes, *, sheet: int, slot: int = 0,
            printed: Optional[str] = None, band: Optional[dict] = None) -> None:
        try:
            self.clips.append(entry(clip, data, n=len(self.clips) + 1,
                                    sheet=sheet, slot=slot, printed=printed,
                                    band=band, sieve=self.sieve))
        except Exception:  # noqa: BLE001 - a record is never worth a page
            pass

    def payload(self) -> dict:
        from .. import version

        return {
            "format": FORMAT,
            "version": VERSION,
            "app": version.describe(),
            "kind": self.kind,
            "file": self.file,
            "date": self.date,
            "division": self.division,
            "cover": self.cover,
            "summary": self.summary,
            "nil": list(self.nil),
            "clips": list(self.clips),
        }


def _payload(record) -> dict:
    return record.payload() if hasattr(record, "payload") else dict(record or {})


def dumps(record) -> bytes:
    """The record as the bytes that go into the file."""
    return json.dumps(_payload(record), ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def loads(raw: bytes) -> Optional[dict]:
    """The record back, or None when these bytes are not one of ours.

    Checked rather than trusted. The file may have been through anything on its
    way back, and a record that is not ours to the letter is no record at all.
    """
    if not raw or len(raw) > MAX_BYTES:
        return None
    try:
        found = json.loads(raw.decode("utf-8"))
    except Exception:  # noqa: BLE001 - not JSON, not ours
        return None
    if not isinstance(found, dict) or found.get("format") != FORMAT:
        return None
    try:
        if int(found.get("version") or 0) > VERSION:
            return None
    except (TypeError, ValueError):
        return None
    clips = found.get("clips")
    if not isinstance(clips, list):
        return None
    found["clips"] = [one for one in clips if isinstance(one, dict)]
    return found


# ------------------------------------------------------------------- the PDF


def attach_pdf(document, record, warnings: Optional[list] = None) -> bool:
    """Put the record into an open PDF, beside the metadata stamp.

    A record already in the document is TAKEN OUT and written again rather
    than updated in place. ``embfile_upd`` does not accept bytes on PyMuPDF
    1.28.2 - it hands them to its own Buffer and raises AttributeError - and
    it raised inside the catch below, so the save went ahead carrying the
    record that was there before. Every exporter opens a fresh document today,
    so nothing reached it; but the first one that does not would ship a report
    whose record names another morning's clippings, and every one of them
    would come back confidently named off it. Delete and add was measured to
    replace the contents, through a save and a reopen.

    Anything that goes wrong is said out loud in ``warnings``, because a
    report with no record in it looks exactly like a report that never had
    one, and the difference only shows up months later when it is imported.
    """
    try:
        data = dumps(record)
        if PDF_NAME in set(document.embfile_names()):
            document.embfile_del(PDF_NAME)
        document.embfile_add(PDF_NAME, data, filename=PDF_NAME, desc=PDF_DESC)
        return True
    except Exception as exc:  # noqa: BLE001 - a record is never worth the report
        if warnings is not None:
            warnings.append(_not_attached(exc))
        return False


def _not_attached(exc: Exception) -> str:
    """What the export says when the record could not go into the file."""
    return (f"This report could not be given {FROM_RECORD} "
            f"({type(exc).__name__}), so importing it back will read the "
            f"names off the page as it always did. Nothing on the page is "
            f"affected.")


def read_pdf(document) -> Optional[dict]:
    """The record out of an open PDF, or None."""
    try:
        if PDF_NAME not in set(document.embfile_names()):
            return None
        return loads(document.embfile_get(PDF_NAME))
    except Exception:  # noqa: BLE001 - any file may be damaged
        return None


# ------------------------------------------------------------------ the Word


def attach_docx(document, record, warnings: Optional[list] = None) -> bool:
    """Put the record into a python-docx document as a customXml part.

    Compressed and base64'd: Word rewrites this part's text when it saves, and
    a single line of base64 comes back byte for byte where pretty-printed XML
    does not.

    Says so in ``warnings`` when it cannot, for the reason attach_pdf does.
    """
    try:
        from docx.opc.constants import RELATIONSHIP_TYPE as RT
        from docx.opc.packuri import PackURI
        from docx.opc.part import Part

        package = document.part.package
        used = set()
        for part in package.iter_parts():
            found = _DOCX_ITEM.search(str(part.partname))
            if found:
                used.add(int(found.group(1)))
        number = next(n for n in range(1, 1000) if n not in used)

        body = base64.b64encode(zlib.compress(dumps(record), 9)).decode("ascii")
        item = (f"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
                f"<cm:record xmlns:cm='{DOCX_NS}' encoding='zlib+base64'"
                f" version='{VERSION}'>{body}</cm:record>").encode("utf-8")
        props = (f"<?xml version='1.0' encoding='UTF-8' standalone='no'?>"
                 f"<ds:datastoreItem ds:itemID='{DOCX_ITEM_ID}'"
                 f" xmlns:ds='http://schemas.openxmlformats.org/officeDocument"
                 f"/2006/customXml'><ds:schemaRefs>"
                 f"<ds:schemaRef ds:uri='{DOCX_NS}'/>"
                 f"</ds:schemaRefs></ds:datastoreItem>").encode("utf-8")

        part = Part(PackURI(f"/customXml/item{number}.xml"), "application/xml",
                    item, package)
        # Word will not keep a customXml item that has no properties part
        # beside it saying which schema it belongs to.
        beside = Part(
            PackURI(f"/customXml/itemProps{number}.xml"),
            "application/vnd.openxmlformats-officedocument."
            "customXmlProperties+xml", props, package)
        part.relate_to(beside, RT.CUSTOM_XML_PROPS)
        document.part.relate_to(part, RT.CUSTOM_XML)
        return True
    except Exception as exc:  # noqa: BLE001 - a record is never worth the report
        if warnings is not None:
            warnings.append(_not_attached(exc))
        return False


_DOCX_BODY = re.compile(r"<cm:record[^>]*>([A-Za-z0-9+/=\s]+)</cm:record>")


def read_docx(archive) -> Optional[dict]:
    """The record out of an open Word file, or None.

    Every customXml item is looked at, because Word renumbers them: the part
    written as item7.xml came back from a real Word 16 save as item2.xml.
    """
    try:
        names = [n for n in archive.namelist() if _DOCX_ITEM.fullmatch(n)]
    except Exception:  # noqa: BLE001
        return None
    for name in names:
        try:
            text = archive.read(name).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - one unreadable part is not the file
            continue
        if DOCX_NS not in text:
            continue
        found = _DOCX_BODY.search(text)
        if not found:
            continue
        try:
            raw = zlib.decompress(base64.b64decode(
                "".join(found.group(1).split())))
        except Exception:  # noqa: BLE001 - a part somebody has rewritten
            continue
        record = loads(raw)
        if record is not None:
            return record
    return None


# --------------------------------------------------------------- reading back


def sha1s(record) -> set:
    """Every picture the record names, by the bytes it was written from.

    The importer stacks two pictures that sit one directly above the other into
    one clipping, because a masthead strip and the article under it are one
    cutting stored as two images. Two pictures that are both in the record are
    two clippings this program put on the page on purpose, and a dossier pair's
    15pt gap is only 1pt over that rule.
    """
    return {str(one.get("sha1") or "")
            for one in (record or {}).get("clips") or [] if one.get("sha1")}


_INVISIBLE = dict.fromkeys(
    map(ord, "​‌‍⁠﻿­"), None)


def _plain(text: str) -> str:
    """A caption reduced to what it says, for comparing one with another."""
    body = (text or "").translate(_INVISIBLE).replace(" ", " ")
    return " ".join(body.split()).casefold()


#: Marks a PDF gives back faithfully that are not ASCII. A caption may well
#: have been typed with a dash or a curly quote in it.
_PDF_MARKS = set("‐‑‒–—‘’“”"
                 "…°₹£€©®½")


def _believable(caption: str, kind: str) -> bool:
    """Is what the page says about itself worth keeping over the record?

    In a Word file, always: Word stores the characters themselves, so a caption
    read back out of one is exactly what somebody typed.

    In a PDF it depends on the script. Our own exports write text through
    insert_htmlbox, and MuPDF names no character for a glyph the font's
    substitution rules produced - so "दैनिक जागरण दिल्ली" extracts as
    "दैनə क जागरण दɘ Ėली", and Calibri turns "Patiala" into "PaƟala". Those
    read as ordinary letters, so nothing about them says they are wrong, and
    taking them for an edited caption would put exactly the mojibake this
    record exists to replace back into the name box. Plain text cannot garble
    that way, so plain text is believed and nothing else is.
    """
    if kind != "pdf":
        return True
    return all(ch.isascii() or ch in _PDF_MARKS for ch in caption)


def _unlike(clip, one: dict) -> bool:
    """Are this picture and this entry demonstrably not the same clipping?

    Only asked by the order rule, which otherwise puts a name on a picture for
    no better reason than where it sits. Both fingerprints are already worked
    out by the time that rule runs, so the plainly wrong case costs nothing to
    refuse: measured, one picture of a six clipping report replaced with an
    unrelated cutting came back wearing the replaced clipping's name, silently.
    The bar is imageops.PICTURE_APART, the distance at which two scans stop
    being the same cutting - not the tight re-encoding bar above, because a
    picture the order rule is looking at has already failed that one and the
    order is all there is left to go on.
    """
    stored = str(one.get("phash") or "")
    if not stored:
        return False
    data = getattr(clip, "image_bytes", b"") or b""
    if not data:
        return False
    mine = picture_print(data, getattr(clip, "image_hash", "")
                         or hashlib.sha1(data).hexdigest())
    if not mine:
        return False
    return imageops.pictures_apart(mine, stored) > imageops.PICTURE_APART


def _fits(found: dict, index: int, position: int) -> bool:
    """Would this pairing leave everything found so far in sequence?"""
    for other, taken in found.items():
        if (other < index) != (taken < position):
            return False
    return True


def _in_sequence(found: dict) -> bool:
    taken = [found[index] for index in sorted(found)]
    return all(a < b for a, b in zip(taken, taken[1:]))


def _recorded(clip, entries) -> bool:
    """Whether the record holds this very picture: the same bytes, or a
    fingerprint as close as the pairing would accept."""
    digest = getattr(clip, "image_hash", "") or ""
    if digest and any(str(one.get("sha1") or "") == digest for one in entries):
        return True
    data = getattr(clip, "image_bytes", b"") or b""
    mine = picture_print(data, digest or hashlib.sha1(data).hexdigest())
    if not mine:
        return False
    for one in entries:
        theirs = str(one.get("phash") or "")
        if theirs and imageops.pictures_apart(mine, theirs) <= RE_ENCODED:
            return True
    return False


def _pairs(clips, entries) -> dict:
    """Which entry belongs to which clipping: clip position -> entry position."""
    found: dict[int, int] = {}
    used: set[int] = set()

    # 1. THE SAME BYTES. The pictures a report embeds come back out of it
    # unchanged - measured through save(garbage=4), extract_image, a PDFium
    # re-save and a Word SaveAs - so this is an answer rather than a guess.
    # Where one picture was used twice, the two entries are taken in order.
    queues: dict[str, list[int]] = {}
    for position, one in enumerate(entries):
        digest = str(one.get("sha1") or "")
        if digest:
            queues.setdefault(digest, []).append(position)
    for index, clip in enumerate(clips):
        waiting = queues.get(getattr(clip, "image_hash", "") or "")
        if waiting:
            position = waiting.pop(0)
            found[index] = position
            used.add(position)

    # 2. WHAT THE PICTURE LOOKS LIKE, for a file whose pictures were
    # re-encoded on the way. The best match has to be both close and clearly
    # closer than the next one, and it has to leave the pairing in sequence.
    spare_clips = [i for i in range(len(clips)) if i not in found]
    spare = [p for p in range(len(entries)) if p not in used]
    if spare_clips and spare:
        for index in spare_clips:
            data = getattr(clips[index], "image_bytes", b"") or b""
            mine = picture_print(
                data, getattr(clips[index], "image_hash", "")
                or hashlib.sha1(data).hexdigest())
            if not mine:
                continue
            best = second = RE_ENCODED + CLEAR_BY + 1
            choice = None
            for position in spare:
                if position in used:
                    continue
                gap = imageops.pictures_apart(
                    mine, str(entries[position].get("phash") or ""))
                if gap < 0:
                    continue
                if gap < best:
                    best, second, choice = gap, best, position
                elif gap < second:
                    second = gap
            if (choice is not None and best <= RE_ENCODED
                    and second - best >= CLEAR_BY
                    and _fits(found, index, choice)):
                found[index] = choice
                used.add(choice)

    # 3. BY ORDER, and only when there is nothing left to decide. Every
    # clipping still unspoken for against every entry still unspoken for, the
    # same number of each, and nothing found so far out of sequence. A pairing
    # the two fingerprints flatly contradict is left out of it - see _unlike -
    # and that clipping is simply counted among the ones the record could not
    # speak for.
    spare_clips = [i for i in range(len(clips)) if i not in found]
    spare = [p for p in range(len(entries)) if p not in used]
    if spare_clips and len(spare_clips) == len(spare) and _in_sequence(found):
        trial = dict(found)
        for index, position in zip(spare_clips, spare):
            if _unlike(clips[index], entries[position]):
                continue
            trial[index] = position
        if _in_sequence(trial):
            found = trial
    return found


def _crop_for(band: dict) -> Optional[CropRect]:
    """The crop that takes a burned report's band back off the picture.

    build_burned adds the headline ABOVE the clipping and the address below, so
    the picture grew and the original is still all there inside it. The box was
    recorded in the pixels of the composed JPEG; stored as fractions it survives
    the picture being re-encoded at another size.
    """
    try:
        x0, y0, x1, y1 = (float(v) for v in band["box"])
        width, height = float(band["w"]), float(band["h"])
    except Exception:  # noqa: BLE001 - a band we cannot read is no band
        return None
    if width <= 0 or height <= 0 or x1 <= x0 or y1 <= y0:
        return None
    if x0 < 0 or y0 < 0 or x1 > width or y1 > height:
        return None
    return CropRect(left=x0 / width, top=y0 / height,
                    right=(width - x1) / width, bottom=(height - y1) / height)


def _apply_one(clip, one: dict, kind: str = "") -> bool:
    """Put one entry onto its clipping. False when the page won the name."""
    band = one.get("band") or None
    if band:
        crop = _crop_for(band)
        if crop is not None:
            clip.crop = crop
        # The headline is no longer in the picture - it has just been cropped
        # off - so the clipping wants its name printed above it again.
        clip.title_in_image = False
    else:
        clip.title_in_image = bool(one.get("title_in_image"))

    said = one.get("section")
    if said:
        try:
            clip.section = Section(said)
        except ValueError:
            pass
    # Set either way, including back to nothing. The dossier heads each
    # category with its own words - "Positive News" - and the reader takes
    # those for the heading the clipping carries; the record knows the
    # clipping carried none, and a heading nobody chose should not follow it
    # into the next report.
    clip.section_title = str(one.get("section_title") or "")
    # Only where the page gave none. A burned dossier prints no address at all
    # - flatten clears it, because it is inside the picture - so the record is
    # the only way one comes back; but where the page does carry a link
    # annotation, that is the file as it stands and it wins.
    if one.get("url") and not (clip.url or "").strip():
        clip.url = str(one["url"])
    if one.get("show_url_box") and not (clip.url or "").strip():
        clip.show_url_box = True

    # THE PAGE WINS WHERE THE PAGE HAS BEEN CHANGED. A report is edited in Word
    # or in a PDF editor after it leaves here - a name corrected, a page number
    # put right - and the record still says what was exported. What somebody
    # typed last is what they meant.
    printed = str(one.get("printed") or "")
    caption = (clip.caption_raw or "").strip()
    if (caption and _plain(caption) != _plain(printed)
            and _believable(caption, kind)):
        return False

    clip.label = str(one.get("label") or "")
    clip.no_title = bool(one.get("no_title"))
    # A record with no newspaper in it is a clipping that never had one, and
    # claiming the name would stop profiles.apply_to_clip reading the caption
    # that IS on the page. Only a name actually stored is restored.
    if one.get("newspaper"):
        clip.newspaper = str(one["newspaper"])
        clip.edition = str(one.get("edition") or "")
        clip.page = str(one.get("page") or "")
        clip.name_source = "report"
        clip.name_confidence = float(one.get("name_confidence") or 0.0)
    return True


def apply(clips, record, warnings: Optional[list] = None) -> int:
    """Put a report's own record back onto the clippings read out of it.

    Returns how many clippings the record spoke for. Anything it cannot match
    is left exactly as the page read it, so a report whose record has been
    stripped imports precisely as it did before this existed.
    """
    warnings = warnings if warnings is not None else []
    entries = (record or {}).get("clips") or []
    if not entries or not clips:
        return 0

    # The cover is not a clipping and has no entry, so it is kept out of the
    # counting - otherwise a report of exactly as many clippings as entries
    # never matches by order.
    # A SHEET TAKEN FOR THE COVER THAT THE RECORD KNOWS IS A CLIPPING. Somebody
    # deletes page one before forwarding the report, and the first CLIPPING is
    # then the first sheet: one picture, no caption of its own, which is what a
    # baked cover looks like too (ourfiles). Its bytes settle it - unless the
    # same pass re-encoded the pictures, which is exactly what one compress-and-
    # extract-pages does, and then the bytes no longer match. So what the
    # picture LOOKS like is asked as well, on the record's own fingerprints and
    # the same bar the pairing uses. The cover has no entry, so it can never be
    # recognised this way and is never unmarked by accident; a clipping page
    # that was deleted leaves nothing behind to unmark either.
    for clip in [c for c in clips
                 if getattr(c, "junk_reason", "") == ourfiles.COVER_NOTE]:
        if _recorded(clip, entries):
            clip.probable_junk = False
            clip.junk_reason = ""
    candidates = [clip for clip in clips
                  if getattr(clip, "junk_reason", "") != ourfiles.COVER_NOTE]
    found = _pairs(candidates, entries)
    kind = str((record or {}).get("file") or "")

    named = edited = 0
    for index in sorted(found):
        try:
            if _apply_one(candidates[index], entries[found[index]], kind):
                named += 1
            else:
                edited += 1
        except Exception:  # noqa: BLE001 - one odd entry costs one clipping
            continue

    missed = len(candidates) - len(found)
    if missed:
        warnings.append(
            f"{missed} clipping(s) in this report could not be matched against "
            f"{FROM_RECORD}, so they were read off the page as usual and may "
            f"need naming by hand.")
    if edited:
        warnings.append(
            f"{edited} caption(s) have been changed since the report was made, "
            f"so what is printed on the page was kept rather than "
            f"{FROM_RECORD}.")
    return named


# ------------------------------------------- a burned report with no record


#: What export/build_burned draws a burned clipping with: 200 dots to the inch,
#: ten points of white at each edge, eight points between the words and the
#: picture, never a sheet narrower than 420 points, the headline in this ink and
#: the address in that one.
#:
#: Written out again rather than imported, because build_burned imports THIS
#: module to put a record into the report it is writing, and importing it back
#: would be a circle. test_burned checks the two sets against each other, so
#: they cannot drift apart without somebody being told.
BAND_DPI = 200
BAND_PAD = 10.0
BAND_GAP = 8.0
BAND_MIN_WIDTH = 420.0
BAND_INK = (0x1A, 0x1F, 0x2B)
BAND_LINK_INK = (0x0F, 0x5F, 0x76)

#: A row counts as white when its darkest pixel is at least this bright. Not
#: 255: the report is saved as a JPEG, and a JPEG leaves a speckle of 246 to 254
#: across a margin that was drawn pure white. Beside a line of type it rings
#: harder still - measured down to 243, two rows under a headline - which is why
#: the gap below wants only part of the white the export leaves.
BAND_WHITE = 245

#: How far the white margin may measure from the ten points build_burned leaves,
#: in pixels. Short of that the picture is somebody's cutting that happens to
#: begin pale; well past it the white belongs to the cutting itself, and this
#: takes off only the ten points that were ours.
BAND_PAD_SHORT = 8
BAND_PAD_LONG = 30

#: How much white has to follow the words before the picture begins, as a share
#: of the eight points build_burned leaves between them. Not the whole eight:
#: the JPEG rings a row or two dark at the edge of a line of type, and the gap
#: measured 24 px at its narrowest where eight points are 22.
#:
#: It cannot be MORE than those eight points either, however tempting. The gap
#: is eight points plus whatever slack the line box leaves under the last line,
#: which measured 27 px under a Latin headline with a descender in it and 99 px
#: under a Devanagari one; the white BETWEEN two wrapped lines of one headline
#: measured 1 px at 14 point and 20 px at 30 point. The two ranges meet as the
#: heading grows, which is why the band is taken as far as it goes rather than
#: stopped at the first gap wide enough - see _band_at.
BAND_GAP_SHARE = 0.8

#: How deep into the picture a band may reach, and how tall the words on it may
#: be. Measured on the burned dossier: the deepest band ends 150 px in and the
#: tallest run of words on one is 96 px. Anything taller than this is a column of
#: newsprint rather than a headline drawn on a strip - but the room left is not
#: large: a headline long enough to be set as three lines at thirty points came
#: out 382 px tall, and one at thirty-six would be refused and left as it is.
BAND_LOOK = 900
BAND_TEXT = 420

#: How much of the band has to be OUR ink. The first is every pixel that is not
#: white, measured against the line from white to the ink - which is where
#: anti-aliasing puts the edge of a stroke - and the second is the middle of the
#: strokes alone. Measured on the burned dossier the two come out at 1.00 and
#: 0.94.
#:
#: What the pair of them say is "dark type on white", and not much more than
#: that. The ink is only 17 units off neutral, so the line from white to it is
#: very nearly the grey axis itself and a bar of 45 admits any grey there is; a
#: newsprint stroke whose middle sits near (20, 20, 22) is 24 away from the ink,
#: inside the 30 the middles are held to. Of 1,611 pictures on documents that
#: are nobody's report of ours, three - a masthead line and two Hindi headlines,
#: each a line of type on white with white under it - passed both, at 1.00 and
#: 0.90, 0.66, 0.77. What refuses the other 1,608 is the geometry, not these.
BAND_ON_LINE = 45
BAND_INK_SHARE = 0.9
BAND_CORE_SHARE = 0.6

#: Which pixels are the middle of a stroke rather than its edge. The headline is
#: near black, so a pixel whose BRIGHTEST channel is dark is inside one; the
#: address is teal, whose green and blue channels are bright even in the middle
#: of a stroke, so there its darkest channel is what settles it.
BAND_CORE_DARK = 110
BAND_LINK_CORE_DARK = 140

#: How much of the ink's own colour cast those middles have to carry, as a share
#: of the ink's. Both inks this program draws with are blue-grey - #1A1F2B is 17
#: more blue than red, #0F5F76 is 103. Measured: the ten real headline bands on
#: the office's burned report carry 0.91 to 0.94 of it and its two address bands
#: 0.91, against -3, 0 and 0 on the three newspaper headlines that the shape of
#: the thing alone took for a band of ours.
#:
#: This is the LAST filter and not the line between the two, and it must not be
#: asked to do more than that. Read across every picture in every sample
#: document there is - 1,009 of 1,024 have middles dark enough to measure in
#: their top strip - the cast runs to 4.21 at its highest, 1.65 at the
#: ninety-ninth and 0.34 at the ninety-fifth, and 36 of the 1,009, which is
#: 3.6%, sit at or above this bar. So it takes the last three false bands off
#: the 1,611, and what keeps the other 1,608 out is the geometry: the white
#: margin at the edge, the white at the sides, and each line of the band being
#: judged on its own.
#:
#: It is the CAST rather than the distance from the ink because the distance
#: moves with the size of the type and this hardly does: the stroke middles of
#: one title burned at every size average 24 away from the ink at ten points and
#: 9 at thirty-six, where the cast over the same range goes 0.75, 0.79, 0.81,
#: 0.88, 0.91, 0.92, 0.94 - since at ten points most of a stroke is its own edge.
#:
#: Half, and no higher, even though 0.34 is the ninety-fifth of the corpus. The
#: smallest heading the panel offers is twelve points and measures 0.79, and
#: eight points - which only a settings file can ask for - measures 0.62. The
#: room above the bar is where those live.
BAND_CORE_CAST = 0.5

#: The ten points of white build_burned leaves at each SIDE of the words, in
#: points, less a little for the JPEG ringing beside a left-aligned line; and
#: how much ink may be found in them before this is not a band of ours.
#:
#: The words never reach the edge of the sheet, because they are set inside
#: those ten points. A clipping does, unless it was too narrow to hold the
#: words and had to be centred on a wider sheet. That is what stops the band
#: walking on down into a picture whose own top happens to be dark grey type on
#: white - which the colour tests alone would take for a headline.
BAND_SIDE = 10.0
BAND_SIDE_SLACK = 3
BAND_SIDE_INK = 0.01

#: A few rows either side of the words when the band is handed to the reader.
#: Tesseract reads a line set flush against the edge of its picture poorly.
BAND_MARGIN = 6


def _off_the_line(pixels, ink):
    """How far each pixel sits off the line from white to this ink.

    A drawn stroke is the ink in the middle and every mixture of the ink and the
    page at its edge, so the whole of it lies on that line; a photograph of
    newsprint does not.
    """
    import numpy as np

    white = np.array([255.0, 255.0, 255.0])
    along = ink - white
    where = np.clip(((pixels - white) @ along) / (along @ along), 0, 1)
    return np.linalg.norm(pixels - (white + where[:, None] * along), axis=1)


def _runs(flags) -> list:
    """[(value, start, stop)] for each unbroken run in a row-by-row flag array."""
    import numpy as np

    if not len(flags):
        return []
    edges = np.flatnonzero(flags[1:] != flags[:-1]) + 1
    bounds = [0, *(int(edge) for edge in edges), len(flags)]
    return [(bool(flags[at]), at, to) for at, to in zip(bounds, bounds[1:])]


def _our_type(block, ink) -> bool:
    """Is this ONE line of rows our own type on white?

    It is handed a single line of the band at a time, never the lines above it
    as well: judged together, a real headline of ours carries a line of the
    cutting through on the average of the two. _band_at says what that cost.

    Four things have to hold. On a real cutting it is usually the three colour
    tests that refuse the line: measured over 250 clippings burned by this
    build, only 68 of them put any ink in the 24-pixel strip the export leaves
    at either side, so for the other 182 the geometry says nothing at all and
    the colour is the whole answer. The side test is a backstop for the ones
    whose ink does run to the edge, not the rule that carries the work - and a
    cutting inset from its own edges whose first line is dark blue-grey type on
    white is not refused by any of the four. recover_bands is what covers that:
    it believes a band only when the file as a whole looks burned. The three
    that follow say
    the block is dark type on white in an ink near ours - every pixel that is
    not white on the line from white to this ink, which is where anti-aliasing
    puts the edge of a stroke, the middles of the strokes near that ink, and
    those middles carrying its colour cast. They are a last filter rather than a
    separation, and BAND_ON_LINE and BAND_CORE_CAST say by how much.
    """
    import numpy as np

    if not block.size:
        return False
    edge = max(1, int(BAND_SIDE * BAND_DPI / 72.0) - BAND_SIDE_SLACK)
    sides = np.concatenate((block[:, :edge], block[:, -edge:]), axis=1)
    if float((sides.min(axis=2) < BAND_WHITE).mean()) > BAND_SIDE_INK:
        return False

    region = block.reshape(-1, 3).astype(float)
    colour = np.array(ink, float)
    marked = region[region.min(axis=1) < BAND_WHITE]
    share = (float((_off_the_line(marked, colour) <= BAND_ON_LINE).mean())
             if len(marked) else 0.0)
    core = (region[region.min(axis=1) < BAND_LINK_CORE_DARK]
            if tuple(ink) == BAND_LINK_INK else
            region[region.max(axis=1) < BAND_CORE_DARK])
    if not len(core):
        return False
    middle = float((np.linalg.norm(core - colour, axis=1) <= 30).mean())
    average = core.mean(axis=0)
    cast = (average[2] - average[0]) / max(1.0, colour[2] - colour[0])
    return (share >= BAND_INK_SHARE and middle >= BAND_CORE_SHARE
            and cast >= BAND_CORE_CAST)


def _band_at(arr, ink) -> Optional[dict]:
    """The band across the TOP of ``arr``, as ``{"words": (from, to), "end": n}``.

    ``end`` is how many rows of this edge the report itself drew - its white
    margin, the words, and the eight points of white it leaves before the
    picture begins - and ``words`` is where the words sit inside them, None when
    the edge carries the white margin and nothing else, which is what a burned
    clipping with no headline looks like. None altogether means this edge is not
    one of ours: there is no white margin at it, or far too much of one.

    Hand it ``arr[::-1]`` for the bottom edge; the answer then counts up from
    the bottom.
    """
    import numpy as np

    pixels = BAND_DPI / 72.0
    pad_px = BAND_PAD * pixels
    # The cheap answer first, and it is the answer nearly every time. Only the
    # first few dozen rows are looked at, so a cutting that starts with ink -
    # which is most of them - costs one pass over 58 rows and nothing else.
    head = int(pad_px + BAND_PAD_LONG) + 1
    inked = np.flatnonzero(arr[:head].min(axis=2).min(axis=1) < BAND_WHITE)
    if not len(inked):
        return {"words": None, "end": int(round(pad_px))}
    pad = int(inked[0])
    if pad < pad_px - BAND_PAD_SHORT:
        return None

    look = min(arr.shape[0], BAND_LOOK)
    white = arr[:look].min(axis=2).min(axis=1) >= BAND_WHITE
    wanted = BAND_GAP_SHARE * BAND_GAP * pixels
    # Every white run wide enough to be the gap, taken in turn, and the band
    # goes on as long as the next line down is still our type. A headline too
    # long for one line is set as two, and the white between those two is as
    # wide as the gap itself once the heading is set large - so stopping at the
    # first wide enough gap would read half a headline and leave the other half
    # drawn on the picture. Walking on instead ends where the words do, because
    # the first thing that is not our type is the clipping.
    #
    # Each line is put to the test ON ITS OWN, not together with the lines
    # above it. Judged as one block from the top of the band down, a real
    # headline of ours outvotes whatever the walk has crossed into: of 250 real
    # clippings burned by this build and read back again, 10 came back as bands
    # of more than one line, and 8 of those had walked into the cutting and
    # taken as much as 6,000 inked pixels of it away with the band. Line by
    # line, not one of the 250 loses a pixel.
    found, line_from = None, pad
    for is_white, start, stop in _runs(white[pad:]):
        if not is_white or (stop - start) < wanted:
            continue
        words_end, band_end = pad + start, pad + stop
        # Too tall for a line or two of type: this is a column of newsprint.
        if words_end - pad > BAND_TEXT:
            break
        if not _our_type(arr[line_from:words_end], ink):
            break
        found, line_from = (words_end, band_end), band_end
    # Nothing on this edge is set off from the picture in our own ink, so only
    # the white margin itself is ours.
    if found is None:
        return {"words": None, "end": min(pad, int(round(pad_px)))}
    # The band ends eight points under the words, because that is where the
    # export puts the picture - NOT where the white after the words runs out.
    # Those are different rows, and what lies between them is the clipping's
    # own white top margin. Taken off with the band, 124 of 250 real clippings
    # burned by this build and read back again came back short of where
    # compose_with_box had put them: 217 px short at the ninety-fifth and 733
    # at the worst, which was 22% of that clipping's height. With the eight
    # points, and with each line of the band judged on its own above, not one
    # of the 250 comes back short at all.
    #
    # What is left behind instead is the slack the line box holds under the
    # last line of type, which measured 5 px under a Latin descender and 77 px
    # under a Devanagari one. Nothing in the picture says how deep that slack
    # is, so it stays on the clipping - and it is white, where what the old
    # rule took was the cutting itself.
    words_end, band_end = found
    return {"words": (pad, words_end),
            "end": min(band_end, words_end + int(round(BAND_GAP * pixels)))}


def _picture_columns(arr, top: int, bottom: int) -> tuple:
    """Which columns between those two rows the report drew rather than the clip.

    A clipping narrower than the 420 points build_burned needs for its words is
    centred on a sheet widened to hold them, so taking the bands off the top and
    bottom still leaves white of ours down both sides. Anything wider than that
    is drawn flush, edge to edge, and there is no white of ours there at all -
    which is why the sheet's own width decides this rather than where the ink
    starts. Measured on the office's burned report: five of its ten cuttings are
    on sheets wider than the narrowest, and going by the ink took 21 to 83 px
    off their sides for nothing.

    On a sheet at the narrowest width the white is ours, and it is the same
    width at both sides because the clipping is centred on it - so the narrower
    of the two inked margins is what comes off each. That can never cross ink at
    either side; what it leaves behind is the cutting's own margin.
    """
    import numpy as np

    width = arr.shape[1]
    if bottom <= top or width > int(round(BAND_MIN_WIDTH * BAND_DPI / 72.0)):
        return 0, width
    inked = np.flatnonzero(
        (arr[top:bottom].min(axis=2) < BAND_WHITE).any(axis=0))
    if not len(inked):
        return 0, width
    side = min(int(inked[0]), width - int(inked[-1]) - 1)
    return side, width - side


def _read_bands(data: bytes) -> Optional[tuple]:
    """What a burned report drew on this picture: (the title, the crop) or None.

    The address burned in under a web clipping is deliberately NOT read. It has
    nowhere to go: putting it in the link box is putting an address nobody
    checked behind a picture people click, and of the two the reader was tried
    on it got one right and spelt a word of the other with a capital letter. The
    band it sits on is measured all the same, because that is what says how much
    of the bottom of the picture belongs to the report rather than the clipping.
    """
    from PIL import Image
    import numpy as np

    if not data:
        return None
    with Image.open(io.BytesIO(data)) as opened:
        # Nothing this program burns is narrower than MIN_WIDTH points at
        # BAND_DPI, because compose widens the sheet to it - and the size comes
        # out of the file's header without a pixel being decoded. On the
        # office's 18.09 report that answers 78 of 96 pictures for nothing.
        if opened.width < int(BAND_MIN_WIDTH * BAND_DPI / 72.0):
            return None
        image = opened.convert("RGB")
        arr = np.asarray(image)
        top = _band_at(arr, BAND_INK)
        bottom = _band_at(arr[::-1], BAND_LINK_INK)
        # Our ink at one edge at least. A white margin on its own proves
        # nothing - a third of the office's own clippings have one - and
        # trimming those would change every one of their thumbnails and picture
        # prints for no reason at all.
        if not ((top and top["words"]) or (bottom and bottom["words"])):
            return None

        height, width = arr.shape[0], arr.shape[1]
        cut_top = top["end"] if top else 0
        cut_bottom = height - (bottom["end"] if bottom else 0)
        left, right = _picture_columns(arr, cut_top, cut_bottom)
        if cut_bottom <= cut_top or right <= left:
            return None

        title = ""
        if top and top["words"]:
            first, last = top["words"]
            title = ocr.band_text(image.crop(
                (0, max(0, first - BAND_MARGIN), width,
                 min(height, last + BAND_MARGIN))))

    return title, CropRect(left=left / width, top=cut_top / height,
                           right=(width - right) / width,
                           bottom=(height - cut_bottom) / height)


def candidates_of(clips) -> list:
    """The clippings a burned report would have burned: every picture in it
    that is a clipping at all."""
    return [clip for clip in clips
            if getattr(clip, "junk_reason", "") != ourfiles.COVER_NOTE]


def recover_bands(clips, warnings: Optional[list] = None) -> int:
    """Read back the names a burned report of ours drew into its own pictures.

    Returns how many names came back. Called after build_clips for a file that
    is ours and carries no record - a report with a record already knows where
    its bands are and what they said, exactly, and says so in ``apply``.

    It has to happen here, before the list makes its rows, because the crop
    decides what the thumbnail shows and what the duplicate check measures. A
    band left on would be compared against a band, and two clippings from the
    same paper wear the same band.

    The words go into ``caption_raw`` and nowhere else, so profiles.apply_to_clip
    reads them exactly as it reads a caption printed above a picture. That is
    not a convenience: what was burned in IS the printed caption - build_burned
    draws ``clip.printed_caption`` - so the two are the same line of text
    arriving by different roads.
    """
    warnings = warnings if warnings is not None else []
    named = trimmed = 0
    looked: list = []
    for clip in clips:
        # Only a clipping with nothing to go on. A caption read off the page or
        # a crop already set means this picture is not a bare composite, and
        # the cover is not a clipping at all.
        if (clip.caption_raw or "").strip() or not clip.crop.is_identity:
            continue
        if getattr(clip, "junk_reason", "") == ourfiles.COVER_NOTE:
            continue
        try:
            found = _read_bands(getattr(clip, "image_bytes", b"") or b"")
        except Exception:  # noqa: BLE001 - a picture we cannot read is not a fault
            continue
        if found is None:
            continue
        looked.append((clip, found))

    # A BURNED REPORT BURNS EVERY CLIPPING. build_burned.flatten composes every
    # one of them, so a band on one picture and nothing on the others is not a
    # burned report - it is one cutting whose own top line happens to look like
    # our type: white margins, dark blue-grey words, and nothing of its own in
    # the ten points at either side. Measured on 250 real clippings burned by
    # this build, the side geometry only bites on 68 of them - the other 182
    # are refused by the colour tests alone - so a cutting set in from its own
    # edges with a bluish first line can still be walked into. Asking the whole
    # file rather than the one picture closes that: on the office's own burned
    # report every clipping carries a band, and on 1,611 pictures of ordinary
    # documents none does.
    candidates = candidates_of(clips)
    enough = len(looked) >= max(2, (len(candidates) + 1) // 2)
    if not enough:
        return 0

    # AND THE FIRST PICTURE OF A BURNED REPORT, IF IT CARRIES NO BAND, IS THE
    # COVER. Every clipping in a burned report is composed - even the two web
    # items of the office's own 08.09 dossier carry a band, with no words on
    # it - so a first picture with none is the sheet in front of them. The PDF
    # knows this already, because its cover is page one with one picture and no
    # words (ourfiles); a Word file has no pages, so nothing said so and the
    # cover arrived as a thirteenth clipping.
    banded = {id(clip) for clip, _found in looked}
    if candidates and id(candidates[0]) not in banded:
        candidates[0].probable_junk = True
        candidates[0].junk_reason = ourfiles.COVER_NOTE

    for clip, found in looked:
        title, crop = found
        clip.crop = crop
        # The words have just been taken off the picture, so the clipping wants
        # its name printed above it again if this report is ever made afresh.
        clip.title_in_image = False
        trimmed += 1
        if title:
            clip.caption_raw = title
            named += 1
    if trimmed:
        warnings.append(
            f"{trimmed} clipping(s) in this report were sent out with the words "
            f"drawn into the picture. The band has been taken off each of them, "
            f"and {named} name(s) were {FROM_BAND} - those are worth a look "
            f"before the report goes out again."
        )
    return named
