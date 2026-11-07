"""Layout engine: susunan panel pada kanvas output.

Mode yang didukung sekarang:
  - `fill`  : satu crop mengikuti wajah (perilaku lama).
  - `split` : dua pembicara ditumpuk vertikal, dengan strip khusus caption di bawah.

Kenapa caption punya strip sendiri: di mode split, kedua panel berisi wajah.
Kalau caption ditaruh di atas gambar, ia menabrak salah satu wajah. Strip 260 px
di bawah membuat caption tidak pernah bertabrakan **secara konstruksi**.

Kenapa panel di-zoom: panel 1080x830 beraspek 1,30. Kalau crop diambil dari
tinggi penuh sumber 16:9, lebarnya jadi ~937 px — hampir seluruh frame, dan
kedua orang ikut masuk. Jadi panel memotong sebagian tinggi sumber (default 60%)
supaya benar-benar satu wajah per panel.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..core.captions import CaptionStyle


@dataclass(frozen=True, slots=True)
class LayoutConfig:
    mode: str = "fill"            # fill | split | three | screenshare
    out_w: int = 1080
    out_h: int = 1920
    caption_strip: int = 260      # px di dasar kanvas, hanya untuk layout berpanel
    panel_gap: int = 0            # px antar panel
    panel_zoom: float = 0.52      # porsi tinggi sumber yang dipakai satu panel
    face_bias: float = 0.50       # posisi wajah di dalam panel (0 = atas, 1 = bawah)
    screen_ratio: float = 0.70    # porsi area layar pada mode screenshare


@dataclass(frozen=True, slots=True)
class PanelCrop:
    crop_w: int
    crop_h: int
    x: float
    y: int = 0
    out_h: int = 830
    fit: bool = False             # True = letterbox, bukan crop-penuh (layar)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


MIN_PANEL_H = 120  # di bawah ini panel bukan wajah lagi, cuma goresan


def panel_geometry(src_w: int, src_h: int, cfg: LayoutConfig, count: int) -> tuple[int, int, int]:
    """(tinggi panel output, lebar crop sumber, tinggi crop sumber)."""
    if count < 1:
        raise ValueError("butuh minimal satu panel")
    usable = cfg.out_h - cfg.caption_strip - cfg.panel_gap * (count - 1)
    panel_out_h = usable // count
    if panel_out_h < MIN_PANEL_H:
        raise ValueError(
            f"caption_strip {cfg.caption_strip}px menyisakan panel {panel_out_h}px "
            f"(minimum {MIN_PANEL_H}px)"
        )
    aspect = cfg.out_w / panel_out_h
    crop_h = max(1, min(src_h, int(round(src_h * cfg.panel_zoom))))
    crop_w = min(src_w, int(round(crop_h * aspect)))
    return panel_out_h, crop_w, crop_h


def split_panels(
    centers: list[tuple[float, float]],
    src_w: int,
    src_h: int,
    cfg: LayoutConfig | None = None,
) -> list[PanelCrop]:
    """Satu panel per pusat wajah `(x, y)`, urut sesuai daftar."""
    cfg = cfg or LayoutConfig(mode="split")
    if len(centers) < 2:
        return []
    panel_out_h, crop_w, crop_h = panel_geometry(src_w, src_h, cfg, len(centers))
    panels: list[PanelCrop] = []
    for cx, cy in centers:
        x = _clamp(cx - crop_w / 2.0, 0.0, max(0.0, src_w - crop_w))
        y = _clamp(cy - crop_h * cfg.face_bias, 0.0, max(0.0, src_h - crop_h))
        panels.append(PanelCrop(crop_w=crop_w, crop_h=crop_h, x=x,
                                y=int(round(y)), out_h=panel_out_h))
    return panels


def three_panels(
    centers: list[tuple[float, float]],
    src_w: int,
    src_h: int,
    cfg: LayoutConfig | None = None,
) -> list[PanelCrop]:
    """Tiga pembicara ditumpuk. Kurang dari tiga -> [] supaya pemanggil jatuh ke split."""
    cfg = cfg or LayoutConfig(mode="three")
    if len(centers) < 3:
        return []
    return split_panels(centers[:3], src_w, src_h, cfg)


def screenshare_panels(
    center: tuple[float, float],
    src_w: int,
    src_h: int,
    cfg: LayoutConfig | None = None,
) -> list[PanelCrop]:
    """Layar penuh di atas (letterbox, tidak dipotong) + strip wajah di bawah."""
    cfg = cfg or LayoutConfig(mode="screenshare")
    usable = cfg.out_h - cfg.caption_strip
    screen_h = int(usable * cfg.screen_ratio)
    strip_h = usable - screen_h
    if strip_h < MIN_PANEL_H:
        raise ValueError(f"screen_ratio {cfg.screen_ratio} menyisakan strip {strip_h}px")

    screen = PanelCrop(crop_w=src_w, crop_h=src_h, x=0.0, y=0, out_h=screen_h, fit=True)

    aspect = cfg.out_w / strip_h
    crop_h = max(1, min(src_h, int(round(src_h * cfg.panel_zoom))))
    crop_w = min(src_w, int(round(crop_h * aspect)))
    cx, cy = center
    x = _clamp(cx - crop_w / 2.0, 0.0, max(0.0, src_w - crop_w))
    y = _clamp(cy - crop_h * cfg.face_bias, 0.0, max(0.0, src_h - crop_h))
    strip = PanelCrop(crop_w=crop_w, crop_h=crop_h, x=x, y=int(round(y)), out_h=strip_h)
    return [screen, strip]


def caption_style_for_split(style: CaptionStyle, cfg: LayoutConfig | None = None) -> CaptionStyle:
    """Pindahkan safe box caption ke strip bawah, dan kecilkan sedikit fontnya."""
    cfg = cfg or LayoutConfig(mode="split")
    strip_top = cfg.out_h - cfg.caption_strip
    return replace(
        style,
        safe_y0=strip_top + 12,
        safe_y1=cfg.out_h - 40,
        font_size=min(style.font_size, 88),
    )
