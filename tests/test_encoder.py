"""Encoder & bitrate: target harus eksplisit, x264 tidak boleh diam-diam jadi default."""

from __future__ import annotations

import unittest
from unittest import mock

from clippergod.pipeline import render as R


class TestVideoArgs(unittest.TestCase):
    def spec(self, **kw):
        return R.RenderSpec(src="a.mp4", dst="b.mp4", start=0.0, duration=5.0, **kw)

    def test_x264_uses_bitrate_not_crf(self):
        args = R.video_args(self.spec(), "libx264")
        self.assertIn("-b:v", args)
        self.assertIn("10M", args)
        self.assertIn("12M", args)          # maxrate
        self.assertNotIn("-crf", args)

    def test_nvenc_gets_its_own_rate_control(self):
        args = R.video_args(self.spec(), "h264_nvenc")
        self.assertIn("-rc", args)
        self.assertIn("-preset", args)

    def test_intermediate_can_ask_for_higher_bitrate(self):
        args = R.video_args(self.spec(), "libx264", 20.0)
        self.assertIn("20M", args)


class TestChooseEncoder(unittest.TestCase):
    def test_prefers_hardware_then_lgpl(self):
        with mock.patch.object(R, "available_encoders",
                               return_value=frozenset({"h264_nvenc", "libopenh264", "libx264"})), \
             mock.patch.object(R, "encoder_works", return_value=True):
            self.assertEqual(R.choose_encoder()[0], "h264_nvenc")

    def test_falls_back_when_gpu_absent(self):
        with mock.patch.object(R, "available_encoders",
                               return_value=frozenset({"h264_nvenc", "libopenh264"})), \
             mock.patch.object(R, "encoder_works", side_effect=lambda n: n != "h264_nvenc"):
            self.assertEqual(R.choose_encoder(), ("libopenh264", "LGPL"))

    def test_strict_license_refuses_x264(self):
        with mock.patch.object(R, "available_encoders", return_value=frozenset({"libx264"})), \
             mock.patch.object(R, "encoder_works", return_value=True), \
             mock.patch.dict("os.environ", {"CLIPPERGOD_STRICT_LICENSE": "1"}):
            with self.assertRaises(R.RenderError):
                R.choose_encoder()

    def test_gpl_reported_when_allowed(self):
        with mock.patch.object(R, "available_encoders", return_value=frozenset({"libx264"})), \
             mock.patch.object(R, "encoder_works", return_value=True), \
             mock.patch.dict("os.environ", {"CLIPPERGOD_ALLOW_GPL": "1"}):
            self.assertEqual(R.choose_encoder(), ("libx264", "GPL"))


if __name__ == "__main__":
    unittest.main()
