"""Oberflaeche ohne Bildschirm (offscreen): Laden, Vergleichen, Exportieren, Projekt, Farbschema."""
import json
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSettings, Qt  # noqa: E402
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
    import drawing_viewer as vw
    win.project_open(path)                                   # schon etwas offen: Projekt im eigenen Fenster
    other = vw.WINDOWS[-1]
    assert other is not win
    wait(app, lambda: not other.running)
    assert other.anns and other.anns[0]["text"] == "Hallo"
    assert other.zones == [(10, 10, 50, 50)]
    other._dirty = False
    other.close()


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


def test_move_region_undo_and_save(app, win, tmp_path, monkeypatch):
    import cv2
    import numpy as np
    img = np.full((600, 800), 255, np.uint8)
    cv2.rectangle(img, (100, 100), (200, 180), 0, 4)          # Kasten, der verschoben wird
    p = tmp_path / "blatt.png"
    cv2.imwrite(str(p), img)
    win._set_file("A", str(p))
    wait(app, lambda: win.payload is not None and not win.running)
    assert win.view_only and win.act_move_sel.isEnabled()
    win.start_move_region()
    win.chk_float_lines.setChecked(True)
    win._sel_move(90, 90, 120, 100)
    assert win.canvas.float is not None and win.btn_float_ok.isEnabled()
    win.canvas.float["dx"], win.canvas.float["dy"] = 300, 200
    win._float_done(True)
    g = win.cache["g_" + str(p)]
    assert g[100:181, 100:201].min() > 200                    # alte Stelle leer (Papier)
    assert g[300:381, 400:501].min() < 50                     # Kasten an der neuen Stelle
    assert win.payload["res"].a[300:381, 400:501].max() > 0   # Linienmaske nachgezogen
    assert win.drawing_edited() and win.act_save_drawing.isEnabled()
    win.undo()
    assert g[100:181, 100:201].min() < 50 and g[300:381, 400:501].min() > 200
    win.redo()
    assert g[300:381, 400:501].min() < 50
    out = tmp_path / "neu.png"
    win._save_dialog = lambda *a: str(out)
    assert win.save_drawing() and cv2.imread(str(out), 0)[300:381, 400:501].min() < 50
    assert not win.drawing_edited()


def test_copy_selection_geometry(app, win, pair, monkeypatch):
    import ui_edit
    seen = {}

    def fake_exec(dlg):
        for mode in ("all", "lines", "geometry"):
            dlg.cb_mode.setCurrentIndex(dlg.cb_mode.findData(mode))
            seen[mode] = dlg.result.copy()
        dlg._copy()
        return 1
    monkeypatch.setattr(ui_edit.CopyDialog, "exec", fake_exec)
    compare(app, win, *pair)
    win.seg_buttons["B"].click()
    win.start_copy_selection()
    assert win.canvas.tool == "copysel"
    win._sel_copy(50, 50, 400, 300)
    assert seen["all"].shape == (300, 400, 4) and seen["all"][..., 3].min() == 255
    assert seen["lines"][..., 3].min() == 0                   # Hintergrund durchsichtig
    assert QApplication.clipboard().mimeData().hasImage()
    assert win.canvas.tool == "hand"
    QApplication.clipboard().clear()                         # offscreen: Zwischenablage nicht ueber das Ende halten


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


def test_multi_select_and_delete(app, win, pair):
    compare(app, win, *pair)
    for k in range(4):
        win._ann_created(dict(type="rect", x=100 + 300 * k, y=100, x2=300 + 300 * k, y2=250, text="", nr=0,
                              color="#e11d48", size=2.0))
    c = win.canvas
    c._set_multi({0, 2})                                     # wie Strg+Klick auf zwei Rahmen
    assert {it.text() for it in win.list_anns.selectedItems()} and len(win.list_anns.selectedItems()) == 2
    win.s_asize.setValue(5.0)                                # Groesse gilt fuer beide
    assert win.anns[0]["size"] == 5.0 and win.anns[2]["size"] == 5.0 and win.anns[1]["size"] == 2.0
    win._ann_delete()
    assert len(win.anns) == 2 and [a["x"] for a in win.anns] == [400, 1000]
    win.list_anns.selectAll()                                # Auswahl in der Liste, Entf
    assert c.selected_anns() == {0, 1}
    win.list_anns.setFocus()
    win._ann_delete()
    assert win.anns == []
    win.undo()
    assert len(win.anns) == 2


def test_annotated_pdf_only_shown_changes(app, win, pair, tmp_path):
    import pymupdf
    compare(app, win, *pair)
    out = str(tmp_path / "a.pdf")
    win._save_dialog = lambda *a: out
    win.export_annotated_pdf()                               # ohne Suche: keine Aenderungen, keine Suche
    wait(app, lambda: not win.running)
    assert win.payload["regs_done"] is False
    with pymupdf.open(out) as d:
        assert len(list(d[0].annots())) == 0
    win.find_regs()
    wait(app, lambda: not win.running)
    n_all = len(win._shown_regs())
    win.cb_filter.setCurrentIndex(win.cb_filter.findData("neu"))
    shown = len(win._shown_regs())
    assert 0 < shown < n_all
    win.export_annotated_pdf()
    wait(app, lambda: not win.running)
    with pymupdf.open(out) as d:
        assert len(list(d[0].annots())) == shown


def test_left_panel_never_clips(app, win):
    win.act_left.setChecked(True)
    win.act_expert.setChecked(True)
    for _ in range(5):
        app.processEvents()
    from ui_widgets import PanelScroll
    sc = win.left.findChild(PanelScroll)
    assert win.left.minimumSizeHint().width() >= sc.widget().minimumSizeHint().width()
    assert win.chk_expert.isChecked()
    win.chk_expert.setChecked(False)
    assert not win.act_expert.isChecked()


