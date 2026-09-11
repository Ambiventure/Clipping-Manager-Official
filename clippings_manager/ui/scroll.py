"""A scroll area that tells the truth about how big its contents are.

QScrollArea's own size hint is capped at 24 line heights, so a card placed inside
one is pinned to about 312px however tall the window is. Reporting the widget's
real hint instead lets the cards take their natural size when there is room and
scroll when there is not - which is what keeps the window freely resizable however
tall the cards grow.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QSize,
    Qt,
    QVariantAnimation,
)
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFrame,
    QScrollArea,
    QScrollBar,
    QSizePolicy,
    QWidget,
)


class CardScroll(QScrollArea):
    """Scrolls a stack of cards without imposing their height on the window."""

    def __init__(self, name: str, inner: QWidget, parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        # AsNeeded, not AlwaysOff. With widgetResizable(True) the inner widget is
        # sized to max(viewport, its own minimum), so anything that genuinely
        # cannot shrink further was simply amputated at the viewport edge - no
        # scrollbar, no cue, and a button cut in half cannot be clicked. The cards
        # are made to shrink properly elsewhere; this is the net underneath, so a
        # control can never again be somewhere the mouse cannot go.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        # Scoped: an unqualified rule here would be inherited by every card
        # inside, and by their combo popups.
        self.setStyleSheet(f"#{name} {{ background: transparent; border: none; }}")
        self.setWidget(inner)
        self.verticalScrollBar().setSingleStep(WHEEL_PIXELS // 2)
        smooth(self)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt name
        inner = self.widget()
        if inner is None:
            return super().sizeHint()
        hint = inner.sizeHint()
        frame = 2 * self.frameWidth()
        return QSize(hint.width() + frame, hint.height() + frame)

    def event(self, event) -> bool:  # noqa: N802 - Qt name
        # A QScrollArea swallows its child's LayoutRequest: it resizes the inner
        # widget to the viewport and never tells its own parent layout that the
        # hint moved. Without this, collapsing a card never gives its height
        # back - the viewport keeps its old size and widgetResizable stretches
        # the contents to fill it again, so the card that just shrank is handed
        # the space straight back and centres its header in 450px of white.
        if event.type() == QEvent.LayoutRequest:
            self.updateGeometry()
        return super().event(event)


class WideScroll(CardScroll):
    """As wide as it needs to be, and exactly as tall as its contents.

    The sentiment board is one document scrolled by one wheel, top to bottom.
    Its set-up half, though, will not shrink sideways below about 1760px - the
    cover designer, the division bar and the layout strip each want their own
    width, and between them they would put that floor under the whole window on
    a 1366x768 laptop.

    A plain scroll area solves the width and breaks the scrolling: it takes a
    vertical scrollbar of its own, and then the wheel does one thing over the
    set-up and another over the columns, which is the section-wise scrolling
    this is meant to be rid of.

    So this one never scrolls vertically. It reports its contents' full height
    as its own, so the page above it is as tall as everything on it and the one
    vertical scrollbar belongs to the page. Sideways it scrolls as needed, which
    is the net under a set-up that is wider than the window.
    """

    def __init__(self, name: str, inner: QWidget, parent=None):
        super().__init__(name, inner, parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Fixed vertically: the layout then hands it exactly the height it asks
        # for - its contents' height - rather than stretching it and giving it
        # somewhere to scroll.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def _tall_enough(self) -> int:
        inner = self.widget()
        if inner is None:
            return super().sizeHint().height()
        bar = self.horizontalScrollBar()
        extra = bar.sizeHint().height() if bar.isVisible() else 0
        return inner.sizeHint().height() + extra + 2 * self.frameWidth()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt name
        return QSize(super().sizeHint().width(), self._tall_enough())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt name
        # Narrow is allowed; short is not. Anything taller than this and the
        # bottom of the set-up would be cut off with no way to reach it.
        return QSize(QScrollArea.minimumSizeHint(self).width(),
                     self._tall_enough())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt name
        super().resizeEvent(event)
        # The sideways scrollbar appearing changes how tall this has to be.
        self.updateGeometry()


class SideScroll(QScrollArea):
    """Scrolls a row of columns sideways without giving up its own height.

    A plain QScrollArea reports almost no minimum height, so placed beside a card
    stack that wants 768px it was handed 84px and the sentiment columns vanished
    to four coloured headers. Reporting the row's real minimum height keeps the
    columns their proper size and lets the cards above scroll instead.
    """

    def __init__(self, name: str, inner: QWidget, parent=None,
                 *, min_height: int = 0):
        super().__init__(parent)
        self.setObjectName(name)
        self._min_height = min_height
        # Not widgetResizable: Qt keeps the inner widget at its own height hint,
        # which left the bottom 104px of every column outside a viewport that has
        # no vertical scrollbar - painted, and past every mouse coordinate. The
        # size is managed below instead, where the rule can be stated plainly:
        # as wide as it needs, exactly as tall as the viewport.
        self.setWidgetResizable(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(f"#{name} {{ background: transparent; border: none; }}")
        self.setWidget(inner)
        self._fit_inner()
        self.horizontalScrollBar().setSingleStep(WHEEL_PIXELS // 2)
        smooth(self, Qt.Horizontal)

    def _bar_room(self) -> int:
        bar = self.horizontalScrollBar()
        return bar.sizeHint().height() if bar is not None else 0

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt name
        inner = self.widget()
        if inner is None:
            return super().minimumSizeHint()
        # Width may be anything - that is what the sideways scrolling is for.
        # Height is the row's own minimum and no more: asking for a whole card
        # here would put that card into the *window's* minimum height and stop it
        # fitting a 768px laptop screen. The claim on space goes in sizeHint.
        return QSize(120, inner.minimumSizeHint().height() + self._bar_room())

    # -- the inner widget is sized here, not by Qt -------------------------
    def _fit_inner(self) -> None:
        inner = self.widget()
        if inner is None:
            return
        viewport = self.viewport().size()
        width = max(viewport.width(), inner.minimumSizeHint().width())
        if inner.size() != QSize(width, viewport.height()):
            inner.resize(width, viewport.height())

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt name
        super().resizeEvent(event)
        self._fit_inner()

    def event(self, event) -> bool:  # noqa: N802 - Qt name
        if event.type() == QEvent.LayoutRequest:
            self._fit_inner()
            self.updateGeometry()
        return super().event(event)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt name
        """What it would like: enough for a whole card, when there is room.

        Qt shares out spare space in proportion to what each widget asks for, so
        this is where the columns stake their claim against the card stack above
        them. Unlike a minimum it costs nothing on a short screen - the columns
        simply get less, and scroll.
        """
        inner = self.widget()
        if inner is None:
            return super().sizeHint()
        hint = inner.sizeHint()
        wanted = max(hint.height(), self._min_height)
        return QSize(hint.width(), wanted + self._bar_room())


# --------------------------------------------------------------- smooth wheel

# How far one notch of the wheel travels. Qt multiplies its own step by the
# number of lines Windows is set to scroll, which on this machine is 7 - and with
# the clip list reporting a 58px step that came to 406px, four whole rows, per
# notch. The same arithmetic left a sentiment column moving 7px. One number here,
# applied everywhere, so every surface in the application behaves the same.
WHEEL_PIXELS = 52          # per line, times the lines the system asks for
WHEEL_LINES = 3            # what a notch means when the system will not say
GLIDE_MS = 260


def _notch_travel() -> int:
    """One wheel notch, in pixels, honouring the system's own setting."""
    lines = QApplication.wheelScrollLines() if QApplication.instance() else 0
    if lines <= 0 or lines > 10:        # "one screen at a time" and other extremes
        lines = WHEEL_LINES
    return int(lines * WHEEL_PIXELS / 2)


