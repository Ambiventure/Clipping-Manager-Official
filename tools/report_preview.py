"""Look at an exported report in a browser, page by page.

The application itself is a native Windows program and cannot be shown in a
browser. What can be shown is the thing that actually gets checked: the newspad
or the dossier that comes out of it. This serves every page of a chosen export as
a picture, in a grid, so a whole report can be read at a glance - which is how a
heading stranded above a blank half-page gets spotted without opening Word.

Word files are converted through Word itself, so what you see is what Word will
print, not an approximation. Without Word installed, PDFs still work.

Runs on the loopback address only, serves only the files it has listed, and never
looks anything up on the network. Nothing here ships inside the executable: it
lives in tools/ and is for checking output while working.

    python tools/report_preview.py [folder ...] [--port 8765]
"""

from __future__ import annotations

import argparse
import html
import io
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pymupdf

SUFFIXES = {".pdf", ".docx"}
RENDER_DPI = 110.0
# A report is 13 to 170 pages. Past this the grid is unreadable anyway and the
# browser starts to struggle, so the rest is listed rather than drawn.
MAX_PAGES = 200
# Anything older than this is last week's work, not what is being checked now.
MAX_AGE_DAYS = 30


def default_folders() -> list[Path]:
    """Where exports usually land."""
    home = Path.home()
    found = [home / "Desktop", home / "Documents", home / "Downloads", Path.cwd()]
    return [p for p in found if p.is_dir()]


class Library:
    """The exports on offer, refreshed on demand. Index is the only handle."""

    def __init__(self, folders: list[Path]):
        self.folders = folders
        self.files: list[Path] = []
        self._lock = threading.Lock()
        self._pdfs: dict[tuple[str, float], Path] = {}
        self._pages: dict[tuple[str, float, int], bytes] = {}

    def refresh(self) -> list[Path]:
        cutoff = time.time() - MAX_AGE_DAYS * 86400
        found: list[tuple[float, Path]] = []
        for folder in self.folders:
            for suffix in SUFFIXES:
                try:
                    for path in folder.glob(f"*{suffix}"):
                        if path.name.startswith("~$"):
                            continue          # Word's own lock file
                        try:
                            stat = path.stat()
                        except OSError:
                            continue
                        if stat.st_mtime >= cutoff:
                            found.append((stat.st_mtime, path))
                except OSError:
                    continue
        found.sort(key=lambda item: item[0], reverse=True)
        with self._lock:
            self.files = [path for _when, path in found]
        return self.files

    def at(self, index: int) -> Path | None:
        with self._lock:
            if 0 <= index < len(self.files):
                return self.files[index]
        return None

    # ---------------------------------------------------------------- pdfs
    def as_pdf(self, path: Path) -> Path:
        """The file itself if it is a PDF, or what Word makes of it."""
        if path.suffix.lower() == ".pdf":
            return path
        key = (str(path), path.stat().st_mtime)
        cached = self._pdfs.get(key)
        if cached and cached.exists():
            return cached
        made = _word_to_pdf(path)
        self._pdfs[key] = made
        return made

    def page_png(self, path: Path, number: int) -> bytes:
        key = (str(path), path.stat().st_mtime, number)
        cached = self._pages.get(key)
        if cached is not None:
            return cached
        with pymupdf.open(self.as_pdf(path)) as doc:
            pixmap = doc[number].get_pixmap(dpi=int(RENDER_DPI))
            data = pixmap.tobytes("png")
        self._pages[key] = data
        return data

    def page_count(self, path: Path) -> int:
        with pymupdf.open(self.as_pdf(path)) as doc:
            return doc.page_count


def _word_to_pdf(path: Path) -> Path:
    """Ask Word to print the document, so the pagination is Word's own."""
    import pythoncom
    from win32com import client

    target = Path(tempfile.gettempdir()) / f"preview-{abs(hash(str(path)))}.pdf"
    pythoncom.CoInitialize()
    word = None
    try:
        word = client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        document = word.Documents.Open(str(path), False, True)
        try:
            document.SaveAs(str(target), FileFormat=17)   # wdFormatPDF
        finally:
            document.Close(False)
        return target
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:  # noqa: BLE001 - Word is gone, nothing to do
                pass
        pythoncom.CoUninitialize()


# ------------------------------------------------------------------- pages

STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 "Segoe UI", system-ui, sans-serif;
       background: #0F172A; color: #E2E8F0; }
