#!/usr/bin/env python3
"""
ZGmax Kommandozeile (Raster): vergleicht zwei gescannte Zeichnungen (TIF, PNG, JPG).

Das Skript richtet beide Bilder aufeinander aus (Verschiebung, Drehung, Skalierung,
lokale Feinausrichtung), blendet Schraffuren mit gleicher Dichte aus und erzeugt ein
Ergebnisbild mit Legende rechts daneben.

Farben im Ergebnisbild:
  rot   = nur in A vorhanden (entfernt oder geaendert)
  blau  = nur in B vorhanden (neu oder geaendert)
  grau  = in beiden Bildern gleich
  gruen = gleich, aber verschoben oder leicht gedreht (nur wenn solche Bereiche erkannt wurden)
  weiss = Hintergrund
"""
EPILOG = """\
Beispiele:
  Ganze Zeichnungen vergleichen (Standardwerte reichen meist):
    python drawing_diff.py alt.tif neu.tif --out diff.png

  Ausschnitt in A mit der Maus waehlen, passender Bereich in B wird automatisch gefunden:
    python drawing_diff.py alt.tif neu.tif --select

  Ausschnitt per Koordinaten (x,y,Breite,Hoehe in Pixeln von A):
    python drawing_diff.py alt.tif neu.tif --crop-a 4000,1500,4000,2500

  Weniger Rauschen / feine Aenderungen sichtbar halten:
    python drawing_diff.py alt.tif neu.tif --tol 3
    python drawing_diff.py alt.tif neu.tif --tol 1

  Verschobene Bereiche als Aenderung werten, Schraffur nicht unterdruecken:
    python drawing_diff.py alt.tif neu.tif --move 0 --hatch 0

  Einzelne Objekte (Masse, Texte) duerfen verschoben/gedreht sein, ohne als Aenderung zu gelten:
    python drawing_diff.py alt.tif neu.tif --obj-shift 60 --obj-rotate 5   # grosszuegiger
    python drawing_diff.py alt.tif neu.tif --obj-shift 10 --obj-rotate 0   # nur kleine Verschiebung
    python drawing_diff.py alt.tif neu.tif --obj-shift 0                   # Verschiebungen sind Aenderungen
    python drawing_diff.py alt.tif neu.tif --verbose                       # zeigt, was verschoben wurde

  Rauschen/Rahmen ausblenden, Aenderungen nummerieren, Liste und PDF-Bericht erzeugen:
    python drawing_diff.py alt.tif neu.tif --min-area 30 --ignore-border 40 --mark --list --report
    python drawing_diff.py alt.tif neu.tif --ignore 9000,5000,1500,800     # Zone ausnehmen
    python drawing_diff.py alt.tif neu.tif --text-diff --index-check       # OCR (rapidocr-onnxruntime)

  Interaktive Ansicht: python drawing_viewer.py alt.tif neu.tif

  Stapel: ALT und NEU sind Ordner, gleich benannte Dateien werden paarweise verglichen
    python drawing_diff.py Ordner_alt Ordner_neu --out Ergebnisse --list

  Verschiedene Formate mischen (PDF wird mit --dpi gerendert) und als PDF ausgeben:
    python drawing_diff.py alt.pdf neu.png --dpi 200 --out diff.pdf
    python drawing_diff.py alt.tif neu.tif --format jpg --quality 90

  Mehrseitige PDF/TIFF: Seite waehlen
    python drawing_diff.py alt.pdf neu.pdf --page-a 2 --page-b 2

Eingabeformate:  PNG, JPG, TIF/TIFF (auch mehrseitig), BMP, WEBP, JP2, GIF, PDF, SVG, XPS, DXF
Ausgabeformate:  PNG (Standard), JPG, TIF, PDF, BMP, WEBP
DXF wird direkt gelesen. Nicht direkt lesbar: DWG, STEP, JT -> vorher als DXF oder PDF exportieren.

Tipps:
  * 1 Pixel entspricht bei 200 dpi etwa 0,13 mm (bei 150 dpi etwa 0,17 mm).
  * Viele rote/blaue Doppellinien      -> --tol erhoehen oder --cell verkleinern.
  * Blasse oder gelbe Linien fehlen    -> --thr erhoehen (z.B. 180).
  * Ausrichtung geht schief            -> --align translation oder engerer Ausschnitt.

Voraussetzung: pip install opencv-python numpy pillow pymupdf
Ausfuehrliche Anleitung: Anleitung_Kommandozeile.html (im selben Ordner)
"""
import argparse
import logging
import os
import sys

