#!/bin/bash
# =====================================================================
#  Construye las apps de Overty para Mac (Liquid Glass)
#  Doble clic en este archivo. Por Gabriel HernArro.
# =====================================================================
cd "$(dirname "$0")" || exit 1
echo "========================================================"
echo "  Construyendo las apps de Overty para Mac"
echo "  Herramienta de Gabriel HernArro"
echo "========================================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
  echo "Falta Python 3. Instala las Herramientas de linea de comandos con:"
  echo "    xcode-select --install"
  echo "y vuelve a abrir este archivo."
  read -r -p "Enter para cerrar..."; exit 1
fi

echo "1/4  Preparando entorno…"
python3 -m venv .venv || { echo "No se pudo crear el entorno."; read -r; exit 1; }
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null 2>&1
echo "2/4  Instalando dependencias (pywebview, pyinstaller, cryptography)…"
pip install pyinstaller pywebview cryptography >/dev/null 2>&1 || { echo "Fallo instalando dependencias."; read -r; exit 1; }

echo "3/4  Compilando Panel y Creador…"
python -m PyInstaller --noconfirm --clean --windowed --name "Panel Overty" \
  --collect-all webview --collect-all cryptography --add-data "web:web" panel_mac.py >/dev/null 2>&1 \
  || { echo "Fallo compilando el Panel."; read -r; exit 1; }
python -m PyInstaller --noconfirm --clean --windowed --name "Creador USB Overty" \
  --collect-all webview --add-data "web:web" crear_mac.py >/dev/null 2>&1 \
  || { echo "Fallo compilando el Creador."; read -r; exit 1; }

echo "4/4  Copiando al Escritorio…"
DEST="$HOME/Desktop/Overty-Mac"
mkdir -p "$DEST"
rm -rf "$DEST/Panel Overty.app" "$DEST/Creador USB Overty.app"
cp -R "dist/Panel Overty.app" "$DEST/" 2>/dev/null
cp -R "dist/Creador USB Overty.app" "$DEST/" 2>/dev/null
# quita la cuarentena para que macOS no las bloquee al abrir
xattr -dr com.apple.quarantine "$DEST/Panel Overty.app" 2>/dev/null
xattr -dr com.apple.quarantine "$DEST/Creador USB Overty.app" 2>/dev/null

echo
echo "========================================================"
echo "  LISTO. Tus apps estan en el Escritorio, carpeta Overty-Mac:"
echo "    • Panel Overty.app"
echo "    • Creador USB Overty.app"
echo "========================================================"
read -r -p "Enter para cerrar..."
