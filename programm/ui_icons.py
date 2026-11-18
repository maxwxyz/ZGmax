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


_r = QRectF                         # kurz: Rechteck im 24er-Raster


def _draw_open(p, name):
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


def _draw_compare(p, name):
    p.drawRoundedRect(_r(3, 3, 12, 12), 1.5, 1.5)
    p.drawRoundedRect(_r(9, 9, 12, 12), 1.5, 1.5)


def _draw_fit(p, name):
    for (cx, cy, sx, sy) in ((4, 4, 1, 1), (20, 4, -1, 1), (4, 20, 1, -1), (20, 20, -1, -1)):
        p.drawLine(QPointF(cx, cy), QPointF(cx + 5 * sx, cy))
        p.drawLine(QPointF(cx, cy), QPointF(cx, cy + 5 * sy))
    p.drawRect(_r(9, 9, 6, 6))


def _draw_zoom(p, name):
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
        p.drawRect(_r(2.5, 2.5, 9, 7))
        p.setPen(pen)


def _draw_save(p, name):
    p.drawLine(QPointF(12, 3), QPointF(12, 15))
    _arrow_head(p, 12, 15, math.pi / 2, 5)
    path = QPainterPath()
    path.moveTo(4, 14)
    path.lineTo(4, 20)
    path.lineTo(20, 20)
    path.lineTo(20, 14)
    p.drawPath(path)


def _draw_print(p, name):
    p.drawRect(_r(7, 3, 10, 6))
    p.drawRoundedRect(_r(3, 9, 18, 8), 1.5, 1.5)
    p.drawRect(_r(7, 14, 10, 7))


def _draw_select(p, name):
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


def _draw_measure(p, name):
    p.save()
    p.translate(12, 12)
    p.rotate(-35)
    p.drawRect(_r(-10, -3.5, 20, 7))
    for i, x in enumerate(range(-7, 9, 3)):
        p.drawLine(QPointF(x, -3.5), QPointF(x, -0.5 if i % 2 else 0.8))
    p.restore()


def _draw_text(p, name):
    p.drawLine(QPointF(5, 5), QPointF(19, 5))
    p.drawLine(QPointF(12, 5), QPointF(12, 20))
    p.drawLine(QPointF(9, 20), QPointF(15, 20))


def _draw_cloud(p, name):
    path = QPainterPath()
    path.moveTo(6, 18)
    path.arcTo(_r(2, 10, 8, 8), 270, -180)
    path.arcTo(_r(5, 5, 8, 8), 180, -150)
    path.arcTo(_r(11, 4, 8, 8), 150, -150)
    path.arcTo(_r(15, 10, 7, 8), 90, -180)
    path.closeSubpath()
    p.drawPath(path)


def _draw_rect(p, name):
    p.drawRect(_r(4, 6, 16, 12))


def _draw_arrow(p, name):
    p.drawLine(QPointF(5, 19), QPointF(18, 6))
    _arrow_head(p, 18, 6, -math.pi / 4, 6)


def _draw_highlight(p, name):
    p.save()
    c = QColor(p.pen().color())
    c.setAlpha(90)
    p.fillRect(_r(3, 13, 18, 6), c)
    p.restore()
    p.save()
    p.translate(12, 9)
    p.rotate(-35)
    p.drawRect(_r(-7, -2.5, 12, 5))
    p.drawLine(QPointF(5, -2.5), QPointF(8, 0))
    p.drawLine(QPointF(5, 2.5), QPointF(8, 0))
    p.restore()


def _draw_number(p, name):
    p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
    f = QFont(UI_FONT)
    f.setPixelSize(11)
    f.setBold(True)
    p.setFont(f)
    p.drawText(_r(0, 0, 24, 24), Qt.AlignmentFlag.AlignCenter, "1")


def _draw_stamp(p, name):
    p.drawRoundedRect(_r(3, 6, 18, 12), 2, 2)
    p.drawLine(QPointF(7, 12), QPointF(10, 15))
    p.drawLine(QPointF(10, 15), QPointF(17, 9))


