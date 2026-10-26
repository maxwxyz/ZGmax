# Prompt: 3D-PMI-Viewer und -Vergleich (neues Projekt)

Diesen Text als erste Nachricht in einem neuen, leeren Projekt verwenden. Er beschreibt Ziel, Umfang, Technik und
Arbeitsweise; Erfahrungen aus ZGmax (2D-Zeichnungsvergleich) sind eingeflossen.

---

## Auftrag

Baue ein Desktop-Programm, mit dem man **3D-Modelle mit PMI** (Product and Manufacturing
Information: Maße, Toleranzen, Form- und Lagetoleranzen, Bezüge, Oberflächenangaben, Hinweise) ansehen, vermessen,
prüfen und **zwei Stände eines Modells vergleichen** können – das 3D-Gegenstück zu einem Zeichnungsvergleich, für
Modelle ohne klassische 2D-Zeichnung (Model Based Definition).

Ich bin Fachanwender (Konstruktion, Automobil), kein Softwareentwickler. Du schreibst den Code, ich gebe Richtung,
Prioritäten und Abnahme. Antworte auf Deutsch, sage klar, was geht und was nicht, und erfinde keine Fähigkeiten von
Bibliotheken: Wenn du dir nicht sicher bist, ob eine Bibliothek etwas kann, prüfe es mit einem kleinen Versuch.

## Formate (in dieser Reihenfolge)

1. **STEP AP242** mit semantischer PMI (Pflicht, Kern des Programms). Auch AP214/AP203 ohne PMI.
2. **QIF** (ISO 23952, XML) – semantische PMI und Messdaten; prüfen, ob als zweiter Weg sinnvoll.
3. **JT** (ISO 14306) – Geometrie und PMI. Erst Machbarkeit prüfen: Freie Leser decken nach meinem Stand oft nur die
   Tessellierung ab; PMI aus JT braucht meist ein lizenziertes Toolkit (z. B. JT Open Toolkit, CAD Exchanger SDK).
   Ergebnis und Kosten vorlegen, bevor du baust.
4. **3D-PDF** (PRC/U3D) – Machbarkeit prüfen; mindestens die eingebettete Geometrie anzeigen.
5. Weitere: IGES, STL, glTF/GLB, 3MF, OBJ (nur Geometrie).

Beispieldaten zum Testen: die öffentlichen **NIST MBE PMI Test- und Validierungsmodelle** (STEP AP242 mit PMI), dazu
eigene anonymisierte Modelle, die ich liefere.

## Funktionen

**Ansehen**
- Modell laden (Drag-and-drop, zuletzt verwendet), Baugruppenstruktur als Baum (ein-/ausblenden, isolieren, transparent).
- Drehen, Verschieben, Zoomen mit Maus und Trackpad wie in gängigen CAD-Viewern; Standardansichten (vorne, oben, iso …),
  Ganzes zeigen, Drehpunkt per Klick.
- **Gespeicherte Ansichten (Saved Views/Kameras) aus dem Modell** mit den jeweils sichtbaren PMI anzeigen und wechseln.
- Schnitt mit Ebene(n), Schnittkontur hervorheben.
- Darstellung: schattiert, mit Kanten, Drahtmodell; heller und dunkler Modus.

**PMI**
- Liste aller PMI (Typ, Wert, Toleranz, Bezüge, Ansicht) mit Filter und Suche.
- **PMI anklicken → zugehörige Flächen/Kanten werden hervorgehoben**; Fläche anklicken → zugehörige PMI werden gezeigt.
- Bezugssystem (A|B|C) und Toleranzrahmen lesbar darstellen, auch als Text in der Liste.

**Messen**
- Abstand (Punkt, Kante, Fläche, kürzester Abstand), Winkel, Radius/Durchmesser, Wandstärke an einer Stelle,
  Koordinaten; Fang an Kanten, Mittelpunkten, Flächen; Ergebnisse als Liste und CSV.

**Vergleichen (zwei Stände)**
- Beide Modelle in dasselbe Koordinatensystem; falls verschoben: Ausrichten (automatisch per Bestpassung, von Hand über
  drei Punktpaare).
- **Geometrie:** Flächen zuordnen (über persistente IDs, wenn vorhanden, sonst geometrisch) und als *neu*, *entfernt*,
  *geändert*, *gleich* einfärben; zusätzlich Abweichungsfarbkarte (Abstand Oberfläche zu Oberfläche) mit Toleranzgrenze.
- **PMI:** semantischer Vergleich – welche Maße/Toleranzen neu, entfallen oder geändert sind (Wert, Toleranz, Bezüge,
  zugeordnete Flächen). Das ist der wichtigste Mehrwert.