import cv2
import numpy as np

from diffcore import *   # noqa: F401,F403
from diffcore import OUT_FORMATS, DiffError
import diffpipe as dp
import diffreport as rep

# ----------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(
        prog="drawing_diff.py",
        usage="python %(prog)s ALT NEU [Optionen]",
        description=__doc__,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )

    g = p.add_argument_group("Eingabe / Ausgabe")
    g.add_argument("a", metavar="ALT", help="Bild A = Referenz (meist der alte Stand). "
                   "Das Ergebnis hat die Groesse von A. Formate: PNG, JPG, TIF/TIFF, BMP, WEBP, "
                   "JP2, GIF, PDF, SVG, XPS.")
    g.add_argument("b", metavar="NEU", help="Bild B = Vergleichsbild (meist der neue Stand). "
                   "Wird auf A ausgerichtet. Darf ein anderes Format als A haben.")
    g.add_argument("--out", metavar="DATEI", default="diff.png",
                   help="Name der Ergebnisdatei; das Format folgt der Endung, z.B. diff.pdf "
                        "(Standard: diff.png)")
    g.add_argument("--format", choices=OUT_FORMATS, metavar="FORMAT",
                   help="Ausgabeformat: " + ", ".join(OUT_FORMATS) + ". Ueberschreibt die Endung "
                        "von --out (Standard: Endung von --out, sonst png)")
    g.add_argument("--quality", type=int, default=95, metavar="1-100",
                   help="Qualitaet bei jpg/webp (Standard: 95)")
    g.add_argument("--dpi", type=int, default=200, metavar="DPI",
                   help="Aufloesung zum Rendern von PDF/SVG und als Angabe in tif/pdf-Ausgabe "
                        "(Standard: 200). Hoeher = genauer, aber mehr Speicher.")
    g.add_argument("--page-a", type=int, default=1, metavar="N",
                   help="Seite in A bei mehrseitigen PDF/TIFF (Standard: 1)")
    g.add_argument("--page-b", type=int, default=1, metavar="N",
                   help="Seite in B bei mehrseitigen PDF/TIFF (Standard: 1)")
    g.add_argument("--no-legend", action="store_true",
                   help="keine Legende (Farben, Dateinamen, Einstellungen) rechts anhaengen")

    g = p.add_argument_group("Ausschnitt waehlen (optional)")
    g.add_argument("--select", action="store_true",
                   help="Ausschnitt in A mit der Maus waehlen (Rahmen aufziehen, ENTER = OK, "
                        "ESC = ganzes Bild)")
    g.add_argument("--crop-a", metavar="x,y,b,h",
                   help="Ausschnitt in A in Pixeln: x,y (obere linke Ecke), Breite, Hoehe")
    g.add_argument("--crop-b", metavar="x,y,b,h",
                   help="Ausschnitt in B in Pixeln (nur noetig bei --fit off)")
    g.add_argument("--fit", choices=["auto", "manual", "off"], default="auto",
                   help="Wie der passende Ausschnitt in B bestimmt wird: auto = automatisch in B "
                        "suchen; manual = mit --select auch in B per Maus waehlen (Seitenverhaeltnis "
                        "von A gesperrt); off = ganzes B bzw. --crop-b (Standard: auto)")
    g.add_argument("--keep-aspect-check", action="store_true",
                   help="abbrechen statt nur warnen, wenn die Seitenverhaeltnisse der Ausschnitte "
                        "stark abweichen")

    g = p.add_argument_group("Erkennung von Linien")
    g.add_argument("--thr", type=int, default=128, metavar="0-255",
                   help="Helligkeitsschwelle: dunkler = Linie. Hoeher erfasst auch blasse/gelbe "
                        "Linien, aber mehr Rauschen (Standard: 128)")

    g = p.add_argument_group("Ausrichtung")
    g.add_argument("--align", choices=["none", "translation", "euclidean", "affine"],
                   default="affine",
                   help="globale Ausrichtung: none = keine; translation = nur Verschiebung; "
                        "euclidean = + Drehung; affine = + Skalierung (Standard: affine)")
    g.add_argument("--tiles", default="auto", metavar="auto|SxZ",
                   help="lokale Feinausrichtung in Kacheln: auto = Kacheln von ca. --cell px; "
                        "z.B. 6x3 = 6 Spalten x 3 Zeilen; 1x1 = aus (Standard: auto)")
    g.add_argument("--cell", type=int, default=400, metavar="PX",
                   help="Kachelgroesse in Pixeln bei --tiles auto (Standard: 400)")
    g.add_argument("--max-shift", type=int, default=30, metavar="PX",
                   help="max. Verschiebung je Kachel bei der Feinausrichtung (Standard: 30)")

    g = p.add_argument_group("Vergleich")
    g.add_argument("--tol", type=int, default=2, metavar="PX",
                   help="Toleranz: Linien mit weniger als PX Abstand gelten als gleich. "
                        "0 = streng, hoeher = weniger Rauschen (Standard: 2)")
    g.add_argument("--hatch", type=int, default=16, metavar="PX",
                   help="Schraffur-Unterdrueckung: max. Linienabstand der Schraffur in px. "
                        "Gleich dichte Schraffur in beiden Bildern gilt nicht als Aenderung; "
                        "0 = aus (Standard: 16)")
    g.add_argument("--move", type=int, default=100, metavar="PX",
                   help="Suchbereich fuer komplett verschobene Bloecke (werden gruen markiert, "
                        "wenn der Inhalt gleich ist); 0 = aus (Standard: 100)")
    g.add_argument("--obj-shift", type=int, default=40, metavar="PX",
                   help="Einzelne Objekte (z.B. ein Mass, ein Text), die nur um bis zu PX Pixel "
                        "verschoben sind, gelten nicht als Aenderung und werden gruen markiert; "
                        "0 = aus (Standard: 40)")
    g.add_argument("--obj-rotate", type=float, default=3.0, metavar="GRAD",
                   help="Wie --obj-shift, aber zusaetzlich um bis zu GRAD Grad gedreht "
                        "(Verschiebung + Drehung zusammen); 0 = keine Drehung (Standard: 3)")

    g = p.add_argument_group("Zonen und Filter")
    g.add_argument("--min-area", type=int, default=20, metavar="PX",
                   help="Unterschiede, die zusammen weniger als PX Pixel haben, werden ignoriert "
                        "(Rauschen, Staub); 0 = aus (Standard: 20)")
    g.add_argument("--keep-edges", action="store_true",
                   help="1 px duenne Saeume direkt an gemeinsamen Linien NICHT ausblenden (Standard: ausblenden, "
                        "weil das fast immer nur Versatz/Strichstaerke beim Scannen oder Rendern ist)")
    g.add_argument("--ignore", action="append", default=[], metavar="x,y,b,h",
                   help="Zone, die nicht verglichen wird (Pixel von A, wie --crop-a); "
                        "mehrfach angebbar, z.B. fuer Schriftfeld oder Stempel")
    g.add_argument("--ignore-border", type=int, default=0, metavar="PX",
                   help="Randstreifen der Breite PX, der nicht verglichen wird (Zeichnungsrahmen)")

    g = p.add_argument_group("Auswertung (alles optional, Standard: aus)")
    g.add_argument("--list", nargs="?", const="", metavar="DATEI.csv",
                   help="Aenderungsliste als CSV schreiben (Nr, Typ, Position, Groesse, Pixel). "
                        "Ohne Namen: <out>_aenderungen.csv")
    g.add_argument("--mark", action="store_true",
                   help="Aenderungen im Ergebnisbild mit nummerierten orangen Rahmen markieren")
    g.add_argument("--report", nargs="?", const="", metavar="DATEI.pdf",
                   help="PDF-Bericht mit Uebersicht, Liste und Detailansichten (A | B | Vergleich). "
                        "Ohne Namen: <out>_bericht.pdf")
    g.add_argument("--report-max", type=int, default=40, metavar="N",
                   help="maximale Anzahl Detailansichten im Bericht (Standard: 40)")
    g.add_argument("--text-diff", action="store_true",
                   help="Text in geaenderten Bereichen per OCR lesen und A/B vergleichen "
                        "(braucht: pip install rapidocr-onnxruntime)")
    g.add_argument("--index-check", action="store_true",
                   help="Schriftfeld (rechts unten) per OCR lesen, Index A/B vergleichen und auf "
                        "Plausibilitaet mit den Aenderungen pruefen (braucht rapidocr-onnxruntime)")

    g = p.add_argument_group("Hilfe")
    g.add_argument("--verbose", action="store_true",
                   help="zusaetzliche Angaben ausgeben (z.B. welche Objekte verschoben/gedreht wurden)")
    g.add_argument("-h", "--help", action="help", help="diese Hilfe anzeigen und beenden")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    if os.path.isdir(args.a) and os.path.isdir(args.b):
        return run_batch(args)
    if os.path.isdir(args.a) or os.path.isdir(args.b):
        sys.exit("ALT und NEU muessen beide Dateien oder beide Ordner sein.")
    run(args)


