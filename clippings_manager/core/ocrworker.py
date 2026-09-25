"""Reading headlines in a process of its own, never on the window's thread.

Pressing "read again" used to run the whole reading - OpenCV, then Tesseract -
on the thread that draws the window, and the window stopped for as long as it
took: a second, or five on a large scan. The duplicate check read on threads of
its own, but in the same process, where the finder's Python can still hold the
window up between Tesseract's long stretches of letting go.

So reading is done by helper processes. Each is this same program started a
second time with ``--ocr-worker``, which loads Tesseract and OpenCV and nothing
else - no window, no Qt - and answers requests over a local Windows pipe. A
picture goes in; the words come back. If a helper crashes on a bad picture it
takes only itself down: the request comes back empty and the next one starts a
fresh helper.

The pipe is a named pipe on this machine (\\\\.\\pipe\\...), guarded by a key
made afresh each run. Nothing here touches the network.

If no helper can be started at all, callers read the old way on a thread of
their own - see ``available`` - so a machine where this fails reads slower, not
never.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

#: How many helpers at most. Each carries its own Tesseract and OpenCV - about
#: 150 MB - and two already read faster than the four in-process readers did,
#: because each reading is now a small region rather than half a page.
MOST = 2

#: How long a helper has to start and say hello. The first start on a cold
#: machine loads OpenCV, NumPy and Tesseract's language data.
START_TIMEOUT = 40.0

#: How long one reading may take before the helper is thought stuck, and is
#: stopped and replaced.
READ_TIMEOUT = 60.0

#: The flag that turns this program into a helper - see main.py.
FLAG = "--ocr-worker"


# ============================================================ the helper side
def serve(address: str, key_hex: str) -> int:
    """Run as a helper: answer reading requests until told to stop."""
    from multiprocessing.connection import Client

    try:
        conn = Client(address, family="AF_PIPE", authkey=bytes.fromhex(key_hex))
    except Exception:  # noqa: BLE001 - the program went away before we came up
        return 2
    try:
        from . import ocr

        conn.send(("hello", ocr.available(), ocr.why_not()))
        while True:
            try:
                message = conn.recv()
            except (EOFError, OSError):
                return 0
            kind = message[0] if message else ""
            if kind == "stop":
                return 0
            try:
                if kind == "headline":
                    found = ocr.headline(message[1])
                    conn.send(("ok", found.text, found.confidence, found.engine))
                elif kind == "region":
                    found = ocr.read_box(message[1], message[2])
                    conn.send(("ok", found.text, found.confidence, found.engine))
                else:
                    conn.send(("error", f"unknown request {kind!r}"))
            except Exception as bad:  # noqa: BLE001 - one picture, not the helper
                conn.send(("error", str(bad)))
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


# ============================================================ the program side
def _command(address: str, key_hex: str) -> tuple:
    """How to start a helper: the packaged program itself, or Python."""
    if getattr(sys, "frozen", False):
        return [sys.executable, FLAG, address, key_hex], None
    root = str(Path(__file__).resolve().parents[2])
    return ([sys.executable, "-m", "clippings_manager.core.ocrworker",
             address, key_hex], root)


class Helper:
    """One helper process and the pipe to it. One request at a time."""

    def __init__(self):
        self.proc = None
        self.conn = None
        self.lock = threading.Lock()
        self.dead = False

    def _start(self) -> bool:
        from multiprocessing.connection import Listener

        key = secrets.token_bytes(24)
        address = (r"\\.\pipe\clippings-manager-ocr-"
                   f"{os.getpid()}-{secrets.token_hex(6)}")
        listener = Listener(address, family="AF_PIPE", authkey=key)
        command, cwd = _command(address, key.hex())
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.proc = subprocess.Popen(
                command, cwd=cwd, creationflags=flags,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
        except Exception:  # noqa: BLE001 - it cannot be started at all
            listener.close()
            return False
        accepted = {}

        def accept():
            try:
                accepted["conn"] = listener.accept()
            except Exception:  # noqa: BLE001 - it never called back
                pass

        waiter = threading.Thread(target=accept, daemon=True)
        waiter.start()
        waiter.join(START_TIMEOUT)
        conn = accepted.get("conn")
        if conn is None:
            self._kill()
            try:
                listener.close()
            except Exception:  # noqa: BLE001
                pass
            return False
        listener.close()
        try:
            if not conn.poll(START_TIMEOUT):
                raise TimeoutError("no hello")
            hello = conn.recv()
            if not hello or hello[0] != "hello" or not hello[1]:
                raise RuntimeError(f"no reader in the helper: {hello!r}")
        except Exception:  # noqa: BLE001 - a helper that cannot read is no help
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            self._kill()
            return False
        self.conn = conn
        return True

    def _kill(self) -> None:
        proc, self.proc = self.proc, None
        if proc is not None:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        conn, self.conn = self.conn, None
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def call(self, message, timeout: float = READ_TIMEOUT):
        """Send one request and wait for its answer. None when it failed."""
        with self.lock:
            if self.conn is None and not self._start():
                self.dead = True
                return None
            try:
                self.conn.send(message)
                if not self.conn.poll(timeout):
                    raise TimeoutError("reading took too long")
                answer = self.conn.recv()
            except Exception:  # noqa: BLE001 - crashed or stuck: start afresh
                self._kill()
                return None
            if not answer or answer[0] != "ok":
                return None
            return answer

    def stop(self) -> None:
        with self.lock:
            if self.conn is not None:
                try:
                    self.conn.send(("stop",))
                except Exception:  # noqa: BLE001
                    pass
            proc = self.proc
            if proc is not None:
                try:
                    proc.wait(timeout=2)
                except Exception:  # noqa: BLE001
                    pass
            self._kill()


class Pool:
    """A few helpers, lent out one caller at a time."""

    def __init__(self, size: int = MOST):
        self.size = max(1, int(size))
        self.helpers = [Helper() for _ in range(self.size)]
        self.idle = list(self.helpers)
        self.ready = threading.Condition()
        self.broken = False

    def _borrow(self) -> Helper:
        with self.ready:
            while not self.idle:
                self.ready.wait()
            return self.idle.pop()

    def _give_back(self, helper: Helper) -> None:
        with self.ready:
            self.idle.append(helper)
            self.ready.notify()

    def ask(self, message):
        helper = self._borrow()
        try:
            answer = helper.call(message)
            if answer is None and helper.dead:
                self.broken = all(h.dead for h in self.helpers)
            return answer
        finally:
            self._give_back(helper)

    def close(self) -> None:
        for helper in self.helpers:
            helper.stop()


_pool: Optional[Pool] = None
_pool_lock = threading.Lock()
_started_at = 0.0


def pool() -> Pool:
    global _pool, _started_at
    with _pool_lock:
        if _pool is None:
            _pool = Pool()
            _started_at = time.monotonic()
        return _pool


def available() -> bool:
    """Whether helpers can be used - False once none of them would start."""
    return not (_pool is not None and _pool.broken)


def _headline(answer):
    from .ocr import Headline

    if not answer:
        return None
    _ok, text, confidence, engine = answer
    return Headline(text or "", int(confidence or 0), engine or "")


def read_headline(data: bytes):
    """The headline of a clipping's picture, read by a helper.

    Blocks until the answer is back, so it is for background threads only.
    None when no helper could read it - the caller then reads the old way.
    """
    if not data or not available():
        return None
    return _headline(pool().ask(("headline", data)))


def read_box(data: bytes, box: tuple):
    """The words inside one box of a picture - the preview's OCR box."""
    if not data or not available():
        return None
    return _headline(pool().ask(("region", data, tuple(box))))


def shutdown() -> None:
    """Stop every helper. Called as the program closes."""
    global _pool
    with _pool_lock:
        current, _pool = _pool, None
    if current is not None:
        current.close()


if __name__ == "__main__":
    # Started as "python -m clippings_manager.core.ocrworker <pipe> <key>"
    # when the program runs from source.
    raise SystemExit(serve(sys.argv[1], sys.argv[2]))
