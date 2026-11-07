"""Pembuat kandidat klip dari transkrip.

Pendekatan: potong per kalimat (bukan per detik acak), lalu gabungkan kalimat
sampai durasi target tercapai. Hasilnya selalu mulai & berhenti di batas
kalimat — bukan di tengah ide.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.boundaries import BoundaryConfig, is_greeting_opening, score_boundary
from ..core.captions import CaptionStyle, build_cues, caption_report
from ..core.models import ClipCandidate, Word
from ..core.scoring import ClipSignals, evaluate, hook_token_hits

DURATION_TARGETS: dict[str, tuple[float, float]] = {
    "reach": (21.0, 34.0),
    "watch": (35.0, 60.0),
    "story": (60.0, 90.0),
}


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    target: str = "watch"
    min_duration: float | None = None
    max_duration: float | None = None
    max_candidates: int = 40
    overlap_ratio: float = 0.5
    long_pause: float = 0.55


def sentence_spans(words: list[Word], cfg: CandidateConfig | None = None) -> list[tuple[int, int]]:
    """Indeks awal/akhir (eksklusif) tiap kalimat."""
    cfg = cfg or CandidateConfig()
    if not words:
        return []

    spans: list[tuple[int, int]] = []
    start = 0
    for i, w in enumerate(words):
        ends_sentence = w.clean.endswith((".", "?", "!", "…"))
        long_gap = (i + 1 < len(words)) and (words[i + 1].start - w.end >= cfg.long_pause)
        if ends_sentence or long_gap or i == len(words) - 1:
            if i + 1 > start:
                spans.append((start, i + 1))
            start = i + 1
    return spans


def _title_from(words: list[Word], limit: int = 7) -> str:
    text = " ".join(w.clean for w in words[:limit]).strip(" .,?!")
    return text[:70] or "Klip tanpa judul"


def _overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    shortest = min(a[1] - a[0], b[1] - b[0])
    return inter / shortest if shortest > 0 else 0.0


def generate(
    words: list[Word],
    cfg: CandidateConfig | None = None,
    boundary_cfg: BoundaryConfig | None = None,
) -> list[ClipCandidate]:
    cfg = cfg or CandidateConfig()
    boundary_cfg = boundary_cfg or BoundaryConfig()

    lo, hi = DURATION_TARGETS.get(cfg.target, DURATION_TARGETS["watch"])
    lo = cfg.min_duration or lo
    hi = cfg.max_duration or hi

    spans = sentence_spans(words, cfg)
    raw: list[ClipCandidate] = []

    for i in range(len(spans)):
        for j in range(i, len(spans)):
            start_idx, end_idx = spans[i][0], spans[j][1]
            chunk = words[start_idx:end_idx]
            if not chunk:
                continue
            start, end = chunk[0].start, chunk[-1].end
            duration = end - start
            if duration < lo:
                continue
            if duration > hi:
                break

            start_b = score_boundary(words, start_idx, "start", boundary_cfg)
            end_b = score_boundary(words, end_idx, "end", boundary_cfg)
            if start_b.score < 0.45 or end_b.score < 0.45:
                continue

            hits = hook_token_hits(" ".join(w.clean for w in chunk[:12]))

            # VPS parsial: hanya komponen yang benar-benar bisa diukur dari transkrip
            # (H dan C). R/A/L/P butuh analisis video/audio dan baru diisi setelah render.
            style = CaptionStyle()
            report = caption_report(build_cues(chunk, style), style)
            vps = evaluate(
                ClipSignals(
                    duration=duration,
                    speech_onset=round(chunk[0].start - start, 3),
                    hook_text=" ".join(w.clean for w in chunk[:12]),
                    greeting_opening=is_greeting_opening(words, start),
                    caption_max_cps=float(report["max_cps"]),
                    caption_violations=len(report["violations"]),
                ),
                measured={"H", "C"},
            )
            score = vps.score

            reasons = [f"durasi {duration:.0f}s"]
            if hits:
                reasons.append("hook: " + ", ".join(hits))
            reasons.append(f"batas {start_b.score:.2f}/{end_b.score:.2f}")
            reasons.append(
                f"VPS {vps.score:.0f} (H {vps.components['H']:.0f}, C {vps.components['C']:.0f}); "
                f"belum diukur: {', '.join(vps.unmeasured)}"
            )

            raw.append(ClipCandidate(
                start=round(start, 3),
                end=round(end, 3),
                title=_title_from(chunk),
                score=round(min(100.0, score), 1),
                reasons=reasons,
                vps=vps.to_dict(),
            ))
            break  # perpanjang lagi akan melewati batas atas

    raw.sort(key=lambda c: (-(c.score or 0), c.start))

    kept: list[ClipCandidate] = []
    for cand in raw:
        if any(_overlap((cand.start, cand.end), (k.start, k.end)) > cfg.overlap_ratio for k in kept):
            continue
        kept.append(cand)
        if len(kept) >= cfg.max_candidates:
            break

    return kept


def summarize(cands: list[ClipCandidate]) -> dict:
    if not cands:
        return {"count": 0}
    scores = [c.score or 0 for c in cands]
    return {
        "count": len(cands),
        "best": max(scores),
        "median": sorted(scores)[len(scores) // 2],
        "avg_duration": round(sum(c.duration for c in cands) / len(cands), 1),
    }
