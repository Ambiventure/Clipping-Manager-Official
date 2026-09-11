"""Colour tokens, fonts and the application stylesheet.

Follows the palette of the AI Studio build this replaces: a dark slate header with
an orange accent edge, navy as the primary action colour, orange as the highlight,
and a near-white working ground so newspaper clippings read as sheets of paper.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QPainter,
    QPixmap,
)

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
ICONS = Path(__file__).resolve().parent.parent / "assets" / "icon"


def app_icon_path(name: str = "icon.png") -> str:
    """The application's own badge, or "" when it has not been generated.

    Built from the artwork by tools/make_icon.py, which cuts the round logo out
    and drops the square background - a white corner around a round mark looks
    like a mistake on a taskbar.
    """
    path = ICONS / name
    return str(path) if path.exists() else ""

# --- brand ------------------------------------------------------------------
NAVY = "#122A52"
NAVY_HOVER = "#1B3B6F"
NAVY_WASH = "#EEF2FA"
NAVY_SELECT = "#F0F5FF"
ORANGE = "#E8792F"
ORANGE_HOVER = "#D56820"
ORANGE_DEEP = "#C55E1A"
ORANGE_WASH = "#FFF4EC"

# --- neutrals ---------------------------------------------------------------
INK = "#1A1F2B"
MUTED = "#6B7280"
FAINT = "#9CA3AF"
HAIRLINE = "#E3E6EC"
HAIRLINE_STRONG = "#CBD5E1"
SURFACE = "#FFFFFF"
CANVAS = "#F4F6FB"
PANEL = "#FAFBFD"
THUMB_BG = "#F8FAFC"

# --- status -----------------------------------------------------------------
GREEN = "#1D8A5E"
GREEN_WASH = "#E9F7F0"
RED = "#C23A2E"
RED_WASH = "#FCEAE8"
DANGER = "#DC2626"
FLAG = "#B8730A"
FLAG_WASH = "#FBF3E7"

# --- the crown ---------------------------------------------------------------
# One dark band, and only one. The top bar is the window frame - it never
# scrolls, it names the organisation, it belongs to the application rather than
# to the document. Everything below it is furniture inside a scrolling page and
# is light. Five stacked dark bands were the actual complaint; the shade of any
# one of them was not.
HEADER_B = "#22385C"          # the crown itself, 4.5x lighter than the old void
CROWN_WELL = "#1B3057"        # a group of controls, sunk into the crown
CROWN_RAISED = "#2E4877"      # controls sitting on the crown
CROWN_HOVER = "#3A5691"
# Collect from WhatsApp, switched on: white on this green is 7.13:1, and the
# light green edge stands out 8.36:1 against the crown.
COLLECT_ON = "#166534"
COLLECT_ON_LINE = "#86EFAC"
CROWN_SUB = "#D7E1F2"         # secondary text on the crown
CROWN_DIM = "#B3C2DC"         # tertiary text on the crown
CROWN_AMBER = "#FDBA74"       # the crown's orange, readable where ORANGE is not
SLATE_LINE = "#4A6698"
SLATE_TEXT = CROWN_SUB

# --- light chrome ------------------------------------------------------------
NAVY_BAND = "#DFE8F6"         # identity bands that used to be black
NAVY_BAND_LINE = "#AEBFDE"
# Brand ORANGE is 2.9:1 on white and cannot legally carry text. This is the ink
# version: still orange, but readable on every light ground we use.
ORANGE_INK = "#9A4A0F"
SLATE_TEXT_LIGHT = "#4C5A72"  # one grey for secondary text on light chrome

# --- preview.py viewport only - never chrome ---------------------------------
# A newspaper scan is a near-white rectangle; the dark surround is a lighting
# decision about the artefact, not part of the interface. The viewer is modal,
# so it never stacks with anything and cannot contribute to the pile-up above.
DARK_PANEL = "#1E293B"
SLATE_INK = "#E2E8F0"          # text on the slate panels; 11.87:1 on DARK_PANEL
SLATE_EDGE = "#33415A"         # their hairline
DARK_BAR = "#0F172A"
DARK_VIEWPORT = "#0A0F1D"

# --- sentiment columns ------------------------------------------------------
# Each column gets a strong colour for its header and accents, a very light fill
# for the column body, a border, and a darker text colour for the count badge.
SENTIMENT_STYLES = {
    "Positive": {"label": "Positive", "hindi": "सकारात्मक", "sign": "+",
                 "colour": "#16A34A", "bg": "#F0FDF4", "line": "#BBF7D0",
                 "badge": "#15803D"},
    "Neutral":  {"label": "Neutral", "hindi": "तटस्थ", "sign": "●",
                 "colour": "#2563EB", "bg": "#EFF6FF", "line": "#BFDBFE",
                 "badge": "#1D4ED8"},
    "Negative": {"label": "Negative", "hindi": "नकारात्मक", "sign": "−",
                 "colour": "#DC2626", "bg": "#FEF2F2", "line": "#FECACA",
                 "badge": "#B91C1C"},
    "Digital":  {"label": "Digital News", "hindi": "डिजिटल न्यूज़", "sign": "🌐",
                 "colour": "#7C3AED", "bg": "#FAF5FF", "line": "#E9D5FF",
                 "badge": "#6D28D9"},
}

# --- source badges ----------------------------------------------------------
SOURCE_STYLES = {
    "word":      {"label": "Word",      "fg": "#1E40AF", "bg": "#DBEAFE", "line": "#93C5FD"},
    "pdf":       {"label": "PDF",       "fg": "#991B1B", "bg": "#FEE2E2", "line": "#FCA5A5"},
    "clipboard": {"label": "Clipboard", "fg": "#5B21B6", "bg": "#EDE9FE", "line": "#C4B5FD"},
    "image":     {"label": "Photo",     "fg": "#065F46", "bg": "#D1FAE5", "line": "#6EE7B7"},
    # The headings of a list that "Filter and arrange" has sorted - "Hindi",
    # "Dainik Jagran" - which are not files at all.
    "arranged":  {"label": "Sorted",    "fg": "#122A52", "bg": "#EEF2FA", "line": "#AFC0DD"},
}

# QColor shortcuts for the painters
QNAVY = QColor(NAVY)
QORANGE = QColor(ORANGE)
QINK = QColor(INK)
QMUTED = QColor(MUTED)
QFAINT = QColor(FAINT)
QHAIRLINE = QColor(HAIRLINE)
QHAIRLINE_STRONG = QColor(HAIRLINE_STRONG)
QSURFACE = QColor(SURFACE)
QCANVAS = QColor(CANVAS)
QTHUMB_BG = QColor(THUMB_BG)
QDANGER = QColor(DANGER)
QFLAG = QColor(FLAG)
QGREEN = QColor(GREEN)


# A combo's popup and a date field's calendar are children of their control, so any
# ancestor carrying an unqualified `background: transparent` repaints them black -
# and a widget's own stylesheet outranks every ancestor's. Pinning the rule on the
# control itself is therefore the only placement that cannot be undone from above.
COMBO_POPUP = (
    "QComboBox QAbstractItemView {"
    f" background: {SURFACE}; color: {INK};"
    f" border: 1px solid {HAIRLINE_STRONG}; border-radius: 10px;"
    f" selection-background-color: {NAVY_SELECT}; selection-color: {NAVY};"
    " outline: none; padding: 4px; }"
)

# The interface switch is the only combo left on a dark ground. Its selected
# row was orange under white text at 2.9:1 - unreadable exactly when it mattered.
COMBO_POPUP_DARK = (
    "QComboBox QAbstractItemView {"
    f" background: {CROWN_RAISED}; color: {CROWN_SUB};"
    f" border: 1px solid {SLATE_LINE}; border-radius: 10px;"
    f" selection-background-color: {CROWN_HOVER}; selection-color: white;"
    " outline: none; padding: 4px; }"
)

# The slate popups on the preview window's dark detail panel. Named here
# rather than written by hand where they are used, because the one place that
# hand-rolled its own - preview.py - is the one that got it wrong: it set a
# selection background and no selection colour, and the pen fell through to the
# near-black NAVY meant for near-white rows. Measured at 1.03:1.
#
# CROWN_HOVER is the selection fill on purpose. It is the only candidate that is
# both readable under white text AND visible as a highlight against the popup:
#   CROWN_HOVER   7.19:1 text, 2.03:1 against the ground
#   CROWN_RAISED  9.09:1 text, 1.61:1 against the ground
#   NAVY         14.20:1 text, 1.03:1 against the ground - invisible as a fill
COMBO_POPUP_SLATE = (
    "QComboBox QAbstractItemView {"
    f" background: {DARK_PANEL}; color: {SLATE_INK};"
    f" border: 1px solid {SLATE_EDGE}; border-radius: 8px;"
    f" selection-background-color: {CROWN_HOVER}; selection-color: #FFFFFF;"
    " outline: none; padding: 3px; }"
    "QComboBox QAbstractItemView::item {"
    f" padding: 5px 8px; color: {SLATE_INK};"
    " border: none; border-radius: 5px; }"
    "QComboBox QAbstractItemView::item:selected {"
    f" background: {CROWN_HOVER}; color: #FFFFFF; }}"
    "QComboBox QAbstractItemView::item:hover {"
    f" background: {CROWN_RAISED}; color: #FFFFFF; }}"
)

# The name-suggestion popup is a top-level QListView with NO PARENT, so no
# "QComboBox QAbstractItemView" selector reaches it - here or in any theming
# library. It has to be styled on the widget itself, which is what _fill does.
COMPLETER_POPUP_SLATE = (
    "QListView {"
    f" background: {DARK_PANEL}; color: {SLATE_INK};"
    f" border: 1px solid {SLATE_EDGE}; border-radius: 8px;"
    f" selection-background-color: {CROWN_HOVER}; selection-color: #FFFFFF;"
    " outline: none; padding: 3px; }"
    "QListView::item {"
    f" padding: 5px 8px; color: {SLATE_INK}; border-radius: 5px; }}"
    "QListView::item:selected {"
    f" background: {CROWN_HOVER}; color: #FFFFFF; }}"
)

CALENDAR_POPUP = (
    "QCalendarWidget QAbstractItemView {"
    f" background: {SURFACE}; color: {INK};"
    f" selection-background-color: {NAVY}; selection-color: white;"
    " outline: none; }"
    f"QCalendarWidget QWidget {{ background: {SURFACE}; color: {INK}; }}"
    "QCalendarWidget QWidget#qt_calendar_navigationbar {"
    f" background: {NAVY_WASH}; }}"
    f"QCalendarWidget QToolButton {{ color: {NAVY}; background: transparent;"
    " border: none; padding: 4px 8px; font-weight: 700; }"
    f"QCalendarWidget QToolButton:hover {{ background: {NAVY_SELECT}; }}"
)


def load_fonts() -> str:
    """Register bundled fonts and return the UI family name."""
    families: list[str] = []
    if ASSETS.is_dir():
        # Regular and Bold, and nothing else. Noto ships thirty-eight files -
        # nine weights across four widths - and registering them all gives Qt
        # "Noto Sans Devanagari Black" and "... ExtraLight" as families it may
        # pick from. These two are also exactly what the packaged build carries,
        # so running from source and running the executable behave the same,
        # which is the whole point of bundling a font in the first place.
        wanted = [
            path for path in
            sorted(ASSETS.glob("*.tt[fc]")) + sorted(ASSETS.glob("*.otf"))
            if path.stem.endswith(("-Regular", "-Bold"))
            and not any(word in path.stem
                        for word in ("Condensed", "Italic", "VariableFont"))
        ]
        for path in wanted:
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id >= 0:
                families.extend(QFontDatabase.applicationFontFamilies(font_id))

    installed = set(QFontDatabase.families())
    for candidate in ("Noto Sans", "Inter", "Segoe UI Variable", "Segoe UI"):
        if candidate in families or candidate in installed:
            return candidate
    return QFont().defaultFamily()


# The three that are preferred when present, in this order. They are a
# preference, not the test - the test is whether a font covers Devanagari.
PREFERRED_DEVANAGARI = ("Noto Sans Devanagari", "Nirmala UI", "Mangal")


def devanagari_family() -> str:
    """A family that covers Devanagari, so mastheads never render as tofu.

    This used to match three names exactly and answer "none" for anything else,
    so a machine carrying Aparajita, Kokila, Utsaah, Sanskrit Text or Adobe
    Devanagari - any of which sets Hindi perfectly well - was treated as having
    no Devanagari at all. Qt already knows which writing systems a family
    covers; asking it is both shorter and right.
    """
    installed = set(QFontDatabase.families())
    for candidate in PREFERRED_DEVANAGARI:
        if candidate in installed:
            return candidate
    for family in sorted(installed):
        try:
            systems = QFontDatabase.writingSystems(family)
        except Exception:  # noqa: BLE001 - a font Qt cannot inspect is no use
            continue
        if QFontDatabase.WritingSystem.Devanagari in systems:
            return family
    return ""


STYLESHEET = f"""
QWidget {{ background: {CANVAS}; color: {INK}; }}
QMainWindow, QDialog {{ background: {CANVAS}; }}
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}

