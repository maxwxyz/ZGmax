"""Vektordaten aus PDF: Ebenen/Farben filtern, exakter Geometrievergleich und PDF-Text (ohne OCR).

Ein PDF kann echte Vektordaten (Linien, Kurven, Text) oder nur ein eingebettetes Bild enthalten.
inspect_pdf() zeigt, was vorliegt. Nur bei Vektordaten sind Vektorvergleich, Ebenen/Farben und PDF-Text sinnvoll.
Alle Bilder entstehen im Format der Rasterpipeline: uint8, 255 = Papier, 0 = Tinte (render_gray)
bzw. uint8 0/255 Tinte (vector_diff).
"""
import numpy as np
import cv2

try:
    import pymupdf
except ImportError:                                  # pragma: no cover
    pymupdf = None


def available():
    return pymupdf is not None


def _hex(c):
    if c is None:
        return None
    if isinstance(c, int):
        return "#%02x%02x%02x" % ((c >> 16) & 255, (c >> 8) & 255, c & 255)
    c = tuple(c)
    if len(c) == 1:
        c = c * 3
    if len(c) == 4:                                  # CMYK
        k = c[3]
        c = tuple(1 - min(1, v + k) for v in c[:3])
    return "#%02x%02x%02x" % tuple(int(round(max(0, min(1, v)) * 255)) for v in c[:3])


def _white(h):
    return h is None or all(int(h[i:i + 2], 16) >= 235 for i in (1, 3, 5))


def _bez(p0, p1, p2, p3, n=12):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2, p3 = (np.array([p.x, p.y]) for p in (p0, p1, p2, p3))
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3


def _pt(p):
    return np.array([p.x, p.y])


def page_items(path, page=1):
    """Zerlegt eine PDF-Seite in Elemente. Gibt (Elemente, (breite_pt, hoehe_pt)) zurueck.
    Element: dict kind ('l' Strecke, 'c' Kurve, 'f' Flaeche, 't' Text), pts (n x 2, in pt), w (Linienbreite),
    color ('#rrggbb'), layer (Name oder None), text."""
    if pymupdf is None:
        raise RuntimeError("PyMuPDF fehlt: pip install pymupdf")
    items = []
    with pymupdf.open(path) as doc:
        pg = doc[max(0, min(page, doc.page_count) - 1)]
        size = (pg.rect.width, pg.rect.height)
        try:
            drawings = pg.get_drawings()
        except Exception:
            drawings = []
        for d in drawings:
            layer = d.get("layer")
            lw = float(d.get("width") or 0.5)
            stroke = _hex(d.get("color")) if d.get("color") is not None else None
            fill = _hex(d.get("fill")) if d.get("fill") is not None else None
            poly = []
            for it in d["items"]:
                k = it[0]
                if k == "l":
                    pts = np.array([_pt(it[1]), _pt(it[2])])
                    kind = "l"
                elif k == "c":
                    pts = _bez(it[1], it[2], it[3], it[4])
                    kind = "c"
                elif k == "re":
                    r = it[1]
                    pts = np.array([[r.x0, r.y0], [r.x1, r.y0], [r.x1, r.y1], [r.x0, r.y1], [r.x0, r.y0]])
                    kind = "l"
                elif k == "qu":
                    q = it[1]
                    pts = np.array([_pt(q.ul), _pt(q.ur), _pt(q.lr), _pt(q.ll), _pt(q.ul)])
                    kind = "l"
                else:
                    continue
                poly.append(pts)
                if stroke is not None and not _white(stroke):
                    items.append(dict(kind=kind, pts=pts, w=lw, color=stroke, layer=layer, text=""))
            if fill is not None and not _white(fill) and poly:
                allp = np.vstack(poly)
                items.append(dict(kind="f", pts=allp, w=0, color=fill, layer=layer, text=""))
        try:
            td = pg.get_text("dict")
        except Exception:
            td = {"blocks": []}
        for b in td.get("blocks", []):
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    t = sp.get("text", "")
                    if not t.strip():
                        continue
                    x0, y0, x1, y1 = sp["bbox"]
                    items.append(dict(kind="t", pts=np.array([[x0, y0], [x1, y1]]), w=sp.get("size", 8),
                                      color=_hex(sp.get("color", 0)), layer=None, text=t))
    return items, size


