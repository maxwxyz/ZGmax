"""Gemeinsame Importe und Konstanten der Oberflaeche."""
import copy
import datetime as dt
import json
import math
import os
import subprocess
import sys

import cv2
import numpy as np
from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSettings, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import (QAction, QActionGroup, QColor, QDesktopServices, QFont, QGuiApplication, QIcon,
                           QImage, QKeySequence, QPainter, QPainterPath, QPalette, QPen, QPixmap, QPolygonF, QShortcut,
                           QTransform)
from PySide6.QtWidgets import (QAbstractItemView, QAbstractSlider, QAbstractSpinBox, QApplication, QCheckBox,
                               QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QScrollBar, QSizePolicy,
                               QSlider, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QToolBar,
                               QStackedWidget, QToolButton, QVBoxLayout, QWidget)

import diffcore as dc
import diffpipe as dp
import diffreport as rep
import diffvector as dv

APP = "ZGmax"
APP_SUBTITLE = "Zeichnungen ansehen, vergleichen und pr\u00fcfen"
ACCENT = "#2563eb"
FILE_FILTER = ("Zeichnungen (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp *.jp2 *.gif *.pdf *.svg *.xps *.dxf);;"
               "Alle Dateien (*)")
FROZEN = bool(getattr(sys, "frozen", False))        # als App (PyInstaller) gestartet
# Programmdateien (Anleitung, Symbole): im App-Paket im Ressourcenordner, sonst neben den .py-Dateien
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(HERE)
TOOL_HINTS = {
    "hand": "Auswahl: Markierungen anklicken und verschieben. Leeres Papier ziehen = Ansicht verschieben.",
    "measure": "Punkte anklicken (L\u00e4nge 2, Winkel/Radius 3). Linienzug/Fl\u00e4che: Doppelklick, Enter oder "
               "Rechtsklick beendet. Esc = abbrechen.",
    "zoom": "Bereich aufziehen, dann wird hineingezoomt. Einfacher Klick = ganze Zeichnung.",
    "region": "Rahmen um den ge\u00e4nderten Bereich aufziehen; er kommt in die \u00c4nderungsliste.",
    "text": "Ins Bild klicken, dann den Text eingeben.",
    "number": "Ins Bild klicken. Jeder Klick setzt die n\u00e4chste Nummer. Esc = fertig.",
    "rect": "Rahmen im Bild aufziehen.",
    "cloud": "Revisionswolke im Bild aufziehen.",
    "highlight": "Fl\u00e4che aufziehen, die farbig hinterlegt wird (Textmarker).",
    "arrow": "Vom Pfeilanfang zur Spitze ziehen.",
    "approval": "Ins Bild klicken, Status und Name w\u00e4hlen.",
    "zone": "Rahmen aufziehen. Dieser Bereich wird beim n\u00e4chsten Vergleich nicht verglichen.",
    "crop": "Rahmen aufziehen. Nur dieser Bereich wird verglichen (schneller).",
}


# ----------------------------------------------------------------- Hauptfenster
PROJECT_EXT = ".zgmax"


def shift_ann(a, dx, dy):
    """Verschiebt eine Anmerkung (inkl. Messpunkte) um dx, dy."""
    for k, d in (("x", dx), ("x2", dx), ("y", dy), ("y2", dy)):
        if k in a:
            a[k] += d
    if a.get("pts"):
        a["pts"] = [[q[0] + dx, q[1] + dy] + list(q[2:]) for q in a["pts"]]


import logging  # noqa: E402

log = logging.getLogger("zeichnungsvergleich")
DRAWING_EXT = tuple(sorted(dc.RASTER_EXT | dc.VECTOR_EXT | {".dxf"}))


def app_settings():
    """Programmeinstellungen. Format folgt QSettings.defaultFormat() (Tests leiten so in eine eigene Datei um)."""
    from PySide6.QtCore import QSettings
    return QSettings(QSettings.defaultFormat(), QSettings.Scope.UserScope, "drawing_diff", "viewer")


TYPE_SHOW = {"entfernt": "entfernt", "neu": "neu", "geaendert": "ge\u00e4ndert", "verschoben": "verschoben"}


def app_data_dir():
    """Ordner fuer Logdatei, automatische Sicherung usw. (wird angelegt)."""
    from PySide6.QtCore import QStandardPaths
    d = os.environ.get("ZV_DATA_DIR") or \
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation) or os.path.expanduser("~")
    os.makedirs(d, exist_ok=True)
    return d


def recent_list(settings):
    """Zuletzt geoeffnet: Liste von dicts {a, b, project} (neueste zuerst)."""
    try:
        data = json.loads(settings.value("recent", "[]") or "[]")
        return [r for r in data if isinstance(r, dict)][:12]
    except (ValueError, TypeError):
        return []


def recent_add(settings, a=None, b=None, project=None):
    entry = {"a": a, "b": b, "project": project}
    lst = [r for r in recent_list(settings) if r != entry]
    settings.setValue("recent", json.dumps([entry] + lst[:11]))


def recent_label(r):
    if r.get("project"):
        return "Projekt: " + os.path.basename(r["project"])
    if r.get("a") and r.get("b"):
        return f"{os.path.basename(r['a'])}  →  {os.path.basename(r['b'])}"
    return os.path.basename(r.get("a") or r.get("b") or "?")
