"""Test layout engine: geometri panel split, safe box caption, dan filter FFmpeg."""

from __future__ import annotations

import unittest

from clippergod.core.captions import CaptionStyle
from clippergod.pipeline.layout import (
    LayoutConfig,
    caption_style_for_split,
    panel_geometry,
    split_panels,
)
from clippergod.pipeline.render import RenderSpec, build_pass1


class GeometryTest(unittest.TestCase):
    def test_two_panels_plus_strip_fill_canvas(self):
        cfg = LayoutConfig(mode="split", caption_strip=260)
        height, crop_w, crop_h = panel_geometry(1280, 720, cfg, 2)
        self.assertEqual(height * 2 + 260, 1920)
        # aspek panel output harus sama dengan aspek crop sumber
        self.assertAlmostEqual(crop_w / crop_h, 1080 / height, places=2)
        self.assertLess(crop_h, 720, "panel harus di-zoom, bukan setinggi frame")

    def test_crop_never_wider_than_source(self):
        cfg = LayoutConfig(mode="split", caption_strip=1200, panel_zoom=1.0)  # ekstrem
        _height, crop_w, _crop_h = panel_geometry(1280, 720, cfg, 2)
        self.assertLessEqual(crop_w, 1280)

    def test_panels_do_not_include_each_other(self):
        """Dua wajah berjarak 520 px: crop tiap panel harus lebih sempit dari itu."""
        cfg = LayoutConfig(mode="split")
        panels = split_panels([(380.0, 360.0), (900.0, 360.0)], 1280, 720, cfg)
        self.assertEqual(len(panels), 2)
        self.assertLess(panels[0].x + panels[0].crop_w, panels[1].x,
                        "panel kiri dan kanan tidak boleh tumpang tindih")

    def test_panel_x_clamped_inside_frame(self):
        cfg = LayoutConfig(mode="split")
        panels = split_panels([(60.0, 360.0), (1240.0, 360.0)], 1280, 720, cfg)
        self.assertGreaterEqual(panels[0].x, 0.0)
        self.assertLessEqual(panels[1].x + panels[1].crop_w, 1280.0 + 0.5)

    def test_panel_y_follows_face(self):
        cfg = LayoutConfig(mode="split")
        low = split_panels([(380.0, 650.0), (900.0, 650.0)], 1280, 720, cfg)
        high = split_panels([(380.0, 150.0), (900.0, 150.0)], 1280, 720, cfg)
        self.assertGreater(low[0].y, high[0].y)

    def test_single_center_gives_no_panels(self):
        self.assertEqual(split_panels([(600.0, 300.0)], 1280, 720, LayoutConfig(mode="split")), [])

    def test_strip_too_tall_is_rejected(self):
        with self.assertRaises(ValueError):
            panel_geometry(1280, 720, LayoutConfig(mode="split", caption_strip=1900), 2)


class CaptionStyleTest(unittest.TestCase):
    def test_safe_box_moves_into_bottom_strip(self):
        style = CaptionStyle()
        adjusted = caption_style_for_split(style, LayoutConfig(mode="split", caption_strip=260))
        self.assertGreater(adjusted.safe_y0, 1920 - 260)
        self.assertLessEqual(adjusted.safe_y1, 1920)
        self.assertLessEqual(adjusted.font_size, style.font_size)
        # garis aman tidak boleh tumpang tindih dengan panel (panel berakhir di 1660)
        self.assertGreater(adjusted.safe_y0, 1660)


class SplitFilterTest(unittest.TestCase):
    def _spec(self) -> RenderSpec:
        panels = split_panels([(380.0, 360.0), (900.0, 360.0)], 1280, 720,
                              LayoutConfig(mode="split"))
        return RenderSpec(
            src="a.mp4", dst="b.mp4", start=1.0, duration=10.0,
            crop_w=panels[0].crop_w, crop_h=panels[0].crop_h,
            layout="split", panels=panels,
        )

    def test_pass1_stacks_panels_and_pads(self):
        cmd = build_pass1(self._spec(), "out.mp4")
        graph = cmd[cmd.index("-filter_complex") + 1]
        self.assertEqual(graph.count("crop=w="), 2)
        self.assertIn("vstack=inputs=2", graph)
        self.assertIn("pad=1080:1920", graph)
        self.assertIn("-map", cmd)
        self.assertIn("[vout]", cmd)

    def test_pass1_falls_back_to_single_crop_without_panels(self):
        spec = self._spec()
        spec.panels = []
        cmd = build_pass1(spec, "out.mp4")
        self.assertIn("-vf", cmd)
        self.assertNotIn("-filter_complex", cmd)


if __name__ == "__main__":
    unittest.main()
