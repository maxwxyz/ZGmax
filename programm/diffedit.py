"""Zeichnung bearbeiten: Ausschnitt verschieben und Auswahl kopieren (auch nur Linien oder nur Geometrie).

Alle Funktionen arbeiten auf Bild-Arrays (Graustufen HxW oder BGR HxWx3) und der Linienmaske (uint8, >0 = Linie)
derselben Groesse. Rechtecke sind (x0, y0, x1, y1) in Pixeln, x1/y1 exklusiv.
"""
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
