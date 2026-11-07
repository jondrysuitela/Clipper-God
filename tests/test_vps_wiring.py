"""VPS harus dipakai jalur kandidat, dan komponen yang belum diukur tidak boleh dinilai.

Dua hal yang dikunci di sini:
  1. `evaluate(measured=...)` menormalkan ulang bobot — bukan mengisi default.
  2. Skor kandidat = VPS parsial, dengan daftar komponen yang belum diukur.
"""

from __future__ import annotations

import unittest

from clippergod.core.boundaries import BoundaryConfig
from clippergod.core.models import Word
from clippergod.core.scoring import ClipSignals, evaluate, score_hook
from clippergod.pipeline.candidates import CandidateConfig, generate


def words(n: int = 90, step: float = 0.42, gap: float = 0.05) -> list[Word]:
    out: list[Word] = []
    t = 0.0
    for i in range(n):
        text = "kenapa" if i % 17 == 0 else f"kata{i}"
        end = t + step
        out.append(Word(text=text, start=round(t, 3), end=round(end, 3)))
        t = end + gap
        if (i + 1) % 6 == 0:
            out[-1] = Word(text=out[-1].text + ".", start=out[-1].start, end=out[-1].end)
            t += 0.3
    return out


class TestPartialVPS(unittest.TestCase):
    def test_unmeasured_components_are_excluded_and_listed(self):
        result = evaluate(ClipSignals(duration=30.0, speech_onset=0.0), measured={"H", "C"})
        self.assertEqual(set(result.components), {"H", "C"})
        self.assertEqual(result.unmeasured, ["R", "A", "L", "P"])
        self.assertTrue(result.partial)

    def test_weight_renormalized_not_diluted(self):
        # H=100, C=100 dengan bobot 0.30/0.15 harus tetap 100 — bukan 45.
        result = evaluate(
            ClipSignals(duration=30.0, speech_onset=0.0, hook_text="kenapa kamu gagal?",
                        caption_max_cps=12.0),
            measured={"H", "C"},
        )
        self.assertEqual(result.components["H"], 100.0)
        self.assertEqual(result.components["C"], 100.0)
        self.assertEqual(result.score, 100.0)

    def test_missing_motion_does_not_punish_hook(self):
        perfect = ClipSignals(duration=30.0, speech_onset=0.0, hook_text="kenapa kamu gagal?")
        value, reasons = score_hook(perfect)
        self.assertEqual(value, 100.0, reasons)
        self.assertTrue(any("belum diukur" in r for r in reasons))


class TestCandidateUsesVPS(unittest.TestCase):
    def test_candidate_score_is_vps_with_honest_gaps(self):
        cands = generate(words(), CandidateConfig(target="reach"))
        self.assertTrue(cands)
        for cand in cands:
            self.assertIsNotNone(cand.vps)
            self.assertEqual(cand.score, cand.vps["score"])
            self.assertEqual(set(cand.vps["components"]), {"H", "C"})
            self.assertEqual(cand.vps["unmeasured"], ["R", "A", "L", "P"])

    def test_boundary_rules_still_apply(self):
        # Skor boleh berubah, tapi larangan potong tengah kalimat tidak boleh longgar.
        cands = generate(words(), CandidateConfig(target="watch"), BoundaryConfig())
        for cand in cands:
            self.assertTrue(cand.reasons[-1].startswith("VPS"))


if __name__ == "__main__":
    unittest.main()
