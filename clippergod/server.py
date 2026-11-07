"""Studio lokal: proyek-proyek independen disajikan lewat HTTP di 127.0.0.1.

Tanpa dependensi baru (stdlib) dan tanpa pengiriman video ke layanan luar.
File dari browser diterima lewat loopback dan disimpan dalam folder proyek.

Endpoint:
    GET  /                     halaman studio
    GET  /api/project          isi .cgproj (atau {"empty": true})
    GET  /api/projects         daftar proyek terdaftar
    POST /api/projects         buat proyek terisolasi
    GET  /api/clip?id=         file mp4 klip
    GET  /api/source           video sumber lokal untuk preview
    POST /api/clips            ubah status klip
    POST /api/jobs             analisis audio dan siapkan kandidat
    POST /api/jobs/process     proses kandidat terpilih
    POST /api/transcript/review dengar ulang ASR dan tinjau perbedaan lokal
    POST /api/jobs/cancel      batalkan job yang sedang berjalan
    GET  /api/jobs/current     status job berjalan/terakhir
    POST /api/upload           salin video dari browser ke folder proyek
    POST /api/pick             dialog pilih file native (Windows)
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import uuid
from urllib.parse import parse_qs, urlparse

from .jobs import JobManager
from .project.store import ProjectStore
from .project.workspaces import WorkspaceRegistry

UI_FILE = Path(__file__).resolve().parents[1] / "ui" / "ClipperGod-Prototipe-Interaktif.html"
ASSETS = UI_FILE.parent / "assets"
STATUSES = ("candidate", "approved", "rejected")
VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}


def _local_source_file(root: Path, project) -> Path | None:
    source = Path(project.media.path)
    if source.is_file():
        return source
    source_id = str(project.extra.get("source_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", source_id):
        return None
    source_dir = root / "source"
    if not source_dir.is_dir():
        return None
    matches = [
        path for path in source_dir.glob(f"*-{source_id}.*")
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    ]
    return max(matches, key=lambda path: path.stat().st_mtime) if matches else None

PICK_SCRIPT = (
    "import tkinter as tk\n"
    "from tkinter import filedialog\n"
    "root = tk.Tk(); root.withdraw(); root.attributes('-topmost', True)\n"
    "path = filedialog.askopenfilename(title='Pilih video', filetypes=["
    "('Video', '*.mp4 *.mov *.mkv *.webm *.m4v *.avi'), ('Semua file', '*.*')])\n"
    "print(path or '')\n"
)
PICK_POWERSHELL = (
    "Add-Type -AssemblyName System.Windows.Forms; "
    "$dialog = New-Object System.Windows.Forms.OpenFileDialog; "
    "$dialog.Title = 'Pilih video'; "
    "$dialog.Filter = 'Video|*.mp4;*.mov;*.mkv;*.webm;*.m4v;*.avi|Semua file|*.*'; "
    "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
    "{ Write-Output $dialog.FileName }"
)
WINDOWS_CAPTION_FONTS = (
    "Arial",
    "Arial Black",
    "Calibri",
    "Cambria",
    "Candara",
    "Comic Sans MS",
    "Consolas",
    "Constantia",
    "Corbel",
    "Franklin Gothic Medium",
    "Georgia",
    "Impact",
    "Segoe UI",
    "Tahoma",
    "Times New Roman",
    "Trebuchet MS",
    "Verdana",
)


def installed_caption_fonts() -> list[str]:
    """Return supported caption families present in the Windows Fonts registry."""
    if sys.platform != "win32":
        return list(WINDOWS_CAPTION_FONTS)

    import winreg

    keys = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
    )
    installed: set[str] = set()
    style_suffix = re.compile(
        r"\s+(?:bold\s+italic|italic\s+bold|semibold|semilight|demibold|"
        r"bold|italic|oblique|regular|light|thin)$",
        re.IGNORECASE,
    )
    for hive, path in keys:
        try:
            with winreg.OpenKey(hive, path) as key:
                for index in range(winreg.QueryInfoKey(key)[1]):
                    name, _value, _kind = winreg.EnumValue(key, index)
                    family = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
                    installed.add(family.casefold())
                    family = style_suffix.sub("", family).strip()
                    installed.add(family.casefold())
        except FileNotFoundError:
            continue
    return [
        family for family in WINDOWS_CAPTION_FONTS
        if family.casefold() in installed
    ]


def health_info() -> dict:
    """Status nyata mesin, bukan klaim di UI."""
    import importlib.util
    import shutil as _shutil

    ffmpeg, encoders, encoder, license_name = "", [], "", ""
    try:
        from .pipeline.render import available_encoders, choose_encoder, resolve_ffmpeg
        ffmpeg = resolve_ffmpeg()
        encoders = sorted(e for e in available_encoders() if "264" in e)
        encoder, license_name = choose_encoder()
    except Exception:  # noqa: BLE001 - status mesin tidak boleh menggagalkan halaman
        pass

    face = ""
    try:
        from .pipeline.faces import yunet_model_path
        face = str(yunet_model_path() or "")
    except Exception:  # noqa: BLE001
        pass

    return {
        "ffmpeg": ffmpeg,
        "encoder": encoder,
        "encoder_license": license_name,
        "encoders": encoders,
        "faster_whisper": importlib.util.find_spec("faster_whisper") is not None,
        "face_model": face,
        "ffprobe": bool(_shutil.which("ffprobe")),
    }


def pick_file(timeout: int = 300) -> str | None:
    """Buka dialog file native. None kalau dibatalkan atau GUI tidak tersedia."""
    if getattr(sys, "frozen", False):
        try:
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-STA", "-Command", PICK_POWERSHELL],
                capture_output=True, text=True, timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"dialog file tidak tersedia: {exc}") from exc
        if proc.returncode:
            raise RuntimeError(
                f"dialog file gagal dibuka: {(proc.stderr or '').strip()}"
            )
        return (proc.stdout or "").strip() or None
    try:
        proc = subprocess.run([sys.executable, "-c", PICK_SCRIPT],
                              capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return (proc.stdout or "").strip() or None


def resolve_target(target: str | Path) -> tuple[Path, Path]:
    """(folder_proyek, path .cgproj) dari folder atau file .cgproj."""
    path = Path(target)
    if path.suffix == ".cgproj":
        return path.parent.resolve(), path.resolve()
    folder = path.resolve()
    return folder, folder / "project.cgproj"


def make_handler(target: str | Path, transcriber_factory=None) -> type[BaseHTTPRequestHandler]:
    root, _ = resolve_target(target)
    workspaces = WorkspaceRegistry(
        root, transcriber_factory=transcriber_factory
    )

    class Handler(BaseHTTPRequestHandler):
        server_version = "ClipperGodStudio/0.2"

        def log_message(self, *_args) -> None:
            return

        # ---------------------------------------------------------- util

        def _json(self, payload: dict, code: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _file(self, path: Path, ctype: str, range_ok: bool = False) -> None:
            size = path.stat().st_size
            start, end, status = 0, size - 1, 200
            header = self.headers.get("Range") if range_ok else None
            if header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
                if match is None or size == 0:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                left, right = match.groups()
                if left:
                    start = int(left)
                    end = int(right) if right else size - 1
                elif right:
                    suffix = int(right)
                    if suffix == 0:
                        start = size
                    else:
                        start = max(0, size - suffix)
                if start >= size or end < start:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                end = min(end, size - 1)
                status = 206

            length = end - start + 1 if size else 0
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with path.open("rb") as media:
                media.seek(start)
                remaining = length
                while remaining:
                    chunk = media.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def _body(self) -> dict:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                raise ValueError(
                    f"body harus JSON untuk {urlparse(self.path).path} "
                    f"(Content-Type: {content_type or 'tidak ada'})"
                )
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw or b"{}")
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"body bukan JSON untuk {urlparse(self.path).path}"
                ) from exc
            if not isinstance(data, dict):
                raise ValueError("body harus object JSON")
            return data

        # ---------------------------------------------------------- GET

        def do_GET(self) -> None:
            parsed = urlparse(self.path)

            if parsed.path in ("/", "/index.html"):
                if not UI_FILE.is_file():
                    self._json({"error": "ui/ClipperGod-Prototipe-Interaktif.html tidak ditemukan"}, 500)
                    return
                self._file(UI_FILE, "text/html; charset=utf-8")
                return

            if parsed.path == "/studio.js":
                script = UI_FILE.parent / "studio.js"
                if not script.is_file():
                    self._json({"error": "ui/studio.js tidak ditemukan"}, 404)
                    return
                self._file(script, "text/javascript; charset=utf-8")
                return

            if parsed.path.startswith("/assets/"):
                name = parsed.path[len("/assets/"):]
                target = (ASSETS / name).resolve()
                if ASSETS.resolve() not in target.parents or not target.is_file():
                    self._json({"error": "aset tidak ditemukan"}, 404)
                    return
                ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                self._file(target, ctype)
                return

            if parsed.path == "/api/health":
                self._json(health_info())
                return

            if parsed.path == "/api/fonts":
                try:
                    self._json({"fonts": installed_caption_fonts()})
                except OSError as exc:
                    self._json({"error": f"daftar font Windows tidak bisa dibaca: {exc}"}, 500)
                return

            if parsed.path == "/api/projects":
                self._json({
                    "default_id": workspaces.default_id,
                    "projects": workspaces.list(),
                })
                return

            try:
                workspace = workspaces.get(
                    self.headers.get("X-ClipperGod-Project")
                    or parse_qs(parsed.query).get("project_id", [None])[0]
                )
            except KeyError as exc:
                self._json({"error": str(exc.args[0])}, 404)
                return
            root = workspace.root
            project_file = root / "project.cgproj"
            store = ProjectStore(project_file)
            jobs = workspaces.jobs(workspace)

            if parsed.path == "/api/probe":
                url = parse_qs(parsed.query).get("url", [""])[0]
                try:
                    from .pipeline.download import probe_url
                    self._json(probe_url(url))
                except Exception as exc:  # noqa: BLE001 - pesan ke UI
                    self._json({"error": str(exc)}, 400)
                return

            if parsed.path == "/api/project":
                with store.locked():
                    if not project_file.is_file():
                        self._json({"empty": True, "out_dir": str(root),
                                    "name": workspace.name})
                        return
                    try:
                        project = store.load()
                    except (OSError, ValueError, KeyError) as exc:
                        self._json({"error": f"proyek tidak bisa dibuka: {exc}"}, 400)
                        return
                payload = project.to_dict()
                payload["media"]["local_available"] = (
                    _local_source_file(root, project) is not None
                )
                self._json({**payload, "empty": False, "out_dir": str(root)})
                return

            if parsed.path == "/api/jobs/current":
                self._json(jobs.current() or {"status": "idle"})
                return

            if parsed.path == "/api/source":
                if not project_file.is_file():
                    self._json({"error": "belum ada proyek"}, 404)
                    return
                with store.locked():
                    project = store.load()
                source = _local_source_file(root, project)
                if source is None:
                    self._json({"error": "video sumber lokal tidak tersedia"}, 404)
                    return
                ctype = mimetypes.guess_type(source.name)[0] or "video/mp4"
                self._file(source, ctype, range_ok=True)
                return

            if parsed.path == "/api/clip":
                clip_id = parse_qs(parsed.query).get("id", [""])[0]
                if not project_file.is_file():
                    self._json({"error": "belum ada proyek"}, 404)
                    return
                with store.locked():
                    clip = store.load().clip(clip_id)
                if clip is None:
                    self._json({"error": "klip tidak dikenal"}, 404)
                    return
                target_file = Path(clip.video).resolve()
                if not clip.video or root not in target_file.parents or not target_file.is_file():
                    self._json({"error": "file klip tidak tersedia"}, 404)
                    return
                self._file(target_file, "video/mp4", range_ok=True)
                return

            self._json({"error": "tidak ditemukan"}, 404)

        # ---------------------------------------------------------- POST

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"

            if path == "/api/projects":
                try:
                    data = self._body()
                    workspace = workspaces.create(data.get("name", ""))
                except ValueError as exc:
                    self._json({"error": str(exc)}, 400)
                    return
                except OSError as exc:
                    self._json({"error": f"folder proyek tidak bisa dibuat: {exc}"}, 500)
                    return
                self._json({
                    "id": workspace.id,
                    "name": workspace.name,
                    "path": str(workspace.root),
                }, 201)
                return

            try:
                workspace = workspaces.get(
                    self.headers.get("X-ClipperGod-Project")
                )
            except KeyError as exc:
                self._json({"error": str(exc.args[0])}, 404)
                return
            root = workspace.root
            project_file = root / "project.cgproj"
            store = ProjectStore(project_file)
            jobs = workspaces.jobs(workspace)

            if path == "/api/upload":
                content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type != "application/octet-stream":
                    self._json({"error": "tipe konten upload tidak valid"}, 415)
                    return
                origin = self.headers.get("Origin")
                if origin and origin != f"http://{self.headers.get('Host', '')}":
                    self._json({"error": "upload hanya dapat dilakukan dari Studio lokal"}, 403)
                    return
                filename = parse_qs(parsed.query).get("filename", [""])[0]
                filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
                suffix = Path(filename).suffix.lower()
                if suffix not in {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}:
                    self._json({"error": "format video tidak didukung"}, 400)
                    return
                try:
                    length = int(self.headers.get("Content-Length", ""))
                except ValueError:
                    self._json({"error": "ukuran upload tidak valid"}, 400)
                    return
                if length <= 0:
                    self._json({"error": "file kosong"}, 400)
                    return

                stem = re.sub(r"[^\w.-]+", "_", Path(filename).stem, flags=re.UNICODE)
                stem = (stem.strip("._") or "source")[:100]
                destination_dir = root / "source"
                destination = destination_dir / f"{stem}-{uuid.uuid4().hex[:8]}{suffix}"
                partial = destination.with_name(destination.name + ".part")
                remaining = length
                try:
                    destination_dir.mkdir(parents=True, exist_ok=True)
                    with partial.open("xb") as output:
                        while remaining:
                            chunk = self.rfile.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise OSError("upload terputus sebelum selesai")
                            output.write(chunk)
                            remaining -= len(chunk)
                    os.replace(partial, destination)
                except OSError as exc:
                    try:
                        partial.unlink(missing_ok=True)
                    except OSError:
                        pass
                    self._json({"error": f"upload gagal: {exc}"}, 500)
                    return
                self._json({"path": str(destination.resolve()), "name": filename})
                return

            try:
                data = self._body()
            except ValueError as exc:
                self._json({"error": str(exc)}, 400)
                return

            if path == "/api/jobs":
                try:
                    job = jobs.start(
                        data.get("video", ""),
                        target=data.get("target", "reach"),
                        limit=int(data.get("limit", 3)),
                        layout=data.get("layout", "fill"),
                        output_format=data.get("output_format", "portrait"),
                        render=bool(data.get("render", True)),
                        defer_video=bool(data.get("defer_video", False)),
                        caption=data.get("caption"),
                        avoid_faces=bool(data.get("avoid_faces", True)),
                        language=data.get("language", "id"),
                        model=data.get("model", "small"),
                        ollama_model=data.get("ollama_model"),
                    )
                except ValueError as exc:
                    self._json({"error": str(exc)}, 400)
                    return
                except RuntimeError as exc:
                    self._json({"error": str(exc)}, 409)
                    return
                self._json(job.to_dict())
                return

            if path == "/api/jobs/process":
                try:
                    job = jobs.process_selected(
                        str(data.get("clip_id", "")),
                        target=data.get("target", "reach"),
                        limit=int(data.get("limit", 1)),
                        layout=data.get("layout", "fill"),
                        output_format=data.get("output_format", "portrait"),
                        render=bool(data.get("render", False)),
                        caption=data.get("caption"),
                        avoid_faces=bool(data.get("avoid_faces", True)),
                        language=data.get("language", "id"),
                        model=data.get("model", "small"),
                    )
                except ValueError as exc:
                    self._json({"error": str(exc)}, 400)
                    return
                except RuntimeError as exc:
                    self._json({"error": str(exc)}, 409)
                    return
                self._json(job.to_dict())
                return

            if path == "/api/transcript/review":
                try:
                    job = jobs.review_transcript(
                        ollama_model=data.get("ollama_model", ""),
                        asr_model=data.get("asr_model", "large-v3-turbo"),
                    )
                except ValueError as exc:
                    self._json({"error": str(exc)}, 400)
                    return
                except RuntimeError as exc:
                    self._json({"error": str(exc)}, 409)
                    return
                self._json(job.to_dict())
                return

            if path == "/api/hooks/analyze":
                clip_id = str(data.get("clip_id", ""))
                model = data.get("model", "llama3.2")
                if not isinstance(model, str) or not model.strip():
                    self._json({"error": "nama model Ollama harus diisi"}, 400)
                    return
                try:
                    from .pipeline.local_hook_ai import (
                        HookAnalysisError, OllamaConfig, analyze_hook,
                    )
                    with store.locked():
                        project = store.load()
                        clip = project.clip(clip_id)
                        if clip is None:
                            self._json({"error": "kandidat tidak ditemukan"}, 404)
                            return
                        transcript = " ".join(
                            word.text for word in project.words
                            if word.end > clip.start and word.start < clip.end
                        )
                    result = analyze_hook(transcript, OllamaConfig(model=model.strip()))
                    analysis = {
                        "score": result.score,
                        "reasons": list(result.reasons),
                        "model": model.strip(),
                    }
                    with store.locked():
                        project = store.load()
                        if project.clip(clip_id) is None:
                            self._json({"error": "kandidat tidak ditemukan"}, 404)
                            return
                        hook_scores = project.extra.setdefault("hook_ai", {})
                        hook_scores[clip_id] = analysis
                        store.save(project)
                except (HookAnalysisError, ValueError, TypeError) as exc:
                    self._json({"error": str(exc)}, 503)
                    return
                self._json(analysis)
                return

            if path == "/api/jobs/cancel":
                if not jobs.cancel(str(data.get("id", ""))):
                    self._json({"error": "job tidak ditemukan atau sudah selesai"}, 409)
                    return
                try:
                    replacement_id = workspaces.discard_after_cancel(workspace)
                except (OSError, RuntimeError) as exc:
                    self._json({"error": f"job dihentikan, tetapi proyek gagal dihapus: {exc}"}, 500)
                    return
                self._json({
                    "ok": True,
                    "project_deleted": True,
                    "workspace_removed": workspace.id != replacement_id,
                    "replacement_id": replacement_id,
                })
                return

            if path == "/api/pick":
                try:
                    picked = pick_file()
                except RuntimeError as exc:
                    self._json({"error": str(exc)}, 500)
                    return
                self._json({"path": picked})
                return

            if path == "/api/reveal":
                if sys.platform == "win32":
                    subprocess.Popen(["explorer", str(root)])
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(root)])
                else:
                    subprocess.Popen(["xdg-open", str(root)])
                self._json({"ok": True, "path": str(root)})
                return

            if path == "/api/clips":
                if not project_file.is_file():
                    self._json({"error": "belum ada proyek"}, 404)
                    return
                with store.locked():
                    project = store.load()
                    clip = project.clip(str(data.get("id", "")))
                    if clip is None:
                        self._json({"error": "klip tidak dikenal"}, 404)
                        return
                    status = data.get("status")
                    if status is not None and status not in STATUSES:
                        self._json({"error": f"status harus salah satu: {', '.join(STATUSES)}"}, 400)
                        return
                    if status is not None:
                        clip.status = status
                    store.save(project)
                self._json({"ok": True, "id": clip.id, "status": clip.status})
                return

            self._json({"error": "tidak ditemukan"}, 404)

    return Handler


def make_server(target: str | Path, host: str = "127.0.0.1", port: int = 0,
                transcriber_factory=None) -> ThreadingHTTPServer:
    handler = make_handler(target, transcriber_factory=transcriber_factory)
    return ThreadingHTTPServer((host, port), handler)


def serve(target: str | Path, host: str = "127.0.0.1", port: int = 0,
          transcriber_factory=None) -> None:
    server = make_server(target, host, port, transcriber_factory=transcriber_factory)
    url = f"http://{host}:{server.server_address[1]}/"
    print(f"studio: {url}  (Ctrl+C untuk berhenti)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nberhenti")
    finally:
        server.server_close()
