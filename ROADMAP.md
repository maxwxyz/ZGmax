# ZGmax – Roadmap und Funktionsstand

Stand: Version **0.8** (26.10.2026). Was sich je Version geändert hat, steht in [CHANGELOG.md](CHANGELOG.md);
technische Übergabe zwischen Sitzungen in [HANDOFF.md](HANDOFF.md). Diese Datei wird bei jeder neuen Funktion und jedem
Release mit gepflegt.

**Legende:** ✅ umgesetzt · 🔧 umgesetzt, aber noch nicht auf allen Systemen ausprobiert · 🟡 geplant · 💡 Idee (noch
nicht beschlossen) · ⚠️ bekanntes Problem

## Roadmap

```
0.5  22.10.2026  ✅ Erste Programmversion: zwei Zeichnungen ausrichten und vergleichen, Ansichten, Bericht
0.6  25.10.2026  ✅ Markieren, Messen, Ebenen, Kommentare (XFDF/PDF), Texterkennung, englische Oberfläche
0.7  25.10.2026  ✅ Prüfen starten, Prüfprotokoll, Maßtabelle, Ordnervergleich, Linienfilter, Scans aufbereiten,
                    Dateitypen zuordnen
0.8  26.10.2026  ✅ Bereiche zuordnen ohne Verzerren, Modus-Schild mit Zuschnitt, Über-Fenster, Werkzeuggröße
                    bleibt, Tests in 1,5 min
0.9  in Arbeit    🔧 Scharfer PDF-Zoom ✅, Revisionstabelle prüfen ✅, große Blätter ✅, Absturz „Schriftfeld lesen“
                    abgesichert ✅, Gerüst für echte Zeichnungen ✅ (echte Fälle fehlen noch), GitHub-Builds grün ✅,
                    Text finden vereint + schneller ✅, Vergleich schneller ✅, Texterkennung im
                    Hintergrund ✅;
                    offen: Windows/Linux von Hand prüfen
1.0  geplant     🟡 Erste stabile Version: Rückmeldungen aus der Nutzung eingearbeitet, alle Systeme geprüft
später           💡 3D-Modelle (eigenes Werkzeug)
```

## Geplant

| Thema | Nutzen | Status |
|---|---|---|
| Feste Tests mit echten, anonymisierten Zeichnungen (Scan, CAD-PDF, DXF, A0) | Sicherheit, dass Vergleich und Maßerkennung auf echten Daten stabil bleiben | 🔧 Gerüst fertig (`tests/real/`), echte Fälle fehlen |
| Absturz bei „Schriftfeld lesen“ beheben | Programm stürzt in OpenCV ab (siehe Bekannte Probleme) | 🔧 abgesichert, Bestätigung mit der Originaldatei offen |
| Dateitypen zuordnen auf Windows und Linux ausprobieren | Doppelklick öffnet PDF/TIFF/… in ZGmax | 🟡 0.9 |
| GitHub-Builds für Windows, macOS, Linux einmal komplett grün (mit allen Tests) | Fertige Apps für alle Systeme aus einer Hand | ✅ 26.10.2026 |
| GitHub Actions auf neue Hauptversionen heben (Node-20-Warnung) | Workflow bleibt lauffähig | ✅ v7 (Node 24) |
| Sichtprüfung am Mac: Bereiche zuordnen, Umschalt-Ecke, Zuschnitt aufheben, Projekt mit einer Zeichnung | Bestätigung der 0.8-Funktionen im echten Einsatz | 🟡 0.9 |
| Rückmeldungen aus der Nutzung einarbeiten, erste stabile Version | Verlässlicher Stand für den Alltag | 🟡 1.0 |
| PDF beim starken Hineinzoomen scharf nachrendern | Feine Schrift und Linien bleiben scharf (Vergleich unverändert) | ✅ |
| Revisionstabelle im Schriftfeld gegen die Änderungsliste prüfen | Fehlende oder falsche Revisionseinträge auffallen lassen | ✅ |
| Große Blätter (A0 mit 400–600 dpi): Warnung oder Vorschau mit geringerer Auflösung | Weniger Speicher, schneller | ✅ |
| Laufendes Programm öffnet weitere Dateien (eine Instanz, Windows) | Schneller, keine doppelten Prozesse | 💡 |
| Texterkennung einmal je Zeichnung im Hintergrund (nach dem Laden), für Suche, Text finden und Schriftfeld | Kein Warten beim ersten Gebrauch | ✅ (eigener Prozess, 0.9) |
| Vergleich über mehrere Rechenkerne pro Kachel (matchTemplate ist der größte Anteil) | Große Blätter schneller | ✅ 0.9 |
| Ordnervergleich als ein gemeinsamer PDF-Bericht | Ein Dokument statt eines je Paar | 💡 |
| Tastenkürzel selbst belegen | Gewohnte Kürzel aus anderen Programmen | 💡 |
| macOS-App mit Entwicklerzertifikat signieren | Keine Warnung beim ersten Start | 💡 (braucht Apple-Entwicklerkonto) |
| 3D-Modelle mit PMI (STEP AP242, JT, 3D-PDF) vergleichen – eigenes Werkzeug | Gleiche Prüfung für 3D-Daten (Vorlage: [docs/Prompt_3D_PMI_Viewer.md](docs/Prompt_3D_PMI_Viewer.md)) | 💡 |

