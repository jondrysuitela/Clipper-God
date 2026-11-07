"""Helper pengukuran VPS: parsing loudnorm, SSIM, cut rate, gap bicara.

Semua diuji tanpa ffmpeg dan tanpa file video — itu inti desainnya.
"""

from __future__ import annotations

import unittest

import numpy as np

from clippergod.core.models import Word
from clippergod.pipeline.measure import (
    cuts_per_minute,
    motion_score,
    parse_loudnorm,
    speech_gaps,
    ssim,
    static_runs,
)

LOUDNORM = """[Parsed_loudnorm_0 @ 0000]
{
	"input_i" : "-14.20",
	"input_tp" : "-1.10",
	"input_lra" : "7.00",
	"input_thresh" : "-24.70",
	"output_i" : "-14.00"
}"""


class TestLoudnorm(unittest.TestCase):
    def test_parses_block(self):
        self.assertEqual(parse_loudnorm(LOUDNORM), (-14.2, -1.1))

    def test_inf_and_garbage_are_none(self):
        self.assertEqual(parse_loudnorm('{"input_i": "-inf", "input_tp": "-inf"}'),
                         (None, None))
        self.assertEqual(parse_loudnorm("tidak ada json"), (None, None))


class TestSsim(unittest.TestCase):
    def test_same_frame_is_one(self):
        frame = np.arange(90 * 160, dtype=np.uint8).reshape(90, 160)
        self.assertAlmostEqual(ssim(frame, frame), 1.0, places=6)

    def test_different_frame_is_lower(self):
        a = np.zeros((90, 160), dtype=np.uint8)
        b = np.full((90, 160), 255, dtype=np.uint8)
        self.assertLess(ssim(a, b), 0.1)


class TestPacing(unittest.TestCase):
    def test_cuts_per_minute(self):
        # 4 sampel berjarak 0.25 s = 1 detik, 2 di antaranya cut -> 120 cut/menit
        self.assertAlmostEqual(cuts_per_minute([20.0, 1.0, 20.0, 1.0], 0.25), 120.0)

    def test_no_frames_means_zero(self):
        self.assertEqual(cuts_per_minute([], 0.25), 0.0)

    def test_static_runs(self):
        self.assertEqual(static_runs([1.0] * 30, 0.25), 1)   # 7,5 s statis
        self.assertEqual(static_runs([1.0] * 10, 0.25), 0)   # 2,5 s

    def test_motion_normalized(self):
        self.assertEqual(motion_score(0.0), 0.0)
        self.assertEqual(motion_score(16.0), 1.0)
        self.assertEqual(motion_score(100.0), 1.0)


class TestSpeechGaps(unittest.TestCase):
    def test_counts_only_long_gaps(self):
        w = [Word("a", 0.0, 0.5), Word("b", 0.6, 1.0),   # gap 0.1
             Word("c", 2.0, 2.4)]                          # gap 1.0
        self.assertEqual(speech_gaps(w), 1)


if __name__ == "__main__":
    unittest.main()
