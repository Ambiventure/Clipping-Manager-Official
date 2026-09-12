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

## 2.0.26

Added

  * **Keep the other one, in the duplicates review.** A round swap button now
    sits between the two pictures. The earlier arrival is still kept by
    default, but when it is the blurred scan and the later one is clear, one
    press turns the pair round: the clear one becomes the one the report
    keeps and the blurred one the repeat to delete. A verdict already given
    follows the sides, a third copy of the same cutting follows the new
    keeper, and "Not a duplicate" on a turned-round pair sticks for both of
    them. Press again to swap back.
  * **The preview shows the clipping a badged one repeats.** Open a clipping
    that carries the red duplicate badge and the one it repeats appears in a
    column beside it, with which file each came from, so the two can be
    compared without leaving the preview. Opening the kept one shows its
    repeat the same way. The other one can be opened with a click, or the
    pair taken straight to the review. The column is not there on a clipping
    that is not flagged, nor on the sentiment board.

## 2.0.25

Added

  * **Hindi to English, on the card and over the list.** A card with Hindi or
    Punjabi in its headline, newspaper or city shows an "English" button at
    the end of its row; "Hindi to English" above the list does every such
    card at once. A newspaper and city typed into the headline box - "राजस्थान
    पत्रिका दिल्ली" - move into the newspaper and city fields in English, the
    way a copied caption would, and a page number goes to the page field.
    Hindi already in the fields is respelt in place. A newspaper the list
    does not know is spelt out by rule and flagged amber for a check, exactly
    as Collect does. A Hindi headline that is a headline is left alone.
  * The list-wide button shows a summary afterwards: each card by number,
    what it said in Hindi, what it says now, and which ones were spelt out by
    rule. One Ctrl+Z puts the whole lot back; one per card for the card button.
  * **Take from my Chrome**, in the links window. Chrome will not lend the
    sign-in you already have to any other program - the profile it has open
    is locked, and a cookie copied out of it is thrown away elsewhere - so a
    post that needs your sign-in is now taken from your own Chrome: the
    program opens the link there, a small panel waits for you to scroll the
    post into view and press Take it, and the clipping opens ready to trim.
    The links window says which captures needed a sign-in and points to it.

Fixed

  * The sign-in wall's message names both ways round it.

## 2.0.24

Fixed

  * **Collect from WhatsApp now reads the captions the office really types.**
    A city written with the joined nasal (जालन्धर, अम्बाला) is the same city
    as with the dot (जालंधर, अंबाला); it used to be refused as "not a city".
  * DB, DJ, IE, PK, AU and ET are read as the papers they stand for, like NBT
    and HT already were.
  * "HT City Delhi" and "Jagran City" are their papers - "City" is a
    supplement, not a place.
  * **A Hindi or Punjabi paper that is not on the newspaper list is spelt out
    in English** and put on the photo, flagged amber for a check, instead of
    being refused and leaving the clipping blank. The bar says so, and says
    how to have it read every time: add the paper to the list.
  * When a caption is not used, the bar now says what shape the copy had -
    "3 words, Hindi", "12 words on 2 lines" - so what went wrong can be told.
    It never shows the words themselves.
  * **The list follows each collected photo**, so the newest one is always in
    view when its caption is copied next.

## 2.0.23

New

  * **Clippings from links.** "+ From links" takes a link - or a whole WhatsApp
    message with a numbered list of a dozen in it - and captures each story as
    a clipping: the headline, the picture and the first inches of the story,
    without the menus, adverts and cookie bars.
  * It lists what it found before it starts, numbered as the sender numbered
    them, with their own words beside each link. Untick any you do not want.
  * Each clipping arrives named after its publication, with the link under it
    ready for the report, and filed as digital coverage. A post from X or
    Facebook is filed as social coverage.
  * A link that will not open, or a post that needs signing in, is said plainly
    and the rest of the list carries on.
  * **Sign in for captures.** X and Facebook only show a post to somebody
    signed in. The button opens a browser window of the program's own where you
    sign in once. Your everyday Chrome, its sign-ins and its history are not
    touched, and the program never sees your password.
  * **Trim.** The full-size view of any clipping now has "Trim…": drag the
    edges in and only what is left is used. The picture itself is not cut, and
    Ctrl+Z puts the edges back.

Needs

  * Capturing links uses the Google Chrome already on the PC. Without Chrome
    the other ways of adding clippings work exactly as before.

