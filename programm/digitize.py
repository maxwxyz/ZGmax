"""Diagramm digitalisieren: Kurven aus einem Diagrammbild (z. B. Kraft-Weg-Diagramm einer Feder) als Wertetabelle.

Ablauf: Tinte binarisieren und Gitter/Achsen/Text abziehen (clean_ink), Achsen erkennen (find_axes), Achsen mit je
zwei Punkten kalibrieren (Calib, linear oder logarithmisch), Kurve vom Klickpunkt aus spaltenweise verfolgen
(trace_curve), Pixel -> Werte (to_values), auf gemeinsame x-Stuetzstellen bringen (make_xs, resample), Polynom
anpassen (fit_poly) oder glaetten (smooth_resample) und als CSV oder Excel ausgeben (to_csv, to_xlsx). Dazu:
Achsen selbst aus der Texterkennung kalibrieren (auto_axes) und farbige Kurven nach Farbton trennen (color_layers).

Ohne Qt. Bilder sind numpy-Arrays (Grau HxW oder BGR HxWx3), Masken uint8 (>0 = Tinte). Punkte sind (x, y) in
Pixeln des Diagrammbilds (Spalte, Zeile; y nach unten).
"""
import math
import re
import statistics

import cv2
import numpy as np


# ---------------------------------------------------------------------------------------------- Kalibrierung

class Axis:
    """Eine Achse: Anteil f (0 am ersten, 1 am zweiten Kalibrierpunkt) <-> Wert, linear oder logarithmisch."""

    def __init__(self, v1, v2, log=False):
        v1, v2 = float(v1), float(v2)
        if log and (v1 <= 0 or v2 <= 0):
            raise ValueError("log axis needs positive values")
        if v1 == v2:
            raise ValueError("axis values must differ")
        self.v1, self.v2, self.log = v1, v2, bool(log)

    def _t(self, v):
        return np.log10(v) if self.log else v

    def value(self, f):
        a, b = self._t(self.v1), self._t(self.v2)
        t = a + np.asarray(f, float) * (b - a)
        return np.power(10.0, t) if self.log else t

    def frac(self, v):
        a, b = self._t(self.v1), self._t(self.v2)
        v = np.asarray(v, float)
        with np.errstate(invalid="ignore", divide="ignore"):
            return (self._t(v) - a) / (b - a)


class Calib:
    """Kalibrierung aus zwei Punkten auf der x-Achse (px1, px2) und zwei auf der y-Achse (py1, py2) mit Werten.

    Die Abbildung ist affin: ein Punkt P wird zerlegt in P = X1 + s*(X2-X1) + t*(Y2-Y1) -> x-Anteil s, und
    P = Y1 + s'*(X2-X1) + t'*(Y2-Y1) -> y-Anteil t'. Damit stimmen auch leicht gedrehte oder schiefe Scans."""

    def __init__(self, px1, vx1, px2, vx2, py1, vy1, py2, vy2, xlog=False, ylog=False):
        self.px1, self.px2 = np.asarray(px1, float), np.asarray(px2, float)
        self.py1, self.py2 = np.asarray(py1, float), np.asarray(py2, float)
        self.ax, self.ay = Axis(vx1, vx2, xlog), Axis(vy1, vy2, ylog)
        u, v = self.px2 - self.px1, self.py2 - self.py1
        m = np.array([u, v]).T                              # Spalten u, v
        if np.linalg.norm(u) < 1 or np.linalg.norm(v) < 1 or abs(np.linalg.det(m)) < 1e-6 * np.linalg.norm(u) * np.linalg.norm(v):
            raise ValueError("calibration points degenerate")
        self.m, self.minv = m, np.linalg.inv(m)

    def to_values(self, pts):
        """Pixelpunkte (N, 2) -> Werte (N, 2)."""
        p = np.asarray(pts, float).reshape(-1, 2)
        s = (self.minv @ (p - self.px1).T)[0]
        t = (self.minv @ (p - self.py1).T)[1]
        return np.column_stack([self.ax.value(s), self.ay.value(t)])

    def to_pixels(self, vals):
        """Werte (N, 2) -> Pixelpunkte (N, 2)."""
        v = np.asarray(vals, float).reshape(-1, 2)
        s, t = self.ax.frac(v[:, 0]), self.ay.frac(v[:, 1])
        # P = X1 + s*u + t1*v  und  P = Y1 + s1*u + t*v  ->  P = X1 + s*u + t*v + (Y1 - X1 in v-Richtung)
        d = self.minv @ (self.py1 - self.px1)               # Y1 - X1 = d0*u + d1*v
        return self.px1 + np.outer(s, self.m[:, 0]) + np.outer(t + d[1], self.m[:, 1])

    @property
    def x_reversed(self):
        """x-Werte fallen im Bild von links nach rechts (z. B. 7 -> 5)."""
        return (self.ax.v2 - self.ax.v1) * (self.px2[0] - self.px1[0]) < 0

    @property
    def y_reversed(self):
        """y-Werte fallen im Bild von unten nach oben (Bildzeilen wachsen nach unten)."""
        return (self.ay.v2 - self.ay.v1) * (self.py2[1] - self.py1[1]) > 0


def to_values(points, calib):
    """Pixelpunkte -> Werte (N, 2); leere Liste bleibt leer."""
    if points is None or len(points) == 0:
        return np.zeros((0, 2))
    return calib.to_values(points)


# ---------------------------------------------------------------------------------------------- Tinte bereinigen

def binarize(img, thr=None):
    """Tintenmaske (uint8 0/255). thr=None: Otsu auf dem dunkelsten Kanal, aber hoechstens 200."""
    gray = img if img.ndim == 2 else cv2.min(cv2.min(img[:, :, 0], img[:, :, 1]), img[:, :, 2])
    gray = np.ascontiguousarray(gray, np.uint8)
    if thr is None:
        t, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thr = min(200, max(60, t))
    return (gray < thr).astype(np.uint8) * 255


def line_masks(ink, frac=0.25, min_len=30):
    """Lange exakt waagerechte und senkrechte Linien (Gitter, Achsen, Rahmen) als Masken (h, v), je uint8.
    Leicht schraege (bis etwa 1 Grad) oder unterbrochene Linien eines Scans werden durch eine Verdickung vorher noch
    erkannt."""
    h, w = ink.shape
    lh = max(min_len, int(frac * w))
    lv = max(min_len, int(frac * h))
    thick_v = cv2.dilate(ink, np.ones((5, 9), np.uint8))         # dazu Unterbrechungen (Rauschen, duenne Linien)
    thick_h = cv2.dilate(ink, np.ones((9, 5), np.uint8))
    mh = cv2.morphologyEx(thick_v, cv2.MORPH_OPEN, np.ones((1, lh), np.uint8))
    mv = cv2.morphologyEx(thick_h, cv2.MORPH_OPEN, np.ones((lv, 1), np.uint8))
    mh = cv2.dilate(cv2.erode(mh, np.ones((1, 9), np.uint8)), np.ones((3, 9), np.uint8)) & ink
    mv = cv2.dilate(cv2.erode(mv, np.ones((9, 1), np.uint8)), np.ones((9, 3), np.uint8)) & ink
    return mh, mv


