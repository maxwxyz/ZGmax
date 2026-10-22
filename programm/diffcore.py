"""Rechenkern des Zeichnungsvergleichs (ohne Kommandozeile und Oberflaeche)."""
import argparse
import functools
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor

# sehr grosse Scans erlauben (muss vor "import cv2" gesetzt sein, OpenCV liest den Wert beim Laden)
os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(2 ** 40))

import cv2
import numpy as np

cv2.ocl.setUseOpenCL(False)
# OpenCV darf alle Kerne nutzen (cv2.setNumThreads(0) wuerde alles auf einen Kern zwingen)

WORKERS = max(1, min(16, os.cpu_count() or 1))
log = logging.getLogger("zeichnungsvergleich")


class DiffError(Exception):
    """Fehler mit verstaendlicher Meldung fuer den Anwender (Datei fehlt, Seite gibt es nicht, ...)."""


class Cancelled(Exception):
    """Berechnung wurde vom Anwender abgebrochen."""


def _tick(tick, i, n):
    """Fortschritt melden / Abbruch pruefen (tick kann None sein)."""
    if tick is not None:
        tick(i, n)


def _pmap(fn, items, window=None):
    """Wie map(fn, items), aber parallel in Threads (OpenCV gibt dabei den GIL frei).
    Ergebnisse kommen in der Reihenfolge von items zurueck. window = hoechstens so viele Aufgaben im Voraus
    (fuer grosse Zwischenergebnisse, begrenzt den Speicher); None = alle auf einmal (schnellste Verteilung)."""
    items = list(items)
    if WORKERS == 1 or len(items) < 2:
        yield from map(fn, items)
        return
    import itertools
    from collections import deque
    ex = ThreadPoolExecutor(WORKERS)
    it = iter(items)
    queue = deque(ex.submit(fn, x) for x in itertools.islice(it, window or len(items)))
    try:
        while queue:
            fut = queue.popleft()
            for x in it:                             # eine erledigt -> eine neue nachschieben
                queue.append(ex.submit(fn, x))
                break
            yield fut.result()
    finally:                                         # auch bei Abbruch: offene Aufgaben verwerfen
        ex.shutdown(wait=True, cancel_futures=True)


# ----------------------------------------------------------------- Laden
RASTER_EXT = {".png", ".jpg", ".jpeg", ".jpe", ".tif", ".tiff", ".bmp", ".webp",
              ".jp2", ".pbm", ".pgm", ".ppm", ".gif"}
VECTOR_EXT = {".pdf", ".svg", ".xps", ".oxps", ".epub"}      # werden mit PyMuPDF gerendert
CAD_EXT = {".dxf"}                                            # wird mit ezdxf nach PDF umgesetzt, dann gerendert
OUT_FORMATS = ("png", "jpg", "tif", "pdf", "bmp", "webp")


def _read_pdf_like(path, page, dpi):
    """PDF/SVG/XPS: Seite mit PyMuPDF auf weissem Grund in 'dpi' rendern -> BGR-Bild."""
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError:
            raise DiffError("Fuer PDF/SVG wird PyMuPDF benoetigt:  pip install pymupdf")
    doc = fitz.open(path)
    if page < 1 or page > doc.page_count:
        raise DiffError(f"{os.path.basename(path)}: Seite {page} existiert nicht (Seiten: 1-{doc.page_count})")
    if doc.page_count > 1:
        log.info(f"  {os.path.basename(path)}: {doc.page_count} Seiten, verwende Seite {page} "
              f"(mit --page-a / --page-b waehlbar)")
    pix = doc[page - 1].get_pixmap(dpi=dpi, alpha=False, colorspace=fitz.csRGB)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def _read_dxf(path, dpi):
    """DXF (Modellbereich) schwarz auf weiss rendern. Masseinheit mm; sehr grosse Zeichnungen werden auf
    hoechstens 1189 mm (A0) verkleinert."""
    try:
        import ezdxf
        from ezdxf.addons.drawing import Frontend, RenderContext, config, layout
        from ezdxf.addons.drawing.pymupdf import PyMuPdfBackend
        import pymupdf
    except ImportError:
        raise DiffError("F\u00fcr DXF werden ezdxf und PyMuPDF ben\u00f6tigt:  pip install ezdxf pymupdf")
    try:
        doc = ezdxf.readfile(path)
    except (IOError, ezdxf.DXFStructureError) as e:
        raise DiffError(f"DXF-Datei kann nicht gelesen werden: {os.path.basename(path)} ({e})")
    backend = PyMuPdfBackend()
    cfg = config.Configuration(background_policy=config.BackgroundPolicy.WHITE,
                               color_policy=config.ColorPolicy.BLACK)
    Frontend(RenderContext(doc), backend, config=cfg).draw_layout(doc.modelspace())
    page = layout.Page(0, 0, layout.Units.mm, margins=layout.Margins.all(5), max_width=1189, max_height=1189)
    data = backend.get_pdf_bytes(page, settings=layout.Settings(fit_page=True))
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        pix = pdf[0].get_pixmap(dpi=dpi, alpha=False, colorspace=pymupdf.csRGB)
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def _read_with_pil(path, page):
    """Fallback / mehrseitige TIFF / GIF: mit Pillow lesen -> BGR-Bild."""
    from PIL import Image, ImageSequence
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(path)
    n = getattr(im, "n_frames", 1)
    if page < 1 or page > n:
        raise DiffError(f"{os.path.basename(path)}: Seite {page} existiert nicht (Seiten: 1-{n})")
    if n > 1:
        log.info(f"  {os.path.basename(path)}: {n} Seiten, verwende Seite {page} "
              f"(mit --page-a / --page-b waehlbar)")
    im.seek(page - 1)
    rgba = im.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))      # Transparenz -> weiss
    rgb = Image.alpha_composite(bg, rgba).convert("RGB")
    return cv2.cvtColor(np.array(rgb), cv2.COLOR_RGB2BGR)


