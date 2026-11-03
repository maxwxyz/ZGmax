"""Feste Tests mit echten (anonymisierten) Zeichnungen aus tests/real/<fall>/ - siehe tests/real/README.md.
Ohne Faelle werden sie uebersprungen."""
import glob
import json
import os
import time

import pytest

import diffpipe as dp
import diffreport as rep

REAL = os.path.join(os.path.dirname(__file__), "real")


def _cases():
    out = []
    for d in sorted(glob.glob(os.path.join(REAL, "*"))):
        if not os.path.isdir(d):
            continue
        a = [f for f in glob.glob(os.path.join(d, "a.*")) if not f.endswith(".json")]
        b = [f for f in glob.glob(os.path.join(d, "b.*")) if not f.endswith(".json")]
        if a and b:
            out.append(pytest.param(d, a[0], b[0], id=os.path.basename(d)))
    return out


CASES = _cases()


def _hits(regs, box):
    x, y, w, h = box
    return [r for r in regs if r["x"] < x + w and r["x"] + r["w"] > x and r["y"] < y + h and r["y"] + r["h"] > y]


@pytest.mark.skipif(not CASES, reason="keine echten Zeichnungen in tests/real/")
@pytest.mark.parametrize("case,pa,pb", CASES or [pytest.param(None, None, None, id="keine")])
def test_real_drawing(case, pa, pb):
    spec = {}
    if os.path.isfile(os.path.join(case, "fall.json")):
        with open(os.path.join(case, "fall.json"), encoding="utf-8") as f:
            spec = json.load(f)
    dpi = int(spec.get("dpi", 200))
    p = dp.Params()
    t0 = time.time()
    a = dp.ink_from_gray(dp.load_gray(pa, int(spec.get("page_a", 1)), dpi), p.thr)
    b = dp.ink_from_gray(dp.load_gray(pb, int(spec.get("page_b", 1)), dpi), p.thr)
    b = dp.prepare_pair(a, b, p.align, lambda *_: None)
    res = dp.run_compare(a, b, p, lambda *_: None)
    regs = rep.find_regions(res)
    secs = time.time() - t0
    real = [r for r in regs if r["typ"] != "verschoben"]
    if "max_sekunden" in spec:
        assert secs <= spec["max_sekunden"], f"{secs:.0f} s"
    if "aenderungen" in spec:
        lo, hi = spec["aenderungen"].get("min", 0), spec["aenderungen"].get("max", 10 ** 9)
        assert lo <= len(real) <= hi, f"{len(real)} Änderungen, erwartet {lo}–{hi}"
    for box in spec.get("bereiche", []):
        assert _hits(real, box), f"keine Änderung in {box}"
    for box in spec.get("ohne_aenderung", []):
        assert not _hits(real, box), f"Fehlalarm in {box}: {[(r['nr'], r['typ']) for r in _hits(real, box)]}"
    if spec.get("masse"):
        if pa.lower().endswith(".pdf") and pb.lower().endswith(".pdf"):
            import diffvector as dv
            dv.fill_text(regs, dv.pdf_words(pa, int(spec.get("page_a", 1))),
                         dv.pdf_words(pb, int(spec.get("page_b", 1))), dpi, lambda *_: None)
        elif rep.ocr_available():
            rep.text_diff(res, regs, lambda *_: None)
        else:
            pytest.skip("Texterkennung nicht installiert")
        rep.dim_changes(regs, lambda *_: None)
        found = " | ".join(r.get("dim", "") for r in regs)
        norm = lambda s: s.replace(",", ".").replace(" ", "")   # noqa: E731
        for old, new in spec["masse"]:
            assert norm(old) in norm(found) and norm(new) in norm(found), f"{old} → {new} nicht in: {found}"