def _draw_panel(p, name):
    p.drawRoundedRect(_r(3, 4, 18, 16), 2, 2)
    x = 9 if name == "panel_left" else 15
    p.drawLine(QPointF(x, 4), QPointF(x, 20))


def _draw_undo_redo(p, name):
    sgn = 1 if name == "undo" else -1
    p.save()
    if sgn < 0:
        p.translate(24, 0)
        p.scale(-1, 1)
    path = QPainterPath()
    path.moveTo(5, 10)
    path.lineTo(15, 10)
    path.arcTo(_r(10, 10, 10, 10), 90, -180)
    path.lineTo(9, 20)
    p.drawPath(path)
    _arrow_head(p, 5, 10, math.pi, 4)
    p.restore()


def _draw_rotate(p, name):
    path = QPainterPath()
    path.arcMoveTo(_r(4, 4, 16, 16), 60)
    path.arcTo(_r(4, 4, 16, 16), 60, 270)
    p.drawPath(path)
    _arrow_head(p, 16, 5.1, -0.3, 4)


def _draw_settings(p, name):
    for y, x in ((7, 15), (12, 8), (17, 13)):
        p.drawLine(QPointF(4, y), QPointF(20, y))
        p.save()
        p.setBrush(QColor(THEME["surface"]))
        p.drawEllipse(QPointF(x, y), 2.2, 2.2)
        p.restore()


def _draw_list(p, name):
    for y in (7, 12, 17):
        p.drawLine(QPointF(9, y), QPointF(20, y))
        p.drawEllipse(QPointF(5, y), 1.2, 1.2)


def _draw_overview(p, name):
    p.drawRoundedRect(_r(3, 5, 18, 14), 2, 2)
    p.drawRect(_r(11, 11, 7, 5))


def _draw_cancel(p, name):
    p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
    p.drawLine(QPointF(9, 9), QPointF(15, 15))
    p.drawLine(QPointF(15, 9), QPointF(9, 15))


def _draw_prev(p, name):
    p.drawLine(QPointF(15, 5), QPointF(8, 12))
    p.drawLine(QPointF(8, 12), QPointF(15, 19))


def _draw_next(p, name):
    p.drawLine(QPointF(9, 5), QPointF(16, 12))
    p.drawLine(QPointF(16, 12), QPointF(9, 19))


def _draw_check(p, name):
    p.drawLine(QPointF(5, 12), QPointF(10, 17))
    p.drawLine(QPointF(10, 17), QPointF(19, 7))


def _draw_reject(p, name):
    p.drawLine(QPointF(6, 6), QPointF(18, 18))
    p.drawLine(QPointF(18, 6), QPointF(6, 18))


def _draw_help(p, name):
    p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
    f = QFont(UI_FONT)
    f.setPixelSize(13)
    f.setBold(True)
    p.setFont(f)
    p.drawText(_r(0, 0, 24, 24), Qt.AlignmentFlag.AlignCenter, "?")


def _draw_sidebyside(p, name):
    p.drawRoundedRect(_r(3, 5, 8, 14), 1.5, 1.5)
    p.drawRoundedRect(_r(13, 5, 8, 14), 1.5, 1.5)


def _draw_ellipse(p, name):
    p.drawEllipse(_r(3, 6, 18, 12))


def _draw_line(p, name):
    p.drawLine(QPointF(5, 19), QPointF(19, 5))


def _draw_poly(p, name):
    pts = [QPointF(4, 18), QPointF(8, 6), QPointF(15, 12), QPointF(20, 5)]
    if name == "polygon":
        pts = [QPointF(4, 17), QPointF(7, 6), QPointF(15, 9), QPointF(20, 18)]
        pts.append(pts[0])
    for i in range(len(pts) - 1):
        p.drawLine(pts[i], pts[i + 1])


def _draw_pen(p, name):
    path = QPainterPath()
    path.moveTo(3, 18)
    path.cubicTo(7, 10, 10, 22, 14, 14)
    path.cubicTo(16, 10, 18, 12, 21, 6)
    p.drawPath(path)


