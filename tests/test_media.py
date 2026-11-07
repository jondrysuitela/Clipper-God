"""Import media: parsing & geometri proxy, tanpa memanggil ffmpeg."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from clippergod.pipeline.media import (
    create_preview_proxy,
    import_media,
    needs_proxy,
    parse_rotation,
    parse_size,
    proxy_args,
    target_size,
)

STDERR = """Input #0, mov,mp4,m4a, from 'clip.mp4':
  Metadata:
    displaymatrix: rotation of -90.00 degrees
  Stream #0:0(und): Video: h264 (High), yuv420p, 1920x1080, 30 fps
"""


class TestParsing(unittest.TestCase):
    def test_rotation(self):
        self.assertEqual(parse_rotation(STDERR), -90)
        self.assertIsNone(parse_rotation("tidak ada metadata"))

    def test_size(self):
        self.assertEqual(parse_size(STDERR), (1920, 1080))
        self.assertIsNone(parse_size("Video: png"))


class TestProxyGeometry(unittest.TestCase):
    def test_target_keeps_aspect_and_even_width(self):
        self.assertEqual(target_size(1920, 1080, 540), (960, 540))
        self.assertEqual(target_size(1280, 720, 540), (960, 540))
        self.assertEqual(target_size(1080, 1920, 540), (304, 540))  # vertikal -> 304 (genap)

    def test_odd_source_rounds_to_even(self):
        width, _height = target_size(1366, 768, 540)
        self.assertEqual(width % 2, 0)

    def test_small_source_needs_no_proxy(self):
        self.assertFalse(needs_proxy(640, 360, 540))
        self.assertTrue(needs_proxy(1920, 1080, 540))

    def test_proxy_args_per_encoder(self):
        self.assertIn("veryfast", proxy_args("libx264", 540))
        self.assertIn("p1", proxy_args("h264_nvenc", 540))
        self.assertIn("2M", proxy_args("libopenh264", 540))


class TestBrowserPreviewProxy(unittest.TestCase):
    def test_preview_proxy_is_h264_playable_and_preserves_aspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.avi"
            writer = cv2.VideoWriter(
                str(source), cv2.VideoWriter_fourcc(*"MJPG"), 10, (320, 240),
            )
            for index in range(10):
                writer.write(np.full((240, 320, 3), index * 10, dtype=np.uint8))
            writer.release()

            proxy = create_preview_proxy(source, root / "studio")

            capture = cv2.VideoCapture(str(proxy))
            self.assertTrue(capture.isOpened())
            ok, frame = capture.read()
            capture.release()
            self.assertTrue(ok)
            self.assertEqual(frame.shape[0], 240)
            self.assertEqual(frame.shape[1], 320)
            self.assertEqual(proxy.parent, root / "studio" / "source")


class TestImportWithoutProjectWrite(unittest.TestCase):
    def test_import_result_has_project_path_without_creating_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.mp4"
            out = root / "studio"
            source.write_bytes(b"video")
            info = {"duration": 12.0, "width": 640, "height": 360, "fps": 30.0}

            with (
                patch("clippergod.pipeline.media.probe_video", return_value=info),
                patch("clippergod.pipeline.media.detect_rotation", return_value=None),
                patch("clippergod.pipeline.media.ffprobe_info", return_value=None),
            ):
                result = import_media(source, out, write_project=False)

            self.assertEqual(result.project, str(out / "project.cgproj"))
            self.assertFalse((out / "project.cgproj").exists())
            self.assertTrue((out / "media.json").is_file())


if __name__ == "__main__":
    unittest.main()