## Bekannte Probleme

- 🔧 **„Schriftfeld lesen“ konnte auf Macs mit Apple-Chip abstürzen** (OpenCVs mehrfädige Größenänderung während der
  Texterkennung). Seit 0.9 läuft die Texterkennung einfädig und nacheinander; ob das den Absturz ganz verhindert, zeigt
  erst die Originaldatei.
- 🔧 **Dateitypen zuordnen** ist auf Windows und Linux noch nicht ausprobiert (macOS: Lesen geprüft).

## Umgesetzt

### Öffnen und Anzeigen
- ✅ PDF/SVG beim starken Hineinzoomen scharf (sichtbarer Ausschnitt aus der Datei) (0.9)
- ✅ Hinweis bei sehr großen Blättern mit Knopf für geringere Auflösung (0.9)
- ✅ Formate: PDF, TIFF (mehrseitig), PNG, JPG, BMP, WebP, JP2, GIF, SVG, XPS, DXF; Transparenz, 16 Bit, CMYK (0.6)
- ✅ Passwortgeschützte PDF mit Passwortabfrage; verständliche Meldungen bei leeren/beschädigten Dateien (0.6)
- ✅ Startseite mit Einführung, zuletzt verwendet, „Zurück zur Zeichnung“ (0.5–0.7)
- ✅ Modus-Schild „Ansehen“ / „Vergleich“ mit Aktionen, jedes Dokument im eigenen Fenster (0.6–0.8)
- ✅ Dunkles Farbschema, Oberflächengröße, Deutsch/Englisch (0.6)
- 🔧 Dateitypen mit ZGmax öffnen (Windows, macOS, Linux; auch portable App) (0.7)

### Vergleichen
- ✅ Ausrichten (global, Kacheln, Drehung, Maßstab), manuelles Ausrichten mit 3 Punkten (0.5–0.6)
- ✅ Ansichten Alt, Neu, Vergleich, Überlagern, Nebeneinander, Schieber, Blinken (0.5)
- ✅ Fehlalarme unterdrücken: Schraffur, verschobene Blöcke/Objekte, Kantensäume, Zeichenprüfung, Papierausgleich (0.5–0.6)
- ✅ Exakter Vektorvergleich für CAD-PDF, PDF-Ebenen (0.6)
- ✅ Ausschnitt, Zonen, Bereiche zuordnen ohne Verzerren (0.6–0.8)
- ✅ Linienfilter (nur Konturen / nur dünne Linien), Änderungen nach Strichbreite ausklammern (0.7)
- ✅ Mehrseitige Dateien, alle Seiten vergleichen, Ordnervergleich mit Übersicht, Revisionen A → B → C (0.6–0.7)

### Prüfen und Freigeben
- ✅ Nummerierte Änderungsliste, geprüft/abgelehnt/Kommentar, Suchfeld, Filter „Zeigen“ (0.5–0.7)
- ✅ „Prüfen starten“ als geführter Rundgang, Löschen mit Entf/Rücktaste, Rückgängig (0.7)
- ✅ Prüfung abschließen mit Prüfprotokoll und Prüfsumme (0.7)
- ✅ Geänderten Text finden – Text und Maße in einem Durchgang (PDF-Text oder Texterkennung, auch senkrecht) (0.6–0.7);
  eine Funktion über der Liste, nutzt schon gelesenen Text (Textsuche, durchsuchbares PDF) (0.9)
- ✅ Maßänderungen als Tabelle mit Toleranzen (PDF/CSV) (0.7)
- ✅ Index und Revisionstabelle prüfen: neuer Eintrag, fehlender Eintrag, Index passt nicht (0.9)

