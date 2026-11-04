"""Diagramm digitalisieren: Kalibrierung, Bereinigen, Verfolgen sich kreuzender Kurven, Tabelle, CSV, Polynom, Dialog."""
import os

import cv2
import numpy as np
import pytest

import digitize as dg

# Kuenstliches Kraft-Weg-Diagramm: x 0..10 mm auf 80..860 px, y 0..500 N auf 620..40 px
X0, X1, Y0, Y1 = 80, 860, 620, 40
CURVES = [
    (lambda s: 40 * s, 0.0, 10.0),
    (lambda s: 5 * s ** 2 - 10 * s + 50, 0.5, 10.0),
    (lambda s: 100 + 25 * s, 1.0, 9.0),
]


def px(s, f):
    return X0 + s / 10.0 * (X1 - X0), Y0 - f / 500.0 * (Y0 - Y1)


def draw_diagram(thick=2, aa=True, curves=None):
    img = np.full((700, 920), 255, np.uint8)
    for k in range(11):                                        # Gitter (1 px) und Teilstriche
        x = int(round(X0 + k * (X1 - X0) / 10))
        cv2.line(img, (x, Y1), (x, Y0), 0, 1)
        cv2.line(img, (x, Y0), (x, Y0 + 8), 0, 2)
        cv2.putText(img, str(k), (x - 6, Y0 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1, cv2.LINE_AA)
    for k in range(6):
        y = int(round(Y0 - k * (Y0 - Y1) / 5))
        cv2.line(img, (X0, y), (X1, y), 0, 1)
        cv2.line(img, (X0 - 8, y), (X0, y), 0, 2)
        cv2.putText(img, str(100 * k), (X0 - 50, y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 0, 1, cv2.LINE_AA)
    cv2.line(img, (X0, Y0), (X1, Y0), 0, 3)                     # Achsen kraeftig
    cv2.line(img, (X0, Y0), (X0, Y1), 0, 3)
    cv2.putText(img, "Weg s [mm]", (420, 685), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1, cv2.LINE_AA)
    cv2.putText(img, "F [N]", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1, cv2.LINE_AA)
    for f, a, b in CURVES if curves is None else curves:
        s = np.linspace(a, b, 400)
        pts = np.array([px(v, f(v)) for v in s], np.float64)
        cv2.polylines(img, [np.round(pts * 4).astype(np.int32)], False, 0, thick,
                      cv2.LINE_AA if aa else cv2.LINE_8, shift=2)
    cv2.putText(img, "1", (300, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 1, cv2.LINE_AA)
    return img


def calib():
    return dg.Calib((X0, Y0), 0, (X1, Y0), 10, (X0, Y0), 0, (X0, Y1), 500)


def draw_dashed(img, f, a, b, dash=14, gap=9, dot=False, thick=2):
    """Kurve f von a bis b gestrichelt (dot=True: strichpunktiert) in img zeichnen; Laengen in Pixeln."""
    s = np.linspace(a, b, 4000)
    pts = np.array([px(v, f(v)) for v in s])
    arc = np.r_[0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
    period = dash + gap + ((3 + gap) if dot else 0)
    ph = arc % period
    on = ph < dash
    if dot:
        on |= (ph >= dash + gap) & (ph < dash + gap + 3)
    edges = np.flatnonzero(np.diff(np.r_[0, on.astype(int), 0]))
    for k0, k1 in zip(edges[::2], edges[1::2]):
        cv2.polylines(img, [np.round(pts[k0:k1] * 4).astype(np.int32)], False, 0, thick, cv2.LINE_AA, shift=2)
    return img


# ------------------------------------------------------------------------------------------- Kalibrierung

def test_calib_linear_roundtrip():
    c = calib()
    v = c.to_values([(X0, Y0), (X1, Y1), ((X0 + X1) / 2, (Y0 + Y1) / 2)])
    assert np.allclose(v, [(0, 0), (10, 500), (5, 250)])
    assert np.allclose(c.to_pixels(v), [(X0, Y0), (X1, Y1), ((X0 + X1) / 2, (Y0 + Y1) / 2)])


def test_calib_log_and_rotated():
    c = dg.Calib((100, 500), 1, (400, 500), 1000, (100, 500), 0.1, (100, 200), 10, xlog=True, ylog=True)
    v = c.to_values([(200, 500), (100, 350), (300, 275)])
    assert np.allclose(v[0], (10, 0.1))
    assert np.allclose(v[1], (1, 1))
    assert np.allclose(v[2], (100, 10 ** 0.5))
    assert np.allclose(c.to_pixels(v), [(200, 500), (100, 350), (300, 275)])
    # um 10 Grad gedrehter Scan: Werte bleiben gleich
    a = np.radians(10)
    rot = lambda p: (np.cos(a) * p[0] - np.sin(a) * p[1], np.sin(a) * p[0] + np.cos(a) * p[1])
    c2 = dg.Calib(rot((0, 0)), 0, rot((100, 0)), 10, rot((0, 0)), 0, rot((0, -100)), 50)
    assert np.allclose(c2.to_values([rot((50, -40))]), [(5, 20)])
    with pytest.raises(ValueError):
        dg.Calib((0, 0), 0, (100, 0), 10, (0, 0), 0, (50, 0), 5)
    with pytest.raises(ValueError):
        dg.Axis(0, 10, log=True)


# ------------------------------------------------------------------------------------------- Bild

def test_find_axes_and_snap():
    ink = dg.binarize(draw_diagram())
    ax = dg.find_axes(ink)
    assert abs(ax["x_axis"][0] - Y0) <= 1.5 and ax["x_axis"][1] <= X0 + 2 and ax["x_axis"][2] >= X1 - 2
    assert abs(ax["y_axis"][0] - X0) <= 1.5
    assert len(ax["vlines"]) >= 10 and len(ax["hlines"]) >= 5
    x = (X0 + 5 * (X1 - X0) / 10)
    assert abs(dg.snap_tick(ink, ax["x_axis"][0], None, x + 7, True) - x) <= 1.5
    assert dg.snap_tick(ink, ax["x_axis"][0], None, x + 40, True) == x + 40     # nichts in der Naehe


def test_clean_ink_removes_grid_and_text():
    img = draw_diagram()
    clean, lines = dg.clean_ink(img)
    ink = dg.binarize(img)
    assert clean[Y0, (X0 + X1) // 2] == 0                      # Achse weg
    assert clean[(Y0 + Y1) // 2, int(X0 + 3 * (X1 - X0) / 10)] == 0   # senkrechte Gitterlinie weg (keine Kurve)
    assert clean[290:305, 298:315].sum() == 0 and ink[290:305, 298:315].sum() > 0    # Text weg
    x, y = px(3.3, CURVES[0][0](3.3))
    assert clean[int(y) - 3:int(y) + 4, int(x)].any()          # Kurve bleibt


@pytest.mark.parametrize("aa", [True, False])
def test_trace_three_crossing_curves(aa):
    img = draw_diagram(aa=aa)
    clean, lines = dg.clean_ink(img)
    c = calib()
    clicks = [3.0, 4.5, 4.5]                                   # Stelle, an der jede Kurve frei liegt
    traced = []
    for (f, a, b), s in zip(CURVES, clicks):
        pts = dg.trace_curve(clean, px(s, f(s)), lines)
        vals = dg.to_values(pts, c)
        traced.append(vals)
        assert vals[:, 0].min() <= a + 0.1 and vals[:, 0].max() >= b - 0.1, (vals[:, 0].min(), vals[:, 0].max())
        err = np.abs(vals[:, 1] - f(vals[:, 0]))
        assert np.percentile(err, 98) < 2.0, np.percentile(err, 98)    # 1 px = 0,86 N
        assert err.max() < 3.5
    xs = dg.make_xs(traced, step=0.5, extend=0.1)              # Enden unter der Achse: 8 px Zugabe
    assert xs[0] == 0 and xs[-1] == 10 and len(xs) == 21
    tab = dg.resample(traced, xs, extend=0.1)
    assert np.isnan(tab[0, 1]) and np.isnan(tab[0, 2]) and np.isnan(tab[-1, 2])   # ausserhalb leer
    for k, (f, a, b) in enumerate(CURVES):
        ok = np.isfinite(tab[:, k])
        assert np.allclose(tab[ok, k], f(xs[ok]), atol=4)
    co, r2 = dg.fit_poly(*dg._clean_xy(traced[1]), 2)
    assert r2 > 0.999 and np.allclose(co, [5, -10, 50], atol=[0.3, 3, 6])


def test_merge_points():
    old = np.array([(0, 1), (1, 1), (2, 1), (3, 1)], float)
    new = np.array([(1.5, 5), (2.5, 5)], float)
    m = dg.merge_points(old, new)
    assert m[:, 0].tolist() == [0, 1, 1.5, 2.5, 3]


# ------------------------------------------------------------------------------------------- Ausgabe

def test_resample_csv_fit():
    a = np.array([(0, 0), (1, 2), (2, 4)], float)
    b = np.array([(1, 1), (3, 3)], float)
    xs = dg.make_xs([a, b], count=4)
    assert np.allclose(xs, [0, 1, 2, 3])
    t = dg.resample([a, b], xs)
    assert np.allclose(t[:3, 0], [0, 2, 4]) and np.isnan(t[3, 0]) and np.isnan(t[0, 1])
    txt = dg.to_csv(xs, t, ["Weg s [mm]", "Kurve; 1", "Kurve 2"], sep=";", decimal=",")
    lines = txt.splitlines()
    assert lines[0] == 'Weg s [mm];"Kurve; 1";Kurve 2'
    assert lines[1] == "0;0;" and lines[4] == "3;;3"
    t2 = dg.resample([np.array([(0, 0.25), (1, 1.25)])], [0.5])
    assert dg.to_csv([0.5], t2, ["x", "y"], decimal=",").splitlines()[1] == "0,5;0,75"
    assert dg.to_csv([0.5], t2, ["x", "y"], sep="\t", decimal=".").splitlines()[1] == "0.5\t0.75"
    co, r2 = dg.fit_poly([0, 1, 2, 3], [1, 3, 5, 7], 1)
    assert np.allclose(co, [2, 1]) and r2 == pytest.approx(1)
    co, r2 = dg.fit_poly([0, 1], [1, 3], 3)                     # zu wenige Punkte: Grad 1
    assert len(co) == 2
    assert dg.poly_text([2, -1.5, 0], "s", "F") == "F = 2·s² - 1,5·s"
    assert dg.poly_text([0.5, 3], decimal=".") == "y = 0.5·x + 3"
    assert dg.make_xs([np.array([(0.3, 0), (2.1, 0)])], step=0.5).tolist() == [0.5, 1.0, 1.5, 2.0]


# ------------------------------------------------------------------------------------------- Zusaetze

def label_items(extra=()):
    """Beschriftungen von draw_diagram wie von der Texterkennung: (x0, y0, x1, y1, text, score, rot)."""
    items = []
    for k in range(11):
        x = int(round(X0 + k * (X1 - X0) / 10))
        (tw, th), _ = cv2.getTextSize(str(k), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        items.append((x - 6, Y0 + 30 - th, x - 6 + tw, Y0 + 30, str(k), 0.9, 0))
    for k in range(6):
        y = int(round(Y0 - k * (Y0 - Y1) / 5))
        (tw, th), _ = cv2.getTextSize(str(100 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        items.append((X0 - 50, y + 5 - th, X0 - 50 + tw, y + 5, str(100 * k), 0.9, 0))
    items.append((420, 670, 520, 690, "Weg s [mm]", 0.9, 0))
    return items + list(extra)


def test_auto_axes_from_labels():
    ink = dg.binarize(draw_diagram())
    x3 = int(round(X0 + 3 * (X1 - X0) / 10))
    wrong = [(x3 - 6, Y0 + 50, x3 + 6, Y0 + 64, "8", 0.6, 0)]          # falsch gelesene Zahl -> Ausreisser
    res = dg.auto_axes(ink, label_items(wrong))
    assert res["nx"] == 11 and res["ny"] == 6 and not res["xlog"] and not res["ylog"]
    c = dg.Calib(res["x1"][0], res["x1"][1], res["x2"][0], res["x2"][1], res["y1"][0], res["y1"][1],
                 res["y2"][0], res["y2"][1])
    assert np.allclose(c.to_values([(X0, Y0), (X1, Y1), (470, 330)]), [(0, 0), (10, 500), (5, 250)], atol=[0.03, 1.5])
    assert dg.auto_axes(ink, []) == {}
    assert dg.parse_number("1,5") == 1.5 and dg.parse_number("\u22122O") == -20 and dg.parse_number("F [N]") is None


def test_auto_axes_log():
    img = np.full((500, 800), 255, np.uint8)
    cv2.line(img, (100, 400), (700, 400), 0, 2)
    cv2.line(img, (100, 400), (100, 50), 0, 2)
    items = []
    for k, v in enumerate(["1", "10", "100", "1000"]):
        x = 100 + 200 * k
        cv2.line(img, (x, 400), (x, 50), 0, 1)
        items.append((x - 10, 415, x + 10, 430, v, 0.9, 0))
    for k, v in enumerate(["0", "50", "100"]):
        y = 400 - 150 * k
        cv2.line(img, (100, y), (700, y), 0, 1)
        items.append((60, y - 7, 90, y + 7, v, 0.9, 0))
    res = dg.auto_axes(dg.binarize(img), items)
    assert res["xlog"] and not res["ylog"] and res["x1"][1] == 1 and res["x2"][1] == 1000
    c = dg.Calib(res["x1"][0], res["x1"][1], res["x2"][0], res["x2"][1], res["y1"][0], res["y1"][1],
                 res["y2"][0], res["y2"][1], xlog=True)
    assert np.allclose(c.to_values([(400, 250)]), [(10 ** 1.5, 50)], rtol=0.02)


def draw_color_diagram():
    """Wie draw_diagram, aber die drei Kurven rot, blau und gruen auf schwarzem Gitter."""
    img = np.full((700, 920, 3), 255, np.uint8)
    for k in range(11):
        x = int(round(X0 + k * (X1 - X0) / 10))
        cv2.line(img, (x, Y1), (x, Y0), (0, 0, 0), 1)
    for k in range(6):
        y = int(round(Y0 - k * (Y0 - Y1) / 5))
        cv2.line(img, (X0, y), (X1, y), (0, 0, 0), 1)
    for (f, a, b), col in zip(CURVES, [(30, 30, 220), (200, 80, 20), (40, 160, 40)]):
        s = np.linspace(a, b, 400)
        pts = np.array([px(v, f(v)) for v in s])
        cv2.polylines(img, [np.round(pts * 4).astype(np.int32)], False, col, 2, cv2.LINE_AA, shift=2)
    return img


def test_color_layers_and_trace():
    img = draw_color_diagram()
    layers = dg.color_layers(img)
    assert len(layers) == 3
    c = calib()
    found = set()
    for l in layers:
        p = dg.layer_start(l["mask"])
        pts = dg.trace_curve(l["mask"], p)
        vals = dg.to_values(pts, c)
        errs = [np.percentile(np.abs(vals[:, 1] - f(vals[:, 0])), 95) for f, a, b in CURVES]
        k = int(np.argmin(errs))
        assert errs[k] < 2.0
        a, b = CURVES[k][1:]
        assert vals[:, 0].min() <= a + 0.1 and vals[:, 0].max() >= b - 0.1
        found.add(k)
    assert found == {0, 1, 2}
    assert dg.layer_at(layers, px(3.3, 40 * 3.3)) is not None
    assert dg.color_layers(draw_diagram()) == [] and dg.color_layers(cv2.cvtColor(draw_diagram(), cv2.COLOR_GRAY2BGR)) == []


def test_smooth_spline():
    xk = np.array([0, 1, 2, 4.0])
    assert np.allclose(dg.natural_spline(xk, 3 * xk + 1, [0.5, 3]), [2.5, 10])
    rng = np.random.default_rng(3)
    x = np.linspace(0, 10, 600)
    y = 5 * x ** 2 - 10 * x + 50 + rng.normal(0, 3, len(x))
    xs = np.linspace(0, 10, 41)
    t = dg.smooth_resample([np.column_stack([x, y])], xs, knots=10)[:, 0]
    assert np.abs(t - (5 * xs ** 2 - 10 * xs + 50)).max() < 4
    tp = dg.poly_resample([np.column_stack([x, y])], xs, 2)[:, 0]
    assert np.abs(tp - (5 * xs ** 2 - 10 * xs + 50)).max() < 2
    assert dg.r2_of(y, 5 * x ** 2 - 10 * x + 50) > 0.99


def test_xlsx(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    xs = np.array([0, 1, 2.0])
    tab = np.array([[0, np.nan], [1, 2], [2, 4]], float)
    path = tmp_path / "d.xlsx"
    dg.to_xlsx(str(path), xs, tab, ["Weg s [mm]", "K1", "K2"], chart_title="Federn", y_title="Kraft F [N]",
               notes=["K1: y = x"], colors=["E11D48", "2563EB"])
    wb = openpyxl.load_workbook(path)
    ws = wb["Werte"]
    assert [c.value for c in ws[1]] == ["Weg s [mm]", "K1", "K2"]
    assert ws["B3"].value == 1 and ws["C2"].value is None and ws["C4"].value == 4
    assert wb["Funktionen"]["A1"].value == "K1: y = x"
    assert len(ws._charts) == 1


def _eval_formula(ws, text):
    """Excel-Formel aus to_xlsx (nur Zellbezuege, +, *, ^) mit den Zellwerten des Blatts ausrechnen."""
    import re
    expr = re.sub(r"\$?([A-Z]+)\$?(\d+)", lambda m: repr(float(ws[f"{m.group(1)}{m.group(2)}"].value)), text[1:])
    return eval(expr.replace("^", "**"))                       # noqa: S307 - nur Zahlen und Operatoren


def test_xlsx_live_formulas(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    xs = np.array([0, 1, 2, 3.0])
    tab = np.array([[1, np.nan], [3.1, 2], [8.9, 4], [19, 6]], float)
    co1, r1 = dg.fit_poly(xs, tab[:, 0], 2)
    co2, r2 = dg.fit_poly(xs[1:], tab[1:, 1], 1)
    path = tmp_path / "f.xlsx"
    dg.to_xlsx(str(path), xs, tab, ["s", "K1", "K2"], polys=[(co1, r1, 0, 3), (co2, r2, 1, 3)], xrev=True,
               labels=("Polynom", "Kurve", "von x", "bis x"))
    wb = openpyxl.load_workbook(path)
    ws = wb["Werte"]
    assert [c.value for c in ws[1]][:7] == ["Kurve", "a0", "a1", "a2", "R²", "von x", "bis x"]
    assert ws["A2"].value == "K1" and ws["B2"].value == pytest.approx(co1[2])
    assert ws["D2"].value == pytest.approx(co1[0])
    assert ws["A3"].value == "K2" and ws["C3"].value == pytest.approx(co2[0]) and ws["D3"].value is None
    assert [c.value for c in ws[5]][:6] == ["s", "K1", "K2", "K1 (Polynom)", "K2 (Polynom)", None]
    assert ws["A6"].value == 0 and ws["B6"].value == 1 and ws["C6"].value is None    # Messwerte bleiben Zahlen
    assert ws["D6"].value == "=$B$2+$C$2*A6+$D$2*A6^2"                              # Formel, rechnet live
    assert ws["E6"].value is None and ws["E7"].value == "=$B$3+$C$3*A7"             # K2 erst ab x = 1
    for r in range(6, 10):
        assert _eval_formula(ws, ws[f"D{r}"].value) == pytest.approx(np.polyval(co1, xs[r - 6]))
    ch = ws._charts[0]
    assert len(ch.series) == 2 and ch.x_axis.scaling.orientation == "maxMin"
    assert ch.y_axis.scaling.orientation == "minMax"
    assert ws.freeze_panes == "A6"


def test_reversed_axes():
    """Achsen, deren Werte im Bild fallen (x nach rechts 10 -> 0, y nach oben 500 -> 0)."""
    c = dg.Calib((X0, Y0), 10, (X1, Y0), 0, (X0, Y0), 500, (X0, Y1), 0)
    assert c.x_reversed and c.y_reversed and not calib().x_reversed and not calib().y_reversed
    img = draw_diagram()
    clean, lines = dg.clean_ink(img)
    f, a, b = CURVES[0]                                         # F = 40 s -> y' = 500 - 40 (10 - x') = 100 + 40 x'
    vals = dg.to_values(dg.trace_curve(clean, px(3.0, f(3.0)), lines), c)
    xs = dg.make_xs([vals], step=1.0, extend=0.1)
    assert xs[0] == 0 and xs[-1] == 10 and np.all(np.diff(xs) > 0)
    tab = dg.resample([vals], xs, extend=0.1)
    assert np.allclose(tab[:, 0], 100 + 40 * xs, atol=3)
    co, r2 = dg.fit_poly(*dg._clean_xy(vals), 1)
    assert np.allclose(co, [40, 100], atol=[0.3, 2]) and r2 > 0.999


def dashed_diagram(dot=False):
    """Gitter, Beschriftung, eine durchgezogene Kurve und eine gestrichelte (dot: strichpunktierte), die sie kreuzt."""
    img = draw_diagram(curves=[CURVES[0]])
    draw_dashed(img, DASHED, 0.3, 9.7, dot=dot)
    return img


DASHED = lambda s: 380 - 30 * s + s ** 2                        # noqa: E731 - faellt, kreuzt 40 s bei s = 5,7


@pytest.mark.parametrize("dot", [False, True])
def test_trace_dashed_curve(dot):
    img = dashed_diagram(dot)
    clean, lines = dg.clean_ink(img)                            # Textgroesse wie vorgeschlagen (28 px > Strich 14 px)
    ink = dg.binarize(img)
    assert clean[290:305, 298:315].sum() == 0 and ink[290:305, 298:315].sum() > 0    # Text trotzdem weg
    assert clean[620:660, 20:75].sum() == 0                                         # Zahlen an der y-Achse weg
    old, _ = dg.clean_ink(img, dashes=False)
    assert (clean > 0).sum() > (old > 0).sum() + 800                                 # Striche bleiben erhalten
    c = calib()
    for s0 in (1.5, 3.0, 8.0):                                  # ueber Luecken und die Kreuzung hinweg
        pts = dg.trace_curve(clean, px(s0, DASHED(s0)), lines)
        v = dg.to_values(pts, c)
        assert v[:, 0].min() <= 0.4 and v[:, 0].max() >= 9.4, (s0, v[:, 0].min(), v[:, 0].max())
        err = np.abs(v[:, 1] - DASHED(v[:, 0]))
        assert np.percentile(err, 98) < 2.0 and err.max() < 4.0, (s0, np.percentile(err, 98), err.max())
    # die durchgezogene Kurve wird an der Kreuzung nicht auf die gestrichelte abgelenkt
    v = dg.to_values(dg.trace_curve(clean, px(2.0, 80), lines), c)
    assert v[:, 0].max() >= 9.9 and np.percentile(np.abs(v[:, 1] - 40 * v[:, 0]), 98) < 2.0


# ------------------------------------------------------------------------------------------- Dialog

@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path_factory.mktemp("settings")))
    return QApplication.instance() or QApplication([])


def _key(w, key):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    QTest.keyClick(w, getattr(Qt.Key, key))


def _pixel(d, x, y):
    """Grauwert der Anzeige am Diagrammpunkt (x, y) (auch bei schaerferem Anzeigebild)."""
    img = d.pix_item.pixmap().toImage()
    sc, pos = d.pix_item.scale(), d.pix_item.pos()
    return img.pixelColor(int((x + 0.5 - pos.x()) / sc), int((y + 0.5 - pos.y()) / sc)).value()


def test_dialog_workflow(qapp, tmp_path):
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QApplication
    import ui_digitize as ud
    img = cv2.cvtColor(draw_diagram(), cv2.COLOR_GRAY2BGR)
    out = tmp_path / "kurven.csv"
    d = ud.DigitizeDialog(None, img, save_dialog=lambda *a: str(out))
    d.show()
    qapp.processEvents()
    assert d.axes["x_axis"] is not None                         # wartet auf die Analyse im Hintergrund
    # Kalibrieren per Klick (eingerastet) und Werte; Eingabetaste im Wertfeld loest keinen Knopf aus
    d.start_calib()
    for key, p, v in (("x1", (X0 + 3, Y0 + 20), "0"), ("x2", (X1 - 4, Y0 + 15), "10"),
                      ("y1", (X0 - 20, Y0 - 2), "0"), ("y2", (X0 - 25, Y1 + 3), "500")):
        assert d.calib_step == key
        d.click(p)
        d.ed_val[key].setText(v)
        _key(d.ed_val[key], "Key_Return")
        assert d.mode == "calib" and not d.curves
    assert d.calib_step is None and not any(b.isChecked() for b in d.btn_calib.values())
    assert d.calib_pts["y2"] == (X0, Y1 + 0.5) and d.lbl_px["y2"].text() == f"{X0}, {Y1} px"
    # Markierungen zoomfest am Punkt; x-Beschriftung unten rechts, y oben links (x1/y1 im Ursprung beide lesbar)
    marks = {it.toolTip().split(":")[0]: it for it in d._items if it.toolTip()}
    assert set(marks) == {"x1", "x2", "y1", "y2"}
    assert marks["y2"].pos() == QPointF(X0 + 0.5, Y1 + 1.0)
    assert marks["y2"].flags() & marks["y2"].GraphicsItemFlag.ItemIgnoresTransformations
    lx, ly = marks["x1"].childItems()[0].pos(), marks["y1"].childItems()[0].pos()
    assert lx.x() > 0 and lx.y() > 0 and ly.x() < 0 and ly.y() < 0
    d.ed_xname.setText("Weg s [mm]")
    d.ed_yname.setText("Kraft F [N]")
    assert d.calib() is not None
    assert np.allclose(d.calib().to_values([(X0, Y0)]), [(0, 0)], atol=0.05)
    # drei Kurven verfolgen
    d.set_mode("trace")
    for k, ((f, a, b), s) in enumerate(zip(CURVES, [3.0, 4.5, 4.5])):
        d.new_curve()
        d.click(px(s, f(s)))
        assert len(d.curves[k]["pts"]) > 500
    assert d.list_curves.count() == 3
    d.list_curves.item(0).setText("Feder 1")
    # Punkt setzen und radieren
    d.list_curves.setCurrentRow(2)
    n = len(d.curves[2]["pts"])
    d.set_mode("erase")
    d.click(px(5, CURVES[2][0](5)))
    assert len(d.curves[2]["pts"]) < n
    d.undo()
    assert len(d.curves[2]["pts"]) == n
    d.set_mode("add")
    d.click(px(9.5, 340))
    assert len(d.curves[2]["pts"]) == n + 1
    d.undo()
    # Tabelle und Funktionen
    d.update_result()                                           # schlaegt Schrittweite 0,5 vor
    assert d.sp_step.value() == 0.5
    d.rb_step.setChecked(True)
    d.sp_step.setValue(1.0)
    d.sp_deg.setValue(2)
    d.update_result()
    txt = d.table_text(sep=";", decimal=",")
    lines = txt.splitlines()
    assert lines[0] == "Weg s [mm];Feder 1;Kurve 2;Kurve 3"
    assert len(lines) == 12
    row5 = lines[6].split(";")
    assert row5[0] == "5" and abs(float(row5[1].replace(",", ".")) - 200) < 4
    assert lines[1].split(";")[3] == ""                         # Kurve 3 beginnt erst bei 1
    d.copy_table()
    assert QApplication.clipboard().text().splitlines()[0].split("\t")[0] == "Weg s [mm]"
    d.copy_functions()
    ft = QApplication.clipboard().text()
    assert "Feder 1" in ft and "R²" in ft
    d.save_csv()
    assert out.read_text(encoding="utf-8-sig").splitlines()[0].startswith("Weg s [mm];")
    # Gitter ausblenden: Gitterlinie weiss, Achse und Kurven bleiben (auch an Kreuzungen mit dem Gitter)
    xg = int(round(X0 + 3 * (X1 - X0) / 10))
    assert _pixel(d, xg, 100) < 128
    d.chk_grid.setChecked(True)
    assert _pixel(d, xg, 100) > 200 and _pixel(d, (X0 + X1) // 2, Y0) < 128 and _pixel(d, X0, 300) < 128
    cx, cy = px(3.0, 120)
    assert min(_pixel(d, xg, int(cy) + k) for k in (-1, 0, 1)) < 128             # Kurve kreuzt die Gitterlinie
    d.chk_clean.setChecked(True)                                # bereinigt und ohne Gitter
    assert _pixel(d, xg, 100) == 255
    d.chk_clean.setChecked(False)
    d.chk_grid.setChecked(False)
    assert _pixel(d, xg, 100) < 128
    qapp.processEvents()
    d.close()


def drag(vp, button, a, b):
    """Mit gedrueckter Taste button im Viewport vp von a nach b ziehen."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    for t, at, held in ((QEvent.Type.MouseButtonPress, a, button), (QEvent.Type.MouseMove, b, button),
                        (QEvent.Type.MouseButtonRelease, b, Qt.MouseButton.NoButton)):
        QApplication.sendEvent(vp, QMouseEvent(t, at, vp.mapToGlobal(at), Qt.MouseButton.NoButton
                                               if t == QEvent.Type.MouseMove else button, held,
                                               Qt.KeyboardModifier.NoModifier))


def test_dialog_zoom_pan(qapp):
    """Zoomen um die Mausposition (Rad, Trackpad), Verschieben (rechte Taste, Leertaste + links), Einpassen."""
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    import ui_digitize as ud
    d = ud.DigitizeDialog(None, draw_diagram())
    d.show()
    qapp.processEvents()
    d.wait_jobs()
    v = d.view
    v.fit()
    s0 = v.scale_factor()
    assert abs(s0 - min(v.viewport().width() / 920 / 1.06, v.viewport().height() / 700 / 1.06)) < 0.01
    vp = v.viewport()

    def wheel(pos, angle=QPoint(0, 120), pixel=QPoint(), phase=Qt.ScrollPhase.NoScrollPhase):
        QApplication.sendEvent(vp, QWheelEvent(QPointF(pos), QPointF(vp.mapToGlobal(pos)), pixel, angle,
                                               Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, phase, False))
    pos = QPoint(120, 90)                                       # nicht die Mitte: Punkt unter der Maus bleibt stehen
    before = v.to_scene(QPointF(pos))
    wheel(pos)
    assert v.scale_factor() == pytest.approx(s0 * 1.25, rel=1e-6)
    after = v.to_scene(QPointF(pos))
    assert abs(after.x() - before.x()) < 1.5 / s0 and abs(after.y() - before.y()) < 1.5 / s0
    wheel(pos, angle=QPoint(0, 0), pixel=QPoint(0, 30), phase=Qt.ScrollPhase.ScrollUpdate)    # Trackpad: verschieben
    assert v.scale_factor() == pytest.approx(s0 * 1.25, rel=1e-6)
    assert v.to_scene(QPointF(pos)).y() == pytest.approx(after.y() - 30 / v.scale_factor(), abs=1.5 / s0)
    v.zoom_at(3.0, QPointF(pos))
    assert v.scale_factor() == pytest.approx(s0 * 3.75, rel=1e-6)
    # rechte Maustaste ziehen = verschieben, kein Werkzeug
    d.start_calib()
    p0 = v.to_scene(QPointF(200, 200))
    drag(vp, Qt.MouseButton.RightButton, QPointF(200, 200), QPointF(260, 230))
    p1 = v.to_scene(QPointF(260, 230))
    assert abs(p1.x() - p0.x()) < 1 and abs(p1.y() - p0.y()) < 1 and d.calib_pts["x1"] is None
    # Leertaste + linke Taste ziehen = verschieben
    v.setFocus()
    QTest.keyPress(v, Qt.Key.Key_Space)
    p0 = v.to_scene(QPointF(300, 300))
    drag(vp, Qt.MouseButton.LeftButton, QPointF(300, 300), QPointF(280, 250))
    p1 = v.to_scene(QPointF(280, 250))
    assert abs(p1.x() - p0.x()) < 1 and abs(p1.y() - p0.y()) < 1
    QTest.keyRelease(v, Qt.Key.Key_Space)
    assert d.calib_pts["x1"] is None and d.calib_step == "x1"
    v.fit()
    assert v.scale_factor() == pytest.approx(s0, rel=1e-3)
    d.close()


def test_dialog_auto_color_excel(qapp, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    import threading
    import ui_digitize as ud
    out = tmp_path / "kurven.xlsx"
    calls = []
    d = None

    def ocr(gray, ask, rots):                   # Texterkennung nachgestellt (Bild doppelt gross)
        calls.append((gray.shape, ask, tuple(rots), threading.current_thread() is threading.main_thread()))
        return [(it[0] * 2, it[1] * 2, it[2] * 2, it[3] * 2) + tuple(it[4:]) for it in label_items()]

    d = ud.DigitizeDialog(None, draw_color_diagram(), save_dialog=lambda *a: str(out), ocr=ocr, auto=False)
    d.wait_ready()
    assert d.btn_colors.isVisibleTo(d) and len(d.curves) == 0
    assert d.take_color_curves() == 3 and d.take_color_curves() == 0          # je Farbe nur einmal
    assert d.auto_calibrate(ask=True) is None                                 # liest im Hintergrund
    assert d.wait_ocr()
    assert calls == [((1400, 1840), True, (0,), False)]           # nur waagerecht, nicht im GUI-Thread
    assert d.ed_val["x2"].text() == "10" and d.ed_val["y2"].text() == "500"
    assert d.mode == "trace" and not d.pb_auto.isVisibleTo(d)
    for cv in d.curve_values():
        errs = [np.percentile(np.abs(cv[:, 1] - f(cv[:, 0])), 95) for f, a, b in CURVES]
        assert min(errs) < 2.5
    d.ed_xname.setText("Weg s [mm]")
    d.cb_values.setCurrentIndex(d.cb_values.findData("smooth"))
    d.update_result()
    assert d.sp_knots.isVisibleTo(d)
    assert "Spline" in d.functions_text()
    xs, tab, head = d.result()
    assert head[0] == "Weg s [mm]" and tab.shape == (21, 3)
    d.btn_xlsx.click()                                          # wie der Knopf (ohne Pfad: Dialog)
    ws = openpyxl.load_workbook(out)["Werte"]
    assert len(ws._charts) == 1 and ws["A1"].value == "Kurve" and ws["B1"].value == "a0"
    assert [ws.cell(6, c).value for c in range(1, 8)] == ["Weg s [mm]", "Kurve 1", "Kurve 2", "Kurve 3",
                                                          "Kurve 1 (Polynom)", "Kurve 2 (Polynom)",
                                                          "Kurve 3 (Polynom)"]
    f = [ws.cell(r, 5).value for r in range(7, 7 + len(xs))]
    assert all(isinstance(t, str) and t.startswith("=$B$2+$C$2*A") for t in f if t is not None) and f[10]
    co = d.polys()[0][0]
    assert _eval_formula(ws, f[10]) == pytest.approx(np.polyval(co, xs[10]))
    # Klick auf eine farbige Kurve verfolgt nur diese Farbe, die neue Kurve bekommt deren Farbe
    d.new_curve()
    d.set_mode("trace")
    d.click(px(4.5, CURVES[2][0](4.5)))
    v = d.curve_values()[-1]
    assert np.percentile(np.abs(v[:, 1] - CURVES[2][0](v[:, 0])), 95) < 2.0
    assert d.curves[-1]["color"] in {x["color"] for x in d.curves[:3]}
    # ohne Beschriftungen: keine Kalibrierung
    d2 = ud.DigitizeDialog(None, draw_diagram(), auto=False)
    assert not d2.auto_calibrate(items=[]) and d2.calib() is None
    d.close()
    d2.close()


def test_dialog_auto_on_open(qapp):
    """Beim Oeffnen: Analyse, farbige Kurven und Texterkennung laufen im Hintergrund; Ergebnis kommt von selbst."""
    import threading
    import time
    import ui_digitize as ud
    seen = []

    def ocr(gray, ask, rots):
        seen.append((ask, tuple(rots), threading.current_thread() is threading.main_thread()))
        ylab = [it[0] < X0 for it in label_items()]             # y-Zahlen waagerecht, x-Zahlen erst gedreht gelesen
        return [(it[0] * 2, it[1] * 2, it[2] * 2, it[3] * 2) + tuple(it[4:]) for it, y in zip(label_items(), ylab)
                if y == (tuple(rots) == (0,))]

    big = cv2.resize(draw_color_diagram(), None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    t = time.perf_counter()
    d = ud.DigitizeDialog(None, draw_color_diagram(), ocr=ocr)
    d.show()
    qapp.processEvents()
    t = time.perf_counter() - t
    t2 = time.perf_counter()
    while (d.calib() is None or not d.curves) and time.perf_counter() - t2 < 20:   # von selbst, ohne Warten
        qapp.processEvents()
        time.sleep(0.005)
    assert len(d.curves) == 3 and d.calib() is not None and seen == [(False, (0,), False), (False, (1, 3), False)]
    assert not d.pb_busy.isVisibleTo(d)
    # von Hand gesetzte Punkte ueberschreibt die Texterkennung beim Oeffnen nicht
    d3 = ud.DigitizeDialog(None, big, ocr=lambda g, a, r: label_items())
    d3.start_calib()
    d3.click((2 * X0 + 5, 2 * Y0 + 10))
    d3.wait_jobs()
    d3.wait_ocr()
    assert d3.calib_pts["x2"] is None and d3.ed_val["x1"].text() == ""
    assert t < 1.0, t
    d.close()
    d3.close()


def test_dialog_reversed_axes(qapp, tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    import ui_digitize as ud
    d = ud.DigitizeDialog(None, draw_diagram(), auto=False)
    d.start_calib()
    for key, p, v in (("x1", (X0, Y0), "7"), ("x2", (X1, Y0), "5"), ("y1", (X0, Y0), "500"), ("y2", (X0, Y1), "0")):
        d.click(p)
        d.ed_val[key].setText(v)
    d.set_mode("trace")
    d.new_curve()
    d.click(px(3.0, CURVES[0][0](3.0)))                         # F = 40 s; x' = 7 - 0,2 s, y' = 500 - F
    d.rb_step.setChecked(True)
    d.sp_step.setValue(0.5)
    d.sp_deg.setValue(1)
    d.update_result()
    xs, tab, head = d.result()
    assert list(xs) == [5.0, 5.5, 6.0, 6.5, 7.0]                # aufsteigend sortiert
    true = 500 - 40 * (7 - xs) / 0.2
    assert np.allclose(tab[:, 0], true, atol=3)
    co, r2, lo, hi = d.polys()[0]
    assert np.allclose(co, [200, 500 - 1400], atol=[2, 12]) and lo < 5.05 and hi > 6.95
    assert "200" in d.functions_text().replace(",", ".")
    path = tmp_path / "rev.xlsx"
    d.save_xlsx(str(path))
    ch = openpyxl.load_workbook(path)["Werte"]._charts[0]
    assert ch.x_axis.scaling.orientation == "maxMin" and ch.y_axis.scaling.orientation == "maxMin"
    d.close()


def test_import_is_lean():
    """ui_digitize wird beim Programmstart geladen: dabei nichts Schweres (Excel, PDF, Texterkennung) importieren."""
    import subprocess
    import sys
    code = ("import sys; sys.path.insert(0, %r); import ui_digitize; "
            "print([m for m in ('openpyxl', 'pymupdf', 'rapidocr_onnxruntime', 'diffreport', 'onnxruntime') "
            "if m in sys.modules])" % os.path.join(os.path.dirname(__file__), "..", "programm"))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60,
                         env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    assert out.stdout.strip().splitlines()[-1] == "[]", out.stdout + out.stderr


def test_mainwindow_area_diagram(qapp, tmp_path, monkeypatch):
    """Im Hauptfenster: ohne Auswahl nur Hinweis, mit Bereich oeffnet sich der Dialog."""
    import time
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QMessageBox
    from test_gui import cleanup_windows
    import drawing_viewer as vw
    import ui_digitize as ud
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)

    assert issubclass(vw.MainWindow, ud.DigitizeMixin)         # im Hauptfenster eingehaengt
    w = vw.MainWindow()
    w.show()
    try:
        w.area_diagram()                                    # ohne Auswahl: nur Hinweis
        assert getattr(w, "_digitize_dlg", None) is None
        p = tmp_path / "diagramm.png"
        cv2.imwrite(str(p), draw_diagram())
        w._set_file("A", str(p))
        t = time.time()
        while (w.payload is None or w.running) and time.time() - t < 60:
            qapp.processEvents()
            time.sleep(0.01)
        w.start_area()
        w.canvas.sel_rects = [(0, 0, 920, 700)]
        w._area_changed()
        d = w.area_diagram()
        assert d is not None and d.isVisible() and d.axes["x_axis"] is not None
        assert d.img.shape[:2] == (700, 920)
        d.close()
    finally:
        cleanup_windows(qapp)


def test_mainwindow_pdf_sharp(qapp, tmp_path, monkeypatch):
    """PDF-Quelle: der Dialog zeigt den Ausschnitt hoeher aufgeloest (im Hintergrund gerendert), deckungsgleich mit
    dem Diagrammbild, in dem gerechnet wird."""
    import time
    pymupdf = pytest.importorskip("pymupdf")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QMessageBox
    from test_gui import cleanup_windows
    import drawing_viewer as vw
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings"))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    doc = pymupdf.open()
    pg = doc.new_page(width=420, height=300)
    for k in range(11):
        pg.draw_line((60 + 30 * k, 30), (60 + 30 * k, 250), width=0.4)
    for k in range(6):
        pg.draw_line((60, 250 - 44 * k), (360, 250 - 44 * k), width=0.4)
    pg.draw_polyline([(60 + 3 * i, 250 - 2.0 * i) for i in range(101)], color=(0.9, 0.1, 0.1), width=1.0)
    path = tmp_path / "d.pdf"
    doc.save(str(path))
    w = vw.MainWindow()
    w.show()
    try:
        w._set_file("A", str(path))
        t = time.time()
        while (w.payload is None or w.running) and time.time() - t < 60:
            qapp.processEvents()
            time.sleep(0.01)
        c = w.canvas
        assert c.vector_src is not None
        w.start_area()
        h, wd = c.shape
        c.sel_rects = [(int(wd * 0.1), int(h * 0.05), int(wd * 0.9), int(h * 0.9))]
        w._area_changed()
        d = w.area_diagram()
        d.wait_jobs()
        hi, sx, sy, sc = d._hi
        H, W = d.img.shape[:2]
        assert sc <= 0.5 and hi.shape[1] * sc == pytest.approx(W, abs=1) and hi.shape[0] * sc == pytest.approx(H, abs=1)
        assert d.pix_item.scale() == sc and d.pix_item.pixmap().width() == hi.shape[1]
        m = np.float32([[1 / sc, 0, -sx / sc], [0, 1 / sc, -sy / sc]])
        back = cv2.warpAffine(hi, m, (W, H), flags=cv2.INTER_AREA | cv2.WARP_INVERSE_MAP, borderValue=(255,) * 3)
        g1, g2 = (cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(float) for a in (d.img, back))
        assert np.abs(g1 - g2).mean() < 8                     # deckungsgleich (sonst Doppellinien)
        p1, p2 = ((255 - g[H // 3:H // 2]).sum(axis=0) for g in (g1, g2))
        first = [int(np.flatnonzero(p > 0.5 * p.max())[0]) for p in (p1, p2)]         # erste senkrechte Linie
        assert abs(first[0] - first[1]) <= 1
        d.chk_grid.setChecked(True)                           # Gitter ausblenden auch im scharfen Bild
        assert d.pix_item.pixmap().width() == hi.shape[1]
        d.close()
    finally:
        cleanup_windows(qapp)
