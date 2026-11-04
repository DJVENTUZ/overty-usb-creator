# -*- coding: utf-8 -*-
"""
Creador de USB de Overty Disk  ·  por Gabriel HernArro
Interfaz gráfica (una sola pantalla). Baja el ISO que Gabriel marque en el control
remoto y deja la USB lista para arrancar en UEFI. Si el control está desactivado,
la app no funciona.

Firma de Gabriel HernArro visible en: ventana, pantalla principal, "Acerca de",
archivo CREADA-POR.txt en cada USB y propiedades del .exe.
"""
import os, sys, json, time, threading, subprocess, tempfile, hashlib, ctypes
import urllib.request

import mb_config as CFG

IS_WIN = os.name == "nt"
NOWIN = 0x08000000 if IS_WIN else 0          # CREATE_NO_WINDOW


# ------------------------------------------------------------------ utilidades
def dir_base():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def dir_web():
    for d in (os.path.join(dir_base(), "web"),
              os.path.join(getattr(sys, "_MEIPASS", dir_base()), "web")):
        if os.path.isdir(d):
            return d
    return os.path.join(dir_base(), "web")


def cache_iso():
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    d = os.path.join(base, "OvertyCreator", "iso")
    os.makedirs(d, exist_ok=True)
    return d


def ps(cmd, timeout=120):
    """PowerShell silencioso; devuelve (codigo, salida, error)."""
    if not IS_WIN:
        return -2, "", "Solo Windows"
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                           capture_output=True, timeout=timeout, creationflags=NOWIN)
        dec = lambda b: (b or b"").decode("utf-8", "replace")
        return r.returncode, dec(r.stdout), dec(r.stderr)
    except subprocess.TimeoutExpired:
        return -1, "", "Tiempo agotado"
    except OSError as e:
        return -2, "", str(e)


def ps_json(cmd, timeout=60):
    rc, out, _ = ps(cmd, timeout)
    out = (out or "").strip()
    if rc != 0 or not out:
        return None
    try:
        d = json.loads(out)
        return d if isinstance(d, list) else [d]
    except ValueError:
        return None


