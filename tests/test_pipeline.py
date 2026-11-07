"""Test lapisan pipeline: kandidat, jalur crop, pelacakan wajah, filter render.

Yang diuji di sini adalah logika yang murni: tidak ada yang memanggil FFmpeg,
tidak ada yang butuh model.
"""

from __future__ import annotations

import unittest

from clippergod.core.captions import choose_placement
from clippergod.core.models import CaptionCue, FaceBox, Word
from clippergod.pipeline.candidates import CandidateConfig, generate, sentence_spans
from clippergod.pipeline.faces import FaceScan, FaceTracker
from clippergod.pipeline.reframe import CropPath, ReframeConfig, plan_crop
from clippergod.pipeline.render import RenderSpec, build_crop_filter, build_video_filter


def _script(sentences: list[tuple[str, float]], gap: float = 0.25) -> list[Word]:
    """Bangun transkrip dari kalimat; tiap kata 0.35 s, jeda antar kata 0.05 s."""
    words: list[Word] = []
    t = 0.0
    for sentence, pause_after in sentences:
        for token in sentence.split():
            words.append(Word(text=token, start=round(t, 3), end=round(t + 0.35, 3)))
            t += 0.40
        t += pause_after - 0.40 + gap
    return words


class SentenceSpanTest(unittest.TestCase):
    def test_punctuation_and_long_pause_split_sentences(self):
        words = _script([
            ("Ini kalimat pertama.", 1.2),
            ("Ini kalimat kedua tanpa titik", 1.2),
            ("Ini ketiga.", 0.0),
        ])
        spans = sentence_spans(words)
        self.assertEqual(len(spans), 3)
        self.assertEqual(spans[0][0], 0)
        for (a0, a1), (b0, _b1) in zip(spans, spans[1:]):
            self.assertEqual(a1, b0, "span harus bersambung tanpa celah")

    def test_empty_transcript_gives_no_spans(self):
        self.assertEqual(sentence_spans([]), [])


class CandidateTest(unittest.TestCase):
    def setUp(self):
        # Empat kalimat x ~9 kata = ~20 s; untuk target 21-34 s perlu enam kalimat
        # supaya ada kombinasi yang masuk rentang.
        self.words = _script([
            ("Pertama kita bahas kenapa hook tiga detik pertama itu penting banget.", 1.4),
            ("Kedua jangan pernah mulai dengan sapaan generik seperti hai guys semuanya.", 1.4),
            ("Ketiga potong klip selalu di akhir kalimat bukan di tengah ide yang belum selesai.", 1.4),
            ("Keempat caption harus mengikuti transkrip yang sama persis tanpa struktur terpisah.", 1.4),
            ("Kelima skor itu potensi bukan probabilitas jadi selalu tunjukkan alasannya.", 1.4),
            ("Keenam framing ikuti wajah yang benar bukan wajah yang paling banyak bergerak.", 1.4),
        ])

    def test_all_candidates_within_target_duration(self):
        cands = generate(self.words, CandidateConfig(target="reach"))
        self.assertTrue(cands, "harus ada kandidat")
        for cand in cands:
            self.assertGreaterEqual(cand.duration, 21.0 - 0.01, cand.title)
            self.assertLessEqual(cand.duration, 34.0 + 0.01, cand.title)

    def test_candidates_start_and_end_on_sentence_edges(self):
        cands = generate(self.words, CandidateConfig(target="reach"))
        starts = {w.start for w in self.words}
        ends = {w.end for w in self.words}
        for cand in cands:
            self.assertIn(cand.start, starts)
            self.assertIn(cand.end, ends)

    def test_no_heavy_overlap_between_kept_candidates(self):
        cands = generate(self.words, CandidateConfig(target="reach", overlap_ratio=0.5))
        for i, a in enumerate(cands):
            for b in cands[i + 1:]:
                inter = min(a.end, b.end) - max(a.start, b.start)
                shortest = min(a.duration, b.duration)
                if shortest > 0 and inter > 0:
                    self.assertLessEqual(inter / shortest, 0.5 + 1e-9,
                                         f"{a.title} vs {b.title}")

    def test_every_candidate_has_reasons(self):
        for cand in generate(self.words, CandidateConfig(target="reach")):
            self.assertTrue(cand.reasons)
            self.assertIsNotNone(cand.score)


