"""Test konfigurasi caption: parsing, validasi, dan efeknya ke file ASS."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from clippergod.core.captions import (
    CaptionStyle,
    build_ass,
    build_cues,
    place_cues,
)
from clippergod.core.models import Word
from clippergod.pipeline.caption_config import (
    CaptionConfig,
    build_style,
    force_position,
    from_dict,
    from_file,
)


def _cue():
    words = [Word(text="halo", start=0.0, end=0.4), Word(text="dunia", start=0.45, end=0.9)]
    return build_cues(words)


class ParseTest(unittest.TestCase):
    def test_full_config(self):
        cfg = from_dict({
            "font": "Inter Black", "size": 72, "color": "#FFFFFF", "highlight": "#22D3EE",
            "outline": 4, "shadow": 2, "outline_color": "#101010",
            "position": "bottom", "uppercase": True, "karaoke": False,
            "max_words": 4, "max_lines": 2, "max_chars": 28, "max_cps": 16,
            "min_duration": 0.9, "max_duration": 2.0,
            "safe_area": {"x0": 100, "x1": 980, "y0": 800, "y1": 1700},
            "position_x": 42, "position_y": 58,
        })
        self.assertEqual(cfg.font, "Inter Black")
        self.assertEqual(cfg.size, 72)
        self.assertEqual(cfg.position, "bottom")
        self.assertTrue(cfg.uppercase)
        self.assertFalse(cfg.karaoke)
        self.assertEqual(cfg.safe_area, (100, 980, 800, 1700))
        self.assertEqual((cfg.position_x, cfg.position_y), (42, 58))

    def test_unknown_key_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            from_dict({"font_size": 72})
        self.assertIn("font_size", str(ctx.exception))

    def test_bad_position_is_rejected(self):
        with self.assertRaises(ValueError):
            from_dict({"position": "tengah"})

    def test_caption_position_must_stay_inside_safe_bounds(self):
        for config in ({"position_x": 9}, {"position_y": 91}):
            with self.assertRaisesRegex(ValueError, "area aman"):
                from_dict(config)

    def test_caption_coordinates_must_be_set_together(self):
        with self.assertRaisesRegex(ValueError, "harus diatur bersamaan"):
            build_style(from_dict({"position_x": 45}))

    def test_safe_area_needs_exactly_four_edges(self):
        with self.assertRaises(ValueError):
            from_dict({"safe_area": {"x0": 0, "x1": 1080, "y0": 0}})

    def test_loads_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "caption.json"
            path.write_text(json.dumps({"size": 60}), encoding="utf-8")
            self.assertEqual(from_file(path).size, 60)

    def test_invalid_json_has_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "caption.json"
            path.write_text("{bukan json", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                from_file(path)
            self.assertIn("tidak valid", str(ctx.exception))


class BuildStyleTest(unittest.TestCase):
    def test_applies_font_colors_and_safe_area(self):
        cfg = from_dict({
            "font": "Inter Black", "size": 84, "highlight": "#22D3EE",
            "outline": 4, "shadow": 1,
            "safe_area": {"x0": 100, "x1": 980, "y0": 800, "y1": 1700},
        })
        style, warnings = build_style(cfg)
        self.assertEqual(style.font_name, "Inter Black")
        self.assertEqual(style.font_size, 84)
        self.assertEqual(style.secondary, "&H00EED322")  # BGR
        self.assertEqual(style.outline, 4)
        self.assertEqual((style.safe_x0, style.safe_x1, style.safe_y0, style.safe_y1),
                         (100, 980, 800, 1700))
        self.assertEqual(warnings, [])

    def test_small_font_needs_explicit_permission(self):
        with self.assertRaises(ValueError) as ctx:
            build_style(from_dict({"size": 40}))
        self.assertIn("allow_small_font", str(ctx.exception))

        style, warnings = build_style(from_dict({"size": 40, "allow_small_font": True}))
        self.assertEqual(style.font_size, 40)
        self.assertTrue(any("batas" in w for w in warnings))

    def test_extreme_cps_is_rejected(self):
        with self.assertRaises(ValueError):
            build_style(from_dict({"max_cps": 45}))

    def test_high_cps_warns_but_passes(self):
        _style, warnings = build_style(from_dict({"max_cps": 26}))
        self.assertTrue(any("CPS" in w for w in warnings))

    def test_line_and_word_limits_validated(self):
        for bad in ({"max_lines": 5}, {"max_words": 12}, {"max_chars": 80}):
            with self.assertRaises(ValueError):
                build_style(from_dict(bad))

    def test_safe_area_must_fit_canvas(self):
        with self.assertRaises(ValueError):
            build_style(from_dict({"safe_area": {"x0": 0, "x1": 1200, "y0": 0, "y1": 1900}}))


class AssOutputTest(unittest.TestCase):
    def _style(self, **cfg) -> CaptionStyle:
        style, _ = build_style(from_dict(cfg))
        return style

    def test_uppercase_applies_to_dialogue_text(self):
        import re
        style = self._style(uppercase=True)
        ass = build_ass(_cue(), style)
        for line in ass.splitlines():
            if line.startswith("Dialogue:"):
                text = line.split(",", 9)[-1]
                body = re.sub(r"\{[^}]*\}", "", text)  # buang tag \an/\pos/\kf
                letters = [ch for ch in body if ch.isalpha()]
                self.assertTrue(letters)
                self.assertTrue(all(ch.isupper() for ch in letters), body)

    def test_karaoke_off_removes_kf_tags(self):
        ass = build_ass(_cue(), self._style(karaoke=False))
        self.assertNotIn(r"\kf", ass)
        self.assertIn("halo dunia", ass)

    def test_karaoke_on_keeps_kf_tags(self):
        ass = build_ass(_cue(), self._style(karaoke=True))
        self.assertIn(r"\kf", ass)

    def test_boxed_style_uses_ass_box_border(self):
        ass = build_ass(_cue(), self._style(box=True))
        style_line = next(line for line in ass.splitlines() if line.startswith("Style: Cap,"))
        self.assertIn(",3,6,3,2,", style_line)
        self.assertIn("&H30000000", style_line)

    def test_forced_position_moves_caption(self):
        style = CaptionStyle()
        cues = _cue()
        place_cues(cues, style, {}, force="top")
        self.assertTrue(all(c.placement == "top" for c in cues))
        ass = build_ass(cues, style)
        self.assertIn(r"\an8", ass)
        self.assertIn(rf"\pos(540,{style.safe_y0})", ass)

    def test_custom_caption_position_is_written_to_ass(self):
        style, _warnings = build_style(from_dict({
            "position_x": 40,
            "position_y": 55,
        }))

        ass = build_ass(_cue(), style)

        self.assertIn(r"\an5", ass)
        self.assertIn(r"\pos(432,1056)", ass)

    def test_force_position_auto_means_none(self):
        self.assertIsNone(force_position(CaptionConfig(position="auto")))
        self.assertEqual(force_position(CaptionConfig(position="bottom")), "bottom")


class CpsExtensionTest(unittest.TestCase):
    def test_long_word_gets_longer_cue_until_cps_complies(self):
        words = [Word(text="extraordinary", start=0.0, end=0.4),
                 Word(text="oke", start=1.5, end=1.9)]
        cues = build_cues(words, CaptionStyle(max_cps=10.0, min_dur=0.3, max_dur=1.8))
        first = cues[0]
        self.assertEqual(first.text, "extraordinary")
        self.assertLessEqual(first.cps, 10.0 + 1e-6, "CPS harus turun setelah diperpanjang")
        self.assertLessEqual(first.end, 1.5 + 1e-9, "tidak boleh menabrak kata berikutnya")

    def test_extension_never_exceeds_max_duration(self):
        words = [Word(text="extraordinary", start=0.0, end=0.4),
                 Word(text="oke", start=9.0, end=9.4)]
        cues = build_cues(words, CaptionStyle(max_cps=5.0, min_dur=0.3, max_dur=1.8))
        self.assertLessEqual(cues[0].duration, 1.8 + 1e-9)


class SchemaTest(unittest.TestCase):
    def test_known_keys_cover_dataclass_fields(self):
        from clippergod.pipeline.caption_config import KNOWN_KEYS
        names = set(CaptionConfig.__dataclass_fields__)
        self.assertEqual(KNOWN_KEYS, names)


if __name__ == "__main__":
    unittest.main()
