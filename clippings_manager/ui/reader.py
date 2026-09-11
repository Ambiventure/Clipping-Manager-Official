"""Reading headlines off in the background, so the window stays alive.

Reading one clipping takes about half a second. A morning is a hundred and
twenty of them, and doing that on the thread that draws the window means the
application is dead for a minute at exactly the moment somebody has just
imported their files and wants to look at them. Measured on one real morning:
56 seconds frozen, 114 separate stalls, the longest 1.7 seconds. Scattering
`processEvents` through it did not help - it bought one repaint every half
second, so the window redrew twice a second and ignored every click in between,
which is harder to diagnose than an honest freeze.

So the reading happens here instead, off the drawing thread, and the answer
arrives when it is ready.

**The engines must be built on the main thread.** This is the one thing that
will silently ruin the feature if it is got wrong. `tesserocr` installs a signal
handler while it starts up, and Python only allows that on the main thread; from
anywhere else it raises "signal only works in main thread of the main
interpreter". Worse, :mod:`ocr` catches that and remembers the failure, so one
attempt from a worker leaves the whole session with no reader at all - every
clipping reads empty, nothing is ever flagged, and the application looks
perfectly healthy while doing nothing. So the engines are made here, on the main
thread, and handed to the worker ready to use.
"""

from __future__ import annotations

import atexit
import os
import time

from PySide6.QtCore import QCoreApplication, QObject, QThread, Signal, Slot

from ..core import imageops, ocr

# How many clippings to read at once. Four engines read four times as fast as
# one (measured: 3.8x on twelve cores) and each costs about 40ms to build and a
# few megabytes to keep. Beyond four the gain flattens and the machine is
# wanted for other things - not least drawing the window.
MOST_ENGINES = 4

# Two cores left alone, not one. Reading a morning takes about a quarter of a
# minute whichever way, and it happens behind a window somebody is trying to
# work in; the difference between four readers and three on an eight-core
# machine is a few seconds nobody is waiting for, against a scroll that stays
# smooth, which is felt on every single gesture.
CORES_LEFT_ALONE = 2

# How long a measuring thread stands aside for, between clippings, in seconds.
#
# See the module docstring for the measurement. Two thousandths is enough: the
# window only needs the interpreter for a moment at a time to stay alive under
# the hand, and this hands it over between every clipping rather than only when
# the pass ends. Across a morning of a hundred and fifty clippings on four
# threads it adds about seventy thousandths of a second to each of them.
BREATHE = 0.002

# How long each reader waits behind the one before it, in seconds.
#
# The first picture an engine reads costs it a couple of hundred milliseconds of
# setting itself up, and that is time the interpreter cannot be doing anything
# else. Four readers starting together therefore make one pause of the better
# part of a second, right after the button was pressed - the moment somebody is
# most likely to be looking at the window and least likely to forgive it. Spread
# out, the same pauses fall in different places and none of them is noticed.
#
# Measured on a real morning: worst pause 789ms with them together, and the
# whole pass a third of a second longer with them apart.
LANE_STAGGER = 0.18


def _how_many() -> int:
    try:
        cores = os.cpu_count() or 2
    except Exception:  # noqa: BLE001
        cores = 2
    return max(1, min(MOST_ENGINES, cores - CORES_LEFT_ALONE))


def _step_aside() -> None:
    """Ask Windows to prefer anything else over this thread.

    Tesseract does not stop to be polite, so on a busy machine four readers and
    a window redrawing compete evenly and the window loses often enough to be
    seen as stutter. Below-normal costs the reading almost nothing - it still
    gets every idle moment there is, and there are plenty - and it means a
    scroll or a click is served first.

    Windows only, and entirely optional: a machine where this fails reads at the
    same speed it always did.
    """
    try:
        import ctypes

        BELOW_NORMAL = -1
        handle = ctypes.windll.kernel32.GetCurrentThread()
        ctypes.windll.kernel32.SetThreadPriority(handle, BELOW_NORMAL)
    except Exception:  # noqa: BLE001 - not Windows, or not permitted
        pass


