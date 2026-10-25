#!/bin/bash
# Einrichtung fuer eine Linux-Cloud-Umgebung (Claude Code im Web): Qt-Systempakete, .venv mit allen Paketen.
set -euo pipefail
cd "$(dirname "$0")/.."
if command -v apt-get >/dev/null; then
  SUDO=$(command -v sudo || true)
  $SUDO apt-get update -qq || true
  $SUDO apt-get install -y -qq libegl1 libgl1 libxkbcommon0 libxkbcommon-x11-0 libfontconfig1 libdbus-1-3 \
    fonts-dejavu-core >/dev/null || true
fi
PY=$(command -v python3.14 || command -v python3)
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements-dev.txt -r requirements-ocr.txt
echo "Fertig. Tests: QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q"