header { position: sticky; top: 0; z-index: 5; background: #12233F;
         border-bottom: 1px solid #24344F; padding: 12px 18px;
         display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
h1 { font-size: 15px; margin: 0; font-weight: 650; letter-spacing: .2px; }
.muted { color: #94A3B8; font-size: 12px; }
a { color: #93C5FD; text-decoration: none; }
a:hover { text-decoration: underline; }
main { padding: 18px; }
ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px;
     grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); }
li a { display: block; padding: 12px 14px; border: 1px solid #24344F;
       border-radius: 10px; background: #16273F; }
li a:hover { border-color: #3B82F6; text-decoration: none; }
.name { font-weight: 600; color: #E2E8F0; word-break: break-all; }
.pill { font-size: 10px; text-transform: uppercase; letter-spacing: .6px;
        border-radius: 999px; padding: 2px 8px; margin-right: 6px;
        border: 1px solid currentColor; }
.pdf { color: #FCA5A5; } .docx { color: #93C5FD; }
.grid { display: grid; gap: 16px;
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
figure { margin: 0; background: #16273F; border: 1px solid #24344F;
         border-radius: 10px; padding: 8px; }
figure img { width: 100%; display: block; background: #fff; border-radius: 4px; }
figcaption { font-size: 11px; color: #94A3B8; padding-top: 6px;
             text-align: center; }
.note { border: 1px solid #7C2D12; background: #2A1408; color: #FDBA74;
        padding: 12px 14px; border-radius: 10px; }
button, select { font: inherit; background: #1E3050; color: #E2E8F0;
                 border: 1px solid #33415A; border-radius: 8px;
                 padding: 6px 10px; cursor: pointer; }
"""


def _shell(title: str, body: str, subtitle: str = "") -> bytes:
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>{STYLE}</style></head><body>
<header><h1>{html.escape(title)}</h1>
<span class="muted">{subtitle}</span>
<span style="flex:1"></span>
<a href="/">All exports</a></header>
<main>{body}</main></body></html>""".encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    library: Library = None            # set on the server before serving

    def log_message(self, *args) -> None:      # quiet: this is a preview
        pass

    def _send(self, data: bytes, kind: str = "text/html; charset=utf-8") -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:                  # noqa: N802 - http.server's name
        parts = urlparse(self.path)
        query = parse_qs(parts.query)
        try:
            if parts.path == "/":
                self._send(self._index())
            elif parts.path == "/view":
                self._send(self._view(int(query.get("f", ["-1"])[0])))
            elif parts.path == "/page":
                index = int(query.get("f", ["-1"])[0])
                number = int(query.get("p", ["0"])[0])
                path = self.library.at(index)
                if path is None:
                    self.send_error(404, "no such export")
                    return
                self._send(self.library.page_png(path, number), "image/png")
            else:
                self.send_error(404, "not a page here")
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001 - a preview never takes the app down
            self._send(_shell("Preview", f'<p class="note">{html.escape(str(exc))}</p>'))

    # ------------------------------------------------------------- pages
    def _index(self) -> bytes:
        files = self.library.refresh()
        if not files:
            where = "<br>".join(html.escape(str(f))
                                for f in self.library.folders)
            return _shell(
                "Exported reports",
                f'<p class="note">No .pdf or .docx from the last '
                f'{MAX_AGE_DAYS} days in:<br><br>{where}<br><br>'
                f'Export a report, then reload this page.</p>')

        rows = []
        for index, path in enumerate(files):
            stat = path.stat()
            when = datetime.fromtimestamp(stat.st_mtime).strftime("%d %b %H:%M")
            kind = path.suffix.lower().lstrip(".")
            rows.append(
                f'<li><a href="/view?f={index}">'
                f'<span class="pill {kind}">{kind}</span>'
                f'<span class="name">{html.escape(path.name)}</span><br>'
                f'<span class="muted">{when} &middot; '
                f'{stat.st_size / 1024:.0f} KB &middot; '
                f'{html.escape(str(path.parent))}</span></a></li>')
        return _shell("Exported reports",
                      "<ul>" + "".join(rows) + "</ul>",
                      f"{len(files)} file(s), newest first")

    def _view(self, index: int) -> bytes:
        path = self.library.at(index)
        if path is None:
            return _shell("Preview", '<p class="note">That export is no longer '
                                     'listed. Go back and reload.</p>')
        try:
            total = self.library.page_count(path)
        except Exception as exc:  # noqa: BLE001
            hint = ""
            if path.suffix.lower() == ".docx":
                hint = ("<br><br>Word files are converted by Word itself. "
                        "If Word is not installed on this machine, export the "
                        "PDF instead and preview that.")
            return _shell(path.name,
                          f'<p class="note">Could not be opened: '
                          f'{html.escape(str(exc))}{hint}</p>')

        shown = min(total, MAX_PAGES)
        figures = "".join(
            f'<figure><img loading="lazy" src="/page?f={index}&p={n}" '
            f'alt="page {n + 1}"><figcaption>Page {n + 1}</figcaption></figure>'
            for n in range(shown))
        extra = ("" if shown == total else
                 f'<p class="note">Showing the first {shown} of {total} pages.</p>')
        return _shell(path.name, extra + f'<div class="grid">{figures}</div>',
                      f"{total} page(s) &middot; {path.parent}")


def _free_port(preferred: int) -> int:
    """The port asked for, or one the machine will actually give us."""
    for candidate in (preferred, 0):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", candidate))
                return probe.getsockname()[1]
            except OSError:
                continue
    return preferred


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="report_preview",
        description="Serve exported reports as pages you can look at.")
    parser.add_argument("folders", nargs="*", type=Path,
                        help="where to look (default: Desktop, Documents, "
                             "Downloads and the current folder)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    folders = [f for f in args.folders if f.is_dir()] or default_folders()
    Handler.library = Library(folders)
    port = _free_port(args.port)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Report preview on http://127.0.0.1:{port}", flush=True)
    for folder in folders:
        print(f"  watching {folder}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