# ------------------------------------------------------------------ control remoto (kill-switch)
def leer_control():
    """Lee control.json de GitHub. Devuelve dict o lanza excepción si no hay internet."""
    req = urllib.request.Request(CFG.CONTROL_URL + "?t=" + str(int(time.time())),
                                 headers={"User-Agent": "OvertyCreator/" + CFG.VERSION, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


# ------------------------------------------------------------------ discos USB
def usbs():
    cmd = ("Get-Disk | Where-Object { $_.BusType -eq 'USB' -and -not $_.IsBoot -and -not $_.IsSystem } | "
           "ForEach-Object { [pscustomobject]@{ n=$_.Number; nombre=$_.FriendlyName; gb=[math]::Round($_.Size/1GB,1) } } | "
           "ConvertTo-Json -Compress")
    return ps_json(cmd) or []


# ------------------------------------------------------------------ descarga del ISO
def descargar_iso(url, sha, log, progreso):
    destino = os.path.join(cache_iso(), "overty.iso")
    # ¿ya lo tenemos con el sha correcto?
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
            raise RuntimeError("El ISO descargado no coincide con la huella de seguridad. Reintenta.")
    return destino


def _sha256(ruta, progreso=None):
    h = hashlib.sha256()
    tam = os.path.getsize(ruta)
    hecho = 0
    with open(ruta, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
            hecho += len(b)
            if progreso and tam:
                progreso(hecho / tam * 100.0, "Verificando el ISO…")
    return h.hexdigest()


# ------------------------------------------------------------------ crear la USB
def crear_usb(disco_n, iso, log, progreso):
    # 1. formatear FAT32 (lo que arranca en UEFI en cualquier PC)
    log("Preparando la USB…")
    progreso(-1, "Preparando la USB…")
    crear = "create partition primary size=32000" if _tam_disco(disco_n) > 32 * 1024**3 else "create partition primary"
    script = "\r\n".join([f"select disk {disco_n}", "clean", "convert mbr", crear,
                          "format fs=fat32 quick label=OVERTY", "active", "assign"])
    dp = os.path.join(tempfile.gettempdir(), "overty_dp.txt")
    open(dp, "w", encoding="ascii").write(script)
    rc, out, err = ps(f"diskpart /s '{dp}'", timeout=300)
    try:
        os.remove(dp)
    except OSError:
        pass
    if rc != 0:
        raise RuntimeError("No se pudo preparar la USB (diskpart).")
    dst = _letra_disco(disco_n)
    if not dst:
        raise RuntimeError("La USB se formateó pero Windows no le dio letra. Reconéctala y reintenta.")
    log(f"USB lista como {dst}:")

    # 2. montar el ISO
    log("Abriendo el ISO…")
    rc, out, _ = ps(f"(Mount-DiskImage -ImagePath '{iso}' -PassThru | Get-Volume).DriveLetter", timeout=120)
    src = (out or "").strip()[:1]
    for _ in range(15):
        if src:
            break
        time.sleep(1)
        rc, out, _ = ps(f"(Get-DiskImage -ImagePath '{iso}' | Get-Volume).DriveLetter")
        src = (out or "").strip()[:1]
    if not src:
        raise RuntimeError("Windows no pudo abrir el ISO.")

    try:
        # 3. copiar con porcentaje real
        archivos, total = [], 0
        for raiz, _, fs in os.walk(src + ":\\"):
            for nombre in fs:
                p = os.path.join(raiz, nombre)
                try:
                    total += os.path.getsize(p)
                    archivos.append(p)
                except OSError:
                    pass
        grandes = [a for a in archivos if _seguro_tam(a) >= 4 * 1024**3]
        if grandes:
            raise RuntimeError("El ISO trae un archivo de más de 4 GB; no cabe en FAT32. Avísale a Gabriel.")
        log(f"Copiando Overty ({len(archivos)} archivos, {total//(1024*1024)} MB)…")
        copiado = 0
        pref = src + ":\\"
        for a in archivos:
            rel = a[len(pref):]
            d = os.path.join(dst + ":\\", rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            with open(a, "rb") as fi, open(d, "wb") as fo:
                while True:
                    b = fi.read(1024 * 1024)
                    if not b:
                        break
                    fo.write(b)
                    copiado += len(b)
                    if total:
                        progreso(copiado / total * 100.0, f"Copiando  {copiado//(1024*1024)} / {total//(1024*1024)} MB")

        # 4. verificar
        log("Verificando…")
        progreso(-1, "Verificando…")
        n_dst = sum(len(fs) for _, _, fs in os.walk(dst + ":\\"))
        if n_dst < len(archivos):
            raise RuntimeError(f"La USB no quedó completa ({n_dst}/{len(archivos)} archivos). Usa otra USB.")
        if not os.path.isfile(os.path.join(dst + ":\\", "EFI", "BOOT", "BOOTX64.EFI")):
            log("Aviso: no encontré EFI\\BOOT\\BOOTX64.EFI; podría no arrancar en UEFI.")
        firma = (f"USB creada con la herramienta de {CFG.FIRMA}\r\n"
                 f"ISO: {os.path.basename(iso)}\r\n"
                 f"Fecha: {time.strftime('%Y-%m-%d %H:%M')}\r\nEquipo: {os.environ.get('COMPUTERNAME','')}\r\n")
        open(os.path.join(dst + ":\\", "CREADA-POR.txt"), "w", encoding="utf-8").write(firma)
        ps(f"Write-VolumeCache -DriveLetter {dst}")
    finally:
        ps(f"Dismount-DiskImage -ImagePath '{iso}'")
    return dst


def _seguro_tam(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def _tam_disco(n):
    rc, out, _ = ps(f"(Get-Disk {n}).Size")
    try:
        return int((out or "0").strip())
    except ValueError:
        return 0


def _letra_disco(n):
    for _ in range(15):
        time.sleep(1)
        rc, out, _ = ps(f"(Get-Partition -DiskNumber {n} | Where-Object DriveLetter | Select-Object -First 1).DriveLetter")
        l = (out or "").strip()[:1]
        if l:
            return l
    ps(f"Get-Partition -DiskNumber {n} | Where-Object {{$_.Size -gt 1GB}} | Add-PartitionAccessPath -AssignDriveLetter")
    time.sleep(2)
    rc, out, _ = ps(f"(Get-Partition -DiskNumber {n} | Where-Object DriveLetter | Select-Object -First 1).DriveLetter")
    return (out or "").strip()[:1] or None


# ------------------------------------------------------------------ API para la interfaz
class API:
    def __init__(self):
        self.estado = {"fase": "cargando", "control": None, "firma": CFG.FIRMA, "version": CFG.VERSION,
                       "usbs": [], "pct": 0, "etapa": "", "log": [], "ocupado": False, "hecho": False}
        self.ventana = None

    # ---- puente
    def snapshot(self):
        return self.estado

    def _log(self, t):
        self.estado["log"] = (self.estado["log"] + [t])[-60:]

    def _prog(self, pct, etapa):
        self.estado["pct"] = round(pct, 1) if pct >= 0 else -1
        self.estado["etapa"] = etapa

    def arrancar(self):
        threading.Thread(target=self._comprobar_control, daemon=True).start()

    def _comprobar_control(self):
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
                dst = crear_usb(int(disco_n), iso, self._log, self._prog)
                self._prog(100, "Listo")
                self._log(f"LISTO: la USB en {dst}: está lista. Ya puedes sacarla.")
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
    api = API()
    w = webview.create_window(f"{CFG.PRODUCTO}  ·  por {CFG.FIRMA}",
                              url=os.path.join(dir_web(), "crear.html"),
                              js_api=api, width=940, height=680, min_size=(820, 600),
                              background_color="#eef3f9")
    api.ventana = w
    webview.start(api.arrancar, gui="edgechromium")


if __name__ == "__main__":
    main()
