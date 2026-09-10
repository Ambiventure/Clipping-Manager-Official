"""Cut the round logo out of an artwork and build the application's icons.

    .venv\\Scripts\\python.exe tools\\make_icon.py "path\\to\\logo.png"

The supplied artwork is a circular badge sitting on a flat background. Everything
outside the circle has to go: an icon is shown against a taskbar, a title bar and a
dark or light Explorer background, and a white square around a round logo looks like
a mistake in every one of them.

So the background colour is read from the corners, the content's bounding box is
measured, the crop is squared off around it, and a circular alpha mask is applied -
supersampled, because a hard-edged circle at 16px looks chewed. Writes a PNG for the
window and a multi-resolution ICO for the executable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "clippings_manager" / "assets" / "icon"

# Windows picks the nearest of these; all of them live in the one .ico.
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
SUPERSAMPLE = 4


def content_box(image: Image.Image, floor: int = 26):
    """The bounding box of the logo itself.

    Not "everything unlike the corner pixel": the artwork sits on a faint
    gradient with a drop shadow and a watermark, and measuring against a corner
    swept all of that in - the box came out wider than the image was tall, so
    squaring it ran off the canvas and the icon picked up a black band.

    The logo is the only saturated thing in the picture, so colourfulness is the
    honest test. Everything neutral - the ground, the shadow, the watermark - is
    the same in all three channels; the badge is not.
    """
    pixels = numpy.asarray(image.convert("RGB")).astype(numpy.int16)
    spread = pixels.max(axis=2) - pixels.min(axis=2)
    mask = spread > floor
    if not mask.any():
        # A flat-coloured logo would defeat that, so fall back to "darker than
        # the corners", which is the other way a badge stands out.
        corner = int(numpy.median(numpy.concatenate([
            pixels[:2, :, :].reshape(-1, 3).mean(axis=1),
            pixels[-2:, :, :].reshape(-1, 3).mean(axis=1),
        ])))
        mask = pixels.mean(axis=2) < corner - 18
    if not mask.any():
        return None
    rows = numpy.where(mask.any(axis=1))[0]
    cols = numpy.where(mask.any(axis=0))[0]
    return (int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1)


def square_around(box, size) -> tuple[int, int, int, int]:
    """The largest square that holds the box and still fits on the canvas."""
    left, top, right, bottom = box
    width, height = size
    side = min(max(right - left, bottom - top), width, height)
    cx, cy = (left + right) // 2, (top + bottom) // 2
    left = max(0, min(cx - side // 2, width - side))
    top = max(0, min(cy - side // 2, height - side))
    return (left, top, left + side, top + side)


def round_off(image: Image.Image) -> Image.Image:
    """Make everything outside the inscribed circle transparent."""
    side = image.size[0]
    big = side * SUPERSAMPLE
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, big - 1, big - 1), fill=255)
    mask = mask.resize((side, side), Image.LANCZOS)
    out = image.convert("RGBA")
    out.putalpha(mask)
    return out


def already_cut(image: Image.Image) -> bool:
    """True when the artwork has been cut out already.

    A supplied cutout is better than anything measured here, so it is used as it
    is: re-cropping and re-masking a clean circle can only soften its edge.
    """
    if image.mode != "RGBA":
        return False
    alpha = numpy.asarray(image)[:, :, 3]
    corners = [alpha[0, 0], alpha[0, -1], alpha[-1, 0], alpha[-1, -1]]
    return max(corners) < 24 and (alpha > 200).any()


def build(source: Path) -> None:
    image = Image.open(source).convert("RGBA")
    if already_cut(image):
        side = min(image.size)
        crop = image.crop(((image.size[0] - side) // 2,
                           (image.size[1] - side) // 2,
                           (image.size[0] - side) // 2 + side,
                           (image.size[1] - side) // 2 + side))
        print(f"  artwork      {image.size[0]}x{image.size[1]}")
        print("  already cut out - using it as supplied")
        write_sizes(crop)
        return
    box = content_box(image)
    if box is None:
        raise SystemExit("That image is a single flat colour - nothing to cut out.")
    square = square_around(box, image.size)
    crop = image.crop(square)
    print(f"  artwork      {image.size[0]}x{image.size[1]}")
    print(f"  logo bounds  {box}")
    print(f"  square crop  {square}  ->  {crop.size[0]}x{crop.size[1]}")

    write_sizes(round_off(crop.resize((1024, 1024), Image.LANCZOS)))


def write_sizes(master: Image.Image) -> None:
    """Write every size the application and Windows ask for.

    Never upscales past the artwork: enlarging a 320px badge to 512 only blurs
    it, and Windows is content with an icon whose largest face is smaller.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    side = master.size[0]

    window = min(512, side)
    png = OUT / "icon.png"
    master.resize((window, window), Image.LANCZOS).save(png, "PNG")
    print(f"  wrote {png}  ({window}px)")

    sizes = [s for s in ICO_SIZES if s <= side] or [side]
    ico = OUT / "icon.ico"
    master.save(ico, "ICO", sizes=[(s, s) for s in sizes])
    print(f"  wrote {ico}  ({', '.join(str(s) for s in sizes)})")

    master.resize((128, 128), Image.LANCZOS).save(OUT / "icon_128.png", "PNG")
    print(f"  wrote {OUT / 'icon_128.png'}  (128px)")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    source = Path(argv[0])
    if not source.exists():
        print(f"No such file: {source}")
        return 1
    print(f"Reading {source}")
    build(source)
    print("\nDone. Rebuild with:  .venv\\Scripts\\python.exe build.py --zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
