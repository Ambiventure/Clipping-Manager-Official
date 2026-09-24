# Clippings Manager — build notes

Running record of what is built, what was decided, and what is still owed. It is
written for whoever maintains this next, and it keeps the wrong turnings as well
as the right ones, because the reasoning is the useful part.

**Two things to know when reading it.** It was verified against real documents
in `Sample clips/`, which are NOT in this repository - that is third-party
newspaper material and not ours to redistribute. And it is a running record
rather than a specification, so where a section describes something as still to
be done, check the code before believing it. `README.md` is the short, current
description; this is the long, historical one.

## How to run

Double-click **Clippings Manager.bat**, or:

```
.venv\Scripts\python.exe -m clippings_manager.main
```

Checks:

```
.venv\Scripts\python.exe -X utf8 tools\verify_stage1.py "Sample clips/31/Word"
.venv\Scripts\python.exe -X utf8 tools\verify_stage2.py "Sample clips/31/Word"
.venv\Scripts\python.exe -X utf8 -m clippings_manager.core.extract_pdf "Sample clips/31" -o extracted_pdf
```

## How the app behaves

Opens **empty**. Every morning brings different files, so there is no fixed set of
clippings baked in — you import today's by whichever route is nearest: the Import
Word / Import PDF / Add photos buttons, a drag from Explorer onto the window, or
Ctrl+V straight out of WhatsApp Web.

The review screen is a **list**, not a tile grid: thumbnail on the left, then
Newspaper / Edition / Page as aligned editable columns. **Clicking a thumbnail opens
the clipping full size** in a preview window, where it can be excluded, deleted,
rotated and renamed, with left/right arrows walking through the list without
closing it.

## Stage status

| # | Stage | State |
|---|---|---|
| 1 | `extract_docx.py` — DrawingML + VML walk, crops, sections, junk flags | done, 163/163 |
| 2 | `profiles.py` — caption regex profiles and name resolution | done, 75/75 captions |
| 3 | Label-band detection for Delhi and Lucknow | next |
| 4 | `label_ocr.py` engine bake-off over all 81 burned-label clips | |
| 5 | `extract_pdf.py` — division PDFs | done, identical output to .docx |
| 6 | `build_pdf.py` — cover page, one clip per page | done, geometry matches the real newspad |
| 7 | PySide6 UI — rebuilt to match the AI Studio layout | working |
| 8 | Word export | done |
| 9 | PyInstaller packaging | done, verified from a clean copy |

## Requirements added after the original brief

- **Both formats import.** Every division sends `.docx` and/or `.pdf`; the tool must
  take either. Confirmed viable: the division PDFs hold the same discrete images
  (32/9/10/31/40/40/1, matching the .docx exactly) and their captions extract as
  clean text, so the same division profiles serve both paths. The one difference is
  that a PDF has no paragraph order — caption-to-image pairing has to be done by
  y-position on the page. Note that Moradabad puts two clippings on one PDF page.
- **WhatsApp drag-and-drop naming.** Loose images dragged in from WhatsApp Web must
  be nameable on the spot, without a separate dialog: drop, then type the newspaper
  into an autocomplete field with the caret already in it, Enter to commit and move
  to the next. This is the import screen's main job, not an afterthought.

## Decisions worth remembering

- **Run-level streaming, not paragraph-level.** Delhi packs a section header and 39
  images into one paragraph. Sections are assigned from a document-ordered event
  stream so text flushes before each image.
- **`mc:AlternateContent` fallbacks are skipped** when the sibling choice holds a
  picture. Doesn't fire on these seven files, but since we walk both `a:blip` and
  `v:imagedata`, any file that uses the pattern would otherwise double-count.
- **Crops are stored, not baked.** `Clip.crop` is a rectangle applied on render, so
  a crop is always reversible. Negative `srcRect` values (Moradabad clip 25 has
  `t="-2411"`) are Word padding the image outward and clamp to zero.
- **The regex only lifts the page number for Ambala and Jammu.** Those two run the
  masthead and the city together with no delimiter, and no regex can know that
  `AMAR UJALA KANGRA 1` has a city while `SURODHAY BHARAT 11` does not. The name
  blob is split by trying every word boundary and scoring both halves against the
  known-name lists. Ties break toward leaving the newspaper name whole.
- **The same resolver serves OCR.** A rough Devanagari string from a burned-in label
  goes through `split_name()` exactly as a caption does, which is why
  `newspapers.json` carries native-script aliases. Editions carry them too, so
  `नई दिल्ली` resolves to `New Delhi` and the newspad prints one consistent spelling.
- **Junk is flagged, never deleted.** Min-dimension only fires when an image is small
  in *both* directions — a Lucknow digital strip is 688x118 and is a real clip. The
  Jammu logo is caught by "uncaptioned, and above the first captioned clip", because
  Jammu has no section headers for the usual rule to key off.
- **Confidence is one number from any source.** `Clip.name_source` is
  `caption` / `ocr` / `manual` and `name_confidence` is 0-1 regardless. Anything the
  user typed is never flagged; anything below 0.75 goes amber in the grid.

## Open questions

- The sample newspad prints captions in Latin (`The Times of India, Delhi`), but the
  brief asks that Devanagari names never render as tofu. Current behaviour
  canonicalises to the Latin spelling and bundles the Devanagari fonts for anything
  the user types or OCR shows. Worth confirming against the finished newspad at
  stage 6.
- Today's load is 163 clippings, not the 165 in the brief — that count came from the
  26-08 sample. The cover page count is computed, so nothing depends on it.

## Learned from the earlier prototype

Taken as-is, because they were right:

- **Clipboard paste is a first-class import path.** WhatsApp Web lets you copy an
  image straight out of a chat; making the user save to disk first and then drag is
  a wasted step. `Ctrl+V` anywhere adds a clipping.
- **The name box sits beside the thumbnail**, not behind a dialog. Naming is the
  slow part of the morning, so it has to be one keystroke away from the image.
- **Grouped by source document, collapsible**, with the group draggable as a unit.
- **Split** one image that contains two clippings; **merge** several into one.
- **Cover page template saved on the device**, reused every day.
- **Separate "From Word" and "From PDF" buttons** so it is obvious both work.

Improved on deliberately:

- **The name box is an autocomplete over `newspapers.json`, not a free-text filename.**
  Initials work: typing `du` offers Dainik Ujala. New names are added to the list on
  the spot and are there tomorrow.
- **Three fields, not one.** Newspaper / Edition / Page, because the newspad caption
  is "Newspaper, Edition" and the page number is real data, not part of a filename.
- **Most rows are already filled in.** 75/75 text captions parse today, so a
  handful are corrected rather than 163 names typed.
- **Enter commits and drops to the same box on the next row**, so a division can be
  named without touching the mouse.
- **Bulk set.** Select twelve Amar Ujala clips, set the newspaper once.
- **Full undo on every mutation**, including reorder. The earlier tool has none, and
  a misdrag across 163 rows is otherwise unrecoverable.
- **The title noise filter is unnecessary here.** "Positive News" / "Digital News" /
  "सकारात्मक समाचार" are not noise to be stripped from titles - they are section
  headers, already detected and used to classify each clip. Structure beats a
  96-word blocklist.
- **Duplicate detection.** The same clipping often arrives from two divisions; those
  are hash-matched and flagged rather than silently exported twice.

## Interface, rebuilt from the AI Studio version

The UI now follows the AI Studio build: dark slate header with the orange accent
edge, a numbered "Add today's clippings" card with the three import buttons, file
groups tied by a curly bracket, one wide headline field per row, and the navy
floating batch bar.

**How it stays fast.** The rows carry ten buttons each, which as real widgets would
be ~1,700 widgets at a full day's load. Instead every row is *painted* by a delegate
and hit-tested against `rowlayout.py`, so paint and clicks always agree on geometry.
Measured at the real volume: 163 clippings import in 1.8s and the list repaints at
about 20ms a frame.

**What each row carries:** select box, drag handle, index, thumbnail (click to open
full size), the headline field, a sub-line showing source / division / section /
page and where the name came from, then Split, Merge, Rotate, a 2x2 move pad and
Delete. Group headers carry their own select-all, rotate, move, delete and collapse.

**Naming flow.** Enter commits and drops into the next row's field, so a division is
named without touching the mouse. The parsed newspaper, edition, page and section are
edited in the preview window, and set in bulk from the batch bar.

## Export, measured off the real 26.08.2026 newspad

That file is 166 pages: 1 cover + 165 clippings. Across its content pages, **148 of
the 165 images sit at exactly left = 17.88pt and are placed at 220 DPI** - not
stretched to fill the page. Widest 540.24pt, tallest 720.24pt, nothing below
756.12pt. So the rule implemented is: place at 220 DPI, scale down only if that
would overflow, never scale up. A 331px cutting stays 108pt wide, exactly as it
does in the original.

Verified on our own output: all 162 images at left 17.88, all at 220 DPI, tops at
71.16 (captioned) or 35.88 (not), 163 pages, 32MB against the sample's 27MB.

Two things worth knowing:

- **Captions go through `insert_htmlbox`, not `insert_text`.** Drawn glyph by glyph,
  Devanagari does not shape: `दैनिक` comes out as `दैनकि` with the vowel sign in the
  wrong place. The HTML box runs a real layout engine and also centres the line.
- **JPEGs pass through untouched.** A clipping that was not cropped or rotated goes
  into the document as the exact bytes that came out of the source, which avoids
  both generation loss and a 92MB file. Anything re-rendered goes back out as JPEG.
  python-docx rejects about one in sixteen of the division JPEGs with its own header
  parser, so Word export re-encodes through Pillow as a fallback.

## Hand-added clippings

Everything dropped or pasted shares one group, `Clipboard images`, and lands at the
**top** of the list in the order it arrived - first drop first. A group per drop
would scatter a morning's WhatsApp images across a dozen one-item brackets, and the
bottom of a 165-row list is the wrong place for the thing you just added.

**Dragging out of a browser is not the same as dragging out of Explorer.** Explorer
hands over a file path; WhatsApp Web hands over whichever of several payloads the
browser feels like, and sometimes only a `blob:` URL that means nothing outside the
page that made it. `ui/dropped.py` tries each route in turn - local files, the
Windows FileContents transfer that Chrome and Edge attach, a raw bitmap, an inline
`data:` URI in dropped HTML - and when a drop carried nothing usable it says so and
points at Ctrl+V, which always works.

## Font licensing - settled

**Done, and it must stay done.** `assets/fonts/` holds Noto Sans Devanagari under
the SIL Open Font License, with `OFL.txt` beside it because that licence requires
the text to travel with the font. No Microsoft face is present and none may be
added: Mangal, Calibri, Cambria and the rest cannot be redistributed, and this
repository is public.

During development the folder did hold `Devanagari.ttf`, a copy of Windows'
Mangal, as a stand-in. It was replaced before the first packaged build. This
section used to say the swap was still to be made, which was harmless in a
private folder and became a false confession the moment the project was
published.

Two faces are actually used - `NotoSansDevanagari-Regular.ttf` and `-Bold.ttf`.
Both `ui/theme.py` and `export/build_pdf.py` name the weight they want rather
than taking whichever file sorts first, because sorting first gave **Black** and
set every Hindi masthead in the heaviest weight there is. The other faces are
kept only because they arrive together in Google's download; the packaged build
carries the two.

## Dragging out of a browser (the WhatsApp Web case)

Dragging an image from WhatsApp Web into a **folder** works, so the bytes are being
offered. Dragging it into a Qt window did not, and the reason is specific:

Chrome offers the picture as `FileGroupDescriptorW` + `FileContents`, and delivers
the contents as a **COM stream** (`TYMED_ISTREAM`). Qt only ever asks for
memory-block formats (`TYMED_HGLOBAL`), so from Qt's side `FileContents` is listed
but comes back empty. Explorer reads the stream; Qt does not. PySide6 exposes no
way to register a format converter (`QWindowsMimeConverter` is C++ only).

So `ui/win_drop.py` registers a real `IDropTarget` on the drop panel's own window
handle and reads the stream itself, exactly as Explorer does. It is scoped to that
one widget deliberately: taking over the whole window would also take over Qt's
internal drag, and dragging rows to reorder them would stop working.

Everything else still goes through `ui/dropped.py`, which tries local files (judged
by their bytes, never by their extension), fourteen byte-carrying formats, the
clipboard bitmap, and inline `data:` URIs. If a drop genuinely carries nothing it
now says which of those it saw, rather than asserting the tool is offline.

Needs pywin32 on Windows. If it is missing, or registration fails, the app falls
back to Qt's behaviour and nothing breaks.

## Export layout: fit the page, not the corner

The original newspad places every image at 220 DPI against the left margin. That is
faithful, but a Jammu cutting is 131x267 pixels, which at 220 DPI is a stamp in the
corner of a sheet. So the default is now **fit the page**: A4, one clipping per
page, 18pt margins on all four edges, centred left to right, enlarged up to 8x to
fill the sheet. Paper size and "fit to page" are both in the export dialog; turning
fit off restores the original 220 DPI placement exactly.

**The image sits directly under its caption, not centred in the space below it.**
Centring left a small clipping floating half a page beneath its own heading, which
reads as two unrelated things on one sheet.

The caption is also **set before the image is placed, and its real height measured**,
rather than a fixed block being reserved for it. Reserving a block leaves invisible
padding: the text stops but the image does not start for another 15pt. Measuring
gives a **3.3pt gap on every page**, and a masthead too long for one line wraps to
two and simply pushes the image down by exactly as much as it needed.

## Cover page, set before export

Step 1 of the main window is now the cover: artwork (remembered on this machine),
an optional heading, the date, and a live preview of the two lines that actually
change - `NUMBER OF CLIPPINGS: n` and `DATE : dd.mm.yyyy`. The count follows the
list as clippings are included and excluded, so by the time Export is pressed there
is nothing left to fill in. The export dialog opens pre-filled from it.

## Why the browser drag was still refused

`QueryGetData` in pywin32 reports success by **not raising**; it returns None, not
S_OK. The check compared it to 0, so every drag was judged unusable and DragEnter
returned DROPEFFECT_NONE - which is the "no entry" cursor over a drop panel that was
working perfectly well underneath. Detection now treats "did not raise" as success,
falls back to enumerating the offered formats, and if it can determine nothing it
accepts the drag rather than refusing a good one. A drop that then turns out to
carry nothing says so instead of failing silently.

## The build

    .venv\Scripts\python.exe build.py          # folder build
    .venv\Scripts\python.exe build.py --zip    # and zip it for copying

Produces `dist/Clippings Manager/` - 213MB, 323 files - plus a 93MB zip. Hand over
the whole folder; the .exe needs `_internal` beside it.

**A folder build, not one file.** A one-file Qt build unpacks a couple of hundred
megabytes to a temp folder on *every* launch. For a tool opened each morning that
is a ten second wait before anything appears. `build.py --onefile` still produces
one if it is ever wanted for emailing.

Three things the spec has to get right, each of which fails silently otherwise:

- **The JSON config travels with the app**, at the same relative path the code
  looks for. User edits still go to `%APPDATA%/ClippingsManager`, so an update
  never overwrites the newspaper list.
- **pywin32's COM plumbing is imported at runtime**, so PyInstaller cannot see it
  by static analysis. Without the hidden imports, reading a WhatsApp drag fails in
  the packaged build only.
- **Unused Qt modules are excluded.** PySide6 installs 640MB; the app needs a third
  of it.

### Checking a build

    "Clippings Manager.exe" --selftest

A packaged windowed build has nowhere to print to, so anything missing from the
bundle shows up as "the program did not start" and there is nothing to go on.
`clippings_manager/selftest.py` exercises exactly what packaging tends to break -
finding the config, resolving a Devanagari font, the COM plumbing, and building a
real PDF and .docx - then writes a report to the Temp folder and shows it.

Verified from a copy in a different folder with PYTHONPATH, PYTHONHOME and
VIRTUAL_ENV scrubbed: all eight checks pass, `packaged build : True`, config read
from `_internal`.

### Fonts and licensing, resolved

`assets/fonts` now ships **empty**. The Mangal stand-in has been removed - it is a
Microsoft font and could not be redistributed. Devanagari captions instead resolve
through Nirmala UI, which is present on every Windows 8 and later machine, and this
was confirmed by rendering with no bundled font at all. Dropping
NotoSansDevanagari-Regular.ttf into that folder and rebuilding bundles it and takes
precedence; nothing in the code needs changing.

## Clippings whose title is printed on the picture

Delhi and Lucknow burn the masthead into the scan, so 81 of a day's 163 clippings
have no caption text anywhere in the document. Those pages are meant to go out as
the picture alone - the title is already in it.

`Clip.title_in_image` is set at extraction time from the division's
`caption_position: burned`, and it changes four things:

- the row no longer goes amber for a missing name; it says "title is printed on
  the clipping"
- the label box reads "title already on the clipping - leave blank" instead of
  prompting
- the "needs a name" count drops from 88 to 7 - the six Moradabad digital-news
  images and the Jammu logo, which genuinely have no title anywhere
- export stops asking about them; only clippings that really need a caption are
  raised

On the page they take the full sheet from the top margin down, with no caption
band above: measured at 18.0pt from the top on every Lucknow page, filling up to
100% of the width.

This is what OCR will replace later. Until then the pages are correct, because the
title is genuinely there - just as pixels rather than text.

## The cover page is rendered once, as a picture

The cover card offers two templates from a dropdown, matching the AI Studio build.
Option 1 composites `NUMBER OF CLIPPINGS` and `DATE` onto the office artwork at a
spot the user clicks; Option 2 draws a whole blank A4 page from a heading, a centre
logo, a date and an optional watermark.

Both go through `core/cover_render.py`, which returns a QImage, and the card writes
that image to a PNG the builders place full-bleed. Doing it this way rather than
laying the cover out twice is deliberate: PyMuPDF and python-docx break lines,
measure fonts and place pictures differently, and the two formats had already drifted
apart once. Now the Word cover and the PDF cover are literally the same pixels.

Because the picture already carries its own text, the builders take
`draw_cover_text=False` and skip the two lines they would otherwise print. Without
that flag every baked cover came out with the count and the date on it twice. The
export dialog re-checks the flag whenever the cover field is edited, so choosing a
different picture - or cancelling that file dialog - lands in the right state.

Geometry is in CSS pixels on a 1654x2338 canvas (A4 at 200 DPI), set with
`setPixelSize`, never `setPointSize`, so the layout does not move with the screen's
DPI. Text is drawn at `y + ascent` because the prototype used `textBaseline: 'top'`
and Qt's `drawText` takes a baseline.

## Two things Qt's stylesheet cascade keeps catching

An unqualified `background:` or `border:` on a widget applies to every descendant,
and an ancestor's stylesheet outranks the application stylesheet regardless of
specificity. A `background: transparent` on a container was enough to erase the navy
step badge inside it. Every rule in the cover card is therefore scoped with an
`#objectName`.

Separately, a `QDateEdit` is a spin box, not a line edit, so none of the `QLineEdit`
rules ever reached it and it kept the bare native look next to properly framed
combo boxes. `QDateEdit`, `QTextEdit` and the checkbox indicator now have their own
rules in `theme.py`, and `theme.stylesheet()` adds the white tick once a GUI
application exists to draw it with.

## The sentiment board builds its own document

The board's Download buttons go to `_export_dossier`, not to the newspad dialog: a
dossier is one division, grouped into the four sentiment columns, and it takes its
settings from the board's own layout panel. The navy strip across each page names
the division - "NORTHERN RAILWAY | Delhi Division" - and the heading typed into the
layout panel replaces that text. Before this the strip printed the three-letter
filing code and the typed heading only reached the document's metadata, where no
reader would ever see it.

## Why the previews are drawn twice over

The cover preview cannot simply be the exported cover scaled down. Option 1
composites its caption at the artwork's own resolution - a 24pt caption on a
1240px-wide scan is 30px tall, 1.7% of the page - so shrinking that finished
picture into the panel left the text about three pixels high. Measured: a 300px
box gave a 3.4px cap height, and a legible 8px cap would have needed a 684px box,
which no card can afford.

So the canvas shows the raw artwork and paints the caption itself at a size chosen
for the screen (12px at 24pt, 8.4px cap), anchored at the marker and drawn from it
downward, exactly where the real block starts. The exported page is untouched -
`render_option1` still does the real compositing, and the PDF and Word covers are
byte-identical to before. The badge is deliberately larger than true scale; that is
the trade for being able to read it.

Option 2 keeps rendering the real page, because at a usable size it is legible on
its own. It moved beside the controls rather than above them: the controls only
need about 840px of the card's width, so the A4 sheet now takes the leftover column
and comes out 553px tall instead of 300 - and the card is *shorter* than it was.

## What kept the window from resizing

Nothing ever called `setMinimumSize`. A top-level widget's layout runs under
`SetDefaultConstraint`, so Qt sets the window's minimum to the layout's total
minimum on every activation, and every un-shrinkable descendant becomes a hard
floor. Measured at 2434x1060, against a 1500x950 the constructor asked for - the
window could not even honour its own opening size, and could not be made to fit a
1080p screen.

Two independent causes, both fixed:

- The standard page's cards were in a plain layout, so their combined minimum
  height was the window's. They now live in a `CardScroll` - a QScrollArea
  subclass, because QScrollArea's own size hint is capped at 24 line heights and
  would have pinned the cards to about 312px however tall the window got.
- Four non-wrapping column subtitles on the sentiment board reported their full
  text width as a minimum, and a QStackedWidget takes the largest minimum across
  *all* pages - so the hidden board was setting the width even while the press
  report was showing. The labels wrap now, and `_fit_pages` gives the hidden page
  an Ignored size policy.

Floor is now 985x328, and a resize to 700x400 lands at 985x400.

## The stylesheet cascade, a third time

`setStyleSheet("background: transparent;")` on four containers in the cover card
reached every descendant - including widgets Qt paints as separate popup windows.
Six combo popups and both date-picker calendars were painting a transparent (black)
ground under near-black text. The one dropdown that looked right was the only one
carrying its own rule.

Scoping the containers with `#objectName` fixes it, but not durably: any future
unqualified rule anywhere up the tree silently breaks it again. So each control
also pins its own popup colours - `theme.COMBO_POPUP`, `COMBO_POPUP_DARK`,
`CALENDAR_POPUP` - because a widget's own stylesheet outranks every ancestor's.
Both were applied; the per-widget rule is the one that holds.

One trap worth remembering: styling `QComboBox::drop-down` at all makes Qt stop
drawing the native arrow, so every combo silently lost its chevron. The rule is now
emitted from `theme.stylesheet()` only alongside a generated arrow image, never on
its own.

## The dossier cover, and why the preview is the page

The sentiment dossier opens on a blank sheet carrying the Indian Railways emblem,
the division's name, the report title, the date and the clipping count. The emblem
is drawn as vectors in a 400-unit space rather than shipped as a bitmap, so it is
crisp at both a 400px preview and a 300 DPI page, and there is no image to license.

The date and the clip count are the awkward part - every office wants them somewhere
slightly different - so they are dragged onto the A4 sheet directly, or dropped by
arming "Click to place". The preview is the same `sentiment_cover.render` call the
exporter makes, with a smaller `scale`; nothing about the page is approximated.

Two things had to be added to the renderer to make dragging honest:

- `pill_bounds()` / `clamp_pill()`. The renderer clamps a pill's *corner* after
  converting from the centre percentage the user aimed at, so the usable centre
  range on A4 is 23.18-76.82% across, not the 8-92% the browser prototype offers.
  Echoing a raw drag percentage would let a pill sit somewhere the next render
  refuses to draw it, and it would visibly snap back. The UI now clamps to the
  renderer's own arithmetic, derived from the same constants so it stays true if
  they move.
- The rendered image reports where each pill actually landed, under the image text
  keys `date_box` and `count_box`. A pill still in the flow has no stored position,
  so there is no other way for the preview to know where to hit-test it without
  re-deriving the whole layout.

Dragging a pill that is still in the flow promotes it to a placed pill, and the
block beneath closes up by the advance it no longer needs. That jump is correct.

## Two Qt traps this card walked into

An `&` in a QPushButton label is a mnemonic marker and simply disappears - the four
tabs read "Division  Text", "Date  Clip Count Placement", "Logo  Styling" until the
ampersands were doubled. The plain label is kept on the button as a property so
tests can assert against something readable.

`QStackedWidget.adjustSize()` resizes the stack to its own hint, so the visible page
stops filling the column until something else re-lays the parent out - three of the
four tabs rendered at half width. `updateGeometry()` asks the parent to redo the
arithmetic instead, which is what was wanted in both cover cards.

## A signal loop worth remembering

The dossier cover follows the board's division, and the board recounts whenever the
clip list changes. Connecting the card's `changed` signal to the window's recount
closed a circle: `set_division` -> `_touch` -> `changed` -> recount ->
`_refresh_columns` -> `set_division`. It ran 165 deep before Python gave up, and the
traceback pointed at `Path.exists()` - simply where the stack happened to run out,
nowhere near the cause. Counting the depth of `_update_counts` found the cycle in
one run.

The fix is in two parts: the cover no longer emits when it is merely following the
board, and it only writes at all when the division text would actually change.

## One crown, five light

Six near-black bars had accumulated - the app header, the division band, the focus
bar, the export strip, the dossier cover header and the A4 sheet bar - and on the
sentiment page they stacked down one screen with thin light strips between them.
Six dark bands stacked down one screen read badly, and the cause was the
*number* of them as much as the shade of any one.

The rule now is role, not shade. The top bar is the window frame: it never scrolls,
it names the organisation, it belongs to the application rather than to the
document, so it stays dark - lifted from #0F172A to #22385C, four and a half times
lighter, so it reads as slate-navy rather than a void. Everything below it is
furniture inside a scrolling page and is light.

The full-screen clipping viewer keeps its #0A0F1D ground and is marked in the token
block as viewport-only. A newspaper scan is a near-white rectangle; the dark
surround is a lighting decision about the artefact, not chrome. It is also modal, so
it can never stack with anything.

Two things had to be derived rather than lightened:

- **ORANGE_INK #9A4A0F.** Brand ORANGE #E8792F is 2.9:1 on white and cannot legally
  carry text. Every orange label that moved onto a light ground needed a darker ink;
  the brand orange survives untouched as a non-text element - the header's accent
  edge, hover borders, the checked checkbox, the drop-zone highlight.
- **The division band's navy rail.** The band's fill is only 1.14:1 against the
  canvas, so the 5px rail down its left edge is load-bearing, not ornament. Delete it
  as decoration and the bar dissolves into the page.

Three live contrast failures were found and fixed on the way:

- Download PDF painted white on brand ORANGE at 2.9:1 - it had never been readable.
- The interface switch's selected row was orange under white, also 2.9:1, so the
  highlighted item was the hardest one to read.
- The active focus bubble filled itself with the bright column colour: white on
  Positive #16A34A is 3.3:1, and the label is 11px. Active bubbles now use the
  badge tone (5.0-7.1:1); the bright colour stays as the rim, where it is non-text.

The focus bar also changed wording. It used to be the heaviest object on screen,
which is what stopped a filtered count being read as the division total. A warm pale
bar cannot do that by weight, so it says "FOCUS: NEGATIVE" instead of "FOCUS MODE:" -
the category name does the work the darkness used to.

## A collapsed card that would not give its height back

Collapsing the cover card left ~450px of white with the header floating in the
middle of it. The cause was not the card and not its stretch factor: a QScrollArea
swallows its child's LayoutRequest. It resizes the inner widget to the viewport and
never tells its own parent layout that the hint moved, so the viewport kept its old
height, `widgetResizable` stretched the contents back out to fill it, and the surplus
was handed to the only item with a stretch factor - the card that had just shrunk.

`CardScroll.event` now forwards LayoutRequest to `updateGeometry()`. Collapsed cover
505px -> 57px, and the reclaimed space goes to the clipping list.

Worth remembering: the first measurement of this "failed" because the toggle ran
before the window had finished its first layout pass. The fix was correct; the test
was reading a half-settled layout.

## Dropping a browser image anywhere in the window

The native IDropTarget was registered on the dotted panel's own window handle, so a
picture dragged out of WhatsApp Web only landed if it was released inside that
rectangle. It is now on the top-level window, which covers every child.

It could not simply take the window over. Qt's own drags - reordering rows, moving
cards between sentiment columns - run through the same OLE loop, and a target that
replaces Qt's kills them outright. So ours chains: it reads Qt's IDropTarget back out
of the window property OLE stores it in, registers in front, and forwards everything
it does not claim.

What it claims is deliberately narrow: a drag that carries FileContents but no
CF_HDROP paths and none of our own MIME types. An ordinary file drag goes to Qt,
which is what keeps a drop on a sentiment column meaning "file it under that heading"
rather than merely "add a clipping".

Two traps, both caught by testing rather than by reading:

- `has_file_contents` is deliberately generous - it accepts a drag it cannot read
  rather than refuse a good one, which is right for a dedicated panel and completely
  wrong as a window-wide claim test. The claim path uses a strict probe instead.
- pywin32 exposes neither `GetProp` nor `GetPropW`, so the window property has to be
  read through ctypes - with `restype = c_void_p`, or the pointer is truncated on
  64-bit and the address is garbage.

## Why the window-wide drop did not work, and how it was found

Registering the target on the window was correct. Three separate faults sat behind
it, and none of them could be caught by testing that the registration existed or
that the claim predicate behaved - which is exactly what the first round of tests
did, and why it reported success on something that accepted nothing at all.

**A bare Python instance is not a COM server.** `pythoncom.WrapObject(instance, IID,
IID)` builds a gateway that dispatches by looking up `_InvokeEx_` on whatever it is
handed. A plain object has none, so every DragEnter, DragOver and Drop failed inside
pywin32 and Windows refused the drag - silently, because the registration itself
succeeded. The fix is `win32com.server.util.wrap(instance, IID)`. Both install paths
had this, so the panel-only fallback was no fallback: the browser drag cannot have
been working on this build for as long as this code has looked the way it does.

**POINTL arrives as a tuple.** pywin32 hands the drop point to a gateway as a plain
`(x, y)`, not an object with `.x`/`.y`. Reading it the wrong way raised inside Drop,
after the drag had already been accepted - so the cursor said yes and nothing
happened.

**CF_HDROP arrives as raw bytes.** pywin32 returns the DROPFILES structure itself,
not a list of names, so `extract_paths` fell through every isinstance branch and
returned nothing.

The predicate also had to change. It refused on doubt, and `available_formats`
returns an empty set both for "no formats" and for "enumeration failed" - so "cannot
tell" read as "not ours" and the drag was handed to Qt, which could not read it
either. It now claims on doubt, and a claim that yields nothing readable is handed
back to Qt rather than swallowed, so guessing wrong costs nothing.

### One trap in the testing itself

Forwarding a **Python-implemented** IDataObject into Qt's drop target corrupts the
heap - `0xC0000374`, inside `_forward`. That is a property of the test harness, not
of the application: a real drag always carries a system data object, and the same
forward with one obtained from `pythoncom.OleGetClipboard()` completes cleanly and
Qt adds the clipping. Worth knowing before someone spends a day chasing it as an
application bug. The suite now uses a real object for the Explorer case and a
Python one only for the browser case, which our own code reads directly and never
forwards.

## Two interfaces, two sets of clippings

The press report and the sentiment board used to share one pool: ClipModel held
every row and the board was handed the same list, filtering it by division. A
dragged image has no division, and the board deliberately shows division-less rows
under *every* division so they cannot become unreachable - so every dragged image
appeared in the Neutral column of all six divisions. That was the visible symptom;
the shared pool was the cause.

Each interface now owns what was added while it was showing. Two ClipModel
instances, `self.model` and `self.board_model`, chosen over a scope flag on one
model for two reasons that matter more than the extra object:

- **Undo stays correct by construction.** Every command already captures its model
  at construction, so a redo can never act on the wrong list. A scope flag would be
  ambient state read at redo time - redo a split performed on the report while the
  board is showing and the new rows would be tagged sentiment.
- **A half-done migration is loud rather than silent.** With two models a missed
  call site shows an empty board or a clipping in the wrong list, on the first drag.
  With a scope flag it would ship a newspad containing the board's clippings and a
  count that lies - wrong output, no symptom.

The one hazard the split introduces is closed first: both pools draw ids from a
single `itertools.count`. Every signal in the app carries a bare clip id, so two
pools each starting at 1 would let a card dragged on the board resolve to a
different clipping of the same id in the report and quietly rewrite it. With one
counter a foreign id resolves to nothing.

Consequences worth knowing:

- Importing a division Word or PDF file puts it in whichever interface is showing,
  and *only* there. The division is still detected and still names the group; it no
  longer decides visibility.
- The board can now import Word and PDF itself, not only photos - its column hint
  always promised all three, and it used to be able to borrow them from an import
  done on the report side.
- Anything added while the board is showing takes the division on show if it has
  none of its own, so undivided clippings become rare rather than ubiquitous.
- A right-click offers "Send to the sentiment board", which moves the Row itself -
  id, thumbnail and clip intact - so nothing has to be imported twice, and Ctrl+Z
  brings it back.
- `_flash` writes to whichever page is visible. The report's status line lives
  inside its import card, so before this an import done on the board was completely
  silent, successes and failures alike.

Left as it is, deliberately: one undo stack for both pools. It is correct - each
command carries its own pool - but Ctrl+Z on the board can undo something done on
the report page. Splitting it into a QUndoGroup changes what Ctrl+Z means, which is
worth asking about before doing.

## The sentiment card is a tile, and you type on it

The card used to be a row - thumbnail on the left, text on the right - which gave
the clipping about 76px and no obvious place to put a headline. It is now a tile
laid out the way the reference does it: a numbered badge and a checkbox across the
top, the clipping in its own framed box with an IMAGE/LINK tag, the headline box
directly beneath it, and a row of move chips and actions at the foot.

Two details that matter:

- **Fixed width, wrapping.** The columns are `IconMode` with `Wrapping` and
  `Movement.Static`, and the delegate returns a fixed 320px width instead of the
  column's width. Without that a focused column stretched a single card across the
  whole page with the picture marooned in the middle of it. Static movement is not
  optional - the column does its own drag and drop, and Qt's item movement would
  fight it.
- **Thumbnails went from 180px to 340px.** The card's picture box is about 300px
  wide, and a 180px thumbnail upscaled into it was visibly soft.

The headline box is a real QLineEdit placed over the card's title strip, the same
arrangement the clip list uses, and it opens by itself on a clipping dropped onto
the board - focused and selected, so a pasted headline replaces the placeholder.
It ignores focus-out caused by the window activating, for the same reason the list's
editor does: a drop from a browser hands focus back a moment after the box opens.

## Counting each interface separately

The interface dropdown labelled BOTH entries with the standard pool's total, so the
board advertised three clippings while holding none. Each entry now counts its own
pool. Worth noting as a class of bug: after splitting a data structure, every place
that *reports* on it has to be revisited, not only the places that read it.

## The application's mark

`tools/make_icon.py` cuts the round badge out of the supplied artwork and writes
`clippings_manager/assets/icon/` - a 512px PNG for the window, a 128px copy for the
header, and a multi-resolution ICO (16 to 256) that Windows reads for the taskbar,
the title bar and Explorer. Re-run it whenever the artwork changes; nothing else
needs touching.

Two things it has to get right, and got wrong first time:

