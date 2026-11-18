"""Ausgabedateien sicher schreiben: erst fertig in eine Hilfsdatei im selben Ordner, dann ersetzen. Bricht das Schreiben
ab (Platte voll, Netzlaufwerk weg, Datei gesperrt, keine Rechte), bleibt das alte Ziel unveraendert und es liegt keine
halbe Datei herum; der Fehler kommt als SaveError mit verstaendlichem Text."""
from i18n import tr
import contextlib
import os
import uuid

import diffcore as dc


class SaveError(dc.DiffError):
    """Zieldatei konnte nicht geschrieben werden. str(e) ist die Meldung fuer den Nutzer (path, reason einzeln)."""

    def __init__(self, path, reason=""):
        self.path, self.reason = path, reason
        super().__init__(message(path, reason))


def message(path, reason=""):
    """Meldung fuer den Nutzer: was nicht ging, warum und woran es meist liegt."""
    txt = tr("Datei konnte nicht gespeichert werden: {}").format(path)
    if reason:
        txt += " – " + reason
    return txt + " " + tr("(Datei in einem anderen Programm geöffnet? Genug Platz? Schreibrechte?)")


def _reason(e):
    if isinstance(e, OSError):
        return e.strerror or str(e) or type(e).__name__
    return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__


def _remove(tmp):
    try:
        if os.path.lexists(tmp):
            os.remove(tmp)
    except OSError:
        pass


@contextlib.contextmanager
def atomic_path(path):
    """with atomic_path(ziel) as tmp: ... schreibt nach tmp (selber Ordner, selbe Endung - Bibliotheken waehlen das
    Format nach der Endung); nach Erfolg ersetzt tmp das Ziel. Bei einem Fehler wird tmp geloescht, das Ziel bleibt
    wie es war, und es kommt SaveError (Abbruch, DiffError und MemoryError werden unveraendert weitergereicht)."""
    path = os.fspath(path)
    folder, name = os.path.split(os.path.abspath(path))
    stem, ext = os.path.splitext(name)
    tmp = os.path.join(folder, f"{stem}.tmp-{uuid.uuid4().hex[:8]}{ext}")
    try:
        yield tmp
        if not os.path.isfile(tmp):
            raise SaveError(path, tr("es wurde nichts geschrieben"))
        try:                                         # Rechte einer vorhandenen Zieldatei behalten
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        except OSError:
            pass
        os.replace(tmp, path)                        # Windows: scheitert, wenn das Ziel woanders geoeffnet ist
    except (dc.Cancelled, dc.DiffError, MemoryError):
        raise
    except Exception as e:                           # noqa: BLE001  auch Fehler der Bibliotheken (PyMuPDF, ezdxf ...)
        raise SaveError(path, _reason(e)) from e
    finally:
        _remove(tmp)


@contextlib.contextmanager
def atomic_open(path, mode="w", **kw):
    """Wie open(path, mode, ...) zum Schreiben, aber ueber atomic_path: das Ziel entsteht erst nach dem Schliessen."""
    with atomic_path(path) as tmp:
        with open(tmp, mode, **kw) as f:
            yield f


def write(path, fn):
    """fn(tmp) schreibt die Datei; danach ersetzt sie das Ziel. Rueckgabe: Ergebnis von fn."""
    with atomic_path(path) as tmp:
        return fn(tmp)
