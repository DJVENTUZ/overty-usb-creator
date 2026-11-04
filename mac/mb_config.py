# -*- coding: utf-8 -*-
"""Configuración compartida del Creador de USB de Overty · por Gabriel HernArro."""

FIRMA = "Gabriel HernArro"
PRODUCTO = "Creador de USB · Overty"
VERSION = "1.0.0"

# Repositorio de control (SEPARADO de mainbit-asistente / toolkit).
# Aquí vive control.json, que decide si la app funciona y qué ISO baja.
GH_OWNER = "DJVENTUZ"
GH_REPO = "overty-usb-creator"
GH_RAMA = "main"

# URL pública (solo lectura) que la app de los técnicos consulta al abrir.
CONTROL_URL = f"https://raw.githubusercontent.com/{GH_OWNER}/{GH_REPO}/{GH_RAMA}/control.json"
# API para que TU panel publique cambios (necesita tu token personal).
CONTROL_API = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/control.json"
