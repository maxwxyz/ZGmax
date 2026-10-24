"""Hauptfenster: Zeichnung bearbeiten (Ausschnitt verschieben) und Auswahl kopieren (auch nur Linien / Geometrie)."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_canvas import invert_view, pool_ink
import diffedit as de


def to_qimage(arr):
    """numpy BGR/BGRA/Grau -> eigenstaendiges QImage."""
    if arr.ndim == 2:
        arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGRA)
    elif arr.shape[2] == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2BGRA)
    arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    return QImage(arr.data, w, h, arr.strides[0], QImage.Format.Format_ARGB32).copy()


def update_levels(levels, rect, pool):
    """Bildpyramide nach einer Aenderung nur im Rechteck rect (Stufe 0) nachziehen."""
    x0, y0, x1, y1 = rect
    for L in range(1, len(levels)):
        x0, y0, x1, y1 = x0 // 2, y0 // 2, (x1 + 1) // 2, (y1 + 1) // 2
        h, w = levels[L].shape[:2]
        x1, y1 = min(x1, w), min(y1, h)
        if x1 <= x0 or y1 <= y0:
            return
        levels[L][y0:y1, x0:x1] = pool(levels[L - 1][2 * y0:2 * y1, 2 * x0:2 * x1])


def _half(x):
    h, w = x.shape[:2]
    return cv2.resize(x, (max(1, w // 2), max(1, h // 2)), interpolation=cv2.INTER_AREA)


class CopyDialog(QDialog):
    """Vorschau und Optionen fuer 'Auswahl kopieren': alles, nur Linien oder nur Geometrie."""

    def __init__(self, parent, img, ink, mm_px, dpi=200):
        super().__init__(parent)
        self.setWindowTitle(tr("Auswahl kopieren"))
        self.img, self.ink = img, ink
        self.small = int(round(5 * dpi / 25.4))           # Pfeilspitzen/Punkte bis etwa 5 mm auf dem Papier
        self.result = None
        lay = QVBoxLayout(self)
        self.preview = QLabel()
        self.preview.setMinimumSize(520, 340)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("QLabel { border: 1px solid #c0c4cc; }")
        lay.addWidget(self.preview, 1)
        form = QFormLayout()
        self.cb_mode = QComboBox()
        self.cb_mode.addItem(tr("Alles (mit Papier)"), "all")
        self.cb_mode.addItem(tr("Nur Linien (Hintergrund durchsichtig)"), "lines")
        self.cb_mode.addItem(tr("Nur Geometrie (ohne Maße, Text und dünne Linien)"), "geometry")
        form.addRow(tr("Inhalt"), self.cb_mode)
        self.sp_width = QSpinBox()
        self.sp_width.setRange(2, 30)
        self.sp_width.setSuffix(" px")
        sw = de.suggest_geometry_width(self._sample(ink))
        self.sp_width.setValue(sw or 4)
        self.sp_width.setToolTip(tr("Nur Linien ab dieser Breite bleiben (Körperkanten). 1 px = {:.2f} mm").format(mm_px))
        self.lbl_width = QLabel(tr("Linien ab Breite"))
        form.addRow(self.lbl_width, self.sp_width)
        self.chk_small = QCheckBox(tr("Pfeilspitzen und Punkte entfernen"))
        self.chk_small.setChecked(True)
        form.addRow("", self.chk_small)
        lay.addLayout(form)
        self.hint = QLabel(tr("Vorschlag aus den Strichstärken: {} px.").format(sw) if sw else
                           tr("Keine deutlich dickeren Linien gefunden – Breite selbst wählen."))
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)
        bb = QDialogButtonBox()
        self.btn_copy = bb.addButton(tr("Kopieren"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_copy.setObjectName("primary")
        self.btn_save = bb.addButton(tr("Speichern …"), QDialogButtonBox.ButtonRole.ActionRole)
        close = bb.addButton(tr("Schließen"), QDialogButtonBox.ButtonRole.RejectRole)
        close.clicked.connect(self.reject)
        self.btn_copy.clicked.connect(self._copy)
        self.btn_save.clicked.connect(self._save)
        lay.addWidget(bb)
        self.cb_mode.currentIndexChanged.connect(self._update)
        self.sp_width.valueChanged.connect(self._update)
        self.chk_small.toggled.connect(self._update)
        self._update()

    @staticmethod
    def _sample(ink, limit=4000):
        """Fuer den Breitenvorschlag hoechstens ein Mittelstueck (schnell auch bei ganzen Blaettern)."""
        h, w = ink.shape
        y0, x0 = max(0, (h - limit) // 2), max(0, (w - limit) // 2)
        return ink[y0:y0 + limit, x0:x0 + limit]

    def _update(self):
        mode = self.cb_mode.currentData()
        geo = mode == "geometry"
        for w in (self.lbl_width, self.sp_width, self.chk_small, self.hint):
            w.setVisible(geo)
        h, w = self.ink.shape
        self.result, _ = de.cut_out(self.img, self.ink, (0, 0, w, h), mode, self.sp_width.value(),
                                   self.small if self.chk_small.isChecked() else 0)
        self._show()

    def _show(self):
        """Vorschau auf Schachbrett, damit durchsichtige Stellen erkennbar sind."""
        img = QPixmap.fromImage(to_qimage(self.result)).scaled(
            self.preview.size() - QSize(8, 8), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        pm = QPixmap(img.size())
        p = QPainter(pm)
        n = 10
        for yy in range(0, pm.height(), n):
            for xx in range(0, pm.width(), n):
                p.fillRect(xx, yy, n, n, QColor("#ffffff") if (xx // n + yy // n) % 2 else QColor("#e3e6ea"))
        p.drawPixmap(0, 0, img)
        p.end()
        self.preview.setPixmap(pm)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.result is not None:
            self._show()

    def _copy(self):
        img = to_qimage(self.result)
        md = QMimeData()
        md.setImageData(img)
        ok, png = cv2.imencode(".png", self.result)      # PNG mit Transparenz fuer Office, Grafikprogramme
        if ok:
            md.setData("image/png", QByteArray(png.tobytes()))
        QApplication.clipboard().setMimeData(md)
        self.accept()

    def _save(self):
        path = self.parent()._save_dialog(tr("Auswahl speichern"), tr("PNG-Bild (*.png)"), "auswahl.png")
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            cv2.imencode(".png", self.result)[1].tofile(path)
            self.accept()


class EditMixin:
    """Teil des Hauptfensters (wird in MainWindow eingemischt)."""

    # --- Auswahl kopieren
    def start_copy_selection(self):
        if self.payload is None:
            return
        if self.canvas.sel_rects:                          # Bereich schon gewaehlt: gleich das Kopierfenster
            self.area_copy_options()
            return
        self._set_tool("copysel")

    def _source_for_view(self):
        """(Bild, Linienmaske) dessen, was gerade angezeigt wird, in Ergebnis-Koordinaten."""
        c = self.canvas
        mode = c.mode
        if mode == "Y":
            mode = c._side or "B"
        elif mode in ("K", "S"):
            mode = "B"
        return mode

    def _sel_copy(self, x, y, w, h, keep_tool=False):
        c = self.canvas
        mode = self._source_for_view()
        part = c._layer(mode, 0, y, y + h, x, x + w)
        if part is None:
            return
        if mode in ("A", "B"):
            ink = (c.res.a if mode == "A" else c.res.b)[y:y + h, x:x + w]
        else:                                              # farbige Ansicht: alles Nicht-Weisse ist Linie
            ink = ((part.min(axis=2) < 200) * 255).astype(np.uint8)
        dlg = CopyDialog(self, np.ascontiguousarray(part), np.ascontiguousarray(ink), c.mm_px, self.dpi_value())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.statusBar().showMessage(tr("Auswahl kopiert ({} × {} px)").format(w, h), 5000)
        if not keep_tool:
            self._set_tool("hand")

    # --- Ausschnitt verschieben (nur beim Ansehen einer einzelnen Zeichnung)
    def _edit_images(self):
        """Bearbeitbare Bilder der angezeigten Einzelzeichnung: [Grau, Farbe] (gleiche Groesse) oder None."""
        path = self.path_a or self.path_b
        g = self.cache.get("g_" + path) if path else None
        if not self.view_only or g is None or self.payload is None or g.shape != self.payload["res"].a.shape:
            return None, path
        c = self.cache.get("c_" + path)
        return [g] + ([c] if c is not None else []), path

    def start_move_region(self):
        imgs, _ = self._edit_images()
        if imgs is None:
            self.banner.show_msg(tr("Ausschnitt verschieben geht beim Ansehen einer einzelnen Zeichnung "
                                    "(Datei → Zeichnung ansehen)."), "info", timeout=8)
            return
        self._set_tool("cutmove")

    def _sel_move(self, x, y, w, h):
        imgs, _ = self._edit_images()
        if imgs is None:
            return
        self.canvas.float = dict(rect=(x, y, x + w, y + h), dx=0, dy=0)
        self._float_images()
        self._update_options()
        self.canvas.update()

    def _float_images(self):
        f = self.canvas.float
        if not f:
            return
        x0, y0, x1, y1 = f["rect"]
        c = self.canvas
        part = c._layer("A", 0, y0, y1, x0, x1)
        ink = c.res.a[y0:y1, x0:x1]
        only = self.chk_float_lines.isChecked()
        mask = de.line_mask(ink, 2) if only else np.ones(ink.shape, bool)
        if f.get("region") is not None:
            mask &= f["region"]
        imgs, _ = self._edit_images()
        bg = de.paper_color(imgs[-1], c.res.a, f["rect"])
        bgc = bg if isinstance(bg, tuple) else (bg, bg, bg)
        alpha = mask.astype(np.uint8) * 255
        piece = np.dstack([invert_view(part, "A") if c.invert else part, alpha])
        hole = np.dstack([np.full(part.shape, bgc, np.uint8), alpha])
        if c.invert:                                        # Anzeige umgekehrt: Vorschau passend dazu
            hole[..., :3] = 255 - hole[..., :3]
        f["piece"], f["hole"] = to_qimage(piece), to_qimage(hole)

    def _float_done(self, ok):
        c = self.canvas
        f = c.float
        c.float = None
        if ok and f and (f["dx"] or f["dy"]):
            self._apply_move(f["rect"], f["dx"], f["dy"], self.chk_float_lines.isChecked(), f.get("region"))
        self._update_options()
        c.update()

    def _apply_move(self, rect, dx, dy, only_lines, region=None):
        imgs, path = self._edit_images()
        if imgs is None:
            return
        ink = self.payload["res"].a
        x0, y0, x1, y1 = rect
        u = de.clip_rect((min(x0, x0 + dx), min(y0, y0 + dy), max(x1, x1 + dx), max(y1, y1 + dy)), ink.shape)
        sl = (slice(u[1], u[3]), slice(u[0], u[2]))
        before = [im[sl].copy() for im in imgs]
        if de.move_region(imgs, ink, rect, dx, dy, only_lines, region) is None:
            return
        self._record_edit(path, u, sl, before, imgs)
        self.statusBar().showMessage(tr("Ausschnitt verschoben um {} / {} px. Rückgängig: Strg+Z").format(dx, dy), 6000)

    def _record_edit(self, path, u, sl, before, imgs):
        """Bildaenderung im Rechteck u fuer Rueckgaengig/Wiederholen festhalten und Ansicht nachziehen."""
        after = [im[sl].copy() for im in imgs]
        del self._edits[self._edit_ver:]                   # nach Rueckgaengig: alte Wiederholung verwerfen
        self._edits.append(dict(path=path, rect=u, before=before, after=after))
        self._edit_ver = len(self._edits)
        self._edit_saved = False
        self._edit_refresh(u)
        self._commit()
        self.act_save_drawing.setEnabled(True)

    def _edit_refresh(self, u):
        """Linienmaske und Ansichtsstufen nach einer Bildaenderung im Rechteck u nachziehen."""
        pl = self.payload
        imgs, _ = self._edit_images()
        if imgs is None:
            return
        g, res = imgs[0], pl["res"]
        m = 16
        x0, y0, x1, y1 = de.clip_rect((u[0] - m, u[1] - m, u[2] + m, u[3] + m), g.shape)
        a = dp.ink_from_gray(g[y0:y1, x0:x1], self.s_thr.value(), self.chk_flatten.isChecked())
        res.a[y0:y1, x0:x1] = a                            # in der Einzelansicht ist res.b dasselbe Feld
        res.both[y0:y1, x0:x1] = a > 0
        r = (x0, y0, x1, y1)
        update_levels(pl["pa"], r, pool_ink)
        if pl["pb"] is not pl["pa"]:
            update_levels(pl["pb"], r, pool_ink)
        pc = (pl.get("pc") or (None,))[0]
        if pc:
            update_levels(pc, r, _half)
        self.canvas.update()

    def _edit_goto(self, ver):
        """Rueckgaengig/Wiederholen der Bildaenderungen bis zum Stand ver."""
        ver = max(0, min(ver, len(self._edits)))
        while self._edit_ver != ver:
            back = self._edit_ver > ver
            e = self._edits[self._edit_ver - 1] if back else self._edits[self._edit_ver]
            imgs, path = self._edit_images()
            if imgs is not None and path == e["path"]:
                x0, y0, x1, y1 = e["rect"]
                for im, patch in zip(imgs, e["before"] if back else e["after"]):
                    im[y0:y1, x0:x1] = patch
                self._edit_refresh(e["rect"])
            self._edit_ver += -1 if back else 1
        self.act_save_drawing.setEnabled(self._edit_ver > 0)

    def drawing_edited(self):
        return bool(getattr(self, "_edit_ver", 0)) and not getattr(self, "_edit_saved", True)

    def save_drawing(self):
        """Bearbeitete Zeichnung (ohne Markierungen) als Bild oder PDF speichern."""
        imgs, path = self._edit_images()
        if imgs is None:
            return False
        base = os.path.splitext(os.path.basename(path))[0] + "_bearbeitet.png"
        out = self._save_dialog(tr("Zeichnung speichern"), tr("PNG (*.png);;TIFF (*.tif);;PDF (*.pdf);;JPEG (*.jpg)"), base)
        if not out:
            return False
        from PIL import Image
        img = imgs[-1]
        pil = Image.fromarray(img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        dpi = self.dpi_value()
        ext = os.path.splitext(out)[1].lower()
        if ext == ".pdf":
            pil.convert("RGB").save(out, resolution=dpi)
        elif ext in (".tif", ".tiff"):
            pil.save(out, dpi=(dpi, dpi), compression="tiff_lzw")
        elif ext in (".jpg", ".jpeg"):
            pil.convert("RGB").save(out, dpi=(dpi, dpi), quality=95)
        else:
            pil.save(out, dpi=(dpi, dpi))
        self._edit_saved = True
        self.banner.show_msg(tr("Gespeichert: {}").format(out), "info", timeout=10)
        return True


MARKUP_MIME = "application/x-zgmax-markups"


def qimage_to_bgra(img):
    """QImage -> BGRA-Array."""
    img = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.constBits(), np.uint8, img.bytesPerLine() * h).reshape(h, img.bytesPerLine())
    return arr[:, :w * 4].reshape(h, w, 4).copy()


class ClipboardMixin:
    """Einfuegen aus der Zwischenablage: Markierungen, Bilder (als verschiebbares Bild), Text."""

    def copy_markups(self, idx=None):
        """Gewaehlte Markierungen in die Zwischenablage (zum Einfuegen hier oder in einem anderen Fenster)."""
        idx = sorted(self.canvas.selected_anns()) if idx is None else idx
        if not idx:
            return False
        anns = [copy.deepcopy(self.anns[i]) for i in idx]
        md = QMimeData()
        md.setData(MARKUP_MIME, QByteArray(json.dumps(anns).encode("utf-8")))
        md.setText("\n".join(self._ann_label(a) for a in anns))
        QApplication.clipboard().setMimeData(md)
        self.statusBar().showMessage(tr("{} Markierung(en) kopiert").format(len(anns)), 4000)
        return True

    def _view_center(self):
        c = self.canvas
        return c.to_img(QPointF(c.width() / 2, c.height() / 2)) if c.rot % 4 == 0 else c.to_img(
            c._xform().inverted()[0].map(QPointF(c.width() / 2, c.height() / 2)))

    def paste(self):
        md = QApplication.clipboard().mimeData()
        if md is None:
            return
        if self.payload is None:                           # nichts offen: Bild als neue Zeichnung oeffnen
            if md.hasImage():
                self.open_clipboard()
            return
        c = self.canvas
        cx, cy = self._view_center()
        new = []
        if md.hasFormat(REGION_MIME):                     # Bereich aus diesem Programm: Bild + Markierungen
            try:
                data = json.loads(bytes(md.data(REGION_MIME)).decode("utf-8"))
            except ValueError:
                data = None
            if data:
                x0, y0, x1, y1 = data["rect"]
                dx, dy = cx - (x0 + x1) / 2, cy - (y0 + y1) / 2
                new.append(dict(type="image", png=data["png"], x=x0 + dx, y=y0 + dy, x2=x1 + dx, y2=y1 + dy,
                                text="", nr=0, color="#000000", size=c.ann_size))
                for a in data.get("anns", []):
                    shift_ann(a, dx, dy)
                    new.append(a)
        elif md.hasFormat(MARKUP_MIME):
            try:
                anns = json.loads(bytes(md.data(MARKUP_MIME)).decode("utf-8"))
            except ValueError:
                anns = []
            if anns:
                bx0 = min(a["x"] for a in anns)
                by0 = min(a["y"] for a in anns)
                bx1 = max(a["x2"] for a in anns)
                by1 = max(a["y2"] for a in anns)
                dx, dy = cx - (bx0 + bx1) / 2, cy - (by0 + by1) / 2
                for a in anns:
                    shift_ann(a, dx, dy)
                    new.append(a)
        elif md.hasImage():
            bgra = qimage_to_bgra(QImage(md.imageData()))
            h, w = bgra.shape[:2]
            if w < 1 or h < 1:
                return
            k = 1.0 / c.scale                              # so gross, wie es auf dem Bildschirm war ...
            k = min(k, 0.8 * c.width() / c.scale / w, 0.8 * c.height() / c.scale / h)   # ... hoechstens 80 % der Ansicht
            ww, hh = w * k, h * k
            new.append(dict(type="image", png=rep.image_png(bgra), x=cx - ww / 2, y=cy - hh / 2, x2=cx + ww / 2,
                            y2=cy + hh / 2, text="", nr=0, color="#000000", size=c.ann_size))
        elif md.hasText() and md.text().strip():
            new.append(dict(type="text", text=md.text().strip()[:2000], x=cx, y=cy, x2=cx, y2=cy, nr=0,
                            color=c.ann_color, size=c.ann_size))
        if not new:
            self.statusBar().showMessage(tr("In der Zwischenablage ist nichts zum Einfügen."), 4000)
            return
        start = len(self.anns)
        self.anns.extend(new)
        self._set_tool("hand")
        self._ann_refresh(len(self.anns) - 1)
        if len(new) > 1:
            c._set_multi(set(range(start, len(self.anns))))
        self._commit()
        self.tabs.setCurrentIndex(1)
        self.statusBar().showMessage(tr("Eingefügt – mit der Maus verschieben, an den Ecken die Größe ändern"), 6000)

    def open_clipboard(self):
        """Bild aus der Zwischenablage (z. B. Bildschirmfoto) als Zeichnung oeffnen."""
        md = QApplication.clipboard().mimeData()
        if md is None or not md.hasImage():
            self.banner.show_msg(tr("In der Zwischenablage ist kein Bild."), "info", timeout=6)
            return
        bgra = qimage_to_bgra(QImage(md.imageData()))
        d = os.path.join(app_data_dir(), "zwischenablage")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, dt.datetime.now().strftime("eingefuegt-%Y%m%d-%H%M%S.png"))
        if bgra[..., 3].min() == 255:
            bgra = bgra[..., :3]
        else:                                              # durchsichtig -> auf weissem Papier
            a = bgra[..., 3:4].astype(np.float32) / 255
            bgra = (bgra[..., :3] * a + 255 * (1 - a)).astype(np.uint8)
        cv2.imencode(".png", bgra)[1].tofile(path)
        win = self.new_window() if self.payload is not None else self
        win.path_b = None
        win.lbl_b.setText(tr("(nicht gewählt)"))
        win._set_file("A", path)


REGION_MIME = "application/x-zgmax-region"


class AreaMixin:
    """Bereichsauswahl (Werkzeug "Bereich"): ein oder mehrere Rechtecke; waehlt Zeichnungsinhalt, Markierungen und
    Aenderungen darin. Danach kopieren, ausschneiden, verschieben, loeschen, exportieren oder zuschneiden."""

    def start_area(self):
        if self.payload is not None:
            self._set_tool("area")

    def _area_bbox(self):
        r = self.canvas.sel_rects
        return de.bbox_of(r) if r else None

    def _area_items(self):
        """(Indizes der Markierungen, Aenderungen) in der Bereichsauswahl."""
        c = self.canvas
        rects = c.sel_rects
        anns = []
        for k, a in enumerate(self.anns):
            b = rep.ann_bounds(c.shape, a)
            if any(b[0] < r[2] and b[2] > r[0] and b[1] < r[3] and b[3] > r[1] for r in rects):
                anns.append(k)
        regs = [g for g in ((self.payload or {}).get("regs") or [])
                if any(g["x"] < r[2] and g["x"] + g["w"] > r[0] and g["y"] < r[3] and g["y"] + g["h"] > r[1]
                       for r in rects)]
        return anns, regs

    def _area_changed(self):
        c = self.canvas
        if not c.sel_rects:
            c.ann_multi, c.ann_selected = set(), None
            self.annMultiSync([])
        else:
            anns, regs = self._area_items()
            c._set_multi(set(anns))
            bx = self._area_bbox()
            self.lbl_area.setText(tr("{} × {} px · {} Markierungen · {} Änderungen").format(
                bx[2] - bx[0], bx[3] - bx[1], len(anns), len(regs)))
        self._update_options()
        c.update()

    def annMultiSync(self, rows):
        self._ann_multi_selected(rows)

    def _area_move_started(self):
        c = self.canvas
        imgs, _ = self._edit_images()
        if imgs is None or not c.sel_rects:                # im Vergleich wandern nur die Markierungen
            return
        bbox = self._area_bbox()
        c.float = dict(rect=bbox, dx=0, dy=0, region=de.region_mask(c.sel_rects, bbox))
        self._float_images()

    def _area_moved(self, dx, dy):
        c = self.canvas
        if c.float is not None:
            f = c.float
            f["dx"], f["dy"] = dx, dy
            self._float_done(True)                         # zeichnet die Zeichnung um und haelt alles fest
        elif dx or dy:
            self._commit()
        for k in sorted(c.selected_anns()):
            it = self.list_anns.item(k)
            if it:
                it.setText(self._ann_label(self.anns[k]))
        self._area_changed()

    def render_region(self, bbox, overlays=True, mode=None):
        """Bereich so, wie er angezeigt wird (Ansicht, Aenderungsrahmen, Markierungen) als BGR-Bild."""
        c = self.canvas
        if mode is None:
            mode = c.mode if c.mode in ("A", "B", "D", "O", "N", "R") else ("B" if c.mode in ("K", "S") else "D")
            if c.mode == "Y":
                mode = c._side or "B"
        x0, y0, x1, y1 = bbox
        out = np.ascontiguousarray(c._layer(mode, 0, y0, y1, x0, x1)).copy()
        if overlays and c.show_overlays:
            if self.payload.get("regs") and c.show_regs:
                regs = [dict(g, x=g["x"] - x0, y=g["y"] - y0) for g in self._shown_regs()]
                rep.draw_marks(out, regs, cloud=self.act_clouds.isChecked())
            rep.draw_annotations(out, self.anns, offset=(x0, y0), ref_shape=c.shape, mm=c.mm_px)
        return out

    def _area_bgra(self, overlays=True):
        bbox = self._area_bbox()
        out = self.render_region(bbox, overlays)
        alpha = de.region_mask(self.canvas.sel_rects, bbox).astype(np.uint8) * 255
        return np.dstack([out, alpha]), bbox

    def area_copy(self):
        """Auswahl wie angezeigt in die Zwischenablage; fuer dieses Programm auch Zeichnung und Markierungen getrennt."""
        if not self.canvas.sel_rects:
            return
        bgra, bbox = self._area_bgra(True)
        plain, _ = self._area_bgra(False)
        anns, _ = self._area_items()
        md = QMimeData()
        md.setImageData(to_qimage(bgra))
        ok, png = cv2.imencode(".png", bgra)
        if ok:
            md.setData("image/png", QByteArray(png.tobytes()))
        data = dict(png=rep.image_png(plain), rect=list(bbox), anns=[copy.deepcopy(self.anns[k]) for k in anns])
        md.setData(REGION_MIME, QByteArray(json.dumps(data).encode("utf-8")))
        QApplication.clipboard().setMimeData(md)
        self.statusBar().showMessage(tr("Auswahl kopiert ({} × {} px, {} Markierungen)").format(
            bbox[2] - bbox[0], bbox[3] - bbox[1], len(anns)), 5000)

    def area_copy_options(self):
        """Kopieren mit Auswahl: alles, nur Linien, nur Geometrie (Vorschaufenster)."""
        bbox = self._area_bbox()
        if bbox is None:
            return
        x0, y0, x1, y1 = bbox
        self._sel_copy(x0, y0, x1 - x0, y1 - y0, keep_tool=True)

    def area_delete(self):
        """Markierungen und Aenderungen in der Auswahl loeschen (die Zeichnung selbst bleibt)."""
        anns, regs = self._area_items()
        if not anns and not regs:
            self.statusBar().showMessage(tr("In der Auswahl sind keine Markierungen oder Änderungen."), 5000)
            return
        for k in sorted(anns, reverse=True):
            del self.anns[k]
        if regs:
            nrs = {g["nr"] for g in regs}
            self.payload["regs"][:] = [g for g in self.payload["regs"] if g["nr"] not in nrs]
            self._fill_table()
        self._ann_refresh(None)
        self._commit()
        self.statusBar().showMessage(tr("{} Markierungen und {} Änderungen gelöscht").format(len(anns), len(regs)), 6000)
        self._area_changed()

    def area_clear(self):
        """Zeichnungsinhalt der Auswahl entfernen (Papierfarbe), nur beim Ansehen einer einzelnen Zeichnung."""
        imgs, path = self._edit_images()
        bbox = self._area_bbox()
        if imgs is None or bbox is None:
            return
        ink = self.payload["res"].a
        sl = (slice(bbox[1], bbox[3]), slice(bbox[0], bbox[2]))
        before = [im[sl].copy() for im in imgs]
        de.fill_region(imgs, ink, bbox, de.region_mask(self.canvas.sel_rects, bbox), self.chk_float_lines.isChecked())
        self._record_edit(path, bbox, sl, before, imgs)

    def area_cut(self):
        self.area_copy()
        if self.view_only and self._edit_images()[0] is not None:
            self.area_clear()
        anns, _ = self._area_items()
        if anns:
            for k in sorted(anns, reverse=True):
                del self.anns[k]
            self._ann_refresh(None)
            self._commit()
        self._area_changed()

    def area_export(self):
        """Auswahl als Bild oder PDF speichern (wie angezeigt, mit Markierungen)."""
        if not self.canvas.sel_rects:
            return
        out = self._save_dialog(tr("Auswahl exportieren"), tr("PNG (*.png);;TIFF (*.tif);;JPEG (*.jpg);;PDF (*.pdf)"),
                                "auswahl.png")
        if not out:
            return
        bgra, _ = self._area_bgra(True)
        ext = os.path.splitext(out)[1].lower()
        from PIL import Image
        dpi = self.dpi_value()
        if ext in (".jpg", ".jpeg", ".pdf"):               # ohne Transparenz: auf Weiss
            a = bgra[..., 3:4].astype(np.float32) / 255
            rgb = (bgra[..., :3] * a + 255 * (1 - a)).astype(np.uint8)[..., ::-1]
            im = Image.fromarray(np.ascontiguousarray(rgb))
            if ext == ".pdf":
                im.save(out, resolution=dpi)
            else:
                im.save(out, dpi=(dpi, dpi), quality=95)
        else:
            Image.fromarray(cv2.cvtColor(bgra, cv2.COLOR_BGRA2RGBA)).save(out, dpi=(dpi, dpi))
        self.banner.show_msg(tr("Gespeichert: {}").format(out), "info", timeout=8)

    def area_clear_selection(self):
        if self.canvas.sel_rects:
            self.canvas.sel_rects = []
            self._area_changed()