Changed

  * The program still does the morning's work on the machine and uploads
    nothing. Capturing a link opens that page, which is the one time it reaches
    the internet besides "Check for updates".

## 2.0.22

New

  * **Each newspad has its own cover pages.** The press report cover, the
    dossier cover, and the headline style and paper now belong to one newspad,
    so two reports with different titles can be worked on side by side.
  * A newspad that has no cover pages of its own yet starts with a copy of the
    ones in the newspad you came from. From then on each keeps its own.
  * **Still shared by all four:** the section headings' size and colour, the
    newspaper list, words kept out, the export folder and formats, Check
    automatically, zoom, and what the duplicate check has learned.
  * **Collect from WhatsApp.** Switch it on with the button at the top, then
    stay in WhatsApp Web: right-click a photo and choose Copy image, and it
    becomes a clipping here. Select its caption and press Ctrl+C, and its
    newspaper, city and page are filled in. There is no need to come back to
    this window between clippings.
  * A caption that is not clearly a caption - a greeting, half a line, a second
    caption for a photo that already has one - is not used. The bar at the top
    says why, and offers one button to put it where it was meant.
  * Collect never reads copies marked private: passwords, and anything copied
    in a Chrome Incognito or Guest window. It switches itself off when you
    change newspad or close the program.
  * **Include on the selection bar.** Tick clippings that are already left out
    and the Exclude button says Include.
  * **Move to: on the selection bar.** It lists every file in the list, and
    "Clipboard images", with how many clippings each has. Choose one and the
    ticked clippings join that file, at its end, and print among its pages.
    Ctrl+Z puts them back where they were. The same list is on the right-click
    menu.
  * A clipping moved this way still says where it really came from. A move
    that would change where a section heading such as ELECTRONIC MEDIA
    prints is greyed out in the list, with the reason.

Changed

  * Rotate is no longer on the selection bar. Every clipping still has its own
    Rotate button.
  * Ctrl+Z undoes on the screen you are looking at: the sentiment board's own
    changes on the board, the press report's in the press report.
  * Saving your setup to a file now carries each newspad's cover pages.
  * The export no longer remembers a cover picture from another newspad.
  * An older copy of the program opening the same folder shows Newspad 1's
    cover pages in every newspad. Nothing is lost: the newer copy still has
    each newspad's own.

Fixed

  * Right-clicking several clippings and choosing "Exclude these" put them
    back into the report instead of leaving them out.
  * With several clippings ticked, one already left out, Exclude takes the
    others out and leaves that one exactly as it was.
  * Undoing "Send to the sentiment board" could bring back a card deleted on
    the board since, or leave the same clipping on both screens. It now puts
    back only what was sent. Sending starts the board's own undo history
    afresh, because the old history no longer matches the board.
  * With "Filter and arrange" sorting the list, its headings (a newspaper, a
    language) now show their name and count. They used to be drawn blank.
  * **A clipping deleted and brought back with Ctrl+Z could lose its picture**
    the next time the program opened, if the program had saved in between. It
    now keeps it.
  * A headline typed in the full-size view of a sentiment card now reaches the
    card. It was dropped without a word.
  * Changes made in the full-size view of a sentiment card are undone by Ctrl+Z
    on the sentiment board, like the board's other changes.
  * The press report's selection bar no longer appears over the sentiment
    board, where its buttons changed clippings you could not see.
  * A caption written in Hindi as हिंदुस्तान टाइम्स is now read as Hindustan
    Times, in imported files as well. It was read as Hindustan.

## 2.0.21

Fixed

  * **Opening yesterday's work no longer loses its pictures.** In 2.0.20, when
    the program asked "You have N clippings left from ...", a save could run
    behind that question while the window was still empty. If you took more
    than a second or so to answer, the pictures were deleted, and "Open them
    again" brought back nothing. Nothing is saved now until the question is
    answered. 2.0.19 and earlier were not affected.

## 2.0.20

