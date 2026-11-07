"""Unduh model deteksi wajah YuNet (232 KB) ke `models/`.

Jalankan sekali:  python tools/fetch_face_model.py

Model tidak di-commit ke repo karena ini biner. Skrip ini memverifikasi SHA-256
supaya file yang dipakai benar-benar model resmi OpenCV Zoo, bukan halaman error
GitHub (raw.githubusercontent mengembalikan pointer LFS, bukan bobotnya).
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clippergod.pipeline.faces import (  # noqa: E402
    YUNET_FILENAME,
    YUNET_SHA256,
    yunet_model_path,
)

# URL LFS langsung: raw.githubusercontent hanya memberi pointer teks.
URL = (
    "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
    "models/face_detection_yunet/" + YUNET_FILENAME
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    existing = yunet_model_path()
    if existing is not None and sha256(existing) == YUNET_SHA256:
        print(f"sudah ada & terverifikasi: {existing}")
        return 0

    dst = ROOT / "models" / YUNET_FILENAME
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(".part")

    print(f"mengunduh {YUNET_FILENAME} ...", end=" ", flush=True)
    try:
        with urllib.request.urlopen(URL, timeout=120) as resp, tmp.open("wb") as fh:
            fh.write(resp.read())
    except Exception as exc:  # noqa: BLE001 - pesan harus jelas untuk user
        tmp.unlink(missing_ok=True)
        print("gagal")
        print(f"  {exc}")
        print(f"  unduh manual dari: {URL}")
        print(f"  lalu taruh sebagai: {dst}")
        return 1

    got = sha256(tmp)
    if got != YUNET_SHA256:
        tmp.unlink(missing_ok=True)
        print("gagal")
        print(f"  sha256 tidak cocok: {got}")
        print(f"  diharapkan         : {YUNET_SHA256}")
        return 1

    tmp.replace(dst)
    print(f"ok ({dst.stat().st_size / 1024:.0f} KB, sha256 terverifikasi)")
    print(f"  {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
