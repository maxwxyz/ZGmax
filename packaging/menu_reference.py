"""Menuereferenz der Anleitungen automatisch aus den echten Menues erzeugen (deutsch und englisch).

    .venv/bin/python packaging/menu_reference.py           Abschnitt in beiden Anleitungen neu schreiben
    .venv/bin/python packaging/menu_reference.py --check   nur pruefen (Exit 1, wenn veraltet; fuer Tests)

Der Abschnitt steht zwischen <!-- MENUS:BEGIN --> und <!-- MENUS:END -->. Beruehrt keine Nutzereinstellungen
(eigener Einstellungs- und Datenordner).
"""
import html
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DOCS = {"de": os.path.join(ROOT, "programm", "Anleitung_Viewer.html"),
        "en": os.path.join(ROOT, "programm", "Manual_Viewer.html")}
BEGIN, END = "<!-- MENUS:BEGIN -->", "<!-- MENUS:END -->"
HEAD = {"de": ("Menü", "Befehl", "Taste", "Wirkung"), "en": ("Menu", "Command", "Key", "What it does")}


def emit():
    """Im Kindprozess (ZV_LANG gesetzt): HTML-Tabellen der Menues ausgeben."""
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QApplication
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, os.environ["ZV_DATA_DIR"])
    sys.path.insert(0, os.path.join(ROOT, "programm"))
    app = QApplication.instance() or QApplication([])  # noqa: F841
    import i18n
    import drawing_viewer as vw
    w = vw.MainWindow()
    lang = i18n.LANG
    h = HEAD[lang]
    out = []

    keys_de = (("Ctrl", "Strg"), ("Shift", "Umschalt"), ("Del", "Entf"), ("PgUp", "Bild ↑"), ("PgDown", "Bild ↓"),
               ("Return", "Enter"), ("Space", "Leertaste"))

    def key_text(a):
        k = a.shortcut().toString(QKeySequence.SequenceFormat.PortableText) if not a.shortcut().isEmpty() else ""
        if lang == "de":
            for x, y in keys_de:
                k = k.replace(x, y)
        return k

    def walk(menu, path):
        menu.aboutToShow.emit()                       # dynamische Menues fuellen
        rows, subs = [], []
        for a in menu.actions():
            if a.isSeparator() or not a.text().strip():
                continue
            name = a.text().replace("&", "")
            if a.menu() is not None:
                subs.append((a.menu(), path + [name]))
                continue
            tip = a.statusTip() or a.toolTip().replace("&", "")
            if tip.rstrip(" …").strip() == name.rstrip(" …").strip():
                tip = ""
            rows.append((name, key_text(a), tip))
        if rows:
            out.append(f"<h3>{html.escape(' → '.join(path))}</h3>")
            out.append(f"<table class=\"menus\"><tr><th>{h[1]}</th><th>{h[2]}</th><th>{h[3]}</th></tr>")
            for name, key, tip in rows:
                out.append(f"<tr><td>{html.escape(name)}</td><td>{html.escape(key)}</td><td>{html.escape(tip)}</td></tr>")
            out.append("</table>")
        for m, pth in subs:
            walk(m, pth)

    for a in w.menuBar().actions():
        if a.menu() is not None and a.text().strip():
            walk(a.menu(), [a.text().replace("&", "")])
    w._dirty = False
    w.close()
    print("\n".join(out))


SKIP_MENUS = ("Zuletzt verwendet", "Recently used", "Fenster", "Window", "Ausschnitte", "Saved views",
              "Werkzeugkasten", "Tool chest", "Sprache", "Language")


def build(lang):
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, ZV_LANG=lang, ZV_DATA_DIR=tmp, QT_QPA_PLATFORM="offscreen")
        r = subprocess.run([sys.executable, __file__, "--emit"], env=env, capture_output=True, text=True, check=True)
    lines, keep = [], True
    for ln in r.stdout.splitlines():                  # Menues mit wechselndem Inhalt (Dateilisten u. a.) auslassen
        if ln.startswith("<h3>"):
            keep = not any(s in ln for s in SKIP_MENUS)
        if keep:
            lines.append(ln)
    return "\n".join(lines)


def main():
    if "--emit" in sys.argv:
        emit()
        return 0
    stale = []
    for lang, path in DOCS.items():
        s = open(path, encoding="utf-8").read()
        i, j = s.index(BEGIN) + len(BEGIN), s.index(END)
        new = "\n" + build(lang) + "\n"
        if s[i:j] != new:
            stale.append(path)
            if "--check" not in sys.argv:
                open(path, "w", encoding="utf-8").write(s[:i] + new + s[j:])
    if "--check" in sys.argv and stale:
        print("Menuereferenz veraltet: " + ", ".join(stale) + "  ->  packaging/menu_reference.py ausfuehren")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
