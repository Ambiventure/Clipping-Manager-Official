"""Build the packaged application.

    .venv\\Scripts\\python.exe build.py            # folder build (recommended)
    .venv\\Scripts\\python.exe build.py --onefile  # single .exe as well
    .venv\\Scripts\\python.exe build.py --zip      # folder build, zipped for copying

The folder build is the one to hand out. A single-file build of a Qt application
unpacks a couple of hundred megabytes into a temporary folder on every launch,
which for a tool opened each morning means a long wait before anything appears;
the folder build starts at once. The single file is convenient for emailing, and
nothing else.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
APP = "Clippings Manager"
# Everything from packaging/ that travels in the folder. The setup notes and the
# checker are for a machine that has never run this before, so they have to be
# inside the hand-over copy rather than sent separately - a note that arrives in
# a different email is a note nobody has when they need it.
README = "READ ME FIRST.txt"
CHANGES = "WHAT'S NEW.txt"
HANDOVER = (
    README,
    "BEFORE YOU START - setting up a new PC.txt",
    "Check this PC.cmd",
)


def _asked_release() -> str:
    """A version given on the command line, if one was: --release 2.0.0."""
    import re as _re

    if "--release" not in sys.argv:
        return ""
    at = sys.argv.index("--release")
    if at + 1 >= len(sys.argv):
        raise SystemExit("  --release needs a number, e.g. --release 2.0.0")
    asked = sys.argv[at + 1].strip()
    if not _re.fullmatch(r"\d+\.\d+\.\d+", asked):
        raise SystemExit(f"  {asked!r} is not a version like 2.0.0")
    return asked


def bump_patch(current: str) -> str:
    """1.7.1 -> 1.7.2. The first two numbers are a person's decision."""
    parts = (current or "0.0.0").split(".")
    while len(parts) < 3:
        parts.append("0")
    try:
        parts[2] = str(int(parts[2]) + 1)
    except ValueError:
        parts[2] = "1"
    return ".".join(parts[:3])


def _write_version(release: str) -> None:
    """Put the new number back into version.py, so the source says it too."""
    target = ROOT / "clippings_manager" / "version.py"
    text = target.read_text(encoding="utf-8")
    import re as _re

    text = _re.sub(r'__version__ = "[^"]*"',
                   f'__version__ = "{release}"', text, count=1)
    target.write_text(text, encoding="utf-8")


def read_stamp() -> dict:
    """The stamp as it stands, without writing a new one."""
    target = ROOT / "clippings_manager" / "_buildstamp.json"
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": "0.0.0", "built": "unbuilt", "digest": ""}


def write_stamp() -> dict:
    """Record which build this is, before anything is packaged.

    Two laptops disagreeing about an exported report is a question nobody could
    answer, because nothing said which build made it. The digest is of the source
    itself, so identical code on two machines carries an identical stamp and
    different code never does.
    """
    sys.path.insert(0, str(ROOT))
    from clippings_manager import version

    previous = read_stamp()
    # The last number goes up by one on every packaged build, and the source
    # file is rewritten so it always says what the latest build was. Nobody
    # decides, nobody forgets, and two builds can never share a number.
    #
    # The first two numbers ARE a decision, and this is how it is made:
    #     python build.py --zip --release 2.0.0
    # Asked for by hand, so a jump like 1.7 to 2.0 is deliberate and shows up
    # in the shell history rather than being an unexplained edit to a file.
    release = _asked_release() or bump_patch(
        previous.get("version") or version.__version__)
    _write_version(release)
    # AFTER the version is written, not before. Taking it first meant the digest
    # described the source as it stood one version ago, so it never matched the
    # code that actually shipped - which defeats the whole point of it: two
    # builds of identical code should carry the same stamp and two builds of
    # different code never should.
    digest = version.source_digest()
    stamp = {
        "version": release,
        "built": date.today().strftime("%d.%m.%Y"),
        "digest": digest,
    }
    target = ROOT / "clippings_manager" / "_buildstamp.json"
    target.write_text(json.dumps(stamp, indent=2), encoding="utf-8")
    _write_version_resource(stamp)
    _write_update_notice(stamp)
    print(f"  version {stamp['version']} · {stamp['digest']} "
          f"(packaged {stamp['built']})")
    return stamp


def _write_update_notice(stamp: dict) -> None:
    """The file a copy in the field reads to learn a newer one exists.

    Written TWICE, on purpose. One copy goes into dist/ beside the zip, which is
    where somebody looks while handing a build over. The other goes to the top
    of the source tree, because that is the ONLY place the Check for updates
    button actually reads - it fetches
    raw.githubusercontent.com/<owner>/<repo>/<branch>/latest.json.

    The build writes the second one rather than leaving it to be copied across,
    because forgetting it fails silently: every installed copy just goes on
    saying "nothing has been published to check against yet", which reads like
    the update check is broken rather than like a file was never committed.
    """
    import sys as _sys

    _sys.path.insert(0, str(ROOT))
    from clippings_manager.core import updates as _updates

    notice = _updates.notice_for(stamp)
    body = json.dumps(notice, indent=2) + "\n"

    beside_zip = ROOT / "dist" / "latest.json"
    beside_zip.parent.mkdir(parents=True, exist_ok=True)
    beside_zip.write_text(body, encoding="utf-8")

    to_commit = ROOT / "latest.json"
    to_commit.write_text(body, encoding="utf-8")

    print(f"  update notice  {to_commit}")
    print(f"     -> COMMIT latest.json and push it, or no installed copy will "
          f"ever see version {notice['version']}.")


