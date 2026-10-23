"""Rechenkern: bekannte Aenderungen muessen gefunden werden, Ergebnis darf sich nicht unbemerkt aendern."""
import hashlib
import json
import os

import numpy as np
import pytest

import diffcore as dc
import diffpipe as dp
import diffreport as rep
from conftest import EXAMPLES

GOLDEN = os.path.join(os.path.dirname(__file__), "golden.json")


def run(pa, pb, **kw):
    p = dp.Params(**kw)
    a = dp.ink_from_gray(dp.load_gray(pa), p.thr)
    b = dp.ink_from_gray(dp.load_gray(pb), p.thr)
    b = dp.prepare_pair(a, b, p.align, lambda *_: None)
    return dp.run_compare(a, b, p, lambda *_: None)


def digest(res):
    h = hashlib.sha1()
    for m in (res.oa, res.ob, res.both, res.moved):
        h.update(np.packbits(m).tobytes())
    return h.hexdigest()


def test_known_changes(pair):
    res = run(*pair)
    assert res.oa[195:206, 1000:1450].any(axis=0).mean() > 0.9   # entfernte Linie = nur in A
    assert res.ob[620:780, 1170:1330].any()                # neuer Kreis = nur in B
    assert not res.ob[620:780, 1170:1330][res.oa[620:780, 1170:1330]].any()
    regs = rep.find_regions(res)
    kinds = {r["typ"] for r in regs}
    assert "entfernt" in kinds and "neu" in kinds
    # verschobener Text gilt nicht als Aenderung (gruen)
    txt = (slice(380, 450), slice(990, 1240))
    assert res.moved[txt].sum() > 0.5 * (res.oa[txt].sum() + res.ob[txt].sum() + res.moved[txt].sum())


def test_identical_has_no_diff(pair):
    res = run(pair[0], pair[0])
    assert not res.oa.any() and not res.ob.any()


def check_golden(key, d):
    """Ergebnis-Fingerabdruck; nach gewollter Aenderung des Verfahrens mit UPDATE_GOLDEN=1 neu schreiben."""
    gold = json.load(open(GOLDEN)) if os.path.isfile(GOLDEN) else {}
    if os.environ.get("UPDATE_GOLDEN") or key not in gold:
        gold[key] = d
        json.dump(gold, open(GOLDEN, "w"), indent=1)
    assert d == gold[key], key


# "v1": Neuerungen aus -> muss exakt wie Version 1 rechnen. "standard": aktuelle Standardeinstellungen.
MODES = {"v1": dict(edge_noise=False, glyphs=False), "standard": {}}


@pytest.mark.parametrize("mode", list(MODES))
def test_golden_synthetic(pair, mode):
    check_golden("synthetic" + ("" if mode == "v1" else "+" + mode), digest(run(*pair, **MODES[mode])))


@pytest.mark.skipif(not os.path.isfile(os.path.join(EXAMPLES, "alt1.tif")), reason="Ordner Beispiele fehlt")
@pytest.mark.parametrize("na,nb", [("alt.tif", "neu.tif"), ("alt1.tif", "neu1.tif")])
@pytest.mark.parametrize("mode", list(MODES))
def test_golden_examples(na, nb, mode):
    d = digest(run(os.path.join(EXAMPLES, na), os.path.join(EXAMPLES, nb), **MODES[mode]))
    check_golden(na + ("" if mode == "v1" else "+" + mode), d)


def test_bench_quality():
    """Messstand (kuenstliche Zeichnungen mit bekannten Aenderungen): Mindestqualitaet halten."""
    import bench
    rows = bench.run_all(seeds=(1,))
    found = sum(r["gefunden"] for _, _, r in rows)
    false = sum(r["fehlalarm"] for _, _, r in rows)
    assert found >= 24 and false <= 8, bench.summary(rows)


