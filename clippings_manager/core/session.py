"""Keep the morning's work on disk, so a sudden close costs nothing.

The department compiles a newspad over an hour or more: documents imported, images
dragged in from WhatsApp, headlines typed, clippings reordered and filed. Losing
that to a crash, a power cut or a stray Alt+F4 means doing the whole morning again,
so the session is written as it goes and read back on the next launch.

The shape of the store follows from what actually changes. Image bytes are the bulk
- tens of megabytes for a real morning - and never change once imported. The
metadata changes constantly: a headline is retyped, a card is dragged to another
column, the order shifts. So pictures are written once into a content-addressed
folder and the manifest, which is small, is rewritten on a debounce.

Crash safety is the whole point, so the manifest is written to a temporary file and
moved into place with ``os.replace``, which is atomic. A kill mid-write therefore
leaves either the previous good manifest or the new one, never half of either. A
manifest that references a picture which is not there loses that one clipping and
says so, rather than refusing to open the rest of the morning's work.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
from dataclasses import fields as dataclass_fields
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from .models import Clip, CropRect, Section

VERSION = 1
MANIFEST = "session.json"
BLOBS = "blobs"
THUMBS = "thumbs"


def session_dir() -> Path:
    """Beside the other settings, so an update never wipes a morning's work."""
    import sys

    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    folder = base / "ClippingsManager" / "session"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / BLOBS).mkdir(exist_ok=True)
    (folder / THUMBS).mkdir(exist_ok=True)
    return folder


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------ encoding


def encode_clip(clip: Clip) -> dict:
    """A Clip as plain JSON values, minus the picture itself.

    Three of its thirty-one fields need help. ``image_bytes`` is not JSON at all and
    lives in the blob folder. ``crop`` is a nested dataclass. ``section`` is the
    quiet one: Section subclasses str, so it *serialises* without complaint and
    comes back as a bare string, which then raises on the first paint that reads
    ``clip.section.value``. It has to be rebuilt as the enum.
    """
    data: dict[str, Any] = {}
    for field in dataclass_fields(clip):
        if field.name == "image_bytes":
            continue
        value = getattr(clip, field.name)
        if isinstance(value, Section):
            data[field.name] = value.value
        elif isinstance(value, CropRect):
            data[field.name] = {
                "left": value.left, "top": value.top,
                "right": value.right, "bottom": value.bottom,
                "raw": value.raw,
            }
        else:
            data[field.name] = value
    return data


def decode_clip(data: dict, image_bytes: bytes) -> Clip:
    clip = Clip()
    known = {f.name for f in dataclass_fields(clip)}
    for name, value in data.items():
        if name not in known:
            continue                      # a field from a newer version
        if name == "section":
            try:
                setattr(clip, name, Section(value))
            except ValueError:
                setattr(clip, name, Section.NEUTRAL)
        elif name == "crop" and isinstance(value, dict):
            crop = CropRect()
            for key in ("left", "top", "right", "bottom"):
                setattr(crop, key, float(value.get(key, 0.0)))
            crop.raw = value.get("raw")
            setattr(clip, name, crop)
        else:
            setattr(clip, name, value)
    clip.image_bytes = image_bytes
    return clip


# --------------------------------------------------------------------- store


class SessionStore:
    """Reads and writes the saved session."""

    def __init__(self, folder: Optional[Path] = None):
        self.folder = folder or session_dir()
        self.blobs = self.folder / BLOBS
        self.thumbs = self.folder / THUMBS
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.thumbs.mkdir(parents=True, exist_ok=True)

    # -- pictures ---------------------------------------------------------
    def put_blob(self, data: bytes) -> str:
        """Write a picture once. Returns the name to reference it by."""
        name = _digest(data)
        target = self.blobs / name
        if not target.exists():
            self._atomic_bytes(target, data)
        return name

    def get_blob(self, name: str) -> Optional[bytes]:
        target = self.blobs / name
        try:
            return target.read_bytes()
        except Exception:  # noqa: BLE001 - a missing picture loses one clipping
            return None

    def put_thumb(self, name: str, data: bytes) -> None:
        target = self.thumbs / f"{name}.png"
        if not target.exists():
            self._atomic_bytes(target, data)

    def get_thumb(self, name: str) -> Optional[bytes]:
        try:
            return (self.thumbs / f"{name}.png").read_bytes()
        except Exception:  # noqa: BLE001 - it will simply be rebuilt
            return None

    @staticmethod
    def _atomic_bytes(target: Path, data: bytes) -> None:
        temp = target.with_suffix(target.suffix + ".part")
        with open(temp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)

    # -- the manifest ------------------------------------------------------
    def save(self, payload: dict) -> None:
        """Write the manifest so a kill can never leave half of one."""
        from .. import version as build

        payload = dict(payload)
        payload["version"] = VERSION
        # Which build read these clippings. The manifest holds what the importer
        # made of a document - captions, sections, whether a masthead was joined
        # to the article under it - so clippings read by an older build keep that
        # older build's idea of the document even after an update. Recording the
        # stamp is what lets the application notice and say so.
        payload["build"] = build.digest()
        payload["saved_at"] = datetime.now().isoformat(timespec="seconds")
        text = json.dumps(payload, ensure_ascii=False, indent=1)
        self._atomic_bytes(self.folder / MANIFEST, text.encode("utf-8"))

    def load(self) -> Optional[dict]:
        path = self.folder / MANIFEST
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except Exception:  # noqa: BLE001 - a corrupt manifest is not a crash
            return None
        if not isinstance(payload, dict) or payload.get("version") != VERSION:
            return None
        return payload

    def saved_by_another_build(self) -> bool:
        """Whether the stored session was read by a different build than this.

        Not a reason to refuse it - a morning's work is never thrown away over
        this - but a reason to say so, because the clippings in it were read by
        rules that have since changed and re-importing is what picks the new ones
        up. A session saved before the stamp existed counts as another build,
        which is the honest answer: it was.
        """
        from .. import version as build

        path = self.folder / MANIFEST
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(payload, dict):
            return False
        return str(payload.get("build", "")) != build.digest()

    def clear(self) -> None:
        """Forget the saved session entirely."""
        try:
            (self.folder / MANIFEST).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        for folder in (self.blobs, self.thumbs):
            try:
                shutil.rmtree(folder, ignore_errors=True)
                folder.mkdir(parents=True, exist_ok=True)
            except Exception:  # noqa: BLE001
                pass

    # -- housekeeping ------------------------------------------------------
    def collect(self, keep: Iterable[str]) -> int:
        """Delete pictures nothing refers to any more.

        Called after a successful manifest write, never before: a blob removed
        while the old manifest is still the one on disk would break the very
        session we are trying to protect. Content addressing means two identical
        clippings share one file, so the set of names in use is the whole test.
        """
        wanted = set(keep)
        removed = 0
        for path in list(self.blobs.glob("*")):
            if path.name.endswith(".part"):
                path.unlink(missing_ok=True)
                continue
            if path.name not in wanted:
                path.unlink(missing_ok=True)
                removed += 1
        for path in list(self.thumbs.glob("*.png")):
            if path.stem not in wanted:
                path.unlink(missing_ok=True)
        return removed

    def size_on_disk(self) -> int:
        total = 0
        for folder in (self.blobs, self.thumbs):
            for path in folder.glob("*"):
                try:
                    total += path.stat().st_size
                except OSError:
                    pass
        return total
