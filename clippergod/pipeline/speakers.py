"""Speaker timeline: ikat label pembicara ke track wajah, beri warna, potong per giliran.

Label pembicara datang dari mana pun — diarisasi (pyannote, F3) atau koreksi manual
di UI. Modul ini tidak peduli sumbernya; ia hanya butuh `Word.speaker`.

Yang dihasilkan:
  - binding speaker -> track wajah (dengan tingkat keyakinan, bukan tebakan yakin),
  - warna highlight caption per speaker (ASS, aman untuk libass),
  - segmen giliran bicara, dipakai reframe untuk memotong framing ke pembicara aktif.

Kenapa "cut" dan bukan pan: dua pembicara yang duduk berjauhan berjarak ~500 px.
Pan mulus 500 px butuh >2 s dan terlihat seperti kamera mabuk; editor profesional
memotong. Jadi framing pindah saat pembicara berganti, bukan meluncur.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.captions import ass_color
from ..core.models import Word
from .faces import FaceScan

#: Warna highlight caption. Dibaca mata sebagai pembeda, bukan dekorasi.
PALETTE: tuple[str, ...] = (
    "#FFD400",  # kuning
    "#3DDC97",  # mint
    "#FF7A45",  # oranye
    "#7AA2FF",  # biru
    "#FF5C8A",  # pink
    "#B388FF",  # ungu
)

MIN_HITS = 3          # di bawah ini, track dianggap kebetulan lewat
MIN_SHARE = 0.45      # porsi bicara yang jatuh di satu wajah
MIN_SEGMENT = 0.8     # segmen lebih pendek digabung: hindari cut beruntun

__all__ = [
    "PALETTE", "MIN_HITS", "MIN_SHARE", "MIN_SEGMENT",
    "ass_color", "SpeakerBinding", "SpeakerTimeline", "SpeakerSegment",
    "bind_speakers", "speaker_segments",
]


def _ass_color_legacy(hex_rgb: str) -> str:
    """Deprecated: pakai `clippergod.core.captions.ass_color`."""
    return ass_color(hex_rgb)


@dataclass(slots=True)
class SpeakerBinding:
    speaker: str
    track_id: int | None
    hits: int
    share: float
    color: str  # ASS
    review: bool = False
    reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "speaker": self.speaker,
            "track_id": self.track_id,
            "hits": self.hits,
            "share": round(self.share, 3),
            "review": self.review,
            **({"reason": self.reason} if self.reason else {}),
        }


@dataclass(slots=True)
class SpeakerTimeline:
    bindings: list[SpeakerBinding] = field(default_factory=list)
    totals: dict[str, int] = field(default_factory=dict)

    def by_speaker(self, speaker: str) -> SpeakerBinding | None:
        for b in self.bindings:
            if b.speaker == speaker:
                return b
        return None

    def color_for(self, speaker: str | None) -> str | None:
        if not speaker:
            return None
        b = self.by_speaker(speaker)
        return b.color if b else None

    def track_for(self, speaker: str | None) -> int | None:
        if not speaker:
            return None
        b = self.by_speaker(speaker)
        return b.track_id if b else None

    @property
    def bound(self) -> list[SpeakerBinding]:
        return [b for b in self.bindings if b.track_id is not None]

    @property
    def needs_review(self) -> list[str]:
        return [b.speaker for b in self.bindings if b.review]

    def colors(self) -> dict[str, str]:
        return {b.speaker: b.color for b in self.bindings}

    def to_dict(self) -> dict:
        return {
            "bindings": [b.to_dict() for b in self.bindings],
            "needs_review": self.needs_review,
        }


@dataclass(frozen=True, slots=True)
class SpeakerSegment:
    start: float  # relatif ke klip
    end: float
    speaker: str | None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def _intervals(words: list[Word]) -> dict[str, list[tuple[float, float]]]:
    out: dict[str, list[tuple[float, float]]] = {}
    for w in words:
        if w.speaker:
            out.setdefault(w.speaker, []).append((w.start, w.end))
    return out


def _speaker_at(intervals: dict[str, list[tuple[float, float]]], t: float,
                tolerance: float = 0.12) -> str | None:
    for speaker, spans in intervals.items():
        for start, end in spans:
            if start - tolerance <= t <= end + tolerance:
                return speaker
    return None


def bind_speakers(
    words: list[Word],
    scan: FaceScan,
    palette: tuple[str, ...] = PALETTE,
    speaker_map: dict[str, int] | None = None,
) -> SpeakerTimeline:
    """Cocokkan tiap speaker ke satu track wajah.

    Tiga jalur, dari yang paling bisa dipercaya:
      1. `speaker_map` eksplisit (hasil koreksi user di UI) -> review=False.
      2. satu speaker, satu wajah -> pakai wajah itu; review kalau share rendah.
      3. jumlah speaker == jumlah wajah -> dipetakan kiri-ke-kanan sesuai urutan
         muncul, dan **selalu** ditandai review: tanpa active-speaker detection
         (Light-ASD, F3 lanjutan) ini tebakan posisi, bukan bukti.

    Kalau jumlahnya tidak cocok, greedy berdasarkan hit lalu tetap review.
    """
    intervals = _intervals(words)
    timeline = SpeakerTimeline()
    if not intervals:
        return timeline

    # warna dibagi urut kemunculan pertama, supaya stabil antar-run
    order: list[str] = []
    for w in words:
        if w.speaker and w.speaker not in order:
            order.append(w.speaker)

    tallies: dict[str, dict[int, int]] = {s: {} for s in order}
    totals: dict[str, int] = {s: 0 for s in order}
    track_x: dict[int, list[float]] = {}
    for t, box in scan.samples:
        if box.track_id is None:
            continue
        track_x.setdefault(box.track_id, []).append((box.x0 + box.x1) / 2.0)
        speaker = _speaker_at(intervals, t)
        if speaker is None:
            continue
        tallies[speaker][box.track_id] = tallies[speaker].get(box.track_id, 0) + 1
        totals[speaker] += 1

    plausible = sorted(
        tid for tid, samples in track_x.items()
        if len(samples) >= MIN_HITS or tid in {t for c in tallies.values() for t in c}
    )
    plausible = [tid for tid in plausible
                 if sum(c.get(tid, 0) for c in tallies.values()) >= MIN_HITS]

    assigned: dict[str, int] = {}
    reason: dict[str, str] = {}

    if speaker_map:
        for speaker, track in speaker_map.items():
            if speaker in totals:
                assigned[speaker] = track

    if not assigned and len(order) == 1 and len(plausible) == 1:
        assigned[order[0]] = plausible[0]
    elif not assigned and len(order) == len(plausible) and len(order) >= 2:
        xs = {tid: sum(v) / len(v) for tid, v in track_x.items() if tid in plausible}
        for speaker, track in zip(order, sorted(plausible, key=lambda t: xs.get(t, 0.0))):
            assigned[speaker] = track
            reason[speaker] = "dipetakan kiri-ke-kanan (perlu konfirmasi)"
    elif not assigned:
        candidates = [
            (hits, speaker, track)
            for speaker, counts in tallies.items()
            for track, hits in counts.items()
            if hits >= MIN_HITS
        ]
        candidates.sort(key=lambda c: (-c[0], c[2]))  # seri: track lebih kecil menang
        used: set[int] = set()
        for hits, speaker, track in candidates:
            if speaker in assigned or track in used:
                continue
            assigned[speaker] = track
            used.add(track)
            reason[speaker] = "tebakan dari tumpang waktu"

    for i, speaker in enumerate(order):
        track = assigned.get(speaker)
        totals_sp = totals.get(speaker, 0)
        hits = tallies.get(speaker, {}).get(track, 0) if track is not None else 0
        share = (hits / totals_sp) if totals_sp else 0.0
        review = track is None or share < MIN_SHARE or speaker in reason
        timeline.bindings.append(
            SpeakerBinding(
                speaker=speaker,
                track_id=track,
                hits=hits,
                share=share,
                color=ass_color(palette[i % len(palette)]),
                review=review,
                reason=reason.get(speaker),
            )
        )
        timeline.totals[speaker] = totals_sp

    return timeline


def speaker_segments(
    words: list[Word],
    start: float,
    end: float,
    min_segment: float = MIN_SEGMENT,
    hold_gap: float = 1.5,
) -> list[SpeakerSegment]:
    """Segmen giliran bicara di dalam [start, end], waktu relatif ke klip.

    Jeda antar kata tetap memakai pembicara terakhir (orang yang sama masih bicara);
    jeda panjang (> hold_gap) dianggap netral dan tetap mempertahankan framing.
    """
    clip_words = [w for w in words if w.speaker and w.end > start and w.start < end]
    if not clip_words:
        return []

    segs: list[SpeakerSegment] = []
    for w in clip_words:
        s = max(start, w.start) - start
        e = min(end, w.end) - start
        if e <= s:
            continue
        if segs and segs[-1].speaker == w.speaker:
            segs[-1] = SpeakerSegment(segs[-1].start, max(segs[-1].end, e), w.speaker)
        else:
            if segs and s - segs[-1].end < hold_gap:
                segs[-1] = SpeakerSegment(segs[-1].start, max(segs[-1].end, s), segs[-1].speaker)
            segs.append(SpeakerSegment(s, e, w.speaker))

    duration = end - start
    if segs:
        segs[0] = SpeakerSegment(0.0, segs[0].end, segs[0].speaker)
        segs[-1] = SpeakerSegment(segs[-1].start, duration, segs[-1].speaker)

    # segmen terlalu pendek digabung ke tetangga terdekat: cut beruntun = goyang
    changed = True
    while changed and len(segs) > 1:
        changed = False
        for i, seg in enumerate(segs):
            if seg.duration >= min_segment:
                continue
            if i == 0:
                segs[1] = SpeakerSegment(seg.start, segs[1].end, segs[1].speaker)
            elif i == len(segs) - 1:
                segs[-2] = SpeakerSegment(segs[-2].start, seg.end, segs[-2].speaker)
            else:
                left = segs[i - 1]
                right = segs[i + 1]
                if left.duration >= right.duration:
                    segs[i - 1] = SpeakerSegment(left.start, seg.end, left.speaker)
                else:
                    segs[i + 1] = SpeakerSegment(seg.start, right.end, right.speaker)
            segs.pop(i)
            changed = True
            break

    # setelah digabung, dua segmen bersebelahan bisa jadi pembicara yang sama
    merged: list[SpeakerSegment] = []
    for seg in segs:
        if merged and merged[-1].speaker == seg.speaker:
            merged[-1] = SpeakerSegment(merged[-1].start, seg.end, seg.speaker)
        else:
            merged.append(seg)
    return merged
