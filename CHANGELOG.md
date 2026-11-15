# 变更记录

本文件是版本号的**唯一来源**。新增版本请只改这里（`## [x.y.z] - YYYY-MM-DD`），由 `scripts/sync_version.py` 注入 `lspy.py` 与 `pyproject.toml`，CI 只校验不写入。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。

## [1.28.0] - 2026-11-15

### 新增（从 LocalSend 官方源码移植）

对照 `localsend-main` 的 `app/lib`（Flutter UI）与 `cli/src`，挑出 CLI 真正用得上的三处：

- **文件级 sha256 校验**：官方 `FileDto` 带 `sha256` 字段（`packages/core/src/model/transfer.rs`），发送端开 `createChecksums` 时填，接收端开 `verifyChecksums` 时校验，不符返回 `422 Checksum mismatch`（`http/server/v2.rs`）。lspy 现在对齐这套语义：不是「有 sha256 就校验」而是按配置决定。
- **网络排查**：移植官方 `pages/troubleshoot_page.dart` 的思路 —— 先看端口能否监听（`WinError 10013` / `EADDRINUSE` 是用户最常撞的墙），再列本机地址，最后给出官方同款的 `netsh advfirewall firewall add rule name="..." dir=in action=allow protocol=TCP localport=...` 命令。
- **随机别名**：对应 `util/alias_generator.dart` 的「形容词+水果」组合（词表按界面语言切换）。**这是一处行为变化**：以前没设别名会直接广播主机名，现在首次运行生成别名并写进配置，主机名不再进局域网。

### 变更

- `files[].sha256`：`send_checksum`（默认开）控制发送时是否附哈希，`verify_checksum`（默认开）控制接收时是否校验；两者在设置面板第 13 项一起切换。
- `device_type` / `device_model`：对应官方 `deviceType` / `deviceModel`，默认仍按平台推断为 `desktop` 与 `Python x.y on <platform>`，设置面板第 11、12 项可改，取值 `mobile` / `desktop` / `web` / `headless` / `server`。
- 纯 http 发送时多一行未加密提示（官方 `encryption_disabled_notice` 的 CLI 版）。
- `troubleshoot` 子命令 + 菜单第 `9` 项；`config --set` 认识 `send_checksum` / `verify_checksum`。
- i18n 223 键 ×10 语言（新增 26 键）。测试 101 → 109。

### 验证

- 云主机真机：`serve --auto-accept` 起接收端，`send` 发 4 KB 文件 → 落盘、内容一致（说明发送端带的 sha256 被接收端校验通过）；手工构造 `sha256` 全 0 的 `prepare-upload` + `upload` → **422**，且落盘文件被删除。
- Linux 上 `troubleshoot` 走非 Windows 分支，输出端口 / 地址 / 防火墙提示 / 组播四段；Windows 上额外打印两条 `netsh` 放行命令。
- 清空 `alias` 后首跑 `info` 得到 `Brave Apple` 一类别名并写入配置文件。

## [1.27.2] - 2026-11-15

### 修复

- **PIN 校验把对端连接打断**：收到 `prepare-upload` 时先判 PIN，不通过就直接回 401 并关连接，可这时对端还在写请求体。实测（Windows、请求体 200 KB）：服务端不读 body 就关闭，客户端拿到的是 `ConnectionAbortedError [WinError 10053]`，读不到 401 —— 官方 LocalSend 客户端因此不会弹 PIN 输入框，只表现为「发送一直失败」。现在先把请求体读完再判 PIN，401 能稳定送达，PIN 输入框正常出现。
- **设置里改 PIN 不生效**：后台接收服务在启动时就把 `pin` / `auto_accept` / `save_dir` 拷成自己的字段，而设置面板只写配置文件，于是改了 PIN 别人照样不用 PIN 就能发进来、改了保存目录文件还落回旧目录，看起来就是「PIN 是坏的」。新增 `_apply_server_config()`，退出设置时立即把这些值同步到运行中的服务；端口没法热改，改了就重建监听并打印新端口。
- 补三条回归用例：改 PIN 后运行中的实例立即要求 PIN（真机复验：菜单里设 2468 后不带 pin 得 401、带 `?pin=2468` 得 200）、`X-LocalSend-Pin` 请求头通道仍认、401 之前必须读完请求体。测试总数 98 → 101。

