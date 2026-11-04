"""Vektorisieren: Kreise und Kreisboegen werden als echte Kreise/Boegen erkannt und geschrieben (DXF, SVG, PDF)."""
import math

import cv2
import numpy as np
import pytest

import diffedit as de

MM = 0.1                                               # mm je Pixel
H, W = 800, 1000
CIRCLES = [((150, 150), 20), ((400, 200), 60), ((750, 300), 150)]
ARCS = [((200, 550), 80, 0, 120), ((450, 620), 40, 200, 290)]   # Bildwinkel (y nach unten), Grad


def sheet():
    img = np.zeros((H, W), np.uint8)
    for (cx, cy), r in CIRCLES:
        cv2.circle(img, (cx, cy), r, 255, 2)
    for (cx, cy), r, a0, a1 in ARCS:
        cv2.ellipse(img, (cx, cy), (r, r), 0, a0, a1, 255, 3)
    cv2.rectangle(img, (600, 500), (900, 700), 255, 3)
    cv2.line(img, (50, 760), (500, 710), 255, 2)
    return img


def to_dxf(x, y):
    return x * MM, (H - y) * MM


@pytest.fixture(scope="module")
def vec():
    return de.vectorize(sheet(), "center", 1.0)


def test_fit_circle_exact():
    t = np.linspace(0.3, 1.4, 30)
    cx, cy, r = de.fit_circle(np.column_stack([12 + 40 * np.cos(t), -7 + 40 * np.sin(t)]))
    assert abs(cx - 12) < 1e-6 and abs(cy + 7) < 1e-6 and abs(r - 40) < 1e-6
    assert de.fit_circle([(0, 0), (1, 1), (2, 2)]) is None        # Gerade


def test_circles_and_arcs_found(vec):
    assert len(vec["circles"]) == len(CIRCLES)
    for (cx, cy), r in CIRCLES:
        assert any(math.hypot(c[0] - cx, c[1] - cy) < 1.5 and abs(c[2] - r) < 1.5 for c in vec["circles"])
    assert len(vec["arcs"]) == len(ARCS)
    for (cx, cy), r, a0, a1 in ARCS:
        a = next(a for a in vec["arcs"] if math.hypot(a[0] - cx, a[1] - cy) < 2)
        assert abs(a[2] - r) < 1.5
        assert abs((a[3] - a0 + 180) % 360 - 180) < 5 and abs((a[4] - a1 + 180) % 360 - 180) < 5


def test_dxf_circles_arcs_lines(vec, tmp_path):
    ezdxf = pytest.importorskip("ezdxf")
    out = str(tmp_path / "v.dxf")
    n = de.write_vectors(out, vec, (W, H), 254, MM)
    msp = ezdxf.readfile(out).modelspace()
    circ, arcs = list(msp.query("CIRCLE")), list(msp.query("ARC"))
    assert len(circ) == len(CIRCLES) and len(arcs) == len(ARCS)
    assert n == len(vec["lines"]) + len(circ) + len(arcs)
    for (cx, cy), r in CIRCLES:                       # Mittelpunkt und Radius in mm (Toleranz 0,15 mm)
        x, y = to_dxf(cx, cy)
        assert any(math.hypot(c.dxf.center.x - x, c.dxf.center.y - y) < 0.15 and abs(c.dxf.radius - r * MM) < 0.15
                   for c in circ)
    for (cx, cy), r, a0, a1 in ARCS:                 # y gespiegelt: Bildwinkel a -> DXF -a, gegen den Uhrzeigersinn
        x, y = to_dxf(cx, cy)
        a = next(a for a in arcs if math.hypot(a.dxf.center.x - x, a.dxf.center.y - y) < 0.2)
        assert abs(a.dxf.radius - r * MM) < 0.15
        assert abs((a.dxf.start_angle + a1 + 180) % 360 - 180) < 5
        assert abs((a.dxf.end_angle + a0 + 180) % 360 - 180) < 5
    polys = list(msp.query("LWPOLYLINE"))
    assert polys and len(polys) <= 4                  # Rechteck und Linie bleiben Linienzuege
    rect = [p for p in polys if p.closed or len(p) >= 5]
    assert rect
    pts = np.array([q[:2] for q in rect[0].get_points()])
    assert abs(pts[:, 0].min() - 600 * MM) < 0.2 and abs(pts[:, 0].max() - 900 * MM) < 0.2
    assert len(pts) <= 9                              # Ecken bleiben Ecken (keine Boegen)
    line = [p for p in polys if len(p) == 2]
    assert line


