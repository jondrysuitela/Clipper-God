"""Antarmuka baris perintah ClipperGod.

    python -m clippergod run video.mp4 --transcript transkrip.json --out hasil
    python -m clippergod transcribe video.mp4 --out transkrip.json --model small

Semua perintah menulis artefak JSON ke disk; tidak ada yang hanya hidup di memori.
"""

from __future__ import annotations

import argparse
import multiprocessing
import json
import sys
import tempfile
from pathlib import Path

from .pipeline.runner import OUTPUT_FORMATS, RunConfig, load_transcript, run, words_to_dicts


def _cmd_run(args: argparse.Namespace) -> int:
    from .pipeline.brand import from_file as brand_from_file
    from .pipeline.caption_config import from_file as caption_from_file
    from .params import load_or_default

    try:
        params = load_or_default(args.params)
    except (OSError, ValueError) as exc:
        print(f"params tidak valid: {exc}", file=sys.stderr)
        return 2

    words = load_transcript(args.transcript)
    if not words:
        print(f"transkrip kosong: {args.transcript}", file=sys.stderr)
        return 2

    brand = None
    if args.brand:
        try:
            brand = brand_from_file(args.brand)
        except (OSError, ValueError) as exc:
            print(f"brand tidak valid: {exc}", file=sys.stderr)
            return 2
        print(f"brand: {brand.name}"
              + (" + logo" if brand.logo else "")
              + (" + caption" if brand.caption else ""))

    caption_cfg = brand.caption if brand else None
    if args.caption:
        try:
            caption_cfg = caption_from_file(args.caption)
        except (OSError, ValueError) as exc:
            print(f"config caption tidak valid: {exc}", file=sys.stderr)
            return 2

    cfg = RunConfig(
        out_dir=Path(args.out),
        target=args.target,
        limit=args.limit,
        language=args.language,
        render_video=not args.no_render,
        force=args.force,
        layout=args.layout,
        output_format=args.format,
        caption=caption_cfg,
        logo=brand.logo if brand else None,
        params=params,
        detect_reactions=args.detect_reactions,
        dna_index=Path(args.dna_index) if args.dna_index else None,
    )
    summary = run(args.video, words, cfg)

    print()
    print(f"{len(summary.clips)} klip di {summary.out_dir}"
          + (f" ({summary.skipped} dilewati karena sudah ada)" if summary.skipped else ""))
    for clip in summary.clips:
        line = f"  {clip['index']:02d}. {clip['title']}  [{clip['duration']:.1f}s"
        if clip.get("render"):
            line += f", {clip['render']['width']}x{clip['render']['height']}"
        line += f", skor {clip['score']}]"
        print(line)
    print(f"ringkasan: {Path(args.out) / 'run.json'}")
    return 0


def _cmd_transcribe(args: argparse.Namespace) -> int:
    from .pipeline.asr import FasterWhisperTranscriber, SetupError, extract_audio

    video = Path(args.video)
    if not video.is_file():
        print(f"video tidak ditemukan: {video}", file=sys.stderr)
        return 2

    try:
        with tempfile.TemporaryDirectory(prefix="clippergod-asr-") as tmp:
            audio = extract_audio(video, Path(tmp) / "audio16k.wav")
            transcriber = FasterWhisperTranscriber(model_size=args.model)
            words = transcriber.transcribe(audio, language=args.language)

            diar_payload = None
            if args.diarize and words:
                from .pipeline.diarize import diarize_file, label_words
                diar = diarize_file(audio, k=args.speakers)
                words = label_words(words, diar)
                diar_payload = diar.to_dict()
    except SetupError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    if not words:
        print("tidak ada kata yang dikenali", file=sys.stderr)
        return 4

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "video": str(video),
        "language": args.language,
        "model": args.model,
        "words": words_to_dicts(words),
    }
    if diar_payload:
        payload["diarization"] = diar_payload
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    dur = words[-1].end
    speakers = {w.speaker for w in words if w.speaker}
    extra = f", {len(speakers)} pembicara" if speakers else ""
    print(f"{len(words)} kata, {dur:.1f}s{extra}, disimpan ke {out}")
    return 0


def _cmd_probe(args: argparse.Namespace) -> int:
    from .pipeline.render import probe_video

    info = probe_video(args.video)
    for key, value in info.items():
        print(f"{key:9s}: {value}")
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    from .pipeline.media import MediaError, import_media
    from .pipeline.render import RenderError

    try:
        result = import_media(args.video, args.out, force=args.force)
    except (MediaError, RenderError, OSError, ValueError) as exc:
        print(f"import gagal: {exc}", file=sys.stderr)
        return 2

    probe = result.probe
    print(f"sumber : {result.source}")
    print(f"video  : {probe['width']}x{probe['height']}, {probe['duration']:.1f}s, {probe['fps']:.2f} fps")
    print(f"proxy  : {result.proxy or 'tidak perlu (sumber sudah kecil)'}")
    print(f"proyek : {result.project}")
    if result.rotation:
        print(f"catatan: metadata rotasi {result.rotation}° tidak diterapkan — "
              "koordinat wajah mengikuti piksel asli")
    if result.vfr:
        print("catatan: sumber VFR; transcode ke CFR belum dilakukan")
    return 0


