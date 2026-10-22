"""Zeichenflaeche: Anzeige, Zoom, Messen, Anmerkungen."""
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
    if t == "measure":
        return [(f"m{i}", q[0], q[1]) for i, q in enumerate(a["pts"])]
    if t == "arrow":
        return [("p1", a["x"], a["y"]), ("p2", a["x2"], a["y2"])]
    if t in rep.RECT_TYPES:
        x0, y0, x1, y1 = min(a["x"], a["x2"]), min(a["y"], a["y2"]), max(a["x"], a["x2"]), max(a["y"], a["y2"])
        return [("tl", x0, y0), ("tr", x1, y0), ("bl", x0, y1), ("br", x1, y1)]
    b = rep.ann_bounds(shape, a)
    if t == "number":
        return [("size", b[2], a["y"])]
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
    if t == "arrow":
        return _dist_seg(ix, iy, a["x"], a["y"], a["x2"], a["y2"]) <= m + rep.ann_line_w(shape, a["size"])
    if t in rep.RECT_TYPES:
        x0, y0, x1, y1 = min(a["x"], a["x2"]), min(a["y"], a["y2"]), max(a["x"], a["x2"]), max(a["y"], a["y2"])
        if t == "cloud":                          # Wolke ragt ueber das Rechteck hinaus
            m += rep.cloud_radius(shape, a["size"])
        inside = x0 - m <= ix <= x1 + m and y0 - m <= iy <= y1 + m
        if t == "highlight":                      # Textmarker: ganze Flaeche anklickbar
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


