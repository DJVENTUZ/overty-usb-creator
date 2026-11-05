# -*- coding: utf-8 -*-
"""
Auto-actualización de las apps de Overty · por Gabriel HernArro
Compara la versión instalada con version.txt del repositorio; si hay una más
nueva, descarga el .zip de la última versión, reemplaza los archivos y relanza.
Todo es best-effort: si algo falla, la app sigue funcionando con su versión actual.
"""
import os, sys, tempfile, zipfile, subprocess
import urllib.request

import mb_config as CFG

NOWIN = 0x08000000 if os.name == "nt" else 0


def _num(v):
    try:
        return tuple(int(x) for x in str(v).strip().split("."))
    except Exception:
        return (0,)


def hay_version_nueva():
    """Devuelve la versión nueva (str) si existe, o None."""
    try:
        req = urllib.request.Request(CFG.VERSION_URL + "?t=" + str(os.getpid()),
                                     headers={"User-Agent": "Overty/" + CFG.VERSION, "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=10) as r:
            v = r.read().decode("utf-8").strip().split()[0]
        return v if _num(v) > _num(CFG.VERSION) else None
    except Exception:
        return None


def actualizar(cual, exe_nombre, log=lambda *a: None):
    """Descarga y aplica la actualización. No regresa si tiene éxito (relanza y sale)."""
    if not getattr(sys, "frozen", False) or os.name != "nt":
        return False  # solo cuando corre como .exe en Windows
    url = CFG.DESCARGA.get(cual)
    if not url:
        return False
    try:
        appdir = os.path.dirname(sys.executable)
        tmp = tempfile.mkdtemp(prefix="overty_upd_")
        zf = os.path.join(tmp, "upd.zip")
        log("Descargando la actualización…")
        req = urllib.request.Request(url, headers={"User-Agent": "Overty/" + CFG.VERSION})
        with urllib.request.urlopen(req, timeout=120) as r, open(zf, "wb") as f:
            while True:
                b = r.read(1024 * 256)
                if not b:
                    break
                f.write(b)
        nuevo = os.path.join(tmp, "nuevo")
        os.makedirs(nuevo, exist_ok=True)
        with zipfile.ZipFile(zf) as z:
            z.extractall(nuevo)
        # script que espera a que cierre la app, copia encima y relanza
        bat = os.path.join(tmp, "aplicar.bat")
        destino_exe = os.path.join(appdir, exe_nombre)
        with open(bat, "w", encoding="ascii") as f:
            f.write("@echo off\r\n"
                    "ping -n 3 127.0.0.1 >nul\r\n"
                    f'robocopy "{nuevo}" "{appdir}" /E /IS /IT /R:1 /W:1 /NFL /NDL /NJH /NJS >nul\r\n'
                    f'start "" "{destino_exe}"\r\n'
                    f'rmdir /s /q "{tmp}" >nul 2>&1\r\n')
        subprocess.Popen(["cmd", "/c", bat], creationflags=0x00000008 | NOWIN)  # DETACHED_PROCESS
        os._exit(0)
    except Exception:
        return False
