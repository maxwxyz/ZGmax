"""Texterkennung ganzer Seiten in einem eigenen Prozess.

Der Prozess laeuft mit niedriger Prioritaet: Ansehen, Bearbeiten und Vergleichen im Programm bleiben fluessig, die
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


def _child_lines(key, gray, workers):
    import diffreport as rep
    eng = rep._ocr_engine().eng                  # ohne Sperre: OpenCV ist in diesem Prozess ohnehin einfaedig

    def progress(f):
        try:
            _queue.put_nowait((key, f))
        except Exception:                        # noqa: BLE001
            pass
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


def submit(key, gray):
    """Auftrag starten (oder den laufenden fuer key zurueckgeben). gray: dunkle Schrift auf hellem Papier."""
    import numpy as np
    with _lock:
        fut = _jobs.get(key)
        if fut is not None and not fut.cancelled() and (not fut.done() or fut.exception() is None):
            return fut
        fut = _get_pool().submit(_child_lines, key, np.ascontiguousarray(gray), TILE_WORKERS)
        _jobs[key] = fut
        _prog[key] = 0.0
        return fut


def busy(key):
    fut = _jobs.get(key)
    return fut is not None and not fut.done()


def result(key):
    """Fertiges Ergebnis fuer key oder None."""
    fut = _jobs.get(key)
    if fut is not None and fut.done() and not fut.cancelled() and fut.exception() is None:
        return fut.result()
    return None


def lines(key, gray, progress=None, cancel=None):
    """Textzeilen der Seite wie diffreport.ocr_lines - im Erkennungsprozess; wartet darauf (Fortschritt, Abbruch).
    Faellt der Prozess aus, wird im Programm selbst gelesen."""
    import diffcore as dc
    import diffreport as rep
    try:
        fut = submit(key, gray)
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
    except Exception:                            # noqa: BLE001 - Prozess nicht verfuegbar oder abgestuerzt
        log.exception("Texterkennung im eigenen Prozess")
        reset()
        return rep.ocr_lines(gray, progress=progress, cancel=cancel)


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
