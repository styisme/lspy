# 变更记录

本文件是版本号的**唯一来源**。新增版本请只改这里（`## [x.y.z] - YYYY-MM-DD`），由 `scripts/sync_version.py` 注入 `lspy.py` 与 `pyproject.toml`，CI 只校验不写入。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。

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

[1.20.0]: https://github.com/styisme/lspy/compare/v1.19.2...v1.20.0
[1.19.2]: https://github.com/styisme/lspy/compare/v1.19.1...v1.19.2
[1.19.1]: https://github.com/styisme/lspy/compare/v1.19.0...v1.19.1
[1.19.0]: https://github.com/styisme/lspy/compare/v1.18.2...v1.19.0
[1.18.2]: https://github.com/styisme/lspy/releases/tag/v1.18.2
