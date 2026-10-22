#!/usr/bin/env python3
"""Erzeugt das Programm-Symbol (icon.png, icon.ico, icon.icns) im Ordner 'programm'.
Aufruf nur noetig, wenn das Symbol geaendert werden soll:  python packaging/make_icon.py"""
import os

from PIL import Image, ImageDraw

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "programm")
S = 1024                    # Zeichengroesse (wird verkleinert = glatte Kanten)


def draw(size=S):
    k = size / 1024.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def box(x0, y0, x1, y1):
        return [x0 * k, y0 * k, x1 * k, y1 * k]

    # Hintergrund: abgerundetes Quadrat in dunklem Blau
    d.rounded_rectangle(box(40, 40, 984, 984), radius=210 * k, fill=(30, 41, 59, 255))
    # Blatt A (alt, rot) hinten links oben, Blatt B (neu, blau) vorne rechts unten
    d.rounded_rectangle(box(190, 190, 640, 700), radius=40 * k, fill=(251, 113, 133, 70),
                        outline=(251, 113, 133, 255), width=int(26 * k))
    d.rounded_rectangle(box(384, 324, 834, 834), radius=40 * k, fill=(96, 165, 250, 70),
                        outline=(96, 165, 250, 255), width=int(26 * k))
    # Ueberlappung hell (= gleich) mit zwei Linien als "Zeichnung"
    d.rectangle(box(396, 336, 628, 688), fill=(226, 232, 240, 235))
    for y, x1 in ((420, 590), (520, 590), (620, 500)):
        d.line([(440 * k, y * k), (x1 * k, y * k)], fill=(71, 85, 105, 255), width=int(26 * k))
    # Gruener Haken-Punkt: "Unterschied gefunden"
    d.ellipse(box(690, 690, 880, 880), fill=(34, 197, 94, 255), outline=(30, 41, 59, 255), width=int(18 * k))
    d.line([(735 * k, 788 * k), (770 * k, 826 * k), (838 * k, 744 * k)], fill=(255, 255, 255, 255),
           width=int(26 * k), joint="curve")
    return img


def main():
    big = draw()
    big.resize((256, 256), Image.LANCZOS).save(os.path.join(HERE, "icon.png"))
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    big.resize((256, 256), Image.LANCZOS).save(os.path.join(HERE, "icon.ico"), sizes=sizes)
    try:
        big.save(os.path.join(HERE, "icon.icns"))
    except Exception:                                    # noqa: BLE001
        pass
    print("Symbole erzeugt in", HERE)


if __name__ == "__main__":
    main()
