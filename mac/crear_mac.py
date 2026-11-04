# -*- coding: utf-8 -*-
"""
Creador de USB de Overty  ·  versión para macOS  ·  por Gabriel HernArro
Interfaz Liquid Glass (pywebview + WKWebView con vibrancy). En Mac la USB se
graba con dd (imagen cruda): es el modo que siempre arranca. Pide tu contraseña
de macOS para escribir en el disco.
"""
import os, sys, json, time, threading, subprocess, tempfile, hashlib, plistlib, shlex
import urllib.request

import mb_config as CFG


def dir_web():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for d in (os.path.join(base, "web"), os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")):
        if os.path.isdir(d):
            return d
    return os.path.dirname(os.path.abspath(__file__))


def cache_iso():
    d = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "OvertyCreator", "iso")
    os.makedirs(d, exist_ok=True)
    return d


def sh(cmd, timeout=120):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        dec = lambda b: (b or b"").decode("utf-8", "replace")
        return r.returncode, r.stdout, dec(r.stderr)
    except subprocess.TimeoutExpired:
        return -1, b"", "Tiempo agotado"
    except OSError as e:
        return -2, b"", str(e)


# ------------------------------------------------------------------ control remoto
def leer_control():
    req = urllib.request.Request(CFG.CONTROL_URL + "?t=" + str(int(time.time())),
                                 headers={"User-Agent": "OvertyCreator/" + CFG.VERSION, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


# ------------------------------------------------------------------ USB en macOS
def usbs():
    rc, out, _ = sh(["diskutil", "list", "-plist", "external", "physical"])
    if rc != 0 or not out:
        return []
    try:
        data = plistlib.loads(out)
    except Exception:
        return []
    res = []
    for d in data.get("AllDisksAndPartitions", []):
        ident = d.get("DeviceIdentifier")
        if not ident:
            continue
        rc2, out2, _ = sh(["diskutil", "info", "-plist", "/dev/" + ident])
        try:
            info = plistlib.loads(out2)
        except Exception:
            continue
        if info.get("Internal", True):
            continue
        size = info.get("TotalSize", 0) or 0
        nombre = (info.get("MediaName") or info.get("IORegistryEntryName") or "Memoria USB").strip() or "Memoria USB"
        res.append({"n": ident, "nombre": nombre, "gb": round(size / 1024**3, 1)})
    return res


# ------------------------------------------------------------------ descarga (igual que en Windows)
def _sha256(ruta, progreso=None):
    h = hashlib.sha256()
    tam = os.path.getsize(ruta) or 1
    hecho = 0
    with open(ruta, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
            hecho += len(b)
            if progreso:
                progreso(hecho / tam * 100.0, "Verificando el ISO…")
    return h.hexdigest()


def descargar_iso(url, sha, log, progreso):
    destino = os.path.join(cache_iso(), "overty.iso")
    if sha and os.path.isfile(destino) and _sha256(destino, progreso) == sha.lower():
        log("ISO ya descargado y verificado.")
        return destino
    log("Descargando el ISO marcado por " + CFG.FIRMA + "…")
    tmp = destino + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "OvertyCreator/" + CFG.VERSION})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        hecho = 0
        while True:
            b = r.read(1024 * 512)
            if not b:
                break
            f.write(b)
            hecho += len(b)
            if total:
                progreso(hecho / total * 100.0, f"Descargando  {hecho//(1024*1024)} / {total//(1024*1024)} MB")
    os.replace(tmp, destino)
    if sha:
        log("Verificando la descarga…")
        if _sha256(destino, progreso) != sha.lower():
            os.remove(destino)
            raise RuntimeError("El ISO descargado no coincide con su huella de seguridad. Reintenta.")
    return destino


# ------------------------------------------------------------------ grabar con dd (pide contraseña)
def crear_usb(disk_id, iso, log, progreso):
    log(f"Desmontando {disk_id}…")
    progreso(-1, "Preparando la USB…")
    sh(["diskutil", "unmountDisk", "force", "/dev/" + disk_id])
    log("Grabando Overty en la USB (dd). Esto tarda varios minutos; no quites la USB.")
    progreso(-1, "Grabando… no quites la USB")
    raw = "/dev/r" + disk_id      # rdisk = acceso crudo, mucho más rápido
    cmd = f"/bin/dd if={shlex.quote(iso)} of={shlex.quote(raw)} bs=4m"
    # dd en el disco crudo necesita privilegios: se piden con el diálogo de macOS
    script = f'do shell script "{cmd}" with administrator privileges'
    rc, out, err = sh(["osascript", "-e", script], timeout=7200)
    if rc != 0:
        if "-128" in (err or "") or "User canceled" in (err or ""):
            raise RuntimeError("Cancelaste la contraseña: no se grabó nada.")
        raise RuntimeError("No se pudo grabar la USB: " + (err or "").strip()[:160])
    sh(["sync"])
    log("Expulsando…")
    sh(["diskutil", "eject", "/dev/" + disk_id])
    return disk_id


# ------------------------------------------------------------------ API para la interfaz
class API:
    def __init__(self):
        self.estado = {"fase": "cargando", "control": None, "firma": CFG.FIRMA, "version": CFG.VERSION,
                       "usbs": [], "pct": 0, "etapa": "", "log": [], "ocupado": False, "hecho": False}
        self.ventana = None

    def snapshot(self):
        return self.estado

    def _log(self, t):
        self.estado["log"] = (self.estado["log"] + [t])[-60:]

    def _prog(self, pct, etapa):
        self.estado["pct"] = round(pct, 1) if pct >= 0 else -1
        self.estado["etapa"] = etapa

    def arrancar(self):
        threading.Thread(target=self._comprobar, daemon=True).start()

    def _comprobar(self):
        try:
            c = leer_control()
            self.estado["control"] = c
            if not c.get("activo", False):
                self.estado["fase"] = "bloqueado"
            else:
                self.estado["fase"] = "listo"
                self.refrescar_usb()
        except Exception:
            self.estado["fase"] = "sin_internet"

    def reintentar(self):
        self.estado["fase"] = "cargando"
        self.arrancar()
        return True

    def refrescar_usb(self):
        if not self.estado["ocupado"]:
            self.estado["usbs"] = usbs()
        return self.estado["usbs"]

    def crear(self, disco_n):
        if self.estado["ocupado"]:
            return False
        c = self.estado.get("control") or {}
        if not c.get("activo"):
            return False
        iso_info = c.get("iso") or {}
        if not iso_info.get("url"):
            self._log("Gabriel aún no marcó ningún ISO en el control.")
            return False
        self.estado["ocupado"] = True
        self.estado["hecho"] = False
        self.estado["log"] = []

        def tarea():
            try:
                iso = descargar_iso(iso_info["url"], iso_info.get("sha256", ""), self._log, self._prog)
                dst = crear_usb(str(disco_n), iso, self._log, self._prog)
                self._prog(100, "Listo")
                self._log(f"LISTO: la USB ({dst}) está lista. Ya puedes sacarla.")
                self.estado["hecho"] = True
            except Exception as e:
                self._log("ERROR: " + str(e))
                self.estado["etapa"] = "Error"
            finally:
                self.estado["ocupado"] = False
                self.refrescar_usb()

        threading.Thread(target=tarea, daemon=True).start()
        return True


def main():
    import webview
    autotest = "--autotest" in sys.argv
    api = API()
    api.ventana = webview.create_window(f"{CFG.PRODUCTO}  ·  por {CFG.FIRMA}",
                                        url=os.path.join(dir_web(), "crear.html"),
                                        js_api=api, width=940, height=680, min_size=(820, 600),
                                        background_color="#eef3f9", vibrancy=True)
    if autotest:
        def _t():
            time.sleep(2.5)
            os._exit(0)
        threading.Thread(target=_t, daemon=True).start()
    webview.start(api.arrancar)


if __name__ == "__main__":
    main()