# ----------------------------------------------------------------- Zeichenflaeche
class Canvas(QWidget):
    cursor = Signal(int, int, float)
    zoneDrawn = Signal(int, int, int, int)
    cropDrawn = Signal(int, int, int, int)
    regionClicked = Signal(int)
    annCreated = Signal(dict)
    placeRequested = Signal(str, float, float)
    annSelected = Signal(int)
    annChanged = Signal()
    annEdit = Signal(int)
    annContext = Signal(int, object)
    contextRequested = Signal(object)
    escapePressed = Signal()
    regionDrawn = Signal(int, int, int, int)
    blinkClicked = Signal()
    viewChanged = Signal(float)              # Zoom geaendert (Massstab Bild -> Bildschirm)
    zoomBoxDone = Signal()                   # einmaliger Zoom-Rahmen fertig -> voriges Werkzeug
    filesDropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.res = None
        self.pa = self.pb = self.pd = None
        self.regs = []
        self.anns = []
        self.visible_types = None
        self.selected = None
        self.ann_selected = None
        self.zones = []
        self.mm_px = 25.4 / 200
        self.mode = "D"
        self.blink_b = False
        self.split = 0.5
        self.tool = "hand"
        self.show_overlays = True
        self.show_regs = True
        self.po = None
        self.snap = True
        self.snap_hint = None
        self.ann_color = "#e11d48"
        self.ann_size = 2.0
        self.scale = 1.0
        self.ox = self.oy = 0.0
        self.measure = []
        self.measure_kind = "dist"
        self.loupe = False
        self.loupe_zoom = 3.0
        self._mouse = None
        self.hover = None
        self._drag = None
        self._rubber = None
        self._ann_prev = None
        self._moved = 0
        self.rot = 0                         # Ansichtsdrehung in 90-Grad-Schritten (nur Anzeige)
        self.message = "Zeichnung A (alt) und B (neu) links \u00f6ffnen\noder hierher ziehen"
        self.show_overview = True            # Uebersichtsfenster unten rechts (nur wenn hineingezoomt)
        self.reg_clouds = False              # nummerierte Aenderungen als Revisionswolke statt Rahmen
        self.pc = (None, None)
        self.show_color = True               # Alt/Neu in Farbe zeigen, wenn die Datei farbig ist
        self.invert = False                  # helle Linien auf dunklem Grund (nur Anzeige)
        self.show_legend = True
        self.preview = None                  # (QImage, (h, w)) waehrend der ersten Berechnung
        self.labels = ("A (alt)", "B (neu)")
        self._side = "A"                     # Nebeneinander: Haelfte unter der Maus
        self._pinch = None
        self.setAcceptDrops(True)
        self.grabGesture(Qt.GestureType.PinchGesture)

    # --- Drehung der Ansicht: width()/height() liefern in Python die Groesse der UNGEDREHTEN Ansicht
    # Nebeneinander (Ansicht "Y"): zwei gleich grosse Haelften mit gleicher Ansicht; ohne Drehung
    def width(self):
        if self.mode == "Y":
            return QWidget.width(self) // 2
        return QWidget.height(self) if self.rot % 2 else QWidget.width(self)

    def height(self):
        if self.mode == "Y":
            return QWidget.height(self)
        return QWidget.width(self) if self.rot % 2 else QWidget.height(self)

    def _xform(self):
        W, H = QWidget.width(self), QWidget.height(self)
        if self.mode == "Y":
            return QTransform()
        return [QTransform(), QTransform(0, 1, -1, 0, W, 0), QTransform(-1, 0, 0, -1, W, H),
                QTransform(0, -1, 1, 0, 0, H)][self.rot % 4]

    def _vp(self, pos):
        """Widget-Position -> Position in der ungedrehten Ansicht (bei Nebeneinander: in der Haelfte).
        Waehrend eines Ziehens gilt die Haelfte, in der es begonnen hat - so kann man ueber die Mitte weiterziehen."""
        if self.mode == "Y":
            half = QWidget.width(self) // 2
            if self._drag is None:
                self._side = "B" if pos.x() >= half else "A"
            return QPointF(pos.x() - half if self._side == "B" else pos.x(), pos.y())
        return self._xform().inverted()[0].map(pos)

    def _emit_view(self):
        self.viewChanged.emit(self.scale)

    def resizeEvent(self, e):
        # Zeigte die Ansicht die ganze Zeichnung, bleibt das nach Groessenaenderung so (Fenster, Leisten)
        if self.res is not None and (getattr(self, "_fitted", True) or e.oldSize().width() <= 0):
            self.fit()

    def fit_scale(self):
        h, w = self.shape
        return min(self.width() / w, self.height() / h) * 0.97

    def zoom_step(self, factor, center=None):
        """Zoomt um factor; center = Widget-Position (Standard: Mitte)."""
        if self.res is None:
            return
        if center is None:
            center = QPointF(self.width() / 2, self.height() / 2)
        ix, iy = self.to_img(center)
        new = float(np.clip(self.scale * factor, self.fit_scale() * 0.3, 40.0))
        self.scale = new
        self.ox = ix - center.x() / new
        self.oy = iy - center.y() / new
        self._fitted = False
        self.update()
        self._emit_view()

    def pan(self, dx, dy):
        """Verschiebt die Ansicht um dx, dy Bildschirmpixel."""
        self.ox -= dx / self.scale
        self.oy -= dy / self.scale
        self._fitted = False
        self.update()

    def set_preview(self, img_gray, full_shape):
        """Vorschau (verkleinerte Zeichnung A) waehrend der ersten Berechnung."""
        if img_gray is None:
            self.preview = None
        else:
            g = np.ascontiguousarray(img_gray)
            qi = QImage(g.data, g.shape[1], g.shape[0], g.strides[0], QImage.Format.Format_Grayscale8).copy()
            self.preview = (qi, full_shape)
        self.update()

    def reset_rotation(self):
        """Neue Zeichnung: Anzeige wieder aufrecht (keine mitgeschleppte Drehung)."""
        if self.rot:
            self.rot = 0
            self.fit()

    def rotate_view(self):
        if self.res is None:
            self.rot = (self.rot + 1) % 4
            self.update()
            return
        h, w = self.shape
        fitted = self.scale <= min(self.width() / w, self.height() / h) * 0.97 * 1.02
        cx, cy = self.to_img(QPointF(self.width() / 2, self.height() / 2))
        self.rot = (self.rot + 1) % 4
        if fitted:
            self.fit()
        else:
            self.zoom_to(self.scale, cx, cy)

    # --- Daten
    def set_data(self, res, pa, pb, pd, regs, keep_view, po=None, pc=None):
        same = self.res is not None and self.res.a.shape == res.a.shape
        self.res, self.pa, self.pb, self.pd, self.regs = res, pa, pb, pd, regs
        self.po = po
        self.pc = pc or (None, None)              # Farbfassungen fuer Alt/Neu (oder None)
        self.measure = []
        if not (keep_view and same):
            self.fit()
        self.update()

    def clear(self):
        """Keine Zeichnung mehr anzeigen (Dokument geschlossen)."""
        self.res = self.pa = self.pb = self.pd = self.po = None
        self.pc = (None, None)
        self.regs, self.measure, self.zones = [], [], []
        self.selected = self.ann_selected = None
        self.preview = None
        self.mode = "D" if self.mode == "Y" else self.mode
        self.update()

    @property
    def shape(self):
        return self.res.a.shape if self.res is not None else (1, 1)

    # --- Ansicht
    def fit(self):
        if self.res is None:
            return
        h, w = self.shape
        self.scale = min(self.width() / w, self.height() / h) * 0.97
        self.ox = -(self.width() / self.scale - w) / 2
        self.oy = -(self.height() / self.scale - h) / 2
        self._fitted = True
        self.update()
        self._emit_view()

    def zoom_to(self, scale, cx, cy):
        self.scale = scale
        self.ox = cx - self.width() / 2 / scale
        self.oy = cy - self.height() / 2 / scale
        self._fitted = False
        self.update()
        self._emit_view()

    def center_box(self, x0, y0, x1, y1):
        h, w = self.shape
        s = min(self.width() / (x1 - x0 + 300), self.height() / (y1 - y0 + 300), 6.0)
        s = max(s, min(self.width() / w, self.height() / h))
        self.zoom_to(s, (x0 + x1) / 2, (y0 + y1) / 2)

    def center_on(self, r):
        self.center_box(r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"])

    def to_img(self, p):
        return p.x() / self.scale + self.ox, p.y() / self.scale + self.oy

    def to_wid(self, x, y):
        return (x - self.ox) * self.scale, (y - self.oy) * self.scale


    # --- Einrasten (Messen)
    def snap_point(self, ix, iy):
        """Rastet auf gerade Linien in der Naehe ein. Gibt (x, y, Art) zurueck; Art None = nichts gefunden.
        Art: 'h' waagerechte Linie, 'v' senkrechte Linie, 'p' Punkt/Ecke."""
        if not self.snap or self.res is None:
            return ix, iy, None
        if QGuiApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            return ix, iy, None
        src = self.res.b if self.mode in ("B", "N") else self.res.a
        h, w = src.shape
        r = int(max(3, min(60, 14 / self.scale)))
        xi, yi = int(round(ix)), int(round(iy))
        x0, y0, x1, y1 = max(0, xi - r), max(0, yi - r), min(w, xi + r + 1), min(h, yi + r + 1)
        if x1 <= x0 or y1 <= y0:
            return ix, iy, None
        ys, xs = np.nonzero(src[y0:y1, x0:x1] > 0)
        if len(xs) == 0:
            return ix, iy, None
        k = int(np.argmin((xs + x0 - ix) ** 2 + (ys + y0 - iy) ** 2))
        px, py = int(xs[k] + x0), int(ys[k] + y0)
        L = 500
        a0, b0 = max(0, px - L), max(0, py - L)
        row = src[py, a0:min(w, px + L + 1)] > 0
        col = src[b0:min(h, py + L + 1), px] > 0
        hx0, hx1 = _run(row, px - a0)
        vy0, vy1 = _run(col, py - b0)
        hx0, hx1, vy0, vy1 = hx0 + a0, hx1 + a0, vy0 + b0, vy1 + b0
        hl, vl = hx1 - hx0 + 1, vy1 - vy0 + 1
        cx, cy = (hx0 + hx1) / 2, (vy0 + vy1) / 2
        if hl >= max(20, 3 * vl):
            x = min(max(ix, hx0), hx1)
            for ex in (hx0, hx1):
                if abs(ix - ex) <= r:
                    x = ex
            return x, cy, "h"
        if vl >= max(20, 3 * hl):
            y = min(max(iy, vy0), vy1)
            for ey in (vy0, vy1):
                if abs(iy - ey) <= r:
                    y = ey
            return cx, y, "v"
        return cx, cy, "p"

    @staticmethod
    def _pair(p1, p2):
        """Zwei parallele Linien: kuerzester Abstand = senkrecht zwischen den Linien."""
        if p1[2] == "h" and p2[2] == "h":
            return (p1[0], p2[1], "h"), True
        if p1[2] == "v" and p2[2] == "v":
            return (p2[0], p1[1], "v"), True
        return p2, False

    def measure_px(self):
        """Laenge (Pixel) der gewaehlten bzw. zuletzt gesetzten Strecke."""
        cand = []
        if self.ann_selected is not None and 0 <= self.ann_selected < len(self.anns):
            cand.append(self.anns[self.ann_selected])
        cand += list(reversed(self.anns))
        for a in cand:
            if a["type"] == "measure" and a.get("kind") == "dist":
                return math.hypot(a["x2"] - a["x"], a["y2"] - a["y"])
        return None

    def finish_measure(self):
        k = self.measure_kind
        pts = self.measure
        need = {"dist": 2, "poly": 2, "angle": 3, "radius": 3, "area": 3}[k]
        if len(pts) >= need:
            P = [[float(q[0]), float(q[1])] for q in pts]
            if k == "dist":
                p2, _ = self._pair(pts[0], pts[1])
                P[1] = [float(p2[0]), float(p2[1])]
            self.annCreated.emit(dict(type="measure", kind=k, pts=P, x=P[0][0], y=P[0][1], x2=P[-1][0],
                                      y2=P[-1][1], text="", nr=0, color=self.ann_color, size=self.ann_size))
        self.measure = []
        self.hover = None
        self.update()

    # --- Darstellung
    def _layer(self, mode, L, y0, y1, x0, x1):
        sl = (slice(y0, y1), slice(x0, x1))
        if mode in ("A", "B"):
            pc = self.pc[0 if mode == "A" else 1] if self.show_color else None
            if pc is not None and L < len(pc):
                return pc[L][sl]
            return cv2.cvtColor(255 - (self.pa if mode == "A" else self.pb)[L][sl], cv2.COLOR_GRAY2BGR)
        if mode == "O":
            a, b = self.pa[L][sl] > 0, self.pb[L][sl] > 0
            return dc.render(a & ~b, b & ~a, a & b, None)
        if mode == "N":
            b, ob = self.pb[L][sl] > 0, self.po[1][L][sl] > 0
            return dc.render(np.zeros_like(ob), ob, b & ~ob, None)
        if mode == "R":
            a, oa = self.pa[L][sl] > 0, self.po[0][L][sl] > 0
            return dc.render(oa, np.zeros_like(oa), a & ~oa, None)
        if L == 0:
            return render_crop(self.res, y0, y1, x0, x1)
        return self.pd[L][sl]

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(THEME["canvas"]))
        if self.res is None:
            if self.preview is not None:
                self._paint_preview(p)
            else:
                p.setPen(QColor(THEME["muted"]))
                p.setFont(QFont(UI_FONT, 13))
                p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            return
        h, w = self.shape
        if self.mode == "Y":
            self._paint_side_by_side(p, w, h)
        else:
            p.save()
            p.setTransform(self._xform())
            self._paint_image(p, self.width(), self.height())
            self._paint_overlays(p, w, h)
            p.restore()
            self._paint_legend(p)
        if self.show_overview:
            self._paint_overview(p)
        if self.tool == "zoom" and self._mouse is not None:      # blaues Fadenkreuz zum Ausrichten
            pen = QPen(QColor(30, 100, 255, 200), 1)
            p.setPen(pen)
            mx, my = self._mouse.x(), self._mouse.y()
            p.drawLine(QPointF(0, my), QPointF(QWidget.width(self), my))
            p.drawLine(QPointF(mx, 0), QPointF(mx, QWidget.height(self)))
        if self.loupe and self._mouse is not None and self.tool != "zone":
            self._paint_loupe(p)
        p.end()

    def _paint_side_by_side(self, p, w, h):
        half = QWidget.width(self) // 2
        H = QWidget.height(self)
        for i, m in enumerate(("A", "B")):
            p.save()
            p.setClipRect(QRectF(i * half, 0, half, H))
            p.translate(i * half, 0)
            self.mode = m
            try:
                self._paint_image(p, half, H)
                self._paint_overlays(p, w, h)
            finally:
                self.mode = "Y"
            p.restore()
            f = QFont(UI_FONT, 10)
            f.setBold(True)
            p.setFont(f)
            txt = self.labels[i]
            r = QRectF(i * half + 10, 10, p.fontMetrics().horizontalAdvance(txt) + 20, 26)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#e5173f") if i == 0 else QColor("#1f3fff"))
            p.drawRoundedRect(r, 6, 6)
            p.setPen(QColor("white"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, txt)
        p.setPen(QPen(QColor(THEME["frame"]), 2))
        p.drawLine(QPointF(half, 0), QPointF(half, H))

    def _paint_preview(self, p):
        qi, (h, w) = self.preview
        W, H = QWidget.width(self), QWidget.height(self)
        s = min(W / w, H / h) * 0.97
        r = QRectF((W - w * s) / 2, (H - h * s) / 2, w * s, h * s)
        p.setOpacity(0.55)
        p.fillRect(r, QColor("white"))
        p.drawImage(r, qi)
        p.setOpacity(1.0)
        p.setPen(QColor(THEME["text"]))
        f = QFont(UI_FONT, 13)
        f.setBold(True)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Vergleich l\u00e4uft \u2026")

    def overview_rect(self):
        """Rechteck des Uebersichtsfensters in Widget-Koordinaten oder None (nicht sichtbar)."""
        if self.res is None or not self.show_overview or self.mode == "Y":
            return None
        if self.scale <= self.fit_scale() * 1.15:            # ganze Zeichnung sichtbar: keine Uebersicht noetig
            return None
        h, w = self.shape
        W, H = QWidget.width(self), QWidget.height(self)
        if self.rot % 2:
            w, h = h, w
        k = min(220 / w, 160 / h)
        ow, oh = w * k, h * k
        return QRectF(W - ow - 14, H - oh - 14, ow, oh)

    def _paint_overview(self, p):
        r = self.overview_rect()
        if r is None:
            return
        top = self.pa[-1]
        if self.mode in ("A", "B", "K", "S") or self.pd[-1] is None:
            pc = self.pc[1 if self.mode == "B" else 0] if self.show_color else None
            img = pc[-1] if pc is not None else cv2.cvtColor(255 - top, cv2.COLOR_GRAY2BGR)
        else:
            img = self.pd[-1]
        img = np.ascontiguousarray(np.rot90(img, -self.rot % 4) if self.rot else img)
        qi = QImage(img.data, img.shape[1], img.shape[0], img.strides[0], QImage.Format.Format_BGR888)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(QColor(THEME["border2"]), 1))
        p.setBrush(QColor(THEME["surface"]))
        p.drawRoundedRect(r.adjusted(-5, -5, 5, 5), 8, 8)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.drawImage(r, qi)
        # sichtbarer Bereich: Ecken der Ansicht -> Bildkoordinaten -> Uebersicht
        h, w = self.shape
        xf = self._xform()
        corners = [self.to_img(QPointF(x, y)) for x, y in ((0, 0), (self.width(), self.height()))]
        x0, x1 = sorted((corners[0][0], corners[1][0]))
        y0, y1 = sorted((corners[0][1], corners[1][1]))
        poly = [QPointF((x - self.ox) * self.scale, (y - self.oy) * self.scale) for x, y in
                ((x0, y0), (x1, y1))]
        a, b = xf.map(poly[0]), xf.map(poly[1])
        W, H = QWidget.width(self), QWidget.height(self)
        vx0, vx1 = sorted((a.x(), b.x()))
        vy0, vy1 = sorted((a.y(), b.y()))
        # Widget -> Uebersicht: gesamte (ggf. gedrehte) Zeichnung liegt in r
        full = [xf.map(QPointF((x - self.ox) * self.scale, (y - self.oy) * self.scale)) for x, y in ((0, 0), (w, h))]
        fx0, fx1 = sorted((full[0].x(), full[1].x()))
        fy0, fy1 = sorted((full[0].y(), full[1].y()))
        kx, ky = r.width() / max(1e-6, fx1 - fx0), r.height() / max(1e-6, fy1 - fy0)
        vr = QRectF(r.left() + (max(vx0, fx0) - fx0) * kx, r.top() + (max(vy0, fy0) - fy0) * ky,
                    (min(vx1, fx1) - max(vx0, fx0)) * kx, (min(vy1, fy1) - max(vy0, fy0)) * ky)
        p.setClipRect(r)
        c = QColor(THEME["accent"])
        c.setAlpha(45)
        p.setBrush(c)
        p.setPen(QPen(QColor(THEME["accent"]), 2))
        p.drawRect(vr)
        p.restore()

    def _overview_jump(self, pos):
        """Klick/Ziehen im Uebersichtsfenster: Ansicht auf diese Stelle zentrieren."""
        r = self.overview_rect()
        if r is None:
            return False
        h, w = self.shape
        fx, fy = (pos.x() - r.left()) / r.width(), (pos.y() - r.top()) / r.height()
        # gedrehte Uebersicht zurueck auf Bildkoordinaten
        u, v = [(fx, fy), (fy, 1 - fx), (1 - fx, 1 - fy), (1 - fy, fx)][self.rot % 4]
        self.zoom_to(self.scale, float(np.clip(u, 0, 1)) * w, float(np.clip(v, 0, 1)) * h)
        return True

    def _paint_loupe(self, p):
        D, Z = 320, self.loupe_zoom
        cx, cy = self._mouse.x(), self._mouse.y()
        ix, iy = self.to_img(self._vp(self._mouse))
        keep = (self.scale, self.ox, self.oy, self.show_regs, self.mode, self.rot)
        if self.mode == "Y":                      # Lupe zeigt die Haelfte unter der Maus
            self.mode, self.rot = self._side, 0
        self.scale = keep[0] * Z
        self.ox, self.oy = ix - D / 2 / self.scale, iy - D / 2 / self.scale
        pm = QPixmap(D, D)
        pm.fill(QColor(THEME["canvas"]))
        q = QPainter(pm)
        q.translate(D / 2, D / 2)                 # Lupe zeigt die Ansicht ebenfalls gedreht
        q.rotate(90 * (self.rot % 4))
        q.translate(-D / 2, -D / 2)
        h, w = self.shape
        self._paint_image(q, D, D)
        self._paint_overlays(q, w, h)
        q.end()
        self.scale, self.ox, self.oy, self.show_regs, self.mode, self.rot = keep
        path = QPainterPath()
        path.addEllipse(QPointF(cx, cy), D / 2, D / 2)
        p.save()
        p.setClipPath(path)
        p.drawPixmap(int(cx - D / 2), int(cy - D / 2), pm)
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("white"), 5))
        p.drawEllipse(QPointF(cx, cy), D / 2, D / 2)
        p.setPen(QPen(QColor(ACCENT), 2))
        p.drawEllipse(QPointF(cx, cy), D / 2, D / 2)
        p.setPen(QPen(QColor(ACCENT), 1))
        p.drawLine(QPointF(cx - 7, cy), QPointF(cx + 7, cy))
        p.drawLine(QPointF(cx, cy - 7), QPointF(cx, cy + 7))
        p.drawText(int(cx - D / 2 + 14), int(cy + D / 2 - 10), f"{Z:g}\u00d7")

    def _paint_image(self, p, W, H):
        """Zeichnet den sichtbaren Bildausschnitt in Geraete-Pixeln (scharf auf Retina/HiDPI)."""
        h, w = self.shape
        s = self.scale
        dpr = max(1.0, p.device().devicePixelRatioF())
        S = s * dpr                                   # Bildpixel -> Geraetepixel
        L = 0
        while L + 1 < len(self.pa) and S * 2 ** (L + 1) <= 1.0:
            L += 1
        f = 2 ** L
        sl_ = S * f
        x0, y0 = max(0.0, self.ox), max(0.0, self.oy)
        x1 = min(float(w), self.ox + W / s)
        y1 = min(float(h), self.oy + H / s)
        if x1 > x0 and y1 > y0:
            lx0, ly0 = int(x0 // f), int(y0 // f)
            lx1, ly1 = int(-(-x1 // f)), int(-(-y1 // f))
            lh, lw = self.pa[L].shape
            lx1, ly1 = min(lx1, lw), min(ly1, lh)
            dw, dh = max(1, round((lx1 - lx0) * sl_)), max(1, round((ly1 - ly0) * sl_))
            px, py = (lx0 * f - self.ox) * s, (ly0 * f - self.oy) * s
            interp = cv2.INTER_NEAREST if sl_ >= 1 else cv2.INTER_AREA
            m = self.mode
            if m == "K":
                m = "B" if self.blink_b else "A"
            if m == "S":
                ia = self._layer("A", L, ly0, ly1, lx0, lx1)
                ib = self._layer("B", L, ly0, ly1, lx0, lx1)
                img = cv2.resize(ia, (dw, dh), interpolation=interp)
                imb = cv2.resize(ib, (dw, dh), interpolation=interp)
                cut = int(np.clip((self.split * W - px) * dpr, 0, dw))
                img[:, cut:] = imb[:, cut:]
                if self.invert:
                    img = invert_view(img, "A")
            else:
                img = cv2.resize(self._layer(m, L, ly0, ly1, lx0, lx1), (dw, dh), interpolation=interp)
                if self.invert:
                    img = invert_view(img, m)
            img = np.ascontiguousarray(img)
            qi = QImage(img.data, dw, dh, img.strides[0], QImage.Format.Format_BGR888)
            qi.setDevicePixelRatio(dpr)
            p.drawImage(QPointF(px, py), qi)

    def _paint_legend(self, p):
        if not self.show_legend:
            return
        items = {"D": (("#e5173f", "nur in A (alt)"), ("#1f3fff", "nur in B (neu)"), ("#969696", "gleich"),
                       ("#00aa00", "verschoben")),
                 "O": (("#e5173f", "nur in A (alt)"), ("#1f3fff", "nur in B (neu)"), ("#969696", "gleich")),
                 "S": (), "A": (), "B": (), "K": (),
                 "N": (("#1f3fff", "neu / ge\u00e4ndert"), ("#969696", "unver\u00e4ndert")),
                 "R": (("#e5173f", "entfernt / ge\u00e4ndert"), ("#969696", "unver\u00e4ndert"))}[self.mode]
        if self.mode in ("A", "B", "K"):            # gleiche Legende wie bei der \u00dcberlagerung: welche Version ist zu sehen
            which = ("B" if self.blink_b else "A") if self.mode == "K" else self.mode
            items = (("#e5173f", "Zeichnung A (alt)"),) if which == "A" else (("#1f3fff", "Zeichnung B (neu)"),)
        if not items:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        f = QFont(UI_FONT, 8)
        p.setFont(f)
        fm = p.fontMetrics()
        wd = max(fm.horizontalAdvance(t) for _, t in items) + 34
        hh = 8 + 17 * len(items)
        x0, y0 = 10, QWidget.height(self) - hh - 10
        p.setPen(QPen(QColor(THEME["border2"]), 1))
        p.setBrush(QColor(*THEME["legend_bg"]))
        p.drawRoundedRect(QRectF(x0, y0, wd, hh), 6, 6)
        for i, (c, t) in enumerate(items):
            y = y0 + 6 + 17 * i
            p.setPen(QPen(QColor("#888888"), 1))
            p.setBrush(QColor(c))
            p.drawRect(QRectF(x0 + 8, y + 2, 11, 11))
            p.setPen(QColor(THEME["text2"]))
            p.drawText(QRectF(x0 + 26, y, wd - 26, 15), Qt.AlignmentFlag.AlignVCenter, t)

    def _paint_ann(self, p, a, selected=False):
        s = self.scale
        shape = self.shape
        col = QColor(a["color"])
        th = rep.ann_text_h(shape, a["size"]) * s
        lw = max(1.5, rep.ann_line_w(shape, a["size"]) * s)
        x, y = self.to_wid(a["x"], a["y"])
        t = a["type"]
        if t == "number":
            r = th * 0.95
            p.setPen(QPen(QColor("white"), max(1.0, lw * 0.4)))
            p.setBrush(col)
            p.drawEllipse(QPointF(x, y), r, r)
            f = QFont(UI_FONT)
            f.setBold(True)
            f.setPixelSize(max(5, int(rep.stamp_font_h(th, a["nr"]))))
            p.setFont(f)
            p.setPen(QColor("white"))
            p.drawText(QRectF(x - r, y - r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, str(a["nr"]))
        elif t == "text":
            if th >= 3:
                f = QFont(UI_FONT)
                f.setPixelSize(max(4, int(th)))
                p.setFont(f)
                box = QRectF(x, y, 20000, 20000)
                fl = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                p.setPen(QColor("white"))
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    p.drawText(box.translated(dx, dy), fl, a["text"])
                p.setPen(col)
                p.drawText(box, fl, a["text"])
        elif t == "approval":
            b = rep.ann_bounds(shape, a)
            a0, b0 = self.to_wid(b[0], b[1])
            a1, b1 = self.to_wid(b[2], b[3])
            p.setPen(QPen(col, max(2.0, lw * 1.3)))
            p.setBrush(QColor("white"))
            p.drawRect(QRectF(a0, b0, a1 - a0, b1 - b0))
            if th >= 3:
                f = QFont(UI_FONT)
                f.setPixelSize(max(4, int(th)))
                p.setFont(f)
                p.setPen(col)
                p.drawText(QRectF(a0 + 0.5 * th, b0 + 0.5 * th, 20000, 20000),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, a["text"])
        elif t == "measure":
            p.setPen(QPen(col, lw))
            for gk, gd in rep.measure_geometry(a):
                if gk == "circle":
                    cx, cy = self.to_wid(gd[0], gd[1])
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawEllipse(QPointF(cx, cy), gd[2] * s, gd[2] * s)
                    p.drawLine(QPointF(cx - 5, cy), QPointF(cx + 5, cy))
                    p.drawLine(QPointF(cx, cy - 5), QPointF(cx, cy + 5))
                else:
                    pg = QPolygonF([QPointF(*self.to_wid(q[0], q[1])) for q in gd])
                    if gk == "poly":
                        c2 = QColor(col)
                        c2.setAlpha(40)
                        p.setBrush(c2)
                        p.drawPolygon(pg)
                    else:
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawPolyline(pg)
            p.setBrush(QColor("white"))
            for q in a["pts"]:
                p.drawEllipse(QPointF(*self.to_wid(q[0], q[1])), 3, 3)
            txt = rep.measure_text(a, self.mm_px)
            if txt:
                mx = sum(q[0] for q in a["pts"]) / len(a["pts"])
                my = sum(q[1] for q in a["pts"]) / len(a["pts"])
                X, Y = self.to_wid(mx, my)
                p.setFont(QFont(UI_FONT, 9))
                r = QRectF(X + 8, Y - 22, p.fontMetrics().horizontalAdvance(txt) + 14, 20)
                p.fillRect(r, QColor(255, 255, 255, 235))
                p.setPen(col)
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, txt)
        elif t == "rect":
            x2, y2 = self.to_wid(a["x2"], a["y2"])
            p.setPen(QPen(col, lw))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(QPointF(x, y), QPointF(x2, y2)).normalized())
        elif t == "cloud":
            pts = rep.cloud_points(a["x"], a["y"], a["x2"], a["y2"], rep.cloud_radius(shape, a["size"]))
            if pts:
                pen = QPen(col, lw)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPolygon(QPolygonF([QPointF(*self.to_wid(qx, qy)) for qx, qy in pts]))
        elif t == "highlight":
            x2, y2 = self.to_wid(a["x2"], a["y2"])
            c2 = QColor(col)
            c2.setAlpha(95)
            p.fillRect(QRectF(QPointF(x, y), QPointF(x2, y2)).normalized(), c2)
        elif t == "arrow":
            x2, y2 = self.to_wid(a["x2"], a["y2"])
            ang = math.atan2(y2 - y, x2 - x)
            head = max(5 * lw, 0.8 * th)
            bx, by = x2 - head * 0.8 * math.cos(ang), y2 - head * 0.8 * math.sin(ang)
            p.setPen(QPen(col, lw))
            p.drawLine(QPointF(x, y), QPointF(bx, by))
            p.setBrush(col)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawPolygon(QPolygonF([QPointF(x2, y2),
                                     QPointF(x2 - head * math.cos(ang - 0.4), y2 - head * math.sin(ang - 0.4)),
                                     QPointF(x2 - head * math.cos(ang + 0.4), y2 - head * math.sin(ang + 0.4))]))
        if selected:
            b = rep.ann_bounds(shape, a)
            a0, b0 = self.to_wid(b[0], b[1])
            a1, b1 = self.to_wid(b[2], b[3])
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(ACCENT), 1.2, Qt.PenStyle.DashLine))
            if t not in ("arrow", "measure"):
                p.drawRect(QRectF(a0 - 3, b0 - 3, a1 - a0 + 6, b1 - b0 + 6))
            p.setPen(QPen(QColor(ACCENT), 1.6))
            p.setBrush(QColor("white"))
            for _, hx, hy in ann_handles(shape, a):
                X, Y = self.to_wid(hx, hy)
                p.drawRect(QRectF(X - 4.5, Y - 4.5, 9, 9))

    def _paint_overlays(self, p, w, h):
        s = self.scale
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        tl = self.to_wid(0, 0)
        p.setPen(QPen(QColor(THEME["frame"]), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(tl[0], tl[1], w * s, h * s))
        if self.mode == "S":
            x = self.split * self.width()
            p.setPen(QPen(QColor(ACCENT), 2))
            p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
            p.setBrush(QColor(ACCENT))
            p.drawEllipse(QPointF(x, self.height() / 2), 9, 9)
            p.setPen(QColor("white"))
            p.drawText(QRectF(x - 9, self.height() / 2 - 9, 18, 18), Qt.AlignmentFlag.AlignCenter, "\u2194")
            p.setPen(QColor(THEME["text2"]))
            p.drawText(10, 20, "A")
            p.drawText(self.width() - 20, 20, "B")
        if not self.show_overlays:
            return
        for x, y, zw, zh in self.zones:
            a = self.to_wid(x, y)
            r = QRectF(a[0], a[1], zw * s, zh * s)
            p.fillRect(r, QColor(250, 204, 21, 70))
            p.setPen(QPen(QColor("#ca8a04"), 1.5, Qt.PenStyle.DashLine))
            p.drawRect(r)
        if self.regs and self.show_regs:
            font = QFont(UI_FONT, 8)
            font.setBold(True)
            p.setFont(font)
            for r in self.regs:
                if self.visible_types is not None and r["typ"] not in self.visible_types:
                    continue
                a = self.to_wid(r["x"] - 10, r["y"] - 10)
                rw, rh = (r["w"] + 20) * s, (r["h"] + 20) * s
                if a[0] > self.width() or a[1] > self.height() or a[0] + rw < 0 or a[1] + rh < 0:
                    continue
                col = QColor(rep.STATUS_COLORS.get(rep.reg_status(r), "#f97316"))
                sel = self.selected == r["nr"]
                rect = QRectF(a[0], a[1], max(rw, 4), max(rh, 4))
                if sel:
                    p.fillRect(rect, QColor(37, 99, 235, 40))
                p.setPen(QPen(QColor(ACCENT) if sel else col, 3 if sel else 1.6))
                p.setBrush(Qt.BrushStyle.NoBrush)
                if self.reg_clouds and rect.width() > 12 and rect.height() > 12:
                    pts = rep.cloud_points(rect.left(), rect.top(), rect.right(), rect.bottom(),
                                           float(np.clip(min(rect.width(), rect.height()) / 6, 4, 16)))
                    p.drawPolygon(QPolygonF([QPointF(qx, qy) for qx, qy in pts]))
                else:
                    p.drawRect(rect)
                label = str(r["nr"])
                tw = p.fontMetrics().horizontalAdvance(label) + 8
                lb = QRectF(rect.left(), rect.top() - 16, tw, 16)
                p.fillRect(lb, QColor(ACCENT) if sel else col)
                p.setPen(QColor("white"))
                p.drawText(lb, Qt.AlignmentFlag.AlignCenter, label)
        for i, a in enumerate(self.anns):
            self._paint_ann(p, a, i == self.ann_selected)
        if self._ann_prev:
            (ax, ay), (bx, by) = self._ann_prev
            self._paint_ann(p, dict(type=self.tool, x=ax, y=ay, x2=bx, y2=by, text="", nr=0,
                                    color=self.ann_color, size=self.ann_size))
        if self.measure or (self.tool == "measure" and self.snap_hint):
            self._paint_measure(p)
        if self._rubber:
            (ax, ay), (bx, by) = self._rubber
            a, b = self.to_wid(ax, ay), self.to_wid(bx, by)
            crop = self.tool in ("crop", "zoom") or (self._drag is not None and self._drag[0] == "rzoom")
            p.setPen(QPen(QColor(ACCENT if crop else "#ca8a04"), 1.8, Qt.PenStyle.DashLine))
            p.setBrush(QColor(37, 99, 235, 40) if crop else QColor(250, 204, 21, 50))
            p.drawRect(QRectF(QPointF(*a), QPointF(*b)).normalized())

    def _paint_measure(self, p):
        mp = [(q[0], q[1]) for q in self.measure]
        n = len(mp)
        if self.hover is not None and self.measure:
            h = self.hover
            if self.measure_kind == "dist" and n == 1:
                h = self._pair(self.measure[0], h)[0]
            mp.append((h[0], h[1]))
        if len(mp) >= 2:
            tmp = dict(type="measure", kind=self.measure_kind, pts=[list(q) for q in mp], x=mp[0][0], y=mp[0][1],
                       x2=mp[-1][0], y2=mp[-1][1], text="", nr=0, color=self.ann_color, size=self.ann_size)
            self._paint_ann(p, tmp)
        p.setPen(QPen(QColor(self.ann_color), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for q in mp[:n]:
            p.drawEllipse(QPointF(*self.to_wid(q[0], q[1])), 4, 4)
        if self.tool == "measure" and self.snap_hint:
            x, y, k = self.snap_hint
            X, Y = self.to_wid(x, y)
            p.setPen(QPen(QColor("#16a34a"), 2))
            p.drawRect(QRectF(X - 6, Y - 6, 12, 12))
            if k == "h":
                p.drawLine(QPointF(X - 18, Y), QPointF(X + 18, Y))
            elif k == "v":
                p.drawLine(QPointF(X, Y - 18), QPointF(X, Y + 18))

    # --- Eingabe
    # --- Eingabe
    # Navigation geht immer, egal welches Werkzeug: Mausrad = zoomen, Trackpad (zwei Finger) = verschieben,
    # Trackpad aufziehen / Strg+Rad = zoomen, mittlere Maustaste = verschieben, rechte Maustaste ziehen =
    # Zoom-Rahmen (kurzer Rechtsklick = Menue), Doppelklick ins Leere = ganze Zeichnung.
    def _pan_widget(self, dx, dy):
        """Verschieben um einen Bildschirm-Vektor (beruecksichtigt die Drehung der Ansicht)."""
        inv = self._xform().inverted()[0]
        d = inv.map(QPointF(dx, dy)) - inv.map(QPointF(0, 0))
        self.pan(d.x(), d.y())

    def wheelEvent(self, e):
        if self.res is None:
            return
        pdl, adl = e.pixelDelta(), e.angleDelta()
        mods = e.modifiers()
        zoom_mod = bool(mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        trackpad = not pdl.isNull() and e.phase() != Qt.ScrollPhase.NoScrollPhase
        if trackpad and not zoom_mod:
            self._pan_widget(pdl.x(), pdl.y())
        else:
            steps = (pdl.y() / 60.0) if (trackpad and zoom_mod) else (adl.y() / 120.0)
            if steps:
                self.zoom_step(1.25 ** steps, self._vp(e.position()))
        ix, iy = self.to_img(self._vp(e.position()))
        self.cursor.emit(int(ix), int(iy), self.scale)

    def event(self, e):
        t = e.type()
        if t == QEvent.Type.NativeGesture and self.res is not None:          # Trackpad aufziehen (macOS)
            if e.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                self.zoom_step(1.0 + e.value(), self._vp(e.position()))
                return True
            if e.gestureType() == Qt.NativeGestureType.SmartZoomNativeGesture:
                self.fit()
                return True
        if t == QEvent.Type.Gesture and self.res is not None:                # Touch-Bildschirm (Windows)
            g = e.gesture(Qt.GestureType.PinchGesture)
            if g is not None:
                c = self.mapFromGlobal(g.centerPoint().toPoint())
                self.zoom_step(g.scaleFactor(), self._vp(QPointF(c)))
                return True
        return super().event(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if files:
            self.filesDropped.emit(files)
            e.acceptProposedAction()

    def _near_split(self, x):
        return self.mode == "S" and abs(x - self.split * self.width()) < 10

    def _hit_handle(self, ix, iy):
        if self.ann_selected is None or not (0 <= self.ann_selected < len(self.anns)):
            return None
        m = 8 / self.scale
        for name, hx, hy in ann_handles(self.shape, self.anns[self.ann_selected]):
            if abs(ix - hx) <= m and abs(iy - hy) <= m:
                return name
        return None

    def hit_ann(self, ix, iy):
        m = 7 / self.scale
        for i in reversed(range(len(self.anns))):
            if ann_hit(self.shape, self.anns[i], ix, iy, m):
                return i
        return None

    def mousePressEvent(self, e):
        self.setFocus()
        if self.res is None:
            if e.button() == Qt.MouseButton.RightButton:
                self.contextRequested.emit(e.globalPosition().toPoint())
            return
        self._moved = 0
        ov = self.overview_rect()
        if e.button() == Qt.MouseButton.LeftButton and ov is not None and ov.contains(e.position()):
            self._overview_jump(e.position())
            self._drag = ("ov",)
            return
        pos = self._vp(e.position())
        ix, iy = self.to_img(pos)
        left = e.button() == Qt.MouseButton.LeftButton
        if e.button() == Qt.MouseButton.RightButton:
            if self.tool == "measure" and self.measure:
                self.finish_measure()
                return
            self._drag = ("rzoom", e.position(), (ix, iy), e.globalPosition().toPoint())
            return
        if e.button() == Qt.MouseButton.MiddleButton:
            self._drag = ("pan", pos, self.ox, self.oy)
        elif left and self._near_split(pos.x()):
            self._drag = ("split",)
        elif left and self.tool == "hand":
            name = self._hit_handle(ix, iy) if self.show_overlays else None
            i = self.hit_ann(ix, iy) if self.show_overlays else None
            if name:
                self._drag = ("handle", name)
            elif i is not None:
                if i != self.ann_selected:
                    self.ann_selected = i
                    self.annSelected.emit(i)
                a = self.anns[i]
                self._drag = ("move", (ix, iy), (a["x"], a["y"], a["x2"], a["y2"]), copy.deepcopy(a.get("pts")))
            else:
                self._drag = ("pan", pos, self.ox, self.oy)
        elif left and self.tool == "measure":
            sx, sy, k = self.snap_point(ix, iy)
            self.measure.append((sx, sy, k))
            self.hover = None
            need = {"dist": 2, "angle": 3, "radius": 3}.get(self.measure_kind)
            if need and len(self.measure) >= need:
                self.finish_measure()
            self.update()
        elif left and self.tool in ("zone", "crop", "region", "zoom"):
            self._rubber = ((ix, iy), (ix, iy))
            self._drag = ("rubber",)
        elif left and self.tool in ("text", "number", "approval"):
            self.placeRequested.emit(self.tool, ix, iy)
        elif left and self.tool in ("rect", "arrow", "cloud", "highlight"):
            self._ann_prev = ((ix, iy), (ix, iy))
            self._drag = ("ann",)
        self.update()

    def mouseMoveEvent(self, e):
        pos = self._vp(e.position())
        self._mouse = e.position()
        if self.loupe or self.tool == "zoom":
            self.update()
        ix = iy = 0.0
        if self.res is not None:
            ix, iy = self.to_img(pos)
            self.cursor.emit(int(ix), int(iy), self.scale)
        ov = self.overview_rect()
        if self._drag is None and ov is not None and ov.contains(e.position()):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif self._near_split(pos.x()):
            self.setCursor(Qt.CursorShape.SplitHCursor)
        elif self.tool == "hand":
            cur = Qt.CursorShape.OpenHandCursor
            if self._drag is not None and self._drag[0] == "pan":
                cur = Qt.CursorShape.ClosedHandCursor
            elif self._drag is not None:
                cur = Qt.CursorShape.SizeAllCursor
            elif self.res is not None and self.show_overlays and (
                    self._hit_handle(ix, iy) or self.hit_ann(ix, iy) is not None):
                cur = Qt.CursorShape.SizeAllCursor
            self.setCursor(cur)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        if self._drag is None:
            if self.tool == "measure" and self.res is not None:
                sx, sy, k = self.snap_point(ix, iy)
                self.snap_hint = (sx, sy, k) if k else None
                self.hover = (sx, sy, k)
                self.update()
            return
        self._moved += 1
        kind = self._drag[0]
        if kind == "ov":
            self._overview_jump(e.position())
            return
        if kind == "rzoom":
            d = e.position() - self._drag[1]
            if abs(d.x()) + abs(d.y()) > 6:
                self._rubber = (self._drag[2], (ix, iy))
        elif kind == "pan":
            self._fitted = False
            d = pos - self._drag[1]
            self.ox = self._drag[2] - d.x() / self.scale
            self.oy = self._drag[3] - d.y() / self.scale
        elif kind == "split":
            self.split = float(np.clip(pos.x() / self.width(), 0.0, 1.0))
        elif kind == "rubber":
            self._rubber = (self._rubber[0], (ix, iy))
            (ax, ay), (bx, by) = self._rubber
            rw, rh = abs(bx - ax), abs(by - ay)
            self.window().statusBar().showMessage(
                f"Bereich: {rw:.0f} × {rh:.0f} px   =   {rw * self.mm_px:.1f} × {rh * self.mm_px:.1f} mm")
        elif kind == "ann":
            self._ann_prev = (self._ann_prev[0], (ix, iy))
        elif kind == "move":
            _, (sx, sy), (x, y, x2, y2), pts0 = self._drag
            a = self.anns[self.ann_selected]
            dx, dy = ix - sx, iy - sy
            a["x"], a["y"], a["x2"], a["y2"] = x + dx, y + dy, x2 + dx, y2 + dy
            if pts0:
                a["pts"] = [[q[0] + dx, q[1] + dy] for q in pts0]
        elif kind == "handle":
            if self._drag[1].startswith("m"):
                ix, iy, _k = self.snap_point(ix, iy)
            apply_handle(self.shape, self.anns[self.ann_selected], self._drag[1], ix, iy)
        self.update()

    def _zoom_rect(self, ax, ay, bx, by):
        zw, zh = abs(bx - ax), abs(by - ay)
        if zw > 5 / self.scale and zh > 5 / self.scale:
            s = float(np.clip(min(self.width() / zw, self.height() / zh) * 0.96, 0.01, 40.0))
            self.zoom_to(s, (ax + bx) / 2, (ay + by) / 2)
            return True
        return False

    def mouseReleaseEvent(self, e):
        if self._drag is None:
            return
        kind = self._drag[0]
        if kind == "rzoom":
            if self._rubber:
                (ax, ay), (bx, by) = self._rubber
                self._rubber = None
                self._zoom_rect(ax, ay, bx, by)
            else:                                  # kurzer Rechtsklick: Menue
                ix, iy = self._drag[2]
                i = self.hit_ann(ix, iy) if self.show_overlays else None
                if i is not None:
                    self.ann_selected = i
                    self.annSelected.emit(i)
                    self.annContext.emit(i, self._drag[3])
                else:
                    self.contextRequested.emit(self._drag[3])
        elif kind == "rubber" and self._rubber:
            (ax, ay), (bx, by) = self._rubber
            x, y = int(min(ax, bx)), int(min(ay, by))
            zw, zh = int(abs(bx - ax)), int(abs(by - ay))
            self._rubber = None
            self.window().statusBar().clearMessage()
            if self.tool == "zoom":
                if not self._zoom_rect(ax, ay, bx, by):
                    self.fit()                     # einfacher Klick im Zoom-Modus: Einpassen
                self.zoomBoxDone.emit()
            elif zw > 5 and zh > 5:
                h, w = self.shape
                x, y = max(0, x), max(0, y)
                zw, zh = min(zw, w - x), min(zh, h - y)
                {"crop": self.cropDrawn, "region": self.regionDrawn}.get(self.tool, self.zoneDrawn).emit(x, y, zw, zh)
        elif kind == "ann" and self._ann_prev:
            (ax, ay), (bx, by) = self._ann_prev
            self._ann_prev = None
            if abs(bx - ax) + abs(by - ay) > 8 / self.scale:
                if self.tool in rep.RECT_TYPES:
                    ax, bx, ay, by = min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)
                color = "#facc15" if self.tool == "highlight" and self.ann_color == "#e11d48" else self.ann_color
                self.annCreated.emit(dict(type=self.tool, x=ax, y=ay, x2=bx, y2=by, text="", nr=0,
                                          color=color, size=self.ann_size))
        elif kind in ("move", "handle"):
            if self._moved:
                self.annChanged.emit()
        elif kind == "pan" and self._moved < 3 and self.tool == "hand":
            if self.mode == "K" and self.ann_selected is None and self.hit_ann(*self.to_img(self._vp(e.position()))) is None:
                self.blinkClicked.emit()          # Klick im Blink-Modus: pausieren / fortsetzen
            self._click(*self.to_img(self._vp(e.position())))
        self._drag = None
        self.update()

    def _click(self, ix, iy):
        """Klick ins Leere: Auswahl aufheben oder nummerierte Aenderung waehlen."""
        if self.ann_selected is not None:
            self.ann_selected = None
            self.annSelected.emit(-1)
        if not self.show_overlays or not self.show_regs:
            return
        hit = [r for r in self.regs if r["x"] - 10 <= ix <= r["x"] + r["w"] + 10
               and r["y"] - 10 <= iy <= r["y"] + r["h"] + 10
               and (self.visible_types is None or r["typ"] in self.visible_types)]
        if hit:
            hit.sort(key=lambda r: r["w"] * r["h"])
            self.regionClicked.emit(hit[0]["nr"])

    def leaveEvent(self, e):
        self._mouse = None
        if self.loupe or self.tool == "zoom":
            self.update()
        super().leaveEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton:          # wie in CAD: Doppelklick Mausrad = alles zeigen
            self.fit()
            return
        if self.tool == "measure" and self.measure:
            self.finish_measure()
            return
        if self.tool != "hand" or self.res is None:
            return
        i = self.hit_ann(*self.to_img(self._vp(e.position()))) if self.show_overlays else None
        if i is not None:
            self.annEdit.emit(i)
        else:
            self.fit()

    def keyPressEvent(self, e):
        k = e.key()
        step = 0.15 * min(self.width(), self.height())
        if k == Qt.Key.Key_Escape:
            self.measure = []
            self._rubber = None
            self._ann_prev = None
            self._drag = None
            self.update()
            self.escapePressed.emit()
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.tool == "measure" and self.measure:
            self.finish_measure()
        elif k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom_step(1.25)
        elif k == Qt.Key.Key_Minus:
            self.zoom_step(1 / 1.25)
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) and self.res is not None:
            dx = {Qt.Key.Key_Left: step, Qt.Key.Key_Right: -step}.get(k, 0)
            dy = {Qt.Key.Key_Up: step, Qt.Key.Key_Down: -step}.get(k, 0)
            self._pan_widget(dx, dy)
        else:
            super().keyPressEvent(e)
