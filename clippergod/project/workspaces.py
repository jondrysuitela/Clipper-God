"""Registry for independent Studio projects and their background jobs."""

from __future__ import annotations

import json
import re
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ..jobs import JobManager


@dataclass(frozen=True, slots=True)
class Workspace:
    id: str
    name: str
    root: Path


class WorkspaceRegistry:
    def __init__(
        self,
        default_root: str | Path,
        *,
        transcriber_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.default_root = Path(default_root).resolve()
        self.registry_path = self.default_root / "projects.json"
        self.projects_root = self.default_root / "projects"
        self._transcriber_factory = transcriber_factory
        self._lock = threading.RLock()
        self._workspaces: dict[str, Workspace] = {}
        self._jobs: dict[str, JobManager] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            if self.registry_path.is_file():
                try:
                    data = json.loads(self.registry_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise RuntimeError(
                        f"daftar proyek tidak bisa dibuka: {self.registry_path}: {exc}"
                    ) from exc
                entries = data.get("projects") if isinstance(data, dict) else None
                if not isinstance(entries, list):
                    raise RuntimeError("format daftar proyek tidak valid")
                for entry in entries:
                    if not isinstance(entry, dict):
                        raise RuntimeError("entri daftar proyek tidak valid")
                    project_id = entry.get("id")
                    name = entry.get("name")
                    path = entry.get("path")
                    if not (
                        isinstance(project_id, str)
                        and re.fullmatch(r"[a-f0-9]{32}", project_id)
                        and isinstance(name, str)
                        and isinstance(path, str)
                    ):
                        raise RuntimeError("identitas proyek pada daftar tidak valid")
                    self._workspaces[project_id] = Workspace(
                        project_id, name, Path(path).resolve()
                    )

            if not any(item.root == self.default_root for item in self._workspaces.values()):
                default = Workspace(
                    uuid.uuid4().hex,
                    self.default_root.name or "Studio",
                    self.default_root,
                )
                self._workspaces[default.id] = default
                self._save()

    def _save(self) -> None:
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "projects": [
                {"id": item.id, "name": item.name, "path": str(item.root)}
                for item in sorted(self._workspaces.values(), key=lambda item: item.name.casefold())
            ],
        }
        temporary = self.registry_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.registry_path)

    @property
    def default_id(self) -> str:
        with self._lock:
            return next(
                item.id for item in self._workspaces.values()
                if item.root == self.default_root
            )

    def get(self, project_id: str | None = None) -> Workspace:
        with self._lock:
            selected = project_id or self.default_id
            workspace = self._workspaces.get(selected)
            if workspace is None:
                raise KeyError("proyek tidak dikenal atau sudah dihapus")
            return workspace

    def create(self, name: str) -> Workspace:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("nama proyek harus diisi")
        clean_name = name.strip()
        if len(clean_name) > 80:
            raise ValueError("nama proyek maksimal 80 karakter")
        with self._lock:
            project_id = uuid.uuid4().hex
            root = self.projects_root / project_id
            root.mkdir(parents=True, exist_ok=False)
            workspace = Workspace(project_id, clean_name, root.resolve())
            self._workspaces[project_id] = workspace
            self._save()
            return workspace

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            workspaces = sorted(
                self._workspaces.values(), key=lambda item: item.name.casefold()
            )
            result = []
            for workspace in workspaces:
                project_file = workspace.root / "project.cgproj"
                name = workspace.name
                updated = None
                clips = 0
                if project_file.is_file():
                    try:
                        project = json.loads(project_file.read_text(encoding="utf-8"))
                        name = str(project.get("name") or name)
                        updated = project.get("modified")
                        clips = len(project.get("clips") or [])
                    except (OSError, json.JSONDecodeError):
                        updated = None
                job = self._job_manager(workspace).current()
                result.append({
                    "id": workspace.id,
                    "name": name,
                    "path": str(workspace.root),
                    "updated": updated,
                    "clips": clips,
                    "job": job or {"status": "idle"},
                })
            return result

    def jobs(self, workspace: Workspace) -> JobManager:
        with self._lock:
            return self._job_manager(workspace)

    def discard_after_cancel(self, workspace: Workspace) -> str:
        """Remove canceled-project data while preserving the shared default registry."""
        with self._lock:
            current = self._workspaces.get(workspace.id)
            if current != workspace:
                raise KeyError("proyek tidak dikenal atau sudah dihapus")
            jobs = self._jobs.get(workspace.id)
            job = jobs.current() if jobs is not None else None
            if job and job["status"] == "running":
                raise RuntimeError("job masih berjalan; folder proyek tidak dihapus")
            if workspace.root == self.default_root:
                for child in workspace.root.iterdir():
                    if child.name in {"projects.json", "projects"}:
                        continue
                    if child.is_symlink() or not child.is_dir():
                        child.unlink()
                    else:
                        shutil.rmtree(child)
            else:
                projects_root = self.projects_root.resolve()
                if (
                    workspace.root.is_symlink()
                    or workspace.root.parent != projects_root
                    or workspace.root == projects_root
                ):
                    raise RuntimeError("folder proyek berada di luar lokasi proyek yang aman")
                shutil.rmtree(workspace.root)
                self._workspaces.pop(workspace.id)
                self._jobs.pop(workspace.id, None)
                self._save()
            return self.default_id

    def _job_manager(self, workspace: Workspace) -> JobManager:
        manager = self._jobs.get(workspace.id)
        if manager is None:
            manager = JobManager(
                workspace.root,
                transcriber_factory=self._transcriber_factory,
            )
            self._jobs[workspace.id] = manager
        return manager
