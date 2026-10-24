"""Hauptfenster: Anmerkungen."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_widgets import ApprovalDialog
import diffxfdf as dx


class AnnotationsMixin:
    """Teil des Hauptfensters (wird in MainWindow eingemischt)."""

    # --- Anmerkungen
    # Farbe/Groesse in der Optionszeile: Ist eine Markierung gewaehlt, gelten sie fuer diese; sonst sind sie die
    # Vorgabe fuer neue Markierungen (canvas.ann_color / ann_size). Auswaehlen aendert die Vorgabe nicht.
    def _set_color_btn(self, c, default=True):
        self.btn_color.setStyleSheet(f"QPushButton {{ background: {c}; border: 1px solid {THEME['border2']}; "
                                     f"border-radius: 6px; padding: 6px 14px; color: white; font-weight: 600; }}")
        self.btn_color.setProperty("shown_color", c)
        if default:
            self.canvas.ann_color = c

    def _pick_color(self):
        a = self._sel()
        c = QColorDialog.getColor(QColor(a["color"] if a else self.canvas.ann_color), self, tr("Farbe"))
        if c.isValid():
            if a:
                for b in self._sel_all():                   # Mehrfachauswahl: alle gewaehlten
                    b["color"] = c.name()
                self._set_color_btn(c.name(), default=False)
                self.canvas.update()
                self._commit()
            else:
                self._set_color_btn(c.name())

    def _sel(self):
        i = self.canvas.ann_selected
        return self.anns[i] if i is not None and 0 <= i < len(self.anns) else None

    def _sel_all(self):
        return [self.anns[i] for i in sorted(self.canvas.selected_anns())]

    def _ann_size(self):
        a = self._sel()
        if a:
            for b in self._sel_all():
                b["size"] = self.s_asize.value()
            self._commit()
        else:
            self.canvas.ann_size = self.s_asize.value()
        self.canvas.update()

    def _ann_label(self, a):
        t = a["type"]
        if t == "number":
            return tr("Nummer {}").format(a['nr'])
        if t == "text":
            return tr("Text: ") + a["text"].replace("\n", " ")[:32]
        if t == "approval":
            return tr("Stempel: ") + " / ".join(a["text"].split("\n")[:2])
        if t == "measure":
            return f"{rep.MEASURE_KINDS.get(a.get('kind'), 'Ma\u00df')}: {rep.measure_text(a, self.canvas.mm_px)}"
        lbl = {"rect": tr("Rahmen"), "cloud": tr("Wolke"), "highlight": tr("Marker"), "arrow": tr("Pfeil"), "line": tr("Linie")}.get(t, t)
        if a.get("comment"):
            lbl += ": " + a["comment"].replace("\n", " ")[:40]
        if a.get("author"):
            lbl += f"  ({a['author']})"
        return lbl

    def _ann_refresh(self, select=None):
        self.canvas.ann_multi = set()
        self.list_anns.blockSignals(True)
        self.list_anns.clear()
        for a in self.anns:
            self.list_anns.addItem(self._ann_label(a))
        ok = select is not None and 0 <= select < len(self.anns)
        if ok:
            self.list_anns.setCurrentRow(select)
        self.list_anns.blockSignals(False)
        self.canvas.ann_selected = select if ok else None
        nrs = [a["nr"] for a in self.anns if a["type"] == "number"]
        self.sp_stamp.blockSignals(True)
        self.sp_stamp.setValue(max(nrs) + 1 if nrs else 1)
        self.sp_stamp.blockSignals(False)
        self.next_nr = self.sp_stamp.value()
        self._sync_ann_controls()
        if hasattr(self, "options_bar"):
            self._update_options()
        self.canvas.update()

    def _sync_ann_controls(self):
        """Optionszeile zeigt die gewaehlte Markierung, sonst die Vorgabe fuer neue."""
        a = self._sel()
        self.s_asize.set_silent(a["size"] if a else self.canvas.ann_size)
        self._set_color_btn(a["color"] if a else self.canvas.ann_color, default=False)

    def _ann_created(self, a):
        self.anns.append(a)
        self._ann_refresh(len(self.anns) - 1)
        self._commit()
        if a["type"] == "measure" and a.get("kind") == "dist" and getattr(self, "_calib_pending", False):
            QTimer.singleShot(0, lambda: self._calibrate(math.hypot(a["x2"] - a["x"], a["y2"] - a["y"])))
        self.tabs.setCurrentIndex(1)
        if a["type"] not in ("number", "measure"):
            self._set_tool("hand")

    def _place(self, tool, x, y):
        """Text, Nummer oder Freigabe setzen (ggf. mit Eingabedialog)."""
        base = dict(x=x, y=y, x2=x, y2=y, text="", nr=0, color=self.canvas.ann_color, size=self.canvas.ann_size)
        if tool == "number":
            self._ann_created(dict(base, type="number", nr=self.next_nr))
        elif tool == "text":
            txt, ok = QInputDialog.getMultiLineText(self, tr("Text einf\u00fcgen"), tr("Anmerkung:"), "")
            if ok and txt.strip():
                self._ann_created(dict(base, type="text", text=txt.strip()))
            else:
                self._set_tool("hand")
        elif tool == "approval":
            t = self._approval_text("")
            if t:
                self._ann_created(dict(base, type="approval", text=t))
            else:
                self._set_tool("hand")

    def _approval_text(self, old):
        lines = old.split("\n") if old else []
        name = lines[1] if len(lines) > 1 else self.settings.value("approval_name", "")
        date = lines[2] if len(lines) > 2 else dt.date.today().strftime("%d.%m.%Y")
        dlg = ApprovalDialog(self, lines[0] if lines else tr("FREIGEGEBEN"), name, date)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        self.settings.setValue("approval_name", dlg.ed_name.text().strip())
        return dlg.text()

    def _ann_selected(self, i):
        self._ann_refresh(i if i >= 0 else None)
        if i >= 0:
            self.tabs.setCurrentIndex(1)

    def _ann_changed(self):
        i = self.canvas.ann_selected
        if i is not None and 0 <= i < len(self.anns):
            it = self.list_anns.item(i)
            if it:
                it.setText(self._ann_label(self.anns[i]))
        self._sync_ann_controls()
        self._commit()

    def _ann_multi_selected(self, rows):
        """Mehrfachauswahl im Bild (Strg/Umschalt + Klick, Umschalt + Rahmen) in die Liste uebernehmen."""
        self.list_anns.blockSignals(True)
        self.list_anns.clearSelection()
        for r in rows:
            it = self.list_anns.item(r)
            if it:
                it.setSelected(True)
        if rows:
            self.list_anns.setCurrentRow(rows[-1], QItemSelectionModel.SelectionFlag.NoUpdate)
        self.list_anns.blockSignals(False)
        if rows:
            self.tabs.setCurrentIndex(1)
        self._sync_ann_controls()
        self._update_options()
        self.canvas.update()

    def _ann_list_selection(self):
        rows = sorted(self.list_anns.row(it) for it in self.list_anns.selectedItems())
        if len(rows) <= 1:
            self.canvas.ann_multi = set()
            self._ann_row(rows[0] if rows else -1)
        else:
            self.canvas.ann_multi = set(rows)
            cur = self.list_anns.currentRow()
            self.canvas.ann_selected = cur if cur in rows else rows[-1]
            self._sync_ann_controls()
            self.canvas.update()
        self._update_options()

    def _ann_row(self, row):
        self.canvas.ann_selected = row if row >= 0 else None
        if row >= 0:
            self.canvas.center_box(*rep.ann_bounds(self.canvas.shape, self.anns[row]))
            self._sync_ann_controls()
        self.canvas.update()

    def _ann_edit(self, i):
        if i is None or not (0 <= i < len(self.anns)):
            return
        a = self.anns[i]
        if a["type"] == "text":
            txt, ok = QInputDialog.getMultiLineText(self, tr("Text \u00e4ndern"), tr("Anmerkung:"), a["text"])
            if ok and txt.strip():
                a["text"] = txt.strip()
        elif a["type"] == "number":
            n, ok = QInputDialog.getInt(self, tr("Nummer \u00e4ndern"), tr("Nummer:"), a["nr"], 1, 9999)
            if ok:
                a["nr"] = n
        elif a["type"] == "approval":
            t = self._approval_text(a["text"])
            if t:
                a["text"] = t
        else:
            self._pick_color()
        self._ann_refresh(i)
        self._commit()

    def _ann_duplicate(self):
        a = self._sel()
        if a:
            b = copy.deepcopy(a)
            off = 40 * rep.ann_unit(self.canvas.shape) / 2
            b["x"] += off
            b["x2"] += off
            b["y"] += off
            b["y2"] += off
            if b.get("pts"):
                b["pts"] = [[q[0] + off, q[1] + off] for q in b["pts"]]
            if b["type"] == "number":
                b["nr"] = self.next_nr
            self.anns.append(b)
            self._ann_refresh(len(self.anns) - 1)
            self._commit()

    def _ann_delete(self):
        idx = sorted(self.canvas.selected_anns(), reverse=True)
        if idx:
            for i in idx:
                del self.anns[i]
            self._ann_refresh(None)
            self._commit()
            if len(idx) > 1:
                self.statusBar().showMessage(tr("{} Markierungen gelöscht (Rückgängig: Strg+Z)").format(len(idx)), 5000)

    def _ann_clear(self):
        if self.anns and QMessageBox.question(self, APP, tr("Alle {} Markierungen löschen? (Rückgängig mit Strg+Z)").format(
                len(self.anns))) == QMessageBox.StandardButton.Yes:
            self.anns.clear()
            self._ann_refresh(None)
            self._commit()

    def _ann_context(self, i, pos):
        m = QMenu(self)
        a = self.anns[i]
        if a["type"] in ("text", "number", "approval"):
            m.addAction(tr("Bearbeiten\u2026"), lambda: self._ann_edit(i))
        m.addAction(tr("Farbe\u2026"), self._pick_color)
        m.addAction(tr("Duplizieren"), self._ann_duplicate)
        m.addSeparator()
        m.addAction(tr("L\u00f6schen"), self._ann_delete)
        m.exec(pos)

    def ann_save(self):
        path = self._save_dialog(tr("Anmerkungen speichern"), tr("Anmerkungen (*.json)"), "anmerkungen.json")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"version": 3, "coords": "global", "annotations": self._state()["anns"]},
                          f, ensure_ascii=False, indent=1)
            self._log(tr("Anmerkungen gespeichert: {}").format(path))

    def ann_load(self):
        d = self.settings.value("outdir", "")
        path, _ = QFileDialog.getOpenFileName(self, tr("Anmerkungen laden"), d, tr("Anmerkungen (*.json)"))
        if path:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.anns[:] = rep.upgrade_annotations(data.get("annotations", []))
            if data.get("coords") == "global":
                for a in self.anns:
                    shift_ann(a, -self.origin[0], -self.origin[1])
            self._ann_refresh(None)
            self._commit()
            self._log(tr("{} Anmerkungen geladen").format(len(self.anns)))

    # --- Kommentare austauschen (XFDF / PDF-Anmerkungen)
    def _sheet_geometry(self, side):
        """(k Pixel je Punkt, Seitenhoehe in Punkt) fuer Datei A oder B der aktuellen Seite."""
        path = self.path_a if side == "A" else self.path_b
        page = (self.sp_pa if side == "A" else self.sp_pb).value()
        k = self.dpi_value() / 72.0
        if path and path.lower().endswith(".pdf") and dv.available():
            import pymupdf
            with pymupdf.open(path) as d:
                return k, d[max(0, min(page, d.page_count) - 1)].rect.height
        g = self.cache.get("g_" + path) if path else None
        h_px = g.shape[0] if g is not None else self.canvas.shape[0]
        return k, h_px / k

    def import_comments(self):
        if self.payload is None:
            QMessageBox.information(self, APP, tr("Bitte zuerst eine Zeichnung \u00f6ffnen."))
            return
        d = self.settings.value("outdir", os.path.dirname(self.path_a or ""))
        path, _ = QFileDialog.getOpenFileName(self, tr("Kommentare einlesen"), d,
                                              tr("Kommentare (*.xfdf *.pdf);;XFDF (*.xfdf);;PDF mit Kommentaren (*.pdf)"))
        if not path:
            return
        side = "A"
        if self.path_a and self.path_b and not self.view_only:
            stem = os.path.splitext(os.path.basename(path))[0].lower()
            guess_b = os.path.splitext(os.path.basename(self.path_b))[0].lower() in stem
            box = QMessageBox(self)
            box.setWindowTitle(APP)
            box.setText(tr("Zu welcher Zeichnung geh\u00f6ren die Kommentare?"))
            ba = box.addButton(tr("Alte Zeichnung (A)"), QMessageBox.ButtonRole.AcceptRole)
            bb = box.addButton(tr("Neue Zeichnung (B)"), QMessageBox.ButtonRole.AcceptRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(bb if guess_b else ba)
            box.exec()
            if box.clickedButton() not in (ba, bb):
                return
            side = "B" if box.clickedButton() is bb else "A"
        page = (self.sp_pa if side == "A" else self.sp_pb).value()
        try:
            k, page_h = self._sheet_geometry(side)
            if path.lower().endswith(".pdf"):
                items, skipped = dx.pdf_comments(path, page)
            else:
                items, skipped = dx.parse_xfdf(path, page_h, page - 1)
        except Exception as e:                       # noqa: BLE001
            self.banner.show_msg(tr("Kommentare konnten nicht gelesen werden: {}").format(e), "error")
            return
        ox, oy = self.origin
        vec = self.chk_vec.isChecked() and self.chk_vec.isEnabled()
        if side == "A" or self.view_only or vec:
            mp = lambda x, y: (x - ox, y - oy)                                           # noqa: E731
        else:
            def mp(x, y):
                q = dp.map_points_tf([(x, y)], self.cache.get("tf"), self.cache.get("box_b"), self.manual_tf)[0]
                return float(q[0]), float(q[1])
        new = dx.to_annotations(items, k, self.canvas.ann_size, mp)
        if not new:
            self.banner.show_msg(tr("In der Datei wurden keine \u00fcbernehmbaren Kommentare f\u00fcr diese Seite gefunden."),
                                 "warn", timeout=10)
            return
        self.anns.extend(new)
        self._ann_refresh(None)
        self._commit()
        self.act_right.setChecked(True)
        self.tabs.setCurrentIndex(1)
        extra = tr(" ({} Kommentare anderer Art übersprungen)").format(skipped) if skipped else ""
        self.banner.show_msg(tr("{} Kommentare als {} Markierungen übernommen{}.").format(len(items), len(new), extra), "info",
                             timeout=12)

    def export_xfdf(self):
        if not self.anns:
            QMessageBox.information(self, APP, tr("Es gibt keine Markierungen zum Speichern."))
            return
        base = os.path.splitext(os.path.basename(self.path_a or "markierungen"))[0]
        path = self._save_dialog(tr("Markierungen als XFDF speichern"), tr("XFDF (*.xfdf)"), base + ".xfdf")
        if not path:
            return
        k, page_h = self._sheet_geometry("A")
        anns = self._state()["anns"]                 # Blattkoordinaten von A
        mm = self.canvas.mm_px
        name = os.path.basename(self.path_a) if (self.path_a or "").lower().endswith(".pdf") else ""
        n = dx.write_xfdf(path, anns, k, page_h, name, self.sp_pa.value() - 1, lambda a: rep.measure_text(a, mm))
        self.banner.show_msg(tr("{} Markierungen gespeichert: {}. In Acrobat: Kommentare → Importieren (zur PDF der alten Zeichnung).").format(n, path), "info", timeout=15)
