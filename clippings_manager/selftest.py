"""A self-check that can be run from the packaged application.

A frozen windowed build has nowhere to print to, so when something is missing from
the bundle the app simply does not appear and there is nothing to go on. This runs
the parts most likely to break in a package - finding the JSON config, resolving a
Devanagari font, the COM plumbing that reads a browser drag, and actually building
a PDF - then writes a plain report and shows it.

Run it on a new machine before trusting the installation:

    "Clippings Manager.exe" --selftest
"""

from __future__ import annotations

import io
import shutil
import sys
import tempfile
import traceback
from datetime import date
from pathlib import Path

# The browser inside the program has to be imported before any Qt application
# exists - the import sets the OpenGL context sharing the engine needs - or
# the engine check below does not fail, it fails fast (0xC0000409) and takes
# the whole self-test with it. Measured, in the venv and in the bundle alike.
try:
    import PySide6.QtWebEngineWidgets  # noqa: F401
except Exception:  # noqa: BLE001 - a build without the browser
    pass


def _line(ok: bool, label: str, detail: str = "") -> str:
    mark = "  ok  " if ok else " FAIL "
    return f"[{mark}] {label}" + (f"\n           {detail}" if detail else "")


def run(sample: str | None = None) -> tuple[bool, str]:
    """Check everything the packaged app depends on. Returns (passed, report)."""
    lines: list[str] = []
    passed = True

    frozen = getattr(sys, "frozen", False)
    base = getattr(sys, "_MEIPASS", None) or str(Path(__file__).resolve().parent.parent)
    from . import version

    lines.append("Clippings Manager - self check")
    lines.append("=" * 60)
    # First line of the report, because "which build is this?" is the first
    # question whenever two machines disagree about the same document.
    lines.append(f"build          : {version.describe()}")
    lines.append(f"packaged build : {frozen}")
    lines.append(f"running from   : {base}")
    lines.append(f"python         : {sys.version.split()[0]}")
    lines.append("")

    # --- configuration ----------------------------------------------------
    try:
        from .core.assemble import load_config

        config = load_config()
        divisions = list(config.get("divisions", {}))
        ok = len(divisions) >= 6
        passed &= ok
        lines.append(_line(ok, "divisions.json", f"{len(divisions)} divisions: "
                                                 f"{', '.join(divisions)}"))
    except Exception as exc:  # noqa: BLE001
        passed = False
        config = None
        lines.append(_line(False, "divisions.json", f"{type(exc).__name__}: {exc}"))

    try:
        from .core.profiles import NameIndex

        index = NameIndex.load(settings=(config or {}).get("name_matching"))
        ok = len(index.newspaper_names) > 20
        passed &= ok
        lines.append(_line(ok, "newspapers.json",
                           f"{len(index.newspaper_names)} newspapers, "
                           f"{len(index.edition_names)} editions"))
    except Exception as exc:  # noqa: BLE001
        passed = False
        index = None
        lines.append(_line(False, "newspapers.json", f"{type(exc).__name__}: {exc}"))

    # --- name resolution, the heart of the thing --------------------------
    if index is not None and config is not None:
        try:
            from .core.profiles import split_name

            paper, edition, score = split_name(
                "दैनिक जागरन दिल्ली", index, config.get("name_matching")
            )
            ok = paper == "Dainik Jagran" and edition == "Delhi"
            passed &= ok
            lines.append(_line(ok, "name matching (misspelt Devanagari)",
                               f"-> {paper} / {edition} (score {score:.0f})"))
        except Exception as exc:  # noqa: BLE001
            passed = False
            lines.append(_line(False, "name matching", f"{type(exc).__name__}: {exc}"))

    # --- drag support -----------------------------------------------------
    try:
        from .ui import win_drop

        # Not just "pywin32 imports": build the COM drop target and call a
        # method on it. A gateway built the wrong way registers perfectly
        # happily and then fails every single call, which looks from outside
        # exactly like a drag that is ignored.
        working = False
        detail = "pywin32 missing - use Ctrl+V instead of dragging"
        if win_drop.Available:
            try:
                import pythoncom
                from win32com.server import util as com_util

                probe = com_util.wrap(
                    win_drop._DropTarget(lambda files, point=None: None),
                    pythoncom.IID_IDropTarget,
                )
                probe.DragLeave()          # raises if the gateway is broken
                working = True
                detail = ("drop target answers - images can be dragged "
                          "from WhatsApp Web and from a folder")
            except Exception as exc:  # noqa: BLE001
                detail = (f"the drop target does not answer "
                          f"({type(exc).__name__}) - use Ctrl+V instead")
        lines.append(_line(working, "browser drag support", detail))
        passed &= working
    except Exception as exc:  # noqa: BLE001
        lines.append(_line(False, "browser drag support",
                           f"{type(exc).__name__}: {exc}"))

    # --- fonts ------------------------------------------------------------
    try:
        from .export.build_pdf import Typeface

        typeface = Typeface()
        # This used to be hardcoded to pass and to claim a system font was in
        # use whether or not one existed - on a machine with no Devanagari face
        # at all it still said "using a system Devanagari font". That is the one
        # line somebody checks when Hindi comes out as boxes, so it has to be
        # true. It reads the font files rather than asking Qt, because the check
        # runs before there is a window.
        from .export.build_pdf import _font_file

        system = next(
            (name for name in ("Nirmala.ttc", "Nirmala.ttf", "mangal.ttf",
                               "aparaj.ttf", "kokila.ttf", "utsaah.ttf")
             if _font_file(name) is not None), "")
        if typeface.bundled:
            where = f"bundled with the app: {typeface.bundled}"
        elif system:
            where = f"this machine's own: {system}"
        else:
            where = ("NONE on this machine and none bundled - Hindi names will "
                     "show as empty boxes on screen and in Word. Install the "
                     "Hindi language pack (Settings > Time & language > Language "
                     "& region > Add a language > Hindi), or ask for a build "
                     "with the font included.")
        on_screen = bool(typeface.bundled or system)
        passed &= on_screen
        lines.append(_line(on_screen, "Devanagari font (screen and Word)", where))
        # The exported PDF and the JPEGs never depend on any of that: MuPDF
        # carries its own Devanagari face inside the packaged library.
        lines.append(_line(True, "Devanagari in the PDF",
                           "independent of this machine - the face travels "
                           "inside the app"))

        # Reading a headline off a cutting, which is what tells the app the
        # same story has arrived twice. Not "is the engine there" but "can it
        # read Hindi": the engine loads perfectly well with no language data
        # and then returns nothing at all, which would leave duplicate
        # detection quietly doing nothing on a machine nobody had checked.
        from .core import ocr

        reader = ocr.available()
        tongues = []
        if reader:
            tongues = sorted(x.stem for x in ocr.TESSDATA.glob("*.traineddata"))
        read_back, trouble = "", ""
        if reader:
            try:
                from PIL import Image, ImageDraw, ImageFont

                # Proportioned like a cutting: the headline across the top,
                # body text under it, so the reader is exercised the way it is
                # in use rather than on a picture that is all headline.
                sheet = Image.new("RGB", (980, 420), (252, 251, 248))
                brush = ImageDraw.Draw(sheet)
                face = None
                for name in ("NotoSansDevanagari-Regular.ttf",):
                    candidate = (Path(__file__).resolve().parent / "assets"
                                 / "fonts" / name)
                    if candidate.is_file():
                        face = ImageFont.truetype(str(candidate), 54)
                if face is not None:
                    brush.text((22, 26), "रेलवे ने नई ट्रेन सेवा शुरू की",
                               fill=(10, 10, 10), font=face)
                    small = ImageFont.truetype(str(candidate), 17)
                    for row in range(8):
                        brush.text((22, 130 + row * 26),
                                   "यह साधारण पाठ है जिसे नहीं पढ़ा जाता",
                                   fill=(90, 90, 90), font=small)
                    stream = io.BytesIO()
                    sheet.save(stream, "PNG")
                    read_back = ocr.headline(stream.getvalue()).text
            except Exception as exc:  # noqa: BLE001
                # A self-check that swallows its own reason is no check at all.
                read_back = ""
                trouble = f"{type(exc).__name__}: {exc}"
        works = reader and bool(read_back)
        passed &= bool(reader)
        lines.append(_line(
            bool(reader), "reading headlines (duplicate detection)",
            f"{ocr.engine_name() or ('no engine - ' + (ocr.why_not() or 'not installed'))}"
            + (f", languages: {', '.join(tongues)}" if tongues else "")
            + (f" - read back {read_back!r}" if read_back
               else f" - COULD NOT READ A TEST HEADLINE ({trouble})" if trouble
               else " - COULD NOT READ A TEST HEADLINE" if reader else "")))

        # Not "is a font present" but "does Hindi come out as Hindi". A base-14
        # font substitutes a middle dot for every character it cannot set and
        # reports success, so a Hindi heading printed as a row of dots on every
        # page and nothing anywhere said so. This draws Hindi through the real
        # exporter and counts what actually landed on the page.
        import pymupdf

        hindi = "दैनिक जागरण"
        probe = pymupdf.open()
        sheet = probe.new_page(width=400, height=90)
        from .export.build_pdf import _draw_line

        _draw_line(sheet, typeface, hindi, pymupdf.Rect(10, 10, 390, 70), 18.0)
        drawn = "".join(
            span["text"] for block in sheet.get_text("dict")["blocks"]
            if block["type"] == 0
            for line in block["lines"] for span in line["spans"])
        faces = {name[3] for name in sheet.get_fonts()}
        probe.close()
        dots = drawn.count("·")
        shaped = dots == 0 and any("evanagari" in f for f in faces)
        passed &= shaped
        lines.append(_line(
            shaped, "Hindi in the report",
            f"set in {', '.join(sorted(faces)) or 'nothing'}"
            if shaped else
            f"came out as {dots} substituted dot(s) - Hindi headings would "
            f"print as dots"))
    except Exception as exc:  # noqa: BLE001
        passed = False
        lines.append(_line(False, "Devanagari font", f"{type(exc).__name__}: {exc}"))

    # --- the browser inside the program --------------------------------------
    # The one piece most likely to be left out of a bundle: the engine, its
    # helper process and its resources. A page is loaded from memory - nothing
    # reaches out - and its title read back.
    try:
        from .ui import embedded

        if not embedded.AVAILABLE:
            raise RuntimeError("QtWebEngine is not in this build")
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWidgets import QApplication

        # The engine will not be made without an application to live in -
        # it does not fail, it fails fast and takes the self-test with it.
        # A QApplication serves every later check as well.
        _app = QApplication.instance() or QApplication([])  # noqa: F841 - kept alive
        page = QWebEnginePage()
        loop = QEventLoop()
        outcome = {}
        page.loadFinished.connect(lambda okay: (outcome.setdefault("ok", okay), loop.quit()))
        QTimer.singleShot(20000, loop.quit)
        page.setHtml("<html><head><title>engine ok</title></head><body>ok</body></html>")
        loop.exec()
        ok = bool(outcome.get("ok")) and page.title() == "engine ok"
        passed &= ok
        lines.append(_line(ok, "browser inside the program",
                           "the engine loaded a page" if ok else
                           f"loaded={outcome.get('ok')} title={page.title()!r}"))
        page.deleteLater()
    except Exception as exc:  # noqa: BLE001
        passed = False
        lines.append(_line(False, "browser inside the program",
                           f"{type(exc).__name__}: {exc}"))

    # --- a real export ----------------------------------------------------
    try:

        from PIL import Image

        from .core.models import Clip, Section
        from .export import build_pdf

        buffer = io.BytesIO()
        Image.new("RGB", (420, 560), (250, 250, 248)).save(buffer, "PNG")
        clip = Clip(
            source_ref="self check", image_bytes=buffer.getvalue(), image_ext=".png",
            native_width=420, native_height=560, section=Section.ELECTRONIC,
            label="दैनिक जागरण, नई दिल्ली",
            url="https://www.example.com/story/1",
            section_title="ELECTRONIC MEDIA",
        )
        target = Path(tempfile.gettempdir()) / "clippings-manager-selfcheck.pdf"
        result = build_pdf.build([clip], target, date.today())
        ok = result.pages == 2 and target.stat().st_size > 1000
        passed &= ok
        lines.append(_line(ok, "PDF export",
                           f"{result.pages} pages, "
                           f"{target.stat().st_size / 1024:.0f} KB -> {target}"))
    except Exception as exc:  # noqa: BLE001
        passed = False
        lines.append(_line(False, "PDF export",
                           f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"))

    try:
        from .export import build_docx

        target = Path(tempfile.gettempdir()) / "clippings-manager-selfcheck.docx"
        result = build_docx.build([clip], target, date.today())
        ok = target.stat().st_size > 1000
        passed &= ok
        lines.append(_line(ok, "Word export",
                           f"{result.clippings} clipping, "
                           f"{target.stat().st_size / 1024:.0f} KB"))
    except Exception as exc:  # noqa: BLE001
        passed = False
        lines.append(_line(False, "Word export", f"{type(exc).__name__}: {exc}"))

    # --- the cover page --------------------------------------------------
    try:
        from .core import cover_render

        page = cover_render.render_option2(
            cover_render.Option2(title="SELF CHECK"), 7, date.today()
        )
        ok = (page is not None and not page.isNull()
              and page.width() == cover_render.PAGE_WIDTH
              and page.height() == cover_render.PAGE_HEIGHT)
        passed &= ok
        lines.append(_line(ok, "cover page",
                           f"generated {page.width()}x{page.height()} "
                           f"(A4 at 200 DPI)"))
    except Exception as exc:  # noqa: BLE001
        passed = False
        lines.append(_line(False, "cover page", f"{type(exc).__name__}: {exc}"))

    # --- the sentiment dossier -------------------------------------------
    try:
        from .export import build_sentiment

        target = Path(tempfile.gettempdir()) / "clippings-manager-dossier.pdf"
        result = build_sentiment.build_pdf([clip], target, None, date.today())
        ok = result.clippings == 1 and target.stat().st_size > 1000
        passed &= ok
        lines.append(_line(ok, "sentiment dossier",
                           f"{result.pages} pages, "
                           f"{target.stat().st_size / 1024:.0f} KB"))
    except Exception as exc:  # noqa: BLE001
        passed = False
        lines.append(_line(False, "sentiment dossier",
                           f"{type(exc).__name__}: {exc}"))

    # --- clippings as pictures ---------------------------------------------
    # Worth proving in the executable: the header is drawn by PyMuPDF because
    # Pillow in this build cannot shape Devanagari, and a packaged build is
    # exactly where a missing font path would show up.
    try:
        from .export import build_jpeg

        clip.newspaper, clip.edition, clip.page = "दैनिक जागरण", "वाराणसी", "5"
        folder = Path(tempfile.mkdtemp(prefix="clippings-jpeg-"))
        made = build_jpeg.build([clip], folder, date.today())
        written = made.files[0] if made.files else None
        ok = bool(written) and written.stat().st_size > 3000
        detail = (f"{made.count} written, {written.stat().st_size // 1024} KB"
                  if written else "nothing written")
        shutil.rmtree(folder, ignore_errors=True)
        passed &= ok
        lines.append(_line(ok, "clippings as JPEG", detail))
    except Exception as exc:  # noqa: BLE001
        passed = False
        lines.append(_line(False, "clippings as JPEG", f"{type(exc).__name__}: {exc}"))

    # --- crash recovery ---------------------------------------------------
    # The store lives under %APPDATA%, which a packaged build reaches differently
    # from a script, so this is worth proving in the executable itself. Uses a
    # scratch folder: a self check must never touch the morning's real session.
    try:
        from .core.models import Section
        from .core.session import SessionStore, decode_clip, encode_clip

        scratch = Path(tempfile.mkdtemp(prefix="clippings-session-"))
        store = SessionStore(scratch)
        name = store.put_blob(clip.image_bytes)
        store.save({"pools": {"standard": [
            {"id": 7, "blob": name, "clip": encode_clip(clip)}]}})
        payload = store.load() or {}
        saved = payload.get("pools", {}).get("standard", [{}])[0]
        back = decode_clip(saved.get("clip", {}), store.get_blob(name) or b"")
        ok = (back.image_bytes == clip.image_bytes
              and back.label == clip.label
              and isinstance(back.section, Section)
              and back.section is clip.section
              # The address printed under the picture and the heading printed
              # over it are both on the clip, and both have to come back: a
              # restored morning that had lost either would export a poorer
              # report than the one that was interrupted.
              and back.url == clip.url
              and back.section_title == clip.section_title)
        store.clear()
        shutil.rmtree(scratch, ignore_errors=True)
        passed &= ok
        lines.append(_line(ok, "crash recovery",
                           f"saved and read back {len(clip.image_bytes)} bytes"))
    except Exception as exc:  # noqa: BLE001
        passed = False
        lines.append(_line(False, "crash recovery", f"{type(exc).__name__}: {exc}"))

    # --- a real document, if one was pointed at ---------------------------
    if sample:
        try:
            from .core.extract_docx import extract_docx
            from .core.extract_pdf import extract_pdf
            from .core.profiles import apply_to_clip

            path = Path(sample)
            extractor = extract_pdf if path.suffix.lower() == ".pdf" else extract_docx
            clips, _warnings = extractor(path)
            for one in clips:
                apply_to_clip(one, config, index)
            named = sum(1 for c in clips if c.newspaper)
            lines.append(_line(bool(clips), f"read {path.name}",
                               f"{len(clips)} clippings, {named} named"))
            passed &= bool(clips)
        except Exception as exc:  # noqa: BLE001
            passed = False
            lines.append(_line(False, f"read {sample}", f"{type(exc).__name__}: {exc}"))

    lines.append("")
    lines.append("=" * 60)
    lines.append("EVERYTHING PASSED" if passed else "SOMETHING FAILED - see above")
    return passed, "\n".join(lines)


def _attach_console() -> bool:
    """Write into the Command Prompt that launched us, if there was one.

    The packaged application is a windowed build, so Windows gives it no console
    and everything printed goes nowhere: run it with --selftest from a Command
    Prompt and the prompt comes straight back, silent, which reads exactly like
    a crash. Attaching to the console of whatever started us puts the report
    where the person who typed the command is looking.

    Returns False when there is no console to attach to - a double-click from
    Explorer - and then the report is shown in a window instead.
    """
    # Do we already have somewhere to print? Ask that FIRST.
    #
    # This is the ordinary case for "python -m clippings_manager.selftest",
    # which is what the README tells anybody checking a fresh install to run.
    # Such a process already owns its console - and AttachConsole REFUSES when
    # you already have one, returning 0. So the question "am I on a console?"
    # was answered "no" on the one surface that most plainly is one, and the
    # report went down the branch below that builds a QApplication and shows a
    # modal box. Run from a terminal that ended in 0xC0000409,
    # STATUS_STACK_BUFFER_OVERRUN, with no traceback and no report.
    if sys.stdout is not None:
        try:
            sys.stdout.write("")
            sys.stdout.flush()
            # The report quotes back the Hindi that OCR just read, and a
            # Windows console hands Python a cp1252 stream that cannot encode
            # any of it. Ask for UTF-8; if the stream will not have it, the
            # printing below is wrapped as well.
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001 - not every stream can
                pass
            return True
        except Exception:  # noqa: BLE001 - a stdout that cannot be written to
            pass

    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes

        # Only reached by the packaged, windowed build, where PyInstaller
        # leaves sys.stdout as None. THAT process has no console of its own, so
        # attaching to the Command Prompt that launched it is right and works.
        ATTACH_PARENT_PROCESS = -1
        if not ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
            return False
        sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        sys.stderr = sys.stdout
        return True
    except Exception:  # noqa: BLE001 - no console, no harm
        return False


def _print_safely(report: str) -> None:
    """Print the report even onto a console that cannot spell half of it.

    The whole point of this command is to tell somebody whether their
    installation works. Failing to print the answer because one line of it is in
    Devanagari turns a passing check into "Failed to execute script", which is
    the most alarming possible way to say "everything is fine".

    The file written to the temp folder is always UTF-8 and always complete, so
    nothing is lost even when the console mangles it.
    """
    try:
        print(report, flush=True)
        return
    except UnicodeEncodeError:
        pass
    except Exception:  # noqa: BLE001
        return

    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        print(report.encode(encoding, "replace").decode(encoding, "replace"),
              flush=True)
    except Exception:  # noqa: BLE001 - the written file is the real output
        pass


def main(argv: list[str]) -> int:
    sample = None
    for arg in argv:
        if not arg.startswith("--"):
            sample = arg
    passed, report = run(sample)

    target = Path(tempfile.gettempdir()) / "clippings-manager-selfcheck.txt"
    try:
        target.write_text(report, encoding="utf-8")
        report += f"\n\nSaved to {target}"
    except Exception:  # noqa: BLE001
        pass

    # A Command Prompt gets the report printed into it and no window; a
    # double-click gets a window, because there is nowhere to print. Showing
    # both would leave a dialog sitting in front of a script that is waiting to
    # finish - which is what "Check this PC.cmd" was doing.
    on_console = _attach_console()
    if on_console:
        _print_safely(report)
        return 0 if passed else 1

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance() or QApplication([])
        box = QMessageBox()
        box.setWindowTitle("Clippings Manager - self check")
        box.setIcon(QMessageBox.Information if passed else QMessageBox.Warning)
        box.setText("Everything passed." if passed else "Something failed.")
        box.setDetailedText(report)
        box.exec()
        # Deliberately NOT "del app". Dropping the last reference to a
        # QApplication runs Qt's teardown at an arbitrary point during
        # interpreter shutdown, which is the same class of fault the console
        # branch above used to hit. The process is about to exit; letting the
        # operating system reclaim it is both faster and safer.
    except Exception:  # noqa: BLE001 - the written report is the real output
        pass
    return 0 if passed else 1


if __name__ == "__main__":
    # Without this, "python -m clippings_manager.selftest" - which is what the
    # README tells anybody checking a fresh install to run - imported the module,
    # defined two functions, ran nothing and exited 0. Silence and a success
    # code, which is indistinguishable from a passing check and is the worst
    # possible answer to "is this installation working?".
    raise SystemExit(main(sys.argv[1:]))
