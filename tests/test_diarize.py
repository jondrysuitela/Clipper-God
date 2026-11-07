"""Test diarisasi: VAD energi, F0 autokorelasi, k-means, dan penempelan label."""

from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from clippergod.core.models import Word
from clippergod.pipeline.diarize import (
    detect_regions,
    diarize_file,
    estimate_f0,
    label_words,
)

SR = 16000


def _tone(freq: float, seconds: float, amp: float = 0.35) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    # harmonik kecil supaya bukan sinus murni: lebih mirip suara, tetap deterministik
    wave_ = amp * (np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(4 * np.pi * freq * t))
    return wave_.astype(np.float32)


def _write(path: Path, parts: list[np.ndarray]) -> None:
    data = np.concatenate(parts)
    pcm = np.clip(data, -1.0, 1.0)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SR)
        out.writeframes((pcm * 32767).astype("<i2").tobytes())


class VadTest(unittest.TestCase):
    def test_silence_between_bursts_becomes_gap(self):
        quiet = np.zeros(int(SR * 0.6), dtype=np.float32)
        samples = np.concatenate([_tone(150, 1.0), quiet, _tone(150, 1.0)])
        regions = detect_regions(samples, SR)
        self.assertEqual(len(regions), 2)
        self.assertAlmostEqual(regions[0].duration, 1.0, delta=0.06)
        self.assertGreater(regions[1].start, 1.5)

    def test_short_blip_is_discarded(self):
        quiet = np.zeros(int(SR * 0.5), dtype=np.float32)
        samples = np.concatenate([_tone(150, 1.0), quiet, _tone(150, 0.1)])
        self.assertEqual(len(detect_regions(samples, SR)), 1)

    def test_silence_only_gives_no_regions(self):
        self.assertEqual(detect_regions(np.zeros(SR, dtype=np.float32), SR), [])


class PitchTest(unittest.TestCase):
    def test_f0_is_close_to_tone_frequency(self):
        quiet = np.zeros(int(SR * 0.5), dtype=np.float32)
        samples = np.concatenate([_tone(120, 1.0), quiet])
        region = detect_regions(samples, SR)[0]
        f0 = estimate_f0(samples, SR, region)
        self.assertIsNotNone(f0)
        self.assertAlmostEqual(f0, 120.0, delta=6.0)

    def test_silence_has_no_pitch(self):
        from clippergod.pipeline.diarize import SpeechRegion
        region = SpeechRegion(start=0.0, end=0.5)
        self.assertIsNone(estimate_f0(np.zeros(SR, dtype=np.float32), SR, region))

    def test_continuous_audio_is_not_dropped(self):
        """Tanpa jeda sama sekali, VAD tidak boleh menganggap semuanya senyap."""
        regions = detect_regions(_tone(140, 2.0), SR)
        self.assertEqual(len(regions), 1)
        self.assertGreater(regions[0].duration, 1.9)


class ClusterTest(unittest.TestCase):
    def test_two_distinct_voices_get_two_labels(self):
        quiet = np.zeros(int(SR * 0.5), dtype=np.float32)
        samples = np.concatenate([
            _tone(110, 1.0), quiet, _tone(210, 1.0), quiet,
            _tone(110, 1.0), quiet, _tone(210, 1.0),
        ])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dua-suara.wav"
            _write(path, [samples])
            diar = diarize_file(path, k=2)

        self.assertEqual(len(diar.regions), 4)
        labels = [r.speaker for r in diar.regions]
        self.assertEqual(len(set(labels)), 2, labels)
        self.assertEqual(labels[0], labels[2])
        self.assertEqual(labels[1], labels[3])
        self.assertNotEqual(labels[0], labels[1])
        low = min(diar.speakers.items(), key=lambda kv: kv[1]["f0_median"])
        self.assertLess(low[1]["f0_median"], 150)

    def test_single_voice_gets_one_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "satu-suara.wav"
            _write(path, [np.concatenate([_tone(130, 1.0), np.zeros(int(SR * 0.4), dtype=np.float32),
                                          _tone(130, 1.0)])])
            diar = diarize_file(path, k=2)
        self.assertEqual({r.speaker for r in diar.regions}, {"S1"})


class LabelWordsTest(unittest.TestCase):
    def _diar(self):
        quiet = np.zeros(int(SR * 0.5), dtype=np.float32)
        samples = np.concatenate([_tone(110, 1.0), quiet, _tone(210, 1.0)])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.wav"
            _write(path, [samples])
            return diarize_file(path, k=2)

    def test_words_get_speaker_by_overlap(self):
        diar = self._diar()
        words = [Word(text="a", start=0.2, end=0.5), Word(text="b", start=1.7, end=2.0)]
        labeled = label_words(words, diar)
        self.assertEqual(labeled[0].speaker, diar.regions[0].speaker)
        self.assertEqual(labeled[1].speaker, diar.regions[1].speaker)
        self.assertNotEqual(labeled[0].speaker, labeled[1].speaker)

    def test_word_in_gap_uses_nearest_region(self):
        diar = self._diar()
        words = [Word(text="x", start=1.05, end=1.15)]  # di dalam jeda
        labeled = label_words(words, diar)
        self.assertIsNotNone(labeled[0].speaker)

    def test_word_far_away_stays_unlabeled(self):
        diar = self._diar()
        words = [Word(text="x", start=8.0, end=8.2)]
        self.assertIsNone(label_words(words, diar)[0].speaker)


if __name__ == "__main__":
    unittest.main()