def run_batch(args):
    """Stapelmodus: gleich benannte Dateien aus Ordner ALT und Ordner NEU werden paarweise verglichen."""
    import copy
    exts = RASTER_EXT | VECTOR_EXT

    def scan(folder):
        return {os.path.splitext(f)[0].lower(): f for f in sorted(os.listdir(folder))
                if os.path.splitext(f)[1].lower() in exts}
    fa, fb = scan(args.a), scan(args.b)
    names = sorted(set(fa) & set(fb))
    if not names:
        sys.exit("Keine gleich benannten Dateien in beiden Ordnern gefunden.")
    only = sorted(set(fa) ^ set(fb))
    if only:
        print(f"Hinweis: {len(only)} Dateien ohne Gegenstueck werden uebersprungen.")
    outdir = args.out
    if os.path.splitext(outdir)[1].lower() in {"." + e for e in OUT_FORMATS}:
        outdir = "Ergebnisse"
    os.makedirs(outdir, exist_ok=True)
    ext = args.format or "png"
    ok = 0
    for i, n in enumerate(names, 1):
        print(f"\n=== [{i}/{len(names)}] {fa[n]} <-> {fb[n]} ===")
        a2 = copy.copy(args)
        a2.a, a2.b = os.path.join(args.a, fa[n]), os.path.join(args.b, fb[n])
        a2.out = os.path.join(outdir, os.path.splitext(fa[n])[0] + "_diff." + ext)
        a2.select, a2.crop_a, a2.crop_b = False, None, None
        a2.list = "" if args.list is not None else None
        a2.report = "" if args.report is not None else None
        try:
            run(a2)
            ok += 1
        except (Exception, SystemExit) as e:             # noqa: BLE001
            print(f"  FEHLER bei {n}: {e}", file=sys.stderr)
    print(f"\nStapel fertig: {ok} von {len(names)} Paaren, Ergebnisse in: {os.path.abspath(outdir)}")


