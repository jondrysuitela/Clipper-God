"""Caption Engine: ASS karaoke per kata, dirender libass.

Kenapa ASS dan bukan drawtext: satu file teks, animasi kaya, karaoke native
(\\k, \\kf, \\ko benar-benar diimplementasikan libass), dan preview bisa memakai
renderer yang sama dengan export sehingga hasilnya tidak berbeda.

Aturan keterbacaan berasal dari riset 03 §12.4:
  maks 2 baris, 32 karakter/baris, 3-5 kata/cue, 12-18 CPS,
  durasi 0.83-1.8 s, safe box x 120-960 / y 270-1260 pada 1080x1920.

Face-aware placement: kalau kotak caption beririsan bounding box wajah,
caption pindah anchor (bawah <-> atas). Font TIDAK pernah dikecilkan di bawah
batas minimum — keterbacaan lebih penting daripada muat.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field

from .models import CaptionCue, FaceBox, Word
from .keywords import keyword_indices


# ------------------------------------------------------------------ style


@dataclass(slots=True)
class CaptionStyle:
    font_name: str = "Montserrat ExtraBold"
    font_size: int = 96
    primary: str = "&H00FFFFFF"      # ASS = &HAABBGGRR (putih)
    secondary: str = "&H0000D7FF"    # highlight karaoke (oranye)
    outline_color: str = "&H00000000"
    back_color: str = "&H80000000"
    border_style: int = 1
    bold: bool = True
    outline: int = 6
    shadow: int = 3
    fade_ms: int = 60

    # tampilan teks
    uppercase: bool = False
    karaoke: bool = True

    # area aman (piksel, resolusi output)
    safe_x0: int = 120
    safe_y0: int = 270
    safe_x1: int = 960
    safe_y1: int = 1260
    position_x: int | None = None
    position_y: int | None = None

    # aturan keterbacaan
    max_words: int = 5
    max_chars: int = 32
    max_lines: int = 2
    min_dur: float = 0.83
    max_dur: float = 1.8
    max_cps: float = 18.0
    min_font_size: int = 48

    # warna per speaker (opsional, hasil Speaker Timeline)
    speaker_colors: dict[str, str] = field(default_factory=dict)

    # sorot kata kunci (angka/negasi/urgensi) dengan garis bawah
    keyword_highlight: bool = True
    max_keywords: int = 2

    # resolusi kanvas ASS
    play_res_x: int = 1080
    play_res_y: int = 1920

    @property
    def line_height(self) -> int:
        return int(self.font_size * 1.12) + self.outline + self.shadow


# ------------------------------------------------------------------ helper


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    if cs == 100:
        s, cs = s + 1, 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _visible_chars(text: str) -> int:
    """Karakter yang benar-benar dibaca mata (spasi tidak dihitung untuk CPS)."""
    return sum(1 for ch in text if not ch.isspace())


def ass_color(hex_rgb: str) -> str:
    """#RRGGBB -> &H00BBGGRR (format warna ASS, alpha 00 = opaque)."""
    h = hex_rgb.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"warna harus #RRGGBB: {hex_rgb!r}")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"&H00{b:02X}{g:02X}{r:02X}"


