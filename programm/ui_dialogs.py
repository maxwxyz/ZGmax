"""Dialoge: Ebenen/Farben, Revisionen, Stapelvergleich."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_widgets import Job
import csv


# ----------------------------------------------------------------- Ebenen und Farben
class VectorFilterDialog(QDialog):
    def __init__(self, win, layers, colors, current):
        super().__init__(win)
        self.setWindowTitle(tr("Ebenen und Farben"))
        self.resize(460, 520)
        lay = QVBoxLayout(self)
        t = QLabel(tr("Nur H\u00e4kchen werden verglichen. So lassen sich z. B. Bema\u00dfung oder Schraffur ausblenden. "
                   "Die Auswahl gilt f\u00fcr A und B."))
        t.setWordWrap(True)
        t.setObjectName("hint")
        lay.addWidget(t)
        cur_l, cur_c = current
        self.lists = []
        for title, data, cur in ((tr("Ebenen"), layers, cur_l), (tr("Farben (Linien, Fl\u00e4chen, Text)"), colors, cur_c)):
            lay.addWidget(QLabel(title))
            lw = QListWidget()
            for k, n in sorted(data.items(), key=lambda kv: -kv[1]):
                it = QListWidgetItem(f"{k}   ({n})")
                it.setData(Qt.ItemDataRole.UserRole, k)
                if k.startswith("#"):
                    pm = QPixmap(16, 16)
                    pm.fill(QColor(k))
                    it.setIcon(QIcon(pm))
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Checked if cur is None or k in cur else Qt.CheckState.Unchecked)
                lw.addItem(it)
            lay.addWidget(lw, 1)
            row = QHBoxLayout()
            for txt, st in ((tr("Alle"), Qt.CheckState.Checked), (tr("Keine"), Qt.CheckState.Unchecked)):
                b = QPushButton(txt)
                b.clicked.connect(lambda _=False, w=lw, s=st: [w.item(i).setCheckState(s) for i in range(w.count())])
                row.addWidget(b)
            row.addStretch()
            lay.addLayout(row)
            self.lists.append(lw)
        row = QHBoxLayout()
        row.addStretch()
        b1, b2 = QPushButton(tr("Abbrechen")), QPushButton(tr("\u00dcbernehmen"))
        b2.setObjectName("primary")
        b1.clicked.connect(self.reject)
        b2.clicked.connect(self.accept)
        row.addWidget(b1)
        row.addWidget(b2)
        lay.addLayout(row)

    def result_filter(self):
        out = []
        for lw in self.lists:
            keys = [lw.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lw.count())
                    if lw.item(i).checkState() == Qt.CheckState.Checked]
            out.append(None if len(keys) == lw.count() else set(keys))
        return tuple(out)


# ----------------------------------------------------------------- Revisionen (A -> B -> C ...)
class RevisionDialog(QDialog):
    HEAD = [tr("Schritt"), tr("Von"), tr("Nach"), tr("nur Alt (px)"), tr("nur Neu (px)"), tr("\u00c4nderungen"), tr("entfernt"), tr("neu"),
            tr("ge\u00e4ndert"), tr("verschoben")]

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.job = None
        self.rows = []
        self.setWindowTitle(tr("Revisionen vergleichen"))
        self.resize(900, 560)
        lay = QVBoxLayout(self)
        t = QLabel(tr("Mehrere Staende derselben Zeichnung in zeitlicher Reihenfolge (alt \u2192 neu) eintragen. "
                   "Jeder Stand wird mit dem vorherigen verglichen; unten entsteht die \u00c4nderungshistorie. "
                   "Es gelten die aktuellen Einstellungen (ohne Zonen und Ausschnitt)."))
        t.setWordWrap(True)
        t.setObjectName("hint")
        lay.addWidget(t)
        row = QHBoxLayout()
        self.lst = QListWidget()
        self.lst.setFixedHeight(130)
        row.addWidget(self.lst, 1)
        col = QVBoxLayout()
        for txt, fn in ((tr("Hinzuf\u00fcgen\u2026"), self._add), (tr("Nach oben"), lambda: self._move(-1)),
                        (tr("Nach unten"), lambda: self._move(1)), (tr("Entfernen"), self._remove)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            col.addWidget(b)
        col.addStretch()
        row.addLayout(col)
        lay.addLayout(row)
        self.table = QTableWidget(0, len(self.HEAD))
        self.table.setHorizontalHeaderLabels(self.HEAD)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self.table, 1)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setFixedHeight(80)
        lay.addWidget(self.logbox)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1)
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        self.chk_img = QCheckBox(tr("Ergebnisbild je Schritt speichern"))
        row.addWidget(self.chk_img)
        row.addStretch()
        self.btn_view = QPushButton(tr("Schritt im Viewer \u00f6ffnen"))
        self.btn_view.clicked.connect(self._open_step)
        self.btn_csv = QPushButton(tr("Historie (CSV) \u2026"))
        self.btn_csv.clicked.connect(self._csv)
        self.btn_go = QPushButton(tr("Vergleichen"))
        self.btn_go.setObjectName("primary")
        self.btn_go.clicked.connect(self.start)
        b = QPushButton(tr("Schlie\u00dfen"))
        b.clicked.connect(self.accept)
        for w in (self.btn_view, self.btn_csv, b, self.btn_go):
            row.addWidget(w)
        lay.addLayout(row)

    def _add(self):
        files, _ = QFileDialog.getOpenFileNames(self, tr("Staende hinzuf\u00fcgen"), self.win.settings.value("dir", ""),
                                                FILE_FILTER)
        for f in files:
            self.lst.addItem(f)

    def _move(self, d):
        r = self.lst.currentRow()
        if r < 0 or not (0 <= r + d < self.lst.count()):
            return
        it = self.lst.takeItem(r)
        self.lst.insertItem(r + d, it)
        self.lst.setCurrentRow(r + d)

    def _remove(self):
        r = self.lst.currentRow()
        if r >= 0:
            self.lst.takeItem(r)

    def start(self):
        files = [self.lst.item(i).text() for i in range(self.lst.count())]
        if len(files) < 2:
            QMessageBox.information(self, APP, tr("Bitte mindestens zwei Staende eintragen."))
            return
        params = self.win.params().copy(ignore=[])
        dpi = self.win.dpi_value()
        save_img = self.chk_img.isChecked()
        outdir = ""
        if save_img:
            outdir = QFileDialog.getExistingDirectory(self, tr("Ordner f\u00fcr die Ergebnisbilder"),
                                                      os.path.dirname(files[0]))
            if not outdir:
                return
        self.rows = []
        self.table.setRowCount(0)
        self.logbox.clear()
        self.bar.setRange(0, len(files) - 1)
        self.bar.setValue(0)
        self.btn_go.setEnabled(False)
        job = Job(None, self)
        self.job = job

        def work(log):
            quiet = lambda *_: None                          # noqa: E731
            prev = dp.ink_from_gray(dp.load_gray(files[0], 1, dpi), params.thr, params.flatten)
            for i in range(1, len(files)):
                log(f"[{i}/{len(files) - 1}] {os.path.basename(files[i - 1])}  ->  {os.path.basename(files[i])}")
                cur = dp.ink_from_gray(dp.load_gray(files[i], 1, dpi), params.thr, params.flatten)
                b = dp.prepare_pair(prev, cur, params.align, quiet)
                res = dp.run_compare(prev, b, params, quiet)
                regs = rep.find_regions(res)
                cnt = {k: sum(1 for r in regs if r["typ"] == k) for k in rep.TYPE_LABEL}
                row = [i, os.path.basename(files[i - 1]), os.path.basename(files[i]), int(res.oa.sum()),
                       int(res.ob.sum()), len(regs), cnt["entfernt"], cnt["neu"], cnt["geaendert"],
                       cnt["verschoben"]]
                if save_img:
                    img = dc.add_legend(dp.render_result(res), row[1], row[2], bool(res.moved.any()), tr("Revision"))
                    rep.draw_marks(img, regs)
                    cv2.imencode(".png", img)[1].tofile(os.path.join(outdir, f"rev{i:02d}_{os.path.splitext(row[2])[0]}.png"))
                self.rows.append(row)
                prev = cur
            return len(self.rows)

        job.fn = work
        job.log.connect(lambda m: (self.logbox.appendPlainText(m),
                                   m.startswith("[") and self.bar.setValue(int(m[1:m.index("/")]) - 1)))
        job.done.connect(self._done)
        job.failed.connect(lambda m: (self.logbox.appendPlainText(tr("FEHLER: ") + m), self.btn_go.setEnabled(True)))
        job.start()

    def _done(self, n):
        self.bar.setValue(self.bar.maximum())
        self.btn_go.setEnabled(True)
        self.table.setRowCount(len(self.rows))
        for r, row in enumerate(self.rows):
            for c, v in enumerate(row):
                it = QTableWidgetItem(str(v))
                if c >= 3:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, it)
        self.logbox.appendPlainText(tr("Fertig: {} Schritte.").format(n))

    def _open_step(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.rows):
            QMessageBox.information(self, APP, tr("Bitte zuerst einen Schritt in der Tabelle w\u00e4hlen."))
            return
        files = [self.lst.item(i).text() for i in range(self.lst.count())]
        self.win._set_file("A", files[r], compute=False)
        self.win._set_file("B", files[r + 1])
        self.accept()

    def _csv(self):
        if not self.rows:
            return
        path = self.win._save_dialog(tr("Historie speichern"), tr("CSV (*.csv)"), "revisionen.csv")
        if path:
            import csv
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(self.HEAD)
                w.writerows(self.rows)
            self.logbox.appendPlainText(tr("Gespeichert: {}").format(path))


# ----------------------------------------------------------------- Stapel-Dialog
class BatchDialog(QDialog):
    """Ordnervergleich: alle zueinander passenden Zeichnungen zweier Ordner (z. B. eigener Stand gegen
    Lieferanten-Datensatz), jede Seite. Uebersicht, welche Blaetter geaendert sind, was fehlt oder neu ist."""
    COLORS = {"changed": "#c2410c", "same": "#16a34a", "only": "#64748b", "error": "#dc2626"}

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.job = None
        self.results = []
        self.setWindowTitle(tr("Ordner vergleichen (Stapel)"))
        self.resize(820, 640)
        lay = QVBoxLayout(self)
        t = QLabel(tr("Vergleicht alle zueinander passenden Zeichnungen zweier Ordner, jede Seite, z. B. den eigenen "
                      "Stand gegen einen Lieferanten-Datensatz. Die Übersicht zeigt, welche Blätter geändert sind und "
                      "welche nur in einem Ordner liegen. Doppelklick öffnet ein Paar zum Prüfen."))
        t.setWordWrap(True)
        t.setObjectName("hint")
        lay.addWidget(t)
        self.ed = []
        form = QGridLayout()
        for i, label in enumerate((tr("Alter Stand (A)"), tr("Neuer Stand (B)"), tr("Ausgabeordner"))):
            e = QLineEdit()
            b = QPushButton(tr("Wählen …"))
            b.clicked.connect(lambda _=False, ed=e, lb=label: self._pick(ed, lb))
            form.addWidget(QLabel(label), i, 0)
            form.addWidget(e, i, 1)
            form.addWidget(b, i, 2)
            self.ed.append(e)
        lay.addLayout(form)
        for e, k in zip(self.ed, ("batch_a", "batch_b", "batch_out")):
            e.setText(win.settings.value(k, ""))
        opts = QGridLayout()
        self.chk_sub = QCheckBox(tr("Unterordner einbeziehen"))
        self.chk_idx = QCheckBox(tr("Revisionskennung im Dateinamen ignorieren (1234_B ↔ 1234_C)"))
        self.chk_img = QCheckBox(tr("Ergebnisbild je geändertem Blatt"))
        self.chk_img.setChecked(True)
        self.chk_csv = QCheckBox(tr("Änderungsliste (CSV) je Paar"))
        self.chk_pdf = QCheckBox(tr("PDF-Bericht je geändertem Paar (dauert länger)"))
        for k, c in enumerate((self.chk_sub, self.chk_idx, self.chk_img, self.chk_csv, self.chk_pdf)):
            c.setChecked(c.isChecked() or win.settings.value("batch_opt_" + str(k), "") == "true")
            opts.addWidget(c, k // 2, k % 2)
        lay.addLayout(opts)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("Zeichnung"), tr("Ergebnis"), tr("Änderungen"), tr("Seiten")])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.table.cellDoubleClicked.connect(self._open_pair)
        lay.addWidget(self.table, 3)
        self.lbl_sum = QLabel("")
        self.lbl_sum.setObjectName("sec")
        lay.addWidget(self.lbl_sum)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setMaximumHeight(90)
        lay.addWidget(self.logbox, 1)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1)
        self.bar.setTextVisible(False)
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        self.btn_open = QPushButton(tr("Ausgabeordner öffnen"))
        self.btn_open.clicked.connect(self._open_out)
        self.btn_go = QPushButton(tr("Starten"))
        self.btn_go.setObjectName("primary")
        self.btn_go.clicked.connect(self.start)
        self.btn_cancel = QPushButton(tr("Schließen"))
        self.btn_cancel.clicked.connect(self._close)
        row.addWidget(self.btn_open)
        row.addStretch()
        row.addWidget(self.btn_cancel)
        row.addWidget(self.btn_go)
        lay.addLayout(row)

    def _pick(self, ed, label):
        d = QFileDialog.getExistingDirectory(self, label, ed.text() or self.win.settings.value("dir", ""))
        if d:
            ed.setText(d)

    def _open_out(self):
        if self.ed[2].text():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.ed[2].text()))

    def _close(self):
        if self.job and self.job.isRunning():
            self.job.cancelled = True
            self.logbox.appendPlainText(tr("Abbruch angefordert … (nach dem aktuellen Blatt)"))
        else:
            self.accept()

    def _open_pair(self, row, _col=0):
        """Doppelklick: Paar in einem neuen Fenster vergleichen."""
        if not (0 <= row < len(self.results)):
            return
        r = self.results[row]
        if not (r.get("a") and r.get("b")):
            return
        w = self.win if not (self.win.path_a or self.win.path_b) else self.win.new_window()
        w._set_file("A", r["a"], compute=False)
        w._set_file("B", r["b"])
        if r.get("first_page", 1) > 1:
            w.sp_pa.setValue(r["first_page"])

    def _add_row(self, r):
        self.results.append(r)
        row = self.table.rowCount()
        self.table.insertRow(row)
        text = {"changed": tr("geändert"), "same": tr("gleich"), "error": tr("Fehler"),
                "only_a": tr("nur im alten Stand"), "only_b": tr("nur im neuen Stand")}[r["state"]]
        col = QColor(self.COLORS["only" if r["state"].startswith("only") else r["state"]])
        vals = [r["name"], "● " + text, str(r.get("changes", "")) if r["state"] in ("changed", "same") else "",
                r.get("pages_text", "")]
        for c, v in enumerate(vals):
            it = QTableWidgetItem(v)
            if c == 1:
                it.setForeground(col)
            if r.get("error") and c == 1:
                it.setToolTip(r["error"])
            self.table.setItem(row, c, it)
        self._summary()

    def _summary(self):
        n = {k: sum(1 for r in self.results if r["state"] == k) for k in ("changed", "same", "only_a", "only_b", "error")}
        self.lbl_sum.setText(tr("{} geändert · {} gleich · {} nur alt · {} nur neu · {} Fehler").format(
            n["changed"], n["same"], n["only_a"], n["only_b"], n["error"]))

    def start(self):
        da, db, out = (e.text().strip() for e in self.ed)
        if not (os.path.isdir(da) and os.path.isdir(db)):
            QMessageBox.information(self, APP, tr("Bitte beide Ordner wählen."))
            return
        save_any = self.chk_img.isChecked() or self.chk_csv.isChecked() or self.chk_pdf.isChecked()
        if save_any and not out:
            QMessageBox.information(self, APP, tr("Bitte einen Ausgabeordner wählen (oder nur die Übersicht: alle "
                                                  "Ausgaben abwählen)."))
            return
        for e, k in zip(self.ed, ("batch_a", "batch_b", "batch_out")):
            self.win.settings.setValue(k, e.text())
        for k, c in enumerate((self.chk_sub, self.chk_idx, self.chk_img, self.chk_csv, self.chk_pdf)):
            self.win.settings.setValue("batch_opt_" + str(k), "true" if c.isChecked() else "false")
        pairs, only_a, only_b = dp.batch_pairs(da, db, dc.RASTER_EXT | dc.VECTOR_EXT | dc.CAD_EXT,
                                               self.chk_sub.isChecked(), self.chk_idx.isChecked())
        if not pairs and not only_a and not only_b:
            QMessageBox.information(self, APP, tr("In den Ordnern wurden keine Zeichnungen gefunden."))
            return
        if out:
            os.makedirs(out, exist_ok=True)
        params = self.win.params().copy(ignore=[])
        dpi, n_scale = self.win.dpi_value(), self.win.scale_n()
        img_on, csv_on, pdf_on = self.chk_img.isChecked(), self.chk_csv.isChecked(), self.chk_pdf.isChecked()
        self.results = []
        self.table.setRowCount(0)
        self.bar.setRange(0, max(1, len(pairs)))
        self.bar.setValue(0)
        self.btn_go.setEnabled(False)
        self.btn_cancel.setText(tr("Abbrechen"))
        self.logbox.clear()
        job = Job(None, self)
        self.job = job

        def work(ctx):
            quiet = lambda *_: None                          # noqa: E731
            for name in only_a:
                ctx.preview(dict(name=name, state="only_a", a=os.path.join(da, name), b=None))
            for name in only_b:
                ctx.preview(dict(name=name, state="only_b", a=None, b=os.path.join(db, name)))
            for i, (name, pa_, pb_) in enumerate(pairs, 1):
                if job.cancelled:
                    ctx(tr("Abgebrochen."))
                    break
                ctx(f"[{i}/{len(pairs)}] {name}")
                try:
                    na, nb = dp.page_count(pa_), dp.page_count(pb_)
                    per_page, total = [], 0
                    for pg in range(1, min(na, nb) + 1):
                        a = dp.ink_from_gray(dp.load_gray(pa_, pg, dpi), params.thr, params.flatten)
                        b = dp.ink_from_gray(dp.load_gray(pb_, pg, dpi), params.thr, params.flatten)
                        b = dp.prepare_pair(a, b, params.align, quiet)
                        res = dp.run_compare(a, b, params, quiet)
                        regs = rep.find_regions(res)
                        cnt = sum(1 for r in regs if r["typ"] != "verschoben")
                        per_page.append(cnt)
                        total += cnt
                        if not cnt or not out:
                            continue
                        stem = os.path.splitext(os.path.basename(pa_))[0] + (f"_S{pg}" if min(na, nb) > 1 else "")
                        base = os.path.join(out, stem + "_diff")
                        if img_on:
                            info = tr("Toleranz {}px, Schraffur {}, Ausrichtung {}").format(params.tol, params.hatch,
                                                                                         params.align)
                            img = dc.add_legend(dp.render_result(res), os.path.basename(pa_), os.path.basename(pb_),
                                                bool(res.moved.any()), info)
                            fp, fmt = dc.resolve_output(base + ".png", None)
                            dc.save_output(img, fp, fmt, dpi, 95)
                        if csv_on:
                            rep.write_csv(base + "_aenderungen.csv", regs, dpi, n_scale)
                        if pdf_on:
                            rep.build_report(base + "_bericht.pdf", res, regs, os.path.basename(pa_),
                                             os.path.basename(pb_), dpi, "", None, 40, quiet, scale_n=n_scale)
                    changed = [k + 1 for k, c in enumerate(per_page) if c]
                    ptxt = tr("Seite {}").format(", ".join(map(str, changed))) if changed and len(per_page) > 1 else ""
                    if na != nb:
                        ptxt = (ptxt + "  " if ptxt else "") + tr("Seitenzahl {} → {}").format(na, nb)
                    state = "changed" if total or na != nb else "same"
                    ctx.preview(dict(name=name, state=state, changes=total, pages_text=ptxt, a=pa_, b=pb_,
                                     first_page=changed[0] if changed else 1))
                except (Exception, SystemExit) as e:             # noqa: BLE001
                    ctx.preview(dict(name=name, state="error", error=str(e), a=pa_, b=pb_))
                    ctx(tr("   FEHLER: {}").format(e))
            return len(pairs)

        job.fn = work
        job.log.connect(self._on_log)
        job.preview.connect(self._add_row)
        job.done.connect(self._done)
        job.failed.connect(lambda m: (self.logbox.appendPlainText(tr("FEHLER: ") + m), self._finish()))
        job.start()

    def _on_log(self, text):
        self.logbox.appendPlainText(text)
        if text.startswith("["):
            self.bar.setValue(int(text[1:text.index("/")]) - 1)

    def _done(self, n):
        self.bar.setValue(self.bar.maximum())
        out = self.ed[2].text().strip()
        if out and self.results:
            try:
                self._write_overview(out)
            except OSError as e:
                self.logbox.appendPlainText(tr("FEHLER: ") + str(e))
        self.logbox.appendPlainText(tr("Fertig: {} Paare verglichen.").format(n))
        self._finish()

    def _write_overview(self, out):
        """Uebersicht als CSV und PDF in den Ausgabeordner."""
        state = {"changed": tr("geändert"), "same": tr("gleich"), "error": tr("Fehler"),
                 "only_a": tr("nur im alten Stand"), "only_b": tr("nur im neuen Stand")}
        rows = [[r["name"], state[r["state"]], str(r.get("changes", "")) if r["state"] in ("changed", "same") else "",
                 r.get("pages_text", "") or r.get("error", "")] for r in self.results]
        with open(os.path.join(out, "uebersicht.csv"), "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([tr("Zeichnung"), tr("Ergebnis"), tr("Änderungen"), tr("Seiten")])
            w.writerows(rows)
        import pymupdf
        doc = pymupdf.open()
        head = [tr("Alter Stand (A): {}").format(self.ed[0].text()), tr("Neuer Stand (B): {}").format(self.ed[1].text()),
                tr("Erstellt: {:%d.%m.%Y %H:%M}").format(dt.datetime.now()), self.lbl_sum.text()]
        vals = [[(v,) if j == 1 and r["state"] in ("changed", "error") else v for j, v in enumerate(row)]
                for row, r in zip(rows, self.results)]
        rep._pdf_table(doc, tr("Ordnervergleich – Übersicht"), head,
                       [(tr("Zeichnung"), 330), (tr("Ergebnis"), 110), (tr("Änderungen"), 70), (tr("Seiten"), 270)], vals)
        doc.save(os.path.join(out, "uebersicht.pdf"), garbage=3, deflate=True)
        doc.close()
        self.logbox.appendPlainText(tr("Übersicht: {}").format(os.path.join(out, "uebersicht.pdf")))

    def _finish(self):
        self.btn_go.setEnabled(True)
        self.btn_cancel.setText(tr("Schließen"))
