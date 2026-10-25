"""Hauptfenster: Aenderungsliste, Texterkennung."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_widgets import ApprovalDialog


class RegionsMixin:
    """Teil des Hauptfensters (wird in MainWindow eingemischt)."""

    # --- Aenderungsliste (nur auf Knopfdruck)
    def _ensure_regs(self, log, force=False):
        pl = self.payload
        if force or not pl["regs_done"]:
            log(tr("Suche \u00c4nderungen \u2026"))
            manual = [r for r in pl["regs"] if r.get("manuell")]
            auto = rep.find_regions(pl["res"], merge=max(1, int(self.s_group.value())))
            nr = len(auto)
            for r in manual:                       # eigene Bereiche bleiben erhalten
                nr += 1
                r["nr"] = nr
                auto.append(r)
            pl["regs"][:] = auto
            pl["regs_done"] = True
        return len(pl["regs"])

    def _reg_delete(self):
        pl = self.payload
        rows = self.table.selectionModel().selectedRows() if pl else []
        if not rows:
            self._log(tr("Keine Zeile in der \u00c4nderungsliste gew\u00e4hlt."))
            return
        nrs = {int(self.table.item(r.row(), 1).text()) for r in rows}
        pl["regs"][:] = [r for r in pl["regs"] if r["nr"] not in nrs]
        self.canvas.selected = None
        self._fill_table()
        self._log(tr("{} Einträge gelöscht").format(len(nrs)))

    def _reg_clear(self):
        pl = self.payload
        if not pl or not pl["regs"]:
            return
        if QMessageBox.question(self, APP, "Alle Eintr\u00e4ge der \u00c4nderungsliste l\u00f6schen?\n"
                                "(\u201e\u00c4nderungen suchen\u201c erstellt die automatische Liste jederzeit neu.)"
                                ) != QMessageBox.StandardButton.Yes:
            return
        pl["regs"].clear()
        pl["regs_done"] = True                     # leer lassen, nicht automatisch neu f\u00fcllen
        self.canvas.selected = None
        self._fill_table()
        self.canvas.update()

    def _region_drawn(self, x, y, w, h):
        pl = self.payload
        if not pl:
            return
        names = {tr("ge\u00e4ndert"): "geaendert", tr("neu"): "neu", tr("entfernt"): "entfernt"}
        item, ok = QInputDialog.getItem(self, tr("\u00c4nderung markieren"), tr("Art der \u00c4nderung:"), list(names), 0, False)
        self._set_tool("hand")
        if not ok:
            return
        res = pl["res"]
        sl = (slice(y, y + h), slice(x, x + w))
        regs = pl["regs"]
        nr = max((r["nr"] for r in regs), default=0) + 1
        regs.append(dict(typ=names[item], px_a=int(res.oa[sl].sum()), px_b=int(res.ob[sl].sum()), px_moved=0,
                         x=int(x), y=int(y), w=int(w), h=int(h), nr=nr, text_a="", text_b="", checked=False,
                         dim="", dim_kind="", manuell=True))
        pl["regs_done"] = True
        self.act_overlays.setChecked(True)
        self.chk_regs.setChecked(True)
        self.cb_filter.setCurrentIndex(0)
        self._reg_edit_dialog(regs[-1], tr("\u00c4nderung beschreiben"))
        self._fill_table()
        self._select_region_nr(nr)

    def _reg_edit_dialog(self, r, title=tr("\u00c4nderung bearbeiten")):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        form = QFormLayout(dlg)
        ea, eb, ed = QLineEdit(r.get("text_a", "")), QLineEdit(r.get("text_b", "")), QLineEdit(r.get("desc", ""))
        ea.setPlaceholderText(tr("z. B. 25 H7"))
        eb.setPlaceholderText(tr("z. B. 30 H7"))
        ed.setPlaceholderText(tr("z. B. Bohrung vergr\u00f6\u00dfert"))
        form.addRow(tr("Text A (alt):"), ea)
        form.addRow(tr("Text B (neu):"), eb)
        form.addRow(tr("Beschreibung:"), ed)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            r["text_a"], r["text_b"], r["desc"] = ea.text().strip(), eb.text().strip(), ed.text().strip()
            r["dim"] = ""
            if r["text_a"] and r["text_b"]:
                rep.dim_changes([r], lambda *_: None)
            return True
        return False

    def _reg_row_edit(self, row, _col=0):
        it = self.table.item(row, 0)
        if it is None or not self.payload:
            return
        nr = it.data(Qt.ItemDataRole.UserRole)
        for r in self.payload["regs"]:
            if r["nr"] == nr:
                if self._reg_edit_dialog(r):
                    self._fill_table()
                    self._select_region_nr(nr)
                break

    def _group_changed(self):
        if self.payload and self.payload["regs_done"]:
            self.group_timer.start(500)

    def _regroup(self):
        """Gruppierung geaendert: Liste neu aufbauen (Haken und gelesene Texte gehen dabei verloren)."""
        if not (self.payload and self.payload["regs_done"]):
            return
        if self.running:
            self.group_timer.start(500)
            return
        self.payload["regs_done"] = False
        self.canvas.selected = None
        self.find_regs()

    def run_dims(self):
        if not self.payload:
            QMessageBox.information(self, APP, tr("Bitte zuerst vergleichen."))
            return
        pdf = bool(self.path_a and self.path_b and self.path_a.lower().endswith(".pdf")
                   and self.path_b.lower().endswith(".pdf") and dv.available())
        if not pdf and not self.ensure_ocr(tr("Ma\u00dfzahlen in Bildern zu lesen")):
            return
        pl, pa, pb = self.payload, self.path_a, self.path_b
        na, nb, dpi = self.sp_pa.value(), self.sp_pb.value(), self.dpi_value()

        def work(log):
            self._ensure_regs(log)
            wa, wb = (dv.pdf_words(pa, na), dv.pdf_words(pb, nb)) if pdf else ([], [])
            if wa or wb:
                log(tr("Ma\u00dfzahlen aus dem PDF-Text \u2026"))
                dv.fill_text(pl["regs"], wa, wb, dpi, log)
            elif rep.ocr_available():
                log(tr("Ma\u00dfzahlen per OCR \u2026"))
                rep.text_diff(pl["res"], pl["regs"], log)
            else:
                log(tr("Weder PDF-Text noch OCR verf\u00fcgbar."))
            return rep.dim_changes(pl["regs"], log)

        def done(n):
            self._fill_table()
            self._busy(False, tr("{} Maßanderungen gefunden").format(n))
            if n:
                self.cb_filter.setCurrentIndex(self.cb_filter.findData("dims"))
        self._run_job(work, tr("Vergleiche Ma\u00dfzahlen \u2026"), done)

    def find_regs(self):
        if not self.payload:
            QMessageBox.information(self, APP, tr("Bitte zuerst vergleichen."))
            return
        self._run_job(lambda log: self._ensure_regs(log, True), tr("Suche \u00c4nderungen \u2026"),
                      lambda n: self._regs_ready())

    def _regs_ready(self):
        self.act_overlays.setChecked(True)
        self.chk_regs.setChecked(True)
        self.tabs.setCurrentWidget(self.tab_regs)
        if self.payload["regs"] and not self.act_right.isChecked() and not getattr(self, "_right_auto_done", False):
            self.act_right.setChecked(True)            # beim ersten Mal die Liste zeigen: dort geht es weiter
            self._right_auto_done = True
        self._fill_table()
        self._busy(False, tr("{} Änderungen gefunden").format(len(self.payload['regs'])))

    def _filter_types(self):
        t = self.cb_filter.currentData()
        if t in ("dims", "open", "changes", "text"):
            return {"entfernt", "neu", "geaendert"}  # nur verschobene Teile sind keine echte Aenderung
        if t == "all":
            return None
        return {t}

    def _filter_spec(self):
        """Aktueller Listenfilter (fuer Hintergrundarbeiten, die keine Widgets lesen duerfen)."""
        return self.cb_filter.currentData(), self._filter_types()

    @staticmethod
    def filter_regs(regs, spec):
        f, types = spec
        return [r for r in regs if (not types or r["typ"] in types) and (f != "dims" or r.get("dim"))
                and (f != "text" or rep.text_changed(r)) and (f != "open" or rep.reg_status(r) == "offen")]

    def _shown_regs(self):
        """Die Aenderungen, die nach dem Filter in der Liste stehen (gleiche Auswahl fuer Liste, PDF-Bericht, CSV und
        PDF mit Anmerkungen)."""
        pl = self.payload
        return self.filter_regs((pl or {}).get("regs") or [], self._filter_spec())

    def _fill_table(self):
        self._update_review_enabled()
        self._regs_listed = self._shown_regs()             # fuer Ausgaben aus dem Hintergrund (ohne Widgets)
        pl = self.payload
        regs = pl["regs"] if pl else []
        self.canvas.visible_types = self._filter_types()
        f = self.cb_filter.currentData()                   # Masse/offen: auch im Bild nur diese Rahmen
        self.canvas.visible_nrs = {r["nr"] for r in self._shown_regs()} if f in ("dims", "open", "text") else None
        mm = self.canvas.mm_px
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for r in self._shown_regs():
            row = self.table.rowCount()
            self.table.insertRow(row)
            st = rep.reg_status(r)
            chk = QTableWidgetItem("\u25cf " + rep.STATUS_LABEL[st])
            chk.setForeground(QColor(rep.STATUS_COLORS[st]))
            chk.setData(Qt.ItemDataRole.UserRole, r["nr"])
            self.table.setItem(row, 0, chk)
            self.table.setItem(row, 1, QTableWidgetItem(str(r["nr"])))
            self.table.setItem(row, 2, QTableWidgetItem(TYPE_SHOW.get(r["typ"], r["typ"])))
            self.table.setItem(row, 3, QTableWidgetItem(f"{r['x'] * mm:.0f} / {r['y'] * mm:.0f}"))
            txt = f"{r['text_a']} \u2192 {r['text_b']}" if (r["text_a"] or r["text_b"]) else ""
            if r.get("dim"):
                txt = tr("Maß {}").format(r['dim'])
            if r.get("desc"):
                txt = (txt + " | " if txt else "") + r["desc"]
            if r.get("comment"):
                txt = (txt + " | " if txt else "") + "\u201e" + r["comment"] + "\u201c"
            self.table.setItem(row, 4, QTableWidgetItem(txt))
        self.table.blockSignals(False)
        if not pl:
            self.lbl_summary.setText(tr("Erst zwei Zeichnungen vergleichen."))
        elif not pl["regs_done"]:
            self.lbl_summary.setText(tr("Noch keine Liste. \u201e\u00c4nderungen suchen\u201c nummeriert alle Unterschiede "
                                     "und markiert sie im Bild. Das geschieht nur auf Wunsch, damit der Vergleich "
                                     "schneller l\u00e4dt."))
        else:
            cnt = {k: sum(1 for r in regs if r["typ"] == k) for k in rep.TYPE_LABEL}
            st = [rep.reg_status(r) for r in regs]
            done = tr("{} geprüft, {} abgelehnt, {} offen").format(st.count('ok'), st.count('abgelehnt'), st.count('offen'))
            nd = sum(1 for r in regs if r.get("dim"))
            s = (tr("{} Bereiche: {} entfernt, {} neu, {} geändert, {} verschoben.\nPrüfung: {}  (N = nächste, G = geprüft, X = abgelehnt)").format(len(regs), cnt['entfernt'], cnt['neu'], cnt['geaendert'], cnt['verschoben'], done))
            if nd:
                s += tr("\nDavon {} mit geändertem Maß (Filter „Maße“).").format(nd)
            if self.index_info:
                i = self.index_info
                s += tr("\nIndex: A = {}, B = {}.  ").format(i['index_a'], i['index_b']) + " ".join(i["notes"])
            self.lbl_summary.setText(s)
        self.canvas.update()

    def _reg(self, nr):
        return next((r for r in self.payload["regs"] if r["nr"] == nr), None) if self.payload else None

    def _table_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:                                       # Auswahl in der Liste aufgehoben: auch im Bild
            if self.canvas.selected is not None:
                self.canvas.selected = None
                self.canvas.update()
            return
        r = self._reg(int(self.table.item(rows[0].row(), 1).text()))
        if r:
            self.canvas.selected = r["nr"]
            self.canvas.center_on(r)

    def _table_checked(self, item):
        if item.column() != 0:
            return
        r = self._reg(item.data(Qt.ItemDataRole.UserRole))
        if r:
            r["checked"] = item.checkState() == Qt.CheckState.Checked
            self.canvas.update()
            regs = self.payload["regs"]
            txt = self.lbl_summary.text().split("Gepr\u00fcft:")[0]
            self.lbl_summary.setText(txt + tr("Geprüft: {}").format(sum(1 for x in regs if x['checked'])))

    def _select_region_nr(self, nr):
        if nr < 0:                                         # abwaehlen (Klick ins Leere, Esc)
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
            self.canvas.selected = None
            self.canvas.update()
            return
        self.tabs.setCurrentWidget(self.tab_regs)
        for row in range(self.table.rowCount()):
            if int(self.table.item(row, 1).text()) == nr:
                self.table.selectRow(row)
                return
        self.canvas.selected = nr
        self.canvas.update()

    # --- OCR
    def _need_ocr(self):
        if not self.payload:
            QMessageBox.information(self, APP, tr("Bitte zuerst vergleichen."))
            return False
        return self.ensure_ocr(tr("Text zu lesen"))

    def ensure_ocr(self, purpose):
        """Texterkennung verfuegbar? Sonst Installation anbieten (nur im Python-Betrieb; die App enthaelt sie)."""
        if rep.ocr_available():
            return True
        if FROZEN:
            QMessageBox.information(self, APP, tr("Diese Programmversion enth\u00e4lt keine Texterkennung (OCR)."))
            return False
        if QMessageBox.question(self, APP, f"Um {purpose}, braucht das Programm die Texterkennung (OCR). Sie ist "
                                "nicht installiert.\n\nJetzt installieren? (Internet n\u00f6tig, ca. 60 MB, "
                                "dauert etwa eine Minute)") != QMessageBox.StandardButton.Yes:
            return False

        def work(ctx):
            import importlib
            ctx.progress(0.1, tr("Installiere Texterkennung"))
            in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
            cmd = [sys.executable, tr("-m"), "pip", "install"] + ([] if in_venv else [tr("--user")]) + \
                  [tr("rapidocr-onnxruntime==1.2.3")]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                raise dc.DiffError(tr("Installation fehlgeschlagen:\n") + (r.stderr or r.stdout)[-800:])
            importlib.invalidate_caches()
            import site
            if not in_venv and site.getusersitepackages() not in sys.path:
                sys.path.append(site.getusersitepackages())
            return rep.ocr_available()

        def done(ok):
            self.banner.show_msg(tr("Texterkennung installiert. Bitte die Funktion noch einmal w\u00e4hlen.") if ok else
                                 tr("Texterkennung installiert, aber noch nicht geladen. Bitte das Programm neu starten."),
                                 "info", timeout=20)
        self._run_job(work, tr("Installiere Texterkennung \u2026"), done)
        return False

    def run_index(self):
        if not self._need_ocr():
            return
        pl = self.payload

        def work(log):
            self._ensure_regs(log)
            return rep.index_check(pl["res"], pl["regs"], log)

        def ok(info):
            self.index_info = info
            self._fill_table()
            self._busy(False, tr("Index gepr\u00fcft"))
        self._run_job(work, tr("Pr\u00fcfe Index \u2026"), ok)
