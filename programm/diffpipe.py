"""Ablauf des Vergleichs als wiederverwendbare Funktionen (fuer Kommandozeile und Viewer).

Stufen:
  1. load_gray()      Datei laden -> Graubild (dunkelster RGB-Kanal)
  2. prepare_pair()   Ausschnitt, Groesse, globale Ausrichtung      (langsam, nur bei neuen Dateien/Ausrichtung)
  3. run_compare()    Kacheln, Verschiebung, Objekt-Suche, Filter   (Parameter des Vergleichs)
"""
from i18n import tr
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
    flatten: bool = False          # ungleichmaessiges Papier (Schatten, Flecken) vor der Schwelle ausgleichen
    edge_noise: bool = True        # 1-px-Saeume an gemeinsamen Linien nicht als Aenderung werten
    glyphs: bool = True            # Zeichenpruefung: aehnliche Ziffern/Buchstaben (1 -> 3) sicher erkennen
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


def ink_from_gray(gray, thr, flatten=False):
    """Tinte (255) wo dunkler als thr. flatten=True: vorher ungleichmaessiges Papier ausgleichen (Schatten,
    vergilbte oder fleckige Scans), damit die Schwelle ueberall gleich wirkt."""
    if flatten:
        gray = flatten_background(gray)
    return ((gray < thr).astype(np.uint8)) * 255


