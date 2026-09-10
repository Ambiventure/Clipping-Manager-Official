"""The report date: picked from a calendar, never in the future, never spun.

Three things were wrong with the date fields, and all three are the same field
being a spin box underneath.

**The wheel.** A `QDateEdit` takes the mouse wheel and steps the day. The cards
sit on one long scrolling page, so scrolling down past the cover card moved the
pointer across the date field and quietly moved the report to another day. It is
the worst kind of bug: nothing looks wrong, the report builds happily, and the
wrong date is printed on the cover and written into every file name. The wheel
now goes to the page, which is where somebody turning it was looking.

**The calendar.** The field had a drop-down with no picture in it - the app's own
stylesheet blanked the spin buttons and left the drop-down bare - so there was
nothing on screen to say a calendar was a click away. It carries a calendar mark
now, drawn from the same set as every other icon in the application.

**The future.** Nothing stopped a date being set in the future, and a report
dated tomorrow is wrong in a way nobody notices until it has been sent. Any date
after today is refused and said out loud, and the builders check again on the way
out, because a date can also arrive from a saved session written on another day.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDate, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QDateEdit, QMessageBox, QPushButton

from . import icons, theme


def today() -> QDate:
    """Today, asked for every time.

    Never cached. The department starts before nine and the application is left
    open; a cached "today" would be yesterday by the next morning and would then
    refuse the date the report is actually for.
    """
    return QDate.currentDate()


def is_future(when) -> bool:
    """Whether this date is after today. Accepts a QDate or a datetime.date."""
    if when is None:
        return False
    if not isinstance(when, QDate):
        try:
            when = QDate(when.year, when.month, when.day)
        except Exception:  # noqa: BLE001 - not a date at all
            return False
    return when > today()


# ------------------------------------------------------------- calendar mark

_ICON_CACHE: dict = {}


def _calendar_file(size: int = 16) -> str:
    """A calendar glyph on disk, for the stylesheet to point at.

    Every other icon in the application is painted straight onto a widget, but a
    stylesheet can only name a file - and `QDateEdit::drop-down` is a stylesheet
    thing. So the same painter is run once into a PNG beside the settings, and
    the @2x copy beside it is what Qt picks up on a high-resolution screen.
    """
    if size in _ICON_CACHE:
        return _ICON_CACHE[size]
    try:
        from .export_dialog import settings_dir

        folder = settings_dir()
        target = folder / f"calendar_{size}.png"
        for scale, path in ((1, target),
                            (2, folder / f"calendar_{size}@2x.png")):
            edge = size * scale
            pixmap = QPixmap(edge, edge)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            icons.calendar(painter, QRectF(0, 0, edge, edge),
                           QColor(theme.NAVY))
            painter.end()
            pixmap.save(str(path), "PNG")
        _ICON_CACHE[size] = target.as_posix()
    except Exception:  # noqa: BLE001 - a bare drop-down, as before
        _ICON_CACHE[size] = ""
    return _ICON_CACHE[size]


def _sheet() -> str:
    """The calendar popup's colours, plus a calendar mark on the drop-down."""
    mark = _calendar_file()
    if not mark:
        return theme.CALENDAR_POPUP
    return (
        theme.CALENDAR_POPUP
        + "QDateEdit::drop-down { subcontrol-origin: padding;"
          " subcontrol-position: center right; width: 26px;"
          " border: none; padding-right: 4px;"
          f" image: url({mark}); }}"
        + "QDateEdit::drop-down:hover { background: transparent; }"
    )


# ------------------------------------------------------------------ the field


