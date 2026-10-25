"""Auswertung des Vergleichs: Aenderungsliste, Markierung, Text-/Index-Abgleich (OCR), PDF-Bericht."""
from i18n import tr
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
TYPE_LABEL = {"entfernt": tr("entfernt (nur A)"), "neu": tr("neu (nur B)"), "geaendert": tr("ge\u00e4ndert"),
              "verschoben": tr("verschoben/gedreht")}


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


def mark_contours(regs, res, min_px=20):
    """Setzt r["contour"]: die Aenderung betrifft Koerperkanten (dicke Linien). Grundlage fuer den Listenfilter
    "Konturen und Masse". Ohne deutlich dickere Linien in der Zeichnung gilt jede Aenderung als Kontur."""
    import diffedit as de
    gw = de.suggest_geometry_width(res.a)
    for r in regs:
        if r["typ"] == "verschoben" or gw is None:
            r["contour"] = gw is None
            continue
        sl = (slice(r["y"], r["y"] + r["h"]), slice(r["x"], r["x"] + r["w"]))
        crop = (res.oa[sl] > 0) | (res.ob[sl] > 0)
        r["contour"] = bool(de.open_lines(crop, gw).sum() >= min_px)
    return regs


# Pruefstatus je Aenderung (Pruefprotokoll). Aeltere Dateien kennen nur "checked" (geprueft ja/nein).
STATUS_LABEL = {"offen": tr("offen"), "ok": tr("gepr\u00fcft"), "abgelehnt": tr("abgelehnt")}
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
        w.writerow([tr("Nr"), tr("Typ"), "x_px", "y_px", tr("Breite_px"), tr("Hoehe_px"), "x_mm", "y_mm",
                    tr("Breite_mm"), tr("Hoehe_mm"), tr("Pixel_nur_A"), tr("Pixel_nur_B"), tr("Pixel_verschoben"),
                    tr("Text_A"), tr("Text_B"), tr("Mass_Aenderung"), tr("Beschreibung"), tr("Status"), tr("Kommentar")])
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
            raise RuntimeError(tr("OCR nicht verfuegbar: pip install rapidocr-onnxruntime"))
        eng = RapidOCR()
        model, keys = os.path.join(OCR_DIR, "latin_rec.onnx"), os.path.join(OCR_DIR, "latin_dict.txt")
        if os.path.isfile(model) and os.path.isfile(keys):
            from rapidocr_onnxruntime.ch_ppocr_v3_rec import TextRecognizer
            eng.text_recognizer = TextRecognizer({"use_cuda": False, "model_path": model, "keys_path": keys,
                                                  "rec_img_shape": [3, 48, 320], "rec_batch_num": 6})
        _engine = eng
    return _engine


def ocr_language():
    return tr("Deutsch/Englisch") if os.path.isfile(os.path.join(OCR_DIR, "latin_rec.onnx")) else tr("Englisch")


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


def ocr_lines(gray, tile=1600, overlap=200, progress=None, cancel=None):
    """Texterkennung der ganzen Zeichnung in Kacheln: Liste (x0, y0, x1, y1, text) je Textzeile in Bildpixeln.
    gray: dunkle Schrift auf hellem Papier. Doppelte Funde aus ueberlappenden Kacheln werden zusammengefasst."""
    H, W = gray.shape
    eng = _ocr_engine()
    tiles = [(x, y) for y in range(0, max(1, H - overlap), tile - overlap) for x in range(0, max(1, W - overlap), tile - overlap)]
    out = []
    for k, (x, y) in enumerate(tiles):
        if cancel is not None and cancel():
            raise dc.Cancelled()
        if progress:
            progress(k / len(tiles))
        part = gray[y:y + tile, x:x + tile]
        if part.min() > 200:                     # leere Kachel
            continue
        res, _ = eng(np.ascontiguousarray(part))
        for box, text, score in res or []:
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            out.append((x + min(xs), y + min(ys), x + max(xs), y + max(ys), str(text).strip()))
    uniq = []
    for b in sorted(out, key=lambda t: (t[1], t[0])):    # gleiche Zeile aus zwei Kacheln nur einmal
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if any(u[4] == b[4] and abs((u[0] + u[2]) / 2 - cx) < 15 and abs((u[1] + u[3]) / 2 - cy) < 15 for u in uniq[-50:]):
            continue
        uniq.append(b)
    return uniq


