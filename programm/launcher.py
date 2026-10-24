#!/usr/bin/env python3
"""Startet den Viewer. Prueft vorher, ob alle noetigen Pakete installiert sind, und bietet an, fehlende
zu installieren. Danach oeffnet sich das Programmfenster und dieses Fenster schliesst sich."""
import importlib.util
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# (Importname, pip-Name, Pflicht?)
PACKAGES = [("cv2", "opencv-python", True), ("numpy", "numpy", True), ("PIL", "pillow", True),
            ("PySide6", "PySide6-Essentials", True), ("pymupdf", "pymupdf", False), ("ezdxf", "ezdxf", False)]


def missing():
    return [(imp, pip, must) for imp, pip, must in PACKAGES if importlib.util.find_spec(imp) is None]


def main():
    miss = missing()
    if miss:
        print("ZGmax: Es fehlen Programmpakete:")
        for imp, pip, must in miss:
            print(f"  - {pip}" + ("" if must else "   (nur fuer PDF/SVG noetig)"))
        print("\nSie werden jetzt automatisch installiert (Internetverbindung noetig). Bitte warten ...\n")
        req = os.path.join(os.path.dirname(HERE), "requirements.txt")   # getestete, feste Versionen
        cmd = [sys.executable, "-m", "pip", "install", "--user"] + (
            ["-r", req] if os.path.isfile(req) else [pip for _, pip, _ in miss])
        if subprocess.call(cmd) != 0:
            print("\nInstallation fehlgeschlagen. Bitte pruefen Sie die Internetverbindung "
                  "und starten Sie das Programm erneut.")
            if os.name == "nt":
                input("Enter zum Beenden ...")
            return 1
        if [m for m in missing() if m[2]]:
            print("\nEs fehlen weiterhin Pakete. Bitte Programm neu starten.")
            return 1
        print("\nFertig.")
    viewer = os.path.join(HERE, "drawing_viewer.py")
    args = sys.argv[1:]
    if os.name == "nt":                                   # ohne Konsolenfenster starten
        exe = sys.executable
        pw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.isfile(pw):
            exe = pw
        flags = 0x00000008 | 0x00000200                   # DETACHED_PROCESS | NEW_PROCESS_GROUP
        subprocess.Popen([exe, viewer, *args], cwd=HERE, creationflags=flags, close_fds=True)
    else:
        # Ausgaben in eine Logdatei statt ins Terminal: das Terminalfenster schliesst sich nach dem Start,
        # Schreiben dorthin wuerde dann fehlschlagen.
        logdir = os.path.expanduser("~/Library/Logs") if sys.platform == "darwin" else HERE
        try:
            log = open(os.path.join(logdir, "ZGmax.log"), "w", encoding="utf-8", errors="replace")
        except OSError:
            log = subprocess.DEVNULL
        subprocess.Popen([sys.executable, "-u", viewer, *args], cwd=HERE, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