def test_drawing_tools_vector(app, win, pair, tmp_path):
    import pymupdf
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    compare(app, win, *pair)
    c = win.canvas
    win._set_tool("pen")                                     # Freihand mit der Maus
    QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(200, 200))
    for x in range(205, 400, 5):
        QTest.mouseMove(c, QPoint(x, 200 + (x % 40)))
    QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=QPoint(400, 230))
    assert win.anns[-1]["type"] == "pen" and len(win.anns[-1]["pts"]) >= 3
    assert c.tool == "pen"                                   # Stift bleibt aktiv
    win._set_tool("polygon")
    for pt in ((500, 300), (600, 300), (560, 380)):
        QTest.mouseClick(c, Qt.MouseButton.LeftButton, pos=QPoint(*pt))
    QTest.keyClick(c, Qt.Key.Key_Return)
    assert win.anns[-1]["type"] == "polygon" and len(win.anns[-1]["pts"]) == 3
    win._ann_created(dict(type="ellipse", x=100, y=500, x2=300, y2=600, text="", nr=0, color="#2563eb", size=2.0))
    a = win.anns[-1]
    ix, iy = 300, 550                                        # rechter Rand der Ellipse
    assert c.hit_ann(ix, iy) == len(win.anns) - 1
    pen = win.anns[0]
    x0 = pen["x"]
    win.canvas.ann_selected = 0                              # Freihand an der Ecke skalieren
    from ui_canvas import apply_handle
    apply_handle(c.shape, pen, "br", pen["x2"] + 100, pen["y2"] + 50)
    assert abs(pen["x"] - x0) < 1e-6 and pen["x2"] > x0 + 100
    win.grab()
    out = str(tmp_path / "a.pdf")
    win._save_dialog = lambda *a: out
    win.export_annotated_pdf()
    wait(app, lambda: not win.running)
    with pymupdf.open(out) as d:
        kinds = {an.type[1] for an in d[0].annots()}
    assert {"Ink", "Polygon", "Circle"} <= kinds
    img = win.export_render("D", True)
    assert img.shape[0] > 100


def test_paste_image_text_and_markups(app, win, pair, tmp_path):
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtCore import QMimeData
    cb = QApplication.clipboard()
    img = QImage(120, 80, QImage.Format.Format_ARGB32)
    img.fill(QColor("#3366cc"))
    cb.setImage(img)
    win.paste()                                              # nichts offen: Bild wird als Zeichnung geoeffnet
    wait(app, lambda: win.payload is not None and not win.running)
    assert win.view_only and win.payload["res"].a.shape == (80, 120)
    win.close_document()
    compare(app, win, *pair)
    cb.setImage(img)
    win.paste()
    a = win.anns[-1]
    assert a["type"] == "image" and a["x2"] > a["x"] and win.canvas.selected_anns() == {len(win.anns) - 1}
    md = QMimeData()
    md.setText("Bitte prüfen")
    cb.setMimeData(md)
    win.paste()
    assert win.anns[-1]["type"] == "text" and win.anns[-1]["text"] == "Bitte prüfen"
    win.canvas._set_multi({0, 1})                            # Markierungen kopieren und einfuegen
    win.copy_result()
    win.paste()
    assert len(win.anns) == 4 and win.anns[2]["type"] == "image"
    img_out = win.export_render("D", True)
    assert img_out.shape[0] > 100
    cb.clear()


def test_inline_text_box_and_keep_tool(app, win, pair):
    import diffreport as rep
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    compare(app, win, *pair)
    c = win.canvas
    win.chk_keep_tool.setChecked(False)
    win._set_tool("text")
    QTest.mouseClick(c, Qt.MouseButton.LeftButton, pos=QPoint(300, 300))   # Klick: Text direkt im Bild
    ed = c.inline_editor
    assert ed is not None and ed.isVisible()
    QTest.keyClicks(ed, "Hallo Welt")
    QTest.keyClick(ed, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    assert c.inline_editor is None and win.anns[-1]["text"] == "Hallo Welt" and "w" not in win.anns[-1]
    assert c.tool == "hand"
    win._set_tool("text")                                    # Ziehen: Textfeld mit Umbruch
    QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(200, 400))
    QTest.mouseMove(c, QPoint(330, 430))
    QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=QPoint(330, 430))
    ed = c.inline_editor
    assert ed is not None and ed.a.get("w")
    QTest.keyClicks(ed, "ein ziemlich langer Hinweistext, der umbrochen werden muss")
    QTest.keyClick(ed, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    box = win.anns[-1]
    th = rep.ann_text_h(c.shape, box["size"])
    assert len(rep.ann_lines(box, th)) > 1
    i = len(win.anns) - 1
    win._ann_edit(i)                                         # bestehenden Text im Bild aendern, Esc = verwerfen
    QTest.keyClicks(c.inline_editor, "XYZ")
    QTest.keyClick(c.inline_editor, Qt.Key.Key_Escape)
    assert "XYZ" not in win.anns[i]["text"]
    win.chk_keep_tool.setChecked(True)                       # Werkzeug behalten: mehrere Pfeile nacheinander
    win._set_tool("arrow")
    for y in (500, 560):
        QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(100, y))
        QTest.mouseMove(c, QPoint(200, y + 20))
        QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=QPoint(200, y + 20))
    assert [a["type"] for a in win.anns[-2:]] == ["arrow", "arrow"] and c.tool == "arrow"
    win.chk_keep_tool.setChecked(False)


