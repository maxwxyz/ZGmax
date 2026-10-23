"""Kleine Bausteine: Hintergrundjob, Regler, Ueberschriften, Dialoge."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403


# ----------------------------------------------------------------- Hintergrundjob
class SafeStream:
    """stdout/stderr, die nie einen Fehler werfen. Auf dem Mac schliesst sich nach dem Start ueber
    'Start ZGmax.command' das Terminalfenster; jedes print() wuerde dann mit OSError
    scheitern und die Berechnung im Hintergrund abbrechen."""

    def __init__(self, stream):
        self._s = stream

    def write(self, text):
        try:
            return self._s.write(text)
        except (OSError, ValueError):
            return len(text)

    def flush(self):
        try:
            self._s.flush()
        except (OSError, ValueError):
            pass

    def __getattr__(self, name):
        return getattr(self._s, name)


class JobContext:
    """Wird an die Arbeitsfunktion eines Jobs uebergeben. Aufruf ctx("Text") schreibt ins Protokoll
    (wie frueher log), ctx.progress(anteil, text) meldet Fortschritt, ctx.cancelled() fragt Abbruch ab."""

    def __init__(self, job):
        self._job = job
        self._last = (-1.0, None)

    def __call__(self, text):
        self._job.log.emit(text)

    def progress(self, frac, text=""):
        frac = float(min(1.0, max(0.0, frac)))
        if abs(frac - self._last[0]) >= 0.005 or text != self._last[1]:   # nicht jede Kleinigkeit melden
            self._last = (frac, text)
            self._job.progress.emit(frac, text)

    def cancelled(self):
        return self._job.cancelled

    def check(self):
        if self._job.cancelled:
            raise dc.Cancelled()

    def preview(self, img):
        self._job.preview.emit(img)


class Job(QThread):
    """Hintergrundarbeit. Meldet sich immer zurueck: done, failed (Meldung; Einzelheiten in .details)
    oder aborted (abgebrochen)."""
    done = Signal(object)
    failed = Signal(str)
    aborted = Signal()
    log = Signal(str)
    progress = Signal(float, str)
    preview = Signal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
        self.cancelled = False
        self.details = ""
        self.ctx = JobContext(self)

    def cancel(self):
        self.cancelled = True

    def run(self):
        try:
            self.done.emit(self.fn(self.ctx))
        except dc.Cancelled:
            self.aborted.emit()
        except (dc.DiffError, SystemExit) as e:
            self.failed.emit(str(e))
        except MemoryError:
            self.details = tr("MemoryError")
            self.failed.emit(tr("Zu wenig Arbeitsspeicher f\u00fcr diese Zeichnung. Bitte mit geringerer Aufl\u00f6sung "
                             "(dpi) oder einem Ausschnitt vergleichen."))
        except BaseException as e:                  # noqa: BLE001  der Job muss sich immer zurueckmelden
            try:
                import traceback
                self.details = traceback.format_exc()
                log.error(self.details)
            except Exception:                       # noqa: BLE001
                pass
            self.failed.emit(f"{type(e).__name__}: {e}")


class OverlayHost(QWidget):
    """Legt Leisten oben ueber ein Widget, statt es nach unten zu schieben: Ein- und Ausblenden
    der Leisten aendert die Groesse des Bilds nicht, die Zeichnung bleibt stehen."""

    def __init__(self, base, bars=(), parent=None):
        super().__init__(parent)
        self.base = base
        base.setParent(self)
        self.column = QWidget(self)
        lay = QVBoxLayout(self.column)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.column.installEventFilter(self)
        for b in bars:
            self.add_bar(b)

    def add_bar(self, bar, index=-1):
        was = not bar.isHidden()
        self.column.layout().insertWidget(index, bar)
        bar.setVisible(was)
        bar.setAutoFillBackground(True)                  # deckt das Bild ab, auch ohne Stylesheet
        bar.installEventFilter(self)
        self.relayout()

    def bar_height(self):
        """Hoehe der sichtbaren Leisten (Bildschirmpixel), die das Bild oben verdecken."""
        return self.column.height()

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.Type.LayoutRequest, QEvent.Type.Show, QEvent.Type.Hide):
            QTimer.singleShot(0, self.relayout)
        return False

    def relayout(self):
        w = self.width()
        self.base.setGeometry(0, 0, w, self.height())
        lay = self.column.layout()
        lay.activate()
        h = lay.heightForWidth(w) if lay.hasHeightForWidth() else lay.sizeHint().height()
        if not any(not lay.itemAt(i).widget().isHidden() for i in range(lay.count())):
            h = 0
        self.column.setGeometry(0, 0, w, max(0, min(h, self.height())))
        self.column.raise_()

    def resizeEvent(self, e):
        self.relayout()

    def sizeHint(self):
        return self.base.sizeHint()

    def minimumSizeHint(self):
        return self.base.minimumSizeHint()


class Banner(QFrame):
    """Hinweisleiste ueber dem Bild (statt Meldungsfenster): info (blau), warn (gelb), error (rot)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("banner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 6, 6)
        self.lbl = QLabel()
        self.lbl.setWordWrap(True)
        self.lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.btn_details = QPushButton(tr("Details"))
        self.btn_details.clicked.connect(self._show_details)
        self.btn_action = QPushButton()
        self.btn_action.setObjectName("primary")
        self.btn_action.clicked.connect(self._action)
        self._action_fn = None
        self.btn_close = QToolButton()
        self.btn_close.setText("\u2715")
        self.btn_close.setToolTip(tr("Schlie\u00dfen"))
        self.btn_close.clicked.connect(self.hide)
        lay.addWidget(self.lbl, 1)
        lay.addWidget(self.btn_action)
        lay.addWidget(self.btn_details)
        lay.addWidget(self.btn_close)
        self.details = ""
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self.hide()

    def _action(self):
        fn, self._action_fn = self._action_fn, None
        self.hide()
        if fn:
            fn()

    def show_msg(self, text, kind="info", details="", timeout=0, action=None):
        """action = (Beschriftung, Funktion): Knopf in der Leiste, z. B. "Einschalten"."""
        self._action_fn = action[1] if action else None
        self.btn_action.setText(action[0] if action else "")
        self.btn_action.setVisible(bool(action))
        self.setProperty("kind", kind)
        self.style().unpolish(self)
        self.style().polish(self)
        self.lbl.setText(text)
        self.details = details
        self.btn_details.setVisible(bool(details))
        self.show()
        if timeout:
            self.timer.start(int(timeout * 1000))
        else:
            self.timer.stop()

    def _show_details(self):
        dlg = QDialog(self.window())
        dlg.setWindowTitle(tr("Details"))
        dlg.resize(720, 420)
        lay = QVBoxLayout(dlg)
        ed = QPlainTextEdit(self.details)
        ed.setReadOnly(True)
        lay.addWidget(ed)
        row = QHBoxLayout()
        cp = QPushButton(tr("In Zwischenablage kopieren"))
        cp.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.details))
        ok = QPushButton(tr("Schlie\u00dfen"))
        ok.clicked.connect(dlg.accept)
        row.addWidget(cp)
        row.addStretch()
        row.addWidget(ok)
        lay.addLayout(row)
        dlg.exec()