/* ------------------------------------------------------------- dark header */
#Header {{ background: {HEADER_B}; }}
#HeaderAccent {{ background: {ORANGE}; }}
#AppName {{ color: #FFFFFF; font-size: 19px; font-weight: 800; }}
#AppTagline {{ color: {SLATE_TEXT}; font-size: 12px; }}
#HeaderRule {{ background: {SLATE_LINE}; }}
#HeaderHint {{ color: {CROWN_DIM}; font-size: 11px; }}
/* These three were translucent over the old near-black. Over the lighter crown
   the same alpha composites to a brown-grey, so they are opaque now. */
#Badge {{
    color: {CROWN_AMBER}; font-size: 10px; font-weight: 700;
    background: {CROWN_RAISED}; border: 1px solid #F5A15E;
    border-radius: 9px; padding: 2px 8px;
}}
#BadgeBlue {{
    color: #93C5FD; font-size: 10px; font-weight: 700;
    background: {CROWN_RAISED}; border: 1px solid #60A5FA;
    border-radius: 9px; padding: 2px 8px;
}}
#Logo {{
    background: {CROWN_RAISED}; border: 1px solid {SLATE_LINE};
    border-radius: 10px;
}}
QPushButton#HeaderButton {{
    background: {CROWN_RAISED}; border: 1px solid {SLATE_LINE};
    border-radius: 10px; padding: 8px 13px; color: {CROWN_SUB}; font-size: 12px;
    font-weight: 600;
}}
QPushButton#HeaderButton:hover {{
    background: {CROWN_HOVER}; border-color: {ORANGE}; color: #FFFFFF;
}}
QPushButton#HeaderButton:checked {{
    background: {COLLECT_ON}; border: 1px solid {COLLECT_ON_LINE}; color: #FFFFFF;
}}
/* Brand ORANGE is only 4.0:1 on the crown and this is 10px text. */
#ModeLabel {{
    color: {CROWN_AMBER}; font-size: 10px; font-weight: 800; letter-spacing: .06em;
}}
QComboBox#ModeSwitch {{
    background: {CROWN_RAISED}; border: 1px solid {SLATE_LINE}; border-radius: 9px;
    padding: 7px 12px; color: #FFFFFF; font-size: 12px; font-weight: 700;
    min-width: 250px;
}}
QComboBox#ModeSwitch:hover {{
    background: {CROWN_HOVER}; border-color: {ORANGE};
}}
QComboBox#ModeSwitch::drop-down {{ border: none; width: 22px; }}
QComboBox#ModeSwitch QAbstractItemView {{
    background: {CROWN_RAISED}; color: {CROWN_SUB}; border: 1px solid {SLATE_LINE};
    selection-background-color: {CROWN_HOVER}; selection-color: white; padding: 4px;
}}

