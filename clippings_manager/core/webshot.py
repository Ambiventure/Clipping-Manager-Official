"""Taking a picture of a web page, using the Chrome already on the machine.

Paste a link and the program should hand back a cutting: the headline, the
picture and the first inches of the story - not the whole page with its menus,
adverts and cookie bars. That is what this does.

HOW, AND WHY THIS WAY. The Chrome on the PC is started with no window, pointed
at its own folder of settings, and driven over the debugging port it opens for
exactly this purpose. Nothing is installed, the hand-over copy does not grow,
and the browser is the one the office already trusts. The page itself is asked
where its story is - scripts run inside the page (core/blockjs.py) and measure
the headline, the picture and the first run of text - and only that rectangle
is captured. The browser inside the program (ui/embedded.py) is driven over
the same protocol by the same code, so a story comes out the same whichever
browser took it.

THE WINDOW IS NARROW ON PURPOSE. At 820 pixels across, a news site lays itself
out in one column: no advert rail beside the story, nothing to crop away. Wide,
the same page puts "you may like" next to the headline and the cutting has to
be cut again. A page that refuses to be that narrow (Economic Times keeps 1003
pixels whatever the window) is given its own width, and only then, so its
centred headline comes out whole.

THE CAPTURE WAITS FOR ITS PICTURES. Not for the page's load event, which an
advert-heavy site may never reach, but for the pictures in the top of the
story - late ones, lazy ones, ones drawn as a background - each wait with a
limit. Adverts, walls, cookie bars and anything pinned over the page are taken
away first, and the picture is taken inside the window with the page brought
to the cutting: taking it beyond the window resized the page after it was
measured, and one site moved its photo 4,800 pixels (NOTES: "Capture quality").

EVERY CALL HAS A LIMIT. A page can stop answering - one site stops Qt's engine
about nine seconds in - and a list of twelve links must not wait on it for
ever. Each call gives up at its own limit and says so in plain words.

IT IS NEVER YOUR OWN CHROME. The program keeps its own settings folder, so the
Chrome you have open - with WhatsApp Web in it - is not touched, not closed,
and not read. Signing in to X or Facebook for the program is done once, in a
window it opens itself, and that sign-in lives only in that folder.

Nothing here runs unless somebody asks for a link to be captured.
"""

from __future__ import annotations

import base64
import json
import math
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import embedcard

#: How wide the page is laid out, in CSS pixels. See the note above.
PAGE_WIDE = 820
PAGE_TALL = 1500
#: Two device pixels per CSS pixel: a cutting has to stand being printed.
SHARPNESS = 2
#: How long to wait for the page itself, and for the browser to start.
PAGE_SECONDS = 25.0
START_SECONDS = 30.0
#: A pause after the page is asked for, before anything is asked of it. The
#: real waiting - for the structure, the pictures, the fonts - is done inside
#: the page by PREPARE_PAGE, each with a limit of its own.
SETTLE_SECONDS = 1.0
#: The limits PREPARE_PAGE waits within, in milliseconds. The page's structure
#: (DOMContentLoaded), the pictures in the top of the story, the fonts, and how
#: far down the page to scroll for pictures that load only when seen.
PREPARE_LIMITS = {"domMs": 4000, "imageMs": 4000, "fontsMs": 1500, "scrollLimit": 3000}
#: Once the cutting is chosen, how long its own pictures may take to finish.
BLOCK_WAIT_MS = 3000
#: The widest a page is ever laid out, for a page that will not be narrower.
WIDEST = 1600
#: Limits for the calls over the wire, in seconds.
CALL_SECONDS = 10.0
SCRIPT_SECONDS = 15.0
#: PREPARE_PAGE's own limits add up to about 11.5 s at the worst (structure 4,
#: a few scroll steps, pictures 4, fonts 1.5, frames); a page that has not
#: answered a few seconds after that has stopped answering.
PREPARE_SECONDS = 16.0
#: How far (CSS pixels) a kept thing may move while its picture is taken
#: before the picture is taken again.
MOVED_TOO_FAR = 4.0
#: Before a link is opened, how long the page the last link left behind has
#: to answer a one-line script. A page can capture normally and stop
#: answering seconds later (Hindustan Times, about nine seconds in); without
#: this the next, innocent link waited 25 s and was blamed for it.
ANSWER_SECONDS = 2.0
#: How long a script is run again, a moment apart, while the page keeps
#: moving on to another page under it (a redirect, then another).
MOVED_SECONDS = 8.0
#: A page that gave nothing to cut and opened less than this long ago may be
#: a page on its way to another (a script that sends it on after a second or
#: two): it is looked at again after MOVE_WAIT at the least.
YOUNG_SECONDS = 3.0
MOVE_WAIT = 1.5
#: How many pages a link may move through before it is given up on.
MOVES = 3

SOCIAL_SITES = ("x.com", "twitter.com", "facebook.com", "instagram.com", "threads.net")

WINDOWS_CHROME = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
)
#: Edge is Chrome underneath and speaks the same protocol. Only used when
#: Chrome is not there at all.
WINDOWS_EDGE = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)

NO_BROWSER = ("Google Chrome was not found on this PC, so a link cannot be "
              "captured. Install Chrome, or take the screenshot by hand and "
              "drag it in.")
DID_NOT_OPEN = ("that page did not open. Check the link, or open it in your "
                "browser to see what it says.")
POST_NEEDS_SIGN_IN = ("that post could not be read. Either it needs you to be "
                      "signed in - sign in to it in the browser inside the "
                      "app, or take it from your Chrome - or the post has been "
                      "taken down.")
#: The card came, and said there is no public post behind the address. Said
#: only after the post's own page has been tried as well, so by the time
#: anybody reads it both ways have been.
NO_PUBLIC_POST = ("that post is not public - it has been taken down, or it was "
                  "only ever shown to the writer's friends. Open it in your "
                  "browser to see, and take the picture from there.")
NOT_A_STORY = "nothing on that page looked like a story"
UNREADABLE = "the page could not be read"
#: For a page captured in the background: it was sent to a blank page to
#: unstick it, so the next link starts clean. Either browser may have been
#: the one taking it, so the words send nobody back to the browser that just
#: failed them.
STOPPED = ("that page stopped answering. Try it again, or take it from your "
           "Chrome.")
#: The page the link before left behind would not answer and could not be
#: unstuck, so this link was never opened. Whoever owns the browser starts it
#: afresh and tries the link once more; these words are seen only if that
#: fails too.
LEFT_STUCK = ("the browser was still stuck on the page before, so this link "
              "was not opened. Try it again.")
#: A page that went on to another page, and another, for as long as it was
#: given.
MOVED_ON = ("that page kept moving on to another page. Open it in your "
            "browser to see where it goes.")
#: For the page somebody is looking at, which is never sent anywhere.
STOPPED_HERE = ("that page stopped answering. Reload it and try again, or "
                "take it from your Chrome.")
