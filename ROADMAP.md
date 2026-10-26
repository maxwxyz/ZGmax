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
0.9  geplant     🟡 Stabilität: echte Zeichnungen als feste Tests, Absturz „Schriftfeld lesen“, Windows/Linux
                    vollständig geprüft (GitHub-Builds mit allen Tests sind grün ✅)
1.0  geplant     🟡 Erste stabile Version: Rückmeldungen aus der Nutzung eingearbeitet, alle Systeme geprüft
später           💡 Scharfer Zoom in PDF, Revisionstabelle prüfen, große Blätter (A0), 3D-Modelle (eigenes Werkzeug)
```

## Geplant

| Thema | Nutzen | Status |
|---|---|---|
| Feste Tests mit echten, anonymisierten Zeichnungen (Scan, CAD-PDF, DXF, A0) | Sicherheit, dass Vergleich und Maßerkennung auf echten Daten stabil bleiben | 🟡 0.9 |
| Absturz bei „Schriftfeld lesen“ beheben | Programm stürzt in OpenCV ab (siehe Bekannte Probleme) | 🟡 0.9 |
| Dateitypen zuordnen auf Windows und Linux ausprobieren | Doppelklick öffnet PDF/TIFF/… in ZGmax | 🟡 0.9 |
| GitHub-Builds für Windows, macOS, Linux einmal komplett grün (mit allen Tests) | Fertige Apps für alle Systeme aus einer Hand | ✅ 26.10.2026 |
| GitHub Actions auf neue Hauptversionen heben (Node-20-Warnung) | Workflow bleibt lauffähig | 🟡 0.9 |
| Sichtprüfung am Mac: Bereiche zuordnen, Umschalt-Ecke, Zuschnitt aufheben, Projekt mit einer Zeichnung | Bestätigung der 0.8-Funktionen im echten Einsatz | 🟡 0.9 |
| Rückmeldungen aus der Nutzung einarbeiten, erste stabile Version | Verlässlicher Stand für den Alltag | 🟡 1.0 |
| PDF beim starken Hineinzoomen scharf nachrendern | Feine Schrift und Linien bleiben scharf (Vergleich unverändert) | 💡 |
| Revisionstabelle im Schriftfeld gegen die Änderungsliste prüfen | Fehlende oder falsche Revisionseinträge auffallen lassen | 💡 |
| Große Blätter (A0 mit 400–600 dpi): Warnung oder Vorschau mit geringerer Auflösung | Weniger Speicher, schneller | 💡 |
| 3D-Modelle mit PMI (STEP AP242, JT, 3D-PDF) vergleichen – eigenes Werkzeug | Gleiche Prüfung für 3D-Daten (Vorlage: [docs/Prompt_3D_PMI_Viewer.md](docs/Prompt_3D_PMI_Viewer.md)) | 💡 |

## Bekannte Probleme

- ⚠️ **„Schriftfeld lesen“ kann auf Macs mit Apple-Chip abstürzen:** Absturz in OpenCVs beschleunigter
  Größenänderung (KleidiCV) während der Texterkennung. Mit Testdateien nicht nachstellbar. Lösungsideen in HANDOFF.md.
- 🔧 **Dateitypen zuordnen** ist auf Windows und Linux noch nicht ausprobiert (macOS: Lesen geprüft).

## Umgesetzt

### Öffnen und Anzeigen
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
- ✅ Geänderten Text und geänderte Maße finden (PDF-Text oder Texterkennung, auch senkrecht) (0.6–0.7)
- ✅ Maßänderungen als Tabelle mit Toleranzen (PDF/CSV) (0.7)

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

### Technik und Betrieb
- ✅ Portable Apps für macOS, Windows und Linux (GitHub-Workflow mit Wahl von Plattform und Tests, alle Tests grün) (0.6–0.8)
- ✅ Selbsttest der fertigen App (`--selbsttest`), Logdatei, Absturz-Meldungen statt Absturz (0.5)
- ✅ 106 automatische Tests in 1,5 min, Stresstest über alle Befehle (0.8)
- ✅ Anleitungen Deutsch/Englisch mit Bildern und Menüreferenz, Änderungshistorie „Was ist neu“ (0.6–0.7)
- ✅ Open Source unter AGPL-3.0 (0.6)