/* The division band, demoted to light. The navy rail on its left edge is
   load-bearing, not ornament: the fill is only 1.14:1 against the canvas, so
   without the rail the bar dissolves into the page. */
#DivisionBar {{
    background: {NAVY_BAND}; border: 1px solid {NAVY_BAND_LINE};
    border-radius: 16px;
}}
#DivisionRail {{ background: {NAVY}; border-radius: 2px; }}
#DivisionName {{ color: {NAVY}; font-size: 15px; font-weight: 700; }}
#DivisionCode {{ color: {ORANGE_INK}; font-size: 13px; font-weight: 800; }}
#DivisionHindi {{ color: {SLATE_TEXT_LIGHT}; font-size: 12px; }}
#DivisionLead {{
    color: #1B3B6F; font-size: 10px; font-weight: 700; letter-spacing: .06em;
}}
QComboBox#DivisionPick {{
    background: {SURFACE}; border: 1px solid {HAIRLINE_STRONG}; border-radius: 8px;
    padding: 6px 11px; color: {INK}; font-size: 12px; font-weight: 600;
    min-width: 260px;
}}
QComboBox#DivisionPick:hover {{ border-color: {NAVY}; }}

/* --------------------------------------------------------------- card body */
#Card {{
    background: {SURFACE}; border: 1px solid {HAIRLINE}; border-radius: 16px;
}}
#StepNumber {{
    background: {NAVY}; color: white; border-radius: 12px;
    font-size: 11px; font-weight: 700;
}}
#CardTitle {{ font-size: 15px; font-weight: 700; color: {INK}; }}
#CountPill {{
    color: {ORANGE}; background: {ORANGE_WASH}; border-radius: 9px;
    padding: 2px 9px; font-size: 11px; font-weight: 700;
}}
#CardHint {{ color: {MUTED}; font-size: 12px; }}
#SubtleHint {{ color: {MUTED}; font-size: 11px; }}