#: For the page somebody is looking at, when it went on to another page while
#: its picture was being taken (a click, or the page's own script): the
#: picture would have been of the other page, filed under this one's link.
PAGE_CHANGED = ("the page changed while it was being captured. Wait for it to "
                "finish opening and try again.")
WIRE_STOPPED = "the page stopped answering"
WIRE_CLOSED = "the browser closed while the page was read"


class ShotError(Exception):
    """Something went wrong for one link. Its message is for the person.

    `kind` says what sort of trouble it was, for the window to act on without
    reading the words: "sign-in" (a wall that wants somebody signed in),
    "gone" (the page never opened), "stopped" (the page or the browser stopped
    answering), "not-a-story" (nothing on it to cut out), "changed" (the page
    somebody is looking at went on to another page during its capture), or ""
    for anything else.

    `unopened` is set on a "stopped" that came before the link was opened -
    the page the link before left behind would not answer - so the link
    itself is not to blame and may be tried once more on a fresh page.
    """

    def __init__(self, message: str = "", kind: str = "", unopened: bool = False):
        super().__init__(message)
        self.kind = kind
        self.unopened = unopened


def find_browser() -> str:
    """Where Chrome is, or Edge if there is no Chrome, or "" if neither."""
    if sys.platform != "win32":
        for name in ("google-chrome", "chromium", "chrome", "msedge"):
            found = shutil.which(name)
            if found:
                return found
        return ""
    for pattern in WINDOWS_CHROME + WINDOWS_EDGE:
        path = Path(os.path.expandvars(pattern))
        if path.is_file():
            return str(path)
    return ""


def browser_folder() -> Path:
    """The program's own browser settings, beside its other settings.

    Its own, never the person's: their Chrome stays open and untouched, and a
    sign-in made here does not reach their everyday browsing.
    """
    from ..ui.export_dialog import settings_dir

    folder = Path(settings_dir()) / "browser"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# ----------------------------------------------------------------- websocket
class _Wire:
    """The smallest WebSocket client that can carry DevTools messages.

    A dependency-free twenty lines each way: the alternative is another library
    in the hand-over copy for one page of protocol.

    Every call keeps to its own time limit. The socket's timeout is set to
    what is left of the call's limit before each read, and a read that runs
    out raises ShotError(kind="stopped") - never a bare TimeoutError. A frame
    half-read when the limit ran out stays in `rest`, unconsumed, so the next
    call picks the stream up where it was and the wire is never out of step.
    """

    def __init__(self, url: str, seconds: float = 30.0):
        rest = url.split("://", 1)[1]
        host_port, _, path = rest.partition("/")
        host, _, port = host_port.partition(":")
        self.seconds = seconds
        #: Set when the page would not answer even after it was unstuck.
        self.stuck = False
        try:
            self.sock = socket.create_connection((host, int(port or 80)), timeout=seconds)
            self.sock.settimeout(seconds)
            key = base64.b64encode(os.urandom(16)).decode()
            self.sock.sendall((
                f"GET /{path} HTTP/1.1\r\nHost: {host_port}\r\nUpgrade: websocket\r\n"
                f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
            head = b""
            while b"\r\n\r\n" not in head:
                piece = self.sock.recv(1)
                if not piece:
                    raise ShotError("the browser would not answer", kind="stopped")
                head += piece
        except (socket.timeout, TimeoutError):
            raise ShotError("the browser would not answer", kind="stopped") from None
        except OSError:
            raise ShotError("the browser would not answer", kind="stopped") from None
        if b" 101" not in head.split(b"\r\n")[0]:
            raise ShotError("the browser refused the connection")
        self.rest = bytearray()
        self.count = 0
        #: A page's own alert, confirm or prompt box is answered "no" as soon
        #: as it is reported. Nobody can see the background page, and an
        #: unanswered box stops the page running any script: an "Ad blocker
        #: detected" alert failed its link as stopped after 17 s. Turned off
        #: for the page somebody is reading - its boxes are theirs to answer.
        self.answer_dialogs = True
        #: Set while capture_current pictures a page as it is: a script whose
        #: page went on to another is not run again in the new page.
        self.stay = False

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def abort(self) -> None:
        """Cut the wire from another thread: a call waiting on it returns at
        once, as WIRE_CLOSED, and every call after it fails straight away.

        For the browser window being closed while it captures. Its page
        answers from Qt's main thread, which is then busy closing the window,
        so a call left waiting could only run out its limit (review of step B,
        round 2). Only shut, never closed, here: the thread that owns the wire
        closes it, so its socket cannot be closed under a read in progress
        and its number handed to another socket meanwhile."""
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def send(self, method: str, **params) -> int:
        self.count += 1
        body = json.dumps({"id": self.count, "method": method,
                           "params": params}).encode()
        mask = os.urandom(4)
        size = len(body)
        header = b"\x81"
        if size < 126:
            header += bytes([0x80 | size])
        elif size < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", size)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", size)
        self.sock.sendall(header + mask
                          + bytes(b ^ mask[i % 4] for i, b in enumerate(body)))
        return self.count

    def _fill(self, many: int, until: Optional[float] = None) -> None:
        """At least `many` bytes waiting in `rest`. Nothing is taken out.

        With `until`, every read is given only what is left of the call's
        limit, not the limit afresh: a frame that trickles in a byte at a time
        stretched a one-second call to nearly ten (measured, a fake server)."""
        while len(self.rest) < many:
            if until is not None:
                left = until - time.time()
                if left <= 0:
                    raise ShotError(WIRE_STOPPED, kind="stopped")
                self.sock.settimeout(max(0.05, left))
            more = self.sock.recv(1 << 16)
            if not more:
                raise ShotError(WIRE_CLOSED, kind="stopped")
            self.rest += more

    def _message(self, until: Optional[float] = None) -> dict:
        # The frame is looked at where it lies and taken out only once the
        # whole of it has arrived: a limit that runs out part-way leaves it
        # in place for the next call.
        self._fill(2, until)
        size = self.rest[1] & 0x7F
        head = 2
        if size == 126:
            self._fill(4, until)
            size = struct.unpack(">H", bytes(self.rest[2:4]))[0]
            head = 4
        elif size == 127:
            self._fill(10, until)
            size = struct.unpack(">Q", bytes(self.rest[2:10]))[0]
            head = 10
        if self.rest[1] & 0x80:
            head += 4                      # a masked frame; servers send none
        self._fill(head + size, until)
        body = bytes(self.rest[head:head + size])
        del self.rest[:head + size]
        try:
            return json.loads(body)
        except ValueError:
            return {}

    def wait(self, message_id: int, seconds: float) -> dict:
        until = time.time() + seconds
        try:
            while True:
                if until - time.time() <= 0:
                    raise ShotError(WIRE_STOPPED, kind="stopped")
                message = self._message(until)
                if (message.get("method") == "Page.javascriptDialogOpening"
                        and getattr(self, "answer_dialogs", True)):
                    # Answered without waiting for the answer: its reply is
                    # passed over like any other message not waited for. A
                    # "leave this page?" box is let go, or the next link
                    # would never open.
                    leave = (message.get("params") or {}).get("type") == "beforeunload"
                    self.send("Page.handleJavaScriptDialog", accept=leave)
                    continue
                if message.get("id") == message_id:
                    if "error" in message:
                        raise ShotError(str(message["error"].get("message", "refused")))
                    return message
        except (socket.timeout, TimeoutError):
            raise ShotError(WIRE_STOPPED, kind="stopped") from None
        except OSError:
            raise ShotError(WIRE_CLOSED, kind="stopped") from None
        finally:
            try:
                self.sock.settimeout(self.seconds)
            except OSError:
                pass

    def call(self, method: str, seconds: float = 30.0, **params) -> dict:
        try:
            sent = self.send(method, **params)
        except OSError:
            raise ShotError(WIRE_CLOSED, kind="stopped") from None
        return self.wait(sent, seconds)


# -------------------------------------------------------------------- browser
@dataclass
class Shot:
    """One captured page."""

    png: bytes
    url: str
    title: str = ""
    site: str = ""
    kind: str = "story"          # story | post | page
    #: CSS pixels, painted margins included.
    width: int = 0
    height: int = 0
    #: How the picture was taken - what was hidden, blanked, waited for, the
    #: window's size, any margin painted back. For looking into a capture that
    #: came out wrong; never saved with the clipping.
    notes: dict = field(default_factory=dict)


@dataclass
class Browser:
    """A Chrome running with no window, ready to be pointed at pages."""

    path: str = ""
    process: Optional[subprocess.Popen] = None
    port: int = 0
    wire: Optional[_Wire] = field(default=None, repr=False)

    # -- opening and closing ------------------------------------------------
    def start(self, visible: bool = False) -> None:
        self.path = self.path or find_browser()
        if not self.path:
            raise ShotError(NO_BROWSER)
        folder = browser_folder()
        # A sign-out asked for while this Chrome was open, done before it opens.
        apply_sign_out_mark()
        port_file = folder / "DevToolsActivePort"
        try:
            port_file.unlink()
        except OSError:
            pass
        flags = [
            self.path, f"--user-data-dir={folder}", "--no-first-run",
            "--no-default-browser-check", "--disable-features=Translate",
            "--remote-debugging-port=0", "--mute-audio", "--disable-gpu",
            "--hide-scrollbars", f"--window-size={PAGE_WIDE},{PAGE_TALL}",
            "about:blank",
        ]
        if not visible:
            flags.insert(1, "--headless=new")
        self.process = subprocess.Popen(
            flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        _STARTED.append(self.process)
        until = time.time() + START_SECONDS
        while time.time() < until:
            if self.process.poll() is not None:
                raise ShotError("the browser stopped before it opened a page")
            try:
                lines = port_file.read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
            if lines and lines[0].strip().isdigit():
                self.port = int(lines[0].strip())
                return
            time.sleep(0.1)
        self.stop()
        raise ShotError("the browser did not start")

    def stop(self) -> None:
        if self.wire is not None:
            self.wire.close()
            self.wire = None
        process, self.process = self.process, None
        if process is None:
            return
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:  # noqa: BLE001 - it is going away either way
            try:
                process.kill()
            except Exception:  # noqa: BLE001
                pass

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    # -- the page -----------------------------------------------------------
    def _page(self) -> _Wire:
        if self.wire is not None:
            return self.wire
        self.wire = attach(self.port)
        # Say who we are the way an ordinary Chrome does. With a window there
        # is no window, the browser calls itself HeadlessChrome, and X answers
        # "Access to x.com was denied" before the page is ever drawn. This is
        # the same browser either way - only the name it gives changes.
        try:
            told = self.wire.call("Browser.getVersion", seconds=10)
            agent = told["result"].get("userAgent", "")
            if "Headless" in agent:
                self.wire.call("Emulation.setUserAgentOverride", seconds=10,
                               userAgent=agent.replace("HeadlessChrome", "Chrome"))
        except ShotError:
            pass          # an older browser: carry on as we are
        return self.wire

    def capture(self, url: str, settle: float = SETTLE_SECONDS) -> Shot:
        """One page, as a cutting. Raises ShotError, never anything else."""
        for attempt in (1, 2):
            if not self.running:
                self.stop()
                self.start()
            wire = self._page()
            try:
                return capture_over(wire, url, settle)
            except ShotError as bad:
                # A page that would not answer even after it was sent to a
                # blank page: this browser is closed, and the next link starts
                # a fresh one rather than waiting on the stuck page again.
                if bad.kind == "stopped" and (wire.stuck or not self.running):
                    self.stop()
                # Stuck before this link was even opened - on the page the
                # link before left behind - so this link is tried once more,
                # in the fresh browser, rather than blamed.
                if attempt == 1 and bad.kind == "stopped" and bad.unopened:
                    continue
                raise
        raise ShotError(STOPPED, kind="stopped")          # not reached

    def __enter__(self) -> "Browser":
        self.start()
        return self

    def __exit__(self, *_args) -> None:
        self.stop()


def free_port() -> int:
    """A loopback port nobody is using, for the browser inside the program
    to answer on. Chosen here because this is the module allowed to know
    what a port is."""
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])
    finally:
        probe.close()


