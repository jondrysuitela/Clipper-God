"""Uji fondasi proyek: simpan/muat, autosave, pemulihan, dan undo/redo.

Fokus uji adalah janji ke user: "kerja lu nggak akan hilang" dan
"setiap perubahan bisa dibatalkan".
"""

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path

from clippergod.core.models import Word
from clippergod.project import (
    AddClip,
    Clip,
    Composite,
    History,
    MoveBoundary,
    Project,
    ProjectStore,
    RemoveClip,
    UpdateClip,
    fingerprint_file,
)


def make_project(tmp: Path, name: str = "Ngobrolin Karier #42") -> Project:
    media = tmp / "sumber.mp4"
    media.write_bytes(b"video palsu untuk uji" * 100)
    p = Project.new(name, media, duration=4320.0, width=1920, height=1080, fps=30)
    p.words = [
        Word(text="kenapa", start=0.10, end=0.45, speaker="rio"),
        Word(text="podcast", start=0.46, end=0.95, speaker="rio"),
        Word(text="sepi", start=0.96, end=1.30, speaker="rio"),
        Word(text="penonton", start=1.31, end=1.90, speaker="dinda"),
    ]
    p.speakers = {"rio": {"name": "Rio", "color": "#7FA8D9"},
                  "dinda": {"name": "Dinda", "color": "#D9A07F"}}
    return p


class TestSchema(unittest.TestCase):
    def test_new_project_has_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_project(Path(d))
            self.assertEqual(p.schema_version, 1)
            self.assertEqual(p.settings["target_platform"], "tiktok")
            self.assertTrue(p.media.exists)
            self.assertTrue(p.media.fingerprint)

    def test_default_settings_are_not_shared_between_projects(self):
        with tempfile.TemporaryDirectory() as d:
            a = make_project(Path(d), "A")
            b = make_project(Path(d), "B")
            a.settings["export"]["bitrate_mbps"] = 20
            self.assertEqual(b.settings["export"]["bitrate_mbps"], 10)

    def test_clip_rejects_inverted_bounds(self):
        with self.assertRaises(ValueError):
            Clip(start=10.0, end=5.0)

    def test_clip_rejects_unknown_status(self):
        with self.assertRaises(ValueError):
            Clip(start=1.0, end=2.0, status="entah")

    def test_duplicate_clip_id_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_project(Path(d))
            c = Clip(start=1.0, end=2.0, title="a")
            p.add_clip(c)
            with self.assertRaises(ValueError):
                p.add_clip(c)

    def test_future_schema_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_project(Path(d))
            data = p.to_dict()
            data["schema_version"] = 99
            with self.assertRaises(ValueError):
                Project.from_dict(data)

    def test_relink_flags_fingerprint_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_project(Path(d))
            original_bytes = Path(p.media.path).read_bytes()

            bad = Path(d) / "lain.mp4"
            bad.write_bytes(b"isi yang benar-benar berbeda")
            self.assertFalse(p.relink(bad))
            self.assertTrue(p.media.path.endswith("lain.mp4"))

            # Sidik jari asli dipertahankan, jadi salinan identik tetap dikenali.
            good = Path(d) / "salinan.mp4"
            good.write_bytes(original_bytes)
            self.assertTrue(p.relink(good))