def find_text(lines, query):
    """Treffer fuer 'query' (Gross-/Kleinschreibung egal) in Textzeilen [(x0, y0, x1, y1, text), ...].
    Gibt Rechtecke (x0, y0, x1, y1) zurueck; innerhalb einer Zeile anteilig nach Zeichenposition."""
    q = query.strip().lower()
    hits = []
    if not q:
        return hits
    for x0, y0, x1, y1, text in lines:
        t = text.lower()
        start = t.find(q)
        while start >= 0:
            n = max(1, len(t))
            hits.append((x0 + (x1 - x0) * start / n, y0, x0 + (x1 - x0) * (start + len(q)) / n, y1))
            start = t.find(q, start + 1)
    # Wort- und Zeilentreffer an derselben Stelle nur einmal (der kleinere = genauere bleibt)
    hits.sort(key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    out = []
    for r in hits:
        cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        if not any(o[0] - 2 <= cx <= o[2] + 2 and o[1] - 2 <= cy <= o[3] + 2 for o in out):
            out.append(r)
    return sorted(out, key=lambda r: (round(r[1] / 20), r[0]))


def ocr_any_orientation(gray, min_score=0.55):
    """Text in jeder Lage: waagerecht, senkrecht von unten nach oben (typische Bemassung) und von oben nach unten.
    Jede Fundstelle wird in der Drehung gelesen, in der sie am sichersten erkannt wird.
    Rueckgabe [(x0, y0, x1, y1, text, score), ...] im Koordinatensystem von gray, in Lesereihenfolge."""
    H, W = gray.shape[:2]
    eng = _ocr_engine()
    found = []
    for rot in (0, 1, 3):                          # 0 Grad, 90 Grad links (unten->oben), 90 Grad rechts
        img = np.ascontiguousarray(np.rot90(gray, rot)) if rot else gray
        res, _ = eng(img)
        for box, text, score in res or []:
            text = str(text).strip()
            if not text or float(score) < min_score:
                continue
            pts = []
            for px, py in box:                     # Punkte zurueck in die ungedrehte Lage
                if rot == 1:                       # np.rot90(k=1): (x, y) -> (y, W-1-x)
                    px, py = W - 1 - py, px
                elif rot == 3:                     # np.rot90(k=3): (x, y) -> (H-1-y, x)
                    px, py = py, H - 1 - px
                pts.append((px, py))
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            found.append((min(xs), min(ys), max(xs), max(ys), text, float(score) * len(text)))
    found.sort(key=lambda t: -t[5])                # sicherste zuerst; Ueberschneidungen nur einmal
    keep = []
    for f in found:
        area = max(1.0, (f[2] - f[0]) * (f[3] - f[1]))
        if any(min(f[2], k[2]) - max(f[0], k[0]) > 0 and min(f[3], k[3]) - max(f[1], k[1]) > 0 and
               (min(f[2], k[2]) - max(f[0], k[0])) * (min(f[3], k[3]) - max(f[1], k[1])) > 0.3 * area for k in keep):
            continue
        keep.append(f)
    keep.sort(key=lambda t: (round(t[1] / max(10, t[3] - t[1])), t[0]))
    return keep


def ocr_box(ink, box, pad=15, max_area=6_000_000):
    x, y, w, h = box
    H, W = ink.shape
    x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
    if (x1 - x0) * (y1 - y0) > max_area:
        return tr("(Bereich zu gross)")
    crop = 255 - ink[y0:y1, x0:x1]
    crop = cv2.copyMakeBorder(crop, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return " ".join(t[4] for t in ocr_any_orientation(crop)).strip()


def text_changed(r):
    """Hat sich der gelesene Text einer Aenderung geaendert (Gross-/Kleinschreibung und Leerzeichen egal)?"""
    a, b = r.get("text_a") or "", r.get("text_b") or ""
    return bool(a or b) and _norm(a).replace(" ", "") != _norm(b).replace(" ", "")


def _norm(s):
    return re.sub(r"\s+", " ", s).strip().casefold()


def text_diff(res, regs, log=print, max_regions=300):
    """Liest Text in geaenderten Bereichen aus A und B und traegt ihn in die Liste ein."""
    todo = [r for r in regs if r["typ"] != "verschoben"][:max_regions]
    log(tr("Textvergleich (OCR) fuer {} Bereiche ...").format(len(todo)))
    for i, r in enumerate(todo, 1):
        box = (r["x"], r["y"], r["w"], r["h"])
        r["text_a"] = ocr_box(res.a, box)
        r["text_b"] = ocr_box(res.b, box)
        if i % 20 == 0:
            log(f"  {i}/{len(todo)}")
    n = sum(1 for r in todo if _norm(r["text_a"]) != _norm(r["text_b"]))
    log(tr("  Text unterschiedlich in {} von {} Bereichen").format(n, len(todo)))
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
    log(tr("Massvergleich: {} Massaenderungen in {} Bereichen").format(n, len(regs)))
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
        notes.append(tr("WARNUNG: Zeichnung ist geaendert, aber der Index im Schriftfeld ist gleich geblieben."))
    if idx_a != idx_b and n_chg == 0:
        notes.append(tr("WARNUNG: Index hat sich geaendert, aber im Zeichnungsfeld wurden keine Aenderungen gefunden."))
    if not notes:
        notes.append(tr("Index und erkannte Aenderungen sind plausibel."))
    out = dict(index_a=idx_a, index_b=idx_b, only_a=only_a, only_b=only_b, changes=n_chg, notes=notes)
    log(tr("Index-Abgleich: A={}  B={}  Aenderungen ausserhalb Schriftfeld: {}").format(idx_a, idx_b, n_chg))
    for n in notes:
        log("  " + n)
    log(tr("  Schriftfeld: {} Texte nur in A, {} Texte nur in B").format(len(only_a), len(only_b)))
    return out


# ----------------------------------------------------------------- Anmerkungen
# Eine Anmerkung ist ein dict: type (text|number|approval|rect|arrow), x, y, x2, y2, text, nr, color, size.
#   text     Text, Ecke oben links bei (x, y)
#   number   nummerierter Kreis, Mitte bei (x, y), Nummer nr
#   approval Freigabe-Stempel (Rahmen mit Text), Ecke oben links bei (x, y)
#   rect     Rahmen (x, y)-(x2, y2)
#   arrow    Pfeil von (x, y) zur Spitze (x2, y2)
APPROVAL_TITLES = (tr("FREIGEGEBEN"), tr("GEPRÜFT"), tr("ABGELEHNT"), tr("IN ARBEIT"))
#   cloud     Revisionswolke um das Rechteck (x, y)-(x2, y2)
#   highlight Textmarker: halbtransparente Flaeche (x, y)-(x2, y2)
#   ellipse   Ellipse im Rechteck (x, y)-(x2, y2)
#   image     eingefuegtes Bild im Rechteck (x, y)-(x2, y2), Inhalt als PNG (Base64) in "png"
#   pen       Freihandlinie, polyline Linienzug, polygon geschlossener Linienzug: Punkte in "pts",
#             (x, y)-(x2, y2) ist das umgebende Rechteck
RECT_TYPES = ("rect", "cloud", "highlight", "ellipse", "image", "redact", "pixelate")
REDACT_TYPES = ("redact", "pixelate")       # unkenntlich machen: wird in jede Ausgabe eingebrannt

# Feste Ebenen: Zeichnung, Aenderungsrahmen und die Markierungen nach Art. Ausgeblendete Ebenen werden weder
# angezeigt noch gespeichert; in PDF mit Anmerkungen und SVG werden die Ebenen als echte Ebenen geschrieben.
LAYERS = (("zeichnung", tr("Zeichnung")), ("zonen", tr("Zonen")), ("aenderungen", tr("Änderungen")),
          ("bilder", tr("Eingefügte Bilder")), ("markierungen", tr("Markierungen")), ("masse", tr("Maße")),
          ("schwaerzung", tr("Schwärzungen")))   # unten -> oben
LAYER_NAMES = dict(LAYERS)


# Pruefstatus je Person wie in Acrobat/Bluebeam (Statusmodell "Review")
REVIEW_STATES = {"none": tr("Kein Status"), "accepted": tr("Akzeptiert"), "rejected": tr("Abgelehnt"),
                 "cancelled": tr("Abgebrochen"), "completed": tr("Abgeschlossen")}
PDF_STATE = {"none": "None", "accepted": "Accepted", "rejected": "Rejected", "cancelled": "Cancelled",
             "completed": "Completed"}
STATE_FROM_PDF = {v.lower(): k for k, v in PDF_STATE.items()}


def ann_id(a):
    """Feste Kennung einer Markierung (fuer Antworten in PDF/XFDF)."""
    import uuid
    if not a.get("id"):
        a["id"] = uuid.uuid4().hex[:12]
    return a["id"]


def ann_layer(a):
    """Ebene einer Anmerkung."""
    return {"measure": "masse", "image": "bilder", "redact": "schwaerzung", "pixelate": "schwaerzung"}.get(
        a.get("type"), "markierungen")


def pixel_block(shape, size):
    """Kantenlaenge der Mosaik-Bloecke beim Verpixeln (Bildpixel); nie so fein, dass Schrift erkennbar bliebe."""
    return int(max(12, round(4 * ann_unit(shape) * size)))


def pixelate(part, blk, seed=0):
    """Unumkehrbares Mosaik: Blockmittel, dazu Zufallsrauschen je Block und nur wenige Stufen - so laesst sich der
    Inhalt auch mit "Entpixeln"-Verfahren nicht zurueckrechnen. Gleiches seed = gleiches Bild (Anzeige = Export)."""
    h, w = part.shape[:2]
    sw, sh = max(1, w // blk), max(1, h // blk)
    small = cv2.resize(part, (sw, sh), interpolation=cv2.INTER_AREA).astype(np.int16)
    rng = np.random.default_rng(seed)
    small += rng.integers(-28, 29, size=small.shape[:2] + ((1,) if small.ndim == 3 else ()), dtype=np.int16)
    small = (np.clip(small, 0, 255) // 32 * 32 + 16).astype(np.uint8)   # 8 Stufen je Kanal
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


def redact_seed(a):
    return int(abs(a["x"]) * 7 + abs(a["y"]) * 13 + abs(a["x2"]) * 17 + abs(a["y2"]) * 19) % (2 ** 31)


def paper_around(img, x0, y0, x1, y1, ring=24):
    """Papierfarbe rund um ein Rechteck (helle Pixel im Rand), fuer "mit Papierfarbe schwaerzen"."""
    h, w = img.shape[:2]
    X0, Y0, X1, Y1 = max(0, x0 - ring), max(0, y0 - ring), min(w, x1 + ring), min(h, y1 + ring)
    box = img[Y0:Y1, X0:X1].reshape(-1, *img.shape[2:]) if img.ndim == 3 else img[Y0:Y1, X0:X1].reshape(-1)
    gray = box.min(axis=1) if img.ndim == 3 else box
    light = box[gray > 150]
    if len(light) == 0:
        return (255, 255, 255) if img.ndim == 3 else 255
    med = np.median(light, axis=0)
    return tuple(int(v) for v in med) if img.ndim == 3 else int(med)


def apply_redactions(img, anns, offset=(0, 0), ref_shape=None):
    """Schwaerzen und Verpixeln in das Bild einbrennen (BGR oder Grau, an Ort und Stelle). Wird bei jeder Ausgabe
    angewendet - auch wenn Markierungen ausgeblendet sind -, damit der Inhalt darunter nirgends erhalten bleibt."""
    shape = _ref(img.shape, ref_shape)
    ox, oy = offset
    h, w = img.shape[:2]
    for a in anns or []:
        if a.get("type") not in REDACT_TYPES:
            continue
        x0 = int(np.floor(min(a["x"], a["x2"]) - ox))
        y0 = int(np.floor(min(a["y"], a["y2"]) - oy))
        x1 = int(np.ceil(max(a["x"], a["x2"]) - ox))
        y1 = int(np.ceil(max(a["y"], a["y2"]) - oy))
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        if x1 <= x0 or y1 <= y0:
            continue
        part = img[y0:y1, x0:x1]
        if a["type"] == "redact":                    # schwarz - oder auf Wunsch in Papierfarbe (weiss "ausmalen")
            if a.get("fill") == "paper":
                part[:] = paper_around(img, x0, y0, x1, y1)
            else:
                part[:] = 0
        else:
            part[:] = pixelate(part, pixel_block(shape, a["size"]), redact_seed(a))
    return img


def redaction_boxes(anns):
    return [(min(a["x"], a["x2"]), min(a["y"], a["y2"]), max(a["x"], a["x2"]), max(a["y"], a["y2"]))
            for a in anns or [] if a.get("type") in REDACT_TYPES]


def redact_result(res, anns):
    """Kopie des Vergleichsergebnisses, in der geschwaerzte/verpixelte Bereiche leer sind (fuer Berichte)."""
    import copy as _copy
    boxes = redaction_boxes(anns)
    if not boxes:
        return res
    r = _copy.copy(res)
    for name in ("a", "b", "oa", "ob", "both", "moved"):
        arr = getattr(r, name)
        if arr is None:
            continue
        arr = arr.copy()
        for x0, y0, x1, y1 in boxes:
            arr[max(0, int(y0)):max(0, int(y1) + 1), max(0, int(x0)):max(0, int(x1) + 1)] = 0
        setattr(r, name, arr)
    return r


LAYER_RANK = {k: i for i, (k, _) in enumerate(LAYERS)}


def layer_order(anns):
    """Indizes der Anmerkungen in Zeichenreihenfolge: untere Ebenen zuerst, innerhalb einer Ebene wie angelegt."""
    return sorted(range(len(anns)), key=lambda i: (LAYER_RANK[ann_layer(anns[i])], i))
PTS_TYPES = ("pen", "polyline", "polygon")


def pts_bbox(pts):
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    return min(xs), min(ys), max(xs), max(ys)


_IMG_CACHE = {}


def ann_image(a):
    """Eingefuegtes Bild einer Anmerkung als BGRA-Array (zwischengespeichert)."""
    import base64
    key = a.get("png", "")
    img = _IMG_CACHE.get(key)
    if img is None:
        raw = np.frombuffer(base64.b64decode(key), np.uint8) if key else np.zeros(0, np.uint8)
        img = cv2.imdecode(raw, cv2.IMREAD_UNCHANGED) if raw.size else None
        if img is None:
            img = np.zeros((1, 1, 4), np.uint8)
        elif img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
        elif img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        if len(_IMG_CACHE) > 64:
            _IMG_CACHE.clear()
        _IMG_CACHE[key] = img
    return img


def image_png(bgra):
    """Bild (BGR/BGRA/Grau) als Base64-PNG fuer eine Anmerkung vom Typ image."""
    import base64
    ok, png = cv2.imencode(".png", bgra)
    return base64.b64encode(png.tobytes()).decode("ascii") if ok else ""


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


def ann_lines(a, th=None):
    """Zeilen eines Texts; mit Textfeldbreite "w" (Bildpixel) wird an Wortgrenzen umbrochen."""
    lines = (a.get("text") or " ").split("\n")
    w = a.get("w")
    if not w or not th:
        return lines
    n = max(1, int(w / (0.55 * th)))                 # Zeichen je Zeile (mittlere Zeichenbreite)
    out = []
    for line in lines:
        cur = ""
        for word in line.split(" "):
            while len(word) > n:                     # sehr lange Woerter hart trennen
                if cur:
                    out.append(cur)
                    cur = ""
                out.append(word[:n])
                word = word[n:]
            if not cur:
                cur = word
            elif len(cur) + 1 + len(word) <= n:
                cur += " " + word
            else:
                out.append(cur)
                cur = word
        out.append(cur)
    return out


MEASURE_KINDS = {"dist": tr("L\u00e4nge"), "chain": tr("Maßkette"), "poly": tr("Linienzug"), "angle": tr("Winkel"),
                 "radius": tr("Radius"), "area": tr("Fl\u00e4che")}


def measure_value(a, mm):
    """(Art, Zahl) eines Masses fuer Summen: Laenge/Linienzug in mm, Flaeche in mm2, Winkel in Grad, Radius in mm."""
    import math
    pts = a.get("pts") or [[a["x"], a["y"]], [a["x2"], a["y2"]]]
    k = a.get("kind", "dist")
    if k in ("dist", "poly"):
        return "length", sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
                             for i in range(len(pts) - 1)) * mm
    if k == "area" and len(pts) >= 3:
        s = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
        return "area", abs(s) / 2 * mm * mm
    if k == "radius" and len(pts) >= 3 and circle_3pts(*pts[:3]):
        return "radius", circle_3pts(*pts[:3])[2] * mm
    if k == "angle" and len(pts) >= 3:
        v1 = (pts[0][0] - pts[1][0], pts[0][1] - pts[1][1])
        v2 = (pts[2][0] - pts[1][0], pts[2][1] - pts[1][1])
        return "angle", abs(math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1])))
    return "other", 0.0