def test_area_selection(app, win, tmp_path):
    import cv2
    import numpy as np
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    img = np.full((600, 800), 255, np.uint8)
    cv2.rectangle(img, (100, 100), (200, 180), 0, 4)
    cv2.rectangle(img, (500, 100), (600, 180), 0, 4)
    p = tmp_path / "blatt.png"
    cv2.imwrite(str(p), img)
    win._set_file("A", str(p))
    wait(app, lambda: win.payload is not None and not win.running)
    win._ann_created(dict(type="rect", x=120, y=120, x2=180, y2=160, text="", nr=0, color="#e11d48", size=2.0))
    win._ann_created(dict(type="text", x=700, y=500, x2=700, y2=500, text="weit weg", nr=0, color="#e11d48", size=2.0))
    c = win.canvas
    win.start_area()
    assert c.tool == "area"
    c.sel_rects = [(90, 90, 210, 190)]
    win._area_changed()
    c.sel_rects.append((490, 90, 610, 190))                  # zweiter Rahmen (Umschalt)
    win._area_changed()
    assert c.selected_anns() == {0} and win.area_buttons["copy"].isVisible()
    win.chk_float_lines.setChecked(False)
    win._area_move_started()                                 # beide Rahmen samt Markierung 50 px nach unten
    c.anns[0]["y"] += 50
    c.anns[0]["y2"] += 50
    c.sel_rects = [(r[0], r[1] + 50, r[2], r[3] + 50) for r in c.sel_rects]
    win._area_moved(0, 50)
    g = win.cache["g_" + str(p)]
    assert g[150:231, 100:201].min() < 50 and g[150:231, 500:601].min() < 50
    assert g[100:140, 100:201].min() > 200                   # alte Stelle leer
    assert win.anns[0]["y"] == 170
    win.area_copy()
    md = QApplication.clipboard().mimeData()
    assert md.hasImage() and md.hasFormat("application/x-zgmax-region")
    win.area_delete()                                        # Entf: Markierung in der Auswahl weg, Zeichnung bleibt
    assert [a["text"] for a in win.anns] == ["weit weg"]
    win.paste()                                              # Bild + Markierung wieder eingefuegt
    assert [a["type"] for a in win.anns][-2:] == ["image", "rect"]
    win.undo()
    win.undo()
    assert len(win.anns) == 2
    QApplication.clipboard().clear()


def test_layers_and_svg_pdf_export(app, win, pair, tmp_path):
    import pymupdf
    compare(app, win, *pair)
    win._ann_created(dict(type="rect", x=100, y=100, x2=300, y2=200, text="", nr=0, color="#e11d48", size=2.0))
    win._ann_created(dict(type="measure", kind="dist", pts=[[100, 400], [500, 400]], x=100, y=400, x2=500, y2=400,
                          text="", nr=0, color="#2563eb", size=2.0))
    win.find_regs()
    wait(app, lambda: not win.running)
    win.act_layers.setChecked(True)
    assert win.tabs.isTabVisible(2)
    out = str(tmp_path / "a.pdf")
    win._save_dialog = lambda *a: out
    win.export_annotated_pdf()
    wait(app, lambda: not win.running)
    with pymupdf.open(out) as d:
        names = {v["name"] for v in d.get_ocgs().values()}
    assert {"Zeichnung", "Änderungen", "Markierungen", "Maße"} <= names
    win.layer_checks["masse"].setChecked(False)              # Masse ausblenden: nicht mehr im Bild/Export
    assert not win.canvas.layer_on["masse"]
    assert [a["type"] for a in win._export_anns()] == ["rect"]
    assert win.canvas.hit_ann(300, 400) is None              # ausgeblendet: nicht anklickbar
    win.layer_locks["markierungen"].setChecked(True)
    assert win.canvas.hit_ann(100, 150) is None              # gesperrt: nicht anklickbar
    svg = str(tmp_path / "a.svg")
    win.export_svg(path=svg)
    txt = open(svg, encoding="utf-8").read()
    assert 'inkscape:label="Zeichnung"' in txt and 'inkscape:label="Markierungen"' in txt and "Maße" not in txt
    import xml.dom.minidom
    xml.dom.minidom.parse(svg)                               # gueltiges XML
    win.act_layers.setChecked(False)


def test_sheet_crop_rotate_adjust_size(app, win, tmp_path, monkeypatch):
    import cv2
    import numpy as np
    import ui_edit
    img = np.full((400, 600), 230, np.uint8)
    cv2.rectangle(img, (100, 100), (200, 180), 40, 4)
    p = tmp_path / "blatt.png"
    cv2.imwrite(str(p), img)
    win._set_file("A", str(p))
    wait(app, lambda: win.payload is not None and not win.running)
    win._ann_created(dict(type="rect", x=110, y=110, x2=190, y2=170, text="", nr=0, color="#e11d48", size=2.0))
    win.start_area()
    win.canvas.sel_rects = [(50, 50, 350, 250)]
    win._area_changed()
    win.sheet_crop()
    wait(app, lambda: not win.running)
    assert win.payload["res"].a.shape == (200, 300) and win.anns[0]["x"] == 60
    win.sheet_rotate(1)                                      # 90 Grad im Uhrzeigersinn
    wait(app, lambda: not win.running)
    assert win.payload["res"].a.shape == (300, 200)
    a = win.anns[0]
    assert (a["x"], a["y"]) == (200 - 120, 60)               # (x, y) -> (h - y, x)
    monkeypatch.setattr(ui_edit.AdjustDialog, "exec", lambda d: (d.s_b.setValue(20), d.s_c.setValue(150), 1)[-1])
    win.sheet_adjust()
    wait(app, lambda: not win.running)
    assert win.cache["g_" + str(p)].max() == 255            # Papier heller
    monkeypatch.setattr(ui_edit.ImageSizeDialog, "exec", lambda d: (d.sp_dpi.setValue(d.dpi0 * 2), 1)[-1])
    dpi0 = win.dpi_value()
    win.sheet_size()
    wait(app, lambda: not win.running)
    assert win.payload["res"].a.shape == (600, 400) and win.dpi_value() == dpi0 * 2
    for _ in range(4):
        win.undo()
        wait(app, lambda: not win.running)
    assert win.payload["res"].a.shape == (400, 600) and win.anns[0]["x"] == 110 and win.dpi_value() == dpi0


