# 变更记录

本文件是版本号的**唯一来源**。新增版本请只改这里（`## [x.y.z] - YYYY-MM-DD`），由 `scripts/sync_version.py` 注入 `lspy.py` 与 `pyproject.toml`，CI 只校验不写入。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。

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

[1.19.0]: https://github.com/styisme/lspy/compare/v1.18.2...v1.19.0
[1.18.2]: https://github.com/styisme/lspy/releases/tag/v1.18.2
