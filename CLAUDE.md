# ZGmax – Hinweise für Claude

Viewer, Vergleichs- und Markup-Programm für technische Zeichnungen (Python 3.14, PySide6 6.12, OpenCV, PyMuPDF).
Code in `programm/`, Tests in `tests/`, Bau in `packaging/`. **Vor jeder Arbeit `HANDOFF.md` lesen** (offene Aufgaben).

## Regeln
- Nutzer schreibt Deutsch; Antworten auf Deutsch. Oberfläche deutsch, Übersetzung in `programm/i18n_en.json`
  (alle neuen `tr("...")`-Texte eintragen; Prüfung: `.venv/bin/python tests/english_check.py` muss `ENGLISH-OK` ausgeben).
  JSON schreiben mit `json.dumps(d, ensure_ascii=False, indent=0, sort_keys=True)` ohne Zeilenende am Schluss.
- Kommentare/Docstrings im Code deutsch ohne Umlaute (ae, oe, ue), Stil wie im umgebenden Code.
- Anleitungen pflegen: `programm/Anleitung_Viewer.html` (DE) und `programm/Manual_Viewer.html` (EN).
- Änderungshistorie: jede für Nutzer sichtbare Änderung im selben Commit in `programm/CHANGELOG.json` unter
  `unreleased` eintragen (`de` und `en`, gleiche Reihenfolge, kurz, aus Nutzersicht). Version = neuester Eintrag in
  `releases` (App liest ihn, `version.py`). Release: `.venv/bin/python packaging/release.py minor|patch|major --git`
  (schreibt auch `CHANGELOG.md`/`CHANGELOG_EN.md`, setzt Tag `v<version>`), danach Apps bauen.
- Commits enden mit `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. **Nach jedem Commit pushen**
  (`origin` = github.com/maxwxyz/ZGmax, privat).
- Hilfsskripte dürfen nie die echten Nutzereinstellungen berühren: `QSettings.setDefaultFormat(IniFormat)` +
  `QSettings.setPath(IniFormat, UserScope, <tmp>)` und `ZV_DATA_DIR=<tmp>` setzen. Nie `QSettings.clear()` (macOS).
- Tests: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` (ca. 20 min; `tests/test_stress.py` klickt alle
  Aktionen durch). Einzelne: `-k name`. Vor dem Bauen alle Tests grün.
- Bauen: `packaging/build_mac.sh` / `build_windows.bat` / `build_linux.sh`, danach `ZGmax --selbsttest`.
  GitHub: Actions → „Apps bauen“ (von Hand).

## Cloud-Umgebung (Linux)
`bash packaging/setup_cloud.sh` richtet `.venv` und die Qt-Systempakete ein (einmal je Umgebung).

## Übergabe zwischen lokal und Cloud
Am Ende **jeder** Antwort: `HANDOFF.md` aktualisieren (Stand, was offen ist, nächste Schritte, Branch), committen,
pushen. Arbeit, die nicht fertig ist, auf einem Branch `wip/...` committen, nicht auf `main`.
