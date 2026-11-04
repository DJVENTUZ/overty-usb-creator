# -*- coding: utf-8 -*-
"""
Panel de control de Overty  ·  SOLO para Gabriel HernArro
Desde aquí: activas o desactivas la herramienta de los técnicos, y SUBES el ISO
que deben usar (se guarda en tu repositorio y se publica solo). Los técnicos nunca
eligen nada: solo dan clic en "Crear".

Tu token de GitHub se guarda cifrado en este equipo con un PIN que solo tú sabes.
"""
import os, sys, json, base64, time, threading, hashlib, http.client
import urllib.request, urllib.error

import mb_config as CFG

APPDATA = os.environ.get("APPDATA") or os.path.expanduser("~")
CFG_DIR = os.path.join(APPDATA, "OvertyPanel")
CFG_BIN = os.path.join(CFG_DIR, "cfg.bin")
GH_API = f"https://api.github.com/repos/{CFG.GH_OWNER}/{CFG.GH_REPO}"


def dir_web():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for d in (os.path.join(base, "web"), os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")):
        if os.path.isdir(d):
            return d
    return os.path.dirname(os.path.abspath(__file__))


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
    """control.json actual → (dict, sha_del_archivo)."""
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
    """Asegura que exista la 'release' donde vive el ISO. Devuelve su dict."""
    try:
        return _req(GH_API + "/releases/tags/iso", token)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return _req(GH_API + "/releases", token, "POST",
                        {"tag_name": "iso", "name": "ISO de Overty (vigente)",
                         "body": "ISO que descargan los técnicos. Lo administra Gabriel HernArro desde el Panel."})
        raise


def subir_asset(token, release_id, ruta, progreso):
    """Sube el ISO como archivo de la release, con porcentaje. Devuelve la URL de descarga."""
    size = os.path.getsize(ruta)
    conn = http.client.HTTPSConnection("uploads.github.com", timeout=1200)
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


# ------------------------------------------------------------------ API para la interfaz
class API:
    def __init__(self):
        self.token = None
        self.ventana = None
        self.estado = {"firma": CFG.FIRMA, "version": CFG.VERSION, "repo": f"{CFG.GH_OWNER}/{CFG.GH_REPO}",
                       "hay_token": hay_token(), "entrado": False, "control": None, "sha": None,
                       "msg": "", "subiendo": False, "pct": 0, "etapa": ""}

    def snapshot(self):
        return self.estado

    def _prog(self, pct, etapa):
        self.estado["pct"] = round(pct, 1)
        self.estado["etapa"] = etapa

    def entrar(self, pin, token_nuevo=""):
        try:
            if token_nuevo.strip():
                guardar_token(pin, token_nuevo.strip())
                self.token = token_nuevo.strip()
            else:
                self.token = leer_token(pin)
            if not self.token:
                self.estado["msg"] = "PIN incorrecto o sin token guardado."
                return False
            ctrl, sha = leer_actual(self.token)
            if ctrl is None:
                ctrl = {"activo": True, "mensaje": "", "iso": {"nombre": "", "url": "", "sha256": ""}}
            self.estado.update(entrado=True, control=ctrl, sha=sha, hay_token=True, msg="")
            return True
        except Exception as e:
            self.estado["msg"] = "Error: " + str(e)[:160]
            return False

    def guardar_estado(self, control):
        """Guarda activo + mensaje (sin tocar el ISO)."""
        try:
            c = self.estado.get("control") or {}
            c["activo"] = bool(control.get("activo"))
            c["mensaje"] = control.get("mensaje", "")
            publicar(self.token, c, self.estado.get("sha"))
            _, self.estado["sha"] = leer_actual(self.token)
            self.estado["control"] = c
            self.estado["msg"] = "✔ Guardado. Los técnicos lo verán al abrir la app."
            return True
        except Exception as e:
            self.estado["msg"] = "No se pudo guardar: " + str(e)[:160]
            return False

    def elegir_y_subir_iso(self):
        """Abre el explorador, el técnico elige el .iso y se sube solo."""
        if self.estado["subiendo"]:
            return ""
        import webview
        try:
            res = self.ventana.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False,
                                                   file_types=("ISO de Overty (*.iso)", "Todos los archivos (*.*)"))
        except Exception:
            res = None
        if not res:
            return ""
        ruta = res[0] if isinstance(res, (list, tuple)) else res
        threading.Thread(target=self._subir_iso, args=(ruta,), daemon=True).start()
        return ruta

    def _subir_iso(self, ruta):
        try:
            self.estado.update(subiendo=True, msg="", pct=0, etapa="Preparando…")
            size = os.path.getsize(ruta)
            if size > 2 * 1024**3:
                self.estado["msg"] = ("El ISO pesa más de 2 GB (límite de GitHub). Súbelo al almacén de la empresa "
                                      "y pega su enlace directo en «Opción avanzada».")
                return
            sha = _sha256(ruta, self._prog)
            self._prog(0, "Conectando con GitHub…")
            rel = _release_iso(self.token)
            for a in rel.get("assets", []):
                if a.get("name") == "overty.iso":
                    _req(GH_API + "/releases/assets/%d" % a["id"], self.token, "DELETE")
            url = subir_asset(self.token, rel["id"], ruta, self._prog)
            c = self.estado.get("control") or {}
            c.setdefault("activo", True)
            c["iso"] = {"nombre": os.path.basename(ruta), "url": url, "sha256": sha, "subido": time.strftime("%Y-%m-%d %H:%M")}
            publicar(self.token, c, self.estado.get("sha"))
            _, self.estado["sha"] = leer_actual(self.token)
            self.estado["control"] = c
            self.estado["msg"] = "✔ ISO subido y publicado. Los técnicos lo bajarán solos al crear la USB."
        except Exception as e:
            self.estado["msg"] = "No se pudo subir el ISO: " + str(e)[:180]
        finally:
            self.estado["subiendo"] = False

    def usar_url(self, nombre, url, sha):
        """Opción avanzada: en vez de subir, apuntar a un ISO ya alojado (OneDrive, etc.)."""
        try:
            c = self.estado.get("control") or {}
            c.setdefault("activo", True)
            c["iso"] = {"nombre": nombre or "Overty Disk", "url": url.strip(), "sha256": sha.strip(),
                        "subido": time.strftime("%Y-%m-%d %H:%M")}
            publicar(self.token, c, self.estado.get("sha"))
            _, self.estado["sha"] = leer_actual(self.token)
            self.estado["control"] = c
            self.estado["msg"] = "✔ ISO (por enlace) publicado."
            return True
        except Exception as e:
            self.estado["msg"] = "No se pudo publicar: " + str(e)[:160]
            return False


def _datos_webview():
    base = os.environ.get("LOCALAPPDATA") or APPDATA
    d = os.path.join(base, "OvertyPanel", "webview")
    os.makedirs(d, exist_ok=True)
    return d


def main():
    import webview
    api = API()
    api.ventana = webview.create_window(f"Panel de control · Overty  ·  {CFG.FIRMA}",
                                        url=os.path.join(dir_web(), "panel.html"),
                                        js_api=api, width=760, height=760, min_size=(680, 640),
                                        background_color="#12263d")
    webview.start(gui="edgechromium", private_mode=False, storage_path=_datos_webview())


if __name__ == "__main__":
    main()
