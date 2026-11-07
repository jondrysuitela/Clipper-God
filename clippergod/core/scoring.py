"""Viral Potential Score (VPS) — skor 0-100 yang bisa dijelaskan.

Aturan desain yang tidak boleh dilanggar:
  1. Skor = POTENSI, bukan probabilitas. Jangan pernah tampilkan sebagai persen.
  2. Setiap komponen wajib punya alasan tekstual. Angka tanpa alasan = black box,
     dan black box adalah keluhan utama user terhadap kompetitor.
  3. Hard gate bisa menahan skor di 40 walau komponen lain sempurna.
  4. Bobot disimpan di config, bukan hard-code — target kalibrasi ρ 0.25-0.40.

Formula awal (hipotesis, riset 03 §12.1):
    VPS = 0.30*H + 0.20*R + 0.15*C + 0.15*A + 0.10*L + 0.10*P
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ------------------------------------------------------------------ bobot


@dataclass(frozen=True, slots=True)
class VPSWeights:
    H: float = 0.30  # hook
    R: float = 0.20  # retensi & pacing
    C: float = 0.15  # caption
    A: float = 0.15  # audio
    L: float = 0.10  # loop & ending
    P: float = 0.10  # platform

    def normalized(self) -> "VPSWeights":
        total = self.H + self.R + self.C + self.A + self.L + self.P
        if total <= 0:
            return VPSWeights()
        return VPSWeights(
            H=self.H / total, R=self.R / total, C=self.C / total,
            A=self.A / total, L=self.L / total, P=self.P / total,
        )


# ------------------------------------------------------------------ sinyal


@dataclass(slots=True)
class ClipSignals:
    """Semua sinyal yang dibutuhkan untuk menilai satu klip."""

    duration: float

    # H
    speech_onset: float | None = None      # detik dari awal klip ke kata pertama
    motion_first_frame: float | None = None  # 0..1, optical flow awal; None = belum diukur
    face_in_first_frame: bool | None = None  # None = belum diukur
    hook_text: str = ""
    greeting_opening: bool = False
    visual_change_at: float | None = None  # detik perubahan visual pertama

    # R
    cut_rate_cpm: float = 0.0
    speech_gaps_over_06: int = 0
    long_static_shots: int = 0

    # C
    caption_max_cps: float = 0.0
    caption_outside_safe: bool = False
    caption_violations: int = 0

    # A
    integrated_lufs: float = -14.0
    true_peak_dbtp: float = -1.0

    # L
    loop_similarity: float = 0.0           # SSIM frame akhir vs awal
    outro_duration: float = 0.0

    # P
    width: int = 1080
    height: int = 1920
    fps: int = 30
    video_bitrate_mbps: float = 10.0


# ------------------------------------------------------------ hook tokens

NEGATIONS = ("jangan", "bukan", "salah", "berhenti", "gagal", "nggak", "tidak", "stop")
CURIOSITY = ("rahasia", "ternyata", "kenapa", "gimana", "bagaimana", "apa", "siapa")
ADDRESSING = ("kamu", "lu", "lo", "anda", "kalian")


def hook_token_hits(text: str, first_n_words: int = 12) -> list[str]:
    """Cari penanda hook di N kata pertama. Return daftar penanda yang kena."""
    words = text.split()[:first_n_words]
    low = " ".join(words).lower()
    hits: list[str] = []

    if "?" in low:
        hits.append("pertanyaan")
    if re.search(r"\d", low):
        hits.append("angka")
    if any(neg in low.split() for neg in NEGATIONS):
        hits.append("negasi")
    if any(cur in low.split() for cur in CURIOSITY):
        hits.append("penasaran")
    if any(addr in low.split() for addr in ADDRESSING):
        hits.append("menyapa penonton")
    return hits


# ------------------------------------------------------------ komponen


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def score_hook(s: ClipSignals) -> tuple[float, list[str]]:
    reasons: list[str] = []

    # 20 — speech onset
    if s.speech_onset is None:
        onset = 0.0
        reasons.append("tidak ada ucapan di awal")
    elif s.speech_onset <= 0.30:
        onset = 1.0
        reasons.append(f"ucapan mulai {s.speech_onset:.2f}s")
    else:
        onset = _clamp(1.0 - (s.speech_onset - 0.30) / 1.2)
        reasons.append(f"ucapan telat {s.speech_onset:.2f}s")

    parts: list[tuple[float, float]] = [(20.0, onset)]

    # 15 — gerakan di frame pertama. None = belum dianalisis: jangan dihukum,
    # bobotnya dikeluarkan lalu skala dinormalkan ulang.
    if s.motion_first_frame is not None:
        motion = _clamp(s.motion_first_frame)
        parts.append((15.0, motion))
        if motion > 0.3:
            reasons.append("ada gerakan di frame awal")

    # 10 — wajah
    if s.face_in_first_frame is not None:
        face = 1.0 if s.face_in_first_frame else 0.0
        parts.append((10.0, face))
        if face:
            reasons.append("wajah terlihat")

    # 25 — hook token
    hits = hook_token_hits(s.hook_text)
    token = _clamp(len(hits) / 2.0)
    parts.append((25.0, token))
    if hits:
        reasons.append("hook: " + ", ".join(hits))
    else:
        reasons.append("tidak ada penanda hook")

    # 15 — bukan sapaan
    greeting = 0.0 if s.greeting_opening else 1.0
    parts.append((15.0, greeting))
    if s.greeting_opening:
        reasons.append("dibuka dengan sapaan")

    # 15 — perubahan visual cepat
    if s.visual_change_at is not None:
        visual = 1.0 if s.visual_change_at <= 1.5 else _clamp(1.0 - (s.visual_change_at - 1.5) / 2.0)
        parts.append((15.0, visual))

    if s.motion_first_frame is None or s.face_in_first_frame is None or s.visual_change_at is None:
        reasons.append("gerakan/wajah/visual belum diukur")

    total = sum(w for w, _v in parts)
    value = (sum(w * v for w, v in parts) / total * 100.0) if total else 0.0
    return _clamp(value), reasons


def score_retention(s: ClipSignals) -> tuple[float, list[str]]:
    reasons: list[str] = []
    cpm = s.cut_rate_cpm

    if 15 <= cpm <= 30:
        base = 100.0
        reasons.append(f"pacing ideal ({cpm:.0f} cut/menit)")
    elif 30 < cpm <= 40:
        base = 100 - (cpm - 30) * 4
        reasons.append(f"pacing agak cepat ({cpm:.0f}/menit)")
    elif cpm > 40:
        base = max(0.0, 60 - (cpm - 40) * 3)
        reasons.append(f"pacing terlalu cepat ({cpm:.0f}/menit)")
    elif 10 <= cpm < 15:
        base = 70 + (cpm - 10) * 6
        reasons.append(f"pacing lambat ({cpm:.0f}/menit)")
    else:
        base = max(0.0, cpm * 7)
        reasons.append(f"hampir tanpa cut ({cpm:.0f}/menit)")

    gap_penalty = min(30.0, s.speech_gaps_over_06 * 10)
    if gap_penalty:
        reasons.append(f"{s.speech_gaps_over_06} jeda mati panjang")

    static_penalty = min(30.0, s.long_static_shots * 15)
    if static_penalty:
        reasons.append(f"{s.long_static_shots} shot statis >6s")

    return _clamp(base - gap_penalty - static_penalty), reasons


def score_caption(s: ClipSignals) -> tuple[float, list[str]]:
    reasons: list[str] = []
    value = 100.0

    if s.caption_violations == 0:
        reasons.append("caption patuh aturan")
    else:
        value -= min(60.0, s.caption_violations * 10)
        reasons.append(f"{s.caption_violations} pelanggaran caption")

    if s.caption_max_cps > 18:
        over = (s.caption_max_cps - 18) * 6
        value -= over
        reasons.append(f"CPS {s.caption_max_cps:.1f} terlalu cepat")

    if s.caption_outside_safe:
        reasons.append("caption keluar safe box")

    return _clamp(value), reasons


def score_audio(s: ClipSignals) -> tuple[float, list[str]]:
    reasons: list[str] = []
    lufs, tp = s.integrated_lufs, s.true_peak_dbtp

    if tp > 0:
        reasons.append("audio clipping")
        return 0.0, reasons

    value = 100.0
    if -15 <= lufs <= -13:
        reasons.append(f"loudness pas ({lufs:.1f} LUFS)")
    else:
        dist = -15 - lufs if lufs < -15 else lufs + 13
        value -= dist * 10
        reasons.append(f"loudness {lufs:.1f} LUFS (target -14)")

    if tp > -1:
        value -= 20
        reasons.append(f"true peak {tp:.1f} dBTP")

    return _clamp(value), reasons


def score_loop(s: ClipSignals) -> tuple[float, list[str]]:
    reasons: list[str] = []
    value = _clamp(s.loop_similarity / 0.60 * 100) if s.loop_similarity < 0.60 else 100.0
    if s.loop_similarity > 0.60:
        reasons.append(f"loop mulus (SSIM {s.loop_similarity:.2f})")
    else:
        reasons.append(f"loop kasar (SSIM {s.loop_similarity:.2f})")

    if s.outro_duration > 1.5:
        value -= min(30.0, (s.outro_duration - 1.5) * 10)
        reasons.append(f"outro {s.outro_duration:.1f}s kepanjangan")

    return _clamp(value), reasons


def score_platform(s: ClipSignals) -> tuple[float, list[str]]:
    reasons: list[str] = []
    value = 100.0

    if (s.width, s.height) != (1080, 1920):
        value -= 30
        reasons.append(f"resolusi {s.width}x{s.height}")
    if s.fps < 30:
        value -= 25
        reasons.append(f"{s.fps} fps")
    if s.video_bitrate_mbps < 8:
        value -= 35
        reasons.append(f"bitrate {s.video_bitrate_mbps:.1f} Mbps")
    if value == 100.0:
        reasons.append("1080x1920, 30fps, bitrate cukup")

    return _clamp(value), reasons


# ------------------------------------------------------------ hasil


@dataclass(slots=True)
class VPSResult:
    score: float
    components: dict[str, float] = field(default_factory=dict)
    reasons: dict[str, list[str]] = field(default_factory=dict)
    gates_failed: list[str] = field(default_factory=list)
    capped: bool = False
    unmeasured: list[str] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        return bool(self.unmeasured)

    def explain(self) -> str:
        parts = [f"VPS {self.score:.0f}"]
        for key in ("H", "R", "C", "A", "L", "P"):
            if key in self.components:
                parts.append(f"{key} {self.components[key]:.0f}")
        if self.gates_failed:
            parts.append("gagal: " + ", ".join(self.gates_failed))
        return " | ".join(parts)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "components": self.components,
            "reasons": self.reasons,
            "gates_failed": self.gates_failed,
            "capped": self.capped,
            "unmeasured": self.unmeasured,
        }


ALL_COMPONENTS = ("H", "R", "C", "A", "L", "P")


def evaluate(
    s: ClipSignals,
    weights: VPSWeights | None = None,
    measured: set[str] | None = None,
) -> VPSResult:
    """Hitung VPS beserta alasan per komponen dan hard gate.

    `measured` = komponen yang sinyalnya benar-benar terukur. Komponen lain
    dikeluarkan dari skor dan bobotnya dinormalkan ulang, bukan diisi angka
    default yang membuat klip tampak lebih baik (atau lebih buruk) dari bukti.
    """
    w = (weights or VPSWeights()).normalized()
    known = set(ALL_COMPONENTS) if measured is None else {
        k for k in measured if k in ALL_COMPONENTS
    }

    computed = {
        "H": score_hook(s),
        "R": score_retention(s),
        "C": score_caption(s),
        "A": score_audio(s),
        "L": score_loop(s),
        "P": score_platform(s),
    }
    components = {k: round(computed[k][0], 1) for k in ALL_COMPONENTS if k in known}
    reasons = {k: computed[k][1] for k in ALL_COMPONENTS if k in known}

    total_w = sum(getattr(w, k) for k in known)
    vps = (sum(getattr(w, k) * computed[k][0] for k in known) / total_w) if total_w else 0.0

    gates: list[str] = []
    if "H" in known and (s.speech_onset is None or s.speech_onset > 0.6):
        gates.append("tidak ada ucapan dalam 0.6s pertama")
    if "C" in known and s.caption_outside_safe:
        gates.append("caption keluar safe box")
    if "A" in known and (s.true_peak_dbtp > 0 or s.integrated_lufs < -20):
        gates.append("audio clipping / terlalu pelan")
    if s.duration < 8:
        gates.append("durasi < 8s")

    capped = bool(gates)
    if capped:
        vps = min(vps, 40.0)

    return VPSResult(
        score=round(_clamp(vps), 1),
        components=components,
        reasons=reasons,
        gates_failed=gates,
        capped=capped,
        unmeasured=[k for k in ALL_COMPONENTS if k not in known],
    )
