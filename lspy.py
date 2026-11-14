#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lspy — LocalSend-compatible Python CLI (Deep Scan Edition)

单文件实现：局域网收发（v2 / v2.1 协议）、跨网中继（ntfy.sh）、
HTTP 深度扫描、断点续传、Web 状态页、TLS。

仅依赖标准库，可直接 `python lspy.py` 运行。
"""

import argparse
import base64
import concurrent.futures
import errno
import hashlib
import http.client
import http.server
import io
import json
import locale
import logging
import logging.handlers
import mimetypes
import os
import random
import shutil
import socket
import socketserver
import ssl
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

# ================== 常量 ==================
VERSION = "1.20.1"
DEFAULT_PORT = 53317
MULTICAST_GROUP = "224.0.0.167"
V2_PREFIX = "/api/localsend/v2"
V1_PREFIX = "/api/localsend/v1"

CONFIG_DIR = Path.home() / ".lspy"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.jsonl"
LOG_FILE = CONFIG_DIR / "lspy.log"
CERT_FILE = CONFIG_DIR / "cert.pem"
KEY_FILE = CONFIG_DIR / "key.pem"

CONFIG_DEFAULTS = {
    "alias": None, "port": DEFAULT_PORT, "save_dir": "./downloads",
    "pin": None, "auto_accept": True, "ntfy_topic": "oldsend_cross_",
    "lang": "auto", "filter_ext": "exe,bat,cmd,vbs,sh",
    "whitelist": [], "blacklist": [], "auto_accept_whitelist": False,
    "use_https": False, "web_enable": True, "organize_by_type": True,
    "history_enable": True, "auto_unzip": False,
    "open_after_receive": False, "log_level": "INFO",
}

SUPPORTED_LANGS = ["zh", "zh_TW", "en", "ja", "ko", "de", "fr", "es", "ru", "pt"]
IS_IDLE = 'idlelib' in sys.modules

# ================== 日志系统 ==================
_log = logging.getLogger("lspy")

def setup_logging():
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        level = getattr(logging, str(get_config("log_level", "INFO")).upper(), logging.INFO)
        _log.setLevel(level)
        _log.handlers.clear()
        fh = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=512*1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
        _log.addHandler(fh)
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        sh.setLevel(level)
        _log.addHandler(sh)
    except Exception: pass


def _configure_stdio():
    """把 stdout/stderr 统一切到 UTF-8。

    Windows 默认代码页（cp936/cp1252）遇到 emoji 会直接抛 UnicodeEncodeError，
    重定向到文件时还会把中文与图标编坏；因此不区分 TTY，统一 reconfigure。
    """
    if IS_IDLE: return
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is None or not hasattr(stream, "reconfigure"): continue
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

# 导入即生效：CI / 测试直接实例化 LspyServer（绕过 main）时也要能安全打印图标
_configure_stdio()

# ================== i18n ==================
I18N = {
    "en": {
        "lang_name": "English", "menu_title": "lspy — LocalSend-compatible CLI",
        "menu_info": "Show device info", "menu_scan": "Scan nearby devices",
        "menu_serve": "Start receive service (foreground)", "menu_send": "Send files to device",
        "menu_cross_send": "Cross-network send (ntfy.sh)", "menu_cross_recv": "Cross-network receive (ntfy.sh)",
        "menu_history": "History", "menu_config": "Settings", "menu_exit": "Exit",
        "choose_prompt": "Select [{choices}]: ", "invalid_option": "Invalid option",
        "bye": "Bye", "scanning_short": "Scanning LAN...", "scanning_long": "Scanning LAN (timeout {t}s)...",
        "scan_none": "No devices found", "scan_found_n": "Found {n} device(s):", "found_device": "Found: {d}",
        "scan_target": "Scanning for target device...", "device_not_found": "Device not found: {n}",
        "specify_device_or_ip": "Please specify --device or --ip",
        "multicast_send_fail": "Multicast send failed: {e}", "multicast_listen_fail": "Multicast listen failed: {e}",
        "http_listening": "HTTP listening {h}:{p}", "https_listening": "HTTPS listening {h}:{p}",
        "save_dir": "Save dir: {d}", "pin_enabled": "PIN enabled: {p}", "mc_listening": "Multicast {g}:{p}",
        "mc_reply": "MC reply: {a} @ {ip}", "stopping": "Stopping...",
        "ask_receive": "From [{a}] @ {ip}: {n} file(s). Accept? [Y/n]: ",
        "session_created": "Session {s} waiting {n} file(s)", "receive_done": "Received: {f} -> {p}",
        "receive_progress": "{f}: {p}% ({r}/{t})", "write_fail": "Write failed: {e}",
        "send_preparing": "Sending {n} file(s) ({s} bytes) -> {d}", "pin_required": "Remote requires PIN (--pin)",
        "conn_fail": "Connection failed: {e}", "send_rejected": "Rejected (HTTP {c})",
        "no_session": "Invalid response: missing sessionId", "send_started": "Session {s}... uploading",
        "send_progress": "Upload: {p}% ({s}/{t})", "send_fail": "Upload failed {f}: {e}",
        "send_done": "Done {a}/{b} file(s)", "https_unsupported": "Target uses HTTPS (unsupported by send)",
        "skip_missing": "Skipping: {p}", "no_files": "No files",
        "cross_pin": "Cross PIN: {p}  (receiver: lspy cross-recv {p})", "packing": "Packing...",
        "packed": "Packed: {n} bytes", "cross_progress": "Send: {s}/{t} ({p}%)",
        "chunk_fail": "Chunk {i} failed: {e}", "cross_sent": "Sent", "listening_pin": "Listening PIN: {p}",
        "cross_recv_progress": "Received {n} bytes", "cross_timeout": "Timeout", "no_data": "No data",
        "saved": "Saved: {p} ({n} bytes)", "unzip_ok": "Extracted: {d}", "unzip_fail": "Extract failed: {e}",
        "blocked_ext": "Blocked: {f}", "blocked_list": "Blocked by blacklist: {a}",
        "invalid_port": "Invalid port", "invalid_input": "Invalid input", "index_out_of_range": "Out of range",
        "no_files_provided": "No files provided", "pin_empty": "PIN empty", "no_file_selected": "No file selected",
        "no_device_scan": "No devices, check peer service", "prompt_files": "File paths (comma-separated): ",
        "prompt_save_dir": "Save dir [{d}]: ", "prompt_pin_off": "PIN (empty=disabled): ",
        "prompt_pin_on": "PIN (empty=use {p}): ", "prompt_ask_each": "Ask each receive? [y/N] (now: {v}): ",
        "prompt_target_pin": "Target PIN (empty=none): ", "prompt_cross_pin": "PIN (empty=random): ",
        "prompt_cross_recv_pin": "6-digit PIN: ", "prompt_pick_device": "Select [1-{n}]: ",
        "pick_files_title": "Select files", "yes": "yes", "no": "no",
        "stun_probing": "Probing STUN...", "stun_result": "Public address: {r}", "stun_fail": "STUN failed: {e}",
        "history_empty": "No history", "history_entry": "[{t}] {f} ({s} bytes) receive={r}",
        "cfg_title": "Current config", "cfg_alias": "Alias", "cfg_port": "Port", "cfg_savedir": "Save dir",
        "cfg_pin": "Default PIN", "cfg_auto": "Auto-accept", "cfg_topic": "NTFY topic", "cfg_fp": "Fingerprint",
        "cfg_lang": "Language", "cfg_none": "(none)", "cfg_default": "(default)",
        "cfg_menu_alias": "Change alias", "cfg_menu_port": "Change port", "cfg_menu_savedir": "Change save dir",
        "cfg_menu_pin": "Change PIN", "cfg_menu_auto": "Toggle auto-accept", "cfg_menu_topic": "Change NTFY topic",
        "cfg_menu_regen_fp": "Regenerate fingerprint", "cfg_menu_reset": "Reset config", "cfg_menu_lang": "Change language",
        "cfg_menu_back": "Back", "cfg_prompt_alias": "New alias [{d}]: ", "cfg_prompt_port": "New port [{d}]: ",
        "cfg_prompt_savedir": "New dir [{d}]: ", "cfg_prompt_pin": "New PIN [{d}]: ",
        "cfg_prompt_topic": "New topic [{d}]: ", "cfg_confirm_reset": "Reset all? [y/N]: ",
        "cfg_reset_done": "Config reset", "cfg_not_exist": "Config not found",
        "cfg_set_done": "Set {k} = {v}", "cfg_unset_done": "Cleared {u}",
        "cfg_invalid_port": "Port 1-65535", "cfg_invalid_set": "Format: --set k=v",
        "cfg_invalid_lang": "Unsupported lang: {l}", "cfg_lang_choice": "Language [{choices}]: ",
        "cfg_file": "Config file", "help_text": "Help", "confirm_receive_30s": "Receive from [{a}]? (30s auto-reject) [Y/n]: ",
        "firewall_tip": "\n💡 提示：如果确认对方已开启服务，请检查：\n  1. Windows 防火墙是否拦截了程序（请在设置中允许 Python 通过防火墙）\n  2. 设备是否在同一局域网（路由器是否开启了 AP 隔离）\n  3. 如果仍不行，请尝试选项 4 -> 2 手动输入对方 IP 发送。\n",
        "deep_scanning": "🌐 UDP timeout, starting HTTP deep scan on {ip}.1/24 ...",
        "web_title": "lspy — receive status", "web_alias": "Alias", "web_port": "Port",
        "web_fp": "Fingerprint", "web_recent": "Recently received", "web_none": "Nothing received yet",
        "web_hint": "Keep this service running. Files sent from LocalSend are saved automatically.",
        "reg_fail": "Register with receiver failed: {e}", "register_ok": "Announced to receiver",
        "send_fallback": "Target has no v2.1 endpoint, falling back to prepare-upload",
        "files_skipped": "{n} file(s) skipped by extension policy", "https_send": "TLS enabled for target",
        "unzip_unsafe": "Extraction refused: unsafe entry {p}", "http_scan_https": "Probing HTTPS hosts too",
        "bound_port": "Bound to port {p}", "no_write_perm": "Cannot write to {p}: {e}",
        "integrity_fail": "Integrity check failed for {f}", "chunk_hash": "Chunk {i} checksum mismatch, retrying",
        "version": "Version", "web_alone": "Web page available at {u}",
        "menu_serve_fg": "Switch to foreground service (verbose progress)",
        "auto_start": "Starting background receiver...", "auto_start_fail": "Auto-start failed: {e}",
        "port_in_use": "Port {p} is unavailable: {e}",
        "port_in_use_tip": "Another LocalSend desktop app or a second lspy instance is probably holding this port. Close it, or pick another port with -p 0 / -p 53318.",
        "port_fallback": "Port {p} is taken, switched to the OS-assigned port {q} (use -p to pin one).",
        "mc_port_busy": "Multicast port 53317 is taken (usually LocalSend desktop running alongside); multicast listening skipped, HTTP discovery still works. Add --no-multicast to silence this.",
        "fg_hint": "Foreground receiver running, Ctrl+C stops it and returns to the menu",
        "send_how": "1. Auto-scan nearby devices\n2. Enter IP manually", "send_choose": "Select [1-2]: ",
        "prompt_ip": "Target IP (e.g. 192.168.1.10): ", "input_error": "Input error: {e}",
        "menu_banner": "lspy — LocalSend-compatible CLI",
        "menu_devices": "Nearby devices", "no_devices_yet": "Not scanned yet, choose 2 to scan",
    },
    "zh": {
        "lang_name": "简体中文", "menu_title": "lspy — LocalSend 兼容命令行工具",
        "menu_info": "显示本机信息", "menu_scan": "扫描附近设备", "menu_serve": "启动接收服务（前台）",
        "menu_send": "发送文件到设备", "menu_cross_send": "跨网发送（ntfy.sh）", "menu_cross_recv": "跨网接收（ntfy.sh）",
        "menu_history": "历史记录", "menu_config": "设置", "menu_exit": "退出",
        "choose_prompt": "请选择 [{choices}]: ", "invalid_option": "无效选项", "bye": "已退出",
        "scanning_short": "正在扫描局域网...", "scanning_long": "扫描网络（超时 {t}s）...",
        "scan_none": "未发现设备", "scan_found_n": "共发现 {n} 个设备：", "found_device": "发现：{d}",
        "scan_target": "扫描目标...", "device_not_found": "未找到：{n}", "specify_device_or_ip": "请指定 --device 或 --ip",
        "multicast_send_fail": "组播发送失败：{e}", "multicast_listen_fail": "组播监听失败：{e}",
        "http_listening": "HTTP 监听 {h}:{p}", "https_listening": "HTTPS 监听 {h}:{p}",
        "save_dir": "保存目录：{d}", "pin_enabled": "PIN：{p}", "mc_listening": "组播监听 {g}:{p}",
        "mc_reply": "组播响应：{a} @ {ip}", "stopping": "正在停止...",
        "ask_receive": "来自 [{a}] @ {ip} 的 {n} 个文件，接收？[Y/n]：",
        "session_created": "会话 {s} 等待 {n} 个文件", "receive_done": "已接收：{f} -> {p}",
        "receive_progress": "{f}：{p}% ({r}/{t})", "write_fail": "写入失败：{e}",
        "send_preparing": "发送 {n} 个文件（{s} 字节）→ {d}", "pin_required": "对方需要 PIN（--pin）",
        "conn_fail": "连接失败：{e}", "send_rejected": "被拒绝（HTTP {c}）", "no_session": "响应缺少 sessionId",
        "send_started": "会话 {s}... 上传中", "send_progress": "上传：{p}% ({s}/{t})", "send_fail": "上传失败 {f}：{e}",
        "send_done": "完成 {a}/{b} 个", "https_unsupported": "目标 HTTPS（发送端暂不支持）",
        "skip_missing": "跳过：{p}", "no_files": "无文件",
        "cross_pin": "跨网 PIN：{p}（接收：lspy cross-recv {p}）", "packing": "打包中...",
        "packed": "已打包：{n} 字节", "cross_progress": "发送：{s}/{t} ({p}%)", "chunk_fail": "分块 {i} 失败：{e}",
        "cross_sent": "已发送", "listening_pin": "监听 PIN：{p}", "cross_recv_progress": "已收 {n} 字节",
        "cross_timeout": "超时", "no_data": "无数据", "saved": "已保存：{p}（{n} 字节）",
        "unzip_ok": "已解压：{d}", "unzip_fail": "解压失败：{e}", "blocked_ext": "拦截：{f}",
        "blocked_list": "黑名单拒绝：{a}", "invalid_port": "端口无效", "invalid_input": "输入无效",
        "index_out_of_range": "序号越界", "no_files_provided": "未提供文件", "pin_empty": "PIN 为空",
        "no_file_selected": "未选择文件", "no_device_scan": "未发现设备，请确认对方已启动",
        "prompt_files": "文件路径（逗号分隔）：", "prompt_save_dir": "保存目录 [{d}]: ",
        "prompt_pin_off": "PIN（留空禁用）：", "prompt_pin_on": "PIN（留空使用 {p}）：",
        "prompt_ask_each": "每次接收询问？[y/N]（当前：{v}）：", "prompt_target_pin": "目标 PIN（留空不校验）：",
        "prompt_cross_pin": "PIN（留空随机）：", "prompt_cross_recv_pin": "6 位 PIN：",
        "prompt_pick_device": "选择 [1-{n}]: ", "pick_files_title": "选择文件", "yes": "是", "no": "否",
        "stun_probing": "STUN 探测...", "stun_result": "公网地址：{r}", "stun_fail": "STUN 失败：{e}",
        "history_empty": "无历史记录", "history_entry": "[{t}] {f}（{s} 字节）receive={r}",
        "cfg_title": "当前配置", "cfg_alias": "别名", "cfg_port": "端口", "cfg_savedir": "保存目录",
        "cfg_pin": "默认 PIN", "cfg_auto": "自动接受", "cfg_topic": "NTFY 话题", "cfg_fp": "指纹",
        "cfg_lang": "语言", "cfg_none": "（未启用）", "cfg_default": "（默认）",
        "cfg_menu_alias": "修改别名", "cfg_menu_port": "修改端口", "cfg_menu_savedir": "修改保存目录",
        "cfg_menu_pin": "修改 PIN", "cfg_menu_auto": "切换自动接受", "cfg_menu_topic": "修改 NTFY 话题",
        "cfg_menu_regen_fp": "重新生成指纹", "cfg_menu_reset": "重置全部", "cfg_menu_lang": "修改语言",
        "cfg_menu_back": "返回", "cfg_prompt_alias": "新别名 [{d}]: ", "cfg_prompt_port": "新端口 [{d}]: ",
        "cfg_prompt_savedir": "新目录 [{d}]: ", "cfg_prompt_pin": "新 PIN [{d}]: ",
        "cfg_prompt_topic": "新话题 [{d}]: ", "cfg_confirm_reset": "确认重置？[y/N]：",
        "cfg_reset_done": "已重置", "cfg_not_exist": "配置文件不存在", "cfg_set_done": "已设置 {k} = {v}",
        "cfg_unset_done": "已取消 {u}", "cfg_invalid_port": "端口 1-65535", "cfg_invalid_set": "格式：--set k=v",
        "cfg_invalid_lang": "不支持：{l}", "cfg_lang_choice": "语言 [{choices}]: ", "cfg_file": "配置文件",
        "help_text": "帮助", "confirm_receive_30s": "接收 [{a}]？（30s 自动拒绝）[Y/n]：",
        "firewall_tip": "\n💡 提示：如果确认对方已开启服务，请检查：\n  1. Windows 防火墙是否拦截了程序（请在设置中允许 Python 通过防火墙）\n  2. 设备是否在同一局域网（路由器是否开启了 AP 隔离）\n  3. 如果仍不行，请尝试选项 4 -> 2 手动输入对方 IP 发送。\n",
        "deep_scanning": "🌐 UDP 扫描超时，正在启动 HTTP 深度扫描网段 {ip}.1/24 ...",
        "web_title": "lspy — 接收状态", "web_alias": "别名", "web_port": "端口", "web_fp": "指纹",
        "web_recent": "最近接收", "web_none": "暂无接收记录",
        "web_hint": "保持服务运行，LocalSend 发来的文件会自动保存。",
        "reg_fail": "向接收端注册失败：{e}", "register_ok": "已向接收端广播身份",
        "send_fallback": "对方不支持 v2.1 接口，回退到 prepare-upload",
        "files_skipped": "因扩展名策略跳过 {n} 个文件", "https_send": "已对目标启用 TLS",
        "unzip_unsafe": "解压被拒绝：非法条目 {p}", "http_scan_https": "同时探测 HTTPS 主机",
        "bound_port": "已绑定端口 {p}", "no_write_perm": "无法写入 {p}：{e}",
        "integrity_fail": "{f} 完整性校验失败", "chunk_hash": "分块 {i} 校验失败，重试中",
        "version": "版本", "web_alone": "网页界面：{u}",
        "menu_serve_fg": "切换为前台服务（详细进度）",
        "auto_start": "正在自动启动后台接收服务...", "auto_start_fail": "自动启动失败：{e}",
        "port_in_use": "端口 {p} 不可用：{e}",
        "port_in_use_tip": "通常是本机已有 LocalSend 桌面版或另一个 lspy 实例占用了该端口。请关掉它，或用 -p 0 / -p 53318 换一个端口。",
        "port_fallback": "端口 {p} 已被占用，已改用系统分配的端口 {q}（如需固定请用 -p 指定）。",
        "mc_port_busy": "组播端口 53317 已被占用（通常是与 LocalSend 桌面版共存）；已跳过组播监听，HTTP 扫描发现仍可用。加 --no-multicast 可关闭该提示。",
        "fg_hint": "前台接收已启动，按 Ctrl+C 停止并返回菜单",
        "send_how": "1. 自动扫描附近设备\n2. 手动输入 IP 地址", "send_choose": "请选择 [1-2]: ",
        "prompt_ip": "目标 IP（如 192.168.1.10）：", "input_error": "输入错误：{e}",
        "menu_banner": "lspy — LocalSend 兼容命令行工具",
        "menu_devices": "附近设备", "no_devices_yet": "尚未扫描，选择 2 开始扫描",
    },
}
for lg in ["zh_TW", "ja", "ko", "de", "fr", "es", "ru", "pt"]:
    if lg not in I18N: I18N[lg] = dict(I18N["en"])

_current_lang = "en"

def _normalize_lang(code):
    if not code: return None
    code = code.strip().lower().replace("-", "_")
    if not code or code in ("c", "posix"): return None
    if code.startswith("zh"):
        if any(x in code for x in ("tw", "hk", "mo", "hant")): return "zh_TW"
        return "zh"
    for prefix, lang in (("ja", "ja"), ("ko", "ko"), ("de", "de"), ("fr", "fr"), ("es", "es"), ("ru", "ru"), ("pt", "pt"), ("en", "en")):
        if code.startswith(prefix): return lang
    return None

def _lang_from_env():
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var)
        if v:
            for part in v.split(":"):
                n = _normalize_lang(part)
                if n: return n
    return None

def _lang_from_locale():
    try:
        loc = locale.getlocale()[0] or locale.getdefaultlocale()[0]
        return _normalize_lang(loc)
    except Exception: return None

def _lang_from_windows():
    if sys.platform != "win32": return None
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\International")
        try: loc = winreg.QueryValueEx(k, "LocaleName")[0]
        finally: k.close()
        return _normalize_lang(loc)
    except Exception: return None

def detect_lang():
    forced = get_config("lang")
    if forced and forced not in ("auto", ""):
        n = _normalize_lang(forced)
        if n: return n
    return _lang_from_env() or _lang_from_windows() or _lang_from_locale() or "en"

def init_lang():
    global _current_lang
    _current_lang = detect_lang()
    return _current_lang

def t(key, **kwargs):
    s = I18N.get(_current_lang, {}).get(key)
    if s is None: s = I18N["en"].get(key, key)
    if kwargs:
        try: return s.format(**kwargs)
        except Exception: return s
    return s

# ================== 配置 ==================
def load_config():
    if CONFIG_FILE.exists():
        try: return json.loads(CONFIG_FILE.read_text("utf-8"))
        except Exception: pass
    return {}

def save_config(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")

def get_config(key, default=None):
    cfg = load_config()
    if key in cfg: return cfg[key]
    if key in CONFIG_DEFAULTS: return CONFIG_DEFAULTS[key]
    return default

def set_config(key, value):
    cfg = load_config()
    if value is None or value == []: cfg.pop(key, None)
    else: cfg[key] = value
    if "fingerprint" not in cfg: cfg["fingerprint"] = _gen_fp()
    save_config(cfg)

def reset_config():
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
        return True
    return False

def _gen_fp():
    return hashlib.sha1(f"{time.time()}-{random.random()}-{socket.gethostname()}".encode()).hexdigest()

def get_fingerprint():
    cfg = load_config()
    fp = cfg.get("fingerprint")
    if not fp:
        fp = _gen_fp()
        cfg["fingerprint"] = fp
        save_config(cfg)
    return fp

def get_alias():
    a = get_config("alias")
    return a or socket.gethostname()

def build_self_info(port=None, protocol=None, download=False):
    """构造对外广播的本机信息；port/protocol 用于反映实际监听配置。"""
    return {
        "alias": get_alias(), "version": VERSION,
        "deviceModel": f"Python {sys.version.split()[0]} on {sys.platform}",
        "deviceType": "desktop", "fingerprint": get_fingerprint(),
        "port": int(port if port is not None else get_config("port")),
        "protocol": protocol or ("https" if get_config("use_https") else "http"),
        "download": bool(download),
    }

def ntfy_base():
    return f"https://ntfy.sh/{get_config('ntfy_topic')}"

# ================== 历史 & 剪贴板 ==================
def append_history(filename, path, size, received):
    if not get_config("history_enable"): return
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "file": filename,
                 "path": str(path), "size": size, "receive": received}
        with open(HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e: _log.warning("history write: %s", e)

def read_history(n=20):
    if not HISTORY_FILE.exists(): return []
    try:
        lines = HISTORY_FILE.read_text("utf-8").splitlines()
        out = []
        for line in lines[-n:]:
            if line.strip():
                try: out.append(json.loads(line))
                except Exception: pass
        return list(reversed(out))
    except Exception: return []

# ================== 文件处理 ==================
_ILLEGAL_NAME_CHARS = '<>:"|?*'


def safe_filename(name, fallback="unnamed"):
    """把对端给出的文件名压平成安全的本地文件名，阻断目录穿越与 Windows 非法字符。"""
    raw = str(name or "").replace("\\", "/").replace("\x00", "")
    base = raw.split("/")[-1].strip()
    for ch in _ILLEGAL_NAME_CHARS:
        base = base.replace(ch, "_")
    base = base.strip(" .")
    if base in ("", ".", "..") or base.lower().startswith(("con", "prn", "aux", "nul")):
        base = f"{fallback}_{int(time.time() * 1000) % 100000}"
    while len(base.encode("utf-8")) > 200 and len(base) > 1:
        stem, ext = os.path.splitext(base)
        base = f"{stem[:max(1, len(stem) - 1)]}{ext}"
    return base


def unique_path(directory, name):
    """返回一个不存在的目标路径；绝不覆盖或复用已有文件。"""
    target = Path(directory) / name
    if not target.exists(): return target
    stem, ext = os.path.splitext(name)
    for i in range(1, 10000):
        candidate = Path(directory) / f"{stem} ({i}){ext}"
        if not candidate.exists(): return candidate
    return Path(directory) / f"{stem} ({int(time.time())}){ext}"


def choose_target_dir(filename, base_dir):
    """按配置决定落地目录。始终尊重用户指定的保存目录，类型分目录均在其下。"""
    base = Path(base_dir).expanduser()
    name = safe_filename(filename)
    if not get_config("organize_by_type"): return base, name
    mime, _ = mimetypes.guess_type(name)
    if not mime: mime = "application/octet-stream"
    if mime.startswith("image/"): sub = "Pictures"
    elif mime.startswith("video/"): sub = "Movies"
    elif mime.startswith("audio/"): sub = "Music"
    elif name.lower().endswith(".apk"): sub = "Apps"
    else: sub = ""
    return (base / sub if sub else base), name

def safe_unzip(zip_path, out_dir):
    """安全解压：拒绝绝对路径、`..` 穿越与符号链接条目，失败时打印原因。"""
    try:
        zip_path = Path(zip_path); out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        canonical = out_dir.resolve()
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                m = info.filename
                if m.startswith(("/", "\\")) or (len(m) > 1 and m[1] == ":"):
                    print("❌ " + t("unzip_unsafe", p=m)); return False
                parts = Path(m).parts
                if any(p in ("..",) for p in parts):
                    print("❌ " + t("unzip_unsafe", p=m)); return False
                # 符号链接（Unix 模式 0xA000）一律拒绝，避免写入任意文件
                if (info.external_attr >> 16) & 0xF000 == 0xA000:
                    print("❌ " + t("unzip_unsafe", p=m)); return False
                target = (out_dir / m).resolve()
                if os.path.commonpath([str(canonical), str(target)]) != str(canonical):
                    print("❌ " + t("unzip_unsafe", p=m)); return False
                if m.endswith("/"): target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(m) as src, open(target, "wb") as dst: shutil.copyfileobj(src, dst)
        return True
    except Exception as e:
        print("❌ " + t("unzip_fail", e=e)); return False

def _progress_line(arrow, msg, pct, every=10):
    """进度输出：TTY 用 \\r 覆盖同一行；重定向到文件时每 every% 打印一行，避免刷屏。"""
    if sys.stdout.isatty() and not IS_IDLE:
        print(f"\r  {arrow}  {msg}", end="", flush=True)
    elif pct == 100 or pct % every == 0:
        print(f"  {arrow}  {msg}", flush=True)


def _open_path(path):
    try:
        if sys.platform == "win32": os.startfile(str(path))
        elif sys.platform == "darwin": subprocess.Popen(["open", str(path)])
        else: subprocess.Popen(["xdg-open", str(path)])
    except Exception: pass

# ================== 安全策略 ==================
def _fingerprint_of(peer_ip, info):
    return (info.get("fingerprint", "") if info else "") or peer_ip

def _is_blocked_ext(filename):
    exts = get_config("filter_ext", "") or ""
    if not exts: return False
    return any(filename.lower().endswith("." + ext.strip()) for ext in exts.split(",") if ext.strip())

def _is_blacklisted(fp):
    return any(fp == x or fp.startswith(x) for x in (get_config("blacklist") or []) if x)

def _is_whitelisted(fp):
    return any(fp == x or fp.startswith(x) for x in (get_config("whitelist") or []) if x)

# ================== 设备模型 & 扫描 ==================
class Device:
    def __init__(self, alias, ip, port=DEFAULT_PORT, version="", fingerprint="", deviceModel="", deviceType="desktop", https=False):
        self.alias = alias; self.ip = ip; self.port = port; self.version = version
        self.fingerprint = fingerprint; self.deviceModel = deviceModel
        self.deviceType = deviceType; self.https = https
    @classmethod
    def from_json(cls, o, ip):
        return cls(alias=o.get("alias", "unknown"), ip=ip, port=int(o.get("port", DEFAULT_PORT)),
                   version=o.get("version", ""), fingerprint=o.get("fingerprint", ""),
                   deviceModel=o.get("deviceModel", ""), deviceType=o.get("deviceType", "desktop"),
                   https=(o.get("protocol", "http").lower() == "https"))
    def url(self, path):
        host = f"[{self.ip}]" if ":" in self.ip and not self.ip.startswith("[") else self.ip
        return f"{'https' if self.https else 'http'}://{host}:{self.port}{path}"
    def __str__(self):
        extra = f" v{self.version}" if self.version else ""
        proto = "https" if self.https else "http"
        return f"{self.alias} @ {self.ip}:{self.port} [{self.deviceType}]{extra} ({proto})"

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def local_ipv4_addresses():
    """尽力枚举本机所有非回环 IPv4（多网卡/多网段时深度扫描才能覆盖）。"""
    found = set()
    try:
        primary = get_local_ip()
        if primary and primary != "127.0.0.1": found.add(primary)
    except Exception: pass
    try:
        for entry in socket.getaddrinfo(socket.gethostname(), 0, socket.AF_INET):
            ip = entry[4][0]
            if ip and not ip.startswith("127.") and ip not in ("0.0.0.0",):
                found.add(ip)
    except Exception: pass
    return sorted(found)


def scan_network(timeout=2.0, verbose=True, extra_hosts=None):
    """组播 + 广播探测局网设备。extra_hosts 用于手动追加待探测地址。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.5)
    self_info = build_self_info()
    payload = json.dumps(self_info).encode("utf-8")

    targets = [(MULTICAST_GROUP, DEFAULT_PORT), ("255.255.255.255", DEFAULT_PORT)]
    for local_ip in local_ipv4_addresses():
        parts = local_ip.split(".")
        if len(parts) == 4:
            targets.append((f"{parts[0]}.{parts[1]}.{parts[2]}.255", DEFAULT_PORT))
    for host in (extra_hosts or []):
        targets.append((host, DEFAULT_PORT))

    for target in targets:
        try: sock.sendto(payload, target)
        except Exception: pass

    devices = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        try: data, addr = sock.recvfrom(65535)
        except socket.timeout: continue
        except Exception: break

        try: obj = json.loads(data.decode("utf-8", errors="ignore"))
        except Exception: continue
        if not isinstance(obj, dict): continue
        if obj.get("fingerprint") == self_info["fingerprint"]: continue

        try: d = Device.from_json(obj, addr[0])
        except Exception: continue
        if f"{d.ip}:{d.port}" not in devices:
            devices[f"{d.ip}:{d.port}"] = d
            if verbose: print(f"  ✅ {t('found_device', d=d)}")

    sock.close()
    return list(devices.values())

