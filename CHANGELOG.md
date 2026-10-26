# ZGmax – Änderungshistorie

## Version 0.8 vom 26.10.2026

- Bereiche zuordnen (A ↔ B): Der Rahmen in B muss nur ungefähr passen; das Programm sucht die Stelle selbst – zuerst bei gleichem Maßstab (Verschiebung, kleine Drehung), nur bei Bedarf mit anderem Maßstab. Keine verzerrten Ergebnisse mehr.
- Ecke ziehen mit Umschalt: Seitenverhältnis bleibt (z. B. eingefügte Bilder).
- Zuschnitt und Vergleichs-Ausschnitt stehen im Modus-Schild und lassen sich dort oder per Rechtsklick aufheben.
- Versionsnummer im Fenstertitel; Über-Fenster mit Copyright.
- Behoben: Projekte mit nur einer Zeichnung blieben nach dem Öffnen auf der Startseite.
- macOS: „Über ZGmax“ erscheint wieder (eigenes Fenster mit Programmsymbol).
- Markierungen: die zuletzt eingestellte Größe gilt für die nächsten Pfeile, Nummern usw. (auch nach dem Neustart).

## Version 0.7 vom 25.10.2026

- Dunkles Farbschema: Ordner-Symbole der Startseite („Datei wählen“) sind nach dem Umschalten wieder gut sichtbar.
- Bauen wahlweise ohne Testlauf (--ohne-tests); GitHub-Workflow mit Wahl von Plattform und Tests; Windows-Bau auf GitHub repariert.
- Änderungen: Regler „Feine oder dicke Linien ausklammern“ blendet Änderungen nach der Strichbreite der Linie aus; die Zeichnung bleibt vollständig.
- Entf/Rücktaste löscht die gewählte Änderung auch im Bild und im Prüfrundgang (weiter mit der nächsten, Strg+Z holt sie zurück).
- Eingefügtes Bild: keine Farb- und Werkzeugleiste mehr; „Werkzeug behalten“ nur beim Zeichnen.
- Kontextmenü im Bild: „In die Zwischenablage (wie angezeigt)“; im Speichern-Menü direkt nach „Als Bild speichern“.
- „Prüfen starten“ ist ein normaler Knopf (nicht mehr hervorgehoben).
- Nach dem Vergleich kein blauer Hinweisbalken mehr und die Optionen-Leiste öffnet nicht von selbst.
- Prüfrundgang: Nächste/Vorige folgen genau der Liste (auch mit Strichbreite, Suche, „Konturen und Maße“).
- Geänderte Maße: senkrecht geschriebene Maße in Leserichtung – Maßzahl vor Toleranz (PDF-Text und Texterkennung).
- Bereiche zuordnen verzerrt nicht mehr: verglichen wird ein gleich großer Ausschnitt um die Mitte, Ausrichtung wie gewohnt.
- Neues Werkzeug „Haken“ (unter Nummer): grüne Haken zum Abhaken geprüfter Maße.
- Rahmen, Ellipse und Polygon wahlweise gefüllt (auch in PDF, SVG und XFDF).
- Schwärzen ohne wirkungslose Größe; „Mit Hintergrundfarbe“, beim Bereich „Nur Linien (ohne Hintergrund)“; Marker zeigt seine gelbe Farbe.
- Speichern-Menü je Modus: beim Ansehen ohne Bericht/Liste/Maßtabelle, im Vergleich ohne „Bearbeitete Zeichnung speichern“.
- Bild aus der Zwischenablage öffnen/einfügen ohne Fehler, wenn kein Bild darin ist.
- Hilfe → Dateitypen mit ZGmax öffnen: PDF, Bilder, DXF und Projekte per Doppelklick in ZGmax öffnen (Windows, macOS, Linux; auch portable App).

## Version 0.6 vom 25.10.2026