def _wrap(text: str, style: CaptionStyle) -> list[str]:
    """Bungkus teks jadi maksimal `max_lines` baris, seimbang."""
    lines = textwrap.wrap(
        text,
        width=style.max_chars,
        break_long_words=False,
        break_on_hyphens=False,
    )
    if len(lines) <= style.max_lines:
        return lines or [""]

    # terlalu banyak baris: bagi rata berdasarkan jumlah kata
    words = text.split()
    per_line = max(1, (len(words) + style.max_lines - 1) // style.max_lines)
    balanced = [" ".join(words[i:i + per_line]) for i in range(0, len(words), per_line)]
    return balanced[: style.max_lines]


def _box(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
    return (x0, y0, x1, y1)


def _overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, dx) * max(0.0, dy)


# ------------------------------------------------------------------ cueing


def build_cues(words: list[Word], style: CaptionStyle | None = None) -> list[CaptionCue]:
    """Pecah transkrip jadi cue caption yang patuh aturan keterbacaan."""
    style = style or CaptionStyle()
    cues: list[CaptionCue] = []
    n = len(words)
    i = 0

    while i < n:
        best = i
        j = i
        while j < n:
            chunk = words[i : j + 1]
            dur = chunk[-1].end - chunk[0].start
            chars = _visible_chars(" ".join(w.clean for w in chunk))

            if len(chunk) > style.max_words:
                break
            if chars > style.max_chars * style.max_lines:
                break
            if dur > style.max_dur:
                break
            if dur > 0 and chars / dur > style.max_cps:
                break  # CPS adalah aturan keras: jangan buat cue yang melanggar batasnya sendiri
            best = j
            j += 1

        chunk = words[i : best + 1]
        start = chunk[0].start
        end = chunk[-1].end

        # durasi minimum: perpanjang selama tidak menabrak kata berikutnya
        if end - start < style.min_dur:
            target = start + style.min_dur
            if best + 1 < n:
                target = min(target, words[best + 1].start)
            end = max(end, target)

        # Kalau masih terlalu cepat dibaca, perpanjang sampai CPS patuh — tapi
        # hanya sampai kata berikutnya mulai, dan tidak melewati max_dur. Tanpa ini
        # `max_cps` di config cuma hiasan untuk kata-kata panjang.
        if chars / max(1e-3, end - start) > style.max_cps:
            needed = start + chars / style.max_cps
            ceiling = start + style.max_dur
            if best + 1 < n:
                ceiling = min(ceiling, words[best + 1].start)
            end = max(end, min(needed, ceiling))

        text = " ".join(w.clean for w in chunk)
        chars = _visible_chars(text)
        dur = max(1e-3, end - start)

        cues.append(
            CaptionCue(
                start=start,
                end=end,
                words=list(chunk),
                lines=_wrap(text, style),
                cps=round(chars / dur, 2),
                char_count=chars,
            )
        )
        i = best + 1

    return cues


def choose_placement(cue: CaptionCue, faces: list[FaceBox], style: CaptionStyle) -> str:
    """Tentukan anchor caption: 'bottom' atau 'top' agar tidak menutupi wajah."""
    if not faces:
        return "bottom"

    h = style.line_height * max(1, len(cue.lines)) + style.outline * 2
    bottom = _box(style.safe_x0, style.safe_y1 - h, style.safe_x1, style.safe_y1)
    top = _box(style.safe_x0, style.safe_y0, style.safe_x1, style.safe_y0 + h)

    margin = 8.0
    b_over = sum(
        _overlap(bottom, _box(f.x0 - margin, f.y0 - margin, f.x1 + margin, f.y1 + margin))
        for f in faces
    )
    t_over = sum(
        _overlap(top, _box(f.x0 - margin, f.y0 - margin, f.x1 + margin, f.y1 + margin))
        for f in faces
    )

    if b_over <= 0:
        return "bottom"
    if t_over <= 0:
        return "top"
    return "bottom" if b_over <= t_over else "top"


def place_cues(
    cues: list[CaptionCue],
    style: CaptionStyle,
    faces_by_cue: dict[int, list[FaceBox]] | None = None,
    force: str | None = None,
) -> list[CaptionCue]:
    """Tentukan anchor tiap cue. `force` = "top"/"bottom" memaksa, None = face-aware."""
    faces_by_cue = faces_by_cue or {}
    for idx, cue in enumerate(cues):
        if force in ("top", "bottom"):
            cue.placement = force
        else:
            cue.placement = choose_placement(cue, faces_by_cue.get(idx, []), style)
    return cues


# ------------------------------------------------------------------ render


def _cue_text(cue: CaptionCue, style: CaptionStyle) -> str:
    """Teks ASS untuk satu cue: karaoke per kata, atau teks biasa."""
    picks = (keyword_indices([w.clean for w in cue.words], style.max_keywords)
             if style.keyword_highlight else set())

    def fmt(index: int) -> str:
        text = cue.words[index].clean
        if style.uppercase:
            text = text.upper()
        if index in picks:
            # Garis bawah aman berdampingan dengan \kf: tidak menyentuh warna
            # karaoke, dan tetap terbaca saat kata sedang di-highlight.
            return r"{\u1}" + text + r"{\u0}"
        return text

    if not style.karaoke:
        return " ".join(fmt(i) for i in range(len(cue.words)))

    parts: list[str] = []
    for i, w in enumerate(cue.words):
        cs = max(1, int(round(w.dur * 100)))
        parts.append(r"{\kf%d}%s" % (cs, fmt(i)))
    return " ".join(parts)


def build_ass(
    cues: list[CaptionCue],
    style: CaptionStyle | None = None,
    title: str = "ClipperGod",
) -> str:
    """Hasilkan file ASS lengkap, siap di-burn lewat filter `subtitles`."""
    style = style or CaptionStyle()
    center_x = (style.safe_x0 + style.safe_x1) // 2

    head = [
        "[Script Info]",
        f"Title: {title}",
        "ScriptType: v4.00+",
        f"PlayResX: {style.play_res_x}",
        f"PlayResY: {style.play_res_y}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Cap,{font},{size},{primary},{secondary},{outline_c},{back_c},{bold},0,0,0,"
        "100,100,0,0,{border_style},{outline},{shadow},2,{ml},{mr},{mv},1".format(
            font=style.font_name,
            size=style.font_size,
            primary=style.primary,
            secondary=style.secondary,
            outline_c=style.outline_color,
            back_c=style.back_color,
            bold=-1 if style.bold else 0,
            border_style=style.border_style,
            outline=style.outline,
            shadow=style.shadow,
            ml=style.safe_x0,
            mr=style.play_res_x - style.safe_x1,
            mv=style.play_res_y - style.safe_y1,
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text",
    ]

    events: list[str] = []
    for cue in cues:
        # anchor: \an2 = bawah-tengah, \an8 = atas-tengah
        if style.position_x is not None and style.position_y is not None:
            an = 5
            anchor_x = round(style.play_res_x * style.position_x / 100)
            anchor_y = round(style.play_res_y * style.position_y / 100)
        elif cue.placement == "top":
            anchor_x = center_x
            anchor_y = style.safe_y0
            an = 8
        else:
            anchor_x = center_x
            anchor_y = style.safe_y1
            an = 2

        tags = [rf"\an{an}", rf"\pos({anchor_x},{anchor_y})"]
        if style.fade_ms > 0:
            tags.append(rf"\fad({style.fade_ms},{style.fade_ms})")

        speaker = cue.words[0].speaker if cue.words else None
        if speaker and speaker in style.speaker_colors:
            # \2c = warna karaoke (sekunder). Teks tetap putih; yang berwarna hanya
            # sapuan highlight, supaya keterbacaan tidak dikorbankan demi identitas.
            tags.append(rf"\2c{style.speaker_colors[speaker]}")

        text = "{" + "".join(tags) + "}" + _cue_text(cue, style)
        events.append(
            f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},Cap,,0,0,0,,{text}"
        )

    return "\n".join(head + events) + "\n"


def caption_report(cues: list[CaptionCue], style: CaptionStyle | None = None) -> dict:
    """Ringkasan kepatuhan caption — dipakai komponen C pada VPS.

    `violations` = aturan yang benar-benar merusak keterbacaan (baris, karakter, CPS).
    `notes` = target yang kadang mustahil dicapai, mis. durasi minimum saat orang
    bicara sangat cepat; dicatat, bukan dianggap kegagalan.
    """
    style = style or CaptionStyle()
    if not cues:
        return {"cues": 0, "max_cps": 0.0, "over_cap": 0,
                "violations": ["tidak ada caption"], "notes": []}

    violations: list[str] = []
    notes: list[str] = []
    over_cap = 0
    for cue in cues:
        if len(cue.lines) > style.max_lines:
            violations.append(f"baris berlebih @{cue.start:.2f}")
        if any(len(line) > style.max_chars for line in cue.lines):
            violations.append(f"karakter berlebih @{cue.start:.2f}")
        if cue.cps > style.max_cps:
            over_cap += 1
            # Satu kata yang sendirian sudah melebihi cap CPS tidak bisa diperbaiki
            # dengan memecah cue — itu konsekuensi kecepatan bicara. Dicatat sebagai
            # catatan; yang dianggap pelanggaran adalah cue multi-kata yang lolos.
            target = violations if len(cue.words) > 1 else notes
            target.append(f"CPS {cue.cps:.1f} @{cue.start:.2f}")
        if cue.duration < style.min_dur - 0.01:
            notes.append(f"durasi {cue.duration:.2f}s @{cue.start:.2f}")

    return {
        "cues": len(cues),
        "max_cps": max(c.cps for c in cues),
        "avg_cps": round(sum(c.cps for c in cues) / len(cues), 2),
        "words_per_cue": round(sum(len(c.words) for c in cues) / len(cues), 2),
        "over_cap": over_cap,
        "violations": violations,
        "notes": notes,
    }