New

  * **Four newspads.** The Newspad button at the top of the window holds four
    separate newspads, so up to four reports can be worked on side by side.
    Pick one and the window shows it exactly as you left it.
  * **What each newspad keeps for itself:** its clippings on both screens, the
    press report date, and the dossier cover's date, count, division and
    prepared-by lines, its report options, and which screen it was on.
  * **What all four share:** the cover designs, headline style and paper,
    section headings, the newspaper list, words kept out, the export folder,
    Check automatically, zoom, and everything the duplicate check has learned.
    Change one of those in any newspad and it changes in all four. "What the
    four newspads share…" at the bottom of the button's menu says the same.
  * Switching newspads clears undo, filters and selection, the same as closing
    the program does. A duplicate check that was running picks up where it
    stopped when you come back, and does not start again from the beginning.
  * Newspad 1 is the newspad you already have. Nothing is moved: it opens with
    your clippings exactly as before.
  * **Files exported from Newspads 2 to 4 say which newspad they came from**, so
    two newspads exported on the same day never write over each other. Newspad
    1's files keep exactly the names they have always had.
  * **The export asks before replacing a file** that is already there.
  * **Only one copy of the program opens at a time.** Opening it a second time
    says it is already open. Two copies open at once could each tidy away the
    other's pictures.
  * "Where your things are kept" lists the four newspads' folders.

Fixed

  * A change to the words kept out, the section headings or the newspaper list
    that could not be saved - a full disk, a locked folder - now says so. It
    used to fail without a word.
  * A newspad whose saved work cannot be read opens with a note and saves
    nothing over it until you choose to set the old work aside. The old files
    are kept, renamed, never deleted.

## 2.0.19

Fixed

  * **The box on the cover page follows the mouse now.** It did not move at all
    while you were dragging it, and crept a pixel when you let go. Measured: a
    drag of 120 pixels moved it none. Pulling a corner to resize used to jump
    back and forth between a few sizes instead of growing steadily; it grows
    steadily, and all four corners work, not just two.
  * **The message strip stops blinking during a duplicate check.** Every message
    set its own nine-second timer to hide the strip, and a check sends a hundred
    messages, so they took turns hiding a line the next one had just shown. It
    is one timer now: the strip stays up while there is news and comes down once
    when there is not.
  * **A proper progress bar** in the import panel while the check runs, so a long
    check reads as work happening rather than as a program that has stopped.
  * **Filtering by language works on every clipping, not just the named ones.**
    This was the real fault behind "English first only lifted two": half a
    morning's clippings carry no newspaper name at all, because Delhi and
    Lucknow print the masthead into the picture instead of typing it. Those had
    no language to sort by. The program now reads the clipping itself where
    there is no name to look up. On a real morning that took the clippings with
    no language from 87 down to 13, and English first lifted all 24 English
    clippings instead of a handful.
  * Your own newspaper list still wins wherever it says something. It is a list
    you can correct, and a correction outranks anything read off a photograph.
  * **The preview window follows the filter.** With a filter on, the arrow keys
    walked through clippings that were not on screen and skipped the ones that
    were, and the counter counted the wrong list. It walks what you are looking
    at, in the order you are looking at it.
  * **The duplicates trainer stops asking about obviously different clippings.**
    Against your own sitting of 64 answers, of which 63 were "not a duplicate":
    the same clippings now produce 9 questions instead of 64, and the one real
    repeat is still among them. It asks when the headlines agree or the pictures
    nearly match, and not when there is nothing in common at all.
  * **Words kept out of the report: four faults.** A Hindi word could be cut in
    half, printing a broken letter; removing a word from the middle of a caption
    left two commas; the dossier and the burned pictures never said what they
    had removed; and the list was not being saved with the rest of your setup.
  * **The page number is kept when you type a headline**, in every report.

## 2.0.18

Fixed

  * **Adding a section heading works properly now, and it was badly broken.**
    The box saved what you had typed after every single letter, so typing one
    heading saved seven, and deleting the "no heading" line saved nine more. It
    never asked, because it was writing while you were still typing.
  * Headings are added in their own window now, behind a "Headings" button, and
    nothing is saved until you press Add. The box beside it only chooses between
    headings that are already on the list.
  * The nine nonsense entries that got saved are cleared out the first time you
    open this version. Anything you added on purpose is kept.
  * **The box under the cover page can be read.** Its heading was being printed
    in the same colour as the panel behind it, so it was invisible. The whole
    box was the wrong colour for where it sits, and now matches the rest of the
    page.
  * **The drop-down lists in the preview window can be read.** The line you had
    chosen was drawn in exactly the colour of the strip behind it - the same
    colour, not merely similar - so the one line you most needed to see was the
    one you could not. Newspaper, edition and section were all affected, and so
    was the list of suggested newspaper names.
  * **The page number is no longer thrown away when you type a headline.** It
    was read correctly and printed correctly until somebody typed over the
    clipping, and then it silently disappeared - which is exactly when it
    mattered. Both reports keep it now. A headline that already names a page
    does not get a second one.
  * Correcting a newspaper or edition name is one undo step again, not one per
    letter typed.

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