def test_searchable_pdf_and_vectorize(app, win, tmp_path, monkeypatch):
    import cv2
    import numpy as np
    import pymupdf
    import ezdxf
    import ui_edit
    img = np.full((600, 900), 255, np.uint8)
    cv2.putText(img, "BOHRUNG 25", (80, 200), cv2.FONT_HERSHEY_SIMPLEX, 2.2, 0, 5)
    cv2.rectangle(img, (60, 300), (600, 500), 0, 4)
    p = tmp_path / "scan.png"
    cv2.imwrite(str(p), img)
    win._set_file("A", str(p))
    wait(app, lambda: win.payload is not None and not win.running)
    out = str(tmp_path / "s.pdf")
    win._save_dialog = lambda *a: out
    win.export_searchable_pdf()
    wait(app, lambda: not win.running, timeout=120)
    with pymupdf.open(out) as d:
        assert d[0].search_for("BOHRUNG")                    # unsichtbarer Text ist durchsuchbar
    for ext in (".svg", ".pdf", ".dxf"):
        monkeypatch.setattr(ui_edit.VectorizeDialog, "exec",
                            lambda d, e=ext: (d.cb_fmt.setCurrentIndex(d.cb_fmt.findData(e)), 1)[-1])
        vo = str(tmp_path / ("v" + ext))
        win._save_dialog = lambda *a, v=vo: v
        win.vectorize_drawing()
        wait(app, lambda: not win.running)
    assert ezdxf.readfile(str(tmp_path / "v.dxf")).modelspace().query("LWPOLYLINE")
    with pymupdf.open(str(tmp_path / "v.pdf")) as d:
        assert len(d[0].get_drawings()) > 0


def test_zones_select_move_delete_and_align_off(app, win, pair):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    compare(app, win, *pair)
    win._add_zone(100, 100, 200, 150)
    c = win.canvas
    assert c.zones and c.hit_zone(150, 150) == 0
    c.zone_sel = None
    c._drag = None
    c.zone_sel = 0                                           # ziehen wie mit der Maus
    c._drag = ("zmove", (150, 150), tuple(c.zones[0]))
    c.zones[0] = (150, 120, 200, 150)
    c._moved = 3
    c.zoneSelected.emit(0)
    c.zoneEdited.emit(0, *c.zones[0])
    assert win.zones[0][:2] == (150 + win.origin[0], 120 + win.origin[1])
    win._ann_delete()                                        # Entf loescht die gewaehlte Zone
    assert win.zones == []
    win.undo()
    assert len(win.zones) == 1
    win.chk_align.setChecked(False)                          # ohne Ausrichtung vergleichen
    assert win.params().align == "off" and win.params().max_shift == 0
    win.start_compute()
    wait(app, lambda: not win.running)
    assert win.payload is not None
    win.chk_align.setChecked(True)


def test_redact_and_pixelate_burned_everywhere(app, win, tmp_path):
    import cv2
    import numpy as np
    import pymupdf
    img = np.full((600, 900), 255, np.uint8)
    cv2.putText(img, "GEHEIM 4711", (80, 200), cv2.FONT_HERSHEY_SIMPLEX, 2.2, 0, 5)
    cv2.rectangle(img, (500, 350), (800, 550), 0, 6)
    p = tmp_path / "scan.png"
    cv2.imwrite(str(p), img)
    win._set_file("A", str(p))
    wait(app, lambda: win.payload is not None and not win.running)
    win._ann_created(dict(type="redact", x=60, y=120, x2=560, y2=230, text="", nr=0, color="#000000", size=2.0))
    win._ann_created(dict(type="pixelate", x=480, y=330, x2=820, y2=570, text="", nr=0, color="#000000", size=4.0))
    win.grab()                                               # Anzeige (Mosaik) laeuft
    win.act_overlays.setChecked(False)                       # auch mit ausgeblendeten Markierungen eingebrannt
    out = win.export_render("A", False, legend=False)
    assert out[150:200, 100:500].max() < 10                  # schwarz
    win.anns[0]["fill"] = "paper"                             # mit Papierfarbe: weiss ausgemalt, Schrift weg
    out2 = win.export_render("A", False, legend=False)
    assert out2[150:200, 100:500].min() > 230
    win.anns[0]["fill"] = "black"
    gray = out[350:550, 500:800].min(axis=2)
    assert gray.min() > 100                                  # Mosaik: keine schwarzen Linien mehr
    win.act_overlays.setChecked(True)
    pdf = str(tmp_path / "s.pdf")
    win._save_dialog = lambda *a: pdf
    win.export_searchable_pdf()
    wait(app, lambda: not win.running, timeout=120)
    with pymupdf.open(pdf) as d:
        assert not d[0].search_for("GEHEIM")                 # kein Text unter der Schwaerzung
    ann_pdf = str(tmp_path / "a.pdf")
    win._save_dialog = lambda *a: ann_pdf
    win.export_annotated_pdf()
    wait(app, lambda: not win.running)
    with pymupdf.open(ann_pdf) as d:
        pix = d[0].get_pixmap(dpi=72)
    win.start_area()                                         # Kopieren ohne Papier
    win.canvas.sel_rects = [(450, 300, 850, 600)]
    win._area_changed()
    win.chk_float_lines.setChecked(True)
    bgra, _ = win._area_bgra(True)
    assert bgra[..., 3].min() == 0 and bgra[..., 3].max() == 255
    QApplication.clipboard().clear()


