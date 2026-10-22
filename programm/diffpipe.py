"""Ablauf des Vergleichs als wiederverwendbare Funktionen (fuer Kommandozeile und Viewer).

Stufen:
  1. load_gray()      Datei laden -> Graubild (dunkelster RGB-Kanal)
  2. prepare_pair()   Ausschnitt, Groesse, globale Ausrichtung      (langsam, nur bei neuen Dateien/Ausrichtung)
  3. run_compare()    Kacheln, Verschiebung, Objekt-Suche, Filter   (Parameter des Vergleichs)
"""
from dataclasses import dataclass, field, replace

import cv2
import numpy as np

import diffcore as dc


# ----------------------------------------------------------------- Parameter
@dataclass
class Params:
    thr: int = 128
    align: str = "affine"          # none | translation | euclidean | affine
    tiles: str = "auto"
    cell: int = 400
    max_shift: int = 30
    tol: int = 2
    hatch: int = 16
    move: int = 100
    obj_shift: int = 40
    obj_rotate: float = 3.0
    min_area: int = 20             # Unterschiedsgruppen mit weniger Pixeln werden ignoriert
    edge_noise: bool = True        # 1-px-Saeume an gemeinsamen Linien nicht als Aenderung werten
    ignore: list = field(default_factory=list)    # Zonen (x, y, b, h) in Pixeln von A
    ignore_border: int = 0         # Randstreifen (Pixel), der nicht verglichen wird
    verbose: bool = False

    def align_key(self):
        """Parameter, die die (langsame) Vorbereitung beeinflussen."""
        return (self.thr, self.align)

    def copy(self, **kw):
        return replace(self, **kw)


@dataclass
class Result:
    a: np.ndarray                  # Tinte A (uint8 0/255)
    b: np.ndarray                  # Tinte B, ausgerichtet
    oa: np.ndarray                 # nur in A (bool)
    ob: np.ndarray                 # nur in B (bool)
    both: np.ndarray
    moved: np.ndarray
    zone: np.ndarray               # ignorierte Zonen (bool) oder None
    nx: int = 1
    ny: int = 1
    objects: tuple = (0, 0, 0, 0)  # geprueft, erkannt, nur Verschiebung, mit Drehung
    found: list = field(default_factory=list)


# ----------------------------------------------------------------- Laden
def load_gray(path, page=1, dpi=200):
    """Dunkelster RGB-Kanal als uint8-Bild (255 = weiss). Schwelle wird spaeter angewandt."""
    img = dc.read_image(path, page, dpi)
    return img.min(axis=2)


def ink_from_gray(gray, thr):
    return ((gray < thr).astype(np.uint8)) * 255


def is_vector(path):
    """Datei wird gerendert (PDF/SVG/DXF): dpi bestimmt die Genauigkeit, nicht die Datei."""
    import os
    return os.path.splitext(path)[1].lower() in (dc.VECTOR_EXT | dc.CAD_EXT)


def page_count(path):
    """Anzahl Seiten (PDF, mehrseitiges TIF/GIF); sonst 1."""
    import os
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in dc.VECTOR_EXT:
            import pymupdf
            with pymupdf.open(path) as d:
                return max(1, d.page_count)
        if ext in {".tif", ".tiff", ".gif"}:
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = None
            with Image.open(path) as im:
                return max(1, getattr(im, "n_frames", 1))
    except Exception:
        pass
    return 1


def file_dpi(path):
    """Aufloesung (dpi) aus den Bilddaten, sonst None. Werte <= 96 gelten als nicht aussagekraeftig."""
    if is_vector(path):
        return None
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        with Image.open(path) as im:
            d = im.info.get("dpi")
            if d and d[0] and d[1]:
                v = float(d[0])
                if v > 96:
                    return int(round(v))
    except Exception:
        pass
    return None


