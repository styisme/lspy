[简体中文](README.md) | [繁體中文](README_zh_TW.md) | **English** | [日本語](README_ja.md) | [한국어](README_ko.md) | [Deutsch](README_de.md) | [Français](README_fr.md) | [Español](README_es.md) | [Русский](README_ru.md) | [Português](README_pt.md)

# lspy

> A command-line implementation of the LocalSend protocol. One file, zero third-party dependencies: LocalSend on your phone, one command on your desktop. Cross-network relay over ntfy.sh included.

[![CI](https://github.com/styisme/lspy/actions/workflows/ci.yml/badge.svg)](https://github.com/styisme/lspy/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.27.1-512BD4)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Made with AI](https://img.shields.io/badge/made%20with-AI-FF6B6B)](docs/AI_DISCLOSURE.md)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-brightgreen)]()

---

## ⚠️ AI Generation Disclosure

> **This project is heavily AI-assisted. Humans own the requirements, review, verification and release.**
>
> See [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md) for scope and known risks. This project follows the [AI Development Guidelines](https://github.com/styisme/ai-development-guidelines) (in-repo copy: [docs/AI-DEVELOPMENT-GUIDELINES.md](docs/AI-DEVELOPMENT-GUIDELINES.md)).

---

## 📦 Version & Origin

Current version: **v1.27.1** (single source of truth is [CHANGELOG.md](CHANGELOG.md), verified and injected by CI).

lspy is an **independent command-line implementation** of the LocalSend protocol, written from scratch. It does not copy the official app (Apache-2.0) sources and only interoperates at the protocol level — see [LICENSE-LocalSend](LICENSE-LocalSend). Sibling GUI implementations: [OldSend](https://github.com/styisme/oldsend) and [WatchSend](https://github.com/styisme/watchsend); they share protocol ideas but no code.

---

## ✨ Core Features

### 🌐 Protocol & Discovery
- **Two protocol generations**: LocalSend `v2` (`prepare-upload`/`upload`/`cancel`) and `v2.1` (`send-request`/`send`); the `v1` prefix works too, so old and new clients both connect.
- **Graceful fallback**: senders try v2.1 first and fall back to `prepare-upload` on 404/405, switching the upload path accordingly.
- **Triple discovery**: multicast `224.0.0.167:53317`, subnet broadcast, and an **HTTP deep scan** (all interfaces, both ports, parallel) for networks where multicast is blocked by firewalls or AP isolation.
- **Direct dial**: `--ip HOST[:PORT]` bypasses discovery; `scan --json` is script-friendly.

### 🛡️ Transfer & Safety
- **Resume**: in-session retries continue from the on-disk offset; retries of completed files are acknowledged without rewriting.
- **Never overwrite**: every landing name goes through `safe_filename` + `unique_path`; conflicts become `(1)` suffixes — no silent skip for same-name/same-size files.
- **Access control**: PIN (returned as `401` + `X-LocalSend-Pin`), fingerprint whitelist/blacklist (prefix matching), blocked extensions (`exe,bat,cmd,vbs,sh` by default) applied per file instead of rejecting the whole session.
- **Zip Slip protection**: absolute paths, drive letters, `..` traversal and symlink entries are refused.
- **TLS**: `lspy cert` generates a self-signed pair; both sides can run over HTTPS.

### 🔁 Cross-network & UI
- **Cross-network relay**: `cross-send` / `cross-recv` over ntfy.sh; the 6-digit PIN is the topic, chunks are 2400 bytes (under the per-message limit), with 3 retries, a SHA-256 + length trailer and per-message de-duplication.
- **Web share page**: the receiver serves one HTML page (device info + recent receipts) that doubles as browser-side transfer: upload files straight into the receive folder, browse and download what was received, and push text into the local clipboard (falls back to a `.txt` file when no clipboard is available). The page and `/web/*` endpoints are ported from watchsend's `WebShareHandler`; with a PIN set, every read and write requires it. The page follows the browser's `Accept-Language` and only falls back to the CLI language when none of the ten matches.
- **History management** (ported from watchsend's History Quick Management): `history --delete N` removes entry N (1 = newest, the CLI equivalent of a long-press delete), `--clear` wipes the list, and `--unzip N` extracts that ZIP in place through the same `safe_unzip` (absolute paths, `..` traversal and symlink entries are refused). ZIP entries are marked 📦 in the list. History is capped by `history_max` (default 300), so the oldest record is dropped instead of growing the file forever.
- **Received .txt lands in the clipboard** (ported from watchsend's `UploadHandler`): a received `.txt` of at most 10 KB has its body copied to the local clipboard, so there is no need to hunt the file down in the download folder. Environments without a clipboard skip it silently, and `config --set clipboard_text=false` turns it off.
- **IPv6 direct address** (ported from watchsend's `[IPv6]:53317` readout): `info` appends `[address]:port` for this machine's IPv6 addresses below the protocol JSON, ready to hand to the peer for cross-network transfers; only global and unique-local unicast addresses are listed, link-local ones are not.
- **Debug keys mode** (ported from watchsend's Debug Keys Mode): `--debug-keys` renders raw i18n keys such as `⟦history_empty⟧` so missing translations stand out; `config --set debug_keys=true` keeps it on across runs, while the flag itself never writes to the config.
- **Interactive menu**: running without a subcommand starts a background receiver and offers scan / send / cross-net / history / settings.
- **File picker without tkinter**: bundled [cfdialog](https://github.com/styisme/cfdialog) 0.3.0 (MIT, one file, stdlib only) takes over when `tkinter` is missing — a terminal browser with numbered entries, `g` for partitions, `h` for hidden files, `a`/`c`/`d` for multi-select; typing `?` at the save-dir setting opens a folder browser. On Android `tkinter` is skipped altogether — mobile Python builds rarely ship Tk — and the picker goes straight to cfdialog.
- **Force the cfdialog picker**: `config --set force_cfdialog=true` (or item 10 in `8. Settings`) sends file selection straight to cfdialog and skips `tkinter`. On machines where `tkinter` imports but never shows a window (missing Tcl data, no DISPLAY, a window swallowed by remote desktop), the automatic order stalls on a dead dialog first — this is the way out.
- **10 UI languages**: zh, zh_TW, en, ja, ko, de, fr, es, ru, pt.

---
- **Receive from any screen**: every input point (menu, settings, file picker) watches the invite queue, so an incoming transfer pops the accept prompt immediately. With `auto_accept` on it skips the prompt and goes straight to the receive detail; press Enter afterwards to return to the screen you came from.
- **Stay after sending**: a finished send no longer flashes away - press Enter to go back to the menu.

## 📱 Quick Start

### 1. Install

```bash
git clone https://github.com/styisme/lspy.git
cd lspy
python lspy.py --help          # run directly
pip install .                  # or install the `lspy` command
```

Python 3.8+, no third-party dependencies. Without `tkinter`, the picker falls back to the bundled cfdialog terminal browser, and only then to typed paths.

No Python at hand? Grab the standalone build from [Releases](https://github.com/styisme/lspy/releases): `lspy-<version>-windows-x64.exe` on Windows, `lspy-<version>-linux-x86_64` on Linux — download and run. The Linux binary is built on Ubuntu 22.04 and needs `glibc >= 2.35`; on older distributions use `pip install lspy`.

### 2. Receive

```bash
lspy serve --web                                     # serve + open status page
lspy serve --auto-accept -d ~/Downloads/lspy --pin 1234
```

Open LocalSend on your phone; it should discover this host. Allow TCP/UDP `53317`.

### 3. Send

```bash
lspy scan
lspy send a.jpg b.pdf --device "Pixel 7"
lspy send a.jpg --ip 192.168.1.20:53317 --pin 1234
```

### 4. Cross-network

```bash
lspy cross-send photo.zip                 # prints a 6-digit PIN
lspy cross-recv 123456 -d ./incoming      # peer enters the PIN
```

---

## 🧰 Commands & Configuration

| Command | Purpose |
| --- | --- |
| `lspy info` | Print this device's LocalSend identity |
| `lspy scan [-t 2] [--json]` | Discover nearby devices |
| `lspy serve [-p 53317] [-d DIR] [--pin PIN] [--auto-accept\|--confirm] [--web] [--no-multicast] [--no-web]` | Receive service |
| `lspy send FILES... (--device NAME\|--ip HOST[:PORT]) [--pin PIN] [--https]` | Send files |
| `lspy cross-send FILES... [--pin PIN]` / `lspy cross-recv PIN [-d DIR]` | Cross-network transfer |
| `lspy history [-n 20] [--delete N] [--clear] [--unzip N]` | List / delete one / clear / extract a ZIP |
| `lspy open FILES...` / `lspy cert` / `lspy stun` | Open, certificates, public-IP probe |
| `lspy config [--show] [--set k=v] [--reset]` | Manage settings |

Runtime data lives in `~/.lspy/` (`config.json`, `history.jsonl`, `lspy.log`, `cert.pem`/`key.pem`). Common keys: `alias`, `port`, `save_dir`, `pin`, `auto_accept`, `filter_ext`, `whitelist`/`blacklist`, `auto_accept_whitelist`, `use_https`, `web_enable`, `organize_by_type`, `history_enable`, `auto_unzip`, `open_after_receive`, `lang`, `ntfy_topic`, `log_level`, `fingerprint`, `debug_keys`, `force_cfdialog`.

Protocol endpoints (`/api/localsend/{v1,v2}/…`): `info`, `register`, `prepare-upload`, `send-request`, `upload`, `send`, `cancel`, plus the web share page at `/` and `/web/info`, `/web/files`, `/web/download`, `/web/upload`, `/web/text`, `/web/clipboard`.

---

## 🛠️ Build & Test

A single-file Python project with no third-party dependencies; packaging uses the standard `pyproject.toml`, executables use PyInstaller:

```bash
pip install .
python -m unittest discover -s tests -v       # 98 cases: unit + end-to-end
python scripts/sync_version.py --check         # version matches CHANGELOG.md
pip install pyinstaller && python scripts/build_binary.py   # standalone executable
```

`build_binary.py` reads the version from `CHANGELOG.md` and writes a platform-named artifact into `dist/`:
`lspy-<version>-windows-x64.exe`, `lspy-<version>-linux-x86_64`, `lspy-<version>-linux-arm64`, `lspy-<version>-macos-arm64`, `lspy-<version>-macos-x64`. Pass `--clean` to wipe `build/` and `dist/` first. `cfdialog.py` and `lg/*.txt` are bundled too (unpacked to `_MEIPASS/lg`, exactly that library's `LIB_DIR/lg`).

### 🤖 Automation

- **CI**: `ci.yml` runs the full suite on Windows and Linux plus a version-consistency check.
- **Release**: pushing a `CHANGELOG.md` change to `main` triggers `release.yml`, which builds a standalone executable on Windows and on Linux, builds the wheel and sdist, then tags and publishes a GitHub Release with all four artifacts.
- **Versioning**: `CHANGELOG.md` is the only source; `scripts/sync_version.py` injects it into `lspy.py` and `pyproject.toml`, and CI verifies only.

---

## 🚧 Risk & Limitations

1. **High AI involvement**: protocol, safety checks and CI scripts are AI-assisted; humans review and verify on real machines. Do not treat this as an audit-grade implementation.
2. **Cross-network channel is public plaintext**: the ntfy topic is the PIN — a leaked PIN is a leaked file. Do not send sensitive data.
3. **Single-file architecture**: `lspy.py` is ~1500 lines. Easy to ship and embed, but weak on modularity, typing and static analysis.
4. **Self-signed TLS**: certificate chains are not validated (same as LocalSend), so it does not stop MITM.
5. **Platform quirks**: Windows Firewall, router AP isolation and macOS local-network permissions can all break discovery.

---

## 📚 Related Docs

- [CHANGELOG.md](CHANGELOG.md)
- [CONTRIBUTING.md](CONTRIBUTING.md) / [CONTRIBUTING_EN.md](CONTRIBUTING_EN.md)
- [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md)
- [docs/DEVELOPMENT_CONSTRAINTS.md](docs/DEVELOPMENT_CONSTRAINTS.md)
- [docs/AI-DEVELOPMENT-GUIDELINES.md](docs/AI-DEVELOPMENT-GUIDELINES.md)
- [LocalSend protocol](https://github.com/localsend/localsend/blob/main/docs/protocol.md)

---

## 📜 License

MIT — see [LICENSE](LICENSE). Protocol compatibility notice: [LICENSE-LocalSend](LICENSE-LocalSend). Independent implementation, no copied official source.

Third-party: `cfdialog.py` and `lg/*.txt` are copied verbatim from [styisme/cfdialog](https://github.com/styisme/cfdialog) 0.3.0 (also MIT); its copyright notice is kept in [LICENSE-cfdialog](LICENSE-cfdialog).