def test_documents_windows_settings_legend_measure(app, win, pair, tmp_path):
    import diffreport as rep
    import drawing_viewer as vw
    compare(app, win, *pair)
    n = len(vw.WINDOWS)
    win.open_recent({"a": pair[0], "b": None, "project": None})     # anderes Dokument: eigenes Fenster
    assert len(vw.WINDOWS) == n + 1 and win.path_b == pair[1]
    other = vw.WINDOWS[-1]
    wait(app, lambda: other.payload is not None and not other.running)
    assert other.view_only and other.anns == []
    other.close()
    win.act_legend.setChecked(False)                                  # Legende: Ansicht und Bild
    assert win.settings.value("legend") == "false"
    w0 = win.export_render("D", False).shape[1]
    win.act_legend.setChecked(True)
    assert win.export_render("D", False).shape[1] > w0
    win._ann_created(dict(type="measure", kind="dist", pts=[[100, 300], [700, 300]], x=100, y=300, x2=700, y2=300,
                          text="", nr=0, color="#2563eb", size=2.0))
    a = win.anns[-1]
    cx, cy, ang, ax, ay = rep.measure_label(a, win.canvas.shape)
    assert abs(ang) < 1e-6 and cy < 300 and abs(cx - 400) < 1        # mittig ueber der Masslinie
    from ui_canvas import apply_handle
    apply_handle(win.canvas.shape, a, "lbl", 450, 200)                # Wert verschieben
    assert rep.measure_label(a, win.canvas.shape)[:2] == (450, 200)
    win.cb_unit.setCurrentIndex(win.cb_unit.findData("cm"))
    win.sp_dec.setValue(1)
    assert rep.measure_text(a, win.canvas.mm_px).endswith(" cm") and "." in rep.measure_text(a, win.canvas.mm_px)
    win.cb_unit.setCurrentIndex(win.cb_unit.findData("mm"))
    win.sp_dec.setValue(2)
    regs = win.payload["regs"] or []
    win.find_regs()
    wait(app, lambda: not win.running)
    for r in win.payload["regs"]:                                     # geaenderter Text: Filter in Liste und Bild
        r["text_a"], r["text_b"] = ("25,4", "25,8") if r["nr"] == 1 else ("A", "A")
    win.cb_filter.setCurrentIndex(win.cb_filter.findData("text"))
    assert [r["nr"] for r in win._shown_regs()] == [1] and win.canvas.visible_nrs == {1}
    win.cb_filter.setCurrentIndex(win.cb_filter.findData("changes"))
    win.settings.setValue("keep_tool", "true")                       # alle Einstellungen zuruecksetzen
    win.settings.setValue("recent", "[]")
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.exec = lambda self: QMessageBox.StandardButton.Reset
    try:
        win.reset_all_settings()
    finally:
        del QMessageBox.exec
    assert win.settings.value("keep_tool") is None and win.settings.value("recent") == "[]"


def test_enabled_states_by_mode(app, win, pair):
    assert not win.act_ann_save.isEnabled() and not win.act_delete.isEnabled()      # nichts offen
    win._set_file("A", pair[0])
    wait(app, lambda: win.payload is not None and not win.running)
    assert win.view_only and not win.act_export_pdf.isEnabled() and not win.act_crop.isEnabled()
    assert win.act_adjust.isEnabled() and win.act_export_ocrpdf.isEnabled()
    win.close_document()
    compare(app, win, *pair)
    assert win.act_export_pdf.isEnabled() and not win.act_adjust.isEnabled() and win.act_export_ocrpdf.isEnabled()
    assert not win.act_align_reset.isEnabled()
    win.resize(1100, 800)                                            # schmal: Leiste oben nur Symbole
    for _ in range(10):
        app.processEvents()
    win._fit_toolbar()
    assert win._tb_text[0].toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly


def test_pdf_comments_imported_and_pdf_layers(app, win, tmp_path):
    import pymupdf
    p = str(tmp_path / "kommentiert.pdf")
    d = pymupdf.open()
    pg = d.new_page(width=595, height=420)
    oc_mass = d.add_ocg("Bemaßung", on=True)
    pg.draw_rect(pymupdf.Rect(50, 50, 300, 200), width=2)
    pg.insert_text((60, 300), "100", fontsize=20, oc=oc_mass)
    an = pg.add_rect_annot(pymupdf.Rect(320, 60, 500, 180))
    an.set_colors(stroke=(1, 0, 0))
    an.set_info(title="Prüfer", content="bitte ändern")
    an.update()
    d.save(p)
    win._set_file("A", p)
    wait(app, lambda: win.payload is not None and not win.running)
    for _ in range(5):
        app.processEvents()
    assert [a["type"] for a in win.anns] == ["rect"] and win.anns[0]["author"] == "Prüfer"   # bearbeitbar
    k = win.dpi_value() / 72
    g = win.cache["g_" + p]
    assert g[int(120 * k), int(320 * k) + 2] > 200            # Kommentar nicht ins Bild gezeichnet
    assert win.pdf_layer_box.isVisibleTo(win) or not win.pdf_layer_box.isHidden()
    ink_before = int((win.payload["res"].a[int(280 * k):int(305 * k), int(55 * k):int(110 * k)] > 0).sum())
    assert ink_before > 0
    win._pdf_layer_toggled("Bemaßung", False)                  # PDF-Ebene ausblenden
    wait(app, lambda: not win.running)
    assert int((win.payload["res"].a[int(280 * k):int(305 * k), int(55 * k):int(110 * k)] > 0).sum()) == 0
    n = len(win.anns)
    win._auto_import_pdf_comments()                           # nicht doppelt
    assert len(win.anns) == n


def test_crop_frame_only_on_output(app, win, pair, tmp_path):
    import pymupdf
    compare(app, win, *pair)
    win._ann_created(dict(type="rect", x=300, y=300, x2=400, y2=380, text="", nr=0, color="#e11d48", size=2.0))
    h, w = win.canvas.shape
    full = win.export_render("D", True, legend=False)
    win.start_area()
    win.canvas.sel_rects = [(200, 200, 700, 600)]
    win._area_changed()
    assert win.area_buttons["crop"].isVisible()              # im Vergleich verfuegbar
    win.set_crop_frame()
    assert win.canvas.crop_frame == (200, 200, 700, 600) and win.payload["res"].a.shape == (h, w)   # nichts geloescht
    out = win.export_render("D", True, legend=False)
    assert out.shape[:2] == (400, 500)
    assert (out == full[200:600, 200:700]).all()
    win.canvas.frameEdited.emit(150, 200, 700, 650)          # Rahmen angepasst (wie mit der Maus)
    assert win.export_render("D", False, legend=False).shape[:2] == (450, 550)
    pdf = str(tmp_path / "z.pdf")
    win._save_dialog = lambda *a: pdf
    win.export_annotated_pdf()
    wait(app, lambda: not win.running)
    with pymupdf.open(pdf) as d:
        pg = d[0]                                           # Seite festhalten (sonst ungueltige Anmerkung)
        r = next(a for a in pg.annots() if a.type[1] == "Square").rect
        k = 72 / win.dpi_value()
        assert abs(r.x0 - 150 * k) < 3                          # Kommentar mit dem Zuschnitt verschoben
    win.undo()
    assert win.canvas.crop_frame == (200, 200, 700, 600)
    win.clear_crop_frame()
    assert win.export_render("D", False, legend=False).shape[:2] == (h, w)


