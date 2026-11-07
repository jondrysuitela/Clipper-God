"""Param dari file: default, override, dan penolakan kunci asing."""

from __future__ import annotations

import unittest
from pathlib import Path

from clippergod.params import ExportConfig, Params, from_dict, from_file, load_or_default


class TestParams(unittest.TestCase):
    def test_empty_dict_is_all_defaults(self):
        self.assertEqual(from_dict({}), Params())

    def test_override_applies(self):
        params = from_dict({"export": {"bitrate_mbps": 8.5}, "boundary": {"shift_score": 0.5}})
        self.assertEqual(params.export.bitrate_mbps, 8.5)
        self.assertEqual(params.boundary.shift_score, 0.5)
        self.assertEqual(params.export.crf, ExportConfig().crf)

    def test_unknown_section_rejected(self):
        with self.assertRaises(ValueError):
            from_dict({"eksport": {"fps": 30}})

    def test_unknown_key_rejected(self):
        with self.assertRaises(ValueError):
            from_dict({"export": {"bitrate": 10}})

    def test_wrong_type_rejected(self):
        with self.assertRaises(ValueError):
            from_dict({"export": {"bitrate_mbps": "cepat"}})
        with self.assertRaises(ValueError):
            from_dict({"export": {"fps": True}})

    def test_repo_config_matches_defaults(self):
        # config/params.json adalah dokumentasi default; kalau menyimpang, salah satu basi.
        path = Path(__file__).resolve().parents[1] / "config" / "params.json"
        self.assertEqual(from_file(path), Params())

    def test_missing_file_falls_back(self):
        self.assertEqual(load_or_default("tidak-ada.json"), Params())


if __name__ == "__main__":
    unittest.main()