- Vergleich: Papierausgleich für Scans, Zeichenprüfung für ähnliche Ziffern (z. B. 41.8 → 43.2), Vorschlag zum exakten Vektorvergleich bei PDF, abgelehnte Funde als Zonen übernehmen.
- Manuelles Ausrichten mit zwei oder drei Punkten.
- Texterkennung Deutsch/Englisch (Umlaute, ß, °, ±); Textsuche im PDF-Text oder per Texterkennung, Treffer auch in der neuen Zeichnung.
- Kommentare aus XFDF und PDF-Anmerkungen einlesen und als XFDF speichern; Antworten und Prüfstatus je Person (wie Acrobat und Bluebeam).
- Englische Oberfläche (Systemsprache) und englische Anleitungen; Größe der Oberfläche einstellbar.
- Messen: Maße wie Bemaßung, Maßkette, Summen und Zählungen, Messungen als CSV, Maßstab und Kalibrierung je Seite, CAD-Fang an Mittelpunkten, Ecken, Schnitt- und Endpunkten, Nullpunkt und Koordinateneingabe.
- Zeichenwerkzeuge: Stift, Ellipse, Linie, Linienzug, Polygon, Text direkt im Bild; Werkzeugkasten mit Vorlagen und eigenen Stempeln.
- Ebenen, Zeichnung bearbeiten (Bereich verschieben), durchsuchbares PDF, Vektorisieren (SVG, PDF, DXF), Schwärzen.
- Zuschnitt als verstellbarer Rahmen für Ausgaben; Markierungen einzeln ein- und ausblenden.
- Mehrseitige Dateien: Markierungen und Prüfstand je Seite, Seitenliste mit Anzahl, Seitenwahl oben und Blättern mit Bild auf/ab, PDF mit Anmerkungen und Änderungsbericht über alle Seiten.
- Scans aufbereiten: Hintergrund bereinigen, gerade ausrichten, Foto eines Blatts entzerren.
- Linienfilter: nur Konturen, nur dünne Linien oder eigene Strichbreite – beim Ansehen und im Vergleich; bei Vektor-PDF mit den echten Strichbreiten.
- Änderungsliste: Filter „Konturen und Maße“, Rückgängig auch für Löschen, Status und Kommentare, Neu nummerieren, Rücktaste löscht; Bericht, CSV und Bild enthalten nur die Einträge der Liste.
- Bedienung: Doppelklick auf ein Werkzeug = Werkzeug behalten; Umschalt = waagerecht/senkrecht verschieben, Linie in 45°-Schritten, Kreis, Quadrat; Einrasten an anderen Markierungen; Ansicht wie angezeigt in die Zwischenablage; von der Startseite zurück zur Zeichnung.
- Projekt als Container: Die Zeichnungen werden in die .zgmax-Datei eingebettet und lassen sich mit ihr verschicken; Programmversion im Projekt.
- Ausschnitte merken (Ansicht → Ausschnitte, Strg+D) und mit einem Klick wieder anspringen; Drucken im Maßstab auch für den sichtbaren Ausschnitt oder einen gewählten Bereich, mit Fußzeile.
- Anleitungen: neuer Abschnitt „Alle Menübefehle“, automatisch aus den Menüs erzeugt; Menüpunkt „Zeichnung ansehen“ heißt jetzt „Einzelne Zeichnung öffnen“.
- „Prüfen starten“: ein Knopf sucht die Änderungen, zeigt die erste offene und blendet die Tasten ein; Einführung in drei Schritten beim ersten Start.
- Prüfung abschließen: Prüfer, Ergebnis (freigegeben, mit Auflagen, nicht freigegeben) und Bemerkung als Prüfprotokoll mit Prüfsumme im Projekt und als PDF.
- Maßänderungen als Tabelle (PDF/CSV) mit Maß alt → neu, Toleranz alt/neu (ISO-Passung, ±, Abmaße), Position und Prüfstatus.
- Ordner vergleichen: eigener Stand gegen Lieferanten-Datensatz, alle Seiten, Unterordner, Revisionskennung im Namen ignorierbar; Übersicht (geändert, gleich, nur alt/neu) als Tabelle, PDF und CSV.
- Suchfelder über der Änderungs- und der Markierungsliste.
- Anleitungen mit Bildern, Inhaltsverzeichnis als Seitenleiste und Umschalter Deutsch/Englisch, der im selben Abschnitt bleibt.
- Versionen mit Änderungshistorie (Hilfe → Was ist neu).
- Lizenz AGPL-3.0.
- Behoben: Menüsymbole im hellen Modus, überlappende Haken in Listen, gewählte Änderung ließ sich nicht abwählen, „Vergleich läuft“ beim bloßen Ansehen, angefangene Markierung klebte nach einem abgebrochenen Dialog am Mauszeiger, „Auf Papier einpassen“ beim Drucken in englischer Oberfläche; Knopf „Löschen“ der Bereichsauswahl heißt jetzt „Markierungen entfernen“; Pfeile (→) erschienen in PDF-Berichten als „?“; die Leiste oben lief bei langen Dateinamen über.

## Version 0.5 vom 22.10.2026

- Ausgangsstand: Viewer und Vergleich mit Ausrichtung, Kachel-Feinausrichtung, verschobenen Blöcken und Objekten, Änderungsliste mit Prüfstatus, Markierungen, Messen, Projekt, PDF-Bericht, Stapel und Revisionen, Kommandozeile.