- **Änderungsliste** mit Nummern, Sprung zur Stelle (Kamera fährt hin), Prüfstatus (offen, geprüft, abgelehnt),
  Kommentar; „Prüfen starten“ führt Schritt für Schritt durch.
- Prüfung abschließen: Prüfer, Ergebnis (freigegeben / mit Auflagen / nicht freigegeben), Bemerkung, Protokoll mit
  Prüfsumme (SHA-256) – ausdrücklich keine qualifizierte elektronische Signatur.
- Ausgaben: PDF-Bericht (Übersicht, Änderungsliste, Bilder je Änderung), Tabelle der PMI-Änderungen (PDF/CSV) für
  Lieferanten und Fertigung, Bildschirmfoto der Ansicht in die Zwischenablage.
- Projektdatei als Container (ZIP mit Projektdaten und eingebetteten Modellen), damit man es verschicken kann.
- Ordnervergleich: viele Modelle zweier Stände auf einmal mit Übersicht (geändert, gleich, nur alt/neu).

## Technik (Vorschlag, bitte begründet bestätigen oder verbessern)

- Python 3 und PySide6 (Qt) für die Oberfläche; Geometriekern **Open CASCADE (OCCT)** über `pythonocc-core` oder `OCP`
  (STEP/XCAF mit Farben, Namen, Ebenen, GD&T über die XCAF-Werkzeuge, gespeicherte Ansichten). Prüfe, welche PMI-Teile
  (semantische vs. nur grafische PMI) die gewählte OCCT-Version tatsächlich liefert, und zeige mir das an einem
  NIST-Modell, bevor die Oberfläche entsteht.
- Darstellung: OCCT-Viewer in einem Qt-Widget oder VTK – entscheide nach Tempo, Auswahl (Picking) und Paketgröße.
- Rechenintensives (Laden, Tessellieren, Vergleich) in Hintergrund-Threads mit Fortschritt und Abbrechen; große
  Baugruppen müssen flüssig bleiben (Tessellierung zwischenspeichern, Detailstufen).
- Lizenzen der Bibliotheken prüfen und im Über-Fenster nennen (OCCT: LGPL mit Ausnahme).

## Bedienung (wichtig für Kollegen, die selten damit arbeiten)

- Wenig auf einmal zeigen, alles beschriftet, Einführung in drei Schritten beim ersten Start.
- Navigation geht immer, egal welches Werkzeug gewählt ist.
- Oberfläche Deutsch, Übersetzung Englisch (alle Texte über `tr()` und eine Übersetzungsdatei), Systemsprache als
  Standard; heller und dunkler Modus mit lesbaren Eingabefeldern.
- Anleitung als HTML (Deutsch und Englisch) im Programm (F1); ein Abschnitt „Alle Menübefehle“ wird automatisch aus den
  Menüs erzeugt und per Test geprüft.

## Qualität und Arbeitsweise

- Tests von Anfang an: Kernfunktionen (Laden, PMI lesen, Vergleich) mit Beispielmodellen, Oberfläche ohne Bildschirm
  (offscreen), ein Stresstest, der alle Aktionen anklickt. Vor jedem Commit laufen die Tests.
- Versionen mit Änderungshistorie (Deutsch/Englisch) in einer Datei; Version auch im Projekt speichern; „Was ist neu“.
- Portable Apps für Windows, macOS und Linux (PyInstaller), Selbsttest-Schalter `--selbsttest`.
- Eine Datei `HANDOFF.md` hält nach jeder Antwort fest, was fertig ist, was offen ist und wie es weitergeht; Arbeit, die
  nicht fertig ist, auf einem Branch `wip/...`.
- Code-Kommentare deutsch ohne Umlaute, kurze Funktionen, keine toten Knöpfe (was nicht geht, ist ausgegraut).

## Vorgehen

1. **Machbarkeit (zuerst, ohne Oberfläche):** STEP AP242 eines NIST-Modells laden, PMI auflisten (Typ, Wert, Toleranz,
   Bezüge, zugeordnete Flächen), gespeicherte Ansichten auslesen. JT- und 3D-PDF-Weg prüfen und mit Aufwand/Kosten
   bewerten. Ergebnis als kurze Übersicht vorlegen.
2. Viewer mit Baum, Navigation, gespeicherten Ansichten, PMI-Liste und Hervorhebung.
3. Messen.
4. Vergleich Geometrie und PMI mit Änderungsliste und Prüfrundgang.
5. Berichte, Projekt-Container, Ordnervergleich.
6. Weitere Formate.

Nach jedem Schritt: lauffähiger Stand, Tests grün, kurze Zusammenfassung mit Bildschirmfotos.
