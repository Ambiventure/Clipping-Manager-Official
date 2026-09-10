# What's new

The source of the "WHAT'S NEW.txt" that travels inside every hand-over copy.
`build.py` renders it, stamps the real version and build date on the top, and
refuses to go quiet about a version that has no entry here.

Rules for writing an entry, because this file is read by the people who use the
program and not by anyone who works on it:

  * Say what is different when they sit down at it, not what was edited.
    "The date can no longer be changed by scrolling past it" - not "wheelEvent
    now ignores".
  * No file names, no function names, no version numbers of libraries.
  * One line per thing. If a line needs a comma and a "which", it is two things.
  * Newest version first. Never rewrite an old entry: it went out to somebody.

---

## 2.0.17

New

  * **The Section box in the preview window is now the heading picker.** On the
    press report it offers Electronic Media, Social Media and Digital Media -
    the three that actually print - instead of the seven sentiment names. Type
    any other heading into it and it is added to the list for next time.
  * **Digital Media prints now.** It never did. A heading typed onto a digital
    clipping was carried, saved and shown on the card, and then dropped when
    the report was built. The Lucknow document files seven digital clippings on
    an ordinary morning.
  * **A size and a colour for section headings**, on two buttons beside the
    picker. It is one setting for the whole report, so every heading in it
    matches, and both the PDF and the Word file obey it - the Word file used to
    print red whatever you chose.
  * "List…" beside them takes a heading off the list, or puts the three
    standard ones back. A clipping already carrying a heading keeps it.
  * On the Sentiment Board the same box is unchanged and still says which
    column a clipping belongs in. It is labelled so now.
  * **A box under the cover page for words you do not want printed.** Add a
    word or a phrase and it is left out of every caption, heading and burned
    headline in the report. Take it off and it prints again.
  * It says what it can and cannot reach, because the obvious guess is wrong: a
    clipping is a photograph of newsprint, so a word inside an article is part
    of the picture and stays there. The list reaches the text the program
    prints - the caption, the heading, the cover.
  * Whole words only, so "man" is not cut out of "manager" and a Hindi word is
    not cut out of the middle of a longer one. Capitals make no difference.
  * The address under a clipping is never touched. Real addresses contain
    ordinary words, and shortening one breaks the link.
  * Nothing is changed on your clippings, and a report that had anything left
    out of it tells you so, with the words and the count, every time. An empty
    list prints exactly the report you get today.

  * **Check for updates.** Press "Runs offline" in the top bar and there is now
    a button that asks, once, whether a newer version has been published. If
    there is one it tells you which, and offers to open the download page in
    your browser.
  * It only asks when you press it. The program still does a whole morning's
    work with the network cable unplugged, and it never checks by itself - not
    at startup, not on a timer, not while you are working.
  * Nothing is downloaded or replaced behind your back. You fetch the new copy
    yourself, the same way you got this one, so there is no way to end up with
    half an installation.
  * If there is no internet at that moment it says so plainly and carries on.
    Not being able to check is not a fault, and it is not treated as one.
  * Updating still leaves your setup alone - the newspaper list, everything the
    trainer has been taught, your cover and your export folder are all kept
    outside the program's own folder and are not touched.

## 2.0.15

