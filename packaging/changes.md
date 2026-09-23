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

## 2.0.45

Added

  * **Two buttons on the edge of the preview window.** Copy the clipping's
    picture to the clipboard - as it prints, so a trimmed or turned clipping
    copies trimmed and turned - ready to paste into WhatsApp, an email or a
    document.
  * **And put a copy of the clipping into another newspad.** Choose any of the
    other three; the menu says how many clippings each one holds. It is a
    copy: the clipping stays where it is, and the one you sent is waiting when
    you switch to that newspad. A clipping on the sentiment board arrives on
    that newspad's board.

## 2.0.44

Fixed

  * **A post on X with a video in it comes out as its picture again.** It was
    coming out as a grey box saying "The media could not be played", with the
    writing and the headline gone with it - the whole card, not just the
    picture. Facebook's and Instagram's video posts were never affected.
  * **The window no longer jumps wider when Collect is switched on.** On a
    window taking half the screen it grew past the right-hand edge, because
    the line that says what Collect is doing was asking for a width of its
    own. Two other lines that could have done the same have been dealt with
    too.
  * **The cover panel now looks switched off when it is.** Turning off Enable
    Cover Page fades everything below it and says "no cover page will be
    printed" beside the switch.
  * **The tick boxes in the print order window can be seen.** They were the
    same colour as the row behind them.
  * **The border round the dossier's export bar goes all the way round.** The
    orange line ran along the top and stopped dead at the corner.
  * **The sideways scroll bar matches the rest of the program** - a grey pill
    instead of Windows' hollow rectangle with arrows at each end.

## 2.0.43

Added

  * **Five names of your own for the file.** Beside Standard name there is now
    My names: pick one and it goes in the box with the date on the end. Edit
    my names keeps five, and they are there the next morning.
  * **A switch that turns the cover page off.** On the cover panel, beside
    Reset: off and the report has no cover sheet at all - the first clipping
    is page one. What you have set up on the panel is kept either way.
  * **Group by platform**, on the heading and layout panel. Every Facebook
    post together, every Twitter post together, every Instagram post together,
    each run headed once with the platform's name in the size and colour set
    on that panel. Newspaper stories are not moved, and Ctrl+Z puts the order
    back. The headings print in the press report and in the dossier alike, and
    can be renamed - TWITTER to X, say - on the headings list.
  * **A Clear all in the links window**, and the window closes itself once the
    whole message has gone through. It stays open if anything failed, so
    nothing goes unseen.
  * **Every link is numbered as you paste it**, and the line above the list
    says what they are: "16 links found: 3 Facebook, 4 Twitter, 5 Instagram,
    4 news sites".
  * **A How this works on the Show and Arrange strip** - what each half does,
    how the rows stack, and why neither of them changes the report.

Changed

  * **Clear all on the sentiment board is at the top**, beside the count of
    what it would clear. It was down among the export buttons.
  * **The seven counts on the sentiment board are small coloured pills** on
    the line that already says how many clippings the division has, instead of
    a band of tiles taking up most of the first screenful.

## 2.0.42

Fixed

  * **A link from Facebook's Share button is captured.** Most of the Facebook
    links that arrive on WhatsApp are the short "facebook.com/share/p/…" kind,
    and every one of them was being put down as "not public" even when the
    post was there and public. The short link stands for a post without naming
    it, so the program now opens it once to see which post it is, and asks for
    that post's card. Still with nobody signed in to anything.

## 2.0.41

Changed

  * **A post is captured without signing in to anything.** X, Facebook,
    Instagram, Threads and LinkedIn all publish a post a second way - the card
    a newspaper quoting it puts in its own page - and that is what the program
    now asks for. No wall, no feed round the edge, no "open in the app" bar,
    and nothing of yours in the program.
  * **The cutting is the post and nothing else**, drawn at the width the site
    draws its own card at, so an upright photograph no longer comes out with a
    black band down each side.
  * **The link on the clipping is still the post's own**, exactly as it was
    sent. Only what the program opens has changed.
  * A link copied on a phone opens the way a computer asks for it, so no page
    offers to open itself in an app.