def test_comment_replies_and_status_roundtrip(app, win, pair, tmp_path, monkeypatch):
    import pymupdf
    import diffxfdf as dx
    import diffreport as rep
    compare(app, win, *pair)
    win.settings.setValue("user_name", "Max")
    win._ann_created(dict(type="cloud", x=100, y=100, x2=400, y2=300, text="", nr=0, color="#e11d48", size=2.0))
    win.canvas._set_multi({0})
    assert not win.thread_box.isHidden()
    win.ed_comment.setPlainText("Maß prüfen")
    win.ed_reply.setText("Ist geprüft, passt.")
    win._add_reply()
    win.cb_state.setCurrentIndex(win.cb_state.findData("accepted"))
    a = win.anns[0]
    assert a["comment"] == "Maß prüfen" and a["replies"][0]["author"] == "Max" and a["states"] == {"Max": "accepted"}
    assert "💬1" in win.list_anns.item(0).text() and "Akzeptiert" in win.list_anns.item(0).text()
    pdf = str(tmp_path / "t.pdf")                              # PDF: Antworten als echte Unterhaltung (/IRT)
    win._save_dialog = lambda *a: pdf
    win.export_annotated_pdf()
    wait(app, lambda: not win.running)
    items, _ = dx.pdf_comments(pdf, 1)
    k = win.dpi_value() / 72
    back = dx.to_annotations(items, k)
    cloud = next(b for b in back if b["type"] in ("cloud", "rect"))
    assert cloud["replies"][0]["text"] == "Ist geprüft, passt." and cloud["states"] == {"Max": "accepted"}
    xf = str(tmp_path / "t.xfdf")                              # XFDF hin und zurueck
    dx.write_xfdf(xf, [a], k, 842)
    items, _ = dx.parse_xfdf(xf, 842)
    back = dx.to_annotations(items, k)
    assert len(back) == 1 and back[0]["replies"][0]["author"] == "Max" and back[0]["states"] == {"Max": "accepted"}


def test_measure_chain_sums_export_and_page_scale(app, win, pair, tmp_path):
    import csv
    compare(app, win, *pair)
    c = win.canvas
    c.measure_kind = "chain"
    c.measure = [(100, 100, None), (300, 100, None), (300, 250, None)]
    c.finish_measure()
    ms = [a for a in win.anns if a["type"] == "measure"]
    assert len(ms) == 2 and ms[0]["group"] == ms[1]["group"]          # Masskette: zwei verbundene Masse
    mm = c.mm_px
    assert "2 Längen" in win.lbl_sums.text() and f"{350 * mm:.2f}" in win.lbl_sums.text()
    out = str(tmp_path / "m.csv")
    win._save_dialog = lambda *a: out
    win.export_measures()
    rows = list(csv.reader(open(out, encoding="utf-8-sig"), delimiter=";"))
    assert rows[1][1] == "Länge" and float(rows[1][2].replace(",", ".")) == pytest.approx(200 * mm, rel=1e-3)
    win.sp_scale.setValue(5.0)                                          # Massstab je Seite
    key = f"{win.path_a}#1"
    assert win.page_scales[key] == 5.0
    win.page_scales[f"{win.path_a}#2"] = 2.0
    win._page_scale_loading = False
    win.sp_pa.setMaximum(2)
    win.sp_pa.setValue(2)
    assert win.scale_n() == 2.0
    win.sp_pa.setValue(1)
    assert win.scale_n() == 5.0


def test_markups_per_page_and_all_pages_pdf(app, win, tmp_path):
    import pymupdf
    p = str(tmp_path / "zwei.pdf")
    d = pymupdf.open()
    for i in range(2):
        pg = d.new_page(width=595, height=420)
        pg.draw_rect(pymupdf.Rect(50 + 40 * i, 50, 300, 200), width=2)
    d.save(p)
    win._set_file("A", p)
    wait(app, lambda: win.payload is not None and not win.running)
    win._ann_created(dict(type="rect", x=100, y=100, x2=300, y2=200, text="", nr=0, color="#e11d48", size=2.0))
    win.sp_pa.setValue(2)                                     # Seite 2: eigene (noch leere) Markierungen
    win.page_timer.stop()
    win.start_compute()
    wait(app, lambda: not win.running)
    assert win.anns == [] and "1 Markierungen" in win.list_pages.item(0).text()
    win._ann_created(dict(type="ellipse", x=50, y=50, x2=150, y2=120, text="", nr=0, color="#2563eb", size=2.0))
    win._ann_created(dict(type="ellipse", x=250, y=50, x2=350, y2=120, text="", nr=0, color="#2563eb", size=2.0))
    win.sp_pa.setValue(1)
    win.page_timer.stop()
    win.start_compute()
    wait(app, lambda: not win.running)
    assert [a["type"] for a in win.anns] == ["rect"]
    out = str(tmp_path / "alle.pdf")
    win._save_dialog = lambda *a: out
    assert win.act_export_all_ann.isVisible()
    win.export_all_pages("annpdf")
    wait(app, lambda: not win.running)
    with pymupdf.open(out) as r:
        assert r.page_count == 2
        p0, p1 = r[0], r[1]
        assert [a.type[1] for a in p0.annots()] == ["Square"] and len(list(p1.annots())) == 2
    proj = str(tmp_path / "s.zgmax")                          # Projekt: Markierungen aller Seiten
    win._save_dialog = lambda *a: proj
    assert win.project_save(True)
    data = json.load(open(proj))
    assert len(data["page_annotations"]["2"]) == 2 and len(data["annotations"]) == 1


