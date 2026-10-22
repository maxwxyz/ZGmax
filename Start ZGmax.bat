@echo off
rem Startet ZGmax (Doppelklick genuegt).
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python wurde nicht gefunden.
  echo Bitte einmalig installieren: https://www.python.org/downloads/
  echo Wichtig: Beim Installieren "Add python.exe to PATH" ankreuzen.
  start "" https://www.python.org/downloads/
  pause
  exit /b 1
)
%PY% "programm\launcher.py" %*
if errorlevel 1 pause
