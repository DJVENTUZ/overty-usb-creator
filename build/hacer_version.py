# -*- coding: utf-8 -*-
"""Genera el archivo de versión de Windows para PyInstaller, con la firma de Gabriel HernArro."""
import sys

FIRMA = "Gabriel HernArro"
VER = "1.0.0.0"

def escribir(ruta, nombre_producto, descripcion, exe):
    v = VER.split(".")
    txt = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({v[0]},{v[1]},{v[2]},{v[3]}), prodvers=({v[0]},{v[1]},{v[2]},{v[3]}),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)),
  kids=[
    StringFileInfo([StringTable('040c04b0', [
      StringStruct('CompanyName', '{FIRMA}'),
      StringStruct('FileDescription', '{descripcion}'),
      StringStruct('FileVersion', '{VER}'),
      StringStruct('InternalName', '{exe}'),
      StringStruct('LegalCopyright', '(c) 2026 {FIRMA}. Todos los derechos reservados.'),
      StringStruct('OriginalFilename', '{exe}.exe'),
      StringStruct('ProductName', '{nombre_producto}'),
      StringStruct('ProductVersion', '{VER}'),
      StringStruct('Comments', 'Desarrollado por {FIRMA}')])]),
    VarFileInfo([VarStruct('Translation', [1036, 1200])])
  ]
)"""
    open(ruta, "w", encoding="utf-8").write(txt)

if __name__ == "__main__":
    if sys.argv[1] == "creador":
        escribir("ver_creador.txt", "Creador de USB Overty - Mainbit", "Creador de USB de Overty", "MainbitCreadorUSB")
    else:
        escribir("ver_panel.txt", "Panel de control Overty", "Panel de control de Overty", "PanelControlOverty")
