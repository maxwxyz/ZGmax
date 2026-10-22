"""Hauptfenster: Aufbau der Oberflaeche (Menue, Leisten, Werkzeugpalette, Seitenleisten, Startseite).

Grundsaetze: wenig auf einmal zeigen, alles beschriftet, Navigation (zoomen/verschieben) geht immer
ohne Werkzeugwechsel. Selten gebrauchte Einstellungen erscheinen erst mit "Alle Einstellungen zeigen".
"""
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_icons import icon
from ui_start import StartPage
from ui_widgets import Banner, Collapsible, Section, SliderRow

VIEWS = (("A", "Alt", "1", "Nur die alte Zeichnung A"),
         ("B", "Neu", "2", "Nur die neue Zeichnung B"),
         ("D", "Vergleich", "3", "Rot = nur alt, Blau = nur neu, Grün = nur verschoben"),
         ("O", "Überlagern", "4", "Beide Zeichnungen ohne Toleranz übereinander"),
         ("Y", "Nebeneinander", "9", "Alt und neu nebeneinander, gemeinsam zoomen und verschieben"),
         ("S", "Schieber", "5", "Links alt, rechts neu; Trennlinie ziehen"),
         ("K", "Blinken", "6", "Wechselt zwischen alt und neu (Leertaste = von Hand)"))
# Alt/Neu mit hervorgehobenen Aenderungen: im Umschalter "Alt"/"Neu" + Haekchen in der Optionszeile
MORE_VIEWS = (("N", "Neu mit Änderungen", "7", "Neue Zeichnung, neue und geänderte Stellen blau"),
              ("R", "Alt mit Änderungen", "8", "Alte Zeichnung, entfernte und geänderte Stellen rot"))
SEG_OF = {"N": "B", "R": "A"}
TOOLS = (("hand", "Auswahl", "select", "V", "Anklicken und verschieben. Leeres Papier ziehen = Ansicht verschieben."),
         ("zoom", "Zoom", "zoom_box", "Z", "Zoom-Rahmen mit Fadenkreuz: Bereich aufziehen. Einfacher Klick = ganze "
                                            "Zeichnung. Geht auch jederzeit mit der rechten Maustaste."),
         ("measure", "Messen", "measure", "M", "Länge, Winkel, Radius, Fläche messen; rastet an Linien ein"),
         ("text", "Text", "text", "T", "Ins Bild klicken und Text eingeben"),
         ("cloud", "Wolke", "cloud", "W", "Revisionswolke aufziehen"),
         ("rect", "Rahmen", "rect", "", "Rahmen aufziehen"),
         ("arrow", "Pfeil", "arrow", "", "Pfeil vom Anfang zur Spitze ziehen"),
         ("highlight", "Marker", "highlight", "", "Textmarker: Fläche farbig hinterlegen"),
         ("number", "Nummer", "number", "", "Fortlaufend nummerierte Kreise setzen"),
         ("approval", "Stempel", "stamp", "", "Stempel mit Status, Name und Datum"))


