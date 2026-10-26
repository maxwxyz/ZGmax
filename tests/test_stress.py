"""Stresstest: jeden Menuebefehl und jedes Werkzeug in jeder Lage (nichts offen, einzelne Zeichnung, Vergleich,
Vektorvergleich) einmal ausloesen - mit Klicks und Ziehen im Bild. Jede Ausnahme laesst den Test scheitern.
So fallen Funktionen auf, die nur in manchen Situationen funktionieren."""
import logging
import os
import sys
import time
import traceback

import pytest

from test_gui import app, wait  # noqa: F401  (Fixture und Hilfsfunktion)

TIMES = [] if os.environ.get("ZV_STRESS_TIMES") else None   # Laufzeit je Befehl messen (Ausgabe am Ende)
SKIP = {"act_quit", "act_close", "act_new_window", "act_shortcut", "act_help", "act_help_cli", "act_logfile",
        "act_reset_settings", "act_cli"}


@pytest.fixture
def quiet_dialogs(monkeypatch, tmp_path):
    """Alle Rueckfragen und Dateidialoge sofort mit Abbrechen beantworten; offene Menues sofort schliessen."""
    from PySide6.QtCore import QSettings, QTimer
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (QApplication, QColorDialog, QDialog, QFileDialog, QInputDialog, QMenu,
                                   QMessageBox)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    for name in ("question", "information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Cancel)
    for name in ("about", "aboutQt"):                    # Ueber-Fenster: sonst wartet der Test auf einen Klick
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", "")))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", staticmethod(lambda *a, **k: ([], "")))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    for name, val in (("getItem", ("", False)), ("getText", ("", False)), ("getMultiLineText", ("", False)),
                      ("getInt", (1, False)), ("getDouble", (1.0, False))):
        monkeypatch.setattr(QInputDialog, name, staticmethod(lambda *a, v=val, **k: v))
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor()))
    monkeypatch.setattr(QDialog, "exec", lambda self: 0)
    closer = QTimer()
    closer.timeout.connect(lambda: [m.close() for m in QApplication.topLevelWidgets()
                                    if isinstance(m, QMenu) and m.isVisible()])
    closer.start(100)
    yield
    closer.stop()


def _collect(errors):
    class H(logging.Handler):
        def emit(self, r):
            if r.levelno >= logging.ERROR:
                errors.append("LOG: " + r.getMessage())
    h = H()
    logging.getLogger().addHandler(h)
    old = sys.excepthook
    sys.excepthook = lambda *a: errors.append("".join(traceback.format_exception(*a)))
    return h, old


def _settle(app, w, t=60):
    t0 = time.time()
    while w.running and time.time() - t0 < t:
        app.processEvents()
        time.sleep(0.01)
    for _ in range(3):
        app.processEvents()


def _all_actions(app, w, label, tmp_path, errors):
    from PySide6.QtGui import QAction
    w._save_dialog = lambda *a, **k: str(tmp_path / f"out_{label}_{time.time_ns()}.png")
    acts = [(n, getattr(w, n)) for n in dir(w) if n.startswith("act_")]
    acts = [(n, a) for n, a in acts if isinstance(a, QAction) and n not in SKIP]
    acts += [("tool_" + k, a) for k, a in w.tool_actions.items()] + [("mode_" + k, a) for k, a in w.mode_actions.items()]
    for n, a in acts:
        if not a.isEnabled():
            continue
        before = len(errors)
        t0 = time.time()
        try:
            a.trigger()
            _settle(app, w)
            if a.isCheckable() and a.isChecked() and not n.startswith(("tool_", "mode_")):
                a.trigger()
                _settle(app, w)
        except Exception:
            errors.append(traceback.format_exc())
        for i in range(before, len(errors)):
            errors[i] = f"[{label}] {n}: {errors[i]}"
        if TIMES is not None:
            TIMES.append((time.time() - t0, label, n))
        w._set_tool("hand")


