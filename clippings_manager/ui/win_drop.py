"""Reading a drag the way Explorer does, on Windows.

Chrome hands a dragged image over as ``FileGroupDescriptorW`` plus ``FileContents``,
and delivers the contents as a **COM stream**. Qt only ever asks for memory-block
formats, so from Qt's side ``FileContents`` looks present but empty — which is why
the same drag saves fine into a folder and arrived here as nothing at all.

There is no way to add a format converter to Qt from Python, so this registers a
real ``IDropTarget`` on one widget's own window handle and reads the stream itself.
Only that widget is taken over; the rest of the window keeps Qt's drag and drop, so
dragging rows around to reorder them is untouched.

Everything here is Windows-only and entirely local. If pywin32 is missing, or
registration fails, the caller simply keeps Qt's behaviour.
"""

from __future__ import annotations

import sys
from typing import Callable, Optional

Available = False
if sys.platform == "win32":
    try:
        import pythoncom
        import win32clipboard
        import win32con
        from win32com.server import util as _com_util

        Available = True
    except ImportError:  # pragma: no cover - pywin32 not installed
        Available = False

# What the browser offers, and what we ask for.
CF_FILEDESCRIPTORW = 0
CF_FILECONTENTS = 0
if Available:
    CF_FILEDESCRIPTORW = win32clipboard.RegisterClipboardFormat("FileGroupDescriptorW")
    CF_FILECONTENTS = win32clipboard.RegisterClipboardFormat("FileContents")

DROPEFFECT_NONE = 0
DROPEFFECT_COPY = 1

CF_HDROP = 15

# What our own drags carry. A drag that has one of these started inside the app -
# a row being reordered, or a card being moved between sentiment columns - and its
# meaning belongs to Qt, not to us.
INTERNAL_FORMATS = (
    "application/x-clippings-rows",
    "application/x-clippings-cards",
)

MAGIC = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"BM", ".bmp"),
    (b"II*\x00", ".tif"),
    (b"MM\x00*", ".tif"),
)


def _screen_point(point) -> tuple[int, int]:
    """Where the drop landed, in screen coordinates.

    pywin32 hands POINTL to a gateway as a plain (x, y) tuple, not as an object
    with .x and .y - reading it the other way raises inside Drop, and the whole
    drop is refused with nothing to show for it.
    """
    try:
        return (int(point[0]), int(point[1]))
    except Exception:  # noqa: BLE001 - some builds may hand over an object
        try:
            return (int(point.x), int(point.y))
        except Exception:  # noqa: BLE001
            return (0, 0)


def _paths_from_dropfiles(raw: bytes) -> list[str]:
    """Parse a DROPFILES block, which is how CF_HDROP actually arrives.

    pywin32 returns the raw structure as bytes rather than a list of names, so
    the obvious isinstance checks all miss and a real file drag reads as empty.
    """
    import struct

    if len(raw) < 20:
        return []
    try:
        offset = struct.unpack_from("<I", raw, 0)[0]
        wide = struct.unpack_from("<I", raw, 16)[0]
        text = raw[offset:].decode("utf-16-le" if wide else "mbcs", "ignore")
    except Exception:  # noqa: BLE001
        return []
    return [part for part in text.split("\x00") if part]


def _looks_like_image(data: bytes) -> bool:
    if any(data.startswith(signature) for signature, _ in MAGIC):
        return True
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def _descriptor_names(data_object) -> list[str]:
    """File names from FILEGROUPDESCRIPTORW: a count, then 592 bytes per file."""
    import struct

    try:
        medium = data_object.GetData(
            (CF_FILEDESCRIPTORW, None, pythoncom.DVASPECT_CONTENT, -1,
             pythoncom.TYMED_HGLOBAL)
        )
    except Exception:  # noqa: BLE001 - no descriptor is not fatal
        return []

    raw = medium.data if isinstance(medium.data, bytes) else bytes(medium.data or b"")
    if len(raw) < 4:
        return []
    count = struct.unpack_from("<I", raw, 0)[0]
    names: list[str] = []
    for index in range(count):
        start = 4 + index * 592
        chunk = raw[start + 72 : start + 72 + 520]
        if len(chunk) < 2:
            break
        name = chunk.decode("utf-16-le", "ignore").split("\x00", 1)[0].strip()
        names.append(name or f"dropped image {index + 1}.png")
    return names


