"""Auswertung des Vergleichs: Aenderungsliste, Markierung, Text-/Index-Abgleich (OCR), PDF-Bericht."""
import csv
import datetime as _dt
import os
import re
import sys

import cv2
import numpy as np

import diffcore as dc
import diffpipe as dp

MARK_BGR = (0, 140, 255)          # Orange: Rahmen und Nummern der Aenderungen
TYPE_LABEL = {"entfernt": "entfernt (nur A)", "neu": "neu (nur B)", "geaendert": "geaendert",
              "verschoben": "verschoben/gedreht"}


# ----------------------------------------------------------------- Aenderungsliste
def _boxes(mask_list, merge, s=4):
    """Gruppiert Masken; liefert je Gruppe Box und Pixelzahl je Maske."""
    union = mask_list[0].copy()
    for m in mask_list[1:]:
        union |= m
    n, lab, s = dp._group(union, merge, s)
    if n <= 1:
        return []
    cnt = []
    x0 = np.full(n, 1 << 30, np.int64)
    y0 = np.full(n, 1 << 30, np.int64)
    x1 = np.zeros(n, np.int64)
    y1 = np.zeros(n, np.int64)
    for m in mask_list:
        ys, xs, l = dp._pix_labels(m, lab, s)
        cnt.append(np.bincount(l, minlength=n))
        np.minimum.at(x0, l, xs)
        np.minimum.at(y0, l, ys)
        np.maximum.at(x1, l, xs)
        np.maximum.at(y1, l, ys)
    out = []
    for i in range(1, n):
        if x1[i] < x0[i]:
            continue
        out.append(dict(x=int(x0[i]), y=int(y0[i]), w=int(x1[i] - x0[i] + 1), h=int(y1[i] - y0[i] + 1),
                        counts=[int(c[i]) for c in cnt]))
    return out


def find_regions(res, merge=25, min_moved=30):
    """Liste der Aenderungen: rot/blau-Gruppen (entfernt/neu/geaendert) und gruene (verschoben)."""
    regs = []
    for r in _boxes([res.oa, res.ob], merge):
        ca, cb = r.pop("counts")
        typ = "entfernt" if cb <= 0.1 * ca else "neu" if ca <= 0.1 * cb else "geaendert"
        regs.append(dict(typ=typ, px_a=ca, px_b=cb, px_moved=0, **r))
    mv = res.moved & res.both
    for r in _boxes([mv], 10):
        c = r.pop("counts")[0]
        if c >= min_moved:
            regs.append(dict(typ="verschoben", px_a=0, px_b=0, px_moved=c, **r))
    regs.sort(key=lambda r: (r["y"] // 300, r["x"]))
    for i, r in enumerate(regs, 1):
        r["nr"] = i
        r["text_a"] = r["text_b"] = ""
        r["dim"] = r["dim_kind"] = ""
        r["checked"] = False
    return regs


# Pruefstatus je Aenderung (Pruefprotokoll). Aeltere Dateien kennen nur "checked" (geprueft ja/nein).
STATUS_LABEL = {"offen": "offen", "ok": "gepr\u00fcft", "abgelehnt": "abgelehnt"}
STATUS_COLORS = {"offen": "#f97316", "ok": "#16a34a", "abgelehnt": "#7c3aed"}


def reg_status(r):
    s = r.get("status")
    if s in STATUS_LABEL:
        return s
    return "ok" if r.get("checked") else "offen"


def set_status(r, status):
    r["status"] = status
    r["checked"] = status == "ok"


def review_text(r):
    """Kurzform fuer Listen/Bericht: 'geprueft: Kommentar'."""
    s = STATUS_LABEL[reg_status(r)]
    return s + (": " + r["comment"] if r.get("comment") else "")


def write_csv(path, regs, dpi=200, scale_n=1.0):
    mm = 25.4 / dpi * scale_n
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Nr", "Typ", "x_px", "y_px", "Breite_px", "Hoehe_px", "x_mm", "y_mm",
                    "Breite_mm", "Hoehe_mm", "Pixel_nur_A", "Pixel_nur_B", "Pixel_verschoben",
                    "Text_A", "Text_B", "Mass_Aenderung", "Beschreibung", "Status", "Kommentar"])
        for r in regs:
            w.writerow([r["nr"], TYPE_LABEL[r["typ"]], r["x"], r["y"], r["w"], r["h"],
                        f"{r['x'] * mm:.1f}".replace(".", ","), f"{r['y'] * mm:.1f}".replace(".", ","),
                        f"{r['w'] * mm:.1f}".replace(".", ","), f"{r['h'] * mm:.1f}".replace(".", ","),
                        r["px_a"], r["px_b"], r["px_moved"], r["text_a"], r["text_b"], r.get("dim", ""), r.get("desc", ""),
                        STATUS_LABEL[reg_status(r)], r.get("comment", "")])


# ----------------------------------------------------------------- Markierung
def draw_marks(img, regs, pad=12, types=None, cloud=False):
    """Zeichnet nummerierte Rahmen (oder Revisionswolken) um die Aenderungen (in place)."""
    h, w = img.shape[:2]
    t = max(2, int(max(h, w) / 2500))
    fs = max(0.8, max(h, w) / 5000)
    for r in regs:
        if types and r["typ"] not in types:
            continue
        x0, y0 = max(0, r["x"] - pad), max(0, r["y"] - pad)
        x1, y1 = min(w - 1, r["x"] + r["w"] + pad), min(h - 1, r["y"] + r["h"] + pad)
        if cloud:
            pts = cloud_points(x0, y0, x1, y1, max(8.0, 0.012 * max(h, w)))
            cv2.polylines(img, [np.round(np.array(pts)).astype(np.int32)], True, MARK_BGR, t, cv2.LINE_AA)
        else:
            cv2.rectangle(img, (x0, y0), (x1, y1), MARK_BGR, t)
        label = str(r["nr"])
        (tw, th), bl = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, fs, t)
        ty0 = y0 - th - bl - 2 * t
        if ty0 < 0:
            ty0 = y0
        cv2.rectangle(img, (x0, ty0), (x0 + tw + 2 * t + 4, ty0 + th + bl + 2 * t), MARK_BGR, -1)
        cv2.putText(img, label, (x0 + t + 2, ty0 + th + t), cv2.FONT_HERSHEY_SIMPLEX, fs,
                    (255, 255, 255), t, cv2.LINE_AA)
    return img


# ----------------------------------------------------------------- OCR (optional)
_engine = None


def ocr_available():
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


OCR_DIR = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "ocr")