def _all_tools(app, w, label, errors):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    c = w.canvas
    for key in list(w.tool_actions):
        if not w.tool_actions[key].isEnabled():
            continue
        before = len(errors)
        try:
            w._set_tool(key)
            QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(300, 300))
            for x in range(310, 420, 20):
                QTest.mouseMove(c, QPoint(x, 300 + x // 4))
            w._set_tool("hand")                       # Werkzeugwechsel mitten im Ziehen
            QTest.mouseMove(c, QPoint(430, 410))
            QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=QPoint(430, 410))
            w._set_tool(key)
            QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(300, 300))
            QTest.mouseMove(c, QPoint(420, 400))
            QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=QPoint(420, 400))
            app.processEvents()
            if c.inline_editor is not None:
                QTest.keyClicks(c.inline_editor, "abc")
                QTest.keyClick(c.inline_editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
            for pt in ((500, 350), (560, 420)):
                QTest.mouseClick(c, Qt.MouseButton.LeftButton, pos=QPoint(*pt))
            QTest.mouseDClick(c, Qt.MouseButton.LeftButton, pos=QPoint(600, 380))
            app.processEvents()
            if c.inline_editor is not None:
                QTest.keyClick(c.inline_editor, Qt.Key.Key_Escape)
            QTest.keyClick(c, Qt.Key.Key_Return)
            QTest.mouseClick(c, Qt.MouseButton.RightButton, pos=QPoint(350, 330))
            if key == "area":                            # Auswahl, alle Befehle der Leiste, verschieben
                QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(250, 250))
                QTest.mouseMove(c, QPoint(450, 420))
                QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=QPoint(450, 420))
                for k, b in list(w.area_buttons.items()):
                    if k not in ("cut", "clear") and b.isVisible():
                        b.click() if hasattr(b, "click") else b.trigger()
                        _settle(app, w)
            w._set_tool("hand")
            QTest.mousePress(c, Qt.MouseButton.LeftButton, pos=QPoint(360, 340))
            QTest.mouseMove(c, QPoint(380, 360))
            QTest.mouseRelease(c, Qt.MouseButton.LeftButton, pos=QPoint(380, 360))
            QTest.keyClick(c, Qt.Key.Key_Delete)
            QTest.keyClick(c, Qt.Key.Key_Escape)
            w.undo()
            w.redo()
            _settle(app, w)
            c.repaint()
        except Exception:
            errors.append(traceback.format_exc())
        for i in range(before, len(errors)):
            errors[i] = f"[{label}] Werkzeug {key}: {errors[i]}"


def test_every_action_and_tool_in_every_situation(app, quiet_dialogs, pair, tmp_path):  # noqa: F811
    import pymupdf
    import drawing_viewer as vw
    errors = []
    h, old_hook = _collect(errors)
    try:
        for name, shift in (("va.pdf", 0), ("vb.pdf", 8)):            # Vektor-PDF-Paar
            d = pymupdf.open()
            pg = d.new_page(width=595, height=420)
            pg.draw_rect(pymupdf.Rect(50, 50, 300, 200), width=1.5)
            pg.insert_text((60 + shift, 250), "Bohrung 25 H7", fontsize=14)
            pg.draw_line((320, 60), (520 + shift, 300), width=0.7)
            d.save(str(tmp_path / name))
        w = vw.MainWindow()
        w.resize(1300, 820)
        w.show()
        _all_actions(app, w, "leer", tmp_path, errors)
        w._set_file("A", pair[0])
        _settle(app, w)
        w._ann_created(dict(type="rect", x=100, y=100, x2=300, y2=200, text="", nr=0, color="#e11d48", size=2.0))
        _all_actions(app, w, "ansicht", tmp_path, errors)
        _all_tools(app, w, "ansicht", errors)
        w.close_document()
        w._set_file("A", pair[0], compute=False)
        w._set_file("B", pair[1])
        _settle(app, w)
        w.find_regs()
        _settle(app, w)
        w.start_area()                                               # mit Zuschnitt-Rahmen (dessen Befehle aktiv)
        w.canvas.sel_rects = [(100, 100, 600, 500)]
        w._area_changed()
        w.set_crop_frame()
        _all_actions(app, w, "vergleich", tmp_path, errors)
        _all_tools(app, w, "vergleich", errors)
        w.close_document()
        w._set_file("A", str(tmp_path / "va.pdf"), compute=False)
        w._set_file("B", str(tmp_path / "vb.pdf"))
        _settle(app, w)
        w.chk_vec.setChecked(True)
        _settle(app, w)
        _all_actions(app, w, "vektor", tmp_path, errors)
        w._dirty = False
        for other in list(vw.WINDOWS) + [w]:
            other._dirty = False
            other.close()
    finally:
        logging.getLogger().removeHandler(h)
        sys.excepthook = old_hook
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().clear()
    if TIMES:
        for t, label, n in sorted(TIMES, reverse=True)[:25]:
            print(f"{t:7.2f}s  {label:10s} {n}", file=sys.stderr)
    assert not errors, "\n\n".join(errors[:10])
