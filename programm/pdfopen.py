"""PDF (und SVG/XPS) einheitlich oeffnen: verstaendliche Fehler statt technischer Meldungen und Passwortschutz.

Ein einmal eingegebenes Passwort gilt fuer die ganze Sitzung (je Datei); alle Stellen, die eine Eingabedatei mit
PyMuPDF oeffnen (Rendern, Vektordaten, Text, Kommentare, Vorschaubilder), nutzen open_doc().
"""
import os

from i18n import tr

PASSWORDS = {}                       # absoluter Pfad -> Passwort (nur im Speicher, nie gespeichert)


class PdfOpenError(Exception):
    """Datei laesst sich nicht oeffnen (beschaedigt, kein PDF)."""


class PasswordRequired(PdfOpenError):
    """PDF ist mit einem Passwort geschuetzt, und es ist (noch) kein passendes bekannt."""


def _key(path):
    return os.path.abspath(path)


def open_doc(path):
    """pymupdf.Document (auch als 'with' nutzbar); entsperrt mit einem bekannten Passwort."""
    import pymupdf
    name = os.path.basename(path)
    if os.path.isfile(path) and os.path.getsize(path) == 0:
        raise PdfOpenError(tr("Die Datei „{}“ ist leer (0 Byte).").format(name))
    try:
        doc = pymupdf.open(path)
    except Exception as e:                       # noqa: BLE001 - FileDataError, RuntimeError je nach Version
        raise PdfOpenError(tr("„{}“ lässt sich nicht öffnen – die Datei ist beschädigt oder kein unterstütztes "
                              "Format ({}).").format(name, type(e).__name__)) from e
    if doc.needs_pass:
        pw = PASSWORDS.get(_key(path))
        if not pw or not doc.authenticate(pw):
            doc.close()
            raise PasswordRequired(tr("„{}“ ist mit einem Passwort geschützt.").format(name))
    return doc


def needs_password(path):
    """True, wenn die Datei ein PDF mit Passwort ist und noch kein passendes bekannt ist."""
    try:
        open_doc(path).close()
    except PasswordRequired:
        return True
    except Exception:                            # noqa: BLE001 - andere Fehler meldet das Laden selbst
        return False
    return False


def try_password(path, pw):
    """Passwort pruefen und bei Erfolg fuer die Sitzung merken."""
    import pymupdf
    try:
        with pymupdf.open(path) as doc:
            if doc.authenticate(pw):
                PASSWORDS[_key(path)] = pw
                return True
    except Exception:                            # noqa: BLE001
        pass
    return False
