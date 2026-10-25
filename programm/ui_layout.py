"""Hauptfenster: Aufbau der Oberflaeche (Menue, Leisten, Werkzeugpalette, Seitenleisten, Startseite).

Grundsaetze: wenig auf einmal zeigen, alles beschriftet, Navigation (zoomen/verschieben) geht immer
ohne Werkzeugwechsel. Selten gebrauchte Einstellungen erscheinen erst mit "Alle Einstellungen zeigen".
"""
import i18n
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_icons import icon
from ui_start import StartPage
from ui_widgets import Banner, Collapsible, DoubleClickFilter, ElideLabel, FlowLayout, OverlayHost, PaletteFrame, PanelScroll, Section, SliderRow

VIEWS = (("A", tr("Alt"), "1", tr("Nur die alte Zeichnung A")),
         ("B", tr("Neu"), "2", tr("Nur die neue Zeichnung B")),
         ("D", tr("Vergleich"), "3", tr("Rot = nur alt, Blau = nur neu, Grün = nur verschoben")),
         ("O", tr("Überlagern"), "4", tr("Beide Zeichnungen ohne Toleranz übereinander")),
         ("Y", tr("Nebeneinander"), "9", tr("Alt und neu nebeneinander, gemeinsam zoomen und verschieben")),
         ("S", tr("Schieber"), "5", tr("Links alt, rechts neu; Trennlinie ziehen")),
         ("K", tr("Blinken"), "6", tr("Wechselt zwischen alt und neu (Leertaste = von Hand)")))
# Alt/Neu mit hervorgehobenen Aenderungen: im Umschalter "Alt"/"Neu" + Haekchen in der Optionszeile
MORE_VIEWS = (("N", tr("Neu mit Änderungen"), "7", tr("Neue Zeichnung, neue und geänderte Stellen blau")),
              ("R", tr("Alt mit Änderungen"), "8", tr("Alte Zeichnung, entfernte und geänderte Stellen rot")))
SEG_OF = {"N": "B", "R": "A"}
TOOLS = (("hand", tr("Auswahl"), "select", "V", tr("Anklicken und verschieben. Leeres Papier ziehen = Ansicht verschieben.")),
         ("area", tr("Bereich"), "area", "B", tr("Bereich aufziehen (mit Umschalt/Strg weitere dazu). Wählt Zeichnung, "
                                              "Markierungen und Änderungen darin: kopieren, ausschneiden, verschieben, "
                                              "löschen, exportieren.")),
         ("zoom", tr("Zoom"), "zoom_box", "Z", tr("Zoom-Rahmen mit Fadenkreuz: Bereich aufziehen. Einfacher Klick = ganze "
                                            "Zeichnung. Geht auch jederzeit mit der rechten Maustaste.")),
         ("measure", tr("Messen"), "measure", "M", tr("Länge, Winkel, Radius, Fläche messen; rastet an Linien ein")),
         ("text", tr("Text"), "text", "T", tr("Ins Bild klicken und Text eingeben")),
         ("cloud", tr("Wolke"), "cloud", "W", tr("Revisionswolke aufziehen")),
         ("rect", tr("Rahmen"), "rect", "", tr("Rahmen aufziehen")),
         ("ellipse", tr("Ellipse"), "ellipse", "", tr("Ellipse oder Kreis aufziehen")),
         ("line", tr("Linie"), "line", "", tr("Linie vom Anfang zum Ende ziehen")),
         ("polyline", tr("Linienzug"), "polyline", "", tr("Punkte anklicken; Doppelklick, Enter oder Rechtsklick beendet")),
         ("polygon", tr("Polygon"), "polygon", "", tr("Eckpunkte anklicken; Doppelklick, Enter oder Rechtsklick schließt")),
         ("arrow", tr("Pfeil"), "arrow", "", tr("Pfeil vom Anfang zur Spitze ziehen")),
         ("pen", tr("Stift"), "pen", "", tr("Freihand zeichnen; bleibt eine verschiebbare, änderbare Linie")),
         ("highlight", tr("Marker"), "highlight", "", tr("Textmarker: Fläche farbig hinterlegen")),
         ("redact", tr("Schwärzen"), "redact", "", tr("Bereich schwärzen: in jeder Ausgabe (Bild, PDF, Druck, Kopie) "
                                                     "unwiderruflich eingebrannt")),
         ("pixelate", tr("Verpixeln"), "pixelate", "", tr("Bereich verpixeln (Mosaik); Größe = Blockgröße. In jeder "
                                                         "Ausgabe eingebrannt")),
         ("number", tr("Nummer"), "number", "", tr("Fortlaufend nummerierte Kreise setzen")),
         ("approval", tr("Stempel"), "stamp", "", tr("Stempel mit Status, Name und Datum")))


