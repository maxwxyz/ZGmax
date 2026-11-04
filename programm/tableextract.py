"""Tabelle aus einem Bereich der Zeichnung lesen (ohne Qt): Zellraster aus Tabellenlinien oder aus der Lage der
Woerter, Text je Zelle, Ausgabe als CSV oder Excel.

Eingabe sind Textteile (x0, y0, x1, y1, text) - Woerter, PDF-Textstuecke oder Zeilen der Texterkennung - in
Pixeln des Bereichs (links oben = 0, 0) und wahlweise das Graubild des Bereichs (dunkle Linien auf hellem Papier)."""
import csv
import io
import re

import cv2
import numpy as np


def _height(words, default=15.0):
    """Typische Schrifthoehe (Median der Hoehen waagerechter Textteile)."""
    hs = [w[3] - w[1] for w in words if w[3] - w[1] > 0 and (w[2] - w[0]) >= 0.5 * (w[3] - w[1])]
    if not hs:
        hs = [min(w[2] - w[0], w[3] - w[1]) for w in words if min(w[2] - w[0], w[3] - w[1]) > 0]
    return float(np.median(hs)) if hs else default


def _cluster(values, tol):
    """Positionen (pos, gewicht) zusammenfassen, die naeher als tol beieinander liegen: gewichtete Mitten."""
    out = []
    for p, wt in sorted(values):
        if out and p - out[-1][2] <= tol:
            g = out[-1]
            g[0] += p * wt
            g[1] += wt
            g[2] = p
        else:
            out.append([p * wt, wt, p])
    return [float(g[0] / g[1]) for g in out]


def table_lines(gray, text_h=15.0):
    """Waagerechte und senkrechte Tabellenlinien im Graubild: (ys, xs) - Linienpositionen in Pixeln, sortiert.
    Linien sind lange, schmale Striche; Schrift faellt durch die Mindestlaenge (mehrfache Schrifthoehe) heraus."""
    if gray is None or gray.size == 0:
        return [], []
    H, W = gray.shape[:2]
    ink = ((gray < 160) * 255).astype(np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))   # kleine Luecken im Scan schliessen
    out = []
    for horiz in (True, False):
        size = W if horiz else H
        k = int(max(20, 2.5 * text_h, 0.08 * size))
        if k >= size:
            out.append([])
            continue
        kern = np.ones((1, k) if horiz else (k, 1), np.uint8)
        mask = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kern)
        n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        vals = []
        for i in range(1, n):
            x, y, w, h, _a = stats[i]
            length, thick = (w, h) if horiz else (h, w)
            if length < k or thick > max(8, 0.6 * text_h):        # dicke Flaechen sind keine Linien
                continue
            vals.append(((y + h / 2.0) if horiz else (x + w / 2.0), float(length)))
        out.append(_cluster(vals, max(3.0, 0.5 * text_h)))
    return out[0], out[1]


def _rows_from_words(words, text_h):
    """Zeilengrenzen aus der Lage der Woerter: Baender nach der Mitte in y, Grenze zwischen zwei Baendern."""
    bands = []
    for w in sorted(words, key=lambda t: (t[1] + t[3]) / 2):
        cy = (w[1] + w[3]) / 2
        if bands and cy - bands[-1][2] <= 0.5 * text_h:
            b = bands[-1]
            b[0], b[1] = min(b[0], w[1]), max(b[1], w[3])
            b[2] = (b[2] * b[3] + cy) / (b[3] + 1)
            b[3] += 1
        else:
            bands.append([w[1], w[3], cy, 1])
    return [(a[1] + b[0]) / 2 if b[0] > a[1] else (a[2] + b[2]) / 2 for a, b in zip(bands, bands[1:])]


def _cols_from_words(words, width, text_h, rows):
    """Spaltengrenzen aus der Lage der Woerter: senkrechte Streifen, die in (fast) allen Zeilen frei sind.
    Woerter einer Zeile mit kleinem Abstand (Wortabstand) zaehlen als ein Stueck, damit Zellen mit mehreren
    Woertern nicht zerfallen. Eine einzelne breite Kopfzeile (ueber mehrere Spalten) verhindert keine Grenze."""
    width = int(np.ceil(max([width] + [w[2] for w in words]))) + 2
    cover = np.zeros(width, np.int32)
    by_row = {}
    for w in words:
        by_row.setdefault(_index(rows, (w[1] + w[3]) / 2), []).append(w)
    for ws in by_row.values():
        ws = sorted(ws, key=lambda t: t[0])
        segs = []
        for w in ws:
            if segs and w[0] - segs[-1][1] < 0.6 * text_h:
                segs[-1][1] = max(segs[-1][1], w[2])
            else:
                segs.append([w[0], w[2]])
        for a, b in segs:
            cover[max(0, int(a)):max(0, int(np.ceil(b)))] += 1
    allowed = int(0.15 * len(by_row)) if len(by_row) >= 5 else 0
    free = cover <= allowed
    lo, hi = int(min(w[0] for w in words)), int(np.ceil(max(w[2] for w in words)))
    out, x = [], lo
    while x < hi:
        if free[x]:
            s = x
            while x < hi and free[x]:
                x += 1
            if x - s >= 0.6 * text_h:
                out.append(_best_gap(cover, s, x))
        x += 1
    return out


