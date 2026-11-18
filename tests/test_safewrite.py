"""Sicheres Schreiben: erst Hilfsdatei, dann ersetzen; Schreibfehler als verstaendliche Meldung; Nachfrage, wenn die
geoeffnete Zeichnung ueberschrieben wuerde."""
import os
import sys

import numpy as np
import pytest

from test_gui import app, win, wait, compare  # noqa: F401
from PySide6.QtWidgets import QFileDialog, QMessageBox  # noqa: E402

OLD = "ALTER INHALT"


def leftovers(folder):
    return [n for n in os.listdir(folder) if ".tmp-" in n]


def lock(monkeypatch, target):
    """Wie eine in einem anderen Programm geoeffnete Datei unter Windows: Ersetzen von target scheitert."""
    real = os.replace

    def replace(src, dst, **kw):
        if os.path.abspath(dst) == os.path.abspath(target):
            raise PermissionError(13, "Zugriff verweigert", str(dst))
        return real(src, dst, **kw)
    monkeypatch.setattr(os, "replace", replace)


# ----------------------------------------------------------------- Kern
def test_atomic_success_replaces(tmp_path):
    import safewrite as sw
    out = tmp_path / "bericht.pdf"
    out.write_text(OLD)
    with sw.atomic_path(str(out)) as tmp:
        assert os.path.dirname(tmp) == str(tmp_path) and tmp.endswith(".pdf") and tmp != str(out)
        with open(tmp, "w") as f:
            f.write("NEU")
        assert out.read_text() == OLD                     # Ziel bleibt bis zum Schluss das alte
    assert out.read_text() == "NEU" and not leftovers(tmp_path)
    new = tmp_path / "neu.csv"                            # Ziel gibt es noch nicht
    with sw.atomic_open(str(new), "w", encoding="utf-8") as f:
        f.write("a;b")
    assert new.read_text() == "a;b" and not leftovers(tmp_path)
    assert sw.write(str(new), lambda t: open(t, "w").write("x") and 7) == 7 and new.read_text() == "x"


def test_atomic_failure_keeps_old(tmp_path, monkeypatch):
    import diffcore as dc
    import safewrite as sw
    out = tmp_path / "liste.csv"
    out.write_text(OLD)
    with pytest.raises(sw.SaveError) as ei:               # Fehler mitten im Schreiben (z. B. Platte voll)
        with sw.atomic_open(str(out), "w") as f:
            f.write("halb")
            raise OSError(28, "No space left on device")
    assert out.read_text() == OLD and not leftovers(tmp_path)
    assert str(out) in str(ei.value) and "No space left" in str(ei.value) and "Schreibrechte" in str(ei.value)
    assert isinstance(ei.value, dc.DiffError) and isinstance(ei.value.__cause__, OSError)
    with pytest.raises(sw.SaveError):                     # Fehler einer Bibliothek (kein OSError)
        with sw.atomic_path(str(out)) as tmp:
            open(tmp, "w").close()
            raise RuntimeError("cannot write")
    assert out.read_text() == OLD and not leftovers(tmp_path)
    with pytest.raises(sw.SaveError):                     # nichts geschrieben
        with sw.atomic_path(str(out)):
            pass
    with pytest.raises(dc.Cancelled):                     # Abbruch bleibt Abbruch
        with sw.atomic_path(str(out)) as tmp:
            open(tmp, "w").close()
            raise dc.Cancelled()
    assert out.read_text() == OLD and not leftovers(tmp_path)
    lock(monkeypatch, str(out))                           # Ziel gesperrt: Ersetzen scheitert
    with pytest.raises(sw.SaveError):
        with sw.atomic_open(str(out), "w") as f:
            f.write("NEU")
    assert out.read_text() == OLD and not leftovers(tmp_path)
    with pytest.raises(sw.SaveError):                     # Ordner fehlt (Netzlaufwerk weg)
        with sw.atomic_open(str(tmp_path / "weg" / "x.csv"), "w") as f:
            f.write("NEU")


def test_library_writers_are_atomic(tmp_path, monkeypatch):
    """Die Schreibfunktionen der Bibliothek lassen bei einem Fehler das alte Ziel stehen."""
    import diffcore as dc
    import diffedit as de
    import diffreport as rep
    import safewrite as sw
    import tableextract as te
    img = np.full((60, 80, 3), 255, np.uint8)
    jobs = {"b.png": lambda p: dc.save_output(img, p, "png"), "b.pdf": lambda p: dc.save_output(img, p, "pdf"),
            "b.tif": lambda p: dc.save_output(img, p, "tif"), "l.csv": lambda p: rep.write_csv(p, []),
            "m.csv": lambda p: rep.write_dim_csv(p, []), "t.xlsx": lambda p: te.to_xlsx([["a", "1"]], p),
            "v.dxf": lambda p: de.write_vectors(p, de.vectorize(np.zeros((40, 40), np.uint8), "lines", 1.0), (40, 40), 200, None)}
    for name, fn in jobs.items():                         # Erfolg: richtige Datei, keine Hilfsdatei
        p = str(tmp_path / name)
        fn(p)
        assert os.path.getsize(p) > 0 and not leftovers(tmp_path), name
    for name, fn in jobs.items():
        p = tmp_path / name
        p.write_text(OLD)
        with monkeypatch.context() as m:
            lock(m, str(p))
            with pytest.raises(sw.SaveError):
                fn(str(p))
        assert p.read_text() == OLD and not leftovers(tmp_path), name