def _write_version_resource(stamp: dict) -> None:
    """The properties Explorer shows, so the build can be read without running it.

    Right-click the executable, Properties, Details: version and build. On a
    machine whose reports look wrong, that is the quickest way to find out it is
    running last week's copy, without opening the application at all.
    """
    newline = chr(10)
    numbers = tuple(int(part) for part in stamp["version"].split(".")[:3]) + (0,)
    fields = [
        ("CompanyName", "Northern Railway"),
        ("FileDescription", "Clippings Manager - daily newspad"),
        ("FileVersion", stamp["version"]),
        ("InternalName", "ClippingsManager"),
        ("OriginalFilename", APP + ".exe"),
        ("ProductName", "Clippings Manager"),
        ("ProductVersion", stamp["version"]),
        ("Comments", f"{stamp['digest']} - packaged {stamp['built']}"),
    ]
    entries = [f"StringStruct({name!r}, {value!r})" for name, value in fields]
    lines = [
        "VSVersionInfo(",
        f"  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers},",
        "                    mask=0x3f, flags=0x0, OS=0x40004,",
        "                    fileType=0x1, subtype=0x0, date=(0, 0)),",
        "  kids=[",
        "    StringFileInfo([StringTable('040904B0', [",
        "      " + ("," + newline + "      ").join(entries),
        "    ])]),",
        "    VarFileInfo([VarStruct('Translation', [1033, 1200])]),",
        "  ]",
        ")",
    ]
    folder = ROOT / "packaging"
    folder.mkdir(exist_ok=True)
    (folder / "version_info.txt").write_text(newline.join(lines) + newline, encoding="utf-8")


# ------------------------------------------------------------- what changed

def write_changes(target: Path, stamp: dict) -> bool:
    """Render packaging/changes.md into the folder, as plain text.

    The source is written for the people who use the program - what is different
    when they sit down at it, not what was edited - and this only formats it and
    stamps the build on top. Returns False when the version being built has no
    entry, so the caller can say so loudly rather than shipping last version's
    list under this version's number, which is the one way a change log is
    worse than no change log at all.
    """
    newline = chr(10)
    source = ROOT / "packaging" / "changes.md"
    version = stamp.get("version", "")
    if not source.is_file():
        return False

    body, keeping, found = [], False, False
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            # Everything from the first version heading onwards is the log; the
            # preamble above it is a note to whoever writes the entries.
            keeping = True
            heading = line[3:].strip()
            if heading == version:
                found = True
            body.append("")
            body.append(heading)
            body.append("-" * len(heading))
            continue
        if not keeping:
            continue
        if line.startswith("---"):
            continue
        body.append(line.rstrip())

    while body and not body[0].strip():
        body.pop(0)

    width = 79
    head = [
        "WHAT'S NEW IN CLIPPINGS MANAGER".center(width).rstrip(),
        "",
        f"You are running version {version}, built {stamp.get('built', '')}.",
        "",
        "This lists what changed in each version, newest first. It is written",
        "in plain English on purpose - it says what is different when you sit",
        "down at the program, not what was changed inside it.",
        "",
        "=" * width,
    ]
    if not found:
        head[2:2] = [
            "",
            f"NOTE: version {version} has no entry below. It is a rebuild of the",
            "version above it, or its notes were not written before it was made.",
        ]
    (target / CHANGES).write_text(
        newline.join(head + body) + newline, encoding="utf-8")
    return found


