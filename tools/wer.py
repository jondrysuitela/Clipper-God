"""Ukur Word Error Rate transkrip ASR terhadap teks asli (ground truth).

Jalankan:  python tools/wer.py <ground_truth.json> <transcript.json>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

WORD = re.compile(r"[a-z0-9']+")


def normalize(text: str) -> list[str]:
    return WORD.findall(text.lower())


def edit_distance(ref: list[str], hyp: list[str]) -> int:
    m, n = len(ref), len(hyp)
    prev = list(range(n + 1))
    for i in range(1, m + 1):
        cur = [i] + [0] * n
        for j in range(1, n + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1,
                         prev[j - 1] + (ref[i - 1] != hyp[j - 1]))
        prev = cur
    return prev[n]


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    truth = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    got = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

    ref = [w for line in truth["lines"] for w in normalize(line["text"])]
    hyp = normalize(" ".join(w["text"] for w in got["words"]))
    errors = edit_distance(ref, hyp)

    print(f"kata asli : {len(ref)}")
    print(f"kata ASR  : {len(hyp)}")
    print(f"WER       : {errors / max(1, len(ref)):.1%}  ({errors} salah dari {len(ref)})")
    print()
    print("asli :", " ".join(ref))
    print("asr  :", " ".join(hyp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
