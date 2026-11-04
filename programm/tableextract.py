"""Tabelle aus einem Bereich der Zeichnung lesen (ohne Qt): Zellraster aus Tabellenlinien oder aus der Lage der
Woerter, verbundene Zellen (fehlende Linienstuecke), Text je Zelle, Ausgabe als CSV oder Excel.

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


def _ink(gray):
    """Dunkle Pixel (Tinte) als 0/255-Maske, kleine Luecken im Scan geschlossen."""
    ink = ((gray < 160) * 255).astype(np.uint8)
    return cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))


def _strokes(ink, horiz, k, text_h):
    """Schmale Striche einer Richtung, mindestens k lang: (maske, [(lage, laenge, anfang, ende)])."""
    kern = np.ones((1, k) if horiz else (k, 1), np.uint8)
    mask = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kern)
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, _a = stats[i]
        length, thick = (w, h) if horiz else (h, w)
        if length < k or thick > max(8, 0.6 * text_h):            # dicke Flaechen sind keine Linien
            continue
        out.append(((y + h / 2.0) if horiz else (x + w / 2.0), float(length),
                    float(x if horiz else y), float((x + w) if horiz else (y + h))))
    return mask, out


def _in_text(horiz, pos, a, b, words):
    """Liegt der Strich (Lage pos, von a bis b) groesstenteils in Textteilen? Dann ist er Schrift, keine Linie."""
    if not words:
        return False
    cov = np.zeros(max(1, int(np.ceil(b - a))), bool)
    for w in words:
        lo, hi, p0, p1 = (w[0], w[2], w[1], w[3]) if horiz else (w[1], w[3], w[0], w[2])
        if p0 <= pos <= p1 and hi > a and lo < b:
            cov[max(0, int(lo - a)):max(0, int(np.ceil(hi - a)))] = True
    return cov.mean() >= 0.8


def _lines(gray, text_h=15.0, words=None):
    """Wie table_lines, zusaetzlich die Tintenmaske: (ys, xs, ink)."""
    if gray is None or gray.size == 0:
        return [], [], None
    H, W = gray.shape[:2]
    ink = _ink(gray)
    tol = max(3.0, 0.5 * text_h)
    masks, found, ks = [], [], []
    for horiz in (True, False):
        size = W if horiz else H
        k = int(max(20, 2.5 * text_h, 0.08 * size))
        ks.append(k)
        if k >= size:
            masks.append(None)
            found.append([])
            continue
        m, parts = _strokes(ink, horiz, k, text_h)
        masks.append(m)
        found.append([q for q in parts if not _in_text(horiz, q[0], q[2], q[3], words)])
    # Kurze Trennstriche (z. B. im Schriftfeld nur ueber eine Zeile): gelten, wenn sie an beiden Enden auf eine
    # Linie der anderen Richtung treffen - Schrift beruehrt nicht zwei Linien zugleich
    short = int(max(8, 0.8 * text_h))
    t2 = max(5.0, 0.4 * text_h)
    extra = [[], []]
    for d, horiz in enumerate((True, False)):
        omask = masks[1 - d]
        other = _cluster([(p[0], p[1]) for p in found[1 - d]], tol)
        if omask is None or len(other) < 2 or short >= ks[d]:
            continue
        _m, parts = _strokes(ink, horiz, short, text_h)
        for pos, length, a, b in parts:
            if length >= ks[d] or b - a <= 2 * t2 or _in_text(horiz, pos, a, b, words):
                continue
            ends = []
            for e in (a, b):
                hit = [o for o in other if abs(o - e) <= t2]
                if not hit:
                    break
                o, q = int(round(hit[0])), int(round(pos))
                r = int(t2)
                win = omask[max(0, o - r):o + r + 1, max(0, q - r):q + r + 1] if not horiz else \
                    omask[max(0, q - r):q + r + 1, max(0, o - r):o + r + 1]
                if not win.any():                                  # Linie der anderen Richtung muss dort sein
                    break
                ends.append(o)
            if len(ends) == 2 and ends[0] != ends[1]:
                extra[d].append((pos, length))
    ys = _cluster([(p[0], p[1]) for p in found[0]] + extra[0], tol)
    xs = _cluster([(p[0], p[1]) for p in found[1]] + extra[1], tol)
    return ys, xs, ink


def table_lines(gray, text_h=15.0, words=None):
    """Waagerechte und senkrechte Tabellenlinien im Graubild: (ys, xs) - Linienpositionen in Pixeln, sortiert.
    Linien sind lange, schmale Striche; Schrift faellt durch die Mindestlaenge (mehrfache Schrifthoehe) heraus,
    mit words (Textteile) auch Striche, die fast ganz in Text liegen (zusammengewachsene Buchstaben).
    Kuerzere Striche zaehlen, wenn sie zwei Linien der anderen Richtung verbinden."""
    return _lines(gray, text_h, words)[:2]


def _present(ink, horiz, pos, a, b, words, text_h):
    """Ist die Linie an der Lage pos zwischen den Kreuzungspunkten a und b vorhanden (Linienstueck einer Zellgrenze)?
    Geprueft wird ein schmales Band um die Linie ohne die Enden; Stellen, an denen Text ueber die Grenze reicht
    (verbundene Zelle oder Zeile der Texterkennung), zaehlen nicht. Vorhanden, wenn mindestens die Haelfte Tinte ist."""
    hw = int(max(2, round(0.2 * text_h)))
    m = max(3.0, 0.2 * text_h)
    lo, hi = int(round(a + m)), int(round(b - m))
    if hi - lo < 2:
        return True                                                # zu kurz zum Pruefen: Grenze behalten
    p = int(round(pos))
    if horiz:
        cov = ink[max(0, p - hw):p + hw + 1, max(0, lo):hi].any(axis=0)
    else:
        cov = ink[max(0, lo):hi, max(0, p - hw):p + hw + 1].any(axis=1)
    if cov.size == 0:
        return True
    lo = max(0, lo)
    free = np.ones(cov.size, bool)
    for w in words:
        if horiz and w[1] < pos + hw and w[3] > pos - hw:
            s, e = w[0], w[2]
        elif not horiz and w[0] < pos + hw and w[2] > pos - hw:
            s, e = w[1], w[3]
        else:
            continue
        free[max(0, int(s) - lo):max(0, int(np.ceil(e)) - lo)] = False
    if free.sum() >= max(3, 0.25 * cov.size):
        cov = cov[free]
    return float(cov.mean()) >= 0.5


def _merged(ink, rb, cb, words, text_h):
    """Verbundene Zellen im Linienraster: Teilzellen innerhalb des Rahmens, zwischen denen das Linienstueck fehlt,
    gehoeren zusammen. Rueckgabe (owner, ext): owner[(r, c)] = linke obere Teilzelle (r0, c0) einer verbundenen
    Zelle, ext[(r0, c0)] = rechte untere Teilzelle (r1, c1). Nicht rechteckige Gruppen (z. B. durch eine Luecke im
    Scan) bleiben getrennt. Zeile r liegt zwischen rb[r - 1] und rb[r], Spalte c zwischen cb[c - 1] und cb[c]."""
    nr, nc = len(rb) + 1, len(cb) + 1
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for r in range(1, nr - 1):
        for c in range(1, nc - 1):
            find((r, c))
            if c + 1 < nc - 1 and not _present(ink, False, cb[c], rb[r - 1], rb[r], words, text_h):
                parent[find((r, c))] = find((r, c + 1))
            if r + 1 < nr - 1 and not _present(ink, True, rb[r], cb[c - 1], cb[c], words, text_h):
                parent[find((r, c))] = find((r + 1, c))
    groups = {}
    for cell in list(parent):
        groups.setdefault(find(cell), []).append(cell)
    owner, ext = {}, {}
    for cells in groups.values():
        if len(cells) < 2:
            continue
        r0, r1 = min(t[0] for t in cells), max(t[0] for t in cells)
        c0, c1 = min(t[1] for t in cells), max(t[1] for t in cells)
        if (r1 - r0 + 1) * (c1 - c0 + 1) != len(cells):
            continue
        for t in cells:
            owner[t] = (r0, c0)
        ext[(r0, c0)] = (r1, c1)
    return owner, ext


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
    Rueckgabe dict(rows=[[str]], spans=[(zeile, spalte, zeilen, spalten)], ys=[Zeilengrenzen], xs=[Spaltengrenzen],
    by_lines=(zeilen, spalten) aus Linien?).
    Waagerechte/senkrechte Linien gelten, wenn mindestens zwei da sind; sonst bestimmt die Lage der Woerter
    Zeilen bzw. Spalten. Leere Zeilen und Spalten am Rand fallen weg. Bei Linien in beiden Richtungen wird je
    Zellgrenze geprueft, ob das Linienstueck da ist; fehlt es, ist die Zelle verbunden: ihr ganzer Text steht in der
    linken oberen Teilzelle (die anderen bleiben leer) und spans nennt die Ausdehnung (in Zeilen/Spalten von rows)."""
    words = [(float(w[0]), float(w[1]), float(w[2]), float(w[3]), str(w[4]).strip()) for w in words
             if str(w[4]).strip()]
    if size is None:
        size = (gray.shape[1], gray.shape[0]) if gray is not None else (
            max([w[2] for w in words] + [1]), max([w[3] for w in words] + [1]))
    W, H = size
    th = _height(words)
    ys, xs, ink = _lines(gray, th, words) if gray is not None else ([], [], None)
    rows_lines, cols_lines = len(ys) >= 2, len(xs) >= 2
    if not words:
        return dict(rows=[], spans=[], ys=ys, xs=xs, by_lines=(rows_lines, cols_lines))
    if rows_lines:
        rb = list(ys)                    # Grenzen = alle Linien (Text ausserhalb des Rahmens: eigene Randzeile)
    else:
        rb = _rows_from_words(words, th)
    owner, ext = {}, {}
    if cols_lines:
        cb = list(xs)
        if rows_lines and ink is not None:
            owner, ext = _merged(ink, rb, cb, words, th)
        words = [p for w in words for p in _split(w, cb, th)]
    else:
        cb = _cols_from_words(words, W, th, rb)
    nr, nc = len(rb) + 1, len(cb) + 1
    cells = [[[] for _ in range(nc)] for _ in range(nr)]
    for w in words:
        r = _index(rb, (w[1] + w[3]) / 2)
        c = _index(cb, (w[0] + w[2]) / 2)
        r, c = owner.get((r, c), (r, c))                           # Text gehoert zur ganzen verbundenen Zelle
        cells[r][c].append(w)
    rows = [[_join(ws, th) for ws in row] for row in cells]
    used = [[bool(v) for v in row] for row in rows]               # belegt: Text oder Teil einer Zelle mit Text
    for (r0, c0), (r1, c1) in ext.items():
        if rows[r0][c0]:
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    used[r][c] = True
    # Leere Zeilen/Spalten am Rand weg (ausserhalb des Rahmens, doppelte Linien), innen bleiben sie erhalten
    keep_r = [i for i in range(nr) if any(used[i])]
    keep_c = [j for j in range(nc) if any(u[j] for u in used)]
    if not keep_r or not keep_c:
        return dict(rows=[], spans=[], ys=rb, xs=cb, by_lines=(rows_lines, cols_lines))
    R = list(range(keep_r[0], keep_r[-1] + 1))
    C = list(range(keep_c[0], keep_c[-1] + 1))
    if rows_lines:                       # leere Zeilen zwischen eng liegenden (doppelten) Linien entfernen
        gaps = [b - a for a, b in zip([0.0] + list(rb), list(rb) + [float(H)])]
        R = [i for i in R if any(used[i][j] for j in C) or gaps[i] >= 0.8 * th]
    if cols_lines:
        gaps = [b - a for a, b in zip([0.0] + list(cb), list(cb) + [float(W)])]
        C = [j for j in C if any(used[i][j] for i in R) or gaps[j] >= 0.8 * th]
    spans = []
    for (r0, c0), (r1, c1) in ext.items():
        rr = [k for k, i in enumerate(R) if r0 <= i <= r1]
        cc = [k for k, j in enumerate(C) if c0 <= j <= c1]
        if rr and cc and len(rr) * len(cc) > 1:
            spans.append((rr[0], cc[0], len(rr), len(cc)))
    rows = [[rows[i][j] for j in C] for i in R]
    return dict(rows=rows, spans=sorted(spans), ys=rb, xs=cb, by_lines=(rows_lines, cols_lines))


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


