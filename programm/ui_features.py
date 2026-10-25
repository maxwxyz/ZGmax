"""Hauptfenster: Startseite, Zuletzt verwendet, automatische Sicherung, automatische Einstellung,
alle Seiten vergleichen, Schriftfeld lesen, Bereiche zuordnen, Pruefrundgang, Hilfe."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_dialogs import RevisionDialog


class BgTask(QThread):
    """Kleine Hintergrundarbeit (PDF pruefen, Vorschaubilder), unabhaengig vom Hauptjob."""
    result = Signal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.result.emit(self.fn())
        except Exception:                                    # noqa: BLE001
            log.exception("Hintergrundaufgabe fehlgeschlagen")
            self.result.emit(None)


class RegionPickDialog(QDialog):
    """Zeigt eine Zeichnung verkleinert; der Anwender zieht einen Rahmen auf. box() = (x, y, b, h) im Original."""

    def __init__(self, parent, gray, title, hint):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.full = gray.shape
        scr = QGuiApplication.primaryScreen().availableGeometry()
        k = min((scr.width() - 160) / gray.shape[1], (scr.height() - 260) / gray.shape[0], 1.0)
        small = cv2.resize(gray, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        self.k = k
        self.img = QImage(np.ascontiguousarray(small).data, small.shape[1], small.shape[0], small.strides[0],
                          QImage.Format.Format_Grayscale8).copy()
        lay = QVBoxLayout(self)
        t = QLabel(hint)
        t.setWordWrap(True)
        lay.addWidget(t)
        self.view = QLabel()
        self.view.setFixedSize(self.img.width(), self.img.height())
        self.view.setCursor(Qt.CursorShape.CrossCursor)
        self.view.installEventFilter(self)
        lay.addWidget(self.view, 0, Qt.AlignmentFlag.AlignCenter)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        self.ok = bb.button(QDialogButtonBox.StandardButton.Ok)
        self.ok.setEnabled(False)
        lay.addWidget(bb)
        self.r0 = self.r1 = None
        self._draw()

    def _draw(self):
        pm = QPixmap.fromImage(self.img)
        if self.r0 and self.r1:
            p = QPainter(pm)
            c = QColor(ACCENT)
            p.setPen(QPen(c, 2))
            c.setAlpha(40)
            p.setBrush(c)
            p.drawRect(QRectF(self.r0, self.r1).normalized())
            p.end()
        self.view.setPixmap(pm)

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Type.MouseButtonPress:
            self.r0 = self.r1 = ev.position()
        elif t == QEvent.Type.MouseMove and self.r0 is not None and ev.buttons():
            self.r1 = ev.position()
            self._draw()
        elif t == QEvent.Type.MouseButtonRelease and self.r0 is not None:
            self.r1 = ev.position()
            self._draw()
            r = QRectF(self.r0, self.r1).normalized()
            self.ok.setEnabled(r.width() > 10 and r.height() > 10)
        return False

    def box(self):
        r = QRectF(self.r0, self.r1).normalized()
        h, w = self.full
        x0, y0 = int(max(0, r.left() / self.k)), int(max(0, r.top() / self.k))
        x1, y1 = int(min(w, r.right() / self.k)), int(min(h, r.bottom() / self.k))
        return x0, y0, x1 - x0, y1 - y0


class FeaturesMixin:
    """Teil des Hauptfensters (wird in MainWindow eingemischt)."""

    # ----------------------------------------------------------------- Startseite, Zuletzt verwendet
    def show_start(self):
        self.start.set_files(self.path_a, self.path_b)
        self.start.set_recent(recent_list(self.settings))
        self.stack.setCurrentWidget(self.start)
        self._update_enabled()

    def open_view_only(self):
        d = self.settings.value("dir", "")
        path, _ = QFileDialog.getOpenFileName(self, tr("Zeichnung ansehen"), d, FILE_FILTER)
        if not path:
            return
        win = self.new_window() if self.payload is not None else self   # offener Vergleich bleibt erhalten
        win.path_b = None
        win.lbl_b.setText(tr("(nicht gewählt)"))
        win._set_file("A", path)

    def _doc_window(self):
        """Fenster fuer ein weiteres Dokument: ist hier schon etwas offen, ein neues Fenster - Markierungen,
        Pruefstand und Einstellungen eines Dokuments bleiben so getrennt."""
        return self.new_window() if (self.payload is not None or self.path_a or self.path_b) else self

    def open_recent(self, r):
        w = self._doc_window()
        if w is not self:
            w.open_recent(r)
            return
        if r.get("project"):
            if os.path.isfile(r["project"]):
                self.project_open(r["project"])
            else:
                self.banner.show_msg(tr("Projekt nicht gefunden: ") + r["project"], "warn", timeout=8)
            return
        missing = [p for p in (r.get("a"), r.get("b")) if p and not os.path.isfile(p)]
        if missing:
            QMessageBox.information(self, APP, tr("Datei nicht gefunden:\n") + "\n".join(missing))
            return
        self.path_b = None
        if r.get("a") and r.get("b"):
            self._set_file("A", r["a"], compute=False)
            self._set_file("B", r["b"])
        else:
            self.lbl_b.setText(tr("(nicht gewählt)"))
            self._set_file("A", r.get("a") or r.get("b"))

    def _fill_recent_menu(self, menu=None):
        menu = menu or self.menu_recent
        menu.clear()
        entries = recent_list(self.settings)
        for r in entries:
            menu.addAction(recent_label(r), lambda r=r: self.open_recent(r))
        if not entries:
            menu.addAction(tr("(leer)")).setEnabled(False)
        else:
            menu.addSeparator()
            menu.addAction(tr("Liste leeren"), lambda: self.settings.setValue("recent", "[]"))

    def _toggle_overview(self, on):
        self.canvas.show_overview = on
        self.settings.setValue("overview", "true" if on else "false")
        self.canvas.update()

    def open_revisions(self):
        RevisionDialog(self).exec()

    # ----------------------------------------------------------------- Hintergrund
    def run_background(self, fn, done):
        t = BgTask(fn, self)
        self._bg = getattr(self, "_bg", [])
        self._bg.append(t)
        t.result.connect(done)
        t.finished.connect(lambda t=t: self._bg.remove(t) if t in self._bg else None)
        t.start()

    # ----------------------------------------------------------------- Automatisch einstellen
    def auto_params(self):
        if not (self.path_a and self.path_b):
            QMessageBox.information(self, APP, tr("Bitte zuerst beide Zeichnungen öffnen."))
            return
        pa, pb, ga_, gb_, dpi, vf = (self.path_a, self.path_b, self.sp_pa.value(), self.sp_pb.value(),
                                     self.dpi_value(), self.vfilter)
        base = self.params()

        def work(ctx):
            ctx.progress(0.05, tr("Lade"))
            ga = self._gray(pa, ga_, dpi, ctx, vf)
            gb = self._gray(pb, gb_, dpi, ctx, vf)
            ctx.progress(0.4, tr("Messe Linien und Ausrichtung"))
            return dp.suggest_params(ga, gb, dpi, base=base, log=ctx, cancel=ctx.cancelled)

        def done(r):
            p, why = r
            self.chk_flatten.setChecked(p.flatten)
            for w, v in ((self.s_thr, p.thr), (self.s_tol, p.tol), (self.s_area, p.min_area), (self.s_cell, p.cell),
                         (self.s_maxs, p.max_shift), (self.s_move, p.move), (self.s_obj, p.obj_shift),
                         (self.s_hatch, p.hatch)):
                w.set_silent(v)
            self.banner.show_msg(tr("<b>Automatisch eingestellt.</b> ") + " ".join(why), "info", timeout=30)
            self.start_compute()
        self._run_job(work, tr("Stelle automatisch ein …"), done)

    # ----------------------------------------------------------------- Alle Seiten vergleichen
    def compare_all_pages(self):
        if not (self.path_a and self.path_b):
            QMessageBox.information(self, APP, tr("Bitte zuerst beide Zeichnungen öffnen."))
            return
        n = min(self.n_pages_a, self.n_pages_b)
        if n < 2:
            QMessageBox.information(self, APP, tr("Die Dateien haben nur eine Seite."))
            return
        pa, pb, dpi, params = self.path_a, self.path_b, self.dpi_value(), self.params().copy(ignore=[])

        def work(ctx):
            out = {}
            quiet = lambda *_: None                          # noqa: E731
            for i in range(1, n + 1):
                ctx.check()
                lo, hi = (i - 1) / n, i / n
                ctx.progress(lo, tr("Seite {} von {}").format(i, n))
                a = dp.ink_from_gray(dp.load_gray(pa, i, dpi), params.thr, params.flatten)
                b = dp.prepare_pair(a, dp.ink_from_gray(dp.load_gray(pb, i, dpi), params.thr, params.flatten), params.align, quiet)
                res = dp.run_compare(a, b, params, quiet, cancel=ctx.cancelled,
                                     progress=lambda f, t, lo=lo, hi=hi, i=i: ctx.progress(lo + (hi - lo) * f,
                                                                                          tr("Seite {} von {}").format(i, n)))
                regs = rep.find_regions(res)
                out[i] = len([r for r in regs if r["typ"] != "verschoben"])
                ctx(tr("Seite {}: {} Änderungen").format(i, out[i]))
            return out

        def done(out):
            self.page_summary = out
            self._update_page_labels()
            for i, cnt in out.items():
                it = self.list_pages.item(i - 1)
                if it is not None:
                    it.setForeground(QColor("#c2410c" if cnt else "#16a34a"))
            changed = [str(i) for i, c in out.items() if c]
            self.sec_pages.set_open(True)
            self.act_left.setChecked(True)
            self.banner.show_msg((tr("Geänderte Seiten: ") + ", ".join(changed)) if changed else
                                 tr("Alle Seiten sind gleich."), "info", timeout=30)
        self._run_job(work, tr("Vergleiche alle Seiten …"), done)

    def _anns_of_page(self, n, single):
        """Markierungen (Blattkoordinaten) der Seite n bzw. des Seitenpaars n:n."""
        key = f"{n}" if single else f"{n}:{n}"
        if key == getattr(self, "_anns_key", None):
            st = self._state()
            return st["anns"]
        return copy.deepcopy(getattr(self, "page_anns", {}).get(key, []))

    def export_all_pages(self, kind="annpdf"):
        """Alle Seiten in einer PDF: 'annpdf' = Zeichnung (bzw. Vergleich) mit Markierungen als echte Kommentare,
        'report' = Aenderungsbericht ueber alle Seiten (nur im Vergleich)."""
        single = not (self.path_a and self.path_b) or self.view_only
        n = self.n_pages_a if single else min(self.n_pages_a, self.n_pages_b)
        if not self.payload:
            return
        if kind == "report" and single:
            QMessageBox.information(self, APP, tr("Der Änderungsbericht braucht zwei Zeichnungen."))
            return
        name = "alle_seiten_bericht.pdf" if kind == "report" else "alle_seiten_anmerkungen.pdf"
        path = self._save_dialog(tr("Alle Seiten speichern"), tr("PDF (*.pdf)"), name)
        if not path:
            return
        pa, pb, dpi, mm = self.path_a or self.path_b, self.path_b, self.dpi_value(), self.canvas.mm_px
        params = self.params().copy(ignore=[])
        hidden = tuple(sorted(getattr(self, "pdf_off", set())))
        anns = {i: [a for a in self._anns_of_page(i, single) if not a.get("hidden")] for i in range(1, n + 1)}
        names = (os.path.basename(pa or ""), os.path.basename(pb or ""))
        info = self._info()

        def work(ctx):
            import tempfile
            import pymupdf
            out = pymupdf.open()
            quiet = lambda *_: None                              # noqa: E731
            with tempfile.TemporaryDirectory() as tmp:
                for i in range(1, n + 1):
                    ctx.check()
                    ctx.progress((i - 1) / n, tr("Seite {} von {}").format(i, n))
                    if single:
                        img = dc.read_image(pa, i, dpi, hidden)
                        regs, res = [], None
                    else:
                        a = dp.ink_from_gray(dp.load_gray(pa, i, dpi), params.thr, params.flatten)
                        b = dp.prepare_pair(a, dp.ink_from_gray(dp.load_gray(pb, i, dpi), params.thr, params.flatten),
                                            params.align, quiet)
                        res = dp.run_compare(a, b, params, quiet, cancel=ctx.cancelled)
                        regs = [r for r in rep.find_regions(res) if r["typ"] != "verschoben"]
                        img = dp.render_result(res)
                    rep.apply_redactions(img, anns[i])
                    f = os.path.join(tmp, f"p{i}.pdf")
                    if kind == "report":
                        rep.build_report(f, rep.redact_result(res, anns[i]), regs, names[0], names[1], dpi, info,
                                         None, 40, quiet, anns=anns[i], scale_n=self.scale_n())
                    else:
                        rep.build_annotated_pdf(f, img, regs, anns[i], dpi, mm, names)
                    with pymupdf.open(f) as part:
                        out.insert_pdf(part, annots=True)
                out.save(path, deflate=True)
            out.close()
            return path
        self._run_job(work, tr("Speichere alle Seiten …"), self._saved)

    # ----------------------------------------------------------------- Schriftfeld
    def read_title_block(self):
        path = self.path_a or self.path_b
        if not path:
            QMessageBox.information(self, APP, tr("Bitte zuerst eine Zeichnung öffnen."))
            return
        page, dpi = self.sp_pa.value(), self.dpi_value()
        pdf = path.lower().endswith(".pdf") and dv.available()
        if not pdf and not self.ensure_ocr(tr("das Schriftfeld eines Bildes zu lesen")):
            return

        def work(ctx):
            ctx.progress(0.1, tr("Lese Schriftfeld"))
            texts = []
            if pdf:
                texts = dv.title_block_words(path, page)
            if not texts and rep.ocr_available():
                g = self._gray(path, page, dpi, ctx)
                h, w = g.shape
                crop = np.ascontiguousarray(g[int(h * 0.62):, int(w * 0.5):])   # dunkle Schrift auf hellem Papier
                texts = [(o[0], o[1], o[-1]) for o in rep.ocr_image(crop)]
            return rep.parse_title_block(texts)

        def done(info):
            if not info or not any(info.get(k) for k in ("scale", "number", "revision")):
                self.banner.show_msg(tr("Im Schriftfeld (rechts unten) wurden keine Angaben erkannt."), "warn", timeout=10)
                return
            self.title_info = info
            parts = []
            if info.get("number"):
                parts.append(tr("Zeichnungsnummer {}").format(info['number']))
            if info.get("revision"):
                parts.append(tr("Index {}").format(info['revision']))
            if info.get("scale"):
                parts.append(tr("Maßstab {}").format(info['scale']))
            self.banner.show_msg(tr("Schriftfeld: ") + ",  ".join(parts), "info", timeout=20)
            if info.get("scale_n") and abs(info["scale_n"] - self.scale_n()) > 1e-6:
                if QMessageBox.question(self, APP, f"Maßstab {info['scale']} für Messungen übernehmen?") == \
                        QMessageBox.StandardButton.Yes:
                    self.sp_scale.setValue(info["scale_n"])
        self._run_job(work, tr("Lese Schriftfeld …"), done)

    # ----------------------------------------------------------------- Bereiche zuordnen
    def match_regions(self):
        if not (self.path_a and self.path_b):
            QMessageBox.information(self, APP, tr("Bitte zuerst beide Zeichnungen öffnen."))
            return
        if self.running:
            return
        dpi, vf = self.dpi_value(), self.vfilter
        try:
            ga = self._gray(self.path_a, self.sp_pa.value(), dpi, self._log, vf)
            gb = self._gray(self.path_b, self.sp_pb.value(), dpi, self._log, vf)
        except dc.DiffError as e:
            self.banner.show_msg(str(e), "error")
            return
        da = RegionPickDialog(self, ga, tr("Bereich in A (alt)"), tr("Schritt 1 von 2: In der alten Zeichnung den Bereich "
                              "aufziehen, der verglichen werden soll."))
        if da.exec() != QDialog.DialogCode.Accepted:
            return
        db = RegionPickDialog(self, gb, tr("Bereich in B (neu)"), tr("Schritt 2 von 2: In der neuen Zeichnung den "
                              "passenden Bereich aufziehen. Größenunterschiede gleicht das Programm aus."))
        if db.exec() != QDialog.DialogCode.Accepted:
            return
        self.crop, self.crop_b = da.box(), db.box()
        self.btn_crop_off.setEnabled(True)
        self.lbl_crop.setText(tr("Aktuell: zugeordnete Bereiche A {} × {} px, B {} × {} px").format(self.crop[2], self.crop[3], self.crop_b[2], self.crop_b[3]))
        self.start_compute()

    # ----------------------------------------------------------------- Pruefrundgang
    def _ordered_regs(self):
        pl = self.payload
        if not pl or not pl["regs_done"]:
            return []
        types = self._filter_types()
        return [r for r in pl["regs"] if not types or r["typ"] in types]

    def review_step(self, d):
        """Zur naechsten (d=1) bzw. vorigen (d=-1) Aenderung; vorwaerts bevorzugt noch offene."""
        if not self.payload:
            return
        if not self.payload["regs_done"]:
            self.find_regs()
            return
        regs = self._ordered_regs()
        if not regs:
            return
        nrs = [r["nr"] for r in regs]
        cur = self.canvas.selected
        i = nrs.index(cur) if cur in nrs else (-1 if d > 0 else len(nrs))
        order = [(i + d * k) % len(nrs) for k in range(1, len(nrs) + 1)]
        if d > 0:
            open_ = [j for j in order if rep.reg_status(regs[j]) == "offen"]
            j = open_[0] if open_ else order[0]
            if not open_ and cur is not None:
                self.banner.show_msg(tr("Alle Änderungen sind bearbeitet."), "info", timeout=6)
        else:
            j = order[0]
        if not self.right.isVisible():
            self.act_right.setChecked(True)
        self._select_region_nr(nrs[j])
        self.canvas.setFocus()

    def _current_reg(self):
        return self._reg(self.canvas.selected) if self.canvas.selected is not None else None

    def review_set(self, status):
        r = self._current_reg()
        if r is None:
            self.review_step(1)
            return
        rep.set_status(r, status)
        nr = r["nr"]
        self._fill_table()
        self._dirty = True
        self._update_title()
        if status == "ok":
            self.review_step(1)
        else:
            self._select_region_nr(nr)
        self.canvas.setFocus()

    def review_comment(self):
        r = self._current_reg()
        if r is None:
            QMessageBox.information(self, APP, tr("Bitte zuerst eine Änderung wählen (N = nächste)."))
            return
        txt, ok = QInputDialog.getMultiLineText(self, tr("Kommentar zu Änderung {}").format(r['nr']), tr("Kommentar:"),
                                                r.get("comment", ""))
        if ok:
            r["comment"] = txt.strip()
            if r.get("status") is None and r.get("comment"):
                rep.set_status(r, "abgelehnt" if rep.reg_status(r) == "abgelehnt" else rep.reg_status(r))
            self._fill_table()
            self._select_region_nr(r["nr"])
            self._dirty = True
            self._update_title()

    def zones_from_rejected(self):
        """Abgelehnte Aenderungen (z. B. wiederkehrender Stempel, Datum im Schriftfeld) werden Zonen, die beim
        naechsten Vergleich nicht mehr verglichen werden - auch in Projekten fuer spaetere Staende."""
        regs = [r for r in (self.payload["regs"] if self.payload else []) if rep.reg_status(r) == "abgelehnt"]
        if not regs:
            QMessageBox.information(self, APP, tr("Es gibt keine als \u201eabgelehnt\u201c markierten \u00c4nderungen."))
            return
        ox, oy = self.origin
        for r in regs:
            self.zones.append((int(r["x"] - 10 + ox), int(r["y"] - 10 + oy), int(r["w"] + 20), int(r["h"] + 20)))
        self._refresh_zones()
        self._commit()
        self.banner.show_msg(tr("{} abgelehnte Änderungen als Zonen übernommen; sie werden nicht mehr verglichen.").format(len(regs)), "info", timeout=12, action=(tr("Jetzt neu vergleichen"), self.start_compute))

    # ----------------------------------------------------------------- Manuell ausrichten (3 Punkte)
    def start_manual_align(self):
        if not (self.payload and self.path_a and self.path_b) or self.view_only:
            QMessageBox.information(self, APP, tr("Bitte zuerst zwei Zeichnungen vergleichen."))
            return
        self._align_prev_mode = self.canvas.mode
        self.canvas.align_pts = {"A": [], "B": []}
        self._set_mode("Y")
        self._set_tool("align")
        self._align_hint()

    def _align_hint(self):
        a, b = self.canvas.align_pts["A"], self.canvas.align_pts["B"]
        n = len(b) + 1
        if len(a) == len(b):
            txt = tr("Punkt {} von 3: In der <b>alten</b> Zeichnung (links) einen markanten Punkt anklicken (Ecke, Kreuzung, Kreismitte).").format(n)
            if len(b) == 2:
                txt += tr(" Oder <b>Enter</b>: mit zwei Punkten ausrichten (Verschieben, Drehen, Ma\u00dfstab).")
        else:
            txt = tr("Punkt {} von 3: Denselben Punkt in der <b>neuen</b> Zeichnung (rechts) anklicken.").format(len(a))
        self.banner.show_msg(tr("Manuell ausrichten \u2013 ") + txt + tr("  Esc = abbrechen."), "info",
                             action=(tr("Abbrechen"), lambda: self._set_tool("hand")))

    def _align_point(self, side, x, y):
        pts = self.canvas.align_pts
        if side == "done":
            if len(pts["A"]) == len(pts["B"]) >= 2:
                self._apply_alignment()
            return
        want = "A" if len(pts["A"]) == len(pts["B"]) else "B"
        if side != want:
            self.banner.show_msg(tr("Bitte jetzt in der {} Zeichnung klicken.").format('alten (linken)' if want == 'A' else 'neuen (rechten)'), "warn", timeout=6)
            QTimer.singleShot(1500, self._align_hint)
            return
        pts[side].append((x, y))
        self.canvas.update()
        if len(pts["A"]) == len(pts["B"]) == 3:
            self._apply_alignment()
        else:
            self._align_hint()

    def _apply_alignment(self):
        """Transformation, die die Punkte von B auf die von A legt; wirkt zusaetzlich zur automatischen."""
        a = np.float32(self.canvas.align_pts["A"])
        b = np.float32(self.canvas.align_pts["B"])
        if len(a) >= 3:
            M = cv2.getAffineTransform(b[:3], a[:3])
        else:
            M, _ = cv2.estimateAffinePartial2D(b, a)
        if M is None or not np.isfinite(M).all() or abs(np.linalg.det(M[:, :2])) < 0.5:
            self.banner.show_msg(tr("Die Punkte passen nicht zusammen (z. B. vertauscht). Bitte neu setzen."), "warn",
                                 timeout=10)
            self.canvas.align_pts = {"A": [], "B": []}
            self._align_hint()
            return
        old = np.vstack([np.float32(self.manual_tf), [0, 0, 1]]) if self.manual_tf is not None else np.eye(3, dtype=np.float32)
        self.manual_tf = (np.vstack([M, [0, 0, 1]]) @ old)[:2].tolist()
        self.canvas.align_pts = {"A": [], "B": []}
        self._set_tool("hand")
        self._set_mode(getattr(self, "_align_prev_mode", "D") if self._align_prev_mode != "Y" else "D")
        self.act_align_reset.setEnabled(True)
        self._dirty = True
        res = float(np.abs(cv2.transform(b[None], M)[0] - a).max())
        self.banner.show_msg(tr("Ausgerichtet (Restabweichung der Punkte {:.1f} px). Es wird neu verglichen.").format(res),
                             "info", timeout=10, action=(tr("R\u00fcckg\u00e4ngig"), self.reset_manual_align))
        self.start_compute()

    def reset_manual_align(self):
        if self.manual_tf is None:
            return
        self.manual_tf = None
        self.act_align_reset.setEnabled(False)
        self._dirty = True
        self.banner.show_msg(tr("Manuelle Ausrichtung entfernt."), "info", timeout=6)
        self.start_compute()

    # ----------------------------------------------------------------- Automatische Sicherung
    # Je Fenster eine Datei "wiederherstellen-<Prozess>-<Fenster>.zgmax". Normales Schliessen loescht sie;
    # liegt beim Start eine Datei eines nicht mehr laufenden Prozesses herum, war es ein Absturz.
    def _autosave_path(self):
        if not hasattr(self, "_autosave_name"):
            FeaturesMixin._win_counter = getattr(FeaturesMixin, "_win_counter", 0) + 1
            self._autosave_name = f"wiederherstellen-{os.getpid()}-{FeaturesMixin._win_counter}{PROJECT_EXT}"
        return os.path.join(app_data_dir(), self._autosave_name)

    def autosave(self):
        """Sichert ungespeicherte Markierungen/Pruefung jede Minute (fuer den Fall eines Absturzes)."""
        if not getattr(self, "_dirty", False) or not (self.path_a or self.path_b):
            return
        try:
            data = self._project_data()
            data["autosave_of"] = self.project_path
            tmp = self._autosave_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self._autosave_path())
        except Exception:                                    # noqa: BLE001
            log.exception("Automatische Sicherung fehlgeschlagen")

    def clear_autosave(self):
        try:
            os.remove(self._autosave_path())
        except OSError:
            pass

    @staticmethod
    def _pid_alive(pid):
        if pid == os.getpid():
            return True
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except (OSError, ValueError):
            return False

    def check_autosave(self):
        """Nach einem Absturz: gesicherten Stand anbieten (nur Dateien nicht mehr laufender Programme)."""
        import glob
        if getattr(FeaturesMixin, "_autosave_checked", False):
            return
        FeaturesMixin._autosave_checked = True
        leftovers = []
        for path in glob.glob(os.path.join(app_data_dir(), "wiederherstellen*" + PROJECT_EXT)):
            parts = os.path.basename(path).split("-")
            pid = int(parts[1]) if len(parts) > 2 and parts[1].isdigit() else -1
            if not self._pid_alive(pid):
                leftovers.append(path)
        if not leftovers:
            return
        r = QMessageBox.question(self, APP, tr("Das Programm wurde beim letzten Mal nicht normal beendet. "
                                 "Ungespeicherte Markierungen und Pr\u00fcfergebnisse wiederherstellen?"))
        for k, path in enumerate(sorted(leftovers, key=os.path.getmtime, reverse=True)):
            if r == QMessageBox.StandardButton.Yes:
                win = self if k == 0 else self.new_window()
                win.project_open(path)
                win.project_path = None
                win._dirty = True
                win._update_title()
            try:
                os.remove(path)
            except OSError:
                pass

    # ----------------------------------------------------------------- Fenster und Schliessen
    def new_window(self):
        """Weiteres Fenster fuer einen anderen Vergleich (gleiches Programm, eigene Daten)."""
        import drawing_viewer
        w = drawing_viewer.MainWindow()
        drawing_viewer.WINDOWS.append(w)
        g = self.geometry()
        w.resize(self.size())
        w.move(g.x() + 40, g.y() + 40)
        w.show()
        return w

    def close_document(self):
        """Vergleich/Projekt schliessen, Programm bleibt offen (zurueck zur Startseite)."""
        if not self._maybe_save():
            return
        for job in list(self.jobs):
            job.cancel()
            job.wait(15000)
        self.running = self.pending = False
        self.path_a = self.path_b = None
        self.payload = None
        self.cache.clear()
        self.crop = self.crop_b = None
        self._crop_seen = None
        self.origin = (0, 0)
        self.anns.clear()
        self.zones.clear()
        self.pdf_off, self._comments_done = set(), set()
        self.crop_frame = None
        self.page_scales = {}
        self.page_anns, self._anns_key = {}, None
        self.project_path = None
        self.restore_regs = None
        self.index_info = None
        self.view_only = False
        for lbl in (self.lbl_a, self.lbl_b):
            lbl.setText(tr("(nicht gew\u00e4hlt)"))
            lbl.setToolTip("")
        self.btn_crop_off.setEnabled(False)
        self.lbl_crop.setText(tr("Aktuell: ganzes Blatt"))
        self.sec_pages.hide()
        self.n_pages_a = self.n_pages_b = 1
        self.canvas.clear()
        self._ann_refresh(None)
        self._refresh_zones()
        self._fill_table()
        self._reset_history()
        self.clear_autosave()
        self.banner.hide()
        self.act_left.setChecked(False)
        self.act_right.setChecked(False)
        self._set_view_only(False)
        self._update_title()
        self._busy(False, tr("Bereit"))
        self.show_start()

    # ----------------------------------------------------------------- Hilfe
    def show_keys(self):
        rows = [(tr("Mausrad"), tr("Zoomen (an der Mausposition)")),
                (tr("Trackpad: zwei Finger"), tr("Verschieben;  Aufziehen = Zoomen")),
                (tr("Leeres Papier ziehen"), tr("Verschieben (Werkzeug Auswahl)")),
                (tr("Mittlere Maustaste ziehen"), tr("Verschieben (jedes Werkzeug)")),
                (tr("Rechte Maustaste ziehen"), tr("Zoom-Rahmen (jedes Werkzeug)")),
                (tr("Rechtsklick"), tr("Menü")), (tr("Doppelklick ins Leere / F"), tr("Ganze Zeichnung")),
                (tr("+ / −, Pfeiltasten"), tr("Zoomen / Verschieben")),
                ("1 2 3 9 4 6", tr("Alt, Neu, Vergleich, Nebeneinander, Überlagern, Blinken")),
                (tr("Leertaste"), tr("Zwischen alt und neu wechseln")),
                (tr("V  M  T  W  Z"), tr("Auswahl, Messen, Text, Wolke, Zoom-Rahmen")),
                (tr("N / P"), tr("Nächste / vorige Änderung")),
                (tr("G / X / C"), tr("Geprüft / abgelehnt / Kommentar")),
                (tr("H / L / R"), tr("Markierungen ein/aus, Lupe, Ansicht drehen")),
                (tr("Entf"), tr("Gewählte Markierung löschen")), (tr("Esc"), tr("Werkzeug beenden")),
                (tr("Strg+Z / Strg+Umschalt+Z"), tr("Rückgängig / Wiederholen")),
                (tr("Strg+O / Strg+S / Strg+P"), tr("Projekt öffnen / speichern / drucken"))]
        mod = tr("⌘ (Befehlstaste)") if sys.platform == "darwin" else tr("Strg")
        html = (tr("<table cellspacing=6>") + "".join(f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in rows) +
                tr("</table><p>Auf dem Mac steht Strg für {}. Einzeltasten wirken, wenn das Bild den Fokus hat (einmal hineinklicken).</p>").format(mod))
        QMessageBox.information(self, tr("Tastenkürzel"), html)

    def open_logfile(self):
        p = os.path.join(app_data_dir(), "zeichnungsvergleich.log")
        if os.path.isfile(p):
            QDesktopServices.openUrl(QUrl.fromLocalFile(p))
        else:
            QMessageBox.information(self, APP, tr("Es gibt noch keine Logdatei."))

    def show_about(self):
        import drawing_viewer
        QMessageBox.about(self, APP, tr("<h3>{} {}</h3><p>{}: ansehen, messen, markieren, vergleichen und prüfen.</p><p>Logdatei und automatische Sicherung:<br>{}</p>").format(APP, drawing_viewer.VERSION, APP_SUBTITLE, app_data_dir()))

    # ----------------------------------------------------------------- PDF mit Anmerkungen
    def export_annotated_pdf(self):
        if not self._need_result():
            return
        if not dv.available():
            QMessageBox.information(self, APP, tr("Dafür wird PyMuPDF benötigt."))
            return
        path = self._save_dialog(tr("PDF mit Anmerkungen speichern"), tr("PDF (*.pdf)"), "vergleich_anmerkungen.pdf")
        if not path:
            return
        pl, dpi, mm = self.payload, self.dpi_value(), self.canvas.mm_px
        mode = self.canvas.mode if self.canvas.mode in ("A", "B", "D", "O", "N", "R") else "D"
        anns = self._export_anns()
        names = (os.path.basename(self.path_a or ""), os.path.basename(self.path_b or ""))
        # Nur was angezeigt wird: Aenderungen nur, wenn gesucht wurde, und nur die nach dem Filter sichtbaren
        shown = (self.act_overlays.isChecked() and self.canvas.show_regs and pl.get("regs_done") is not False
                 and self.canvas.layer_on.get("aenderungen", True))
        regs = copy.deepcopy(self._shown_regs()) if shown else []

        f = self._frame_local()
        if f is not None:                              # Zuschnitt: Lage der Kommentare mitverschieben
            for a in anns:
                shift_ann(a, -f[0], -f[1])
            regs = [dict(g, x=g["x"] - f[0], y=g["y"] - f[1]) for g in regs]

        def work(ctx):
            ctx.progress(0.1, tr("Erzeuge Bild"))
            img = self.export_render(mode, False, legend=False)
            ctx.progress(0.6, tr("Schreibe PDF"))
            rep.build_annotated_pdf(path, img, regs, anns, dpi, mm, names)
            return path
        self._run_job(work, tr("Erzeuge PDF mit Anmerkungen …"),
                      lambda p: self.banner.show_msg(tr("Gespeichert: {}").format(p), "info", timeout=10))