/* --------------------------------------------------------------- dropzone */
#DropZone {{
    background: {PANEL}; border: 2px dashed {HAIRLINE_STRONG}; border-radius: 16px;
}}
#DropZone[hot="true"] {{ background: {ORANGE_WASH}; border-color: {ORANGE}; }}

/* ---------------------------------------------------------------- buttons */
QPushButton {{
    background: {SURFACE}; border: 1px solid {HAIRLINE_STRONG}; border-radius: 11px;
    padding: 8px 14px; font-size: 12px; font-weight: 600; color: {INK};
}}
QPushButton:hover {{ background: {NAVY_WASH}; border-color: {NAVY}; }}
QPushButton:disabled {{ color: {FAINT}; border-color: {HAIRLINE}; background: {SURFACE}; }}

QPushButton#NavyFilled {{
    background: {NAVY}; border: 1px solid {NAVY}; color: white; font-weight: 700;
}}
QPushButton#NavyFilled:hover {{ background: {NAVY_HOVER}; border-color: {NAVY_HOVER}; }}
QPushButton#NavyOutline {{
    background: {SURFACE}; border: 2px solid {NAVY}; color: {NAVY}; font-weight: 700;
}}
QPushButton#NavyOutline:hover {{ background: {NAVY_WASH}; }}
QPushButton#OrangeOutline {{
    background: {SURFACE}; border: 2px solid {ORANGE}; color: {ORANGE}; font-weight: 700;
}}
QPushButton#OrangeOutline:hover {{ background: {ORANGE_WASH}; }}
/* White on brand ORANGE is 2.9:1 - it never carried this text legibly. */
QPushButton#OrangeFilled {{
    background: {ORANGE_INK}; border: 1px solid {ORANGE}; color: white; font-weight: 700;
}}
QPushButton#OrangeFilled:hover {{ background: {ORANGE_DEEP}; border-color: {ORANGE_DEEP}; }}
QPushButton#OrangeFilled:disabled {{ background: #F0C4A4; border-color: #F0C4A4; color: #FFF3EA; }}
QPushButton#LinkDanger {{
    background: transparent; border: none; color: {DANGER}; font-weight: 600;
    padding: 4px 6px;
}}
QPushButton#LinkDanger:hover {{ color: #991B1B; background: #FEF2F2; }}
QPushButton#Quiet {{
    background: #F1F5F9; border: 1px solid {HAIRLINE}; border-radius: 8px;
    padding: 5px 10px; font-size: 11px; color: {NAVY};
}}
QPushButton#Quiet:hover {{ background: #E2E8F0; }}
QPushButton#LinkNavy {{
    background: transparent; border: none; color: {NAVY}; font-weight: 700;
    padding: 4px 2px; font-size: 12px;
}}
QPushButton#LinkNavy:hover {{ color: {ORANGE}; }}

