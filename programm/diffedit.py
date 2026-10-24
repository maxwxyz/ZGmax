"""Zeichnung bearbeiten: Ausschnitt verschieben, Auswahl kopieren (auch nur Linien oder nur Geometrie), zuschneiden,
drehen, Helligkeit, Bildgroesse und Vektorisieren (Pixel -> Linien fuer SVG, PDF, DXF).

Alle Funktionen arbeiten auf Bild-Arrays (Graustufen HxW oder BGR HxWx3) und der Linienmaske (uint8, >0 = Linie)
derselben Groesse. Rechtecke sind (x0, y0, x1, y1) in Pixeln, x1/y1 exklusiv.
"""
import os

import cv2
import numpy as np


def clip_rect(rect, shape):
    h, w = shape[:2]
    x0, y0, x1, y1 = (int(round(v)) for v in rect)
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    return max(0, x0), max(0, y0), min(w, x1), min(h, y1)


def paper_color(img, ink, rect=None, ring=40):
    """Farbe des Papiers: Median der Nicht-Linien-Pixel um das Rechteck (sonst im ganzen Bild, ausgeduennt)."""
    h, w = img.shape[:2]
    if rect is not None:
        x0, y0, x1, y1 = clip_rect((rect[0] - ring, rect[1] - ring, rect[2] + ring, rect[3] + ring), img.shape)
    else:
        x0, y0, x1, y1 = 0, 0, w, h
    step = max(1, int(np.sqrt((x1 - x0) * (y1 - y0) / 250000)))
    part = img[y0:y1:step, x0:x1:step]
    free = ink[y0:y1:step, x0:x1:step] == 0
    px = part[free] if free.any() else part.reshape(-1, *part.shape[2:])
    if len(px) == 0:
        return 255 if img.ndim == 2 else (255, 255, 255)
    med = np.median(px, axis=0)
    return int(med) if img.ndim == 2 else tuple(int(v) for v in med)


def line_mask(ink_patch, grow=1):
    """Linienpixel eines Ausschnitts, etwas erweitert (Kantenglaettung der Linien mitnehmen)."""
    m = ink_patch > 0
    if grow > 0 and m.any():
        m = cv2.dilate(m.astype(np.uint8), np.ones((2 * grow + 1, 2 * grow + 1), np.uint8)) > 0
    return m


def region_mask(rects, bbox):
    """Vereinigung mehrerer Rechtecke als Maske im umgebenden Rechteck bbox."""
    x0, y0, x1, y1 = bbox
    m = np.zeros((y1 - y0, x1 - x0), bool)
    for a, b, c, d in rects:
        m[max(0, b - y0):max(0, d - y0), max(0, a - x0):max(0, c - x0)] = True
    return m


def bbox_of(rects):
    return min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects)


def fill_region(images, ink, rect, region=None, only_lines=False):
    """Bereich leeren: Linien (oder alles) im Rechteck/in der Maske bekommen die Papierfarbe."""
    x0, y0, x1, y1 = clip_rect(rect, ink.shape)
    if x1 <= x0 or y1 <= y0:
        return None
    mask = line_mask(ink[y0:y1, x0:x1], 2) if only_lines else np.ones((y1 - y0, x1 - x0), bool)
    if region is not None:
        mask &= region[:y1 - y0, :x1 - x0]
    for img in images:
        img[y0:y1, x0:x1][mask] = paper_color(img, ink, (x0, y0, x1, y1))
    return x0, y0, x1, y1


