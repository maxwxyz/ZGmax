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
        part = rep.apply_redactions(np.ascontiguousarray(part).copy(), self.anns, (x, y), c.shape)
        if mode in ("A", "B"):
            ink = (c.res.a if mode == "A" else c.res.b)[y:y + h, x:x + w].copy()
            for b in rep.redaction_boxes(self.anns):
                ink[max(0, int(b[1]) - y):max(0, int(b[3]) + 1 - y), max(0, int(b[0]) - x):max(0, int(b[2]) + 1 - x)] = 0
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
        if not self.view_only or g is None or self.payload is None or g.shape != self.payload["res"].a.shape \
                or self.canvas.layer_lock.get("zeichnung") or not self.canvas.layer_on.get("zeichnung", True):
            return None, path                              # Zeichnung gesperrt oder ausgeblendet: nicht bearbeiten
        c = self.cache.get("c_" + path)
        return [g] + ([c] if c is not None else []), path

    def start_move_region(self):
        imgs, _ = self._edit_images()
        if imgs is None:
            self.banner.show_msg(tr("Ausschnitt verschieben geht beim Ansehen einer einzelnen Zeichnung "
                                    "(Datei → Einzelne Zeichnung öffnen)."), "info", timeout=8)
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
            if e.get("full"):                              # ganze Zeichnung (zuschneiden, drehen ...): tauschen
                if e["path"] == (self.path_a or self.path_b):
                    self._set_sheet(e["path"], e["before"] if back else e["after"], e["dpi"][0 if back else 1])
                self._edit_ver += -1 if back else 1
                continue
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
        img = self._apply_frame(rep.apply_redactions(imgs[-1].copy(), self.anns))   # Schwaerzungen, Zuschnitt
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
        elif md.hasImage() and not QApplication.clipboard().image().isNull():
            bgra = qimage_to_bgra(QApplication.clipboard().image())
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
        self.tabs.setCurrentWidget(self.tab_anns)
        self.statusBar().showMessage(tr("Eingefügt – mit der Maus verschieben, an den Ecken die Größe ändern"), 6000)

    def open_clipboard(self):
        """Bild aus der Zwischenablage (z. B. Bildschirmfoto) als Zeichnung oeffnen."""
        md = QApplication.clipboard().mimeData()
        img = QApplication.clipboard().image() if md is not None and md.hasImage() else QImage()
        if img.isNull():                                   # kein (lesbares) Bild, z. B. nur Text kopiert
            self.banner.show_msg(tr("In der Zwischenablage ist kein Bild."), "info", timeout=6)
            return
        bgra = qimage_to_bgra(img)
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

    def _area_bbox(self, clip=True):
        """Umgebendes Rechteck der Bereichsauswahl; clip=False: auch ueber den Blattrand hinaus (Zuschneiden)."""
        r = self.canvas.sel_rects
        if not r:
            return None
        b = de.bbox_of(r)
        if not clip:
            return b
        h, w = self.canvas.shape
        b = (max(0, b[0]), max(0, b[1]), min(w, b[2]), min(h, b[3]))
        return b if b[2] > b[0] and b[3] > b[1] else None

    def _area_items(self):
        """(Indizes der Markierungen, Aenderungen) in der Bereichsauswahl."""
        c = self.canvas
        rects = c.sel_rects
        anns = []
        for k, a in enumerate(self.anns):
            b = rep.ann_bounds(c.shape, a)
            if c.ann_editable(a) and any(b[0] < r[2] and b[2] > r[0] and b[1] < r[3] and b[3] > r[1] for r in rects):
                anns.append(k)
        if c.layer_lock.get("aenderungen") or not c.layer_on.get("aenderungen", True):
            return anns, []
        return anns, self._area_regs(rects)

    def _area_zones(self):
        c = self.canvas
        if c.layer_lock.get("zonen") or not c.layer_on.get("zonen", True):
            return []
        return [k for k, (x, y, w, h) in enumerate(c.zones)
                if any(x < r[2] and x + w > r[0] and y < r[3] and y + h > r[1] for r in c.sel_rects)]

    def _area_regs(self, rects):
        regs = [g for g in ((self.payload or {}).get("regs") or [])
                if any(g["x"] < r[2] and g["x"] + g["w"] > r[0] and g["y"] < r[3] and g["y"] + g["h"] > r[1]
                       for r in rects)]
        return regs

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
        if not c.layer_on.get("zeichnung", True):
            out[:] = 255
        rep.apply_redactions(out, self.anns, (x0, y0), c.shape)   # Schwaerzungen immer
        if overlays and c.show_overlays:
            if self.payload.get("regs") and c.show_regs and c.layer_on.get("aenderungen", True):
                regs = [dict(g, x=g["x"] - x0, y=g["y"] - y0) for g in self._shown_regs()]
                rep.draw_marks(out, regs, cloud=self.act_clouds.isChecked())
            rep.draw_annotations(out, self._export_anns(), offset=(x0, y0), ref_shape=c.shape, mm=c.mm_px)
        return out

    def _export_anns(self):
        """Markierungen fuer Bild, PDF und Bericht: nur bei eingeblendeten Markierungen und nur sichtbare Ebenen."""
        if not self.act_overlays.isChecked():
            return []
        return [copy.deepcopy(self.anns[i]) for i in rep.layer_order(self.anns) if self.canvas.ann_visible(self.anns[i])]

    def _export_regs(self):
        c = self.canvas
        if not (self.act_overlays.isChecked() and c.show_regs and c.layer_on.get("aenderungen", True)
                and self.payload and self.payload.get("regs_done") is not False):
            return []
        return copy.deepcopy(self._shown_regs())

    def export_svg(self, bbox=None, path=None):
        """Als SVG mit Ebenen speichern: Zeichnung als Bild, Aenderungen und Markierungen als Vektoren."""
        if not self._need_result():
            return
        c = self.canvas
        if path is None:
            path = self._save_dialog(tr("Als SVG mit Ebenen speichern"), tr("SVG (*.svg)"), "zeichnung.svg")
        if not path:
            return
        h, w = c.shape
        if bbox is None and self._frame_local() is not None:     # Zuschnitt-Rahmen (innerhalb des Blatts)
            f = self._frame_local()
            bbox = (max(0, f[0]), max(0, f[1]), min(w, f[2]), min(h, f[3]))
        bbox = bbox or (0, 0, w, h)
        img = self.render_region(bbox, overlays=False) if c.layer_on.get("zeichnung", True) else None
        x0, y0, x1, y1 = bbox
        regs = [g for g in self._export_regs() if g["x"] < x1 and g["x"] + g["w"] > x0 and g["y"] < y1
                and g["y"] + g["h"] > y0]
        rep.build_svg(path, img, (x1 - x0, y1 - y0), regs, self._export_anns(), self.dpi_value(), c.mm_px,
                      offset=(x0, y0), ref_shape=c.shape)
        self.banner.show_msg(tr("Gespeichert: {}").format(path), "info", timeout=8)
        return path

    def _area_bgra(self, overlays=True, only_lines=None):
        """Bereich als BGRA (ausserhalb der Rechtecke durchsichtig). only_lines: auch das Papier durchsichtig,
        nur Linien (und Markierungen) bleiben - wie beim Verschieben mit "Nur Linien"."""
        bbox = self._area_bbox()
        out = self.render_region(bbox, overlays)
        region = de.region_mask(self.canvas.sel_rects, bbox)
        if only_lines is None:
            only_lines = self.chk_float_lines.isChecked()
        if only_lines:
            plain = self.render_region(bbox, False)
            gray = plain.min(axis=2) if plain.ndim == 3 else plain
            keep = de.line_mask(((gray < 200) * 255).astype(np.uint8), 1)
            if overlays:
                keep |= (out != plain).any(axis=2) if out.ndim == 3 else out != plain
            region &= keep
        return np.dstack([out, region.astype(np.uint8) * 255]), bbox

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
        zones = self._area_zones()
        if not anns and not regs and not zones:
            self.statusBar().showMessage(tr("In der Auswahl sind keine Markierungen, Änderungen oder Zonen."), 5000)
            return
        for k in sorted(anns, reverse=True):
            del self.anns[k]
        if zones:
            for k in sorted(zones, reverse=True):
                del self.zones[k]
            self._refresh_zones()
            self._param_changed()
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
        out = self._save_dialog(tr("Auswahl exportieren"),
                                tr("PNG (*.png);;TIFF (*.tif);;JPEG (*.jpg);;PDF (*.pdf);;SVG mit Ebenen (*.svg)"),
                                "auswahl.png")
        if not out:
            return
        if out.lower().endswith(".svg"):
            self.export_svg(self._area_bbox(), out)
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


