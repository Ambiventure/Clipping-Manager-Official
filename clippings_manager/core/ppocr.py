"""PaddleOCR, reading the headline the finder found.

PaddleOCR's own models - PP-OCRv5: its text detector, which finds the lines of
type in a noisy scan, and its Devanagari and English readers - run by ONNX
Runtime. The models are PaddleOCR's (Apache 2.0), exported to ONNX by the
RapidOCR project (Apache 2.0); ONNX Runtime (MIT) runs them on the processor.
Not the PaddlePaddle framework itself: that is a few hundred megabytes to run
these same three small files, and ONNX Runtime is what PaddleOCR itself
deploys them with when speed matters.

Nothing here decides WHERE the headline is. OpenCV does that first
(core/headfind), and only the region it chose is handed over - so a photograph,
the office's label and the paper's nameplate are never read, and no time goes
on reading the whole picture. The office asked for exactly that order.

Within the region: the detector finds each line of type, each line is cut out
straight and read, and the lines are put back in reading order. Every line is
read with the Devanagari reader first, which also knows English letters; a
line that comes back mostly in English letters is read again with the English
reader, and the surer of the two is kept.

Offline, always. The models travel with the program in assets/ppocr and are
opened from there; nothing is ever downloaded.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from pathlib import Path

MODELS = Path(__file__).resolve().parent.parent / "assets" / "ppocr"

#: The three files, as PaddleOCR names the models.
DETECTOR = "PP-OCRv5_mobile_det.onnx"
HINDI = "devanagari_PP-OCRv5_mobile_rec.onnx"
ENGLISH = "en_PP-OCRv5_mobile_rec.onnx"

#: PaddleOCR's own settings for its detector (PP-OCRv5, DBPostProcess).
DETECT_THRESHOLD = 0.3      # a pixel is text above this
BOX_THRESHOLD = 0.6         # a line is kept when its pixels average this
UNCLIP_RATIO = 1.5          # how far a found line is grown back out
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)

#: The detector is shown the region with its type at about this height in
#: pixels. PaddleOCR scales whole pages; a headline region can be a 40-pixel
#: strip off a phone capture or a 400-pixel one off a scan, and the detector
#: finds lines best at the sizes it was trained on.
DETECT_TYPE_HEIGHT = 40
#: And never more than this across, which is where the time goes.
DETECT_WIDEST = 2400

#: The readers take lines this tall.
READ_HEIGHT = 48

#: A found box this much narrower than it is tall is not a line of type.
UPRIGHT = 0.34

#: Processor threads per reading. Two helper processes read at once, and the
#: window has to stay responsive beside them. Four read no faster: measured,
#: 340 cuttings in two helpers took 107 seconds against 108.
THREADS = 2
#: ONNX Runtime's memory pool. On, the same 340 read in 99 seconds - and each
#: helper held 426 MB after 170 cuttings, against 193 MB with it off and 117
#: MB for Tesseract alone. Eight per cent is not worth half a gigabyte on an
#: office machine with two helpers.
ARENA = False


@dataclass
class Line:
    """One line of type found and read inside the region."""

    box: tuple          # (left, top, right, bottom) in the region's pixels
    text: str
    score: float        # 0..1, the reader's mean certainty over its letters
    height: float = 0.0  # the line's own height, in the region's pixels
    points: list = field(default_factory=list)
    #: The certainty of each letter of ``text``, in order.
    sure: list = field(default_factory=list)


class Engine:
    """The detector and the two readers, opened once per process."""

    def __init__(self, threads: int = THREADS):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, int(threads))
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        # Every region is a different size; an arena sized to the biggest one
        # seen would sit on that memory for the rest of the morning (ARENA).
        options.enable_cpu_mem_arena = ARENA
        providers = ["CPUExecutionProvider"]

        def session(name: str):
            return ort.InferenceSession(str(MODELS / name), options,
                                        providers=providers)

        self.detector = session(DETECTOR)
        self.readers = {}
        for key, name in (("hin", HINDI), ("eng", ENGLISH)):
            reader = session(name)
            listed = reader.get_modelmeta().custom_metadata_map.get("character", "")
            # PaddleOCR's CTC decoding: index 0 is the blank, the dictionary
            # follows, and the space is the last class.
            self.readers[key] = (reader, ["\x00"] + listed.splitlines() + [" "])
        self._lock = threading.Lock()

    # ------------------------------------------------------------- finding
    def find_lines(self, bgr, type_height: float = 0.0) -> list:
        """Each line of type in the picture: four corners, in its pixels."""
        import cv2
        import numpy as np

        high, wide = bgr.shape[:2]
        if high < 4 or wide < 4:
            return []
        scale = 1.0
        if type_height and type_height > 0:
            scale = DETECT_TYPE_HEIGHT / float(type_height)
        scale = max(0.25, min(4.0, scale))
        if wide * scale > DETECT_WIDEST:
            scale = DETECT_WIDEST / float(wide)
        # A margin all round, and height enough that a one-line strip is not
        # a sliver: the detector judges a line by the paper around it.
        margin = int(max(8, 0.6 * DETECT_TYPE_HEIGHT))
        scaled_w = max(8, int(round(wide * scale)))
        scaled_h = max(8, int(round(high * scale)))
        picture = cv2.resize(bgr, (scaled_w, scaled_h),
                             interpolation=cv2.INTER_AREA if scale < 1
                             else cv2.INTER_CUBIC)
        need_h = max(scaled_h + 2 * margin, int(scaled_w / 8))
        pad_top = (need_h - scaled_h) // 2
        canvas_h = int(math.ceil(need_h / 32.0) * 32)
        canvas_w = int(math.ceil((scaled_w + 2 * margin) / 32.0) * 32)
        canvas = np.full((canvas_h, canvas_w, 3), 255, dtype=np.uint8)
        canvas[pad_top:pad_top + scaled_h, margin:margin + scaled_w] = picture

        blob = (canvas.astype(np.float32) / 255.0 - np.array(MEAN, np.float32)) \
            / np.array(STD, np.float32)
        blob = blob.transpose(2, 0, 1)[np.newaxis]
        name = self.detector.get_inputs()[0].name
        with self._lock:
            chance = self.detector.run(None, {name: blob})[0][0, 0]

        found = []
        bitmap = (chance > DETECT_THRESHOLD).astype(np.uint8)
        contours, _ = cv2.findContours(bitmap * 255, cv2.RETR_LIST,
                                       cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours[:1000]:
            (cx, cy), (rw, rh), angle = cv2.minAreaRect(contour)
            if min(rw, rh) < 3:
                continue
            if _mean_inside(chance, cv2.boxPoints(((cx, cy), (rw, rh), angle))) \
                    < BOX_THRESHOLD:
                continue
            # Grown back out by the detector's own rule (PaddleOCR's unclip):
            # the found core of a line is narrower than its ink. Offsetting a
            # rectangle with round corners and boxing the result is the same
            # rectangle, grown by the offset on every side.
            grow = rw * rh * UNCLIP_RATIO / (2.0 * (rw + rh))
            if min(rw, rh) + 2 * grow < 5:
                continue
            corners = cv2.boxPoints(((cx, cy), (rw + 2 * grow, rh + 2 * grow),
                                     angle))
            corners[:, 0] = (corners[:, 0] - margin) / scale
            corners[:, 1] = (corners[:, 1] - pad_top) / scale
            corners[:, 0] = np.clip(corners[:, 0], 0, wide - 1)
            corners[:, 1] = np.clip(corners[:, 1], 0, high - 1)
            corners = _clockwise(corners)
            across = np.linalg.norm(corners[0] - corners[1])
            down = np.linalg.norm(corners[0] - corners[3])
            if across <= 3 or down <= 3:
                continue
            # Upright: a column rule or the edge of a photograph. A headline's
            # line is wide, and even one letter alone is nearly square.
            if across < UPRIGHT * down:
                continue
            found.append(corners)
        return _reading_order(found)

    # ------------------------------------------------------------- reading
    def read_lines(self, crops: list, which: str = "hin") -> list:
        """[(text, score, each letter's certainty)] for each cut-out line,
        read with one reader."""
        import cv2
        import numpy as np

        if not crops:
            return []
        reader, chars = self.readers[which]
        results = [("", 0.0, [])] * len(crops)
        order = sorted(range(len(crops)),
                       key=lambda i: crops[i].shape[1] / float(crops[i].shape[0]))
        name = reader.get_inputs()[0].name
        for start in range(0, len(order), 6):
            batch = order[start:start + 6]
            widest = max(320.0 / READ_HEIGHT,
                         max(crops[i].shape[1] / float(crops[i].shape[0])
                             for i in batch))
            span = int(READ_HEIGHT * widest)
            blob = np.zeros((len(batch), 3, READ_HEIGHT, span), np.float32)
            for row, i in enumerate(batch):
                crop = crops[i]
                width = min(span, int(math.ceil(READ_HEIGHT * crop.shape[1]
                                                / float(crop.shape[0]))))
                line = cv2.resize(crop, (max(1, width), READ_HEIGHT))
                line = line.astype(np.float32).transpose(2, 0, 1) / 255.0
                blob[row, :, :, :width] = (line - 0.5) / 0.5
            with self._lock:
                chances = reader.run(None, {name: blob})[0]
            for row, i in enumerate(batch):
                results[i] = _decode(chances[row], chars)
        return results

    def read(self, bgr, type_height: float = 0.0) -> list:
        """Every line in the picture, found and read, in reading order."""
        import numpy as np

        corners = self.find_lines(bgr, type_height)
        if not corners:
            return []
        crops = [_straightened(bgr, points) for points in corners]
        hindi = self.read_lines(crops, "hin")
        english_wanted = [i for i, (text, _s, _l) in enumerate(hindi)
                          if _mostly_latin(text)]
        english = dict(zip(english_wanted,
                           self.read_lines([crops[i] for i in english_wanted],
                                           "eng")))
        lines = []
        for i, points in enumerate(corners):
            text, score, sure = hindi[i]
            if i in english and english[i][1] >= score:
                text, score, sure = english[i]
            xs, ys = points[:, 0], points[:, 1]
            box = (int(xs.min()), int(ys.min()), int(math.ceil(xs.max())),
                   int(math.ceil(ys.max())))
            tall = float(min(np.linalg.norm(points[0] - points[3]),
                             np.linalg.norm(points[1] - points[2])))
            lines.append(Line(box, text, float(score), tall,
                              points.tolist(), list(sure)))
        return [line for line in lines if line.text.strip()]


def _decode(chances, chars) -> tuple:
    """PaddleOCR's CTC decoding: the likeliest class at each step, repeats
    folded, blanks dropped; the certainty is the mean over the letters kept.
    (text, certainty, each letter's certainty)"""
    import numpy as np

    best = chances.argmax(axis=1)
    sure = chances.max(axis=1)
    keep = np.ones(len(best), dtype=bool)
    keep[1:] = best[1:] != best[:-1]
    keep &= best != 0
    letters, each = [], []
    for k, p in zip(best[keep], sure[keep]):
        letter = chars[k] if k < len(chars) else ""
        letters.append(letter)
        each += [float(p)] * len(letter)
    certainty = float(sure[keep].mean()) if keep.any() else 0.0
    return "".join(letters), certainty, each


def _mean_inside(chance, corners) -> float:
    """The detector's average over the inside of a box (PaddleOCR's 'fast')."""
    import cv2
    import numpy as np

    high, wide = chance.shape[:2]
    box = corners.copy()
    x0 = int(np.clip(np.floor(box[:, 0].min()), 0, wide - 1))
    x1 = int(np.clip(np.ceil(box[:, 0].max()), 0, wide - 1))
    y0 = int(np.clip(np.floor(box[:, 1].min()), 0, high - 1))
    y1 = int(np.clip(np.ceil(box[:, 1].max()), 0, high - 1))
    mask = np.zeros((y1 - y0 + 1, x1 - x0 + 1), dtype=np.uint8)
    box[:, 0] -= x0
    box[:, 1] -= y0
    cv2.fillPoly(mask, box.reshape(1, -1, 2).astype(np.int32), 1)
    return cv2.mean(chance[y0:y1 + 1, x0:x1 + 1], mask)[0]


def _clockwise(points):
    """Top-left, top-right, bottom-right, bottom-left."""
    import numpy as np

    by_x = points[np.argsort(points[:, 0]), :]
    left, right = by_x[:2, :], by_x[2:, :]
    top_left, bottom_left = left[np.argsort(left[:, 1]), :]
    top_right, bottom_right = right[np.argsort(right[:, 1]), :]
    return np.array([top_left, top_right, bottom_right, bottom_left],
                    dtype=np.float32)


def _reading_order(found: list) -> list:
    """Top to bottom, and left to right along a line.

    Two boxes are on one line when they overlap by at least half the shorter
    one's height. The widest boxes are placed first - a line of type is wide:
    a speck of dust found between two lines once started a "line" of its
    own, took the first half of the next line into it and left its last word
    to a line after ("समस्याएं, रहा कार्य चल" for "समस्याएं, चल रहा कार्य");
    and a column rule, the tallest thing in the region, took both lines of a
    headline into one and put the second first.
    """
    if not found:
        return []
    rows = []
    for points in sorted(found, key=lambda p: -float(p[:, 0].max() - p[:, 0].min())):
        top, bottom = float(points[:, 1].min()), float(points[:, 1].max())
        for row in rows:
            shared = min(bottom, row["bottom"]) - max(top, row["top"])
            if shared >= 0.5 * min(bottom - top, row["bottom"] - row["top"]):
                row["members"].append(points)
                break
        else:
            rows.append({"top": top, "bottom": bottom, "members": [points]})
    ordered = []
    for row in sorted(rows, key=lambda r: r["top"]):
        ordered += sorted(row["members"], key=lambda p: float(p[:, 0].min()))
    return ordered


def _straightened(bgr, points):
    """A found line cut out square to the page (PaddleOCR's rotate-crop)."""
    import cv2
    import numpy as np

    wide = int(max(np.linalg.norm(points[0] - points[1]),
                   np.linalg.norm(points[2] - points[3])))
    high = int(max(np.linalg.norm(points[0] - points[3]),
                   np.linalg.norm(points[1] - points[2])))
    wide, high = max(1, wide), max(1, high)
    target = np.array([[0, 0], [wide, 0], [wide, high], [0, high]],
                      dtype=np.float32)
    turn = cv2.getPerspectiveTransform(points.astype(np.float32), target)
    return cv2.warpPerspective(bgr, turn, (wide, high),
                               borderMode=cv2.BORDER_REPLICATE,
                               flags=cv2.INTER_CUBIC)


def _mostly_latin(text: str) -> bool:
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    devanagari = sum(1 for ch in text if "ऀ" <= ch <= "ॿ")
    return latin >= 2 and latin > devanagari


# ----------------------------------------------------------------- one engine
_engine = None
_tried = False
_trouble = ""
_made = threading.Lock()


def engine():
    """The engine for this process, made on first use. None when it cannot be
    - no ONNX Runtime, or a model missing - and why_not() says why."""
    global _engine, _tried, _trouble
    if _tried:
        return _engine
    with _made:
        if _tried:
            return _engine
        try:
            missing = [name for name in (DETECTOR, HINDI, ENGLISH)
                       if not (MODELS / name).is_file()]
            if missing:
                _trouble = f"missing {', '.join(missing)} in {MODELS}"
            else:
                _engine = Engine()
        except Exception as exc:  # noqa: BLE001 - no engine is a state, not a fault
            _trouble = f"{type(exc).__name__}: {exc}"
            _engine = None
        _tried = True
    return _engine


def available() -> bool:
    return engine() is not None


def installed() -> bool:
    """Is there a PaddleOCR to read with - without opening it to find out?

    The reading's stamp names the engines, and it is written in the window's
    own process too, which never reads a clipping itself: opening the models
    there to write a name would cost half a second and a hundred megabytes.
    """
    if _tried:
        return _engine is not None
    import importlib.util

    try:
        return (importlib.util.find_spec("onnxruntime") is not None
                and all((MODELS / name).is_file()
                        for name in (DETECTOR, HINDI, ENGLISH)))
    except Exception:  # noqa: BLE001
        return False


def why_not() -> str:
    engine()
    return _trouble


def version() -> str:
    """What the reading stamp names this engine by."""
    try:
        import onnxruntime

        return f"paddleocr PP-OCRv5 (onnxruntime {onnxruntime.__version__})"
    except Exception:  # noqa: BLE001
        return "paddleocr PP-OCRv5"
