"""Farbschema hell/dunkel: Stylesheet, Palette, Umschalten."""
from ui_common import *  # noqa: F401,F403

UI_FONT = "Segoe UI" if os.name == "nt" else ("Helvetica Neue" if sys.platform == "darwin" else "DejaVu Sans")

# ----------------------------------------------------------------- Farbschema (hell / dunkel)
# Die Zeichnung selbst bleibt immer schwarz auf weiss (wie im gespeicherten Ergebnis); umgefaerbt
# werden Fenster, Bedienelemente und die Flaeche um die Zeichnung.
THEMES = {
    "light": dict(
        accent=ACCENT, accent_hover="#1d4ed8", accent_off="#93b4f5",
        window="#f4f5f7", surface="#ffffff", border="#e0e3e8", border2="#cfd5de",
        text="#1f2937", text2="#374151", muted="#6b7280", disabled="#9ca3af",
        hover="#eef1f6", sel_bg="#dbe7fd", sel_fg="#111827", on_bg="#dbe7fd", on_hover="#c9dafc", on_fg="#1d4ed8", grid="#eef0f3", groove="#dde1e8", track="#e5e8ee",
        canvas="#e6e9ef", frame="#9aa3b2", legend_bg=(255, 255, 255, 225), segbg="#eceef2", seghover="#e2e5ea",
        info_bg="#e8f0fe", info_fg="#1e3a8a", warn_bg="#fef3c7", warn_fg="#78350f", err_bg="#fee2e2", err_fg="#7f1d1d",
        name="light"),
    "dark": dict(
        accent="#3b82f6", accent_hover="#2563eb", accent_off="#34507f",
        window="#1c1f24", surface="#262a31", border="#353b44", border2="#4a515c",
        text="#e5e7eb", text2="#d1d5db", muted="#9ca3af", disabled="#6b7280",
        hover="#323842", sel_bg="#1e3a6e", sel_fg="#f3f4f6", on_bg="#1e3a6e", on_hover="#25467f", on_fg="#93c0ff", grid="#30353c", groove="#3a4049", track="#353b44",
        canvas="#15171b", frame="#5b6472", legend_bg=(38, 42, 49, 230), segbg="#1c1f24", seghover="#2c3139",
        info_bg="#1e2f52", info_fg="#dbe7fd", warn_bg="#463710", warn_fg="#fde68a", err_bg="#4c1d1d", err_fg="#fecaca",
        name="dark"),
}
THEME = dict(THEMES["light"])           # aktuelles Schema; wird von apply_theme() ersetzt