def move_region(images, ink, rect, dx, dy, only_lines=False, region=None):
    """Verschiebt den Ausschnitt rect um (dx, dy) in allen Bildern (gleiche Groesse, z. B. Grau und Farbe).
    only_lines: nur die Linien wandern, der Hintergrund am Ziel bleibt. Die frei gewordene Flaeche bekommt die
    Papierfarbe. Rueckgabe: veraendertes Rechteck (Vereinigung von Quelle und Ziel) oder None."""
    shape = ink.shape
    x0, y0, x1, y1 = clip_rect(rect, shape)
    dx, dy = int(round(dx)), int(round(dy))
    if x1 <= x0 or y1 <= y0 or (dx == 0 and dy == 0):
        return None
    tx0, ty0, tx1, ty1 = clip_rect((x0 + dx, y0 + dy, x1 + dx, y1 + dy), shape)
    if tx1 <= tx0 or ty1 <= ty0:                    # ganz aus dem Blatt geschoben: nur entfernen
        tx0 = ty0 = tx1 = ty1 = 0
    mask = line_mask(ink[y0:y1, x0:x1], 2) if only_lines else np.ones((y1 - y0, x1 - x0), bool)
    if region is not None:                          # mehrere Rechtecke: nur deren Inhalt
        mask &= region[:y1 - y0, :x1 - x0]
    for img in images:
        piece = img[y0:y1, x0:x1].copy()
        bg = paper_color(img, ink, (x0, y0, x1, y1))
        src = img[y0:y1, x0:x1]
        src[mask] = bg                               # Quelle leeren (nur Linien oder ganze Flaeche)
        if tx1 > tx0:
            sx0, sy0 = tx0 - (x0 + dx), ty0 - (y0 + dy)  # abgeschnittener Teil am Blattrand
            sub = piece[sy0:sy0 + ty1 - ty0, sx0:sx0 + tx1 - tx0]
            m = mask[sy0:sy0 + ty1 - ty0, sx0:sx0 + tx1 - tx0]
            dst = img[ty0:ty1, tx0:tx1]
            dst[m] = sub[m]
    if tx1 > tx0:
        return min(x0, tx0), min(y0, ty0), max(x1, tx1), max(y1, ty1)
    return x0, y0, x1, y1


def open_lines(ink, width):
    """Nur Linien, die mindestens width Pixel breit sind (runde Oeffnung: richtungsunabhaengig)."""
    k = max(1, int(width))
    if k <= 1:
        return ink > 0
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    return cv2.morphologyEx((ink > 0).astype(np.uint8), cv2.MORPH_OPEN, se) > 0


def suggest_geometry_width(ink, max_width=16, share=0.5):
    """Linienbreite (px), ab der eine Linie als Koerperkante gilt. Koerperkanten sind die dicksten Linien der
    Zeichnung (nach Norm etwa doppelt so breit wie Mass- und Hinweislinien, dicker als Schrift) und tragen meist den
    groessten Teil der Linienpixel. Gesucht wird die groesste Breite, die noch die Haelfte der Linienpixel haelt;
    die Grenze liegt knapp darunter.
    None = keine deutlich dickeren Linien vorhanden."""
    m = ink > 0
    total = int(m.sum())
    if total < 50:
        return None
    thick = 1
    for k in range(2, max_width + 1):
        if open_lines(m, k).sum() >= share * total:
            thick = k
        else:
            break
    return thick - 1 if thick >= 3 else None


def geometry_mask(ink, width=None, drop_small=40, keep_ratio=0.0):
    """Nur die Geometrie einer technischen Zeichnung: dicke Linien (Koerperkanten). Duenne Linien (Masslinien,
    Hinweislinien, Mittellinien, Schraffur) und Text in normaler Schriftstaerke fallen weg; kleine gefuellte Flecken
    (Masspfeile, Punkte) bis drop_small Pixel werden entfernt. Heuristik nach Strichstaerke - bei Zeichnungen ohne
    unterschiedliche Strichstaerken bleibt (fast) alles oder nichts uebrig. Rueckgabe: (Maske, verwendete Breite)."""
    if width is None:
        width = suggest_geometry_width(ink)
        if width is None:
            return ink > 0, None
    core = open_lines(ink, width)
    # Kanten der Linien wieder dazu, aber nur echte Linienpixel: setzt auch Linien wieder zusammen, die bei
    # gescannten (ausgefransten) Strichen durch das Ausduennen in Stuecke zerfallen sind
    m = (cv2.dilate(core.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))) > 0) & (ink > 0)
    if drop_small > 0 and m.any():
        n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
        bw, bh, area = st[:, cv2.CC_STAT_WIDTH], st[:, cv2.CC_STAT_HEIGHT], st[:, cv2.CC_STAT_AREA]
        fill = area / np.maximum(1, bw * bh)
        small = (np.maximum(bw, bh) <= drop_small) & ((fill > 0.3) | (np.maximum(bw, bh) <= drop_small / 3))
        small[0] = False                                   # klein und kompakt (Pfeilspitze, Punkt) oder winzig
        if small.any():
            m &= ~small[lab]
    return m, width


