"""Pembatalan harus menghentikan ekstraksi audio dan iterasi transkripsi."""

from __future__ import annotations

import tempfile
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from clippergod.pipeline.asr import (
    FasterWhisperTranscriber,
    extract_audio,
    extract_audio_segment,
)
from clippergod.progress import CancelToken, CancelledError


class TranscriberCancellationTest(unittest.TestCase):
    def test_faster_whisper_reports_audio_coverage_and_runtime_backend(self):
        events = []

        class FakeModel:
            def transcribe(self, *_args, **_kwargs):
                return iter([
                    SimpleNamespace(end=4.0, words=[
                        SimpleNamespace(word="halo", start=0.0, end=0.5, probability=1.0)
                    ]),
                ]), SimpleNamespace(duration=10.0)

        transcriber = FasterWhisperTranscriber()
        transcriber._model = FakeModel()
        transcriber.resolved_device = "cuda"
        transcriber.resolved_compute_type = "float16"

        words = transcriber.transcribe("audio.wav", on_progress=events.append)

        self.assertEqual(len(words), 1)
        self.assertEqual([event["stage"] for event in events], ["model_load", "model_ready", "transcribe"])
        self.assertEqual(events[-1]["processed_seconds"], 4.0)
        self.assertEqual(events[-1]["duration_seconds"], 10.0)
        self.assertEqual(events[-1]["device"], "cuda")
        self.assertEqual(events[-1]["compute_type"], "float16")

    def test_faster_whisper_checks_cancellation_between_segments(self):
        cancel = CancelToken()

        class FakeModel:
            def transcribe(self, *_args, **_kwargs):
                def segments():
                    yield SimpleNamespace(words=[
                        SimpleNamespace(word="halo", start=0.0, end=0.5, probability=1.0)
                    ])
                    cancel.cancel()
                    yield SimpleNamespace(words=[])

                return segments(), None

        transcriber = FasterWhisperTranscriber()
        transcriber._model = FakeModel()
        with self.assertRaises(CancelledError):
            transcriber.transcribe("audio.wav", cancel=cancel)

    def test_audio_extraction_terminates_ffmpeg_when_cancelled(self):
        cancel = CancelToken()

        class FakeProcess:
            returncode = None
            terminated = False

            def communicate(self, timeout=None):
                if timeout == 0.15:
                    cancel.cancel()
                    raise subprocess.TimeoutExpired("ffmpeg", timeout)
                return "", ""

            def terminate(self):
                self.terminated = True
                self.returncode = -1

            def poll(self):
                return self.returncode

        process = FakeProcess()
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch("clippergod.pipeline.render.resolve_ffmpeg", return_value="ffmpeg"), \
                patch("clippergod.pipeline.asr.subprocess.Popen", return_value=process):
            with self.assertRaises(CancelledError):
                extract_audio("source.mp4", Path(temp_dir) / "audio.wav", cancel=cancel)
        self.assertTrue(process.terminated)

    def test_selected_segment_extraction_seeks_and_limits_duration(self):
        process = SimpleNamespace(returncode=0, communicate=lambda timeout=None: ("", ""))
        with tempfile.TemporaryDirectory() as temp_dir, \
                patch("clippergod.pipeline.render.resolve_ffmpeg", return_value="ffmpeg"), \
                patch("clippergod.pipeline.asr.subprocess.Popen", return_value=process) as popen:
            result = extract_audio_segment(
                "source.mp4", Path(temp_dir) / "selected.wav", 12.5, 28.0,
            )
        self.assertEqual(result.name, "selected.wav")
        command = popen.call_args.args[0]
        self.assertEqual(command[command.index("-ss") + 1], "12.500")
        self.assertEqual(command[command.index("-t") + 1], "28.000")

    def test_selected_segment_rejects_invalid_range(self):
        with self.assertRaisesRegex(ValueError, "waktu awal"):
            extract_audio_segment("source.mp4", "selected.wav", -1, 2)
        with self.assertRaisesRegex(ValueError, "durasi"):
            extract_audio_segment("source.mp4", "selected.wav", 0, 0)


if __name__ == "__main__":
    unittest.main()
