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


def _chain(first, n):
    """Pyramide aus einer Stufe 0: n weitere Stufen, jede halb so gross."""
    out = [first]
    for _ in range(n):
        x = out[-1]
        out.append(pool_ink(x.view(np.uint8) if x.dtype == bool else x))
    return out


def build_pyramids(res, min_side=300):
    """Bildstufen fuer schnelles Zoomen. A, B, ihre Abweichungen und die Vergleichsansicht entstehen parallel
    (OpenCV gibt die Python-Sperre frei); bool-Masken als Stufe 0 direkt (spart 2 Byte je Pixel)."""
    from concurrent.futures import ThreadPoolExecutor
    n, side = 0, min(res.a.shape)
    while side // 2 >= min_side:
        side //= 2
        n += 1
    h, w = res.a.shape

    def compare_view():
        pd = [None]
        if n:
            h2, w2 = h // 2, w // 2
            l1 = np.empty((h2, w2, 3), np.uint8)
            step = 1024
            for y in range(0, h2 * 2, step):
                y1 = min(h2 * 2, y + step)
                l1[y // 2:y1 // 2] = pool_color(render_crop(res, y, y1, 0, w2 * 2))
            pd.append(l1)
            while len(pd) < n + 1:
                pd.append(pool_color(pd[-1]))
        return pd
    with ThreadPoolExecutor(max_workers=5) as ex:
        jobs = [ex.submit(_chain, m, n) for m in (res.a, res.b, res.oa, res.ob)] + [ex.submit(compare_view)]
        pa, pb, poa, pob, pd = (j.result() for j in jobs)
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


SIDES = ("t", "b", "l", "r")
CORNERS = ("tl", "tr", "bl", "br")
_OPPOSITE = {"tl": "br", "tr": "bl", "bl": "tr", "br": "tl", "t": "b", "b": "t", "l": "r", "r": "l"}


def _box_handles(x0, y0, x1, y1):
    """Ecken und Seitenmitten eines Rechtecks."""
    xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
    return [("tl", x0, y0), ("tr", x1, y0), ("bl", x0, y1), ("br", x1, y1),
            ("t", xm, y0), ("b", xm, y1), ("l", x0, ym), ("r", x1, ym)]


def _local_handles(shape, a):
    """Anfasser ohne Drehung (Name, x, y) in Bildkoordinaten."""
    t = a["type"]
    if t == "measure":                               # Messpunkte und der Wert (verschiebbar)
        cx, cy, _ang, _ax, _ay = rep.measure_label(a, shape)
        return [(f"m{i}", q[0], q[1]) for i, q in enumerate(a["pts"])] + [("lbl", cx, cy)]
    if t in ("arrow", "line"):
        return [("p1", a["x"], a["y"]), ("p2", a["x2"], a["y2"])]
    if t in ("polyline", "polygon") and a.get("pts"):
        return [(f"v{i}", q[0], q[1]) for i, q in enumerate(a["pts"])]
    if t == "pen" and a.get("pts"):                  # Freihand: an Ecken und Seiten skalieren
        return _box_handles(*rep.pts_bbox(a["pts"]))
    if t in rep.RECT_TYPES:
        return _box_handles(*rep.rot_box(shape, a))
    b = rep.ann_frame(shape, a)
    if t == "number":
        return [("size", b[2], a["y"])]
    if t == "text" and a.get("w"):                   # Textfeld: rechts die Breite, unten rechts die Groesse
        return [("tw", a["x"] + a["w"], (b[1] + b[3]) / 2), ("size", b[2], b[3])]
    return [("size", b[2], b[3])]


def rot_grip(shape, a, scale=None):
    """Drehanfasser ueber der oberen Seitenmitte: (Fusspunkt, Anfasser) in Bildkoordinaten oder None.
    scale = Bildschirmpixel je Bildpixel (Abstand 24 Bildschirmpixel), sonst fester Abstand im Bild."""
    t = a["type"]
    if t in rep.ROT_TYPES:
        x0, y0, x1, y1 = rep.rot_box(shape, a)
    elif t in rep.PTS_TYPES and len(a.get("pts") or []) > 1:   # Linienzug, Polygon, Freihand: Punkte drehen
        x0, y0, x1, y1 = rep.pts_bbox(a["pts"])
        if max(x1 - x0, y1 - y0) <= 0:
            return None
    else:
        return None
    d = 24 / scale if scale else 8 * rep.ann_unit(shape)
    if t == "cloud":                                 # Wolke ragt ueber die Box hinaus
        d += rep.cloud_radius(shape, a["size"])
    cx = (x0 + x1) / 2
    base, top = (cx, y0), (cx, y0 - d)
    r = rep.ann_rot(a)
    if r:
        c = rep.rot_center(shape, a)
        base, top = rep.rot_pt(*base, *c, r), rep.rot_pt(*top, *c, r)
    return base, top


def ann_handles(shape, a, scale=None):
    """Anfasser einer Anmerkung: Liste (Name, x, y) in Bildkoordinaten (bei gedrehten Markierungen mitgedreht).
    Ecken (tl, tr, bl, br), Seitenmitten (t, b, l, r) und der Drehanfasser "rot" bei Arten mit Box."""
    hs = _local_handles(shape, a)
    r = rep.ann_rot(a)
    if r:
        c = rep.rot_center(shape, a)
        hs = [(n, *rep.rot_pt(hx, hy, *c, r)) for n, hx, hy in hs]
    g = rot_grip(shape, a, scale)
    if g is not None:
        hs.append(("rot", *g[1]))
    return hs


def handle_center(shape, a):
    """Bezugspunkt fuer die Richtung eines Anfassers (Mitte der Box)."""
    t = a["type"]
    if t in rep.ROT_TYPES:
        return rep.rot_center(shape, a)
    b = rep.pts_bbox(a["pts"]) if t in rep.PTS_TYPES and a.get("pts") else rep.ann_frame(shape, a)
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def size_cursor(dx, dy):
    """Groessen-Mauszeiger fuer die Richtung (dx, dy) auf dem Bildschirm (y nach unten)."""
    ang = math.degrees(math.atan2(dy, dx)) % 180
    k = int(((ang + 22.5) % 180) // 45)              # 0 waagerecht, 1 fallend, 2 senkrecht, 3 steigend
    return (Qt.CursorShape.SizeHorCursor, Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeVerCursor,
            Qt.CursorShape.SizeBDiagCursor)[k]


_ROT_CURSOR = []


def rotate_cursor():
    """Mauszeiger fuer den Drehanfasser: kreisfoermiger Pfeil (einmal erzeugt)."""
    if not _ROT_CURSOR:
        from PySide6.QtGui import QCursor
        pm = QPixmap(24, 24)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx = cy = 12.0
        r = 7.0
        end = math.radians(330)                      # Bogen von 60 Grad ueber 270 Grad (gegen den Uhrzeigersinn)
        ex, ey = cx + r * math.cos(end), cy - r * math.sin(end)
        tx, ty = -math.sin(end), -math.cos(end)      # Laufrichtung am Bogenende
        head = QPolygonF([QPointF(ex + tx * 4, ey + ty * 4), QPointF(ex - ty * 3.5, ey + tx * 3.5),
                          QPointF(ex + ty * 3.5, ey - tx * 3.5)])
        for col, w in (("white", 4.0), ("black", 1.6)):
            pen = QPen(QColor(col), w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), 60 * 16, 270 * 16)
            p.setBrush(QColor(col))
            p.drawPolygon(head)
        p.end()
        _ROT_CURSOR.append(QCursor(pm, 12, 12))
    return _ROT_CURSOR[0]


def apply_rotation(shape, a, orig, px, py, step=None):
    """Drehanfasser gezogen: a aus dem Stand beim Anfassen (orig) so drehen, dass der Anfasser zum Punkt (px, py)
    zeigt. step = Raster in Grad (Umschalt: 15). Arten mit Box bekommen das Feld "rot", Linienzug, Polygon und
    Freihand werden ueber ihre Punkte gedreht. Gibt den Winkel zurueck."""
    if orig["type"] in rep.ROT_TYPES:
        cx, cy = rep.rot_center(shape, orig)
        ang = math.degrees(math.atan2(px - cx, -(py - cy)))
        if step:
            ang = round(ang / step) * step
        ang = round(ang % 360.0, 2)
        if ang in (0.0, 360.0):
            a.pop("rot", None)
        else:
            a["rot"] = ang
        return ang
    x0, y0, x1, y1 = rep.pts_bbox(orig["pts"])
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ang = math.degrees(math.atan2(px - cx, -(py - cy)))
    if step:
        ang = round(ang / step) * step
    a["pts"] = [list(rep.rot_pt(q[0], q[1], cx, cy, ang)) + list(q[2:]) for q in orig["pts"]]
    a["x"], a["y"], a["x2"], a["y2"] = rep.pts_bbox(a["pts"])
    return ang % 360.0


def ann_hit(shape, a, ix, iy, m):
    t = a["type"]
    r = rep.ann_rot(a)
    if r:                                            # gedreht: Punkt in die ungedrehte Lage der Box bringen
        ix, iy = rep.rot_pt(ix, iy, *rep.rot_center(shape, a), -r)
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
    b = rep.ann_frame(shape, a)
    return b[0] - m <= ix <= b[2] + m and b[1] - m <= iy <= b[3] + m


def apply_handle(shape, a, name, px, py):
    """Anfasser name auf den Punkt (px, py) ziehen. Gedrehte Markierungen: in der ungedrehten Lage aendern, danach
    so verschieben, dass der gegenueberliegende Anfasser (bzw. die Ecke oben links) an seinem Platz bleibt."""
    r = rep.ann_rot(a)
    if not r:
        _apply_handle(shape, a, name, px, py)
        return
    c = rep.rot_center(shape, a)
    lx, ly = rep.rot_pt(px, py, *c, -r)
    loc = {n: (hx, hy) for n, hx, hy in _local_handles(shape, a)}
    fx, fy = loc.get(_OPPOSITE.get(name), (a["x"], a["y"]))   # fester Punkt
    wx, wy = rep.rot_pt(fx, fy, *c, r)
    _apply_handle(shape, a, name, lx, ly)
    nx, ny = rep.rot_pt(fx, fy, *rep.rot_center(shape, a), r)
    for kx, ky in (("x", "y"), ("x2", "y2")):
        a[kx] += wx - nx
        a[ky] += wy - ny


def _apply_handle(shape, a, name, px, py):
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
    if t == "pen" and a.get("pts") and name in CORNERS + SIDES:
        x0, y0, x1, y1 = rep.pts_bbox(a["pts"])
        fx, fy = (x1 if "l" in name else x0), (y1 if "t" in name else y0)   # fester Punkt: gegenueberliegende Ecke
        ox_, oy_ = (x0 if "l" in name else x1), (y0 if "t" in name else y1)
        sx = (px - fx) / (ox_ - fx) if abs(ox_ - fx) > 1e-6 and name not in ("t", "b") else 1.0
        sy = (py - fy) / (oy_ - fy) if abs(oy_ - fy) > 1e-6 and name not in ("l", "r") else 1.0
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
    elif t in rep.RECT_TYPES and name in CORNERS + SIDES:
        x0, y0, x1, y1 = min(a["x"], a["x2"]), min(a["y"], a["y2"]), max(a["x"], a["x2"]), max(a["y"], a["y2"])
        if name not in ("t", "b"):                   # Seitenmitte oben/unten: Breite bleibt
            if "l" in name:
                x0 = px
            else:
                x1 = px
        if name not in ("l", "r"):                   # Seitenmitte links/rechts: Hoehe bleibt
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
            b = rep.ann_frame(shape, a)
            w0 = max(1.0, b[2] - b[0])
            a["size"] = float(np.clip(a["size"] * max(8.0, px - a["x"]) / w0, 0.5, 20))