def _ocr_engine():
    """Texterkennung: Fundstellen wie im Paket rapidocr-onnxruntime, Zeichen mit dem lateinischen Modell
    (Deutsch, Englisch, Umlaute, ß, °, ±), falls vorhanden; sonst das mitgelieferte Modell des Pakets."""
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except Exception:
            raise RuntimeError("OCR nicht verfuegbar: pip install rapidocr-onnxruntime")
        eng = RapidOCR()
        model, keys = os.path.join(OCR_DIR, "latin_rec.onnx"), os.path.join(OCR_DIR, "latin_dict.txt")
        if os.path.isfile(model) and os.path.isfile(keys):
            from rapidocr_onnxruntime.ch_ppocr_v3_rec import TextRecognizer
            eng.text_recognizer = TextRecognizer({"use_cuda": False, "model_path": model, "keys_path": keys,
                                                  "rec_img_shape": [3, 48, 320], "rec_batch_num": 6})
        _engine = eng
    return _engine


def ocr_language():
    return "Deutsch/Englisch" if os.path.isfile(os.path.join(OCR_DIR, "latin_rec.onnx")) else "Englisch"


def ocr_image(gray):
    """Liefert [(x, y, hoehe, text), ...] sortiert nach Zeilen (dunkle Schrift auf hellem Grund)."""
    result, _ = _ocr_engine()(gray)
    items = []
    for box, text, score in result or []:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append((min(xs), min(ys), (max(ys) - min(ys)), str(text).strip()))
    items.sort(key=lambda t: (round(t[1] / max(10, t[2])), t[0]))
    return items


