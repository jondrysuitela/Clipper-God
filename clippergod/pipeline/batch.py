"""Batch queue: banyak video diproses berurutan, tahan gangguan, bisa dilanjutkan.

Prinsip yang dipegang sama seperti `run()`: setiap perubahan status ditulis ke disk
sebelum pekerjaan berikutnya dimulai. Jadi kalau proses mati di tengah antrean,
putaran berikutnya melanjutkan dari job yang belum selesai — bukan mengulang dari nol.

Manifest (JSON):

    {
      "jobs": [
        {"id": "ep01", "video": "a.mp4", "transcript": "a.json", "target": "reach", "limit": 3},
        {"id": "ep02", "video": "b.mp4", "transcript": "b.json",
         "layout": "split", "format": "landscape"}
      ]
    }

Status disimpan di `<out>/queue.json`:
    pending -> running -> done | failed
Job `failed` dicoba ulang pada putaran berikutnya selama `attempts < max_attempts`.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .runner import RunConfig, _write_json, load_transcript, run

DONE = "done"
FAILED = "failed"
RUNNING = "running"
PENDING = "pending"


@dataclass(slots=True)
class BatchJob:
    id: str
    video: str
    transcript: str
    target: str = "watch"
    limit: int = 3
    layout: str = "fill"
    output_format: str = "portrait"
    language: str = "id"
    caption: str | None = None
    brand: str | None = None


@dataclass(slots=True)
class JobState:
    id: str
    status: str = PENDING
    attempts: int = 0
    out_dir: str = ""
    clips: int = 0
    skipped: int = 0
    seconds: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "attempts": self.attempts,
            "out_dir": self.out_dir,
            "clips": self.clips,
            "skipped": self.skipped,
            "seconds": round(self.seconds, 2),
            **({"error": self.error} if self.error else {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobState":
        return cls(
            id=str(data["id"]),
            status=str(data.get("status", PENDING)),
            attempts=int(data.get("attempts", 0)),
            out_dir=str(data.get("out_dir", "")),
            clips=int(data.get("clips", 0)),
            skipped=int(data.get("skipped", 0)),
            seconds=float(data.get("seconds", 0.0)),
            error=data.get("error"),
        )


@dataclass(slots=True)
class BatchReport:
    out_dir: Path
    states: list[JobState] = field(default_factory=list)
    already_done: int = 0

    @property
    def done(self) -> int:
        return sum(1 for s in self.states if s.status == DONE)

    @property
    def failed(self) -> int:
        return sum(1 for s in self.states if s.status == FAILED)

    @property
    def clips(self) -> int:
        return sum(s.clips for s in self.states)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "count": len(self.states),
            "done": self.done,
            "failed": self.failed,
            "clips": self.clips,
            "jobs": [s.to_dict() for s in self.states],
        }


class ManifestError(ValueError):
    pass


def load_manifest(path: str | Path) -> list[BatchJob]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items = raw.get("jobs") if isinstance(raw, dict) else raw
    if not isinstance(items, list) or not items:
        raise ManifestError("manifest harus berisi 'jobs' yang tidak kosong")

    jobs: list[BatchJob] = []
    seen: set[str] = set()
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ManifestError(f"job #{i} bukan object")
        job_id = str(item.get("id") or f"job{i:02d}")
        if job_id in seen:
            raise ManifestError(f"id duplikat: {job_id}")
        seen.add(job_id)
        for required in ("video", "transcript"):
            if not item.get(required):
                raise ManifestError(f"job '{job_id}' tidak punya '{required}'")
        jobs.append(
            BatchJob(
                id=job_id,
                video=str(item["video"]),
                transcript=str(item["transcript"]),
                target=str(item.get("target", "watch")),
                limit=int(item.get("limit", 3)),
                layout=str(item.get("layout", "fill")),
                output_format=str(item.get("format", "portrait")),
                language=str(item.get("language", "id")),
                caption=str(item["caption"]) if item.get("caption") else None,
                brand=str(item["brand"]) if item.get("brand") else None,
            )
        )
    return jobs


def _load_states(path: Path, jobs: list[BatchJob]) -> dict[str, JobState]:
    states: dict[str, JobState] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}  # queue rusak: mulai dari status bersih, jangan crash
        for item in raw.get("jobs", []):
            try:
                state = JobState.from_dict(item)
            except (KeyError, TypeError, ValueError):
                continue
            states[state.id] = state
    # job yang belum punya state (pertama kali, atau queue rusak) dimulai dari pending
    for job in jobs:
        states.setdefault(job.id, JobState(id=job.id))
    return states


def run_batch(
    manifest: str | Path,
    out_dir: str | Path,
    *,
    force: bool = False,
    max_attempts: int = 2,
    stop_on_error: bool = False,
    scanner: Callable[..., Any] | None = None,
    renderer: Callable[..., Any] | None = None,
    render_video: bool = True,
    log: Callable[[str], None] = print,
) -> BatchReport:
    jobs = load_manifest(manifest)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    queue_path = out / "queue.json"
    states = _load_states(queue_path, jobs)
    report = BatchReport(out_dir=out, states=[states[j.id] for j in jobs],
                         already_done=sum(1 for s in states.values() if s.status == DONE))

    log(f"antrean: {len(jobs)} job, {report.already_done} sudah selesai")

    for job in jobs:
        state = states[job.id]
        if state.status == DONE and not force:
            log(f"  [selesai] {job.id} — dilewati")
            continue
        if state.status == FAILED and state.attempts >= max_attempts and not force:
            log(f"  [gagal {state.attempts}x] {job.id} — tidak dicoba lagi")
            continue

        state.status = RUNNING
        state.error = None
        state.attempts += 1
        _write_json(queue_path, report.to_dict())

        started = time.perf_counter()
        job_out = out / job.id
        state.out_dir = str(job_out)
        log(f"  [jalan] {job.id} (percobaan {state.attempts}) ...")

        try:
            words = load_transcript(job.transcript)
            caption_cfg = None
            logo = None
            if job.brand:
                from .brand import from_file as brand_from_file
                profile = brand_from_file(job.brand)
                caption_cfg = profile.caption
                logo = profile.logo
            if job.caption:
                from .caption_config import from_file as caption_from_file
                caption_cfg = caption_from_file(job.caption)
            cfg = RunConfig(
                out_dir=job_out,
                target=job.target,
                limit=job.limit,
                language=job.language,
                layout=job.layout,
                output_format=job.output_format,
                render_video=render_video,
                force=force,
                caption=caption_cfg,
                logo=logo,
            )
            summary = run(job.video, words, cfg, scanner=scanner,
                          renderer=renderer, log=log)
            state.clips = len(summary.clips)
            state.skipped = summary.skipped
            state.status = DONE
            log(f"  [selesai] {job.id}: {state.clips} klip")
        except Exception as exc:  # noqa: BLE001 - satu job gagal tidak mematikan antrean
            state.status = FAILED
            state.error = f"{type(exc).__name__}: {exc}"
            log(f"  [gagal] {job.id}: {state.error}")
        finally:
            state.seconds = time.perf_counter() - started
            _write_json(queue_path, report.to_dict())

        if state.status == FAILED and stop_on_error:
            log("berhenti karena --stop-on-error")
            break

    _write_json(queue_path, report.to_dict())
    return report
