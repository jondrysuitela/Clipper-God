"""Progress & batal: token harus menghentikan run, bukan sekadar diabaikan."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clippergod.core.models import Word
from clippergod.pipeline.runner import RunConfig, run
from clippergod.progress import CancelToken, CancelledError, Progress


class TestCancelToken(unittest.TestCase):
    def test_starts_clean(self):
        token = CancelToken()
        token.raise_if_cancelled()          # tidak melempar
        self.assertFalse(token.cancelled)

    def test_cancel_is_sticky(self):
        token = CancelToken()
        token.cancel()
        self.assertTrue(token.cancelled)
        with self.assertRaises(CancelledError):
            token.raise_if_cancelled()


class TestProgress(unittest.TestCase):
    def test_emits_percent_per_stage(self):
        seen: list[dict] = []
        p = Progress(emit=seen.append)
        p.start("faces", 4)
        p.advance(2)
        self.assertEqual([e["stage"] for e in seen], ["faces", "faces"])
        self.assertEqual(seen[-1]["percent"], 50.0)

    def test_no_callback_is_silent(self):
        p = Progress()
        p.start("x", 2)
        p.advance()                          # tidak boleh melempar

    def test_total_zero_has_no_percent(self):
        seen: list[dict] = []
        p = Progress(emit=seen.append)
        p.start("probe")
        self.assertIsNone(seen[-1]["percent"])


class TestRunHonoursCancel(unittest.TestCase):
    def test_pre_cancelled_run_stops_before_touching_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = CancelToken()
            token.cancel()
            cfg = RunConfig(out_dir=Path(tmp) / "out", render_video=False, cancel=token)
            with self.assertRaises(CancelledError):
                run("tidak-ada.mp4", [Word("halo", 0.0, 0.5)], cfg)
            self.assertFalse((Path(tmp) / "out").exists())


if __name__ == "__main__":
    unittest.main()
