#!/usr/bin/env python3
"""ZGmax - Zeichnungen ansehen, vergleichen und pruefen.

Start:  App "ZGmax" oder Doppelklick auf "Start ZGmax" im Hauptordner,
        oder  python drawing_viewer.py [ALT [NEU]]   (eine Datei = nur ansehen)
Anleitung: Menue Hilfe > Anleitung (F1).
"""
import i18n
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_canvas import Canvas, build_color_pyramids, build_pyramids
import diffedit as de
from ui_dialogs import BatchDialog, RevisionDialog, VectorFilterDialog
from ui_widgets import Job, SafeStream, WheelGuard
from ui_regions import RegionsMixin
from ui_annotations import AnnotationsMixin
from ui_project import ProjectMixin
from ui_export import ExportMixin
from ui_layout import LayoutMixin
from ui_features import FeaturesMixin
from ui_search import SearchMixin
from ui_edit import AreaMixin, ClipboardMixin, EditMixin, OcrPdfMixin, SheetEditMixin, VectorizeMixin

VERSION = "2.0"
WINDOWS = []                     # alle offenen Hauptfenster (Datei > Neues Fenster)


def hide_filtered(img, ink_all, ink_kept):
    """Linien, die der Linienfilter weglaesst, auch im Original (Farbe/Graustufen) als Papier zeigen."""
    if img is None or ink_kept is ink_all or img.shape[:2] != ink_all.shape[:2]:
        return img
    gone = (ink_all > 0) & (ink_kept == 0)
    if not gone.any():
        return img
    gone = cv2.dilate(gone.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0   # Kantenglaettung mitnehmen
    out = img.copy()
    out[gone] = 255
    return out


class MainWindow(LayoutMixin, FeaturesMixin, SearchMixin, EditMixin, ClipboardMixin, AreaMixin, SheetEditMixin, OcrPdfMixin,
                 VectorizeMixin, RegionsMixin, AnnotationsMixin, ProjectMixin, ExportMixin, QMainWindow):
    def __init__(self, path_a=None, path_b=None):
        super().__init__()
        self.setWindowTitle(APP)
        self.resize(1440, 900)
        self.setMinimumSize(900, 600)
        self.setAcceptDrops(True)
        self.settings = app_settings()
        self.theme_mode = theme_setting(self.settings)
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):          # Systemwechsel hell/dunkel bei "Automatisch"
            hints.colorSchemeChanged.connect(self._system_theme_changed)
        self.path_a = self.path_b = None
        self.n_pages_a = self.n_pages_b = 1
        self.running = False
        self.pending = False
        self.jobs = []
        self.current_job = None
        self.cache = {}
        self._hinted = set()                        # Dateien, zu denen der Scan-Hinweis schon kam
        self.payload = None
        self.view_only = False
        self.page_summary = {}
        self.crop_b = None                # selbst zugeordneter Bereich in B (x, y, b, h) oder None
        self.manual_tf = None             # manuelles Ausrichten: 2x3-Matrix (ausgerichtetes B -> A) oder None
        # Anmerkungen und Zonen werden global (Koordinaten des ganzen Blatts A) verstanden. self.anns
        # und die Canvas-Zonen sind die lokalen Ansichten relativ zu self.origin (Ursprung des gerade
        # angezeigten Ergebnisses, = Ausschnitt-Ecke). self.zones ist immer global.
        self.zones = []
        self.anns = []
        self.origin = (0, 0)
        self.project_path = None
        self.undo_stack, self.redo_stack, self._cur_state = [], [], None
        self.crop = None                  # (x, y, b, h) in Koordinaten des ganzen Blatts A
        self._crop_seen = None
        self.index_info = None
        self.next_nr = 1
        self._prev_tool = "hand"
        self.restore_regs = None          # aus Projekt: Aenderungsliste nach dem Vergleich wiederherstellen
        self.canvas = Canvas()
        self.canvas.anns = self.anns
        cv = self.canvas
        cv.cursor.connect(self._on_cursor)
        cv.zoneDrawn.connect(self._add_zone)
        cv.cropDrawn.connect(self._crop_drawn)
        cv.regionClicked.connect(self._select_region_nr)
        cv.annCreated.connect(self._ann_created)
        cv.placeRequested.connect(self._place)
        cv.textBoxDrawn.connect(lambda x, y, w: self._place("text", x, y, w))
        cv.annSelected.connect(self._ann_selected)
        cv.annMultiSelected.connect(self._ann_multi_selected)
        cv.annChanged.connect(self._ann_changed)
        cv.annEdit.connect(self._ann_edit)
        cv.annContext.connect(self._ann_context)
        cv.contextRequested.connect(self._canvas_menu)
        cv.escapePressed.connect(lambda: self._set_tool("hand"))
        cv.regionDrawn.connect(self._region_drawn)
        cv.blinkClicked.connect(lambda: self.act_pause.toggle())
        cv.viewChanged.connect(self._on_view_changed)
        cv.zoomBoxDone.connect(self._zoom_box_done)
        cv.filesDropped.connect(self._files_dropped)
        cv.alignPoint.connect(self._align_point)
        cv.selCopy.connect(self._sel_copy)
        cv.zoneEdited.connect(self._zone_edited)
        cv.frameEdited.connect(self._frame_edited)
        cv.zoneSelected.connect(self._zone_selected)
        cv.selMove.connect(self._sel_move)
        cv.straightenLine.connect(self._straighten_line)
        cv.floatDone.connect(self._float_done)
        cv.areaChanged.connect(self._area_changed)
        cv.areaMoveStarted.connect(self._area_move_started)
        cv.areaMoved.connect(self._area_moved)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self.start_compute)
        self.page_timer = QTimer(self)
        self.page_timer.setSingleShot(True)
        self.page_timer.timeout.connect(self.start_compute)
        self.blink = QTimer(self)
        self.blink.setInterval(550)
        self.blink.timeout.connect(self._blink)
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(60_000)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()
        self.wheel_guard = WheelGuard(self)
        QApplication.instance().installEventFilter(self.wheel_guard)

        self._icon_buttons = []
        self._build_actions()
        self._build_menubar()
        self._build_toolbar()
        self._build_left()
        self._build_right()
        split = QSplitter()
        split.addWidget(self.left)
        split.addWidget(self._build_center())
        split.addWidget(self.right)
        split.setSizes([320, 900, 380])
        split.setStretchFactor(1, 1)
        split.setChildrenCollapsible(False)
        self.split = split
        self.setCentralWidget(split)
        self._build_statusbar()
        self.left.hide()
        self.right.hide()
        self.act_expert.setChecked(self.settings.value("expert", "false") == "true")
        self._set_expert(self.act_expert.isChecked())
        self.canvas.show_overview = self.act_overview.isChecked()
        self.canvas.reg_clouds = self.act_clouds.isChecked()
        self.canvas.invert = self.act_invert.isChecked()
        self.canvas.show_color = self.act_color.isChecked()
        self._update_options()
        self.show_start()

        self._reset_history()
        self._update_title()
        self._update_units()
        if path_a:
            self._set_file("A", path_a, compute=False)
        if path_b:
            self._set_file("B", path_b, compute=False)
        if path_a:
            self.start_compute()
        QTimer.singleShot(400, self.check_autosave)


    # --- Hilfe
    def _open_doc(self, p):
        if not os.path.isfile(p):
            QMessageBox.information(self, APP, tr("{} wurde nicht gefunden.").format(os.path.basename(p)))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def open_help(self):
        self._open_doc(os.path.join(HERE, i18n.doc("Anleitung_Viewer.html")))

    def set_theme(self, mode):
        self.theme_mode = mode
        self.settings.setValue("theme", mode)
        apply_theme(QApplication.instance(), mode)
        self._theme_applied()

    def _system_theme_changed(self, *_):
        if self.theme_mode == "auto" and (THEME["canvas"] == THEMES["dark"]["canvas"]) != system_is_dark():
            apply_theme(QApplication.instance(), "auto")
            self._theme_applied()

    def _theme_applied(self):
        self._set_color_btn(self.canvas.ann_color)
        self._refresh_icons()
        self.canvas.update()

    def make_shortcut(self):
        bat = sys.executable if FROZEN else os.path.join(ROOT, "Start ZGmax.bat")
        if not os.path.isfile(bat):
            QMessageBox.information(self, APP, tr("Start ZGmax.bat wurde nicht gefunden."))
            return
        ico = os.path.join(HERE, "icon.ico")
        icon_loc = f"{sys.executable},0" if FROZEN else (f"{ico},0" if os.path.isfile(ico) else tr("shell32.dll,22"))
        script = ("$d=[Environment]::GetFolderPath('Desktop');"
                  "$s=(New-Object -COM WScript.Shell).CreateShortcut(\"$d\\ZGmax.lnk\");"
                  f"$s.TargetPath='{bat}';$s.WorkingDirectory='{ROOT}';$s.WindowStyle=7;"
                  f"$s.IconLocation='{icon_loc}';$s.Save()")
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, capture_output=True)
            self._log(tr("Desktop-Verkn\u00fcpfung \u201eZGmax\u201c wurde erstellt."))
            QMessageBox.information(self, APP, tr("Die Verkn\u00fcpfung \u201eZGmax\u201c liegt jetzt auf dem Desktop."))
        except Exception as e:                      # noqa: BLE001
            QMessageBox.warning(self, APP, tr("Verknüpfung konnte nicht erstellt werden:\n{}").format(e))

    def open_batch(self):
        BatchDialog(self).exec()

    # --- Vektordaten (PDF)
    def _vec_inspect(self, which, path):
        """PDF auf Vektordaten pruefen - im Hintergrund, damit das Fenster bei grossen PDF nicht haengt."""
        self.vinfo[which] = None
        self.vfilter = (None, None)
        self._vec_status()
        if not (path.lower().endswith(".pdf") and dv.available()):
            return

        def work():
            try:
                return dv.inspect_pdf(path, 1)
            except Exception:                                # noqa: BLE001
                return None

        def done(info):
            if (self.path_a if which == "A" else self.path_b) == path:
                self.vinfo[which] = info
                self._vec_status()
                self._suggest_vector()
        self.run_background(work, done)

    def _vec_status(self):
        def txt(w):
            i = self.vinfo[w]
            if i is None:
                return tr("{}: keine PDF-Datei").format(w)
            if not i["vector"]:
                return tr("{}: Pixelbild im PDF").format(w)
            return tr("{}: Vektordaten ({} Linien/Flächen, {} Texte)").format(w, i['paths'], i['texts'])
        both = all(self.vinfo[w] and self.vinfo[w]["vector"] for w in "AB")
        self.lbl_vec.setText(txt("A") + "\n" + txt("B") + ("" if both else
                             tr("\nVektorvergleich und Filter brauchen echte Vektordaten in beiden PDF.")))
        self.chk_vec.setEnabled(both)
        self.btn_vfilter.setEnabled(both)
        if not both:
            self.chk_vec.setChecked(False)
        lay, col = self.vfilter
        parts = []
        if lay is not None:
            parts.append(tr("{} Ebenen").format(len(lay)))
        if col is not None:
            parts.append(tr("{} Farben").format(len(col)))
        self.lbl_vfilter.setText(tr("Filter: ") + (", ".join(parts) if parts else "alles"))
        self._update_vec_visibility()

    def _suggest_vector(self):
        """Beide PDF mit echten Vektordaten (aus CAD): exakten Vektorvergleich anbieten (kein Pixelrauschen)."""
        both = all(self.vinfo.get(w) and self.vinfo[w]["vector"] for w in "AB")
        if both and not self.chk_vec.isChecked() and not getattr(self, "_vec_offered", None) == (self.path_a, self.path_b):
            self._vec_offered = (self.path_a, self.path_b)

            def on():
                self.chk_vec.setChecked(True)
                self.start_compute()
            self.banner.show_msg(tr("Beide PDF enthalten echte Vektordaten (aus dem CAD-System). Der Vektorvergleich "
                                 "vergleicht Linie gegen Linie \u2013 exakt und ohne Pixelrauschen."), "info",
                                 timeout=40, action=(tr("Vektorvergleich einschalten"), on))

    def open_vfilter(self):
        layers, colors = {}, {}
        for w in "AB":
            i = self.vinfo[w]
            if i:
                for k, v in i["layers"].items():
                    layers[k] = layers.get(k, 0) + v
                for k, v in i["colors"].items():
                    colors[k] = colors.get(k, 0) + v
        dlg = VectorFilterDialog(self, layers, colors, self.vfilter)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.vfilter = dlg.result_filter()
            self._vec_status()
            self._param_changed()
            if self.path_a and self.path_b:
                self.start_compute()

    def run_text(self):
        """Text jeder Aenderung (A -> B): exakt aus dem PDF, wenn beide echten Text haben, sonst Texterkennung."""
        if not self.payload or self.view_only:
            QMessageBox.information(self, APP, tr("Bitte zuerst vergleichen."))
            return
        pdf = bool(self.path_a.lower().endswith(".pdf") and self.path_b.lower().endswith(".pdf") and dv.available())
        pl, pa, pb = self.payload, self.path_a, self.path_b
        na, nb, dpi = self.sp_pa.value(), self.sp_pb.value(), self.dpi_value()
        wa, wb = (dv.pdf_words(pa, na), dv.pdf_words(pb, nb)) if pdf else ([], [])
        if not (wa or wb) and not self.ensure_ocr(tr("Text zu lesen")):
            return

        def work(log):
            self._ensure_regs(log)
            if wa or wb:
                log(tr("Text aus dem PDF (exakt) …"))
                dv.fill_text(pl["regs"], wa, wb, dpi, log)
                return tr("PDF-Text")
            rep.text_diff(pl["res"], pl["regs"], log)
            return tr("Texterkennung")
        def done(how):
            n = sum(1 for r in pl["regs"] if rep.text_changed(r))
            self._fill_table()
            self._commit()
            self._busy(False, tr("Text gelesen ({}): {} Änderungen mit geändertem Text").format(how, n))
            if n:
                self.cb_filter.setCurrentIndex(self.cb_filter.findData("text"))
        self._run_job(work, tr("Lese Text \u2026"), done)

    # --- Datei-Handling
    def open_file(self, which):
        d = self.settings.value("dir", "")
        path, _ = QFileDialog.getOpenFileName(self, tr("Zeichnung {} öffnen").format(which), d, FILE_FILTER)
        if path:
            self._set_file(which, path)

    def _unlock_pdf(self, path):
        """Passwortgeschuetzte PDF: nach dem Passwort fragen (gilt bis zum Beenden). False = abgebrochen."""
        import pdfopen
        if not pdfopen.needs_password(path):
            return True
        msg = tr("„{}“ ist mit einem Passwort geschützt.\nPasswort:").format(os.path.basename(path))
        while True:
            pw, ok = QInputDialog.getText(self, APP, msg, QLineEdit.EchoMode.Password)
            if not ok:
                return False
            if pdfopen.try_password(path, pw):
                return True
            msg = tr("Das Passwort stimmt nicht. Bitte noch einmal:")

    def _set_file(self, which, path, compute=True):
        self.settings.setValue("dir", os.path.dirname(path))
        lbl = self.lbl_a if which == "A" else self.lbl_b
        if not os.path.isfile(path):
            self.banner.show_msg(tr("Datei nicht gefunden: {}").format(path), "error")
            return
        ext = os.path.splitext(path)[1].lower()
        if ext == ".dwg":
            self.banner.show_msg(tr("DWG-Dateien kann das Programm nicht direkt lesen. Bitte im CAD-Programm als DXF "
                                 "oder PDF speichern."), "warn")
            return
        if ext == ".pdf" and not self._unlock_pdf(path):
            return
        if which == "A":
            self.path_a = path
        else:
            self.path_b = path
        lbl.setText(os.path.basename(path))
        lbl.setToolTip(path)
        self.start.set_files(self.path_a, self.path_b)
        self.crop_b = None
        self.manual_tf = None
        if hasattr(self, "act_align_reset"):
            self.act_align_reset.setEnabled(False)
        self._vec_inspect(which, path)
        if which == "A":
            self._detect_dpi(path)
            self._crop_reset(silent=True)
            self.canvas.reset_rotation()
        self._setup_pages(which, path)
        if compute:
            self.start_compute()

    def _detect_dpi(self, path):
        if dp.is_vector(path):
            self.lbl_dpi.setText(tr("PDF/SVG: Die Aufl\u00f6sung bestimmt die Rendergenauigkeit (Standard 200)."))
            return
        d = dp.file_dpi(path)
        self.sp_dpi.blockSignals(True)
        if d:
            self.sp_dpi.setValue(int(d))
            self.lbl_dpi.setText(tr("Aus der Datei gelesen: {} dpi.").format(d))
        else:
            self.lbl_dpi.setText(tr("Die Datei enth\u00e4lt keine Aufl\u00f6sung. Es gilt der eingestellte Wert; "
                                 "bei Bedarf mit Kalibrieren pr\u00fcfen."))
            self.sec_file.set_open(True)
        self.sp_dpi.blockSignals(False)
        self._update_units()

    def _setup_pages(self, which, path):
        n = dp.page_count(path)
        spin = self.sp_pa if which == "A" else self.sp_pb
        spin.blockSignals(True)
        spin.setRange(1, n)
        spin.setValue(1)
        spin.blockSignals(False)
        if which == "A":
            self.n_pages_a = n
        else:
            self.n_pages_b = n
        multi = self.n_pages_a > 1 or self.n_pages_b > 1
        self.sec_pages.setVisible(multi)
        if multi:
            self.sec_pages.set_open(True)
        if which == "A":
            self._fill_pages(path, n)

    def _fill_pages(self, path, n):
        self.page_summary = {}
        self.list_pages.blockSignals(True)
        self.list_pages.clear()
        for i in range(min(n, 200)):
            self.list_pages.addItem(QListWidgetItem(tr("Seite {}").format(i + 1)))
        if self.list_pages.count():
            self.list_pages.setCurrentRow(0)
        self.list_pages.blockSignals(False)
        if not (dp.is_vector(path) and n > 1):
            return

        def work():                                          # Vorschaubilder im Hintergrund (QImage ist threadsicher)
            out = []
            try:
                import pymupdf
                from pdfopen import open_doc
                with open_doc(path) as pm:
                    for i in range(min(n, 60)):
                        pg = pm.load_page(i)
                        z = 120.0 / max(pg.rect.width, pg.rect.height)
                        pix = pg.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
                        out.append(QImage(pix.samples, pix.width, pix.height, pix.stride,
                                          QImage.Format.Format_RGB888).copy())
            except Exception:                                # noqa: BLE001
                pass
            return out

        def done(imgs):
            if self.path_a != path:
                return
            for i, img in enumerate(imgs):
                it = self.list_pages.item(i)
                if it is not None:
                    it.setIcon(QIcon(QPixmap.fromImage(img)))
        self.run_background(work, done)

    def _page_row(self, row):
        if row >= 0:
            self.sp_pa.setValue(row + 1)

    def _remember_page_scale(self, val):
        """Massstab/Kalibrierung gilt je Seite (mehrseitige Dateien haben oft verschiedene Massstaebe)."""
        if self.path_a and not getattr(self, "_page_scale_loading", False):
            self.__dict__.setdefault("page_scales", {})[f"{self.path_a}#{self.sp_pa.value()}"] = float(val)

    def _apply_page_scale(self):
        key = f"{self.path_a}#{self.sp_pa.value()}"
        val = getattr(self, "page_scales", {}).get(key)
        if val is not None and abs(val - self.scale_n()) > 1e-9:
            self._page_scale_loading = True
            self.sp_scale.setValue(val)
            self._page_scale_loading = False

    def _page_changed(self, which, v):
        if which == "A":
            self._apply_page_scale()
        if self.chk_couple.isChecked():
            other = self.sp_pb if which == "A" else self.sp_pa
            if other.maximum() >= v and other.value() != v:
                other.blockSignals(True)
                other.setValue(v)
                other.blockSignals(False)
        if which == "A" and 0 <= v - 1 < self.list_pages.count() and self.list_pages.currentRow() != v - 1:
            self.list_pages.blockSignals(True)
            self.list_pages.setCurrentRow(v - 1)
            self.list_pages.blockSignals(False)
        if self.path_a or self.path_b:                 # auch beim Ansehen einer einzelnen mehrseitigen Datei
            self.page_timer.start(450)

    # --- Markierungen je Seite
    def _page_key(self):
        single = not (self.path_a and self.path_b)
        return f"{self.sp_pa.value()}" if single else f"{self.sp_pa.value()}:{self.sp_pb.value()}"

    def _swap_page_anns(self):
        """Seite gewechselt: Markierungen der bisherigen Seite beiseitelegen, die der neuen holen (Blattkoordinaten)."""
        key = self._page_key()
        old = getattr(self, "_anns_key", None)
        same_page = old is not None and old.split(":")[0] == key.split(":")[0] and (":" in old) != (":" in key)
        if old is None or old == key or same_page:     # gleiche Seite (Ansehen <-> Vergleich): Markierungen behalten
            self._anns_key = key
            return
        self.canvas.reset_interaction()
        pages = self.__dict__.setdefault("page_anns", {})
        ox, oy = self.origin
        cur = copy.deepcopy(self.anns)
        for a in cur:
            shift_ann(a, ox, oy)                           # global ablegen
        if cur:
            pages[old] = cur
        else:
            pages.pop(old, None)
        new = copy.deepcopy(pages.pop(key, []))
        for a in new:
            shift_ann(a, -ox, -oy)
        self.anns[:] = new
        self._anns_key = key
        self.undo_stack, self.redo_stack = [], []          # Rueckgaengig gilt je Seite; Ungespeichertes bleibt markiert
        self._cur_state = self._state()
        self._update_history_buttons()
        self._ann_refresh(None)

    def _update_page_labels(self):
        """Seitenliste: Anzahl Markierungen je Seite (und Aenderungen, wenn alle Seiten verglichen wurden)."""
        if not hasattr(self, "list_pages") or self.list_pages.count() == 0:
            return
        pages = getattr(self, "page_anns", {})
        single = not (self.path_a and self.path_b)
        for i in range(self.list_pages.count()):
            n = i + 1
            key = f"{n}" if single else f"{n}:{n}"
            cnt = len(self.anns) if key == getattr(self, "_anns_key", None) else len(pages.get(key, []))
            base = tr("Seite {}").format(n)
            chg = getattr(self, "page_summary", {}).get(n)
            if chg is not None:
                base += tr("  –  ") + (tr("{} Änderungen").format(chg) if chg else tr("keine Änderung"))
            if cnt:
                base += tr("  ·  {} Markierungen").format(cnt)
            it = self.list_pages.item(i)
            if it.text() != base:
                it.setText(base)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self._files_dropped([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    def _files_dropped(self, files):
        if self.payload is not None or self.path_a or self.path_b:   # schon etwas offen: neues Fenster
            self._doc_window()._files_dropped(files)
            return
        proj = [f for f in files if f.lower().endswith(PROJECT_EXT)]
        if proj:
            self.project_open(proj[0])
            return
        if len(files) >= 2:
            self._set_file("A", files[0], compute=False)
            self._set_file("B", files[1])
        elif files:
            self._set_file("B" if self.path_a else "A", files[0])

    # --- Parameter, Einheiten
    def dpi_value(self):
        return self.sp_dpi.value()

    def scale_n(self):
        return float(self.sp_scale.value())

    def _update_units(self, *_):
        self.canvas.mm_px = 25.4 / max(1, self.dpi_value()) * self.scale_n()
        rep.MEASURE_FMT["mm"] = self.canvas.mm_px     # fuer die Lage der Messwerte (Platz auf kurzen Massen)
        if hasattr(self, "lbl_sums"):
            self._update_sums()
        if hasattr(self, "lbl_meas_scale"):
            n = self.scale_n()
            txt = f"1 : {n:g}" if n >= 1 else f"{1 / n:g} : 1"
            self.lbl_meas_scale.setText(tr("Maßstab {}").format(txt))
            self.lbl_meas_scale.setToolTip(tr("Auflösung {} dpi. Klick = Maßstab eingeben").format(self.dpi_value()))
        if hasattr(self, "list_anns"):
            for i, a in enumerate(self.anns):
                it = self.list_anns.item(i)
                if it:
                    it.setText(self._ann_label(a))
        self.canvas.update()
        if self.payload:
            self._fill_table()

    def _dpi_changed(self):
        self._update_units()
        if self.path_a and self.path_b and any(dp.is_vector(p) for p in (self.path_a, self.path_b)):
            self._param_changed()

    def _calibrate(self, d=None):
        """Massstab so setzen, dass eine gemessene Strecke ihre wahre Laenge hat. Ohne Messung: erst messen
        lassen (zwei Punkte), danach erscheint die Abfrage von selbst."""
        d = d or self.canvas.measure_px()
        if not d:
            self._calib_pending = True
            self.cb_mkind.setCurrentIndex(0)                 # Laenge
            self._set_tool("measure")
            self.banner.show_msg(tr("Kalibrieren: Eine Strecke mit bekannter L\u00e4nge messen (zwei Punkte anklicken, "
                                 "z. B. an einem Ma\u00df der Zeichnung). Danach die wahre L\u00e4nge eingeben."),
                                 "info", timeout=25)
            return
        self._calib_pending = False
        self.banner.hide()
        paper = d * 25.4 / max(1, self.dpi_value())
        val, ok = QInputDialog.getDouble(
            self, tr("Kalibrieren"), tr("Wahre Länge der gemessenen Strecke (mm):\n(gemessen auf dem Blatt: {:.2f} mm)").format(paper), paper * self.scale_n(), 0.001, 1e7, 2)
        if ok and val > 0:
            self.sp_scale.setValue(val / paper)
            self._log(tr("Maßstab kalibriert: 1 : {:.3f}").format(val / paper))

    def params(self):
        return dp.Params(
            thr=int(self.s_thr.value()), align=self.cb_align.currentText() if self.chk_align.isChecked() else "off",
            cell=max(32, int(self.s_cell.value())),
            max_shift=int(self.s_maxs.value()) if self.chk_align.isChecked() else 0, tol=int(self.s_tol.value()), hatch=int(self.s_hatch.value()),
            move=int(self.s_move.value()), obj_shift=int(self.s_obj.value()), obj_rotate=float(self.s_rot.value()),
            min_area=int(self.s_area.value()), ignore=self._local_zones(self._compute_origin()),
            ignore_border=int(self.s_border.value()), edge_noise=self.chk_edges.isChecked(),
            flatten=self.chk_flatten.isChecked(), glyphs=self.chk_glyphs.isChecked(),
            lines=self.cb_lines.currentData(), line_min=self.sp_wmin.value(), line_max=self.sp_wmax.value())

    def _param_changed(self):
        if not (self.path_a and self.path_b):
            return
        if self.chk_live.isChecked():
            self.debounce.start(700)
        self._params_dirty = True
        self.btn_run.setText(tr("Vergleichen \u25cf"))
        self.act_compare.setText(tr("Vergleichen \u25cf"))
        self._update_mode_chip()

    def lines_active(self):
        """True, wenn der Linienfilter etwas ausblendet."""
        key = self.cb_lines.currentData()
        return key in ("contours", "thin") or (key == "custom" and (self.sp_wmin.value() or self.sp_wmax.value()))

    def _lines_changed(self, *_):
        """Linienfilter geaendert: beim Ansehen sofort neu zeichnen, im Vergleich wie jede andere Einstellung."""
        self.row_lines.setVisible(self.cb_lines.currentData() == "custom")
        self._update_mode_chip()
        if self.path_a and self.path_b and not self.view_only:
            self._param_changed()
        elif self.path_a or self.path_b:
            self.debounce.start(500)

    def _reset_params(self):
        for w in (self.s_thr, self.s_tol, self.s_hatch, self.s_move, self.s_obj, self.s_rot, self.s_area,
                  self.s_cell, self.s_maxs):
            w.reset()
        self.cb_align.setCurrentText("affine")
        self.chk_edges.setChecked(True)
        self.chk_glyphs.setChecked(True)
        self.chk_flatten.setChecked(False)
        self.chk_align.setChecked(True)

    # --- Zonen und Ausschnitt
    def _add_zone(self, x, y, w, h):
        ox, oy = self.origin                      # vom Bild kommen lokale Koordinaten -> global speichern
        self.zones.append((x + ox, y + oy, w, h))
        self._refresh_zones()
        self._set_tool("hand")
        self._param_changed()
        self._commit()

    def _remove_zone(self):
        i = self.list_zones.currentRow()
        if 0 <= i < len(self.zones):
            del self.zones[i]
            self._refresh_zones()
            self._param_changed()
            self._commit()

    def _zone_edited(self, i, x, y, w, h):
        """Zone im Bild verschoben oder in der Groesse geaendert (lokale Koordinaten -> global)."""
        if 0 <= i < len(self.zones):
            ox, oy = self.origin
            self.zones[i] = (x + ox, y + oy, w, h)
            self._refresh_zones()
            self.canvas.zone_sel = i
            self._param_changed()
            self._commit()

    def _zone_selected(self, i):
        self.list_zones.blockSignals(True)
        self.list_zones.setCurrentRow(i)
        self.list_zones.blockSignals(False)
        if i >= 0:
            self.statusBar().showMessage(tr("Zone gewählt: ziehen = verschieben, Ecken = Größe, Entf = löschen"), 5000)

    def _zone_delete(self, idx=None):
        i = self.canvas.zone_sel if idx is None else idx
        if i is None or not (0 <= i < len(self.zones)):
            return
        del self.zones[i]
        self.canvas.zone_sel = None
        self._refresh_zones()
        self._param_changed()
        self._commit()

    def _clear_zones(self):
        if self.zones:
            self.zones.clear()
            self._refresh_zones()
            self._param_changed()
            self._commit()

    def _local_zones(self, origin=None):
        ox, oy = origin if origin is not None else self.origin
        return [(x - ox, y - oy, w, h) for x, y, w, h in self.zones]

    def _refresh_zones(self):
        self.list_zones.clear()
        for z in self.zones:
            self.list_zones.addItem(tr("x=%d y=%d  %d\u00d7%d px") % z)
        self.canvas.zones = self._local_zones()
        self.canvas.update()

    def _compute_origin(self):
        """Ursprung des Ergebnisses: Ecke des Ausschnitts (Vektorvergleich nutzt immer das ganze Blatt)."""
        vec = self.chk_vec.isChecked() and self.chk_vec.isEnabled()
        return (self.crop[0], self.crop[1]) if (self.crop and not vec) else (0, 0)

    def _set_origin(self, new):
        """Rechnet Anmerkungen auf einen neuen Ursprung um, damit sie am Blatt haften bleiben."""
        dx, dy = self.origin[0] - new[0], self.origin[1] - new[1]
        self.origin = tuple(new)
        if dx or dy:
            for a in self.anns:
                shift_ann(a, dx, dy)
            self._ann_refresh(None)
        self._refresh_zones()

    def _crop_drawn(self, x, y, w, h):
        if w < 200 or h < 200:
            self.banner.show_msg(tr("Ausschnitt zu klein (mindestens 200 × 200 Pixel)."), "warn", timeout=8)
            return
        ox, oy = self.origin
        self.crop = (ox + x, oy + y, w, h)
        self.manual_tf = None                     # Punkte bezogen sich auf den alten Ausschnitt
        self.btn_crop_off.setEnabled(True)
        self.lbl_crop.setText(tr("Aktuell: Ausschnitt {} × {} px").format(w, h))
        self._set_tool("hand")
        self.start_compute()

    def _crop_reset(self, silent=False):
        if self.crop is None:
            return
        self.crop = None
        self.crop_b = None
        self.manual_tf = None                     # Punkte bezogen sich auf den Ausschnitt
        self.btn_crop_off.setEnabled(False)
        self.lbl_crop.setText(tr("Aktuell: ganzes Blatt"))
        if not silent:
            self.start_compute()

    # --- Jobs
    def _run_job(self, fn, text, done, on_abort=None):
        """Startet eine Hintergrundberechnung (nur eine gleichzeitig) mit Fortschritt und Abbrechen."""
        if self.running:
            self._log(tr("Bitte warten, es l\u00e4uft noch eine Berechnung."))
            return False
        self.running = True
        self._busy(True, text)
        job = Job(fn, self)
        self.jobs.append(job)
        self.current_job = job
        job.log.connect(self._log)
        job.progress.connect(self._on_progress)
        job.preview.connect(lambda pv: self.canvas.set_preview(*pv))

        def ok(r):
            self.running = False
            self._busy(False, tr("Fertig"))
            done(r)

        def bad(m):
            self.running = False
            self._failed(m, job.details)

        def aborted():
            self.running = False
            self.pending = False
            self._busy(False, tr("Abgebrochen"))
            self.canvas.set_preview(None, None)
            self.banner.show_msg(tr("Berechnung abgebrochen."), "info", timeout=6)
            if on_abort:
                on_abort()
        job.done.connect(ok)
        job.failed.connect(bad)
        job.aborted.connect(aborted)
        job.finished.connect(lambda j=job: self.jobs.remove(j) if j in self.jobs else None)
        job.start()
        return True

    def cancel_job(self):
        if self.current_job is not None and self.current_job.isRunning():
            self.current_job.cancel()
            self.lbl_status.setText(tr("Breche ab \u2026"))
            self.btn_cancel.setEnabled(False)

    def _on_progress(self, frac, text):
        self.progress.setRange(0, 1000)
        self.progress.setValue(int(frac * 1000))
        if text:
            self.lbl_status.setText(f"{text} \u2026  {frac * 100:.0f} %")

    def start_compute(self):
        if not (self.path_a or self.path_b):
            self.show_start()
            return
        if self.running:
            self.pending = True
            return
        self.debounce.stop()
        single = not (self.path_a and self.path_b)
        pa_, pb_ = self.path_a or self.path_b, self.path_b or self.path_a
        if self.path_a:
            ga_, gb_ = self.sp_pa.value(), self.sp_pa.value() if single else self.sp_pb.value()
        else:
            ga_ = gb_ = self.sp_pb.value()
        snap = dict(pa=pa_, pb=pb_, page_a=ga_, page_b=gb_,
                    dpi=self.dpi_value(), params=self.params(), crop=self.crop, crop_b=self.crop_b,
                    manual=self.manual_tf,
                    vf=self.vfilter, origin=self._compute_origin(), single=single,
                    pdf_off=tuple(sorted(getattr(self, "pdf_off", set()))),
                    vec=(not single) and self.chk_vec.isChecked() and self.chk_vec.isEnabled(),
                    vtol=self.sp_vtol.value())
        self._swap_page_anns()                           # Markierungen gehoeren zur Seite
        self.pending = False
        self._params_dirty = False
        self.btn_run.setText(tr("Vergleichen"))
        self.act_compare.setText(tr("Vergleichen"))
        self._update_mode_chip()
        self.banner.hide()
        if self.payload is None:
            self.stack.setCurrentWidget(self.work)
        self.canvas.preview_text = tr("Zeichnung wird geladen …") if single else tr("Vergleich läuft …")
        self._run_job(lambda ctx: self._compute(snap, ctx),
                      tr("Lade \u2026") if single else tr("Vergleiche \u2026"), lambda r: self._computed(r, snap))

    def _gray(self, path, page, dpi, log, vf=(None, None), hidden=()):
        filt = vf if (path.lower().endswith(".pdf") and vf != (None, None)) else (None, None)
        hidden = tuple(sorted(hidden)) if path.lower().endswith(".pdf") else ()
        try:                                         # Datei auf der Platte geaendert -> neu laden
            stt = os.stat(path)
            stamp = (stt.st_mtime_ns, stt.st_size)
        except OSError:
            stamp = None
        key = ("gray", path, stamp, page, dpi if dp.is_vector(path) else 0, repr(filt), hidden)
        if self.cache.get("gk_" + path) != key:
            log(tr("Lade {} …").format(os.path.basename(path)))
            if filt != (None, None):
                self.cache["g_" + path] = dv.render_gray(path, page, dpi, *filt)
                self.cache["c_" + path] = None
            else:
                img = dc.read_image(path, page, dpi, hidden)
                self.cache["g_" + path] = img.min(axis=2)            # dunkelster Kanal (wie load_gray)
                self.cache["c_" + path] = img if dp.is_colored(img) else None   # Farbfassung nur, wenn farbig
            self.cache["gk_" + path] = key
        return self.cache["g_" + path]

    def _color(self, path):
        return self.cache.get("c_" + path)

    def _compute_vec(self, snap, log):
        log.progress(0.05, tr("Lese Vektordaten"))
        p = snap["params"]
        if snap["crop"]:
            log(tr("Hinweis: Im Vektorvergleich wird immer das ganze Blatt verglichen (Ausschnitt ignoriert)."))
        fa = snap["vf"]
        a, b, oa, ob, both = dv.vector_diff(snap["pa"], snap["pb"], snap["page_a"], snap["page_b"], snap["dpi"],
                                            fa, fa, snap["vtol"], log)
        zone = dp.make_zone(a.shape, p.ignore, p.ignore_border)
        if zone is not None:
            oa[zone] = ob[zone] = False
            both[zone] = a[zone] > 0
        if p.min_area > 0:
            dp.filter_small(oa, ob, p.min_area, both=both)
        res = dp.Result(a, b, oa, ob, both, np.zeros_like(oa), zone)
        log(tr("Erzeuge Ansichten \u2026"))
        pa, pb, pd, po = build_pyramids(res)
        return dict(res=res, regs=[], regs_done=False, pa=pa, pb=pb, pd=pd, po=po)

    def _compute(self, snap, log):
        p = snap["params"]
        if snap.get("vec"):
            return self._compute_vec(snap, log)
        log.progress(0.01, tr("Lade ") + os.path.basename(snap["pa"]))
        ga = self._gray(snap["pa"], snap["page_a"], snap["dpi"], log, snap["vf"], snap.get("pdf_off", ()))
        log.check()
        if self.payload is None:                     # erste Berechnung: schon mal Zeichnung A zeigen
            k = min(1.0, 2400 / max(ga.shape))
            log.preview((cv2.resize(ga, None, fx=k, fy=k, interpolation=cv2.INTER_AREA), ga.shape))
        if snap.get("single"):                       # nur eine Datei: anzeigen, nicht vergleichen
            a0 = dp.ink_from_gray(ga, p.thr, p.flatten)
            p, band = dp.resolve_lines(a0, p, self._vector_gw(snap["pa"], snap["page_a"], snap["dpi"], p))
            a, _b = dp.apply_line_filter(a0, a0, p, log)
            z = np.zeros(a.shape, bool)              # calloc: kostet erst Speicher, wenn beschrieben
            res = dp.Result(a, a, z, z, a > 0, z, None)
            log.progress(0.6, tr("Erzeuge Ansicht"))
            pa, pb, pd, po = build_pyramids(res)
            ca = self._color(snap["pa"])
            ca = ca if ca is not None else ga                # Original: Farbe oder Graustufen
            ca = hide_filtered(ca, a0, a)
            pc = build_color_pyramids(ca, len(pa))
            return dict(res=res, regs=[], regs_done=False, pa=pa, pb=pb, pd=pd, po=po, color=(ca, ca), pc=(pc, pc),
                        band=band)
        log.progress(0.12, tr("Lade ") + os.path.basename(snap["pb"]))
        gb = self._gray(snap["pb"], snap["page_b"], snap["dpi"], log, snap["vf"], snap.get("pdf_off", ()))
        log.check()
        key = (self.cache.get("gk_" + snap["pa"]), self.cache.get("gk_" + snap["pb"]), p.thr, p.flatten, p.align,
               snap["crop"], snap.get("crop_b"), repr(snap.get("manual")))
        if self.cache.get("key") != key:
            self.cache["key"] = None
            log.progress(0.22, tr("Richte aus"))
            a_full, b_full = dp.ink_from_gray(ga, p.thr, p.flatten), dp.ink_from_gray(gb, p.thr, p.flatten)
            if snap.get("crop_b") and snap["crop"]:   # Bereiche selbst zugeordnet
                a, b0 = dc.crop(a_full, snap["crop"]), dc.crop(b_full, snap["crop_b"])
                box_b = snap["crop_b"]
                log(tr("Zugeordnete Bereiche: A {}  B {}").format(snap['crop'], snap['crop_b']))
            else:
                a, b0, box_b = dp.crop_pair(a_full, b_full, snap["crop"], log)
            log.check()
            self.cache["b"], tf = dp.prepare_pair_tf(a, b0, p.align, log)
            self.cache["a"] = a
            self.cache["tf"], self.cache["box_b"] = tf, box_b     # fuer Suchtreffer in B (Punkte ausrichten)
            # Farbfassungen (nur Anzeige von Alt/Neu) genauso zuschneiden und ausrichten wie die Tinte
            # Originalfassungen fuer Alt/Neu (Farbe, sonst Graustufen) genauso zuschneiden und ausrichten
            ca, cb = self._color(snap["pa"]), self._color(snap["pb"])
            if (ca is None) != (cb is None):                 # eine farbig, eine grau: beide farbig fuehren
                ca = ca if ca is not None else cv2.cvtColor(ga, cv2.COLOR_GRAY2BGR)
                cb = cb if cb is not None else cv2.cvtColor(gb, cv2.COLOR_GRAY2BGR)
            ca = ca if ca is not None else ga
            cb = cb if cb is not None else gb
            ca = dc.crop(ca, snap["crop"])
            cb = dp.apply_tf(dc.crop(cb, box_b), tf)
            if snap.get("manual") is not None:           # manuelle Ausrichtung zusaetzlich anwenden
                M = np.float32(snap["manual"])
                h_, w_ = self.cache["a"].shape
                bm = cv2.warpAffine(self.cache["b"], M, (w_, h_), flags=cv2.INTER_LINEAR, borderValue=0)
                self.cache["b"] = ((bm > 127).astype(np.uint8)) * 255
                cb = cv2.warpAffine(cb, M, (w_, h_), flags=cv2.INTER_LINEAR,
                                    borderValue=(255, 255, 255) if cb.ndim == 3 else 255)
            self.cache["color"] = (ca, cb)
            self.cache["key"] = key
        log.check()
        p, band = dp.resolve_lines(self.cache["a"], p, self._vector_gw(snap["pa"], snap["page_a"], snap["dpi"], p))
        res = dp.run_compare(self.cache["a"], self.cache["b"], p, log, cancel=log.cancelled,
                             progress=lambda f, t: log.progress(0.3 + 0.62 * f, t))
        log.progress(0.93, tr("Erzeuge Ansichten"))
        pa, pb, pd, po = build_pyramids(res)
        ca, cb = self.cache.get("color", (None, None))
        if res.a is not self.cache["a"]:                       # Linienfilter: auch im Original ausblenden
            ca, cb = hide_filtered(ca, self.cache["a"], res.a), hide_filtered(cb, self.cache["b"], res.b)
        return dict(res=res, regs=[], regs_done=False, pa=pa, pb=pb, pd=pd, po=po, color=(ca, cb),
                    pc=(build_color_pyramids(ca, len(pa)), build_color_pyramids(cb, len(pa))), band=band)

    def _vector_gw(self, path, page, dpi, p):
        """Koerperkantenbreite (px) aus den echten Strichbreiten eines Vektor-PDF; None = aus den Pixeln schaetzen."""
        if p.lines not in ("contours", "thin") or not path.lower().endswith(".pdf") or not dv.available():
            return None
        key = ("strokes", path, page, dpi, self.cache.get("gk_" + path))
        if self.cache.get("sk_" + path) != key:
            try:
                hist = dv.stroke_hist(path, page, dpi)
            except Exception:                                   # noqa: BLE001
                hist = {}
            self.cache["sh_" + path], self.cache["sk_" + path] = hist, key
        hist = self.cache["sh_" + path]
        if sum(hist.values()) < 1000:                          # kaum Vektorlinien (z. B. eingebetteter Scan)
            return None
        return de.geometry_width_from_strokes(hist)

    def _scan_hint(self):
        """Einmal je Datei beim Ansehen einer Rasterzeichnung: schiefer Scan oder Foto eines Blatts? Dann Hinweis mit
        Knopf zur passenden Aufbereitung (nichts geschieht von selbst)."""
        path = self.path_a or self.path_b
        if not (self.view_only and path) or path in self._hinted or dp.is_vector(path):
            return
        self._hinted.add(path)
        g = self.cache.get("g_" + path)
        if g is None:
            return
        try:
            hint = de.scan_hint(g)
        except Exception:                                  # noqa: BLE001 - nur ein Hinweis
            log.exception("Scan-Hinweis")
            return
        if hint and hint[0] == "photo":
            self.banner.show_msg(tr("Sieht aus wie ein Foto eines Blatts. Entzerren macht es rechteckig und "
                                    "maßhaltig."), "info", action=(tr("Entzerren …"), self.sheet_perspective),
                                 timeout=15)
        elif hint:
            self.banner.show_msg(tr("Die Zeichnung liegt um {}° schief.").format(QLocale().toString(hint[1], "f", 1)),
                                 "info", action=(tr("Gerade ausrichten …"), self.sheet_straighten), timeout=15)

    def _computed(self, r, snap):
        keep = self.payload is not None and snap["crop"] == self._crop_seen
        self.payload = r
        self.index_info = None
        self.canvas.selected = None
        self._set_origin(snap["origin"])           # Anmerkungen/Zonen haften am Blatt, nicht am Ausschnitt
        self.canvas.set_data(r["res"], r["pa"], r["pb"], r["pd"], r["regs"], keep_view=keep, po=r["po"],
                             pc=r.get("pc"))
        self._crop_seen = snap["crop"]
        self.canvas.zones = self._local_zones()
        self._refresh_frame()
        self.canvas.set_preview(None, None)
        self.stack.setCurrentWidget(self.work)
        was_view_only = self.view_only
        self._set_view_only(bool(snap.get("single")))
        if snap.get("single"):
            self._set_mode("A")
            self.canvas.labels = ("A", "A")
        else:
            self.canvas.labels = ("A  " + os.path.basename(self.path_a), "B  " + os.path.basename(self.path_b))
            if was_view_only or self.canvas.mode not in self.mode_actions:
                self._set_mode("D")
            if not self.act_left.isChecked() and not getattr(self, "_left_auto_done", False):
                self.act_left.setChecked(True)     # beim ersten Vergleich Einstellungen zeigen
                self._left_auto_done = True
        if self.restore_regs is not None and not snap.get("single"):
            r["regs"][:] = self.restore_regs   # Pruefstand aus dem Projekt
            r["regs_done"] = True
            self.restore_regs = None
        if snap["params"].lines in ("contours", "thin") and r.get("band") == (0, 0):
            self.banner.show_msg(tr("Linienfilter wirkt hier nicht: Die Zeichnung hat keine deutlich "
                                    "unterschiedlichen Strichstärken. Es werden alle Linien gezeigt."), "info",
                                 timeout=12)
        self._regs_ver = getattr(self, "_regs_ver", 0) + 1    # neue Liste: Rueckgaengig beginnt fuer sie neu
        self._cur_state = self._state()
        recent_add(self.settings, a=self.path_a, b=self.path_b, project=self.project_path)
        self._update_enabled()
        self._refresh_pdf_layers()
        QTimer.singleShot(0, self._auto_import_pdf_comments)
        QTimer.singleShot(400, self._scan_hint)
        if self.search_bar.isVisible():                # Treffer an die neue Lage anpassen
            QTimer.singleShot(0, self.run_search)
        self._fill_table()
        self._update_title()
        self.canvas.setFocus()
        if snap.get("single"):
            self._busy(False, tr("Bereit. Mausrad = zoomen, Ziehen = verschieben, rechte Maustaste ziehen = Zoom-Rahmen."))
        else:
            self._busy(False, tr("Fertig. \u201e\u00c4nderungen suchen\u201c (rechte Leiste) nummeriert die Unterschiede."))
        if self.pending or (self.chk_live.isChecked() and getattr(self, "_params_dirty", False)):
            self.start_compute()

    def _failed(self, msg, details=""):
        self._busy(False, tr("Fehler"))
        self._log(tr("FEHLER: ") + msg)
        self.canvas.set_preview(None, None)
        if self.payload is None:
            self.show_start()
            QMessageBox.warning(self, APP, msg)
        else:
            self.banner.show_msg(msg, "error", details)

    def _busy(self, on, text):
        self.progress.setVisible(on)
        self.progress.setRange(0, 0)                 # unbestimmt, bis die erste Fortschrittsmeldung kommt
        self.btn_cancel.setVisible(on)
        self.btn_cancel.setEnabled(True)
        self.lbl_status.setText(text)
        self.btn_run.setEnabled(not on)
        self.btn_regs.setEnabled(not on)
        self.act_compare.setEnabled(not on and bool(self.path_a and self.path_b))

    def _log(self, text):
        self.log.appendPlainText(text)
        self.lbl_status.setText(text.strip())

    # --- Ansicht und Werkzeuge
    def _set_mode(self, m):
        if self.view_only and m != "A":
            return
        self.mode_actions[m].setChecked(True)
        seg = {"N": "B", "R": "A"}.get(m, m)
        if seg in self.seg_buttons:
            self.seg_buttons[seg].setChecked(True)
        self.chk_highlight.blockSignals(True)
        self.chk_highlight.setChecked(m in ("N", "R"))
        self.chk_highlight.blockSignals(False)
        fit_after = (m == "Y") != (self.canvas.mode == "Y")      # Nebeneinander halbiert die Breite
        self.canvas.mode = m
        self.act_legend.setEnabled(m in ("D", "O", "N", "R") and not self.view_only)   # Legende nur im Vergleich
        if fit_after:
            self.canvas.fit()
        if m == "K" and self.act_pause.isChecked():
            self.act_pause.setChecked(False)       # Klick auf \u201eBlinken\u201c hebt eine Pause immer auf
        self._update_options()
        if m == "K" and not self.act_pause.isChecked():
            self.blink.start()
        else:
            self.blink.stop()
        self.canvas.update()

    def _pause_blink(self, on):
        if on:
            self.blink.stop()
        elif self.canvas.mode == "K":
            self.blink.start()
        self.canvas.update()

    def _blink(self):
        self.canvas.blink_b = not self.canvas.blink_b
        self.canvas.update()

    def _space(self):
        if self.canvas.mode != "K":
            self._set_mode("K")
            self.act_pause.setChecked(True)        # Leertaste = von Hand schalten
        self.canvas.blink_b = not self.canvas.blink_b
        self.canvas.update()

    def swap_ab(self):
        a, b = self.path_a, self.path_b
        if not (a and b):
            return
        pa, pb = self.sp_pa.value(), self.sp_pb.value()
        self.path_a, self.path_b = b, a
        ta, tb_ = self.lbl_a.text(), self.lbl_b.text()
        ua, ub = self.lbl_a.toolTip(), self.lbl_b.toolTip()
        self.lbl_a.setText(tb_)
        self.lbl_a.setToolTip(ub)
        self.lbl_b.setText(ta)
        self.lbl_b.setToolTip(ua)
        self.n_pages_a, self.n_pages_b = self.n_pages_b, self.n_pages_a
        for sp, n, v in ((self.sp_pa, self.n_pages_a, pb), (self.sp_pb, self.n_pages_b, pa)):
            sp.blockSignals(True)
            sp.setRange(1, max(1, n))
            sp.setValue(v)
            sp.blockSignals(False)
        self._vec_inspect("A", self.path_a)
        self._vec_inspect("B", self.path_b)
        self.start_compute()

    def copy_result(self):
        if self.canvas.tool == "area" and self.canvas.sel_rects:
            self.area_copy()
            return
        if self.canvas.tool == "hand" and self.canvas.selected_anns():   # gewaehlte Markierungen kopieren
            self.copy_markups()
            return
        if not self._need_result():
            return
        mode, overlays = self.canvas.mode, self.act_overlays.isChecked()
        out = np.ascontiguousarray(self.export_render(mode, overlays))
        h, w = out.shape[:2]
        fmt = QImage.Format.Format_BGR888 if out.ndim == 3 else QImage.Format.Format_Grayscale8
        img = QImage(out.data, w, h, out.strides[0], fmt).copy()
        QGuiApplication.clipboard().setImage(img)
        self._log(tr("Ergebnis in die Zwischenablage kopiert."))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._fit_toolbar)

    def _canvas_menu(self, gpos):
        m = QMenu(self)
        m.addAction(self.act_fit)
        m.addAction(self.act_100)
        m.addAction(self.act_rotate)
        m.addSeparator()
        for key in ("hand", "measure", "text", "cloud", "arrow", "highlight"):
            m.addAction(self.tool_actions[key])
        m.addSeparator()
        if self.path_a and self.path_b:
            m.addAction(tr("A und B tauschen"), self.swap_ab)
        if self.canvas.zone_sel is not None:
            m.addAction(tr("Zone löschen"), self._zone_delete)
            m.addSeparator()
        if self.payload is not None and self.canvas._mouse is not None:   # Nullpunkt fuer Koordinaten
            c = self.canvas
            ix, iy = c.to_img(c._vp(c._mouse))
            sx, sy, _k = c.snap_point(ix, iy) if c.snap else (ix, iy, None)
            m.addAction(tr("Nullpunkt hier setzen"), lambda: (setattr(c, "coord_origin", (sx, sy)), c.update()))
            if c.coord_origin is not None:
                m.addAction(tr("Nullpunkt zurücksetzen"), lambda: (setattr(c, "coord_origin", None), c.update()))
            m.addSeparator()
        if self.canvas.sel_rects:                        # Bereichsauswahl: ihre Befehle zuerst
            for k, b in self.area_buttons.items():
                if b.isVisible():
                    m.addAction(b.text(), b.click if isinstance(b, QPushButton) else b.trigger)
            m.addSeparator()
        if not self.canvas.sel_rects:                    # mit Bereichsauswahl stehen Kopieren & Co. schon oben
            m.addAction(self.act_copy)
            m.addAction(self.act_copy_sel)
        if self.view_only:
            m.addAction(self.act_move_sel)
        m.addAction(self.act_export_img)
        m.exec(gpos)

    def _zoom_box_done(self):
        """Zoom-Rahmen ueber Taste/Menue: einmalig, danach zurueck. Ueber die Palette gewaehlt: bleibt aktiv."""
        if not self.tool_actions["zoom"].isChecked():
            self._set_tool(self._prev_tool)

    def _set_tool(self, t):
        c = self.canvas
        if t == "zoom" and c.tool != "zoom":
            self._prev_tool = c.tool                   # Zoom-Rahmen ist einmalig, danach zurueck
        if c.float is not None and t != "cutmove":       # schwebenden Ausschnitt beim Werkzeugwechsel absetzen
            self._float_done(True)
        if t != "area" and c.sel_rects:                  # Bereichsauswahl gilt nur im Werkzeug "Bereich"
            c.sel_rects = []
        c.zone_sel = None
        c.tool = t
        if c.ann_selected is not None or c.ann_multi:  # Werkzeugwechsel hebt die Auswahl auf (Leiste zeigt Vorgabe)
            c.ann_selected = None
            c.ann_multi = set()
            self.list_anns.blockSignals(True)
            self.list_anns.clearSelection()
            self.list_anns.setCurrentRow(-1)
            self.list_anns.blockSignals(False)
            self._sync_ann_controls()
        c.measure = []
        c.poly, c._poly_hover, c._pen = [], None, None
        c.snap_hint = None
        c.hover = None
        c._ann_prev = None
        c._rubber = None
        c._drag = None                                   # angefangenes Ziehen gehoert zum alten Werkzeug
        b = getattr(self, "group_buttons", {}).get(t)
        if b is not None:
            m = b.menu()                                   # Gruppenknopf zeigt das zuletzt gewaehlte Werkzeug
            b.setDefaultAction(self.tool_actions[t])
            b.setMenu(m)
        if t in self.tool_actions:
            self.tool_actions[t].setChecked(True)
        else:                                  # Zone/Ausschnitt/Zoom: kein Knopf in der Palette
            for a in self.tool_actions.values():
                if a.isChecked():
                    a.actionGroup().setExclusive(False)
                    a.setChecked(False)
                    a.actionGroup().setExclusive(True)
        if t in ("text", "number", "rect", "arrow", "approval", "zone", "crop", "measure", "region", "cloud",
                 "highlight", "ellipse", "line", "polyline", "polygon", "pen", "area", "redact", "pixelate"):
            self.act_overlays.setChecked(True)
        self._update_options()
        c.setCursor(Qt.CursorShape.OpenHandCursor if t == "hand" else Qt.CursorShape.CrossCursor)
        self.statusBar().showMessage(TOOL_HINTS.get(t, ""), 8000)
        c.setFocus()
        c.update()

    def _toggle_loupe(self, on):
        self.canvas.loupe = on
        self._update_options()
        self.canvas.update()

    def _mkind_changed(self, *_):
        self.canvas.measure_kind = self.cb_mkind.currentData()
        self._set_tool("measure")

    def _toggle_overlays(self, on):
        self.canvas.show_overlays = on
        self.canvas.update()

    def _toggle_regs(self, on):
        self.canvas.show_regs = on
        self.canvas.update()

    def _toggle_snap(self, on):
        self.canvas.snap = on
        self.canvas.snap_hint = None

    def _zoom100(self):
        c = self.canvas
        if c.res is not None:
            c.zoom_to(1.0, c.ox + c.width() / 2 / c.scale, c.oy + c.height() / 2 / c.scale)

    def _on_cursor(self, ix, iy, s):
        c = self.canvas
        if c.coord_origin is not None:                 # Koordinaten ab Nullpunkt (y nach oben, wie im CAD)
            x, y = c.to_coords(ix, iy)
            u = rep.MEASURE_FMT.get("unit", "mm")
            self.lbl_pos.setText(tr("x {:.2f}  y {:.2f} {}  (ab Nullpunkt)").format(x, y, u))
            return
        mm = c.mm_px
        self.lbl_pos.setText(tr("x {}  y {} px   |   {:.1f} / {:.1f} mm").format(ix, iy, ix * mm, iy * mm))

    def _on_view_changed(self, s):
        self.lbl_zoom.setText(f"{s * 100:.0f} %")


class _FileOpenFilter(QObject):
    """macOS: Dateien, die im Finder auf das Programm gezogen oder mit ihm geoeffnet werden."""

    def __init__(self, win):
        super().__init__()
        self.win, self.files = win, []
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._flush)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.FileOpen and ev.file():
            self.files.append(ev.file())
            self.timer.start(300)                    # mehrere Dateien kommen einzeln nacheinander
            return True
        return False

    def _flush(self):
        files, self.files = self.files, []
        act = QApplication.activeWindow()
        win = act if isinstance(act, MainWindow) else (WINDOWS[-1] if WINDOWS else None)
        if files and win is not None:
            win._files_dropped(files)


