"""Pembangun video uji sintetis: satu orang bergerak, atau dua orang duduk diam.

Dipakai demo, bukan bagian produk. Tujuannya: memberi pipeline video yang
gerakannya diketahui persis, sehingga kesalahan crop bisa diukur, bukan dikira-kira.

Audio bisa sine (untuk uji gerak) atau file ucapan sungguhan (untuk uji ASR).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PORTRAIT = ROOT / "ui" / "assets" / "clip-frame-rio-01.jpg"


def _mux(video: str | Path, dst: Path, seconds: float, tone: float,
         audio: str | Path | None) -> None:
    """Tempel audio ke video. Tanpa `audio`, dipakai sine sebagai pengganti."""
    from clippergod.pipeline.render import resolve_ffmpeg

    if audio is None:
        src = ["-f", "lavfi", "-i", f"sine=frequency={tone:.0f}:duration={seconds}"]
    else:
        src = ["-i", str(audio)]

    subprocess.run(
        [resolve_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(video), *src,
         "-c:v", "copy", "-c:a", "aac", "-shortest", str(dst)],
        check=True,
    )
    Path(video).unlink(missing_ok=True)


def _person_sprite(person_height: int, mirror: bool = False):
    """Potong potret jadi sprite + mask feather, siap ditempel ke kanvas."""
    img = cv2.imread(str(PORTRAIT))
    if img is None:
        raise SystemExit(f"aset tidak ditemukan: {PORTRAIT}")
    person = img[0:1100, 100:1050]
    scale = person_height / person.shape[0]
    person = cv2.resize(person, (int(person.shape[1] * scale), person_height))
    if mirror:
        person = cv2.flip(person, 1)

    ph, pw = person.shape[:2]
    mask = np.zeros((ph, pw), dtype=np.float32)
    pad = 36
    mask[pad:ph - pad, pad:pw - pad] = 1.0
    mask = cv2.GaussianBlur(mask, (0, 0), pad / 2.0)[..., None]
    return person.astype(np.float32), mask


def build_two_speakers(
    dst: str | Path,
    seconds: float = 40.0,
    size: tuple[int, int] = (1280, 720),
    person_height: int = 430,
    margin: int = 60,
    fps: int = 30,
    tone: float = 200.0,
    audio: str | Path | None = None,
) -> Path:
    """Dua orang diam di kiri & kanan — kamera podcast statis, dua wajah.

    Dipakai untuk menguji speaker timeline: framing harus pindah antar wajah
    saat pembicara berganti, bukan meluncur pelan di antara keduanya.
    """
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    w, h = size

    left, left_mask = _person_sprite(person_height, mirror=False)
    right, right_mask = _person_sprite(person_height, mirror=True)
    ph, pw = left.shape[:2]
    y0 = (h - ph) // 2

    spots = [(margin, left, left_mask), (w - pw - margin, right, right_mask)]
    grad = np.tile(np.linspace(28, 12, w, dtype=np.float32), (h, 1))
    background = cv2.merge([grad, grad, grad * 1.06]).astype(np.uint8)

    silent = dst.with_name(dst.stem + "_tanpa_audio.mp4")
    writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not writer.isOpened():
        raise SystemExit("VideoWriter gagal dibuka")

    frames = int(round(seconds * fps))
    for _i in range(frames):
        canvas = background.copy()
        for x0, sprite, mask in spots:
            roi = canvas[y0:y0 + ph, x0:x0 + pw].astype(np.float32)
            canvas[y0:y0 + ph, x0:x0 + pw] = np.clip(
                sprite * mask + roi * (1.0 - mask), 0, 255
            ).astype(np.uint8)
        writer.write(canvas)
    writer.release()

    _mux(silent, dst, seconds, tone, audio)
    return dst


def build_moving_person(
    dst: str | Path,
    seconds: float = 8.0,
    size: tuple[int, int] = (1280, 720),
    person_height: int = 430,
    start_x: int = 140,
    travel: int = 500,
    fps: int = 30,
    tone: float = 220.0,
    audio: str | Path | None = None,
) -> Path:
    """Tulis video H.264 (orang bergerak) + audio sine atau file ucapan."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    w, h = size

    person_f, mask = _person_sprite(person_height, mirror=False)
    ph, pw = person_f.shape[:2]
    y0 = (h - ph) // 2
    grad = np.tile(np.linspace(28, 12, w, dtype=np.float32), (h, 1))
    background = cv2.merge([grad, grad, grad * 1.06]).astype(np.uint8)

    silent = dst.with_name(dst.stem + "_tanpa_audio.mp4")
    writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not writer.isOpened():
        raise SystemExit("VideoWriter gagal dibuka")

    frames = int(round(seconds * fps))
    for i in range(frames):
        canvas = background.copy()
        x0 = int(start_x + travel * (i / max(1, frames - 1)))
        x1 = min(w, x0 + pw)
        roi = canvas[y0:y0 + ph, x0:x1].astype(np.float32)
        m = mask[:, : x1 - x0]
        blended = person_f[:, : x1 - x0] * m + roi * (1.0 - m)
        canvas[y0:y0 + ph, x0:x1] = np.clip(blended, 0, 255).astype(np.uint8)
        writer.write(canvas)
    writer.release()

    _mux(silent, dst, seconds, tone, audio)
    return dst
