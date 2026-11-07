"""Deteksi & pelacakan wajah untuk auto-reframe.

Dua backend, keduanya CPU-only dan lisensi permisif:
  - YuNet (`cv2.FaceDetectorYN`, model 232 KB dari OpenCV Zoo, MIT) — default
    di OpenCV 5, di mana `CascadeClassifier` sudah dihapus dari API Python.
  - Haar cascade (`cv2.CascadeClassifier`) — dipakai kalau OpenCV 4.x terpasang
    dan model YuNet tidak tersedia.

Model YuNet tidak ikut di repo. Unduh sekali:
    python tools/fetch_face_model.py
lalu detektor menemukannya di `models/` (atau lewat CLIPPERGOD_FACE_MODEL).
Untuk produksi, antarmuka yang sama bisa diisi MediaPipe/Light-ASD tanpa
mengubah kode pemanggil.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import math
import cv2

from ..core.models import FaceBox

YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"


def yunet_model_path() -> Path | None:
    """Cari model YuNet: env var, lalu `models/` di root repo, lalu cache user."""
    env = os.environ.get("CLIPPERGOD_FACE_MODEL")
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    candidates.append(Path(__file__).resolve().parents[2] / "models" / YUNET_FILENAME)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "ClipperGod" / "models" / YUNET_FILENAME)
    for path in candidates:
        if path.is_file() and path.stat().st_size > 100_000:
            return path
    return None


class DetectorError(RuntimeError):
    """Dipakai saat detektor tidak bisa disiapkan."""


class FaceDetector(Protocol):
    def detect(self, frame) -> list[FaceBox]: ...


# ------------------------------------------------------------------ detektor


class YuNetFaceDetector:
    """YuNet: 232 KB, ~1 ms/frame di CPU, tahan wajah kecil & miring."""

    def __init__(self, model_path: str | Path | None = None, scale: float = 0.5,
                 score_threshold: float = 0.6) -> None:
        if not hasattr(cv2, "FaceDetectorYN"):
            raise DetectorError(
                "build OpenCV ini tidak punya FaceDetectorYN. Pasang opencv-python>=4.5.4 "
                "atau turunkan ke OpenCV 4.x untuk memakai Haar cascade."
            )
        path = Path(model_path) if model_path else yunet_model_path()
        if path is None or not path.is_file():
            raise DetectorError(
                "Model YuNet belum ada. Jalankan: python tools/fetch_face_model.py "
                f"(atau set CLIPPERGOD_FACE_MODEL ke file {YUNET_FILENAME})."
            )
        self.scale = scale
        self.score_threshold = score_threshold
        self.model_path = path
        self._det = None
        self._input_size: tuple[int, int] | None = None

    def _ensure(self, frame) -> None:
        h, w = frame.shape[:2]
        size = (max(2, int(w * self.scale) // 2 * 2), max(2, int(h * self.scale) // 2 * 2))
        if self._det is None:
            self._det = cv2.FaceDetectorYN.create(
                str(self.model_path), "", size, self.score_threshold, 0.3, 5000
            )
        if self._input_size != size:
            self._det.setInputSize(size)
            self._input_size = size

    def detect(self, frame) -> list[FaceBox]:
        self._ensure(frame)
        sw, sh = self._input_size  # type: ignore[misc]
        small = cv2.resize(frame, (sw, sh), interpolation=cv2.INTER_AREA)
        _, faces = self._det.detect(small)
        if faces is None:
            return []
        inv = 1.0 / self.scale
        boxes = [
            FaceBox(x0=float(f[0]) * inv, y0=float(f[1]) * inv,
                    x1=(float(f[0]) + float(f[2])) * inv,
                    y1=(float(f[1]) + float(f[3])) * inv)
            for f in faces
        ]
        return sorted(boxes, key=lambda b: b.area, reverse=True)


class HaarFaceDetector:
    """Haar cascade frontal face. Hanya ada di OpenCV 4.x."""

    def __init__(self, scale: float = 0.4, min_neighbors: int = 6,
                 min_size: int = 36) -> None:
        cascade_cls = getattr(cv2, "CascadeClassifier", None)
        if cascade_cls is None:
            raise DetectorError(
                "OpenCV ini tidak punya CascadeClassifier (dihapus di OpenCV 5). "
                "Pakai model YuNet: python tools/fetch_face_model.py"
            )
        path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        self._cascade = cascade_cls(str(path))
        if self._cascade.empty():
            raise DetectorError(f"cascade tidak bisa dimuat: {path}")
        self.scale = scale
        self.min_neighbors = min_neighbors
        self.min_size = min_size

    def detect(self, frame) -> list[FaceBox]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, None, fx=self.scale, fy=self.scale,
                           interpolation=cv2.INTER_AREA)
        rects = self._cascade.detectMultiScale(
            small,
            scaleFactor=1.1,
            minNeighbors=self.min_neighbors,
            minSize=(int(self.min_size * self.scale), int(self.min_size * self.scale)),
        )
        inv = 1.0 / self.scale
        boxes = [
            FaceBox(x0=x * inv, y0=y * inv, x1=(x + w) * inv, y1=(y + h) * inv)
            for (x, y, w, h) in rects
        ]
        return sorted(boxes, key=lambda b: b.area, reverse=True)


class OpenCVFaceDetector:
    """Fasad: YuNet kalau model tersedia, Haar kalau OpenCV 4.x."""

    def __init__(self, scale: float | None = None, **kwargs) -> None:
        errors: list[str] = []
        if yunet_model_path() is not None:
            try:
                self._impl: FaceDetector = YuNetFaceDetector(
                    scale=0.5 if scale is None else scale, **kwargs
                )
                self.backend = "yunet"
                return
            except DetectorError as exc:
                errors.append(str(exc))
        try:
            self._impl = HaarFaceDetector(scale=0.4 if scale is None else scale)
            self.backend = "haar"
            return
        except DetectorError as exc:
            errors.append(str(exc))
        raise DetectorError(
            "Tidak ada detektor wajah yang bisa dipakai:\n- " + "\n- ".join(errors)
        )

    def detect(self, frame) -> list[FaceBox]:
        return self._impl.detect(frame)


# ------------------------------------------------------------------ pelacak


def _iou(a: FaceBox, b: FaceBox) -> float:
    dx = min(a.x1, b.x1) - max(a.x0, b.x0)
    dy = min(a.y1, b.y1) - max(a.y0, b.y0)
    if dx <= 0 or dy <= 0:
        return 0.0
    inter = dx * dy
    union = a.area + b.area - inter
    return inter / union if union > 0 else 0.0


class FaceTracker:
    """Pencocokan IoU sederhana. Cukup untuk kamera statis (podcast/webcam)."""

    def __init__(self, iou_threshold: float = 0.25, max_missing: int = 8) -> None:
        self.iou_threshold = iou_threshold
        self.max_missing = max_missing
        self._next_id = 1
        self._tracks: dict[int, FaceBox] = {}
        self._missing: dict[int, int] = {}

    def update(self, boxes: list[FaceBox]) -> list[FaceBox]:
        assigned: list[FaceBox] = []
        used: set[int] = set()

        for box in boxes:
            best_id, best_iou = None, self.iou_threshold
            for tid, prev in self._tracks.items():
                if tid in used:
                    continue
                score = _iou(box, prev)
                if score > best_iou:
                    best_id, best_iou = tid, score

            if best_id is None:
                best_id = self._next_id
                self._next_id += 1

            used.add(best_id)
            tracked = FaceBox(box.x0, box.y0, box.x1, box.y1, track_id=best_id)
            self._tracks[best_id] = tracked
            self._missing[best_id] = 0
            assigned.append(tracked)

        for tid in list(self._tracks):
            if tid not in used:
                self._missing[tid] = self._missing.get(tid, 0) + 1
                if self._missing[tid] > self.max_missing:
                    self._tracks.pop(tid, None)
                    self._missing.pop(tid, None)

        return assigned


# ------------------------------------------------------------------ pemindaian


@dataclass(slots=True)
class FaceScan:
    samples: list[tuple[float, FaceBox]] = field(default_factory=list)
    track_hits: dict[int, int] = field(default_factory=dict)
    width: int = 0
    height: int = 0
    fps: float = 30.0
    duration: float = 0.0

    @property
    def dominant_track(self) -> int | None:
        if not self.track_hits:
            return None
        return max(self.track_hits, key=lambda k: self.track_hits[k])

    def centers(self, track_id: int | None = None) -> list[tuple[float, float]]:
        tid = track_id if track_id is not None else self.dominant_track
        return [(t, (b.x0 + b.x1) / 2.0) for t, b in self.samples if b.track_id == tid]

    @property
    def hit_rate(self) -> float:
        return len(self.samples)

    def boxes(self, track_id: int | None = None) -> list[tuple[float, FaceBox]]:
        tid = track_id if track_id is not None else self.dominant_track
        return [(t, b) for t, b in self.samples if b.track_id == tid]

    def nearest(self, t: float, track_id: int | None = None) -> FaceBox | None:
        """Kotak wajah terdekat dari waktu `t` (sampel tidak harus pas detiknya)."""
        items = self.boxes(track_id)
        if not items:
            return None
        return min(items, key=lambda item: abs(item[0] - t))[1]


def scan_video(
    path: str | Path,
    detector: FaceDetector | None = None,
    sample_fps: float = 6.0,
    max_seconds: float | None = None,
    cancel=None,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> FaceScan:
    """Baca rentang video dan deteksi wajah tiap ~1/sample_fps detik."""
    if not math.isfinite(start_seconds) or start_seconds < 0:
        raise ValueError("waktu awal scan harus angka >= 0")
    if end_seconds is not None and (
        not math.isfinite(end_seconds) or end_seconds <= start_seconds
    ):
        raise ValueError("waktu akhir scan harus lebih besar dari waktu awal")
    detector = detector or OpenCVFaceDetector()
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise DetectorError(f"video tidak bisa dibuka: {path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    source_duration = total / fps if fps else 0.0
    duration = source_duration
    if max_seconds:
        duration = min(duration, max_seconds)
    if end_seconds is not None:
        duration = min(duration, end_seconds)
    if start_seconds >= duration and duration > 0:
        cap.release()
        raise ValueError("waktu awal scan melewati durasi video")
    scan_end = duration if end_seconds is None else min(duration, end_seconds)

    step = max(1, int(round(fps / max(1.0, sample_fps))))
    tracker = FaceTracker()
    scan = FaceScan(
        width=width, height=height, fps=fps,
        duration=max(0.0, scan_end - start_seconds),
    )

    seeked = (
        cap.set(cv2.CAP_PROP_POS_MSEC, start_seconds * 1000)
        if start_seconds else False
    )
    idx = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) if seeked else 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = idx / fps
        if t >= scan_end:
            break
        if idx % 50 == 0 and cancel is not None:
            cancel.raise_if_cancelled()
        if t >= start_seconds and idx % step == 0:
            for box in tracker.update(detector.detect(frame)):
                scan.samples.append((t, box))
                scan.track_hits[box.track_id] = scan.track_hits.get(box.track_id, 0) + 1
        idx += 1

    cap.release()
    return scan
