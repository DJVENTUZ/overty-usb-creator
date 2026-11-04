# -*- coding: utf-8 -*-
"""
Panel de control de Overty  ·  SOLO para Gabriel HernArro
Interfaz nativa (Tkinter): funciona en cualquier Windows, físico o en VM.
Activa/desactiva la herramienta de los técnicos y SUBE el ISO que deben usar.
Tu token de GitHub se guarda cifrado en este equipo con un PIN que solo tú sabes.
"""
import os, sys, json, base64, time, threading, hashlib, http.client
import urllib.request, urllib.error
import tkinter as tk
from tkinter import ttk, filedialog

import mb_config as CFG

APPDATA = os.environ.get("APPDATA") or os.path.expanduser("~")
CFG_DIR = os.path.join(APPDATA, "OvertyPanel")
CFG_BIN = os.path.join(CFG_DIR, "cfg.bin")
GH_API = f"https://api.github.com/repos/{CFG.GH_OWNER}/{CFG.GH_REPO}"

NAVY = "#12263d"; PANEL = "#17304d"; CARD = "#1d3a5b"; FIELD = "#13263d"
INK = "#eaf2fb"; INK2 = "#9db6d0"; BLUE = "#3a7fc0"; OK = "#3fd07f"; RED = "#ff6b61"
LINEC = "#2c4a66"


def recurso(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


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
                progreso(hecho / tam * 100.0, "Calculando huella de seguridad…")
    return h.hexdigest()


# ------------------------------------------------------------------ cifrado del token con el PIN
def _clave(pin, salt):
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200000)
    return base64.urlsafe_b64encode(kdf.derive(pin.encode("utf-8")))


def guardar_token(pin, token):
    from cryptography.fernet import Fernet
    os.makedirs(CFG_DIR, exist_ok=True)
    salt = os.urandom(16)
    tok = Fernet(_clave(pin, salt)).encrypt(token.encode("utf-8"))
    with open(CFG_BIN, "wb") as f:
        f.write(salt + b"\n" + tok)


def leer_token(pin):
    from cryptography.fernet import Fernet
    if not os.path.isfile(CFG_BIN):
        return None
    raw = open(CFG_BIN, "rb").read().split(b"\n", 1)
    if len(raw) != 2:
        return None
    try:
        return Fernet(_clave(pin, raw[0])).decrypt(raw[1]).decode("utf-8")
    except Exception:
        return None


def hay_token():
    return os.path.isfile(CFG_BIN)


# ------------------------------------------------------------------ GitHub
def _req(url, token, metodo="GET", data=None):
    req = urllib.request.Request(url, method=metodo,
                                 headers={"Authorization": "token " + token,
                                          "Accept": "application/vnd.github+json",
                                          "User-Agent": "OvertyPanel/" + CFG.VERSION})
    if data is not None:
        req.data = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        b = r.read()
        return json.loads(b) if b else {}


