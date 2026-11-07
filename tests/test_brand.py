"""Test brand kit: parsing/validasi profil dan filter overlay di pass 2."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from clippergod.pipeline.brand import from_dict, from_file, merge_caption
from clippergod.pipeline.caption_config import from_dict as caption_from_dict
from clippergod.pipeline.render import LogoSpec, RenderSpec, build_pass2, needs_pass2


def _logo(path: Path, size: tuple[int, int] = (200, 200)) -> Path:
    Image.new("RGBA", size, (255, 0, 255, 255)).save(path)
    return path


class LogoSpecTest(unittest.TestCase):
    def test_corner_positions(self):
        logo = LogoSpec(path="x.png", margin=30)
        self.assertEqual(logo.overlay_xy(), ("main_w-overlay_w-30", "main_h-overlay_h-30"))
        self.assertEqual(LogoSpec(path="x.png", position="tl", margin=12).overlay_xy(),
                         ("12", "12"))
        self.assertEqual(LogoSpec(path="x.png", position="tr", margin=8).overlay_xy(),
                         ("main_w-overlay_w-8", "8"))
        self.assertEqual(LogoSpec(path="x.png", position="bl", margin=8).overlay_xy(),
                         ("8", "main_h-overlay_h-8"))

    def test_custom_position_uses_explicit_pixels(self):
        self.assertEqual(LogoSpec(path="x.png", position="custom", x=111, y=222).overlay_xy(),
                         ("111", "222"))

    def test_width_from_ratio_or_pixels(self):
        self.assertEqual(LogoSpec(path="x.png", width_ratio=0.2).pixel_width(1080), 216)
        self.assertEqual(LogoSpec(path="x.png", width=150, width_ratio=0.2).pixel_width(1080), 150)


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.logo = _logo(self.root / "logo.png")

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_profile(self):
        profile = from_dict({
            "name": "Kanal Rio",
            "caption": {"font": "Inter Black", "size": 72, "highlight": "#FF7A45"},
            "logo": {"path": "logo.png", "position": "tr", "width_ratio": 0.2,
                     "margin": 24, "opacity": 0.8},
        }, base_dir=self.root)
        self.assertEqual(profile.name, "Kanal Rio")
        self.assertEqual(profile.caption.font, "Inter Black")
        self.assertEqual(profile.logo.position, "tr")
        self.assertEqual(profile.logo.margin, 24)
        self.assertAlmostEqual(profile.logo.opacity, 0.8)
        self.assertTrue(Path(profile.logo.path).is_file())

    def test_relative_logo_is_resolved_against_profile_folder(self):
        path = self.root / "brand.json"
        path.write_text(json.dumps({"logo": {"path": "logo.png"}}), encoding="utf-8")
        profile = from_file(path)
        self.assertEqual(Path(profile.logo.path), (self.root / "logo.png").resolve())

    def test_missing_logo_file_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            from_dict({"logo": {"path": "tidak-ada.png"}}, base_dir=self.root)
        self.assertIn("tidak ditemukan", str(ctx.exception))

    def test_unknown_keys_are_rejected(self):
        with self.assertRaises(ValueError):
            from_dict({"logo": {"path": "logo.png", "rotasi": 30}}, base_dir=self.root)
        with self.assertRaises(ValueError):
            from_dict({"logo": {"path": "logo.png"}, "warna": "#fff"}, base_dir=self.root)

    def test_invalid_logo_values_are_rejected(self):
        for bad in ({"width_ratio": 0.9}, {"opacity": 1.5}, {"position": "tengah"},
                    {"margin": -5}):
            payload = {"path": "logo.png", **bad}
            with self.assertRaises(ValueError, msg=str(bad)):
                from_dict({"logo": payload}, base_dir=self.root)

    def test_merge_caption_lets_explicit_config_win(self):
        profile = from_dict({"caption": {"size": 72}, "logo": {"path": "logo.png"}},
                            base_dir=self.root)
        override = caption_from_dict({"size": 60})
        self.assertEqual(merge_caption(profile, override).size, 60)
        self.assertEqual(merge_caption(profile, None).size, 72)


class Pass2FilterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.logo_path = _logo(self.root / "logo.png")

    def tearDown(self):
        self.tmp.cleanup()

    def _spec(self, logo: bool, ass: bool = True) -> RenderSpec:
        return RenderSpec(
            src="a.mp4", dst="b.mp4", start=5.0, duration=4.0,
            crop_w=405, crop_h=720,
            ass_path="cap.ass" if ass else None,
            logo=LogoSpec(path=str(self.logo_path), position="tr", width=150,
                          margin=24, opacity=0.9) if logo else None,
            audio=True,
        )

    def test_logo_is_scaled_and_overlaid_after_caption(self):
        cmd = build_pass2(self._spec(logo=True), "cropped.mp4", "out.mp4")
        graph = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("cap.ass", graph)               # caption lebih dulu
        self.assertLess(graph.index("ass="), graph.index("overlay="))
        self.assertIn("scale=150:-1", graph)
        self.assertIn("colorchannelmixer=aa=0.90", graph)
        self.assertIn("overlay=x=main_w-overlay_w-24:y=24", graph)
        self.assertIn("[vout]", cmd)
        self.assertIn("1:a:0?", cmd)
        self.assertEqual(cmd.count("-i"), 3)          # cropped, src, logo

    def test_caption_only_still_uses_filter_complex(self):
        cmd = build_pass2(self._spec(logo=False), "cropped.mp4", "out.mp4")
        self.assertIn("-filter_complex", cmd)
        self.assertIn("[vcap]", cmd)
        self.assertNotIn("overlay=", " ".join(cmd))

    def test_no_caption_no_logo_maps_video_directly(self):
        cmd = build_pass2(self._spec(logo=False, ass=False), "cropped.mp4", "out.mp4")
        self.assertNotIn("-filter_complex", cmd)
        self.assertIn("0:v:0", cmd)
        self.assertEqual(cmd.count("-i"), 2)

    def test_logo_only_requires_pass2(self):
        spec = self._spec(logo=True, ass=False)
        spec.audio = False
        self.assertTrue(needs_pass2(spec), "logo saja tetap butuh pass 2")

    def test_plain_crop_needs_only_one_pass(self):
        spec = self._spec(logo=False, ass=False)
        spec.audio = False
        self.assertFalse(needs_pass2(spec))

    def test_logo_without_audio_uses_input_one(self):
        spec = self._spec(logo=True)
        spec.audio = False
        cmd = build_pass2(spec, "cropped.mp4", "out.mp4")
        graph = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("[1:v]", graph)


if __name__ == "__main__":
    unittest.main()
