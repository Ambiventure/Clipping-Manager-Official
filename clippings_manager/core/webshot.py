"""Taking a picture of a web page, using the Chrome already on the machine.

Paste a link and the program should hand back a cutting: the headline, the
picture and the first inches of the story - not the whole page with its menus,
adverts and cookie bars. That is what this does.

HOW, AND WHY THIS WAY. The Chrome on the PC is started with no window, pointed
at its own folder of settings, and driven over the debugging port it opens for
exactly this purpose. Nothing is installed, the hand-over copy does not grow,
and the browser is the one the office already trusts. The page itself is asked
where its story is - a script runs inside the page and measures the headline,
the picture and the first run of text - and only that rectangle is captured.

THE WINDOW IS NARROW ON PURPOSE. At 820 pixels across, a news site lays itself
out in one column: no advert rail beside the story, nothing to crop away. Wide,
the same page puts "you may like" next to the headline and the cutting has to
be cut again.

IT IS NEVER YOUR OWN CHROME. The program keeps its own settings folder, so the
Chrome you have open - with WhatsApp Web in it - is not touched, not closed,
and not read. Signing in to X or Facebook for the program is done once, in a
window it opens itself, and that sign-in lives only in that folder.

Nothing here runs unless somebody asks for a link to be captured.
"""

from __future__ import annotations

import base64
import json
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

#: How wide the page is laid out, in CSS pixels. See the note above.
PAGE_WIDE = 820
PAGE_TALL = 1500
#: Two device pixels per CSS pixel: a cutting has to stand being printed.
SHARPNESS = 2
#: How long to wait for the page itself, and for the browser to start.
PAGE_SECONDS = 25.0
START_SECONDS = 30.0
#: After "loaded", pages still move things about for a moment.
SETTLE_SECONDS = 2.5

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


