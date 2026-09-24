"""Which font sets Hindi, everywhere this program sets Hindi.

Not to be confused with :mod:`devanagari` next door, which is about the letters
themselves - reading Hindi back out of a PDF that stored it as glyph numbers.
This module is only ever about which typeface draws them.

Four places used to name a Devanagari face, and they named different ones. The
screen asked for Noto Sans Devanagari, Nirmala UI or Mangal and then, failing
all three, for whatever family Qt said covered Devanagari - which is sorted by
name, so a machine without those three set every masthead in Adobe Devanagari
or Khand Bold because those sort early. The cover named six. The PDF named
three, in CSS. Word named exactly one, Nirmala UI, with nothing behind it. A
machine that happened to be missing the one a given place named fell back to
something nobody chose, or to empty boxes.

They all come here now. The list below is every Devanagari face worth naming,
in the order a newspaper report wants them: the one carried inside this build
first, because it is the only one that is certainly there; then the plain
reading faces Windows ships; then the calligraphic ones, which set Hindi
perfectly well but are a poor choice for a page of body text, so they are
wanted only when nothing plainer exists; then the faces other systems and
other offices have.

The list is a PREFERENCE and never a test. Anything else this machine has that
covers Devanagari still counts, and comes after the named ones - the test is
whether a family covers the script, which Qt already knows.
"""

from __future__ import annotations

from typing import Optional

#: Ours, carried inside the build. First everywhere, because it is the only
#: face that is certainly present - a packaged copy on a fresh machine has it
#: whether or not anything is installed.
BUNDLED = "Noto Sans Devanagari"

#: The plain faces: what a page of news should be set in.
PLAIN = (
    "Nirmala UI",        # every Windows since 8, and the one Word is told
    "Noto Serif Devanagari",
    "Mangal",            # the old Windows default, still on many office PCs
    "Sanskrit Text",
    "Shobhika",
    "Annapurna SIL",
    "Samyak Devanagari",
    "Lohit Devanagari",
    "Devanagari MT",         # macOS
    "Devanagari Sangam MN",  # macOS
    "Kohinoor Devanagari",   # macOS
    "FreeSerif",             # Linux, and anywhere GNU fonts are installed
    "Noto Sans",             # its Devanagari is a separate family, but harmless
)

#: The calligraphic ones. They are Devanagari faces and they draw every glyph,
#: but they are handwriting, not news type - wanted only when there is nothing
#: plainer on the machine at all.
CALLIGRAPHIC = ("Aparajita", "Utsaah", "Kokila", "Adobe Devanagari")

#: Everything named, best first.
FACES = (BUNDLED, *PLAIN, *CALLIGRAPHIC)

#: What Word is told when nothing can be worked out. Nirmala UI ships with
#: every Windows from 8 onwards, including the Single Language editions the
#: office runs, so it is the name most likely to mean something on whichever
#: machine the .docx is opened on - which is not this one.
WORD_DEFAULT = "Nirmala UI"

_installed_cache: Optional[list] = None


def _covers_devanagari() -> list:
    """Every family on this machine that can set Devanagari, as Qt sees it.

    Answers nothing at all until there is a Qt application to ask through.
    Reading the font database before one exists does not raise - it ABORTS the
    process, with no traceback and nothing printed - and this module is read at
    import time by the exporters, which are imported from all sorts of places.
    Nothing is remembered from an unanswerable ask either, so the first one
    after the application is up gets the real list.
    """
    try:
        from PySide6.QtGui import QFontDatabase, QGuiApplication

        if QGuiApplication.instance() is None:
            return []
        systems = QFontDatabase.writingSystems
        return [family for family in QFontDatabase.families()
                if QFontDatabase.WritingSystem.Devanagari in systems(family)]
    except Exception:  # noqa: BLE001 - no Qt at all, or one that will not say
        return []


def forget() -> None:
    """Drop what was worked out about this machine. For tests, and for a font
    installed while the program is running."""
    global _installed_cache
    _installed_cache = None


def chain() -> list:
    """Every Devanagari face to try, best first.

    The named ones that this machine has, in the order above, and then anything
    else it has that covers the script. A font chain rather than one name: Qt,
    Word and MuPDF all walk a list, so a face that turns out to be missing a
    glyph - or missing altogether - costs nothing.
    """
    global _installed_cache
    if _installed_cache is not None:
        return list(_installed_cache)
    here = _covers_devanagari()
    if not here:
        # Nothing could be asked - no Qt yet, or a font database that will not
        # answer. Name every face there is rather than the one we carry: a
        # name that means nothing on this machine costs nothing, and a face
        # left out of the list cannot be used even where it exists.
        return list(FACES)
    known = set(here)
    named = [name for name in FACES if name in known]
    # The bundled face is registered by the program itself, so it is in `here`
    # once the fonts have been loaded and missing before that. Named anyway:
    # asking for a font that is not there is how a chain is supposed to work.
    ordered = named if BUNDLED in named else [BUNDLED, *named]
    if not named:
        # This machine has Devanagari faces and not one of them is a face
        # anybody here has heard of. Take the lot: an unknown face that draws
        # the glyphs beats a known name that is not installed. Only in this
        # case, though - on an ordinary machine the tail would be a dozen
        # display weights of Poppins behind the face actually wanted.
        ordered = [*ordered, *here]
    _installed_cache = list(ordered)
    return list(ordered)


def best() -> str:
    """The one face to use where only one can be named."""
    return chain()[0]


def css(*, quoted: bool = True, all_known: bool = False) -> str:
    """The chain as a CSS font-family value, for the PDF.

    ``all_known`` names every face in the list rather than the ones this
    machine has, which is what the report wants: a PDF should not come out
    differently because it was made on a different desk, the face that
    actually draws the Hindi is the one embedded in the file, and a name
    nothing can resolve is simply passed over.

    Ends in sans-serif so MuPDF has somewhere to go when it recognises none of
    the names - which is what it did before any of this existed.
    """
    names = []
    for name in (FACES if all_known else chain()):
        names.append(f"'{name}'" if quoted and " " in name else name)
    names.append("sans-serif")
    return ", ".join(names)


def for_word() -> str:
    """The single face name written into a .docx for Devanagari text.

    ONE name, because that is all w:cs takes - and it is read on somebody
    else's machine, not this one, so what is installed here is only a hint.
    Nirmala UI is named whenever it is plausible, because it is the face the
    reader is most likely to have; this machine's own best face is named only
    when even that is missing here, which says the machine is unusual and its
    own answer is the better guess.
    """
    here = chain()
    if WORD_DEFAULT in here:
        return WORD_DEFAULT
    for name in here:
        # Never the bundled one: it is inside THIS program, not on the machine
        # the document is opened on, so naming it would leave Word with a name
        # it has never heard of.
        if name != BUNDLED:
            return name
    return WORD_DEFAULT