def run(args):
    boxa, boxb = parse_box(args.crop_a), parse_box(args.crop_b)
    A_full = load_ink(args.a, args.thr, args.page_a, args.dpi)
    B_full = load_ink(args.b, args.thr, args.page_b, args.dpi)
    if args.select:
        boxa = select_roi(A_full, "Ausschnitt A waehlen (ENTER bestaetigen)")
    a = crop(A_full, boxa)

    if boxb is None and args.select and args.fit == "manual":
        boxb = select_roi(B_full, "Ausschnitt B waehlen", ratio=a.shape[1] / a.shape[0])
    elif boxb is None and args.fit == "auto" and boxa is not None:
        print("Suche Ausschnitt A in B (automatisch) ...")
        boxb, score = autofit(a, B_full)
        if boxb is None:
            print("  Warnung: nichts gefunden, nutze ganzes Bild B", file=sys.stderr)
        else:
            print(f"  gefunden: {boxb}  (Uebereinstimmung {score:.2f})")
            if score < 0.15:
                print("  Warnung: schwache Uebereinstimmung - Ergebnis pruefen, evtl. "
                      "--fit manual oder groesseren Ausschnitt waehlen", file=sys.stderr)
    if args.select or boxb:
        print(f"  --crop-a {','.join(map(str, boxa)) if boxa else ''}  "
              f"--crop-b {','.join(map(str, boxb)) if boxb else ''}")
    b = crop(B_full, boxb)
    print(f"  A: {a.shape[1]}x{a.shape[0]}   B: {b.shape[1]}x{b.shape[0]}")

    ra, rb = a.shape[1] / a.shape[0], b.shape[1] / b.shape[0]
    if abs(ra / rb - 1) > 0.03:
        msg = f"Seitenverhaeltnis weicht ab (A {ra:.3f}, B {rb:.3f}) - Ausschnitte pruefen!"
        if args.keep_aspect_check:
            sys.exit(msg)
        print("  Warnung: " + msg, file=sys.stderr)

    # B auf Groesse und Lage von A bringen (siehe diffpipe.prepare_pair)
    b = dp.prepare_pair(a, b, args.align)

    zones = [parse_box(z) for z in args.ignore]
    params = dp.Params(thr=args.thr, align=args.align, tiles=args.tiles, cell=args.cell,
                       max_shift=args.max_shift, tol=args.tol, hatch=args.hatch, move=args.move,
                       obj_shift=args.obj_shift, obj_rotate=args.obj_rotate, min_area=args.min_area,
                       ignore=zones, ignore_border=args.ignore_border, verbose=args.verbose,
                       edge_noise=not args.keep_edges)
    res = dp.run_compare(a, b, params)

    out_path, out_fmt = resolve_output(args.out, args.format)
    base = os.path.splitext(out_path)[0]
    want_regs = args.list is not None or args.mark or args.report is not None \
        or args.text_diff or args.index_check
    regs, index = [], None
    if want_regs:
        regs = rep.find_regions(res)
        print(f"Aenderungen: {len(regs)} Bereiche")
        if (args.text_diff or args.index_check) and not rep.ocr_available():
            print("  Warnung: OCR nicht installiert (pip install rapidocr-onnxruntime) - "
                  "Textvergleich/Index-Abgleich uebersprungen", file=sys.stderr)
        else:
            if args.text_diff:
                rep.text_diff(res, regs)
            if args.index_check:
                index = rep.index_check(res, regs)

    out = dp.render_result(res)
    if args.mark:
        rep.draw_marks(out, regs)
    info = tr("Toleranz {}px, Schraffur {}, Verschiebung {}, Objekt-Verschiebung {}px, Objekt-Drehung {}Grad, "
              "Kacheln {}x{}, Ausrichtung {}, Schwelle {}").format(args.tol, args.hatch, args.move, args.obj_shift,
                                                                  args.obj_rotate, res.nx, res.ny, args.align, args.thr)
    if args.min_area:
        info += f", Min-Area {args.min_area}px"
    if zones or args.ignore_border:
        info += tr(", {} Zone(n) ausgeblendet").format(len(zones)) + (
            tr(", Rand {}px").format(args.ignore_border) if args.ignore_border else "")
    if not args.no_legend:
        out = add_legend(out, os.path.basename(args.a), os.path.basename(args.b),
                         bool(res.moved.any()), info)
    out_path, out_fmt = save_output(out, out_path, out_fmt, args.dpi, args.quality)
    print(f"Gespeichert: {out_path}  ({out.shape[1]}x{out.shape[0]}, {out_fmt.upper()})")

    if args.list is not None:
        csv_path = args.list or base + "_aenderungen.csv"
        rep.write_csv(csv_path, regs, args.dpi)
        print(f"Liste: {csv_path}  ({len(regs)} Zeilen)")
    if args.report is not None:
        pdf_path = args.report or base + "_bericht.pdf"
        n = rep.build_report(pdf_path, res, regs, os.path.basename(args.a), os.path.basename(args.b),
                             args.dpi, info, index, args.report_max)
        print(f"Bericht: {pdf_path}  ({n} Seiten)")


if __name__ == "__main__":
    try:
        main()
    except DiffError as e:
        sys.exit(str(e))