New

  * **Duplicates Trainer.** A button beside the interface switch opens a screen
    that shows you pairs of clippings it is unsure about, two at a time, and
    asks whether they are the same cutting. It picks the pairs worth asking
    about rather than showing you everything: on a real morning of ten thousand
    pairs, fifty picked this way hold about a dozen real repeats, where fifty
    picked at random hold none.
  * It tells you why it is asking - whether the headlines nearly matched, or
    the pictures did, or a headline could not be read at all.
  * Y for the same cutting, N for different, S to skip, Ctrl+Z to take the last
    one back. Skipping writes nothing down: a guess recorded here is worse than
    no answer, because a year later nobody can tell it from one you were sure of.
  * **Save to a file, and load it back.** Everything you decide can be written
    to one file - to keep, to move to another PC, to hand to a colleague, or to
    send back so a later version of the program can be set against real
    mornings instead of guesses. Loading a file tells you what it will do before
    it does it.
  * What you decide is remembered by what the clippings LOOK like, not by their
    place in the list, so it still counts tomorrow, after a re-import, and after
    the program is updated.
  * Where two people disagree about a pair, neither answer wins. The pair is
    marked as disagreed and put back in front of you - one careless click can
    never quietly overwrite somebody's correct answer.
  * What is saved carries no user name, no machine name and no folder paths.
  * **Save my setup to a file, and put it back.** In "Which papers are which"
    there are now two buttons that carry your whole setup in ONE file - the
    newspaper list, what the trainer has been taught, the cover and heading
    settings, where exports go, and the window size. For a new PC, for handing
    your setup to somebody else, or for a copy somewhere safe.
  * You do NOT need it to update the program. Everything the program remembers
    lives outside its own folder, so an update leaves all of it exactly where
    it is. There is no folder to copy and no step to forget.
  * **"Runs offline" in the top bar is a button now.** Press it and it tells
    you what the program remembers, where it keeps it, whether a copy is being
    kept somewhere backed up, and when that copy was last written. Saving a
    setup, putting one back, and choosing where copies go are all there - so
    they can be reached on a machine with nothing imported yet, which is
    exactly the machine somebody restores onto.
  * **Keep a copy in your Google Drive or OneDrive.** Point it at that folder
    and a fresh copy of your setup is written there every time you close the
    program. The program still never goes online - it writes a file, and the
    sync program you already have carries it into your account. Nothing to sign
    in to, and it still works on a morning with no internet.
  * It finds Google Drive where Google actually puts it. Drive for Desktop
    mounts itself as a drive rather than a folder, so a copy of the program
    that only looked in your home folder would have found nothing on a machine
    where Drive was installed and working perfectly.
  * Your clippings are never copied there. A morning is 34MB of the
    newspapers' own photographs against 25KB of settings, and it is a morning's
    work rather than something you set.

Changes

  * **Choosing a size no longer takes three restarts.** The percentage in the
    middle of the zoom buttons now opens a list of every size, and picking one
    goes straight there. It used to step one size at a time, asking to restart
    at every step - three of them to get from 100% to 70%.
  * 75% has been added. It was asked for and could not be reached: the sizes
    went 70%, 80%, with nothing between them.
  * **Nothing is taken out of the report without being shown to you first.**
    Suspected repeats are badged and stay in the report until you look at the
    pair and delete it yourself. On one real morning the program was quietly
    removing six clippings, and three of them were separate pieces of coverage
    - a clipping that disappears on its own leaves nothing on screen to notice.

Fixes

  * The fingerprint used to compare two clippings is now taken of the picture
    as it prints, with the crop applied. It was being taken of the whole
    picture before cropping, so two copies of one cutting cropped differently
    could look like two different cuttings.

## 2.0.12

New

  * **Filter and arrange.** A button above the clipping list opens a strip where
    you can show only some of the clippings - the regional papers, the Hindi
    ones, the big publications - or put them in another order without hiding
    anything.
  * The filters stack. Pick Regional, then pick Hindi or English on top of it,
    and each choice only narrows what the one before it left.
  * Arranging is a separate control, so you can sort the whole morning by size
    without hiding a single clipping, or hide all but the English papers and
    leave them in the order you put them in.
  * Arranging asks which comes first. Choose Language and a second row appears
    with every language this morning has - click English and the English
    papers go to the top; click Punjabi next and they follow. Anything you do
    not click stays in its usual order. The same for newspaper, reach, size
    and medium, and the strip says the order in words.
  * Every choice shows how many clippings are under it before you pick it.
  * "Show all again" puts everything back exactly as it was - the same order,
    the same brackets, the same folded documents, the same ticks.
  * **Filtering changes what you see, never what is exported.** A hidden
    clipping is still in the report. The strip says so while it is open.
  * "Which papers are which" lets you say what counts as regional, what is
    Hindi, and which are the big publications. What you set there is kept when
    the program is updated - and the papers nobody could confirm are marked, so
    you can see which ones are worth correcting.
  * Sixty-two publications come already sorted into national, regional and
    local; Hindi, English and Punjabi; and big, middling and small. Television
    channels, news websites and social media are kept separate from the papers.

