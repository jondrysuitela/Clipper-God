"""Keyword highlight: hanya kata yang mengubah arti, dan tidak merusak karaoke."""

from __future__ import annotations

import unittest

from clippergod.core.captions import CaptionStyle, build_ass, build_cues
from clippergod.core.keywords import keyword_indices, score
from clippergod.core.models import Word


def words(*items: str) -> list[Word]:
    out, t = [], 0.0
    for item in items:
        out.append(Word(item, round(t, 2), round(t + 0.4, 2)))
        t += 0.45
    return out


def ass(*items: str, **style_kw) -> str:
    style = CaptionStyle(**style_kw)
    return build_ass(build_cues(words(*items), style), style)


class TestScoring(unittest.TestCase):
    def test_numbers_and_negation_score_highest(self):
        self.assertEqual(score("2026"), 3)
        self.assertEqual(score("gagal"), 3)
        self.assertEqual(score("paling"), 2)
        self.assertEqual(score("dunia"), 0)

    def test_limit_and_deterministic_order(self):
        picked = keyword_indices(["halo", "gagal", "dunia", "3"], limit=2)
        self.assertEqual(picked, {1, 3})
        self.assertEqual(len(keyword_indices(["halo", "dunia"], limit=2)), 0)


class TestAssOutput(unittest.TestCase):
    def test_keyword_gets_underline(self):
        text = ass("ini", "gagal", "total")
        self.assertIn(r"{\u1}gagal{\u0}", text)

    def test_plain_words_are_untouched(self):
        text = ass("halo", "dunia")
        self.assertNotIn(r"\u1", text)

    def test_can_be_disabled(self):
        text = ass("ini", "gagal", keyword_highlight=False)
        self.assertNotIn(r"\u1", text)

    def test_karaoke_still_present(self):
        text = ass("ini", "gagal")
        self.assertIn(r"\kf", text)
        self.assertIn(r"{\u1}gagal{\u0}", text)


if __name__ == "__main__":
    unittest.main()