def cut_out(img, ink, rect, mode="all", width=None, drop_small=40):
    """Ausschnitt als BGRA-Bild fuer die Zwischenablage. mode: 'all' (wie angezeigt, mit Papier), 'lines'
    (nur Linien, Hintergrund durchsichtig), 'geometry' (nur dicke Linien, durchsichtig). Rueckgabe (bgra, width)."""
    x0, y0, x1, y1 = clip_rect(rect, img.shape)
    part = img[y0:y1, x0:x1]
    bgr = cv2.cvtColor(part, cv2.COLOR_GRAY2BGR) if part.ndim == 2 else part.copy()
    alpha = np.full(bgr.shape[:2], 255, np.uint8)
    used = None
    if mode in ("lines", "geometry"):
        ip = ink[y0:y1, x0:x1]
        if mode == "geometry":
            m, used = geometry_mask(ip, width, drop_small)
        else:
            m = ip > 0
        gray = part if part.ndim == 2 else part.min(axis=2)
        paper = paper_color(gray, ip)
        near = line_mask(m.astype(np.uint8), 1) & ~m        # Kantenglaettung: weicher Rand statt Treppen
        soft = np.clip((paper - gray.astype(np.int16)) * 3, 0, 255).astype(np.uint8)
        alpha[:] = 0
        alpha[near] = soft[near]
        alpha[m] = 255
    return np.dstack([bgr, alpha]), used


# ----------------------------------------------------------------- ganze Zeichnung (Groesse/Lage aendert sich)
def crop_images(images, rect):
    x0, y0, x1, y1 = clip_rect(rect, images[0].shape)
    return [np.ascontiguousarray(im[y0:y1, x0:x1]) for im in images]


def rotate_images(images, quarter):
    """Um quarter * 90 Grad im Uhrzeigersinn drehen."""
    return [np.ascontiguousarray(np.rot90(im, -quarter % 4)) for im in images]


def resize_images(images, factor):
    out = []
    for im in images:
        h, w = im.shape[:2]
        size = (max(1, int(round(w * factor))), max(1, int(round(h * factor))))
        out.append(cv2.resize(im, size, interpolation=cv2.INTER_AREA if factor < 1 else cv2.INTER_CUBIC))
    return out


def adjust_images(images, brightness=0, contrast=1.0):
    """Helligkeit (-100 ... 100) und Kontrast (Faktor) um die Mitte 128."""
    lut = np.clip((np.arange(256, dtype=np.float32) - 128) * contrast + 128 + brightness * 1.28, 0, 255).astype(np.uint8)
    return [cv2.LUT(im, lut) for im in images]