/* ------------------------------------------------------------ status strip */
#StatusInfo {{
    background: {NAVY_WASH}; color: {NAVY}; border: 1px solid rgba(18,42,82,0.2);
    border-radius: 10px; padding: 9px 12px; font-size: 12px; font-weight: 600;
}}
#StatusGood {{
    background: {GREEN_WASH}; color: {GREEN}; border: 1px solid rgba(29,138,94,0.25);
    border-radius: 10px; padding: 9px 12px; font-size: 12px; font-weight: 600;
}}
#StatusBad {{
    background: {RED_WASH}; color: {RED}; border: 1px solid rgba(194,58,46,0.25);
    border-radius: 10px; padding: 9px 12px; font-size: 12px; font-weight: 600;
}}

/* ------------------------------------------------------------------- list */
QListView {{
    background: {CANVAS}; border: none; outline: none;
    selection-background-color: transparent;
}}
QListView::item {{ border: none; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: #C3CBD6; border-radius: 6px; min-height: 44px; margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: #A2ADBC; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* ------------------------------------------------------------- inline edit */
QLineEdit {{
    background: {SURFACE}; border: 1px solid {HAIRLINE}; border-radius: 11px;
    padding: 6px 10px; font-size: 12px; font-weight: 600; color: {INK};
    selection-background-color: {NAVY}; selection-color: white;
}}
QLineEdit:focus {{ border: 1px solid {NAVY}; }}
QComboBox {{
    background: {SURFACE}; border: 1px solid {HAIRLINE_STRONG}; border-radius: 11px;
    padding: 6px 10px; font-size: 12px; color: {INK};
}}
QComboBox:focus {{ border-color: {NAVY}; }}
QComboBox QAbstractItemView {{
    background: {SURFACE}; color: {INK};
    border: 1px solid {HAIRLINE_STRONG};
    selection-background-color: {NAVY_SELECT}; selection-color: {NAVY};
    outline: none; padding: 4px;
}}

/* Calendar popups are separate windows and were inheriting a transparent ground
   from an ancestor, which paints black behind near-black day numbers. */
QCalendarWidget QAbstractItemView {{
    background: {SURFACE}; color: {INK};
    selection-background-color: {NAVY}; selection-color: white;
    outline: none;
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {NAVY_WASH}; }}

/* A date field is a spin box, not a line edit, so none of the rules above
   reached it and it kept the bare native look. */
QDateEdit, QSpinBox, QDoubleSpinBox {{
    background: {SURFACE}; border: 1px solid {HAIRLINE_STRONG};
    border-radius: 11px; padding: 5px 9px; font-size: 12px;
    font-weight: 600; color: {INK};
}}
QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {NAVY}; }}
QDateEdit::drop-down {{ border: none; width: 20px; }}
QDateEdit::up-button, QDateEdit::down-button {{ width: 0; border: none; }}

