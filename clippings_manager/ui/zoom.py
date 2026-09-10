"""How big the whole application is drawn.

The office laptops are 1366x768. On a screen that size the cards, the list and
the footer together want more room than there is, and the answer people reach
for is "make it smaller so it all fits".

Making it smaller is harder than it sounds here, because most of what is on
screen is not made of widgets. The clipping cards are PAINTED - every size in
rowlayout.py and delegates.py is a number of pixels, not a font. Changing the
application font moves nothing: measured, raising it from 10pt to 14pt left the
window's minimum size, the footer height, the buttons and the list rows all
byte-identical, because the stylesheet pins sizes in px and Qt resets item views
to the platform font anyway.

The one thing that scales all of it - widgets, stylesheet pixels, painted cards,
icons and thumbnails alike - is Qt's own display scale, because it works below
the layout: everything above it goes on thinking in the same logical pixels.
Measured on an 800px-tall screen: at 0.75 the application sees 1067px of height,
at 1.25 it sees 640px.

The catch is that Qt reads it once, when the application object is made, and
offers no way to change it afterwards. So the buttons write the choice down and
start the application again. That is why this file only stores a number - the
restart lives in main_window, where the session can be saved first, and the
session comes back on its own when the application returns.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# The sizes offered. 0.70 and 0.75 both fit a 1366x768 screen; 1.30 is for
# somebody on a large monitor who wants the Hindi bigger.
#
# 0.75 is here because it was asked for and was not reachable: the list ran
# 0.70, 0.80, and there is a real difference between them on a small laptop.
# The steps are uneven on purpose - close together where the small screens are,
# further apart above 100% where a step has to be worth a restart to be worth
# offering at all.
LEVELS = (0.70, 0.75, 0.80, 0.90, 1.00, 1.15, 1.30)
NORMAL = 1.00

# The environment variable Qt reads at startup. Set before QApplication exists
# or it does nothing at all.
VARIABLE = "QT_SCALE_FACTOR"


def _where() -> Path:
    """Beside the other settings, so an update never wipes it."""
    from .export_dialog import settings_dir

    return settings_dir() / "display.json"


def level() -> float:
    """The size the application was last set to."""
    try:
        data = json.loads(_where().read_text(encoding="utf-8"))
        asked = float(data.get("zoom", NORMAL))
    except Exception:  # noqa: BLE001 - no setting means the normal size
        return NORMAL
    return asked if 0.5 <= asked <= 2.0 else NORMAL


def remember(value: float) -> None:
    try:
        _where().write_text(json.dumps({"zoom": round(float(value), 3)}),
                            encoding="utf-8")
    except Exception:  # noqa: BLE001 - not being able to save is not fatal
        pass


def step(current: float, by: int) -> float:
    """The next size up or down the list, stopping at either end."""
    closest = min(range(len(LEVELS)), key=lambda i: abs(LEVELS[i] - current))
    return LEVELS[max(0, min(len(LEVELS) - 1, closest + by))]


def apply_to_environment() -> float:
    """Tell Qt what size to draw at. Call BEFORE making the QApplication.

    Returns the size applied, so the caller can say so if it wants to.

    **It assigns; it does not fall back.** This used to be ``setdefault``, on the
    reasoning that somebody who had set the variable by hand should keep it - and
    that quietly broke the buttons after the first press. Changing the size
    starts the application again, and a child process inherits its parent's
    environment: the second copy therefore started with the FIRST copy's
    QT_SCALE_FACTOR already set, ``setdefault`` left it alone, and every change
    after the first one did nothing at all. The percentage in the header moved
    and the window did not, which is exactly what was reported.

    Clearing it when the size is normal matters for the same reason: going back
    to 100% has to remove an inherited 0.70, not merely decline to overwrite it.
    """
    asked = level()
    if abs(asked - NORMAL) > 0.001:
        os.environ[VARIABLE] = f"{asked:.3f}"
    else:
        os.environ.pop(VARIABLE, None)
    return asked


def as_percent(value: float) -> str:
    return f"{round(value * 100):d}%"
