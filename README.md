# Clippings Manager

A Windows desktop program that turns a morning's newspaper clippings into a
finished press report.

It was written for Northern Railway's Public Relations department, who compile a
daily "newspad" from six divisional documents plus loose clipping photographs
that arrive over WhatsApp. Doing that by hand is an hour of cutting, pasting and
renaming before anyone has read a word of it.

## What it does

**Imports a morning from whatever it arrives as.** Word files, PDFs, or images
dragged straight from WhatsApp Web or a folder. It reads the pictures out of the
documents along with the caption printed under each one, works out which
publication and which edition each clipping came from, and puts them in a list.

**Finds the repeats.** The same story reaches the department from several
divisions on the same morning. Every clipping is fingerprinted by what it looks
like and by the headline read off it, and the ones that are genuinely the same
cutting are offered for review. Nothing is ever dropped silently.

**Builds the report.** A cover page, then every clipping laid out on its own
sheet with its caption and its link, as a PDF and as a Word file that say the
same thing. There is a second interface that files clippings into Positive,
Neutral, Negative and Digital columns and builds a sentiment dossier instead.

**Keeps four newspads apart.** The Newspad button at the top holds four separate
reports, each with its own clippings, dates and dossier lines, so several can be
worked on in the same sitting. The designs, the newspaper list and everything
the duplicate check has learned are shared by all four.

## Two things worth knowing

**It works offline.** The whole morning's work is done on the machine, with the
network cable unplugged if you like. Nothing is uploaded anywhere, ever.

There is one outbound request in the whole program: a "Check for updates"
button, which asks this repository for a version number when you press it and at
no other time. If it finds a newer version it offers to open the download page
in your browser - it never downloads or installs anything itself.

**Your settings are not in the program folder.** The newspaper list, the cover
settings, and everything the duplicate trainer has been taught live in
`%APPDATA%\ClippingsManager`. Updating the program leaves all of it alone, and
there is a button that writes the lot to one file you can carry to another PC.

## Installing it

Most people want the packaged build: take the zip from
[Releases](../../releases), unzip it anywhere, and run `Clippings Manager.exe`.
There is nothing to install, no Python to set up, and it needs no administrator
rights.

If that page is empty, no build has been published yet - build it yourself from
the section below, or ask for one.

## Running it from source

Windows, Python 3.13.

```
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m clippings_manager.main
```

**Read the tesserocr note in `requirements.txt` before you do.** It is the one
dependency that will not install by itself on Windows, and the program needs it
to read headlines.

To check an installation:

```
.venv\Scripts\python.exe -m clippings_manager.selftest
```

To build the executable:

```
.venv\Scripts\python.exe build.py --zip
```

`NOTES.md` is the running record of how the thing works and why it works that
way. It is written for whoever maintains it next, and it is honest about the
parts that were got wrong first.

## Licence

Copyright (C) 2026 Ambiventure.

**GNU Affero General Public License v3.0.** See [LICENSE](LICENSE).

This is not an arbitrary pick. The PDF engine, PyMuPDF, is dual-licensed as
AGPL-3.0 or a paid commercial licence from Artifex; using it in a program that
is given away means the program is AGPL-3.0 too.

In practice: anyone may use it, copy it and change it. Anyone who passes a copy
on to somebody else - changed or not - has to pass the source on with it, under
the same licence. Using it inside your own organisation, however you like,
carries no obligation at all.

`THIRD-PARTY-NOTICES.md` lists what else is used and under what terms.
