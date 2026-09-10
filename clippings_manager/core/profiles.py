"""Turn a caption line into newspaper, edition and page.

Each division writes its captions differently, so the regexes live in
``config/divisions.json`` and can be fixed without touching this file.

Two divisions run the newspaper and the city together with no delimiter at all --
``DAINIK JAGARAN JAMMU 9`` and ``AMAR UJALA YAMUNA NAGAR EDITION PAGE 3`` -- and no
regex can know where one ends and the other begins, because ``SURODHAY BHARAT 11``
has no city in it and ``AMAR UJALA KANGRA 1`` does. So the regex only lifts the page
number, and the remaining blob is split by trying every word boundary and scoring
each half against the known-newspaper and known-edition lists. The best-scoring
split wins.

The same resolver serves the OCR stage: a rough Devanagari string from a burned-in
label is matched against the same closed list, which is reliable even when the raw
characters are not.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from rapidfuzz import fuzz

from .models import SECTION_NAMES, Clip

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalise(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace. Unicode-aware."""
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", (text or "").lower())).strip()


@dataclass
class Parsed:
    """Result of reading one caption."""

    newspaper: str = ""
    edition: str = ""
    page: str = ""
    confidence: float = 0.0     # 0.0-1.0
    rule: str = ""              # which regex fired, for debugging a bad profile
    raw_newspaper: str = ""     # what the caption actually said, before canonicalising

    @property
    def ok(self) -> bool:
        return bool(self.newspaper)


