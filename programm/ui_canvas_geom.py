"""Zeichenflaeche: Hilfsfunktionen ohne Fenster (Bildpyramiden, Griffe und Treffer von Markierungen)."""
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403


# ----------------------------------------------------------------- Hilfsfunktionen
def pool_ink(x):
    h, w = x.shape
    s = cv2.resize(x, (max(1, w // 2), max(1, h // 2)), interpolation=cv2.INTER_AREA)
    return ((s > 0).astype(np.uint8)) * 255


def pool_color(x):
    e = cv2.erode(x, np.ones((2, 2), np.uint8), anchor=(0, 0))
    return np.ascontiguousarray(e[::2, ::2])


def render_crop(res, y0, y1, x0, x1):
    sl = (slice(y0, y1), slice(x0, x1))
    out = dc.render(res.oa[sl], res.ob[sl], res.both[sl], res.moved[sl])
    if res.zone is not None:
        z = res.zone[sl] & ~(res.oa[sl] | res.ob[sl] | res.both[sl])
        out[z] = (215, 240, 255)
    return out


def build_pyramids(res, min_side=300):
    pa, pb = [res.a], [res.b]
    poa, pob = [res.oa], [res.ob]                   # Stufe 0: bool-Masken direkt (spart 2 Byte je Pixel)
    while min(pa[-1].shape) // 2 >= min_side:
        pa.append(pool_ink(pa[-1]))
        pb.append(pool_ink(pb[-1]))
        poa.append(pool_ink(poa[-1].view(np.uint8) if poa[-1].dtype == bool else poa[-1]))
        pob.append(pool_ink(pob[-1].view(np.uint8) if pob[-1].dtype == bool else pob[-1]))
    h, w = res.a.shape
    pd = [None]
    if len(pa) > 1:
        h2, w2 = h // 2, w // 2
        l1 = np.empty((h2, w2, 3), np.uint8)
        step = 1024
        for y in range(0, h2 * 2, step):
            y1 = min(h2 * 2, y + step)
            l1[y // 2:y1 // 2] = pool_color(render_crop(res, y, y1, 0, w2 * 2))
        pd.append(l1)
        while len(pd) < len(pa):
            pd.append(pool_color(pd[-1]))
    return pa, pb, pd, (poa, pob)


def build_color_pyramids(img, levels):
    """Farbfassung als Stufen wie build_pyramids (jede Stufe halb so gross) oder None."""
    if img is None:
        return None
    out = [img]
    while len(out) < levels:
        h, w = out[-1].shape[:2]
        out.append(cv2.resize(out[-1], (max(1, w // 2), max(1, h // 2)), interpolation=cv2.INTER_AREA))
    return out


def invert_view(img, mode):
    """Anzeige mit hellen Linien auf dunklem Grund. Einzelzeichnungen: Helligkeit umkehren, Farbton behalten;
    Vergleich: nur Papier dunkel und Grau heller, Rot/Blau/Gruen bleiben erkennbar."""
    if mode in ("A", "B"):
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = 255 - lab[:, :, 0]
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    out = img.copy()
    white = (img == 255).all(axis=2)
    gray = (img == 150).all(axis=2)
    out[white] = (26, 24, 22)
    out[gray] = (175, 175, 175)
    return out


def _run(a, i):
    """Grenzen (lo, hi) der zusammenhaengenden Wahr-Werte um Index i."""
    lo = hi = i
    n = len(a)
    while lo > 0 and a[lo - 1]:
        lo -= 1
    while hi < n - 1 and a[hi + 1]:
        hi += 1
    return lo, hi


def _dist_seg(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def ann_handles(shape, a):
    """Anfasser einer Anmerkung: Liste (Name, x, y) in Bildkoordinaten."""
    t = a["type"]
    if t == "measure":                               # Messpunkte und der Wert (verschiebbar)
        cx, cy, _ang, _ax, _ay = rep.measure_label(a, shape)
        return [(f"m{i}", q[0], q[1]) for i, q in enumerate(a["pts"])] + [("lbl", cx, cy)]
    if t in ("arrow", "line"):
        return [("p1", a["x"], a["y"]), ("p2", a["x2"], a["y2"])]
    if t in ("polyline", "polygon") and a.get("pts"):
        return [(f"v{i}", q[0], q[1]) for i, q in enumerate(a["pts"])]
    if t == "pen" and a.get("pts"):                  # Freihand: an den Ecken skalieren
        x0, y0, x1, y1 = rep.pts_bbox(a["pts"])
        return [("tl", x0, y0), ("tr", x1, y0), ("bl", x0, y1), ("br", x1, y1)]
    if t in rep.RECT_TYPES:
        x0, y0, x1, y1 = min(a["x"], a["x2"]), min(a["y"], a["y2"]), max(a["x"], a["x2"]), max(a["y"], a["y2"])
        return [("tl", x0, y0), ("tr", x1, y0), ("bl", x0, y1), ("br", x1, y1)]
    b = rep.ann_bounds(shape, a)
    if t == "number":
        return [("size", b[2], a["y"])]
    if t == "text" and a.get("w"):                   # Textfeld: rechts die Breite, unten rechts die Groesse
        return [("tw", a["x"] + a["w"], (b[1] + b[3]) / 2), ("size", b[2], b[3])]
    return [("size", b[2], b[3])]


def ann_hit(shape, a, ix, iy, m):
    t = a["type"]
    if t == "measure":
        m += rep.ann_line_w(shape, a["size"])
        for gk, gd in rep.measure_geometry(a):
            if gk == "circle":
                if abs(math.hypot(ix - gd[0], iy - gd[1]) - gd[2]) <= m:
                    return True
            else:
                pl = list(gd) + ([gd[0]] if gk == "poly" else [])
                if any(_dist_seg(ix, iy, *pl[i], *pl[i + 1]) <= m for i in range(len(pl) - 1)):
                    return True
        return False
    if t in ("arrow", "line"):
        return _dist_seg(ix, iy, a["x"], a["y"], a["x2"], a["y2"]) <= m + rep.ann_line_w(shape, a["size"])
    if t in rep.PTS_TYPES and a.get("pts"):
        pl = list(a["pts"]) + ([a["pts"][0]] if t == "polygon" else [])
        mm = m + rep.ann_line_w(shape, a["size"])
        if len(pl) == 1:
            return math.hypot(ix - pl[0][0], iy - pl[0][1]) <= mm
        if any(_dist_seg(ix, iy, *pl[i], *pl[i + 1]) <= mm for i in range(len(pl) - 1)):
            return True
        if t == "polygon" and len(pl) > 3:           # Polygon: auch innen anklickbar
            return cv2.pointPolygonTest(np.float32(a["pts"]), (float(ix), float(iy)), False) >= 0
        return False
    if t == "image":
        return min(a["x"], a["x2"]) <= ix <= max(a["x"], a["x2"]) and min(a["y"], a["y2"]) <= iy <= max(a["y"], a["y2"])
    if t == "ellipse":
        cx, cy = (a["x"] + a["x2"]) / 2, (a["y"] + a["y2"]) / 2
        rx, ry = max(1.0, abs(a["x2"] - a["x"]) / 2), max(1.0, abs(a["y2"] - a["y"]) / 2)
        d = math.hypot((ix - cx) / rx, (iy - cy) / ry)
        mm = m + rep.ann_line_w(shape, a["size"])
        return abs(d - 1) * min(rx, ry) <= mm
    if t in rep.RECT_TYPES:
        x0, y0, x1, y1 = min(a["x"], a["x2"]), min(a["y"], a["y2"]), max(a["x"], a["x2"]), max(a["y"], a["y2"])
        if t == "cloud":                          # Wolke ragt ueber das Rechteck hinaus
            m += rep.cloud_radius(shape, a["size"])
        inside = x0 - m <= ix <= x1 + m and y0 - m <= iy <= y1 + m
        if t in ("highlight", "redact", "pixelate"):   # Flaechen: ganz anklickbar
            return inside
        deep = x0 + m < ix < x1 - m and y0 + m < iy < y1 - m
        return inside and not deep
    b = rep.ann_bounds(shape, a)
    return b[0] - m <= ix <= b[2] + m and b[1] - m <= iy <= b[3] + m


def apply_handle(shape, a, name, px, py):
    t = a["type"]
    if t == "measure" and name.startswith("m"):
        a["pts"][int(name[1:])] = [px, py]
        a["x"], a["y"] = a["pts"][0]
        a["x2"], a["y2"] = a["pts"][-1]
        return
    if name == "lbl":                                # Messwert verschieben (Abstand zum Ankerpunkt merken)
        _cx, _cy, _ang, ax, ay = rep.measure_label(dict(a, lo=None), shape)
        a["lo"] = [px - ax, py - ay]
        return
    if name.startswith("v") and a.get("pts"):
        a["pts"][int(name[1:])] = [px, py]
        a["x"], a["y"], a["x2"], a["y2"] = rep.pts_bbox(a["pts"])
        return
    if t == "pen" and a.get("pts") and name in ("tl", "tr", "bl", "br"):
        x0, y0, x1, y1 = rep.pts_bbox(a["pts"])
        fx, fy = (x1 if "l" in name else x0), (y1 if "t" in name else y0)   # fester Punkt: gegenueberliegende Ecke
        ox_, oy_ = (x0 if "l" in name else x1), (y0 if "t" in name else y1)
        sx = (px - fx) / (ox_ - fx) if abs(ox_ - fx) > 1e-6 else 1.0
        sy = (py - fy) / (oy_ - fy) if abs(oy_ - fy) > 1e-6 else 1.0
        if abs(sx) < 0.02 or abs(sy) < 0.02:
            return
        a["pts"] = [[fx + (q[0] - fx) * sx, fy + (q[1] - fy) * sy] for q in a["pts"]]
        a["x"], a["y"], a["x2"], a["y2"] = rep.pts_bbox(a["pts"])
        return
    if name == "tw":
        a["w"] = max(4 * rep.ann_unit(shape), px - a["x"])
        return
    if name == "p1":
        a["x"], a["y"] = px, py
    elif name == "p2":
        a["x2"], a["y2"] = px, py
    elif t in rep.RECT_TYPES:
        x0, y0, x1, y1 = min(a["x"], a["x2"]), min(a["y"], a["y2"]), max(a["x"], a["x2"]), max(a["y"], a["y2"])
        if "l" in name:
            x0 = px
        else:
            x1 = px
        if "t" in name:
            y0 = py
        else:
            y1 = py
        a["x"], a["x2"] = min(x0, x1), max(x0, x1)
        a["y"], a["y2"] = min(y0, y1), max(y0, y1)
    elif name == "size":
        unit = rep.ann_unit(shape)
        if t == "number":
            a["size"] = float(np.clip(abs(px - a["x"]) / (0.95 * 10 * unit), 0.5, 20))
        else:
            b = rep.ann_bounds(shape, a)
            w0 = max(1.0, b[2] - b[0])
            a["size"] = float(np.clip(a["size"] * max(8.0, px - a["x"]) / w0, 0.5, 20))
