#!/bin/bash
# Baut die portable Linux-App: dist/ZGmax/ZGmax und dist/ZGmax-<version>-Linux-<arch>.tar.gz
# Voraussetzung: Python 3 mit venv. Fuer die Tests ohne Bildschirm: QT_QPA_PLATFORM=offscreen und die Qt-Grundpakete
# (z. B. Ubuntu: libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3). Die App laeuft auf Linux-Systemen mit
# derselben Prozessorart und einer gleich alten oder neueren glibc wie das Bau-System.
set -euo pipefail
cd "$(dirname "$0")/.."
ARCH=$(uname -m)
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements-dev.txt -r requirements-ocr.txt
QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen} .venv/bin/python -m pytest -q
rm -rf build/pyinstaller dist/ZGmax
.venv/bin/pyinstaller --noconfirm --clean --workpath build/pyinstaller --distpath dist packaging/zgmax.spec
VER=$(.venv/bin/python -c "import sys; sys.path.insert(0,'programm'); import drawing_viewer as v; print(v.VERSION)")
TGZ="dist/ZGmax-${VER}-Linux-${ARCH}.tar.gz"
rm -f "$TGZ"
tar -C dist -czf "$TGZ" ZGmax
echo "Fertig: dist/ZGmax/ZGmax  und  $TGZ"
