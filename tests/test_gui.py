"""Oberflaeche ohne Bildschirm (offscreen): Laden, Vergleichen, Exportieren, Projekt, Farbschema."""
import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402


@pytest.fixture(scope="session")
def app():
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    a = QApplication.instance() or QApplication([])
    a.setStyle("Fusion")
    return a


@pytest.fixture
def win(app, tmp_path, monkeypatch):
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    import drawing_viewer as vw
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(f"Fehlermeldung: {a[2:]}"))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard)
    vw.apply_theme(app, "light")
    w = vw.MainWindow()
    w.show()
    yield w
    w._dirty = False
    w.close()


def wait(app, cond, timeout=60):
    t = time.time()
    while not cond():
        app.processEvents()
        time.sleep(0.01)
        if time.time() - t > timeout:
            raise TimeoutError("Zeitueberschreitung")


def compare(app, w, pa, pb):
    w._set_file("A", pa, compute=False)
    w._set_file("B", pb)
    wait(app, lambda: w.payload is not None and not w.running)


def test_compare_and_exports(app, win, pair, tmp_path):
    compare(app, win, *pair)
    assert win.payload["res"].oa.any()
    win.find_regs()
    wait(app, lambda: not win.running)
    assert len(win.payload["regs"]) >= 2
    for name, fn in (("e.png", win.export_image), ("e.csv", win.export_csv), ("e.pdf", win.export_pdf)):
        out = str(tmp_path / name)
        win._save_dialog = lambda *a, out=out: out
        fn()
        wait(app, lambda: not win.running)
        assert os.path.getsize(out) > 100, name


def test_project_roundtrip(app, win, pair, tmp_path):
    compare(app, win, *pair)
    win._ann_created(dict(type="text", x=100, y=100, x2=100, y2=100, text="Hallo", nr=0, color="#e11d48", size=2.0))
    win.zones.append((10, 10, 50, 50))
    path = str(tmp_path / "p.zgmax")
    win._save_dialog = lambda *a: path
    assert win.project_save(True)
    data = json.load(open(path))
    assert data["format"] == "zgmax" and data["annotations"][0]["text"] == "Hallo"
    win.anns.clear()
    win.project_open(path)
    wait(app, lambda: not win.running)
    assert win.anns and win.anns[0]["text"] == "Hallo"
    assert win.zones == [(10, 10, 50, 50)]


def test_theme_switch(app, win):
    import drawing_viewer as vw
    for mode in ("dark", "light"):
        win.set_theme(mode)
        assert vw.THEME["canvas"] == vw.THEMES[mode]["canvas"]
        win.grab()


def test_view_only_single_file(app, win, pair):
    win._set_file("A", pair[0])
    wait(app, lambda: win.payload is not None and not win.running)
    assert win.view_only and win.canvas.mode == "A"
    assert win.stack.currentWidget() is win.work
    win.canvas.zoom_step(3.0)
    assert win.canvas.overview_rect() is not None          # hineingezoomt -> Uebersicht sichtbar
    win.grab()


def test_side_by_side_and_navigation(app, win, pair):
    compare(app, win, *pair)
    win._set_mode("Y")
    assert win.canvas.width() == win.canvas.rect().width() // 2
    win.grab()
    s0 = win.canvas.scale
    win.canvas.zoom_step(2.0)
    assert win.canvas.scale == pytest.approx(2 * s0)
    win._set_mode("D")
    win._set_tool("zoom")
    win.canvas.zoomBoxDone.emit()
    assert win.canvas.tool == "zoom"                        # Zoom-Werkzeug bleibt aktiv (wie frueher)
    win.canvas.escapePressed.emit()
    assert win.canvas.tool == "hand"


def test_review_flow_and_project(app, win, pair, tmp_path):
    import diffreport as rep
    compare(app, win, *pair)
    win.review_step(1)                                      # sucht zuerst die Aenderungen
    wait(app, lambda: not win.running)
    win.review_step(1)
    first = win.canvas.selected
    assert first is not None
    win.review_set("ok")
    assert rep.reg_status(win._reg(first)) == "ok" and win.canvas.selected != first
    win.review_set("abgelehnt")
    path = str(tmp_path / "p.zgmax")
    win._save_dialog = lambda *a: path
    assert win.project_save(True)
    win.project_open(path)
    wait(app, lambda: win.payload is not None and not win.running)
    st = sorted(rep.reg_status(r) for r in win.payload["regs"])
    assert "ok" in st and "abgelehnt" in st
    csv = str(tmp_path / "l.csv")
    rep.write_csv(csv, win.payload["regs"])
    assert "gepr" in open(csv, encoding="utf-8-sig").read()


def test_cancel(app, win, pair):
    compare(app, win, *pair)
    win.s_tol.set_silent(3)
    win.start_compute()
    win.cancel_job()
    wait(app, lambda: not win.running)
    assert win.payload is not None                         # altes Ergebnis bleibt


def test_auto_params(app, win, pair):
    compare(app, win, *pair)
    win.auto_params()
    wait(app, lambda: not win.running and "Automatisch" in win.banner.lbl.text())
    wait(app, lambda: not win.running)
    assert 1 <= win.s_tol.value() <= 6


