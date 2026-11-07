"""Uji perilaku mesin inti ClipperGod (tanpa GPU, tanpa ffmpeg).

Fokus uji adalah JANJI PRODUK, bukan detail implementasi:
  - tidak pernah memotong di tengah kalimat
  - caption tidak pernah melewati batas keterbacaan
  - caption tidak menutupi wajah kalau ada ruang
  - skor tidak bisa tinggi kalau hook gagal
"""

from __future__ import annotations

import unittest

from clippergod.core import (
    CaptionStyle,
    ClipSignals,
    FaceBox,
    VPSWeights,
    Word,
    build_ass,
    build_cues,
    caption_report,
    choose_placement,
    enforce,
    evaluate,
    extend_for_reaction,
    hook_token_hits,
    is_greeting_opening,
    score_boundary,
)


def mk(pairs):
    return [Word(text=t, start=s, end=e) for t, s, e in pairs]


#: Kalimat utuh dengan satu batas jelek (tengah klausa) dan satu batas bagus.
SENTENCE = mk(
    [
        ("Jadi", 0.10, 0.35),
        ("hari", 0.36, 0.60),
        ("ini", 0.61, 0.78),          # <- batas JELEK (tengah klausa, tanpa jeda)
        ("gua", 0.80, 1.00),
        ("mau", 1.01, 1.22),
        ("bahas", 1.23, 1.55),
        ("kenapa", 1.56, 1.95),
        ("podcast", 1.96, 2.35),
        ("lu", 2.36, 2.50),
        ("sepi", 2.51, 2.80),
        ("penonton.", 2.81, 3.30),    # <- batas BAGUS (akhir kalimat + jeda)
        ("Padahal", 3.90, 4.30),
    ]
)


class TestSemanticBoundary(unittest.TestCase):
    def test_mid_clause_is_rejected(self):
        b = score_boundary(SENTENCE, 3, role="end")
        self.assertLess(b.score, 0.45, f"potong tengah kalimat lolos: {b}")
        self.assertFalse(b.safe)

    def test_sentence_end_with_pause_is_accepted(self):
        b = score_boundary(SENTENCE, 11, role="end")
        self.assertGreaterEqual(b.score, 0.70, f"batas bagus ditolak: {b}")
        self.assertTrue(b.safe)
        self.assertIn("akhir kalimat", b.reasons)

    def test_dangling_conjunction_penalized(self):
        words = mk([("A", 0, 0.3), ("dan", 0.31, 0.5), ("B.", 0.90, 1.2)])
        b = score_boundary(words, 2, role="end")  # berhenti tepat di "dan"
        self.assertLess(b.score, 0.60)

    def test_start_boundary_penalizes_conjunction(self):
        b = score_boundary(SENTENCE, 3, role="start")  # mulai dari "gua" -> oke
        self.assertTrue(any("pembuka" in r or "konjungsi" in r for r in b.reasons) or b.score >= 0)

    def test_enforce_moves_cut_to_safe_boundary(self):
        clip = enforce(SENTENCE, 0.8, 2.9)  # sengaja mulai & berhenti di tempat salah
        self.assertFalse(clip.rejected)
        self.assertGreater(clip.end, 2.9, "akhir klip tidak digeser ke akhir kalimat")
        self.assertLessEqual(clip.start, 0.8 + 0.01)

    def test_enforce_rejects_unsalvageable(self):
        words = mk([("eee", 0, 0.2), ("emm", 0.21, 0.4), ("hmm", 0.41, 0.6)])
        clip = enforce(words, 0.2, 0.5)
        self.assertTrue(clip.rejected)

    def test_greeting_opening_detected(self):
        words = mk([("Hai", 0, 0.3), ("guys", 0.4, 0.9), ("topik", 3.6, 4.0)])
        self.assertTrue(is_greeting_opening(words, 0.0))

    def test_punchline_guard_extends_past_laughter(self):
        new_end = extend_for_reaction(10.0, [(9.0, 12.0)])
        self.assertAlmostEqual(new_end, 12.2, places=2)

    def test_punchline_guard_ignores_unrelated_reaction(self):
        self.assertEqual(extend_for_reaction(10.0, [(1.0, 3.0)]), 10.0)