def auto_levels(gray):
    """(Helligkeit, Kontrast), die Papier weiss und Linien kraeftig machen (1 % / 99,5 % der Grauwerte)."""
    sample = gray[::max(1, gray.shape[0] // 1000), ::max(1, gray.shape[1] // 1000)]
    lo, hi = np.percentile(sample, (1, 99.5))
    if hi - lo < 10:
        return 0, 1.0
    c = 255.0 / (hi - lo)
    b = (127.5 - ((lo + hi) / 2 - 128) * c - 128) / 1.28
    return float(np.clip(b, -100, 100)), float(np.clip(c, 0.2, 4.0))


def transform_anns(anns, fn, scale=1.0):
    """Markierungen mit der Punktabbildung fn(x, y) -> (x, y) mitfuehren (Zuschneiden, Drehen, Groesse)."""
    for a in anns:
        (a["x"], a["y"]), (a["x2"], a["y2"]) = fn(a["x"], a["y"]), fn(a["x2"], a["y2"])
        if a.get("pts"):
            a["pts"] = [list(fn(q[0], q[1])) + list(q[2:]) for q in a["pts"]]
        if a.get("w"):
            a["w"] *= scale
        if a.get("type") in ("rect", "cloud", "highlight", "ellipse", "image"):
            a["x"], a["x2"] = sorted((a["x"], a["x2"]))
            a["y"], a["y2"] = sorted((a["y"], a["y2"]))
        elif a.get("pts") and a.get("type") in ("pen", "polyline", "polygon"):
            a["x"], a["y"], a["x2"], a["y2"] = (min(q[0] for q in a["pts"]), min(q[1] for q in a["pts"]),
                                                 max(q[0] for q in a["pts"]), max(q[1] for q in a["pts"]))
    return anns


def rotate_point_fn(shape, quarter):
    """Abbildung eines Punkts bei Drehung um quarter * 90 Grad im Uhrzeigersinn (Bild h x w)."""
    h, w = shape[:2]
    q = quarter % 4
    if q == 1:
        return lambda x, y: (h - y, x)
    if q == 2:
        return lambda x, y: (w - x, h - y)
    if q == 3:
        return lambda x, y: (y, w - x)
    return lambda x, y: (x, y)


# ----------------------------------------------------------------- Vektorisieren (Pixel -> Linien)
def thin(ink, progress=None, cancel=None):
    """Skelett der Linien (Zhang-Suen, 1 Pixel breit): Mittellinien jeder Strichstaerke."""
    img = np.pad((ink > 0).astype(np.uint8), 1)
    it = 0
    while True:
        changed = False
        for step in (0, 1):
            if cancel is not None and cancel():
                raise KeyboardInterrupt
            P = img
            p2, p3, p4 = P[:-2, 1:-1], P[:-2, 2:], P[1:-1, 2:]
            p5, p6, p7 = P[2:, 2:], P[2:, 1:-1], P[2:, :-2]
            p8, p9 = P[1:-1, :-2], P[:-2, :-2]
            c = P[1:-1, 1:-1]
            nb = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9
            seq = (p2, p3, p4, p5, p6, p7, p8, p9, p2)
            trans = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.uint8) for i in range(8))
            if step == 0:
                cond = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                cond = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            rm = (c == 1) & (nb >= 2) & (nb <= 6) & (trans == 1) & cond
            if rm.any():
                c[rm] = 0
                changed = True
        it += 1
        if progress:
            progress(min(0.5, it / 30))
        if not changed:
            break
    return img[1:-1, 1:-1]


