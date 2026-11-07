"""Verifikasi klip berlayout split: dua wajah, satu per panel, caption di strip.

Jalankan:  python tools/verify_layout.py <run_dir>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clippergod.pipeline.faces import OpenCVFaceDetector  # noqa: E402
from clippergod.pipeline.render import probe_video  # noqa: E402

POS = re.compile(r"\\pos\((\d+),(\d+)\)")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    run_dir = Path(sys.argv[1])
    clip_dirs = sorted(p for p in (run_dir / "clips").iterdir() if p.is_dir())
    if not clip_dirs:
        print("tidak ada klip", file=sys.stderr)
        return 1

    ok_all = True
    for clip_dir in clip_dirs:
        clip = json.loads((clip_dir / "clip.json").read_text(encoding="utf-8"))
        video = Path(clip["video"])
        meta = probe_video(video)
        panels = clip["crop"].get("panels", [])
        strip_top = meta["height"] - 260

        print(f"{clip_dir.name}")
        print(f"   mode {clip['crop']['mode']}, {len(panels)} panel, "
              f"{meta['width']}x{meta['height']}")

        # 1. caption di strip bawah
        ass = Path(clip["captions"]["ass"]).read_text(encoding="utf-8")
        ys = [int(y) for _x, y in POS.findall(ass)]
        in_strip = all(y >= strip_top for y in ys) if ys else False
        print(f"   caption \\pos y: {min(ys) if ys else '-'}..{max(ys) if ys else '-'} "
              f"(strip mulai {strip_top}) {'OK' if in_strip else 'MELESET'}")

        # 2. dua wajah, satu di tiap panel
        cap = cv2.VideoCapture(str(video))
        detector = OpenCVFaceDetector()
        top_hit = bottom_hit = 0
        checked = 0
        for frac in (0.2, 0.45, 0.7):
            cap.set(cv2.CAP_PROP_POS_MSEC, frac * meta["duration"] * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            checked += 1
            for box in detector.detect(frame):
                cy = (box.y0 + box.y1) / 2
                if cy < meta["height"] / 2:
                    top_hit += 1
                else:
                    bottom_hit += 1
        cap.release()
        two_panels = top_hit >= checked and bottom_hit >= checked and checked > 0
        print(f"   {checked} frame diuji: wajah panel atas {top_hit}, bawah {bottom_hit} "
              f"{'OK' if two_panels else 'TIDAK'}")

        ok_all = ok_all and in_strip and two_panels

    print()
    print(f"putusan: {'LULUS' if ok_all else 'PERLU REVIEW'}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