class SmoothWheel(QObject):
    """Makes the wheel glide instead of lurch.

    Qt scrolls a list by whole items and a scroll area by a fixed step, both
    applied instantly, so a notch of the wheel jumps the page and the eye has to
    find its place again. This animates from wherever the view is to wherever the
    notch asked for, easing out, and adds a further notch to the target already in
    flight so spinning the wheel accelerates smoothly rather than restarting.

    A touchpad's own pixel deltas are already continuous and are passed through
    untouched - animating them would fight the finger.
    """

    def __init__(self, area: QAbstractScrollArea, orientation=Qt.Vertical):
        super().__init__(area)
        self._area = area
        self._bar = (area.verticalScrollBar() if orientation == Qt.Vertical
                     else area.horizontalScrollBar())
        self._anim = QVariantAnimation(self)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.setDuration(GLIDE_MS)
        self._target = None
        self._expected = None
        self._writing = False
        self._anim.valueChanged.connect(self._step)
        self._anim.finished.connect(self._settled)
        # A list with rows of different heights re-lays itself out while it
        # scrolls and writes its own value into the middle of a glide, which
        # showed as one backward jerk per notch. Watching for a value that is not
        # the one just written puts it back in the same pass, before anything is
        # repainted, so the correction is never seen.
        self._bar.valueChanged.connect(self._hold)
        area.viewport().installEventFilter(self)

    def _step(self, value) -> None:
        self._expected = int(value)
        self._writing = True
        try:
            self._bar.setValue(self._expected)
        finally:
            self._writing = False

    def _hold(self, value: int) -> None:
        if self._writing or self._expected is None:
            return
        if self._anim.state() != QVariantAnimation.Running:
            return
        if value != self._expected:
            self._step(self._expected)

    def _settled(self) -> None:
        self._target = None
        self._expected = None

    def halt(self) -> None:
        """Stop a glide where it is. A newspad switch replaces the page under it,
        and a glide still aiming at a position on the old page would carry on
        writing that position into the new one."""
        self._anim.stop()
        self._settled()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt name
        if event.type() != QEvent.Wheel:
            return False
        if self._bar is None or self._bar.maximum() <= self._bar.minimum():
            return False
        # Shift+wheel means "scroll sideways", so hand it back - but only where
        # there is something to scroll sideways. On a surface with no horizontal
        # bar Qt quietly scrolls vertically instead, which made Shift the one
        # gesture that still jumped. Ctrl is not excluded at all: nothing in this
        # application zooms on Ctrl+wheel.
        if event.modifiers() & Qt.ShiftModifier:
            sideways = self._area.horizontalScrollBar()
            if sideways is not None and sideways.maximum() > 0:
                return False
        if not event.pixelDelta().isNull():
            return False                # a touchpad: already smooth, leave it

        steps = event.angleDelta().y() / 120.0
        if not steps:
            return False
        start = self._bar.value()
        base = self._target if self._target is not None else start
        target = base - steps * _notch_travel()
        target = max(self._bar.minimum(), min(self._bar.maximum(), int(target)))
        if target == start and self._target is None:
            return False

        self._target = target
        self._anim.stop()
        self._expected = start
        self._anim.setStartValue(float(start))
        self._anim.setEndValue(float(target))
        self._anim.start()
        event.accept()
        return True


