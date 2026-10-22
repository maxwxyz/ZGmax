"""Dialoge: Ebenen/Farben, Revisionen, Stapelvergleich."""
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_widgets import Job


# ----------------------------------------------------------------- Ebenen und Farben
class VectorFilterDialog(QDialog):
    def __init__(self, win, layers, colors, current):
        super().__init__(win)
        self.setWindowTitle("Ebenen und Farben")
        self.resize(460, 520)
        lay = QVBoxLayout(self)
        t = QLabel("Nur H\u00e4kchen werden verglichen. So lassen sich z. B. Bema\u00dfung oder Schraffur ausblenden. "
                   "Die Auswahl gilt f\u00fcr A und B.")
        t.setWordWrap(True)
        t.setObjectName("hint")
        lay.addWidget(t)
        cur_l, cur_c = current
        self.lists = []
        for title, data, cur in (("Ebenen", layers, cur_l), ("Farben (Linien, Fl\u00e4chen, Text)", colors, cur_c)):
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
            for txt, st in (("Alle", Qt.CheckState.Checked), ("Keine", Qt.CheckState.Unchecked)):
                b = QPushButton(txt)
                b.clicked.connect(lambda _=False, w=lw, s=st: [w.item(i).setCheckState(s) for i in range(w.count())])
                row.addWidget(b)
            row.addStretch()
            lay.addLayout(row)
            self.lists.append(lw)
        row = QHBoxLayout()
        row.addStretch()
        b1, b2 = QPushButton("Abbrechen"), QPushButton("\u00dcbernehmen")
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
    HEAD = ["Schritt", "Von", "Nach", "nur Alt (px)", "nur Neu (px)", "\u00c4nderungen", "entfernt", "neu",
            "ge\u00e4ndert", "verschoben"]

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.job = None
        self.rows = []
        self.setWindowTitle("Revisionen vergleichen")
        self.resize(900, 560)
        lay = QVBoxLayout(self)
        t = QLabel("Mehrere Staende derselben Zeichnung in zeitlicher Reihenfolge (alt \u2192 neu) eintragen. "
                   "Jeder Stand wird mit dem vorherigen verglichen; unten entsteht die \u00c4nderungshistorie. "
                   "Es gelten die aktuellen Einstellungen (ohne Zonen und Ausschnitt).")
        t.setWordWrap(True)
        t.setObjectName("hint")
        lay.addWidget(t)
        row = QHBoxLayout()
        self.lst = QListWidget()
        self.lst.setFixedHeight(130)
        row.addWidget(self.lst, 1)
        col = QVBoxLayout()
        for txt, fn in (("Hinzuf\u00fcgen\u2026", self._add), ("Nach oben", lambda: self._move(-1)),
                        ("Nach unten", lambda: self._move(1)), ("Entfernen", self._remove)):
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
        self.chk_img = QCheckBox("Ergebnisbild je Schritt speichern")
        row.addWidget(self.chk_img)
        row.addStretch()
        self.btn_view = QPushButton("Schritt im Viewer \u00f6ffnen")
        self.btn_view.clicked.connect(self._open_step)
        self.btn_csv = QPushButton("Historie (CSV) \u2026")
        self.btn_csv.clicked.connect(self._csv)
        self.btn_go = QPushButton("Vergleichen")
        self.btn_go.setObjectName("primary")
        self.btn_go.clicked.connect(self.start)
        b = QPushButton("Schlie\u00dfen")
        b.clicked.connect(self.accept)
        for w in (self.btn_view, self.btn_csv, b, self.btn_go):
            row.addWidget(w)
        lay.addLayout(row)

    def _add(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Staende hinzuf\u00fcgen", self.win.settings.value("dir", ""),
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
            QMessageBox.information(self, APP, "Bitte mindestens zwei Staende eintragen.")
            return
        params = self.win.params().copy(ignore=[])
        dpi = self.win.dpi_value()
        save_img = self.chk_img.isChecked()
        outdir = ""
        if save_img:
            outdir = QFileDialog.getExistingDirectory(self, "Ordner f\u00fcr die Ergebnisbilder",
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
            prev = dp.ink_from_gray(dp.load_gray(files[0], 1, dpi), params.thr)
            for i in range(1, len(files)):
                log(f"[{i}/{len(files) - 1}] {os.path.basename(files[i - 1])}  ->  {os.path.basename(files[i])}")
                cur = dp.ink_from_gray(dp.load_gray(files[i], 1, dpi), params.thr)
                b = dp.prepare_pair(prev, cur, params.align, quiet)
                res = dp.run_compare(prev, b, params, quiet)
                regs = rep.find_regions(res)
                cnt = {k: sum(1 for r in regs if r["typ"] == k) for k in rep.TYPE_LABEL}
                row = [i, os.path.basename(files[i - 1]), os.path.basename(files[i]), int(res.oa.sum()),
                       int(res.ob.sum()), len(regs), cnt["entfernt"], cnt["neu"], cnt["geaendert"],
                       cnt["verschoben"]]
                if save_img:
                    img = dc.add_legend(dp.render_result(res), row[1], row[2], bool(res.moved.any()), "Revision")
                    rep.draw_marks(img, regs)
                    cv2.imencode(".png", img)[1].tofile(os.path.join(outdir, f"rev{i:02d}_{os.path.splitext(row[2])[0]}.png"))
                self.rows.append(row)
                prev = cur
            return len(self.rows)

        job.fn = work
        job.log.connect(lambda m: (self.logbox.appendPlainText(m),
                                   m.startswith("[") and self.bar.setValue(int(m[1:m.index("/")]) - 1)))
        job.done.connect(self._done)
        job.failed.connect(lambda m: (self.logbox.appendPlainText("FEHLER: " + m), self.btn_go.setEnabled(True)))
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
        self.logbox.appendPlainText(f"Fertig: {n} Schritte.")

    def _open_step(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.rows):
            QMessageBox.information(self, APP, "Bitte zuerst einen Schritt in der Tabelle w\u00e4hlen.")
            return
        files = [self.lst.item(i).text() for i in range(self.lst.count())]
        self.win._set_file("A", files[r], compute=False)
        self.win._set_file("B", files[r + 1])
        self.accept()

    def _csv(self):
        if not self.rows:
            return
        path = self.win._save_dialog("Historie speichern", "CSV (*.csv)", "revisionen.csv")
        if path:
            import csv
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(self.HEAD)
                w.writerows(self.rows)
            self.logbox.appendPlainText(f"Gespeichert: {path}")


# ----------------------------------------------------------------- Stapel-Dialog
class BatchDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.job = None
        self.setWindowTitle("Stapelvergleich")
        self.resize(640, 520)
        lay = QVBoxLayout(self)
        t = QLabel("Vergleicht alle gleich benannten Dateien aus zwei Ordnern nacheinander und speichert je Paar "
                   "ein Ergebnisbild. Es gelten die aktuellen Einstellungen (ohne Zonen und Ausschnitt).")
        t.setWordWrap(True)
        t.setObjectName("hint")
        lay.addWidget(t)
        self.ed = []
        for label in ("Ordner mit alten Zeichnungen (A)", "Ordner mit neuen Zeichnungen (B)", "Ausgabeordner"):
            lay.addWidget(QLabel(label))
            row = QHBoxLayout()
            e = QLineEdit()
            b = QPushButton("W\u00e4hlen\u2026")
            b.clicked.connect(lambda _=False, ed=e, lb=label: self._pick(ed, lb))
            row.addWidget(e, 1)
            row.addWidget(b)
            lay.addLayout(row)
            self.ed.append(e)
        for e, k in zip(self.ed, ("batch_a", "batch_b", "batch_out")):
            e.setText(win.settings.value(k, ""))
        self.chk_csv = QCheckBox("Zus\u00e4tzlich \u00c4nderungsliste (CSV) je Paar")
        self.chk_pdf = QCheckBox("Zus\u00e4tzlich PDF-Bericht je Paar (dauert l\u00e4nger)")
        lay.addWidget(self.chk_csv)
        lay.addWidget(self.chk_pdf)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        lay.addWidget(self.logbox, 1)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1)
        lay.addWidget(self.bar)
        row = QHBoxLayout()
        self.btn_open = QPushButton("Ausgabeordner \u00f6ffnen")
        self.btn_open.clicked.connect(self._open_out)
        self.btn_go = QPushButton("Starten")
        self.btn_go.setObjectName("primary")
        self.btn_go.clicked.connect(self.start)
        self.btn_cancel = QPushButton("Schlie\u00dfen")
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
            self.logbox.appendPlainText("Abbruch angefordert \u2026 (nach dem aktuellen Paar)")
        else:
            self.accept()

    def start(self):
        da, db, out = (e.text().strip() for e in self.ed)
        if not (os.path.isdir(da) and os.path.isdir(db)):
            QMessageBox.information(self, APP, "Bitte beide Eingabeordner w\u00e4hlen.")
            return
        if not out:
            QMessageBox.information(self, APP, "Bitte einen Ausgabeordner w\u00e4hlen.")
            return
        for e, k in zip(self.ed, ("batch_a", "batch_b", "batch_out")):
            self.win.settings.setValue(k, e.text())
        exts = dc.RASTER_EXT | dc.VECTOR_EXT

        def scan(f):
            return {os.path.splitext(n)[0].lower(): n for n in sorted(os.listdir(f))
                    if os.path.splitext(n)[1].lower() in exts}
        fa, fb = scan(da), scan(db)
        names = sorted(set(fa) & set(fb))
        if not names:
            QMessageBox.information(self, APP, "Keine gleich benannten Dateien in beiden Ordnern gefunden.")
            return
        os.makedirs(out, exist_ok=True)
        params = self.win.params().copy(ignore=[])
        dpi, csv_on, pdf_on = self.win.dpi_value(), self.chk_csv.isChecked(), self.chk_pdf.isChecked()
        n_scale = self.win.scale_n()
        self.bar.setRange(0, len(names))
        self.bar.setValue(0)
        self.btn_go.setEnabled(False)
        self.btn_cancel.setText("Abbrechen")
        self.logbox.clear()
        job = Job(None, self)
        self.job = job

        def work(log):
            ok = 0
            quiet = lambda *_: None                          # noqa: E731
            for i, n in enumerate(names, 1):
                if job.cancelled:
                    log("Abgebrochen.")
                    break
                log(f"[{i}/{len(names)}] {fa[n]}  <->  {fb[n]}")
                try:
                    pa_, pb_ = os.path.join(da, fa[n]), os.path.join(db, fb[n])
                    a = dp.ink_from_gray(dp.load_gray(pa_, 1, dpi), params.thr)
                    b = dp.ink_from_gray(dp.load_gray(pb_, 1, dpi), params.thr)
                    b = dp.prepare_pair(a, b, params.align, quiet)
                    res = dp.run_compare(a, b, params, quiet)
                    img = dp.render_result(res)
                    info = f"Toleranz {params.tol}px, Schraffur {params.hatch}, Ausrichtung {params.align}"
                    img = dc.add_legend(img, fa[n], fb[n], bool(res.moved.any()), info)
                    base = os.path.join(out, os.path.splitext(fa[n])[0] + "_diff")
                    fp, fmt = dc.resolve_output(base + ".png", None)
                    dc.save_output(img, fp, fmt, dpi, 95)
                    regs = rep.find_regions(res) if (csv_on or pdf_on) else []
                    if csv_on:
                        rep.write_csv(base + "_aenderungen.csv", regs, dpi, n_scale)
                    if pdf_on:
                        rep.build_report(base + "_bericht.pdf", res, regs, fa[n], fb[n], dpi, info, None, 40,
                                         quiet, scale_n=n_scale)
                    log("   fertig")
                    ok += 1
                except (Exception, SystemExit) as e:             # noqa: BLE001
                    log(f"   FEHLER: {e}")
            return ok, len(names)

        job.fn = work
        job.log.connect(self._on_log)
        job.done.connect(self._done)
        job.failed.connect(lambda m: (self.logbox.appendPlainText("FEHLER: " + m), self._finish()))
        job.start()

    def _on_log(self, text):
        self.logbox.appendPlainText(text)
        if text.startswith("["):
            self.bar.setValue(int(text[1:text.index("/")]) - 1)

    def _done(self, r):
        self.bar.setValue(self.bar.maximum())
        self.logbox.appendPlainText(f"\nFertig: {r[0]} von {r[1]} Paaren verglichen.")
        self._finish()

    def _finish(self):
        self.btn_go.setEnabled(True)
        self.btn_cancel.setText("Schlie\u00dfen")