class TestStore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.store = ProjectStore(self.tmp / "proyek.cgproj")
        self.project = make_project(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_roundtrip_preserves_everything(self):
        self.project.add_clip(Clip(start=862.0, end=898.4, title="Hook", score=92.0))
        self.store.save(self.project)

        loaded = self.store.load()
        self.assertEqual(loaded.name, self.project.name)
        self.assertEqual(len(loaded.words), 4)
        self.assertEqual(loaded.words[0].text, "kenapa")
        self.assertEqual(loaded.words[3].speaker, "dinda")
        self.assertEqual(len(loaded.clips), 1)
        self.assertAlmostEqual(loaded.clips[0].score, 92.0)
        self.assertEqual(loaded.settings["target_platform"], "tiktok")

    def test_save_is_atomic_and_leaves_no_temp(self):
        self.store.save(self.project)
        leftovers = list(self.tmp.glob("*.tmp"))
        self.assertEqual(leftovers, [])
        self.assertTrue(self.store.exists())

    def test_concurrent_store_instances_keep_project_valid(self):
        barrier = threading.Barrier(4)
        errors: list[Exception] = []

        def save_repeatedly(index: int) -> None:
            store = ProjectStore(self.store.path)
            project = make_project(self.tmp, f"Writer {index}")
            try:
                barrier.wait(timeout=5)
                for _ in range(5):
                    store.save(project)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=save_repeatedly, args=(i,)) for i in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertFalse(any(thread.is_alive() for thread in threads), "writer thread macet")
        self.assertEqual(errors, [])
        self.assertRegex(self.store.load().name, r"^Writer [0-3]$")

    def test_suffix_is_forced(self):
        s = ProjectStore(self.tmp / "tanpa-ekstensi")
        self.assertEqual(s.path.suffix, ".cgproj")

    def test_autosave_skipped_when_nothing_changed(self):
        self.project.add_clip(Clip(start=1.0, end=9.0))
        first = self.store.autosave(self.project)
        second = self.store.autosave(self.project)
        self.assertFalse(first.skipped)
        self.assertTrue(second.skipped)

    def test_autosave_written_after_change(self):
        self.project.add_clip(Clip(start=1.0, end=9.0))
        self.store.autosave(self.project)
        self.project.add_clip(Clip(start=20.0, end=30.0))
        result = self.store.autosave(self.project)
        self.assertFalse(result.skipped)
        self.assertTrue(self.store.has_autosave())

    def test_save_clears_autosave(self):
        self.project.add_clip(Clip(start=1.0, end=9.0))
        self.store.autosave(self.project)
        self.assertTrue(self.store.has_autosave())
        self.store.save(self.project)
        self.assertFalse(self.store.has_autosave())

    def test_recover_returns_none_without_autosave(self):
        self.store.save(self.project)
        self.assertIsNone(self.store.recover())

    def test_recover_returns_newer_autosave(self):
        self.project.add_clip(Clip(start=1.0, end=9.0))
        self.store.autosave(self.project)

        # Pastikan autosave benar-benar lebih baru dari file proyek.
        os.utime(self.store.autosave_path, (2_000_000_000, 2_000_000_000))
        if self.store.exists():
            os.utime(self.store.path, (1_000_000_000, 1_000_000_000))

        recovered = self.store.recover()
        self.assertIsNotNone(recovered)
        self.assertEqual(len(recovered.clips), 1)
        self.assertTrue(recovered.extra.get("recovered_from_autosave"))

    def test_recover_ignores_stale_autosave(self):
        self.project.add_clip(Clip(start=1.0, end=9.0))
        self.store.save(self.project)
        self.store.autosave(self.project, force=True)
        os.utime(self.store.autosave_path, (1_000_000_000, 1_000_000_000))
        os.utime(self.store.path, (2_000_000_000, 2_000_000_000))
        self.assertIsNone(self.store.recover())

    def test_peek_does_not_need_full_load(self):
        self.project.add_clip(Clip(start=1.0, end=9.0))
        self.store.save(self.project)
        meta = self.store.peek()
        self.assertEqual(meta["clips"], 1)
        self.assertAlmostEqual(meta["duration"], 4320.0)

    def test_load_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            ProjectStore(self.tmp / "hantu.cgproj").load()


