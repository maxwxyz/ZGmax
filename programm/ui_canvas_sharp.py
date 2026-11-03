"""Zeichenflaeche: PDF beim starken Hineinzoomen scharf zeigen. Teil von Canvas.

Die Zeichnung liegt als Bild in der eingestellten Aufloesung vor (Vergleichen, Messen und Markieren arbeiten darauf).
Ist sie sehr gross gezoomt, wuerde jedes Bildpixel nur vergroessert. Stammt die Zeichnung aus einer PDF/SVG und wird
sie unveraendert gezeigt (Ansicht Alt bzw. Einzelansicht, Original-Farben, ohne Bearbeitung und Linienfilter), rendert
diese Erweiterung nach kurzer Ruhe nur den sichtbaren Ausschnitt direkt aus der Datei in Bildschirmaufloesung und legt
ihn darueber. Am Vergleich und an den Koordinaten aendert das nichts.
"""
from ui_common import *  # noqa: F401,F403
from ui_canvas_geom import invert_view

SHARP_FROM = 1.25          # ab dieser Vergroesserung (Geraetepixel je Bildpixel) wird nachgerendert
SHARP_MAX_PX = 16_000_000  # hoechstens so viele Pixel je Ausschnitt (Speicher, Tempo)


class CanvasSharpMixin:
    """Wird in Canvas eingemischt. vector_src setzt das Hauptfenster: dict(path, page, dpi, off=(x, y), hidden=())
    oder None (kein scharfes Nachrendern)."""

    def _sharp_init(self):
        self.vector_src = None
        self._sharp = None                    # dict(key, rect=(x0, y0, x1, y1) Bildpixel, S, img=QImage)
        self._sharp_doc = None                # (Pfad, geoeffnetes Dokument)
        self._sharp_timer = QTimer(self)
        self._sharp_timer.setSingleShot(True)
        self._sharp_timer.setInterval(120)    # erst nach kurzer Ruhe (nicht bei jedem Schritt des Mausrads)
        self._sharp_timer.timeout.connect(self._sharp_render)
        self._sharp_want = None

    def set_vector_src(self, src):
        if src != self.vector_src:
            self.vector_src = src
            self._sharp = None
            if self._sharp_doc is not None and (src is None or src.get("path") != self._sharp_doc[0]):
                try:
                    self._sharp_doc[1].close()
                except Exception:              # noqa: BLE001
                    pass
                self._sharp_doc = None
            self.update()

    def _sharp_key(self):
        v = self.vector_src
        return (v["path"], v["page"], v["dpi"], tuple(v.get("off", (0, 0))), tuple(v.get("hidden", ()))) if v else None

    def _sharp_paint(self, p, m, S, vis):
        """Nach dem normalen Bild aufrufen: scharfen Ausschnitt darueberlegen bzw. anfordern."""
        if (self.vector_src is None or m != "A" or not self.show_color or S < SHARP_FROM
                or not self.layer_on.get("zeichnung", True)):
            return
        key = self._sharp_key()
        sh = self._sharp
        x0, y0, x1, y1 = vis
        if sh and sh["key"] == key and abs(sh["S"] - S) / S < 0.02 and sh["rect"][0] <= x0 and sh["rect"][1] <= y0 \
                and sh["rect"][2] >= x1 and sh["rect"][3] >= y1:
            rx0, ry0, rx1, ry1 = sh["rect"]
            s = self.scale
            img = sh["img"]
            if self.invert:
                img = sh.get("inv")
            p.drawImage(QRectF((rx0 - self.ox) * s, (ry0 - self.oy) * s, (rx1 - rx0) * s, (ry1 - ry0) * s), img)
            return
        self._sharp_want = (key, vis, S)
        self._sharp_timer.start()

    def _sharp_open(self, path):
        if self._sharp_doc is None or self._sharp_doc[0] != path:
            from pdfopen import open_doc
            self._sharp_doc = (path, open_doc(path))
        return self._sharp_doc[1]

    def _sharp_render(self):
        want, self._sharp_want = self._sharp_want, None
        v = self.vector_src
        if want is None or v is None or want[0] != self._sharp_key():
            return
        _key, (x0, y0, x1, y1), S = want
        h, w = self.shape
        mx, my = (x1 - x0) * 0.25, (y1 - y0) * 0.25            # Rand: kleines Verschieben ohne Neurendern
        x0, y0 = max(0.0, x0 - mx), max(0.0, y0 - my)
        x1, y1 = min(float(w), x1 + mx), min(float(h), y1 + my)
        if x1 <= x0 or y1 <= y0:
            return
        if (x1 - x0) * (y1 - y0) * S * S > SHARP_MAX_PX:        # zu gross: Rand weglassen bzw. Aufloesung begrenzen
            S = min(S, (SHARP_MAX_PX / ((x1 - x0) * (y1 - y0))) ** 0.5)
            if S < SHARP_FROM:
                return
        try:
            import pymupdf
            doc = self._sharp_open(v["path"])
            hide = set(v.get("hidden") or ())
            for c in doc.layer_ui_configs() or []:               # PDF-Ebenen wie beim normalen Laden
                if c.get("text") in hide and c.get("on"):
                    doc.set_layer_ui_config(c["number"], action=2)
            pg = doc[max(0, min(v["page"], doc.page_count) - 1)]
            k = 72.0 / v["dpi"]                                   # Bildpixel -> Punkt
            ox, oy = v.get("off", (0, 0))
            clip = pymupdf.Rect((x0 + ox) * k, (y0 + oy) * k, (x1 + ox) * k, (y1 + oy) * k) & pg.rect
            if clip.is_empty:
                return
            z = S * v["dpi"] / 72.0                               # Geraetepixel je Punkt
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=clip, alpha=False, colorspace=pymupdf.csRGB,
                                annots=False)
            rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.stride)[:, :pix.width * 3]
            bgr = np.ascontiguousarray(cv2.cvtColor(rgb.reshape(pix.height, pix.width, 3), cv2.COLOR_RGB2BGR))
        except Exception:                                         # noqa: BLE001 - nur Anzeige: dann eben unscharf
            log.exception("Scharfes Nachrendern")
            self.vector_src = None
            return
        rect = (clip.x0 / k - ox, clip.y0 / k - oy, clip.x1 / k - ox, clip.y1 / k - oy)
        inv = np.ascontiguousarray(invert_view(bgr, "A"))       # Farben umkehren wie im normalen Bild
        mk = lambda a: QImage(a.data, a.shape[1], a.shape[0], a.strides[0], QImage.Format.Format_BGR888).copy()  # noqa: E731
        self._sharp = dict(key=self._sharp_key(), rect=rect, S=S, img=mk(bgr), inv=mk(inv))
        self.update()
