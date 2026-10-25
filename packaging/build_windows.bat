@echo off
rem Baut die portable Windows-App: dist\ZGmax\ZGmax.exe und ein ZIP davon.
rem Aufruf mit "ohne-tests" (oder ZGMAX_OHNE_TESTS=1): ohne Testlauf bauen.
rem Voraussetzung: Python 3 (python.org, "Add python.exe to PATH"). Auf einem Windows-PC ausfuehren.
setlocal
cd /d "%~dp0\.."
if not exist .venv\Scripts\python.exe (
  rem Zuerst das Python im PATH (in GitHub Actions das von setup-python); "py -3" waehlt sonst das neueste
  rem installierte Python, fuer das es evtl. noch nicht alle Pakete gibt (z. B. onnxruntime)
  python -m venv .venv || py -3 -m venv .venv || goto :fehler
)
.venv\Scripts\python --version
.venv\Scripts\python -m pip install -q --upgrade pip || goto :fehler
.venv\Scripts\python -m pip install -q -r requirements-dev.txt -r requirements-ocr.txt || goto :fehler
if /i "%~1"=="ohne-tests" set ZGMAX_OHNE_TESTS=1
if "%ZGMAX_OHNE_TESTS%"=="1" (
  echo Tests uebersprungen ^(ohne-tests^)
) else (
  .venv\Scripts\python -m pytest -q || goto :fehler
)
if exist dist\ZGmax rmdir /s /q dist\ZGmax
.venv\Scripts\pyinstaller --noconfirm --clean --workpath build\pyinstaller --distpath dist packaging\zgmax.spec || goto :fehler
for /f %%v in ('.venv\Scripts\python -c "import sys; sys.path.insert(0,'programm'); import drawing_viewer as v; print(v.VERSION)"') do set VER=%%v
powershell -NoProfile -Command "Compress-Archive -Force -Path dist\ZGmax -DestinationPath dist\ZGmax-%VER%-Windows-x64.zip" || goto :fehler
echo.
echo Fertig: dist\ZGmax\ZGmax.exe und dist\ZGmax-%VER%-Windows-x64.zip
pause
exit /b 0
:fehler
echo.
echo Der Bau ist fehlgeschlagen (siehe Meldungen oben).
pause
exit /b 1