# ----------------------------------------------------------------- Bausteine
class WheelGuard(QObject):
    """Mausrad ueber Reglern/Feldern scrollt die Seitenleiste, statt Werte zu aendern
    (ausser das Feld wurde vorher angeklickt)."""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Wheel and not isinstance(obj, QScrollBar) and \
                isinstance(obj, (QAbstractSlider, QAbstractSpinBox, QComboBox)):
            if not obj.hasFocus():
                w = obj.parent()
                while w is not None and not isinstance(w, QScrollArea):
                    w = w.parent()
                if w is not None:
                    sb = w.verticalScrollBar()
                    sb.setValue(sb.value() - int(ev.angleDelta().y() / 120 * max(20, sb.singleStep()) * 2))
                return True
        return False


class SliderRow(QWidget):
    changed = Signal()

    def __init__(self, label, lo, hi, val, step=1.0, decimals=0, tip=""):
        super().__init__()
        self.step = step
        self.default = val
        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(decimals)
        self.spin.setRange(lo, hi * 100 if hi > 0 else 100000.0)   # im Feld sind auch gr\u00f6\u00dfere Werte als am Regler m\u00f6glich
        self.spin.setSingleStep(step)
        self.spin.setValue(val)
        self.spin.setFixedWidth(84)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(int(round(lo / step)), int(round(hi / step)))
        self.slider.setValue(int(round(val / step)))
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(QLabel(label))
        top.addStretch()
        top.addWidget(self.spin)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(2)
        lay.addLayout(top)
        lay.addWidget(self.slider)
        self.setToolTip(tip + ("\n\n" if tip else "") + tr("Im Zahlenfeld kann auch ein gr\u00f6\u00dferer Wert als am Regler eingetippt werden."))
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)

    def _from_slider(self, v):
        self.spin.blockSignals(True)
        self.spin.setValue(v * self.step)
        self.spin.blockSignals(False)
        self.changed.emit()

    def _from_spin(self, v):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(v / self.step)))
        self.slider.blockSignals(False)
        self.changed.emit()

    def value(self):
        return self.spin.value()

    def set_silent(self, v):
        for w in (self.spin, self.slider):
            w.blockSignals(True)
        self.spin.setValue(v)
        self.slider.setValue(int(round(v / self.step)))
        for w in (self.spin, self.slider):
            w.blockSignals(False)

    def reset(self):
        self.spin.setValue(self.default)


