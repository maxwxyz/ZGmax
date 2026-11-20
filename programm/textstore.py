"""Gelesener Text einer Zeichnung, dauerhaft gemerkt (damit dieselbe Zeichnung nicht wieder gelesen werden muss).

Erkannt wird die Datei an ihrem INHALT (Pruefsumme), nicht am Namen: eine umbenannte oder kopierte Zeichnung findet
ihren Text wieder, eine andere Datei unter gleichem Namen nicht. Je Datei, Seite und (bei PDF/SVG/DXF) Aufloesung eine
kleine Datei unter <Daten>/textcache mit den Teilen "h" (waagerecht), "v" (senkrecht), "s" (schraeg/kopfueber).
Der Ordner raeumt sich selbst auf: hoechstens MAX_FILES Dateien und MAX_MB, nichts Aelteres als MAX_DAYS (zuletzt
benutzt bleibt). Nur Texterkennung landet hier - echter PDF-Text ist ohnehin sofort da.
"""
import gzip
import hashlib
import json
import os
import re
import time

VER = 1                       # erhoehen, wenn sich die Erkennung so aendert, dass alte Ergebnisse nicht mehr gelten
MAX_FILES, MAX_MB, MAX_DAYS = 400, 40, 120
PARTS = ("h", "v", "s")
MAX_LINES = 100000            # mehr Textzeilen je Teil nimmt der Import aus einem Projekt nicht an
_ids = {}                     # (Pfad, Aenderungszeit, Groesse) -> Pruefsumme
_NAME = re.compile(r"^[0-9a-f]{40}-p\d+-d\d+\.json\.gz$")


def _dir():
    from ui_common import app_data_dir
    d = os.path.join(app_data_dir(), "textcache")
    os.makedirs(d, exist_ok=True)
    return d


def file_id(path):
    """Pruefsumme des ganzen Dateiinhalts (SHA-1, je Datei und Aenderungszeit nur einmal gerechnet) oder None."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (os.path.abspath(path), st.st_mtime_ns, st.st_size)
    if key not in _ids:
        h = hashlib.sha1(str(st.st_size).encode())
        try:
            with open(path, "rb") as f:                  # immer der ganze Inhalt: Stichproben uebersehen Aenderungen
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
        except OSError:
            return None
        if len(_ids) > 200:
            _ids.clear()
        _ids[key] = h.hexdigest()
    return _ids[key]


def name(fid, page, dpi):
    return f"{fid}-p{int(page)}-d{int(dpi)}.json.gz"


def _read(path):
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("ver") == VER else None
    except (OSError, ValueError, EOFError):
        return None


def load(fid, page, dpi):
    """Gemerkte Teile {"h": [...], "v": [...], "s": [...]} (nur vorhandene) oder {}. Zeilen als Listen
    [x0, y0, x1, y1, text, ...] in Bildpixeln der Datei."""
    if not fid:
        return {}
    p = os.path.join(_dir(), name(fid, page, dpi))
    d = _read(p)
    if d is None:
        return {}
    try:
        os.utime(p)                                  # zuletzt benutzt
    except OSError:
        pass
    return {k: [tuple(tuple(v) if isinstance(v, list) else v for v in ln) for ln in d[k]] for k in PARTS if k in d}


def save(fid, page, dpi, part, lines):
    """Einen Teil ("h", "v" oder "s") dazuschreiben (vorhandene Teile bleiben)."""
    if not fid or part not in PARTS:
        return False
    p = os.path.join(_dir(), name(fid, page, dpi))
    d = _read(p) or {"ver": VER}
    d[part] = [list(ln) for ln in lines]
    tmp = f"{p}.{os.getpid()}.tmp"
    try:
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, p)
        return True
    except (OSError, TypeError, ValueError):
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def prune(max_files=MAX_FILES, max_mb=MAX_MB, max_days=MAX_DAYS):
    """Aufraeumen: Altes, Ueberzaehliges und Fremdes entfernen (das zuletzt Benutzte bleibt). Gibt die Anzahl
    geloeschter Dateien zurueck."""
    d = _dir()
    items, n = [], 0
    for fn in os.listdir(d):
        p = os.path.join(d, fn)
        try:
            st = os.stat(p)
        except OSError:
            continue
        if not _NAME.match(fn):                      # Reste (.tmp) aelter als eine Stunde, sonst nichts anfassen
            if fn.endswith(".tmp") and time.time() - st.st_mtime > 3600:
                try:
                    os.remove(p)
                    n += 1
                except OSError:
                    pass
            continue
        items.append((st.st_mtime, st.st_size, p))
    items.sort(reverse=True)                         # neueste zuerst
    total, limit = 0, time.time() - max_days * 86400
    for i, (mt, size, p) in enumerate(items):
        total += size
        if i >= max_files or total > max_mb << 20 or mt < limit:
            try:
                os.remove(p)
                n += 1
            except OSError:
                pass
    return n


def export(fid, page, dpi):
    """Inhalt fuer das Mitspeichern im Projekt: (Dateiname, dict) oder None."""
    if not fid:
        return None
    d = _read(os.path.join(_dir(), name(fid, page, dpi)))
    return (name(fid, page, dpi), d) if d else None


def import_(fname, data):
    """Aus einem Projekt uebernehmen, wenn hier noch nichts dazu liegt. Der Name muss dem festen Muster entsprechen
    (kommt aus einer fremden Datei)."""
    if not _NAME.match(str(fname)) or not isinstance(data, dict) or data.get("ver") != VER:
        return False
    p = os.path.join(_dir(), fname)
    if os.path.exists(p):
        return False
    clean = {"ver": VER}
    for k in PARTS:
        if isinstance(data.get(k), list):
            clean[k] = [ln for ln in data[k][:MAX_LINES] if isinstance(ln, list) and 5 <= len(ln) <= 12
                        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in ln[:4])
                        and isinstance(ln[4], str) and len(ln[4]) <= 2000]
    tmp = f"{p}.{os.getpid()}.tmp"
    try:
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False)
        os.replace(tmp, p)
        return True
    except OSError:
        return False
