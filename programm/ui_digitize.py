"""Diagramm digitalisieren (Bereich -> Mehr -> Diagramm digitalisieren …): Achsen kalibrieren, Kurven anklicken und
verfolgen lassen, Wertetabelle und angenaeherte Funktionen kopieren oder als CSV/Excel speichern. Kernlogik:
digitize.py.

Der Dialog ist sofort sichtbar: Bild bereinigen, Achsen suchen und Farben trennen laufen in einem Hintergrund-Thread
(numpy/OpenCV geben dabei die GIL frei), ebenso die Texterkennung der Achsbeschriftungen und das schaerfere Rendern
einer PDF-Quelle fuer die Anzeige. Ergebnisse holt ein Zeitgeber des Dialogs ab - schliesst der Dialog vorher, werden
sie verworfen."""
import copy
import threading

import cv2
import numpy as np
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QAbstractSpinBox, QApplication, QButtonGroup, QCheckBox, QComboBox,
                               QDialog, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsSimpleTextItem,
                               QGraphicsView, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QScrollArea,
                               QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTextEdit, QToolButton,
                               QVBoxLayout, QWidget)

import digitize as dg
from i18n import tr

COLORS = ["#e11d48", "#2563eb", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#db2777", "#65a30d"]
CALIB_KEYS = ("x1", "x2", "y1", "y2")
EXTEND_PX = 8                      # Kurvenenden unter Achsen/Gitter: so viele Pixel darf die Tabelle verlaengern
HIRES_MAX_SIDE = 6000              # schaerfere Anzeige einer PDF-Quelle: laengere Seite hoechstens so viele Pixel
_LAST = {}                         # Eingaben der letzten Digitalisierung (nur fuer diese Sitzung)


def _qimage(arr):
    """numpy Grau/BGR -> eigenstaendiges QImage."""
    arr = np.ascontiguousarray(arr)
    fmt = QImage.Format.Format_Grayscale8 if arr.ndim == 2 else QImage.Format.Format_BGR888
    return QImage(arr.data, arr.shape[1], arr.shape[0], arr.strides[0], fmt).copy()


def _num(text):
    """Zahl aus einem Eingabefeld (Komma oder Punkt) oder None."""
    t = (text or "").strip().replace(" ", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def nice_step(span, n=20):
    """Runde Schrittweite (1, 2, 5 * 10^k) fuer etwa n Schritte."""
    if not span or not np.isfinite(span) or span <= 0:
        return 1.0
    raw = span / n
    k = 10.0 ** np.floor(np.log10(raw))
    for m in (1, 2, 5, 10):
        if raw <= m * k * 1.0001:
            return float(m * k)
    return float(10 * k)


def trace_bounds(axes, width, x):
    """Spaltenbereich fuer das Verfolgen: innerhalb der erkannten Achsen, wenn der Klick dazwischen liegt."""
    lo, hi = 0, width - 1
    if axes.get("y_axis") and axes["y_axis"][0] < x:
        lo = int(axes["y_axis"][0])
    if axes.get("x_axis") and axes["x_axis"][2] > x and axes["x_axis"][1] <= lo + 3:
        hi = int(axes["x_axis"][2])
    return lo, hi


def prepare(img, text_size, color_traces=True):
    """Analyse beim Oeffnen (ohne Qt, im Hintergrund-Thread): Tinte, Linienmasken, Achsen, bereinigte Tinte,
    Farbebenen und - color_traces - die schon verfolgten farbigen Kurven [(Ebene, Punkte), ...]."""
    ink = dg.binarize(img)
    masks = dg.line_masks(ink)
    axes = dg.find_axes(ink, masks)
    clean, lines = dg.clean_from(ink, masks, text_size)
    layers = dg.color_layers(img)
    traces = []
    if color_traces:
        for k, layer in enumerate(layers):
            p = dg.layer_start(layer["mask"])
            if p is None:
                continue
            pts = dg.trace_curve(layer["mask"], p, bounds=trace_bounds(axes, ink.shape[1], p[0]))
            if len(pts) >= 10:
                traces.append((k, pts))
    return dict(ink=ink, masks=masks, axes=axes, clean=clean, lines=lines, layers=layers, traces=traces)


def axis_label_image(gray, axes, text_size):
    """Bild fuer die Texterkennung der Achsbeschriftungen: die Diagrammflaeche (rechts der y- und ueber der x-Achse)
    weiss - dort sucht auto_axes keine Zahlen, und jede Fundstelle weniger spart Erkennungszeit. Ganze Bildgroesse
    statt schmaler Streifen: die Texterkennung vergroessert jedes Bild auf mindestens 736 px an der kurzen Seite,
    Streifen waeren damit teurer als das ganze Bild."""
    xa, ya = axes.get("x_axis"), axes.get("y_axis")
    if not (xa and ya):
        return gray
    m = max(3, int(text_size) // 2)
    out = gray.copy()
    out[:max(0, int(xa[0]) - m), int(ya[0]) + m:] = 255
    return out


def _dedupe(items):
    """Doppelte Fundstellen (aus mehreren Durchlaeufen) nur einmal, die sicherere zuerst."""
    items = sorted(items, key=lambda t: -(float(t[5]) if len(t) > 5 else 0.0))
    keep = []
    for it in items:
        area = max(1.0, (it[2] - it[0]) * (it[3] - it[1]))
        if any(it[4] == k[4] and max(0.0, min(it[2], k[2]) - max(it[0], k[0]))
               * max(0.0, min(it[3], k[3]) - max(it[1], k[1])) > 0.5 * area for k in keep):
            continue
        keep.append(it)
    return keep


def render_hires(src, bbox, f, region, base, redact=()):
    """Ausschnitt bbox (Bildpixel der Zeichnung) direkt aus der PDF/SVG src (wie Canvas.vector_src) f-fach
    aufgeloest rendern, nur fuer die Anzeige. Ausserhalb der Auswahl (region) weiss, in Schwaerzungen (Rechtecke im
    Diagrammbild) das schon geschwaerzte Grundbild base. Liefert (BGR, x, y, Massstab): linke obere Ecke im
    Diagrammbild und Groesse eines Pixels in Diagrammpixeln - oder None."""
    import pymupdf
    from pdfopen import open_doc
    x0, y0, x1, y1 = bbox
    with open_doc(src["path"]) as doc:
        hide = set(src.get("hidden") or ())
        for c in doc.layer_ui_configs() or []:                    # PDF-Ebenen wie beim normalen Laden
            if c.get("text") in hide and c.get("on"):
                doc.set_layer_ui_config(c["number"], action=2)
        pg = doc[max(0, min(src["page"], doc.page_count) - 1)]
        k = 72.0 / src["dpi"]                                     # Bildpixel -> Punkt
        ox, oy = src.get("off", (0, 0))
        clip = pymupdf.Rect((x0 + ox) * k, (y0 + oy) * k, (x1 + ox) * k, (y1 + oy) * k) & pg.rect
        if clip.is_empty:
            return None
        z = f / k                                                 # Geraetepixel je Punkt
        pix = pg.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=clip, alpha=False, colorspace=pymupdf.csRGB,
                            annots=False)
        rgb = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.stride)[:, :pix.width * 3]
        bgr = np.ascontiguousarray(cv2.cvtColor(rgb.reshape(pix.height, pix.width, 3), cv2.COLOR_RGB2BGR))
        px0, py0 = pix.x, pix.y
    # Geraetepixel i <-> Punkt (px0 + i) / z <-> Zeichnungspixel (px0 + i) / f - ox <-> Diagrammpixel ... - x0
    sx, sy, sc = px0 / f - ox - x0, py0 / f - oy - y0, 1.0 / f
    h, w = base.shape[:2]
    cx = np.floor(sx + (np.arange(bgr.shape[1]) + 0.5) * sc).astype(int)
    cy = np.floor(sy + (np.arange(bgr.shape[0]) + 0.5) * sc).astype(int)
    out = ~(((cx >= 0) & (cx < w))[None, :] & ((cy >= 0) & (cy < h))[:, None])
    ix, iy = np.clip(cx, 0, w - 1), np.clip(cy, 0, h - 1)
    out |= ~region[np.ix_(iy, ix)]
    bgr[out] = 255
    if redact:
        m = np.zeros((h, w), bool)
        for a, b, c, d in redact:
            m[max(0, b):max(0, d), max(0, a):max(0, c)] = True
        mh = m[np.ix_(iy, ix)]
        if mh.any():
            up = base[np.ix_(iy, ix)]
            bgr[mh] = up[mh] if up.ndim == 3 else up[mh][:, None]
    return bgr, sx, sy, sc


class _Job:
    """Arbeit in einem Hintergrund-Thread; fn(job) darf job.progress (0..1) setzen. Ergebnis per done()/wait()."""

    def __init__(self, fn):
        self.result = self.error = None
        self.progress = 0.0
        self._t = threading.Thread(target=self._run, args=(fn,), daemon=True)
        self._t.start()

    def _run(self, fn):
        try:
            self.result = fn(self)
        except BaseException as e:                                   # noqa: BLE001 - wird im Dialog gemeldet
            self.error = e

    def done(self):
        return not self._t.is_alive()

    def wait(self):
        self._t.join()
        return self


class DiagramView(QGraphicsView):
    """Bildflaeche wie die Zeichenflaeche im Hauptfenster: Mausrad = zoomen um die Mausposition, Trackpad: zwei
    Finger verschieben, Aufziehen oder Strg+Rad zoomen; rechte oder mittlere Taste oder Leertaste + linke Taste ziehen
    = verschieben; linke Taste = Werkzeug."""

    pressed = Signal(QPointF)
    dragged = Signal(QPointF)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(420, 320)
        self.viewport().grabGesture(Qt.GestureType.PinchGesture)
        self.tool_cursor = Qt.CursorShape.ArrowCursor
        self._img = QRectF()
        self._pan = None
        self._left = False
        self._space = False
        self._fitted = True

    def set_image_rect(self, w, h):
        """Bildgroesse; die Szene ist rundum groesser, damit Zoomen um die Maus und Verschieben ueberall gehen."""
        self._img = QRectF(0, 0, w, h)
        m = 2.0 * max(w, h)
        self.scene().setSceneRect(-m, -m, w + 2 * m, h + 2 * m)

    def fit(self):
        """Ganzes Diagramm (mit schmalem Rand) einpassen."""
        r = self._img
        if r.isEmpty():
            return
        d = 0.03 * max(r.width(), r.height())
        self.fitInView(r.adjusted(-d, -d, d, d), Qt.AspectRatioMode.KeepAspectRatio)
        self._fitted = True

    def showEvent(self, e):
        super().showEvent(e)
        if self._fitted:
            QTimer.singleShot(0, self, self.fit)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._fitted:
            self.fit()

    def scale_factor(self):
        return max(1e-6, self.transform().m11())

    def fit_scale(self):
        r = self._img
        if r.isEmpty():
            return 1.0
        return min(self.viewport().width() / r.width(), self.viewport().height() / r.height())

    def to_scene(self, pos):
        """Viewport-Position -> Szenenpunkt (Diagrammpixel), ohne auf ganze Pixel zu runden."""
        return self.viewportTransform().inverted()[0].map(QPointF(pos))

    def zoom_at(self, factor, pos=None):
        """Um factor zoomen; der Bildpunkt unter pos (Viewport, Standard: Mitte) bleibt stehen."""
        if pos is None:
            pos = QPointF(self.viewport().width() / 2, self.viewport().height() / 2)
        pos = QPointF(pos)
        s = self.scale_factor()
        new = float(np.clip(s * factor, self.fit_scale() * 0.3, 40.0))
        if abs(new / s - 1) < 1e-9:
            return
        old = self.to_scene(pos)
        self.scale(new / s, new / s)
        now = self.viewportTransform().map(old)
        self.pan_by(pos.x() - now.x(), pos.y() - now.y())

    def pan_by(self, dx, dy):
        """Inhalt um dx, dy Bildschirmpixel verschieben."""
        h, v = self.horizontalScrollBar(), self.verticalScrollBar()
        h.setValue(h.value() - int(round(dx)))
        v.setValue(v.value() - int(round(dy)))
        self._fitted = False

    def wheelEvent(self, e):
        pdl, adl = e.pixelDelta(), e.angleDelta()
        zoom_mod = bool(e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        trackpad = not pdl.isNull() and e.phase() != Qt.ScrollPhase.NoScrollPhase
        if trackpad and not zoom_mod:
            self.pan_by(pdl.x(), pdl.y())
        else:
            steps = (pdl.y() / 60.0) if (trackpad and zoom_mod) else (adl.y() / 120.0)
            if steps:
                self.zoom_at(1.25 ** steps, e.position())
        e.accept()

    def viewportEvent(self, e):
        t = e.type()
        if t == QEvent.Type.NativeGesture:                          # Trackpad aufziehen (macOS)
            if e.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                self.zoom_at(1.0 + e.value(), e.position())
                return True
            if e.gestureType() == Qt.NativeGestureType.SmartZoomNativeGesture:
                self.fit()
                return True
        if t == QEvent.Type.Gesture:                                # Touch-Bildschirm
            g = e.gesture(Qt.GestureType.PinchGesture)
            if g is not None:
                c = self.viewport().mapFromGlobal(g.centerPoint().toPoint())
                self.zoom_at(g.scaleFactor(), QPointF(c))
                return True
        return super().viewportEvent(e)

    def set_tool_cursor(self, shape):
        self.tool_cursor = shape
        if self._pan is None and not self._space:
            self.viewport().setCursor(shape)

    def enterEvent(self, e):
        super().enterEvent(e)
        fw = QApplication.focusWidget()                             # Leertaste soll hier ankommen, ausser beim Tippen
        if not isinstance(fw, (QLineEdit, QAbstractSpinBox, QPlainTextEdit, QTextEdit)):
            self.setFocus()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space:
            if not e.isAutoRepeat():
                self._space = True
                self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            e.accept()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Space:
            if not e.isAutoRepeat():
                self._space = False
                if self._pan is None:
                    self.viewport().setCursor(self.tool_cursor)
            e.accept()
            return
        super().keyReleaseEvent(e)

    def focusOutEvent(self, e):
        if self._space:
            self._space = False
            self.viewport().setCursor(self.tool_cursor)
        super().focusOutEvent(e)

    def mousePressEvent(self, e):
        b = e.button()
        if b in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton) or (
                b == Qt.MouseButton.LeftButton and self._space):
            self._pan = e.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if b == Qt.MouseButton.LeftButton:
            self.setFocus()
            self._left = True
            self.pressed.emit(self.to_scene(e.position()))

    def mouseMoveEvent(self, e):
        if self._pan is not None:
            d = e.position() - self._pan
            self._pan = e.position()
            self.pan_by(d.x(), d.y())
            return
        if self._left:
            self.dragged.emit(self.to_scene(e.position()))

    def mouseReleaseEvent(self, e):
        if self._pan is not None:
            self._pan = None
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor if self._space else self.tool_cursor)
        self._left = False

    def mouseDoubleClickEvent(self, e):
        self.mousePressEvent(e)                                     # zweiter Klick wie ein einfacher (Punkte setzen)


