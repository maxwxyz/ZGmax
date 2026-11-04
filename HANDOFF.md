# Übergabe (Stand 2026-11-04, lokal) – **Version 1.0** (Tag `v1.0`), alles auf `main`, keine offenen Branches

**Versionsnummern neu (2026-10-26):** aktuelle Version **0.8**. Die früheren 2.0/2.1/2.2 heißen jetzt 0.5/0.6/0.7
(CHANGELOG, Git-Tags `v0.6`, `v0.7`, `v0.8`; die alten Tags `v2.1`/`v2.2` sind gelöscht). `version.OLD_NUMBERS`
ordnet alte Nummern in Projekten und Einstellungen richtig ein. Wo unten „2.1“/„2.2“ steht, ist 0.6/0.7 gemeint.

Der Cloud-Branch `wip/ui-runde-8d9lrn` ist per Fast-Forward in `main` und gelöscht.

## Plan und Roadmap
- `ROADMAP.md` abgeglichen (2026-11-04): **1.0 veröffentlicht** (Tag `v1.0`). Offen für 1.1: Windows/Linux von Hand
  prüfen (Dateitypen, Hintergrund-Erkennung, Wiederherstellen, Drag & Drop), echte Testzeichnungen in `tests/real/`,
  Absturz-Fix „Schriftfeld lesen“ mit Originaldatei. Ideen: Prüfplan mit Ballonnummern + ISO-286-Passungen,
  Schriftfeld als Daten, Stückliste gegen Positionsnummern, eine Instanz, Ordnervergleich als ein PDF, Tastenkürzel,
  macOS-Signatur. Keine Firma/Zielgruppe nennen.

## Erledigt 2026-11-04 (nach 1.0)
- Windows/Linux: deaktivierte Menüeinträge waren nicht grau – `* { color }` im Stylesheet überschrieb die Palette.
  Jetzt `*:disabled` und `QMenu::item:disabled` in `ui_theme.make_qss`; Test `test_disabled_menu_items_greyed`.
  Am Mac zeichnet das System die Menüleiste (deshalb dort schon grau). 161 Tests grün, Mac-Bau OK.
- GitHub-Lauf für 1.0 (41803038113) auf allen drei Systemen grün. Neuer Lauf mit dem Fix (alle, mit Tests):
  41805528676 – Ergebnis prüfen, dann unter Windows die grauen Menüeinträge ansehen.

## Erledigt 2026-11-04 (Release 1.0)
- Agenten in Worktrees, Ergebnisse zusammengeführt: `tableextract.py` + `ui_table.py` (Tabelle CSV/Excel, mehrere
  Seiten, `area_text` mit Fenster), `digitize.py` + `ui_digitize.py` (Diagramm), Kreise/Bögen in `diffedit.py`
  (`vectorize(curves=True)`, Option `vec_curves`), Suche über alle Seiten (`ui_search.py`, `_text_key(side, page)`).
- Selbst: Pfeilspitzen (`a["heads"]`, `rep.arrow_parts`, PDF/SVG/XFDF hin und zurück), Drag & Drop
  (`ui_start.DropOverlay`, `MainWindow._drop_targets/_drop_chosen`), Vorrang im Erkennungsprozess
  (`ocrservice`: eigene Warteschlange, FOREGROUND/HORIZONTAL/VERTICAL/SKEW, unterbricht lange Durchläufe),
  schräge Texte (`rep.ocr_skew`, `skey`, Rückfall in `ocr_box`).
- openpyxl 3.1.5 in requirements.txt. `.claude/worktrees/` in `.gitignore`.
- 160 Tests grün, Mac-Bau + Selbsttest OK (neu: Schritt „Excel“). GitHub-Lauf „Apps bauen“ (alle, mit Tests) gestartet:
  Run 41803038113 – Ergebnis beim nächsten Mal prüfen.

## Erledigt 2026-11-03 (Release 0.9)
- `rep.index_check(lines=...)` nimmt Schriftfeld und Revisionstabelle aus vorhandenen Zeilen (PDF-Text oder
  `MainWindow._known_lines`, gemeinsam mit `run_text`; wartet auf den Hintergrund). Test `test_index_check_uses_read_text`.
- Release 0.9: Einträge für „Was ist neu“ zusammengefasst (12 statt 23), `release.py minor` (ohne `--git`, Commit mit
  Co-Authored-By von Hand), Tag `v0.9`. ROADMAP: 0.9 fertig, offene Punkte nach 1.0.

