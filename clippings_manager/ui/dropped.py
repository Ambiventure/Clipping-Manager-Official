"""Getting images out of whatever was dropped or pasted.

Dragging a photo out of Explorer hands over a file path. Dragging one out of
WhatsApp Web hands over a bundle of formats, and which of them actually holds the
bytes depends on the browser and on how the page produced the image. Explorer can
save such a drag, so the bytes are there; the job is to find which format has them.

So every route is tried in order, nothing is rejected on the strength of a file
extension, and when a drop genuinely carries no image the caller is given the list
of formats that did arrive rather than a flat refusal.
"""

from __future__ import annotations

import base64
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QMimeData
from PySide6.QtGui import QImage, QPixmap

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
DOCUMENT_SUFFIXES = {".docx", ".pdf"}

WINDOWS_MIME = 'application/x-qt-windows-mime;value="%s"'
FILE_CONTENTS = WINDOWS_MIME % "FileContents"
FILE_DESCRIPTOR = WINDOWS_MIME % "FileGroupDescriptorW"

# Formats worth trying for raw image bytes, best first.
IMAGE_FORMATS = (
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/bmp",
    "image/tiff",
    "image/gif",
    "application/x-qt-image",
    FILE_CONTENTS,
    WINDOWS_MIME % "PNG",
    WINDOWS_MIME % "JFIF",
    WINDOWS_MIME % "image/png",
    WINDOWS_MIME % "image/jpeg",
)

_DATA_URI = re.compile(
    rb'data:image/[a-z+.-]+;base64,([A-Za-z0-9+/=\s]{40,})', re.I
)

# Magic numbers, so a file with a missing or odd extension is still recognised.
MAGIC = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"BM", ".bmp"),
    (b"II*\x00", ".tif"),
    (b"MM\x00*", ".tif"),
)


def sniff(data: bytes) -> str:
    """The image type these bytes actually are, ignoring any file name."""
    for signature, suffix in MAGIC:
        if data.startswith(signature):
            return suffix
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ""


@dataclass
class Dropped:
    """What a drop or paste actually yielded."""

    files: list[Path] = field(default_factory=list)
    images: list[tuple[bytes, str]] = field(default_factory=list)
    remote_urls: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def empty(self) -> bool:
        return not self.files and not self.images


def _png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QBuffer.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def _as_image(value) -> QImage:
    """Coerce whatever ``imageData()`` handed back into a QImage.

    It can come back as a QImage, a QPixmap, or a QVariant wrapping either, and
    passing the wrong one to the QImage constructor quietly produces a null image —
    which looks exactly like "there was no picture".
    """
    if isinstance(value, QImage):
        return value
    if isinstance(value, QPixmap):
        return value.toImage()
    try:
        image = QImage(value)
        if not image.isNull():
            return image
    except Exception:  # noqa: BLE001
        pass
    try:
        return QPixmap(value).toImage()
    except Exception:  # noqa: BLE001
        return QImage()


def _descriptor_name(mime: QMimeData) -> str:
    """The file name Windows attached to a file-transfer drag, if there is one.

    FILEGROUPDESCRIPTORW is a 4-byte count then one 592-byte record per file; the
    last 520 bytes of a record are the UTF-16 name.
    """
    if not mime.hasFormat(FILE_DESCRIPTOR):
        return ""
    try:
        raw = bytes(mime.data(FILE_DESCRIPTOR))
        if len(raw) >= 596 and struct.unpack_from("<I", raw, 0)[0] >= 1:
            name = raw[4 + 72 : 4 + 72 + 520].decode("utf-16-le", "ignore")
            return name.split("\x00", 1)[0].strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def _from_formats(mime: QMimeData) -> list[tuple[bytes, str]]:
    """Any format that yields decodable image bytes."""
    name = _descriptor_name(mime) or "dropped image.png"
    for fmt in IMAGE_FORMATS:
        if not mime.hasFormat(fmt):
            continue
        try:
            payload = bytes(mime.data(fmt))
        except Exception:  # noqa: BLE001
            continue
        if len(payload) < 64:
            continue
        image = QImage.fromData(payload)
        if not image.isNull():
            return [(payload if sniff(payload) else _png_bytes(image), name)]
    return []