def crop_pair(a_full, b_full, box_a, log=print):
    """Schneidet A auf box_a (x, y, b, h) zu und sucht den passenden Ausschnitt in B.
    Gibt (a, b, box_b) zurueck. Ohne box_a: beide unveraendert."""
    if box_a is None:
        return a_full, b_full, None
    a = dc.crop(a_full, box_a)
    log("Suche Ausschnitt A in B (automatisch) ...")
    box_b, score = dc.autofit(a, b_full)
    if box_b is None:
        log("  Warnung: nichts gefunden, nutze ganzes Bild B")
        return a, b_full, None
    log(f"  gefunden: {box_b}  (Uebereinstimmung {score:.2f})")
    if score < 0.15:
        log("  Warnung: schwache Uebereinstimmung - Ergebnis pruefen, evtl. groesseren Ausschnitt waehlen")
    return a, dc.crop(b_full, box_b), box_b


# ----------------------------------------------------------------- Stufe 2
def match_size(a, b):
    """B auf die Groesse von A bringen (ohne Skalierung, wenn der Massstab gleich ist)."""
    sx, sy = a.shape[1] / b.shape[1], a.shape[0] / b.shape[0]
    if abs(sx - 1) < 0.01 and abs(sy - 1) < 0.01:
        canvas = np.zeros(a.shape, np.uint8)
        hh, ww = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
        canvas[:hh, :ww] = b[:hh, :ww]
        return canvas
    interp = cv2.INTER_AREA if b.shape[0] > a.shape[0] else cv2.INTER_LINEAR
    b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=interp)
    return ((b > 127).astype(np.uint8)) * 255


def prepare_pair(a, b, align="affine", log=print):
    """Bringt B auf Groesse und Lage von A (global). Gibt B zurueck."""
    return prepare_pair_tf(a, b, align, log)[0]


def prepare_pair_tf(a, b, align="affine", log=print):
    """Wie prepare_pair, gibt zusaetzlich die Umrechnung zurueck, mit der apply_tf() ein anderes Bild von B
    (z. B. die Farbfassung) genau gleich ausrichtet: (b_ausgerichtet, tf)."""
    sx, sy = a.shape[1] / b.shape[1], a.shape[0] / b.shape[0]
    tf = {"shape": a.shape[:2], "resize": not (abs(sx - 1) < 0.01 and abs(sy - 1) < 0.01),
          "shrink": b.shape[0] > a.shape[0], "M": None, "exact": False}
    b = match_size(a, b)
    if align == "none":
        return b, tf
    log(f"Richte aus ({align}) ...")
    warp = dc.align_global(a, b, align)
    log("  Warp: " + str(np.round(warp, 4).tolist()))
    if np.abs(warp[:, :2] - np.eye(2)).max() < 0.0005:
        M = np.float32([[1, 0, round(float(warp[0, 2]))], [0, 1, round(float(warp[1, 2]))]])
        log(f"  Nur Verschiebung -> gerundet auf dx={M[0, 2]:+.0f} dy={M[1, 2]:+.0f}")
        tf.update(M=M, exact=True)
        return cv2.warpAffine(b, M, (a.shape[1], a.shape[0]),
                              flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP, borderValue=0), tf
    tf["M"] = warp
    b = dc.apply_warp(b, warp, a.shape)
    return ((b > 127).astype(np.uint8)) * 255, tf


def apply_tf(img, tf):
    """Richtet ein Farbbild (BGR, weisses Papier) von B so aus wie prepare_pair_tf() die Tinte von B."""
    h, w = tf["shape"]
    if tf["resize"]:
        img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA if tf["shrink"] else cv2.INTER_LINEAR)
    else:
        canvas = np.full((h, w) + img.shape[2:], 255, np.uint8)
        hh, ww = min(h, img.shape[0]), min(w, img.shape[1])
        canvas[:hh, :ww] = img[:hh, :ww]
        img = canvas
    if tf["M"] is not None:
        img = cv2.warpAffine(img, tf["M"], (w, h), borderValue=(255, 255, 255),
                             flags=(cv2.INTER_NEAREST if tf["exact"] else cv2.INTER_LINEAR) | cv2.WARP_INVERSE_MAP)
    return img