- **Finding the badge.** Measuring "everything unlike the corner pixel" swept in the
  faint background gradient, the drop shadow and a watermark, so the box came out
  wider than the image was tall - squaring it then ran off the canvas and the icon
  picked up a black band. The logo is the only *saturated* thing in the artwork, so
  the test is colourfulness: max channel minus min channel. Everything neutral is
  excluded by construction.
- **Cutting the corners away.** A round mark inside an opaque square looks like a
  mistake on a taskbar. The circle mask is drawn at 4x and scaled down, because a
  hard-edged circle at 16px is visibly chewed.

## Two interfaces, two histories

They are independent in every sense now: a QUndoGroup holds one QUndoStack per
interface and the active one follows the mode, so Ctrl+Z on the board can no longer
reach back into the press report. The newspad export clears only the report's
history.

The floating scroll and undo buttons appear on both pages rather than only the
report - the board scrolls too, and it has a history worth walking back. Their
visibility follows the *visible* pool's count, so they appear exactly when there is
something to scroll. `SentimentBoard.scroll_columns` sends every visible column to
one end, honouring focus mode.

## Losing a morning's work

A session represents a long stretch of unrecoverable work: six documents
imported, clippings dragged in, headlines typed, cards filed by sentiment. A
crash or a stray Alt+F4 used to cost all of it. Now the session is written as it
goes and read back on the next launch.

**What is written, and how often.** The shape follows from what actually changes.
Image bytes are the bulk - 50MB for a real morning, measured - and never change
once imported. The metadata changes constantly. So pictures go once into a
content-addressed folder keyed by SHA-256 of their own bytes, and the manifest,
which is small, is rewritten on a 1500ms debounce. Two identical clippings share
one file: 210 clippings in the real test needed 181 files. `collect()` deletes
blobs nothing refers to, and runs only *after* a successful manifest write - a
blob removed while the old manifest is still on disk would break the very session
it is protecting.

**Why os.replace.** Crash safety is the whole point, so the manifest is written to
a `.part` file, fsynced, and moved into place with `os.replace`, which is atomic on
Windows. A kill mid-write leaves either the previous good manifest or the new one,
never half of either. Verified by truncating a manifest to `{"version": 1, "pools":
{` - the application opens empty rather than half-loaded.

**The three fields that need help.** Clip has thirty; twenty-seven round-trip
untouched. `image_bytes` is not JSON. `crop` is a nested dataclass. `section` is
the quiet one: `Section` subclasses `str`, so `json.dumps` writes it happily and
`json.loads` hands back a bare string, which compares equal to the enum everywhere
and then raises `AttributeError: 'str' object has no attribute 'value'` on the
first repaint. It has to be rebuilt with `Section(value)`.

**Not through make_rows.** The obvious entry point re-parses `caption_raw` and
re-applies `probable_junk`, which would quietly undo an hour of review every
morning - a newspaper that was cleared comes back, a junk flag that was
overridden is reimposed. Restore builds `Row` objects directly.

**Two counters, not one.** `_group_serial` is embedded in each group key. Restart
it at 1 and the next import of the same document re-mints a key a restored group
already holds, and the two runs merge into one bracket. `_clip_ids` is shared
across both pools precisely so an id means one clipping; restart it and the same
id exists in each pool. Both are saved, and both resume above the highest id
actually restored - a stale number is worse than a wasted one.

**Cached thumbnails.** `make_thumbnail` already built a PNG buffer and threw it
away. Keeping it costs nothing at import, adds ~3MB to the store, and is the
difference between a 4s and a 0.2s rebuild. The rest of a 2.8s restore is reading
50MB of pictures back; it happens once, after the window is on screen, under a
wait cursor.

**When it does not come back.** A missing blob loses that one clipping and says
so, rather than refusing to open the rest of the morning. An unreadable or
newer-version manifest restores nothing and the application opens normally.

**Yesterday is not this morning's problem.** The newspad is a daily job, so the
two cases are genuinely different. Work saved earlier the *same day* is a crash to
recover from and returns without a word. Work saved on an *earlier* day is
yesterday's finished newspad; reopening to 180 stale clippings and clearing them
by hand every morning would be a chore, so that case asks - defaulting to keeping
the work, because losing a morning is the worse of the two mistakes.

**How it was proved.** Not by calling `save_session()` in a test: in real use
nothing calls it, a timer does. So a live application in a separate process
imports a document, the timer fires unaided, and `os._exit(1)` kills it with no
`closeEvent`, no destructors and no Qt shutdown - a headline typed four seconds
before the kill comes back. And on the packaged build itself, since a frozen build
resolves `%APPDATA%` differently: a session is planted, the real .exe is started
against it, closed cleanly, and the manifest it writes back is read from outside.

## Four newspads

Asked for as four "instances": four separate empty copies of the program, to
work on four newspads at once, sharing what should be shared.

**One window, one newspad loaded at a time.** Three designs were measured: four
windows in one process, four pages resident in one window, and this. The first
two each had a way to lose work that this one cannot have - two copies of a
settings panel each saving the whole file (a heading size of 48 went back to
18), one window's shutdown stopping another's duplicate check (0 of 40 results
delivered), and two sessions tidying away each other's pictures. So there is one
copy of every panel, cache, shortcut and background worker, and a switch swaps
what they are looking at.

**Each newspad is a whole session folder.** Newspad 1 is the `session` folder
there has always been, untouched, so the first launch after the upgrade is the
morning as it was. Newspads 2-4 are `session-2..4`, made the first time each is
opened and never by looking - the menu reads their manifests by path. Which one
is open is `instances.json`, written atomically. Instance metadata never goes
into session.json: an older build rebuilds that file from scratch and would drop
it. The five dossier "morning" values moved from the shared sentiment_cover.json
into each newspad's session, under one additive key; VERSION stays 1, because
bumping it made an older build's close wipe the session.

**The switch, in order, and nothing in between.** Commit editors, settle the
duplicate check, save the outgoing newspad *strictly* (a failed save refuses the
switch), write the pointer, clear, point the store at the other folder, restore
through the same code a launch uses. No events run between the clear and the
restore except the earlier-day question, and while that is up every save and
check is held off - so no timer can ever pair one newspad's lists with another
newspad's folder. If anything fails after the save, the outgoing newspad is put
back from that save; if even that fails, nothing more is saved until the program
is opened again. An emptied window must never be saved: the tidy-up after a save
deletes every picture the manifest no longer names.

**Each newspad has its own look (2.0.22).** Two reports with different titles
need two different covers - the first build shared the covers and the user said
so at once. So the two cover cards and the two headline-style panels became each
newspad's own: Newspad 1's in the four root files every older build reads,
newspads 2-4's under the same names in `design-N`, beside their session folders
and never inside them, so Start fresh, the tidy-up and set-aside cannot reach
them. The danger this moved to the switch is the measured one - a panel saving
the whole file into the wrong place - so the rules live once, in
`ui/design_file.py`: a panel's file is its own state, never worked out at save
time; pending edits go to the file being left before the panel moves; a load
never saves; a save is armed only when the DESIGN changed (a date or a division
line is the newspad's own and lives in its session, and letting it rewrite the
design meant a file that would not write could trap somebody in a newspad for
changing the day); every write is whole or nothing. A newspad seen for the first
time gets a copy of the look on screen - only a look that can be trusted: never
the defaults a panel shows because its own file would not read, which would
otherwise become that newspad's cover for good. A file that will not read is
never written over; it is set aside, renamed, only when somebody changes that
design. A failed design save refuses the switch once and says so; asked again,
the switch goes ahead and names the change it left behind. Saved setups carry
every newspad's look, and a restore reloads only the open panels whose file it
put back.

**A check under way is settled, not abandoned.** The pass is stopped and waited
for, and what it had read is copied back before the newspad leaves, so coming
back reads only the rest (8 of 24 kept, 16 read on return, the same pairs as an
uninterrupted run). Every reader callback is stamped with a pass generation, and
every deferred call that carries a bare clipping id with a newspad generation:
ids are per newspad, and a late answer or a delayed "open the headline box"
would otherwise land on whichever clipping has that id in the next newspad.

**The switch found an old reader fault.** A mid-check switch was followed by a
1.5-second freeze. No Python was running in it, so stack samples showed nothing;
timing every Qt event found 120,000 queued progress messages. The reader's
progress loop waited on its first lane, and once that lane finished it spun,
sending progress as fast as it could until the slowest lane was done. Normally
the window drained them as they came; a switch holds the window for a second,
and they piled up. Paced on a running lane, and only when the count changes:
the worst pause after a switch went from 1,500 ms to 57.

**One copy at a time.** Two copies open on one folder delete each other's
pictures. main.py takes a lock file in the settings folder: a second copy says
the program is already open and leaves, a killed copy's lock is recognised as
stale by its process id (taken over in 12 ms, measured), and a zoom restart
waits up to 30 s for the copy it replaces to finish closing. A lock that cannot
be made at all never stops the program opening.

**How it was proved.** In-process: every value round-trips, a check interrupted
at every stage resumes correctly, a failed save or a failed open leaves the
newspad whole, a stale deferred call does nothing, and memory's high-water mark
does not rise over eight switches. Out of process: the program killed with
`os._exit` at eight points of a switch, and each time both manifests read, no
picture is missing, the headline typed just before the switch is on disk, and a
relaunch opens the newspad the pointer names. And the 2.0.19 build run against a
machine with three newspads opens Newspad 1 whole and leaves the rest
byte-for-byte alone.

## Collect from WhatsApp (2.0.22)

The loose clippings arrive in WhatsApp Web as photos with a caption under each.
Adding one used to be: drag or copy the photo, come back to this window, type
the newspaper. Collect lets somebody stay in Chrome - Copy image, then select
the caption and Ctrl+C - and the program takes each copy as it happens.

**Why the clipboard and nothing cleverer.** WhatsApp's terms forbid automating
it. Its "Export chat" keeps the captions, but without media every picture is
"<image omitted>", and with media the export has to be made on the phone and
carried across - slower than the copying it would replace, and its layout could
not be checked against a real one. The clipboard is the one thing the person
already does by hand. It is read only while Collect is on, from the button, and
never remembered across launches.

**The watcher (ui/clipwatch.py).** The "clipboard changed" signal only counts;
the read happens 150 ms later, never inside the notification, because the
copying program may still be writing. If another program holds the clipboard
open it retries at 150/300/600/1200 ms rather than blocking. Copies marked
private are not read at all: password managers set
ExcludeClipboardContentFromMonitorProcessing, and Chrome sets
CanIncludeInClipboardHistory to zero on every copy from an Incognito or Guest
window. Only pictures, plain text and a file list (to say files are not
collected) are asked for; formats a browser renders on demand never are.

**Pairing never guesses (ui/collect.py).** A caption goes on the photo added
most recently, and only if that photo has no name yet. A caption with no photo
waiting, a second caption for a named photo, text that is not clearly a caption:
refused out loud, with one button that puts it where it was probably meant. One
missed photo copy therefore cannot shift every later caption along by one,
which is the mistake that would print a wrong newspaper on a morning's worth of
clippings. Every photo and every naming is one undo step on the stack of the
interface it went to.

**The caption reader is strict on purpose (core/copied.py).** parse_caption is
built to make the best of a document, and measured it reads "Sir please see
Amar Ujala today" as Amar Ujala. On a clipboard that is the wrong instinct. The
paper has to be at one end and spelt as the list spells it - vowel signs kept,
one typing slip forgiven only in a name of seven letters or more - because the
index's containment score read "Muzaffarnagar" as Srinagar and "शाम"
("evening") as Shimla, both at full confidence. The words after the paper have
to be a listed city, all of them, or a real town from the reader's own PLACES
list (about 340, with Hindi and Punjabi spellings), printed in English at 0.8:
a word merely missing from the list printed "Amar Ujala nahi mila" as the Nahi
Mila edition. Three adversaries threw 58 misreads at it; after the fixes a
sweep of every listed paper against every listed city (33,170 readings) gives
no wrong name, and the worst read is 5 ms. Reasons for a refusal are fixed
sentences: a refused copy might be a password, and it is never shown back on
screen.

**Made robust from the office's own captions (2.0.24).** In use, captions
went unread "sometimes". Measured against the forms they really copy, the
misses were not random: a city typed with a conjunct nasal where the list has
the dot (अम्बाला / अंबाला), shorthand the list does not carry (DB, DJ, IE), a
supplement's word ("HT City"), and papers the list has never heard of (वीर
अर्जुन). The fold now writes both nasals the same way on both sides of every
comparison; the shorthand lives in copied.py rather than the shared list, where
two letters would be a poor thing to go looking for inside a document's
captions; and an unlisted Hindi or Punjabi masthead in front of a LISTED city
is spelt out in English by rule (core/copied.romanise: the everyday spelling,
with the silent "a" dropped where Hindi drops it) at confidence 0.7 - under the
card's amber line on purpose, so the flag asks for the check. A refusal now
carries the copy's shape ("3 words, Hindi") and never its words.

**Quiet arrival.** A collected photo does not raise the window, take focus or
open the headline box, because the person is in Chrome. A headline box that a
drag had opened and left empty is put away before a copied caption fills that
clipping - committed if typed in, cancelled if not - or its empty text would be
taken for "no headline" and hide the name. Ctrl+V after Collect has taken the
copy says it is not needed instead of adding the photo twice.

**It stops itself** on a newspad switch (copies waiting are dropped and
counted), on close, and in a newspad that cannot save.

**Found by its suite.** Collect read `_pending_section` before every photo,
and the window only created it on the first paste or column Add, so the first
collected photo of a session failed. It is now set in the window's constructor.
One trap in the testing itself: data a script puts on Qt's offscreen clipboard
crashes the interpreter on exit (0xC0000005) with or without Collect. The
program never writes to the clipboard; the suites clear it before quitting.

## The selection bar: Include, Move to, no Rotate (2.0.22)

Asked for together, and pinned until Collect was done.

**Exclude reads Include** when every ticked clipping is already out. A mixed
selection is taken OUT, never put back: putting back a clipping the duplicate
check excluded also marks it "not a duplicate" for good (SetIncluded), which
nobody pressing a button for five clippings meant for the one they had not
noticed. The right-click "Exclude these N" had been pushing included=True for
any group, so it put them back in; it now goes through the same function.

**"Move to" means another file's bracket.** What "category" meant was settled
from the user's own earlier AI Studio build, whose navy bar this one copied: it
had "Move to Category ▾" in the same place, listing the file groups, and its
screens called file groups categories. A move changes Row.group_key and nothing
else - source_kind and source_name keep saying where the picture came from,
because the card tag, the preview and the duplicate review all show them.

Two things made it more than a reorder, both found by a design review before it
shipped:

*   **Section headings are positional.** A heading is carried by the one
    clipping that opens a run; everything after it prints under it until the
    next. Moving the ELECTRONIC MEDIA opener into an earlier file put an
    unmoved Positive clipping under ELECTRONIC MEDIA. plan_move_into hands the
    heading to the next clipping that stays, then runs the exporter's own rule
    (section_banners, through openers_of - the same path as the card's red
    chip) over the proposed order, and refuses unless every staying clipping
    prints under exactly the heading it did before. WhatsApp pictures never
    carry headings, so the everyday move never meets a refusal.
*   **Ticks add up.** A card's checkbox never replaces the selection, so ticks
    left after a move rode along with the next one. They are cleared inside the
    undo step, and undo brings them back.

Moved rows take the fold of the bracket they arrive in; fold sets are worked out
again from the rows, because run idents are numbered by order and a move can
renumber them. The note about what happened sits where the bar was: the status
line is at the top of the page, scrolled away while somebody works down the list.

**Found while mapping it, fixed with it.** "Send to the sentiment board" undid
from whole-list snapshots on the report's history while the board kept its own:
a card deleted on the board came back, and the board's undo could then put the
sent clipping on both screens as one shared object. It now moves rows one by one
and clears the board's history whenever rows cross. And a list sorted by "Filter
and arrange" painted its headings blank: the badge-icon lookup indexed a dict
that had no entry for arranged groups, so the KeyError stopped the header after
its badge - no title, no count, invisible but working buttons.

## Clippings from links (2.0.23)

Digital coverage arrives as links, not files. Pasting one - or the whole
WhatsApp message with a numbered list of a dozen in it - now gives a clipping
per story: the headline, the picture and the first inches of the text.

**The browser is the one already on the PC.** Chrome is started with no window,
pointed at a settings folder of the program's own, and driven over the debugging
port it opens for the purpose (core/webshot.py, with a twenty-line WebSocket
client rather than another library in the hand-over copy). The alternative was
to carry Chromium inside the program: PySide6 ships it, and the spec has always
excluded it, because Qt6WebEngineCore.dll alone is 195 MB against a 230 MB
application - the download would have gone from about 100 MB to 250 MB. Asked,
the department chose the Chrome they already have.

**Its own settings folder** (%APPDATA%\ClippingsManager\browser) is what keeps
the person's Chrome out of it. Theirs stays open with WhatsApp Web in it, is
never read and never closed, and a sign-in made for capturing - X and Facebook
show a post to nobody else - lives only in the program's folder. The sign-in
happens in a browser window the program opens: no password is ever typed into
the program, and it never sees one.

**The page says where its story is.** A script runs inside the page
(core/blockjs.py) and measures the headline, the picture under it and the first
run of body text; only that rectangle is captured. Anything fixed or sticky is
taken away before measuring, so a cookie bar never lands across the picture.
Three things were learned by measuring real pages:

  * **The window is 820 pixels wide on purpose.** At that width a news site
    lays itself out in one column and there is no advert rail to crop away. At
    1280 the Indian Express put "you may like" beside the headline, and the
    cutting had to be cut again.
  * **The body is found by weight of text, not by tag.** The Times of India
    puts its story in plain divs with no <p> at all, so a paragraph rule found
    only the photo and the cutting ended mid-sentence.
  * **The width comes from the picture and the first lines**, never the
    headline's box, which can span the page while its words wrap early.

**Chrome must not say it is headless.** With the default user agent X answers
"Access to x.com was denied" before the page is drawn; the same browser with
"HeadlessChrome" changed to "Chrome" is let in. A page that never arrives leaves
Chrome showing its own error page, which is recognised by its address and
refused in words rather than photographed.

**One browser for a list, not one per link.** Twelve links cost one startup
(about a second) and three to four seconds each. The capturing runs on a thread
of its own so the window stays usable, and the thread ends itself from inside -
see ui/reader.py for what happens when it does not.

**Trimming.** A capture is a good cutting, not always the right one, so the
full-size view has "Trim…": drag the edges in, and what is left is the clipping.
Nothing is cut from the picture - the box becomes the clipping's crop, applied
when it is drawn and exported, so Ctrl+Z is exact. The box is drawn on the
picture as SHOWN, already cropped and turned, so imageops.crop_from_view turns
it back and lays it over any crop already there: trimming twice narrows, never
starts again from the whole.

**Reading the links out of a message** (core/links.py) is plain text work. A
numbered list often has the words on one line and the link on the next, so a
label waits for the link that follows it; the sender's name is stripped only
where WhatsApp itself put one, or "BRICS Summit: ..." lost its first two words;
group invites are not stories; and the same link twice is one clipping.

**The site names the paper** from the newspaper list rather than a table here,
so a paper the office adds is recognised the same day. The SHORTEST listed name
holding the site's own word wins: jagran.com is Dainik Jagran, not Punjabi
Jagran, and tribuneindia.com is The Tribune. A site matching nothing gets no
name at all - a wrong masthead is worse than none, the same rule as the caption
reader.

## Making the window narrow

Narrow the window and controls on the right were cut off and could not be
clicked. Reproduced at 1050px - the Collapse button read "Collaps", the
Black colour swatch and the third Alignment button ran past the edge, and no
scrollbar went anywhere near them.

**One cause, reported many times.** A `QScrollArea` reports a small constant as its
own minimum width (36px) and does not pass its contents' minimum up the layout
chain. So the window's floor was computed as though the cards needed nothing -
985px - while the card column inside genuinely needed 1091px. `widgetResizable`
then refuses to size that column below 1091, and with the horizontal scrollbar
forced off the extra 106px is not hidden, not scrollable, just painted past the
viewport edge. Qt clips child mouse events at that edge, so those controls were
not merely off-screen, they were inert. Every other finding - the long labels, the
stylesheet `min-width`s, the fixed-width combos - only decides *how much*
overflows. None of them can make a control unreachable on its own.

**The single worst line.** `_fit_pages` in the cover card constrained only the
vertical axis. A stacked layout takes the largest minimum across every page in
*both* directions, so the hidden Option 2, which needs 1021px, was setting the
width of the card while Option 1 - which needs 323px - was the one on screen. One
added line took the card from 1055px to 511px.

**Why labels matter so much.** A `QLabel` with word wrap off reports a minimum
width equal to its entire text. Three sentences of guidance across the header were
holding the whole window open at 985px between them. `ui/fluid.py` has the two
pieces that fix this class of problem: `ElidedLabel`, which keeps the sentence when
there is room and trims it when there is not, and `FlowLayout`, which wraps a row
of controls onto a second line instead of overflowing - its `minimumSize` is the
widest single item, never the sum, which is the whole point.

**Elide, do not wrap.** Wrapping also solves the width, and it was the obvious fix
for the drop panel's hint. But a wrapped `QLabel` reports a taller size hint even
while it sits on one line, and those 32px were enough to push the card column past
the viewport and stop the cover preview growing. Wrap only where a second line is
genuinely wanted and the height is free.

**A board scrolls sideways.** Four sentiment columns that each need 275px cannot
honestly fit a 900px window. Shrinking them anyway is what put the delete button on
every card outside the mouse's reach - `CardDelegate.sizeHint` returned a fixed
320px whatever the column width, and the action buttons are anchored to the card's
right edge. The cards now follow their column, and below the width where four fit,
the board scrolls sideways like any board with more columns than screen.

**Sizing a scroll area's contents by hand.** `setWidgetResizable(True)` keeps the
inner widget at its own height hint rather than the viewport's, so wrapping the
columns in a scroller left the bottom 104px of every column outside a viewport with
no vertical scrollbar - painted, and past every mouse coordinate. `SideScroll` turns
`widgetResizable` off and states the rule plainly instead: as wide as it needs,
exactly as tall as the viewport.

**Minimum versus hint.** Asking for a whole card of column height in
`minimumSizeHint` put that card into the *window's* minimum height and stopped it
fitting a 768px laptop. A claim on space belongs in `sizeHint`, which Qt honours
when there is room and ignores when there is not.

**It opened bigger than the screen.** `self.resize(1500, 950)` was unconditional.
On a 1366x768 screen the window came up with its right-hand edge past the edge
of the desktop - the export buttons somewhere the mouse could not go - and
dragging the frame narrower ran straight into the clipping above. It now opens
large but never larger than the screen it opens on.

**Where it stands.** Both interfaces floor at 721px, down from 985 and 1038, and
both are held there by the header alone rather than by anything that can be
clipped. Every interactive control was hit-tested at 1600, 1440, 1366, 1280, 1200,
1100, 1024, 950, 880, 800 and 740px on both pages: none is past an edge, and
anything that legitimately overflows now sits in a scroller with a working bar.
Two small repairs fell out along the way - the row action buttons are hit-tested
before the elastic thumbnail and caption that grow over them on a narrow window,
and the inline headline box now follows its row when the list is resized or
scrolled instead of being stranded where it opened.

## Scrolling, and a row that stopped being centred

Two small things, one of them my own doing.

**The buttons.** Making the import row wrap for narrow windows left-aligned it,
because a flow layout has no stretches to pad with. `FlowLayout` now takes an
alignment and centres each wrapped line independently - the total width of a line
is only known once the line is complete, so it lays out in two passes.

**The wheel.** Measured before: the clipping list travelled 406px per notch - four
whole rows - while a sentiment column moved 7px. Qt multiplies each surface's own
step by the system's line count, and those steps were wildly different. One
distance now, derived from the system setting, eased over ~16 frames.

A real defect turned up under test: the list re-lays itself out mid-scroll (rows
vary in height and the view is in `Adjust` mode) and wrote its own value into the
middle of the glide, which showed as a backward jerk on every notch. The animation
watches for a value it did not write and puts it back in the same pass, before
anything repaints.

Ctrl+wheel glides like everything else - nothing here zooms, and leaving it to Qt
made it the one gesture that still jumped. Shift is handed back only where there
is something to scroll sideways; where there is not, Qt quietly turns it into a
vertical scroll, which was the same jump wearing a different hat.

## Heading and document layout

The caption above each clipping used to be constants in `export/layout.py`. It is
now a panel on each interface - page, font, size, bold, page numbers, alignment.

**Defaults are today's behaviour, not a tidy round number.** The prototype this was
modelled on defaults to 11pt; this application has always printed captions at 15pt
(`CAPTION_SIZE`), centred, not bold, on A4, with no page numbers. Copying the
prototype would have silently restyled every newspad. And because the dossier has
always set its clip titles at 11pt, left, bold, the two panels start from
*different* defaults - each from its own document's habits. Proved rather than
asserted: a default build renders page-for-page identical to one with no panel at
all.

**Font choice cannot break Hindi.** Worth knowing why: PyMuPDF never resolves
Nirmala UI at all. Latin runs in a MuPDF base face and Devanagari in MuPDF's own
built-in Noto, chosen by per-character fallback that happens outside the CSS
family list - so serif and mono are safe by construction. Word is the opposite
case: `run.font.name` writes only `w:ascii`/`w:hAnsi`, and Word picks a face per
script, so Devanagari needed `w:cs` set explicitly. It never was. Hindi in Word is
now more robust than before this change.

**What `place()` had to learn.** Setting the caption size is not enough: the box
reserved for it was sized from the fixed 15pt leading, so asking for 32pt got
26.9pt and nobody was told. `place()` now takes the leading, and a footer band
when page numbers are on - the margins are 18pt and a fit-page clipping runs right
down to them, so without reserving that strip the number would print on the
picture. In original-size mode only the *gap* between `LEGACY_CAPTION_TOP` and
`LEGACY_TOP_CAPTIONED` scales; at the default size the sum is exactly the measured
71.16, so the reproduction of the real newspad is untouched.

**One thing that was already broken.** `SentimentOptions.page` existed and was
used, but `export_options()` never returned a `page` key, so the dossier was A4
whatever anyone chose. It now follows the panel.

Below about 9pt MuPDF will not set type smaller than roughly 9.1pt in a text box,
so 8pt prints a little larger than asked. Everything from 10pt up is exact.

## Clippings as pictures

The dossier and the newspad are documents. This is the third thing the department
sends: single JPEGs, forwarded one at a time on WhatsApp, where nothing travels
alongside the picture. So the masthead, the date and the page are drawn into the
image, and the file is named for the newspaper and the day so it can still be
identified after it has been forwarded twice.

**Why it does not use Pillow.** Roughly half these newspapers are Hindi, and
Pillow in this build has no Raqm - `features.check("raqm")` is False, so is
harfbuzz - which means it cannot shape Devanagari. It would not crash; it would
draw the letters in code-point order with the matras and conjuncts in the wrong
places, in a script most of the office reads. PyMuPDF shapes it correctly and is
already what draws every caption in the PDF export, so the header burned into a
JPEG and the caption printed in the newspad come out of the same code and look
the same. The page is built at the clipping's own pixel size, so nothing is
resampled on the way through.

The header is two lines, matching the examples the department supplied: the paper
and its edition, then the date and the page. A clipping with no page number just
gets the date. A clipping with no parsed newspaper falls back to the headline the
user typed, because if they retyped it the parse was wrong.

Same newspaper, same day, twice over is the normal case rather than the edge one,
so names collide by design and the second gets "(2)". Names are stripped of the
characters Windows refuses and capped at 120.

It is on the sentiment board only, and it writes
to a folder rather than a file - then opens that folder, because the next thing
anybody does with these is pick them up and send them.

## What the dossier was losing

Three faults in the sentiment dossier, all of them silent - which is why they had
been there a while.

**The typed headline was thrown away.** `include_clip_titles` defaulted to False,
both in `SentimentOptions` and in the board's own options panel, where the tick was
labelled "Repeats the clipping's name above the picture". It does not repeat
anything: a headline typed onto a card exists nowhere else in the document. So
naming every clipping on the board - which is most of the morning's work - produced
a dossier with no names in it and no message to say so. It defaults on now, and the
wording says what it does.

**The category was stamped on every page.** The section heading was already drawn
once per category and always had been. What repeated was the navy banner strip,
which carried a category badge in its top right and is drawn on every sheet. The
banner keeps NORTHERN RAILWAY and the division; the category is announced once, in
its own heading, where it belongs.

**The report ran in screen order.** It iterated `sentiment.COLUMNS`, which is the
left-to-right order of the columns on the board: positive, neutral, negative,
digital. The document is read in a different order - positive, neutral, digital,
negative - so `build_sentiment.report_columns()` is now its own thing. The board is
a work surface and the dossier is a document; they are not obliged to agree, and
conflating them is what caused this. Anything not named in `REPORT_ORDER` is still
printed, after the rest, so a category added later cannot silently vanish.

The press report was explicitly out of scope and its exports are byte-identical
across this change - checked, not assumed, by rendering every page of the newspad
PDF and hashing it before and after.

## Where a drop lands

`_section_under` asked `QApplication.widgetAt` which column the pointer was over.
That asks the window system what is on top at that point, and during a drag the
answer can be the browser's own drag image, or any window that happens to overlap -
in which case it returns None and the drop forgets which column it was aimed at.
It now falls back to the window's own `childAt`, which does not care what is
stacked above the application. The symptom that exposed it was a test failing
intermittently depending on what else was open on the desktop.

## A heading belongs to its clipping

The symptom: the masthead sat at the top of an otherwise empty sheet with the
cutting a long way below it, which reads as two unrelated items. The first guess -
that the clipping image carried its own white margins - was wrong, and measuring
said so: across fourteen sample clippings the internal margin was 0-3%, worst case
18%, nowhere near the half-page gap on screen. The source clipping had no margin
at all. So it was layout.

**The dossier centred the picture alone.** `top = cursor + (image_height -
draw_height) / 2` put the cutting in the middle of the space while the title
stayed where the cursor was, at the top. Measured on a wide, short clipping: title
at 65..82pt, picture at 397..496pt - a 315pt gap on an 842pt page. It is now 9pt.

**The newspad kept them together but pinned the pair to the top margin**, so a
small clipping left the whole page empty below it. Both now treat the heading and
the clipping as one block and centre that block on the sheet: the title is 5pt
above the picture in the newspad, 9pt in the dossier, and the white space is
shared above and below instead of all falling below.

Getting there meant measuring the caption before placing anything. The caption's
height decides where the block sits, and the block's position decides where the
caption goes - so it is drawn once onto a scratch page purely to measure, then the
placement is computed, then it is drawn for real. Drawing first and placing
afterwards is exactly what produced the stranded heading.

**Sizes.** 15pt had been the caption size since the beginning and it reads small
under a cutting that fills an A4 sheet, so the newspad now starts at 18 and the
dossier at 16. `CAPTION_SIZE` stays 15: it is not a preference but the reference
the leading ratio and the original-size geometry are measured against, and moving
it would move the reproduction of the real newspad. Anyone can set any size in the
panel; these are only where the dial starts.

The cover page is untouched by all of this - checked by hashing every rendered
page of a newspad before and after, where page one is identical and only the
clipping pages moved.

## The board's two halves

Setting up a division is a once-a-day job. Filing clippings into columns is the
rest of the morning. The settings half had grown - heading strip, division bar,
totals, cover card, focus bar, heading layout - until it took more of the window
than the columns did, and the columns are the work surface.

They now sit either side of a drag handle. The settings scroll within whatever
they are given, and dragging the handle shut hands the whole window to the cards:
measured at a 1000px-tall window, the columns go from 333px to 753px. Where the
handle was left is written to `board_split.json` and put back on the next launch,
because nobody wants to re-drag it every morning.

`show_settings(True/False)` opens and closes it from code, which is also how the
behaviour is tested.

## What the exports are called

These are filed by hand afterwards, so the names have to suit a person reading
a folder listing rather than a program parsing one.
A division is written name-then-code - `Lucknow(LKO)` - by `_division_tag()`, and
both sentiment exports use the same function so a folder of pictures and the
report it came from cannot disagree.

    News Coverage - Lucknow(LKO) - 05.09.2026.pdf
    Lucknow(LKO)-News Clips-05.09.2026\
        P\    P - दैनिक जागरण दिल्ली - 05.09.2026.jpg
        N\    N - हिंदुस्तान लखनऊ - 05.09.2026.jpg
        D\    D - The Times of India Delhi - 05.09.2026.jpg
        Neg\  Neg - दैनिक भास्कर जम्मू - 05.09.2026.jpg

The category leads each file name as well as naming its folder, so a pile of these
still sorts into its groups once they have been copied somewhere else - which is
what happens the moment they are forwarded. Uniqueness is per folder, not across
the export: the same newspaper can appear once under P and once under Neg without
either being renamed for the other's sake.

The date in a file name is the full `05.09.2026`, matching the reports filed
beside it. The date burned into the picture stays the short `26-08-26` from the
examples the office supplied - the two are read in different places.

## The board is a page

Two wrong answers before the right one, and the mistake each time was the
same: treating a scrolling problem as a hiding problem.

The set-up half of the sentiment board - division, totals, cover page, layout -
crowded the columns where the work happens. The first attempt was a drag handle
between the two: it worked, and nobody would ever find it, being a hairline the
width of the window. The second added a labelled "Hide setup" button, which was
better but still answered the wrong question. Neither let the wheel do it, and
the wheel is what a person reaches for.

So the board is one page now. `PageScroll` holds the set-up and the columns in a
single vertical scroll and does two things to make it behave:

* the working half is kept **at least as tall as the viewport**, so scrolling to
  the bottom hands the entire window to the columns;
* the set-up half is capped at a little over half the viewport and scrolls inside
  itself, because without a ceiling it is taller than the window on its own and
  the board opens with the columns entirely below the fold - which is worse than
  what was there before. That was caught by measuring, not by looking: the columns
  reported `visibleRegion()` of zero.

The button stays, doing what the wheel does, and its label follows the scroll
position however the page was moved. The export row sits outside the scroll so
Download is always reachable.

**What this broke, and how it showed.** Two drag-and-drop tests started failing,
one of them filing a clipping under the wrong category. Both aimed at
`column.rect().center()` - the geometric middle of a column that is now taller
than the window, so the point was off-screen. The fix was in the tests, which now
aim at the middle of `visibleRegion()`: nobody drops on a part of a column they
cannot see. Worth stating plainly because the first instinct was that the router
had broken, and it had not.

## Why the dossier never had a cover

Two faults stacked on top of each other, and both were silent.

**The switch was not the switch.** `_export_dossier` read `include_cover` from the
options panel and then only ever turned it *off* when the card was unticked - it
never turned it *on* when the card was ticked. The comment above it said the card
decides; the code did not. So the decision fell through to a checkbox in the
options panel that defaults to unticked, and a person who ticked the obvious
"Enable Cover Page" got a dossier with no cover and nothing to explain why. The
card is now the only switch, and the panel's tick mirrors it so the two can never
read differently.

