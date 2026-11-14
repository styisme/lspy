[简体中文](README.md) | [繁體中文](README_zh_TW.md) | [English](README_EN.md) | [日本語](README_ja.md) | [한국어](README_ko.md) | [Deutsch](README_de.md) | [Français](README_fr.md) | [**Español**](README_es.md) | [Русский](README_ru.md) | [Português](README_pt.md)

# lspy

> Una implementación de línea de comandos del protocolo LocalSend. Un solo archivo, sin dependencias de terceros: LocalSend en el móvil, una orden en el ordenador. Incluye retransmisión entre redes mediante ntfy.sh.

[![CI](https://github.com/styisme/lspy/actions/workflows/ci.yml/badge.svg)](https://github.com/styisme/lspy/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.19.1-512BD4)]()
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
- **Control de acceso**: PIN (`401` + `X-LocalSend-Pin`), listas blanca/negra de huellas, filtro de extensiones peligrosas (se omiten por archivo).
- **Protección Zip Slip**: se rechazan rutas absolutas, letras de unidad, recorrido `..` y enlaces simbólicos.
- **TLS**: `lspy cert` genera un par autofirmado; ambos lados pueden usar HTTPS.
- **Entre redes**: vía ntfy.sh, bloques de 2400 bytes, 3 reintentos, SHA-256 final.
- **Página de estado web**, **10 idiomas de interfaz**.

---

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
```

---

## 🚧 Riesgos y limitaciones

1. **Alta participación de IA**: protocolo, comprobaciones de seguridad y scripts de CI están asistidos por IA; revisión humana y pruebas reales son obligatorias. No es una implementación auditada.
2. **Canal entre redes en claro**: el tema de ntfy es el PIN — PIN filtrado, archivo filtrado. No envíe datos sensibles.
3. **Arquitectura de un solo archivo**: `lspy.py` ronda las 1500 líneas; fácil de distribuir, débil en modularidad y análisis estático.
4. **TLS autofirmado**: no se validan cadenas de certificados, por lo que no protege contra MITM.

---

## 📜 Licencia

MIT ([LICENSE](LICENSE)). Aviso de compatibilidad: [LICENSE-LocalSend](LICENSE-LocalSend).
