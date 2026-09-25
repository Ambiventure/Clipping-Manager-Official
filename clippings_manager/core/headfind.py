"""Where the headline is on a cutting - found by looking, before anything is read.

The reader used to take a fixed slice off the top of the picture (40 per cent,
then 72, then all of it), read every line in it, and keep the tallest. Two
things went wrong with that, and both came back as gibberish:

  * A photograph above the headline was READ. Tesseract finds "lines" in a
    photograph as happily as in type, and a patch of a man's shirt read as
    nonsense and was sometimes the tallest thing in the slice.
  * The biggest type on a cutting is often NOT the headline. The office's own
    label ("The Times of India Pg 4 25.09.26"), a newspaper's nameplate
    ("THESE DAYS") and a division's stamped strip are all set larger than the
    story's headline, and none of them is part of the article.

So this looks first and reads second. OpenCV finds the article - the columns of
body text and the photographs among them - and the headline is the bold type
that belongs to that article: sitting on top of it, or inside it, never out on
its own beyond a gap. Only that one region is read. It is faster, because the
reader sees a strip a few lines high rather than half a page, and it cannot
read a photograph, because a photograph is never the region it is handed.

Nothing here reads a word. It is geometry only: the size and the weight of
the ink, where the columns are, where the pictures are.

WEIGHT, NOT ONLY SIZE. A Hindi word's height depends on its vowel signs - "पर"
is two thirds the height of "मिला" in the same line of the same headline - so
height alone split headlines apart and dropped their shorter words. How thick
the strokes are does not change with the vowel signs, and it is what makes a
headline a headline: bold type over thin body text. Both are used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

#: Pictures are measured at this width. Sizes below are in these pixels, so a
#: 600-pixel phone capture and a 4000-pixel scan are judged alike.
WORK_WIDTH = 1100

#: Type this much taller than the body text is headline type on size alone.
HEADLINE_RATIO = 1.7
#: Or this much taller AND this much bolder. The tight Hindi crops the
#: divisions send set the headline only 1.4-1.6 times the body, which the
#: size rule alone missed entirely - but always in much heavier strokes.
BOLD_RATIO = 1.25
BOLD_STROKE = 1.55

#: A word beside a headline line joins it when it is at least this tall and
#: this bold, relative to the line. Body text in the next column, level with
#: the headline, fails the weight test however tall its vowel signs are.
KIN_HEIGHT = 0.55
KIN_STROKE = 0.62

#: Picture regions: a window mostly mid-grey (photographs are grey, type on
#: newsprint is black on white) or mostly ink (a dark photograph).
GRAPHIC_SHARE = 0.34
DARK_SHARE = 0.6

#: How far above the article a headline may sit, in its own type heights.
#: A headline sits on its story; an office label or a nameplate sits above
#: a gap.
MAY_FLOAT = 1.6


@dataclass
class Region:
    """A box on the picture, in the picture's own pixels."""

    left: int
    top: int
    right: int
    bottom: int
    #: How tall its type is, in the picture's own pixels.
    type_height: float = 0.0
    #: Why it was chosen, or why not - for the pictures that check this.
    note: str = ""
    score: float = 0.0
    #: The headline's own lines, without the padding round them - what the
    #: reader keeps when it clears the edges of the box. See ocr.read_region.
    core: tuple = ()
    #: Each line on its own, as regions - for reading a block line by line
    #: when the whole of it reads as a label. See ocr.two_stage.
    lines: tuple = ()

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def box(self) -> tuple:
        return (self.left, self.top, self.right, self.bottom)


@dataclass
class Finding:
    """Everything the look worked out, best candidate first."""

    candidates: list = field(default_factory=list)
    #: The article itself, when one was found.
    article: Optional[Region] = None
    #: Rejected headline type - the office's label, the nameplate - and why.
    rejected: list = field(default_factory=list)
    body_height: float = 0.0
    #: The candidate whose reading was used - the best one, unless it read
    #: as nothing or as a paper's name. Set by ocr.two_stage.
    chosen: Optional[Region] = None

    @property
    def best(self) -> Optional[Region]:
        return self.candidates[0] if self.candidates else None


