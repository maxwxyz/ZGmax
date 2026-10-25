# Übergabe (Stand 2026-10-25, Cloud → lokal)

Branch: `wip/ui-runde-8d9lrn` (Cloud). Basis: lokaler Branch `wip/ui-runde`; auf `main` liegt 786153d (ZGmax vor dieser
Runde). Lokal weitermachen: `git fetch origin && git checkout wip/ui-runde-8d9lrn`.

## Erledigt in der Cloud-Runde (alles mit Tests in `tests/test_gui.py` / `tests/test_core.py`)
- Linienfilter (linke Leiste, beide Modi); Grenze aus echter Strichbreite (Vektor-PDF: `dv.stroke_hist`, Raster:
  `de.stroke_width_hist` über Abstandstransformation, robust auch bei vielen dünnen Linien); Hinweis, wenn wirkungslos.
- Listenfilter „Konturen und Maße“ (`r["contour"]`, `rep.mark_contours`), Änderungen neu nummerieren.
- Rückgängig für die Änderungsliste (`_state` enthält `regs` + `regs_ver`; neuer Vergleich = neue Liste).
- „Automatisch neu berechnen“ Standard an, einheitlich; Kachel-/Drehungsregler ausgeblendet (nur CLI/Automatik).
- Seitennavigation: Seitenwahl oben (◀ n / N ▶), Bild auf/ab; Prüfstand je Seite (`page_regs`, im Projekt).
- Gemerkte Ausschnitte (Strg+D, Ansicht → Ausschnitte, `page_views`, im Projekt).
- Drucken im Maßstab: ganzes Blatt / sichtbarer Ausschnitt / Bereich, Fußzeile (`_print_options`, `_print_to`).
- Ansicht in die Zwischenablage (wie angezeigt, ohne Legende; Strg+Umschalt+E; `Canvas.view_image`).
- Umschalt beim Zeichnen: Linie/Pfeil 45°, Ellipse = Kreis, Rechteck/Wolke = Quadrat (`_shift_constrain`).
- `.zgmax` als Container (ZIP mit `projekt.json` + `dateien/`, Standard an, `act_embed`); alte JSON-Projekte lesbar;
  eingebettete Fassung, wenn Original fehlt oder anders ist (SHA-256).
- Versionen: `programm/version.py`, `programm/CHANGELOG.json` (DE/EN), `packaging/release.py`, Hilfe → Was ist neu,
  Hinweis nach Update, `app_version` im Projekt. Aktuelle Version 2.1 (noch nicht gebaut/getaggt).
- Anleitungen: alle neuen Funktionen; Abschnitt „Alle Menübefehle“ automatisch (`packaging/menu_reference.py`,
  Test `test_manual_menu_reference_up_to_date`).
- Aufgeteilt: `ui_canvas.py` → `ui_canvas_geom.py`, `ui_canvas_snap.py`, `ui_canvas_paint.py`; `ui_layout.py` →
  `ui_panels.py` (Seitenleisten).
- Fixes: „Vergleich läuft“ beim Ansehen, verlorenes Loslassen (Dialog) ließ Markierung am Cursor kleben
  (`_lost_release`), Einpassen beim Drucken in EN, Abwählen der Änderung, Texte „Markierungen entfernen“,
  „Einzelne Zeichnung öffnen“.
- `docs/Entstehungsgeschichte.md`: Vorlage für eine Präsentation (Daten vor 22.10. noch ergänzen).

## Offen / nächste Schritte
- Volle Testsuite: Ergebnis siehe letzte Antwort / Commit. Danach Merge nach `main`, Release:
  `.venv/bin/python packaging/release.py` ist für 2.1 nicht nötig (2.1 steht schon in `releases`); nur Tag `v2.1` setzen
  und bauen. Ab jetzt neue Einträge unter `unreleased`.
- Lokal: `packaging/build_mac.sh`, `ZGmax --selbsttest`, Sichtprüfung (Seitenwahl oben, Linienfilter, Druckdialog,
  Was ist neu, Dark Mode).
- Ideen (nicht beauftragt): Revisionstabelle/Schriftfeld-Index gegen Änderungsliste prüfen, geführte Erst-Tour,
  Golden-Tests mit echten anonymisierten Zeichnungen, 3D-PMI (STEP AP242/JT) als eigenes Werkzeug bewerten.