def _cmd_ui(args: argparse.Namespace) -> int:
    from .server import serve

    target = Path(args.project)
    if target.suffix == ".cgproj":
        if not target.is_file():
            print(f"proyek tidak ditemukan: {target}", file=sys.stderr)
            return 2
        folder = target.parent
    else:
        folder = target
        folder.mkdir(parents=True, exist_ok=True)
    serve(folder, port=args.port)
    return 0


def _cmd_batch(args: argparse.Namespace) -> int:
    from .pipeline.batch import ManifestError, run_batch

    try:
        report = run_batch(
            args.manifest,
            args.out,
            force=args.force,
            max_attempts=args.attempts,
            stop_on_error=args.stop_on_error,
            render_video=not args.no_render,
        )
    except ManifestError as exc:
        print(f"manifest tidak valid: {exc}", file=sys.stderr)
        return 2

    print()
    print(f"{report.done}/{len(report.states)} job selesai, {report.failed} gagal, "
          f"{report.clips} klip")
    for state in report.states:
        mark = {"done": "OK  ", "failed": "GAGAL", "pending": "-",
                "running": "..."}.get(state.status, state.status)
        line = f"  {mark} {state.id:16s} {state.clips:2d} klip"
        if state.error:
            line += f"  {state.error}"
        print(line)
    print(f"antrean: {Path(args.out) / 'queue.json'}")
    return 0 if report.failed == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clippergod",
        description="Clipper video offline: video panjang -> klip vertikal siap posting.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="potong video jadi klip memakai transkrip JSON")
    run_p.add_argument("video", help="file video sumber")
    run_p.add_argument("--transcript", required=True, help="JSON berisi words[{text,start,end}]")
    run_p.add_argument("--out", required=True, help="folder kerja untuk artefak + hasil")
    run_p.add_argument("--target", default="watch", choices=["reach", "watch", "story"])
    run_p.add_argument("--limit", type=int, default=5, help="jumlah klip yang dirender")
    run_p.add_argument("--language", default="id")
    run_p.add_argument("--no-render", action="store_true",
                       help="hanya batas + caption + JSON, tanpa FFmpeg")
    run_p.add_argument("--layout", default="fill",
                       choices=["fill", "split", "three", "screenshare"],
                       help="fill: crop ikut wajah; split: dua panel; three: tiga panel; "
                            "screenshare: layar 70% + strip wajah")
    run_p.add_argument("--format", default="portrait", choices=OUTPUT_FORMATS,
                       help="format output: portrait 1080x1920, square 1080x1080, "
                            "landscape 1920x1080")
    run_p.add_argument("--caption", help="JSON gaya caption (font, warna, posisi, dll)")
    run_p.add_argument("--brand", help="JSON brand kit (caption + logo)")
    run_p.add_argument("--params", help="JSON parameter mesin (default: config/params.json bila ada)")
    run_p.add_argument("--no-reactions", dest="detect_reactions", action="store_false",
                       help="matikan punchline guard (deteksi tawa/aplaus)")
    run_p.add_argument("--dna-index", help="JSON indeks DNA untuk cek duplikat lintas episode")
    run_p.add_argument("--force", action="store_true", help="render ulang walau sudah ada")
    run_p.set_defaults(func=_cmd_run)

    tr_p = sub.add_parser("transcribe", help="video -> transkrip kata (faster-whisper)")
    tr_p.add_argument("video")
    tr_p.add_argument("--out", required=True)
    tr_p.add_argument("--model", default="small", help="small/medium/large-v3-turbo")
    tr_p.add_argument("--language", default="id")
    tr_p.add_argument("--diarize", action="store_true",
                      help="tandai pembicara (VAD energi + pitch, baseline)")
    tr_p.add_argument("--speakers", type=int, default=2,
                      help="jumlah pembicara untuk diarisasi")
    tr_p.set_defaults(func=_cmd_transcribe)

    pr_p = sub.add_parser("probe", help="tampilkan metadata video")
    pr_p.add_argument("video")
    pr_p.set_defaults(func=_cmd_probe)

    ba_p = sub.add_parser("batch", help="proses banyak video dari manifest JSON")
    ba_p.add_argument("manifest", help="JSON berisi jobs[{id,video,transcript,...}]")
    ba_p.add_argument("--out", required=True, help="folder antrean + hasil per job")
    ba_p.add_argument("--attempts", type=int, default=2, help="percobaan maksimal per job")
    ba_p.add_argument("--force", action="store_true", help="proses ulang walau sudah selesai")
    ba_p.add_argument("--stop-on-error", action="store_true")
    ba_p.add_argument("--no-render", action="store_true", help="tanpa FFmpeg")
    ba_p.set_defaults(func=_cmd_batch)

    ui_p = sub.add_parser("ui", help="studio lokal: pilih video -> klip")
    ui_p.add_argument("project", help="folder proyek (dibuat bila belum ada) atau file .cgproj")
    ui_p.add_argument("--port", type=int, default=0, help="0 = pilih port bebas")
    ui_p.set_defaults(func=_cmd_ui)

    im_p = sub.add_parser("import", help="siapkan proyek + proxy 540p dari video")
    im_p.add_argument("video")
    im_p.add_argument("--out", required=True, help="folder proyek + proxy")
    im_p.add_argument("--force", action="store_true", help="timpa proyek yang sudah ada")
    im_p.set_defaults(func=_cmd_import)

    return parser


def main(argv: list[str] | None = None) -> int:
    multiprocessing.freeze_support()
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\ndibatalkan", file=sys.stderr)
        return 130
    except (ValueError, FileNotFoundError) as exc:
        print(f"gagal: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