def inspect_pdf(path, page=1):
    """Was steckt in der Seite? dict: vector (bool), paths, texts, layers {Name: Anzahl}, colors {#hex: Anzahl}."""
    items, size = page_items(path, page)
    layers, colors = {}, {}
    paths = texts = 0
    for it in items:
        if it["kind"] == "t":
            texts += 1
        else:
            paths += 1
        layers[it["layer"] or "(ohne Ebene)"] = layers.get(it["layer"] or "(ohne Ebene)", 0) + 1
        colors[it["color"]] = colors.get(it["color"], 0) + 1
    return dict(vector=paths >= 20, paths=paths, texts=texts, layers=layers, colors=colors, size=size)


def _keep(it, layers, colors):
    if layers is not None and (it["layer"] or "(ohne Ebene)") not in layers:
        return False
    if colors is not None and it["color"] not in colors:
        return False
    return True


def draw_items(items, shape, dpi, mask=None):
    """Zeichnet Elemente in eine Maske (uint8, 255 = Tinte)."""
    z = dpi / 72.0
    m = np.zeros(shape, np.uint8) if mask is None else mask
    texts = []
    for it in items:
        if it["kind"] == "t":
            texts.append(it)
            continue
        p = np.round(it["pts"] * z).astype(np.int32)
        if it["kind"] == "f":
            cv2.fillPoly(m, [p], 255)
        else:
            cv2.polylines(m, [p], False, 255, max(1, int(round(it["w"] * z))), cv2.LINE_8)
    if texts:
        from PIL import Image, ImageDraw
        import diffcore as dc
        im = Image.fromarray(m)
        d = ImageDraw.Draw(im)
        for it in texts:
            (x0, y0), (x1, y1) = it["pts"] * z
            d.text((x0, y0), it["text"], font=dc._font(max(6, int((y1 - y0) * 0.9))), fill=255)
        m[:] = np.asarray(im)
    return m


def _shape(size_a, size_b, dpi):
    z = dpi / 72.0
    return int(round(max(size_a[1], size_b[1]) * z)), int(round(max(size_a[0], size_b[0]) * z))


def render_gray(path, page, dpi, layers=None, colors=None, shape=None):
    """Gefiltertes Graubild (255 = Papier) fuer die Rasterpipeline."""
    items, size = page_items(path, page)
    items = [i for i in items if _keep(i, layers, colors)]
    shp = shape or (int(round(size[1] * dpi / 72)), int(round(size[0] * dpi / 72)))
    return 255 - draw_items(items, shp, dpi)


