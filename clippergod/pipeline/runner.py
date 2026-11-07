"""Orkestrator: transkrip + video → klip vertikal siap posting.

Satu putaran menghasilkan satu folder kerja yang berisi artefak tiap tahap:

    out/
      transcript.json         kata + waktu absolut (sumber kebenaran)
      candidates.json         kandidat + skor + alasan
      run.json                ringkasan: probe, config, hasil per klip
      clips/01_judul/
        clip.json             batas, jalur crop, laporan caption, metadata render
        caption.ass
        clip.mp4

Aturan yang dipegang (docs/SPEC-CLIPPERGOD.md §2):
  3. setiap tahap menghasilkan artefak JSON di disk → bisa diulang tanpa
     mengulang semuanya, dan tahan crash,
  5. preview dan export memakai renderer yang sama (libass),

Karena itu `run()` idempoten: kalau `clip.json` (dan `clip.mp4`) sudah ada,
tahap itu dilewati kecuali `force=True`.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from ..core.boundaries import BoundaryConfig, enforce, extend_for_reaction
from ..core.captions import CaptionStyle, build_ass, build_cues, caption_report, place_cues
from ..core.models import FaceBox, Word
from ..params import ExportConfig, Params
from ..project.schema import fingerprint_file
from ..progress import CancelToken, Progress
from .dna import DnaIndex, clip_dna
from .candidates import CandidateConfig, generate
from .caption_config import CaptionConfig, build_style, force_position
from .faces import FaceScan, OpenCVFaceDetector, scan_video
from .layout import LayoutConfig, PanelCrop, caption_style_for_split, screenshare_panels, split_panels
from .reframe import (
    CropPath,
    ReframeConfig,
    SegmentCrop,
    crop_width,
    median_center,
    plan_crop,
    static_x,
)
from .render import LogoSpec, RenderResult, RenderSpec, probe_video, render
from .speakers import SpeakerTimeline, bind_speakers, speaker_segments

APP_VERSION = "0.2.0"
OUTPUT_FORMATS = {
    "portrait": (1080, 1920),
    "square": (1080, 1080),
    "landscape": (1920, 1080),
}


# ------------------------------------------------------------------ konfigurasi


@dataclass(slots=True)
class RunConfig:
    out_dir: Path
    target: str = "watch"
    limit: int = 5
    fps: int = 30
    sample_fps: float = 6.0
    language: str = "id"
    render_video: bool = True
    force: bool = False
    layout: str = "fill"        # "fill" (crop ikut wajah) atau "split" (panel bertumpuk)
    output_format: str = "portrait"
    caption_strip: int = 260    # hanya dipakai layout split
    candidate_ranges: list[tuple[float, float] | tuple[float, float, str]] | None = None
    preserve_unselected_clips: bool = False
    params: Params | None = None     # config/params.json
    fonts_dir: str | None = None     # folder font untuk libass
    progress: Progress = field(default_factory=Progress)
    cancel: CancelToken | None = None
    detect_reactions: bool = False
    reactions: list[tuple[float, float]] | None = None
    dna_index: Path | None = None
    caption: CaptionConfig | None = None  # override gaya caption dari JSON
    logo: LogoSpec | None = None          # dari brand kit
    avoid_faces: bool = True
    caption_style: CaptionStyle = field(default_factory=CaptionStyle)
    reframe: ReframeConfig = field(default_factory=ReframeConfig)
    boundary: BoundaryConfig = field(default_factory=BoundaryConfig)
    candidate: CandidateConfig = field(default_factory=CandidateConfig)


@dataclass(slots=True)
class RunSummary:
    out_dir: Path
    video: str
    probe: dict[str, Any]
    clips: list[dict[str, Any]]
    skipped: int = 0

    def paths(self) -> list[Path]:
        return [Path(c["dir"]) / "clip.mp4" for c in self.clips if c.get("video")]


# ------------------------------------------------------------------ util


def slugify(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug[:limit].rstrip("-") or "klip")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def words_to_dicts(words: list[Word]) -> list[dict[str, Any]]:
    return [
        {
            "text": w.clean,
            "start": round(w.start, 3),
            "end": round(w.end, 3),
            "prob": round(w.prob, 4),
            **({"speaker": w.speaker} if w.speaker else {}),
        }
        for w in words
    ]


def _cache_signature(video: Path, words: list[Word], cfg: RunConfig,
                     export: ExportConfig, style: CaptionStyle, scan: FaceScan,
                     reactions: list[tuple[float, float]]) -> str:
    stat = video.stat()
    payload = {
        "app_version": APP_VERSION,
        "source": {
            "path": str(video.resolve()),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "fingerprint": fingerprint_file(video),
        },
        "words": words_to_dicts(words),
        "run": {
            "target": cfg.target,
            "limit": cfg.limit,
            "fps": cfg.fps,
            "sample_fps": cfg.sample_fps,
            "language": cfg.language,
            "render_video": cfg.render_video,
            "layout": cfg.layout,
            "output_format": cfg.output_format,
            "caption_strip": cfg.caption_strip,
            "candidate_ranges": cfg.candidate_ranges,
            "detect_reactions": cfg.detect_reactions,
            "reactions": reactions,
            "avoid_faces": cfg.avoid_faces,
            "caption": asdict(cfg.caption) if cfg.caption else None,
            "logo": asdict(cfg.logo) if cfg.logo else None,
            "style": asdict(style),
            "reframe": asdict(cfg.reframe),
            "boundary": asdict(cfg.boundary),
            "candidate": asdict(cfg.candidate),
            "export": asdict(export),
        },
        "face_scan": {
            "width": scan.width,
            "height": scan.height,
            "samples": [
                (t, box.x0, box.y0, box.x1, box.y1, box.track_id)
                for t, box in scan.samples
            ],
        },
    }
    data = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def words_from_dicts(items: list[dict[str, Any]]) -> list[Word]:
    """Terima `text`/`word` dan `prob`/`probability` — dua bentuk yang lazim."""
    out: list[Word] = []
    for item in items:
        text = str(item.get("text", item.get("word", ""))).strip()
        if not text:
            continue
        start = float(item["start"])
        end = float(item.get("end", start))
        out.append(
            Word(
                text=text,
                start=start,
                end=max(start, end),
                prob=float(item.get("prob", item.get("probability", 1.0))),
                speaker=item.get("speaker"),
            )
        )
    out.sort(key=lambda w: w.start)
    return out


def load_transcript(path: str | Path) -> list[Word]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items = raw.get("words") or raw.get("transcript") or raw.get("segments")
    if not isinstance(items, list):
        raise ValueError(
            "transkrip harus berisi 'words' (atau list of words) dengan text/start/end"
        )
    return words_from_dicts(items)


def slice_words(words: list[Word], start: float, end: float) -> list[Word]:
    """Ambil kata di dalam klip, waktunya digeser ke 0 (caption relatif ke klip)."""
    out: list[Word] = []
    for w in words:
        if w.start >= end:
            break
        if w.end <= start:
            continue
        s = max(0.0, w.start - start)
        e = max(s, min(end, w.end) - start)
        out.append(Word(text=w.text, start=s, end=e, prob=w.prob, speaker=w.speaker))
    return out


def _faces_for_cues(
    cues,
    scan: FaceScan,
    clip_start: float,
    path: CropPath | SegmentCrop,
    style: CaptionStyle,
    timeline: SpeakerTimeline | None = None,
) -> dict[int, list[FaceBox]]:
    """Kotak wajah per cue, dipetakan ke koordinat output 1080x1920.

    Kalau cue punya pembicara yang terikat ke track, pakailah wajah pembicara itu —
    bukan wajah mana pun yang kebetulan paling dekat. Inilah bedanya dengan
    pelacakan "track dominan": pertanyaan yang benar adalah "siapa yang bicara",
    bukan "siapa yang paling banyak terlihat".
    """
    if not scan.samples:
        return {}
    sx = style.play_res_x / path.crop_w
    sy = style.play_res_y / path.crop_h
    out: dict[int, list[FaceBox]] = {}
    for idx, cue in enumerate(cues):
        t_mid = (cue.start + cue.end) / 2
        speaker = cue.words[0].speaker if cue.words else None
        track = timeline.track_for(speaker) if timeline else None
        box = scan.nearest(t_mid + clip_start, track)
        if box is None:
            box = scan.nearest(t_mid + clip_start)
        if box is None:
            continue
        cx = path.at(int(round(t_mid * path.fps)))
        out[idx] = [
            FaceBox(
                x0=(box.x0 - cx) * sx, y0=box.y0 * sy,
                x1=(box.x1 - cx) * sx, y1=box.y1 * sy,
            )
        ]
    return out


def _clip_centers(scan: FaceScan, start: float, end: float,
                  track_id: int | None = None) -> list[tuple[float, float]]:
    boxes = scan.boxes(track_id) if track_id is not None else scan.boxes()
    return [(t - start, (b.x0 + b.x1) / 2.0) for t, b in boxes if start <= t <= end]


def _clip_centers_xy(scan: FaceScan, start: float, end: float,
                     track_id: int | None = None) -> list[tuple[float, float, float]]:
    """Titik tengah wajah (t, x, y) relatif ke klip — dipakai layout split."""
    boxes = scan.boxes(track_id) if track_id is not None else scan.boxes()
    return [(t - start, (b.x0 + b.x1) / 2.0, (b.y0 + b.y1) / 2.0)
            for t, b in boxes if start <= t <= end]


# ------------------------------------------------------------------ eksekusi


def _scan_default(
    video: Path, sample_fps: float, cancel=None,
    scan_range: tuple[float, float] | None = None,
) -> FaceScan:
    options = {}
    if scan_range is not None:
        options = {"start_seconds": scan_range[0], "end_seconds": scan_range[1]}
    return scan_video(
        video, OpenCVFaceDetector(), sample_fps=sample_fps, cancel=cancel, **options,
    )


def _split_payload(panels: list[PanelCrop], face_samples: int, mode: str = "split") -> dict[str, Any]:
    return {
        "mode": mode,
        "w": panels[0].crop_w,
        "h": panels[0].crop_h,
        "static": True,
        "face_samples": face_samples,
        "panels": [
            {"crop_w": p.crop_w, "crop_h": p.crop_h, "x": round(p.x, 2),
             "out_h": p.out_h}
            for p in panels
        ],
    }


def _crop_payload(path: CropPath | SegmentCrop, face_samples: int) -> dict[str, Any]:
    base: dict[str, Any] = {
        "w": path.crop_w, "h": path.crop_h, "static": path.static,
        "expression": path.expression(), "face_samples": face_samples,
    }
    if isinstance(path, SegmentCrop):
        base["mode"] = "speaker-cuts"
        base["cuts"] = [
            {"start": round(s, 3), "end": round(e, 3), "x": round(x, 2)}
            for s, e, x in path.segments
        ]
    else:
        base["mode"] = "pan"
        base["x_first"] = round(path.x[0], 2) if path.x else 0.0
        base["degree"] = max(0, len(path.coeffs) - 1)
        base["coeffs"] = [round(c, 6) for c in path.coeffs]
        base["residual_px"] = round(path.residual, 2)
    return base


def run(
    video: str | Path,
    words: list[Word],
    cfg: RunConfig,
    *,
    scanner: Callable[..., FaceScan] | None = None,
    renderer: Callable[..., RenderResult] | None = None,
    log: Callable[[str], None] = print,
) -> RunSummary:
    video = Path(video)
    if cfg.cancel is not None:
        cfg.cancel.raise_if_cancelled()
    if not isinstance(cfg.output_format, str) or cfg.output_format not in OUTPUT_FORMATS:
        raise ValueError(
            f"format output harus salah satu: {', '.join(OUTPUT_FORMATS)}"
        )
    progress = cfg.progress

    if cfg.params is not None:
        cfg.boundary = cfg.params.boundary
        cfg.reframe = cfg.params.reframe
        cfg.candidate = cfg.params.candidate
    export = cfg.params.export if cfg.params else ExportConfig()
    out_w, out_h = OUTPUT_FORMATS[cfg.output_format]
    reframe_cfg = replace(cfg.reframe, out_ratio=out_w / out_h)
    caption_strip = max(120, round(cfg.caption_strip * out_h / 1920))

    fonts_dir = cfg.fonts_dir
    if fonts_dir is None:
        bundled = Path(__file__).resolve().parents[2] / "fonts"
        fonts_dir = str(bundled) if bundled.is_dir() else None
    out = Path(cfg.out_dir)
    clips_dir = out / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    dna_index = DnaIndex.load(cfg.dna_index)

    if not words:
        raise ValueError("transkrip kosong: tidak ada kata untuk dipotong")

    info = probe_video(video)
    progress.start("probe", 1)
    progress.advance()
    _write_json(out / "transcript.json", {
        "app_version": APP_VERSION,
        "video": str(video),
        "language": cfg.language,
        "words": words_to_dicts(words),
    })

    cand_cfg = replace(
        cfg.candidate,
        target=cfg.target,
        max_candidates=max(cfg.limit * 4, 12),
    )
    progress.start("candidates", 1)
    candidates = generate(words, cand_cfg, cfg.boundary)
    if cfg.candidate_ranges is not None:
        selected = [
            (selection[0], selection[1], selection[2] if len(selection) == 3 else None)
            for selection in cfg.candidate_ranges
        ]
        remaining = list(candidates)
        candidates = []
        for start, end, title in selected:
            matches = [
                candidate for candidate in remaining
                if (title is None or title == candidate.title)
                and abs(candidate.start - start) <= max(5.0, (end - start) * 0.2)
                and abs(candidate.end - end) <= max(5.0, (end - start) * 0.2)
            ]
            if matches:
                candidate = min(
                    matches,
                    key=lambda item: abs(item.start - start) + abs(item.end - end),
                )
                candidates.append(candidate)
                remaining.remove(candidate)
        if not candidates:
            raise ValueError("kandidat terpilih tidak ditemukan dalam transkrip")
        cfg.limit = len(candidates)
    progress.advance()
    _write_json(out / "candidates.json", {
        "target": cfg.target,
        "count": len(candidates),
        "candidates": [
            {
                "title": c.title, "start": c.start, "end": c.end,
                "duration": round(c.duration, 3), "score": c.score, "reasons": c.reasons,
                "vps": c.vps,
            }
            for c in candidates
        ],
    })
    log(f"kandidat: {len(candidates)} (target {cfg.target}, {cfg.limit} akan dirender)")

    progress.start("faces", 1)
    scan_range = None
    if cfg.candidate_ranges is not None and len(cfg.candidate_ranges) == 1:
        selected = cfg.candidate_ranges[0]
        scan_range = (selected[0], selected[1])
    scan = (_scan_default(video, cfg.sample_fps, cfg.cancel, scan_range=scan_range)
            if scanner is None else scanner(video, sample_fps=cfg.sample_fps))
    progress.advance()
    log(f"wajah: {len(scan.samples)} deteksi, track dominan #{scan.dominant_track}")

    style = replace(
        cfg.caption_style,
        play_res_x=out_w,
        play_res_y=out_h,
        safe_x0=round(cfg.caption_style.safe_x0 * out_w / cfg.caption_style.play_res_x),
        safe_x1=round(cfg.caption_style.safe_x1 * out_w / cfg.caption_style.play_res_x),
        safe_y0=round(cfg.caption_style.safe_y0 * out_h / cfg.caption_style.play_res_y),
        safe_y1=round(cfg.caption_style.safe_y1 * out_h / cfg.caption_style.play_res_y),
    )
    if cfg.caption is not None:
        style, warnings = build_style(cfg.caption, style)
        for warning in warnings:
            log(f"  catatan caption: {warning}")
    timeline = bind_speakers(words, scan)
    layout_cfg = LayoutConfig(
        mode=cfg.layout, out_w=out_w, out_h=out_h, caption_strip=caption_strip,
    )
    if timeline.bindings:
        # Warna per pembicara mengalah pada warna highlight yang diminta eksplisit:
        # kalau user menulis "highlight" di config, itu yang dipakai.
        if cfg.caption is not None and cfg.caption.highlight:
            log("  catatan caption: warna highlight dari config dipakai, "
                "warna per pembicara diabaikan")
        else:
            style.speaker_colors = timeline.colors()
        bound = len(timeline.bound)
        log(f"speaker: {len(timeline.bindings)} label, {bound} terikat ke wajah"
            + (f", perlu review: {', '.join(timeline.needs_review)}"
               if timeline.needs_review else ""))
    summary = RunSummary(out_dir=out, video=str(video), probe=info, clips=[])
    produced: set[str] = set()

    reactions: list[tuple[float, float]] = list(cfg.reactions or [])
    if cfg.detect_reactions and not reactions:
        progress.start("reactions", 1)
        try:
            from .reactions import detect_reactions

            reactions = [(s, e) for s, e, _kind in detect_reactions(video)]
            log(f"reaksi: {len(reactions)} wilayah (punchline guard)")
        except Exception as exc:  # noqa: BLE001 - deteksi gagal bukan alasan gagal render
            log(f"catatan: deteksi reaksi dilewati ({type(exc).__name__}: {exc})")
        progress.advance()

    run_cache_key = _cache_signature(video, words, cfg, export, style, scan, reactions)
    progress.start("clip", cfg.limit)

    for cand in candidates:
        if cfg.cancel is not None:
            cfg.cancel.raise_if_cancelled()
        if len(summary.clips) >= cfg.limit:
            break

        bounded = enforce(words, cand.start, cand.end, cfg.boundary)
        if bounded.rejected:
            log(f"  lewati '{cand.title}': {bounded.reject_reason}")
            continue

        start, end = bounded.start, bounded.end
        if reactions:
            extended = extend_for_reaction(end, reactions)
            if extended > end + 0.01:
                log(f"  '{cand.title}': akhir +{extended - end:.1f}s untuk reaksi")
                end = extended
        # Jangan pernah minta FFmpeg memotong melewati akhir video: hasilnya lebih
        # pendek dari metadata dan caption terakhir ikut menggantung.
        video_duration = float(info.get("duration") or 0.0)
        if video_duration and end > video_duration:
            log(f"  '{cand.title}': akhir {end:.1f}s melewati video "
                f"({video_duration:.1f}s) — dipotong ke akhir video")
            end = video_duration
        duration = end - start
        if duration < cfg.boundary.min_duration:
            log(f"  lewati '{cand.title}': {duration:.1f}s terlalu pendek")
            continue

        index = len(summary.clips) + 1
        clip_dir = clips_dir / f"{index:02d}_{slugify(cand.title)}"
        produced.add(clip_dir.name)
        clip_json = clip_dir / "clip.json"
        clip_mp4 = clip_dir / "clip.mp4"
        clip_cache_key = hashlib.sha256(json.dumps(
            {
                "run": run_cache_key,
                "candidate": [cand.start, cand.end, cand.title],
                "bounded": [round(start, 3), round(end, 3)],
            },
            ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        ).encode("utf-8")).hexdigest()

        if clip_json.is_file() and not cfg.force:
            if not cfg.render_video or clip_mp4.is_file():
                payload = json.loads(clip_json.read_text(encoding="utf-8"))
                if payload.get("cache_key") != clip_cache_key:
                    payload = None
            else:
                payload = None
            if payload is not None:
                payload["dir"] = str(clip_dir)
                payload["skipped"] = True
                summary.clips.append(payload)
                summary.skipped += 1
                log(f"  {index:02d}. '{cand.title}' sudah ada — dilewati")
                continue

        clip_dir.mkdir(parents=True, exist_ok=True)
        clip_words = slice_words(words, start, end)
        if not clip_words:
            log(f"  lewati '{cand.title}': tidak ada kata di dalam rentang")
            continue

        segs = speaker_segments(words, start, end) if len(timeline.bound) >= 2 else []
        path: CropPath | SegmentCrop
        panels: list[PanelCrop] = []
        clip_style = style
        src_w = scan.width or info["width"]
        src_h = scan.height or info["height"]
        if cfg.layout == "screenshare" and timeline.bound:
            track = timeline.track_for(timeline.bound[0].speaker)
            pts = _clip_centers_xy(scan, start, end, track)
            cx = median_center([(t, x) for t, x, _y in pts]) or src_w / 2.0
            cy = median_center([(t, y) for t, _x, y in pts]) or src_h / 2.0
            panels = screenshare_panels((cx, cy), src_w, src_h, layout_cfg)
            clip_style = caption_style_for_split(style, layout_cfg)
            path = SegmentCrop(
                segments=[(0.0, duration, 0.0)], crop_w=panels[0].crop_w,
                crop_h=panels[0].crop_h, src_w=src_w, src_h=src_h,
                fps=cfg.reframe.fps, static=True,
            )
            log(f"  '{cand.title}': layout layar 70/30 + strip caption")
        elif len({s.speaker for s in segs}) >= 2:
            cw = crop_width(src_w, src_h, reframe_cfg)
            all_centers = _clip_centers(scan, start, end)
            face_samples = len(all_centers)
            fallback = median_center(all_centers) or src_w / 2.0

            if cfg.layout in ("split", "three"):
                order: list[str] = []
                for seg in segs:
                    if seg.speaker and seg.speaker not in order:
                        order.append(seg.speaker)
                centers: list[tuple[float, float]] = []
                want = 3 if cfg.layout == "three" else 2
                if len(order) < want:
                    log(f"  '{cand.title}': hanya {len(order)} pembicara, layout tiga turun ke split")
                for speaker in order[:want]:
                    pts = _clip_centers_xy(scan, start, end, timeline.track_for(speaker))
                    cx = median_center([(t, x) for t, x, _y in pts]) or fallback
                    cy = median_center([(t, y) for t, _x, y in pts]) or src_h / 2.0
                    centers.append((cx, cy))
                panels = split_panels(centers, src_w, src_h, layout_cfg)
                clip_style = caption_style_for_split(style, layout_cfg)
                path = SegmentCrop(
                    segments=[(0.0, duration, 0.0)], crop_w=panels[0].crop_w,
                    crop_h=panels[0].crop_h, src_w=src_w, src_h=src_h,
                    fps=cfg.reframe.fps, static=True,
                )
                log(f"  '{cand.title}': layout {cfg.layout}, {len(panels)} panel "
                    f"({', '.join(f'{s}@{cx:.0f},{cy:.0f}' for s, (cx, cy) in zip(order, centers))})")
            else:
                rows: list[tuple[float, float, float]] = []
                for seg in segs:
                    track = timeline.track_for(seg.speaker)
                    cx = median_center(
                        _clip_centers(scan, start + seg.start, start + seg.end, track)
                    )
                    rows.append((seg.start, seg.end, static_x(cx if cx is not None else fallback,
                                                               cw, src_w)))
                unique_x = {round(r[2], 1) for r in rows}
                path = SegmentCrop(
                    segments=rows, crop_w=cw, crop_h=src_h, src_w=src_w, src_h=src_h,
                    fps=cfg.reframe.fps, static=len(unique_x) == 1,
                )
                segment_labels = ", ".join(
                    f"{segment.speaker or '-'}@{segment.start:.1f}s"
                    for segment in segs
                )
                log(f"  '{cand.title}': {len(rows)} cut mengikuti pembicara "
                    f"({segment_labels})")
        else:
            centers = _clip_centers(scan, start, end)
            face_samples = len(centers)
            if len(centers) < 2:
                log(f"  '{cand.title}': wajah kurang terlihat, crop statis di tengah")
                centers = [(0.0, (scan.width or info["width"]) / 2.0)]
            path = plan_crop(centers, duration, scan.width or info["width"],
                             scan.height or info["height"], reframe_cfg)

        cues = build_cues(clip_words, clip_style)
        faces_by_cue = {} if panels or not cfg.avoid_faces else _faces_for_cues(
            cues, scan, start, path, clip_style, timeline)
        place_cues(cues, clip_style, faces_by_cue,
                   force=force_position(cfg.caption) if cfg.caption else None)
        ass_path = clip_dir / "caption.ass"
        ass_path.write_text(build_ass(cues, clip_style, title=cand.title), encoding="utf-8")
        report = caption_report(cues, clip_style)
        try:
            from .hooks import plan_hooks

            hook_variants = [v.to_dict() for v in plan_hooks(words, start, end, cfg.boundary)]
        except Exception:  # noqa: BLE001 - lab hook tidak boleh menggagalkan klip
            hook_variants = []

        dna = clip_dna(words, start, end)
        duplicates = dna_index.find(dna)
        dna_index.add(dna, title=cand.title, episode=video.stem, start=start, end=end)

        payload: dict[str, Any] = {
            "app_version": APP_VERSION,
            "cache_key": clip_cache_key,
            "index": index,
            "dir": str(clip_dir),
            "output_format": cfg.output_format,
            "output_size": {"width": out_w, "height": out_h},
            "title": cand.title,
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(duration, 3),
            "score": cand.score,
            "reasons": cand.reasons,
            "vps": cand.vps,
            "hook_variants": hook_variants,
            "dna": {**dna.summary(), "duplicates": duplicates},
            "source_candidate": {"start": cand.start, "end": cand.end, "title": cand.title},
            "boundaries": {
                "start": None if bounded.start_boundary is None else {
                    "time": round(bounded.start_boundary.time, 3),
                    "score": bounded.start_boundary.score,
                    "reasons": list(bounded.start_boundary.reasons),
                },
                "end": None if bounded.end_boundary is None else {
                    "time": round(bounded.end_boundary.time, 3),
                    "score": bounded.end_boundary.score,
                    "reasons": list(bounded.end_boundary.reasons),
                },
                "warnings": bounded.warnings,
            },
            "crop": (_split_payload(panels, face_samples, cfg.layout) if panels
                     else _crop_payload(path, face_samples)),
            "speakers": timeline.to_dict() if timeline.bindings else None,
            "speaker_segments": [
                {"start": round(s.start, 3), "end": round(s.end, 3), "speaker": s.speaker}
                for s in segs
            ] if segs else [],
            "captions": {
                "ass": str(ass_path),
                "cues": len(cues),
                "moved_to_top": sum(1 for c in cues if c.placement == "top"),
                **report,
            },
            "logo": None if cfg.logo is None else {
                "path": cfg.logo.path, "position": cfg.logo.position,
                "width_px": cfg.logo.pixel_width(style.play_res_x),
                "opacity": cfg.logo.opacity,
            },
            "video": str(clip_mp4) if cfg.render_video else None,
        }

        if cfg.render_video:
            spec = RenderSpec(
                src=str(video), dst=str(clip_mp4), start=start, duration=duration,
                out_w=out_w, out_h=out_h,
                fps=export.fps, crop_w=path.crop_w, crop_h=path.crop_h,
                crop_x_expr=path.expression(), ass_path=str(ass_path),
                fonts_dir=fonts_dir,
                crf=export.crf, preset=export.preset,
                bitrate_mbps=export.bitrate_mbps, max_bitrate_mbps=export.max_bitrate_mbps,
                audio=True, loudnorm=True,
                layout="split" if panels else "fill", panels=panels,
                logo=cfg.logo,
            )
            result = (render(spec, cancel=cfg.cancel) if renderer is None
                      else renderer(spec))
            payload["render"] = {
                "width": result.width, "height": result.height,
                "duration": result.duration, "size_mb": result.size_mb,
                "passes": result.passes,
                "encoder": getattr(result, "encoder", ""),
                "license": getattr(result, "license", ""),
            }
            if getattr(result, "license", "") == "GPL":
                log("      catatan: encoder GPL (x264) — untuk rilis publik pakai build LGPL")
            # VPS final: ukur dari klip jadi (audio, loop, pacing, bitrate), bukan
            # dari tebakan. Kalau pengukuran gagal, klip tetap disimpan dengan
            # vps_final=None — jangan menurunkan skor karena alat ukurnya rusak.
            try:
                from ..core.boundaries import is_greeting_opening as _greeting
                from ..core.scoring import evaluate as _evaluate
                from .measure import measure_clip

                face_first = (any(start <= t <= start + 0.5 for t, _b in scan.samples)
                              if scan.samples else None)
                signals, measured = measure_clip(
                    clip_mp4, clip_words,
                    face_in_first_frame=face_first,
                    greeting_opening=_greeting(words, start),
                )
                signals.caption_max_cps = float(report["max_cps"])
                signals.caption_violations = len(report["violations"])
                final = _evaluate(signals, measured=set(measured) | {"C"})
                payload["vps_final"] = final.to_dict()
                metrics = {
                    "cut_rate": round(signals.cut_rate_cpm, 1),
                    "loop_ssim": round(signals.loop_similarity, 3),
                    "bitrate_mbps": round(signals.video_bitrate_mbps, 2),
                }
                if "A" in measured:
                    metrics["lufs"] = round(signals.integrated_lufs, 2)
                    metrics["true_peak"] = round(signals.true_peak_dbtp, 2)
                payload["metrics"] = metrics
                checks = {
                    "bitrate_mbps": round(signals.video_bitrate_mbps, 2),
                    "bitrate_ok": signals.video_bitrate_mbps >= 8.0,
                    "resolution_ok": (result.width, result.height) == (1080, 1920),
                    "fps": signals.fps,
                    "fps_ok": signals.fps >= 30,
                    "measured": sorted(set(measured) | {"C"}),
                }
                if "A" in measured:
                    checks["lufs"] = round(signals.integrated_lufs, 2)
                    checks["loudness_ok"] = -15.0 <= signals.integrated_lufs <= -13.0
                    checks["true_peak_dbtp"] = round(signals.true_peak_dbtp, 2)
                    checks["peak_ok"] = signals.true_peak_dbtp <= -1.0
                payload["render"]["checks"] = checks
                log("      vps final " + f"{final.score:.0f} (" + " | ".join(
                    f"{k} {v:.0f}" for k, v in final.components.items()) + ")")
            except Exception as exc:  # noqa: BLE001 - pengukuran tidak boleh menggagalkan render
                payload["vps_final"] = None
                log(f"      catatan: VPS final dilewati ({type(exc).__name__}: {exc})")
            log(f"  {index:02d}. '{cand.title}' -> {clip_mp4.name} "
                f"({result.width}x{result.height}, {result.duration:.1f}s, "
                f"{result.size_mb:.1f} MB)")
        else:
            log(f"  {index:02d}. '{cand.title}' -> caption saja ({len(cues)} cue)")

        _write_json(clip_json, payload)
        summary.clips.append(payload)
        progress.advance()

    # Folder klip dari putaran sebelumnya bisa tertinggal saat judul/urutan berubah.
    # Jangan dihapus (itu data user), tapi laporkan supaya tidak dikira hasil sekarang.
    stale = sorted(
        p.name for p in clips_dir.iterdir()
        if p.is_dir() and re.match(r"^\d{2}_", p.name) and p.name not in produced
    ) if clips_dir.is_dir() else []
    if stale:
        log(f"catatan: {len(stale)} folder klip lama tidak dipakai putaran ini "
            f"({', '.join(stale[:3])}{'...' if len(stale) > 3 else ''})")

    project_path = None
    if cfg.dna_index:
        dna_index.save(cfg.dna_index)
        log(f"dna: {len(dna_index.entries)} klip di {cfg.dna_index}")
    from .bridge import build_project, save_project

    project_path = save_project(
        build_project(
            video, words, info, summary.clips,
            name=video.stem,
            layout=cfg.layout,
            speakers=timeline.to_dict() if timeline.bindings else None,
            export={"fps": export.fps, "crf": export.crf, "preset": export.preset,
                    "bitrate_mbps": export.bitrate_mbps,
                    "max_bitrate_mbps": export.max_bitrate_mbps,
                    "format": cfg.output_format,
                    "width": out_w, "height": out_h},
        ),
        out,
        preserve_unmatched=cfg.preserve_unselected_clips,
    )
    log(f"proyek: {project_path.name} ({len(summary.clips)} klip)")

    _write_json(out / "run.json", {
        "app_version": APP_VERSION,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "video": str(video),
        "probe": info,
        "config": {
            "target": cfg.target, "limit": cfg.limit, "fps": cfg.fps,
            "sample_fps": cfg.sample_fps, "language": cfg.language,
            "render_video": cfg.render_video, "layout": cfg.layout,
            "output_format": cfg.output_format,
            "output_size": {"width": out_w, "height": out_h},
            "detect_reactions": cfg.detect_reactions,
            "reactions": len(reactions),
            "export": {"fps": export.fps, "crf": export.crf, "preset": export.preset,
                       "bitrate_mbps": export.bitrate_mbps,
                       "max_bitrate_mbps": export.max_bitrate_mbps},
        },
        "count": len(summary.clips),
        "skipped": summary.skipped,
        "stale_dirs": stale,
        "project": str(project_path) if project_path else None,
        "clips": [
            {k: v for k, v in c.items() if k not in {"reasons", "boundaries"}}
            for c in summary.clips
        ],
    })
    return summary
