"""Semantic Boundary Engine.

Tujuan: klip tidak pernah mulai/berhenti di tengah kalimat atau tengah ide.
Ini jawaban langsung untuk keluhan #1 di seluruh kategori clipper
("it always cuts out the funny or important parts").

Skor batas 0.0-1.0. >=0.70 aman, 0.45-0.70 bisa digeser, <0.45 tolak klip.
Semua ambang ada di `BoundaryConfig` supaya bisa dikalibrasi tanpa ubah kode.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Boundary, BoundedClip, Word

# --------------------------------------------------------------- leksikon

#: Kata yang menggantung kalau dipakai sebagai kata TERAKHIR sebuah klip.
DANGLING_TAIL = frozenset(
    {
        "dan", "atau", "tapi", "tetapi", "karena", "yang", "kalau", "jadi",
        "untuk", "dengan", "di", "ke", "dari", "pada", "sehingga", "lalu",
        "kemudian", "sementara", "padahal", "meskipun", "walaupun", "biar",
        "supaya", "kalau", "bahwa", "seperti", "oleh", "akan", "sudah",
        "masih", "lagi", "juga", "saja", "sih", "kan", "deh", "dong",
    }
)

#: Kata yang jelek kalau jadi kata PERTAMA sebuah klip (tidak ada hook).
WEAK_OPENERS = frozenset(
    {"jadi", "oke", "ok", "ya", "nah", "terus", "lalu", "dan", "tapi"}
)

#: Sapaan / pembuka yang membuang 3 detik pertama.
GREETINGS = frozenset(
    {
        "hai", "hi", "hello", "halo", "guys", "semua", "selamat", "datang",
        "pagi", "siang", "malam", "assalamualaikum", "salam",
    }
)

#: Filler konservatif. Sengaja tidak memasukkan "apa"/"ya" karena terlalu
#: sering muncul sebagai kata bermakna.
FILLERS = frozenset({"eee", "ee", "emm", "em", "ehm", "hmm", "hm", "mmm", "aaa", "anu"})

SENTENCE_END = (".", "?", "!", "…")


@dataclass(frozen=True, slots=True)
class BoundaryConfig:
    """Ambang yang bisa dikalibrasi. Default = hasil riset 03 §12.8."""

    min_pause: float = 0.18
    good_pause: float = 0.35
    start_window: float = 2.0
    end_window: float = 2.5
    accept_score: float = 0.70
    shift_score: float = 0.45
    proximity_penalty: float = 0.10  # penalti per detik jarak dari titik awal
    min_duration: float = 8.0
    max_duration: float = 180.0


# --------------------------------------------------------------- utilitas


def _norm(text: str) -> str:
    return "".join(ch for ch in text.strip().lower() if ch.isalnum())


def _is_sentence_end(text: str) -> bool:
    return text.rstrip().endswith(SENTENCE_END)


def _gap_before(words: list[Word], i: int) -> float:
    """Jeda (detik) tepat sebelum kata ke-`i`."""
    if i <= 0:
        return words[0].start if words else 0.0
    if i >= len(words):
        return 5.0  # akhir transkrip: selalu dianggap jeda panjang
    return max(0.0, words[i].start - words[i - 1].end)


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


# --------------------------------------------------------------- penilaian


def score_boundary(
    words: list[Word],
    i: int,
    role: str = "end",
    cfg: BoundaryConfig | None = None,
) -> Boundary:
    """Nilai apakah memotong di indeks `i` aman.

    role="end"   -> potongan ini adalah AKHIR klip (ide harus tuntas)
    role="start" -> potongan ini adalah AWAL klip (harus langsung hook)
    """
    cfg = cfg or BoundaryConfig()
    if not words:
        return Boundary(0.0, 0, 0.0, ("empty",))

    i = max(0, min(i, len(words)))
    pause = _gap_before(words, i)
    reasons: list[str] = []

    # --- jeda ---------------------------------------------------------
    if pause >= cfg.good_pause:
        pause_c = 1.0
        reasons.append(f"jeda {pause:.2f}s")
    elif pause >= cfg.min_pause:
        pause_c = _clamp01((pause - cfg.min_pause) / max(1e-6, cfg.good_pause - cfg.min_pause))
        reasons.append(f"jeda tipis {pause:.2f}s")
    else:
        pause_c = 0.0
        reasons.append(f"tanpa jeda ({pause:.2f}s)")

    if role == "end":
        prev = words[i - 1] if i > 0 else None
        prev_text = prev.clean if prev else ""
        prev_norm = _norm(prev_text)

        sentence_c = 1.0 if _is_sentence_end(prev_text) else 0.0
        if sentence_c:
            reasons.append("akhir kalimat")

        dangling_c = 0.0 if prev_norm in DANGLING_TAIL else 1.0
        if not dangling_c:
            reasons.append(f"kata menggantung: '{prev_text}'")

        filler_c = 0.0 if (prev_norm in FILLERS or _norm(words[i].clean if i < len(words) else "") in FILLERS) else 1.0
        if not filler_c:
            reasons.append("berhenti di filler")

        # ide tuntas: potongan yang layak punya minimal 3 kata sebelum batas
        chunk = words[max(0, i - 60):i]
        complete_c = 1.0 if len(chunk) >= 3 else 0.0
        if not complete_c:
            reasons.append("potongan terlalu pendek")

        score = (
            0.35 * pause_c
            + 0.25 * sentence_c
            + 0.20 * dangling_c
            + 0.10 * filler_c
            + 0.10 * complete_c
        )

    else:  # role == "start"
        nxt = words[i] if i < len(words) else None
        nxt_text = nxt.clean if nxt else ""
        nxt_norm = _norm(nxt_text)

        conj_c = 0.0 if nxt_norm in DANGLING_TAIL else 1.0
        if not conj_c:
            reasons.append(f"mulai dari konjungsi: '{nxt_text}'")

        greet_c = 0.0 if nxt_norm in GREETINGS else 1.0
        if not greet_c:
            reasons.append(f"mulai dari sapaan: '{nxt_text}'")

        weak_c = 0.0 if nxt_norm in WEAK_OPENERS else 1.0
        if not weak_c:
            reasons.append(f"pembuka lemah: '{nxt_text}'")

        filler_c = 0.0 if nxt_norm in FILLERS else 1.0
        prev_c = 1.0 if (i > 0 and _is_sentence_end(words[i - 1].clean)) else 0.0

        score = (
            0.30 * pause_c
            + 0.25 * conj_c
            + 0.25 * min(greet_c, weak_c)
            + 0.10 * filler_c
            + 0.10 * prev_c
        )

    time = _boundary_time(words, i)
    return Boundary(time=time, index=i, score=round(_clamp01(score), 4), reasons=tuple(reasons))


def _boundary_time(words: list[Word], i: int) -> float:
    if not words:
        return 0.0
    if i <= 0:
        return words[0].start
    if i >= len(words):
        return words[-1].end
    return (words[i - 1].end + words[i].start) / 2.0


# --------------------------------------------------------------- pencarian


def find_boundaries(
    words: list[Word], role: str = "end", cfg: BoundaryConfig | None = None
) -> list[Boundary]:
    """Semua kandidat titik potong, urut waktu."""
    cfg = cfg or BoundaryConfig()
    return [score_boundary(words, i, role, cfg) for i in range(0, len(words) + 1)]


def snap(
    words: list[Word],
    t: float,
    role: str = "end",
    cfg: BoundaryConfig | None = None,
) -> Boundary | None:
    """Geser waktu `t` ke batas aman terdekat di dalam jendela pencarian.

    Memilih skor tertinggi dikurangi penalti jarak, supaya klip tidak bergeser
    jauh hanya demi batas yang sedikit lebih baik.
    """
    cfg = cfg or BoundaryConfig()
    window = cfg.start_window if role == "start" else cfg.end_window
    best: Boundary | None = None
    best_rank = -1e9

    for i in range(0, len(words) + 1):
        b = score_boundary(words, i, role, cfg)
        dist = abs(b.time - t)
        if dist > window:
            continue
        rank = b.score - cfg.proximity_penalty * dist
        if rank > best_rank:
            best_rank = rank
            best = b
    return best


def is_greeting_opening(words: list[Word], start: float, lookahead: float = 2.5) -> bool:
    """True kalau 2.5 detik pertama klip hanya berisi sapaan."""
    head = [w for w in words if start - 0.05 <= w.start <= start + lookahead]
    if not head:
        return False
    return all(_norm(w.clean) in GREETINGS for w in head)


# --------------------------------------------------------------- pemaksaan


def enforce(
    words: list[Word],
    start: float,
    end: float,
    cfg: BoundaryConfig | None = None,
) -> BoundedClip:
    """Paksa satu kandidat klip jatuh di batas semantik yang aman."""
    cfg = cfg or BoundaryConfig()
    if not words:
        return BoundedClip(start, end, rejected=True, reject_reason="transkrip kosong")

    start_b = snap(words, start, "start", cfg)
    end_b = snap(words, end, "end", cfg)
    warnings: list[str] = []

    new_start = start_b.time if start_b else start
    new_end = end_b.time if end_b else end

    if start_b is None:
        warnings.append("tidak ada batas awal yang aman")
    elif start_b.score < cfg.shift_score:
        return BoundedClip(
            new_start, new_end, start_b, end_b,
            rejected=True,
            reject_reason=f"awal klip tidak bisa diselamatkan (skor {start_b.score:.2f})",
        )

    if end_b is None:
        warnings.append("tidak ada batas akhir yang aman")
    elif end_b.score < cfg.shift_score:
        return BoundedClip(
            new_start, new_end, start_b, end_b,
            rejected=True,
            reject_reason=f"akhir klip tidak bisa diselamatkan (skor {end_b.score:.2f})",
        )

    if new_end <= new_start:
        return BoundedClip(
            new_start, new_end, start_b, end_b,
            rejected=True, reject_reason="batas terbalik setelah snapping",
        )

    dur = new_end - new_start
    if dur < cfg.min_duration:
        warnings.append(f"terlalu pendek ({dur:.1f}s < {cfg.min_duration}s)")
    if dur > cfg.max_duration:
        warnings.append(f"terlalu panjang ({dur:.1f}s > {cfg.max_duration}s)")

    if is_greeting_opening(words, new_start):
        warnings.append("pembuka masih berupa sapaan")

    return BoundedClip(new_start, new_end, start_b, end_b, warnings=warnings)


def extend_for_reaction(
    end: float,
    reactions: list[tuple[float, float]],
    max_extend: float = 3.0,
    tail: float = 0.2,
) -> float:
    """Punchline guard: jangan potong sebelum tawa/aplaus selesai.

    `reactions` = daftar interval (start, end) hasil deteksi tawa/aplaus.
    Kalau reaksi beririsan dengan 1.5 s sebelum akhir klip, perpanjang akhir.
    """
    new_end = end
    for r_start, r_end in reactions:
        if r_start - 1.5 <= end <= r_end + 0.5:
            new_end = max(new_end, min(r_end + tail, end + max_extend))
    return new_end
