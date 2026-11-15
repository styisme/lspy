[简体中文](README.md) | [繁體中文](README_zh_TW.md) | [English](README_EN.md) | [日本語](README_ja.md) | [한국어](README_ko.md) | [Deutsch](README_de.md) | [Français](README_fr.md) | [Español](README_es.md) | [Русский](README_ru.md) | [Português](README_pt.md)

# lspy

> LocalSend 协议的命令行实现。单文件、零第三方依赖，手机上跑 LocalSend，电脑上一条命令收发文件；也能借 ntfy.sh 做跨网中继。

[![CI](https://github.com/styisme/lspy/actions/workflows/ci.yml/badge.svg)](https://github.com/styisme/lspy/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-1.23.2-512BD4)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Made with AI](https://img.shields.io/badge/made%20with-AI-FF6B6B)](docs/AI_DISCLOSURE.md)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-brightgreen)]()

---

## ⚠️ AI 生成声明

> **本项目在开发过程中大量使用大型语言模型辅助生成，人类负责需求、审阅、验证与发布。**
>
> 详细范围与已知风险见 [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md)；本项目遵循 [AI 开发规范](https://github.com/styisme/ai-development-guidelines)（仓库内副本：[docs/AI-DEVELOPMENT-GUIDELINES.md](docs/AI-DEVELOPMENT-GUIDELINES.md)）。

---

## 📦 版本与来源

当前版本：**v1.23.2**（版本号唯一来源为 [CHANGELOG.md](CHANGELOG.md)，由 CI 校验并注入）。

本项目是 LocalSend 协议的**独立命令行实现**，从零编写，不复制官方 App（Apache-2.0）源码，仅在协议层与其互通，详见 [LICENSE-LocalSend](LICENSE-LocalSend)。同族的图形端实现见 [OldSend](https://github.com/styisme/oldsend) 与 [WatchSend](https://github.com/styisme/watchsend)，lspy 与其共享协议思路，代码互不依赖。

---

## ✨ 核心特性

### 🌐 协议与发现
- **双版本协议**：实现 LocalSend `v2`（`prepare-upload`/`upload`/`cancel`）与 `v2.1`（`send-request`/`send`），`v1` 前缀同样可用，兼容新老客户端。
- **智能回退**：发送端优先 v2.1，对方返回 404/405 自动回退 `prepare-upload`，上传路径随协商结果切换。
- **三重发现**：组播 `224.0.0.167:53317` + 全网段广播 + **HTTP 深度扫描**（多网卡多网段、双端口并发探测，专治组播被防火墙或 AP 隔离拦截）。
- **手动直连**：`--ip HOST[:PORT]` 绕过发现机制，`scan --json` 便于脚本消费。

### 🛡️ 传输与安全
- **断点续传**：会话内重传从已落盘偏移继续；已完成文件的重试直接确认，不重复写入。
- **绝不覆盖**：落地文件名统一走 `safe_filename` + `unique_path`，冲突自动加 `(1)`，同名同大小也没机会被"静默跳过"。
- **访问控制**：PIN 校验（`401` + `X-LocalSend-Pin`）、指纹黑白名单（支持前缀匹配）、危险扩展名过滤（默认拦截 `exe,bat,cmd,vbs,sh`），逐文件跳过而非整会话拒绝。
- **解压防护**：拒绝绝对路径、盘符、`..` 穿越与符号链接条目（Zip Slip）。
- **TLS**：`lspy cert` 生成自签证书，收发两端均可走 HTTPS。

### 🔁 跨网与界面
- **跨网中继**：`cross-send` / `cross-recv` 以 ntfy.sh 为通道，6 位 PIN 即话题名，分块 2400 字节（不超单条上限）、3 次退避重试、尾包 SHA-256 + 长度校验、按消息 id 去重。
- **Web 分享页**：接收端内建一页 HTML（设备信息 + 最近接收记录），并当成「网页版传输」用：浏览器直接上传文件到接收目录、浏览并下载已接收文件、把文本写进本机剪贴板（不可用时落盘成 txt）。这套页面与 `/web/*` 端点移植自 watchsend 的 `WebShareHandler`；设了 PIN 时页面的读写一律要 PIN。页面语言跟随浏览器的 `Accept-Language`，十种语言里一门都认不出才回退 CLI 语言。
- **历史记录管理**（移植自 watchsend 的 History Quick Management）：`history --delete N` 删除第 N 条（1＝最新，等价于 watchsend 的长按删除）、`--clear` 整表清空、`--unzip N` 就地解压该条 ZIP（复用 `safe_unzip`，绝对路径 / `..` / 符号链接一律拒绝）；列表里 ZIP 标 📦。历史条数由 `history_max`（默认 300）封顶，超出自动丢最旧，不再无限膨胀。
- **收到的小 txt 自动进剪贴板**（移植自 watchsend 的 `UploadHandler`）：≤10 KB 的 `.txt` 接收完直接把正文写进本机剪贴板，不用再去下载目录翻文件；无剪贴板环境静默跳过，`config --set clipboard_text=false` 可关。
- **IPv6 直连地址**（移植自 watchsend 的 `[IPv6]:53317` 展示）：`info` 在协议 JSON 后追加本机 IPv6 的 `[地址]:端口`，跨网时直接抄给对端；只列全球/唯一本地单播，链路本地不展示。
- **调试键模式**（移植自 watchsend 的 Debug Keys Mode）：`--debug-keys` 让界面直接显示原始 i18n 键名（如 `⟦history_empty⟧`），缺翻译一眼可见；`config --set debug_keys=true` 可长期打开，命令行开关不会写进配置。
- **交互菜单**：无子命令运行即自动后台接收，菜单内可扫描、发送、跨网、查历史、改配置。
- **10 种界面语言**：简/繁中文、英、日、韩、德、法、西、俄、葡。

---

## 📱 快速开始

### 1. 安装

```bash
git clone https://github.com/styisme/lspy.git
cd lspy
python lspy.py --help          # 免安装直接用
pip install .                  # 或安装为 lspy 命令
```

要求 Python 3.8+，无第三方依赖；`tkinter` 缺失时文件选择自动降级为手输路径。

不想装 Python 也可以：直接下载 [Release](https://github.com/styisme/lspy/releases) 里的单文件程序 —— Windows `lspy-<版本>-windows-x64.exe`、Linux `lspy-<版本>-linux-x86_64`，下载即可运行。Linux 二进制在 Ubuntu 22.04 上构建，要求 `glibc ≥ 2.35`（更老的发行版请用 `pip install lspy`）。

### 2. 接收

```bash
lspy serve --web               # 启动服务并打开状态页
lspy serve --auto-accept -d ~/Downloads/lspy --pin 1234
```

手机端 LocalSend 打开后应能扫描到本机；放通 TCP/UDP `53317`。

### 3. 发送

```bash
lspy scan                                    # 先看有哪些设备
lspy send a.jpg b.pdf --device "Mi 14"       # 按别名发送
lspy send a.jpg --ip 192.168.1.20:53317 --pin 1234
```

### 4. 跨网

```bash
lspy cross-send photo.zip                    # 生成 6 位 PIN
lspy cross-recv 123456 -d ./incoming         # 另一端凭 PIN 接收
```

---

## 🧰 命令与配置

| 命令 | 说明 |
| --- | --- |
| `lspy info` | 打印本机 LocalSend 信息 |
| `lspy scan [-t 2] [--json]` | 发现附近设备 |
| `lspy serve [-p 53317] [-d DIR] [--pin PIN] [--auto-accept\|--confirm] [--web] [--no-multicast] [--no-web]` | 接收服务 |
| `lspy send FILES... (--device NAME\|--ip HOST[:PORT]) [--pin PIN] [--https]` | 发送文件 |
| `lspy cross-send FILES... [--pin PIN]` / `lspy cross-recv PIN [-d DIR]` | 跨网收发 |
| `lspy history [-n 20] [--delete N] [--clear] [--unzip N]` | 历史列表 / 删单条 / 清空 / 解压 ZIP |
| `lspy open FILES...` / `lspy cert` / `lspy stun` | 打开、证书、公网探测 |
| `lspy config [--show] [--set k=v] [--reset]` | 配置管理 |

配置文件位于 `~/.lspy/`（`config.json`、`history.jsonl`、`lspy.log`、`cert.pem` / `key.pem`）。常用键：`alias`、`port`、`save_dir`、`pin`、`auto_accept`、`filter_ext`、`whitelist` / `blacklist`、`auto_accept_whitelist`、`use_https`、`web_enable`、`organize_by_type`、`history_enable`、`auto_unzip`、`open_after_receive`、`lang`、`ntfy_topic`、`log_level`、`fingerprint`、`debug_keys`，完整说明见 [CONTRIBUTING.md](CONTRIBUTING.md#配置项)。

协议端点一览（`/api/localsend/{v1,v2}/…`）：`info`、`register`、`prepare-upload`、`send-request`、`upload`、`send`、`cancel`，以及 Web 分享页 `/` 与 `/web/info`、`/web/files`、`/web/download`、`/web/upload`、`/web/text`、`/web/clipboard`。细节见 [CONTRIBUTING.md](CONTRIBUTING.md#协议实现)。

---

## 🛠️ 构建与测试

单文件 Python 项目，无第三方依赖；打包走标准 `pyproject.toml`，可执行程序走 PyInstaller：

```bash
pip install .                                  # 安装为 lspy
python -m unittest discover -s tests -v        # 77 个用例：单元 + 端到端
python scripts/sync_version.py --check         # 校验版本号与 CHANGELOG 一致
pip install pyinstaller && python scripts/build_binary.py   # 打包单文件可执行程序
```

`build_binary.py` 从 `CHANGELOG.md` 读版本号，产物落在 `dist/` 并按平台命名：
`lspy-<版本>-windows-x64.exe`、`lspy-<版本>-linux-x86_64`、`lspy-<版本>-linux-arm64`、`lspy-<版本>-macos-arm64`、`lspy-<版本>-macos-x64`（Windows 带 `.exe` 后缀）。`--clean` 可先清空 `build/` 与 `dist/`。

### 🤖 自动化

- **CI**：`ci.yml` 在 Windows / Linux 上跑全量测试与版本一致性检查。
- **Release**：`CHANGELOG.md` 变更推送到 `main` 后，`release.yml` 在 Windows 与 Linux runner 上分别用 PyInstaller 打出单文件可执行程序，同时构建 wheel 与 sdist；四类产物汇总后自动打 Tag、发布 GitHub Release。
- **版本号**：唯一来源为 `CHANGELOG.md`，由 `scripts/sync_version.py` 注入 `lspy.py` 与 `pyproject.toml`；CI 只校验不写入。

---

## 🚧 风险与局限

1. **AI 参与度高**：核心协议、安全校验、CI 脚本均为 AI 辅助生成，人类负责审阅与实机验证，请勿把本项目当作"已安全审计"的实现。
2. **跨网通道是公网明文**：ntfy.sh 话题即 PIN，PIN 泄露等于文件泄露，**不要传输敏感数据**。
3. **单文件架构**：`lspy.py` 约 1500 行，便于分发与嵌入，但也意味着模块化、类型标注与静态检查较弱。
4. **自签证书**：HTTPS 通信不校验证书链（与 LocalSend 行为一致），不具备抵御中间人的能力。
5. **平台差异**：Windows 防火墙、路由器 AP 隔离、macOS 本地网络权限都可能让发现失败，需按 [故障排查](CONTRIBUTING.md#故障排查) 逐项确认。

---

## 📚 相关文档

- [CHANGELOG.md](CHANGELOG.md) — 版本变更
- [CONTRIBUTING.md](CONTRIBUTING.md) / [CONTRIBUTING_EN.md](CONTRIBUTING_EN.md) — 贡献指南
- [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md) — AI 生成声明
- [docs/DEVELOPMENT_CONSTRAINTS.md](docs/DEVELOPMENT_CONSTRAINTS.md) — 开发环境约束
- [docs/AI-DEVELOPMENT-GUIDELINES.md](docs/AI-DEVELOPMENT-GUIDELINES.md) — AI 开发规范（仓库内副本）
- [LocalSend 协议文档](https://github.com/localsend/localsend/blob/main/docs/protocol.md)

---

## 📜 许可

本项目代码使用 [MIT 协议](LICENSE)。

与 LocalSend 的协议兼容性说明见 [LICENSE-LocalSend](LICENSE-LocalSend)；本项目为独立实现，未复制官方源码。