class LayoutMixin:
    """Teil des Hauptfensters (wird in MainWindow eingemischt)."""

    # ----------------------------------------------------------------- Aktionen und Menue
    def _act(self, text, fn=None, key=None, tip="", ico=None, checkable=False, canvas_key=False):
        a = QAction(text, self)
        if ico:
            a.setIcon(icon(ico))
            self._icon_actions.append((a, ico))
        if key:
            a.setShortcut(QKeySequence(key))
            if canvas_key:                       # Einzeltaste: nur wenn das Bild den Fokus hat
                a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
                self.canvas.addAction(a)
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        a.setCheckable(checkable)
        if fn is not None:
            (a.toggled if checkable else a.triggered).connect(lambda *_x, f=fn, c=checkable: f(*_x[:1]) if c else f())
        return a

    def _build_actions(self):
        self._icon_actions = []
        A = self._act
        self.act_start = A("Startseite", self.show_start)
        self.act_open_a = A("Alte Zeichnung (A) öffnen …", lambda: self.open_file("A"), "Ctrl+Shift+A", ico="open")
        self.act_open_b = A("Neue Zeichnung (B) öffnen …", lambda: self.open_file("B"), "Ctrl+Shift+B")
        self.act_open_view = A("Zeichnung ansehen …", self.open_view_only, "Ctrl+Shift+O")
        self.act_proj_open = A("Projekt öffnen …", self.project_open, "Ctrl+O")
        self.act_proj_save = A("Projekt speichern", self.project_save, "Ctrl+S")
        self.act_proj_save_as = A("Projekt speichern unter …", lambda: self.project_save(True), "Ctrl+Shift+S")
        self.act_export_img = A("Ergebnisbild speichern …", self.export_image, "Ctrl+E", ico="save")
        self.act_export_annpdf = A("PDF mit Anmerkungen (Acrobat) …", self.export_annotated_pdf)
        self.act_export_pdf = A("PDF-Bericht …", self.export_pdf)
        self.act_export_csv = A("Änderungsliste (CSV) …", self.export_csv)
        self.act_print = A("Drucken im Maßstab …", self.print_scaled, "Ctrl+P", ico="print")
        self.act_ann_save = A("Markierungen speichern …", self.ann_save)
        self.act_ann_load = A("Markierungen laden …", self.ann_load)
        self.act_batch = A("Stapelvergleich (viele Dateien) …", self.open_batch)
        self.act_revisions = A("Revisionen vergleichen (A → B → C) …", self.open_revisions)
        self.act_quit = A("Beenden", QApplication.instance().closeAllWindows, "Ctrl+Q")
        self.act_close = A("Schlie\u00dfen", self.close_document, "Ctrl+W",
                           "Vergleich bzw. Projekt schlie\u00dfen und zur Startseite (das Programm bleibt offen)")
        self.act_new_window = A("Neues Fenster", self.new_window, "Ctrl+N",
                                "Weiteres Fenster f\u00fcr einen anderen Vergleich")
        self.act_quit.setMenuRole(QAction.MenuRole.QuitRole)

        self.act_undo = A("Rückgängig", self.undo, "Ctrl+Z", "Rückgängig (Markierungen, Maße, Zonen)", "undo")
        self.act_redo = A("Wiederholen", self.redo, "Ctrl+Shift+Z", "Wiederholen", "redo")
        self.act_redo2 = QShortcut(QKeySequence("Ctrl+Y"), self, activated=self.redo)
        self.act_delete = A("Markierung löschen", self._ann_delete, "Delete", canvas_key=True)
        self.act_ann_clear = A("Alle Markierungen löschen …", self._ann_clear)
        self.act_copy = A("Ergebnis kopieren", self.copy_result, "Ctrl+C", canvas_key=True)

        self.mode_actions = {}
        grp = QActionGroup(self)
        for key, label, k, tip in VIEWS + MORE_VIEWS:
            a = A(label, lambda m=key: self._set_mode(m), k, f"{tip} (Taste {k})", checkable=False, canvas_key=True)
            a.setCheckable(True)
            grp.addAction(a)
            self.mode_actions[key] = a
        self.mode_actions["D"].setChecked(True)
        self.act_fit = A("Ganze Zeichnung", lambda: self.canvas.fit(), "F", "Ganze Zeichnung zeigen (F oder Doppelklick)",
                         "fit", canvas_key=True)
        self.act_100 = A("Originalgröße (100 %)", self._zoom100, "Ctrl+0")
        self.act_zoom_in = A("Vergrößern", lambda: self.canvas.zoom_step(1.25), "Ctrl++", "Vergrößern (Mausrad, +)", "zoom_in")
        self.act_zoom_out = A("Verkleinern", lambda: self.canvas.zoom_step(1 / 1.25), "Ctrl+-", "Verkleinern (Mausrad, −)", "zoom_out")
        self.act_zoom_box = A("Zoom-Rahmen", lambda: self._set_tool("zoom"),
                              tip="Bereich aufziehen und hineinzoomen (geht auch jederzeit mit der rechten Maustaste)",
                              ico="zoom_box")
        self.act_rotate = A("Ansicht drehen (90°)", lambda: self.canvas.rotate_view(), "R",
                            "Nur die Anzeige drehen (Taste R)", "rotate", canvas_key=True)
        self.act_overview = A("Übersicht", self._toggle_overview, tip="Kleine Übersicht unten rechts, "
                              "wenn hineingezoomt ist. Klicken oder ziehen springt dorthin.", ico="overview", checkable=True)
        self.act_overview.setChecked(self.settings.value("overview", "true") == "true")
        self.act_loupe = A("Lupe", self._toggle_loupe, "L", "Vergrößert den Bereich unter dem Mauszeiger (L)",
                           "loupe", checkable=True, canvas_key=True)
        self.act_overlays = A("Markierungen anzeigen", self._toggle_overlays, "H",
                              "Nummern, Zonen, Markierungen und Maße ein-/ausblenden (H). "
                              "Ausgeblendetes wird auch nicht gespeichert.", checkable=True, canvas_key=True)
        self.act_overlays.setChecked(True)
        self.act_invert = A("Farben umkehren", self._toggle_invert, "I", "Helle Linien auf dunklem Grund (nur "
                            "Anzeige; gespeicherte Bilder bleiben normal). Taste I", checkable=True, canvas_key=True)
        self.act_invert.setChecked(self.settings.value("invert", "false") == "true")
        self.act_color = A("Original anzeigen (Farbe, Graustufen)", self._toggle_color,
                           tip="Alt, Neu, Nebeneinander, Schieber und Blinken zeigen die Datei, wie sie ist (Farbe oder "
                           "Graustufen). Aus = Schwarz-Wei\u00df-Fassung, mit der verglichen wird.", checkable=True)
        self.act_color.setChecked(self.settings.value("color", "true") == "true")
        self.act_clouds = A("\u00c4nderungen als Revisionswolken", self._toggle_clouds,
                            tip="Nummerierte \u00c4nderungen als Wolke statt als Rahmen zeigen und speichern",
                            ico="cloud", checkable=True)
        self.act_clouds.setChecked(self.settings.value("clouds", "false") == "true")
        self.act_left = A("Einstellungen", lambda on: self.left.setVisible(on), tip="Einstellungen ein-/ausblenden",
                          ico="settings", checkable=True)
        self.act_right = A("Änderungen und Markierungen", lambda on: self.right.setVisible(on),
                           tip="Liste der Änderungen und Markierungen ein-/ausblenden", ico="list", checkable=True)
        self.act_expert = A("Alle Einstellungen zeigen", self._set_expert, tip="Auch selten gebrauchte Einstellungen, "
                            "Vektordaten, Zonen und das Protokoll zeigen", checkable=True)
        self.act_space = QShortcut(QKeySequence("Space"), self.canvas, activated=self._space)
        self.act_space.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

        self.tool_actions = {}
        tgrp = QActionGroup(self)
        for key, label, ico, k, tip in TOOLS:
            a = A(label, lambda t=key: self._set_tool(t), k or None, tip + (f" ({k})" if k else ""), ico,
                  canvas_key=bool(k))
            a.setCheckable(True)
            tgrp.addAction(a)
            self.tool_actions[key] = a
        self.tool_actions["hand"].setChecked(True)
        self.act_zone = A("Zone zeichnen (nicht vergleichen)", lambda: self._set_tool("zone"))
        self.act_crop = A("Ausschnitt wählen", lambda: self._set_tool("crop"))
        self.act_crop_off = A("Ganzes Blatt vergleichen", lambda: self._crop_reset())
        self.act_match = A("Bereiche zuordnen (A ↔ B) …", self.match_regions)
        self.act_auto = A("Automatisch einstellen", self.auto_params, tip="Toleranz, Schwelle und Suchbereiche aus "
                          "diesem Zeichnungspaar bestimmen", ico="magic")
        self.act_compare = A("Vergleichen", self.start_compute, "Ctrl+Return", "Vergleich (neu) berechnen", "compare")

        self.act_find = A("Änderungen suchen", self.find_regs, "Ctrl+F")
        self.act_next = A("Nächste Änderung", lambda: self.review_step(1), "N", "Zur nächsten offenen "
                          "Änderung (N)", "next", canvas_key=True)
        self.act_prev = A("Vorige Änderung", lambda: self.review_step(-1), "P", "Zur vorigen Änderung (P)",
                          "prev", canvas_key=True)
        self.act_ok = A("Als geprüft markieren", lambda: self.review_set("ok"), "G",
                        "Gewählte Änderung ist geprüft (G), weiter zur nächsten", "check", canvas_key=True)
        self.act_reject = A("Als abgelehnt markieren", lambda: self.review_set("abgelehnt"), "X",
                            "Gewählte Änderung ist nicht in Ordnung (X)", "reject", canvas_key=True)
        self.act_comment = A("Kommentar …", self.review_comment, "C", "Kommentar zur gewählten Änderung (C)",
                             canvas_key=True)
        self.act_pages = A("Alle Seiten vergleichen", self.compare_all_pages)
        self.act_rej_zones = A("Abgelehnte als Zonen übernehmen", self.zones_from_rejected,
                               tip="Als abgelehnt markierte Änderungen künftig nicht mehr vergleichen")
        self.act_title = A("Schriftfeld lesen", self.read_title_block)
        self.act_ocr = A("Text lesen (OCR)", self.run_ocr)
        self.act_pdftext = A("Text aus PDF lesen", self.run_pdftext)
        self.act_dims = A("Maßzahlen vergleichen", self.run_dims)
        self.act_index = A("Index prüfen", self.run_index)

        self.act_help = A("Anleitung", self.open_help, "F1", ico="help")
        self.act_help_cli = A("Anleitung Kommandozeile",
                              lambda: self._open_doc(os.path.join(HERE, "Anleitung_Kommandozeile.html")))
        self.act_keys = A("Tastenkürzel", self.show_keys)
        self.act_logfile = A("Logdatei öffnen", self.open_logfile)
        self.act_cli = A("Befehl für Kommandozeile kopieren", self.copy_cli)
        self.act_shortcut = A("Desktop-Verknüpfung erstellen", self.make_shortcut)
        self.act_about = A("Über ZGmax", self.show_about)
        self.act_about.setMenuRole(QAction.MenuRole.AboutRole)

    def _build_menubar(self):
        mb = self.menuBar()
        m = mb.addMenu("&Datei")
        m.addAction(self.act_new_window)
        m.addAction(self.act_start)
        m.addSeparator()
        for a in (self.act_open_a, self.act_open_b, self.act_open_view, self.act_proj_open):
            m.addAction(a)
        self.menu_recent = m.addMenu("Zuletzt verwendet")
        self.menu_recent.aboutToShow.connect(self._fill_recent_menu)
        m.addSeparator()
        for a in (self.act_proj_save, self.act_proj_save_as, self.act_close):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_export_img, self.act_export_annpdf, self.act_export_pdf, self.act_export_csv, self.act_print):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_ann_save, self.act_ann_load):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_batch)
        m.addAction(self.act_revisions)
        if os.name == "nt":
            m.addAction(self.act_shortcut)
        m.addSeparator()
        m.addAction(self.act_quit)

        m = mb.addMenu("&Bearbeiten")
        for a in (self.act_undo, self.act_redo):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_delete, self.act_ann_clear, self.act_copy):
            m.addAction(a)

        m = mb.addMenu("&Ansicht")
        for key, *_ in VIEWS + MORE_VIEWS:
            m.addAction(self.mode_actions[key])
        m.addSeparator()
        for a in (self.act_fit, self.act_100, self.act_zoom_in, self.act_zoom_out, self.act_zoom_box, self.act_rotate):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_overview, self.act_loupe, self.act_overlays, self.act_clouds):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_color)
        m.addAction(self.act_invert)
        m.addSeparator()
        for a in (self.act_left, self.act_right):
            m.addAction(a)
        m.addSeparator()
        look = m.addMenu("Darstellung")
        self.theme_actions = {}
        tg = QActionGroup(self)
        for key, txt in (("auto", "Automatisch (wie System)"), ("light", "Hell"), ("dark", "Dunkel")):
            act = look.addAction(txt, lambda k=key: self.set_theme(k))
            act.setCheckable(True)
            tg.addAction(act)
            self.theme_actions[key] = act
        self.theme_actions[self.theme_mode].setChecked(True)
        m.addAction(self.act_expert)

        m = mb.addMenu("&Werkzeuge")
        for key, *_ in TOOLS:
            m.addAction(self.tool_actions[key])
        m.addSeparator()
        m.addAction(self.act_auto)
        for a in (self.act_crop, self.act_crop_off, self.act_match, self.act_zone):
            m.addAction(a)

        m = mb.addMenu("&Prüfen")
        for a in (self.act_compare, self.act_find):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_next, self.act_prev, self.act_ok, self.act_reject, self.act_comment, self.act_rej_zones):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_pages, self.act_title, self.act_pdftext, self.act_dims, self.act_ocr, self.act_index):
            m.addAction(a)

        m = mb.addMenu("&Hilfe")
        for a in (self.act_help, self.act_help_cli, self.act_keys):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_logfile, self.act_cli, self.act_about):
            m.addAction(a)

    # ----------------------------------------------------------------- Werkzeugleiste oben
    def _tb_button(self, tb, act, text_beside=True):
        tb.addAction(act)
        w = tb.widgetForAction(act)
        if w is not None and text_beside:
            w.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        return w

    def _build_toolbar(self):
        tb = QToolBar("Hauptleiste")
        tb.setObjectName("main")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(tb)
        self.tb = tb
        open_menu = QMenu(self)
        for a in (self.act_open_a, self.act_open_b, self.act_open_view, self.act_proj_open):
            open_menu.addAction(a)
        self.menu_recent2 = open_menu.addMenu("Zuletzt verwendet")
        self.menu_recent2.aboutToShow.connect(lambda: self._fill_recent_menu(self.menu_recent2))
        open_menu.addSeparator()
        open_menu.addAction(self.act_start)
        b = QToolButton()
        b.setText("Öffnen")
        b.setIcon(icon("open"))
        self._icon_buttons = [(b, "open")]
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        b.setMenu(open_menu)
        b.setToolTip("Zeichnungen oder Projekt öffnen")
        tb.addWidget(b)
        self.btn_compare_tb = self._tb_button(tb, self.act_compare)
        self.act_compare_tb = tb.actions()[-1]
        self.sep_views = tb.addSeparator()
        # Ansichten als ruhiger Umschalter (eine Gruppe, gewaehlte Ansicht hell hervorgehoben)
        self.view_box = QFrame()
        self.view_box.setObjectName("segbox")
        vl = QHBoxLayout(self.view_box)
        vl.setContentsMargins(3, 3, 3, 3)
        vl.setSpacing(2)
        self.seg_buttons = {}
        grp = QButtonGroup(self)
        grp.setExclusive(True)
        for key, label, k, tip in VIEWS:
            btn = QToolButton()
            btn.setText(label)
            btn.setToolTip(f"{tip} (Taste {k})")
            btn.setCheckable(True)
            btn.setObjectName("seg")
            btn.clicked.connect(lambda _=False, m=key: self._seg_clicked(m))
            grp.addButton(btn)
            vl.addWidget(btn)
            self.seg_buttons[key] = btn
        self.seg_buttons["D"].setChecked(True)
        self.act_view_box = tb.addWidget(self.view_box)
        self.act_pause = QAction("Pause", self, checkable=True)
        self.act_pause.setToolTip("Blinken anhalten/fortsetzen (auch Klick ins Bild; Leertaste wechselt von Hand)")
        self.act_pause.toggled.connect(self._pause_blink)
        tb.addSeparator()
        tb.addAction(self.act_zoom_out)
        self.lbl_zoom = QToolButton()
        self.lbl_zoom.setObjectName("zoomlabel")
        self.lbl_zoom.setText("–")
        self.lbl_zoom.setToolTip("Zoomstufe. Klick = Originalgröße (100 %)")
        self.lbl_zoom.clicked.connect(self._zoom100)
        tb.addWidget(self.lbl_zoom)
        tb.addAction(self.act_zoom_in)
        self._tb_button(tb, self.act_fit)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        save = QMenu(self)
        for a in (self.act_export_img, self.act_export_annpdf, self.act_export_pdf, self.act_export_csv, self.act_print):
            save.addAction(a)
        save.addSeparator()
        for a in (self.act_proj_save, self.act_proj_save_as):
            save.addAction(a)
        b = QToolButton()
        b.setText("Speichern")
        b.setIcon(icon("save"))
        self._icon_buttons.append((b, "save"))
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        b.setMenu(save)
        b.setToolTip("Ergebnis, Bericht oder Projekt speichern; drucken")
        tb.addWidget(b)
        tb.addSeparator()
        self._tb_button(tb, self.act_left)
        self._tb_button(tb, self.act_right)
        ext = tb.findChild(QToolButton, "qt_toolbar_ext_button")
        if ext is not None:
            ext.setIcon(QIcon())
            ext.setText("»")
            ext.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            ext.setMinimumSize(40, 30)
            ext.setToolTip("Das Fenster ist zu schmal: weitere Schaltflächen hier öffnen")

    # ----------------------------------------------------------------- Werkzeugpalette links am Bild
    def _build_palette(self):
        pal = QFrame()
        pal.setObjectName("palette")
        pal.setFixedWidth(76)
        lay = QVBoxLayout(pal)
        lay.setContentsMargins(5, 8, 5, 8)
        lay.setSpacing(2)
        for key, *_ in TOOLS:
            b = QToolButton()
            b.setDefaultAction(self.tool_actions[key])
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(22, 22))
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            lay.addWidget(b)
            if key == "measure":
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setStyleSheet(f"color: {THEME['border']};")
                lay.addWidget(line)
        lay.addStretch(1)
        for act in (self.act_loupe, self.act_overview):
            b = QToolButton()
            b.setDefaultAction(act)
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(22, 22))
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            lay.addWidget(b)
        self.palette_frame = pal
        return pal

    # ----------------------------------------------------------------- Optionsleiste (je Werkzeug)
    def _build_options(self):
        bar = QFrame()
        bar.setObjectName("panel")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(10)
        self.opt_measure = QWidget()
        l = QHBoxLayout(self.opt_measure)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(QLabel("Messart"))
        self.cb_mkind = QComboBox()
        for key, txt in rep.MEASURE_KINDS.items():
            self.cb_mkind.addItem(txt, key)
        self.cb_mkind.setToolTip("Länge = 2 Punkte, Winkel und Radius = 3 Punkte, Linienzug und Fläche = "
                                 "beliebig viele (Ende mit Doppelklick, Enter oder Rechtsklick)")
        self.cb_mkind.currentIndexChanged.connect(self._mkind_changed)
        l.addWidget(self.cb_mkind)
        self.chk_snap = QCheckBox("An Linien einrasten")
        self.chk_snap.setChecked(True)
        self.chk_snap.setToolTip("Umschalt gedrückt halten = vorübergehend frei messen")
        self.chk_snap.toggled.connect(self._toggle_snap)
        l.addWidget(self.chk_snap)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        l.addWidget(sep)
        self.lbl_meas_scale = QToolButton()
        self.lbl_meas_scale.setText("Ma\u00dfstab 1 : 1")
        self.lbl_meas_scale.clicked.connect(self._scale_dialog)
        l.addWidget(self.lbl_meas_scale)
        b = QPushButton("Kalibrieren \u2026")
        b.setToolTip("Eine Strecke mit bekannter L\u00e4nge messen und ihre wahre L\u00e4nge eingeben; "
                     "danach stimmen alle Ma\u00dfe (auch bei falscher Aufl\u00f6sung oder Ma\u00dfstab).")
        b.clicked.connect(lambda: self._calibrate())
        l.addWidget(b)
        b = QPushButton("Aus Schriftfeld")
        b.setToolTip("Ma\u00dfstab aus dem Schriftfeld lesen (PDF-Text oder Texterkennung)")
        b.clicked.connect(self.read_title_block)
        l.addWidget(b)
        lay.addWidget(self.opt_measure)
        self.opt_ann = QWidget()
        l = QHBoxLayout(self.opt_ann)
        l.setContentsMargins(0, 0, 0, 0)
        self.btn_color = QPushButton("Farbe")
        self.btn_color.clicked.connect(self._pick_color)
        l.addWidget(self.btn_color)
        l.addWidget(QLabel("Größe"))
        self.s_asize = QDoubleSpinBox()
        self.s_asize.setRange(0.5, 12)
        self.s_asize.setSingleStep(0.5)
        self.s_asize.setDecimals(1)
        self.s_asize.setValue(2.0)
        self.s_asize.setToolTip("Größe von Text, Nummer, Stempel und Linienstärke")
        self.s_asize.valueChanged.connect(self._ann_size)
        self.s_asize.set_silent = lambda v: (self.s_asize.blockSignals(True), self.s_asize.setValue(v),
                                             self.s_asize.blockSignals(False))
        l.addWidget(self.s_asize)
        self.lbl_stamp = QLabel("Nächste Nummer")
        self.sp_stamp = QSpinBox()
        self.sp_stamp.setRange(1, 9999)
        self.sp_stamp.valueChanged.connect(lambda v: setattr(self, "next_nr", v))
        l.addWidget(self.lbl_stamp)
        l.addWidget(self.sp_stamp)
        lay.addWidget(self.opt_ann)
        self.opt_view = QWidget()                     # Optionen der Ansicht (Blinken, Hervorheben, Schieber)
        l = QHBoxLayout(self.opt_view)
        l.setContentsMargins(0, 0, 0, 0)
        self.lbl_blink = QLabel("Blinken")
        self.cb_blink = QComboBox()
        for txt, ms in (("langsam", 1200), ("normal", 550), ("schnell", 250)):
            self.cb_blink.addItem(txt, ms)
        self.cb_blink.setCurrentIndex(1)
        self.cb_blink.setToolTip("Blinkgeschwindigkeit")
        self.cb_blink.currentIndexChanged.connect(lambda _: self.blink.setInterval(self.cb_blink.currentData()))
        self.btn_pause = QToolButton()
        self.btn_pause.setDefaultAction(self.act_pause)
        self.lbl_blink_hint = QLabel("Leertaste = von Hand wechseln, Klick ins Bild = Pause")
        self.lbl_blink_hint.setObjectName("hint")
        self.chk_highlight = QCheckBox("Änderungen hervorheben")
        self.chk_highlight.setToolTip("In der alten Zeichnung entfernte Stellen rot, in der neuen neue Stellen blau "
                                      "(Tasten 8 / 7)")
        self.chk_highlight.toggled.connect(self._highlight_toggled)
        self.lbl_slider_hint = QLabel("Schieber: die blaue Trennlinie mit der Maus ziehen (links alt, rechts neu)")
        self.lbl_slider_hint.setObjectName("hint")
        for w in (self.lbl_blink, self.cb_blink, self.btn_pause, self.lbl_blink_hint, self.chk_highlight,
                  self.lbl_slider_hint):
            l.addWidget(w)
        lay.addWidget(self.opt_view)
        self.opt_loupe = QWidget()
        l = QHBoxLayout(self.opt_loupe)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(QLabel("Lupe"))
        self.cb_loupe = QComboBox()
        for z in (2, 3, 5, 8):
            self.cb_loupe.addItem(f"{z}×", float(z))
        self.cb_loupe.setCurrentIndex(1)
        self.cb_loupe.currentIndexChanged.connect(
            lambda _: setattr(self.canvas, "loupe_zoom", self.cb_loupe.currentData()))
        l.addWidget(self.cb_loupe)
        lay.addWidget(self.opt_loupe)
        for w in (self.opt_measure, self.opt_ann, self.opt_loupe, self.opt_view):  # nie zusammendruecken
            w.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.lbl_tool_hint = QLabel("")
        self.lbl_tool_hint.setObjectName("hint")
        self.lbl_tool_hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(self.lbl_tool_hint, 1)
        self.options_bar = bar
        self._set_color_btn("#e11d48")
        return bar

    def _seg_clicked(self, key):
        if key in ("A", "B") and self.chk_highlight.isChecked() and not self.view_only:
            key = {"A": "R", "B": "N"}[key]
        self._set_mode(key)

    def _highlight_toggled(self, on):
        m = self.canvas.mode
        if on and m in ("A", "B"):
            self._set_mode({"A": "R", "B": "N"}[m])
        elif not on and m in ("N", "R"):
            self._set_mode({"N": "B", "R": "A"}[m])

    def _update_options(self):
        t = self.canvas.tool
        m = self.canvas.mode
        blink, single = m == "K", m in ("A", "B", "N", "R") and not self.view_only
        for w in (self.lbl_blink, self.cb_blink, self.btn_pause, self.lbl_blink_hint):
            w.setVisible(blink)
        self.chk_highlight.setVisible(single)
        self.lbl_slider_hint.setVisible(m == "S")
        view_opts = blink or single or m == "S"
        self.opt_view.setVisible(view_opts)
        self.opt_measure.setVisible(t == "measure")
        self.opt_ann.setVisible(t in ("text", "number", "approval", "rect", "arrow", "cloud", "highlight")
                                or (t == "hand" and self.canvas.ann_selected is not None))
        self.lbl_stamp.setVisible(t == "number")
        self.sp_stamp.setVisible(t == "number")
        self.opt_loupe.setVisible(self.act_loupe.isChecked())
        self.lbl_tool_hint.setText(TOOL_HINTS.get(t, "") if t != "hand" else "")
        self.options_bar.setVisible(t != "hand" or self.act_loupe.isChecked() or self.canvas.ann_selected is not None
                                    or (view_opts and self.payload is not None))

    # ----------------------------------------------------------------- Mitte: Startseite / Bild
    def _build_center(self):
        self.stack = QStackedWidget()
        self.start = StartPage()
        self.start.fileChosen.connect(lambda w, p: self._set_file(w, p))
        self.start.browse.connect(self.open_file)
        self.start.recentChosen.connect(self.open_recent)
        self.start.projectRequested.connect(self.project_open)
        self.start.viewOnly.connect(lambda: self.start_compute())
        self.stack.addWidget(self.start)
        work = QWidget()
        v = QVBoxLayout(work)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.banner = Banner()
        v.addWidget(self.banner)
        v.addWidget(self._build_options())
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_palette())
        h.addWidget(self.canvas, 1)
        v.addLayout(h, 1)
        self.stack.addWidget(work)
        self.work = work
        return self.stack

    # ----------------------------------------------------------------- Seitenleiste links: Einstellungen
    def _build_left(self):
        self.left = QWidget()
        self.left.setObjectName("panel")
        self.left.setMinimumWidth(300)
        self.left.setMaximumWidth(440)
        inner = QWidget()
        inner.setObjectName("panel")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(12, 8, 12, 12)
        lay.setSpacing(8)

        sec = Section("Zeichnungen")
        self.lbl_a, self.lbl_b = QLabel("(nicht gewählt)"), QLabel("(nicht gewählt)")
        for tag, lbl, which in (("A  –  alt", self.lbl_a, "A"), ("B  –  neu", self.lbl_b, "B")):
            row = QHBoxLayout()
            t = QLabel(tag)
            t.setObjectName("sec")
            row.addWidget(t)
            row.addStretch()
            btn = QPushButton("Öffnen …")
            btn.clicked.connect(lambda _=False, w=which: self.open_file(w))
            row.addWidget(btn)
            sec.body.addLayout(row)
            lbl.setObjectName("file")
            lbl.setWordWrap(True)
            sec.body.addWidget(lbl)
        b = QPushButton("A und B tauschen")
        b.clicked.connect(self.swap_ab)
        sec.body.addWidget(b)
        lay.addWidget(sec)

        sec = Section("Empfindlichkeit")
        self.s_tol = SliderRow("Toleranz (px)", 0, 10, 2, 1, 0,
                               "Linien mit weniger Abstand gelten als gleich. Höher = weniger Rauschen.")
        sec.body.addWidget(self.s_tol)
        self.s_area = SliderRow("Mindestgröße einer Änderung (px)", 0, 500, 20, 5, 0,
                                "Unterschiede, die zusammen weniger Pixel haben, werden ignoriert "
                                "(Staub, einzelne Punkte). 0 = nichts ignorieren.")
        sec.body.addWidget(self.s_area)
        b = QPushButton("Automatisch einstellen")
        b.setIcon(icon("magic"))
        self._icon_buttons.append((b, "magic"))
        b.setToolTip(self.act_auto.toolTip())
        b.clicked.connect(self.auto_params)
        self.btn_auto = b
        sec.body.addWidget(b)
        h = QLabel("Viele dünne rote/blaue Doppellinien? Toleranz erhöhen. "
                   "Kleine Änderungen fehlen? Toleranz verringern.")
        h.setObjectName("hint")
        h.setWordWrap(True)
        sec.body.addWidget(h)
        lay.addWidget(sec)

        self.sec_pages = Collapsible("Seiten", "Seite auswählen")
        self.list_pages = QListWidget()
        self.list_pages.setIconSize(QSize(40, 56))
        self.list_pages.setFixedHeight(170)
        self.list_pages.currentRowChanged.connect(self._page_row)
        self.sec_pages.body.addWidget(self.list_pages)
        self.sp_pa, self.sp_pb = QSpinBox(), QSpinBox()
        for s_ in (self.sp_pa, self.sp_pb):
            s_.setRange(1, 1)
        row = QHBoxLayout()
        for w in (QLabel("Seite A"), self.sp_pa, QLabel("Seite B"), self.sp_pb):
            row.addWidget(w)
        self.sec_pages.body.addLayout(row)
        self.chk_couple = QCheckBox("A und B gemeinsam blättern")
        self.chk_couple.setChecked(True)
        self.sec_pages.body.addWidget(self.chk_couple)
        b = QPushButton("Alle Seiten vergleichen")
        b.setToolTip("Vergleicht jede Seite und zeigt in der Liste, wie viele Änderungen sie hat")
        b.clicked.connect(self.compare_all_pages)
        self.sec_pages.body.addWidget(b)
        self.sp_pa.valueChanged.connect(lambda v: self._page_changed("A", v))
        self.sp_pb.valueChanged.connect(lambda v: self._page_changed("B", v))
        self.sec_pages.hide()
        lay.addWidget(self.sec_pages)

        fo = Collapsible("Maßstab und Auflösung", "Auflösung (dpi) und Zeichnungsmaßstab für Messungen")
        self.sp_dpi = QSpinBox()
        self.sp_dpi.setRange(50, 1200)
        self.sp_dpi.setValue(200)
        self.sp_dpi.setSuffix(" dpi")
        self.sp_dpi.setToolTip("Auflösung der Zeichnung A. Bei Bilddateien meist automatisch aus der Datei gelesen, "
                               "bei PDF die Rendering-Auflösung.")
        self.lbl_dpi = QLabel("")
        self.lbl_dpi.setObjectName("hint")
        self.lbl_dpi.setWordWrap(True)
        self.sp_scale = QDoubleSpinBox()
        self.sp_scale.setDecimals(3)
        self.sp_scale.setRange(0.01, 1000)
        self.sp_scale.setValue(1.0)
        self.sp_scale.setPrefix("1 : ")
        self.sp_scale.setToolTip("Zeichnungsmaßstab 1 : n. Messwerte werden mit n multipliziert. "
                                 "Bei Maßstab 2:1 (vergrößert) 0,5 eintragen.")
        row = QHBoxLayout()
        row.addWidget(QLabel("Zeichnungsmaßstab"))
        row.addStretch()
        row.addWidget(self.sp_scale)
        fo.body.addLayout(row)
        row = QHBoxLayout()
        b1, b2, b3 = QPushButton("Kalibrieren …"), QPushButton("Aus Schriftfeld"), QPushButton("1 : 1")
        b1.setToolTip("Zuerst eine bekannte Strecke messen (Werkzeug Messen), dann ihre wahre Länge eingeben")
        b2.setToolTip("Maßstab aus dem Schriftfeld lesen (PDF-Text oder OCR)")
        b1.clicked.connect(self._calibrate)
        b2.clicked.connect(self.read_title_block)
        b3.clicked.connect(lambda: self.sp_scale.setValue(1.0))
        for b in (b1, b2, b3):
            row.addWidget(b)
        fo.body.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Auflösung"))
        row.addStretch()
        row.addWidget(self.sp_dpi)
        fo.body.addLayout(row)
        fo.body.addWidget(self.lbl_dpi)
        lay.addWidget(fo)
        self.sec_file = fo

        # --- ab hier nur mit "Alle Einstellungen zeigen"
        zon = Collapsible("Ausschnitt und Zonen", "Nur einen Teil vergleichen oder Bereiche ausnehmen")
        h = QLabel("Ausschnitt: nur diesen Teil der Zeichnung vergleichen (schneller). Der passende Bereich in B "
                   "wird automatisch gesucht; mit „Bereiche zuordnen“ wählt man ihn selbst.")
        h.setObjectName("hint")
        h.setWordWrap(True)
        zon.body.addWidget(h)
        row = QHBoxLayout()
        self.btn_crop = QPushButton("Ausschnitt wählen")
        self.btn_crop.setToolTip("Dann im Bild einen Rahmen aufziehen")
        self.btn_crop.clicked.connect(lambda: self._set_tool("crop"))
        self.btn_crop_off = QPushButton("Ganzes Blatt")
        self.btn_crop_off.clicked.connect(lambda: self._crop_reset())
        self.btn_crop_off.setEnabled(False)
        row.addWidget(self.btn_crop)
        row.addWidget(self.btn_crop_off)
        zon.body.addLayout(row)
        b = QPushButton("Bereiche zuordnen (A ↔ B) …")
        b.setToolTip("Bereich in A und passenden Bereich in B selbst wählen, z. B. wenn eine Ansicht "
                     "auf dem Blatt verschoben oder anders skaliert wurde")
        b.clicked.connect(self.match_regions)
        zon.body.addWidget(b)
        self.lbl_crop = QLabel("Aktuell: ganzes Blatt")
        self.lbl_crop.setObjectName("hint")
        zon.body.addWidget(self.lbl_crop)
        h = QLabel("Zonen: Bereiche, die nicht verglichen werden (z. B. Schriftfeld, Stempel).")
        h.setObjectName("hint")
        h.setWordWrap(True)
        zon.body.addWidget(h)
        self.btn_zone = QPushButton("Zone zeichnen")
        self.btn_zone.setToolTip("Dann im Bild einen Rahmen aufziehen")
        self.btn_zone.clicked.connect(lambda: self._set_tool("zone"))
        zon.body.addWidget(self.btn_zone)
        self.list_zones = QListWidget()
        self.list_zones.setFixedHeight(64)
        zon.body.addWidget(self.list_zones)
        row = QHBoxLayout()
        b1, b2 = QPushButton("Entfernen"), QPushButton("Alle löschen")
        b1.clicked.connect(self._remove_zone)
        b2.clicked.connect(self._clear_zones)
        row.addWidget(b1)
        row.addWidget(b2)
        zon.body.addLayout(row)
        self.s_border = SliderRow("Randstreifen (px)", 0, 300, 0, 5, 0,
                                  "Zeichnungsrahmen am Blattrand nicht vergleichen.")
        zon.body.addWidget(self.s_border)
        lay.addWidget(zon)

        self.vfilter = (None, None)
        self.vinfo = {"A": None, "B": None}
        vec = Collapsible("Vektordaten (PDF)", "Exakter Vergleich, Ebenen und Farben")
        self.lbl_vec = QLabel("Bei PDF mit Vektordaten stehen hier weitere Funktionen bereit.")
        self.lbl_vec.setObjectName("hint")
        self.lbl_vec.setWordWrap(True)
        vec.body.addWidget(self.lbl_vec)
        self.chk_vec = QCheckBox("Vektorvergleich (exakt statt Pixel)")
        self.chk_vec.setToolTip("Vergleicht die Linien, Kurven und Texte des PDF direkt. Kein Rastern, keine "
                                "Ausrichtung nötig; beide Zeichnungen müssen dasselbe Koordinatensystem haben.")
        self.chk_vec.setEnabled(False)
        self.chk_vec.toggled.connect(lambda _: self._param_changed())
        vec.body.addWidget(self.chk_vec)
        self.sp_vtol = QDoubleSpinBox()
        self.sp_vtol.setDecimals(2)
        self.sp_vtol.setRange(0.0, 5.0)
        self.sp_vtol.setSingleStep(0.05)
        self.sp_vtol.setValue(0.05)
        self.sp_vtol.setSuffix(" mm")
        self.sp_vtol.setToolTip("Lagetoleranz: Elemente, die weniger abweichen, gelten als gleich.")
        self.sp_vtol.valueChanged.connect(lambda _: self._param_changed())
        row = QHBoxLayout()
        row.addWidget(QLabel("Toleranz"))
        row.addWidget(self.sp_vtol)
        vec.body.addLayout(row)
        self.btn_vfilter = QPushButton("Ebenen und Farben …")
        self.btn_vfilter.setToolTip("Nur bestimmte Ebenen oder Farben vergleichen (z. B. ohne Bemaßung)")
        self.btn_vfilter.clicked.connect(self.open_vfilter)
        self.btn_vfilter.setEnabled(False)
        vec.body.addWidget(self.btn_vfilter)
        self.lbl_vfilter = QLabel("Filter: alles")
        self.lbl_vfilter.setObjectName("hint")
        vec.body.addWidget(self.lbl_vfilter)
        lay.addWidget(vec)
        self.sec_vec = vec

        self.s_thr = SliderRow("Linienschwelle", 0, 255, 128, 1, 0,
                               "Dunkler als dieser Wert = Linie. Höher erfasst auch blasse/gelbe Linien.")
        self.cb_align = QComboBox()
        self.cb_align.addItems(["affine", "euclidean", "translation", "none"])
        self.cb_align.setToolTip("affine = Verschiebung+Drehung+Skalierung; euclidean = +Drehung; "
                                 "translation = nur Verschiebung; none = keine")
        self.s_hatch = SliderRow("Schraffur-Unterdrückung (px)", 0, 40, 16, 1, 0,
                                 "Max. Linienabstand einer Schraffur; gleich dichte Schraffur ist keine Änderung. 0 = aus.")
        self.s_move = SliderRow("Blöcke verschoben (px)", 0, 300, 100, 5, 0,
                                "Suchbereich für komplett verschobene Blöcke (grün). 0 = aus.")
        self.s_obj = SliderRow("Objekt-Verschiebung (px)", 0, 150, 40, 1, 0,
                               "Einzelne Maße/Texte, die nur so weit verschoben sind, gelten nicht als Änderung. 0 = aus.")
        self.s_rot = SliderRow("Objekt-Drehung (Grad)", 0, 10, 3, 0.5, 1,
                               "Zusätzliche Drehung für die Objekt-Suche. 0 = keine Drehung.")
        self.s_cell = SliderRow("Kachelgröße (px)", 100, 1200, 400, 50, 0,
                                "Kleinere Kacheln = feinere lokale Ausrichtung.")
        self.s_maxs = SliderRow("Max. Kachelverschiebung (px)", 0, 100, 30, 1, 0,
                                "Größte lokale Verschiebung je Kachel.")
        adv = Collapsible("Erweiterte Optionen", "Für den normalen Vergleich nicht nötig")
        adv.body.addWidget(self.s_thr)
        row = QHBoxLayout()
        row.addWidget(QLabel("Ausrichtung"))
        row.addWidget(self.cb_align, 1)
        adv.body.addLayout(row)
        for w in (self.s_hatch, self.s_move, self.s_obj, self.s_rot, self.s_cell, self.s_maxs):
            adv.body.addWidget(w)
        self.chk_edges = QCheckBox("Kantens\u00e4ume an Linien ignorieren")
        self.chk_edges.setChecked(True)
        self.chk_edges.setToolTip("1 Pixel d\u00fcnne S\u00e4ume direkt an Linien, die in beiden Zeichnungen vorkommen, "
                                  "gelten nicht als \u00c4nderung (Versatz oder Strichst\u00e4rke beim Scannen/Rendern).")
        self.chk_edges.toggled.connect(lambda _: self._param_changed())
        adv.body.addWidget(self.chk_edges)
        self.chk_glyphs = QCheckBox("Zeichen genau pr\u00fcfen (\u00e4hnliche Ziffern)")
        self.chk_glyphs.setChecked(True)
        self.chk_glyphs.setToolTip("Ziffern und Buchstaben Form gegen Form vergleichen, damit z. B. 41.8 \u2192 43.2 "
                                   "sicher als \u00c4nderung erkannt wird, obwohl sich die Ziffern stark \u00fcberdecken.")
        self.chk_glyphs.toggled.connect(lambda _: self._param_changed())
        adv.body.addWidget(self.chk_glyphs)
        self.chk_flatten = QCheckBox("Ungleichm\u00e4\u00dfiges Papier ausgleichen")
        self.chk_flatten.setToolTip("F\u00fcr Scans mit Schatten, Flecken oder vergilbtem Papier: die Helligkeit des "
                                    "Papiers wird vor dem Vergleich ausgeglichen. \u201eAutomatisch einstellen\u201c "
                                    "schaltet das bei Bedarf selbst ein.")
        self.chk_flatten.toggled.connect(lambda _: self._param_changed())
        adv.body.addWidget(self.chk_flatten)
        b = QPushButton("Standardwerte")
        b.clicked.connect(self._reset_params)
        adv.body.addWidget(b)
        lay.addWidget(adv)
        self.expert_widgets = [zon, adv]
        lay.addStretch()

        for w in (self.s_thr, self.s_tol, self.s_hatch, self.s_move, self.s_obj, self.s_rot, self.s_area,
                  self.s_cell, self.s_maxs, self.s_border):
            w.changed.connect(self._param_changed)
        self.cb_align.currentIndexChanged.connect(self._param_changed)
        self.sp_dpi.valueChanged.connect(self._dpi_changed)
        self.sp_scale.valueChanged.connect(self._update_units)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(12, 6, 12, 12)
        self.chk_live = QCheckBox("Automatisch neu berechnen")
        self.chk_live.setChecked(False)
        self.chk_live.setToolTip("Nach jeder Änderung eines Reglers sofort neu vergleichen")
        self.expert_widgets.append(self.chk_live)
        self.btn_run = QPushButton("Vergleichen")
        self.btn_run.setObjectName("primary")
        self.btn_run.clicked.connect(self.start_compute)
        bl.addWidget(self.chk_live)
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
        self.btn_regs = QPushButton("Änderungen suchen und nummerieren")
        self.btn_regs.setObjectName("primary")
        self.btn_regs.clicked.connect(self.find_regs)
        l1.addWidget(self.btn_regs)
        nav = QGridLayout()                       # Zeile 1: blaettern, Zeile 2: bewerten
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(4)
        self._review_buttons = []
        for (act, txt, row, col, span) in ((self.act_prev, "Vorige", 0, 0, 1), (self.act_next, "Nächste", 0, 1, 2),
                                           (self.act_ok, "Geprüft", 1, 0, 1), (self.act_reject, "Abgelehnt", 1, 1, 1),
                                           (self.act_comment, "Kommentar …", 1, 2, 1)):
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
        row = QHBoxLayout()
        row.addWidget(QLabel("Zeigen:"))
        self.cb_filter = QComboBox()
        self.cb_filter.addItems(["Änderungen", "Alle (auch verschoben)", "entfernt", "neu", "geändert",
                                 "verschoben", "Maße", "offen"])
        self.cb_filter.setToolTip("„Änderungen“ = alles außer nur verschobenen Teilen. „Maße“ = geänderte "
                                  "Maßzahlen, „offen“ = noch nicht geprüft.")
        self.cb_filter.currentIndexChanged.connect(self._fill_table)
        row.addWidget(self.cb_filter, 1)
        self.chk_regs = QCheckBox("Im Bild zeigen")
        self.chk_regs.setChecked(True)
        self.chk_regs.toggled.connect(self._toggle_regs)
        row.addWidget(self.chk_regs)
        l1.addLayout(row)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Status", "Nr", "Typ", "Pos. mm", "Text / Kommentar"])
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
        self.btn_region = QPushButton("Selbst markieren")
        self.btn_region.setToolTip("Eigenen Bereich als Änderung eintragen: Rahmen im Bild aufziehen.")
        self.btn_region.clicked.connect(lambda: self._set_tool("region"))
        self.btn_regdel = QPushButton("Löschen")
        self.btn_regdel.setToolTip("Gewählte Zeile(n) aus der Liste entfernen")
        self.btn_regdel.clicked.connect(self._reg_delete)
        self.btn_regclr = QPushButton("Liste leeren")
        self.btn_regclr.clicked.connect(self._reg_clear)
        for b in (self.btn_region, self.btn_regdel, self.btn_regclr):
            row.addWidget(b)
        l1.addLayout(row)
        QShortcut(QKeySequence("Delete"), self.table, activated=self._reg_delete).setContext(
            Qt.ShortcutContext.WidgetShortcut)
        more = Collapsible("Texte und Maße lesen", "PDF-Text, Texterkennung (OCR), Maßzahlen, Index")
        self.s_group = SliderRow("Gruppierung (px)", 0, 150, 25, 5, 0,
                                 "Wie nah beieinander liegende Unterschiede zu EINEM Eintrag zusammengefasst werden.")
        self.s_group.changed.connect(self._group_changed)
        more.body.addWidget(self.s_group)
        self.group_timer = QTimer(self)
        self.group_timer.setSingleShot(True)
        self.group_timer.timeout.connect(self._regroup)
        self.btn_pdftext = QPushButton("Text aus PDF lesen (exakt)")
        self.btn_pdftext.clicked.connect(self.run_pdftext)
        self.btn_dims = QPushButton("Maßzahlen vergleichen")
        self.btn_dims.setToolTip("Meldet Maße wie „12,5 → 12,8“ getrennt von rein grafischen Änderungen")
        self.btn_dims.clicked.connect(self.run_dims)
        self.btn_ocr = QPushButton("Text lesen (OCR)")
        self.btn_ocr.setToolTip("Liest den Text in jedem geänderten Bereich. Braucht das Zusatzpaket "
                                "rapidocr-onnxruntime.")
        self.btn_ocr.clicked.connect(self.run_ocr)
        self.btn_idx = QPushButton("Index prüfen")
        self.btn_idx.clicked.connect(self.run_index)
        for b in (self.btn_pdftext, self.btn_dims, self.btn_ocr, self.btn_idx):
            more.body.addWidget(b)
        l1.addWidget(more)
        tabs.addTab(t1, "Änderungen")

        t2 = QWidget()
        t2.setObjectName("panel")
        l2 = QVBoxLayout(t2)
        l2.setContentsMargins(0, 6, 0, 0)
        h = QLabel("Werkzeug links wählen (Text, Wolke, Pfeil …) und ins Bild klicken. Mit „Auswahl“ "
                   "anklicken, verschieben und an den Ecken die Größe ändern. Doppelklick = bearbeiten, "
                   "Rechtsklick = Menü, Entf = löschen.")
        h.setObjectName("hint")
        h.setWordWrap(True)
        l2.addWidget(h)
        self.list_anns = QListWidget()
        self.list_anns.currentRowChanged.connect(self._ann_row)
        self.list_anns.itemDoubleClicked.connect(lambda it: self._ann_edit(self.list_anns.row(it)))
        l2.addWidget(self.list_anns, 1)
        row = QHBoxLayout()
        for text, fn in (("Bearbeiten …", lambda: self._ann_edit(self.canvas.ann_selected)),
                         ("Duplizieren", self._ann_duplicate), ("Löschen", self._ann_delete)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, f=fn: f())
            row.addWidget(b)
        l2.addLayout(row)
        tabs.addTab(t2, "Markierungen")

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(110)
        self.log.setPlaceholderText("Protokoll")
        lay.addWidget(self.log)
        self.expert_widgets.append(self.log)
        self._fill_table()

    # ----------------------------------------------------------------- Statusleiste
    def _build_statusbar(self):
        sb = self.statusBar()
        self.lbl_status = QLabel("Bereit")
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setFixedWidth(180)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_cancel.setToolTip("Laufende Berechnung abbrechen")
        self.btn_cancel.clicked.connect(self.cancel_job)
        self.btn_cancel.hide()
        self.lbl_pos = QLabel("")
        self.lbl_pos.setObjectName("hint")
        sb.addWidget(self.lbl_status, 1)
        sb.addPermanentWidget(self.progress)
        sb.addPermanentWidget(self.btn_cancel)
        sb.addPermanentWidget(self.lbl_pos)

    # ----------------------------------------------------------------- Zustaende
    def _scale_dialog(self):
        n, ok = QInputDialog.getDouble(self, "Ma\u00dfstab", "Zeichnungsma\u00dfstab 1 : n  (f\u00fcr 2:1 bitte 0,5 "
                                       "eingeben):", self.scale_n(), 0.01, 1000, 3)
        if ok:
            self.sp_scale.setValue(n)

    def _toggle_invert(self, on):
        self.settings.setValue("invert", "true" if on else "false")
        self.canvas.invert = on
        self.canvas.update()

    def _toggle_color(self, on):
        self.settings.setValue("color", "true" if on else "false")
        self.canvas.show_color = on
        self.canvas.update()

    def _toggle_clouds(self, on):
        self.settings.setValue("clouds", "true" if on else "false")
        self.canvas.reg_clouds = on
        self.canvas.update()

    def _set_expert(self, on):
        self.settings.setValue("expert", "true" if on else "false")
        for w in self.expert_widgets:
            w.setVisible(on)
        self._update_vec_visibility()

    def _update_vec_visibility(self):
        both_vec = all(self.vinfo.get(w) and self.vinfo[w]["vector"] for w in "AB")
        self.sec_vec.setVisible(self.act_expert.isChecked() or both_vec)

    def _refresh_icons(self):
        for a, name in self._icon_actions:
            a.setIcon(icon(name))
        for b, act in getattr(self, "_review_buttons", []):
            b.setIcon(act.icon())
        for b, name in self._icon_buttons:
            b.setIcon(icon(name))
        self.palette_frame.findChildren(QFrame)  # Stylesheet neu anwenden
        for line in self.palette_frame.findChildren(QFrame):
            if line.frameShape() == QFrame.Shape.HLine:
                line.setStyleSheet(f"color: {THEME['border']};")

    def _update_enabled(self):
        """Ohne Ergebnis sind Ansicht, Zoom und Speichern ausgegraut (keine toten Knoepfe)."""
        has = self.payload is not None
        for a in (self.act_fit, self.act_100, self.act_zoom_in, self.act_zoom_out, self.act_zoom_box, self.act_rotate,
                  self.act_export_img, self.act_export_annpdf, self.act_export_pdf, self.act_export_csv,
                  self.act_print, self.act_copy, self.act_find, self.act_proj_save, self.act_proj_save_as):
            a.setEnabled(has)
        for a in self.mode_actions.values():
            a.setEnabled(has and not self.view_only)
        for b in self.seg_buttons.values():
            b.setEnabled(has)
        for a in self.tool_actions.values():
            a.setEnabled(has)
        self.act_compare.setEnabled(bool(self.path_a and self.path_b) and not self.running)
        self.lbl_zoom.setEnabled(has)

    def _set_view_only(self, on):
        """Nur eine Datei: Vergleichsfunktionen ausblenden (reines Ansehen)."""
        self.view_only = on
        self.act_view_box.setVisible(not on)
        self.sep_views.setVisible(not on)
        self.act_compare_tb.setVisible(not on)
        for key in ("A", "B", "D", "Y", "O", "K", "S", "N", "R"):
            self.mode_actions[key].setEnabled(not on)
        for a in (self.act_find, self.act_next, self.act_prev, self.act_ok, self.act_reject, self.act_comment,
                  self.act_export_pdf, self.act_export_csv, self.act_auto):
            a.setEnabled(not on)
        self.canvas.show_legend = not on
        self.tabs.setTabVisible(0, not on)
        if on:
            self.act_left.setChecked(False)
            self.tabs.setCurrentIndex(1)
