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
reports, each with its own clippings, dates, dossier lines, cover pages and
headline style, so several reports with different titles can be worked on in the
same sitting. The newspaper list, section headings, the words kept out and
everything the duplicate check has learned are shared by all four.

**Makes a clipping out of a link.** Paste a link - or the whole WhatsApp
message with a numbered list of a dozen in it - and each story is captured as a
clipping: the headline, the picture and the first inches of the story, without
the menus, adverts and cookie bars. Posts on X and Facebook are captured as the
post. Any capture can be trimmed by dragging its edges in. A post that needs
your sign-in can be taken from your own Chrome: the program opens the link
there and takes the picture from the screen when you say the post is showing.

**Collects straight from WhatsApp Web.** Switch on "Collect from WhatsApp" and
stay in the chat: copy a photo and it becomes a clipping, copy its caption and
the newspaper, city and page are filled in. Anything that is not clearly a
caption is refused out loud rather than guessed at. It reads the clipboard only
while it is switched on, leaves copies marked private alone, and keeps nothing
it was not asked to.

**Duplicates are shown, never silently dropped.** A clipping that repeats one
already in the list is badged; the review puts the two side by side with the
words they were matched on, and a swap button keeps the other one when the
earlier scan is the blurred one. Opening a badged clipping shows the one it
repeats beside it, with the file each came from.

**Hindi to English.** A card with Hindi or Punjabi in its headline, newspaper
or city shows an "English" button; "Hindi to English" above the list does
every such card at once and lists what it changed, card by card. A newspaper
and city typed into the headline box move into their fields in English; a
paper the list does not know is spelt out by rule and flagged for a check.

## Two things worth knowing

**The morning's work is done on the machine.** Reading the documents, naming
the clippings, finding the repeats, building the report: all of it happens on
the PC, with the network cable unplugged if you like. Nothing is ever uploaded,
and no clipping leaves the machine.

Two things reach out, and only when you ask them to:

  * **"Check for updates"** asks this repository for a version number when you
    press it, and at no other time. If it finds a newer version it offers to
    open the download page in your browser - it never downloads or installs
    anything itself.
  * **Capturing a link** opens that page in the browser inside the program -
    Qt's own Chromium, which travels with it - to photograph the story. It
    is the same as opening the page yourself. Sign in there once for X and
    Facebook; the sign-in lives in the program's own profile
    (`%APPDATA%\ClippingsManager\webprofile`) and nowhere else, and your
    everyday Chrome, its sign-ins and its history are untouched. On a PC
    where the engine is missing, the Chrome already installed is used
    instead, in a settings folder of the program's own. "Take from my Chrome" asks your
    own Chrome to open the link, the way a click on it would, and takes the
    picture from the screen when you press Take it.

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