Fixed

  * **A post that is not public is now said to be that**, instead of being put
    down as needing a sign-in that would not have helped. If it was only ever
    shown to the writer's friends, or has been taken down, the count line
    offers to take it from your own Chrome.
  * Adverts and cookie notices are cleared once more, after a page's pictures
    arrive - which is when the late ones appear.
  * A page with no headline of its own is now named by its own heading where it
    has one, rather than by the wording on its tab.

## 2.0.40

Added

  * **Every report now carries a record of its own clippings.** A report made
    from today comes back whole when it is imported again - every name,
    heading, category and link exactly as it went out, including clippings
    whose name was never printed on the page.
  * **A report whose headlines were burned into the pictures comes back with
    them off again**, each name back in its own box. Word and PDF alike.

Fixed

  * **An old report of ours imports with its names.** A report named for a
    division - "Press Media Coverage Regarding Delhi Division..." - was read by
    that division's own rules. Delhi's and Lucknow's say the name is inside the
    picture, so every printed name was thrown away: 17 of 17 in the report sent
    in. Ambala's and Jammu's would have put each name on the wrong clipping.
  * **A name printed in Hindi comes back in Hindi.** "दैनिक जागरण दिल्ली" was
    arriving as "दैनə क जागरण दɘ Ėली". It is now read from the letters the page
    itself carries, and only when redrawing it gives that very page back.
  * **A long web address printed under a clipping is no longer read as the next
    clipping's name**, and no clipping takes the address of the one before it.
  * **The board's categories no longer take the wheel from the page.** With
    five categories the strip was wide enough to scroll sideways, and a notch
    over it slid the columns instead of moving the page.

## 2.0.39

Fixed

  * **One of our own reports comes back whole.** A report of ours that prints
    a heading part way down - ELECTRONIC MEDIA, SOCIAL MEDIA - came back with
    every clipping above that heading flagged "probably not a clipping" and
    its tick cleared. On the office's own 18.09.2026 report that was 239
    clippings of 254. They now arrive as what they are: ticked, named, and
    under the headings the report printed.
  * **A dossier from the sentiment board is known for one of ours** when it is
    imported, the Word file as well as the PDF. Its Word file carried no stamp,
    so its clippings came back under a stranger's rules.
  * **A category that printed "Nil - no clips" is not read as a clipping**, and
    its words are not read as the next clipping's name.

## 2.0.38

Added

  * **Advertisement is a category of its own** on the sentiment board, beside
    Digital news. It has everything the other categories have: cards with a
    headline bar and Add URL, dragging in and out, its own count, its own
    colour, and a place in the dossier.
  * **Print order**, on the sentiment page's Heading & Document Layout card.
    Drag the five categories into the order you want the dossier to read in.
  * **A switch in front of each category there.** On, and the category is
    printed even when it is empty - it says "Nil - no clips". Off, and it is
    left out of the dossier altogether.
  * **A switched-off category says what it left out** after the export, so a
    category switched off months ago cannot quietly drop today's clippings.

Changed

  * **An advertisement is no longer filed under Digital news.** Anything
    already filed as an advertisement moves to the new category.

Fixed

  * **The next clipping after a priority is the one that was below it**, even
    when you press a second bubble or change your mind. It used to take you to
    the clipping now shown as No. 2, which you had already seen. On the
    sentiment board and in the press report alike.

## 2.0.37

Added

  * **Manage Newspaper List**, on the right-click menu of Collect from
    WhatsApp: every newspaper and city Collect already reads, with a search
    bar at the top.
  * **Papers from any state can be added**, with the other ways they are
    typed - Hindi, Punjabi, any language, or short, like DJ.
  * **A Cities list beside it**, for a town a caption names that Collect does
    not read yet.
  * **Names typed into clippings today are offered for the list**, one press
    to keep them.
  * **The list is kept for good** - for every newspad, after the program is
    closed, and through updates. It also travels with "Save my setup to a
    file".

