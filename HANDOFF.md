# Übergabe (Stand 2026-10-26, lokal) – alles auf `main`, keine offenen Branches

**Versionsnummern neu (2026-10-26):** aktuelle Version **0.8**. Die früheren 2.0/2.1/2.2 heißen jetzt 0.5/0.6/0.7
(CHANGELOG, Git-Tags `v0.6`, `v0.7`, `v0.8`; die alten Tags `v2.1`/`v2.2` sind gelöscht). `version.OLD_NUMBERS`
ordnet alte Nummern in Projekten und Einstellungen richtig ein. Wo unten „2.1“/„2.2“ steht, ist 0.6/0.7 gemeint.

Der Cloud-Branch `wip/ui-runde-8d9lrn` ist per Fast-Forward in `main` und gelöscht.

## Plan und Roadmap
- `ROADMAP.md` geprüft (2026-10-26): Stand 0.8 vollständig unter „Umgesetzt“; als Nächstes **0.9 Stabilität** (echte
  Zeichnungen als feste Tests, Absturz „Schriftfeld lesen“, Dateitypen auf Windows/Linux prüfen, GitHub-Builds grün,
  Actions-Versionen, Sichtprüfung am Mac), dann **1.0 erste stabile Version**. Ideen (noch nicht beschlossen): scharfer
  PDF-Zoom, Revisionstabelle prüfen, große Blätter, 3D-Modelle. Im Repo keine Firma, Zielgruppe oder Pilotgruppe nennen.
- Keine offenen Aktionen – Pause bis zur nächsten Eingabe.

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