class Reading:
    """What was worked out about one clipping, ready to be copied back."""

    __slots__ = ("uid", "text", "confidence", "engine", "print_all",
                 "print_low", "print_fine", "width", "height", "ink")

    def __init__(self, uid, text, confidence, engine, print_all, print_low,
                 print_fine="", width=0, height=0, ink=""):
        self.uid = uid
        self.text = text
        self.confidence = confidence
        self.engine = engine
        self.print_all = print_all
        self.print_low = print_low
        # Taken in the same pass as the prints above: the finer 256-bit print,
        # the size of the trimmed content box, and where the ink sits.
        self.print_fine = print_fine
        self.width = width
        self.height = height
        self.ink = ink


class Reader(QObject):
    """Reads a batch of clippings away from the window.

    It is given plain bytes and gets back plain values - it never touches a
    Clip. The clippings belong to the window's thread and are painted from it;
    handing them to another thread to be modified while they are being drawn is
    how a list ends up half-painted from two different states.
    """

    progressed = Signal(int, int)          # done, total
    finished = Signal(list)                # [Reading]

    def __init__(self, engines, parent=None, read_headlines: bool = True,
                 measure: bool = True):
        super().__init__(parent)
        self._engines = list(engines)
        # Whether to measure the pictures as well as read them. False for the
        # second pass, whose clippings were all measured by the first one
        # seconds earlier - and measuring them again means four threads
        # decoding four pictures in the same instant, which is felt as one long
        # pause exactly when the reading starts.
        self._measure = measure
        self._work: list = []
        self._stop = False
        # What the pass had read by the time it ended, stopped or not. A stopped
        # pass sends an empty list, because a partial answer must never be
        # mistaken for the whole one - but a newspad switch stops a pass and
        # still wants to keep the readings already taken, rather than read the
        # same pictures again when the newspad is opened next.
        self.kept: list = []
        self._done = 0
        # A pass that only fingerprints. Taking a print is a few thousandths of
        # a second and reading a headline is about half of one, so measuring
        # everything first and reading only what already looks like a repeat is
        # the difference between the machine being busy for half a minute after
        # an import and being busy for two seconds.
        self._read_headlines = read_headlines

    def give(self, work) -> None:
        """[(uid, image_bytes)] to read. Set before the thread starts."""
        self._work = list(work)

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        total = len(self._work)
        if not total or (self._read_headlines and not self._engines):
            self.finished.emit([])
            self._end()
            return

        lanes = max(1, min(len(self._engines) if self._read_headlines
                           else MOST_ENGINES, total))
        out: list = []

        # The work is split into as many runs as there are engines, and each
        # run is given ONE engine that belongs to it alone.
        #
        # The obvious way - hand out engines by item number, engine[i % lanes]
        # - looks equivalent and is not. A pool decides which thread takes
        # which item, so two threads can reach for the same engine at the same
        # moment, and two threads inside one Tesseract engine take the whole
        # process down: no traceback, no exit code, the window simply
        # disappears. An engine belongs to a thread, never to an item.
        runs = [self._work[lane::lanes] for lane in range(lanes)]

        def sweep(lane):
            _step_aside()
            if lane and LANE_STAGGER:
                # Behind the lane before it. See LANE_STAGGER.
                time.sleep(lane * LANE_STAGGER)
            engine = self._engines[lane] if lane < len(self._engines) else None
            got = []
            for uid, data in runs[lane]:
                if self._stop:
                    break
                if engine is None or not self._read_headlines:
                    found = ocr.Headline()
                else:
                    try:
                        found = ocr.headline_with(engine, data)
                    except Exception:  # noqa: BLE001 - it will not read
                        found = ocr.Headline()
                blank = {"whole": "", "lower": "", "fine": "", "width": 0,
                         "height": 0, "ink": ""}
                if not self._measure:
                    # Nothing to say about the picture. The window keeps what it
                    # already has: it only copies a measurement back when there
                    # is one, so an empty answer here changes nothing.
                    seen = blank
                else:
                    try:
                        # One decode, one trim, everything measured off it.
                        seen = imageops.measure(data)
                    except Exception:  # noqa: BLE001
                        seen = blank
                got.append(Reading(
                    uid, found.text, found.confidence,
                    (found.engine or "tesseract") if self._read_headlines else "",
                    seen["whole"], seen["lower"], seen["fine"],
                    seen["width"], seen["height"], seen["ink"]))
                self._done += 1
                if not self._read_headlines and BREATHE:
                    # Stand aside for the window. A reading pass does not need
                    # this - Tesseract lets go of the interpreter for the whole
                    # of every recognition - but a measuring pass never lets go
                    # on its own, and four of them together can keep the window
                    # shut for the better part of a second. See BREATHE.
                    time.sleep(BREATHE)
            return got

        try:
            import threading

            threads, results = [], [None] * lanes

            def hold(lane):
                results[lane] = sweep(lane)

            for lane in range(lanes):
                thread = threading.Thread(target=hold, args=(lane,),
                                          daemon=True)
                thread.start()
                threads.append(thread)
            # Progress is told to Qt from HERE, on the thread Qt made. A signal
            # emitted from a thread Qt does not know about is another way to
            # lose the process without a word.
            #
            # Paced by waiting on a lane that is still RUNNING. This used to wait
            # on the first lane, finished or not - and once that lane had
            # finished, the wait returned at once and the loop spun, sending a
            # progress message as fast as it could until the slowest lane was
            # done. Measured after a newspad switch: 120,000 of them queued up
            # for the window, and 1.5 seconds of frozen window draining them.
            # And only when there is something new to say.
            said = -1
            while True:
                running = [t for t in threads if t.is_alive()]
                if not running:
                    break
                if self._done != said:
                    said = self._done
                    self.progressed.emit(said, total)
                running[0].join(0.15)
            for t in threads:
                t.join()
            for part in results:
                out.extend(part or [])
        except Exception:  # noqa: BLE001 - never let this kill the window
            pass
        self.progressed.emit(total, total)
        self.kept = list(out)
        self.finished.emit([] if self._stop else out)
        self._end()

    def _end(self) -> None:
        """Stop this thread's own event loop, from inside it.

        The answers above went out as a queued call, which the window will pick
        up when it next draws. Stopping the thread must NOT wait for that. If
        the window has already gone - the program is closing, a report has just
        been written and the door shut - nobody is left to call quit(), the
        thread runs on, and a QThread still running when its C++ object is
        destroyed ends the process on the spot: no traceback, no message, exit
        code 0xC0000409. Ending here needs nothing from anybody.
        """
        try:
            here = QThread.currentThread()
            app = QCoreApplication.instance()
            # Never the window's own thread. run() is only ever reached from
            # the background thread, but if it were ever called straight - from
            # a test, or a later shortcut - quitting here would stop the
            # program's event loop and close the window.
            if here is not None and app is not None and here is not app.thread():
                here.quit()
        except RuntimeError:  # the thread object is already gone
            pass


