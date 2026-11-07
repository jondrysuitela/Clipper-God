"""Penyimpanan proyek: simpan atomik, autosave, dan pemulihan setelah crash.

Kenapa repot soal atomik: kalau aplikasi mati saat menulis, file proyek tidak
boleh jadi setengah jadi. Kita tulis ke file sementara, fsync, lalu rename —
operasi rename bersifat atomik di NTFS maupun ext4.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .schema import Project


_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def _path_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve()))
    with _LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


def _sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


@dataclass(slots=True)
class SaveResult:
    path: str
    size: int
    ms: float
    skipped: bool = False
    autosave: bool = False

    def __str__(self) -> str:
        tag = "autosave" if self.autosave else "simpan"
        if self.skipped:
            return f"{tag}: tidak ada perubahan"
        return f"{tag}: {self.size / 1024:.1f} KB dalam {self.ms:.0f} ms"


class ProjectStore:
    """Satu file proyek + satu file autosave pendamping."""

    SUFFIX = ".cgproj"
    AUTOSAVE_SUFFIX = ".autosave"

    def __init__(self, path: str | Path) -> None:
        p = Path(path)
        self.path = p if p.suffix == self.SUFFIX else p.with_suffix(self.SUFFIX)
        self._last_hash: str = ""
        self._lock = _path_lock(self.path)

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Lock project read-modify-write operations across store instances."""
        with self._lock:
            yield

    # ------------------------------------------------------------ path
    @property
    def autosave_path(self) -> Path:
        return self.path.with_name(self.path.name + self.AUTOSAVE_SUFFIX)

    def exists(self) -> bool:
        return self.path.is_file()

    def has_autosave(self) -> bool:
        return self.autosave_path.is_file()

    # ------------------------------------------------------------ simpan
    def save(self, project: Project, atomic: bool = True) -> SaveResult:
        with self.locked():
            t0 = time.perf_counter()
            project.touch()
            data = json.dumps(project.to_dict(), ensure_ascii=False, indent=1).encode("utf-8")
            self.path.parent.mkdir(parents=True, exist_ok=True)

            if atomic:
                tmp = self.path.with_name(self.path.name + ".tmp")
                with open(tmp, "wb") as fh:
                    fh.write(data)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, self.path)
            else:
                self.path.write_bytes(data)

            self._last_hash = _sha(data)
            self.clear_autosave()
            return SaveResult(str(self.path), len(data), (time.perf_counter() - t0) * 1000)

    def autosave(self, project: Project, force: bool = False) -> SaveResult:
        """Tulis autosave hanya kalau isinya berubah.

        Mencegah disk menulis 200 kali per menit saat user cuma menggeser kursor.
        """
        with self.locked():
            t0 = time.perf_counter()
            data = json.dumps(project.to_dict(), ensure_ascii=False, indent=1).encode("utf-8")
            digest = _sha(data)

            if not force and digest == self._last_hash and self.autosave_path.is_file():
                return SaveResult(str(self.autosave_path), len(data), 0.0,
                                  skipped=True, autosave=True)

            self.autosave_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.autosave_path.with_name(self.autosave_path.name + ".tmp")
            with open(tmp, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.autosave_path)
            self._last_hash = digest
            return SaveResult(str(self.autosave_path), len(data),
                              (time.perf_counter() - t0) * 1000, autosave=True)

    # ------------------------------------------------------------ muat
    def load(self, path: str | Path | None = None) -> Project:
        with self.locked():
            target = Path(path) if path else self.path
            if not target.is_file():
                raise FileNotFoundError(f"proyek tidak ditemukan: {target}")
            raw = target.read_bytes()
            self._last_hash = _sha(raw)
            return Project.from_dict(json.loads(raw.decode("utf-8")))

    def peek(self) -> dict:
        """Baca metadata tanpa memuat seluruh transkrip (untuk daftar proyek terakhir)."""
        with self.locked():
            raw = self.path.read_bytes()
            d = json.loads(raw.decode("utf-8"))
            return {
                "name": d.get("name", ""),
                "modified": d.get("modified", ""),
                "clips": len(d.get("clips", [])),
                "duration": d.get("media", {}).get("duration", 0.0),
            }

    # ------------------------------------------------------------ pulihkan
    def recover(self) -> Project | None:
        """Kembalikan proyek dari autosave kalau lebih baru daripada file utama."""
        with self.locked():
            if not self.has_autosave():
                return None

            if self.exists() and self.autosave_path.stat().st_mtime <= self.path.stat().st_mtime:
                return None

            try:
                raw = self.autosave_path.read_bytes()
                project = Project.from_dict(json.loads(raw.decode("utf-8")))
            except (OSError, ValueError, KeyError):
                return None

            project.extra["recovered_from_autosave"] = True
            self._last_hash = _sha(raw)
            return project

    def clear_autosave(self) -> None:
        for p in (self.autosave_path,
                  self.autosave_path.with_name(self.autosave_path.name + ".tmp")):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass

    def discard(self) -> None:
        """Hapus file proyek dan autosave (dipakai saat proyek baru dibatalkan)."""
        for p in (self.path, self.autosave_path):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
