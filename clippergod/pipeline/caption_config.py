"""Konfigurasi caption dari JSON — batas yang bisa diatur user, tanpa merusak keterbacaan.

Yang boleh diubah: font, ukuran, warna teks/highlight, outline, posisi, huruf besar,
karaoke on/off, kotak latar, batas kata/baris/karakter/CPS/durasi, dan area aman.

Yang tidak boleh: menurunkan font di bawah 48 px tanpa menyatakannya eksplisit
(`allow_small_font`). Spec menetapkan 48 px sebagai batas keterbacaan; kalau user
tetap ingin lebih kecil, itu pilihannya — tapi harus tercatat sebagai peringatan,
bukan diam-diam diterima.

Contoh `caption.json`:

    {
      "font": "Montserrat ExtraBold",
      "size": 84,
      "color": "#FFFFFF",
      "highlight": "#22D3EE",
      "position": "bottom",
      "uppercase": true,
      "karaoke": true,
      "box": false,
      "max_words": 4,
      "max_cps": 16,
      "safe_area": {"x0": 120, "x1": 960, "y0": 900, "y1": 1700}
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

from ..core.captions import CaptionStyle, ass_color

FONT_FLOOR = 48
FONT_MAX = 160
KNOWN_KEYS = {
    "font", "size", "color", "highlight", "outline", "shadow", "outline_color",
    "position", "uppercase", "karaoke", "max_words", "max_lines", "max_chars",
    "max_cps", "min_duration", "max_duration", "safe_area", "allow_small_font",
    "keyword_highlight", "max_keywords", "box", "position_x", "position_y",
}
POSITIONS = ("auto", "bottom", "top")


@dataclass(frozen=True, slots=True)
class CaptionConfig:
    font: str | None = None
    size: int | None = None
    color: str | None = None
    highlight: str | None = None
    outline_color: str | None = None
    outline: int | None = None
    shadow: int | None = None
    position: str = "auto"
    position_x: int | None = None
    position_y: int | None = None
    uppercase: bool = False
    karaoke: bool = True
    box: bool = False
    max_words: int | None = None
    max_lines: int | None = None
    max_chars: int | None = None
    max_cps: float | None = None
    min_duration: float | None = None
    max_duration: float | None = None
    safe_area: tuple[int, int, int, int] | None = None
    allow_small_font: bool = False
    keyword_highlight: bool | None = None
    max_keywords: int | None = None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def from_dict(data: dict[str, Any]) -> CaptionConfig:
    _require(isinstance(data, dict), "config caption harus object JSON")
    unknown = set(data) - KNOWN_KEYS
    _require(not unknown, f"kunci tidak dikenal: {', '.join(sorted(unknown))}")

    def opt_int(key: str) -> int | None:
        value = data.get(key)
        if value is None:
            return None
        _require(isinstance(value, int) and not isinstance(value, bool),
                 f"'{key}' harus bilangan bulat")
        return int(value)

    def opt_float(key: str) -> float | None:
        value = data.get(key)
        if value is None:
            return None
        _require(isinstance(value, (int, float)) and not isinstance(value, bool),
                 f"'{key}' harus angka")
        return float(value)

    position = str(data.get("position", "auto"))
    _require(position in POSITIONS, f"'position' harus salah satu: {', '.join(POSITIONS)}")
    position_x = opt_int("position_x")
    position_y = opt_int("position_y")
    for key, value in (("position_x", position_x), ("position_y", position_y)):
        if value is not None:
            _require(10 <= value <= 90, f"'{key}' harus berada di area aman 10-90%")

    safe_area = None
    if "safe_area" in data:
        area = data["safe_area"]
        _require(isinstance(area, dict), "'safe_area' harus object")
        _require(set(area) == {"x0", "x1", "y0", "y1"},
                 "'safe_area' harus berisi tepat x0, x1, y0, y1")
        values = [area[k] for k in ("x0", "x1", "y0", "y1")]
        _require(all(isinstance(v, int) and not isinstance(v, bool) for v in values),
                 "'safe_area' harus bilangan bulat semua")
        safe_area = (values[0], values[1], values[2], values[3])

    return CaptionConfig(
        font=str(data["font"]) if data.get("font") is not None else None,
        size=opt_int("size"),
        color=str(data["color"]) if data.get("color") else None,
        highlight=str(data["highlight"]) if data.get("highlight") else None,
        outline_color=str(data["outline_color"]) if data.get("outline_color") else None,
        outline=opt_int("outline"),
        shadow=opt_int("shadow"),
        position=position,
        position_x=position_x,
        position_y=position_y,
        uppercase=bool(data.get("uppercase", False)),
        karaoke=bool(data.get("karaoke", True)),
        box=bool(data.get("box", False)),
        max_words=opt_int("max_words"),
        max_lines=opt_int("max_lines"),
        max_chars=opt_int("max_chars"),
        max_cps=opt_float("max_cps"),
        min_duration=opt_float("min_duration"),
        max_duration=opt_float("max_duration"),
        safe_area=safe_area,
        allow_small_font=bool(data.get("allow_small_font", False)),
        keyword_highlight=(None if "keyword_highlight" not in data
                           else bool(data["keyword_highlight"])),
        max_keywords=opt_int("max_keywords"),
    )


def from_file(path: str | Path) -> CaptionConfig:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON caption tidak valid ({path}): {exc}") from exc
    return from_dict(raw)


def _validate(style: CaptionStyle, cfg: CaptionConfig) -> list[str]:
    warnings: list[str] = []
    _require(style.font_size >= 12, "ukuran font terlalu kecil")
    if style.font_size < FONT_FLOOR:
        _require(cfg.allow_small_font,
                 f"font {style.font_size} px di bawah batas keterbacaan {FONT_FLOOR} px "
                 f"(set 'allow_small_font': true kalau memang mau)")
        warnings.append(f"font {style.font_size} px di bawah batas {FONT_FLOOR} px")
    _require(style.font_size <= FONT_MAX, f"font maksimum {FONT_MAX} px")

    _require(1 <= style.max_words <= 8, "max_words harus 1-8")
    _require(1 <= style.max_lines <= 3, "max_lines harus 1-3")
    _require(12 <= style.max_chars <= 48, "max_chars harus 12-48")
    _require(8.0 <= style.max_cps <= 30.0, "max_cps harus 8-30")
    _require(0.3 <= style.min_dur <= 3.0, "min_dur harus 0.3-3.0")
    _require(1 <= style.max_keywords <= 4, "max_keywords harus 1-4")
    _require(style.max_dur >= style.min_dur, "max_dur tidak boleh lebih kecil dari min_dur")
    if style.max_cps > 24:
        warnings.append(f"CPS {style.max_cps:.0f} di atas kecepatan baca nyaman (~18)")

    _require(style.safe_x0 >= 0 and style.safe_x1 <= style.play_res_x,
             "safe_area x keluar kanvas")
    _require(style.safe_y0 >= 0 and style.safe_y1 <= style.play_res_y,
             "safe_area y keluar kanvas")
    _require(style.safe_x1 - style.safe_x0 >= 240, "safe_area terlalu sempit (min 240 px)")
    _require(style.safe_y1 - style.safe_y0 >= 150, "safe_area terlalu pendek (min 150 px)")
    return warnings


def build_style(cfg: CaptionConfig, base: CaptionStyle | None = None) -> tuple[CaptionStyle, list[str]]:
    """Terapkan config ke CaptionStyle. Melempar ValueError untuk nilai mustahil."""
    style = replace(base) if base is not None else CaptionStyle()

    if cfg.font:
        style.font_name = cfg.font
    if cfg.size is not None:
        style.font_size = cfg.size
    if cfg.color:
        style.primary = ass_color(cfg.color)
    if cfg.highlight:
        style.secondary = ass_color(cfg.highlight)
    if cfg.outline_color:
        style.outline_color = ass_color(cfg.outline_color)
    if cfg.outline is not None:
        _require(0 <= cfg.outline <= 12, "outline harus 0-12")
        style.outline = cfg.outline
    if cfg.shadow is not None:
        _require(0 <= cfg.shadow <= 12, "shadow harus 0-12")
        style.shadow = cfg.shadow
    if cfg.max_words is not None:
        style.max_words = cfg.max_words
    if cfg.max_lines is not None:
        style.max_lines = cfg.max_lines
    if cfg.max_chars is not None:
        style.max_chars = cfg.max_chars
    if cfg.max_cps is not None:
        style.max_cps = cfg.max_cps
    if cfg.min_duration is not None:
        style.min_dur = cfg.min_duration
    if cfg.max_duration is not None:
        style.max_dur = cfg.max_duration
    style.uppercase = cfg.uppercase
    style.karaoke = cfg.karaoke
    style.border_style = 3 if cfg.box else 1
    if cfg.box:
        style.back_color = "&H30000000"
    if cfg.keyword_highlight is not None:
        style.keyword_highlight = cfg.keyword_highlight
    if cfg.max_keywords is not None:
        style.max_keywords = cfg.max_keywords
    if cfg.safe_area:
        style.safe_x0, style.safe_x1, style.safe_y0, style.safe_y1 = cfg.safe_area
    style.position_x = cfg.position_x
    style.position_y = cfg.position_y
    _require(
        (style.position_x is None) == (style.position_y is None),
        "position_x dan position_y harus diatur bersamaan",
    )

    warnings = _validate(style, cfg)
    return style, warnings


def force_position(cfg: CaptionConfig) -> str | None:
    """None = biarkan face-aware; selain itu paksa anchor."""
    return None if cfg.position == "auto" else cfg.position


def schema() -> dict[str, Any]:
    """Deskripsi field untuk dokumentasi/UI, bukan validasi runtime."""
    return {f.name: f.type for f in fields(CaptionConfig)}
