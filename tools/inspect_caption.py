"""Ringkas isi file ASS + clip.json tanpa membuka gambar.

Jalankan:  python tools/inspect_caption.py <clip_dir>
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

STYLE = re.compile(r"^Style: Cap,(?P<font>[^,]+),(?P<size>\d+),(?P<primary>[^,]+),"
                   r"(?P<secondary>[^,]+)")
ANCHOR = re.compile(r"\\an(\d)")
POS = re.compile(r"\\pos\((\d+),(\d+)\)")
TAG = re.compile(r"\{[^}]*\}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    run_dir = Path(sys.argv[1])
    for clip_dir in sorted(p for p in (run_dir / "clips").iterdir() if p.is_dir()):
        clip = json.loads((clip_dir / "clip.json").read_text(encoding="utf-8"))
        ass = Path(clip["captions"]["ass"]).read_text(encoding="utf-8")

        style = None
        for line in ass.splitlines():
            match = STYLE.match(line)
            if match:
                style = match.groupdict()
                break

        dialogue = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
        texts = [TAG.sub("", l.split(",", 9)[-1]).strip() for l in dialogue]
        anchors = Counter(m.group(1) for m in ANCHOR.finditer(ass))
        pos_y = sorted({int(m.group(2)) for m in POS.finditer(ass)})
        has_kf = "\\kf" in ass

        print(f"{clip_dir.name}")
        print(f"   font        : {style['font']} {style['size']} px"
              if style else "   font        : (tidak terbaca)")
        print(f"   warna       : teks {style['primary']}, highlight {style['secondary']}"
              if style else "   warna       : -")
        print(f"   anchor \\an  : {dict(anchors)}   pos y: {pos_y}")
        print(f"   karaoke     : {'ya' if has_kf else 'tidak'}   cue: {len(dialogue)}")
        print(f"   contoh teks : {texts[0] if texts else '-'}")
        caption = clip["captions"]
        over = caption.get("over_cap", 0)
        print(f"   CPS maks    : {caption['max_cps']} (di atas cap: {over} cue)"
              f"   kata/cue: {caption['words_per_cue']}   pelanggaran: {len(caption['violations'])}"
              f"   catatan: {len(caption.get('notes', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