**And the renderer was called wrongly.** `sentiment_cover.render` takes
`(config, clip_count, page_name, scale)`. It was reached through a shim that
guessed between three call shapes, and the shape it tried first passed the page
*width* where the count belongs and the page *height* where the paper's name
belongs. That raised `AttributeError` - `'float' object has no attribute 'lower'` -
and the shim only caught `TypeError`, so it did not fall through to the shapes
that would have worked. Every cover failed to draw, the warning went into a list
nobody surfaced, and the count that belongs on the sheet was never passed at all.
The shim is gone; the call is written out.

**A test was green throughout.** `test_sentiment_ui` asserted that page one
"carries the cover wording" with `"DOSSIER" in first or "DAILY" in first or
len(first.strip()) > 0`. That last clause is true of any page with any text on it,
so the check passed while page one was the first category. It now asserts what it
meant: page one carries a picture and is not the first category. A test that
cannot fail is worse than no test, because it is counted.

## Room to design the cover

The board keeps the set-up to a little over half the window so the columns are
never pushed off the bottom. That is right while the set-up is being glanced at
and wrong the moment somebody opens the cover designer, which is a full-height
job. Opening it now lends the set-up 78% of the window - enough for the whole
customiser, with a strip of columns still showing so a clipping can be dragged
across - scrolls back to the top and brings the card into view. Closing it hands
the room straight back.

## A file I destroyed

I overwrote `test_cover_export.py` - the press report's cover test - by writing a
new dossier test to the same name. It is rebuilt from what it was covering rather
than recovered, so it is not the same file: the newspad's cover renders for both
templates, the rendered sheet is what lands on page one in PDF and Word, and a
different clipping count draws a different sheet. Worth recording as a caution:
Write replaces, and a familiar-looking name is exactly when to check first.

## A headline on one page and its clipping on the next

It affected the Word dossier only; the PDF was fine. Word decides its own
pagination, so this code can do nothing but reserve room and be right about it.

The first diagnosis was wrong and worth recording. `DOCX_TITLE_COST` was a flat
22pt, from when every title printed at one fixed size - and the size is the
person's choice now, so a long Hindi masthead at 16pt really costs 48pt. That is a
genuine fault and is fixed: `_docx_title_cost` measures the title from its own
length, its size and the width it has to wrap into. But it was not the cause. On
the wide clippings I first tested with, the picture is width-bound and the title's
cost never binds, so the fix made no difference and the pages still came out
wrong.

The cause was `DOCX_SLACK = 14.0`. Reserve the head, the title and 14pt, give the
rest to the picture, and the sums land *exactly* on the page limit - 785.9pt of an
785.89pt page. Word then charges for several things this code never sees: the
empty paragraph carrying the page break takes a line of its own on the new page,
the picture's own paragraph has a line height, and the document style adds spacing
after each. Any one of them tips the picture over, and Word moves the picture -
not the title - so the headline is left behind on the page before. The slack is
48pt now, which costs about 34pt of picture and buys back the page.

**And I nearly missed it by measuring against the wrong margin.** The check said
two pages overflowed under both the old and the new title cost, which looked like
the fix doing nothing. The margin here is 28pt, not the newspad's 36, so the usable
height is 785.89 and not 770 - the "overflow" was arithmetic of mine, and the real
finding underneath it was that the fit was exact. Worth stating because the wrong
constant in a test reads exactly like a bug in the code.

## Folding the whole list

Two pills on the bar above the clipping list: Collapse
all and Expand all. A morning is six or seven documents and a hundred-odd
clippings, and shutting them one at a time to reach the one being worked on is
fine on the day it is written and tiresome by the end of the week.

`ClipModel.set_all_collapsed` folds every bracket in one pass and rebuilds once at
the end, rather than once per group - with seven documents the difference is
visible. `all_collapsed()` and `group_count()` sit beside it so the buttons can
tell the truth about what they will do.

Two details that only showed on screen. The bar's right margin is 64, not 4: the
floating scroll and undo buttons hover in that gutter, and the second pill
disappeared underneath them. And the buttons hide themselves when the list is
empty, because there is nothing to fold - but *not* when the list holds only loose
clippings, which was my first assumption and wrong. Loose clippings arrive under
"Clipboard images", which is a real bracket like any other, so folding it is a
perfectly sensible thing to want.

## Digital coverage carries a link

A digital clipping is a screenshot of a web page, and what has to travel with it
is the address it came from - not a headline. The card's text strip reads LINK on
that column and edits `clip.url`; everywhere else it still reads TITLE and edits
`clip.label`. `EditUrl` is a command of its own so undo says which of the two it
put back, and so the two fields can never be confused for one another.

In the exporters, a digital clipping prints no heading at all: its link already
prints under the picture, where a source belongs, and a heading as well would say
the same thing twice in two places.

Two tests were describing the old arrangement and had to be told. One expected a
headline over every clipping including the digital ones. The other compared two
dossiers built at different heading sizes and found them identical - correctly, as
it happens: everything with a URL is filed under Digital, and digital coverage no
longer has a heading for the size to act on, so the check now files its clippings
somewhere that does.

## The cover bubbles have a size

The date and the clip count could be put anywhere on the sheet but not made to fit
what was put in them. Both now carry a scale, 50% to 250%, with the box, its
corner radius and its type all scaled together - and the flow advance scaled too,
so an enlarged bubble does not sit on the line below it. `_scaled_pill` clamps
whatever it is given, so a hand-edited settings file cannot produce a bubble the
width of the page.

## Five faces, because five is what there are

The panel offers more sizes - twenty-four rather than sixteen, up to 48pt - and
more faces. But not as many faces as the first attempt: that offered ten, and
measuring showed five of them were a lie. MuPDF resolves a small built-in set and
silently falls back for everything else, so Calibri, Segoe UI, Arial Narrow,
Verdana and Tahoma all drew Nimbus Sans, which is what "Standard" already is. Five
choices that change the screen and not the page is worse than not offering them.

What is offered now is the five MuPDF genuinely draws - Helvetica, Times, Courier,
Charis and Noto Serif - each mapped to a real Windows font in Word, and each
verified to come out in a different typeface. Devanagari is untouched by all of
them: the chosen face goes in front of the Hindi stack, never in place of it.

## The real Word fonts, after all

Five faces were offered, on the reasoning that the PDF could not draw more.
That was true of the approach taken and not of the problem itself, and the
correction - name the ordinary Word fonts as well - was the right one.

Naming a font in CSS is not enough: MuPDF knows a handful of built-in faces and
quietly draws one of those for anything else, which is why Calibri came out as
Nimbus Sans. But `insert_htmlbox` takes a `pymupdf.Archive`, and the machine has
the real font files in `C:\Windows\Fonts`. So the exporter now reads them from
there and embeds them - the same files Word embeds, from the same folder - with an
`@font-face` rule per face and a second one for its bold. Measured: all eighteen
faces on offer come out as eighteen genuinely different typefaces, bold included.

`available_faces()` reports which files this machine actually has, and the panel
only lists those. A face that is not installed would be a choice that quietly
printed as something else, which is the thing this was meant to stop. "Standard
(Sans)" is always offered, is still the default, and still produces byte-identical
pages - checked, because a font list is not worth changing a year of newspads for.

The Devanagari stack still follows the chosen face rather than being replaced by
it, so a Hindi masthead is drawn by a font that has the glyphs even when the Latin
is set in Calibri. Checked for every one of the eighteen.

Embedding costs about 800KB per document, once, whatever the page count.

One test had to be told: it wrote `"family": "comic"` into a settings file as
deliberate rubbish, and "comic" is now Comic Sans MS - a perfectly good answer. The
rubbish is rubbish again.


## Hindi to English, and a post from the person's own Chrome (2.0.25)

Two rows in the office's list had their newspaper and city typed into the
headline box, in Hindi - "अर्थ प्रकाश पंजाब", "राजस्थान पत्रिका दिल्ली" - and
printed in Hindi over an English report. The ask was a button on the card and
one over the list, with a summary of what was changed on which card.

**The deciding is the reader's.** `copied.english_for(clip, index)` reads a
Hindi headline with `copied.read`, the same reader Collect uses on a copied
caption, so a card and a copy come out the same: a listed paper is spelt as
the list spells it, a city likewise, a page number goes to the page field.
What the reader refuses is tried once more as a short name: up to three
Hindi words, none of them chat, are a newspaper the list has never heard of -
before a place from PLACES, or alone - spelt out by `romanise` and flagged at
0.7 like Collect's spelt-out papers. Anything longer is a headline and is left
exactly alone, and the summary says so and why ("9 words do not read as a
newspaper and a city"). The accepted cost is the same as Collect's: three
ordinary Hindi words in the headline box are taken for a paper, flagged
amber, one Ctrl+Z from where they were. Hindi already in the newspaper or city
field is respelt in place and the headline kept.

**One undo step, and it is allowed to empty the headline.** `PutInEnglish`
extends `FillFromCopy` with `label` and `no_title` among its fields - the one
command that does, on purpose: what the box held was a caption, not a
headline, and the Hindi is kept in `caption_raw` where a copied caption would
be. The list-wide button wraps every card in one macro. The pill is a
`rowlayout.clip_row(english=True)` hit, drawn like Split; the delegate asks
`copied.needs_english` per card, which reads three fields and costs nothing.

**The person's Chrome sign-in cannot be borrowed, and this was measured.**
The other ask was for captures to use the sign-in the open Chrome already
has. Three facts closed every road to it, all measured on the office machine
(scratchpad probe_cookie_copy.py, probe_borrow.py, 2.0.25):

  * Chrome 136 and later refuse remote debugging on the profile folder in use,
    and no second Chrome may open a profile that is open.
  * The open profile's cookie file is locked exclusively while Chrome runs -
    copying it is `PermissionError`. That is deliberate on Chrome's part.
  * Every profile on the machine holds only app-bound ("v20") cookies. A cookie
    row copied out of a closed profile, with its Local State, into the
    program's browser folder is thrown away by Chrome on start: the headless
    browser read 0 of them.

So `core/chromewin.py` and `ui/fromchrome.py` do the honest thing: the program
asks the person's own Chrome to open the link (`chrome.exe URL` goes to the
running instance, in the profile it has open), a small always-on-top panel
waits for them to scroll the post into view and press Take it, the panel steps
out of the way for 260 ms, and the Chrome window is pictured off the screen -
`DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)` for the frame as drawn,
`QScreen.grabWindow(0, ...)` in device-independent pixels. The clipping opens
in the preview with the trim already started, because the picture is the whole
browser window. Nothing on the site is done by the program: the person scrolls,
the person says when - which is also why it is clear of every site's terms.

Two traps in the finder: the Claude desktop app, WhatsApp Desktop and VS Code
all have Chrome's window class (`Chrome_WidgetWin_1`), so a Chrome window is
one whose title ends in " - Google Chrome" (or Edge's, or Chromium's); and
`GetWindowRect` includes the invisible resize border, seven pixels a side,
which would be in the picture. The program-owned sign-in browser stays for
sites that let a signed-in browser read posts in the background.

`chromewin` imports `subprocess`, not a network module, and the carry-forward
rule (only `updates.py` and `webshot.py` may import one) still holds: asking
Chrome to open a link is what a click on one in WhatsApp asks of it.


## Keeping the other one, and the repeat beside the preview (2.0.26)

The review screen keeps the earlier arrival and offers the later one for
deletion, which is right until the earlier one is the blurred scan. The swap
button (`DuplicatesDialog.swap`) turns the pair round with `dataclasses.replace`
on the Pair - the dialog's own list, never the window's - and remembers each
pair's arrival-order keeper in `first`, so `turned(i)` is a fact about the pair
and not a flag to keep in step. Three things follow from one press: the
verdict moves with the sides (a mark meaning "delete the one on the right"
still means that); every other pair that repeated the old keeper is pointed
at the new one, so three scans of one cutting keep one keeper between them;
and "Not a duplicate" on a turned pair spares BOTH clippings (`to_spare`) -
the next check pairs them the way they arrived, and sparing only the person's
copy would let it flag the same pair again. `review_duplicates` reads the
dialog's pairs, not the list it handed in, so a verdict is recorded the way
round it was judged.

The preview's column (`PreviewDialog._show_twin`) is the same comparison
without the modal: a badged clipping shows the one it repeats, the keeper
shows its first repeat ("and N more"), each named by the file it came in from
through the window's `_source_of`. It is rebuilt on every `show_row`, hidden
on the board and on any clipping with no partner, and a duplicate check that
finishes while the preview is open re-shows the row - except during a trim,
where `show_row` would drop the box being drawn. Two traps: `clicked` carries
its checked flag, so a signal's `emit` cannot be connected to it directly (a
lambda sheds the argument); and the arrows glyph on the swap button lives in
Segoe UI Symbol, not Segoe UI.


## Three faults from one morning's use (2.0.27)

**Word spilled a clipping onto the next page, ten times in 257.** The PDF
measured each caption on a scratch page before sizing the picture
(`build_pdf._draw_line`); Word was given `caption_leading` - one line - and a
masthead that wraps to two lines at 18pt left the picture a line too tall.
Word cannot keep a caption with a picture that does not fit beside it, so the
page break put the caption alone on one sheet and the picture on the next.
`build_pdf.measure_caption` is now the one measure both exporters ask, with
the same embedded faces (`Typeface`), so the wrap comes out where Word's will.
`DOCX_SLACK` still covers Word's own rounding.

**Re-importing the program's own report called its clippings junk.**
Measured with a report built from a 1200x140 strip and a 380x110 screenshot:
"extreme shape" and "very small", the rules meant for icons and rules in a
division's document. Every report the program writes is stamped (the PDF's
creator and producer, the Word file's comments - `assemble.MADE_HERE`), and
`build_clips(own=True)` leaves those two rules out for a stamped file. The
repeat rule and the letterhead rule still apply: the cover picture is still
not a clipping. A stranger's file that happens to hold the same pictures is
judged as before - the suite strips the stamp and checks.

**The sentiment cover had no text sizes.** The lines were constants
(`ORG_SIZE`, `TITLE_SIZE`...). Five config fields now hold a size in points,
0 meaning the drawn size, so every cover saved before them prints as it did
(pinned pixel for pixel). The fixed advances between lines were measured for
the drawn sizes, so `_block` takes `drawn` and moves the cursor on by the
extra line height when a line is set larger - otherwise the subtitle printed
through the title. The card's boxes are QComboBoxes keyed by float data;
`_write_sizes` offers a hand-typed size as itself rather than snapping it.


## The black drop-down, again (2.0.28)

The sentiment cover card's tab pages carried `background: transparent`
unqualified, so it reached every descendant - a combo's popup included,
which painted black with black type. The same trap the standard cover card
walked into and documented ("Two Qt traps this card walked into"). Both
fixes are in: the page rule is scoped by object name, and every size box
carries `theme.COMBO_POPUP` on its own sheet, which no ancestor can undo.
The lesson is now three times over: never an unqualified rule on anything
that can hold a popup.

The sizes moved beside their text on the Division & Text tab (`_field_head`
puts the label, anything else on that line, and the size box on one row),
where the person types the line they are sizing. The notes line has its
own size; the two footer lines offer up to 20pt because they sit a fixed way
up from the bottom edge.


## Collect: the page, not the list (2.0.29)

2.0.24 made the list "follow each collected photo" with `list.scrollTo` -
and the list cannot scroll: it stands at its full height inside the page
(`body_scroll`), as test_dropscroll's own docstring had already said about
the drop. Measured with probe_collect_scroll.py: after a quiet add the page
sat at its OLD maximum and the new row started exactly at the visible edge,
one row under the fold, from wherever the page had been. `_reveal_on_page`
maps the row into the page's coordinates and sets the page's bar so the row
sits at the foot of the view - twice, at 0 and 160 ms, because the page's
range only grows once the list has laid the row out.

The caption that "goes missing altogether": nothing in the reader or the
collector loses a copy silently except one path - a copy carrying formatted
text (`text/html`) with no plain copy of it, which `classify` returned as
None and the watcher swallowed. That is read off the markup now
(`QTextDocumentFragment`, parsed, nothing fetched), a None is said as
"nothing", and the Collector keeps a history of every copy and its fate
(`Collector.history`, "What was copied…" on the bar) - kind, size or shape,
and what was done, never the words - so the next "it missed the caption"
can be answered from the record rather than guessed at.

## The dossier's Word cover is text (2.0.29)

`sentiment_cover.blocks` walks the same flow as `_paint` - the emblem box,
each line wrapped with the same metrics, the pills at `_pill_origin`, the
footer a fixed way up - and hands back `cover_render.Placed` items in page
pixels at 200 DPI, which `word_cover.add_cover` already knew how to set as
anchored text boxes and one picture. Deliberately a second copy of the flow
rather than a refactoring: the picture is pinned pixel for pixel by its
suite, and this must not move it. `add_cover` now takes whatever groups the
layout names (the dossier has five: heading, date, count, caption, logo)
instead of three by name. The emblem is drawn to a PNG in the temporary
folder for Word to embed; a custom logo file is used as it is. Not written:
the pills' rounded backgrounds and the border frame - the words are what
get edited, and a page border is a different thing in Word.


## The caption that "goes missing": printed as typed (2.0.30)

Two in ten captions "missed" in use, with the photos landing every time.
The clipboard path is the same for both, so the misses are refusals: the
reader is strict on purpose - "newspaper, city, page" or nothing - and a
refusal reads as a miss to somebody working in WhatsApp with the bar out of
sight. The 2.0.24 measurement (117 office forms) still reads 116, so the
two in ten are forms the office types that nobody has written down.

The answer is not a looser reader. A caption the reader cannot take apart
is still the caption the office copied, and what the report needs is the
words above the picture: `collect.as_typed` puts them in the headline box
exactly as written (`commands.CaptionAsTyped`, FillFromCopy plus `label`),
at confidence 0.5 so the card is amber, with the bar saying why the words
were not read. Refused still, deliberately: one token (a copied password is
one token), an address, chat, mostly numbers, more than 60 words, two
bubbles. Up to 16 words it happens at once; up to 60 it is offered on the
button. "What was copied…" records it as "printed as typed on No. 7 (the
reason)", which is also what to read when it happens again - the reason is
the form the reader wants teaching.


## The browser inside the program (2.0.31)

The ask: capture the story without Chrome's tabs and bookmarks bar, sign in
once inside the program, and capture twelve links with nothing on the
screen. Qt's own Chromium (QtWebEngine, already in the toolkit) does all
three, and the block finder and the DevTools client of core/webshot drive
it unchanged: `webshot.capture_over(wire, url)` is the one capture, over
headless Chrome's wire or the embedded page's.

Three facts measured on the way, each of which cost a probe:

  * The DevTools server of the embedded engine answers from the thread
    that owns the browser - Qt's main thread. A blocking request made from
    the main thread waits on itself for ever. Every call over the wire is
    made from a worker thread (`embedded.Catcher` on a QThread, as
    webclip's Catcher always was).
  * A page with no view gives no screenshot, ever: `Page.captureScreenshot`
    needs a rendered surface. A view in a window shown off every edge of
    the desktop (`PARK_AT`, a Tool window that never takes focus) gives one
    in half a second. That is the whole "silent" mechanism.
  * The debugging port has to be in the environment before Qt reads it,
    and QtWebEngineWidgets must be imported before the QApplication exists
    (`embedded.prepare()` in main.py, before the application is made); the
    port itself only opens when the first page is made, and only on
    127.0.0.1. `webshot.free_port` picks it, because webshot is the module
    allowed to know what a port is.

Sign-ins are recorded by host name off the profile's `cookieAdded` - never
a value - into `webprofile/signed-in.json`, which is how the button can say
"Signed in: x.com" without opening the engine. `embedded.usable()` is false
on the offscreen platform, so every offscreen suite keeps the headless path
and its stand-in browser; test_embedded runs on the real window platform
with a loopback HTTP server for the fixture. The build spec had excluded
QtWebEngine to keep the zip small; it is in now, with QtWebChannel and
QtPositioning, which the engine links.

## Three of the person's own asks (2.0.31)

**The summary page** is `export/summary.Summary.of(clips, board_clips,
config)`: four tallies (kind, division, newspaper, board), counted once so
the PDF and the Word file cannot disagree, rendered by each builder in its
own way (`_summary_pages` flows onto a second sheet when the newspaper list
is long; the Word page uses a right tab stop for the counts). "Print" is
every section that is not electronic, digital, social or an advertisement,
because that is what the import files a print cutting under. Off by
default in the export window and remembered.

**Shown in its folder** is `explorer /select,<path>`, after "Open when
finished" and independent of it.

**Tidying** is `core/tidy.py`: the blank margins by a difference against
the corner colour (`ImageChops`, no loops), then - for a portrait picture
at least 480 wide - the status bar from the top and the navigation bar from
the bottom by row signatures on a posterised 480-wide copy: a run of rows
at least 84% one colour, between 1.2% and 7.5% of the height (10% at the
bottom), carrying a few marks (0.1% to 22% of the band's pixels: the time,
the icons, the pill) and ending at a plain edge. Conservative by design: a
missed bar costs a moment with the trim tool, a wrong one a piece of the
story. Applied in `_add_loose` to pictures that came by hand (`source_file
== "clipboard"`) as a CropRect, never to the bytes; the layout card's
"Trim phone bars" switches it off, and Collect's bar says when it happened.
The switch is a preference in the export settings file that every newspad
shares, only shown on the card - not one of the card's layout values, which
are HeadingStyle's own keywords and nothing else (test_heading builds a
HeadingStyle from them, and a stray key there took the suite down).

**The build numbers itself.** `build.py` bumps the stamp on every packaged
build and rewrites version.py, latest.json and version_info.txt; a rebuild
of the same version needs `--release 2.0.30`, or it becomes 2.0.31 with no
entry in changes.md. Recorded here because it cost a round.

## The division short forms, and links glued together (2.0.32)

**What happened to "HT LKO".** Measured on 2.0.31: every one of 24 forms
with a division code was refused - "HT LKO", "NBT LKO page 3", "HT (LKO)",
"DB UMB 4", "अमर उजाला LKO" as "the words after the newspaper are not a city",
and "LKO NBT" as "did not start with a newspaper". Collect then printed the
two words as typed (`collect.as_typed('HT LKO')` is `('auto', 'HT LKO')`),
which is the person's What was copied… line word for word. The reader knew
LKO and the rest only as file-name divisions, never as the city in a caption.

**The fix is one check at the top of `copied._listed_city`.** Both orders
come through it - `_edition` for paper-first, `_paper_at_end` for
city-first - so nothing else needed changing. A single word that is a code
is the division's name from divisions.json, printed only when that name is
on the edition list (so a renamed division never prints a city the list does
not know). Codes are matched in any case except JAT and MB, which count only
in capitals: "Amar Ujala Jat andolan" is a headline and "mb" is megabytes.
The codes are read per read in `_names`, through `load_config` (which
already caches the file) - no second table, and no cache in copied.py,
which test_copied pins. A missing or malformed file gives no codes and
the read never raises. `copied.division_code(word)` is the same test on one
word, cut the way a caption is cut, and `copied.division_used(reading,
index)` says which code a caption's city was read from, for the step that
files a collected clipping under the division (both below).

Measured with the change (test_copied, 741 checks, was 570; 818 after the
review fixes below, 827 after the second round):

  * all 24 forms read at 1.0 with the city known, plus both orders, dotted
    and bracketed codes, pages and Hindi mastheads;
  * every listed paper and shorthand beside every code, both ways round: 816
    readings, no wrong name, every paper-first one read; the only refusals
    are the six "<code> Aaj", because Aaj after a city is "today";
  * `probe_caption_forms.py` (117 office forms) prints byte for byte what
    2.0.31 printed (kept as `caption_forms_2031.txt` beside the suite, 116 of
    117), with the codes on, with them off, and with the two looser rules
    below switched on.

**FZR prints Ferozpur, as divisions.json spells it**, while "अमर उजाला
फिरोजपुर" prints Firozpur. newspapers.json has a "Firozpur" entry (with
Ferozpur as an alias) and a separate "Ferozpur" entry; the table is sorted,
so `_exact` finds Ferozpur first. Not merged here - a question for the
office. Hindi and written-out division names ("लखनऊ मंडल", "Lucknow
Division") are deliberately not read in this release.

A side effect worth knowing: "Put in English" reads a Hindi headline box with
`copied.read`, so "अमर उजाला LKO" there now becomes Amar Ujala, Lucknow too.

**`ReaderRules`, read's optional third argument**, holds what a session may
let through. Nothing in the window passes one yet; Collect's options menu is
the next step. The defaults are 2.0.31's reading plus the codes:

  * `city_alone` (off): "LKO", "Lucknow page 3", "LKO 3" name the city with
    the newspaper empty, which the card flags amber. A chat word that is also
    a listed edition is still refused ("main" is "I" before it is Main).
    Under this rule only, a city on its own line that agrees with the caption
    above it is the caption wrapping, not a second caption - otherwise "Amar
    ujala / jalandhar" would have been refused as two captions.
  * `unlisted_paper_in_english` (off): "Veer Arjun Delhi" is Veer Arjun at
    0.7, the Hindi rule for English letters. What stands in front may not be
    a city, a town or a code ("Lucknow Delhi", "LKO Delhi"). The measured cost
    is "Reached Delhi" read as a paper called Reached, flagged amber, which
    is why it is off.
  * `towns_as_typed` (on): switched off, "NBT Mumbai" is refused.

`copied.listed_paper` and `copied.listed_city` answer "is this on the list"
for a box a person types into. Traps kept: Reading stays at eleven fields
and collect.py still uses only read, caption_values and as_typed_words
(test_copied section 0). So which code a caption's city was read from is
asked of `copied.division_used(reading, index)`, not carried in a new field.

**Which code a caption used: what review found.** The recipe first handed
to the next step split `reading.text` on spaces and asked `division_code`
of each word. Of 22 forms the reader reads as a division's city, it found
no code for 11: "HT-LKO", "HT,LKO", "HT/LKO", "HT:LKO", "HT–LKO",
"LKO-NBT", "HT|LKO", "HT;LKO", "HT(LKO)", "HT&LKO", "HT+LKO". The cause is
that `reading.text` keeps the caption as typed, and "HT-LKO" is one word to
split(); the reader cuts words its own way (page, dates, words such as
"edition", then separators and hyphens). That cutting is now one function,
`_name_words`, used by the caption test itself (the 117 forms still print
byte for byte as 2.0.31) and by `division_used`, which gives a code only
when that division's name is the city the reading printed - "HT Delhi"
gives nothing, even with "DLI" elsewhere in the copy. `division_code` had
the same fault the other way: it said yes to "L-K-O", "l_k_o", "L/K/O" and
"J:A:T", which the reader refuses. It now runs the word through the same
cutting, and test_copied holds it to the reader over 20 odd forms. All 816
sweep readings give their own code back.

**Glued links.** `links.find` cuts a match where a second `http://` or
`https://` starts inside it, so "https://a.in/xhttps://b.in/y" is two stories
- text already glued, typed, or pasted through a box that does not add the
new line. The first cut spared only a scheme after "=" ("?url=https://…").
Review compared it with 2.0.31 and found it also broke addresses that carry
another inside them, each into an address that goes nowhere plus a second
row: "urldefense.com/v3/__https://…", "search?q=cache:https://…",
"?next=%2Fhttps://…", "?next=/https://…", "&https://…", "#https://…",
"%20https://…", "12ft.io/https://…", "r.jina.ai/https://…".

`links._carried` now decides. A scheme is carried straight after = : _ & #
? or a percent-escape; anywhere in the query or fragment unless straight
after a letter, a digit or a sentence's punctuation
("?utm_source=whatsapphttps://…" is still glued); and straight after a
site's front page with no path. Anywhere else in the path it is glued, "/"
included, because an Indian Express link ends in "/" and the next begins
straight after it. Each scheme is judged against the piece it is in, not
the whole run, so a query in the first link does not carry a third.

Measured over the reviewers' 66,456-text corpus, 2.0.31 against now: 23
texts give different links, every one with a scheme inside the match. 21 are
glued links pulled apart (a WhatsApp invite glued to a story now gives the
story). The other two are the accepted cost: an archive's address with a
path before the story ("web.archive.org/web/2024…/https://…",
"archive.ph/newest/https://…") is cut in two.

**Collect's reader took a glued pair as ONE link**, to the run-together
address, in 2.0.31 and in the first cut of this release; the first version
of this note said it refused them, which was never measured and was wrong.
End to end (offscreen, sandbox APPDATA), a photo followed by a copy of "HT
LKO https://…/x-1https://indianexpress.com/y/" put the glued address on the
photo. Changed on purpose: `copied._read_bubble` now cuts each token with
the same rule, so a glued pair is refused with "it had more than one web
address", the same as two addresses with a space between them, and a caption
copied with a glued pair is refused with it, as it is with a space. The same
link glued to itself is that link once. copied.py may not import links.py,
so the rule is a twin there (`copied._unglued`, `copied._carried`);
test_copied holds the four patterns identical, character for character, and
the two cuts equal over 21 glued and carried forms. Over the corpus, 23 of
Collect's readings changed from the first cut, all with a scheme inside: 17
glued pairs now refused, the two archive addresses now refused as two (the
same cost as the links list), "http://https://b.in" in two forms now the
link after it, the same link glued to itself now one link, and a WhatsApp
invite glued to a story now the story.

**Share links end in "=" (review, round 2).** The rule above counted a
scheme straight after any "=" as carried, and an Instagram share link ends
in a value's own "=": base64 padding, "?igsh=MWQ1ZGUxMzBkMA==". So
Instagram (igsh "=", "==", the copy-link form, the older igshid) and
Facebook's "/share/r/…&rdid=Xy12==" glued to the next link were still one
address. End to end (offscreen MainWindow, sandbox APPDATA), "HT LKO " + an
Instagram link + a Hindustan Times link put the run-together address on the
photo as "Hindustan Times, Lucknow" and its link, while the same two the
other way round were refused. 2.0.31 did the same, so it was not a
regression, but it made the release note false for the links the office
pastes most. Threads "?xmt=", YouTube "?si=", X "&s=19" and Facebook
"?mibextid=" already split, because they end in a letter or digit.

The fix is `_KEY_EQUALS`, a fifth twin pattern: an "=" (or "%3D") carries
only when it closes a key's name, straight after ?, &, ; or # (or their
escapes) - "?url=", "&u=", ";jsessionid=", "#url=", "#:~:text=",
"%3Furl%3D". An "=" that ends a value is glued, so "…==https://" and
"…%3D%3D" (a Google Maps "g_ep=") are two links. In the query or fragment,
"-", "_" and "~" now end a value too: a YouTube "si" code is url-safe
base64 and ends in "-" or "_" about one time in thirty. `_CARRIER_MARK`
lost its "=", which _KEY_EQUALS now decides. Measured: every carried form
test_weblinks and test_copied pinned before still one link; over the
reviewers' corpus (66,456 texts, 55 with a scheme straight after a
non-space) 0 differences in `links.find` and 0 in `copied.read`; the worst
case of one 17 KB token of 1000 carried addresses went from 122 to 159 ms.
The new cost, pinned in test_weblinks: an address carried after an "=" in
the path rather than the query, "r.search.yahoo.com/RU=https://…", is cut in
two (Yahoo escapes that address in practice). "https://a.in/x==https://…",
which nothing pinned either way, is now two links.

## Capture quality: waiting, clearing, and the width (2.0.32)

**The two bad captures were reproduced exactly, and neither was a loading
problem.** India Today's came out 1594x450 px from the browser inside the
program (headless 1624x394), the size of the person's picture. The lead
photo had finished loading (complete, naturalWidth 690) when it was taken.
The 2.0.31 FIND_BLOCK ended the cutting at any advert-named block lower than
the headline, and `div.ads__common` sits between the standfirst and the
photo. Hindustan Times ended at its `google_ads_iframe` the same way.
Economic Times came out 1390x1424 in both engines: at 820 px the page keeps a
minimum width of 1003, its headline is centred across both columns with words
from 104 to 899 px, and the rail rule pulled the right edge to 668, through
the words; the 16 px padding added afterwards let 17 px of the rail back in.
A headline flush with the page edge (HT) lost its margin to a clamp at 0.

**The capture now runs in steps (`webshot.capture_over`, scripts in
`core/blockjs.py`), each from a measured failure:**

  * PREPARE_PAGE never waits for the load event: HT sat at "interactive" for
    over 25 s and ET needed 6.7 s. It waits for DOMContentLoaded (4 s),
    turns lazy pictures eager and moves data-src and friends into place,
    scrolls the top 3000 px only (so a "next story" feed does not take over),
    then waits for pictures, background pictures and posters in that region
    (4 s) and fonts (1.5 s). Every frame wait is raced against 120 ms, and
    every scroll is `behavior: 'instant'` - a page with smooth scrolling
    would otherwise still be moving when measured.
  * CLEAR_CLUTTER hides adverts by whole name tokens and adjacent-token
    compounds, never substrings, and never hides the headline's holder or
    story text (300+ characters, under half in links). Each guard is a page
    that broke: HT keeps its whole story in `taboola-readmore` (6821
    characters), TOI's lead picture is `vdo_embedd`, Bhaskar's news list is
    named with hashes like `ad3ccf1a`, NDTV's story wrapper is
    `js-ad-section`, and NDTV's footer link "Advertise" is not a label.
    Emptied wrappers collapse (Bhaskar left a 600 px gap). Fixed and sticky
    elements are hidden here - no longer in FIND_BLOCK - except a pinned
    page wrapper holding the headline, which is let flow: the old rule hid
    it and the wall fixture came out as an 820x32 refusal.
  * FIND_BLOCK's width is the union of the headline's words, the picture and
    text lines measured from the text itself (TOI's paragraphs wrap bare
    around a floated picture); never narrower than the headline; a rail
    beside the column is blanked (visibility) rather than cropped; a block
    ends the cutting only below the lead picture; the bottom snaps to a
    whole line; a bare `<article>` is a post (signed-out X, September 2026);
    padding the page edge eats comes back as `margin` for `paint_margin` to
    paint in the page's background colour.
  * A lead player with no picture of its own gets the page's poster or
    og:image in its place: ET's player iframe goes blank or black about 3 s
    in, and `--autoplay-policy=user-gesture-required` gave a black box.
  * The picture is taken INSIDE the window. `captureBeyondViewport: true`
    resizes the view after measuring: HT's feed moved the kept photo from
    y=1502 to y=6341, India Today moved 73 px in Qt. Measured with a ruler
    page: with false, the clip is in page coordinates but only what is inside
    the window is painted. So the window is fitted to the cutting (820 wide
    unless the cutting overhangs, then the page's own width, at most 1600;
    as tall as the cutting + 40), the page is scrolled to it, cleared and
    measured again, and shot with false. Kept things outside the clip widen
    it; if the headline or picture moved more than 4 px during the shot it is
    taken once more.

**The browser inside the program.** Qt's scrollbar made the parked page 805
px wide; `ShowScrollBars` is now off on that page only (the browser window
keeps its own). HT stops Qt's page running scripts about 9 s after it opens
and it never recovers; `Page.navigate about:blank` unsticks it at once, and
`Host.renew()` makes a new parked page if even that fails. `Catcher` does
this between links, so one page fails its own link and the next captures.
Everything a parked page needs is set in `Host._new_page`, so a renewed
page has it: step B's permission handler belongs there.

