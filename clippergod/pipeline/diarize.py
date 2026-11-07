"""Diarisasi ringan: VAD energi + F0 (pitch) + k-means 1-D.

Ini **baseline**, bukan pengganti pyannote. Tujuannya menjawab satu pertanyaan
sempit: "giliran bicara ini suara siapa?" pada rekaman dengan dua warna suara
yang jelas berbeda (pria/wanita, dua host podcast).

Yang dipakai:
  1. VAD energi adaptif (ambang dari noise floor + puncak), buang hening.
  2. F0 per wilayah bicara lewat autokorelasi (70-400 Hz).
  3. k-means 1-D pada log F0, dua klaster; label diberi urut kemunculan.

Batasan yang harus disebut: dua pembicara dengan pitch mirip akan salah klaster,
dan suara di atas musik tidak tertangani. Kalau `pyannote` tersedia (butuh token
HuggingFace), modul ini bisa diganti tanpa mengubah pemanggil.
"""

from __future__ import annotations

import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..core.models import Word

FRAME_MS = 25
HOP_MS = 10
MIN_REGION = 0.30
MIN_GAP = 0.20
F0_MIN = 70.0
F0_MAX = 400.0


@dataclass(slots=True)
class SpeechRegion:
    start: float
    end: float
    f0: float | None = None
    speaker: str | None = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(slots=True)
class Diarization:
    regions: list[SpeechRegion] = field(default_factory=list)
    speakers: dict[str, dict] = field(default_factory=dict)
    sample_rate: int = 16000

    def speaker_at(self, t: float) -> str | None:
        for r in self.regions:
            if r.start <= t <= r.end:
                return r.speaker
        return None

    def segments(self) -> list[tuple[float, float, str]]:
        return [(r.start, r.end, r.speaker) for r in self.regions if r.speaker]

    def to_dict(self) -> dict:
        return {
            "sample_rate": self.sample_rate,
            "speakers": self.speakers,
            "regions": [
                {"start": round(r.start, 3), "end": round(r.end, 3),
                 "f0_hz": round(r.f0, 1) if r.f0 else None, "speaker": r.speaker}
                for r in self.regions
            ],
        }


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2:
            raise ValueError("butuh WAV PCM 16-bit")
        sr = wav.getframerate()
        channels = wav.getnchannels()
        raw = wav.readframes(wav.getnframes())
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, sr


def _frames(samples: np.ndarray, sr: int, frame_ms: int = FRAME_MS, hop_ms: int = HOP_MS):
    frame = max(1, int(sr * frame_ms / 1000))
    hop = max(1, int(sr * hop_ms / 1000))
    if len(samples) < frame:
        return np.zeros((0, frame), dtype=np.float32)
    count = 1 + (len(samples) - frame) // hop
    idx = np.arange(frame)[None, :] + hop * np.arange(count)[:, None]
    return samples[idx]


def _rms(frames: np.ndarray) -> np.ndarray:
    return np.sqrt((frames ** 2).mean(axis=1) + 1e-12)


def detect_regions(samples: np.ndarray, sr: int) -> list[SpeechRegion]:
    """VAD energi: ambang mengikuti noise floor dan puncak, bukan angka mati."""
    frames = _frames(samples, sr)
    if not len(frames):
        return []
    rms = _rms(frames)
    noise = float(np.percentile(rms, 20))
    peak = float(np.percentile(rms, 95))
    if peak < 1e-3:  # ~ -60 dBFS: praktis hening, tidak ada yang bisa diarisasi
        return []
    # Ambang adaptif, tapi tidak boleh melebihi 70% puncak: kalau rekaman tidak
    # punya jeda sama sekali, noise floor == puncak dan aturan "di atas noise"
    # akan membuang seluruh audio.
    threshold = min(max(noise * 1.8, peak * 0.10), peak * 0.7)
    threshold = max(threshold, 1e-3)
    voiced = rms > threshold

    hop = HOP_MS / 1000.0
    regions: list[SpeechRegion] = []
    i = 0
    n = len(voiced)
    while i < n:
        if not voiced[i]:
            i += 1
            continue
        j = i
        while j < n and voiced[j]:
            j += 1
        regions.append(SpeechRegion(start=i * hop, end=j * hop))
        i = j

    # gabung jeda pendek, buang wilayah terlalu pendek
    merged: list[SpeechRegion] = []
    for r in regions:
        if merged and r.start - merged[-1].end < MIN_GAP:
            merged[-1].end = r.end
        else:
            merged.append(r)
    return [r for r in merged if r.duration >= MIN_REGION]


