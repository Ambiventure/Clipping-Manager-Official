"""Where everything sits inside a row.

The rows are painted, not built from widgets, so paint and hit-testing have to agree
about geometry down to the pixel. Both ask this module, so a button is always
clickable exactly where it was drawn.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QRect

# --- clipping row -----------------------------------------------------------
# Space kept clear at the edges of every row: the curly bracket lives in the left
# inset, and the right inset stops a row sliding under the floating buttons.
LEFT_INSET = 16
RIGHT_INSET = 66

ROW_HEIGHT = 92
# A clipping that has both a headline and an address shows two boxes instead of
# one, and needs the room for the second. A clipping with one of them - which is
# most of them - is exactly as tall as it always was.
FIELD_HEIGHT = 32
FIELD_GAP = 6
ROW_HEIGHT_TWO = ROW_HEIGHT + FIELD_HEIGHT + FIELD_GAP
ROW_GAP = 8
CARD_RADIUS = 14
BRACKET_WIDTH = 26          # the curly-bracket spine down the left of a group
PAD = 12
CHECK = 20
GRIP_W = 18
INDEX_W = 22
THUMB = 64
ICON_BTN = 28
MOVE_BTN = 22

# --- group header -----------------------------------------------------------
GROUP_HEIGHT = 46
GROUP_GAP = 6


@dataclass
class Hit:
    """A clickable region inside a row."""

    name: str
    rect: QRect
    tooltip: str = ""


@dataclass
class RowGeometry:
    card: QRect
    check: QRect
    grip: QRect
    index: QRect
    thumb: QRect
    label: QRect
    sub: QRect
    # The address box. Empty when the clipping has no address, in which case
    # nothing is drawn there and nothing is clickable there either.
    url: QRect = field(default_factory=QRect)
    buttons: list[Hit] = field(default_factory=list)
    bracket: QRect = field(default_factory=QRect)

    def hits(self) -> list[Hit]:
        # The small buttons are tested first. The thumbnail and the caption are
        # large and elastic; on a narrow window they grow until they sit under
        # the buttons, and whichever region is tested first wins the click. Put
        # the big soft targets last and a squeezed row still deletes and rotates
        # where it says it does.
        return [
            *self.buttons,
            Hit("check", self.check, "Select this clipping"),
            Hit("grip", self.grip, "Drag to reorder"),
            Hit("thumb", self.thumb, "Open full size"),
            *([Hit("url", self.url,
                   "The address that prints under the image, as a link")]
              if not self.url.isNull() and self.url.isValid() else []),
            *([Hit("label", self.label,
                   "The headline that prints above the image")]
              if not self.label.isNull() and self.label.isValid() else []),
        ]


# The Add URL button on the sub-line. Small on purpose: it is an offer, not
# an instruction, and most clippings out of a division document never want
# an address at all.
ADD_URL_W = 76
ADD_URL_H = 17


def clip_row(option_rect: QRect, *, in_group: bool, is_last: bool,
             show_title: bool = True, show_url: bool = False,
             english: bool = False) -> RowGeometry:
    """Lay out one clipping row inside the rectangle Qt hands the delegate.

    A clipping shows the boxes it has something to put in: a headline, an
    address, or both. One with neither shows the headline box, because that is
    the one a person reaches for first. An empty box that can never be filled is
    only clutter, and on a list of 165 clippings it is a great deal of clutter.
    """
    frame = option_rect.adjusted(LEFT_INSET, 0, -RIGHT_INSET, 0)
    left = frame.left() + (BRACKET_WIDTH if in_group else 0)
    height = ROW_HEIGHT_TWO if (show_title and show_url) else ROW_HEIGHT
    card = QRect(
        left,
        frame.top(),
        frame.width() - (BRACKET_WIDTH if in_group else 0),
        height,
    )
    bracket = QRect(frame.left(), frame.top(), BRACKET_WIDTH, height)

    y_mid = card.center().y()
    x = card.left() + PAD

    check = QRect(x, y_mid - CHECK // 2, CHECK, CHECK)
    x += CHECK + 8

    grip = QRect(x, y_mid - 12, GRIP_W, 24)
    x += GRIP_W + 4

    index = QRect(x, y_mid - 8, INDEX_W, 16)
    x += INDEX_W + 8

    thumb = QRect(x, y_mid - THUMB // 2, THUMB, THUMB)
    x += THUMB + 12

    # --- right-hand action cluster, laid out from the right edge -----------
    right = card.right() - PAD
    buttons: list[Hit] = []

    def add(name: str, width: int, tooltip: str, height: int = ICON_BTN) -> None:
        nonlocal right
        rect = QRect(right - width, y_mid - height // 2, width, height)
        buttons.append(Hit(name, rect, tooltip))
        right = rect.left() - 6

    add("delete", ICON_BTN, "Delete this clipping")

    # 2x2 move pad: top / up over down / bottom
    pad_w, pad_h = MOVE_BTN * 2 + 6, MOVE_BTN * 2 + 6
    pad = QRect(right - pad_w, y_mid - pad_h // 2, pad_w, pad_h)
    buttons.append(Hit("movepad", pad, ""))
    cell = MOVE_BTN
    buttons.append(Hit("move_top", QRect(pad.left() + 2, pad.top() + 2, cell, cell),
                       "Move to the top"))
    buttons.append(Hit("move_up", QRect(pad.left() + 4 + cell, pad.top() + 2, cell, cell),
                       "Move up one"))
    buttons.append(Hit("move_down", QRect(pad.left() + 2, pad.top() + 4 + cell, cell, cell),
                       "Move down one"))
    buttons.append(Hit("move_bottom",
                       QRect(pad.left() + 4 + cell, pad.top() + 4 + cell, cell, cell),
                       "Move to the bottom"))
    right = pad.left() - 6

    add("rotate", ICON_BTN, "Rotate 90° clockwise")
    # Only on a card with Hindi or Punjabi in a field the report prints. A
    # caption typed into the headline box stays as typed, and this is the
    # button that reads it and writes it into the fields in English.
    if english:
        add("english", 78, "Put this card's Hindi into English")

    if not is_last:
        add("merge", 84, "Merge this clipping with the one below it")
    add("split", 74, "Split this image into two clippings")

    # --- the fields take what is left --------------------------------------
    label_left = thumb.right() + 12
    label_width = max(120, right - 10 - label_left)
    if not (show_title or show_url):
        show_title = True          # something has to be there to type into

    top = card.top() + (16 if not (show_title and show_url) else 14)
    label = QRect()
    url = QRect()
    if show_title:
        label = QRect(label_left, top, label_width, FIELD_HEIGHT)
        top = label.bottom() + FIELD_GAP
    if show_url:
        url = QRect(label_left, top, label_width, FIELD_HEIGHT)
        top = url.bottom() + FIELD_GAP
    sub = QRect(label_left, top - FIELD_GAP + 4, label_width, 16)

    # A clipping with no address box gets a small button to ask for one, on the
    # line under the fields. It used to be an item on a menu behind the card,
    # which is no use at all to somebody who has just pasted a screenshot of a
    # web page and is looking for somewhere to put the link - there was nothing
    # on the card to say an address box existed.
    for missing, name, tip in (
            (not show_url, "add_url",
             "Add the web address this clipping came from"),
            (not show_title, "add_title",
             "Add a headline to print above this clipping")):
        if not missing:
            continue
        add_rect = QRect(sub.left(), sub.top() - 1, ADD_URL_W, ADD_URL_H)
        buttons.append(Hit(name, add_rect, tip))
        sub = QRect(add_rect.right() + 8, sub.top(),
                    max(0, sub.width() - ADD_URL_W - 8), sub.height())

    return RowGeometry(
        card=card,
        check=check,
        grip=grip,
        index=index,
        thumb=thumb,
        label=label,
        sub=sub,
        url=url,
        buttons=buttons,
        bracket=bracket,
    )


@dataclass
class GroupGeometry:
    card: QRect
    grip: QRect
    check: QRect
    badge: QRect
    title: QRect
    count: QRect
    buttons: list[Hit] = field(default_factory=list)

    def hits(self) -> list[Hit]:
        # The title comes last so the buttons that sit on top of the same row
        # win the hit test; only the leftover width behaves as the title.
        return [
            Hit("group_grip", self.grip, "Drag the whole file"),
            Hit("group_check", self.check, "Select every clipping from this file"),
            *self.buttons,
            Hit("group_title", self.title.united(self.badge),
                "Show or hide this file's clippings"),
        ]


def group_row(option_rect: QRect, title_width: int) -> GroupGeometry:
    frame = option_rect.adjusted(LEFT_INSET, 0, -RIGHT_INSET, 0)
    card = QRect(frame.left(), frame.top(), frame.width(), GROUP_HEIGHT)
    y_mid = card.center().y()
    x = card.left() + 10

    grip = QRect(x, y_mid - 11, GRIP_W, 22)
    x += GRIP_W + 6
    check = QRect(x, y_mid - 9, 18, 18)
    x += 18 + 10
    badge = QRect(x, y_mid - 10, 74, 20)
    x += 74 + 10

    right = card.right() - 10
    buttons: list[Hit] = []

    def add(name: str, width: int, tooltip: str) -> None:
        nonlocal right
        rect = QRect(right - width, y_mid - 13, width, 26)
        buttons.append(Hit(name, rect, tooltip))
        right = rect.left() - 5

    add("group_collapse", 26, "Collapse or expand this file")
    add("group_delete", 26, "Delete every clipping from this file")
    add("group_bottom", 24, "Move this file to the bottom")
    add("group_down", 24, "Move this file down")
    add("group_up", 24, "Move this file up")
    add("group_top", 24, "Move this file to the top")
    add("group_rotate", 26, "Rotate every clipping in this file")

    count_w = 62
    count = QRect(right - count_w, y_mid - 9, count_w, 18)
    right = count.left() - 8

    title = QRect(x, y_mid - 9, max(80, right - x), 18)
    return GroupGeometry(
        card=card, grip=grip, check=check, badge=badge,
        title=title, count=count, buttons=buttons,
    )
