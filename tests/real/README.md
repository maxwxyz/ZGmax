# Feste Tests mit echten Zeichnungen

Jeder Unterordner ist ein Fall mit zwei Ständen einer echten (anonymisierten!) Zeichnung. `tests/test_real.py` vergleicht
sie bei jedem Testlauf und prüft die Erwartungen. Ohne Unterordner werden die Tests übersprungen.

```
tests/real/
  gehaeuse_scan/
    a.tif            alter Stand (jedes Format, das ZGmax öffnet: PDF, TIF, PNG, DXF …)
    b.tif            neuer Stand
    fall.json        Erwartungen (alle Angaben freiwillig)
```

`fall.json` – Koordinaten in Pixeln der Zeichnung A bei der angegebenen Auflösung (z. B. in ZGmax unten in der
Statusleiste ablesen):

```json
{
  "dpi": 200, "page_a": 1, "page_b": 1,
  "aenderungen": {"min": 3, "max": 12},
  "bereiche": [[1200, 640, 300, 200]],
  "ohne_aenderung": [[100, 100, 800, 400]],
  "masse": [["120", "125"]],
  "max_sekunden": 60
}
```

- `aenderungen`: Anzahl gefundener Änderungen (ohne nur verschobene Teile) zwischen `min` und `max`.
- `bereiche`: in jedem Rechteck `[x, y, Breite, Höhe]` muss eine Änderung liegen (bekannte, echte Änderungen).
- `ohne_aenderung`: in diesen Rechtecken darf keine Änderung liegen (z. B. nur verschobene Ansicht, Scanrauschen).
- `masse`: diese Maßänderungen (alt, neu) müssen erkannt werden (PDF-Text oder Texterkennung).
- `max_sekunden`: Vergleich darf nicht länger dauern (Tempo bei großen Blättern).

Wichtig: Nur Zeichnungen ohne vertrauliche Inhalte ablegen (Schriftfeld, Firmen- und Personennamen unkenntlich, z. B.
mit ZGmax → Schwärzen und *Bearbeitete Zeichnung speichern*). Das Repository ist privat, aber Dateien bleiben in der
Git-Geschichte.
