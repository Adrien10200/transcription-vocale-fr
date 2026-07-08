"""Convertit assets/icon.svg en assets/icon.ico (multi-résolutions) via Qt + Pillow."""
import io
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer

HERE = Path(__file__).resolve().parent
SVG = HERE / "icon.svg"
ICO = HERE / "icon.ico"
PNG = HERE / "icon.png"

app = QApplication.instance() or QApplication(sys.argv)

renderer = QSvgRenderer(QByteArray(SVG.read_bytes()))
print("SVG valide :", renderer.isValid())

sizes = [16, 24, 32, 48, 64, 128, 256]

from PIL import Image

pil_imgs = []
for s in sizes:
    img = QImage(s, s, QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    renderer.render(p)
    p.end()
    qb = QBuffer()
    qb.open(QIODevice.WriteOnly)
    img.save(qb, "PNG")
    pil = Image.open(io.BytesIO(bytes(qb.data()))).convert("RGBA")
    pil_imgs.append(pil)

# PNG haute résolution (pour le README)
pil_imgs[-1].save(PNG, format="PNG")
print("PNG écrit :", PNG)

# ICO multi-résolutions (pour l'exe Windows)
pil_imgs[-1].save(ICO, format="ICO", sizes=[(s, s) for s in sizes])
print("ICO écrit :", ICO)