## Erledigt 2026-11-03 (sechster Commit)
- Erkennungsprozess lädt die Seite selbst: `ocrservice.submit(key, vertical=, src=ocrservice.source(path, page, dpi))`
  (Passwort der PDF wird mitgegeben, nur im Speicher), `page_gray(src)` = `dc.read_image` + dunkelster Kanal, im Kind
  für waagerecht + senkrecht nur einmal geladen (`_last`). Hintergrund prüft kein Graubild mehr (lief bei
  ausgeblendeten PDF-Ebenen/Vektorfilter nicht); `run_search` ruft nicht mehr `self._gray` (verdrängte das
  Vergleichsbild). Scheitert nur ein Auftrag (z. B. Datei), bleibt der Prozess; Rückfall im Programm per `page_gray`.
  Tests: `test_background_text_recognition` (mit fremder Fassung im Cache), `test_search_reads_in_process_...`.

## Erledigt 2026-11-03 (fünfter Commit)
- `PALETTE_GROUPS[0]` = Wolke + `SHAPES`; Gruppenknopf merkt das letzte Werkzeug in `palette_<erstes>` (Einstellung),
  Test `test_cloud_and_shapes_share_button`. 116 Tests grün, Mac-Bau + Selbsttest OK.

## Erledigt 2026-11-03 (vierter Commit)
- Hintergrund: zweiter Auftrag je Seite `ocrservice.vkey(key)` mit `rep.ocr_vertical` (Seite um 90° links/rechts
  gedreht, nur senkrechte Funde, Überschneidungen nach Sicherheit); `run_text` wartet auf beide und gibt `vlines` an
  `rep.text_diff` → `ocr_box(known_v=...)` erkennt nichts mehr. Doppelte Funde (waagerechte Erkennung liest senkrechte
  Texte teils mit) per `_overlap` entfernt. `rep._may_hold_text` überspringt Kacheln mit nur langen Linien. Feinere
  Kacheln/Regionen ausprobiert: kein Zeitgewinn auf dichten Zeichnungen, Ergebnis ändert sich → verworfen.
- Statusleiste `lbl_bg_text` „Text: N %“ (`_bg_text_status`, gewichtet: senkrecht = 2).
- `dp.filter_small` zählt je Gruppenzelle per `cv2.resize(INTER_AREA)` × s² (bitgleich, 0,53 → 0,11 s auf A0).
- Rechte Leiste: `_set_reviewing(on)` zeigt Prüfknöpfe nur im Rundgang; `_tab_hint(kurz, lang)` für Markierungen und
  Ebenen; langer Hinweis in „Weitere Prüfungen“ entfernt. `act_compare_with_tb` immer unsichtbar (Schild-Menü).
- `SettingsDialog` (ui_dialogs) über `act_settings` (Strg+,, PreferencesRole); Menüs Darstellung/Sprache/Größe/
  Alle Einstellungen/Text im Hintergrund aus „Ansicht“ entfernt (`theme_actions` gibt es nicht mehr).
- Wiederherstellen-Fehlalarm: `_pid_alive` unter Windows per OpenProcess/GetExitCodeProcess (os.kill(pid, 0) beendet
  dort den Prozess!), Sicherung nur mit Inhalt (`_worth_restoring`), geschlossenes Fenster sichert nicht mehr
  (`_closed`, Timer gestoppt), `aboutToQuit → clear_process_autosaves`, alte leere Sicherungen werden still gelöscht.
- 115 Tests grün, Mac-Bau + Selbsttest OK.

## Erledigt 2026-11-03 (dritter Commit)
- **Texterkennung im Hintergrund** (`programm/ocrservice.py`): `ProcessPoolExecutor(1)` mit `spawn`, Kindprozess mit
  `os.nice(10)` bzw. BELOW_NORMAL (Windows), OpenCV einfädig, ORT je Sitzung `cpu // (2 * TILE_WORKERS)` Threads
  (zusammen halbe Kerne), `rep.ocr_lines(..., workers=3, eng=raw)` liest 3 Kacheln gleichzeitig. Ein Auftrag je
  Text-Schlüssel (`_text_key`); Textsuche (`ui_search.run_search`) und durchsuchbares PDF warten über
  `ocrservice.lines` auf denselben Auftrag; `run_text` wartet per Timer. Start 1,5 s nach dem Laden
  (`_bg_text_start`, nur wenn das gecachte Graubild zur Seite passt, `_gray_key`); PDF mit Text direkt
  `dv.text_lines`. Einstellung `bg_text` (Ansicht → „Text im Hintergrund lesen“), Tests mit `ZGMAX_BG_OCR=0`
  (conftest), eigener Test `test_background_text_recognition`; Stresstest überspringt `act_bg_text`.
  `multiprocessing.freeze_support()` am Anfang von `main()`, `aboutToQuit → ocrservice.stop`. Selbsttest prüft den
  Prozess („Texterkennung im Hintergrund“) – auf dem Mac in der App OK.
  Messung (Testseite 7000×9900): im Programm 5,4 s, im Prozess 4,2 s; Hauptthread unter Volllast nur ~15 % langsamer.
