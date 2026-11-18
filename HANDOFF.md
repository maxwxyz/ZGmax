# Übergabe (Stand 2026-11-18, lokal) – **Version 1.1** (Tag `v1.1`), alles auf `main`, keine offenen Branches

**Versionsnummern neu (2026-10-26):** aktuelle Version **0.8**. Die früheren 2.0/2.1/2.2 heißen jetzt 0.5/0.6/0.7
(CHANGELOG, Git-Tags `v0.6`, `v0.7`, `v0.8`; die alten Tags `v2.1`/`v2.2` sind gelöscht). `version.OLD_NUMBERS`
ordnet alte Nummern in Projekten und Einstellungen richtig ein. Wo unten „2.1“/„2.2“ steht, ist 0.6/0.7 gemeint.

Der Cloud-Branch `wip/ui-runde-8d9lrn` ist per Fast-Forward in `main` und gelöscht.

## Plan und Roadmap
- `ROADMAP.md` abgeglichen (2026-11-18): **1.1 veröffentlicht** (Tag `v1.1`). Offen für 1.2: Windows/Linux von Hand
  prüfen (Installer mit echtem Nutzerkonto, Übergabe an laufendes Programm, Drag & Drop, graue Menüs), echte
  Testzeichnungen in `tests/real/`, Absturz-Fix „Schriftfeld lesen“ mit Originaldatei. Ideen: Prüfplan mit
  Ballonnummern + ISO-286-Passungen, Schriftfeld als Daten, Stückliste gegen Positionsnummern, Ordnervergleich als
  ein PDF, Tastenkürzel, Signatur (macOS und Windows-Installer). Keine Firma/Zielgruppe nennen.

## Stand 2026-11-18 abends
- Alle sieben Review-Befunde erledigt und zusammengeführt (drei Agenten-Branches, gelöscht): Speichern absichern
  (`programm/safewrite.py`), Leisten-Aufbau und große Zeichen-/Berichtsfunktionen in Teilfunktionen, 38
  Befehls-Erklärungen, 99 unbenutzte Übersetzungen entfernt. 205 Tests grün, Mac-Bau + Selbsttest OK.
- GitHub-Bau „Apps bauen“ (alle, mit Tests) für diesen Stand gestartet – Ergebnis prüfen. Version bleibt 1.1
  (Einträge unter „unreleased“; nächstes Release wäre 1.2).
- Offen für den Nutzer: Windows-Test von Hand (Installer-Dialog, Übergabe an laufendes Programm, Drag & Drop, graue
  Menüs, gesperrte Zieldatei beim Speichern), echte Testzeichnungen, Commit-Zeile (Fable 5.2 vs. CLAUDE.md Opus 5.5).

## Erledigt 2026-11-18 (nach 1.1, unter „unreleased“)
- Texterkennung überall im eigenen Prozess: `rep._in_service` um `ocr_image`, `ocr_lines`, `ocr_any_orientation`,
  `ocr_vertical`, `ocr_skew` → `ocrservice.call(name, args, kwargs)` (Vorrang FOREGROUND, hält Hintergrund 2 s
  zurück, damit Reihen einzelner Aufrufe ihn nicht dauernd abbrechen). Absturz → `ocrservice.Crashed` → leeres
  Ergebnis, `rep.OCR_CRASHED` zählt, `_run_job` meldet es per Hinweis. `ZGMAX_OCR_IM_PROGRAMM=1` = alter Weg.
  Kosten: kleine Einzelerkennungen ~50 % langsamer (10 Stück 3,5 s statt 2,3 s).
- Review der ganzen App, 7 Befunde: (1) Pfad aus fremder Projektdatei (`read_project`, jetzt nur Hex), (2) Aufräumen
  `prune_project_files` (30 Tage), (4) Fensterlage `quickstart.saved_window/save_window` (nur wenn `main()` die
  App-Eigenschaft `zgmax_remember_window` setzt). (3) Speichern absichern, (6) Tooltips, (7) große Funktionen:
  drei Agenten in Worktrees – Ergebnisse zusammenführen. (5) unbenutzte Übersetzungen danach entfernen.