def estimate_f0(samples: np.ndarray, sr: int, region: SpeechRegion) -> float | None:
    """Median F0 wilayah lewat autokorelasi; None kalau tidak ada periode jelas."""
    start = int(region.start * sr)
    end = int(region.end * sr)
    chunk = samples[start:end]
    frames = _frames(chunk, sr, frame_ms=40, hop_ms=20)
    if not len(frames):
        return None

    lo = int(sr / F0_MAX)
    hi = int(sr / F0_MIN)
    values: list[float] = []
    for frame in frames:
        x = frame - frame.mean()
        energy = float(np.sqrt((x ** 2).mean()))
        if energy < 1e-3:
            continue
        corr = np.correlate(x, x, mode="full")[len(x) - 1:]
        if len(corr) <= hi or corr[0] <= 0:
            continue
        corr = corr / corr[0]
        lag = lo + int(np.argmax(corr[lo:hi]))
        if corr[lag] < 0.30:
            continue
        values.append(sr / lag)
    if len(values) < 3:
        return None
    return float(np.median(values))


def cluster_f0(regions: list[SpeechRegion], k: int = 2) -> dict[str, dict]:
    """k-means 1-D pada log F0. Label S1, S2, ... diberi urut kemunculan."""
    voiced = [r for r in regions if r.f0]
    if not voiced:
        return {}
    xs = np.array([np.log(r.f0) for r in voiced])
    k = min(k, len(xs))
    if k == 1:
        centers = np.array([xs.mean()])
    else:
        centers = np.linspace(xs.min(), xs.max(), k)
        for _ in range(30):
            labels = np.abs(xs[:, None] - centers[None, :]).argmin(axis=1)
            new = np.array([xs[labels == i].mean() if np.any(labels == i) else centers[i]
                            for i in range(k)])
            if np.allclose(new, centers):
                break
            centers = new
    labels = np.abs(xs[:, None] - centers[None, :]).argmin(axis=1)

    # urutan label mengikuti klaster pertama yang muncul di rekaman
    order: list[int] = []
    for r, lab in zip(voiced, labels):
        if lab not in order:
            order.append(int(lab))
    name_for = {lab: f"S{i + 1}" for i, lab in enumerate(order)}

    stats: dict[str, dict] = {}
    for r, lab in zip(voiced, labels):
        r.speaker = name_for[int(lab)]
        entry = stats.setdefault(r.speaker, {"regions": 0, "f0": []})
        entry["regions"] += 1
        entry["f0"].append(r.f0)

    for name, entry in stats.items():
        f0s = entry.pop("f0")
        entry["f0_median"] = round(float(np.median(f0s)), 1)
        entry["duration"] = round(
            sum(r.duration for r in voiced if r.speaker == name), 2
        )
    return stats


def diarize_file(path: str | Path, k: int = 2) -> Diarization:
    samples, sr = read_wav(path)
    regions = detect_regions(samples, sr)
    for r in regions:
        r.f0 = estimate_f0(samples, sr, r)
    stats = cluster_f0(regions, k=k)
    return Diarization(regions=regions, speakers=stats, sample_rate=sr)


def label_words(words: list[Word], diar: Diarization, fallback: float = 0.75) -> list[Word]:
    """Tempelkan label pembicara ke tiap kata berdasarkan tumpang waktu.

    Ekor kata sering jatuh di luar wilayah yang terdeteksi VAD (konsonan akhir
    melemah). Untuk itu dipakai wilayah terdekat dalam `fallback` detik, supaya
    kata tidak dibiarkan tanpa label hanya karena ekornya tidak terdeteksi.
    """
    out: list[Word] = []
    for w in words:
        best, best_overlap = None, 0.0
        for r in diar.regions:
            if not r.speaker:
                continue
            overlap = min(w.end, r.end) - max(w.start, r.start)
            if overlap > best_overlap:
                best, best_overlap = r.speaker, overlap
        if best is None:
            nearest, distance = None, fallback
            mid = (w.start + w.end) / 2
            for r in diar.regions:
                if not r.speaker:
                    continue
                gap = max(r.start - mid, mid - r.end, 0.0)
                if gap < distance:
                    nearest, distance = r.speaker, gap
            best = nearest
        out.append(Word(text=w.text, start=w.start, end=w.end, prob=w.prob,
                        speaker=best or w.speaker))
    return out
