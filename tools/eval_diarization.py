"""Ukur akurasi label pembicara hasil diarisasi terhadap timeline asli.

Jalankan:  python tools/eval_diarization.py <ground_truth.json> <transcript.json>

Label hasil cluster (S1/S2) tidak harus sama arti dengan label asli, jadi
dibandingkan lewat pemetaan terbaik (permutasi), bukan teks label mentah.
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path


def truth_speaker_at(truth: dict, t: float) -> str | None:
    for line in truth["lines"]:
        if line["start"] <= t <= line["end"]:
            return line["speaker"]
    return None


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    truth = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    got = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

    pairs: list[tuple[str, str]] = []
    unlabeled = 0
    for w in got["words"]:
        mid = (w["start"] + w["end"]) / 2
        expected = truth_speaker_at(truth, mid)
        predicted = w.get("speaker")
        if expected is None:
            continue
        if predicted is None:
            unlabeled += 1
            continue
        pairs.append((expected, predicted))

    if not pairs:
        print("tidak ada kata berlabel untuk dievaluasi", file=sys.stderr)
        return 1

    labels = sorted({p for _t, p in pairs})
    best_acc, best_map = -1.0, {}
    for perm in itertools.permutations(sorted({t for t, _p in pairs}), len(labels)):
        mapping = dict(zip(labels, perm))
        correct = sum(1 for t, p in pairs if mapping[p] == t)
        acc = correct / len(pairs)
        if acc > best_acc:
            best_acc, best_map = acc, mapping

    print(f"kata dievaluasi : {len(pairs)}")
    print(f"tanpa label     : {unlabeled}")
    print(f"akurasi speaker : {best_acc:.1%}")
    print(f"pemetaan        : {best_map}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
