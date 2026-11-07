"""Ukur sinyal VPS dari klip yang sudah dirender.

Prinsip: hanya isi komponen yang benar-benar diukur. Kalau ffmpeg gagal atau
file tidak bisa dibaca, sinyalnya tetap None dan komponen itu tidak dinilai —
bukan diisi angka default yang membuat skor terlihat meyakinkan.

Semua helper murni (parse_loudnorm, ssim, cuts_per_minute) dipisah dari IO
supaya bisa diuji tanpa ffmpeg maupun file video.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

from ..core.models import Word
from ..core.scoring import ClipSignals

CUT_DIFF = 18.0        # rata-rata selisih piksel (0-255) yang dianggap ganti shot
STATIC_DIFF = 2.0      # di bawah ini frame praktis tidak berubah
SIZE = (160, 90)       # resolusi kerja untuk motion/histogram


# ------------------------------------------------------------------ murni


def parse_loudnorm(stderr: str) -> tuple[float | None, float | None]:
    """Ambil (integrated LUFS, true peak dBTP) dari blok JSON loudnorm."""
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start < 0 or end <= start:
        return None, None
    try:
        data = json.loads(stderr[start:end + 1])
    except ValueError:
        return None, None

    def num(key: str) -> float | None:
        try:
            value = float(data[key])
        except (KeyError, TypeError, ValueError):
            return None
        return value if np.isfinite(value) else None

    return num("input_i"), num("input_tp")


def ssim(a: np.ndarray, b: np.ndarray) -> float:
    """SSIM global dua frame grayscale (tanpa scikit-image)."""
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    mu_a, mu_b = a.mean(), b.mean()
    var_a, var_b = a.var(), b.var()
    cov = ((a - mu_a) * (b - mu_b)).mean()
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    denom = (mu_a ** 2 + mu_b ** 2 + c1) * (var_a + var_b + c2)
    return float(((2 * mu_a * mu_b + c1) * (2 * cov + c2)) / denom) if denom else 0.0


def cuts_per_minute(diffs: list[float], step: float, threshold: float = CUT_DIFF) -> float:
    if not diffs or step <= 0:
        return 0.0
    cuts = sum(1 for d in diffs if d >= threshold)
    return cuts / (len(diffs) * step) * 60.0


def motion_score(diff: float) -> float:
    """Selisih piksel -> 0..1. 16 level rata-rata sudah dianggap gerakan penuh."""
    return float(max(0.0, min(1.0, diff / 16.0)))


def static_runs(diffs: list[float], step: float, hold: float = 6.0) -> int:
    runs, length = 0, 0.0
    for d in diffs:
        if d < STATIC_DIFF:
            length += step
        else:
            if length >= hold:
                runs += 1
            length = 0.0
    return runs + (1 if length >= hold else 0)


def speech_gaps(words: list[Word], minimum: float = 0.6) -> int:
    return sum(1 for a, b in zip(words, words[1:]) if b.start - a.end > minimum)


# ------------------------------------------------------------------ IO


def measure_audio(path: str | Path, ffmpeg: str | None = None) -> tuple[float | None, float | None]:
    from .render import resolve_ffmpeg

    cmd = [
        ffmpeg or resolve_ffmpeg(), "-hide_banner", "-nostats", "-i", str(path),
        "-vn", "-af", "loudnorm=I=-14:TP=-1:print_format=json", "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None, None
    return parse_loudnorm(proc.stderr or "")


def _gray(cap: cv2.VideoCapture) -> np.ndarray:
    ok, frame = cap.read()
    if not ok:
        return np.zeros(SIZE, dtype=np.uint8)
    return cv2.cvtColor(cv2.resize(frame, SIZE), cv2.COLOR_BGR2GRAY)


def loop_similarity(path: str | Path) -> float | None:
    """SSIM frame terakhir vs frame pertama — bahan komponen L."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    first = _gray(cap)
    if total > 1:
        cap.set(cv2.CAP_PROP_POS_FRAMES, total - 1)
    last = _gray(cap)
    cap.release()
    return ssim(first, last)


def scan_motion(path: str | Path, sample_fps: float = 4.0,
                max_seconds: float | None = None) -> tuple[list[float], float]:
    """Selisih antar frame pada `sample_fps`. Return (diffs, step_detik)."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return [], 0.0
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps / max(1.0, sample_fps))))
    diffs: list[float] = []
    prev: np.ndarray | None = None
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if max_seconds is not None and idx / fps > max_seconds:
            break
        if idx % step == 0:
            gray = cv2.cvtColor(cv2.resize(frame, SIZE), cv2.COLOR_BGR2GRAY).astype(np.int16)
            if prev is not None:
                diffs.append(float(np.abs(gray - prev).mean()))
            prev = gray
        idx += 1
    cap.release()
    return diffs, step / fps if fps else 0.0


def measure_clip(
    path: str | Path,
    words: list[Word],
    *,
    face_in_first_frame: bool | None = None,
    greeting_opening: bool = False,
    ffmpeg: str | None = None,
) -> tuple[ClipSignals, set[str]]:
    """Bangun ClipSignals dari klip hasil render.

    Return (sinyal, komponen yang benar-benar terukur). Komponen yang gagal
    diukur tidak masuk daftar — jadi tidak ikut dinilai sama sekali.
    """
    from .render import probe_video

    info = probe_video(path)
    duration = float(info["duration"]) or 0.0
    bitrate = (float(info["size_mb"]) * 8.0 / duration) if duration else 0.0

    lufs, peak = measure_audio(path, ffmpeg=ffmpeg)
    diffs, step = scan_motion(path, max_seconds=3.0)
    full_diffs, full_step = scan_motion(path)
    loop = loop_similarity(path)
    changes = [i * step for i, d in enumerate(diffs) if d >= CUT_DIFF]
    # Tidak ada perubahan = terukur statis (skor 0), bukan "belum diukur".
    visual_change = changes[0] if changes else (duration if diffs else None)

    measured = {"P"}
    if diffs:
        measured.add("H")
    if full_diffs:
        measured.add("R")
    if lufs is not None and peak is not None:
        measured.add("A")
    if loop is not None:
        measured.add("L")

    signals = ClipSignals(
        duration=duration,
        speech_onset=words[0].start if words else None,
        motion_first_frame=motion_score(diffs[0]) if diffs else None,
        face_in_first_frame=face_in_first_frame,
        hook_text=" ".join(w.clean for w in words[:12]),
        greeting_opening=greeting_opening,
        visual_change_at=visual_change,
        cut_rate_cpm=cuts_per_minute(full_diffs, full_step),
        speech_gaps_over_06=speech_gaps(words),
        long_static_shots=static_runs(full_diffs, full_step),
        integrated_lufs=lufs if lufs is not None else -14.0,
        true_peak_dbtp=peak if peak is not None else -1.0,
        loop_similarity=loop if loop is not None else 0.0,
        width=int(info["width"]),
        height=int(info["height"]),
        fps=int(round(float(info["fps"]))),
        video_bitrate_mbps=bitrate,
    )
    return signals, measured
