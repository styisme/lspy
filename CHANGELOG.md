# 变更记录

本文件是版本号的**唯一来源**。新增版本请只改这里（`## [x.y.z] - YYYY-MM-DD`），由 `scripts/sync_version.py` 注入 `lspy.py` 与 `pyproject.toml`，CI 只校验不写入。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。

## [1.23.0] - 2026-11-15

### 新增

- **Web 页跟随浏览器语言**（移植自 watchsend 的「Web 10-Language Adaptive」）：接收端不再把网页语言绑死在 CLI 的当前语言，而是读 `Accept-Language` 并按 q 权重挑一门内置语言（`pick_accept_language`），认不出来才回退 CLI 语言。`<html lang>` 也一并写入，读屏与断词都跟着浏览器走。
- **调试键模式**（移植自 watchsend 的 Debug Keys Mode）：`--debug-keys` 让本次运行的界面直接显示原始 i18n 键名（如 `⟦history_empty⟧`），一眼就能看出哪句没翻译；`config --set debug_keys=true` 可长期打开，命令行开关不会写进配置。
- **历史记录管理**（移植自 watchsend 的 History Quick Management 与 Native ZIP Extraction）：`history --delete N` 删除列表里第 N 条（1＝最新，等价于 watchsend 的长按删除），`--clear` 整表清空，`--unzip N` 把该条 ZIP 就地解压到同名文件夹并复用 `safe_unzip`（绝对路径、`..` 穿越、符号链接条目一律拒绝）。列表里 ZIP 按 watchsend 的习惯标 📦。

### 变更

- 新增 `_t_for(lang, key)` 按语言取词条，Web 页按请求语言渲染，不再依赖全局 `_current_lang`。
- 删除历史条目时先把「最新在前」的列表反序写进临时文件，再 `os.replace` 换回，避免写一半把历史弄丢。

### 测试

- 新增 15 个用例：`Accept-Language` 取高权重 / 跳过 `q=0` 与未知语言 / 无头回退、页面按 `ja` 与未知语言分别渲染、调试键模式返回原始键与命令行开关、ZIP 标记、按序号删除（含越界不动文件）、清空、历史 ZIP 解压、非 ZIP 拒绝、Zip Slip 拒绝。测试总数 49 → 64。

## [1.22.0] - 2026-11-15

### 新增

- **Web 分享页**（移植自 watchsend 的 `WebShareHandler` + `index.html`）：接收端的 `/` 从只读状态页升级为单页三页签分享界面 —— 浏览器直接上传文件到接收目录（拖拽/多选、逐文件进度、名称经 `safe_filename`+`unique_path`、命中 `filter_ext` 一律 403、单次上限 2 GiB）、浏览并下载已接收文件（`/web/files` + 流式 `/web/download`，`web_safe_path` 挡住 `..` 与绝对路径）、把文本写进本机剪贴板（无剪贴板环境自动落盘为 `web-text-<时间>.txt`）。
- `/web/info` 返回别名、端口、版本、是否需要 PIN 与已接收文件数。
- 设了 PIN 时，`/web/*` 全部要求 `pin` 查询参数或 `X-LocalSend-Pin` 请求头；页面会提示输入并记住（localStorage）。
- 13 条新文案进 10 份词表（各 175 键），页面语言跟随 CLI 当前语言。

### 变更

- 页面模板改为占位符替换（`@@TOKEN@@`），不再用 `.format` 拼 CSS，避免大括号转义坑。
- README 10 语言与 CONTRIBUTING 中英同步更新 Web 分享页说明与端点表。

### 测试

- 新增 12 个用例：页面三页签 + 占位符全部替换、`/web/info`、文件列表、上传落盘与中文名、扩展名拦截、下载字节一致、下载 `..` 穿越拒绝、上传穿越名压平、PIN 保护、`/web/text` 空与非空、`web_safe_path` 边界。测试总数 37 → 49。

## [1.21.2] - 2026-11-15

### 修复

- Linux 上一个 locale 环境变量都没有时（`LANG`/`LC_*` 全空），`history` 等命令会把 `locale.getdefaultlocale()` 的 `DeprecationWarning` 直接打进取到的输出里。现在该探测函数被包进 `warnings.catch_warnings` 并忽略 `DeprecationWarning`，同时用 `getattr` 兼容 Python 3.15 移除该 API 后的情形。
- 补一个回归测试断言该探测不再泄漏弃用警告，测试总数 36 → 37。

## [1.21.1] - 2026-11-15

### 修复

- `auto` 语言检测在 Windows 上从未生效，等于默认英文：`_lang_from_windows()` 用 `k.close()` 关闭 `winreg.PyHKEY`，而该对象只有 `Close()`，`AttributeError` 被 `except Exception` 吞掉，函数直接返回 `None`；`_lang_from_locale()` 则把 `locale.getlocale()` 的本地化长名（中文系统是 `Chinese (Simplified)_China`）当成语言代码，`_normalize_lang` 只认 `zh_/ja_/de_` 这类前缀，同样返回 `None`。两条兜底同时失效 → `detect_lang()` 一律落到 `"en"`，中文 Windows 上首启是英文界面。
- `_lang_from_windows()` 改用 `with winreg.OpenKey(...)` 托管句柄，不再手动关闭。
- `_lang_from_locale()` 依次尝试 `locale.getlocale()`、`locale.getdefaultlocale()`，任一取到有效值即返回。

