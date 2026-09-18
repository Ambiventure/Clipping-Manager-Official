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

import re
from typing import Iterable

#: The cover's own lines. The count is printed by build_pdf, build_docx and
#: cover_render - every cover this program can make carries it.
COVER_COUNT = "NUMBER OF CLIPPINGS:"
COVER_DATE = "DATE :"

#: The coverage summary page's heading (2.0.31).
SUMMARY_TITLE = "Coverage summary"

#: What a page number looks like on its own at the foot of a sheet. Numbers are
#: only furniture in one of our own files: a division's caption that is nothing
#: but a page number is rare but real, and this never sees those.
_ONLY_A_NUMBER = re.compile(r"^\s*\d{1,4}\s*$")


def _text(event) -> str:
    return (getattr(event, "text", "") or "").strip()


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
        if text.startswith(COVER_COUNT) or text == SUMMARY_TITLE:
            return True
    return False


def mark_furniture(events: list) -> int:
    """Mark the cover, the page numbers and the summary page. Returns how many.

    Only ever called for one of our own files, and only ever ADDS furniture
    marks: a document that prints none of this is left exactly as it was.
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
        if baked or printed:
            for event in on_page:
                if not event.furniture:
                    event.furniture = True
                    event.furniture_note = "the report's cover"
                    marked += 1
    else:
        last_cover_line = None
        for index, event in enumerate(events):
            if getattr(event, "kind", "") != "text":
                continue
            text = _text(event)
            if text.startswith(COVER_COUNT) or text.startswith(COVER_DATE):
                last_cover_line = index
        if last_cover_line is not None:
            for event in events[:last_cover_line + 1]:
                if not event.furniture:
                    event.furniture = True
                    event.furniture_note = "the report's cover"
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