# Hinweis: Spinboxen und Comboboxen werden bewusst NICHT per Stylesheet gestaltet,
# sonst verschwinden ihre Pfeile. Ihre Farben kommen aus der Palette (make_palette).
def make_qss(t):
    return f"""
* {{ font-family: "{UI_FONT}", Arial; font-size: 10pt; color: {t['text']}; }}
QMainWindow, QWidget#panel {{ background: {t['window']}; }}
QToolBar {{ background: {t['surface']}; border: none; border-bottom: 1px solid {t['border']}; spacing: 4px; padding: 4px 10px; }}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 5px 12px; }}
QToolButton:hover {{ background: {t['hover']}; }}
QToolButton:checked {{ background: {t['on_bg']}; color: {t['on_fg']}; border: 1px solid {t['on_bg']}; }}
QToolButton:checked:hover {{ background: {t['on_hover']}; }}
QToolButton::menu-indicator {{ image: none; }}
QToolButton#qt_toolbar_ext_button {{ background: #f59e0b; color: white; font-weight: 700; border-radius: 6px; min-width: 34px; padding: 2px 8px; font-size: 16px; }}
QToolButton#qt_toolbar_ext_button:hover {{ background: #d97706; }}
QLabel#sec {{ font-weight: 600; color: {t['text2']}; }}
QLabel#secarrow {{ color: {t['muted']}; }}
QLabel#toolbarlabel {{ color: {t['muted']}; padding: 0 4px 0 8px; }}
QFrame#card {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; }}
QPushButton {{ background: {t['surface']}; border: 1px solid {t['border2']}; border-radius: 6px; padding: 6px 12px; }}
QPushButton:hover {{ background: {t['hover']}; }}
QPushButton:disabled {{ color: {t['disabled']}; background: {t['window']}; }}
QPushButton#primary {{ background: {t['accent']}; border-color: {t['accent']}; color: white; font-weight: 600; padding: 8px 12px; }}
QPushButton#primary:hover {{ background: {t['accent_hover']}; }}
QPushButton#primary:disabled {{ background: {t['accent_off']}; border-color: {t['accent_off']}; color: white; }}
QSlider::groove:horizontal {{ height: 4px; background: {t['groove']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {t['surface']}; border: 2px solid {t['accent']}; width: 12px; height: 12px; margin: -6px 0; border-radius: 8px; }}
QTableWidget, QListWidget, QPlainTextEdit {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; gridline-color: {t['grid']}; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: {t['sel_bg']}; color: {t['sel_fg']}; }}
QHeaderView::section {{ background: {t['window']}; border: none; border-bottom: 1px solid {t['border']}; padding: 4px 6px; color: {t['muted']}; font-weight: 600; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ padding: 6px 14px; background: transparent; border: none; color: {t['muted']}; }}
QTabBar::tab:selected {{ color: {t['text']}; font-weight: 600; border-bottom: 2px solid {t['accent']}; }}
QStatusBar {{ background: {t['surface']}; border-top: 1px solid {t['border']}; }}
QScrollArea {{ border: none; background: transparent; }}
QProgressBar {{ border: none; background: {t['track']}; border-radius: 3px; max-height: 6px; }}
QProgressBar::chunk {{ background: {t['accent']}; border-radius: 3px; }}
QLabel#hint {{ color: {t['muted']}; }}
QLabel#file {{ background: {t['window']}; border: 1px solid {t['border']}; border-radius: 5px; padding: 4px 8px; }}
QToolBar#main QToolButton {{ padding: 5px 9px; }}
QFrame#segbox {{ background: {t['segbg']}; border-radius: 9px; }}
QToolBar#main QToolButton#modechip {{ background: {t['segbg']}; color: {t['accent']}; border: 1px solid transparent;
                  border-radius: 9px; padding: 5px 10px; font-weight: 600; margin-left: 4px; margin-right: 4px; }}
QToolBar#main QToolButton#modechip:hover {{ background: {t['seghover']}; }}
QToolBar#main QToolButton#modechip::menu-indicator {{ image: none; width: 0; }}
QToolBar#main QToolButton#modechip[single="true"] {{ color: {t['text2']}; }}
QToolBar#main QToolButton#modechip[dirty="true"] {{ border: 1px solid {t['accent']}; }}
QToolButton#seg {{ background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 4px 8px;
                  color: {t['text2']}; }}
QToolButton#seg:hover {{ background: {t['seghover']}; }}
QToolButton#seg:checked {{ background: {t['surface']}; border: 1px solid {t['border2']}; color: {t['accent']};
                          font-weight: 600; }}
QFrame#palette {{ background: {t['surface']}; border-right: 1px solid {t['border']}; }}
QFrame#palette QToolButton {{ padding: 4px 2px; border-radius: 8px; font-size: 8.5pt; }}
QFrame#palette QToolButton::menu-button {{ background: transparent; border: none; width: 12px; }}
QFrame#banner {{ border-radius: 0; border-bottom: 1px solid {t['border']}; }}
QFrame#searchbar {{ background: {t['surface']}; border-bottom: 1px solid {t['border']}; }}
QFrame#optbar {{ background: {t['window']}; border-bottom: 1px solid {t['border']}; }}
QFrame#banner[kind="info"] {{ background: {t['info_bg']}; }}
QFrame#banner[kind="info"] QLabel {{ color: {t['info_fg']}; }}
QFrame#banner[kind="warn"] {{ background: {t['warn_bg']}; }}
QFrame#banner[kind="warn"] QLabel {{ color: {t['warn_fg']}; }}
QFrame#banner[kind="error"] {{ background: {t['err_bg']}; }}
QFrame#banner[kind="error"] QLabel {{ color: {t['err_fg']}; }}
QWidget#startpage {{ background: {t['canvas']}; }}
QLabel#bigtitle {{ font-size: 18pt; font-weight: 600; }}
QLabel#brand {{ font-size: 11pt; font-weight: 700; color: {t['accent']}; }}
QLabel#cardtitle {{ font-size: 12pt; font-weight: 600; }}
QFrame#dropcard {{ background: {t['surface']}; border: 2px dashed {t['border2']}; border-radius: 12px; }}
QFrame#dropcard:hover {{ border-color: {t['accent']}; }}
QFrame#dropcard[filled="true"] {{ border-style: solid; border-color: {t['accent']}; }}
QListWidget#recent {{ padding: 4px; }}
QListWidget#recent::item {{ padding: 6px 8px; border-radius: 6px; }}
QListWidget#recent::item:hover {{ background: {t['hover']}; }}
QListView::item {{ padding: 2px 0px; }}
QCheckBox::indicator, QAbstractItemView::indicator {{ width: 15px; height: 15px; border: 1.5px solid {t['muted']}; border-radius: 4px; background: {t['surface']}; }}
QCheckBox::indicator:checked, QAbstractItemView::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; image: url("{t.get('check_png', '')}"); }}
QCheckBox::indicator:disabled {{ border-color: {t['disabled']}; background: {t['window']}; }}
QLabel#status_ok {{ color: #16a34a; font-weight: 600; }}
QLabel#ok {{ color: #16a34a; font-weight: 600; }}
QLabel#warn {{ color: #c2410c; font-weight: 600; }}
QFrame#introcard {{ background: {t['surface']}; border: 1px solid {t['accent']}; border-radius: 10px; }}
QLabel#stepnr {{ color: {t['accent']}; font-size: 16pt; font-weight: 700; }}
QLabel#zoomlabel {{ min-width: 52px; qproperty-alignment: AlignCenter; }}
"""



