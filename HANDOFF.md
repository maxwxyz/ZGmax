# Übergabe (Stand 2026-10-25, Cloud → lokal)

**Alles ist in `main`** (Version 2.1, noch nicht gebaut/getaggt). Die Branches `wip/ui-runde` und
`wip/ui-runde-8d9lrn` sind gemergt und gelöscht.

## Lokal weitermachen
```bash
git fetch --prune origin
git checkout main && git pull
git branch -D wip/ui-runde 2>/dev/null       # alter lokaler Arbeitsbranch, steckt vollständig in main
.venv/bin/pip install -r requirements-dev.txt  # pyflakes ist neu dabei (optional)
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q    # ca. 20-30 min
packaging/build_mac.sh && dist/ZGmax.app/Contents/MacOS/ZGmax --selbsttest
git tag v2.1 && git push origin v2.1          # wenn der Build passt
```
Sichtprüfung am Mac: Startseite mit Einführung, Seitenwahl oben bei mehrseitigen PDF, Prüfen starten / Prüfung
abschließen, Ordner vergleichen, Maßänderungen als Tabelle, Druckdialog, Dark Mode, Ladezeit großer PDF.

## Was in der Cloud-Runde dazukam (alles mit Tests)
- Linienfilter (Konturen / dünne Linien / eigene Breite), Strichbreite aus Vektor-PDF bzw. Abstandstransformation;
  Listenfilter „Konturen und Maße“; Rückgängig für die Änderungsliste; neu nummerieren.
- Seitenwahl oben, Bild auf/ab, Prüfstand je Seite; gemerkte Ausschnitte (Strg+D); Drucken im Maßstab für Ausschnitt
  oder Bereich; Ansicht in die Zwischenablage; Umschalt beim Zeichnen (45°, Kreis, Quadrat).
- `.zgmax` als Container mit eingebetteten Zeichnungen; Versionen und Änderungshistorie (`programm/CHANGELOG.json`,
  `programm/version.py`, `packaging/release.py`, Hilfe → Was ist neu).
- **Prüfen starten** (Strg+Umschalt+R), **Prüfung abschließen** mit Protokoll und Prüfsumme (`ui_review.py`,
  `rep.make_protocol`), **Maßänderungen als Tabelle** mit Toleranzen (`rep.parse_tolerance`, `rep.dim_rows`),
  **Ordner vergleichen** mit Übersicht (`BatchDialog`, `dp.batch_pairs`), Einführung beim ersten Start, Suchfelder.
- Anleitungen DE/EN vollständig; „Alle Menübefehle“ automatisch (`packaging/menu_reference.py`, Test prüft).
- Code: `ui_canvas_geom.py`, `ui_canvas_snap.py`, `ui_canvas_paint.py`, `ui_panels.py`, `ui_review.py` neu.
- Dokumente: `docs/Entstehungsgeschichte.md` (Präsentationsvorlage, Daten vor 22.10. ergänzen),
  `docs/Prompt_3D_PMI_Viewer.md` (Startprompt für das 3D-PMI-Projekt).

## Regeln (siehe CLAUDE.md)
- Neue sichtbare Änderungen in `programm/CHANGELOG.json` unter `unreleased` (de + en); Release mit
  `packaging/release.py minor --git`.
- Neue Menübefehle: `.venv/bin/python packaging/menu_reference.py` ausführen (sonst schlägt der Test fehl).

## Ideen (nicht beauftragt)
- Golden-Tests mit echten anonymisierten Zeichnungen (Scan, CAD-PDF, DXF, A0) – wichtigster Robustheitspunkt.
- Revisionstabelle im Schriftfeld gegen die Änderungsliste prüfen.
- Speicher/Tempo bei A0 mit 400-600 dpi (Warnung oder Vorschau mit geringerer Auflösung).