def _best_gap(cover, s, e):
    """Grenze in der Mitte des am wenigsten bedeckten Teils von [s, e)."""
    seg = cover[s:e]
    m = seg.min()
    idx = np.nonzero(seg == m)[0]
    return float(s + (idx[0] + idx[-1]) / 2.0)


def _index(bounds, v):
    """Nummer des Abschnitts, in dem v liegt (bounds: innere Grenzen, sortiert)."""
    return int(np.searchsorted(np.asarray(bounds, float), v, side="right")) if len(bounds) else 0


def _split(word, bounds, text_h):
    """Textteil, das ueber Spaltengrenzen reicht (z. B. eine ganze Zeile der Texterkennung), an Leerzeichen in
    Woerter aufteilen; ihre Lage wird nach der Zeichenposition geschaetzt."""
    x0, y0, x1, y1, text = word[:5]
    if not any(x0 + 0.3 * text_h < b < x1 - 0.3 * text_h for b in bounds) or " " not in text.strip():
        return [word[:5]]
    n = max(1, len(text))
    out, pos = [], 0
    for part in text.split(" "):
        if part:
            a = x0 + (x1 - x0) * pos / n
            b = x0 + (x1 - x0) * (pos + len(part)) / n
            out.append((a, y0, b, y1, part))
        pos += len(part) + 1
    return out


def _join(words, text_h):
    """Text einer Zelle in Lesereihenfolge: Zeilen von oben nach unten, darin von links nach rechts."""
    lines = []
    for w in sorted(words, key=lambda t: (t[1] + t[3]) / 2):
        cy = (w[1] + w[3]) / 2
        if lines and cy - lines[-1][0] <= 0.5 * text_h:
            lines[-1][1].append(w)
        else:
            lines.append([cy, [w]])
    return " ".join(" ".join(t[4] for t in sorted(ws, key=lambda t: t[0])) for _, ws in lines).strip()


def table_grid(words, gray=None, size=None):
    """Zellraster und Inhalt. words: [(x0, y0, x1, y1, text, ...)] in Pixeln des Bereichs; gray: Graubild des
    Bereichs oder None; size: (breite, hoehe) des Bereichs (sonst aus gray bzw. den Woertern).
    Rueckgabe dict(rows=[[str]], ys=[Zeilengrenzen], xs=[Spaltengrenzen], by_lines=(zeilen, spalten) aus Linien?).
    Waagerechte/senkrechte Linien gelten, wenn mindestens zwei da sind; sonst bestimmt die Lage der Woerter
    Zeilen bzw. Spalten. Leere Zeilen und Spalten am Rand fallen weg; verbundene Zellen stehen in der ersten
    Zelle (die anderen bleiben leer)."""
    words = [(float(w[0]), float(w[1]), float(w[2]), float(w[3]), str(w[4]).strip()) for w in words
             if str(w[4]).strip()]
    if size is None:
        size = (gray.shape[1], gray.shape[0]) if gray is not None else (
            max([w[2] for w in words] + [1]), max([w[3] for w in words] + [1]))
    W, H = size
    th = _height(words)
    ys, xs = table_lines(gray, th) if gray is not None else ([], [])
    rows_lines, cols_lines = len(ys) >= 2, len(xs) >= 2
    if not words:
        return dict(rows=[], ys=ys, xs=xs, by_lines=(rows_lines, cols_lines))
    if rows_lines:
        rb = list(ys)                    # Grenzen = alle Linien (Text ausserhalb des Rahmens: eigene Randzeile)
    else:
        rb = _rows_from_words(words, th)
    if cols_lines:
        cb = list(xs)
        words = [p for w in words for p in _split(w, cb, th)]
    else:
        cb = _cols_from_words(words, W, th, rb)
    nr, nc = len(rb) + 1, len(cb) + 1
    cells = [[[] for _ in range(nc)] for _ in range(nr)]
    for w in words:
        r = _index(rb, (w[1] + w[3]) / 2)
        c = _index(cb, (w[0] + w[2]) / 2)
        cells[r][c].append(w)
    rows = [[_join(ws, th) for ws in row] for row in cells]
    # Leere Zeilen/Spalten am Rand weg (ausserhalb des Rahmens, doppelte Linien), innen bleiben sie erhalten
    keep_r = [i for i, r in enumerate(rows) if any(r)]
    keep_c = [j for j in range(nc) if any(r[j] for r in rows)]
    if not keep_r or not keep_c:
        return dict(rows=[], ys=rb, xs=cb, by_lines=(rows_lines, cols_lines))
    rows = [r[keep_c[0]:keep_c[-1] + 1] for r in rows[keep_r[0]:keep_r[-1] + 1]]
    if rows_lines:                       # leere Zeilen zwischen eng liegenden (doppelten) Linien entfernen
        gaps = [b - a for a, b in zip([0.0] + list(rb), list(rb) + [float(H)])][keep_r[0]:keep_r[-1] + 1]
        rows = [r for r, g in zip(rows, gaps) if any(r) or g >= 0.8 * th]
    if cols_lines:
        gaps = [b - a for a, b in zip([0.0] + list(cb), list(cb) + [float(W)])][keep_c[0]:keep_c[-1] + 1]
        keep = [j for j, g in enumerate(gaps) if any(r[j] for r in rows) or g >= 0.8 * th]
        rows = [[r[j] for j in keep] for r in rows]
    return dict(rows=rows, ys=rb, xs=cb, by_lines=(rows_lines, cols_lines))


