"""Bangun audio ucapan sungguhan dengan voice TTS Windows (16 kHz mono).

Dipakai untuk menguji jalur ASR tanpa memakai rekaman orang lain. Yang penting:
audio ini benar-benar berisi ucapan, bukan tone — jadi Whisper harus benar-benar
mendengarkan, dan hasil transkripnya bisa dibandingkan dengan teks aslinya.

Jalankan:  python tools/make_speech.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo" / "asr"

VOICES = {
    "S1": "Microsoft David Desktop",   # pria
    "S2": "Microsoft Zira Desktop",    # wanita
}

#: (pembicara, kalimat). Sengaja tanpa apostrof supaya aman masuk PowerShell.
LINES: list[tuple[str, str]] = [
    ("S1", "Most podcasts lose viewers in the first three seconds."),
    ("S2", "The problem is not the algorithm. It is a weak opening."),
    ("S1", "Ask a sharp question before you explain anything."),
    ("S2", "Cut the clip at the end of a sentence, never in the middle."),
    ("S1", "Captions should follow the transcript, not a separate timeline."),
    ("S2", "And the camera should follow the person who is actually speaking."),
]

GAP_SECONDS = 0.55
SAMPLE_RATE = 16000


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def synthesize(workdir: Path) -> list[Path]:
    """Tiap kalimat jadi satu WAV lewat SAPI; satu panggilan PowerShell untuk semua."""
    script_lines = [
        "Add-Type -AssemblyName System.Speech",
        "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo"
        "(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, "
        "[System.Speech.AudioFormat.AudioChannel]::Mono)",
        "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer",
    ]
    paths: list[Path] = []
    for i, (speaker, text) in enumerate(LINES, start=1):
        wav = workdir / f"s{i:02d}.wav"
        paths.append(wav)
        script_lines += [
            f"$synth.SelectVoice({_ps_quote(VOICES[speaker])})",
            f"$synth.SetOutputToWaveFile({_ps_quote(str(wav))}, $fmt)",
            f"$synth.Speak({_ps_quote(text)})",
            "$synth.SetOutputToNull()",
        ]
    script_lines.append("$synth.Dispose()")

    script = workdir / "tts.ps1"
    script.write_text("\n".join(script_lines), encoding="utf-8")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", str(script)], check=True, capture_output=True)
    return paths


def concat(paths: list[Path], dst: Path, gap: float = GAP_SECONDS) -> dict:
    """Gabung WAV + jeda, kembalikan timeline per kalimat (untuk evaluasi WER)."""
    silence = b"\x00\x00" * int(SAMPLE_RATE * gap)
    timeline = []
    t = 0.0
    with wave.open(str(dst), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        for i, path in enumerate(paths):
            with wave.open(str(path), "rb") as src:
                if src.getframerate() != SAMPLE_RATE or src.getnchannels() != 1:
                    raise SystemExit(
                        f"{path.name}: format tak terduga "
                        f"({src.getframerate()} Hz, {src.getnchannels()} ch)"
                    )
                frames = src.readframes(src.getnframes())
                dur = src.getnframes() / src.getframerate()
            speaker, text = LINES[i]
            timeline.append({"speaker": speaker, "text": text,
                             "start": round(t, 3), "end": round(t + dur, 3)})
            out.writeframes(frames)
            t += dur
            if i < len(paths) - 1:
                out.writeframes(silence)
                t += gap
    return {"duration": round(t, 3), "lines": timeline}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cg-tts-") as tmp:
        parts = synthesize(Path(tmp))
        meta = concat(parts, OUT / "speech.wav")

    import json
    (OUT / "ground_truth.json").write_text(json.dumps({
        "sample_rate": SAMPLE_RATE,
        "voices": VOICES,
        **meta,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"audio: {OUT / 'speech.wav'}  {meta['duration']:.1f}s")
    for line in meta["lines"]:
        print(f"  {line['speaker']} {line['start']:5.2f}-{line['end']:5.2f}  {line['text']}")


if __name__ == "__main__":
    sys.exit(main())
