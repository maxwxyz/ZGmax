"""Kommentare austauschen: XFDF (Acrobat & Co.) und PDF-Anmerkungen einlesen, Markierungen als XFDF schreiben.

Alle Zwischenergebnisse sind "Kommentare" in PDF-Punkten mit Ursprung oben links (wie PyMuPDF):
  dict(kind, rect=(x0, y0, x1, y1), pts=[(x, y), ...], text, color '#rrggbb', author, date, cloudy, subject)
kind: rect, ellipse, line, polygon, polyline, text, note, highlight, ink, stamp
to_annotations() macht daraus Markierungen des Programms (Bildpixel bei 'dpi').
"""
import datetime as _dt
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

XFDF_NS = "http://ns.adobe.com/xfdf/"
_KIND = {"square": "rect", "circle": "ellipse", "line": "line", "polygon": "polygon", "polyline": "polyline",
         "freetext": "text", "text": "note", "highlight": "highlight", "underline": "highlight",
         "strikeout": "highlight", "squiggly": "highlight", "ink": "ink", "stamp": "stamp"}


def _floats(s):
    return [float(v) for v in re.split(r"[,;\s]+", (s or "").strip()) if v]


def _color(s, default="#e11d48"):
    s = (s or "").strip()
    return s.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", s) else default


def _local(tag):
    return tag.split("}", 1)[-1]


def parse_xfdf(path, page_h_pt, page=0):
    """XFDF lesen (nur Kommentare der Seite 'page', 0-basiert). page_h_pt = Seitenhoehe in Punkt
    (XFDF zaehlt y von unten). Gibt (Kommentare, Anzahl uebersprungener) zurueck."""
    root = ET.parse(path).getroot()
    out, skipped = [], 0
    annots = next((e for e in root.iter() if _local(e.tag) == "annots"), None)
    if annots is None:
        return out, 0
    flip = lambda x, y: (x, page_h_pt - y)                     # noqa: E731
    for e in annots:
        tag = _local(e.tag)
        if tag not in _KIND or int(e.get("page", 0) or 0) != page:
            skipped += tag not in _KIND
            continue
        r = _floats(e.get("rect"))
        fr = _floats(e.get("fringe"))                             # Rand fuer Wolkenboegen (links, unten, rechts, oben)
        if len(r) == 4 and len(fr) == 4:
            r = [r[0] + fr[0], r[1] + fr[1], r[2] - fr[2], r[3] - fr[3]]
        rect = None
        if len(r) == 4:
            (x0, y0), (x1, y1) = flip(r[0], r[3]), flip(r[2], r[1])
            rect = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        pts = []
        if tag == "line":
            pts = [flip(*_floats(e.get("start"))[:2]), flip(*_floats(e.get("end"))[:2])]
        elif tag in ("polygon", "polyline"):
            v = _floats(next((c.text for c in e if _local(c.tag) == "vertices"), e.get("vertices")))
            pts = [flip(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)]
        elif tag == "ink":
            for g in e.iter():
                if _local(g.tag) == "gesture":
                    v = _floats(g.text)
                    pts += [flip(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)]
        elif tag in ("highlight", "underline", "strikeout", "squiggly") and e.get("coords"):
            v = _floats(e.get("coords"))
            xy = [flip(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)]
            if xy:
                rect = (min(p[0] for p in xy), min(p[1] for p in xy), max(p[0] for p in xy), max(p[1] for p in xy))
        text = ""
        for c in e:
            if _local(c.tag) == "contents" and c.text:
                text = c.text
            elif _local(c.tag) == "contents-richtext" and not text:
                text = "".join(c.itertext())
        color = _color(e.get("color"))
        if tag == "freetext":                                   # Textfarbe steht im Stil
            m = re.search(r"color:\s*(#[0-9a-fA-F]{6})", e.get("defaultstyle", "") or "")
            color = _color(m.group(1) if m else e.get("color"), "#e11d48")
        out.append(dict(kind=_KIND[tag], rect=rect, pts=pts, text=(text or "").strip(), color=color,
                        author=e.get("title", ""), date=e.get("date", ""), subject=e.get("subject", ""),
                        cloudy=(e.get("style", "") or "").lower() == "cloudy", name=e.get("name"),
                        irt=e.get("inreplyto"), state=e.get("state"), statemodel=e.get("statemodel")))
    return out, skipped


