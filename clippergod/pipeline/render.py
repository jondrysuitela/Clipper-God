"""Render klip ke kanvas output pilihan: dua pass FFmpeg.

Pass 1  crop (mengikuti jalur wajah) + scale/pad ke ukuran output + fps
Pass 2  bakar caption ASS + ambil audio asli + normalisasi loudness

Kenapa dua pass, bukan satu filter graph raksasa (riset 02 §10.4):
  - tiap pass bisa diulang sendiri kalau gagal,
  - mudah di-debug,
  - pass 1 bisa di-cache saat user cuma mengganti gaya caption.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import cv2

from .layout import PanelCrop
from ..progress import CancelledError


class RenderError(RuntimeError):
    pass


def resolve_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover - tergantung lingkungan
        raise RenderError(
            "FFmpeg tidak ditemukan. Pasang ffmpeg di PATH atau `pip install imageio-ffmpeg`."
        ) from exc


#: Urutan encoder: hardware dulu, lalu build LGPL. x264 (GPL) hanya kalau diizinkan.
ENCODER_ORDER = ("h264_nvenc", "libopenh264", "libx264")
GPL_ENCODERS = frozenset({"libx264", "libx264rgb"})


@lru_cache(maxsize=1)
def available_encoders(ffmpeg: str | None = None) -> frozenset[str]:
    exe = ffmpeg or resolve_ffmpeg()
    try:
        proc = subprocess.run(
            [exe, "-hide_banner", "-encoders"],
            capture_output=True, text=True, errors="replace", timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    names: set[str] = set()
    for line in (proc.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("V"):
            names.add(parts[1])
    return frozenset(names)


@lru_cache(maxsize=8)
def encoder_works(name: str, ffmpeg: str | None = None) -> bool:
    """Encode 1 frame betulan: nama ada di daftar belum tentu ada GPU-nya."""
    exe = ffmpeg or resolve_ffmpeg()
    cmd = [
        exe, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
        "-frames:v", "1", "-c:v", name, "-f", "null", "-",
    ]
    try:
        return subprocess.run(cmd, capture_output=True, timeout=25).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def choose_encoder(allow_gpl: bool | None = None) -> tuple[str, str]:
    """Pilih (encoder, lisensi).

    Build tanpa NVENC/OpenH264 tapi punya x264: dipakai dengan peringatan, karena
    menolak render total lebih buruk daripada risiko lisensi yang dilaporkan.
    Set `CLIPPERGOD_STRICT_LICENSE=1` untuk melarang x264 sepenuhnya.
    """
    if allow_gpl is None:
        allow_gpl = os.environ.get("CLIPPERGOD_ALLOW_GPL") == "1"
    strict = os.environ.get("CLIPPERGOD_STRICT_LICENSE") == "1"
    have = available_encoders()

    for name in ENCODER_ORDER:
        if name not in have or not encoder_works(name):
            continue
        if name in GPL_ENCODERS and strict and not allow_gpl:
            raise RenderError(
                "Build FFmpeg ini hanya punya x264 (GPL), dan CLIPPERGOD_STRICT_LICENSE=1. "
                "Pakai build dengan h264_nvenc/libopenh264."
            )
        return name, ("GPL" if name in GPL_ENCODERS else "LGPL")

    raise RenderError(
        "Tidak ada encoder H.264 yang bisa dipakai. Pasang FFmpeg dengan "
        "h264_nvenc atau libopenh264 (atau libx264 bila lisensi GPL diterima)."
    )


def video_args(spec: "RenderSpec", encoder: str, bitrate_mbps: float | None = None) -> list[str]:
    """Rate control per encoder: target 10 Mbps, plafon 12 Mbps (spec §5)."""
    br = f"{bitrate_mbps or spec.bitrate_mbps:g}M"
    mx = f"{spec.max_bitrate_mbps:g}M"
    buf = f"{spec.max_bitrate_mbps * 2:g}M"
    if encoder == "h264_nvenc":
        return ["-c:v", encoder, "-preset", spec.nvenc_preset, "-rc", "vbr",
                "-b:v", br, "-maxrate", mx, "-bufsize", buf, "-pix_fmt", "yuv420p"]
    if encoder == "libopenh264":
        return ["-c:v", encoder, "-b:v", br, "-maxrate", mx, "-bufsize", buf,
                "-pix_fmt", "yuv420p"]
    return ["-c:v", encoder, "-preset", spec.preset, "-b:v", br, "-maxrate", mx,
            "-bufsize", buf, "-pix_fmt", "yuv420p"]


def escape_filter_path(path: str | Path) -> str:
    """Path aman untuk argumen filter FFmpeg di Windows maupun POSIX."""
    p = str(path).replace("\\", "/")
    return p.replace(":", r"\:").replace("'", r"\'")


@lru_cache(maxsize=4)
def _crop_accepts_eval(ffmpeg: str | None = None) -> bool:
    """Apakah build FFmpeg ini masih punya opsi `crop.eval`?"""
    exe = ffmpeg or resolve_ffmpeg()
    try:
        proc = subprocess.run(
            [exe, "-hide_banner", "-h", "filter=crop"],
            capture_output=True, text=True, errors="replace", timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return True  # lebih aman: perilaku lama butuh eval=frame
    return " eval " in (proc.stdout or "")


@dataclass(frozen=True, slots=True)
class LogoSpec:
    """Logo yang ditempel di pass 2, setelah caption dibakar."""

    path: str
    position: str = "br"          # tl | tr | bl | br | custom
    width: int | None = None      # piksel; None = pakai width_ratio
    width_ratio: float = 0.16
    margin: int = 36
    opacity: float = 1.0
    x: int = 0
    y: int = 0

    def pixel_width(self, out_w: int) -> int:
        return int(self.width or round(out_w * self.width_ratio))

    def overlay_xy(self) -> tuple[str, str]:
        """Ekspresi overlay; memakai main_w/overlay_w supaya tidak perlu tahu ukuran logo."""
        m = self.margin
        if self.position == "tl":
            return str(m), str(m)
        if self.position == "tr":
            return f"main_w-overlay_w-{m}", str(m)
        if self.position == "bl":
            return str(m), f"main_h-overlay_h-{m}"
        if self.position == "br":
            return f"main_w-overlay_w-{m}", f"main_h-overlay_h-{m}"
        return str(self.x), str(self.y)


@dataclass(slots=True)
class RenderSpec:
    src: str
    dst: str
    start: float
    duration: float

    out_w: int = 1080
    out_h: int = 1920
    fps: int = 30

    crop_w: int | None = None
    crop_h: int | None = None
    crop_x_expr: str | None = None
    crop_y: int = 0

    ass_path: str | None = None
    fonts_dir: str | None = None

    audio: bool = True
    loudnorm: bool = True
    crf: int = 20
    preset: str = "medium"

    # encoder & bitrate (spec §5: 1080x1920, 8 Mbps min, 10-12 disarankan)
    bitrate_mbps: float = 10.0
    max_bitrate_mbps: float = 12.0
    encoder: str | None = None
    nvenc_preset: str = "p5"
    allow_gpl: bool | None = None

    extra_vf: list[str] = field(default_factory=list)

    # Layout: "fill" = satu crop mengikuti wajah, "split" = panel bertumpuk.
    layout: str = "fill"
    panels: list[PanelCrop] = field(default_factory=list)
    logo: LogoSpec | None = None


def build_crop_filter(spec: RenderSpec) -> str | None:
    if not spec.crop_w or not spec.crop_h:
        return None
    x = spec.crop_x_expr or "0"
    base = f"crop=w={spec.crop_w}:h={spec.crop_h}:x='{x}':y={spec.crop_y}"
    # FFmpeg <=7 default-nya eval=init: posisi dibekukan di frame pertama dan pan
    # tidak pernah terjadi. FFmpeg 8+ menghapus opsi itu (selalu per-frame) dan
    # menolak `eval=frame` sebagai "Option not found". Jadi: probe dulu.
    if _crop_accepts_eval():
        base += ":eval=frame"
    return base


def build_video_filter(spec: RenderSpec) -> str:
    parts: list[str] = []
    crop = build_crop_filter(spec)
    if crop:
        parts.append(crop)
    if spec.crop_w and spec.crop_h:
        parts.append(
            f"scale={spec.out_w}:{spec.out_h}:force_original_aspect_ratio=decrease:"
            f"flags=lanczos,pad={spec.out_w}:{spec.out_h}:(ow-iw)/2:(oh-ih)/2:"
            "color=black,setsar=1"
        )
    else:
        parts.append(f"scale={spec.out_w}:{spec.out_h}:flags=lanczos")
    parts.append(f"fps={spec.fps}")
    parts.extend(spec.extra_vf)
    return ",".join(parts)


def build_pass1(spec: RenderSpec, out_path: str | Path, encoder: str | None = None) -> list[str]:
    encoder = encoder or choose_encoder(spec.allow_gpl)[0]
    if spec.layout == "split" and spec.panels:
        # Dua crop dari satu input, ditumpuk, lalu dipad sampai 1080x1920.
        # Tanpa `pad`, hasil vstack lebih pendek dari kanvas dan caption ASS
        # (yang ditulis untuk 1920) akan meleset ke atas.
        parts: list[str] = []
        for i, panel in enumerate(spec.panels):
            if panel.fit:
                # Layar tidak boleh dipotong: muat utuh, sisanya letterbox.
                parts.append(
                    f"[0:v]crop=w={panel.crop_w}:h={panel.crop_h}"
                    f":x={int(round(panel.x))}:y={panel.y},"
                    f"scale={spec.out_w}:{panel.out_h}:force_original_aspect_ratio=decrease,"
                    f"pad={spec.out_w}:{panel.out_h}:(ow-iw)/2:(oh-ih)/2:color=black,"
                    f"setsar=1[v{i}]"
                )
            else:
                parts.append(
                    f"[0:v]crop=w={panel.crop_w}:h={panel.crop_h}"
                    f":x={int(round(panel.x))}:y={panel.y},"
                    f"scale={spec.out_w}:{panel.out_h}:"
                    "force_original_aspect_ratio=decrease:flags=lanczos,"
                    f"pad={spec.out_w}:{panel.out_h}:(ow-iw)/2:(oh-ih)/2:"
                    f"color=black,setsar=1[v{i}]"
                )
        labels = "".join(f"[v{i}]" for i in range(len(spec.panels)))
        parts.append(f"{labels}vstack=inputs={len(spec.panels)}[stack]")
        stacked = sum(p.out_h for p in spec.panels)
        tail = "[stack]"
        if stacked != spec.out_h:
            parts.append(f"[stack]pad={spec.out_w}:{spec.out_h}:0:0:color=black[pad]")
            tail = "[pad]"
        parts.append(f"{tail}fps={spec.fps}[vout]")
        return [
            resolve_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{spec.start:.3f}", "-t", f"{spec.duration:.3f}",
            "-i", spec.src,
            "-an",
            "-filter_complex", ";".join(parts),
            "-map", "[vout]",
            *video_args(spec, encoder, spec.bitrate_mbps * 2),
            str(out_path),
        ]

    return [
        resolve_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{spec.start:.3f}", "-t", f"{spec.duration:.3f}",
        "-i", spec.src,
        "-an",
        "-vf", build_video_filter(spec),
        *video_args(spec, encoder, spec.bitrate_mbps * 2),
        str(out_path),
    ]


def _ass_filter(spec: RenderSpec) -> str:
    assert spec.ass_path
    base = f"filename='{escape_filter_path(spec.ass_path)}'"
    if spec.fonts_dir:
        base += f":fontsdir='{escape_filter_path(spec.fonts_dir)}'"
    return f"ass={base}"


def build_pass2(spec: RenderSpec, cropped: str | Path, out_path: str | Path,
                encoder: str | None = None) -> list[str]:
    encoder = encoder or choose_encoder(spec.allow_gpl)[0]
    inputs: list[str] = ["-i", str(cropped)]
    if spec.audio:
        inputs += ["-ss", f"{spec.start:.3f}", "-t", f"{spec.duration:.3f}",
                   "-i", spec.src]
    logo_index = None
    if spec.logo is not None:
        inputs += ["-i", spec.logo.path]
        logo_index = 2 if spec.audio else 1

    cmd = [resolve_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *inputs]

    # Caption dibakar dulu, lalu logo ditempel di atasnya. Urutan ini penting:
    # logo tidak boleh tertimpa subtitle, dan posisinya dihitung dari kanvas akhir.
    filters: list[str] = []
    label = "[0:v]"
    if spec.ass_path:
        filters.append(f"{label}{_ass_filter(spec)}[vcap]")
        label = "[vcap]"
    if spec.logo is not None and logo_index is not None:
        width = spec.logo.pixel_width(spec.out_w)
        filters.append(
            f"[{logo_index}:v]scale={width}:-1:flags=lanczos,format=rgba,"
            f"colorchannelmixer=aa={spec.logo.opacity:.2f}[logo]"
        )
        x, y = spec.logo.overlay_xy()
        filters.append(f"{label}[logo]overlay=x={x}:y={y}[vout]")
        label = "[vout]"

    if filters:
        cmd += ["-filter_complex", ";".join(filters), "-map", label]
    else:
        cmd += ["-map", "0:v:0"]

    if spec.audio:
        cmd += ["-map", "1:a:0?"]
        cmd += ["-c:a", "aac", "-b:a", "320k", "-ar", "48000"]
        if spec.loudnorm:
            cmd += ["-af", "loudnorm=I=-14:TP=-1:LRA=11"]
    cmd += [
        *video_args(spec, encoder),
        "-movflags", "+faststart",
        str(out_path),
    ]
    return cmd


# ---------------------------------------------------------------- eksekusi


@dataclass(slots=True)
class RenderResult:
    path: str
    width: int
    height: int
    duration: float
    size_mb: float
    passes: int
    encoder: str = ""
    license: str = ""

    def __str__(self) -> str:
        return (f"{Path(self.path).name}: {self.width}x{self.height} "
                f"{self.duration:.2f}s {self.size_mb:.1f} MB")


def probe_video(path: str | Path) -> dict:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RenderError(f"tidak bisa membaca hasil render: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    info = {
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": round(fps, 3),
        "frames": frames,
        "duration": round(frames / fps, 3) if fps else 0.0,
        "size_mb": round(Path(path).stat().st_size / 1048576, 2),
    }
    cap.release()
    return info


def _run(cmd: list[str], cancel=None) -> None:
    """Jalankan FFmpeg sambil memantau token batal (render bisa berjam-jam)."""
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors="replace",
    )
    try:
        while proc.poll() is None:
            if cancel is not None and cancel.cancelled:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise CancelledError("render dibatalkan user")
            time.sleep(0.15)
    finally:
        if proc.poll() is None:
            proc.kill()
    _out, err = proc.communicate()
    if proc.returncode != 0:
        tail = (err or "").strip().splitlines()[-6:]
        raise RenderError("FFmpeg gagal:\n" + "\n".join(tail))


def needs_pass2(spec: RenderSpec) -> bool:
    """Pass 2 perlu jalan kalau ada yang harus ditambahkan di atas video pass 1."""
    return bool(spec.ass_path or spec.audio or spec.logo)


def render(spec: RenderSpec, keep_intermediate: bool = False, cancel=None) -> RenderResult:
    """Jalankan pass 1 lalu pass 2. Mengembalikan metadata hasil."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="clippergod-"))
    cropped = tmp_dir / "pass1.mp4"
    encoder, license_name = choose_encoder(spec.allow_gpl)
    try:
        _run(build_pass1(spec, cropped, encoder), cancel)
        if needs_pass2(spec):
            _run(build_pass2(spec, cropped, spec.dst, encoder), cancel)
            passes = 2
        else:
            shutil.move(str(cropped), spec.dst)
            passes = 1
    finally:
        if not keep_intermediate:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    info = probe_video(spec.dst)
    return RenderResult(
        path=spec.dst,
        width=info["width"],
        height=info["height"],
        duration=info["duration"],
        size_mb=info["size_mb"],
        passes=passes,
        encoder=encoder,
        license=license_name,
    )
