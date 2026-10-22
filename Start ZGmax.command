#!/bin/bash
# Startet ZGmax (macOS/Linux).
# Einmalig ausfuehrbar machen:  chmod +x "Start ZGmax.command"
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  python3 programm/launcher.py "$@"
else
  echo "Python 3 wurde nicht gefunden. Bitte installieren: https://www.python.org/downloads/"
  open "https://www.python.org/downloads/" 2>/dev/null
  read -n 1 -s -r -p "Taste druecken zum Beenden ..."
  exit 1
fi
