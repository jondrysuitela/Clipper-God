"""Layout tiga panel & layar + strip: geometri tidak boleh tumpang tindih."""

from __future__ import annotations

import unittest

from clippergod.core.captions import CaptionStyle
from clippergod.pipeline.layout import (
    LayoutConfig,
    caption_style_for_split,
    screenshare_panels,
    three_panels,
)
from clippergod.pipeline.render import RenderSpec, build_pass1

CFG = LayoutConfig()
USABLE = CFG.out_h - CFG.caption_strip


class TestThree(unittest.TestCase):
    def test_three_faces_make_three_panels(self):
        panels = three_panels([(300, 300), (640, 300), (980, 300)], 1280, 720, CFG)
        self.assertEqual(len(panels), 3)
        self.assertGreaterEqual(sum(p.out_h for p in panels), USABLE - len(panels))
        self.assertTrue(all(not p.fit for p in panels))

    def test_two_faces_fall_back(self):
        self.assertEqual(three_panels([(300, 300), (900, 300)], 1280, 720, CFG), [])


class TestScreenshare(unittest.TestCase):
    def panels(self):
        return screenshare_panels((640, 300), 1280, 720, CFG)

    def test_screen_is_letterboxed_speaker_is_cropped(self):
        screen, strip = self.panels()
        self.assertTrue(screen.fit)
        self.assertEqual((screen.crop_w, screen.crop_h), (1280, 720))
        self.assertFalse(strip.fit)
        self.assertLess(strip.crop_w, 1280)

    def test_heights_cover_usable_area(self):
        screen, strip = self.panels()
        self.assertEqual(screen.out_h + strip.out_h, USABLE)
        self.assertGreater(screen.out_h, strip.out_h)

    def test_caption_goes_to_bottom_strip(self):
        cfg = caption_style_for_split(CaptionStyle(), CFG)
        self.assertEqual(cfg.safe_y0, CFG.out_h - CFG.caption_strip + 12)
        self.assertLessEqual(cfg.safe_y1, CFG.out_h)

    def test_filter_graph_letterboxes_screen_panel(self):
        spec = RenderSpec(src="a.mp4", dst="b.mp4", start=0.0, duration=5.0,
                          layout="split", panels=self.panels())
        cmd = " ".join(build_pass1(spec, "out.mp4", "libx264"))
        self.assertIn("force_original_aspect_ratio=decrease", cmd)
        self.assertIn("pad=1080:1162", cmd)
        self.assertIn("vstack=inputs=2", cmd)


if __name__ == "__main__":
    unittest.main()
