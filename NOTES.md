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