class Header(QWidget):
    """Einheitliche Ueberschrift fuer Bereiche (gleiche Hoehe und gleicher linker Rand)."""
    clicked = Signal()

    def __init__(self, title, expandable=False):
        super().__init__()
        self.setFixedHeight(30)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 8, 0)
        self.lbl = QLabel(title)
        self.lbl.setObjectName("sec")
        lay.addWidget(self.lbl)
        lay.addStretch()
        self.arrow = QLabel("\u25b8" if expandable else "")
        self.arrow.setObjectName("secarrow")
        lay.addWidget(self.arrow)
        self.expandable = expandable
        if expandable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        if self.expandable:
            self.clicked.emit()


class Section(QWidget):
    def __init__(self, title):
        super().__init__()
        self.header = Header(title)
        self.card = QFrame()
        self.card.setObjectName("card")
        self.body = QVBoxLayout(self.card)
        self.body.setContentsMargins(12, 10, 12, 10)
        self.body.setSpacing(6)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.header)
        lay.addWidget(self.card)


class Collapsible(Section):
    """Eingeklappter Bereich: erst bei Klick auf die Ueberschrift sichtbar."""

    def __init__(self, title, hint=""):
        super().__init__(title)
        self.header.expandable = True
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.arrow.setText("\u25b8")
        self.header.setToolTip(hint)
        self.header.clicked.connect(lambda: self.set_open(not self.card.isVisible()))
        self.card.setVisible(False)

    def set_open(self, on):
        self.card.setVisible(on)
        self.header.arrow.setText("\u25be" if on else "\u25b8")


class ApprovalDialog(QDialog):
    def __init__(self, parent, status, name, date):
        super().__init__(parent)
        self.setWindowTitle(tr("Stempel"))
        lay = QFormLayout(self)
        self.cb = QComboBox()
        self.cb.addItems(rep.APPROVAL_TITLES)
        if status in rep.APPROVAL_TITLES:
            self.cb.setCurrentText(status)
        self.ed_name = QLineEdit(name)
        self.ed_name.setPlaceholderText(tr("Name oder K\u00fcrzel"))
        self.ed_date = QLineEdit(date)
        lay.addRow(tr("Status"), self.cb)
        lay.addRow(tr("Name"), self.ed_name)
        lay.addRow(tr("Datum"), self.ed_date)
        row = QHBoxLayout()
        ok, cancel = QPushButton("OK"), QPushButton(tr("Abbrechen"))
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        row.addStretch()
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addRow(row)

    def text(self):
        return "\n".join(s for s in (self.cb.currentText(), self.ed_name.text().strip(),
                                     self.ed_date.text().strip()) if s)
