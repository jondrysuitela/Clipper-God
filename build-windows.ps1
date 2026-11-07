param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

try {
    $VersionText = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not run Python executable '$Python'."
    }
    $Version = [version]$VersionText
    if ($Version -lt [version]"3.11") {
        throw "Python 3.11 or newer is required (found $VersionText)."
    }

    & $Python -c "import PyInstaller, cv2, numpy, faster_whisper, yt_dlp, imageio_ffmpeg"
    if ($LASTEXITCODE -ne 0) {
        throw "Build dependencies are missing. Run: $Python -m pip install -r requirements-build.txt"
    }

    & $Python -m PyInstaller --clean --noconfirm `
        --distpath (Join-Path $Root "dist") `
        --workpath (Join-Path $Root "build\pyinstaller") `
        (Join-Path $Root "ClipperGod.spec")
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed."
    }

    $App = Join-Path $Root "dist\ClipperGod\ClipperGod.exe"
    if (-not (Test-Path $App)) {
        throw "Build completed without the expected executable: $App"
    }
    Write-Host "Built one-folder app: $App"
} catch {
    Write-Error $_
    exit 1
}