# --- HTTP 深度扫描（专治 UDP/组播被防火墙或 AP 隔离拦截） ---
def http_scan(ip_or_host, timeout=1.0, port=None, hosts=None, announce=True):
    """对给定网段（或主机列表）并发探测 /info 接口。"""
    port = int(port if port is not None else get_config("port"))
    candidates = list(hosts or [])
    label = ".".join(str(ip_or_host).split(".")[:3]) if ip_or_host else "*"
    if ip_or_host and ip_or_host.count(".") == 3:
        base_ip = ".".join(ip_or_host.split(".")[:3])
        candidates.extend(f"{base_ip}.{i}" for i in range(1, 255))
    elif ip_or_host:
        candidates.append(ip_or_host)

    devices = []

    def probe(ip):
        for scheme in ("http", "https"):
            url = f"{scheme}://{ip}:{port}{V2_PREFIX}/info"
            try:
                ctx = ssl._create_unverified_context() if scheme == "https" else None
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                    if resp.status == 200:
                        o = json.loads(resp.read().decode("utf-8"))
                        d = Device.from_json(o, ip)
                        d.https = d.https or scheme == "https"
                        d.port = port
                        return d
            except Exception:
                continue
        return None

    if announce: print("\n" + t("deep_scanning", ip=label))
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
        futures = [pool.submit(probe, ip) for ip in candidates]
        for f in concurrent.futures.as_completed(futures):
            d = f.result()
            if d and d.fingerprint != get_fingerprint():
                devices.append(d)
                if announce: print(f"  ✅ {t('found_device', d=d)}")
    return devices

