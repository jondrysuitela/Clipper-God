"""`.cgproj` harus bisa dibuka lagi setelah run, bukan cuma ditulis."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clippergod.core.models import Word
from clippergod.pipeline.bridge import build_project, save_project
from clippergod.project.store import ProjectStore


def sample_clips():
    return [
        {"start": 0.3, "end": 22.9, "title": "klip satu", "score": 72.5, "layout": "split"},
        {"start": 5.0, "end": 5.0, "title": "rusak", "score": 1.0},  # harus dilewati
    ]


class TestBridge(unittest.TestCase):
    def test_roundtrip_through_store(self):
        words = [Word("halo", 0.0, 0.4), Word("dunia", 0.5, 0.9)]
        info = {"duration": 46.0, "width": 1280, "height": 720, "fps": 30.0}
        with tempfile.TemporaryDirectory() as tmp:
            project = build_project(
                Path(tmp) / "video.mp4", words, info, sample_clips(),
                name="Episode 1", layout="fill", speakers={"bindings": []},
                export={"bitrate_mbps": 9.0},
            )
            path = save_project(project, tmp)
            self.assertTrue(path.is_file())

            loaded = ProjectStore(path).load()
            self.assertEqual(loaded.name, "Episode 1")
            self.assertEqual(len(loaded.words), 2)
            self.assertEqual(len(loaded.clips), 1)          # klip rusak dilewati
            self.assertEqual(loaded.clips[0].layout, "split")
            self.assertEqual(loaded.clips[0].status, "candidate")
            self.assertAlmostEqual(loaded.media.duration, 46.0)
            self.assertEqual(loaded.settings["export"]["bitrate_mbps"], 9.0)
            self.assertEqual(loaded.settings["export"]["fps"], 30)  # default tetap ada

    def test_project_survives_reopen(self):
        info = {"duration": 10.0, "width": 1920, "height": 1080, "fps": 25.0}
        with tempfile.TemporaryDirectory() as tmp:
            project = build_project("v.mp4", [Word("a", 0.0, 0.2)], info, [])
            path = save_project(project, tmp)
            self.assertEqual(ProjectStore(path).peek()["clips"], 0)

    def test_saving_updated_run_preserves_review_state(self):
        info = {"duration": 46.0, "width": 1280, "height": 720, "fps": 30.0}
        clips = sample_clips()[:1]
        with tempfile.TemporaryDirectory() as tmp:
            project = build_project("video.mp4", [], info, clips)
            path = save_project(project, tmp)
            previous = ProjectStore(path).load()
            previous.clips[0].status = "approved"
            previous.clips[0].notes = ["cek audio"]
            ProjectStore(path).save(previous)

            updated = build_project("video.mp4", [], info, clips)
            save_project(updated, tmp)
            saved = ProjectStore(path).load().clips[0]
            self.assertEqual(saved.id, previous.clips[0].id)
            self.assertEqual(saved.status, "approved")
            self.assertEqual(saved.notes, ["cek audio"])

    def test_selected_candidate_keeps_other_candidates(self):
        info = {"duration": 46.0, "width": 1280, "height": 720, "fps": 30.0}
        clips = [
            {"start": 0.3, "end": 22.9, "title": "klip satu"},
            {"start": 23.0, "end": 45.0, "title": "klip dua"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = save_project(build_project("video.mp4", [], info, clips), tmp)
            previous = ProjectStore(path).load()
            previous.clips[1].status = "approved"
            previous.clips[1].notes = ["pertahankan"]
            previous.extra["hook_ai"] = {
                previous.clips[0].id: {"score": 80, "reasons": ["jelas"]},
            }
            ProjectStore(path).save(previous)

            adjusted = [{"start": 0.3, "end": 20.0, "title": "klip satu"}]
            selected = build_project("video-lokal.mp4", [], info, adjusted)
            save_project(selected, tmp, preserve_unmatched=True)
            saved = ProjectStore(path).load()

            self.assertEqual(len(saved.clips), 2)
            self.assertEqual(saved.clips[0].id, previous.clips[0].id)
            self.assertEqual(saved.clips[1].id, previous.clips[1].id)
            self.assertEqual(saved.clips[1].status, "approved")
            self.assertEqual(saved.clips[1].notes, ["pertahankan"])
            self.assertEqual(
                saved.extra["hook_ai"][previous.clips[0].id]["score"], 80,
            )


if __name__ == "__main__":
    unittest.main()