def _read_stream(stream, limit: int = 64 * 1024 * 1024) -> bytes:
    """Drain an IStream. Chrome hands the picture over this way."""
    chunks: list[bytes] = []
    total = 0
    while total < limit:
        try:
            block = stream.Read(1 << 20)
        except Exception:  # noqa: BLE001 - end of stream, or a refusal
            break
        if not block:
            break
        chunks.append(bytes(block))
        total += len(block)
    return b"".join(chunks)


def _one_file(data_object, index: int) -> Optional[bytes]:
    """The bytes of file ``index``, however this data object chooses to hand them over."""
    attempts = (
        pythoncom.TYMED_ISTREAM,
        pythoncom.TYMED_HGLOBAL,
        pythoncom.TYMED_FILE,
    )
    for tymed in attempts:
        try:
            medium = data_object.GetData(
                (CF_FILECONTENTS, None, pythoncom.DVASPECT_CONTENT, index, tymed)
            )
        except Exception:  # noqa: BLE001 - try the next transfer type
            continue

        payload = medium.data
        if payload is None:
            continue
        if isinstance(payload, bytes):
            if payload:
                return payload
            continue
        if isinstance(payload, str):
            # TYMED_FILE hands back a path to a temporary file.
            try:
                with open(payload, "rb") as handle:
                    return handle.read()
            except Exception:  # noqa: BLE001
                continue
        if hasattr(payload, "Read"):
            data = _read_stream(payload)
            if data:
                return data
    return None


def extract_paths(data_object) -> list[str]:
    """Real file paths from a plain Explorer drag (CF_HDROP)."""
    if not Available:
        return []
    try:
        medium = data_object.GetData(
            (win32con.CF_HDROP, None, pythoncom.DVASPECT_CONTENT, -1,
             pythoncom.TYMED_HGLOBAL)
        )
    except Exception:  # noqa: BLE001
        return []
    data = medium.data
    if isinstance(data, (list, tuple)):
        return [str(item) for item in data]
    if isinstance(data, str):
        return [data]
    if isinstance(data, (bytes, bytearray)):
        return _paths_from_dropfiles(bytes(data))
    return []


def extract_files(data_object) -> list[tuple[bytes, str]]:
    """Every file carried by a drag, as ``(bytes, name)``."""
    if not Available:
        return []
    names = _descriptor_names(data_object)
    if not names:
        return []

    found: list[tuple[bytes, str]] = []
    for index, name in enumerate(names):
        data = _one_file(data_object, index)
        if data and len(data) > 64:
            found.append((data, name))
    return found


def available_formats(data_object) -> set[int]:
    """Clipboard format ids this data object is offering."""
    formats: set[int] = set()
    try:
        enumerator = data_object.EnumFormatEtc(pythoncom.DATADIR_GET)
    except Exception:  # noqa: BLE001
        return formats
    while True:
        try:
            batch = enumerator.Next(16)
        except Exception:  # noqa: BLE001
            break
        if not batch:
            break
        for entry in batch:
            try:
                formats.add(int(entry[0]))
            except Exception:  # noqa: BLE001
                continue
    return formats


def carries_internal(data_object) -> bool:
    """True when the drag started inside this application."""
    if not Available:
        return False
    for name in INTERNAL_FORMATS:
        try:
            fmt = win32clipboard.RegisterClipboardFormat(name)
        except Exception:  # noqa: BLE001
            continue
        try:
            # pywin32 signals success by NOT raising.
            data_object.QueryGetData(
                (fmt, None, pythoncom.DVASPECT_CONTENT, -1,
                 pythoncom.TYMED_HGLOBAL)
            )
            return True
        except Exception:  # noqa: BLE001 - this format simply is not offered
            continue
    return False


def carries_paths(data_object) -> bool:
    """True for an ordinary file drag, which Qt reads perfectly well itself."""
    if not Available:
        return False
    try:
        # A direct probe, not available_formats: enumerating can fail outright,
        # and a failure there would read as "no paths" and let us claim a drag
        # Qt was handling perfectly well.
        data_object.QueryGetData(
            (win32con.CF_HDROP, None, pythoncom.DVASPECT_CONTENT, -1,
             pythoncom.TYMED_HGLOBAL)
        )
        return True
    except Exception:  # noqa: BLE001 - this drag carries no file paths
        pass
    try:
        return win32con.CF_HDROP in available_formats(data_object)
    except Exception:  # noqa: BLE001
        return False