def ocr_box(ink, box, pad=15, max_area=6_000_000):
    x, y, w, h = box
    H, W = ink.shape
    x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
    if (x1 - x0) * (y1 - y0) > max_area:
        return "(Bereich zu gross)"
    crop = 255 - ink[y0:y1, x0:x1]
    crop = cv2.copyMakeBorder(crop, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return " ".join(t[3] for t in ocr_image(crop)).strip()


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().casefold()


def text_diff(res, regs, log=print, max_regions=300):
    """Liest Text in geaenderten Bereichen aus A und B und traegt ihn in die Liste ein."""
    todo = [r for r in regs if r["typ"] != "verschoben"][:max_regions]
    log(f"Textvergleich (OCR) fuer {len(todo)} Bereiche ...")
    for i, r in enumerate(todo, 1):
        box = (r["x"], r["y"], r["w"], r["h"])
        r["text_a"] = ocr_box(res.a, box)
        r["text_b"] = ocr_box(res.b, box)
        if i % 20 == 0:
            log(f"  {i}/{len(todo)}")
    n = sum(1 for r in todo if _norm(r["text_a"]) != _norm(r["text_b"]))
    log(f"  Text unterschiedlich in {n} von {len(todo)} Bereichen")
    return regs


# ----------------------------------------------------------------- Massvergleich (Zahlen im Text)
_NUM = re.compile(r"(?:(?<![\w.,])|(?<=\bR)|(?<=\bM))[-+]?\d+(?:[.,]\d+)?")


def _numbers(text):
    """Zahlen eines Textes als Liste von (Zahl, Schreibweise), z. B. 'o12,5 +/-0.1' -> 12.5, 0.1."""
    out = []
    t = text.replace("\u00d8", " ").replace("\u2300", " ").replace("\u00b1", " ")
    for m in _NUM.finditer(t):
        s = m.group(0).lstrip("+")
        try:
            out.append((abs(float(s.replace(",", "."))), s.replace("-", "").replace(".", ",")))
        except ValueError:
            continue
    return out


def dim_changes(regs, log=print):
    """Vergleicht je Aenderung die Zahlen in Text A und B. Setzt r['dim'] (z. B. '12,5 -> 12,8') und
    r['dim_kind'] ('geaendert', 'neu', 'entfernt') oder '' (keine Massaenderung)."""
    n = 0
    for r in regs:
        r["dim"], r["dim_kind"] = "", ""
        na, nb = _numbers(r.get("text_a", "")), _numbers(r.get("text_b", ""))
        if not na and not nb:
            continue
        ra, rb = list(na), list(nb)
        for v in list(ra):                      # gleiche Werte heben sich auf
            hit = next((w for w in rb if abs(w[0] - v[0]) < 1e-9), None)
            if hit is not None:
                ra.remove(v)
                rb.remove(hit)
        if not ra and not rb:
            continue
        parts = []
        for i in range(max(len(ra), len(rb))):
            a = ra[i][1] if i < len(ra) else "\u2013"
            b = rb[i][1] if i < len(rb) else "\u2013"
            parts.append(f"{a} \u2192 {b}")
        r["dim"] = "; ".join(parts)
        r["dim_kind"] = "geaendert" if ra and rb else ("entfernt" if ra else "neu")
        n += 1
    log(f"Massvergleich: {n} Massaenderungen in {len(regs)} Bereichen")
    return n


# ----------------------------------------------------------------- Aenderungsindex (optional)
def _index_candidates(items):
    c = [t[3] for t in items if re.fullmatch(r"[A-Z]{1,2}", t[3])]
    return sorted(set(c), key=lambda s: (len(s), s))


def index_check(res, regs, log=print, box=(0.45, 0.70)):
    """Vergleicht das Schriftfeld (rechts unten) per OCR und prueft die Aenderungen auf Plausibilitaet.

    box = (Anteil Breite, Anteil Hoehe) des Schriftfeld-Bereichs rechts unten.
    Der Index wird heuristisch bestimmt (hoechster Grossbuchstaben-Index im Bereich).
    """
    H, W = res.a.shape
    x0, y0 = int(W * (1 - box[0])), int(H * box[1])
    sub = (slice(y0, H), slice(x0, W))
    ia = ocr_image(255 - res.a[sub])
    ib = ocr_image(255 - res.b[sub])
    ta, tb = {_norm(t[3]) for t in ia}, {_norm(t[3]) for t in ib}
    only_a = sorted(t for t in ta - tb if t)
    only_b = sorted(t for t in tb - ta if t)
    ca, cb = _index_candidates(ia), _index_candidates(ib)
    idx_a, idx_b = (ca[-1] if ca else "?"), (cb[-1] if cb else "?")
    outside = [r for r in regs if r["y"] + r["h"] < y0 or r["x"] + r["w"] < x0]
    n_chg = sum(1 for r in outside if r["typ"] != "verschoben")
    notes = []
    if idx_a != "?" and idx_a == idx_b and n_chg > 0:
        notes.append("WARNUNG: Zeichnung ist geaendert, aber der Index im Schriftfeld ist gleich geblieben.")
    if idx_a != idx_b and n_chg == 0:
        notes.append("WARNUNG: Index hat sich geaendert, aber im Zeichnungsfeld wurden keine Aenderungen gefunden.")
    if not notes:
        notes.append("Index und erkannte Aenderungen sind plausibel.")
    out = dict(index_a=idx_a, index_b=idx_b, only_a=only_a, only_b=only_b, changes=n_chg, notes=notes)
    log(f"Index-Abgleich: A={idx_a}  B={idx_b}  Aenderungen ausserhalb Schriftfeld: {n_chg}")
    for n in notes:
        log("  " + n)
    log(f"  Schriftfeld: {len(only_a)} Texte nur in A, {len(only_b)} Texte nur in B")
    return out


# ----------------------------------------------------------------- Anmerkungen
# Eine Anmerkung ist ein dict: type (text|number|approval|rect|arrow), x, y, x2, y2, text, nr, color, size.
#   text     Text, Ecke oben links bei (x, y)
#   number   nummerierter Kreis, Mitte bei (x, y), Nummer nr
#   approval Freigabe-Stempel (Rahmen mit Text), Ecke oben links bei (x, y)
#   rect     Rahmen (x, y)-(x2, y2)
#   arrow    Pfeil von (x, y) zur Spitze (x2, y2)
APPROVAL_TITLES = ("FREIGEGEBEN", "GEPRÜFT", "ABGELEHNT", "IN ARBEIT")
#   cloud     Revisionswolke um das Rechteck (x, y)-(x2, y2)
#   highlight Textmarker: halbtransparente Flaeche (x, y)-(x2, y2)
RECT_TYPES = ("rect", "cloud", "highlight")


def _ref(shape, ref):
    return ref if ref is not None else shape


def ann_unit(shape):
    return max(2.0, max(shape[:2]) / 2500)


def ann_text_h(shape, size):
    """Texthoehe in Bildpixeln (waechst mit der Blattgroesse)."""
    return 10 * ann_unit(shape) * size


def ann_line_w(shape, size):
    return max(2.0, 1.2 * ann_unit(shape) * size)


def stamp_font_h(th, nr):
    return th * (1.0 if len(str(nr)) <= 2 else 0.7)


def cloud_radius(shape, size):
    """Groesse der Boegen einer Revisionswolke (Bildpixel)."""
    return 4.0 * ann_unit(shape) * max(0.6, size)


def cloud_points(x0, y0, x1, y1, r):
    """Umriss einer Revisionswolke: Halbkreise nach aussen entlang des Rechtecks (Liste von Punkten)."""
    import math
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    pts = []
    for (ax, ay), (bx, by) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        L = math.hypot(bx - ax, by - ay)
        if L < 1e-6:
            continue
        ux, uy = (bx - ax) / L, (by - ay) / L
        nx, ny = uy, -ux                          # nach aussen (Umlauf im Uhrzeigersinn, y nach unten)
        n = max(1, round(L / (2 * r)))
        seg = L / n
        for i in range(n):
            cx, cy = ax + ux * seg * (i + 0.5), ay + uy * seg * (i + 0.5)
            rr = seg / 2
            for k in range(10):
                t = math.pi - math.pi * k / 9
                pts.append((cx + rr * (math.cos(t) * ux + math.sin(t) * nx),
                            cy + rr * (math.cos(t) * uy + math.sin(t) * ny)))
    return pts


def ann_lines(a):
    return (a.get("text") or " ").split("\n")


MEASURE_KINDS = {"dist": "L\u00e4nge", "poly": "Linienzug", "angle": "Winkel", "radius": "Radius", "area": "Fl\u00e4che"}


def circle_3pts(p, q, r):
    """Kreis durch drei Punkte: (cx, cy, radius) oder None (Punkte auf einer Linie)."""
    ax, ay = p
    bx, by = q
    cx, cy = r
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return ux, uy, ((ax - ux) ** 2 + (ay - uy) ** 2) ** 0.5


def measure_text(a, mm):
    """Messwert als Text. mm = Millimeter je Bildpixel (inkl. Massstab)."""
    import math
    pts = a.get("pts") or [[a["x"], a["y"]], [a["x2"], a["y2"]]]
    k = a.get("kind", "dist")
    if k in ("dist", "poly"):
        L = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))
        return f"{L * mm:.2f} mm"
    if k == "angle" and len(pts) >= 3:
        v1 = (pts[0][0] - pts[1][0], pts[0][1] - pts[1][1])
        v2 = (pts[2][0] - pts[1][0], pts[2][1] - pts[1][1])
        ang = abs(math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1])))
        return f"{ang:.2f}°"
    if k == "radius" and len(pts) >= 3:
        c = circle_3pts(*pts[:3])
        return "gerade" if c is None else f"R {c[2] * mm:.2f} mm  (Ø {2 * c[2] * mm:.2f})"
    if k == "area" and len(pts) >= 3:
        s = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                for i in range(len(pts)))
        return f"{abs(s) / 2 * mm * mm:.1f} mm²"
    return ""


def measure_geometry(a):
    """Zeichenhilfe: Liste (Typ, daten) -> ('line', [pts]), ('poly', [pts]), ('circle', (cx, cy, r))."""
    pts = [tuple(p) for p in (a.get("pts") or [[a["x"], a["y"]], [a["x2"], a["y2"]]])]
    k = a.get("kind", "dist")
    if k == "area":
        return [("poly", pts)]
    if k == "radius" and len(pts) >= 3:
        c = circle_3pts(*pts[:3])
        return [("circle", c)] if c else [("line", pts)]
    return [("line", pts)]


def ann_bounds(shape, a):
    """Umrandung (x0, y0, x1, y1) in Bildpixeln."""
    th = ann_text_h(shape, a["size"])
    x, y, t = a["x"], a["y"], a["type"]
    if t == "measure":
        pts = a.get("pts") or [[x, y], [a["x2"], a["y2"]]]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs) - th, min(ys) - th, max(xs) + th * 6, max(ys) + th * 1.5
    if t == "number":
        r = 0.95 * th
        return x - r, y - r, x + r, y + r
    if t in ("text", "approval"):
        lines = ann_lines(a)
        pad = 0.5 * th if t == "approval" else 0
        return (x, y, x + max(len(s) for s in lines) * 0.58 * th + 2 * pad,
                y + len(lines) * 1.25 * th + 2 * pad)
    lw = ann_line_w(shape, a["size"])
    if t == "cloud":
        lw += cloud_radius(shape, a["size"])
    return (min(x, a["x2"]) - lw, min(y, a["y2"]) - lw, max(x, a["x2"]) + lw, max(y, a["y2"]) + lw)


