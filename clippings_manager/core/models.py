"""Core data model shared by the extractors, the UI and the exporters.

A Clip is one newspaper clipping: the image bytes exactly as they were stored in the
source document, plus everything we know about where it came from and what it says.
Image bytes are kept in their original encoding; the crop is stored as a rectangle and
applied on render, so a crop is always reversible and never destroys pixels.
"""

from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Section(str, Enum):
    """Sentiment / category section a clip was filed under in its source document."""

    POSITIVE = "Positive"
    NEUTRAL = "Neutral"
    DIGITAL = "Digital"
    ADVERTISEMENT = "Advertisement"
    NEGATIVE = "Negative"
    ELECTRONIC = "Electronic"
    SOCIAL = "Social"

    @property
    def sort_key(self) -> int:
        return _SECTION_ORDER.index(self)


_SECTION_ORDER = [
    Section.POSITIVE,
    Section.NEUTRAL,
    Section.DIGITAL,
    Section.ADVERTISEMENT,
    Section.NEGATIVE,
    Section.ELECTRONIC,
    Section.SOCIAL,
]


@dataclass
class CropRect:
    """A crop expressed as fractions of the image, matching DrawingML's ``a:srcRect``.

    Word stores srcRect in 1000ths of a percent, so ``l="4000"`` means trim 4% off the
    left edge. Missing attributes mean zero. Negative values mean Word *padded* the
    image outward; we cannot invent pixels, so those clamp to zero and are recorded in
    ``raw`` for reference.
    """

    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0
    raw: Optional[dict] = None

    @property
    def is_identity(self) -> bool:
        return not any((self.left, self.top, self.right, self.bottom))

    @classmethod
    def from_src_rect(cls, attrs: dict) -> "CropRect":
        """Build from the raw attribute dict of an ``<a:srcRect>`` element."""
        raw = {k: attrs.get(k) for k in ("l", "t", "r", "b")}

        def frac(key: str) -> float:
            value = attrs.get(key)
            if value in (None, ""):
                return 0.0
            try:
                # Negative srcRect pads the image out; there are no pixels to recover.
                return max(0.0, int(value) / 100000.0)
            except ValueError:
                return 0.0

        return cls(frac("l"), frac("t"), frac("r"), frac("b"), raw=raw)

    def box(self, width: int, height: int) -> tuple[int, int, int, int]:
        """Pixel crop box for a WxH image, clamped to at least one pixel."""
        left = int(round(self.left * width))
        top = int(round(self.top * height))
        right = int(round((1.0 - self.right) * width))
        bottom = int(round((1.0 - self.bottom) * height))
        right = max(right, left + 1)
        bottom = max(bottom, top + 1)
        return left, top, min(right, width), min(bottom, height)


# The only sections ever printed as a heading, and the words used. These are the
# two the 360 Degree document has; the six division reports head their runs too
# ("POSITIVE NEWS :-") and have never printed them.
SECTION_NAMES = {
    Section.ELECTRONIC.value: "ELECTRONIC MEDIA",
    Section.SOCIAL.value: "SOCIAL MEDIA",
}


# "Page 3", "page-3", "pg 4", "p.5" - and never a bare number, so a headline
# reading "12 new trains announced" or "Platform 5 gets a new roof" is not
# mistaken for one that already names its page.
_PAGE_ALREADY = re.compile(r"\bp(?:age|g)?\b\s*[-.:]?\s*\d", re.I)


