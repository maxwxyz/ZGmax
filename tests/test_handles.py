"""Anfasser gewaehlter Markierungen: Mauszeiger, Seitenmitten, Drehen (Feld "rot"), Ausgabe gedrehter Markierungen."""
import math
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402

from test_gui import app, compare, win, wait  # noqa: E402,F401

import diffreport as rep  # noqa: E402
from ui_canvas_geom import ann_handles, ann_hit, apply_handle, apply_rotation  # noqa: E402

SHAPE = (800, 1000)


# ----------------------------------------------------------------- Hilfen
def _wid(c, ix, iy):
    """Bildpunkt -> Widget-Position (mit Ansichtsdrehung)."""
    return c._xform().map(QPointF(*c.to_wid(ix, iy)))


def _send(c, kind, pos, buttons=Qt.MouseButton.NoButton, mods=Qt.KeyboardModifier.NoModifier):
    t = {"press": QEvent.Type.MouseButtonPress, "move": QEvent.Type.MouseMove,
         "release": QEvent.Type.MouseButtonRelease}[kind]
    btn = Qt.MouseButton.NoButton if kind == "move" else Qt.MouseButton.LeftButton
    gp = c.mapToGlobal(pos.toPoint())
    ev = QMouseEvent(t, pos, QPointF(gp), btn, buttons, mods)
    {"press": c.mousePressEvent, "move": c.mouseMoveEvent, "release": c.mouseReleaseEvent}[kind](ev)


def _drag(c, a_img, b_img, mods=Qt.KeyboardModifier.NoModifier, steps=4):
    """Mit der linken Maustaste von Bildpunkt a nach b ziehen."""
    pa = _wid(c, *a_img)
    _send(c, "press", pa, Qt.MouseButton.LeftButton)
    for i in range(1, steps + 1):
        f = i / steps
        p = _wid(c, a_img[0] + (b_img[0] - a_img[0]) * f, a_img[1] + (b_img[1] - a_img[1]) * f)
        _send(c, "move", p, Qt.MouseButton.LeftButton, mods)
    _send(c, "release", _wid(c, *b_img), Qt.MouseButton.NoButton, mods)


def _hover(c, ix, iy):
    _send(c, "move", _wid(c, ix, iy))
    return c.cursor().shape()


def _handle(c, name):
    a = c.anns[c.ann_selected]
    return next((hx, hy) for n, hx, hy in ann_handles(c.shape, a, c.scale) if n == name)


def _setup(app, win, pair, typ="rect", **extra):
    compare(app, win, *pair)
    c = win.canvas
    win._set_tool("hand")
    cx, cy = c.to_img(QPointF(c.width() / 2, c.height() / 2))
    w = 160 / c.scale
    win._ann_created(dict(type=typ, x=cx - w, y=cy - w / 2, x2=cx + w, y2=cy + w / 2, text="", nr=0,
                          color="#e11d48", size=2.0, **extra))
    win._set_tool("hand")
    app.processEvents()
    c.ann_selected = len(win.anns) - 1
    c.ann_multi = set()
    return c, win.anns[-1]


# ----------------------------------------------------------------- Oberflaeche
def test_cursor_shapes_over_handles(app, win, pair):
    c, a = _setup(app, win, pair)
    S = Qt.CursorShape
    assert _hover(c, *_handle(c, "tl")) == S.SizeFDiagCursor
    assert _hover(c, *_handle(c, "br")) == S.SizeFDiagCursor
    assert _hover(c, *_handle(c, "tr")) == S.SizeBDiagCursor
    assert _hover(c, *_handle(c, "bl")) == S.SizeBDiagCursor
    assert _hover(c, *_handle(c, "l")) == S.SizeHorCursor
    assert _hover(c, *_handle(c, "r")) == S.SizeHorCursor
    assert _hover(c, *_handle(c, "t")) == S.SizeVerCursor
    assert _hover(c, *_handle(c, "b")) == S.SizeVerCursor
    assert _hover(c, *_handle(c, "rot")) == S.BitmapCursor          # eigener Dreh-Zeiger
    x0, y0, x1, y1 = rep.rot_box(c.shape, a)
    assert _hover(c, (x0 + x1) / 2 + 30 / c.scale, y0) == S.SizeAllCursor   # auf der Markierung: verschieben
    a["rot"] = 90                                     # gedreht: Zeiger folgt der Lage
    assert _hover(c, *_handle(c, "r")) == S.SizeVerCursor
    assert _hover(c, *_handle(c, "t")) == S.SizeHorCursor
    assert _hover(c, *_handle(c, "tl")) == S.SizeBDiagCursor
    a["rot"] = 45
    assert _hover(c, *_handle(c, "r")) == S.SizeFDiagCursor


def test_cursor_while_dragging_handle(app, win, pair):
    c, a = _setup(app, win, pair)
    p = _handle(c, "r")
    _send(c, "press", _wid(c, *p), Qt.MouseButton.LeftButton)
    _send(c, "move", _wid(c, p[0] + 20 / c.scale, p[1]), Qt.MouseButton.LeftButton)
    assert c.cursor().shape() == Qt.CursorShape.SizeHorCursor      # beim Ziehen nicht "Verschieben"
    _send(c, "release", _wid(c, p[0] + 20 / c.scale, p[1]))


