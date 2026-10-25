"""Startseite: zwei Ablagefelder (alt / neu), zuletzt verwendete Dateien, Projekt oeffnen."""
from i18n import tr
from ui_common import *  # noqa: F401,F403
from ui_theme import *  # noqa: F401,F403
from ui_icons import icon


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

    def set_back(self, on):
        self.btn_back.setVisible(on)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self.btn_back.isVisible():
            self.backRequested.emit()
            return
        super().keyPressEvent(e)

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
