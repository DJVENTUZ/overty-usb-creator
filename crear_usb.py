# -*- coding: utf-8 -*-
"""
Creador de USB de Overty Disk  ·  por Gabriel HernArro
Interfaz nativa (Tkinter): funciona en cualquier Windows, físico o en máquina
virtual, sin depender de aceleración gráfica. Baja el ISO que Gabriel marque en
el control remoto y deja la USB lista para arrancar en UEFI.
"""
import os, sys, json, time, threading, subprocess, tempfile, hashlib
import urllib.request
import tkinter as tk
from tkinter import ttk

import mb_config as CFG
import mb_update

IS_WIN = os.name == "nt"
NOWIN = 0x08000000 if IS_WIN else 0

# Paleta Mainbit
BG = "#eef3f9"; CARD = "#ffffff"; NAVY = "#1b3b5a"; BLUE = "#3a7fc0"; BLUE2 = "#4a90d2"
INK = "#16304a"; INK2 = "#6b84a0"; LINE = "#dbe6f1"; OK = "#2ea86a"; WARN = "#d9902a"; RED = "#cf4b42"


def recurso(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# ------------------------------------------------------------------ backend (sin cambios de fondo)
def cache_iso():
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    d = os.path.join(base, "OvertyCreator", "iso")
    os.makedirs(d, exist_ok=True)
    return d


def ps(cmd, timeout=120):
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


def leer_control():
    req = urllib.request.Request(CFG.CONTROL_URL + "?t=" + str(int(time.time())),
                                 headers={"User-Agent": "OvertyCreator/" + CFG.VERSION, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def usbs():
    cmd = ("Get-Disk | Where-Object { $_.BusType -eq 'USB' -and -not $_.IsBoot -and -not $_.IsSystem } | "
           "ForEach-Object { [pscustomobject]@{ n=$_.Number; nombre=$_.FriendlyName; gb=[math]::Round($_.Size/1GB,1) } } | "
           "ConvertTo-Json -Compress")
    return ps_json(cmd) or []


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


def _seguro_tam(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def crear_usb(disco_n, iso, log, progreso):
    """Graba el ISO en la USB en MODO IMAGEN (escritura cruda al disco físico),
    igual que 'dd' / Rufus-DD. Es el único método que arranca de forma fiable este
    tipo de imagen live. Necesita permisos de administrador."""
    import ctypes
    from ctypes import wintypes

    # 1) limpiar el disco: quita particiones y libera bloqueos de Windows
    log("Preparando la USB…")
    progreso(-1, "Preparando la USB…")
    script = "\r\n".join([f"select disk {disco_n}", "clean", "rescan"])
    dp = os.path.join(tempfile.gettempdir(), "overty_dp.txt")
    open(dp, "w", encoding="ascii").write(script)
    rc, out, err = ps(f"diskpart /s '{dp}'", timeout=180)
    try:
        os.remove(dp)
    except OSError:
        pass
    if rc != 0:
        raise RuntimeError("No se pudo preparar la USB (diskpart).")
    time.sleep(2)

    # 2) escritura cruda del ISO al disco físico \\.\PhysicalDrive<N>
    total = os.path.getsize(iso)
    log(f"Grabando Overty en la USB (modo imagen, {total//(1024*1024)} MB)…")
    GENERIC_RW = 0x80000000 | 0x40000000
    SHARE_RW = 0x00000001 | 0x00000002
    OPEN_EXISTING = 3
    INVALID = ctypes.c_void_p(-1).value
    k = ctypes.windll.kernel32
    k.CreateFileW.restype = ctypes.c_void_p
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                              wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    path = f"\\\\.\\PhysicalDrive{disco_n}"
    h = k.CreateFileW(path, GENERIC_RW, SHARE_RW, None, OPEN_EXISTING, 0, None)
    if h == INVALID or h is None:
        raise RuntimeError("No pude abrir la USB para escritura. Reconéctala y reintenta como administrador.")
    try:
        # bloquea y desmonta cualquier volumen remanente (ignora errores si no hay)
        for ctl in (0x00090018, 0x00090020):  # FSCTL_LOCK_VOLUME, FSCTL_DISMOUNT_VOLUME
            br = wintypes.DWORD(0)
            k.DeviceIoControl(ctypes.c_void_p(h), ctl, None, 0, None, 0, ctypes.byref(br), None)
        escrito = 0
        CH = 4 * 1024 * 1024
        with open(iso, "rb") as src:
            while True:
                b = src.read(CH)
                if not b:
                    break
                if len(b) % 512:                       # alinear a sector
                    b += b"\x00" * (512 - len(b) % 512)
                wr = wintypes.DWORD(0)
                ok = k.WriteFile(ctypes.c_void_p(h), b, len(b), ctypes.byref(wr), None)
                if not ok or wr.value != len(b):
                    raise RuntimeError(f"Fallo al escribir en la USB (error {k.GetLastError()}).")
                escrito += len(b)
                if total:
                    progreso(min(99.0, escrito / total * 100.0), f"Grabando  {escrito//(1024*1024)} / {total//(1024*1024)} MB")
        k.FlushFileBuffers(ctypes.c_void_p(h))
    finally:
        k.CloseHandle(ctypes.c_void_p(h))

    # 3) verificar: releer el primer MB y compararlo con el ISO
    log("Verificando…")
    progreso(-1, "Verificando…")
    try:
        h2 = k.CreateFileW(path, 0x80000000, SHARE_RW, None, OPEN_EXISTING, 0, None)
        if h2 and h2 != INVALID:
            buf = ctypes.create_string_buffer(1024 * 1024)
            rd = wintypes.DWORD(0)
            k.ReadFile(ctypes.c_void_p(h2), buf, len(buf), ctypes.byref(rd), None)
            k.CloseHandle(ctypes.c_void_p(h2))
            with open(iso, "rb") as src:
                esperado = src.read(1024 * 1024)
            if buf.raw[:len(esperado)] != esperado:
                raise RuntimeError("La verificación no coincidió. Reintenta o usa otra USB.")
    except OSError:
        pass

    log(f"USB grabada correctamente ({total//(1024*1024)} MB).")
    return None


def crear_ventoy(disco_n, iso, log, progreso):
    """Instala Ventoy en la USB (queda reutilizable y multi-ISO) y copia el ISO.
    Ventoy arranca el ISO montándolo, así que el usbfix (sin live-media) arranca bien."""
    vexe = recurso(os.path.join("ventoy", "Ventoy2Disk.exe"))
    if not os.path.isfile(vexe):
        raise RuntimeError("Este programa no incluye Ventoy. Usa el modo Imagen.")
    log("Instalando Ventoy en la USB…")
    progreso(-1, "Instalando Ventoy…")
    try:
        r = subprocess.run([vexe, "VTOYCLI", "/I", f"/PhyDrive:{disco_n}"],
                           input=b"y\r\ny\r\n", cwd=os.path.dirname(vexe),
                           capture_output=True, timeout=600, creationflags=NOWIN)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Ventoy tardó demasiado. Reintenta o usa el modo Imagen.")
    if r.returncode != 0:
        raise RuntimeError("Ventoy no pudo instalarse (¿la USB está en uso? ¿protegida contra escritura?).")
    # buscar la partición de datos de Ventoy (etiqueta 'Ventoy')
    letra = None
    for _ in range(25):
        time.sleep(1)
        rc, out, _ = ps(f"(Get-Partition -DiskNumber {disco_n} | Get-Volume | "
                        f"Where-Object {{$_.FileSystemLabel -eq 'Ventoy'}}).DriveLetter")
        letra = (out or "").strip()[:1]
        if letra:
            break
    if not letra:
        raise RuntimeError("Ventoy se instaló pero no apareció su partición. Reconecta la USB y copia el ISO a mano.")
    log(f"Copiando Overty a la USB ({letra}:)…")
    destino = os.path.join(letra + ":\\", "overty.iso")
    total = os.path.getsize(iso)
    hecho = 0
    with open(iso, "rb") as s, open(destino, "wb") as d:
        while True:
            b = s.read(4 * 1024 * 1024)
            if not b:
                break
            d.write(b)
            hecho += len(b)
            if total:
                progreso(hecho / total * 100.0, f"Copiando  {hecho//(1024*1024)} / {total//(1024*1024)} MB")
    ps(f"Write-VolumeCache -DriveLetter {letra}")
    return letra


# ------------------------------------------------------------------ interfaz Tkinter
class App:
    def __init__(self, root, autotest=False):
        self.root = root
        self.autotest = autotest
        self.fase = "cargando"
        self.control = None
        self.sel = tk.IntVar(value=-1)
        self.modo = tk.StringVar(value="imagen")
        self.lista_usb = []
        self.ocupado = False

        root.title(f"{CFG.PRODUCTO}  ·  por {CFG.FIRMA}")
        root.configure(bg=BG)
        root.geometry("900x650")
        root.minsize(820, 600)
        try:
            self._logo = tk.PhotoImage(file=recurso(os.path.join("assets", "logo_h.png")))
            root.iconphoto(True, self._logo)
        except Exception:
            self._logo = None

        self._encabezado()
        self.cuerpo = tk.Frame(root, bg=BG)
        self.cuerpo.pack(fill="both", expand=True, padx=22, pady=(0, 10))
        self._pie()

        if autotest:
            self.control = {"activo": True, "iso": {"nombre": "Overty Disk (USB fix)", "url": "x"}}
            self.lista_usb = [{"n": 1, "nombre": "SanDisk Cruzer Glide", "gb": 14.4},
                              {"n": 2, "nombre": "Kingston DataTraveler", "gb": 28.8}]
            self.fase = "listo"
            self._render()
            root.after(1500, self._captura)
        else:
            threading.Thread(target=self._auto_update, daemon=True).start()
            threading.Thread(target=self._comprobar, daemon=True).start()

    def _auto_update(self):
        try:
            v = mb_update.hay_version_nueva()
            if v:
                mb_update.actualizar("creador", "MainbitCreadorUSB.exe")  # descarga, reemplaza y relanza
        except Exception:
            pass

    # ---- estructura fija
    def _encabezado(self):
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=22, pady=(16, 12))
        chip = tk.Frame(top, bg="#ffffff", padx=10, pady=6)
        chip.pack(side="left")
        if self._logo:
            tk.Label(chip, image=self._logo, bg="#ffffff").pack()
        else:
            tk.Label(chip, text="Mainbit", bg="#ffffff", fg=NAVY, font=("Segoe UI", 15, "bold")).pack()
        tit = tk.Frame(top, bg=BG)
        tit.pack(side="left", padx=14)
        tk.Label(tit, text="Creador de USB · Overty", bg=BG, fg=INK, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(tit, text="Deja la memoria lista para arrancar, en un clic", bg=BG, fg=INK2,
                 font=("Segoe UI", 9)).pack(anchor="w")
        tk.Label(top, text=f"Herramienta de {CFG.FIRMA}", bg=BG, fg=INK2, font=("Segoe UI", 9)).pack(side="right")

    def _pie(self):
        tk.Label(self.root, text=f"© 2026 {CFG.FIRMA} · v{CFG.VERSION}", bg=BG, fg=INK2,
                 font=("Segoe UI", 8)).pack(side="bottom", pady=6)

    def _boton(self, parent, texto, cmd, tipo="pri", **kw):
        colores = {"pri": (BLUE, "#ffffff"), "ok": (OK, "#ffffff"), "soft": ("#e7eef7", INK)}
        bg, fg = colores.get(tipo, colores["pri"])
        b = tk.Button(parent, text=texto, command=cmd, bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                      relief="flat", bd=0, font=("Segoe UI", 10, "bold"), cursor="hand2", padx=18, pady=9, **kw)
        return b

    def _card(self):
        c = tk.Frame(self.cuerpo, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        c.pack(fill="both", expand=True)
        return c

    # ---- marshalling a la UI
    def ui(self, fn, *a):
        try:
            self.root.after(0, lambda: fn(*a))
        except Exception:
            pass

    # ---- lógica
    def _comprobar(self):
        try:
            c = leer_control()
            self.control = c
            if not c.get("activo", False):
                self.fase = "bloqueado"
            else:
                self.fase = "listo"
                self.lista_usb = usbs()
        except Exception:
            self.fase = "sin_internet"
        self.ui(self._render)

    def refrescar_usb(self):
        if not self.ocupado:
            self.lista_usb = usbs()
            self._render()

    def reintentar(self):
        self.fase = "cargando"
        self._render()
        threading.Thread(target=self._comprobar, daemon=True).start()

    # ---- pantallas
    def _limpiar(self):
        for w in self.cuerpo.winfo_children():
            w.destroy()

    def _render(self):
        self._limpiar()
        if self.fase == "cargando":
            return self._centro("Comprobando…", "Verificando la licencia y el ISO.", INK2)
        if self.fase == "sin_internet":
            c = self._centro("Sin conexión", "Esta herramienta necesita internet para verificar la licencia\ny descargar el ISO.", WARN)
            self._boton(c, "Reintentar", self.reintentar).pack(pady=8)
            return
        if self.fase == "bloqueado":
            m = (self.control or {}).get("mensaje") or "Herramienta desactivada."
            return self._centro("Acceso desactivado", m, RED)
        return self._listo()

    def _centro(self, titulo, sub, color):
        c = self._card()
        box = tk.Frame(c, bg=CARD)
        box.place(relx=0.5, rely=0.45, anchor="center")
        tk.Label(box, text=titulo, bg=CARD, fg=color, font=("Segoe UI", 16, "bold")).pack()
        tk.Label(box, text=sub, bg=CARD, fg=INK2, font=("Segoe UI", 10), justify="center").pack(pady=6)
        return box

    def _listo(self):
        c = self._card()
        pad = tk.Frame(c, bg=CARD)
        pad.pack(fill="both", expand=True, padx=22, pady=18)
        iso = (self.control or {}).get("iso") or {}
        # chip de estado del ISO
        chip = tk.Frame(pad, bg="#eef6ef", highlightbackground="#cfe6d4", highlightthickness=1)
        chip.pack(fill="x", pady=(0, 14))
        txt = ("✓   Overty listo para grabar · se descarga automáticamente" if iso.get("url")
               else f"!   Aún no hay un Overty disponible. Contacta a {CFG.FIRMA}.")
        tk.Label(chip, text=txt, bg="#eef6ef", fg=(INK if iso.get("url") else "#8a6a2e"),
                 font=("Segoe UI", 10), anchor="w", padx=12, pady=10).pack(fill="x")

        tk.Label(pad, text="ELIGE LA MEMORIA USB", bg=CARD, fg=INK2, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        cont = tk.Frame(pad, bg=CARD)
        cont.pack(fill="both", expand=True, pady=8)
        if self.lista_usb:
            for u in self.lista_usb:
                fila = tk.Frame(cont, bg="#f7fbff", highlightbackground=LINE, highlightthickness=1)
                fila.pack(fill="x", pady=4)
                rb = tk.Radiobutton(fila, variable=self.sel, value=u["n"], bg="#f7fbff", activebackground="#f7fbff",
                                    command=self._render, takefocus=0)
                rb.pack(side="left", padx=(8, 0))
                info = tk.Frame(fila, bg="#f7fbff")
                info.pack(side="left", fill="x", expand=True, pady=8)
                tk.Label(info, text=u["nombre"], bg="#f7fbff", fg=INK, font=("Segoe UI", 11, "bold")).pack(anchor="w")
                tk.Label(info, text=f"Disco {u['n']} · se borrará todo su contenido", bg="#f7fbff", fg=INK2,
                         font=("Segoe UI", 9)).pack(anchor="w")
                tk.Label(fila, text=f"{u['gb']} GB", bg="#f7fbff", fg=NAVY,
                         font=("Segoe UI", 12, "bold")).pack(side="right", padx=14)
        else:
            tk.Label(cont, text="Conecta una memoria USB (8 GB o más) y aparecerá aquí.",
                     bg=CARD, fg=INK2, font=("Segoe UI", 10)).pack(pady=24)

        # selector de modo de grabado
        modo_f = tk.Frame(pad, bg=CARD)
        modo_f.pack(fill="x", pady=(10, 0))
        tk.Label(modo_f, text="MODO", bg=CARD, fg=INK2, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Radiobutton(modo_f, variable=self.modo, value="imagen", bg=CARD, activebackground=CARD, fg=INK,
                       selectcolor="#e7eef7", font=("Segoe UI", 10), anchor="w", takefocus=0,
                       text="  Imagen — USB dedicada a Overty. Siempre arranca. (recomendado)").pack(fill="x")
        tk.Radiobutton(modo_f, variable=self.modo, value="ventoy", bg=CARD, activebackground=CARD, fg=INK,
                       selectcolor="#e7eef7", font=("Segoe UI", 10), anchor="w", takefocus=0,
                       text="  Ventoy — USB reutilizable, puede llevar varios ISOs. También arranca.").pack(fill="x")

        barra = tk.Frame(pad, bg=CARD)
        barra.pack(fill="x", pady=(10, 0))
        tk.Label(barra, text="⚠ La USB que elijas se borra por completo.", bg=CARD, fg=INK2,
                 font=("Segoe UI", 9)).pack(side="left")
        puede = bool(iso.get("url")) and self.lista_usb
        self._boton(barra, "Crear USB", self._crear, "pri",
                    state=("normal" if puede else "disabled")).pack(side="right")
        self._boton(barra, "Actualizar", self.refrescar_usb, "soft").pack(side="right", padx=8)

    def _crear(self):
        if self.ocupado or self.sel.get() < 0:
            return
        disco = self.sel.get()
        modo = self.modo.get()
        self.ocupado = True
        self._pantalla_progreso()
        threading.Thread(target=self._tarea, args=(disco, modo), daemon=True).start()

    def _pantalla_progreso(self):
        self._limpiar()
        c = self._card()
        pad = tk.Frame(c, bg=CARD)
        pad.pack(fill="both", expand=True, padx=22, pady=18)
        self.lbl_pct = tk.Label(pad, text="0%", bg=CARD, fg=NAVY, font=("Segoe UI", 30, "bold"))
        self.lbl_pct.pack(anchor="w")
        self.lbl_etapa = tk.Label(pad, text="Preparando…", bg=CARD, fg=INK2, font=("Segoe UI", 10))
        self.lbl_etapa.pack(anchor="w")
        self.pbar = ttk.Progressbar(pad, maximum=100, length=100)
        self.pbar.pack(fill="x", pady=10)
        self.txt = tk.Text(pad, height=12, bg="#f6f9fc", fg=INK2, relief="flat", font=("Consolas", 9),
                           highlightbackground=LINE, highlightthickness=1, padx=10, pady=8, wrap="word")
        self.txt.pack(fill="both", expand=True)
        self.txt.configure(state="disabled")
        self.fin_frame = tk.Frame(pad, bg=CARD)
        self.fin_frame.pack(fill="x", pady=(10, 0))

    def _log(self, t):
        def _():
            self.txt.configure(state="normal")
            self.txt.insert("end", t + "\n")
            self.txt.see("end")
            self.txt.configure(state="disabled")
        self.ui(_)

    def _prog(self, pct, etapa):
        def _():
            if pct < 0:
                self.pbar.configure(mode="indeterminate")
                self.pbar.start(12)
                self.lbl_pct.configure(text="···")
            else:
                self.pbar.stop()
                self.pbar.configure(mode="determinate", value=pct)
                self.lbl_pct.configure(text=f"{int(pct)}%")
            self.lbl_etapa.configure(text=etapa)
        self.ui(_)

    def _tarea(self, disco, modo="imagen"):
        try:
            iso_info = (self.control or {}).get("iso") or {}
            iso = descargar_iso(iso_info["url"], iso_info.get("sha256", ""), self._log, self._prog)
            if modo == "ventoy":
                crear_ventoy(int(disco), iso, self._log, self._prog)
                self._prog(100, "Listo")
                self._log("LISTO: USB con Ventoy lista. Arranca desde ella y elige Overty en el menú.")
            else:
                crear_usb(int(disco), iso, self._log, self._prog)
                self._prog(100, "Listo")
                self._log("LISTO: la USB está lista. Ya puedes sacarla.")
            self.ui(self._exito)
        except Exception as e:
            self._log("ERROR: " + str(e))
            self.ui(lambda: self.lbl_etapa.configure(text="Error", fg=RED))
            self.ui(self._reintentar_btn)
        finally:
            self.ocupado = False

    def _exito(self):
        tk.Label(self.fin_frame, text="✔ Lista. Arranca la PC desde la USB (F12, modo UEFI).",
                 bg=CARD, fg=OK, font=("Segoe UI", 10, "bold")).pack(side="left")
        self._boton(self.fin_frame, "Crear otra", self._otra, "pri").pack(side="right")

    def _reintentar_btn(self):
        self._boton(self.fin_frame, "Volver", self._otra, "soft").pack(side="right")

    def _otra(self):
        self.sel.set(-1)
        self.refrescar_usb()
        self.fase = "listo"
        self._render()

    def _captura(self):
        try:
            from PIL import ImageGrab
            self.root.update_idletasks()
            x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
            w, h = self.root.winfo_width(), self.root.winfo_height()
            ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(os.environ.get("MB_SHOT", "shot_creador.png"))
        except Exception as e:
            print("captura falló:", e)
        self.root.destroy()


def main():
    autotest = "--autotest" in sys.argv
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App(root, autotest=autotest)
    root.mainloop()


if __name__ == "__main__":
    main()
