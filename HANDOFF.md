# Übergabe (Stand 2026-10-26, Cloud → lokal) – Cloud gestoppt, lokal weitermachen

Branch **`wip/ui-runde-8d9lrn`** (auf `main` = v2.2 aufgesetzt, **noch nicht gemergt**).

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

## Offen – lokal als Nächstes
1. **Stresstest hängt** (`tests/test_stress.py`): bleibt in `show_about` stehen, weil `QMessageBox.about` im Fixture
   `quiet_dialogs` nicht abgefangen wird (modaler Dialog wartet ewig). Fix: in `quiet_dialogs` ergänzen
   `monkeypatch.setattr(QMessageBox, "about", staticmethod(lambda *a, **k: None))` (ggf. auch `aboutQt`).
   Danach mit `ZV_STRESS_TIMES=1 ... pytest -s tests/test_stress.py` die langsamsten Befehle ansehen (Ausgabe am Ende)
   und teure in `SKIP` aufnehmen (Neuberechnung, alle Seiten, Texterkennung, Vektorisieren – nicht jede Kombination
   nötig). **Ziel: alle Tests zusammen höchstens 20 min** (Nutzerwunsch).
2. Volle Tests, `english_check`, Mac-App bauen (`packaging/build_mac.sh`), Selbsttest, ausprobieren: Bereiche
   zuordnen mit echten Zeichnungen, Umschalt-Ecke an eingefügtem Bild, Zuschnitt aufheben, Projekt mit einer
   Zeichnung öffnen, Über-Fenster, Fenstertitel.
3. Wenn grün: nach `main` (Fast-Forward), pushen, `wip/ui-runde-8d9lrn` lokal und auf GitHub löschen.

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
- **Wichtigstes nächstes Thema: Tests schneller machen.** Lokal ~53 min, davon das meiste im Setup: spätere GUI-Tests
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
