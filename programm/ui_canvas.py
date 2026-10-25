"""Zeichenflaeche: Anzeige, Zoom, Messen, Anmerkungen."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403

from ui_canvas_geom import *  # noqa: F401,F403
from ui_canvas_snap import CanvasSnapMixin
from ui_canvas_paint import CanvasPaintMixin


# ----------------------------------------------------------------- Zeichenflaeche
class Canvas(CanvasSnapMixin, CanvasPaintMixin, QWidget):
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
    straightenLine = Signal(float, float, float, float)   # Kante nachgezeichnet (gerade ausrichten)
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
        self.coord_origin = None                     # Nullpunkt fuer Koordinaten (Bildpixel) oder None = Blattecke
        self.coord_editor = None                     # Eingabefeld fuer Laenge/Koordinaten beim Messen und Zeichnen
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
        self.preview_text = tr("Vergleich läuft …")
        self._snapshot = False               # view_image(): nur die Zeichnung mit Markierungen malen
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
        """Vorschau (verkleinerte Zeichnung A) waehrend der ersten Berechnung; Text darueber: preview_text."""
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
                self._drag = ("handle", name, (ix, iy))
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
        elif left and self.tool in ("rect", "arrow", "cloud", "highlight", "ellipse", "line", "redact", "pixelate",
                                    "straighten"):
            self._ann_prev = ((ix, iy), (ix, iy))
            self._drag = ("ann",)
        self.update()

    def _lost_release(self, e):
        """Maustaste ist nicht mehr gedrueckt, aber eine Zieh-Aktion laeuft noch: Das Loslassen hat ein Dialog oder
        Menue geschluckt. Schon begonnene Aenderungen (Verschieben, Groesse, Stift) regulaer abschliessen, alles andere
        (neue Markierung, Rahmen aufziehen) verwerfen - sonst klebt es am Mauszeiger."""
        if self._drag[0] in ("move", "handle", "zmove", "zhandle", "fhandle", "areamove", "float", "pen"):
            self.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, e.position(), e.globalPosition(),
                                               Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, e.modifiers()))
            return
        self._drag = self._rubber = self._ann_prev = None
        self.window().statusBar().clearMessage()
        self.update()

    def _shift_constrain(self, start, ix, iy):
        """Umschalt beim Zeichnen: Linie/Pfeil in 45-Grad-Schritten, Ellipse = Kreis, Rechteck/Rahmen = Quadrat."""
        ax, ay = start
        dx, dy = ix - ax, iy - ay
        if self.tool in ("line", "arrow"):
            r = math.hypot(dx, dy)
            ang = round(math.atan2(dy, dx) / (math.pi / 4)) * (math.pi / 4)
            return ax + r * math.cos(ang), ay + r * math.sin(ang)
        if self.tool in ("ellipse", "rect", "cloud"):
            m = max(abs(dx), abs(dy))
            return ax + math.copysign(m, dx or 1), ay + math.copysign(m, dy or 1)
        return ix, iy

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
        if self._drag is not None and e.buttons() == Qt.MouseButton.NoButton:
            self._lost_release(e)                         # Loslassen ging verloren (z. B. an einen Dialog)
            return
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
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                ix, iy = self._shift_constrain(self._ann_prev[0], ix, iy)
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
            mods = e.modifiers()
            if mods & Qt.KeyboardModifier.ShiftModifier:          # Umschalt: nur waagerecht oder senkrecht
                if abs(dx) >= abs(dy):
                    dy = 0
                else:
                    dx = 0
            if not mods & Qt.KeyboardModifier.AltModifier:        # Alt: ohne Einrasten an anderen Elementen
                boxes = [rep.ann_bounds(self.shape, o) for o in orig.values()]
                box = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                       max(b[2] for b in boxes), max(b[3] for b in boxes))
                dx, dy = self._align_snap(box, dx, dy, set(orig), lock_x=dx == 0 and dy != 0,
                                          lock_y=dy == 0 and dx != 0)
            for k, o in orig.items():
                if k < len(self.anns):
                    a = self.anns[k]
                    a["x"], a["y"], a["x2"], a["y2"] = o["x"] + dx, o["y"] + dy, o["x2"] + dx, o["y2"] + dy
                    if o.get("pts"):
                        a["pts"] = [[q[0] + dx, q[1] + dy] for q in o["pts"]]
        elif kind == "handle":
            mods = e.modifiers()
            if mods & Qt.KeyboardModifier.ShiftModifier:          # Umschalt: Ecke nur waagerecht oder senkrecht
                sx, sy = self._drag[2]
                if abs(ix - sx) >= abs(iy - sy):
                    iy = sy
                else:
                    ix = sx
            if self._drag[1].startswith("m"):
                ix, iy, _k = self.snap_point(ix, iy)
            elif not mods & Qt.KeyboardModifier.AltModifier:     # Kante/Ecke an anderen Elementen einrasten
                dx, dy = self._align_snap((ix, iy, ix, iy), 0, 0, {self.ann_selected})
                ix, iy = ix + dx, iy + dy
            apply_handle(self.shape, self.anns[self.ann_selected], self._drag[1], ix, iy)
        self.update()

    def _align_snap(self, box, dx, dy, skip, lock_x=False, lock_y=False):
        """Einrasten beim Verschieben: Kanten und Mitte des verschobenen Rahmens (box + dx/dy) an Kanten und Mitten
        der anderen Markierungen, wenn sie naeher als 6 Bildschirmpixel liegen. Merkt Hilfslinien zum Zeichnen.
        Rueckgabe: angepasstes (dx, dy)."""
        self._guides = []
        if not self.anns:
            return dx, dy
        tol = 6 / self.scale
        xs, ys = [], []
        for k, a in enumerate(self.anns):
            if k in skip or not self.ann_visible(a):
                continue
            x0, y0, x1, y1 = rep.ann_bounds(self.shape, a)
            xs += [x0, (x0 + x1) / 2, x1]
            ys += [y0, (y0 + y1) / 2, y1]
        if not xs:
            return dx, dy
        mine_x = [box[0] + dx, (box[0] + box[2]) / 2 + dx, box[2] + dx]
        mine_y = [box[1] + dy, (box[1] + box[3]) / 2 + dy, box[3] + dy]
        best = min(((t - m, t) for m in mine_x for t in xs), key=lambda v: abs(v[0]))
        if not lock_x and abs(best[0]) < tol:
            dx += best[0]
            self._guides.append(("v", best[1]))
        best = min(((t - m, t) for m in mine_y for t in ys), key=lambda v: abs(v[0]))
        if not lock_y and abs(best[0]) < tol:
            dy += best[0]
            self._guides.append(("h", best[1]))
        return dx, dy

    def _paint_guides(self, p):
        """Hilfslinien beim Einrasten an anderen Elementen (gestrichelt, Akzentfarbe)."""
        pen = QPen(QColor(ACCENT), 1, Qt.PenStyle.DashLine)
        p.setPen(pen)
        for kind, v in getattr(self, "_guides", []):
            if kind == "v":
                x = self.to_wid(v, 0)[0]
                p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
            else:
                y = self.to_wid(0, v)[1]
                p.drawLine(QPointF(0, y), QPointF(self.width(), y))

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
        self._guides = []
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
                if self.selected is not None:          # auch die gewaehlte Aenderung
                    self.regionClicked.emit(-1)
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
            if self.tool == "straighten":
                if abs(bx - ax) + abs(by - ay) > 8 / self.scale:
                    self.straightenLine.emit(ax, ay, bx, by)
            elif abs(bx - ax) + abs(by - ay) > 8 / self.scale:
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
            if self.selected is not None:                # ausgeblendete Rahmen: Auswahl trotzdem aufheben
                self.regionClicked.emit(-1)
            return
        hit = [r for r in self.regs if r["x"] - 10 <= ix <= r["x"] + r["w"] + 10
               and r["y"] - 10 <= iy <= r["y"] + r["h"] + 10
               and (self.visible_types is None or r["typ"] in self.visible_types)
               and (self.visible_nrs is None or r["nr"] in self.visible_nrs)]
        if hit:
            hit.sort(key=lambda r: r["w"] * r["h"])
            self.regionClicked.emit(hit[0]["nr"])
        elif self.selected is not None:                  # Klick ins Leere hebt auch die Aenderungs-Auswahl auf
            self.regionClicked.emit(-1)

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
        if (self.tool == "measure" or (self.tool in ("polyline", "polygon") and self.poly)) and e.text() and \
                e.text() in "0123456789-@.,<" and self.res is not None:
            self._open_coord_input(e.text())          # Laenge oder Koordinaten eintippen (wie im CAD)
            return
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
            if self.selected is not None:                # Esc: gewaehlte Aenderung abwaehlen (jedes Werkzeug)
                self.regionClicked.emit(-1)
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