def _from_html(mime: QMimeData) -> list[tuple[bytes, str]]:
    """An <img> in dropped HTML whose source is an inline data: URI."""
    if not mime.hasHtml():
        return []
    found = []
    for match in _DATA_URI.finditer(mime.html().encode("utf-8", "ignore")):
        try:
            raw = base64.b64decode(re.sub(rb"\s+", b"", match.group(1)))
        except Exception:  # noqa: BLE001
            continue
        if QImage.fromData(raw).isNull():
            continue
        found.append((raw, "pasted image.png"))
    return found


def read(mime: QMimeData) -> Dropped:
    """Pull whatever usable images or files a drop or paste is carrying."""
    result = Dropped(formats=list(mime.formats()))

    # 1. Local files: Explorer, Finder, a folder of photos, a browser that wrote
    #    the image to a temp file first. Judged by content, not by extension.
    if mime.hasUrls():
        for url in mime.urls():
            if not url.isLocalFile():
                text = url.toString()
                if text.startswith(("http://", "https://", "blob:", "data:")):
                    result.remote_urls.append(text)
                continue
            path = Path(url.toLocalFile())
            if path.is_dir():
                result.files.append(path)
                continue
            if not path.exists():
                continue
            suffix = path.suffix.lower()
            if suffix in IMAGE_SUFFIXES or suffix in DOCUMENT_SUFFIXES:
                result.files.append(path)
                continue
            # No useful extension: look at the bytes before giving up on it.
            try:
                head = path.open("rb").read(16)
            except Exception:  # noqa: BLE001
                continue
            if sniff(head):
                result.files.append(path)

    # 2. Bytes carried in the drag itself.
    if not result.files:
        result.images.extend(_from_formats(mime))

    # 3. A bitmap on the clipboard or in the drag.
    if not result.files and not result.images and mime.hasImage():
        image = _as_image(mime.imageData())
        if not image.isNull():
            result.images.append((_png_bytes(image), "pasted image.png"))

    # 4. An inline data: URI inside dropped HTML.
    if not result.files and not result.images:
        result.images.extend(_from_html(mime))

    # 5. A data: URI sitting in the plain text of the drop.
    if not result.files and not result.images and mime.hasText():
        match = _DATA_URI.search(mime.text().encode("utf-8", "ignore"))
        if match:
            try:
                raw = base64.b64decode(re.sub(rb"\s+", b"", match.group(1)))
                if not QImage.fromData(raw).isNull():
                    result.images.append((raw, "pasted image.png"))
            except Exception:  # noqa: BLE001
                pass

    if result.empty:
        result.note = _explain(result)
    return result


def _explain(result: Dropped) -> str:
    """Say what actually arrived, and what to do about it."""
    if FILE_CONTENTS in result.formats or FILE_DESCRIPTOR in result.formats:
        # The picture IS in this drag, but as a COM stream that Qt will not read.
        # The drop panel has its own handler that reads it; the rest of the window
        # is still Qt's, so a drop landing there comes through empty.
        return (
            "Drop it on the dashed panel at the top of the window.\n\n"
            "That panel reads a browser drag the way Explorer does. Dropped "
            "anywhere else in the window, the picture does not come through.\n\n"
            "Ctrl+V works anywhere, if that is easier."
        )
    if result.remote_urls:
        return (
            "That drag carried only a link to the picture, not the picture itself."
            "\n\nRight-click the image in WhatsApp Web, choose Copy image, then "
            "press Ctrl+V here."
        )
    listing = "\n".join(f"    {f}" for f in result.formats[:14]) or "    (nothing)"
    return (
        "Nothing usable came with that drop.\n\n"
        "Right-click the image in WhatsApp Web, choose Copy image, then press "
        "Ctrl+V here.\n\n"
        "If dragging it into a folder works but this does not, send me this list "
        "and I will add the missing format:\n"
        f"{listing}"
    )