def debugging_address(port: int) -> str:
    """What QtWebEngine is told to listen on: loopback only, this port."""
    return f"127.0.0.1:{port}"


def targets(port: int) -> list:
    """The pages a DevTools port offers. Blocking: never from the thread that
    owns the browser's own event loop (the embedded one answers from Qt's
    main thread, so a call made there waits on itself)."""
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list",
                                timeout=20) as answer:
        return json.loads(answer.read())


def connect(port: int, target_id: str = "", exact: bool = False) -> _Wire:
    """A bare wire to one page on a DevTools port, nothing asked of the page
    yet - the page with this target id, or the first page there is (unless
    `exact`, when only that page will do: a page just made in place of a
    stuck one must never be mistaken for the browser window somebody is
    reading)."""
    pages = [t for t in targets(port) if t.get("type") == "page"]
    if target_id:
        chosen = [t for t in pages if t.get("id") == target_id]
        pages = chosen if (chosen or exact) else pages
    if not pages:
        raise ShotError("the browser opened no page")
    return _Wire(pages[0]["webSocketDebuggerUrl"])


def attach(port: int, target_id: str = "", exact: bool = False,
           seconds: float = CALL_SECONDS, hold=None) -> _Wire:
    """A wire to one page, ready for captures (see connect). Each of the two
    calls that make it ready keeps to `seconds`: a page that stopped
    answering held them for 30 s each, and every link of the next list
    failed behind it.

    `hold`, when given, is handed the wire the moment it is connected, before
    anything is asked of the page, so another thread can cut it while those
    calls wait. The browser inside the program answers them from Qt's main
    thread, and that thread may be the one ending the program (review of
    step B, round 3)."""
    wire = connect(port, target_id, exact)
    if hold is not None:
        hold(wire)
    try:
        wire.call("Page.enable", seconds=seconds)
        wire.call("Runtime.enable", seconds=seconds)
    except ShotError:
        wire.close()
        raise
    return wire


