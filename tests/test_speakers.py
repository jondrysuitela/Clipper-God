"""Test speaker timeline: binding label→wajah, warna, segmen, dan crop berpotongan."""

from __future__ import annotations

import unittest

from clippergod.core.models import FaceBox, Word
from clippergod.pipeline.faces import FaceScan
from clippergod.pipeline.reframe import SegmentCrop
from clippergod.pipeline.speakers import (
    ass_color,
    bind_speakers,
    speaker_segments,
)


def _word(text: str, start: float, end: float, speaker: str | None = None) -> Word:
    return Word(text=text, start=start, end=end, speaker=speaker)


def _box(cx: float, size: float = 120.0, track: int = 1) -> FaceBox:
    return FaceBox(cx - size / 2, 100, cx + size / 2, 100 + size, track_id=track)


def _scan_two_people(seconds: float = 20.0, left: float = 380.0, right: float = 900.0,
                     step: float = 0.25) -> FaceScan:
    """Kedua wajah selalu terlihat, seperti kamera podcast dua orang."""
    scan = FaceScan(width=1280, height=720)
    t = 0.0
    while t < seconds:
        scan.samples.append((round(t, 3), _box(left, track=1)))
        scan.samples.append((round(t, 3), _box(right, track=2)))
        t += step
    scan.track_hits = {1: len(scan.samples) // 2, 2: len(scan.samples) // 2}
    return scan


class ColorTest(unittest.TestCase):
    def test_rgb_to_ass_is_bgr(self):
        # #FFD400 (kuning) -> ASS menyimpan BGR: &H00 00 D4 FF
        self.assertEqual(ass_color("#FFD400"), "&H0000D4FF")
        self.assertEqual(ass_color("3DDC97"), "&H0097DC3D")

    def test_bad_color_is_rejected(self):
        with self.assertRaises(ValueError):
            ass_color("#FFF")


class BindTest(unittest.TestCase):
    def test_two_speakers_bind_to_two_different_faces(self):
        words = [_word("a", 0.0, 4.0, "S1"), _word("b", 4.5, 9.0, "S2"),
                 _word("c", 9.5, 14.0, "S1"), _word("d", 14.5, 19.0, "S2")]
        timeline = bind_speakers(words, _scan_two_people())
        self.assertEqual(len(timeline.bindings), 2)
        s1 = timeline.by_speaker("S1")
        s2 = timeline.by_speaker("S2")
        self.assertIsNotNone(s1.track_id)
        self.assertIsNotNone(s2.track_id)
        self.assertNotEqual(s1.track_id, s2.track_id)
        self.assertNotEqual(s1.color, s2.color)
        # Dua wajah selalu terlihat = tanpa ASD tidak ada bukti siapa bicara.
        # Heuristik kiri-ke-kanan harus jujur menandai dirinya perlu review.
        self.assertEqual(sorted(timeline.needs_review), ["S1", "S2"])
        self.assertIn("kiri-ke-kanan", s1.reason or "")
        self.assertLessEqual(s1.track_id, s2.track_id, "urutan kiri-ke-kanan")

    def test_explicit_map_is_trusted(self):
        words = [_word("a", 0.0, 4.0, "S1"), _word("b", 4.5, 9.0, "S2")]
        timeline = bind_speakers(words, _scan_two_people(), speaker_map={"S1": 2, "S2": 1})
        self.assertEqual(timeline.by_speaker("S1").track_id, 2)
        self.assertEqual(timeline.by_speaker("S2").track_id, 1)
        self.assertEqual(timeline.needs_review, [])

    def test_single_speaker_single_face_is_not_flagged(self):
        words = [_word("a", 0.0, 5.0, "S1")]
        scan = FaceScan(width=1280, height=720)
        for i in range(20):
            scan.samples.append((i * 0.25, _box(380.0, track=7)))
        timeline = bind_speakers(words, scan)
        binding = timeline.by_speaker("S1")
        self.assertEqual(binding.track_id, 7)
        self.assertFalse(binding.review)

    def test_speaker_without_faces_needs_review(self):
        words = [_word("a", 0.0, 3.0, "S1")]
        blank = FaceScan(width=1280, height=720)
        timeline = bind_speakers(words, blank)
        binding = timeline.by_speaker("S1")
        self.assertIsNone(binding.track_id)
        self.assertTrue(binding.review)
        self.assertEqual(binding.share, 0.0)

    def test_words_without_speaker_labels_produce_no_timeline(self):
        timeline = bind_speakers([_word("a", 0.0, 1.0)], _scan_two_people())
        self.assertEqual(timeline.bindings, [])

    def test_share_reflects_minority_face(self):
        """Kalau wajah pembicara hanya terlihat separuh waktu, share ikut turun."""
        words = [_word("a", 0.0, 10.0, "S1")]
        scan = FaceScan(width=1280, height=720)
        for i in range(20):                       # 5 s terlihat, 5 s hilang
            scan.samples.append((i * 0.25, _box(380.0, track=1)))
        for i in range(20, 40):
            scan.samples.append((i * 0.25, _box(380.0, track=2)))
        timeline = bind_speakers(words, scan)
        binding = timeline.by_speaker("S1")
        self.assertEqual(binding.track_id, 1)
        self.assertLess(binding.share, 0.6)


class SegmentTest(unittest.TestCase):
    def test_alternating_speakers_split_cleanly(self):
        words = [_word("a", 0.0, 4.0, "S1"), _word("b", 4.2, 8.0, "S2"),
                 _word("c", 8.2, 12.0, "S1")]
        segs = speaker_segments(words, 0.0, 12.0)
        self.assertEqual([s.speaker for s in segs], ["S1", "S2", "S1"])
        self.assertAlmostEqual(segs[0].start, 0.0)
        self.assertAlmostEqual(segs[-1].end, 12.0)

    def test_short_segment_is_merged_into_neighbour(self):
        words = [_word("a", 0.0, 4.0, "S1"), _word("b", 4.05, 4.3, "S2"),
                 _word("c", 4.35, 9.0, "S1")]
        segs = speaker_segments(words, 0.0, 9.0, min_segment=0.8)
        self.assertEqual([s.speaker for s in segs], ["S1"])

    def test_gap_between_words_keeps_previous_speaker(self):
        words = [_word("a", 0.0, 1.0, "S1"), _word("b", 2.0, 3.0, "S1")]
        segs = speaker_segments(words, 0.0, 3.0)
        self.assertEqual(len(segs), 1)
        self.assertAlmostEqual(segs[0].end, 3.0)

    def test_empty_when_no_speaker_labels(self):
        self.assertEqual(speaker_segments([_word("a", 0.0, 1.0)], 0.0, 1.0), [])


class SegmentCropTest(unittest.TestCase):
    def test_expression_switches_at_segment_boundary(self):
        path = SegmentCrop(
            segments=[(0.0, 5.0, 100.0), (5.0, 10.0, 600.0)],
            crop_w=405, crop_h=720, src_w=1280, src_h=720, fps=30,
        )
        expr = path.expression()
        self.assertTrue(expr.startswith("max(0,min(875,"))
        self.assertIn("if(lt(t,5.000),100.00,600.00)", expr)
        self.assertAlmostEqual(path.at(0), 100.0)
        self.assertAlmostEqual(path.at(149), 100.0)   # 4.97 s
        self.assertAlmostEqual(path.at(150), 600.0)   # 5.00 s

    def test_static_when_all_segments_share_position(self):
        path = SegmentCrop(
            segments=[(0.0, 5.0, 200.0), (5.0, 10.0, 200.0)],
            crop_w=405, crop_h=720, src_w=1280, src_h=720, static=True,
        )
        self.assertEqual(path.expression(), "200")
        self.assertAlmostEqual(path.at(240), 200.0)

    def test_x_is_clamped_inside_frame(self):
        path = SegmentCrop(
            segments=[(0.0, 5.0, 900.0)], crop_w=405, crop_h=720, src_w=1280, src_h=720,
        )
        self.assertLessEqual(path.at(0), path.max_x)


if __name__ == "__main__":
    unittest.main()
