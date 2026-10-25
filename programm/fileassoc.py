"""Dateitypen mit ZGmax verknuepfen (Doppelklick oeffnet die Datei in ZGmax), auch fuer die portable App.

Je System:
  Windows  Eintraege nur fuer den angemeldeten Nutzer (HKCU, keine Adminrechte): ZGmax erscheint bei "Oeffnen mit",
           .zgmax-Projekte gehoeren direkt ZGmax. Den Standard fuer fremde Typen (PDF, PNG ...) darf seit Windows 10
           nur der Nutzer selbst setzen - dafuer oeffnet das Programm die passende Seite der Windows-Einstellungen.
  macOS    Standardprogramm je Typ ueber LaunchServices (nur aus der fertigen App ZGmax.app heraus).
  Linux    .desktop-Datei unter ~/.local/share/applications und xdg-mime je Typ.
Wird die portable App verschoben, die Zuordnung einfach erneut setzen (der Pfad steht in den Eintraegen).
"""
import os
import subprocess
import sys

from i18n import tr

FROZEN = getattr(sys, "frozen", False)
APP_ID = "ZGmax"
BUNDLE_ID = "de.zgmax.app"                     # wie in packaging/zgmax.spec
PROG_DRAWING, PROG_PROJECT = "ZGmax.Zeichnung", "ZGmax.Projekt"

# Schluessel, Anzeige, Endungen, macOS-UTI, MIME-Typ
TYPES = (
    ("pdf", "PDF", (".pdf",), "com.adobe.pdf", "application/pdf"),
    ("png", "PNG", (".png",), "public.png", "image/png"),
    ("jpg", "JPEG", (".jpg", ".jpeg"), "public.jpeg", "image/jpeg"),
    ("tif", "TIFF", (".tif", ".tiff"), "public.tiff", "image/tiff"),
    ("bmp", "BMP", (".bmp",), "com.microsoft.bmp", "image/bmp"),
    ("webp", "WebP", (".webp",), "org.webmproject.webp", "image/webp"),
    ("svg", "SVG", (".svg",), "public.svg-image", "image/svg+xml"),
    ("dxf", "DXF", (".dxf",), None, "image/vnd.dxf"),
    ("zgmax", tr("ZGmax-Projekt"), (".zgmax",), None, "application/x-zgmax"),
)


def launch_command():
    """(Programm, Argumente vor der Datei): fertige App direkt, sonst Python mit dem Startskript."""
    if FROZEN:
        return sys.executable, []
    exe = sys.executable
    if os.name == "nt" and exe.lower().endswith("python.exe"):     # ohne schwarzes Konsolenfenster
        w = exe[:-len("python.exe")] + "pythonw.exe"
        exe = w if os.path.isfile(w) else exe
    return exe, [os.path.join(os.path.dirname(os.path.abspath(__file__)), "drawing_viewer.py")]


def supported():
    """Kann auf diesem System zugeordnet werden? (False, Grund) sonst."""
    if sys.platform == "darwin" and not FROZEN:
        return False, tr("Auf dem Mac geht das nur aus der fertigen App ZGmax.app heraus.")
    return True, ""


# ----------------------------------------------------------------- Windows
def _win_cmd():
    exe, pre = launch_command()
    return " ".join(f'"{p}"' for p in [exe] + pre) + ' "%1"', exe


def _win_set(keys):
    import winreg
    cmd, exe = _win_cmd()
    root = winreg.HKEY_CURRENT_USER
    base = r"Software\Classes"

    def put(path, name, value, kind=winreg.REG_SZ):
        with winreg.CreateKey(root, path) as k:
            winreg.SetValueEx(k, name, 0, kind, value)
    for prog, label in ((PROG_DRAWING, tr("Zeichnung (ZGmax)")), (PROG_PROJECT, tr("ZGmax-Projekt"))):
        put(rf"{base}\{prog}", "", label)
        put(rf"{base}\{prog}\DefaultIcon", "", f'"{exe}",0')
        put(rf"{base}\{prog}\shell\open\command", "", cmd)
    cap = rf"Software\{APP_ID}\Capabilities"           # damit ZGmax in "Standard-Apps" mit seinen Typen erscheint
    put(cap, "ApplicationName", APP_ID)
    put(cap, "ApplicationDescription", tr("Technische Zeichnungen ansehen, vergleichen und prüfen"))
    put(r"Software\RegisteredApplications", APP_ID, cap)
    for key, _lbl, exts, _uti, _mime in TYPES:
        prog = PROG_PROJECT if key == "zgmax" else PROG_DRAWING
        for ext in exts:
            on = key in keys
            if on:
                put(rf"{base}\{ext}\OpenWithProgids", prog, b"", winreg.REG_NONE)
                put(rf"{cap}\FileAssociations", ext, prog)
                if key == "zgmax":                     # eigener Typ: direkt Standard
                    put(rf"{base}\{ext}", "", prog)
            else:
                for path, name in ((rf"{base}\{ext}\OpenWithProgids", prog), (rf"{cap}\FileAssociations", ext)):
                    try:
                        with winreg.OpenKey(root, path, 0, winreg.KEY_SET_VALUE) as k:
                            winreg.DeleteValue(k, name)
                    except OSError:
                        pass
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # Explorer neu einlesen lassen
    except Exception:                                                     # noqa: BLE001
        pass


def _win_get():
    import winreg
    on = set()
    for key, _lbl, exts, _uti, _mime in TYPES:
        prog = PROG_PROJECT if key == "zgmax" else PROG_DRAWING
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{exts[0]}\OpenWithProgids") as k:
                winreg.QueryValueEx(k, prog)
                on.add(key)
        except OSError:
            pass
    return on