def measure_summary(anns, mm, fmt=None):
    """Summen und Zaehlungen fuer die Liste: Laengen, Flaechen, Anzahl je Markierungsart."""
    fmt = fmt or MEASURE_FMT
    unit, dec = fmt.get("unit", "mm"), int(fmt.get("dec", 2))
    f = UNITS.get(unit, 1.0)
    L = A = 0.0
    nl = na = 0
    counts = {}
    for a in anns:
        if a.get("type") == "measure":
            kind, v = measure_value(a, mm)
            if kind == "length":
                L, nl = L + v, nl + 1
            elif kind == "area":
                A, na = A + v, na + 1
        counts[a.get("type")] = counts.get(a.get("type"), 0) + 1
    parts = []
    if nl:
        parts.append(tr("{} Längen: Σ {} {}").format(nl, _num(L * f, dec), unit))
    if na:
        parts.append(tr("{} Flächen: Σ {} {}²").format(na, _num(A * f * f, max(0, dec - 1)), unit))
    return parts, counts


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


# Anzeige der Messwerte (Einheit, Nachkommastellen); vom Programm aus den Einstellungen gesetzt
MEASURE_FMT = {"unit": "mm", "dec": 2}
UNITS = {"mm": 1.0, "cm": 0.1, "m": 0.001, "in": 1 / 25.4}