def read_image(path, page=1, dpi=200):
    """Liest ein Bild in beliebigem unterstuetzten Format als BGR-Array."""
    if not os.path.isfile(path):
        raise DiffError(f"Datei nicht gefunden: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext in VECTOR_EXT:
        return _read_pdf_like(path, page, dpi)
    if ext in CAD_EXT:
        return _read_dxf(path, dpi)
    if ext == ".dwg":
        raise DiffError("DWG kann nicht direkt gelesen werden. Bitte im CAD-Programm als DXF oder PDF speichern.")
    img = None
    if ext in {".tif", ".tiff", ".gif"} and page == 1:
        # Anzahl Seiten pruefen: bei mehrseitigen Dateien Pillow nutzen, damit die Wahl gilt
        try:
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = None
            with Image.open(path) as im:
                if getattr(im, "n_frames", 1) > 1:
                    return _read_with_pil(path, page)
        except Exception:
            pass
    if ext in {".tif", ".tiff", ".gif"} and page != 1:
        return _read_with_pil(path, page)
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:                                  # unbekannte Endung oder exotische Kompression
        try:
            img = _read_with_pil(path, page)
        except Exception as e:
            raise DiffError(f"Kann '{path}' nicht lesen ({e}).\n"
                     f"Unterstuetzt: {', '.join(sorted(RASTER_EXT | VECTOR_EXT))}")
    return img


def load_ink(path, thr, page=1, dpi=200):
    """Laedt Bild und liefert Tinten-Maske (uint8, 255 = Linie/Text/Farbe).

    Es wird der dunkelste RGB-Kanal benutzt: Alles, was in einem Kanal dunkel ist
    (schwarz, gelb, rot, blau, ...), zaehlt als Inhalt. Nur Weiss/Hellgrau ist Hintergrund.
    """
    img = read_image(path, page, dpi)
    low = img.min(axis=2)
    return ((low < thr).astype(np.uint8)) * 255


def resolve_output(out, fmt):
    """Bestimmt Ausgabedatei und -format aus --out und --format."""
    base, ext = os.path.splitext(out)
    ext = ext.lower().lstrip(".")
    if ext == "jpeg":
        ext = "jpg"
    if ext == "tiff":
        ext = "tif"
    if fmt:
        fmt = fmt.lower()
        return (base if ext else out) + "." + fmt, fmt
    if ext in OUT_FORMATS:
        return out, ext
    return out + ".png" if not ext else out, "png"


def save_output(img_bgr, path, fmt, dpi=200, quality=95):
    """Speichert das Ergebnisbild als png / jpg / tif / pdf / bmp / webp.

    Gibt (Pfad, Format) zurueck - bei Formatgrenzen kann auf PNG ausgewichen werden.
    """
    if fmt == "webp" and max(img_bgr.shape[:2]) > 16383:
        log.warning("  Warnung: WebP erlaubt max. 16383 px je Seite - speichere stattdessen als PNG")
        path, fmt = os.path.splitext(path)[0] + ".png", "png"
    if fmt in ("png", "bmp"):
        ok = cv2.imwrite(path, img_bgr)
    elif fmt == "webp":
        ok = cv2.imwrite(path, img_bgr, [cv2.IMWRITE_WEBP_QUALITY, quality])
    elif fmt == "jpg":
        ok = cv2.imwrite(path, img_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    else:                                            # tif, pdf -> Pillow
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        im = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        if fmt == "tif":
            im.save(path, compression="tiff_lzw", dpi=(dpi, dpi))
        else:
            im.save(path, "PDF", resolution=float(dpi))
        ok = True
    if not ok:
        raise DiffError(f"Konnte Ergebnis nicht speichern: {path}")
    return path, fmt


def parse_box(s):
    if not s:
        return None
    x, y, w, h = (int(v) for v in s.split(","))
    return x, y, w, h


def crop(m, box):
    if box is None:
        return m
    x, y, w, h = box
    return m[y:y + h, x:x + w]


def select_roi(m, title, ratio=None):
    """Interaktive Auswahl auf Tinten-Maske m -> Box (x,y,w,h) in Originalkoordinaten.

    ratio=None : freies Rechteck.
    ratio=w/h  : Seitenverhaeltnis gesperrt; Maus ziehen bestimmt Breite, Hoehe folgt.
    Der Rahmen ist blau. ENTER/Leertaste = OK, ESC = ganzes Bild.
    """
    s = 1400 / max(m.shape)
    small = cv2.resize(255 - m, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    st = {"p0": None, "p1": None, "drag": False}

    def cb(ev, x, y, flags, _):
        if ev == cv2.EVENT_LBUTTONDOWN:
            st.update(p0=(x, y), p1=(x, y), drag=True)
        elif ev == cv2.EVENT_MOUSEMOVE and st["drag"]:
            x0, y0 = st["p0"]
            if ratio is None:
                st["p1"] = (x, y)               # freies Rechteck
            else:
                h = int(abs(x - x0) / ratio)    # Hoehe folgt der Breite
                st["p1"] = (x, y0 + (h if y >= y0 else -h))
        elif ev == cv2.EVENT_LBUTTONUP:
            st["drag"] = False

    win = title if ratio is None else title + f"  [Seitenverhaeltnis fix {ratio:.3f}]"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, cb)
    while True:
        view = cv2.cvtColor(small, cv2.COLOR_GRAY2BGR)
        if st["p0"] and st["p1"]:
            cv2.rectangle(view, st["p0"], st["p1"], (255, 0, 0), 2)   # blau (BGR)
        cv2.imshow(win, view)
        k = cv2.waitKey(20) & 0xFF
        if k in (13, 32):
            break
        if k == 27:
            st["p0"] = None
            break
    cv2.destroyAllWindows()
    if not st["p0"] or st["p0"] == st["p1"]:
        return None
    (x0, y0), (x1, y1) = st["p0"], st["p1"]
    return tuple(int(v / s) for v in (min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)))


def autofit(a, b, work=3000):
    """Sucht den Bereich von Ausschnitt a im (ganzen) Bild b - unabhaengig von Massstab/dpi.

    Multi-Scale-Template-Matching auf verkleinerten, geglaetteten Masken.
    Liefert (box_in_b, score) mit box = (x, y, w, h) in Pixeln von b, Seitenverhaeltnis wie a.
    """
    wb = min(1.0, work / max(b.shape))
    B = cv2.resize(b, None, fx=wb, fy=wb, interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    B = cv2.GaussianBlur(B, (0, 0), 1.5)
    wa = 600 / max(a.shape)
    A0 = cv2.resize(a, None, fx=wa, fy=wa, interpolation=cv2.INTER_AREA).astype(np.float32) / 255

    def match(r):                      # r = B-Pixel pro A-Pixel
        f = r * wb / wa
        t = cv2.resize(A0, None, fx=f, fy=f,
                       interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_LINEAR)
        t = cv2.GaussianBlur(t, (0, 0), 1.5)
        if min(t.shape) < 60 or t.shape[0] > B.shape[0] or t.shape[1] > B.shape[1]:
            return None
        res = cv2.matchTemplate(B, t, cv2.TM_CCOEFF_NORMED)
        res = np.nan_to_num(res, nan=-1.0, posinf=-1.0, neginf=-1.0)
        # Fenster mit (fast) keinem Inhalt (leere Flaechen) ausschliessen
        ink = cv2.boxFilter(B, -1, (t.shape[1], t.shape[0]), normalize=True)
        ink = ink[t.shape[0] // 2:t.shape[0] // 2 + res.shape[0],
                  t.shape[1] // 2:t.shape[1] // 2 + res.shape[1]]
        res[ink < 0.5 * float(t.mean())] = -1.0
        _, mx, _, loc = cv2.minMaxLoc(res)
        return mx, loc, r

    best = None
    for r in np.geomspace(0.3, 3.5, 45):
        m = match(r)
        if m and (best is None or m[0] > best[0]):
            best = m
    if best is None:
        return None, 0.0
    for r in np.linspace(best[2] * 0.92, best[2] * 1.08, 17):
        m = match(r)
        if m and m[0] > best[0]:
            best = m
    mx, loc, r = best
    if abs(r - 1) < 0.015:
        r = 1.0     # gleicher Massstab: nicht skalieren (Interpolation erzeugt Moire auf Schraffur)
    box = (int(loc[0] / wb), int(loc[1] / wb), int(a.shape[1] * r), int(a.shape[0] * r))
    return box, float(mx)


# ----------------------------------------------------------------- Ausrichten
def _prep(m, scale, blur):
    s = cv2.resize(m, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    s = cv2.GaussianBlur(s.astype(np.float32) / 255.0, (0, 0), blur)
    return s


def align_global(a, b, mode="affine", work=2000):
    """Richtet b auf a aus (gleiche Groesse vorausgesetzt). Liefert warp (2x3, Vollaufloesung)."""
    scale = min(1.0, work / max(a.shape))
    fa, fb = _prep(a, scale, 2.0), _prep(b, scale, 2.0)

    warp = np.eye(2, 3, dtype=np.float32)
    # Start: Verschiebung per Phasenkorrelation
    try:
        (dx, dy), _ = cv2.phaseCorrelate(fa, fb)
        warp[0, 2], warp[1, 2] = dx, dy
    except cv2.error:
        pass

    motion = {"translation": cv2.MOTION_TRANSLATION,
              "euclidean": cv2.MOTION_EUCLIDEAN,
              "affine": cv2.MOTION_AFFINE}[mode]
    crit = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6)
    try:
        # inputMask/gaussFiltSize-Argumente sind je nach OpenCV-Version Pflicht
        _, warp = cv2.findTransformECC(fa, fb, warp, motion, crit, None, 5)
    except cv2.error as e:
        log.warning(f"  Warnung: ECC fehlgeschlagen ({e}); nutze nur Verschiebung")
    warp = warp.copy()
    warp[:, 2] /= scale        # Translation auf Vollaufloesung umrechnen
    return warp


def apply_warp(b, warp, shape):
    h, w = shape
    return cv2.warpAffine(b, warp, (w, h),
                          flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                          borderValue=0)


def best_shift(ta, tb_pad, m, min_gain=0.7):
    """Ganzzahlige Verschiebung (dx, dy) in +-m px, bei der Kachel ta am besten auf B passt.

    Exakte Suche (Quadratische Abweichung) statt Phasenkorrelation: rastet nicht auf
    periodischer Schraffur oder Text falsch ein. Eine Verschiebung wird nur uebernommen,
    wenn die Abweichung deutlich (min_gain) sinkt; bei Gleichstand gewinnt die kleinere.
    """
    if int((ta > 0).sum()) < 300:
        return 0, 0
    fa = cv2.GaussianBlur(ta.astype(np.float32) / 255, (0, 0), 1.0)
    fb = cv2.GaussianBlur(tb_pad.astype(np.float32) / 255, (0, 0), 1.0)
    res = cv2.matchTemplate(fb, fa, cv2.TM_SQDIFF)          # Form (2m+1, 2m+1)
    c0 = float(res[m, m])
    if c0 <= 0:
        return 0, 0
    yy, xx = np.mgrid[-m:m + 1, -m:m + 1]
    res = res + 0.02 * c0 * (xx ** 2 + yy ** 2) / float(m * m)   # kleine Verschiebungen bevorzugen
    iy, ix = np.unravel_index(int(res.argmin()), res.shape)
    if res[iy, ix] < min_gain * c0:
        return int(ix - m), int(iy - m)
    return 0, 0


def tile_shift(a, b, max_shift):
    """Feine Verschiebung eines Kachelpaares per Phasenkorrelation."""
    if a.sum() < 255 * 200 or b.sum() < 255 * 200:
        return 0.0, 0.0
    fa = cv2.GaussianBlur(a.astype(np.float32) / 255, (0, 0), 1.5)
    fb = cv2.GaussianBlur(b.astype(np.float32) / 255, (0, 0), 1.5)
    win = cv2.createHanningWindow(fa.shape[::-1], cv2.CV_32F)
    (dx, dy), resp = cv2.phaseCorrelate(fa, fb, win)
    if resp < 0.05 or abs(dx) > max_shift or abs(dy) > max_shift:
        return 0.0, 0.0
    return dx, dy


# ----------------------------------------------------------------- Vergleich
def hatch_region(m, period):
    """Maske der Schraffur-Flaechen: viele dicht parallel liegende Linien.

    Linien mit Abstand <= period verschmelzen nach dem Aufweiten zu einer Flaeche;
    nur Flaechen, die mindestens ~3 Linienabstaende breit/hoch sind, bleiben uebrig
    (einzelne Linien, Bemassung und Text fallen heraus).
    """
    r = max(1, period // 2)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    fat = cv2.dilate(m, k)
    s = max(3, 3 * period)
    reg = cv2.morphologyEx(fat, cv2.MORPH_OPEN, np.ones((s, s), np.uint8))
    return reg > 0


def diff_masks(a, b, tol, hatch=16):
    """Nur-A / Nur-B mit Toleranz (Pixel). Linien innerhalb 'tol' Pixel gelten als gleich.

    hatch > 0 (= max. Linienabstand der Schraffur in px): Dort, wo in BEIDEN Bildern
    eine Schraffur-Flaeche liegt und die Liniendichte etwa gleich ist, werden Abweichungen
    ignoriert (Schraffur ist nur phasenverschoben). Fehlt die Schraffur in einem Bild
    oder ist sie dichter/lockerer, bleibt der Unterschied markiert.
    """
    if tol > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * tol + 1, 2 * tol + 1))
        a_d, b_d = cv2.dilate(a, k), cv2.dilate(b, k)
    else:
        a_d, b_d = a, b
    only_a = (a > 0) & (b_d == 0)
    only_b = (b > 0) & (a_d == 0)
    if hatch > 0 and (only_a.any() or only_b.any()):
        both_h = hatch_region(a, hatch) & hatch_region(b, hatch)
        if both_h.any():
            w = (3 * hatch) | 1
            da = cv2.boxFilter(a.astype(np.float32) / 255, -1, (w, w))
            db = cv2.boxFilter(b.astype(np.float32) / 255, -1, (w, w))
            same = np.abs(da - db) <= 0.3 * np.maximum(da, db)
            sup = both_h & same
            only_a &= ~sup
            only_b &= ~sup
    both = (a > 0) & ~only_a | (b > 0) & ~only_b
    return only_a, only_b, both


def compare(a, b, tol, tiles, max_shift, hatch=16, move=100, tick=None):
    h, w = a.shape
    only_a = np.zeros(a.shape, bool)
    only_b = np.zeros(a.shape, bool)
    both = np.zeros(a.shape, bool)
    moved = np.zeros(a.shape, bool)
    nx, ny = tiles
    m = max_shift                       # kleine Feinkorrektur
    M = max(max_shift, move)            # grosse Suche nach verschobenen Bereichen
    bp = cv2.copyMakeBorder(b, M, M, M, M, cv2.BORDER_CONSTANT, value=0)

    def tile(ji):                       # Kacheln sind unabhaengig -> parallel
        j, i = ji
        x0, x1 = i * w // nx, (i + 1) * w // nx
        y0, y1 = j * h // ny, (j + 1) * h // ny
        ta = a[y0:y1, x0:x1]

        def piece(dx, dy):          # B-Inhalt bei (x+dx, y+dy) liegt auf A bei (x, y); keine Interpolation
            return bp[y0 + M + dy:y1 + M + dy, x0 + M + dx:x1 + M + dx]

        dx = dy = 0
        if nx * ny > 1 and m > 0:
            dx, dy = best_shift(ta, bp[y0 + M - m:y1 + M + m, x0 + M - m:x1 + M + m], m)
        oa, ob, bo = diff_masks(ta, piece(dx, dy), tol, hatch)
        cost0 = int(oa.sum() + ob.sum())
        mv = False
        # Ganzer Block verschoben (z.B. Tabelle/Ansicht um 80 px)? -> grosse Suche
        if move > 0 and nx * ny > 1 and cost0 > 0.05 * max(1, int((ta > 0).sum())):
            bdx, bdy = best_shift(ta, bp[y0:y1 + 2 * M, x0:x1 + 2 * M], M, min_gain=0.5)
            if bdx or bdy:
                oa2, ob2, bo2 = diff_masks(ta, piece(bdx, bdy), tol, hatch)
                if int(oa2.sum() + ob2.sum()) < 0.5 * cost0:
                    oa, ob, bo = oa2, ob2, bo2
                    mv = True
        return (y0, y1, x0, x1), oa, ob, bo, bool(dx or dy), mv

    shifted = nmoved = 0
    for k, ((y0, y1, x0, x1), oa, ob, bo, sh, mv) in enumerate(
            _pmap(tile, [(j, i) for j in range(ny) for i in range(nx)], window=4 * WORKERS)):
        _tick(tick, k + 1, nx * ny)
        shifted += sh
        if mv:
            moved[y0:y1, x0:x1] = True
            nmoved += 1
        only_a[y0:y1, x0:x1], only_b[y0:y1, x0:x1], both[y0:y1, x0:x1] = oa, ob, bo
    if nx * ny > 1:
        log.info(f"  Feinausrichtung: {shifted} von {nx * ny} Kacheln verschoben; "
              f"{nmoved} Kacheln als 'verschobener Bereich' erkannt")
    return only_a, only_b, both, moved


def suppress_edge_noise(only_a, only_b, both, touch=1.5):
    """Kantensaeume entfernen (in place): Unterschiede, die eine in beiden Zeichnungen vorhandene Linie direkt
    beruehren und selbst nur 1 px dick sind. Das sind Linien, die nur minimal versetzt oder dicker gerendert/
    gescannt wurden. Eigene Linien mit Abstand zur gemeinsamen Linie bleiben erhalten. Gibt die Pixelzahl zurueck."""
    if not (only_a.any() or only_b.any()) or not both.any():
        return 0
    near = cv2.distanceTransform((~both).view(np.uint8), cv2.DIST_L2, 3) <= touch
    removed = 0
    for m in (only_a, only_b):
        if not m.any():
            continue
        thin = cv2.distanceTransform(m.view(np.uint8), cv2.DIST_L2, 3) <= 1.0
        bad = m & thin & near
        removed += int(bad.sum())
        m &= ~bad
        both |= bad                                  # bleibt als (graue) gemeinsame Linie sichtbar
    return removed


def refine_objects(a, b, only_a, only_b, both, moved, tol, max_shift, max_rot,
                   grow=20, accept=0.5, step=0.5, rot_gain=0.7, tick=None):
    """Sucht fuer jedes verbliebene Unterschieds-Objekt eine kleine Verschiebung und Drehung.

    Beispiel: Ein Mass ist 4 px nach oben gerutscht. Die Kachel-Ausrichtung findet das nicht,
    weil in der Kachel auch unveraenderter Inhalt liegt. Hier wird jede zusammenhaengende
    Unterschiedsregion (Teile mit weniger als 'grow' px Abstand gehoeren zusammen) einzeln
    betrachtet: B wird im Bereich +-max_shift px verschoben und +-max_rot Grad gedreht, bis
    es zu A passt. Sinkt der Unterschied dadurch auf unter 'accept' (Standard 50 %), gilt das
    Objekt als nur verschoben/gedreht und wird gruen statt rot/blau gezeichnet.
    Aenderungen werden in only_a, only_b, both, moved direkt eingetragen.
    Gibt (geprueft, uebernommen, nur_verschoben, gedreht, liste) zurueck; liste enthaelt je
    Objekt (x, y, b, h, dx, dy, grad, unterschied_vorher, unterschied_nachher).
    Eine Drehung wird nur verwendet, wenn sie den Abstand zu A um mindestens 30 % stärker
    senkt als eine reine Verschiebung (rot_gain = 0.7); sonst gilt die reine Verschiebung.
    """
    diff = (only_a | only_b).astype(np.uint8)
    if max_shift <= 0 or not diff.any():
        return 0, 0, 0, 0, []
    found = []
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
    n, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(diff, k), connectivity=8)
    angles = [0.0]
    if max_rot > 0:
        a_list = np.arange(step, max_rot + 1e-9, step)
        angles += [s * v for v in a_list for s in (1, -1)]
    pad = int(max_shift)
    H, W = b.shape
    yy, xx = np.mgrid[-pad:pad + 1, -pad:pad + 1]

    def search(i):
        """Suche fuer Objekt i (liest nur a, b, diff, lab -> parallel moeglich).
        None = nicht geprueft, False = geprueft ohne Treffer, sonst Ergebnis zum Eintragen."""
        x, y, w, h, _ = st[i]
        comp = lab[y:y + h, x:x + w] == i
        before = int(diff[y:y + h, x:x + w][comp].sum())
        ta = a[y:y + h, x:x + w]
        if before < 40 or int((ta > 0)[comp].sum()) < 60 or w * h > 3_000_000:
            return None
        # B-Bereich mit Rand (ausserhalb des Bildes = leer)
        rb0 = np.zeros((h + 2 * pad, w + 2 * pad), np.uint8)
        sx0, sy0 = max(0, x - pad), max(0, y - pad)
        sx1, sy1 = min(W, x + w + pad), min(H, y + h + pad)
        rb0[sy0 - (y - pad):sy1 - (y - pad), sx0 - (x - pad):sx1 - (x - pad)] = b[sy0:sy1, sx0:sx1]
        fa = cv2.GaussianBlur(ta.astype(np.float32) / 255, (0, 0), 1.0)
        mask = comp.astype(np.float32)
        best, best0, c0 = None, None, None
        for ang in angles:
            if ang == 0.0:
                rb = rb0
            else:
                Mr = cv2.getRotationMatrix2D((rb0.shape[1] / 2, rb0.shape[0] / 2), ang, 1.0)
                rb = cv2.warpAffine(rb0, Mr, (rb0.shape[1], rb0.shape[0]), flags=cv2.INTER_LINEAR)
            fb = cv2.GaussianBlur(rb.astype(np.float32) / 255, (0, 0), 1.0)
            res = cv2.matchTemplate(fb, fa, cv2.TM_SQDIFF, mask=mask)
            res = np.nan_to_num(res, nan=1e30, posinf=1e30, neginf=1e30)
            if c0 is None:
                c0 = float(res[pad, pad])
                if c0 <= 0:
                    break
            # kleine Verschiebungen/Drehungen leicht bevorzugen
            res = res + 0.02 * c0 * ((xx ** 2 + yy ** 2) / float(pad * pad) + (ang / max(max_rot, 1)) ** 2)
            iy, ix = np.unravel_index(int(res.argmin()), res.shape)
            cost = (float(res[iy, ix]), ang, ix, iy, rb)
            if ang == 0.0:
                best0 = cost
            if best is None or cost[0] < best[0]:
                best = cost
        if best is None:
            return False
        # Eine Drehung nur, wenn sie deutlich besser ist als reine Verschiebung
        if best[1] != 0.0 and best0 is not None and best[0] > rot_gain * best0[0]:
            best = best0
        if best[1] == 0.0 and best[2] == pad and best[3] == pad:
            return False
        _, ang, ix, iy, rb = best
        tb = rb[iy:iy + h, ix:ix + w]
        if ang != 0.0:
            tb = ((tb > 127).astype(np.uint8)) * 255
        na, nb, nboth = diff_masks(ta, tb, tol, 0)
        after = int((na | nb)[comp].sum())
        if after >= accept * before:
            return False
        return comp, na, nb, nboth, (x, y, w, h, ix - pad, iy - pad, ang, before, after)

    # Objekte sind disjunkt (je eigenes Label) -> Eintragen in fester Reihenfolge, Ergebnis wie seriell
    checked = accepted = only_shift = rotated = 0
    for k, r in enumerate(_pmap(search, range(1, n))):
        _tick(tick, k + 1, n - 1)
        if r is None:
            continue
        checked += 1
        if r is False:
            continue
        comp, na, nb, nboth, item = r
        x, y, w, h = item[:4]
        sl = (slice(y, y + h), slice(x, x + w))
        only_a[sl][comp] = na[comp]
        only_b[sl][comp] = nb[comp]
        both[sl][comp] = nboth[comp]
        moved[sl][comp] |= nboth[comp]
        accepted += 1
        found.append(item)
        if item[6] != 0.0:
            rotated += 1
        else:
            only_shift += 1
    return checked, accepted, only_shift, rotated, found


def refine_by_glyph(a, b, only_a, only_b, both, moved, tol, max_shift, grow=12, cover=0.9, max_px=6000, tick=None):
    """Einzelne Tinten-Objekte (Ziffern, Zeichen, kleine Symbole) einzeln suchen.

    Liegen im selben Unterschiedsbereich auch echte Aenderungen, scheitert die Bereichs-Suche. Hier wird
    jedes zusammenhaengende Tintenobjekt von A, das Nur-A-Pixel enthaelt, fuer sich in B gesucht
    (Suchbereich +-max_shift). Es gilt als verschoben, wenn es zu 'cover' auf B-Tinte passt UND an der
    Fundstelle mindestens die Haelfte seiner Flaeche in B Nur-B-Pixel sind (dort ist also wirklich
    Neues). Gibt (geprueft, uebernommen, liste) zurueck.
    """
    diff = (only_a | only_b).astype(np.uint8)
    if max_shift <= 0 or not diff.any():
        return 0, 0, []
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * tol + 1, 2 * tol + 1)) if tol > 0 else None
    pad = int(max_shift)
    H, W = a.shape
    kg = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
    n, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(diff, kg), connectivity=8)
    checked = accepted = 0
    found = []
    for i in range(1, n):
        _tick(tick, i, n - 1)
        x, y, w, h, _ = st[i]
        if w * h > 2_500_000:
            continue
        reg = (a[y:y + h, x:x + w] > 0) & (lab[y:y + h, x:x + w] == i)
        nl, ll, ls, _ = cv2.connectedComponentsWithStats(reg.astype(np.uint8), connectivity=8)
        for j in range(1, nl):
            ox, oy, ow, oh, npx = ls[j]
            if npx < 12 or npx > max_px or ow > 400 or oh > 400:
                continue
            om = ll[oy:oy + oh, ox:ox + ow] == j
            gx, gy = x + ox, y + oy
            da = int((only_a[gy:gy + oh, gx:gx + ow] & om).sum())
            if da < 8:
                continue
            checked += 1
            x0, y0, x1, y1 = max(0, gx - pad), max(0, gy - pad), min(W, gx + ow + pad), min(H, gy + oh + pad)
            win = (b[y0:y1, x0:x1] > 0).astype(np.uint8)
            if k is not None:
                win = cv2.dilate(win, k)
            if win.shape[0] < oh or win.shape[1] < ow:
                continue
            res = cv2.matchTemplate(win.astype(np.float32), om.astype(np.float32), cv2.TM_CCORR) / float(npx)
            yy, xx = np.mgrid[0:res.shape[0], 0:res.shape[1]]
            dxg, dyg = xx + x0 - gx, yy + y0 - gy
            score = res - 0.02 * (dxg ** 2 + dyg ** 2) / float(pad * pad)
            iy, ix = np.unravel_index(int(score.argmax()), score.shape)
            sx, sy = int(dxg[iy, ix]), int(dyg[iy, ix])
            if (sx, sy) == (0, 0) or res[iy, ix] < cover:
                if DBG:
                    log.debug("T g rej cover " + " ".join(map(str, (gx, gy, ow, oh, npx, (sx, sy), round(float(res[iy, ix]), 2)))))
                continue
            tx, ty = gx + sx, gy + sy
            if tx < 0 or ty < 0 or tx + ow > W or ty + oh > H:
                continue
            tm = cv2.dilate(om.astype(np.uint8), k).astype(bool) if k is not None else om
            ob = only_b[ty:ty + oh, tx:tx + ow] & tm
            if int(ob.sum()) < 0.5 * da:
                if DBG:
                    log.debug("T g rej onlyb " + " ".join(map(str, (gx, gy, ow, oh, (sx, sy), da, int(ob.sum())))))
                continue
            sa = only_a[gy:gy + oh, gx:gx + ow] & om
            only_a[gy:gy + oh, gx:gx + ow][sa] = False
            only_b[ty:ty + oh, tx:tx + ow][ob] = False
            both[gy:gy + oh, gx:gx + ow][sa] = True
            moved[gy:gy + oh, gx:gx + ow][sa] = True
            both[ty:ty + oh, tx:tx + ow][ob] = True
            moved[ty:ty + oh, tx:tx + ow][ob] = True
            accepted += 1
            found.append((gx, gy, ow, oh, sx, sy, 0.0, da + int(ob.sum()), 0))
    return checked, accepted, found


