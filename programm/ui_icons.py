"""Einheitliche Linien-Symbole (vektoriell gezeichnet, passend zum Farbschema, scharf auf Retina).

icon(name) liefert ein QIcon; Zustand "an" (z. B. gedrueckter Werkzeugknopf) wird weiss gezeichnet.
Die Zeichnungen arbeiten in einem 24 x 24-Raster.
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap

from ui_theme import THEME, UI_FONT

_cache = {}


def _arrow_head(p, x, y, ang, size=4.0):
    for d in (-0.5, 0.5):
        p.drawLine(QPointF(x, y), QPointF(x - size * math.cos(ang + d), y - size * math.sin(ang + d)))


def _draw(p, name):
    """Zeichnet das Symbol 'name' mit dem aktuellen Stift (24er-Raster)."""
    r = QRectF
    if name == "open":
        path = QPainterPath()
        path.moveTo(3, 7)
        path.lineTo(3, 19)
        path.lineTo(19, 19)
        path.lineTo(21, 10)
        path.lineTo(7, 10)
        path.lineTo(5, 19)
        p.drawPath(path)
        path = QPainterPath()
        path.moveTo(3, 7)
        path.lineTo(3, 5)
        path.lineTo(9, 5)
        path.lineTo(11, 7)
        path.lineTo(18, 7)
        path.lineTo(18, 10)
        p.drawPath(path)
    elif name == "compare":
        p.drawRoundedRect(r(3, 3, 12, 12), 1.5, 1.5)
        p.drawRoundedRect(r(9, 9, 12, 12), 1.5, 1.5)
    elif name == "fit":
        for (cx, cy, sx, sy) in ((4, 4, 1, 1), (20, 4, -1, 1), (4, 20, 1, -1), (20, 20, -1, -1)):
            p.drawLine(QPointF(cx, cy), QPointF(cx + 5 * sx, cy))
            p.drawLine(QPointF(cx, cy), QPointF(cx, cy + 5 * sy))
        p.drawRect(r(9, 9, 6, 6))
    elif name in ("zoom_in", "zoom_out", "loupe", "zoom_box"):
        c = (10, 10) if name != "zoom_box" else (13, 13)
        rad = 6 if name != "zoom_box" else 5
        p.drawEllipse(QPointF(*c), rad, rad)
        p.drawLine(QPointF(c[0] + rad * 0.72, c[1] + rad * 0.72), QPointF(21, 21))
        if name == "zoom_in":
            p.drawLine(QPointF(7, 10), QPointF(13, 10))
            p.drawLine(QPointF(10, 7), QPointF(10, 13))
        elif name == "zoom_out":
            p.drawLine(QPointF(7, 10), QPointF(13, 10))
        elif name == "zoom_box":
            pen = p.pen()
            dash = QPen(pen)
            dash.setDashPattern([2, 2])
            p.setPen(dash)
            p.drawRect(r(2.5, 2.5, 9, 7))
            p.setPen(pen)
    elif name == "save":
        p.drawLine(QPointF(12, 3), QPointF(12, 15))
        _arrow_head(p, 12, 15, math.pi / 2, 5)
        path = QPainterPath()
        path.moveTo(4, 14)
        path.lineTo(4, 20)
        path.lineTo(20, 20)
        path.lineTo(20, 14)
        p.drawPath(path)
    elif name == "print":
        p.drawRect(r(7, 3, 10, 6))
        p.drawRoundedRect(r(3, 9, 18, 8), 1.5, 1.5)
        p.drawRect(r(7, 14, 10, 7))
    elif name == "select":
        path = QPainterPath()
        path.moveTo(6, 3)
        path.lineTo(6, 19)
        path.lineTo(10, 15)
        path.lineTo(13, 21)
        path.lineTo(15.5, 20)
        path.lineTo(12.5, 14)
        path.lineTo(18, 14)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "measure":
        p.save()
        p.translate(12, 12)
        p.rotate(-35)
        p.drawRect(r(-10, -3.5, 20, 7))
        for i, x in enumerate(range(-7, 9, 3)):
            p.drawLine(QPointF(x, -3.5), QPointF(x, -0.5 if i % 2 else 0.8))
        p.restore()
    elif name == "text":
        p.drawLine(QPointF(5, 5), QPointF(19, 5))
        p.drawLine(QPointF(12, 5), QPointF(12, 20))
        p.drawLine(QPointF(9, 20), QPointF(15, 20))
    elif name == "cloud":
        path = QPainterPath()
        path.moveTo(6, 18)
        path.arcTo(r(2, 10, 8, 8), 270, -180)
        path.arcTo(r(5, 5, 8, 8), 180, -150)
        path.arcTo(r(11, 4, 8, 8), 150, -150)
        path.arcTo(r(15, 10, 7, 8), 90, -180)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "rect":
        p.drawRect(r(4, 6, 16, 12))
    elif name == "arrow":
        p.drawLine(QPointF(5, 19), QPointF(18, 6))
        _arrow_head(p, 18, 6, -math.pi / 4, 6)
    elif name == "highlight":
        p.save()
        c = QColor(p.pen().color())
        c.setAlpha(90)
        p.fillRect(r(3, 13, 18, 6), c)
        p.restore()
        p.save()
        p.translate(12, 9)
        p.rotate(-35)
        p.drawRect(r(-7, -2.5, 12, 5))
        p.drawLine(QPointF(5, -2.5), QPointF(8, 0))
        p.drawLine(QPointF(5, 2.5), QPointF(8, 0))
        p.restore()
    elif name == "number":
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        f = QFont(UI_FONT)
        f.setPixelSize(11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(r(0, 0, 24, 24), Qt.AlignmentFlag.AlignCenter, "1")
    elif name == "stamp":
        p.drawRoundedRect(r(3, 6, 18, 12), 2, 2)
        p.drawLine(QPointF(7, 12), QPointF(10, 15))
        p.drawLine(QPointF(10, 15), QPointF(17, 9))
    elif name in ("panel_left", "panel_right"):
        p.drawRoundedRect(r(3, 4, 18, 16), 2, 2)
        x = 9 if name == "panel_left" else 15
        p.drawLine(QPointF(x, 4), QPointF(x, 20))
    elif name in ("undo", "redo"):
        sgn = 1 if name == "undo" else -1
        p.save()
        if sgn < 0:
            p.translate(24, 0)
            p.scale(-1, 1)
        path = QPainterPath()
        path.moveTo(5, 10)
        path.lineTo(15, 10)
        path.arcTo(r(10, 10, 10, 10), 90, -180)
        path.lineTo(9, 20)
        p.drawPath(path)
        _arrow_head(p, 5, 10, math.pi, 4)
        p.restore()
    elif name == "rotate":
        path = QPainterPath()
        path.arcMoveTo(r(4, 4, 16, 16), 60)
        path.arcTo(r(4, 4, 16, 16), 60, 270)
        p.drawPath(path)
        _arrow_head(p, 16, 5.1, -0.3, 4)
    elif name == "settings":
        for y, x in ((7, 15), (12, 8), (17, 13)):
            p.drawLine(QPointF(4, y), QPointF(20, y))
            p.save()
            p.setBrush(QColor(THEME["surface"]))
            p.drawEllipse(QPointF(x, y), 2.2, 2.2)
            p.restore()
    elif name == "list":
        for y in (7, 12, 17):
            p.drawLine(QPointF(9, y), QPointF(20, y))
            p.drawEllipse(QPointF(5, y), 1.2, 1.2)
    elif name == "overview":
        p.drawRoundedRect(r(3, 5, 18, 14), 2, 2)
        p.drawRect(r(11, 11, 7, 5))
    elif name == "cancel":
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        p.drawLine(QPointF(9, 9), QPointF(15, 15))
        p.drawLine(QPointF(15, 9), QPointF(9, 15))
    elif name == "prev":
        p.drawLine(QPointF(15, 5), QPointF(8, 12))
        p.drawLine(QPointF(8, 12), QPointF(15, 19))
    elif name == "next":
        p.drawLine(QPointF(9, 5), QPointF(16, 12))
        p.drawLine(QPointF(16, 12), QPointF(9, 19))
    elif name == "check":
        p.drawLine(QPointF(5, 12), QPointF(10, 17))
        p.drawLine(QPointF(10, 17), QPointF(19, 7))
    elif name == "reject":
        p.drawLine(QPointF(6, 6), QPointF(18, 18))
        p.drawLine(QPointF(18, 6), QPointF(6, 18))
    elif name == "help":
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        f = QFont(UI_FONT)
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        p.drawText(r(0, 0, 24, 24), Qt.AlignmentFlag.AlignCenter, "?")
    elif name == "sidebyside":
        p.drawRoundedRect(r(3, 5, 8, 14), 1.5, 1.5)
        p.drawRoundedRect(r(13, 5, 8, 14), 1.5, 1.5)
    elif name == "ellipse":
        p.drawEllipse(r(3, 6, 18, 12))
    elif name == "line":
        p.drawLine(QPointF(5, 19), QPointF(19, 5))
    elif name in ("polyline", "polygon"):
        pts = [QPointF(4, 18), QPointF(8, 6), QPointF(15, 12), QPointF(20, 5)]
        if name == "polygon":
            pts = [QPointF(4, 17), QPointF(7, 6), QPointF(15, 9), QPointF(20, 18)]
            pts.append(pts[0])
        for i in range(len(pts) - 1):
            p.drawLine(pts[i], pts[i + 1])
    elif name == "pen":
        path = QPainterPath()
        path.moveTo(3, 18)
        path.cubicTo(7, 10, 10, 22, 14, 14)
        path.cubicTo(16, 10, 18, 12, 21, 6)
        p.drawPath(path)
    elif name == "shapes":
        p.drawRect(r(3, 3, 10, 9))
        p.drawEllipse(r(10, 10, 11, 11))
    elif name == "area":                            # Auswahlrahmen: gestrichelt mit Anfassern an den Ecken
        pen = p.pen()
        dash = QPen(pen)
        dash.setDashPattern([1.6, 1.6])
        p.setPen(dash)
        p.drawRect(r(4, 5, 16, 14))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pen.color())
        for cx, cy in ((4, 5), (20, 5), (4, 19), (20, 19)):
            p.drawRect(r(cx - 2, cy - 2, 4, 4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen)
    elif name == "layers":
        for dy in (0, 5, 10):
            path = QPainterPath()
            path.moveTo(12, 3 + dy)
            path.lineTo(21, 7 + dy)
            path.lineTo(12, 11 + dy)
            path.lineTo(3, 7 + dy)
            path.closeSubpath()
            p.drawPath(path)
    elif name == "redact":
        p.drawRect(r(3, 5, 18, 14))
        p.fillRect(r(5, 8, 14, 3), p.pen().color())
        p.fillRect(r(5, 13, 10, 3), p.pen().color())
    elif name == "pixelate":
        for i, (x, y) in enumerate(((3, 4), (9, 4), (15, 4), (3, 10), (9, 10), (15, 10), (3, 16), (9, 16), (15, 16))):
            if i % 2 == 0:
                p.fillRect(r(x, y, 6, 6), p.pen().color())
            else:
                p.drawRect(r(x + 0.5, y + 0.5, 5, 5))
    elif name == "lock":
        p.drawRoundedRect(r(5, 11, 14, 10), 1.5, 1.5)
        path = QPainterPath()
        path.moveTo(8, 11)
        path.lineTo(8, 8)
        path.arcTo(r(8, 3.5, 8, 9), 180, -180)
        path.lineTo(16, 11)
        p.drawPath(path)
    elif name == "magic":
        p.drawLine(QPointF(4, 20), QPointF(15, 9))
        for (x, y) in ((17, 4), (20, 8), (13, 3)):
            p.drawLine(QPointF(x - 1.5, y), QPointF(x + 1.5, y))
            p.drawLine(QPointF(x, y - 1.5), QPointF(x, y + 1.5))


def _pixmap(name, color, size, dpr):
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24.0, size / 24.0)
    pen = QPen(QColor(color), 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    _draw(p, name)
    p.end()
    return pm


def icon(name, color=None):
    """QIcon im aktuellen Farbschema; Zustand 'an' (gedrueckt) in der Akzentfarbe - passt auf hellblauem Knopf und
    im Menue (dort war Weiss auf hellem Grund unsichtbar)."""
    col = color or THEME["text"]
    key = (name, col, THEME["surface"], THEME["on_fg"])
    if key not in _cache:
        ic = QIcon()
        for size in (16, 20, 24, 32):
            ic.addPixmap(_pixmap(name, col, size, 2.0), QIcon.Mode.Normal, QIcon.State.Off)
            ic.addPixmap(_pixmap(name, color or THEME["on_fg"], size, 2.0), QIcon.Mode.Normal, QIcon.State.On)
            ic.addPixmap(_pixmap(name, THEME["disabled"], size, 2.0), QIcon.Mode.Disabled, QIcon.State.Off)
        _cache[key] = ic
    return _cache[key]


ALL = ("open", "compare", "fit", "zoom_in", "zoom_out", "zoom_box", "loupe", "save", "print", "select", "measure",
       "text", "cloud", "rect", "arrow", "highlight", "number", "stamp", "panel_left", "panel_right", "undo", "redo",
       "rotate", "settings", "list", "overview", "cancel", "prev", "next", "check", "reject", "help", "sidebyside",
       "magic")
