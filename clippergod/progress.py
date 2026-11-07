"""Progress dan pembatalan kooperatif.

Dipakai UI maupun CLI: satu callback menerima dict {stage, done, total, percent},
dan satu token bisa dibatalkan dari thread lain. Pembatalan tidak membunuh proses
sepihak — pemanggil memeriksa token di titik aman, lalu FFmpeg dihentikan rapi
supaya file setengah jadi tidak tertinggal.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable


class CancelledError(RuntimeError):
    """Dibatalkan user. Bukan kegagalan; jangan diperlakukan seperti error."""


class CancelToken:
    def __init__(self, event=None) -> None:
        self._event = event or threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError("dibatalkan user")


@dataclass(slots=True)
class Progress:
    """Callback opsional. Tanpa callback, semua metode jadi no-op."""

    emit: Callable[[dict], None] | None = None
    stage: str = ""
    done: int = 0
    total: int = 0

    def start(self, stage: str, total: int = 0) -> None:
        self.stage, self.done, self.total = stage, 0, total
        self._send()

    def advance(self, n: int = 1) -> None:
        self.done += n
        self._send()

    def finish(self) -> None:
        if self.total:
            self.done = self.total
        self._send()

    def _send(self) -> None:
        if self.emit is None:
            return
        self.emit({
            "stage": self.stage,
            "done": self.done,
            "total": self.total,
            "percent": round(100.0 * self.done / self.total, 1) if self.total else None,
        })
