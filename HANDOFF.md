# Übergabe (Stand 2026-10-25, Cloud → lokal)

Branch: `wip/ui-runde-8d9lrn` (enthält `wip/ui-runde` vollständig; `main` = 786153d liegt darunter, Merge ist ein
Fast-Forward). Version 2.1 (in `programm/CHANGELOG.json`, noch nicht gebaut/getaggt).

## Stand der Tests (Cloud)
- Neue/geänderte Tests einzeln grün; Teil „test_gui gerade Hälfte“ komplett grün (36/36).
- Rest (test_core + andere Hälfte test_gui, Stresstest) lief bei Übergabe noch → **lokal einmal komplett laufen lassen**.
- Die Cloud-Maschine ist langsam (Gesamtlauf > 60 min); lokal ca. 20-30 min.

## Lokal weitermachen (Reihenfolge)
```bash
git fetch --prune origin
git checkout wip/ui-runde-8d9lrn && git pull
.venv/bin/pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q        # alles grün?
.venv/bin/python tests/english_check.py                          # ENGLISH-OK
# wenn grün: nach main (Fast-Forward) und aufräumen
git checkout main && git merge --ff-only wip/ui-runde-8d9lrn && git push origin main
git push origin --delete wip/ui-runde wip/ui-runde-8d9lrn
git branch -D wip/ui-runde wip/ui-runde-8d9lrn 2>/dev/null
# bauen und taggen
packaging/build_mac.sh && dist/ZGmax.app/Contents/MacOS/ZGmax --selbsttest
git tag v2.1 && git push origin v2.1
```
Sichtprüfung am Mac (Retina, echtes Theme): Startseite mit Einführung, Leiste oben bei schmalem Fenster (keine
Knöpfe im Überlauf), Prüfen starten / Prüfung abschließen, Ordner vergleichen, Maßänderungen als Tabelle (PDF: Pfeile
als „->“), Druckdialog, Dark Mode, Anleitung (Hilfe → Anleitung: Seitenleiste, Bilder, DE/EN-Umschalter).

## In dieser Runde dazugekommen (alles mit Tests)
- Prüfen starten (Strg+Umschalt+R), Prüfung abschließen mit Protokoll und Prüfsumme (`ui_review.py`),
  Maßänderungs-Tabelle mit Toleranzen (`rep.parse_tolerance`, `rep.dim_rows`, `rep.build_dim_report`),
  Ordnervergleich mit Übersicht (`BatchDialog`, `dp.batch_pairs`), Einführung beim ersten Start, Suchfelder.
- Linienfilter (PDF-Strichbreiten, Abstandstransformation), Rückgängig für die Änderungsliste, Seitenwahl oben,
  Prüfstand je Seite, gemerkte Ausschnitte, Drucken von Ausschnitt/Bereich, Zwischenablage, Umschalt beim Zeichnen,
  `.zgmax` als Container, Versionen/Änderungshistorie (`version.py`, `release.py`, Was ist neu).
- „Automatisch neu berechnen“ ist **standardmäßig aus** (Nutzerwunsch).
- Leiste oben: `_fit_toolbar` misst den echten Platzbedarf (Texte weg → Dateinamen kürzen → Überlagern/Schieber/
  Blinken nur im Menü).
- PDF-Berichte: `rep.pdf_text` ersetzt Zeichen, die Helvetica nicht kann (→ wurde „?“).
- Anleitungen DE/EN: Bilder (`programm/doc_img/de|en`, erzeugt mit `packaging/doc_screenshots.py`), Seitenleiste,
  Sprachumschalter; „Alle Menübefehle“ automatisch (`packaging/menu_reference.py`). Beide Skripte nach UI-Änderungen
  ausführen (Tests prüfen Menüreferenz und Bilder).
- Code aufgeteilt: `ui_canvas_geom/_snap/_paint.py`, `ui_panels.py`, `ui_review.py`.
- Dokumente: `docs/Entstehungsgeschichte.md`, `docs/Prompt_3D_PMI_Viewer.md`.

## Offen / Ideen
- Golden-Tests mit echten anonymisierten Zeichnungen (Scan, CAD-PDF, DXF, A0) – wichtigster Robustheitspunkt.
- Revisionstabelle im Schriftfeld gegen die Änderungsliste prüfen.
- Speicher/Tempo bei A0 mit 400-600 dpi (Warnung oder Vorschau mit geringerer Auflösung).
- Testlaufzeit verkürzen (Fixture-Setup dauert in der Cloud bis 100 s; lokal messen mit `--durations=15`).
