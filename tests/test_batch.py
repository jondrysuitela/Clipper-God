"""Test batch queue: status di disk, lanjut setelah gagal, dan validasi manifest."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from clippergod.core.models import FaceBox, Word
from clippergod.pipeline.batch import (
    DONE,
    FAILED,
    ManifestError,
    load_manifest,
    run_batch,
)
from clippergod.pipeline.faces import FaceScan
from clippergod.pipeline.render import RenderResult


def _make_video(path: Path, seconds: int = 45) -> None:
    w, h = 320, 180
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (w, h))
    if not writer.isOpened():
        raise unittest.SkipTest("VideoWriter tidak tersedia")
    frame = np.full((h, w, 3), 30, dtype=np.uint8)
    for i in range(seconds * 30):
        frame[:, :, 0] = 30 + (i % 30)
        writer.write(frame)
    writer.release()


def _words(seconds: float = 45.0) -> list[Word]:
    lines = [
        "Kenapa podcast kamu sepi penonton padahal isinya bagus sekali",
        "Tiga detik pertama menentukan apakah orang bertahan atau langsung geser",
        "Hook yang lemah membuat algoritma tidak punya alasan menyebarkan klip",
        "Potong selalu di akhir kalimat supaya idenya tetap utuh dan jelas",
        "Caption harus mengikuti transkrip yang sama bukan struktur terpisah",
        "Framing ikuti wajah yang sedang bicara bukan wajah yang paling besar",
    ]
    words: list[Word] = []
    t, idx = 0.3, 0
    while t < seconds:
        line = lines[idx % len(lines)]
        idx += 1
        for token in line.split():
            if t >= seconds:
                break
            words.append(Word(text=token, start=round(t, 3), end=round(t + 0.35, 3)))
            t += 0.40
        t += 0.55
    return words


def _scan(seconds: float = 45.0) -> FaceScan:
    scan = FaceScan(width=1280, height=720)
    t = 0.0
    while t < seconds:
        scan.samples.append((round(t, 3), FaceBox(380, 180, 560, 420, track_id=1)))
        t += 0.25
    scan.track_hits = {1: len(scan.samples)}
    return scan


class FakeRenderer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, spec) -> RenderResult:
        self.calls.append(spec.dst)
        Path(spec.dst).parent.mkdir(parents=True, exist_ok=True)
        Path(spec.dst).write_bytes(b"fake")
        return RenderResult(path=spec.dst, width=1080, height=1920,
                            duration=spec.duration, size_mb=0.1, passes=2)


class BatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.video = self.root / "sumber.mp4"
        _make_video(self.video)
        self.words_path = self.root / "transkrip.json"
        self.words_path.write_text(
            json.dumps({"words": [{"text": w.text, "start": w.start, "end": w.end}
                                  for w in _words()]}),
            encoding="utf-8",
        )
        self.renderer = FakeRenderer()

    def tearDown(self):
        self.tmp.cleanup()

    def _manifest(self, jobs: list[dict]) -> Path:
        path = self.root / "manifest.json"
        path.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
        return path

    def _batch(self, manifest: Path, out: str = "antrean", **kwargs):
        kwargs.setdefault("scanner", lambda *a, **k: _scan())
        kwargs.setdefault("renderer", self.renderer)
        kwargs.setdefault("log", lambda *_: None)
        return run_batch(manifest, self.root / out, **kwargs)

    def test_two_jobs_done_and_one_missing_transcript_failed(self):
        manifest = self._manifest([
            {"id": "ep01", "video": str(self.video), "transcript": str(self.words_path),
             "target": "reach", "limit": 1},
            {"id": "ep02", "video": str(self.video), "transcript": str(self.words_path),
             "target": "reach", "limit": 1},
            {"id": "ep03", "video": str(self.video), "transcript": str(self.root / "hilang.json")},
        ])
        report = self._batch(manifest)

        self.assertEqual(report.done, 2)
        self.assertEqual(report.failed, 1)
        queue = json.loads((self.root / "antrean" / "queue.json").read_text(encoding="utf-8"))
        status = {job["id"]: job["status"] for job in queue["jobs"]}
        self.assertEqual(status, {"ep01": DONE, "ep02": DONE, "ep03": FAILED})
        self.assertIn("FileNotFoundError", queue["jobs"][2]["error"])
        self.assertEqual(len(self.renderer.calls), 2)

    def test_rerun_only_retries_failed_job(self):
        broken = self.root / "ep03.json"
        manifest = self._manifest([
            {"id": "ep01", "video": str(self.video), "transcript": str(self.words_path),
             "target": "reach", "limit": 1},
            {"id": "ep03", "video": str(self.video), "transcript": str(broken),
             "target": "reach", "limit": 1},
        ])
        first = self._batch(manifest)
        self.assertEqual((first.done, first.failed), (1, 1))
        calls_after_first = len(self.renderer.calls)

        broken.write_text(self.words_path.read_text(encoding="utf-8"), encoding="utf-8")
        second = self._batch(manifest)

        self.assertEqual(second.done, 2)
        self.assertEqual(second.failed, 0)
        self.assertEqual(len(self.renderer.calls), calls_after_first + 1,
                         "job yang sudah selesai tidak boleh dirender ulang")
        self.assertEqual(second.states[0].attempts, 1)

    def test_failed_job_stops_after_max_attempts(self):
        manifest = self._manifest([
            {"id": "ep01", "video": str(self.video), "transcript": str(self.root / "nope.json")},
        ])
        self._batch(manifest, max_attempts=1)
        report = self._batch(manifest, max_attempts=1)
        self.assertEqual(report.failed, 1)
        self.assertEqual(report.states[0].attempts, 1, "tidak dicoba lagi setelah batas")

    def test_stop_on_error_leaves_rest_pending(self):
        manifest = self._manifest([
            {"id": "ep01", "video": str(self.video), "transcript": str(self.root / "nope.json")},
            {"id": "ep02", "video": str(self.video), "transcript": str(self.words_path)},
        ])
        report = self._batch(manifest, stop_on_error=True)
        self.assertEqual(report.failed, 1)
        self.assertEqual(report.states[1].status, "pending")

    def test_corrupt_queue_file_does_not_crash(self):
        out = self.root / "antrean"
        out.mkdir()
        (out / "queue.json").write_text("{bukan json", encoding="utf-8")
        manifest = self._manifest([
            {"id": "ep01", "video": str(self.video), "transcript": str(self.words_path),
             "target": "reach", "limit": 1},
        ])
        report = self._batch(manifest)
        self.assertEqual(report.done, 1)

    def test_job_caption_config_is_applied(self):
        caption = self.root / "caption.json"
        caption.write_text(json.dumps({"uppercase": True, "karaoke": False}),
                           encoding="utf-8")
        manifest = self._manifest([
            {"id": "ep01", "video": str(self.video), "transcript": str(self.words_path),
             "target": "reach", "limit": 1, "caption": str(caption)},
        ])
        report = self._batch(manifest)
        self.assertEqual(report.done, 1)

        clip_json = next((self.root / "antrean" / "ep01" / "clips").glob("*/clip.json"))
        ass = Path(json.loads(clip_json.read_text(encoding="utf-8"))["captions"]["ass"])
        text = ass.read_text(encoding="utf-8")
        self.assertNotIn(r"\kf", text)
        dialogue = [l for l in text.splitlines() if l.startswith("Dialogue:")]
        self.assertTrue(dialogue)
        body = dialogue[0].split(",", 9)[-1]
        body = re.sub(r"\{[^}]*\}", "", body)  # buang tag \an/\pos/\fad
        letters = [c for c in body if c.isalpha() and c.isascii()]
        self.assertTrue(letters)
        self.assertTrue(all(c.isupper() for c in letters), body)

    def test_force_reprocesses_done_job(self):
        manifest = self._manifest([
            {"id": "ep01", "video": str(self.video), "transcript": str(self.words_path),
             "target": "reach", "limit": 1},
        ])
        self._batch(manifest)
        calls = len(self.renderer.calls)
        self._batch(manifest, force=True)
        self.assertGreater(len(self.renderer.calls), calls)


class ManifestTest(unittest.TestCase):
    def _write(self, payload) -> Path:
        import tempfile
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(payload, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_rejects_empty_jobs(self):
        with self.assertRaises(ManifestError):
            load_manifest(self._write({"jobs": []}))

    def test_rejects_duplicate_id(self):
        path = self._write({"jobs": [
            {"id": "a", "video": "v.mp4", "transcript": "t.json"},
            {"id": "a", "video": "v.mp4", "transcript": "t.json"},
        ]})
        with self.assertRaises(ManifestError):
            load_manifest(path)

    def test_requires_video_and_transcript(self):
        with self.assertRaises(ManifestError):
            load_manifest(self._write({"jobs": [{"id": "a", "video": "v.mp4"}]}))

    def test_accepts_bare_list(self):
        path = self._write([{"id": "a", "video": "v.mp4", "transcript": "t.json"}])
        jobs = load_manifest(path)
        self.assertEqual(jobs[0].id, "a")
        self.assertEqual(jobs[0].target, "watch")


if __name__ == "__main__":
    unittest.main()
