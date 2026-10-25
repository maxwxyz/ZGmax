"""Zeichenflaeche: Einrasten (CAD-Fang), Koordinaten und Messen. Teil von Canvas."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_canvas_geom import *  # noqa: F401,F403
from ui_canvas_geom import _run


class CanvasSnapMixin:
    """Wird in Canvas eingemischt."""

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
        feat = self._snap_features(src, ix, iy, use_b)   # Schnittpunkte und Kreismittelpunkte zuerst (wie im CAD)
        if feat is not None:
            return feat
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

    # --- Koordinaten: Nullpunkt und direkte Eingabe
    def unit_factor(self):
        """Bildpixel je Anzeigeeinheit (mm, cm, m, in) - inkl. Massstab."""
        f = rep.UNITS.get(rep.MEASURE_FMT.get("unit", "mm"), 1.0)
        return 1.0 / max(1e-12, self.mm_px * f)

    def to_coords(self, ix, iy):
        """Bildpixel -> Koordinaten in der Anzeigeeinheit, bezogen auf den Nullpunkt, y nach oben (wie im CAD)."""
        ox, oy = self.coord_origin if self.coord_origin else (0.0, float(self.shape[0]))
        u = self.unit_factor()
        return (ix - ox) / u, (oy - iy) / u

    def from_coords(self, x, y):
        ox, oy = self.coord_origin if self.coord_origin else (0.0, float(self.shape[0]))
        u = self.unit_factor()
        return ox + x * u, oy - y * u

    def _last_point(self):
        if self.tool == "measure" and self.measure:
            return self.measure[-1][0], self.measure[-1][1]
        if self.tool in ("polyline", "polygon") and self.poly:
            return self.poly[-1][0], self.poly[-1][1]
        return None

    def parse_coord_input(self, text, toward=None):
        """'25' = Laenge zum Mauszeiger hin, '25<30' = Laenge unter Winkel (Grad, gegen den Uhrzeiger),
        '@dx;dy' = relativ zum letzten Punkt, 'x;y' = absolut ab Nullpunkt. Zahlen mit Komma oder Punkt.
        Gibt Bildpunkt (x, y) oder None."""
        t = text.strip().replace(" ", "")
        if not t:
            return None
        num = lambda s: float(s.replace(",", "."))     # noqa: E731
        last = self._last_point()
        u = self.unit_factor()
        try:
            if t.startswith("@") and ";" in t:
                if last is None:
                    return None
                dx, dy = (num(v) for v in t[1:].split(";", 1))
                return last[0] + dx * u, last[1] - dy * u
            if ";" in t:
                x, y = (num(v) for v in t.split(";", 1))
                return self.from_coords(x, y)
            if last is None:
                return None
            if "<" in t:
                L, ang = (num(v) for v in t.split("<", 1))
                a = math.radians(ang)
                return last[0] + math.cos(a) * L * u, last[1] - math.sin(a) * L * u
            L = num(t)
            tx, ty = toward if toward else (last[0] + 1, last[1])
            d = math.hypot(tx - last[0], ty - last[1]) or 1.0
            return last[0] + (tx - last[0]) / d * L * u, last[1] + (ty - last[1]) / d * L * u
        except ValueError:
            return None

    def _open_coord_input(self, first):
        if self.coord_editor is None:
            ed = QLineEdit(self)
            ed.setPlaceholderText(tr("Länge, Länge<Winkel, @dx;dy oder x;y"))
            ed.setFixedWidth(220)
            ed.returnPressed.connect(self._coord_entered)
            QShortcut(QKeySequence("Escape"), ed, activated=lambda: (ed.hide(), self.setFocus())).setContext(
                Qt.ShortcutContext.WidgetShortcut)
            self.coord_editor = ed
        ed = self.coord_editor
        pos = self._mouse or QPointF(self.width() / 2, self.height() / 2)
        ed.move(int(min(self.width() - 230, pos.x() + 16)), int(min(self.height() - 30, pos.y() + 16)))
        ed.setText(first)
        ed.show()
        ed.setFocus()
        self.window().statusBar().showMessage(
            tr("Eingabe in {}: 25 = Länge Richtung Mauszeiger · 25<30 = mit Winkel · @10;5 = relativ · 100;50 = ab "
               "Nullpunkt · Enter = setzen, Esc = abbrechen").format(rep.MEASURE_FMT.get("unit", "mm")), 15000)

    def _coord_entered(self):
        ed = self.coord_editor
        toward = self.to_img(self._vp(self._mouse)) if self._mouse is not None else None
        pt = self.parse_coord_input(ed.text(), toward)
        ed.hide()
        self.setFocus()
        if pt is None:
            self.window().statusBar().showMessage(tr("Eingabe nicht verstanden (erst einen Punkt setzen?)"), 5000)
            return
        x, y = pt
        if self.tool == "measure":
            self.measure.append((x, y, None))
            need = {"dist": 2, "angle": 3, "radius": 3}.get(self.measure_kind)
            if need and len(self.measure) >= need:
                self.finish_measure()
        elif self.tool in ("polyline", "polygon"):
            self.poly.append([x, y])
        self.update()

    @staticmethod
    def _corner_point(sk, cx, cy, r=16):
        """Genaue Ecke: Schnitt der beiden Linien-Mittellinien (Skelett) um eine grob gefundene Ecke."""
        h, w = sk.shape
        x0, y0 = max(0, int(cx) - r), max(0, int(cy) - r)
        patch = (sk[y0:min(h, int(cy) + r + 1), x0:min(w, int(cx) + r + 1)] > 0).astype(np.uint8) * 255
        if patch.sum() < 255 * 8:
            return None
        lines = cv2.HoughLines(patch, 1, np.pi / 180, max(6, r // 2))
        if lines is None or len(lines) < 2:
            return None
        r1, t1 = lines[0][0]
        for r2, t2 in (ln[0] for ln in lines[1:]):
            dt = abs((t1 - t2 + np.pi / 2) % np.pi - np.pi / 2)
            if dt > np.radians(20):                       # zwei deutlich verschiedene Richtungen
                A = np.array([[np.cos(t1), np.sin(t1)], [np.cos(t2), np.sin(t2)]])
                try:
                    px, py = np.linalg.solve(A, [r1, r2])
                except np.linalg.LinAlgError:
                    return None
                if -2 <= px <= patch.shape[1] + 2 and -2 <= py <= patch.shape[0] + 2:
                    return float(px + x0), float(py + y0)
                return None
        return None

    def _snap_features(self, src, ix, iy, use_b):
        """Fangpunkte wie im CAD: Schnitt-/Eckpunkte von Linien ('x') und Kreismittelpunkte ('c') in der Naehe des
        Zeigers. Gibt (x, y, Art) oder None."""
        h, w = src.shape
        grab = max(4.0, 12 / self.scale)                    # Fangradius (Bildpixel)
        best = None
        # Schnitt- und Eckpunkte: Knoten im Skelett der Linien in einem kleinen Fenster
        r = int(min(200, max(20, 40 / self.scale)))
        x0, y0 = max(0, int(ix) - r), max(0, int(iy) - r)
        x1, y1 = min(w, int(ix) + r + 1), min(h, int(iy) + r + 1)
        win = src[y0:y1, x0:x1]
        if x1 > x0 + 4 and y1 > y0 + 4 and win.any():
            import diffedit as de
            sk = de.thin(win)
            nb = cv2.filter2D(sk, cv2.CV_16S, np.ones((3, 3), np.float32)) - sk
            ys, xs = np.nonzero((sk > 0) & ((nb >= 3) | (nb == 1)))   # Kreuzungen/Abzweige und Linienenden
            cand = [(float(x), float(y)) for x, y in zip(xs, ys)]
            corners = cv2.goodFeaturesToTrack(cv2.GaussianBlur(win.astype(np.float32), (5, 5), 1.5), 40, 0.15, 4)
            if corners is not None:                         # Ecken (L-Form) - im Skelett kein Abzweig
                for (cx_, cy_), in corners:
                    q = self._corner_point(sk, cx_, cy_)
                    if q is not None:
                        cand.append(q)
            if cand:
                arr = np.array(cand)
                d = np.hypot(arr[:, 0] + x0 - ix, arr[:, 1] + y0 - iy)
                k = int(np.argmin(d))
                if d[k] <= grab:
                    best = (float(arr[k, 0] + x0), float(arr[k, 1] + y0), "x", float(d[k]))
        # Kreismittelpunkte: Kreise (auch grosse) um den Zeiger herum suchen, Ergebnis je Stelle zwischenspeichern
        R = int(min(400, max(40, 300 / self.scale)))
        key = (int(ix) // 16, int(iy) // 16, use_b, R // 20, id(src))
        cache = self.__dict__.setdefault("_circle_cache", {})
        circles = cache.get(key)
        if circles is None:
            cx0, cy0 = max(0, int(ix) - R), max(0, int(iy) - R)
            cx1, cy1 = min(w, int(ix) + R + 1), min(h, int(iy) + R + 1)
            part = src[cy0:cy1, cx0:cx1]
            circles = []
            if part.size and part.any():
                g = cv2.GaussianBlur(255 - part, (5, 5), 1.2)
                found = cv2.HoughCircles(g, cv2.HOUGH_GRADIENT_ALT, 1.5, 8, param1=150, param2=0.8,
                                         minRadius=4, maxRadius=R)
                if found is not None:
                    ys, xs = np.nonzero(part > 0)
                    for c in found[0]:                    # Mittelpunkt genau: Kreis durch die Linienpixel einpassen
                        near = np.abs(np.hypot(xs - c[0], ys - c[1]) - c[2]) < max(3.0, c[2] * 0.06)
                        px, py = xs[near].astype(np.float64), ys[near].astype(np.float64)
                        if len(px) >= 12:
                            A = np.column_stack([px, py, np.ones_like(px)])
                            sol, *_ = np.linalg.lstsq(A, px * px + py * py, rcond=None)
                            ccx, ccy = sol[0] / 2, sol[1] / 2
                            cr = math.sqrt(max(0.0, sol[2] + ccx * ccx + ccy * ccy))
                            circles.append((float(ccx + cx0), float(ccy + cy0), float(cr)))
                        else:
                            circles.append((float(c[0] + cx0), float(c[1] + cy0), float(c[2])))
            if len(cache) > 400:
                cache.clear()
            cache[key] = circles
        for cx, cy, cr in circles:
            d = math.hypot(cx - ix, cy - iy)
            if d <= grab and (best is None or d < best[3]):
                best = (cx, cy, "c", d)
        return None if best is None else best[:3]

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