def revive(port: int, target_id: str) -> Optional[_Wire]:
    """A wire to a background page that stopped answering, after sending it
    to a blank page - which needs nothing of the stuck page itself, so it
    works where attach cannot. None if the page still does not answer. Only
    ever for a page nobody is looking at."""
    try:
        wire = connect(port, target_id, exact=True)
    except Exception:  # noqa: BLE001 - not listed, or the port is gone
        return None
    try:
        if _unstick(wire):
            wire.call("Page.enable", seconds=CALL_SECONDS)
            wire.call("Runtime.enable", seconds=CALL_SECONDS)
            return wire
    except ShotError:
        pass
    wire.close()
    return None


def answers(page: _Wire, seconds: float = 3.0) -> bool:
    """Whether the page runs a one-line script within `seconds`."""
    try:
        got = page.call("Runtime.evaluate", expression="1", returnByValue=True,
                        seconds=seconds)
        return (got.get("result", {}).get("result") or {}).get("value") == 1
    except ShotError:
        return False


# ------------------------------------------------------------------- scripts
class _ScriptFailed(Exception):
    """A script threw inside the page (not the page stopping: that is a
    ShotError)."""


def _evaluate(page: _Wire, expression: str, seconds: float) -> object:
    """What a script in the page answered. A page that navigates itself while
    the script runs (a redirect) destroys the script's world: it is run again,
    a moment later, in the new one - and again while the page keeps moving
    on, for MOVED_SECONDS. A page still moving after that is refused in plain
    words, never with the browser's own ("Inspected target navigated or
    closed", which is what two quick redirects used to show)."""
    until = time.time() + MOVED_SECONDS
    while True:
        try:
            answer = page.call("Runtime.evaluate", expression=expression,
                               returnByValue=True, awaitPromise=True,
                               seconds=seconds)
        except ShotError as bad:
            said = str(bad).casefold()
            if not bad.kind and ("context" in said or "navigated" in said):
                # The page somebody is looking at is pictured as it is, or
                # not at all: run again, the script would picture the page it
                # went on to and file it under the first page's link.
                if getattr(page, "stay", False):
                    raise ShotError(PAGE_CHANGED, kind="changed") from None
                if time.time() + 0.7 < until:
                    time.sleep(0.7)
                    continue
                raise ShotError(MOVED_ON, kind="not-a-story") from None
            raise
        result = answer.get("result", {})
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            said = (details.get("exception") or {}).get("description") or details.get("text", "")
            raise _ScriptFailed(str(said)[:300])
        return (result.get("result") or {}).get("value")
    return None


def _run(page: _Wire, script: str, *args, seconds: float = SCRIPT_SECONDS) -> object:
    """A script that is a function, called with these arguments."""
    called = "(" + script.strip() + ")(" + ", ".join(json.dumps(a) for a in args) + ")"
    return _evaluate(page, called, seconds)


def _soft(page: _Wire, script: str, *args, seconds: float = SCRIPT_SECONDS,
          call: bool = True) -> object:
    """A helping script whose failure inside the page must not cost the
    capture - a page that overrides what it uses. The page stopping still
    stops the capture."""
    try:
        if call:
            return _run(page, script, *args, seconds=seconds)
        return _evaluate(page, script, seconds)
    except _ScriptFailed as bad:
        return {"failed": str(bad)}


def _json(value, default=None):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default if default is not None else {}
    if isinstance(value, dict):
        return value
    return default if default is not None else {}


def refusal(found: dict) -> Optional[ShotError]:
    """Why what FIND_BLOCK found gives no cutting, or None when it gives one.

    A page that never arrived - no network, a wrong link, or a site that turned
    us away - leaves Chrome showing its own error page, and a picture of that
    is worth nothing. X and Facebook draw the frame of a post and nothing
    inside it when they will not show it, so an empty box from them means the
    same as their sign-in wall.
    """
    if (str(found.get("href", "")).startswith("chrome-error:")
            or found.get("site") == "chromewebdata"):
        return ShotError(DID_NOT_OPEN, kind="gone")
    if found.get("blocked"):
        return ShotError(str(found["blocked"]), kind="sign-in")
    # A CARD WITH NO POST BEHIND IT. The site served the card and drew its own
    # words on it instead of the post: taken down, or never public. It is not
    # a sign-in wall - nobody signed in would see it either - so it is its own
    # answer, and capture_over tries the post's own page before anybody is
    # told, because somebody signed in may still be shown a friends-only post.
    if found.get("card") and embedcard.gone(str(found.get("cardText") or "")):
        return ShotError(NO_PUBLIC_POST, kind="card-gone")
    try:
        width, height = float(found["width"]), float(found["height"])
    except (KeyError, TypeError, ValueError):
        return ShotError(UNREADABLE, kind="not-a-story")
    if width < 80 or height < 80:
        host = (found.get("site") or "").lower()
        social = any(host == name or host.endswith("." + name) for name in SOCIAL_SITES)
        # A CARD THAT CAME TO NOTHING is never answered with "sign in". The
        # card is served to anybody, so a sign-in would not have helped; and a
        # site that changes the shape of its card one morning must not send
        # the whole office off to sign in to it. Called card-gone, which is
        # what capture_over tries the post's own page for.
        if found.get("card"):
            return ShotError(NO_PUBLIC_POST, kind="card-gone")
        if social:
            return ShotError(POST_NEEDS_SIGN_IN, kind="sign-in")
        return ShotError(NOT_A_STORY, kind="not-a-story")
    return None


def _find(page: _Wire) -> dict:
    from .blockjs import FIND_BLOCK

    try:
        raw = _evaluate(page, FIND_BLOCK, SCRIPT_SECONDS)
    except _ScriptFailed:
        raise ShotError(UNREADABLE, kind="not-a-story") from None
    if not raw:
        raise ShotError(UNREADABLE, kind="not-a-story")
    found = _json(raw)
    bad = refusal(found)
    if bad is not None:
        raise bad
    return found


def _clip_of(found: dict) -> dict:
    return {"x": float(found["x"]), "y": float(found["y"]),
            "width": float(found["width"]), "height": float(found["height"]),
            "scale": 1}


def _rgb(text: str) -> Optional[tuple]:
    """(r, g, b) from "rgb(r, g, b)" or "rgba(r, g, b, a)", or None - for a
    see-through colour, or any other way of writing one. Only rgb() is read:
    "oklch(0.97 0 0)", read as numbers, was painted black."""
    import re

    m = re.fullmatch(r"\s*rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)\s*(?:[,/]\s*([\d.]+)(%?)\s*)?\)\s*",
                     text or "")
    if not m:
        return None
    if m.group(4) is not None and float(m.group(4)) == 0:
        return None
    return tuple(max(0, min(255, int(round(float(n))))) for n in m.group(1, 2, 3))