def test_side_handles_scale_one_direction(app, win, pair):
    c, a = _setup(app, win, pair)
    x0, y0, x1, y1 = a["x"], a["y"], a["x2"], a["y2"]
    d = 60 / c.scale
    _drag(c, _handle(c, "r"), (_handle(c, "r")[0] + d, _handle(c, "r")[1] + d))   # nur die Breite
    assert a["x"] == pytest.approx(x0) and a["y"] == pytest.approx(y0) and a["y2"] == pytest.approx(y1)
    assert a["x2"] == pytest.approx(x1 + d, abs=7 / c.scale)
    _drag(c, _handle(c, "t"), (_handle(c, "t")[0] + d, _handle(c, "t")[1] - d))   # nur die Hoehe, oben
    assert a["y"] == pytest.approx(y0 - d, abs=7 / c.scale) and a["y2"] == pytest.approx(y1)
    assert a["x"] == pytest.approx(x0)
    win.undo()
    win.undo()
    b = win.anns[-1]
    assert (b["x"], b["y"], b["x2"], b["y2"]) == pytest.approx((x0, y0, x1, y1))
    win.redo()
    assert win.anns[-1]["x2"] == pytest.approx(x1 + d, abs=7 / c.scale)


def test_rotate_handle_drag_shift_and_undo(app, win, pair):
    c, a = _setup(app, win, pair)
    cx, cy = rep.rot_center(c.shape, a)
    r = 200 / c.scale
    _drag(c, _handle(c, "rot"), (cx + r, cy))                    # nach rechts = 90 Grad
    a = win.anns[-1]
    assert a["rot"] == pytest.approx(90, abs=0.5)
    ang = math.radians(50)                                      # Umschalt: 15-Grad-Schritte (50 -> 45)
    _drag(c, _handle(c, "rot"), (cx + r * math.sin(ang), cy - r * math.cos(ang)), Qt.KeyboardModifier.ShiftModifier)
    assert win.anns[-1]["rot"] == 45
    win.undo()
    assert win.anns[-1]["rot"] == pytest.approx(90, abs=0.5)
    win.undo()
    assert "rot" not in win.anns[-1]                            # urspruenglich ungedreht
    win.redo()
    assert win.anns[-1]["rot"] == pytest.approx(90, abs=0.5)


def test_rotated_hit_and_resize(app, win, pair):
    c, a = _setup(app, win, pair)
    a["rot"] = 90
    cx, cy = rep.rot_center(c.shape, a)
    w = (a["x2"] - a["x"]) / 2                                  # halbe Breite (vor dem Drehen waagerecht)
    i = len(win.anns) - 1
    assert c.hit_ann(cx, cy - w) == i                           # jetzt oben: Rand der gedrehten Box
    assert c.hit_ann(cx - w, cy) is None                        # links: dort war die Box ungedreht
    tl = _handle(c, "tl")
    assert tl == pytest.approx(rep.rot_pt(a["x"], a["y"], cx, cy, 90))
    fixed = _handle(c, "l")                                     # gegenueber von "r"
    p = _handle(c, "r")
    _drag(c, p, (p[0], p[1] + 50 / c.scale))                    # "r" zeigt nach unten: laenger ziehen
    a = win.anns[-1]
    assert a["rot"] == 90
    assert _handle(c, "l") == pytest.approx(fixed, abs=1e-6)    # gegenueberliegende Seite bleibt stehen
    assert a["x2"] - a["x"] == pytest.approx(2 * w + 50 / c.scale, abs=7 / c.scale)


def test_rotated_text_and_polyline_rotation(app, win, pair):
    compare(app, win, *pair)
    c = win.canvas
    win._ann_created(dict(type="text", x=300, y=300, x2=300, y2=300, text="Hallo", nr=0, color="#e11d48", size=2.0))
    a = win.anns[-1]
    names = [n for n, _x, _y in ann_handles(c.shape, a)]
    assert "rot" in names and "size" in names
    a["rot"] = 30
    b = rep.ann_frame(c.shape, a)
    cx, cy = rep.rot_center(c.shape, a)
    assert ann_hit(c.shape, a, *rep.rot_pt(b[2] - 2, b[3] - 2, cx, cy, 30), 2)
    tl = rep.rot_pt(a["x"], a["y"], cx, cy, 30)
    apply_handle(c.shape, a, "size", *rep.rot_pt(b[2] + 40, b[3] + 10, cx, cy, 30))   # groesser: Ecke oben links bleibt
    cx2, cy2 = rep.rot_center(c.shape, a)
    assert rep.rot_pt(a["x"], a["y"], cx2, cy2, 30) == pytest.approx(tl, abs=1e-6)
    pl = dict(type="polyline", pts=[[0, 0], [100, 0]], x=0, y=0, x2=100, y2=0, color="#000000", size=1.0)
    out = dict(pl, pts=[list(q) for q in pl["pts"]])
    apply_rotation(c.shape, out, pl, 50 + 10, 0)                # Polylinie: Punkte drehen (90 Grad)
    assert "rot" not in out
    assert out["pts"][0] == pytest.approx([50, -50], abs=1e-6) and out["pts"][1] == pytest.approx([50, 50], abs=1e-6)