def _num(v, dec):
    return f"{v:.{dec}f}"


def measure_text(a, mm, fmt=None):
    """Messwert als Text. mm = Millimeter je Bildpixel (inkl. Massstab); fmt = {"unit", "dec"}."""
    import math
    fmt = fmt or MEASURE_FMT
    unit, dec = fmt.get("unit", "mm"), int(fmt.get("dec", 2))
    f = UNITS.get(unit, 1.0)
    pts = a.get("pts") or [[a["x"], a["y"]], [a["x2"], a["y2"]]]
    k = a.get("kind", "dist")
    if k in ("dist", "poly"):
        L = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))
        return f"{_num(L * mm * f, dec)} {unit}"
    if k == "angle" and len(pts) >= 3:
        v1 = (pts[0][0] - pts[1][0], pts[0][1] - pts[1][1])
        v2 = (pts[2][0] - pts[1][0], pts[2][1] - pts[1][1])
        ang = abs(math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], v1[0] * v2[0] + v1[1] * v2[1])))
        return f"{_num(ang, max(0, dec - 1))}°"
    if k == "radius" and len(pts) >= 3:
        c = circle_3pts(*pts[:3])
        return tr("gerade") if c is None else f"R {_num(c[2] * mm * f, dec)} {unit}  (Ø {_num(2 * c[2] * mm * f, dec)})"
    if k == "area" and len(pts) >= 3:
        s = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                for i in range(len(pts)))
        return f"{_num(abs(s) / 2 * mm * mm * f * f, max(0, dec - 1))} {unit}²"
    return ""


def measure_label(a, shape):
    """Lage des Messwerts wie bei einer Bemassung: (cx, cy, winkel_grad, ax, ay) in Bildpixeln. Bei einer Laenge
    steht der Wert mittig ueber der Masslinie und parallel zu ihr (immer lesbar, nie kopfueber); sonst waagerecht
    ueber dem Mittelpunkt. Mit "lo" (Verschiebung durch den Benutzer) liegt er daneben; (ax, ay) ist dann der
    Punkt, zu dem eine Hinweislinie fuehrt."""
    import math
    pts = a.get("pts") or [[a["x"], a["y"]], [a["x2"], a["y2"]]]
    _lw, th, _al = measure_style(shape, a["size"])
    k = a.get("kind", "dist")
    ang = 0.0
    if k == "dist" and len(pts) >= 2:
        (x0, y0), (x1, y1) = pts[0][:2], pts[-1][:2]
        ax, ay = (x0 + x1) / 2, (y0 + y1) / 2
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        if ang > 90:
            ang -= 180
        elif ang <= -90:
            ang += 180
    elif k == "radius" and len(pts) >= 3 and circle_3pts(*pts[:3]):
        c = circle_3pts(*pts[:3])
        ax, ay = c[0], c[1]
    elif k == "angle" and len(pts) >= 3:
        ax, ay = pts[1][0], pts[1][1]
    else:
        ax = sum(p[0] for p in pts) / len(pts)
        ay = sum(p[1] for p in pts) / len(pts)
    r = math.radians(ang)
    gap = 0.75 * th                                 # Mitte des Werts ueber der Linie
    cx, cy = ax + math.sin(r) * gap, ay - math.cos(r) * gap
    if k == "dist" and len(pts) >= 2 and MEASURE_FMT.get("mm"):
        L = math.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])
        tw = 0.62 * th * len(measure_text(a, MEASURE_FMT["mm"]))
        if tw + th > L:                             # kurzes Mass: Wert ausserhalb, hinter dem Pfeil (wie im CAD)
            ex, ey = (pts[-1][0], pts[-1][1]) if pts[-1][0] >= pts[0][0] else (pts[0][0], pts[0][1])
            cx, cy = ex + math.cos(r) * (tw / 2 + 0.8 * th), ey + math.sin(r) * (tw / 2 + 0.8 * th)
    lo = a.get("lo")
    if lo:
        cx, cy = ax + lo[0], ay + lo[1]
    return cx, cy, ang, ax, ay


def measure_style(shape, size):
    """Bemassung: (Linienbreite, Texthoehe, Pfeillaenge) in Bildpixeln. Duenne Linie, gut lesbare Zahl."""
    lw = max(1.0, 0.55 * ann_line_w(shape, size))
    th = 0.75 * ann_text_h(shape, size)
    return lw, th, max(6 * lw, 0.9 * th)