def paint_margin(png: bytes, margin: dict, scale: float, background: str = "",
                 edges: Optional[dict] = None) -> bytes:
    """Paint back the padding the page's edge ate, in the page's own colour.

    A headline flush with the left edge of the page cannot have 16 pixels of
    page to its left, so the cutting would start at the letters. The strip is
    added here instead - at the sides in the page's background colour, not the
    colour most common at the edge, which for a photo flush with the edge is
    the photo. The same goes for the top and bottom, where the padding would
    have run into the next line of text: the cutting stops short of that line
    and the rest of the padding is painted - in `edges` "top" and "bottom",
    the colour behind what the cutting starts and ends at (a white story card
    on a grey page), or the page's colour where there is none.
    """
    import io

    margin = margin or {}
    left = int(round(float(margin.get("left", 0) or 0) * scale))
    right = int(round(float(margin.get("right", 0) or 0) * scale))
    top = int(round(float(margin.get("top", 0) or 0) * scale))
    bottom = int(round(float(margin.get("bottom", 0) or 0) * scale))
    if not (left > 0 or right > 0 or top > 0 or bottom > 0):
        return png
    left, right, top, bottom = max(0, left), max(0, right), max(0, top), max(0, bottom)
    from PIL import Image   # here, not at the top: nothing else in this module draws

    picture = Image.open(io.BytesIO(png)).convert("RGB")
    colour = _rgb(background) or (255, 255, 255)
    edges = edges or {}
    out = Image.new("RGB", (picture.width + left + right, picture.height + top + bottom), colour)
    if top > 0:
        out.paste(_rgb(edges.get("top", "")) or colour, (left, 0, left + picture.width, top))
    if bottom > 0:
        out.paste(_rgb(edges.get("bottom", "")) or colour,
                  (left, top + picture.height, left + picture.width, top + picture.height + bottom))
    out.paste(picture, (left, top))
    buffer = io.BytesIO()
    out.save(buffer, "PNG")
    return buffer.getvalue()


def _metrics(page: _Wire) -> dict:
    return _json(_evaluate(page, "JSON.stringify({sx: scrollX, sy: scrollY, iw: innerWidth, "
                                 "ih: innerHeight, cw: document.documentElement.clientWidth})",
                           CALL_SECONDS))


def _outside(found: dict, clip: dict) -> list:
    return [k for k in found.get("kept", [])
            if k["x"] < clip["x"] - 2 or k["right"] > clip["x"] + clip["width"] + 2
            or k["y"] < clip["y"] - 2 or k["bottom"] > clip["y"] + clip["height"] + 2]


class _LookAgain(Exception):
    """The page gave only the whole page to cut while it was still opening:
    it is prepared and looked at again (capture_over)."""


def _cut(page: _Wire, url: str, notes: dict, as_is: bool, patient=None,
         window: int = 0) -> Shot:
    """From a prepared page to a Shot: clear, find, wait, fit, shoot, check.

    `as_is` is the page somebody is looking at: its layout width is never
    changed and its videos are left alone. `patient`, when given, is asked
    whether a page that gives only itself to cut is worth another look; if it
    says so, nothing is pictured and _LookAgain is raised. `window` is how wide
    the page is laid out - PAGE_WIDE for a news page, and the card's own width
    for a post's card, which fills whatever it is given.
    """
    window = window or PAGE_WIDE
    from .blockjs import (CHECK_KEPT, CLEAR_CLUTTER, POSTER_FOR_PLAYER, SCROLL_TO,
                          WAIT_BLOCK)

    notes["clear"] = _json(_soft(page, CLEAR_CLUTTER, {"asIs": as_is}))
    found = _find(page)
    if patient is not None and found.get("kind") == "page" and patient():
        raise _LookAgain()
    notes["poster"] = _soft(page, POSTER_FOR_PLAYER, call=False)
    notes["waited"] = _json(_soft(page, WAIT_BLOCK, _clip_of(found), BLOCK_WAIT_MS,
                                  seconds=BLOCK_WAIT_MS / 1000 + SCRIPT_SECONDS))
    # CLEARED AGAIN, NOW THE PICTURES ARE IN. A cookie bar, a newsletter box or
    # an advert that needed its own picture arrives with them, after the first
    # clearing and after the cutting was measured. Cheap, and it hides nothing
    # it hid before; where it did hide something new, the cutting is measured
    # again, because the page under it has moved.
    later = _json(_soft(page, CLEAR_CLUTTER, {"asIs": as_is}), default={})
    notes["cleared_later"] = later.get("fresh", 0) if isinstance(later, dict) else 0
    if (notes["waited"].get("late") or str(notes["poster"]).startswith("poster")
            or notes["cleared_later"]):
        found = _find(page)

    # Measured once, before any fitting: how wide the page's window is inside
    # its scrollbar at 820, and how tall the window is.
    start = _metrics(page)
    # What the window is now, as far as the override goes: the background page
    # was set to 820 x 1500 before it was opened; a page somebody is looking at
    # keeps its own size unless its cutting is taller than its window.
    base_tall = PAGE_TALL if not as_is else int(start.get("ih") or PAGE_TALL)
    current = (window, PAGE_TALL) if not as_is else (0, 0)
    client_w = int(start.get("cw") or window)
    shot_data = b""
    moved = 0.0
    for attempt in (1, 2):
        clip = _clip_of(found)
        # Fit the window to the cutting. A picture taken inside the window
        # paints only the window, so a cutting wider or taller than it would
        # come out white where it overhangs.
        need_w = int(math.ceil(clip["x"] + clip["width"]))
        wide = current[0]
        if not as_is:
            wide = window
            if need_w > client_w:
                wide = min(max(need_w, int(found.get("docWidth") or need_w))
                           + (window - client_w), WIDEST)
        tall = max(base_tall, int(math.ceil(clip["height"])) + 40)
        want = (wide, tall if (not as_is or tall != base_tall) else 0)
        if want != current:
            page.call("Emulation.setDeviceMetricsOverride", seconds=CALL_SECONDS,
                      width=want[0], height=want[1], deviceScaleFactor=SHARPNESS,
                      mobile=False)
            current = want
        notes["viewport"] = [want[0] or int(start.get("iw") or 0), want[1] or base_tall]

        # Bring the page to the cutting, clear again (a feed or a wall can
        # arrive with the scroll) and measure again where it now is.
        _run(page, SCROLL_TO, max(0, int(clip["y"]) - 20), seconds=CALL_SECONDS)
        _soft(page, CLEAR_CLUTTER, {"asIs": as_is})
        found = _find(page)
        clip = _clip_of(found)
        here = _metrics(page)
        if clip["y"] < here.get("sy", 0) or clip["y"] + clip["height"] > here.get("sy", 0) + here.get("ih", 0):
            _run(page, SCROLL_TO, max(0, int(clip["y"]) - 5), seconds=CALL_SECONDS)
            here = _metrics(page)

        # Everything kept must be inside the cutting.
        outside = _outside(found, clip)
        if outside:
            doc_w = float(found.get("docWidth") or (clip["x"] + clip["width"]))
            left = max(0.0, min([clip["x"]] + [k["x"] - 2 for k in outside]))
            top = max(0.0, min([clip["y"]] + [k["y"] - 2 for k in outside]))
            right = min(doc_w, max([clip["x"] + clip["width"]] + [k["right"] + 2 for k in outside]))
            bottom = max([clip["y"] + clip["height"]] + [k["bottom"] + 2 for k in outside])
            bottom = min(bottom, top + MOST_TALL_CAP)
            clip.update(x=left, y=top, width=right - left, height=bottom - top)
            notes["kept_outside"] = [k["name"] for k in outside]
        sy, ih = float(here.get("sy", 0)), float(here.get("ih", 0))
        sx, cw = float(here.get("sx", 0)), float(here.get("cw", 0))
        beyond = not (clip["y"] >= sy - 0.5 and clip["y"] + clip["height"] <= sy + ih + 0.5
                      and clip["x"] >= sx - 0.5 and clip["x"] + clip["width"] <= sx + cw + 1)
        notes["beyond"] = beyond

        shot = page.call("Page.captureScreenshot", seconds=PAGE_SECONDS, format="png",
                         captureBeyondViewport=beyond, clip=clip)
        shot_data = base64.b64decode(shot["result"]["data"])

        # Nothing may have moved while the picture was taken.
        after = _json(_soft(page, CHECK_KEPT, call=False), default=[])
        moved = 0.0
        if isinstance(after, list):
            before = {k["name"]: k for k in found.get("kept", [])}
            for k in after:
                was = before.get(k.get("name"))
                if was and not str(k.get("name", "")).startswith("line"):
                    moved = max(moved, abs(k["x"] - was["x"]), abs(k["y"] - was["y"]),
                                abs(k["right"] - was["right"]))
        notes["moved"] = round(moved, 1)
        if moved <= MOVED_TOO_FAR or attempt == 2:
            break
        notes["taken_again"] = True
        found = _find(page)

    margin = found.get("margin") or {}
    notes["margin"] = margin
    notes["rails"] = found.get("rails", [])
    notes["found"] = {k: found.get(k) for k in ("kind", "x", "y", "width", "height", "docWidth",
                                                "clientWidth", "notes", "kept", "background", "edges")}
    data = paint_margin(shot_data, margin, SHARPNESS, found.get("background", ""), found.get("edges"))
    width = clip["width"] + float(margin.get("left", 0) or 0) + float(margin.get("right", 0) or 0)
    height = (clip["height"] + float(margin.get("top", 0) or 0)
              + float(margin.get("bottom", 0) or 0))
    return Shot(png=data, url=url or found.get("href", ""),
                title=(found.get("title") or "").strip(),
                site=found.get("site", ""), kind=found.get("kind", "story"),
                width=int(round(width)), height=int(round(height)), notes=notes)