def carries_bitmap(data_object) -> bool:
    """True for a plain image drag, which Qt reads natively and routes itself."""
    if not Available:
        return False
    for fmt in (win32con.CF_DIB, win32con.CF_DIBV5):
        try:
            data_object.QueryGetData(
                (fmt, None, pythoncom.DVASPECT_CONTENT, -1,
                 pythoncom.TYMED_HGLOBAL)
            )
            return True
        except Exception:  # noqa: BLE001 - not offered in this shape
            continue
    return False


def offers_stream_contents(data_object) -> bool:
    """Strictly whether this drag carries a browser's file stream.

    has_file_contents is deliberately generous - it accepts a drag it cannot read
    rather than refuse a good one, which is right for a panel that does nothing
    else. Window-wide that generosity would claim drags belonging to Qt, so the
    claim test has to be the strict one: a positive answer, or nothing.
    """
    if not Available:
        return False
    # Browsers differ over which shape they will answer for, so ask several
    # ways before falling back to enumeration - a positive answer here is what
    # lets a claim beat a co-advertised CF_HDROP.
    for fmt, lindex, tymed in (
        (CF_FILEDESCRIPTORW, -1, pythoncom.TYMED_HGLOBAL),
        (CF_FILECONTENTS, 0, pythoncom.TYMED_ISTREAM),
        (CF_FILECONTENTS, 0, pythoncom.TYMED_HGLOBAL),
        (CF_FILECONTENTS, -1, pythoncom.TYMED_ISTREAM),
    ):
        try:
            data_object.QueryGetData(
                (fmt, None, pythoncom.DVASPECT_CONTENT, lindex, tymed)
            )
            return True
        except Exception:  # noqa: BLE001 - try the next shape
            continue
    try:
        # NOTE: available_formats returns an empty set both for "no formats"
        # and for "enumeration failed", so a False here means "could not tell",
        # not "definitely not". The caller must treat it that way.
        return bool(available_formats(data_object)
                    & {CF_FILEDESCRIPTORW, CF_FILECONTENTS})
    except Exception:  # noqa: BLE001
        return False


def qt_drop_target(hwnd: int):
    """Qt's own IDropTarget for this window, so ours can sit in front of it.

    Qt keeps it on a window property. Taking it back out is the only way to
    register in front of Qt without killing its drag and drop outright: QDrag
    runs through this same OLE loop, so a target that simply replaces Qt's
    stops rows reordering and sentiment cards moving between columns.
    """
    if not Available:
        return None
    try:
        # Through ctypes rather than pywin32, which exposes neither GetProp nor
        # GetPropW - and the restype matters: the value is a pointer, so reading
        # it as a C int truncates it on 64-bit and hands back a bad address.
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
        user32.GetPropW.restype = ctypes.c_void_p
        address = user32.GetPropW(wintypes.HWND(hwnd), "OleDropTargetInterface")
        if not address:
            return None
        return pythoncom.ObjectFromAddress(address, pythoncom.IID_IDropTarget)
    except Exception:  # noqa: BLE001 - without it we simply do not chain
        return None


def has_file_contents(data_object) -> bool:
    """Whether this drag is carrying file contents.

    pywin32 signals success from ``QueryGetData`` by *not raising* - it returns
    None, not S_OK. Comparing the result to 0 marks every drag as unusable, which
    is what produced the "no entry" cursor over a drop panel that was working
    perfectly well underneath.
    """
    if not Available:
        return False
    try:
        data_object.QueryGetData(
            (CF_FILEDESCRIPTORW, None, pythoncom.DVASPECT_CONTENT, -1,
             pythoncom.TYMED_HGLOBAL)
        )
        return True
    except Exception:  # noqa: BLE001 - fall through to enumerating instead
        pass

    formats = available_formats(data_object)
    if formats:
        return bool(
            formats & {CF_FILEDESCRIPTORW, CF_FILECONTENTS, win32con.CF_HDROP,
                       win32con.CF_DIB, win32con.CF_DIBV5}
        )
    # Nothing could be determined. Accept the drag rather than refuse a good one;
    # if it turns out to carry nothing, the drop says so.
    return True


