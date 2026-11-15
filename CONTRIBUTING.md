# 贡献指南

[**简体中文**](CONTRIBUTING.md) | [English](CONTRIBUTING_EN.md)

感谢为 **lspy** 贡献代码。本项目遵循一套轻量但严格的管理约定：**Conventional Commits + SemVer 2.0.0 + CHANGELOG**。

> **关于出身**：lspy 是 LocalSend 协议的独立命令行实现（Python，单文件，仅标准库），从零编写，不复制官方 App 源码。同族的图形端实现见 [OldSend](https://github.com/styisme/oldsend) 与 [WatchSend](https://github.com/styisme/watchsend)，共享协议思路但代码互不依赖。相关文档：[README](README.md) | [CHANGELOG](CHANGELOG.md) | [AI 生成声明](docs/AI_DISCLOSURE.md) | [开发约束](docs/DEVELOPMENT_CONSTRAINTS.md) | [AI 开发规范](docs/AI-DEVELOPMENT-GUIDELINES.md)。

---

## ⚠️ 关于 AI 生成的代码

依照 [AI 开发规范](https://github.com/styisme/ai-development-guidelines)（仓库内副本：[docs/AI-DEVELOPMENT-GUIDELINES.md](docs/AI-DEVELOPMENT-GUIDELINES.md)），本项目绝大部分代码是 **AI 辅助生成** 的（尤其是协议解析、文件落盘与命名、扫描探测、跨网分块、i18n 与 CI 脚本）。

提交 PR 时你必须：

- 说明本次改动是否由 AI 生成；
- **亲自验证功能**（必须真实跑起来收发一次，不能只"编译通过/语法正确"）；
- 若你也用了 AI，请在 PR 描述里写明模型与 prompt 方向；
- 涉及**鉴权与 PIN、证书与 TLS、路径与沙箱校验、协议解析、命令执行、CI 密钥与发布脚本**的改动，需声明"已逐行人工审阅"。

---

## 本地开发

### 环境要求

| 组件 | 版本 |
|---|---|
| Python | 3.8 及以上（CI 覆盖 3.9 / 3.11 / 3.13） |
| 第三方依赖 | 无（仅标准库；`tkinter` 可选，用于文件选择框） |
| Git | 2.x |
| 操作系统 | Windows / macOS / Linux |

### 常用命令

```bash
git clone https://github.com/styisme/lspy.git
cd lspy

python lspy.py --help                     # 免安装运行
pip install .                             # 安装为 lspy 命令
python -m unittest discover -s tests -v   # 全量测试（29 例）
python scripts/sync_version.py --check    # 校验版本号与 CHANGELOG 一致
pip install pyinstaller && python scripts/build_binary.py --clean   # 打包单文件可执行程序
```

本地联调最省事的方式是起两个进程互相收发：

```bash
# 终端 A
python lspy.py serve -p 53501 --no-multicast -d ./tmp_recv
# 终端 B
python lspy.py send ./some.bin --ip 127.0.0.1:53501
```

### 云端构建与自动发版

- **CI**（`.github/workflows/ci.yml`）：push / PR 触发，在 Windows 与 Linux 上跑全量测试 + `sync_version.py --check` + 语法编译检查。
- **Release**（`.github/workflows/release.yml`）：`CHANGELOG.md` 变更推送到 `main` 后触发 —— 先在 `windows-latest` 与 `ubuntu-latest` 上分别用 PyInstaller 打出单文件可执行程序（`lspy-<版本>-windows-x64.exe` / `lspy-<版本>-linux-x86_64`），再构建 wheel 与 sdist，最后汇总全部产物、打 Tag 并发布 GitHub Release。
- **二进制命名**：由 `scripts/build_binary.py` 统一决定，版本号取自 `CHANGELOG.md`，无需手工改文件名。

本地一键构建与版本同步也可手跑：

```bash
python scripts/sync_version.py            # 把 CHANGELOG 顶部版本写入 lspy.py 与 pyproject.toml
python -m build                           # 需要 build 包；CI 内完成
python scripts/build_binary.py --clean    # 需要 pyinstaller；产物在 dist/
```

> Linux 上打包若要保留 tkinter 文件选择器，需先 `sudo apt-get install -y python3-tk`；缺失时脚本自动跳过 `--hidden-import tkinter`，二进制里降级为手输路径。

---

## 项目结构

```text
lspy/
├── lspy.py                     # 单文件主程序（CLI + HTTP 服务 + 发送端 + 跨网 + i18n）
├── tests/
│   └── test_lspy.py            # unittest：单元 + 端到端收发
├── scripts/
│   ├── sync_version.py         # 从 CHANGELOG 提取版本并注入（唯一版本来源）
│   ├── extract_release_notes.py # 生成发版用的版本号与 Release Notes
│   └── build_binary.py         # 用 PyInstaller 打包单文件可执行程序
├── docs/
│   ├── AI_DISCLOSURE.md        # AI 生成声明
│   ├── DEVELOPMENT_CONSTRAINTS.md  # 开发环境约束
│   └── AI-DEVELOPMENT-GUIDELINES.md # AI 开发规范（上游副本）
├── .github/
│   ├── workflows/ci.yml        # 测试流水线
│   ├── workflows/release.yml   # 自动发版
│   └── PULL_REQUEST_TEMPLATE.md
├── README.md / README_EN.md / README_*.md   # 10 语言文档
├── CHANGELOG.md                # 版本唯一来源
├── CONTRIBUTING.md / CONTRIBUTING_EN.md
├── LICENSE / LICENSE-LocalSend
└── pyproject.toml
```

`lspy.py` 内部分区（自上而下）：常量与配置 → 日志与 stdio → i18n → 工具函数（文件名净化、唯一路径、进度条、HTTP opener）→ 发现（组播 / 广播 / HTTP 扫描）→ `LspyServer`（HTTP 处理与协商）→ 发送端 → 跨网 → 历史与证书 → 交互菜单 → `main`。

---

## 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/v1.0.0/)：

```
<type>(<scope>): <subject>
```

### 允许的类型

- `feat`：新功能
- `fix`：缺陷修复
- `docs`：仅文档
- `style`：格式调整（不改逻辑）
- `refactor`：重构
- `perf`：性能优化
- `test`：测试相关
- `build`：构建/打包
- `ci`：CI 配置
- `chore`：杂项（版本号、.gitignore）

### 常用 scope

- `core`：协议核心与协商逻辑
- `http`：HTTP 服务端 / 客户端
- `discovery`：组播、广播、深度扫描
- `transfer`：发送、接收、落盘、续传
- `security`：PIN、黑名单、扩展名过滤、路径校验、TLS
- `cross`：ntfy.sh 跨网
- `web`：Web 状态页
- `cli`：命令行与交互菜单
- `i18n`：多语言

### 示例

```
feat(transfer): resume interrupted uploads from on-disk offset
fix(security): refuse zip entries that escape the target directory
ci: verify CHANGELOG version consistency before packaging
docs: restructure README into the multi-language suite
```

使用 AI 辅助的提交推荐在正文末行标注 `ai-assisted`（规范 3.5）。

---

## 分支模型

| 分支 | 用途 |
|---|---|
| `main` | 稳定分支（默认） |
| `feat/xxx` | 功能分支 |
| `fix/xxx` | 修复分支 |
| `docs/xxx` | 文档分支 |

---

## Pull Request 流程

1. Fork 仓库（或直接在分支上改）
2. 建分支：`git checkout -b feat/your-feature`
3. 改代码，并在本地跑通测试 + 真实收发一次
4. 按 Conventional Commits 提交
5. Push 并开 PR
6. 等 CI 全绿 + 人工 Review

### PR 描述应包含

```markdown
## 改动内容
简要说明做了什么

## 改动类型
- [ ] feat / fix / refactor / docs / chore

## 关联 Issue
Closes #123

## 验证方式
- [ ] 本地 `python -m unittest discover -s tests -v` 全绿
- [ ] 真实收发验证（操作系统 + 对端 LocalSend 版本）
- [ ] CI 通过

## AI 参与
- [ ] 是（请说明模型与人工验证内容）
- [ ] 否
```

> 仓库已提供 `.github/PULL_REQUEST_TEMPLATE.md`，其中包含 AI 开发规范要求的"已说明 AI 参与程度""已在目标平台编译/运行""安全敏感代码已审阅"三项必勾检查。

---

## 提交 Issue

### Bug 报告

请提供：

- **操作系统与 Python 版本**
- **对端设备型号与 LocalSend 版本**
- **复现步骤**
- **期望行为** vs **实际行为**
- 日志（`~/.lspy/lspy.log` 相关片段），必要时附 `lspy --version` 与 `lspy info` 输出

### 功能请求

- 说明使用场景（例如"无组播的企业网络里怎么发现设备"）
- 如可能，给出参考实现或协议文档链接

---

## 版本规则（严格自动化）

遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)：

| 改动性质 | 版本位 |
|---|---|
| 不兼容变更（协议行为、配置键、CLI 参数） | **MAJOR** |
| 向后兼容的新功能 | **MINOR** |
| 缺陷修复 | **PATCH** |

⚠️ **重要**：版本号唯一来源是 `CHANGELOG.md`。**不要手改 `lspy.py` 的 `VERSION` 或 `pyproject.toml` 的 `version`**，只改 CHANGELOG（例如 `## [1.20.0] - 2026-12-01`），再由 `scripts/sync_version.py` 注入，CI 会校验一致性。

---

## 配置项

配置文件：`~/.lspy/config.json`，用 `lspy config --set k=v` 修改。

| 键 | 默认 | 说明 |
|---|---|---|
| `alias` | 主机名 | 对外显示的设备名 |
| `port` | `53317` | 服务端口；`0` 表示随机可用端口 |
| `save_dir` | `./downloads` | 接收目录 |
| `pin` | 无 | 固定 PIN；设置后接收端要求校验 |
| `auto_accept` | `true` | 自动接受，不弹确认 |
| `filter_ext` | `exe,bat,cmd,vbs,sh` | 拒收的扩展名（逐文件跳过） |
| `whitelist` / `blacklist` | 空 | 指纹名单，支持前缀匹配；黑名单优先 |
| `auto_accept_whitelist` | `false` | 白名单设备自动接受 |
| `use_https` | `false` | 收发是否走 HTTPS |
| `web_enable` | `true` | 是否提供 Web 状态页 |
| `organize_by_type` | `true` | 按文件类型分目录保存 |
| `history_enable` | `true` | 是否写 `history.jsonl` |
| `auto_unzip` | `false` | 接收完成后自动解压（仍走 Zip Slip 校验） |
| `open_after_receive` | `false` | 接收完成后用系统程序打开 |
| `lang` | `auto` | 界面语言：`auto` 或 `zh/zh_TW/en/ja/ko/de/fr/es/ru/pt` |
| `ntfy_topic` | `oldsend_cross_` | 跨网 ntfy 话题前缀 |
| `log_level` | `INFO` | `DEBUG/INFO/WARNING/ERROR` |
| `fingerprint` | 自动生成 | 设备指纹，删除后自动重建 |

---

## 协议实现

服务端路由（前缀 `/api/localsend/v2`，`/v1` 同样挂载）：

| 端点 | 方法 | 作用 |
|---|---|---|
| `/info` | GET | 设备信息（返回实际绑定端口） |
| `/register` | POST | v2.1 预注册 |
| `/prepare-upload` | POST | v2 上传前协商 |
| `/send-request` | POST | v2.1 发送请求 |
| `/upload` / `/send` | POST | 分块接收（`fileId` / `sessionId` + `token`） |
| `/cancel` | POST | 取消会话，清理半成品 |

发送端优先 `send-request` → `send`；遇 404/405 回退 `prepare-upload` → `upload`。跨网通道用 ntfy 消息 JSON，分块 2400 字节，尾包携带 `__SHA256__:<hash>:<len>`。

Web 分享页（`web_enable` 关闭时整组 404；设了 PIN 时全部要求 `pin` 查询参数或 `X-LocalSend-Pin` 请求头）：

| 端点 | 方法 | 作用 |
|---|---|---|
| `/`、`/index.html` | GET | 单页分享界面：上传 / 下载 / 文本三页签 + 设备信息 + 最近接收 |
| `/web/info` | GET | 别名、端口、版本、是否要求 PIN、已接收文件数 |
| `/web/files` | GET | 接收目录内的文件列表（相对路径、大小、mtime，上限 500 条） |
| `/web/download?name=` | GET | 流式下载单个文件；`name` 经 `web_safe_path` 校验，`..`/绝对路径一律拒 |
| `/web/upload?name=` | POST | 原始 body 落盘到接收目录，复用 `safe_filename` + `unique_path` + 扩展名黑名单，单次上限 2 GiB |
| `/web/text` | POST | JSON `{text}`：写入本机剪贴板；无剪贴板时落盘为 `web-text-<时间>.txt` |
| `/web/clipboard` | GET | 读本机剪贴板的纯文本 |


---

## 故障排查

**Q：手机扫描不到电脑？**
A：按顺序排查：① 放通 TCP/UDP `53317`（Windows 防火墙首次运行会弹窗）；② 路由器是否开启 AP 隔离；③ 用 `lspy scan -t 5` 看是否能通过 HTTP 深扫发现；④ 企业网络常封组播，此时用 `--ip` 直连最稳。

**Q：对方一直 401 / 提示需要 PIN？**
A：接收端设置了 `pin`。发送时加 `--pin`，或在对方 `lspy config --set pin=""` 清空。响应头 `X-LocalSend-Pin` 表示对端要求 PIN。

**Q：单个文件被拒收，整批都失败？**
A：v1.19.0 起扩展名过滤与黑名单是**逐文件**判断，只会跳过命中项；若仍整批失败，看 `lspy.log` 里的 `403` 原因（多半是该文件命中 `filter_ext`）。

**Q：同名文件会不会被覆盖？**
A：不会。落盘统一走 `safe_filename` + `unique_path`，冲突自动加 `(1)`；同名同大小也不会被当成"已接收"跳过。

**Q：中断后重传，进度为什么从中间开始？**
A：这是预期的会话内续传：按已落盘偏移继续。换新会话（重新 `prepare-upload`）则从头开始。

**Q：`lspy serve` 报端口占用？**
A：`-p 0` 或 `lspy config --set port=0` 让系统分配，`lspy info` 会显示实际绑定端口。

**Q：输出重定向到文件后中文/图标乱码？**
A：非 TTY 时程序会把 stdout/stderr 切到 UTF-8；若仍乱码，确认读取端按 UTF-8 解析（Windows 记事本需 ANSI 之外的编码设置），或先 `chcp 65001`。

**Q：发送到 HTTPS 设备失败？**
A：加 `--https`（或 `lspy config --set use_https=true`）。本实现与 LocalSend 一致，不校验证书链，自签证书可用。

**Q：`--web` 打不开页面？**
A：确认服务在跑且 `web_enable=true`，访问 `http://<绑定IP>:<端口>/`。若用了 `--no-web`，页面被显式关闭。

**Q：没有 `tkinter`，选文件对话框报错？**
A：会自动降级为手输路径；想恢复对话框请安装带 Tk 的 Python 发行版。

**Q：CI 报版本号不一致？**
A：说明 `lspy.py` / `pyproject.toml` 与 `CHANGELOG.md` 顶部版本不同。跑 `python scripts/sync_version.py` 后再提交。

---

## 许可

贡献即表示同意以 [MIT 协议](LICENSE) 授权你的代码。与 LocalSend 的协议兼容性说明见 [LICENSE-LocalSend](LICENSE-LocalSend)。
