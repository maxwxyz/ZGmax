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