def setup_logging():
    """Logdatei im Benutzerordner (rotierend) und unbehandelte Fehler dort eintragen statt abzustuerzen."""
    import logging.handlers
    try:
        fh = logging.handlers.RotatingFileHandler(os.path.join(app_data_dir(), "zeichnungsvergleich.log"),
                                                  maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        root = logging.getLogger()
        root.addHandler(fh)
        root.setLevel(logging.INFO)
    except OSError:
        pass

    def hook(et, ev, tb):
        import traceback
        text = "".join(traceback.format_exception(et, ev, tb))
        log.error("Unbehandelter Fehler:\n" + text)
        app = QApplication.instance()
        for w in (app.topLevelWidgets() if app else []):
            if isinstance(w, MainWindow):
                if issubclass(et, PermissionError):   # typisch Windows: Datei in Acrobat/Excel geoeffnet
                    msg = tr("Datei kann nicht geschrieben werden – ist sie in einem anderen Programm geöffnet? ({})")
                    w.banner.show_msg(msg.format(getattr(ev, "filename", "") or ev), "error", text)
                else:
                    w.banner.show_msg(tr("Unerwarteter Fehler: {}: {}").format(et.__name__, ev), "error", text)
                break
    sys.excepthook = hook


def selftest():
    """Prueft im fertigen Programm, ob alle Bausteine laden und rechnen (Aufruf mit --selbsttest)."""
    import tempfile
    out, ok = [], True

    def step(name, fn):
        nonlocal ok
        try:
            r = fn()
            out.append(tr("OK      {}").format(name) + (f": {r}" if r else ""))
        except Exception as e:                       # noqa: BLE001
            ok = False
            out.append(tr("FEHLER  {}: {}: {}").format(name, type(e).__name__, e))
    tmp = tempfile.mkdtemp()
    img = np.full((600, 800), 255, np.uint8)
    cv2.rectangle(img, (50, 50), (700, 500), 0, 3)
    cv2.putText(img, tr("Massstab 1:5"), (80, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 0, 2)
    img2 = img.copy()
    cv2.circle(img2, (500, 200), 60, 0, 3)
    pa, pb = os.path.join(tmp, "a.png"), os.path.join(tmp, "b.png")
    dc.imwrite_any(pa, img)
    dc.imwrite_any(pb, img2)

    def compare():
        p = dp.Params()
        a = dp.ink_from_gray(dp.load_gray(pa), p.thr)
        b = dp.prepare_pair(a, dp.ink_from_gray(dp.load_gray(pb), p.thr), p.align, lambda *_: None)
        r = dp.run_compare(a, b, p, lambda *_: None)
        assert r.ob.any(), tr("Aenderung nicht gefunden")
        return tr("{} Aenderung(en)").format(len(rep.find_regions(r)))

    def pdf():
        import pymupdf
        d = pymupdf.open()
        d.new_page().insert_text((72, 72), "Test")
        f = os.path.join(tmp, "t.pdf")
        d.save(f)
        return f"{dc.read_image(f, dpi=72).shape}"

    def dxf():
        import ezdxf
        d = ezdxf.new()
        d.modelspace().add_line((0, 0), (100, 50))
        f = os.path.join(tmp, "t.dxf")
        d.saveas(f)
        return f"{dc.read_image(f, dpi=72).shape}"

    def ocr():
        if not rep.ocr_available():
            return tr("nicht enthalten")
        return " ".join(t[-1] for t in rep.ocr_image(img))
    step(tr("Vergleich"), compare)
    step("PDF", pdf)
    step("DXF", dxf)
    step(tr("Texterkennung"), ocr)
    step(tr("Schrift"), lambda: os.path.basename(str(dc._font_path())))
    text = tr("{} {} Selbsttest\n").format(APP, VERSION) + "\n".join(out)
    log.info(text)
    print(text)
    return 0 if ok else 1


def install_qt_translations(app):
    """Knoepfe der Qt-eigenen Fenster (Speichern, Verwerfen, Abbrechen, Ja/Nein, Dateiauswahl) in der
    Programmsprache. Englisch ist die Grundsprache von Qt und braucht nichts."""
    from PySide6.QtCore import QLibraryInfo, QTranslator
    if i18n.LANG == "en":
        return None
    t = QTranslator(app)
    if t.load(f"qtbase_{i18n.LANG}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(t)
        return t
    log.info("Qt-Uebersetzung qtbase_%s nicht gefunden", i18n.LANG)
    return None


def main():
    if "--selbsttest" in sys.argv:
        setup_logging()
        sys.exit(selftest())
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is not None:
            setattr(sys, name, SafeStream(getattr(sys, name)))
    if os.name == "nt":                          # eigenes Symbol in der Taskleiste (nicht das von Python)
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ZGmax.Viewer.2")
        except Exception:                        # noqa: BLE001
            pass
    scale = ui_scale_setting(app_settings())       # Groesse der Oberflaeche (vor dem Start festlegen)
    if abs(scale - 1.0) > 0.01:
        os.environ["QT_SCALE_FACTOR"] = f"{scale:.2f}"
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setOrganizationName("ZGmax")
    app.setApplicationVersion(VERSION)
    app.setStyle(tr("Fusion"))
    setup_logging()
    install_qt_translations(app)
    log.info(tr("Start {} {} ({}, Python {})").format(APP, VERSION, sys.platform, sys.version.split()[0]))
    apply_theme(app, theme_setting(app_settings()))
    ico = os.path.join(HERE, "icon.png")
    if os.path.isfile(ico):
        app.setWindowIcon(QIcon(ico))
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    proj = [a for a in args if a.lower().endswith(PROJECT_EXT)]
    args = [a for a in args if a not in proj]
    w = MainWindow(args[0] if len(args) > 0 else None, args[1] if len(args) > 1 else None)
    WINDOWS.append(w)
    fo = _FileOpenFilter(w)
    app.installEventFilter(fo)
    w.show()
    if proj:
        QTimer.singleShot(0, lambda: w.project_open(proj[0]))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