def make_palette(t):
    """Palette passend zum Stylesheet: Eingabefelder, Listen, Menues und Dialoge, die nicht per
    Stylesheet gestaltet sind, bekommen so Hintergrund und Schrift des gewaehlten Schemas."""
    pal = QPalette()
    R, G = QPalette.ColorRole, QPalette.ColorGroup
    for role, key in ((R.Window, "window"), (R.WindowText, "text"), (R.Base, "surface"),
                      (R.AlternateBase, "hover"), (R.Text, "text"), (R.Button, "surface"),
                      (R.ButtonText, "text"), (R.ToolTipBase, "surface"), (R.ToolTipText, "text"),
                      (R.PlaceholderText, "disabled"), (R.Highlight, "accent"), (R.Link, "accent"),
                      (R.Light, "surface"), (R.Midlight, "border"), (R.Mid, "border2"),
                      (R.Dark, "frame"), (R.Shadow, "canvas")):
        pal.setColor(role, QColor(t[key]))
    pal.setColor(R.HighlightedText, QColor("white"))
    pal.setColor(R.BrightText, QColor("white"))
    for role in (R.Text, R.WindowText, R.ButtonText):
        pal.setColor(G.Disabled, role, QColor(t["disabled"]))
    return pal


def theme_setting(settings):
    mode = settings.value("theme", "auto")
    return mode if mode in ("auto", "light", "dark") else "auto"


def system_is_dark():
    hints = QGuiApplication.styleHints()
    return hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark


def _check_png():
    """Weisses Haekchen fuer angehakte Felder (als Datei, weil das Stylesheet eine Bilddatei braucht)."""
    path = os.path.join(app_data_dir(), "haken.png")
    if not os.path.isfile(path):
        from PySide6.QtGui import QPainter, QPen, QPixmap
        pm = QPixmap(30, 30)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("white"), 3.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline([QPointF(7, 15.5), QPointF(12.5, 21), QPointF(23, 9)])
        p.end()
        pm.save(path)
    return path.replace("\\", "/")


def apply_theme(app, mode):
    """mode: 'auto' (wie das Betriebssystem), 'light' oder 'dark'. Gibt das benutzte Schema zurueck."""
    hints = app.styleHints()
    if mode == "auto":
        if hasattr(hints, "unsetColorScheme"):          # Qt >= 6.8: wieder dem System folgen
            hints.unsetColorScheme()
        name = "dark" if system_is_dark() else "light"
    else:
        name = mode
        if hasattr(hints, "setColorScheme"):            # Qt >= 6.8: auch Titelleiste und native Dialoge
            hints.setColorScheme(Qt.ColorScheme.Dark if mode == "dark" else Qt.ColorScheme.Light)
    THEME.clear()
    THEME.update(THEMES[name])
    THEME["check_png"] = _check_png()
    app.setPalette(make_palette(THEME))
    app.setStyleSheet(make_qss(THEME))
    for w in app.topLevelWidgets():
        w.update()
    return name
