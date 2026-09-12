"""Finding the links in a message somebody pasted.

The coverage list arrives on WhatsApp as one message: a dozen stories, numbered,
each with a line of words and a link, and often a "Forwarded" label and the
sender's name on top. Somebody pasting that into the program wants twelve
entries, in the order they were sent, each with the words that came with it -
not one wall of text.

So this reads a message and gives back the links in the order they appear, with
whatever the sender wrote beside each one as its label. It is plain text work:
nothing here opens a page or reaches the network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: A web address inside ordinary writing. Deliberately not anchored: a link can
#: sit at the end of a line of words, in brackets, or straight after a number.
_ADDRESS = re.compile(
    r"""(?xi)
    (?<![\w@.])                      # not the tail of an email or a longer word
    (?:
        https?://[^\s<>"'\]\)]+      # a plain link
      | www\.[^\s<>"'\]\)]+          # the www form, no scheme
    )
    """)

#: "1.", "1)", "(1)", "1 -", "01." at the start of a line: the numbering of a
#: list somebody typed by hand. The number itself is not part of the label.
_NUMBER = re.compile(r"^\s*[\(\[]?(\d{1,2})(?:[\)\].:]|\s*[-–—])\s*")

#: WhatsApp's own furniture, and the sender line a copy of a message carries.
_FURNITURE = re.compile(
    r"""(?xi)
    ^\s*(?:
        \[?forwarded(?:\ many\ times)?\]?
      | \[\d{1,2}[:.]\d{2}(?:\s?[ap]\.?m\.?)?,\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\]
    )\s*""")

#: Trailing punctuation that belongs to the sentence, not to the address.
_TAIL = "’'\".,;:!?)]}>»”…।"

#: Links that are never a story to capture.
_NOT_A_STORY = ("wa.me", "whatsapp.com", "chat.whatsapp.com", "api.whatsapp.com")


@dataclass(frozen=True)
class Found:
    """One link out of the message, with what was written beside it."""

    url: str
    label: str = ""          # the sender's own words for it, if there were any
    number: int = 0          # its number in the list, when the list was numbered

    @property
    def site(self) -> str:
        """The site it points at, without "www." - "indianexpress.com"."""
        rest = self.url.split("://", 1)[-1]
        host = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].lower()
        host = host.split("@")[-1].split(":")[0]
        return host[4:] if host.startswith("www.") else host


def tidy(address: str) -> str:
    """One address, with the writing around it taken off."""
    address = address.strip().strip(_TAIL)
    # A bracket only counts as the address's own if it was opened inside it.
    while address.endswith(")") and address.count("(") < address.count(")"):
        address = address[:-1]
    if address.lower().startswith("www."):
        address = "https://" + address
    return address


def _clean_label(line: str) -> str:
    """The words on a line, with the address, the numbering and WhatsApp's own
    labels taken out. It is what the sender called the story."""
    plain, furniture = _FURNITURE.subn("", line)
    plain = _NUMBER.sub("", plain)
    plain = _ADDRESS.sub(" ", plain)
    # The sender's name, but only where WhatsApp itself put one - after the
    # "[10:15 am, 11/09/2026]" of a copied message. Stripped from every line,
    # it ate the start of any headline with a colon in it: "BRICS Summit: ...".
    if furniture:
        plain = re.sub(r"^[^:\n]{1,40}:\s+(?=\S)", "", plain)
    return " ".join(plain.split()).strip(" -–—:|")


def find(text: str) -> list[Found]:
    """Every story link in a pasted message, in the order it was written.

    The same link twice is one entry: a forwarded list often repeats the last
    story under a "read more" line.
    """
    found: list[Found] = []
    seen: set[str] = set()
    # A numbered list is often typed with the words on one line and the link on
    # the next. The words wait here until a link turns up to carry them.
    waiting_label, waiting_number = "", 0
    for line in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = _FURNITURE.sub("", line)
        numbered_here = _NUMBER.match(stripped)
        number = int(numbered_here.group(1)) if numbered_here else 0
        label = _clean_label(line)
        addresses = list(_ADDRESS.finditer(line))
        if not addresses:
            if label:
                waiting_label, waiting_number = label, number
            continue
        for match in addresses:
            url = tidy(match.group(0))
            if not url or url.lower() in seen:
                continue
            host = url.split("://", 1)[-1].split("/", 1)[0].lower()
            if any(host == bad or host.endswith("." + bad) for bad in _NOT_A_STORY):
                continue
            seen.add(url.lower())
            found.append(Found(url=url, label=label or waiting_label,
                               number=number or waiting_number))
            # A label belongs to the first link it meets; a second link on the
            # same line is its own story with no words of its own.
            label, waiting_label, waiting_number = "", "", 0
        waiting_label, waiting_number = "", 0
    return found


def numbered(found: list[Found]) -> bool:
    """Whether the sender numbered the list - 1, 2, 3 - rather than just
    writing the links one under another."""
    numbers = [row.number for row in found if row.number]
    return len(numbers) >= 2 and numbers == sorted(numbers)


#: Sites whose pages are posts rather than stories, and are filed as social
#: coverage. Everything else a link points at is digital coverage.
SOCIAL = ("x.com", "twitter.com", "facebook.com", "instagram.com",
          "threads.net", "youtube.com", "youtu.be", "linkedin.com")


def is_social(site: str) -> bool:
    host = (site or "").lower().lstrip(".")
    return any(host == name or host.endswith("." + name) for name in SOCIAL)


def _letters(words: str) -> str:
    return "".join(ch for ch in (words or "").lower() if ch.isalnum())


def paper_for_site(site: str, index) -> str:
    """The publication a site belongs to, as the newspaper list spells it.

    "indianexpress.com" is The Indian Express, "timesofindia.indiatimes.com" is
    The Times of India, "amarujala.com" is Amar Ujala. Worked out from the list
    the office keeps rather than a table written here, so a paper they add is
    recognised the same day.

    The SHORTEST listed name that holds the site's own word wins, because the
    extra letters in the longer ones are another paper's: jagran.com is Dainik
    Jagran, not Punjabi Jagran, and tribuneindia.com is The Tribune, not Dainik
    Tribune. Nothing is guessed beyond that - a site matching nothing gets no
    name, and the card shows the site instead. A wrong masthead on a cutting is
    worse than none, the same rule as the caption reader.
    """
    host = (site or "").lower().lstrip(".")
    if not host or is_social(host):
        return ""
    labels = [part for part in host.split(".")
              if part not in ("com", "in", "co", "org", "net", "www", "news")]
    if not labels:
        return ""
    word = _letters(labels[0])
    # "tribuneindia" is the Tribune's own address; "epaper", "live" and the
    # rest are how a site names its sections, not part of a masthead.
    trimmed = word
    for tail in ("india", "online", "live", "daily", "epaper", "hindi", "english"):
        if trimmed.endswith(tail) and len(trimmed) > len(tail) + 3:
            trimmed = trimmed[:-len(tail)]
            break
    names = list(getattr(index, "newspaper_names", []))
    for wanted in (word, trimmed):
        if len(wanted) < 4:
            continue
        exact = [name for name in names if _letters(name) == wanted]
        if exact:
            return sorted(exact, key=len)[0]
        holding = [name for name in names
                   if wanted in _letters(name) or _letters(name) in wanted]
        if holding:
            return sorted(holding, key=lambda n: (len(_letters(n)), n))[0]
    return ""
