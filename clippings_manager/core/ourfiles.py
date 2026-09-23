"""Reading back a report this program printed.

A finished report comes back in more often than anybody planned for: yesterday's
file reopened to lift three clippings out of it, a Word report imported to check
against the PDF, a morning rebuilt from the file that was sent. Every picture in
it was already accepted as a clipping by the person who exported it, so it must
come back in as one - included, named, and under the right heading.

WHAT WENT WRONG, AND WHY IT WAS NOT THE SIZE RULES
--------------------------------------------------

2.0.27 already knew one of our reports by its stamp and dropped the size and
shape rules for it. The report imported in September still came in with all 180
clippings flagged "probably not a clipping" and every one of them outside the
export. The reason was one line on the LAST page:

    Coverage summary
    By kind
    Print     146
    Digital    29        <- read as a section header

"Digital" is the name of a section, so the importer took that line for the first
section header in the document - and its rule is that a picture above the first
section header is a letterhead, not a clipping. Every picture in the report is
above the last page. So every clipping was flagged, and a flagged clipping
arrives with its tick cleared.

The coverage summary page went in at 2.0.31, which is exactly when this started.
It was not the size rules, it was not the stamp, and it happened in the Word
report too, word for word.

WHAT THIS MODULE DOES
---------------------

It knows the three things our own reports print that are not clippings - the
cover, the page numbers at the foot, and the coverage summary page - and marks
them as furniture before anything is read off the page. Furniture is not a
caption, is not a section header, and is not a clipping.

The words it looks for are the words the exporters print, imported from here by
both of them, so the two halves cannot drift apart.
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable, Optional

#: The cover's own lines. The count is printed by build_pdf, build_docx and
#: cover_render - every cover this program can make carries it.
COVER_COUNT = "NUMBER OF CLIPPINGS:"
COVER_DATE = "DATE :"

#: The coverage summary page's heading (2.0.31).
SUMMARY_TITLE = "Coverage summary"

#: What the sentiment dossier prints for a category that is switched on and
#: holds nothing (2.0.38). build_sentiment prints these words from here, so the
#: page that writes them and the reader that skips them cannot drift apart.
NIL_WORDS = "Nil - no clips"

#: What the dossier's Word file draws between two clippings sharing a sheet -
#: a run of this character and nothing else. Read back it became the second
#: clipping's caption, and a clipping WITH a caption at the end of a file makes
#: every picture before it "above the first captioned clipping": a six clipping
#: dossier came back with five of them flagged. Printed from here for the same
#: reason NIL_WORDS is.
DIVIDER_MARK = "─"

#: A line that is a rule and nothing else. The range is the WHOLE box drawing
#: block, U+2500 to U+257F, not only the character above: a report may have
#: been through a tool that redrew the rule with a heavier or a doubled line,
#: and any run of box drawing characters is a rule rather than a name whoever
#: printed it. Only our own files ever reach this.
_ONLY_A_RULE = re.compile(r"^[─-╿\s]+$")

#: What a cover's pictures and lines are marked as. Named because the record
#: reader (core/reportrecord) has to leave the cover out of its counting: it is
#: not a clipping, so it has no entry, and a report with as many clippings as
#: entries would never match by order if the cover were counted among them.
COVER_NOTE = "the report's cover"

#: What a page number looks like on its own at the foot of a sheet. Numbers are
#: only furniture in one of our own files: a division's caption that is nothing
#: but a page number is rare but real, and this never sees those.
_ONLY_A_NUMBER = re.compile(r"^\s*\d{1,4}\s*$")


def _text(event) -> str:
    return (getattr(event, "text", "") or "").strip()


def _named(pictures: Iterable, known) -> bool:
    """Is any of these pictures one the report's own record names?

    A picture with an entry in the record is a clipping this program put on the
    page on purpose, so it is never furniture - the same rule extract_pdf
    already applies to the backdrop of a category heading.
    """
    if not known:
        return False
    for event in pictures:
        data = getattr(event, "data", b"") or b""
        if data and hashlib.sha1(data).hexdigest() in known:
            return True
    return False


def looks_like_ours(events: Iterable) -> bool:
    """Is this document one of our reports, going by what is printed on it?

    The metadata stamp (assemble.made_here) is the first and better test; this
    is for a report made before the stamp existed, or one that has been through
    a tool that rewrote the metadata. Both lines it looks for are ours: no
    division's document has ever printed either.
    """
    for event in events:
        if getattr(event, "kind", "") != "text":
            continue
        text = _text(event)
        if (text.startswith(COVER_COUNT) or text == SUMMARY_TITLE
                or text.endswith(NIL_WORDS)):
            return True
    return False


def mark_furniture(events: list, cover: Optional[bool] = None,
                   known: Iterable[str] = ()) -> int:
    """Mark the cover, the page numbers and the summary page. Returns how many.

    Only ever called for one of our own files, and only ever ADDS furniture
    marks: a document that prints none of this is left exactly as it was.

    ``cover`` is what the report's own record says (core/reportrecord), and it
    settles a question the page cannot always answer. Left as None - every
    division's document, and every report of ours made before the record
    existed - the cover is guessed from the page exactly as it always was.

    ``known`` is the sha1 of every picture that record names, and it is how a
    report whose cover is no longer in it is recognised. See the cover block.
    """
    marked = 0
    events = list(events)

    # The summary page, and anything after it. It is the last thing in the
    # report before the numbering, and every line on it - "By kind", "Digital",
    # "Lucknow Division", the counts - is a tally, not a caption.
    start = None
    for index, event in enumerate(events):
        if getattr(event, "kind", "") == "text" and _text(event) == SUMMARY_TITLE:
            start = index
            break
    if start is not None:
        for event in events[start:]:
            if not event.furniture:
                event.furniture = True
                event.furniture_note = "the report's coverage summary"
                marked += 1

    # The cover, when there is one. Not "page 1 of a PDF": the sentiment
    # dossier opens on its first category, headed "Positive News", with the
    # first clipping under it - taking that page for a cover threw a clipping
    # away and lost the heading with it. A cover page says what it is. Either
    # it prints the count and the date, or it is one picture and nothing else,
    # which is a cover with its words baked into the picture.
    pages = {getattr(event, "page", 0) for event in events}
    if pages - {0}:
        first = min(page for page in pages if page)
        on_page = [e for e in events if getattr(e, "page", 0) == first]
        words = [_text(e) for e in on_page if getattr(e, "kind", "") == "text"]
        pictures = [e for e in on_page if getattr(e, "kind", "") == "image"]
        baked = len(pictures) == 1 and not any(words)
        printed = any(w.startswith(COVER_COUNT) or w.startswith(COVER_DATE)
                      for w in words)
        # A burned dossier with no cover and its category headings switched off
        # opens on a page holding one picture and no words - which is a
        # clipping, and the guess above would throw it away. Told there is no
        # cover, the guess is not made; told there is one, the first sheet is
        # the cover whatever it happens to print.
        if cover is False:
            wanted = False
        elif cover is True:
            # The cover is the FIRST SHEET, not the first sheet that happens to
            # carry anything. A report whose cover was left plain puts nothing
            # on page one at all, and without this the first clipping - page
            # two, one picture, no caption - would be taken for the cover.
            wanted = first == 1 and (printed or bool(pictures))
            # AND THE COVER MAY NOT BE IN THE FILE ANY MORE. Somebody deletes
            # page one before forwarding the report, or sends pages 2 onwards
            # of it, and the first sheet is then the first CLIPPING. Marking
            # that sheet ate the clipping's printed caption, flagged it
            # "probably not a clipping", and - because the reader leaves the
            # cover out of its counting - put it beyond the record's reach as
            # well, so it came back with no name at all where 2.0.39 read it
            # perfectly. A picture the record names is a clipping, so a sheet
            # holding one is not the cover, whatever the record says it had.
            if wanted and _named(pictures, known):
                wanted = False
        else:
            wanted = baked or printed
        if wanted:
            for event in on_page:
                if not event.furniture:
                    event.furniture = True
                    event.furniture_note = COVER_NOTE
                    marked += 1
    else:
        last_cover_line = None
        for index, event in enumerate(events):
            if getattr(event, "kind", "") != "text":
                continue
            text = _text(event)
            if text.startswith(COVER_COUNT) or text.startswith(COVER_DATE):
                last_cover_line = index
        # A Word report has no pages, so the cover is whatever comes before its
        # own last line. Where the cover was rasterised to one picture with its
        # words baked in, there is no such line and the record has to say so -
        # but only when nothing is written above that picture, because a line
        # above the first picture in a Word file is that clipping's caption.
        # The same guard the PDF branch needs: a Word report forwarded with its
        # cover taken out opens on a picture with nothing above it, which is
        # exactly the shape of a rasterised cover. The record names the
        # clipping and has no entry for the cover, so it settles which is which.
        if last_cover_line is None and cover is True:
            first_picture = next(
                (i for i, e in enumerate(events)
                 if getattr(e, "kind", "") == "image"), None)
            if (first_picture is not None
                    and not _named([events[first_picture]], known)
                    and not any(
                        getattr(e, "kind", "") == "text" and _text(e)
                        for e in events[:first_picture])):
                last_cover_line = first_picture
        if last_cover_line is not None:
            for event in events[:last_cover_line + 1]:
                if not event.furniture:
                    event.furniture = True
                    event.furniture_note = COVER_NOTE
                    marked += 1

    # A category with nothing in it, in the dossier: its page says so in
    # words. They are not a caption for the clipping on the next page, and
    # they are not a clipping.
    for event in events:
        if getattr(event, "kind", "") == "text" and _text(event).endswith(NIL_WORDS):
            if not event.furniture:
                event.furniture = True
                event.furniture_note = "a category with no clippings"
                marked += 1

    # The rule the Word dossier draws between two clippings on one sheet. It
    # is a line, not a name.
    for event in events:
        if (getattr(event, "kind", "") == "text" and not event.furniture
                and _text(event) and _ONLY_A_RULE.match(_text(event))):
            event.furniture = True
            event.furniture_note = "a rule between two clippings"
            marked += 1

    # The page numbers. In a PDF they are their own text event at the foot of
    # every sheet, and the caption walk above the next picture reads them: the
    # second clipping of a re-imported report was named "1 Hindustan Times,
    # Lucknow, Page 2" - page one's number, glued to page two's caption.
    #
    # A number is a page number only when it is the number THIS sheet would be
    # given: the report numbers from the first clipping, so the sheet the
    # reader calls page 7 carries a 7 and is the eighth in the file
    # (build_pdf._number_pages). Any other bare number is part of a caption,
    # and eating it costs a clipping its name - the department's own older
    # report prints "DAINIK SAWERA JAMMU" and "5" on two lines, and a rule
    # that took every lone number left that cutting unnamed.
    for event in events:
        if getattr(event, "kind", "") != "text" or event.furniture:
            continue
        page = getattr(event, "page", 0)
        if page and _ONLY_A_NUMBER.match(_text(event)):
            if int(_text(event)) == page - 1:
                event.furniture = True
                event.furniture_note = "a page number"
                marked += 1
    return marked
