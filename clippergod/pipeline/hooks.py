"""Hook A/B Lab: tiga pembuka berbeda untuk body yang sama.

Yang diubah hanya titik mulai (selalu di batas kalimat); akhir klip tetap, jadi
body-nya sama. Varian diskor dengan komponen H yang sama seperti kandidat, supaya
perbandingannya apel-ke-apel — bukan tebakan "yang ini kayaknya lebih nendang".

Belum ada penulisan ulang audio (memindahkan kalimat hook ke depan); itu tahap
berikutnya. Yang disediakan di sini: pilihan pembuka + alasannya.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.boundaries import BoundaryConfig, is_greeting_opening, score_boundary
from ..core.models import Word
from ..core.scoring import ClipSignals, evaluate
from .candidates import CandidateConfig, sentence_spans

MIN_BODY = 8.0


@dataclass(frozen=True, slots=True)
class HookVariant:
    label: str
    start: float
    end: float
    text: str
    score: float
    reasons: tuple[str, ...] = ()

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "text": self.text,
            "score": self.score,
            "reasons": list(self.reasons),
        }


def _sentences(words: list[Word], start: float, end: float) -> list[tuple[float, int, str]]:
    """(waktu_mulai, indeks_global, teks) tiap kalimat di dalam klip."""
    clip = [w for w in words if w.end > start and w.start < end]
    if not clip:
        return []
    first_global = next((i for i, w in enumerate(words) if w.start >= clip[0].start), 0)
    out: list[tuple[float, int, str]] = []
    for a, b in sentence_spans(clip, CandidateConfig()):
        text = " ".join(w.clean for w in clip[a:b]).strip()
        if text:
            out.append((clip[a].start, first_global + a, text))
    return out


def _score(words: list[Word], start: float, end: float, text: str) -> float:
    result = evaluate(
        ClipSignals(
            duration=end - start,
            speech_onset=0.0,
            hook_text=text,
            greeting_opening=is_greeting_opening(words, start),
        ),
        measured={"H"},
    )
    return result.components["H"]


def plan_hooks(
    words: list[Word],
    start: float,
    end: float,
    boundary: BoundaryConfig | None = None,
    limit: int = 3,
) -> list[HookVariant]:
    """Varian A (asli), B (hook terkuat), C (runner-up), semua di batas kalimat."""
    cfg = boundary or BoundaryConfig()
    sentences = _sentences(words, start, end)
    if not sentences:
        return []
    original_start = sentences[0][0]

    scored: list[tuple[float, float, int, str, bool]] = []
    for sentence_start, index, text in sentences:
        if end - sentence_start < MIN_BODY:
            continue
        is_original = abs(sentence_start - original_start) < 0.01
        # Pembuka asli selalu masuk: klip ini sudah lolos enforce(), dan varian A
        # memang harus menunjukkan apa adanya. Penyaring batas hanya untuk alternatif.
        if not is_original and score_boundary(words, index, "start", cfg).score < cfg.shift_score:
            continue
        scored.append((_score(words, sentence_start, end, text), sentence_start, index, text, is_original))
    if not scored:
        return []

    scored.sort(key=lambda item: item[1])            # A = kalimat pertama
    original = scored[0]
    alternatives = sorted((item for item in scored if not item[4]),
                          key=lambda item: (-item[0], item[1]))
    chosen = [original]
    for item in alternatives:
        if len(chosen) >= limit:
            break
        if all(abs(item[1] - c[1]) > 0.01 for c in chosen):
            chosen.append(item)

    labels = ["A", "B", "C", "D"]
    variants: list[HookVariant] = []
    for label, (score, sentence_start, _index, text, is_original) in zip(labels, chosen):
        reasons = [f"H {score:.0f}", "pembuka asli" if is_original else "pembuka alternatif"]
        variants.append(HookVariant(
            label=label, start=round(sentence_start, 3), end=round(end, 3),
            text=text[:80], score=round(score, 1), reasons=tuple(reasons),
        ))
    return variants