def _draw_shapes(p, name):
    p.drawRect(_r(3, 3, 10, 9))
    p.drawEllipse(_r(10, 10, 11, 11))


def _draw_area(p, name):                            # Auswahlrahmen: gestrichelt mit Anfassern an den Ecken
    pen = p.pen()
    dash = QPen(pen)
    dash.setDashPattern([1.6, 1.6])
    p.setPen(dash)
    p.drawRect(_r(4, 5, 16, 14))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(pen.color())
    for cx, cy in ((4, 5), (20, 5), (4, 19), (20, 19)):
        p.drawRect(_r(cx - 2, cy - 2, 4, 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(pen)


def _draw_layers(p, name):
    for dy in (0, 5, 10):
        path = QPainterPath()
        path.moveTo(12, 3 + dy)
        path.lineTo(21, 7 + dy)
        path.lineTo(12, 11 + dy)
        path.lineTo(3, 7 + dy)
        path.closeSubpath()
        p.drawPath(path)


def _draw_redact(p, name):
    p.drawRect(_r(3, 5, 18, 14))
    p.fillRect(_r(5, 8, 14, 3), p.pen().color())
    p.fillRect(_r(5, 13, 10, 3), p.pen().color())


def _draw_pixelate(p, name):
    for i, (x, y) in enumerate(((3, 4), (9, 4), (15, 4), (3, 10), (9, 10), (15, 10), (3, 16), (9, 16), (15, 16))):
        if i % 2 == 0:
            p.fillRect(_r(x, y, 6, 6), p.pen().color())
        else:
            p.drawRect(_r(x + 0.5, y + 0.5, 5, 5))


def _draw_lock(p, name):
    p.drawRoundedRect(_r(5, 11, 14, 10), 1.5, 1.5)
    path = QPainterPath()
    path.moveTo(8, 11)
    path.lineTo(8, 8)
    path.arcTo(_r(8, 3.5, 8, 9), 180, -180)
    path.lineTo(16, 11)
    p.drawPath(path)


def _draw_magic(p, name):
    p.drawLine(QPointF(4, 20), QPointF(15, 9))
    for (x, y) in ((17, 4), (20, 8), (13, 3)):
        p.drawLine(QPointF(x - 1.5, y), QPointF(x + 1.5, y))
        p.drawLine(QPointF(x, y - 1.5), QPointF(x, y + 1.5))


# Name des Symbols -> Zeichenfunktion (p, name); mehrere Namen koennen sich eine Funktion teilen
_SYMBOLS = {
    "open": _draw_open, "compare": _draw_compare, "fit": _draw_fit, "zoom_in": _draw_zoom, "zoom_out": _draw_zoom,
    "loupe": _draw_zoom, "zoom_box": _draw_zoom, "save": _draw_save, "print": _draw_print, "select": _draw_select,
    "measure": _draw_measure, "text": _draw_text, "cloud": _draw_cloud, "rect": _draw_rect, "arrow": _draw_arrow,
    "highlight": _draw_highlight, "number": _draw_number, "stamp": _draw_stamp, "panel_left": _draw_panel,
    "panel_right": _draw_panel, "undo": _draw_undo_redo, "redo": _draw_undo_redo, "rotate": _draw_rotate,
    "settings": _draw_settings, "list": _draw_list, "overview": _draw_overview, "cancel": _draw_cancel,
    "prev": _draw_prev, "next": _draw_next, "check": _draw_check, "reject": _draw_reject, "help": _draw_help,
    "sidebyside": _draw_sidebyside, "ellipse": _draw_ellipse, "line": _draw_line, "polyline": _draw_poly,
    "polygon": _draw_poly, "pen": _draw_pen, "shapes": _draw_shapes, "area": _draw_area, "layers": _draw_layers,
    "redact": _draw_redact, "pixelate": _draw_pixelate, "lock": _draw_lock, "magic": _draw_magic
}


def _draw(p, name):
    """Zeichnet das Symbol 'name' mit dem aktuellen Stift (24er-Raster)."""
    fn = _SYMBOLS.get(name)
    if fn is not None:
        fn(p, name)


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