## [1.27.1] - 2026-11-15

### 修复

- **菜单「扫描附近设备」像是卡住**：深度扫描对 /24 里每个地址都要发 `http` 与 `https` 两次请求，Windows 上单次连接能等 5–9 秒，扫一个网段实测 35 秒，而中途只打印一行「正在启动 HTTP 深度扫描」，看上去就是死住了。现在先用 0.3 秒的 TCP 试探筛掉没开端口的地址，只对通的地址发 HTTP 请求：同一网段 35.4s → 8.2s。进度也可见了，扫描期间按 `🔎 已探/总数` 刷新一行，找到设备照样插播 `✅`。扫描结束仍回到菜单等待输入（真机复验：菜单选 2 → 7.4 秒后重新出现「请选择」）。

## [1.27.0] - 2026-11-15

### 新增

- **任意界面弹出接收申请**：交互菜单里的每一处输入都改成 `_prompt()`：它一边等这一行输入，一边盯着接收邀请队列。每次只挂一个「读一行」的任务（`_read_line_task`），任务一结束线程就空闲——不能用常驻 stdin 读线程，`cfdialog` 的文件浏览器自己也读 stdin，常驻读者会把它的按键吞掉。别人往本机发文件时会立刻打断当前提问，弹出「接收详情」——发件人、IP、文件数、总大小、前 10 个文件名都在里面；接受后直接进接收详情看进度，收完按回车回到刚才那个提问。设置面板、选文件、输入 IP、跨网 PIN 等界面同样生效。
- **自动接收直接进详情**：`auto_accept` 打开（或命中 `auto_accept_whitelist`）时不再询问，直接把请求送进接收详情页，进度、汇总照常显示，回车返回。
- **拒绝与超时都有回执**：直接回车接受，输入 `r`（或 `n`/`no`/`nein`/`нет`/`não`/`아니오`/`いいえ`）拒绝；60 秒无人应答按拒绝处理，不会把发件端吊死在那里。
- **发送完成后停在界面**：发送结束不再直接甩回菜单，先留一行「发送结束，按回车回到菜单」，按回车才回到菜单循环，避免发送完窗口一闪而过。

### 变更

- 接收进度只画一处：菜单在画详情时置 `server.quiet_receive`，HTTP 处理线程不再逐文件打印 `⬇️` 行，避免两处进度互相覆盖；会话建立那行 `📥` 也一并让位给详情页。
- 传输过程中的邀请不抢键盘（`_notify_invites()` 只提示排队数量），等回到输入界面或发送收尾时再弹出，避免在 `\r` 进度行里插字。
- 词表新增 9 个键（`press_enter_back`、`invite_banner`、`invite_prompt`、`invite_rejected`、`invite_timeout`、`recv_detail_title`、`recv_detail_state`、`recv_detail_done`、`send_back_hint`），10 种语言全覆盖，键数 188 → 197。

### 测试

- 新增 8 个用例：字节数格式化（B/KB/MB/GB 四处进位）、回车接受 / `r` 拒绝 / EOF 拒绝、`serve` 子命令仍走终端确认且不入菜单队列、`auto_accept` 直接把邀请送进详情、正在回答别的问题时邀请先弹出且回车后回到原问题、拒绝时不进详情、非终端输入仍按原语义读 `input()`。测试总数 90 → 98。

## [1.26.0] - 2026-11-15

### 新增

- **Android 上自动跳过 tkinter**：新增 `_is_android()`，按 `sys.platform == "android"`、`TERMUX_VERSION`、`PREFIX` 含 `com.termux`、`ANDROID_ROOT` / `ANDROID_DATA` 四个标记判定（只读环境，不跑外部命令，结果缓存一次）。命中后 `pick_files()` 根本不 import `tkinter` —— 手机上的 Python 发行版（Termux、Pydroid、Chaquopy）基本不带 Tk，`import tkinter` 轻则 `ImportError`，重则卡住整个菜单；跳过后直接走 cfdialog，库也不在才退回手敲路径。
- 判定与 `force_cfdialog` 相互独立：任一成立就跳过 `tkinter`，不互相覆盖。

