"""Import media: probe, deteksi rotasi/VFR, proxy 540p, proyek awal.

Proxy bukan hiasan: scrubbing 1080p di UI lokal membuat CPU satu core penuh,
sementara 540p cukup untuk memilih klip. Export selalu dari sumber asli.

Rotasi hanya **dicatat**, tidak diterapkan. Menerapkannya di proxy sementara
render memakai sumber akan membuat koordinat wajah dan crop berbeda sistem —
itu bug yang lebih mahal daripada manfaatnya untuk sekarang.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from ..project.schema import MediaRef, Project, fingerprint_file
from ..project.store import ProjectStore
from .render import RenderError, _run, choose_encoder, probe_video, resolve_ffmpeg

ROTATION_RE = re.compile(r"rotation of (-?\d+(?:\.\d+)?) degrees")
SIZE_RE = re.compile(r"Video:.*?(\d{2,5})x(\d{2,5})")


class MediaError(RuntimeError):
    pass


def parse_rotation(stderr: str) -> int | None:
    match = ROTATION_RE.search(stderr or "")
    return int(round(float(match.group(1)))) if match else None


def parse_size(stderr: str) -> tuple[int, int] | None:
    match = SIZE_RE.search(stderr or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


def target_size(width: int, height: int, height_px: int = 540) -> tuple[int, int]:
    """Skala proporsional; lebar dibulatkan ke angka genap (syarat H.264)."""
    if width <= 0 or height <= 0:
        return (0, 0)
    ratio = height_px / height
    out_w = max(2, int(round(width * ratio / 2.0)) * 2)
    return out_w, int(height_px)


def needs_proxy(width: int, height: int, height_px: int = 540) -> bool:
    return min(width, height) > height_px


def proxy_args(encoder: str, height_px: int) -> list[str]:
    if encoder == "h264_nvenc":
        return ["-c:v", encoder, "-preset", "p1", "-b:v", "2M"]
    if encoder == "libopenh264":
        return ["-c:v", encoder, "-b:v", "2M"]
    return ["-c:v", encoder, "-preset", "veryfast", "-b:v", "2M"]


def create_preview_proxy(
    video: str | Path,
    out_dir: str | Path,
    *,
    cancel=None,
    height_px: int = 540,
    max_width: int = 960,
) -> Path:
    """Create a browser-friendly H.264 preview while retaining source quality."""
    source = Path(video)
    if not source.is_file():
        raise MediaError(f"video tidak ditemukan: {source}")
    info = probe_video(source)
    width, height = int(info["width"]), int(info["height"])
    if width <= 0 or height <= 0:
        raise MediaError(f"dimensi video sumber tidak valid: {source}")
    scale = min(1.0, height_px / height, max_width / width)
    target_w = max(2, int(round(width * scale / 2)) * 2)
    target_h = max(2, int(round(height * scale / 2)) * 2)

    out = Path(out_dir) / "source"
    out.mkdir(parents=True, exist_ok=True)
    fingerprint = fingerprint_file(source) or source.name
    proxy = out / f"preview-{fingerprint}.mp4"
    if proxy.is_file():
        return proxy
    temporary = proxy.with_name(proxy.stem + ".tmp.mp4")
    encoder, _license = choose_encoder()
    command = [
        resolve_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", f"scale={target_w}:{target_h}:flags=fast_bilinear",
        *proxy_args(encoder, height_px),
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
        "-movflags", "+faststart", str(temporary),
    ]
    try:
        _run(command, cancel)
        temporary.replace(proxy)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return proxy


def _stderr_of(args: list[str]) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise MediaError(f"gagal menjalankan ffmpeg: {exc}") from exc
    return proc.stderr or ""


def detect_rotation(video: str | Path) -> int | None:
    """Rotasi dari metadata displaymatrix (video ponsel). None = tidak diketahui."""
    exe = resolve_ffmpeg()
    return parse_rotation(_stderr_of([exe, "-hide_banner", "-i", str(video)]))


def ffprobe_info(video: str | Path) -> dict | None:
    """VFR hanya bisa dipastikan lewat ffprobe; tanpa itu jangan menebak."""
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    cmd = [exe, "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate,codec_name",
           "-of", "json", str(video)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=60)
        data = json.loads(proc.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    streams = data.get("streams") or []
    if not streams:
        return None
    stream = streams[0]
    r_rate, avg_rate = stream.get("r_frame_rate"), stream.get("avg_frame_rate")
    return {
        "codec": stream.get("codec_name"),
        "r_frame_rate": r_rate,
        "avg_frame_rate": avg_rate,
        "vfr": bool(r_rate and avg_rate and r_rate != avg_rate),
    }


@dataclass(frozen=True, slots=True)
class ImportResult:
    source: str
    proxy: str | None
    project: str
    probe: dict
    rotation: int | None
    vfr: bool | None

    def to_dict(self) -> dict:
        return {
            "source": self.source, "proxy": self.proxy, "project": self.project,
            "probe": self.probe, "rotation": self.rotation, "vfr": self.vfr,
        }


def import_media(video: str | Path, out_dir: str | Path, *, height_px: int = 540,
                 force: bool = False, write_project: bool = True) -> ImportResult:
    video = Path(video)
    if not video.is_file():
        raise MediaError(f"video tidak ditemukan: {video}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    project_path = out / "project.cgproj"
    store = ProjectStore(project_path)
    if write_project and project_path.exists() and not force:
        raise MediaError(f"proyek sudah ada: {project_path} (pakai --force untuk menimpa)")

    info = probe_video(video)  # melempar kalau codec tidak terbaca OpenCV
    rotation = detect_rotation(video)
    ff = ffprobe_info(video)

    proxy_path: Path | None = None
    if needs_proxy(info["width"], info["height"], height_px):
        proxy_path = out / f"proxy_{height_px}p.mp4"
        encoder, _license = choose_encoder()
        w, h = target_size(info["width"], info["height"], height_px)
        cmd = [
            resolve_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(video), "-an",
            "-vf", f"scale={w}:{h}:flags=lanczos",
            *proxy_args(encoder, height_px),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(proxy_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip().splitlines()[-4:]
            raise MediaError("gagal membuat proxy:\n" + "\n".join(tail))

    if write_project:
        project = Project(
            name=video.stem or "Tanpa judul",
            media=MediaRef(
                path=str(video.resolve()),
                duration=float(info["duration"]),
                width=int(info["width"]), height=int(info["height"]),
                fps=float(info["fps"]), fingerprint=fingerprint_file(video),
            ),
            extra={
                "proxy": str(proxy_path) if proxy_path else None,
                "rotation": rotation,
                "vfr": None if ff is None else ff["vfr"],
                "imported": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )
        store.save(project)

    result = ImportResult(
        source=str(video.resolve()),
        proxy=str(proxy_path) if proxy_path else None,
        project=str(store.path),
        probe=info, rotation=rotation,
        vfr=None if ff is None else ff["vfr"],
    )
    (out / "media.json").write_text(
        json.dumps({**result.to_dict(), "ffprobe": ff}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return result
