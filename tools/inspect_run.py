"""Periksa batas potongan sebuah hasil `run`: kata apa yang ada di sekitar cut.

Jalankan:  python tools/inspect_run.py <run_dir>

Gunanya menjawab satu pertanyaan: apakah klip mulai/berhenti di tengah kata?
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load_words(run_dir: Path) -> list[dict]:
    return json.loads((run_dir / "transcript.json").read_text(encoding="utf-8"))["words"]


def neighbours(words: list[dict], t: float) -> tuple[dict | None, dict | None]:
    before = [w for w in words if w["end"] <= t]
    after = [w for w in words if w["start"] >= t]
    return (before[-1] if before else None), (after[0] if after else None)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    run_dir = Path(sys.argv[1])
    words = load_words(run_dir)
    clips = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["clips"]

    for clip in clips:
        start, end = clip["start"], clip["end"]
        print(f"{clip['index']:02d}. {clip['title']}")
        print(f"    {start:.2f}s -> {end:.2f}s  ({clip['duration']:.2f}s)")
        for label, t in (("awal", start), ("akhir", end)):
            prev, nxt = neighbours(words, t)
            gap_before = t - prev["end"] if prev else None
            gap_after = nxt["start"] - t if nxt else None
            inside = any(w["start"] < t < w["end"] for w in words)
            print(f"    {label:5s} @{t:7.2f}s  "
                  f"kata sebelumnya {prev['text']!r} (+{gap_before:.2f}s)" if gap_before is not None
                  else f"    {label:5s} @{t:7.2f}s  tidak ada kata sebelumnya", end="")
            print(f"  | kata berikutnya {nxt['text']!r} (-{gap_after:.2f}s)" if nxt else
                  "  | akhir transkrip")
            if inside:
                print("        PERINGATAN: potongan jatuh di dalam kata")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
