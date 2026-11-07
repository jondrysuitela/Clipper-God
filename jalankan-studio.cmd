@echo off
rem ClipperGod Studio - launcher Windows
rem Cari Python yang benar, lalu jalankan server dan buka browser.

setlocal
cd /d "%~dp0"

set "PY="
python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul && set "PY=python"
if not defined PY if exist "%LOCALAPPDATA%\Programs\AutoClaw2\resources\vendor\python\python.exe" set "PY=%LOCALAPPDATA%\Programs\AutoClaw2\resources\vendor\python\python.exe"
if not defined PY if exist "C:\Users\HP\AppData\Local\Programs\AutoClaw2\resources\vendor\python\python.exe" set "PY=C:\Users\HP\AppData\Local\Programs\AutoClaw2\resources\vendor\python\python.exe"

if not defined PY (
  echo.
  echo Python tidak ditemukan di PATH.
  echo Pasang Python 3.11 atau lebih baru dari https://www.python.org/downloads/ ^(centang "Add to PATH"^),
  echo lalu jalankan: pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

"%PY%" -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul
if errorlevel 1 (
  echo.
  echo ClipperGod memerlukan Python 3.11 atau lebih baru.
  echo Interpreter yang ditemukan terlalu lama atau tidak bisa dijalankan.
  echo.
  pause
  exit /b 1
)

if not exist "studio" mkdir "studio"

start "ClipperGod Studio" cmd /k ""%PY%" tools\cg.py ui studio --port 8765"
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8765/

echo.
echo Studio dibuka di http://127.0.0.1:8765/
echo Tutup jendela "ClipperGod Studio" untuk menghentikan server.
echo.
pause
