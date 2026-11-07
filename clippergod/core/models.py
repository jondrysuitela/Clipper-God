"""Model data inti ClipperGod.

Prinsip arsitektur: transkrip, caption, dan timeline adalah SATU struktur data
yang sama. Semua komponen menghasilkan timestamp pada timeline audio 16 kHz —
tidak pernah waktu relatif per komponen.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------- transkrip


@dataclass(frozen=True, slots=True)
class Word:
    """Satu kata dengan boundary waktu absolut (detik)."""

    text: str
    start: float
    end: float
    prob: float = 1.0
    speaker: str | None = None

    @property
    def dur(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def clean(self) -> str:
        return self.text.strip()


@dataclass(slots=True)
class Segment:
    """Kalimat / baris transkrip (output ASR sebelum di-reflow)."""

    words: list[Word] = field(default_factory=list)
    speaker: str | None = None

    @property
    def start(self) -> float:
        return self.words[0].start if self.words else 0.0

    @property
    def end(self) -> float:
        return self.words[-1].end if self.words else 0.0

    @property
    def text(self) -> str:
        return " ".join(w.clean for w in self.words)


# ---------------------------------------------------------------- batas klip


@dataclass(frozen=True, slots=True)
class Boundary:
    """Titik potong yang dinilai aman/tidaknya.

    `index` = posisi potong di antara ``words[index-1]`` dan ``words[index]``.
    """

    time: float
    index: int
    score: float
    reasons: tuple[str, ...] = ()

    @property
    def safe(self) -> bool:
        return self.score >= 0.70


@dataclass(slots=True)
class BoundedClip:
    """Hasil pemaksaan batas semantik pada satu kandidat klip."""

    start: float
    end: float
    start_boundary: Boundary | None = None
    end_boundary: Boundary | None = None
    warnings: list[str] = field(default_factory=list)
    rejected: bool = False
    reject_reason: str | None = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


# ---------------------------------------------------------------- media


@dataclass(frozen=True, slots=True)
class FaceBox:
    """Bounding box wajah dalam piksel pada resolusi output."""

    x0: float
    y0: float
    x1: float
    y1: float
    track_id: int | None = None
    speaker: str | None = None

    @property
    def w(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def h(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def area(self) -> float:
        return self.w * self.h


@dataclass(slots=True)
class CaptionCue:
    """Satu baris caption yang sudah dipecah sesuai aturan keterbacaan."""

    start: float
    end: float
    words: list[Word]
    lines: list[str] = field(default_factory=list)
    placement: str = "bottom"  # "bottom" | "top"
    cps: float = 0.0
    char_count: int = 0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def text(self) -> str:
        return " ".join(self.lines)


@dataclass(slots=True)
class ClipCandidate:
    """Kandidat klip sebelum/sesudah diskor."""

    start: float
    end: float
    title: str = ""
    score: float | None = None
    reasons: list[str] = field(default_factory=list)
    vps: dict | None = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)