Fixes

  * **"Check for Duplicates" no longer freezes the program.** It used to do all
    of its work on the screen: on a morning of a hundred and forty clippings
    that was over a minute of a dead window, with pauses of nearly two seconds.
    It now works in the background like the automatic check has for a while.
    The same morning: the button answers immediately, the whole check takes
    about twenty seconds, and the window stays usable throughout.
  * Ten newspapers the reports carry were not on the list, so they were being
    counted as other papers. "Punjabi Jagran" was being recorded as "Dainik
    Jagran" - a Punjabi paper counted as a Hindi one - and "Ajit Samachar" as
    "Ajit". Also added: Haribhoomi, Jagmarg, Prath Kiran, Bedaak Kesari, Uturn
    and News Times Ludhiana, and the channels Aaj Tak and Times Now so they stop
    being mistaken for newspapers.
  * Pressing "Check for Duplicates" after cropping a clipping now measures the
    picture again in full. Some of the measurements were left at their values
    from before the crop.
  * Saving your morning is no longer slow. The program re-read every picture
    from scratch each time it saved - which it does on a short delay after every
    edit - and on a morning of a hundred and forty clippings that was about
    seven tenths of a second of frozen window, over and over. It now does that
    work once, when the pictures first arrive.
  * The progress line during a duplicate check was being rebuilt about sixteen
    hundred times to say the same thing.
  * Dropping a WhatsApp image in now scrolls the page to it, with its headline
    box open and ready to type into. Since the page became one long scroll the
    list could no longer scroll itself, so the box was opening off screen and
    nothing seemed to happen. The same fix covers importing a file and pressing
    Enter to move to the next headline.
  * Dragging a block of clippings towards the top or bottom of the screen
    scrolls the page again, and keeps scrolling while the pointer is held
    there. It used to be impossible to drag a clipping past what was on screen.
  * A web address typed into a clipping's headline box still goes to the link
    box - and the empty headline box no longer stays behind above it.

## 2.0.8

Fixes

  * "Check for Duplicates" no longer says the headline reader is missing on a
    machine where it is installed and working. Importing files could leave the
    reader switched off for the rest of the session, and the only way back was
    to close the program and open it again.
  * Closing the program while it is still looking through an import no longer
    shuts it down without a word. It now finishes the clipping it was holding
    and lets go before the window disappears.

## 2.0.7

Changes

  * The clipping count and date on your own cover artwork are now a box you can
    take hold of. Drag it to move it, and pull a corner to make it bigger or
    smaller - it used to be placed by clicking somewhere else on the artwork,
    with the size buried in a list.
  * The box is see-through, so the artwork underneath it can be judged while it
    is being positioned, and it is exactly the box that prints.
  * Stretching the box and choosing from the Text Size list are now the same
    thing: move one and the other follows.
  * That cover goes into the Word file as the artwork plus real text, so the
    count and the date can be corrected in Word. Both covers are editable there
    now, not only the generated one.

## 2.0.6

Fixes

  * The cover heading and date are now the size they say they are. Asking for
    96pt used to print at 63pt - in the PDF and in the Word file alike - because
    the sizes were being scaled by about two thirds on the way out. Every size
    in those two lists is now a real point size, so a cover made before this
    will come out larger than it used to.
  * A long sub-heading on the cover wraps onto a second line instead of running
    off both edges of the sheet.

Changes

  * Importing no longer makes the window feel stuck. The pictures are shrunk by
    several threads at once, so the longest the window stops responding for
    during an import went from about three quarters of a second to about a
    fifth.

## 2.0.5

  * The program carries a list of what changed in each version, in plain
    English, in "WHAT'S NEW.txt" beside "READ ME FIRST.txt". It now goes back to
    before version 2.0, so the whole history is in one place.

## 2.0.4

Fixes

  * A web address printed under a picture is no longer mistaken for the next
    picture's headline. That is what put a link where a headline should be and
    then printed the same link twice on the page, once above the picture and
    once below it.
  * The program no longer closes without warning if you shut the window while it
    is still checking for duplicates.
  * Adding a web address to a clipping that has no headline yet no longer takes
    the headline box away. Both boxes can now be asked for on any clipping.

Changes

  * Clippings on the sentiment board now hold both a headline and a web address.
    Positive, Neutral and Negative start with the headline and offer "Add URL";
    Digital starts with the address and offers "Add title".
  * A headline typed on a digital clipping is now printed in the dossier. It
    used to be thrown away.
  * The program remembers what you decide about repeats. Every "Not a duplicate"
    is kept, so it never asks you about the same two clippings twice, and after
    five judgements it can offer extra pairs for you to look at. It never
    removes a clipping on the strength of what it has learnt - only offers one
    for you to judge.
  * Measuring a morning's pictures for the duplicate check is about twice as
    fast.

## 2.0.3

Changes

  * The sentiment board's cards were rebuilt to hold both a headline and a link.

## 2.0.2

Fixes

  * The zoom buttons now really do change the size. Pressing them a second time
    used to change the percentage on screen and nothing else.
  * "Back to the top" now moves the page. In the press report it did nothing at
    all, and on the sentiment board it moved the columns instead.
  * The round buttons at the bottom right no longer sit on top of the
    "Download PDF" button on the sentiment board.
  * The bar that appears when clippings are selected no longer covers the last
    clipping in the list.
  * The window can be made narrower again - it had grown a 1171-pixel floor,
    which is why things were being cut off at the right-hand edge on a small
    screen.

