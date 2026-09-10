Fonts bundled with the application.

The PDF and Word exports need a face that can set Devanagari, so a Northern
Railway masthead like "दैनिक जागरण" never comes out as empty boxes or with its
vowel signs in the wrong place. The face travels inside the application rather
than being looked for on the PC, so a report built on one machine looks the same
as a report built on another.

WHAT IS HERE, AND WHY IT CAN BE

    Noto Sans Devanagari, in every weight and width.

It is licensed under the SIL Open Font License 1.1, and OFL.txt beside this file
is that licence. The licence requires the text to travel with the font, which is
why it is committed here rather than kept somewhere tidier.

NO MICROSOFT FONT IS HERE, AND NONE MAY BE PUT HERE

During development this folder held Devanagari.ttf, a copy of Windows' own
Mangal, as a stand-in. Mangal is a Microsoft font and must not be redistributed;
it was replaced with Noto before the first packaged build and must never come
back. This note used to describe that swap as still to be done, which - once the
project became a public repository - read as a confession that a Microsoft font
was sitting in it. It is not, and never was in any shipped copy.

WHICH OF THESE IS ACTUALLY USED

Two files: NotoSansDevanagari-Regular.ttf and NotoSansDevanagari-Bold.ttf. Both
the screen (ui/theme.py) and the PDF (export/build_pdf.py) name the weight they
want rather than taking whatever sorts first - taking the first file gave
"Black", and every Hindi masthead came out in the heaviest weight there is. The
other thirty-five faces are here because they arrive together in Google's
download and cost nothing to keep; the packaged build carries only the two.

If the folder is empty the system fonts are the fallback, and on a PC without a
Devanagari face a Hindi name prints as empty boxes.

If a face is ever added here, check its licence permits redistribution and put
that licence in this folder beside it.