### Markieren und Messen
- ✅ Text, Wolke, Rahmen, Ellipse, Linie, Linienzug, Polygon, Pfeil, Stift, Marker, Nummer, Haken, Stempel (0.6–0.7)
- ✅ Gefüllte Formen, Werkzeugkasten mit Vorlagen, eigene Stempel, zuletzt gewählte Größe bleibt (0.6–0.8)
- ✅ Schwärzen und Verpixeln (in jeder Ausgabe eingebrannt) (0.6)
- ✅ Messen wie im CAD: Länge, Winkel, Radius, Fläche, Maßkette, Fangpunkte, Koordinaten-Eingabe, Kalibrieren (0.6)
- ✅ Einrasten an anderen Elementen, Umschalt = waagerecht/senkrecht bzw. Seitenverhältnis (0.7–0.8)
- ✅ Kommentare mit Antworten und Status je Person; XFDF und PDF-Anmerkungen hin und zurück (0.6)
- ✅ Ebenen (Zeichnung, Änderungen, Markierungen, Maße, Bilder, Zonen, Schwärzung) (0.6)

### Zeichnung bearbeiten (beim Ansehen)
- ✅ Bereich verschieben/ausschneiden/kopieren (auch nur Linien oder nur Geometrie), Zuschnitt-Rahmen (0.6)
- ✅ Drehen, Helligkeit/Kontrast, Bildgröße, Gerade ausrichten, Entzerren (4 Ecken), Hintergrund ausgleichen (0.6–0.7)

### Ausgeben
- ✅ Bild, PDF mit Anmerkungen, SVG mit Ebenen, durchsuchbares PDF, Vektorisieren (SVG/PDF/DXF) (0.5–0.6)
- ✅ PDF-Änderungsbericht und Änderungsliste (CSV) – nur was in der Liste steht (0.5–0.7)
- ✅ Drucken im Maßstab, Kopieren wie angezeigt (0.6–0.7)
- ✅ Projekte (.zgmax, auch mit eingebetteten Zeichnungen), gemerkte Ausschnitte, automatische Sicherung (0.6–0.7)

### Bedienung
- ✅ Wolke und Formen in einem Knopf der Werkzeugleiste, merkt das zuletzt gewählte Werkzeug (0.9)
- ✅ Einstellungsfenster (Darstellung, Sprache, Größe, Name, Text im Hintergrund, alle Einstellungen) (0.9)
- ✅ Rechte Leiste: Prüfknöpfe nur während der Prüfung, kurze Hinweise mit Tooltip; „Vergleichen mit …“ nur im Schild (0.9)
- ✅ Keine falsche Wiederherstellen-Frage mehr beim Start (Windows-Prozessprüfung, nur bei echtem Inhalt) (0.9)

### Technik und Betrieb
- ✅ Portable Apps für macOS, Windows und Linux (GitHub-Workflow mit Wahl von Plattform und Tests, alle Tests grün) (0.6–0.8)
- ✅ Selbsttest der fertigen App (`--selbsttest`), Logdatei, Absturz-Meldungen statt Absturz (0.5)
- ✅ Texterkennung im Hintergrund (eigener Prozess, niedrige Priorität, halbe Kerne), ganze Seiten 30–40 % schneller,
  Absturz der Erkennung beendet das Programm nicht mehr (0.9); liest auch senkrechte Texte, Fortschritt „Text: %“ in der Statusleiste,
  Kacheln ohne Text werden übersprungen (0.9)
- ✅ „Kleine Unterschiede ausfiltern“ 5x schneller (bitgleich), A0/300 dpi 2,8 s → 2,2 s (0.9)
- ✅ Große Blätter: verschobene Objekte besser auf alle Kerne verteilt (A0/300 dpi 3,8 s → 2,8 s) (0.9)
- ✅ Vergleich etwa ein Drittel schneller (Kanal-Minimum, Vergleichsbild und Kantensaum mit OpenCV, Bildstufen
  parallel) (0.9)
- ✅ Automatische Tests in 1,5 min, Stresstest über alle Befehle; Gerüst für Tests mit echten Zeichnungen (0.8–0.9)
- ✅ Anleitungen Deutsch/Englisch mit Bildern und Menüreferenz, Änderungshistorie „Was ist neu“ (0.6–0.7)
- ✅ Open Source unter AGPL-3.0 (0.6)