# ----------------------------------------------------------------- Oberflaeche
def shown(w):
    return w.banner.lbl.text(), w.banner.property("kind")


def test_export_jobs_report_write_error(app, win, pair, tmp_path, monkeypatch):
    compare(app, win, *pair)
    win.find_regs()
    wait(app, lambda: not win.running)
    for name, fn in (("e.png", win.export_image), ("e.csv", win.export_csv), ("e.pdf", win.export_pdf),
                     ("a.pdf", win.export_annotated_pdf)):
        out = tmp_path / name
        out.write_text(OLD)
        win.log.clear()
        win._save_dialog = lambda *a, out=out: str(out)
        with monkeypatch.context() as m:
            lock(m, str(out))
            fn()
            wait(app, lambda: not win.running)
        text, kind = shown(win)
        assert kind == "error" and "konnte nicht gespeichert werden" in text and str(out) in text, name
        assert "Schreibrechte" in text and "Traceback" not in (win.banner.details or ""), name
        assert "Gespeichert" not in win.log.toPlainText() and "Gespeichert" not in text, name
        assert out.read_text() == OLD and not leftovers(tmp_path), name
    out = tmp_path / "danach.csv"                         # Programm bleibt bedienbar: naechster Export klappt
    win._save_dialog = lambda *a: str(out)
    win.export_csv()
    wait(app, lambda: not win.running)
    assert out.stat().st_size > 10 and shown(win)[1] == "info" and "Gespeichert" in shown(win)[0]


@pytest.mark.skipif(sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="Ordnerrechte nur unter Unix ohne root pruefbar")
def test_export_into_readonly_folder(app, win, pair, tmp_path):
    compare(app, win, *pair)
    ro = tmp_path / "nur_lesen"
    ro.mkdir()
    old = ro / "e.png"
    old.write_text(OLD)
    os.chmod(ro, 0o555)
    try:
        for name, fn in (("e.png", win.export_image), ("neu.csv", win.export_csv)):
            win._save_dialog = lambda *a, name=name: str(ro / name)
            win.log.clear()
            fn()
            wait(app, lambda: not win.running)
            text, kind = shown(win)
            assert kind == "error" and "konnte nicht gespeichert werden" in text, name
            assert "Gespeichert" not in win.log.toPlainText(), name
        assert old.read_text() == OLD and os.listdir(ro) == ["e.png"]
    finally:
        os.chmod(ro, 0o755)


def test_direct_saves_report_write_error(app, win, pair, tmp_path, monkeypatch):
    """Speichern ohne Hintergrund-Job: Meldung in der Hinweisleiste, kein „Gespeichert“."""
    compare(app, win, *pair)
    win._ann_created(dict(type="text", x=100, y=100, x2=100, y2=100, text="Hallo", nr=0, color="#e11d48", size=2.0))
    win._ann_created(dict(type="measure", kind="dist", pts=[[100, 400], [500, 400]], x=100, y=400, x2=500, y2=400,
                          nr=0, color="#e11d48", size=2.0, text=""))
    for name, fn in (("a.json", win.ann_save), ("m.csv", win.export_measures), ("x.xfdf", win.export_xfdf),
                     ("z.svg", win.export_svg)):
        out = tmp_path / name
        out.write_text(OLD)
        win.log.clear()
        win.banner.hide()
        win._save_dialog = lambda *a, out=out: str(out)
        with monkeypatch.context() as m:
            lock(m, str(out))
            fn()
        text, kind = shown(win)
        assert kind == "error" and "konnte nicht gespeichert werden" in text and str(out) in text, name
        assert "Gespeichert" not in win.log.toPlainText() and "gespeichert:" not in text, name
        assert out.read_text() == OLD and not leftovers(tmp_path), name
        fn()                                              # ohne Sperre klappt es
        assert out.read_text() != OLD and shown(win)[1] == "info", name


def test_overwriting_source_asks(app, win, pair, tmp_path, monkeypatch):
    compare(app, win, *pair)
    other = str(tmp_path / "anders.png")
    asked = []

    def run(picks, answer):
        asked.clear()
        seq = iter(picks)
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (next(seq), ""))
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: (asked.append(a[2]), answer)[1])
        return win._save_dialog("Titel", "PNG (*.png)", "x.png")

    yes, no = QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No
    assert run([other], no) == other and not asked                     # fremde Datei: keine Nachfrage
    assert run([pair[0], other], no) == other and len(asked) == 1      # Nein: neu waehlen
    assert os.path.basename(pair[0]) in asked[0]
    assert run([pair[1], ""], no) == "" and len(asked) == 1            # Nein, dann abgebrochen (auch Zeichnung B)
    assert run([pair[0]], yes) == pair[0] and len(asked) == 1          # Ja: ausdruecklich ueberschreiben
    link = str(tmp_path / "verweis.png")
    if hasattr(os, "symlink") and sys.platform != "win32":             # dieselbe Datei unter anderem Namen
        os.symlink(pair[0], link)
        assert run([link, other], no) == other and len(asked) == 1
