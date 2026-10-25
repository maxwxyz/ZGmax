"""Zeichenflaeche: Darstellung (Bild, Ansichten, Markierungen, Legende, Uebersicht, Lupe). Teil von Canvas."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_canvas_geom import *  # noqa: F401,F403


class CanvasPaintMixin:
    """Wird in Canvas eingemischt."""

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
            if not self._snapshot:
                self._paint_legend(p)
        if self._snapshot:                             # Bild "wie angezeigt": ohne Legende, Uebersicht, Fadenkreuz
            p.end()
            return
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

    def view_image(self):
        """Der sichtbare Ausschnitt 1:1 wie am Bildschirm (Zoom, Ansicht, Markierungen), ohne Legende, Uebersicht,
        Lupe und ohne die Leisten ueber dem Bild."""
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(QWidget.width(self) * dpr), int(QWidget.height(self) * dpr))
        pm.setDevicePixelRatio(dpr)
        self._snapshot = True
        try:
            self.render(pm, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawWindowBackground)
        finally:
            self._snapshot = False
        return pm.toImage()

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
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.preview_text)

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
        if getattr(self, "_guides", None) and self._drag is not None and self._drag[0] in ("move", "handle"):
            self._paint_guides(p)
        if self._ann_prev:
            (ax, ay), (bx, by) = self._ann_prev
            if self.tool == "straighten":                 # nachgezeichnete Kante: duenne blaue Linie
                p.setPen(QPen(QColor(ACCENT), 2))
                p.drawLine(QPointF(*self.to_wid(ax, ay)), QPointF(*self.to_wid(bx, by)))
            else:
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
        if self.coord_origin is not None:              # Nullpunkt: Achsenkreuz wie im CAD (x rechts, y oben)
            X, Y = self.to_wid(*self.coord_origin)
            p.setPen(QPen(QColor("#dc2626"), 2))
            p.drawLine(QPointF(X, Y), QPointF(X + 34, Y))
            p.drawText(QPointF(X + 37, Y + 4), "x")
            p.setPen(QPen(QColor("#16a34a"), 2))
            p.drawLine(QPointF(X, Y), QPointF(X, Y - 34))
            p.drawText(QPointF(X - 3, Y - 38), "y")
            p.setBrush(QColor("white"))
            p.setPen(QPen(QColor("#111827"), 1.5))
            p.drawEllipse(QPointF(X, Y), 4, 4)
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
            elif k == "x":                                # Schnittpunkt
                p.drawLine(QPointF(X - 9, Y - 9), QPointF(X + 9, Y + 9))
                p.drawLine(QPointF(X - 9, Y + 9), QPointF(X + 9, Y - 9))
            elif k == "c":                                # Kreismittelpunkt
                p.drawEllipse(QPointF(X, Y), 9, 9)
                p.drawLine(QPointF(X - 13, Y), QPointF(X + 13, Y))
                p.drawLine(QPointF(X, Y - 13), QPointF(X, Y + 13))
