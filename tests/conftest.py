"""Gemeinsame Hilfen fuer die Tests: kuenstliche Zeichnungen mit bekannten Aenderungen."""
import os
import sys

import cv2
import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "programm"))
EXAMPLES = os.path.join(os.path.dirname(ROOT), "Beispiele")
import tempfile  # noqa: E402
os.environ.setdefault("ZV_DATA_DIR", tempfile.mkdtemp(prefix="zv-test-"))   # Tests nie in echte Programmdaten


def draw_sheet(changed=False):
    """Blatt 1600 x 1100 px. changed=True: Text verschoben, eine Linie entfernt, ein Kreis neu."""
    img = np.full((1100, 1600), 255, np.uint8)
    cv2.rectangle(img, (40, 40), (1560, 1060), 0, 3)                      # Rahmen
    for i in range(6):                                                     # Raster aus Linien
        cv2.line(img, (120, 150 + i * 120), (900, 150 + i * 120), 0, 2)
    if not changed:
        cv2.line(img, (1000, 200), (1450, 200), 0, 3)                      # wird in B entfernt
    cv2.circle(img, (500, 520), 120, 0, 2)
    if changed:
        cv2.circle(img, (1250, 700), 80, 0, 3)                             # neu in B
    dy = 14 if changed else 0                                              # Text nur verschoben
    cv2.putText(img, "MASS 25,4", (1000, 420 + dy), cv2.FONT_HERSHEY_SIMPLEX, 1.4, 0, 3)
    for k in range(30):                                                    # Schraffur
        x = 150 + k * 10
        cv2.line(img, (x, 850), (x + 60, 950), 0, 1)
    return img


@pytest.fixture
def pair(tmp_path):
    from PIL import Image
    pa, pb = tmp_path / "alt.png", tmp_path / "neu.png"
    Image.fromarray(draw_sheet(False)).save(pa, dpi=(200, 200))
    Image.fromarray(draw_sheet(True)).save(pb, dpi=(200, 200))
    return str(pa), str(pb)