SHAPES = ("rect", "ellipse", "line", "polyline", "polygon")   # in der Palette unter "Formen" (Pfeil eigener Knopf)
PALETTE_GROUPS = (SHAPES, ("redact", "pixelate"), ("number", "approval"))   # je ein Knopf, Auswahl ueber das Dreieck
NAV_TOOLS = ("hand", "area", "zoom", "measure")              # Doppelklick hier: "Werkzeug behalten" aus


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
        self.act_start = A(tr("Startseite"), self.show_start)
        self.act_open_a = A(tr("Alte Zeichnung (A) öffnen …"), lambda: self.open_file("A"), "Ctrl+Shift+A", ico="open")
        self.act_open_b = A(tr("Neue Zeichnung (B) öffnen …"), lambda: self.open_file("B"), "Ctrl+Shift+B")
        self.act_open_view = A(tr("Zeichnung ansehen …"), self.open_view_only, "Ctrl+Shift+O")
        self.act_proj_open = A(tr("Projekt öffnen …"), self.project_open, "Ctrl+O")
        self.act_proj_save = A(tr("Projekt speichern"), self.project_save, "Ctrl+S")
        self.act_proj_save_as = A(tr("Projekt speichern unter …"), lambda: self.project_save(True), "Ctrl+Shift+S")
        self.act_export_img = A(tr("Als Bild speichern (wie angezeigt) …"), self.export_image, "Ctrl+E",
                                tr("Bild mit Markierungen wie angezeigt als PNG, JPG, TIFF oder PDF"), ico="save")
        self.act_export_ocrpdf = A(tr("Durchsuchbares PDF (Texterkennung) …"), lambda: self.export_searchable_pdf(),
                                   tip=tr("Zeichnung als PDF mit unsichtbarem Text: in jedem PDF-Programm durchsuchbar "
                                          "und kopierbar (Scans per Texterkennung)"))
        self.act_vectorize = A(tr("Vektorisieren (SVG, PDF, DXF) …"), lambda: self.vectorize_drawing(),
                               tip=tr("Pixelzeichnung in Linien umwandeln, z. B. für CAD (DXF) oder verlustfreies "
                                      "Vergrößern"))
        self.act_export_svg = A(tr("Als SVG mit Ebenen …"), lambda: self.export_svg(),
                                tip=tr("Zeichnung, Änderungen und Markierungen als getrennte Ebenen; Markierungen als "
                                       "Vektoren (in Inkscape, Illustrator & Co. bearbeitbar)"))
        self.act_export_annpdf = A(tr("PDF mit Anmerkungen (Acrobat) …"), self.export_annotated_pdf)
        self.act_export_pdf = A(tr("PDF-Änderungsbericht …"), self.export_pdf)
        self.act_export_csv = A(tr("Änderungsliste (CSV) …"), self.export_csv)
        self.act_print = A(tr("Drucken im Maßstab …"), self.print_scaled, "Ctrl+P", ico="print")
        self.act_ann_save = A(tr("Markierungen speichern …"), self.ann_save)
        self.act_ann_load = A(tr("Markierungen laden …"), self.ann_load)
        self.act_import_comments = A(tr("Kommentare einlesen (XFDF, PDF) …"), self.import_comments,
                                     tip=tr("Kommentare aus Acrobat & Co. übernehmen: XFDF-Datei oder kommentierte PDF"))
        self.act_export_all_ann = A(tr("PDF mit Anmerkungen – alle Seiten …"), lambda: self.export_all_pages("annpdf"),
                                    tip=tr("Jede Seite mit ihren Markierungen (im Vergleich: Ergebnis mit Änderungen) "
                                           "in einer PDF"))
        self.act_export_all_report = A(tr("PDF-Änderungsbericht – alle Seiten …"),
                                       lambda: self.export_all_pages("report"),
                                       tip=tr("Änderungsbericht über alle Seiten in einer PDF"))
        self.act_export_measures = A(tr("Messungen und Zählung als CSV (Excel) …"), lambda: self.export_measures(),
                                     tip=tr("Alle Maße mit Wert, Einheit und Seite sowie die Anzahl je Markierungsart"))
        self.act_export_xfdf = A(tr("Markierungen als XFDF speichern …"), self.export_xfdf,
                                 tip=tr("Für Acrobat & Co.: Kommentare → Importieren"))
        self.act_batch = A(tr("Stapelvergleich (viele Dateien) …"), self.open_batch)
        self.act_revisions = A(tr("Revisionen vergleichen (A → B → C) …"), self.open_revisions)
        self.act_quit = A(tr("Beenden"), QApplication.instance().closeAllWindows, "Ctrl+Q")
        self.act_close = A(tr("Schlie\u00dfen"), self.close_document, "Ctrl+W",
                           tr("Vergleich bzw. Projekt schlie\u00dfen und zur Startseite (das Programm bleibt offen)"))
        self.act_new_window = A(tr("Neues Fenster"), self.new_window, "Ctrl+N",
                                tr("Weiteres Fenster f\u00fcr einen anderen Vergleich"))
        self.act_quit.setMenuRole(QAction.MenuRole.QuitRole)

        self.act_undo = A(tr("Rückgängig"), self.undo, "Ctrl+Z", tr("Rückgängig (Markierungen, Maße, Zonen)"), "undo")
        self.act_redo = A(tr("Wiederholen"), self.redo, "Ctrl+Shift+Z", tr("Wiederholen"), "redo")
        self.act_redo2 = QShortcut(QKeySequence("Ctrl+Y"), self, activated=self.redo)
        self.act_delete = A(tr("Markierung löschen"), self._ann_delete, "Delete", canvas_key=True)
        self.act_ann_clear = A(tr("Alle Markierungen löschen …"), self._ann_clear)
        self.act_copy = A(tr("Kopieren"), self.copy_result, "Ctrl+C",
                          tr("Bereichsauswahl, gewählte Markierungen oder sonst die ganze Ansicht (wie angezeigt) "
                             "kopieren"), canvas_key=True)
        self.act_paste = A(tr("Einfügen"), self.paste, "Ctrl+V",
                           tr("Aus der Zwischenablage einfügen: Markierungen, Bild (verschiebbar) oder Text. Ist nichts "
                              "geöffnet, wird ein Bild als Zeichnung geöffnet."))
        self.act_open_clip = A(tr("Bild aus Zwischenablage öffnen"), self.open_clipboard,
                               tip=tr("Z. B. ein Bildschirmfoto als Zeichnung öffnen"))
        self.act_cut = A(tr("Ausschneiden"), lambda: self.area_cut() if self.canvas.sel_rects else None, "Ctrl+X",
                         tr("Bereichsauswahl ausschneiden (Markierungen; beim Ansehen auch die Zeichnung)"))
        self.act_copy_sel = A(tr("Nur Linien/Geometrie kopieren …"), self.start_copy_selection, "Ctrl+Shift+C",
                              tr("Bereich aufziehen und kopieren: alles, nur Linien oder nur die Geometrie "
                                 "(ohne Maße, Text und dünne Linien)"))
        self.act_move_sel = A(tr("Ausschnitt verschieben"), self.start_move_region,
                              tip=tr("Teil der Zeichnung ausschneiden und an anderer Stelle einsetzen "
                                     "(beim Ansehen einer einzelnen Zeichnung)"))
        self.act_save_drawing = A(tr("Bearbeitete Zeichnung speichern …"), self.save_drawing,
                                  tip=tr("Die Zeichnung mit verschobenen Ausschnitten als Bild oder PDF speichern "
                                         "(ohne Markierungen)"))
        self.act_save_drawing.setEnabled(False)
        self.act_sheet_crop = A(tr("Auf Bereich zuschneiden (endgültig)"), lambda: self.sheet_crop(),
                                tip=tr("Die Zeichnung selbst auf den mit „Bereich“ gewählten Teil zuschneiden"))
        self.act_frame_clear = A(tr("Zuschnitt aufheben"), lambda: self.clear_crop_frame(),
                                 tip=tr("Den Zuschnitt-Rahmen entfernen; Ausgaben zeigen wieder das ganze Blatt"))
        self.act_frame_apply = A(tr("Zuschnitt endgültig anwenden"), lambda: self.apply_crop_frame(),
                                 tip=tr("Die Zeichnung selbst auf den Zuschnitt-Rahmen zuschneiden (rückgängig mit Strg+Z)"))
        for a in (self.act_frame_clear, self.act_frame_apply):     # erst sichtbar, wenn ein Zuschnitt gesetzt ist
            a.setEnabled(False)
            a.setVisible(False)
        self.act_rot_cw = A(tr("90° nach rechts drehen"), lambda: self.sheet_rotate(1))
        self.act_rot_ccw = A(tr("90° nach links drehen"), lambda: self.sheet_rotate(3))
        self.act_rot_180 = A(tr("180° drehen"), lambda: self.sheet_rotate(2))
        self.act_adjust = A(tr("Helligkeit und Kontrast …"), lambda: self.sheet_adjust())
        self.act_size = A(tr("Bildgröße und Auflösung …"), lambda: self.sheet_size())
        self.act_background = A(tr("Hintergrund ausgleichen …"), lambda: self.sheet_background(),
                                tip=tr("Schatten, Falten und vergilbtes Papier eines Scans herausrechnen; Papier weiß "
                                       "oder in eigener Farbe"))
        self.act_straighten = A(tr("Gerade ausrichten …"), lambda: self.sheet_straighten(),
                                tip=tr("Schräg eingescannte Zeichnung gerade drehen: Winkel automatisch erkennen oder "
                                       "von Hand"))
        self.act_straighten_line = A(tr("Gerade ausrichten an Linie"), lambda: self.start_straighten_line(),
                                     tip=tr("Eine Kante nachziehen, die waagerecht oder senkrecht sein soll"))
        self.act_perspective = A(tr("Entzerren (4 Ecken) …"), lambda: self.sheet_perspective(),
                                 tip=tr("Foto eines Blatts rechteckig rechnen: Ecken werden erkannt und lassen sich "
                                        "verschieben; Papierformat wählbar, damit die mm stimmen"))
        self.sheet_actions = (self.act_move_sel, self.act_sheet_crop, self.act_rot_cw, self.act_rot_ccw,
                              self.act_rot_180, self.act_straighten, self.act_straighten_line, self.act_perspective,
                              self.act_background, self.act_adjust, self.act_size)

        self.mode_actions = {}
        grp = QActionGroup(self)
        for key, label, k, tip in VIEWS + MORE_VIEWS:
            a = A(label, lambda m=key: self._set_mode(m), k, tr("{} (Taste {})").format(tip, k), checkable=False, canvas_key=True)
            a.setCheckable(True)
            grp.addAction(a)
            self.mode_actions[key] = a
        self.mode_actions["D"].setChecked(True)
        self.act_fit = A(tr("Ganze Zeichnung"), lambda: self.canvas.fit(), "F", tr("Ganze Zeichnung zeigen (F oder Doppelklick)"),
                         "fit", canvas_key=True)
        self.act_100 = A(tr("Originalgröße (100 %)"), self._zoom100, "Ctrl+0")
        self.act_zoom_in = A(tr("Vergrößern"), lambda: self.canvas.zoom_step(1.25), "Ctrl++", tr("Vergrößern (Mausrad, +)"), "zoom_in")
        self.act_zoom_out = A(tr("Verkleinern"), lambda: self.canvas.zoom_step(1 / 1.25), "Ctrl+-", tr("Verkleinern (Mausrad, −)"), "zoom_out")
        self.act_zoom_box = A(tr("Zoom-Rahmen"), lambda: self._set_tool("zoom"),
                              tip=tr("Bereich aufziehen und hineinzoomen (geht auch jederzeit mit der rechten Maustaste)"),
                              ico="zoom_box")
        self.act_rotate = A(tr("Ansicht drehen (90°)"), lambda: self.canvas.rotate_view(), "R",
                            tr("Nur die Anzeige drehen (Taste R)"), "rotate", canvas_key=True)
        self.act_overview = A(tr("Übersicht"), self._toggle_overview, tip=tr("Kleine Übersicht unten rechts, "
                              "wenn hineingezoomt ist. Klicken oder ziehen springt dorthin."), ico="overview", checkable=True)
        self.act_overview.setChecked(self.settings.value("overview", "true") == "true")
        self.act_loupe = A(tr("Lupe"), self._toggle_loupe, "L", tr("Vergrößert den Bereich unter dem Mauszeiger (L)"),
                           "loupe", checkable=True, canvas_key=True)
        self.act_overlays = A(tr("Markierungen anzeigen"), self._toggle_overlays, "H",
                              tr("Nummern, Zonen, Markierungen und Maße ein-/ausblenden (H). "
                              "Ausgeblendetes wird auch nicht gespeichert."), checkable=True, canvas_key=True)
        self.act_overlays.setChecked(True)
        self.act_invert = A(tr("Farben umkehren"), self._toggle_invert, "I", tr("Helle Linien auf dunklem Grund (nur "
                            "Anzeige; gespeicherte Bilder bleiben normal). Taste I"), checkable=True, canvas_key=True)
        self.act_invert.setChecked(self.settings.value("invert", "false") == "true")
        self.act_color = A(tr("Original anzeigen (Farbe, Graustufen)"), self._toggle_color,
                           tip=tr("Alt, Neu, Nebeneinander, Schieber und Blinken zeigen die Datei, wie sie ist (Farbe oder "
                           "Graustufen). Aus = Schwarz-Wei\u00df-Fassung, mit der verglichen wird."), checkable=True)
        self.act_color.setChecked(self.settings.value("color", "true") == "true")
        self.act_clouds = A(tr("\u00c4nderungen als Revisionswolken"), self._toggle_clouds,
                            tip=tr("Nummerierte \u00c4nderungen als Wolke statt als Rahmen zeigen und speichern"),
                            ico="cloud", checkable=True)
        self.act_clouds.setChecked(self.settings.value("clouds", "false") == "true")
        self.act_legend = A(tr("Legende anzeigen"), self._toggle_legend,
                            tip=tr("Farblegende im Vergleich – auch beim Speichern als Bild, Kopieren und Drucken"),
                            checkable=True)
        self.act_legend.setChecked(self.settings.value("legend", "true") == "true")
        self.act_reset_settings = A(tr("Alle Einstellungen zurücksetzen …"), self.reset_all_settings,
                                    tip=tr("Darstellung, Sprache, Größe, Werte des Vergleichs und Werkzeugoptionen auf "
                                           "Standard; Dateien und Projekte bleiben unverändert"))
        self.act_layers = A(tr("Ebenen"), self._toggle_layers_tab, tip=tr("Ebenen ein-/ausblenden und sperren"),
                            ico="layers", checkable=True)
        self.act_left = A(tr("Optionen"), lambda on: self.left.setVisible(on),
                          tip=tr("Seitenleiste mit den Einstellungen des Vergleichs ein-/ausblenden"),
                          ico="settings", checkable=True)
        self.act_right = A(tr("Elemente"), lambda on: self.right.setVisible(on),
                           tip=tr("Seitenleiste mit allem, was auf der Zeichnung liegt: Änderungen, Markierungen und "
                                  "(über Ansicht → Ebenen) Ebenen"), ico="list", checkable=True)
        self.act_left.setIconText(tr("Optionen"))         # kurz fuer die Leiste oben; Menue behaelt den langen Text
        self.act_right.setIconText(tr("Elemente"))
        self.act_expert = A(tr("Alle Einstellungen zeigen"), self._set_expert, tip=tr("Auch selten gebrauchte Einstellungen, "
                            "Vektordaten, Zonen und das Protokoll zeigen"), checkable=True)
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
        self.act_zone = A(tr("Zone zeichnen (nicht vergleichen)"), lambda: self._set_tool("zone"))
        self.act_crop = A(tr("Ausschnitt wählen"), lambda: self._set_tool("crop"))
        self.act_crop_off = A(tr("Ganzes Blatt vergleichen"), lambda: self._crop_reset())
        self.act_match = A(tr("Bereiche zuordnen (A ↔ B) …"), self.match_regions)
        self.act_align = A(tr("Manuell ausrichten (3 Punkte)"), self.start_manual_align,
                           tip=tr("Wenn die automatische Ausrichtung danebenliegt: drei gleiche Punkte in Alt und Neu "
                               "anklicken"))
        self.act_align_reset = A(tr("Manuelle Ausrichtung zurücksetzen"), self.reset_manual_align)
        self.act_align_reset.setEnabled(False)
        self.act_auto = A(tr("Automatisch einstellen"), self.auto_params, tip=tr("Toleranz, Schwelle und Suchbereiche aus "
                          "diesem Zeichnungspaar bestimmen"), ico="magic")
        self.act_compare = A(tr("Vergleichen"), self.start_compute, "Ctrl+Return", tr("Vergleich (neu) berechnen"), "compare")

        self.act_find = A(tr("Änderungen suchen"), self.find_regs, "Ctrl+Shift+F")
        self.act_renumber = A(tr("Änderungen neu nummerieren"), self.renumber_regs,
                              tip=tr("Liste fortlaufend ab 1 nummerieren (sonst behalten die Einträge ihre Nummer "
                                     "auch nach dem Löschen)"))
        self.act_search = A(tr("Text suchen …"), self.open_search, "Ctrl+F", tr("Text in der Zeichnung suchen (PDF-Text, "
                            "bei Bildern Texterkennung)"), "loupe")
        self.act_search_next = A(tr("Weitersuchen"), lambda: self.search_step(1), "F3", tr("Nächster Treffer (F3, Enter)"),
                                 "next")
        self.act_search_prev = A(tr("Rückwärts suchen"), lambda: self.search_step(-1), "Shift+F3", tr("Voriger Treffer "
                                 "(Umschalt+F3)"), "prev")
        self.act_next = A(tr("Nächste Änderung"), lambda: self.review_step(1), "N", tr("Zur nächsten offenen "
                          "Änderung (N)"), "next", canvas_key=True)
        self.act_prev = A(tr("Vorige Änderung"), lambda: self.review_step(-1), "P", tr("Zur vorigen Änderung (P)"),
                          "prev", canvas_key=True)
        self.act_ok = A(tr("Als geprüft markieren"), lambda: self.review_set("ok"), "G",
                        tr("Gewählte Änderung ist geprüft (G), weiter zur nächsten"), "check", canvas_key=True)
        self.act_reject = A(tr("Als abgelehnt markieren"), lambda: self.review_set("abgelehnt"), "X",
                            tr("Gewählte Änderung ist nicht in Ordnung (X)"), "reject", canvas_key=True)
        self.act_comment = A(tr("Kommentar …"), self.review_comment, "C", tr("Kommentar zur gewählten Änderung (C)"),
                             canvas_key=True)
        self.act_pages = A(tr("Alle Seiten vergleichen"), self.compare_all_pages)
        self.act_rej_zones = A(tr("Abgelehnte als Zonen übernehmen"), self.zones_from_rejected,
                               tip=tr("Als abgelehnt markierte Änderungen künftig nicht mehr vergleichen"))
        self.act_title = A(tr("Schriftfeld lesen"), self.read_title_block)
        self.act_text = A(tr("Geänderten Text finden"), self.run_text,
                          tip=tr("Liest den Text in jeder Änderung (Alt → Neu, auch Maße) – aus dem PDF, wenn es echten "
                                 "Text enthält, sonst per Texterkennung in jeder Lage (waagerecht und senkrecht), "
                                 "deutsch und englisch. Danach zeigen Liste und Bild nur Änderungen, deren Text sich "
                                 "geändert hat; „Zeigen: Änderungen“ holt alles zurück."))
        self.act_dims = A(tr("Geänderte Maße finden"), self.run_dims,
                          tip=tr("Liest die Zahlen jeder Änderung und zeigt danach nur die Änderungen, bei denen sich "
                                 "eine Maßzahl geändert hat (z. B. 12,5 → 12,8). Rein grafische Änderungen werden "
                                 "ausgeblendet; „Zeigen: Änderungen“ holt sie zurück."))
        self.act_index = A(tr("Schriftfeld-Index prüfen"), self.run_index,
                           tip=tr("Liest den Index (Revision) im Schriftfeld von Alt und Neu und warnt, wenn die "
                                  "Zeichnung geändert, der Index aber gleich geblieben ist – oder umgekehrt."))

        self.act_help = A(tr("Anleitung"), self.open_help, "F1", ico="help")
        self.act_help_cli = A(tr("Anleitung Kommandozeile"),
                              lambda: self._open_doc(os.path.join(HERE, i18n.doc("Anleitung_Kommandozeile.html"))))
        self.act_keys = A(tr("Tastenkürzel"), self.show_keys)
        self.act_logfile = A(tr("Logdatei öffnen"), self.open_logfile)
        self.act_cli = A(tr("Befehl für Kommandozeile kopieren"), self.copy_cli)
        self.act_shortcut = A(tr("Desktop-Verknüpfung erstellen"), self.make_shortcut)
        self.act_about = A(tr("Über ZGmax"), self.show_about)
        self.act_about.setMenuRole(QAction.MenuRole.AboutRole)

    def _build_menubar(self):
        mb = self.menuBar()
        m = mb.addMenu(tr("&Datei"))
        m.addAction(self.act_new_window)
        m.addAction(self.act_start)
        m.addSeparator()
        for a in (self.act_open_a, self.act_open_b, self.act_open_view, self.act_open_clip, self.act_proj_open):
            m.addAction(a)
        self.menu_recent = m.addMenu(tr("Zuletzt verwendet"))
        self.menu_recent.aboutToShow.connect(self._fill_recent_menu)
        m.addSeparator()
        for a in (self.act_proj_save, self.act_proj_save_as, self.act_close):
            m.addAction(a)
        m.addSeparator()
        ex = m.addMenu(tr("Exportieren"))                  # alles, was eine Datei erzeugt
        for a in (self.act_export_img, self.act_export_annpdf, self.act_export_all_ann, self.act_export_svg, None,
                  self.act_export_ocrpdf, self.act_vectorize, self.act_save_drawing, None, self.act_export_pdf,
                  self.act_export_all_report, self.act_export_csv):
            ex.addSeparator() if a is None else ex.addAction(a)   # Bild/PDF | Zeichnung umwandeln | Bericht
        m.addAction(self.act_print)
        m.addSeparator()
        mk = m.addMenu(tr("Markierungen"))
        for a in (self.act_ann_save, self.act_ann_load, None, self.act_import_comments, self.act_export_xfdf, None,
                  self.act_export_measures):
            mk.addSeparator() if a is None else mk.addAction(a)
        if os.name == "nt":
            m.addAction(self.act_shortcut)
        m.addSeparator()
        m.addAction(self.act_quit)

        m = mb.addMenu(tr("&Bearbeiten"))
        for a in (self.act_undo, self.act_redo):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_search, self.act_search_next, self.act_search_prev, self.act_title):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_delete, self.act_ann_clear, self.act_cut, self.act_copy, self.act_copy_sel, self.act_paste):
            m.addAction(a)
        m.addSeparator()
        sm = m.addMenu(tr("Zeichnung bearbeiten"))
        sm.setToolTip(tr("Beim Ansehen einer einzelnen Zeichnung; Original bleibt unverändert"))
        sm.setToolTipsVisible(True)
        for a in self.sheet_actions:
            sm.addAction(a)
            if a in (self.act_sheet_crop, self.act_rot_180, self.act_perspective):
                sm.addSeparator()
        sm.addSeparator()
        sm.addAction(self.act_save_drawing)
        m.addAction(self.act_frame_clear)
        m.addAction(self.act_frame_apply)

        m = mb.addMenu(tr("&Ansicht"))
        for key, *_ in VIEWS + MORE_VIEWS:
            m.addAction(self.mode_actions[key])
        m.addSeparator()
        for a in (self.act_fit, self.act_100, self.act_zoom_in, self.act_zoom_out, self.act_zoom_box, self.act_rotate):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_overview, self.act_loupe, self.act_overlays, self.act_legend, self.act_layers,
                  self.act_clouds):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_color)
        m.addAction(self.act_invert)
        m.addSeparator()
        for a in (self.act_left, self.act_right):
            m.addAction(a)
        m.addSeparator()
        look = m.addMenu(tr("Darstellung"))
        self.theme_actions = {}
        tg = QActionGroup(self)
        for key, txt in (("auto", tr("Automatisch (wie System)")), ("light", tr("Hell")), ("dark", tr("Dunkel"))):
            act = look.addAction(txt, lambda k=key: self.set_theme(k))
            act.setCheckable(True)
            tg.addAction(act)
            self.theme_actions[key] = act
        self.theme_actions[self.theme_mode].setChecked(True)
        lang = m.addMenu(tr("Sprache") + " / Language")
        lg = QActionGroup(self)
        cur_lang = i18n.setting()
        for key, txt in (("auto", tr("Automatisch (wie System)")), ("de", "Deutsch"), ("en", "English")):
            act = lang.addAction(txt, lambda k=key: self.set_language(k))
            act.setCheckable(True)
            act.setChecked(key == cur_lang)
            lg.addAction(act)
        size = m.addMenu(tr("Größe der Oberfläche"))
        sg = QActionGroup(self)
        cur = ui_scale_setting(self.settings)
        for v in UI_SCALES:
            act = size.addAction(f"{v * 100:.0f} %" + (tr("  (Standard)") if v == 1.0 else ""),
                                 lambda v=v: self.set_ui_scale(v))
            act.setCheckable(True)
            act.setChecked(abs(v - cur) < 0.01)
            sg.addAction(act)
        m.addAction(self.act_expert)

        m = mb.addMenu(tr("&Werkzeuge"))
        for key, *_ in TOOLS:
            m.addAction(self.tool_actions[key])
        chest = m.addMenu(tr("Werkzeugkasten"))
        chest.aboutToShow.connect(lambda c=chest: self._fill_toolchest(c))

        # Alles zum Vergleichen an einer Stelle: starten, einstellen, pruefen, auswerten, weitere Vergleiche
        m = mb.addMenu(tr("&Vergleichen"))
        for a in (self.act_compare, self.act_find, self.act_renumber):
            m.addAction(a)
        sm = m.addMenu(tr("Vergleich einstellen"))
        for a in (self.act_auto, self.act_align, self.act_align_reset, None, self.act_crop, self.act_crop_off,
                  self.act_match, self.act_zone):
            sm.addSeparator() if a is None else sm.addAction(a)
        m.addSeparator()
        for a in (self.act_next, self.act_prev, self.act_ok, self.act_reject, self.act_comment, self.act_rej_zones):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_text, self.act_dims, self.act_index):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_pages, self.act_batch, self.act_revisions):
            m.addAction(a)

        self.menu_windows = mb.addMenu(tr("&Fenster"))       # alle offenen Fenster (je Dokument eines)
        self.menu_windows.aboutToShow.connect(self._fill_window_menu)

        m = mb.addMenu(tr("&Hilfe"))
        for a in (self.act_help, self.act_help_cli, self.act_keys):
            m.addAction(a)
        m.addSeparator()
        for a in (self.act_logfile, self.act_cli, self.act_reset_settings, self.act_about):
            m.addAction(a)

    # ----------------------------------------------------------------- Werkzeugleiste oben
    def _tb_button(self, tb, act, text_beside=True):
        tb.addAction(act)
        w = tb.widgetForAction(act)
        if w is not None and text_beside:
            w.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self._tb_text.append(w)
        return w

    def _fit_toolbar(self):
        """Ist das Fenster zu schmal fuer die Leiste oben, verlieren die Knoepfe Schritt fuer Schritt ihren Text
        (zuerst Elemente und Optionen, zuletzt Vergleichen; Name bleibt im Tooltip) - statt dass Knoepfe im
        Ueberlauf-Menue verschwinden."""
        tb = getattr(self, "main_toolbar", None)
        if tb is None or not self._tb_text:
            return
        base, extra = 24, {}
        for act in tb.actions():                  # ueber die Aktionen: im Ueberlauf versteckte Knoepfe zaehlen mit
            if not act.isVisible():
                continue
            if act.isSeparator():
                base += 10
                continue
            w = tb.widgetForAction(act)
            if w is None:
                continue
            if w in self._tb_text:                 # Breite ohne Text; der Text kommt bei Platz dazu
                base += w.iconSize().width() + 23 + tb.layout().spacing()
                extra[w] = w.fontMetrics().horizontalAdvance(w.text()) + 11
            else:
                base += max(0, w.sizeHint().width()) + tb.layout().spacing()
        # Reihenfolge, in der der Text wegfaellt: unwichtigstes zuerst
        order = sorted(self._tb_text, key=lambda w: getattr(w, "_text_rank", 0))
        keep = [w for w in order if w.isVisible() or w in extra]
        now = [w for w in keep if w.toolButtonStyle() != Qt.ToolButtonStyle.ToolButtonIconOnly]
        avail = tb.width()
        n = len(keep)
        while n > 0 and base + sum(extra.get(w, 0) for w in keep[len(keep) - n:]) > avail:
            n -= 1
        if n > len(now) and base + sum(extra.get(w, 0) for w in keep[len(keep) - n:]) > avail - 20:
            n = len(now)                         # erst mit etwas Luft wieder Text zeigen (kein Flackern)
        with_text = set(keep[len(keep) - n:])
        for w in self._tb_text:
            style = Qt.ToolButtonStyle.ToolButtonTextBesideIcon if w in with_text else \
                Qt.ToolButtonStyle.ToolButtonIconOnly
            if w.toolButtonStyle() != style:
                w.setToolButtonStyle(style)

    def _tb_proxy(self, src, ico):
        """Eigene Aktion fuer die Leiste oben: laesst sich je Modus ausblenden, ohne dass der Menuepunkt
        verschwindet (dort bleibt er ausgegraut sichtbar)."""
        a = QAction(icon(ico), src.text(), self)
        a.setIconText(src.iconText())
        a.setToolTip(src.toolTip())
        a.setEnabled(src.isEnabled())
        a.triggered.connect(src.trigger)
        src.changed.connect(lambda a=a, src=src: a.setEnabled(src.isEnabled()))
        self._icon_actions.append((a, ico))
        return a

    def _build_toolbar(self):
        tb = QToolBar(tr("Hauptleiste"))
        self.main_toolbar, self._tb_text = tb, []
        tb.setObjectName("main")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(tb)
        self.tb = tb
        open_menu = QMenu(self)
        for a in (self.act_open_a, self.act_open_b, self.act_open_view, self.act_open_clip, self.act_proj_open):
            open_menu.addAction(a)
        self.menu_recent2 = open_menu.addMenu(tr("Zuletzt verwendet"))
        self.menu_recent2.aboutToShow.connect(lambda: self._fill_recent_menu(self.menu_recent2))
        open_menu.addSeparator()
        open_menu.addAction(self.act_start)
        b = QToolButton()
        b.setText(tr("Öffnen"))
        b.setIcon(icon("open"))
        self._icon_buttons = [(b, "open")]
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        b.setMenu(open_menu)
        b.setToolTip(tr("Zeichnungen oder Projekt öffnen"))
        tb.addWidget(b)
        self._tb_text.append(b)
        b._text_rank = 2
        # Woran man den Modus erkennt: Schild mit Modus und Datei(en); Klick = was man damit tun kann
        # (neu vergleichen, tauschen, Datei wechseln). Ersetzt im Vergleich einen eigenen Vergleichen-Knopf.
        self.mode_chip = QToolButton()
        self.mode_chip.setObjectName("modechip")
        self.mode_chip.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.mode_chip.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        chip_menu = QMenu(self.mode_chip)
        chip_menu.aboutToShow.connect(lambda m=chip_menu: self._fill_chip_menu(m))
        self.mode_chip.setMenu(chip_menu)
        self.act_mode_chip = tb.addWidget(self.mode_chip)
        self.act_mode_chip.setVisible(False)
        self.act_compare_with_tb = self._tb_proxy(self.act_open_b, "compare")   # beim Ansehen: zweite Zeichnung
        self.act_compare_with_tb.setText(tr("Vergleichen mit …"))
        self.act_compare_with_tb.setIconText(tr("Vergleichen mit …"))
        self.act_compare_with_tb.setToolTip(tr("Zweite Zeichnung (neu) öffnen und mit dieser vergleichen"))
        self.btn_compare_with_tb = self._tb_button(tb, self.act_compare_with_tb)
        self.btn_compare_with_tb._text_rank = 4
        self.act_compare_with_tb.setVisible(False)
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
            btn.setToolTip(tr("{} (Taste {})").format(tip, k))
            btn.setCheckable(True)
            btn.setObjectName("seg")
            btn.clicked.connect(lambda _=False, m=key: self._seg_clicked(m))
            grp.addButton(btn)
            vl.addWidget(btn)
            self.seg_buttons[key] = btn
        self.seg_buttons["D"].setChecked(True)
        self.act_view_box = tb.addWidget(self.view_box)
        self.act_pause = QAction(tr("Pause"), self, checkable=True)
        self.act_pause.setToolTip(tr("Blinken anhalten/fortsetzen (auch Klick ins Bild; Leertaste wechselt von Hand)"))
        self.act_pause.toggled.connect(self._pause_blink)
        proxy = self._tb_proxy
        self.tb_zoom_actions = [tb.addSeparator()]
        tb.addAction(z := proxy(self.act_zoom_out, "zoom_out"))
        self.tb_zoom_actions.append(z)
        self.lbl_zoom = QToolButton()
        self.lbl_zoom.setObjectName("zoomlabel")
        self.lbl_zoom.setText("–")
        self.lbl_zoom.setToolTip(tr("Zoomstufe. Klick = Originalgröße (100 %)"))
        self.lbl_zoom.clicked.connect(self._zoom100)
        self.tb_zoom_actions.append(tb.addWidget(self.lbl_zoom))
        for src, ico in ((self.act_zoom_in, "zoom_in"), (self.act_fit, "fit")):   # Symbol genuegt (F, Doppelklick)
            tb.addAction(z := proxy(src, ico))
            self.tb_zoom_actions.append(z)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        save = QMenu(self)                                # gleiche Gruppen wie Datei -> Exportieren
        for a in (self.act_export_img, self.act_export_annpdf, self.act_export_all_ann, self.act_export_svg, None,
                  self.act_export_ocrpdf, self.act_vectorize, self.act_save_drawing, None, self.act_export_pdf,
                  self.act_export_all_report, self.act_export_csv, None, self.act_print):
            save.addSeparator() if a is None else save.addAction(a)   # Bild/PDF | Aenderungsbericht | Drucken
        save.addSeparator()
        for a in (self.act_proj_save, self.act_proj_save_as):
            save.addAction(a)
        b = QToolButton()
        b.setText(tr("Speichern"))
        b.setIcon(icon("save"))
        self._icon_buttons.append((b, "save"))
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        b.setMenu(save)
        b.setToolTip(tr("Ergebnis, Bericht oder Projekt speichern; drucken"))
        self.tb_zoom_actions.append(tb.addWidget(b))                  # wie Zoom: erst mit geoeffneter Zeichnung
        self._tb_text.append(b)
        b._text_rank = 3
        tb.addSeparator()
        self._tb_button(tb, self.act_left)._text_rank = 1      # Text faellt bei Platzmangel zuerst weg
        self._tb_button(tb, self.act_right)._text_rank = 0
        ext = tb.findChild(QToolButton, "qt_toolbar_ext_button")
        if ext is not None:
            ext.setIcon(QIcon())
            ext.setText("»")
            ext.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            ext.setMinimumSize(40, 30)
            ext.setToolTip(tr("Das Fenster ist zu schmal: weitere Schaltflächen hier öffnen"))

    # ----------------------------------------------------------------- Werkzeugpalette links am Bild
    def _build_palette(self):
        pal = PaletteFrame()                          # wird bei wenig Hoehe zu reinen Symbolen
        pal.setObjectName("palette")
        pal.setFixedWidth(84)
        lay = QVBoxLayout(pal)
        lay.setContentsMargins(5, 8, 5, 8)
        lay.setSpacing(2)
        self.group_buttons = {}
        self._dbl_filter = DoubleClickFilter(self._tool_double_clicked, self)
        for key, *_ in TOOLS:
            group = next((g for g in PALETTE_GROUPS if key in g), None)
            if group and key != group[0]:
                continue
            b = QToolButton()
            if group:                                 # mehrere Werkzeuge in einem Knopf, Auswahl ueber das Dreieck
                menu = QMenu(b)
                for k2 in group:
                    menu.addAction(self.tool_actions[k2])
                b.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
                b.setDefaultAction(self.tool_actions[key])
                b.setMenu(menu)
                for k2 in group:
                    self.group_buttons[k2] = b
                menu.triggered.connect(lambda act, b=b, m=menu: (b.setDefaultAction(act), b.setMenu(m)))
            else:
                b.setDefaultAction(self.tool_actions[key])
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(22, 22))
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.installEventFilter(self._dbl_filter)
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

    def _tool_double_clicked(self, button):
        """Doppelklick auf ein Zeichenwerkzeug: Werkzeug behalten an (mehrere hintereinander zeichnen).
        Doppelklick auf Auswahl, Bereich, Zoom oder Messen: Werkzeug behalten wieder aus."""
        act = button.defaultAction()
        key = next((k for k, a in self.tool_actions.items() if a is act), None)
        if key is None or not act.isEnabled():
            return
        self._set_tool(key)
        keep = key not in NAV_TOOLS
        self.chk_keep_tool.setChecked(keep)
        self.statusBar().showMessage(tr("Werkzeug behalten: an – „{}“ bleibt nach dem Zeichnen aktiv (Esc beendet).")
                                     .format(act.text()) if keep else tr("Werkzeug behalten: aus"), 6000)

    # ----------------------------------------------------------------- Optionsleiste (je Werkzeug)
    def _build_options(self):
        bar = QFrame()
        bar.setObjectName("optbar")
        lay = FlowLayout(bar, 10)                    # bricht bei schmalem Bild um, statt abzuschneiden
        lay.setContentsMargins(12, 4, 12, 4)
        self.opt_measure = QWidget()
        l = FlowLayout(self.opt_measure)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(QLabel(tr("Messart")))
        self.cb_mkind = QComboBox()
        for key, txt in rep.MEASURE_KINDS.items():
            self.cb_mkind.addItem(txt, key)
        self.cb_mkind.setToolTip(tr("Länge = 2 Punkte, Winkel und Radius = 3 Punkte, Linienzug und Fläche = "
                                 "beliebig viele (Ende mit Doppelklick, Enter oder Rechtsklick)"))
        self.cb_mkind.currentIndexChanged.connect(self._mkind_changed)
        l.addWidget(self.cb_mkind)
        self.chk_snap = QCheckBox(tr("An Linien einrasten"))
        self.chk_snap.setChecked(True)
        self.chk_snap.setToolTip(tr("Umschalt gedrückt halten = vorübergehend frei messen"))
        self.chk_snap.toggled.connect(self._toggle_snap)
        l.addWidget(self.chk_snap)
        self.cb_unit = QComboBox()                    # Anzeige der Messwerte
        for u in rep.UNITS:
            self.cb_unit.addItem(u, u)
        self.cb_unit.setToolTip(tr("Einheit der Messwerte"))
        self.sp_dec = QSpinBox()
        self.sp_dec.setRange(0, 4)
        self.sp_dec.setToolTip(tr("Nachkommastellen der Messwerte"))
        self.sp_dec.setPrefix(tr("Stellen: "))
        rep.MEASURE_FMT.update(unit=self.settings.value("meas_unit", "mm"), dec=int(self.settings.value("meas_dec", 2)))
        self.cb_unit.setCurrentIndex(max(0, self.cb_unit.findData(rep.MEASURE_FMT["unit"])))
        self.sp_dec.setValue(rep.MEASURE_FMT["dec"])
        self.cb_unit.currentIndexChanged.connect(lambda _: self._measure_fmt())
        self.sp_dec.valueChanged.connect(lambda _: self._measure_fmt())
        l.addWidget(self.cb_unit)
        l.addWidget(self.sp_dec)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        l.addWidget(sep)
        self.lbl_meas_scale = QToolButton()
        self.lbl_meas_scale.setText(tr("Ma\u00dfstab 1 : 1"))
        self.lbl_meas_scale.clicked.connect(self._scale_dialog)
        l.addWidget(self.lbl_meas_scale)
        b = QPushButton(tr("Kalibrieren \u2026"))
        b.setToolTip(tr("Eine Strecke mit bekannter L\u00e4nge messen und ihre wahre L\u00e4nge eingeben; "
                     "danach stimmen alle Ma\u00dfe (auch bei falscher Aufl\u00f6sung oder Ma\u00dfstab)."))
        b.clicked.connect(lambda: self._calibrate())
        l.addWidget(b)
        b = QPushButton(tr("Aus Schriftfeld"))
        b.setToolTip(tr("Ma\u00dfstab aus dem Schriftfeld lesen (PDF-Text oder Texterkennung)"))
        b.clicked.connect(self.read_title_block)
        l.addWidget(b)
        lay.addWidget(self.opt_measure)
        self.opt_ann = QWidget()
        l = FlowLayout(self.opt_ann)
        l.setContentsMargins(0, 0, 0, 0)
        self.btn_color = QPushButton(tr("Farbe"))
        self.btn_color.clicked.connect(self._pick_color)
        l.addWidget(self.btn_color)
        self.chk_redact_paper = QCheckBox(tr("Mit Papierfarbe (weiß ausmalen)"))
        self.chk_redact_paper.setToolTip(tr("Statt schwarz in der Farbe des Papiers ringsum füllen – der Inhalt "
                                         "verschwindet unauffällig"))
        self.chk_redact_paper.toggled.connect(self._redact_fill_changed)
        l.addWidget(self.chk_redact_paper)
        l.addWidget(QLabel(tr("Größe")))
        self.s_asize = QDoubleSpinBox()
        self.s_asize.setRange(0.5, 12)
        self.s_asize.setSingleStep(0.5)
        self.s_asize.setDecimals(1)
        self.s_asize.setValue(2.0)
        self.s_asize.setToolTip(tr("Größe von Text, Nummer, Stempel und Linienstärke"))
        self.s_asize.valueChanged.connect(self._ann_size)
        self.s_asize.set_silent = lambda v: (self.s_asize.blockSignals(True), self.s_asize.setValue(v),
                                             self.s_asize.blockSignals(False))
        l.addWidget(self.s_asize)
        self.chk_keep_tool = QCheckBox(tr("Werkzeug behalten"))
        self.chk_keep_tool.setToolTip(tr("Nach dem Zeichnen bleibt das Werkzeug aktiv – z. B. mehrere Pfeile "
                                      "nacheinander. Aus: danach zurück zur Auswahl, um gleich zu verschieben. "
                                      "Esc beendet das Werkzeug."))
        self.chk_keep_tool.setChecked(self.settings.value("keep_tool", "false") == "true")
        self.chk_keep_tool.toggled.connect(lambda on: self.settings.setValue("keep_tool", "true" if on else "false"))
        l.addWidget(self.chk_keep_tool)
        self.btn_presets = QToolButton()                # Werkzeugkasten: gespeicherte Werkzeuge
        self.btn_presets.setText(tr("Vorlagen"))
        self.btn_presets.setToolTip(tr("Werkzeugkasten: Werkzeug mit Farbe und Größe als Vorlage speichern und "
                                    "mit einem Klick wieder wählen"))
        self.btn_presets.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        pm = QMenu(self.btn_presets)
        pm.aboutToShow.connect(lambda m=pm: self._fill_toolchest(m))
        self.btn_presets.setMenu(pm)
        l.addWidget(self.btn_presets)
        self.lbl_stamp = QLabel(tr("Nächste Nummer"))
        self.sp_stamp = QSpinBox()
        self.sp_stamp.setRange(1, 9999)
        self.sp_stamp.valueChanged.connect(lambda v: setattr(self, "next_nr", v))
        l.addWidget(self.lbl_stamp)
        l.addWidget(self.sp_stamp)
        lay.addWidget(self.opt_ann)
        self.opt_view = QWidget()                     # Optionen der Ansicht (Blinken, Hervorheben, Schieber)
        l = FlowLayout(self.opt_view)
        l.setContentsMargins(0, 0, 0, 0)
        self.lbl_blink = QLabel(tr("Blinken"))
        self.cb_blink = QComboBox()
        for txt, ms in ((tr("langsam"), 1200), (tr("normal"), 550), (tr("schnell"), 250)):
            self.cb_blink.addItem(txt, ms)
        self.cb_blink.setCurrentIndex(1)
        self.cb_blink.setToolTip(tr("Blinkgeschwindigkeit"))
        self.cb_blink.currentIndexChanged.connect(lambda _: self.blink.setInterval(self.cb_blink.currentData()))
        self.btn_pause = QToolButton()
        self.btn_pause.setDefaultAction(self.act_pause)
        self.lbl_blink_hint = QLabel(tr("Leertaste = von Hand wechseln, Klick ins Bild = Pause"))
        self.lbl_blink_hint.setObjectName("hint")
        self.chk_highlight = QCheckBox(tr("Änderungen hervorheben"))
        self.chk_highlight.setToolTip(tr("In der alten Zeichnung entfernte Stellen rot, in der neuen neue Stellen blau "
                                      "(Tasten 8 / 7)"))
        self.chk_highlight.toggled.connect(self._highlight_toggled)
        self.lbl_slider_hint = QLabel(tr("Schieber: die blaue Trennlinie mit der Maus ziehen (links alt, rechts neu)"))
        self.lbl_slider_hint.setObjectName("hint")
        for w in (self.lbl_blink, self.cb_blink, self.btn_pause, self.lbl_blink_hint, self.chk_highlight,
                  self.lbl_slider_hint):
            l.addWidget(w)
        lay.addWidget(self.opt_view)
        self.opt_loupe = QWidget()
        l = FlowLayout(self.opt_loupe)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(QLabel(tr("Lupe")))
        self.cb_loupe = QComboBox()
        for z in (2, 3, 5, 8):
            self.cb_loupe.addItem(f"{z}×", float(z))
        self.cb_loupe.setCurrentIndex(1)
        self.cb_loupe.currentIndexChanged.connect(
            lambda _: setattr(self.canvas, "loupe_zoom", self.cb_loupe.currentData()))
        l.addWidget(self.cb_loupe)
        lay.addWidget(self.opt_loupe)
        self.opt_area = QWidget()                     # Bereichsauswahl
        l = FlowLayout(self.opt_area)
        l.setContentsMargins(0, 0, 0, 0)
        self.lbl_area = QLabel("")
        self.lbl_area.setObjectName("hint")
        l.addWidget(self.lbl_area)
        self.area_buttons = {}
        more = QMenu(self)
        for key, text, fn, tip, main in (
                ("copy", tr("Kopieren"), lambda: self.area_copy(), tr("Wie angezeigt kopieren (Strg+C)"), True),
                ("copyopt", tr("Nur Linien/Geometrie kopieren …"), lambda: self.area_copy_options(),
                 tr("Alles, nur Linien oder nur Geometrie kopieren (Strg+Umschalt+C)"), False),
                ("cut", tr("Ausschneiden"), lambda: self.area_cut(), tr("Strg+X"), False),
                ("delete", tr("Löschen"), lambda: self.area_delete(),
                 tr("Markierungen und Änderungen in der Auswahl löschen (Entf)"), True),
                ("clear", tr("Zeichnung im Bereich leeren"), lambda: self.area_clear(),
                 tr("Zeichnungsinhalt der Auswahl entfernen (Papierfarbe)"), False),
                ("crop", tr("Zuschneiden"), lambda: self.set_crop_frame(),
                 tr("Zuschnitt-Rahmen setzen: Speichern, Drucken und Kopieren zeigen nur diesen Teil (ragt er über das "
                    "Blatt, mit Rand). Nichts wird gelöscht; der Rahmen lässt sich an den Anfassern anpassen."), True),
                ("export", tr("Exportieren …"), lambda: self.area_export(),
                 tr("Auswahl als Bild, PDF oder SVG speichern"), True)):
            if main:
                b = QPushButton(text)
                b.setToolTip(tip)
                b.clicked.connect(fn)
                b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                l.addWidget(b)
            else:                                     # seltener gebraucht: im Menue "Mehr"
                b = more.addAction(text, fn)
                b.setToolTip(tip)
            self.area_buttons[key] = b
        more.setToolTipsVisible(True)
        self.btn_area_more = QToolButton()
        self.btn_area_more.setText(tr("Mehr"))
        self.btn_area_more.setMenu(more)
        self.btn_area_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        l.addWidget(self.btn_area_more)
        lay.addWidget(self.opt_area)
        self.opt_float = QWidget()                    # Ausschnitt verschieben
        l = FlowLayout(self.opt_float)
        l.setContentsMargins(0, 0, 0, 0)
        self.chk_float_lines = QCheckBox(tr("Nur Linien (ohne Papier)"))
        self.chk_float_lines.setToolTip(tr("Verschieben: nur die Linien wandern, Papier und Hintergrund am Ziel bleiben; "
                                        "die frei gewordene Stelle bekommt die Papierfarbe. Kopieren und Exportieren: "
                                        "das Papier wird durchsichtig, nur Linien und Markierungen bleiben."))
        self.chk_float_lines.setChecked(True)
        self.chk_float_lines.toggled.connect(lambda _: (self._float_images(), self.canvas.update()))
        l.addWidget(self.chk_float_lines)
        self.btn_float_ok = QPushButton(tr("Übernehmen"))
        self.btn_float_ok.setObjectName("primary")
        self.btn_float_ok.clicked.connect(lambda: self._float_done(True))
        self.btn_float_cancel = QPushButton(tr("Abbrechen"))
        self.btn_float_cancel.clicked.connect(lambda: self._float_done(False))
        l.addWidget(self.btn_float_ok)
        l.addWidget(self.btn_float_cancel)
        lay.addWidget(self.opt_float)
        for w in (self.opt_measure, self.opt_ann, self.opt_loupe, self.opt_view, self.opt_float, self.opt_area):
            w.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.lbl_tool_hint = QLabel("")
        self.lbl_tool_hint.setObjectName("hint")
        self.lbl_tool_hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(self.lbl_tool_hint)
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
        self.opt_ann.setVisible(t in ("text", "number", "approval", "cloud", "highlight", "pen", "arrow", "redact",
                                      "pixelate") + SHAPES
                                or (t == "hand" and self.canvas.ann_selected is not None))
        sel = self.canvas.anns[self.canvas.ann_selected] if (
            self.canvas.ann_selected is not None and self.canvas.ann_selected < len(self.canvas.anns)) else None
        sel_t = sel["type"] if sel else None
        redact_ctx = t in ("redact", "pixelate") or (t == "hand" and sel_t in ("redact", "pixelate"))
        self.btn_color.setVisible(not redact_ctx)             # Schwaerzen ist schwarz, Verpixeln hat keine Farbe
        self.chk_redact_paper.setVisible(t == "redact" or (t == "hand" and sel_t == "redact"))
        if sel_t == "redact":
            self.chk_redact_paper.blockSignals(True)
            self.chk_redact_paper.setChecked(sel.get("fill") == "paper")
            self.chk_redact_paper.blockSignals(False)
        self.lbl_stamp.setVisible(t == "number")
        self.sp_stamp.setVisible(t == "number")
        self.opt_loupe.setVisible(self.act_loupe.isChecked())
        has_sel = bool(self.canvas.sel_rects)
        self.opt_area.setVisible(t == "area")
        self.lbl_area.setVisible(has_sel)
        self.btn_area_more.setVisible(has_sel)
        for k, b in self.area_buttons.items():
            b.setVisible(has_sel and (k != "clear" or self.view_only))
        self.opt_float.setVisible(t in ("cutmove", "area") or self.canvas.float is not None)
        for b in (self.btn_float_ok, self.btn_float_cancel):
            b.setEnabled(self.canvas.float is not None)
            b.setVisible(t != "area")
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
        self.start.backRequested.connect(self.show_work)
        self.stack.addWidget(self.start)
        work = QWidget()
        v = QVBoxLayout(work)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._build_palette())
        # Such-, Options- und Hinweisleiste liegen ueber dem Bild: Einblenden verschiebt die Zeichnung nicht
        self.canvas_host = OverlayHost(self.canvas, (self._build_search_bar(), self._build_options()))
        h.addWidget(self.canvas_host, 1)
        v.addLayout(h, 1)
        self.stack.addWidget(work)
        self.work = work
        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        self.center_layout = cv
        self.banner = Banner()
        cv.addWidget(self.banner)
        cv.addWidget(self.stack, 1)
        self.stack.currentChanged.connect(lambda _: self._place_banner())
        return center

    def _place_banner(self):
        """Hinweisleiste: auf der Startseite oben im Layout, beim Bild als Ueberlagerung (Bild bleibt stehen)."""
        if self.stack.currentWidget() is self.work:
            if self.banner.parent() is not self.canvas_host.column:
                self.canvas_host.add_bar(self.banner, 0)
        elif self.banner.parent() is self.canvas_host.column:
            was = not self.banner.isHidden()
            self.center_layout.insertWidget(0, self.banner)
            self.banner.setVisible(was)

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
        for w in (self.s_hatch, self.s_move, self.s_obj, self.s_rot, self.s_cell, self.s_maxs):
            adv.body.addWidget(w)
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
        self.chk_live.setChecked(False)
        self.chk_live.setToolTip(tr("Nach jeder Änderung eines Reglers sofort neu vergleichen"))
        self.expert_widgets.append(self.chk_live)
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
        self.btn_regs = QPushButton(tr("Änderungen suchen und nummerieren"))
        self.btn_regs.setObjectName("primary")
        self.btn_regs.clicked.connect(self.find_regs)
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
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr("Status"), tr("Nr"), tr("Typ"), tr("Pos. mm"), tr("Text / Kommentar")])
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

    def _fill_window_menu(self):
        import drawing_viewer
        m = self.menu_windows
        m.clear()
        m.addAction(self.act_new_window)
        m.addSeparator()
        for w in drawing_viewer.WINDOWS + ([] if self in drawing_viewer.WINDOWS else [self]):
            title = w.windowTitle().replace(" \u2013 " + APP, "") or APP
            a = m.addAction(title, lambda w=w: (w.showNormal() if w.isMinimized() else None, w.raise_(),
                                                 w.activateWindow()))
            a.setCheckable(True)
            a.setChecked(w is self)

    def _measure_fmt(self):
        rep.MEASURE_FMT.update(unit=self.cb_unit.currentData(), dec=self.sp_dec.value())
        self.settings.setValue("meas_unit", rep.MEASURE_FMT["unit"])
        self.settings.setValue("meas_dec", rep.MEASURE_FMT["dec"])
        self._update_units()                       # Liste und Bild neu beschriften

    def _redact_fill_changed(self, on):
        c = self.canvas
        changed = False
        for k in c.selected_anns():
            if c.anns[k]["type"] == "redact":
                c.anns[k]["fill"] = "paper" if on else "black"
                changed = True
        if changed:
            self._commit()
        c.update()

    def _toggle_legend(self, on):
        self.settings.setValue("legend", "true" if on else "false")
        self.canvas.show_legend = on and not self.view_only
        self.canvas.update()

    def _toggle_layers_tab(self, on):
        self.settings.setValue("layers_tab", "true" if on else "false")
        self.tabs.setTabVisible(self.tabs.indexOf(self.tab_layers), on)
        if on:
            self.act_right.setChecked(True)
            self.right.setVisible(True)
            self.tabs.setCurrentWidget(self.tab_layers)

    # ----------------------------------------------------------------- Statusleiste
    def _build_statusbar(self):
        sb = self.statusBar()
        self.lbl_status = QLabel(tr("Bereit"))
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setFixedWidth(180)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.btn_cancel = QPushButton(tr("Abbrechen"))
        self.btn_cancel.setToolTip(tr("Laufende Berechnung abbrechen"))
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
        n, ok = QInputDialog.getDouble(self, tr("Ma\u00dfstab"), tr("Zeichnungsma\u00dfstab 1 : n  (f\u00fcr 2:1 bitte 0,5 "
                                       "eingeben):"), self.scale_n(), 0.01, 1000, 3)
        if ok:
            self.sp_scale.setValue(n)

    def set_ui_scale(self, v):
        if abs(v - ui_scale_setting(self.settings)) < 0.01:
            return
        self.settings.setValue("ui_scale", v)
        self.banner.show_msg(tr("Die Oberfläche wird nach einem Neustart auf {:.0f} % gestellt.").format(v * 100), "info",
                             action=(tr("Jetzt neu starten"), self.restart_app))

    def set_language(self, lang):
        if lang == i18n.setting():
            return
        self.settings.setValue("language", lang)
        target = lang if lang != "auto" else i18n.system_language()
        msg = ("Die Sprache wird nach einem Neustart umgestellt." if target == "de" else
               "The language will change after a restart.")
        self.banner.show_msg(msg, "info", action=("Jetzt neu starten" if target == "de" else "Restart now",
                                                  self.restart_app))

    def reset_all_settings(self):
        """Alle gespeicherten Einstellungen auf Standard (nach Rueckfrage); Darstellung/Sprache/Groesse per Neustart."""
        box = QMessageBox(self)
        box.setWindowTitle(APP)
        box.setText(tr("Alle Einstellungen auf Standard zurücksetzen?"))
        box.setInformativeText(tr("Darstellung, Sprache, Größe der Oberfläche, Werte des Vergleichs, Werkzeugoptionen "
                                  "und Fensterlage. Zeichnungen, Projekte und Markierungen bleiben unverändert."))
        keep = QCheckBox(tr("Liste „Zuletzt verwendet“ behalten"))
        keep.setChecked(True)
        box.setCheckBox(keep)
        box.setStandardButtons(QMessageBox.StandardButton.Reset | QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Reset:
            return
        st = self.settings
        st.setFallbacksEnabled(False)                  # nur die eigenen Schluessel (macOS: nie die globalen)
        for k in st.allKeys():
            if not (k == "recent" and keep.isChecked()):
                st.remove(k)
        st.setFallbacksEnabled(True)
        st.sync()
        self._reset_params()
        for chk, on in ((self.chk_keep_tool, False), (self.chk_float_lines, True), (self.chk_live, False)):
            chk.setChecked(on)
        for act, on in ((self.act_legend, True), (self.act_clouds, False), (self.act_expert, False),
                        (self.act_layers, False)):
            if act.isChecked() != on:
                act.trigger()
        self.set_theme("auto")
        self.theme_actions["auto"].setChecked(True)
        self.banner.show_msg(tr("Einstellungen zurückgesetzt. Sprache und Größe der Oberfläche gelten nach einem "
                                "Neustart."), "info", action=(tr("Jetzt neu starten"), self.restart_app), timeout=20)

    def restart_app(self):
        """Programm neu starten (z. B. fuer die Groesse der Oberflaeche); Ungespeichertes wird vorher abgefragt."""
        if not self._maybe_save():
            return
        args = [a for a in sys.argv[1:] if a.startswith("-")]
        if self.project_path:
            args.append(self.project_path)
        elif self.path_a:
            args += [p for p in (self.path_a, self.path_b) if p]
        prog = sys.executable
        if not FROZEN:
            args = [os.path.abspath(sys.argv[0])] + args
        from PySide6.QtCore import QProcess
        QProcess.startDetached(prog, args)
        self._dirty = False
        QApplication.instance().closeAllWindows()

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
        self._apply_mode_panels()

    def _apply_mode_panels(self):
        """Linke Seitenleiste je Modus: beim Ansehen nur Datei, Seiten und Massstab - kein Vergleichs-Zubehoer."""
        single = getattr(self, "view_only", False)
        expert = self.act_expert.isChecked()
        for w in getattr(self, "compare_widgets", ()):
            w.setVisible(not single and (w not in self.expert_widgets or expert))
        head_a, tag_a, _l = self.file_rows["A"]
        tag_a.setText(tr("Zeichnung") if single else tr("A  –  alt"))
        for w in self.file_rows["B"]:
            w.setVisible(not single)
        self.btn_swap.setVisible(not single)
        self.btn_add_b.setVisible(single)
        self.btn_run.setVisible(not single)
        self.chk_live.setVisible(not single and expert)

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
        for a in (self.act_search, self.act_search_next, self.act_search_prev,
                  self.act_fit, self.act_100, self.act_zoom_in, self.act_zoom_out, self.act_zoom_box, self.act_rotate,
                  self.act_export_img, self.act_export_annpdf, self.act_export_pdf, self.act_export_csv,
                  self.act_print, self.act_copy, self.act_copy_sel, self.act_find, self.act_proj_save,
                  self.act_export_svg, self.act_export_ocrpdf, self.act_vectorize,
                  self.act_proj_save_as):
            a.setEnabled(has)
        for a in (self.act_delete, self.act_ann_clear, self.act_cut, self.act_ann_save, self.act_ann_load,
                  self.act_export_measures,
                  self.act_import_comments, self.act_export_xfdf, self.act_title):   # brauchen ein Dokument
            a.setEnabled(has)
        for a in self.sheet_actions:                                  # nur beim Ansehen einer einzelnen Zeichnung
            a.setEnabled(has and self.view_only)
        for a in (self.act_find, self.act_export_pdf, self.act_export_csv, self.act_auto, self.act_index,
                  self.act_match, self.act_align, self.act_zone, self.act_crop, self.act_crop_off, self.act_clouds):
            a.setEnabled(has and not self.view_only)                  # nur im Vergleich
        self.act_align_reset.setEnabled(has and not self.view_only and getattr(self, "manual_tf", None) is not None)
        multi = has and max(getattr(self, "n_pages_a", 1), getattr(self, "n_pages_b", 1)) > 1
        self.act_export_all_ann.setVisible(multi)                    # nur bei mehrseitigen Dateien
        self.act_export_all_report.setVisible(multi and not self.view_only)
        self.act_pages.setEnabled(multi and not self.view_only)
        self.act_legend.setEnabled(has and not self.view_only and self.canvas.mode in ("D", "O", "N", "R"))
        for a in (self.tb_zoom_actions if hasattr(self, "tb_zoom_actions") else ()):
            a.setVisible(has)                                          # Startseite: keine toten Knoepfe oben
        if hasattr(self, "act_view_box"):
            self.act_view_box.setVisible(has and not self.view_only)
            self.sep_views.setVisible(has and not self.view_only)
        self._update_review_enabled()
        self._update_mode_chip()
        for a in self.mode_actions.values():
            a.setEnabled(has and not self.view_only)
        for b in self.seg_buttons.values():
            b.setEnabled(has)
        for a in self.tool_actions.values():
            a.setEnabled(has)
        self.act_compare.setEnabled(bool(self.path_a and self.path_b) and not self.running)
        self.lbl_zoom.setEnabled(has)

    def _update_mode_chip(self):
        """Schild oben: 'Ansehen: datei' oder 'Vergleich: alt → neu' - man sieht sofort, in welchem Modus man ist."""
        chip = getattr(self, "mode_chip", None)
        if chip is None:
            return
        has = self.payload is not None
        self.act_mode_chip.setVisible(has)
        if not has:
            return
        fm = chip.fontMetrics()
        name = lambda p, w: fm.elidedText(os.path.basename(p or ""), Qt.TextElideMode.ElideMiddle, w)  # noqa: E731
        dirty = getattr(self, "_params_dirty", False) and not self.view_only
        if self.view_only:                      # Modus bleibt immer lesbar, nur die Dateinamen werden gekuerzt
            text = tr("Ansehen: {}").format(name(self.path_a or self.path_b, 220))
            tip = tr("Einzelansicht: eine Zeichnung ansehen, messen und markieren. Zum Vergleichen eine zweite "
                     "Zeichnung öffnen („Vergleichen mit …“).")
        else:
            text = tr("Vergleich: {} → {}").format(name(self.path_a, 120), name(self.path_b, 120))
            tip = tr("Vergleich: A (alt) und B (neu) übereinander; Unterschiede sind farbig. Klick: neu "
                     "vergleichen, A und B tauschen oder eine Datei wechseln.")
            if dirty:
                text = "● " + text
                tip = tr("Einstellungen geändert – Klick → „Neu vergleichen“ (Strg+Enter).") + "\n" + tip
        if self.lines_active():                 # Linienfilter blendet Linien aus: sichtbar machen
            text += "  · " + tr("Linienfilter")
            tip += "\n" + tr("Linienfilter aktiv: nur ein Teil der Linien wird gezeigt und verglichen.")
        chip.setProperty("single", bool(self.view_only))
        chip.setProperty("dirty", bool(dirty))
        chip.style().unpolish(chip)
        chip.style().polish(chip)
        chip.setToolTip(tip + "\n\n" + "\n".join(p for p in (self.path_a, self.path_b) if p))
        chip.setText(text + "  ▾")

    def _fill_chip_menu(self, m):
        m.clear()
        if self.view_only:
            m.addAction(tr("Mit anderer Zeichnung vergleichen …"), lambda: self.open_file("B"))
            m.addAction(tr("Andere Zeichnung ansehen …"), self.open_view_only)
        else:
            m.addAction(self.act_compare)
            m.addAction(tr("A und B tauschen"), self.swap_ab)
            m.addSeparator()
            m.addAction(tr("Andere alte Zeichnung (A) …"), lambda: self.open_file("A"))
            m.addAction(tr("Andere neue Zeichnung (B) …"), lambda: self.open_file("B"))
        m.addSeparator()
        m.addAction(self.act_close)

    def _update_review_enabled(self):
        """Pruefen (naechste, geprueft, abgelehnt, ...) und Text/Masse lesen erst, wenn es Aenderungen gibt."""
        pl = self.payload
        regs = bool(pl and not self.view_only and pl.get("regs"))
        for a in (self.act_next, self.act_prev, self.act_ok, self.act_reject, self.act_comment, self.act_rej_zones,
                  self.act_text, self.act_dims, self.act_renumber):
            a.setEnabled(regs)

    def _set_view_only(self, on):
        """Nur eine Datei: Vergleichsfunktionen ausblenden (reines Ansehen)."""
        self.view_only = on
        self.act_compare_with_tb.setVisible(on)
        for key, *_ in VIEWS + MORE_VIEWS:                       # Vergleichsansichten auch im Menue weg
            self.mode_actions[key].setVisible(not on)
        self._apply_mode_panels()
        self._update_mode_chip()
        self._update_enabled()
        QTimer.singleShot(0, self._fit_toolbar)
        self.canvas.show_legend = not on and self.act_legend.isChecked()
        self.act_legend.setEnabled(not on and self.canvas.mode in ("D", "O", "N", "R"))
        self.tabs.setTabVisible(self.tabs.indexOf(self.tab_regs), not on)
        if on:
            self.act_left.setChecked(False)
            self.tabs.setCurrentWidget(self.tab_anns)
