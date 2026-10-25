#!/bin/bash
# Baut die portable macOS-App: dist/ZGmax.app und dist/ZGmax-macOS-<arch>.zip
# Voraussetzung: Python 3 (python.org). Die App laeuft auf Macs mit derselben Prozessorart (Apple-Chip = arm64,
# Intel = x86_64) wie der Bau-Mac.
# Aufruf mit --ohne-tests (oder ZGMAX_OHNE_TESTS=1): ohne Testlauf bauen, z. B. fuer einen schnellen Probebau.
set -euo pipefail
cd "$(dirname "$0")/.."
ARCH=$(uname -m)
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements-dev.txt -r requirements-ocr.txt
if [ "${1:-}" = "--ohne-tests" ] || [ "${ZGMAX_OHNE_TESTS:-0}" = "1" ]; then
  echo "Tests uebersprungen (--ohne-tests)"
else
  .venv/bin/python -m pytest -q
fi
rm -rf build/pyinstaller dist/ZGmax dist/ZGmax.app
.venv/bin/pyinstaller --noconfirm --clean --workpath build/pyinstaller --distpath dist packaging/zgmax.spec
rm -rf dist/ZGmax                       # nur das .app-Paket weitergeben
codesign --force --deep --sign - dist/ZGmax.app   # Ad-hoc-Signatur (ohne Apple-Entwicklerkonto)
VER=$(.venv/bin/python -c "import sys; sys.path.insert(0,'programm'); import drawing_viewer as v; print(v.VERSION)")
ZIP="dist/ZGmax-${VER}-macOS-${ARCH}.zip"
rm -f "$ZIP"
ditto -c -k --keepParent dist/ZGmax.app "$ZIP"
echo "Fertig: dist/ZGmax.app  und  $ZIP"
