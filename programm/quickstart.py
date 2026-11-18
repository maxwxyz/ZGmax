"""Schneller Start: alles, was vor den schweren Bausteinen (OpenCV, Rechenkern, Oberflaeche) schon geht.

Braucht nur Qt. Drei Dinge:
- Laeuft ZGmax schon, bekommt es die Dateien uebergeben (ein Programm statt vieler; sofort da).
- Sonst zeigt eine Sofortvorschau das Bild, waehrend der Rest laedt (bei Bildformaten, die Qt selbst lesen kann).
- Startzeit messen (--startzeit): fuer den Vergleich zwischen Versionen und Systemen.
"""
import json
import os
import sys
import time

T0 = time.time()                              # Programmbeginn (so frueh wie moeglich importieren)
MARKS = []                                    # [(Name, Sekunden seit Start)]
SERVER = "zgmax-" + (os.environ.get("USERNAME") or os.environ.get("USER") or "user")
QT_IMAGES = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff")
PREVIEW_MAX_PX = 150_000_000                  # groessere Bilder: nur der Name (das Lesen dauerte laenger als der Start)


def mark(name):
    """Zeitpunkt merken; ZGMAX_T0 (Sekunden seit 1970, vom Aufrufer) zaehlt auch die Zeit vor dem ersten Befehl."""
    try:
        t0 = float(os.environ.get("ZGMAX_T0", "")) or T0
    except ValueError:
        t0 = T0
    MARKS.append((name, time.time() - t0))


def file_args(argv):
    return [os.path.abspath(a) for a in argv[1:] if not a.startswith("-")]


def make_app(argv):
    """QApplication mit Oberflaechengroesse aus den Einstellungen (muss vor dem Start feststehen)."""
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    if "--startzeit" in argv:                    # Messlauf: eigene Einstellungen und Daten, nichts vom Nutzer beruehren
        import tempfile
        tmp = tempfile.mkdtemp(prefix="zgmax-startzeit-")
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tmp)
        os.environ["ZV_DATA_DIR"] = tmp
        os.environ["ZGMAX_BG_OCR"] = "0"
    if os.name == "nt":                          # eigenes Symbol in der Taskleiste (nicht das von Python)
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ZGmax.Viewer.2")
        except Exception:                        # noqa: BLE001
            pass
    try:
        st = QSettings(QSettings.defaultFormat(), QSettings.Scope.UserScope, "drawing_diff", "viewer")
        scale = float(st.value("ui_scale", 1.0))
    except (TypeError, ValueError):
        scale = 1.0
    if 0.5 < scale < 2.5 and abs(scale - 1.0) > 0.01:
        os.environ["QT_SCALE_FACTOR"] = f"{scale:.2f}"
    app = QApplication(argv)
    mark("Qt")
    return app


def _settings():
    from PySide6.QtCore import QSettings
    return QSettings(QSettings.defaultFormat(), QSettings.Scope.UserScope, "drawing_diff", "viewer")


def saved_window(settings=None):
    """Zuletzt benutzte Lage des Hauptfensters: (x, y, b, h, maximiert) oder None. Nur, wenn das Fenster damit noch
    auf einem angeschlossenen Bildschirm liegt (sonst waere es nach dem Abstecken eines Monitors unerreichbar)."""
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QGuiApplication
    st = settings or _settings()
    try:
        x, y, w, h = (int(st.value("win_" + k)) for k in "xywh")
    except (TypeError, ValueError):
        return None
    if w < 600 or h < 400:
        return None
    r = QRect(x, y, w, h)
    if not any(s.availableGeometry().intersected(r).width() >= 200 and
               s.availableGeometry().intersected(r).height() >= 150 for s in QGuiApplication.screens()):
        return None
    return x, y, w, h, str(st.value("win_max", "false")).lower() == "true"


def save_window(win, settings=None):
    """Lage des Hauptfensters merken (bei maximiertem Fenster die Lage davor und das Merkmal maximiert)."""
    st = settings or _settings()
    g = win.normalGeometry() if win.isMaximized() or win.isFullScreen() else win.geometry()
    if g.width() >= 600 and g.height() >= 400:
        for k, v in zip("xywh", (g.x(), g.y(), g.width(), g.height())):
            st.setValue("win_" + k, int(v))
    st.setValue("win_max", "true" if win.isMaximized() else "false")