def pdf_comments(path, page=1):
    """Anmerkungen einer PDF-Seite lesen (PyMuPDF). Gibt (Kommentare, Anzahl uebersprungener) zurueck."""
    import pymupdf
    names = {"Square": "rect", "Circle": "ellipse", "Line": "line", "Polygon": "polygon", "PolyLine": "polyline",
             "FreeText": "text", "Text": "note", "Highlight": "highlight", "Underline": "highlight",
             "StrikeOut": "highlight", "Squiggly": "highlight", "Ink": "ink", "Stamp": "stamp"}
    out, skipped = [], 0
    with pymupdf.open(path) as doc:
        pg = doc[max(0, min(page, doc.page_count) - 1)]
        for a in pg.annots() or []:
            t = a.type[1]
            if t not in names:
                skipped += t not in ("Popup", "Link", "Widget")
                continue
            info = a.info or {}
            stroke = (a.colors or {}).get("stroke") or (a.colors or {}).get("fill")
            color = "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in stroke[:3]) if stroke else "#e11d48"
            v = a.vertices or []
            if v and isinstance(v[0], (list, tuple)) and v and isinstance(v[0][0], (list, tuple)):
                v = [p for stroke_ in v for p in stroke_]          # Ink: Liste von Strichen
            pts = [(float(p[0]), float(p[1])) for p in v] if t in ("Line", "Polygon", "PolyLine", "Ink") else []
            r = a.rect
            rd = a.rect_delta                                     # Rand fuer Wolkenboegen herausrechnen
            if rd and t in ("Square", "Circle", "Polygon") and any(rd):
                r = pymupdf.Rect(r.x0 + rd[0], r.y0 + rd[1], r.x1 - rd[2], r.y1 - rd[3])
            border = a.border or {}
            st = doc.xref_get_key(a.xref, "State")
            sm = doc.xref_get_key(a.xref, "StateModel")
            out.append(dict(kind=names[t], rect=(r.x0, r.y0, r.x1, r.y1), pts=pts,
                            text=(info.get("content") or "").strip(), color=color, author=info.get("title", ""),
                            date=info.get("modDate", "") or info.get("creationDate", ""),
                            subject=info.get("subject", ""), cloudy=bool(border.get("clouds", 0) and border["clouds"] > 0),
                            name=str(a.xref), irt=str(a.irt_xref) if a.irt_xref > 0 else None,
                            state=st[1] if st[0] != "null" else None, statemodel=sm[1] if sm[0] != "null" else None))
    return out, skipped