- Textschicht (Nutzerwunsch, ohne Daueranzeige in der Statusleiste): `programm/textstore.py` merkt erkannten Text
  unter `<Daten>/textcache/<sha1 des Inhalts>-p<Seite>-d<dpi|0>.json.gz` (Teile h/v/s, `VER`), Obergrenze 400
  Dateien/40 MB/120 Tage (`prune` einmal je Programmlauf). `SearchMixin`: `_store_pull/_store_push/_store_ref`,
  `text_layer(side, page)` als gemeinsame Quelle (Suche, `_known_lines`, Schriftfeld, Tabelle, Text kopieren),
  `_text_valid` (bearbeitete Zeichnung: Suche liest das gezeigte Bild, Schlüssel `txt-edit`). Projekt: `text_cache`
  in `_project_data`, Import in `project_open` (Name gegen festes Muster geprüft). Tests räumen die Ablage je Test
  (conftest `_fresh_text_store`).

## Erledigt 2026-11-18 (Release 1.1)
- Prüfbau 44304411880 auf allen drei Systemen grün, Installer-Probe bestanden (bauen, `/CURRENTUSER` installieren,
  darüber aktualisieren, Selbsttest, Registry, Deinstallation). Startzeiten der fertigen Apps (GitHub-Rechner):
  Windows Vorschau 0,2 s / Bild 0,75 s, Linux 0,19 / 0,79 s, macOS 0,35 / 1,5 s.
- Review-Fixes: `Job.release()` nach `finished`, `_trim_cache()` beim Dateiwechsel, Vorschau nur bis 150 MP.
- Golden-Tests: `golden.json` enthält je Fall `sha` und Pixelzahlen `n`; am Mac exakt, sonst Toleranz
  (max(100, 2 %)) – `GOLDEN_TOLERANT=1` erzwingt das auch am Mac.
- Commit-Zeile: seit dem Modellwechsel „Co-Authored-By: Claude Fable 5.2“; CLAUDE.md nennt noch Opus 5.5 (Nutzer gefragt).

## Erledigt 2026-11-18 (zwei CI-Fehler aus Lauf 44300320970)
- Linux: Golden-Tests und `test_map_points…` rot (Ausrichtung 24 px daneben) – ECC hing am Startwert der
  Phasenkorrelation, der auf dem Runner anders ausfiel (am Mac nicht nachstellbar, mit gefälschtem Startwert schon).
  `dc.align_global` jetzt grob-zu-fein mit zwei Startwerten (`_ecc`); Fingerabdrücke unverändert, Test
  `test_alignment_survives_bad_phase_start`.
- Windows: Zugriffsverletzung im Stresstest (`Job.__init__`) – `ocrservice._held()` fragte aus dem Thread des
  Prozess-Pools `QThread.isRunning()` ab, während der Hauptthread Jobs löschen kann. Jetzt Marken statt Qt-Objekten
  (`pause(token)/resume(token)`, `PAUSE_MAX` 300 s, `job.destroyed` gibt frei).

## Erledigt 2026-11-18 (Windows-Installer)
- `packaging/zgmax.iss` (Inno Setup 6, UTF-8 mit BOM, CRLF): `PrivilegesRequired=lowest` +
  `PrivilegesRequiredOverridesAllowed=dialog` (Dialog „für alle / nur für mich“, ohne Admin automatisch je Nutzer),
  Aufgaben je Dateityp, Registry über `HKA` nach dem Schema von `fileassoc.py`, `[InstallDelete]` räumt `_internal`
  vor einem Update. Workflow-Schritt „Windows-Installer bauen und probeweise installieren“: ISCC (ggf. per choco),
  stille Installation `/CURRENTUSER`, Update darüber, Selbsttest der installierten App, Registry-Prüfung,
  Deinstallation. Artefakt `dist/*-Setup.exe` neben dem ZIP. Lokal am Mac nicht prüfbar – erster Lauf zeigt, ob es baut.
  Portable App bleibt (Ein-Datei-EXE verworfen: entpackt bei jedem Start, langsamer). Ohne Signatur SmartScreen-Warnung.

