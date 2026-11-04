# -*- coding: utf-8 -*-
"""Genera un icono .ico con los colores de Mainbit (no depende del PNG del logo)."""
import sys
from PIL import Image, ImageDraw

def icono(ruta, anillo=False):
    base = 256
    img = Image.new("RGBA", (base, base), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # cuadrado redondeado degradado azul->marino
    for y in range(base):
        t = y / base
        r = int(0x4a + (0x1b - 0x4a) * t)
        g = int(0x90 + (0x3b - 0x90) * t)
        b = int(0xd2 + (0x5a - 0xd2) * t)
        d.line([(0, y), (base, y)], fill=(r, g, b, 255))
    mask = Image.new("L", (base, base), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, base - 1, base - 1], radius=54, fill=255)
    img.putalpha(mask)
    d = ImageDraw.Draw(img)
    if anillo:  # panel: un anillo (como la "o" del logo)
        d.ellipse([70, 70, 186, 186], outline=(255, 255, 255, 255), width=26)
    else:       # creador: una "M" dibujada con trazos (no depende de ninguna fuente)
        w = 26
        c = (255, 255, 255, 255)
        d.line([(78, 182), (78, 74)], fill=c, width=w, joint="curve")        # pata izq
        d.line([(78, 74), (128, 138)], fill=c, width=w, joint="curve")       # diagonal 1
        d.line([(128, 138), (178, 74)], fill=c, width=w, joint="curve")      # diagonal 2
        d.line([(178, 74), (178, 182)], fill=c, width=w, joint="curve")      # pata der
        for x, y in [(78, 182), (78, 74), (128, 138), (178, 74), (178, 182)]:
            d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=c)
    img.save(ruta, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

if __name__ == "__main__":
    icono(sys.argv[1], anillo=(len(sys.argv) > 2 and sys.argv[2] == "panel"))
