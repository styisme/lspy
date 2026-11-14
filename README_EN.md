[简体中文](README.md) | [繁體中文](README_zh_TW.md) | **English** | [日本語](README_ja.md) | [한국어](README_ko.md) | [Deutsch](README_de.md) | [Français](README_fr.md) | [Español](README_es.md) | [Русский](README_ru.md) | [Português](README_pt.md)

# lspy

> A command-line implementation of the LocalSend protocol. One file, zero third-party dependencies: LocalSend on your phone, one command on your desktop. Cross-network relay over ntfy.sh included.

[![CI](https://github.com/styisme/lspy/actions/workflows/ci.yml/badge.svg)](https://github.com/styisme/lspy/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.19.2-512BD4)]()
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

Current version: **v1.19.2** (single source of truth is [CHANGELOG.md](CHANGELOG.md), verified and injected by CI).

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
- **Web status page**: the receiver serves a small HTML page (device info + recent receipts); `--web` opens it.
- **Interactive menu**: running without a subcommand starts a background receiver and offers scan / send / cross-net / history / settings.
- **10 UI languages**: zh, zh_TW, en, ja, ko, de, fr, es, ru, pt.

---

## 📱 Quick Start

### 1. Install

```bash
git clone https://github.com/styisme/lspy.git
cd lspy
python lspy.py --help          # run directly
pip install .                  # or install the `lspy` command
```

Python 3.8+, no third-party dependencies. Without `tkinter`, the file picker falls back to typed paths.

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
| `lspy history [-n 20]` / `lspy open FILES...` / `lspy cert` / `lspy stun` | History, open, certificates, public-IP probe |
| `lspy config [--show] [--set k=v] [--reset]` | Manage settings |

Runtime data lives in `~/.lspy/` (`config.json`, `history.jsonl`, `lspy.log`, `cert.pem`/`key.pem`). Common keys: `alias`, `port`, `save_dir`, `pin`, `auto_accept`, `filter_ext`, `whitelist`/`blacklist`, `auto_accept_whitelist`, `use_https`, `web_enable`, `organize_by_type`, `history_enable`, `auto_unzip`, `open_after_receive`, `lang`, `ntfy_topic`, `log_level`, `fingerprint`.

Protocol endpoints (`/api/localsend/{v1,v2}/…`): `info`, `register`, `prepare-upload`, `send-request`, `upload`, `send`, `cancel`, plus the web status page at `/`.

---

## 🛠️ Build & Test

A single-file Python project; packaging uses the standard `pyproject.toml`:

```bash
pip install .
python -m unittest discover -s tests -v
python scripts/sync_version.py --check
```

### 🤖 Automation

- **CI**: `ci.yml` runs the full suite on Windows and Linux plus a version-consistency check.
- **Release**: pushing a `CHANGELOG.md` change to `main` triggers `release.yml` to build the wheel, tag, and publish a GitHub Release.
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