def append_table(rows, spans, more, more_spans):
    """Wie append_rows, dazu die verbundenen Zellen beider Teile: (zeilen, spans). Die Spannen des angehaengten Teils
    ruecken nach unten; faellt seine Kopfzeile weg, verlieren Spannen dort diese Zeile."""
    out = append_rows(rows, more)
    drop = len(rows) + len(more) - len(out)          # 1, wenn die wiederholte Kopfzeile wegfiel
    off = len(rows) - drop
    res = [tuple(s) for s in spans or []]
    for r, c, rs, cs in more_spans or []:
        if r < drop:
            rs -= drop - r
            r = drop
        if rs >= 1 and rs * cs > 1:
            res.append((r + off, c, rs, cs))
    return out, res


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


def to_xlsx(rows, path, sheet="Tabelle", spans=()):
    """Zeilen als Excel-Datei (.xlsx): Zahlen als Zahl, sonst Text; erste Zeile fett; Spaltenbreite nach Inhalt.
    spans: verbundene Zellen (zeile, spalte, zeilen, spalten), werden in Excel verbunden (Text oben, umbrochen)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    n = max((len(r) for r in rows), default=0)
    spans = [tuple(int(v) for v in s) for s in spans or ()
             if s[0] < len(rows) and s[1] < n and s[2] >= 1 and s[3] >= 1 and s[2] * s[3] > 1]
    wide = {(r, c): cs for r, c, _rs, cs in spans}
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
            widths[j - 1] = max(widths[j - 1], longest / wide.get((i - 1, j - 1), 1))
    for r, c, rs, cs in spans:
        ws.merge_cells(start_row=r + 1, start_column=c + 1, end_row=min(len(rows), r + rs),
                       end_column=min(n, c + cs))
        ws.cell(row=r + 1, column=c + 1).alignment = Alignment(vertical="top", wrap_text=True)
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = min(60, max(6, int(np.ceil(w)) + 2))
    wb.save(path)
    return path
