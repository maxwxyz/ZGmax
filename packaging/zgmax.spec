# PyInstaller-Bauplan fuer die portable App (macOS .app bzw. Windows-Ordner mit .exe).
# Bauen:  macOS: packaging/build_mac.sh     Windows: packaging\build_windows.bat
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "programm")
sys.path.insert(0, SRC)
from drawing_viewer import VERSION  # noqa: E402

datas = [(os.path.join(SRC, f), ".") for f in ("Anleitung_Viewer.html", "Anleitung_Kommandozeile.html",
                                               "Manual_Viewer.html", "Manual_CommandLine.html",
                                               "i18n_en.json", "CHANGELOG.json", "icon.png", "icon.ico", "icon.icns")]
datas += [(os.path.join(ROOT, "LICENSE"), ".")]       # AGPL-3.0, liegt der App bei
datas += [(os.path.join(SRC, "ocr", f), "ocr") for f in ("latin_rec.onnx", "latin_dict.txt", "HERKUNFT.txt")]
hidden = ["ezdxf.addons.drawing.pymupdf", "ezdxf.addons.drawing.layout", "ezdxf.addons.drawing.config",
          "PySide6.QtPrintSupport", "PySide6.QtSvg"]
try:                                                 # Texterkennung (optional) samt Modellen mitnehmen
    from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
    import rapidocr_onnxruntime  # noqa: F401
    # rapidocr laedt seine Teile ueber den eigenen Ordner (sys.path) -> Quelldateien mitnehmen
    datas += collect_data_files("rapidocr_onnxruntime", include_py_files=True)
    # was die mitgenommenen Quelldateien selbst importieren (PyInstaller sieht das nicht)
    hidden += ["rapidocr_onnxruntime", "onnxruntime", "pyclipper", "shapely", "shapely.geometry", "yaml", "six"]
    print("Texterkennung (OCR) wird eingebaut")
except ImportError:
    print("Hinweis: Texterkennung (OCR) nicht installiert - App ohne OCR")
excludes = ["tkinter", "matplotlib", "IPython", "pytest", "PyQt5", "PyQt6", "PySide2",
            "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtQuick",
            "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization"]

a = Analysis([os.path.join(SRC, "drawing_viewer.py")], pathex=[SRC], datas=datas, hiddenimports=hidden,
             excludes=excludes, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ZGmax", console=False,
          icon=os.path.join(SRC, "icon.icns" if sys.platform == "darwin" else "icon.ico"),
          version=None, upx=False, argv_emulation=False)
coll = COLLECT(exe, a.binaries, a.datas, name="ZGmax", upx=False)

if sys.platform == "darwin":
    doc_types = [
        {"CFBundleTypeName": "Zeichnung", "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
         "LSItemContentTypes": ["com.adobe.pdf", "public.tiff", "public.png", "public.jpeg", "public.svg-image",
                                "com.microsoft.bmp", "org.webmproject.webp"]},
        {"CFBundleTypeName": "DXF-Zeichnung", "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
         "CFBundleTypeExtensions": ["dxf"]},
        {"CFBundleTypeName": "ZGmax-Projekt", "CFBundleTypeRole": "Editor", "LSHandlerRank": "Owner",
         "CFBundleTypeExtensions": ["zgmax"]},
    ]
    app = BUNDLE(coll, name="ZGmax.app", icon=os.path.join(SRC, "icon.icns"),
                 bundle_identifier="de.zgmax.app",
                 info_plist={"CFBundleShortVersionString": VERSION, "CFBundleVersion": VERSION,
                             "CFBundleDisplayName": "ZGmax", "NSHighResolutionCapable": True,
                             "LSMinimumSystemVersion": "12.0", "CFBundleDocumentTypes": doc_types,
                             "NSRequiresAquaSystemAppearance": False})