Changes

  * The date can no longer be changed by scrolling the mouse wheel over it.
    Scrolling anywhere now scrolls the page, and no setting changes underneath
    the pointer.
  * Every date field has a calendar to click and a "Today" button beside it.
  * A report cannot be dated later than today. If a later date is picked, the
    program says so and puts it back.
  * The two interfaces are now both on the header as buttons, with a count on
    each, instead of one being hidden inside a drop-down list.
  * Clipping cards carry a small "Add URL" button, so a pasted screenshot has
    somewhere obvious to put the link it came from.

## 2.0.1

Fixes

  * Importing a digital-news document no longer puts the article link in the
    headline as well as underneath the picture.

Changes

  * The export screen has a box for the file name. Both the PDF and the Word
    file take the name typed there.
  * The generated cover page (Option 2) arrives in the Word file as real text
    and a picture of the logo, so it can be edited in Word. It used to be one
    flat image that could not be changed at all.
  * The cover heading goes up to 128pt and the date to 48pt.
  * The logo, the heading and the date can be dragged around the cover page.
  * Duplicate checking has an on/off switch beside the "Check for Duplicates"
    button. With it off, importing files checks nothing until you ask.
  * Both interfaces scroll as one page, top to bottom, instead of in sections.
  * Zoom buttons in the header scale the whole program, for a small laptop
    screen.

## 2.0.0

  * The program learned to find the same clipping arriving twice, by reading the
    headline off the picture and comparing the pictures themselves. Repeats are
    greyed out, badged, and kept out of the finished report until you decide.
  * A review screen shows each suspected repeat beside the clipping it repeats.
  * Hindi headlines are read from the picture as well as English ones.
  * Page numbers found in a clipping's caption are printed in the headline.
  * The report with headlines burned into the pictures exports as Word as well
    as PDF, and asks for a name first.

## Before 2.0.0

There was no change log before this point, and no record of which build held
what - so rather than invent version numbers, here is everything the program had
learned to do by the time the log was started, grouped by the part of the
morning it belongs to.

Reading the division documents

  * Division documents can be brought in as Word or as PDF, and both give the
    same clippings in the same order.
  * The division a file belongs to is read from its name, so documents can be
    brought in exactly as they arrive.
  * The newspaper, the edition and the page number are read out of the caption
    into three separate boxes, so most rows are filled in before you start.
  * Clippings are sorted into positive, neutral, negative and digital from the
    headings printed in the document itself, including headings that are
    numbered or misspelled.
  * In a PDF, each clipping is matched to the caption sitting nearest it on the
    page, so a page carrying two clippings comes in as two named ones.
  * Logos, letterheads, icons, spacers, page rules and the artwork behind a
    section heading arrive unticked, so they stay out of the report unless you
    tick them.
  * Clippings that Word had stored in an older way are no longer skipped - two
    of Ferozpur's nine used to disappear without a word.
  * Long runs of clippings no longer arrive under the wrong heading. Forty from
    Delhi and fifteen from Moradabad used to be counted as the wrong kind of
    news.
  * A caption printed on two lines is read as one, so a newspaper and its city
    no longer arrive as two half-names.
  * A newspaper's name-strip sitting above its article is joined back onto it,
    instead of arriving as a bare logo followed by a headless story.
  * A clipping that was trimmed in Word arrives looking the way it looks in the
    division's own document.
  * A wide, short digital-news strip is no longer mistaken for an icon and left
    out of the report.

Naming and arranging

  * The name box sits beside the thumbnail, not behind a dialog, and offers
    newspapers as you type - initials work, and a new name is remembered for
    tomorrow.
  * Enter saves a headline and moves straight into the next clipping's box, so a
    whole division can be named without touching the mouse.
  * Twelve clippings can be selected and their newspaper set once.
  * One picture holding two clippings can be split, and several can be merged
    into one.
  * A clipping can be rotated, trimmed, excluded from the report, or opened full
    size in a preview window that walks through the list with the arrow keys.
  * Everything can be undone, including a misdrag - a wrong move across a
    hundred and sixty rows is otherwise unrecoverable.
  * Clippings are reordered by dragging the handle, with an orange line showing
    exactly where they will land and a tag saying how many are moving.
  * The list scrolls by itself while a dragged clipping is held near the top or
    bottom edge.
  * A whole document's clippings can be dragged as one block, and each
    document's heading carries its own controls to tick, rotate, move, delete or
    fold the lot.