class TestHistory(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.project = make_project(self.tmp)
        self.now = [0.0]
        self.history = History(self.project, clock=lambda: self.now[0])

    def tearDown(self):
        self._tmp.cleanup()

    def test_undo_add_clip(self):
        clip = Clip(start=1.0, end=9.0)
        self.history.execute(AddClip(clip))
        self.assertEqual(len(self.project.clips), 1)

        self.history.undo()
        self.assertEqual(len(self.project.clips), 0)
        self.assertTrue(self.history.can_redo)

    def test_undo_remove_restores_position(self):
        a = self.project.add_clip(Clip(start=1.0, end=2.0, title="a"))
        b = self.project.add_clip(Clip(start=3.0, end=4.0, title="b"))
        c = self.project.add_clip(Clip(start=5.0, end=6.0, title="c"))

        self.history.execute(RemoveClip(b.id))
        self.assertEqual([x.title for x in self.project.clips], ["a", "c"])

        self.history.undo()
        self.assertEqual([x.title for x in self.project.clips], ["a", "b", "c"])

    def test_redo_reapplies(self):
        self.history.execute(AddClip(Clip(start=1.0, end=2.0)))
        self.history.undo()
        self.history.redo()
        self.assertEqual(len(self.project.clips), 1)
        self.assertFalse(self.history.can_redo)

    def test_new_command_clears_redo(self):
        self.history.execute(AddClip(Clip(start=1.0, end=2.0)))
        self.history.undo()
        self.assertTrue(self.history.can_redo)
        self.history.execute(AddClip(Clip(start=3.0, end=4.0)))
        self.assertFalse(self.history.can_redo)

    def test_coalesces_rapid_boundary_drags(self):
        clip = self.project.add_clip(Clip(start=10.0, end=40.0))
        original = clip.start

        for i, v in enumerate([9.0, 8.0, 7.0]):
            self.now[0] = 0.1 * (i + 1)
            self.history.execute(MoveBoundary(clip.id, "start", v))

        self.assertEqual(self.history.depth[0], 1, "geseran beruntun harus jadi satu langkah")
        self.assertAlmostEqual(self.project.clip(clip.id).start, 7.0)

        self.history.undo()
        self.assertAlmostEqual(self.project.clip(clip.id).start, original)

    def test_slow_drags_are_separate_steps(self):
        clip = self.project.add_clip(Clip(start=10.0, end=40.0))
        self.now[0] = 0.0
        self.history.execute(MoveBoundary(clip.id, "start", 9.0))
        self.now[0] = 2.0
        self.history.execute(MoveBoundary(clip.id, "start", 8.0))
        self.assertEqual(self.history.depth[0], 2)

    def test_moving_both_edges_does_not_merge(self):
        clip = self.project.add_clip(Clip(start=10.0, end=40.0))
        self.history.execute(MoveBoundary(clip.id, "start", 9.0))
        self.now[0] = 0.1
        self.history.execute(MoveBoundary(clip.id, "end", 39.0))
        self.assertEqual(self.history.depth[0], 2)

    def test_boundary_cannot_invert_clip(self):
        clip = self.project.add_clip(Clip(start=10.0, end=12.0))
        with self.assertRaises(ValueError):
            self.history.execute(MoveBoundary(clip.id, "start", 20.0))
        self.assertAlmostEqual(self.project.clip(clip.id).start, 10.0)

    def test_composite_undoes_as_one_step(self):
        a = self.project.add_clip(Clip(start=1.0, end=2.0, status="candidate"))
        b = self.project.add_clip(Clip(start=3.0, end=4.0, status="candidate"))

        bulk = Composite(
            [UpdateClip(a.id, "status", "approved"),
             UpdateClip(b.id, "status", "approved")],
            label="Setujui semua",
        )
        self.history.execute(bulk)

        self.assertEqual(self.project.clip(a.id).status, "approved")
        self.assertEqual(self.project.clip(b.id).status, "approved")
        self.assertEqual(self.history.depth[0], 1)

        self.history.undo()
        self.assertEqual(self.project.clip(a.id).status, "candidate")
        self.assertEqual(self.project.clip(b.id).status, "candidate")

    def test_history_respects_limit(self):
        history = History(self.project, limit=3, clock=lambda: self.now[0])
        for i in range(5):
            self.now[0] = float(i)
            history.execute(AddClip(Clip(start=float(i), end=float(i) + 0.5)))
        self.assertEqual(history.depth[0], 3)

    def test_failed_update_does_not_crash_history(self):
        with self.assertRaises(KeyError):
            self.history.execute(UpdateClip("tidak-ada", "title", "x"))
        self.assertEqual(self.history.depth[0], 0)

    def test_version_increments_for_ui(self):
        before = self.history.version
        self.history.execute(AddClip(Clip(start=1.0, end=2.0)))
        self.assertGreater(self.history.version, before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