class NameIndex:
    """Known newspapers and editions, with fuzzy lookup.

    Grows at runtime: whatever the user types in the review grid is added, so the
    next day's document matches it without being retyped.
    """

    def __init__(self, data: Optional[dict] = None, settings: Optional[dict] = None):
        data = data or {}
        settings = settings or {}
        self.partial_min_alias_len = settings.get("partial_min_alias_len", 6)
        self.accept_score = settings.get("accept_score", 85)
        self.weak_score = settings.get("weak_score", 65)

        # canonical name -> aliases as written, and the same normalised for matching.
        # Both are kept so save() can round-trip the file without losing the native
        # script spellings, which are what make OCR matching work at all.
        self._papers: dict[str, list[str]] = {}
        self._papers_norm: dict[str, list[str]] = {}
        # Editions carry aliases too, so a Devanagari city from a burned-in label
        # resolves to the same canonical spelling the newspad prints.
        self._editions: dict[str, list[str]] = {}
        self._editions_norm: dict[str, list[str]] = {}

        for source, raw, norm in (
            (data.get("newspapers", []), self._papers, self._papers_norm),
            (data.get("editions", []), self._editions, self._editions_norm),
        ):
            for entry in source:
                if isinstance(entry, dict):
                    name = entry.get("name", "")
                    aliases = list(entry.get("aliases", []))
                else:
                    name, aliases = str(entry), []
                if not name:
                    continue
                raw[name] = aliases
                norm[name] = [normalise(s) for s in [name, *aliases] if s]

    # -- loading -----------------------------------------------------------
    @classmethod
    def load(cls, path: Optional[Path] = None, settings: Optional[dict] = None):
        path = Path(path) if path else CONFIG_DIR / "newspapers.json"
        with open(path, encoding="utf-8") as handle:
            return cls(json.load(handle), settings)

    @property
    def newspaper_names(self) -> list[str]:
        return sorted(self._papers)

    @property
    def edition_names(self) -> list[str]:
        return sorted(self._editions)

    def add_newspaper(self, name: str) -> None:
        name = (name or "").strip()
        if name and name not in self._papers:
            self._papers[name] = []
            self._papers_norm[name] = [normalise(name)]

    def add_edition(self, name: str) -> None:
        name = (name or "").strip()
        if name and name not in self._editions:
            self._editions[name] = []
            self._editions_norm[name] = [normalise(name)]

    def save(self, path: Path) -> None:
        """Write the grown lists back out, aliases intact."""
        payload = {
            "_version": 1,
            "newspapers": [
                {"name": name, "aliases": self._papers[name]}
                for name in sorted(self._papers)
            ],
            "editions": [
                {"name": name, "aliases": self._editions[name]}
                for name in sorted(self._editions)
            ],
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # -- scoring -----------------------------------------------------------
    def _score(self, candidate: str, alias: str) -> float:
        """How well ``candidate`` matches one known spelling.

        When the candidate is the longer string the alias may be sitting inside it --
        'Dainik Jagran (Jagran City)' contains 'Dainik Jagran' -- so a containment
        score is right. When the candidate is shorter, containment would score 'AMAR'
        against 'Amar Ujala' as a perfect match and wreck the splitter, so a whole
        string comparison is used instead.
        """
        if not candidate or not alias:
            return 0.0
        if len(candidate) > len(alias) and len(alias) >= self.partial_min_alias_len:
            return max(fuzz.partial_ratio(alias, candidate), fuzz.ratio(candidate, alias))
        return max(fuzz.ratio(candidate, alias), fuzz.token_sort_ratio(candidate, alias))

    def _best(self, candidate: str, entries: Iterable[tuple[str, str]]):
        """Highest-scoring entry, breaking ties by whole-string similarity.

        The tiebreak matters: 'hindustan times' scores 100 against both 'Hindustan'
        (contained) and 'Hindustan Times' (equal). Without it the winner is whichever
        happened to be listed first, and the masthead silently loses a word.
        """
        best_name, best_key = "", (0.0, 0.0)
        for name, alias in entries:
            key = (self._score(candidate, alias), float(fuzz.ratio(candidate, alias)))
            if key > best_key:
                best_name, best_key = name, key
        return best_name, best_key[0]

    def newspaper_detail(self, text: str) -> tuple[str, float, float]:
        """As :meth:`match_newspaper`, plus how *exactly* the text matched.

        The exactness is a whole-string similarity, so 'Dainik Jagran Nai' scores
        lower than 'Dainik Jagran' even though both contain the masthead. The
        splitter uses it to decide which half a borderline word belongs to.
        """
        candidate = normalise(text)
        if not candidate:
            return "", 0.0, 0.0
        name, score = self.match_newspaper(text)
        if not name:
            return "", 0.0, 0.0
        exactness = max(
            (float(fuzz.ratio(candidate, alias)) for alias in self._papers_norm[name]),
            default=0.0,
        )
        return name, score, exactness

    def match_newspaper(self, text: str) -> tuple[str, float]:
        """Best canonical newspaper for this text, with a 0-100 score."""
        candidate = normalise(text)
        if not candidate:
            return "", 0.0
        return self._best(
            candidate,
            (
                (name, alias)
                for name, aliases in self._papers_norm.items()
                for alias in aliases
            ),
        )

    def match_edition(self, text: str) -> tuple[str, float]:
        """Best canonical edition/city for this text, with a 0-100 score."""
        candidate = normalise(text)
        if not candidate:
            return "", 0.0
        return self._best(
            candidate,
            (
                (name, alias)
                for name, aliases in self._editions_norm.items()
                for alias in aliases
            ),
        )


# ------------------------------------------------------------------ splitting


def split_name(
    blob: str,
    index: NameIndex,
    settings: Optional[dict] = None,
) -> tuple[str, str, float]:
    """Split 'AMAR UJALA YAMUNA NAGAR' into ('Amar Ujala', 'Yamuna Nagar', score).

    Tries every word boundary and keeps the split that scores best across both
    halves. An empty edition scores neutral rather than zero, so a paper with no
    city -- 'Surodhay Bharat 11' -- is not forced to donate a word to the edition.
    """
    settings = settings or {}
    w_paper = settings.get("newspaper_weight", 0.65)
    w_edition = settings.get("edition_weight", 0.35)
    no_edition = settings.get("no_edition_score", 50)

    words = (blob or "").split()
    if not words:
        return "", "", 0.0

    best_result = ("", "", 0.0)
    best_key = (-1.0, -1.0)
    for cut in range(len(words), 0, -1):
        paper_text = " ".join(words[:cut])
        edition_text = " ".join(words[cut:])

        paper_name, paper_score, exactness = index.newspaper_detail(paper_text)
        if edition_text:
            edition_name, edition_score = index.match_edition(edition_text)
        else:
            edition_name, edition_score = "", no_edition

        total = w_paper * paper_score + w_edition * edition_score
        # Ties are common, because a masthead scores the same whether or not a city
        # is stuck to the end of it. Exactness breaks the tie toward the split that
        # leaves the newspaper name whole and nothing more.
        key = (total, exactness)
        if key > best_key:
            paper = paper_name if paper_score >= index.accept_score else paper_text
            edition = (
                edition_name
                if edition_text and edition_score >= index.accept_score
                else edition_text
            )
            best_key = key
            best_result = (paper, edition, paper_score)

    return best_result


def canonical_newspaper(text: str, index: NameIndex) -> tuple[str, float]:
    """Canonical spelling for a newspaper name that is already isolated."""
    name, score = index.match_newspaper(text)
    if score >= index.accept_score:
        return name, score
    return (text or "").strip(), score


def canonical_edition(text: str, index: NameIndex) -> tuple[str, float]:
    name, score = index.match_edition(text)
    if score >= index.accept_score:
        return name, score
    return (text or "").strip(), score


# -------------------------------------------------------------------- parsing


def _confidence(paper_score: float, matched_regex: bool, has_page: bool) -> float:
    """Turn a 0-100 name score into the 0-1 confidence the review grid flags on."""
    confidence = min(paper_score, 100.0) / 100.0
    if not matched_regex:
        confidence *= 0.75      # fields were guessed without a profile match
    if not has_page:
        confidence *= 0.95      # a missing page number is a small doubt, not a big one
    return round(min(confidence, 1.0), 3)


def parse_caption(
    caption: str,
    division: str,
    config: dict,
    index: NameIndex,
) -> Parsed:
    """Read one caption line using the profile for ``division``."""
    caption = (caption or "").strip()
    if not caption:
        return Parsed()

    profile = config.get("divisions", {}).get(division, {})
    settings = config.get("name_matching", {})
    should_split = profile.get("split_name", False)

    for number, pattern in enumerate(profile.get("caption_regexes", []), start=1):
        match = re.search(pattern, caption, re.I)
        if not match:
            continue
        groups = match.groupdict()
        page = (groups.get("page") or "").strip()
        rule = f"{division}#{number}"

        if groups.get("name_blob"):
            paper, edition, score = split_name(groups["name_blob"], index, settings)
            raw = groups["name_blob"].strip()
        else:
            raw = (groups.get("newspaper") or "").strip()
            paper, score = canonical_newspaper(raw, index)
            edition, _ = canonical_edition(groups.get("edition") or "", index)

        return Parsed(
            newspaper=paper,
            edition=edition,
            page=page,
            confidence=_confidence(score, True, bool(page)),
            rule=rule,
            raw_newspaper=raw,
        )

    # No profile regex matched. Rather than give up, split the whole line: a caption
    # in an unexpected shape still usually starts with the newspaper name.
    trailing_page = re.search(r"(?:page|pg)\D{0,4}(\d{1,3})\s*$", caption, re.I)
    page = trailing_page.group(1) if trailing_page else ""
    body = caption[: trailing_page.start()] if trailing_page else caption
    paper, edition, score = split_name(body, index, settings)
    return Parsed(
        newspaper=paper,
        edition=edition,
        page=page,
        confidence=_confidence(score, False, bool(page)),
        rule=f"{division}#fallback",
        raw_newspaper=body.strip(),
    )


def apply_to_clip(clip: Clip, config: dict, index: NameIndex) -> Parsed:
    """Fill a clip's newspaper/edition/page from its caption. Never overwrites a
    value the user typed themselves."""
    if clip.name_source == "manual":
        return Parsed(clip.newspaper, clip.edition, clip.page, clip.name_confidence)

    # Electronic and social coverage is named, not datelined. What sits over the
    # screenshot is a channel, a site or a handle - "Aaj Tak", "Babushahi.com",
    # "Facebook:" - and splitting it into a paper and a city turns "Aaj Tak" into
    # "Aaj, Tak", because the index does know a daily called Aaj. There is no
    # edition to find, so none is looked for.
    if clip.section in SECTION_NAMES and clip.caption_raw.strip():
        clip.newspaper = clip.caption_raw.strip()
        clip.edition = ""
        clip.name_source = "caption"
        clip.name_confidence = 1.0
        return Parsed(clip.newspaper, "", clip.page, 1.0)

    parsed = parse_caption(clip.caption_raw, clip.division, config, index)
    if parsed.ok or parsed.page:
        clip.newspaper = parsed.newspaper
        clip.edition = parsed.edition
        clip.page = parsed.page
        clip.name_source = "caption"
        clip.name_confidence = parsed.confidence
    return parsed


def parse_clips(clips: Iterable[Clip], config: dict, index: NameIndex) -> list[Parsed]:
    return [apply_to_clip(clip, config, index) for clip in clips]