# ================== 核心：抑制异常 ==================
class _Session:
    def __init__(self, sid, peer_ip, alias=""):
        self.session_id = sid; self.peer_ip = peer_ip; self.alias = alias
        self.files = {}; self.done = set(); self.created = time.time()

class _ThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True; daemon_threads = True
    def handle_error(self, request, client_address):
        exc_type, _, _ = sys.exc_info()
        if exc_type in (ConnectionResetError, ConnectionAbortedError, BrokenPipeError): return
        super().handle_error(request, client_address)

class LspyServer:
    def __init__(self, host="0.0.0.0", port=None, save_dir=None, auto_accept=None, pin=None,
                 verbose=False, multicast=True, protocol=None, web_enable=None):
        self.host = host
        self.port = int(port if port is not None else get_config("port"))
        self.bound_port = self.port
        self.save_dir = Path(save_dir if save_dir else get_config("save_dir")).expanduser()
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print("❌ " + t("no_write_perm", p=self.save_dir, e=e)); raise
        self.auto_accept = auto_accept if auto_accept is not None else get_config("auto_accept")
        self.pin = pin; self.verbose = verbose
        self.sessions = {}; self.lock = threading.Lock()
        self.httpd = None; self._mc_running = True
        self.multicast = bool(multicast)
        self.web_enable = get_config("web_enable") if web_enable is None else bool(web_enable)
        if protocol == "https": self._use_https = CERT_FILE.exists() and KEY_FILE.exists()
        else: self._use_https = bool(protocol is None and get_config("use_https")
                                     and CERT_FILE.exists() and KEY_FILE.exists())

    def _ask_receive(self, alias, peer_ip, count):
        """人工确认接收；无法交互（非终端）时直接拒绝，避免线程阻塞。"""
        if not sys.stdin or not sys.stdin.isatty():
            _log.warning("non-interactive stdin: rejecting incoming request (use --auto-accept)")
            return False
        try:
            ans = input("\n" + t("ask_receive", a=alias, ip=peer_ip, n=count)).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return ans not in ("n", "no", "non", "nein", "нет", "não", "아니오", "いいえ")

    def _register_files(self, files, peer_ip, alias):
        sid = self._gen_session_id(); sess = _Session(sid, peer_ip, alias)
        tokens, resume = {}, {}
        for fid, meta in files.items():
            fname = meta.get("fileName", fid)
            try: size = int(meta.get("size", -1))
            except (TypeError, ValueError): size = -1
            token = self._gen_token()
            tdir, safe_name = choose_target_dir(fname, self.save_dir)
            try: tdir.mkdir(parents=True, exist_ok=True)
            except OSError as e: raise OSError(t("no_write_perm", p=tdir, e=e))
            # unique_path 保证永不覆盖既有文件，也避免“同名同大小即视为已完成”的静默跳过
            target = unique_path(tdir, safe_name)
            sess.files[fid] = {"fileName": fname, "size": size, "token": token,
                               "path": target, "received": 0}
            tokens[fid] = token; resume[fid] = 0
        with self.lock: self.sessions[sid] = sess
        print(f"\n📥 {t('session_created', s=sid[:8], n=len(files))}")
        return sid, tokens, resume

    def _post_process(self, target):
        """接收完成后的可选动作：自动解压 zip / 自动打开文件；失败只记日志，不影响主流程。"""
        try:
            target = Path(target)
            if get_config("auto_unzip") and target.suffix.lower() == ".zip":
                out_dir = unique_path(target.parent, target.stem)
                if safe_unzip(target, out_dir):
                    print("✅ " + t("unzip_ok", d=Path(out_dir).resolve()))
            if get_config("open_after_receive"):
                _open_path(target)
        except Exception as e:
            _log.warning("post-process failed: %s", e)

    def _web_page_html(self):
        import html as _html
        info = build_self_info(port=self.bound_port,
                               protocol="https" if self._use_https else "http")
        rows = []
        for e in read_history(30):
            rows.append(
                "<tr><td>{}</td><td>{}</td><td><code>{}</code></td></tr>".format(
                    _html.escape(str(e.get("time", ""))),
                    _html.escape(str(e.get("file", ""))),
                    _html.escape(str(e.get("path", "")))))
        body = "".join(rows) or f"<tr><td colspan=3>{_html.escape(t('web_none'))}</td></tr>"
        title = _html.escape(t("web_title"))
        return """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
body{{font-family:system-ui,Segoe UI,sans-serif;max-width:820px;margin:0 auto;padding:24px;background:#f7f8fa;color:#1f2430}}
h1{{font-size:20px;margin:0 0 16px}} .card{{background:#fff;border:1px solid #e6e8eb;border-radius:12px;padding:18px;margin-bottom:16px}}
.k{{display:inline-block;min-width:96px;color:#6b7280}} table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;padding:8px;border-bottom:1px solid #eef0f3;font-size:13px}}
code{{color:#4b5563;font-size:12px}} .muted{{color:#6b7280;font-size:12px}}
</style></head><body>
<h1>{title}</h1>
<div class="card">
<div><span class="k">{alias}</span>{alias_v}</div>
<div><span class="k">{port}</span>{port_v}</div>
<div><span class="k">{fp}</span><code>{fp_v}</code></div>
<div><span class="k">ver</span>{ver}</div>
<div class="muted" style="margin-top:12px">{hint}</div>
</div>
<div class="card"><h1 style="font-size:16px">{recent}</h1>
<table><thead><tr><th>Time</th><th>File</th><th>Path</th></tr></thead><tbody>{body}</tbody></table>
</div></body></html>""".format(
            title=title, alias=t("web_alias"), alias_v=_html.escape(str(info["alias"])),
            port=t("web_port"), port_v=info["port"], fp=t("web_fp"),
            fp_v=_html.escape(str(info["fingerprint"])[:32]),
            ver=_html.escape(VERSION), hint=_html.escape(t("web_hint")),
            recent=_html.escape(t("web_recent")), body=body)

    def _gen_session_id(self): return f"{int(time.time() * 1000):x}{random.getrandbits(64):x}"
    def _gen_token(self): return f"{time.time_ns() ^ random.getrandbits(64):x}"

    def _make_handler(self):
        server = self
        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, fmt, *args): pass
            def _json(self, status, obj):
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers(); self.wfile.write(body); self.close_connection = True
            def _read_body(self):
                length = int(self.headers.get("Content-Length", "0") or 0)
                return self.rfile.read(length) if length > 0 else b""

            def _pin_ok(self, qs):
                return not server.pin or qs.get("pin", [None])[0] == server.pin

            def _unauthorized(self):
                self.send_response(401); self.send_header("X-LocalSend-Pin", "true")
                self.send_header("Content-Length", "0"); self.send_header("Connection", "close")
                self.end_headers(); self.close_connection = True

            def _html_page(self):
                body = server._web_page_html().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers(); self.wfile.write(body); self.close_connection = True

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                peer_qs = urllib.parse.parse_qs(parsed.query)
                if path in ("/", "/index.html"):
                    if not server.web_enable: self._json(404, {"error": "web disabled"}); return
                    self._html_page(); return
                if path in (f"{V2_PREFIX}/info", f"{V1_PREFIX}/info"):
                    self._json(200, build_self_info(port=server.bound_port,
                                                    protocol="https" if server._use_https else "http"))
                elif path in (f"{V2_PREFIX}/cancel", f"{V1_PREFIX}/cancel"):
                    sid = peer_qs.get("sessionId", [None])[0]
                    if sid:
                        with server.lock: server.sessions.pop(sid, None)
                    self._json(200, {})
                else: self._json(404, {"error": "not found"})

            def do_POST(self):
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                qs = urllib.parse.parse_qs(parsed.query)
                peer_ip = self.client_address[0]

                if path in (f"{V2_PREFIX}/register", f"{V1_PREFIX}/register"):
                    self._read_body()
                    self._json(200, build_self_info(port=server.bound_port,
                                                    protocol="https" if server._use_https else "http"))
                    return

                # v2.1 的 send-request 与旧版 prepare-upload 语义一致，共用处理逻辑
                if path in (f"{V2_PREFIX}/prepare-upload", f"{V1_PREFIX}/prepare-upload",
                            f"{V2_PREFIX}/send-request", f"{V1_PREFIX}/send-request"):
                    if not self._pin_ok(qs): self._unauthorized(); return
                    try: o = json.loads(self._read_body().decode("utf-8") or "{}")
                    except Exception: self._json(400, {"error": "bad request"}); return
                    if not isinstance(o, dict): self._json(400, {"error": "bad request"}); return

                    files = o.get("files") or {}; info = o.get("info") or {}
                    if not isinstance(files, dict) or not files:
                        self._json(400, {"error": "no files"}); return
                    if not isinstance(info, dict): info = {}
                    sender_alias = str(info.get("alias") or "unknown")
                    fp = _fingerprint_of(peer_ip, info)

                    if _is_blacklisted(fp):
                        print("\n⛔ " + t("blocked_list", a=sender_alias))
                        self._json(403, {"error": "blacklisted"}); return

                    accepted, skipped = {}, 0
                    for fid, f in files.items():
                        if not isinstance(f, dict): continue
                        if _is_blocked_ext(f.get("fileName", fid)): skipped += 1; continue
                        accepted[fid] = f
                    if skipped: print("\n⚠️  " + t("files_skipped", n=skipped))
                    if not accepted: self._json(403, {"error": "blocked"}); return

                    auto = server.auto_accept
                    if not auto and get_config("auto_accept_whitelist") and _is_whitelisted(fp): auto = True
                    if not auto and not server._ask_receive(sender_alias, peer_ip, len(accepted)):
                        self._json(403, {"error": "rejected"}); return

                    try: sid, tokens, resume = server._register_files(accepted, peer_ip, sender_alias)
                    except OSError as e:
                        self._json(507, {"error": str(e)}); return
                    self._json(200, {"sessionId": sid, "files": tokens, "resume": resume})
                    return

                # v2.1 用 /send 承载单文件上传，与 /upload 等价
                if path in (f"{V2_PREFIX}/upload", f"{V1_PREFIX}/upload",
                            f"{V2_PREFIX}/send", f"{V1_PREFIX}/send"):
                    sid = qs.get("sessionId", [None])[0]; fid = qs.get("fileId", [None])[0]
                    token = qs.get("token", [None])[0]
                    do_resume = qs.get("resume", ["0"])[0] in ("1", "true", "yes")
                    sess = server.sessions.get(sid)
                    if not sess or fid not in sess.files or sess.files[fid]["token"] != token:
                        self._json(403, {"error": "forbidden"}); return

                    entry = sess.files[fid]; target = entry["path"]
                    try: length = int(self.headers.get("Content-Length", "-1") or "-1")
                    except (TypeError, ValueError): length = -1
                    expected = entry["size"] if entry["size"] > 0 else (length if length > 0 else -1)

                    existing = target.stat().st_size if target.exists() else 0
                    if expected > 0 and existing >= expected:
                        # 完整文件已落盘（客户端重试），直接确认，不重复写
                        sess.done.add(fid); self._json(200, {"sessionId": sid})
                        if len(sess.done) >= len(sess.files):
                            with server.lock: server.sessions.pop(sid, None)
                        return
                    if not do_resume or existing <= 0: existing = 0; mode = "wb"
                    else: mode = "ab"

                    received = existing; last_pct = -1
                    try:
                        with open(target, mode) as fp:
                            remaining = length if length > 0 else (1 << 62)
                            if expected > 0: remaining = min(remaining, expected - existing)
                            while remaining > 0:
                                chunk = self.rfile.read(min(65536, remaining))
                                if not chunk: break
                                fp.write(chunk); received += len(chunk); remaining -= len(chunk)
                                if expected > 0:
                                    pct = int(received * 100 / expected)
                                    if pct // 5 != last_pct // 5 or pct == 100:
                                        msg = t("receive_progress", f=entry["fileName"], p=pct,
                                                r=received, t=expected)
                                        _progress_line("⬇️", msg, pct)
                                        last_pct = pct
                        entry["received"] = received
                    except Exception as e:
                        print(); _log.warning("write failed: %s", e)
                        self._json(500, {"error": str(e)}); return

                    if sys.stdout.isatty() and not IS_IDLE: print()
                    if expected > 0 and received != expected:
                        print("❌ " + t("integrity_fail", f=entry["fileName"]))
                        self._json(500, {"error": "size mismatch"}); return

                    sess.done.add(fid)
                    print(f"✅ {t('receive_done', f=entry['fileName'], p=target)}")
                    append_history(entry["fileName"], target, received, True)
                    self._json(200, {"sessionId": sid})
                    threading.Thread(target=server._post_process, args=(target,),
                                     daemon=True).start()
                    if len(sess.done) >= len(sess.files):
                        with server.lock: server.sessions.pop(sid, None)
                    return
                self._json(404, {"error": "not found"})
        return Handler

    @staticmethod
    def _is_port_conflict(e):
        """端口被占用的判定：Windows 常报 WSAEACCES(10013)，POSIX 报 EADDRINUSE(98)。"""
        if getattr(e, "winerror", None) in (10013, 10048): return True
        return e.errno in (errno.EADDRINUSE, errno.EACCES)

    def _bind_httpd(self, port):
        self.httpd = _ThreadingTCPServer((self.host, port), self._make_handler())

    def start(self, blocking=True):
        requested = self.port
        try:
            self._bind_httpd(requested)
        except OSError as e:
            if self._is_port_conflict(e) and requested == DEFAULT_PORT:
                # 默认端口被别的 LocalSend 占用（很常见：官方桌面版同时在跑）：自动改用系统端口
                try:
                    self._bind_httpd(0)
                except OSError as e2:
                    print("\n❌ " + t("port_in_use", p=requested, e=e2))
                    print("   " + t("port_in_use_tip"))
                    raise
                print("⚠️  " + t("port_fallback", p=requested, q=self.httpd.server_address[1]))
            else:
                print("\n❌ " + t("port_in_use", p=requested, e=e))
                print("   " + t("port_in_use_tip"))
                raise
        self.bound_port = self.httpd.server_address[1]
        self.port = self.bound_port

        if self._use_https:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(str(CERT_FILE), str(KEY_FILE))
            self.httpd.socket = ctx.wrap_socket(self.httpd.socket, server_side=True)
            print("🚀 " + t("https_listening", h=self.host, p=self.port))
        else:
            print("🚀 " + t("http_listening", h=self.host, p=self.port))
        print("📁 " + t("save_dir", d=self.save_dir.resolve()))
        if self.pin: print("🔑 " + t("pin_enabled", p=self.pin))

        if self.multicast:
            print("📡 " + t("mc_listening", g=MULTICAST_GROUP, p=DEFAULT_PORT))
            threading.Thread(target=self._mc_loop, daemon=True).start()
        if self.web_enable:
            print("🌐 " + t("web_alone", u=f"http://127.0.0.1:{self.bound_port}/"))

        if blocking:
            try: self.httpd.serve_forever()
            except KeyboardInterrupt: print("\n👋 " + t("stopping"))
            finally: self.stop()
        else: threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self._mc_running = False
        if self.httpd:
            try: self.httpd.shutdown()
            except Exception: pass
            try: self.httpd.server_close()
            except Exception: pass

    def _mc_loop(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", DEFAULT_PORT))
            mreq = struct.pack("4sl", socket.inet_aton(MULTICAST_GROUP), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except OSError as e:
            key = "mc_port_busy" if self._is_port_conflict(e) else "multicast_listen_fail"
            print("⚠️  " + t(key, e=e)); return
        except Exception as e:
            print("⚠️  " + t("multicast_listen_fail", e=e)); return
        try:
            sock.settimeout(1.0)
            while self._mc_running:
                try: data, addr = sock.recvfrom(65535)
                except socket.timeout: continue
                except Exception: continue
                try: o = json.loads(data.decode("utf-8", errors="ignore"))
                except Exception: continue
                if not isinstance(o, dict): continue
                if addr[0] == "127.0.0.1" or o.get("fingerprint") == get_fingerprint(): continue
                try:
                    rs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    rs.sendto(json.dumps(build_self_info(
                        port=self.bound_port,
                        protocol="https" if self._use_https else "http")).encode("utf-8"), addr)
                    rs.close()
                except Exception: pass
        finally:
            try: sock.close()
            except Exception: pass

# ================== 发送端 ==================
def _opener_for(url):
    """https 目标使用不校验证书的 opener：LocalSend 设备普遍是自签名证书。"""
    if url.lower().startswith("https"):
        ctx = ssl._create_unverified_context()
        return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    return urllib.request.build_opener()


def _post_json(url, body, timeout=30):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with _opener_for(url).open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            try: return resp.status, (json.loads(raw) if raw.strip() else {})
            except Exception: return resp.status, {}
    except urllib.error.HTTPError as e:
        if e.code == 401: raise RuntimeError("PIN_REQUIRED")
        return e.code, None


def _prepare_upload(device, files_info, pin):
    """优先走 v2.1 的 send-request，遇到不支持（404/405）时回退到 prepare-upload。"""
    body = {"info": build_self_info(), "files": files_info}
    for endpoint in ("send-request", "prepare-upload"):
        url = device.url(f"{V2_PREFIX}/{endpoint}")
        if pin: url += f"?pin={urllib.parse.quote(pin)}"
        status, resp = _post_json(url, body)
        if status in (404, 405):
            print("ℹ️  " + t("send_fallback")); continue
        return endpoint, status, resp
    return "send-request", 404, None


def _upload_one(url, filepath, offset, size, total_size, sent_counter, lock):
    parsed = urllib.parse.urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else DEFAULT_PORT)
    if parsed.scheme == "https":
        conn = http.client.HTTPSConnection(parsed.hostname, port, timeout=300,
                                           context=ssl._create_unverified_context())
    else:
        conn = http.client.HTTPConnection(parsed.hostname, port, timeout=300)
    path = parsed.path + (("?" + parsed.query) if parsed.query else "")
    conn.putrequest("POST", path)
    conn.putheader("Content-Type", "application/octet-stream")
    conn.putheader("Content-Length", str(size - offset))
    conn.endheaders()

    last_pct = -1
    try:
        with open(filepath, "rb") as fp:
            fp.seek(offset); remaining = size - offset
            while remaining > 0:
                chunk = fp.read(min(65536, remaining))
                if not chunk: break
                conn.send(chunk); remaining -= len(chunk)
                with lock:
                    sent_counter[0] += len(chunk)
                    pct = int(sent_counter[0] * 100 / total_size) if total_size else 100
                    if pct // 5 != last_pct // 5 or pct == 100:
                        msg = t("send_progress", p=pct, s=sent_counter[0], t=total_size)
                        _progress_line("⬆️", msg, pct)
                        last_pct = pct
        resp = conn.getresponse(); resp.read()
        return 200 <= resp.status < 300
    finally:
        conn.close()


def send_files(device, filepaths, pin=None, threads=3):
    files_info, file_ids, total_size = {}, [], 0
    for fp in filepaths:
        if not os.path.isfile(fp): print("⚠️  " + t("skip_missing", p=fp)); continue
        fid = hashlib.md5(f"{fp}{time.time()}{random.random()}".encode()).hexdigest()[:16]
        file_ids.append((fid, fp)); size = os.path.getsize(fp)
        mime, _ = mimetypes.guess_type(fp)
        files_info[fid] = {"id": fid, "fileName": os.path.basename(fp), "size": size,
                           "fileType": mime or "application/octet-stream"}
        total_size += size

    if not file_ids: print("❌ " + t("no_files")); return False
    if device.https: print("🔒 " + t("https_send"))

    print("📤 " + t("send_preparing", n=len(file_ids), s=total_size, d=device))
    # 先向对方注册身份（部分接收端会据此显示设备并刷新会话）
    try:
        _post_json(device.url(f"{V2_PREFIX}/register"), build_self_info())
    except Exception as e:
        _log.info("%s", t("reg_fail", e=e))

    try: endpoint, status, resp = _prepare_upload(device, files_info, pin)
    except RuntimeError: print("🔒 " + t("pin_required")); return False
    except Exception as e: print("❌ " + t("conn_fail", e=e)); return False

    if status != 200 or not resp: print("❌ " + t("send_rejected", c=status)); return False
    sid = resp.get("sessionId")
    if not sid: print("❌ " + t("no_session")); return False
    tokens = resp.get("files", {}) or {}; resume = resp.get("resume", {}) or {}
    upload_path = "send" if endpoint == "send-request" else "upload"

    print("✅ " + t("send_started", s=str(sid)[:8]))
    sent_counter = [0]; lock = threading.Lock(); results = {}

    def worker(fid, fp):
        token = tokens.get(fid)
        if not token: results[fid] = False; return
        try: offset = int(resume.get(fid, 0) or 0)
        except (TypeError, ValueError): offset = 0
        size = files_info[fid]["size"]
        if offset >= size:
            with lock: sent_counter[0] += size
            results[fid] = True; return
        q = (f"?sessionId={urllib.parse.quote(str(sid))}&fileId={urllib.parse.quote(fid)}"
             f"&token={urllib.parse.quote(str(token))}&resume={1 if offset > 0 else 0}")
        try:
            with lock: sent_counter[0] += offset
            results[fid] = _upload_one(device.url(f"{V2_PREFIX}/{upload_path}") + q,
                                       fp, offset, size, total_size, sent_counter, lock)
        except Exception as e:
            results[fid] = False; print("\n❌ " + t("send_fail", f=os.path.basename(fp), e=e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, threads)) as pool:
        list(pool.map(lambda args: worker(*args), file_ids))

    ok = sum(1 for v in results.values() if v)
    print("✅ " + t("send_done", a=ok, b=len(file_ids)))
    return ok == len(file_ids)

# ================== 跨网 ==================
CROSS_CHUNK = 2400            # base64 后 ≈3200 字符，留足 ntfy 单条 4096 字节上限
CROSS_RETRIES = 3


def _ntfy_post(url, body, timeout=15):
    last = None
    for attempt in range(CROSS_RETRIES):
        try:
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", "text/plain")
            urllib.request.urlopen(req, timeout=timeout).read()
            return True
        except Exception as e:
            last = e
            time.sleep(0.5 * (attempt + 1))
    raise last


def cross_send(filepaths, pin=None):
    if not pin: pin = f"{random.randint(100000, 999999)}"
    print("📌 " + t("cross_pin", p=pin) + "\n📦 " + t("packing"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in filepaths:
            if os.path.isfile(fp): zf.write(fp, os.path.basename(fp))
    data = buf.getvalue()
    if not data: print("❌ " + t("no_files")); return False
    print("📦 " + t("packed", n=len(data)))

    url = ntfy_base() + pin
    digest = hashlib.sha256(data).hexdigest()
    total, sent, idx = len(data), 0, 0
    while sent < total:
        piece = data[sent:sent + CROSS_CHUNK]
        try: _ntfy_post(url, base64.b64encode(piece).encode())
        except Exception as e: print("\n❌ " + t("chunk_fail", i=idx, e=e)); return False
        sent += len(piece); idx += 1
        _progress_line("⬆️", t("cross_progress", s=sent, t=total, p=int(sent * 100 / total)),
                       int(sent * 100 / total))
        time.sleep(0.1)
    # 尾包携带长度与 SHA256，接收端据此判完整性；旧版本接收端会忽略无法解码的尾包
    try: _ntfy_post(url, f"__SHA256__:{digest}:{total}".encode())
    except Exception: pass
    try: _ntfy_post(url, b"__END__")
    except Exception: pass
    print("\n✅ " + t("cross_sent"))
    return True


def cross_recv(pin, out_dir=None):
    out = Path(out_dir if out_dir else get_config("save_dir")).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    poll_url = ntfy_base() + pin + "/json?poll=1"
    print("📡 " + t("listening_pin", p=pin))
    chunks, seen, finished, idle, expect = [], set(), False, 0, None
    digest = None
    while not finished:
        got = False
        try:
            with urllib.request.urlopen(poll_url, timeout=20) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
            for line in content.splitlines():
                line = line.strip()
                if not line: continue
                try: o = json.loads(line)
                except Exception: continue
                mid = o.get("id") or f"{o.get('time', 0)}-{hash(line)}"
                if mid in seen: continue
                seen.add(mid)
                msg = o.get("message", "")
                if not isinstance(msg, str): continue
                if msg == "__END__": finished = True; break
                if msg.startswith("__SHA256__:"):
                    parts = msg.split(":")
                    if len(parts) == 3:
                        digest = parts[1]; 
                        try: expect = int(parts[2])
                        except ValueError: expect = None
                    continue
                if msg:
                    try:
                        chunks.append(base64.b64decode(msg, validate=True)); got = True
                        _progress_line("⬇️", t("cross_recv_progress",
                                              n=sum(len(c) for c in chunks)))
                    except Exception: pass
        except Exception: pass
        if finished: break
        if not got:
            idle += 1
            if idle > 300: print("\n⏱️  " + t("cross_timeout")); return False
        else: idle = 0
        time.sleep(1)
    print()
    data = b"".join(chunks)
    if not data: print("❌ " + t("no_data")); return False

    if digest and hashlib.sha256(data).hexdigest() != digest:
        print("❌ " + t("integrity_fail", f=f"lspy_{pin}.zip")); return False
    if expect is not None and len(data) != expect:
        print("❌ " + t("integrity_fail", f=f"lspy_{pin}.zip")); return False

    zip_path = out / f"lspy_{pin}.zip"; zip_path.write_bytes(data)
    print("📦 " + t("saved", p=zip_path, n=len(data)))
    if safe_unzip(zip_path, out):
        print("✅ " + t("unzip_ok", d=out.resolve()))
        try: zip_path.unlink()
        except Exception: pass
    return True

# ================== CLI 子命令 ==================
def _discover(timeout=2.0, announce=True):
    """组播扫描 + HTTP 深度扫描（同时探测配置端口与默认端口），合并去重。"""
    devs = scan_network(timeout=timeout)
    seen = {f"{d.ip}:{d.port}" for d in devs}
    ports = sorted({DEFAULT_PORT, int(get_config("port") or DEFAULT_PORT)})
    bases = sorted({".".join(ip.split(".")[:3]) for ip in local_ipv4_addresses()
                    if ip.count(".") == 3 and not ip.startswith("127.")})
    first = True
    for base in bases:
        for port in ports:
            for d in http_scan(f"{base}.1", port=port, announce=announce and first):
                key = f"{d.ip}:{d.port}"
                if key not in seen:
                    seen.add(key); devs.append(d)
            first = False
    return devs


def cmd_info(args): print(json.dumps(build_self_info(), indent=2, ensure_ascii=False))


def cmd_scan(args):
    print("🔍 " + t("scanning_long", t=args.timeout))
    devs = _discover(args.timeout)
    if args.json:
        print(json.dumps([{"alias": d.alias, "ip": d.ip, "port": d.port, "version": d.version,
                           "fingerprint": d.fingerprint, "deviceType": d.deviceType,
                           "https": d.https} for d in devs], indent=2, ensure_ascii=False))
        return
    if not devs:
        print(t("scan_none"))
        print(t("firewall_tip"))
    else:
        print("\n" + t("scan_found_n", n=len(devs)))
        for i, d in enumerate(devs, 1): print(f"  {i}. {d}")


def cmd_serve(args):
    auto = get_config("auto_accept")
    if args.confirm: auto = False
    elif args.auto_accept: auto = True
    pin = None if args.no_pin else (args.pin or get_config("pin"))
    web_enable = None if not args.no_web else False
    srv = LspyServer(host=args.host, port=args.port, save_dir=args.dir, auto_accept=auto,
                     pin=pin, verbose=args.verbose, multicast=not args.no_multicast,
                     web_enable=web_enable)
    if args.web and not args.no_web:
        def _open_when_ready():
            for _ in range(100):
                if srv.httpd is not None: break
                time.sleep(0.1)
            try: webbrowser.open(f"http://127.0.0.1:{srv.bound_port}/")
            except Exception: pass
        threading.Thread(target=_open_when_ready, daemon=True).start()
    srv.start(blocking=True)


def cmd_send(args):
    if args.ip:
        host, port = args.ip, (args.port or DEFAULT_PORT)
        if ":" in args.ip and not args.ip.startswith("["):
            h, p = args.ip.rsplit(":", 1)
            if p.isdigit(): host, port = h, int(p)
        dev = Device(alias=args.ip, ip=host, port=port, https=args.https)
        send_files(dev, args.files, pin=args.pin)
        return
    if not args.device:
        print("❌ " + t("specify_device_or_ip")); return

    print("🔍 " + t("scan_target"))
    devs = _discover(args.timeout)
    target = next((d for d in devs if d.alias == args.device or d.fingerprint == args.device
                   or f"{d.ip}:{d.port}" == args.device), None)
    if target: send_files(target, args.files, pin=args.pin)
    else: print("❌ " + t("device_not_found", n=args.device))


def cmd_cross_send(args): cross_send(args.files, args.pin)
def cmd_cross_recv(args): cross_recv(args.pin, args.dir)


def cmd_stun(args):
    print("🔍 " + t("stun_probing"))
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sock.settimeout(3)
        txn = bytes(random.getrandbits(8) for _ in range(12))
        req = struct.pack(">HHI", 1, 0, 0x2112A442) + txn
        sock.sendto(req, ("stun.l.google.com", 19302))
        data, _ = sock.recvfrom(2048)
        pos, msg_len = 20, struct.unpack(">H", data[2:4])[0]
        while pos + 4 <= 20 + msg_len and pos + 4 <= len(data):
            typ, ln = struct.unpack(">HH", data[pos:pos + 4]); val = data[pos + 4:pos + 4 + ln]
            if typ in (0x0020, 0x0001) and len(val) >= 8:
                xport = struct.unpack(">H", val[2:4])[0]; ip_b = bytearray(val[4:8])
                if typ == 0x0020:
                    xport ^= 0x2112
                    ip_b = bytearray(a ^ b for a, b in zip(ip_b, [0x21, 0x12, 0xA4, 0x42]))
                print(t("stun_result", r=f"{'.'.join(map(str, ip_b))}:{xport}")); return
            pos += 4 + ln
        print(t("stun_fail", e="no mapped address in response"))
    except Exception as e:
        print(t("stun_fail", e=e))
    finally:
        if sock:
            try: sock.close()
            except Exception: pass

def cmd_history(args):
    entries = read_history(args.n)
    if not entries: print(t("history_empty")); return
    for e in entries:
        print(t("history_entry", t=e.get("time"), f=e.get("file"), s=e.get("size"), r=e.get("receive")))

def cmd_cert(args):
    try:
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", str(KEY_FILE), "-out", str(CERT_FILE), "-days", "3650", "-nodes", "-subj", "/CN=lspy"], check=True, capture_output=True)
        print(f"✅ cert: {CERT_FILE}\n✅ key : {KEY_FILE}")
    except Exception as e: print(f"❌ {e}")

def cmd_open(args):
    for p in args.files: _open_path(p)

def cmd_config(args):
    if args.reset:
        reset_config(); print("✅ " + t("cfg_reset_done")); return
    if args.show: print(json.dumps(load_config(), indent=2, ensure_ascii=False)); return
    if args.set:
        if "=" not in args.set: print("⚠️ " + t("cfg_invalid_set")); return
        k, v = args.set.split("=", 1)
        try:
            if k == "port":
                if not v.isdigit() or not 1 <= int(v) <= 65535:
                    print("⚠️ " + t("cfg_invalid_port")); return
                v = int(v)
            elif k in ("auto_accept", "use_https", "web_enable", "organize_by_type",
                       "history_enable", "auto_unzip", "open_after_receive",
                       "auto_accept_whitelist"):
                v = v.lower() in ("1", "true", "yes", "on")
            elif k in ("whitelist", "blacklist"):
                v = [x.strip() for x in v.split(",") if x.strip()]
        except Exception as e:
            print("⚠️ " + t("input_error", e=e)); return
        set_config(k, v); print("✅ " + t("cfg_set_done", k=k, v=v)); return
    interactive_config()

# ================== 交互菜单 ==================
def interactive_config():
    while True:
        cfg = load_config()
        alias = cfg.get("alias") or f"{socket.gethostname()} {t('cfg_default')}"
        port = cfg.get("port", DEFAULT_PORT); save_dir = cfg.get("save_dir", "./downloads")
        pin = cfg.get("pin") or t("cfg_none"); auto = cfg.get("auto_accept", True)
        fp = cfg.get("fingerprint", "?"); topic = cfg.get("ntfy_topic", CONFIG_DEFAULTS["ntfy_topic"])
        lang = I18N[_current_lang].get("lang_name", _current_lang)

        print("\n" + "─" * 50); print(" ⚙️  " + t("cfg_title")); print("─" * 50)
        print(f"  {t('cfg_lang'):<12}: {lang}\n  {t('cfg_alias'):<12}: {alias}\n  {t('cfg_port'):<12}: {port}")
        print(f"  {t('cfg_savedir'):<12}: {save_dir}\n  {t('cfg_pin'):<12}: {pin}\n  {t('cfg_auto'):<12}: {auto}")
        print(f"  {t('cfg_topic'):<12}: {topic}\n  {t('cfg_fp'):<12}: {fp[:20]}...\n  {t('cfg_file'):<12}: {CONFIG_FILE}")
        print("─" * 50)
        for i, k in enumerate(["cfg_menu_alias", "cfg_menu_port", "cfg_menu_savedir", "cfg_menu_pin", "cfg_menu_auto", "cfg_menu_topic", "cfg_menu_regen_fp", "cfg_menu_reset", "cfg_menu_lang"], 1):
            print(f" {i}. {t(k)}")
        print(f" 0. {t('cfg_menu_back')}"); print("─" * 50)

        try: choice = input(t("choose_prompt", choices="0-9")).strip()
        except (EOFError, KeyboardInterrupt): return

        if choice == "0": return
        elif choice == "1": set_config("alias", input(t("cfg_prompt_alias", d=socket.gethostname())).strip() or None)
        elif choice == "2":
            v = input(t("cfg_prompt_port", d=port)).strip()
            if v.isdigit() and 1 <= int(v) <= 65535: set_config("port", int(v))
            elif v: print("⚠️ " + t("cfg_invalid_port"))
        elif choice == "3": set_config("save_dir", input(t("cfg_prompt_savedir", d=save_dir)).strip() or None)
        elif choice == "4": set_config("pin", input(t("cfg_prompt_pin", d=cfg.get("pin") or "")).strip() or None)
        elif choice == "5": set_config("auto_accept", not auto)
        elif choice == "6": set_config("ntfy_topic", input(t("cfg_prompt_topic", d=topic)).strip() or None)
        elif choice == "7": set_config("fingerprint", _gen_fp())
        elif choice == "8":
            if input(t("cfg_confirm_reset")).strip().lower() == "y": reset_config(); print("✅ " + t("cfg_reset_done"))
        elif choice == "9":
            codes = ["auto"] + SUPPORTED_LANGS
            for i, c in enumerate(codes): print(f"  {i}. {c} — {t('cfg_default') if c=='auto' else I18N.get(c, {}).get('lang_name', c)}")
            try:
                idx = int(input(t("cfg_lang_choice", choices=f"0-{len(codes)-1}")).strip())
                if 0 <= idx < len(codes): set_config("lang", codes[idx]); init_lang()
            except Exception: pass

def pick_files():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw()
        paths = filedialog.askopenfilenames(title=t("pick_files_title")); root.destroy()
        if paths: return list(paths)
    except Exception: pass
    raw = input(t("prompt_files")).strip()
    return [x.strip().strip('"').strip("'") for x in raw.split(",") if x.strip()]


def interactive_menu():
    print("\n" + "=" * 20 + " " + t("menu_banner") + " " + "=" * 20)

    bg_server = None
    print("🔄 " + t("auto_start"))
    try:
        bg_server = LspyServer(auto_accept=get_config("auto_accept"), pin=get_config("pin"))
        bg_server.start(blocking=False)
    except Exception as e:
        print("❌ " + t("auto_start_fail", e=e))

    devices = []
    while True:
        print("\n 1. " + t("menu_info") + "\n 2. " + t("menu_scan") + "\n 3. " + t("menu_serve_fg"))
        print(" 4. " + t("menu_send") + "\n 5. " + t("menu_cross_send") + "\n 6. " + t("menu_cross_recv"))
        print(" 7. " + t("menu_history") + "\n 8. " + t("menu_config") + "\n 0. " + t("menu_exit"))
        try:
            choice = input(t("choose_prompt", choices="0-8")).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 " + t("bye"))
            if bg_server: bg_server.stop()
            return

        if choice == "0":
            print("👋 " + t("bye"))
            if bg_server: bg_server.stop()
            return
        elif choice == "1":
            print(json.dumps(build_self_info(), indent=2, ensure_ascii=False))
        elif choice == "2":
            print("🔍 " + t("scanning_short"))
            devices = _discover(2.0)
            if not devices:
                print(t("scan_none"))
                print(t("firewall_tip"))
        elif choice == "3":
            if bg_server: bg_server.stop(); bg_server = None
            print("🚀 " + t("fg_hint"))
            try: LspyServer().start(blocking=True)
            except OSError as e: print("❌ " + t("port_in_use", p=DEFAULT_PORT, e=e))
            try:
                bg_server = LspyServer(auto_accept=get_config("auto_accept"), pin=get_config("pin"))
                bg_server.start(blocking=False)
            except Exception as e:
                print("❌ " + t("auto_start_fail", e=e))
        elif choice == "4":
            target = None
            try:
                print(t("send_how"))
                sub = input(t("send_choose")).strip()
                if sub == "1":
                    if not devices:
                        print("🔍 " + t("scanning_short"))
                        devices = _discover(2.0)
                    if not devices:
                        print("❌ " + t("no_device_scan"))
                        print(t("firewall_tip"))
                        continue
                    for i, d in enumerate(devices, 1): print(f"  {i}. {d}")
                    idx = int(input(t("prompt_pick_device", n=len(devices))).strip()) - 1
                    if not 0 <= idx < len(devices):
                        print("⚠️ " + t("index_out_of_range")); continue
                    target = devices[idx]
                elif sub == "2":
                    ip = input(t("prompt_ip")).strip()
                    if not ip: continue
                    host, port = ip, DEFAULT_PORT
                    if ":" in ip and not ip.startswith("["):
                        h, p = ip.rsplit(":", 1)
                        if p.isdigit(): host, port = h, int(p)
                    target = Device(alias=ip, ip=host, port=port)
                if target:
                    files = pick_files()
                    if not files:
                        print("⚠️ " + t("no_file_selected")); continue
                    pin = input(t("prompt_target_pin")).strip() or None
                    send_files(target, files, pin=pin)
            except (EOFError, KeyboardInterrupt):
                pass
            except Exception as e:
                print("⚠️ " + t("input_error", e=e))
        elif choice == "5":
            files = pick_files()
            if files: cross_send(files, input(t("prompt_cross_pin")).strip() or None)
        elif choice == "6":
            pin = input(t("prompt_cross_recv_pin")).strip()
            if pin: cross_recv(pin)
        elif choice == "7":
            cmd_history(argparse.Namespace(n=20))
        elif choice == "8":
            interactive_config()
        else:
            print("⚠️ " + t("invalid_option"))


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="lspy", description="lspy — LocalSend-compatible Python CLI")
    parser.add_argument("--version", action="version", version=f"lspy {VERSION}")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("info", help="print this device's LocalSend info")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("scan", help="discover nearby devices")
    p.add_argument("-t", "--timeout", type=float, default=2.0)
    p.add_argument("--json", action="store_true", help="output JSON")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("serve", help="start the receive service")
    p.add_argument("-H", "--host", default="0.0.0.0"); p.add_argument("-p", "--port", type=int, default=None)
    p.add_argument("-d", "--dir", default=None); p.add_argument("--pin"); p.add_argument("--no-pin", action="store_true")
    p.add_argument("--confirm", action="store_true"); p.add_argument("--auto-accept", action="store_true")
    p.add_argument("--web", action="store_true", help="open the status page in a browser")
    p.add_argument("--no-multicast", action="store_true", help="disable the multicast listener")
    p.add_argument("--no-web", action="store_true", help="disable the HTTP status page")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("send", help="send files to a device")
    p.add_argument("files", nargs="+"); p.add_argument("--device"); p.add_argument("--ip")
    p.add_argument("--port", type=int, default=None); p.add_argument("--https", action="store_true")
    p.add_argument("--pin"); p.add_argument("-t", "--timeout", type=float, default=3.0)
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("cross-send", help="send files across networks via ntfy.sh")
    p.add_argument("files", nargs="+"); p.add_argument("--pin")
    p.set_defaults(func=cmd_cross_send)

    p = sub.add_parser("cross-recv", help="receive cross-network files via ntfy.sh")
    p.add_argument("pin"); p.add_argument("-d", "--dir", default=None)
    p.set_defaults(func=cmd_cross_recv)

    p = sub.add_parser("stun", help="probe the public address via STUN")
    p.set_defaults(func=cmd_stun)

    p = sub.add_parser("history", help="show transfer history")
    p.add_argument("-n", type=int, default=20)
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("cert", help="generate a self-signed TLS certificate")
    p.set_defaults(func=cmd_cert)

    p = sub.add_parser("open", help="open files with the OS handler")
    p.add_argument("files", nargs="+"); p.set_defaults(func=cmd_open)

    p = sub.add_parser("config", help="show / set / reset configuration")
    p.add_argument("--show", action="store_true"); p.add_argument("--set")
    p.add_argument("--reset", action="store_true"); p.set_defaults(func=cmd_config)
    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_stdio()
    init_lang(); setup_logging()
    if args.verbose:
        _log.setLevel(logging.DEBUG)
    if not getattr(args, "cmd", None):
        # 非交互环境（管道/重定向）下不要阻塞在 input()
        if not (sys.stdin and sys.stdin.isatty()):
            parser.print_help(); return 0
        interactive_menu()
        return 0
    args.func(args)
    return 0


if __name__ == "__main__":
    try: sys.exit(main())
    except KeyboardInterrupt: sys.exit(130)