def test_annotations_exports(app, win, pair, tmp_path):
    import pymupdf
    compare(app, win, *pair)
    for t in ("cloud", "highlight", "arrow", "rect"):
        win._ann_created(dict(type=t, x=100, y=100, x2=400, y2=300, text="", nr=0, color="#e11d48", size=2.0))
    win._ann_created(dict(type="number", x=500, y=500, x2=500, y2=500, text="", nr=1, color="#e11d48", size=2.0))
    win._ann_created(dict(type="text", x=600, y=600, x2=600, y2=600, text="Hallo", nr=0, color="#e11d48", size=2.0))
    win.act_clouds.setChecked(True)
    win.find_regs()
    wait(app, lambda: not win.running)
    out = str(tmp_path / "a.pdf")
    win._save_dialog = lambda *a: out
    win.export_annotated_pdf()
    wait(app, lambda: not win.running)
    with pymupdf.open(out) as d:
        kinds = {a.type[1] for a in d[0].annots()}
    assert {"Square", "Line", "FreeText", "Circle"} <= kinds
    img = win.export_render("D", True)
    assert img.shape[0] > 100


def test_multipage_tiff(app, win, tmp_path):
    from PIL import Image
    from conftest import draw_sheet
    pa, pb = tmp_path / "a.tif", tmp_path / "b.tif"
    s1, s2 = Image.fromarray(draw_sheet(False)), Image.fromarray(draw_sheet(True))
    s1.save(pa, save_all=True, append_images=[s1])
    s1.save(pb, save_all=True, append_images=[s2])
    compare(app, win, str(pa), str(pb))
    assert win.n_pages_a == 2 and win.sec_pages.isVisibleTo(win)
    win.compare_all_pages()
    wait(app, lambda: not win.running)
    assert win.page_summary[1] == 0 and win.page_summary[2] > 0


def test_dxf_and_title_block(app, win, tmp_path):
    import ezdxf
    import pymupdf
    import diffcore as dc
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (200, 0))
    msp.add_circle((100, 60), 40)
    dxf = str(tmp_path / "t.dxf")
    doc.saveas(dxf)
    img = dc.read_image(dxf, dpi=100)
    assert img.shape[0] > 50 and (img < 128).any()
    pdf = str(tmp_path / "t.pdf")
    d = pymupdf.open()
    pg = d.new_page(width=842, height=595)
    pg.draw_line((50, 50), (700, 400))
    pg.insert_text((560, 520), "Maßstab 1:5   Zeichnungsnummer 4711-0815   Index C", fontsize=8)
    d.save(pdf)
    win._set_file("A", pdf)
    wait(app, lambda: win.payload is not None and not win.running)
    win.read_title_block()
    wait(app, lambda: not win.running and getattr(win, "title_info", None))
    assert win.title_info["number"] == "4711-0815" and win.title_info["scale_n"] == 5.0


def test_calibrate_from_measure_bar(app, win, pair, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    compare(app, win, *pair)
    win._calibrate()                                        # noch keine Messung -> Messen startet
    assert win.canvas.tool == "measure" and win._calib_pending
    monkeypatch.setattr(QInputDialog, "getDouble", lambda *a, **k: (50.0, True))
    d = 400.0                                               # 400 px bei 200 dpi = 50,8 mm auf dem Blatt
    win.canvas.annCreated.emit(dict(type="measure", kind="dist", pts=[[0, 0], [d, 0]], x=0, y=0, x2=d, y2=0,
                                    text="", nr=0, color="#e11d48", size=2.0))
    wait(app, lambda: not win._calib_pending)
    assert win.scale_n() == pytest.approx(50.0 / 50.8, rel=1e-3)
    assert "Maßstab" in win.lbl_meas_scale.text()


def test_close_document_and_new_window(app, win, pair):
    import drawing_viewer as vw
    compare(app, win, *pair)
    win.close_document()
    assert win.payload is None and win.path_a is None and win.stack.currentWidget() is win.start
    w2 = win.new_window()
    assert w2 in vw.WINDOWS and w2 is not win
    w2._set_file("A", pair[1])
    wait(app, lambda: w2.payload is not None and not w2.running)
    assert w2.view_only
    w2.close()
    assert w2 not in vw.WINDOWS


def test_color_views_and_invert(app, win, tmp_path):
    import cv2
    import numpy as np
    from PIL import Image
    from conftest import draw_sheet
    paths = []
    for name, changed in (("a.png", False), ("b.png", True)):
        g = draw_sheet(changed)
        img = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
        cv2.rectangle(img, (300, 300), (700, 600), (0, 0, 255), 6)            # rote Kontur = Farbe in der Datei
        p = tmp_path / name
        Image.fromarray(img[:, :, ::-1]).save(p, dpi=(200, 200))
        paths.append(str(p))
    compare(app, win, *paths)
    ca, cb = win.payload["color"]
    assert ca is not None and cb.shape[:2] == win.payload["res"].a.shape
    assert (cb[300:310, 400:600, 2] > 200).any() and (cb[300:310, 400:600, 0] < 80).any()   # rot bleibt rot
    win._set_mode("A")
    layer = win.canvas._layer("A", 0, 290, 320, 400, 600)
    assert (layer[:, :, 2].astype(int) - layer[:, :, 0] > 100).any()             # Anzeige farbig
    win._set_mode("D")
    assert win.canvas._layer("D", 0, 290, 320, 400, 600).ndim == 3
    win.act_invert.setChecked(True)
    win.grab()
    win._set_mode("Y")
    win.grab()
    win.act_invert.setChecked(False)
    img = win.export_render("B", False, legend=False)
    assert (img[:, :, 2].astype(int) - img[:, :, 0] > 100).any()               # Export Neu in Farbe