def background(gray, k=31):
    """Helligkeit des Papiers je Stelle (Linien herausgerechnet), auf 1/4 Groesse geschaetzt."""
    s = 4
    small = cv2.resize(gray, (max(1, gray.shape[1] // s), max(1, gray.shape[0] // s)), interpolation=cv2.INTER_AREA)
    bg = cv2.dilate(small, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))   # helle Umgebung = Papier
    bg = cv2.GaussianBlur(bg, (0, 0), k / 2)
    return cv2.resize(bg, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)


def flatten_background(gray):
    bg = background(gray).astype(np.float32)
    return np.clip(gray.astype(np.float32) * 255.0 / np.maximum(bg, 1.0), 0, 255).astype(np.uint8)


def uneven_background(gray):
    """Wie stark schwankt die Papierhelligkeit? (Grauwerte; ueber ~35 lohnt der Ausgleich)."""
    bg = background(gray[::2, ::2])
    lo, hi = np.percentile(bg, (2, 98))
    return float(hi - lo)


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
            from pdfopen import open_doc
            with open_doc(path) as d:
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
    log(tr("Suche Ausschnitt A in B (automatisch) ..."))
    box_b, score = dc.autofit(a, b_full)
    if box_b is None:
        log(tr("  Warnung: nichts gefunden, nutze ganzes Bild B"))
        return a, b_full, None
    log(tr("  gefunden: {}  (Uebereinstimmung {:.2f})").format(box_b, score))
    if score < 0.15:
        log(tr("  Warnung: schwache Uebereinstimmung - Ergebnis pruefen, evtl. groesseren Ausschnitt waehlen"))
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
    tf = {"shape": a.shape[:2], "src_shape": b.shape[:2], "resize": not (abs(sx - 1) < 0.01 and abs(sy - 1) < 0.01),
          "shrink": b.shape[0] > a.shape[0], "M": None, "exact": False}
    if align == "off":                               # gar nicht ausrichten: B liegt links oben auf A, wie es ist
        tf["resize"] = False
        canvas = np.zeros(a.shape, np.uint8)
        hh, ww = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
        canvas[:hh, :ww] = b[:hh, :ww]
        log(tr("Ohne Ausrichtung (Zeichnungen liegen übereinander, wie sie sind)."))
        return canvas, tf
    b = match_size(a, b)
    if align == "none":
        return b, tf
    log(tr("Richte aus ({}) ...").format(align))
    warp = dc.align_global(a, b, align)
    log(tr("  Warp: ") + str(np.round(warp, 4).tolist()))
    if np.abs(warp[:, :2] - np.eye(2)).max() < 0.0005:
        M = np.float32([[1, 0, round(float(warp[0, 2]))], [0, 1, round(float(warp[1, 2]))]])
        log(tr("  Nur Verschiebung -> gerundet auf dx={:+.0f} dy={:+.0f}").format(M[0, 2], M[1, 2]))
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
        canvas = np.full((h, w) + img.shape[2:], 255, np.uint8)        # Farbe (h, w, 3) oder grau (h, w)
        hh, ww = min(h, img.shape[0]), min(w, img.shape[1])
        canvas[:hh, :ww] = img[:hh, :ww]
        img = canvas
    if tf["M"] is not None:
        img = cv2.warpAffine(img, tf["M"], (w, h), borderValue=(255, 255, 255) if img.ndim == 3 else 255,
                             flags=(cv2.INTER_NEAREST if tf["exact"] else cv2.INTER_LINEAR) | cv2.WARP_INVERSE_MAP)
    return img


def map_points_tf(pts, tf, box=None, manual=None):
    """Punkte (x, y) aus dem Originalbild von B in die Lage, in der B nach Zuschnitt (box), prepare_pair_tf (tf)
    und manuellem Ausrichten (manual) angezeigt wird. Gegenstueck zu apply_tf fuer Koordinaten."""
    p = np.asarray(pts, np.float64).reshape(-1, 2).copy()
    if box is not None:
        p -= (box[0], box[1])
    if tf is not None:
        if tf["resize"]:
            h, w = tf["shape"]
            p *= (w / tf["src_shape"][1], h / tf["src_shape"][0])
        if tf["M"] is not None:
            M = np.vstack([np.asarray(tf["M"], np.float64), [0, 0, 1]])
            p = cv2.transform(p[None], np.linalg.inv(M)[:2])[0]    # warpAffine mit WARP_INVERSE_MAP
    if manual is not None:
        p = cv2.transform(p[None], np.asarray(manual, np.float64))[0]
    return p


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
    log(tr("Vergleiche ..."))
    oa, ob, both, moved = dc.compare(ac, bc, p.tol, (nx, ny), p.max_shift, p.hatch, p.move,
                                     tick=st(0.0, 0.45, tr("Vergleiche Kacheln")))
    objs, found = (0, 0, 0, 0), []
    if p.obj_shift > 0:
        chk = acc = nsh = nrot = 0
        for grow, lo, hi in ((20, 0.45, 0.65), (8, 0.65, 0.75)):
            c_, a_, s_, r_, f_ = dc.refine_objects(ac, bc, oa, ob, both, moved, p.tol,
                                                   p.obj_shift, p.obj_rotate, grow=grow,
                                                   tick=st(lo, hi, tr("Suche verschobene Objekte")))
            chk, acc, nsh, nrot = chk + c_, acc + a_, nsh + s_, nrot + r_
            found += f_
        objs = (chk, acc, nsh, nrot)
        for grow, lo, hi in ((14, 0.75, 0.82), (6, 0.82, 0.88)):
            c_, a_, f_ = dc.refine_by_ink(ac, bc, oa, ob, both, moved, p.tol, p.obj_shift, grow=grow,
                                          tick=st(lo, hi, tr("Suche verschobene Objekte")))
            objs = (objs[0] + c_, objs[1] + a_, objs[2] + a_, objs[3])
            found += f_
            acc += a_
        c_, a_, f_ = dc.refine_by_glyph(ac, bc, oa, ob, both, moved, p.tol, p.obj_shift,
                                        tick=st(0.88, 0.95, tr("Suche verschobene Zeichen")))
        objs = (objs[0] + c_, objs[1] + a_, objs[2] + a_, objs[3])
        found += f_
        acc += a_
        chk, nsh = objs[0], objs[2]
        log(tr("  Objekt-Suche: {} Unterschiedsbereiche geprueft, {} als verschoben/gedreht erkannt ({} nur Verschiebung, {} mit Drehung)").format(chk, acc, nsh, nrot))
        if p.verbose:
            for x_, y_, w_, h_, dx_, dy_, ang_, bf_, af_ in found:
                log(tr("    Objekt bei x={} y={} ({}x{}): Verschiebung dx={:+d} dy={:+d} px, Drehung {:+.1f} Grad, Unterschied {} -> {} px").format(x_, y_, w_, h_, dx_, dy_, ang_, bf_, af_))
    st(0.95, 0.96, tr("Filtere Kantens\u00e4ume"))(0, 1)
    hint = (oa | ob) if p.glyphs else None          # Abweichungen vor dem Kantenfilter: Hinweis fuer Zeichenpruefung
    if p.edge_noise:
        n_edge = dc.suppress_edge_noise(oa, ob, both)
        log(tr("  Kantensäume: {} px an gemeinsamen Linien ignoriert").format(n_edge))
    if p.glyphs:                     # nach dem Kantenfilter: Formabweichungen der Zeichen bleiben erhalten
        n_gl = dc.glyph_check(ac, bc, oa, ob, both, moved, max_h=max(30, int(round(p.cell * 0.15))),
                              tick=st(0.96, 0.99, tr("Pr\u00fcfe Zeichen")), hint=hint)
        del hint
        log(tr("  Zeichenprüfung: {} geänderte Zeichen").format(n_gl))
    st(0.99, 1.0, tr("Filtere kleine Unterschiede"))(0, 1)
    if p.min_area > 0:
        # Unterdrueckte Reste bleiben als normale (graue) Linie sichtbar
        rem = filter_small(oa, ob, p.min_area, both=both)
        log(tr("  Min-Area: {} kleine Unterschiedsgruppen (< {} px) ignoriert").format(rem, p.min_area))
    if zone is not None:
        both[zone] = a[zone] > 0
    log(tr("  nur A: {} px   nur B: {} px   gemeinsam: {} px").format(int(oa.sum()), int(ob.sum()), int(both.sum())))
    st(0.95, 1.0, tr("Fertig"))(1, 1)
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
    unev = max(uneven_background(gray_a), uneven_background(gray_b))
    p.flatten = unev > 35
    if p.flatten:
        why.append(tr("Papier ungleichmäßig hell (Schwankung {:.0f} Graustufen): wird vor dem Vergleich ausgeglichen.").format(unev))
        gray_a, gray_b = flatten_background(gray_a), flatten_background(gray_b)
    small = lambda g: cv2.resize(g, None, fx=min(1.0, 2500 / max(g.shape)), fy=min(1.0, 2500 / max(g.shape)),
                                 interpolation=cv2.INTER_AREA)
    both = np.concatenate([small(gray_a).ravel(), small(gray_b).ravel()])
    otsu, _ = cv2.threshold(both.reshape(1, -1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    p.thr = int(np.clip(otsu, 90, 210))
    why.append(tr("Linienschwelle {}: trennt Papier und Linien (gemessen).").format(p.thr))
    k = max(0.25, dpi / 200.0)
    p.cell = int(np.clip(round(400 * k / 50) * 50, 150, 1200))
    p.max_shift = int(np.clip(round(30 * k), 5, 100))
    p.move = int(np.clip(round(100 * k), 20, 300))
    p.obj_shift = int(np.clip(round(40 * k), 8, 150))
    p.hatch = int(np.clip(round(16 * k), 4, 40))
    why.append(tr("Suchbereiche für {} dpi umgerechnet (Kachel {} px, Objekt-Verschiebung {} px, Schraffur {} px).").format(dpi, p.cell, p.obj_shift, p.hatch))
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
    why.append(tr("Toleranz {} px: bis dahin verschwinden {:.0f} % der Abweichungen (nur ungenau übereinanderliegende Linien); mehr Toleranz würde vor allem echte Änderungen schlucken.").format(p.tol, drop))
    # Verzug: wie weit liegen einzelne Felder nach der Gesamtausrichtung noch daneben? (Stichprobe von Kacheln)
    shifts = []
    H, W = a.shape
    step = max(p.cell, int(max(H, W) / 7))
    search = int(np.clip(round(60 * k), 10, 150))
    for y in range(0, max(1, H - p.cell + 1), step):
        for x in range(0, max(1, W - p.cell + 1), step):
            ta = a[y:y + p.cell, x:x + p.cell]
            if int((ta > 0).sum()) < 300:
                continue
            tb = np.pad(b[y:y + p.cell, x:x + p.cell], search)[:ta.shape[0] + 2 * search, :ta.shape[1] + 2 * search]
            if tb.shape[0] < ta.shape[0] + 2 * search or tb.shape[1] < ta.shape[1] + 2 * search:
                continue
            bp = np.pad(b, search)[y:y + ta.shape[0] + 2 * search, x:x + ta.shape[1] + 2 * search]
            dx, dy = dc.best_shift(ta, bp, search)
            shifts.append(max(abs(dx), abs(dy)))
    if shifts:
        worst = float(np.percentile(shifts, 90))
        p.max_shift = int(np.clip(np.ceil(worst * 1.5) + 3, 5, 100))
        why.append(tr("Max. Kachelverschiebung {} px: einzelne Bereiche liegen nach dem Ausrichten bis etwa {:.0f} px "
                      "daneben (gemessen an {} Stellen).").format(p.max_shift, worst, len(shifts)))
    p.min_area = int(np.clip(round(3 * stroke * stroke + 8 * k), 5, 400))
    why.append(tr("Mindestgröße {} px: Linien sind etwa {:.1f} px breit; kleinere Punkte gelten als Staub.").format(p.min_area, stroke))
    log(tr("Automatisch eingestellt: ") + " ".join(why))
    return p, why
