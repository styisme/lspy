# lspy

一个与 [LocalSend](https://localsend.org/) 协议兼容的 Python 命令行文件传输工具。单文件实现、仅依赖标准库，可直接在局域网内与手机/电脑上的 LocalSend 客户端互传文件，也支持借助 ntfy.sh 做跨网中转。

```
lspy send photo.jpg --device "Pixel 7"      # 发到手机
lspy serve --web                            # 电脑收文件，并打开状态页
```

## 特性

- **协议兼容**：实现 LocalSend `v2` 的 `info / register / prepare-upload / upload / cancel`，并同时实现 `v2.1` 的 `send-request / send`；`v1` 前缀同样可用，兼容老客户端。
- **双向收发**：命令行发送（可指定设备别名、指纹或 `IP:端口`）与前台/后台接收服务。
- **发现机制**：组播 `224.0.0.167:53317` + 全网段广播 + **HTTP 深度扫描**（组播被防火墙或 AP 隔离拦截时的兜底方案），自动合并去重。
- **断点续传**：会话内重传从已落盘偏移继续，不再整文件重来；文件名冲突时自动加 `(1)` 后缀，**绝不覆盖已有同名文件**。
- **安全策略**：PIN 校验（401 + `X-LocalSend-Pin`）、指纹黑白名单、危险扩展名过滤（默认拦截 `exe,bat,cmd,vbs,sh`），文件名与解压路径均做穿越防护。
- **TLS**：`lspy cert` 生成自签证书后，收发两端都可走 HTTPS（对自签证书不校验证书链，与 LocalSend 一致）。
- **Web 状态页**：接收端内建一页 HTML（设备信息 + 最近接收记录），`--web` 自动打开。
- **跨网中转**：`cross-send / cross-recv` 以 ntfy.sh 为通道，分块带 SHA-256 校验，弱网重试。
- **10 种界面语言**：中（简/繁）、英、日、韩、德、法、西、俄、葡，默认按系统区域自动选择。

## 环境要求

- Python 3.8+（Windows / macOS / Linux 均可）
- 无第三方依赖；`tkinter` 缺失时发送向导自动降级为手输路径
- 局域网互传需放通 53317 端口（TCP 用于传输，UDP 用于发现）

## 安装

```bash
# 直接用
python lspy.py --help

# 或安装为命令（推荐）
pip install .
lspy --version
```

## 命令一览

| 命令 | 说明 |
| --- | --- |
| `lspy info` | 打印本机 LocalSend 信息（别名、指纹、端口、协议） |
| `lspy scan [-t 2] [--json]` | 发现附近设备；`--json` 输出机读结果 |
| `lspy serve [-p 53317] [-d DIR] [--pin PIN] [--auto-accept\|--confirm] [--web] [--no-multicast] [--no-web]` | 启动接收服务（前台） |
| `lspy send FILES... (--device NAME\|--ip HOST[:PORT]) [--pin PIN] [--https] [-t 3]` | 发送文件 |
| `lspy cross-send FILES... [--pin 123456]` | 跨网发送（打包后经 ntfy.sh 中转） |
| `lspy cross-recv PIN [-d DIR]` | 跨网接收 |
| `lspy history [-n 20]` | 传输历史 |
| `lspy cert` | 用 openssl 生成自签证书（写入配置目录） |
| `lspy open FILES...` | 用系统默认程序打开文件 |
| `lspy config [--show] [--set k=v] [--reset]` | 查看/修改/重置配置；不带参数进入交互式设置 |
| `lspy`（无子命令） | 交互式菜单：自动后台接收 + 扫描/发送/跨网/历史/设置 |

示例：

```bash
lspy scan --json                                   # 看有哪些设备
lspy send a.jpg b.pdf --device "Mi 14"             # 按别名发送
lspy send a.jpg --ip 192.168.1.20:53317 --pin 1234 # 按 IP + PIN 发送
lspy serve --auto-accept -d ~/Downloads/lspy       # 免确认接收
```

## 交互菜单

无子命令运行时进入菜单，序号含义：

```
1 显示本机信息   2 扫描附近设备   3 切换为前台服务（详细进度）
4 发送文件       5 跨网发送       6 跨网接收
7 历史记录       8 设置           0 退出
```

菜单启动时会自动起一个后台接收服务（受 `auto_accept` / `pin` 配置控制）；选 `3` 会先停后台服务，转前台带进度输出，退出后自动恢复后台服务。

## 配置

配置目录 `~/.lspy/`：

| 文件 | 用途 |
| --- | --- |
| `config.json` | 配置项 |
| `history.jsonl` | 传输历史（每行一条 JSON） |
| `lspy.log` | 滚动日志（512KB × 3） |
| `cert.pem` / `key.pem` | TLS 自签证书（`lspy cert` 生成） |

配置项（`lspy config --set k=v` 修改）：

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `alias` | 主机名 | 对外显示的设备名 |
| `port` | `53317` | 监听端口 |
| `save_dir` | `./downloads` | 接收保存根目录 |
| `pin` | 无 | 接收端默认 PIN |
| `auto_accept` | `true` | 是否免确认接收 |
| `auto_accept_whitelist` | `false` | 白名单设备免确认 |
| `whitelist` / `blacklist` | `[]` | 指纹白/黑名单（支持前缀匹配） |
| `filter_ext` | `exe,bat,cmd,vbs,sh` | 拒收的扩展名（逗号分隔，留空即不拦） |
| `organize_by_type` | `true` | 按类型分子目录（Pictures/Movies/Music/Apps） |
| `use_https` | `false` | 接收端启用 HTTPS（需已有证书） |
| `web_enable` | `true` | 启用 Web 状态页 |
| `ntfy_topic` | `oldsend_cross_` | 跨网中继的 ntfy 话题前缀 |
| `auto_unzip` | `false` | 收到 zip 自动解压 |
| `open_after_receive` | `false` | 接收完成后自动打开 |
| `history_enable` | `true` | 记录传输历史 |
| `lang` | `auto` | 界面语言（`zh`/`zh_TW`/`en`/`ja`/`ko`/`de`/`fr`/`es`/`ru`/`pt`） |
| `log_level` | `INFO` | 日志级别 |

## 协议实现

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/api/localsend/v2/info`、`v1/info` | GET | 返回设备信息（`port` 为实际绑定端口） |
| `/api/localsend/v2/register`、`v1/register` | POST | 接收方回执本机信息 |
| `/api/localsend/v2/prepare-upload` | POST | v2 会话协商，返回 `sessionId` / `files`(token) / `resume` |
| `/api/localsend/v2/send-request` | POST | v2.1 会话协商（语义同上） |
| `/api/localsend/v2/upload` | POST | v2 单文件上传（`sessionId&fileId&token&resume`） |
| `/api/localsend/v2/send` | POST | v2.1 单文件上传（参数同上） |
| `/api/localsend/v2/cancel` | GET/POST | 取消会话 |
| `/` | GET | Web 状态页（`web_enable=false` 时 404） |

发送端优先 `send-request`，对方返回 404/405 时自动回退到 `prepare-upload`；上传路径随之选择 `send` 或 `upload`。带 PIN 时在查询串附加 `?pin=`，接收端校验失败返回 `401` 并带 `X-LocalSend-Pin: true`。

## 目录结构

```
lspy.py            # 单文件实现（CLI + 协议服务端/客户端 + 跨网 + Web 页）
tests/test_lspy.py # 单元 + 端到端测试（stdlib unittest）
pyproject.toml     # 打包与 lspy 命令入口
README.md
CHANGELOG.md
```

## 测试

```bash
python -m unittest discover -s tests -v
```

测试覆盖：文件名净化与路径穿越、解压安全、配置与指纹稳定性、i18n 回退、`info` 端口一致性、Web 页、v2.1 全流程、PIN 校验、黑名单、扩展名过滤（部分/全部）、错误 token、cancel、端到端收发（含大文件与同名冲突）。

## 故障排查

1. **扫描不到设备**：确认在同一局域网、路由器未开 AP 隔离；Windows 防火墙需允许 Python 访问专用网络（TCP+UDP 53317）。
2. **UDP 被拦**：`lspy scan` 在组播超时后会自动做 HTTP 深度扫描；也可 `lspy scan -t 5` 延长组播等待，或用 `--ip` 直连。
3. **端口被占**：换 `-p` 或改 `port` 配置；`serve` 报错会直接说明是绑定失败。
4. **对方要 PIN**：`--pin` 传入；接收端 `--no-pin` 可忽略配置里的 PIN。
5. **HTTPS 收不到**：先 `lspy cert`，再把 `use_https` 设为 `true`；发送端加 `--https`。

## 安全说明

- 默认拦截可执行类扩展名；黑白名单按指纹匹配（也接受前缀，便于按机型批量匹配）。
- 对端文件名一律压平成 `safe_filename`，解压拒绝绝对路径、`..` 与符号链接，落盘前用 `unique_path` 规避覆盖。
- 接收端为非交互环境（stdin 非 TTY）且未开自动接收时，会拒绝请求并记日志，避免服务线程卡在 `input()`。
- 跨网通道 ntfy.sh 是公网明文服务，PIN 即话题名，**不要传输敏感数据**。
