# ZGmax

Zeichnungen ansehen, vergleichen und prüfen. Technische Zeichnungen ansehen, vergleichen, vermessen, markieren und prüfen. Anleitung für Anwender:
`programm/Anleitung_Viewer.html` (im Programm: Hilfe → Anleitung, F1), Kommandozeile: `programm/Anleitung_Kommandozeile.html`.

## Aufbau

| Datei | Inhalt |
|---|---|
| `programm/diffcore.py` | Rechenkern: Laden (Bild, PDF, DXF), Ausrichten, Kachelvergleich, Objektsuche, Kantensäume, Ausgabe |
| `programm/diffpipe.py` | Ablauf (laden → ausrichten → vergleichen), Parameter, automatische Einstellung |
| `programm/diffreport.py` | Änderungsliste, Prüfstatus, Anmerkungen, PDF-Bericht, PDF mit Acrobat-Anmerkungen, Schriftfeld, OCR |
| `programm/diffvector.py` | PDF-Vektordaten: Ebenen/Farben, exakter Vergleich, PDF-Text |
| `programm/drawing_diff.py` | Kommandozeile |
| `programm/drawing_viewer.py` | Programmfenster (Einstieg), Hauptfenster-Abläufe |
| `programm/ui_*.py` | Oberfläche: Aufbau (`ui_layout`), Zeichenfläche (`ui_canvas`), Funktionen (`ui_features`), Liste (`ui_regions`), Markierungen (`ui_annotations`), Projekt (`ui_project`), Export (`ui_export`), Farbschema (`ui_theme`), Symbole (`ui_icons`), Startseite (`ui_start`) |

## Entwickeln

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -r requirements-ocr.txt
.venv/bin/python -m pytest
.venv/bin/python programm/drawing_viewer.py
```

Die Tests prüfen bekannte Änderungen an künstlichen Zeichnungen, die Oberfläche (ohne Bildschirm) und – wenn der Ordner
`../Beispiele` vorhanden ist – Fingerabdrücke der Ergebnisse. Ändert sich das Vergleichsverfahren gewollt:
`UPDATE_GOLDEN=1 .venv/bin/python -m pytest`.

## Portable Apps bauen

* macOS (auf einem Mac): `packaging/build_mac.sh` → `dist/ZGmax.app` und ZIP. Läuft auf Macs mit derselben
  Prozessorart wie der Bau-Mac (Apple-Chip oder Intel).
* Windows (auf einem Windows-PC): `packaging\build_windows.bat` → `dist\ZGmax\ZGmax.exe` und ZIP.
* Automatisch für alle drei: Projekt auf GitHub legen; `.github/workflows/build.yml` baut bei jedem Tag `v*` oder von Hand.

Die Paketversionen sind in `requirements*.txt` festgelegt; nur gemeinsam und nach einem Testlauf ändern.

Projektdateien: `.zgmax`. Die Einstellungen liegen weiterhin unter dem alten internen Schlüssel `drawing_diff/viewer`,
damit vorhandene Einstellungen und Projekte nach der Umbenennung weiter gelten.
