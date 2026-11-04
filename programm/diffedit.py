"""Zeichnung bearbeiten: Ausschnitt verschieben, Auswahl kopieren (auch nur Linien oder nur Geometrie), zuschneiden,
drehen, Helligkeit, Bildgroesse, Scans aufbereiten (Hintergrund, gerade, entzerren) und Vektorisieren (Pixel -> Linien fuer SVG, PDF, DXF).

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


def stroke_width_hist(ink):
    """Strichbreiten einer Rasterzeichnung: {breite_px: laenge * breite}. Gemessen auf der Mittellinie jedes Strichs
    (Maxima der Abstandstransformation: Abstand zum Papier d, Breite etwa 2 d - 1)."""
    m = (ink > 0).astype(np.uint8)
    if m.sum() < 50:
        return {}
    d = cv2.distanceTransform(m, cv2.DIST_L2, 3)
    ridge = (d > 0) & (d >= cv2.dilate(d, np.ones((3, 3), np.uint8)))
    w = np.maximum(1, np.round(2 * d[ridge] - 1)).astype(np.int64)
    return {k: float(v) * k for k, v in enumerate(np.bincount(w)) if v}


def suggest_geometry_width(ink):
    """Linienbreite (px), ab der eine Linie als Koerperkante gilt (Koerperkanten sind nach Norm etwa doppelt so breit
    wie Mass- und Hinweislinien). Funktioniert auch, wenn duenne Linien und Text den groessten Teil der Zeichnung
    ausmachen. None = keine deutlich dickeren Linien vorhanden."""
    return geometry_width_from_strokes(stroke_width_hist(ink))


def width_band(ink, lo=0, hi=0):
    """Nur Linien mit einer Strichbreite von lo bis hi Pixel (0 = ohne Grenze) - z. B. nur Konturen (dicke Linien)
    oder nur Mass-/Hinweislinien und Text. Rueckgabe uint8 0/255 wie ink."""
    m = ink > 0
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    keep = m
    if lo and lo > 1:                                  # Kern der dicken Linien, Kanten wieder dazu (Scans)
        keep = (cv2.dilate(open_lines(m, lo).astype(np.uint8), se) > 0) & m
    if hi and hi > 0:
        thick = (cv2.dilate(open_lines(m, hi + 1).astype(np.uint8), se) > 0) & m
        keep = keep & ~thick
    return keep.astype(np.uint8) * 255


def geometry_width_from_strokes(hist, min_share=0.05, ratio=1.4):
    """Grenze zwischen duennen Linien und Koerperkanten aus einer Strichbreiten-Verteilung ({breite_px: gewicht}),
    gemessen (stroke_width_hist) oder aus einem Vektor-PDF (diffvector.stroke_hist).
    Koerperkanten = dickste Breite mit nennenswertem Anteil; die Grenze liegt zwischen ihr und der naechsten mindestens
    ratio-mal duenneren. None = nur eine Strichbreite."""
    total = sum(hist.values())
    if total <= 0:
        return None
    widths = sorted(k for k, v in hist.items() if v >= min_share * total)
    if not widths:
        return None
    thick = widths[-1]
    thin = [k for k in widths if k * ratio <= thick]       # benachbarte Breiten (Rundung, Scan) sind eine Klasse
    if not thin:
        return None
    return max(thin[-1] + 1, int(np.ceil((thin[-1] + thick) / 2)))


def resolve_band(ink, mode, lo=0, hi=0, gw=None):
    """Linienfilter als (lo, hi) in Pixeln: 'contours' = ab der Breite der Koerperkanten, 'thin' = darunter
    (beides aus der Zeichnung bestimmt; gw = schon bekannte Grenze, z. B. aus dem PDF), 'custom' = lo/hi,
    sonst (0, 0) = alle Linien."""
    if mode in ("contours", "thin"):
        if gw is None:
            gw = suggest_geometry_width(ink)
        if gw is None:                                 # keine deutlich dickeren Linien: Filter wirkt nicht
            return 0, 0
        return (gw, 0) if mode == "contours" else (0, gw - 1)
    if mode == "custom":
        return int(lo), int(hi)
    return 0, 0


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
def crop_images(images, rect, ink=None):
    """Auf rect zuschneiden. Ragt rect ueber das Blatt hinaus, wird das Blatt vergroessert; der neue Rand bekommt
    die Papierfarbe (aus ink bestimmt, sonst Weiss)."""
    h, w = images[0].shape[:2]
    x0, y0, x1, y1 = (int(v) for v in rect)
    out = []
    for im in images:
        bg = paper_color(im, ink) if ink is not None else (255 if im.ndim == 2 else (255, 255, 255))
        canvas = np.empty((y1 - y0, x1 - x0) + im.shape[2:], im.dtype)
        canvas[:] = bg
        sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        if sx1 > sx0 and sy1 > sy0:
            canvas[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = im[sy0:sy1, sx0:sx1]
        out.append(canvas)
    return out


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


# ----------------------------------------------------------------- Scan aufbereiten: Hintergrund, gerade, entzerren
def background_estimate(img, size=None):
    """Verlauf des Papiers (Schatten, Falten, Vergilbung) ohne die Linien: verkleinern, Linien zuschliessen
    (dunkle Striche verschwinden im hellen Umfeld), glaetten, wieder vergroessern."""
    h, w = img.shape[:2]
    k = min(1.0, 900 / max(h, w))
    small = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else img.copy()
    r = size or max(5, int(round(max(small.shape[:2]) / 90)) | 1)
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (r, r)))
    bg = cv2.medianBlur(bg, min(255, 2 * r + 1) if bg.dtype == np.uint8 else 5)
    return cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR)


def flatten_background(images, strength=50, color=None):
    """Hintergrund ausgleichen: Bild durch den geschaetzten Papierverlauf teilen (Papier wird gleichmaessig weiss),
    strength (0 ... 100) macht hellen Rest (Falten, Flecken) ganz weiss. color: neue Papierfarbe (B, G, R) oder None
    = weiss. Linien behalten ihre Farbe."""
    out = []
    t = 255 - 1.6 * float(strength)                     # ab diesem Grauwert ist es Papier
    for im in images:                                   # alles in 8 Bit: auch A0-Scans ohne grossen Speicher
        bg = np.maximum(background_estimate(im), 1)
        flat = cv2.divide(im, bg, scale=255)
        if strength > 0:
            flat = cv2.convertScaleAbs(flat, alpha=255.0 / max(t, 1.0))
        if color is not None:                            # weisses Papier einfaerben, Schwarz bleibt schwarz
            c = [v / 255.0 for v in color[:3]]
            if im.ndim == 2:
                flat = cv2.convertScaleAbs(flat, alpha=sum(c) / 3)
            else:
                flat = cv2.merge([cv2.convertScaleAbs(ch, alpha=k) for ch, k in zip(cv2.split(flat), c)])
        out.append(flat)
    return out


def ink_of(img):
    """Linienmaske eines Scans (Otsu auf dem ausgeglichenen Graubild)."""
    g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    g = flatten_background([g], 0)[0]
    _, ink = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return ink


def skew_angle(img, max_angle=15.0):
    """Drehwinkel zum Geraderichten in Grad (positiv = gegen den Uhrzeigersinn drehen) aus den langen Linien
    (Rahmen, Schriftfeld, Bemassung). None, wenn nichts Verlaessliches gefunden wurde."""
    h, w = img.shape[:2]
    k = min(1.0, 1600 / max(h, w))
    small = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else img
    ink = ink_of(small)
    lines = cv2.HoughLinesP(ink, 1, np.pi / 1800, threshold=80, minLineLength=max(40, max(small.shape[:2]) // 12),
                            maxLineGap=4)
    if lines is None:
        return None
    angles, weights = [], []
    for x0, y0, x1, y1 in lines.reshape(-1, 4):
        a = np.degrees(np.arctan2(y1 - y0, x1 - x0))       # y nach unten: positiv = im Uhrzeigersinn geneigt
        a = (a + 45) % 90 - 45                             # senkrechte Linien zaehlen wie waagerechte
        if abs(a) <= max_angle:
            angles.append(a)
            weights.append(np.hypot(x1 - x0, y1 - y0))
    if len(angles) < 2:
        return None
    angles, weights = np.array(angles), np.array(weights)
    order = np.argsort(angles)
    cum = np.cumsum(weights[order])
    med = angles[order][np.searchsorted(cum, cum[-1] / 2)]  # gewichteter Median: robust gegen Schraffuren
    near = np.abs(angles - med) < 0.5
    return float(np.average(angles[near], weights=weights[near]))


def line_angle(x0, y0, x1, y1):
    """Drehwinkel (Grad, gegen den Uhrzeigersinn), der eine nachgezeichnete Linie waagerecht bzw. senkrecht macht."""
    a = np.degrees(np.arctan2(y1 - y0, x1 - x0))
    return float((a + 45) % 90 - 45)


def rotate_angle_images(images, angle, ink=None):
    """Um angle Grad gegen den Uhrzeigersinn drehen (Bild waechst, damit nichts abgeschnitten wird; neue Ecken in
    Papierfarbe). Rueckgabe (Bilder, Punktabbildung fn(x, y))."""
    h, w = images[0].shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)    # OpenCV: positiv = gegen den Uhrzeigersinn
    cos, sin = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(np.ceil(h * sin + w * cos)), int(np.ceil(h * cos + w * sin))
    m[0, 2] += nw / 2 - w / 2
    m[1, 2] += nh / 2 - h / 2
    out = []
    for im in images:
        bg = paper_color(im, ink) if ink is not None else (255 if im.ndim == 2 else (255, 255, 255))
        out.append(cv2.warpAffine(im, m, (nw, nh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT,
                                  borderValue=bg if im.ndim == 2 else tuple(int(v) for v in bg)))

    def fn(x, y):
        return float(m[0, 0] * x + m[0, 1] * y + m[0, 2]), float(m[1, 0] * x + m[1, 1] * y + m[1, 2])
    return out, fn


def order_quad(pts):
    """Vier Punkte als oben links, oben rechts, unten rechts, unten links."""
    p = np.asarray(pts, np.float32).reshape(4, 2)
    s, d = p.sum(1), p[:, 1] - p[:, 0]
    return np.array([p[np.argmin(s)], p[np.argmin(d)], p[np.argmax(s)], p[np.argmax(d)]], np.float32)


def find_sheet_quad(img):
    """Ecken des Blatts in einem Foto (helles Papier vor dunklerem Grund). Ohne klares Blatt: die Bildecken
    (etwas eingerueckt), damit man sie von Hand setzen kann. Rueckgabe 4x2 (oben links, im Uhrzeigersinn)."""
    q = sheet_in_photo(img)
    if q is None:
        h, w = img.shape[:2]
        d = 0.03 * min(h, w)
        return order_quad([(d, d), (w - d, d), (w - d, h - d), (d, h - d)])
    return q


def sheet_in_photo(img):
    """Ecken eines Blatts, das sich deutlich vom dunkleren Grund abhebt (Foto), sonst None (normaler Scan)."""
    h, w = img.shape[:2]
    k = min(1.0, 800 / max(h, w))
    small = cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k < 1 else img
    g = small if small.ndim == 2 else cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    g = cv2.GaussianBlur(g, (7, 7), 0)
    _, m = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))   # Zeichnung im Papier zuschliessen
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area = small.shape[0] * small.shape[1]
    best = None
    for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:3]:
        a = cv2.contourArea(c)
        if a < 0.2 * area or a > 0.98 * area:            # zu klein, oder das ganze Bild (kein Rand zu sehen)
            continue
        hull = cv2.convexHull(c)
        for eps in (0.02, 0.03, 0.05, 0.08):
            ap = cv2.approxPolyDP(hull, eps * cv2.arcLength(hull, True), True)
            if len(ap) == 4:
                best = ap.reshape(4, 2)
                break
        if best is None:
            best = cv2.boxPoints(cv2.minAreaRect(hull))
        break
    if best is None:
        return None
    paper = cv2.mean(g, mask=cv2.fillConvexPoly(np.zeros_like(g), order_quad(best).astype(np.int32), 255))[0]
    outside = cv2.mean(g, mask=255 - cv2.fillConvexPoly(np.zeros_like(g), order_quad(best).astype(np.int32), 255))[0]
    if paper - outside < 40:                             # kein klarer Unterschied: eher ein Scan mit Rand
        return None
    return order_quad(np.asarray(best, np.float32) / k)


def scan_hint(img):
    """Kurzer Blick auf eine frisch geoeffnete Rasterzeichnung: ('photo', None) wenn ein Blatt auf dunklerem Grund zu
    sehen ist, ('skew', Winkel) wenn sie merklich schief liegt, sonst None."""
    if sheet_in_photo(img) is not None:
        return "photo", None
    a = skew_angle(img)
    if a is not None and 0.3 <= abs(a) <= 15:
        return "skew", a
    return None


PAPER_MM = {"A4": (210, 297), "A3": (297, 420), "A2": (420, 594), "A1": (594, 841), "A0": (841, 1189)}


def quad_size(quad):
    """Breite und Hoehe (px) des entzerrten Blatts: laengere der gegenueberliegenden Kanten."""
    tl, tr, br, bl = order_quad(quad)
    w = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    h = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    return max(1, int(round(w))), max(1, int(round(h)))


def warp_size(quad, paper=None):
    """Zielgroesse (w, h) px und mm je px (oder None) fuer ein Papierformat ('A4' ... 'A0', Lage aus den Ecken) bzw.
    das Seitenverhaeltnis der Ecken (paper None)."""
    w, h = quad_size(quad)
    if paper not in PAPER_MM:
        return (w, h), None
    a, b = PAPER_MM[paper]
    mw, mh = (b, a) if w > h else (a, b)
    px = max(w / mw, h / mh)                             # Aufloesung der Ecken halten (px je mm)
    return (int(round(mw * px)), int(round(mh * px))), 1.0 / px


def warp_quad(images, quad, size, ink=None):
    """Blatt entzerren: die vier Ecken (oben links, im Uhrzeigersinn) werden auf ein Rechteck size = (w, h)
    abgebildet. Rueckgabe (Bilder, Punktabbildung fn(x, y))."""
    w, h = size
    src = order_quad(quad)
    dst = np.array([(0, 0), (w, 0), (w, h), (0, h)], np.float32)
    m = cv2.getPerspectiveTransform(src, dst)
    out = []
    for im in images:
        bg = paper_color(im, ink) if ink is not None else (255 if im.ndim == 2 else (255, 255, 255))
        out.append(cv2.warpPerspective(im, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT,
                                       borderValue=bg if im.ndim == 2 else tuple(int(v) for v in bg)))

    def fn(x, y):
        q = m @ np.array([x, y, 1.0])
        return float(q[0] / q[2]), float(q[1] / q[2])
    return out, fn


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


def fit_circle(pts):
    """Kreis durch Punkte (algebraisch nach Taubin, auch fuer kurze Boegen kaum verzerrt): (cx, cy, r) oder None."""
    p = np.asarray(pts, np.float64)
    if len(p) < 3:
        return None
    m = p.mean(axis=0)
    u, v = p[:, 0] - m[0], p[:, 1] - m[1]
    z = u * u + v * v
    zm = z.mean()
    if zm <= 1e-12:
        return None
    z0 = (z - zm) / (2 * np.sqrt(zm))
    try:
        _, _, vt = np.linalg.svd(np.column_stack([z0, u, v]), full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    a = vt[2].copy()
    a[0] /= 2 * np.sqrt(zm)
    a3 = -zm * a[0]
    if abs(a[0]) < 1e-12:                             # Gerade (unendlicher Radius)
        return None
    cx, cy = -a[1] / a[0] / 2 + m[0], -a[2] / a[0] / 2 + m[1]
    r2 = a[1] * a[1] + a[2] * a[2] - 4 * a[0] * a3
    if r2 <= 0:
        return None
    return float(cx), float(cy), float(np.sqrt(r2) / abs(a[0]) / 2)


def _arc_of(p, eps=1.0):
    """Liegen die Punkte p (N x 2, in Laufrichtung) auf einem Kreisbogen? Rueckgabe (cx, cy, r, a0, sweep) mit
    Winkeln in Grad im Bild (y nach unten), sweep mit Vorzeichen der Laufrichtung; sonst None."""
    if len(p) < 8:
        return None
    q = p[2:-2] if len(p) >= 14 else p                # Enden am Knoten sind vom Ausduennen verzogen
    c = fit_circle(q)
    if c is None:
        return None
    cx, cy, r = c
    ext = float(np.ptp(p, axis=0).max())
    if r < 4 or r > 50 * max(ext, 1.0):
        return None
    d = np.hypot(q[:, 0] - cx, q[:, 1] - cy) - r
    tol = max(1.0, eps) + 0.01 * r                   # Pixelraster des Skeletts: knapp 1 px Abweichung
    if np.abs(d).max() > tol or np.sqrt(np.mean(d * d)) > 0.45 * tol:
        return None
    a = np.arctan2(p[:, 1] - cy, p[:, 0] - cx)
    da = np.diff(a)
    da = (da + np.pi) % (2 * np.pi) - np.pi
    tot = float(da.sum())
    if np.any(np.sign(tot) * da < -1.5 / r):          # laeuft zurueck: kein Bogen
        return None
    idx = _dp_index(p, max(1.0, eps))                 # keine Ecke im Bogen (Spitze eines A, Rechteckecke)
    if len(idx) > 2:
        v = np.diff(p[idx], axis=0)
        h = np.arctan2(v[:, 1], v[:, 0])
        if np.hypot(*(p[-1] - p[0])) < 1.5:            # geschlossen: auch die Naht ist eine Ecke
            h = np.append(h, h[0])
        turn = np.abs((np.diff(h) + np.pi) % (2 * np.pi) - np.pi)
        lim = 2 * np.arccos(max(-1.0, 1 - 1.2 * max(1.0, eps) / r)) + np.radians(10)
        if turn.max() > lim:
            return None
    sw = abs(tot)
    if sw < np.radians(20) or r * (1 - np.cos(min(sw, np.pi) / 2)) < 1.5:   # zu flach: Linie
        return None
    return cx, cy, r, float(np.degrees(a[0])), float(np.degrees(tot))


def _dp_index(p, eps):
    """Douglas-Peucker auf einem offenen Linienzug: Indizes der behaltenen Punkte (aufsteigend)."""
    n = len(p)
    if n <= 2:
        return list(range(n))
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        a, b = p[i], p[j]
        q = p[i + 1:j]
        ab = b - a
        L = float(np.hypot(*ab))
        if L < 1e-9:
            dist = np.hypot(q[:, 0] - a[0], q[:, 1] - a[1])
        else:
            dist = np.abs(ab[0] * (q[:, 1] - a[1]) - ab[1] * (q[:, 0] - a[0])) / L
        k = int(np.argmax(dist))
        if dist[k] > eps:
            k += i + 1
            keep[k] = True
            stack.append((i, k))
            stack.append((k, j))
    return [int(i) for i in np.nonzero(keep)[0]]


def _arc_point(cx, cy, r, deg):
    t = np.radians(deg)
    return (cx + r * float(np.cos(t)), cy + r * float(np.sin(t)))


def _segment(p, eps):
    """Offenen Linienzug (Bildpixel, N x 2) gierig in Linien und Kreisboegen zerlegen: ["L", i0, i1] oder
    ["A", i0, i1, bogen] mit Indizes in p."""
    bp = _dp_index(p, eps)
    parts, i = [], 0                                   # ["L", k0, k1] oder ["A", k0, k1, bogen], k = Index in bp
    while i < len(bp) - 1:
        best, miss = None, 0
        for j in range(i + 2, len(bp)):
            arc = _arc_of(p[bp[i]:bp[j] + 1], eps)
            if arc is None:
                miss += 1
                if (best is not None and miss > 2) or (best is None and j - i >= 6):   # passt nicht (mehr)
                    break
                continue
            best, miss = (j, arc), 0
        if best is None:
            if parts and parts[-1][0] == "L":
                parts[-1][2] = i + 1
            else:
                parts.append(["L", i, i + 1])
            i += 1
        else:
            j, arc = best
            k = i
            while parts and parts[-1][0] == "L" and k > parts[-1][1]:   # Bogen nach hinten in die Linie verlaengern
                a2 = _arc_of(p[bp[k - 1]:bp[j] + 1], eps)
                if a2 is None:
                    break
                k, arc = k - 1, a2
                parts[-1][2] = k
                if parts[-1][1] == k:
                    parts.pop()
            parts.append(["A", k, j, arc])
            i = j
    return [[q[0], bp[q[1]], bp[q[2]]] + q[3:] for q in parts]


def _curves_of(pts, closed, eps=1.0):
    """Ein verfolgter Linienzug (Bildpixel) -> (Linienzuege, Boegen, Kreise). Bogen = (cx, cy, r, a0, a1) in Grad,
    im Bild (y nach unten) von a0 aufsteigend bis a1; Kreis = (cx, cy, r). Gerade Abschnitte bleiben Linienzuege."""
    p = np.asarray(pts, np.float64)
    if closed:
        pc = np.vstack([p, p[:1]])
        arc = _arc_of(pc, eps)
        if arc is not None and abs(arc[4]) > 340:
            return [], [], [arc[:3]]
        idx = _dp_index(pc, eps)                       # Start an die schaerfste Ecke legen (nicht mitten im Bogen)
        if len(idx) > 3:
            best, k0 = -1.0, 0
            for k in range(len(idx) - 1):
                a = pc[idx[k - 1] if k else idx[-2]]
                b, c = pc[idx[k]], pc[idx[k + 1]]
                v1, v2 = b - a, c - b
                n1, n2 = np.hypot(*v1), np.hypot(*v2)
                if n1 > 0 and n2 > 0:
                    t = 1 - float(np.dot(v1, v2) / (n1 * n2))
                    if t > best:
                        best, k0 = t, idx[k]
            p = np.roll(p, -k0, axis=0)
        p = np.vstack([p, p[:1]])
    parts = _segment(p, eps)
    if closed and any(q[0] == "L" for q in parts) and "A" in (parts[0][0], parts[-1][0]):
        q = max((q for q in parts if q[0] == "L"), key=lambda q: q[2] - q[1])   # Naht in die Mitte einer Linie
        m = (q[1] + q[2]) // 2
        p = np.roll(p[:-1], -m, axis=0)
        p = np.vstack([p, p[:1]])
        parts = _segment(p, eps)
    items = []                                         # ["L", punkte] oder ["A", cx, cy, r, winkel_anfang, winkel_ende]
    for pt in parts:
        if pt[0] == "A":
            cx, cy, r, a0, sw = pt[3]
            items.append(["A", cx, cy, r, a0, a0 + sw])
        else:
            seg = p[pt[1]:pt[2] + 1]
            items.append(["L", [tuple(map(float, seg[k])) for k in _dp_index(seg, eps)]])
    pairs = [(k, k + 1) for k in range(len(items) - 1)] + ([(len(items) - 1, 0)] if closed and len(items) > 1 else [])
    for k, m in pairs:                                 # Uebergang Bogen <-> Linie: tangential oder am Bogenende
        x, y = items[k], items[m]
        if x[0] == y[0] == "A":                        # zwei Boegen: am Schnittpunkt der Kreise verbinden
            q = _circle_cut(x, y, _arc_point(x[1], x[2], x[3], x[5]), 3.5 * max(1.0, eps))
            if q is not None:
                for arc, slot in ((x, 5), (y, 4)):
                    t = float(np.degrees(np.arctan2(q[1] - arc[2], q[0] - arc[1])))
                    t = arc[slot] + (t - arc[slot] + 180) % 360 - 180
                    other = arc[9 - slot]
                    if (t - other) * (arc[slot] - other) > 0:   # Laufrichtung bleibt
                        arc[slot] = t
            continue
        if x[0] == y[0]:
            continue
        arc, ln, at_end = (x, y[1], True) if x[0] == "A" else (y, x[1], False)
        near, far = (ln[0], ln[1]) if at_end else (ln[-1], ln[-2])
        slot = 5 if at_end else 4
        t = _tangent_angle(arc, near, far, arc[slot], eps)
        if t is not None and (arc[5] - arc[4]) * ((t if at_end else arc[5]) - (arc[4] if at_end else t)) > 0:
            arc[slot] = t
        q = _arc_point(arc[1], arc[2], arc[3], arc[slot])
        if at_end:
            ln[0] = q
        else:
            ln[-1] = q
    if closed and len(items) > 1 and items[0][0] == items[-1][0] == "L":   # Naht mitten in einer Linie
        ln = items[-1][1] + items[0][1][1:]
        items[0][1] = [ln[k] for k in _dp_index(np.asarray(ln, np.float64), eps)]
        items.pop()
    lines = [it[1] for it in items if it[0] == "L"]
    arcs = [(it[1], it[2], it[3], min(it[4], it[5]), max(it[4], it[5])) for it in items if it[0] == "A"]
    return lines, arcs, []


def _circle_cut(a, b, near, dist):
    """Schnittpunkt der Kreise zweier Boegen ["A", cx, cy, r, ..], der near am naechsten liegt (hoechstens dist
    entfernt), sonst None."""
    (x0, y0, r0), (x1, y1, r1) = a[1:4], b[1:4]
    d = float(np.hypot(x1 - x0, y1 - y0))
    if d < 1e-6 or d > r0 + r1 or d < abs(r0 - r1):
        return None
    t = (d * d + r0 * r0 - r1 * r1) / (2 * d)
    h = float(np.sqrt(max(0.0, r0 * r0 - t * t)))
    ux, uy = (x1 - x0) / d, (y1 - y0) / d
    px, py = x0 + t * ux, y0 + t * uy
    q = min(((px - h * uy, py + h * ux), (px + h * uy, py - h * ux)),
            key=lambda c: np.hypot(c[0] - near[0], c[1] - near[1]))
    return q if np.hypot(q[0] - near[0], q[1] - near[1]) <= dist else None


def _tangent_angle(arc, near, far, cur, eps=1.0):
    """Laeuft die Strecke far -> near tangential in den Bogen? Dann Winkel (Grad) des Beruehrpunkts, sonst None."""
    _, cx, cy, r = arc[:4]
    ax, ay = far
    dx, dy = near[0] - ax, near[1] - ay
    L2 = dx * dx + dy * dy
    if L2 < 4:
        return None
    t = ((cx - ax) * dx + (cy - ay) * dy) / L2
    fx, fy = ax + t * dx, ay + t * dy
    if t < 0.3 or abs(np.hypot(cx - fx, cy - fy) - r) > max(1.0, eps, 0.02 * r) \
            or np.hypot(fx - near[0], fy - near[1]) > 0.5 * r + 3:
        return None
    a = float(np.degrees(np.arctan2(fy - cy, fx - cx)))
    a = cur + (a - cur + 180) % 360 - 180
    return a if abs(a - cur) <= 45 else None


def merge_arcs(arcs, circles):
    """Boegen desselben Kreises (an Knoten zerteilt, z. B. von Mittellinien gekreuzt) zusammenfassen: luecken-
    lose Boegen werden ein Bogen, rundum ein Vollkreis. Rueckgabe (boegen, kreise)."""
    arcs = list(arcs)
    out_a, out_c = [], list(circles)
    used = [False] * len(arcs)
    cell = 8.0                                         # Raster der Mittelpunkte: nur Nachbarzellen vergleichen
    grid = {}
    for i, a in enumerate(arcs):
        grid.setdefault((int(a[0] // cell), int(a[1] // cell)), []).append(i)
    for i, a in enumerate(arcs):
        if used[i]:
            continue
        grp = [a]
        used[i] = True
        tol = min(cell, max(1.5, 0.03 * a[2]))
        gx, gy = int(a[0] // cell), int(a[1] // cell)
        for j in sorted(j for ix in (gx - 1, gx, gx + 1) for iy in (gy - 1, gy, gy + 1) for j in grid.get((ix, iy), ())):
            b = arcs[j]
            if not used[j] and abs(b[2] - a[2]) <= tol and np.hypot(b[0] - a[0], b[1] - a[1]) <= tol:
                grp.append(b)
                used[j] = True
        if len(grp) == 1:
            out_a.append(a)
            continue
        w = np.array([g[4] - g[3] for g in grp])
        cx, cy, r = (float(np.dot(w, [g[k] for g in grp]) / w.sum()) for k in range(3))
        gap = min(30.0, np.degrees(12.0 / r) + 2.0)       # Luecke am Knoten (kreuzende Linie) ueberbruecken
        iv = sorted(((g[3] % 360, g[3] % 360 + g[4] - g[3]) for g in grp))
        merged = [list(iv[0])]
        for s, e in iv[1:]:
            if s <= merged[-1][1] + gap:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        if len(merged) > 1 and merged[0][0] + 360 <= merged[-1][1] + gap:   # ueber 0 Grad hinweg
            merged[0] = [merged[-1][0], max(merged[-1][1], merged[0][1] + 360)]
            merged.pop()
        if len(merged) == 1 and merged[0][1] - merged[0][0] >= 360 - gap:
            out_c.append((cx, cy, r))
        else:
            out_a.extend((cx, cy, r, s, e) for s, e in merged)
    return out_a, out_c


def snap_ends(lines, arcs, dist=1.5):
    """Linienenden, die fast auf einem Bogenende liegen, genau dorthin setzen (geschlossener Zug im CAD)."""
    pts = [_arc_point(a[0], a[1], a[2], a[3]) for a in arcs] + [_arc_point(a[0], a[1], a[2], a[4]) for a in arcs]
    if not pts or not lines:
        return lines
    grid = {}
    for q in pts:
        grid.setdefault((int(q[0] // dist), int(q[1] // dist)), []).append(q)
    out = []
    for ln in lines:
        ln = list(ln)
        for k in (0, -1):
            x, y = ln[k]
            gx, gy = int(x // dist), int(y // dist)
            best, bd = None, dist
            for ix in (gx - 1, gx, gx + 1):
                for iy in (gy - 1, gy, gy + 1):
                    for q in grid.get((ix, iy), ()):
                        d = np.hypot(q[0] - x, q[1] - y)
                        if d <= bd:
                            best, bd = q, d
            if best is not None:
                ln[k] = best
        out.append(ln)
    return out


def trace_skeleton(skel, eps=1.0, min_len=1, progress=None, curves=False):
    """Skelett -> Linienzuege [(x, y), ...]. Knoten (3+ Nachbarn) verbinden die Zuege; Zuege werden mit
    eps Pixeln Toleranz vereinfacht. curves=True: Kreise und Kreisboegen erkennen, Rueckgabe dann
    (linienzuege, boegen, kreise) wie bei _curves_of."""
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
    paths, raw = [], []
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
        jn = [None, None]                               # Knoten an Anfang/Ende (Nummer)
        for end, at in ((line[0], 0), (line[-1], -1)):   # an Knoten anschliessen
            if closed:
                break
            cand = [int(jlab[end[1] + dy, end[0] + dx]) for dy, dx in _N8
                    if 0 <= end[0] + dx < W and 0 <= end[1] + dy < H and jlab[end[1] + dy, end[0] + dx]]
            if at and len(cand) > 1 and cand[0] == jn[0]:     # kurzer Zug zwischen zwei Knoten: nicht zweimal
                cand = [j for j in cand if j != jn[0]] + cand  # an denselben anschliessen
            if cand:
                if at == 0:
                    pts.insert(0, jcent[cand[0]])
                else:
                    pts.append(jcent[cand[0]])
                jn[at] = cand[0]
        if len(pts) < min_len and not any(p in jcent for p in (pts[0], pts[-1])):
            continue
        if curves:
            raw.append([pts, jn[0], jn[1], closed])
            continue
        paths.append(_simplify(pts, closed, eps))
    if not curves:
        return paths
    arcs, circles = [], []
    for pts, _, _, closed in _join_chains(raw):
        if len(pts) >= 8:
            ln, ar, ci = _curves_of(pts, closed, eps)
            paths.extend(ln)
            arcs.extend(ar)
            circles.extend(ci)
        else:
            paths.append(_simplify(pts, closed, eps))
    arcs, circles = merge_arcs(arcs, circles)
    return snap_ends(paths, arcs), arcs, circles


def _simplify(pts, closed, eps):
    """Linienzug mit eps Pixeln Toleranz vereinfachen (geschlossen: Anfangspunkt am Ende wiederholt)."""
    if len(pts) == 1:                                  # Punkt (z. B. Dezimalpunkt): kurzer Strich, runde Enden
        pts = [pts[0], (pts[0][0] + 0.01, pts[0][1])]
    arr = np.float32(pts).reshape(-1, 1, 2)
    simp = cv2.approxPolyDP(arr, eps, closed).reshape(-1, 2)
    return [(float(a), float(b)) for a, b in simp] + ([(float(simp[0][0]), float(simp[0][1]))] if closed else [])


def _join_chains(raw):
    """Zuege an Knoten mit genau zwei Anschluessen verbinden: das Skelett hat an Treppenstufen schraeger und
    runder Linien Schein-Knoten, die einen Kreis sonst in viele Stuecke teilen; kurze Stummel an Knoten fallen
    weg (Schleife zurueck zum selben Knoten, einzelnes Pixel mit freiem Ende). raw = [[pts, j0, j1, closed]]."""
    deg = {}
    for _, a, b, _ in raw:
        for j in (a, b):
            if j is not None:
                deg[j] = deg.get(j, 0) + 1
    raw = [c for c in raw if not ((len(c[0]) <= 4 and c[1] is not None and c[1] == c[2]) or
                                  (len(c[0]) <= 2 and (c[1] is None) != (c[2] is None)
                                   and deg.get(c[1] if c[1] is not None else c[2], 0) >= 3))]   # Stummel
    att = {}
    for i, (_, a, b, _) in enumerate(raw):
        for j in (a, b):
            if j is not None:
                att.setdefault(j, []).append(i)
    ch = [list(c) for c in raw]
    to = list(range(len(ch)))                          # Verweis auf den Zug, in dem ein Zug aufgegangen ist

    def cur(i):
        while to[i] != i:
            i = to[i]
        return i
    for node, lst in att.items():
        if len(lst) != 2:
            continue
        i, k = cur(lst[0]), cur(lst[1])
        a, b = ch[i], ch[k]
        if i == k:                                     # beide Enden am selben Knoten: geschlossener Zug
            if a[1] == node and a[2] == node and not a[3]:
                a[0] = a[0][:-1] if len(a[0]) > 1 and a[0][0] == a[0][-1] else a[0]
                a[1] = a[2] = None
                a[3] = True
            continue
        if a[2] != node:
            a[0], a[1], a[2] = a[0][::-1], a[2], a[1]
        if b[1] != node:
            b[0], b[1], b[2] = b[0][::-1], b[2], b[1]
        if a[2] != node or b[1] != node:
            continue
        a[0] = a[0] + b[0][1:]
        a[2] = b[2]
        to[k] = i
        ch[k] = None
    return [c for c in ch if c is not None]


def vectorize(ink, mode="center", eps=1.0, progress=None, cancel=None, curves=True):
    """Pixelzeichnung -> Vektoren. mode 'center': Mittellinien (fuer CAD) plus gefuellte Flaechen fuer alles, was
    deutlich dicker als ein Strich ist (Masspfeile, Punkte, Balken); 'outline': nur gefuellte Umrisse (sieht genau
    aus wie das Original). curves: Kreise und Kreisboegen als solche erkennen (nur Mittellinien).
    Rueckgabe dict(lines, fills, width, arcs, circles); Bogen (cx, cy, r, a0, a1) in Grad im Bild (y nach unten)."""
    m = (ink > 0).astype(np.uint8)
    if mode == "outline":
        return dict(lines=[], fills=outline_paths(m, min(eps, 0.7)), width=1.0, arcs=[], circles=[])
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
    if curves:
        lines, arcs, circles = trace_skeleton(sk, eps, progress=progress, curves=True)
    else:
        lines, arcs, circles = trace_skeleton(sk, eps, progress=progress), [], []
    return dict(lines=lines, fills=fills, width=sw, arcs=arcs, circles=circles)


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
    """Ergebnis von vectorize() als SVG, PDF oder DXF: Linien mit Strichstaerke, Flaechen gefuellt, erkannte Kreise
    und Boegen als echte Kreise/Boegen (SVG circle/Bogenpfad, PDF Kreis/Bogen, DXF CIRCLE/ARC).
    DXF: Koordinaten in mm (mm_px = mm je Pixel inkl. Massstab), y nach oben; Linien und Flaechen auf eigenen Layern."""
    W, H = size
    lines, fills, width = vec["lines"], vec["fills"], vec["width"]
    arcs, circles = vec.get("arcs", []), vec.get("circles", [])
    ext = os.path.splitext(path)[1].lower()
    hexcol = "#%02x%02x%02x" % color
    if ext == ".svg":
        mmw, mmh = W * 25.4 / dpi, H * 25.4 / dpi
        out = [f'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="{mmw:.2f}mm" '
               f'height="{mmh:.2f}mm" viewBox="0 0 {W} {H}">']
        if fills:
            d = " ".join("M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in p) + " Z" for p in fills)
            out.append(f'<path d="{d}" fill="{hexcol}" fill-rule="evenodd" stroke="none"/>')
        if lines or arcs or circles:
            out.append(f'<g fill="none" stroke="{hexcol}" stroke-width="{width:.2f}" stroke-linecap="round" '
                       f'stroke-linejoin="round">')
            out.extend('<polyline points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in p) + '"/>' for p in lines)
            out.extend(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}"/>' for cx, cy, r in circles)
            for cx, cy, r, a0, a1 in arcs:             # Bild und SVG: y nach unten, Winkel steigend = sweep 1
                (xa, ya), (xb, yb) = _arc_point(cx, cy, r, a0), _arc_point(cx, cy, r, a1)
                out.append(f'<path d="M{xa:.2f},{ya:.2f} A{r:.2f},{r:.2f} 0 {int(a1 - a0 > 180)} 1 {xb:.2f},{yb:.2f}"/>')
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
        if lines or arcs or circles:
            for p in lines:
                sh.draw_polyline([pymupdf.Point(x * k, y * k) for x, y in p])
            for cx, cy, r in circles:
                sh.draw_circle(pymupdf.Point(cx * k, cy * k), r * k)
            for cx, cy, r, a0, a1 in arcs:             # draw_sector: positiver Winkel = gegen den Uhrzeigersinn
                xa, ya = _arc_point(cx, cy, r, a0)
                sh.draw_sector(pymupdf.Point(cx * k, cy * k), pymupdf.Point(xa * k, ya * k), -(a1 - a0), fullSector=False)
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
        for cx, cy, r in circles:
            msp.add_circle((cx * f, (H - cy) * f), r * f, dxfattribs={"layer": "LINIEN"})
        for cx, cy, r, a0, a1 in arcs:                 # y gespiegelt: Bildwinkel a -> -a, Bogen laeuft dann von -a1 bis -a0
            msp.add_arc((cx * f, (H - cy) * f), r * f, (-a1) % 360, (-a0) % 360, dxfattribs={"layer": "LINIEN"})
        for p in fills:                              # Flaechen als Schraffur SOLID mit Umriss
            pts = [(x * f, (H - y) * f) for x, y in p]
            hatch = msp.add_hatch(color=7, dxfattribs={"layer": "FLAECHEN"})
            hatch.paths.add_polyline_path(pts, is_closed=True)
        doc.saveas(path)
    else:
        raise ValueError(ext)
    return len(lines) + len(fills) + len(arcs) + len(circles)