Changed

  * **Collect's right-click menu is five lines.** Every option it had is still
    there, inside Options for this session.
  * **"Newspaper, city, page and division for this session" is now "Same
    newspaper for every photo".** It does the same thing.

## 2.0.36

Added

  * **A menu in the top left corner** - the three lines beside the logo. It
    holds Settings, the Duplicates Trainer, the zoom and Runs offline (where
    your files are kept, and updates).
  * **Settings, with a Clean up** that clears out what the program gathers
    over a long run, so it works as if newly installed.
  * **Clean up measures every clipping again for the duplicate check,**
    from scratch. The way duplicates are decided does not change.
  * **Clean up also empties the browser's saved pages** (your sign-ins stay),
    frees memory and deletes the program's own temporary files.
  * **Nothing you made is touched by Clean up** - no clipping, name, trim,
    priority, setting or saved newspad.

Changed

  * **The top bar holds only the newspad, the Press Report / Sentiment Board
    switch and Collect from WhatsApp.** It fits on one line on a laptop screen.

Fixed

  * **A clipping that is trimmed or turned is compared as it looks now.** The
    duplicate check went on using the picture from before the trim, so a
    clipping and its copy could be missed.

## 2.0.35

Added

  * **Keys 1 to 5 press the priority bubbles** in the preview window, and
    pressing the lit one's number takes the priority off. A number typed into
    a box - the Page box, say - is still just a number.

Changed

  * **The priority bubbles are the height of the other buttons** on the
    preview's bar.

Fixed

  * **Taking a priority off puts the clipping back at its own serial number.**
    On a morning carried over from an earlier version it stayed wherever the
    priority had lifted it to.

## 2.0.34

Changed

  * **The priority bubbles are round, flat and quiet** - an outline until you
    choose one, filled in its own colour when you do. They sat on a white
    block before.
  * **Priority now starts at none.** A clipping has no priority until you give
    it one, and everything with no priority sits under all five, in the order
    it came in. Nothing moves until you press a bubble.
  * **Press the lit bubble again to take the priority off.** The clipping drops
    back exactly where it came in.
  * **The list is always in priority order**: 1 first, then 2, down to 5, then
    everything unassigned - and inside each one, the order the clippings
    arrived in, or the order you dragged them into.
  * **The priority shows on the card** as a small number in its own colour, and
    only on the clippings you have given one to. It is never printed in the
    report.

Fixed

  * **Two different cuttings that happen to look alike are no longer called the
    same one.** A cutting with little in it but a masthead band and a few lines
    of type, or a picture with nothing in it at all, could be read as a repeat
    of another; the check now asks for far more agreement before the picture
    alone may decide, and refuses a picture that carries no detail whatever.

## 2.0.33

Added

  * **Five priority buttons at the top of the preview window.** Press 1 to 5
    and the clipping moves to that priority in the list - every 1 above every
    2, and so on down to 5 - so a morning can be put in order of importance
    without dragging anything.
  * **Clippings at the same priority keep the order you gave them,** and the
    arrows, the move pad and a drag move a clipping inside its own priority
    rather than out of it. Dragging a clipping into another priority's run
    gives it that priority, in one step that Ctrl+Z takes back.
  * **The next arrow goes on down the list after a priority is set,** to the
    clipping that was under the one just moved, not back up to where it
    landed. Setting a whole morning is a number and an arrow, a number and an
    arrow.
  * **The priority shows on the card,** as a small number on the corner of
    the picture - and nothing at all on a clipping still at the middle
    priority, which is where every clipping starts.