### 变更

- `_normalize_lang()` 增补本地化全名映射：`Chinese (Traditional)`/`Taiwan`/`Hong Kong`/`Macau` → `zh_TW`，其余 Chinese → `zh`；Japanese / Korean / German / French / Spanish / Russian / Portuguese / English 全名同样可识别，`auto` 在中文、德文等系统上都能命中对应语言。

### 新增

- 3 个回归测试：本地化长名归一化、假 `winreg` 断言不再调用 `close()`（旧实现必挂）、`auto` 必须落在 `SUPPORTED_LANGS` 内。测试总数 33 → 36。

## [1.21.0] - 2026-11-15

### 修复

- 语言菜单"英文冒充其它语言"：`I18N` 里只有 `en`、`zh` 两份真实词表，其余 8 种语言被启动时的兜底循环 `I18N[lg] = dict(I18N["en"])` 静默复制成英文副本。结果是「设置 → 修改语言」只有 1–2 项正常，第 3–10 项全部显示 `English`，切换到 ja/ko/de/fr/es/ru/pt/zh_TW 后界面依旧是英文——README 声称 10 语言、CLI 实际只有 2 语言。
- 兜底循环改为**导入时硬校验**：`SUPPORTED_LANGS` 中任一语言缺失词表即抛 `RuntimeError`，不再用英文副本掩盖缺失。

### 新增

- 内置完整词表：`zh_TW`（繁體中文）、`ja`（日本語）、`ko`（한국어）、`de`（Deutsch）、`fr`（Français）、`es`（Español）、`ru`（Русский）、`pt`（Português），每份 162 个键，占位符（`{p}`、`{q}`、`{n}`、`{ip}` 等）与英文逐一对应；菜单、扫描、收发、跨网、历史、设置、Web 状态页全部本地化，Windows 防火墙与端口占用等诊断句一并翻译。
- 语言菜单现在显示各自母语名（`zh_TW — 繁體中文`、`ja — 日本語`……），10 种语言名互不重复。
- 4 个回归测试：各语言键集合必须等于英文的 162 键且非空、非英文副本；语言名互补重复且 `zh_TW` 为 `繁體中文`；每键占位符与英文一致；切换语言后 `t()` 输出确实改变（测试总数 29 → 33）。

## [1.20.1] - 2026-11-15

### 修复

- Linux 二进制在旧发行版上无法启动：`ubuntu-latest`（24.04）打出的 PyInstaller 包要求 `GLIBC_2.38`，在 Ubuntu 22.04（glibc 2.35）上报 `libm.so.6: version 'GLIBC_2.38' not found` 直接退出。发版矩阵的 Linux 构建改到 `ubuntu-22.04`，产物兼容 glibc ≥ 2.35 的发行版。

## [1.20.0] - 2026-11-15

### 新增

- 单文件可执行程序：`scripts/build_binary.py` 从 `CHANGELOG.md` 读版本号，用 PyInstaller 打包 `lspy.py`，产物按平台命名（`windows-x64.exe` / `linux-x86_64` / `linux-arm64` / `macos-arm64` / `macos-x64`），支持 `--clean`；`tkinter` 存在时才加入 `--hidden-import`，缺失平台自动降级为手输路径。
- 发版流水线同时出二进制与包：`release.yml` 拆为 `binaries`（`windows-latest` + `ubuntu-latest` 矩阵）、`package`（wheel + sdist）、`release`（汇总全部产物 → 打 Tag → 发布 Release）三个 job。Linux runner 先尝试 `apt-get install python3-tk`。
- `pyproject.toml` 增加 `binary` 可选依赖（`pyinstaller>=6.0`）。

### 变更

- README（10 语言）与 CONTRIBUTING（中英）补充"直接下载预编译程序"与本地打包命令；Release 产物说明更新为"Windows exe + Linux 可执行文件 + wheel + sdist"。

## [1.19.2] - 2026-11-15

### 修复

- Windows 旧代码页（cp936 / cp1252）下打印 emoji 会抛 `UnicodeEncodeError`，导致 `LspyServer.start()` 在启动阶段直接失败（GitHub Actions 的 Windows runner 即此场景）：`_configure_stdio()` 现在**无条件**把 stdout/stderr 切到 UTF-8（`errors="replace"`），并在模块导入时即生效，作为库调用或被测试导入时同样安全。
- 修复 `scripts/sync_version.py` 的替换缺陷：旧实现把原版本号又拼回字符串（写出 `VERSION = "1.19.11.19.0` 这类坏内容），现按正确分组替换并增加写后自校验。

