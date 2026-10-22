"""Hauptfenster: Anmerkungen."""
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_widgets import ApprovalDialog


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
        c = QColorDialog.getColor(QColor(a["color"] if a else self.canvas.ann_color), self, "Farbe")
        if c.isValid():
            if a:
                a["color"] = c.name()
                self._set_color_btn(c.name(), default=False)
                self.canvas.update()
                self._commit()
            else:
                self._set_color_btn(c.name())

    def _sel(self):
        i = self.canvas.ann_selected
        return self.anns[i] if i is not None and 0 <= i < len(self.anns) else None

    def _ann_size(self):
        a = self._sel()
        if a:
            a["size"] = self.s_asize.value()
            self._commit()
        else:
            self.canvas.ann_size = self.s_asize.value()
        self.canvas.update()

    def _ann_label(self, a):
        t = a["type"]
        if t == "number":
            return f"Nummer {a['nr']}"
        if t == "text":
            return "Text: " + a["text"].replace("\n", " ")[:32]
        if t == "approval":
            return "Stempel: " + " / ".join(a["text"].split("\n")[:2])
        if t == "measure":
            return f"{rep.MEASURE_KINDS.get(a.get('kind'), 'Ma\u00df')}: {rep.measure_text(a, self.canvas.mm_px)}"
        return {"rect": "Rahmen", "cloud": "Wolke", "highlight": "Marker", "arrow": "Pfeil"}.get(t, t)

    def _ann_refresh(self, select=None):
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
            txt, ok = QInputDialog.getMultiLineText(self, "Text einf\u00fcgen", "Anmerkung:", "")
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
        dlg = ApprovalDialog(self, lines[0] if lines else "FREIGEGEBEN", name, date)
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
            txt, ok = QInputDialog.getMultiLineText(self, "Text \u00e4ndern", "Anmerkung:", a["text"])
            if ok and txt.strip():
                a["text"] = txt.strip()
        elif a["type"] == "number":
            n, ok = QInputDialog.getInt(self, "Nummer \u00e4ndern", "Nummer:", a["nr"], 1, 9999)
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
        i = self.canvas.ann_selected
        if i is not None and 0 <= i < len(self.anns):
            del self.anns[i]
            self._ann_refresh(None)
            self._commit()

    def _ann_clear(self):
        if self.anns and QMessageBox.question(self, APP, "Alle Anmerkungen l\u00f6schen? (R\u00fcckg\u00e4ngig mit Strg+Z)") == QMessageBox.StandardButton.Yes:
            self.anns.clear()
            self._ann_refresh(None)
            self._commit()

    def _ann_context(self, i, pos):
        m = QMenu(self)
        a = self.anns[i]
        if a["type"] in ("text", "number", "approval"):
            m.addAction("Bearbeiten\u2026", lambda: self._ann_edit(i))
        m.addAction("Farbe\u2026", self._pick_color)
        m.addAction("Duplizieren", self._ann_duplicate)
        m.addSeparator()
        m.addAction("L\u00f6schen", self._ann_delete)
        m.exec(pos)

    def ann_save(self):
        path = self._save_dialog("Anmerkungen speichern", "Anmerkungen (*.json)", "anmerkungen.json")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"version": 3, "coords": "global", "annotations": self._state()["anns"]},
                          f, ensure_ascii=False, indent=1)
            self._log(f"Anmerkungen gespeichert: {path}")

    def ann_load(self):
        d = self.settings.value("outdir", "")
        path, _ = QFileDialog.getOpenFileName(self, "Anmerkungen laden", d, "Anmerkungen (*.json)")
        if path:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.anns[:] = rep.upgrade_annotations(data.get("annotations", []))
            if data.get("coords") == "global":
                for a in self.anns:
                    shift_ann(a, -self.origin[0], -self.origin[1])
            self._ann_refresh(None)
            self._commit()
            self._log(f"{len(self.anns)} Anmerkungen geladen")