**Every wire call keeps its limit.** 2.0.31's `_Wire.wait` sat in `recv` for
the socket's 30 s and let a bare TimeoutError out. Now each read gets what is
left of the call's own limit and a timeout is `ShotError(kind="stopped")`.
The design note said partial frames were already safe; they were not quite:
`_message` took the two header bytes out before the body had arrived, so a
timeout between the two would have put the wire out of step. Frames are now
looked at in place and taken out whole (test_capturequality 0b drives a fake
server that sends half a frame across a timeout). `PREPARE_SECONDS` is 16,
not the design's 20: PREPARE_PAGE's own limits add up to about 11.5 s, and a
busy page then fails in 17 s rather than 21.

**`ShotError(message, kind)`**: "sign-in" (a wall, or X's empty post box),
"gone" (Chrome's error page), "stopped", "not-a-story". The wording no longer
names "Sign in for captures", which step B removes: it says to sign in to it
in the browser inside the app, or take it from your Chrome.

**`webshot.capture_current(wire, url, restore=True)`** pictures a page
somebody has open, for step B's browser window: no navigation, no
scroll-through, no promotion of lazy pictures, videos left alone, the layout
width kept (`setDeviceMetricsOverride` width 0, DPR 2), scrollbars hidden
with `Emulation.setScrollbarsHidden` for the shot only. **Measured, and not
what was expected:** on Qt's visible page that call does nothing - the 15 px
scrollbar stays, with or without a metrics override (innerWidth 1020,
clientWidth 1005 throughout; probe_qt_scrollbars.py). It still hides
Chrome's. The scrollbar stays out of the cutting because FIND_BLOCK clamps
the cut to the page's width inside it, and test_embedded pins that rather
than the hiding. Hiding it for real would mean flipping the window page's
ShowScrollBars, which re-lays the page the person is reading. Every change the
scripts make is written down on the element (`data-clip-prev` holds the
attributes' old values, inserted nodes carry `data-clip-added`) and
RESTORE_PAGE undoes it in a finally, with the scroll put back; a stuck page
is never sent to about:blank. The restore is sent even to a page that stopped
answering (2 s limit, the answer not waited for beyond it): a page that was
only busy runs it when it comes back, instead of keeping its header and
adverts hidden. **Trap, measured:** an inline style set through
`el.style` and then removed with `removeAttribute('style')` without being
read first is still serialised as `style=""` by Chrome - the attribute is
written from the style lazily. RESTORE_PAGE reads each attribute before
putting it back; the suites compare `outerHTML` before and after, character
for character.

**A busy page poisons the next link on the same site.** The first busy
fixture started its endless loop 1.5 s in: the capture finished before it,
and the NEXT link, same site, same renderer, hung its navigation for 25 s.
The fixture now starts at 0.2 s. Headless Chrome recovered through
about:blank; `Browser.capture` starts a fresh Chrome if the page still does
not answer.

**The ad-blocker box** in the person's Economic Times picture came from the
ad-blocker in their own Chrome. In both of the program's browsers ET served
its adverts and showed no such text. The capture removes such walls anyway.

**Tests.** test_capturequality.py (new): 25 checks with no browser (kinds,
wording, imports, `paint_margin`, the wire's limits against a fake server),
then 18 capture fixtures in capture_fixtures/ on a loopback server with a
slow-picture route, checked by pixel colour in headless Chrome, and the same
fixtures in the browser inside the program in a child process on the real
window platform; the script checks one by one (CLEAR_CLUTTER idempotent,
kept rects inside the clip, RESTORE_PAGE complete, ET margin 11); the ruler;
capture_current leaving the page identical; busy pages. The verdicts live in
capture_checks.py, shared with test_embedded.py section 6 (scrollbars off,
820 inside, five fixtures through Catcher, a busy page then the next link,
renew, capture_current on the browser window's own page). test_webclip
section 8 now also pins in-window capture and kind "gone"; test_fromchrome
section 5 uses the capture's real wording. Fixture timings: 1.4-4.8 s
headless, 1.5-5.0 s embedded; the 4 s and 4.5 s late pictures are the slow
ones.

### What the review of the capture found, and what changed (2.0.32)

Every finding was reproduced before it was fixed, against the 2.0.31 code on
the same page where that made sense (review probes `probe_find.py`,
`probe_wire.py`, `break/probe_*.py`).

  * **A negated advert name hid the lead photo.** `<div class="leadMedia
    noAds">` and `<figure class="story-image ad-free">` split into the token
    "ads"/"ad" and were hidden: green 0 px, where 2.0.31 kept the whole
    photo. An advert word right after no/non/without/zero or right before
    free/less/none no longer counts. And CLEAR_CLUTTER now finds the lead
    picture the way FIND_BLOCK will (first figure/img/picture/video under
    the largest headline, in its column, over 25,000 px2) and never hides,
    by name or label, anything holding it - nor climbs a label or an advert
    frame up into it. Only a photo's shape counts: at least half the
    headline's width and at least 0.3 as tall as wide, so a 728x90 or
    970x250 banner, or a 300x250 box, is still an advert. Pinned:
    `falsepositives.html` (noAds, ad-free) and `leadguard.html`
    ("story-ad-wrap", not negated, kept; the real `ad-slot-box` still goes).
  * **An ad-blocker wall with its own `<h1>` was captured instead of the
    story.** The headline guard ran before the wall test, so the dialog
    "held the headline" and was let flow; FIND_BLOCK then took its bigger
    h1. Result: a 707x88 purple cutting titled "Ad Blocker Detected".
    Walls are now told apart first: a pinned or dialog element holding an
    h1 is a wall if it has wall words ("ad blocker detected", "turn off your
    ad blocker"...) or wall names over a fifth of the view, and holds no
    story text; a dialog is also a wall when it simply has no story text. The
    headlines are counted without those, and FIND_BLOCK prefers an h1 that
    is not inside a dialog. A page wrapper pinned to stop scrolling holds
    story text, so it is still let flow, never hidden (`wall.html` passes
    unchanged). Pinned: `wallh1.html`.
  * **A bare `<article>` was a post on every site.** The rule came from
    signed-out X; on a news page with no long h1 (an h2 headline, or a Hindi
    headline of fifteen letters or fewer) a strip of teaser `<article>`s
    made the cutting a 272x182 teaser. A bare article now counts only on a
    social site, behind a sign-in wall, or as the page's own column (at
    least half the layout width, not inside nav/header/footer/aside -
    signed-out X's post is 600 of 820). Such pages are "page" again, as in
    2.0.31. Pinned: `noh1teasers.html`, `noh1article.html` (the teasers in a
    plain div).
  * **Redirects.** Lowering the first pause from 2.5 s to 1.0 s lost a link
    whose page sends itself on at 1.5 s: refused at 1.2 s as "nothing looked
    like a story", where 2.0.31 captured it. A refusal on a document that
    opened under 3 s ago now waits until it is 3 s old (1.5 s at least) and
    runs again if `location.href` or `performance.timeOrigin` changed, for up
    to three pages. Two quick hops (each at 1.6 s, while a 3 s picture loads)
    used to show the browser's own "Inspected target navigated or closed"
    with an empty kind; `_evaluate` now reruns a script every 0.7 s while its
    world keeps being destroyed, for 8 s, then refuses with MOVED_ON, kind
    "not-a-story". Measured: 1.5 s script redirect 3.5 s, two hops 4.5 s
    (landing page, not the "nearly there" page 2.0.31 captured), a 1 s meta
    refresh 2.2 s. Pinned: `redirect.html`, `redirect2hop.html`; section 0
    drives `_evaluate` with a stand-in page.
  * **A trickling frame stretched a call.** The limit was set once per
    message and every `recv` got it afresh: `call(seconds=1.0)` against a
    server sending a byte every 0.15 s came back after 9.6 s. The deadline
    now goes down to `_fill`, which sets what is left before every read;
    1.0 s, and the half-read frame is still kept for the next call. Pinned in
    0b.
  * **"Stopped answering" sent people back to the browser that stopped.**
    STOPPED is raised by both engines; it now says "Try it again, or take it
    from your Chrome."
  * **A page that hangs after its own capture.** fx_latehang captures in
    under 2 s and spins at 12 s, the HT pattern in Qt. In the browser inside
    the program the next list's `attach` sat 30 s on `Page.enable` and every
    link failed, and every list after, with the target id never changing.
    `attach` now keeps its enable calls to a limit (5 s at a list's start),
    and `Catcher._first_wire` recovers a parked page that does not answer
    before the first link: `webshot.revive` (a bare wire, which needs nothing
    of the stuck page, sends it to about:blank and waits 3 s for an answer),
    else `Host.renew`. For this fixture about:blank did not unstick Qt's page
    and renew did: next list of two links 12.0 s, the list after 1.9 s. In
    headless Chrome the next, innocent link failed after 25.1 s and was
    blamed; `capture_over` now first asks the page the last link left behind
    to answer within 2 s, sends it to about:blank if not, and if that fails
    raises `ShotError(LEFT_STUCK, kind="stopped", unopened=True)`, on which
    `Browser.capture` starts a fresh Chrome and tries the link once more
    (Catcher likewise, on the recovered page). Measured 7.0 s, captured.
    Pinned: test_capturequality 6b, test_embedded section 6.
  * **The padding sliced the next line.** The bottom snapped to a whole line
    plus 4 px, then 16 px of padding: shown = 20 - the gap to the next line,
    so body text with lines under 20 px apart came out with the top of the
    next line (fx_lines2 13 of 17 px, Times of India 13 of 21, Dainik
    Bhaskar 4 of 24). FIND_BLOCK now walks the text in the padding: a line
    starting in the padding under the cutting ends it 1 px above that line,
    a line ending in the padding above (a kicker over the headline) starts
    it 1 px below, and the rest comes back as `margin.bottom` / `margin.top`
    for `paint_margin` to paint in the page's colour. Pinned: `lines.html`
    (red text; no red in the first or last 24 device rows).
  * **`Host.renew()` and the hung renderer: the measurement was the trap.**
    The review saw the old target still listed and its renderer using a full
    core 12 s after renew. Measured again with every step on a timer
    (fixC/probe_renew_release.py): plain `deleteLater`, lifecycle Discarded
    then deleteLater, and `shiboken6.delete` all released the renderer (0.0
    cores, target gone). The review's probe pumped processEvents from inside
    a timer callback, and a deferred delete does not run there; the same is
    true of the suite's nested waits, or any loop turned inside another.
    `setLifecycleState(Discarded)` is refused silently (the state stays
    Active) and is not used. renew() now deletes the old page at once, which
    releases it under a nested loop too (the review's probe re-run: 0.0
    cores, not listed). Pinned in test_embedded section 6 with a page still
    hung when renew is called, inside the suite's own nested wait.

**Live, after these changes (14 September 2026, both engines,
design/C/live_final.py, out/final_<site>_<engine>.png):** India Today 812x862
(photo, caption, first paragraph), Economic Times 926x709 (centred headline
whole, rail blanked, left margin 11), Hindustan Times 808x852 (left margin
16), NDTV 822x755, the public X post 598x626 as a post, Times of India
830x757 with 14 px painted back under the last whole line, Dainik Bhaskar
399x644 with 5. The two engines gave the same sizes. The cut-line probe found
no line through the bottom edge on TOI, Bhaskar or India Today. It flagged a
"weather" line at TOI's top, but that was measured on the page after the shot
- a strip that appears once the page is scrolled - and the picture's top edge
shows no such text. **Trap in the fixture:** the first `lines.html` paragraph
ended before the 620 px run, so its bottom check passed without a line under
the cutting at all; lengthened, it fails with the edge rule switched off
(7,930 red pixels in the last 24 rows, 2,366 in the first) and passes with it
(fixC/probe_lines_check.py).

### What the second and third reviews of the capture found (2.0.32)

Each was reproduced first with the reviewers' probes (review/C/r2/probe_r2.py,
probe_alert_next.py, probe_emb_alert.py; r3/probe_asis_heights.py), and each
fixture is now a capture fixture run in both engines.

  * **A headline laid over its photo was hidden as a wall.** CLEAR_CLUTTER
    takes an absolute layer with z-index 100 or more as pinned, and a pinned
    thing holding an h1 as a wall if it has a wall's name or words. A feature
    headline in `div.hero-overlay` ("overlay") and one reading "Railway Board
    to allow ads on the outside of Vande Bharat coaches" ("allow ads") were
    both hidden, and the capture came out as a page with no headline. A
    wall's name now counts only for a fixed element or a dialog. A wall's
    words are read with the headline's own words taken out, unless the
    headline is at least half wall words: "Ad Blocker Detected on this site"
    (wallh1.html) is still a wall. FIND_BLOCK and the lead-picture guard also
    take a photo that the headline sits over as the lead picture, and the
    cutting starts at the photo's top: 2.0.31 printed only the strip of photo
    behind the headline. overlayhero and allowads now come out as stories,
    852x684 and 852x624, with the photo.
  * **"ad" inside "lead".** FIND_BLOCK's STOP regex was a substring match, so
    `<p class="lead">` ended the cutting at the photo's caption; "subhead",
    "header", "shadow", "download" and "Moradabad" would have done the same.
    2.0.31 had the same regex, but its text-line bottom reached past the stop;
    the whole-line snap made the stop real. STOP and JUNK now read whole
    class and id words, as CLEAR_CLUTTER does, with the same negation
    ("noAds"). STOP still takes a word beginning with one of its longer words
    (videos, recommended, embedded, widgets). leadpara went from 792x562 with
    no paragraph to 792x751 with them. The fixture also has h2.subhead,
    div.shadow-box and p.download-note after the lead.
  * **A page's own alert box.** Headless Chrome stops a page's scripts until a
    dialog is answered, so the alert link failed as stopped after 17 s. Qt's
    default was worse: an application-modal QMessageBox at (0, 31) on the
    screen, not in the parked window. It blocked the whole program, and while
    it stayed open the next link failed too. `_Wire.wait` now answers
    `Page.javascriptDialogOpening` the moment it arrives
    (`Page.handleJavaScriptDialog`, accept false; a beforeunload box accept
    true, or the next navigation would be held). The parked page is
    `embedded.QuietPage`, whose javaScriptAlert, Confirm and Prompt answer no
    and show nothing. capture_current turns the wire's answering off for its
    run: a box on the page somebody is reading is theirs to answer.
    alertwall.html (alert, then confirm, then prompt) was captured in 1.4 s
    headless. Pinned in both engines with a watcher that records and closes any
    visible QDialog; test_embedded runs it through Catcher followed by an
    ordinary link, and test_capturequality 0c drives the answering against a
    fake page.
  * **Margins painted black.** Chrome returns a colour written as
    oklch()/lab()/color() in that form from getComputedStyle, and paint_margin
    read every number in the string as RGB: oklch(0.97 0 0) came out as
    (1, 0, 0). FIND_BLOCK now draws the colour on a 1x1 canvas and reads the
    pixel back as rgb(); paint_margin reads only rgb()/rgba() and falls back
    to white. oklch.html's margins now come out rgb(245, 245, 245).
  * **The bottom margin in the page's colour under a white card.** The top
    and bottom strips now take the colour behind what the cutting starts and
    ends at, from the nearest ancestor with a background: the headline (or
    the photo under it) at the top, the last kept line or the photo at the
    bottom. The sides keep the page colour, so a photo flush with the edge is
    not stretched. FIND_BLOCK returns `edges: {top, bottom}`. Pinned:
    cardonpage.html.
  * **A story or post the page draws after about 1.2 s.** With the 1.0 s
    settle, a story put in at 1.8 s came out as its grey Loading box (kind
    page), where 2.0.31's 2.5 s wait had it. On a social host, a post drawn at
    1.2 s or later was refused as needing a sign-in (probe_xslow, x.com
    answered through DevTools Fetch). Live X drew its post 0.68-0.83 s in,
    even on an emulated slow line, so this was a thin margin rather than a
    live failure. `_moved_on` is now `_look_again`. A 'page' result, a
    'sign-in' refusal or a 'not-a-story' on a document under 3 s old waits
    until the document is 3 s old (1.5 s at least), once per document, and
    PREPARE and FIND run again. A page that really is empty or walled pays
    that wait once. spa.html now captures in 3.5 s. Pinned: spa.html, and
    latepost.html (a post drawn at 1.8 s under a log-in button, so the
    sign-in path).
  * **capture_current followed the window to another page.** `_evaluate`
    reruns a script whose world was destroyed, which is right for a redirect.
    On the page somebody is reading, a click during the capture pictured the
    next page under the first page's link. capture_current now sets
    `wire.stay`, so a destroyed world is `ShotError(PAGE_CHANGED,
    kind="changed")` at once. It also compares `performance.timeOrigin`
    before and after, because a page opened between two scripts runs the
    rest of them without complaint. The restore does not scroll the new
    page. Only the document is compared, not location.href: sites that
    rewrite the address as the reader scrolls into the next story
    (history.replaceState) would refuse every capture. A route change inside
    the same document (pushState, as on X) is not caught. Pinned:
    test_capturequality 4b, both ways.
  * **A long page cut through its last line.** The 2200 px cap fell wherever
    it fell, and the line-edge walk only looked below the box. A capped
    cutting now ends 1 px above the line the cap falls through, and the rest
    is painted. **Trap in the check:** 8 red pixels are still in the last 24
    device rows - the descenders of the last whole line - so pagecap checks
    the painted strip, and that the lowest red band spans at least 22 device
    rows.
  * **Qt's scrollbar gone after capture_current (third review).**
    test_embedded failed 84/1 while the suite still exited 0, so the battery
    listed it as ok. Measured on the browser window's own page at 1040x420
    (fixC2/probe_bar.py, probe_bar2.py), on both the ruler and asis pages:
    - An override taller than the window, then cleared, keeps the bar. So
      does the same override with `dontSetVisibleSize`.
    - The loss needs `Emulation.setScrollbarsHidden`: hidden, overridden
      taller, cleared, then shown gives bar 0 until the next resize.
    - Shown again before the override is cleared keeps 15 px at 0.3, 1 and
      3 s. Never hidden at all also keeps 15.
    The finally now sends setScrollbarsHidden(false) first. The hide does
    nothing on Qt's page but still hides headless Chrome's scrollbar. Also
    measured: a clip taken inside a window-sized view paints only the window
    (255 beyond it), while `dontSetVisibleSize` paints beyond the window
    without resizing the view - worth knowing if the resize is ever seen.
    Pinned: as_is_checks (the order); test_capturequality's embedded child
    pictures a 1040x420 browser window's own page and reads the bar at 0.3,
    1 and 3 s; test_embedded section 6.

**Trap in the leadpara fixture:** with a 400 px photo, the 620 px story run
ended inside the shadow-box paragraph, so "paragraphs after the subhead" failed
for the length of the run, not for a stop. The photo is 240 px, so the
subhead, shadow box and download note all fall inside the run: brown now
reaches 371 CSS px under the photo. A stop at the subhead would end it at about
140.

**Live, after these changes (14 September 2026, both engines,
design/C/live_final.py, out/final_<site>_<engine>.png, every PNG looked at):**
India Today 812x862, Economic Times 926x709 (left margin 11, rail blanked),
Hindustan Times 808x852, NDTV 822x755, the X post 598x626, Times of India
820x757 headless and 830x757 embedded, Dainik Bhaskar 399x644. These are the
same sizes as before this round. NDTV's and Bhaskar's dark pages have their
painted edges in their own dark colour. Suites: test_capturequality 424/0,
test_embedded 89/0 (was 84/1), test_webclip 52/0, test_weblinks 95/0,
test_fromchrome 35/0, test_carryforward 48/0.

### What the fourth review of the capture found (2.0.32)

Both reproduced first with the reviewer's probe (review/C/r4b/probe_r4.py,
headless, comparing the working tree with the 2.0.31 path). Every fixture is
now a capture fixture, run in both engines.

  * **A pinned wall with a heading of its own became the cutting.** This was a
    regression from 2.0.31, in both engines. 2.0.31 hid every fixed and sticky
    element before measuring. This round's CLEAR_CLUTTER counted a pinned box
    holding an h1 as a wall only when its text matched one of four WALL_TEXT
    phrases or it had a wall's class name. Otherwise it "rescued" the box to
    position:static, and its bigger h1 won FIND_BLOCK. The wallh1 fixture
    said "Ad Blocker Detected", the one wording that matched, so it passed.
    Measured before the fix, each a story plus a position:fixed box with a
    44 px h1, no role=dialog and no wall class:
    - "It looks like you're using an ad blocker" (abswall): 671x144, all purple
    - the Hindi "ऐसा लगता है कि आप ऐड ब्लॉकर का इस्तेमाल कर रहे हैं" (wallhindi): 639x144
    - "Register free to continue reading this story" (paywallh1): 721x144

    2.0.31 captured all three as the story. The wall is now known by what it
    is. A fixed box holding a heading and no story text (under 300 characters,
    or mostly links) is a wall, whatever it says: hidden, and its h1 left out
    of the headlines. Only a pinned box WITH story text is set back in the
    page, which is wall.html's page wrapper. A sticky box is a wall on the
    same terms only when the page has a headline somewhere else, because a
    story's own heading block can be sticky (stickyhead.html keeps its only
    headline). A box whose headings are all mostly wall words is a wall however
    long it runs. longwall.html has "Ad Blocker Detected" over 400 characters
    of instructions, which counted as story text and was rescued before.
    WALL_TEXT is wider too: "you're using an ad blocker" with its lead-in,
    "detected an ad blocker", "register/subscribe to continue reading", and
    the Hindi ऐड/एड ब्लॉकर. It is built with new RegExp so it can run over
    several lines. FIND_BLOCK ranks an h1 inside a fixed or sticky box with no
    story text after every other h1, so a page nothing has cleared chooses the
    same headline. After the fix: abswall 792x627, wallhindi 792x639,
    paywallh1 792x627, each with the photo and no purple.
    **Trap:** the ranking is only after the dialog rule. An h1 in a dialog
    still ranks last of all.
  * **A wallpaper advert behind the story was taken as its lead photo.**
    skinad.html has a 1920x1200 img in div#div-gpt-ad-skin at the top of the
    page, behind a 760 px story. The headline lies over it, so the "under" rule
    (a photo with the headline laid over it) took it as the lead. The lead
    guard then shielded its wrapper from being hidden. FIND_BLOCK kept it, and
    _cut widened the window to 1370 to take it in: 1952x1232, 5.5 million
    yellow pixels, with a 291 px painted margin. 2.0.31 had the advert in its
    cutting too (1370 wide), but only as background. Now:
    - a picture counts as "under" only when it lies within the page
      (left >= 0, right <= the window, allowing for a scrollbar) and is no
      wider than 1.5 times the headline's column, in both scripts. The column
      is the nearest box round the headline holding 200 more characters than
      the headline.
    - the lead guard never takes a picture inside an advert network's wrapper
      (a NETWORK name, such as gptad, adslot or adcontainer) that holds no
      story text and no headline. "story-ad-wrap" is a plain name and stays
      guarded (leadguard.html). Hindustan Times' "taboola-readmore" holds the
      story, so it stays guarded too.

    skinad now comes out 792 wide with no yellow, and its wrapper is hidden
    as an advert name. The reviewer's vhhero, vhlead and floatline fixtures
    are unchanged: 852x1852, 792x1562, 792x835.
    **Trap in the fixture:** skinad's paragraphs were under 200 characters,
    so no body was found and the cutting ended at the caption. 2.0.31 showed
    text only because the advert stretched its cutting. The fixture's first
    paragraph is now long enough to be a story's.

**Live, after these changes (14 September 2026, both engines, live_final.py,
every PNG looked at):** India Today 812x862, Economic Times 926x709 (left
margin 11, rail blanked, player still), Hindustan Times 808x852, NDTV 822x755,
the X post 598x626, Times of India 820x757 headless and 830x757 embedded,
Dainik Bhaskar 399x644. All are the same as before this round, so the wall
rule hides nothing any of these sites needs. Suites: test_capturequality
516/0 (294 headless plus 222 in the embedded child; the six new fixtures pass
in both engines), test_embedded 89/0, test_webclip 52/0, test_weblinks 95/0,
test_fromchrome 35/0, test_carryforward 48/0.

## Choosing how to capture, the link tour and saved sign-ins (2.0.32)

The asks: an automatic Enter after a pasted or dragged link; the "browser
inside the app" and "take from my Chrome" buttons selectable, with right-click
options, and the whole way of taking links rethought; a browser that shows the
next link; and a ☰ menu showing the stored sign-ins, with a way to remove
them.

**The paste box (`webclip.LinkBox`).** A QPlainTextEdit whose
`canInsertFromMimeData`/`insertFromMimeData` are overridden. The design probe
(design/B/probe_linkbox.py, offscreen) measured that one Python override
catches all four ways text arrives: `paste()`, a Ctrl+V key event, the
standard context menu's Paste, and a drop, including a drop that carries only
`setUrls` and no text. `put_links` wraps the insertion in
beginEditBlock/endEditBlock, so one undo takes it back. The rule is:

  * mid-line, move to the end of the line first. Inserting at the cursor cut
    an address into "https" and "://a…" in the probe.
  * a newline before the text if the line already has words on it.
  * after the text, a newline if words follow or the box ends there;
    otherwise step to the next line.
  * leading and trailing blank lines of the paste are dropped.

The result is never a blank line. Words with no link in them, and drags inside
the box, go to the base class. `setPlainText` is overridden only to emit
`replaced`. It is not virtual, so the override is seen only by Python callers
(start_over and the suites), which is exactly who should clear the person's
own ticks.

**States are kept by address, not by row.** `LinksDialog.states`
(url.lower() -> LinkState: new/queued/capturing/retrying/done/failed/walled/
skipped, with clip_id and how) and `ticks` (the person's own tick, kept only
when they changed it) survive `_reread`, which still rebuilds the rows on
every keystroke. Before 2.0.32 the ✓/✕ marks were written on the items and
lost on the next paste; the ticks came back on, so a second Capture captured
the done links again.

Undo is noticed by `pool_for(clip_id) is None`. The check runs 150 ms after
the undo stacks' `indexChanged` (a single-shot timer, per the debouncing
note), on show and on activation. A redo brings the ✓ back, because the
clip_id is kept on a state that went back to "new".

`open_links` adds words to the list when the window is visible
(`put_links(at_end=True)`) and starts over when it is hidden. test_webclip 7b,
where a paste after closing lists exactly one link, keeps passing.

**Two ways and one Capture button.** An exclusive QButtonGroup of two
checkable buttons ("Browser inside the app", and "My Chrome" on win32 only).
The choice is kept in export.json as `links_capture_with`, like the tidy
switch. My Chrome's trim tick is `chrome_trim_after`, and the browser window
keeps `browser_capture_then_next` and `browser_panel_open`.

Without the engine (the offscreen suites, or a build without QtWebEngine),
"Browser inside the app" captures with the hidden Chrome on the program's
folder, and its menu offers sign-in windows through `webshot.sign_in`.

Menus are built fresh by `menu_for(name)` and `row_menu_for(item)`, and every
QAction carries its key as data. Suites trigger an action by key and never
show the menu. When a menu is shown it goes through `popup()`: test_webclip
pins that none of webclip, embedded or sitepanel contains `.exec(`.

**Walls.** `ShotError.kind == "sign-in"` (step C) marks a row walled. A
failure with no kind falls back to `\bsign(?:ed)?[- ]?in\b`, so "design" does
not match. The count line turns into rich text with `<a href='sign-in'>` and
`<a href='chrome'>`.

A link the parked page failed with kind "stopped" is queued, and after the
background run it is tried once more in headless Chrome (`_start_run(retry,
"retry")`), when `find_browser()` finds one. `embedded.Catcher` now emits
`troubled(url, kind)` before each failure's `caught`, because `caught` keeps
its three arguments for test_embedded section 3.

**Links dropped anywhere.** `MainWindow._links_in(mime)` answers the words of
a drop or paste that carries no files, no picture bytes and at least one link
that is not a picture address: not .jpg/.png/…, not `format=jpg`, and not
blob: or data:. `accept_payload` sends those words to the links window before
its "Nothing to add" box. That one change covers the window, ClipList.dropEvent
and a sentiment column (accept_payload_into). A sentiment column is not
remembered for a link: the flash says it went to the links window.

**Trap (the design missed it, the critic caught it):** a link dragged from
real Chrome is claimed by `win_drop`, not left for Qt. Chrome offers it as
FileGroupDescriptorW/FileContents for "<title>.url", plus
UniformResourceLocatorW and text. `_WindowDropTarget._claim` takes any file
stream, `_deliver` found no picture, and `on_empty` opened "Nothing came with
that drop" before Qt saw the drop.

`win_drop.link_words` now reads the address from UniformResourceLocatorW,
UniformResourceLocator, CF_UNICODETEXT or the shortcut's `URL=` line. The
shortcut is read even when it is under 64 bytes, which extract_files drops.
When there is an address, `_deliver` returns False with no box, and the window
target forwards DragEnter+Drop to Qt, whose dropEvent takes the link route.
The panel-only fallback target has no Qt behind it, so it calls `on_link`.

test_window_drop section 7 pins this with a fake data object. **Still to do by
hand once:** drag a link from the address bar of real Chrome onto the window
and see the links window open with no box.

**The cookie store, measured (design/B/probe_jar*.txt, QtWebEngine 6.11.2):**

  * `loadAllCookies` never emits anything, before or after a page exists.
  * `storage/Cookies` is locked while the engine runs (PermissionError at 2 s
    and at 34 s) and readable with sqlite before it starts.
  * `deleteCookie(cookie)` with no origin removes nothing.
    `deleteCookie(cookie, QUrl("https://domain/path"))`, even with an empty
    value, removes the saved cookie and fires cookieRemoved.
  * The store does nothing until a page exists.

So `Host.__init__` runs in this order:

  1. The wipe mark.
  2. `sitedata.read_cookie_file(storage/Cookies)` into a `Jar`.
  3. The profile.
  4. The page and its settings.
  5. `cookieAdded`/`cookieRemoved` connected to the jar.

`jarChanged` is debounced by 250 ms. A cookie that expires during a session
is never announced, so it can stay in the panel until the next start. The
jar's `facts()` drops anything past its date, so it is never counted as a
sign-in.

**Signed in is decided by the cookie's name** (`sitedata.SIGN_IN_COOKIES`):
auth_token for X, c_user for Facebook, sessionid for Instagram and Threads,
li_at for LinkedIn, LOGIN_INFO for YouTube, and SID or __Secure-1PSID for
Google. A setHtml page with base https://x.com got guest_id,
guest_id_ads, personalization_id and __cf_bm without any sign-in, and the old
any-cookie rule said "Signed in: x.com". `webshot.signed_in_sites` uses the
same rule on the program's Chrome.

`sitedata` has no value field anywhere. CookieFact is name, domain, path and
dates. The query names its columns, and the file is copied to a temp folder
before it is read. test_sitedata puts a sentinel in value and encrypted_value
and checks it never comes back. test_embedded section 8 checks that no
widget text in the panel holds it.

**Removing things.** `Host.sign_out(site)` calls deleteCookie with
`origin_for(fact)` for each of that site's cookies. After 1.5 s it checks the
jar for leftovers (`signOutLeft`), so a cookie with an odd domain or path is
reported rather than silently kept.

"Remove everything" does these now: deleteAllCookies, clearHttpCache,
clearAllVisitedLinks, and permission.reset(). Local Storage, IndexedDB and the
rest cannot be cleared per site while the engine holds them, so it writes
`webprofile/wipe-on-start` and they are deleted before the next Host is made.
The panel says so.

The program's own Chrome (`webshot.chrome_cookie_file()`, always under
`browser_folder()`) has its rows deleted with sqlite only when no Chrome this
program started is running and the file is not held open (`sitedata.in_use`:
Chromium opens it for itself alone). Otherwise
`browser/sign-out-on-start.json` is carried out by `apply_sign_out_mark()` in
`Browser.start` and `sign_in`, before Chrome opens. The person's everyday
Chrome is never read.

**The browser window.**

  * Capture this page uses `webshot.capture_current` (step C) over the visible
    page's own `devToolsId()`, through `embedded.Catcher(as_is=True)`, which
    attaches with `exact=True` so it can never picture the parked page
    instead.
  * The clipping is filed under the tour's link when `on_tour_link()` holds:
    no LinkClicked/FormSubmitted main-frame navigation since the tour opened
    it (`TourPage.acceptNavigationRequest`), no typed or dropped address, the
    same site, and the page is the link as sent or where its redirects landed.
  * Pop-ups (InNewDialog, InNewWindow) open in a `PopupWindow` on the same
    profile through `request.openIn`. A tab request loads in the same view.
  * `permissionRequested` is denied on both pages. A denied prompt is stored
    and listed in the panel with Forget (test_embedded section 8, through
    geolocation).

**The watch on a page that stops responding.** Every 2 s the window asks the
page to run "1". If 5 s pass unanswered, it shows "This page stopped
responding" with Reload and Skip to the next link. This never happens in the
first 6 s after loadStarted.

`loadStarted` voids the pending question, because a cross-site navigation
swaps the renderer and an old question may never be answered.
`renderProcessTerminated` shows the note too. Reload and Skip first put a
fresh TourPage in the view and delete the stuck one with shiboken6.delete, as
Host.renew does: navigating a page hung in a script is not dependable.

**Trap in the suites:** `QMessageBox.information(...)` is a static C++ call.
Patching `QMessageBox.exec` does not stub it, and an offscreen suite hangs on
it. test_webclip section 10 patches `information` for the picture-link drop,
and test_embedded now answers `QMessageBox.question` "Yes" and counts it
apart from boxes that should never open.

**Trap: two windowed suites at once.** test_real_drop failed "an editor is
open" while a real-platform probe window was on the screen beside it: the
probe took the focus, and the rename box did not stay open. Run alone it
passes 15/15. Never run two suites or probes that show real windows at the
same time.

**Suites after this step (14 September 2026):** test_sitedata 47/0 (new),
test_linkbox 30/0 (new), test_webclip 100/0 (sections 9 to 12b new),
test_fromchrome 43/0 (sections 4 and 5 rewritten for the two ways, 6 new),
test_weblinks 95/0, test_carryforward 48/0, test_capturequality 516/0 (222 in
the embedded child), test_collect 82/0, test_dropflow 17/0, test_dropscroll
21/0, test_four 27/0, test_tidy 23/0, test_batch 27/0, test_newspads 137/0,
test_real_drop 15/0, test_window_drop 33/0 (section 7 new), test_embedded
139/0 (sections 4 and 5 rewritten; 7, 8 and 9 new).

**Open question: busy.html did not hang the browser window inside
test_embedded.** In a fresh window the watch fires at 7 to 9 s. Two probes
copied the suite's order, and every step of section 8 was left out in turn
(stepB/probe_watch*.py); it still fired. Inside the suite, runs 1 to 3 never
fired. Counted there, it was 22 watch ticks, 22 questions and 22 answers: the
watch worked, and the page kept answering. The fixture's loop starts from a
200 ms timer, but a timer check in the same place passed in run 4, so the
window's timers do run there. Nothing in webshot or blockjs pauses a page's
time or freezes it (grep: device metrics, scrollbars, user agent only). The
cause is not found. Section 9 now also runs `for (;;) {}` into the page
straight away, which hangs it whatever the timers do, and the watch noticed
it at 6.9 s. The timer check stays, because a browser window whose timers
stopped would never load a page's late pictures.

### What the review of step B found, and what changed (2.0.32)

Ten findings, two must-fix. Every one was reproduced first, with the review's
own probes (review/B), before anything was changed. The real-platform probes
were run from copies that park their windows off the screen (fixB/repro,
made by fixB/make_parked.py), because the originals put a browser window over
the person's work and took the keyboard. Before and after are in
fixB/repro/before_*.txt and after_*.txt.

**A tour link that goes on to another host was filed as a new clipping.**
`on_tour_link` compared the site on the screen with the site of the link as
sent before anything else, so youtu.be to youtube.com, fb.watch to
facebook.com and twitter.com to x.com all failed it, both while loading and
after. On the real platform (a 302 from 127.0.0.1 to localhost standing in)
Capture this page made a clipping titled from the page, did not tick the row
and did not move on.

Now: while the tour's load is under way and the person has done nothing of
their own, the page is the link; after it, the page is the link as sent or
where it landed. `_url_changed` records the landing as the redirects happen.
Removing the site test widened one gap: a Back pressed while the link was
still loading would have been filed under it. So `TourPage` now counts
BackForward as the person's own going, beside LinkClicked and FormSubmitted.
test_embedded 7b pins it with `capture_checks`' new `/redirect/<name>` route.

**The ☰ panel was quadratic and ran everywhere.** `_fill_tree` called
`jar.facts_for(site)` per site, each a pass over the whole jar. Every
`jarChanged` rebuilt every panel, hidden or not, and re-read the program's
Chrome's cookie file. `Host._changed` ran `signed_in_sites` over the whole jar
per cookie. Measured by the review with a synthetic jar, before:

  * 300 sites / 3,001 cookies: rebuild 1,122 ms (1,030 ms in my rerun);
  * 100 ordinary cookies arriving: 337 ms of `signed_in_sites`.

After, same jar, offscreen (fixB/repro/after_bcd.txt, test_sitepanel):

  * shown and filled: 22-24 ms; a cookie change while shown: 11 ms;
  * a cookie change while hidden: 0.02 ms (nothing is done);
  * 100 ordinary cookies arriving: 0.2 ms.

The changes: `Jar.by_site()` groups in one pass and `summary(grouped=)`
reuses it; `site_of` is `lru_cache`d; a site's cookie rows are made when it
is opened (`ShowIndicator` plus `itemExpanded`); the panel fills on
`showEvent` and on `jarChanged` only while visible; Chrome's file and the
permissions are read only on show; the Signed in rows are remade only when
who is signed in changed; `Host._changed` works out sign-ins again only for a
cookie `sitedata.is_sign_in` says is one.

**A cookie change cleared the chosen site** and switched Remove off under the
pointer. `_fill_tree` now puts back the chosen site (or cookie row), the
opened sites and the scroll position.

**Trap: a lambda connected to a long-lived host.** The panel connected
`host.cacheCleared` to a lambda. Bound methods of a QObject are disconnected
when it is destroyed; a lambda is not, and would be called on a deleted
panel. All three connections are bound methods now (test_sitepanel 4).

**Closed browser windows stayed alive.** `open_browser` made a new
BrowserWindow each time and `_inside_closed` only dropped the reference: after
three opens there were three windows, each with its page loaded, and five
panels rebuilding on one `jarChanged` (R4). Now the links window keeps one.
Closing it puts it away: the watch stops, a capture is stopped, pop-ups close,
and `_renew_page` gives it a blank page and deletes the old one and its
renderer. Opening it again tours as a new window would.

**Trap: Esc and QDialog.** `QDialog.reject()` hides without `closeEvent`, so
Esc left the watch running (R3). But `QDialog::closeEvent` itself calls
`reject()`. An override of `reject` that simply calls `close()` would come
back into `close()` while it is already closing: Qt returns at once, reject
never hides, and the close event is ignored. Hence the `_closing` flag:
`reject` calls `close()` unless closeEvent is running, and then the real
reject. Esc that a page did not use comes back up through the view's parent,
the splitter, whose event filter eats it: Esc on the page or in the panel
never closes the window. Esc in the address bar still does. The sign-in
pop-up ignores Esc (hidden by reject, it was never deleted).

**"Saved sign-ins and site data…" navigated away** from the page somebody was
on, because `open_browser` ran `set_tour(open_now=True)` for any call without
a login. Now a panel-only call over an open page only shows the panel; over a
window put away blank it tours, as a new window does.

**The panel was remembered as open when opened that way.** `show_panel`'s
`setChecked` fired `toggled`, and `_panel_toggled` always remembers. The
button is now set with its signals blocked.

**The panel's Sign in skipped the waiting link.** It went through
`_open_typed` (left_tour, no pending_login), so Next opened the link after
it, and the walled note's "then Capture again" would have taken the sign-in
page. It goes through `open_login` now, and the note says to press Next › to
come back to the post.

**A link pasted on a label line took the label.** With the cursor in a line
of words with no link, and that line's link below, the pasted link went
between them, and `links.find` gave it the sender's words. `put_links` now
puts it after the link those words name (`_link_line_below`). Words at the
end of the box, waiting for a link, still go to the next one.

**Trap: `\b(?:https?://)` matches inside "blob:https://".** A WhatsApp Web
picture drag that brought only its blob: address was read as a link: the
panel-only target handed it on and nothing happened; the window target gave it
back to Qt without the advice to copy the image. `win_drop.link_words` now asks
`links.story_links`, which takes out blob:, data: and filesystem: addresses and
picture addresses (the rule moved from MainWindow to `links.PICTURE_ADDRESS`).
`links.find` had refused the WhatsApp blob only because web.whatsapp.com is
not a story; a blob: of any other site was a link to it until now.
`_native_link_dropped` gives the advice when no story link is left.

**The program's Chrome, while open, "kept nothing".** Chromium holds its
cookie file for itself alone, so a read got [] (probe_chrome_locked.py).
`webshot.chrome_kept()` answers the lines and whether that Chrome is open,
keeping the last lines read in this session (names, counts, dates) for while
it is. The panel and the no-engine menu and note say it is open instead of
"It keeps nothing" or "nowhere yet". A sign-out that has to wait takes the
site out of the kept lines.

**Trap in the suites: a label added to a shown layout is shown on the next
turn of the event loop,** and one taken out is deleted then. A check of
`isVisibleTo` straight after `rebuild()` saw the old labels. And the first
widget a process shows pays for its style and fonts once: 340 ms, which
test_sitepanel now pays on a small panel before it times anything.

**Trap: a page asked for its profile takes the cookie store's handle with it.**
The first run of test_embedded after these fixes stopped in section 8:
`host.store.setCookie` raised "Internal C++ object (QWebEngineCookieStore)
already deleted". A traced copy (fixB/repro/embedded_trace.py) showed the
handle going invalid at one moment: when section 4's browser window was
closed and its page deleted. Section 4 had asked that page `page.profile()`.

The store probe (fixB/repro/probe_store.py) had shown a window shown, a page
renewed, a window put away, `deleteLater`, a panel filled and `Host.renew`
all leaving the handle alive, because none of them asked a page for its
profile. Offscreen, on a profile that keeps nothing on disk
(fixB/repro/probe_profile_owner.py): with no `page.profile()` call,
`shiboken6.delete(page)` leaves the profile and store handles valid; with
one, the profile's handle stays valid and the store's does not. The store
itself lives on, and `profile.cookieStore()` asked again hands out a new,
working handle.

The typesystems carry no parent rule for either type, so this is PySide's own
bookkeeping. Before these fixes nothing deleted section 4's page, so the
suite never met it. The program never asks a page for its profile (grep), so
only the suite set it off. `Host.store` is a property now that asks the
profile each time, so a dead handle cannot be kept.

The `cookieAdded` and `cookieRemoved` connections made on the first handle
keep working after it dies: on the real platform, test_embedded section 8's
cookies still reached the jar after section 4's page was deleted, and the
suite passed 156/0. Offscreen this could not be told either way:
`cookieAdded` never fired there, even before the deletion
(probe_profile_owner2.py).

**Suites after these fixes (14 September 2026), every one after the last
change:**

  * test_sitepanel 31/0 (new, offscreen);
  * test_linkbox 38/0 (section 9 new);
  * test_sitedata 52/0 (the program's Chrome held open);
  * test_webclip 109/0 (12c new);
  * test_window_drop 38/0 (blob: and picture addresses in section 7);
  * test_embedded 156/0 (7b and 9b new; section 8 counts the host's passes
    and opens every site before looking for a value; two checks that pinned
    `dialog.browser is None` now pin a window kept hidden);
  * test_fromchrome 43/0, test_weblinks 95/0, test_carryforward 48/0,
    test_collect 82/0, test_dropflow 17/0, test_dropscroll 21/0,
    test_real_drop 15/0, test_capturequality 516/0.

Windowed suites and probes were run one at a time. The review's
real-platform probes were run again from their parked copies after the fixes,
and all ten findings are gone (fixB/repro/after_real.txt,
after_offscreen.txt, after_bcd.txt, after_windrop_blob.txt,
after_chrome_locked.txt).

### What the second review of step B found, and what changed (2.0.32)

Four findings, one must-fix. Every one was reproduced before anything was
changed. The tour ones were run with the review's own real-platform probes
(review/B/r2_probe_tour.py and r2_probe_tour2.py, which park their windows).
The cookie ones were run with probe_cookie_tempcopy.py and
probe_remove_cookies_hold.py. Before and after are in fixB2/before_*.txt and
fixB2/after_*.txt.

**Deleting the link on the screen filed its page under the next link.**
`update_tour` kept `at` as a place in the list when the current link had
gone, so the link after it took that place, and `on_tour_link` still matched
the page through `_landed`. Measured before (S3, S3b):

  * Capture this page filed asis.html's picture under adstrip.html, with
    adstrip's sender's words, and ticked row 3;
  * Next went to at+1, so the link after the deleted one was never opened.

Now the page is taken off the tour: `left_tour` is set, and `_landed` and
`_tour_load` are cleared. `_gone` holds the place of the link that took its
place, found by `_place()` from the old list: the first later link still
there, else the place after the last earlier one, else past the end. Next
opens `_gone` itself and Previous the link before it. When the deleted link
was the last, nothing comes next. `go_to`, `set_tour` and `_put_away` clear
it. test_embedded 7c.

**Another YouTube or Facebook video was filed under the link that was sent.**
`_same_page` dropped the query, and a `history.pushState` navigation never
reaches `acceptNavigationRequest`. So `watch?v=1` going on to `?v=2` stayed
"the link": the other video got the sender's words and the row was ticked
(S1).

`_same_page` now compares only the keys that name the video or post
(`_STORY_IN_QUERY`), and only when both addresses carry the key:

  * `v` on watch and video.php;
  * `story_fbid` and `id` on story.php and permalink.php;
  * `fbid` on photo and photo.php.

Why not the whole query less a list of tracking keys (the review's first
suggestion): sites rewrite their query after the load, when `_landed` is no
longer followed. A Facebook share link lands with `rdid` and drops it, Times
of India adds `from=mdr`. Any key missing from a tracking list would make the
link that was sent "another page" again, which is the fault round 1 fixed (a
clipping titled from the page, its row unticked). A news site that keys its
story by the query (pib.gov.in's PRID) is not a single-page app: another
story there is a navigation request, which `left_tour` already notes.
test_embedded 7d pins both, with capture_checks' new `/watch` route (the
story page plus a `go2()` that pushStates to `?v=2`).

**Closing the browser during Capture this page froze the program.** Measured
before (S4, S4c): `close()` held the main thread 6.01-6.02 s, then the link
got linkFailed "stopped" and a ✕ in the links window. The page was fine. As
this module's docstring says, the page answers the debugging protocol from
Qt's main thread, which was blocked in `thread.wait(6000)`.

Now `_put_away` never waits:

  * `Catcher.stop(now=True)` cuts the wire with `_Wire.abort()`. That is a
    socket shutdown, never a close from another thread: the owning thread
    closes it, so its number cannot be reused while a read is still in
    progress.
  * `_capturing = None`, so `_caught` drops the answer.
  * The thread is kept until its own `finished`. `_done_capturing` lets it
    go, and puts the blank page in if the window is still put away.

Keeping `self.thread` until then is what makes the drop safe. Capture this
page does nothing while it is set, and the given-up capture's `caught` is
queued before its `finished`, so its answer can never be taken for a new
capture's. `_end_capture` on `aboutToQuit` cuts the capture and waits up to
3 s, because a thread still running at teardown ends the process with a
crash (see "background passes must end themselves").

**Trap: a stop that comes while the wire is still being made.** A stop asked
while `_first_wire` is attaching finds no wire to cut. `Catcher._hold` records
each wire under a lock and cuts it at once if a cut was asked for already.

**The cookie readers left their connection open when the query failed.**
`with sqlite3.connect() as db` commits or rolls back; it never closes. After
a failed query the connection sat in a reference cycle, freed only by
`gc.collect()` (probe_gc_release.out):

  * `read_cookie_file`: TemporaryDirectory's clean-up could not remove the
    copy, so a copy was left in %TEMP%. The probe's was 8,192 bytes with its
    dummy value column. Every run of test_sitedata left a 21-byte one from
    its not-a-database check.
  * `remove_cookies` and `apply_mark`: the program's Chrome's cookie file
    stayed held (WinError 32 on a rename) just before that Chrome is started
    on it.

Now both use `contextlib.closing`, the copy is unlinked in a `finally`, and
the folder has `ignore_cleanup_errors=True`. test_sitedata section 3 runs
these checks with the garbage collector off: no new cm-cookies-* folder, and
the file renames after -1 and after a mark that could not be carried out.
The twelve folders earlier runs and probes had left in TEMP were removed by
hand, after checking what each held: nine 21-byte junk copies, and three
probe copies with dummy values or no rows.

**Left as it was:** LinksDialog.closeEvent's own `wait(6000)` for a list
running over the parked page has the same shape. It was there at 6ba1c60, and
not waiting there changes when a background list's clippings are filed, so
it is left for a change of its own.

**Measured after the fixes** (fixB2/after_tour.txt, after_tour2.txt,
after_tour_copy.txt, check_old_sitedata_out.txt):

  * S1: `?v=2` is "Another page", the capture is a clipping titled from the
    page, and nothing is ticked.
  * S3 and S3b: the page left open is filed as its own clipping, no row is
    ticked, and Next opens adstrip.html, the link after the deleted one.
  * S4 and S4c: `close()` holds the main thread 0.00-0.01 s. Nothing is
    filed, linkFailed is not sent, and the row keeps no ✕.
  * S4b: reopened at once, the next Capture this page took 9.5 s on the
    slow-picture page and ticked the row.
  * The old readers, run beside the fixed ones with the collector off: two
    copies left and the file held; fixed, none left and the file let go.

The original r2_probe_tour.py stops at S4 after the fix, on its own
reference to a QThread the window has let go of. fixB2/make_probe_copy.py
makes a copy that checks `shiboken6.isValid` first, and S4b ran from that.

**Trap in the suite: a headline is not a page.** The first run of 7d failed
four checks, and the code was not at fault. The page before the video link
had the same fixture headline, so a wait for "Rajdhani" in the title passed
before the video page had begun to load, and `go2()` ran on the old page. 7c
and 7d now wait for the link's own address and the end of the tour's load.

**Suites after these fixes (15 September 2026), every one after the last
change:**

  * test_embedded 184/0 (7c, 7d and 7e new; no earlier check changed);
  * test_sitedata 57/0 (section 3: the query-fails checks, with the
    collector off);
  * test_webclip 109/0, test_fromchrome 43/0, test_weblinks 95/0,
    test_linkbox 38/0, test_sitepanel 31/0, test_carryforward 48/0,
    test_collect 82/0;
  * test_dropflow 17/0, test_dropscroll 21/0, test_window_drop 38/0,
    test_real_drop 15/0 (its eight win32com tracebacks are the same as in
    the review's run), test_capturequality 516/0.

Windowed suites and probes were run one at a time.

### What the third review of step B found, and what changed (2.0.32)

Seven findings, all should-fix. Two pairs were one fault seen twice (the tour
and the undo of its link; quitting and closing during a capture), so there
are five changes. Every one was reproduced first with the review's own
probes: review/B/r3/r3_probe_tour.py, r3_probe_quit.py and
r3_probe_linkbox.py, and review/B/r3_probe_menus.py and
r3_probe_teardown.py. Before and after are in fixB3/before_*.txt and
fixB3/after_*.txt.

**Ending the program in the first moment of Capture this page crashed it.**
Measured before (before_quit.txt, before_test_browser_quit.txt):

  * quit straight after the press: `app.exec()` returned 3.01-3.02 s after
    `quit()`, the capture thread was still running, exit 0xC0000409, twice;
  * the main window closed straight after the press, then quit: the same,
    3.00 s and 0xC0000409 (Git Bash reports that code as 127, so the exit
    code is read through Python);
  * quit 0.4 s after the press, and quit with no capture: exit 0.

Why. `_first_wire` attaches: /json/list, the WebSocket handshake,
Page.enable and Runtime.enable. The browser inside the program answers all
of that from Qt's main thread. `_end_capture` blocked that thread in
`thread.wait(3000)`, and `_hold` recorded the wire only after `_first_wire`
had returned, so `stop(now=True)` had nothing to cut. Its docstring's "Cut,
it needs nothing more of this thread" was not true of that moment. When the
wait gave up, deleting the window destroyed a QThread still running.

Now:

  * `webshot.attach` takes `hold`, handed the wire the moment it is
    connected, before Page.enable. `_first_wire` passes `_hold`, and returns
    at once when `_cut` is set before, during or just after attaching,
    closing the wire it made.
  * `_end_capture` waits with the events turning:
    `processEvents(ExcludeUserInputEvents, 50)` then `thread.wait(20)`, until
    the thread ends, `_done_capturing` lets it go, or END_SECONDS
    (ATTACH_SECONDS + 3) pass. The page answers the handshake, the held wire
    is cut there, and the thread ends.
  * `_done_capturing` makes no fresh page while `_ending`. Nothing needs a
    new QWebEnginePage made inside aboutToQuit.

The cut alone would not have been enough. `targets()` (urlopen, 20 s) and
the handshake cannot be cut, and only the main thread answers them, so the
turning events are what end those two.

Why not the review's other two suggestions:

  * A longer plain wait: the page cannot answer a blocked thread however long
    it waits. Only attach's own limits would end it, which is 5-8 s of a
    program that looks hung as it closes.
  * Taking a still-running thread out of the window's ownership: the process
    ends anyway, and the interpreter's own teardown would then destroy it.

Measured after (after_test_browser_quit.txt, after_teardown.txt): the three
first-moment cases exit 0x0, `app.exec()` returns 0.01-0.02 s after
`quit()`, and no thread is left running. The teardown probe exits 0x0. In
r3_probe_tour.py T4, `_end_capture` holds 0.00 s with no thread left; its
step error afterwards is the probe's own reference to a thread the window has
let go, as round 2 noted for r2_probe_tour.py.

New suite **test_browser_quit.py** (real window platform, a child process per
case, crash dialogs off in the child, sandbox APPDATA). It checks the pieces
in-process: attach's `hold` before any call; `_first_wire` with a cut
before, during and just after attaching; with no cut, as before. It then
runs five whole-program cases (quit at once twice, close then quit, quit
after 0.4 s, no capture). Before the fix: 18 passed, 10 failed. After: 33/0.

**A slip put right took the page off the tour for good.** Measured before
(before_tour.txt), a 3-link tour on link 2:

  * T2, one character of its address deleted and typed back: `_gone` stayed
    2, the chip said "Another page", and Next would open link 3. Capture
    filed a new clipping titled from the page, and row 2 stayed unticked.
  * T2b, its lines deleted and then Ctrl+Z: the same.

Now `update_tour` keeps `_gone_was` when it sets `_gone`. That holds the link
that went, the page object, the page's `moves`, and `left_tour`,
`_tour_load`, `_landed` and `pending_login` as they were. `_gone_back` puts
all of it back when that link is in the list again, the page object is the
same, and `moves` has not changed. While the link is gone, `_url_changed`
and `_load_finished` go on following its load in `_gone_was`, so a link
taken off in the middle of a redirect comes back landed.

`TourPage.moves` is new because `left_tour` cannot say whether the person
moved: taking a page off the tour sets it too. It counts:

  * a link clicked, a form sent, Back or Forward (acceptNavigationRequest);
  * an address typed or dropped, or a page's new tab (`_open_typed`);
  * a sign-in page opened (`open_login`).

A reload does not count, nor a page's own script going on (7d's pushState).
Once the link is back, `on_tour_link` still judges those by address.

Measured after (after_tour.txt): T2 and T2b are at 1, `_gone` None,
"Not captured yet", and Next opens link 3. Capture files under link 2 with
"Somebody reading" and ticks row 2. test_embedded 7c now pins:

  * a keystroke typed back;
  * lines deleted and undone;
  * Capture then filing under link 2 with its words and ticking its row;
  * an address the person opens themselves in between keeping the page their
    own.

**An undone clipping still said "Captured ✓" in the browser.** Before (T3):
after `undo_stack.undo()` the links window's row was ticked again, but the
browser's chip and picker kept the ✓ and `_done` stayed True, even after the
links window was activated. `_refresh_states` repainted rows and never told
the browser; only `_repaint(url)` and `_reread` did. Now it marks the
browser for each link whose state changed, even while a list runs or when
not repainting. After: the chip says "Not captured yet" and the picker has no
✓. test_embedded 7f pins undo and redo in both windows.

**A link put in at the start of a labelled link's line took its words.**
Before (before_linkbox.txt): L1, L1b, L2 (a blank line between) and L4 (a
drop) were wrong, and L3 was right. `_link_line_below` only handled a cursor
inside a line of words. `LinkBox._label_line_above` now finds the line of
words naming the link the cursor is just before: at the start of that link's
line, or anywhere on a blank or spaces-only line between. `put_links` then
goes before those words. Whether the words name the link is asked of
`links.find` on the two lines together, so the label rule is not written a
second time. A link with words of its own on its line is left as before.
After: 5 as wanted. test_linkbox section 10 has seven checks, including the
drop, the spaces-only line, one Ctrl+Z, and the own-words control. Before
the fix the suite was 40 passed, 5 failed.

**Every right-click menu stayed a child of the links window.** Before
(before_menus.txt): 100 menus left after 25 rounds. `_show_menu` and
`_row_menu` now set WA_DeleteOnClose before `popup()`. `menu_for` and
`row_menu_for` are unchanged, because the suites build menus with them
without showing them. After: 0 left.

**Trap in the menu check.** test_webclip's check sends
`QEvent.DeferredDelete` itself. The suite's checks run inside a timer's
event, and a deferred delete posted there is not delivered by its nested
`wait()` loops, so a count taken after `wait()` alone would stay high
whatever the code did. `self._menu` points at a deleted menu once that menu
closes. Nothing reads it then; test_webclip reads it only while the menu is
open.

**Release notes.** The paste-box bullet gains "the words written over a link
stay with that link". The other four faults are in parts new in 2.0.32,
which nobody has had, so nothing is said of them.

**Suites after these fixes (15 September 2026), every one after the last
change.** No earlier check was changed; 7c's flow was extended, not altered.

  * test_browser_quit 33/0 (new; 18 passed, 10 failed before the fix);
  * test_embedded 196/0 (7c 8 new checks, 7f 4);
  * test_linkbox 45/0 (section 10);
  * test_webclip 110/0 (the menu check; 109/1 before);
  * test_sitedata 57/0, test_sitepanel 31/0, test_fromchrome 43/0,
    test_weblinks 95/0, test_carryforward 48/0, test_collect 82/0;
  * test_dropflow 17/0, test_dropscroll 21/0, test_window_drop 38/0,
    test_real_drop 15/0 (its eight win32com tracebacks, as in round 2),
    test_capturequality 516/0.

Windowed suites and probes were run one at a time.

## Collect's options, and the short forms filing the division (2.0.32)

Right-click Collect from WhatsApp opens its options. The office asked for a
Collect they could "set up for a particular session and carry on", and for
the six division short forms to be read (the reader side of that is in "The
division short forms, and links glued together" above).

### Where the options live, and why nowhere else

On the Collector, in memory: `collector.options`, a frozen
`collect_options.CollectOptions`. The window makes the Collector once, so the
options survive Collect off and on and a newspad switch, and a new launch
starts at `DEFAULTS`. They are never written anywhere - the suite scans every
file under its sandbox APPDATA for the option names. A session newspaper
remembered overnight is exactly the setting that would quietly print
yesterday's paper on tomorrow's clippings, and Collect itself is already
"never remembered across launches".

Every default is 2.0.31's Collect, with two deliberate exceptions:

  * the short forms are read (the fix itself);
  * **a story link no photo is waiting for goes to the links list**
    (`links_to_list`, on). Before, it was refused (NO_PHOTO, or LINK_NOT_USED
    when the newest photo already had a newspaper or a link) and kept only
    for the button, and the next photo's arrival quietly lost it. The
    review of the stream designs found this was the one route by which a
    copied link never reached the links window. It goes through
    `MainWindow.open_links(url, quiet=True)`, never raised or activated,
    because Collect never takes the keyboard from Chrome. A link already
    listed is said, not listed twice. The review of this step changed where
    it goes and when the window shows - see below.

`paste_clipboard` now asks `_links_in` before Collect's PASTE_NOT_NEEDED
early return. With Collect on, a link pasted with Ctrl+V used to be answered
"Ctrl+V is not needed" and never reached the links window.

### Why the options are in their own module

test_copied section 0 pins ui/collect.py to `copied.read`,
`caption_values`, `as_typed_words` and the WHY_ strings. Everything else the
options need - `ReaderRules`, `division_used`, `listed_paper`,
`listed_city`, `UNLISTED_PAPER_CONFIDENCE` - is reached from
ui/collect_options.py. collect.py passes `collect_options.reader_rules(...)`
as read()'s third argument and never names a rule itself. The pin still
passes (test_copied 827/0).

### Every place a "may a caption name this?" decision is made

Session defaults make a waiting photo's newspaper non-empty, so the plain
`caption_open(clip)` would refuse every caption on a preset photo.
`Collector._caption_open(row)` is `caption_open` or "this row's name is still
only what the session stamped" (`_is_preset`: stamped this session, still
`copied`, no caption_raw, newspaper and edition unchanged). It is used at all
four sites: the same-photo "the next caption goes on it", the as-typed path,
the main caption path and `use_pending`'s as-typed button. The link path
accepts a preset row the same way. What was stamped is kept per row, so a
caption that leaves the city or page out keeps the session's, even after the
options change.

The stamp happens before `_add_loose`, so the photo and its name are one
undo step. It is `name_source="copied"` with an empty `caption_raw`, so
`profiles.apply_to_clip` never re-guesses it on a merge.

### The division, set only where it cannot hide a card

A code sets `clip.division` only when the clipping has none. On the board it
also has to be either All divisions or the division already showing, because
`sentiment_board._visible_rows` and the dossier drop a card filed under
another division. So "HT LKO" on Delhi's board names Lucknow, keeps DLI, and
the bar says why ("the card stays under Delhi, the division the board is
showing"). A clipping that already has a division keeps it and says so. A
city written in full never sets one: `copied.division_used` answers only for
a code the reader actually read. `division` joined `FillFromCopy.FIELDS`, so
one undo takes the caption and the division back together. `PutInEnglish`
has its own FIELDS and is unchanged.

### The menu, the dialog and the bar

  * `StayOpenMenu` triggers a checkable, non-exclusive item on mouse release
    or Enter and stays open. Radios and plain items close it as usual. Group
    headings are disabled actions, because `QMenu.addSection` text is not
    drawn under the app stylesheet. Shown with `popup()`, never `exec()`, and
    so is the options line's "Change…". While the popup is up `_idle` already
    holds copies, and a change applies to them when it closes (pinned).
  * The session box is `SessionDefaultsDialog`, opened with `open()`. It is
    window-modal, so copies wait while it is up. The name notes are refreshed
    on a 150 ms timer, not on every keystroke. The names are stored as the
    lists spell them ("dj" -> Dainik Jagran, "LKO" -> Lucknow). A paper not
    on the list stamps 0.7, which is amber.
  * "The one clipping ticked" is offered only in the press report. The board
    has no selection that the batch bar or Collect can read yet (see step D),
    so in the sentiment board the item is disabled and a caption goes on the
    newest photo.
  * The options' board column while another is opened out: the card lands
    out of sight, so the bar says where it went and the page is not asked to
    reveal it (`_add_loose(reveal=False)`).
  * The bar gets a second label, `options_line`, so the pinned message texts
    never change. The button's `tuned` property gives it an amber
    `COLLECT_TUNED_LINE` border. The border colour only changes, never its
    width: the window floor is pinned equal with options changed and at the
    defaults, with Collect on and off. `#FDBA74` is 6.96:1 on the header and
    4.23:1 on the Collecting green.
  * `_add_loose(clips, quiet=False, tidy=None, reveal=True)` and
    `_tidy_screenshots(clips, wanted=None)`: Collect's "always/never trim"
    never writes the Layout card's own setting.

### A trap in testing "bring into view: off"

The first run failed: the page moved to 5063 with reveal off. The cause was
not reveal off. `_reveal_on_page` scrolls at 0, 160 and 450 ms, and the suite
set the page to the top 60 ms after the *previous* photo's copy had settled
(450 ms). The previous photo's last reveal carried it down.
probe_reveal_off.py recorded no scroll at all after a reveal-off photo once
the earlier timers had run. The check now waits them out and records every
`valueChanged` after the photo arrives.

### Results

test_collectoptions 195/0 (new), test_copied 827/0, test_collect 82/0,
test_astyped 36/0, test_collectscroll 29/0, test_webclip 110/0,
test_weblinks 95/0, test_window_drop 38/0, test_dropflow 17/0, test_four
27/0, test_board_send 23/0, test_batchbar 108/0, test_split_pools 26/0, and
from the design's wider list test_tidy 23/0, test_english 49/0,
test_dupswap 31/0, test_dropscroll 21/0, test_headerbits 23/0,
test_contrast 28/0, test_resize 35/0, test_fluid 13/0, test_sentiment_ui
74/0, test_boardfields 33/0, test_summary 31/0, test_newspads 137/0. No pin
in an existing suite had to change.

### What the review of step A2 found, and what changed (2.0.32)

Every finding was reproduced first with the reviewers' own probes
(review/A2/probe_a2.py, probe_a2b.py, probe_gaps.py, probe_menu_release.py,
probe_quiet_links_zorder.py), and each is pinned in test_collectoptions.

**Photos off let a caption slide onto the photo before.** The design said the
target stays. But the caption copied after an uncollected picture belongs to
that picture, and every other picture that is not taken (too small, not a
picture, a picture's address) already leaves no photo waiting - the module's
one rule. With photos off the picture now clears the target too, so its
caption is NO_PHOTO; with "replace" on it no longer overwrote the name before.

**A photo named from the session and then printed as typed kept the session's
paper.** "Veer Arjun Delhi" printed above the picture while the fields still
said Dainik Jagran, Lucknow - and the coverage summary counts papers from the
fields. On a preset row the same CaptionAsTyped step now also empties
newspaper, city and page, so one undo brings the session's name back. The
session's division stays: it is where the person is working.

**A caption copied just before its photo said none of its notes.** The one
message replaced everything: no "Filed under Lucknow division", no small
picture, and on Delhi's board no word that the card stays under Delhi - which
the brief requires. `use_pending`'s work is now `_put_pending`, returning its
notes; `_named`'s reading notes are `_reading_notes`; `_take_picture` keeps
the photo's own notes apart from its message. EARLY_USED carries all three.

**"The division the board is showing" on All divisions.** That wording is now
only for a card under the one division on show. A card with its own division
on All divisions, or under another one, gets NOTE_DIVISION_KEPT_CARD ("the
division it already had").

**The links route, three faults.**

  * *A link after its photo's caption was still refused.* The route ran only
    with no photo at all, so the usual order - photo, caption, the story's
    link - still flashed LINK_NOT_USED and lost the link with the next photo.
    A photo with a newspaper or a link is not waiting for a link either, so
    that refusal now goes to the list too (LINK_TO_LIST_TAKEN names the
    photo). The menu label stands; its tooltip says what "waiting" means.
    With the option off it is 2.0.31's refusal and button.
  * *A closed window's list was wiped.* Closed, `open_links` started afresh,
    and `setPlainText` took the box's undo with it. `MainWindow.links_kept()`
    is what a quiet link goes under: the box while open, or while it was last
    used in this newspad (`_links_gen`). After a newspad switch it starts
    afresh, since captures land in the newspad in use. The duplicate check
    reads the same thing, not only an open window.
  * *The "quiet" window still went on top of Chrome.* Measured by the review
    on the real window platform: shown without activating, it kept the
    keyboard off but still went above the window in front. Now it is shown
    only while the main window is the active one. Otherwise `_links_waiting`
    is set, the bar adds LIST_WHEN_BACK, and `changeEvent` shows it when the
    person comes back. No taskbar flash: a link waiting in the list needs no
    attention, and the flash is kept for refusals. The person's own Ctrl+V
    also appends while unseen links wait, so it never wipes them.

**Two traps in that last fix, both on the real window platform**
(fixA2/probe_activation_diag*.py, one scenario per process in the end):

  * The first version of the probe said the window, shown on return, took the
    keyboard. Six rounds of diagnosis ruled out the fill, the second link,
    focus widgets and timing. The cause was the probe: it asked `d.winId()`
    before the first show. A native window made before its first show keeps
    the show-without-activating flag it was made with, because Qt passes
    `WA_ShowWithoutActivating` to the native window (`_q_showWithoutActivating`)
    only when it makes it. With an early winId it failed every time (P15);
    without, never (P1, P8, P16). Nothing in the program asks for the links
    window's winId today, but win_drop does for the windows it takes drops
    on. So `_show_links_quietly` also sets the property on an existing native
    window (P17 passes).
  * The show on return is queued (`QTimer.singleShot(0)`) and not done inside
    the ActivationChange, so it never interleaves with the activation itself.

**What was copied… lost every copy to a Reset.** One line per option changed
meant 21 changes and a Reset filled all 40 lines. Now a change of options is
one line (OPTIONS_RESET for a return to the defaults), and option lines are
capped apart (OPTIONS_HISTORY_MAX = 12), so they never push out a copy.

**"The one ticked clipping" said the wrong thing.** A new photo said "Now copy
its caption" and the same photo again said the next caption goes on it -
both wrong when captions go on the ticked clipping (ADDED_TICKED with
NOTE_TICKED now, and no ALREADY_NEXT). With two ticked, a link went to the
links list instead of PICK_ONE, and with none an unreadable caption was told
to copy again. PICK_ONE is asked first on both routes. On the board the menu
ticked "the one ticked clipping" while captions went on the newest card: the
choice now shows what is in effect where the menu opens (`in_effect`), and the
phrase says "ticked in the press report".

**A lone mouse release flipped a tick.** QMenu takes a release only when its
press was on the menu. The fix first recorded the press, and the suite then
caught a second trap: when StayOpenMenu takes a tick's release itself, QMenu
never sees that release, so it still counts the earlier press as its own and
acted on the next lone release - it ticked Photos and closed the menu. A
release with no press of its own on this menu is now dropped before QMenu
sees it.

Not done as the review put it: an unreadable caption refused with PICK_ONE
keeps its words in the Pending, but no button offers them once a clipping is
ticked. The button needs a target, and ticking does not redraw the bar. That
matches a readable caption under PICK_ONE, which has no button either.

Results after the review fixes: test_collectoptions 221/0 (was 195; its pins
for photos off, the links route and the history changed on purpose, as above),
test_collect_quietlinks 13/0 (new, real window platform: the links window is
held back while another window is in front, opens on return without taking
the keyboard, keeps a closed list, and survives an early native window). The
whole battery passed, 106 suites: test_collect 82/0, test_astyped 36/0,
test_collectscroll 29/0, test_copied 827/0, test_webclip 110/0, test_weblinks
95/0, test_window_drop 38/0, test_dropflow 17/0, test_four, test_board_send
23/0, test_batchbar 108/0, test_split_pools, test_embedded 196/0,
test_linkbox 45/0. No pin in an existing suite had to change.

### Round 2 of the review of step A2, and what changed (2.0.32)

Every finding was reproduced first with the reviewers' own probes
(review/A2/probe_r2.py, probe_r2_menu.py, r2/probe_r2b.py, probe_diff.py) and
re-run after the fix (fixA2r2/). Each is pinned in test_collectoptions.

**A tick clicked with a submenu open did nothing.** While a submenu is the
active popup, Qt gives it every mouse event. QMenu hands an event over the menu
below on to that menu (`QMenuPrivate::mouseEventTaken`), and a release only when
that menu holds the press. Round 1's guard sat in the submenu. The press was not
on the submenu, so the guard dropped the release before QMenu could pass it on.
A release with no press of its own is now given to QMenu when it lands over a
menu this one was opened from (`_over_menu_before` walks `parentWidget()` while
it is a QMenu). That menu's own `_press_seen` still drops a truly lone release,
so round 1's trap stays closed. Section 3 drives it with QTest on the menu's
`windowHandle()`, so Qt routes the click through the open popup as a real mouse
does.

Trap: the reviewers' bare side-by-side (one tick, one submenu) still shows
StayOpenMenu toggling nothing. That is only because it ran second, at the same
point, in the same process. In fixA2r2/probe_minimal_menu2.py a StayOpenMenu
toggles and stays open when it runs alone, at 300,300 or with a button parent.
Any menu clicked second at the same global point is hidden on the press, before
its release, and a plain QMenu fails the same way ("qmenu300 qmenu300"). The
second press carries QTest timestamp 503. Nothing in our menu causes it.

**A caption copied just before its photo went on the photo after a refused
one.** Every refused picture cleared `target`, but the early Pending kept its
flag, so the next photo took the caption silently. This happened on four routes
(too small, a picture's address, photos off, the watcher's "unreadable").
`_no_photo_waiting()` now clears the target and `pending.early` at all of
those, and at "not a picture". The caption stays pending, so the next photo
offers 2.0.31's "Put it on No. N" instead.

**Ctrl+V listed a link Collect had already dealt with.** Round 1 moved
`_links_in` before PASTE_NOT_NEEDED so that a pasted link reaches the links
window with Collect on. That also let through links Collect had put on a photo
or in the list, and Capture then made a second clipping of the story. With
Collect on and the copy already read, `Collector.links_not_taken(words)` now
leaves out any link that is some clipping's url (report or board) or in
`links_kept()`. If nothing is left and the list has the link, it flashes
PASTE_LINK_LISTED and the links window opens. Otherwise it flashes
PASTE_LINK_ON with the clipping's number. The list is asked first, because a
link can be in both places and the list is where the paste was going. A copy
holding a taken link and a new one lists only the new one. Its words are
rebuilt as label and address, and a numbered list loses its numbers. That case
is rare: Collect never takes a copy with two addresses.

**The session's division, silently not put on a card.** On a board showing one
division, `stamp_preset` leaves the division off so the card is not hidden, yet
the options line says every photo gets it. NOTE_SESSION_DIVISION now says the
card stays under the board's division, and where the session's goes. It is one
of the photo's own notes, so a caption copied just before carries it too.

**2.0.31's "Put the link on No. N" had gone.** Round 1 sent a link copied after
its photo's caption to the list instead of refusing it, and the button went
with the refusal. That branch now also keeps a Pending (`link_only`, USE_LINK,
`listed=True`), with no alarm and no amber. When the button is used, the link
goes on the photo and `LinksDialog.take_out(url)` removes its line from the box,
as one undo step in the box. It only removes a line that holds just that link,
with none of the sender's words above naming it. It also waits until nothing is
capturing and the link has not been captured. If it cannot remove the line, the
bar says the link is still listed. As in 2.0.31, the button moves on to the next
photo when one arrives. One trap is left open: undoing the link on the photo
does not put the line back. The link is then nowhere, which is where a refused
link was in 2.0.31.

**Lower-case sentence starts on the board.** On the board `_which` gives "the
card in Negative". LINK_TO_LIST_TAKEN, and 2.0.31's BY_HAND, HAS_CAPTION and
TYPED, start with it. `_capital()` now fixes the first letter at those four
places. No suite pinned the board wording.

Pins changed on purpose in test_collectoptions, section 9:
  * "Ctrl+V of a link with Collect on reaches the links window". The clipboard
    held a link Collect had already listed, so it is now PASTE_LINK_LISTED. A
    link Collect did not take (links off) is pinned reaching the window at the
    end of the section.
  * "with no alarm and no button". The button is now offered.

Section 7 empties the links list it adds to, because section 9 counts from
empty.

## A category as the report's list: the foundations (2.0.32)

The office asked for an expanded sentiment category to become the press
report's own list, with every one of its features. Step D1 lays the ground and
changes nothing on screen: one visibility rule, a scope on the list model, the
ordering helpers working inside a scope, and a list that can stand in for a
column when something is dropped on it. The steps after it put the list on the
board.

### One pool, one rule, a scope

`sentiment.shows(clip, column, division)` is now the board's only statement of
what it shows: the division on show or no division, and the column through
`column_for`. `_visible_rows`, `_refresh_columns` and `visible_clips` all ask
it. `ALL_DIVISIONS` moved to core/sentiment.py, and sentiment_board keeps the
name.

`model.Scope(column, division)` is one category in one division. It is frozen
and spelt one way only: a section folded into Digital names Digital, and None
means all divisions. The board will ask for its scope on every change, and a
scope that looked new each time would throw the ticks away. The division is
the board's `active` as it is: an empty one is the board with no divisions set
up, which shows only unassigned clippings (see Traps).

`ClipModel.scope` is a view state beside the lens. It is not the pool flag
turned down in "Two interfaces, two sets of clippings": no command reads it to
decide what to change. Every command still snapshots the whole pool, so undo is
exact whatever is focused when it runs (pinned: seven steps made across three
scopes, undone under a fourth).

Under a scope:
  * `visible_rows`, the brackets, the numbers, `select_range`, `shown_count`
    and `group_count` all follow it. The numbers run 1..n in the category,
    which is the card's badge and the dossier's order.
  * Bracket identities start with the scope's tag
    (`Positive|DLI|D:/day/dli.docx#1#run0`). One Word file sits in all four
    categories, and `run_folded` looks idents up by name, so without the tag a
    fold in Positive folded the file in Negative.
  * `set_all_collapsed(False)` opens only the scope's own brackets.
    `collapsed_row_ids` is shared by every category, and clearing it opened
    what had been folded elsewhere.
  * `set_scope` does nothing for an equal scope. `_update_counts` runs
    `set_rows` on every `countsChanged`, and a rebuild announces counts, which
    would ask again. A real change clears the lens, the lens folds and the
    ticks.
  * `rebuild` drops ticks the list no longer shows and says so. `refresh_clip`
    and `refresh_all` rebuild when membership changed: `SetFieldOnMany` and
    `EditField` only repaint, and a row moved to Negative stayed listed in
    Positive.
  * `number_of`, `neighbour_below` (the Merge partner) and
    `scoped_insert_point`. The last is after the category's last loose
    clipping, else its top, else the pool's own rule in an empty category -
    which keeps test_collect 42's `rows[-1]`.

`headings_print` (default True) gives `section_openers == {}` when off. The
dossier prints no section headings, and board rows otherwise got red SOCIAL
MEDIA and ELECTRONIC MEDIA chips and refused moves. The window turns it off on
the board's pool in the next step.

### The weave

`move_to`, `move_relative` and `move_group_relative` take `rows=`. With no rows
and a scope they work over the category and `_weave` it back into the slots it
already holds, so nothing in another category or division changes place.
`move_to` is still given a place in the whole pool - what `ClipList.dropEvent`
works out - and turns it into a place in the category. `plan_move_into` moves
only the category's own clippings, weaves `rows_after`, and skips the heading
hand-off and refusals when `headings_print` is off. The weave lives inside the
helpers so no caller can order the category and forget the rest. Handed a list
that is not the scope reordered, it returns the pool unchanged rather than lose
a clipping.

Measured on the suite's fixture of thirty clippings:
  * On the pool, 'up' on No. 2 of Positive DLI stepped over a Digital row and
    nothing visible moved. Scoped, it moves.
  * All 31 drop targets for four picks give the order a whole-pool drop gives
    the category, and every outside clipping keeps its slot. The whole-pool
    drop does not keep the slots.
  * dli.docx's Positive rows [4, 6, 10] sit between Negative, Neutral and
    Social rows, so a bracket arrow could not find the file on the pool. Every
    bracket's four arrows now work on it.

### The list's drop routing

`ClipList.drop_section` and `empty_hint` are None and empty on the press
report's list. With a drop section, a drop that is not the list's own rows goes
to `accept_payload_into(mime, section)`, so it lands in that category. A board
card let go on a list is ignored: it used to be "Nothing to add". The empty
words are painted in QFAINT. An empty list standing at its content's height is
one pixel tall, so with words it stands `EMPTY_HINT_HEIGHT` (120). The window's
`_section_under` asks for `drop_section` first as it walks up from the widget
under the pointer.

### How "the same with no scope" was shown

focuslist_capture.py ran before any of this changed and wrote
focuslist_before.json. It holds:
  * 16 list states: folds, filter and arrangement, ranges, section edits and
    reset_view;
  * 140 `move_relative`, 32 bracket, 155 `move_to` and 36 `plan_move_into`
    results, 11 of them refused;
  * one `MoveIntoFile` forwards and back;
  * the board's buckets, counts and export order for DLI, UMB, LKO and all
    divisions.

test_focuslist section 1 works all of it out again on the changed code and
compares key for key.

### Traps

  * A model with its own id counter mints id 1 on a merge, which is one of the
    fixture's own ids. The window's two pools share one counter; the suite
    gives its model one that starts at 1000.
  * `shows` with an empty division means unassigned clippings only, exactly as
    the board did with no divisions configured. `Scope` first turned an empty
    division into all divisions, and the review measured what that does: a
    board with no divisions set up has `active == ""`, its Positive column
    held card 14, and `Scope(Positive, board.active)` listed fourteen rows.
    All four columns disagreed. Only None is now another spelling of all
    divisions, and the tag of an empty division is `Positive||`.
  * test_foldall's own modal guard names QMessageBox without importing it, so
    it prints a NameError whenever the import's progress dialog is up. That is
    harmless and older than this work: exit 0, 18/0. Not touched.

### After the review

Five findings, each reproduced with the reviewers' probes (review/D1
probe_scope.py and scopeprobe.py) before it was changed, and run again after.

  * The empty division: see Traps. `Scope` keeps `""` as the board holds it.
  * `_weave` compared how many rows it was handed, not which. A list of the
    category's length with its first row twelve times gave back 30 rows
    holding 19 clippings, and pushed as a Reorder the pool held 19 until undo.
    It now compares the rows themselves and hands back the pool unchanged
    otherwise. No helper sends such a list; the guard is for the next caller.
  * A move into a file, undone while another category was open, lost the
    moved clipping's fold. `_fold_sets` worked the brackets out under the
    scope on show, where the movers sit in no bracket, so the fold kept for
    them never came back: Positive's folded loose clipping 19 came back open
    when the undo ran in Negative. `MoveIntoFile` now keeps the scope it was
    made under, and its fold sets are worked out there for undo and redo
    alike. `file_runs` and `_file_groups` take `scope=` for it, and the
    default `SCOPE_ON_SHOW` leaves every other caller as it was. A mover that
    no bracket holds keeps its own fold, as a last resort.
  * The same function rebuilt `collapsed_groups` from the scope on show
    alone, so a move in Positive threw away Negative's Collapse all. The
    brackets still drew folded through their clippings, but `all_collapsed()`
    said no. Every category and division with a folded bracket is worked out
    again now. `Scope.of_ident` reads the scope back from an identity, which
    is exact because group keys are file paths or `__loose__` and a division
    code holds no bar.
  * A file folded under All divisions and opened under Delhi was folded
    again back under All divisions: its identity stayed, and so did its Ambala
    clipping, No. 8, in `collapsed_row_ids`. A fold reaches every view that
    holds one of its clippings (`run_folded` needs only one), so opening now
    reaches as far. `_open_elsewhere` discards, under the same category's
    other divisions, every folded bracket that shares a clipping with the one
    opened, clippings and all. Expand all under a scope does the same. Another
    category never shares a clipping and is not touched.

None of it reaches the list with no scope. `_weave` is only called under one,
`_open_elsewhere` returns at once without one, and a command made with no scope
works over no scope as before, with no tagged identities on the press report
to read back. Section 1's capture from before D1 still matches key for key.

  * `{scope} | {...} - {None}` in `_fold_sets`: the minus binds first, so a
    command made with no scope still works over no scope.
  * The probe's six "not exact" lines in P6 come from its own history, which
    counts pushes. Keyed by the stack's index instead (probe_fuzz_diag.py),
    the same seeds undo and redo exactly, before these fixes and after.

After the fixes: test_focuslist 135/0 (fifteen checks added, one pin turned
round: `Scope(D, "")` used to be pinned equal to all divisions, and is now
pinned apart from it), test_sentiment_ui 74/0, test_cards 16/0, test_dossier
17/0, test_filter_roundtrip 48/0, test_foldall 18/0, test_batchbar 108/0,
test_four 27/0, test_window_drop 38/0, test_dropflow 17/0, test_collect 82/0,
test_split_pools 26/0, test_board_send 23/0, test_session 27/0. test_real_drop
is 14/1 inside the batch ("an editor is open", the rename box after a drop) and
15/0 run alone, exactly as the reviewers found it before these fixes.

### After the second review

One finding, about the design step D2 follows rather than about D1's code.
design_D.json told D2 to build the board's scope as
`Scope(column, '' if board.active in ('', '__all__') else board.active)`,
written when an empty division still meant all divisions. It no longer does, so
that recipe lists only the unassigned clippings under All divisions. Measured
on the fixture with a real board after `select_division(ALL_DIVISIONS)`
(review/D1/r2/fix_repro_q4.py): Positive holds fourteen cards and the recipe
listed [14]; Neutral, Negative and Digital disagreed the same way. The board's
`active` passed as it is matched all four.

  * design_D.json now says `Scope(Section(board.focused), board.active)`, never
    respelt. Its `shows` line and its `Scope` default said the same old thing
    and were corrected with it (review/D1/r2/patch_design_d.py keeps the
    original beside it). The respelling came from `_stamp_pending`, where it is
    right: a clipping added under All divisions takes no division rather than
    the picker's `__all__`. The design now says that is a different rule and
    not to copy it into the scope. `_stamp_pending` is not touched.
  * `sentiment.shows` says in its docstring that an empty division matches only
    the clippings with no division and is never another spelling of
    ALL_DIVISIONS. No code changed.
  * test_focuslist section 2 gained one check: a board with divisions, in each
    of DLI, UMB, LKO and All divisions, has every column's cards equal to what
    `Scope(column, board.active)` lists, all thirty clippings on show under All
    divisions, and fewer for the empty division. It had only pinned the board
    with no divisions set up.

After this fix every live suite and the two battery-only ones ran serially, 105
in all, every one exit 0 with no failure (review/D1/r2fix/all_results.txt).
The step's own list: test_focuslist 136/0, test_sentiment_ui 74/0,
test_dossier 17/0, test_filter_roundtrip 48/0, test_batchbar 108/0,
test_window_drop 38/0, test_real_drop 15/0 (inside the batch this time),
test_dropflow 17/0, test_collect 82/0. test_cards, test_foldall and test_four
print no total when they pass and exited 0, in the batch and run alone.
No pin in an existing suite had to change.

### Results

test_focuslist 120/0 (new), test_sentiment_ui 74/0, test_cards 16/0,
test_dossier 17/0, test_filter_roundtrip 48/0, test_foldall 18/0,
test_batchbar 108/0, test_four 27/0, test_window_drop 38/0, test_real_drop
15/0, test_dropflow 17/0, test_collect 82/0. From the design's wider list:
test_split_pools 26/0, test_board_send 23/0, test_boardfields 33/0,
test_boardpicker 14/0, test_english 49/0, test_headerbits 23/0, test_360 60/0,
test_dropscroll 21/0, test_collectscroll 29/0, test_session 27/0,
test_newspads 137/0, test_carryforward 48/0 (the network-import pin),
test_fromchrome 43/0, test_dupswap 31/0, test_independent 23/0, test_resize
35/0, test_scroll 15/0. No pin in an existing suite had to change.

## A category as the report's list: on the board (2.0.32)

Step D2 puts D1's scope on screen. Expand, a Quick focus chip or a focus bubble
shows the category as the press report's own ClipList over the board's pool,
and every list gesture reaches the same MainWindow handler the report uses,
told which pool it is for. Nothing is copied and no command class is new.

### Where the list stands

`SentimentBoard.focus_area` sits in the board's work half under the column
strip: a slot for the list's bar and filter strip (the window makes them - it
owns what they do) and `focus_list`, built once and never rebuilt, because a
headline box opened on it is found again by a timer. Focused, the card view is
hidden, the strip is held to the header's height with stretch 0, the list
follows its content, and the page scrolls - so reveal, Enter to the next row,
edge autoscroll and the floating top/bottom buttons all move the page, as on
the report. `show_settings(False)` runs a moment later, once the page's range
has grown. Closed, the strip goes back to minimum 0, maximum 16777215 and
stretch 1, and every card view is shown.

  * The cap is measured: `heightForWidth` at the strip's viewport width, plus
    the panel's edge. First written as "+2 for the layout margin", it cut two
    pixels off the subtitle (header 52, wanting 54): the panel's stylesheet
    border is a further pixel each side. The edge is now
    `rect - contentsRect` plus the layout's margins.
  * The subtitle wraps with the width, so an event filter on each header
    re-caps (later, not inside the header's own resize) while it is the
    focused one. Pinned at 760 and back at 1280.
  * Measured at 1280x800: page viewport 491px, the list 331px of it (67%)
    once the set-up is away, header to the list's bar 12px. The window's floor
    is no wider than over four columns.

### Which list, which pool

`_list_pool()` is the report's pool in its own interface, the board's while a
category is opened, and None over four columns. The navy bar, Ctrl+A, Delete,
Home/End and the batch handlers ask it where they used to test
`mode != 'standard'`, so test_batchbar 17 and 24 and test_split_pools 8 hold
unchanged: over four columns nothing acts. `_list_for(pool)` and
`_list_parts(pool)` give the view and the bar's widgets. The list's signals are
wired with `functools.partial(handler, pool=board_model)`; each handler reads
`pool or self.model`, pushes on `stack_for`, and ignores ids its pool does not
hold. `_selected_ids(pool)` is in list order (`scoped_rows`); numbers in flashes
and the English summary are `number_of`, so a category says its own numbers.

`_sync_board_scope()` builds `Scope(Section(board.focused), board.active)` -
active as it is, see D1's second review - and does nothing for an equal scope.
A change commits the list's box, clears the board's filter strip and its
shift-click anchor, and counts once. `focusChanged` is sent from `toggle_focus`,
`_division_picked` and `select_division` (which said nothing before), and
`_refresh_board` and `_update_counts` ask too. `_update_counts` returns at once
while `_scope_changing` is set, and after a sync that changed the scope,
because the sync has just counted under the new one: no recursion.

`board_model.headings_print = False` from construction.

### What the list offers that the cards did differently

  * Move to (bar and right-click) lists the other three categories first,
    through `_assign_sentiment`, which now also unticks what left and drops
    their row folds. The right-click menu on the board is a popup, never
    exec(); the report's keeps exec(), which test_batchbar reads by polling
    for the popup.
  * `_DropBubble` takes list rows on another category's bubble (its own
    takes nothing) and sends `assignRequested`; click and style unchanged, and
    still at `bubbles[k]['button']`.
  * The row's bin deletes at once with "Ctrl+Z brings it back", as the report
    does (design open question 0); a file's bin and the bar's Delete ask.
  * `begin_rename` opens the list's box while focused, and opens nothing for a
    clipping another category holds. `commit_editors`/`settle_editors` reach
    the list. A quiet arrival (Collect, a captured link) is scrolled into the
    list by `_reveal_in_board_list`, and `reveal=False` still leaves the page
    alone.
  * The board's bar has no duplicate buttons: the check reads the report's
    pool only (open question 1). `edit_categories` on the board reuses the
    existing CategoriesDialog, opened with open() since the review (see
    After review).
  * The report page's foot room for the bar is now set only in the report's
    interface (it was whenever the bar showed, which was only there);
    `board.set_foot_room` gives the board's page the same room.

### Traps

  * A direct `clicked.connect(self._put_all_in_english)` delivered `checked`
    as the new `pool` argument: the report's Hindi to English and Select all
    buttons acted on False, and test_english failed nine checks. Both are
    lambdas now; every other direct connection to a changed handler was
    grepped - list signals, `toggled` and `changed` pass no spare argument.
  * `QUndoStack.count()` keeps undone commands, and a push after an undo drops
    them, so "one step" measured by count reads zero. The new checks use
    `index()`.
  * test_collectoptions 19 reads `_add_loose` with inspect.getsource. Run while
    main_window.py was being edited, it read shifted lines and failed; alone
    afterwards, 237/0.
  * test_real_drop 7, "an editor is open", failed 14/1 twice run alone.
    Wrapped in a logger of every open, commit and cancel, the report's box
    opened on clip 3 and nothing closed it, and the suite passed 15/0: the
    check runs straight after a deferred open. D1 recorded the same check
    flaking in the batch.

### Left for the next step

Design steps 9-11: `_add_loose` still inserts at `loose_insert_point` (not
`scoped_insert_point`), `_stamp_pending`'s focused fallback, `dropEvent` and
`_native_files_dropped` falling back to the focused category, clip_from_link
and fromchrome's numbering, `_preview_delete` walking the category, and the
arrival, preview, export, session and re-entrancy test blocks (design 13-18).
`_clear_for_switch` already clears the board's filter strip and anchor.
`_board_focus_changed` also refreshes Collect's bar, which names the column a
collected photo goes in: it said the old one until something else redrew it.

### Results

test_focuslist 288/0 (152 checks added for sections 6-17; one label in section
5 reworded, no check changed), test_sentiment_ui 74/0, test_resize 35/0,
test_scroll 15/0, test_workarea 24/0, test_fluid 13/0, test_independent 23/0,
test_english 49/0, test_dropflow 17/0, test_headerbits 23/0, test_360 60/0,
test_filter_roundtrip 48/0, test_batchbar 108/0, test_split_pools 26/0,
test_board_send 23/0, test_foldall 24/0, test_boardfields 33/0, test_cards
16/0, test_four 27/0. Also test_collect 82/0, test_collectoptions 237/0,
test_window_drop 38/0, test_collectscroll 29/0, test_boardpicker 14/0,
test_dropscroll 21/0, test_wholepage 31/0, test_carryforward 48/0 (the
network-import pin). test_real_drop passed 2 of 3 plain runs and 15/0 under
the logging wrapper; its one failure is always section 7's "an editor is open"
(see Traps). No pin in an existing suite had to change.

### After review

Four review findings, each reproduced first (review/D2/repro_fix.py, beside
the reviewers' probe1, probe3 and probe_timing) and then pinned in
test_focuslist section 18.

  * **A move took two Ctrl+Z.** `_assign_sentiment` pushed the section, then
    (for a clipping with no division, while one division is showing) the
    division as a second command. One Ctrl+Z took the division back and left
    the clipping in the other category, out of the list it came from.
    Measured on clipping 14: index +2 by Move to, by a bubble, and by a card
    drag - the last already so in 2.0.31. Both pushes now sit in one
    `beginMacro`, only when both run, so a clipping that has a division is
    still a plain single command. Redo sends it with its division again.
  * **The filter strip's count went stale.** `_refresh_filter_choices` ran
    from five places and none was a recount, so under a filter the board's
    strip said "Showing 5 of 12" over four rows after one left, and the
    report's did the same after a delete. `_update_counts` now calls
    `_say_filter_counts`, which rewrites only the words of a strip that is
    on screen. Not `_refresh_filter_choices`: its `offer()` rebuilds the
    chip buttons, and `_lens_changed` - run from a chip's own click - ends in
    `_update_counts`, so it would take the button away under its own signal.
    `_assign_sentiment` does call it, outside any click, so a paper whose
    last clipping in the category left is no longer offered.
  * **Two boxes waited with exec().** The board's "Which papers are which"
    now opens `CategoriesDialog` with `open()` (WA_DeleteOnClose), and
    `_categories_edited` runs from `finished`. The board's Set newspaper and
    Set edition build a `QInputDialog` with `open()`, fix the clippings when
    it opens and apply on `textValueSelected` through `_set_field_on`, which
    drops any clipping deleted meanwhile. Both are window-modal, so the list
    cannot change under them by hand. The press report keeps `exec()` and
    `getItem` exactly as it was; a check pins that.
  * **Every right-click left seven QActions on the window.** They were
    `QAction(text, self)` in a menu shown with `popup()` and WA_DeleteOnClose:
    the menu went and its entries stayed. All nine entries are parented to
    the menu now, in both interfaces. The report's own menu is still never
    deleted after its `exec()` (it was not before either); deleting it was
    left alone because a suite could read a menu after `exec()` returns.
  * The board's right-click Set newspaper/Set edition did nothing on an
    unticked row: `_bulk_field` read the ticks, and the menu offers it for the
    row clicked. On the board the menu now hands over its ids. The press
    report's menu has the same gap and is unchanged, as it has been since
    before 2.0.32.

Traps met on the way:

  * Counting `W.findChildren(QAction)` after closing a popup inside a nested
    `QEventLoop` still counts the closed menus' own entries: a deferred
    delete posted there waits for the loop it was posted in. The check calls
    `app.sendPostedEvents(None, QEvent.DeferredDelete)` and counts direct
    children, where the leak was.
  * test_focuslist sweeps the active modal widget every 150ms into MODALS.
    A check on a box opened with `open()` answers it straight away, with no
    wait in between.
  * Pin changed on purpose: test_focuslist 15 stubbed `QInputDialog.getItem`
    for the navy bar's Set newspaper. It now finds the open picker, checks that
    nothing was pushed and getItem was not asked, and answers the picker.
  * Suites run three groups at once through d2_run.py: test_four writes its
    summary to four_results.txt, not stdout, so the runner's fallback read a
    neighbouring group's file and reported 48. Alone it is 27/0.

Results after the fixes: test_focuslist 316/0 (27 checks in the new section
18, one in 15 repinned), test_sentiment_ui 74/0, test_resize 35/0, test_scroll
15/0, test_workarea 24/0, test_fluid 13/0, test_independent 23/0, test_english
49/0, test_dropflow 17/0, test_headerbits 23/0, test_360 60/0,
test_filter_roundtrip 48/0, test_batchbar 108/0, test_split_pools 26/0,
test_board_send 23/0, test_foldall 24/0, test_boardfields 33/0, test_cards
16/0, test_four 27/0, and test_notsaved 10/0 (it builds CategoriesDialog).

### Round 2: a pick dropped in silence, and ticks the filter hides

Two findings, reproduced first with the reviewers' probe_r2, probe_pick and
probe_more (review/D2/r2), then pinned in test_focuslist section 18.

  * **Round 1's fix reached the state the filter must never reach.**
    `_assign_sentiment` began calling `_refresh_filter_choices` so a paper
    whose last clipping left was no longer offered. `PickList.offer` drops a
    pick that is no longer offered, but `FilterBar.offer` runs with `_quiet`
    set, so `changed` never fires and the list keeps the old lens. Measured:
    Positive in Delhi, The Times of India picked (one clipping, 18), 18 moved
    to Negative. The list showed 0 of 11 with `board_model.lens.busy` True,
    while the strip's lens was not busy, nothing was lit, Show all again was
    greyed and the words said no filter was on. Select all then said "the
    other 11 are hidden", and the move pad was refused. The English pill
    reached the same state on the board (0/12) and in the press report (0/30,
    there since before 2.0.32). So did all five Hindustan Times rows moved
    together. Section 18 missed it because it moved one of five, so the pick
    survived.
    Fix: after each `offer()` in `_refresh_filter_choices`, if the strip's
    `lens()` is not equal to its list's `lens` (a dataclass, so `==` compares
    picks, order and ranking), `_lens_changed` hands the list the strip's
    lens. Only `_lens_changed` ever gives a list a lens from the strip, and
    scope changes and `replace_all` reset to an empty Lens. So a difference
    means something went stale. It is safe there because
    `_refresh_filter_choices` never runs inside a chip's click, and
    `_lens_changed` does not call it back.
  * **A paper brought back by Ctrl+Z was not offered.** Nothing on the undo
    path rebuilds the chips. The paper could be neither picked nor taken
    off, and a paper changed by a pushed step (Set newspaper) kept a lit pick
    over nothing. Now a single-shot `_offer_timer` (interval 0) is started by
    `indexChanged` on both histories and runs `_refresh_filter_choices`. It
    is deferred so it never runs inside the click that pushed the step. It
    is coalesced, so a macro or a run of steps asks once. It does nothing
    unless a strip is open, so no check hangs off every keystroke (see "Qt
    checks must be debounced").
  * **Right-click Move to category moved ticked clippings the filter hid.**
    Measured: 1, 4 and 10 ticked, Hindustan Times picked (only 10 shown).
    Right-click 10, Negative: all three moved, "Moved 3 clippings", and the
    submenu gave no count. The bar's Move to refuses under a filter, but
    right-click moving under a filter is pinned in section 18, so it stays.
    Under a lens the board's menu now files only the ticked rows on screen,
    or the row clicked when none of those is ticked. The submenu is titled
    "Move these N to category" when N > 1. `_fill_category_actions(hidden=)`
    adds a greyed "2 more ticked are hidden by the filter and stay here".
    Exclude and Delete in the same menu still act on every tick and say the
    count, as the navy bar does, and the press report's menu is unchanged.

Traps met on the way:

  * probe_pick and probe_r2 A4 pressed the move pad after the move and then
    one Ctrl+Z. The move pad was refused under the stale filter, so it pushed
    nothing. With the fix it works, pushes a step, and that Ctrl+Z undoes it
    instead of the move. The probes then report the chip "not back", and
    probe_pick hits StopIteration looking for 18. Run in a clean order
    (review/D2/r2fix/probe_nopick.py) the chip goes and comes back.
  * test_resize (window wider than the offscreen desktop, cover card at
    1024px) and test_scroll (two Shift+wheel/top checks) fail 2 each on this
    machine. They fail the same 2 on the untouched 2.0.31 tree
    (review/D2/r2/suites_tree_head), so they depend on the offscreen screen,
    not on this work. Round 1's 35/0 and 15/0 were measured elsewhere.
  * Several suites write their summary to a results file beside the suite
    (resize_results.txt, split_results.txt, deg360_results.txt, ...) and
    print nothing. A runner that reads stdout only reports "no summary".

Pins changed on purpose: test_focuslist 15's "with three ticked it speaks of
the three" also expects "Move these 3 to category". Round 2 added 25 checks at
the end of section 18.

Results after round 2: test_focuslist 341/0, test_sentiment_ui 74/0,
test_resize 33/2 and test_scroll 13/2 (the same failures as at 2.0.31),
test_workarea 24/0, test_fluid 13/0, test_independent 23/0, test_english
49/0, test_dropflow 17/0, test_headerbits 23/0, test_360 60/0,
test_filter_roundtrip 48/0, test_batchbar 108/0, test_split_pools 26/0,
test_board_send 23/0, test_foldall 18/0, test_boardfields 33/0, test_cards
16/0, test_four 27/0, test_notsaved 10/0, test_carryforward 48/0.

### Round 3: a strip rebuilt for nothing, a menu that disagreed with itself

Five findings as filed, three problems, each reproduced first with the
reviewers' probes in review/D2/r3 (perf2_r3.py, probe_r3.py parts menu and
report, rv3_menu.py, rv3_merge.py). Before and after are in review/D2/r3fix.

  * **An open strip rebuilt every chip after every step.** Round 2's
    `_offer_timer` runs `_refresh_filter_choices` whenever either history's
    index changes. `FilterBar.offer` then deleted and remade every chip, with
    two style sheets each and the FlowLayout laid out from nothing. It did
    this although a headline, a rotate or a Ctrl+Z changes no paper and no
    count. So round 2's note that the timer "does nothing unless a strip is
    open" was true, but with a strip open it did a lot. Measured with
    perf2_r3.py, median of 12 Enters in a headline box, strip shut then open:
    report of 60 rows 12 then 131ms, 240 rows 17 then 139ms, board Positive
    of 112 rows 27-37 then 140ms.
    Fix: `PickList.offer` and `RankList.offer` keep the (value, count) list
    they last built from, and return at once when given the same one again.
    `_paint` sets a sheet only when it differs. A pick cannot go stale while
    nothing on offer changes, because a pick is only ever made from a chip
    that was offered. So round 2's drop and hand-over still run whenever
    they matter. The check is per row, so a changed paper rebuilds the
    newspaper row only. `RankList` still repaints when it returns early:
    `_order_changed` empties `ranked` before offering, and choosing the
    arrangement already lit offers the same values again.
    After: 60 rows 13 then 14ms, 240 rows 19-21 then 21ms, board 35 then
    34-39ms.
  * **A category's right-click menu acted on two sets of clippings under a
    filter.** Round 2 made only Move to category follow the screen.
    `ids = ticks or [clip_id]` still fed Exclude, Set newspaper, Set edition,
    Merge and Delete. Measured with rv3_menu.py: Hindustan Times picked, only
    clipping 1 ticked (so hidden), right-click on 15. Exclude and Set
    newspaper changed 1, while Rotate, Delete clipping and Move to category
    acted on 15. With probe_r3's menu part: two hidden ticks, right-click on
    25, and "Delete 2 clippings" removed 1 and 4 but left 25. With
    rv3_merge.py, "Merge these 3 into one" joined two hidden clippings.
    Fix, on the board only: under a lens the menu works out its clippings
    once, as the ticked rows on screen or else the row clicked, and every
    entry takes them. The labels name them, as "these 2", or as "the ticked
    one" when a single tick elsewhere is the target. That second form is
    needed because Open full size, Split and Rotate still take the row under
    the mouse. How many ticks the filter hides is now one greyed line at the
    top of the menu, not a line inside the category submenu. Merge is greyed
    "(clear the filter first)", as the row's merge pill is. Deleting several
    goes through the new `_delete_many(ids, pool)`, which `_batch_delete`
    now calls with its ticks.
    After: in rv3_menu.py every entry acts on 15. In probe_r3, Delete on 25
    removes 25 without asking. rv3_merge.py is offered no Merge, since there
    is one target.
    Left as they were: the press report's menu is still ticks-or-row, as at
    2.0.31, so with one tick elsewhere its Exclude takes the tick and its
    Delete takes the row clicked. The navy bar's Merge still joins every tick
    under a filter, in both lists, as the report's always has.
  * **The press report let a pick go when its paper's last clipping was
    deleted.** Measured with probe_r3's report part. In 2.0.31 'Solo Paper'
    stayed lit over an empty list, and Ctrl+Z came back into the filter. In
    the working tree the list shows all 29, and after Ctrl+Z all 30, with
    the paper offered but not picked.
    Not reverted, because it is round 2's rule reached one more way. The
    pick already lets go when that clipping moves category, is put in
    English (pinned for the press report in round 2) or is given another
    paper. Keeping it for a delete alone would give two answers to one
    question. The other way out, leaving every lit pick offered at 0, would
    reverse round 2's board pins and leave lit empty chips behind. So the
    change is kept on purpose. changes.md's entry now includes a delete and
    says that Ctrl+Z offers the paper again without putting its filter back.
    test_filter_roundtrip section 12 pins this on a real morning.

Traps met on the way:

  * test_stripcost's heartbeat under-reads a single Enter. The
    `processEvents()` inside the measured Enter fires the heartbeat timer
    too, which splits the gap in two. So the suite also compares the median
    Enter with the strip open against the strip shut. With the fix switched
    off in memory (review/D2/r3fix/stripcost_without_fix.py) it fails 10:
    the six chip-identity checks and four timings. The report's Enter was
    363ms open against 19ms shut, its worst gap 307ms, and a rotate 319ms.
  * test_focuslist's modal closer shuts any modal box after 150ms. So the
    new Set newspaper checks find and answer the board's picker straight
    after `trigger()`, with no wait between, as round 2's Set edition check
    does.

Pins changed on purpose: in test_focuslist section 18, "the submenu ... says
two ticked stay" now expects the line at the top of the menu and none in the
submenu. Added: 14 checks at the end of test_focuslist section 18
(`section_d2_review_menu`), 4 in test_filter_roundtrip section 12, and the new
test_stripcost.py (22).

Results after round 3: test_stripcost 22/0, test_focuslist 355/0,
test_filter_roundtrip 52/0, test_sentiment_ui 74/0, test_resize 35/0,
test_scroll 15/0 (both passed in full on this run; round 2 saw 2 failures in
each that depend on the offscreen screen), test_workarea 24/0, test_fluid 13/0,
test_independent 23/0, test_english 49/0, test_dropflow 17/0, test_headerbits
23/0, test_360 60/0, test_batchbar 108/0, test_split_pools 26/0,
test_board_send 23/0, test_foldall 18/0, test_boardfields 33/0, test_cards
16/0, test_four 27/0, test_notsaved 10/0, test_carryforward 48/0.

## A category as the report's list: arrivals, the preview, duplicates (2.0.32)

Step D3 finishes the focused list. What the whole feature rests on, from the
sections above, in one place:

  * **The scope is a view projection**, beside the lens: `ClipModel.scope`,
    set only on the board's pool while a category is opened, never saved,
    never undoable, never read by an exporter. The board's rule is one
    function, `sentiment.shows`.
  * **The weave**: every gesture that decides an order is worked out over the
    category and woven back into the slots the category already holds, inside
    the commands helpers, so nothing in another category or division moves and
    undo is exact whatever is open when it runs.
  * **Bracket identities carry the scope's tag**, so a fold in Positive is not
    a fold in Negative.
  * **`headings_print` is off on the board's pool**: the dossier prints no
    section headings, and the SOCIAL MEDIA chips and refused moves went with it.
  * **The layout**: the list stands at its content's height in the board's
    page, under the category's header held to its own height, so everything
    that scrolls scrolls the page.
  * **`_list_pool()`** is the report's pool in its interface, the board's while
    a category is open, and None over four columns - which is what keeps every
    "the bar belongs to the report" guard true there.

### Arrivals

`_focused_section()` is the category opened, or None. Three routes fall back to
it when nothing under the pointer names a column: `_stamp_pending` (a paste, a
drop, the header's Add), `_native_files_dropped` (a browser drag let go over the
header or the page's margin), and the window's own `dropEvent`. A drop on the
list itself already went through its `drop_section`.

  * `_stamp_pending` cannot tell a picture's default Neutral from a column
    somebody chose, so the two arrivals that choose their own column arm it
    first: Collect (its options' column, else the one opened, else Neutral)
    and a captured link (Social or Digital). Without that, Collect's "Board
    column: Positive" with Negative opened, and every captured link, would
    have been filed in the opened category. Both put back a column a board
    button armed, as Collect always did.
  * `_add_loose` uses `scoped_insert_point` only when every arrival is held by
    the scope. A photo Collect's options send to a hidden category goes where
    the pool's own rule puts it; put at the opened category's loose place it
    would have landed among another category's clippings. In an empty category
    the scoped point falls back to the pool rule, which keeps test_collect 42.
  * Measured on the suite's fixture, Negative in Delhi: the category's loose
    place is 2, the pool's 19. Paste, a drop on the list, a browser drag over
    the list, one let go over nothing, one let go on the window and the
    header's Add all land at 2, with the box open in the list and the row on
    screen.
  * The board's rename route is still `board.begin_rename` (list-aware since
    D2), and `_add_loose` still names `_begin_rename` and
    `loose_insert_point`, which test_collect 44 and test_window_drop 6 read.
  * A photo Collect adds opens no box, in a category as in the report: the
    person is in WhatsApp and nothing may take the keyboard. It is brought into
    view in the list. A photo dragged in while Collect is on opens its box with
    "or copy its caption in WhatsApp", and the caption copied next puts the
    untouched box away through `settle_editors`.
  * A story link let go on the opened list still goes to the links window, and
    `accept_payload_into`'s finally lets the armed category go.
  * A captured link says where it went on the board: "No. 6 in Digital" when
    the list shows it, "into Digital - the board is showing only Negative"
    when it does not, "into Digital" over four columns. The press report's
    words are as they were (`number_of` is `position_of + 1` with no scope).
    Take from my Chrome and the links list follow the same rule.

### The preview

  * `PreviewDialog` is made once, with the pool that opened it first, and kept
    that pool for good. A board clipping's repeat was then looked for among
    the report's rows. `open_preview` now hands it the pool every time.
  * `_preview_walk` fell back to the whole pool when nothing was visible, so a
    category whose last clipping had just moved away counted every clipping on
    the board. Under a scope it returns what the category shows, even nothing.
  * `_preview_delete` under a scope shows the next clipping of the walk: the
    category's next, not the pool's. A row its Sentiment has just taken out of
    the category has no place in the walk; then it is the first walk row that
    stood at or after the deleted row's pool position, else the walk's last,
    and the preview closes when the walk is empty. With no scope (the press
    report, and a card's preview over four columns) it is the pool's own next
    row, filter or not, as in 2.0.31 - pinned both ways in test_focuslist 21:
    305 deleted shows 306 with no filter, and under a Hindustan Times filter
    that hides 306.

### The duplicate checks, over a category

Every report-list duplicate feature now works in an opened category, on the
board's pool and the board's history: the red badge and its hover, the red
bracket of a file repeating another, the repeat beside the preview, Check for
Duplicates, Preview and Delete Duplicates with its swap and Not a Duplicate,
and Check automatically.

  * **What is compared is the category, in the division on show.** The review
    deletes. A pair with one side in a category not on screen would delete a
    clipping nobody can see, which D2's review made every other list action
    stop doing. The same cutting filed in two categories is therefore not
    found; that would need a review able to show and move between categories.
  * **One background pass serves both lists.** `_duplicate_pool` says whose
    pass is running and `_duplicate_scope` which category it started over. A
    list that asks while the OTHER list's pass runs - by Check automatically
    or by its own Check for Duplicates button - is kept in
    `_duplicates_waiting` and asked for when it ends (`_pass_over`); before,
    it would simply have been dropped. The button says which list is being
    checked and that this one is next, and is answered out loud at its own
    finish. A request during its own list's pass is still dropped ("Already
    looking"), as the report's always was. A board request not started when
    the category changes is let go with its out-loud flag, whether it is still
    in `_duplicates_waiting` or already on the board's timer after the
    report's pass ended (`_let_board_request_go`, round 2): it was that
    category's. A pressed one says so; one overtaken in mid-pass says it was
    not finished. Measured with Check automatically on: the report's pass
    started first, the board's request arrived during it and waited, then ran.
  * **Check for Duplicates forgets what was read when its own pass starts,**
    not at the press (`_forget_readings`, flagged by `_fresh_report` and by
    `_fresh_board`, the Scope it was pressed over). Round 2 of the review.
  * **A category changed under a pass offers nothing.** The shortlist and the
    finish both compare the scope with the one the pass started over; what was
    read stays on the clippings, and the new category is asked about afresh.
    A scope change forgets the board's pairs, suggestions, file marks and
    button. Badges stay on the clippings, as the report's do across a restore.
    The category then opened is offered again the pairs its clippings' marks
    already name (`_offer_board_marks`, `duplicates.marked_pairs`): every
    clipping whose `duplicate_of` names another in the category, with nothing
    compared and nothing read, whatever Check automatically says. Those are
    exactly the pairs the badge and the preview's twin show, so the three
    agree; suggestions are not remade, the next check makes them.
  * The board has its own timer, asked by the board's history and by opening a
    category. Nothing is asked over four columns.
  * Check for Duplicates on the board answers at the first finish, whatever it
    read. The report's waits for a pass that read something, because an
    automatic pass may already be under way when its button is pressed. The
    board's button starts nothing while a pass runs: during its own it is
    already looking, during the report's it waits its turn, so the pass that
    ends with its answer is the one it asked for. The report's button pressed
    during the board's pass answers whatever its own pass reads
    (`_answer_even_if_nothing_read`), for the same reason: no automatic pass
    of the report's can be under way before it.
  * The board's review opens with `open()` and acts on `finished`. With
    `WA_DeleteOnClose` that is safe: `done()` emits `finished` before the
    deferred delete. It deletes only from the category's rows. The "no headline
    reader" box on the board also opens without waiting. The report's review
    and box still wait, as they did.
  * `_copy_back` and `_source_of` look through both pools. Every clipping's uid
    is its own, and a clipping is only ever in one pool.
  * The board bar's duplicate buttons are made by the same `_make_list_bar`.
    "Check automatically" is one setting in two boxes; each follows the other
    with its signals blocked. Every `clicked` goes through a lambda (D2's trap:
    `checked` arrives as the new `pool` argument).
  * The preview shows a board clipping's repeat only under a scope, numbered by
    the category and saying "the dossier keeps". A card's preview over four
    columns shows none, as before, so test_dupswap 4's last check holds as it
    was written.

Still the press report's alone: the **Duplicates Trainer** button in the header.
It labels pairs for the whole program and is not part of the list.

### Cost

On a 150-clipping board with Positive opened (test_focuslist 25): a headline
typed costs a 22ms median (21-32ms over five), a move 27ms. Opening or closing
a category resets the list once, with `_update_counts` never inside itself.

### Traps

  * A suite point taken at the list's own corner was off the page once a
    reveal had scrolled it, and `_section_under` answered for the bar there.
    The check now takes a point on the part of the list the page shows.
  * The suite's duplicate block uses a stand-in for the background reader: it
    takes real picture prints, returns headlines from a table, and answers on a
    timer, so the report's and the board's passes can be made to overlap on
    purpose. No Tesseract and no thread.

### Results

test_focuslist 459/0: 104 checks added in sections 19-25 (arrivals by every
route, Collect, the preview, leaving, the duplicate checks, exports and
sessions, cost); none of its earlier checks changed.

From the step's list: test_four 27/0, test_collect 82/0, test_collectscroll
29/0, test_collectoptions 237/0, test_window_drop 38/0, test_dropscroll 21/0,
test_webclip 110/0, test_weblinks 95/0, test_fromchrome 43/0, test_boardpicker
14/0, test_dossier 17/0, test_dossier_format 44/0, test_jpeg 39/0, test_burned
23/0, test_session 27/0, test_session_real 18/0, test_newspads 137/0,
test_newspads_kill 48/0, test_nofreeze 13/0 (run alone), test_carryforward
48/0 (the network-import pin),
test_duplicates 58/0, test_dupswap 31/0, test_sentiment_ui 74/0. The suites
the duplicate and bar changes touch: test_batch 27/0 (its pin that the report's
Check automatically sits beside Check for Duplicates), test_batchbar 108/0,
test_trainer_window 23/0 (`_source_of`), test_english 49/0, test_dropflow 17/0,
test_split_pools 26/0, test_board_send 23/0.

test_real_drop was 14/1 at the end of the step, in the batch and run alone:
section 7's "an editor is open". That was recorded here as the known flake. It
was not a flake: the review ran it alone three times and it failed every time,
4 of 4 with its batch. See "After review": its section 4 wrote the real
clipboard, and with that gone the check passes. Its eight win32com tracebacks
come from the suite's own stand-in data object (`QueryGetData`), as in D2's
rounds.

### After review

Six findings, all should-fix. Each was reproduced on the working tree first.

  * **Delete in the preview, after its Sentiment moved the row out, showed
    another category's clipping.** Reproduced with the review's probe A:
    Negative in Delhi is [2, 5, 17, 23]; 5 set to Positive in the preview,
    then Delete showed 6, a Positive clipping, at "0 / 3". Under a scope the
    pool's next row is never used now (see The preview); the same probe shows
    17 at "2 / 3".
  * **The press report's Delete in the preview under a filter had changed**
    without a word: the next row shown (310) instead of the pool's next (306,
    which the filter hides). Put back as 2.0.31 has it; the walk is used only
    under a scope. Kept as it was rather than improved, because nothing asked
    for the report to change.
  * **After a category change the badge and the preview said "flagged", and
    the review said nothing was.** Reproduced with probe I, Check
    automatically off: a pair found in Positive, the division changed to UMB
    and back (and, apart, the category closed and opened) - 0 pairs, no
    button, the copy still badged, and "Compare in the review" said "Nothing
    is flagged as a duplicate." Of the ways out, the pairs are rebuilt from
    the marks (`_offer_board_marks`). `duplicates.apply` over the category was
    not used: it takes the prints of any clipping without them on the window's
    thread (8.8ms a clipping, measured in core/duplicates) and re-marks, so
    with Check automatically off, opening a category would have flagged
    clippings nobody asked to be checked. Clearing the badges would have
    thrown away what a check found; hiding the review button would have left
    the preview saying "flagged" with no way to act on it.
  * **Check for Duplicates pressed during the other list's pass** said
    "Already looking", and that list was never checked or answered.
    Reproduced with probe G: the passes started were the board's prints and
    reading, and nothing of the report's. Now it waits its turn (see The
    duplicate checks); probe G shows the report's two passes after the
    board's, and both answers.
  * **test_real_drop wrote the real Windows clipboard** in section 4
    (`OpenClipboard`, `EmptyClipboard`, `SetClipboardData(CF_HDROP)`, then
    `OleGetClipboard` to borrow a system data object), on every battery run.
    Confirmed by reading it, and not run again in that form. The object is
    made by the shell for the sandbox file now (`SHGetDesktopFolder`,
    `ParseDisplayName`, `GetUIObjectOf(IID_IDataObject)`): the object Explorer
    drags, carrying CF_HDROP, in memory. Every clipboard call made from Python
    is refused and recorded, and a new section 8 checks that none was made.
  * **Its section 7 failure** was traced on a copy with the shell's object in
    section 4 (d3fix_realdrop_trace.py in the scratchpad), logging every open,
    commit and cancel of the report's box, every `_begin_rename` and every
    `set_mode`. Twice on the working tree and twice on the pre-D3 tree the log
    is the same: the folder drag's deferred rename commits box 2 and opens
    box 3 while the report's list is hidden behind the board, and box 3 is
    still open at section 7 and 1.5s later. The suite itself then passed 16/0
    three times run alone. So the failure needed the clipboard's data object.
    That variant was not run again, because it writes the clipboard, so what
    in it closed or delayed box 3 is not known; nothing in this step's code
    was on that path.
    (Round 2: wrong. The failure did not need the clipboard. It is a timing
    race that the shell's seven-format object made rarer, and the suite's
    section 4 input had been changed. See "After review, round 2".)

Traps:

  * A data object written in Python and forwarded into Qt corrupts the heap
    (the suite's own note), which is why section 4 wanted a system one. The
    clipboard is not the only place to get one: the shell makes one for any
    file, in memory.
  * `DuplicatesDialog` keeps the pairs it was given as `pairs`, which
    `_duplicates_reviewed` also reads; a suite that stubs `open` can capture
    what the review was opened on from there.

Results after review: test_focuslist 472/0, 13 checks added and none changed -
seven in 21 (Delete after the Sentiment moved a row out, at the category's
middle and its end, with their undos; the preview closing on an empty walk;
the report under a filter) and six in 23 (the pairs offered again, before and
after a division change, with the review opening on them; either button
pressed during the other list's pass; its own list's still already looking; a
waiting category request let go). test_real_drop 16/0 three times run alone,
section 8 added.

No pin in an existing suite had to change. test_dupswap 4's "the board's
preview never shows it" still describes a card's preview over four columns.
(Round 2 corrects this: test_real_drop's section 4 input had been changed.)

### After review, round 2

Six findings, all should-fix: five in the duplicate checks, one in
test_real_drop. Each was reproduced on the working tree first with the
review's own probes (review/D3/r2/body_dups.py K, K2 and M;
r2_whatbroke/probe_flash.py and probe_wipe.py), and the logs matched the
review's line for line. The same probes were run again after the fixes.

  * **A category's request that had waited for the report's pass answered for
    the next category.** Round 1 let the request go only while it sat in
    `_duplicates_waiting`. Once the report's pass ends, `_pass_over` puts it
    on the board's 400ms timer. Negative opened inside that time was checked
    out loud ("Checked 4 clippings in Negative"), and with Check automatically
    off it was read though nobody asked, while Positive was never checked.
    `_let_board_request_go` now also stops the timer. It clears the out-loud
    flag unless a board pass is under way, and says "Positive's duplicate
    check was not run: Negative was opened." Check automatically asks afresh
    for the category now on show. Probe K after the fix: only the report's
    two passes ran, nothing was said "in Negative", and Positive's readings
    and prints were intact.
  * **Pressing wiped the readings at once** (two findings, one cause).
    `check_duplicates_now` cleared every reading before the "wait for the
    other list" branch. A request dropped by a category change left its
    clippings with no headline and no prints, still paired, the hover saying
    "(nothing could be read)". Now the press only sets `_fresh_report` or
    `_fresh_board`, and `_run_duplicate_check` forgets when that list's own
    pass starts, over the category it was pressed in. Probe K2 and
    probe_wipe after the fix: the readings stayed through the press, the
    let-go and the report's pass.
    One path needed care to keep the press report as it was. A report press
    still waiting at a newspad switch is carried across as "loud", and the
    resumed check never forgets again. So `_settle_reader` forgets for it
    before the clippings are saved, which is what 2.0.31's press did.
    Left as it was: a pressed category check overtaken *in mid-pass* by a
    category change has already forgotten. Its prints pass takes the prints
    again, but the headlines are not read, because the shortlist refuses a
    changed scope. It now says "was not finished", and the next check over
    that category reads them (`to_read` picks clippings with no
    `ocr_engine`). Finishing the reading anyway would read clippings in a
    category nobody is looking at, which is what the first finding
    complained of.
  * **A pair with one side moved out of the category was still offered.**
    Probe M: the first copy's Sentiment was set to Negative in the preview.
    The button still counted the pair, and the review opened on it. Turned
    round and confirmed, it deleted nothing and said "Duplicates: deleted 1."
    It also recorded a verdict. `_board_pairs_on_show` keeps only pairs and
    suggestions with both clippings in `scoped_rows()`, both when the review
    opens and when the button counts. `_count_board_review` recounts after
    every step on the board's history, and returns at once when there are no
    pairs. The stored pairs are kept whole, so a Ctrl+Z bringing the
    clipping back offers the pair again. On the board, `_duplicates_reviewed`
    judges, spares and deletes only clippings in the category, and "deleted
    N" counts the rows actually removed. Probe M after the fix: the pair was
    not offered and the button counted the 25 suggestions still in the list.
    The probe's swap deleted one of those, one board step, so "deleted 1" was
    true.
    Not changed, by reading the code only: the press report has the same
    shape. A pair whose clipping was deleted with Check automatically off
    would still say "deleted 1". It is left as 2.0.31 has it, because this
    step keeps the report's behaviour.
  * **A category's automatic answer was said on the press report's strip.**
    `_flash` writes to the strip of whichever screen is on show, and a bare
    "No duplicates found." there read as the report's answer. The quiet branch
    of `_finish_board_check` now speaks only while the board is on show, and
    names the category ("No duplicates found in Positive."). Its "Looking at N
    clipping(s)…" and "Reading clippings… n of m" are not said either for a
    quiet category pass while the report is on show
    (`_quiet_board_pass_off_screen`). probe_flash after the fix: nothing was
    said on either strip, and the pairs were still found. Left as 2.0.31 has
    it: the report's own quiet answer still lands on the board's strip when
    the board is on show.

  * **test_real_drop's section 4 input had been changed, and that hid a
    race.** Round 1 swapped the clipboard's data object (CF_HDROP alone) for
    the shell's object for the file (`GetUIObjectOf`, seven formats), and
    blamed the clipboard for the failure. The review rebuilt the old shape
    with no clipboard (`SHCreateDataObject`, then `SetData(CF_HDROP)`), and
    section 7 still failed 2 of 9.
    Measured here with the review's probe, on a copy of the reviewed tree and
    on the pre-D3 tree in turn, one windowed run at a time. Idle, 0 of 10 on
    each. Under 11 busy processes, 2 of 10 on D3 and 0 of 10 before it.
    In the failing runs, section 4's ten `processEvents` outlast the 80ms
    `_begin_rename` wait. Box 3 opens inside them, and section 5's `set_mode`
    commits it.
    To see whether D3 moves that, probe_realdrop_timed.py timed the Drop call,
    the ten pumps and the time from Drop to the box opening, on both trees:

                 Drop      pumps     box opens after Drop
      idle   D3  50.5ms    49.3ms    89.9ms
             pre 49.6ms    47.6ms    93.4ms
      load   D3  73.2ms    66.8ms    90.8ms
             pre 73.1ms    66.9ms    86.8ms

    The same on both trees (medians of 10), so D3 does not shift the race.
    The gap between the end of the pumps and the box is about 40ms idle and
    about 20ms under load. With the review's runs that makes 4 of 19 failing
    against 0 of 18, which is not significant (one-sided p about 0.06).
    The fix: section 4 uses `SHCreateDataObject` with CF_HDROP alone, and a new
    check says the object offers it. The suite then waits up to 3 seconds for
    the box on the last arrival before section 5, and section 7 checks that
    ("an editor is open on the last arrival", renamed).

Trap: `_sync_board_scope` reuses `was` for the filter bar's `blockSignals`.
The first version of the fix kept the old scope in `was` and so passed a bool
on. Every let-go raised AttributeError (test_focuslist 482/4; the probe
counted 2 exceptions, which the harness's excepthook swallows). The variable
is `left_scope` now.

Results after round 2: test_focuslist 486/0. It gained 14 checks and changed
none. Three sit in 23's existing blocks: the report's and the category's
readings kept while waiting and measured from scratch when their own pass
starts, and the let-go said with nothing forgotten. Eleven are in a new
round-2 block: the request on the board's timer let go and said, its
readings kept, the pair out of the list not counted or offered, a review
closed after one side left acting on nothing, Ctrl+Z counting again, the
quiet answer silent over the report and naming the category on the board,
the pairs found again, and a report press settled by a newspad switch.
The review's probes K, K2, M, Z, probe_flash and probe_wipe re-ran clean,
with 0 exceptions. test_real_drop 17/0 in 20 runs of 20, ten idle and ten
under 11 busy processes: one check more (the data object carries CF_HDROP),
and section 7's check renamed as above.

The whole battery, every suite's newest copy one at a time, passed 108 of 108.
From the step's list: test_four ok, test_collect 82/0, test_collectscroll
29/0, test_collectoptions 237/0, test_window_drop 38/0, test_dropscroll 21/0,
test_webclip 110/0, test_weblinks 95/0, test_fromchrome 43/0,
test_boardpicker 14/0, test_dossier 17/0, test_dossier_format ok, test_jpeg
ok, test_burned ok, test_session ok, test_session_real ok, test_newspads
137/0, test_newspads_kill 48/0, test_nofreeze 13/0, test_carryforward 48/0,
test_duplicates ok, test_dupswap 31/0, test_sentiment_ui 74/0. Also
test_embedded 196/0, test_real_drop 17/0 (its eight win32com tracebacks come
from its stand-in data object, as before), test_cards ok and
test_collect_quietlinks 13/0; the review's own battery had those last two
failing, and both pass here.
No other pin in an existing suite changed. The suite checks added are
test_focuslist's 14 and test_real_drop's CF_HDROP check.

## Clearing with a category open (2.0.32)

The completeness audit (gap 6.46) found that nothing showed what Clear all,
and step 2's Add buttons, do while a category of the board is opened out.
Measured with probe_clearall_focus.py on test_focuslist's fixture. The board
held 30 clippings, Negative in DLI listed 4 of them (2, 5, 17, 23), and the
board showed 24 in DLI.

  * **Step 2's card is not on the board.** Clear all, Add photos, From Word,
    From PDF and From links are all on the press report's page of `pages`.
    With a category open, `import_card.isVisibleTo(window)` is False and so
    is each button's. The only clear anybody can press there is the board's
    own Clear this division, which is in the export row under the page and
    stays on show.
  * **Clear all, reached by a call, emptied the whole board.** `_clear_all`
    acts on `pool()`, which is the board's pool while the board is on show.
    It asked "30 clipping(s) will be removed from the list" over a list of
    four and removed every clipping in every division, as one board step.
    Nobody can press it there, but a whole-pool wipe is the wrong answer
    to pin. So while the board is on show it hands over to
    `_clear_division(board.active)`, the board's own clear, with the board's
    own question. The press report's Clear all is unchanged.
  * **Clear this division over a list of four asked about 24.** It uses
    `board.visible_clips()`, which is all four columns whatever is focused.
    It removed the 24 and left UMB's six (8, 12, 13, 22, 27, 28). Negative
    stayed open with an empty list, and Ctrl+Z was exact. It still clears
    the division: that is the button's name, and a morning is compiled
    division by division. Clearing one category is already Ctrl+A and Delete
    in its list. What changed is the question. With a category open it adds
    "That is every category in it, not only the 4 in Negative on show."
    The 4 is counted with `sentiment.shows` over the clippings about to be
    removed, not the pool's scope, so the number cannot disagree with the
    board. Over four columns the question is exactly what it was.
  * **"from __all__".** `_clear_division` compared the code with "ALL", but
    the board holds `sentiment.ALL_DIVISIONS` ("__all__"). With every
    division on show the question named the division "__all__". It now
    compares with the constant and says "the board".
  * **Add photos was already right.** Reached by a call with Negative open,
    `import_paths` → `_add_loose` → `_stamp_pending` filed the picture as
    Negative in DLI, at `scoped_insert_point()` (2). That was one board step,
    with the box in the list. It is now pinned alongside the header's Add.

Traps:
  * `QPushButton.click()` fires on a hidden button. That is how the probe
    and the suite reach step 2's handlers from the board. So a click proves
    nothing about what a person can reach; the visibility check does.
  * test_focuslist's `QMessageBox.question` stub records only "q". Section
    26 swaps in a recorder for the wording and puts the stub back in its
    `finally`.

Results: test_focuslist 503/0. Its new section 26 added 17 checks and changed
none; it runs after 25 and puts both pools and both histories back.
test_sentiment_ui 74/0, test_split_pools 26/0, test_board_send 23/0. No
existing suite pinned Clear all or Clear this division, so no pin changed.


## "Show it in its folder" opened Documents (2.0.32)

2.0.31's `ExportDialog._show_in_folder` ran
`subprocess.Popen(["explorer", f"/select,{path}"])`. Given a list, Python
builds the command line itself and quotes any argument with a space in it -
and the report is always named "PRESS MEDIA COVERAGE OVER NORTHERN RAILWAYS
<date>", so the whole switch went to Explorer as
`"/select,C:\...\PRESS MEDIA COVERAGE ... .pdf"` (measured with
`subprocess.list2cmdline`). Explorer does not read a quoted switch and opens
its default folder, Documents, whatever folder "Save into" named.

Now the shell's own `SHOpenFolderAndSelectItems` is called through ctypes
(`export_dialog._select_in_explorer`): `ILCreateFromPathW` takes the path as a
path - spaces, commas and all - and the folder opens with the file selected.
The path is resolved first, so a relative "Save into" still works. When the
shell cannot select it, the folder itself is opened with `os.startfile`, never
Documents. COM is already initialised on the window's thread; the call only
balances what it adds. test_summary pins the file chosen, the relative path,
the fallback, and that the shell finds a report whose folder and name both
have spaces - without opening an Explorer window on the person's screen.


## What the office's own verdicts changed about duplicates (2.0.33)

The Duplicates Trainer (2.0.22) exists so pairs near the rule's boundary can be
labelled by the people who compile the report. Two mornings of labelling came
back - `ClippingsManager-training-471539c9-20260911.json` and
`...-7a258095-20260913.json`, 117 pairs, 12 of them the same cutting twice.
Replayed through the rule as it stood: **7 of the 12 found, and 9 pairs wrongly
flagged.**

Every one of those 9 wrong flags was two cuttings out of ONE division's own
document. Every one of the 12 real repeats crossed documents. Not a coincidence:
a division that pastes two cuttings into its file has already decided both
belong in the report - the same story in two papers, or one paper's two
editions - while the repeat this check exists for is the same story arriving in
two divisions' files, or pasted in by hand against a file.

So the rule is now in three parts (`core/duplicates.py`):

  * `one_document(a, b)` - the same real file (`.docx`, `.doc`, `.docm`,
    `.pdf`, `.rtf`). The words are not consulted for such a pair at all.
    "clipboard", "link" and "board" are NOT documents: two pastes of one
    photograph are the repeat the collect screen makes most often, and a naive
    "same source name" rule would have thrown that away.
  * `certainly_same(a, b)` - 8 apart out of 64 on the whole picture AND 40 out
    of 256 on the fine print AND the ink within 0.12. The three labelled
    repeats with no readable words sit at (0, 2), (2, 7) and (2, 10); the
    nearest labelled non-repeat is (12, 71). This needs no headline, so those
    three are found, and found before the OCR pass has started.

    The ink gate was not in the first cut of this and the OLD duplicates suite
    caught what was missing, which is the case for keeping suites that were
    written for a rule that has since changed. A difference hash describes
    where a cutting's columns and photograph sit; a picture with no structure
    in it - a photograph of a platform, a scan that came out nearly blank - has
    nothing to describe, so two unrelated ones land 6 apart on the whole
    picture and 36 on the fine print, inside both numbers above. Their ink is
    0.217, while the four labelled repeats this rule settles measure 0.000,
    0.013, 0.041 and 0.075. Set at 0.12, and it costs none of the 12.
  * the words, across documents only, with the picture gate widened from
    28/31 to `PICTURES_APART` 32 / `LOWER_APART` 34. Two known repeats sit at
    30 and 33; the nearest cross-document non-repeat is 34. The widening was
    only affordable because the pairs the old numbers protected against were
    all same-document pairs.

Scored on all 117: **12 of 12 found, none wrongly flagged.**

One repeat needed a fourth thing. Its two copies read 111 characters of
headline each, at confidence 79 and 57, agreeing at 99.1 - and `ocr.Headline`
calls anything under 60 unusable, because a masthead read at 45 once matched a
different cutting from the same paper at 98. The line is right and it stays;
`_worth_the_words` admits a reading below it only when both readings are at
least 60 characters, neither is under 45 confidence, and the plain ratio is 95
or better. Of the 117 pairs that admits exactly that one.

`Pair.by_picture` says how a pair was found, because "100% of the same
headline" over two cuttings whose headlines nobody could read is a lie about
the evidence - and the review screen is asking somebody to trust it.

**Quickness.** The reading list (`to_read`) is now the clippings that resemble
something in ANOTHER document, closely but not certainly. Measured:

    what is imported                     read before   read now
    one division's file, on its own        39 of 39      0 of 39
    the same, Moradabad's                  36 of 36      0 of 36
    the same, Lucknow's                    34 of 34      0 of 34
    all six divisions, one morning        175 of 175   175 of 175

A file on its own is the commonest import there is and now reads nothing -
about twenty seconds of Tesseract a file. A whole morning still reads
everything, which is honest: with six files in the list nearly every clipping
resembles something in somebody else's file. And on the 6 September corpus,
where every division exists as both .docx and .pdf, 86 repeats are now flagged
with no headline read at all. `imageops.pictures_apart` parses each print once
a morning instead of once a pair (`_as_number`, an lru_cache).

`core/training.py` reads the rule's own gates rather than a copy of them, so
the trainer keeps asking about the edge of the rule that ships.

## Importing the program's own report: it was the summary page (2.0.33)

A report exported by this program and imported again came in with all 180
clippings flagged "probably not a clipping" and every tick cleared
(`ui/model.make_rows` clears the tick of anything flagged). 2.0.27 had already
taught the importer to know its own files by their metadata stamp and to drop
the size and shape rules for them, and it made no difference.

The cause was one line on the last page:

    Coverage summary
    By kind
    Print     146
    Digital    29        <- read as a section header

"Digital" is a section name, so `build_clips` took that line for the document's
first section header - and a picture above the first section header is a
letterhead, not a clipping. Every picture in the report is above the last page.
The coverage summary page went in at 2.0.31, which is exactly when this
started, and it happened in the Word report too, word for word.

Three changes:

  * **A header with nothing under it is not a header.** `build_clips` only
    counts a section header that has a picture after it somewhere. General,
    and nothing to do with our own files: a stray word in a sign-off could
    always have done this.
  * **`core/ourfiles.py`** knows the three things our reports print that are
    not clippings - the cover, the page numbers, the coverage summary - and
    marks those events as furniture before anything is read. Furniture is not a
    caption, not a section header, and its pictures are not clippings. The
    words it looks for are imported by `build_pdf` and `build_docx` from the
    same module, so the two halves cannot drift.
  * **The file is recognised by its own pages as well as its stamp**
    (`looks_like_ours`), so a report made before the stamp existed, or one
    that has been through a tool that rewrote the metadata, is still known.
    Both exporters now write a second stamp into the keywords as well.

The cover is not "page 1". The sentiment dossier opens on its first category,
headed "Positive News", with the first clipping under it - taking that page for
a cover threw a clipping away and lost the heading with it. A cover page says
what it is: it prints the count and the date, or it is one picture and no words
at all (a cover with its words baked in).

Two more things the round trip needed. The page number at the foot of a sheet
was being read as the front of the next caption ("1 Hindustan Times, Lucknow,
Page 2"); it is furniture now. And every heading printed in one of our reports
comes back on the clipping it headed - `build_clips` treats our own files as
"titled", where a division's document only carries the headings the config
names - so a re-imported report can be rebuilt with its sections intact.

Measured, on a report of 8 clippings exported both ways, with a cover picture,
printed headings, page numbers and a summary page, and again with the stamps
stripped off: 9 pictures in, one flagged and it is the cover, 8 of 8 named with
their page, sections and heading words restored. The sentiment dossier: 8 of 8,
each under its own category, nothing flagged. A division's own document is
untouched by all of it.

## Five priorities, and why a band is a scope (2.0.33)

The department asked for five bubbles in the preview window that move a
clipping up and down the list, with every 1 above every 2 and so on, strictly.

`Clip.priority` is 1 to 5 and starts at 3. That matters more than it looks: a
list nobody has set a priority on is ONE band, the whole list, so every helper
below does exactly what it did before this existed, and `banded()` - a stable
sort by level - is the identity on it.

The ordering helpers treat a band the way they already treat a category of the
board: `in_levels` reorders one level's rows and lays them back in the slots
that level already holds, which is `_weave` for priorities. So the arrows, the
move pad, "move to top" and a file's own arrows all move a clipping inside its
own level and no further - the department asked for ten clippings at priority 1
that can still be put in any order - and no other row, bracket or heading is
disturbed.

A drag and drop is the one gesture that changes a level, because a drop says
"put it here" and here has a priority (`level_at`, where the row ABOVE decides,
since a clipping is dropped underneath the one it was dragged past). Without
that the list would come out of level order the moment anybody dragged a card
past a boundary. It is one undo step: `SetPriority` is a `Reorder` that also
carries the levels, because a clipping at priority 1 sitting among the 3s is
the one thing this feature must never produce.

Arrivals: `AddClips` re-bands after inserting, stably, so a new clipping keeps
the place it was given among its own level and sits above the 4s and 5s rather
than at the very bottom.

**The walk does not follow the clipping.** Somebody going down a morning
setting priorities is at a place in the list, not on a clipping: sending them
back up to wherever it landed means the next arrow walks the same clippings
again. So `_preview_priority` remembers the row that was BELOW before anything
moved, and the next forward arrow goes there - once, and only forwards. A step
back, or opening another clipping, walks the list as it now stands.


## The list is a sort (2.0.34)

2.0.33 gave the five priorities a middle resting place (3) and let each level
keep whatever order the person arranged inside it. The department asked for
something simpler and stricter, in their words:

    The visible list is always produced by sorting -
    Priority (highest first), ImportOrder (original import order as a stable
    tie-breaker). 0 = Unassigned (meaning import order). Show all Priority 1..5
    items first, then keep Unassigned items at the bottom, in pure import
    order. Clicking the already-selected bubble can reset to Unassigned.

So `Clip.priority` is 0 to 5 with 0 meaning none set, `Clip.order_seq` is the
arrival number, and `core/models.list_key` is `(priority or 6, order_seq)`.
`ClipModel.rows` is kept sorted on that key at all times - it is not an
arrangement of its own any more - and every gesture that moves a clipping goes
through one command, `commands.Arrange`, which writes the priority, the arrival
numbers and the order together.

**Two numbers, two jobs.** A priority never touches the arrival number, which
is what makes "press the lit bubble again" put a clipping back exactly where it
came in rather than at the top or bottom of the unassigned run. A move by hand
never touches the priority: it gives the moved clipping a number between its
new neighbours' numbers (`commands.arrivals_for`), so the sort reproduces the
arrangement, and nothing else in the list is renumbered.

**A drop only changes a priority when the place asks for it** (`level_at`).
The list is sorted, so most drops land somewhere the clipping could sit anyway:
at the top of the unassigned run, say, with the last priority 5 above it.
Reading "the row above" as the answer made that a demotion to 5. Now the
clipping keeps its own priority whenever its own priority still fits between
the neighbours, and takes the place's only when it cannot - dropped in among
the 1s it becomes a 1, dragged down into the unassigned it loses its priority.

A session written by 2.0.33 carries priority 3 on every clipping and means
nothing by it. `session.decode_clip` reads a 3 with no arrival number beside it
as "no priority", which is the only build that combination can have come from.

**The bubbles.** They were pills on a white block: the application's own sheet
paints every plain widget the page colour, so the holder behind them was white
inside the preview's dark bar, and the global button padding stretched the
circles into ovals. They are 24px circles now with `background: transparent` on
the holder, an outline until chosen and filled in their own colour when they
are - and the size is the widget's own (`setFixedSize`), because a `min-width`
in a stylesheet is the content box and the border made the circle two pixels
wider than its radius.

## What the fixtures caught about the picture rule (2.0.34)

2.0.33's "the picture alone settles it" gate was 8 of 64 and 40 of 256, set
midway between the labelled repeats (0/2, 2/7, 2/10) and the nearest labelled
non-repeat (12/71). Two suites written years apart found what those 117
labelled pairs could not say:

  * `test_focuslist`'s board fixture uses 40x30 blocks of flat colour. A flat
    picture has no part darker than the part beside it, so its difference hash
    is all zeros - and so is every other flat picture's. Fourteen fixture
    clippings came back as twelve repeats.
  * `test_duplicates` draws cutting-like pictures: a masthead band and eight
    lines of type whose lengths vary. Two DIFFERENT ones measure 7 apart on the
    whole picture and 19 on the fine print, inside that gate.

Both are fair warnings about real material - a mostly-white cutting, an advert,
a screenshot of an empty page - so the rule now has a floor as well as a
ceiling. `LEAST_DETAIL` refuses a picture whose fine print sets fewer than 24
of its 256 bits (real cuttings set 105 to 132; a photograph of gentle gradients
sets 112; a flat block sets none), and the gate itself is 4 and 16, which every
labelled pair still scores 12 of 12 on with none wrong.

**And the battery was reading only exit codes.** Most suites print "N passed, M
failed" and never call sys.exit, so a suite could report failures and be
counted a pass. It now reads the tally as well, which is how both of these came
to light at all.


## Settings, the corner menu, and measurements that went stale (2.0.36)

The morning this was asked for, the duplicate check missed copies that were
plainly the same picture. The check keeps what it measures about each clipping
- the picture prints, the ink profile, the headline read off it - because
measuring is the slow part. Trimming (`SetCrop`) and turning (`Rotate`) changed
the picture and kept the measurements, so a trimmed clipping went on being
compared as the picture it used to be; captures from Chrome are trimmed as a
matter of course. Only "Check for duplicates now" ever forgot them. Both
commands now call `duplicates.forget_measurements`, undo included, and the
next check measures afresh.

Settings > Clean up (`ui/settings_dialog.py`) is the same forgetting for every
clipping at once, both pools, plus the browser's page cache (never its
`storage`, which holds the sign-ins), `QPixmapCache` and the parsed-print
cache, and the program's own temporary files matched by name
(`TEMP_FILES`, `TEMP_FOLDERS`) so nothing of anybody else's can be caught. It
feeds the rule; it does not touch it.

The top bar now holds only the newspad, the report switch and Collect, and
fits one line at 1366 (98px, from 120px). The Duplicates Trainer, the zoom and
Runs offline moved into the menu at the top left. Their buttons are still
made, connected and named - suites and the window use `zoom_label`,
`zoom_buttons`, `trainer_btn` - but they live in `_parked`, a holder that is
never shown, so nothing that shows one can put it back on the header. The
NEWSPAD and INTERFACE captions are gone: each control says what it is.


## The newspaper list is kept, as changes (2.0.37)

Collect names a photo from its caption only when the caption starts with a
listed paper, and the list was the 56 papers in `config/newspapers.json`. A
paper from another state was refused, and a name typed by hand lasted until
the program closed (`NameIndex.add_newspaper` never saved). Manage Newspaper
List (`ui/newspaper_list.py`, on Collect's right-click menu) edits both lists,
newspapers and cities; `core/paperlist.py` keeps them.

**Only the changes are written** - `newspaper_list.json` in the settings
folder holds `added`, `changed` (with `was`, the shipped name) and `removed`
for each list. The shipped file is read fresh and the changes laid over it, so
a paper a later version ships still arrives. An entry nobody edited is the
very `Entry` it was filled from, so opening and saving the editor writes no
change.

**The merge keeps the shipped order, and must.** `NameIndex._best` settles an
exact tie by whichever name comes first, and the cities in the shipped file are
not alphabetical. The first merge sorted, which would have changed how a
document's caption resolves on every machine, list edited or not. Now changed
entries stay in place and added ones go at the end; the editor sorts only for
display, and `test_newspaperlist` pins that an unedited index is identical to
the loaded one, order included.

Names typed into a clipping stay session-only on purpose - a typing slip saved
for good would be read as a newspaper every morning after. `set_newspapers`
keeps them for the session when the list is replaced, and the editor offers
them (`typed_newspapers`, "Add them to the list") rather than saving them
unseen. The editor opens with everything the reader knows - the shipped list
with the saved changes, and the reader's own short forms (`copied.SHORTHAND`,
shown and searchable, never written, so they cannot be removed by mistake).
One search bar at the top filters both lists and turns to the list that has
the match.

Collect's right-click menu went from about thirty lines to five: Manage
Newspaper List, Same newspaper for every photo (was "Newspaper, city, page and
division for this session…"), Options for this session (every option, as it
was, in one `StayOpenMenu`), What was copied, Reset. Clear only appears while
photos are being named.


## A fifth category, a print order, and where "next" comes from (2.0.38)

**Advertisement.** `sentiment.COLUMNS` is the one list the board, the buckets
and the dossier are built from, so the category itself was one line; what it
cost was everything that had assumed four. The card's Move: chips were three
hard-coded names (`{"Neu": ..., "Neg": ..., "Dig": ...}`) laid out at fixed
positions with the card's own chip skipped, leaving a hole - now
`moves_to(section)` builds them from the columns and `card_geometry` takes the
section so paint and hit-test agree. The chips size themselves to the room
between the word "Move:" and the two buttons, and drop the word when even that
is short, because a column is narrower with five of them: the minimum went from
275 to 250, which is what lets all five stand side by side on a 1366 laptop
instead of the fifth sitting behind a sideways scroll. `ADVERTISEMENT` came out
of `FOLDS_INTO_DIGITAL`, so anything already filed as an advertisement moves
into the new category on its own.

**Print order** (`ui/print_order.py`, `sentiment.printing_plan`). The order and
the switches live with the dossier's other layout settings
(`heading_sentiment.json`, so per newspad and carried by the backup) and reach
the exporter as `SentimentOptions.print_plan`. `printed_columns` returns
`(category, printed, says Nil when empty)`; an empty `print_plan` means the old
behaviour exactly - every category that holds something, no Nil pages - so a
headless build or an older call is unchanged. A category switched off is not
printed even when it holds clippings (the switch says so, and the window says
so), and the export warns with how many it left out.

Two traps in the layout card: `_values` was rebuilt from the controls on every
edit, which threw the print order away (it has no control of its own), and
`defaults_for` handed out the module's own list and dict, which a drag would
have edited in place.

**The next clipping after a priority.** 2.0.35 remembered the clipping below
the one on screen when a bubble was pressed. Press a second bubble - or change
your mind, or clear it - and the first press has already moved the clipping to
the top, so "the one below it" became the clipping now shown as No. 2, one they
had already seen. The place is now fixed when the preview ARRIVES at a clipping
(`_remember_after`, `_preview_at`), never when a bubble is pressed; drawing the
same clipping again after a priority, a trim or a rename does not move it.
The board hit this because that is where the morning's sorting is done, but the
press report had the same fault.


## Our own report, read back - the second half of it (2.0.39)

2.0.33 fixed the coverage summary page being read as the first section header.
The same rule bit again from the other end, and this time on a file we could
measure: the office's own `PRESS MEDIA COVERAGE OVER NORTHERN RAILWAYS
18.09.2026.pdf` - 254 pages, exported by 2.0.32, stamped, read as ours. It
prints no heading over the first 240 clippings, because nobody asked for one,
and then ELECTRONIC MEDIA and SOCIAL MEDIA near the end. Every picture above
the first header is a letterhead, says the rule, so **239 of 254 came back
flagged "probably not a clipping", each with its tick cleared**.

The rule is right for a division's document and wrong for ours: in our own
report every picture above the heading is a clipping somebody accepted and
exported, and the report prints headings only where they asked for them. It is
now skipped when the file is one of ours (`own` in `assemble.build_clips`); the
cover is still furniture, which is what the rule was catching here.

Two more, found while measuring:

  * the sentiment dossier's **Word** file carried no stamp at all - only title,
    subject and author - so a dossier imported into the press report was read
    under a division's rules. It now writes the same two stamps the report's
    Word file writes (`dc:description` and `cp:keywords`), and the dossier's
    PDF carries the keywords beside its creator.
  * 2.0.38's "Nil - no clips" page is a page with words and no picture. Those
    words live in `core/ourfiles` now, printed from there by the exporter and
    marked as furniture by the reader, so the page cannot become a caption for
    the clipping after it.

`test_ownreport` grew section 3b (the office's shape: six clippings with no
heading, then one with) and 4b (the Nil page), both in PDF and Word, both with
the stamp and with it stripped off - 89 checks. The measurement that started it
is in `scratchpad/probe_ownimport2.py`: it reads a real report and prints what
the importer made of it.


## Our own report, read back - what it took to finish it (2.0.40)

Three separate faults were hiding behind one report ("the names do not fill
in"), and only one of them was the one already fixed in 2.0.39.

**The division profile was being applied to our own file.** `detect_division`
reads the FILE NAME, and a report of ours is often named for a division, so
"Press Media Coverage Regarding Delhi Division ..." was read by Delhi's
profile - whose `caption_position` is "burned", meaning "the name is inside the
picture, there is no caption to read". Every one of its 17 printed captions was
dropped. Lucknow is "burned" too; Ambala and Jammu are "after", which hands
each caption to the picture above it. Our exporters always print the caption
directly above its clipping, so `build_clips` now forces `position="before"`
for our own files, and the caption walk stops at the page edge (our reports put
one clipping on a sheet). The same page rule gives each clipping its own link:
`link_for` looked backwards as well and handed a clipping the address of the
one before it. `_mark_address_tails` marks the second line of a wrapped address
so it can never be read as a name.

**Hindi came back as glyph numbers** ("दैनə क जागरण दɘ Ėली"). MuPDF writes a
ToUnicode map by reading the font's cmap backwards, so every glyph the font's
GSUB *makes* - matra variants, half forms, conjuncts, and Latin ligatures in
Calibri and Cambria - has no entry, and readers fall back to the glyph number.
`core/glyphtext.py` reads those words from the embedded font's own tables in
stored order, then CONFIRMS each candidate by drawing it again with that font
and comparing glyph ids: a word is accepted only when exactly one well-formed
spelling draws exactly the page's glyphs. 1,404 of 1,404 lab lines exact, and
it refuses every word of a Word-made division PDF rather than guessing.

**`core/reportrecord.py` is the answer for everything else.** Every export now
embeds a JSON record of its clippings (PDF: an embedded file; Word: a customXml
part - both measured through a PyMuPDF save, a PDFium save and a Word 16
SaveAs). On import it is paired to the pictures by sha1, then by fingerprint
for a re-encoded file, then by order only when the counts agree; the page wins
when a caption was edited after the export. It carries what the page cannot:
the names of clippings that printed no caption at all, and the burned band's
box, so a burned report comes back with the band cropped off and the name in
its box. Nothing machine-identifying goes in, and every string passes the same
word list the page does.

For burned reports made before the record existed, `recover_bands` finds the
band by the export's own geometry and inks, reads it, and crops it - but only
when the file as a whole looks burned, because on a single picture the colour
tests alone can be fooled by a cutting whose own top line is dark blue-grey on
white (measured: the side geometry only bites on 68 of 250 real clippings).
The first picture of a burned report with no band is its cover.

Measured on the office's own files: the Water Safety report 17 clippings, 14
named (three were never named), Hindi correct; 18.09 253 clippings, 158 named;
the burned dossier 12 clippings, 10 names off the bands, 12 bands cropped,
0 inked pixels lost; 47 sample documents compared against 2.0.39, only our own
report reads differently.


## Capturing a post without signing in to anything (2.0.41)

The morning used to begin with a sign-in. A link to a post on X, Facebook or
Instagram opens, for anybody signed out, a page that is mostly a wall, so the
program asked the office to sign in - in the browser inside the app, or by
taking the picture from their own Chrome. That put somebody's account into the
program, and it broke the day a site signed them out.

**Every one of those sites already publishes the post a second way.** It is
what a newspaper quoting a post puts inside its own page: X's
`platform.twitter.com/embed/Tweet.html?id=`, Facebook's
`plugins/post.php?href=`, Instagram's `/p/CODE/embed/captioned/`, Threads' and
LinkedIn's equivalents. It is meant to be read by anybody, it is served to a
browser that has never signed in to anything, and it carries the post alone -
the writer, the words, the picture, the date - with no feed, no wall and no
banner. `core/embedcard.py` turns a post's link into that address; plain text
work, no network, and it says nothing for a link that names a person, a page
or a search rather than one post.

Measured signed out, in the program's own hidden Chrome with no account of any
kind: a page's Facebook post whole, Hindi and photograph and reaction counts
included; three Instagram reels with their captions; X with its writer and
date. A morning's list of five mixed links - three posts, two stories - came
back five of five, none of them signed in, about 2.8 s each.

**Only the address OPENED changes.** The cutting keeps the post's own link and
its own site, because that is what the report prints and what somebody clicks
a year later. `capture_over` opens the card, `_capture_at` files the shot under
the link that was sent, and the site is put back afterwards - the card's own
host is platform.twitter.com, which is nobody's idea of where the post was.

**The window is the lever, not the site's width parameter.** Facebook's plugin
ignores `width` when the card is opened on its own - measured at 500, 620 and
750, all one size - and fills whatever window it is given. At the program's
usual 820 an upright photograph came out with a black band down each side, and
X's card, which stops at 550, came out with white to the right of it. Each
card now draws in a window of its own width (`embedcard.WINDOWS`), and `_cut`
takes that width rather than PAGE_WIDE.

**A card is not a news page**, so `CLEAR_CLUTTER` stops at the top of one: the
rules below it are written for a story with adverts round it, and they read a
card wrongly - X's card is one `<article>` laid over the page, which the
pinned-over-the-page rule hides. What is taken off a card is named: a cookie
notice, and Instagram's own comment box and "View more on Instagram" button,
which are controls for somebody reading on the site rather than part of the
post being quoted. `FIND_BLOCK` cuts a card to everything painted on it -
every picture, and every element with writing of its own - which is tighter
than the body and works the same on all five sites.

**Where there is no public post behind the address** - taken down, or shown
only to the writer's friends - the card says so in the site's own words, in the
middle of the card rather than its first line ("Instagram / Instagram / The
link to this photo may be broken"), so the whole of its writing goes back and
`embedcard.gone` reads it. The post's own page is then tried after it, the old
way, because somebody who IS signed in may still be shown it; only if that
fails too is anybody told, and what they are told is that the post is not
public, not that they need to sign in. A card that comes to nothing for any
other reason is treated the same way, so a site that changes the shape of its
cards one morning cannot send the whole office off to sign in to it.

Signing in still exists, for a post that is not public and for a paper that
wants an account before it shows a story. It is no longer how the morning
starts.

Also: the clutter is cleared once more, after the pictures arrive, which is
when a late cookie bar or newsletter box appears - and the cutting is measured
again only where that hid something new. A page with no headline to build a
cutting round is now named by its own `<h1>` where it has one, then by what it
tells a site to print when it is shared, and only then by the wording on its
tab.


## A link from Facebook's Share button (2.0.42)

The office's own WhatsApp list, tried the morning after 2.0.41 went out: 16
links, 13 captured, and the three that failed were all Facebook - all three of
the form `facebook.com/share/p/1JsEoxaa6y/`, which is what Facebook's Share
button gives and therefore most of what arrives. Each was put down as "not
public" although the post was public and there that minute (Indian Express,
Obc Prabhat, Rahul Baba ki Masti).

**A share link stands for a post without naming it.** The plugin needs the
post's own address and refuses the short one. Measured on that Indian Express
link, signed out:

  * `plugins/post.php?href=<the share link>` -> "no longer available"
  * `href=<the page's own canonical address>`, which is the form with the
    post's words and number in it (`/posts/against-all-odds-…/1674736980676764/`)
    and is also what its `og:url` says -> **also** "no longer available"
  * `href=<where the browser came to rest>`, the `pfbid…` form -> the post

So the address to ask for is the one the BROWSER ends on, not the one the page
calls itself. `embedcard.needs_resolving` marks the forms worth opening for
(`/share/p|v|r/` and `fb.watch`), `webshot._resolve` opens the link on the page
that is about to do the capture anyway and reads `location.href` until it stops
looking like a share link (six seconds, asked every 0.6), and
`embedcard.resolved` tidies it. Whatever the page shows meanwhile - the post,
or a wall - is not looked at: only where the browser was left. A share link
that does not move is captured exactly as it was sent, as before.

The list then came back 16 of 16 with nobody signed in to anything: three
Facebook posts through their share links, four X posts (Northern Railway's own
among them), five Instagram posts and reels, and four newspaper stories. The
glued pair in the middle of the message - two Instagram links with no space
between them - was found as two, which is core/links doing its job.


## The export, the board and the links window (2.0.43)

Six things asked for together. The one with a design decision in it is the
grouping.

**Grouping posts by platform is a button, not a rule.** The office's own
example was "3 Facebook, 2 Twitter, 3 Instagram, then 2 Facebook, 2 Instagram
and 3 Twitter", wanted as five, five and five with the platform named once over
each run. Doing that automatically at export would have broken the promise the
export box makes - "in exactly the order shown in the list" - so page 7 of the
report would no longer have been item 7 of the list. Asked, the office chose a
button. `commands.GroupSocial` does both halves in ONE step, because they are
one idea: a heading printed once over a run means nothing if the run is not
together, and posts gathered with no heading do not say what they are. One
Ctrl+Z takes back both.

`social_grouping` gathers each platform's run at the place its FIRST post
already held, keeps the order inside a run, and does not move a newspaper's
story at all. The heading is `Clip.section_key` + `section_title`, which is the
machinery that already prints a heading once per run (`layout.section_banners`),
so the press report needed nothing new. The six platform headings ship on the
headings list (`core/sections.SHIPPED`) so they can be renamed once for every
report after it - TWITTER is the office's word, and x.com is X.

The dossier does not use `section_banners` - it heads its pages by category -
so `build_sentiment` grew a platform line under the category heading, drawn on
the first clipping of each platform run inside that category, in both the PDF
and the Word file. It reads the words off the clipping and works nothing out
from the address: a dossier must not start naming platforms the report has not
been told to name.

**No cover page at all** is a switch on the cover panel, which the dossier's
cover panel has had all along. `with_cover=False` means no sheet is written -
not a blank one, not the plain count-and-date one - so `_number_pages` had to
learn where to start counting (`first=0`), the Word file had to stop putting a
page break before its first clipping, and the report's record had to say
`cover=False` or a reader would count the first clipping as furniture.

**The board's counts** were six tiles 64 pixels tall across their own band -
most of a laptop's first screenful for seven numbers. They are pills now, on
the line that already carries the division's count, each still in its category's
colour. Everything that writes the numbers was left alone: `_tile` still hands
back a dict with a "count" label in it. Moving them up made that line long
enough to push the board sideways at 1180, so the sentence beside the title
elides - it is the only thing on the line that is not a number or a control.

**The links window** numbers every link by where it is in the list rather than
by what the sender typed, because the sender's numbering is often missing and
more often wrong once two glued links have been split apart; and the line above
the list counts them by site. It closes itself about two seconds after the last
clipping, but ONLY when every link went through: a window that closed over "3
are not public" would have thrown away the only notice of it.

**The heading and layout panel wraps** when it runs out of room - it already
did at 1180 before any of this - and measured at 1366 the dossier's strip goes
to two rows for a grouping button labelled anything longer than about "Group
posts". Hence "Group by platform", with the sentence in the tooltip.


## A video on a card, and four things that were the wrong width (2.0.44)

**An X post with a video came out as a grey box.** Not the picture: the whole
card. X's embed asks the browser whether it can play the video, and the browser
INSIDE THE APP - Qt's engine - is built without H.264, so it answers no:
`canPlayType('video/mp4; codecs="avc1.42E01E"')` returns `""` and
`MediaSource.isTypeSupported` returns false. X answers that by throwing the
whole card away and drawing "The media could not be played" in its place,
headline and all.

It took a while to see because the program's OWN Chrome does have the codecs:
fifteen captures of the office's three links there came out right, every time.
Through the browser inside the app - which is what the office captures with -
six of six were lost. Facebook and Instagram were never affected: their embeds
show a still poster and never instantiate a player.

`blockjs.STILL_THE_VIDEO` runs on a card before the site's own scripts do, and
tells the page it CAN play: `canPlayType` answers "probably" for anything that
looks like MP4, `MediaSource.isTypeSupported` answers true, `load()` does
nothing, `play()` returns a promise that never settles, and a source set on a
media element goes nowhere. Nothing is ever decoded, so the player stays
exactly as it starts - the poster frame with the play button over it, which is
the cutting wanted. Measured after: six of six right, and the files went from
131 kB of grey to 1.3 MB of photograph.

It has to be installed with `Page.addScriptToEvaluateOnNewDocument` BEFORE
navigating. Run as an ordinary script after `Page.navigate`, it lands on the
document being left rather than the one arriving, and the card is built
unpatched - measured, six of six still lost. It is removed again afterwards, so
a page somebody opens in the browser window is never touched by it.

**A label can decide how wide the program is.** Switching Collect on while the
sentiment board was open grew the window from 760 to 1119 pixels, walking its
right edge off a half-screen desktop. The cause was `BoardStatus`, a plain
QLabel on the export bar: handed "Collecting into the sentiment board, Neutral
column - 0 photos, 0 captions." it asked for one unbroken line 811 pixels wide,
which became the export strip's minimum, then the board's, then the window's.
It is an `ElidedLabel` now, with the sentence on its tooltip.

A sweep for the same fault found two more - the words-kept-out strip and the
empty-list guidance - and they are wrapped or elided too. The only long label
left is the board's own title, which is four fixed words and well inside the
window's own minimum. The rule worth keeping: **nothing that is handed a
SENTENCE may be a plain QLabel in a strip.**

Also: the dossier export bar's border was `border: 1px` with `border-top: 3px`
and a radius - Qt lays the thick side over the thin one and stops it dead where
the curve begins, so the orange ran along the top and the rest was a hairline
nobody could see. One 2px border all the way round. The sideways scroll bar had
no rule at all, so Windows drew its own; it is the same grey pill as the
upright one now. And the print order window's tick boxes were drawn in the
window's background colour, on a row of the same colour - given an outline, a
white face and a navy box with a tick.


## Copying a clipping out of the preview (2.0.45)

Two buttons on a tab riding the right edge of the picture. They are there
rather than among Rotate, Split, Trim and Exclude at the foot because neither
of them CHANGES the clipping - one takes a copy of the picture, the other takes
a copy of the clipping - and the foot is where the things that change it live.
The tab is rounded on its left side only and flush on its right, so the
window's own edge is the tab's straight side and it reads as part of the window
rather than as two buttons left on top of it.

**The clipboard gets the picture as it PRINTS.** `clip.render()` is the call
the exporters make, so a trimmed or turned clipping is copied trimmed and
turned - what somebody pastes into WhatsApp is what the report would have
shown.

**Copying into another newspad had to be done on disk.** Only one newspad is
ever loaded (see core/newspads), so the clipping cannot be handed to a window:
`newspads.deliver` writes it into the other newspad's own manifest and picture
folder exactly as its window would have, and it is there when somebody switches
to it. Four things it is careful about:

  * **Never the newspad that is open.** The window owns that manifest and
    rewrites the whole of it on its next save, so anything written round the
    back of it would vanish seconds later without a word. It refuses outright
    rather than trusting the caller.
  * **Never over a manifest that cannot be read**, which is a morning waiting
    to be rescued: appending to "nothing saved" would write a fresh manifest
    over it.
  * **Its own uid and its own id.** The uid is what the duplicate check and
    the board's lists know a clipping by, so a copy sharing one would be one
    clipping in two places; the id is taken past anything either pool already
    holds, not merely from the counter, in case an older build wrote no
    counter.
  * **The pool it came from.** A board clipping joins that newspad's board.

The clipping's own newspad is saved first, so a picture the window has not yet
written to disk is not the one thing the copy is missing.


## The headline that was cut off, and the stamp that hid a repeat (2.0.46)

**"Trim phone bars" was eating headlines, and it is gone.** The office sent a
Times of India cutting whose first line came back sliced. Measured on their own
picture (493 x 700): the first ink is at row 24 and the tidy-up cut at row 40 -
sixteen rows into solid black type. `_margins` was right; `_bar` was wrong. A
status bar is "a band at the top that is one colour with a few small marks in
it", and that is exactly a headline's first line; the only thing keeping the
rule off ordinary pictures was "taller than wide", which a newspaper cutting
usually is.

The office's own verdict settled it: they had already found that unticking the
switch imported the picture correctly, and said that in a year of use no
clipping has ever carried a phone bar. So `tidy_box` takes a `bars` argument
that defaults to **False** and nothing in the program passes True. The code and
its tests stay - one line turns it back on - but the program never asks. Doing
it properly would mean recognising a battery and a signal meter, which every
phone draws its own way and which are a dozen pixels across on a pasted
picture: a great deal of machinery for something never once needed.

Two more faults came out of the same picture:

  * **A bar that was FOUND but not cut still cancelled the margin.** The rule
    is "where a bar is found the edge is the bar's, and no margin is looked for
    there" - but bars were only ever cut on a phone's screenshot, so on
    anything else the edge came away untrimmed. Now a bar only speaks for its
    edge when it is actually being cut.
  * **A margin cut exactly on the first inked pixel shaves the letters**, whose
    edges fade into the paper. It now backs off a few pixels and counts fainter
    ink as ink (`MARGIN_SAFETY`, `INK_TOLERANCE`).

The tidy-up only ever touches PASTED pictures (`source_file == "clipboard"`)
and only ever as a crop; a PDF, a Word file or a photograph added from disk has
never been near it, and the picture itself is never altered.

**A stamped copy was not seen as a repeat.** The office sent the same Rajasthan
Patrika cutting twice, one copy stamped with a black band carrying the paper,
the city and the date. `ocr.strip_band` would not look past 35% of a picture
and that band is 48.5% of it, so the band stayed: the reader read the stamp
instead of the story (nothing at all, against the story's own headline on the
plain copy), and the prints measured 32 and 33 apart - passing both gates by a
single point, on nothing but luck.

At 0.50 the band comes off, both copies read
"इंडियन रेलवे ट्रैक से जुड़े रोचक तथ्य", the prints fall to 18 and 20, and the
pair is found. Measured for harm: of 28 real pictures in the sample folders,
**none** is changed by the new limit, and test_duplicates (58), test_duprule
(50) and test_dupswap (31) are unchanged. What the new limit could reach is a
cutting whose top 35-50% is a dark photograph ending in a clean light edge;
that would be measured and read from below the photograph. `strip_band` is used
only for MEASURING and READING - never for the picture or the report - so the
cost there is a little less precision in matching, not a clipping.


## Finding a clipping, and seeing what the reader read (2.0.47)

**The search takes operators, and it does not need a library.** The office
asked for something that behaves like a search box - AND, OR, phrases,
exclusions - and asked which library to bring in. None: a full-text engine
(Whoosh and the like) wants an index, a good deal of bundle weight and its own
fight with PyInstaller, for a list of a hundred and sixty rows that is already
in memory. `ui/findbar.parse` is about sixty lines and gives the same syntax
with no dependency at all.

  * words next to each other are joined by "and";
  * `OR` in capitals splits the query into sides - so `a b OR c` is
    `(a and b) or c`, which is how a search box groups them;
  * `"a phrase"` is asked for exactly, in that order;
  * `-word` must NOT be there;
  * `paper:`, `headline:`, `read:`, `edition:`, `link:` ask one field only.

`OR` has to be capitals so a headline with the word "or" in it stays a
headline. Text is folded before it is compared - case, punctuation, and the
Devanagari matras, because a reading taken off a picture loses them - and
anything four letters or longer that did not match plainly is tried again
forgivingly with rapidfuzz, which is already in the build. A quoted phrase is
never guessed at.

**What the reader read is now a field.** It was already being kept, and the
duplicate check and the search both use it, but it was the one thing about a
clipping nobody could see or correct: a misread headline quietly stopped a
repeat being found, with nothing on screen to say so. It is a box on the row
and a box in the preview, with two round buttons - read the picture again, and
put these words into the headline that prints. Corrections are kept on the
clipping, so both the check and the search improve together.

The box only appears where there IS a reading. An empty box on every one of a
hundred and sixty rows is the clutter `rowlayout` warns about, so a row grows
to three boxes only when it has three things to say.

**The export bar's last-action line is the undo stack, said out loud.**
`undoText()` is the thing that would be undone, which is the last thing done,
and it steps back on Ctrl+Z without being told. Each interface has its own
stack, so the board and the press report each report their own work. It elides,
and the count beside it wraps, so neither ever reaches the export buttons -
measured at 1240, 900 and 760.

**The bubble** was a QFrame, which draws a box by default: a squarer edge
inside the rounded navy one, which is what "many unwanted edges" was. It is one
shape now, translucent, and only as wide as its words - a wrapped label's
sizeHint is its MINIMUM, so the sentence is measured as one line and capped at
456 rather than pinned at 680 whatever it said.


## Why the reader kept saying nothing (2.0.48)

The office reported "nothing is read" on pictures that are perfectly clear.
Measured on their own files, there were four faults, and one of them was
hiding the other three.

**`headline()` carried its own copy of the search.** It duplicated the
two-band logic that `headline_with()` has, so everything added to
`headline_with` was never reached by the reading the program actually does -
which goes through `headline()`. One path now.

**A narrow clipping was refused outright.** `_prepare` handed back None below
240 pixels across, so a cutting trimmed to one column was never read at all.
Tesseract wants about 1200 across whatever it starts at and the line below
already enlarges everything else; there was no reason for a floor above the
point where there is nothing to enlarge (40).

**Only the top of the picture was ever read.** Two bands, 40% and 72%. A
cutting whose headline sits beside the photograph, or a strip with its words at
the foot, came back empty from both. The whole picture is now read as a last
resort - slower, and a worse headline, so only after the other two have said
nothing.

**And it read the picture as it ARRIVED.** `read_into` used `clip.image_bytes`,
which is before the trim and the turn. A photograph that came in sideways and
was turned upright in the program was still read sideways: measured, gibberish
where the upright picture reads "gupta rides hydrogen train, says next stop
del" at 96. It reads `clip.render()` now - the picture as the report shows it.

For a picture nobody has turned, the other three ways up are tried, but only
when reading it as it lies gave nothing or scored under 55, and another way up
only replaces it when it is clearly better (15 points). Measured on the
office's cuttings: the right way up comes back at 96 and the wrong ways up at
0, 26, 39 and 75 - the 39 being confident-looking nonsense off a sideways
cutting, which is why the line is drawn above it rather than at 30.

Measured after, on every picture the office has sent in: the real cuttings read
exactly as before at 96 and 97, and the three that came back with NOTHING now
read at 94, 72 and 63.

**The search field is pinned.** It used to sit on the page and scroll away,
while its results hang off the window - so the panel had to chase the field
down the screen and then flip above it when the field neared the foot, which
read as a glitch. Pinned above the page, the field never moves, the panel
always hangs downwards, and it has the window's whole height to fill. The panel
also stays open when a result is opened, with the query still in the box: the
next thing after looking at one result is almost always the next result.
