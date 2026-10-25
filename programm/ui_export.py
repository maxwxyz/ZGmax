"""Hauptfenster: Bild, Liste, Bericht, Druck."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_widgets import ApprovalDialog


class ExportMixin:
    """Teil des Hauptfensters (wird in MainWindow eingemischt)."""

    # --- Export
    def _saved(self, path):
        """Einheitliche Rueckmeldung nach dem Speichern einer Datei (Hinweisleiste und Protokoll)."""
        self._log(tr("Gespeichert: {}").format(path))
        self.banner.show_msg(tr("Gespeichert: {}").format(path), "info", timeout=10)

    def _need_result(self):
        if not self.payload:
            QMessageBox.information(self, APP, tr("Bitte zuerst vergleichen."))
            return False
        return True

    def _info(self):
        p = self.params()
        res = self.payload["res"]
        s = (tr("Toleranz {}px, Schraffur {}, Verschiebung {}, Objekt-Verschiebung {}px, Objekt-Drehung {}Grad, Kacheln {}x{}, Ausrichtung {}, Schwelle {}").format(p.tol, p.hatch, p.move, p.obj_shift, p.obj_rotate, res.nx, res.ny, p.align, p.thr))
        if self.crop:
            s += tr(", Ausschnitt {}x{}px").format(self.crop[2], self.crop[3])
        return s

    def _save_dialog(self, title, flt, default):
        d = self.settings.value("outdir", os.path.dirname(self.path_a or ""))
        path, _ = QFileDialog.getSaveFileName(self, title, os.path.join(d, default), flt)
        if path:
            self.settings.setValue("outdir", os.path.dirname(path))
        return path

    def export_render(self, mode, overlays, legend=None):
        """Baut das Ergebnisbild wie angezeigt (Ansicht + Markierungen + Anmerkungen + Legende).
        legend=None: wie in der Ansicht eingestellt (Ansicht > Legende anzeigen)."""
        if legend is None:
            legend = self.act_legend.isChecked()
        pl = self.payload
        res = pl["res"]
        if mode in ("A", "B", "K"):
            col = pl.get("color", (None, None))[1 if mode == "B" else 0] if self.canvas.show_color else None
            if col is None:
                col = 255 - (res.b if mode == "B" else res.a)
            out = col.copy() if col.ndim == 3 else cv2.cvtColor(col, cv2.COLOR_GRAY2BGR)
        elif mode == "O":
            a, b = res.a > 0, res.b > 0
            out = dc.render(a & ~b, b & ~a, a & b, None)
        elif mode == "N":
            b = res.b > 0
            out = dc.render(np.zeros_like(res.ob), res.ob, b & ~res.ob, None)
        elif mode == "R":
            a = res.a > 0
            out = dc.render(res.oa, np.zeros_like(res.oa), a & ~res.oa, None)
        else:
            out = dp.render_result(res)
        if not self.canvas.layer_on.get("zeichnung", True):        # Ebene Zeichnung ausgeblendet: leeres Papier
            out = np.full_like(out, 255)
        if overlays:
            if pl["regs"] and self.canvas.show_regs and self.canvas.layer_on.get("aenderungen", True):
                rep.draw_marks(out, getattr(self, "_regs_listed", pl["regs"]),     # wie in der Liste (auch im
                               cloud=self.act_clouds.isChecked())                   # Hintergrund lesbar)
            rep.draw_annotations(out, self._export_anns(), mm=self.canvas.mm_px)
        rep.apply_redactions(out, self.anns)        # Schwaerzen/Verpixeln immer, auch ohne Markierungen
        out = self._apply_frame(out)                # Zuschnitt-Rahmen (nur Ausgaben)
        if legend and mode in ("D", "S", "O", "N", "R"):
            out = dc.add_legend(out, os.path.basename(self.path_a), os.path.basename(self.path_b),
                                bool(res.moved.any()) and mode in ("D", "S"), self._info())
        return out

    def _print_options(self):
        """Druckdialog: was (ganzes Blatt, sichtbarer Ausschnitt, gewaehlter Bereich) und wie gross.
        Rueckgabe (was, faktor) mit faktor None = einpassen, sonst 1.0 = Originalgroesse; None = abgebrochen."""
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Drucken im Maßstab"))
        form = QFormLayout(dlg)
        cb_what, cb_size = QComboBox(), QComboBox()
        cb_what.addItem(tr("Ganzes Blatt"), "sheet")
        cb_what.addItem(tr("Sichtbarer Ausschnitt"), "view")
        if self._area_bbox() is not None:
            cb_what.addItem(tr("Gewählter Bereich (Werkzeug Bereich)"), "area")
            cb_what.setCurrentIndex(2)
        for txt, f in ((tr("Auf Papier einpassen"), None), (tr("100 % (Originalgröße des Blatts)"), 1.0),
                       ("50 %", 0.5), ("25 %", 0.25), ("200 %", 2.0)):
            cb_size.addItem(txt, f)
        cb_size.setCurrentIndex(1)
        cb_size.setToolTip(tr("100 % druckt maßstäblich: 10 mm auf dem Blatt sind 10 mm auf dem Papier. Passt es nicht "
                              "auf eine Seite, wird auf mehrere Seiten verteilt."))
        form.addRow(tr("Drucken:"), cb_what)
        form.addRow(tr("Größe auf dem Papier:"), cb_size)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return cb_what.currentData(), cb_size.currentData(), cb_size.currentText()

    def _print_box(self, what):
        """Druckbereich in Bildpixeln (x0, y0, x1, y1) oder None = ganzes Blatt."""
        h, w = self.canvas.shape
        if what == "area":
            return self._area_bbox()
        if what == "view":
            c = self.canvas
            x0, y0 = c.to_img(QPointF(0, 0))
            x1, y1 = c.to_img(QPointF(c.width(), c.height()))
            b = (max(0, int(x0)), max(0, int(y0)), min(w, int(np.ceil(x1))), min(h, int(np.ceil(y1))))
            return b if b[2] > b[0] and b[3] > b[1] else None
        return None

    def print_scaled(self):
        """Drucken im Massstab: 100 % = Originalgroesse des Blatts (aus dpi), sonst Einpassen oder Prozent; ganzes Blatt,
        sichtbarer Ausschnitt oder gewaehlter Bereich. Ist das Papier zu klein, wird auf mehrere Seiten verteilt.
        Unten auf jeder Seite steht, was und in welcher Groesse gedruckt wurde."""
        if not self._need_result():
            return
        from PySide6.QtGui import QPageLayout
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        opt = self._print_options()
        if opt is None:
            return
        what, factor, size_txt = opt
        mode = self.canvas.mode if self.canvas.mode in ("A", "B", "D", "O", "N", "R") else "D"
        out = self.export_render(mode, True, False)
        box = self._print_box(what)
        if box is not None:
            out = out[box[1]:box[3], box[0]:box[2]]
        out = np.ascontiguousarray(out)
        h, w = out.shape[:2]
        img = QImage(out.data, w, h, out.strides[0], QImage.Format.Format_BGR888).copy()
        pr = QPrinter(QPrinter.PrinterMode.HighResolution)
        pr.setPageOrientation(QPageLayout.Orientation.Landscape if w >= h else QPageLayout.Orientation.Portrait)
        if QPrintDialog(pr, self).exec() != QDialog.DialogCode.Accepted:
            return
        self._print_to(pr, img, factor, size_txt)

    def _print_to(self, pr, img, factor, size_txt):
        from PySide6.QtPrintSupport import QPrinter
        w, h = img.width(), img.height()
        pg = pr.pageRect(QPrinter.Unit.DevicePixel)
        dev_mm = pr.resolution() / 25.4
        foot_h = 5 * dev_mm                                 # Fusszeile: Datei, Groesse, Massstab
        avail_h = max(1.0, pg.height() - foot_h)
        if factor is None:
            f = min(pg.width() / w, avail_h / h)
        else:
            f = 25.4 / max(1, self.dpi_value()) * factor * dev_mm
        tw, th = pg.width() / f, avail_h / f
        name = os.path.basename(self.path_a or self.path_b or "")
        foot = f"{APP} · {name} · {size_txt}"
        if self.scale_n() != 1.0:
            foot += " · " + tr("Zeichnungsmaßstab 1 : {}").format(QLocale().toString(self.scale_n(), "g", 6))
        p = QPainter(pr)
        p.setFont(QFont(UI_FONT, 7))
        nx, ny = max(1, int(np.ceil(w / tw - 1e-9))), max(1, int(np.ceil(h / th - 1e-9)))
        for j in range(ny):
            for i in range(nx):
                if i or j:
                    pr.newPage()
                x, y = i * tw, j * th
                sw, sh = min(tw, w - x), min(th, h - y)
                p.drawImage(QRectF(0, 0, sw * f, sh * f), img, QRectF(x, y, sw, sh))
                part = tr("  ·  Seite {} von {}").format(j * nx + i + 1, nx * ny) if nx * ny > 1 else ""
                p.drawText(QRectF(0, pg.height() - foot_h, pg.width(), foot_h),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, foot + part)
        p.end()
        self._log(tr("Gedruckt: {}").format(size_txt))

    def copy_view(self):
        """Sichtbaren Ausschnitt wie angezeigt (ohne Legende) in die Zwischenablage."""
        if not self._need_result():
            return
        img = self.canvas.view_image()
        QGuiApplication.clipboard().setImage(img)
        self._log(tr("Ansicht in die Zwischenablage kopiert ({} × {} px)").format(img.width(), img.height()))
        self.statusBar().showMessage(tr("Ansicht in die Zwischenablage kopiert"), 4000)

    def export_image(self):
        if not self._need_result():
            return
        path = self._save_dialog(tr("Ergebnisbild speichern"), tr("PNG (*.png);;JPEG (*.jpg);;TIFF (*.tif);;PDF (*.pdf)"),
                                 "diff.png")
        if not path:
            return
        mode, overlays, dpi = self.canvas.mode, self.act_overlays.isChecked(), self.dpi_value()

        def work(log):
            out = self.export_render(mode, overlays)
            fp, fmt = dc.resolve_output(path, None)
            return dc.save_output(out, fp, fmt, dpi, 95)
        self._run_job(work, tr("Speichere \u2026"), lambda p: self._saved(path))

    def export_csv(self):
        if not self._need_result():
            return
        path = self._save_dialog(tr("\u00c4nderungsliste speichern"), tr("CSV (*.csv)"), "diff_aenderungen.csv")
        if not path:
            return
        pl, dpi, sn, spec = self.payload, self.dpi_value(), self.scale_n(), self._filter_spec()

        def work(log):
            self._ensure_regs(log)
            rep.write_csv(path, self.filter_regs(pl["regs"], spec), dpi, sn)   # wie die Liste: Filter, ohne Geloeschte
            return path
        self._run_job(work, tr("Speichere \u2026"), lambda p: (self._fill_table(), self._saved(p)))

    def export_pdf(self):
        if not self._need_result():
            return
        path = self._save_dialog(tr("PDF-Bericht speichern"), tr("PDF (*.pdf)"), "diff_bericht.pdf")
        if not path:
            return
        pl, info, dpi, idx = self.payload, self._info(), self.dpi_value(), self.index_info
        sn, anns, spec = self.scale_n(), self._export_anns(), self._filter_spec()
        names = (os.path.basename(self.path_a), os.path.basename(self.path_b))

        def work(log):
            self._ensure_regs(log)
            boxes = rep.redaction_boxes(self.anns)        # geschwaerzte Bereiche: auch im Bericht unkenntlich
            regs = [dict(g, text_a="", text_b="", dim="") if any(
                g["x"] < b[2] and g["x"] + g["w"] > b[0] and g["y"] < b[3] and g["y"] + g["h"] > b[1] for b in boxes)
                else g for g in self.filter_regs(pl["regs"], spec)]   # nur was in der Liste steht
            rep.build_report(path, rep.redact_result(pl["res"], self.anns), regs, names[0], names[1], dpi, info, idx,
                             40, log, anns=anns, scale_n=sn)
            return path
        self._run_job(work, tr("Erstelle Bericht \u2026"),
                      lambda p: (self._fill_table(), self._saved(p)))

    def copy_cli(self):
        if not (self.path_a and self.path_b):
            return
        p, d = self.params(), dp.Params()
        parts = ["python", "drawing_diff.py", self.path_a, self.path_b]
        for attr, flag in (("thr", tr("--thr")), ("align", tr("--align")), ("cell", tr("--cell")), ("max_shift", tr("--max-shift")),
                           ("tol", tr("--tol")), ("hatch", tr("--hatch")), ("move", tr("--move")), ("obj_shift", tr("--obj-shift")),
                           ("obj_rotate", tr("--obj-rotate")), ("min_area", tr("--min-area")),
                           ("ignore_border", tr("--ignore-border"))):
            if getattr(p, attr) != getattr(d, attr):
                parts += [flag, str(getattr(p, attr))]
        for z in p.ignore:
            parts += [tr("--ignore"), ",".join(map(str, z))]
        if self.crop:
            parts += [tr("--crop-a"), ",".join(map(str, self.crop))]
        if self.dpi_value() != 200:
            parts += [tr("--dpi"), str(self.dpi_value())]
        if not p.edge_noise:
            parts += [tr("--keep-edges")]
        cmd = " ".join(f'"{x}"' if (" " in x or "\\" in x) else x for x in parts)
        QGuiApplication.clipboard().setText(cmd)
        self._log(tr("Befehl in Zwischenablage (im Ordner \u201eprogramm\u201c ausf\u00fchren): ") + cmd)
