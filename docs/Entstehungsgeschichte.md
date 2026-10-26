# ZGmax – Entstehungsgeschichte

Vorlage für eine Präsentation. Jeder Abschnitt mit `##` entspricht etwa einer Folie oder einem Folienblock; die
Stichpunkte sind die Kernaussagen, „Sprechertext“ liefert den Hintergrund. Daten vor dem 22.10.2026 sind nicht in der
Versionsverwaltung belegt und sollten vor der Präsentation ergänzt werden (markiert mit *[ergänzen]*).

---

## 1. Ausgangslage: ein ganz normaler Engpass

- Zwei Revisionen einer Zeichnung müssen kurzfristig verglichen werden.
- Das vorhandene Werkzeug (ZG-View) liefert kein brauchbares Ergebnis: Zeichnungen und Ansichten sind leicht
  gegeneinander versetzt, der Vergleich zeigt fast alles als geändert.
- Händisches Vergleichen („Flip-Flop“ oder Ausdruck auf Leuchttisch) kostet Zeit und übersieht kleine Maßänderungen.

**Sprechertext:** Der Bedarf entstand nicht aus einem Projektauftrag, sondern aus einer konkreten Lücke im Alltag.
Pixelgenaue Vergleiche scheitern, sobald ein Blatt neu geplottet, anders skaliert oder eine Ansicht verschoben wurde –
also im Normalfall.

---

## 2. Der erste Schritt: ein Python-Skript per Kommandozeile

- Mit KI-Unterstützung („gevibed“) entsteht ein Python-Skript: zwei Zeichnungen rein, Ergebnisbild raus.
- Kern: **automatisches Ausrichten** (Verschiebung, Drehung, Maßstab), danach Vergleich mit Toleranz.
- Erweitert um **Ausschnitt vergleichen** (nur einen Teil des Blatts) und als Neuheit:
  **verschobene, aber unveränderte Elemente** werden erkannt und grün statt rot/blau dargestellt.
- Zeitpunkt: *[ergänzen]*

**Sprechertext:** Genau das konnte das bisherige Werkzeug nicht: Eine Bemaßung, die nur ein Stück gewandert ist, ist
keine Änderung. Das Skript trennt „wirklich geändert“ von „nur verschoben“ – damit schrumpft die Liste der Funde auf
das, was ein Prüfer sehen muss.

---

## 3. Vom Skript zum Programm: das GUI-MVP

- Aus dem Skript wird eine Oberfläche (Python, Qt), die auch Kollegen ohne Kommandozeile bedienen können.
- Funktionsumfang des MVP (Stand „ZGmax 2.0“, 22.10.2026):
  - Zeichnungen öffnen per Drag-and-drop (PDF, TIFF, PNG, JPG, DXF u. a.), mehrseitige Dateien
  - Ansichten Alt, Neu, Vergleich (rot = entfernt, blau = neu, grau = gleich, grün = verschoben), Nebeneinander,
    Überlagern, Schieber, Blinken
  - Feinausrichtung in Kacheln (Scans sind oft ungleichmäßig verzogen), Schraffur- und Rauschunterdrückung
  - Nummerierte Änderungsliste mit Prüfstatus (geprüft, abgelehnt, Kommentar)
  - Markierungen, Messen, Projektdatei, PDF-Bericht, Stapel- und Revisionsvergleich

**Sprechertext:** Ab hier ist es kein Skript mehr, sondern ein Werkzeug für den Arbeitsplatz. Ziel war von Anfang an:
wenig auf einmal zeigen, alles beschriftet, keine Hürde für Kollegen, die mit CAD-Viewern aufgewachsen sind.

---

## 4. Verfeinerung Schritt für Schritt (ab 22.10.2026)

Die wichtigsten Ausbaustufen in der Reihenfolge, in der sie entstanden sind (aus der Versionsgeschichte):

| Wann | Was dazukam | Nutzen |
|---|---|---|
| 22.10. | Papierausgleich, Messstand-Bestimmung, Zeichenprüfung für ähnliche Ziffern, Vorschlag Vektorvergleich, abgelehnte Funde als Zonen | Weniger Fehlalarme bei Scans; 41.8 → 43.2 wird sicher erkannt |
| 22.10. | Manuelles Ausrichten mit drei Punkten | Auch stark verschobene oder umgezeichnete Blätter vergleichbar |
| 23.10. | Texterkennung Deutsch/Englisch, Textsuche in PDF-Text oder Scan | Maße und Hinweise in jeder Zeichnung finden |
| 23.10. | Kommentare aus XFDF/PDF einlesen und zurückgeben | Austausch mit Acrobat/Bluebeam beim Lieferanten |
| 23.10. | Englische Oberfläche und Anleitungen | Einsatz mit internationalen Partnern |
| 24.10. | Zeichenwerkzeuge (Stift, Ellipse, Linie, Polygon, Text im Bild), Bereichsauswahl, Einfügen | Vollwertiges Markup |
| 24.10. | Ebenen, Zeichnung bearbeiten, durchsuchbares PDF, Vektorisieren (SVG/PDF/DXF), Schwärzen | Weitergabe ohne vertrauliche Inhalte, Rückführung ins CAD |
| 25.10. | Antworten und Status je Person in Kommentaren, Maßkette, Summen, Messungen als CSV, Maßstab je Seite | Prüfprotokoll mit mehreren Beteiligten |
| 25.10. | CAD-Fang an Mittelpunkten, Ecken, Schnittpunkten; Koordinateneingabe | Messen wie im CAD |
| 25.10. | Werkzeugkasten mit Vorlagen, eigene Stempel, Markierungen und Prüfstand je Seite | Wiederkehrende Prüfungen schneller |
| 25.10. | Scans aufbereiten (Hintergrund, gerade ausrichten, Foto entzerren) | Auch Papierzeichnungen und Handyfotos nutzbar |
| 25.10. | Linienfilter (nur Konturen / nur dünne Linien), Filter „Konturen und Maße“ | Nur relevante Geometrie- und Maßänderungen |
| 25.10. | Projekt als Container mit eingebetteten Zeichnungen, Versionen mit Änderungshistorie | Ein File zum Verschicken; nachvollziehbare Releases |