Fixed

  * **A report this program made can be imported again.** Every clipping came
    back flagged "probably not a clipping" and outside the export, in the Word
    report and in the PDF alike. The coverage summary's last page was being
    read as the document's first section heading, which made every picture in
    the report sit above it.
  * **A re-imported report comes back named and under its own headings** -
    newspaper, city and page from the caption printed above each clipping, and
    the sections from the headings printed over them. The cover is the only
    thing that is not a clipping, and it says so.
  * **The page number at the foot of the sheet is no longer read as part of
    the next caption** ("1 Hindustan Times, Lucknow, Page 2").
  * **The same cutting in two divisions' files is found more often, and more
    quickly.** Two mornings of verdicts from the Duplicates Trainer were
    measured against the check: it now finds every repeat those verdicts name,
    including three whose headlines could not be read at all, and flags none of
    the pairs they say are not repeats.
  * **Two cuttings inside one division's own document are no longer called
    repeats of each other** on their headlines. The division put both of them
    in; that was nine of every nine wrong flags in the labelled verdicts.
  * **Importing one division's file no longer reads a headline off every
    clipping in it** - about twenty seconds a file - because a repeat inside
    one file is not a repeat.

## 2.0.32

Added

  * **The six division short forms in a copied caption.** "HT LKO", "DB UMB
    4" or "LKO NBT" copied under a photo now names it - Hindustan Times,
    Lucknow - instead of printing the words as typed. LKO is Lucknow, MB
    Moradabad, UMB Ambala, DLI Delhi, JAT Jammu and FZR Ferozpur, either
    way round and with a page number. JAT and MB count only in capitals,
    because "Jat" and "mb" are ordinary words.
  * **Right-click Collect from WhatsApp for its options.** What it collects,
    how it reads a caption, where a photo goes, and what it does when a copy
    is not used. A tick can be set without the menu closing.
  * **Collect's options last until the program is closed, and are never
    saved.** While any is changed, the Collect bar lists them with Change…,
    and the button has an amber edge.
  * **Every photo Collect adds can arrive already named** with a newspaper,
    city, page and division for the session. A copied caption still replaces
    the name, and what it leaves out is kept. On a sentiment board showing
    one division, a card keeps that division, and the bar says so.
  * **A city on its own can be a caption** - "LKO" or "Lucknow page 3" - with
    the newspaper left for you to type, or taken from the session's.
  * **A caption with a division's short form files the clipping under that
    division** when it has none. A card on the sentiment board keeps the
    division the board is showing, and the bar says so.
  * **More ways to pair a caption with its photo.** A new caption can replace
    one already copied, a caption copied just before its photo can go on it,
    or a caption can go on the one clipping ticked in the press report. A
    caption copied before a photo that was not taken - too small, or its
    address copied instead - is never put on the photo after it by itself.
  * **Choose how links are captured.** The links window has "Capture with:
    Browser inside the app / My Chrome", and one Capture button that uses
    the choice - "Capture 4" in the background, or "Take 4 from Chrome". The
    choice is remembered.
  * **Right-click either way for more,** or press the ⋯ beside them. Browser
    inside the app: open the browser at the links, sign in to X, Facebook or
    Instagram, see what is saved, sign out. My Chrome: take the ticked links
    now, take only the posts that need a sign-in, and whether the trim opens
    after each picture.
  * **Each link in the list says what happened to it** - waiting, capturing,
    ✓ with its clipping's number and which way took it, ✕ with the reason, or
    "needs a sign-in". The marks stay when more links are pasted, and a
    captured clipping that is undone gives its link back.
  * **Right-click a link in the list** to capture just that one, take it from
    your Chrome, open it in the browser inside the app or in your Chrome, or
    show its clipping. Double-click opens it in the browser inside the app.
  * **Posts that hit a sign-in wall get two ways past it** in the line under
    the box: sign in to that site in the browser inside the app, or take
    them from your Chrome. Both are links that do it.
  * **The browser inside the app goes through the message's links.** A strip
    shows Previous, "3 of 12 · site · headline" (pick any) and Next, whether
    this link is captured yet, and "Then open the next link", which is on.
    Alt+PgDown and Alt+PgUp move between links; Ctrl+Enter captures.
  * **Capture this page pictures the page as you see it,** without loading
    it again: its pictures have loaded, and a pop-up you closed stays
    closed. It is filed under the link from the message, with the sender's
    words, and the links window ticks it off - also when the link goes on to
    another address, as youtu.be, fb.watch and twitter.com links do.
  * **A page that is not the message's link is filed as a clipping of its
    own** - another video or post that YouTube or Facebook moves on to, or
    the page left open after its link was deleted from the list - and the
    link that was sent stays waiting. Next then opens the link that came
    after the deleted one.
  * **Closing the browser while it captures closes it at once.** The capture
    is dropped, and its link is not marked as failed.
  * **The browser's ☰ panel shows your sign-ins and what the sites keep.**
    Each signed-in site has Sign out, and the panel says plainly that no
    passwords are stored. Every site that keeps data is listed with how
    much and until when, with Remove. Site permissions have Forget. There is
    also Clear stored pages and pictures, Forget visited pages, and Remove
    everything.
  * **Sign in from the ☰ panel and press Next ›** to come back to the post
    that asked for the sign-in.
  * **The program's own hidden Chrome's sign-ins are listed in that panel
    too,** and can be removed. Your everyday Chrome is never read. While
    that Chrome is open, the panel says so rather than showing nothing.
  * **The browser has a forward button and a loading bar.** "Sign in with
    Google" and other sign-in pop-ups open in a small window of their own,
    and a site asking for your location, camera or notifications is refused.
  * **A page that stops responding in the browser says so,** with Reload and
    Skip to the next link.
  * **A link dragged onto the window, the clippings list or a sentiment
    column opens the links window with the link in it.**
  * **A link dropped on the browser's address bar opens at once,** and so does
    one pasted into an empty address bar. Right-click the bar for Paste and
    go.
  * **Expand on a sentiment category shows it as the press report's list.**
    The same rows, file brackets, move buttons and pills, numbered as the
    cards are, and the set-up scrolls away so the list has the window.
  * **Show all, All four or the category's bubble brings the four columns
    back** exactly as they were, in the order made in the list.
  * **Tick, Shift-click, Select all and Ctrl+A work in an opened category,**
    and the navy bar acts on its ticks. Every change there is one Ctrl+Z on
    the board and never touches the press report.
  * **Move to on the bar lists the other three categories first,** then the
    category's files. Right-click a row for Move to category.
  * **Drag rows within an opened category,** and every other category and
    division keeps its order.
  * **Drop rows on another category's bubble** to move them there.
  * **Type headlines down an opened category.** Enter or Tab goes to the next
    clipping in that category, Up goes back, and Esc leaves it.
  * **Hindi to English and Filter and arrange work on one category** from
    the bar over its list.
  * **A picture pasted, dropped, dragged from a browser or added while a
    category is opened lands in that category,** at the top of its loose
    clippings, with its headline box open in the list.
  * **A photo Collect from WhatsApp adds to an opened category is brought
    into view in its list.** One Collect's options send to another category
    leaves the list where it is, and the bar says where it went.
  * **The preview opened from a category walks that category,** counts only
    its clippings, and Delete there shows its next one.
  * **Check for Duplicates, Preview and Delete Duplicates and Check
    automatically work in an opened category,** on that category's
    clippings: the red badge on its rows, the repeat beside it in the
    preview, and every delete one Ctrl+Z on the board. Pressed while the
    other list is being checked, it says so and checks its own list next -
    or says it was not run, if another category is opened before its turn.
  * **A link captured while a category is opened is named by its number in
    that category,** or by the column it went into when that is another one.