## [1.19.1] - 2026-11-15

### 修复

- 端口被占用时给出可读诊断：识别 `WinError 10013` / `WSAEACCES` 与 `EADDRINUSE`，明确提示"本机可能已有 LocalSend 桌面版或另一个 lspy 实例占用该端口"，不再误报为"连接失败"。
- 默认端口 `53317` 被占用时自动回退到系统分配的空闲端口，并打印实际绑定端口；`-p` 显式指定的端口仍严格失败，不做隐式替换。
- 组播端口 `53317` 被占用时提示与 LocalSend 桌面版共存的处理方式（可加 `--no-multicast`），而不是笼统的"组播监听失败"。
- 交互菜单「切换为前台服务」不再吞掉绑定错误。
- 新增 `TestPortConflict` 四个用例（10013 / EADDRINUSE 识别、非冲突错误不误判、默认端口回退）。

## [1.19.0] - 2026-11-15

### 修复

- 同名同大小文件不再被当作「已接收」静默跳过：改为统一走 `unique_path` 生成新文件名，绝不覆盖既有文件。
- 接收端口一致性：`/info` 与组播应答改为返回实际绑定端口，`port=0` 或 `-p` 覆盖时不再广播错误端口。
- 断点续传语义修正：仅在同一会话内按已落盘偏移续传，已完成文件的重试直接确认而不重写；进度统计包含续传偏移，不再少算。
- 扩展名过滤改为**逐文件跳过**（此前会整会话 403 拒绝），全部被拦时才返回 403。
- `safe_unzip` 加固：拒绝绝对路径、盘符、`..` 穿越与符号链接条目，失败给出具体条目而不是静默返回 False。
- 进度输出在非 TTY（重定向/日志）下改为每 10% 一行，不再用 `\r` 刷屏；`IS_IDLE` 场景不再打印半行。
- 非交互 stdin 且未开自动接收时直接拒绝请求并记日志，避免服务线程卡死。
- `stun` 在异常路径也已关闭 socket；`interactive_config` 端口非法输入有提示；`config --set` 增加类型校验与错误提示。
- `history` 无记录时输出提示；`cmd_send` 缺少 `--device/--ip` 时明确报错。

### 新增

- LocalSend v2.1 端点：`send-request` / `send`；发送端优先 v2.1，遇到 404/405 自动回退 `prepare-upload`。
- Web 状态页（`GET /`）：设备信息 + 最近接收记录，支持 `--web` 自动打开与 `web_enable` 开关。
- 发送端 HTTPS 支持（`--https`，自签证书不校验证书链）；`--ip` 增加 `--port` 参数。
- 接收端 `register` 回执、发送前主动注册、`fileType` 按 MIME 推断（不再一律 octet-stream）。
- `scan --json` 机读输出；`--version`；`serve --no-multicast / --no-web`；`main(argv)` 便于嵌入与测试。
- HTTP 深度扫描覆盖多网卡多网段，同时探测配置端口与默认端口，并去重。
- 跨网传输分块降到 2400 字节（base64 后不超 ntfy 单条上限），分块上传带 3 次重试，尾包携带 SHA-256 与总长度做完整性校验，接收端按消息 id 去重。
- 收到文件后的可选项真正生效：`auto_unzip`（安全解压）与 `open_after_receive`；移除从未生效的 `text_clipboard` 配置与死代码 `copy_to_clipboard`。
- 界面文案补全 i18n（菜单标题、前台切换、发送向导、错误提示等）。

### 工程化

- 新增 `tests/test_lspy.py`：25 个单元 + 端到端用例（含 v2.1 流程、PIN、黑名单、扩展名过滤、路径穿越、同名冲突、大文件）。
- 新增 `pyproject.toml`（`pip install .` 后可用 `lspy` 命令）与 `.gitignore`。
- 新增 `README.md`。

## [1.18.2] - 2026-11-14

### 新增

- 初版：LocalSend v1/v2 收发、组播扫描、HTTP 深度扫描、ntfy.sh 跨网、多语言菜单。

[1.22.0]: https://github.com/styisme/lspy/compare/v1.21.2...v1.22.0
[1.21.2]: https://github.com/styisme/lspy/compare/v1.21.1...v1.21.2
[1.21.1]: https://github.com/styisme/lspy/compare/v1.21.0...v1.21.1
[1.21.0]: https://github.com/styisme/lspy/compare/v1.20.1...v1.21.0
[1.20.1]: https://github.com/styisme/lspy/compare/v1.20.0...v1.20.1
[1.20.0]: https://github.com/styisme/lspy/compare/v1.19.2...v1.20.0
[1.19.2]: https://github.com/styisme/lspy/compare/v1.19.1...v1.19.2
[1.19.1]: https://github.com/styisme/lspy/compare/v1.19.0...v1.19.1
[1.19.0]: https://github.com/styisme/lspy/compare/v1.18.2...v1.19.0
[1.18.2]: https://github.com/styisme/lspy/releases/tag/v1.18.2
