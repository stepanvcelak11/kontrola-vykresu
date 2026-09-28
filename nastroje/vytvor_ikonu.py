"""Vygeneruje ikonu aplikace (kontrola/resources/ikona.png, ikona.ico, ikona.svg).

Spuštění: python nastroje/vytvor_ikonu.py  (potřebuje PySide6 a Pillow)
Malé velikosti (16–32 px) mají zjednodušenou kresbu, aby byly ostré.
"""

import io
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402

BG = """<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#1D4ED8"/><stop offset="1" stop-color="#0891B2"/></linearGradient>
<linearGradient id="ok" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#4ADE80"/><stop offset="1" stop-color="#16A34A"/></linearGradient>
<filter id="st" x="-20%" y="-20%" width="140%" height="140%">
  <feDropShadow dx="0" dy="4" stdDeviation="5" flood-color="#0F172A" flood-opacity="0.35"/></filter>
</defs>
<rect x="8" y="8" width="240" height="240" rx="54" fill="url(#bg)"/>
<path d="M8 120 Q128 60 248 110 L248 62 Q248 8 194 8 L62 8 Q8 8 8 62 Z" fill="#FFFFFF" opacity="0.08"/>"""

FULL = BG + """
<g filter="url(#st)">
  <rect x="42" y="40" width="152" height="170" rx="14" fill="#F8FAFC"/>
</g>
<g stroke="#CBD5E1" stroke-width="2">
  <line x1="42" y1="97" x2="194" y2="97"/><line x1="42" y1="154" x2="194" y2="154"/>
  <line x1="93" y1="40" x2="93" y2="210"/><line x1="144" y1="40" x2="144" y2="210"/>
</g>
<polygon points="62,62 128,56 136,120 70,128" fill="#FECACA" stroke="#DC2626" stroke-width="5" stroke-linejoin="round"/>
<polyline points="60,188 104,150 172,166" fill="none" stroke="#1F2937" stroke-width="6" stroke-linecap="round"
          stroke-linejoin="round"/>
<polyline points="128,56 172,70 176,128" fill="none" stroke="#1F2937" stroke-width="5" stroke-linecap="round"
          stroke-dasharray="11 7"/>
<g>
  <polygon points="104,136 116,158 92,158" fill="#2563EB" stroke="#1E3A8A" stroke-width="2"/>
  <circle cx="104" cy="151" r="3.2" fill="#FFFFFF"/>
</g>
<g filter="url(#st)">
  <circle cx="186" cy="186" r="50" fill="url(#ok)" stroke="#FFFFFF" stroke-width="9"/>
</g>
<polyline points="163,187 180,204 211,170" fill="none" stroke="#FFFFFF" stroke-width="14" stroke-linecap="round"
          stroke-linejoin="round"/>"""

SIMPLE = BG + """
<rect x="40" y="36" width="150" height="176" rx="18" fill="#F8FAFC"/>
<polygon points="64,64 134,58 142,128 72,134" fill="#FECACA" stroke="#DC2626" stroke-width="12" stroke-linejoin="round"/>
<circle cx="184" cy="184" r="58" fill="#22C55E" stroke="#FFFFFF" stroke-width="12"/>
<polyline points="156,186 177,207 213,166" fill="none" stroke="#FFFFFF" stroke-width="20" stroke-linecap="round"
          stroke-linejoin="round"/>"""


def svg(body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">{body}</svg>'


def render(body: str, size: int) -> Image.Image:
    r = QSvgRenderer(QByteArray(svg(body).encode("utf-8")))
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    r.render(p, QRectF(0, 0, size, size))
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


def main():
    QGuiApplication(sys.argv[:1])
    out = Path(__file__).resolve().parents[1] / "kontrola" / "resources"
    (out / "ikona.svg").write_text(svg(FULL), encoding="utf-8")
    big = render(FULL, 256)
    big.save(out / "ikona.png")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [render(SIMPLE if s <= 32 else FULL, s) for s in sizes]
    imgs[-1].save(out / "ikona.ico", format="ICO", sizes=[(s, s) for s in sizes], append_images=imgs[:-1])
    print("hotovo:", out)


if __name__ == "__main__":
    main()