class _Hand(QObject):
    """Carries the reader's answers back to the thread that owns the window.

    Made on the caller's thread, so Qt knows where its slots must run. See
    :func:`start` for why that matters more than it looks.
    """

    def __init__(self, on_progress, on_finished, thread, parent=None):
        super().__init__(parent)
        self._on_progress = on_progress
        self._on_finished = on_finished
        self._thread = thread
        self._engines: list = []

    @Slot(int, int)
    def progressed(self, done: int, total: int) -> None:
        self._on_progress(done, total)

    @Slot(list)
    def finished(self, results) -> None:
        try:
            self._on_finished(results)
        finally:
            # The pass stops itself as well (see Reader._end), so this is a
            # second belt and not the only one. It can arrive after the thread
            # is already gone, which is fine and must not raise.
            try:
                self._thread.quit()
            except RuntimeError:
                pass

    @Slot()
    def done(self) -> None:
        engines, self._engines = self._engines, []
        ocr.close_engines(engines)


# Every pass that is still going. A pass holds a thread, and a thread that is
# still running when the process tears down takes the process with it, so the
# door is not allowed to shut until they have all been let out.
_LIVE: list = []
_AT_EXIT = False
_HOOKED = False


def _forget(thread) -> None:
    try:
        _LIVE.remove(thread)
    except ValueError:
        pass