def open_windows_settings():
    """Windows-Einstellungen -> Standard-Apps -> ZGmax (dort setzt der Nutzer den Standard je Typ)."""
    try:
        os.startfile(f"ms-settings:defaultapps?registeredAppUser={APP_ID}")     # noqa: S606 (nur Windows)
    except OSError:
        os.startfile("ms-settings:defaultapps")                                  # noqa: S606


# ----------------------------------------------------------------- macOS (LaunchServices)
def _cf():
    import ctypes
    import ctypes.util
    cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
    cs = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreServices"))
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    cs.LSSetDefaultRoleHandlerForContentType.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
    cs.LSSetDefaultRoleHandlerForContentType.restype = ctypes.c_int32
    cs.LSCopyDefaultRoleHandlerForContentType.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    cs.LSCopyDefaultRoleHandlerForContentType.restype = ctypes.c_void_p
    cs.UTTypeCreatePreferredIdentifierForTag.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    cs.UTTypeCreatePreferredIdentifierForTag.restype = ctypes.c_void_p
    return ctypes, cf, cs


def _mac_uti(cf, cs, uti, ext):
    """UTI des Typs; fuer DXF/zgmax aus der Endung (dynamischer Typ des Systems)."""
    if uti:
        return cf.CFStringCreateWithCString(None, uti.encode(), 0x08000100)
    tag_class = cf.CFStringCreateWithCString(None, b"public.filename-extension", 0x08000100)
    tag = cf.CFStringCreateWithCString(None, ext.lstrip(".").encode(), 0x08000100)
    ref = cs.UTTypeCreatePreferredIdentifierForTag(tag_class, tag, None)
    cf.CFRelease(tag_class)
    cf.CFRelease(tag)
    return ref


def _mac_handler(ctypes, cf, cs, ref):
    out = cs.LSCopyDefaultRoleHandlerForContentType(ref, 0xFFFFFFFF)
    if not out:
        return ""
    buf = ctypes.create_string_buffer(512)
    cf.CFStringGetCString(out, buf, 512, 0x08000100)
    cf.CFRelease(out)
    return buf.value.decode(errors="ignore").lower()


def _mac_set(keys):
    ctypes, cf, cs = _cf()
    me = cf.CFStringCreateWithCString(None, BUNDLE_ID.encode(), 0x08000100)
    fails = []
    for key, lbl, exts, uti, _mime in TYPES:
        if key not in keys:
            continue
        ref = _mac_uti(cf, cs, uti, exts[0])
        if not ref or cs.LSSetDefaultRoleHandlerForContentType(ref, 0xFFFFFFFF, me) != 0:
            fails.append(lbl)
        if ref:
            cf.CFRelease(ref)
    cf.CFRelease(me)
    return fails


def _mac_get():
    ctypes, cf, cs = _cf()
    on = set()
    for key, _lbl, exts, uti, _mime in TYPES:
        ref = _mac_uti(cf, cs, uti, exts[0])
        if ref:
            if _mac_handler(ctypes, cf, cs, ref) == BUNDLE_ID:
                on.add(key)
            cf.CFRelease(ref)
    return on


# ----------------------------------------------------------------- Linux (freedesktop)
def _desktop_path():
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "applications", "zgmax.desktop")


def _linux_set(keys):
    exe, pre = launch_command()
    path = _desktop_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mimes = ";".join(t[4] for t in TYPES) + ";"
    exec_ = " ".join(f'"{p}"' for p in [exe] + pre) + " %F"
    with open(path, "w", encoding="utf-8") as f:
        f.write("[Desktop Entry]\nType=Application\nName=ZGmax\n"
                f"Comment={tr('Technische Zeichnungen ansehen, vergleichen und prüfen')}\n"
                f"Exec={exec_}\nIcon={os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.png')}\n"
                f"MimeType={mimes}\nCategories=Graphics;Viewer;Engineering;\nTerminal=false\n")
    fails = []
    for key, lbl, _exts, _uti, mime in TYPES:
        if key in keys:
            if subprocess.run(["xdg-mime", "default", "zgmax.desktop", mime], capture_output=True).returncode:
                fails.append(lbl)
    subprocess.run(["update-desktop-database", os.path.dirname(path)], capture_output=True)
    return fails


def _linux_get():
    on = set()
    for key, _lbl, _exts, _uti, mime in TYPES:
        try:
            r = subprocess.run(["xdg-mime", "query", "default", mime], capture_output=True, text=True, timeout=5)
            if r.stdout.strip() == "zgmax.desktop":
                on.add(key)
        except (OSError, subprocess.SubprocessError):
            pass
    return on


# ----------------------------------------------------------------- gemeinsam
def current():
    """Typen, die gerade mit ZGmax verknuepft sind (Windows: bei "Oeffnen mit" eingetragen)."""
    try:
        if os.name == "nt":
            return _win_get()
        if sys.platform == "darwin":
            return _mac_get() if FROZEN else set()
        return _linux_get()
    except Exception:                                  # noqa: BLE001 - nur Anzeige
        return set()


def apply(keys):
    """Gewaehlte Typen verknuepfen. Rueckgabe: Liste der Typen, bei denen es nicht ging."""
    keys = set(keys)
    if os.name == "nt":
        _win_set(keys)
        return []
    if sys.platform == "darwin":
        return _mac_set(keys)
    return _linux_set(keys)