- **Große Blätter:** `refine_objects` startet große Objekte zuerst und sucht die Drehungen großer Objekte
  (`_BIG_OBJ` = 250 000 px) parallel (Ergebnis gleich). A0/300 dpi: Vergleich 3,8 s → 2,8 s.
- 113 Tests grün, Mac-Bau + Selbsttest OK.

## Erledigt 2026-11-03 (zweiter Commit)
- **Geänderten Text finden** = eine Funktion (`MainWindow.run_text(then=None)`), `act_dims` entfernt, `run_dims` ruft
  `run_text`. Liest Text und Maße (`rep.dim_changes`) in einem Durchgang. Knopf `btn_text` über der Liste nach „Feine
  oder dicke Linien ausklammern“; Rest im Collapsible „Weitere Prüfungen“ (Gruppierung, Index/Revisionstabelle).
- **OCR wiederverwenden:** `rep.ocr_box(..., known=...)` nimmt bekannte waagerechte Zeilen (Textsuche-Cache
  `self.cache[self._text_key(side)[0]]`, auch vom durchsuchbaren PDF in `ui_edit.export_searchable_pdf`) und erkennt nur
  noch senkrechte Texte (Drehung 1/3); `rep.text_diff(..., only_new=True)` überspringt Bereiche mit `r["text_read"]`.
  `ocr_any_orientation(..., rots=)` gibt 7-Tupel mit Drehung zurück. Test `test_changed_text_reuses_read_text`.
- **Tempo** (A1, 200 dpi: 2,2 s → 1,45 s): `dc.darkest_channel` (cv2 statt `min(axis=2)`), `dc.render` per Code +
  `cv2.LUT` (8x), `suppress_edge_noise` mit Dilatation/Erosion statt distanceTransform (bitgleich), `build_pyramids`
  parallel. Rest: `matchTemplate` in `refine_objects` (~0,6 s), Programmstart-Import ~0,3 s (ok).
- Statusleiste nach dem Vergleich leer; Summenzeile ohne Tastenhinweis; Hinweis „Noch keine Liste“ nennt „Prüfen
  starten“; Markierungssummen „Längen: 2 (Σ …) · Wolken: 1“.
- Anleitungen DE/EN, Bilder, Menüreferenz, i18n, CHANGELOG, ROADMAP aktualisiert. 112 Tests grün, Mac-Bau + Selbsttest OK.

## Inhalt des Branches
1. **Funktionen** (Commit 523eb3e):
   - Bereiche zuordnen A ↔ B: `dp.match_region` sucht den Inhalt von A im erweiterten Rahmen von B (`_match_in`), danach
     Ausrichtung `euclidean` (Verschiebung + Drehung, kein Verzerren); nur wenn nichts passt (Score < 0,35)
     `dc.autofit` mit anderem Maßstab und `affine`. Hinweis bei schwacher Übereinstimmung.
   - Umschalt an Ecken: Seitenverhältnis bleibt (`ui_canvas.py`, Zieh-Art „handle“).
   - Modus-Schild „· Zuschnitt“ / „· Ausschnitt“, Aufheben im Schild-Menü und per Rechtsklick (`_add_crop_actions`).
   - Version im Fenstertitel; Über-Fenster mit `COPYRIGHT`/`AUTHOR`; Info.plist `NSHumanReadableCopyright`.
   - Behoben: Projekt mit nur einer Zeichnung blieb auf der Startseite.
2. **Testlaufzeit** (Commit 6749965 + Test-Korrektur im letzten Commit):
   - Ursache: Jedes Testfenster ließ ~37 versteckte Fenster liegen (nie gelöscht), `apply_theme` stylte alle neu →
     Aufbau wuchs von 0,01 s auf 8 s nach 8 Tests (später 80–120 s). Jetzt `cleanup_windows()` im Fixture `win`
     (`tests/test_gui.py`): Jobs beenden, alle Fenster schließen und mit `deleteLater` + `DeferredDelete` löschen.
   - Verzögerte Timer an das Fenster gebunden (`QTimer.singleShot(ms, self, self.x)`), sonst Fehler nach dem Löschen.
   - **Ergebnis Cloud: test_gui + test_core in 2 min 47 s** (vorher > 60 min): 100 grün, 1 veralteter Test
     (`test_multipage_tiff`, linke Leiste bleibt seit „keine Optionen-Leiste nach dem Vergleich“ zu) korrigiert
     und einzeln grün.
   - `CLAUDE.md`: fester Ablauf nach jeder Aufgabe (bauen, Tests, nur bei Grün committen → main → pushen → Branches
     löschen).

