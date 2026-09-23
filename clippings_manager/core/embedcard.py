"""The public card a post has, so nobody has to sign in to capture it.

THE PROBLEM. A link to a post on X, Facebook or Instagram opens, for anybody
not signed in, a page that is mostly a wall: "log in to see more", a banner
telling you to open the app, a feed of other people's posts round the edge.
The program used to answer that by asking the office to sign in - in the
browser inside the app, or by taking the picture from their own Chrome. That
is a chore at the start of every morning, it puts somebody's own account into
the program, and it breaks the day a site signs them out.

WHAT IS DONE INSTEAD. Every one of those sites publishes the same post a
second way, for the newspapers and blogs that quote it: an embed. It is the
address a site uses when it puts a post inside its own page, it is meant to be
read by anybody, and it is served to a browser that has never signed in to
anything. It carries the post and nothing else - the writer, the words, the
picture, the date - with no feed, no wall and no banner. That is exactly the
cutting the office wants, so the program opens the embed instead of the post.

Measured signed out, on a browser with no account of any kind: X gives the
post with its writer and date; Facebook's plugin gives a page's post whole,
Hindi and picture included, and its pictures come from fbcdn as usual;
Instagram's serves its card. None of the three asked for a sign-in.

THE LINK IS STILL THE POST'S OWN. Only the address that is OPENED changes.
The clipping keeps the address the office was sent, which is what the report
prints and what somebody clicks a year later.

WHERE IT DOES NOT REACH. A post somebody put up for their friends only has no
public card, and neither has one that has been taken down; the card says so in
its own words and the program then tries the post's own page, which is the old
way and still works for anybody who is signed in. YouTube is left alone: its
page is public already and gives a headline, which an embed would not.

Plain text work. Nothing here opens a page or reaches the network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, urlsplit

#: How wide to ask Facebook to draw the card. The plugin ignores it when the
#: card is opened on its own - measured at 500, 620 and 750, all one size - so
#: the WINDOW is the lever and this only tells the site what is wanted.
FACEBOOK_WIDE = 750

#: How wide a window each site's card is drawn in. A card fills the window it
#: is given, and the window the rest of the program uses is 820: the post then
#: came out stretched to 820 with a black band down each side of an upright
#: photograph, or - X, whose card stops at 550 - with white to the right of it.
#: These are each site's own card at its own width, measured against 820, 620,
#: 560 and 500 on a page's post.
WINDOWS = {
    "x.com": 560, "twitter.com": 560,
    "facebook.com": 560,
    "instagram.com": 700,          # its card draws up to 658
    "threads.net": 600, "threads.com": 600,
    "linkedin.com": 620,
}

#: What a site adds to a link so it can tell who shared it. None of it names
#: the post, all of it follows a link copied from a phone, and an address
#: carrying it is the same post. Dropped before the card is asked for, so the
#: same post shared twice is asked for the same way.
_TRACKING = re.compile(
    r"""(?xi)^(?:
        fbclid | igsh | igshid | mibextid | rdid | share_url | ref | refsrc
      | s | t | si | feature | app | _rdr | comment_id | notif_id | notif_t
      | utm_[a-z_]+
    )$""")

#: x.com/NorthernRailway/status/1234, /i/web/status/1234, /statuses/1234.
_X_POST = re.compile(r"(?i)/(?:[^/]+/status(?:es)?|i/web/status)/(\d{1,25})\b")
#: instagram.com/p/CODE, /reel/CODE, /tv/CODE - the code is the post.
_INSTAGRAM_POST = re.compile(r"(?i)/(p|reel|reels|tv)/([A-Za-z0-9_-]{5,32})\b")
#: threads.net/@somebody/post/CODE.
_THREADS_POST = re.compile(r"(?i)/@([A-Za-z0-9._]{1,40})/post/([A-Za-z0-9_-]{5,32})\b")
#: linkedin.com/posts/name-activity-1234567890123-abcd, and the form the site
#: itself uses, /feed/update/urn:li:activity:1234567890123.
_LINKEDIN_POST = re.compile(r"(?i)(?:activity[:-]|ugcPost[:-])(\d{10,25})\b")
#: A Facebook address that names one post rather than a person or a page:
#: /posts/…, /permalink/…, ?story_fbid=…, /videos/…, /photo(s)/…, /share/p/…,
#: /reel/…, /notes/…, and the /watch/?v= form.
_FACEBOOK_POST = re.compile(
    r"""(?xi)
      /posts?/ | /permalink | story_fbid= | /videos?/ | /photos?/ | /photo\b
    | /share/(?:p|v|r)/ | /reel/ | /notes?/ | /watch | /media/set | fbid=
    """)

#: The sites whose posts have a public card here. A site not in it is captured
#: the way it always was.
SITES = ("x.com", "twitter.com", "facebook.com", "instagram.com",
         "threads.net", "threads.com", "linkedin.com")

#: What a card says when there is no public post behind the address: it was
#: taken down, or it was never public. Matched in the page's own words,
#: lower-cased, because each site words it its own way and none of them gives
#: a status code to go on. Measured on each site's card, signed out.
GONE_WORDS = (
    "no longer available",              # Facebook
    "may have been removed",            # Facebook, Instagram
    "may be broken",                    # Instagram
    "sorry, this page isn",             # Instagram, older wording
    "this post is unavailable",         # Threads
    "hmm...this page doesn",            # X, a deleted post
    "this post is from an account",     # X, a locked account
    "content isn't available",          # Facebook, a friends-only post
    "content is no longer available",
)


@dataclass(frozen=True)
class Card:
    """A post's public card: the address to open, and who it belongs to."""

    url: str                 # what the browser is pointed at
    site: str                # the post's own site, as the link had it
    platform: str            # what a person calls that site
    kind: str = "post"

    @property
    def window(self) -> int:
        """How wide a window to draw this card in."""
        return WINDOWS.get(self.site, 620)

    @property
    def note(self) -> str:
        return f"{self.platform} card, {self.window} wide"


