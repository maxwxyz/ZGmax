"""Zeichenflaeche: Anzeige, Zoom, Messen, Anmerkungen."""
from i18n import tr
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


# ----------------------------------------------------------------- Zeichenflaeche
class Canvas(QWidget):
    cursor = Signal(int, int, float)
    zoneDrawn = Signal(int, int, int, int)
    cropDrawn = Signal(int, int, int, int)
    regionClicked = Signal(int)
    annCreated = Signal(dict)
    placeRequested = Signal(str, float, float)
    textBoxDrawn = Signal(float, float, float)       # Textfeld aufgezogen: x, y, Breite (Bildpixel)
    annSelected = Signal(int)
    annMultiSelected = Signal(list)              # mehrere Markierungen gewaehlt (Strg/Umschalt)
    selCopy = Signal(int, int, int, int)         # Auswahl kopieren: Rechteck aufgezogen
    selMove = Signal(int, int, int, int)         # Ausschnitt verschieben: Rechteck aufgezogen
    floatDone = Signal(bool)                     # verschobenen Ausschnitt uebernehmen (True) / verwerfen
    zoneEdited = Signal(int, int, int, int, int)  # Zone i verschoben/geaendert: x, y, w, h (Bildpixel)
    zoneSelected = Signal(int)                   # Zone angeklickt (-1 = keine)
    frameEdited = Signal(int, int, int, int)     # Zuschnitt-Rahmen geaendert: x0, y0, x1, y1 (Bildpixel)
    areaChanged = Signal()                       # Bereichsauswahl geaendert (neu, erweitert, aufgehoben)
    areaMoveStarted = Signal()                   # Ziehen in der Bereichsauswahl beginnt (Zeichnung mitnehmen?)
    areaMoved = Signal(int, int)                 # Bereichsauswahl um dx, dy verschoben (beim Loslassen)
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
    alignPoint = Signal(str, float, float)   # manuelles Ausrichten: Seite ("A"/"B") und Bildpunkt

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.res = None
        self.pa = self.pb = self.pd = None
        self.regs = []
        self.anns = []
        self.visible_types = None
        self.visible_nrs = None                      # nur diese Nummern zeigen (Filter Masse/offen) oder None
        self.selected = None
        self.ann_selected = None
        self.ann_multi = set()                       # Mehrfachauswahl (mit ann_selected), leer = Einzelauswahl
        self.float = None                            # schwebender Ausschnitt beim Verschieben (dict)
        self.sel_rects = []                          # Bereichsauswahl: Rechtecke (x0, y0, x1, y1) in Bildpixeln
        self.zone_sel = None                         # gewaehlte Zone (Index) oder None
        self.crop_frame = None                       # Zuschnitt fuer Ausgaben (x0, y0, x1, y1) oder None
        self.layer_on = {k: True for k, _ in rep.LAYERS}      # Ebenen: sichtbar
        self.layer_lock = {k: False for k, _ in rep.LAYERS}   # Ebenen: gesperrt (nicht waehlbar/aenderbar)
        self.editing = None                          # Index des Texts, der gerade im Bild bearbeitet wird
        self.inline_editor = None                    # Eingabefeld dafuer (wird bei Zoom/Verschieben mitgefuehrt)
        self.poly = []                               # Punkte des Linienzugs/Polygons, das gerade entsteht
        self._pen = None                             # Punkte der Freihandlinie, die gerade entsteht
        self._poly_hover = None
        self._qimg = {}                              # eingefuegte Bilder als QImage (nach PNG-Inhalt)
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
        self.message = tr("Zeichnung A (alt) und B (neu) links \u00f6ffnen\noder hierher ziehen")
        self.show_overview = True            # Uebersichtsfenster unten rechts (nur wenn hineingezoomt)
        self.reg_clouds = False              # nummerierte Aenderungen als Revisionswolke statt Rahmen
        self.pc = (None, None)
        self.show_color = True               # Alt/Neu in Farbe zeigen, wenn die Datei farbig ist
        self.invert = False                  # helle Linien auf dunklem Grund (nur Anzeige)
        self.show_legend = True
        self.align_pts = {"A": [], "B": []}       # manuelles Ausrichten: gesetzte Punkte je Seite
        self.search_hits, self.search_cur, self.search_side = [], -1, "A"   # Textsuche
        self.preview = None                  # (QImage, (h, w)) waehrend der ersten Berechnung
        self.labels = (tr("A (alt)"), tr("B (neu)"))
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

    def reset_interaction(self):
        """Laufende Eingaben abbrechen (Text im Bild, schwebender Ausschnitt, Linienzug, Auswahl) - vor Rueckgaengig,
        Schliessen oder neuem Dokument, damit nichts an veralteten Indizes oder Koordinaten haengt."""
        if self.inline_editor is not None:
            self.inline_editor._finish(False)
        self.float = None
        self.poly, self._poly_hover, self._pen, self.measure = [], None, None, []
        self._drag = self._rubber = self._ann_prev = None
        self.sel_rects = []
        self.zone_sel = None
        self.ann_multi, self.ann_selected = set(), None

    def clear(self):
        """Keine Zeichnung mehr anzeigen (Dokument geschlossen)."""
        self.reset_interaction()
        self.crop_frame = None
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
        use_b = self.mode in ("B", "N") or (self.mode == "Y" and self._side == "B")
        src = self.res.b if use_b else self.res.a
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
        need = {"dist": 2, "chain": 2, "poly": 2, "angle": 3, "radius": 3, "area": 3}[k]
        if k == "chain" and len(pts) >= 2:          # Masskette: je Abschnitt ein eigenes Mass, als Gruppe
            import uuid
            grp = uuid.uuid4().hex[:8]
            for i in range(len(pts) - 1):
                (ax, ay), (bx, by) = pts[i][:2], pts[i + 1][:2]
                self.annCreated.emit(dict(type="measure", kind="dist", pts=[[float(ax), float(ay)], [float(bx), float(by)]],
                                          x=ax, y=ay, x2=bx, y2=by, text="", nr=0, color=self.ann_color,
                                          size=self.ann_size, group=grp))
            self.measure = []
            self.hover = None
            self.update()
            return
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
                part = pc[L][sl]
                return part if part.ndim == 3 else cv2.cvtColor(part, cv2.COLOR_GRAY2BGR)
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
            self._paint_base(p, self.width(), self.height())
            self._paint_float(p)
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
        if self.inline_editor is not None:            # Texteingabe im Bild folgt Zoom und Verschieben
            self.inline_editor.place()
        if self.loupe and self._mouse is not None and self.tool != "zone":
            self._paint_loupe(p)
        p.end()

    def _paint_float(self, p):
        """Verschobener Ausschnitt: Quelle mit Papierfarbe abgedeckt, Stueck an der neuen Stelle, gestrichelt umrandet."""
        f = self.float
        if not f:
            return
        x0, y0, x1, y1 = f["rect"]
        X0, Y0 = self.to_wid(x0, y0)
        X1, Y1 = self.to_wid(x1, y1)
        src = QRectF(X0, Y0, X1 - X0, Y1 - Y0)
        dst = src.translated(f["dx"] * self.scale, f["dy"] * self.scale)
        p.drawImage(src, f["hole"])
        p.drawImage(dst, f["piece"])
        pen = QPen(QColor(ACCENT), 0, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(dst)

    def _paint_side_by_side(self, p, w, h):
        half = QWidget.width(self) // 2
        H = QWidget.height(self)
        for i, m in enumerate(("A", "B")):
            p.save()
            p.setClipRect(QRectF(i * half, 0, half, H))
            p.translate(i * half, 0)
            self.mode = m
            self._painting_side = m
            try:
                self._paint_base(p, half, H)
                self._paint_overlays(p, w, h)
            finally:
                self.mode = "Y"
                self._painting_side = None
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
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("Vergleich l\u00e4uft \u2026"))

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
            img = pc[-1] if pc is not None else 255 - top
            if img.ndim == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
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

    def _paint_base(self, p, W, H):
        """Zeichnung - oder, wenn ihre Ebene ausgeblendet ist, leeres Papier."""
        if self.layer_on.get("zeichnung", True):
            self._paint_image(p, W, H)
            return
        h, w = self.shape
        a, b = self.to_wid(0, 0), self.to_wid(w, h)
        p.fillRect(QRectF(QPointF(*a), QPointF(*b)).normalized(), QColor(26, 24, 22) if self.invert else QColor("white"))

    def ann_visible(self, a):
        return self.layer_on.get(rep.ann_layer(a), True) and not a.get("hidden")

    def ann_editable(self, a):
        return self.ann_visible(a) and not self.layer_lock.get(rep.ann_layer(a), False)

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
        items = {"D": (("#e5173f", tr("nur in A (alt)")), ("#1f3fff", tr("nur in B (neu)")), ("#969696", tr("gleich")),
                       ("#00aa00", tr("verschoben"))),
                 "O": (("#e5173f", tr("nur in A (alt)")), ("#1f3fff", tr("nur in B (neu)")), ("#969696", tr("gleich"))),
                 "S": (), "A": (), "B": (), "K": (),
                 "N": (("#1f3fff", tr("neu / ge\u00e4ndert")), ("#969696", tr("unver\u00e4ndert"))),
                 "R": (("#e5173f", tr("entfernt / ge\u00e4ndert")), ("#969696", tr("unver\u00e4ndert")))}[self.mode]
        if self.mode in ("A", "B", "K"):            # gleiche Legende wie bei der \u00dcberlagerung: welche Version ist zu sehen
            which = ("B" if self.blink_b else "A") if self.mode == "K" else self.mode
            items = (("#e5173f", tr("Zeichnung A (alt)")),) if which == "A" else (("#1f3fff", tr("Zeichnung B (neu)")),)
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
                txt = "\n".join(rep.ann_lines(a, rep.ann_text_h(shape, a["size"])))
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    p.drawText(box.translated(dx, dy), fl, txt)
                p.setPen(col)
                p.drawText(box, fl, txt)
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
            mlw, mth, alen = rep.measure_style(shape, a["size"])
            mlw, mth, alen = max(1.0, mlw * s), mth * s, alen * s
            # Groesse wie auf dem Papier (waechst mit dem Zoom); beim Herauszoomen nie unlesbar klein
            mth = max(11.0, mth)
            alen = float(np.clip(alen, 7, 40))
            pen = QPen(col, mlw)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            for gk, gd in rep.measure_geometry(a):
                if gk == "circle":
                    cx, cy = self.to_wid(gd[0], gd[1])
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawEllipse(QPointF(cx, cy), gd[2] * s, gd[2] * s)
                    p.drawLine(QPointF(cx - 6, cy), QPointF(cx + 6, cy))
                    p.drawLine(QPointF(cx, cy - 6), QPointF(cx, cy + 6))
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
            wp = [self.to_wid(q[0], q[1]) for q in a["pts"]]
            if a.get("kind", "dist") == "dist" and len(wp) >= 2:   # Pfeilspitzen wie bei einer Bemassung
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col)
                for tip, frm in ((wp[0], wp[1]), (wp[-1], wp[-2])):
                    p.drawPolygon(QPolygonF([QPointF(*q) for q in rep.arrow_head(tip, frm, alen)]))
            else:
                p.setPen(QPen(col, mlw))
                p.setBrush(QColor("white"))
                for q in wp:
                    p.drawEllipse(QPointF(*q), 3, 3)
            txt = rep.measure_text(a, self.mm_px)
            if txt:                                   # Wert wie bei einer Bemassung: ueber der Linie, parallel
                cx, cy, ang, ax, ay = rep.measure_label(a, shape)
                X, Y = self.to_wid(cx, cy)
                if a.get("lo"):                       # verschoben: Hinweislinie zur Messung
                    p.setPen(QPen(col, max(1.0, mlw * 0.8)))
                    p.drawLine(QPointF(X, Y), QPointF(*self.to_wid(ax, ay)))
                f = QFont(UI_FONT)
                f.setPixelSize(int(mth))
                f.setBold(True)
                p.setFont(f)
                tw = p.fontMetrics().horizontalAdvance(txt)
                p.save()
                p.translate(X, Y)
                p.rotate(ang)
                r = QRectF(-tw / 2 - mth * 0.3, -mth * 0.65, tw + mth * 0.6, mth * 1.3)
                p.setPen(QPen(col, 1))
                p.setBrush(QColor(255, 255, 255, 235))
                p.drawRoundedRect(r, mth * 0.25, mth * 0.25)
                p.setPen(col)
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, txt)
                p.restore()
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
        elif t == "line":
            x2, y2 = self.to_wid(a["x2"], a["y2"])
            pen = QPen(col, lw)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x, y), QPointF(x2, y2))
        elif t == "ellipse":
            x2, y2 = self.to_wid(a["x2"], a["y2"])
            p.setPen(QPen(col, lw))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(QPointF(x, y), QPointF(x2, y2)).normalized())
        elif t in rep.PTS_TYPES and a.get("pts"):
            pen = QPen(col, lw)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            pg = QPolygonF([QPointF(*self.to_wid(q[0], q[1])) for q in a["pts"]])
            if t == "polygon":
                p.drawPolygon(pg)
            elif len(a["pts"]) == 1:
                p.drawPoint(pg[0])
            else:
                p.drawPolyline(pg)
        elif t == "image":
            x2, y2 = self.to_wid(a["x2"], a["y2"])
            p.drawImage(QRectF(QPointF(x, y), QPointF(x2, y2)).normalized(), self._ann_qimage(a))
        elif t == "redact":
            x2, y2 = self.to_wid(a["x2"], a["y2"])
            fill = QColor("black")
            if a.get("fill") == "paper" and self.res is not None:   # Papierfarbe aus der Umgebung
                h_, w_ = self.shape
                X0, Y0 = max(0, int(min(a["x"], a["x2"]))), max(0, int(min(a["y"], a["y2"])))
                X1, Y1 = min(w_, int(max(a["x"], a["x2"])) + 1), min(h_, int(max(a["y"], a["y2"])) + 1)
                if X1 > X0 and Y1 > Y0:
                    m = self.mode if self.mode in ("A", "B", "D", "O", "N", "R") else "D"
                    ring = 24
                    part = self._layer(m, 0, max(0, Y0 - ring), min(h_, Y1 + ring), max(0, X0 - ring), min(w_, X1 + ring))
                    b, g, r = rep.paper_around(part, ring, ring, part.shape[1] - ring, part.shape[0] - ring)
                    fill = QColor(r, g, b)
                    if self.invert:
                        fill = QColor(26, 24, 22)
            p.fillRect(QRectF(QPointF(x, y), QPointF(x2, y2)).normalized(), fill)
        elif t == "pixelate":
            img, rect = self._pixelated(a)
            if img is not None:
                a0, b0 = self.to_wid(rect[0], rect[1])
                a1, b1 = self.to_wid(rect[2], rect[3])
                p.save()
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
                p.drawImage(QRectF(a0, b0, a1 - a0, b1 - b0), img)
                p.restore()
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
            if t not in ("arrow", "line", "measure") or self.ann_multi:
                p.drawRect(QRectF(a0 - 3, b0 - 3, a1 - a0 + 6, b1 - b0 + 6))
            p.setPen(QPen(QColor(ACCENT), 1.6))
            p.setBrush(QColor("white"))
            for _, hx, hy in ([] if self.ann_multi else ann_handles(shape, a)):   # Griffe nur bei Einzelauswahl
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
        if self.tool == "align":                  # Punkte des manuellen Ausrichtens (je Haelfte)
            side = "B" if self.mode == "B" else "A"
            f = QFont(UI_FONT, 10)
            f.setBold(True)
            p.setFont(f)
            for i, (qx, qy) in enumerate(self.align_pts[side]):
                X, Y = self.to_wid(qx, qy)
                p.setPen(QPen(QColor("#f59e0b"), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(X, Y), 9, 9)
                p.drawLine(QPointF(X - 14, Y), QPointF(X + 14, Y))
                p.drawLine(QPointF(X, Y - 14), QPointF(X, Y + 14))
                r = QRectF(X + 8, Y - 26, 20, 18)
                p.fillRect(r, QColor("#f59e0b"))
                p.setPen(QColor("white"))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(i + 1))
        if self.search_hits and (self.mode not in ("A", "B") or self.res is None or
                                 not (getattr(self, "_painting_side", None))
                                 or self._painting_side == self.search_side):
            for i, (x0, y0, x1, y1) in enumerate(self.search_hits):
                a0, b0 = self.to_wid(x0, y0)
                a1, b1 = self.to_wid(x1, y1)
                r = QRectF(a0 - 3, b0 - 3, a1 - a0 + 6, b1 - b0 + 6)
                cur = i == self.search_cur
                p.fillRect(r, QColor(250, 204, 21, 110 if cur else 60))
                p.setPen(QPen(QColor("#ea580c" if cur else "#ca8a04"), 2.5 if cur else 1.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(r)
        if not self.show_overlays:
            return
        for k, (x, y, zw, zh) in enumerate(self.zones if self.layer_on.get("zonen", True) else []):
            a = self.to_wid(x, y)
            r = QRectF(a[0], a[1], zw * s, zh * s)
            p.fillRect(r, QColor(250, 204, 21, 70))
            sel = k == self.zone_sel
            p.setPen(QPen(QColor(ACCENT if sel else "#ca8a04"), 2.2 if sel else 1.5, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            if sel:                                   # Anfasser an den Ecken
                p.setPen(QPen(QColor(ACCENT), 1.6))
                p.setBrush(QColor("white"))
                for X, Y in ((r.left(), r.top()), (r.right(), r.top()), (r.left(), r.bottom()), (r.right(), r.bottom())):
                    p.drawRect(QRectF(X - 4.5, Y - 4.5, 9, 9))
        if self.regs and self.show_regs and self.layer_on.get("aenderungen", True):
            font = QFont(UI_FONT, 8)
            font.setBold(True)
            p.setFont(font)
            for r in self.regs:
                if self.visible_types is not None and r["typ"] not in self.visible_types:
                    continue
                if self.visible_nrs is not None and r["nr"] not in self.visible_nrs:
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
        chosen = self.selected_anns()
        for i in rep.layer_order(self.anns):               # Ebenen: Bilder unten, Masse oben
            a = self.anns[i]
            if i != self.editing and self.ann_visible(a):   # nicht: gerade direkt bearbeiteter Text, aus. Ebene
                self._paint_ann(p, a, i in chosen)
        if self._ann_prev:
            (ax, ay), (bx, by) = self._ann_prev
            self._paint_ann(p, dict(type=self.tool, x=ax, y=ay, x2=bx, y2=by, text="", nr=0,
                                    color=self.ann_color, size=self.ann_size))
        if self._pen:
            self._paint_ann(p, dict(type="pen", pts=self._pen, x=0, y=0, x2=0, y2=0, text="", nr=0,
                                    color=self.ann_color, size=self.ann_size))
        if self.poly:
            pts = self.poly + ([self._poly_hover] if self._poly_hover else [])
            self._paint_ann(p, dict(type="polyline" if len(pts) < 3 else self.tool, pts=pts, x=0, y=0, x2=0, y2=0,
                                    text="", nr=0, color=self.ann_color, size=self.ann_size))
            p.setPen(QPen(QColor(ACCENT), 1.4))
            p.setBrush(QColor("white"))
            for q in self.poly:
                p.drawEllipse(QPointF(*self.to_wid(*q)), 3.5, 3.5)
        if self.measure or (self.tool == "measure" and self.snap_hint):
            self._paint_measure(p)
        if self.crop_frame is not None and self.show_overlays:
            self._paint_crop_frame(p)
        if self.sel_rects:                             # Bereichsauswahl: gestrichelt, leicht getoent
            for x0, y0, x1, y1 in self.sel_rects:
                a, b = self.to_wid(x0, y0), self.to_wid(x1, y1)
                rr = QRectF(QPointF(*a), QPointF(*b)).normalized()
                p.setBrush(QColor(37, 99, 235, 28))
                p.setPen(QPen(QColor("white"), 1.6))
                p.drawRect(rr)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(QColor(ACCENT), 1.6, Qt.PenStyle.DashLine))
                p.drawRect(rr)
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
            tmp = dict(type="measure", kind="poly" if self.measure_kind == "chain" else self.measure_kind,
                       pts=[list(q) for q in mp], x=mp[0][0], y=mp[0][1],
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
        if self.ann_multi or self.ann_selected is None or not (0 <= self.ann_selected < len(self.anns)):
            return None
        m = 8 / self.scale
        for name, hx, hy in ann_handles(self.shape, self.anns[self.ann_selected]):
            if abs(ix - hx) <= m and abs(iy - hy) <= m:
                return name
        return None

    def _pixelated(self, a):
        """Mosaik des angezeigten Inhalts unter einer Verpixelung (zwischengespeichert)."""
        h, w = self.shape
        x0, y0 = max(0, int(min(a["x"], a["x2"]))), max(0, int(min(a["y"], a["y2"])))
        x1, y1 = min(w, int(np.ceil(max(a["x"], a["x2"])))), min(h, int(np.ceil(max(a["y"], a["y2"]))))
        if x1 <= x0 or y1 <= y0:
            return None, None
        mode = self.mode if self.mode in ("A", "B", "D", "O", "N", "R") else "D"
        blk = rep.pixel_block(self.shape, a["size"])
        key = ("pix", x0, y0, x1, y1, blk, rep.redact_seed(a), mode, self.show_color, self.invert, id(self.pa),
               self.layer_on.get("zeichnung"))
        hit = self._qimg.get(key)
        if hit is None:
            part = self._layer(mode, 0, y0, y1, x0, x1) if self.layer_on.get("zeichnung", True) else \
                np.full((y1 - y0, x1 - x0, 3), 255, np.uint8)
            if self.invert:
                part = invert_view(part, mode)
            small = np.ascontiguousarray(rep.pixelate(part, blk, rep.redact_seed(a))[::blk, ::blk])
            img = QImage(small.data, small.shape[1], small.shape[0], small.strides[0], QImage.Format.Format_BGR888).copy()
            if len(self._qimg) > 64:
                self._qimg.clear()
            hit = self._qimg[key] = img
        return hit, (x0, y0, x1, y1)

    def _ann_qimage(self, a):
        key = a.get("png", "")
        img = self._qimg.get(key)
        if img is None:
            arr = np.ascontiguousarray(rep.ann_image(a))
            img = QImage(arr.data, arr.shape[1], arr.shape[0], arr.strides[0], QImage.Format.Format_ARGB32).copy()
            if len(self._qimg) > 64:
                self._qimg.clear()
            self._qimg[key] = img
        return img

    def finish_poly(self):
        """Linienzug/Polygon abschliessen (Doppelklick, Enter, Rechtsklick)."""
        pts = []
        for q in self.poly:                          # doppelte Punkte (Doppelklick) entfernen
            if not pts or math.hypot(q[0] - pts[-1][0], q[1] - pts[-1][1]) > 2 / self.scale:
                pts.append([float(q[0]), float(q[1])])
        self.poly, self._poly_hover = [], None
        if len(pts) >= (3 if self.tool == "polygon" else 2):
            x0, y0, x1, y1 = rep.pts_bbox(pts)
            self.annCreated.emit(dict(type=self.tool, pts=pts, x=x0, y=y0, x2=x1, y2=y1, text="", nr=0,
                                      color=self.ann_color, size=self.ann_size))
        self.update()

    def _finish_pen(self):
        pts = self._pen or []
        self._pen = None
        if len(pts) >= 2:                            # glaetten: Punkte auf eine Abweichung < ~0,6 Bildschirmpixel
            arr = np.float32(pts).reshape(-1, 1, 2)
            arr = cv2.approxPolyDP(arr, 0.6 / self.scale, False).reshape(-1, 2)
            pts = [[float(q[0]), float(q[1])] for q in arr]
        if pts:
            x0, y0, x1, y1 = rep.pts_bbox(pts)
            if len(pts) == 1:
                pts = [pts[0], [pts[0][0] + 0.01, pts[0][1]]]
            self.annCreated.emit(dict(type="pen", pts=pts, x=x0, y=y0, x2=x1, y2=y1, text="", nr=0,
                                      color=self.ann_color, size=self.ann_size))
        self.update()

    def hit_ann(self, ix, iy):
        m = 7 / self.scale
        for i in reversed(rep.layer_order(self.anns)):     # oben liegende zuerst treffen
            if self.ann_editable(self.anns[i]) and ann_hit(self.shape, self.anns[i], ix, iy, m):
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
            if self.tool in ("polyline", "polygon") and self.poly:
                self.finish_poly()
                return
            self._drag = ("rzoom", e.position(), (ix, iy), e.globalPosition().toPoint())
            return
        if left and self.float:                      # schwebender Ausschnitt: ziehen oder (Klick daneben) absetzen
            x0, y0, x1, y1 = self.float["rect"]
            dx, dy = self.float["dx"], self.float["dy"]
            if x0 + dx <= ix <= x1 + dx and y0 + dy <= iy <= y1 + dy:
                self._drag = ("float", (ix, iy), dx, dy)
            else:
                self.floatDone.emit(True)
            return
        if e.button() == Qt.MouseButton.MiddleButton:
            self._drag = ("pan", pos, self.ox, self.oy)
        elif left and self._near_split(pos.x()):
            self._drag = ("split",)
        elif left and self.tool == "hand":
            add = bool(e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
                                         | Qt.KeyboardModifier.MetaModifier))
            name = self._hit_handle(ix, iy) if self.show_overlays and not add and not self.ann_multi else None
            i = self.hit_ann(ix, iy) if self.show_overlays else None
            if name:
                self._drag = ("handle", name)
            elif i is not None and add:                  # Strg/Umschalt + Klick: zur Auswahl hinzu / heraus
                chosen = self.selected_anns()
                chosen ^= {i}
                self._set_multi(chosen)
            elif i is not None:
                if i not in self.selected_anns():
                    self.ann_multi = set()
                    self.ann_selected = i
                    self.annSelected.emit(i)
                idx = sorted(self.selected_anns())
                orig = {k: copy.deepcopy(self.anns[k]) for k in idx}
                self._drag = ("move", (ix, iy), orig)
            elif add and self.show_overlays and self.anns:  # Umschalt + Ziehen im Leeren: Auswahlrahmen
                self._rubber = ((ix, iy), (ix, iy))
                self._drag = ("selbox",)
            elif self._frame_handle(ix, iy) is not None:    # Zuschnitt-Rahmen an Ecke/Kante anpassen
                self._drag = ("fhandle", self._frame_handle(ix, iy), tuple(self.crop_frame))
            elif self._zone_handle(ix, iy) is not None:     # Ecke der gewaehlten Zone: Groesse aendern
                self._drag = ("zhandle", self._zone_handle(ix, iy), tuple(self.zones[self.zone_sel]))
            elif self.hit_zone(ix, iy) is not None:          # Zone anklicken: waehlen und verschieben
                k = self.hit_zone(ix, iy)
                if self.ann_selected is not None or self.ann_multi:
                    self.ann_multi, self.ann_selected = set(), None
                    self.annSelected.emit(-1)
                self.zone_sel = k
                self.zoneSelected.emit(k)
                self._drag = ("zmove", (ix, iy), tuple(self.zones[k]))
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
        elif left and self.tool == "area":
            add = bool(e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
                                         | Qt.KeyboardModifier.MetaModifier))
            if not add and self.in_selection(ix, iy):     # in die Auswahl klicken und ziehen = verschieben
                self.areaMoveStarted.emit()
                idx = sorted(self.selected_anns())
                self._drag = ("areamove", (ix, iy), {k: copy.deepcopy(self.anns[k]) for k in idx},
                              list(self.sel_rects))
            else:
                self._rubber = ((ix, iy), (ix, iy))
                self._drag = ("area", add)
        elif left and self.tool in ("zone", "crop", "region", "zoom", "copysel", "cutmove"):
            self._rubber = ((ix, iy), (ix, iy))
            self._drag = ("rubber",)
        elif left and self.tool == "text":                 # Klick = Text an der Stelle, Ziehen = Textfeld
            self._rubber = ((ix, iy), (ix, iy))
            self._drag = ("textbox",)
        elif left and self.tool in ("number", "approval"):
            self.placeRequested.emit(self.tool, ix, iy)
        elif left and self.tool == "align":
            sx, sy, _k = self.snap_point(ix, iy)
            self.alignPoint.emit(self._side if self.mode == "Y" else "A", sx, sy)
        elif left and self.tool == "pen":
            self._pen = [[ix, iy]]
            self._drag = ("pen",)
        elif left and self.tool in ("polyline", "polygon"):
            self.poly.append([ix, iy])
        elif left and self.tool in ("rect", "arrow", "cloud", "highlight", "ellipse", "line", "redact", "pixelate"):
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
                    self._hit_handle(ix, iy) or self.hit_ann(ix, iy) is not None or self._frame_handle(ix, iy)):
                cur = Qt.CursorShape.SizeAllCursor
            self.setCursor(cur)
        elif self.tool == "area" and self.res is not None and self.in_selection(ix, iy):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)
        if self._drag is None and self.poly:              # Linienzug: Vorschau bis zum Mauszeiger
            self._poly_hover = [ix, iy]
            self.update()
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
        elif kind == "areamove":
            _, (sx, sy), orig, rects0 = self._drag
            dx, dy = round(ix - sx), round(iy - sy)
            for k, o in orig.items():
                if k < len(self.anns):
                    a = self.anns[k]
                    a["x"], a["y"], a["x2"], a["y2"] = o["x"] + dx, o["y"] + dy, o["x2"] + dx, o["y2"] + dy
                    if o.get("pts"):
                        a["pts"] = [[q[0] + dx, q[1] + dy] for q in o["pts"]]
            self.sel_rects = [(r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy) for r in rects0]
            if self.float:
                self.float["dx"], self.float["dy"] = dx, dy
        elif kind in ("rubber", "selbox", "textbox", "area") and self._rubber is not None:
            self._rubber = (self._rubber[0], (ix, iy))
            (ax, ay), (bx, by) = self._rubber
            rw, rh = abs(bx - ax), abs(by - ay)
            self.window().statusBar().showMessage(
                tr("Bereich: {:.0f} × {:.0f} px   =   {:.1f} × {:.1f} mm").format(rw, rh, rw * self.mm_px, rh * self.mm_px))
        elif kind == "ann":
            self._ann_prev = (self._ann_prev[0], (ix, iy))
        elif kind == "fhandle" and self.crop_frame is not None:
            _, name, (x0, y0, x1, y1) = self._drag
            if "l" in name:
                x0 = ix
            if "r" in name:
                x1 = ix
            if "t" in name:
                y0 = iy
            if "b" in name:
                y1 = iy
            x0, x1 = sorted((int(round(x0)), int(round(x1))))
            y0, y1 = sorted((int(round(y0)), int(round(y1))))
            self.crop_frame = (x0, y0, max(x0 + 2, x1), max(y0 + 2, y1))
        elif kind == "zmove" and self.zone_sel is not None:
            _, (sx, sy), (x, y, w, h) = self._drag
            self.zones[self.zone_sel] = (int(round(x + ix - sx)), int(round(y + iy - sy)), w, h)
        elif kind == "zhandle" and self.zone_sel is not None:
            _, corner, (x, y, w, h) = self._drag
            x0, y0, x1, y1 = x, y, x + w, y + h
            if "l" in corner:
                x0 = ix
            else:
                x1 = ix
            if "t" in corner:
                y0 = iy
            else:
                y1 = iy
            x0, x1 = sorted((int(round(x0)), int(round(x1))))
            y0, y1 = sorted((int(round(y0)), int(round(y1))))
            self.zones[self.zone_sel] = (x0, y0, max(1, x1 - x0), max(1, y1 - y0))
        elif kind == "pen" and self._pen is not None:
            q = self._pen[-1]
            if math.hypot(ix - q[0], iy - q[1]) >= 1.5 / self.scale:
                self._pen.append([ix, iy])
        elif kind == "float" and self.float:
            _, (sx, sy), dx0, dy0 = self._drag
            self.float["dx"], self.float["dy"] = round(dx0 + ix - sx), round(dy0 + iy - sy)
        elif kind == "move":
            _, (sx, sy), orig = self._drag
            dx, dy = ix - sx, iy - sy
            for k, o in orig.items():
                if k < len(self.anns):
                    a = self.anns[k]
                    a["x"], a["y"], a["x2"], a["y2"] = o["x"] + dx, o["y"] + dy, o["x2"] + dx, o["y2"] + dy
                    if o.get("pts"):
                        a["pts"] = [[q[0] + dx, q[1] + dy] for q in o["pts"]]
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
                    z = self.hit_zone(ix, iy) if self.tool == "hand" else None
                    if z is not None:                  # Rechtsklick auf eine Zone: waehlen, Menue mit "Zone loeschen"
                        self.zone_sel = z
                        self.zoneSelected.emit(z)
                    self.contextRequested.emit(self._drag[3])
        elif kind == "area":
            r = self._rubber
            self._rubber = None
            self.window().statusBar().clearMessage()
            if r and abs(r[1][0] - r[0][0]) * self.scale > 4 and abs(r[1][1] - r[0][1]) * self.scale > 4:
                h, w = self.shape
                x0, x1 = sorted((r[0][0], r[1][0]))
                y0, y1 = sorted((r[0][1], r[1][1]))
                # nicht auf das Blatt begrenzt: "Zuschneiden" kann so das Blatt auch vergroessern
                rect = (int(np.floor(x0)), int(np.floor(y0)), int(round(x1)), int(round(y1)))
                if rect[2] > 0 and rect[3] > 0 and rect[0] < w and rect[1] < h:
                    self.sel_rects = (self.sel_rects if self._drag[1] else []) + [rect]
            elif not self._drag[1]:                    # Klick ins Leere: Auswahl aufheben
                self.sel_rects = []
            self.areaChanged.emit()
        elif kind == "areamove":
            _, (sx, sy), _o, rects0 = self._drag
            dx = self.sel_rects[0][0] - rects0[0][0] if self.sel_rects and rects0 else 0
            dy = self.sel_rects[0][1] - rects0[0][1] if self.sel_rects and rects0 else 0
            self._drag = None
            self.areaMoved.emit(dx, dy)
        elif kind == "textbox" and self._rubber:
            (ax, ay), (bx, by) = self._rubber
            self._rubber = None
            self.window().statusBar().clearMessage()
            if abs(bx - ax) * self.scale > 20:
                self.textBoxDrawn.emit(min(ax, bx), min(ay, by), abs(bx - ax))
            else:
                self.placeRequested.emit("text", ax, ay)
        elif kind == "selbox" and self._rubber:
            (ax, ay), (bx, by) = self._rubber
            self._rubber = None
            self.window().statusBar().clearMessage()
            x0, x1, y0, y1 = min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)
            hit = set()
            for k, a in enumerate(self.anns):
                bx0, by0, bx1, by1 = rep.ann_bounds(self.shape, a)
                if bx0 < x1 and bx1 > x0 and by0 < y1 and by1 > y0:
                    hit.add(k)
            self._set_multi(self.selected_anns() | hit)
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
                {"crop": self.cropDrawn, "region": self.regionDrawn, "copysel": self.selCopy,
                 "cutmove": self.selMove}.get(self.tool, self.zoneDrawn).emit(x, y, zw, zh)
        elif kind == "ann" and self._ann_prev:
            (ax, ay), (bx, by) = self._ann_prev
            self._ann_prev = None
            if abs(bx - ax) + abs(by - ay) > 8 / self.scale:
                if self.tool in rep.RECT_TYPES:
                    ax, bx, ay, by = min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)
                color = "#facc15" if self.tool == "highlight" and self.ann_color == "#e11d48" else self.ann_color
                extra = {}
                if self.tool == "redact":                # Schwaerzen: schwarz oder Papierfarbe (Haken in der Leiste)
                    color = "#000000"
                    win = self.window()
                    extra["fill"] = "paper" if getattr(win, "chk_redact_paper", None) and \
                        win.chk_redact_paper.isChecked() else "black"
                self.annCreated.emit(dict(type=self.tool, x=ax, y=ay, x2=bx, y2=by, text="", nr=0,
                                          color=color, size=self.ann_size, **extra))
        elif kind == "pen":
            self._finish_pen()
        elif kind == "fhandle" and self.crop_frame is not None:
            if self._moved:
                self.frameEdited.emit(*self.crop_frame)
        elif kind in ("zmove", "zhandle") and self.zone_sel is not None:
            if self._moved:
                self.zoneEdited.emit(self.zone_sel, *self.zones[self.zone_sel])
        elif kind in ("move", "handle"):
            if self._moved:
                self.annChanged.emit()
        elif kind == "pan" and self._moved < 3 and self.tool == "hand":
            if self.mode == "K" and self.ann_selected is None and self.hit_ann(*self.to_img(self._vp(e.position()))) is None:
                self.blinkClicked.emit()          # Klick im Blink-Modus: pausieren / fortsetzen
            self._click(*self.to_img(self._vp(e.position())))
        self._drag = None
        self.update()

    def hit_zone(self, ix, iy):
        if not (self.show_overlays and self.layer_on.get("zonen", True)) or self.layer_lock.get("zonen"):
            return None
        m = 4 / self.scale
        for k in reversed(range(len(self.zones))):
            x, y, w, h = self.zones[k]
            if x - m <= ix <= x + w + m and y - m <= iy <= y + h + m:
                return k
        return None

    def _frame_points(self):
        x0, y0, x1, y1 = self.crop_frame
        xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
        return (("tl", x0, y0), ("tr", x1, y0), ("bl", x0, y1), ("br", x1, y1),
                ("t", xm, y0), ("b", xm, y1), ("l", x0, ym), ("r", x1, ym))

    def _frame_handle(self, ix, iy):
        if self.crop_frame is None or not self.show_overlays:
            return None
        m = 9 / self.scale
        for name, hx, hy in self._frame_points():
            if abs(ix - hx) <= m and abs(iy - hy) <= m:
                return name
        return None

    def _paint_crop_frame(self, p):
        """Zuschnitt: aussen abgedunkelt, Rahmen mit Anfassern (gilt nur fuer Ausgaben)."""
        x0, y0, x1, y1 = self.crop_frame
        a, b = self.to_wid(x0, y0), self.to_wid(x1, y1)
        r = QRectF(QPointF(*a), QPointF(*b)).normalized()
        outside = QPainterPath()
        outside.addRect(QRectF(self.rect()).adjusted(-5000, -5000, 5000, 5000))
        inner = QPainterPath()
        inner.addRect(r)
        p.fillPath(outside.subtracted(inner), QColor(15, 23, 42, 110))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("white"), 2))
        p.drawRect(r)
        p.setPen(QPen(QColor(ACCENT), 2, Qt.PenStyle.DashLine))
        p.drawRect(r)
        p.setPen(QPen(QColor(ACCENT), 1.6))
        p.setBrush(QColor("white"))
        for _n, hx, hy in self._frame_points():
            X, Y = self.to_wid(hx, hy)
            p.drawRect(QRectF(X - 5, Y - 5, 10, 10))

    def _zone_handle(self, ix, iy):
        if self.zone_sel is None or self.zone_sel >= len(self.zones):
            return None
        x, y, w, h = self.zones[self.zone_sel]
        m = 8 / self.scale
        for name, hx, hy in (("tl", x, y), ("tr", x + w, y), ("bl", x, y + h), ("br", x + w, y + h)):
            if abs(ix - hx) <= m and abs(iy - hy) <= m:
                return name
        return None

    def _click(self, ix, iy):
        """Klick ins Leere: Auswahl aufheben oder nummerierte Aenderung waehlen."""
        if self.zone_sel is not None:
            self.zone_sel = None
            self.zoneSelected.emit(-1)
        if self.ann_selected is not None or self.ann_multi:
            self.ann_multi = set()
            self.ann_selected = None
            self.annSelected.emit(-1)
        if not self.show_overlays or not self.show_regs:
            return
        hit = [r for r in self.regs if r["x"] - 10 <= ix <= r["x"] + r["w"] + 10
               and r["y"] - 10 <= iy <= r["y"] + r["h"] + 10
               and (self.visible_types is None or r["typ"] in self.visible_types)
               and (self.visible_nrs is None or r["nr"] in self.visible_nrs)]
        if hit:
            hit.sort(key=lambda r: r["w"] * r["h"])
            self.regionClicked.emit(hit[0]["nr"])

    def in_selection(self, ix, iy):
        return any(r[0] <= ix <= r[2] and r[1] <= iy <= r[3] for r in self.sel_rects)

    def selected_anns(self):
        """Indizes aller gewaehlten Markierungen (Einzel- oder Mehrfachauswahl)."""
        sel = {k for k in self.ann_multi if 0 <= k < len(self.anns)}
        if self.ann_selected is not None and 0 <= self.ann_selected < len(self.anns):
            sel.add(self.ann_selected)
        return sel

    def _set_multi(self, chosen):
        chosen = sorted(chosen)
        self.ann_multi = set(chosen) if len(chosen) > 1 else set()
        self.ann_selected = chosen[-1] if chosen else None
        self.annMultiSelected.emit(chosen)
        self.update()

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
        if self.tool in ("polyline", "polygon") and self.poly:
            self.finish_poly()
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
        if self.float and k in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.floatDone.emit(k != Qt.Key.Key_Escape)
            return
        if self.float and k in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            d = 10 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1   # Pfeiltasten: pixelgenau schieben
            self.float["dx"] += {Qt.Key.Key_Left: -d, Qt.Key.Key_Right: d}.get(k, 0)
            self.float["dy"] += {Qt.Key.Key_Up: -d, Qt.Key.Key_Down: d}.get(k, 0)
            self.update()
            return
        if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.poly:
            self.finish_poly()
            return
        if k == Qt.Key.Key_Escape:
            self.poly, self._poly_hover, self._pen = [], None, None
            self.measure = []
            self._rubber = None
            self._ann_prev = None
            self._drag = None
            self.update()
            self.escapePressed.emit()
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.tool == "measure" and self.measure:
            self.finish_measure()
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.tool == "align":
            self.alignPoint.emit("done", 0.0, 0.0)
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
