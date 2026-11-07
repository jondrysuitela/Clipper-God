"""Ambil video dari URL (YouTube) memakai yt-dlp.

Batasan yang disengaja:
  - hanya http(s) dan host YouTube yang diterima; bukan pengunduh umum,
  - format dipilih <=1080p mp4 (h264/aac) supaya OpenCV dan FFmpeg di hilir tidak
    berurusan dengan codec eksotis,
  - progres dilaporkan per byte, dan unduhan bisa dihentikan lewat callback.

Hak atas materi ada di tangan user. Modul ini alat; bukan izin.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

YOUTUBE_HOSTS = (
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtu.be", "www.youtu.be",
)


class DownloadError(RuntimeError):
    """URL tidak bisa diunduh. Pesan harus menyebut sebab yang bisa ditindak."""


def is_url(text: str) -> bool:
    try:
        parsed = urlparse((text or "").strip())
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def is_supported_url(text: str) -> bool:
    if not is_url(text):
        return False
    host = (urlparse(text.strip()).hostname or "").lower()
    return host in YOUTUBE_HOSTS


def probe_url(url: str) -> dict:
    """Metadata tanpa mengunduh apa pun: judul, durasi, thumbnail, uploader."""
    if not is_supported_url(url):
        raise DownloadError("hanya URL YouTube (http/https) yang didukung")
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover
        raise DownloadError("yt-dlp belum terpasang. Jalankan: pip install yt-dlp") from exc

    options = {"quiet": True, "noprogress": True, "no_warnings": True,
               "skip_download": True, "noplaylist": True}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        raise DownloadError(f"metadata gagal dibaca: {first.replace('ERROR: ', '')[:200]}") from exc
    if not info:
        raise DownloadError("tidak ada video pada URL itu")
    return {
        "id": info.get("id", ""),
        "title": info.get("title") or "Tanpa judul",
        "duration": float(info.get("duration") or 0.0),
        "thumbnail": info.get("thumbnail") or "",
        "uploader": info.get("uploader") or "",
        "webpage_url": info.get("webpage_url") or url,
    }


def download_audio(url: str, out_dir: str | Path, *,
                   progress: Callable[[float, str], None] | None = None,
                   cancel=None) -> Path:
    """Unduh audio saja — cukup untuk transkripsi, jauh lebih kecil dari video."""
    if not is_supported_url(url):
        raise DownloadError("hanya URL YouTube (http/https) yang didukung")
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover
        raise DownloadError("yt-dlp belum terpasang. Jalankan: pip install yt-dlp") from exc

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def hook(data: dict) -> None:
        if cancel is not None and cancel.cancelled:
            raise DownloadError("unduhan dibatalkan")
        if progress is None:
            return
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            progress((done / total * 100.0) if total else 0.0, "audio")
        elif data.get("status") == "finished":
            progress(100.0, "audio selesai")

    options = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(out / "audio-%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "overwrites": False,
        "progress_hooks": [hook],
    }
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise DownloadError("tidak ada audio pada URL itu")
            return _pick_file(info, Path(ydl.prepare_filename(info)))
    except DownloadError:
        raise
    except Exception as exc:  # noqa: BLE001
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        raise DownloadError(f"gagal mengunduh audio: {first.replace('ERROR: ', '')[:200]}") from exc


def _pick_file(info: dict, fallback: Path) -> Path:
    downloads = info.get("requested_downloads") or []
    for item in downloads:
        path = item.get("filepath")
        if path and Path(path).is_file():
            return Path(path)
    if fallback.is_file():
        return fallback
    merged = fallback.with_suffix(".mp4")
    if merged.is_file():
        return merged
    raise DownloadError(f"unduhan selesai tapi file tidak ditemukan: {fallback.name}")


def download(
    url: str,
    out_dir: str | Path,
    *,
    progress: Callable[[float, str], None] | None = None,
    cancel=None,
    max_height: int = 1080,
) -> Path:
    """Unduh satu video. `progress(persen, keterangan)` dipanggil berkala."""
    if not is_supported_url(url):
        raise DownloadError("hanya URL YouTube (http/https) yang didukung")

    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover - tergantung lingkungan
        raise DownloadError("yt-dlp belum terpasang. Jalankan: pip install yt-dlp") from exc

    from .render import resolve_ffmpeg

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def hook(data: dict) -> None:
        if cancel is not None and cancel.cancelled:
            raise DownloadError("unduhan dibatalkan")
        if progress is None:
            return
        if data.get("status") == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            done = data.get("downloaded_bytes") or 0
            percent = (done / total * 100.0) if total else 0.0
            speed = data.get("speed") or 0
            note = f"{percent:.0f}%"
            if speed:
                note += f" · {speed / 1048576:.1f} MB/s"
            progress(percent, note)
        elif data.get("status") == "finished":
            progress(100.0, "unduhan selesai, menggabungkan audio")

    options = {
        "format": (
            f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"best[height<={max_height}][ext=mp4]/best[height<={max_height}]/best"
        ),
        "outtmpl": str(out / "%(title).80s-%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "overwrites": False,
        "ffmpeg_location": resolve_ffmpeg(),
        "progress_hooks": [hook],
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                raise DownloadError("tidak ada video pada URL itu")
            return _pick_file(info, Path(ydl.prepare_filename(info)))
    except DownloadError:
        raise
    except Exception as exc:  # noqa: BLE001 - pesan yt-dlp panjang dan teknis
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        first = first.replace("ERROR: ", "").strip()
        raise DownloadError(f"gagal mengunduh: {first[:240]}") from exc
