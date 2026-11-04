"""Tabelle aus Auswahl: Zellraster aus Linien oder aus der Lage der Woerter, CSV, Dialog im Hauptfenster."""
import csv
import io

import cv2
import numpy as np
import pytest

import tableextract as te
from test_gui import app, wait, win  # noqa: F401 - Fixtures des Fenstertests

DATA = [["Pos", "Benennung", "Menge"], ["1", "Schraube M6", "4"], ["2", "Mutter", "2,5"], ["3", "", "1"]]


def draw_table(lines=True, xs=(20, 200, 400, 580), ys=(20, 80, 140, 200, 260)):
    """Graubild mit Tabelle (Linien wahlweise) und die Woerter dazu (je Wort ein Rechteck)."""
    img = np.full((300, 620), 255, np.uint8)
    if lines:
        for x in xs:
            cv2.line(img, (x, ys[0]), (x, ys[-1]), 0, 2)
        for y in ys:
            cv2.line(img, (xs[0], y), (xs[-1], y), 0, 2)
    words = []
    for r, row in enumerate(DATA):
        for c, t in enumerate(row):
            x = xs[c] + 10
            for part in t.split():
                w = len(part) * 12
                cv2.putText(img, part, (x, ys[r] + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1)
                words.append((x, ys[r] + 25, x + w, ys[r] + 43, part))
                x += w + 8
    return img, words


def test_grid_from_lines():
    img, words = draw_table(True)
    g = te.table_grid(words, img)
    assert g["by_lines"] == (True, True)
    assert len(g["xs"]) == 4 and len(g["ys"]) == 5
    assert g["rows"] == DATA


def test_grid_from_words_without_lines():
    img, words = draw_table(False)
    g = te.table_grid(words, img)
    assert g["by_lines"] == (False, False)
    assert g["rows"] == DATA
    assert te.extract_table(words) == DATA                      # ganz ohne Bild


def test_lines_split_ocr_line_and_merged_cell():
    """Eine Zeile der Texterkennung ueber zwei Spalten wird an der Linie geteilt; eine verbundene Zelle (ohne
    senkrechte Linie in dieser Zeile) steht in der ersten Zelle, die zweite bleibt leer."""
    img = np.full((200, 420), 255, np.uint8)
    for y in (10, 70, 130):
        cv2.line(img, (10, y), (410, y), 0, 2)
    for x in (10, 410):
        cv2.line(img, (x, 10), (x, 130), 0, 2)
    cv2.line(img, (210, 70), (210, 130), 0, 2)                  # Mitte nur in der zweiten Zeile
    words = [(30, 30, 200, 50, "Kopf ueber alles"),
             (30, 90, 300, 110, "links rechts")]               # eine Zeile, reicht ueber die Mitte
    rows = te.extract_table(words, img)
    assert rows == [["Kopf ueber alles", ""], ["links", "rechts"]]


def test_scan_like_table_with_noise():
    """Bitmap wie ein Scan: Linien leicht unterbrochen und verrauscht, Schrift bleibt keine Linie."""
    img, words = draw_table(True)
    rng = np.random.default_rng(1)
    img[rng.random(img.shape) < 0.002] = 0
    img[:, 300:302] = np.where(img[:, 300:302] == 0, 255, img[:, 300:302])   # kleine Luecke in den waagerechten
    g = te.table_grid(words, img)
    assert g["rows"] == DATA


def test_multiline_cell_and_empty_rows():
    img = np.full((260, 420), 255, np.uint8)
    for y in (10, 110, 170, 230):
        cv2.line(img, (10, y), (410, y), 0, 2)
    for x in (10, 150, 410):
        cv2.line(img, (x, 10), (x, 230), 0, 2)
    words = [(20, 30, 60, 48, "A"), (160, 25, 260, 43, "zweite"), (160, 60, 260, 78, "Zeile"),
             (20, 190, 60, 208, "C")]
    assert te.extract_table(words, img) == [["A", "zweite Zeile"], ["", ""], ["C", ""]]


def test_csv_quoting():
    rows = [["a;b", 'sag "hallo"', "2,5"], ["mit\nUmbruch", "", "x"], ["kurz"]]
    s = te.to_csv(rows)
    assert s.splitlines()[0] == '"a;b";"sag ""hallo""";2,5'
    back = list(csv.reader(io.StringIO(s, newline=""), delimiter=";"))
    assert back == [["a;b", 'sag "hallo"', "2,5"], ["mit\nUmbruch", "", "x"], ["kurz", "", ""]]
    assert te.to_csv([["1,5", "x"]], ",") == '"1,5",x\r\n'
    assert te.to_csv([["1,5", "a b"]], "\t", "\n") == "1,5\ta b\n"
    assert te.to_csv([]) == ""


def test_append_rows_header_and_padding():
    """Tabelle ueber mehrere Seiten: wiederholte Kopfzeile faellt weg (auch mit anderem Leerraum), fehlende Spalten
    werden aufgefuellt; eine andere erste Zeile bleibt."""
    a = [["Pos", "Benennung", "Menge"], ["1", "Schraube", "4"]]
    b = [["Pos ", "benennung", "Menge"], ["2", "Mutter", "2", "extra"]]
    assert te.append_rows(a, b) == [["Pos", "Benennung", "Menge", ""], ["1", "Schraube", "4", ""],
                                    ["2", "Mutter", "2", "extra"]]
    assert te.append_rows(a, [["3", "Scheibe"]]) == a + [["3", "Scheibe", ""]]
    assert te.append_rows([], [["x"]]) == [["x"]]


def test_as_number():
    assert te.as_number("2,5") == 2.5 and te.as_number("2.5") == 2.5 and te.as_number("-3") == -3
    assert te.as_number("0,5") == 0.5 and te.as_number("0") == 0 and te.as_number(" 12 ") == 12
    for t in ("007", "1.000,5", "M6", "", "2,5 mm", "1,2,3"):
        assert te.as_number(t) is None, t


def test_to_xlsx(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    out = tmp_path / "t.xlsx"
    te.to_xlsx(DATA + [["4", "Stift", "007"]], str(out))
    ws = openpyxl.load_workbook(str(out)).active
    assert [c.value for c in ws[1]] == ["Pos", "Benennung", "Menge"] and ws["A1"].font.bold
    assert ws["A2"].value == 1 and ws["C3"].value == 2.5 and ws["B3"].value == "Mutter"
    assert ws["B4"].value is None and ws["C5"].value == "007" and not ws["A2"].font.bold
    assert ws.column_dimensions["B"].width > ws.column_dimensions["A"].width


# --- Hauptfenster
@pytest.fixture
def twin(win, monkeypatch):
    """Tabellenfenster (nicht modal) abfangen: got["dlg"], got["rows"] beim Oeffnen."""
    import ui_table
    got = {}

    def fake_show(dlg):
        got["dlg"] = dlg
        got["rows"] = dlg.rows()
    monkeypatch.setattr(ui_table.TableDialog, "show", fake_show)
    return win, got


def pdf_table(pg, data):
    """Tabelle mit Linien und Text auf eine PDF-Seite (wie test_gui_pdf_table)."""
    xs, ys = (50, 110, 250, 330), tuple(50 + 30 * i for i in range(len(data) + 1))
    for x in xs:
        pg.draw_line((x, ys[0]), (x, ys[-1]), width=0.8)
    for y in ys:
        pg.draw_line((xs[0], y), (xs[-1], y), width=0.8)
    for r, row in enumerate(data):
        for c, t in enumerate(row):
            if t:
                pg.insert_text((xs[c] + 5, ys[r] + 20), t, fontsize=10)


def test_gui_pdf_table(app, twin, tmp_path, monkeypatch):
    import diffvector as dv
    if not dv.available():
        pytest.skip("PyMuPDF fehlt")
    import pymupdf
    win, got = twin
    p = tmp_path / "tabelle.pdf"
    doc = pymupdf.open()
    pdf_table(doc.new_page(width=400, height=300), DATA)
    doc.save(str(p))
    doc.close()
    win._set_file("A", str(p))
    wait(app, lambda: win.payload is not None and not win.running)
    z = win.dpi_value() / 72.0
    win.canvas.sel_rects = [(int(40 * z), int(40 * z), int(340 * z), int(180 * z))]
    win.area_table()
    wait(app, lambda: not win.running and "rows" in got)
    assert got["rows"] == DATA
    dlg = got["dlg"]
    dlg.table.item(3, 1).setText("neu; mit Semikolon")       # bearbeitete Zelle kommt mit
    dlg.copy()
    from PySide6.QtWidgets import QApplication
    txt = QApplication.clipboard().text()
    assert txt.splitlines()[0] == "Pos;Benennung;Menge" and '"neu; mit Semikolon"' in txt
    dlg.cb_sep.setCurrentIndex(dlg.cb_sep.findData("\t"))
    out = tmp_path / "t.csv"
    monkeypatch.setattr(win, "_save_dialog", lambda *a: str(out))
    assert dlg.save() == str(out)
    raw = out.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b"2\tMutter\t2,5\r\n" in raw
    openpyxl = pytest.importorskip("openpyxl")
    seen = {}
    out2 = tmp_path / "t.xlsx"

    def fake_dialog(title, flt, default):
        seen.update(flt=flt, default=default)
        return str(tmp_path / "t")                                # ohne Endung: Excel wie gewaehlt
    monkeypatch.setattr(win, "_save_dialog", fake_dialog)
    dlg.btn_xlsx.click()
    assert seen["flt"].startswith("Excel") and seen["default"].endswith("_Tabelle.xlsx")
    ws = openpyxl.load_workbook(str(out2)).active
    assert ws["A1"].value == "Pos" and ws["A1"].font.bold and ws["C3"].value == 2.5


def test_gui_table_over_pages(app, twin, tmp_path):
    """Tabelle ueber zwei Seiten: zweite Auswahl auf Seite 2 anhaengen, wiederholte Kopfzeile faellt weg."""
    import diffvector as dv
    if not dv.available():
        pytest.skip("PyMuPDF fehlt")
    import pymupdf
    win, got = twin
    p = tmp_path / "lang.pdf"
    doc = pymupdf.open()
    pdf_table(doc.new_page(width=400, height=300), DATA[:3])
    pdf_table(doc.new_page(width=400, height=300), [DATA[0], DATA[3], ["4", "Stift", "8"]])
    doc.save(str(p))
    doc.close()
    win._set_file("A", str(p))
    wait(app, lambda: win.payload is not None and not win.running)
    z = win.dpi_value() / 72.0
    win.canvas.sel_rects = [(int(40 * z), int(40 * z), int(340 * z), int(150 * z))]
    win.area_table()
    wait(app, lambda: not win.running and "rows" in got)
    dlg = got["dlg"]
    assert got["rows"] == DATA[:3]
    win.sp_pa.setValue(2)
    wait(app, lambda: not win.running and not win.page_timer.isActive() and win.payload is not None)
    win.canvas.sel_rects = []
    assert win._table_append(dlg) is False                       # ohne Auswahl nur ein Hinweis
    win.canvas.sel_rects = [(int(40 * z), int(40 * z), int(340 * z), int(150 * z))]
    dlg.btn_append.click()
    wait(app, lambda: not win.running and dlg.table.rowCount() > 3)
    assert dlg.rows() == DATA + [["4", "Stift", "8"]]


def test_gui_bitmap_known_text(app, twin, tmp_path):
    """Bitmap ohne Texterkennung: schon gelesener Text (wie vom Hintergrund) wird benutzt."""
    win, got = twin
    img, words = draw_table(True)
    sheet = np.full((600, 900), 255, np.uint8)
    sheet[100:400, 100:720] = img
    p = tmp_path / "scan.png"
    cv2.imwrite(str(p), sheet)
    win._set_file("A", str(p))
    wait(app, lambda: win.payload is not None and not win.running)
    win.cache[win._text_key("A")[0]] = [(w[0] + 100, w[1] + 100, w[2] + 100, w[3] + 100, w[4]) for w in words]
    win.canvas.sel_rects = [(110, 110, 700, 380)]
    win.area_table()
    wait(app, lambda: not win.running and "rows" in got)
    assert got["rows"] == DATA


def test_gui_no_text(app, twin, tmp_path, monkeypatch):
    import diffreport as rep
    win, got = twin
    p = tmp_path / "leer.png"
    cv2.imwrite(str(p), np.full((300, 400), 255, np.uint8))
    win._set_file("A", str(p))
    wait(app, lambda: win.payload is not None and not win.running)
    monkeypatch.setattr(rep, "ocr_available", lambda: True)
    monkeypatch.setattr(rep, "ocr_any_orientation", lambda g, **k: [])
    win.canvas.sel_rects = [(10, 10, 200, 200)]
    win.area_table()
    wait(app, lambda: not win.running)
    app.processEvents()
    assert "rows" not in got


def test_gui_copy_text(app, twin, tmp_path, monkeypatch):
    """Text kopieren: Text im Bereich in Lesereihenfolge (Zeilen von oben, Teile von links) erst im Fenster zeigen
    (bearbeitbar, mit Quelle), dann in die Zwischenablage."""
    from PySide6.QtWidgets import QApplication, QLabel
    import ui_table
    win, _got = twin
    shown = {}
    monkeypatch.setattr(ui_table.TextDialog, "show", lambda dlg: shown.setdefault("dlg", dlg))
    img, words = draw_table(True)
    sheet = np.full((600, 900), 255, np.uint8)
    sheet[100:400, 100:720] = img
    p = tmp_path / "scan.png"
    cv2.imwrite(str(p), sheet)
    win._set_file("A", str(p))
    wait(app, lambda: win.payload is not None and not win.running)
    win.cache[win._text_key("A")[0]] = [(w[0] + 100, w[1] + 100, w[2] + 100, w[3] + 100, w[4]) for w in words]
    win.canvas.sel_rects = [(110, 110, 700, 200)]                # nur die ersten Zeilen
    QApplication.clipboard().setText("vorher")
    win.area_text()
    wait(app, lambda: not win.running and "dlg" in shown)
    dlg = shown["dlg"]
    assert QApplication.clipboard().text() == "vorher"           # noch nichts kopiert
    lines = dlg.edit.toPlainText().splitlines()
    assert lines[0] == " ".join(t for t in DATA[0] if t)
    assert "gelesener Text" in dlg.findChild(QLabel, "hint").text()
    dlg.edit.setPlainText(dlg.edit.toPlainText() + "\nergaenzt")
    dlg.btn_copy.click()
    txt = QApplication.clipboard().text()
    assert txt.splitlines()[0] == lines[0] and txt.endswith("ergaenzt")