### 测试

- 新增 3 个用例：四个环境标记逐个命中（含反例 `PREFIX=/usr` 不误判为 Android）、Android 上同时装上会抛错的 tkinter stub 与可用的 cfdialog 时必须走 cfdialog、Android 且没有 cfdialog 时仍能手敲路径。测试总数 87 → 90。

## [1.25.1] - 2026-11-15

### 修复

- 1.25.0 新增的 `test_force_cfdialog_is_a_real_config_key` 把 `sys.stdout` 指向用系统默认编码打开的 `os.devnull`，在 CI 的 Windows 上（cp1252）打印 `✅` 时直接 `UnicodeEncodeError`，三个 Windows 矩阵全红。改用 `contextlib.redirect_stdout(io.StringIO())` 收口，与终端编码无关。

### 测试

- 本地用 `PYTHONIOENCODING=cp1252` 复现旧行为并验证修复：`TestDialogPicker` 在 cp1252 下 10 例全过。测试总数仍为 87。

## [1.25.0] - 2026-11-15

### 新增

- **强制使用 cfdialog 的开关**：新增配置键 `force_cfdialog`（默认 `false`），打开后选文件直接走 cfdialog 终端浏览器，**跳过 `tkinter`** —— 有些机器上 `tkinter` 能 `import` 却弹不出窗（缺 Tcl 数据、无 DISPLAY、或有窗口但被远程桌面吞掉焦点），此时自动降级顺序反而会先卡在一个不响应的窗口里。开关可在 `8. 设置` 的第 10 项一键切换，也可 `config --set force_cfdialog=true`（接受 `1/true/yes/on`）。
- 设置面板新增「选文件方式」一行摘要：`自动（tkinter → cfdialog）` / `强制 cfdialog（跳过 tkinter）`，不用记配置文件里放过什么。

### 变更

- 词表新增 4 个键（`cfg_dialog`、`cfg_dialog_auto`、`cfg_dialog_force`、`cfg_menu_force_cfdialog`），10 种语言全覆盖，键数 184 → 188；设置菜单的选项从 9 项扩到 10 项，选择提示同步改为 `[0-10]`。
- 强制只改变**尝试顺序**，不改变失败语义：`force_cfdialog` 打开但库不在（例如有人把 `cfdialog.py` 删了）时，仍然回退到「手敲逗号分隔路径」，不会把用户锁死在一个不可用的选择器上。

### 测试

- 新增 3 个用例：开着强制时即使 `tkinter` 可导入也不得调用它（用会在被调用时抛错的 stub 断言）、强制但缺库时仍能手敲路径、`force_cfdialog` 从 `CONFIG_DEFAULTS` 与 `config --set` 两个方向都能进来。测试总数 84 → 87。

## [1.24.0] - 2026-11-15

### 新增

