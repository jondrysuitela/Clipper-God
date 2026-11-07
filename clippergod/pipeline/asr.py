"""Transkripsi: antarmuka + backend faster-whisper + backend skrip untuk uji.

Backend asli dimuat lambat (lazy) supaya aplikasi tetap bisa jalan — dan tetap
bisa diuji — di mesin yang belum mengunduh model.
"""

from __future__ import annotations

import math
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from ..core.models import Word
from ..progress import CancelToken, CancelledError


class SetupError(RuntimeError):
    """Model/dependensi belum siap. Pesan harus menyebut cara memperbaikinya."""


class Transcriber(Protocol):
    def transcribe(self, audio_path: str | Path, language: str = "id") -> list[Word]: ...


@dataclass(slots=True)
class ScriptedTranscriber:
    """Transkrip tetap untuk test dan demo tanpa model."""

    words: list[Word]
    language: str = "id"

    def transcribe(self, audio_path: str | Path, language: str = "id") -> list[Word]:
        return list(self.words)


class FasterWhisperTranscriber:
    """faster-whisper (CTranslate2). GPU kalau ada, CPU kalau tidak.

    Model `large-v3-turbo` ~1,6 GB. `small` ~460 MB — dipakai sebagai fallback CPU.
    """

    def __init__(
        self,
        model_size: str = "large-v3-turbo",
        device: str = "auto",
        compute_type: str = "auto",
        download_root: str | None = None,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.download_root = download_root
        self._model = None
        self.resolved_device: str | None = None
        self.resolved_compute_type: str | None = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover
            raise SetupError(
                "faster-whisper belum terpasang. Jalankan: pip install faster-whisper"
            ) from exc

        device = self.device
        compute = self.compute_type
        if device == "auto":
            try:
                import ctranslate2
                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                device = "cpu"
        if compute == "auto":
            compute = "float16" if device == "cuda" else "int8"

        self.resolved_device = device
        self.resolved_compute_type = compute
        try:
            self._model = WhisperModel(
                self.model_size, device=device, compute_type=compute,
                download_root=self.download_root,
            )
        except Exception as exc:  # pragma: no cover - tergantung jaringan/model
            raise SetupError(
                f"model '{self.model_size}' tidak bisa dimuat ({exc}). "
                "Pastikan model sudah diunduh atau mesin terhubung internet sekali saja."
            ) from exc
        return self._model

    def transcribe(
        self, audio_path: str | Path, language: str = "id",
        cancel: CancelToken | None = None,
        on_progress: Callable[[dict], None] | None = None,
    ) -> list[Word]:
        if on_progress is not None:
            on_progress({
                "stage": "model_load",
                "cached": self._model is not None,
                "model": self.model_size,
            })
        model = self._load()
        if on_progress is not None:
            on_progress({
                "stage": "model_ready",
                "model": self.model_size,
                "device": self.resolved_device or self.device,
                "compute_type": self.resolved_compute_type or self.compute_type,
            })
        if cancel is not None:
            cancel.raise_if_cancelled()
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            word_timestamps=True,
            vad_filter=True,
            beam_size=5,
        )
        started = time.monotonic()
        duration = float(getattr(info, "duration", 0.0) or 0.0)
        words: list[Word] = []
        processed = 0.0
        for seg in segments:
            if cancel is not None:
                cancel.raise_if_cancelled()
            processed = max(processed, float(getattr(seg, "end", 0.0) or 0.0))
            for w in (seg.words or []):
                text = (w.word or "").strip()
                if not text:
                    continue
                words.append(Word(text=text, start=float(w.start),
                                  end=float(w.end), prob=float(getattr(w, "probability", 1.0))))
            if on_progress is not None:
                elapsed = time.monotonic() - started
                on_progress({
                    "stage": "transcribe",
                    "processed_seconds": processed,
                    "duration_seconds": duration,
                    "elapsed_seconds": elapsed,
                    "device": self.resolved_device or self.device,
                    "compute_type": self.resolved_compute_type or self.compute_type,
                })
        return words


def extract_audio(
    src: str | Path, dst: str | Path, sample_rate: int = 16000,
    cancel: CancelToken | None = None,
) -> Path:
    """Ambil audio mono 16 kHz — format yang diharapkan Whisper."""
    from .render import resolve_ffmpeg

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        resolve_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src), "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-c:a", "pcm_s16le", str(dst),
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors="replace",
    )
    while True:
        if cancel is not None and cancel.cancelled:
            proc.terminate()
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
            raise CancelledError("ekstraksi audio dibatalkan user")
        try:
            _stdout, stderr = proc.communicate(timeout=0.15)
            break
        except subprocess.TimeoutExpired:
            continue
    if proc.returncode != 0:
        raise SetupError("gagal mengekstrak audio: " + (stderr or "").strip()[-300:])
    return dst


def extract_audio_segment(
    src: str | Path, dst: str | Path, start: float, duration: float,
    sample_rate: int = 16000, cancel: CancelToken | None = None,
) -> Path:
    """Ekstrak hanya rentang audio terpilih untuk transkripsi lanjutan."""
    if not math.isfinite(start) or start < 0:
        raise ValueError("waktu awal audio harus angka >= 0")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("durasi audio harus angka > 0")
    if cancel is not None:
        cancel.raise_if_cancelled()
    from .render import resolve_ffmpeg

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        resolve_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{duration:.3f}",
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(dst),
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors="replace",
    )
    while True:
        if cancel is not None and cancel.cancelled:
            proc.terminate()
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
            raise CancelledError("ekstraksi audio klip dibatalkan user")
        try:
            _stdout, stderr = proc.communicate(timeout=0.15)
            break
        except subprocess.TimeoutExpired:
            continue
    if proc.returncode != 0:
        raise SetupError("gagal mengekstrak audio klip: " + (stderr or "").strip()[-300:])
    return dst
