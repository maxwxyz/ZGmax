"""Tests zu den Befunden der Durchsicht (Schwaerzung in Ausgaben, Ergebnis an Dateien gebunden, Startseite,
einzelne neue Zeichnung, gleiche Datei als A und B, ungleiche Seitenzahl, Pruefprotokoll)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QMessageBox  # noqa: E402

from test_gui import app, compare, wait, win  # noqa: E402,F401


def test_start_page_waits_for_second_file(app, win, pair):
    """Ein Feld der Startseite fuellen startet nichts - erst mit beiden Feldern wird verglichen."""
    win.start_choose("A", pair[0])
    app.processEvents()
    assert not win.running and win.payload is None
    assert win.stack.currentWidget() is win.start and win.start.btn_view.isEnabled()
    assert win.start.card_a.file.text() == "alt.png"
    win.start_choose("B", pair[1])
    wait(app, lambda: win.payload is not None and not win.running)
    assert not win.view_only and (win.path_a, win.path_b) == pair


def test_new_drawing_first_then_old(app, win, pair):
    """Nur die NEUE Zeichnung ansehen, spaeter die alte dazu: die Rollen stimmen (alt = A, neu = B)."""
    win.start_choose("B", pair[1])
    assert win.start.card_b.file.text() == "neu.png" and win.start.card_a.file.text() != "neu.png"
    win.start_view_only()
    wait(app, lambda: win.payload is not None and not win.running)
    assert win.view_only and win.path_a == pair[1] and win.path_b is None and win._single_is_b
    assert win._start_files() == (None, pair[1])
    win._set_file("A", pair[0])                              # „Mit anderer Zeichnung vergleichen“ (open_other)
    wait(app, lambda: not win.running and not win.view_only)
    assert (win.path_a, win.path_b) == pair and not win._single_is_b
    res = win.payload["res"]                                  # der neue Kreis ist „nur in neu“, nicht „nur in alt“
    assert (res.ob[620:780, 1170:1330] > 0).sum() > 100 and (res.oa[620:780, 1170:1330] > 0).sum() == 0


def test_start_page_drop_targets(app, win, pair):
    """Eine Zeichnung auf die Startseite ziehen: Ziele Alt, Neu, Nur ansehen; neben den Feldern = ansehen."""
    win.show_start()
    assert win._start_waiting()
    assert [t[0] for t in win._start_targets()] == ["view", "A", "B"]
    win._drop_chosen("A", [pair[0]])
    assert win.payload is None and not win.running and win.path_a == pair[0]
    assert [t[0] for t in win._start_targets()] == ["view", "A", "B"]
    win._drop_chosen("view", [pair[1]])                      # die andere allein ansehen: das wartende Feld ist leer
    wait(app, lambda: win.payload is not None and not win.running)
    assert win.view_only and win.path_a == pair[1] and win.path_b is None


def test_same_file_as_a_and_b(app, win, pair, tmp_path):
    """Dieselbe Datei als alt und neu: keine Aenderung, und das Projekt laesst sich speichern und oeffnen."""
    compare(app, win, pair[0], pair[0])
    wait(app, lambda: win.payload is not None and not win.running)
    assert not [r for r in win.payload["regs"] if r["typ"] != "verschoben"]
    proj = tmp_path / "gleich.zgmax"
    win._save_dialog = lambda *a, **k: str(proj)
    assert win.project_save(as_new=True)
    win.close_document()
    win.project_open(str(proj))
    wait(app, lambda: win.payload is not None and not win.running)
    assert win.path_a and win.path_b and not win.view_only


def test_failed_swap_blocks_export(app, win, pair, tmp_path, monkeypatch):
    """Laesst sich eine neu gewaehlte Datei nicht laden, bleibt das alte Ergebnis stehen - Berichte sind gesperrt."""
    compare(app, win, *pair)
    wait(app, lambda: win.payload is not None and not win.running)
    assert win.result_current()
    bad = tmp_path / "kaputt.png"
    bad.write_bytes(b"kein Bild")
    win._set_file("B", str(bad))
    wait(app, lambda: not win.running)
    assert win.payload is not None and not win.result_current()
    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: seen.append(a[2]))
    assert not win._need_result() and seen
    win._set_file("B", pair[1])
    wait(app, lambda: not win.running)
    assert win.result_current() and win._need_result()


def test_close_asks_for_work_on_other_pages(app, win, pair):
    """Markierungen einer anderen Seite zaehlen als Arbeit (Schliessen fragt, Autosave greift)."""
    compare(app, win, *pair)
    wait(app, lambda: win.payload is not None and not win.running)
    assert not win._has_work()
    win.page_anns = {"2:2": [dict(kind="text", x=1, y=1, text="x")]}
    assert win._has_work()
    win.page_anns = {}
    win.protocols = [dict(result="ok")]
    assert win._has_work()
    win.protocols = []


def test_protocol_notices_changed_measure():
    import diffreport as rep
    regs = [dict(nr=1, typ="geaendert", x=10, y=10, w=40, h=20, dim="25,4 → 26", status="ok", comment="")]
    rec = dict(items=[dict(nr=1, status=rep.reg_status(regs[0]), comment="", typ="geaendert", dim="25,4 → 26",
                           x=10, y=10, w=40, h=20)])
    assert rep.protocol_matches(rec, regs)
    assert not rep.protocol_matches(rec, [dict(regs[0], dim="25,4 → 27")])
    assert not rep.protocol_matches(rec, [dict(regs[0], x=300)])
    assert not rep.protocol_matches(rec, regs + [dict(regs[0], nr=2)])
    old = dict(items=[dict(nr=1, status=rep.reg_status(regs[0]), comment="")])   # altes Protokoll ohne Mass/Lage
    assert rep.protocol_matches(old, [dict(regs[0], dim="anders")])


def test_redaction_strips_read_text():
    import diffreport as rep
    anns = [dict(type="redact", x=0, y=0, x2=100, y2=100)]
    regs = [dict(nr=1, typ="geaendert", x=20, y=20, w=30, h=10, text_a="GEHEIM", text_b="GEHEIM 2", dim="1 → 2",
                 dim_kind="laenge", comment="bitte klaeren"),
            dict(nr=2, typ="neu", x=500, y=500, w=30, h=10, text_a="", text_b="OFFEN", dim="", dim_kind="")]
    out = rep.strip_redacted(regs, anns)
    assert out[0]["text_a"] == out[0]["text_b"] == out[0]["dim"] == "" and out[0]["comment"] == "bitte klaeren"
    assert out[1]["text_b"] == "OFFEN" and regs[0]["text_a"] == "GEHEIM"       # Original bleibt


def test_unequal_page_count_is_reported(app, win, tmp_path):
    """2 gegen 3 Seiten: die zusaetzliche Seite wird als hinzugekommen gemeldet, nicht verschwiegen."""
    import pymupdf

    def pdf(path, n):
        doc = pymupdf.open()
        for i in range(n):
            pg = doc.new_page(width=400, height=300)
            pg.draw_rect(pymupdf.Rect(40, 40, 360, 260), width=2)
            pg.insert_text((80, 150), f"Blatt {i + 1}", fontsize=24)
        doc.save(str(path))
        doc.close()
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    pdf(a, 2), pdf(b, 3)
    compare(app, win, str(a), str(b))
    wait(app, lambda: win.payload is not None and not win.running)
    win.compare_all_pages()
    wait(app, lambda: not win.running)
    msg = win.banner.lbl.text()
    assert "nur in Neu" in msg and "3" in msg


def test_batch_pairs_same_name_other_format(tmp_path):
    """a.pdf und a.png im selben Ordner: beide werden gepaart, keine verdraengt die andere."""
    import diffpipe as dp
    da, db = tmp_path / "alt", tmp_path / "neu"
    for d in (da, db):
        d.mkdir()
        for n in ("a.pdf", "a.png", "b.png"):
            (d / n).write_bytes(b"x")
    pairs, only_a, only_b = dp.batch_pairs(str(da), str(db), {".pdf", ".png"})
    assert sorted(os.path.basename(p[1]) for p in pairs) == ["a.pdf", "a.png", "b.png"]
    assert all(os.path.basename(p[1]) == os.path.basename(p[2]) for p in pairs) and not only_a and not only_b


def test_xlsx_keeps_text_with_equals_sign(tmp_path):
    """Gelesener Text, der mit „=“ beginnt, ist Text und keine Formel."""
    import openpyxl
    import tableextract
    out = tmp_path / "t.xlsx"
    tableextract.to_xlsx([["Pos", "Wert"], ["1", "=1+1"], ["2", "=HYPERLINK(\"http://x\")"]], str(out))
    ws = openpyxl.load_workbook(str(out)).active
    assert ws["B2"].data_type == "s" and ws["B2"].value == "=1+1" and ws["B3"].data_type == "s"


def test_page_scales_survive_other_path():
    """Massstaebe je Seite haengen an der Seite, nicht am Dateipfad (altes Format wird uebernommen)."""
    from ui_project import _page_scales
    assert _page_scales({"/alt/pfad/z.pdf#2": 5, "3": 10.0, "kaputt": "x"}, "/alt/pfad/z.pdf") == {"2": 5.0, "3": 10.0}
    assert _page_scales({"/fremd.pdf#2": 7, "/alt/z.pdf#2": 5}, "/alt/z.pdf") == {"2": 5.0}
    assert _page_scales(None, None) == {}


def test_project_rejects_tampered_embedded_file(app, win, pair, tmp_path):
    """Eingebettete Zeichnung, die nicht zur vermerkten Pruefsumme passt: das Projekt wird nicht gelesen."""
    import json
    import zipfile
    import ui_project
    compare(app, win, *pair)
    wait(app, lambda: win.payload is not None and not win.running)
    proj = tmp_path / "p.zgmax"
    win._save_dialog = lambda *a, **k: str(proj)
    win.act_embed.setChecked(True)
    assert win.project_save(as_new=True)
    assert not [f for f in os.listdir(tmp_path) if f.endswith(".tmp")]      # kein Rest vom Schreiben
    bad = tmp_path / "boese.zgmax"
    with zipfile.ZipFile(proj) as zin, zipfile.ZipFile(bad, "w") as zout:
        data = json.loads(zin.read(ui_project.PROJECT_JSON))
        data["files"]["a_sha256"] = "ab" * 32                               # passt nicht zum Inhalt
        for it in zin.infolist():
            zout.writestr(it, json.dumps(data) if it.filename == ui_project.PROJECT_JSON else zin.read(it.filename))
    with pytest.raises(ValueError):
        ui_project.read_project(str(bad))


def test_vector_fill_with_other_outline_is_a_change():
    """Zwei Flaechen mit fast gleichem Schwerpunkt, aber anderem Umriss gelten nicht als gleich."""
    import numpy as np
    import diffvector as dv
    sq = lambda r, n=4: dict(kind="f", pts=np.array(                       # noqa: E731
        [[r * np.cos(t), r * np.sin(t)] for t in np.linspace(0, 2 * np.pi, n, endpoint=False)]))
    assert dv._same(sq(10, 8), sq(10, 8), 0.5)
    assert not dv._same(sq(10, 8), sq(14, 9), 0.5)                          # anderer Umriss, gleiche Mitte
    assert dv._same(sq(10, 40), sq(10, 41), 0.5)                            # nur anders zerlegt


def test_export_side_by_side_and_slider(app, win, pair):
    """„Als Bild speichern“ in Nebeneinander und Schieber liefert, was zu sehen ist - nicht das Vergleichsbild."""
    import numpy as np
    compare(app, win, *pair)
    wait(app, lambda: win.payload is not None and not win.running)
    a, b = win.export_render("A", False, False), win.export_render("B", False, False)
    y = win.export_render("Y", False, False)
    assert y.shape[1] > 2 * a.shape[1] and np.array_equal(y[:, :a.shape[1]], a) and np.array_equal(y[:, -b.shape[1]:], b)
    win.canvas.blink_b = True
    assert np.array_equal(win.export_render("K", False, False), b)


def test_cli_batch_reports_partial_failure(tmp_path, pair):
    """Ordnervergleich auf der Befehlszeile: scheitert ein Paar, endet der Lauf mit Rueckgabewert 1."""
    import shutil
    import subprocess
    import sys
    da, db, out = tmp_path / "alt", tmp_path / "neu", tmp_path / "aus"
    da.mkdir(), db.mkdir()
    shutil.copy(pair[0], da / "gut.png"), shutil.copy(pair[1], db / "gut.png")
    (da / "kaputt.png").write_bytes(b"x"), (db / "kaputt.png").write_bytes(b"x")
    prog = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "programm", "drawing_diff.py")
    r = subprocess.run([sys.executable, prog, str(da), str(db), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 1 and os.path.isfile(out / "gut_diff.png"), r.stdout + r.stderr
