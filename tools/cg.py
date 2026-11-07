"""Launcher CLI untuk lingkungan yang menjalankan Python secara isolated (`-I`).

Di instalasi Python normal cukup:
    python -m clippergod run ...

Di mesin yang memaksa isolated mode (seperti runtime aplikasi ini), `-m` tidak
menambahkan folder kerja ke sys.path. Skrip ini melakukannya, lalu meneruskan
argumen apa adanya:
    python tools/cg.py run video.mp4 --transcript t.json --out hasil
"""

from __future__ import annotations

import sys
import multiprocessing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clippergod.cli import main  # noqa: E402

if __name__ == "__main__":
    multiprocessing.freeze_support()
    arguments = sys.argv[1:]
    if getattr(sys, "frozen", False) and not arguments:
        arguments = ["ui", "studio"]
    raise SystemExit(main(arguments))