def _dash_chains(lab, st, cand, min_chain=3):
    """Striche gestrichelter oder strichpunktierter Linien unter den kleinen Teilen finden.

    lab, st: Ergebnis von connectedComponentsWithStats, cand: bool je Teil (kleine Teile). Ein Teil ist ein Strich,
    wenn er laenglich ist; zwei Striche gehoeren zusammen, wenn der naechste in Verlaengerung (Richtung des Strichs)
    nach einer Luecke von hoechstens etwa zwei Strichlaengen folgt und aehnlich gerichtet ist (je Strich und Seite
    der naechste). Ketten aus mindestens min_chain Strichen sind Linien. Liefert (Kurvenstriche, Gitterstriche) als
    bool je Teil und die Bruecken der Kurvenstriche als Liste ((x0, y0), (x1, y1), Strichstaerke); Gitterstriche
    liegen in langen, exakt waagerechten oder senkrechten Ketten (gestricheltes Gitter)."""
    n = len(st)
    keep, grid = np.zeros(n, bool), np.zeros(n, bool)
    idx = np.flatnonzero(cand)
    if len(idx) < min_chain or len(idx) > 20000:
        return keep, grid, []
    sel = np.zeros(n, bool)
    sel[idx] = True
    ys, xs = np.nonzero(sel[lab])
    ls = lab[ys, xs]
    xs, ys = xs.astype(float), ys.astype(float)
    cnt = np.maximum(np.bincount(ls, minlength=n), 1).astype(float)
    mx, my = np.bincount(ls, xs, n) / cnt, np.bincount(ls, ys, n) / cnt      # Schwerpunkte je Teil
    dx, dy = xs - mx[ls], ys - my[ls]
    mxx, myy, mxy = (np.bincount(ls, w, n)[idx] / cnt[idx] for w in (dx * dx, dy * dy, dx * dy))
    half = 0.5 * (mxx + myy)
    root = np.sqrt(0.25 * (mxx - myy) ** 2 + mxy ** 2)
    l1, l2 = half + root, np.maximum(half - root, 1.0 / 12)
    ang = 0.5 * np.arctan2(2 * mxy, mxx - myy)
    length = np.sqrt(12 * l1) + 1                          # gleichmaessig belegte Strecke: Varianz = L^2 / 12
    ok = (length >= 4) & (l1 / l2 >= 4)                    # laenglich (Seitenverhaeltnis etwa 2:1 und mehr)
    sx, sy, ang, length, idx = mx[idx][ok], my[idx][ok], ang[ok], length[ok], idx[ok]
    m = len(idx)
    if m < min_chain:
        return keep, grid, []
    thick = np.maximum(1.0, cnt[idx] / length)
    ux, uy = np.cos(ang), np.sin(ang)
    order = np.argsort(sx)
    sxs = sx[order]
    rmax = float(4 * length.max() + 4 + length.max())

    def neighbours(ends, factor, min_cos, min_along):
        """Je (Strich, Seite) aus ends den naechsten passenden Strich auf dieser Seite: dict -> (Luecke, Nachbar)."""
        best = {}
        for i in sorted({e[0] for e in ends}):
            lo, hi = np.searchsorted(sxs, [sx[i] - rmax, sx[i] + rmax])
            j = order[lo:hi]
            j = j[j != i]
            if not len(j):
                continue
            ddx, ddy = sx[j] - sx[i], sy[j] - sy[i]
            dist = np.hypot(ddx, ddy)
            gap = dist - 0.5 * (length[i] + length[j])
            along = ddx * ux[i] + ddy * uy[i]
            same = np.abs(ux[i] * ux[j] + uy[i] * uy[j]) >= min_cos
            reach = factor * np.maximum(length[i], length[j]) + 4
            good = (gap >= -2) & (gap <= reach) & same & (np.abs(along) >= min_along * dist)
            for side in (1, -1):
                if (i, side) not in ends:
                    continue
                g = good & (np.sign(along) == side)
                if g.any():
                    k = int(np.argmin(np.where(g, gap, np.inf)))
                    best[(i, side)] = (float(gap[k]), int(j[k]))
        return best

    def mutual(best):
        """Nur gegenseitige Nachbarn verbinden: Kanten (i, k) und die dabei belegten Seiten."""
        edges, used = set(), set()
        for (i, side), (_, k) in best.items():
            back = [(k, sd) for sd in (1, -1) if best.get((k, sd), (0, -1))[1] == i]
            if back:
                edges.add((min(i, k), max(i, k)))
                used.add((i, side))
                used.add(back[0])
        return edges, used
    # Luecke hoechstens etwa zwei Strichlaengen; danach freie Kettenenden noch einmal weiter (etwa vier
    # Strichlaengen, z. B. ueber eine Kreuzung mit einer anderen Kurve), dafuer genauer in Verlaengerung
    allends = {(i, sd) for i in range(m) for sd in (1, -1)}
    edges, used = mutual(neighbours(allends, 2.0, np.cos(np.radians(35)), 0.85))
    more, _ = mutual(neighbours(allends - used, 4.0, np.cos(np.radians(15)), 0.97))
    edges |= more
    parent = np.arange(m)

    def root_of(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, k in edges:
        a, b = root_of(i), root_of(k)
        if a != b:
            parent[a] = b
    roots = np.array([root_of(i) for i in range(m)])
    size = np.bincount(roots, minlength=m)
    chain = size[roots] >= min_chain
    hw = float(lab.shape[1]), float(lab.shape[0])
    curve = np.zeros(m, bool)
    for r in np.unique(roots[chain]):
        mem = roots == r
        a = np.abs(np.degrees(ang[mem]))
        flat = (a <= 2).all() and np.ptp(sy[mem]) <= 2 and np.ptp(sx[mem]) >= 0.3 * hw[0]
        steep = (np.abs(a - 90) <= 2).all() and np.ptp(sx[mem]) <= 2 and np.ptp(sy[mem]) >= 0.3 * hw[1]
        (grid if flat or steep else keep)[idx[mem]] = True
        curve |= mem & (not (flat or steep))
    bridges = []
    for i, k in edges:
        if not (curve[i] and curve[k]):
            continue
        ends = []
        for q in (i, k):
            h = 0.5 * length[q] - 1
            ends.append([(sx[q] + h * ux[q], sy[q] + h * uy[q]), (sx[q] - h * ux[q], sy[q] - h * uy[q])])
        p, q = min(((p, q) for p in ends[0] for q in ends[1]), key=lambda t: math.dist(*t))
        bridges.append((p, q, float(min(thick[i], thick[k]))))
    return keep, grid, bridges


def remove_small(ink, size):
    """Zusammenhaengende Teile, deren Rahmen in beiden Richtungen hoechstens size px misst (Text, Ziffern, Punkte),
    entfernen."""
    if size <= 0:
        return ink
    n, lab, st, _ = cv2.connectedComponentsWithStats((ink > 0).astype(np.uint8), connectivity=8)
    small = (st[:, cv2.CC_STAT_WIDTH] <= size) & (st[:, cv2.CC_STAT_HEIGHT] <= size)
    small[0] = False
    out = ink.copy()
    out[small[lab]] = 0
    return out


def dash_masks(free, size):
    """Striche gestrichelter Kurven in der Tinte ohne lange Linien (free): (Kurvenstriche, Gitterstriche) als
    Masken. Beruecksichtigt werden nur kleine Teile (hoechstens size px), siehe _dash_chains. Die Luecken zwischen
    den Strichen einer Kurve werden in der Kurvenmaske geschlossen."""
    keep = np.zeros_like(free)
    grid = np.zeros_like(free)
    if size <= 0:
        return keep, grid
    n, lab, st, _ = cv2.connectedComponentsWithStats((free > 0).astype(np.uint8), connectivity=8)
    small = (st[:, cv2.CC_STAT_WIDTH] <= size) & (st[:, cv2.CC_STAT_HEIGHT] <= size)
    small[0] = False
    k, g, bridges = _dash_chains(lab, st, small)
    keep[k[lab]] = 255
    grid[g[lab]] = 255
    for p, q, t in bridges:                               # Luecken schliessen: Kurve wie durchgezogen verfolgen
        cv2.line(keep, (int(round(p[0] * 4)), int(round(p[1] * 4))), (int(round(q[0] * 4)), int(round(q[1] * 4))),
                 255, max(1, int(round(t))), cv2.LINE_8, shift=2)
    return keep, grid


def default_text_size(shape):
    """Vorschlag fuer die Textgroesse: etwa 3 % der laengeren Seite, mindestens 6 px."""
    return max(6, int(round(0.03 * max(shape[:2]))))


def clean_from(ink, masks, text_size, dashes=True):
    """Wie clean_ink, aber aus fertiger Tintenmaske und Linienmasken (mh, mv) von line_masks - beim Aendern der
    Textgroesse muss nicht neu binarisiert und nach Linien gesucht werden."""
    mh, mv = masks
    lines = mh | mv
    # Text zuerst entfernen (solange Kurvenstuecke zwischen Gitterlinien noch am Gitter haengen), dann die Linien;
    # danach nur noch Krumen (Reste von Teilstrichen und Kreuzungspunkten). Striche gestrichelter Kurven werden
    # ohne die Linien gesucht (dort von Gitterlinien getrennt) und bleiben; ein gestricheltes Gitter zaehlt zu den
    # Linien.
    keep = None
    if dashes and text_size > 0:
        free = ink & ~lines
        free |= lines & cv2.dilate(free, np.ones((5, 5), np.uint8))   # von Gitterlinien zerschnittene Striche
        keep, grid = dash_masks(free, text_size)
        lines = lines | grid
    out = remove_small(ink, text_size) & ~lines
    if keep is not None:
        out |= keep & ~lines
    out = remove_small(out, 3)
    return out, lines


def clean_ink(img, thr=None, text_size=None, line_frac=0.25, dashes=True):
    """Tinte ohne Gitter, Achsen, Rahmen und Text: (bereinigte Maske, Linienmaske). img Grau oder BGR.
    text_size=None: Vorschlag aus der Bildgroesse, 0 = Text behalten. dashes: Striche gestrichelter Kurven nicht
    als Text entfernen."""
    ink = binarize(img, thr)
    if text_size is None:
        text_size = default_text_size(ink.shape)
    return clean_from(ink, line_masks(ink, line_frac), text_size, dashes)


# ---------------------------------------------------------------------------------------------- Achsen

def _groups(idx):
    """Aufeinanderfolgende Indizes zu Gruppen (Start, Ende inklusive)."""
    if len(idx) == 0:
        return []
    br = np.flatnonzero(np.diff(idx) > 1)
    starts = np.r_[idx[0], idx[br + 1]]
    ends = np.r_[idx[br], idx[-1]]
    return list(zip(starts.tolist(), ends.tolist()))


def _line_list(mask, axis):
    """Linien einer Richtung: Liste (Mitte, Anfang, Ende, Laenge). axis=1: waagerecht (Zeilen), 0: senkrecht."""
    prof = (mask > 0).sum(axis=axis)
    if prof.max(initial=0) == 0:
        return []
    out = []
    for a, b in _groups(np.flatnonzero(prof > 0)):
        band = mask[a:b + 1, :] if axis == 1 else mask[:, a:b + 1]
        cov = np.flatnonzero((band > 0).any(axis=0 if axis == 1 else 1))
        out.append(((a + b) / 2.0, int(cov[0]), int(cov[-1]), int(prof[a:b + 1].max())))
    return out


def find_axes(ink, masks=None):
    """Achsen und Gitter in der Tintenmaske (binarize) erkennen. Liefert dict mit
    x_axis=(y, x0, x1) oder None (unterste lange waagerechte Linie), y_axis=(x, y0, y1) oder None (linkeste lange
    senkrechte Linie), hlines=[y, ...], vlines=[x, ...] (alle langen Linien, Mitte). masks: fertige Linienmasken
    (mh, mv) von line_masks(ink), sonst werden sie hier gesucht."""
    mh, mv = masks if masks is not None else line_masks(ink)
    hl, vl = _line_list(mh, 1), _line_list(mv, 0)
    res = dict(x_axis=None, y_axis=None, hlines=[c for c, *_ in hl], vlines=[c for c, *_ in vl])
    if hl:
        longest = max(n for *_, n in hl)
        cand = [l for l in hl if l[3] >= 0.6 * longest]
        c, a, b, _ = max(cand, key=lambda l: l[0])
        res["x_axis"] = (c, a, b)
    if vl:
        longest = max(n for *_, n in vl)
        cand = [l for l in vl if l[3] >= 0.6 * longest]
        c, a, b, _ = min(cand, key=lambda l: l[0])
        res["y_axis"] = (c, a, b)
    return res


def line_band(mask, pos, horizontal):
    """Zeilen (horizontal) bzw. Spalten einer Linie in der Linienmaske um Position pos: (Anfang, Ende inklusive)."""
    prof = (mask > 0).sum(axis=1 if horizontal else 0)
    i = int(np.clip(round(pos), 0, len(prof) - 1))
    if prof[i] == 0:
        return i, i
    a, b = i, i
    while a > 0 and prof[a - 1] > 0:
        a -= 1
    while b < len(prof) - 1 and prof[b + 1] > 0:
        b += 1
    return a, b


def snap_line(centers, p, radius=12):
    """Naechste Gitterlinie (oder Achse) im Umkreis radius um p oder None."""
    if not centers:
        return None
    c = min(centers, key=lambda v: abs(v - p))
    return float(c) if abs(c - p) <= radius else None


def snap_tick(ink, axis_pos, along, p, horizontal, radius=12, band=12):
    """Kalibrierklick an einen Teilstrich oder eine Gitterlinie einrasten.

    horizontal=True: Achse waagerecht in Zeile axis_pos, p = Klick-x; gesucht wird in einem Band ober- und unterhalb
    der Achse (ohne die Achse selbst) die naechste Tintenspalte im Umkreis radius. Liefert die eingerastete
    Koordinate entlang der Achse oder p, wenn nichts in der Naehe ist. along wird nicht gebraucht (Bereich der Achse),
    ist aber fuer Aufrufer praktisch zum Begrenzen."""
    h, w = ink.shape
    a = int(round(axis_pos))
    if horizontal:
        rows = list(range(max(0, a - band), max(0, a - 3))) + list(range(min(h, a + 4), min(h, a + band + 1)))
        if not rows:
            return p
        prof = (ink[rows, :] > 0).sum(axis=0)
        n = w
    else:
        cols = list(range(max(0, a - band), max(0, a - 3))) + list(range(min(w, a + 4), min(w, a + band + 1)))
        if not cols:
            return p
        prof = (ink[:, cols] > 0).sum(axis=1)
        n = h
    lo, hi = max(0, int(p - radius)), min(n, int(p + radius) + 1)
    if along is not None:
        lo, hi = max(lo, int(along[0])), min(hi, int(along[1]) + 1)
    if hi <= lo:
        return p
    idx = np.flatnonzero(prof[lo:hi] >= 2) + lo
    if len(idx) == 0:
        return p
    best = min(_groups(idx), key=lambda g: abs((g[0] + g[1]) / 2.0 - p))
    return (best[0] + best[1]) / 2.0


# ---------------------------------------------------------------------------------------------- Verfolgen

def _runs(col):
    """Tintenlaeufe einer Spalte: Array (k, 2) mit Anfang, Ende (inklusive)."""
    idx = np.flatnonzero(col)
    if len(idx) == 0:
        return np.zeros((0, 2), int)
    return np.array(_groups(idx), int)


def nearest_ink(ink, p, radius=15):
    """Naechstes Tintenpixel zu p im Umkreis radius oder None."""
    h, w = ink.shape
    x, y = int(round(p[0])), int(round(p[1]))
    x0, x1, y0, y1 = max(0, x - radius), min(w, x + radius + 1), max(0, y - radius), min(h, y + radius + 1)
    ys, xs = np.nonzero(ink[y0:y1, x0:x1])
    if len(xs) == 0:
        return None
    d = (xs + x0 - p[0]) ** 2 + (ys + y0 - p[1]) ** 2
    k = int(np.argmin(d))
    return int(xs[k] + x0), int(ys[k] + y0)


def stroke_width(ink, x, y):
    """Strichstaerke an (x, y): kuerzerer der beiden Laeufe senkrecht/waagerecht durch den Punkt."""
    def run(line, i):
        if not line[i]:
            return 0
        a = i
        while a > 0 and line[a - 1]:
            a -= 1
        b = i
        while b < len(line) - 1 and line[b + 1]:
            b += 1
        return b - a + 1
    return max(1, min(run(ink[:, x] > 0, y), run(ink[y, :] > 0, x)))


def _predictor(xs, ys, deg, slope):
    """Vorhersage fuer eine Kreuzung: (Polynom in x - xr, xr) durch die letzten freien Punkte (Gerade: Parabeln
    schiessen beim Verlaengern leicht weg); zu wenige Punkte: Gerade mit der bisherigen Steigung."""
    deg = min(deg, len(xs) - 1)
    if deg < 1 or np.ptp(xs) == 0:
        return np.array([slope, ys[-1]]), xs[-1]
    return np.polyfit(np.asarray(xs) - xs[-1], ys, deg), xs[-1]


def _slope(xs, ys):
    """Steigung der Ausgleichsgeraden (wie np.polyfit(xs, ys, 1)[0], aber ohne dessen Aufwand je Spalte)."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx if sxx > 0 else 0.0


def _trace_dir(ink, full, x0, y0, step, run0, tol, max_gap, x_lo, x_hi, window, max_contact=150, seed=()):
    """Eine Richtung (step +1/-1) spaltenweise verfolgen; liefert Liste (x, y) ohne den Startpunkt.

    ink: bereinigte Tinte, full: dazu die entfernten Gitterlinien, beide transponiert (Zeile = Bildspalte, damit
    der Zugriff je Spalte schnell ist). Gelaeufe werden in full gebildet, damit eine
    Kurve, die auf einer Gitterlinie liegt oder sie kreuzt, wie an einer Kreuzung behandelt wird (Vorhersage statt
    abgeschnittener Mitte); ein Lauf zaehlt aber nur, wenn er auch bereinigte Tinte enthaelt (nie einer Gitterlinie
    allein folgen). seed: Punkte von der anderen Seite des Starts (in Laufrichtung vor dem Start) fuer die
    Anfangsrichtung.
    run0: Laenge des Tintenlaufs am Start (Anfangswert fuer die uebliche Lauflaenge). Kreuzungen: liegt eine zweite
    Kurve an (Lauf deutlich laenger als ueblich, oder die Nachbarkurve hat sich bis auf Beruehrung genaehert und ist
    dann im eigenen Lauf verschwunden), wird die Richtung von vorher eingefroren (Gerade durch die letzten freien
    Punkte) und ihr gefolgt, bis die Kurven wieder getrennt nebeneinander liegen."""
    hx = [float(p[0]) for p in seed] + [float(x0)]     # freie (eindeutige) Punkte fuer die Richtung
    hy = [float(p[1]) for p in seed] + [float(y0)]
    lens = [float(run0)]
    out = []
    x = x0
    gap = 0
    slope = 0.0
    frozen = None                                       # eingefrorene Vorhersage waehrend einer Kreuzung
    contact = 0                                         # Spalten in der Kreuzung
    touching = False                                    # Nachbarkurve hat den eigenen Lauf beruehrt
    overlap = 0                                         # Spalten, in denen die Kurven genau uebereinander liegen
    on_line = 0                                         # Spalten, in denen die Kurve ganz auf einer Gitterlinie liegt
    last_strong = 0                                     # Anzahl Punkte bis zum letzten mit eigener Tinte
    curve_contact = False                               # Kreuzung mit einer anderen Kurve (nicht nur Gitterlinie)
    run_cols = 99                                       # Spalten mit Tinte seit der letzten Luecke
    fresh = 0                                           # davon in lens eingetragen
    while True:
        x += step
        if x < x_lo or x > x_hi:
            break
        if frozen is not None:
            c, xr = frozen
            pred = float(np.polyval(c, x - xr))
        else:
            n = min(window, len(hx))
            if n >= 3 and hx[-1] != hx[-n]:
                slope = _slope(hx[-n:], hy[-n:])
            pred = hy[-1] + slope * (x - hx[-1])
        runs = _runs(full[x] > 0)
        t = tol + 0.1 * gap
        best, bd, weak = None, None, False
        for k, (a, b) in enumerate(runs):
            w = full is not ink and not ink[x, a:b + 1].any()     # nur Gitterlinie
            if w and (gap or on_line >= 4 * lens[0] + 10):
                continue
            d = 0.0 if a <= pred <= b else min(abs(a - pred), abs(b - pred))
            if d <= t and (bd is None or d < bd or (d == bd and weak and not w)):
                best, bd, weak = k, d, w
        on_line = on_line + 1 if weak else 0
        if best is None:
            if gap == 0 and fresh and len(lens) > 2:     # Strichende (gestrichelt): Laeufe dort duenner, vergessen
                del lens[-min(2, fresh, len(lens) - 1):]
            gap += 1
            run_cols = fresh = 0
            if gap > max_gap:
                break
            continue
        gap = 0
        run_cols += 1
        a, b = runs[best]
        L = float(statistics.median(lens[-40:]))
        near = 2 * L + 2                                # Abstand (Kante zu Kante), ab dem eine Nachbarkurve stoert
        nd = min([a - runs[k][1] - 1 for k in range(best)] + [runs[k][0] - b - 1 for k in range(best + 1, len(runs))],
                 default=1e9)
        long_run = L + max(1.5, 0.3 * L)
        merged = b - a + 1 > long_run or weak
        alone = nd >= near
        if weak:
            by_curve = False
        else:                                           # eigene Tinte allein zu lang: zweite Kurve, nicht Gitter
            ys = np.flatnonzero(ink[x, a:b + 1])
            by_curve = ys[-1] - ys[0] + 1 > long_run
        if frozen is None:
            ambiguous = merged or (touching and alone)
            curve_contact = by_curve or (touching and alone)
        else:                                           # in der Kreuzung bis die Nachbarkurve getrennt daneben liegt
            curve_contact = curve_contact or by_curve
            ambiguous = merged or (alone and curve_contact and overlap < 4 * L + 10)
        if ambiguous and contact < max_contact:
            if frozen is None:
                frozen = _predictor(hx[-2 * window:], hy[-2 * window:], 1, slope)
                overlap = 0
            contact += 1
            if merged:
                lo, hi = a - 0.5 + L / 2, b + 0.5 - L / 2
                y = (a + b) / 2.0 if hi <= lo else min(max(pred, lo), hi)
            else:                                       # Kurven liegen genau uebereinander
                overlap += 1
                y = min(max(pred, a), b)
            out.append((float(x), y))
            if not weak:
                last_strong = len(out)
            touching = False
            continue
        frozen, contact = None, 0                       # eindeutig: Mitte des Laufs
        touching = nd <= 2
        y = (a + b) / 2.0
        if run_cols > 2:                                # Strichanfang (duenner) nicht als uebliche Lauflaenge
            lens.append(float(b - a + 1))
            fresh += 1
        hx.append(float(x))
        hy.append(y)
        out.append((float(x), y))
        last_strong = len(out)
    return out[:last_strong]                            # nie auf einer Gitterlinie allein enden


def trace_curve(ink, start_xy, lines=None, bounds=None, max_gap=None, tol=None, window=12, snap_radius=15):
    """Kurve vom Klickpunkt aus nach links und rechts verfolgen (je Spalte ein Punkt).

    Je Spalte wird die Tintengruppe gewaehlt, die der Fortsetzung (Gerade durch die letzten Punkte) am naechsten
    liegt; an Kreuzungen (zu langer Lauf) wird der Vorhersage gefolgt, Luecken (entfernte Gitterlinien,
    Strichelung) bis max_gap Spalten werden ueberbrueckt. lines: von clean_ink entfernte Gitterlinien (empfohlen,
    dann werden Kurven auf Gitterlinien sauber weiterverfolgt). bounds=(x0, x1) begrenzt die Spalten.
    Liefert Array (N, 2) sortiert nach x, leer wenn am Klickpunkt keine Tinte ist."""
    h, w = ink.shape
    p = nearest_ink(ink, start_xy, snap_radius)
    if p is None:
        return np.zeros((0, 2))
    x0, y0 = p
    full = ink if lines is None else cv2.bitwise_or(ink, lines)
    if tol is None:
        tol = max(4.0, 2.5 * stroke_width(ink, x0, y0))
    # Startspalte: naechste Spalte nahe am Klick, in der die Kurve frei liegt (nicht auf einer Gitterlinie); bei
    # gestrichelten Kurven nicht am duennen Ende eines Strichs (Lauf mindestens so lang wie ueblich in der Naehe)
    found = []
    for dx in sorted(range(-12, 13), key=abs):
        x = x0 + dx
        if not 0 <= x < w:
            continue
        cand = [(a, b) for a, b in _runs(full[:, x] > 0) if ink[a:b + 1, x].any()
                and (a <= y0 <= b or min(abs(a - y0), abs(b - y0)) <= tol + abs(dx))]
        if len(cand) == 1 and np.array_equal(ink[cand[0][0]:cand[0][1] + 1, x] > 0,
                                             np.ones(cand[0][1] - cand[0][0] + 1, bool)):
            found.append((x, cand[0]))
    start = None
    if found:
        usual = float(np.median([b - a + 1 for _, (a, b) in found]))
        start = next(f for f in found if f[1][1] - f[1][0] + 1 >= usual)
    if start is None:
        col = _runs(ink[:, x0] > 0)
        start = (x0, min(col, key=lambda r: 0 if r[0] <= y0 <= r[1] else min(abs(r[0] - y0), abs(r[1] - y0))))
        usual = 0
    x0, (a, b) = start
    run0 = max(b - a + 1, usual)
    yc = (a + b) / 2.0
    if max_gap is None:
        max_gap = max(30, int(0.05 * w))
    x_lo, x_hi = (0, w - 1) if bounds is None else (max(0, int(bounds[0])), min(w - 1, int(bounds[1])))
    args = (np.ascontiguousarray(ink.T), np.ascontiguousarray(full.T) if lines is not None else None, x0, yc)
    if args[1] is None:
        args = (args[0], args[0], x0, yc)
    rest = (run0, tol, max_gap, x_lo, x_hi, window)
    # zuerst rechts, dann links mit der Anfangsrichtung von rechts, dann rechts noch einmal mit der von links
    right = _trace_dir(*args, 1, *rest)
    left = _trace_dir(*args, -1, *rest, seed=right[:window][::-1])
    right = _trace_dir(*args, 1, *rest, seed=left[:window][::-1])
    pts = left[::-1] + [(float(x0), yc)] + right
    return np.array(pts, float)


def merge_points(old, new):
    """Neu verfolgte Punkte in eine Kurve uebernehmen: im x-Bereich von new ersetzen, sonst behalten."""
    old = np.asarray(old, float).reshape(-1, 2)
    new = np.asarray(new, float).reshape(-1, 2)
    if len(new) == 0:
        return old
    lo, hi = new[:, 0].min(), new[:, 0].max()
    keep = old[(old[:, 0] < lo) | (old[:, 0] > hi)]
    out = np.vstack([keep, new])
    return out[np.argsort(out[:, 0], kind="stable")]


# ---------------------------------------------------------------------------------------------- Ergebnis

def _clean_xy(vals):
    """Werte nach x sortieren, gleiche x mitteln, NaN entfernen -> (xs, ys)."""
    v = np.asarray(vals, float).reshape(-1, 2)
    v = v[np.isfinite(v).all(axis=1)]
    if len(v) == 0:
        return np.zeros(0), np.zeros(0)
    ux, inv = np.unique(v[:, 0], return_inverse=True)
    uy = np.bincount(inv, weights=v[:, 1]) / np.bincount(inv)
    return ux, uy


def make_xs(curves, count=None, step=None, extend=0.0):
    """Gemeinsame x-Stuetzstellen ueber den Bereich aller Kurven: count Stellen gleichmaessig oder Schrittweite step
    (an Vielfachen von step ausgerichtet). extend: Bereich je Seite um so viel erweitern (Kurvenenden, die unter
    Achsen oder Gitterlinien verschwinden)."""
    xs = [c[:, 0] for c in curves if len(c)]
    if not xs:
        return np.zeros(0)
    allx = np.concatenate(xs)
    allx = allx[np.isfinite(allx)]
    if len(allx) == 0:
        return np.zeros(0)
    lo, hi = float(allx.min()) - extend, float(allx.max()) + extend
    if step:
        step = abs(float(step))
        a = math.ceil(lo / step - 1e-9) * step
        n = int(math.floor((hi - a) / step + 1e-9)) + 1
        if n > 100000:
            raise ValueError("too many rows")
        return np.round(a + np.arange(max(0, n)) * step, 12)
    count = max(2, int(count or 21))
    return np.linspace(lo, hi, count)


def resample(curves, xs, extend=0.0):
    """Kurven (Liste von Wertearrays (N, 2)) an den Stellen xs linear interpolieren -> Tabelle (len(xs), Kurven);
    ausserhalb des Bereichs einer Kurve (plus extend je Seite, dort geradlinig verlaengert) NaN."""
    xs = np.asarray(xs, float)
    out = np.full((len(xs), len(curves)), np.nan)
    for k, c in enumerate(curves):
        cx, cy = _clean_xy(c)
        if len(cx) == 0:
            continue
        if len(cx) == 1:
            out[np.abs(xs - cx[0]) <= max(extend, 1e-12), k] = cy[0]
            continue
        eps = 1e-12 * max(1.0, abs(cx[0]), abs(cx[-1]))
        inside = (xs >= cx[0] - eps) & (xs <= cx[-1] + eps)
        out[inside, k] = np.interp(xs[inside], cx, cy)
        if extend > 0:                                  # knapp ausserhalb: Gerade durch die Endpunkte verlaengern
            m = min(8, len(cx))
            for sel, ex, ey in ((xs < cx[0] - eps) & (xs >= cx[0] - extend - eps), cx[:m], cy[:m]), \
                               ((xs > cx[-1] + eps) & (xs <= cx[-1] + extend + eps), cx[-m:], cy[-m:]):
                if sel.any():
                    out[sel, k] = np.polyval(np.polyfit(ex, ey, 1), xs[sel])
    return out


def fit_poly(xs, ys, deg):
    """Polynom vom Grad deg anpassen: (Koeffizienten hoechste Potenz zuerst, Bestimmtheitsmass R^2).
    Zu wenige Punkte: Grad wird verringert."""
    x, y = np.asarray(xs, float), np.asarray(ys, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) == 0:
        return np.zeros(0), float("nan")
    deg = max(0, min(int(deg), len(np.unique(x)) - 1))
    c = np.polyfit(x, y, deg)
    fit = np.polyval(c, x)
    ss_res = float(((y - fit) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else (1.0 if ss_res == 0 else 0.0)
    return c, r2


def fmt_num(v, decimal=",", digits=6):
    """Zahl kurz mit digits signifikanten Stellen; NaN -> leer."""
    if v is None or not np.isfinite(v):
        return ""
    s = f"{float(v):.{digits}g}"
    if s == "-0":
        s = "0"
    return s.replace(".", decimal) if decimal != "." else s


def poly_text(coeffs, x="x", y="y", decimal=",", digits=5):
    """Polynom als lesbarer Text, z. B. 'y = 1,2·x² - 3·x + 0,5'."""
    sup = {2: "²", 3: "³"}
    deg = len(coeffs) - 1
    parts = []
    for k, c in enumerate(coeffs):
        pw = deg - k
        if c == 0 and deg > 0:
            continue
        s = fmt_num(abs(c), decimal, digits)
        term = s if pw == 0 else f"{s}·{x}" + (sup.get(pw, f"^{pw}") if pw > 1 else "")
        sign = "-" if c < 0 else "+"
        parts.append((sign, term))
    if not parts:
        return f"{y} = 0"
    first = ("-" if parts[0][0] == "-" else "") + parts[0][1]
    rest = "".join(f" {s} {t}" for s, t in parts[1:])
    return f"{y} = {first}{rest}"


def to_csv(xs, table, header, sep=";", decimal=",", digits=6):
    """Wertetabelle als CSV-Text: Kopfzeile header (x-Name, Kurvennamen), dann je Stuetzstelle eine Zeile;
    leere Felder, wo eine Kurve nicht definiert ist. sep '\\t' fuer Tabellenkalkulation per Zwischenablage."""
    def cell(s):
        s = str(s)
        if sep in s or '"' in s or "\n" in s:
            s = '"' + s.replace('"', '""') + '"'
        return s
    lines = [sep.join(cell(h) for h in header)]
    for i, x in enumerate(xs):
        row = [fmt_num(x, decimal, digits)] + [fmt_num(v, decimal, digits) for v in table[i]]
        lines.append(sep.join(row))
    return "\n".join(lines) + "\n"


def points_csv(curves, names, header_xy, sep=";", decimal=",", digits=6):
    """Rohpunkte aller Kurven untereinander: Kurve; x; y."""
    lines = [sep.join(["", header_xy[0], header_xy[1]])]
    for name, c in zip(names, curves):
        for x, y in np.asarray(c, float).reshape(-1, 2):
            lines.append(sep.join([name, fmt_num(x, decimal, digits), fmt_num(y, decimal, digits)]))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------------------------- Achsen per Texterkennung

_NUM = re.compile(r"^[+-]?(\d+([.,]\d*)?|[.,]\d+)([eE][+-]?\d+)?$")


def parse_number(text):
    """Achsbeschriftung als Zahl ('1,5', '-20', '0.25', '1e3') oder None. Ein gelesenes O statt 0 wird korrigiert;
    Tausenderpunkte werden nicht erkannt (bei Diagrammachsen selten)."""
    t = (text or "").strip().replace("−", "-").replace("–", "-").replace(" ", "")
    if re.fullmatch(r"[\dOo.,+-]+", t or "x") and re.search(r"\d", t):
        t = t.replace("O", "0").replace("o", "0")
    if not _NUM.match(t):
        return None
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return None


def _fit_axis(pos, vals):
    """Pixelposition = a + b * t(Wert) mit t = Wert (linear) oder log10 (logarithmisch) robust ausgleichen.
    Liefert (log, a, b, benutzte Indizes) oder None. Ausreisser (falsch gelesene Zahlen) fallen weg."""
    pos, vals = np.asarray(pos, float), np.asarray(vals, float)
    best = None
    for log in (False, True):
        if log and (vals <= 0).any():
            continue
        t = np.log10(vals) if log else vals
        idx = np.arange(len(t))
        a = b = 0.0
        while len(idx) >= 2 and np.ptp(t[idx]) > 0:
            b, a = np.polyfit(t[idx], pos[idx], 1)
            res = np.abs(pos[idx] - (a + b * t[idx]))
            if res.max() <= max(3.0, 0.01 * np.ptp(pos[idx])) or len(idx) == 2:
                break
            idx = np.delete(idx, int(np.argmax(res)))
        if len(idx) < 2 or np.ptp(t[idx]) == 0 or abs(b) < 1e-9:
            continue
        if len(idx) == 2 and len(t) > 3:                 # nur zwei von vielen passen: unsicher
            continue
        err = float(np.abs(pos[idx] - (a + b * t[idx])).mean())
        score = (len(idx), -err)
        if best is None or score > best[0]:
            best = (score, (log, float(a), float(b), idx))
    return None if best is None else best[1]


def auto_axes(ink, ocr_items, axes=None):
    """Achsen selbst kalibrieren: Zahlen der Texterkennung (x0, y0, x1, y1, text, ...) unter der x-Achse bzw.
    links der y-Achse den Teilstrichen/Gitterlinien zuordnen und die Abbildung ausgleichen (linear oder log).

    Liefert dict mit Schluesseln x1, x2, y1, y2 -> ((px, py), Wert), xlog, ylog, nx, ny (Anzahl benutzter
    Beschriftungen); fehlt eine Achse, fehlen ihre Schluessel. ink: Tintenmaske (binarize)."""
    if axes is None:
        axes = find_axes(ink)
    out = {}
    items = []
    for it in ocr_items or []:
        v = parse_number(it[4])
        if v is not None:
            x0, y0, x1, y1 = (float(c) for c in it[:4])
            items.append((x0, y0, x1, y1, v))
    xa, ya = axes.get("x_axis"), axes.get("y_axis")
    if xa:
        ay, a, b = xa
        pos, vals = [], []
        for x0, y0, x1, y1, v in items:
            cy, cx, th, tw = (y0 + y1) / 2, (x0 + x1) / 2, max(4.0, y1 - y0), x1 - x0
            if not (ay < cy < ay + 4 * th + 30 and a - 0.6 * tw - 10 <= cx <= b + 0.6 * tw + 10):
                continue
            if ya and x1 < ya[0] - 2:                    # links neben der y-Achse: gehoert zur y-Achse
                continue
            r = max(6.0, 0.5 * tw + 4)
            px = snap_line(axes["vlines"], cx, r)
            px = px if px is not None else snap_tick(ink, ay, None, cx, True, radius=r)
            pos.append(px)
            vals.append(v)
        f = _fit_axis(pos, vals) if len(pos) >= 2 else None
        if f:
            log, a0, b0, idx = f
            vs = np.asarray(vals)[idx]
            for key, v in (("x1", vs.min()), ("x2", vs.max())):
                out[key] = ((a0 + b0 * (np.log10(v) if log else v), float(ay)), float(v))
            out["xlog"], out["nx"] = log, len(idx)
    if ya:
        axx, a, b = ya
        pos, vals = [], []
        for x0, y0, x1, y1, v in items:
            cy, th, tw = (y0 + y1) / 2, max(4.0, y1 - y0), x1 - x0
            if not (x1 < axx + 4 and axx - tw - 4 * th - 30 < x0 and a - 2 * th <= cy <= b + 2 * th):
                continue
            if xa and y0 > xa[0] + 2:                    # unter der x-Achse: gehoert zur x-Achse
                continue
            r = max(6.0, 0.5 * th + 4)
            py = snap_line(axes["hlines"], cy, r)
            py = py if py is not None else snap_tick(ink, axx, None, cy, False, radius=r)
            pos.append(py)
            vals.append(v)
        f = _fit_axis(pos, vals) if len(pos) >= 2 else None
        if f:
            log, a0, b0, idx = f
            vs = np.asarray(vals)[idx]
            for key, v in (("y1", vs.min()), ("y2", vs.max())):
                out[key] = ((float(axx), a0 + b0 * (np.log10(v) if log else v)), float(v))
            out["ylog"], out["ny"] = log, len(idx)
    return out


# ---------------------------------------------------------------------------------------------- Farbige Kurven

def color_layers(img, min_sat=70, min_pixels=150, hue_tol=12):
    """Farbige Tinte nach Farbton trennen: Liste dict(mask (uint8 0/255), color (B, G, R), hue), groesste zuerst.
    Schwarz, Grau und Weiss gehoeren zu keiner Ebene. Leere Liste bei Graubildern."""
    if img.ndim != 3:
        return []
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[:, :, 0].astype(int), hsv[:, :, 1], hsv[:, :, 2]
    colored = (sat >= min_sat) & (val >= 50)
    if colored.sum() < min_pixels:
        return []
    hist = np.bincount(hue[colored], minlength=180).astype(float)
    k = np.exp(-0.5 * (np.arange(-6, 7) / 2.5) ** 2)
    sm = np.convolve(np.r_[hist[-6:], hist, hist[:6]], k, "same")[6:-6]     # Farbton ist ein Kreis
    peaks = [i for i in range(180) if sm[i] > 0 and sm[i] >= sm[i - 1] and sm[i] > sm[(i + 1) % 180]]
    peaks.sort(key=lambda i: -sm[i])
    layers, taken = [], np.zeros(180, bool)
    for p in peaks:
        if taken[p]:
            continue
        d = np.abs(((np.arange(180) - p) + 90) % 180 - 90)
        band = (d <= hue_tol) & ~taken
        m = colored & band[hue]
        if m.sum() < min_pixels:
            continue
        taken |= band
        col = tuple(int(c) for c in np.median(img[m], axis=0))
        layers.append(dict(mask=m.astype(np.uint8) * 255, color=col, hue=int(p)))
    layers.sort(key=lambda l: -int((l["mask"] > 0).sum()))
    return layers


def layer_at(layers, p, radius=6):
    """Index der Farbebene, die am Punkt p (im Umkreis radius) die meiste Tinte hat, oder None."""
    best, n = None, 0
    x, y = int(round(p[0])), int(round(p[1]))
    for k, l in enumerate(layers):
        m = l["mask"]
        h, w = m.shape
        c = int((m[max(0, y - radius):min(h, y + radius + 1), max(0, x - radius):min(w, x + radius + 1)] > 0).sum())
        if c > n:
            best, n = k, c
    return best


def layer_start(mask):
    """Startpunkt zum Verfolgen einer Farbebene: Mitte des breitesten Teils, in einer Spalte mit genau einem Lauf."""
    n, lab, st, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), connectivity=8)
    if n <= 1:
        return None
    k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_WIDTH]))
    x0, w = int(st[k, cv2.CC_STAT_LEFT]), int(st[k, cv2.CC_STAT_WIDTH])
    for dx in sorted(range(w), key=lambda d: abs(d - w // 2)):
        r = _runs(mask[:, x0 + dx] > 0)
        if len(r) == 1:
            return float(x0 + dx), (r[0][0] + r[0][1]) / 2.0
    return None


# ---------------------------------------------------------------------------------------------- Glatte Kurve

def natural_spline(xk, yk, xs):
    """Natuerlicher kubischer Spline durch (xk, yk), ausgewertet an xs (xk aufsteigend, mindestens 2 Punkte)."""
    xk, yk, xs = np.asarray(xk, float), np.asarray(yk, float), np.asarray(xs, float)
    n = len(xk)
    if n < 3:
        return np.interp(xs, xk, yk)
    hk = np.diff(xk)
    a = np.zeros((n, n))
    r = np.zeros(n)
    a[0, 0] = a[-1, -1] = 1.0
    for i in range(1, n - 1):
        a[i, i - 1], a[i, i], a[i, i + 1] = hk[i - 1], 2 * (hk[i - 1] + hk[i]), hk[i]
        r[i] = 6 * ((yk[i + 1] - yk[i]) / hk[i] - (yk[i] - yk[i - 1]) / hk[i - 1])
    m = np.linalg.solve(a, r)                            # zweite Ableitungen
    i = np.clip(np.searchsorted(xk, xs) - 1, 0, n - 2)
    t0, t1, hh = xs - xk[i], xk[i + 1] - xs, hk[i]
    return (m[i] * t1 ** 3 + m[i + 1] * t0 ** 3) / (6 * hh) + (yk[i] / hh - m[i] * hh / 6) * t1 \
        + (yk[i + 1] / hh - m[i + 1] * hh / 6) * t0


def smooth_knots(xs, ys, knots=10):
    """Geglaettete Stuetzpunkte: knots Stellen gleichmaessig ueber den Bereich, je Stelle eine lokal gewichtete
    Ausgleichsgerade (Tricube-Gewichte ueber zwei Abstaende) -> (xk, yk)."""
    x, y = np.asarray(xs, float), np.asarray(ys, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 2 or np.ptp(x) == 0:
        return x[:1], y[:1]
    knots = int(max(2, min(knots, len(np.unique(x)))))
    xk = np.linspace(x.min(), x.max(), knots)
    span = 2.0 * (xk[1] - xk[0])
    yk = np.empty(knots)
    for j, c in enumerate(xk):
        d = np.abs(x - c) / span
        wgt = np.where(d < 1, (1 - d ** 3) ** 3, 0.0)
        if (wgt > 0).sum() < 2:
            yk[j] = np.interp(c, x, y)
            continue
        sw = np.sqrt(wgt)
        A = np.column_stack([np.ones_like(x), x - c]) * sw[:, None]
        yk[j] = np.linalg.lstsq(A, y * sw, rcond=None)[0][0]
    return xk, yk


def smooth_resample(curves, xs, knots=10, extend=0.0):
    """Wie resample, aber mit glatter Kurve (natuerlicher Spline durch smooth_knots) statt der Messpunkte."""
    xs = np.asarray(xs, float)
    out = np.full((len(xs), len(curves)), np.nan)
    for k, c in enumerate(curves):
        cx, cy = _clean_xy(c)
        if len(cx) < 2:
            continue
        xk, yk = smooth_knots(cx, cy, knots)
        eps = extend + 1e-12 * max(1.0, abs(cx[0]), abs(cx[-1]))
        inside = (xs >= cx[0] - eps) & (xs <= cx[-1] + eps)
        out[inside, k] = natural_spline(xk, yk, xs[inside])
    return out


def poly_resample(curves, xs, deg, extend=0.0):
    """Wie resample, aber mit dem ausgeglichenen Polynom vom Grad deg (nur im Bereich der Kurve)."""
    xs = np.asarray(xs, float)
    out = np.full((len(xs), len(curves)), np.nan)
    for k, c in enumerate(curves):
        cx, cy = _clean_xy(c)
        if len(cx) < 2:
            continue
        co, _ = fit_poly(cx, cy, deg)
        eps = extend + 1e-12 * max(1.0, abs(cx[0]), abs(cx[-1]))
        inside = (xs >= cx[0] - eps) & (xs <= cx[-1] + eps)
        out[inside, k] = np.polyval(co, xs[inside])
    return out


def r2_of(y, fit):
    """Bestimmtheitsmass R^2 von fit gegenueber y."""
    y, fit = np.asarray(y, float), np.asarray(fit, float)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    ss_res = float(((y - fit) ** 2).sum())
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0


# ---------------------------------------------------------------------------------------------- Excel

def to_xlsx(path, xs, table, header, sheet="Werte", chart_title="", x_title="", y_title="", xlog=False,
            ylog=False, notes=(), notes_sheet="Funktionen", colors=None, polys=None, xrev=False, yrev=False,
            labels=("Polynom", "Kurve", "von x", "bis x")):
    """Wertetabelle als Excel-Datei mit eingebettetem Punktdiagramm (je Kurve eine Linie). openpyxl wird erst hier
    geladen. notes: Textzeilen (z. B. Funktionen) auf einem zweiten Blatt; colors: Linienfarben 'RRGGBB'.

    polys: je Kurve (Koeffizienten hoechste Potenz zuerst, R^2, x von, x bis) oder None. Dann stehen oben die
    Koeffizienten a0, a1, ... je Kurve in Zellen und neben den gemessenen Werten je Kurve eine Spalte mit der Formel
    (z. B. =$B$2+$C$2*A5+$D$2*A5^2) - Aendern von x oder eines Koeffizienten rechnet sofort neu. labels: Texte
    (Polynom, Kurve, von x, bis x). xrev/yrev: Achse faellt im Bild (z. B. 7 -> 5); das Diagramm zeigt sie ebenso
    umgekehrt."""
    from openpyxl import Workbook
    from openpyxl.chart import Reference, ScatterChart, Series
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter as col
    wb = Workbook()
    ws = wb.active
    ws.title = sheet[:31]
    bold = Font(bold=True)
    names = [str(h) for h in header[1:]]
    polys = list(polys or [])
    fits = [(k, p) for k, p in enumerate(polys[:len(names)]) if p is not None and len(p[0])]
    widths = {}

    def put(r, c, v, b=False):
        cell = ws.cell(row=r, column=c, value=v)
        if b:
            cell.font = bold
        if isinstance(v, str) and not v.startswith("="):
            widths[c] = max(widths.get(c, 10), min(40, len(v) + 4))
        return cell
    top = 1                                               # Zeile der Tabellenkoepfe
    coef_row = {}
    if fits:
        deg = max(len(p[0]) for _, p in fits) - 1
        put(1, 1, labels[1], True)
        for i in range(deg + 1):
            put(1, 2 + i, f"a{i}", True)
        for j, t in enumerate(("R²", labels[2], labels[3])):
            put(1, deg + 3 + j, t, True)
        for row, (k, (co, r2, lo, hi)) in enumerate(fits, start=2):
            coef_row[k] = row
            put(row, 1, names[k])
            for i, a in enumerate(np.asarray(co, float)[::-1]):         # a0 zuerst
                put(row, 2 + i, float(a))
            for j, v in enumerate((r2, lo, hi)):
                put(row, deg + 3 + j, float(v) if np.isfinite(v) else None)
        top = len(fits) + 3                               # eine Zeile Abstand
    head = [str(header[0])] + names + [f"{names[k]} ({labels[0]})" for k, _ in fits]
    for c, h in enumerate(head, start=1):
        put(top, c, h, True)
    for i, x in enumerate(xs):
        r = top + 1 + i
        put(r, 1, float(x))
        for k, v in enumerate(table[i]):
            put(r, 2 + k, None if not np.isfinite(v) else float(v))
        for j, (k, (co, *_)) in enumerate(fits):
            if not np.isfinite(table[i][k]):
                continue                                  # nur wo die Kurve gemessen ist
            cr = coef_row[k]
            terms = [f"${col(2 + p)}${cr}" + ("" if p == 0 else f"*A{r}" + ("" if p == 1 else f"^{p}"))
                     for p in range(len(co))]
            put(r, 2 + len(names) + j, "=" + "+".join(terms))
    for c, w in widths.items():
        ws.column_dimensions[col(c)].width = w
    ws.freeze_panes = f"A{top + 1}"
    wb.calculation.fullCalcOnLoad = True                  # Formeln beim Oeffnen berechnen
    n = len(xs)
    ch = ScatterChart()
    if chart_title:
        ch.title = chart_title
    ch.style = 13
    ch.x_axis.title = x_title or str(header[0])
    if y_title:
        ch.y_axis.title = y_title
    ch.x_axis.delete = False                              # sonst blendet Excel die Achsen aus
    ch.y_axis.delete = False
    if xlog:
        ch.x_axis.scaling.logBase = 10
    if ylog:
        ch.y_axis.scaling.logBase = 10
    if xrev:                                              # wie im Bild: Werte fallen nach rechts, y-Achse bleibt links
        ch.x_axis.scaling.orientation = "maxMin"
        ch.y_axis.crosses = "max"
    if yrev:                                              # Werte fallen nach oben, x-Achse bleibt unten
        ch.y_axis.scaling.orientation = "maxMin"
        ch.x_axis.crosses = "max"
    ch.display_blanks = "gap"
    xref = Reference(ws, min_col=1, min_row=top + 1, max_row=top + n)
    for k in range(1, len(header)):
        yref = Reference(ws, min_col=k + 1, min_row=top, max_row=top + n)
        s = Series(yref, xref, title_from_data=True)
        s.marker.symbol = "none"
        s.smooth = False
        if colors and k - 1 < len(colors) and colors[k - 1]:
            s.graphicalProperties.line.solidFill = colors[k - 1]
        s.graphicalProperties.line.width = 22000          # EMU, etwa 1,7 pt
        ch.series.append(s)
    ch.width, ch.height = 18, 11
    ws.add_chart(ch, f"{col(len(head) + 2)}{top + 1}")
    if notes:
        ws2 = wb.create_sheet(notes_sheet[:31])
        for line in notes:
            ws2.append([line])
        ws2.column_dimensions["A"].width = 110
    wb.save(path)
