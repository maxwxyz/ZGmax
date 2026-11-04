"""Hauptfenster: Textsuche in der Zeichnung (PDF-Text, sonst Texterkennung)."""
from i18n import tr
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
        lay.addWidget(QLabel(tr("Suchen")))
        self.ed_search = QLineEdit()
        self.ed_search.setPlaceholderText(tr("Text in der Zeichnung, z. B. 25 H7 oder Bohrung"))
        self.ed_search.setClearButtonEnabled(True)
        self.ed_search.setMinimumWidth(260)
        self.ed_search.returnPressed.connect(lambda: self.search_step(1))
        self.ed_search.textChanged.connect(lambda _: self.search_timer.start(300))
        lay.addWidget(self.ed_search)
        self.cb_search_in = QComboBox()
        self.cb_search_in.addItem(tr("in Neu"), "B")
        self.cb_search_in.addItem(tr("in Alt"), "A")
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
        close.setToolTip(tr("Suche schließen (Esc)"))
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
        self._bg_text_poll()                             # im Hintergrund fertig geworden?
        lines = self.cache.get(key)
        if lines is None:
            if self.running:
                self.lbl_search.setText(tr("Bitte warten …"))
                self.search_timer.start(800)
                return
            pdf = path.lower().endswith(".pdf") and dv.available()
            if not pdf and not rep.ocr_available():
                if not self.ensure_ocr(tr("Text in Bildern zu suchen")):
                    self.lbl_search.setText(tr("Ohne Texterkennung nur in PDF mit Text möglich."))
                    return
            dpi = self.dpi_value()
            src = ocrservice.source(path, page, dpi)     # der Erkennungsprozess laedt die Seite selbst

            def work(ctx):
                found = dv.text_lines(path, page, dpi) if pdf else []
                if not found:                            # Bild oder PDF ohne Text: Texterkennung
                    if not rep.ocr_available():
                        return []
                    ctx.progress(0.02, tr("Lese Text in der Zeichnung"))
                    found = ocrservice.lines(key, src=src, cancel=ctx.cancelled,   # wartet ggf. auf den Hintergrund
                                             progress=lambda f: ctx.progress(f, tr("Lese Text in der Zeichnung")))
                return found

            def done(found):
                self.cache[key] = found
                self.run_search()
            self.canvas.search_hits, self.canvas.search_cur = [], -1     # alte Treffer gelten nicht mehr
            self.canvas.update()
            self.lbl_search.setText(tr("Lese den Text der Zeichnung (einmalig) …"))
            self._run_job(work, tr("Lese Text …"), done)
            return
        sk = self.cache.get(ocrservice.skey(key)) or []   # schraege Texte, wo waagerecht nichts gefunden wurde
        extra = [l[:5] for l in sk if not any(rep._overlap(l, h) > 0.5 for h in lines)]
        raw = rep.find_text(list(lines) + extra, q)
        hits = [self._to_view(side, h) for h in raw]
        h0, w0 = self.canvas.shape
        hits = [h for h in hits if h[2] > 0 and h[3] > 0 and h[0] < w0 and h[1] < h0]
        self.canvas.search_hits = hits
        self.canvas.search_side = side
        self.canvas.search_cur = 0 if hits else -1
        self.lbl_search.setText(tr("{} Treffer").format(len(hits)) if hits else tr("Nicht gefunden"))
        if hits:
            self._show_hit()
        self.canvas.update()

    # --- Texterkennung im Hintergrund
    def _bg_text_on(self):
        return self.settings.value("bg_text", os.environ.get("ZGMAX_BG_OCR", "1") != "0", type=bool)

    def _set_bg_text(self, on):
        self.settings.setValue("bg_text", bool(on))
        if on:
            self._bg_text_start()
        else:
            for key in list(getattr(self, "_bg_keys", ())):
                if not ocrservice.result(key):
                    ocrservice.stop()
                    break
            self._bg_keys = set()

    def _bg_text_start(self):
        """Nach dem Laden: Text der Zeichnung(en) im Hintergrund lesen, fuer Textsuche, „Geaenderten Text finden“ und
        durchsuchbares PDF. Laeuft im eigenen Prozess mit niedriger Prioritaet (ocrservice); bei PDF mit echtem Text
        wird gleich dieser genommen."""
        if not hasattr(self, "_bg_keys"):
            self._bg_keys, self._bg_all = set(), set()
            self._bg_timer = QTimer(self)
            self._bg_timer.setInterval(500)
            self._bg_timer.timeout.connect(self._bg_text_poll)
        if self.payload is None or not self._bg_text_on() or not rep.ocr_available():
            return
        if not self._bg_keys:
            self._bg_all = set()                         # neue Runde fuer die Fortschrittsanzeige
        sides = ["A"] if self.view_only or not self.path_b else ["B", "A"]
        for side in sides:
            key, path, page = self._text_key(side)
            vk = ocrservice.vkey(key)
            have = lambda k: k in self.cache or ocrservice.busy(k)      # noqa: E731
            if have(key) and have(vk) and have(ocrservice.skey(key)):
                continue
            if key not in self.cache and path.lower().endswith(".pdf") and dv.available():
                try:
                    found = dv.text_lines(path, page, self.dpi_value())      # echter PDF-Text: schnell, gleich hier
                except Exception:                        # noqa: BLE001
                    found = []
                if found:                                # PDF-Text: senkrechte Masse liest „Geaenderten Text
                    self.cache[key] = found              # finden“ direkt aus dem PDF
                    continue
            src = ocrservice.source(path, page, self.dpi_value())   # Prozess laedt die Seite selbst (alle Ebenen)
            sk = ocrservice.skey(key)                    # zuletzt schraeg/kopfueber (zur Sicherheit)
            for k, vert in ((key, False), (vk, True), (sk, "skew")):   # erst waagerecht (Suche), dann senkrecht
                if not have(k):
                    ocrservice.submit(k, vertical=vert, src=src)
                    self._bg_keys.add(k)
                    self._bg_all.add(k)
        if self._bg_keys:
            self._bg_timer.start()
        self._bg_text_status()

    def _bg_text_poll(self):
        for key in list(getattr(self, "_bg_keys", ())):
            r = ocrservice.result(key)
            if r is not None:
                self.cache.setdefault(key, r)
                self._bg_keys.discard(key)
            elif not ocrservice.busy(key):               # abgebrochen oder fehlgeschlagen
                self._bg_keys.discard(key)
        if hasattr(self, "_bg_timer") and not self._bg_keys:
            self._bg_timer.stop()
        self._bg_text_status()

    def _bg_text_status(self):
        """Kleine Anzeige unten rechts: „Text: 60 %“, solange im Hintergrund gelesen wird."""
        lbl = getattr(self, "lbl_bg_text", None)
        if lbl is None:
            return
        keys = list(getattr(self, "_bg_keys", ()))
        if not keys:
            lbl.hide()
            return
        weight = lambda k: {"vert": 2.0, "skew": 3.0}.get(k[0], 1.0)   # noqa: E731 - Anzahl der Drehungen
        allk = self._bg_all
        done = sum(weight(k) * (ocrservice.progress(k) or 0.0 if k in self._bg_keys else 1.0) for k in allk)
        lbl.setText(tr("Text: {} %").format(int(100 * done / max(1.0, sum(weight(k) for k in allk)))))
        lbl.show()

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
        self.lbl_search.setText(tr("{} von {}").format(c.search_cur + 1, len(c.search_hits)))
        c.update()