def _host(url: str) -> str:
    """The site an address points at, without "www." or a leading dot."""
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _site(host: str) -> str:
    """Which of the sites with a card this host belongs to, or ""."""
    for name in SITES:
        if host == name or host.endswith("." + name):
            return name
    return ""


def _trimmed(url: str) -> str:
    """The address with the sharing marks taken off, and nothing else.

    A link copied out of WhatsApp carries whatever the phone added -
    "?fbclid=…", "?igsh=…", "&utm_source=…". The post is the same post; only
    the marks differ, so they go before the card is asked for. Anything that
    is not a mark is left exactly as it was: "?v=12345" on a Facebook video
    IS the post.
    """
    split = urlsplit(url)
    if not split.query:
        return url.split("#", 1)[0]
    kept = [pair for pair in split.query.split("&")
            if pair and not _TRACKING.fullmatch(pair.split("=", 1)[0])]
    rest = f"?{'&'.join(kept)}" if kept else ""
    port = f":{split.port}" if split.port else ""
    return f"{split.scheme or 'https'}://{split.hostname or ''}{port}{split.path}{rest}"


def card_for(url: str) -> Optional[Card]:
    """The public card for this post, or None when the address has none.

    None means "capture it the way you always did": it is not one of the
    sites, or it is one of them but the address names a person, a page or a
    search rather than one post.
    """
    url = (url or "").strip()
    if not url:
        return None
    host = _host(url)
    site = _site(host)
    if not site:
        return None
    plain = _trimmed(url)
    path = urlsplit(plain).path or "/"

    if site in ("x.com", "twitter.com"):
        found = _X_POST.search(path)
        if not found:
            return None
        # theme and lang are fixed so the card looks the same every morning,
        # and dnt asks X not to count the view as a person reading it.
        return Card(url=("https://platform.twitter.com/embed/Tweet.html"
                         f"?id={found.group(1)}&theme=light&dnt=true&lang=en"),
                    site=site, platform="X")

    if site == "instagram.com":
        found = _INSTAGRAM_POST.search(path)
        if not found:
            return None
        kind = "reel" if found.group(1).startswith("reel") else found.group(1)
        # "captioned" is the form that carries the writing under the picture.
        # Without it the card is the photo alone, which says nothing.
        return Card(url=(f"https://www.instagram.com/{kind}/{found.group(2)}"
                         "/embed/captioned/"),
                    site=site, platform="Instagram")

    if site in ("threads.net", "threads.com"):
        found = _THREADS_POST.search(path)
        if not found:
            return None
        return Card(url=(f"https://www.threads.net/@{found.group(1)}"
                         f"/post/{found.group(2)}/embed"),
                    site=site, platform="Threads")

    if site == "linkedin.com":
        found = _LINKEDIN_POST.search(plain)
        if not found:
            return None
        return Card(url=("https://www.linkedin.com/embed/feed/update/"
                         f"urn:li:activity:{found.group(1)}"),
                    site=site, platform="LinkedIn")

    # Facebook. The plugin takes the post's own address and draws it, so
    # nothing is picked out of the link but the fact that it names a post.
    if not _FACEBOOK_POST.search(plain):
        return None
    # Always the plain site: a link copied on a phone says m.facebook.com,
    # and the plugin is asked for the same card either way.
    wanted = re.sub(r"(?i)^https?://(?:[a-z0-9-]+\.)*facebook\.com",
                    "https://www.facebook.com", plain)
    return Card(url=("https://www.facebook.com/plugins/post.php"
                     f"?href={quote(wanted, safe='')}"
                     f"&show_text=true&width={FACEBOOK_WIDE}"
                     "&adapt_container_width=true&lazy=false"),
                site=site, platform="Facebook")


