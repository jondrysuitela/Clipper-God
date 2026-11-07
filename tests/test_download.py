"""URL YouTube: dikenali, dibatasi, dan tidak salah menerima skema lain."""

from __future__ import annotations

import unittest

from clippergod.pipeline.download import is_supported_url, is_url


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


if __name__ == "__main__":
    unittest.main()
