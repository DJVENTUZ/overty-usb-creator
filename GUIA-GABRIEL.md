# Guía de arranque — Creador de USB de Overty

Hecho por **Gabriel HernArro**. Proyecto **separado** del toolkit (mainbit-asistente).

## Qué es cada cosa
- **Creador de USB** (`MainbitCreadorUSB.exe`) → lo usan los técnicos. Baja el ISO que tú marques y graba la USB. Si tú lo desactivas, deja de funcionar.
- **Panel de control** (`PanelControlOverty.exe`) → solo tú. Activa/desactiva la herramienta y cambia el ISO.
- **`control.json`** → el “interruptor” remoto. Vive en este repo; el Creador lo lee al abrir.

## Puesta en marcha (una vez)

### 1. Crea el repositorio en GitHub
- Nuevo repo llamado **`overty-usb-creator`** en tu cuenta **DJVENTUZ**.
- Puede ser **público** (el código y `control.json` no tienen secretos). El ISO NO se sube aquí.
- Sube todos estos archivos (puedes arrastrarlos en la web de GitHub, o con `git push`).

### 2. Deja que GitHub compile los .exe
- Al subir, se ejecuta solo el flujo **“Compilar Creador y Panel (Overty)”**.
- Cuando termine, en **Releases → latest** tendrás `MainbitCreadorUSB.zip` y `PanelControlOverty.zip`.

### 3. Crea tu token de GitHub (para el Panel)
- GitHub → Settings → Developer settings → **Personal access tokens (classic)** → Generate.
- Permiso: **repo**. Cópialo (empieza con `ghp_`).

### 4. Abre el Panel y sube el primer ISO
- Descomprime `PanelControlOverty.zip`, abre `PanelControlOverty.exe`.
- Inventa un **PIN** y pega tu **token** (se guarda cifrado en tu equipo con ese PIN).
- Pulsa **“Subir ISO nuevo…”**, elige el `.iso` ya corregido (el de `reparar_overty.sh`).
  El Panel lo sube a tu repositorio, calcula su huella (SHA-256) y lo publica solo.
- Listo. Los técnicos ya lo bajarán al crear la USB.

> **Importante sobre dónde queda el ISO.** “Subir ISO” lo guarda en los *Releases* de este repositorio.
> - Si el repo es **público**, el ISO queda **descargable por cualquiera que tenga el enlace**. Cómodo para los técnicos (no necesitan clave), pero confirma con Mainbit que está bien publicar Overty así.
> - Si NO quieres que sea público, deja el ISO en el **OneDrive/SharePoint de la empresa** y usa **“Opción avanzada → Usar este enlace”** con su URL de descarga directa. Ahí el repo puede quedar público pero el ISO no.
> - Límite de GitHub: 2 GB por archivo. Si el ISO pesa más, usa la opción avanzada (OneDrive).

### 5. Reparte el Creador
- Pasa `MainbitCreadorUSB.zip` a los técnicos (por el OneDrive de la empresa).
- Ellos solo: conectan la USB, eligen la memoria y dan **Crear**. No ven ni eligen ISO.

## Día a día
- **Cambió el proveedor de borrado / nuevo ISO:** corrige el ISO con `reparar_overty.sh` y en el Panel pulsa **“Subir ISO nuevo…”**. Los técnicos no hacen nada: la próxima vez que abran el Creador baja el nuevo.
- **Desactivar todo (p. ej. si te vas):** en el Panel apaga “Permitir crear USBs” → **Guardar estado**. El Creador mostrará tu mensaje y no funcionará.

## Tu firma
Aparece en: el nombre de ventana, la pantalla principal, el pie, el archivo `CREADA-POR.txt`
de cada USB, y en las **propiedades del .exe** (autor y copyright Gabriel HernArro).

## Nota honesta sobre “que no puedan ver qué tiene”
El `.exe` se puede desensamblar; ninguna protección lo impide del todo, solo lo complica.
Lo que de verdad prueba que es tuyo es tu historial de commits en este repo (con fecha) y tu
firma en todo. El interruptor remoto es tu control de licencia, y conviene usarlo de forma
abierta, como lo que es: tu herramienta, bajo tu control.