#: The tallest a cutting grows to take in a kept thing that fell outside it.
MOST_TALL_CAP = 2232


def _unstick(page: _Wire) -> bool:
    """Send the background page to a blank page, which unsticks it at once
    (measured: Qt's engine on hindustantimes.com). Answers whether the page
    runs a script again; if not, the wire is marked stuck for its owner to
    start afresh. Only ever for a page nobody is looking at."""
    try:
        page.call("Page.navigate", url="about:blank", seconds=5.0)
    except ShotError:
        pass
    ok = answers(page, 3.0)
    page.stuck = not ok
    return ok


def capture_over(page: _Wire, url: str, settle: float = SETTLE_SECONDS) -> Shot:
    """One page, as a cutting, over any DevTools wire - headless Chrome's or
    the embedded browser's parked page. Raises ShotError, never anything else.

    A LINK TO A POST OPENS THE POST'S PUBLIC CARD (core/embedcard), not the
    post's own page: the card is the same post as the site hands a newspaper
    quoting it, it is served to a browser that has never signed in to
    anything, and it carries the post alone - no feed, no wall, no "open in
    the app". Nobody has to sign in to anything to capture the morning. Only
    the address OPENED changes: the cutting keeps the post's own link, and its
    own site, which is what the report prints. Where the card says there is no
    public post behind the address, the post's own page is tried after it, the
    old way, because somebody who IS signed in may still be shown it.

    The page is opened at 820 pixels, prepared (its structure, its lazy
    pictures, its fonts), cleared of adverts and walls, measured, fitted and
    pictured inside the window. A page that stops answering is sent to a blank
    page - this is the background page, never one somebody is reading - and
    the link fails in plain words.

    Before the link is opened, the page the last link left behind must answer:
    one that stopped answering after its own capture is unstuck first, and if
    it cannot be, the ShotError is `unopened`, for the owner to start afresh
    and try this link again. A page that, a moment after it opened, gives
    nothing to cut, only itself, or a sign-in wall is looked at again once it
    is a few seconds old (see _look_again).
    """
    card = embedcard.card_for(url)
    if card is None and embedcard.needs_resolving(url):
        # A share link. Opened once, on the page that is about to do the
        # capture anyway, to see which post it stands for; whatever the page
        # then shows - the post, or a wall - the address it came to rest at is
        # the post's own, and that is what the card is asked for. Nothing is
        # signed in to, and if it does not move, the link is captured as it is.
        real = _resolve(page, url)
        if real:
            card = embedcard.card_for(real)
            if card is not None:
                notes_first = {"stood_for": real}
                try:
                    shot = _capture_at(page, card.url, url, settle, card=card)
                except ShotError as bad:
                    if bad.kind not in ("card-gone", "not-a-story", "gone"):
                        raise
                    try:
                        shot = _capture_at(page, real, url, settle)
                    except ShotError:
                        raise bad from None
                    notes_first.update(card_first=card.url, card_failed=str(bad))
                shot.notes.update(notes_first)
                return shot
    if card is None:
        # No card for this one. It is still opened the way a computer would
        # ask for it, so a link copied on a phone does not bring a page laid
        # out for a phone with "open in the app" across the top of it.
        return _capture_at(page, embedcard.desktop_form(url), url, settle)
    notes_of = {}
    try:
        shot = _capture_at(page, card.url, url, settle, card=card)
    except ShotError as bad:
        if bad.kind not in ("card-gone", "not-a-story", "gone"):
            raise
        # The card came to nothing. The post's own page is tried once, the way
        # it was tried before there were cards: a post shown only to friends
        # is there for somebody signed in, and a site that changes the shape
        # of its cards one morning must not take the morning with it.
        notes_of = {"card_first": card.url, "card_failed": str(bad)}
        try:
            shot = _capture_at(page, url, url, settle)
        except ShotError:
            raise bad from None
    shot.notes.update(notes_of)
    return shot


#: How long a share link is given to arrive at the post it stands for, and
#: how often it is asked. A redirect through the site's own page takes about a
#: second; anything slower than this is not worth holding a list of twelve up
#: for, and the link is then captured as it was sent.
RESOLVE_SECONDS = 6.0
RESOLVE_WAIT = 0.6


