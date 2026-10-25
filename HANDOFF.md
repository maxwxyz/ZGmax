# Übergabe (Stand 2026-10-25, lokal → Cloud)

Branch: `wip/ui-runde` (auf `main` liegt der letzte fertige Stand 786153d). Lokale Session musste wegen
Nutzungslimit pausieren. **Fertig, aber noch nicht voll getestet** (nur Einzeltests/Screenshots):
- Menü-Icons im Zustand „an“ blau statt weiß (`ui_icons.icon`, Theme-Schlüssel `on_bg/on_hover/on_fg`), aktive
  Werkzeugknöpfe hellblau; Listenzeilen mit Abstand (überlappende Checkboxen).
- Palette: Stempel unter Nummer gruppiert; Doppelklick auf Zeichenwerkzeug = „Werkzeug behalten“ an, auf
  Auswahl/Bereich/Zoom/Messen = aus (`_tool_double_clicked`, `DoubleClickFilter`).
- Startseite: „← Zurück zur Zeichnung“ (+ Esc), `show_work()`.
- Verschieben/Ecken ziehen: Umschalt = nur waagerecht/senkrecht; Einrasten an Kanten/Mitten anderer Markierungen
  mit gestrichelten Hilfslinien, Alt = ohne Einrasten (`Canvas._align_snap`, `_paint_guides`).
- Änderungsliste: Backspace (Mac-„delete“) löscht; Abwählen per Klick ins Leere/Esc/Liste.
- PDF-Änderungsbericht, CSV und Bildexport nur mit den Einträgen der Liste (Filter, ohne Gelöschte):
  `RegionsMixin.filter_regs`, `_filter_spec`, `_regs_listed`.
- Reiter rechts: Markierungen, Änderungen, Ebenen (`tab_anns`, `tab_regs`, `tab_layers` statt Indizes).

**Halb fertig – Linienfilter** (Anzeige und Vergleich nur bestimmte Strichbreiten):
- Fertig: `diffedit.width_band`, `diffedit.resolve_band`, `Params.lines/line_min/line_max`,
  `diffpipe.apply_line_filter` (in `run_compare` und Einzelansicht), `hide_filtered` für Farbbilder.
- Offen: UI in der linken Leiste (beide Modi, nicht nur Experte): Collapsible „Linien filtern“ mit `self.cb_lines`
  (all / contours „Nur Konturen (dicke Linien)“ / thin „Nur dünne Linien (Maße, Text, Schraffur)“ / custom) und
  `self.sp_wmin`, `self.sp_wmax` (px, 0 = ohne Grenze, nur bei custom sichtbar); Änderung → `start_compute()`
  (entprellt). Hinweis im Modus-Schild, wenn aktiv. In Projektdatei speichern (`ui_project.py`).
  `params()` in `drawing_viewer.py` liest die Widgets schon (mit hasattr-Fallback).
- Offen: Listenfilter „Konturen und Maße“ in `cb_filter` (`ui_layout.py` ~1338): Region gilt als Kontur, wenn
  `diffedit.open_lines(changed_crop, gw).sum() >= 20` (gw = `suggest_geometry_width(res.a)`), berechnet in
  `_ensure_regs` (Hintergrund); oder `r["dim"]`.

**Weitere offene Punkte aus den Nutzerwünschen:**
- „Änderungen neu nummerieren“ (Befehl im Menü Vergleichen); Nummern bleiben sonst beim Löschen erhalten.
- Prüfen: exportierte Legende im Bild englisch bei englischer Oberfläche (`diffcore` Legende nutzt `tr`, testen).
- Antwort an den Nutzer: Über-Fenster liegt auf dem Mac im Programmmenü „ZGmax → Über ZGmax“.
- Dann: Tests für alle Punkte, Übersetzungen (`english_check`), Anleitungen DE/EN (Reiterreihenfolge, Doppelklick,
  Umschalt/Einrasten, Zurück zur Zeichnung, Linienfilter, Backspace), volle Tests, Commit/Merge nach `main`, Push,
  `packaging/build_mac.sh` nur lokal.
