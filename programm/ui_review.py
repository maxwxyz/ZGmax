"""Hauptfenster: Pruefrundgang starten, Pruefung mit Freigabe abschliessen (Pruefprotokoll), Massaenderungs-Tabelle."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_project import file_sha256
from version import VERSION


class ReviewMixin:
    """Teil des Hauptfensters (wird in MainWindow eingemischt)."""

    # ----------------------------------------------------------------- Pruefrundgang
    def review_start(self):
        """Ein Klick statt drei: Aenderungen suchen (falls noch nicht geschehen), erste offene zeigen, Tasten erklaeren."""
        if not self.payload or self.view_only:
            QMessageBox.information(self, APP, tr("Bitte zuerst zwei Zeichnungen vergleichen."))
            return
        if not self.payload["regs_done"]:
            self._run_job(lambda log: self._ensure_regs(log, True), tr("Suche Änderungen …"),
                          lambda n: (self._regs_ready(), self._review_begin()))
            return
        self._review_begin()

    def _review_begin(self):
        self.act_right.setChecked(True)
        self.tabs.setCurrentWidget(self.tab_regs)
        self.act_overlays.setChecked(True)
        self.chk_regs.setChecked(True)
        if self.cb_filter.currentData() in ("all", "verschoben"):    # nur verschobene Teile sind nichts zu pruefen
            self.cb_filter.setCurrentIndex(self.cb_filter.findData("changes"))
        self.ed_reg_search.clear()
        regs = [r for r in self.payload["regs"] if r["typ"] != "verschoben"]
        if not regs:
            self.banner.show_msg(tr("Keine Änderungen gefunden – die Zeichnungen stimmen überein."), "info",
                                 action=(tr("Prüfung abschließen …"), self.review_finish), timeout=20)
            return
        self.canvas.selected = None
        self.review_step(1)
        self._review_hint()

    def _review_hint(self):
        regs = [r for r in (self.payload or {}).get("regs") or [] if r["typ"] != "verschoben"]
        n_open = sum(1 for r in regs if rep.reg_status(r) == "offen")
        if n_open:
            self.banner.show_msg(tr("Prüfen: noch {} von {} offen.   N = nächste · G = geprüft · X = abgelehnt · "
                                    "C = Kommentar · P = vorige").format(n_open, len(regs)), "info",
                                 action=(tr("Prüfung abschließen …"), self.review_finish))
        else:
            self.banner.show_msg(tr("Alle {} Änderungen sind bearbeitet.").format(len(regs)), "info",
                                 action=(tr("Prüfung abschließen …"), self.review_finish))

    # ----------------------------------------------------------------- Pruefprotokoll mit Freigabe
    def _protocol_key(self):
        return self._page_key()

    def current_protocol(self):
        """Juengstes Pruefprotokoll dieser Seite (oder None)."""
        key = self._protocol_key()
        recs = [p for p in getattr(self, "protocols", []) if p.get("page") == key]
        return recs[-1] if recs else None

    def review_finish(self):
        """Pruefung abschliessen: Pruefer, Ergebnis und Bemerkung; der Stand aller Aenderungen wird als Protokoll mit
        Pruefsumme im Projekt gespeichert und auf Wunsch als PDF."""
        pl = self.payload
        if not pl or self.view_only:
            return
        if not pl["regs_done"]:
            self.review_start()
            return
        regs = [r for r in pl["regs"] if r["typ"] != "verschoben"]
        st = [rep.reg_status(r) for r in regs]
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Prüfung abschließen"))
        dlg.setMinimumWidth(460)
        form = QFormLayout(dlg)
        info = QLabel(tr("{} Änderungen: {} geprüft, {} abgelehnt, {} offen").format(
            len(regs), st.count("ok"), st.count("abgelehnt"), st.count("offen")))
        info.setWordWrap(True)
        form.addRow(info)
        if st.count("offen"):
            warn = QLabel(tr("Es sind noch Änderungen offen. Sie werden als „offen“ ins Protokoll übernommen."))
            warn.setObjectName("warn")
            warn.setWordWrap(True)
            form.addRow(warn)
        ed_name = QLineEdit(self._user_name(ask=False))
        ed_name.setPlaceholderText(tr("Vor- und Nachname"))
        cb = QComboBox()
        for k, v in rep.PROTOCOL_RESULTS.items():
            cb.addItem(v, k)
        if st.count("abgelehnt"):
            cb.setCurrentIndex(cb.findData("cond"))
        ed_rem = QPlainTextEdit()
        ed_rem.setPlaceholderText(tr("z. B. Auflagen, Hinweise an den Lieferanten"))
        ed_rem.setFixedHeight(80)
        chk_pdf = QCheckBox(tr("Protokoll als PDF speichern"))
        chk_pdf.setChecked(True)
        form.addRow(tr("Prüfer:"), ed_name)
        form.addRow(tr("Ergebnis:"), cb)
        form.addRow(tr("Bemerkung:"), ed_rem)
        form.addRow(chk_pdf)
        note = QLabel(tr("Das Protokoll hält Prüfer, Zeitpunkt und den Stand jeder Änderung fest. Eine Prüfsumme zeigt "
                         "später, ob es verändert wurde (keine qualifizierte elektronische Signatur)."))
        note.setObjectName("hint")
        note.setWordWrap(True)
        form.addRow(note)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Abschließen"))
        bb.accepted.connect(lambda: dlg.accept() if ed_name.text().strip() else ed_name.setFocus())
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = ed_name.text().strip()
        self.settings.setValue("user_name", name)
        rec = self._make_protocol(name, cb.currentData(), ed_rem.toPlainText().strip())
        self.__dict__.setdefault("protocols", []).append(rec)
        self._dirty = True
        self._update_title()
        self._update_protocol_label()
        msg = tr("Prüfung abgeschlossen: {} ({})").format(rep.PROTOCOL_RESULTS[rec["result"]], name)
        if chk_pdf.isChecked():
            path = self._save_dialog(tr("Prüfprotokoll speichern"), tr("PDF (*.pdf)"), "pruefprotokoll.pdf")
            if path:
                rep.build_protocol_pdf(path, rec)
                self._saved(path)
        self.banner.show_msg(msg + tr(" – im Projekt gespeichert (Projekt speichern nicht vergessen)."), "info",
                             timeout=12)

    def _make_protocol(self, name, result, remark):
        files = []
        for role, p in (("A", self.path_a), ("B", self.path_b)):
            if p and os.path.isfile(p):
                files.append(dict(role=role, name=os.path.basename(p), sha256=file_sha256(p)))
        return rep.make_protocol(self.payload["regs"], name, result, remark, files, self._protocol_key(), VERSION)

    def _update_protocol_label(self):
        """Hinweis in der Aenderungsliste: zuletzt abgeschlossen von ... (und ob der Stand seitdem geaendert wurde)."""
        if not hasattr(self, "lbl_protocol"):
            return
        rec = self.current_protocol()
        pl = self.payload
        if rec is None or not pl or not pl.get("regs_done"):
            self.lbl_protocol.hide()
            return
        try:
            when = dt.datetime.fromisoformat(rec["date"]).strftime("%d.%m.%Y %H:%M")
        except (KeyError, ValueError):
            when = rec.get("date", "")
        txt = tr("✔ {} – {}, {}").format(rep.PROTOCOL_RESULTS.get(rec["result"], rec["result"]), rec["reviewer"], when)
        bad = False
        if not rep.protocol_valid(rec):
            txt += tr("  ·  Protokoll wurde nachträglich verändert!")
            bad = True
        elif not rep.protocol_matches(rec, pl["regs"]):
            txt += tr("  ·  Prüfstand seitdem geändert – erneut abschließen")
            bad = True
        self.lbl_protocol.setText(txt)
        self.lbl_protocol.setObjectName("warn" if bad else "ok")
        self.lbl_protocol.style().unpolish(self.lbl_protocol)
        self.lbl_protocol.style().polish(self.lbl_protocol)
        self.lbl_protocol.show()

    def show_protocols(self):
        """Alle Pruefprotokolle des Projekts mit Pruefung der Pruefsumme; einzelne als PDF speichern."""
        recs = list(getattr(self, "protocols", []))
        if not recs:
            QMessageBox.information(self, APP, tr("Noch keine Prüfung abgeschlossen (Vergleichen → Prüfung "
                                                  "abschließen …)."))
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Prüfprotokolle"))
        dlg.resize(720, 360)
        lay = QVBoxLayout(dlg)
        tbl = QTableWidget(len(recs), 5)
        tbl.setHorizontalHeaderLabels([tr("Datum"), tr("Prüfer"), tr("Ergebnis"), tr("Seite"), tr("Prüfsumme")])
        tbl.verticalHeader().hide()
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for i, r in enumerate(recs):
            ok = rep.protocol_valid(r)
            vals = [r.get("date", "")[:16].replace("T", " "), r.get("reviewer", ""),
                    rep.PROTOCOL_RESULTS.get(r.get("result"), r.get("result", "")), str(r.get("page", "")),
                    tr("in Ordnung") if ok else tr("verändert!")]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 4:
                    it.setForeground(QColor("#16a34a" if ok else "#dc2626"))
                tbl.setItem(i, j, it)
        tbl.selectRow(len(recs) - 1)
        lay.addWidget(tbl)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        b = bb.addButton(tr("Als PDF speichern …"), QDialogButtonBox.ButtonRole.ActionRole)

        def save():
            row = tbl.currentRow()
            if 0 <= row < len(recs):
                path = self._save_dialog(tr("Prüfprotokoll speichern"), tr("PDF (*.pdf)"), "pruefprotokoll.pdf")
                if path:
                    rep.build_protocol_pdf(path, recs[row])
                    self._saved(path)
        b.clicked.connect(save)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.exec()

    # ----------------------------------------------------------------- Massaenderungs-Tabelle
    def export_dim_table(self):
        """Massaenderungen als Tabelle (PDF oder CSV): alt -> neu, Toleranz alt/neu, Position, Status. Sind die Masse
        noch nicht gelesen, wird das zuerst erledigt."""
        pl = self.payload
        if not pl or self.view_only:
            QMessageBox.information(self, APP, tr("Bitte zuerst zwei Zeichnungen vergleichen."))
            return
        if not (pl["regs_done"] and any(r.get("dim") for r in pl["regs"])):
            self.run_dims(then=lambda n: self._write_dim_table() if n else QMessageBox.information(
                self, APP, tr("Keine geänderten Maße gefunden.")))
            return
        self._write_dim_table()

    def _write_dim_table(self):
        path = self._save_dialog(tr("Maßänderungen speichern"), tr("PDF (*.pdf);;CSV (*.csv)"), "massaenderungen.pdf")
        if not path:
            return
        rows = rep.dim_rows(self.payload["regs"], self.canvas.mm_px,
                            self.sp_pa.value() if max(self.n_pages_a, self.n_pages_b) > 1 else None)
        names = (os.path.basename(self.path_a), os.path.basename(self.path_b))
        if path.lower().endswith(".csv"):
            rep.write_dim_csv(path, rows)
        else:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            rep.build_dim_report(path, rows, *names, info=f"{APP} {VERSION}")
        self._saved(path)
