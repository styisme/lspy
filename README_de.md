[简体中文](README.md) | [繁體中文](README_zh_TW.md) | [English](README_EN.md) | [日本語](README_ja.md) | [한국어](README_ko.md) | [**Deutsch**](README_de.md) | [Français](README_fr.md) | [Español](README_es.md) | [Русский](README_ru.md) | [Português](README_pt.md)

# lspy

> Eine Kommandozeilen-Implementierung des LocalSend-Protokolls. Eine Datei, keine Fremdabhängigkeiten: LocalSend auf dem Handy, eine Zeile auf dem Rechner. Inklusive Relay über ntfy.sh für geräteübergreifende Netze.

[![CI](https://github.com/styisme/lspy/actions/workflows/ci.yml/badge.svg)](https://github.com/styisme/lspy/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.28.3-512BD4)]()
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
- **Zugriffskontrolle**: PIN (`401` wenn nötig oder falsch, `429` nach 3 Fehlversuchen einer IP — wie bei LocalSend), Fingerprint-White-/Blacklist, Filter gefährlicher Endungen (pro Datei übersprungen).
- **Zip-Slip-Schutz**: absolute Pfade, Laufwerksbuchstaben, `..`-Traversal und Symlinks werden abgelehnt.
- **TLS**: `lspy cert` erzeugt ein selbstsigniertes Paar; beide Seiten können HTTPS nutzen.
- **Cross-Network**: über ntfy.sh, 2400-Byte-Chunks, 3 Versuche, SHA-256-Prüfsumme am Ende.
- **Web-Freigabeseite** (Hochladen / Herunterladen / Text, aus watchsend portiert; die Seite folgt `Accept-Language` der Browsersprache), **10 UI-Sprachen**.
- **sha256-Prüfsummen pro Datei** (wie `createChecksums` / `verifyChecksums`): der Sender legt den Hash jeder Datei in `files[].sha256` ab, ein Empfänger mit `verify_checksum` prüft ihn wie offiziell — bei Abweichung `422 Checksum mismatch`, die gespeicherte Datei wird verworfen. Bei reinem HTTP wird zusätzlich gewarnt, dass der Verkehr unverschlüsselt ist.
- **Netzwerkdiagnose** (aus der offiziellen `troubleshoot_page`): `lspy troubleshoot` oder Menüpunkt `9` prüft, ob der Port belegt werden kann, listet lokale Adressen (IPv4 zuerst, `fe80`-Link-Local ausgeblendet), gibt die Windows-Firewall-Regel `netsh advfirewall ... localport=` aus und weist darauf hin, dass der HTTP-Scan bei AP-Isolation weiter funktioniert.
- **Zufälliger Alias und konfigurierbares Geräteprofil** (wie `alias_generator` und `deviceType` / `deviceModel`): der erste Start erzeugt einen Alias aus Adjektiv und Frucht und speichert ihn, sodass der Hostname nicht mehr ins LAN gesendet wird; `device_type` / `device_model` bestimmen Typ und Modell in `info`, auch über die Einstellungen 11 und 12.
- **Verlauf & Debug** (ebenfalls aus watchsend): `history --delete N` / `--clear` / `--unzip N` (ZIP mit 📦, Zip-Slip-Schutz), `--debug-keys` zeigt rohe i18n-Schlüssel.
- **Kleine Empfangshilfen**: empfangene `.txt` bis 10 KB landen automatisch in der Zwischenablage (über `clipboard_text` abschaltbar), der Verlauf wird per `history_max` (Standard 300) gekürzt, und `info` zeigt zusätzlich `[IPv6]:Port`.
- **Dateiauswahl ohne tkinter**: mitgeliefertes [cfdialog](https://github.com/styisme/cfdialog) 0.3.0 (MIT, eine Datei, nur Standardbibliothek) ersetzt den tkinter-Dialog durch einen Terminal-Browser (Nummern, `g` Partitionen, `h` versteckt, `a`/`c`/`d` Mehrfachauswahl); `?` beim Speicherordner öffnet den Ordner-Browser. Mit `config --set force_cfdialog=true` lässt sich der Terminal-Browser erzwingen (tkinter wird übersprungen). Unter Android wird tkinter übersprungen (dort fehlt Tk meist), der Browser startet sofort.

---
- **Empfang von jedem Bildschirm aus**: jede Eingabestelle (Menue, Einstellungen, Dateiauswahl) ueberwacht die Warteschlange eingehender Uebertragungen und zeigt die Annahmefrage sofort an. Mit aktivem `auto_accept` geht es direkt zur Empfangsdetailansicht; danach mit Enter zurueck zum vorherigen Bildschirm.
- **Bleiben nach dem Senden**: nach dem Senden wird nicht mehr sofort beendet - Enter fuehrt zurueck ins Menue.

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