def available() -> bool:
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:  # noqa: BLE001 - no OpenCV means the old way
        return False


# ------------------------------------------------------------------- helpers
def _gray(image):
    """The picture as grey levels at the working width, and the scale used."""
    import cv2
    import numpy as np

    gray = np.asarray(image.convert("L"))
    height, width = gray.shape[:2]
    scale = WORK_WIDTH / float(max(1, width))
    if abs(scale - 1.0) > 0.08:
        gray = cv2.resize(
            gray, (max(1, int(round(width * scale))),
                   max(1, int(round(height * scale)))),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
    else:
        scale = 1.0
    # Reversed type - white on black - is turned the ordinary way round. Told
    # by how much of the picture is PAPER, not by its middle grey: a cutting
    # between two black bands is half black and still black type on white.
    if float((gray > 150).mean()) < 0.3:
        gray = 255 - gray
    return gray, scale


def _ink(gray):
    """Black on white, as 255 on 0.

    Two thresholds, joined. The local one follows uneven light across a
    phone photograph, but inside a stroke thicker than a third of its window
    the neighbourhood is dark too, so the stroke's middle drops out: a bold
    headline came back hollow, broken into fragments, and measured as thin.
    The page-wide one fills those strokes back in.
    """
    import cv2

    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    local = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                  cv2.THRESH_BINARY_INV, 35, 15)
    _, whole = cv2.threshold(blur, 0, 255,
                             cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return cv2.bitwise_or(local, whole)


def _graphic_mask(gray, ink):
    """Where the photographs and drawings are."""
    import cv2
    import numpy as np

    height, width = gray.shape[:2]
    window = max(15, width // 36)
    # Grey that is NOT ink. A headline printed in dark grey rather than black
    # - a scanned page, a tinted panel - is all mid-grey, and counting it
    # called the headline a photograph and erased it. Its letters are ink; a
    # photograph's tones mostly are not.
    mid = ((gray > 60) & (gray < 205) & (ink == 0)).astype(np.float32)
    share = cv2.blur(mid, (window, window))
    wide = max(25, width // 18)
    dark = cv2.blur((ink > 0).astype(np.float32), (wide, wide))
    mask = ((share > GRAPHIC_SHARE) | (dark > DARK_SHARE)).astype(np.uint8) * 255
    # Edges of bold type are grey too; they make thin shapes, a photograph
    # makes a solid one. Opening takes the thin ones away.
    grain = max(5, window // 2)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (grain, grain))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    keep = np.zeros_like(mask)
    least = (width * height) * 0.006
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] >= least:
            keep[labels == i] = 255
    return keep


def _body(pieces, page_height: int) -> tuple:
    """The body type's height and stroke: whatever covers the most WIDTH.

    Counted by width, not by piece. On an enlarged Hindi cutting the most
    NUMEROUS pieces of ink are the dots and marks above and below the
    letters, and counting pieces put the body type at 9 pixels on a cutting
    whose words are 45 tall. By width, the body text is where most ink is.
    """
    import numpy as np

    rows = [(p["h"], p["w"], p["stroke"]) for p in pieces
            if 6 <= p["h"] <= max(12, page_height * 0.12)]
    if len(rows) < 8:
        return 0.0, 0.0
    heights = [h for h, _w, _s in rows]
    weights = [w for _h, w, _s in rows]
    top = int(max(heights)) + 3
    counts, edges = np.histogram(heights, bins=range(6, top, 3),
                                 weights=weights)
    if counts.size == 0:
        return 0.0, 0.0
    at = int(np.argmax(counts))
    body = float((edges[at] + edges[at + 1]) / 2.0)
    strokes = [s for h, _w, s in rows if 0.7 * body <= h <= 1.4 * body]
    stroke = float(np.median(strokes)) if strokes else 1.0
    return body, max(0.8, stroke)


class _Joined:
    """Union-find, for pieces of ink that belong together."""

    def __init__(self, n):
        self.up = list(range(n))

    def top(self, i):
        while self.up[i] != i:
            self.up[i] = self.up[self.up[i]]
            i = self.up[i]
        return i

    def join(self, a, b):
        a, b = self.top(a), self.top(b)
        if a != b:
            self.up[b] = a


def _lines_of(pieces) -> list:
    """Headline pieces into lines, each judged by its own size and weight."""
    n = len(pieces)
    joined = _Joined(n)
    order = sorted(range(n), key=lambda k: pieces[k]["x"])
    for a_at, a in enumerate(order):
        pa = pieces[a]
        for b in order[a_at + 1:]:
            pb = pieces[b]
            gap = pb["x"] - (pa["x"] + pa["w"])
            if gap > 1.1 * max(pa["h"], pb["h"]):
                break              # sorted by left edge: nothing nearer
            if max(pa["stroke"], pb["stroke"]) > 1.8 * min(pa["stroke"],
                                                           pb["stroke"]):
                continue
            shared = (min(pa["y"] + pa["h"], pb["y"] + pb["h"])
                      - max(pa["y"], pb["y"]))
            if shared >= 0.5 * min(pa["h"], pb["h"]):
                joined.join(a, b)
    groups = {}
    for i in range(n):
        groups.setdefault(joined.top(i), []).append(pieces[i])
    return [_line(members) for members in groups.values()]


def _line(members) -> dict:
    x0 = min(p["x"] for p in members)
    y0 = min(p["y"] for p in members)
    x1 = max(p["x"] + p["w"] for p in members)
    y1 = max(p["y"] + p["h"] for p in members)
    tallest = max(p["h"] for p in members)
    sizes = sorted(p["h"] for p in members if p["h"] >= 0.5 * tallest)
    strokes = sorted(p["stroke"] for p in members)
    return {"box": [x0, y0, x1, y1], "type": float(sizes[len(sizes) // 2]),
            "stroke": float(strokes[len(strokes) // 2]),
            "members": list(members), "lines": 1}


def _grow(lines, pieces) -> None:
    """Let each line take in the words beside it that are its weight.

    "पर", "की", "मुंबई की" - the short words of a Hindi headline, short
    because they carry no vowel sign above - were left out of their own
    line by a test of height. They are exactly as bold as the rest of it,
    and the body text of the next column along, level with them, is not.
    """
    taken = set()
    for line in lines:
        for p in line["members"]:
            taken.add(id(p))
    for line in lines:
        grown = True
        while grown:
            grown = False
            x0, y0, x1, y1 = line["box"]
            size, stroke = line["type"], line["stroke"]
            for p in pieces:
                if id(p) in taken:
                    continue
                if p["h"] < KIN_HEIGHT * size or p["h"] > 1.5 * size:
                    continue
                if p["stroke"] < KIN_STROKE * stroke:
                    continue
                shared = min(y1, p["y"] + p["h"]) - max(y0, p["y"])
                if shared < 0.6 * p["h"]:
                    continue
                if p["x"] >= x1:
                    gap = p["x"] - x1
                elif p["x"] + p["w"] <= x0:
                    gap = x0 - (p["x"] + p["w"])
                else:
                    gap = 0
                if gap > 0.9 * size:
                    continue
                line["members"].append(p)
                line["box"] = [min(x0, p["x"]), min(y0, p["y"]),
                               max(x1, p["x"] + p["w"]),
                               max(y1, p["y"] + p["h"])]
                taken.add(id(p))
                grown = True
                x0, y0, x1, y1 = line["box"]


def _rejoin(lines) -> list:
    """Two halves of one line, side by side, made one line again.

    "रेलवे स्टेशन पर मिला व्यक्ति का शव": the tall words made two lines, split
    where the short word "पर" sat between them, and "पर" then joined the
    first half - leaving two lines on one row, a word-space apart, and the
    finder choosing between them as if they were two headlines. Lines that
    share their row, their weight and nearly their size, and sit a word-space
    apart, are one line.
    """
    joined = _Joined(len(lines))
    for a in range(len(lines)):
        la = lines[a]
        ax0, ay0, ax1, ay1 = la["box"]
        for b in range(a + 1, len(lines)):
            lb = lines[b]
            bx0, by0, bx1, by1 = lb["box"]
            shared = min(ay1, by1) - max(ay0, by0)
            if shared < 0.6 * min(ay1 - ay0, by1 - by0):
                continue
            gap = max(bx0 - ax1, ax0 - bx1)
            size = max(la["type"], lb["type"])
            if gap > 0.9 * size:
                continue
            if max(la["stroke"], lb["stroke"]) > 1.6 * min(la["stroke"],
                                                           lb["stroke"]):
                continue
            if max(la["type"], lb["type"]) > 1.6 * min(la["type"], lb["type"]):
                continue
            joined.join(a, b)
    groups = {}
    for i, line in enumerate(lines):
        groups.setdefault(joined.top(i), []).append(line)
    return [_line([p for line in group for p in line["members"]])
            for group in groups.values()]


def _ink_height(ink, box) -> float:
    """How tall a line's type is by where its ink is - not by its box.

    A box reaches from the highest vowel sign to the lowest, and Hindi lines
    differ in how many they carry. The band holding the middle 84 per cent of
    the ink is the body of the letters, the same on every line of one
    headline and different from a dateline's.
    """
    import numpy as np

    x0, y0, x1, y1 = box
    rows = (ink[y0:y1, x0:x1] > 0).sum(axis=1).astype(np.float64)
    total = rows.sum()
    if total <= 0:
        return float(y1 - y0)
    running = np.cumsum(rows) / total
    low = int(np.searchsorted(running, 0.08))
    high = int(np.searchsorted(running, 0.92))
    return float(max(1, high - low))


def _group_lines(mask, height: float):
    """Body letters into lines: joined sideways, barely downwards."""
    import cv2

    across = max(3, int(round(height * 0.9)))
    down = max(1, int(round(height * 0.12)))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (across, down))
    joined = cv2.dilate(mask, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(joined, 8)
    return [tuple(int(v) for v in stats[i][:4]) for i in range(1, count)]


# ---------------------------------------------------------------------- look
def find(image) -> Finding:
    """Look at a cutting and say where its headline is."""
    import cv2
    import numpy as np

    found = Finding()
    try:
        gray, scale = _gray(image)
    except Exception:  # noqa: BLE001 - a picture that will not decode
        return found
    height, width = gray.shape[:2]
    if width < 40 or height < 20:
        return found

    ink = _ink(gray)
    graphic = _graphic_mask(gray, ink)
    ink[graphic > 0] = 0          # a photograph's grain is not letters
    distance = cv2.distanceTransform(ink, cv2.DIST_L2, 3)

    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    pieces = []
    for i in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[i])
        if h < 4 or area < 10:
            continue
        if w > width * 0.92 or h > height * 0.45:
            continue              # a rule, a frame, a border
        if area / float(max(1, w * h)) > 0.85 and w > 3 * h:
            continue              # a solid bar
        inside = labels[y:y + h, x:x + w] == i
        # Stroke weight: twice the deepest point inside the ink.
        stroke = 2.0 * float(distance[y:y + h, x:x + w][inside].max())
        pieces.append({"i": i, "x": x, "y": y, "w": w, "h": h,
                       "stroke": stroke})
    if not pieces:
        return found
    body, body_stroke = _body(pieces, height)
    if body <= 0:
        body = max(8.0, float(np.median([p["h"] for p in pieces]))
                   / HEADLINE_RATIO)
        body_stroke = max(0.8, float(np.median([p["stroke"] for p in pieces])))
    found.body_height = body / scale

    # --- the body text, and from it the article --------------------------
    body_mask = np.zeros_like(ink)
    heads = []
    for p in pieces:
        x, y, w, h = p["x"], p["y"], p["w"], p["h"]
        if 0.55 * body <= h <= 1.6 * body and p["stroke"] < 1.4 * body_stroke:
            body_mask[y:y + h, x:x + w][labels[y:y + h, x:x + w] == p["i"]] = 255
        if (h >= HEADLINE_RATIO * body
                or (h >= BOLD_RATIO * body
                    and p["stroke"] >= BOLD_STROKE * body_stroke)):
            heads.append(p)

    lines = [ln for ln in _group_lines(body_mask, body) if ln[2] >= 3 * body]
    paragraph = np.zeros_like(ink)
    for x, y, w, h in lines:
        paragraph[y:y + h, x:x + w] = 255
    paragraph = cv2.dilate(paragraph, cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(3, int(body * 1.2)), max(3, int(body * 1.6)))))
    story = cv2.bitwise_or(paragraph, graphic)
    story = cv2.dilate(story, cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(3, int(body * 2)), max(3, int(body * 1.5)))))
    count_s, labels_s, stats_s, _ = cv2.connectedComponentsWithStats(story, 8)
    article = None
    best_weight = 0.0
    for i in range(1, count_s):
        x, y, w, h, _area = (int(v) for v in stats_s[i])
        # Weighed by how much BODY TEXT it holds: a lone photograph or a
        # sliver of the next story along is not the article.
        inside = paragraph[y:y + h, x:x + w][labels_s[y:y + h, x:x + w] == i]
        weight = float((inside > 0).sum())
        if weight > best_weight:
            best_weight, article = weight, (x, y, x + w, y + h)
    if article is not None and best_weight < (width * height) * 0.02:
        article = None            # too little body text to call it an article

    # --- headline type, as lines and then as blocks ----------------------
    if not heads:
        return found
    blocks = _lines_of(heads)
    _grow(blocks, [p for p in pieces if p["h"] >= 0.3 * body])
    blocks = _rejoin(blocks)
    for block in blocks:
        block["pieces"] = len(block["members"])
        block["core"] = _ink_height(ink, block["box"])

    def as_region(block, note, score=0.0):
        x0, y0, x1, y1 = block["box"]
        # Tight at the sides: half a letter of padding took in the first
        # letters of the next column along, and they came back as garbage
        # in the middle of a good reading.
        pad_y = int(block["type"] * 0.3)
        pad_x = int(block["type"] * 0.15)
        parts = []
        for part in block.get("line_boxes") or ():
            if len(block.get("line_boxes") or ()) < 2:
                break
            parts.append(as_region({"box": list(part), "type": block["type"]},
                                   note, score))
        return Region(
            left=max(0, int((x0 - pad_x) / scale)),
            top=max(0, int((y0 - pad_y) / scale)),
            right=min(int(round(width / scale)), int((x1 + pad_x) / scale)),
            bottom=min(int(round(height / scale)), int((y1 + pad_y) / scale)),
            type_height=block["type"] / scale, note=note, score=score,
            core=(int(x0 / scale), int(y0 / scale),
                  int(x1 / scale), int(y1 / scale)),
            lines=tuple(parts))

    # A LONE MARK IS NOT A LINE. One piece of ink a couple of letters wide -
    # a dot, the end of a rule, a scrap of a picture - joined the top of a
    # headline because it happened to be about the right size, and dragged
    # the box up over the paper's dateline. It is kept out of the joining,
    # not only out of the choosing.
    lone = [b for b in blocks
            if b["pieces"] < 2 or (b["box"][2] - b["box"][0]) < 2.5 * b["type"]]
    for block in lone:
        found.rejected.append(as_region(block, "a lone mark, not a line"))
    blocks = sorted((b for b in blocks if b not in lone),
                    key=lambda b: (b["box"][1], b["box"][0]))

    # Lines of the same size and weight stacked close together are one
    # headline. Each is compared with the block's FIRST line, never with what
    # the block has grown to: against a running maximum, a nameplate, the
    # strip under it and the headline under that chained into one block.
    merged = []
    for block in blocks:
        for other in reversed(merged):
            ox0, oy0, ox1, oy1 = other["box"]
            x0, y0, x1, y1 = block["box"]
            gap = y0 - oy1
            overlap = min(ox1, x1) - max(ox0, x0)
            smaller = min(block["type"], other["first"])
            core = min(block["core"], other["first_core"])
            # And by the box, within 1.4: the two lines of one Hindi
            # headline measured 1.35 apart, a red kicker over its headline
            # 1.5 - and a kicker is not the headline.
            similar = (abs(block["core"] - other["first_core"]) <= 0.25 * core
                       and max(block["type"], other["first"])
                       <= 1.4 * min(block["type"], other["first"])
                       and max(block["stroke"], other["first_stroke"])
                       <= 1.6 * min(block["stroke"], other["first_stroke"]))
            if (similar and -0.4 * smaller <= gap <= 0.9 * smaller
                    and overlap > 0.3 * min(ox1 - ox0, x1 - x0)):
                other["box"] = [min(ox0, x0), min(oy0, y0),
                                max(ox1, x1), max(oy1, y1)]
                other["pieces"] += block["pieces"]
                other["lines"] += 1
                other["type"] = max(other["type"], block["type"])
                other["line_boxes"].append(tuple(block["box"]))
                break
        else:
            fresh = dict(block)
            fresh["first"] = block["type"]
            fresh["first_core"] = block["core"]
            fresh["first_stroke"] = block["stroke"]
            fresh["line_boxes"] = [tuple(block["box"])]
            merged.append(fresh)

    if article is not None:
        ax0, ay0, ax1, ay1 = article
        found.article = Region(int(ax0 / scale), int(ay0 / scale),
                               int(ax1 / scale), int(ay1 / scale),
                               note="article")
    scored = []
    for block in merged:
        x0, y0, x1, y1 = block["box"]
        wide = x1 - x0
        pictured = graphic[y0:y1, x0:x1]
        if pictured.size and (pictured > 0).mean() > 0.3:
            found.rejected.append(as_region(block, "inside a picture"))
            continue
        where = 1.0
        if article is not None:
            ax0, ay0, ax1, ay1 = article
            overlap = min(ax1, x1) - max(ax0, x0)
            if overlap < 0.45 * wide:
                found.rejected.append(as_region(
                    block, "beside the article, not over it"))
                continue
            if y1 < ay0:
                gap = ay0 - y1
                if gap > MAY_FLOAT * block["type"] + 2 * body:
                    found.rejected.append(as_region(
                        block, "above a gap - not part of the article"))
                    continue
            elif y0 > ay1:
                found.rejected.append(as_region(block, "below the article"))
                continue
            # Nearer the top of the story is likelier the headline than a
            # sub-head half way down it.
            depth = max(0.0, (y0 - ay0) / float(max(1, ay1 - ay0)))
            where = 1.0 - 0.45 * min(1.0, depth)
        span = min(1.0, wide / float(max(1, (article[2] - article[0])
                                         if article else width)))
        # Size and weight together: the headline is the big, bold one.
        heft = block["type"] * (block["stroke"] / max(0.8, body_stroke)) ** 0.5
        score = heft * (0.55 + 0.45 * span) * where
        if block["lines"] > 3:
            score *= 0.7          # a paragraph of big type is a standfirst
        scored.append((score, block))

    scored.sort(key=lambda sb: -sb[0])
    found.candidates = [as_region(block, "headline", score)
                        for score, block in scored]
    return found