# ------------------------------------------------------- the wheel and forms

def page_under(widget) -> Optional[QAbstractScrollArea]:
    """The nearest surface above this widget that has somewhere to scroll.

    Nearest, and with something to scroll: the board's set-up sits in a
    sideways-only scroll (WideScroll) whose vertical bar has no range at all, so
    walking to the first scroll area found would hand the wheel to a surface that
    cannot move. This walks past those to the page.
    """
    node = widget.parentWidget() if hasattr(widget, "parentWidget") else None
    while node is not None:
        if isinstance(node, QAbstractScrollArea):
            bar = node.verticalScrollBar()
            if bar is not None and bar.maximum() > bar.minimum():
                return node
        node = node.parentWidget()
    return None


class WheelGuard(QObject):
    """Stops a form control stealing the wheel from the page it sits on.

    A combo box, a spin box or a date field takes the wheel and changes its own
    value. On a dialog that is a convenience. On this application it is a bug
    twice over, because the cards are one long scrolling page: the page does not
    move, and a setting silently changes that nobody meant to touch.

    The report date is the one that matters. Scrolling from the cover card down
    to the clippings drags the pointer straight across it, and every notch moved
    the report to a different day - printed on the cover, written into the file
    name, and noticed by nobody until the file had gone out.

    A spin box - which is what a date field is underneath - never gets the wheel
    now, whether it is on a page or in a dialog; there is no reading of "I turned
    the wheel" that means "change this number". A combo box or a slider keeps its
    ordinary behaviour where there is no page to scroll, and gives the wheel up
    where there is.

    Installed on the application, so it holds for controls that do not exist yet
    - and most of these are built while a card is being opened.
    """

    #: Never, wherever they are. A date is the reason this class exists.
    NEVER = (QAbstractSpinBox,)
    #: Only when there is a page that would rather have it.
    WHEN_ON_A_PAGE = (QComboBox, QAbstractSlider)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt name
        if event.type() != QEvent.Wheel:
            return False
        # A scrollbar is a slider, and the wheel over one should go on scrolling
        # the thing it belongs to.
        if isinstance(watched, QScrollBar):
            return False
        never = isinstance(watched, self.NEVER)
        if not never and not isinstance(watched, self.WHEN_ON_A_PAGE):
            return False
        # A combo box that is showing its list is being used, not scrolled past.
        if isinstance(watched, QComboBox) and watched.view().isVisible():
            return False
        page = page_under(watched)
        if page is not None:
            QApplication.sendEvent(page.viewport(), event)
            return True
        return never