# ----------------------------------------------------------------- Kern: Ausgabe
def _rot_rect(**kw):
    d = dict(type="rect", x=300, y=350, x2=700, y2=450, color="#ff0000", size=2.0, text="", nr=0, rot=90,
             filled=True)
    d.update(kw)
    return d


def test_ann_bounds_and_old_projects():
    a = dict(type="rect", x=10, y=20, x2=110, y2=60, color="#ff0000", size=1.0, text="", nr=0)
    assert rep.ann_rot(a) == 0 and rep.ann_bounds(SHAPE, a) == rep.ann_frame(SHAPE, a)
    assert rep.ann_rot(dict(type="line", rot=30)) == 0            # Linien drehen nicht ueber "rot"
    b = rep.ann_bounds(SHAPE, _rot_rect())
    assert b[0] < 450 and b[2] > 550 and b[1] < 200 and b[3] > 600 and b[2] - b[0] < 140


def test_draw_rotated_rect_in_image():
    img = rep.draw_annotations(np.full((800, 1000, 3), 255, np.uint8), [_rot_rect()])
    assert tuple(img[250, 500]) == (0, 0, 255)                  # gedreht: senkrechter Balken (BGR rot)
    assert tuple(img[400, 350]) == (255, 255, 255)              # wo die ungedrehte Box laege: frei
    assert tuple(img[580, 520]) == (0, 0, 255)
    off = rep.draw_annotations(np.full((400, 400, 3), 255, np.uint8), [_rot_rect()], offset=(400, 200),
                               ref_shape=(800, 1000))           # Ausschnitt (Druck): gleiche Stelle
    assert tuple(off[50, 100]) == (0, 0, 255) and tuple(off[200, 10]) == (255, 255, 255)


def test_rotated_redaction_burned_in():
    img = np.zeros((800, 1000, 3), np.uint8) + 200
    a = dict(type="redact", x=300, y=350, x2=700, y2=450, color="#000000", size=2.0, text="", nr=0, rot=90)
    rep.apply_redactions(img, [a])
    assert img[250, 500].max() == 0 and img[400, 350].min() == 200
    bx = rep.redaction_boxes([a])[0]
    assert bx[0] <= 450 and bx[2] >= 550 and bx[1] <= 200 and bx[3] >= 600


def test_rotated_pdf_svg_xfdf(tmp_path):
    import pymupdf
    import diffxfdf
    img = np.full((800, 1000, 3), 255, np.uint8)
    anns = [_rot_rect(rot=30),
            dict(type="text", x=100, y=100, x2=100, y2=100, color="#0000ff", size=2.0, text="Hallo", nr=0, rot=30),
            dict(type="approval", x=100, y=600, x2=100, y2=600, color="#00aa00", size=2.0, text="OK", nr=0, rot=90),
            dict(type="ellipse", x=400, y=200, x2=600, y2=260, color="#ff00ff", size=2.0, text="", nr=0, rot=-30),
            dict(type="image", x=50, y=400, x2=250, y2=500, color="#000000", size=2.0, text="", nr=0, rot=20,
                 png=rep.image_png(np.zeros((10, 20, 3), np.uint8)))]
    out = str(tmp_path / "a.pdf")
    rep.build_annotated_pdf(out, img, [], anns, dpi=200)
    with pymupdf.open(out) as doc:
        pg = doc[0]
        kinds = [an.type[1] for an in pg.annots()]
        assert kinds.count("Polygon") >= 3 and "FreeText" in kinds     # Rahmen/Ellipse/Text als Polygon, Stempel 90
        poly = next(an for an in pg.annots() if an.type[1] == "Polygon")
        k = 72 / 200
        exp = [(px * k, py * k) for px, py in rep.rot_corners(SHAPE, anns[0])]
        assert np.allclose(np.array(poly.vertices), np.array(exp), atol=0.05)
        assert "Hallo" in pg.get_text()                              # gedrehter Text als Seiteninhalt
        ft = next(an for an in pg.annots() if an.type[1] == "FreeText")
        assert doc.xref_get_key(ft.xref, "Rotate")[1] == "270"
    svg = str(tmp_path / "a.svg")
    rep.build_svg(svg, img, (1000, 800), [], anns)
    txt = open(svg, encoding="utf-8").read()
    assert 'transform="rotate(30.00 500.0 400.0)"' in txt and txt.count('transform="rotate(') == 5
    x = str(tmp_path / "a.xfdf")
    diffxfdf.write_xfdf(x, anns, 200 / 72, 800 * 72 / 200)
    xt = open(x, encoding="utf-8").read()
    assert xt.count("<polygon ") == 2 and 'rotation="270"' in xt
    items, _ = diffxfdf.parse_xfdf(x, 800 * 72 / 200)
    back = diffxfdf.to_annotations(items, 200 / 72)
    assert any(b["type"] == "polygon" and len(b["pts"]) == 4 for b in back)   # Lage bleibt als Polygon erhalten
