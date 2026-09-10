"""The sentiment side: six divisions, four categories, and how a clip lands in one.

The standard report cares about the running order of a day's clippings. The
sentiment dossier cares about something else entirely: for each of the six Northern
Railway divisions, how the day's coverage split between positive, neutral, negative
and digital.

Most of that is already known by the time a clipping reaches here. The division
comes from the file name, and the section comes from the headings inside the
document, so a day's imports drop into the right columns without anybody sorting
them by hand. This module only fills the gaps: loose images with a telling file
name, and the mapping from the seven document sections onto the four columns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .assemble import load_config
from .models import Clip, Section

# The four board columns, in the order they are shown.
COLUMNS = (Section.POSITIVE, Section.NEUTRAL, Section.NEGATIVE, Section.DIGITAL)

# Sections with no column of their own. They all tend to carry an article link,
# which is what the Digital column is for, so that is where they appear.
FOLDS_INTO_DIGITAL = (Section.ADVERTISEMENT, Section.ELECTRONIC, Section.SOCIAL)


@dataclass(frozen=True)
class Division:
    """One Northern Railway division, as the sentiment board presents it."""

    code: str
    name: str            # "Ferozpur"
    full_name: str       # "Ferozpur Division"
    hindi_name: str      # "फ़िरोज़पुर मंडल"
    colour: str
    description: str
    order: int

    @property
    def label(self) -> str:
        return f"{self.full_name} ({self.code})"


def divisions(config: Optional[dict] = None) -> list[Division]:
    """The six divisions, in their canonical order."""
    config = config or load_config()
    order = config.get("division_order") or sorted(config["divisions"])
    found: list[Division] = []
    for code in order:
        profile = config["divisions"].get(code)
        if not profile:
            continue
        found.append(
            Division(
                code=code,
                name=profile.get("name", code),
                full_name=profile.get("full_name", f"{profile.get('name', code)} Division"),
                hindi_name=profile.get("hindi_name", ""),
                colour=profile.get("colour", "#5C666E"),
                description=profile.get("description", ""),
                order=profile.get("order", len(found)),
            )
        )
    return sorted(found, key=lambda d: d.order)


def division_by_code(code: str, config: Optional[dict] = None) -> Optional[Division]:
    for division in divisions(config):
        if division.code == code:
            return division
    return None


def column_for(section: Section) -> Section:
    """Which of the four columns a clipping's section belongs in."""
    if section in FOLDS_INTO_DIGITAL:
        return Section.DIGITAL
    if section in COLUMNS:
        return section
    return Section.NEUTRAL


def detect_sentiment(filename: str, config: Optional[dict] = None) -> Optional[Section]:
    """Guess a category from a file name, or None if it says nothing.

    Checked negative first: a name containing both "negative" and "positive" almost
    always means a file *about* negative coverage, and a positive-first order would
    quietly mis-file it.
    """
    config = config or load_config()
    settings = config.get("sentiment_detection") or {}
    keywords = settings.get("keywords") or {}
    stem = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

    for name in settings.get("order", list(keywords)):
        words = keywords.get(name) or []
        if not words:
            continue
        pattern = "|".join(re.escape(w) for w in words)
        if re.search(
            rf"(?:^|[_\-\s./\\]){pattern}(?:[_\-\s./\\0-9]|$)", stem, re.IGNORECASE
        ):
            try:
                return Section(name)
            except ValueError:
                continue
    return None


def apply_filename_hints(clip: Clip, filename: str, config: Optional[dict] = None) -> None:
    """Fill in division and category for a clipping that arrived without them.

    A clipping pulled out of a division document already knows both, and nothing
    here overwrites that. This is for the loose images: a file called
    ``LKO_negative_02.jpg`` should not have to be filed by hand.
    """
    config = config or load_config()
    if not clip.division:
        from .assemble import detect_division

        found = detect_division(filename, config)
        if found:
            clip.division = found

    if not clip.caption_raw and not clip.title_in_image:
        guess = detect_sentiment(filename, config)
        if guess is not None:
            clip.section = guess


def tally(clips, division_code: str = "") -> dict[Section, int]:
    """How many clippings sit in each column, optionally for one division."""
    counts = {column: 0 for column in COLUMNS}
    for clip in clips:
        if division_code and clip.division != division_code:
            continue
        counts[column_for(clip.section)] += 1
    return counts