def _resolve(page: _Wire, url: str) -> str:
    """Which post a share link stands for: the address the browser comes to
    rest at. "" when it does not move, or cannot be opened."""
    try:
        page.call("Emulation.setDeviceMetricsOverride", seconds=CALL_SECONDS,
                  width=PAGE_WIDE, height=PAGE_TALL, deviceScaleFactor=1,
                  mobile=False)
        page.call("Page.navigate", url=url, seconds=PAGE_SECONDS)
    except ShotError:
        return ""
    until = time.time() + RESOLVE_SECONDS
    while time.time() < until:
        time.sleep(RESOLVE_WAIT)
        try:
            here = _json(_evaluate(page, _WHICH_PAGE, CALL_SECONDS)) or {}
        except (_ScriptFailed, ShotError):
            return ""
        found = embedcard.resolved(str(here.get("href") or ""))
        if found:
            return found
    return ""


def _capture_at(page: _Wire, opening: str, keep: str,
                settle: float = SETTLE_SECONDS, card=None) -> Shot:
    """`opening` is opened; the cutting is filed under `keep`. The two differ
    only for a post captured through its public card."""
    from .blockjs import PREPARE_PAGE

    began = time.time()
    notes: dict = {"card": card.note} if card is not None else {}
    window = card.window if card is not None else PAGE_WIDE
    looked: set = set()
    stilled = ""
    try:
        try:
            if not answers(page, ANSWER_SECONDS):
                notes["unstuck_first"] = True
                if not _unstick(page):
                    raise ShotError(LEFT_STUCK, kind="stopped", unopened=True)
            page.call("Emulation.setDeviceMetricsOverride", seconds=CALL_SECONDS,
                      width=window, height=PAGE_TALL, deviceScaleFactor=SHARPNESS,
                      mobile=False)
            if card is not None:
                # BEFORE THE CARD'S OWN SCRIPTS RUN, which is the whole point:
                # run in the page after navigating, this landed on the document
                # being left rather than the one arriving, and the card's player
                # was built unpatched (measured: six of six still lost). Asked
                # for on the NEXT document, it is the first thing that runs
                # there. Taken off again afterwards so the page somebody opens
                # in the browser window is never touched by it.
                from .blockjs import STILL_THE_VIDEO
                try:
                    told = page.call("Page.addScriptToEvaluateOnNewDocument",
                                     seconds=CALL_SECONDS, source=STILL_THE_VIDEO)
                    stilled = told.get("result", {}).get("identifier", "")
                    notes["stilled"] = bool(stilled)
                except ShotError:
                    stilled = ""            # an engine without it loses nothing
            page.call("Page.navigate", url=opening, seconds=PAGE_SECONDS)
            time.sleep(max(0.5, settle))
            for step in range(1, MOVES + 1):
                notes["prepare"] = _json(_soft(page, PREPARE_PAGE, PREPARE_LIMITS,
                                               seconds=PREPARE_SECONDS))
                patient = (lambda: _look_again(page, notes, looked)) if step < MOVES else None
                try:
                    shot = _cut(page, keep, notes, as_is=False, patient=patient,
                                window=window)
                    break
                except _LookAgain:
                    notes.setdefault("looked_again", []).append("page")
                except ShotError as bad:
                    if (bad.kind not in ("not-a-story", "sign-in") or str(bad) == MOVED_ON
                            or step == MOVES or not _look_again(page, notes, looked)):
                        raise
                    notes.setdefault("looked_again", []).append(bad.kind)
        except (KeyError, TypeError, ValueError, _ScriptFailed) as bad:
            raise ShotError(f"{UNREADABLE} ({bad})", kind="not-a-story") from None
    except ShotError as bad:
        if bad.kind != "stopped" or bad.unopened:
            raise
        if str(bad) == WIRE_CLOSED:
            page.stuck = True          # nothing more will come down this wire
            raise
        _unstick(page)
        raise ShotError(STOPPED, kind="stopped") from None
    finally:
        if stilled:
            try:
                page.call("Page.removeScriptToEvaluateOnNewDocument",
                          seconds=CALL_SECONDS, identifier=stilled)
            except ShotError:
                pass
    if card is not None:
        # The card's own address is platform.twitter.com; the post is X's.
        # The cutting is filed under the site the office was sent.
        shot.site = card.site
        shot.kind = "post"
    shot.notes["seconds"] = round(time.time() - began, 2)
    return shot


#: Which document the page is showing, and how long ago it opened.
_WHICH_PAGE = ("JSON.stringify({href: location.href, since: performance.timeOrigin,"
               " age: performance.now()})")


def _look_again(page: _Wire, notes: dict, looked: set) -> bool:
    """Whether a page that gave nothing worth cutting is to be prepared and
    looked at once more - answered after waiting until it is YOUNG_SECONDS old.

    Two sorts of page are young when first looked at. One is on its way to
    another: a "taking you to the story" page that sends itself on a second and
    a half later was refused at 1.2 s (2.0.31, which waited 2.5 s before
    looking, captured it). The other draws its story with its own script after
    it opens: a story put in at 1.8 s was pictured as its grey "Loading" box,
    and a post drawn at 1.2 s or later was refused as needing a sign-in. Each
    document is waited for once, and only while it is young, so a page that
    really is empty, or really wants a sign-in, is held up by a second or two
    at most.
    """
    try:
        first = _json(_evaluate(page, _WHICH_PAGE, CALL_SECONDS))
    except _ScriptFailed:
        return False
    if not first:
        return False
    which = (first.get("href"), first.get("since"))
    age = float(first.get("age") or 0) / 1000.0
    if age > YOUNG_SECONDS or which in looked:
        return False
    looked.add(which)
    time.sleep(max(MOVE_WAIT, YOUNG_SECONDS - age))
    try:
        now = _json(_evaluate(page, _WHICH_PAGE, CALL_SECONDS))
    except _ScriptFailed:
        return True
    if (now.get("href"), now.get("since")) != which:
        notes.setdefault("moved_on", []).append(str(now.get("href", ""))[:160])
    return True


