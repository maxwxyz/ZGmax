# ZGmax

View, compare, measure, mark up and review technical drawings. ZGmax compares two revisions of a drawing
(old and new), highlights and numbers the differences and lets you review them one by one.

* User manual: `programm/Manual_Viewer.html` (German: `programm/Anleitung_Viewer.html`). In the program: Help → Manual, F1.
* Command line: `programm/Manual_CommandLine.html` (German: `programm/Anleitung_Kommandozeile.html`).
* `Anleitung.html` in the root folder opens the manual in the system language.

The user interface is available in German and English. By default it follows the system language (German on a German
system, otherwise English); it can be changed under View → Sprache / Language.

## Features

* Formats: PDF, TIFF (multi-page), PNG, JPG, BMP, WebP, JP2, GIF, SVG, XPS, DXF
* Views: old, new, compare (red/blue/gray, green = moved), side by side, overlay, slider, blink
* Robust raster comparison: global and tile alignment, hatching, moved blocks/objects, edge fringes, glyph check,
  paper flattening, auto-adjust of the parameters; exact vector comparison for CAD PDFs
* Review workflow: numbered changes, checked/rejected/comment, CSV, PDF report, PDF with Acrobat annotations
* Measuring with snapping and calibration; vector markups (text typed in place or as wrapping text box, cloud, box,
  ellipse, line, arrow, polyline, polygon, freehand pen, highlight, number, stamp, pasted images), multi-selection
* Region tool: one or more rectangles selecting drawing content, markups and changes – copy, cut, paste, move, delete,
  export; copy lines only or geometry only (without dimensions/text, by line width)
* Fixed layers (drawing, changes, markups, dimensions, pasted images, zones): show/hide, lock; PDF with real layers,
  SVG with layers
* Editing a single drawing: move/clear regions, crop, rotate, brightness/contrast, image size/resolution (with undo)
* Searchable PDF (invisible OCR text), vectorizing to SVG/PDF/DXF (centre lines or outlines)
* Text search (PDF text or OCR, German and English), comment import from XFDF and PDF, XFDF export
* Manual 3-point alignment, regions, matched areas, zones, multi-page, batch and revision comparison
* Projects (`.zgmax`, with embedded drawings to send along), saved views, autosave, several windows, dark mode, adjustable interface size

## Code layout

| File | Contents |
|---|---|
| `programm/diffcore.py` | Core: loading (image, PDF, DXF), alignment, tile comparison, object search, edge fringes, glyph check, output |
| `programm/diffpipe.py` | Pipeline (load → align → compare), parameters, auto-adjust |
| `programm/diffreport.py` | Change list, review status, annotations, PDF report, Acrobat annotations, title block, OCR, text search |
| `programm/diffvector.py` | PDF vector data: layers/colors, exact comparison, PDF text |
| `programm/diffedit.py` | Editing: move/clear regions, copy (geometry-only filter by line width), crop, rotate, adjust, resize, vectorize |
| `programm/diffxfdf.py` | Comments: read XFDF and PDF annotations, write XFDF |
| `programm/drawing_diff.py` | Command line |
| `programm/drawing_viewer.py` | Program window (entry point), main window workflow, self-test |
| `programm/ui_*.py` | UI: layout (`ui_layout`), side panels (`ui_panels`), canvas (`ui_canvas`; drawing in `ui_canvas_paint`, snapping/measuring in `ui_canvas_snap`, helpers in `ui_canvas_geom`), features (`ui_features`), search (`ui_search`), editing, region tool, clipboard, layers export, vectorizing (`ui_edit`), list (`ui_regions`), markups (`ui_annotations`), project (`ui_project`), export (`ui_export`), theme (`ui_theme`), icons (`ui_icons`), start page (`ui_start`) |
| `programm/version.py`, `programm/CHANGELOG.json` | Version and change history (DE/EN); `packaging/release.py` makes a release and writes `CHANGELOG.md` / `CHANGELOG_EN.md` |
| `programm/i18n.py`, `programm/i18n_en.json` | Translation: German source strings → English |
| `programm/ocr/` | Latin text recognition model (PP-OCRv5, Apache-2.0) for German and English |

The source code (comments, identifiers, UI source strings) is German. UI strings are wrapped in `tr()`;
`packaging/i18n_mark.py --list` lists all keys, and `tests/english_check.py` checks that every key has a translation.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt -r requirements-ocr.txt
.venv/bin/python -m pytest
.venv/bin/python programm/drawing_viewer.py
```

The tests check known changes in synthetic drawings, the UI (headless) and, if the folder `../Beispiele` exists,
fingerprints of the results. If the comparison is changed on purpose: `UPDATE_GOLDEN=1 .venv/bin/python -m pytest`.
`tests/bench.py` measures hits and false alarms on synthetic drawings. Force a language with `ZV_LANG=de` or `ZV_LANG=en`.

## Building portable apps

* macOS (on a Mac): `packaging/build_mac.sh` → `dist/ZGmax.app` and a ZIP. Runs on Macs with the same processor type
  as the build Mac (Apple silicon or Intel).
* Windows (on a Windows PC with Python 3.12+ on the PATH): `packaging\build_windows.bat` → `dist\ZGmax\ZGmax.exe` and a ZIP.
* Linux: `packaging/build_linux.sh` → `dist/ZGmax/ZGmax` and a `.tar.gz`. Runs on systems with the same processor type and
  the same or a newer glibc as the build system.
* On GitHub for all platforms: Actions → "Apps bauen" → "Run workflow" (`.github/workflows/build.yml`) builds and
  self-tests Windows x64, macOS arm64 and Linux x64 on the latest runner systems; the archives are attached to the run as
  artifacts.

The app is self-contained (Python, manuals, OCR model, translations). Check a build with `ZGmax --selbsttest`.
Package versions are pinned in `requirements*.txt`; change them only together and after a test run.

Project files: `.zgmax`. Settings are still stored under the old internal key `drawing_diff/viewer`, so existing
settings and projects keep working after the rename.

## License

ZGmax is free software under the **GNU Affero General Public License 3.0** (AGPL-3.0), see `LICENSE`. It comes without
any warranty. Whoever passes the program on must also make its source code available under the same license.

AGPL-3.0 is required because ZGmax uses PyMuPDF/MuPDF (AGPL-3.0). Other libraries: Qt/PySide6 (LGPL-3.0), OpenCV
(Apache 2.0), NumPy (BSD), Pillow (MIT-CMU), ezdxf (MIT), RapidOCR and the PaddleOCR model (Apache 2.0), ONNX Runtime
(MIT), Python (PSF). The list is also shown in the program under Help → About ZGmax.
