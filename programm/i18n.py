"""Sprache der Oberflaeche: Deutsch oder Englisch.

tr("Text") liefert die Uebersetzung des deutschen Textes (oder ihn selbst). Texte mit Werten werden als Vorlage
uebersetzt: tr("Seite {} von {}").format(i, n). Die Sprache steht beim Programmstart fest:
  1. Umgebungsvariable ZV_LANG (de/en), z. B. fuer Tests
  2. Einstellung "language" (Ansicht > Sprache), "auto" = wie das Betriebssystem
  3. Systemsprache: Deutsch -> de, alles andere -> en (Englisch als Ersatz)
Uebersetzungen: i18n_en.json (deutscher Text -> englischer Text).
"""
import json
import os
import sys

LANGS = ("de", "en")
_HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def system_language():
    try:
        from PySide6.QtCore import QLocale
        return "de" if QLocale.system().language() == QLocale.Language.German else "en"
    except Exception:                                    # noqa: BLE001
        import locale
        loc = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
        return "de" if loc.startswith("de") else "en"


def setting():
    try:
        from PySide6.QtCore import QSettings
        v = QSettings(QSettings.defaultFormat(), QSettings.Scope.UserScope, "drawing_diff", "viewer").value("language")
        return v if v in LANGS else "auto"
    except Exception:                                    # noqa: BLE001
        return "auto"


def _detect():
    env = os.environ.get("ZV_LANG", "")
    if env in LANGS:
        return env
    s = setting()
    return s if s in LANGS else system_language()


LANG = _detect()
_EN = None


def tr(text):
    """Uebersetzung von 'text' in die aktuelle Sprache (unbekannte Texte bleiben unveraendert)."""
    global _EN
    if LANG == "de":
        return text
    if _EN is None:
        try:
            with open(os.path.join(_HERE, "i18n_en.json"), encoding="utf-8") as f:
                _EN = json.load(f)
        except (OSError, ValueError):
            _EN = {}
    return _EN.get(text, text)


def doc(name):
    """Dateiname einer Anleitung in der aktuellen Sprache (Anleitung_Viewer.html -> Manual_Viewer.html)."""
    if LANG == "en":
        alt = {"Anleitung_Viewer.html": "Manual_Viewer.html",
               "Anleitung_Kommandozeile.html": "Manual_CommandLine.html"}.get(name, name)
        if os.path.isfile(os.path.join(_HERE, alt)):
            return alt
    return name
