"""Einstieg der App (auch der gebauten): zuerst freeze_support, erst danach das Programm.

Die Texterkennung im Hintergrund laeuft in einem eigenen Prozess (ocrservice). Der startet dieselbe Datei noch einmal;
steht hier vor freeze_support nichts Schweres, laedt er weder Oberflaeche noch Fenster und ist schnell bereit.
"""
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    import drawing_viewer
    drawing_viewer.main()
