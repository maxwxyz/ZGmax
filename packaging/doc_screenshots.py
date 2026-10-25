"""Bildschirmfotos fuer die Anleitungen erzeugen (deutsch und englisch).

    .venv/bin/python packaging/doc_screenshots.py

Schreibt programm/doc_img/de/*.png und programm/doc_img/en/*.png. Beispielzeichnung wird synthetisch erzeugt (keine
echten Daten). Beruehrt keine Nutzereinstellungen (eigener Einstellungs- und Datenordner je Sprache).
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "programm", "doc_img")


def sample(changed=False):
    """Beispiel-Werkstattzeichnung (A4 quer, 150 dpi): Rahmen, Schriftfeld, Bauteil mit Bohrungen, Bemassung, Schnitt
    mit Schraffur. changed=True: Bohrung groesser und versetzt, Mass 120 -> 125, neue Nut, Index B."""
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1754, 1240
    img = np.full((H, W), 255, np.uint8)
    thick, thin = 5, 2
    cv2.rectangle(img, (30, 30), (W - 30, H - 30), 0, thin)
    tb = (W - 560, H - 200)
    cv2.rectangle(img, tb, (W - 30, H - 30), 0, thin)
    for y in (H - 150, H - 100, H - 65):
        cv2.line(img, (tb[0], y), (W - 30, y), 0, 1)
    cv2.line(img, (W - 200, H - 200), (W - 200, H - 30), 0, 1)
    L = 125 if changed else 120
    x0, y0, s = 220, 260, 6.0                                  # Bauteil: 1 mm = 6 px
    x1, y1 = int(x0 + L * s), int(y0 + 80 * s)
    pts = np.array([(x0, y0), (x1 - 40, y0), (x1, y0 + 40), (x1, y1), (x0, y1)], np.int32)
    cv2.polylines(img, [pts], True, 0, thick)
    hx = x0 + int((35 if changed else 30) * s)
    r = int((11 if changed else 10) * s)
    for cx, cy, rr in ((hx, y0 + int(40 * s), r), (x0 + int(85 * s), y0 + int(40 * s), int(8 * s))):
        cv2.circle(img, (cx, cy), rr, 0, thick)
        for k in range(-rr - 25, rr + 25, 18):                  # Mittellinien (Strich)
            cv2.line(img, (cx + k, cy), (cx + min(k + 10, rr + 25), cy), 0, 1)
            cv2.line(img, (cx, cy + k), (cx, cy + min(k + 10, rr + 25)), 0, 1)
    if changed:                                                 # neue Nut
        cv2.rectangle(img, (x0 + int(55 * s), y1 - int(14 * s)), (x0 + int(70 * s), y1), 0, thick)

    def arrow_dim(a, b, off, horiz=True):
        if horiz:
            y = off
            cv2.line(img, (a, y1), (a, y + 10), 0, 1)
            cv2.line(img, (b, y1), (b, y + 10), 0, 1)
            cv2.arrowedLine(img, ((a + b) // 2, y), (a, y), 0, 1, tipLength=0.04)
            cv2.arrowedLine(img, ((a + b) // 2, y), (b, y), 0, 1, tipLength=0.04)
    arrow_dim(x0, x1, y1 + 70)
    sx, sy = 260, 880                                           # Schnitt A-A mit Schraffur
    cv2.rectangle(img, (sx, sy), (sx + 520, sy + 160), 0, thick)
    for k in range(0, 680, 14):
        cv2.line(img, (sx + k, sy), (sx + k - 160, sy + 160), 0, 1)
    img[sy + 3:sy + 158, sx - 200:sx] = 255
    cv2.rectangle(img, (sx, sy), (sx + 520, sy + 160), 0, thick)
    pil = Image.fromarray(img)
    d = ImageDraw.Draw(pil)
    try:
        f = ImageFont.truetype("DejaVuSans.ttf", 26)
        fs = ImageFont.truetype("DejaVuSans.ttf", 20)
    except OSError:
        f = fs = ImageFont.load_default()
    d.text(((x0 + x1) // 2 - 25, y1 + 38), str(L), font=f, fill=0)
    d.text((hx - 60, y0 - 70), "Ø22 H7" if changed else "Ø20 H7", font=f, fill=0)
    d.line([(hx, y0 + int(40 * s) - r), (hx - 20, y0 - 40)], fill=0, width=1)
    d.text((x0 + int(85 * s) - 40, y0 - 70), "Ø16", font=f, fill=0)
    d.text((x1 + 40, y0 + 200), "80 ±0,1", font=f, fill=0)
    d.text((sx, sy - 45), "A-A", font=f, fill=0)
    d.text((tb[0] + 15, H - 190), "ZGmax – Beispielteil Halter", font=f, fill=0)
    d.text((tb[0] + 15, H - 140), "Werkstoff S235JR   Maßstab 1:1", font=fs, fill=0)
    d.text((tb[0] + 15, H - 92), "Zeichnungsnr. 4711-001", font=fs, fill=0)
    d.text((W - 185, H - 140), "Index", font=fs, fill=0)
    d.text((W - 150, H - 100), "B" if changed else "A", font=f, fill=0)
    d.text((80, 60), "Allgemeintoleranzen ISO 2768-m", font=fs, fill=0)
    return np.asarray(pil)


SCENES = r'''
import os, sys, time
from PySide6.QtCore import QSettings, QPointF
from PySide6.QtWidgets import QApplication, QDialog
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, os.environ["ZV_DATA_DIR"])
app = QApplication([])
app.setStyle("Fusion")
from PySide6.QtCore import QLibraryInfo, QTranslator
import i18n
t = QTranslator(app)
if t.load(f"qtbase_{i18n.LANG}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
    app.installTranslator(t)
import drawing_viewer as vw
from PIL import Image
OUT, pa, pb, tmp = sys.argv[1:5]

def pump(n=40):
    for _ in range(n):
        app.processEvents(); time.sleep(0.01)

def wait(cond, t=120):
    t0 = time.time()
    while not cond():
        app.processEvents(); time.sleep(0.01)
        if time.time() - t0 > t: raise TimeoutError

def shot(w, name):
    pump()
    p = os.path.join(OUT, name + ".png")
    w.grab().save(p)
    im = Image.open(p).convert("RGB")
    im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(p, optimize=True)

vw.apply_theme(app, "light")
w = vw.MainWindow(); w.resize(1440, 880); w.show()
shot(w, "start")
w.start.set_intro(False)
w._set_file("A", pa, compute=False); w._set_file("B", pb)
wait(lambda: w.payload is not None and not w.running)
w.act_fit.trigger(); w.banner.hide()
shot(w, "vergleich")
w.review_start(); wait(lambda: not w.running)
shot(w, "pruefen")
w.banner.hide()
w._set_mode("Y"); w.act_fit.trigger()
shot(w, "nebeneinander")
w._set_mode("D")
w.sec_lines.set_open(True)
w.cb_lines.setCurrentIndex(w.cb_lines.findData("contours"))
w.start_compute(); wait(lambda: not w.running)
w.act_fit.trigger(); w.banner.hide()
shot(w, "linienfilter")
w.cb_lines.setCurrentIndex(0); w.start_compute(); wait(lambda: not w.running)
w.find_regs(); wait(lambda: not w.running)
# Massaenderungen: Texte der Aenderungen wie nach "Geaenderte Masse finden"
import diffreport as rep
regs = [r for r in w.payload["regs"] if r["typ"] != "verschoben"]
for r, (ta, tb) in zip(regs, (("120", "125"), ("Ø20 H7", "Ø22 H7"), ("80 ±0,1", "80 ±0,05"))):
    r["text_a"], r["text_b"] = ta, tb
rep.dim_changes(w.payload["regs"])
pdf = os.path.join(tmp, "m.pdf")
rep.build_dim_report(pdf, rep.dim_rows(w.payload["regs"], w.canvas.mm_px), "alt.png", "neu.png")
import pymupdf
with pymupdf.open(pdf) as d:
    d[0].get_pixmap(dpi=110, clip=pymupdf.Rect(0, 0, 842, 260)).save(os.path.join(OUT, "masstabelle.png"))
w.settings.setValue("user_name", "Erika Muster")
orig = QDialog.exec
def grab_exec(self):
    self.show(); shot(self, "abschliessen"); return 0
QDialog.exec = grab_exec
w.review_finish()
QDialog.exec = orig
from ui_dialogs import BatchDialog
da, db, out = (os.path.join(tmp, n) for n in ("Eigener_Stand", "Lieferant", "Ausgabe"))
dlg = BatchDialog(w); dlg.resize(820, 600)
for e, v in zip(dlg.ed, (da, db, out)): e.setText(v)
dlg.chk_idx.setChecked(True); dlg.chk_img.setChecked(False)
dlg.show(); dlg.start(); wait(lambda: dlg.btn_go.isEnabled())
shot(dlg, "ordner"); dlg.close()
w._dirty = False; w.close_document()
w._set_file("A", pb)
wait(lambda: w.payload is not None and not w.running)
w.act_fit.trigger()
c = w.canvas
for a in (dict(type="cloud", x=560, y=180, x2=820, y2=420, text="", nr=0, color="#e11d48", size=2.0),
          dict(type="arrow", x=1000, y=330, x2=850, y2=300, text="", nr=0, color="#e11d48", size=2.0),
          dict(type="text", x=1010, y=300, x2=1300, y2=360, text="Bohrung prüfen", nr=0, color="#e11d48", size=2.0),
          dict(type="number", x=300, y=200, x2=300, y2=200, text="", nr=1, color="#2563eb", size=2.0),
          dict(type="measure", kind="dist", pts=[[220, 790], [970, 790]], x=220, y=790, x2=970, y2=790,
               text="", nr=0, color="#2563eb", size=2.0)):
    w._ann_created(a)
w.act_right.setChecked(True); w.tabs.setCurrentWidget(w.tab_anns)
c.ann_selected = None; w.banner.hide()
shot(w, "markieren")
w._dirty = False; w.close()
'''


def main():
    import shutil
    from PIL import Image
    tmp = os.path.join(tempfile.gettempdir(), "ZGmax-Beispiel")   # lesbarer Pfad in den Bildern
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    pa, pb = os.path.join(tmp, "alt.png"), os.path.join(tmp, "neu.png")
    Image.fromarray(sample(False)).save(pa, dpi=(150, 150))
    Image.fromarray(sample(True)).save(pb, dpi=(150, 150))
    for d, files in (("Eigener_Stand", ("4711-001_A.png", "4711-002.png", "4711-003.png")),
                     ("Lieferant", ("4711-001_B.png", "4711-002.png", "4711-004.png"))):
        os.makedirs(os.path.join(tmp, d))
        for n in files:
            shutil.copy(pb if n.endswith("_B.png") else pa, os.path.join(tmp, d, n))
    script = os.path.join(tmp, "scenes.py")
    with open(script, "w", encoding="utf-8") as f:
        f.write(SCENES)
    for lang in ("de", "en"):
        out = os.path.join(OUT, lang)
        os.makedirs(out, exist_ok=True)
        data = tempfile.mkdtemp()
        env = dict(os.environ, ZV_LANG=lang, ZV_DATA_DIR=data, QT_QPA_PLATFORM="offscreen",
                   PYTHONPATH=os.path.join(ROOT, "programm"))
        subprocess.run([sys.executable, script, out, pa, pb, tmp], env=env, check=True)
        print(lang, sorted(os.listdir(out)))


if __name__ == "__main__":
    main()
