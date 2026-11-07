"""Test orkestrator `run()` + CLI, memakai scanner & renderer palsu.

Yang diuji: bentuk artefak di disk, konsistensi waktu caption (relatif ke klip),
idempotensi (tidak render ulang), dan pembacaan transkrip dari JSON.
Tidak ada FFmpeg yang dijalankan di sini; scanner dan renderer menggunakan stub.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from clippergod.core.models import FaceBox, Word
from clippergod.pipeline.faces import FaceScan
from clippergod.pipeline.faces import scan_video
from clippergod.pipeline.render import RenderResult
from clippergod.pipeline.caption_config import from_dict as caption_from_dict
from clippergod.pipeline.runner import (
    RunConfig,
    load_transcript,
    run,
    slice_words,
    slugify,
    words_from_dicts,
    words_to_dicts,
)


def _make_video(path: Path, seconds: int = 45, size: tuple[int, int] = (320, 180)) -> None:
    w, h = size
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (w, h))
    if not writer.isOpened():
        raise unittest.SkipTest("VideoWriter tidak tersedia di mesin ini")
    frame = np.full((h, w, 3), 24, dtype=np.uint8)
    for i in range(seconds * 30):
        frame[:, :, 0] = 24 + (i % 40)
        writer.write(frame)
    writer.release()


def _transcript(seconds: float = 45.0) -> list[Word]:
    """Kalimat 6 detik, tiap kata 0.4 s, jeda 0.25 s di akhir kalimat."""
    sentences = [
        "Kenapa podcast kamu sepi penonton padahal isinya bagus sekali",
        "Tiga detik pertama menentukan apakah orang bertahan atau langsung geser",
        "Hook yang lemah membuat algoritma tidak punya alasan menyebarkan klip",
        "Potong selalu di akhir kalimat supaya idenya tetap utuh dan jelas",
        "Caption harus mengikuti transkrip yang sama bukan struktur terpisah",
        "Framing ikuti wajah yang sedang bicara bukan wajah yang paling besar",
        "Skor itu potensi bukan probabilitas jadi selalu tunjukkan alasannya",
    ]
    words: list[Word] = []
    t = 0.3
    idx = 0
    while t < seconds:
        sentence = sentences[idx % len(sentences)]
        idx += 1
        for token in sentence.split():
            if t >= seconds:
                break
            words.append(Word(text=token, start=round(t, 3), end=round(t + 0.4, 3)))
            t += 0.45
        t += 0.55
    return words


def _scan(seconds: float = 45.0) -> FaceScan:
    scan = FaceScan(width=1280, height=720)
    t = 0.0
    step = 0.25
    while t < seconds:
        cx = 480.0 + 60.0 * np.sin(t / 6.0)
        box = FaceBox(cx - 90, 180, cx + 90, 420, track_id=1)
        scan.samples.append((round(t, 3), box))
        t += step
    scan.track_hits = {1: len(scan.samples)}
    return scan


class FakeRenderer:
    def __init__(self) -> None:
        self.calls: list = []

    def __call__(self, spec) -> RenderResult:
        self.calls.append(spec)
        Path(spec.dst).parent.mkdir(parents=True, exist_ok=True)
        Path(spec.dst).write_bytes(b"fake-mp4")
        return RenderResult(path=spec.dst, width=1080, height=1920,
                            duration=spec.duration, size_mb=0.1, passes=2)


class SliceWordsTest(unittest.TestCase):
    def test_times_become_relative_to_clip(self):
        words = [Word(text="a", start=10.0, end=10.5), Word(text="b", start=11.0, end=11.5)]
        out = slice_words(words, 10.0, 12.0)
        self.assertEqual([w.text for w in out], ["a", "b"])
        self.assertAlmostEqual(out[0].start, 0.0)
        self.assertAlmostEqual(out[1].start, 1.0)

    def test_words_outside_clip_are_dropped(self):
        words = [Word(text="a", start=1.0, end=2.0), Word(text="b", start=30.0, end=31.0)]
        self.assertEqual(len(slice_words(words, 5.0, 10.0)), 0)


class TranscriptIoTest(unittest.TestCase):
    def test_roundtrip_dicts(self):
        words = [Word(text="halo", start=0.0, end=0.4, prob=0.9, speaker="S1")]
        again = words_from_dicts(words_to_dicts(words))
        self.assertEqual(again[0].text, "halo")
        self.assertAlmostEqual(again[0].prob, 0.9)
        self.assertEqual(again[0].speaker, "S1")

    def test_accepts_word_and_probability_aliases(self):
        words = words_from_dicts([{"word": "oke", "start": 1.0, "end": 2.0, "probability": 0.5}])
        self.assertEqual(words[0].text, "oke")
        self.assertAlmostEqual(words[0].prob, 0.5)

    def test_loads_json_file_with_words_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.json"
            path.write_text(json.dumps({"words": [
                {"text": "satu", "start": 0.0, "end": 1.0},
                {"text": "dua", "start": 1.0, "end": 2.0},
            ]}), encoding="utf-8")
            self.assertEqual(len(load_transcript(path)), 2)

    def test_rejects_shape_without_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.json"
            path.write_text(json.dumps({"foo": 1}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_transcript(path)


class SlugTest(unittest.TestCase):
    def test_slug_is_filesystem_safe(self):
        self.assertEqual(slugify("Kenapa Podcast Lu Sepi?"), "kenapa-podcast-lu-sepi")
        self.assertEqual(slugify("   "), "klip")
        self.assertLessEqual(len(slugify("kata " * 40)), 40)


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.video = self.root / "sumber.mp4"
        _make_video(self.video)
        self.words = _transcript()
        self.scan = _scan()
        self.renderer = FakeRenderer()

    def tearDown(self):
        self.tmp.cleanup()

    def _cfg(self, **kwargs) -> RunConfig:
        base = dict(out_dir=self.root / "hasil", limit=2, target="reach",
                    render_video=False)
        base.update(kwargs)
        return RunConfig(**base)

    def test_writes_one_artifact_per_stage(self):
        summary = run(self.video, self.words, self._cfg(), scanner=lambda *a, **k: self.scan,
                      log=lambda *_: None)
        out = self.root / "hasil"
        self.assertTrue((out / "transcript.json").is_file())
        self.assertTrue((out / "candidates.json").is_file())
        self.assertTrue((out / "run.json").is_file())
        self.assertTrue(summary.clips)
        for clip in summary.clips:
            clip_dir = Path(clip["dir"])
            self.assertTrue((clip_dir / "clip.json").is_file())
            self.assertTrue((clip_dir / "caption.ass").is_file())
            self.assertGreaterEqual(clip["duration"], 8.0)

    def test_candidate_range_limits_processing_to_selected_clip(self):
        complete = run(
            self.video, self.words, self._cfg(limit=2),
            scanner=lambda *a, **k: self.scan, log=lambda *_: None,
        )
        selected = complete.clips[0]["source_candidate"]
        result = run(
            self.video, self.words,
            self._cfg(candidate_ranges=[(selected["start"], selected["end"])]),
            scanner=lambda *a, **k: self.scan, log=lambda *_: None,
        )
        self.assertEqual(len(result.clips), 1)
        self.assertEqual(result.clips[0]["source_candidate"], selected)

    def test_selected_candidate_limits_default_face_scan_to_clip_range(self):
        complete = run(
            self.video, self.words, self._cfg(limit=1),
            scanner=lambda *a, **k: self.scan, log=lambda *_: None,
        )
        selected = complete.clips[0]["source_candidate"]
        with patch(
            "clippergod.pipeline.runner._scan_default", return_value=self.scan,
        ) as default_scan:
            run(
                self.video, self.words,
                self._cfg(
                    out_dir=self.root / "selected-scan",
                    limit=1,
                    candidate_ranges=[(selected["start"], selected["end"], selected["title"])],
                ),
                log=lambda *_: None,
            )
        self.assertEqual(
            default_scan.call_args.kwargs["scan_range"],
            (selected["start"], selected["end"]),
        )

    def test_face_scan_only_detects_frames_in_requested_range(self):
        class Detector:
            def __init__(self):
                self.frames = 0

            def detect(self, _frame):
                self.frames += 1
                return []

        detector = Detector()
        scan = scan_video(
            self.video, detector=detector, sample_fps=2,
            start_seconds=10.0, end_seconds=12.0,
        )

        self.assertAlmostEqual(scan.duration, 2.0, places=1)
        self.assertGreater(detector.frames, 0)
        self.assertLessEqual(detector.frames, 6)

    def test_candidate_ranges_preserve_the_requested_selection_order(self):
        complete = run(
            self.video, self.words, self._cfg(limit=2),
            scanner=lambda *a, **k: self.scan, log=lambda *_: None,
        )
        selected = [clip["source_candidate"] for clip in complete.clips[:2]]
        result = run(
            self.video, self.words,
            self._cfg(
                out_dir=self.root / "reordered",
                limit=2,
                candidate_ranges=[
                    (item["start"], item["end"], item["title"])
                    for item in reversed(selected)
                ],
            ),
            scanner=lambda *a, **k: self.scan, log=lambda *_: None,
        )
        self.assertEqual(
            [clip["source_candidate"] for clip in result.clips],
            list(reversed(selected)),
        )

    def test_captions_are_relative_to_clip_start(self):
        summary = run(self.video, self.words, self._cfg(limit=1),
                      scanner=lambda *a, **k: self.scan, log=lambda *_: None)
        clip = summary.clips[0]
        ass = Path(clip["captions"]["ass"]).read_text(encoding="utf-8")
        stamps = [line.split(",")[1] for line in ass.splitlines() if line.startswith("Dialogue:")]
        self.assertTrue(stamps)
        first = stamps[0]  # 0:00:00.xx
        self.assertTrue(first.startswith("0:00:0"), first)
        self.assertLess(float(first.split(":")[-1]), 5.0)

    def test_crop_expression_is_ready_for_ffmpeg(self):
        summary = run(self.video, self.words, self._cfg(limit=1),
                      scanner=lambda *a, **k: self.scan, log=lambda *_: None)
        crop = summary.clips[0]["crop"]
        self.assertEqual(crop["w"], 405)
        self.assertIn("expression", crop)
        self.assertTrue(crop["expression"].startswith("max(0,min("))
        self.assertGreater(crop["face_samples"], 0)

    def test_render_metadata_recorded_when_rendering(self):
        summary = run(self.video, self.words, self._cfg(limit=1, render_video=True),
                      scanner=lambda *a, **k: self.scan,
                      renderer=self.renderer, log=lambda *_: None)
        clip = summary.clips[0]
        self.assertEqual(clip["render"]["width"], 1080)
        self.assertEqual(clip["render"]["height"], 1920)
        self.assertTrue(Path(clip["video"]).is_file())
        self.assertEqual(len(self.renderer.calls), 1)
        self.assertEqual(self.renderer.calls[0].crop_w, 405)

    def test_output_formats_set_dimensions_and_caption_canvas(self):
        formats = {
            "portrait": (1080, 1920),
            "square": (1080, 1080),
            "landscape": (1920, 1080),
        }
        for output_format, size in formats.items():
            with self.subTest(output_format=output_format):
                summary = run(
                    self.video, self.words,
                    self._cfg(out_dir=self.root / output_format, limit=1, render_video=True,
                              output_format=output_format),
                    scanner=lambda *a, **k: self.scan,
                    renderer=self.renderer, log=lambda *_: None,
                )
                clip = summary.clips[0]
                spec = self.renderer.calls[-1]
                self.assertEqual((spec.out_w, spec.out_h), size)
                self.assertEqual(clip["output_size"], {"width": size[0], "height": size[1]})
                ass = Path(clip["captions"]["ass"]).read_text(encoding="utf-8")
                self.assertIn(f"PlayResX: {size[0]}", ass)
                self.assertIn(f"PlayResY: {size[1]}", ass)

    def test_rerun_skips_without_calling_renderer(self):
        cfg = self._cfg(limit=1, render_video=True)
        run(self.video, self.words, cfg, scanner=lambda *a, **k: self.scan,
            renderer=self.renderer, log=lambda *_: None)
        summary = run(self.video, self.words, cfg, scanner=lambda *a, **k: self.scan,
                      renderer=self.renderer, log=lambda *_: None)
        self.assertEqual(summary.skipped, 1)
        self.assertEqual(len(self.renderer.calls), 1, "renderer tidak boleh dipanggil lagi")

    def test_caption_config_change_invalidates_cached_render(self):
        cfg = self._cfg(limit=1, render_video=True)
        run(self.video, self.words, cfg, scanner=lambda *a, **k: self.scan,
            renderer=self.renderer, log=lambda *_: None)

        updated = self._cfg(limit=1, render_video=True,
                            caption=caption_from_dict({"uppercase": True}))
        summary = run(self.video, self.words, updated, scanner=lambda *a, **k: self.scan,
                      renderer=self.renderer, log=lambda *_: None)
        self.assertEqual(summary.skipped, 0)
        self.assertEqual(len(self.renderer.calls), 2)

    def test_force_rerenders(self):
        cfg = self._cfg(limit=1, render_video=True, force=True)
        run(self.video, self.words, cfg, scanner=lambda *a, **k: self.scan,
            renderer=self.renderer, log=lambda *_: None)
        run(self.video, self.words, cfg, scanner=lambda *a, **k: self.scan,
            renderer=self.renderer, log=lambda *_: None)
        self.assertEqual(len(self.renderer.calls), 2)

    def test_empty_transcript_is_rejected(self):
        with self.assertRaises(ValueError):
            run(self.video, [], self._cfg(), scanner=lambda *a, **k: self.scan,
                log=lambda *_: None)

    def test_stale_clip_dirs_are_reported_not_deleted(self):
        cfg = self._cfg(limit=1)
        run(self.video, self.words, cfg, scanner=lambda *a, **k: self.scan,
            log=lambda *_: None)
        stale = self.root / "hasil" / "clips" / "99_klip-lama"
        stale.mkdir(parents=True)
        (stale / "clip.json").write_text("{}", encoding="utf-8")

        run(self.video, self.words, cfg, scanner=lambda *a, **k: self.scan,
            log=lambda *_: None)
        summary = json.loads((self.root / "hasil" / "run.json").read_text(encoding="utf-8"))
        self.assertIn("99_klip-lama", summary["stale_dirs"])
        self.assertTrue(stale.is_dir(), "folder lama tidak boleh dihapus otomatis")

    def test_clip_never_runs_past_end_of_video(self):
        longer = _transcript(seconds=75.0)
        summary = run(self.video, longer, self._cfg(limit=2),
                      scanner=lambda *a, **k: _scan(75.0), log=lambda *_: None)
        probe_duration = summary.probe["duration"]
        self.assertTrue(summary.clips)
        for clip in summary.clips:
            self.assertLessEqual(clip["end"], probe_duration + 0.01, clip["title"])
            self.assertGreaterEqual(clip["duration"], 8.0)


class CliTest(unittest.TestCase):
    def test_run_without_render_creates_run_json(self):
        from clippergod.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "v.mp4"
            _make_video(video, seconds=45)
            transcript = root / "t.json"
            transcript.write_text(json.dumps({"words": words_to_dicts(_transcript())}),
                                  encoding="utf-8")
            code = main(["run", str(video), "--transcript", str(transcript),
                         "--out", str(root / "out"), "--no-render",
                         "--target", "reach", "--limit", "1", "--format", "landscape"])
            self.assertEqual(code, 0)
            summary = json.loads((root / "out" / "run.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(summary["count"], 1)
            self.assertEqual(summary["config"]["output_size"], {"width": 1920, "height": 1080})

    def test_missing_transcript_returns_error_code(self):
        from clippergod.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "v.mp4"
            _make_video(video, seconds=3)
            code = main(["run", str(video), "--transcript", str(Path(tmp) / "nope.json"),
                         "--out", str(Path(tmp) / "out")])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
