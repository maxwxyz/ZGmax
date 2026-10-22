"""Messstand fuer die Vergleichsqualitaet.

Erzeugt kuenstliche, aber realistische Zeichnungspaare mit BEKANNTEN Aenderungen und typischen Stoerungen
(Drehung, Skalierung, oertlicher Verzug, Strichstaerke, Rauschen, Grauschleier, verschobene Textbloecke)
und misst:
  gefunden   = Anteil der echten Aenderungen, die in der Aenderungsliste stehen (Trefferquote)
  fehlalarm  = Eintraege der Liste, die keine echte Aenderung ueberdecken (sollten 0 sein)
Aufruf:  python tests/bench.py            (alle Szenarien, Standardeinstellungen)
         python tests/bench.py --compare  (mehrere Einstellungen nebeneinander)
"""
import os
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "programm"))
import diffpipe as dp  # noqa: E402
import diffreport as rep  # noqa: E402

W, H = 3300, 2300                      # etwa A3 quer bei 200 dpi
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _text(img, s, x, y, scale=0.9, th=2):
    cv2.putText(img, s, (x, y), FONT, scale, 0, th, cv2.LINE_AA)


def base_drawing(rng):
    """Zeichnung mit Rahmen, Schriftfeld, Ansichten, Bemassung, Schraffur und Text. Gibt (Bild, Objekte)."""
    img = np.full((H, W), 255, np.uint8)
    cv2.rectangle(img, (60, 60), (W - 60, H - 60), 0, 4)
    cv2.rectangle(img, (W - 1100, H - 360), (W - 60, H - 60), 0, 3)               # Schriftfeld
    for k in range(1, 5):
        cv2.line(img, (W - 1100, H - 360 + 60 * k), (W - 60, H - 360 + 60 * k), 0, 1)
    _text(img, "Massstab 1:2   Zeichnungsnummer 4711-0815   Index C", W - 1080, H - 320, 0.8, 2)
    objs = []
    for v in range(6):                                                            # Ansichten
        cx, cy = 400 + (v % 3) * 900, 450 + (v // 3) * 900
        r = int(rng.integers(120, 220))
        cv2.circle(img, (cx, cy), r, 0, 3)
        cv2.circle(img, (cx, cy), r // 3, 0, 2)
        cv2.rectangle(img, (cx - r - 60, cy - 30), (cx + r + 60, cy + 30), 0, 2)
        cv2.line(img, (cx - r - 120, cy), (cx + r + 120, cy), 0, 1, cv2.LINE_AA)  # Mittellinie
        for k in range(14):                                                       # Schraffur
            x = cx - r + 10 + k * 12
            cv2.line(img, (x, cy + r // 2), (x + 40, cy + r // 2 + 40), 0, 1, cv2.LINE_AA)
        y = cy + r + 60                                                           # Bemassung
        cv2.line(img, (cx - r, y), (cx + r, y), 0, 1, cv2.LINE_AA)
        cv2.line(img, (cx - r, cy + r), (cx - r, y + 10), 0, 1)
        cv2.line(img, (cx + r, cy + r), (cx + r, y + 10), 0, 1)
        _text(img, f"{2 * r / 8:.1f}", cx - 30, y - 10, 0.8, 2)
        objs.append(dict(cx=cx, cy=cy, r=r, dim=(cx - 30, y - 10)))
    for i in range(8):                                                            # Hinweistexte
        _text(img, f"Hinweis {i + 1}: Kanten gebrochen 0,{i + 2} x 45", 120, H - 330 + 32 * i, 0.7, 2)
    return img, objs


def make_case(seed, scenario):
    """Gibt (A, B, echte_aenderungen [boxen], nur_verschoben [boxen]) zurueck; Bilder 255 = Papier."""
    rng = np.random.default_rng(seed)
    a, objs = base_drawing(rng)
    b = a.copy()
    gt, moved = [], []
    # --- echte Aenderungen (immer dieselben 5 Arten)
    o = objs[0]                                                    # Mass geaendert
    x, y = o["dim"]
    cv2.rectangle(b, (x - 5, y - 30), (x + 90, y + 8), 255, -1)
    _text(b, f"{o['r'] / 4 + 1.5:.1f}", x, y, 0.8, 2)
    gt.append((x - 5, y - 30, 100, 40))
    o = objs[1]                                                    # Bohrung hinzugefuegt
    cv2.circle(b, (o["cx"] + o["r"] // 2, o["cy"] - o["r"] // 2), 25, 0, 2)
    gt.append((o["cx"] + o["r"] // 2 - 30, o["cy"] - o["r"] // 2 - 30, 60, 60))
    o = objs[2]                                                    # Mittelkreis entfernt
    cv2.circle(b, (o["cx"], o["cy"]), o["r"] // 3, 255, 4)
    gt.append((o["cx"] - o["r"] // 3 - 5, o["cy"] - o["r"] // 3 - 5, 2 * (o["r"] // 3) + 10, 2 * (o["r"] // 3) + 10))
    o = objs[3]                                                    # Kontur verlaengert
    cv2.line(b, (o["cx"] + o["r"] + 60, o["cy"] - 30), (o["cx"] + o["r"] + 140, o["cy"] - 30), 0, 2)
    gt.append((o["cx"] + o["r"] + 55, o["cy"] - 40, 95, 20))
    cv2.rectangle(b, (W - 1080, H - 345), (W - 300, H - 300), 255, -1)    # Index im Schriftfeld
    _text(b, "Massstab 1:2   Zeichnungsnummer 4711-0815   Index D", W - 1080, H - 320, 0.8, 2)
    gt.append((W - 300 - 150, H - 345, 160, 45))
    # --- nur verschoben (keine Aenderung): Hinweistext 6 um 25 px nach rechts
    y6 = H - 330 + 32 * 5
    blk = a[y6 - 25:y6 + 8, 110:900].copy()
    b[y6 - 25:y6 + 8, 110:900] = 255
    b[y6 - 25:y6 + 8, 135:925] = np.minimum(b[y6 - 25:y6 + 8, 135:925], blk)
    moved.append((110, y6 - 25, 815, 33))
    # --- Stoerungen je Szenario
    if scenario == "fleckig":                                       # Schatten und vergilbtes Papier (nur B)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        shade = 1.0 - 0.45 * np.clip((xx / W) * (yy / H) * 1.6, 0, 1)        # dunkle Ecke unten rechts
        b = np.clip(b.astype(np.float32) * shade * 0.92, 0, 255).astype(np.uint8)
    if scenario in ("scan", "verzug", "strich", "alles"):
        if scenario in ("scan", "alles"):                          # leicht gedreht/skaliert/verschoben gescannt
            M = cv2.getRotationMatrix2D((W / 2, H / 2), 0.25, 0.998)
            M[:, 2] += (7, -4)
            b = cv2.warpAffine(b, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=255)
        if scenario in ("verzug", "alles"):                        # oertlicher Verzug bis ~2 px
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            dx = 2.0 * np.sin(xx / 400.0) * np.cos(yy / 350.0)
            dy = 1.6 * np.cos(xx / 300.0)
            b = cv2.remap(b, xx + dx, yy + dy, cv2.INTER_LINEAR, borderValue=255)
        if scenario in ("strich", "alles"):                        # Strich 1 px dicker (anderer Drucker/Scanner)
            b = cv2.erode(b, np.ones((2, 2), np.uint8))
        if scenario in ("scan", "alles"):                          # Grauschleier, Rauschen, Staub
            b = np.clip(b.astype(np.int16) - 25 + rng.normal(0, 10, b.shape), 0, 255).astype(np.uint8)
            for _ in range(60):
                cv2.circle(b, (int(rng.integers(100, W - 100)), int(rng.integers(100, H - 100))),
                           int(rng.integers(1, 3)), 0, -1)
    return a, b, gt, moved


def _overlap(r, box, pad=8):
    x, y, w, h = box
    return not (r["x"] + r["w"] < x - pad or r["x"] > x + w + pad or r["y"] + r["h"] < y - pad or r["y"] > y + h + pad)


def evaluate(a_gray, b_gray, gt, moved, params=None, log=lambda *_: None):
    p = params or dp.Params()
    t = time.time()
    a = dp.ink_from_gray(a_gray, p.thr, p.flatten)
    bi = dp.ink_from_gray(b_gray, p.thr, p.flatten)
    b = dp.prepare_pair(a, bi, p.align, log)
    res = dp.run_compare(a, b, p, log)
    regs = [r for r in rep.find_regions(res) if r["typ"] != "verschoben"]
    found = sum(1 for g in gt if any(_overlap(r, g) for r in regs))
    false = [r for r in regs if not any(_overlap(r, g) for g in gt)]
    return dict(gefunden=found, echt=len(gt), fehlalarm=len(false), eintraege=len(regs),
                im_verschobenen=sum(1 for r in false if any(_overlap(r, m) for m in moved)), zeit=time.time() - t)


SCENARIOS = ("sauber", "scan", "verzug", "strich", "fleckig", "alles")


def run_all(params=None, seeds=(1, 2)):
    rows = []
    for sc in SCENARIOS:
        for s in seeds:
            a, b, gt, mv = make_case(s, sc)
            r = evaluate(a, b, gt, mv, params)
            rows.append((sc, s, r))
    return rows


def summary(rows):
    f = sum(r["gefunden"] for _, _, r in rows)
    e = sum(r["echt"] for _, _, r in rows)
    fa = sum(r["fehlalarm"] for _, _, r in rows)
    return f"gefunden {f}/{e}  Fehlalarme {fa}"


if __name__ == "__main__":
    variants = {"Standard": dp.Params()}
    if "--compare" in sys.argv:
        variants = {"Version 1": dp.Params(edge_noise=False, glyphs=False), "Standard": dp.Params(),
                    "Standard + Papierausgleich": dp.Params(flatten=True)}
        for k, v in getattr(dp, "BENCH_VARIANTS", {}).items():
            variants[k] = v
    for name, p in variants.items():
        rows = run_all(p)
        print(f"== {name}: {summary(rows)}")
        for sc, s, r in rows:
            print(f"   {sc:7s} #{s}: gefunden {r['gefunden']}/{r['echt']}  Fehlalarme {r['fehlalarm']:3d} "
                  f"(davon im verschobenen Text {r['im_verschobenen']})  {r['zeit']:.1f}s")
