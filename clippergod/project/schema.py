"""Skema data proyek ClipperGod (.cgproj).

Aturan yang dipegang:
  1. Video sumber TIDAK PERNAH diubah. Proyek hanya menyimpan catatan di atasnya.
  2. Semua yang terlihat di UI harus bisa direkonstruksi dari file ini.
  3. Versi skema disimpan eksplisit supaya file lama tetap bisa dibuka.
"""

from __future__ import annotations

import copy
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.models import Word

SCHEMA_VERSION = 1
APP_VERSION = "0.2.0"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def new_id(prefix: str = "c") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def fingerprint_file(path: str | Path, sample: int = 1 << 20) -> str:
    """Sidik jari murah: ukuran + 1 MB pertama. Dipakai untuk relink media."""
    p = Path(path)
    try:
        size = p.stat().st_size
        with p.open("rb") as fh:
            head = fh.read(sample)
    except OSError:
        return ""
    h = hashlib.sha1()
    h.update(str(size).encode())
    h.update(head)
    return h.hexdigest()[:16]


# ------------------------------------------------------------------ media


@dataclass(slots=True)
class MediaRef:
    path: str
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 30.0
    fingerprint: str = ""

    @property
    def exists(self) -> bool:
        return Path(self.path).is_file()

    @property
    def is_vertical(self) -> bool:
        return self.height > self.width > 0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "duration": round(self.duration, 3),
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MediaRef":
        return cls(
            path=d.get("path", ""),
            duration=float(d.get("duration", 0.0)),
            width=int(d.get("width", 0)),
            height=int(d.get("height", 0)),
            fps=float(d.get("fps", 30.0)),
            fingerprint=d.get("fingerprint", ""),
        )


# ------------------------------------------------------------------ klip


CLIP_STATUS = ("candidate", "approved", "rejected")


@dataclass(slots=True)
class Clip:
    """Satu kandidat klip. Semua field yang bisa diubah user ada di sini."""

    start: float
    end: float
    id: str = field(default_factory=lambda: new_id("clip"))
    title: str = ""
    score: float | None = None
    status: str = "candidate"
    layout: str = "fill"
    hook_variant: str = "A"
    caption_style: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)
    video: str = ""                 # path klip hasil render (untuk preview di UI)
    vps: dict[str, Any] | None = None      # skor rinci + alasan
    metrics: dict[str, Any] | None = None  # lufs/true peak/cut rate/ssim/bitrate

    def __post_init__(self) -> None:
        if self.status not in CLIP_STATUS:
            raise ValueError(f"status tidak dikenal: {self.status}")
        if self.end <= self.start:
            raise ValueError(f"klip terbalik: {self.start} -> {self.end}")

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "title": self.title,
            "score": self.score,
            "status": self.status,
            "layout": self.layout,
            "hook_variant": self.hook_variant,
            "caption_style": self.caption_style,
            "notes": list(self.notes),
            "video": self.video,
            "vps": self.vps,
            "metrics": self.metrics,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Clip":
        return cls(
            start=float(d["start"]),
            end=float(d["end"]),
            id=d.get("id") or new_id("clip"),
            title=d.get("title", ""),
            score=d.get("score"),
            status=d.get("status", "candidate"),
            layout=d.get("layout", "fill"),
            hook_variant=d.get("hook_variant", "A"),
            caption_style=d.get("caption_style"),
            notes=list(d.get("notes", [])),
            video=str(d.get("video", "")),
            vps=d.get("vps"),
            metrics=d.get("metrics"),
        )


# ------------------------------------------------------------------ proyek


DEFAULT_SETTINGS: dict[str, Any] = {
    "target_platform": "tiktok",
    "caption_preset": "punch",
    "caption_highlight": "#FFD84D",
    "font_size": 96,
    "avoid_faces": True,
    "safe_zone": True,
    "export": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "bitrate_mbps": 10,
        "lufs": -14.0,
        "true_peak": -1.0,
    },
}


def _word_to_dict(w: Word) -> dict:
    return {"t": w.text, "s": round(w.start, 3), "e": round(w.end, 3),
            "p": round(w.prob, 3), "sp": w.speaker}


