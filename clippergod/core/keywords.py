"""Pemilihan kata kunci untuk disorot di caption.

Yang disorot hanya kata yang benar-benar mengubah arti kalau dilewatkan:
angka, negasi, dan penanda urgensi/superlatif. Sapaan dan kata umum sengaja
tidak masuk — menyorot "halo" tidak menambah informasi, hanya menambah noise.
"""

from __future__ import annotations

NEGATION = frozenset({
    "jangan", "bukan", "gagal", "salah", "berhenti", "tidak", "nggak", "enggak",
    "belum", "tanpa", "stop", "never", "not", "no",
})
URGENCY = frozenset({
    "sekarang", "hari", "cepat", "terakhir", "batas", "deadline", "gratis",
    "rahasia", "penting", "wajib", "harus", "only", "now", "free", "secret",
})
SUPERLATIVE = frozenset({
    "paling", "terbaik", "terburuk", "selalu", "semua", "pertama", "utama",
    "satu-satunya", "terbesar", "tersering", "most", "best", "worst", "always",
})
LEXICON = NEGATION | URGENCY | SUPERLATIVE


def normalize(word: str) -> str:
    return "".join(ch for ch in word.lower() if ch.isalnum() or ch == "-")


def score(word: str) -> int:
    token = normalize(word)
    if not token:
        return 0
    if any(ch.isdigit() for ch in token):
        return 3
    if token in NEGATION:
        return 3
    if token in URGENCY or token in SUPERLATIVE:
        return 2
    return 0


def keyword_indices(words: list[str], limit: int = 2) -> set[int]:
    """Indeks kata yang layak disorot, maksimal `limit`, urut prioritas."""
    ranked = [(score(w), -i, i) for i, w in enumerate(words)]
    picked = [(s, i) for s, _neg, i in sorted(ranked, reverse=True) if s > 0]
    return {i for _s, i in picked[:max(0, limit)]}
