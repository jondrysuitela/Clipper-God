"""Job satu tombol: import -> transkripsi (palsu) -> potong, tanpa render."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from clippergod.core.models import ClipCandidate, Word
from clippergod.jobs import Job, JobManager, _words_in_candidate_windows
from clippergod.pipeline.local_hook_ai import HookAnalysis, OllamaUnavailableError
from clippergod.project.schema import Clip, MediaRef, Project, fingerprint_file
from clippergod.project.store import ProjectStore

SENTENCES = [
    "kenapa podcast kamu sepi penonton padahal isinya bagus",
    "jawabannya bukan di kamera mahal atau lampu studio",
    "tapi di tiga kebiasaan kecil yang sering dilewatkan",
    "pertama kamu tidak pernah memotong bagian membosankan",
    "kedua judulnya tidak menjanjikan apa pun",
    "ketiga kamu selalu mulai dari sapaan panjang",
]


def transcript() -> list[Word]:
    words: list[Word] = []
    t = 0.3
    for sentence in SENTENCES:
        for token in sentence.split():
            words.append(Word(token, round(t, 2), round(t + 0.45, 2)))
            t += 0.50
        words[-1] = Word(words[-1].text + ".", words[-1].start, words[-1].end)
        t += 0.40
    return words


def make_video(path: Path, seconds: float = 22.0, fps: int = 10) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (320, 240))
    for i in range(int(seconds * fps)):
        frame = np.full((240, 320, 3), (i * 3) % 255, dtype=np.uint8)
        cv2.circle(frame, (160 + int(20 * np.sin(i / 8)), 120), 40, (200, 180, 160), -1)
        writer.write(frame)
    writer.release()


class ScriptedTranscriber:
    def __init__(self, words: list[Word], delay: float = 0.0) -> None:
        self.words = words
        self.delay = delay

    def transcribe(self, audio_path, language: str = "id") -> list[Word]:
        if self.delay:
            time.sleep(self.delay)
        return list(self.words)


def manager(root: Path, delay: float = 0.0) -> JobManager:
    return JobManager(
        root,
        transcriber_factory=lambda model: ScriptedTranscriber(transcript(), delay),
        audio_extractor=lambda src, dst: dst,  # video uji tidak punya audio
    )


class JobTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.video = self.root / "sumber.avi"
        make_video(self.video)
        self.out = self.root / "studio"

    def tearDown(self):
        self.tmp.cleanup()

    def wait(self, manager: JobManager, timeout: float = 90.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = manager.current()
            if job and job["status"] != "running":
                return job
            time.sleep(0.2)
        self.fail("job tidak selesai dalam batas waktu")

    def test_one_click_flow_produces_project(self):
        boss = manager(self.out)
        boss.start(self.video, target="reach", limit=2, output_format="square", render=False)
        job = self.wait(boss)

        self.assertEqual(job["status"], "done", job)
        self.assertGreaterEqual(job["clips"], 1)
        self.assertTrue((self.out / "transcript.json").is_file())

        project = ProjectStore(self.out / "project.cgproj").load()
        self.assertEqual(len(project.clips), job["clips"])
        self.assertEqual(project.clips[0].status, "candidate")
        self.assertEqual(project.settings["export"]["format"], "square")
        self.assertEqual(project.settings["export"]["width"], 1080)
        self.assertEqual(project.settings["export"]["height"], 1080)
        self.assertTrue(any((self.out / "clips").glob("*/clip.json")))

    def test_deferred_local_job_stops_after_transcript_and_candidates(self):
        boss = manager(self.out)
        boss.start(self.video, target="reach", limit=2, render=False, defer_video=True)
        job = self.wait(boss)

        self.assertEqual(job["status"], "ready", job)
        self.assertGreaterEqual(job["clips"], 1)
        self.assertTrue((self.out / "transcript.json").is_file())
        self.assertFalse(any((self.out / "clips").glob("*/clip.mp4")))

        project = ProjectStore(self.out / "project.cgproj").load()
        self.assertEqual(project.media.path, str(self.video))
        self.assertTrue(project.extra["preview"])
        self.assertEqual(len(project.clips), job["clips"])

    def test_deferred_hook_scan_uses_tiny_and_persists_candidate_windows_only(self):
        models: list[str] = []
        boss = JobManager(
            self.out,
            transcriber_factory=lambda model: (
                models.append(model) or ScriptedTranscriber(transcript())
            ),
            audio_extractor=lambda src, dst: dst,
        )
        boss.start(
            self.video, target="reach", limit=2, render=False,
            defer_video=True, model="medium",
        )

        job = self.wait(boss)

        self.assertEqual(job["status"], "ready", job)
        self.assertEqual(models, ["tiny"])
        project = ProjectStore(self.out / "project.cgproj").load()
        self.assertEqual(project.extra["transcript_scope"], "candidate_windows")
        transcript_file = __import__("json").loads(
            (self.out / "transcript.json").read_text(encoding="utf-8")
        )
        self.assertEqual(transcript_file["model"], "tiny")
        self.assertEqual(transcript_file["scope"], "candidate_windows")

    def test_coarse_workspace_words_exclude_audio_outside_candidate_windows(self):
        words = transcript() + [Word("jauh", 100.0, 100.4)]
        candidates = [SimpleNamespace(start=0.0, end=2.0)]

        result = _words_in_candidate_windows(words, candidates)

        self.assertTrue(result)
        self.assertNotIn("jauh", [word.text for word in result])

    def test_preview_persists_only_the_requested_number_of_candidates(self):
        boss = manager(self.out)
        candidates = [
            ClipCandidate(
                start=index * 30.0,
                end=index * 30.0 + 25.0,
                title=f"Kandidat {index + 1}",
                score=90.0 - index,
            )
            for index in range(6)
        ]
        meta = {
            "id": "abc123",
            "title": "Podcast",
            "duration": 200.0,
            "webpage_url": "https://youtu.be/abc123",
        }

        with patch(
            "clippergod.pipeline.candidates.generate", return_value=candidates,
        ):
            count, _ranges, _summary, warning = boss._publish_preview(
                "https://youtu.be/abc123", meta, [], "reach", 3, "fill",
                preview_only=True,
            )

        project = ProjectStore(self.out / "project.cgproj").load()
        self.assertIsNone(warning)
        self.assertEqual(count, 3)
        self.assertEqual(len(project.clips), 3)
        self.assertEqual(
            [clip.title for clip in project.clips],
            ["Kandidat 1", "Kandidat 2", "Kandidat 3"],
        )
        self.assertEqual(project.extra["candidate_limit"], 3)

    def test_ollama_ranking_selects_candidates_for_render_and_marks_them(self):
        words = [
            Word(word.text, word.start + index * 30, word.end + index * 30)
            for index in range(4)
            for word in transcript()
        ]
        boss = JobManager(
            self.out,
            transcriber_factory=lambda model: ScriptedTranscriber(words),
            audio_extractor=lambda src, dst: dst,
        )

        def rank_last_first(candidates, _config, **_kwargs):
            return [
                (candidate_id, HookAnalysis(95.0 - index, ("Strong opening",)))
                for index, (candidate_id, _text) in enumerate(reversed(candidates))
            ]

        with patch(
            "clippergod.pipeline.local_hook_ai.rank_hooks",
            side_effect=rank_last_first,
        ) as rank, patch("clippergod.jobs.import_media"), patch(
            "clippergod.jobs.run",
            return_value=SimpleNamespace(clips=[{"video": None}]),
        ) as pipeline_run:
            boss.start(
                self.video, target="reach", limit=1, render=False,
                ollama_model="test-model",
            )
            job = self.wait(boss)

        self.assertEqual(job["status"], "done", job)
        self.assertGreaterEqual(len(rank.call_args.args[0]), 2)
        self.assertIn("source_metadata", rank.call_args.kwargs)
        project = ProjectStore(self.out / "project.cgproj").load()
        self.assertEqual(len(project.clips), 1)
        selected_id = project.extra["ollama_selection"]["selected_clip_ids"][0]
        selected = project.clip(selected_id)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.status, "approved")
        self.assertEqual(project.extra["hook_ai"][selected_id]["score"], 95.0)
        self.assertEqual(
            pipeline_run.call_args.args[2].candidate_ranges,
            [(selected.start, selected.end, selected.title)],
        )

    def test_ollama_unavailable_falls_back_to_heuristic_and_warns(self):
        boss = manager(self.out)
        with patch(
            "clippergod.pipeline.local_hook_ai.rank_hooks",
            side_effect=OllamaUnavailableError("connection refused"),
        ):
            boss.start(
                self.video, target="reach", limit=1, render=False,
                defer_video=True, ollama_model="missing-model",
            )
            job = self.wait(boss)

        self.assertEqual(job["status"], "ready", job)
        self.assertIn("skor heuristik", job["warning"])
        project = ProjectStore(self.out / "project.cgproj").load()
        self.assertTrue(project.extra["ollama_selection"]["fallback"])
        self.assertEqual(
            sum(clip.status == "approved" for clip in project.clips), 1,
        )

    def test_selected_candidate_transcribes_only_clip_and_reuses_accurate_words(self):
        models: list[str] = []
        boss = JobManager(
            self.out,
            transcriber_factory=lambda model: (
                models.append(model) or ScriptedTranscriber(transcript())
            ),
            audio_extractor=lambda src, dst: dst,
        )
        boss.start(self.video, target="reach", limit=2, render=False, defer_video=True)
        self.assertEqual(self.wait(boss)["status"], "ready")
        clip = ProjectStore(self.out / "project.cgproj").load().clips[0]

        with patch("clippergod.jobs.import_media") as media_import, patch(
            "clippergod.jobs.run", return_value=SimpleNamespace(clips=[{"video": None}]),
        ) as pipeline_run:
            boss.process_selected(
                clip.id, target="reach", limit=1, render=False, model="medium",
            )
            job = self.wait(boss)
            boss.process_selected(
                clip.id, target="reach", limit=1, render=True, model="medium",
            )
            second_job = self.wait(boss)

        self.assertEqual(job["status"], "done", job)
        self.assertEqual(second_job["status"], "done", second_job)
        self.assertEqual(models, ["tiny", "medium"])
        media_import.assert_not_called()
        words = pipeline_run.call_args.args[1]
        config = pipeline_run.call_args.args[2]
        self.assertTrue(words)
        self.assertTrue(all(clip.start <= word.start < clip.end for word in words))
        self.assertAlmostEqual(words[0].start, clip.start + 0.3)
        self.assertEqual(config.candidate_ranges, [(clip.start, clip.end, clip.title)])
        self.assertTrue(config.preserve_unselected_clips)
        self.assertTrue(config.render_video)
        saved = ProjectStore(self.out / "project.cgproj").load()
        self.assertEqual(
            saved.extra["accurate_transcripts"][clip.id]["model"], "medium",
        )

    def test_selected_youtube_candidate_uses_downloaded_local_source_for_preview(self):
        source_url = "https://www.youtube.com/watch?v=example123"
        clip = Clip(start=0.0, end=1.0, title="Hook")
        project = Project(
            name="YouTube",
            media=MediaRef(path=source_url, duration=10.0),
            words=[Word("hook", 0.1, 0.5)],
            clips=[clip],
            extra={"source_url": source_url, "source_id": "example123"},
        )
        project.extra["accurate_transcripts"] = {
            clip.id: {
                "model": "medium",
                "language": "id",
                "source_fingerprint": "",
                "start": clip.start,
                "end": clip.end,
                "word_count": 1,
            },
        }
        store = ProjectStore(self.out / "project.cgproj")
        store.save(project)
        boss = JobManager(self.out, downloader=lambda *_args, **_kwargs: self.video)
        job = Job(id="youtube-preview-test", out_dir=str(self.out))

        with patch(
            "clippergod.jobs.run",
            return_value=SimpleNamespace(clips=[{"video": None}]),
        ):
            boss._process_selected_work(
                job, source_url, clip.id, clip.start, clip.end, clip.title,
                "reach", 1, "fill", "portrait", False, "id", "medium",
                None, True, source_url, "example123",
            )

        self.assertEqual(job.status, "done", job.error)
        saved = store.load()
        self.assertEqual(saved.media.path, str(self.video))
        self.assertEqual(saved.media.fingerprint, fingerprint_file(self.video))
        self.assertEqual(saved.extra["source_url"], source_url)

    def test_second_job_is_refused_while_running(self):
        boss = manager(self.out, delay=1.5)
        boss.start(self.video, limit=1, render=False)
        with self.assertRaises(RuntimeError):
            boss.start(self.video, limit=1, render=False)
        self.wait(boss)

    def test_isolated_worker_reports_failure_to_parent(self):
        boss = JobManager(self.out)
        job = Job(id="worker-test", out_dir=str(self.out))
        boss._job = job
        boss._launch(job, "unknown", (), lambda *_args: None)

        result = self.wait(boss)

        self.assertEqual(result["status"], "failed")
        self.assertIn("operasi worker tidak dikenal", result["error"])

    def test_isolated_worker_can_be_force_terminated(self):
        boss = JobManager(self.out)

        job = boss.start(self.video, limit=1, render=False)

        self.assertTrue(boss.cancel(job.id))
        self.assertEqual(boss.current()["status"], "cancelled")

    def test_cancel_stops_job_before_project_is_written(self):
        transcribing = threading.Event()
        continue_transcription = threading.Event()

        class BlockingTranscriber:
            def transcribe(self, audio_path, language: str = "id") -> list[Word]:
                transcribing.set()
                if not continue_transcription.wait(5):
                    raise TimeoutError("test transcriber timed out")
                return transcript()

        boss = JobManager(
            self.out,
            transcriber_factory=lambda model: BlockingTranscriber(),
            audio_extractor=lambda src, dst: dst,
        )
        boss.start(self.video, limit=1, render=False)
        try:
            self.assertTrue(transcribing.wait(10), "transcriber tidak mulai")
            job_id = boss.current()["id"]
            self.assertTrue(boss.cancel(job_id))
        finally:
            continue_transcription.set()

        job = self.wait(boss)
        self.assertEqual(job["status"], "cancelled")
        self.assertFalse((self.out / "project.cgproj").exists())

    def test_missing_video_rejected_immediately(self):
        boss = manager(self.out)
        with self.assertRaises(ValueError):
            boss.start(self.root / "tidak-ada.mp4")

    def test_empty_ollama_model_is_rejected_when_ai_selection_is_requested(self):
        boss = manager(self.out)
        with self.assertRaisesRegex(ValueError, "nama model Ollama"):
            boss.start(self.video, ollama_model=" ")

    def test_transcript_review_runs_second_asr_and_keeps_original_words(self):
        project = Project(
            name="Sumber",
            media=MediaRef(path=str(self.video)),
            words=transcript(),
        )
        store = ProjectStore(self.out / "project.cgproj")
        store.save(project)
        (self.out / "transcript.json").write_text(
            '{"language":"id"}', encoding="utf-8"
        )
        second_pass = transcript() + [Word("tambahan", 20.0, 20.4)]
        boss = JobManager(
            self.out,
            transcriber_factory=lambda model: ScriptedTranscriber(second_pass),
            audio_extractor=lambda src, dst: dst,
        )
        differences = [{
            "id": "0", "start": 0.0, "end": 30.0,
            "primary": "transkrip awal", "second_pass": "transkrip ulang",
            "assessment": "possible_missed_words", "note": "Ada kata berbeda.",
        }]

        with patch(
            "clippergod.pipeline.local_hook_ai.ensure_ollama_model"
        ) as ensure_model, patch(
            "clippergod.pipeline.local_hook_ai.review_transcript",
            return_value=differences,
        ) as review:
            boss.review_transcript(
                ollama_model="test-ollama", asr_model="medium"
            )
            job = self.wait(boss)

        self.assertEqual(job["status"], "done")
        self.assertEqual(job["kind"], "transcript_review")
        self.assertEqual(job["clips"], 1)
        ensure_model.assert_called_once()
        review.assert_called_once()
        saved = store.load()
        self.assertEqual(saved.words, transcript())
        self.assertEqual(saved.extra["transcript_review"]["differences"], differences)

    def test_transcript_review_rejects_unknown_asr_model(self):
        boss = manager(self.out)
        with self.assertRaisesRegex(ValueError, "model ASR pemeriksa"):
            boss.review_transcript(
                ollama_model="test-ollama", asr_model="unknown"
            )

    def test_video_without_audio_gets_clear_error(self):
        boss = JobManager(self.out, transcriber_factory=lambda model: ScriptedTranscriber([]))
        boss.start(self.video, limit=1, render=False)
        job = self.wait(boss)
        self.assertEqual(job["status"], "failed")
        self.assertIn("trek audio", job["error"])

    def test_youtube_url_is_downloaded_before_import(self):
        calls: list[str] = []
        meta = {"id": "abc123", "title": "Uji", "duration": 22.0,
                "thumbnail": "", "uploader": "kanal", "webpage_url": "https://youtu.be/abc123"}

        def fake_download(url, out_dir, **kwargs):
            calls.append(url)
            kwargs.get("progress", lambda *_: None)(50.0, "uji")
            return self.video

        boss = JobManager(
            self.out,
            transcriber_factory=lambda model: ScriptedTranscriber(transcript()),
            audio_extractor=lambda src, dst: dst,
            downloader=fake_download,
            probe=lambda url: meta,
            audio_downloader=lambda url, out_dir, **kw: self.video,
        )
        boss.start("https://youtu.be/abc123", limit=1, render=False)
        job = self.wait(boss)
        self.assertEqual(job["status"], "done", job)
        self.assertEqual(calls, ["https://youtu.be/abc123"])

        project = ProjectStore(self.out / "project.cgproj").load()
        self.assertEqual(project.extra.get("source_url"), "https://youtu.be/abc123")
        self.assertEqual(project.extra.get("source_id"), "abc123")
        self.assertNotIn("preview", project.extra)

    def test_deferred_youtube_job_downloads_source_for_local_candidate_preview(self):
        video_downloads: list[str] = []
        meta = {"id": "abc123", "title": "Uji", "duration": 22.0,
                "thumbnail": "", "uploader": "kanal", "webpage_url": "https://youtu.be/abc123"}

        def fake_download(url, out_dir, **kwargs):
            video_downloads.append(url)
            return self.video

        boss = JobManager(
            self.out,
            transcriber_factory=lambda model: ScriptedTranscriber(transcript()),
            audio_extractor=lambda src, dst: dst,
            downloader=fake_download,
            probe=lambda url: meta,
            audio_downloader=lambda url, out_dir, **kw: self.video,
        )
        boss.start("https://youtu.be/abc123", limit=1, render=False, defer_video=True)
        job = self.wait(boss)

        self.assertEqual(job["status"], "ready", job)
        self.assertEqual(video_downloads, ["https://youtu.be/abc123"])
        project = ProjectStore(self.out / "project.cgproj").load()
        self.assertEqual(project.extra["source_url"], "https://youtu.be/abc123")
        self.assertTrue(project.extra["preview"])
        self.assertEqual(project.media.path, str(self.video))
        self.assertEqual(project.media.fingerprint, fingerprint_file(self.video))
        transcript_data = json.loads(
            (self.out / "transcript.json").read_text(encoding="utf-8")
        )
        self.assertEqual(transcript_data["scope"], "candidate_windows")

    def test_unsupported_url_rejected(self):
        boss = manager(self.out)
        with self.assertRaises(ValueError):
            boss.start("https://vimeo.com/123", limit=1, render=False)
        with self.assertRaises(ValueError):
            boss.start("javascript:alert(1)", limit=1, render=False)

    def test_unknown_output_format_rejected(self):
        boss = manager(self.out)
        with self.assertRaisesRegex(ValueError, "format output"):
            boss.start(self.video, output_format="cinema", render=False)


if __name__ == "__main__":
    unittest.main()