def draw_annotations(img_bgr, anns, offset=(0, 0), ref_shape=None, mm=None):
    """Brennt die Anmerkungen in das Bild (BGR) ein. offset = Ursprung des Bildausschnitts im Gesamtbild,
    ref_shape = Form des Gesamtbilds (bestimmt die Groesse von Text und Linien), mm = mm je Pixel (Messwerte)."""
    if not anns:
        return img_bgr
    import math
    from PIL import Image, ImageDraw
    shape = _ref(img_bgr.shape, ref_shape)
    ox, oy = offset
    im = Image.fromarray(np.ascontiguousarray(img_bgr[:, :, ::-1]))
    d = ImageDraw.Draw(im)
    for a in anns:
        th = ann_text_h(shape, a["size"])
        lw = ann_line_w(shape, a["size"])
        col = a["color"]
        x, y, x2, y2 = a["x"] - ox, a["y"] - oy, a["x2"] - ox, a["y2"] - oy
        t = a["type"]
        if t == "number":
            r = 0.95 * th
            d.ellipse([x - r, y - r, x + r, y + r], fill=col, outline="white", width=max(1, int(lw * 0.4)))
            d.text((x, y), str(a["nr"]), font=dc._font(max(6, int(stamp_font_h(th, a["nr"])))),
                   fill="white", anchor="mm")
        elif t == "text":
            d.multiline_text((x, y), a.get("text", ""), font=dc._font(max(6, int(th))), fill=col,
                             stroke_width=max(1, int(th / 12)), stroke_fill="white", spacing=int(th * 0.25))
        elif t == "approval":
            b = ann_bounds(shape, dict(a, x=x, y=y))
            d.rectangle([b[0], b[1], b[2], b[3]], fill="white", outline=col, width=max(2, int(lw * 1.3)))
            d.multiline_text((x + 0.5 * th, y + 0.5 * th), a.get("text", ""), font=dc._font(max(6, int(th))),
                             fill=col, spacing=int(th * 0.25))
        elif t == "measure":
            for gk, gd in measure_geometry(a):
                if gk == "circle":
                    cx, cy, cr = gd[0] - ox, gd[1] - oy, gd[2]
                    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], outline=col, width=int(lw))
                    d.line([(cx - lw * 3, cy), (cx + lw * 3, cy)], fill=col, width=int(lw))
                    d.line([(cx, cy - lw * 3), (cx, cy + lw * 3)], fill=col, width=int(lw))
                else:
                    pl = [(p[0] - ox, p[1] - oy) for p in gd]
                    if gk == "poly":
                        pl = pl + [pl[0]]
                    d.line(pl, fill=col, width=int(lw), joint="curve")
            for p in (a.get("pts") or [[a["x"], a["y"]], [a["x2"], a["y2"]]]):
                d.ellipse([p[0] - ox - lw * 1.6, p[1] - oy - lw * 1.6, p[0] - ox + lw * 1.6, p[1] - oy + lw * 1.6],
                          outline=col, width=max(1, int(lw * 0.7)))
            if mm:
                txt = measure_text(a, mm)
                pp = a.get("pts") or [[a["x"], a["y"]], [a["x2"], a["y2"]]]
                tx = sum(p[0] for p in pp) / len(pp) - ox
                ty = sum(p[1] for p in pp) / len(pp) - oy
                d.text((tx + 6, ty - th * 1.3), txt, font=dc._font(max(6, int(th))), fill=col,
                       stroke_width=max(1, int(th / 8)), stroke_fill="white")
        elif t == "rect":
            d.rectangle([min(x, x2), min(y, y2), max(x, x2), max(y, y2)], outline=col, width=int(lw))
        elif t == "cloud":
            pl = cloud_points(x, y, x2, y2, cloud_radius(shape, a["size"]))
            if pl:
                d.line(pl + [pl[0]], fill=col, width=int(lw), joint="curve")
        elif t == "highlight":
            layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
            ImageDraw.Draw(layer).rectangle([min(x, x2), min(y, y2), max(x, x2), max(y, y2)],
                                            fill=_rgba(col, 95))
            im = Image.alpha_composite(im.convert("RGBA"), layer).convert("RGB")
            d = ImageDraw.Draw(im)
        elif t == "arrow":
            ang = math.atan2(y2 - y, x2 - x)
            head = max(5 * lw, 0.8 * th)
            bx, by = x2 - head * 0.8 * math.cos(ang), y2 - head * 0.8 * math.sin(ang)
            d.line([(x, y), (bx, by)], fill=col, width=int(lw))
            d.polygon([(x2, y2),
                       (x2 - head * math.cos(ang - 0.4), y2 - head * math.sin(ang - 0.4)),
                       (x2 - head * math.cos(ang + 0.4), y2 - head * math.sin(ang + 0.4))], fill=col)
    img_bgr[:] = np.asarray(im)[:, :, ::-1]
    return img_bgr


