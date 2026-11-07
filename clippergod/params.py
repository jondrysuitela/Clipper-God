"""Parameter mesin dari file JSON, bukan dari default yang terkubur di kode.

Yang diatur di sini: ambang batas potongan, jalur crop, pembuatan kandidat, dan
export. Gaya caption tetap punya filenya sendiri (`--caption`) karena divalidasi
lebih ketat dan sering diubah per brand.

Kunci asing ditolak. Salah tulis nama parameter harus jadi error, bukan diam-diam
memakai default dan membuat hasilnya tidak bisa dijelaskan.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any, TypeVar

from .core.boundaries import BoundaryConfig
from .pipeline.candidates import CandidateConfig
from .pipeline.reframe import ReframeConfig

DEFAULT_PATH = Path("config") / "params.json"

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ExportConfig:
    fps: int = 30
    crf: int = 20
    preset: str = "medium"
    bitrate_mbps: float = 10.0
    max_bitrate_mbps: float = 12.0


@dataclass(frozen=True, slots=True)
class Params:
    boundary: BoundaryConfig = field(default_factory=BoundaryConfig)
    reframe: ReframeConfig = field(default_factory=ReframeConfig)
    candidate: CandidateConfig = field(default_factory=CandidateConfig)
    export: ExportConfig = field(default_factory=ExportConfig)


SECTIONS = {
    "boundary": BoundaryConfig,
    "reframe": ReframeConfig,
    "candidate": CandidateConfig,
    "export": ExportConfig,
}


def _check_type(name: str, key: str, value: Any, default: Any) -> None:
    if default is None:
        return
    if isinstance(default, bool):
        ok = isinstance(value, bool)
    elif isinstance(default, int):
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif isinstance(default, float):
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif isinstance(default, str):
        ok = isinstance(value, str)
    else:
        ok = True
    if not ok:
        raise ValueError(f"'{name}.{key}' harus {type(default).__name__}, bukan {type(value).__name__}")


def _section(cls: type[T], name: str, values: Any) -> T:
    if not isinstance(values, dict):
        raise ValueError(f"'{name}' harus object JSON")
    base = cls()  # type: ignore[call-arg]
    allowed = {f.name for f in fields(base)}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"kunci '{name}' tidak dikenal: {', '.join(sorted(unknown))}")
    for key, value in values.items():
        _check_type(name, key, value, getattr(base, key))
    return replace(base, **values)


def from_dict(data: dict[str, Any]) -> Params:
    if not isinstance(data, dict):
        raise ValueError("params harus object JSON")
    unknown = set(data) - set(SECTIONS)
    if unknown:
        raise ValueError(f"bagian tidak dikenal: {', '.join(sorted(unknown))}")
    return Params(**{name: _section(cls, name, data[name])
                     for name, cls in SECTIONS.items() if name in data})


def from_file(path: str | Path) -> Params:
    file = Path(path)
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON params tidak valid ({file}): {exc}") from exc
    return from_dict(raw)


def load_or_default(path: str | Path | None = None) -> Params:
    """Pakai file kalau ada; tanpa file tetap jalan dengan default yang sama."""
    if path is None:
        path = DEFAULT_PATH
    file = Path(path)
    return from_file(file) if file.is_file() else Params()