def test_svg_and_pdf_use_curves(vec, tmp_path):
    import pymupdf
    svg = str(tmp_path / "v.svg")
    de.write_vectors(svg, vec, (W, H), 254, MM)
    txt = open(svg, encoding="utf-8").read()
    assert txt.count("<circle") == len(CIRCLES) and txt.count(" A") >= len(ARCS)
    pdf = str(tmp_path / "v.pdf")
    de.write_vectors(pdf, vec, (W, H), 254, MM)
    with pymupdf.open(pdf) as d:
        items = [it for dr in d[0].get_drawings() for it in dr["items"]]
    assert sum(1 for it in items if it[0] == "c") >= 4 * len(CIRCLES)   # Kreise als Bezierkurven
    k = 72 / 254                                      # Bogen 0..120 Grad (Bild): Endpunkte richtig herum
    (cx, cy), r, a0, a1 = ARCS[0]
    ends = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))) for a in (a0, a1)]
    pts = [(p.x / k, p.y / k) for it in items if it[0] == "c" for p in (it[1], it[4])]
    for ex, ey in ends:
        assert min(math.hypot(px - ex, py - ey) for px, py in pts) < 3


def test_circle_crossed_by_center_lines():
    img = np.zeros((300, 300), np.uint8)
    cv2.circle(img, (150, 150), 50, 255, 2)
    cv2.line(img, (80, 150), (220, 150), 255, 1)
    cv2.line(img, (150, 80), (150, 220), 255, 1)
    v = de.vectorize(img, "center", 1.0)
    assert len(v["circles"]) == 1 and not v["arcs"]
    cx, cy, r = v["circles"][0]
    assert math.hypot(cx - 150, cy - 150) < 1 and abs(r - 50) < 1
    assert len(v["lines"]) >= 2


def test_slot_lines_and_arcs_connect():
    img = np.zeros((300, 400), np.uint8)               # Langloch: zwei Halbkreise, zwei Geraden
    cv2.ellipse(img, (100, 150), (40, 40), 0, 90, 270, 255, 2)
    cv2.ellipse(img, (300, 150), (40, 40), 0, -90, 90, 255, 2)
    cv2.line(img, (100, 110), (300, 110), 255, 2)
    cv2.line(img, (100, 190), (300, 190), 255, 2)
    v = de.vectorize(img, "center", 1.0)
    assert len(v["arcs"]) == 2 and not v["circles"]
    for a in v["arcs"]:
        assert abs(a[2] - 40) < 1.5 and abs((a[4] - a[3]) - 180) < 12
    ends = [de._arc_point(a[0], a[1], a[2], t) for a in v["arcs"] for t in a[3:5]]
    lend = [p for ln in v["lines"] for p in (ln[0], ln[-1])]
    for e in ends:                                    # Linien schliessen genau an die Boegen an
        assert min(math.hypot(e[0] - q[0], e[1] - q[1]) for q in lend) < 1e-6


def test_curves_off_and_outline_unchanged():
    img = sheet()
    v = de.vectorize(img, "center", 1.0, curves=False)
    assert not v["arcs"] and not v["circles"] and len(v["lines"]) > 5
    o = de.vectorize(img, "outline", 1.0)
    assert not o["arcs"] and not o["circles"] and o["fills"]