_N8 = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def trace_skeleton(skel, eps=1.0, min_len=1, progress=None):
    """Skelett -> Linienzuege [(x, y), ...]. Knoten (3+ Nachbarn) verbinden die Zuege; Zuege werden mit
    eps Pixeln Toleranz vereinfacht."""
    sk = (skel > 0).astype(np.uint8)
    nb = cv2.filter2D(sk, cv2.CV_16S, np.ones((3, 3), np.float32)) - sk
    junction = (sk == 1) & (nb >= 3)
    nj, jlab = cv2.connectedComponents(junction.astype(np.uint8), connectivity=8)
    jcent = [None] * nj
    if nj > 1:
        ys, xs = np.nonzero(jlab)
        lab = jlab[ys, xs]
        cnt = np.bincount(lab, minlength=nj)
        cx = np.bincount(lab, xs, minlength=nj) / np.maximum(1, cnt)
        cy = np.bincount(lab, ys, minlength=nj) / np.maximum(1, cnt)
        jcent = [(float(cx[i]), float(cy[i])) for i in range(nj)]
    rest = (sk == 1) & ~junction
    n, lab = cv2.connectedComponents(rest.astype(np.uint8), connectivity=8)
    ys, xs = np.nonzero(lab)
    order = np.argsort(lab[ys, xs], kind="stable")
    ys, xs, ls = ys[order], xs[order], lab[ys, xs][order]
    bounds = np.searchsorted(ls, np.arange(1, n + 1))
    H, W = sk.shape
    paths = []
    for i in range(1, n):
        if progress and i % 2000 == 0:
            progress(0.5 + 0.45 * i / n)
        py, px = ys[bounds[i - 1]:bounds[i]], xs[bounds[i - 1]:bounds[i]]
        pix = set(zip(px.tolist(), py.tolist()))
        if not pix:
            continue

        def nbrs(p):
            return [(p[0] + dx, p[1] + dy) for dy, dx in _N8 if (p[0] + dx, p[1] + dy) in pix]
        start = next((p for p in pix if len(nbrs(p)) <= 1), next(iter(pix)))
        line, seen, cur = [start], {start}, start
        while True:                                   # entlang gehen (4er-Nachbarn zuerst: kein Zickzack)
            cand = [q for q in nbrs(cur) if q not in seen]
            if not cand:
                break
            cand.sort(key=lambda q: abs(q[0] - cur[0]) + abs(q[1] - cur[1]))
            cur = cand[0]
            seen.add(cur)
            line.append(cur)
        closed = len(line) > 3 and max(abs(line[0][0] - line[-1][0]), abs(line[0][1] - line[-1][1])) <= 1 \
            and len(nbrs(start)) >= 2
        pts = [(float(x), float(y)) for x, y in line]
        for end, at in ((line[0], 0), (line[-1], -1)):   # an Knoten anschliessen
            if closed:
                break
            for dy, dx in _N8:
                x, y = end[0] + dx, end[1] + dy
                if 0 <= x < W and 0 <= y < H and jlab[y, x]:
                    c = jcent[jlab[y, x]]
                    if at == 0:
                        pts.insert(0, c)
                    else:
                        pts.append(c)
                    break
        if len(pts) < min_len and not any(p in jcent for p in (pts[0], pts[-1])):
            continue
        if len(pts) == 1:                              # Punkt (z. B. Dezimalpunkt): kurzer Strich, runde Enden
            pts = [pts[0], (pts[0][0] + 0.01, pts[0][1])]
        arr = np.float32(pts).reshape(-1, 1, 2)
        simp = cv2.approxPolyDP(arr, eps, closed).reshape(-1, 2)
        paths.append(([(float(a), float(b)) for a, b in simp] + ([(float(simp[0][0]), float(simp[0][1]))] if closed else [])))
    return paths


def vectorize(ink, mode="center", eps=1.0, progress=None, cancel=None):
    """Pixelzeichnung -> Vektoren. mode 'center': Mittellinien (fuer CAD) plus gefuellte Flaechen fuer alles, was
    deutlich dicker als ein Strich ist (Masspfeile, Punkte, Balken); 'outline': nur gefuellte Umrisse (sieht genau
    aus wie das Original). Rueckgabe dict(lines, fills, width)."""
    m = (ink > 0).astype(np.uint8)
    if mode == "outline":
        return dict(lines=[], fills=outline_paths(m, min(eps, 0.7)), width=1.0)
    sk = thin(m, progress, cancel)
    sw = stroke_width(m, sk)
    k = int(round(2.2 * sw)) | 1                      # Flaechen: dicker als ~2 Striche
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(3, k), max(3, k)))
    blobs = cv2.morphologyEx(m, cv2.MORPH_OPEN, se)
    fills = []
    if blobs.any():
        blobs = cv2.dilate(blobs, np.ones((3, 3), np.uint8)) & m
        fills = outline_paths(blobs, 0.7)
        sk = thin(m & ~blobs, None, cancel) if fills else sk
    return dict(lines=trace_skeleton(sk, eps, progress=progress), fills=fills, width=sw)