**Sprechertext:** Jede Stufe kam aus einer konkreten Rückmeldung im Arbeitsalltag. Die KI hat den Code geschrieben;
Richtung, Prioritäten und Abnahme lagen beim Fachanwender. Mehr als 60 automatische Oberflächentests und ein
Stresstest, der jede Funktion durchklickt, sichern jeden Schritt ab.

---

## 5. Was das Vergleichen robust macht

- **Ausrichten auf drei Ebenen:** ganzes Blatt, Kacheln, einzelne Objekte (Maße, Texte, Ansichten).
- **Verschoben ist nicht geändert:** grün markiert, nicht in der Liste der Änderungen.
- **Fehlalarme unterdrücken:** Kantensäume, Schraffur, Papierflecken, gleich gerasterte Schrift.
- **Exakter Vektorvergleich** für CAD-PDFs: Linien und Texte direkt, ohne Raster.
- **Automatisch einstellen:** misst Toleranz, Strichstärke und Verzug am konkreten Zeichnungspaar.

---

## 6. Heute: Was ZGmax leistet

**Vergleichen und Messen**
- Zwei Revisionen in Sekunden vergleichen – auch bei versetzten Ansichten, anderem Maßstab, Scan gegen PDF.
- Nur das sehen, was zählt: Filter auf Konturen und Maße, verschobene Teile grün, Änderungen nummeriert.
- Messen wie im CAD (Fang, Kalibrieren, Maßstab je Seite) und markieren wie in Acrobat.

**Prüfen und Dokumentieren**
- Prüfrundgang mit Status je Änderung (offen, geprüft, abgelehnt, Kommentar) als Prüfprotokoll:
  PDF-Bericht, CSV, PDF mit Anmerkungen.
- Mehrseitige Zeichnungssätze: Prüfstand je Seite, „Alle Seiten vergleichen“ zeigt, wo sich etwas geändert hat.
- Revisionen und Stapel: viele Zeichnungen auf einmal gegen den Vorstand prüfen.

**Lieferanten**
- Kommentare kommen als XFDF/PDF-Anmerkungen zurück und gehen genauso wieder hinaus (Acrobat, Bluebeam).
- Ein `.zgmax`-Projekt enthält Zeichnungen, Markierungen und Prüfstand – ein File zum Verschicken.
- Schwärzen für die Weitergabe ohne vertrauliche Inhalte.

**Schnittstellen**
- Konstruktion: DXF lesen, Vektorisieren nach DXF/SVG/PDF für die Rückführung ins CAD.
- Simulation: Konturen-Filter und „Nur Geometrie kopieren“ liefern bereinigte Geometrie ohne Bemaßung.
- Produktion: Drucken im Maßstab (auch nur ein Ausschnitt), durchsuchbare PDFs, Texterkennung auf Scans aus der
  Werkstatt.

---

## 7. Wie es entstanden ist – und was man daraus lernen kann

- Vom akuten Problem zum Werkzeug in kurzer Zeit: Fachwissen + KI als Entwickler.
- Kleine Schritte, jeder sofort im Alltag erprobt; automatische Tests verhindern Rückschritte.
- Portabel für Windows, macOS und Linux; Oberfläche Deutsch/Englisch; Open Source (AGPL-3.0).
- Nächste Ideen: 3D-Modelle mit PMI (STEP AP242, JT) ansehen und vergleichen – als eigenes Werkzeug zu bewerten.

---

## Anhang: Zahlen und Fakten (für eine Fakten-Folie)

- Programmiersprache Python, Oberfläche Qt (PySide6), Bildverarbeitung OpenCV, PDF PyMuPDF.
- Versionen und Änderungen: siehe `CHANGELOG.md` (deutsch) und `CHANGELOG_EN.md`.
- Anleitungen: `programm/Anleitung_Viewer.html`, `programm/Manual_Viewer.html`.
- Zu ergänzen: Zeitaufwand, Zahl der Nutzer, eingesparte Zeit je Vergleich, Beispiele aus dem Alltag *[ergänzen]*.