def _marker(path, pos, pen=None, brush=None):
    """Markierung in Bildschirmpixeln (bleibt beim Zoomen gleich gross) an Szenenpunkt pos."""
    it = QGraphicsPathItem(path)
    it.setFlag(it.GraphicsItemFlag.ItemIgnoresTransformations)
    it.setPos(pos)
    it.setPen(pen if pen is not None else QPen(Qt.PenStyle.NoPen))
    if brush is not None:
        it.setBrush(brush)
    return it


class DigitizeDialog(QDialog):
    """Diagramm digitalisieren: img = Bildausschnitt (BGR oder Grau) des Diagramms.

    save_dialog(title, filter, default_name) -> Pfad (wie MainWindow._save_dialog), notify(text) fuer Meldungen im
    Hauptfenster, ocr(gray, ask, rots) -> Liste wie diffreport.ocr_any_orientation(gray, rots=rots) oder None
    (ask=False: nicht nach einer Installation fragen; wird im Hintergrund-Thread aufgerufen), ocr_ready(ask) -> bool:
    Texterkennung vorhanden (fragt bei ask nach der Installation; im GUI-Thread vor dem Lesen auf Knopfdruck),
    hires() -> Ergebnis von render_hires oder None (schaerfere Anzeige, im Hintergrund); alles optional. auto=True: farbige Kurven werden
    nach Farbe getrennt uebernommen und mit ocr die Achsen selbst kalibriert, sobald die Analyse fertig ist."""

    def __init__(self, parent, img, save_dialog=None, notify=None, ocr=None, auto=True, ocr_ready=None, hires=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Diagramm digitalisieren"))
        self.resize(1280, 820)
        self.img = img if img.ndim == 3 else cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        self.save_dialog, self.notify, self.ocr, self.ocr_ready = save_dialog, notify, ocr, ocr_ready
        self.auto = auto
        self.text_size = dg.default_text_size(self.img.shape)
        self._d = None                                    # Ergebnis von prepare (Analyse)
        self._hi = None                                   # schaerferes Anzeigebild (BGR, x, y, Massstab)
        self._hide = {}                                   # Masken "Gitter ausblenden" je Bildgroesse
        self._ocr_job = None
        self._ocr_auto = False
        self._ocr_result = None
        self.curves = []                                  # dict(name, color, pts (N, 2) Pixel)
        self.calib_pts = {k: None for k in CALIB_KEYS}
        self.calib_step = None
        self.mode = None
        self._undo = []
        self._step_auto = True
        self._items = []
        img_, ts = self.img, self.text_size
        self._prep = _Job(lambda job: prepare(img_, ts, auto))
        self._hires_job = _Job(lambda job: hires()) if hires is not None else None
        self._build()
        self._load_last()
        self.view.set_image_rect(self.img.shape[1], self.img.shape[0])
        self._show_image()
        self.set_mode("calib")
        self.start_calib()
        self._result_timer = QTimer(self, singleShot=True, interval=120, timeout=self.update_result)
        self.update_result()
        self._poll = QTimer(self, interval=40, timeout=self._poll_jobs)
        self._poll.start()
        self._update_busy()

    # ------------------------------------------------------------------------------------------ Analyse (Hintergrund)

    def _data(self):
        if self._d is None:
            self.wait_ready()
        return self._d

    ink = property(lambda self: self._data()["ink"])
    axes = property(lambda self: self._data()["axes"])
    clean = property(lambda self: self._data()["clean"])
    lines = property(lambda self: self._data()["lines"])
    layers = property(lambda self: self._data()["layers"])

    def wait_ready(self):
        """Auf die Analyse warten (sonst laeuft sie im Hintergrund) und ihr Ergebnis uebernehmen."""
        if self._d is not None:
            return
        job = self._prep.wait()
        if job.error is not None:
            raise job.error
        self._d = job.result
        self._after_prep()

    def _after_prep(self):
        layers = self._d["layers"]
        self.btn_colors.setText(tr("Farbige Kurven übernehmen ({})").format(len(layers)))
        self.btn_colors.setVisible(bool(layers))
        if self.chk_clean.isChecked() or self.chk_grid.isChecked():
            self._show_image()
        else:
            self._draw()
        if self.auto and self._d["traces"]:
            self.take_color_curves(self._d["traces"])
        self._update_busy()
        if self.auto and self.ocr is not None and all(self.calib_pts[k] is None for k in CALIB_KEYS):
            self._ocr_auto = True
            self.read_axes(ask=False)

    def _poll_jobs(self):
        busy = False
        if self._d is None:
            if self._prep.done():
                self.wait_ready()
            else:
                busy = True
        if self._hires_job is not None:
            if self._hires_job.done():
                job, self._hires_job = self._hires_job, None
                if job.error is None and job.result is not None:
                    self._hi = job.result
                    self._show_image()
            else:
                busy = True
        if self._ocr_job is not None:
            if self._ocr_job.done():
                self._ocr_finished()
            else:
                self.pb_auto.setValue(int(100 * self._ocr_job.progress))
                busy = True
        if not busy:
            self._poll.stop()
        self._update_busy()

    def _update_busy(self):
        if self._d is None:
            t = tr("Diagramm wird analysiert …")
        elif self._hires_job is not None:
            t = tr("Ansicht wird geschärft …")
        else:
            t = ""
        self.lbl_busy.setText(t)
        self.lbl_busy.setVisible(bool(t))
        self.pb_busy.setVisible(bool(t))

    def wait_jobs(self):
        """Alle Hintergrundarbeiten abwarten und uebernehmen (fuer Tests und Selbsttest)."""
        self.wait_ready()
        if self._hires_job is not None:
            self._hires_job.wait()
        if self._ocr_job is not None:
            self._ocr_job.wait()
        self._poll_jobs()

    # ------------------------------------------------------------------------------------------ Aufbau

    def _build(self):
        lay = QVBoxLayout(self)
        split = QSplitter(Qt.Orientation.Horizontal)
        lay.addWidget(split, 1)
        self.view = DiagramView()
        self.view.pressed.connect(lambda p: self.click((p.x() - 0.5, p.y() - 0.5)))
        self.view.dragged.connect(lambda p: self.drag((p.x() - 0.5, p.y() - 0.5)))
        self.pix_item = QGraphicsPixmapItem()
        self.pix_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.view.scene().addItem(self.pix_item)
        split.addWidget(self.view)

        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(6, 0, 6, 0)
        sl.addWidget(self._build_axes())
        sl.addWidget(self._build_curves())
        sl.addWidget(self._build_result(), 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(side)
        scroll.setMinimumWidth(max(460, side.minimumSizeHint().width() + 24))   # nie waagerecht abschneiden
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        split.addWidget(scroll)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        bottom = QHBoxLayout()
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("hint")
        self.lbl_status.setWordWrap(True)
        bottom.addWidget(self.lbl_status, 1)
        self.lbl_busy = QLabel()
        self.lbl_busy.setObjectName("hint")
        bottom.addWidget(self.lbl_busy)
        self.pb_busy = QProgressBar()
        self.pb_busy.setRange(0, 0)                       # laeuft, ohne Prozentangabe
        self.pb_busy.setMaximumWidth(120)
        self.pb_busy.setTextVisible(False)
        bottom.addWidget(self.pb_busy)
        b = QPushButton(tr("Ganzes Diagramm"))
        b.setToolTip(tr("Ansicht auf das ganze Diagramm einpassen. Mausrad oder Aufziehen = zoomen, rechte "
                        "Maustaste oder Leertaste + Ziehen = verschieben."))
        b.clicked.connect(self.view.fit)
        bottom.addWidget(b)
        close = QPushButton(tr("Schließen"))
        close.clicked.connect(self.close)
        bottom.addWidget(close)
        lay.addLayout(bottom)
        for b in self.findChildren(QPushButton):          # Eingabetaste in einem Feld loest keinen Knopf aus
            b.setAutoDefault(False)
            b.setDefault(False)

    def _build_axes(self):
        box = QGroupBox(tr("1. Achsen kalibrieren"))
        g = QGridLayout(box)
        hint = QLabel(tr("Je zwei Punkte auf der x- und der y-Achse anklicken (am besten an beschrifteten "
                         "Teilstrichen) und ihre Werte eintragen."))
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        g.addWidget(hint, 0, 0, 1, 4)
        names = {"x1": tr("x-Achse, Punkt 1"), "x2": tr("x-Achse, Punkt 2"),
                 "y1": tr("y-Achse, Punkt 1"), "y2": tr("y-Achse, Punkt 2")}
        self.btn_calib, self.ed_val, self.lbl_px = {}, {}, {}
        for r, k in enumerate(CALIB_KEYS, start=1):
            b = QPushButton(names[k])
            b.setCheckable(True)
            b.setToolTip(tr("Klicken, dann den Punkt im Diagramm anklicken"))
            b.clicked.connect(lambda _=False, k=k: self._pick(k))
            self.btn_calib[k] = b
            g.addWidget(b, r, 0)
            lbl = QLabel("–")
            lbl.setMinimumWidth(90)
            self.lbl_px[k] = lbl
            g.addWidget(lbl, r, 1)
            ed = QLineEdit()
            ed.setPlaceholderText(tr("Wert"))
            ed.textChanged.connect(self._changed)
            ed.returnPressed.connect(self.view.setFocus)    # weiter im Diagramm (naechster Punkt)
            self.ed_val[k] = ed
            g.addWidget(ed, r, 2, 1, 2)
        r = len(CALIB_KEYS) + 1
        self.ed_xname = QLineEdit()
        self.ed_xname.setPlaceholderText(tr("z. B. Weg s [mm]"))
        self.ed_yname = QLineEdit()
        self.ed_yname.setPlaceholderText(tr("z. B. Kraft F [N]"))
        self.chk_xlog = QCheckBox(tr("logarithmisch"))
        self.chk_ylog = QCheckBox(tr("logarithmisch"))
        for w in (self.ed_xname, self.ed_yname):
            w.textChanged.connect(self._changed)
        for w in (self.chk_xlog, self.chk_ylog):
            w.toggled.connect(self._changed)
        g.addWidget(QLabel(tr("x-Achse")), r, 0)
        g.addWidget(self.ed_xname, r, 1, 1, 2)
        g.addWidget(self.chk_xlog, r, 3)
        g.addWidget(QLabel(tr("y-Achse")), r + 1, 0)
        g.addWidget(self.ed_yname, r + 1, 1, 1, 2)
        g.addWidget(self.chk_ylog, r + 1, 3)
        self.chk_snap = QCheckBox(tr("An Achse und Teilstrichen einrasten"))
        self.chk_snap.setChecked(True)
        self.chk_snap.setToolTip(tr("Kalibrierpunkte rücken auf die erkannte Achse und den nächsten Teilstrich "
                                    "oder die nächste Gitterlinie."))
        g.addWidget(self.chk_snap, r + 2, 0, 1, 4)
        self.btn_auto = QPushButton(tr("Automatisch (Texterkennung)"))
        self.btn_auto.setToolTip(tr("Zahlen an den Achsen lesen und die Achsen daraus kalibrieren. Danach prüfen; "
                                    "einzelne Punkte lassen sich von Hand korrigieren."))
        self.btn_auto.clicked.connect(lambda: self.auto_calibrate(ask=True))
        self.btn_auto.setEnabled(self.ocr is not None)
        g.addWidget(self.btn_auto, r + 3, 0, 1, 2)
        self.lbl_auto = QLabel()
        self.lbl_auto.setWordWrap(True)
        self.lbl_auto.setObjectName("hint")
        g.addWidget(self.lbl_auto, r + 3, 2, 1, 2)
        self.pb_auto = QProgressBar()
        self.pb_auto.setRange(0, 100)
        self.pb_auto.setTextVisible(False)
        self.pb_auto.setMaximumHeight(8)
        self.pb_auto.setVisible(False)
        g.addWidget(self.pb_auto, r + 4, 0, 1, 4)
        return box

    def _build_curves(self):
        box = QGroupBox(tr("2. Kurven"))
        v = QVBoxLayout(box)
        hint = QLabel(tr("„Verfolgen“: eine Kurve dort anklicken, wo sie frei liegt – sie wird nach beiden Seiten "
                         "verfolgt, auch über Kreuzungen und Gitterlinien. Fehlt ein Stück, an anderer Stelle "
                         "noch einmal klicken oder Punkte von Hand setzen."))
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        v.addWidget(hint)
        self.list_curves = QListWidget()
        self.list_curves.setMaximumHeight(110)
        self.list_curves.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                         | QAbstractItemView.EditTrigger.EditKeyPressed
                                         | QAbstractItemView.EditTrigger.SelectedClicked)
        self.list_curves.setToolTip(tr("Doppelklick = umbenennen"))
        self.list_curves.itemChanged.connect(self._renamed)
        self.list_curves.currentRowChanged.connect(lambda _: self._draw())
        v.addWidget(self.list_curves)
        row = QHBoxLayout()
        b = QPushButton(tr("Neue Kurve"))
        b.clicked.connect(self._new_curve_clicked)
        row.addWidget(b)
        self.btn_clear = QPushButton(tr("Leeren"))
        self.btn_clear.setToolTip(tr("Alle Punkte der gewählten Kurve entfernen"))
        self.btn_clear.clicked.connect(self.clear_curve)
        row.addWidget(self.btn_clear)
        self.btn_del = QPushButton(tr("Löschen"))
        self.btn_del.clicked.connect(self.delete_curve)
        row.addWidget(self.btn_del)
        v.addLayout(row)
        self.btn_undo = QPushButton(tr("Rückgängig"))
        self.btn_undo.setShortcut("Ctrl+Z")
        self.btn_undo.clicked.connect(self.undo)
        self.btn_colors = QPushButton(tr("Farbige Kurven übernehmen ({})").format(0))
        self.btn_colors.setToolTip(tr("Je Farbe im Diagramm eine Kurve anlegen und verfolgen"))
        self.btn_colors.clicked.connect(lambda: self.take_color_curves())
        self.btn_colors.setVisible(False)                 # erst nach der Analyse, wenn es Farben gibt
        v.addWidget(self.btn_colors)
        row = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.btn_mode = {}
        for key, text, tip in (("trace", tr("Verfolgen"), tr("Kurve anklicken: wird automatisch verfolgt")),
                               ("add", tr("Punkt setzen"), tr("Jeder Klick setzt einen Punkt der gewählten Kurve")),
                               ("erase", tr("Radieren"), tr("Über Punkte der gewählten Kurve ziehen, um sie zu "
                                                            "entfernen"))):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            b.clicked.connect(lambda _=False, key=key: self.set_mode(key))
            self.mode_group.addButton(b)
            self.btn_mode[key] = b
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.btn_undo)
        v.addLayout(row)
        f = QFormLayout()
        self.chk_clean = QCheckBox(tr("Bereinigtes Bild zeigen (ohne Gitter und Text)"))
        self.chk_clean.toggled.connect(self._show_image)
        f.addRow(self.chk_clean)
        self.chk_grid = QCheckBox(tr("Gitter ausblenden"))
        self.chk_grid.setToolTip(tr("Gitterlinien in der Ansicht ausblenden (die Achsen bleiben). Am Verfolgen "
                                    "ändert das nichts."))
        self.chk_grid.toggled.connect(self._show_image)
        f.addRow(self.chk_grid)
        self.sp_text = QSpinBox()
        self.sp_text.setRange(0, 400)
        self.sp_text.setSuffix(" px")
        self.sp_text.setValue(self.text_size)
        self.sp_text.setToolTip(tr("Kleine Teile bis zu dieser Größe (Schrift, Ziffern) werden beim Verfolgen "
                                   "ignoriert; Striche gestrichelter Kurven bleiben erhalten. 0 = nichts entfernen."))
        self.sp_text.valueChanged.connect(self._text_size_changed)
        f.addRow(tr("Text ignorieren bis"), self.sp_text)
        v.addLayout(f)
        return box

    def _build_result(self):
        box = QGroupBox(tr("3. Wertetabelle und Funktionen"))
        v = QVBoxLayout(box)
        g = QGridLayout()
        self.rb_count = QRadioButton(tr("Anzahl Stützstellen"))
        self.rb_step = QRadioButton(tr("Schrittweite"))
        self.rb_count.setChecked(True)
        self.sp_count = QSpinBox()
        self.sp_count.setRange(2, 10000)
        self.sp_count.setValue(21)
        self.sp_step = QDoubleSpinBox()
        self.sp_step.setDecimals(6)
        self.sp_step.setRange(1e-6, 1e9)
        self.sp_step.setValue(1.0)
        self.sp_step.valueChanged.connect(self._step_edited)
        g.addWidget(self.rb_count, 0, 0)
        g.addWidget(self.sp_count, 0, 1)
        g.addWidget(self.rb_step, 1, 0)
        g.addWidget(self.sp_step, 1, 1)
        self.cb_decimal = QComboBox()
        self.cb_decimal.addItem(tr("Dezimalkomma (1,5)"), ",")
        self.cb_decimal.addItem(tr("Dezimalpunkt (1.5)"), ".")
        g.addWidget(QLabel(tr("Zahlen")), 2, 0)
        g.addWidget(self.cb_decimal, 2, 1)
        self.sp_deg = QSpinBox()
        self.sp_deg.setRange(1, 3)
        self.sp_deg.setValue(2)
        self.sp_deg.setToolTip(tr("Grad des angenäherten Polynoms (1 = Gerade, z. B. Federrate)"))
        g.addWidget(QLabel(tr("Polynomgrad")), 3, 0)
        g.addWidget(self.sp_deg, 3, 1)
        self.cb_values = QComboBox()
        self.cb_values.addItem(tr("Gemessen (interpoliert)"), "raw")
        self.cb_values.addItem(tr("Glatte Kurve (Spline)"), "smooth")
        self.cb_values.addItem(tr("Polynom (Ausgleich)"), "poly")
        self.cb_values.setToolTip(tr("Welche Werte in Tabelle, CSV und Excel stehen: die verfolgten Punkte, eine "
                                     "geglättete Kurve oder das angenäherte Polynom"))
        g.addWidget(QLabel(tr("Werte")), 4, 0)
        g.addWidget(self.cb_values, 4, 1)
        self.sp_knots = QSpinBox()
        self.sp_knots.setRange(3, 60)
        self.sp_knots.setValue(10)
        self.sp_knots.setToolTip(tr("Stützpunkte der glatten Kurve: weniger = glatter, mehr = näher an den Punkten"))
        self.lbl_knots = QLabel(tr("Glättung (Stützpunkte)"))
        g.addWidget(self.lbl_knots, 5, 0)
        g.addWidget(self.sp_knots, 5, 1)
        for w in (self.rb_count, self.rb_step):
            w.toggled.connect(self._changed)
        for w in (self.sp_count, self.sp_step, self.sp_deg, self.sp_knots):
            w.valueChanged.connect(self._changed)
        self.cb_decimal.currentIndexChanged.connect(self._changed)
        self.cb_values.currentIndexChanged.connect(self._changed)
        v.addLayout(g)
        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(160)
        v.addWidget(self.table, 1)
        self.txt_fit = QPlainTextEdit()
        self.txt_fit.setReadOnly(True)
        self.txt_fit.setMaximumHeight(110)
        v.addWidget(self.txt_fit)
        row = QHBoxLayout()
        self.btn_copy = QPushButton(tr("Tabelle kopieren"))
        self.btn_copy.setObjectName("primary")
        self.btn_copy.setToolTip(tr("Mit Tabulatoren, zum Einfügen in eine Tabellenkalkulation"))
        self.btn_copy.clicked.connect(self.copy_table)
        row.addWidget(self.btn_copy)
        self.btn_save = QPushButton(tr("CSV speichern …"))
        self.btn_save.clicked.connect(self.save_csv)
        row.addWidget(self.btn_save)
        self.btn_xlsx = QPushButton(tr("Excel speichern …"))
        self.btn_xlsx.setToolTip(tr("Wertetabelle mit fertigem Diagramm als Excel-Datei (.xlsx); die Polynome "
                                    "stehen mit ihren Koeffizienten als Formeln daneben und rechnen live mit."))
        self.btn_xlsx.clicked.connect(lambda: self.save_xlsx())
        v.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(self.btn_xlsx)
        self.btn_fn = QPushButton(tr("Funktionen kopieren"))
        self.btn_fn.clicked.connect(self.copy_functions)
        row.addWidget(self.btn_fn)
        v.addLayout(row)
        return box

    def _load_last(self):
        """Achsennamen und Ausgabe-Einstellungen der letzten Digitalisierung (diese Sitzung) uebernehmen."""
        if not _LAST:
            return
        self.ed_xname.setText(_LAST.get("xname", ""))
        self.ed_yname.setText(_LAST.get("yname", ""))
        self.cb_decimal.setCurrentIndex(max(0, self.cb_decimal.findData(_LAST.get("decimal", ","))))
        self.sp_deg.setValue(_LAST.get("deg", 2))
        self.cb_values.setCurrentIndex(max(0, self.cb_values.findData(_LAST.get("values", "raw"))))
        self.sp_knots.setValue(_LAST.get("knots", 10))

    def closeEvent(self, e):
        self._poll.stop()
        _LAST.update(xname=self.ed_xname.text(), yname=self.ed_yname.text(),
                     decimal=self.cb_decimal.currentData(), deg=self.sp_deg.value(),
                     values=self.cb_values.currentData(), knots=self.sp_knots.value())
        super().closeEvent(e)

    # ------------------------------------------------------------------------------------------ Bild und Overlays

    def _grid_mask(self, shape=None):
        """Maske "Gitter ausblenden" (uint8) in Diagrammpixeln oder fuer das schaerfere Anzeigebild (shape):
        Linien ohne Achsen und ohne die Umgebung der Kurven (Kreuzungen bleiben geschlossen)."""
        key = None if shape is None else tuple(shape[:2])
        if key in self._hide:
            return self._hide[key]
        if shape is None:
            d = self._data()
            hide = d["lines"].copy()
            mh, mv = d["masks"]
            ax = d["axes"]
            if ax.get("x_axis"):
                a, b = dg.line_band(mh, ax["x_axis"][0], True)
                hide[a:b + 1, :][mh[a:b + 1, :] > 0] = 0
            if ax.get("y_axis"):
                a, b = dg.line_band(mv, ax["y_axis"][0], False)
                hide[:, a:b + 1][mv[:, a:b + 1] > 0] = 0
            # Kurven, die eine Linie kreuzen: quer zur Linie laufende Tinte (ohne die Linien der anderen Richtung)
            ink = d["ink"]
            hide[(mv > 0) & (cv2.morphologyEx(ink & ~mh, cv2.MORPH_OPEN, np.ones((1, 5), np.uint8)) > 0)] = 0
            hide[(mh > 0) & (cv2.morphologyEx(ink & ~mv, cv2.MORPH_OPEN, np.ones((5, 1), np.uint8)) > 0)] = 0
            hide[cv2.dilate(d["clean"], np.ones((3, 3), np.uint8)) > 0] = 0
            # schmale Luecken, die das Ausblenden in Kurven riss (steile Kreuzungen), wieder schliessen
            vis = ink & ~hide
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
            hide[cv2.morphologyEx(vis, cv2.MORPH_CLOSE, k) > 0] = 0
            if ax.get("x_axis") and ax.get("y_axis"):    # nur in der Diagrammflaeche (Beschriftung bleibt ganz)
                inner = np.zeros_like(hide)
                inner[int(ax["y_axis"][1]):int(ax["x_axis"][0]) + 1, int(ax["y_axis"][0]):int(ax["x_axis"][2]) + 1] = 1
                hide &= inner * 255
        else:
            base = self._grid_mask()
            _, sx, sy, sc = self._hi
            h, w = base.shape
            ix = np.clip(np.floor(sx + (np.arange(shape[1]) + 0.5) * sc).astype(int), 0, w - 1)
            iy = np.clip(np.floor(sy + (np.arange(shape[0]) + 0.5) * sc).astype(int), 0, h - 1)
            n = max(3, int(round(1.0 / sc)) | 1)              # Kantenglaettung der Linien mit abdecken
            hide = cv2.dilate(np.ascontiguousarray(base[np.ix_(iy, ix)]), np.ones((n, n), np.uint8))
        self._hide[key] = hide
        return hide

    def _show_image(self):
        if self.chk_clean.isChecked():
            show = np.full(self.ink.shape, 255, np.uint8)
            if not self.chk_grid.isChecked():
                show[self.lines > 0] = 215                # entfernte Linien blass
            show[self.clean > 0] = 0
            pos, sc = (0.0, 0.0), 1.0
        else:
            src, sx, sy, sc = self._hi if self._hi is not None else (self.img, 0.0, 0.0, 1.0)
            pos = (sx, sy)
            show = src
            if self.chk_grid.isChecked():
                show = src.copy()
                show[self._grid_mask(None if self._hi is None else src.shape) > 0] = 255
        self.pix_item.setPixmap(QPixmap.fromImage(_qimage(show)))
        self.pix_item.setPos(*pos)
        self.pix_item.setScale(sc)
        self._draw()

    def _draw(self):
        """Achsen, Kalibrierpunkte und Kurven neu zeichnen (Markierungen in Bildschirmpixeln, zoomfest)."""
        sc = self.view.scene()
        for it in self._items:
            sc.removeItem(it)
        self._items = []

        def add(it):
            sc.addItem(it)
            self._items.append(it)
            return it

        ax = self._d["axes"] if self._d is not None else {}
        pen = QPen(QColor("#06b6d4"), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        if ax.get("x_axis"):
            y, x0, x1 = ax["x_axis"]
            p = QPainterPath(QPointF(x0, y + 0.5))
            p.lineTo(x1 + 1, y + 0.5)
            add(QGraphicsPathItem(p)).setPen(pen)
        if ax.get("y_axis"):
            x, y0, y1 = ax["y_axis"]
            p = QPainterPath(QPointF(x + 0.5, y0))
            p.lineTo(x + 0.5, y1 + 1)
            add(QGraphicsPathItem(p)).setPen(pen)
        cur = self.list_curves.currentRow() if hasattr(self, "list_curves") else -1
        dot = QPainterPath()
        dot.addEllipse(QPointF(0, 0), 3.0, 3.0)
        for k, c in enumerate(self.curves):
            pts = c["pts"]
            if not len(pts):
                continue
            pen = QPen(QColor(c["color"]), 3.5 if k == cur else 2)
            pen.setCosmetic(True)
            path = QPainterPath(QPointF(pts[0][0] + 0.5, pts[0][1] + 0.5))
            prev = pts[0][0]
            for x, y in pts[1:]:
                if x - prev > 3:                          # Luecke (nicht verfolgt): nicht verbinden
                    path.moveTo(x + 0.5, y + 0.5)
                else:
                    path.lineTo(x + 0.5, y + 0.5)
                prev = x
            it = add(QGraphicsPathItem(path))
            it.setPen(pen)
            if len(pts) <= 80:                            # wenige Punkte (von Hand): Punkte zeigen
                brush = QBrush(QColor(c["color"]))
                for x, y in pts:
                    add(_marker(dot, QPointF(x + 0.5, y + 0.5), brush=brush))
        f = QFont()
        f.setBold(True)
        col = QColor("#ea580c")
        cross = QPainterPath(QPointF(-8, 0))
        cross.lineTo(8, 0)
        cross.moveTo(0, -8)
        cross.lineTo(0, 8)
        for k in CALIB_KEYS:
            p = self.calib_pts[k]
            if p is None:
                continue
            pen = QPen(col, 2)
            pen.setCosmetic(True)
            m = add(_marker(cross, QPointF(p[0] + 0.5, p[1] + 0.5), pen))
            m.setZValue(10)
            t = QGraphicsSimpleTextItem(k, m)             # Beschriftung in Bildschirmpixeln neben dem Kreuz:
            t.setFont(f)                                  # x unten rechts, y oben links (fallen x1/y1 im
            t.setBrush(QBrush(col))                       # Ursprung zusammen, bleiben beide lesbar)
            r = t.boundingRect()
            t.setPos(QPointF(5, 4) if k[0] == "x" else QPointF(-6 - r.width(), -4 - r.height()))
            m.setToolTip(f"{k}: {p[0]:.1f}, {p[1]:.1f} px")

    def _text_size_changed(self, v):
        self.text_size = v
        d = self._data()
        d["clean"], d["lines"] = dg.clean_from(d["ink"], d["masks"], v)
        self._hide = {}
        self._show_image()

    # ------------------------------------------------------------------------------------------ Bedienung

    def set_mode(self, mode):
        self.mode = mode
        for k, b in self.btn_mode.items():
            b.setChecked(k == mode)
        if mode != "calib":
            self.calib_step = None
            for b in self.btn_calib.values():
                b.setChecked(False)
        self.view.set_tool_cursor(Qt.CursorShape.CrossCursor if mode else Qt.CursorShape.ArrowCursor)
        self._hint()

    def start_calib(self):
        """Kalibrierpunkte der Reihe nach setzen (beginnt beim ersten fehlenden)."""
        missing = [k for k in CALIB_KEYS if self.calib_pts[k] is None]
        self._pick(missing[0] if missing else "x1")

    def _pick(self, key):
        self.set_mode("calib")
        self.calib_step = key
        for k, b in self.btn_calib.items():
            b.setChecked(k == key)
        self._hint()

    def _hint(self):
        if self.mode == "calib" and self.calib_step:
            names = {"x1": tr("ersten Punkt auf der x-Achse"), "x2": tr("zweiten Punkt auf der x-Achse"),
                     "y1": tr("ersten Punkt auf der y-Achse"), "y2": tr("zweiten Punkt auf der y-Achse")}
            t = tr("Den {} anklicken.").format(names[self.calib_step])
        elif self.mode == "trace":
            t = tr("Eine Kurve anklicken, wo sie frei liegt (nicht an einer Kreuzung).")
        elif self.mode == "add":
            t = tr("Klicks setzen Punkte der gewählten Kurve.")
        elif self.mode == "erase":
            t = tr("Über Punkte ziehen, um sie zu entfernen.")
        else:
            t = ""
        self.lbl_status.setText(t + "  " + tr("Mausrad oder Aufziehen = zoomen, rechte Maustaste oder Leertaste + "
                                              "Ziehen = verschieben."))

    def click(self, p):
        """Linksklick an Bildpunkt p = (x, y) in Pixeln des Diagramms (auch fuer Tests)."""
        h, w = self.img.shape[:2]
        if not (-2 <= p[0] <= w + 1 and -2 <= p[1] <= h + 1):
            return
        if self.mode == "calib" and self.calib_step:
            self._set_calib(self.calib_step, p)
        elif self.mode == "trace":
            self._trace(p)
        elif self.mode == "add":
            c = self._current(create=True)
            self._push()
            pts = np.vstack([c["pts"], [p]])
            c["pts"] = pts[np.argsort(pts[:, 0], kind="stable")]
            self._curve_changed()
        elif self.mode == "erase":
            self._push()
            self._erase(p)

    def drag(self, p):
        if self.mode == "erase":
            self._erase(p)

    def _set_calib(self, key, p):
        x, y = float(p[0]), float(p[1])
        ax = self.axes
        if self.chk_snap.isChecked():
            if key[0] == "x" and ax.get("x_axis"):
                ay, a, b = ax["x_axis"]
                y = ay
                s = dg.snap_line(ax["vlines"], x)
                x = s if s is not None else dg.snap_tick(self.ink, ay, (a, b), x, True)
            elif key[0] == "y" and ax.get("y_axis"):
                axx, a, b = ax["y_axis"]
                x = axx
                s = dg.snap_line(ax["hlines"], y)
                y = s if s is not None else dg.snap_tick(self.ink, axx, (a, b), y, False)
        self._ocr_auto = False                            # von Hand gesetzt: Texterkennung beim Oeffnen nicht drueber
        self.calib_pts[key] = (x, y)
        self.lbl_px[key].setText(f"{x:.0f}, {y:.0f} px")
        self.ed_val[key].setFocus()
        self.ed_val[key].selectAll()
        missing = [k for k in CALIB_KEYS if self.calib_pts[k] is None]
        if missing:
            self._pick(missing[0])
        else:
            self.calib_step = None
            for b in self.btn_calib.values():
                b.setChecked(False)
            self.lbl_status.setText(tr("Achsenpunkte gesetzt. Werte eintragen, dann mit „Verfolgen“ die Kurven "
                                       "anklicken."))
        self._draw()
        self._changed()

    def _bounds(self, x):
        return trace_bounds(self.axes, self.img.shape[1], x)

    def _trace(self, p):
        k = dg.layer_at(self.layers, p) if self.layers else None
        if k is not None:                                  # farbige Kurve: nur Pixel dieser Farbe verfolgen
            pts = dg.trace_curve(self.layers[k]["mask"], p, bounds=self._bounds(p[0]))
        else:
            pts = dg.trace_curve(self.clean, p, self.lines, bounds=self._bounds(p[0]))
        if len(pts) < 2:
            self.lbl_status.setText(tr("Hier wurde keine Linie gefunden. Näher an die Kurve klicken oder „Text "
                                       "ignorieren bis“ verkleinern."))
            return
        c = self._current(create=True)
        self._push()
        if k is not None and not len(c["pts"]):            # neue Kurve bekommt die Farbe aus dem Diagramm
            c["color"] = self._hex(self.layers[k]["color"])
            row = self.curves.index(c)
            self._sync_list()
            self.list_curves.setCurrentRow(row)
        c["pts"] = dg.merge_points(c["pts"], pts)
        self._curve_changed()
        self.lbl_status.setText(tr("{}: {} Punkte verfolgt. Nächste Kurve: „Neue Kurve“, dann anklicken.").format(
            c["name"], len(pts)))

    @staticmethod
    def _hex(bgr):
        return "#{:02x}{:02x}{:02x}".format(bgr[2], bgr[1], bgr[0])

    def take_color_curves(self, traces=None):
        """Je Farbebene eine Kurve anlegen und vom laengsten Stueck aus verfolgen; liefert die Anzahl. traces:
        schon verfolgte Kurven [(Ebene, Punkte), ...] (aus der Analyse im Hintergrund)."""
        layers = self.layers
        if traces is None:
            traces = []
            for k, layer in enumerate(layers):
                p = dg.layer_start(layer["mask"])
                if p is None:
                    continue
                pts = dg.trace_curve(layer["mask"], p, bounds=self._bounds(p[0]))
                if len(pts) >= 10:
                    traces.append((k, pts))
        n = 0
        for k, pts in traces:
            col = self._hex(layers[k]["color"])
            if any(c["color"] == col for c in self.curves):
                continue                                   # diese Farbe gibt es schon
            c = self.new_curve()
            c["color"] = col
            c["pts"] = pts
            n += 1
        if n:
            self._sync_list()
            self.list_curves.setCurrentRow(len(self.curves) - 1)
            self._curve_changed()
            self.lbl_status.setText(tr("{} farbige Kurven übernommen. Fehlt ein Stück, mit „Verfolgen“ an der "
                                       "Stelle klicken.").format(n))
        return n

    def read_axes(self, ask=True):
        """Achsbeschriftungen im Hintergrund lesen; danach kalibriert auto_calibrate. Zuerst nur waagerechte Schrift
        (ein Durchlauf statt drei); senkrechte nur, wenn damit nicht beide Achsen erkannt werden. Liefert False, wenn
        keine Texterkennung moeglich ist, sonst None (laeuft)."""
        if self.ocr is None or self._ocr_job is not None:
            return False
        if ask and self.ocr_ready is not None:
            if not self.ocr_ready(True):                  # fragt nach der Installation (im GUI-Thread)
                return False
            call_ask = False
        else:
            call_ask = ask if self.ocr_ready is None else False
        ink, axes = self.ink, self.axes
        gray = axis_label_image(cv2.cvtColor(self.img, cv2.COLOR_BGR2GRAY), axes, self.text_size)
        f = 2 if max(gray.shape) < 1400 else 1            # kleine Ausschnitte vergroessert lesen
        big = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC) if f > 1 else gray
        big = np.ascontiguousarray(big)                   # hier vergroessern: OpenCV nicht neben der Texterkennung
        ocr = self.ocr

        def read(rots):
            res = ocr(big, call_ask, rots)
            if res is None:
                return None
            return [(it[0] / f, it[1] / f, it[2] / f, it[3] / f) + tuple(it[4:]) for it in res]

        def work(job):
            items = read((0,))
            if items is None:
                return None
            job.progress = 0.5
            res = dg.auto_axes(ink, items, axes)
            if "x1" not in res or "y1" not in res:        # senkrechte Beschriftungen nur bei Bedarf lesen
                more = read((1, 3))
                items = _dedupe(items + (more or []))
            job.progress = 1.0
            return items
        self._ocr_job = _Job(work)
        self.lbl_auto.setText(tr("Lese Achsbeschriftungen …"))
        self.pb_auto.setValue(0)
        self.pb_auto.setVisible(True)
        self.btn_auto.setEnabled(False)
        self._poll.start()
        return None

    def _ocr_finished(self):
        job, self._ocr_job = self._ocr_job, None
        self.pb_auto.setVisible(False)
        self.btn_auto.setEnabled(self.ocr is not None)
        auto, self._ocr_auto = self._ocr_auto, False
        if job.error is not None:
            self.lbl_auto.setText(tr("Texterkennung fehlgeschlagen: {}").format(job.error))
            self._ocr_result = False
        elif job.result is None:
            self.lbl_auto.setText("")
            self._ocr_result = False
        elif auto and any(self.calib_pts[k] is not None for k in CALIB_KEYS):
            self.lbl_auto.setText("")                     # inzwischen von Hand kalibriert: nichts ueberschreiben
            self._ocr_result = False
        else:
            self._ocr_result = self.auto_calibrate(job.result)
        return self._ocr_result

    def wait_ocr(self):
        """Auf die laufende Texterkennung warten; liefert, ob beide Achsen kalibriert wurden (fuer Tests)."""
        if self._ocr_job is not None:
            self._ocr_job.wait()
            return self._ocr_finished()
        return bool(self._ocr_result)

    def auto_calibrate(self, items=None, ask=True):
        """Achsen aus den gelesenen Beschriftungen kalibrieren. items: Ergebnis der Texterkennung; ohne items wird
        die Texterkennung im Hintergrund gestartet (Ergebnis spaeter, siehe wait_ocr) und None geliefert. Sonst
        True, wenn beide Achsen kalibriert wurden."""
        if items is None:
            return self.read_axes(ask)
        res = dg.auto_axes(self.ink, items, self.axes)
        done = []
        for ax, keys, log_box in (("x", ("x1", "x2"), self.chk_xlog), ("y", ("y1", "y2"), self.chk_ylog)):
            if keys[0] not in res:
                continue
            for k in keys:
                (px, py), v = res[k]
                self.calib_pts[k] = (float(px), float(py))
                self.lbl_px[k].setText(f"{px:.0f}, {py:.0f} px")
                self.ed_val[k].setText(dg.fmt_num(v, self.cb_decimal.currentData() or ","))
            log_box.setChecked(bool(res[ax + "log"]))
            done.append(ax)
        if done == ["x", "y"]:
            self.lbl_auto.setText(tr("Aus {} + {} Beschriftungen kalibriert – bitte prüfen.").format(
                res["nx"], res["ny"]))
            self.set_mode("trace")
            if not self.curves:
                self.lbl_status.setText(tr("Achsen kalibriert. Jetzt die Kurven anklicken."))
        elif done:
            self.lbl_auto.setText(tr("Nur die {}-Achse erkannt; die andere von Hand kalibrieren.").format(done[0]))
            self.start_calib()
        else:
            self.lbl_auto.setText(tr("Keine Achsbeschriftungen erkannt – bitte von Hand kalibrieren."))
        self._draw()
        self._changed()
        return done == ["x", "y"]

    def _erase(self, p):
        c = self._current()
        if c is None or not len(c["pts"]):
            return
        r = max(3.0, 10.0 / self.view.scale_factor())
        d = np.hypot(c["pts"][:, 0] - p[0], c["pts"][:, 1] - p[1])
        if (d <= r).any():
            c["pts"] = c["pts"][d > r]
            self._curve_changed()

    def _current(self, create=False):
        k = self.list_curves.currentRow()
        if 0 <= k < len(self.curves):
            return self.curves[k]
        if create:
            self.new_curve()
            return self.curves[-1]
        return None

    def new_curve(self, name=None):
        k = len(self.curves)
        used = {c["color"] for c in self.curves}
        color = next((c for c in COLORS if c not in used), COLORS[k % len(COLORS)])
        nums = [int(c["name"].split()[-1]) for c in self.curves
                if c["name"].startswith(tr("Kurve") + " ") and c["name"].split()[-1].isdigit()]
        name = name or tr("Kurve") + f" {max(nums + [k]) + 1}"
        self._push()
        self.curves.append(dict(name=name, color=color, pts=np.zeros((0, 2))))
        self._sync_list()
        self.list_curves.setCurrentRow(k)
        return self.curves[-1]

    def _new_curve_clicked(self):
        self.new_curve()
        self.set_mode("trace")

    def clear_curve(self):
        c = self._current()
        if c is not None and len(c["pts"]):
            self._push()
            c["pts"] = np.zeros((0, 2))
            self._curve_changed()

    def delete_curve(self):
        k = self.list_curves.currentRow()
        if 0 <= k < len(self.curves):
            self._push()
            del self.curves[k]
            self._sync_list()
            self.list_curves.setCurrentRow(min(k, len(self.curves) - 1))
            self._curve_changed()

    def _push(self):
        self._undo.append(copy.deepcopy(self.curves))
        del self._undo[:-50]

    def undo(self):
        if not self._undo:
            return
        k = self.list_curves.currentRow()
        self.curves = self._undo.pop()
        self._sync_list()
        self.list_curves.setCurrentRow(min(max(k, 0), len(self.curves) - 1))
        self._curve_changed()

    def _sync_list(self):
        self.list_curves.blockSignals(True)
        self.list_curves.clear()
        for c in self.curves:
            it = QListWidgetItem(c["name"])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
            pm = QPixmap(14, 14)
            pm.fill(QColor(c["color"]))
            it.setIcon(pm)
            self.list_curves.addItem(it)
        self.list_curves.blockSignals(False)

    def _renamed(self, it):
        k = self.list_curves.row(it)
        if 0 <= k < len(self.curves):
            name = it.text().strip() or self.curves[k]["name"]
            self.curves[k]["name"] = name
            self._changed()

    def _curve_changed(self):
        self._draw()
        self._changed()

    def _step_edited(self):
        if not getattr(self, "_setting_step", False):
            self._step_auto = False

    def _changed(self, *_):
        if hasattr(self, "_result_timer"):
            self._result_timer.start()

    # ------------------------------------------------------------------------------------------ Ergebnis

    def calib(self):
        """Kalibrierung aus Klicks und Werten oder None (unvollstaendig/ungueltig)."""
        if any(self.calib_pts[k] is None for k in CALIB_KEYS):
            return None
        v = {k: _num(self.ed_val[k].text()) for k in CALIB_KEYS}
        if any(x is None for x in v.values()):
            return None
        try:
            return dg.Calib(self.calib_pts["x1"], v["x1"], self.calib_pts["x2"], v["x2"],
                            self.calib_pts["y1"], v["y1"], self.calib_pts["y2"], v["y2"],
                            self.chk_xlog.isChecked(), self.chk_ylog.isChecked())
        except ValueError:
            return None

    def names(self):
        return (self.ed_xname.text().strip() or "x", self.ed_yname.text().strip() or "y")

    def curve_values(self, cal=None):
        cal = cal or self.calib()
        if cal is None:
            return []
        return [dg.to_values(c["pts"], cal) for c in self.curves]

    def _extend(self, cal):
        """Zugabe an den Kurvenenden in x-Werten (EXTEND_PX Pixel; bei logarithmischer x-Achse keine)."""
        if cal.ax.log:
            return 0.0
        a, b = np.asarray(self.calib_pts["x1"], float), np.asarray(self.calib_pts["x2"], float)
        d = np.linalg.norm(b - a)
        return abs(cal.ax.v2 - cal.ax.v1) / d * EXTEND_PX if d > 0 else 0.0

    def result(self):
        """(xs, Tabelle, Kopf) oder None; xs aufsteigend, auch wenn die x-Achse im Bild fallende Werte hat."""
        cal = self.calib()
        if cal is None:
            return None
        vals = self.curve_values(cal)
        if not any(len(v) for v in vals):
            return None
        ext = self._extend(cal)
        if self.rb_step.isChecked():
            try:
                xs = dg.make_xs(vals, step=self.sp_step.value(), extend=ext)
            except ValueError:
                return None
        else:
            xs = dg.make_xs(vals, count=self.sp_count.value(), extend=ext)
        how = self.cb_values.currentData()
        if how == "smooth":
            tab = dg.smooth_resample(vals, xs, self.sp_knots.value(), extend=ext)
        elif how == "poly":
            tab = dg.poly_resample(vals, xs, self.sp_deg.value(), extend=ext)
        else:
            tab = dg.resample(vals, xs, extend=ext)
        return xs, tab, [self.names()[0]] + [c["name"] for c in self.curves]

    def polys(self, cal=None):
        """Je Kurve (Koeffizienten hoechste Potenz zuerst, R^2, x von, x bis) oder None (zu wenige Punkte)."""
        cal = cal or self.calib()
        out = []
        for v in self.curve_values(cal) if cal is not None else []:
            ux, uy = dg._clean_xy(v)
            if len(ux) < 2:
                out.append(None)
                continue
            co, r2 = dg.fit_poly(ux, uy, self.sp_deg.value())
            out.append((co, r2, float(ux.min()), float(ux.max())))
        return out

    def table_text(self, sep="\t", decimal=None):
        res = self.result()
        if res is None:
            return ""
        xs, tab, head = res
        return dg.to_csv(xs, tab, head, sep=sep, decimal=decimal or self.cb_decimal.currentData())

    def functions_text(self):
        cal = self.calib()
        if cal is None:
            return ""
        dec = self.cb_decimal.currentData()
        xn, yn = self.names()
        lines = [tr("x = {}, y = {}").format(xn, yn)]
        for c, v, pf in zip(self.curves, self.curve_values(cal), self.polys(cal)):
            if pf is None:
                continue
            co, r2, lo, hi = pf
            lines.append(tr("{}: {}   (R² = {}, gültig für x = {} … {})").format(
                c["name"], dg.poly_text(co, "x", "y", dec), dg.fmt_num(r2, dec, 6),
                dg.fmt_num(lo, dec, 4), dg.fmt_num(hi, dec, 4)))
            if self.cb_values.currentData() == "smooth":
                ux, uy = dg._clean_xy(v)
                xk, yk = dg.smooth_knots(ux, uy, self.sp_knots.value())
                lines.append("    " + tr("glatte Kurve (kubischer Spline durch {} Stützpunkte): R² = {}").format(
                    len(xk), dg.fmt_num(dg.r2_of(uy, dg.natural_spline(xk, yk, ux)), dec, 6)))
        return "\n".join(lines)

    def update_result(self):
        smooth = self.cb_values.currentData() == "smooth"
        self.lbl_knots.setVisible(smooth)
        self.sp_knots.setVisible(smooth)
        cal = self.calib()
        if cal is not None and self._step_auto:            # runde Schrittweite vorschlagen
            vals = [v for v in self.curve_values(cal) if len(v)]
            if vals:
                allx = np.concatenate([v[:, 0] for v in vals])
                span = np.nanmax(allx) - np.nanmin(allx)
            else:
                span = abs(cal.ax.v2 - cal.ax.v1)
            self._setting_step = True
            self.sp_step.setValue(nice_step(span))
            self._setting_step = False
        res = self.result()
        self.table.clear()
        if res is None:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.txt_fit.setPlainText(tr("Achsen kalibrieren (vier Punkte mit Werten) und mindestens eine Kurve "
                                         "erfassen, dann erscheinen hier Tabelle und Funktionen.")
                                      if cal is None else tr("Noch keine Kurve erfasst."))
            for b in (self.btn_copy, self.btn_save, self.btn_xlsx, self.btn_fn):
                b.setEnabled(False)
            return
        xs, tab, head = res
        dec = self.cb_decimal.currentData()
        self.table.setColumnCount(len(head))
        self.table.setHorizontalHeaderLabels(head)
        self.table.setRowCount(len(xs))
        for i, x in enumerate(xs[:5000]):
            self.table.setItem(i, 0, QTableWidgetItem(dg.fmt_num(x, dec)))
            for k in range(tab.shape[1]):
                self.table.setItem(i, k + 1, QTableWidgetItem(dg.fmt_num(tab[i, k], dec)))
        self.table.resizeColumnsToContents()
        self.txt_fit.setPlainText(self.functions_text())
        for b in (self.btn_copy, self.btn_save, self.btn_xlsx, self.btn_fn):
            b.setEnabled(True)

    def _say(self, text):
        self.lbl_status.setText(text)
        if self.notify:
            self.notify(text)

    def copy_table(self):
        txt = self.table_text(sep="\t")
        if txt:
            QApplication.clipboard().setText(txt)
            self._say(tr("Wertetabelle kopiert ({} Zeilen).").format(txt.count("\n") - 1))

    def copy_functions(self):
        txt = self.functions_text()
        if txt:
            QApplication.clipboard().setText(txt)
            self._say(tr("Funktionen kopiert."))

    def save_csv(self):
        txt = self.table_text(sep=";")
        if not txt:
            return
        title, flt = tr("Wertetabelle als CSV speichern"), tr("CSV (*.csv)")
        if self.save_dialog:
            path = self.save_dialog(title, flt, "diagramm.csv")
        else:
            path, _ = QFileDialog.getSaveFileName(self, title, "diagramm.csv", flt)
        if not path:
            return
        with open(path, "w", encoding="utf-8-sig", newline="") as f:   # mit BOM: Excel erkennt UTF-8
            f.write(txt.replace("\n", "\r\n"))
        self._say(tr("Gespeichert: {}").format(path))

    def save_xlsx(self, path=None):
        res = self.result()
        if res is None:
            return
        if path is None:
            title, flt = tr("Wertetabelle als Excel-Datei speichern"), tr("Excel (*.xlsx)")
            if self.save_dialog:
                path = self.save_dialog(title, flt, "diagramm.xlsx")
            else:
                path, _ = QFileDialog.getSaveFileName(self, title, "diagramm.xlsx", flt)
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        xs, tab, head = res
        xn, yn = self.names()
        cal = self.calib()
        try:
            dg.to_xlsx(path, xs, tab, head, sheet=tr("Werte"), x_title=xn, y_title=yn,
                       xlog=self.chk_xlog.isChecked(), ylog=self.chk_ylog.isChecked(),
                       notes=self.functions_text().splitlines(), notes_sheet=tr("Funktionen"),
                       colors=[c["color"].lstrip("#").upper() for c in self.curves],
                       polys=self.polys(cal), xrev=cal.x_reversed, yrev=cal.y_reversed,
                       labels=(tr("Polynom"), tr("Kurve"), tr("von x"), tr("bis x")))
        except ImportError:
            self._say(tr("Für Excel-Dateien fehlt das Paket openpyxl."))
            return
        except OSError as e:
            self._say(tr("Speichern fehlgeschlagen: {}").format(e))
            return
        self._say(tr("Gespeichert: {}").format(path))


