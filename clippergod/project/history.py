"""Riwayat aksi: undo/redo yang benar-benar bisa diandalkan.

Prinsip:
  - Setiap perubahan state WAJIB lewat Command, supaya bisa dibalik.
  - Aksi cepat berulang (geser batas klip) digabung jadi satu langkah undo,
    bukan 60 langkah per detik.
  - Aksi massal ("terapkan ke semua klip") jadi SATU langkah undo lewat Composite.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from .schema import Clip, Project


@runtime_checkable
class Command(Protocol):
    label: str

    def apply(self, project: Project) -> None: ...
    def revert(self, project: Project) -> None: ...


# ------------------------------------------------------------------ klip


@dataclass(slots=True)
class AddClip:
    clip: Clip
    index: int | None = None
    label: str = "Tambah klip"

    def apply(self, project: Project) -> None:
        project.add_clip(self.clip)
        if self.index is not None:
            project.clips.insert(self.index, project.clips.pop())
            project.touch()

    def revert(self, project: Project) -> None:
        project.remove_clip(self.clip.id)


@dataclass(slots=True)
class RemoveClip:
    clip_id: str
    label: str = "Hapus klip"
    _clip: Clip | None = None
    _index: int = -1

    def apply(self, project: Project) -> None:
        self._index = next((i for i, c in enumerate(project.clips) if c.id == self.clip_id), -1)
        self._clip = project.remove_clip(self.clip_id)

    def revert(self, project: Project) -> None:
        if self._clip is None:
            return
        project.clips.insert(max(0, self._index), self._clip)
        project.touch()


@dataclass(slots=True)
class UpdateClip:
    clip_id: str
    field: str
    value: Any
    label: str = "Ubah klip"
    _old: Any = None
    _had_old: bool = False

    def apply(self, project: Project) -> None:
        clip = project.clip(self.clip_id)
        if clip is None:
            raise KeyError(self.clip_id)
        self._old = getattr(clip, self.field, None)
        self._had_old = True
        setattr(clip, self.field, self.value)
        project.touch()

    def revert(self, project: Project) -> None:
        clip = project.clip(self.clip_id)
        if clip is None or not self._had_old:
            return
        setattr(clip, self.field, self._old)
        project.touch()


@dataclass(slots=True)
class MoveBoundary:
    """Geser awal/akhir klip. Ini command yang paling sering dipanggil."""

    clip_id: str
    edge: str  # "start" | "end"
    value: float
    label: str = "Geser batas"
    _old: float | None = None

    def apply(self, project: Project) -> None:
        clip = project.clip(self.clip_id)
        if clip is None:
            raise KeyError(self.clip_id)
        if self.edge not in ("start", "end"):
            raise ValueError(f"edge tidak dikenal: {self.edge}")

        self._old = clip.start if self.edge == "start" else clip.end
        new_start = self.value if self.edge == "start" else clip.start
        new_end = self.value if self.edge == "end" else clip.end
        if new_end <= new_start:
            raise ValueError("batas klip akan terbalik")

        clip.start, clip.end = new_start, new_end
        project.touch()

    def revert(self, project: Project) -> None:
        clip = project.clip(self.clip_id)
        if clip is None or self._old is None:
            return
        if self.edge == "start":
            clip.start = self._old
        else:
            clip.end = self._old
        project.touch()


# ------------------------------------------------------------------ massal


@dataclass(slots=True)
class Composite:
    """Beberapa command sebagai satu langkah undo (mis. terapkan ke semua klip)."""

    commands: list[Command] = field(default_factory=list)
    label: str = "Aksi gabungan"

    def apply(self, project: Project) -> None:
        done: list[Command] = []
        try:
            for cmd in self.commands:
                cmd.apply(project)
                done.append(cmd)
        except Exception:
            for cmd in reversed(done):
                cmd.revert(project)
            raise

    def revert(self, project: Project) -> None:
        for cmd in reversed(self.commands):
            cmd.revert(project)


# ------------------------------------------------------------------ riwayat


class History:
    def __init__(
        self,
        project: Project,
        limit: int = 200,
        coalesce_ms: int = 450,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.project = project
        self.limit = limit
        self.coalesce_ms = coalesce_ms
        self._clock = clock
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._last_at: float = 0.0
        self._version = 0  # naik setiap perubahan, dipakai UI untuk tahu kapan harus render ulang

    # --- query -----------------------------------------------------
    @property
    def version(self) -> int:
        return self._version

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    @property
    def redo_label(self) -> str:
        return self._redo[-1].label if self._redo else ""

    @property
    def depth(self) -> tuple[int, int]:
        return len(self._undo), len(self._redo)

    # --- mutasi ----------------------------------------------------
    def execute(self, cmd: Command, coalesce: bool = True) -> Command:
        cmd.apply(self.project)
        now = self._clock()

        if coalesce and self._mergeable(cmd, now):
            prev = self._undo[-1]
            # prev sudah punya nilai _old asli; cukup perbarui target terbarunya.
            if isinstance(prev, MoveBoundary) and isinstance(cmd, MoveBoundary):
                prev.value = cmd.value
            elif isinstance(prev, UpdateClip) and isinstance(cmd, UpdateClip):
                prev.value = cmd.value
            self._last_at = now
            self._version += 1
            return prev

        self._undo.append(cmd)
        if len(self._undo) > self.limit:
            del self._undo[0]
        self._redo.clear()
        self._last_at = now
        self._version += 1
        return cmd

    def undo(self) -> Command | None:
        if not self._undo:
            return None
        cmd = self._undo.pop()
        cmd.revert(self.project)
        self._redo.append(cmd)
        self._last_at = 0.0
        self._version += 1
        return cmd

    def redo(self) -> Command | None:
        if not self._redo:
            return None
        cmd = self._redo.pop()
        cmd.apply(self.project)
        self._undo.append(cmd)
        self._last_at = 0.0
        self._version += 1
        return cmd

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()
        self._last_at = 0.0
        self._version += 1

    # --- internal --------------------------------------------------
    def _mergeable(self, cmd: Command, now: float) -> bool:
        """Gabungkan geseran beruntun pada batas yang sama dalam jendela waktu singkat."""
        if not self._undo:
            return False
        prev = self._undo[-1]

        if isinstance(prev, MoveBoundary) and isinstance(cmd, MoveBoundary):
            same = prev.clip_id == cmd.clip_id and prev.edge == cmd.edge
        elif isinstance(prev, UpdateClip) and isinstance(cmd, UpdateClip):
            same = prev.clip_id == cmd.clip_id and prev.field == cmd.field
        else:
            return False

        return same and (now - self._last_at) * 1000.0 <= self.coalesce_ms
