"""Hauptfenster: Tabelle aus der Bereichsauswahl lesen und als CSV kopieren oder speichern."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
import diffedit as de
import tableextract as te

SEPS = ((";", tr("Semikolon (;)")), (",", tr("Komma (,)")), ("\t", tr("Tabulator (zum Einfügen in Excel)")))


class TableDialog(QDialog):
    """Vorschau der gelesenen Tabelle (Zellen bearbeitbar), Trennzeichen waehlen, kopieren oder speichern."""

    def __init__(self, win, rows, source):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(tr("Tabelle aus Auswahl"))
        self.resize(820, 520)
        lay = QVBoxLayout(self)
        nr, nc = len(rows), max((len(r) for r in rows), default=0)
        h = QLabel(tr("{} Zeilen × {} Spalten ({}). Zellen lassen sich vor dem Kopieren bearbeiten.").format(
            nr, nc, source))
        h.setWordWrap(True)
        h.setObjectName("hint")
        lay.addWidget(h)
        self.table = QTableWidget(nr, nc)
        for i, r in enumerate(rows):
            for j, v in enumerate(r):
                self.table.setItem(i, j, QTableWidgetItem(v))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.resizeColumnsToContents()
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Trennzeichen")))
        self.cb_sep = QComboBox()
        for sep, name in SEPS:
            self.cb_sep.addItem(name, sep)
        k = self.cb_sep.findData(win.settings.value("table_sep", ";"))
        self.cb_sep.setCurrentIndex(max(0, k))
        self.cb_sep.currentIndexChanged.connect(lambda _i: win.settings.setValue("table_sep", self.sep()))
        row.addWidget(self.cb_sep)
        row.addStretch()
        self.btn_copy = QPushButton(tr("Kopieren (CSV)"))
        self.btn_copy.setToolTip(tr("Tabelle als Text in die Zwischenablage. Mit Tabulator lässt sie sich direkt "
                                    "in Excel einfügen."))
        self.btn_copy.clicked.connect(self.copy)
        row.addWidget(self.btn_copy)
        self.btn_save = QPushButton(tr("Speichern …"))
        self.btn_save.clicked.connect(self.save)
        row.addWidget(self.btn_save)
        close = QPushButton(tr("Schließen"))
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def sep(self):
        return self.cb_sep.currentData()

    def rows(self):
        """Tabelle wie im Dialog (mit Bearbeitungen)."""
        t = self.table
        return [[(t.item(i, j).text() if t.item(i, j) else "") for j in range(t.columnCount())]
                for i in range(t.rowCount())]

    def text(self, newline="\n"):
        return te.to_csv(self.rows(), self.sep(), newline)

    def copy(self):
        QGuiApplication.clipboard().setText(self.text())
        self.win.statusBar().showMessage(tr("Tabelle kopiert ({} Zeilen)").format(self.table.rowCount()), 5000)

    def save(self):
        base = os.path.splitext(os.path.basename(self.win.path_a or self.win.path_b or "Tabelle"))[0] + "_Tabelle.csv"
        path = self.win._save_dialog(tr("Tabelle speichern"), tr("CSV (*.csv);;Text (*.txt)"), base)
        if not path:
            return None
        with open(path, "w", encoding="utf-8-sig", newline="") as f:     # mit BOM: Excel erkennt die Umlaute
            f.write(self.text("\r\n"))
        self.win.banner.show_msg(tr("Gespeichert: {}").format(path), "info", timeout=8)
        return path


class TableMixin:
    """Teil des Hauptfensters (wird in MainWindow eingemischt): Bereich > Mehr > Als Tabelle (CSV)."""

    def _table_side(self):
        """Seite, deren Zeichnung zu sehen ist: Neu ("B") in der Ansicht Neu, sonst Alt bzw. die einzelne Datei."""
        c = self.canvas
        if self.view_only or not (self.path_a and self.path_b):
            return "A" if self.path_a else "B"
        return "B" if c.mode in ("B", "N") or (c.mode == "Y" and c._side == "B") else "A"

    def _table_words(self, side, bbox):
        """Vorhandener Text im Bereich in Pixeln des Bereichs: (Textteile, Quelle) - exakt aus dem PDF, sonst schon
        gelesener Text (Hintergrund, Textsuche); (None, None), wenn erst gelesen werden muss."""
        x0, y0, x1, y1 = bbox
        rects = self.canvas.sel_rects or [bbox]
        path = self.path_a if side == "A" else self.path_b
        page = (self.sp_pa if side == "A" else self.sp_pb).value()

        def inside(items):
            out = []
            for it in items:
                r = self._to_view(side, it[:4])
                cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
                if any(q[0] <= cx <= q[2] and q[1] <= cy <= q[3] for q in rects):
                    out.append((r[0] - x0, r[1] - y0, r[2] - x0, r[3] - y0, it[4]))
            return out
        # PDF-Text nur, wenn das Bild der Datei entspricht (ohne Bearbeitung und Zuschnitt-Rahmen)
        if (path and path.lower().endswith(".pdf") and dv.available() and not getattr(self, "_edit_ver", 0)
                and self._frame_local() is None):
            try:
                words = dv.pdf_words(path, page)
            except Exception:                                  # noqa: BLE001 - dann eben Texterkennung
                words = []
            z = self.dpi_value() / 72.0
            got = inside([(w[0] * z, w[1] * z, w[2] * z, w[3] * z, w[4]) for w in words])
            if got:
                return got, tr("Text aus dem PDF")
        self._bg_text_poll()
        lines = self.cache.get(self._text_key(side)[0])
        if lines:
            got = inside(lines)
            if got:
                return got, tr("gelesener Text")
        return None, None

    def _table_gray(self, side, bbox):
        """Graubild des Bereichs (ohne Markierungen), ausserhalb der Rechtecke weiss."""
        plain = self.render_region(bbox, False, mode=side)
        gray = np.ascontiguousarray(dc.darkest_channel(plain)).copy()
        region = de.region_mask(self.canvas.sel_rects, bbox)
        gray[~region.astype(bool)] = 255
        return gray

    def area_table(self):
        """Tabelle im gewaehlten Bereich lesen (Zellraster aus Linien oder aus der Lage des Texts) und als CSV
        anbieten: Vorschau, kopieren, speichern."""
        bbox = self._area_bbox()
        if self.payload is None or bbox is None:
            return
        side = self._table_side()
        gray = self._table_gray(side, bbox)
        words, source = self._table_words(side, bbox)
        if words is None and not self.ensure_ocr(tr("Text der Tabelle zu lesen")):
            return

        def work(ctx):
            w, src = words, source
            if w is None:
                ctx.progress(0.1, tr("Texterkennung"))
                pad = 20
                big = cv2.copyMakeBorder(gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
                w = [(t[0] - pad, t[1] - pad, t[2] - pad, t[3] - pad, t[4]) for t in rep.ocr_any_orientation(big)]
                src = tr("Texterkennung")
            ctx.progress(0.9, tr("Zellen bestimmen"))
            return te.extract_table(w, gray), src

        def done(res):
            rows, src = res
            if not rows:
                self.banner.show_msg(tr("Im Bereich wurde kein Text gefunden."), "info", timeout=8)
                return
            self._table_dlg = TableDialog(self, rows, src)
            self._table_dlg.exec()
        self._run_job(work, tr("Lese Tabelle …"), done)

    def area_text(self):
        """Text im gewaehlten Bereich in Lesereihenfolge in die Zwischenablage - exakt aus dem PDF, sonst schon
        gelesener Text, sonst Texterkennung des Bereichs (in jeder Lage)."""
        bbox = self._area_bbox()
        if self.payload is None or bbox is None:
            return
        side = self._table_side()
        words, _src = self._table_words(side, bbox)
        if words is None and not self.ensure_ocr(tr("Text im Bereich zu lesen")):
            return
        gray = self._table_gray(side, bbox) if words is None else None

        def work(ctx):
            if words is not None:
                return words
            ctx.progress(0.1, tr("Texterkennung"))
            pad = 20
            big = cv2.copyMakeBorder(gray, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
            return [(t[0] - pad, t[1] - pad, t[2] - pad, t[3] - pad, t[4]) for t in rep.ocr_any_orientation(big)]

        def done(w):
            text = words_to_text(w)
            if not text:
                self.banner.show_msg(tr("Im Bereich wurde kein Text gefunden."), "info", timeout=8)
                return
            QApplication.clipboard().setText(text)
            self.statusBar().showMessage(tr("Text kopiert ({} Zeilen)").format(text.count("\n") + 1), 6000)
        self._run_job(work, tr("Lese Text …"), done)


def words_to_text(words):
    """Textteile (x0, y0, x1, y1, text) zu Zeilen: gleiche Hoehe = eine Zeile (links nach rechts), Zeilen von oben
    nach unten. Wort- und Zeilenfunde an derselben Stelle (PDF-Text liefert beides) nur einmal."""
    items = []
    for w in sorted(words, key=lambda t: -(t[2] - t[0])):         # ganze Zeilen vor ihren Woertern
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if any(o[0] - 1 <= cx <= o[2] + 1 and o[1] - 1 <= cy <= o[3] + 1 and w[4] in o[4] for o in items):
            continue
        if str(w[4]).strip():
            items.append(w)
    rows = []
    for w in sorted(items, key=lambda t: ((t[1] + t[3]) / 2, t[0])):
        cy, h = (w[1] + w[3]) / 2, max(1.0, w[3] - w[1])
        if rows and abs(rows[-1][0] - cy) < 0.5 * max(h, rows[-1][1]):
            rows[-1][2].append(w)
        else:
            rows.append([cy, h, [w]])
    return "\n".join(" ".join(str(t[4]).strip() for t in sorted(r[2], key=lambda t: t[0])) for r in rows)
