"""Startet die Oberflaeche auf Englisch, vergleicht, exportiert und sucht uebersehene deutsche Texte.
Wird von test_english_ui in einem eigenen Prozess aufgerufen (die Sprache steht beim Start fest)."""
import os
import re
import sys
import tempfile

os.environ["ZV_LANG"] = "en"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("ZV_DATA_DIR", tempfile.mkdtemp())
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "programm"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PySide6.QtCore import QSettings  # noqa: E402
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tempfile.mkdtemp())
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QLabel, QLineEdit, QMenu,  # noqa: E402
                               QTabWidget)
import time  # noqa: E402

app = QApplication([])
app.setStyle("Fusion")
import drawing_viewer as vw  # noqa: E402
from PIL import Image  # noqa: E402
from conftest import draw_sheet  # noqa: E402

vw.apply_theme(app, "light")
w = vw.MainWindow()
w.show()
tmp = tempfile.mkdtemp()
pa, pb = os.path.join(tmp, "a.png"), os.path.join(tmp, "b.png")
Image.fromarray(draw_sheet(False)).save(pa, dpi=(200, 200))
Image.fromarray(draw_sheet(True)).save(pb, dpi=(200, 200))


def wait(c, t=60):
    t0 = time.time()
    while not c():
        app.processEvents()
        time.sleep(0.01)
        if time.time() - t0 > t:
            raise TimeoutError


w._set_file("A", pa, compute=False)
w._set_file("B", pb)
wait(lambda: w.payload is not None and not w.running)
w.find_regs()
wait(lambda: not w.running)
w.act_right.setChecked(True)
w.act_left.setChecked(True)
w.act_expert.setChecked(True)
errors = []
assert w.act_compare.text().startswith("Compare"), w.act_compare.text()
GERMAN = re.compile(r"[äöüßÄÖÜ]|\b(und|oder|nicht|Zeichnung|Änderung|Datei|öffnen|speichern|wählen|Vergleich|"
                    r"anzeigen|Einstellung|Bereich|Seite|Markierung|bitte|Ausschnitt|Linie)\b", re.I)
ALLOWED = {"Deutsch", "Sprache / Language"}
seen = []
for wd in w.findChildren(QAbstractButton) + w.findChildren(QLabel):
    seen += [wd.text(), wd.toolTip()]
for wd in w.findChildren(QComboBox):
    seen += [wd.itemText(i) for i in range(wd.count())] + [wd.toolTip()]
for wd in w.findChildren(QLineEdit):
    seen.append(wd.placeholderText())
for wd in w.findChildren(QTabWidget):
    seen += [wd.tabText(i) for i in range(wd.count())]
for a in w.findChildren(QAction):
    seen += [a.text(), a.toolTip()]
for m in w.findChildren(QMenu):
    seen.append(m.title())
for t in seen:
    t = re.sub(r"<[^>]+>", " ", t or "")
    if t and t not in ALLOWED and GERMAN.search(t) and "ZGmax" not in t[:6] and not t.endswith((".tif", ".png")):
        errors.append(t)
for i in range(w.table.columnCount()):                    # Kopfzeile der Aenderungsliste
    t = w.table.horizontalHeaderItem(i).text()
    if GERMAN.search(t):
        errors.append("Tabelle: " + t)
out = os.path.join(tmp, "r.pdf")
w._save_dialog = lambda *a: out
w.export_pdf()
wait(lambda: not w.running)
csv = os.path.join(tmp, "l.csv")
w._save_dialog = lambda *a: csv
w.export_csv()
wait(lambda: not w.running)
head = open(csv, encoding="utf-8-sig").readline()
if "Type" not in head:
    errors.append("CSV: " + head)
w._dirty = False
print("ENGLISH-OK" if not errors else "GERMAN LEFT:\n" + "\n".join(sorted(set(errors))))