def hand_over(files, timeout=400):
    """Laeuft ZGmax schon? Dann die Dateien dorthin geben (auch ohne Dateien: Fenster nach vorn). True = erledigt,
    dieses Programm kann sofort enden."""
    if os.environ.get("ZGMAX_EIGENE_INSTANZ") == "1":
        return False
    from PySide6.QtNetwork import QLocalSocket
    s = QLocalSocket()
    s.connectToServer(SERVER)
    if not s.waitForConnected(timeout):
        return False
    if os.name == "nt":                          # das laufende Programm darf sein Fenster nach vorn holen
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(-1)
        except Exception:                        # noqa: BLE001
            pass
    s.write(json.dumps({"files": files}).encode("utf-8") + b"\n")
    s.flush()
    s.waitForBytesWritten(timeout)               # False heisst nur: schon alles geschrieben
    ok = s.waitForReadyRead(2000)                # Antwort = angenommen
    s.disconnectFromServer()
    return bool(ok)


def serve(on_files):
    """Im laufenden Programm: Dateien weiterer Aufrufe annehmen. on_files(Liste) wird im Hauptthread gerufen."""
    from PySide6.QtNetwork import QLocalServer
    srv = QLocalServer()
    srv.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not srv.listen(SERVER):
        QLocalServer.removeServer(SERVER)        # Rest eines abgestuerzten Laufs
        if not srv.listen(SERVER):
            return None

    def incoming():
        while srv.hasPendingConnections():
            c = srv.nextPendingConnection()

            def read(c=c):
                if not c.canReadLine():
                    return
                try:
                    files = json.loads(bytes(c.readLine()).decode("utf-8")).get("files") or []
                except ValueError:
                    files = []
                c.write(b"ok\n")
                c.flush()
                c.disconnectFromServer()
                on_files([f for f in files if isinstance(f, str)])
            c.readyRead.connect(read)
            read()
    srv.newConnection.connect(incoming)
    return srv


def preview(path, size=(1440, 900), place=None):
    """Sofortvorschau: Fenster in Programmgroesse mit dem Bild (falls Qt es lesen kann), sonst nur der Dateiname.
    Bleibt, bis das Hauptfenster das Bild selbst zeigt. None, wenn es nichts zu zeigen gibt."""
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QColor, QImageReader, QPalette, QPixmap
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
    if not path or not os.path.isfile(path):
        return None
    w = QWidget()
    w.setWindowTitle("ZGmax – " + os.path.basename(path))
    ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    if os.path.isfile(ico):
        from PySide6.QtGui import QIcon
        w.setWindowIcon(QIcon(ico))
    w.resize(*size)
    if place:                                    # wie das Hauptfenster beim letzten Mal: (x, y, b, h, maximiert)
        w.setGeometry(*place[:4])
    pal = w.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#e5e7eb"))
    w.setPalette(pal)
    lay = QVBoxLayout(w)
    lbl = QLabel(os.path.basename(path) + " …")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet("color: #374151; font-size: 14pt;")
    lay.addWidget(lbl)
    if path.lower().endswith(QT_IMAGES):
        try:
            QImageReader.setAllocationLimit(0)   # grosse Zeichnungen erlauben
            r = QImageReader(path)
            r.setAutoTransform(True)
            full = r.size()
            if full.isValid() and 0 < full.width() * full.height() <= PREVIEW_MAX_PX:
                box = QSize(size[0] - 40, size[1] - 60)
                r.setScaledSize(full.scaled(box, Qt.AspectRatioMode.KeepAspectRatio))   # klein lesen: schnell
                img = r.read()
                if not img.isNull():
                    lbl.setPixmap(QPixmap.fromImage(img))
        except Exception:                        # noqa: BLE001 - dann eben nur der Name
            pass
    if place and place[4]:
        w.showMaximized()
    else:
        w.show()
    return w


def report():
    """Gemessene Zeiten als eine Zeile, z. B. 'Startzeit: Qt 0,31 s · Vorschau 0,38 s · Fenster 1,20 s · Bild 1,42 s'."""
    return "Startzeit: " + " · ".join(f"{n} {t:.2f} s" for n, t in MARKS)
