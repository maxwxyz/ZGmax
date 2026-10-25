"""Hauptfenster: Seitenleisten links (Einstellungen) und rechts (Markierungen, Aenderungen, Ebenen)."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_icons import icon
from ui_widgets import Collapsible, ElideLabel, PanelScroll, Section, SliderRow


class PanelsMixin:
    """Teil des Hauptfensters (wird in MainWindow eingemischt)."""

    # ----------------------------------------------------------------- Seitenleiste links: Einstellungen
    def _build_left(self):
        self.left = QWidget()
        self.left.setObjectName("panel")
        self.left.setMaximumWidth(560)                  # Mindestbreite: aus dem Inhalt (PanelScroll)
        inner = QWidget()
        inner.setObjectName("panel")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(12, 8, 12, 12)
        lay.setSpacing(8)

        sec = Section(tr("Zeichnungen"))
        self.lbl_a, self.lbl_b = ElideLabel(tr("(nicht gewählt)")), ElideLabel(tr("(nicht gewählt)"))
        self.file_rows = {}
        for tag, lbl, which in ((tr("A  –  alt"), self.lbl_a, "A"), (tr("B  –  neu"), self.lbl_b, "B")):
            head = QWidget()
            row = QHBoxLayout(head)
            row.setContentsMargins(0, 0, 0, 0)
            t = QLabel(tag)
            t.setObjectName("sec")
            row.addWidget(t)
            row.addStretch()
            btn = QPushButton(tr("Öffnen …"))
            btn.clicked.connect(lambda _=False, w=which: self.open_file(w))
            row.addWidget(btn)
            sec.body.addWidget(head)
            lbl.setObjectName("file")
            sec.body.addWidget(lbl)
            self.file_rows[which] = (head, t, lbl)
        self.btn_swap = QPushButton(tr("A und B tauschen"))
        self.btn_swap.clicked.connect(self.swap_ab)
        sec.body.addWidget(self.btn_swap)
        self.btn_add_b = QPushButton(tr("Mit anderer Zeichnung vergleichen …"))   # nur beim Ansehen
        self.btn_add_b.setObjectName("primary")
        self.btn_add_b.setToolTip(tr("Zweite Zeichnung (neu) öffnen; dann wird verglichen"))
        self.btn_add_b.clicked.connect(lambda: self.open_file("B"))
        self.btn_add_b.setVisible(False)
        sec.body.addWidget(self.btn_add_b)
        lay.addWidget(sec)

        sec = Section(tr("Empfindlichkeit"))
        self.sec_sens = sec
        self.s_tol = SliderRow(tr("Toleranz (px)"), 0, 10, 2, 1, 0,
                               tr("Linien mit weniger Abstand gelten als gleich. Höher = weniger Rauschen."))
        sec.body.addWidget(self.s_tol)
        self.s_area = SliderRow(tr("Mindestgröße einer Änderung (px)"), 0, 500, 20, 5, 0,
                                tr("Unterschiede, die zusammen weniger Pixel haben, werden ignoriert "
                                "(Staub, einzelne Punkte). 0 = nichts ignorieren."))
        sec.body.addWidget(self.s_area)
        b = QPushButton(tr("Automatisch einstellen"))
        b.setIcon(icon("magic"))
        self._icon_buttons.append((b, "magic"))
        b.setToolTip(self.act_auto.toolTip())
        b.clicked.connect(self.auto_params)
        self.btn_auto = b
        row = QHBoxLayout()
        row.addWidget(b)
        self.chk_align = QCheckBox(tr("Zeichnungen ausrichten"))
        self.chk_align.setChecked(True)
        self.chk_align.setToolTip(tr("An (Standard): Neu wird auf Alt ausgerichtet (Verschiebung, Drehung, Maßstab, "
                                  "Feinausrichtung in Kacheln). Aus: beide liegen genau so übereinander, wie sie in den "
                                  "Dateien sind (links oben bündig, ohne Skalieren) – z. B. wenn schon exakt "
                                  "ausgerichtete PDF aus dem CAD verglichen werden."))
        self.chk_align.toggled.connect(lambda _: self._param_changed())
        sec.body.addWidget(self.chk_align)
        b2 = QPushButton(tr("Manuell ausrichten"))
        b2.setToolTip(self.act_align.toolTip())
        b2.clicked.connect(self.start_manual_align)
        row.addWidget(b2)
        sec.body.addLayout(row)
        h = QLabel(tr("Viele dünne rote/blaue Doppellinien? Toleranz erhöhen. "
                   "Kleine Änderungen fehlen? Toleranz verringern."))
        h.setObjectName("hint")
        h.setWordWrap(True)
        sec.body.addWidget(h)
        lay.addWidget(sec)

        # Linienfilter: gilt fuer Anzeige und Vergleich, daher in beiden Modi sichtbar
        lf = Collapsible(tr("Linien filtern"), tr("Nur bestimmte Strichbreiten anzeigen und vergleichen"))
        self.cb_lines = QComboBox()
        for txt, key in ((tr("Alle Linien"), "all"), (tr("Nur Konturen (dicke Linien)"), "contours"),
                         (tr("Nur dünne Linien (Maße, Text, Schraffur)"), "thin"),
                         (tr("Strichbreite selbst wählen"), "custom")):
            self.cb_lines.addItem(txt, key)
        self.cb_lines.setToolTip(tr("Blendet Linien nach ihrer Strichbreite aus. „Nur Konturen“ zeigt und vergleicht "
                                 "nur die Körperkanten; die Grenze wird aus der Zeichnung bestimmt."))
        lf.body.addWidget(self.cb_lines)
        self.sp_wmin, self.sp_wmax = QSpinBox(), QSpinBox()
        for s_ in (self.sp_wmin, self.sp_wmax):
            s_.setRange(0, 40)
            s_.setSuffix(tr(" px"))
            s_.setSpecialValueText(tr("ohne"))
        self.sp_wmin.setToolTip(tr("Dünnere Linien ausblenden (0 = ohne Grenze)"))
        self.sp_wmax.setToolTip(tr("Dickere Linien ausblenden (0 = ohne Grenze)"))
        self.row_lines = QWidget()
        row = QHBoxLayout(self.row_lines)
        row.setContentsMargins(0, 0, 0, 0)
        for w in (QLabel(tr("Breite von")), self.sp_wmin, QLabel(tr("bis")), self.sp_wmax):
            row.addWidget(w)
        row.addStretch()
        self.row_lines.setVisible(False)
        lf.body.addWidget(self.row_lines)
        self.cb_lines.currentIndexChanged.connect(self._lines_changed)
        self.sp_wmin.valueChanged.connect(self._lines_changed)
        self.sp_wmax.valueChanged.connect(self._lines_changed)
        lay.addWidget(lf)
        self.sec_lines = lf

        self.sec_pages = Collapsible(tr("Seiten"), tr("Seite auswählen"))
        self.list_pages = QListWidget()
        self.list_pages.setIconSize(QSize(40, 56))
        self.list_pages.setFixedHeight(170)
        self.list_pages.currentRowChanged.connect(self._page_row)
        self.sec_pages.body.addWidget(self.list_pages)
        self.sp_pa, self.sp_pb = QSpinBox(), QSpinBox()
        for s_ in (self.sp_pa, self.sp_pb):
            s_.setRange(1, 1)
        row = QHBoxLayout()
        for w in (QLabel(tr("Seite A")), self.sp_pa, QLabel(tr("Seite B")), self.sp_pb):
            row.addWidget(w)
        self.sec_pages.body.addLayout(row)
        self.chk_couple = QCheckBox(tr("A und B gemeinsam blättern"))
        self.chk_couple.setChecked(True)
        self.sec_pages.body.addWidget(self.chk_couple)
        b = QPushButton(tr("Alle Seiten vergleichen"))
        b.setToolTip(tr("Vergleicht jede Seite und zeigt in der Liste, wie viele Änderungen sie hat"))
        b.clicked.connect(self.compare_all_pages)
        self.sec_pages.body.addWidget(b)
        self.sp_pa.valueChanged.connect(lambda v: self._page_changed("A", v))
        self.sp_pb.valueChanged.connect(lambda v: self._page_changed("B", v))
        self.sec_pages.hide()
        lay.addWidget(self.sec_pages)

        fo = Collapsible(tr("Maßstab und Auflösung"), tr("Auflösung (dpi) und Zeichnungsmaßstab für Messungen"))
        self.sp_dpi = QSpinBox()
        self.sp_dpi.setRange(50, 1200)
        self.sp_dpi.setValue(200)
        self.sp_dpi.setSuffix(tr(" dpi"))
        self.sp_dpi.setToolTip(tr("Auflösung der Zeichnung A. Bei Bilddateien meist automatisch aus der Datei gelesen, "
                               "bei PDF die Rendering-Auflösung."))
        self.lbl_dpi = QLabel("")
        self.lbl_dpi.setObjectName("hint")
        self.lbl_dpi.setWordWrap(True)
        self.sp_scale = QDoubleSpinBox()
        self.sp_scale.setDecimals(3)
        self.sp_scale.setRange(0.01, 1000)
        self.sp_scale.setValue(1.0)
        self.sp_scale.setPrefix("1 : ")
        self.sp_scale.setToolTip(tr("Zeichnungsmaßstab 1 : n. Messwerte werden mit n multipliziert. "
                                 "Bei Maßstab 2:1 (vergrößert) 0,5 eintragen."))
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Zeichnungsmaßstab")))
        row.addStretch()
        row.addWidget(self.sp_scale)
        fo.body.addLayout(row)
        row = QHBoxLayout()
        b1, b2, b3 = QPushButton(tr("Kalibrieren …")), QPushButton(tr("Aus Schriftfeld")), QPushButton("1 : 1")
        b1.setToolTip(tr("Zuerst eine bekannte Strecke messen (Werkzeug Messen), dann ihre wahre Länge eingeben"))
        b2.setToolTip(tr("Maßstab aus dem Schriftfeld lesen (PDF-Text oder OCR)"))
        b1.clicked.connect(self._calibrate)
        b2.clicked.connect(self.read_title_block)
        b3.clicked.connect(lambda: self.sp_scale.setValue(1.0))
        for b in (b1, b2, b3):
            row.addWidget(b)
        fo.body.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Auflösung")))
        row.addStretch()
        row.addWidget(self.sp_dpi)
        fo.body.addLayout(row)
        fo.body.addWidget(self.lbl_dpi)
        lay.addWidget(fo)
        self.sec_file = fo

        # --- ab hier nur mit "Alle Einstellungen zeigen"
        zon = Collapsible(tr("Ausschnitt und Zonen"), tr("Nur einen Teil vergleichen oder Bereiche ausnehmen"))
        h = QLabel(tr("Ausschnitt: nur diesen Teil der Zeichnung vergleichen (schneller). Der passende Bereich in B "
                   "wird automatisch gesucht; mit „Bereiche zuordnen“ wählt man ihn selbst."))
        h.setObjectName("hint")
        h.setWordWrap(True)
        zon.body.addWidget(h)
        row = QHBoxLayout()
        self.btn_crop = QPushButton(tr("Ausschnitt wählen"))
        self.btn_crop.setToolTip(tr("Dann im Bild einen Rahmen aufziehen"))
        self.btn_crop.clicked.connect(lambda: self._set_tool("crop"))
        self.btn_crop_off = QPushButton(tr("Ganzes Blatt"))
        self.btn_crop_off.clicked.connect(lambda: self._crop_reset())
        self.btn_crop_off.setEnabled(False)
        row.addWidget(self.btn_crop)
        row.addWidget(self.btn_crop_off)
        zon.body.addLayout(row)
        b = QPushButton(tr("Bereiche zuordnen (A ↔ B) …"))
        b.setToolTip(tr("Bereich in A und passenden Bereich in B selbst wählen, z. B. wenn eine Ansicht "
                     "auf dem Blatt verschoben oder anders skaliert wurde"))
        b.clicked.connect(self.match_regions)
        zon.body.addWidget(b)
        self.lbl_crop = QLabel(tr("Aktuell: ganzes Blatt"))
        self.lbl_crop.setObjectName("hint")
        zon.body.addWidget(self.lbl_crop)
        h = QLabel(tr("Zonen: Bereiche, die nicht verglichen werden (z. B. Schriftfeld, Stempel)."))
        h.setObjectName("hint")
        h.setWordWrap(True)
        zon.body.addWidget(h)
        self.btn_zone = QPushButton(tr("Zone zeichnen"))
        self.btn_zone.setToolTip(tr("Dann im Bild einen Rahmen aufziehen"))
        self.btn_zone.clicked.connect(lambda: self._set_tool("zone"))
        zon.body.addWidget(self.btn_zone)
        self.list_zones = QListWidget()
        self.list_zones.setFixedHeight(64)
        self.list_zones.currentRowChanged.connect(
            lambda r: (setattr(self.canvas, "zone_sel", r if r >= 0 else None), self.canvas.update()))
        for key in ("Delete", "Backspace"):
            QShortcut(QKeySequence(key), self.list_zones, activated=lambda: self._zone_delete(
                self.list_zones.currentRow())).setContext(Qt.ShortcutContext.WidgetShortcut)
        zon.body.addWidget(self.list_zones)
        row = QHBoxLayout()
        b1, b2 = QPushButton(tr("Entfernen")), QPushButton(tr("Alle löschen"))
        b1.clicked.connect(self._remove_zone)
        b2.clicked.connect(self._clear_zones)
        row.addWidget(b1)
        row.addWidget(b2)
        zon.body.addLayout(row)
        self.s_border = SliderRow(tr("Randstreifen (px)"), 0, 300, 0, 5, 0,
                                  tr("Zeichnungsrahmen am Blattrand nicht vergleichen."))
        zon.body.addWidget(self.s_border)
        lay.addWidget(zon)

        self.vfilter = (None, None)
        self.vinfo = {"A": None, "B": None}
        vec = Collapsible(tr("Vektordaten (PDF)"), tr("Exakter Vergleich, Ebenen und Farben"))
        self.lbl_vec = QLabel(tr("Bei PDF mit Vektordaten stehen hier weitere Funktionen bereit."))
        self.lbl_vec.setObjectName("hint")
        self.lbl_vec.setWordWrap(True)
        vec.body.addWidget(self.lbl_vec)
        self.chk_vec = QCheckBox(tr("Vektorvergleich (exakt statt Pixel)"))
        self.chk_vec.setToolTip(tr("Vergleicht die Linien, Kurven und Texte des PDF direkt. Kein Rastern, keine "
                                "Ausrichtung nötig; beide Zeichnungen müssen dasselbe Koordinatensystem haben."))
        self.chk_vec.setEnabled(False)
        self.chk_vec.toggled.connect(lambda _: self._param_changed())
        vec.body.addWidget(self.chk_vec)
        self.sp_vtol = QDoubleSpinBox()
        self.sp_vtol.setDecimals(2)
        self.sp_vtol.setRange(0.0, 5.0)
        self.sp_vtol.setSingleStep(0.05)
        self.sp_vtol.setValue(0.05)
        self.sp_vtol.setSuffix(tr(" mm"))
        self.sp_vtol.setToolTip(tr("Lagetoleranz: Elemente, die weniger abweichen, gelten als gleich."))
        self.sp_vtol.valueChanged.connect(lambda _: self._param_changed())
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Toleranz")))
        row.addWidget(self.sp_vtol)
        vec.body.addLayout(row)
        self.btn_vfilter = QPushButton(tr("Ebenen und Farben …"))
        self.btn_vfilter.setToolTip(tr("Nur bestimmte Ebenen oder Farben vergleichen (z. B. ohne Bemaßung)"))
        self.btn_vfilter.clicked.connect(self.open_vfilter)
        self.btn_vfilter.setEnabled(False)
        vec.body.addWidget(self.btn_vfilter)
        self.lbl_vfilter = QLabel(tr("Filter: alles"))
        self.lbl_vfilter.setObjectName("hint")
        vec.body.addWidget(self.lbl_vfilter)
        lay.addWidget(vec)
        self.sec_vec = vec

        self.s_thr = SliderRow(tr("Linienschwelle"), 0, 255, 128, 1, 0,
                               tr("Dunkler als dieser Wert = Linie. Höher erfasst auch blasse/gelbe Linien."))
        self.cb_align = QComboBox()
        self.cb_align.addItems(["affine", "euclidean", "translation", "none"])
        self.cb_align.setToolTip(tr("affine = Verschiebung+Drehung+Skalierung; euclidean = +Drehung; "
                                 "translation = nur Verschiebung; none = keine"))
        self.s_hatch = SliderRow(tr("Schraffur-Unterdrückung (px)"), 0, 40, 16, 1, 0,
                                 tr("Max. Linienabstand einer Schraffur; gleich dichte Schraffur ist keine Änderung. 0 = aus."))
        self.s_move = SliderRow(tr("Blöcke verschoben (px)"), 0, 300, 100, 5, 0,
                                tr("Suchbereich für komplett verschobene Blöcke (grün). 0 = aus."))
        self.s_obj = SliderRow(tr("Objekt-Verschiebung (px)"), 0, 150, 40, 1, 0,
                               tr("Einzelne Maße/Texte, die nur so weit verschoben sind, gelten nicht als Änderung. 0 = aus."))
        self.s_rot = SliderRow(tr("Objekt-Drehung (Grad)"), 0, 10, 3, 0.5, 1,
                               tr("Zusätzliche Drehung für die Objekt-Suche. 0 = keine Drehung."))
        self.s_cell = SliderRow(tr("Kachelgröße (px)"), 100, 1200, 400, 50, 0,
                                tr("Kleinere Kacheln = feinere lokale Ausrichtung."))
        self.s_maxs = SliderRow(tr("Max. Kachelverschiebung (px)"), 0, 100, 30, 1, 0,
                                tr("Größte lokale Verschiebung je Kachel."))
        adv = Collapsible(tr("Erweiterte Optionen"), tr("Für den normalen Vergleich nicht nötig"))
        adv.body.addWidget(self.s_thr)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Ausrichtung")))
        row.addWidget(self.cb_align, 1)
        adv.body.addLayout(row)
        for w in (self.s_hatch, self.s_move, self.s_obj):
            adv.body.addWidget(w)
        # Feinausrichtung (Kacheln) und Objekt-Drehung stellt "Automatisch einstellen" ein; im Alltag braucht sie
        # niemand - nur noch Kommandozeile und Projektdatei. Die Regler bleiben unsichtbar als Wertespeicher.
        for w in (self.s_rot, self.s_cell, self.s_maxs):
            w.setParent(adv)
            w.hide()
        self.chk_edges = QCheckBox(tr("Kantens\u00e4ume an Linien ignorieren"))
        self.chk_edges.setChecked(True)
        self.chk_edges.setToolTip(tr("1 Pixel d\u00fcnne S\u00e4ume direkt an Linien, die in beiden Zeichnungen vorkommen, "
                                  "gelten nicht als \u00c4nderung (Versatz oder Strichst\u00e4rke beim Scannen/Rendern)."))
        self.chk_edges.toggled.connect(lambda _: self._param_changed())
        adv.body.addWidget(self.chk_edges)
        self.chk_glyphs = QCheckBox(tr("Zeichen genau pr\u00fcfen (\u00e4hnliche Ziffern)"))
        self.chk_glyphs.setChecked(True)
        self.chk_glyphs.setToolTip(tr("Ziffern und Buchstaben Form gegen Form vergleichen, damit z. B. 41.8 \u2192 43.2 "
                                   "sicher als \u00c4nderung erkannt wird, obwohl sich die Ziffern stark \u00fcberdecken."))
        self.chk_glyphs.toggled.connect(lambda _: self._param_changed())
        adv.body.addWidget(self.chk_glyphs)
        self.chk_flatten = QCheckBox(tr("Ungleichm\u00e4\u00dfiges Papier ausgleichen"))
        self.chk_flatten.setToolTip(tr("F\u00fcr Scans mit Schatten, Flecken oder vergilbtem Papier: die Helligkeit des "
                                    "Papiers wird vor dem Vergleich ausgeglichen. \u201eAutomatisch einstellen\u201c "
                                    "schaltet das bei Bedarf selbst ein."))
        self.chk_flatten.toggled.connect(lambda _: self._param_changed())
        adv.body.addWidget(self.chk_flatten)
        b = QPushButton(tr("Standardwerte"))
        b.clicked.connect(self._reset_params)
        adv.body.addWidget(b)
        lay.addWidget(adv)
        self.expert_widgets = [zon, adv]
        self.compare_widgets = [self.sec_sens, zon]           # beim Ansehen einer einzelnen Zeichnung ohne Sinn
        lay.addStretch()

        for w in (self.s_thr, self.s_tol, self.s_hatch, self.s_move, self.s_obj, self.s_rot, self.s_area,
                  self.s_cell, self.s_maxs, self.s_border):
            w.changed.connect(self._param_changed)
        self.cb_align.currentIndexChanged.connect(self._param_changed)
        self.sp_dpi.valueChanged.connect(self._dpi_changed)
        self.sp_scale.valueChanged.connect(self._update_units)
        self.sp_scale.valueChanged.connect(self._remember_page_scale)

        scroll = PanelScroll(inner, 300)
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(12, 6, 12, 12)
        self.chk_live = QCheckBox(tr("Automatisch neu berechnen"))
        self.chk_live.setChecked(self.settings.value("live", "false") == "true")
        self.chk_live.setToolTip(tr("Aus (Standard): Geänderte Einstellungen gelten erst mit „Vergleichen“ (● am Knopf "
                                 "zeigt, dass neu verglichen werden sollte). An: jede Änderung vergleicht kurz danach "
                                 "neu. Beim Ansehen einer Zeichnung wirkt alles sofort."))
        self.chk_live.toggled.connect(lambda on: self.settings.setValue("live", "true" if on else "false"))
        self.btn_run = QPushButton(tr("Vergleichen"))
        self.btn_run.setObjectName("primary")
        self.btn_run.clicked.connect(self.start_compute)
        self.chk_expert = QCheckBox(tr("Alle Einstellungen"))
        self.chk_expert.setToolTip(self.act_expert.toolTip())
        self.chk_expert.toggled.connect(self.act_expert.setChecked)
        self.act_expert.toggled.connect(lambda on: (self.chk_expert.blockSignals(True), self.chk_expert.setChecked(on),
                                                    self.chk_expert.blockSignals(False)))
        row = QHBoxLayout()
        row.addWidget(self.chk_expert)
        row.addStretch()
        row.addWidget(self.chk_live)
        bl.addLayout(row)
        bl.addWidget(self.btn_run)
        outer = QVBoxLayout(self.left)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll, 1)
        outer.addWidget(bottom)

    # ----------------------------------------------------------------- Seitenleiste rechts
    def _build_right(self):
        self.right = QWidget()
        self.right.setObjectName("panel")
        self.right.setMinimumWidth(320)
        lay = QVBoxLayout(self.right)
        lay.setContentsMargins(0, 6, 12, 12)
        lay.setSpacing(6)
        tabs = QTabWidget()
        lay.addWidget(tabs, 1)
        self.tabs = tabs

        t1 = QWidget()
        t1.setObjectName("panel")
        l1 = QVBoxLayout(t1)
        l1.setContentsMargins(0, 6, 0, 0)
        self.btn_regs = QPushButton(tr("Prüfen starten"))       # bewusst kein Hauptknopf: Liste und Bild stehen im
        self.btn_regs.setToolTip(self.act_review_start.toolTip())
        self.btn_regs.clicked.connect(self.review_start)
        l1.addWidget(self.btn_regs)
        nav = QGridLayout()                       # Zeile 1: blaettern, Zeile 2: bewerten
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(4)
        self._review_buttons = []
        for (act, txt, row, col, span) in ((self.act_prev, tr("Vorige"), 0, 0, 1), (self.act_next, tr("Nächste"), 0, 1, 2),
                                           (self.act_ok, tr("Geprüft"), 1, 0, 1), (self.act_reject, tr("Abgelehnt"), 1, 1, 1),
                                           (self.act_comment, tr("Kommentar …"), 1, 2, 1)):
            b = QPushButton(txt)
            b.setIcon(act.icon())
            b.setToolTip(act.toolTip())
            b.clicked.connect(act.trigger)
            nav.addWidget(b, row, col, 1, span)
            self._review_buttons.append((b, act))
        for c in range(3):
            nav.setColumnStretch(c, 1)
        self.review_bar = QWidget()
        self.review_bar.setLayout(nav)
        l1.addWidget(self.review_bar)
        self.lbl_summary = QLabel("")
        self.lbl_summary.setObjectName("hint")
        self.lbl_summary.setWordWrap(True)
        l1.addWidget(self.lbl_summary)
        self.lbl_protocol = QLabel("")                # zuletzt abgeschlossene Pruefung dieser Seite
        self.lbl_protocol.setWordWrap(True)
        self.lbl_protocol.hide()
        l1.addWidget(self.lbl_protocol)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Zeigen:")))
        self.cb_filter = QComboBox()
        for txt, key in ((tr("Änderungen"), "changes"), (tr("Alle (auch verschoben)"), "all"), (tr("entfernt"), "entfernt"),
                         (tr("neu"), "neu"), (tr("geändert"), "geaendert"), (tr("verschoben"), "verschoben"),
                         (tr("nur geänderter Text"), "text"), (tr("nur geänderte Maße"), "dims"),
                         (tr("Konturen und Maße"), "geo"), (tr("offen"), "open")):
            self.cb_filter.addItem(txt, key)
        self.cb_filter.setToolTip(tr("„Änderungen“ = alles außer nur verschobenen Teilen. „nur geänderte Maße“ = "
                                  "Änderungen mit geänderter Maßzahl (nach „Geänderte Maße finden“), „Konturen und Maße“ = nur "
                                  "Änderungen an dicken Linien (Körperkanten) oder Maßen, „offen“ = noch "
                                  "nicht geprüft. Gilt für Liste, Bild und PDF."))
        self.cb_filter.currentIndexChanged.connect(self._fill_table)
        row.addWidget(self.cb_filter, 1)
        self.chk_regs = QCheckBox(tr("Im Bild zeigen"))
        self.chk_regs.setChecked(True)
        self.chk_regs.toggled.connect(self._toggle_regs)
        row.addWidget(self.chk_regs)
        l1.addLayout(row)
        self.ed_reg_search = self._search_field(tr("Suchen: Nr., Text, Maß, Kommentar"), self._fill_table)
        l1.addWidget(self.ed_reg_search)
        # Aenderungen nach Strichbreite ausklammern (die Zeichnung selbst bleibt vollstaendig, anders als "Linien filtern")
        sw = Collapsible(tr("Feine oder dicke Linien ausklammern"),
                         tr("Änderungen nach der Strichbreite der betroffenen Linie ausblenden"))
        self.s_regw_min = SliderRow(tr("Feiner als (px)"), 0, 12, 0, 1, 0,
                                    tr("Änderungen an Linien, die dünner sind, ausblenden – z. B. Maß- und Hinweislinien, "
                                       "Schraffur, Text. 0 = aus."))
        self.s_regw_max = SliderRow(tr("Dicker als (px)"), 0, 20, 0, 1, 0,
                                    tr("Änderungen an Linien, die dicker sind, ausblenden – z. B. nur Maße und Text "
                                       "sehen. 0 = aus."))
        for w in (self.s_regw_min, self.s_regw_max):
            w.changed.connect(self._fill_table)
            sw.body.addWidget(w)
        h = QLabel(tr("Die Zeichnung bleibt vollständig; nur Liste, Rahmen im Bild und Berichte werden gefiltert. "
                      "Kleine Änderungen nach Fläche: Optionen → Mindestgröße einer Änderung."))
        h.setObjectName("hint")
        h.setWordWrap(True)
        sw.body.addWidget(h)
        l1.addWidget(sw)
        self.sec_regw = sw
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr("Status"), tr("Nr"), tr("Typ"), tr("Pos. mm"), tr("Inhalt")])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        for i in range(4):
            hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._table_selected)
        self.table.cellDoubleClicked.connect(self._reg_row_edit)
        self.table.itemChanged.connect(self._table_checked)
        l1.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.btn_region = QPushButton(tr("Selbst markieren"))
        self.btn_region.setToolTip(tr("Eigenen Bereich als Änderung eintragen: Rahmen im Bild aufziehen."))
        self.btn_region.clicked.connect(lambda: self._set_tool("region"))
        self.btn_regdel = QPushButton(tr("Löschen"))
        self.btn_regdel.setToolTip(tr("Gewählte Zeile(n) aus der Liste entfernen"))
        self.btn_regdel.clicked.connect(self._reg_delete)
        self.btn_regclr = QPushButton(tr("Liste leeren"))
        self.btn_regclr.clicked.connect(self._reg_clear)
        for b in (self.btn_region, self.btn_regdel, self.btn_regclr):
            row.addWidget(b)
        l1.addLayout(row)
        for key in ("Delete", "Backspace"):            # Mac: die Taste "delete" ist Backspace
            QShortcut(QKeySequence(key), self.table, activated=self._reg_delete).setContext(
                Qt.ShortcutContext.WidgetShortcut)
        more = Collapsible(tr("Text und Maße"), tr("Geänderten Text, geänderte Maße, Schriftfeld-Index"))
        self.s_group = SliderRow(tr("Gruppierung (px)"), 0, 150, 25, 5, 0,
                                 tr("Wie nah beieinander liegende Unterschiede zu EINEM Eintrag zusammengefasst werden."))
        self.s_group.changed.connect(self._group_changed)
        more.body.addWidget(self.s_group)
        self.group_timer = QTimer(self)
        self.group_timer.setSingleShot(True)
        self.group_timer.timeout.connect(self._regroup)
        for a in (self.act_text, self.act_dims, self.act_index):
            b = QPushButton(a.text())
            b.setToolTip(a.toolTip())
            b.clicked.connect(a.trigger)
            more.body.addWidget(b)
        h = QLabel(tr("Beide lesen den Text jeder Änderung (auch senkrechte Maße) und schreiben „alt → neu“ in die "
                   "Liste. Danach bleiben in Liste und Bild nur Änderungen mit geändertem Text bzw. geänderter "
                   "Maßzahl – feine Strichänderungen an der Geometrie werden ausgeblendet."))
        h.setObjectName("hint")
        h.setWordWrap(True)
        more.body.addWidget(h)
        l1.addWidget(more)
        self.tab_regs = t1

        t2 = QWidget()
        t2.setObjectName("panel")
        l2 = QVBoxLayout(t2)
        l2.setContentsMargins(0, 6, 0, 0)
        h = QLabel(tr("Werkzeug links wählen (Text, Wolke, Pfeil …) und ins Bild klicken. Mit „Auswahl“ "
                   "anklicken, verschieben und an den Ecken die Größe ändern. Doppelklick = bearbeiten, "
                   "Rechtsklick = Menü, Entf = löschen. Mehrere: Strg/Umschalt + Klick oder Umschalt + Rahmen ziehen."))
        h.setObjectName("hint")
        h.setWordWrap(True)
        ann_hint = h                                  # Hinweis unter der Liste (wie bei den Ebenen)
        self.list_anns = QListWidget()
        self.list_anns.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)  # Strg/Umschalt = mehrere
        self.list_anns.itemSelectionChanged.connect(self._ann_list_selection)
        self.list_anns.itemChanged.connect(self._ann_item_checked)   # Haken = Markierung sichtbar
        self.list_anns.itemDoubleClicked.connect(lambda it: self._ann_edit(self.list_anns.row(it)))
        for key in ("Delete", "Backspace"):                # Entf in der Liste loescht die Auswahl
            QShortcut(QKeySequence(key), self.list_anns, activated=self._ann_delete).setContext(
                Qt.ShortcutContext.WidgetShortcut)
        self.ed_ann_search = self._search_field(tr("Suchen: Art, Text, Kommentar, Name"), self._ann_apply_search)
        l2.addWidget(self.ed_ann_search)
        l2.addWidget(self.list_anns, 1)
        row = QGridLayout()
        for i, (text, fn) in enumerate(((tr("Bearbeiten …"), lambda: self._ann_edit(self.canvas.ann_selected)),
                                        (tr("Duplizieren"), self._ann_duplicate), (tr("Löschen"), self._ann_delete),
                                        (tr("Alle löschen …"), self._ann_clear))):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, f=fn: f())
            row.addWidget(b, i // 2, i % 2)
        l2.addLayout(row)
        self.lbl_sums = QLabel("")                    # Summen und Zaehlungen (Auswahl oder alle)
        self.lbl_sums.setObjectName("hint")
        self.lbl_sums.setWordWrap(True)
        l2.addWidget(self.lbl_sums)
        l2.addWidget(self._build_thread_panel())
        l2.addWidget(ann_hint)
        # Reihenfolge: Markierungen (gibt es immer, bleibt vorn), Aenderungen (nur im Vergleich), Ebenen
        self.tab_anns, self.tab_layers = t2, self._build_layers_tab()
        tabs.addTab(t2, tr("Markierungen"))
        tabs.addTab(t1, tr("Änderungen"))
        tabs.addTab(self.tab_layers, tr("Ebenen"))
        on = self.settings.value("layers_tab", "true") == "true"      # Ebenen standardmaessig sichtbar
        tabs.setTabVisible(tabs.indexOf(self.tab_layers), on)
        self.act_layers.blockSignals(True)
        self.act_layers.setChecked(on)
        self.act_layers.blockSignals(False)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(110)
        self.log.setPlaceholderText(tr("Protokoll"))
        lay.addWidget(self.log)
        self.expert_widgets.append(self.log)
        self._fill_table()

    def _search_field(self, placeholder, fn):
        """Suchfeld ueber einer Liste: filtert beim Tippen, Esc/Kreuz leert es."""
        ed = QLineEdit()
        ed.setPlaceholderText(placeholder)
        ed.setClearButtonEnabled(True)
        ed.textChanged.connect(lambda _t: fn())
        QShortcut(QKeySequence("Escape"), ed, activated=ed.clear).setContext(Qt.ShortcutContext.WidgetShortcut)
        return ed

    def _build_layers_tab(self):
        t = QWidget()
        t.setObjectName("panel")
        l = QVBoxLayout(t)
        l.setContentsMargins(0, 6, 0, 0)
        box = QFrame()
        box.setObjectName("card")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(10, 6, 6, 6)
        bl.setSpacing(2)
        self.layer_checks, self.layer_locks = {}, {}
        for key, name in reversed(rep.LAYERS):          # oberste Ebene oben, Zeichnung (unterste) unten
            row = QHBoxLayout()
            chk = QCheckBox(name)
            chk.setChecked(True)
            chk.setToolTip(tr("Sichtbar: ein- oder ausblenden"))
            chk.toggled.connect(lambda on, k=key: self._layer_set(k, visible=on))
            lock = QToolButton()
            lock.setCheckable(True)
            lock.setIcon(icon("lock"))
            self._icon_buttons.append((lock, "lock"))
            lock.setToolTip(tr("Sperren: Inhalte lassen sich nicht auswählen, verschieben oder löschen"))
            lock.setAutoRaise(True)
            lock.toggled.connect(lambda on, k=key: self._layer_set(k, locked=on))
            row.addWidget(chk, 1)
            row.addWidget(lock)
            bl.addLayout(row)
            self.layer_checks[key], self.layer_locks[key] = chk, lock
        l.addWidget(box)
        self.pdf_layer_box = QFrame()                 # Ebenen aus der PDF-Datei selbst (Optional Content)
        self.pdf_layer_box.setObjectName("card")
        pl = QVBoxLayout(self.pdf_layer_box)
        pl.setContentsMargins(10, 6, 6, 6)
        pl.setSpacing(2)
        t1 = QLabel(tr("Ebenen der PDF-Datei"))
        t1.setObjectName("sec")
        pl.addWidget(t1)
        self.pdf_layer_rows = QVBoxLayout()
        pl.addLayout(self.pdf_layer_rows)
        self.pdf_layer_box.hide()
        l.addWidget(self.pdf_layer_box)
        h = QLabel(tr("Ausgeblendete Ebenen erscheinen weder im Bild noch beim Speichern, Drucken oder Kopieren – "
                   "außer Schwärzungen: Die werden immer eingebrannt. Gesperrte Ebenen lassen sich nicht auswählen "
                   "oder ändern. „PDF mit Anmerkungen“ und „Als SVG mit Ebenen“ speichern die sichtbaren Ebenen als "
                   "echte Ebenen."))
        h.setObjectName("hint")
        h.setWordWrap(True)
        l.addWidget(h)
        l.addStretch()
        return t

    def _refresh_pdf_layers(self):
        """Ebenen der geoeffneten PDF-Datei(en) als Haken anbieten; ausgeblendete werden nicht gezeichnet und nicht
        verglichen."""
        names = []
        for p in (self.path_a, self.path_b):
            if p and p.lower().endswith(".pdf"):
                names += [n for n in dc.pdf_layers(p) if n not in names]
        while self.pdf_layer_rows.count():
            w = self.pdf_layer_rows.takeAt(0).widget()
            if w:
                w.deleteLater()
        off = self.__dict__.setdefault("pdf_off", set())
        off &= set(names)
        for n in names:
            chk = QCheckBox(n)
            chk.setChecked(n not in off)
            chk.toggled.connect(lambda on, n=n: self._pdf_layer_toggled(n, on))
            self.pdf_layer_rows.addWidget(chk)
        self.pdf_layer_box.setVisible(bool(names))

    def _pdf_layer_toggled(self, name, on):
        (self.pdf_off.discard if on else self.pdf_off.add)(name)
        self.start_compute()                       # neu zeichnen (und vergleichen) ohne/mit dieser Ebene

    def _layer_set(self, key, visible=None, locked=None):
        c = self.canvas
        if visible is not None:
            c.layer_on[key] = visible
        if locked is not None:
            c.layer_lock[key] = locked
        keep = {k for k in c.selected_anns() if c.ann_editable(c.anns[k])}   # Auswahl nur auf waehlbaren Ebenen
        if keep != c.selected_anns():
            c._set_multi(keep)
        if key == "zonen" and c.zone_sel is not None and (not c.layer_on["zonen"] or c.layer_lock["zonen"]):
            c.zone_sel = None
        c.update()