def capture_current(page: _Wire, url: str = "", restore: bool = True) -> Shot:
    """The page as it is on the screen now, as a cutting - for the browser
    window, where somebody has the page open, has scrolled it, perhaps closed
    its pop-up, and its pictures have loaded.

    Nothing navigates and nothing scrolls through the page. Scrollbars are
    hidden for the picture only. Every change made to the page - adverts
    hidden, a rail blanked, a player's still put in, the scroll - is written
    down on the elements themselves and undone afterwards, whatever happened
    (RESTORE_PAGE, in a finally). A page that stops answering is never sent to
    a blank page: it is the person's. Its own alert boxes are left for them to
    answer. A page that goes on to another page while it is being pictured is
    refused as "changed", never pictured under the first page's link.
    """
    from .blockjs import PREPARE_PAGE, RESTORE_PAGE

    began = time.time()
    notes: dict = {"as_is": True}
    saved: dict = {}
    which: dict = {}
    stuck = changed = False
    was = (getattr(page, "answer_dialogs", True), getattr(page, "stay", False))
    page.answer_dialogs, page.stay = False, True
    try:
        try:
            saved = _metrics(page)
            # Which document this is: a click in the window, or the page's own
            # script, can open another while the capture runs.
            which = _json(_evaluate(page, _WHICH_PAGE, CALL_SECONDS))
            try:
                page.call("Emulation.setScrollbarsHidden", seconds=CALL_SECONDS, hidden=True)
            except ShotError as bad:
                if bad.kind == "stopped":
                    raise
            page.call("Emulation.setDeviceMetricsOverride", seconds=CALL_SECONDS,
                      width=0, height=0, deviceScaleFactor=SHARPNESS, mobile=False)
            notes["prepare"] = _json(_soft(page, PREPARE_PAGE,
                                           {"scroll": False, "promote": False, "domMs": 1000,
                                            "imageMs": PREPARE_LIMITS["imageMs"],
                                            "fontsMs": PREPARE_LIMITS["fontsMs"]},
                                           seconds=PREPARE_SECONDS))
            shot = _cut(page, url, notes, as_is=True)
            # A page opened between two scripts runs the rest of them without
            # complaint, and the picture is of it: the document is asked again.
            now = _json(_evaluate(page, _WHICH_PAGE, CALL_SECONDS))
            if which and now.get("since") != which.get("since"):
                raise ShotError(PAGE_CHANGED, kind="changed")
        except (KeyError, TypeError, ValueError, _ScriptFailed) as bad:
            raise ShotError(f"{UNREADABLE} ({bad})", kind="not-a-story") from None
    except ShotError as bad:
        if bad.kind == "stopped":
            stuck = True
            raise ShotError(STOPPED_HERE, kind="stopped") from None
        changed = bad.kind == "changed"
        raise
    finally:
        if restore:
            # Sent even to a page that stopped answering, with a short limit:
            # the page runs it the moment it comes back, so a page that was
            # only busy is not left with its adverts and header hidden. A page
            # somebody went on to is not scrolled to where the first one was.
            try:
                where = ({"x": saved.get("sx", 0), "y": saved.get("sy", 0)}
                         if saved and not changed else None)
                notes["restored"] = _json(_run(page, RESTORE_PAGE, where,
                                               seconds=2.0 if stuck else CALL_SECONDS))
            except (ShotError, _ScriptFailed) as bad:
                notes["restored"] = {"failed": str(bad)}
                stuck = stuck or getattr(bad, "kind", "") == "stopped"
        # The scrollbars are given back BEFORE the override is cleared.
        # Measured on Qt's own page (fixC2/probe_bar2.py, a window shorter than
        # its cutting): hidden, overridden taller, then cleared and shown again,
        # the page kept no scrollbar until the window was next resized; shown
        # again first, it keeps it. An override alone, or no hiding, keeps it.
        for method, params in (("Emulation.setScrollbarsHidden", {"hidden": False}),
                               ("Emulation.clearDeviceMetricsOverride", {})):
            try:
                page.call(method, seconds=2.0 if stuck else CALL_SECONDS, **params)
            except ShotError:
                pass
        page.answer_dialogs, page.stay = was
    shot.notes["seconds"] = round(time.time() - began, 2)
    return shot


def sign_in(url: str = "https://x.com/login") -> subprocess.Popen:
    """Open a real browser window, on the program's own settings, so somebody
    can sign in once. What they sign into is remembered for later captures.

    Deliberately their own doing: the program never asks for a password and
    never sees one - the sign-in happens in the browser, as it always does.
    """
    path = find_browser()
    if not path:
        raise ShotError(NO_BROWSER)
    apply_sign_out_mark()
    process = subprocess.Popen(
        [path, f"--user-data-dir={browser_folder()}", "--no-first-run",
         "--no-default-browser-check", f"--window-size=1100,900", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _STARTED.append(process)
    return process


#: The program's own Chrome processes started from here, so a sign-out knows
#: not to write to a cookie file that one of them has open.
_STARTED: list = []
#: Left in the program's Chrome folder when a sign-out has to wait for its
#: Chrome to close: carried out before that Chrome next starts.
SIGN_OUT_MARK = "sign-out-on-start.json"


def chrome_cookie_file() -> Path:
    """The cookie file of the program's own Chrome - inside browser_folder(),
    never the person's everyday Chrome, which is not read or touched."""
    return browser_folder() / "Default" / "Network" / "Cookies"


def chrome_running() -> bool:
    """Whether the program's own Chrome is open now: one this program started
    is still running, or something holds its cookie file."""
    from . import sitedata

    _STARTED[:] = [p for p in _STARTED if p.poll() is None]
    return bool(_STARTED) or sitedata.in_use(chrome_cookie_file())


def signed_in_sites(store: Optional[Path] = None) -> list[str]:
    """Which sites the program's own browser has a sign-in for.

    Read from the cookie file's names only - never the values, which are the
    keys to those accounts - and decided by the name of each site's sign-in
    cookie: a site that has only been visited is not signed in. While the
    program's Chrome is open, what it was last read to keep (chrome_kept).
    """
    from . import sitedata

    if store is None:
        lines, _open = chrome_kept()
        return sorted(line.site for line in lines if line.signed_in)
    return sitedata.Jar(sitedata.read_cookie_file(store)).signed_in_sites()


#: What the program's own Chrome was last read to keep, site by site - names,
#: counts and dates, never a value. That Chrome holds its cookie file for
#: itself alone while it is open, and a read then gets nothing: the ☰ panel
#: said "It keeps nothing" during a sign-in window (review of step B).
_LAST_KEPT: list = []


def chrome_kept() -> tuple[list, bool]:
    """What the program's own Chrome keeps, site by site (sitedata.SiteSummary),
    and whether that Chrome is open now. While it is open its cookie file
    cannot be read, and the lines are the ones last read in this session - []
    when none were."""
    from . import sitedata

    store = chrome_cookie_file()
    if sitedata.in_use(store):
        return list(_LAST_KEPT), True
    lines = sitedata.Jar(sitedata.read_cookie_file(store)).summary()
    _LAST_KEPT[:] = lines
    return lines, chrome_running()


def chrome_sites() -> list:
    """What the program's own Chrome keeps, site by site (sitedata.SiteSummary)."""
    return chrome_kept()[0]


def sign_out_of_chrome(site: str = "") -> str:
    """Remove one site's cookies from the program's own Chrome ("" for every
    site). "done", or "next-start" when that Chrome is open and the removal
    has to wait until before it next starts."""
    from . import sitedata

    if chrome_running() or sitedata.remove_cookies(chrome_cookie_file(), site) < 0:
        sitedata.mark_for_next_start(browser_folder() / SIGN_OUT_MARK, site)
        # What is shown while it waits is what it will be.
        _LAST_KEPT[:] = [line for line in _LAST_KEPT if site and line.site != site]
        return "next-start"
    return "done"


def apply_sign_out_mark() -> bool:
    """A sign-out that waited for the program's Chrome to close, done now,
    before it starts again. True when there was one and it is done."""
    from . import sitedata

    mark = browser_folder() / SIGN_OUT_MARK
    if not mark.is_file() or chrome_running():
        return False
    return sitedata.apply_mark(mark, chrome_cookie_file())