def _grid(items, cell):
    g = {}
    for i, it in enumerate(items):
        c = it["pts"].mean(axis=0)
        g.setdefault((int(c[0] // cell), int(c[1] // cell)), []).append(i)
    return g


def _same(a, b, tol):
    if a["kind"] != b["kind"]:
        return False
    if a["kind"] == "t":
        return a["text"] == b["text"] and np.abs(a["pts"] - b["pts"]).max() <= tol * 3
    if len(a["pts"]) != len(b["pts"]):
        if a["kind"] != "f":
            return False
        return abs(len(a["pts"]) - len(b["pts"])) < 3 and abs(a["pts"].mean(0) - b["pts"].mean(0)).max() <= tol * 2
    if np.abs(a["pts"] - b["pts"]).max() <= tol:
        return True
    return a["kind"] in ("l", "c") and np.abs(a["pts"] - b["pts"][::-1]).max() <= tol


def match_items(ia, ib, tol_pt):
    """Ordnet Elemente aus A denen aus B zu. Gibt (frei_a, frei_b, gemeinsam) als Indexlisten zurueck."""
    cell = max(2.0, tol_pt * 4)
    gb = _grid(ib, cell)
    used = set()
    only_a, both = [], []
    for i, a in enumerate(ia):
        c = a["pts"].mean(axis=0)
        cx, cy = int(c[0] // cell), int(c[1] // cell)
        hit = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in gb.get((cx + dx, cy + dy), ()):
                    if j not in used and _same(a, ib[j], tol_pt):
                        hit = j
                        break
                if hit is not None:
                    break
            if hit is not None:
                break
        if hit is None:
            only_a.append(i)
        else:
            used.add(hit)
            both.append(i)
    only_b = [j for j in range(len(ib)) if j not in used]
    return only_a, only_b, both


def vector_diff(pa, pb, page_a, page_b, dpi, filt_a=None, filt_b=None, tol_mm=0.05, log=print):
    """Exakter Vergleich der Geometrie. filt_x = (Ebenen oder None, Farben oder None).
    Gibt (a, b, oa, ob, both) zurueck (a, b uint8 0/255; Rest bool)."""
    fa = filt_a or (None, None)
    fb = filt_b or (None, None)
    ia, sa = page_items(pa, page_a)
    ib, sb = page_items(pb, page_b)
    ia = [i for i in ia if _keep(i, *fa)]
    ib = [i for i in ib if _keep(i, *fb)]
    log(f"Vektorvergleich: {len(ia)} Elemente in A, {len(ib)} in B")
    oa_i, ob_i, bo_i = match_items(ia, ib, tol_mm / 25.4 * 72.0)
    shp = _shape(sa, sb, dpi)
    a = draw_items(ia, shp, dpi)
    b = draw_items(ib, shp, dpi)
    oa = draw_items([ia[i] for i in oa_i], shp, dpi) > 0
    ob = draw_items([ib[i] for i in ob_i], shp, dpi) > 0
    both = draw_items([ia[i] for i in bo_i], shp, dpi) > 0
    both &= ~(oa | ob)
    log(f"  nur A: {len(oa_i)} Elemente   nur B: {len(ob_i)} Elemente   gleich: {len(bo_i)}")
    return a, b, oa, ob, both


def text_lines(path, page=1, dpi=200):
    """Text einer PDF-Seite als Zeilen (x0, y0, x1, y1, text) in Pixeln bei 'dpi' (wie das gerenderte Bild)."""
    if pymupdf is None:
        return []
    k = dpi / 72.0
    lines = {}
    with pymupdf.open(path) as doc:
        pg = doc[max(0, min(page, doc.page_count) - 1)]
        for x0, y0, x1, y1, w, blk, ln, _wn in pg.get_text("words"):
            lines.setdefault((blk, ln), []).append((x0, y0, x1, y1, w))
    out = []
    for words in lines.values():                    # je Wort eine eigene Zeile: Treffer exakt am Wort ...
        for x0, y0, x1, y1, w in words:
            out.append((x0 * k, y0 * k, x1 * k, y1 * k, w))
        if len(words) > 1:                          # ... und die ganze Zeile fuer Suchbegriffe mit Leerzeichen
            out.append((min(w[0] for w in words) * k, min(w[1] for w in words) * k,
                        max(w[2] for w in words) * k, max(w[3] for w in words) * k, " ".join(w[4] for w in words)))
    return out


def title_block_words(path, page=1, box=(0.5, 0.62)):
    """Woerter im Schriftfeld (rechts unten): Liste (x, y, text) in pt, in Lesereihenfolge."""
    if pymupdf is None:
        return []
    with pymupdf.open(path) as doc:
        pg = doc[max(0, min(page, doc.page_count) - 1)]
        W, H = pg.rect.width, pg.rect.height
        words = pg.get_text("words")
    out = [(w[0], w[1], w[4]) for w in words if w[0] >= box[0] * W and w[1] >= box[1] * H]
    return sorted(out, key=lambda t: (round(t[1] / 4), t[0]))


def pdf_words(path, page=1):
    """Eingebettete Textteile: Liste (x0, y0, x1, y1, text) in pt. Leer, wenn die Seite kein Text enthaelt."""
    items, _ = page_items(path, page)
    return [(*i["pts"][0], *i["pts"][1], i["text"]) for i in items if i["kind"] == "t"]


def fill_text(regs, words_a, words_b, dpi, log=print):
    """Schreibt den Text aus dem PDF in die Aenderungen (text_a / text_b), ohne OCR."""
    z = dpi / 72.0

    def inside(words, r):
        out = []
        for x0, y0, x1, y1, t in words:
            cx, cy = (x0 + x1) / 2 * z, (y0 + y1) / 2 * z
            if r["x"] - 5 <= cx <= r["x"] + r["w"] + 5 and r["y"] - 5 <= cy <= r["y"] + r["h"] + 5:
                out.append((round(y0), x0, t))
        return " ".join(t for _, _, t in sorted(out))
    n = 0
    for r in regs:
        r["text_a"], r["text_b"] = inside(words_a, r), inside(words_b, r)
        n += bool(r["text_a"] or r["text_b"])
    log(f"PDF-Text: {n} Aenderungen mit Text")
    return n
