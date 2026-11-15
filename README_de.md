[简体中文](README.md) | [繁體中文](README_zh_TW.md) | [English](README_EN.md) | [日本語](README_ja.md) | [한국어](README_ko.md) | [**Deutsch**](README_de.md) | [Français](README_fr.md) | [Español](README_es.md) | [Русский](README_ru.md) | [Português](README_pt.md)

# lspy

> Eine Kommandozeilen-Implementierung des LocalSend-Protokolls. Eine Datei, keine Fremdabhängigkeiten: LocalSend auf dem Handy, eine Zeile auf dem Rechner. Inklusive Relay über ntfy.sh für geräteübergreifende Netze.

[![CI](https://github.com/styisme/lspy/actions/workflows/ci.yml/badge.svg)](https://github.com/styisme/lspy/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.23.0-512BD4)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Made with AI](https://img.shields.io/badge/made%20with-AI-FF6B6B)](docs/AI_DISCLOSURE.md)

---

## ⚠️ Offenlegung der KI-Generierung

Dieses Projekt wurde stark mit KI-Unterstützung entwickelt. Anforderungen, Review, Verifikation und Release liegen beim Menschen. Details in [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md); das Projekt folgt den [AI Development Guidelines](https://github.com/styisme/ai-development-guidelines).

---

## ✨ Hauptfunktionen

- **Zwei Protokollgenerationen**: LocalSend `v2` (`prepare-upload`/`upload`/`cancel`) und `v2.1` (`send-request`/`send`); `v1`-Präfix ebenfalls. Automatischer Fallback bei 404/405.
- **Dreifache Erkennung**: Multicast `224.0.0.167:53317`, Subnet-Broadcast und **HTTP-Tiefenscan** (alle Interfaces, beide Ports parallel).
- **Fortsetzen ohne Überschreiben**: Innerhalb einer Sitzung wird ab dem Plattenoffset weitergeschrieben; Namen laufen über `safe_filename` + `unique_path`, Konflikte werden zu `(1)`.
- **Zugriffskontrolle**: PIN (`401` + `X-LocalSend-Pin`), Fingerprint-White-/Blacklist, Filter gefährlicher Endungen (pro Datei übersprungen).
- **Zip-Slip-Schutz**: absolute Pfade, Laufwerksbuchstaben, `..`-Traversal und Symlinks werden abgelehnt.
- **TLS**: `lspy cert` erzeugt ein selbstsigniertes Paar; beide Seiten können HTTPS nutzen.
- **Cross-Network**: über ntfy.sh, 2400-Byte-Chunks, 3 Versuche, SHA-256-Prüfsumme am Ende.
- **Web-Freigabeseite** (Hochladen / Herunterladen / Text, aus watchsend portiert; die Seite folgt `Accept-Language` der Browsersprache), **10 UI-Sprachen**.
- **Verlauf & Debug** (ebenfalls aus watchsend): `history --delete N` / `--clear` / `--unzip N` (ZIP mit 📦, Zip-Slip-Schutz), `--debug-keys` zeigt rohe i18n-Schlüssel.

---

## 📱 Schnellstart

```bash
git clone https://github.com/styisme/lspy.git
cd lspy
python lspy.py --help          # ohne Installation
pip install .                  # als `lspy` installieren

lspy serve --web
lspy scan
lspy send a.jpg --ip 192.168.1.20:53317 --pin 1234
lspy cross-send photo.zip
```

Python 3.8+, keine Fremdabhängigkeiten. TCP/UDP `53317` freigeben.

---

## 🛠️ Bauen & Testen

```bash
pip install .
python -m unittest discover -s tests -v
python scripts/sync_version.py --check
pip install pyinstaller && python scripts/build_binary.py
```

Ohne Python: die Einzeldatei aus den [Releases](https://github.com/styisme/lspy/releases) — Windows `lspy-<Version>-windows-x64.exe`, Linux `lspy-<Version>-linux-x86_64`.

Ein `CHANGELOG.md`-Push auf `main` baut die Binaries unter Windows und Linux und veröffentlicht zusammen mit wheel und sdist automatisch Tag und Release.


---

## 🚧 Risiken & Grenzen

1. **Hoher KI-Anteil**: Protokoll, Sicherheitsprüfungen und CI-Skripte sind KI-unterstützt; Review und echte Geräte sind Pflicht. Keine auditierte Implementierung.
2. **Cross-Network im Klartext**: Das ntfy-Topic ist die PIN — geleakte PIN, geleakte Datei. Keine sensiblen Daten senden.
3. **Ein-Datei-Architektur**: `lspy.py` rund 1500 Zeilen, leicht zu verteilen, aber schwach in Modularität und statischer Analyse.
4. **Selbstsigniertes TLS**: Zertifikatsketten werden nicht geprüft, kein Schutz gegen MITM.

---

## 📜 Lizenz

MIT ([LICENSE](LICENSE)). Hinweis zur Protokollkompatibilität: [LICENSE-LocalSend](LICENSE-LocalSend).
