[简体中文](README.md) | [**繁體中文**](README_zh_TW.md) | [English](README_EN.md) | [日本語](README_ja.md) | [한국어](README_ko.md) | [Deutsch](README_de.md) | [Français](README_fr.md) | [Español](README_es.md) | [Русский](README_ru.md) | [Português](README_pt.md)

# lspy

> LocalSend 協定的命令列實作。單檔、零第三方依賴：手機跑 LocalSend，電腦一行指令收發檔案；另可透過 ntfy.sh 做跨網中繼。

[![CI](https://github.com/styisme/lspy/actions/workflows/ci.yml/badge.svg)](https://github.com/styisme/lspy/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.22.0-512BD4)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Made with AI](https://img.shields.io/badge/made%20with-AI-FF6B6B)](docs/AI_DISCLOSURE.md)

---

## ⚠️ AI 生成聲明

本專案開發過程大量使用大型語言模型輔助生成，人類負責需求、審閱、驗證與發佈。詳見 [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md)，並遵循 [AI 開發規範](https://github.com/styisme/ai-development-guidelines)。

---

## 📦 版本與來源

目前版本：**v1.22.0**（版本號唯一來源為 [CHANGELOG.md](CHANGELOG.md)，由 CI 驗證並注入）。

本專案為 LocalSend 協定的獨立命令列實作，自零撰寫，未複製官方 App 原始碼，僅於協定層互通。

---

## ✨ 核心特性

- **雙版本協定**：支援 `v2`（`prepare-upload`/`upload`/`cancel`）與 `v2.1`（`send-request`/`send`），`v1` 前綴亦相容；發送端優先 v2.1，遇 404/405 自動回退。
- **三重發現**：組播 `224.0.0.167:53317`、網段廣播、**HTTP 深度掃描**（多網卡、雙埠並行），克服防火牆與 AP 隔離。
- **斷點續傳與防覆寫**：會話內自磁碟偏移續傳；落地檔名經 `safe_filename` + `unique_path`，衝突自動加 `(1)`。
- **存取控制**：PIN（`401` + `X-LocalSend-Pin`）、指紋黑白名單、危險副檔名過濾（逐檔跳過而非整個會話拒絕）。
- **解壓防護**：拒絕絕對路徑、磁碟機代號、`..` 穿越與符號連結（Zip Slip）。
- **TLS**：`lspy cert` 產生自簽憑證，雙端皆可走 HTTPS。
- **跨網中繼**：`cross-send` / `cross-recv` 走 ntfy.sh，分塊 2400 位元組、3 次重試、尾包 SHA-256 與長度校驗。
- **Web 分享頁**：接收端內建 HTML 頁面（裝置資訊 + 最近接收紀錄），並可當「網頁版傳輸」用：瀏覽器直接上傳檔案到接收目錄、瀏覽並下載已接收檔案、把文字寫進本機剪貼簿（不可用時存成 txt）。頁面與 `/web/*` 端點移植自 watchsend 的 `WebShareHandler`；設了 PIN 時頁面的讀寫一律需要 PIN。
- **10 種介面語言**。

---

## 📱 快速開始

```bash
git clone https://github.com/styisme/lspy.git
cd lspy
python lspy.py --help          # 免安裝直接用
pip install .                  # 或安裝為 lspy 指令

lspy serve --web               # 接收（並開啟狀態頁）
lspy scan                      # 掃描附近裝置
lspy send a.jpg --device "Pixel 7"
lspy send a.jpg --ip 192.168.1.20:53317 --pin 1234
lspy cross-send photo.zip      # 跨網傳送，產生 6 位 PIN
lspy cross-recv 123456 -d ./incoming
```

需求 Python 3.8+，無第三方依賴；需放通 TCP/UDP `53317`。

---

## 🛠️ 建置與測試

```bash
pip install .
python -m unittest discover -s tests -v
python scripts/sync_version.py --check
pip install pyinstaller && python scripts/build_binary.py
```

也可直接下載 [Release](https://github.com/styisme/lspy/releases) 的單檔執行檔：Windows `lspy-<版本>-windows-x64.exe`、Linux `lspy-<版本>-linux-x86_64`，免安裝 Python。

`release.yml` 會在 Windows 與 Linux 上分別打包，並於 `CHANGELOG.md` 變更推送後自動打 Tag、發佈 Release（含執行檔、wheel、sdist）。


CI 於 Windows / Linux 執行全量測試與版本一致性檢查；`CHANGELOG.md` 變更推送至 `main` 後自動建置 wheel、打 Tag 並發佈 Release。

---

## 🚧 風險與限制

1. **AI 參與度高**：協定、安全校驗與 CI 腳本為 AI 輔助生成，人類負責審閱與實機驗證，請勿視為「已完成安全稽核」。
2. **跨網通道為公網明文**：ntfy 話題即 PIN，**勿傳輸敏感資料**。
3. **單檔架構**：`lspy.py` 約 1500 行，便於分發，但模組化與靜態檢查較弱。
4. **自簽憑證**：不校驗憑證鏈（與 LocalSend 行為一致），無法抵禦中間人。
5. **平台差異**：Windows 防火牆、路由器 AP 隔離、macOS 本地網路權限皆可能導致無法發現。

---

## 📚 相關文件

- [CHANGELOG.md](CHANGELOG.md) / [CONTRIBUTING.md](CONTRIBUTING.md)
- [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md) / [docs/DEVELOPMENT_CONSTRAINTS.md](docs/DEVELOPMENT_CONSTRAINTS.md)
- [docs/AI-DEVELOPMENT-GUIDELINES.md](docs/AI-DEVELOPMENT-GUIDELINES.md)

---

## 📜 授權

MIT，詳見 [LICENSE](LICENSE)。協定相容性說明見 [LICENSE-LocalSend](LICENSE-LocalSend)。
