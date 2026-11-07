"""Deteksi reaksi: sinyal sintetis, tanpa file audio atau ffmpeg."""

from __future__ import annotations

import unittest

import numpy as np

from clippergod.pipeline.reactions import analyse, classify, regions

SR = 16000


def signal(*spans: tuple[float, float, float]) -> np.ndarray:
    """spans = (mulai, durasi, amplitudo). Di luar span = hening."""
    total = int(SR * max(s + e for s, e, _a in spans)) + SR // 2
    out = np.zeros(total, dtype=np.float32)
    rng = np.random.default_rng(0)
    for start, dur, amp in spans:
        i = int(start * SR)
        j = i + int(dur * SR)
        out[i:j] = rng.normal(0, amp, j - i).astype(np.float32)
    return out


class TestRegions(unittest.TestCase):
    def test_noise_burst_is_a_reaction(self):
        rms, flat, step = analyse(signal((3.0, 0.6, 0.3)), SR)
        found = regions(rms, flat, step)
        self.assertTrue(found)
        self.assertTrue(any(s < 3.5 < e for s, e in found), found)

    def test_silence_has_no_reaction(self):
        rms, flat, step = analyse(np.zeros(SR * 3, dtype=np.float32), SR)
        self.assertEqual(regions(rms, flat, step), [])

    def test_pure_tone_is_not_a_reaction(self):
        t = np.arange(int(SR * 0.8)) / SR
        tone = (0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        rms, flat, step = analyse(tone, SR)
        self.assertEqual(regions(rms, flat, step), [])


class TestClassify(unittest.TestCase):
    def test_short_is_laughter_long_is_applause(self):
        self.assertEqual(classify(0.0, 0.6), "laughter")
        self.assertEqual(classify(0.0, 2.0), "applause")


if __name__ == "__main__":
    unittest.main()