class DayEdit(QDateEdit):
    """A report date. Not spun by the wheel, and never in the future."""

    #: Shown when somebody picks a day that has not happened yet.
    FUTURE_TITLE = "That date has not happened yet"

    def __init__(self, parent=None, what: str = "report"):
        super().__init__(parent)
        self._what = what
        self._putting_back = False
        self.setCalendarPopup(True)
        self.setDisplayFormat("dd.MM.yyyy")
        self.setDate(today())
        self.setStyleSheet(_sheet())
        self.setToolTip(
            "Click the calendar to pick a date. The wheel does not change it, "
            "and a date after today is not accepted.")
        # Click-to-focus only. WheelFocus is the default for a spin box, and it
        # is what let the pointer merely passing over the field take the keyboard
        # as well as the wheel.
        self.setFocusPolicy(Qt.StrongFocus)
        # The ceiling. With it in place a future date can never be emitted, so
        # nothing connected to dateChanged - and nothing downstream of that -
        # can be handed one. Reverting after the fact raced the other handlers
        # and lost; see the module docstring.
        self.setMinimumDate(QDate(2000, 1, 1))
        self.raise_the_ceiling()

    # -- the ceiling ------------------------------------------------------
    def raise_the_ceiling(self) -> None:
        """Today, again. The application is left open overnight.

        A ceiling worked out when the window opened is yesterday's by the next
        morning, and would then refuse the date the report is actually for.
        """
        now = today()
        if self.maximumDate() != now:
            self.setMaximumDate(now)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt name
        self.raise_the_ceiling()
        super().showEvent(event)

    def focusInEvent(self, event) -> None:  # noqa: N802 - Qt name
        self.raise_the_ceiling()
        super().focusInEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt name
        # Covers the calendar button: the popup is built from the range, so the
        # range has to be right before it opens.
        self.raise_the_ceiling()
        super().mousePressEvent(event)

    def setDate(self, value) -> None:  # noqa: N802 - Qt name
        """Refuse a future date, and say so rather than clamping in silence.

        The ceiling above stops one being SET. This is how somebody finds out
        why - a date restored from a session written on another machine, or a
        Today pressed while the clock was wrong, would otherwise slide back to
        today with nothing on screen to explain it.
        """
        self.raise_the_ceiling()
        if is_future(value) and not self._putting_back:
            wanted = QDate(value)
            super().setDate(today())
            QTimer.singleShot(0, lambda: self._say_so(wanted))
            return
        super().setDate(value)

    # -- the wheel belongs to the page ------------------------------------
    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt name
        """Never step the date. Let whatever is underneath scroll instead.

        Ignoring rather than accepting is the whole trick: Qt then walks the
        event up to the parent, and the parent is the page.
        """
        event.ignore()

    # -- and the future belongs to nobody ---------------------------------
    def _say_so(self, wanted: QDate) -> None:
        QMessageBox.warning(
            self.window(), self.FUTURE_TITLE,
            f"{wanted.toString('dd.MM.yyyy')} is in the future, and a "
            f"{self._what} cannot be dated later than today.\n\n"
            f"The date has been put back to "
            f"{today().toString('dd.MM.yyyy')}.")


def today_button(edit: QDateEdit, name: str = "DateToday") -> QPushButton:
    """A button that puts the field back to today, in one press."""
    button = QPushButton("Today")
    button.setObjectName(name)
    button.setCursor(Qt.PointingHandCursor)
    button.setToolTip("Set the date to today")
    button.setStyleSheet(
        f"#{name} {{ background: transparent; border: none;"
        f" color: {theme.ORANGE_DEEP}; font-size: 10px; font-weight: 800; }}"
        f"#{name}:hover {{ color: {theme.ORANGE}; }}"
    )
    button.clicked.connect(lambda: edit.setDate(today()))
    return button


# --------------------------------------------------------- the strict rule


def refuse_future(parent, when, what: str = "report") -> bool:
    """True when this date may be built. Says why, and returns False, when not.

    The fields refuse a future date as it is typed, and this is the second
    check, on the way out. A date does not only come from a field: a session
    saved yesterday evening is restored this morning carrying yesterday's
    choice, the clock on a machine can be wrong and then corrected, and the
    dossier takes its date from a different card than the newspad does. This is
    the one place every finished file passes through.
    """
    if not is_future(when):
        return True
    stamp = when.strftime("%d.%m.%Y") if hasattr(when, "strftime") else str(when)
    QMessageBox.warning(
        parent, DayEdit.FUTURE_TITLE,
        f"The {what} is dated {stamp}, which is in the future.\n\n"
        f"Nothing was built. Set the date to today or earlier and try again.")
    return False