QTextEdit {{
    background: {SURFACE}; border: 1px solid {HAIRLINE}; border-radius: 11px;
    padding: 6px 9px; font-size: 12px; color: {INK};
    selection-background-color: {NAVY}; selection-color: white;
}}
QTextEdit:focus {{ border: 1px solid {NAVY}; }}

QCheckBox {{ font-size: 12px; color: {INK}; spacing: 7px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 4px;
    border: 1.5px solid {HAIRLINE_STRONG}; background: {SURFACE};
}}
QCheckBox::indicator:hover {{ border-color: {NAVY}; }}
QCheckBox::indicator:checked {{
    background: {NAVY}; border: 1.5px solid {NAVY};
}}
QCheckBox::indicator:disabled {{ background: {PANEL}; border-color: {HAIRLINE}; }}

/* ---------------------------------------------------------------- footer */
#Footer {{ background: {SURFACE}; border-top: 1px solid {HAIRLINE}; }}
#FooterCount {{ color: {MUTED}; font-size: 12px; }}
#FooterCount b {{ color: {INK}; font-size: 15px; }}

/* ----------------------------------------------------------------- misc */
QToolTip {{
    background: {NAVY}; color: white; border: none; padding: 6px 9px;
    border-radius: 6px; font-size: 11px;
}}
QMenu {{
    background: {SURFACE}; border: 1px solid {HAIRLINE_STRONG}; border-radius: 12px;
    padding: 6px;
}}
QMenu::item {{ padding: 7px 14px; border-radius: 8px; font-size: 12px; }}
QMenu::item:selected {{ background: {NAVY_SELECT}; color: {NAVY}; }}
QMenu::separator {{ height: 1px; background: {HAIRLINE}; margin: 5px 8px; }}
QProgressDialog {{ background: {SURFACE}; }}
QProgressBar {{
    border: 1px solid {HAIRLINE}; border-radius: 5px; background: {PANEL};
    text-align: center; height: 9px;
}}
QProgressBar::chunk {{ background: {ORANGE}; border-radius: 4px; }}
"""


_icon_files: dict = {}


def icon_file(key: str, drawer: str, colour: str, size: int = 14,
              inset: float = 0.0) -> str:
    """One of the painted icons written to a file.

    A Qt stylesheet can only take an image by URL and there is no bundled asset
    to point at, so the icons the stylesheet needs are drawn once and cached.
    Returns "" before the GUI application exists - painting needs one - and each
    caller falls back to something that still reads correctly without it.
    """
    if key in _icon_files:
        return _icon_files[key]
    if QGuiApplication.instance() is None:
        return ""
    path = ""
    try:
        from . import icons

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        draw = getattr(icons, drawer, None)
        if draw is not None:
            draw(painter,
                 QRectF(inset, inset, size - inset * 2, size - inset * 2),
                 QColor(colour))
        painter.end()
        target = Path(tempfile.gettempdir()) / "ClippingsManager" / f"{key}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        if pixmap.save(str(target), "PNG"):
            path = str(target).replace("\\", "/")
    except Exception:  # noqa: BLE001 - callers degrade gracefully
        path = ""
    _icon_files[key] = path
    return path


def tick_icon() -> str:
    """The white tick for a checked box; without it the box is a filled navy
    square, which still reads as on."""
    return icon_file("tick", "check", "#FFFFFF", 15, inset=2.5)


def apply_font(widget) -> None:
    """Put the Devanagari fallback back on a widget the stylesheet stripped it from.

    Qt drops the application font's family LIST as soon as any stylesheet is in
    force: QStyleSheetStyle resets every item view to the platform system font,
    so a clipping list and a sentiment column were painting Hindi with a family
    chain of exactly ['Segoe UI']. It looked fine here only because Qt quietly
    merges in some other face per glyph when one exists on the machine - and on a
    machine where none does, that is the difference between a masthead and a row
    of empty boxes.

    Called on the views that show mastheads, after the stylesheet is applied.
    """
    from PySide6.QtGui import QGuiApplication

    deva = devanagari_family()
    if not deva:
        return
    font = widget.font()
    families = [f for f in font.families() if f] or [font.family()]
    if deva in families:
        return
    base = QGuiApplication.font().families() or []
    font.setFamilies([*families, *[f for f in base if f not in families], deva])
    widget.setFont(font)


def stylesheet() -> str:
    """The application stylesheet, plus the rules that need a drawn image.

    These are appended rather than baked into STYLESHEET because they can only
    be built once a GUI application exists to paint them.
    """
    rules = [STYLESHEET]

    tick = tick_icon()
    if tick:
        rules.append("QCheckBox::indicator:checked { image: url("
                     + tick + "); }")

    # Styling ::drop-down at all stops Qt drawing the native arrow, so the rule
    # and its replacement arrow have to arrive together or not at all.
    arrow = icon_file("chevron", "chevron_down", MUTED, 12, inset=1.0)
    if arrow:
        rules.append("QComboBox::drop-down { border: none; width: 22px; }")
        rules.append("QComboBox::down-arrow { image: url(" + arrow
                     + "); width: 11px; height: 11px; }")
        pale = icon_file("chevron_light", "chevron_down", SLATE_TEXT, 12,
                         inset=1.0)
        if pale:
            rules.append("QComboBox#ModeSwitch::down-arrow { image: url("
                         + pale + "); width: 11px; height: 11px; }")
    return "\n".join(rules)