class CropPathTest(unittest.TestCase):
    def test_follows_face_moving_linearly(self):
        centers = [(t, 200.0 + 150.0 * t) for t in (i / 8 for i in range(33))]  # 0..4 s
        path = plan_crop(centers, 4.0, 1280, 720)
        self.assertFalse(path.static)
        self.assertEqual(path.crop_w, 405)  # 720 * 9/16, tinggi penuh
        errors = []
        for frame in range(0, 4 * 30, 15):
            ideal = 200.0 + 150.0 * (frame / 30) - path.crop_w / 2
            ideal = max(0.0, min(path.max_x, ideal))
            errors.append(abs(path.at(frame) - ideal))
        # smoothing + deadband + fit polinomial: 20 px sumber masih < 5% lebar crop
        self.assertLess(max(errors), 20.0, f"error maks {max(errors):.1f} px")
        self.assertLess(errors[len(errors) // 2], 6.0)

    def test_static_face_gives_static_path(self):
        path = plan_crop([(t, 640.0) for t in (i / 8 for i in range(33))], 4.0, 1280, 720)
        self.assertTrue(path.static)
        self.assertEqual(path.expression(), str(int(round(640.0 - 202.5))))

    def test_path_stays_inside_source_frame(self):
        centers = [(t, 60.0 + 1200.0 * t) for t in (i / 8 for i in range(33))]
        path = plan_crop(centers, 4.0, 1280, 720)
        self.assertGreaterEqual(min(path.x), 0.0)
        self.assertLessEqual(max(path.x), path.max_x + 1e-6)

    def test_residual_within_configured_tolerance(self):
        # Wajah bergerak 400 px dalam 4 s (100 px/s) dan tetap di dalam frame.
        centers = [(t, 300.0 + 100.0 * t) for t in (i / 8 for i in range(33))]
        cfg = ReframeConfig()
        path = plan_crop(centers, 4.0, 1280, 720, cfg)
        self.assertFalse(path.static)
        self.assertLessEqual(path.residual, cfg.max_residual_ratio * path.crop_w)
        # Jalur tidak boleh menempel di tepi: wajah masih bisa ditaruh di tengah.
        self.assertLess(max(path.x), path.max_x - 50)

    def test_expression_uses_ascending_coefficients_in_seconds(self):
        """Regresi: np.polyfit mengembalikan pangkat tertinggi dulu, FFmpeg butuh naik."""
        path = CropPath(
            x=[1.0], crop_w=405, crop_h=720, src_w=1280, src_h=720,
            coeffs=[2.0, 0.0, 1.0],  # 2*n^2 + 0*n + 1 (domain frame)
            static=False, fps=30,
        )
        expr = path.expression("t")
        # 2*n^2 -> 2*30^2 * t^2 = 1800 t^2, konstanta tetap 1
        self.assertIn("1800.0000*pow(t,2)", expr)
        self.assertIn("1.0000", expr)
        self.assertNotIn("2.0000*pow(t,0)", expr)
        self.assertTrue(expr.startswith("max(0,min(875,"))

    def test_crop_path_at_matches_polyval(self):
        centers = [(t, 200.0 + 300.0 * t) for t in (i / 8 for i in range(33))]
        path = plan_crop(centers, 4.0, 1280, 720)
        import numpy as np
        for frame in (0, 17, 55, 119):
            self.assertAlmostEqual(path.at(frame), float(np.polyval(path.coeffs, frame)), 6)


class RenderFilterTest(unittest.TestCase):
    def test_crop_filter_is_dynamic_when_expression_given(self):
        spec = RenderSpec(src="a.mp4", dst="b.mp4", start=0.0, duration=4.0,
                          crop_w=405, crop_h=720, crop_x_expr="max(0,min(875,10*t))")
        filt = build_crop_filter(spec)
        self.assertIsNotNone(filt)
        self.assertIn("crop=w=405:h=720", filt)
        # Kalau build FFmpeg masih punya opsi eval, ia harus dipakai (default-nya init).
        from clippergod.pipeline.render import _crop_accepts_eval
        self.assertEqual("eval=frame" in filt, _crop_accepts_eval())

    def test_no_crop_when_size_missing(self):
        spec = RenderSpec(src="a.mp4", dst="b.mp4", start=0.0, duration=4.0)
        self.assertIsNone(build_crop_filter(spec))

    def test_video_filter_scales_to_vertical_canvas(self):
        spec = RenderSpec(src="a.mp4", dst="b.mp4", start=0.0, duration=4.0)
        filt = build_video_filter(spec)
        self.assertIn("scale=1080:1920", filt)
        self.assertIn("fps=30", filt)

    def test_video_filter_pads_mismatched_crop_without_distortion(self):
        spec = RenderSpec(
            src="a.mp4", dst="b.mp4", start=0.0, duration=4.0,
            out_w=1920, out_h=1080, crop_w=405, crop_h=720,
        )
        filt = build_video_filter(spec)
        self.assertIn("force_original_aspect_ratio=decrease", filt)
        self.assertIn("pad=1920:1080", filt)


class FaceTrackingTest(unittest.TestCase):
    def _box(self, cx: float, cy: float = 360.0, size: float = 120.0) -> FaceBox:
        return FaceBox(cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2)

    def test_tracker_keeps_one_id_across_small_motion(self):
        tracker = FaceTracker()
        ids = []
        for step in range(12):
            boxes = tracker.update([self._box(400.0 + step * 6.0)])
            ids.append(boxes[0].track_id)
        self.assertEqual(len(set(ids)), 1, f"id berubah: {ids}")

    def test_tracker_creates_new_id_for_far_jump(self):
        tracker = FaceTracker()
        first = tracker.update([self._box(200.0)])[0].track_id
        second = tracker.update([self._box(1000.0)])[0].track_id
        self.assertNotEqual(first, second)

    def test_nearest_sample_is_closest_in_time(self):
        scan = FaceScan(width=1280, height=720)
        scan.samples = [(0.0, self._box(300.0)), (0.5, self._box(500.0)),
                        (1.0, self._box(700.0))]
        scan.track_hits = {None: 3}
        self.assertAlmostEqual(scan.nearest(0.45).x1 - 60, 500.0, places=3)
        self.assertAlmostEqual(scan.nearest(0.95).x1 - 60, 700.0, places=3)

    def test_centers_only_dominant_track(self):
        small = FaceBox(0, 0, 10, 10, track_id=2)
        big = FaceBox(500, 300, 620, 420, track_id=1)
        scan = FaceScan(width=1280, height=720)
        scan.samples = [(0.0, big), (0.1, small), (0.2, big)]
        scan.track_hits = {1: 2, 2: 1}
        self.assertEqual(scan.dominant_track, 1)
        self.assertEqual(len(scan.centers()), 2)


class CaptionPlacementTest(unittest.TestCase):
    def _cue(self, lines=1) -> CaptionCue:
        word = Word(text="halo", start=0.0, end=1.0)
        return CaptionCue(start=0.0, end=1.0, words=[word], lines=["halo"] * lines)

    def test_face_at_top_pushes_caption_to_bottom(self):
        cue = self._cue()
        from clippergod.core.captions import CaptionStyle
        face = FaceBox(300, 300, 780, 900)
        self.assertEqual(choose_placement(cue, [face], CaptionStyle()), "bottom")

    def test_face_in_caption_band_pushes_caption_to_top(self):
        cue = self._cue()
        from clippergod.core.captions import CaptionStyle
        face = FaceBox(300, 1050, 780, 1500)
        self.assertEqual(choose_placement(cue, [face], CaptionStyle()), "top")

    def test_no_face_keeps_caption_at_bottom(self):
        from clippergod.core.captions import CaptionStyle
        self.assertEqual(choose_placement(self._cue(), [], CaptionStyle()), "bottom")


if __name__ == "__main__":
    unittest.main()
