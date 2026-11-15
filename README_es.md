[简体中文](README.md) | [繁體中文](README_zh_TW.md) | [English](README_EN.md) | [日本語](README_ja.md) | [한국어](README_ko.md) | [Deutsch](README_de.md) | [Français](README_fr.md) | [**Español**](README_es.md) | [Русский](README_ru.md) | [Português](README_pt.md)

# lspy

> Una implementación de línea de comandos del protocolo LocalSend. Un solo archivo, sin dependencias de terceros: LocalSend en el móvil, una orden en el ordenador. Incluye retransmisión entre redes mediante ntfy.sh.

[![CI](https://github.com/styisme/lspy/actions/workflows/ci.yml/badge.svg)](https://github.com/styisme/lspy/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.28.2-512BD4)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Made with AI](https://img.shields.io/badge/made%20with-AI-FF6B6B)](docs/AI_DISCLOSURE.md)

---

## ⚠️ Divulgación de generación por IA

Este proyecto se desarrolló en gran medida con asistencia de modelos de lenguaje. Los requisitos, la revisión, la verificación y la publicación son responsabilidad humana. Detalles en [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md); el proyecto sigue las [AI Development Guidelines](https://github.com/styisme/ai-development-guidelines).

---

## ✨ Funciones principales

- **Dos generaciones de protocolo**: LocalSend `v2` (`prepare-upload`/`upload`/`cancel`) y `v2.1` (`send-request`/`send`); el prefijo `v1` también funciona. Reversión automática ante 404/405.
- **Detección triple**: multicast `224.0.0.167:53317`, difusión de subred y **escaneo HTTP profundo** (todas las interfaces, dos puertos en paralelo).
- **Reanudación sin sobrescribir**: se continúa desde el desplazamiento en disco; los nombres pasan por `safe_filename` + `unique_path` y los conflictos se convierten en `(1)`.
- **Control de acceso**: PIN (`401` requerido/erróneo, `429` tras 3 fallos desde una IP — igual que LocalSend), listas blanca/negra de huellas, filtro de extensiones peligrosas (se omiten por archivo).
- **Protección Zip Slip**: se rechazan rutas absolutas, letras de unidad, recorrido `..` y enlaces simbólicos.
- **TLS**: `lspy cert` genera un par autofirmado; ambos lados pueden usar HTTPS.
- **Entre redes**: vía ntfy.sh, bloques de 2400 bytes, 3 reintentos, SHA-256 final.
- **Página web de compartir** (subir / descargar / texto, portada desde watchsend; la página sigue el `Accept-Language` del navegador), **10 idiomas de interfaz**.
- **sha256 por archivo** (igual que `createChecksums` / `verifyChecksums`): el emisor pone el hash de cada archivo en `files[].sha256` y el receptor con `verify_checksum` lo comprueba como el oficial: si no coincide devuelve `422 Checksum mismatch` y el archivo guardado se descarta. En http simple avisa además de que el tráfico no va cifrado.
- **Diagnóstico de red** (portado de `troubleshoot_page`): `lspy troubleshoot` o la opción `9` del menú comprueba si el puerto se puede escuchar, lista las direcciones locales (IPv4 primero, `fe80` oculto), imprime la regla de firewall de Windows `netsh advfirewall ... localport=` y recuerda que el escaneo HTTP sigue funcionando cuando el multicast está bloqueado por aislamiento AP.
- **Alias aleatorio y perfil de dispositivo configurable** (como `alias_generator` y `deviceType` / `deviceModel`): el primer arranque genera un alias «adjetivo + fruta» y lo guarda, así que el nombre del host deja de difundirse en la LAN; `device_type` / `device_model` fijan el tipo y modelo anunciados en `info`, también desde las opciones 11 y 12 de ajustes.
- **Historial y depuración** (también de watchsend): `history --delete N` / `--clear` / `--unzip N` (ZIP marcado 📦, protección Zip Slip), `--debug-keys` muestra las claves i18n sin traducir.
- **Detalles de recepción**: los `.txt` recibidos de hasta 10 KB van directos al portapapeles (se desactiva con `clipboard_text`), el historial se recorta con `history_max` (300 por defecto) e `info` muestra además `[IPv6]:puerto`.
- **Selector de archivos sin tkinter**: [cfdialog](https://github.com/styisme/cfdialog) 0.3.0 incluido (MIT, un solo archivo) sustituye el diálogo de tkinter por un navegador de terminal (números, `g` particiones, `h` ocultos, `a`/`c`/`d` selección múltiple); `?` en la carpeta de recepción abre el explorador de carpetas. `config --set force_cfdialog=true` fuerza el navegador de terminal y omite tkinter. En Android se omite tkinter (allí casi nunca incluye Tk) y el navegador arranca directamente.

---
- **Recepcion desde cualquier pantalla**: cada punto de entrada (menu, ajustes, seleccion de archivos) vigila la cola de transferencias entrantes y muestra la solicitud de aceptacion al instante. Con `auto_accept` activado se va directo al detalle de recepcion; despues, Enter vuelve a la pantalla anterior.
- **Permanecer tras el envio**: un envio terminado ya no desaparece - Enter vuelve al menu.

## 📱 Inicio rápido

```bash
git clone https://github.com/styisme/lspy.git
cd lspy
python lspy.py --help          # sin instalar
pip install .                  # instala el comando `lspy`

lspy serve --web
lspy scan
lspy send a.jpg --ip 192.168.1.20:53317 --pin 1234
lspy cross-send photo.zip
```

Python 3.8+, sin dependencias. Permita TCP/UDP `53317`.

---

## 🛠️ Compilación y pruebas

```bash
pip install .
python -m unittest discover -s tests -v
python scripts/sync_version.py --check
pip install pyinstaller && python scripts/build_binary.py
```

Sin Python: usa el binario autónomo de [Releases](https://github.com/styisme/lspy/releases) — Windows `lspy-<versión>-windows-x64.exe`, Linux `lspy-<versión>-linux-x86_64`.

Un push de `CHANGELOG.md` a `main` compila los binarios en Windows y Linux y publica automáticamente el tag y el Release junto al wheel y el sdist.


---

## 🚧 Riesgos y limitaciones

1. **Alta participación de IA**: protocolo, comprobaciones de seguridad y scripts de CI están asistidos por IA; revisión humana y pruebas reales son obligatorias. No es una implementación auditada.
2. **Canal entre redes en claro**: el tema de ntfy es el PIN — PIN filtrado, archivo filtrado. No envíe datos sensibles.
3. **Arquitectura de un solo archivo**: `lspy.py` ronda las 1500 líneas; fácil de distribuir, débil en modularidad y análisis estático.
4. **TLS autofirmado**: no se validan cadenas de certificados, por lo que no protege contra MITM.

---

## 📜 Licencia

MIT ([LICENSE](LICENSE)). Aviso de compatibilidad: [LICENSE-LocalSend](LICENSE-LocalSend).
