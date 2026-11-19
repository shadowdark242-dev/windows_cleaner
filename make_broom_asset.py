"""Готовит маску иконки-метлы из исходной картинки (чёрный силуэт на светлом/шахматном фоне).

    python make_broom_asset.py path/to/broom.png
Результат — cleanix/ui/broom_data.py (PNG 256×256: белый цвет + альфа, в base64).
"""
import base64
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

app = QGuiApplication(sys.argv)
src = QImage(sys.argv[1]).convertToFormat(QImage.Format.Format_ARGB32)
w, h = src.width(), src.height()
mask = QImage(w, h, QImage.Format.Format_ARGB32)
x0, y0, x1, y1 = w, h, 0, 0
for y in range(h):
    for x in range(w):
        c = src.pixelColor(x, y)
        lum = (c.red() * 299 + c.green() * 587 + c.blue() * 114) // 1000
        a = max(0, min(255, int((200 - lum) * 255 / 150)))      # тёмное → непрозрачно, светлый/серый фон → 0
        mask.setPixelColor(x, y, QColor(255, 255, 255, a))
        if a > 40:
            x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
crop = mask.copy(x0, y0, x1 - x0 + 1, y1 - y0 + 1)
side = max(crop.width(), crop.height())
sq = QImage(side, side, QImage.Format.Format_ARGB32)
sq.fill(Qt.GlobalColor.transparent)
p = QPainter(sq)
p.drawImage((side - crop.width()) // 2, (side - crop.height()) // 2, crop)
p.end()
out = sq.scaled(256, 256, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
ba = QByteArray()
buf = QBuffer(ba)
buf.open(QIODevice.OpenModeFlag.WriteOnly)
out.save(buf, "PNG")
b64 = base64.b64encode(bytes(ba)).decode()
lines = [b64[i:i + 100] for i in range(0, len(b64), 100)]
dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cleanix", "ui", "broom_data.py")
with open(dest, "w") as fh:
    fh.write('"""Маска иконки-метлы (PNG 256x256, белый + альфа). Сгенерировано make_broom_asset.py."""\n')
    fh.write("BROOM_PNG_B64 = (\n" + "\n".join(f'    "{l}"' for l in lines) + "\n)\n")
print("bbox", (x0, y0, x1, y1), "bytes", len(ba))