def test_report_all_pages(app, win, tmp_path):
    import pymupdf
    paths = []
    for name, dx in (("a.pdf", 0), ("b.pdf", 30)):
        d = pymupdf.open()
        for i in range(2):
            pg = d.new_page(width=595, height=420)
            pg.draw_rect(pymupdf.Rect(50, 50, 300, 200), width=2)
            pg.draw_line((350 + dx * i, 100), (500, 300), width=2)
        p = str(tmp_path / name)
        d.save(p)
        paths.append(p)
    compare(app, win, *paths)
    out = str(tmp_path / "bericht.pdf")
    win._save_dialog = lambda *a: out
    assert win.act_export_all_report.isVisible()
    win.export_all_pages("report")
    wait(app, lambda: not win.running, timeout=120)
    with pymupdf.open(out) as r:
        assert r.page_count >= 2


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


def test_selection_does_not_change_defaults(app, win, pair):
    compare(app, win, *pair)
    win._set_color_btn("#00aa00")                          # Vorgabe gruen
    win.s_asize.setValue(3.0)
    win._ann_created(dict(type="rect", x=10, y=10, x2=200, y2=200, text="", nr=0, color="#ff0000", size=6.0))
    win._ann_selected(0)
    assert win.btn_color.property("shown_color") == "#ff0000" and win.s_asize.value() == 6.0
    assert win.canvas.ann_color == "#00aa00" and win.canvas.ann_size == 3.0       # Vorgabe unveraendert
    win._set_tool("zoom")
    win._set_tool("hand")
    assert win.canvas.ann_selected is None
    assert win.btn_color.property("shown_color") == "#00aa00" and win.s_asize.value() == 3.0


def test_side_by_side_drag_across_middle(app, win, pair):
    from PySide6.QtCore import QPointF
    compare(app, win, *pair)
    win._set_mode("Y")
    c = win.canvas
    half = c.rect().width() // 2
    c._drag = None
    start = c._vp(QPointF(half - 40, 100))                # Ziehen beginnt links ...
    c._drag = ("pan", start, c.ox, c.oy)
    p_left = c._vp(QPointF(half - 10, 100))
    p_right = c._vp(QPointF(half + 10, 100))              # ... und geht ueber die Mitte nach rechts
    assert p_right.x() - p_left.x() == pytest.approx(20)  # kein Sprung um eine halbe Breite
    c._drag = None


def test_vector_offer_and_rejected_zones(app, win, tmp_path):
    import pymupdf
    import diffreport as rep
    paths = []
    for name, extra in (("a.pdf", False), ("b.pdf", True)):
        d = pymupdf.open()
        pg = d.new_page(width=600, height=400)
        for i in range(30):
            pg.draw_line((20 + i * 15, 30), (20 + i * 15, 350))
        if extra:
            pg.draw_circle((300, 200), 40)
        p = str(tmp_path / name)
        d.save(p)
        paths.append(p)
    compare(app, win, *paths)
    wait(app, lambda: win.banner.btn_action.isVisible())
    assert "Vektor" in win.banner.btn_action.text()
    win.banner.btn_action.click()
    wait(app, lambda: not win.running)
    assert win.chk_vec.isChecked()
    win.find_regs()
    wait(app, lambda: not win.running)
    rep.set_status(win.payload["regs"][0], "abgelehnt")
    n = len(win.zones)
    win.zones_from_rejected()
    assert len(win.zones) == n + 1


def test_view_switch_and_highlight(app, win, pair):
    compare(app, win, *pair)
    win.seg_buttons["B"].click()
    assert win.canvas.mode == "B" and win.chk_highlight.isVisible()
    win.chk_highlight.setChecked(True)
    assert win.canvas.mode == "N" and win.seg_buttons["B"].isChecked()
    win.seg_buttons["A"].click()
    assert win.canvas.mode == "R"                                  # Hervorheben bleibt beim Wechsel
    win.seg_buttons["K"].click()
    assert win.cb_blink.isVisible() and not win.chk_highlight.isVisible()


def test_bars_overlay_canvas(app, win, pair):
    """Options-, Such- und Hinweisleiste liegen ueber dem Bild: die Zeichnung bleibt stehen."""
    compare(app, win, *pair)
    app.processEvents()
    c = win.canvas
    size, view = c.size(), (c.scale, c.ox, c.oy)
    win._set_tool("measure")
    win.open_search()
    win.banner.show_msg("Test", "info")
    for _ in range(5):
        app.processEvents()
    assert win.options_bar.isVisible() and win.search_bar.isVisible() and win.banner.isVisible()
    assert win.canvas_host.bar_height() > 60
    assert c.size() == size and (c.scale, c.ox, c.oy) == view
    win._set_tool("hand")
    win.close_search()
    win.banner.hide()
    for _ in range(5):
        app.processEvents()
    assert win.canvas_host.bar_height() == 0 and c.size() == size
    win.close_document()
    app.processEvents()
    assert win.banner.parent() is not win.canvas_host.column    # Startseite: Leiste wieder im Layout


def test_manual_three_point_alignment(app, win, tmp_path):
    import cv2
    import numpy as np
    from PIL import Image
    from conftest import draw_sheet
    a = draw_sheet(False)
    M = np.float32([[1, 0, 9], [0, 1, -6]])                     # B um (9, -6) verschoben
    b = cv2.warpAffine(draw_sheet(False), M, (a.shape[1], a.shape[0]), borderValue=255)
    pa, pb = tmp_path / "a.png", tmp_path / "b.png"
    Image.fromarray(a).save(pa)
    Image.fromarray(b).save(pb)
    win.cb_align.setCurrentText("none")                         # Automatik aus: Versatz bleibt sichtbar
    for w in (win.s_maxs, win.s_move, win.s_obj):              # auch keine Feinausrichtung/Objektsuche
        w.set_silent(0)
    compare(app, win, str(pa), str(pb))
    before = int(win.payload["res"].oa.sum())
    assert before > 1000
    win.start_manual_align()
    assert win.canvas.mode == "Y" and win.canvas.tool == "align"
    win.canvas.snap = False
    for (x, y) in ((40, 40), (1560, 40), (40, 1060)):          # Rahmenecken in A und (verschoben) in B
        win.canvas.alignPoint.emit("A", x, y)
        win.canvas.alignPoint.emit("B", x + 9, y - 6)
    wait(app, lambda: not win.running and win.manual_tf is not None)
    wait(app, lambda: not win.running)
    assert int(win.payload["res"].oa.sum()) < before * 0.2
    assert win.canvas.tool == "hand"