def to_annotations(items, k, size=2.0, map_point=None):
    """Kommentare (PDF-Punkte) -> Markierungen des Programms (Bildpixel = Punkt * k). map_point(x, y) kann die
    Pixel zusaetzlich umrechnen (z. B. Kommentare zur neuen Zeichnung in deren ausgerichtete Lage)."""
    def P(x, y):
        x, y = x * k, y * k
        return map_point(x, y) if map_point else (x, y)

    from diffreport import STATE_FROM_PDF
    replies = [it for it in items if it.get("irt")]      # Antworten und Status gehoeren zu ihrer Markierung
    items = [it for it in items if not it.get("irt")]
    by_name = {}
    anns = []
    marks = []                                        # (Name, Index der ersten daraus entstandenen Markierung)
    for it in items:
        marks.append((it.get("name"), len(anns)))
        note = it.get("text", "")
        meta = dict(author=it.get("author", ""), date=it.get("date", ""), comment=note)
        base = dict(text="", nr=0, color=it.get("color") or "#e11d48", size=size, **meta)
        r = it.get("rect")
        box = None
        if r:
            (ax, ay), (bx, by) = P(r[0], r[1]), P(r[2], r[3])
            box = (min(ax, bx), min(ay, by), max(ax, bx), max(ay, by))
        kind = it["kind"]
        pts = [P(*p) for p in it.get("pts") or []]
        if kind == "ellipse" and box is not None and not it.get("cloudy"):
            anns.append(dict(base, type="ellipse", x=box[0], y=box[1], x2=box[2], y2=box[3]))
            continue
        if kind in ("polygon", "polyline", "ink") and not it.get("cloudy") and len(pts) >= 2:
            if kind == "ink":                            # Freihand: Punkte ausduennen
                step = max(1, len(pts) // 200)
                pts = pts[::step] + ([pts[-1]] if (len(pts) - 1) % step else [])
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            anns.append(dict(base, type={"ink": "pen"}.get(kind, kind), pts=[list(p) for p in pts],
                             x=min(xs), y=min(ys), x2=max(xs), y2=max(ys)))
            continue
        if kind in ("rect", "ellipse", "polygon", "highlight") or (kind == "polyline" and it.get("cloudy")):
            if kind in ("polygon", "polyline") and it.get("pts"):
                ps = [P(*p) for p in it["pts"]]
                box = (min(p[0] for p in ps), min(p[1] for p in ps), max(p[0] for p in ps), max(p[1] for p in ps))
            if box is None:
                continue
            t = "highlight" if kind == "highlight" else ("cloud" if it.get("cloudy") else "rect")
            anns.append(dict(base, type=t, x=box[0], y=box[1], x2=box[2], y2=box[3]))
        elif kind in ("line", "polyline", "ink") and len(it.get("pts") or []) >= 2:
            ps = [P(*p) for p in it["pts"]]
            step = 1 if kind != "ink" else max(1, len(ps) // 40)   # Freihandstriche vereinfachen
            ps = ps[::step] + ([ps[-1]] if (len(ps) - 1) % step else [])
            for i in range(len(ps) - 1):
                last = i == len(ps) - 2
                anns.append(dict(base, type="arrow" if (kind == "line" and last) else "line",
                                 x=ps[i][0], y=ps[i][1], x2=ps[i + 1][0], y2=ps[i + 1][1]))
        elif kind in ("text", "note", "stamp") and box is not None:
            txt = note or it.get("subject", "") or ("Notiz" if kind == "note" else "")
            if not txt:
                continue
            if kind == "stamp":
                anns.append(dict(base, type="approval", x=box[0], y=box[1], x2=box[0], y2=box[1],
                                 text=(it.get("subject") or txt).upper()))
            else:
                prefix = f"{it['author']}: " if (kind == "note" and it.get("author")) else ""
                anns.append(dict(base, type="text", x=box[0], y=box[1], x2=box[0], y2=box[1], text=prefix + txt))
    for (name, i0), nxt in zip(marks, [m[1] for m in marks[1:]] + [len(anns)]):
        if name and i0 < nxt:
            by_name[name] = anns[i0]
    for rp in replies:                                # Unterhaltung an die Markierung haengen
        parent = by_name.get(rp["irt"])
        if parent is None:
            continue
        who = rp.get("author", "")
        if rp.get("state") and (rp.get("statemodel") or "Review").lower() == "review":
            parent.setdefault("states", {})[who] = STATE_FROM_PDF.get(rp["state"].lower(), "none")
        elif rp.get("text"):
            parent.setdefault("replies", []).append(dict(author=who, date=rp.get("date", ""), text=rp["text"]))
    return anns


def write_xfdf(path, anns, k, page_h_pt, pdf_name="", page=0, measure_text=None):
    """Markierungen als XFDF schreiben (in Acrobat: Kommentare > Importieren). k = Pixel je Punkt."""
    def X(x):
        return f"{x / k:.2f}"

    def Y(y):
        return f"{page_h_pt - y / k:.2f}"

    now = _dt.datetime.now().strftime("D:%Y%m%d%H%M%S")
    rows = []
    from diffreport import PDF_STATE, ann_id
    for a in anns:
        t = a["type"]
        if t in ("redact", "pixelate"):              # Schwaerzungen sind keine Kommentare
            continue
        n_rows = len(rows)
        col = a.get("color", "#e11d48")
        aid = a.get("id") or ann_id(dict(a))
        common = (f'page="{page}" color="{col}" title="{escape(a.get("author") or "ZGmax")}" '
                  f'date="{escape(a.get("date") or now)}" width="1.5" name="{escape(aid)}"')
        contents = a.get("comment") or a.get("text") or ""
        x0, y0 = min(a["x"], a["x2"]), min(a["y"], a["y2"])
        x1, y1 = max(a["x"], a["x2"]), max(a["y"], a["y2"])
        rect = f'rect="{X(x0)},{Y(y1)},{X(x1)},{Y(y0)}"'
        body = f"<contents>{escape(contents)}</contents>" if contents else ""
        if t in ("rect", "cloud"):
            style = ' style="cloudy" intensity="1"' if t == "cloud" else ""
            rows.append(f"<square {common} {rect}{style}>{body}</square>")
        elif t == "highlight":
            rows.append(f'<square {common} {rect} opacity="0.35" interior-color="{col}">{body}</square>')
        elif t in ("arrow", "line"):
            tail = ' tail="ClosedArrow"' if t == "arrow" else ""
            rows.append(f'<line {common} {rect} start="{X(a["x"])},{Y(a["y"])}" end="{X(a["x2"])},{Y(a["y2"])}"'
                        f'{tail}>{body}</line>')
        elif t in ("text", "approval", "number"):
            txt = str(a["nr"]) if t == "number" else a.get("text", "")
            lines = (txt or " ").split("\n")
            wpt, hpt = max(40.0, 7.0 * max(len(s) for s in lines)), 14.0 * len(lines)
            xl, ytop = a["x"] / k, page_h_pt - a["y"] / k
            r2 = f'rect="{xl:.2f},{ytop - hpt:.2f},{xl + wpt:.2f},{ytop:.2f}"'
            rows.append(f'<freetext {common} {r2} defaultstyle="font: Helvetica 10pt; color:{col}">'
                        f"<contents>{escape(txt)}</contents></freetext>")
        elif t == "ellipse":
            rows.append(f"<circle {common} {rect}>{body}</circle>")
        elif t in ("pen", "polyline", "polygon") and a.get("pts"):
            verts = ";".join(f"{X(p[0])},{Y(p[1])}" for p in a["pts"])
            if t == "pen":
                rows.append(f"<ink {common} {rect}><inklist><gesture>{verts}</gesture></inklist>{body}</ink>")
            else:
                rows.append(f"<{t} {common} {rect}><vertices>{verts}</vertices>{body}</{t}>")
        elif t == "measure":
            pts = a.get("pts") or [[a["x"], a["y"]], [a["x2"], a["y2"]]]
            verts = ";".join(f"{X(p[0])},{Y(p[1])}" for p in pts)
            val = measure_text(a) if measure_text else ""
            rows.append(f'<polyline {common} {rect}><vertices>{verts}</vertices>'
                        f"<contents>{escape(val)}</contents></polyline>")
        if len(rows) > n_rows:                        # Unterhaltung: Antworten und Status (inreplyto)
            for j, r in enumerate(a.get("replies") or []):
                rows.append(f'<text page="{page}" {rect} color="{col}" title="{escape(r.get("author") or "")}" '
                            f'date="{escape(r.get("date") or now)}" name="{escape(aid)}-r{j}" '
                            f'inreplyto="{escape(aid)}"><contents>{escape(r.get("text", ""))}</contents></text>')
            for j, (who, st) in enumerate((a.get("states") or {}).items()):
                rows.append(f'<text page="{page}" {rect} color="{col}" title="{escape(who)}" date="{now}" '
                            f'name="{escape(aid)}-s{j}" inreplyto="{escape(aid)}" state="{PDF_STATE.get(st, "None")}" '
                            f'statemodel="Review"><contents>{escape(PDF_STATE.get(st, "None"))}</contents></text>')
    href = f'<f href="{escape(pdf_name)}"/>' if pdf_name else ""
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<xfdf xmlns="{XFDF_NS}" xml:space="preserve">\n'
           f"{href}<annots>\n" + "\n".join(rows) + "\n</annots>\n</xfdf>\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)
    return len(rows)