def _word_from_dict(d: dict) -> Word:
    return Word(text=d["t"], start=float(d["s"]), end=float(d["e"]),
                prob=float(d.get("p", 1.0)), speaker=d.get("sp"))


@dataclass(slots=True)
class Project:
    name: str
    media: MediaRef
    id: str = field(default_factory=lambda: new_id("proj"))
    words: list[Word] = field(default_factory=list)
    clips: list[Clip] = field(default_factory=list)
    speakers: dict[str, dict] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    created: str = field(default_factory=now_iso)
    modified: str = field(default_factory=now_iso)
    schema_version: int = SCHEMA_VERSION
    app_version: str = APP_VERSION
    extra: dict[str, Any] = field(default_factory=dict)

    # --- koleksi ---------------------------------------------------
    def clip(self, clip_id: str) -> Clip | None:
        return next((c for c in self.clips if c.id == clip_id), None)

    def add_clip(self, clip: Clip) -> Clip:
        if any(c.id == clip.id for c in self.clips):
            raise ValueError(f"id klip duplikat: {clip.id}")
        self.clips.append(clip)
        self.touch()
        return clip

    def remove_clip(self, clip_id: str) -> Clip | None:
        for i, c in enumerate(self.clips):
            if c.id == clip_id:
                self.touch()
                return self.clips.pop(i)
        return None

    def replace_clip(self, clip: Clip) -> None:
        for i, c in enumerate(self.clips):
            if c.id == clip.id:
                self.clips[i] = clip
                self.touch()
                return
        raise KeyError(clip.id)

    def touch(self) -> None:
        self.modified = now_iso()

    # --- relink ----------------------------------------------------
    def relink(self, new_path: str | Path) -> bool:
        """Arahkan ulang ke file media baru. True kalau sidik jari cocok.

        Sidik jari ASLI dipertahankan sebagai identitas proyek — kalau ditimpa,
        relink berikutnya kehilangan pembanding dan selalu dianggap cocok.
        """
        expected = self.media.fingerprint
        ref = MediaRef(
            path=str(new_path),
            duration=self.media.duration,
            width=self.media.width,
            height=self.media.height,
            fps=self.media.fps,
            fingerprint=fingerprint_file(new_path),
        )
        match = bool(expected) and ref.fingerprint == expected
        if not expected:
            expected = ref.fingerprint
        self.media = MediaRef(
            path=ref.path, duration=ref.duration, width=ref.width,
            height=ref.height, fps=ref.fps, fingerprint=expected,
        )
        self.touch()
        return match

    # --- serialisasi ----------------------------------------------
    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "app_version": self.app_version,
            "id": self.id,
            "name": self.name,
            "created": self.created,
            "modified": self.modified,
            "media": self.media.to_dict(),
            "words": [_word_to_dict(w) for w in self.words],
            "clips": [c.to_dict() for c in self.clips],
            "speakers": self.speakers,
            "settings": self.settings,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        version = int(d.get("schema_version", 0))
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"proyek dibuat versi lebih baru ({version} > {SCHEMA_VERSION}). "
                "Perbarui aplikasi dulu."
            )
        return cls(
            name=d.get("name", "Tanpa judul"),
            media=MediaRef.from_dict(d.get("media", {})),
            id=d.get("id") or new_id("proj"),
            words=[_word_from_dict(w) for w in d.get("words", [])],
            clips=[Clip.from_dict(c) for c in d.get("clips", [])],
            speakers=dict(d.get("speakers", {})),
            settings=dict(d.get("settings", {})),
            created=d.get("created", now_iso()),
            modified=d.get("modified", now_iso()),
            schema_version=SCHEMA_VERSION,
            app_version=d.get("app_version", APP_VERSION),
            extra=dict(d.get("extra", {})),
        )

    @classmethod
    def new(cls, name: str, media_path: str | Path, **media_info: Any) -> "Project":
        """Proyek baru dari satu file video."""
        info = {
            "duration": media_info.get("duration", 0.0),
            "width": media_info.get("width", 0),
            "height": media_info.get("height", 0),
            "fps": media_info.get("fps", 30.0),
        }
        ref = MediaRef(
            path=str(media_path),
            fingerprint=fingerprint_file(media_path),
            **info,
        )
        return cls(name=name, media=ref, settings=copy.deepcopy(DEFAULT_SETTINGS))
