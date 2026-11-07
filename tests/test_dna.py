"""Clip DNA: duplikat harus tertangkap, parafrase bukan urusannya."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clippergod.core.models import Word
from clippergod.pipeline.dna import DnaIndex, clip_dna, jaccard, shingles


def make_words(text: str, step: float = 0.4) -> list[Word]:
    out, t = [], 0.0
    for token in text.split():
        out.append(Word(token, round(t, 2), round(t + step, 2)))
        t += step + 0.05
    return out


A = "kenapa podcast kamu sepi penonton padahal isinya bagus sekali dan konsisten"
B = "kenapa podcast kamu sepi penonton padahal isinya bagus sekali dan konsisten setiap minggu"
C = "cara membuat thumbnail yang menarik perhatian di beranda youtube"


class TestShingles(unittest.TestCase):
    def test_identical_text_is_identical(self):
        self.assertEqual(jaccard(shingles(A), shingles(A)), 1.0)

    def test_shifted_cut_still_similar(self):
        score = jaccard(shingles(A), shingles(B))
        self.assertGreater(score, 0.6, score)

    def test_unrelated_text_is_low(self):
        self.assertLess(jaccard(shingles(A), shingles(C)), 0.2)

    def test_empty_text_is_safe(self):
        self.assertEqual(shingles(""), frozenset())
        self.assertEqual(jaccard(frozenset(), shingles(A)), 0.0)


class TestIndex(unittest.TestCase):
    def test_finds_duplicate_across_episodes_and_persists(self):
        words = make_words(A)
        dna = clip_dna(words, 0.0, words[-1].end)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dna" / "index.json"
            index = DnaIndex()
            index.add(dna, title="klip satu", episode="ep01", start=0.0, end=words[-1].end)
            index.save(path)

            reloaded = DnaIndex.load(path)
            other = clip_dna(make_words(B), 0.0, 10.0)
            matches = reloaded.find(other)
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["episode"], "ep01")
            self.assertGreaterEqual(matches[0]["similarity"], 0.6)

    def test_no_false_positive(self):
        index = DnaIndex()
        index.add(clip_dna(make_words(A), 0.0, 10.0), title="a", episode="ep01",
                  start=0.0, end=10.0)
        self.assertEqual(index.find(clip_dna(make_words(C), 0.0, 10.0)), [])

    def test_broken_index_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.json"
            path.write_text("{bukan json", encoding="utf-8")
            self.assertEqual(DnaIndex.load(path).entries, [])


if __name__ == "__main__":
    unittest.main()