## Lokal erledigt (2026-10-26)
- Stresstest hing in `show_about` → `QMessageBox.about`/`aboutQt` im Fixture `quiet_dialogs` abgefangen. Er läuft jetzt in
  **17 s**; langsamster Befehl 1,2 s (`act_text`, `act_dims`) → nichts in `SKIP` nötig.
- **Volle Tests: 106 grün in 1 min 27 s** (vorher ~53 min). Langsamste: Stresstest 17 s, Seitenwechsel 11 s, Golden-Tests
  je 2–5 s. `english_check` = ENGLISH-OK.
- `packaging/build_mac.sh` mit Tests grün, `ZGmax --selbsttest` OK.
- Ausprobieren mit Bildschirmfotos (Bereiche zuordnen mit echten Zeichnungen, Umschalt-Ecke, Zuschnitt aufheben, Projekt
  mit einer Zeichnung, Über-Fenster/Titel) **auf Wunsch übersprungen** – noch offen für eine spätere Sichtprüfung.

## Offen
- Sichtprüfung der Punkte oben am Mac.
- Dateitypen zuordnen auf Windows und Linux ausprobieren (siehe Abschnitt 2.2 unten).
- Absturz „Schriftfeld lesen“ (OpenCV-KleidiCV-Resize, siehe unten).
- Ideen: PDF beim Hineinzoomen scharf nachrendern, Golden-Tests mit echten Zeichnungen, Revisionstabelle prüfen,
  A0-Warnung/Vorschau.

---

# Übergabe (Stand 2026-10-25 spät, lokal)

`main` = letzter Stand, **v2.1 getaggt** (Tag auf b30ef0e). Keine offenen WIP-Branches.

## Erledigt in dieser Sitzung
- Cloud-Stand (`wip/ui-runde-8d9lrn`) per Fast-Forward nach `main`, WIP-Branches lokal und auf GitHub gelöscht.
- Volle Tests lokal: 102 grün, `english_check` = ENGLISH-OK.
- `packaging/build_mac.sh` grün (102 Tests), `ZGmax --selbsttest` OK → `dist/ZGmax-2.1-macOS-arm64.zip` (nur lokal).
- Sichtprüfung am Mac (Retina, echtes Theme): Startseite mit Einführung, Leiste oben bei 1000/820 px, Prüfen
  starten / Prüfung abschließen, Ordner vergleichen, Maßtabelle (PDF), Druckdialog, Dark Mode, Anleitung
  (Seitenleiste, DE/EN-Umschalter, alle 9 Bilder je Sprache vorhanden und im App-Paket). Gefunden und behoben:
  Ordner-Symbole der Startseite blieben im Dark Mode dunkel (`StartPage.refresh_icons`, Test
  `test_start_icons_follow_theme`).
- GitHub-Workflow: Windows-Bau scheiterte (`py -3` wählte ein anderes Python ohne onnxruntime) → nutzt jetzt das
  Python im PATH. Workflow beim Start von Hand mit Wahl **plattform** (alle/Windows/macOS/Linux) und **tests**
  (an/aus). Lokal ohne Tests bauen: `--ohne-tests` (Windows `ohne-tests`) oder `ZGMAX_OHNE_TESTS=1`.
- `CHANGELOG.json` → `unreleased`: Dark-Mode-Symbole, Bauen ohne Tests / Workflow-Wahl / Windows-Bau.

## Danach (Commits bis „Haken, gefüllte Formen …“; volle Tests seitdem nicht gelaufen)
- Änderungen-Reiter: Regler „Feine oder dicke Linien ausklammern“ (`s_regw_min/max`, `rep.change_stroke_width`,
  `RegionsMixin.width_ok`, Feld `r["sw"]`); Entf/Rücktaste löscht gewählte Änderung auch im Bild/Rundgang
  (`_reg_delete`, `act_delete` mit beiden Tasten); eingefügtes Bild ohne Farb-/Werkzeugleiste; Kontextmenü und
  Speichern-Menü „In die Zwischenablage (wie angezeigt)“; „Prüfen starten“ kein Hauptknopf mehr. Tests dazu grün;
  der volle Lauf wurde auf Wunsch nach 49 von ~105 Tests abgebrochen (bis dahin kein Fehler) → **vor dem nächsten
  Bau einmal komplett laufen lassen**. Anleitungen, Bilder (`doc_screenshots.py`), Menüreferenz, CHANGELOG unreleased
  aktualisiert.