class DigitizeMixin:
    """Hauptfenster: Bereich -> Mehr -> Diagramm digitalisieren …"""

    def area_diagram(self):
        c = self.canvas
        bbox = self._area_bbox() if self.payload is not None and c.sel_rects else None
        if bbox is None:
            self.banner.show_msg(tr("Erst mit dem Werkzeug „Bereich“ (B) das Diagramm aufziehen, dann "
                                    "„Diagramm digitalisieren …“ wählen."), "info", timeout=8)
            return
        import diffedit as de
        mode = "B" if c.mode in ("D", "O", "N", "R") else None    # im Vergleich: neue Zeichnung, ohne Farben
        img = self.render_region(bbox, False, mode=mode)
        region = de.region_mask(c.sel_rects, bbox)
        img = img.copy()
        img[~region.astype(bool)] = 255
        dlg = DigitizeDialog(self, img, save_dialog=self._save_dialog,
                             notify=lambda t: self.banner.show_msg(t, "info", timeout=8), ocr=self._digitize_ocr,
                             ocr_ready=self._digitize_ocr_ready,
                             hires=self._digitize_hires(bbox, region.astype(bool), mode, img))
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._digitize_dlg = dlg                                   # nicht modal: Zeichnung bleibt bedienbar
        dlg.show()
        return dlg

    def _digitize_hires(self, bbox, region, mode, base):
        """Schaerfere Anzeige fuer den Dialog: bei einer PDF/SVG-Quelle, die unveraendert gezeigt wird (wie das
        scharfe Nachrendern der Zeichenflaeche), eine Funktion fuer render_hires, sonst None."""
        c = self.canvas
        v = getattr(c, "vector_src", None)
        if mode is None:                                           # wie render_region
            mode = c.mode if c.mode in ("A", "B", "D", "O", "N", "R") else ("B" if c.mode in ("K", "S") else "D")
            if c.mode == "Y":
                mode = c._side or "B"
        if not v or mode != "A" or not c.show_color or not c.layer_on.get("zeichnung", True):
            return None
        x0, y0, x1, y1 = bbox
        f = min(4.0, HIRES_MAX_SIDE / max(x1 - x0, y1 - y0))
        if f < 1.5:
            return None
        import diffreport as rep
        redact = []                                                # Schwaerzungen im Diagrammbild
        for a in self.anns or []:
            if a.get("type") in rep.REDACT_TYPES:
                redact.append((int(np.floor(min(a["x"], a["x2"]) - x0)), int(np.floor(min(a["y"], a["y2"]) - y0)),
                               int(np.ceil(max(a["x"], a["x2"]) - x0)), int(np.ceil(max(a["y"], a["y2"]) - y0))))
        src = dict(v)
        return lambda: render_hires(src, bbox, f, region, base, redact)

    def _digitize_ocr_ready(self, ask):
        """Texterkennung vorhanden? ask: sonst Installation anbieten."""
        import diffreport as rep
        if rep.ocr_available():
            return True
        return bool(ask) and bool(self.ensure_ocr(tr("die Achsbeschriftungen zu lesen")))

    def _digitize_ocr(self, gray, ask, rots=(0, 1, 3)):
        """Texterkennung fuer die Achsbeschriftungen in den Lagen rots (0 = waagerecht, 1/3 = senkrecht); ask=False:
        nur wenn vorhanden, nicht installieren lassen."""
        import diffreport as rep
        if not rep.ocr_available():
            if not ask or not self.ensure_ocr(tr("die Achsbeschriftungen zu lesen")):
                return None
        return rep.ocr_any_orientation(gray, rots=tuple(rots))