def extract_table(words, gray=None, size=None):
    """Tabelle als Liste von Zeilen (Listen von Strings), siehe table_grid."""
    return table_grid(words, gray, size)["rows"]


def to_csv(rows, sep=";", newline="\r\n"):
    """Zeilen als CSV-Text. Semikolon wie im deutschen Excel; Zahlen mit Dezimalkomma bleiben unveraendert.
    Felder mit Trennzeichen, Anfuehrungszeichen oder Zeilenumbruch werden in Anfuehrungszeichen gesetzt."""
    buf = io.StringIO()
    wr = csv.writer(buf, delimiter=sep, quotechar='"', quoting=csv.QUOTE_MINIMAL, lineterminator=newline)
    n = max((len(r) for r in rows), default=0)
    for r in rows:
        wr.writerow([("" if v is None else str(v)) for v in r] + [""] * (n - len(r)))
    return buf.getvalue()


def _norm(v):
    """Zelltext zum Vergleichen: ohne Leerraum am Rand, mehrfache Leerzeichen zu einem, Gross/Klein egal."""
    return " ".join(str(v or "").split()).casefold()


def append_rows(rows, more):
    """Zweite Tabelle (andere Seite, anderer Bereich) unten anhaengen. Eine wiederholte Kopfzeile (erste Zeile wie
    die erste Zeile der bisherigen Tabelle) faellt weg; alle Zeilen werden auf die groesste Spaltenzahl aufgefuellt."""
    rows = [list(r) for r in rows]
    more = [list(r) for r in more]
    if rows and more and any(rows[0]) and [_norm(v) for v in rows[0] if _norm(v)] == \
            [_norm(v) for v in more[0] if _norm(v)]:
        more = more[1:]
    out = rows + more
    n = max((len(r) for r in out), default=0)
    return [r + [""] * (n - len(r)) for r in out]


_NUM = re.compile(r"^[+\-−]?(\d+)([.,](\d+))?$")


def as_number(v):
    """Zelltext als Zahl (int/float), wenn er eine ist - Dezimalkomma oder -punkt; sonst None. Fuehrende Nullen
    (Sachnummern wie 007) und Tausenderpunkte bleiben Text."""
    s = str(v or "").strip().replace("−", "-")
    m = _NUM.match(s)
    if not m or (len(m.group(1)) > 1 and m.group(1).startswith("0")):
        return None
    if m.group(2) is None:
        return int(s)
    return float(s.replace(",", "."))


def to_xlsx(rows, path, sheet="Tabelle"):
    """Zeilen als Excel-Datei (.xlsx): Zahlen als Zahl, sonst Text; erste Zeile fett; Spaltenbreite nach Inhalt."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    n = max((len(r) for r in rows), default=0)
    widths = [0] * n
    bold = Font(bold=True)
    for i, r in enumerate(rows, 1):
        for j, v in enumerate(list(r) + [""] * (n - len(r)), 1):
            v = "" if v is None else str(v)
            num = as_number(v)
            c = ws.cell(row=i, column=j, value=num if num is not None else (v or None))
            if i == 1:
                c.font = bold
            longest = max((len(t) for t in v.split("\n")), default=0)
            widths[j - 1] = max(widths[j - 1], longest)
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = min(60, max(6, w + 2))
    wb.save(path)
    return path