@dataclass
class Clip:
    """One clipping, from import through review to export."""

    # Its own name, so one clipping can point at another and still mean it after
    # a save and a reload. Nothing had needed that until clippings could be
    # marked as repeats of each other.
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)

    # --- provenance -------------------------------------------------------------
    source_file: str = ""
    source_ref: str = ""          # e.g. "word/media/image7.png" or "page 3 / xobject 2"
    division: str = ""            # DLI, MB, UMB, FZR, LKO, JAT — "" for loose images
    doc_index: int = 0            # position in the source document, 0-based
    section: Section = Section.NEUTRAL

    # The heading a person chose for this clipping, by name - "electronic",
    # "social", "digital", or one of their own. Deliberately NOT a Section
    # member: Section also decides which column a clipping sits in on the
    # Sentiment Board, and sentiment.column_for ends "return Section.NEUTRAL",
    # so a value added here for the sake of a heading would silently re-file
    # somebody's clipping onto Neutral. A plain string cannot move anything.
    #
    # section_title below still holds the WORDS. Both are written together, so
    # a session saved here and opened on an older build still prints the
    # heading - the older build reads the words and ignores the key.
    section_key: str = ""

    # --- image ------------------------------------------------------------------
    image_bytes: bytes = b""
    image_ext: str = ".png"
    native_width: int = 0
    native_height: int = 0
    crop: CropRect = field(default_factory=CropRect)
    rotation: int = 0             # degrees clockwise; phone photos arrive sideways
    is_vml: bool = False          # came from a legacy <v:imagedata> shape

    # --- parsed fields ----------------------------------------------------------
    caption_raw: str = ""         # the caption line exactly as it appeared
    newspaper: str = ""
    edition: str = ""             # edition / city
    page: str = ""

    # --- where the name came from, and how sure we are --------------------------
    name_source: str = ""         # "caption" | "ocr" | "manual" | "copied" | ""
    name_confidence: float = 0.0  # 0.0-1.0, whatever the source
    ocr_text: str = ""            # the headline read off the picture, for matching
    # What language the clipping itself appears to be in, worked out once from
    # the script of its own text, and where that answer came from. Only ever
    # consulted when the newspaper has no name for the list to look up - which
    # on a real morning is half of them.
    language_seen: str = ""
    language_source: str = ""
    ocr_engine: str = ""
    headline_confidence: int = 0  # 0-100, how sure the reader was

    # --- review state -----------------------------------------------------------
    label: str = ""               # what prints above the image; blank means derive it
    title_in_image: bool = False  # Delhi and Lucknow burn the masthead into the scan
    # Show the address box on this card even though there is no address yet.
    # A pasted screenshot has neither a caption nor a link, so the card draws
    # only the headline box and there is nowhere to put the story's address.
    show_url_box: bool = False
    # The mirror of it, for the digital column: there the address is the field
    # that is always there and the headline is the one asked for.
    show_title_box: bool = False

    # A finer picture print, 256 bits over the same trimmed content box as
    # picture_hash. Sixty-four bits cannot tell two different cuttings of one
    # story from a genuine rescan - measured, on real mornings the two
    # populations INVERT, with a real repeat 25 apart and a non-repeat 24 - and
    # no cut-off can separate an inversion. At 256 bits they separate.
    picture_hash_fine: str = ""
    # The size of the content box the prints were taken over, in pixels. Raw
    # image dimensions are no use for this: a genuine rescan pair differs by 56%
    # on raw pixels and 2.8% on the content box, because one copy carries a
    # typed caption band and the other does not.
    content_w: int = 0
    content_h: int = 0
    # Where the ink sits, row by row and column by column: 128 numbers, written
    # as text so a session file stays plain JSON. Two cuttings of DIFFERENT
    # stories put their ink in different places even when their thumbnails
    # rhyme, which is what this is for.
    ink_profile: str = ""
    # The user emptied the headline box and meant it. Without this, clearing
    # the box only removed what was TYPED and the parsed caption underneath
    # reappeared the moment focus left - so a title could not be got rid of.
    no_title: bool = False
    include: bool = True
    sort_position: int = 0        # user-set order; authoritative at export time
    probable_junk: bool = False
    junk_reason: str = ""
    # The uid of the clipping this one repeats, or None. Set both by the
    # within-file check at import and by the headline comparison across files.
    duplicate_of: Optional[str] = None
    # The user looked at it and said it was not a repeat. Their word is final:
    # it is never flagged again, however alike the headlines look.
    not_duplicate: bool = False
    # Set when the duplicate check itself excluded this clipping, so the check
    # knows which exclusions are its own to undo. Without it, a clipping
    # dropped as a repeat stayed dropped after the thing it repeated was
    # deleted - out of the report for good, with no badge and no reason shown.
    excluded_as_duplicate: bool = False
    image_hash: str = ""           # exact bytes, for the same picture twice
    # What the cutting LOOKS like, roughly - see imageops.fingerprint. The one
    # above changes if a single byte does; this one survives a rescan, a crop
    # and a stamped-on masthead, and differs between two cuttings of one story.
    picture_hash: str = ""
    # The same, of the lower part alone - what the cutting looks like below the
    # newspaper's masthead banner, which is identical on every cutting that
    # paper prints and makes unrelated stories resemble one another.
    picture_hash_lower: str = ""

    # --- digital / social extras ------------------------------------------------
    url: str = ""
    outlet: str = ""

    # The name of the section this clipping opens, as the source document printed
    # it: "ELECTRONIC MEDIA" over the first item of the electronic run, "SOCIAL
    # MEDIA" over the first social one. It belongs to the clipping rather than to
    # the report, so it travels with the picture when the picture is moved, and
    # anyone can see on the card that the report will carry it.
    section_title: str = ""

    # ------------------------------------------------------------------------
    @property
    def display_caption(self) -> str:
        """As it prints above the picture: 'Newspaper, Edition, Page 3'.

        The page number is part of what identifies a cutting, and the department
        writes it into the caption itself - "Dainik Bhaskar page no- 2 Firozpur",
        "AMAR UJALA AMBALA EDITION PAGE 1". The import lifts it into its own
        field so it can be corrected on the card, and it used to stop there: the
        report printed "Dainik Bhaskar, Firozpur" and the reader had no way to
        find the cutting in the paper.

        Only ever added to a name. A page number on its own is not a caption, so
        a clipping whose masthead could not be read stays blank rather than
        printing as "Page 5".
        """
        parts = [p for p in (self.newspaper.strip(), self.edition.strip()) if p]
        if parts and self.page.strip():
            parts.append(f"Page {self.page.strip()}")
        return ", ".join(parts)

    @property
    def effective_label(self) -> str:
        """What actually prints above the picture.

        A typed label always wins; an emptied one wins too. Falling back to the
        parsed caption whenever nothing was typed meant a caption could never be
        removed - delete it, click away, and "Amar Ujala, Ambala, Page 1" came
        straight back, because it had never been what was typed in the first
        place.
        """
        if self.no_title:
            return ""
        return self.label.strip() or self.display_caption

    @property
    def printed_caption(self) -> str:
        """What prints ABOVE the picture. `effective_label` is its NAME.

        The page number is where the cutting is in the paper - the one thing a
        reader has who wants to find the story again - so typing a headline
        must not throw it away. It used not to: `effective_label` returns the
        typed label OR the assembled caption, and the assembled caption is the
        only place the page was ever written.

        Two guards. Nothing is added when no headline was typed, because the
        assembled caption already carries the page and would otherwise get a
        second one. And nothing is added when the typed headline already names a
        page itself.
        """
        said = self.effective_label
        if not said:
            return ""
        page = self.page.strip()
        if page and self.label.strip() and not _PAGE_ALREADY.search(said):
            return f"{said}, Page {page}"
        return said

    @property
    def title_text(self) -> str:
        """What the one title field shows.

        Digital, electronic and social coverage is a screenshot of a web page,
        and what identifies it is the address the import read from under the
        picture - so with nothing typed, that is what the field offers. Type a
        headline over it and the headline is what the field holds; the address
        is not lost, it goes on printing underneath where it belongs.
        """
        if self.no_title:
            return ""
        return self.effective_label or self.url.strip()

    @property
    def needs_attention(self) -> bool:
        """True when the review grid should flag this clip amber.

        A clip the user has typed themselves is never flagged, however odd it looks.
        Neither is one whose masthead is printed on the picture: Delhi and Lucknow
        burn it in, so the page carries its own title and no caption is wanted.
        """
        if self.name_source == "manual":
            return False
        if self.title_in_image and not self.label.strip():
            return False
        return not self.newspaper or self.name_confidence < 0.75

    def rendered_size(self) -> tuple[int, int]:
        """Pixel size after the crop and any rotation are applied."""
        if self.crop.is_identity:
            width, height = self.native_width, self.native_height
        else:
            left, top, right, bottom = self.crop.box(
                self.native_width, self.native_height
            )
            width, height = right - left, bottom - top
        if self.rotation % 180:
            return height, width
        return width, height

    def render(self):
        """Open the clip as a PIL image with its crop applied.

        Imported lazily so the extractor and its tests stay usable without Pillow.
        """
        from PIL import Image

        image = Image.open(io.BytesIO(self.image_bytes))
        image.load()
        if not self.crop.is_identity:
            image = image.crop(self.crop.box(image.width, image.height))
        if self.rotation % 360:
            # expand=True so a 90 degree turn does not clip the corners off
            image = image.rotate(-self.rotation, expand=True)
        return image

    def to_manifest(self, image_path: str = "") -> dict:
        """JSON-safe summary. Image bytes are deliberately excluded."""
        data = asdict(self)
        data.pop("image_bytes")
        data["section"] = self.section.value
        data["crop"] = {
            "left": self.crop.left,
            "top": self.crop.top,
            "right": self.crop.right,
            "bottom": self.crop.bottom,
            "raw_src_rect": self.crop.raw,
            "is_identity": self.crop.is_identity,
        }
        data["rendered_width"], data["rendered_height"] = self.rendered_size()
        data["display_caption"] = self.display_caption
        if image_path:
            data["image_path"] = image_path
        return data