DBG = False


def refine_by_ink(a, b, only_a, only_b, both, moved, tol, max_shift, grow=14, cover=0.88, min_px=12, tick=None):
    """Verschobene Objekte (Masse, Texte) auch dann erkennen, wenn Unveraendertes direkt daneben liegt.

    refine_objects() vergleicht ein ganzes Fenster; liegen im Fenster unveraenderte Linien, stoeren
    diese die Suche. Hier zaehlen NUR die Unterschiedspixel: Passen die Nur-A-Pixel nach einer
    Verschiebung (dx, dy) auf die Tinte von B UND die Nur-B-Pixel um (-dx, -dy) auf die Tinte von A
    (beide zu mindestens 'cover'), ist das Objekt nur verschoben. Es muessen auf beiden Seiten
    Unterschiede vorliegen und etwa gleich viele sein; ein echtes Loeschen oder Hinzufuegen
    bleibt deshalb erhalten.
    Gibt (geprueft, uebernommen, liste) zurueck; liste = (x, y, b, h, dx, dy, 0.0, vorher, nachher).
    """
    diff = (only_a | only_b).astype(np.uint8)
    if max_shift <= 0 or not diff.any():
        return 0, 0, []
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * tol + 1, 2 * tol + 1)) if tol > 0 else None
    pad = int(max_shift)
    H, W = a.shape
    kg = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
    n, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(diff, kg), connectivity=8)
    yy, xx = np.mgrid[-pad:pad + 1, -pad:pad + 1]
    checked = accepted = 0
    found = []
    for i in range(1, n):
        _tick(tick, i, n - 1)
        x, y, w, h, _ = st[i]
        if w * h > 2_500_000:
            continue
        comp = lab[y:y + h, x:x + w] == i
        pa = only_a[y:y + h, x:x + w] & comp
        pb = only_b[y:y + h, x:x + w] & comp
        na, nb = int(pa.sum()), int(pb.sum())
        if na < min_px or nb < min_px or min(na, nb) < 0.4 * max(na, nb):
            continue
        checked += 1
        x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)

        def window(m, dil=True):
            out = np.zeros((h + 2 * pad, w + 2 * pad), np.uint8)
            out[y0 - (y - pad):y1 - (y - pad), x0 - (x - pad):x1 - (x - pad)] = m[y0:y1, x0:x1]
            return cv2.dilate(out, k) if (dil and k is not None) else out
        a_raw, b_raw = window(a, False), window(b, False)
        bd = (cv2.dilate(b_raw, k) if k is not None else b_raw).astype(np.float32) / 255
        ad = (cv2.dilate(a_raw, k) if k is not None else a_raw).astype(np.float32) / 255
        ra = cv2.matchTemplate(bd, pa.astype(np.float32), cv2.TM_CCORR)       # Nur-A auf B-Tinte bei +s
        rb = cv2.matchTemplate(ad, pb.astype(np.float32), cv2.TM_CCORR)       # Nur-B auf A-Tinte bei +t
        rb = rb[::-1, ::-1]                                                   # t = -s
        score = ra / na + rb / nb
        score = score / 2 - 0.02 * (xx ** 2 + yy ** 2) / float(pad * pad)
        iy, ix = np.unravel_index(int(score.argmax()), score.shape)
        sx, sy = int(ix - pad), int(iy - pad)
        if (sx, sy) == (0, 0):
            continue
        sa = bd[pad + sy:pad + sy + h, pad + sx:pad + sx + w] > 0
        sb = ad[pad - sy:pad - sy + h, pad - sx:pad - sx + w] > 0
        ca, cb = int((pa & sa).sum()), int((pb & sb).sum())
        if ca < cover * na or cb < cover * nb:
            if DBG:
                log.debug("T rej cover " + " ".join(map(str, (x, y, w, h, (sx, sy), ca / na, cb / nb))))
            continue
        # Gegenprobe am ganzen Objekt: Die Tinte der betroffenen Zeichen/Linien (nicht nur die
        # Unterschiedspixel) muss nach der Verschiebung passen. So bleibt z. B. 0,1 -> 0,2 eine Aenderung.
        def obj_mask(raw, d):
            wm = np.zeros(raw.shape, np.uint8)
            wm[pad:pad + h, pad:pad + w] = d.astype(np.uint8)
            _, lb = cv2.connectedComponents((raw > 0).astype(np.uint8), connectivity=8)
            ids = np.unique(lb[wm > 0])
            return np.isin(lb, ids[ids > 0])

        def shifted(arr, dx_, dy_):
            out = np.zeros_like(arr)
            ys, xs = slice(max(0, -dy_), arr.shape[0] - max(0, dy_)), slice(max(0, -dx_), arr.shape[1] - max(0, dx_))
            yd, xd = slice(max(0, dy_), arr.shape[0] - max(0, -dy_)), slice(max(0, dx_), arr.shape[1] - max(0, -dx_))
            out[ys, xs] = arr[yd, xd]
            return out
        oa_, ob_ = obj_mask(a_raw, pa), obj_mask(b_raw, pb)
        if oa_.sum() > 40000 or ob_.sum() > 40000:
            if DBG:
                log.debug("T rej big " + " ".join(map(str, (x, y, w, h, int(oa_.sum()), int(ob_.sum())))))
            continue
        bs, as_ = shifted(bd, sx, sy) > 0, shifted(ad, -sx, -sy) > 0
        if (oa_ & bs).sum() < cover * oa_.sum() or (ob_ & as_).sum() < cover * ob_.sum():
            if DBG:
                log.debug("T rej obj " + " ".join(map(str, (x, y, w, h, (sx, sy), (oa_ & bs).sum() / oa_.sum(), (ob_ & as_).sum() / ob_.sum()))))
            continue
        sl = (slice(y, y + h), slice(x, x + w))
        res_a, res_b = pa & sa, pb & sb
        only_a[sl][res_a] = False
        only_b[sl][res_b] = False
        both[sl][res_a | res_b] = True
        moved[sl][res_a | res_b] = True
        accepted += 1
        found.append((x, y, w, h, sx, sy, 0.0, na + nb, (na - ca) + (nb - cb)))
    return checked, accepted, found


