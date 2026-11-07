"""Jembatan: hasil `run()` bisa dibuka sebagai proyek `.cgproj`.

Tanpa ini ada dua model data paralel — `clip.json` untuk mesin dan `.cgproj`
untuk UI — dan UI harus menebak mana yang benar. Sekarang satu putaran
menuliskan keduanya, dan `.cgproj` memuat hal yang sama (kata, klip, speaker,
setelan export).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.models import Word
from ..project.schema import DEFAULT_SETTINGS, Clip, MediaRef, Project, fingerprint_file
from ..project.store import ProjectStore


def build_project(
    video: str | Path,
    words: list[Word],
    info: dict[str, Any],
    clips: list[dict[str, Any]],
    *,
    name: str | None = None,
    layout: str = "fill",
    speakers: dict[str, Any] | None = None,
    export: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> Project:
    """Rakit `Project` dari artefak satu putaran. Tidak menyentuh file video."""
    settings = dict(DEFAULT_SETTINGS)
    if export:
        settings["export"] = {**DEFAULT_SETTINGS["export"], **export}

    media = MediaRef(
        path=str(video),
        duration=float(info.get("duration") or 0.0),
        width=int(info.get("width") or 0),
        height=int(info.get("height") or 0),
        fps=float(info.get("fps") or 30.0),
        fingerprint=fingerprint_file(video),
    )
    project = Project(
        name=name or Path(video).stem or "Tanpa judul",
        media=media,
        words=list(words),
        speakers=speakers or {},
        settings=settings,
        extra=dict(extra or {}),
    )
    for item in clips:
        start = float(item["start"])
        end = float(item["end"])
        if end <= start:
            continue  # klip rusak tidak boleh menggagalkan seluruh proyek
        project.add_clip(Clip(
            start=start,
            end=end,
            title=str(item.get("title") or ""),
            score=(item.get("vps_final") or {}).get("score", item.get("score")),
            status="candidate",
            layout=str(item.get("layout") or layout),
            video=str(item.get("video") or ""),
            vps=item.get("vps_final") or item.get("vps"),
            metrics=item.get("metrics"),
        ))
    return project


def save_project(project: Project, out_dir: str | Path, *,
                 preserve_unmatched: bool = False) -> Path:
    """Simpan atomik ke `<out>/project.cgproj` (lihat ProjectStore)."""
    store = ProjectStore(Path(out_dir) / "project.cgproj")
    with store.locked():
        if store.exists():
            previous = store.load()
            same_media = (
                previous.media.fingerprint == project.media.fingerprint
                if previous.media.fingerprint and project.media.fingerprint
                else previous.media.path == project.media.path
            )
            if same_media or preserve_unmatched:
                new_extra = dict(project.extra)
                project.extra = {**previous.extra, **new_extra}
                if "preview" not in new_extra:
                    project.extra.pop("preview", None)
                existing: dict[tuple[float, float, str], list[Clip]] = {}
                for clip in previous.clips:
                    key = (round(clip.start, 3), round(clip.end, 3), clip.title)
                    existing.setdefault(key, []).append(clip)
                used_ids: set[str] = set()
                for clip in project.clips:
                    key = (round(clip.start, 3), round(clip.end, 3), clip.title)
                    matches = existing.get(key)
                    while matches and matches[0].id in used_ids:
                        matches.pop(0)
                    old = matches.pop(0) if matches else None
                    if old is None and preserve_unmatched:
                        old = next((
                            candidate for candidate in previous.clips
                            if candidate.id not in used_ids
                            and candidate.title == clip.title
                            and abs(candidate.start - clip.start) <= max(5.0, candidate.duration * 0.2)
                            and abs(candidate.end - clip.end) <= max(5.0, candidate.duration * 0.2)
                        ), None)
                    if old is not None:
                        used_ids.add(old.id)
                        clip.id = old.id
                        clip.status = old.status
                        clip.notes = list(old.notes)
                if preserve_unmatched:
                    project.clips.extend(
                        clip for clip in previous.clips
                        if clip.id not in used_ids
                    )
        store.save(project)
    return store.path