def stop_all(grace_ms: int = 5000) -> None:
    """Stop every background pass and wait for it. Safe to call twice.

    Called on the way out - both when the application quits and, for anything
    that never ran an event loop at all, at interpreter exit. Asking a pass to
    stop is cheap: it checks between clippings, so it notices within about the
    time it takes to read one.
    """
    for thread in list(_LIVE):
        try:
            worker = getattr(thread, "_worker", None)
            if worker is not None:
                worker.stop()
            thread.quit()
            stopped = thread.wait(grace_ms)
            # Only once it has stopped. A reader that is still inside Tesseract
            # when its engine is taken away is the one failure this file cannot
            # catch or report - the process simply ends. If the wait ran out,
            # the engines are left alone and released when the process does.
            hand = getattr(thread, "_hand", None)
            if stopped and hand is not None:
                engines, hand._engines = getattr(hand, "_engines", []) or [], []
                ocr.close_engines(engines)
        except RuntimeError:  # already destroyed, which is what we wanted
            pass
        _forget(thread)


def _watch_the_door() -> None:
    """Make sure something stops these passes before the process goes.

    Two ways out, because there are two ways out: the application quitting -
    the window closed, the program finished - and the interpreter simply
    ending, which is what a script that never ran an event loop does.
    """
    global _AT_EXIT, _HOOKED
    if not _AT_EXIT:
        _AT_EXIT = True
        atexit.register(stop_all)
    if not _HOOKED:
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(stop_all)
            _HOOKED = True


def start(work, on_progress, on_finished, parent=None,
          read_headlines: bool = True, measure: bool = True):
    """Read these clippings in the background. Returns (thread, reader).

    The engines are built here, on the caller's thread, which must be the main
    one - see the module docstring for what happens otherwise.

    ``read_headlines=False`` takes only the picture fingerprints. No engine is
    built at all then, which matters: building four of them is about 160ms on
    the thread that draws the window, and a fingerprint-only pass is exactly the
    one that wants to start without a pause.
    """
    engines = []
    if work and read_headlines:
        engines = ocr.build_engines(_how_many())
    thread = QThread(parent)
    reader = Reader(engines, read_headlines=read_headlines, measure=measure)
    reader.give(work)
    reader.moveToThread(thread)
    thread.started.connect(reader.run)

    # The answers come back through this, and it is not decoration.
    #
    # A plain function connected to a signal gives Qt no QObject, and therefore
    # no thread, so Qt calls it straight away on whichever thread emitted -
    # here, the reader's. Everything the callback then touched was touched from
    # the wrong thread: the clipping list, the status strip, and worst of all
    # the headline reader.
    #
    # That last one is not merely unsafe, it is permanent. Building a Tesseract
    # engine installs a signal handler, and Python allows that only on the main
    # thread; anywhere else it raises "signal only works in main thread of the
    # main interpreter", and ocr remembers the failure for the rest of the
    # session. One background pass finishing was enough to leave every later
    # duplicate check telling the user this machine has no headline reader.
    #
    # A QObject made HERE, on the caller's thread, is the fix: Qt sees a sender
    # in one thread and a receiver in another and queues the call, so the slots
    # below run where the window lives.
    hand = _Hand(on_progress, on_finished, thread, parent)
    reader.progressed.connect(hand.progressed)
    reader.finished.connect(hand.finished)
    thread.finished.connect(hand.done)
    # Kept alive for as long as the thread is: a receiver that has been
    # collected delivers nothing, and the pass would appear to hang.
    thread._hand = hand
    thread._worker = reader
    hand._engines = engines

    # Remembered until it is over, so the program cannot walk out on it. This
    # connection is deliberately a plain function: it must run the moment the
    # thread ends, on the thread that ended, and not wait its turn behind a
    # window that may never draw again.
    _LIVE.append(thread)
    thread.finished.connect(lambda: _forget(thread))
    _watch_the_door()

    thread.start()
    return thread, reader