class _DropTarget:
    """A real IDropTarget, so the drag reaches us with its data object intact."""

    _public_methods_ = ["DragEnter", "DragOver", "DragLeave", "Drop"]
    _com_interfaces_ = [pythoncom.IID_IDropTarget] if Available else []

    def __init__(self, on_files: Callable[[list[tuple[bytes, str]]], None],
                 on_enter: Callable[[bool], None] | None = None,
                 on_empty: Callable[[], None] | None = None):
        self.on_files = on_files
        self.on_enter = on_enter
        self.on_empty = on_empty
        self._interested = False
        # Screen coordinates of the drop, so the caller can work out which
        # column or list it landed on.
        self.point = (0, 0)

    def DragEnter(self, data_object, key_state, point, effect):
        self._interested = has_file_contents(data_object)
        if self.on_enter:
            try:
                self.on_enter(self._interested)
            except Exception:  # noqa: BLE001
                pass
        return DROPEFFECT_COPY if self._interested else DROPEFFECT_NONE

    def DragOver(self, key_state, point, effect):
        return DROPEFFECT_COPY if self._interested else DROPEFFECT_NONE

    def DragLeave(self):
        self._interested = False
        if self.on_enter:
            try:
                self.on_enter(False)
            except Exception:  # noqa: BLE001
                pass

    def Drop(self, data_object, key_state, point, effect):
        return (DROPEFFECT_COPY if self._deliver(data_object, point)
                else DROPEFFECT_NONE)

    def _deliver(self, data_object, point) -> bool:
        """Read the drag and hand the pictures over. False if there were none."""
        self.point = _screen_point(point)
        if self.on_enter:
            try:
                self.on_enter(False)
            except Exception:  # noqa: BLE001
                pass
        try:
            files = extract_files(data_object)
        except Exception:  # noqa: BLE001 - a bad drag must not take the app down
            files = []

        # A plain Explorer drag onto the same panel carries paths, not contents.
        if not files:
            for path in extract_paths(data_object):
                try:
                    with open(path, "rb") as handle:
                        files.append((handle.read(), path.rsplit("\\", 1)[-1]))
                except Exception:  # noqa: BLE001
                    continue

        images = [(data, name) for data, name in files if _looks_like_image(data)]
        if images:
            try:
                self.on_files(images, self.point)
            except Exception:  # noqa: BLE001
                pass
            return True

        # Accepted the drag but found nothing usable in it: say so rather than
        # leaving the drop looking as though it silently worked.
        if self.on_empty:
            try:
                self.on_empty()
            except Exception:  # noqa: BLE001
                pass
        return False


class Registration:
    """Keeps the drop target alive for as long as the widget is."""

    def __init__(self, hwnd: int, target) -> None:
        self.hwnd = hwnd
        self.target = target

    def revoke(self) -> None:
        try:
            pythoncom.RevokeDragDrop(self.hwnd)
        except Exception:  # noqa: BLE001
            pass


class _WindowDropTarget(_DropTarget):
    """Sits in front of Qt's target for the whole window and forwards.

    It claims only the drag Qt cannot read - a browser handing the picture over
    as a stream. An ordinary file drag and every drag that started inside the
    application go straight through to Qt, which is what keeps a drop on a
    sentiment column meaning "file it under that heading" rather than merely
    "add a clipping".
    """

    def __init__(self, qt_target, on_files, on_enter=None, on_empty=None):
        super().__init__(on_files, on_enter, on_empty)
        self.qt_target = qt_target
        self.mine = False

    def _claim(self, data_object) -> bool:
        """Take only what Qt cannot read for itself.

        The order matters. A positive answer about a file stream has to beat a
        co-advertised CF_HDROP, because a browser offers both. And the last line
        claims on doubt rather than refusing: "cannot tell" used to mean "hand it
        to Qt", which silently lost the drag, and a wrong guess here costs
        nothing now that an unreadable claim is handed back.
        """
        if carries_internal(data_object):
            return False                            # our own drag: Qt's meaning
        if offers_stream_contents(data_object):
            return True                             # positively a file stream
        if carries_paths(data_object):
            return False                            # Explorer: Qt reads these
        if carries_bitmap(data_object):
            return False                            # a bitmap: Qt reads these
        return True                                 # cannot tell: try it

    def _forward(self, name: str, *args):
        if self.qt_target is None:
            return DROPEFFECT_NONE
        try:
            return getattr(self.qt_target, name)(*args)
        except Exception:  # noqa: BLE001 - never let Qt's target break the drag
            return DROPEFFECT_NONE

    def DragEnter(self, data_object, key_state, point, effect):
        self.mine = self._claim(data_object)
        if self.mine:
            return super().DragEnter(data_object, key_state, point, effect)
        return self._forward("DragEnter", data_object, key_state, point, effect)

    def DragOver(self, key_state, point, effect):
        if self.mine:
            return super().DragOver(key_state, point, effect)
        return self._forward("DragOver", key_state, point, effect)

    def DragLeave(self):
        if self.mine:
            self.mine = False
            return super().DragLeave()
        return self._forward("DragLeave")

    def Drop(self, data_object, key_state, point, effect):
        if not self.mine:
            return self._forward("Drop", data_object, key_state, point, effect)
        self.mine = False
        if self._deliver(data_object, point):
            return DROPEFFECT_COPY
        # Claimed it and found nothing readable in it. Give the drop back rather
        # than swallow it - Qt can still recover a picture from dropped HTML or
        # from an inline data: URI. It never saw this drag begin, so it needs
        # its own DragEnter first.
        self._forward("DragEnter", data_object, key_state, point, effect)
        return self._forward("Drop", data_object, key_state, point, effect)