Fixed

  * **A card moved to another column comes back with one Ctrl+Z.** A card
    with no division, moved while one division was showing, used to need
    two: the first left it in the column it had been sent to.
  * **The Filter and arrange strip's count stays right** after a delete, a
    Ctrl+Z, or a clipping moved to another category, instead of keeping the
    count from when the filter was chosen.
  * **A filtered list no longer goes blank with the filter looking off.** When
    the last clipping of a chosen paper moves to another category, is
    deleted, is put in English or is given another paper, the filter lets
    that paper go and the list shows everything again. Before, the list
    stayed empty with Show all again greyed out until the strip was shut.
  * **A paper brought back by Ctrl+Z is offered in Filter and arrange again**
    at once, in both interfaces. Its filter is not put back on by itself: a
    paper's last clipping deleted and brought back shows the whole list, and
    the paper can be picked again.
  * **Right-click in an opened category under a filter acts only on the
    clippings you can see.** Exclude, Set newspaper, Set edition, Delete and
    Move to category all take the ticked ones on screen, or the one clicked
    when none of those is ticked, and say how many. Ticked ones the filter
    hides are counted at the top of the menu and left alone, and Merge waits
    until the filter is cleared.
  * **A story link copied while Collect is on goes to the links list when no
    photo is waiting for it** - before any photo, or after the photo's
    caption - instead of being lost when the next photo came. The links
    window opens when you come back to the program, never over WhatsApp,
    and the links already in it stay. After a caption, "Put the link on"
    is still offered, and a link put on the photo that way comes back out
    of the list.
  * **Ctrl+V of a story link while Collect is on opens the links window,**
    instead of saying that Ctrl+V is not needed. A link Collect has already
    put on a photo or in the list is not listed a second time.
  * **Collect's messages about a card on the sentiment board start with a
    capital letter.**
  * **Every link pasted or dragged into the links window goes on a line of
    its own,** so the next paste is always read as its own link. No blank
    lines are left, an address is never cut in two, the words written over a
    link stay with that link, and one Ctrl+Z takes a whole paste back.
  * **A second link pasted with Ctrl+V while the links window is open is
    added under the first,** instead of taking its place.
  * **Dragging a link from Chrome no longer says "Nothing came with that
    drop".**
  * **A site you only visited is no longer shown as signed in.** Opening
    x.com used to be enough to show "Signed in: x.com".
  * **Two links pasted with nothing between them are two links.** Run
    together, they used to be taken as one address that went nowhere; each
    is now its own story in the links list, an Instagram or Facebook share
    link as well as a newspaper's.
  * **Two links copied together under a photo are no longer put on it as
    one.** Collect used to join them into an address that went nowhere; it
    now leaves the photo alone and says the copy had more than one web
    address.
  * **A link's cutting no longer stops at an advert.** An "Advertisement"
    strip between the standfirst and the photo is taken out and the story
    closes up, so an India Today cutting keeps its photo, caption and first
    paragraph. Nor does a cutting stop at the photo's caption on a site that
    styles its first paragraph as the introduction.
  * **A headline laid over its photo is kept, with the photo.** Such a
    headline used to be taken for a pop-up and removed - especially one
    about advertising - and the page was printed without it.
  * **Headlines are no longer clipped at the right or the left.** A cutting
    is never narrower than its headline: one centred over the story and its
    side column (Economic Times) comes out whole, with the side column
    blanked beside the story, and a headline at the very edge of the page
    gets a clean white margin.
  * **Photos are waited for.** A cutting waits, up to a few seconds, for the
    story's photos - late ones, ones that load only when scrolled to, and a
    post's photos and link-card pictures - instead of printing empty boxes.
  * **No half lines at the edges.** The bottom of a cutting no longer shows
    the top half of the next line of text, and the top no longer shows the
    bottom half of the small heading over the headline. A very long page no
    longer ends through the middle of a line.
  * **The edges added round a cutting match the page.** A white story on a
    grey page stays white under its last line, and a page with a light grey
    background no longer gets black bars.
  * **A story or post that the page puts up a moment after it opens is waited
    for**, instead of the page's grey "Loading" box being captured, or the
    post being called one that needs a sign-in.
  * **A page's own message boxes no longer stop a capture.** An "Ad blocker
    detected" box that a page pops up is answered without being shown. In
    the browser inside the app it used to open in the corner of the screen,
    stop the whole program, and fail the next link as well.
  * **Pop-ups are taken off before the picture.** Ad-blocker notices and
    "register to continue reading" boxes - even ones with a big heading of
    their own, however they are worded, in English or Hindi - cookie and
    notification prompts and their dark backdrops are removed, a page that
    was locked is let scroll, and blur is taken off. The "Ad blocker
    detected" box on Economic Times comes from the ad-blocker in your own
    Chrome; the program's browsers have none.
  * **A wallpaper advert behind a story stays out of its cutting.** The
    cutting is as wide as the story, not as wide as the advert painted
    across the page behind it.
  * **A link that passes through a "taking you to the story" page is
    followed to the story**, instead of capturing the page in between.
  * **A story that opens with a video prints the video's picture**, not the
    black box the player shows once it has started.
  * **A public X post is captured when X shows it signed out**, instead of
    being refused. When a post really does need a sign-in, the message now
    says to sign in to it in the browser inside the app, or take it from
    your Chrome.
  * **The browser inside the app takes the same cutting as Chrome.** No
    scrollbar strip at the edge of its cuttings any more.
  * **A page that stops responding fails only its own link**, in either
    browser. The rest of the list is captured, and so is the next list -
    even when a page stops responding a few seconds after its cutting was
    taken, which used to fail the next link, or every link after it in the
    browser inside the app until the program was closed.
  * **A link the browser inside the app stopped on is tried again with
    Chrome,** quietly, and marked "taken with Chrome" when that works.
  * **An "Ad-Blocker Detected" box from your own Chrome is explained.** My
    Chrome's help and its Take it panel say to close the box or pause the
    blocker for that site, or to use Browser inside the app, which has no
    blocker. Economic Times and Times of India links are marked with this
    in the list.
  * **Clear this division, pressed with a category opened out, says it clears
    every category in the division,** beside how many are in the list on
    show. It used to ask to remove 24 clippings over a list of four.
  * **With every division showing, Clear this division no longer calls it
    "__all__".** It asks to remove the clippings from the board.
  * **"Show it in its folder" opens the folder the report was saved into,**
    with the report selected, instead of Documents. It went wrong whenever
    the folder or the report's name had a space in it - which the report's
    name always does.