## Version 2.2 (getaggt, lokal ohne Tests gebaut)
- Neu: Hilfe → Dateitypen mit ZGmax öffnen (`fileassoc.py`, `FileTypesDialog`): Windows HKCU (Öffnen mit,
  RegisteredApplications/Capabilities, .zgmax als Standard, danach `ms-settings:defaultapps?registeredAppUser=ZGmax`),
  macOS LaunchServices (`LSSetDefaultRoleHandlerForContentType`, nur aus ZGmax.app; Lesen lokal geprüft), Linux
  `zgmax.desktop` + `xdg-mime`. **Auf Windows und Linux noch nicht ausprobiert** – beim ersten Windows-Test prüfen:
  Einträge unter `HKCU\Software\Classes`, „Öffnen mit“, Einstellungsseite.
- Volle Tests seit 2.1 nicht gelaufen (auf Wunsch). Vor dem nächsten Release komplett laufen lassen.

## Offen
- **Absturz „Schriftfeld lesen“ (beim Nutzer, nicht nachgestellt, vom Nutzer zurückgestellt):** macOS-Absturzbericht
  `~/Library/Logs/DiagnosticReports/ZGmax-2026-10-25-192233.ips`: SIGSEGV in OpenCV
  `kleidicv_resize_generic_stripe_u8` (KleidiCV-Beschleunigung auf Apple-Chip, mehrfädig) aus `cv2.resize`, während
  die Texterkennung (onnxruntime/rapidocr) lief. Im Python-Log nichts. Mit Test-PNG/-PDF lokal nicht auslösbar. Ideen:
  `cv2.resize`-Aufrufe vor der OCR mit `np.ascontiguousarray`, `cv2.setNumThreads(1)` nur während der OCR, oder
  OpenCV-Version wechseln; zuerst mit der Datei des Nutzers nachstellen.
- ~~Tests schneller machen~~ – erledigt 2026-10-26 (1 min 27 s). Lokal ~53 min, davon das meiste im Setup: spätere GUI-Tests
  brauchen 80–123 s nur fürs Fixture (`--durations=15` zeigt „setup“), Tendenz steigend im Lauf → vermutlich bleiben
  Fenster, Threads (Job/QThread), Timer oder Caches der vorigen Tests liegen. Vorgehen: Fixture `win` in
  `tests/test_gui.py` messen (Zeit bis `MainWindow()` und bis `show()`), nach jedem Test `w.close()`,
  `w.deleteLater()`, `QApplication.processEvents()` und laufende Jobs beenden; prüfen, ob `QApplication.topLevelWidgets()`
  wächst; Einstellungen/Datenordner je Test leer. Ziel: Gesamtlauf deutlich unter 10 min. Danach ggf. `pytest-xdist`
  (`-n auto`) für test_core, langsame Tests mit `@pytest.mark.slow` kennzeichnen und im Bau/CI wählbar machen.
- **GitHub-Builds noch nie komplett grün durchgelaufen**: Windows mit dem Fix kam über die Paketinstallation hinaus
  (40 min in den Tests, dann vom Nutzer abgebrochen); macOS abgebrochen; Linux lief bei Übergabe noch
  (Run 40212871727). Vorschlag: einmal `plattform=alle, tests=aus` starten (schnell, prüft Bau + Selbsttest).
- Aus der Cloud-Übergabe: Golden-Tests mit echten anonymisierten Zeichnungen; Revisionstabelle im Schriftfeld gegen
  die Änderungsliste prüfen; Speicher/Tempo bei A0 mit 400–600 dpi.
- Node-20-Warnung in Actions: `actions/checkout`/`setup-python`/`upload-artifact` bei Gelegenheit auf neue
  Hauptversionen heben.
- Vorschläge an den Nutzer (noch nicht beauftragt): PDF beim starken Hineinzoomen scharf nachrendern (nur sichtbarer
  Ausschnitt aus dem PDF, Vergleich unverändert); Golden-Tests mit echten Zeichnungen; Revisionstabelle prüfen;
  A0-Warnung/Vorschau.