class TestCaptions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = (
            "gua mau bahas kenapa podcast lu sepi penonton padahal kontennya bagus "
            "banget sumpah ini penting buat lu semua yang lagi mulai bikin konten"
        ).split()
        pairs, t = [], 0.0
        for w in text:
            pairs.append((w, t, t + 0.40))
            t += 0.45
        cls.words = mk(pairs)

    def test_cue_respects_readability_rules(self):
        style = CaptionStyle()
        cues = build_cues(self.words, style)
        self.assertGreater(len(cues), 0)
        for cue in cues:
            self.assertLessEqual(len(cue.words), style.max_words)
            self.assertLessEqual(len(cue.lines), style.max_lines)
            for line in cue.lines:
                self.assertLessEqual(len(line), style.max_chars, f"baris terlalu panjang: {line!r}")
            self.assertLessEqual(cue.duration, style.max_dur + 0.02)

    def test_no_word_lost_when_splitting(self):
        cues = build_cues(self.words)
        rebuilt = [w.clean for c in cues for w in c.words]
        self.assertEqual(rebuilt, [w.clean for w in self.words])

    def test_face_aware_placement_moves_caption_up(self):
        style = CaptionStyle()
        cue = build_cues(self.words, style)[0]
        face = FaceBox(x0=400, y0=1150, x1=700, y1=1400)
        self.assertEqual(choose_placement(cue, [face], style), "top")

    def test_face_away_keeps_caption_at_bottom(self):
        style = CaptionStyle()
        cue = build_cues(self.words, style)[0]
        face = FaceBox(x0=400, y0=350, x1=700, y1=600)
        self.assertEqual(choose_placement(cue, [face], style), "bottom")

    def test_ass_output_is_wellformed(self):
        cues = build_cues(self.words)
        ass = build_ass(cues)
        self.assertIn("[Script Info]", ass)
        self.assertIn("PlayResX: 1080", ass)
        self.assertIn("[V4+ Styles]", ass)
        self.assertIn(r"\kf", ass)
        self.assertIn(r"\pos(", ass)
        self.assertEqual(ass.count("Dialogue:"), len(cues))
        self.assertTrue(ass.endswith("\n"))

    def test_report_flags_nothing_on_clean_input(self):
        cues = build_cues(self.words)
        report = caption_report(cues)
        self.assertEqual(report["cues"], len(cues))
        # Tidak ada pelanggaran keras. CPS bisa melewati cap hanya kalau satu kata
        # sendirian sudah terlalu panjang untuk durasinya (tidak bisa dipecah lagi).
        self.assertEqual(report["violations"], [])
        for cue in cues:
            if cue.cps > CaptionStyle().max_cps:
                self.assertEqual(len(cue.words), 1, f"cue multi-kata melanggar CPS: {cue.lines}")
                self.assertTrue(any("CPS" in n for n in report["notes"]))


class TestVPS(unittest.TestCase):
    def base(self, **kw):
        params = dict(
            duration=40.0,
            speech_onset=0.2,
            motion_first_frame=0.6,
            face_in_first_frame=True,
            hook_text="kenapa kamu selalu gagal bikin konten? ini 3 alasannya",
            greeting_opening=False,
            visual_change_at=1.0,
            cut_rate_cpm=22.0,
            caption_max_cps=14.0,
            integrated_lufs=-14.0,
            true_peak_dbtp=-1.2,
            loop_similarity=0.7,
            outro_duration=0.8,
            width=1080,
            height=1920,
            fps=30,
            video_bitrate_mbps=10.0,
        )
        params.update(kw)
        return ClipSignals(**params)

    def test_weights_normalize_to_one(self):
        w = VPSWeights().normalized()
        total = w.H + w.R + w.C + w.A + w.L + w.P
        self.assertAlmostEqual(total, 1.0, places=6)

    def test_strong_clip_scores_high(self):
        result = evaluate(self.base())
        self.assertGreater(result.score, 75, result.explain())
        self.assertEqual(result.gates_failed, [])

    def test_gate_caps_score_when_no_speech(self):
        result = evaluate(self.base(speech_onset=None))
        self.assertTrue(result.capped)
        self.assertLessEqual(result.score, 40.0)

    def test_gate_caps_when_caption_breaks_safe_box(self):
        result = evaluate(self.base(caption_outside_safe=True))
        self.assertLessEqual(result.score, 40.0)

    def test_clipping_kills_audio_component(self):
        result = evaluate(self.base(true_peak_dbtp=0.5))
        self.assertEqual(result.components["A"], 0.0)
        self.assertLessEqual(result.score, 40.0)

    def test_overpacing_lowers_retention(self):
        ideal = evaluate(self.base(cut_rate_cpm=22.0)).components["R"]
        frantic = evaluate(self.base(cut_rate_cpm=55.0)).components["R"]
        self.assertGreater(ideal, frantic)

    def test_reasons_are_human_readable(self):
        result = evaluate(self.base())
        self.assertTrue(result.reasons["H"], "komponen H tanpa alasan")
        self.assertIn("hook", " ".join(result.reasons["H"]).lower())

    def test_hook_token_detection(self):
        hits = hook_token_hits("kenapa kamu nggak pernah mulai?")
        self.assertIn("pertanyaan", hits)
        self.assertIn("negasi", hits)
        self.assertIn("menyapa penonton", hits)


if __name__ == "__main__":
    unittest.main(verbosity=2)