class ShotError(Exception):
    """Something went wrong for one link. Its message is for the person."""


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
    """

    def __init__(self, url: str, seconds: float = 30.0):
        rest = url.split("://", 1)[1]
        host_port, _, path = rest.partition("/")
        host, _, port = host_port.partition(":")
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
                raise ShotError("the browser would not answer")
            head += piece
        if b" 101" not in head.split(b"\r\n")[0]:
            raise ShotError("the browser refused the connection")
        self.rest = b""
        self.count = 0

    def close(self) -> None:
        try:
            self.sock.close()
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

    def _take(self, many: int) -> bytes:
        while len(self.rest) < many:
            more = self.sock.recv(1 << 16)
            if not more:
                raise ShotError("the browser closed while the page was read")
            self.rest += more
        out, self.rest = self.rest[:many], self.rest[many:]
        return out

    def _message(self) -> dict:
        _first, second = self._take(2)
        size = second & 0x7F
        if size == 126:
            size = struct.unpack(">H", self._take(2))[0]
        elif size == 127:
            size = struct.unpack(">Q", self._take(8))[0]
        try:
            return json.loads(self._take(size))
        except ValueError:
            return {}

    def wait(self, message_id: int, seconds: float) -> dict:
        until = time.time() + seconds
        while time.time() < until:
            message = self._message()
            if message.get("id") == message_id:
                if "error" in message:
                    raise ShotError(str(message["error"].get("message", "refused")))
                return message
        raise ShotError("the page took too long")

    def call(self, method: str, seconds: float = 30.0, **params) -> dict:
        return self.wait(self.send(method, **params), seconds)


# -------------------------------------------------------------------- browser
@dataclass
class Shot:
    """One captured page."""

    png: bytes
    url: str
    title: str = ""
    site: str = ""
    kind: str = "story"          # story | post | page
    width: int = 0
    height: int = 0


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
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/list",
                                    timeout=20) as answer:
            targets = json.loads(answer.read())
        pages = [t for t in targets if t.get("type") == "page"]
        if not pages:
            raise ShotError("the browser opened no page")
        self.wire = _Wire(pages[0]["webSocketDebuggerUrl"])
        self.wire.call("Page.enable")
        self.wire.call("Runtime.enable")
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
        from .blockjs import FIND_BLOCK

        if not self.running:
            self.start()
        page = self._page()
        page.call("Emulation.setDeviceMetricsOverride", width=PAGE_WIDE,
                  height=PAGE_TALL, deviceScaleFactor=SHARPNESS, mobile=False)
        page.call("Page.navigate", url=url, seconds=PAGE_SECONDS)
        time.sleep(max(0.5, settle))
        answer = page.call("Runtime.evaluate", expression=FIND_BLOCK,
                           returnByValue=True, seconds=PAGE_SECONDS)
        raw = (answer.get("result", {}).get("result", {}) or {}).get("value")
        if not raw:
            raise ShotError("the page could not be read")
        found = json.loads(raw)
        # A page that never arrived - no network, a wrong link, or a site that
        # turned us away - leaves Chrome showing its own error page. A picture
        # of that is worth nothing, so it is said instead.
        if (found.get("href", "").startswith("chrome-error:")
                or found.get("site") == "chromewebdata"):
            raise ShotError("that page did not open. Check the link, or open it "
                            "in your browser to see what it says.")
        if found.get("blocked"):
            raise ShotError(found["blocked"])
        clip = {"x": float(found["x"]), "y": float(found["y"]),
                "width": float(found["width"]), "height": float(found["height"]),
                "scale": 1}
        if clip["width"] < 80 or clip["height"] < 80:
            # X and Facebook draw the frame of a post and nothing inside it
            # when they will not show it, so an empty box means the same as
            # their sign-in wall.
            host = (found.get("site") or "").lower()
            social = any(host == name or host.endswith("." + name) for name in
                         ("x.com", "twitter.com", "facebook.com", "instagram.com",
                          "threads.net"))
            raise ShotError(
                "that post could not be read. Either it needs you to be signed "
                'in - use "Sign in for captures" once - or the post has been '
                "taken down." if social else
                "nothing on that page looked like a story")
        shot = page.call("Page.captureScreenshot", format="png",
                         captureBeyondViewport=True, clip=clip,
                         seconds=PAGE_SECONDS)
        data = base64.b64decode(shot["result"]["data"])
        return Shot(png=data, url=url, title=(found.get("title") or "").strip(),
                    site=found.get("site", ""), kind=found.get("kind", "story"),
                    width=int(clip["width"]), height=int(clip["height"]))

    def __enter__(self) -> "Browser":
        self.start()
        return self

    def __exit__(self, *_args) -> None:
        self.stop()


def sign_in(url: str = "https://x.com/login") -> subprocess.Popen:
    """Open a real browser window, on the program's own settings, so somebody
    can sign in once. What they sign into is remembered for later captures.

    Deliberately their own doing: the program never asks for a password and
    never sees one - the sign-in happens in the browser, as it always does.
    """
    path = find_browser()
    if not path:
        raise ShotError(NO_BROWSER)
    return subprocess.Popen(
        [path, f"--user-data-dir={browser_folder()}", "--no-first-run",
         "--no-default-browser-check", f"--window-size=1100,900", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def signed_in_sites() -> list[str]:
    """Which sites the program's own browser has a sign-in for.

    Read from the cookie file's names only - never the values, which are the
    keys to those accounts.
    """
    import sqlite3

    found: set[str] = set()
    store = browser_folder() / "Default" / "Network" / "Cookies"
    if not store.is_file():
        return []
    copy = store.with_suffix(".reading")
    try:
        shutil.copyfile(store, copy)
        with sqlite3.connect(f"file:{copy}?mode=ro", uri=True) as db:
            for (host,) in db.execute("SELECT DISTINCT host_key FROM cookies"):
                host = (host or "").lstrip(".")
                for known in ("x.com", "twitter.com", "facebook.com", "instagram.com"):
                    if host == known or host.endswith("." + known):
                        found.add(known)
    except Exception:  # noqa: BLE001 - it is only a hint on a button
        return sorted(found)
    finally:
        try:
            copy.unlink()
        except OSError:
            pass
    return sorted(found)
