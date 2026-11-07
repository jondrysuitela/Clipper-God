"""Deteksi reaksi (tawa/aplaus) untuk Punchline Guard.

Heuristik, bukan pengklasifikasi: wilayah bersuara dengan energi tinggi dan
spektrum rata (noise-like) dianggap reaksi; tawa pendek, aplaus panjang.
Batasannya harus disebut: musik dan derau angin juga noise-like, jadi hasilnya
dipakai untuk *memperpanjang* akhir klip, bukan untuk memotong apa pun.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from .asr import extract_audio
from .diarize import read_wav

FRAME = 0.05
HOP = 0.025
FLAT_MIN = 0.35          # 0 = tonal, 1 = noise rata
MIN_REGION = 0.25
MERGE_GAP = 0.12
APPLAUSE_MIN = 1.2


def analyse(samples: np.ndarray, sr: int, chunk: int = 8192) -> tuple[np.ndarray, np.ndarray, float]:
    """RMS + spectral flatness per frame. Diproses per blok supaya hemat memori."""
    frame_n = max(1, int(sr * FRAME))
    hop = max(1, int(sr * HOP))
    if len(samples) < frame_n:
        return np.zeros(0), np.zeros(0), HOP
    total = 1 + (len(samples) - frame_n) // hop
    rms = np.empty(total)
    flat = np.empty(total)
    offsets = np.arange(frame_n)[None, :]
    for start in range(0, total, chunk):
        stop = min(total, start + chunk)
        idx = offsets + hop * np.arange(start, stop)[:, None]
        block = samples[idx]
        rms[start:stop] = np.sqrt((block ** 2).mean(axis=1) + 1e-12)
        mag = np.abs(np.fft.rfft(block, axis=1)) + 1e-9
        flat[start:stop] = np.exp(np.log(mag).mean(axis=1)) / mag.mean(axis=1)
    return rms, flat, hop / sr


def regions(rms: np.ndarray, flat: np.ndarray, step: float) -> list[tuple[float, float]]:
    """Gabungkan frame noise-like yang berurutan jadi wilayah reaksi."""
    if not len(rms):
        return []
    base = float(np.median(rms))
    threshold = max(base * 1.5, 0.01)
    mask = (rms > threshold) & (flat > FLAT_MIN)

    out: list[tuple[float, float]] = []
    start: float | None = None
    last = 0.0
    for i, on in enumerate(mask):
        t = i * step
        if on:
            if start is None:
                start = t
            last = t
        elif start is not None and t - last > MERGE_GAP:
            out.append((start, last + step))
            start = None
    if start is not None:
        out.append((start, last + step))
    return [(s, e) for s, e in out if e - s >= MIN_REGION]


def classify(start: float, end: float) -> str:
    return "applause" if (end - start) >= APPLAUSE_MIN else "laughter"


def detect_reactions(video: str | Path) -> list[tuple[float, float, str]]:
    """Ambil audio video, kembalikan wilayah reaksi dalam waktu absolut sumber."""
    with tempfile.TemporaryDirectory(prefix="cg-react-") as tmp:
        wav = extract_audio(video, Path(tmp) / "audio.wav")
        samples, sr = read_wav(wav)
    rms, flat, step = analyse(samples, sr)
    return [(s, e, classify(s, e)) for s, e in regions(rms, flat, step)]
