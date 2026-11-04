"""Startseite: zwei Ablagefelder (alt / neu), zuletzt verwendete Dateien, Projekt oeffnen."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_icons import icon
from PySide6.QtGui import QCursor


class DropCard(QFrame):
    """Ablagefeld fuer eine Zeichnung (Klick oder Datei hineinziehen)."""
    chosen = Signal(str)
    browse = Signal()

    def __init__(self, title, hint):
        super().__init__()
        self.setObjectName("dropcard")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(250, 170)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        self.title = QLabel(title)
        self.title.setObjectName("cardtitle")
        self.file = QLabel(hint)
        self.file.setObjectName("hint")
        self.file.setWordWrap(True)
        self.btn = QPushButton(tr("Datei wählen …"))
        self.btn.setIcon(icon("open"))
        self.btn.clicked.connect(self.browse.emit)
        lay.addWidget(self.title)
        lay.addWidget(self.file, 1)
        lay.addWidget(self.btn, 0, Qt.AlignmentFlag.AlignLeft)

    def set_file(self, path):
        self.file.setText(os.path.basename(path) if path else tr("Noch keine Datei"))
        self.file.setToolTip(path or "")
        self.setProperty("filled", bool(path))
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, e):
        self.browse.emit()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if files:
            self.chosen.emit(files[0])
            e.acceptProposedAction()


class StartPage(QWidget):
    fileChosen = Signal(str, str)          # ("A"/"B", Pfad)
    browse = Signal(str)                   # "A"/"B"
    recentChosen = Signal(dict)
    projectRequested = Signal()
    viewOnly = Signal()
    backRequested = Signal()               # zurueck zur offenen Zeichnung
    introClosed = Signal()                 # Einfuehrung "Verstanden"

    def __init__(self):
        super().__init__()
        self.setObjectName("startpage")
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        col = QWidget()
        col.setMaximumWidth(820)
        lay = QVBoxLayout(col)
        lay.setSpacing(14)
        brand = QLabel(tr("{}  <span style='font-weight:400'>· {}</span>").format(APP, APP_SUBTITLE))
        brand.setObjectName("brand")
        top = QHBoxLayout()
        top.addWidget(brand)
        top.addStretch()
        self.btn_back = QPushButton(tr("← Zurück zur Zeichnung"))   # nur sichtbar, wenn schon etwas offen ist
        self.btn_back.setObjectName("primary")
        self.btn_back.setToolTip(tr("Zur geöffneten Zeichnung zurück (Esc)"))
        self.btn_back.clicked.connect(self.backRequested.emit)
        self.btn_back.setVisible(False)
        top.addWidget(self.btn_back)
        lay.addLayout(top)
        h = QLabel(tr("Zeichnungen vergleichen oder ansehen"))
        h.setObjectName("bigtitle")
        sub = QLabel(tr("Zwei Dateien hierher ziehen (alt und neu) – oder links die alte und rechts die neue "
                     "Zeichnung wählen. Der Vergleich startet von selbst. Eine einzelne Datei wird nur angezeigt."))
        sub.setObjectName("hint")
        sub.setWordWrap(True)
        lay.addWidget(h)
        lay.addWidget(sub)
        self.intro = self._build_intro()
        lay.addWidget(self.intro)
        row = QHBoxLayout()
        row.setSpacing(16)
        self.card_a = DropCard(tr("Alte Zeichnung (A)"), tr("Noch keine Datei"))
        self.card_b = DropCard(tr("Neue Zeichnung (B)"), tr("Noch keine Datei"))
        for w, c in (("A", self.card_a), ("B", self.card_b)):
            c.chosen.connect(lambda p, w=w: self.fileChosen.emit(w, p))
            c.browse.connect(lambda w=w: self.browse.emit(w))
            row.addWidget(c, 1)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.btn_view = QPushButton(tr("Nur ansehen"))
        self.btn_view.setToolTip(tr("Die gewählte Zeichnung ohne Vergleich anzeigen (zoomen, messen, markieren)"))
        self.btn_view.clicked.connect(self.viewOnly.emit)
        self.btn_view.setEnabled(False)
        b = QPushButton(tr("Projekt öffnen …"))
        b.clicked.connect(self.projectRequested.emit)
        row.addWidget(self.btn_view)
        row.addStretch()
        row.addWidget(b)
        lay.addLayout(row)
        self.lbl_recent = QLabel(tr("Zuletzt verwendet"))
        self.lbl_recent.setObjectName("sec")
        lay.addWidget(self.lbl_recent)
        self.recent = QListWidget()
        self.recent.setObjectName("recent")
        self.recent.setMaximumHeight(220)
        self.recent.itemActivated.connect(self._recent)
        self.recent.itemClicked.connect(self._recent)
        lay.addWidget(self.recent)
        center = QHBoxLayout()
        center.addStretch(1)
        center.addWidget(col, 4)
        center.addStretch(1)
        outer.addLayout(center)
        outer.addStretch(2)

    def _build_intro(self):
        """Kurze Einfuehrung in drei Schritten (beim ersten Start; Hilfe -> Einfuehrung zeigt sie wieder)."""
        card = QFrame()
        card.setObjectName("introcard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        head = QHBoxLayout()
        t = QLabel(tr("So geht's – in drei Schritten"))
        t.setObjectName("cardtitle")
        head.addWidget(t)
        head.addStretch()
        b = QPushButton(tr("Verstanden"))
        b.clicked.connect(lambda: (card.hide(), self.introClosed.emit()))
        head.addWidget(b)
        lay.addLayout(head)
        row = QHBoxLayout()
        row.setSpacing(18)
        for nr, title, text in (
                ("1", tr("Öffnen"), tr("Alte Zeichnung links, neue rechts ablegen. Eine einzelne Datei wird nur "
                                       "angezeigt – zum Messen und Markieren.")),
                ("2", tr("Vergleichen"), tr("Startet von selbst. Rot = nur in alt, blau = nur in neu, grün = nur "
                                            "verschoben, grau = gleich.")),
                ("3", tr("Prüfen"), tr("„Prüfen starten“ zeigt jede Änderung: G = geprüft, X = abgelehnt, "
                                       "C = Kommentar. Am Ende „Prüfung abschließen“."))):
            col = QVBoxLayout()
            col.setSpacing(2)
            top = QHBoxLayout()
            top.setSpacing(8)
            n = QLabel(nr)
            n.setObjectName("stepnr")
            tt = QLabel(title)
            tt.setObjectName("sec")
            top.addWidget(n)
            top.addWidget(tt, 1)
            col.addLayout(top)
            d = QLabel(text)
            d.setObjectName("hint")
            d.setWordWrap(True)
            col.addWidget(d)
            col.addStretch()
            row.addLayout(col, 1)
        lay.addLayout(row)
        card.hide()
        return card

    def set_intro(self, on):
        self.intro.setVisible(on)

    def set_back(self, on):
        self.btn_back.setVisible(on)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self.btn_back.isVisible():
            self.backRequested.emit()
            return
        super().keyPressEvent(e)

    def refresh_icons(self):
        """Nach einem Wechsel des Farbschemas: Symbole neu zeichnen (sonst dunkel auf dunkel)."""
        for c in (self.card_a, self.card_b):
            c.btn.setIcon(icon("open"))

    def set_files(self, a, b):
        self.card_a.set_file(a)
        self.card_b.set_file(b)
        self.btn_view.setEnabled(bool(a or b) and not (a and b))

    def set_recent(self, entries):
        self.recent.clear()
        for r in entries:
            it = QListWidgetItem(recent_label(r))
            it.setToolTip("\n".join(v for v in (r.get("project"), r.get("a"), r.get("b")) if v))
            it.setData(Qt.ItemDataRole.UserRole, r)
            self.recent.addItem(it)
        self.recent.setVisible(bool(entries))
        self.lbl_recent.setVisible(bool(entries))

    def _recent(self, it):
        self.recentChosen.emit(it.data(Qt.ItemDataRole.UserRole))


class DropOverlay(QWidget):
    """Ziele beim Hineinziehen einer Datei, wenn schon eine Zeichnung offen ist (wie die Felder der Startseite):
    zusaetzlich in neuem Fenster, stattdessen, oder als Alt (A) / Neu (B) vergleichen. Ablegen ausserhalb der Ziele
    = wie bisher in neuem Fenster."""
    chosen = Signal(str, list)             # (Ziel, Dateien)

    def __init__(self, parent):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.files, self.cards = [], []
        self._watch = QTimer(self)                        # Sicherheitsnetz: Maus nicht mehr ueber dem Fenster oder
        self._watch.setInterval(300)                      # Ziehen abgebrochen, ohne dass das System es meldet
        self._watch.timeout.connect(self._check_gone)
        self.hide()
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        self.title = QLabel("")
        self.title.setObjectName("cardtitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.title)
        sub = QLabel(tr("Auf ein Feld ziehen – außerhalb der Felder ablegen öffnet in einem neuen Fenster."))
        sub.setObjectName("hint")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(sub)
        self.row = QHBoxLayout()
        self.row.setSpacing(16)
        outer.addLayout(self.row)
        outer.addStretch(1)
        outer.setContentsMargins(40, 40, 40, 40)

    def open(self, files, targets):
        """targets: [(Schluessel, Titel, Hinweis), ...]"""
        self.files = files
        while self.row.count():
            w = self.row.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.cards = []
        self.row.addStretch(1)
        for key, title, hint in targets:
            c = QFrame()
            c.setObjectName("dropcard")
            c.setFixedSize(230, 130)
            lay = QVBoxLayout(c)
            t = QLabel(title)
            t.setObjectName("cardtitle")
            t.setWordWrap(True)
            h = QLabel(hint)
            h.setObjectName("hint")
            h.setWordWrap(True)
            lay.addWidget(t)
            lay.addWidget(h, 1)
            c._key = key
            self.row.addWidget(c)
            self.cards.append(c)
        self.row.addStretch(1)
        names = ", ".join(os.path.basename(f) for f in files[:3]) + (" …" if len(files) > 3 else "")
        self.title.setText(tr("{} – wohin damit?").format(names))
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        self._watch.start()

    def hideEvent(self, e):
        self._watch.stop()
        super().hideEvent(e)

    def _check_gone(self):
        """Ueberlay entfernen, sobald die Maus nicht mehr ueber dem Fenster ist (Ziehen abgebrochen oder woanders
        hin) - dann kann man normal weiterarbeiten."""
        if not self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            self.hide()

    def _card_at(self, pos):
        for c in self.cards:                              # Karten sind Kinder des Overlays: gleiche Koordinaten
            if c.geometry().contains(pos):
                return c
        return None

    def _highlight(self, pos):
        hit = self._card_at(pos)
        for c in self.cards:
            on = c is hit
            if bool(c.property("filled")) != on:
                c.setProperty("filled", on)
                c.style().unpolish(c)
                c.style().polish(c)
        return hit

    def paintEvent(self, e):
        p = QPainter(self)
        col = QColor(THEME["canvas"])
        col.setAlpha(225)
        p.fillRect(self.rect(), col)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        self._highlight(e.position().toPoint())
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.hide()

    def dropEvent(self, e):
        hit = self._card_at(e.position().toPoint())
        files = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()] or self.files
        self.hide()
        e.acceptProposedAction()
        self.chosen.emit(hit._key if hit else "window", files)

    def keyPressEvent(self, e):
        self.hide()                                       # jede Taste (z. B. Esc) schliesst die Ziele

    def mousePressEvent(self, e):
        self.hide()                                       # Klick = weiterarbeiten
