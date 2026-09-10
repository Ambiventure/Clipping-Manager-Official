"""Stage 2 check: does every text caption parse into newspaper / edition / page?

Run:  .venv\\Scripts\\python.exe -X utf8 tools\\verify_stage2.py "Sample clips/31/Word"

Prints every caption in the four text-caption divisions next to what was parsed out
of it, then a per-division hit rate. Delhi and Lucknow are skipped: their names are
burned into the image and come from OCR at stage 4.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clippings_manager.core.extract_docx import (  # noqa: E402
    detect_division,
    extract_docx,
    load_config,
)
from clippings_manager.core.profiles import NameIndex, apply_to_clip  # noqa: E402

TEXT_DIVISIONS = ("MB", "FZR", "UMB", "JAT")


def main() -> int:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "Sample clips/31/Word")
    config = load_config()
    index = NameIndex.load(settings=config.get("name_matching"))

    files = sorted(p for p in folder.glob("*.docx") if not p.name.startswith("~$"))
    totals: dict[str, list[int]] = {}
    low_confidence: list[str] = []
    unparsed: list[str] = []

    for path in files:
        division = detect_division(path.name)
        if division not in TEXT_DIVISIONS:
            continue
        clips, _ = extract_docx(path)

        print("=" * 108)
        print(f"{division}  {path.name}")
        print("-" * 108)
        print(f"{'#':>3}  {'caption':<52} {'newspaper':<24} {'edition':<14} "
              f"{'pg':>3} {'conf':>5}")

        parsed_ok = 0
        captioned = 0
        for clip in clips:
            parsed = apply_to_clip(clip, config, index)
            if not clip.caption_raw:
                continue
            captioned += 1
            if parsed.ok:
                parsed_ok += 1
            mark = " " if parsed.confidence >= 0.75 else "!"
            print(f"{clip.doc_index + 1:>3}{mark} {clip.caption_raw[:52]:<52} "
                  f"{clip.newspaper[:24]:<24} {clip.edition[:14]:<14} "
                  f"{clip.page:>3} {parsed.confidence:>5.2f}")
            if not parsed.ok:
                unparsed.append(f"{division} #{clip.doc_index + 1}: {clip.caption_raw}")
            elif parsed.confidence < 0.75:
                low_confidence.append(
                    f"{division} #{clip.doc_index + 1}: {clip.caption_raw!r} -> "
                    f"{clip.newspaper!r} / {clip.edition!r} (conf {parsed.confidence})"
                )

        got = totals.setdefault(division, [0, 0])
        got[0] += parsed_ok
        got[1] += captioned

    print("=" * 108)
    print("Parse rate by division (captions that produced a newspaper name):")
    grand_ok = grand_total = 0
    for division in TEXT_DIVISIONS:
        if division not in totals:
            continue
        ok, total = totals[division]
        grand_ok += ok
        grand_total += total
        rate = 100.0 * ok / total if total else 0.0
        print(f"   {division:<5} {ok:>3}/{total:<3}  {rate:5.1f}%")
    rate = 100.0 * grand_ok / grand_total if grand_total else 0.0
    print(f"   {'ALL':<5} {grand_ok:>3}/{grand_total:<3}  {rate:5.1f}%")

    if unparsed:
        print(f"\n{len(unparsed)} caption(s) produced no newspaper name:")
        for line in unparsed:
            print(f"   {line}")
    if low_confidence:
        print(f"\n{len(low_confidence)} caption(s) would be flagged amber for review:")
        for line in low_confidence:
            print(f"   {line}")

    if grand_total and grand_ok == grand_total and not low_confidence:
        print("\nAll stage 2 captions parsed with confidence.")
        return 0
    return 0 if not unparsed else 1


if __name__ == "__main__":
    raise SystemExit(main())