_GUARD: Optional[WheelGuard] = None


def guard_the_wheel(app=None) -> Optional[WheelGuard]:
    """Apply the rule above to the whole application. Safe to call twice."""
    global _GUARD
    app = app or QApplication.instance()
    if app is None or _GUARD is not None:
        return _GUARD
    _GUARD = WheelGuard(app)
    app.installEventFilter(_GUARD)
    return _GUARD


def smooth(area: QAbstractScrollArea, orientation=Qt.Vertical) -> SmoothWheel:
    """Give one scrollable surface a gliding wheel. Returns the filter."""
    return SmoothWheel(area, orientation)


class PageScroll(QScrollArea):
    """The whole page in one vertical scroll, the way a web page scrolls.

    The sentiment board is a column of set-up - division, totals, cover page,
    layout - and then the columns where the work actually happens. A drag handle
    let the two be rebalanced, and a button folded the set-up away, but neither is
    what a person reaches for: they turn the wheel. So the page scrolls as one,
    and the working half is kept at least as tall as the viewport, which means
    scrolling to the bottom hands the whole window to the columns.
    """

    def __init__(self, name: str, inner: QWidget, filler: QWidget,
                 cap: QWidget | None = None, share: float = 0.55, parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self._filler = filler
        # The set-up is taller than the window on its own, so without a ceiling
        # the columns start below the fold and the board opens showing no work
        # surface at all. It keeps a little over half the window and scrolls
        # inside itself; the wheel then takes it away entirely.
        self._cap = cap
        self._share = share
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        # Sideways is AlwaysOff again: the one section that will not shrink -
        # the board's set-up - carries its own sideways net (WideScroll), so the
        # page itself never needs one, and two horizontal scrollbars nested one
        # inside the other made the column strip impossible to reason about.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(f"#{name} {{ background: transparent; border: none; }}")
        self.setWidget(inner)
        self.verticalScrollBar().setSingleStep(WHEEL_PIXELS // 2)
        smooth(self)

    def set_share(self, share: float) -> None:
        """How much of the window the capped half may take, from now on."""
        share = max(0.2, min(0.95, float(share)))
        if abs(share - self._share) > 0.001:
            self._share = share
            self._fit_filler()

    def _fit_filler(self) -> None:
        room = self.viewport().height()
        if self._cap is not None:
            self._cap.setMaximumHeight(max(180, int(room * self._share)))
        if self._filler is not None:
            self._filler.setMinimumHeight(max(240, room))

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt name
        super().resizeEvent(event)
        self._fit_filler()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt name
        super().showEvent(event)
        self._fit_filler()

    def to_work(self) -> None:
        """Scroll until the working half starts at the top of the window."""
        if self._filler is None:
            return
        self.ensureVisible(0, self._filler.y(), 0, 0)
        self.verticalScrollBar().setValue(self._filler.y())

    def to_top(self) -> None:
        self.verticalScrollBar().setValue(0)

    def at_work(self) -> bool:
        """True when the set-up has been scrolled out of the way."""
        if self._filler is None:
            return False
        return self.verticalScrollBar().value() >= self._filler.y() - 8
