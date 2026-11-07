"""Job bertahap: metadata/audio/transkrip -> pilih kandidat -> proses video.

Studio menjalankan setiap job di worker proses terpisah agar pembatalan dapat
menghentikan operasi yang tidak kooperatif tanpa mematikan server atau UI.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import queue
import signal
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .core.models import ClipCandidate, Word
from .params import load_or_default
from .pipeline.asr import (
    FasterWhisperTranscriber,
    SetupError,
    extract_audio,
    extract_audio_segment,
)
from .pipeline.download import (
    download as download_video,
    download_audio as download_audio_only,
    is_supported_url,
    is_url,
    probe_url,
)
from .pipeline.media import create_preview_proxy, import_media
from .pipeline.runner import OUTPUT_FORMATS, RunConfig, run, words_to_dicts
from .project.schema import fingerprint_file
from .progress import CancelToken, CancelledError, Progress

#: Peta tahap mesin ke rentang persen keseluruhan.
STAGE_RANGE = {
    "probe": (26, 28),
    "candidates": (28, 30),
    "faces": (30, 45),
    "reactions": (45, 48),
    "clip": (48, 98),
}
def _words_in_candidate_windows(
    words: list[Word], candidates: list[ClipCandidate],
) -> list[Word]:
    ranges = [(candidate.start, candidate.end) for candidate in candidates]
    return [
        word for word in words
        if any(word.end > start and word.start < end for start, end in ranges)
    ]


@dataclass
class Job:
    id: str
    out_dir: str
    status: str = "running"          # running | ready | done | failed | cancelled
    stage: str = "menyiapkan"
    percent: float | None = None
    message: str = ""
    error: str | None = None
    warning: str | None = None
    started: float = field(default_factory=time.time)
    finished: float | None = None
    stage_started: float = field(default_factory=time.time)
    clips: int = 0
    kind: str = "process"
    cancel_token: CancelToken = field(default_factory=CancelToken, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _notify: Callable[[dict[str, Any]], None] | None = field(
        default=None, repr=False, compare=False,
    )

    def update(self, stage: str | None = None, percent: float | None = None,
               message: str | None = None) -> None:
        with self._lock:
            if stage is not None:
                if stage != self.stage:
                    self.stage_started = time.time()
                self.stage = stage
            if percent is not None:
                self.percent = round(max(0.0, min(100.0, percent)), 1)
            if message is not None:
                self.message = message
        self._emit()

    def finish(self, clips: int) -> None:
        with self._lock:
            self.status = "done"
            self.stage = "selesai"
            self.percent = 100.0
            self.clips = clips
            self.message = f"{clips} klip siap"
            self.finished = time.time()
        self._emit()

    def finish_ready(self, clips: int) -> None:
        with self._lock:
            self.status = "ready"
            self.stage = "pilih_klip"
            self.percent = 100.0
            self.clips = clips
            self.message = f"{clips} kandidat siap untuk pratinjau lokal dan ASR klip terpilih"
            self.finished = time.time()
        self._emit()

    def fail(self, error: str) -> None:
        with self._lock:
            if self.cancel_token.cancelled:
                self.status = "cancelled"
                self.stage = "dibatalkan"
                self.error = None
                self.message = "proses dibatalkan"
            else:
                self.status = "failed"
                self.stage = "gagal"
                self.error = error
            self.finished = time.time()
        self._emit()

    def _emit(self) -> None:
        if self._notify is not None:
            self._notify(self.to_dict())

    def apply_snapshot(self, snapshot: dict[str, Any]) -> None:
        with self._lock:
            self.status = snapshot["status"]
            self.stage = snapshot["stage"]
            self.percent = snapshot["percent"]
            self.message = snapshot["message"]
            self.error = snapshot["error"]
            self.clips = snapshot["clips"]
            self.warning = snapshot["warning"]
            self.finished = (
                self.started + snapshot["seconds"]
                if snapshot["status"] != "running" else None
            )
            self.stage_started = time.time() - snapshot["stage_seconds"]

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "id": self.id, "status": self.status, "stage": self.stage,
                "percent": self.percent, "message": self.message,
                "error": self.error, "clips": self.clips,
                "warning": self.warning,
                "kind": self.kind,
                "seconds": round((self.finished or time.time()) - self.started, 1),
                "stage_seconds": round(time.time() - self.stage_started, 1),
            }


class JobManager:
    def __init__(self, out_dir: str | Path,
                 transcriber_factory: Callable[[str], Any] | None = None,
                 audio_extractor: Callable[[Path, Path], Path] | None = None,
                 downloader: Callable[..., Path] | None = None,
                 probe: Callable[[str], dict] | None = None,
                 audio_downloader: Callable[..., Path] | None = None) -> None:
        self.out_dir = Path(out_dir)
        self._factory = transcriber_factory or (
            lambda model: FasterWhisperTranscriber(model_size=model))
        self._extractor = audio_extractor
        self._download = downloader or download_video
        self._probe = probe or probe_url
        self._download_audio = audio_downloader or download_audio_only
        self._job: Job | None = None
        self._lock = threading.Lock()
        self._worker = None
        self._worker_queue = None
        self._use_process_worker = all(
            dependency is None for dependency in (
                transcriber_factory, audio_extractor, downloader, probe, audio_downloader,
            )
        )

    def _launch(self, job: Job, operation: str, args: tuple, thread_target) -> None:
        if not self._use_process_worker:
            threading.Thread(target=thread_target, args=(job, *args), daemon=True).start()
            return
        if self._worker is not None:
            self._worker.join(timeout=3)
            if self._worker.is_alive():
                raise RuntimeError("worker proyek sebelumnya belum berhenti")
            self._worker = None
            if self._worker_queue is not None:
                self._worker_queue.close()
                self._worker_queue = None
        context = multiprocessing.get_context("spawn")
        cancel_event = context.Event()
        progress_queue = context.Queue()
        job.cancel_token = CancelToken(cancel_event)
        worker = context.Process(
            target=_run_job_worker,
            args=(str(self.out_dir), job.id, job.kind, operation, args,
                  cancel_event, progress_queue),
            daemon=True,
        )
        try:
            worker.start()
        except Exception as exc:
            progress_queue.close()
            job.fail(f"worker gagal dimulai: {type(exc).__name__}: {exc}")
            raise RuntimeError(f"worker job tidak bisa dimulai: {exc}") from exc
        self._worker = worker
        self._worker_queue = progress_queue

    def _extract_audio(self, source: Path, destination: Path, cancel: CancelToken) -> Path:
        cancel.raise_if_cancelled()
        if self._extractor is None:
            result = extract_audio(source, destination, cancel=cancel)
        else:
            result = self._extractor(source, destination)
        cancel.raise_if_cancelled()
        return result

    def _extract_segment_audio(
        self, source: Path, destination: Path, start: float, duration: float,
        cancel: CancelToken,
    ) -> Path:
        cancel.raise_if_cancelled()
        if self._extractor is None:
            result = extract_audio_segment(
                source, destination, start, duration, cancel=cancel,
            )
        else:
            result = self._extractor(source, destination)
        cancel.raise_if_cancelled()
        return result

    @staticmethod
    def _transcribe(
        transcriber, audio: Path, language: str, cancel: CancelToken,
        on_progress: Callable[[dict], None] | None = None,
    ):
        cancel.raise_if_cancelled()
        if isinstance(transcriber, FasterWhisperTranscriber):
            return transcriber.transcribe(
                audio, language=language, cancel=cancel, on_progress=on_progress
            )
        words = transcriber.transcribe(audio, language=language)
        cancel.raise_if_cancelled()
        return words

    def current(self) -> dict[str, Any] | None:
        with self._lock:
            job = self._job
            if job is None:
                return None
            if self._worker_queue is not None:
                while True:
                    try:
                        job.apply_snapshot(self._worker_queue.get_nowait())
                    except queue.Empty:
                        break
            if self._worker is not None and not self._worker.is_alive():
                self._worker.join()
                if self._worker_queue is not None:
                    while True:
                        try:
                            job.apply_snapshot(self._worker_queue.get_nowait())
                        except queue.Empty:
                            break
                if job.status == "running":
                    job.fail(
                        f"worker berhenti tanpa hasil (exit code {self._worker.exitcode})"
                    )
                self._worker = None
                if self._worker_queue is not None:
                    self._worker_queue.close()
                    self._worker_queue = None
            return job.to_dict()

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._job
            if job is None:
                return False
            if self._worker_queue is not None:
                while True:
                    try:
                        job.apply_snapshot(self._worker_queue.get_nowait())
                    except queue.Empty:
                        break
            if self._worker is not None and not self._worker.is_alive():
                self._worker.join()
                if self._worker_queue is not None:
                    while True:
                        try:
                            job.apply_snapshot(self._worker_queue.get_nowait())
                        except queue.Empty:
                            break
                if job.status == "running":
                    job.fail(
                        f"worker berhenti tanpa hasil (exit code {self._worker.exitcode})"
                    )
                self._worker = None
                if self._worker_queue is not None:
                    self._worker_queue.close()
                    self._worker_queue = None
            if job.id != job_id or job.status != "running":
                return False
            job.cancel_token.cancel()
            job.update(stage="membatalkan", message="permintaan pembatalan diterima")
            if self._worker is not None and self._worker.is_alive():
                if os.name == "nt":
                    self._worker.terminate()
                else:
                    os.killpg(self._worker.pid, signal.SIGTERM)
                self._worker.join(timeout=3)
                if self._worker.is_alive():
                    if os.name == "nt":
                        self._worker.kill()
                    else:
                        os.killpg(self._worker.pid, signal.SIGKILL)
                    self._worker.join()
                job.fail("job dihentikan paksa")
                self._worker = None
                if self._worker_queue is not None:
                    self._worker_queue.close()
                    self._worker_queue = None
            return True

    def review_transcript(
        self, *, ollama_model: str, asr_model: str = "large-v3-turbo",
    ) -> Job:
        from .project.store import ProjectStore

        if not isinstance(ollama_model, str) or not ollama_model.strip():
            raise ValueError("nama model Ollama harus diisi")
        if not isinstance(asr_model, str) or asr_model not in {
            "small", "medium", "large-v3-turbo",
        }:
            raise ValueError("model ASR pemeriksa tidak dikenal")
        project_path = self.out_dir / "project.cgproj"
        transcript_path = self.out_dir / "transcript.json"
        if not project_path.is_file() or not transcript_path.is_file():
            raise ValueError("analisis dan transkrip belum tersedia")
        project = ProjectStore(project_path).load()
        if not project.words:
            raise ValueError("transkrip proyek kosong")
        source = str(project.media.path or "").strip()
        source_url = str(project.extra.get("source_url") or "").strip()
        source_id = str(project.extra.get("source_id") or "").strip()
        if not Path(source).is_file() and not is_url(source_url):
            raise ValueError("video/audio sumber lokal tidak tersedia untuk diperiksa")
        if source_url and not is_supported_url(source_url):
            raise ValueError("hanya URL YouTube (http/https) yang didukung")
        with self._lock:
            if self._job and self._job.status == "running":
                raise RuntimeError("masih ada job yang berjalan")
            job = Job(
                id=uuid.uuid4().hex[:8],
                out_dir=str(self.out_dir),
                kind="transcript_review",
            )
            self._job = job
        args = (source, source_url, source_id, asr_model, ollama_model.strip())
        self._launch(
            job, "review", args,
            lambda child_job, *worker_args:
                self._review_transcript_work(child_job, *worker_args),
        )
        return job

    def _review_transcript_work(
        self, job: Job, source: str, source_url: str, source_id: str,
        asr_model: str, ollama_model: str,
    ) -> None:
        from .pipeline.local_hook_ai import (
            OllamaConfig, ensure_ollama_model, review_transcript,
        )
        from .project.store import ProjectStore

        try:
            job.update("transcript_review", 5, "memuat transkrip utama")
            ollama_config = OllamaConfig(model=ollama_model, timeout=120.0)
            job.update("transcript_review", 8, "memeriksa Ollama dan model lokal")
            ensure_ollama_model(ollama_config)
            job.cancel_token.raise_if_cancelled()
            store = ProjectStore(self.out_dir / "project.cgproj")
            with store.locked():
                project = store.load()
                original_words = list(project.words)
                language = "id"
                transcript_path = self.out_dir / "transcript.json"
                if transcript_path.is_file():
                    metadata = json.loads(transcript_path.read_text(encoding="utf-8"))
                    language = str(metadata.get("language") or language)

            with tempfile.TemporaryDirectory(prefix="cg-review-") as tmp:
                audio: Path
                source_path = Path(source)
                if source_path.is_file():
                    job.update("transcript_review", 10, "menyiapkan audio untuk dengar ulang")
                    audio = self._extract_audio(
                        source_path, Path(tmp) / "audio16k.wav", job.cancel_token
                    )
                else:
                    audio_dir = self.out_dir / "source"
                    existing = (
                        sorted(audio_dir.glob(f"audio-{source_id}.*"))
                        if source_id and audio_dir.is_dir() else []
                    )
                    if existing:
                        audio = existing[0]
                    else:
                        job.update("transcript_review", 10, "mengunduh audio sumber")
                        audio = self._download_audio(
                            source_url, audio_dir, cancel=job.cancel_token
                        )
                job.cancel_token.raise_if_cancelled()
                job.update(
                    "transcript_review", 35,
                    f"dengar ulang audio dengan faster-whisper {asr_model}",
                )
                second_words = self._transcribe(
                    self._factory(asr_model), audio, language, job.cancel_token
                )
                job.cancel_token.raise_if_cancelled()
                job.update("transcript_review", 75, f"Ollama {ollama_model} memeriksa perbedaan")
                review = review_transcript(
                    original_words, second_words,
                    ollama_config,
                )
            job.cancel_token.raise_if_cancelled()
            with store.locked():
                current = store.load()
                if current.words != original_words:
                    raise RuntimeError(
                        "transkrip berubah selama pemeriksaan; hasil lama tidak disimpan"
                    )
                current.extra["transcript_review"] = {
                    "model": ollama_model,
                    "asr_model": asr_model,
                    "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "differences": review,
                    "reviewed_windows": len(review),
                }
                store.save(current)
            job.finish(len(review))
            job.update(message=(
                "Tidak ditemukan perbedaan antar-ASR."
                if not review else
                f"{len(review)} bagian berbeda; periksa saran Ollama, transkrip asli tidak diubah."
            ))
        except CancelledError:
            job.fail("pemeriksaan dibatalkan")
        except Exception as exc:  # noqa: BLE001 - kegagalan harus terlihat di Studio
            job.fail(f"{type(exc).__name__}: {exc}")

    def start(self, video: str | Path, *, target: str = "reach", limit: int = 3,
              layout: str = "fill", output_format: str = "portrait",
              render: bool = True, language: str = "id",
              model: str = "small", caption: dict[str, Any] | None = None,
              avoid_faces: bool = True, defer_video: bool = False,
              ollama_model: str | None = None) -> Job:
        source = str(video or "").strip()
        if is_url(source):
            if not is_supported_url(source):
                raise ValueError("hanya URL YouTube (http/https) yang didukung")
        elif not Path(source).is_file():
            raise ValueError(f"video tidak ditemukan: {source}")
        if target not in ("reach", "watch", "story"):
            raise ValueError("target harus reach/watch/story")
        if layout not in ("fill", "split", "three", "screenshare"):
            raise ValueError("layout tidak dikenal")
        if not isinstance(output_format, str) or output_format not in OUTPUT_FORMATS:
            raise ValueError(
                f"format output harus salah satu: {', '.join(OUTPUT_FORMATS)}"
            )
        if not 1 <= int(limit) <= 20:
            raise ValueError("limit harus 1-20")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("nama model ASR harus diisi")
        if caption is not None and not isinstance(caption, dict):
            raise ValueError("caption harus object")
        if ollama_model is not None and (
            not isinstance(ollama_model, str) or not ollama_model.strip()
        ):
            raise ValueError("nama model Ollama harus diisi atau fitur hook AI dinonaktifkan")
        from .pipeline.caption_config import from_dict as caption_from_dict
        caption_config = caption_from_dict(caption) if caption is not None else None

        with self._lock:
            if self._job and self._job.status == "running":
                raise RuntimeError("masih ada job yang berjalan")
            job = Job(id=uuid.uuid4().hex[:8], out_dir=str(self.out_dir))
            self._job = job

        args = (
            source, target, int(limit), layout, output_format, bool(render), language,
            model, caption_config, bool(avoid_faces), bool(defer_video),
            ollama_model.strip() if ollama_model else None,
        )
        self._launch(
            job, "start", args,
            lambda child_job, *worker_args: self._work(child_job, *worker_args),
        )
        return job

    def process_selected(
        self, clip_id: str, *, target: str = "reach", limit: int = 1,
        layout: str = "fill", output_format: str = "portrait", render: bool = False,
        language: str = "id", model: str = "small",
        caption: dict[str, Any] | None = None, avoid_faces: bool = True,
    ) -> Job:
        from .project.store import ProjectStore

        project_path = self.out_dir / "project.cgproj"
        if not project_path.is_file():
            raise ValueError("analisis kandidat belum tersedia")
        project = ProjectStore(project_path).load()
        clip = project.clip(clip_id)
        if clip is None:
            raise ValueError("kandidat tidak ditemukan")
        media_path = str(project.media.path or "").strip()
        source = (media_path if Path(media_path).is_file()
                  else str(project.extra.get("source_url") or media_path)).strip()
        target = str(project.extra.get("candidate_target") or target)
        if target not in ("reach", "watch", "story"):
            raise ValueError("target harus reach/watch/story")
        if layout not in ("fill", "split", "three", "screenshare"):
            raise ValueError("layout tidak dikenal")
        if not 1 <= int(limit) <= 20:
            raise ValueError("limit harus 1-20")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("nama model ASR harus diisi")
        if is_url(source) and not is_supported_url(source):
            raise ValueError("hanya URL YouTube (http/https) yang didukung")
        if not is_url(source) and not Path(source).is_file():
            raise ValueError("video sumber tidak ditemukan")
        if not isinstance(output_format, str) or output_format not in OUTPUT_FORMATS:
            raise ValueError(f"format output harus salah satu: {', '.join(OUTPUT_FORMATS)}")
        if caption is not None and not isinstance(caption, dict):
            raise ValueError("caption harus object")
        from .pipeline.caption_config import from_dict as caption_from_dict
        caption_config = caption_from_dict(caption) if caption is not None else None

        with self._lock:
            if self._job and self._job.status == "running":
                raise RuntimeError("masih ada job yang berjalan")
            job = Job(id=uuid.uuid4().hex[:8], out_dir=str(self.out_dir))
            self._job = job
        args = (
            source, clip.id, clip.start, clip.end, clip.title, target, limit, layout,
            output_format, bool(render), language, model, caption_config,
            bool(avoid_faces), project.extra.get("source_url"),
            project.extra.get("source_id"),
        )
        self._launch(
            job, "process_selected", args,
            lambda child_job, *worker_args:
                self._process_selected_work(child_job, *worker_args),
        )
        return job

    # ------------------------------------------------------------------ kerja

    def _publish_preview(self, source: str, meta: dict, words, target: str,
                         limit: int, layout: str, ollama_model: str | None = None,
                         on_ollama=None, cancel: CancelToken | None = None,
                         preview_only: bool = False) -> tuple[
                             int, list[tuple[float, float, str]], str, str | None
                         ]:
        """Tulis kandidat transkrip sebelum analisis visual atau render."""
        from .pipeline.bridge import build_project, save_project
        from .pipeline.candidates import CandidateConfig, generate
        from .pipeline.local_hook_ai import (
            MAX_RANKED_CANDIDATES, HookAnalysisError, OllamaConfig, rank_hooks,
        )

        if cancel is not None:
            cancel.raise_if_cancelled()
        max_candidates = max(limit * 4, 12)
        if ollama_model:
            max_candidates = max(limit, min(max_candidates, MAX_RANKED_CANDIDATES))
        cands = generate(words, CandidateConfig(target=target, max_candidates=max_candidates))
        candidate_ids = {id(candidate): str(index) for index, candidate in enumerate(cands)}
        scores: dict[str, Any] = {}
        warning = None
        if ollama_model and cands:
            if on_ollama:
                on_ollama()
            hook_texts = [
                (str(index), " ".join(
                    word.clean for word in words
                    if word.end > candidate.start and word.start < candidate.end
                ))
                for index, candidate in enumerate(cands)
            ]
            try:
                ranked = rank_hooks(
                    hook_texts,
                    OllamaConfig(model=ollama_model, timeout=120.0),
                    source_metadata=meta,
                )
                if cancel is not None:
                    cancel.raise_if_cancelled()
            except HookAnalysisError as exc:
                warning = (
                    f"Ollama tidak tersedia ({exc}); kandidat dipilih dengan "
                    "skor heuristik aplikasi."
                )
            else:
                by_id = {str(index): candidate for index, candidate in enumerate(cands)}
                cands = [by_id[candidate_id] for candidate_id, _analysis in ranked]
                scores = dict(ranked)
        ranked_count = len(cands)
        selected = cands[:limit]
        cands = selected
        clips = [{"start": c.start, "end": c.end, "title": c.title,
                  "score": c.score, "layout": layout, "vps": c.vps}
                 for c in cands]
        info = {"duration": float(meta.get("duration") or 0.0),
                "width": 0, "height": 0, "fps": 30.0}
        project_words = _words_in_candidate_windows(words, cands) if preview_only else words
        project = build_project(
            source, project_words, info, clips,
            name=(meta.get("title") or "YouTube")[:80],
            layout=layout,
            export={"format": meta.get("output_format", "portrait")},
            extra={"source_url": meta.get("webpage_url"),
                   "source_id": meta.get("id"), "preview": True,
                   "candidate_target": target,
                   "candidate_limit": limit,
                   "transcript_scope": "candidate_windows" if preview_only else "full_source",
                   "output_format": meta.get("output_format", "portrait")},
        )
        if cancel is not None:
            cancel.raise_if_cancelled()
        save_project(project, self.out_dir)
        from .project.store import ProjectStore
        store = ProjectStore(self.out_dir / "project.cgproj")
        with store.locked():
            saved = store.load()
            hook_ai = saved.extra.setdefault("hook_ai", {})
            selected_ids = []
            for index, candidate in enumerate(cands):
                clip = next((
                    item for item in saved.clips
                    if item.title == candidate.title
                    and abs(item.start - candidate.start) < 0.01
                    and abs(item.end - candidate.end) < 0.01
                ), None)
                if clip is None:
                    continue
                if index < len(selected):
                    selected_ids.append(clip.id)
                    if clip.status == "candidate":
                        clip.status = "approved"
                analysis = scores.get(candidate_ids[id(candidate)])
                if ollama_model and analysis:
                    hook_ai[clip.id] = {
                        "score": analysis.score,
                        "reasons": list(analysis.reasons),
                        "model": ollama_model,
                    }
                elif ollama_model:
                    hook_ai.pop(clip.id, None)
            if ollama_model:
                saved.extra["ollama_selection"] = {
                    "model": ollama_model,
                    "selected_clip_ids": selected_ids,
                    "fallback": warning is not None,
                }
            else:
                saved.extra.pop("ollama_selection", None)
            store.save(saved)

        selected_ranges = [(c.start, c.end, c.title) for c in selected]
        if ollama_model and warning is None:
            summary = (
                f"Ollama {ollama_model} merangking {ranked_count} kandidat; "
                f"{len(selected)} dipilih otomatis untuk ditinjau."
            )
        elif warning:
            summary = f"{len(cands)} kandidat; {warning}"
        else:
            summary = f"{len(cands)} kandidat hook siap"
        return len(clips), selected_ranges, summary, warning

    def _stamp_project(self, meta: dict) -> None:
        """Tandai tahap preview selesai dan simpan asal URL jika tersedia."""
        from .project.store import ProjectStore

        store = ProjectStore(self.out_dir / "project.cgproj")
        with store.locked():
            if not store.exists():
                return
            project = store.load()
            project.extra.update({"source_url": meta.get("webpage_url"),
                                  "source_id": meta.get("id")})
            project.extra.pop("preview", None)
            store.save(project)

    def _work(self, job: Job, source: str, target: str, limit: int, layout: str,
              output_format: str,
              render: bool, language: str, model: str, caption, avoid_faces: bool,
              defer_video: bool, ollama_model: str | None) -> None:
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            source_url = source if is_url(source) else None
            meta: dict | None = None
            video: Path | None = None
            audio: Path | None = None

            if source_url:
                job.cancel_token.raise_if_cancelled()
                job.update("metadata", 1, "membaca metadata")
                meta = self._probe(source_url)
                job.update("metadata", 3, f"{meta['title']} · {meta['duration']:.0f} detik")
                job.update("audio", 4, "mengunduh audio saja")

                def on_audio(percent: float, note: str) -> None:
                    job.update("audio", 4 + percent * 0.08, f"audio · {percent:.0f}%")

                audio = self._download_audio(source_url, self.out_dir / "source",
                                             progress=on_audio, cancel=job.cancel_token)
            else:
                video = Path(source)

            job.cancel_token.raise_if_cancelled()
            with tempfile.TemporaryDirectory(prefix="cg-job-") as tmp:
                if audio is None and video is not None:
                    job.update("audio_extract", 8, "mengekstrak audio dari video")
                    audio = self._extract_audio(
                        video, Path(tmp) / "audio16k.wav", job.cancel_token
                    )
                scan_model = "tiny" if defer_video else model
                scan_mode = "pemindaian hook awal" if defer_video else "transkripsi"
                job.update("model_load", 13, f"memuat ASR {scan_model} untuk {scan_mode}")
                transcriber = self._factory(scan_model)

                def on_asr_progress(event: dict) -> None:
                    if event["stage"] == "model_load":
                        cache_status = (
                            "siap di memori" if event["cached"]
                            else "memuat model (pertama kali bisa lebih lama)"
                        )
                        job.update(
                            "model_load", 13,
                            f"model {event['model']} · {cache_status}",
                        )
                        return
                    if event["stage"] == "model_ready":
                        job.update(
                            "model_load", 13,
                            f"model siap · {event['device']} · {event['compute_type']}",
                        )
                        return
                    processed = event["processed_seconds"]
                    duration = event["duration_seconds"]
                    elapsed = event["elapsed_seconds"]
                    ratio = min(1.0, processed / duration) if duration > 0 else 0.0
                    if duration > 0 and elapsed > 0 and processed > 0:
                        speed = processed / elapsed
                        remain = max(0.0, duration - processed) / speed if speed else 0.0
                        timing = (
                            f"{processed:.0f}/{duration:.0f} dtk audio · "
                            f"{speed:.1f}× waktu nyata · sisa ~{remain:.0f} dtk"
                        )
                    else:
                        timing = f"{elapsed:.0f} dtk berlalu"
                    device = event.get("device") or "perangkat otomatis"
                    compute = event.get("compute_type")
                    precision = f" · {compute}" if compute else ""
                    job.update(
                        "transcribe", 13 + 16 * ratio,
                        f"{scan_mode} {device}{precision} · {timing}",
                    )

                words = self._transcribe(
                    transcriber, audio, language, job.cancel_token,
                    on_progress=on_asr_progress,
                )
            job.cancel_token.raise_if_cancelled()
            if not words:
                raise RuntimeError("tidak ada kata yang dikenali — coba model lain atau cek audio")

            if not defer_video:
                (self.out_dir / "transcript.json").write_text(
                    json.dumps({
                        "video": str(video or source),
                        "language": language,
                        "model": model,
                        "words": words_to_dicts(words),
                    }, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            job.update("potong", 30, f"{len(words)} kata dikenali")

            if source_url and meta:
                preview_meta = dict(meta)
                preview_source = source_url
            else:
                from .pipeline.render import probe_video
                preview_meta = probe_video(video)
                preview_meta.update({"title": video.stem, "output_format": output_format})
                preview_source = str(video)
            preview_meta["output_format"] = output_format
            def on_ollama() -> None:
                job.update("hooks", 31, f"Ollama {ollama_model} menilai kandidat hook…")

            hooks, selected_ranges, selection_summary, warning = self._publish_preview(
                preview_source, preview_meta, words, target, limit, layout,
                ollama_model=ollama_model, on_ollama=on_ollama,
                cancel=job.cancel_token, preview_only=defer_video,
            )
            job.cancel_token.raise_if_cancelled()
            job.warning = warning
            job.update("hooks", 32, selection_summary)
            if defer_video:
                from .project.store import ProjectStore

                if source_url:
                    job.update(
                        "video_preview", 33,
                        "mengunduh video untuk pratinjau kandidat lokal",
                    )

                    def on_preview_video(percent: float, note: str) -> None:
                        job.update(
                            "video_preview",
                            33 + percent * 0.65,
                            f"video pratinjau · {percent:.0f}%",
                        )

                    video = self._download(
                        source_url,
                        self.out_dir / "source",
                        progress=on_preview_video,
                        cancel=job.cancel_token,
                    )
                    job.cancel_token.raise_if_cancelled()
                if video is not None:
                    job.update("video_preview", 95, "menyiapkan format video untuk preview Studio")
                    preview_proxy = create_preview_proxy(
                        video, self.out_dir, cancel=job.cancel_token,
                    )
                    store = ProjectStore(self.out_dir / "project.cgproj")
                    with store.locked():
                        project = store.load()
                        if source_url:
                            project.media.path = str(video)
                            project.media.fingerprint = fingerprint_file(video)
                        project.extra["preview_proxy"] = str(preview_proxy)
                        store.save(project)

                preview_project = ProjectStore(
                    self.out_dir / "project.cgproj"
                ).load()
                (self.out_dir / "transcript.json").write_text(
                    json.dumps({
                        "video": preview_project.media.path,
                        "language": language,
                        "model": scan_model,
                        "scope": "candidate_windows",
                        "words": words_to_dicts(preview_project.words),
                    }, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            if defer_video:
                job.finish_ready(hooks)
                job.update(message=selection_summary)
                return

            if source_url:
                job.update("video", 34, "mengunduh video untuk render")

                def on_video(percent: float, note: str) -> None:
                    job.update("video", 34 + percent * 0.26, f"video · {percent:.0f}%")

                video = self._download(source_url, self.out_dir / "source",
                                       progress=on_video, cancel=job.cancel_token)

            if video is None:
                raise RuntimeError("video sumber tidak tersedia")

            job.update("import", 61, "memeriksa video dan membuat proxy")
            import_media(video, self.out_dir, force=True, write_project=False)
            job.cancel_token.raise_if_cancelled()

            def on_progress(event: dict) -> None:
                lo, hi = STAGE_RANGE.get(event.get("stage", ""), (25, 98))
                share = (event.get("percent") or 0.0) / 100.0
                job.update(event.get("stage"), lo + (hi - lo) * share)

            cfg = RunConfig(
                out_dir=self.out_dir, target=target, limit=limit, layout=layout,
                output_format=output_format,
                render_video=render, params=load_or_default(),
                progress=Progress(emit=on_progress),
                caption=caption, avoid_faces=avoid_faces, cancel=job.cancel_token,
                candidate_ranges=selected_ranges if ollama_model else None,
            )
            summary = run(video, words, cfg, log=lambda line: job.update(message=line))
            if not summary.clips:
                raise RuntimeError("tidak ada kandidat klip yang lolos aturan batas")
            if source_url and meta:
                self._stamp_project(meta)
            job.cancel_token.raise_if_cancelled()
            job.finish(len(summary.clips))
        except SetupError as exc:
            text = str(exc)
            if "contain any stream" in text or "tidak punya" in text:
                text = "video ini tidak punya trek audio — ASR butuh suara"
            job.fail(f"SetupError: {text}")
        except CancelledError:
            job.fail("dibatalkan user")
        except Exception as exc:  # noqa: BLE001 - semua kegagalan harus sampai ke UI
            job.fail(f"{type(exc).__name__}: {exc}")

    def _process_selected_work(
        self, job: Job, source: str, clip_id: str, start: float, end: float, title: str,
        target: str, limit: int, layout: str, output_format: str,
        render_video: bool, language: str, model: str, caption, avoid_faces: bool,
        source_url: str | None, source_id: str | None,
    ) -> None:
        try:
            from .project.store import ProjectStore

            store = ProjectStore(self.out_dir / "project.cgproj")
            preview_project = store.load()
            coarse_words = list(preview_project.words)
            cached = preview_project.extra.get("accurate_transcripts", {}).get(clip_id)
            words = []
            if (
                isinstance(cached, dict)
                and cached.get("model") == model
                and cached.get("language") == language
                and cached.get("source_fingerprint") == preview_project.media.fingerprint
                and abs(float(cached.get("start", -1)) - start) < 0.001
                and abs(float(cached.get("end", -1)) - end) < 0.001
            ):
                words = [
                    word for word in coarse_words
                    if word.end > start and word.start < end
                ]
                if len(words) != int(cached.get("word_count", -1)):
                    words = []

            video = Path(source) if not is_url(source) else None
            if is_url(source):
                job.update("video", 5, "mengunduh video untuk kandidat terpilih")

                def on_video(percent: float, note: str) -> None:
                    job.update("video", 5 + percent * 0.65, f"video · {percent:.0f}%")

                video = self._download(source, self.out_dir / "source",
                                       progress=on_video, cancel=job.cancel_token)
            job.cancel_token.raise_if_cancelled()
            if video is None:
                raise RuntimeError("video sumber tidak tersedia")
            job.update("video_preview", 10, "menyiapkan format video untuk preview Studio")
            preview_proxy = create_preview_proxy(
                video, self.out_dir, cancel=job.cancel_token,
            )
            if (
                is_url(source)
                or preview_project.extra.get("preview_proxy") != str(preview_proxy)
            ):
                with store.locked():
                    project = store.load()
                    if is_url(source):
                        project.media.path = str(video)
                        project.media.fingerprint = fingerprint_file(video)
                    project.extra["preview_proxy"] = str(preview_proxy)
                    store.save(project)
            if not words:
                job.update("transcribe_clip", 12, f"menyiapkan audio klip · ASR {model}")
                with tempfile.TemporaryDirectory(prefix="cg-clip-asr-") as tmp:
                    audio = self._extract_segment_audio(
                        video, Path(tmp) / "selected.wav", start, end - start,
                        job.cancel_token,
                    )

                    def on_asr_progress(event: dict) -> None:
                        if event["stage"] == "model_load":
                            note = (
                                "memuat model" if not event["cached"]
                                else "model siap di memori"
                            )
                            job.update("transcribe_clip", 14, f"ASR {model} · {note}")
                            return
                        if event["stage"] == "model_ready":
                            job.update(
                                "transcribe_clip", 15,
                                f"ASR {model} siap · {event['device']} · "
                                f"{event['compute_type']}",
                            )
                            return
                        duration = float(event.get("duration_seconds") or end - start)
                        processed = float(event.get("processed_seconds") or 0.0)
                        ratio = min(1.0, processed / duration) if duration > 0 else 0.0
                        job.update(
                            "transcribe_clip", 15 + 15 * ratio,
                            f"transkripsi akurat klip · {processed:.0f}/"
                            f"{duration:.0f} dtk audio",
                        )

                    segment_words = self._transcribe(
                        self._factory(model), audio, language, job.cancel_token,
                        on_progress=on_asr_progress,
                    )
                words = []
                duration = end - start
                for word in segment_words:
                    word_start = max(0.0, min(duration, word.start))
                    word_end = max(word_start, min(duration, word.end))
                    if word_end > word_start:
                        words.append(Word(
                            text=word.text,
                            start=start + word_start,
                            end=start + word_end,
                            prob=word.prob,
                            speaker=word.speaker,
                        ))
                if not words:
                    raise RuntimeError(
                        "ASR tidak menemukan kata pada klip terpilih; "
                        "coba model lain atau periksa audionya"
                    )

            def on_progress(event: dict) -> None:
                lo, hi = STAGE_RANGE.get(event.get("stage", ""), (25, 98))
                share = (event.get("percent") or 0.0) / 100.0
                job.update(event.get("stage"), 30 + (lo + (hi - lo) * share) * 0.70)

            cfg = RunConfig(
                out_dir=self.out_dir, target=target, limit=limit, layout=layout,
                output_format=output_format, render_video=render_video,
                params=load_or_default(), progress=Progress(emit=on_progress),
                caption=caption, avoid_faces=avoid_faces, cancel=job.cancel_token,
                candidate_ranges=[(start, end, title)],
                preserve_unselected_clips=True,
            )
            summary = run(video, words, cfg, log=lambda line: job.update(message=line))
            if not summary.clips:
                raise RuntimeError("kandidat terpilih tidak bisa diproses")
            with store.locked():
                project = store.load()
                project.words = sorted(
                    [
                        word for word in coarse_words
                        if word.end <= start or word.start >= end
                    ] + words,
                    key=lambda word: (word.start, word.end),
                )
                accurate = project.extra.setdefault("accurate_transcripts", {})
                accurate[clip_id] = {
                    "model": model,
                    "language": language,
                    "source_fingerprint": project.media.fingerprint,
                    "start": start,
                    "end": end,
                    "word_count": len(words),
                }
                store.save(project)

            (self.out_dir / "transcript.json").write_text(
                json.dumps({
                    "video": str(video),
                    "language": language,
                    "model": model,
                    "scope": "candidate_windows",
                    "words": words_to_dicts(project.words),
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._stamp_project({
                "webpage_url": source_url,
                "id": source_id,
            })
            job.cancel_token.raise_if_cancelled()
            job.finish(len(summary.clips))
        except CancelledError:
            job.fail("dibatalkan user")
        except SetupError as exc:
            text = str(exc)
            if "contain any stream" in text or "tidak punya" in text:
                text = "video ini tidak punya trek audio — ASR butuh suara"
            job.fail(f"SetupError: {text}")
        except Exception as exc:  # noqa: BLE001 - kegagalan harus terlihat di Studio
            job.fail(f"{type(exc).__name__}: {exc}")


def _run_job_worker(
    out_dir: str, job_id: str, kind: str, operation: str, args: tuple,
    cancel_event, progress_queue,
) -> None:
    if os.name != "nt":
        os.setsid()
    kill_job_handle = _attach_worker_children_to_job()
    manager = JobManager(out_dir)
    job = Job(
        id=job_id,
        out_dir=out_dir,
        kind=kind,
        cancel_token=CancelToken(cancel_event),
        _notify=progress_queue.put,
    )
    manager._job = job
    try:
        if operation == "start":
            manager._work(job, *args)
        elif operation == "review":
            manager._review_transcript_work(job, *args)
        elif operation == "process_selected":
            manager._process_selected_work(job, *args)
        else:
            raise ValueError(f"operasi worker tidak dikenal: {operation}")
    except Exception as exc:
        job.fail(f"{type(exc).__name__}: {exc}")
    finally:
        progress_queue.put(job.to_dict())
        if kill_job_handle is not None:
            import ctypes
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(kill_job_handle)


def _attach_worker_children_to_job():
    if os.name != "nt":
        return None

    import ctypes
    from ctypes import wintypes

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, wintypes.INT, ctypes.c_void_p, wintypes.DWORD,
    ]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimitInformation()
    limits.BasicLimitInformation.LimitFlags = 0x2000
    if not kernel32.SetInformationJobObject(
        handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
    ):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(handle)
        raise ctypes.WinError(error)
    if not kernel32.AssignProcessToJobObject(handle, kernel32.GetCurrentProcess()):
        error = ctypes.get_last_error()
        kernel32.CloseHandle(handle)
        raise ctypes.WinError(error)
    return handle