def install_window(widget, on_files, on_enter=None, on_empty=None
                   ) -> Optional[Registration]:
    """Take browser drags for the whole window, leaving Qt's own drags alone."""
    if not Available:
        return None
    try:
        hwnd = int(widget.winId())
        if not hwnd:
            return None
        try:
            pythoncom.OleInitialize()
        except Exception:  # noqa: BLE001 - Qt has usually done this already
            pass

        inner = qt_drop_target(hwnd)
        if inner is None:
            # Without Qt's target to fall back on, taking the window would kill
            # reordering and category moves. Better to leave it alone.
            return None
        try:
            # Take a reference of our own BEFORE revoking. RevokeDragDrop
            # releases the reference OLE holds, and Qt does not keep one - so
            # without this the pointer we forward to is freed memory. It
            # survives DragEnter and corrupts the heap on Drop.
            inner = inner.QueryInterface(pythoncom.IID_IDropTarget)
        except Exception:  # noqa: BLE001 - cannot own it, so do not take over
            return None

        pythoncom.RevokeDragDrop(hwnd)
        # Through the server policy, not WrapObject on a bare instance: the
        # gateway dispatches by looking up _InvokeEx_ on whatever it is handed,
        # and a plain object has none - so every DragEnter, DragOver and Drop
        # fails inside pywin32 and Windows refuses the drag. Silently, because
        # the registration itself succeeds.
        target = _com_util.wrap(
            _WindowDropTarget(inner, on_files, on_enter, on_empty),
            pythoncom.IID_IDropTarget,
        )
        pythoncom.RegisterDragDrop(hwnd, target)
        return Registration(hwnd, target)
    except Exception:  # noqa: BLE001 - fall back to the panel-only registration
        return None


def install(widget, on_files, on_enter=None, on_empty=None) -> Optional[Registration]:
    """Take over drag and drop for one widget. Returns None if it cannot be done.

    The widget is given its own native window so only its own area is affected;
    Qt keeps handling everything else, including dragging rows to reorder them.
    """
    if not Available:
        return None
    try:
        from PySide6.QtCore import Qt

        widget.setAttribute(Qt.WA_NativeWindow, True)
        widget.setAcceptDrops(False)          # Qt must not fight us for this area
        hwnd = int(widget.winId())
        if not hwnd:
            return None

        # Qt has already called OleInitialize on the GUI thread, which is what
        # RegisterDragDrop needs. Asking again can legitimately fail, so it must
        # not be allowed to abort the registration.
        try:
            pythoncom.OleInitialize()
        except Exception:  # noqa: BLE001
            pass
        try:
            pythoncom.RevokeDragDrop(hwnd)    # in case Qt already claimed it
        except Exception:  # noqa: BLE001
            pass

        target = _com_util.wrap(
            _DropTarget(on_files, on_enter, on_empty),
            pythoncom.IID_IDropTarget,
        )
        pythoncom.RegisterDragDrop(hwnd, target)
        return Registration(hwnd, target)
    except Exception:  # noqa: BLE001 - fall back to Qt's handling
        return None