Getting clippings in

  * Three buttons at the top: the divisions' Word documents, their PDFs, and
    photos already saved on the machine.
  * Documents and photos can be dragged straight from a folder onto the window.
  * A picture can be dragged straight out of WhatsApp Web and becomes a
    clipping, with no need to save it first - and it can be dropped anywhere in
    the window, not only on the dashed panel.
  * An image copied anywhere, including out of a WhatsApp Web chat, can be added
    with Ctrl+V.
  * A clipping dropped or pasted in gathers at the top of the list with its own
    heading, and its headline box opens by itself so you can type straight away.
  * A drop the program cannot use now says what actually arrived and points you
    at Ctrl+V, instead of simply refusing.

Building the report

  * The day's newspad comes out as a finished PDF: a cover page carrying the
    count and the date, then one clipping to a page, in the order you arranged
    them.
  * The same report can be saved as a Word file, for editing afterwards.
  * A small cutting is enlarged to fill the sheet instead of printing as a
    postage stamp in the corner. The true-to-life size is still there as a
    setting.
  * The paper size can be chosen, A4 or Letter, and the whole report follows it.
  * The heading printed above each clipping can be set - lettering, size, bold,
    centred or ranged left - a page number can be printed at the foot of every
    sheet, and the choices are remembered.
  * Every clipping can also be saved as a single picture with the newspaper, the
    date and the page printed into it, filed into folders by category.
  * Hindi newspaper names print properly: the right letters in the right order
    in the PDF, and no longer as rows of empty boxes in the Word file.
  * The headline sits directly above the clipping it names, the two centred
    together on the sheet, instead of the headline being stranded at the top of
    a nearly empty page.
  * A long newspaper name wraps onto a second line and pushes the picture down,
    instead of being squeezed onto one line.
  * In the Word file a headline is no longer left at the bottom of one page
    while its picture moves onto the next.
  * Choosing a different lettering really changes the printed report. Several of
    the choices used to look different on screen and come out identical on
    paper, with nothing said.

The cover page

  * The cover can be your own office artwork with the count and the date placed
    where you click, or a plain sheet built from a heading, a logo and the date.
  * It is set up before you export, the artwork is remembered on the machine,
    and the clipping count fills itself in and follows what you include and
    leave out.
  * The cover on the PDF and the cover on the Word file are the same page. The
    two had drifted apart.
  * The count and the date are no longer printed twice on it.

The sentiment board and the division dossier

  * A second way of working: pick one division and see that morning's coverage
    in four columns - Positive, Neutral, Negative and Digital - with a running
    count on each and a total across the top.
  * Clippings sort themselves into the four columns as they come in, from the
    headings inside the document and from the wording of a loose photo's file
    name.
  * A clipping in the wrong column can be dragged across, or moved with the
    small buttons on the clipping itself.
  * The division's report saves as PDF or Word, grouped under the four headings,
    each clipping printed large.
  * It can open on a cover sheet carrying the Railways emblem, the division's
    name, the title, the date and the count - and what is on screen is exactly
    the page that will print.
  * The date and the count on that cover can be dragged anywhere on the sheet
    and made bigger or smaller, and the count can show the total or the
    four-way split. The wording, colour, border and emblem can all be changed,
    with four ready-made looks to start from.
  * Ticking "Enable Cover Page" now actually produces a cover. Every report used
    to come out without one and nothing said why.
  * A headline typed onto a clipping is printed above its picture instead of
    being quietly thrown away.
  * Each category is announced once, at the start of its section, instead of
    being stamped in the corner of every sheet.

Being able to rely on it

  * If the computer is switched off, loses power, or the program is closed by
    accident, the morning's clippings, headlines, sentiment filing and running
    order are all still there when it is opened again.
  * Work saved earlier the same day comes back on its own. Work left from an
    earlier day is offered first, with the choice of opening it or starting
    fresh.
  * The program never goes online. Every document is read on the machine it is
    running on.
  * The Hindi lettering travels inside the program, so a report looks the same
    on a computer that has no Hindi fonts of its own.
  * The window, the program's file properties, and every PDF and Word report it
    produces all say which copy of the program made them - so two machines can
    be compared at a glance.
  * Every copy handed over carries its own number, and the number always goes
    up, so the higher one is always the newer program.
  * A computer that has never run it can be checked with one double-click, which
    prints a plain line for each thing the program needs and says what is
    missing.
