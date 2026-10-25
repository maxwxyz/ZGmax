# Übergabe (Stand 2026-10-25, Cloud → lokal)

Branch: `wip/ui-runde-8d9lrn` (Cloud). Basis: lokaler Branch `wip/ui-runde` (0dc3923); auf `main` liegt der letzte
fertige Stand 786153d. Lokal weitermachen: `git fetch origin && git checkout wip/ui-runde-8d9lrn`.

**In dieser Cloud-Runde erledigt** (mit Tests in `tests/test_gui.py`):
- Linienfilter-UI: Collapsible „Linien filtern“ in der linken Leiste (beide Modi), `cb_lines` (all/contours/thin/custom),
  `sp_wmin`/`sp_wmax` (nur bei custom, `row_lines`), Änderung → `_lines_changed` → `debounce` → `start_compute()`.
  Modus-Schild zeigt „· Linienfilter“ (`lines_active()`). Im Projekt gespeichert (`params.lines/line_min/line_max`).
- Listenfilter „Konturen und Maße“ (`cb_filter` Schlüssel `geo`): `diffreport.mark_contours` setzt `r["contour"]`
  in `_ensure_regs`; ohne deutlich dickere Linien gilt alles als Kontur; manuelle/alte Einträge ohne Schlüssel = Kontur.
- „Änderungen neu nummerieren“ (Menü Vergleichen, `act_renumber`, `renumber_regs`).
- Abwählen einer Änderung: Esc jetzt bei jedem Werkzeug, Klick ins Leere auch bei ausgeblendeten Rahmen und im
  Werkzeug Bereich (`ui_canvas._click`, Bereich-Freigabe).
- Bestätigungsfrage „Liste leeren“ übersetzt; fehlende Übersetzungen ergänzt (`english_check` = ENGLISH-OK).
- Legende im Bildexport: nutzt `tr` beim Aufruf, alle Texte in `i18n_en.json` → bei englischer Oberfläche englisch.
- Anleitungen DE/EN: Reiterreihenfolge, Zurück zur Zeichnung, Linienfilter, Doppelklick, Umschalt/Einrasten,
  Konturen und Maße, Backspace, neu nummerieren, Abwählen, Berichte nur Liste.

**Offen / nächste Schritte:**
- Volle Testsuite lief in der Cloud (Ergebnis siehe Commit-Nachricht bzw. unten). Danach Merge nach `main`.
- Lokal: `packaging/build_mac.sh`, `ZGmax --selbsttest`, Sichtprüfung (Linienfilter-Leiste, Modus-Schild, Dark Mode).
- Antwort an den Nutzer offen: Über-Fenster auf dem Mac im Programmmenü „ZGmax → Über ZGmax“.
- Letzte Nutzerfrage kam abgeschnitten an („gibts ein modus um farben zu …“) – nachfragen.
- Vorschläge an den Nutzer (noch nicht beauftragt), Reihenfolge = Priorität:
  1. Änderungsliste ins Rückgängig aufnehmen (`ui_project._state` kennt nur anns/zones/frame/edit: Löschen, Status,
     Neu nummerieren, Liste leeren sind nicht rückgängig zu machen).
  2. Linienfilter: Hinweis, wenn `suggest_geometry_width` None liefert (Filter wirkt nicht); bei Vektor-PDF die echte
     Strichbreite aus dem PDF statt der Pixelheuristik; Konturen-Heuristik an echten Zeichnungen (Scans, 400 dpi) prüfen.
  3. Neuberechnen vereinheitlichen: Linienfilter rechnet sofort, Regler nur mit „Automatisch neu berechnen“.
  4. Expertenregler ausdünnen (Kachelgröße, Max. Kachelverschiebung, Objekt-Drehung nur CLI/Automatik).
  5. Gespeicherte Ausschnitte (Ansichten merken), Druck eines Ausschnitts im Maßstab.
  6. `ui_canvas.py` (2200 Z.) und `ui_layout.py` (1880 Z.) aufteilen (Werkzeuge als eigene Klassen).
  7. Golden-Tests mit echten, anonymisierten Zeichnungen (Scan, PDF-Vektor, DXF).
