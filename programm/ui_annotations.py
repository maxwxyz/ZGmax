"""Hauptfenster: Anmerkungen."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_widgets import ApprovalDialog
import diffxfdf as dx


class InlineText(QPlainTextEdit):
    """Texteingabe direkt im Bild (statt Eingabefenster). Strg+Enter oder Klick daneben = fertig, Esc = abbrechen."""
    finished = Signal(bool)

    def __init__(self, canvas, a):
        super().__init__(canvas)
        self.canvas, self.a = canvas, a
        self._done = False
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().setDocumentMargin(1)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if a.get("w")
                             else QPlainTextEdit.LineWrapMode.NoWrap)
        self._px = None
        self.setPlainText(a.get("text", ""))
        self.setPlaceholderText(tr("Text …"))
        self.textChanged.connect(self.place)
        self.place()
        self.show()
        self.setFocus()
        self.moveCursor(QTextCursor.MoveOperation.End)

    def place(self):
        c, a = self.canvas, self.a
        th = int(max(9, rep.ann_text_h(c.shape, a["size"]) * c.scale))
        if th != self._px:                        # Schriftgroesse wie im Bild (Stylesheet, sonst gewinnt das Farbschema)
            self._px = th
            self.setStyleSheet(f"QPlainTextEdit {{ background: rgba(255,255,255,215); color: {a['color']}; "
                               f"border: 1px dashed {ACCENT}; padding: 0; font-family: '{UI_FONT}'; "
                               f"font-size: {th}px; }}")
            f = QFont(UI_FONT)
            f.setPixelSize(th)
            self.setFont(f)
        fm = self.fontMetrics()
        lines = (self.toPlainText() or " ").split("\n")
        x, y = c.to_wid(a["x"], a["y"])
        if a.get("w"):
            w = a["w"] * c.scale
            doc_lines = max(1, self.document().documentLayout().documentSize().height() // max(1, fm.lineSpacing()))
            n = int(max(len(lines), doc_lines))
        else:
            w = max(fm.horizontalAdvance(s) for s in lines) + fm.averageCharWidth() * 3
            n = len(lines)
        geo = QRect(int(x) - 2, int(y) - 2, int(max(40, w)) + 6, int(n * fm.lineSpacing()) + 8)
        if self.geometry() != geo:
            self.setGeometry(geo)

    def event(self, e):
        # Strg+Enter (sonst "Vergleichen") und Esc gehoeren waehrend der Eingabe dem Textfeld
        if e.type() == QEvent.Type.ShortcutOverride and e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter,
                                                                     Qt.Key.Key_Escape):
            e.accept()
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._finish(False)
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and e.modifiers() & (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            self._finish(True)
        else:
            super().keyPressEvent(e)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        QTimer.singleShot(0, lambda: self._finish(True))

    def _finish(self, ok):
        if not self._done:
            self._done = True
            self.finished.emit(ok)


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
                self._ann_update_items(self.canvas.selected_anns())
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

    @staticmethod
    def _swatch(col):
        pm = QPixmap(14, 14)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1))
        p.setBrush(QColor(col))
        p.drawRoundedRect(QRectF(1, 1, 12, 12), 3, 3)
        p.end()
        return QIcon(pm)

    def _ann_label(self, a):
        """Listentext: Art und Inhalt, dazu Anzahl der Antworten und gesetzte Status."""
        lbl = self._ann_label_base(a)
        n = len(a.get("replies") or [])
        if n:
            lbl += "  💬" + str(n)
        st = [s for s in dict.fromkeys((a.get("states") or {}).values()) if s in rep.REVIEW_STATES and s != "none"]
        if st:
            lbl += "  [" + ", ".join(rep.REVIEW_STATES[s] for s in st) + "]"
        return lbl

    def _ann_label_base(self, a):
        t = a["type"]
        if t == "number":
            return tr("Nummer {}").format(a['nr'])
        if t == "text":
            return tr("Text: ") + a["text"].replace("\n", " ")[:32]
        if t == "approval":
            return tr("Stempel: ") + " / ".join(a["text"].split("\n")[:2])
        if t == "measure":
            return f"{rep.MEASURE_KINDS.get(a.get('kind'), 'Ma\u00df')}: {rep.measure_text(a, self.canvas.mm_px)}"
        lbl = {"rect": tr("Rahmen"), "cloud": tr("Wolke"), "highlight": tr("Marker"), "arrow": tr("Pfeil"),
               "line": tr("Linie"), "ellipse": tr("Ellipse"), "pen": tr("Freihand"), "polyline": tr("Linienzug"),
               "polygon": tr("Polygon"), "image": tr("Bild"), "redact": tr("Schwärzung"),
               "pixelate": tr("Verpixelung")}.get(t, t)
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
            it = QListWidgetItem(self._ann_label(a))
            it.setIcon(self._swatch(a.get("color", "#000000")))   # Farbe der Markierung
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked if a.get("hidden") else Qt.CheckState.Checked)
            it.setToolTip(tr("Haken = im Bild und in Ausgaben sichtbar"))
            self.list_anns.addItem(it)
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
        self._update_sums()
        if hasattr(self, "list_pages"):
            self._update_page_labels()
        if hasattr(self, "options_bar"):
            self._update_options()
        self.canvas.update()

    # --- Unterhaltung: Kommentar, Antworten, Status je Person (wie Acrobat/Bluebeam)
    def _build_thread_panel(self):
        box = QFrame()
        box.setObjectName("card")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)
        self.lbl_thread_head = QLabel("")
        self.lbl_thread_head.setObjectName("sec")
        self.lbl_thread_head.setWordWrap(True)
        lay.addWidget(self.lbl_thread_head)
        self.ed_comment = QPlainTextEdit()
        self.ed_comment.setPlaceholderText(tr("Kommentar zur Markierung …"))
        self.ed_comment.setFixedHeight(54)
        self.ed_comment.textChanged.connect(self._comment_edited)
        lay.addWidget(self.ed_comment)
        self.lbl_thread = QLabel("")
        self.lbl_thread.setWordWrap(True)
        self.lbl_thread.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_thread.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.lbl_thread)
        row = QHBoxLayout()
        self.ed_reply = QLineEdit()
        self.ed_reply.setPlaceholderText(tr("Antworten …"))
        self.ed_reply.returnPressed.connect(self._add_reply)
        b = QPushButton(tr("Antworten"))
        b.clicked.connect(self._add_reply)
        row.addWidget(self.ed_reply, 1)
        row.addWidget(b)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Mein Status")))
        self.cb_state = QComboBox()
        for k, v in rep.REVIEW_STATES.items():
            self.cb_state.addItem(v, k)
        self.cb_state.currentIndexChanged.connect(self._state_changed)
        row.addWidget(self.cb_state, 1)
        lay.addLayout(row)
        self.thread_box = box
        self._comment_timer = QTimer(self)
        self._comment_timer.setSingleShot(True)
        self._comment_timer.timeout.connect(self._commit)
        box.hide()
        return box

    def _user_name(self, ask=True):
        """Name fuer Kommentare und Status (einmal fragen, dann gemerkt)."""
        name = self.settings.value("user_name", "") or self.settings.value("approval_name", "")
        if not name and ask:
            name, ok = QInputDialog.getText(self, APP, tr("Dein Name für Kommentare und Status:"))
            name = name.strip() if ok else ""
            if name:
                self.settings.setValue("user_name", name)
        return name

    def _thread_refresh(self):
        idx = sorted(self.canvas.selected_anns())
        a = self.anns[idx[0]] if len(idx) == 1 and idx[0] < len(self.anns) else None
        self.thread_box.setVisible(a is not None)
        if a is None:
            return
        head = self._ann_label(a).split(":")[0]
        who = " · ".join(v for v in (a.get("author"), (a.get("date") or "")[:16]) if v)
        self.lbl_thread_head.setText(head + (f"  ({who})" if who else ""))
        self.ed_comment.blockSignals(True)
        if self.ed_comment.toPlainText() != (a.get("comment") or ""):
            self.ed_comment.setPlainText(a.get("comment") or "")
        self.ed_comment.blockSignals(False)
        import html
        parts = [f"<b>{html.escape(r.get('author') or '?')}</b> <span style='color:gray'>"
                 f"{html.escape((r.get('date') or '')[:16])}</span><br>{html.escape(r.get('text', ''))}"
                 for r in a.get("replies") or []]
        states = a.get("states") or {}
        if states:
            parts.append(tr("Status: ") + ", ".join(f"{html.escape(k or '?')}: {rep.REVIEW_STATES.get(v, v)}"
                                                    for k, v in states.items()))
        self.lbl_thread.setText("<br><br>".join(parts))
        self.lbl_thread.setVisible(bool(parts))
        me = self._user_name(ask=False)
        self.cb_state.blockSignals(True)
        self.cb_state.setCurrentIndex(max(0, self.cb_state.findData(states.get(me, "none"))))
        self.cb_state.blockSignals(False)

    def _thread_ann(self):
        idx = sorted(self.canvas.selected_anns())
        return self.anns[idx[0]] if len(idx) == 1 and idx[0] < len(self.anns) else None

    def _comment_edited(self):
        a = self._thread_ann()
        if a is not None:
            a["comment"] = self.ed_comment.toPlainText()
            self._ann_update_items(self.canvas.selected_anns())
            self._comment_timer.start(800)        # Tippen zusammenfassen: ein Rueckgaengig-Schritt

    def _add_reply(self):
        a = self._thread_ann()
        txt = self.ed_reply.text().strip()
        if a is None or not txt:
            return
        a.setdefault("replies", []).append(dict(author=self._user_name(), text=txt,
                                                date=dt.datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.ed_reply.clear()
        self._ann_update_items(self.canvas.selected_anns())
        self._thread_refresh()
        self._commit()

    def _state_changed(self, _i):
        a = self._thread_ann()
        if a is None:
            return
        me = self._user_name()
        st = self.cb_state.currentData()
        if st == "none":
            (a.get("states") or {}).pop(me, None)
        else:
            a.setdefault("states", {})[me] = st
        self._ann_update_items(self.canvas.selected_anns())
        self._thread_refresh()
        self._commit()

    def _sync_ann_controls(self):
        """Optionszeile zeigt die gewaehlte Markierung, sonst die Vorgabe fuer neue."""
        if hasattr(self, "thread_box"):
            self._thread_refresh()
        self._update_sums()
        a = self._sel()
        self.s_asize.set_silent(a["size"] if a else self.canvas.ann_size)
        self._set_color_btn(a["color"] if a else self.canvas.ann_color, default=False)

    def _ann_created(self, a):
        rep.ann_id(a)
        if not a.get("author"):
            a["author"] = self._user_name(ask=False)
        self.anns.append(a)
        self._ann_refresh(len(self.anns) - 1)
        self._commit()
        if a["type"] == "measure" and a.get("kind") == "dist" and getattr(self, "_calib_pending", False):
            QTimer.singleShot(0, lambda: self._calibrate(math.hypot(a["x2"] - a["x"], a["y2"] - a["y"])))
        self.tabs.setCurrentWidget(self.tab_anns)
        if a["type"] not in ("number", "measure", "pen") and not self.chk_keep_tool.isChecked():
            self._set_tool("hand")                        # Zaehlen, Messen, Freihand oder "Werkzeug behalten": bleibt

    def _place(self, tool, x, y, w=None):
        """Text, Nummer oder Freigabe setzen. Text wird direkt im Bild getippt."""
        base = dict(x=x, y=y, x2=x, y2=y, text="", nr=0, color=self.canvas.ann_color, size=self.canvas.ann_size)
        if tool == "number":
            self._ann_created(dict(base, type="number", nr=self.next_nr))
        elif tool == "text":
            self._text_inline(None, dict(base, type="text", **({"w": w} if w else {})))
        elif tool == "approval":
            t = self._approval_text("")
            if t:
                self._ann_created(dict(base, type="approval", text=t))
            else:
                self._set_tool("hand")

    def _text_inline(self, idx, a):
        """Text direkt im Bild schreiben (neu: idx None) oder aendern. Bei gedrehter Ansicht: Eingabefenster."""
        c = self.canvas
        if c.inline_editor is not None:
            c.inline_editor._finish(True)
        if c.rot % 4 != 0:
            txt, ok = QInputDialog.getMultiLineText(self, tr("Text einf\u00fcgen"), tr("Anmerkung:"), a.get("text", ""))
            if ok and txt.strip():
                a["text"] = txt.strip()
                if idx is None:
                    self._ann_created(a)
                else:
                    self._ann_refresh(idx)
                    self._commit()
            return
        ed = InlineText(c, a)
        c.inline_editor, c.editing = ed, idx
        c.update()
        self.statusBar().showMessage(tr("Text tippen. Strg+Enter oder Klick daneben = fertig, Esc = abbrechen."), 8000)

        def done(ok):
            txt = ed.toPlainText().strip()
            c.inline_editor, c.editing = None, None
            ed.deleteLater()
            c.setFocus()
            if idx is None:
                if ok and txt:
                    self._ann_created(dict(a, text=txt))
                elif not self.chk_keep_tool.isChecked():
                    self._set_tool("hand")
            elif ok and txt != a.get("text"):
                if txt:
                    a["text"] = txt
                    self._ann_refresh(idx)
                else:                                      # Text geleert: Markierung entfernen
                    del self.anns[idx]
                    self._ann_refresh(None)
                self._commit()
            c.update()
        ed.finished.connect(done)

    def _approval_text(self, old):
        lines = old.split("\n") if old else []
        name = lines[1] if len(lines) > 1 else self.settings.value("approval_name", "")
        date = lines[2] if len(lines) > 2 else dt.date.today().strftime("%d.%m.%Y")
        try:
            custom = json.loads(self.settings.value("stamps", "[]") or "[]")
        except ValueError:
            custom = []
        dlg = ApprovalDialog(self, lines[0] if lines else tr("FREIGEGEBEN"), name, date, custom)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        self.settings.setValue("approval_name", dlg.ed_name.text().strip())
        self.settings.setValue("stamps", json.dumps(dlg.stamps(), ensure_ascii=False))
        return dlg.text()

    # --- Werkzeugkasten: gespeicherte Werkzeuge mit Farbe und Groesse (z. B. "Wolke rot dick", "Marker gruen")
    def _presets(self):
        try:
            return json.loads(self.settings.value("toolchest", "[]") or "[]")
        except ValueError:
            return []

    def _fill_toolchest(self, menu):
        menu.clear()
        presets = self._presets()
        for p in presets:
            act = menu.addAction(self._swatch(p.get("color", "#000000")), p["name"], lambda p=p: self.apply_preset(p))
            act.setToolTip(tr("Werkzeug {}, Größe {:.1f}").format(p.get("tool"), p.get("size", 2.0)))
        if presets:
            menu.addSeparator()
        menu.addAction(tr("Aktuelles Werkzeug als Vorlage speichern …"), self.save_preset)
        if presets:
            rm = menu.addMenu(tr("Vorlage entfernen"))
            for i, p in enumerate(presets):
                rm.addAction(p["name"], lambda i=i: self._remove_preset(i))

    def save_preset(self):
        c = self.canvas
        t = c.tool if c.tool not in ("hand", "zoom", "area") else None
        if t is None:
            QMessageBox.information(self, APP, tr("Zuerst ein Zeichen-, Mess- oder Markierwerkzeug wählen und Farbe "
                                                  "und Größe einstellen."))
            return
        label = next((lbl for k, lbl, *_ in TOOLS_LIST() if k == t), t)
        name, ok = QInputDialog.getText(self, tr("Vorlage speichern"), tr("Name der Vorlage:"),
                                        text=f"{label} {c.ann_size:g}")
        if not ok or not name.strip():
            return
        p = dict(name=name.strip(), tool=t, color=c.ann_color, size=c.ann_size)
        if t == "measure":
            p["kind"] = c.measure_kind
        if t == "redact":
            p["fill"] = "paper" if self.chk_redact_paper.isChecked() else "black"
        presets = [q for q in self._presets() if q["name"] != p["name"]] + [p]
        self.settings.setValue("toolchest", json.dumps(presets, ensure_ascii=False))
        self.statusBar().showMessage(tr("Vorlage „{}“ gespeichert (Werkzeuge → Werkzeugkasten)").format(p["name"]), 5000)

    def _remove_preset(self, i):
        presets = self._presets()
        if 0 <= i < len(presets):
            del presets[i]
            self.settings.setValue("toolchest", json.dumps(presets, ensure_ascii=False))

    def apply_preset(self, p):
        if self.payload is None or p.get("tool") not in self.tool_actions:
            return
        self._set_tool(p["tool"])
        c = self.canvas
        c.ann_size = float(p.get("size", c.ann_size))
        self.s_asize.set_silent(c.ann_size)
        if p.get("color"):
            self._set_color_btn(p["color"])
        if p.get("kind") and self.cb_mkind.findData(p["kind"]) >= 0:
            self.cb_mkind.setCurrentIndex(self.cb_mkind.findData(p["kind"]))
        if "fill" in p:
            self.chk_redact_paper.setChecked(p["fill"] == "paper")
        self.statusBar().showMessage(tr("Vorlage „{}“").format(p["name"]), 3000)

    def _ann_selected(self, i):
        self._ann_refresh(i if i >= 0 else None)
        if i >= 0:
            self.tabs.setCurrentWidget(self.tab_anns)

    def _ann_item_checked(self, it):
        """Haken in der Liste: einzelne Markierung ein-/ausblenden (ausgeblendet = auch nicht gespeichert/gedruckt)."""
        i = self.list_anns.row(it)
        if not (0 <= i < len(self.anns)):
            return
        hidden = it.checkState() != Qt.CheckState.Checked
        if bool(self.anns[i].get("hidden")) != hidden:
            if hidden:
                self.anns[i]["hidden"] = True
            else:
                self.anns[i].pop("hidden", None)
            self.canvas.update()
            self._commit()

    def _update_sums(self):
        """Summen der Messungen und Anzahl je Art - fuer die Auswahl, sonst fuer alle Markierungen."""
        if not hasattr(self, "lbl_sums"):
            return
        sel = sorted(self.canvas.selected_anns())
        anns = [self.anns[i] for i in sel] if len(sel) > 1 else self.anns
        parts, counts = rep.measure_summary(anns, self.canvas.mm_px)
        names = {"number": tr("Nummern"), "cloud": tr("Wolken"), "rect": tr("Rahmen"), "text": tr("Texte"),
                 "arrow": tr("Pfeile"), "approval": tr("Stempel")}
        cnt = [f"{n} {names[t]}" for t, n in counts.items() if t in names]
        txt = " · ".join(parts + cnt)
        self.lbl_sums.setText((tr("Auswahl: ") if len(sel) > 1 else tr("Gesamt: ")) + txt if txt else "")
        self.lbl_sums.setVisible(bool(txt))

    def export_measures(self):
        """Messungen und Zaehlung als CSV (Semikolon, UTF-8 mit BOM - Excel oeffnet es direkt)."""
        if not self.anns:
            QMessageBox.information(self, APP, tr("Es gibt keine Markierungen zum Speichern."))
            return
        path = self._save_dialog(tr("Messungen speichern"), tr("CSV für Excel (*.csv)"), "messungen.csv")
        if not path:
            return
        import csv
        mm = self.canvas.mm_px
        unit = rep.MEASURE_FMT.get("unit", "mm")
        f = rep.UNITS.get(unit, 1.0)
        page = self.sp_pa.value()
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow([tr("Nr"), tr("Art"), tr("Wert"), tr("Einheit"), tr("Anzeige"), tr("Seite"), tr("Gruppe"),
                        tr("Autor"), tr("Kommentar")])
            n = 0
            for a in self.anns:
                if a.get("type") != "measure":
                    continue
                n += 1
                kind, v = rep.measure_value(a, mm)
                val, u = {"length": (v * f, unit), "area": (v * f * f, unit + "²"), "radius": (v * f, unit),
                          "angle": (v, "°")}.get(kind, (v, ""))
                w.writerow([n, rep.MEASURE_KINDS.get(a.get("kind"), a.get("kind")), f"{val:.4f}".replace(".", ","), u,
                            rep.measure_text(a, mm), page, a.get("group", ""), a.get("author", ""),
                            a.get("comment", "")])
            w.writerow([])
            parts, counts = rep.measure_summary(self.anns, mm)
            for ptxt in parts:
                w.writerow([tr("Summe"), ptxt])
            for t, c in sorted(counts.items()):
                w.writerow([tr("Anzahl"), self._ann_label_base(dict(type=t, nr=0, text="", x=0, y=0, x2=0, y2=0,
                                                                     size=1, kind="dist", pts=[[0, 0], [0, 0]])
                                                                ).split(":")[0], c])
        self._saved(path)

    def _ann_update_items(self, idx):
        """Listeneintraege (Text, Farbfeld) nach einer Aenderung nachziehen, ohne die Auswahl zu verlieren."""
        for i in idx:
            it = self.list_anns.item(i) if 0 <= i < len(self.anns) else None
            if it:
                it.setText(self._ann_label(self.anns[i]))
                it.setIcon(self._swatch(self.anns[i].get("color", "#000000")))

    def _ann_changed(self):
        self._ann_update_items(self.canvas.selected_anns())
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
            self.tabs.setCurrentWidget(self.tab_anns)
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
        if a["type"] == "text" and self.canvas.rot % 4 == 0:
            self._text_inline(i, a)
            return
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
        if self.canvas.tool == "area" and self.canvas.sel_rects:   # Entf in der Bereichsauswahl
            self.area_delete()
            return
        if self.canvas.zone_sel is not None:                      # Entf bei gewaehlter Zone
            self._zone_delete()
            return
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
        m.addAction(tr("Ausblenden"), lambda: self.list_anns.item(i).setCheckState(Qt.CheckState.Unchecked))
        m.addSeparator()
        m.addAction(tr("L\u00f6schen"), self._ann_delete)
        m.exec(pos)

    def ann_save(self):
        path = self._save_dialog(tr("Anmerkungen speichern"), tr("Anmerkungen (*.json)"), "anmerkungen.json")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"version": 3, "coords": "global", "annotations": self._state()["anns"]},
                          f, ensure_ascii=False, indent=1)
            self._saved(path)

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
            from pdfopen import open_doc
            with open_doc(path) as d:
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
        new = self._comments_to_markups(items, side, k)
        if not new:
            self.banner.show_msg(tr("In der Datei wurden keine \u00fcbernehmbaren Kommentare f\u00fcr diese Seite gefunden."),
                                 "warn", timeout=10)
            return
        self.anns.extend(new)
        self._ann_refresh(None)
        self._commit()
        self.act_right.setChecked(True)
        self.tabs.setCurrentWidget(self.tab_anns)
        extra = tr(" ({} Kommentare anderer Art übersprungen)").format(skipped) if skipped else ""
        self.banner.show_msg(tr("{} Kommentare als {} Markierungen übernommen{}.").format(len(items), len(new), extra), "info",
                             timeout=12)

    def _comments_to_markups(self, items, side, k):
        """Kommentare (PDF-Punkte) in Markierungen in der Lage der Anzeige (B: wie ausgerichtet)."""
        ox, oy = self.origin
        vec = self.chk_vec.isChecked() and self.chk_vec.isEnabled()
        if side == "A" or self.view_only or vec:
            mp = lambda x, y: (x - ox, y - oy)                                           # noqa: E731
        else:
            def mp(x, y):
                q = dp.map_points_tf([(x, y)], self.cache.get("tf"), self.cache.get("box_b"), self.manual_tf)[0]
                return float(q[0]), float(q[1])
        return dx.to_annotations(items, k, self.canvas.ann_size, mp)

    def _auto_import_pdf_comments(self):
        """Beim Oeffnen einer PDF: deren Kommentare als bearbeitbare Markierungen uebernehmen (einmal je Datei und
        Seite und Fenster; nicht bei Projekten - die haben ihre Markierungen schon)."""
        if self.payload is None or self.project_path or not dv.available():
            return
        done = self.__dict__.setdefault("_comments_done", set())
        sides = [("A", self.path_a, self.sp_pa.value())]
        if not self.view_only and self.path_b:
            sides.append(("B", self.path_b, self.sp_pb.value()))
        new, n_items = [], 0
        for side, path, page in sides:
            if not path or not path.lower().endswith(".pdf") or (path, page) in done:
                continue
            done.add((path, page))
            try:
                items, _skipped = dx.pdf_comments(path, page)
                if items:
                    k, _h = self._sheet_geometry(side)
                    got = self._comments_to_markups(items, side, k)
                    for a in got:
                        a["source"] = "AB"[side == "B"] if not self.view_only else ""
                    new += got
                    n_items += len(items)
            except Exception as e:                   # noqa: BLE001 - Kommentare sind Beiwerk, Fehler nur melden
                log.warning("Kommentare aus %s nicht gelesen: %s", path, e)
        if new:
            self.anns.extend(new)
            self._ann_refresh(None)
            self._commit()
            self.banner.show_msg(tr("{} Kommentare aus der PDF als bearbeitbare Markierungen übernommen (Ebene "
                                    "Markierungen; rückgängig mit Strg+Z).").format(n_items), "info", timeout=12)

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
