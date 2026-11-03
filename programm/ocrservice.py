"""Texterkennung ganzer Seiten in einem eigenen Prozess.

Der Prozess laedt die Seite selbst aus der Datei (normale Fassung: alle Ebenen, ohne Filter) - unabhaengig davon, wie
sie im Programm gerade gezeigt oder verglichen wird; nichts Grosses muss zwischen den Prozessen kopiert werden und das
Bild im Programm bleibt unberuehrt. Der Prozess laeuft mit niedriger Prioritaet: Ansehen, Bearbeiten und Vergleichen im Programm bleiben fluessig, die
Texterkennung nimmt sich nur freie Rechenzeit. Darin werden mehrere Kacheln gleichzeitig gelesen (schneller als
nacheinander) und OpenCV laeuft einfaedig (siehe diffreport._SafeOcr). Stuerzt die Erkennung ab, bleibt das Programm
offen; dann wird im Programm selbst gelesen. Ein Auftrag je Schluessel (Datei, Seite, Aufloesung): wer denselben Text
braucht, wartet auf denselben Auftrag.
"""
import logging
import os
import threading
import time

log = logging.getLogger("zgmax")

TILE_WORKERS = 3                 # Kacheln gleichzeitig im Erkennungsprozess
_pool = None
_queue = None                    # Fortschritt aus dem Prozess: (Schluessel, Anteil)
_jobs = {}                       # Schluessel -> Future
_prog = {}                       # Schluessel -> letzter Anteil
_lock = threading.Lock()


def _child_init(queue):
    """Im Erkennungsprozess: niedrige Prioritaet, OpenCV einfaedig, Fortschritts-Warteschlange merken."""
    global _queue
    _queue = queue
    try:
        if os.name == "nt":
            import ctypes
            k = ctypes.windll.kernel32
            k.SetPriorityClass(k.GetCurrentProcess(), 0x4000)       # BELOW_NORMAL_PRIORITY_CLASS
        else:
            os.nice(10)
    except Exception:                                               # noqa: BLE001
        pass
    import cv2
    cv2.setNumThreads(0)
    _limit_ort_threads()


