"""Clip DNA: sidik jari isi klip untuk mencegah duplikat lintas episode.

Yang di-hash adalah teksnya, bukan file video: klip yang sama bisa dirender ulang
dengan crop/caption berbeda dan tetap harus dikenali. Pembandingnya Jaccard atas
shingle 5 kata — tahan terhadap potongan yang bergeser beberapa kata, tapi tidak
tahan terhadap parafrase total (itu butuh embedding, belum ada di sini).

Index disimpan di JSON. Tanpa path index, perbandingan hanya berlaku dalam satu
putaran; dengan path, satu episode bisa dibandingkan dengan episode sebelumnya.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from ..core.models import Word

K = 5
THRESHOLD = 0.6
VERSION = 1


def tokens(text: str) -> list[str]:
    return "".join(ch.lower() if ch.isalnum() else " " for ch in text).split()


def shingles(text: str, k: int = K) -> frozenset[str]:
    words = tokens(text)
    if not words:
        return frozenset()
    if len(words) < k:
        return frozenset({hashlib.blake2b(" ".join(words).encode(), digest_size=8).hexdigest()})
    return frozenset(
        hashlib.blake2b(" ".join(words[i:i + k]).encode(), digest_size=8).hexdigest()
        for i in range(len(words) - k + 1)
    )


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


@dataclass(frozen=True, slots=True)
class Dna:
    text: str
    shingles: frozenset[str]
    duration: float

    @property
    def key(self) -> str:
        joined = "|".join(sorted(self.shingles))
        return hashlib.blake2b(joined.encode(), digest_size=8).hexdigest()

    def summary(self) -> dict:
        return {"key": self.key, "shingles": len(self.shingles),
                "duration": round(self.duration, 2), "text": self.text[:120]}


def clip_dna(words: list[Word], start: float, end: float) -> Dna:
    text = " ".join(w.clean for w in words if w.end > start and w.start < end)
    return Dna(text=text, shingles=shingles(text), duration=end - start)


class DnaIndex:
    def __init__(self, entries: list[dict] | None = None) -> None:
        self.entries: list[dict] = list(entries or [])

    @classmethod
    def load(cls, path: str | Path | None) -> "DnaIndex":
        if path is None:
            return cls()
        file = Path(path)
        if not file.is_file():
            return cls()
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()  # index rusak: mulai bersih, jangan gagalkan render
        if int(raw.get("version", 0)) > VERSION:
            return cls()
        return cls(raw.get("clips", []))

    def save(self, path: str | Path) -> Path:
        file = Path(path)
        file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": VERSION, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "clips": self.entries}
        tmp = file.with_suffix(file.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(file)
        return file

    def find(self, dna: Dna, threshold: float = THRESHOLD) -> list[dict]:
        found: list[dict] = []
        for entry in self.entries:
            score = jaccard(dna.shingles, frozenset(entry.get("shingles", [])))
            if score >= threshold:
                found.append({
                    "key": entry.get("key", ""),
                    "title": entry.get("title", ""),
                    "episode": entry.get("episode", ""),
                    "similarity": round(score, 3),
                })
        return sorted(found, key=lambda item: -item["similarity"])

    def add(self, dna: Dna, *, title: str, episode: str, start: float, end: float) -> None:
        self.entries.append({
            "key": dna.key,
            "title": title,
            "episode": episode,
            "start": round(start, 3),
            "end": round(end, 3),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "shingles": sorted(dna.shingles),
        })
