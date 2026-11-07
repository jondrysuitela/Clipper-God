# PyInstaller one-folder build for Windows.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all
import imageio_ffmpeg


ROOT = Path(SPECPATH).resolve()
datas = []
binaries = []
hiddenimports = [
    "cv2",
    "numpy",
    "faster_whisper",
    "yt_dlp",
    "ctranslate2",
    "av",
    "tokenizers",
]

# These packages use native extensions, lazy imports, and runtime package data.
for package in ("cv2", "numpy", "faster_whisper", "yt_dlp", "ctranslate2"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

# The HTTP server resolves UI_FILE relative to clippergod/server.py, so preserve
# the repository's ui/ and fonts/ paths under PyInstaller's data directory.
for directory in ("ui", "fonts", "config", "models"):
    source = ROOT / directory
    if source.is_dir():
        for path in source.rglob("*"):
            if path.is_file():
                datas.append((str(path), str(path.relative_to(ROOT).parent)))

# imageio-ffmpeg is used as the bundled FFmpeg fallback by the render pipeline.
ffmpeg_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
binaries.append((str(ffmpeg_exe), "imageio_ffmpeg/binaries"))

hiddenimports = sorted(set(hiddenimports))
datas = list(dict.fromkeys(datas))
binaries = list(dict.fromkeys(binaries))

a = Analysis(
    [str(ROOT / "tools" / "cg.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "torchaudio", "ollama"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ClipperGod",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ClipperGod",
)
