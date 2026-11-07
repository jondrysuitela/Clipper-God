"""Pipeline media: transkrip, kandidat, wajah, reframe, render.

Semua modul di sini boleh bergantung pada dependensi berat (OpenCV, FFmpeg,
model) tapi harus memuatnya dengan malas: impor paket ini tidak boleh menyeret
model atau GPU.
"""

__all__ = ["asr", "candidates", "faces", "reframe", "render", "runner", "speakers"]