## 2.0.31

Added

  * **A browser inside the program, for links.** Links are captured by the
    program's own browser now: sign in there once - "Browser inside the
    app…" in the links window opens it, X and Facebook keep their sign-in
    in the program's own profile, never in your Chrome - and every capture
    after that is signed in. Twelve links are captured with nothing on the
    screen: the page that captures is parked off the edge of the desktop,
    and only the story, or the post, comes out - no tabs, no bookmarks bar.
    A page can also be captured by hand from that window ("Capture this
    page"). "Take from my Chrome" stays for a post nothing else can reach.
    The download is larger for it: the engine travels with the program.
  * **A coverage summary page.** Tick "Add a coverage summary page at the
    end" in the export window and the report ends with one page that counts
    the day up: how many clippings, of what kind (print, electronic,
    digital, social, advertisement), from which division, in which
    newspapers - and, when the sentiment board has been used, how the day
    split between positive, neutral and negative. In the PDF and the Word
    file alike; off unless you tick it.
  * **The file shown in its folder.** After an export, the PDF or Word file
    is selected in its folder in Explorer, ready to be dragged onto a mail
    or a chat. "Show it in its folder" in the export window, on by default,
    beside "Open when finished". File names carry the date as they always
    did.
  * **Pasted phone screenshots are tidied.** A screenshot pasted or
    collected from a phone loses its status bar (the time, the battery),
    its navigation bar or gesture strip, and any blank margin - as a crop,
    so the picture itself is untouched and Trim… then Whole picture puts
    them back. It is careful: a band is a bar only when it is thin, nearly
    one colour, holds a few small marks and stops at a plain edge; a
    newspaper scan is left alone. "Trim phone bars" on the Heading &
    Document Layout card switches it off.

## 2.0.30

Fixed

  * **A copied caption the program cannot take apart is printed as typed.**
    Collect used to refuse a caption it could not read as "newspaper, city,
    page" - "Not used" on the bar, and nothing on the photo. Now, when a
    photo is waiting and the copy is short and made of words, the words go
    into the photo's headline box exactly as written, so they print above
    the picture; the card is flagged amber because nobody has checked them,
    the bar says what happened and why the words were not read, and Ctrl+Z
    or "Undo that" takes it back. A longer copy is offered on a button
    ("Print it as typed on No. 7"). Still refused, as before: a single word
    (a copied password is a single word and must never land on a card), an
    address, chat, a copy that is mostly numbers, a pasted article, and two
    messages copied at once.
  * **Collect's scroll comes all the way.** The page is brought to the new
    photo once more after the list has finished laying it out, and stops
    clear of the bar that floats over the foot of the page.

## 2.0.29

Added

  * **The sentiment dossier's Word cover can be edited.** It used to go into
    the Word file as one picture. It is text now - each line in a text box
    Word can retype or drag, the emblem as a picture - the same arrangement
    the press report's cover already had, so a date or a division name can
    be corrected in Word without coming back here. The two pills keep their
    words and lose their rounded backgrounds; the border frame is not
    written. The PDF is unchanged: one picture, as printed.
  * **"What was copied…" on the Collect bar.** Every copy since Collect was
    switched on, what kind it was - a picture and its size, text and its
    shape - and what became of it: added as No. 7, caption copied onto No.
    7, not used and why, or nothing to do. Never the words themselves. A
    copy that held neither a picture nor text is now said on the bar as
    well, so a copy that goes nowhere is never a mystery.

Fixed

  * **Collect from WhatsApp now brings the page to the photo.** The list
    stands at its full height inside the page, so asking the list to scroll
    did nothing: a collected photo landed one row under the visible edge, and
    nothing seemed to happen. It is the page that moves now, once the new
    row has been laid out, and the photo sits at the foot of the view with
    the ones before it in sight above.
  * **A caption copied as formatted text only is read.** A copy that carried
    the words as markup with no plain-text copy of them used to go nowhere,
    silently. The words are read off the markup now.

## 2.0.28

Fixed

  * **The sentiment cover's size drop-downs painted black, with black type
    on them.** They are white now, with dark type, wherever they open.
  * **The size sits beside each line's text.** On the Division & Text tab,
    every text field - railway zone, division, title, subtitle, prepared by,
    additional notes - has its size box at the right of its own label; the
    separate "Text sizes" panel on the styling tab is gone. The notes line
    has a size of its own, apart from the prepared-by line, and the two
    footer lines offer small type only, since they sit close to the edge.

## 2.0.27

Added

  * **Text sizes on the sentiment dossier's cover.** The cover card's Logo &
    Styling tab now has a size for each line of the sheet - railway zone,
    division, title, subtitle, and the prepared-by and notes lines - in
    points, as they print. "Standard" is the size it always drew at, so a
    cover designed earlier prints exactly as before. A line set larger moves
    the lines under it down, so nothing prints through anything.

Fixed

  * **The Word report no longer spills a clipping onto the next page.** A
    caption that wraps to two lines - "NEW INDIA HERALD DELHI EDITION PAGE
    NO.1" at 18pt does - was given one line's room in the Word file, so the
    picture was a line too tall and Word moved it to the next sheet, leaving
    the caption alone above an empty page: a 257-clipping report ran to 267
    pages. Word is now told how tall the caption really is, measured with the
    same faces, as the PDF always was.
  * **A report the program made is trusted when it is imported again.** Its
    pictures were being judged by the rules meant for a division's document,
    so a wide website strip was flagged as an "extreme shape" and a small
    phone screenshot as "very small" - "probably not a clipping" on things
    that were clippings when they went out. The program's own PDF and Word
    files are recognised by the stamp they carry, and those two rules are not
    applied to them. A repeated picture is still flagged, and so is the cover.

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
