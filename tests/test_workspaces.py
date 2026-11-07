import tempfile
import unittest
from pathlib import Path

from clippergod.project.workspaces import WorkspaceRegistry


class WorkspaceRegistryTest(unittest.TestCase):
    def test_projects_keep_separate_job_managers_and_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = WorkspaceRegistry(Path(directory))
            original = registry.get()
            second = registry.create("Proyek kedua")

            self.assertIsNot(registry.jobs(original), registry.jobs(second))
            self.assertIs(registry.jobs(original), registry.jobs(original))

            restored = WorkspaceRegistry(Path(directory))
            self.assertEqual(restored.get(original.id), original)
            self.assertEqual(restored.get(second.id), second)

    def test_discard_default_project_preserves_registry_and_other_projects(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = WorkspaceRegistry(Path(directory))
            default = registry.get()
            other = registry.create("Proyek lain")
            reserved = other.root / "keep.txt"
            reserved.write_text("data proyek lain", encoding="utf-8")
            (default.root / "project.cgproj").write_text("proyek lama", encoding="utf-8")
            (default.root / "source").mkdir()
            (default.root / "source" / "video.mp4").write_bytes(b"media")

            replacement_id = registry.discard_after_cancel(default)

            self.assertEqual(replacement_id, default.id)
            self.assertTrue(registry.registry_path.is_file())
            self.assertTrue(reserved.is_file())
            self.assertFalse((default.root / "project.cgproj").exists())
            self.assertFalse((default.root / "source").exists())

    def test_discard_isolated_project_removes_workspace_and_data(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = WorkspaceRegistry(Path(directory))
            default = registry.get()
            workspace = registry.create("Dibatalkan")
            (workspace.root / "project.cgproj").write_text("data", encoding="utf-8")

            replacement_id = registry.discard_after_cancel(workspace)

            self.assertEqual(replacement_id, default.id)
            self.assertFalse(workspace.root.exists())
            with self.assertRaises(KeyError):
                registry.get(workspace.id)


if __name__ == "__main__":
    unittest.main()