def outline_paths(ink, eps=0.7):
    """Umrisse der Linien (mit Loechern) als geschlossene Linienzuege: sieht aus wie das Original."""
    cnts, _ = cv2.findContours((ink > 0).astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in cnts:
        if len(c) < 3:
            continue
        s = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
        if len(s) >= 3:
            out.append([(float(x), float(y)) for x, y in s])
    return out


def stroke_width(ink, skel=None):
    """Typische Strichstaerke (px): doppelter Abstand der Mittellinie zum Rand (Median)."""
    dt = cv2.distanceTransform((ink > 0).astype(np.uint8), cv2.DIST_L2, 3)
    sk = thin(ink) if skel is None else skel
    v = dt[sk > 0]
    return float(max(1.0, 2 * np.median(v))) if v.size else 1.0


def write_vectors(path, vec, size, dpi=200, mm_px=None, color=(0, 0, 0)):
    """Ergebnis von vectorize() als SVG, PDF oder DXF: Linien mit Strichstaerke, Flaechen gefuellt.
    DXF: Koordinaten in mm (mm_px = mm je Pixel inkl. Massstab), y nach oben; Linien und Flaechen auf eigenen Layern."""
    W, H = size
    lines, fills, width = vec["lines"], vec["fills"], vec["width"]
    ext = os.path.splitext(path)[1].lower()
    hexcol = "#%02x%02x%02x" % color
    if ext == ".svg":
        mmw, mmh = W * 25.4 / dpi, H * 25.4 / dpi
        out = [f'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="{mmw:.2f}mm" '
               f'height="{mmh:.2f}mm" viewBox="0 0 {W} {H}">']
        if fills:
            d = " ".join("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in p) + " Z" for p in fills)
            out.append(f'<path d="{d}" fill="{hexcol}" fill-rule="evenodd" stroke="none"/>')
        if lines:
            out.append(f'<g fill="none" stroke="{hexcol}" stroke-width="{width:.2f}" stroke-linecap="round" '
                       f'stroke-linejoin="round">')
            out.extend('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in p) + '"/>' for p in lines)
            out.append("</g>")
        out.append("</svg>\n")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out))
    elif ext == ".pdf":
        import pymupdf
        k = 72.0 / dpi
        doc = pymupdf.open()
        page = doc.new_page(width=W * k, height=H * k)
        sh = page.new_shape()
        col = tuple(v / 255 for v in color)
        if fills:
            for p in fills:
                sh.draw_polyline([pymupdf.Point(x * k, y * k) for x, y in p] + [pymupdf.Point(p[0][0] * k, p[0][1] * k)])
            sh.finish(color=None, fill=col, even_odd=True, closePath=True)
        if lines:
            for p in lines:
                sh.draw_polyline([pymupdf.Point(x * k, y * k) for x, y in p])
            sh.finish(color=col, width=max(0.1, width * k), lineCap=1, lineJoin=1, closePath=False)
        sh.commit()
        doc.save(path, deflate=True)
        doc.close()
    elif ext == ".dxf":
        import ezdxf
        f = mm_px or 25.4 / dpi
        doc = ezdxf.new("R2010", setup=True)
        doc.units = ezdxf.units.MM
        doc.layers.add("LINIEN", color=7)
        doc.layers.add("FLAECHEN", color=7)
        msp = doc.modelspace()
        for p in lines:
            msp.add_lwpolyline([(x * f, (H - y) * f) for x, y in p], dxfattribs={"layer": "LINIEN"})
        for p in fills:                              # Flaechen als Schraffur SOLID mit Umriss
            pts = [(x * f, (H - y) * f) for x, y in p]
            hatch = msp.add_hatch(color=7, dxfattribs={"layer": "FLAECHEN"})
            hatch.paths.add_polyline_path(pts, is_closed=True)
        doc.saveas(path)
    else:
        raise ValueError(ext)
    return len(lines) + len(fills)