def test_text_search_pdf(app, win, tmp_path):
    import pymupdf
    paths = []
    for name, txt in (("a.pdf", "Bohrung 25 H7"), ("b.pdf", "Bohrung 30 H7")):
        d = pymupdf.open()
        pg = d.new_page(width=600, height=400)
        for i in range(25):
            pg.draw_line((20 + i * 20, 30), (20 + i * 20, 350))
        pg.insert_text((300, 200), txt, fontsize=14)
        pg.insert_text((60, 380), "Bohrung entgratet", fontsize=10)
        p = str(tmp_path / name)
        d.save(p)
        paths.append(p)
    compare(app, win, *paths)
    win.open_search()
    win.ed_search.setText("bohrung")
    win.run_search()
    wait(app, lambda: not win.running and win.canvas.search_hits)
    assert len(win.canvas.search_hits) == 2
    xs = sorted(h[0] for h in win.canvas.search_hits)
    assert abs(xs[1] - 300 * 200 / 72) < 15                # Treffer liegt am Text (pt -> px bei 200 dpi)
    win.ed_search.setText("30 h7")                        # Begriff mit Leerzeichen, nur in Neu
    win.run_search()
    assert len(win.canvas.search_hits) == 1
    win.cb_search_in.setCurrentIndex(1)                   # in Alt: dort steht 25 H7
    wait(app, lambda: not win.running and win.lbl_search.text() == "Nicht gefunden")
    assert len(win.canvas.search_hits) == 0
    win.search_step(1)
    win.close_search()
    assert not win.canvas.search_hits


def test_text_search_ocr(app, win, tmp_path):
    import diffreport as rep
    import numpy as np
    from PIL import Image, ImageDraw
    if not rep.ocr_available():
        pytest.skip("Texterkennung nicht installiert")
    import diffcore as dc
    img = Image.new("L", (1800, 1200), 255)
    d = ImageDraw.Draw(img)
    d.rectangle((40, 40, 1760, 1160), outline=0, width=4)
    d.text((1300, 1050), "Maßstab 1:2  Index C", font=dc._font(30), fill=0)
    d.text((200, 300), "Bohrung Ø12 H7", font=dc._font(30), fill=0)
    p = tmp_path / "scan.png"
    img.save(p)
    win._set_file("A", str(p))
    wait(app, lambda: win.payload is not None and not win.running)
    win.open_search()
    win.ed_search.setText("Bohrung")
    win.run_search()
    wait(app, lambda: not win.running and win.canvas.search_hits)
    x0, y0, x1, y1 = win.canvas.search_hits[0]
    assert 180 < x0 < 260 and 280 < y0 < 340


def test_comments_pdf_and_xfdf_roundtrip(app, win, tmp_path, monkeypatch):
    import pymupdf
    from PySide6.QtWidgets import QFileDialog
    pdf = str(tmp_path / "zeichnung.pdf")
    d = pymupdf.open()
    pg = d.new_page(width=600, height=400)
    pg.draw_rect((50, 50, 550, 350))
    a = pg.add_rect_annot(pymupdf.Rect(100, 100, 200, 160))
    a.set_border(width=1.5, clouds=1)
    a.set_info(title="Prüfer", content="Wolke: Maß prüfen")
    a.update()
    a = pg.add_line_annot((300, 300), (400, 250))
    a.set_line_ends(0, pymupdf.PDF_ANNOT_LE_CLOSED_ARROW)
    a.update()
    a = pg.add_freetext_annot(pymupdf.Rect(350, 80, 520, 110), "Bohrung entgraten", fontsize=10)
    a.update()
    a = pg.add_text_annot((80, 320), "Bitte Toleranz klären")
    a.set_info(title="Max")
    a.update()
    d.save(pdf)
    win._set_file("A", pdf)
    wait(app, lambda: win.payload is not None and not win.running)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (pdf, ""))
    win.import_comments()
    types = sorted(x["type"] for x in win.anns)
    assert types == ["arrow", "cloud", "text", "text"], types
    k = 200 / 72
    cloud = next(x for x in win.anns if x["type"] == "cloud")
    assert abs(cloud["x"] - 100 * k) < 3 and abs(cloud["y"] - 100 * k) < 3 and cloud["author"] == "Prüfer"
    # Rundreise ueber XFDF
    xf = str(tmp_path / "k.xfdf")
    win._save_dialog = lambda *a: xf
    win.export_xfdf()
    before = [(x["type"], round(x["x"]), round(x["y"])) for x in win.anns]
    win.anns.clear()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (xf, ""))
    win.import_comments()
    after = [(x["type"], round(x["x"]), round(x["y"])) for x in win.anns]
    assert sorted(t for t, _, _ in after) == sorted(t for t, _, _ in before)
    for (t, x, y) in before:
        assert any(t2 == t and abs(x2 - x) <= 2 and abs(y2 - y) <= 2 for t2, x2, y2 in after), (t, x, y, after)


def test_ui_scale_setting(app, win):
    from ui_common import ui_scale_setting
    win.set_ui_scale(1.3)
    assert ui_scale_setting(win.settings) == 1.3 and win.banner.btn_action.isVisible()   # auch auf der Startseite
    win.settings.setValue("ui_scale", "kaputt")
    assert ui_scale_setting(win.settings) == 1.0


def test_english_ui():
    """Oberflaeche auf Englisch: alle Bedienelemente uebersetzt, Bericht und Liste englisch."""
    import subprocess
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(here, "english_check.py")], capture_output=True, text=True,
                       timeout=300)
    assert "ENGLISH-OK" in r.stdout, r.stdout[-3000:] + r.stderr[-2000:]
