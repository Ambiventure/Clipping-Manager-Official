"""Stage 1 check: does the .docx extractor find every clipping, and only clippings?

Run:  .venv\\Scripts\\python.exe tools\\verify_stage1.py "Sample clips/31/Word"

Asserts the counts established by inspecting the real 31-08-2026 documents, so a
regression in the XML walk shows up as a failed line rather than a quietly missing
clipping.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clippings_manager.core.extract_docx import detect_division, extract_docx  # noqa: E402

# filename fragment -> (division, clips, captioned, vml, cropped, flagged)
EXPECTED = {
    "Ambala": ("UMB", 32, 32, 0, 0, 0),
    "FZR": ("FZR", 9, 9, 2, 0, 0),
    "JAMMU": ("JAT", 10, 9, 0, 0, 1),
    "MB Paper": ("MB", 31, 25, 0, 5, 0),
    "Neutral News DLI": ("DLI", 40, 0, 0, 0, 0),
    "Lucknow": ("LKO", 40, 0, 0, 0, 0),
    "Positive News DLI": ("DLI", 1, 0, 0, 0, 0),
}

SECTIONS = {
    "MB Paper": {"Positive": 10, "Neutral": 15, "Digital": 6},
    "Lucknow": {"Positive": 22, "Neutral": 10, "Digital": 7, "Advertisement": 1},
    "Ambala": {"Positive": 4, "Neutral": 28},
    "FZR": {"Positive": 1, "Neutral": 8},
}


def main() -> int:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "Sample clips/31/Word")
    files = sorted(p for p in folder.glob("*.docx") if not p.name.startswith("~$"))
    if not files:
        print(f"No .docx files found in {folder}")
        return 2

    failures: list[str] = []
    total = 0

    for path in files:
        key = next((k for k in EXPECTED if k.lower() in path.name.lower()), None)
        clips, warnings = extract_docx(path)
        total += len(clips)

        actual = (
            detect_division(path.name),
            len(clips),
            sum(1 for c in clips if c.caption_raw),
            sum(1 for c in clips if c.is_vml),
            sum(1 for c in clips if not c.crop.is_identity),
            sum(1 for c in clips if c.probable_junk),
        )
        labels = ("division", "clips", "captioned", "vml", "cropped", "flagged")

        if key is None:
            print(f"?  {path.name}: no expectation recorded, got {actual}")
            continue

        line_failures = [
            f"{label}: expected {want}, got {got}"
            for label, want, got in zip(labels, EXPECTED[key], actual)
            if want != got
        ]

        if key in SECTIONS:
            counts: dict[str, int] = {}
            for clip in clips:
                counts[clip.section.value] = counts.get(clip.section.value, 0) + 1
            if counts != SECTIONS[key]:
                line_failures.append(
                    f"sections: expected {SECTIONS[key]}, got {counts}"
                )

        mark = "FAIL" if line_failures else "ok  "
        print(f"{mark} {path.name}")
        print(f"       division={actual[0]} clips={actual[1]} captioned={actual[2]} "
              f"vml={actual[3]} cropped={actual[4]} flagged={actual[5]}")
        for failure in line_failures:
            print(f"       -> {failure}")
            failures.append(f"{path.name}: {failure}")
        for warning in warnings:
            print(f"       ! {warning}")

    print(f"\n{total} clippings extracted in total (expected 163).")
    if total != 163:
        failures.append(f"total: expected 163, got {total}")

    if failures:
        print(f"\n{len(failures)} check(s) FAILED.")
        return 1
    print("\nAll stage 1 checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
