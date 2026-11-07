"""URL YouTube: dikenali, dibatasi, dan tidak salah menerima skema lain."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from clippergod.pipeline.download import is_supported_url, is_url, probe_url


class TestUrlDetection(unittest.TestCase):
    def test_http_urls(self):
        self.assertTrue(is_url("https://youtube.com/watch?v=abc"))
        self.assertTrue(is_url("http://youtu.be/abc"))

    def test_not_urls(self):
        self.assertFalse(is_url(r"D:\rekaman\podcast.mp4"))
        self.assertFalse(is_url(""))
        self.assertFalse(is_url("javascript:alert(1)"))
        self.assertFalse(is_url("ftp://youtube.com/x"))

    def test_only_youtube_supported(self):
        self.assertTrue(is_supported_url("https://www.youtube.com/watch?v=abc"))
        self.assertTrue(is_supported_url("https://youtu.be/abc"))
        self.assertTrue(is_supported_url("https://m.youtube.com/watch?v=abc"))
        self.assertFalse(is_supported_url("https://vimeo.com/123"))
        self.assertFalse(is_supported_url("https://youtube.com.evil.test/watch?v=abc"))

    def test_host_is_case_insensitive(self):
        self.assertTrue(is_supported_url("https://WWW.YouTube.COM/watch?v=abc"))

    def test_probe_returns_bounded_description_and_valid_chapters(self):
        captured = {}

        class FakeYoutubeDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def extract_info(self, _url, download):
                captured["skip_download"] = self.options["skip_download"]
                captured["download"] = download
                return {
                    "id": "abc123",
                    "title": "Podcast",
                    "description": "Episode description",
                    "chapters": [
                        {"start_time": 10, "end_time": 20, "title": "Hook"},
                        {"start_time": -1, "end_time": 5, "title": "Invalid"},
                    ],
                    "webpage_url": "https://youtu.be/abc123",
                }

        with patch.dict("sys.modules", {"yt_dlp": SimpleNamespace(YoutubeDL=FakeYoutubeDL)}):
            result = probe_url("https://youtu.be/abc123")

        self.assertTrue(captured["skip_download"])
        self.assertFalse(captured["download"])
        self.assertEqual(result["description"], "Episode description")
        self.assertEqual(result["chapters"], [{
            "start_time": 10.0, "end_time": 20.0, "title": "Hook",
        }])


if __name__ == "__main__":
    unittest.main()
