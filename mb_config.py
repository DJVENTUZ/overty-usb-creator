# -*- coding: utf-8 -*-
"""Configuración compartida del Creador de USB de Overty · por Gabriel HernArro."""

FIRMA = "Gabriel HernArro"
PRODUCTO = "Creador de USB · Overty"
VERSION = "1.1.2"

# Repositorio de control (SEPARADO de mainbit-asistente / toolkit).
# Aquí vive control.json, que decide si la app funciona y qué ISO baja.
GH_OWNER = "DJVENTUZ"
GH_REPO = "overty-usb-creator"
GH_RAMA = "main"

# URL pública (solo lectura) que la app de los técnicos consulta al abrir.
CONTROL_URL = f"https://raw.githubusercontent.com/{GH_OWNER}/{GH_REPO}/{GH_RAMA}/control.json"
# API para que TU panel publique cambios (necesita tu token personal).
CONTROL_API = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/control.json"

# Auto-actualización: la app compara su VERSION con este archivo y, si hay una
# más nueva, descarga el .zip de la última versión y se reemplaza sola.
VERSION_URL = f"https://raw.githubusercontent.com/{GH_OWNER}/{GH_REPO}/{GH_RAMA}/version.txt"
DESCARGA = {
    "creador": f"https://github.com/{GH_OWNER}/{GH_REPO}/releases/download/latest/MainbitCreadorUSB.zip",
    "panel": f"https://github.com/{GH_OWNER}/{GH_REPO}/releases/download/latest/PanelControlOverty.zip",
}