def _limit_ort_threads():
    """Rechenkerne der Erkennung begrenzen: zusammen hoechstens die Haelfte, der Rest bleibt fuer das Programm."""
    try:
        import onnxruntime
        import rapidocr_onnxruntime.utils as ru
        per = max(1, (os.cpu_count() or 2) // (2 * TILE_WORKERS))

        def options():
            so = onnxruntime.SessionOptions()
            so.intra_op_num_threads = per
            so.inter_op_num_threads = 1
            return so
        ru.SessionOptions = options
    except Exception:                                               # noqa: BLE001
        pass


def vkey(key):
    """Schluessel fuer die senkrechten Texte derselben Seite."""
    return ("vert",) + tuple(key)


_last = None                     # im Erkennungsprozess: (Quelle, Graubild) der zuletzt geladenen Seite


def page_gray(src):
    """Graubild einer Seite wie beim normalen Laden (dunkelster Kanal). src = (Pfad, Seite, dpi, Passwort oder None)."""
    import diffcore as dc
    path, page, dpi, pw = src
    if pw:
        import pdfopen
        pdfopen.PASSWORDS[pdfopen._key(path)] = pw
    return dc.darkest_channel(dc.read_image(path, page, dpi))


def source(path, page, dpi):
    """Quelle fuer submit/lines: Datei, Seite, Aufloesung und ggf. das Passwort der PDF (nur im Speicher)."""
    import pdfopen
    return (path, page, dpi, pdfopen.PASSWORDS.get(pdfopen._key(path)))


def _child_lines(key, gray, workers, vertical=False, src=None):
    global _last
    import diffreport as rep
    eng = rep._ocr_engine().eng                  # ohne Sperre: OpenCV ist in diesem Prozess ohnehin einfaedig
    if gray is None:                             # Seite selbst laden (waagerecht und senkrecht nur einmal)
        if _last is None or _last[0] != src:
            _last = (src, page_gray(src))
        gray = _last[1]

    def progress(f):
        try:
            _queue.put_nowait((key, f))
        except Exception:                        # noqa: BLE001
            pass
    if vertical:
        return rep.ocr_vertical(gray, progress=progress, workers=workers, eng=eng)
    return rep.ocr_lines(gray, progress=progress, workers=workers, eng=eng)


def _get_pool():
    global _pool, _queue
    if _pool is None:
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor
        ctx = mp.get_context("spawn")
        _queue = ctx.Queue()
        _pool = ProcessPoolExecutor(1, mp_context=ctx, initializer=_child_init, initargs=(_queue,))
    return _pool


def _drain():
    while _queue is not None:
        try:
            k, f = _queue.get_nowait()
        except Exception:                        # noqa: BLE001 - leer
            return
        _prog[k] = f


def submit(key, gray=None, vertical=False, src=None):
    """Auftrag starten (oder den laufenden fuer key zurueckgeben). gray: dunkle Schrift auf hellem Papier, oder None
    und src (siehe source): dann laedt der Prozess die Seite selbst.
    vertical: nur die senkrechten Texte lesen (ocr_vertical), sonst die waagerechten (ocr_lines)."""
    import numpy as np
    with _lock:
        fut = _jobs.get(key)
        if fut is not None and not fut.cancelled() and (not fut.done() or fut.exception() is None):
            return fut
        g = None if gray is None else np.ascontiguousarray(gray)
        fut = _get_pool().submit(_child_lines, key, g, TILE_WORKERS, vertical, src)
        _jobs[key] = fut
        _prog[key] = 0.0
        return fut


def busy(key):
    fut = _jobs.get(key)
    return fut is not None and not fut.done()


def progress(key):
    """Fortschritt 0..1 des Auftrags key (None = keiner bekannt)."""
    _drain()
    fut = _jobs.get(key)
    if fut is None:
        return None
    return 1.0 if fut.done() else _prog.get(key, 0.0)


def result(key):
    """Fertiges Ergebnis fuer key oder None."""
    fut = _jobs.get(key)
    if fut is not None and fut.done() and not fut.cancelled() and fut.exception() is None:
        return fut.result()
    return None


def lines(key, gray=None, progress=None, cancel=None, src=None):
    """Textzeilen der Seite wie diffreport.ocr_lines - im Erkennungsprozess; wartet darauf (Fortschritt, Abbruch).
    gray oder src wie bei submit. Faellt der Prozess aus, wird im Programm selbst gelesen."""
    import diffcore as dc
    import diffreport as rep
    from concurrent.futures.process import BrokenProcessPool
    try:
        fut = submit(key, gray, src=src)
        while True:
            try:
                return fut.result(timeout=0.15)
            except TimeoutError:
                pass
            if cancel is not None and cancel():
                stop()
                raise dc.Cancelled()
            _drain()
            if progress:
                progress(_prog.get(key, 0.0))
    except dc.Cancelled:
        raise
    except Exception as e:                       # noqa: BLE001 - Prozess nicht verfuegbar oder abgestuerzt
        log.exception("Texterkennung im eigenen Prozess")
        if isinstance(e, (BrokenProcessPool, OSError, RuntimeError)) or _pool is None:
            reset()                              # Prozess kaputt: beim naechsten Mal neu starten
        else:
            with _lock:
                _jobs.pop(key, None)             # nur dieser Auftrag gescheitert (z. B. Datei): nicht festhalten
        return rep.ocr_lines(gray if gray is not None else page_gray(src), progress=progress, cancel=cancel)


def reset():
    """Prozess verwerfen (z. B. nach Absturz); der naechste Auftrag startet einen neuen."""
    global _pool, _queue
    with _lock:
        pool, _pool, _queue = _pool, None, None
        _jobs.clear()
        _prog.clear()
    if pool is not None:
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception:                        # noqa: BLE001
            pass


def stop():
    """Laufende Erkennung sofort beenden (Prozess abbrechen)."""
    pool = _pool
    procs = list(getattr(pool, "_processes", {}).values()) if pool is not None else []
    reset()
    for p in procs:
        try:
            p.kill()
        except Exception:                        # noqa: BLE001
            pass


def wait_idle(timeout=60.0):
    """Fuer Tests: warten, bis kein Auftrag mehr laeuft."""
    t0 = time.time()
    while any(not f.done() for f in list(_jobs.values())) and time.time() - t0 < timeout:
        time.sleep(0.05)