# Schriften fuer Legende, Bericht und Anmerkungen. Pillow sucht Namen ohne Pfad nur exakt (Gross-/Kleinschreibung),
# auf dem Mac heisst die Datei "Arial.ttf" im Unterordner Supplemental -> volle Pfade mit angeben.
FONT_CANDIDATES = ("arial.ttf", "segoeui.ttf",                                     # Windows
                   "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
                   "/System/Library/Fonts/Helvetica.ttc",                           # macOS
                   "DejaVuSans.ttf", "LiberationSans-Regular.ttf")                  # Linux


@functools.lru_cache(maxsize=None)
def _font_path():
    from PIL import ImageFont
    for name in FONT_CANDIDATES:
        try:
            ImageFont.truetype(name, 10)
            return name
        except OSError:
            continue
    return None


@functools.lru_cache(maxsize=256)
def _font(size):
    from PIL import ImageFont
    path = _font_path()
    if path:
        return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size)          # Pillow >= 10.1: skalierbare Standardschrift
    except TypeError:
        return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    """Bricht Text (auch ohne Leerzeichen, z.B. Dateinamen) auf max_w Pixel Breite um."""
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    return lines + [cur] if cur else lines


def add_legend(img, name_a, name_b, show_moved, info=""):
    """Haengt rechts ein weisses Legendenfeld an (Bildinhalt wird nicht ueberschrieben)."""
    from PIL import Image, ImageDraw
    h, w = img.shape[:2]
    s = min(4.0, max(0.7, h / 1500))              # Skalierung mit der Bildgroesse
    pw = int(760 * s)
    pad = int(30 * s)
    f_h, f_t, f_s = _font(int(34 * s)), _font(int(26 * s)), _font(int(22 * s))
    entries = [
        ((255, 0, 0), "Nur in A (rot)"),
        ((0, 0, 255), "Nur in B (blau)"),
        ((150, 150, 150), "In beiden Bildern gleich (grau)"),
    ]
    if show_moved:
        entries.append(((0, 170, 0), "Gleich, nur verschoben/gedreht (gruen)"))
    entries.append(((255, 255, 255), "Hintergrund (weiss)"))

    panel = Image.new("RGB", (pw, h), (255, 255, 255))
    d = ImageDraw.Draw(panel)
    d.line([(0, 0), (0, h)], fill=(0, 0, 0), width=max(2, int(3 * s)))
    y = pad
    d.text((pad, y), "Legende", font=f_h, fill=(0, 0, 0))
    y += int(f_h.size * 1.8)
    box = int(f_t.size * 1.3)
    for rgb, label in entries:                      # rgb hier in RGB-Reihenfolge
        d.rectangle([pad, y, pad + box, y + box], fill=rgb, outline=(0, 0, 0), width=max(1, int(s)))
        d.text((pad + box + int(16 * s), y + (box - f_t.size) // 2), label, font=f_t, fill=(0, 0, 0))
        y += int(box * 1.5)
    y += int(f_h.size * 0.8)
    for tag, name in (("A (Referenz):", name_a), ("B (Vergleich):", name_b)):
        d.text((pad, y), tag, font=f_t, fill=(0, 0, 0))
        y += int(f_t.size * 1.4)
        for ln in _wrap(d, name, f_s, pw - 2 * pad):
            d.text((pad, y), ln, font=f_s, fill=(60, 60, 60))
            y += int(f_s.size * 1.3)
        y += int(f_t.size * 0.8)
    if info:
        d.text((pad, y), "Einstellungen:", font=f_t, fill=(0, 0, 0))
        y += int(f_t.size * 1.4)
        for ln in _wrap(d, info, f_s, pw - 2 * pad):
            d.text((pad, y), ln, font=f_s, fill=(60, 60, 60))
            y += int(f_s.size * 1.3)

    out = np.full((h, w + pw, 3), 255, np.uint8)
    out[:, :w] = img
    out[:, w:] = np.array(panel)[:, :, ::-1]        # RGB -> BGR
    return out


def render(only_a, only_b, both, moved=None):
    out = np.full(only_a.shape + (3,), 255, np.uint8)       # BGR
    out[both] = (150, 150, 150)
    if moved is not None:
        out[both & moved] = (0, 170, 0)     # gruen: gleicher Inhalt, nur verschoben
    out[only_a] = (0, 0, 255)       # rot
    out[only_b] = (255, 0, 0)       # blau
    return out