class AdjustDialog(QDialog):
    """Helligkeit und Kontrast mit Vorschau."""

    def __init__(self, parent, img):
        super().__init__(parent)
        self.setWindowTitle(tr("Helligkeit und Kontrast"))
        k = min(1.0, 520 / img.shape[1], 340 / img.shape[0])     # Vorschau passt ganz ins Fenster
        self.small = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        gray = img if img.ndim == 2 else img.min(axis=2)
        self.auto = de.auto_levels(gray)
        lay = QVBoxLayout(self)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(420, 300)
        lay.addWidget(self.preview, 1)
        form = QFormLayout()
        self.s_b = QSlider(Qt.Orientation.Horizontal)
        self.s_b.setRange(-100, 100)
        self.s_c = QSlider(Qt.Orientation.Horizontal)
        self.s_c.setRange(20, 400)
        self.s_c.setValue(100)
        form.addRow(tr("Helligkeit"), self.s_b)
        form.addRow(tr("Kontrast"), self.s_c)
        lay.addLayout(form)
        row = QHBoxLayout()
        b = QPushButton(tr("Automatisch (Papier weiß, Linien kräftig)"))
        b.clicked.connect(lambda: (self.s_b.setValue(int(round(self.auto[0]))), self.s_c.setValue(int(round(self.auto[1] * 100)))))
        row.addWidget(b)
        b = QPushButton(tr("Zurücksetzen"))
        b.clicked.connect(lambda: (self.s_b.setValue(0), self.s_c.setValue(100)))
        row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        bb = QDialogButtonBox()
        bb.addButton(tr("Übernehmen"), QDialogButtonBox.ButtonRole.AcceptRole).setObjectName("primary")
        bb.addButton(tr("Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.s_b.valueChanged.connect(self._update)
        self.s_c.valueChanged.connect(self._update)
        self._update()

    def values(self):
        return self.s_b.value(), self.s_c.value() / 100

    def _update(self):
        out = de.adjust_images([self.small], *self.values())[0]
        self.preview.setPixmap(QPixmap.fromImage(to_qimage(out)))


class ImageSizeDialog(QDialog):
    """Bildgroesse (Pixel) und Aufloesung (dpi)."""

    def __init__(self, parent, shape, dpi):
        super().__init__(parent)
        self.setWindowTitle(tr("Bildgröße und Auflösung"))
        self.h, self.w = shape[:2]
        self.dpi0 = dpi
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.cb = QComboBox()
        self.cb.addItem(tr("Pixel neu berechnen (Größe auf dem Papier bleibt)"), "resample")
        self.cb.addItem(tr("Nur Auflösung ändern (Pixel bleiben, mm-Werte ändern sich)"), "dpi")
        form.addRow(tr("Art"), self.cb)
        self.sp_dpi = QSpinBox()
        self.sp_dpi.setRange(20, 2400)
        self.sp_dpi.setValue(int(dpi))
        self.sp_dpi.setSuffix(" dpi")
        form.addRow(tr("Neue Auflösung"), self.sp_dpi)
        self.lbl = QLabel()
        self.lbl.setObjectName("hint")
        form.addRow("", self.lbl)
        lay.addLayout(form)
        bb = QDialogButtonBox()
        bb.addButton(tr("Übernehmen"), QDialogButtonBox.ButtonRole.AcceptRole).setObjectName("primary")
        bb.addButton(tr("Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.cb.currentIndexChanged.connect(self._update)
        self.sp_dpi.valueChanged.connect(self._update)
        self._update()

    def factor(self):
        return self.sp_dpi.value() / self.dpi0 if self.cb.currentData() == "resample" else 1.0

    def _update(self):
        f, d = self.factor(), self.sp_dpi.value()
        w, h = int(round(self.w * f)), int(round(self.h * f))
        self.lbl.setText(tr("{} × {} px  →  {} × {} px,  {:.0f} × {:.0f} mm").format(
            self.w, self.h, w, h, w * 25.4 / d, h * 25.4 / d))


class SheetEditMixin:
    """Ganze Zeichnung bearbeiten (nur beim Ansehen einer Datei): zuschneiden, drehen, Helligkeit, Bildgroesse,
    Scan aufbereiten (Hintergrund, gerade ausrichten, entzerren)."""

    def _sheet_images(self):
        path = self.path_a or self.path_b
        g = self.cache.get("g_" + path) if path else None
        if not self.view_only or g is None or self.canvas.layer_lock.get("zeichnung"):
            self.banner.show_msg(tr("Das geht beim Ansehen einer einzelnen Zeichnung (Datei → Einzelne Zeichnung öffnen) "
                                    "und wenn die Ebene Zeichnung nicht gesperrt ist."), "info", timeout=8)
            return None, path
        c = self.cache.get("c_" + path)
        return [g] + ([c] if c is not None else []), path

    def _sheet_edit(self, new, ann_fn=None, scale=1.0, dpi=None, label=""):
        imgs, path = self._sheet_images()
        if imgs is None:
            return
        if ann_fn is not None:
            de.transform_anns(self.anns, ann_fn, scale)
        dpi0 = self.dpi_value()
        del self._edits[self._edit_ver:]
        self._edits.append(dict(path=path, full=True, before=imgs, after=new, dpi=(dpi0, dpi or dpi0)))
        self._edit_ver = len(self._edits)
        self._edit_saved = False
        self._set_sheet(path, new, dpi or dpi0)
        self.canvas.sel_rects = []
        self._ann_refresh(None)
        self._commit()
        self.act_save_drawing.setEnabled(True)
        if label:
            self.statusBar().showMessage(label + tr(" – Rückgängig: Strg+Z"), 6000)

    def _set_sheet(self, path, imgs, dpi):
        """Neue Bilddaten der Zeichnung einsetzen und die Ansicht neu aufbauen."""
        self.cache["g_" + path] = imgs[0]
        if len(imgs) > 1:
            self.cache["c_" + path] = imgs[1]
        if dpi != self.dpi_value():
            self.sp_dpi.blockSignals(True)
            self.sp_dpi.setValue(int(round(dpi)))
            self.sp_dpi.blockSignals(False)
            self._update_units()
        self.start_compute()

    # --- Zuschnitt: verstellbarer Rahmen, gilt nur fuer Ausgaben (Speichern, Drucken, Kopieren)
    def set_crop_frame(self):
        """Zuschneiden: die Bereichsauswahl wird zum Zuschnitt-Rahmen. Nichts wird geloescht; der Rahmen laesst sich
        an den Anfassern anpassen und wirkt erst beim Speichern, Drucken und Kopieren (auch im Vergleich)."""
        bbox = self._area_bbox(clip=False)
        if bbox is None:
            self.banner.show_msg(tr("Erst mit dem Werkzeug „Bereich“ (B) den Teil aufziehen, der bleiben soll."),
                                 "info", timeout=8)
            return
        ox, oy = self.origin
        self.crop_frame = (bbox[0] + ox, bbox[1] + oy, bbox[2] + ox, bbox[3] + oy)   # global wie Zonen
        self.canvas.sel_rects = []
        self._set_tool("hand")
        self._refresh_frame()
        self._commit()
        self.banner.show_msg(tr("Zuschnitt gesetzt: gilt beim Speichern, Drucken und Kopieren. Rand an den Anfassern "
                                "anpassen; aufheben unter Bearbeiten → Zuschnitt aufheben."), "info",
                             action=(tr("Aufheben"), self.clear_crop_frame), timeout=12)

    def clear_crop_frame(self):
        if getattr(self, "crop_frame", None) is not None:
            self.crop_frame = None
            self._refresh_frame()
            self._commit()

    def _refresh_frame(self):
        f = getattr(self, "crop_frame", None)
        ox, oy = self.origin
        self.canvas.crop_frame = None if f is None else (f[0] - ox, f[1] - oy, f[2] - ox, f[3] - oy)
        for a in (getattr(self, "act_frame_clear", None), getattr(self, "act_frame_apply", None)):
            if a is not None:
                a.setEnabled(f is not None and (a is self.act_frame_clear or self.view_only))
                a.setVisible(f is not None)                # im Menue nur, solange es einen Rahmen gibt
        self.canvas.update()

    def _frame_edited(self, x0, y0, x1, y1):
        ox, oy = self.origin
        self.crop_frame = (x0 + ox, y0 + oy, x1 + ox, y1 + oy)
        self._refresh_frame()
        self._commit()

    def _frame_local(self):
        return self.canvas.crop_frame

    def _apply_frame(self, img):
        """Bild auf den Zuschnitt-Rahmen bringen (ausserhalb des Blatts: weisser Rand)."""
        f = self._frame_local()
        return img if f is None else de.crop_images([img], f)[0]

    def apply_crop_frame(self):
        """Zuschnitt endgueltig auf die Zeichnung anwenden (beim Ansehen einer einzelnen Zeichnung)."""
        f = self._frame_local()
        if f is None:
            return
        self.canvas.sel_rects = [f]
        self.crop_frame = None
        self._refresh_frame()
        self.sheet_crop()

    def sheet_crop(self):
        """Zeichnung endgueltig auf die Bereichsauswahl zuschneiden (ragt sie ueber das Blatt, wird es vergroessert,
        der neue Rand bekommt die Papierfarbe). Nur beim Ansehen einer einzelnen Zeichnung."""
        bbox = self._area_bbox(clip=False)
        if bbox is None:
            self.banner.show_msg(tr("Erst mit dem Werkzeug „Bereich“ (B) den Teil aufziehen, der bleiben soll."),
                                 "info", timeout=8)
            return
        imgs, _ = self._sheet_images()
        if imgs is None:
            return
        x0, y0 = bbox[0], bbox[1]
        new = de.crop_images(imgs, bbox, self.payload["res"].a)
        grown = new[0].shape[:2] != (min(bbox[3], imgs[0].shape[0]) - max(bbox[1], 0),
                                     min(bbox[2], imgs[0].shape[1]) - max(bbox[0], 0))
        self._sheet_edit(new, lambda x, y: (x - x0, y - y0),
                         label=(tr("Blatt vergrößert auf {} × {} px") if grown else tr("Zugeschnitten auf {} × {} px"))
                         .format(bbox[2] - bbox[0], bbox[3] - bbox[1]))

    def sheet_rotate(self, quarter):
        imgs, _ = self._sheet_images()
        if imgs is None:
            return
        self._sheet_edit(de.rotate_images(imgs, quarter), de.rotate_point_fn(imgs[0].shape, quarter),
                         label=tr("Gedreht"))

    def sheet_adjust(self):
        imgs, _ = self._sheet_images()
        if imgs is None:
            return
        dlg = AdjustDialog(self, imgs[-1])
        if dlg.exec() != QDialog.DialogCode.Accepted or dlg.values() == (0, 1.0):
            return
        self._sheet_edit(de.adjust_images(imgs, *dlg.values()), label=tr("Helligkeit/Kontrast geändert"))

    def sheet_size(self):
        imgs, _ = self._sheet_images()
        if imgs is None:
            return
        dlg = ImageSizeDialog(self, imgs[0].shape, self.dpi_value())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        f, dpi = dlg.factor(), dlg.sp_dpi.value()
        if abs(f - 1) < 1e-6 and dpi == self.dpi_value():
            return
        new = de.resize_images(imgs, f) if abs(f - 1) > 1e-6 else [im.copy() for im in imgs]
        self._sheet_edit(new, (lambda x, y: (x * f, y * f)) if abs(f - 1) > 1e-6 else None, f, dpi,
                         label=tr("Bildgröße {} × {} px, {} dpi").format(new[0].shape[1], new[0].shape[0], dpi))

    # --- Scan aufbereiten: Hintergrund ausgleichen, gerade ausrichten, entzerren
    def _sheet_ink(self):
        res = (self.payload or {}).get("res")
        return getattr(res, "a", None)

    def sheet_background(self):
        imgs, _ = self._sheet_images()
        if imgs is None:
            return
        dlg = BackgroundDialog(self, imgs[-1])
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            new = de.flatten_background(imgs, *dlg.values())
        finally:
            QApplication.restoreOverrideCursor()
        self._sheet_edit(new, label=tr("Hintergrund ausgeglichen"))

    def sheet_straighten(self):
        imgs, _ = self._sheet_images()
        if imgs is None:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            angle = de.skew_angle(imgs[0])
        finally:
            QApplication.restoreOverrideCursor()
        dlg = StraightenDialog(self, imgs[-1], angle)
        r = dlg.exec()
        if r == StraightenDialog.LINE:
            self.start_straighten_line()
        elif r == QDialog.DialogCode.Accepted:
            self._straighten(dlg.angle())

    def start_straighten_line(self):
        imgs, _ = self._sheet_images()
        if imgs is not None:
            self._set_tool("straighten")

    def _straighten_line(self, x0, y0, x1, y1):
        """Nachgezeichnete Kante: so drehen, dass sie waagerecht bzw. senkrecht liegt."""
        self._set_tool("hand")
        self._straighten(de.line_angle(x0, y0, x1, y1))

    def _straighten(self, angle):
        if abs(angle) < 0.005:
            self.statusBar().showMessage(tr("Die Zeichnung liegt schon gerade."), 5000)
            return
        imgs, _ = self._sheet_images()
        if imgs is None:
            return
        new, fn = de.rotate_angle_images(imgs, angle, self._sheet_ink())
        self._sheet_edit(new, fn, label=tr("Um {:.2f}° gedreht").format(angle))

    def sheet_perspective(self):
        imgs, _ = self._sheet_images()
        if imgs is None:
            return
        dlg = PerspectiveDialog(self, imgs[-1], self.dpi_value())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        q, size, dpi = dlg.result()
        new, fn = de.warp_quad(imgs, q, size, self._sheet_ink())
        w0, _h0 = de.quad_size(q)
        self._sheet_edit(new, fn, size[0] / max(1, w0), dpi,
                         label=tr("Entzerrt auf {} × {} px").format(size[0], size[1]))


def _ok_cancel(dlg, lay, ok=None):
    bb = QDialogButtonBox()
    bb.addButton(ok or tr("Übernehmen"), QDialogButtonBox.ButtonRole.AcceptRole).setObjectName("primary")
    bb.addButton(tr("Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    return bb


class BackgroundDialog(QDialog):
    """Hintergrund ausgleichen oder ersetzen (Schatten, Falten, Vergilbung) mit Vorschau."""

    def __init__(self, parent, img):
        super().__init__(parent)
        self.setWindowTitle(tr("Hintergrund ausgleichen"))
        k = min(1.0, 520 / img.shape[1], 340 / img.shape[0])     # Vorschau passt ganz ins Fenster
        self.small = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        self.color = None
        lay = QVBoxLayout(self)
        hint = QLabel(tr("Rechnet Schatten, Falten und vergilbtes Papier heraus: das Papier wird gleichmäßig, die "
                         "Linien bleiben."))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(460, 320)
        lay.addWidget(self.preview, 1)
        form = QFormLayout()
        self.s_str = QSlider(Qt.Orientation.Horizontal)
        self.s_str.setRange(0, 100)
        self.s_str.setValue(50)
        self.s_str.setToolTip(tr("Höher = auch kräftigere Flecken und Knicke werden weiß; zu hoch lässt helle Linien "
                                 "verblassen"))
        form.addRow(tr("Stärke"), self.s_str)
        row = QHBoxLayout()
        self.cb_paper = QComboBox()
        self.cb_paper.addItem(tr("Weiß"), "white")
        self.cb_paper.addItem(tr("Eigene Farbe …"), "color")
        row.addWidget(self.cb_paper, 1)
        self.sw = QLabel()
        self.sw.setFixedSize(22, 22)
        row.addWidget(self.sw)
        form.addRow(tr("Papier"), row)
        lay.addLayout(form)
        _ok_cancel(self, lay)
        self.s_str.valueChanged.connect(self._update)
        self.cb_paper.activated.connect(self._paper)
        self._update()

    def _paper(self):
        if self.cb_paper.currentData() == "color":
            c = QColorDialog.getColor(QColor(245, 240, 225) if self.color is None else
                                      QColor(self.color[2], self.color[1], self.color[0]), self, tr("Papierfarbe"))
            if c.isValid():
                self.color = (c.blue(), c.green(), c.red())
            elif self.color is None:
                self.cb_paper.setCurrentIndex(0)
        else:
            self.color = None
        self._update()

    def values(self):
        return self.s_str.value(), self.color

    def _update(self):
        self.sw.setStyleSheet("" if self.color is None else
                              "background: rgb({},{},{}); border: 1px solid gray;".format(*self.color[::-1]))
        out = de.flatten_background([self.small], *self.values())[0]
        self.preview.setPixmap(QPixmap.fromImage(to_qimage(out)))


class StraightenDialog(QDialog):
    """Gerade ausrichten: Winkel (automatisch erkannt oder von Hand) mit Vorschau und Raster."""

    LINE = 2                                              # Rueckgabe: stattdessen Linie nachzeichnen

    def __init__(self, parent, img, angle=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Gerade ausrichten"))
        k = min(1.0, 520 / img.shape[1], 340 / img.shape[0])     # Vorschau passt ganz ins Fenster
        self.small = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        self.auto = angle
        lay = QVBoxLayout(self)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(460, 320)
        lay.addWidget(self.preview, 1)
        form = QFormLayout()
        self.sp = QDoubleSpinBox()
        self.sp.setRange(-45, 45)
        self.sp.setDecimals(2)
        self.sp.setSingleStep(0.1)
        self.sp.setSuffix(" °")
        self.sp.setToolTip(tr("Positiv = gegen den Uhrzeigersinn drehen"))
        self.sp.setValue(angle or 0.0)
        form.addRow(tr("Drehen um"), self.sp)
        self.lbl = QLabel(tr("Automatisch erkannt: {}°").format(QLocale().toString(angle, "f", 2)) if angle is not None else
                          tr("Keine langen geraden Linien gefunden – Winkel von Hand eingeben oder eine Linie "
                             "nachzeichnen."))
        self.lbl.setObjectName("hint")
        self.lbl.setWordWrap(True)
        form.addRow("", self.lbl)
        lay.addLayout(form)
        row = QHBoxLayout()
        b = QPushButton(tr("Automatisch"))
        b.setEnabled(angle is not None)
        b.clicked.connect(lambda: self.sp.setValue(self.auto or 0.0))
        row.addWidget(b)
        b = QPushButton(tr("An Linie nachzeichnen …"))
        b.setToolTip(tr("Im Bild eine Kante nachziehen, die waagerecht oder senkrecht sein soll"))
        b.clicked.connect(lambda: self.done(self.LINE))
        row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        _ok_cancel(self, lay)
        self.sp.valueChanged.connect(self._update)
        self._update()

    def angle(self):
        return self.sp.value()

    def _update(self):
        out = de.rotate_angle_images([self.small], self.angle())[0][0]
        out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR) if out.ndim == 2 else out.copy()
        h, w = out.shape[:2]
        for x in range(0, w, 40):                         # Raster zum Vergleichen
            out[:, x] = (out[:, x] * 0.5 + np.array((235, 160, 60)) * 0.5).astype(np.uint8)
        for y in range(0, h, 40):
            out[y, :] = (out[y, :] * 0.5 + np.array((235, 160, 60)) * 0.5).astype(np.uint8)
        self.preview.setPixmap(QPixmap.fromImage(to_qimage(out)))


class QuadEditor(QWidget):
    """Bild mit vier verschiebbaren Ecken und Lupe an der gezogenen Ecke."""

    changed = Signal()

    def __init__(self, img, quad):
        super().__init__()
        self.img = img
        self.qimg = to_qimage(img)
        self.quad = [list(map(float, q)) for q in quad]
        self.drag = None
        self.setMinimumSize(560, 420)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def _geom(self):
        h, w = self.img.shape[:2]
        k = min((self.width() - 20) / w, (self.height() - 20) / h)
        return k, (self.width() - w * k) / 2, (self.height() - h * k) / 2

    def _to_w(self, x, y):
        k, ox, oy = self._geom()
        return QPointF(ox + x * k, oy + y * k)

    def _to_i(self, p):
        k, ox, oy = self._geom()
        h, w = self.img.shape[:2]
        return min(max((p.x() - ox) / k, 0), w), min(max((p.y() - oy) / k, 0), h)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        k, ox, oy = self._geom()
        h, w = self.img.shape[:2]
        p.drawImage(QRectF(ox, oy, w * k, h * k), self.qimg)
        poly = QPolygonF([self._to_w(*q) for q in self.quad])
        p.setPen(QPen(QColor(ACCENT), 2))
        p.setBrush(QColor(37, 99, 235, 40))
        p.drawPolygon(poly)
        for i, q in enumerate(self.quad):
            p.setBrush(QColor("white") if i != self.drag else QColor(ACCENT))
            p.drawEllipse(self._to_w(*q), 7, 7)
        if self.drag is not None:                         # Lupe: Ausschnitt um die Ecke, vierfach
            x, y = self.quad[self.drag]
            r = 30
            src = QRectF(x - r, y - r, 2 * r, 2 * r)
            c = self._to_w(x, y)
            size = 140
            tx = c.x() + 20 if c.x() + 20 + size < self.width() else c.x() - 20 - size
            ty = c.y() + 20 if c.y() + 20 + size < self.height() else c.y() - 20 - size
            dst = QRectF(tx, ty, size, size)
            p.setPen(QPen(QColor(ACCENT), 2))
            p.setBrush(QColor("white"))
            p.drawRect(dst)
            p.drawImage(dst, self.qimg, src)
            p.setPen(QPen(QColor("#e11d48"), 1))
            p.drawLine(QPointF(dst.center().x(), dst.top()), QPointF(dst.center().x(), dst.bottom()))
            p.drawLine(QPointF(dst.left(), dst.center().y()), QPointF(dst.right(), dst.center().y()))
        p.end()

    def mousePressEvent(self, e):
        pos = e.position()
        d = [(pos - self._to_w(*q)).manhattanLength() for q in self.quad]
        i = int(np.argmin(d))
        if d[i] < 40:
            self.drag = i
            self.update()

    def mouseMoveEvent(self, e):
        if self.drag is not None:
            self.quad[self.drag] = list(self._to_i(e.position()))
            self.update()

    def mouseReleaseEvent(self, _e):
        if self.drag is not None:
            self.drag = None
            self.update()
            self.changed.emit()


class PerspectiveDialog(QDialog):
    """Entzerren: vier Ecken des Blatts setzen (automatisch erkannt), Format waehlen, Vorschau."""

    def __init__(self, parent, img, dpi):
        super().__init__(parent)
        self.setWindowTitle(tr("Entzerren (4 Ecken)"))
        self.full_shape = img.shape[:2]
        self.k = min(1.0, 900 / max(img.shape[:2]))
        small = cv2.resize(img, None, fx=self.k, fy=self.k, interpolation=cv2.INTER_AREA)
        self.small, self.dpi = small, dpi
        self.auto = de.find_sheet_quad(img)
        lay = QVBoxLayout(self)
        hint = QLabel(tr("Die Ecken des Blatts an die vier Punkte ziehen (Lupe hilft). Danach wird das Blatt "
                         "rechteckig gerechnet, z. B. bei einem Handyfoto."))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        body = QHBoxLayout()
        self.editor = QuadEditor(small, self.auto * self.k)
        body.addWidget(self.editor, 3)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(220, 220)
        body.addWidget(self.preview, 2)
        lay.addLayout(body, 1)
        form = QFormLayout()
        self.cb_fmt = QComboBox()
        self.cb_fmt.addItem(tr("Seitenverhältnis aus den Ecken"), None)
        for f in de.PAPER_MM:
            self.cb_fmt.addItem(tr("{} (mm stimmen danach)").format(f), f)
        form.addRow(tr("Format"), self.cb_fmt)
        self.lbl = QLabel()
        self.lbl.setObjectName("hint")
        form.addRow("", self.lbl)
        lay.addLayout(form)
        row = QHBoxLayout()
        b = QPushButton(tr("Blatt erkennen"))
        b.clicked.connect(lambda: self._set_quad(self.auto * self.k))
        row.addWidget(b)
        b = QPushButton(tr("Ecken an den Bildrand"))
        h, w = small.shape[:2]
        b.clicked.connect(lambda: self._set_quad(np.float32([(0, 0), (w, 0), (w, h), (0, h)])))
        row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        _ok_cancel(self, lay, tr("Entzerren"))
        self.editor.changed.connect(self._update)
        self.cb_fmt.currentIndexChanged.connect(self._update)
        self.resize(900, 640)
        self._update()

    def _set_quad(self, q):
        self.editor.quad = [list(map(float, p)) for p in q]
        self.editor.update()
        self._update()

    def quad(self):
        """Ecken im vollen Bild (oben links, im Uhrzeigersinn)."""
        return de.order_quad(np.float32(self.editor.quad) / self.k)

    def result(self):
        """(Ecken, Zielgroesse (w, h), neue dpi)."""
        q = self.quad()
        size, mm_px = de.warp_size(q, self.cb_fmt.currentData())
        if not mm_px:
            return q, size, self.dpi
        dpi = max(20, round(25.4 / mm_px))                 # ganze dpi; Groesse passend, damit die mm genau stimmen
        f = dpi * mm_px / 25.4
        return q, (int(round(size[0] * f)), int(round(size[1] * f))), dpi

    def _update(self):
        q, size, dpi = self.result()
        self.lbl.setText(tr("Ergebnis: {} × {} px,  {:.0f} × {:.0f} mm bei {:.0f} dpi").format(
            size[0], size[1], size[0] * 25.4 / dpi, size[1] * 25.4 / dpi, dpi))
        f = min(1.0, 320 / max(size))
        out = de.warp_quad([self.small], q * self.k, (max(1, int(size[0] * f)), max(1, int(size[1] * f))))[0][0]
        self.preview.setPixmap(QPixmap.fromImage(to_qimage(out)))


class OcrPdfMixin:
    """Durchsuchbares PDF aus einem Scan (Texterkennung) und Vektorisieren."""

    def export_searchable_pdf(self):
        if not self._need_result():
            return
        c = self.canvas
        side = "A"                                         # im Vergleich: die gerade gezeigte Zeichnung
        if not self.view_only:
            side = "B" if c.mode in ("B", "N") or (c.mode in ("K", "S", "Y") and c._side == "B") else "A"
        path = (self.path_a if side == "A" else self.path_b) or self.path_a or self.path_b
        # Text direkt aus der PDF nur, wenn das Bild der Datei entspricht (Einzelansicht, ohne Bearbeitung)
        pdf = (self.view_only and path.lower().endswith(".pdf") and dv.available() and not getattr(self, "_edit_ver", 0)
               and self._frame_local() is None)
        if not pdf and not rep.ocr_available() and not self.ensure_ocr(tr("Text für ein durchsuchbares PDF zu lesen")):
            return
        base = os.path.splitext(os.path.basename(path))[0] + "_durchsuchbar.pdf"
        out = self._save_dialog(tr("Durchsuchbares PDF speichern"), tr("PDF (*.pdf)"), base)
        if not out:
            return
        page, dpi = (self.sp_pa if side == "A" else self.sp_pb).value(), self.dpi_value()
        img = self.export_render(side, self.act_overlays.isChecked(), legend=False)
        plain = self.export_render(side, False, legend=False)   # Texterkennung auf dem Bild in Ergebnislage
        gray = plain.min(axis=2) if plain.ndim == 3 else plain

        boxes = rep.redaction_boxes(self.anns)

        def work(ctx):
            lines = dv.text_lines(path, page, dpi) if pdf else []
            if not lines:
                ctx.progress(0.02, tr("Texterkennung"))
                lines = rep.ocr_lines(gray, progress=lambda f: ctx.progress(0.05 + 0.85 * f, tr("Texterkennung")),
                                      cancel=ctx.cancelled)
            ctx.progress(0.92, tr("Schreibe PDF"))
            lines = [ln for ln in lines if not any(ln[0] < b[2] and ln[2] > b[0] and ln[1] < b[3] and ln[3] > b[1]
                                                   for b in boxes)]   # kein Text unter Schwaerzungen
            return rep.build_searchable_pdf(out, img, lines, dpi, os.path.basename(path))
        self._run_job(work, tr("Erzeuge durchsuchbares PDF …"),
                      lambda n: self.banner.show_msg(tr("Gespeichert: {} ({} Textzeilen durchsuchbar)").format(out, n),
                                                     "info", timeout=12))


class VectorizeDialog(QDialog):
    def __init__(self, parent, has_area):
        super().__init__(parent)
        self.setWindowTitle(tr("Vektorisieren"))
        lay = QVBoxLayout(self)
        h = QLabel(tr("Wandelt die Pixel der Zeichnung in Linien um und speichert sie als SVG, PDF oder DXF "
                      "(für CAD). Text wird nicht als Text erkannt, sondern als Linien gezeichnet."))
        h.setWordWrap(True)
        h.setObjectName("hint")
        lay.addWidget(h)
        form = QFormLayout()
        self.cb_mode = QComboBox()
        self.cb_mode.addItem(tr("Mittellinien – einzelne Linien, gut für CAD (DXF)"), "center")
        self.cb_mode.addItem(tr("Umrisse – sieht genau aus wie das Original"), "outline")
        form.addRow(tr("Art"), self.cb_mode)
        self.cb_area = QComboBox()
        self.cb_area.addItem(tr("Ganze Zeichnung"), "all")
        if has_area:
            self.cb_area.addItem(tr("Nur der gewählte Bereich"), "area")
            self.cb_area.setCurrentIndex(1)
        form.addRow(tr("Bereich"), self.cb_area)
        self.sp_eps = QDoubleSpinBox()
        self.sp_eps.setRange(0.3, 5.0)
        self.sp_eps.setSingleStep(0.1)
        self.sp_eps.setValue(1.0)
        self.sp_eps.setSuffix(" px")
        self.sp_eps.setToolTip(tr("Wie weit eine Linie vom Pixelverlauf abweichen darf. Größer = weniger Punkte, "
                                  "glattere Linien; kleiner = genauer"))
        form.addRow(tr("Vereinfachen"), self.sp_eps)
        self.cb_fmt = QComboBox()
        for txt, ext in ((tr("SVG (Grafikprogramme, Browser)"), ".svg"), (tr("PDF (Vektor)"), ".pdf"),
                         (tr("DXF (CAD, Maße in mm)"), ".dxf")):
            self.cb_fmt.addItem(txt, ext)
        form.addRow(tr("Format"), self.cb_fmt)
        lay.addLayout(form)
        bb = QDialogButtonBox()
        bb.addButton(tr("Speichern …"), QDialogButtonBox.ButtonRole.AcceptRole).setObjectName("primary")
        bb.addButton(tr("Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class VectorizeMixin:
    def vectorize_drawing(self):
        if not self._need_result():
            return
        c = self.canvas
        dlg = VectorizeDialog(self, bool(c.sel_rects))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        ext = dlg.cb_fmt.currentData()
        name = os.path.splitext(os.path.basename(self.path_a or self.path_b or "zeichnung"))[0] + "_vektor" + ext
        out = self._save_dialog(tr("Vektoren speichern"), dlg.cb_fmt.currentText().split(" (")[0] + f" (*{ext})", name)
        if not out:
            return
        if not out.lower().endswith(ext):
            out += ext
        mode = c.mode if c.mode in ("A", "B") else ("B" if c.mode in ("N", "K", "S") or (c.mode == "Y" and c._side == "B")
                                                    else "A")
        ink = c.res.a if mode == "A" else c.res.b
        h, w = ink.shape
        bbox = self._area_bbox() if dlg.cb_area.currentData() == "area" else (0, 0, w, h)
        if dlg.cb_area.currentData() != "area" and self._frame_local() is not None:   # Zuschnitt
            f = self._frame_local()
            bbox = (max(0, f[0]), max(0, f[1]), min(w, f[2]), min(h, f[3]))
        x0, y0, x1, y1 = bbox
        part = np.ascontiguousarray(ink[y0:y1, x0:x1])
        if dlg.cb_area.currentData() == "area":            # mehrere Rechtecke: nur deren Inhalt
            part = part * de.region_mask(c.sel_rects, bbox)
        part = part.copy()
        for b in rep.redaction_boxes(self.anns):            # Geschwaerztes wird nicht vektorisiert
            part[max(0, int(b[1]) - y0):max(0, int(b[3]) + 1 - y0), max(0, int(b[0]) - x0):max(0, int(b[2]) + 1 - x0)] = 0
        vmode, eps, dpi, mm = dlg.cb_mode.currentData(), dlg.sp_eps.value(), self.dpi_value(), c.mm_px

        def work(ctx):
            ctx.progress(0.02, tr("Vektorisiere"))
            vec = de.vectorize(part, vmode, eps, progress=lambda f: ctx.progress(0.02 + 0.9 * f, tr("Vektorisiere")),
                               cancel=ctx.cancelled)
            ctx.progress(0.95, tr("Schreibe Datei"))
            return de.write_vectors(out, vec, (x1 - x0, y1 - y0), dpi, mm)
        self._run_job(work, tr("Vektorisiere …"),
                      lambda n: self.banner.show_msg(tr("Gespeichert: {} ({} Linien und Flächen)").format(out, n),
                                                     "info", timeout=12))
