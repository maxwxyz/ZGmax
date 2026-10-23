"""Hauptfenster: Textsuche in der Zeichnung (PDF-Text, sonst Texterkennung)."""
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_icons import icon


class SearchMixin:
    """Teil des Hauptfensters (wird in MainWindow eingemischt)."""

    def _build_search_bar(self):
        bar = QFrame()
        bar.setObjectName("searchbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.addWidget(QLabel("Suchen"))
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText("Text in der Zeichnung, z. B. 25 H7 oder Bohrung")
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.setMinimumWidth(260)
        self.ed_search.returnPressed.connect(lambda: self.search_step(1))
        self.ed_search.textChanged.connect(lambda _: self.search_timer.start(300))
        lay.addWidget(self.ed_search)
        self.cb_search_in = QComboBox()
        self.cb_search_in.addItem("in Neu", "B")
        self.cb_search_in.addItem("in Alt", "A")
        self.cb_search_in.currentIndexChanged.connect(lambda _: self.run_search())
        lay.addWidget(self.cb_search_in)
        for act in (self.act_search_prev, self.act_search_next):
            b = QToolButton()
            b.setDefaultAction(act)
            lay.addWidget(b)
        self.lbl_search = QLabel("")
        self.lbl_search.setObjectName("hint")
        lay.addWidget(self.lbl_search, 1)
        close = QToolButton()
        close.setText("✕")
        close.setToolTip("Suche schließen (Esc)")
        close.clicked.connect(self.close_search)
        lay.addWidget(close)
        QShortcut(QKeySequence("Escape"), self.ed_search, activated=self.close_search).setContext(
            Qt.ShortcutContext.WidgetShortcut)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.run_search)
        self.search_bar = bar
        bar.hide()
        return bar

    def open_search(self):
        if self.payload is None:
            return
        two = bool(self.path_a and self.path_b) and not self.view_only
        self.cb_search_in.setVisible(two)
        if two:                                          # Seite nach der aktuellen Ansicht vorschlagen
            self.cb_search_in.blockSignals(True)
            self.cb_search_in.setCurrentIndex(1 if self.canvas.mode in ("A", "R") else 0)
            self.cb_search_in.blockSignals(False)
        self.search_bar.show()
        self.ed_search.setFocus()
        self.ed_search.selectAll()
        if self.ed_search.text():
            self.run_search()

    def close_search(self):
        self.search_bar.hide()
        self.canvas.search_hits, self.canvas.search_cur = [], -1
        self.canvas.update()
        self.canvas.setFocus()

    def _search_side(self):
        if self.view_only or not (self.path_a and self.path_b):
            return "A"
        return self.cb_search_in.currentData()

    def _text_key(self, side):
        path = self.path_a if side == "A" else self.path_b
        page = (self.sp_pa if side == "A" else self.sp_pb).value()
        try:
            st = os.stat(path)
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            stamp = None
        return ("txt", path, page, self.dpi_value(), stamp), path, page

    def run_search(self):
        """Text sammeln (einmal je Datei/Seite, im Hintergrund) und Treffer zeigen."""
        if self.payload is None or not self.search_bar.isVisible():
            return
        q = self.ed_search.text().strip()
        if not q:
            self.canvas.search_hits, self.canvas.search_cur = [], -1
            self.lbl_search.setText("")
            self.canvas.update()
            return
        side = self._search_side()
        key, path, page = self._text_key(side)
        lines = self.cache.get(key)
        if lines is None:
            if self.running:
                self.lbl_search.setText("Bitte warten …")
                self.search_timer.start(800)
                return
            pdf = path.lower().endswith(".pdf") and dv.available()
            if not pdf and not rep.ocr_available():
                if not self.ensure_ocr("Text in Bildern zu suchen"):
                    self.lbl_search.setText("Ohne Texterkennung nur in PDF mit Text möglich.")
                    return
            dpi = self.dpi_value()

            def work(ctx):
                found = dv.text_lines(path, page, dpi) if pdf else []
                if not found:                            # Bild oder PDF ohne Text: Texterkennung
                    if not rep.ocr_available():
                        return []
                    ctx.progress(0.02, "Lese Text in der Zeichnung")
                    g = self._gray(path, page, dpi, ctx)
                    found = rep.ocr_lines(g, progress=lambda f: ctx.progress(f, "Lese Text in der Zeichnung"),
                                          cancel=ctx.cancelled)
                return found

            def done(found):
                self.cache[key] = found
                self.run_search()
            self.canvas.search_hits, self.canvas.search_cur = [], -1     # alte Treffer gelten nicht mehr
            self.canvas.update()
            self.lbl_search.setText("Lese den Text der Zeichnung (einmalig) …")
            self._run_job(work, "Lese Text …", done)
            return
        raw = rep.find_text(lines, q)
        hits = [self._to_view(side, h) for h in raw]
        h0, w0 = self.canvas.shape
        hits = [h for h in hits if h[2] > 0 and h[3] > 0 and h[0] < w0 and h[1] < h0]
        self.canvas.search_hits = hits
        self.canvas.search_side = side
        self.canvas.search_cur = 0 if hits else -1
        self.lbl_search.setText(f"{len(hits)} Treffer" if hits else "Nicht gefunden")
        if hits:
            self._show_hit()
        self.canvas.update()

    def _to_view(self, side, r):
        """Rechteck aus Original-Pixeln der Datei in die Koordinaten des angezeigten Ergebnisses."""
        x0, y0, x1, y1 = r
        vec = self.chk_vec.isChecked() and self.chk_vec.isEnabled()
        if side == "A" or self.view_only or vec:
            ox, oy = self.origin
            return x0 - ox, y0 - oy, x1 - ox, y1 - oy
        pts = dp.map_points_tf([(x0, y0), (x1, y0), (x0, y1), (x1, y1)], self.cache.get("tf"),
                               self.cache.get("box_b"), self.manual_tf)
        return pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()

    def search_step(self, d):
        c = self.canvas
        if not self.search_bar.isVisible():
            self.open_search()
            return
        if not c.search_hits:
            self.run_search()
            return
        c.search_cur = (c.search_cur + d) % len(c.search_hits)
        self._show_hit()

    def _show_hit(self):
        c = self.canvas
        x0, y0, x1, y1 = c.search_hits[c.search_cur]
        c.center_box(x0, y0, x1, y1)
        self.lbl_search.setText(f"{c.search_cur + 1} von {len(c.search_hits)}")
        c.update()