def arrow_head(tip, frm, length):
    """Dreieck einer Pfeilspitze an 'tip', die von 'frm' her kommt."""
    import math
    ang = math.atan2(tip[1] - frm[1], tip[0] - frm[0])
    w = 0.38
    return [tip, (tip[0] - length * math.cos(ang - w), tip[1] - length * math.sin(ang - w)),
            (tip[0] - length * math.cos(ang + w), tip[1] - length * math.sin(ang + w))]


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
        cx, cy, _ang, _ax, _ay = measure_label(a, shape)
        xs = [p[0] for p in pts] + [cx - th * 3, cx + th * 3]
        ys = [p[1] for p in pts] + [cy - th, cy + th]
        return min(xs) - th * 0.5, min(ys) - th * 0.5, max(xs) + th * 0.5, max(ys) + th * 0.5
    if t == "number":
        r = 0.95 * th
        return x - r, y - r, x + r, y + r
    if t in ("text", "approval"):
        lines = ann_lines(a, th)
        pad = 0.5 * th if t == "approval" else 0
        w = max(max(len(s) for s in lines) * 0.58 * th, a.get("w") or 0)
        return (x, y, x + w + 2 * pad, y + len(lines) * 1.25 * th + 2 * pad)
    lw = ann_line_w(shape, a["size"])
    if t == "cloud":
        lw += cloud_radius(shape, a["size"])
    if t in PTS_TYPES and a.get("pts"):
        x0, y0, x1, y1 = pts_bbox(a["pts"])
        return x0 - lw, y0 - lw, x1 + lw, y1 + lw
    if t == "image":
        lw = 0
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
        if a["type"] in REDACT_TYPES:                 # zum Schluss, ueber allem (apply_redactions)
            continue
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
            d.multiline_text((x, y), "\n".join(ann_lines(a, th)), font=dc._font(max(6, int(th))), fill=col,
                             stroke_width=max(1, int(th / 12)), stroke_fill="white", spacing=int(th * 0.25))
        elif t == "approval":
            b = ann_bounds(shape, dict(a, x=x, y=y))
            d.rectangle([b[0], b[1], b[2], b[3]], fill="white", outline=col, width=max(2, int(lw * 1.3)))
            d.multiline_text((x + 0.5 * th, y + 0.5 * th), a.get("text", ""), font=dc._font(max(6, int(th))),
                             fill=col, spacing=int(th * 0.25))
        elif t == "measure":
            mlw, mth, alen = measure_style(shape, a["size"])
            pp = [(p[0] - ox, p[1] - oy) for p in (a.get("pts") or [[a["x"], a["y"]], [a["x2"], a["y2"]]])]
            for gk, gd in measure_geometry(a):
                if gk == "circle":
                    cx, cy, cr = gd[0] - ox, gd[1] - oy, gd[2]
                    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], outline=col, width=max(1, int(mlw)))
                    d.line([(cx - mlw * 4, cy), (cx + mlw * 4, cy)], fill=col, width=max(1, int(mlw)))
                    d.line([(cx, cy - mlw * 4), (cx, cy + mlw * 4)], fill=col, width=max(1, int(mlw)))
                else:
                    pl = [(p[0] - ox, p[1] - oy) for p in gd]
                    if gk == "poly":
                        pl = pl + [pl[0]]
                    d.line(pl, fill=col, width=max(1, int(round(mlw))), joint="curve")
            if a.get("kind", "dist") == "dist" and len(pp) >= 2:     # Pfeilspitzen wie bei einer Bemassung
                d.polygon(arrow_head(pp[0], pp[1], alen), fill=col)
                d.polygon(arrow_head(pp[-1], pp[-2], alen), fill=col)
            else:
                for p in pp:
                    r_ = max(2.0, 1.4 * mlw)
                    d.ellipse([p[0] - r_, p[1] - r_, p[0] + r_, p[1] + r_], outline=col, width=max(1, int(mlw)))
            if mm:                                    # Wert ueber der Masslinie, parallel zu ihr
                txt = measure_text(a, mm)
                cx, cy, ang, ax, ay = measure_label(a, shape)
                cx, cy, ax, ay = cx - ox, cy - oy, ax - ox, ay - oy
                if a.get("lo"):
                    d.line([(cx, cy), (ax, ay)], fill=col, width=max(1, int(mlw)))
                f = dc._font(max(6, int(mth)))
                w_ = d.textlength(txt, font=f)
                bw, bh = int(w_ + mth * 0.6) + 2, int(mth * 1.3) + 2
                lab = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
                ld = ImageDraw.Draw(lab)
                ld.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=mth * 0.25, fill="white", outline=col,
                                     width=max(1, int(mlw)))
                ld.text((bw / 2, bh / 2), txt, font=f, fill=col, anchor="mm")
                if abs(ang) > 0.1:
                    lab = lab.rotate(-ang, resample=Image.BICUBIC, expand=True)
                im.paste(lab, (int(round(cx - lab.width / 2)), int(round(cy - lab.height / 2))), lab)
                d = ImageDraw.Draw(im)
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
        elif t == "line":
            d.line([(x, y), (x2, y2)], fill=col, width=int(lw))
        elif t == "ellipse":
            d.ellipse([min(x, x2), min(y, y2), max(x, x2), max(y, y2)], outline=col, width=int(lw))
        elif t in PTS_TYPES and a.get("pts"):
            pl = [(q[0] - ox, q[1] - oy) for q in a["pts"]]
            if t == "polygon" and len(pl) > 2:
                pl = pl + [pl[0]]
            if len(pl) == 1:
                pl = pl * 2
            d.line(pl, fill=col, width=int(lw), joint="curve")
            if t == "pen":                               # runde Enden wie beim Stift
                r_ = lw / 2
                for q in (pl[0], pl[-1]):
                    d.ellipse([q[0] - r_, q[1] - r_, q[0] + r_, q[1] + r_], fill=col)
        elif t == "image":
            src = ann_image(a)
            bw, bh = int(round(abs(x2 - x))), int(round(abs(y2 - y)))
            if bw > 0 and bh > 0:
                tile = cv2.resize(src, (bw, bh), interpolation=cv2.INTER_AREA if bw < src.shape[1] else cv2.INTER_LINEAR)
                pil = Image.fromarray(cv2.cvtColor(tile, cv2.COLOR_BGRA2RGBA))
                im.paste(pil, (int(round(min(x, x2))), int(round(min(y, y2)))), pil)
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
    apply_redactions(img_bgr, anns, offset, ref_shape)
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
        d.text((PW - M - 220, 30), tr("Seite {}").format(len(pages) + 1), font=F_S, fill=(200, 210, 225))
        return im, d

    def paste(im, arr_bgr, x, y):
        rgb = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2RGB) if arr_bgr.ndim == 3 else arr_bgr
        im.paste(Image.fromarray(rgb), (x, y))

    # ---- Seite 1: Uebersicht
    im, d = new_page("ZGmax - Uebersicht")
    y = 120
    cnt = {k: sum(1 for r in regs if r["typ"] == k) for k in TYPE_LABEL}
    lines = [tr("A (Referenz): {}").format(name_a), tr("B (Vergleich): {}").format(name_b),
             tr("Erstellt: {:%d.%m.%Y %H:%M}   Aufloesung: {} dpi").format(_dt.datetime.now(), dpi),
             tr("Aenderungen: {}  (entfernt {}, neu {}, geaendert {}, verschoben {})").format(len(regs), cnt['entfernt'], cnt['neu'], cnt['geaendert'], cnt['verschoben'])]
    if index:
        lines.append(tr("Index (vermutet): A = {}   B = {}").format(index['index_a'], index['index_b']))
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
    cols = [(tr("Nr"), 60), (tr("Typ"), 270), (tr("Position (mm)"), 250), (tr("Groesse (mm)"), 220), (tr("Text A"), 420), (tr("Text B"), 420)]
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
                    f"{r['w'] * mm:.1f} x {r['h'] * mm:.1f}", ((tr("Ma\u00df: ") + r["dim"]) if r.get("dim") else r["text_a"])[:34],
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
        label = {"text": tr("Text"), "number": tr("Nummer"), "approval": tr("Stempel"), "rect": tr("Rahmen"), "arrow": tr("Pfeil"),
                 "measure": tr("Maß")}
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
                d.text((M + 260, y), tr("{:.0f} / {:.0f} mm").format(a['x'] * mm, a['y'] * mm), font=F_S, fill=(30, 30, 30))
                d.text((M + 520, y), txt[:70], font=F_S, fill=(30, 30, 30))
                y += 46
                d.line([(M, y - 8), (PW - M, y - 8)], fill=(225, 228, 232), width=1)
            pages.append(im)

    # ---- Detailseiten: A | B | Vergleich
    det = [r for r in regs][:max_detail]
    log(tr("Bericht: {} Detailansichten ...").format(len(det)))
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
            d.text((M, y), tr("{}  {}   Position {:.0f} / {:.0f} mm").format(r['nr'], TYPE_LABEL[r['typ']], r['x'] * mm, r['y'] * mm), font=F_N,
                   fill=(20, 20, 20))
            if r.get("desc"):
                d.text((M, y + 50), r["desc"][:90], font=F_S, fill=(30, 30, 30))
            if r.get("dim"):
                d.text((M, y + 32), tr("Maß {}").format(r['dim'][:70]), font=F_N, fill=(180, 20, 40))
            elif r["text_a"] or r["text_b"]:
                d.text((M, y + 32), tr("Text: {}  ->  {}").format(r['text_a'][:60], r['text_b'][:60]), font=F_S, fill=(90, 90, 90))
            for i, (img, lab) in enumerate(((ca, "A"), (cb, "B"), (cd, tr("Vergleich")))):
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
        log(tr("Hinweis: PyMuPDF fehlt, es wird ein Rasterbericht erzeugt (pip install pymupdf)."))
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
    pg = page(tr("ZGmax - \u00dcbersicht"))
    cnt = {k: sum(1 for r in regs if r["typ"] == k) for k in TYPE_LABEL}
    lines = [tr("A (Referenz): {}").format(name_a), tr("B (Vergleich): {}").format(name_b),
             tr("Erstellt: {:%d.%m.%Y %H:%M}   Auflösung: {} dpi").format(_dt.datetime.now(), dpi),
             tr("Änderungen: {}  (entfernt {}, neu {}, geändert {}, verschoben {})").format(len(regs), cnt['entfernt'], cnt['neu'], cnt['geaendert'], cnt['verschoben'])]
    if index:
        lines.append(tr("Index (vermutet): A = {}   B = {}").format(index['index_a'], index['index_b']))
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
    cols = [(tr("Nr"), 28), (tr("Typ"), 78), (tr("Position (mm)"), 82), (tr("Gr\u00f6\u00dfe (mm)"), 78), (tr("Text A"), 140),
            (tr("Text B"), 140), (tr("Beschreibung"), 236)]
    per = 27
    for p0 in range(0, len(regs), per):
        pg = page(tr("\u00c4nderungsliste"))
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
                    (tr("Ma\u00df ") + dim + "  " if dim else "") + r.get("desc", "")
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
        label = {"text": tr("Text"), "number": tr("Nummer"), "approval": tr("Stempel"), "rect": tr("Rahmen"), "arrow": tr("Pfeil"),
                 "measure": tr("Ma\u00df")}
        for p0 in range(0, len(anns), per):
            pg = page(tr("Anmerkungen"))
            y = 62.0
            for a in anns[p0:p0 + per]:
                what = label.get(a["type"], a["type"])
                if a["type"] == "number":
                    what += f" {a['nr']}"
                txt = " / ".join(s for s in (a.get("text") or "").split("\n") if s)
                if a["type"] == "measure":
                    what = MEASURE_KINDS.get(a.get("kind", "dist"), "Ma\u00df")
                    txt = measure_text(a, mm) + ("  " + txt if txt else "")
                row_text(pg, y, [(M, 120, what, DARK), (M + 130, 120, tr("{:.0f} / {:.0f} mm").format(a['x'] * mm, a['y'] * mm), DARK),
                                 (M + 260, PW - 2 * M - 260, txt, DARK)])
                y += 7
                pg.draw_line((M, y), (PW - M, y), color=(0.88, 0.89, 0.91), width=0.5)
                y += 12

    # ---- Details A | B | Vergleich (volle Aufloesung, max. 1600 px je Bild)
    det = list(regs)[:max_detail]
    log(tr("Bericht: {} Detailansichten ...").format(len(det)))
    gap = 10.0
    pw_ = (PW - 2 * M - 2 * gap) / 3
    ph_ = 205.0
    for p0 in range(0, len(det), 2):
        pg = page(tr("Details: A | B | Vergleich"))
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
                sub.append(tr("Ma\u00df ") + r["dim"])
            elif r.get("text_a") or r.get("text_b"):
                sub.append(tr("Text: {}  ->  {}").format(r.get('text_a', ''), r.get('text_b', '')))
            if r.get("desc"):
                sub.append(tr("Beschreibung: ") + r["desc"])
            if r.get("status") or r.get("checked") or r.get("comment"):
                sub.append(tr("Pr\u00fcfung: ") + review_text(r))
            for s in sub:
                pg.insert_text((M, y), fit_text(s, PW - 2 * M, 9.5), fontsize=9.5, fontname="helv",
                               color=(0.7, 0.08, 0.16) if s.startswith("Ma\u00df") else GREY)
                y += 13
            y += 4
            for i, (img, lab) in enumerate(((ca, "A"), (cb, "B"), (cd, tr("Vergleich")))):
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
_TB_STOP = {"index", "rev", "revision", "blatt", "sheet", tr("maßstab"), "massstab", "scale", "datum", "date", "name",
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
def _pdf_thread(doc, page, parent, a, oc=None):
    """Antworten und Status einer Markierung als Antwort-Anmerkungen (/IRT) - in Acrobat als Unterhaltung sichtbar."""
    import pymupdf
    pt = pymupdf.Point(parent.rect.x0, parent.rect.y0)
    entries = [(r.get("author", ""), r.get("text", ""), r.get("date", ""), None) for r in a.get("replies") or []]
    entries += [(who, REVIEW_STATES.get(st, st), "", st) for who, st in (a.get("states") or {}).items()]
    for who, text, date, state in entries:
        r = page.add_text_annot(pt, text or " ")
        r.set_info(title=who or "ZGmax", content=text or "")
        r.set_irt_xref(parent.xref)
        if state:
            doc.xref_set_key(r.xref, "State", pymupdf.get_pdf_str(PDF_STATE.get(state, "None")))
            doc.xref_set_key(r.xref, "StateModel", "(Review)")
        if oc:
            r.set_oc(oc)
        r.update()


def build_annotated_pdf(path, img_bgr, regs, anns, dpi=200, mm=None, names=("", ""), layers=True):
    """Ergebnisbild als PDF; Aenderungen als Revisionswolken und eigene Markierungen als echte PDF-Anmerkungen
    (in Acrobat & Co. anklick-, kommentier- und loeschbar). layers=True: jede Art auf einer eigenen PDF-Ebene
    (Zeichnung, Aenderungen, Markierungen, Masse, Eingefuegte Bilder), in Acrobat ein- und ausblendbar."""
    import math
    import pymupdf
    h, w = img_bgr.shape[:2]
    k = 72.0 / dpi
    doc = pymupdf.open()
    page = doc.new_page(width=w * k, height=h * k)
    ocg = {}
    if layers:
        used = {"zeichnung"} | ({"aenderungen"} if regs else set()) | {ann_layer(a) for a in anns}
        for key, name in LAYERS:
            if key in used:
                ocg[key] = doc.add_ocg(name, on=True)
    ok, png = cv2.imencode(".png", img_bgr)
    page.insert_image(page.rect, stream=png.tobytes(), oc=ocg.get("zeichnung", 0))
    shape = img_bgr.shape

    def rgb(col):
        col = col.lstrip("#")
        return tuple(int(col[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def info(annot, subject, content):
        annot.set_info(title=tr("ZGmax"), subject=subject, content=content)

    for r in regs:
        pad = 12
        rect = pymupdf.Rect((r["x"] - pad) * k, (r["y"] - pad) * k, (r["x"] + r["w"] + pad) * k,
                            (r["y"] + r["h"] + pad) * k)
        an = page.add_rect_annot(rect)
        an.set_border(width=1.5, clouds=1)
        an.set_colors(stroke=rgb(STATUS_COLORS[reg_status(r)]))
        txt = [tr("Änderung {}: {}").format(r['nr'], TYPE_LABEL[r['typ']])]
        if r.get("text_a") or r.get("text_b"):
            txt.append(f"{r.get('text_a', '')} → {r.get('text_b', '')}")
        if r.get("dim"):
            txt.append(tr("Maß ") + r["dim"])
        if r.get("desc"):
            txt.append(r["desc"])
        txt.append(tr("Prüfung: ") + review_text(r))
        info(an, tr("Änderung {}").format(r['nr']), "\n".join(txt))
        if "aenderungen" in ocg:
            an.set_oc(ocg["aenderungen"])
        an.update()
    for a in anns:
        t = a["type"]
        if t in REDACT_TYPES:                         # steckt schon im Bild (eingebrannt)
            continue
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
            info(an, {"rect": tr("Rahmen"), "cloud": tr("Wolke"), "highlight": tr("Markierung")}[t], a.get("text", ""))
        elif t in ("arrow", "line"):
            an = page.add_line_annot(pymupdf.Point(x, y), pymupdf.Point(x2, y2))
            an.set_colors(stroke=col)
            an.set_border(width=lw)
            if t == "arrow":
                an.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, pymupdf.PDF_ANNOT_LE_CLOSED_ARROW)
            info(an, tr("Pfeil") if t == "arrow" else tr("Linie"), a.get("comment", ""))
        elif t == "ellipse":
            an = page.add_circle_annot(pymupdf.Rect(min(x, x2), min(y, y2), max(x, x2), max(y, y2)))
            an.set_colors(stroke=col)
            an.set_border(width=lw)
            info(an, tr("Ellipse"), a.get("comment", ""))
        elif t in PTS_TYPES and a.get("pts"):
            pts = [pymupdf.Point(q[0] * k, q[1] * k) for q in a["pts"]]
            if t == "pen":
                an = page.add_ink_annot([[(q.x, q.y) for q in pts]])
            elif t == "polygon":
                an = page.add_polygon_annot(pts)
            else:
                an = page.add_polyline_annot(pts)
            an.set_colors(stroke=col)
            an.set_border(width=lw)
            info(an, {"pen": tr("Freihand"), "polygon": tr("Polygon"), "polyline": tr("Linienzug")}[t],
                 a.get("comment", ""))
        elif t == "image":
            ok, png = cv2.imencode(".png", ann_image(a))
            if ok:
                page.insert_image(pymupdf.Rect(min(x, x2), min(y, y2), max(x, x2), max(y, y2)),
                                  stream=png.tobytes(), keep_proportion=False, oc=ocg.get("bilder", 0))
            continue
        elif t in ("text", "approval"):
            b = ann_bounds(shape, a)
            rect = pymupdf.Rect(b[0] * k, b[1] * k, b[2] * k + th, b[3] * k + th * 0.5)
            an = page.add_freetext_annot(rect, a.get("text", ""), fontsize=max(4, th * 0.85), text_color=col,
                                         border_color=col if t == "approval" else None)
            info(an, tr("Stempel") if t == "approval" else tr("Text"), a.get("text", ""))
        elif t == "number":
            rr = 0.95 * th
            an = page.add_circle_annot(pymupdf.Rect(x - rr, y - rr, x + rr, y + rr))
            an.set_colors(stroke=col, fill=col)
            an.set_border(width=0.5)
            info(an, tr("Nummer {}").format(a['nr']), tr("Nummer {}").format(a['nr']))
            if "markierungen" in ocg:
                an.set_oc(ocg["markierungen"])
            an.update()
            an = page.add_freetext_annot(pymupdf.Rect(x - rr, y - rr * 0.75, x + rr, y + rr), str(a["nr"]),
                                         fontsize=max(4, rr), text_color=(1, 1, 1), align=1)
            info(an, tr("Nummer {}").format(a['nr']), str(a["nr"]))
        elif t == "measure":
            pts = [pymupdf.Point(q[0] * k, q[1] * k) for q in (a.get("pts") or [[a["x"], a["y"]], [a["x2"], a["y2"]]])]
            an = page.add_polyline_annot(pts) if a.get("kind") != "area" else page.add_polygon_annot(pts)
            an.set_colors(stroke=col)
            an.set_border(width=max(0.5, measure_style(shape, a["size"])[0] * k))
            if a.get("kind", "dist") == "dist":
                an.set_line_ends(pymupdf.PDF_ANNOT_LE_CLOSED_ARROW, pymupdf.PDF_ANNOT_LE_CLOSED_ARROW)
            info(an, tr("Maß"), measure_text(a, mm) if mm else "")
            if mm:                                    # Wert auch sichtbar (nicht nur beim Anklicken)
                if "masse" in ocg:
                    an.set_oc(ocg["masse"])
                an.update()
                cx, cy, _ang, _ax, _ay = measure_label(a, shape)
                txt = measure_text(a, mm)
                mth = measure_style(shape, a["size"])[1] * k
                tw = pymupdf.get_text_length(txt, fontname="helv", fontsize=mth) + mth * 0.6
                an = page.add_freetext_annot(pymupdf.Rect(cx * k - tw / 2, cy * k - mth * 0.7, cx * k + tw / 2,
                                                          cy * k + mth * 0.7), txt, fontsize=mth, text_color=col,
                                             fill_color=(1, 1, 1), align=1)
                info(an, tr("Maß"), txt)
        else:
            continue
        if ann_layer(a) in ocg:
            an.set_oc(ocg[ann_layer(a)])
        an.update()
        _pdf_thread(doc, page, an, a, ocg.get(ann_layer(a)))
    doc.set_metadata({"title": f"Vergleich {names[0]} → {names[1]}", "creator": "ZGmax"})
    doc.save(path, deflate=True)
    doc.close()
    return path


def build_svg(path, img_bgr, size, regs, anns, dpi=200, mm=None, offset=(0, 0), ref_shape=None):
    """SVG mit Ebenen (Inkscape/Illustrator: Ebenen, sonst Gruppen): Zeichnung als eingebettetes Bild, Aenderungen
    und Markierungen als echte Vektorelemente (in Grafikprogrammen einzeln bearbeitbar). size = (Breite, Hoehe)
    in Bildpixeln, offset = Ursprung des Ausschnitts, img_bgr=None: ohne Zeichnung."""
    import base64
    import math
    from xml.sax.saxutils import escape
    W, H = size
    ox, oy = offset
    shape = _ref((H, W), ref_shape)
    mmw, mmh = W * 25.4 / dpi, H * 25.4 / dpi
    out = [f'<?xml version="1.0" encoding="UTF-8"?>\n'
           f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" width="{mmw:.2f}mm" height="{mmh:.2f}mm" '
           f'viewBox="0 0 {W} {H}">']

    def layer(key, body):
        if body:
            out.append(f'<g inkscape:groupmode="layer" id="{key}" inkscape:label="{escape(LAYER_NAMES[key])}">')
            out.extend(body)
            out.append("</g>")

    def P(x, y):
        return f"{x - ox:.1f},{y - oy:.1f}"

    def img_tag(bgra, x, y, w, h):
        ok, png = cv2.imencode(".png", bgra)
        data = base64.b64encode(png.tobytes()).decode("ascii") if ok else ""
        return (f'<image x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" preserveAspectRatio="none" '
                f'xlink:href="data:image/png;base64,{data}"/>')

    if img_bgr is not None:
        layer("zeichnung", [img_tag(img_bgr, 0, 0, W, H)])
    body = []
    for r in regs or []:
        col = STATUS_COLORS[reg_status(r)]
        body.append(f'<rect x="{r["x"] - ox - 12:.1f}" y="{r["y"] - oy - 12:.1f}" width="{r["w"] + 24}" '
                    f'height="{r["h"] + 24}" fill="none" stroke="{col}" stroke-width="{ann_line_w(shape, 1.5):.1f}"/>')
        body.append(f'<text x="{r["x"] - ox - 12:.1f}" y="{r["y"] - oy - 16:.1f}" fill="{col}" '
                    f'font-family="Arial" font-size="{ann_text_h(shape, 1.2):.1f}" font-weight="bold">{r["nr"]}</text>')
    layer("aenderungen", body)
    groups = {"markierungen": [], "masse": [], "bilder": [], "schwaerzung": []}
    for a in anns or []:
        t, col = a["type"], a.get("color", "#e11d48")
        if t in REDACT_TYPES:                         # steckt schon im Bild der Zeichnung (eingebrannt)
            continue
        th, lw = ann_text_h(shape, a["size"]), ann_line_w(shape, a["size"])
        x, y, x2, y2 = a["x"], a["y"], a["x2"], a["y2"]
        stroke = f'fill="none" stroke="{col}" stroke-width="{lw:.1f}" stroke-linecap="round" stroke-linejoin="round"'
        g = groups[ann_layer(a)]
        x0, y0, x1, y1 = min(x, x2), min(y, y2), max(x, x2), max(y, y2)
        if t == "rect":
            g.append(f'<rect x="{x0 - ox:.1f}" y="{y0 - oy:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" {stroke}/>')
        elif t == "highlight":
            g.append(f'<rect x="{x0 - ox:.1f}" y="{y0 - oy:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" '
                     f'fill="{col}" fill-opacity="0.37"/>')
        elif t == "ellipse":
            g.append(f'<ellipse cx="{(x0 + x1) / 2 - ox:.1f}" cy="{(y0 + y1) / 2 - oy:.1f}" rx="{(x1 - x0) / 2:.1f}" '
                     f'ry="{(y1 - y0) / 2:.1f}" {stroke}/>')
        elif t == "cloud":
            pl = cloud_points(x, y, x2, y2, cloud_radius(shape, a["size"]))
            g.append(f'<polygon points="{" ".join(P(*q) for q in pl)}" {stroke}/>')
        elif t in ("line", "arrow"):
            if t == "arrow":
                ang = math.atan2(y2 - y, x2 - x)
                head = max(5 * lw, 0.8 * th)
                bx, by = x2 - head * 0.8 * math.cos(ang), y2 - head * 0.8 * math.sin(ang)
                g.append(f'<line x1="{x - ox:.1f}" y1="{y - oy:.1f}" x2="{bx - ox:.1f}" y2="{by - oy:.1f}" {stroke}/>')
                tri = [(x2, y2), (x2 - head * math.cos(ang - 0.4), y2 - head * math.sin(ang - 0.4)),
                       (x2 - head * math.cos(ang + 0.4), y2 - head * math.sin(ang + 0.4))]
                g.append(f'<polygon points="{" ".join(P(*q) for q in tri)}" fill="{col}"/>')
            else:
                g.append(f'<line x1="{x - ox:.1f}" y1="{y - oy:.1f}" x2="{x2 - ox:.1f}" y2="{y2 - oy:.1f}" {stroke}/>')
        elif t in PTS_TYPES and a.get("pts"):
            tag = "polygon" if t == "polygon" else "polyline"
            g.append(f'<{tag} points="{" ".join(P(q[0], q[1]) for q in a["pts"])}" {stroke}/>')
        elif t in ("text", "approval"):
            lines = ann_lines(a, th)
            pad = 0.5 * th if t == "approval" else 0
            if t == "approval":
                b = ann_bounds(shape, a)
                g.append(f'<rect x="{b[0] - ox:.1f}" y="{b[1] - oy:.1f}" width="{b[2] - b[0]:.1f}" '
                         f'height="{b[3] - b[1]:.1f}" fill="white" stroke="{col}" stroke-width="{lw * 1.3:.1f}"/>')
            spans = "".join(f'<tspan x="{x - ox + pad:.1f}" dy="{th * (1.0 if i == 0 else 1.25):.1f}">{escape(s)}</tspan>'
                            for i, s in enumerate(lines))
            g.append(f'<text y="{y - oy + pad:.1f}" fill="{col}" font-family="Arial" font-size="{th:.1f}">{spans}</text>')
        elif t == "number":
            r = 0.95 * th
            g.append(f'<circle cx="{x - ox:.1f}" cy="{y - oy:.1f}" r="{r:.1f}" fill="{col}" stroke="white"/>')
            g.append(f'<text x="{x - ox:.1f}" y="{y - oy + th * 0.35:.1f}" fill="white" font-family="Arial" '
                     f'font-weight="bold" font-size="{stamp_font_h(th, a["nr"]):.1f}" text-anchor="middle">{a["nr"]}</text>')
        elif t == "measure":
            mlw, mth, alen = measure_style(shape, a["size"])
            for gk, gd in measure_geometry(a):
                if gk == "circle":
                    g.append(f'<circle cx="{gd[0] - ox:.1f}" cy="{gd[1] - oy:.1f}" r="{gd[2]:.1f}" fill="none" '
                             f'stroke="{col}" stroke-width="{mlw:.1f}"/>')
                else:
                    tag = "polygon" if gk == "poly" else "polyline"
                    g.append(f'<{tag} points="{" ".join(P(*q) for q in gd)}" fill="none" stroke="{col}" '
                             f'stroke-width="{mlw:.1f}"/>')
            pp = a.get("pts") or [[x, y], [x2, y2]]
            if a.get("kind", "dist") == "dist" and len(pp) >= 2:
                for tip, frm in ((pp[0], pp[1]), (pp[-1], pp[-2])):
                    g.append(f'<polygon points="{" ".join(P(*q) for q in arrow_head(tip, frm, alen))}" fill="{col}"/>')
            if mm:                                    # Wert ueber der Masslinie, parallel zu ihr
                cx, cy, ang, ax, ay = measure_label(a, shape)
                if a.get("lo"):
                    g.append(f'<line x1="{cx - ox:.1f}" y1="{cy - oy:.1f}" x2="{ax - ox:.1f}" y2="{ay - oy:.1f}" '
                             f'stroke="{col}" stroke-width="{mlw:.1f}"/>')
                g.append(f'<text x="{cx - ox:.1f}" y="{cy - oy + mth * 0.35:.1f}" fill="{col}" font-family="Arial" '
                         f'font-weight="bold" font-size="{mth:.1f}" text-anchor="middle" stroke="white" '
                         f'stroke-width="{mth / 6:.1f}" paint-order="stroke" '
                         f'transform="rotate({ang:.2f} {cx - ox:.1f} {cy - oy:.1f})">{escape(measure_text(a, mm))}</text>')
        elif t == "image":
            g.append(img_tag(ann_image(a), x0 - ox, y0 - oy, x1 - x0, y1 - y0))
    for key in ("markierungen", "masse", "bilder"):
        layer(key, groups[key])
    out.append("</svg>\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return path


def build_searchable_pdf(path, img_bgr, lines, dpi=200, title=""):
    """Durchsuchbares PDF: das Bild als Seite, darueber unsichtbarer Text aus der Texterkennung (oder dem PDF), so
    dass man in jedem PDF-Programm suchen, markieren und kopieren kann. lines = [(x0, y0, x1, y1, text), ...] in
    Bildpixeln. Hochkant stehender Text (Bemassung senkrecht) wird gedreht eingesetzt."""
    import pymupdf
    h, w = img_bgr.shape[:2]
    k = 72.0 / dpi
    doc = pymupdf.open()
    page = doc.new_page(width=w * k, height=h * k)
    ok, png = cv2.imencode(".png", img_bgr)
    page.insert_image(page.rect, stream=png.tobytes())
    n = 0
    for x0, y0, x1, y1, text in lines:
        text = "".join(ch if ord(ch) < 256 else "?" for ch in str(text)).strip()   # Helvetica: Latin-1 (ä, ß, Ø, ±, °)
        if not text:
            continue
        bw, bh = (x1 - x0) * k, (y1 - y0) * k
        vertical = bh > 1.8 * bw and len(text) > 1
        size = max(1.0, (bw if vertical else bh) * 0.8)
        length = pymupdf.get_text_length(text, fontname="helv", fontsize=size)
        span = bh if vertical else bw
        sx = span / length if length > 0 else 1.0
        if vertical:                                # von unten nach oben lesen (wie senkrechte Masszahlen)
            pt = pymupdf.Point(x1 * k - size * 0.25, y1 * k)
            page.insert_text(pt, text, fontname="helv", fontsize=size, render_mode=3, rotate=90,
                             morph=(pt, pymupdf.Matrix(1, sx)))
        else:
            pt = pymupdf.Point(x0 * k, y1 * k - size * 0.22)
            page.insert_text(pt, text, fontname="helv", fontsize=size, render_mode=3,
                             morph=(pt, pymupdf.Matrix(sx, 1)))
        n += 1
    doc.set_metadata({"title": title, "creator": "ZGmax"})
    doc.save(path, deflate=True)
    doc.close()
    return n