def run(command: list[str]) -> None:
    print("  " + " ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(f"build failed: {' '.join(command)}")


def folder_build() -> Path:
    stamp = write_stamp()
    print("Building the folder application…")
    run([sys.executable, "-m", "PyInstaller", "ClippingsManager.spec",
         "--noconfirm", "--clean"])
    target = DIST / APP
    for name in HANDOVER:
        shutil.copy(ROOT / "packaging" / name, target / name)

    # The licences go in the zip, not just in the repository.
    #
    # The packaged copy carries Qt (LGPL), MuPDF (AGPL) and Noto Sans
    # Devanagari (SIL OFL), and every one of those licences says the text has
    # to accompany a copy that is handed on. That was arguably academic while
    # this went to one department on a USB stick. It stops being academic the
    # moment the zip is a public download, and a missing LICENSE is the kind of
    # thing nobody notices until somebody else does.
    for name in ("LICENSE", "THIRD-PARTY-NOTICES.md"):
        source = ROOT / name
        if source.is_file():
            shutil.copy(source, target / name)
        else:
            print(f"  !  {name} is missing from the project root - the "
                  f"hand-over copy will go out without it.")

    # The change log travels with it, rendered fresh from one source so it can
    # never drift out of step with the version on the executable.
    if not write_changes(target, stamp):
        print("")
        print("  " + "!" * 66)
        print(f"  !  There is no entry for {stamp['version']} in "
              f"packaging/changes.md.")
        print("  !  The copy that goes out will say so rather than pretend,")
        print("  !  but somebody should write one line about what changed.")
        print("  " + "!" * 66)

    # assets/fonts was always meant to carry a Devanagari face - its README says
    # so, and says which one - and it never got one. Without it the application
    # borrows whatever the machine has, so Hindi names are correct on a machine
    # with the Hindi fonts and empty boxes on one without. The exported PDF is
    # safe either way, because MuPDF carries its own face; the screen and Word
    # are not. Said at every build, because a thing nobody is reminded of is a
    # thing that stays undone for months.
    fonts = ROOT / "clippings_manager" / "assets" / "fonts"
    if not (list(fonts.glob("*.tt[fc]")) + list(fonts.glob("*.otf"))):
        print()
        print("  NOTE: no Devanagari font is bundled "
              "(clippings_manager/assets/fonts is empty).")
        print("        Hindi will be correct in the exported PDF and JPEGs on any")
        print("        machine, but on screen and in Word it needs the machine's")
        print("        own Hindi fonts. Drop NotoSansDevanagari-Regular.ttf (SIL")
        print("        Open Font License) into that folder to make it certain -")
        print("        nothing else needs changing.")
        print()

    # Whatever hand-over copies were here belong to an older build. Leaving one
    # beside a fresh folder is how the wrong build gets handed over.
    for old in stale_archives(stamp):
        old.unlink()
        print(f"  removed the stale hand-over copy: {old.name}")
    return target


def onefile_build() -> Path:
    write_stamp()
    print("Building the single file…")
    run([
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--windowed", "--noconfirm", "--clean",
        "--name", APP + " (single file)",
        "--add-data", "clippings_manager/config;clippings_manager/config",
        "--add-data", "clippings_manager/_buildstamp.json;clippings_manager",
        "--add-data", "clippings_manager/assets/fonts;clippings_manager/assets/fonts",
        "--hidden-import", "win32com.server.policy",
        "--hidden-import", "win32com.server.util",
        "--hidden-import", "pythoncom",
        "--hidden-import", "pywintypes",
        "clippings_manager/main.py",
    ])
    return DIST / f"{APP} (single file).exe"


def stale_archives(stamp: dict) -> list[Path]:
    """Hand-over copies left over from an earlier build.

    This is the one that got away. A folder build overwrote
    dist/Clippings Manager/ and left dist/Clippings Manager.zip untouched, so the
    only copy-ready artifact in the tree stayed at whatever it was last time
    --zip was passed. Someone copying "the app" to another machine copied the
    zip, which is how a laptop ended up running a build three hours older than
    the one it was checked against - and there was nothing to say so.

    Anything that does not carry this build's stamp in its name is stale by
    definition, so it goes.
    """
    keep = archive_name(stamp)
    return [path for path in DIST.glob("*.zip") if path.name != keep]


def archive_name(stamp: dict) -> str:
    """The version is in the file name, and nothing else.

    No date: the version already counts up on every build, so it says on its own
    which of two copies is newer, and a dated name puts two different builds
    from one afternoon under the same label.
    """
    return f"{APP} {stamp['version']}.zip"


def make_zip(folder: Path, stamp: dict) -> Path:
    archive = DIST / archive_name(stamp)
    print(f"Zipping {folder.name} -> {archive.name} (this takes a minute)…")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in folder.rglob("*"):
            if path.is_file():
                zf.write(path, Path(APP) / path.relative_to(folder))
    return archive


def main() -> int:
    stamp = read_stamp()
    folder = folder_build()
    size = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
    print(f"\n  {folder}  ({size / 1_000_000:.0f} MB)")

    if "--onefile" in sys.argv:
        single = onefile_build()
        print(f"  {single}  ({single.stat().st_size / 1_000_000:.0f} MB)")

    stamp = read_stamp()
    if "--zip" in sys.argv:
        archive = make_zip(folder, stamp)
        print(f"  {archive}  ({archive.stat().st_size / 1_000_000:.0f} MB)")

    print(
        "\nCheck the build before handing it over:\n"
        f'  "{folder / (APP + ".exe")}" --selftest\n'
        "\nTo make a copy for another machine:\n"
        f"  {Path(sys.executable).name} build.py --zip\n"
        f"  -> dist/{archive_name(stamp)}\n"
        "The build is in the name, and the application shows the same line in\n"
        "its title bar, so two machines can be compared at a glance.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
