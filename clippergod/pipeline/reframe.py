"""Perencana crop vertikal (auto-reframe).

Masalah: FFmpeg `crop` hanya menerima ekspresi matematis, bukan array posisi.
Solusi: jalur crop yang sudah dihaluskan di-fit ke polinomial orde rendah, lalu
polinomial itu yang ditulis sebagai ekspresi `x='...'`. Hasilnya pan yang mulus
tanpa filter graph raksasa.

Urutan filter (dari riset 02 §7.2):
  deadband -> EMA -> Kalman -> clamp kecepatan -> fit polinomial

EMA dan Kalman dijalankan dua arah (maju lalu mundur). Offline kita punya
seluruh rekaman, jadi tidak perlu mengorbankan akurasi demi kausalitas: filter
dua arah tidak punya lag, sedangkan filter satu arah selalu tertinggal ~15 px
saat wajah bergerak konstan.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True, slots=True)
class ReframeConfig:
    out_ratio: float = 9 / 16        # 0.5625
    fps: int = 30
    deadband_px: float = 12.0        # abaikan gerakan kecil (jitter wajah)
    ema_alpha: float = 0.16          # 0 = sangat halus, 1 = mentah
    max_step_px: float = 9.0         # batas gerak per frame
    headroom: float = 0.08           # ruang di atas kepala, porsi tinggi crop
    poly_degree: int = 3
    # 2% lebar crop (~8 px @405) -> ~1% lebar output. Di bawah itu tidak terlihat
    # mata; lebih ketat dari ini hanya mengejar noise detektor.
    max_residual_ratio: float = 0.02


@dataclass(slots=True)
class CropPath:
    """Jalur crop siap dipakai renderer."""

    x: list[float]
    crop_w: int
    crop_h: int
    src_w: int
    src_h: int
    coeffs: list[float] = field(default_factory=list)
    residual: float = 0.0
    static: bool = False
    fps: int = 30

    @property
    def max_x(self) -> float:
        return max(0.0, self.src_w - self.crop_w)

    def expression(self, var: str = "t") -> str:
        """Ekspresi FFmpeg untuk `crop=x=...`, dalam detik (`t`).

        `coeffs` disimpan dalam domain indeks frame (urutan np.polyfit: pangkat
        tertinggi dulu). Dua hal yang mudah salah di sini:
          - urutan koefisien harus dibalik ke pangkat naik,
          - variabel `t` berjalan dalam detik, jadi tiap pangkat diskalakan fps**k.
        Tanpa `eval=frame` di filter, FFmpeg hanya mengevaluasi sekali di awal.
        """
        if self.static or not self.coeffs:
            return str(int(round(self.x[0] if self.x else 0)))
        parts: list[str] = []
        for power, c in enumerate(reversed(self.coeffs)):
            k = c * (self.fps ** power)
            if abs(k) < 1e-9:
                continue
            if power == 0:
                parts.append(f"{k:.4f}")
            elif power == 1:
                parts.append(f"{k:.4f}*{var}")
            else:
                parts.append(f"{k:.4f}*pow({var},{power})")
        if not parts:
            return "0"
        expr = "+".join(parts)
        return f"max(0,min({self.max_x:.0f},{expr}))"

    def at(self, frame: int) -> float:
        if self.static or not self.coeffs:
            return self.x[0] if self.x else 0.0
        return float(np.polyval(self.coeffs, frame))


def _resample(samples: list[tuple[float, float]], duration: float, fps: int) -> np.ndarray:
    """Ubah sampel (t, cx) yang tidak teratur menjadi kurva per frame."""
    n = max(1, int(round(duration * fps)))
    if not samples:
        return np.zeros(n)

    ts = np.array([s[0] for s in samples], dtype=float)
    vs = np.array([s[1] for s in samples], dtype=float)
    order = np.argsort(ts)
    ts, vs = ts[order], vs[order]

    grid = np.arange(n) / fps
    if len(ts) == 1:
        return np.full(n, vs[0])
    return np.interp(grid, ts, vs)


def _deadband(raw: np.ndarray, band: float) -> np.ndarray:
    out = np.empty_like(raw)
    held = float(raw[0])
    for i, v in enumerate(raw):
        if abs(v - held) >= band:
            held = float(v)
        out[i] = held
    return out


def _ema(raw: np.ndarray, alpha: float) -> np.ndarray:
    out = np.empty_like(raw)
    acc = float(raw[0])
    for i, v in enumerate(raw):
        acc = alpha * float(v) + (1.0 - alpha) * acc
        out[i] = acc
    return out


def _ema_zero_phase(raw: np.ndarray, alpha: float) -> np.ndarray:
    """EMA maju + mundur: halus tanpa lag (butuh seluruh sinyal, offline)."""
    if len(raw) < 3:
        return raw.astype(float).copy()
    forward = _ema(raw, alpha)
    return _ema(forward[::-1], alpha)[::-1]


def _kalman_1d(raw: np.ndarray, q: float = 6.0, r: float = 40.0) -> np.ndarray:
    """Kalman constant-velocity sederhana: posisi + kecepatan."""
    out = np.empty_like(raw)
    x, v = float(raw[0]), 0.0
    p00, p01, p11 = 1.0, 0.0, 1.0
    for i, z in enumerate(raw):
        # prediksi
        x = x + v
        p00 += p01 + p11 * 0.0 + q
        p01 += p11
        p11 += q
        # koreksi
        y = float(z) - x
        s = p00 + r
        k0, k1 = p00 / s, p01 / s
        x += k0 * y
        v += k1 * y
        p00 -= k0 * p00
        p01 -= k0 * p01
        p11 -= k1 * p01
        out[i] = x
    return out


def _clamp_step(path: np.ndarray, max_step: float) -> np.ndarray:
    out = np.empty_like(path)
    out[0] = path[0]
    for i in range(1, len(path)):
        delta = float(path[i] - out[i - 1])
        delta = max(-max_step, min(max_step, delta))
        out[i] = out[i - 1] + delta
    return out


def _clamp_step_zero_phase(path: np.ndarray, max_step: float) -> np.ndarray:
    """Batas kecepatan dua arah, supaya tidak menyeret posisi ke belakang."""
    if len(path) < 3:
        return _clamp_step(path, max_step)
    forward = _clamp_step(path, max_step)
    backward = _clamp_step(forward[::-1], max_step)[::-1]
    return (forward + backward) / 2.0


def _fit_path(path: np.ndarray, start_degree: int, tolerance: float) -> tuple[list[float], float, int]:
    """Fit polinomial sesederhana mungkin yang masih di dalam toleransi.

    Derajat dinaikkan satu per satu sampai residu <= tolerance; kalau tetap
    tidak tercapai, derajat terbaik yang dipakai dan residunya dilaporkan
    (pemanggil bisa memperingatkan user, bukan diam-diam menggelembungkan klaim).
    """
    n = np.arange(len(path))
    best: tuple[list[float], float, int] | None = None
    for degree in range(start_degree, 6):
        deg = min(degree, max(1, len(path) - 1))
        coeffs = np.polyfit(n, path, deg)
        residual = float(np.max(np.abs(np.polyval(coeffs, n) - path)))
        if best is None or residual < best[1]:
            best = ([float(c) for c in coeffs], residual, deg)
        if residual <= tolerance:
            return best
        if deg == max(1, len(path) - 1):
            break
    assert best is not None
    return best


def plan_crop(
    face_centers: list[tuple[float, float]],
    duration: float,
    src_w: int,
    src_h: int,
    cfg: ReframeConfig | None = None,
) -> CropPath:
    """`face_centers` = [(detik, pusat_x_wajah), ...] pada koordinat sumber."""
    cfg = cfg or ReframeConfig()

    crop_w = int(round(src_h * cfg.out_ratio))
    crop_w = min(crop_w, src_w)
    crop_h = src_h

    raw_cx = _resample(face_centers, duration, cfg.fps)
    target_x = np.clip(raw_cx - crop_w / 2.0, 0.0, max(0.0, src_w - crop_w))

    path = _deadband(target_x, cfg.deadband_px)
    path = _ema_zero_phase(path, cfg.ema_alpha)
    path = _kalman_1d(path)
    path = _kalman_1d(path[::-1])[::-1]
    path = _clamp_step_zero_phase(path, cfg.max_step_px)
    path = np.clip(path, 0.0, max(0.0, src_w - crop_w))

    variance = float(np.max(path) - np.min(path)) if len(path) else 0.0
    static = variance < max(4.0, cfg.deadband_px * 0.5)

    if static:
        fixed = float(np.median(path)) if len(path) else 0.0
        return CropPath(
            x=[fixed] * max(1, len(path)), crop_w=crop_w, crop_h=crop_h,
            src_w=src_w, src_h=src_h, coeffs=[fixed], residual=0.0, static=True,
            fps=cfg.fps,
        )

    n = np.arange(len(path))
    tolerance = max(0.5, cfg.max_residual_ratio * crop_w)
    coeffs, residual, _degree = _fit_path(path, cfg.poly_degree, tolerance)

    return CropPath(
        x=[float(v) for v in path],
        crop_w=crop_w, crop_h=crop_h, src_w=src_w, src_h=src_h,
        coeffs=coeffs,
        residual=residual,
        static=False,
        fps=cfg.fps,
    )


def crop_pixel_deviation(path: CropPath, frame: int) -> float:
    """Selisih antara posisi sebenarnya dan hasil fit — untuk QA render."""
    return abs(path.at(frame) - path.x[min(frame, len(path.x) - 1)])


# ------------------------------------------------------------------ per speaker


def crop_width(src_w: int, src_h: int, cfg: ReframeConfig | None = None) -> int:
    cfg = cfg or ReframeConfig()
    return min(src_w, int(round(src_h * cfg.out_ratio)))


def static_x(center: float, crop_w: int, src_w: int) -> float:
    return max(0.0, min(float(src_w - crop_w), center - crop_w / 2.0))


def median_center(samples: list[tuple[float, float]]) -> float | None:
    if not samples:
        return None
    xs = sorted(cx for _t, cx in samples)
    mid = len(xs) // 2
    return xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2.0


@dataclass(slots=True)
class SegmentCrop:
    """Jalur crop berpotongan: framing pindah saat pembicara berganti.

    Beda dari `CropPath` yang satu polinomial mulus: di sini posisi x berubah
    seketika di batas segmen. Itu memang tujuannya — pan 500 px antar dua orang
    terlihat seperti kamera mabuk, sedangkan cut terlihat seperti editor.
    """

    segments: list[tuple[float, float, float]]  # (start, end, x)
    crop_w: int
    crop_h: int
    src_w: int
    src_h: int
    fps: int = 30
    static: bool = False

    @property
    def max_x(self) -> float:
        return max(0.0, self.src_w - self.crop_w)

    @property
    def x(self) -> list[float]:
        return [s[2] for s in self.segments]

    def at(self, frame: int) -> float:
        t = frame / self.fps
        for _start, end, x in self.segments:
            if t < end:
                return max(0.0, min(self.max_x, x))
        return max(0.0, min(self.max_x, self.segments[-1][2]))

    def expression(self, var: str = "t") -> str:
        if not self.segments:
            return "0"
        if self.static:
            return str(int(round(self.segments[0][2])))
        expr = f"{self.segments[-1][2]:.2f}"
        for _start, end, x in reversed(self.segments[:-1]):
            expr = f"if(lt({var},{end:.3f}),{x:.2f},{expr})"
        return f"max(0,min({self.max_x:.0f},{expr}))"
