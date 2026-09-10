"""Drop probe: shows exactly what a drag is carrying.

Dragging an image out of WhatsApp Web hands Windows a bundle of formats, and which
ones actually contain the bytes differs by browser and by how the page made the
image. This window reports every format it receives and how many bytes each holds,
so the importer can be pointed at the one that works instead of guessing.

Run it, drag one image from WhatsApp Web onto it, and send me what it prints:

    .venv\\Scripts\\python.exe -X utf8 tools\\drop_probe.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

REPORT = Path(__file__).resolve().parent.parent / "drop_report.txt"


def describe(mime) -> str:
    lines: list[str] = []
    add = lines.append

    add("=" * 72)
    add("WHAT THE DROP CARRIED")
    add("=" * 72)
    add(f"hasImage : {mime.hasImage()}")
    add(f"hasUrls  : {mime.hasUrls()}")
    add(f"hasHtml  : {mime.hasHtml()}")
    add(f"hasText  : {mime.hasText()}")
    add("")

    if mime.hasUrls():
        add("URLs:")
        for url in mime.urls():
            add(f"   local={url.isLocalFile()}  {url.toString()[:160]}")
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                add(f"      exists={path.exists()}  "
                    f"size={path.stat().st_size if path.exists() else '-'}")
        add("")

    if mime.hasImage():
        raw = mime.imageData()
        add(f"imageData() type   : {type(raw).__name__}")
        image = raw if isinstance(raw, QImage) else QImage(raw)
        add(f"as QImage          : null={image.isNull()} "
            f"size={image.width()}x{image.height()}")
        add("")

    add("EVERY FORMAT, AND HOW MANY BYTES IT ACTUALLY YIELDS:")
    for fmt in mime.formats():
        try:
            size = mime.data(fmt).size()
        except Exception as exc:  # noqa: BLE001
            size = f"error: {type(exc).__name__}"
        marker = "  <-- HAS DATA" if isinstance(size, int) and size > 0 else ""
        add(f"   {str(size):>10}  {fmt}{marker}")

    if mime.hasText():
        add("")
        add(f"text: {mime.text()[:300]!r}")
    add("")
    return "\n".join(lines)


class Probe(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Drop probe — drag one WhatsApp image here")
        self.resize(880, 620)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        heading = QLabel(
            "Drag ONE image from WhatsApp Web onto this window.\n"
            "Then copy everything below, or send me drop_report.txt."
        )
        heading.setStyleSheet("font-size: 14px; font-weight: 600; padding: 8px;")
        layout.addWidget(heading)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px;"
        )
        self.output.setPlainText("Waiting for a drop…")
        layout.addWidget(self.output, 1)

        paste = QPushButton("Or press this after copying an image (tests Ctrl+V)")
        paste.clicked.connect(self._paste)
        layout.addWidget(paste)

    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        event.acceptProposedAction()
        self._report(describe(event.mimeData()))

    def _paste(self):
        self._report(describe(QApplication.clipboard().mimeData()))

    def _report(self, text: str) -> None:
        self.output.setPlainText(text)
        try:
            REPORT.write_text(text, encoding="utf-8")
            self.output.appendPlainText(f"\n(also written to {REPORT})")
        except Exception:  # noqa: BLE001
            pass
        print(text)


def main() -> int:
    app = QApplication(sys.argv)
    probe = Probe()
    probe.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