def _rgba(col, alpha):
    col = col.lstrip("#")
    return tuple(int(col[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def upgrade_annotations(anns):
    """Alte Dateien: Typ 'stamp' heisst jetzt 'number'."""
    for a in anns:
        if a.get("type") == "stamp":
            a["type"] = "number"
        a.setdefault("x2", a["x"])
        a.setdefault("y2", a["y"])
        a.setdefault("text", "")
        a.setdefault("nr", 0)
    return anns


# ----------------------------------------------------------------- PDF-Bericht
def _thumb(img, maxw, maxh):
    h, w = img.shape[:2]
    f = min(maxw / w, maxh / h, 1.0)
    if f >= 1:
        return img
    out = cv2.resize(img, (max(1, int(w * f)), max(1, int(h * f))), interpolation=cv2.INTER_AREA)
    k = min(6.0, 1 / f)
    return (255 - np.clip((255 - out.astype(np.float32)) * k, 0, 255)).astype(np.uint8)


def _fit(img, w, h):
    ih, iw = img.shape[:2]
    f = min(w / iw, h / ih)
    interp = cv2.INTER_AREA if f < 1 else cv2.INTER_NEAREST
    out = cv2.resize(img, (max(1, int(iw * f)), max(1, int(ih * f))), interpolation=interp)
    if f < 1:
        k = min(4.0, 1 / f)
        out = (255 - np.clip((255 - out.astype(np.float32)) * k, 0, 255)).astype(np.uint8)
    return out


def build_report_raster(path, res, regs, name_a, name_b, dpi=200, info="", index=None, max_detail=40, log=print,
                        anns=None, scale_n=1.0):
    from PIL import Image, ImageDraw
    PW, PH, M = 1754, 1240, 60                       # A4 quer bei 150 dpi
    F_T, F_H, F_N, F_S = dc._font(44), dc._font(30), dc._font(24), dc._font(20)
    pages = []

    def new_page(title):
        im = Image.new("RGB", (PW, PH), "white")
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, PW, 90], fill=(34, 48, 68))
        d.text((M, 22), title, font=F_H, fill="white")
        d.text((PW - M - 220, 30), f"Seite {len(pages) + 1}", font=F_S, fill=(200, 210, 225))
        return im, d

    def paste(im, arr_bgr, x, y):
        rgb = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2RGB) if arr_bgr.ndim == 3 else arr_bgr
        im.paste(Image.fromarray(rgb), (x, y))

    # ---- Seite 1: Uebersicht
    im, d = new_page("ZGmax - Uebersicht")
    y = 120
    cnt = {k: sum(1 for r in regs if r["typ"] == k) for k in TYPE_LABEL}
    lines = [f"A (Referenz): {name_a}", f"B (Vergleich): {name_b}",
             f"Erstellt: {_dt.datetime.now():%d.%m.%Y %H:%M}   Aufloesung: {dpi} dpi",
             f"Aenderungen: {len(regs)}  (entfernt {cnt['entfernt']}, neu {cnt['neu']}, "
             f"geaendert {cnt['geaendert']}, verschoben {cnt['verschoben']})"]
    if index:
        lines.append(f"Index (vermutet): A = {index['index_a']}   B = {index['index_b']}")
        lines += index["notes"]
    for ln in lines:
        d.text((M, y), ln, font=F_N, fill=(20, 20, 20))
        y += 36
    ov = dc.render(res.oa, res.ob, res.both, res.moved)
    draw_marks(ov, regs)
    draw_annotations(ov, anns or [], mm=25.4 / dpi * scale_n)
    th = _thumb(ov, PW - 2 * M, PH - y - 80)
    paste(im, th, M + (PW - 2 * M - th.shape[1]) // 2, y + 10)
    d.text((M, PH - 50), info[:200], font=F_S, fill=(90, 90, 90))
    pages.append(im)

    # ---- Tabellenseiten
    mm = 25.4 / dpi * scale_n
    cols = [("Nr", 60), ("Typ", 270), ("Position (mm)", 250), ("Groesse (mm)", 220), ("Text A", 420), ("Text B", 420)]
    per = 22
    for p0 in range(0, len(regs), per):
        im, d = new_page("Aenderungsliste")
        x = M
        y = 115
        for name, wd in cols:
            d.text((x, y), name, font=F_N, fill=(34, 48, 68))
            x += wd
        d.line([(M, y + 34), (PW - M, y + 34)], fill=(34, 48, 68), width=2)
        y += 46
        for r in regs[p0:p0 + per]:
            vals = [str(r["nr"]), TYPE_LABEL[r["typ"]], f"{r['x'] * mm:.0f} / {r['y'] * mm:.0f}",
                    f"{r['w'] * mm:.1f} x {r['h'] * mm:.1f}", (("Ma\u00df: " + r["dim"]) if r.get("dim") else r["text_a"])[:34],
                    ("" if r.get("dim") else r["text_b"])[:34]]
            x = M
            for v, (_, wd) in zip(vals, cols):
                d.text((x, y), v, font=F_S, fill=(30, 30, 30))
                x += wd
            y += 46
            d.line([(M, y - 8), (PW - M, y - 8)], fill=(225, 228, 232), width=1)
        pages.append(im)

    # ---- Anmerkungen (Liste)
    if anns:
        label = {"text": "Text", "number": "Nummer", "approval": "Stempel", "rect": "Rahmen", "arrow": "Pfeil",
                 "measure": "Maß"}
        for p0 in range(0, len(anns), per):
            im, d = new_page("Anmerkungen")
            y = 115
            for a in anns[p0:p0 + per]:
                what = label.get(a["type"], a["type"])
                if a["type"] == "number":
                    what += f" {a['nr']}"
                txt = " / ".join(s for s in (a.get("text") or "").split("\n") if s)
                if a["type"] == "measure":
                    what = MEASURE_KINDS.get(a.get("kind", "dist"), "Maß")
                    txt = measure_text(a, mm) + ("  " + txt if txt else "")
                d.text((M, y), what, font=F_S, fill=(30, 30, 30))
                d.text((M + 260, y), f"{a['x'] * mm:.0f} / {a['y'] * mm:.0f} mm", font=F_S, fill=(30, 30, 30))
                d.text((M + 520, y), txt[:70], font=F_S, fill=(30, 30, 30))
                y += 46
                d.line([(M, y - 8), (PW - M, y - 8)], fill=(225, 228, 232), width=1)
            pages.append(im)

    # ---- Detailseiten: A | B | Vergleich
    det = [r for r in regs][:max_detail]
    log(f"Bericht: {len(det)} Detailansichten ...")
    PWI = (PW - 2 * M - 40) // 3
    PHI = 470
    for p0 in range(0, len(det), 2):
        im, d = new_page("Details: A | B | Vergleich")
        y = 115
        for r in det[p0:p0 + 2]:
            pad = max(40, int(0.25 * max(r["w"], r["h"])))
            H, W = res.a.shape
            x0, y0 = max(0, r["x"] - pad), max(0, r["y"] - pad)
            x1, y1 = min(W, r["x"] + r["w"] + pad), min(H, r["y"] + r["h"] + pad)
            sl = (slice(y0, y1), slice(x0, x1))
            ca, cb = 255 - res.a[sl], 255 - res.b[sl]
            cd = dc.render(res.oa[sl], res.ob[sl], res.both[sl], res.moved[sl])
            if anns:
                near = [a for a in anns if (lambda b: b[2] >= x0 and b[0] <= x1 and b[3] >= y0 and b[1] <= y1)(
                    ann_bounds(res.a.shape, a))]
                draw_annotations(cd, near, (x0, y0), res.a.shape, mm)
            d.text((M, y), f"{r['nr']}  {TYPE_LABEL[r['typ']]}   Position {r['x'] * mm:.0f} / {r['y'] * mm:.0f} mm", font=F_N,
                   fill=(20, 20, 20))
            if r.get("desc"):
                d.text((M, y + 50), r["desc"][:90], font=F_S, fill=(30, 30, 30))
            if r.get("dim"):
                d.text((M, y + 32), f"Ma\u00df {r['dim'][:70]}", font=F_N, fill=(180, 20, 40))
            elif r["text_a"] or r["text_b"]:
                d.text((M, y + 32), f"Text: {r['text_a'][:60]}  ->  {r['text_b'][:60]}", font=F_S, fill=(90, 90, 90))
            for i, (img, lab) in enumerate(((ca, "A"), (cb, "B"), (cd, "Vergleich"))):
                px = M + i * (PWI + 20)
                fitted = _fit(img, PWI, PHI)
                paste(im, fitted, px, y + 70)
                d.rectangle([px, y + 70, px + PWI, y + 70 + PHI], outline=(190, 195, 205))
                d.text((px + 8, y + 74), lab, font=F_S, fill=(90, 90, 90))
            y += PHI + 130
        pages.append(im)

    pages[0].save(path, "PDF", save_all=True, append_images=pages[1:], resolution=150)
    return len(pages)


def build_report(path, res, regs, name_a, name_b, dpi=200, info="", index=None, max_detail=40, log=print,
                 anns=None, scale_n=1.0):
    """PDF-Bericht mit echtem Text (durchsuchbar) und hochaufgeloesten Bildern. Ohne PyMuPDF: Rasterbericht."""
    try:
        import pymupdf
    except ImportError:
        log("Hinweis: PyMuPDF fehlt, es wird ein Rasterbericht erzeugt (pip install pymupdf).")
        return build_report_raster(path, res, regs, name_a, name_b, dpi, info, index, max_detail, log, anns, scale_n)
    PW, PH, M = 842.0, 595.0, 30.0                   # A4 quer in Punkt
    doc = pymupdf.open()
    mm = 25.4 / dpi * scale_n
    NAVY, GREY, DARK = (34 / 255, 48 / 255, 68 / 255), (0.4, 0.4, 0.4), (0.1, 0.1, 0.1)
    font = pymupdf.Font("helv")

    def clean(s):
        return str(s).encode("cp1252", "replace").decode("cp1252").replace("\n", " ")

    def fit_text(s, width, size):
        s = clean(s)
        if font.text_length(s, size) <= width:
            return s
        while s and font.text_length(s + "...", size) > width:
            s = s[:-1]
        return s + "..."

    def page(title):
        pg = doc.new_page(width=PW, height=PH)
        pg.draw_rect(pymupdf.Rect(0, 0, PW, 40), color=None, fill=NAVY)
        pg.insert_text((M, 26), clean(title), fontsize=16, fontname="helv", color=(1, 1, 1))
        pg.insert_text((PW - M - 50, 26), f"Seite {doc.page_count}", fontsize=10, fontname="helv", color=(0.8, 0.84, 0.9))
        return pg

    def put(pg, img, rect, maxpx):
        h, w = img.shape[:2]
        f = min(maxpx / max(w, h), 1.0)
        if f < 1:
            img = _fit(img, int(w * f), int(h * f))
        ok, buf = cv2.imencode(".png", img)
        if ok:
            pg.insert_image(rect, stream=buf.tobytes(), keep_proportion=True)

    def row_text(pg, y, items, size=9):
        for x, w, s, col in items:
            pg.insert_text((x, y), fit_text(s, w - 4, size), fontsize=size, fontname="helv", color=col)

    # ---- Uebersicht
    pg = page("ZGmax - \u00dcbersicht")
    cnt = {k: sum(1 for r in regs if r["typ"] == k) for k in TYPE_LABEL}
    lines = [f"A (Referenz): {name_a}", f"B (Vergleich): {name_b}",
             f"Erstellt: {_dt.datetime.now():%d.%m.%Y %H:%M}   Aufl\u00f6sung: {dpi} dpi",
             f"\u00c4nderungen: {len(regs)}  (entfernt {cnt['entfernt']}, neu {cnt['neu']}, "
             f"ge\u00e4ndert {cnt['geaendert']}, verschoben {cnt['verschoben']})"]
    if index:
        lines.append(f"Index (vermutet): A = {index['index_a']}   B = {index['index_b']}")
        lines += list(index["notes"])
    y = 62.0
    for ln in lines:
        pg.insert_text((M, y), fit_text(ln, PW - 2 * M, 11), fontsize=11, fontname="helv", color=DARK)
        y += 16
    ov = dc.render(res.oa, res.ob, res.both, res.moved)
    draw_marks(ov, regs)
    draw_annotations(ov, anns or [], mm=mm)
    ov = _thumb(ov, 6000, 3000)
    put(pg, ov, pymupdf.Rect(M, y + 4, PW - M, PH - 34), 6000)
    pg.insert_text((M, PH - 16), fit_text(info, PW - 2 * M, 8), fontsize=8, fontname="helv", color=GREY)

    # ---- Aenderungsliste als Text
    cols = [("Nr", 28), ("Typ", 78), ("Position (mm)", 82), ("Gr\u00f6\u00dfe (mm)", 78), ("Text A", 140),
            ("Text B", 140), ("Beschreibung", 236)]
    per = 27
    for p0 in range(0, len(regs), per):
        pg = page("\u00c4nderungsliste")
        x, y = M, 62.0
        for name, wd in cols:
            pg.insert_text((x, y), name, fontsize=9.5, fontname="helv", color=NAVY)
            x += wd
        pg.draw_line((M, y + 4), (PW - M, y + 4), color=NAVY, width=1)
        y += 18
        for r in regs[p0:p0 + per]:
            dim = r.get("dim")
            vals = [str(r["nr"]), TYPE_LABEL[r["typ"]], f"{r['x'] * mm:.0f} / {r['y'] * mm:.0f}",
                    f"{r['w'] * mm:.1f} x {r['h'] * mm:.1f}", r.get("text_a", ""), r.get("text_b", ""),
                    ("Ma\u00df " + dim + "  " if dim else "") + r.get("desc", "")
                    + (("  [" + review_text(r) + "]") if (r.get("status") or r.get("checked")) else "")]
            x = M
            items = []
            for v, (_, wd) in zip(vals, cols):
                items.append((x, wd, v, DARK))
                x += wd
            row_text(pg, y, items)
            y += 7
            pg.draw_line((M, y), (PW - M, y), color=(0.88, 0.89, 0.91), width=0.5)
            y += 12

    # ---- Anmerkungen als Text
    if anns:
        label = {"text": "Text", "number": "Nummer", "approval": "Stempel", "rect": "Rahmen", "arrow": "Pfeil",
                 "measure": "Ma\u00df"}
        for p0 in range(0, len(anns), per):
            pg = page("Anmerkungen")
            y = 62.0
            for a in anns[p0:p0 + per]:
                what = label.get(a["type"], a["type"])
                if a["type"] == "number":
                    what += f" {a['nr']}"
                txt = " / ".join(s for s in (a.get("text") or "").split("\n") if s)
                if a["type"] == "measure":
                    what = MEASURE_KINDS.get(a.get("kind", "dist"), "Ma\u00df")
                    txt = measure_text(a, mm) + ("  " + txt if txt else "")
                row_text(pg, y, [(M, 120, what, DARK), (M + 130, 120, f"{a['x'] * mm:.0f} / {a['y'] * mm:.0f} mm", DARK),
                                 (M + 260, PW - 2 * M - 260, txt, DARK)])
                y += 7
                pg.draw_line((M, y), (PW - M, y), color=(0.88, 0.89, 0.91), width=0.5)
                y += 12

    # ---- Details A | B | Vergleich (volle Aufloesung, max. 1600 px je Bild)
    det = list(regs)[:max_detail]
    log(f"Bericht: {len(det)} Detailansichten ...")
    gap = 10.0
    pw_ = (PW - 2 * M - 2 * gap) / 3
    ph_ = 205.0
    for p0 in range(0, len(det), 2):
        pg = page("Details: A | B | Vergleich")
        y = 62.0
        for r in det[p0:p0 + 2]:
            pad = max(40, int(0.25 * max(r["w"], r["h"])))
            H, W = res.a.shape
            x0, y0 = max(0, r["x"] - pad), max(0, r["y"] - pad)
            x1, y1 = min(W, r["x"] + r["w"] + pad), min(H, r["y"] + r["h"] + pad)
            sl = (slice(y0, y1), slice(x0, x1))
            ca, cb = 255 - res.a[sl], 255 - res.b[sl]
            cd = dc.render(res.oa[sl], res.ob[sl], res.both[sl], res.moved[sl])
            if anns:
                near = [a for a in anns if (lambda b: b[2] >= x0 and b[0] <= x1 and b[3] >= y0 and b[1] <= y1)(
                    ann_bounds(res.a.shape, a))]
                draw_annotations(cd, near, (x0, y0), res.a.shape, mm)
            pg.insert_text((M, y), fit_text(f"{r['nr']}  {TYPE_LABEL[r['typ']]}   Position "
                                           f"{r['x'] * mm:.0f} / {r['y'] * mm:.0f} mm", PW - 2 * M, 11),
                           fontsize=11, fontname="helv", color=DARK)
            y += 14
            sub = []
            if r.get("dim"):
                sub.append("Ma\u00df " + r["dim"])
            elif r.get("text_a") or r.get("text_b"):
                sub.append(f"Text: {r.get('text_a', '')}  ->  {r.get('text_b', '')}")
            if r.get("desc"):
                sub.append("Beschreibung: " + r["desc"])
            if r.get("status") or r.get("checked") or r.get("comment"):
                sub.append("Pr\u00fcfung: " + review_text(r))
            for s in sub:
                pg.insert_text((M, y), fit_text(s, PW - 2 * M, 9.5), fontsize=9.5, fontname="helv",
                               color=(0.7, 0.08, 0.16) if s.startswith("Ma\u00df") else GREY)
                y += 13
            y += 4
            for i, (img, lab) in enumerate(((ca, "A"), (cb, "B"), (cd, "Vergleich"))):
                rc = pymupdf.Rect(M + i * (pw_ + gap), y, M + i * (pw_ + gap) + pw_, y + ph_)
                put(pg, img, rc, 1600)
                pg.draw_rect(rc, color=(0.75, 0.77, 0.8), width=0.5)
                pg.insert_text((rc.x0 + 4, rc.y0 + 10), lab, fontsize=8, fontname="helv", color=GREY)
            y += ph_ + 28
    doc.save(path, deflate=True, garbage=3)
    n = doc.page_count
    doc.close()
    return n


# ----------------------------------------------------------------- Schriftfeld
_TB_LABELS = r"(?:zeichnungs?\s*-?\s*n(?:umme)?r\.?|zeichn\.?\s*-?\s*nr\.?|zeich\.?\s*-?\s*nr\.?|drawing\s*(?:no|number)\.?" \
             r"|dwg\.?\s*no\.?|teile?\s*-?\s*nr\.?|sach\s*-?\s*nr\.?|ident\s*-?\s*nr\.?|artikel\s*-?\s*nr\.?|part\s*no\.?)"
_TB_STOP = {"index", "rev", "revision", "blatt", "sheet", "maßstab", "massstab", "scale", "datum", "date", "name",
            "gepr", "gez", "bearb", "werkstoff", "material", "benennung", "titel", "title", "format", "von", "of"}


def parse_title_block(texts):
    """Schriftfeld-Angaben aus Texten [(x, y, text)] in Lesereihenfolge.
    Gibt dict(scale '1:2', scale_n 2.0, number, revision, raw) zurueck (fehlende Angaben = None)."""
    import re
    toks = [t[2].strip() for t in texts if str(t[2]).strip()]
    full = " ".join(toks)
    out = dict(scale=None, scale_n=None, number=None, revision=None, raw=full[:400])

    def num(v):
        return float(v.replace(",", "."))
    m = re.search(r"(?i)(?:ma(?:ß|ss)stab|scale|\bM\b)\s*[:.]?\s*(\d+(?:[.,]\d+)?)\s*:\s*(\d+(?:[.,]\d+)?)", full)
    if not m:
        m = re.search(r"(?<![\d.:/])(\d{1,3}(?:[.,]\d+)?)\s*:\s*(\d{1,4}(?:[.,]\d+)?)(?![\d:])", full)
    if m and num(m.group(1)) > 0 and num(m.group(2)) > 0:
        a, b = num(m.group(1)), num(m.group(2))
        if a == 1 or b == 1:
            out["scale"] = f"{m.group(1)}:{m.group(2)}"
            out["scale_n"] = b / a
    for m in re.finditer(_TB_LABELS + r"\s*[:.]?\s*([A-Z0-9][A-Za-z0-9._/\-]{2,})", full, re.I):
        if m.group(1).lower().strip(".:") not in _TB_STOP:
            out["number"] = m.group(1)
            break
    for m in re.finditer(r"(?i)\b(?:änd(?:erungs)?\s*-?\s*index|index|rev(?:ision)?|ausgabe)\b\.?\s*[:.]?\s*"
                         r"([A-Z]{1,2}|\d{1,3}|[A-Z]\d{1,2})\b", full):
        if m.group(1).lower() not in _TB_STOP:
            out["revision"] = m.group(1)
            break
    if out["number"] is None or out["revision"] is None:
        _title_columns(toks, out)
    return out


def _title_columns(toks, out):
    """Tabellenform: Zeile mit Ueberschriften (Zeichn.-Nr. | Index | Blatt), darunter die Werte in derselben
    Reihenfolge. Der Wert zur Ueberschrift steht dann so viele Felder nach der Ueberschriftenzeile."""
    import re
    is_num = lambda t: re.fullmatch(_TB_LABELS, t, re.I) is not None                      # noqa: E731
    is_rev = lambda t: re.fullmatch(r"(?i)index|rev(?:ision)?|ausgabe|änd\.?-?index", t) is not None  # noqa: E731
    is_label = lambda t: is_num(t) or is_rev(t) or t.lower().strip(".:") in _TB_STOP       # noqa: E731
    i = 0
    while i < len(toks):
        if is_label(toks[i]):
            j = i
            while j < len(toks) and is_label(toks[j]):
                j += 1
            n = j - i
            if n >= 2:
                for k in range(i, j):
                    v = toks[k + n] if k + n < len(toks) else None
                    if v is None or is_label(v):
                        continue
                    if is_num(toks[k]) and out["number"] is None and len(v) >= 3:
                        out["number"] = v
                    elif is_rev(toks[k]) and out["revision"] is None and len(v) <= 3:
                        out["revision"] = v
            i = j
        else:
            i += 1


# ----------------------------------------------------------------- PDF mit Anmerkungen (Acrobat)
def build_annotated_pdf(path, img_bgr, regs, anns, dpi=200, mm=None, names=("", "")):
    """Ergebnisbild als PDF; Aenderungen als Revisionswolken und eigene Markierungen als echte PDF-Anmerkungen
    (in Acrobat & Co. anklick-, kommentier- und loeschbar)."""
    import math
    import pymupdf
    h, w = img_bgr.shape[:2]
    k = 72.0 / dpi
    doc = pymupdf.open()
    page = doc.new_page(width=w * k, height=h * k)
    ok, png = cv2.imencode(".png", img_bgr)
    page.insert_image(page.rect, stream=png.tobytes())
    shape = img_bgr.shape

    def rgb(col):
        col = col.lstrip("#")
        return tuple(int(col[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def info(annot, subject, content):
        annot.set_info(title="ZGmax", subject=subject, content=content)

    for r in regs:
        pad = 12
        rect = pymupdf.Rect((r["x"] - pad) * k, (r["y"] - pad) * k, (r["x"] + r["w"] + pad) * k,
                            (r["y"] + r["h"] + pad) * k)
        an = page.add_rect_annot(rect)
        an.set_border(width=1.5, clouds=1)
        an.set_colors(stroke=rgb(STATUS_COLORS[reg_status(r)]))
        txt = [f"Änderung {r['nr']}: {TYPE_LABEL[r['typ']]}"]
        if r.get("text_a") or r.get("text_b"):
            txt.append(f"{r.get('text_a', '')} → {r.get('text_b', '')}")
        if r.get("dim"):
            txt.append("Maß " + r["dim"])
        if r.get("desc"):
            txt.append(r["desc"])
        txt.append("Prüfung: " + review_text(r))
        info(an, f"Änderung {r['nr']}", "\n".join(txt))
        an.update()
    for a in anns:
        t = a["type"]
        col = rgb(a["color"])
        th = ann_text_h(shape, a["size"]) * k
        lw = max(0.5, ann_line_w(shape, a["size"]) * k)
        x, y, x2, y2 = a["x"] * k, a["y"] * k, a["x2"] * k, a["y2"] * k
        if t in ("rect", "cloud", "highlight"):
            an = page.add_rect_annot(pymupdf.Rect(min(x, x2), min(y, y2), max(x, x2), max(y, y2)))
            if t == "highlight":
                an.set_colors(stroke=col, fill=col)
                an.set_opacity(0.35)
                an.set_border(width=0)
            else:
                an.set_colors(stroke=col)
                an.set_border(width=lw, clouds=1 if t == "cloud" else -1)
            info(an, {"rect": "Rahmen", "cloud": "Wolke", "highlight": "Markierung"}[t], a.get("text", ""))
        elif t == "arrow":
            an = page.add_line_annot(pymupdf.Point(x, y), pymupdf.Point(x2, y2))
            an.set_colors(stroke=col)
            an.set_border(width=lw)
            an.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, pymupdf.PDF_ANNOT_LE_CLOSED_ARROW)
            info(an, "Pfeil", "")
        elif t in ("text", "approval"):
            b = ann_bounds(shape, a)
            rect = pymupdf.Rect(b[0] * k, b[1] * k, b[2] * k + th, b[3] * k + th * 0.5)
            an = page.add_freetext_annot(rect, a.get("text", ""), fontsize=max(4, th * 0.85), text_color=col,
                                         border_color=col if t == "approval" else None)
            info(an, "Stempel" if t == "approval" else "Text", a.get("text", ""))
        elif t == "number":
            rr = 0.95 * th
            an = page.add_circle_annot(pymupdf.Rect(x - rr, y - rr, x + rr, y + rr))
            an.set_colors(stroke=col, fill=col)
            an.set_border(width=0.5)
            info(an, f"Nummer {a['nr']}", f"Nummer {a['nr']}")
            an.update()
            an = page.add_freetext_annot(pymupdf.Rect(x - rr, y - rr * 0.75, x + rr, y + rr), str(a["nr"]),
                                         fontsize=max(4, rr), text_color=(1, 1, 1), align=1)
            info(an, f"Nummer {a['nr']}", str(a["nr"]))
        elif t == "measure":
            pts = [pymupdf.Point(q[0] * k, q[1] * k) for q in (a.get("pts") or [[a["x"], a["y"]], [a["x2"], a["y2"]]])]
            an = page.add_polyline_annot(pts) if a.get("kind") != "area" else page.add_polygon_annot(pts)
            an.set_colors(stroke=col)
            an.set_border(width=lw)
            info(an, "Maß", measure_text(a, mm) if mm else "")
        else:
            continue
        an.update()
    doc.set_metadata({"title": f"Vergleich {names[0]} → {names[1]}", "creator": "ZGmax"})
    doc.save(path, deflate=True)
    doc.close()
    return path