- **内置 cfdialog 文件选择器**：随仓库附带 [cfdialog](https://github.com/styisme/cfdialog) 0.3.0（单文件、纯标准库的 CLI 文件对话框库，MIT），`4. 发送文件到设备` 选文件时依次尝试 `tkinter` → `cfdialog` 交互式浏览器 → 手敲路径。没有 `tkinter` 数据文件的精简 Python（本例即是）以前只能一路退到「输入路径」，现在可以在目录里用数字跳转、`g` 切分区、`h` 显示隐藏文件、`a`/`c`/`d` 多选。
- **设置里的保存目录支持浏览**：`8. 设置` → 保存目录一项输入 `?` 直接用目录浏览器挑，不用再对着键盘敲一长串路径；提示文案（`cfg_savedir_hint`）已补进 10 份词表。

### 变更

- cfdialog 的自动提权被显式关闭（`set_auto_elevate(False)`）：它默认会在首次调用时尝试 UAC/root 并**重启整个进程**，放进交互菜单等于随机退出。
- cfdialog 的界面语言跟随 lspy 当前语言（`zh→zh_CN`、`zh_TW→zh_TW`、`en/ja/ko/ru/fr/es` 直映）；`de`/`pt` 没有对应语言包，回退英文。
- 打包脚本把 `lg/*.txt` 作为数据一并塞进单文件产物（解包后 `_MEIPASS/lg` 正好对上 cfdialog 的 `LIB_DIR/lg`），所以 exe 里的选择器不是只有中英两种语言。

### 测试

- 新增 7 个用例：缺库时三条入口都返回 `None`（继续降级而不是崩）、加载器确实关掉了自动提权、多选/单选返回值规整、取消与异常都算「没选到」、`tkinter` 与 cfdialog 都不可用时仍能手敲逗号分隔路径、语言映射只映射 cfdialog 真有的语言包。测试总数 77 → 84。

## [1.23.2] - 2026-11-15

### 修复

- 剪贴板命令行工具（`pbcopy` / `wl-copy` / `xclip` / `xsel`）原先只看进程有没有跑起来就算成功，不看退出码：`xclip` 装在机器上却拿不到 X display 时会返回 1，此时仍被当成「已写入剪贴板」，`/web/text` 因此跳过落盘，用户粘进来的文本既没进剪贴板也没存文件。现在统一走 `_run_clipboard_cmd`，退出码非 0 一律算失败并继续降级（`wl-copy`→`xclip`→`xsel`→`tkinter`）。

### 测试

- 新增 2 个用例：命令不存在或退出码非 0 都返回失败、真实 POSIX 命令零退出码才算成功。测试总数 75 → 77。

## [1.23.1] - 2026-11-15

### 新增

- **收到的小 txt 自动进剪贴板**（移植自 watchsend `UploadHandler`）：接收完成的 `.txt` 若不超过 10 KB 且内容非空，直接把正文写进本机剪贴板（`_maybe_clipboard_text`），省掉「去下载目录找文件、再打开复制」这一步。无 GUI/无剪贴板的环境静默跳过，不影响接收；`config --set clipboard_text=false` 可关掉。
- **IPv6 可直连地址展示**（移植自 watchsend `CrossNetActivity` 的 `[IPv6]:53317`）：`info` 在协议 JSON 之后追加本机 IPv6 的 `[地址]:端口`，跨网时可以直接抄给对端。只列全球/唯一本地单播地址，`::1`、`::`、`fe80::` 链路本地（需 zone id 才能路由）一律不展示。

### 变更

- **历史记录条数上限**（移植自 watchsend `HistoryStore` 只保留最新 100 条）：新增 `history_max` 配置，默认 300，超出后追加时自动丢掉最旧记录（走临时文件 + `os.replace`，不会写坏历史）；设 0 表示不裁剪。原先 `history.jsonl` 只增不减，长期使用会无限膨胀、每次读取都要全量解析。

### 修复

- **剪贴板改为系统原生通道**：`_clipboard_set` / `_clipboard_get` 先走 Win32 API（`CF_UNICODETEXT`）、`pbcopy` / `wl-copy` / `xclip` / `xsel`，`tkinter` 只作兜底。原先只依赖 `tkinter`，而它需要 `init.tcl` 等数据文件 —— 在精简 Python 与 PyInstaller 打包里常常缺失，`import tkinter` 成功但 `tkinter.Tk()` 抛 `TclError`，于是剪贴板写入一直静默失败：1.22.0 的 `/web/text` 在中文 Windows 上从未真正写进剪贴板，本次新增的「收到 txt 自动进剪贴板」也会无声失效。

### 测试

- 新增 11 个用例：小 txt 写入剪贴板、非 txt 与超 10 KB 跳过、配置关闭后不写、真实 HTTP 上传 `.txt` 后剪贴板收到正文（验证 `_post_process` 接线）、历史上限丢最旧 / 0 关闭裁剪 / 裁剪后每行仍是合法 JSON、IPv6 列表按方括号打印、无 IPv6 时给出提示、枚举结果不含回环与链路本地、Win32 剪贴板原生通道往返（含中文）。测试总数 64 → 75。
- 测试进程默认把 `_clipboard_set` 换成桩，跑测试不会再覆盖用户自己的剪贴板内容。

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