#: The hosts a site keeps for phones, and what the same page is called on a
#: computer. A link copied on a phone and sent on WhatsApp - which is how most
#: of them arrive - points at one of these, and the site then draws its page
#: for a phone: one column, and a bar across it offering to open the post in
#: the app. Opened by its desktop name, no such bar is ever drawn, which is
#: what the browser does for anybody typing the link themselves.
#:
#: Only where the desktop name is certain to serve the same page. Nothing is
#: guessed from an "m." on a site the program does not know: a newspaper's
#: m.example.com may be the only address its story has.
DESKTOP_HOSTS = {
    "m.facebook.com": "www.facebook.com",
    "mbasic.facebook.com": "www.facebook.com",
    "web.facebook.com": "www.facebook.com",
    "touch.facebook.com": "www.facebook.com",
    "mobile.twitter.com": "x.com",
    "m.twitter.com": "x.com",
    "mobile.x.com": "x.com",
    "m.youtube.com": "www.youtube.com",
}


def desktop_form(url: str) -> str:
    """The same page as a computer would ask for it, or the address unchanged.

    Used for a link with no card of its own, so that a post's page, a profile
    or a video opens as it does on a desktop rather than as a phone's page
    with "open in the app" across it.
    """
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return url
    wanted = DESKTOP_HOSTS.get(host)
    if not wanted:
        return url
    return re.sub(r"(?i)^(https?://)" + re.escape(host), r"\1" + wanted, url, count=1)


def is_card(url: str) -> bool:
    """Whether this is an address the program opened for a card, rather than a
    page somebody asked for. The scripts inside the page ask, so that a card is
    cut to its own edges and nothing on it is taken for an advert."""
    plain = (url or "").lower()
    return bool(
        plain.startswith("https://platform.twitter.com/embed/")
        or "/plugins/post.php" in plain
        or re.search(r"(?i)instagram\.com/(?:p|reel|tv)/[^/]+/embed", plain)
        or re.search(r"(?i)threads\.(?:net|com)/@[^/]+/post/[^/]+/embed", plain)
        or "linkedin.com/embed/feed/update/" in plain)


def gone(words: str) -> bool:
    """Whether a card is saying there is no public post behind the address -
    taken down, or never public. The words are the site's own."""
    plain = " ".join((words or "").lower().split())
    return any(mark in plain for mark in GONE_WORDS)
