"""Studio lokal: API proyek, preview klip, dan perubahan status harus persisten."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

from clippergod.core.models import Word
from clippergod.pipeline.bridge import build_project, save_project
from clippergod.pipeline.local_hook_ai import HookAnalysis
from clippergod.project.store import ProjectStore
from clippergod.server import make_server, pick_file


class StudioTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.video = root / "clips" / "01" / "clip.mp4"
        self.video.parent.mkdir(parents=True)
        self.video.write_bytes(b"fake-mp4-bytes")

        project = build_project(
            "sumber.mp4",
            [Word("halo", 0.0, 0.5)],
            {"duration": 30.0, "width": 1280, "height": 720, "fps": 30.0},
            [{"start": 0.0, "end": 20.0, "title": "klip satu", "score": 71.0,
              "video": str(self.video)}],
        )
        self.path = save_project(project, root)
        self.server = make_server(self.path)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_frozen_file_picker_uses_windows_dialog(self):
        result = type("Result", (), {
            "returncode": 0, "stdout": "C:\\Videos\\clip.mp4\r\n", "stderr": "",
        })()
        with patch.object(sys, "frozen", True, create=True), patch(
            "clippergod.server.subprocess.run", return_value=result,
        ) as run:
            self.assertEqual(pick_file(), "C:\\Videos\\clip.mp4")
        self.assertEqual(run.call_args.args[0][0], "powershell.exe")

    def get(self, path: str):
        with urllib.request.urlopen(self.base + path) as response:
            return response.status, response.read()

    def post(self, path: str, payload: dict):
        request = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())

    def get_for_project(self, path: str, project_id: str):
        request = urllib.request.Request(
            self.base + path, headers={"X-ClipperGod-Project": project_id},
        )
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())

    def upload(self, filename: str, payload: bytes, route: str = "/api/upload"):
        request = urllib.request.Request(
            self.base + route + "?filename=" + filename,
            data=payload,
            headers={"Content-Type": "application/octet-stream"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())

    def test_projects_can_be_created_and_remain_isolated(self):
        status, created = self.post("/api/projects", {"name": "Proyek kedua"})
        self.assertEqual(status, 201)
        project_id = created["id"]

        status, empty_project = self.get_for_project("/api/project", project_id)
        self.assertEqual(status, 200)
        self.assertTrue(empty_project["empty"])
        self.assertEqual(empty_project["name"], "Proyek kedua")

        request = urllib.request.Request(
            self.base + "/api/upload?filename=episode.mp4",
            data=b"project-two-video",
            headers={
                "Content-Type": "application/octet-stream",
                "X-ClipperGod-Project": project_id,
            },
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, 200)
            uploaded = json.loads(response.read())
        self.assertEqual(
            Path(uploaded["path"]).parent,
            self.path.parent / "projects" / project_id / "source",
        )

        status, original = self.get("/api/project")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(original)["name"], "sumber")

        _, body = self.get("/api/projects")
        listing = json.loads(body)
        self.assertEqual(len(listing["projects"]), 2)

    def test_cancel_discards_default_data_but_preserves_other_projects(self):
        project_file = self.path
        registry_file = project_file.parent / "projects.json"
        with patch("clippergod.jobs.JobManager.cancel", return_value=True):
            _, result = self.post("/api/jobs/cancel", {"id": "cancel-me"})

        _, body = self.get("/api/projects")
        listing = json.loads(body)
        self.assertTrue(result["project_deleted"])
        self.assertFalse(result["workspace_removed"])
        self.assertEqual(result["replacement_id"], listing["default_id"])
        self.assertFalse(project_file.exists())
        self.assertTrue(registry_file.is_file())

    def test_unknown_project_id_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as response:
            self.get_for_project("/api/project", "a" * 32)
        self.assertEqual(response.exception.code, 404)

    def test_transcript_review_rejects_unknown_asr_model(self):
        request = urllib.request.Request(
            self.base + "/api/transcript/review",
            data=json.dumps({
                "ollama_model": "llama3.2",
                "asr_model": "unknown",
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as response:
            urllib.request.urlopen(request)
        self.assertEqual(response.exception.code, 400)
        payload = json.loads(response.exception.read())
        self.assertIn("model ASR pemeriksa", payload["error"])

    def test_project_endpoint(self):
        status, body = self.get("/api/project")
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(data["name"], "sumber")
        self.assertEqual(len(data["clips"]), 1)
        self.assertTrue(data["out_dir"])

    def test_clip_streams_video(self):
        status, body = self.get("/api/project")
        clip_id = json.loads(body)["clips"][0]["id"]
        status, payload = self.get("/api/clip?id=" + clip_id)
        self.assertEqual(status, 200)
        self.assertEqual(payload, b"fake-mp4-bytes")

    def test_clip_supports_http_byte_ranges(self):
        _, body = self.get("/api/project")
        clip_id = json.loads(body)["clips"][0]["id"]
        request = urllib.request.Request(
            self.base + "/api/clip?id=" + clip_id,
            headers={"Range": "bytes=2-6"},
        )
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Content-Range"], "bytes 2-6/14")
            self.assertEqual(response.read(), b"ke-mp")

    def test_source_streams_local_media_with_byte_ranges(self):
        project = ProjectStore(self.path).load()
        project.media.path = str(self.video)
        ProjectStore(self.path).save(project)
        request = urllib.request.Request(
            self.base + "/api/source",
            headers={"Range": "bytes=0-4"},
        )
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), b"fake-")

    def test_source_preview_uses_downloaded_youtube_video(self):
        project = ProjectStore(self.path).load()
        project.media.path = "https://www.youtube.com/watch?v=example123"
        project.extra.update({
            "source_url": project.media.path,
            "source_id": "example123",
        })
        ProjectStore(self.path).save(project)
        source_dir = self.path.parent / "source"
        source_dir.mkdir()
        downloaded = source_dir / "video-example123.mp4"
        downloaded.write_bytes(b"downloaded-video")

        _, body = self.get("/api/project")
        payload = json.loads(body)
        self.assertTrue(payload["media"]["local_available"])

        status, content = self.get("/api/source")
        self.assertEqual(status, 200)
        self.assertEqual(content, b"downloaded-video")

    def test_source_preview_prefers_workspace_h264_proxy(self):
        project = ProjectStore(self.path).load()
        project.media.path = str(self.video)
        proxy = self.path.parent / "source" / "preview-test.mp4"
        proxy.parent.mkdir()
        proxy.write_bytes(b"browser-compatible-preview")
        project.extra["preview_proxy"] = str(proxy)
        ProjectStore(self.path).save(project)

        status, content = self.get("/api/source")

        self.assertEqual(status, 200)
        self.assertEqual(content, b"browser-compatible-preview")

    def test_local_hook_analysis_is_persisted_without_changing_primary_score(self):
        _, body = self.get("/api/project")
        clip = json.loads(body)["clips"][0]
        with patch(
            "clippergod.pipeline.local_hook_ai.analyze_hook",
            return_value=HookAnalysis(84.0, ("Pertanyaan yang jelas",)),
        ) as analyze:
            status, result = self.post(
                "/api/hooks/analyze",
                {"clip_id": clip["id"], "model": "qwen2.5:3b"},
            )
        self.assertEqual(status, 200)
        self.assertEqual(result["score"], 84.0)
        self.assertEqual(result["model"], "qwen2.5:3b")
        self.assertEqual(analyze.call_args.args[0], "halo")

        saved = ProjectStore(self.path).load()
        self.assertEqual(saved.extra["hook_ai"][clip["id"]]["score"], 84.0)
        self.assertEqual(saved.clips[0].score, clip["score"])

    def test_status_change_persists(self):
        _, body = self.get("/api/project")
        clip_id = json.loads(body)["clips"][0]["id"]
        status, _ = self.post("/api/clips", {"id": clip_id, "status": "approved"})
        self.assertEqual(status, 200)
        self.assertEqual(ProjectStore(self.path).load().clips[0].status, "approved")

    def test_video_upload_saves_source_inside_project(self):
        status, data = self.upload("episode.mp4", b"video-source")
        uploaded = Path(data["path"])
        self.assertEqual(status, 200)
        self.assertEqual(uploaded.parent, self.path.parent / "source")
        self.assertEqual(uploaded.read_bytes(), b"video-source")

    def test_video_upload_accepts_trailing_slash(self):
        status, data = self.upload("episode.mp4", b"video-source", "/api/upload/")
        uploaded = Path(data["path"])
        self.assertEqual(status, 200)
        self.assertEqual(uploaded.read_bytes(), b"video-source")

    def test_upload_rejects_unsupported_extension(self):
        request = urllib.request.Request(
            self.base + "/api/upload?filename=episode.txt",
            data=b"not a video",
            headers={"Content-Type": "application/octet-stream"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as response:
            urllib.request.urlopen(request)
        self.assertEqual(response.exception.code, 400)

    def test_unknown_clip_and_status_are_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as unknown:
            self.get("/api/clip?id=tidak-ada")
        self.assertEqual(unknown.exception.code, 404)

        _, body = self.get("/api/project")
        clip_id = json.loads(body)["clips"][0]["id"]
        with self.assertRaises(urllib.error.HTTPError) as bad:
            self.post("/api/clips", {"id": clip_id, "status": "dihapus"})
        self.assertEqual(bad.exception.code, 400)

    def test_non_json_api_request_reports_expected_content_type(self):
        request = urllib.request.Request(
            self.base + "/api/clips",
            data=b"binary-body",
            headers={"Content-Type": "application/octet-stream"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as response:
            urllib.request.urlopen(request)
        self.assertEqual(response.exception.code, 400)
        payload = json.loads(response.exception.read())
        self.assertIn("Content-Type: application/octet-stream", payload["error"])

    def test_home_serves_studio_page(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn(b"ClipperGod", body)
        self.assertIn(b'id="projectSelect"', body)
        self.assertIn(b'id="createProjectBtn"', body)

    def test_health_endpoint(self):
        status, body = self.get("/api/health")
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertIn("faster_whisper", data)
        self.assertIn("encoders", data)

    def test_caption_fonts_endpoint_lists_installed_windows_families(self):
        status, body = self.get("/api/fonts")
        fonts = json.loads(body)["fonts"]
        self.assertEqual(status, 200)
        self.assertIsInstance(fonts, list)
        self.assertTrue(all(isinstance(font, str) and font for font in fonts))

    def test_studio_script_is_served(self):
        status, body = self.get("/studio.js")
        self.assertEqual(status, 200)
        self.assertIn(b"/api/project", body)
        self.assertIn(b"X-ClipperGod-Project", body)


if __name__ == "__main__":
    unittest.main()
