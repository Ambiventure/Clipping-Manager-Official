# Third-party notices

What Clippings Manager is built on, and under what terms. Every licence below
was read off the package actually installed in this project's virtual
environment, not looked up from memory — the versions are the ones the shipped
build was made with.

## The one that decides this project's own licence

**PyMuPDF 1.28.2** — *Dual licensed: GNU AGPL 3.0, or a commercial licence from
Artifex Software.*
https://github.com/pymupdf/PyMuPDF

PyMuPDF wraps MuPDF and does all the PDF reading and writing: pulling clippings
out of the division PDFs, and drawing the finished newspad. Under the free half
of that dual licence, a program that uses it and is given to other people must
itself be AGPL-3.0. That is why this project is AGPL-3.0 and not something more
permissive. The alternative is buying a commercial licence from Artifex, which
would allow any licence you like.

## Everything else

| Package | Version | Licence | What it does here |
|---|---|---|---|
| PySide6 | 6.11.2 | LGPL-3.0 (also offered under GPL-2.0 / GPL-3.0) | The Qt bindings the whole interface is built on |
| Pillow | 12.3.0 | MIT-CMU (HPND) | Crop, rotate, resize, thumbnails, merging and splitting clippings |
| python-docx | 1.2.0 | MIT | Writing the Word report |
| lxml | 6.1.2 | BSD-3-Clause | Reading raw docx XML that python-docx cannot reach — VML shapes and crop rectangles |
| rapidfuzz | 3.14.6 | MIT | Matching misspelt publication names and near-identical headlines |
| numpy | 2.5.2 | BSD-3-Clause (with bundled components under their own permissive terms, listed in its LICENSE) | Ink-band detection, finding where to split a joined clipping |
| tesserocr | 2.10.0 | MIT | Reading the headline off a clipping |
| pywin32 | 312 | PSF | Accepting a drag from a browser the way Explorer does |
| PyInstaller | 6.22.2 | GPL-2.0-or-later, with a bootloader exception | Building the .exe. The exception exists precisely so packaged programs are not forced to GPL |

### A note on PySide6 and LGPL

PySide6 is used as a library, unmodified, through its ordinary Python API, and
this project's own source is published in full.

The LGPL's central condition is that whoever receives the program must be able
to replace the library with their own version of it. For the SOURCE here that
is straightforward - anyone can install a different PySide6 and run it.

For the PACKAGED .exe the honest answer is that the obligation is met by the
combination of two things, not by one: the Qt DLLs are bundled as separate
files rather than statically linked, and the complete source needed to rebuild
the executable is in this repository along with the exact command that does it.
Somebody wanting a different Qt can install it and run `build.py`. That is the
mechanism, stated plainly rather than waved at.

The LGPL also requires the licence text to travel with a distribution that
includes the library. The packaged zip carries LICENSE and this file for that
reason.

## Bundled data and artwork

**Noto Sans Devanagari** — SIL Open Font License 1.1.
`clippings_manager/assets/fonts/`, with `OFL.txt` beside it as the licence
requires.

The Devanagari face travels inside the application rather than being looked for
on the PC, so a Hindi masthead prints the same on every machine. No Microsoft
font is bundled and none may be: Mangal and its relatives cannot be
redistributed.

**Tesseract language data** — `eng.traineddata` and `hin.traineddata` under
`clippings_manager/assets/tessdata/`, from the Tesseract OCR project, Apache
License 2.0. https://github.com/tesseract-ocr/tessdata_best

Apache 2.0 requires its licence text to accompany the files it covers, so a
copy sits beside them as `clippings_manager/assets/tessdata/LICENSE`.

**The application icon** — `clippings_manager/assets/icon/`, drawn for this
project.

## What is deliberately NOT in this repository

Newspaper clippings. The program was developed against real morning documents
from Northern Railway's divisions, and those are other people's copyrighted
photographs and article text. None of them are committed, and `.gitignore` is
written to keep it that way — including the loose page renders and screenshots
that development leaves at the project root.

If you want to try the program, use your own documents.
