"""Einstieg der App (auch der gebauten): zuerst freeze_support, dann der schnelle Start, erst danach das Programm.

Die Texterkennung im Hintergrund laeuft in einem eigenen Prozess (ocrservice). Der startet dieselbe Datei noch einmal;
steht hier vor freeze_support nichts Schweres, laedt er weder Oberflaeche noch Fenster und ist schnell bereit.
Danach (quickstart, braucht nur Qt): Dateien an ein schon laufendes ZGmax geben, sonst das Bild gleich als
Sofortvorschau zeigen - und erst dann OpenCV, Rechenkern und Oberflaeche laden.
"""
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    import sys
    import quickstart as qs
    app = pv = None
    if "--selbsttest" not in sys.argv:
        files = qs.file_args(sys.argv)
        app = qs.make_app(sys.argv)
        if "--startzeit" not in sys.argv and "--neu" not in sys.argv and qs.hand_over(files):
            sys.exit(0)                          # ZGmax laeuft schon und hat die Dateien uebernommen
        if files and not files[0].lower().endswith(".zgmax"):
            pv = qs.preview(files[0], place=qs.saved_window())
            if pv is not None:
                app.processEvents()
                qs.mark("Vorschau")
    import drawing_viewer
    drawing_viewer.main(app, pv)