def is_colored(img_bgr, min_frac=0.0005):
    """Hat das Bild nennenswert Farbe (nicht nur Grau/Schwarz)? Stichprobe jedes 4. Pixels."""
    if img_bgr is None or img_bgr.ndim != 3:
        return False
    s = img_bgr[::4, ::4]
    chroma = s.max(axis=2).astype(np.int16) - s.min(axis=2)
    return float((chroma > 40).mean()) > min_frac


# ----------------------------------------------------------------- Zonen
def make_zone(shape, zones, border):
    if not zones and border <= 0:
        return None
    z = np.zeros(shape, bool)
    h, w = shape
    for x, y, bw, bh in zones:
        z[max(0, y):max(0, y + bh), max(0, x):max(0, x + bw)] = True
    if border > 0:
        z[:border, :] = z[-border:, :] = True
        z[:, :border] = z[:, -border:] = True
    return z


# ----------------------------------------------------------------- Gruppen (fuer min-area und Liste)
def _group(mask, merge, s=4):
    """Fasst nahe beieinander liegende Pixel zu Gruppen zusammen (auf 1/s Aufloesung)."""
    h, w = mask.shape
    small = cv2.resize(mask.astype(np.uint8) * 255, (max(1, w // s), max(1, h // s)),
                       interpolation=cv2.INTER_AREA) > 0
    k = max(1, merge // s)
    small = cv2.dilate(small.astype(np.uint8), np.ones((2 * k + 1, 2 * k + 1), np.uint8))
    n, lab = cv2.connectedComponents(small, connectivity=8)
    return n, lab, s


def _pix_labels(mask, lab, s):
    ys, xs = np.nonzero(mask)
    l = lab[np.minimum(ys // s, lab.shape[0] - 1), np.minimum(xs // s, lab.shape[1] - 1)]
    return ys, xs, l


def filter_small(oa, ob, min_area, merge=25, both=None):
    """Entfernt Unterschiedsgruppen mit weniger als min_area Pixeln (in place).
    both: entfernte Pixel dort als 'gleich' eintragen (bleiben als graue Linie sichtbar)."""
    if min_area <= 0:
        return 0
    n, lab, s = _group(oa | ob, merge)
    parts = [_pix_labels(m, lab, s) for m in (oa, ob)]
    tot = sum(np.bincount(l, minlength=n) for _, _, l in parts)
    removed = int(((tot > 0) & (tot < min_area)).sum())
    for m, (ys, xs, l) in zip((oa, ob), parts):
        bad = tot[l] < min_area
        m[ys[bad], xs[bad]] = False
        if both is not None:
            both[ys[bad], xs[bad]] = True
    return removed


# ----------------------------------------------------------------- Stufe 3
def stage(progress, cancel, lo, hi, text):
    """Rueckruf fuer eine Rechenstufe: meldet Fortschritt lo..hi (0..1) und prueft auf Abbruch."""
    def tick(i, n):
        if cancel is not None and cancel():
            raise dc.Cancelled()
        if progress is not None:
            progress(lo + (hi - lo) * i / max(1, n), text)
    return tick


def run_compare(a, b, p, log=print, cancel=None, progress=None):
    """Vergleicht A mit ausgerichtetem B. Gibt Result zurueck.
    cancel(): True = abbrechen (loest dc.Cancelled aus); progress(anteil 0..1, text)."""
    def st(lo, hi, text):
        return stage(progress, cancel, lo, hi, text)
    zone = make_zone(a.shape, p.ignore, p.ignore_border)
    ac, bc = a, b
    if zone is not None:
        ac, bc = a.copy(), b.copy()
        ac[zone] = 0
        bc[zone] = 0
    if p.tiles.lower() == "auto":
        nx, ny = max(1, round(a.shape[1] / p.cell)), max(1, round(a.shape[0] / p.cell))
    else:
        nx, ny = (int(v) for v in p.tiles.lower().split("x"))
    log("Vergleiche ...")
    oa, ob, both, moved = dc.compare(ac, bc, p.tol, (nx, ny), p.max_shift, p.hatch, p.move,
                                     tick=st(0.0, 0.45, "Vergleiche Kacheln"))
    objs, found = (0, 0, 0, 0), []
    if p.obj_shift > 0:
        chk = acc = nsh = nrot = 0
        for grow, lo, hi in ((20, 0.45, 0.65), (8, 0.65, 0.75)):
            c_, a_, s_, r_, f_ = dc.refine_objects(ac, bc, oa, ob, both, moved, p.tol,
                                                   p.obj_shift, p.obj_rotate, grow=grow,
                                                   tick=st(lo, hi, "Suche verschobene Objekte"))
            chk, acc, nsh, nrot = chk + c_, acc + a_, nsh + s_, nrot + r_
            found += f_
        objs = (chk, acc, nsh, nrot)
        for grow, lo, hi in ((14, 0.75, 0.82), (6, 0.82, 0.88)):
            c_, a_, f_ = dc.refine_by_ink(ac, bc, oa, ob, both, moved, p.tol, p.obj_shift, grow=grow,
                                          tick=st(lo, hi, "Suche verschobene Objekte"))
            objs = (objs[0] + c_, objs[1] + a_, objs[2] + a_, objs[3])
            found += f_
            acc += a_
        c_, a_, f_ = dc.refine_by_glyph(ac, bc, oa, ob, both, moved, p.tol, p.obj_shift,
                                        tick=st(0.88, 0.95, "Suche verschobene Zeichen"))
        objs = (objs[0] + c_, objs[1] + a_, objs[2] + a_, objs[3])
        found += f_
        acc += a_
        chk, nsh = objs[0], objs[2]
        log(f"  Objekt-Suche: {chk} Unterschiedsbereiche geprueft, {acc} als verschoben/gedreht "
            f"erkannt ({nsh} nur Verschiebung, {nrot} mit Drehung)")
        if p.verbose:
            for x_, y_, w_, h_, dx_, dy_, ang_, bf_, af_ in found:
                log(f"    Objekt bei x={x_} y={y_} ({w_}x{h_}): Verschiebung dx={dx_:+d} dy={dy_:+d} px, "
                    f"Drehung {ang_:+.1f} Grad, Unterschied {bf_} -> {af_} px")
    st(0.95, 1.0, "Filtere kleine Unterschiede")(0, 1)
    if p.edge_noise:
        n_edge = dc.suppress_edge_noise(oa, ob, both)
        log(f"  Kantens\u00e4ume: {n_edge} px an gemeinsamen Linien ignoriert")
    if p.min_area > 0:
        # Unterdrueckte Reste bleiben als normale (graue) Linie sichtbar
        rem = filter_small(oa, ob, p.min_area, both=both)
        log(f"  Min-Area: {rem} kleine Unterschiedsgruppen (< {p.min_area} px) ignoriert")
    if zone is not None:
        both[zone] = a[zone] > 0
    log(f"  nur A: {int(oa.sum())} px   nur B: {int(ob.sum())} px   gemeinsam: {int(both.sum())} px")
    st(0.95, 1.0, "Fertig")(1, 1)
    return Result(a, b, oa, ob, both, moved, zone, nx, ny, objs, found)


def render_result(res):
    """Farbbild (BGR) des Vergleichs; ignorierte Zonen hellgelb hinterlegt."""
    out = dc.render(res.oa, res.ob, res.both, res.moved)
    if res.zone is not None:
        bg = res.zone & ~(res.oa | res.ob | res.both)
        out[bg] = (215, 240, 255)
    return out


# ----------------------------------------------------------------- Automatisch einstellen
def suggest_params(gray_a, gray_b, dpi=200, base=None, log=print, cancel=None):
    """Schlaegt Parameter fuer genau dieses Zeichnungspaar vor.

    Gemessen wird, was sich messen laesst:
      * Linienschwelle: Otsu-Schwelle der Grauwerte (trennt Papier und Linien).
      * Toleranz: Nach der Ausrichtung liegen gleiche Linien nicht exakt aufeinander (Scan, Rendering).
        Fuer B-Linien nahe einer A-Linie wird der Abstand gemessen; 90 % liegen innerhalb der Toleranz.
      * Mindestgroesse: aus der Linienstaerke (ein Punkt/Staubkorn ist kleiner als ein kurzes Linienstueck).
    Alle Suchbereiche (Kacheln, Verschiebungen, Schraffur) sind fuer 200 dpi gedacht und werden mit
    der Aufloesung skaliert. Was eine "relevante" Aenderung ist, kann das Programm nicht wissen.
    Gibt (Params, Liste von Erklaerungen) zurueck.
    """
    p = (base or Params()).copy()
    why = []
    small = lambda g: cv2.resize(g, None, fx=min(1.0, 2500 / max(g.shape)), fy=min(1.0, 2500 / max(g.shape)),
                                 interpolation=cv2.INTER_AREA)
    both = np.concatenate([small(gray_a).ravel(), small(gray_b).ravel()])
    otsu, _ = cv2.threshold(both.reshape(1, -1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    p.thr = int(np.clip(otsu, 90, 210))
    why.append(f"Linienschwelle {p.thr}: trennt Papier und Linien (gemessen).")
    k = max(0.25, dpi / 200.0)
    p.cell = int(np.clip(round(400 * k / 50) * 50, 150, 1200))
    p.max_shift = int(np.clip(round(30 * k), 5, 100))
    p.move = int(np.clip(round(100 * k), 20, 300))
    p.obj_shift = int(np.clip(round(40 * k), 8, 150))
    p.hatch = int(np.clip(round(16 * k), 4, 40))
    why.append(f"Suchbereiche für {dpi} dpi umgerechnet (Kachel {p.cell} px, Objekt-Verschiebung "
               f"{p.obj_shift} px, Schraffur {p.hatch} px).")
    if cancel is not None and cancel():
        raise dc.Cancelled()
    a = ink_from_gray(gray_a, p.thr)
    b = prepare_pair(a, ink_from_gray(gray_b, p.thr), p.align, lambda *_: None)
    if cancel is not None and cancel():
        raise dc.Cancelled()
    # Linienstaerke: doppelter Abstand der Linienmitte zum Rand
    dt_in = cv2.distanceTransform(a, cv2.DIST_L2, 3)
    core = dt_in[(dt_in > 0) & (cv2.dilate(dt_in, np.ones((3, 3), np.uint8)) == dt_in)]
    stroke = float(2 * np.median(core)) if core.size else 2.0
    # Toleranz: Anzahl abweichender Pixel je Toleranz. Zuerst faellt sie steil (Linien liegen nur
    # ungenau aufeinander), dann flach (echte Aenderungen bleiben). Gewaehlt wird der Knick.
    counts = []
    for t in range(0, 8):
        if t:
            kk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * t + 1, 2 * t + 1))
            ad, bd = cv2.dilate(a, kk), cv2.dilate(b, kk)
        else:
            ad, bd = a, b
        counts.append(int(((a > 0) & (bd == 0)).sum() + ((b > 0) & (ad == 0)).sum()))
    p.tol = next((t for t in range(1, 7) if counts[t + 1] > 0.6 * max(1, counts[t])), 6)
    drop = 100 * (1 - counts[p.tol] / max(1, counts[0]))
    why.append(f"Toleranz {p.tol} px: bis dahin verschwinden {drop:.0f} % der Abweichungen (nur ungenau "
               f"\u00fcbereinanderliegende Linien); mehr Toleranz w\u00fcrde vor allem echte \u00c4nderungen schlucken.")
    p.min_area = int(np.clip(round(3 * stroke * stroke + 8 * k), 5, 400))
    why.append(f"Mindestgröße {p.min_area} px: Linien sind etwa {stroke:.1f} px breit; kleinere Punkte "
               f"gelten als Staub.")
    log("Automatisch eingestellt: " + " ".join(why))
    return p, why
