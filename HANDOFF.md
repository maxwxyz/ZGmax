# Übergabe (Stand 2026-10-25 abends, lokal)

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

## Offen
- **GitHub-Builds noch nie komplett grün durchgelaufen**: Windows mit dem Fix kam über die Paketinstallation hinaus
  (40 min in den Tests, dann vom Nutzer abgebrochen); macOS abgebrochen; Linux lief bei Übergabe noch
  (Run 40212871727). Vorschlag: einmal `plattform=alle, tests=aus` starten (schnell, prüft Bau + Selbsttest).
- **Testlaufzeit**: Setup späterer GUI-Tests 80–123 s pro Test (wächst im Lauf → vermutlich bleiben Fenster/Objekte
  liegen; Fixture `win` in `tests/test_gui.py` prüfen: `deleteLater` + `processEvents`, Caches leeren). Gesamt
  ~53 min lokal; auf GitHub-macOS entsprechend teuer (privates Repo, macOS-Minuten ×10).
- Aus der Cloud-Übergabe: Golden-Tests mit echten anonymisierten Zeichnungen; Revisionstabelle im Schriftfeld gegen
  die Änderungsliste prüfen; Speicher/Tempo bei A0 mit 400–600 dpi.
- Node-20-Warnung in Actions: `actions/checkout`/`setup-python`/`upload-artifact` bei Gelegenheit auf neue
  Hauptversionen heben.
