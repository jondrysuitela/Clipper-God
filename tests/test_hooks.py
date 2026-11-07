"""Hook A/B: tiga pembuka, body sama, skor H yang bisa dibandingkan."""

from __future__ import annotations

import unittest

from clippergod.core.models import Word
from clippergod.pipeline.hooks import plan_hooks


def transcript() -> list[Word]:
    # Kalimat 1: sapaan lemah. Kalimat 2: pertanyaan + negasi + "kamu".
    lines = [
        ("hai", "semua", "selamat", "datang", "di", "podcast", "kita", "hari", "ini."),
        ("kenapa", "kamu", "selalu", "gagal", "bikin", "konten", "menarik", "?"),
        ("jawabannya", "bukan", "di", "kamera", "atau", "lampu", "mahal", "."),
        ("tapi", "di", "tiga", "kebiasaan", "kecil", "yang", "sering", "dilewatkan", "."),
    ]
    words: list[Word] = []
    t = 0.0
    for line in lines:
        for token in line:
            words.append(Word(token, round(t, 2), round(t + 0.4, 2)))
            t += 0.45
        t += 0.65
    return words


class TestPlanHooks(unittest.TestCase):
    def setUp(self):
        self.words = transcript()
        self.start = self.words[0].start
        self.end = self.words[-1].end

    def test_three_distinct_openings(self):
        variants = plan_hooks(self.words, self.start, self.end)
        self.assertEqual([v.label for v in variants], ["A", "B", "C"])
        self.assertEqual(len({round(v.start, 2) for v in variants}), 3)

    def test_first_variant_is_original_opening(self):
        variants = plan_hooks(self.words, self.start, self.end)
        self.assertAlmostEqual(variants[0].start, self.start, places=2)
        self.assertIn("pembuka asli", variants[0].reasons)

    def test_strong_hook_beats_greeting(self):
        variants = plan_hooks(self.words, self.start, self.end)
        by_label = {v.label: v for v in variants}
        self.assertGreater(by_label["B"].score, by_label["A"].score)
        self.assertIn("kenapa", by_label["B"].text.lower())

    def test_variants_keep_same_end_and_min_body(self):
        for variant in plan_hooks(self.words, self.start, self.end):
            self.assertAlmostEqual(variant.end, self.end, places=3)
            self.assertGreaterEqual(variant.duration, 8.0)

    def test_too_short_clip_has_no_variants(self):
        self.assertEqual(plan_hooks(self.words, self.words[0].start, self.words[0].start + 5.0), [])


if __name__ == "__main__":
    unittest.main()