## Erledigt 2026-11-18 (schneller Start)
- GitHub-Lauf 44298581129: Linux rot – SIGFPE in OpenCV (Stresstest): `_SafeOcr` stellte `cv2.setNumThreads(0)` um,
  während der Hauptthread `HoughCircles` rechnete (Texterkennung des Diagramm-Fensters im Hintergrund-Thread).
  Jetzt nur noch am Mac umstellen (`_SafeOcr.SINGLE`); im Erkennungsprozess bleibt es einmalig beim Start.
  Erste Windows-Startzeiten (Runner, warm): Vorschau 0,25 s, Bild 0,9 s.
- `programm/quickstart.py` (braucht nur Qt): `make_app`, `hand_over`/`serve` (QLocalServer `zgmax-<Nutzer>`: ein
  weiterer Aufruf gibt seine Dateien ab und endet; `--neu` oder `ZGMAX_EIGENE_INSTANZ=1` erzwingt einen eigenen Lauf,
  `restart_app` nutzt `--neu`), `preview` (Sofortvorschau über QImageReader, verkleinert gelesen), `mark`/`report`.
  `zgmax_start.py` ruft das vor dem Import von `drawing_viewer`; `main(app, preview)` zeigt das Hauptfenster erst,
  wenn die Zeichnung da ist, und schließt dann die Vorschau.
- Messung: `ZGmax --startzeit <datei>` (eigene Einstellungen im Temp-Ordner, `ZGMAX_T0` = Startzeitpunkt vom Aufrufer,
  `ZGMAX_STARTZEIT_DATEI` für Windows ohne Konsole). Mac-App warm: Vorschau 0,32 s, Bild 0,87 s, Startseite 0,59 s.
  GitHub-Workflow misst nach dem Selbsttest dreimal und gibt die Zeiten aus (Windows-Werte dort ablesen).
- Kalt dominiert das Laden von OpenCV (~1,2 s am Mac) und Qt; das ist nicht vermeidbar, liegt jetzt aber hinter der
  Vorschau. Fensteraufbau 0,24 s (Werkzeugleiste/Symbole ~0,15 s) – wenig zu holen.
- Achtung: Ein Messlauf vor der Umstellung lief mit den echten Einstellungen und hat vermutlich die Scratch-Datei
  `…/scratchpad/zd/a.png` in „Zuletzt verwendet“ eingetragen (Zurücknehmen wurde blockiert) – Nutzer informiert.

## Erledigt 2026-11-04 (nach 1.0)
- Zweite Runde nach 1.0 (Agenten + selbst): Tempo – Hintergrund-Erkennung startet erst im Ruhezustand
  (`_bg_idle_start`), pausiert während Laden/Vergleich (`_run_job(..., pause_ocr=True)` → `ocrservice.pause(job)`,
  Prozess per SIGSTOP/NtSuspendProcess eingefroren, gilt nur solange der Job läuft), schlanker Einstieg
  `programm/zgmax_start.py` (Spec, Launcher, Dateitypen) – der Erkennungsprozess lädt keine Oberfläche mehr.
  Diagramm (Dialog sofort offen, Zoom um Maus, scharfe PDF-Ansicht, Gitter ausblenden, umgekehrte Achsen, y2-Fehler,
  gestrichelt, Excel-Formeln), Tabellen mit verbundenen Zellen (`spans`), Anfasser: Größen-Cursor, Seitenmitten,
  Drehen (`rot`, überall in der Ausgabe). 190 Tests grün, Mac-Bau + Selbsttest OK.
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