def test_edge_noise_keeps_real_changes(pair):
    res = run(*pair, edge_noise=True)
    assert res.oa[195:206, 1000:1450].any(axis=0).mean() > 0.9      # entfernte Linie bleibt erkannt
    assert res.ob[620:780, 1170:1330].sum() > 200                     # neuer Kreis bleibt erkannt


def test_font_has_requested_size():
    assert dc._font(44).size == 44


def test_output_formats(pair, tmp_path):
    res = run(*pair)
    img = dp.render_result(res)
    for fmt in dc.OUT_FORMATS:
        p, f = dc.save_output(img, str(tmp_path / f"o.{fmt}"), fmt)
        assert os.path.getsize(p) > 1000


def test_missing_file_raises_differror():
    with pytest.raises(dc.DiffError):
        dp.load_gray("/gibt/es/nicht.png")


def test_cancel_and_progress(pair):
    p = dp.Params()
    a = dp.ink_from_gray(dp.load_gray(pair[0]), p.thr)
    b = dp.prepare_pair(a, dp.ink_from_gray(dp.load_gray(pair[1]), p.thr), p.align, lambda *_: None)
    seen = []
    dp.run_compare(a, b, p, lambda *_: None, progress=lambda f, t: seen.append(f))
    assert seen and seen[-1] == pytest.approx(1.0) and all(x <= y + 1e-9 for x, y in zip(seen, seen[1:]))
    with pytest.raises(dc.Cancelled):
        dp.run_compare(a, b, p, lambda *_: None, cancel=lambda: True)


def test_suggest_params(pair):
    ga, gb = dp.load_gray(pair[0]), dp.load_gray(pair[1])
    p, why = dp.suggest_params(ga, gb, 200, log=lambda *_: None)
    assert 1 <= p.tol <= 4 and 90 <= p.thr <= 210 and len(why) >= 3
    p4, _ = dp.suggest_params(ga, gb, 400, log=lambda *_: None)
    assert p4.cell > p.cell and p4.obj_shift > p.obj_shift


@pytest.mark.skipif(not rep.ocr_available(), reason="Texterkennung nicht installiert")
def test_ocr_title_block():
    import cv2
    img = np.full((260, 900), 255, np.uint8)
    cv2.putText(img, "Massstab 1:5", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 0, 2)
    cv2.putText(img, "Zeichnungsnummer 4711-0815", (20, 170), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 0, 2)
    info = rep.parse_title_block([(o[0], o[1], o[-1]) for o in rep.ocr_image(img)])
    assert info["scale_n"] == 5.0 and info["number"] == "4711-0815"


@pytest.mark.skipif(not rep.ocr_available(), reason="Texterkennung nicht installiert")
def test_ocr_german_umlauts():
    from PIL import Image, ImageDraw
    img = Image.new("L", (900, 90), 255)
    ImageDraw.Draw(img).text((15, 20), "Oberfläche Größe Übermaß ±0,1", font=dc._font(40), fill=0)
    txt = " ".join(o[-1] for o in rep.ocr_image(np.array(img)))
    assert "Oberfläche" in txt and "Größe" in txt and "Übermaß" in txt and "±0,1" in txt


def test_map_points_matches_image_transform(pair):
    """Punkte muessen genau so ausgerichtet werden wie das Bild (fuer Suchtreffer in B)."""
    import cv2
    a = dp.ink_from_gray(dp.load_gray(pair[0]), 128)
    g = dp.load_gray(pair[1])
    M0 = cv2.getRotationMatrix2D((800, 550), 0.6, 0.97)
    g2 = cv2.warpAffine(g, M0, (g.shape[1], g.shape[0]), borderValue=255)
    b, tf = dp.prepare_pair_tf(a, dp.ink_from_gray(g2, 128), "affine", lambda *_: None)
    pts = np.array([[1250, 700], [500, 520], [1000, 200]], float)       # Kreis neu, Kreis, Linie in B (ungedreht)
    raw = cv2.transform(pts[None], M0)[0]                                # dieselben Punkte im gedrehten B
    back = dp.map_points_tf(raw, tf)
    assert np.abs(back - pts).max() < 3.0
