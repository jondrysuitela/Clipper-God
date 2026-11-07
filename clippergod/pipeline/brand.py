"""Brand kit: satu profil berisi gaya caption + logo, dipakai berulang lintas job.

Tujuannya menghindari menyalin setelan yang sama ke setiap manifest:

    {
      "name": "Kanal Rio",
      "caption": {"font": "Inter Black", "size": 72, "highlight": "#FF7A45", "position": "top"},
      "logo": {"path": "logo.png", "position": "tr", "width_ratio": 0.16, "margin": 36, "opacity": 0.9}
    }

Aturan yang dipegang: profil tidak boleh membuat hasil yang mustahil — logo hilang,
opacity di luar 0-1, atau logo selebar kanvas semuanya ditolak dengan pesan jelas.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .caption_config import CaptionConfig, from_dict as caption_from_dict
from .render import LogoSpec

POSITIONS = ("tl", "tr", "bl", "br", "custom")
KNOWN_KEYS = {"name", "caption", "logo"}
LOGO_KEYS = {"path", "position", "width_ratio", "width", "margin", "opacity", "x", "y"}


@dataclass(frozen=True, slots=True)
class BrandProfile:
    name: str
    caption: CaptionConfig | None = None
    logo: LogoSpec | None = None
    base_dir: Path | None = None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _resolve(path: str, base_dir: Path | None) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or base_dir is None:
        return candidate
    return (base_dir / candidate).resolve()


def from_dict(data: dict[str, Any], base_dir: str | Path | None = None) -> BrandProfile:
    _require(isinstance(data, dict), "profil brand harus object JSON")
    unknown = set(data) - KNOWN_KEYS
    _require(not unknown, f"kunci tidak dikenal di profil brand: {', '.join(sorted(unknown))}")

    base = Path(base_dir) if base_dir else None
    name = str(data.get("name") or "brand")

    caption = None
    if data.get("caption") is not None:
        caption = caption_from_dict(data["caption"])

    logo = None
    if data.get("logo") is not None:
        raw = data["logo"]
        _require(isinstance(raw, dict), "'logo' harus object")
        unknown_logo = set(raw) - LOGO_KEYS
        _require(not unknown_logo,
                 f"kunci logo tidak dikenal: {', '.join(sorted(unknown_logo))}")
        _require(bool(raw.get("path")), "'logo.path' wajib diisi")

        position = str(raw.get("position", "br"))
        _require(position in POSITIONS, f"'logo.position' harus salah satu: {', '.join(POSITIONS)}")

        path = _resolve(str(raw["path"]), base)
        _require(path.is_file(), f"file logo tidak ditemukan: {path}")

        width = raw.get("width")
        width_ratio = float(raw.get("width_ratio", 0.16))
        _require(0.03 <= width_ratio <= 0.35, "'logo.width_ratio' harus 0.03-0.35")
        if width is not None:
            _require(isinstance(width, int) and 16 <= width <= 1080,
                     "'logo.width' harus 16-1080 piksel")
        margin = int(raw.get("margin", 36))
        _require(0 <= margin <= 400, "'logo.margin' harus 0-400")
        opacity = float(raw.get("opacity", 1.0))
        _require(0.0 <= opacity <= 1.0, "'logo.opacity' harus 0-1")

        logo = LogoSpec(
            path=str(path), position=position, width=width, width_ratio=width_ratio,
            margin=margin, opacity=opacity,
            x=int(raw.get("x", 0)), y=int(raw.get("y", 0)),
        )

    return BrandProfile(name=name, caption=caption, logo=logo, base_dir=base)


def from_file(path: str | Path) -> BrandProfile:
    file = Path(path)
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON brand tidak valid ({file}): {exc}") from exc
    return from_dict(raw, base_dir=file.parent)


def merge_caption(profile: BrandProfile, override: CaptionConfig | None) -> CaptionConfig | None:
    """Config eksplisit dari `--caption` menang atas profil; tidak digabung diam-diam."""
    if override is not None:
        return override
    return profile.caption
