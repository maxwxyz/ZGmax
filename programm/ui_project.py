"""Hauptfenster: Rueckgaengig, Projekt speichern/oeffnen."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_widgets import ApprovalDialog


class ProjectMixin:
    """Teil des Hauptfensters (wird in MainWindow eingemischt)."""

    # --- Rueckgaengig / Wiederholen (Anmerkungen und Zonen)
    def _state(self):
        ox, oy = self.origin
        anns = copy.deepcopy(self.anns)
        for a in anns:
            shift_ann(a, ox, oy)                   # global speichern
        f = getattr(self, "crop_frame", None)
        return {"anns": anns, "zones": [list(z) for z in self.zones], "edit": getattr(self, "_edit_ver", 0),
                "frame": list(f) if f else None}

    def _reset_history(self):
        self._edits, self._edit_ver, self._edit_saved = [], 0, True      # Bildaenderungen (Ausschnitt verschieben)
        if hasattr(self, "act_save_drawing"):
            self.act_save_drawing.setEnabled(False)
        self.undo_stack, self.redo_stack = [], []
        self._cur_state = self._state()
        self._dirty = False
        self._update_history_buttons()

    def _update_history_buttons(self):
        self.act_undo.setEnabled(bool(self.undo_stack))
        self.act_redo.setEnabled(bool(self.redo_stack))

    def _commit(self):
        """Nach jeder Aenderung aufrufen: legt den vorherigen Stand auf den Rueckgaengig-Stapel."""
        st = self._state()
        if self._cur_state is not None and st == self._cur_state:
            return
        if self._cur_state is not None:
            self.undo_stack.append(self._cur_state)
            del self.undo_stack[:-200]
        self._cur_state = st
        self.redo_stack.clear()
        self._dirty = True
        self._update_history_buttons()
        self._update_title()

    def _apply_state(self, st):
        self.canvas.reset_interaction()            # Rueckgaengig mitten in einer Eingabe: diese verwerfen
        ox, oy = self.origin
        anns = copy.deepcopy(st["anns"])
        for a in anns:
            shift_ann(a, -ox, -oy)
        zones = [tuple(z) for z in st["zones"]]
        self.crop_frame = tuple(st["frame"]) if st.get("frame") else None
        self._refresh_frame()
        zones_changed = zones != self.zones
        self.anns[:] = anns
        self.zones[:] = zones
        if st.get("edit", 0) != getattr(self, "_edit_ver", 0):
            self._edit_goto(st.get("edit", 0))
        self._ann_refresh(None)
        self._refresh_zones()
        if zones_changed:
            self._param_changed()
        self._cur_state = copy.deepcopy(st)
        self._dirty = True
        self._update_history_buttons()
        self._update_title()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self._cur_state)
        self._apply_state(self.undo_stack.pop())
        self._log(tr("R\u00fcckg\u00e4ngig"))

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self._cur_state)
        self._apply_state(self.redo_stack.pop())
        self._log(tr("Wiederholt"))

    # --- Projekt (Sitzung) speichern und laden
    def _update_title(self):
        if self.project_path:
            name = os.path.basename(self.project_path)
        elif self.path_a and self.path_b:
            name = f"{os.path.basename(self.path_a)} \u2192 {os.path.basename(self.path_b)}"   # alt -> neu
        elif self.path_a or self.path_b:
            name = os.path.basename(self.path_a or self.path_b)
        else:
            name = APP_SUBTITLE
        self.setWindowTitle(f"{name}{' *' if getattr(self, '_dirty', False) else ''} \u2013 {APP}")

    def _project_data(self):
        pa, pb = self.path_a, self.path_b
        sliders = {k: getattr(self, k).value() for k in ("s_thr", "s_tol", "s_hatch", "s_move", "s_obj", "s_rot",
                                                         "s_area", "s_cell", "s_maxs", "s_border", "s_group")}
        lay, col = self.vfilter
        st = self._state()
        return {
            "format": "zgmax", "version": 2, "program": APP,
            "saved": dt.datetime.now().isoformat(timespec="seconds"),
            "files": {"a": pa, "b": pb, "page_a": self.sp_pa.value(), "page_b": self.sp_pb.value()},
            "dpi": self.dpi_value(), "scale": self.scale_n(),
            "params": dict(sliders, align=self.cb_align.currentText(), edge_noise=self.chk_edges.isChecked(),
                           glyphs=self.chk_glyphs.isChecked(), flatten=self.chk_flatten.isChecked(),
                           align_on=self.chk_align.isChecked()),
            "pdf_layers_off": sorted(getattr(self, "pdf_off", set())),
            "page_scales": getattr(self, "page_scales", {}),
            "annotations_page": getattr(self, "_anns_key", None),
            "page_annotations": getattr(self, "page_anns", {}),           # Markierungen der anderen Seiten
            "vector": {"on": self.chk_vec.isChecked(), "tol": self.sp_vtol.value(),
                       "layers": sorted(lay) if lay is not None else None,
                       "colors": sorted(col) if col is not None else None},
            "crop": list(self.crop) if self.crop else None,
            "zones": st["zones"], "annotations": st["anns"], "crop_frame": st.get("frame"),
            "view": {"mode": self.canvas.mode, "overlays": self.act_overlays.isChecked()},
            "approval_name": self.settings.value("approval_name", ""),
            "crop_b": list(self.crop_b) if self.crop_b else None,
            "manual_align": self.manual_tf,
            # Aenderungsliste mit Pruefstand (Status, Kommentar, eigene Eintraege)
            "regions": copy.deepcopy(self.payload["regs"]) if (self.payload and self.payload["regs_done"]) else None,
        }

    def project_save(self, as_new=False):
        path = self.project_path
        if as_new is not False or not path:
            base = os.path.splitext(os.path.basename(self.path_a or "projekt"))[0]
            path = self._save_dialog(tr("Projekt speichern"), tr("ZGmax-Projekt (*{})").format(PROJECT_EXT),
                                     base + PROJECT_EXT)
            if not path:
                return False
        if not path.lower().endswith(PROJECT_EXT):
            path += PROJECT_EXT
        data = self._project_data()
        base_dir = os.path.dirname(os.path.abspath(path))
        for k in ("a", "b"):                      # zusaetzlich relative Pfade (Projekt samt Dateien verschiebbar)
            p = data["files"][k]
            if p:
                try:
                    data["files"][k + "_rel"] = os.path.relpath(p, base_dir)
                except ValueError:                # anderes Laufwerk
                    pass
        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)                 # erst fertig schreiben, dann ersetzen
        except OSError as ex:
            QMessageBox.warning(self, APP, tr("Projekt konnte nicht gespeichert werden:\n{}").format(ex))
            return False
        self.project_path = path
        self._dirty = False
        self._update_title()
        self._saved(path)
        return True

    def project_open(self, path=None):
        if not isinstance(path, str) or not path:
            d = self.settings.value("outdir", "")
            path, _ = QFileDialog.getOpenFileName(self, tr("Projekt \u00f6ffnen"), d,
                                                  tr("ZGmax-Projekt (*{})").format(PROJECT_EXT))
            if not path:
                return
        if self.payload is not None or self.path_a or self.path_b:   # eigenes Fenster fuer das Projekt
            self._doc_window().project_open(path)
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("format") != "zgmax":
                raise ValueError(tr("keine Projektdatei dieses Programms"))
            if int(data.get("version", 1)) > 2:
                self.banner.show_msg(tr("Das Projekt stammt aus einer neueren Programmversion. Es wird ge\u00f6ffnet, "
                                     "neuere Angaben k\u00f6nnen aber fehlen."), "warn", timeout=15)
        except (OSError, ValueError) as ex:
            QMessageBox.warning(self, APP, tr("Projekt konnte nicht gelesen werden:\n{}").format(ex))
            return
        base_dir = os.path.dirname(os.path.abspath(path))
        fl = data.get("files", {})
        found = {}
        for k in ("a", "b"):
            cands = [fl.get(k), os.path.normpath(os.path.join(base_dir, fl[k + "_rel"])) if fl.get(k + "_rel") else None,
                     os.path.join(base_dir, os.path.basename(fl[k])) if fl.get(k) else None]
            found[k] = next((c for c in cands if c and os.path.isfile(c)), None)
        missing = [k.upper() for k in ("a", "b") if fl.get(k) and not found[k]]
        if missing:
            QMessageBox.warning(self, APP, tr("Zeichnung ") + tr(" und ").join(missing) + tr(" wurde nicht gefunden. Das Projekt "
                                "wird trotzdem ge\u00f6ffnet; Datei bitte \u00fcber \u201e\u00d6ffnen\u2026\u201c neu w\u00e4hlen."))
        self.settings.setValue("outdir", base_dir)
        self.payload = None
        self.restore_regs = data.get("regions") if isinstance(data.get("regions"), list) else None
        self.crop = None
        self.zones.clear()
        self.anns.clear()
        self.origin = (0, 0)
        if found["a"]:
            self._set_file("A", found["a"], compute=False)
        if found["b"]:
            self._set_file("B", found["b"], compute=False)

        def quiet(widget, fn):
            widget.blockSignals(True)
            fn()
            widget.blockSignals(False)
        for w, key in ((self.sp_pa, "page_a"), (self.sp_pb, "page_b")):
            quiet(w, lambda w=w, key=key: w.setValue(min(max(1, int(fl.get(key, 1))), w.maximum())))
        quiet(self.sp_dpi, lambda: self.sp_dpi.setValue(int(data.get("dpi", self.sp_dpi.value()))))
        quiet(self.sp_scale, lambda: self.sp_scale.setValue(float(data.get("scale", 1.0))))
        pr = data.get("params", {})
        for k in ("s_thr", "s_tol", "s_hatch", "s_move", "s_obj", "s_rot", "s_area", "s_cell", "s_maxs", "s_border",
                  "s_group"):
            if k in pr:
                getattr(self, k).set_silent(pr[k])
        for key, chk in (("edge_noise", self.chk_edges), ("glyphs", self.chk_glyphs), ("flatten", self.chk_flatten),
                         ("align_on", self.chk_align)):
            if key in pr:
                quiet(chk, lambda chk=chk, key=key: chk.setChecked(bool(pr[key])))
        if pr.get("align"):
            quiet(self.cb_align, lambda: self.cb_align.setCurrentText(pr["align"]))
        self.pdf_off = set(data.get("pdf_layers_off") or [])
        self.page_scales = dict(data.get("page_scales") or {})
        self.page_anns = copy.deepcopy(data.get("page_annotations") or {})
        vc = data.get("vector", {})
        self.vfilter = (set(vc["layers"]) if vc.get("layers") is not None else None,
                        set(vc["colors"]) if vc.get("colors") is not None else None)
        if "tol" in vc:
            quiet(self.sp_vtol, lambda: self.sp_vtol.setValue(float(vc["tol"])))
        self._vec_status()
        if vc.get("on") and self.chk_vec.isEnabled():
            quiet(self.chk_vec, lambda: self.chk_vec.setChecked(True))
        cr = data.get("crop")
        cb = data.get("crop_b")
        if cr and len(cr) == 4:
            self.crop = tuple(int(v) for v in cr)
            self.crop_b = tuple(int(v) for v in cb) if cb and len(cb) == 4 else None
            self.btn_crop_off.setEnabled(True)
            self.lbl_crop.setText(tr("Aktuell: Ausschnitt {} × {} px").format(self.crop[2], self.crop[3]))
        self.zones[:] = [tuple(int(v) for v in z) for z in data.get("zones", [])]
        ma = data.get("manual_align")
        self.manual_tf = ma if (isinstance(ma, list) and len(ma) == 2) else None
        self.act_align_reset.setEnabled(self.manual_tf is not None)
        self.anns[:] = rep.upgrade_annotations(copy.deepcopy(data.get("annotations", [])))   # global; origin = (0, 0)
        self._anns_key = data.get("annotations_page") or self._page_key()       # diese Markierungen: aktuelle Seite
        self.crop_frame = tuple(data["crop_frame"]) if data.get("crop_frame") else None
        self._refresh_frame()
        if data.get("approval_name"):
            self.settings.setValue("approval_name", data["approval_name"])
        self._update_units()
        self._ann_refresh(None)
        self._refresh_zones()
        self.project_path = path
        self._reset_history()
        self._update_title()
        vw = data.get("view", {})
        if vw.get("mode") in self.mode_actions:
            self._set_mode(vw["mode"])
            self.mode_actions[vw["mode"]].setChecked(True)
        self.act_overlays.setChecked(bool(vw.get("overlays", True)))
        self._log(tr("Projekt geöffnet: {}").format(path))
        if not path.endswith("wiederherstellen" + PROJECT_EXT):
            recent_add(self.settings, project=path)
        if self.path_a and self.path_b:
            self.start_compute()

    def _maybe_save(self):
        """Ungespeicherte Markierungen/Pruefung: fragen. False = Abbrechen gewaehlt."""
        if self.drawing_edited():
            r = QMessageBox.question(self, APP, tr("Die Zeichnung wurde bearbeitet (Ausschnitt verschoben). "
                                     "Bearbeitete Zeichnung speichern?"),
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                     | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel or (
                    r == QMessageBox.StandardButton.Save and not self.save_drawing()):
                return False
        reviewed = bool(self.payload and any(r.get("status") or r.get("comment") for r in self.payload["regs"]))
        if getattr(self, "_dirty", False) and (self.anns or self.zones or reviewed):
            r = QMessageBox.question(self, APP, tr("Es gibt ungespeicherte \u00c4nderungen (Markierungen, Zonen oder "
                                     "Pr\u00fcfergebnisse). Als Projekt speichern?"),
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                     | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel or (
                    r == QMessageBox.StandardButton.Save and not self.project_save()):
                return False
        return True

    def closeEvent(self, e):
        if not self._maybe_save():
            e.ignore()
            return
        for job in list(self.jobs) + list(getattr(self, "_bg", [])):   # laufende Berechnung sauber beenden
            if hasattr(job, "cancel"):
                job.cancel()
            job.wait(15000)
        self.clear_autosave()
        import drawing_viewer
        if self in drawing_viewer.WINDOWS:
            drawing_viewer.WINDOWS.remove(self)
        super().closeEvent(e)