def leer_actual(token):
    try:
        j = _req(CFG.CONTROL_API, token)
        return json.loads(base64.b64decode(j["content"]).decode("utf-8")), j["sha"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        raise


def publicar(token, control, sha):
    control["firma"] = CFG.FIRMA
    control["actualizado"] = time.strftime("%Y-%m-%d %H:%M")
    cuerpo = json.dumps(control, ensure_ascii=False, indent=2)
    data = {"message": f"control: {'activo' if control.get('activo') else 'DESACTIVADO'} · {control['actualizado']}",
            "content": base64.b64encode(cuerpo.encode("utf-8")).decode("ascii"), "branch": CFG.GH_RAMA}
    if sha:
        data["sha"] = sha
    return _req(CFG.CONTROL_API, token, "PUT", data)


def _release_iso(token):
    try:
        return _req(GH_API + "/releases/tags/iso", token)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return _req(GH_API + "/releases", token, "POST",
                        {"tag_name": "iso", "name": "ISO de Overty (vigente)",
                         "body": "ISO que descargan los técnicos. Lo administra Gabriel HernArro desde el Panel."})
        raise


def subir_asset(token, release_id, ruta, progreso):
    size = os.path.getsize(ruta)
    conn = http.client.HTTPSConnection("uploads.github.com", timeout=1800)
    path = f"/repos/{CFG.GH_OWNER}/{CFG.GH_REPO}/releases/{release_id}/assets?name=overty.iso"
    conn.putrequest("POST", path)
    conn.putheader("Authorization", "token " + token)
    conn.putheader("Content-Type", "application/octet-stream")
    conn.putheader("Content-Length", str(size))
    conn.putheader("Accept", "application/vnd.github+json")
    conn.putheader("User-Agent", "OvertyPanel/" + CFG.VERSION)
    conn.endheaders()
    enviado = 0
    with open(ruta, "rb") as f:
        while True:
            b = f.read(1024 * 512)
            if not b:
                break
            conn.send(b)
            enviado += len(b)
            progreso(enviado / size * 100.0, f"Subiendo  {enviado//(1024*1024)} / {size//(1024*1024)} MB")
    r = conn.getresponse()
    cuerpo = r.read()
    conn.close()
    if r.status not in (200, 201):
        raise RuntimeError(f"GitHub rechazó la subida (código {r.status}).")
    return json.loads(cuerpo)["browser_download_url"]


# ------------------------------------------------------------------ interfaz Tkinter
class App:
    def __init__(self, root, autotest=False):
        self.root = root
        self.autotest = autotest
        self.token = None
        self.control = None
        self.sha = None

        root.title(f"Panel de control · Overty  ·  {CFG.FIRMA}")
        root.configure(bg=NAVY)
        root.geometry("740x720")
        root.minsize(680, 640)
        try:
            self._logo = tk.PhotoImage(file=recurso(os.path.join("assets", "logo_h.png")))
            root.iconphoto(True, self._logo)
        except Exception:
            self._logo = None

        self._encabezado()
        self.cuerpo = tk.Frame(root, bg=NAVY)
        self.cuerpo.pack(fill="both", expand=True, padx=22, pady=(0, 10))
        tk.Label(root, text=f"© 2026 {CFG.FIRMA} · Panel v{CFG.VERSION} · {CFG.GH_OWNER}/{CFG.GH_REPO}",
                 bg=NAVY, fg=INK2, font=("Segoe UI", 8)).pack(side="bottom", pady=6)

        if autotest:
            self._login()
            root.after(1500, self._captura)
        else:
            self._login()

    def _encabezado(self):
        top = tk.Frame(self.root, bg=NAVY)
        top.pack(fill="x", padx=22, pady=(16, 12))
        chip = tk.Frame(top, bg="#ffffff", padx=9, pady=5)
        chip.pack(side="left")
        if self._logo:
            tk.Label(chip, image=self._logo, bg="#ffffff").pack()
        else:
            tk.Label(chip, text="Mainbit", bg="#ffffff", fg=NAVY, font=("Segoe UI", 14, "bold")).pack()
        tit = tk.Frame(top, bg=NAVY)
        tit.pack(side="left", padx=12)
        tk.Label(tit, text="Panel de control · Overty", bg=NAVY, fg=INK, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(tit, text="Solo para ti · activa, desactiva y cambia el ISO", bg=NAVY, fg=INK2,
                 font=("Segoe UI", 9)).pack(anchor="w")
        tk.Label(top, text=f"Sesión de {CFG.FIRMA}", bg=NAVY, fg=INK2, font=("Segoe UI", 9)).pack(side="right")

    # ---- helpers de widgets
    def _boton(self, parent, texto, cmd, tipo="pri", **kw):
        colores = {"pri": (BLUE, "#ffffff"), "ok": (OK, "#06331c"), "soft": (FIELD, INK)}
        bg, fg = colores.get(tipo, colores["pri"])
        return tk.Button(parent, text=texto, command=cmd, bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                         relief="flat", bd=0, font=("Segoe UI", 10, "bold"), cursor="hand2", padx=16, pady=8, **kw)

    def _card(self, parent=None):
        c = tk.Frame(parent or self.cuerpo, bg=CARD, highlightbackground=LINEC, highlightthickness=1)
        c.pack(fill="x", pady=8)
        return c

    def _label(self, parent, texto):
        tk.Label(parent, text=texto, bg=CARD, fg=INK2, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(10, 2))

    def _entry(self, parent, show=None, valor=""):
        e = tk.Entry(parent, show=show, bg=FIELD, fg=INK, insertbackground=INK, relief="flat",
                     font=("Segoe UI", 11), highlightbackground=LINEC, highlightthickness=1)
        e.pack(fill="x", padx=16, pady=(0, 4), ipady=6)
        if valor:
            e.insert(0, valor)
        return e

    def _limpiar(self):
        for w in self.cuerpo.winfo_children():
            w.destroy()
        self.msg = None

    def _poner_msg(self, parent):
        self.msg = tk.Label(parent, text="", bg=CARD, fg=INK2, font=("Segoe UI", 9), anchor="w", justify="left")
        self.msg.pack(fill="x", padx=16, pady=(4, 10))

    def _set_msg(self, t, ok=False):
        if self.msg:
            self.msg.configure(text=t, fg=(OK if ok else (INK2 if t.startswith("…") else RED)))

    # ---- login
    def _login(self):
        self._limpiar()
        existe = hay_token()
        c = self._card()
        tk.Label(c, text=("Entrar" if existe else "Configura tu PIN"), bg=CARD, fg=INK2,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        tk.Label(c, text=("Escribe tu PIN para entrar." if existe else
                          "Primera vez: inventa un PIN (el que recuerdes) y pega tu token de GitHub\n"
                          "con permiso 'repo'. Se guarda cifrado; después solo te pediré el PIN."),
                 bg=CARD, fg=INK2, font=("Segoe UI", 9), justify="left").pack(anchor="w", padx=16)
        self._label(c, "PIN" if existe else "PIN nuevo (invéntalo)")
        self.e_pin = self._entry(c, show="•")
        if not existe:
            self._label(c, "Token de GitHub (ghp_…)")
            self.e_tok = self._entry(c, show="•")
        else:
            self.e_tok = None
        self._poner_msg(c)
        self._boton(c, "Guardar y entrar" if not existe else "Entrar", self._entrar).pack(anchor="e", padx=16, pady=(0, 12))
        if not self.autotest:
            self.e_pin.focus_set()

    def _entrar(self):
        pin = self.e_pin.get()
        tok = self.e_tok.get() if self.e_tok else ""
        if not pin:
            return self._set_msg("Escribe un PIN.")
        self._set_msg("… entrando")
        threading.Thread(target=self._entrar_bg, args=(pin, tok), daemon=True).start()

    def _entrar_bg(self, pin, tok):
        try:
            if tok.strip():
                guardar_token(pin, tok.strip())
                self.token = tok.strip()
            else:
                self.token = leer_token(pin)
            if not self.token:
                return self.root.after(0, lambda: self._set_msg("PIN incorrecto o sin token guardado."))
            ctrl, sha = leer_actual(self.token)
            if ctrl is None:
                ctrl = {"activo": True, "mensaje": "", "iso": {"nombre": "", "url": "", "sha256": ""}}
            self.control, self.sha = ctrl, sha
            self.root.after(0, self._panel)
        except Exception as e:
            self.root.after(0, lambda: self._set_msg("Error: " + str(e)[:140]))

    # ---- panel principal
    def _panel(self):
        self._limpiar()
        c = (self.control or {})
        iso = c.get("iso") or {}

        # estado del servicio
        s = self._card()
        fila = tk.Frame(s, bg=CARD)
        fila.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(fila, text="ESTADO DEL SERVICIO", bg=CARD, fg=INK2, font=("Segoe UI", 9, "bold")).pack(side="left")
        self.var_activo = tk.BooleanVar(value=bool(c.get("activo", True)))
        self.chip_estado = tk.Label(fila, text="", font=("Segoe UI", 9, "bold"), padx=10, pady=2)
        self.chip_estado.pack(side="right")
        self._pinta_chip()
        chk = tk.Checkbutton(s, text="  Permitir crear USBs (si lo apagas, la app de los técnicos deja de funcionar)",
                             variable=self.var_activo, command=self._pinta_chip, bg=CARD, fg=INK,
                             activebackground=CARD, activeforeground=INK, selectcolor=FIELD, font=("Segoe UI", 10),
                             anchor="w")
        chk.pack(fill="x", padx=14, pady=4)
        self._label(s, "Mensaje cuando está desactivado")
        self.txt_msg = tk.Text(s, height=2, bg=FIELD, fg=INK, insertbackground=INK, relief="flat",
                               font=("Segoe UI", 10), highlightbackground=LINEC, highlightthickness=1, wrap="word")
        self.txt_msg.pack(fill="x", padx=16, pady=(0, 6))
        self.txt_msg.insert("1.0", c.get("mensaje", ""))
        self._poner_msg(s)
        self._boton(s, "Guardar estado", self._guardar).pack(anchor="e", padx=16, pady=(0, 12))

        # ISO
        i = self._card()
        tk.Label(i, text="ISO QUE USAN LOS TÉCNICOS", bg=CARD, fg=INK2,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(12, 6))
        caja = tk.Frame(i, bg=FIELD, highlightbackground=LINEC, highlightthickness=1)
        caja.pack(fill="x", padx=16)
        nombre = iso.get("nombre") or "Todavía no has subido ningún ISO"
        sub = ("En uso" + (" · subido " + iso.get("subido", "") if iso.get("subido") else "")) if iso.get("url") \
              else "Los técnicos no podrán crear USB hasta que subas uno."
        tk.Label(caja, text=nombre, bg=FIELD, fg=INK, font=("Segoe UI", 11, "bold"), anchor="w").pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(caja, text=sub, bg=FIELD, fg=INK2, font=("Segoe UI", 9), anchor="w").pack(fill="x", padx=12, pady=(0, 8))

        self.iso_prog_frame = tk.Frame(i, bg=CARD)
        self.iso_prog_frame.pack(fill="x", padx=16, pady=8)
        self.btn_subir = self._boton(self.iso_prog_frame, "⬆  Subir ISO nuevo…", self._subir)
        self.btn_subir.pack(fill="x")
        tk.Label(i, text="Elige el .iso ya corregido. Se sube a tu repositorio, se calcula su huella y se\n"
                         "publica solo. Límite de GitHub: 2 GB (si pesa más, usa un enlace de OneDrive).",
                 bg=CARD, fg=INK2, font=("Segoe UI", 9), justify="left").pack(anchor="w", padx=16, pady=(0, 10))
        self._poner_msg(i)

        # avanzado: enlace externo
        av = self._card()
        tk.Label(av, text="OPCIÓN AVANZADA · usar un ISO alojado en otro lado (OneDrive…)", bg=CARD, fg=INK2,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(12, 4))
        self._label(av, "URL de descarga directa")
        self.e_url = self._entry(av, valor=iso.get("url", "") if iso.get("url", "").startswith("http") else "")
        self.e_url.configure(bg=FIELD)
        self._boton(av, "Usar este enlace", self._usar_url, "soft").pack(anchor="e", padx=16, pady=(4, 12))

    def _pinta_chip(self):
        on = self.var_activo.get()
        self.chip_estado.configure(text=("ACTIVO" if on else "DESACTIVADO"),
                                   bg=("#13402a" if on else "#40201e"), fg=(OK if on else RED))

    def _guardar(self):
        self._set_msg("… guardando")
        datos = {"activo": self.var_activo.get(), "mensaje": self.txt_msg.get("1.0", "end").strip()}
        threading.Thread(target=self._guardar_bg, args=(datos,), daemon=True).start()

    def _guardar_bg(self, datos):
        try:
            c = self.control or {}
            c["activo"] = datos["activo"]
            c["mensaje"] = datos["mensaje"]
            publicar(self.token, c, self.sha)
            _, self.sha = leer_actual(self.token)
            self.control = c
            self.root.after(0, lambda: self._set_msg("✔ Guardado. Los técnicos lo verán al abrir la app.", ok=True))
        except Exception as e:
            self.root.after(0, lambda: self._set_msg("No se pudo guardar: " + str(e)[:140]))

    def _subir(self):
        ruta = filedialog.askopenfilename(title="Elige el ISO de Overty",
                                          filetypes=[("ISO de Overty", "*.iso"), ("Todos", "*.*")])
        if not ruta:
            return
        self.btn_subir.pack_forget()
        self.pbar = ttk.Progressbar(self.iso_prog_frame, maximum=100)
        self.pbar.pack(fill="x")
        self.lbl_sub = tk.Label(self.iso_prog_frame, text="Preparando…", bg=CARD, fg=INK2, font=("Segoe UI", 9))
        self.lbl_sub.pack(anchor="w", pady=(4, 0))
        threading.Thread(target=self._subir_bg, args=(ruta,), daemon=True).start()

    def _prog_sub(self, pct, etapa):
        def _():
            self.pbar.configure(value=pct)
            self.lbl_sub.configure(text=f"{etapa}   ({int(pct)}%)")
        self.root.after(0, _)

    def _subir_bg(self, ruta):
        try:
            if os.path.getsize(ruta) > 2 * 1024**3:
                return self.root.after(0, lambda: self._set_msg(
                    "El ISO pesa más de 2 GB (límite de GitHub). Usa la opción avanzada con un enlace de OneDrive."))
            sha = _sha256(ruta, self._prog_sub)
            self._prog_sub(0, "Conectando con GitHub…")
            rel = _release_iso(self.token)
            for a in rel.get("assets", []):
                if a.get("name") == "overty.iso":
                    _req(GH_API + "/releases/assets/%d" % a["id"], self.token, "DELETE")
            url = subir_asset(self.token, rel["id"], ruta, self._prog_sub)
            c = self.control or {}
            c.setdefault("activo", True)
            c["iso"] = {"nombre": os.path.basename(ruta), "url": url, "sha256": sha,
                        "subido": time.strftime("%Y-%m-%d %H:%M")}
            publicar(self.token, c, self.sha)
            _, self.sha = leer_actual(self.token)
            self.control = c
            self.root.after(0, self._panel)
            self.root.after(50, lambda: self._set_msg("✔ ISO subido y publicado. Los técnicos ya lo bajarán solos.", ok=True))
        except Exception as e:
            self.root.after(0, lambda: self._set_msg("No se pudo subir: " + str(e)[:150]))
            self.root.after(0, self._panel)

    def _usar_url(self):
        url = self.e_url.get().strip()
        if not url:
            return self._set_msg("Pega una URL.")
        self._set_msg("… publicando")
        threading.Thread(target=self._usar_url_bg, args=(url,), daemon=True).start()

    def _usar_url_bg(self, url):
        try:
            c = self.control or {}
            c.setdefault("activo", True)
            c["iso"] = {"nombre": os.path.basename(url.split("?")[0]) or "Overty Disk", "url": url, "sha256": "",
                        "subido": time.strftime("%Y-%m-%d %H:%M")}
            publicar(self.token, c, self.sha)
            _, self.sha = leer_actual(self.token)
            self.control = c
            self.root.after(0, self._panel)
            self.root.after(50, lambda: self._set_msg("✔ ISO (por enlace) publicado.", ok=True))
        except Exception as e:
            self.root.after(0, lambda: self._set_msg("No se pudo publicar: " + str(e)[:140]))

    def _captura(self):
        try:
            from PIL import ImageGrab
            self.root.update_idletasks()
            x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
            w, h = self.root.winfo_width(), self.root.winfo_height()
            ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(os.environ.get("MB_SHOT", "shot_panel.png"))
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
