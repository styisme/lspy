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
VERSION = "1.23.0"
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
        "history_cleared": "History wiped", "history_deleted": "Deleted: {f}",
        "history_bad_index": "No such entry: {n}", "history_missing": "File is gone: {p}",
        "not_zip": "Not a ZIP file: {p}",
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
        "web_tab_upload": "Send to this device", "web_tab_download": "Download from this device", "web_tab_text": "Text message",
        "web_upload_hint": "Drop files here or click to choose. They are saved to the receive folder.", "web_download_empty": "Nothing received yet", "web_text_hint": "Text goes to the clipboard, or to a .txt file when the clipboard is unavailable.",
        "web_send": "Send", "web_clip_btn": "Read clipboard", "web_pin_prompt": "Access PIN",
        "web_up_ok": "Uploaded", "web_text_ok": "Text sent", "web_pin_bad": "PIN required",
        "web_uploaded": "Uploaded {f}",
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
        "history_cleared": "已清空历史记录", "history_deleted": "已删除：{f}",
        "history_bad_index": "没有这条记录：{n}", "history_missing": "文件已不存在：{p}",
        "not_zip": "不是 ZIP 文件：{p}",
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
        "web_tab_upload": "上传到本机", "web_tab_download": "下载本机文件", "web_tab_text": "发送文本",
        "web_upload_hint": "拖入文件或点击选择，上传后保存到接收目录", "web_download_empty": "还没有接收过文件", "web_text_hint": "文本会写入本机剪贴板；剪贴板不可用时保存为 txt 文件",
        "web_send": "发送", "web_clip_btn": "读取剪贴板", "web_pin_prompt": "访问 PIN",
        "web_up_ok": "已上传", "web_text_ok": "已发送", "web_pin_bad": "需要 PIN",
        "web_uploaded": "已上传 {f}",
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
    "de": {
        "lang_name": "Deutsch", "menu_title": "lspy — LocalSend-kompatible CLI",
        "menu_info": "Geräteinfo anzeigen", "menu_scan": "Geräte in der Nähe suchen",
        "menu_serve": "Empfangsdienst starten (Vordergrund)", "menu_send": "Dateien an Gerät senden",
        "menu_cross_send": "Senden über Netzwerke hinweg (ntfy.sh)", "menu_cross_recv": "Empfangen über Netzwerke hinweg (ntfy.sh)",
        "menu_history": "Verlauf", "menu_config": "Einstellungen", "menu_exit": "Beenden",
        "choose_prompt": "Auswahl [{choices}]: ", "invalid_option": "Ungültige Auswahl",
        "bye": "Beendet", "scanning_short": "Suche im LAN...", "scanning_long": "Suche im LAN (Timeout {t}s)...",
        "scan_none": "Keine Geräte gefunden", "scan_found_n": "{n} Gerät(e) gefunden:", "found_device": "Gefunden: {d}",
        "scan_target": "Suche Zielgerät...", "device_not_found": "Gerät nicht gefunden: {n}",
        "specify_device_or_ip": "Bitte --device oder --ip angeben",
        "multicast_send_fail": "Multicast-Senden fehlgeschlagen: {e}", "multicast_listen_fail": "Multicast-Empfang fehlgeschlagen: {e}",
        "http_listening": "HTTP lauscht auf {h}:{p}", "https_listening": "HTTPS lauscht auf {h}:{p}",
        "save_dir": "Speicherordner: {d}", "pin_enabled": "PIN aktiv: {p}", "mc_listening": "Multicast {g}:{p}",
        "mc_reply": "MC-Antwort: {a} @ {ip}", "stopping": "Wird beendet...",
        "ask_receive": "Von [{a}] @ {ip}: {n} Datei(en). Annehmen? [Y/n]: ",
        "session_created": "Sitzung {s} wartet auf {n} Datei(en)", "receive_done": "Empfangen: {f} -> {p}",
        "receive_progress": "{f}: {p}% ({r}/{t})", "write_fail": "Schreiben fehlgeschlagen: {e}",
        "send_preparing": "Sende {n} Datei(en) ({s} Bytes) -> {d}", "pin_required": "Gegenstelle verlangt PIN (--pin)",
        "conn_fail": "Verbindung fehlgeschlagen: {e}", "send_rejected": "Abgelehnt (HTTP {c})",
        "no_session": "Ungültige Antwort: sessionId fehlt", "send_started": "Sitzung {s}... wird hochgeladen",
        "send_progress": "Upload: {p}% ({s}/{t})", "send_fail": "Upload fehlgeschlagen {f}: {e}",
        "send_done": "Fertig {a}/{b} Datei(en)", "https_unsupported": "Ziel nutzt HTTPS (vom Senden nicht unterstützt)",
        "skip_missing": "Übersprungen: {p}", "no_files": "Keine Dateien",
        "cross_pin": "Cross-PIN: {p}  (Empfänger: lspy cross-recv {p})", "packing": "Packe...",
        "packed": "Gepackt: {n} Bytes", "cross_progress": "Senden: {s}/{t} ({p}%)",
        "chunk_fail": "Block {i} fehlgeschlagen: {e}", "cross_sent": "Gesendet", "listening_pin": "Warte auf PIN: {p}",
        "cross_recv_progress": "{n} Bytes empfangen", "cross_timeout": "Timeout", "no_data": "Keine Daten",
        "saved": "Gespeichert: {p} ({n} Bytes)", "unzip_ok": "Entpackt: {d}", "unzip_fail": "Entpacken fehlgeschlagen: {e}",
        "blocked_ext": "Blockiert: {f}", "blocked_list": "Durch Blacklist blockiert: {a}",
        "invalid_port": "Ungültiger Port", "invalid_input": "Ungültige Eingabe", "index_out_of_range": "Außerhalb des Bereichs",
        "no_files_provided": "Keine Dateien angegeben", "pin_empty": "PIN leer", "no_file_selected": "Keine Datei ausgewählt",
        "no_device_scan": "Keine Geräte, prüfe den Dienst der Gegenstelle", "prompt_files": "Dateipfade (kommagetrennt): ",
        "prompt_save_dir": "Speicherordner [{d}]: ", "prompt_pin_off": "PIN (leer=aus): ",
        "prompt_pin_on": "PIN (leer={p} verwenden): ", "prompt_ask_each": "Jedes Mal nachfragen? [y/N] (aktuell: {v}): ",
        "prompt_target_pin": "Ziel-PIN (leer=keine): ", "prompt_cross_pin": "PIN (leer=zufällig): ",
        "prompt_cross_recv_pin": "6-stellige PIN: ", "prompt_pick_device": "Auswahl [1-{n}]: ",
        "pick_files_title": "Dateien auswählen", "yes": "ja", "no": "nein",
        "stun_probing": "STUN wird abgefragt...", "stun_result": "Öffentliche Adresse: {r}", "stun_fail": "STUN fehlgeschlagen: {e}",
        "history_empty": "Kein Verlauf", "history_entry": "[{t}] {f} ({s} Bytes) receive={r}",
        "history_cleared": "Verlauf gelöscht", "history_deleted": "Gelöscht: {f}",
        "history_bad_index": "Kein solcher Eintrag: {n}", "history_missing": "Datei fehlt: {p}",
        "not_zip": "Keine ZIP-Datei: {p}",
        "cfg_title": "Aktuelle Konfiguration", "cfg_alias": "Alias", "cfg_port": "Port", "cfg_savedir": "Speicherordner",
        "cfg_pin": "Standard-PIN", "cfg_auto": "Automatisch annehmen", "cfg_topic": "NTFY-Thema", "cfg_fp": "Fingerabdruck",
        "cfg_lang": "Sprache", "cfg_none": "(keine)", "cfg_default": "(Standard)",
        "cfg_menu_alias": "Alias ändern", "cfg_menu_port": "Port ändern", "cfg_menu_savedir": "Speicherordner ändern",
        "cfg_menu_pin": "PIN ändern", "cfg_menu_auto": "Auto-Annehmen umschalten", "cfg_menu_topic": "NTFY-Thema ändern",
        "cfg_menu_regen_fp": "Fingerabdruck neu erzeugen", "cfg_menu_reset": "Konfiguration zurücksetzen", "cfg_menu_lang": "Sprache ändern",
        "cfg_menu_back": "Zurück", "cfg_prompt_alias": "Neuer Alias [{d}]: ", "cfg_prompt_port": "Neuer Port [{d}]: ",
        "cfg_prompt_savedir": "Neuer Ordner [{d}]: ", "cfg_prompt_pin": "Neue PIN [{d}]: ",
        "cfg_prompt_topic": "Neues Thema [{d}]: ", "cfg_confirm_reset": "Alles zurücksetzen? [y/N]: ",
        "cfg_reset_done": "Konfiguration zurückgesetzt", "cfg_not_exist": "Konfiguration nicht gefunden",
        "cfg_set_done": "{k} = {v} gesetzt", "cfg_unset_done": "{u} gelöscht",
        "cfg_invalid_port": "Port 1-65535", "cfg_invalid_set": "Format: --set k=v",
        "cfg_invalid_lang": "Nicht unterstützte Sprache: {l}", "cfg_lang_choice": "Sprache [{choices}]: ",
        "cfg_file": "Konfigurationsdatei", "help_text": "Hilfe", "confirm_receive_30s": "Von [{a}] empfangen? (30s, dann automatisch ablehnen) [Y/n]: ",
        "firewall_tip": "\n💡 Hinweis: Wenn der Dienst der Gegenstelle läuft, prüfe:\n  1. Ob die Windows-Firewall das Programm blockiert (Python in den Einstellungen freigeben)\n  2. Ob beide Geräte im selben LAN sind (AP-Isolation im Router?)\n  3. Wenn es weiter nicht klappt: Option 4 -> 2, IP manuell eingeben.\n",
        "deep_scanning": "🌐 UDP-Timeout, starte HTTP-Tiefenscan auf {ip}.1/24 ...",
        "web_title": "lspy — Empfangsstatus", "web_alias": "Alias", "web_port": "Port",
        "web_fp": "Fingerabdruck", "web_recent": "Zuletzt empfangen", "web_none": "Noch nichts empfangen",
        "web_hint": "Diesen Dienst laufen lassen. Von LocalSend gesendete Dateien werden automatisch gespeichert.",
        "reg_fail": "Registrierung beim Empfänger fehlgeschlagen: {e}", "register_ok": "Beim Empfänger angekündigt",
        "send_fallback": "Ziel hat keinen v2.1-Endpunkt, Fallback auf prepare-upload",
        "files_skipped": "{n} Datei(en) durch Endungsregel übersprungen", "https_send": "TLS für das Ziel aktiviert",
        "unzip_unsafe": "Entpacken abgelehnt: unsicherer Eintrag {p}", "http_scan_https": "HTTPS-Hosts werden mitgeprüft",
        "bound_port": "An Port {p} gebunden", "no_write_perm": "Kann nicht nach {p} schreiben: {e}",
        "integrity_fail": "Integritätsprüfung fehlgeschlagen für {f}", "chunk_hash": "Prüfsumme von Block {i} stimmt nicht, neuer Versuch",
        "version": "Version", "web_alone": "Webseite unter {u}",
        "web_tab_upload": "An dieses Gerät senden", "web_tab_download": "Von diesem Gerät laden", "web_tab_text": "Textnachricht",
        "web_upload_hint": "Dateien hierher ziehen oder klicken. Sie werden im Empfangsordner gespeichert.", "web_download_empty": "Noch nichts empfangen", "web_text_hint": "Text wird in die Zwischenablage kopiert oder als .txt-Datei gespeichert, wenn keine Zwischenablage verfügbar ist.",
        "web_send": "Senden", "web_clip_btn": "Zwischenablage lesen", "web_pin_prompt": "Zugriffs-PIN",
        "web_up_ok": "Hochgeladen", "web_text_ok": "Text gesendet", "web_pin_bad": "PIN erforderlich",
        "web_uploaded": "Hochgeladen: {f}",
        "menu_serve_fg": "In den Vordergrunddienst wechseln (ausführlicher Verlauf)",
        "auto_start": "Hintergrund-Empfänger wird gestartet...", "auto_start_fail": "Autostart fehlgeschlagen: {e}",
        "port_in_use": "Port {p} nicht verfügbar: {e}",
        "port_in_use_tip": "Wahrscheinlich hält die LocalSend-Desktop-App oder eine zweite lspy-Instanz diesen Port. Schließen, oder einen anderen Port mit -p 0 / -p 53318 wählen.",
        "port_fallback": "Port {p} ist belegt, auf den vom System vergebenen Port {q} gewechselt (mit -p festlegen).",
        "mc_port_busy": "Multicast-Port 53317 ist belegt (meist läuft LocalSend-Desktop daneben); Multicast-Listener übersprungen, HTTP-Erkennung funktioniert weiter. --no-multicast schaltet den Hinweis ab.",
        "fg_hint": "Vordergrund-Empfänger läuft, Ctrl+C beendet ihn und kehrt zum Menü zurück",
        "send_how": "1. Geräte automatisch suchen\n2. IP manuell eingeben", "send_choose": "Auswahl [1-2]: ",
        "prompt_ip": "Ziel-IP (z. B. 192.168.1.10): ", "input_error": "Eingabefehler: {e}",
        "menu_banner": "lspy — LocalSend-kompatible CLI",
        "menu_devices": "Geräte in der Nähe", "no_devices_yet": "Noch nicht gesucht, wähle 2 zum Suchen",
    },
    "fr": {
        "lang_name": "Français", "menu_title": "lspy — CLI compatible LocalSend",
        "menu_info": "Afficher les infos de l'appareil", "menu_scan": "Rechercher les appareils proches",
        "menu_serve": "Démarrer le service de réception (premier plan)", "menu_send": "Envoyer des fichiers à un appareil",
        "menu_cross_send": "Envoi inter-réseaux (ntfy.sh)", "menu_cross_recv": "Réception inter-réseaux (ntfy.sh)",
        "menu_history": "Historique", "menu_config": "Paramètres", "menu_exit": "Quitter",
        "choose_prompt": "Choix [{choices}] : ", "invalid_option": "Option invalide",
        "bye": "Au revoir", "scanning_short": "Analyse du réseau local...", "scanning_long": "Analyse du réseau local (délai {t}s)...",
        "scan_none": "Aucun appareil trouvé", "scan_found_n": "{n} appareil(s) trouvé(s) :", "found_device": "Trouvé : {d}",
        "scan_target": "Recherche de l'appareil cible...", "device_not_found": "Appareil introuvable : {n}",
        "specify_device_or_ip": "Indiquez --device ou --ip",
        "multicast_send_fail": "Échec de l'envoi multicast : {e}", "multicast_listen_fail": "Échec de l'écoute multicast : {e}",
        "http_listening": "HTTP à l'écoute sur {h}:{p}", "https_listening": "HTTPS à l'écoute sur {h}:{p}",
        "save_dir": "Dossier de réception : {d}", "pin_enabled": "PIN activé : {p}", "mc_listening": "Multicast {g}:{p}",
        "mc_reply": "Réponse MC : {a} @ {ip}", "stopping": "Arrêt...",
        "ask_receive": "De [{a}] @ {ip} : {n} fichier(s). Accepter ? [Y/n] : ",
        "session_created": "Session {s} en attente de {n} fichier(s)", "receive_done": "Reçu : {f} -> {p}",
        "receive_progress": "{f} : {p}% ({r}/{t})", "write_fail": "Échec d'écriture : {e}",
        "send_preparing": "Envoi de {n} fichier(s) ({s} octets) -> {d}", "pin_required": "La cible exige un PIN (--pin)",
        "conn_fail": "Connexion échouée : {e}", "send_rejected": "Refusé (HTTP {c})",
        "no_session": "Réponse invalide : sessionId manquant", "send_started": "Session {s}... envoi en cours",
        "send_progress": "Envoi : {p}% ({s}/{t})", "send_fail": "Échec de l'envoi de {f} : {e}",
        "send_done": "Terminé {a}/{b} fichier(s)", "https_unsupported": "La cible utilise HTTPS (non pris en charge à l'envoi)",
        "skip_missing": "Ignoré : {p}", "no_files": "Aucun fichier",
        "cross_pin": "PIN inter-réseaux : {p}  (réception : lspy cross-recv {p})", "packing": "Compression...",
        "packed": "Compressé : {n} octets", "cross_progress": "Envoi : {s}/{t} ({p}%)",
        "chunk_fail": "Bloc {i} échoué : {e}", "cross_sent": "Envoyé", "listening_pin": "En écoute du PIN : {p}",
        "cross_recv_progress": "{n} octets reçus", "cross_timeout": "Délai dépassé", "no_data": "Aucune donnée",
        "saved": "Enregistré : {p} ({n} octets)", "unzip_ok": "Extrait : {d}", "unzip_fail": "Échec de l'extraction : {e}",
        "blocked_ext": "Bloqué : {f}", "blocked_list": "Bloqué par la liste noire : {a}",
        "invalid_port": "Port invalide", "invalid_input": "Entrée invalide", "index_out_of_range": "Hors limites",
        "no_files_provided": "Aucun fichier fourni", "pin_empty": "PIN vide", "no_file_selected": "Aucun fichier sélectionné",
        "no_device_scan": "Aucun appareil, vérifiez le service distant", "prompt_files": "Chemins des fichiers (séparés par des virgules) : ",
        "prompt_save_dir": "Dossier de réception [{d}] : ", "prompt_pin_off": "PIN (vide=désactivé) : ",
        "prompt_pin_on": "PIN (vide={p}) : ", "prompt_ask_each": "Demander à chaque réception ? [y/N] (actuel : {v}) : ",
        "prompt_target_pin": "PIN cible (vide=aucun) : ", "prompt_cross_pin": "PIN (vide=aléatoire) : ",
        "prompt_cross_recv_pin": "PIN à 6 chiffres : ", "prompt_pick_device": "Choisir [1-{n}] : ",
        "pick_files_title": "Sélectionner des fichiers", "yes": "oui", "no": "non",
        "stun_probing": "Interrogation STUN...", "stun_result": "Adresse publique : {r}", "stun_fail": "Échec STUN : {e}",
        "history_empty": "Historique vide", "history_entry": "[{t}] {f} ({s} octets) receive={r}",
        "history_cleared": "Historique effacé", "history_deleted": "Supprimé : {f}",
        "history_bad_index": "Entrée inexistante : {n}", "history_missing": "Fichier absent : {p}",
        "not_zip": "Ce n'est pas un ZIP : {p}",
        "cfg_title": "Configuration actuelle", "cfg_alias": "Alias", "cfg_port": "Port", "cfg_savedir": "Dossier de réception",
        "cfg_pin": "PIN par défaut", "cfg_auto": "Acceptation automatique", "cfg_topic": "Sujet NTFY", "cfg_fp": "Empreinte",
        "cfg_lang": "Langue", "cfg_none": "(aucun)", "cfg_default": "(par défaut)",
        "cfg_menu_alias": "Changer l'alias", "cfg_menu_port": "Changer le port", "cfg_menu_savedir": "Changer le dossier de réception",
        "cfg_menu_pin": "Changer le PIN", "cfg_menu_auto": "Basculer l'acceptation automatique", "cfg_menu_topic": "Changer le sujet NTFY",
        "cfg_menu_regen_fp": "Régénérer l'empreinte", "cfg_menu_reset": "Réinitialiser la configuration", "cfg_menu_lang": "Changer la langue",
        "cfg_menu_back": "Retour", "cfg_prompt_alias": "Nouvel alias [{d}] : ", "cfg_prompt_port": "Nouveau port [{d}] : ",
        "cfg_prompt_savedir": "Nouveau dossier [{d}] : ", "cfg_prompt_pin": "Nouveau PIN [{d}] : ",
        "cfg_prompt_topic": "Nouveau sujet [{d}] : ", "cfg_confirm_reset": "Tout réinitialiser ? [y/N] : ",
        "cfg_reset_done": "Configuration réinitialisée", "cfg_not_exist": "Configuration introuvable",
        "cfg_set_done": "{k} = {v} défini", "cfg_unset_done": "{u} effacé",
        "cfg_invalid_port": "Port 1-65535", "cfg_invalid_set": "Format : --set k=v",
        "cfg_invalid_lang": "Langue non prise en charge : {l}", "cfg_lang_choice": "Langue [{choices}] : ",
        "cfg_file": "Fichier de configuration", "help_text": "Aide", "confirm_receive_30s": "Recevoir de [{a}] ? (refus automatique dans 30 s) [Y/n] : ",
        "firewall_tip": "\n💡 Astuce : si le service distant tourne bien, vérifiez :\n  1. Le pare-feu Windows bloque-t-il le programme ? (autorisez Python dans les paramètres)\n  2. Les deux appareils sont-ils sur le même réseau local ? (isolation AP du routeur ?)\n  3. Sinon, essayez l'option 4 -> 2 pour saisir l'IP manuellement.\n",
        "deep_scanning": "🌐 Délai UDP écoulé, scan HTTP approfondi sur {ip}.1/24 ...",
        "web_title": "lspy — état de réception", "web_alias": "Alias", "web_port": "Port",
        "web_fp": "Empreinte", "web_recent": "Réceptions récentes", "web_none": "Rien reçu pour l'instant",
        "web_hint": "Laissez ce service actif. Les fichiers envoyés depuis LocalSend sont enregistrés automatiquement.",
        "reg_fail": "Échec de l'enregistrement auprès du récepteur : {e}", "register_ok": "Annoncé au récepteur",
        "send_fallback": "La cible n'a pas d'endpoint v2.1, retour à prepare-upload",
        "files_skipped": "{n} fichier(s) ignoré(s) par la politique d'extensions", "https_send": "TLS activé pour la cible",
        "unzip_unsafe": "Extraction refusée : entrée non sûre {p}", "http_scan_https": "Sondage aussi des hôtes HTTPS",
        "bound_port": "Lié au port {p}", "no_write_perm": "Impossible d'écrire dans {p} : {e}",
        "integrity_fail": "Contrôle d'intégrité échoué pour {f}", "chunk_hash": "Somme de contrôle du bloc {i} incorrecte, nouvelle tentative",
        "version": "Version", "web_alone": "Page web sur {u}",
        "web_tab_upload": "Envoyer à cet appareil", "web_tab_download": "Télécharger depuis cet appareil", "web_tab_text": "Message texte",
        "web_upload_hint": "Déposez des fichiers ici ou cliquez pour choisir. Ils sont enregistrés dans le dossier de réception.", "web_download_empty": "Rien reçu pour l'instant", "web_text_hint": "Le texte est copié dans le presse-papiers, ou enregistré en .txt si celui-ci est indisponible.",
        "web_send": "Envoyer", "web_clip_btn": "Lire le presse-papiers", "web_pin_prompt": "PIN d'accès",
        "web_up_ok": "Envoyé", "web_text_ok": "Texte envoyé", "web_pin_bad": "PIN requis",
        "web_uploaded": "Envoyé : {f}",
        "menu_serve_fg": "Passer au service au premier plan (progression détaillée)",
        "auto_start": "Démarrage du récepteur en arrière-plan...", "auto_start_fail": "Échec du démarrage automatique : {e}",
        "port_in_use": "Port {p} indisponible : {e}",
        "port_in_use_tip": "L'application LocalSend ou une seconde instance de lspy occupe probablement ce port. Fermez-la, ou choisissez un autre port avec -p 0 / -p 53318.",
        "port_fallback": "Le port {p} est pris, passage au port {q} attribué par le système (utilisez -p pour le fixer).",
        "mc_port_busy": "Le port multicast 53317 est occupé (souvent LocalSend lancé à côté) ; écoute multicast ignorée, la découverte HTTP fonctionne toujours. Ajoutez --no-multicast pour masquer ce message.",
        "fg_hint": "Récepteur au premier plan actif, Ctrl+C l'arrête et revient au menu",
        "send_how": "1. Rechercher automatiquement les appareils\n2. Saisir l'IP manuellement", "send_choose": "Choisir [1-2] : ",
        "prompt_ip": "IP cible (ex. 192.168.1.10) : ", "input_error": "Erreur de saisie : {e}",
        "menu_banner": "lspy — CLI compatible LocalSend",
        "menu_devices": "Appareils proches", "no_devices_yet": "Pas encore analysé, choisissez 2 pour lancer l'analyse",
    },
    "ja": {
        "lang_name": "日本語", "menu_title": "lspy — LocalSend 互換 CLI",
        "menu_info": "端末情報を表示", "menu_scan": "近くの端末を検索",
        "menu_serve": "受信サービスを起動（前面）", "menu_send": "ファイルを端末へ送信",
        "menu_cross_send": "ネットワーク越し送信（ntfy.sh）", "menu_cross_recv": "ネットワーク越し受信（ntfy.sh）",
        "menu_history": "履歴", "menu_config": "設定", "menu_exit": "終了",
        "choose_prompt": "選択 [{choices}]: ", "invalid_option": "無効な選択",
        "bye": "終了しました", "scanning_short": "LAN を検索中...", "scanning_long": "LAN を検索中（タイムアウト {t} 秒）...",
        "scan_none": "端末が見つかりません", "scan_found_n": "{n} 台の端末が見つかりました:", "found_device": "検出: {d}",
        "scan_target": "対象端末を検索中...", "device_not_found": "端末が見つかりません: {n}",
        "specify_device_or_ip": "--device か --ip を指定してください",
        "multicast_send_fail": "マルチキャスト送信に失敗: {e}", "multicast_listen_fail": "マルチキャスト受信に失敗: {e}",
        "http_listening": "HTTP 待受中 {h}:{p}", "https_listening": "HTTPS 待受中 {h}:{p}",
        "save_dir": "保存先: {d}", "pin_enabled": "PIN 有効: {p}", "mc_listening": "マルチキャスト {g}:{p}",
        "mc_reply": "MC 応答: {a} @ {ip}", "stopping": "停止中...",
        "ask_receive": "[{a}] @ {ip} から {n} ファイル。受け取りますか？ [Y/n]: ",
        "session_created": "セッション {s}、{n} ファイル待機中", "receive_done": "受信: {f} -> {p}",
        "receive_progress": "{f}: {p}% ({r}/{t})", "write_fail": "書き込み失敗: {e}",
        "send_preparing": "{n} ファイル（{s} バイト）を送信 -> {d}", "pin_required": "相手は PIN を要求しています（--pin）",
        "conn_fail": "接続失敗: {e}", "send_rejected": "拒否されました（HTTP {c}）",
        "no_session": "不正な応答: sessionId がありません", "send_started": "セッション {s}... アップロード中",
        "send_progress": "アップロード: {p}% ({s}/{t})", "send_fail": "アップロード失敗 {f}: {e}",
        "send_done": "完了 {a}/{b} ファイル", "https_unsupported": "相手は HTTPS を使用（送信側は未対応）",
        "skip_missing": "スキップ: {p}", "no_files": "ファイルがありません",
        "cross_pin": "クロス PIN: {p}  (受信側: lspy cross-recv {p})", "packing": "圧縮中...",
        "packed": "圧縮完了: {n} バイト", "cross_progress": "送信: {s}/{t} ({p}%)",
        "chunk_fail": "チャンク {i} 失敗: {e}", "cross_sent": "送信済み", "listening_pin": "PIN 待受中: {p}",
        "cross_recv_progress": "{n} バイト受信", "cross_timeout": "タイムアウト", "no_data": "データなし",
        "saved": "保存: {p}（{n} バイト）", "unzip_ok": "展開: {d}", "unzip_fail": "展開失敗: {e}",
        "blocked_ext": "ブロック: {f}", "blocked_list": "ブラックリストでブロック: {a}",
        "invalid_port": "ポートが不正", "invalid_input": "入力が不正", "index_out_of_range": "範囲外です",
        "no_files_provided": "ファイルが指定されていません", "pin_empty": "PIN が空です", "no_file_selected": "ファイルが選択されていません",
        "no_device_scan": "端末が見つかりません。相手のサービスを確認してください", "prompt_files": "ファイルパス（カンマ区切り）: ",
        "prompt_save_dir": "保存先 [{d}]: ", "prompt_pin_off": "PIN（空=無効）: ",
        "prompt_pin_on": "PIN（空={p} を使用）: ", "prompt_ask_each": "受信ごとに確認しますか？ [y/N]（現在: {v}）: ",
        "prompt_target_pin": "相手の PIN（空=なし）: ", "prompt_cross_pin": "PIN（空=ランダム）: ",
        "prompt_cross_recv_pin": "6 桁の PIN: ", "prompt_pick_device": "選択 [1-{n}]: ",
        "pick_files_title": "ファイルを選択", "yes": "はい", "no": "いいえ",
        "stun_probing": "STUN を問い合わせ中...", "stun_result": "グローバルアドレス: {r}", "stun_fail": "STUN 失敗: {e}",
        "history_empty": "履歴はありません", "history_entry": "[{t}] {f}（{s} バイト）receive={r}",
        "history_cleared": "履歴を消去しました", "history_deleted": "削除しました: {f}",
        "history_bad_index": "その番号の記録はありません: {n}", "history_missing": "ファイルが見つかりません: {p}",
        "not_zip": "ZIP ファイルではありません: {p}",
        "cfg_title": "現在の設定", "cfg_alias": "エイリアス", "cfg_port": "ポート", "cfg_savedir": "保存先",
        "cfg_pin": "既定の PIN", "cfg_auto": "自動受け取り", "cfg_topic": "NTFY トピック", "cfg_fp": "フィンガープリント",
        "cfg_lang": "言語", "cfg_none": "（なし）", "cfg_default": "（既定）",
        "cfg_menu_alias": "エイリアスを変更", "cfg_menu_port": "ポートを変更", "cfg_menu_savedir": "保存先を変更",
        "cfg_menu_pin": "PIN を変更", "cfg_menu_auto": "自動受け取りを切り替え", "cfg_menu_topic": "NTFY トピックを変更",
        "cfg_menu_regen_fp": "フィンガープリントを再生成", "cfg_menu_reset": "設定をリセット", "cfg_menu_lang": "言語を変更",
        "cfg_menu_back": "戻る", "cfg_prompt_alias": "新しいエイリアス [{d}]: ", "cfg_prompt_port": "新しいポート [{d}]: ",
        "cfg_prompt_savedir": "新しい保存先 [{d}]: ", "cfg_prompt_pin": "新しい PIN [{d}]: ",
        "cfg_prompt_topic": "新しいトピック [{d}]: ", "cfg_confirm_reset": "すべてリセットしますか？ [y/N]: ",
        "cfg_reset_done": "設定をリセットしました", "cfg_not_exist": "設定ファイルが見つかりません",
        "cfg_set_done": "{k} = {v} を設定しました", "cfg_unset_done": "{u} を消去しました",
        "cfg_invalid_port": "ポートは 1-65535", "cfg_invalid_set": "形式: --set k=v",
        "cfg_invalid_lang": "未対応の言語: {l}", "cfg_lang_choice": "言語 [{choices}]: ",
        "cfg_file": "設定ファイル", "help_text": "ヘルプ", "confirm_receive_30s": "[{a}] から受信しますか？（30 秒で自動拒否） [Y/n]: ",
        "firewall_tip": "\n💡 ヒント: 相手のサービスが動いている場合は次を確認してください:\n  1. Windows ファイアウォールがこのプログラムを遮断していないか（設定で Python を許可）\n  2. 同じ LAN にいるか（ルーターの AP アイソレーション）\n  3. それでもだめなら、オプション 4 -> 2 で相手の IP を手入力して送信してください。\n",
        "deep_scanning": "🌐 UDP がタイムアウト。HTTP 深掘りスキャンを開始します: {ip}.1/24 ...",
        "web_title": "lspy — 受信状態", "web_alias": "エイリアス", "web_port": "ポート",
        "web_fp": "フィンガープリント", "web_recent": "最近の受信", "web_none": "まだ受信していません",
        "web_hint": "このサービスを起動したままにしてください。LocalSend から送られたファイルは自動保存されます。",
        "reg_fail": "受信側への登録に失敗: {e}", "register_ok": "受信側へ通知しました",
        "send_fallback": "相手に v2.1 エンドポイントがありません。prepare-upload に切り替えます",
        "files_skipped": "拡張子ポリシーにより {n} ファイルをスキップ", "https_send": "相手に対して TLS を有効化",
        "unzip_unsafe": "展開を拒否: 安全でないエントリ {p}", "http_scan_https": "HTTPS ホストも同時に探索",
        "bound_port": "ポート {p} にバインドしました", "no_write_perm": "{p} に書き込めません: {e}",
        "integrity_fail": "{f} の整合性チェックに失敗", "chunk_hash": "チャンク {i} のチェックサム不一致、再試行します",
        "version": "バージョン", "web_alone": "Web ページ: {u}",
        "web_tab_upload": "この端末へ送信", "web_tab_download": "端末からダウンロード", "web_tab_text": "テキスト送信",
        "web_upload_hint": "ファイルをドロップするかクリックして選択。受信フォルダーに保存されます。", "web_download_empty": "まだファイルを受信していません", "web_text_hint": "テキストはクリップボードにコピーされます。クリップボードが使えない場合は txt ファイルとして保存されます。",
        "web_send": "送信", "web_clip_btn": "クリップボードを読み取る", "web_pin_prompt": "アクセス PIN",
        "web_up_ok": "アップロード済み", "web_text_ok": "送信済み", "web_pin_bad": "PIN が必要",
        "web_uploaded": "アップロード済み {f}",
        "menu_serve_fg": "前面サービスに切り替え（詳細な進捗）",
        "auto_start": "バックグラウンド受信サービスを起動中...", "auto_start_fail": "自動起動に失敗: {e}",
        "port_in_use": "ポート {p} が使用できません: {e}",
        "port_in_use_tip": "LocalSend デスクトップ版や別の lspy がこのポートを使っている可能性があります。終了するか、-p 0 / -p 53318 で別ポートを指定してください。",
        "port_fallback": "ポート {p} は使用中です。OS が割り当てたポート {q} に切り替えました（固定するには -p）。",
        "mc_port_busy": "マルチキャストポート 53317 が使用中です（多くの場合 LocalSend デスクトップ版と併用）。マルチキャスト受信をスキップしましたが、HTTP 探索は利用できます。--no-multicast を付けるとこの表示を消せます。",
        "fg_hint": "前面受信を実行中。Ctrl+C で停止してメニューに戻ります",
        "send_how": "1. 近くの端末を自動検索\n2. IP を手入力", "send_choose": "選択 [1-2]: ",
        "prompt_ip": "相手の IP（例: 192.168.1.10）: ", "input_error": "入力エラー: {e}",
        "menu_banner": "lspy — LocalSend 互換 CLI",
        "menu_devices": "近くの端末", "no_devices_yet": "まだ検索していません。2 を選んで検索してください",
    },
    "ko": {
        "lang_name": "한국어", "menu_title": "lspy — LocalSend 호환 CLI",
        "menu_info": "기기 정보 표시", "menu_scan": "주변 기기 검색",
        "menu_serve": "수신 서비스 시작 (포그라운드)", "menu_send": "기기로 파일 보내기",
        "menu_cross_send": "네트워크 간 전송 (ntfy.sh)", "menu_cross_recv": "네트워크 간 수신 (ntfy.sh)",
        "menu_history": "기록", "menu_config": "설정", "menu_exit": "종료",
        "choose_prompt": "선택 [{choices}]: ", "invalid_option": "잘못된 선택",
        "bye": "종료되었습니다", "scanning_short": "LAN 검색 중...", "scanning_long": "LAN 검색 중 (제한 시간 {t}초)...",
        "scan_none": "기기를 찾지 못했습니다", "scan_found_n": "{n}대의 기기를 찾았습니다:", "found_device": "발견: {d}",
        "scan_target": "대상 기기 검색 중...", "device_not_found": "기기를 찾을 수 없음: {n}",
        "specify_device_or_ip": "--device 또는 --ip 를 지정하세요",
        "multicast_send_fail": "멀티캐스트 전송 실패: {e}", "multicast_listen_fail": "멀티캐스트 수신 실패: {e}",
        "http_listening": "HTTP 대기 {h}:{p}", "https_listening": "HTTPS 대기 {h}:{p}",
        "save_dir": "저장 경로: {d}", "pin_enabled": "PIN 사용: {p}", "mc_listening": "멀티캐스트 {g}:{p}",
        "mc_reply": "MC 응답: {a} @ {ip}", "stopping": "중지 중...",
        "ask_receive": "[{a}] @ {ip} 에서 {n}개 파일. 받으시겠습니까? [Y/n]: ",
        "session_created": "세션 {s}, {n}개 파일 대기 중", "receive_done": "수신: {f} -> {p}",
        "receive_progress": "{f}: {p}% ({r}/{t})", "write_fail": "기록 실패: {e}",
        "send_preparing": "{n}개 파일({s} 바이트) 전송 -> {d}", "pin_required": "상대가 PIN 을 요구합니다 (--pin)",
        "conn_fail": "연결 실패: {e}", "send_rejected": "거부됨 (HTTP {c})",
        "no_session": "잘못된 응답: sessionId 없음", "send_started": "세션 {s}... 업로드 중",
        "send_progress": "업로드: {p}% ({s}/{t})", "send_fail": "업로드 실패 {f}: {e}",
        "send_done": "완료 {a}/{b}개 파일", "https_unsupported": "대상이 HTTPS 사용 (전송 미지원)",
        "skip_missing": "건너뜀: {p}", "no_files": "파일 없음",
        "cross_pin": "크로스 PIN: {p}  (수신 측: lspy cross-recv {p})", "packing": "압축 중...",
        "packed": "압축 완료: {n} 바이트", "cross_progress": "전송: {s}/{t} ({p}%)",
        "chunk_fail": "청크 {i} 실패: {e}", "cross_sent": "전송 완료", "listening_pin": "PIN 대기: {p}",
        "cross_recv_progress": "{n} 바이트 수신", "cross_timeout": "시간 초과", "no_data": "데이터 없음",
        "saved": "저장됨: {p} ({n} 바이트)", "unzip_ok": "압축 해제: {d}", "unzip_fail": "압축 해제 실패: {e}",
        "blocked_ext": "차단됨: {f}", "blocked_list": "블랙리스트로 차단: {a}",
        "invalid_port": "잘못된 포트", "invalid_input": "잘못된 입력", "index_out_of_range": "범위를 벗어남",
        "no_files_provided": "파일이 지정되지 않았습니다", "pin_empty": "PIN 이 비어 있습니다", "no_file_selected": "선택된 파일이 없습니다",
        "no_device_scan": "기기가 없습니다. 상대 서비스를 확인하세요", "prompt_files": "파일 경로 (쉼표로 구분): ",
        "prompt_save_dir": "저장 경로 [{d}]: ", "prompt_pin_off": "PIN (비우면 사용 안 함): ",
        "prompt_pin_on": "PIN (비우면 {p} 사용): ", "prompt_ask_each": "수신할 때마다 확인할까요? [y/N] (현재: {v}): ",
        "prompt_target_pin": "대상 PIN (비우면 없음): ", "prompt_cross_pin": "PIN (비우면 임의): ",
        "prompt_cross_recv_pin": "6자리 PIN: ", "prompt_pick_device": "선택 [1-{n}]: ",
        "pick_files_title": "파일 선택", "yes": "예", "no": "아니오",
        "stun_probing": "STUN 조회 중...", "stun_result": "공인 주소: {r}", "stun_fail": "STUN 실패: {e}",
        "history_empty": "기록 없음", "history_entry": "[{t}] {f} ({s} 바이트) receive={r}",
        "history_cleared": "기록을 지웠습니다", "history_deleted": "삭제됨: {f}",
        "history_bad_index": "해당 기록이 없습니다: {n}", "history_missing": "파일이 없습니다: {p}",
        "not_zip": "ZIP 파일이 아닙니다: {p}",
        "cfg_title": "현재 설정", "cfg_alias": "별칭", "cfg_port": "포트", "cfg_savedir": "저장 경로",
        "cfg_pin": "기본 PIN", "cfg_auto": "자동 수락", "cfg_topic": "NTFY 토픽", "cfg_fp": "지문",
        "cfg_lang": "언어", "cfg_none": "(없음)", "cfg_default": "(기본)",
        "cfg_menu_alias": "별칭 변경", "cfg_menu_port": "포트 변경", "cfg_menu_savedir": "저장 경로 변경",
        "cfg_menu_pin": "PIN 변경", "cfg_menu_auto": "자동 수락 전환", "cfg_menu_topic": "NTFY 토픽 변경",
        "cfg_menu_regen_fp": "지문 재생성", "cfg_menu_reset": "설정 초기화", "cfg_menu_lang": "언어 변경",
        "cfg_menu_back": "뒤로", "cfg_prompt_alias": "새 별칭 [{d}]: ", "cfg_prompt_port": "새 포트 [{d}]: ",
        "cfg_prompt_savedir": "새 경로 [{d}]: ", "cfg_prompt_pin": "새 PIN [{d}]: ",
        "cfg_prompt_topic": "새 토픽 [{d}]: ", "cfg_confirm_reset": "모두 초기화할까요? [y/N]: ",
        "cfg_reset_done": "설정을 초기화했습니다", "cfg_not_exist": "설정 파일을 찾을 수 없습니다",
        "cfg_set_done": "{k} = {v} 설정됨", "cfg_unset_done": "{u} 삭제됨",
        "cfg_invalid_port": "포트 1-65535", "cfg_invalid_set": "형식: --set k=v",
        "cfg_invalid_lang": "지원하지 않는 언어: {l}", "cfg_lang_choice": "언어 [{choices}]: ",
        "cfg_file": "설정 파일", "help_text": "도움말", "confirm_receive_30s": "[{a}] 에서 수신할까요? (30초 후 자동 거부) [Y/n]: ",
        "firewall_tip": "\n💡 팁: 상대 서비스가 켜져 있다면 다음을 확인하세요:\n  1. Windows 방화벽이 이 프로그램을 막고 있는지 (설정에서 Python 허용)\n  2. 같은 LAN 에 있는지 (공유기 AP 격리)\n  3. 그래도 안 되면 옵션 4 -> 2 로 상대 IP 를 직접 입력하세요.\n",
        "deep_scanning": "🌐 UDP 시간 초과, {ip}.1/24 대역 HTTP 심층 스캔 시작 ...",
        "web_title": "lspy — 수신 상태", "web_alias": "별칭", "web_port": "포트",
        "web_fp": "지문", "web_recent": "최근 수신", "web_none": "아직 수신 기록 없음",
        "web_hint": "이 서비스를 계속 실행하세요. LocalSend 에서 보낸 파일은 자동 저장됩니다.",
        "reg_fail": "수신 측 등록 실패: {e}", "register_ok": "수신 측에 알렸습니다",
        "send_fallback": "대상에 v2.1 엔드포인트가 없어 prepare-upload 로 대체합니다",
        "files_skipped": "확장자 정책으로 {n}개 파일 건너뜀", "https_send": "대상에 TLS 활성화",
        "unzip_unsafe": "압축 해제 거부: 안전하지 않은 항목 {p}", "http_scan_https": "HTTPS 호스트도 함께 탐색",
        "bound_port": "포트 {p} 에 바인딩됨", "no_write_perm": "{p} 에 쓸 수 없습니다: {e}",
        "integrity_fail": "{f} 무결성 검사 실패", "chunk_hash": "청크 {i} 체크섬 불일치, 재시도",
        "version": "버전", "web_alone": "웹 페이지: {u}",
        "web_tab_upload": "이 기기로 보내기", "web_tab_download": "기기에서 다운로드", "web_tab_text": "텍스트 보내기",
        "web_upload_hint": "파일을 끌어다 놓거나 클릭해 선택하세요. 받기 폴더에 저장됩니다.", "web_download_empty": "아직 받은 파일이 없습니다", "web_text_hint": "텍스트는 클립보드에 복사되며, 클립보드를 쓸 수 없으면 txt 파일로 저장됩니다.",
        "web_send": "보내기", "web_clip_btn": "클립보드 읽기", "web_pin_prompt": "접근 PIN",
        "web_up_ok": "업로드됨", "web_text_ok": "전송됨", "web_pin_bad": "PIN 필요",
        "web_uploaded": "업로드됨 {f}",
        "menu_serve_fg": "포그라운드 서비스로 전환 (상세 진행)",
        "auto_start": "백그라운드 수신 서비스 시작 중...", "auto_start_fail": "자동 시작 실패: {e}",
        "port_in_use": "포트 {p} 사용 불가: {e}",
        "port_in_use_tip": "LocalSend 데스크톱 앱이나 다른 lspy 인스턴스가 이 포트를 점유하고 있을 수 있습니다. 종료하거나 -p 0 / -p 53318 로 다른 포트를 지정하세요.",
        "port_fallback": "포트 {p} 가 사용 중이라 OS 가 할당한 포트 {q} 로 전환했습니다 (고정하려면 -p).",
        "mc_port_busy": "멀티캐스트 포트 53317 이 사용 중입니다 (대개 LocalSend 데스크톱과 병행). 멀티캐스트 수신을 건너뛰었지만 HTTP 탐색은 계속 사용할 수 있습니다. --no-multicast 로 이 안내를 끌 수 있습니다.",
        "fg_hint": "포그라운드 수신 실행 중, Ctrl+C 로 중지하고 메뉴로 돌아갑니다",
        "send_how": "1. 주변 기기 자동 검색\n2. IP 직접 입력", "send_choose": "선택 [1-2]: ",
        "prompt_ip": "대상 IP (예: 192.168.1.10): ", "input_error": "입력 오류: {e}",
        "menu_banner": "lspy — LocalSend 호환 CLI",
        "menu_devices": "주변 기기", "no_devices_yet": "아직 검색하지 않았습니다. 2 를 선택해 검색하세요",
    },
    "zh_TW": {
        "lang_name": "繁體中文", "menu_title": "lspy — LocalSend 相容命令列工具",
        "menu_info": "顯示本機資訊", "menu_scan": "掃描附近裝置", "menu_serve": "啟動接收服務（前景）",
        "menu_send": "傳送檔案到裝置", "menu_cross_send": "跨網傳送（ntfy.sh）", "menu_cross_recv": "跨網接收（ntfy.sh）",
        "menu_history": "歷史紀錄", "menu_config": "設定", "menu_exit": "離開",
        "choose_prompt": "請選擇 [{choices}]: ", "invalid_option": "無效選項", "bye": "已離開",
        "scanning_short": "正在掃描區域網路...", "scanning_long": "掃描網路（逾時 {t}s）...",
        "scan_none": "未發現裝置", "scan_found_n": "共發現 {n} 個裝置：", "found_device": "發現：{d}",
        "scan_target": "掃描目標...", "device_not_found": "未找到：{n}", "specify_device_or_ip": "請指定 --device 或 --ip",
        "multicast_send_fail": "群播傳送失敗：{e}", "multicast_listen_fail": "群播監聽失敗：{e}",
        "http_listening": "HTTP 監聽 {h}:{p}", "https_listening": "HTTPS 監聽 {h}:{p}",
        "save_dir": "儲存目錄：{d}", "pin_enabled": "PIN：{p}", "mc_listening": "群播監聽 {g}:{p}",
        "mc_reply": "群播回應：{a} @ {ip}", "stopping": "正在停止...",
        "ask_receive": "來自 [{a}] @ {ip} 的 {n} 個檔案，接收？[Y/n]：",
        "session_created": "工作階段 {s} 等待 {n} 個檔案", "receive_done": "已接收：{f} -> {p}",
        "receive_progress": "{f}：{p}% ({r}/{t})", "write_fail": "寫入失敗：{e}",
        "send_preparing": "傳送 {n} 個檔案（{s} 位元組）→ {d}", "pin_required": "對方需要 PIN（--pin）",
        "conn_fail": "連線失敗：{e}", "send_rejected": "被拒絕（HTTP {c}）", "no_session": "回應缺少 sessionId",
        "send_started": "工作階段 {s}... 上傳中", "send_progress": "上傳：{p}% ({s}/{t})", "send_fail": "上傳失敗 {f}：{e}",
        "send_done": "完成 {a}/{b} 個", "https_unsupported": "目標為 HTTPS（傳送端暫不支援）",
        "skip_missing": "跳過：{p}", "no_files": "無檔案",
        "cross_pin": "跨網 PIN：{p}（接收：lspy cross-recv {p}）", "packing": "封裝中...",
        "packed": "已封裝：{n} 位元組", "cross_progress": "傳送：{s}/{t} ({p}%)", "chunk_fail": "分塊 {i} 失敗：{e}",
        "cross_sent": "已傳送", "listening_pin": "監聽 PIN：{p}", "cross_recv_progress": "已收 {n} 位元組",
        "cross_timeout": "逾時", "no_data": "無資料", "saved": "已儲存：{p}（{n} 位元組）",
        "unzip_ok": "已解壓：{d}", "unzip_fail": "解壓失敗：{e}", "blocked_ext": "攔截：{f}",
        "blocked_list": "黑名單拒絕：{a}", "invalid_port": "連接埠無效", "invalid_input": "輸入無效",
        "index_out_of_range": "序號超出範圍", "no_files_provided": "未提供檔案", "pin_empty": "PIN 為空",
        "no_file_selected": "未選擇檔案", "no_device_scan": "未發現裝置，請確認對方已啟動",
        "prompt_files": "檔案路徑（逗號分隔）：", "prompt_save_dir": "儲存目錄 [{d}]: ",
        "prompt_pin_off": "PIN（留空停用）：", "prompt_pin_on": "PIN（留空使用 {p}）：",
        "prompt_ask_each": "每次接收都詢問？[y/N]（目前：{v}）：", "prompt_target_pin": "目標 PIN（留空不驗證）：",
        "prompt_cross_pin": "PIN（留空隨機）：", "prompt_cross_recv_pin": "6 位數 PIN：",
        "prompt_pick_device": "選擇 [1-{n}]: ", "pick_files_title": "選擇檔案", "yes": "是", "no": "否",
        "stun_probing": "STUN 探測...", "stun_result": "公網位址：{r}", "stun_fail": "STUN 失敗：{e}",
        "history_empty": "無歷史紀錄", "history_entry": "[{t}] {f}（{s} 位元組）receive={r}",
        "history_cleared": "已清空歷史記錄", "history_deleted": "已刪除：{f}",
        "history_bad_index": "沒有這筆記錄：{n}", "history_missing": "檔案已不存在：{p}",
        "not_zip": "不是 ZIP 檔案：{p}",
        "cfg_title": "目前設定", "cfg_alias": "別名", "cfg_port": "連接埠", "cfg_savedir": "儲存目錄",
        "cfg_pin": "預設 PIN", "cfg_auto": "自動接受", "cfg_topic": "NTFY 主題", "cfg_fp": "指紋",
        "cfg_lang": "語言", "cfg_none": "（未啟用）", "cfg_default": "（預設）",
        "cfg_menu_alias": "修改別名", "cfg_menu_port": "修改連接埠", "cfg_menu_savedir": "修改儲存目錄",
        "cfg_menu_pin": "修改 PIN", "cfg_menu_auto": "切換自動接受", "cfg_menu_topic": "修改 NTFY 主題",
        "cfg_menu_regen_fp": "重新產生指紋", "cfg_menu_reset": "重設全部", "cfg_menu_lang": "修改語言",
        "cfg_menu_back": "返回", "cfg_prompt_alias": "新別名 [{d}]: ", "cfg_prompt_port": "新連接埠 [{d}]: ",
        "cfg_prompt_savedir": "新目錄 [{d}]: ", "cfg_prompt_pin": "新 PIN [{d}]: ",
        "cfg_prompt_topic": "新主題 [{d}]: ", "cfg_confirm_reset": "確認重設？[y/N]：",
        "cfg_reset_done": "已重設", "cfg_not_exist": "設定檔不存在", "cfg_set_done": "已設定 {k} = {v}",
        "cfg_unset_done": "已取消 {u}", "cfg_invalid_port": "連接埠 1-65535", "cfg_invalid_set": "格式：--set k=v",
        "cfg_invalid_lang": "不支援：{l}", "cfg_lang_choice": "語言 [{choices}]: ", "cfg_file": "設定檔",
        "help_text": "說明", "confirm_receive_30s": "接收 [{a}]？（30 秒後自動拒絕）[Y/n]：",
        "firewall_tip": "\n💡 提示：如果確認對方已開啟服務，請檢查：\n  1. Windows 防火牆是否攔截了程式（請在設定中允許 Python 通過防火牆）\n  2. 裝置是否在同一個區域網路（路由器是否開啟了 AP 隔離）\n  3. 如果仍不行，請嘗試選項 4 -> 2 手動輸入對方 IP 傳送。\n",
        "deep_scanning": "🌐 UDP 掃描逾時，正在啟動 HTTP 深度掃描網段 {ip}.1/24 ...",
        "web_title": "lspy — 接收狀態", "web_alias": "別名", "web_port": "連接埠", "web_fp": "指紋",
        "web_recent": "最近接收", "web_none": "尚無接收紀錄",
        "web_hint": "保持服務執行，LocalSend 傳來的檔案會自動儲存。",
        "reg_fail": "向接收端註冊失敗：{e}", "register_ok": "已向接收端廣播身分",
        "send_fallback": "對方不支援 v2.1 介面，回退到 prepare-upload",
        "files_skipped": "因副檔名策略跳過 {n} 個檔案", "https_send": "已對目標啟用 TLS",
        "unzip_unsafe": "解壓被拒絕：非法項目 {p}", "http_scan_https": "同時探測 HTTPS 主機",
        "bound_port": "已綁定連接埠 {p}", "no_write_perm": "無法寫入 {p}：{e}",
        "integrity_fail": "{f} 完整性驗證失敗", "chunk_hash": "分塊 {i} 驗證失敗，重試中",
        "version": "版本", "web_alone": "網頁介面：{u}",
        "web_tab_upload": "上傳到本機", "web_tab_download": "下載本機檔案", "web_tab_text": "傳送文字",
        "web_upload_hint": "拖入檔案或點擊選擇，上傳後儲存到接收目錄", "web_download_empty": "還沒有接收過檔案", "web_text_hint": "文字會寫入本機剪貼簿；剪貼簿不可用時儲存為 txt 檔案",
        "web_send": "傳送", "web_clip_btn": "讀取剪貼簿", "web_pin_prompt": "存取 PIN",
        "web_up_ok": "已上傳", "web_text_ok": "已傳送", "web_pin_bad": "需要 PIN",
        "web_uploaded": "已上傳 {f}",
        "menu_serve_fg": "切換為前景服務（詳細進度）",
        "auto_start": "正在自動啟動背景接收服務...", "auto_start_fail": "自動啟動失敗：{e}",
        "port_in_use": "連接埠 {p} 無法使用：{e}",
        "port_in_use_tip": "通常是本機已有 LocalSend 桌面版或另一個 lspy 實例佔用了該連接埠。請關掉它，或用 -p 0 / -p 53318 換一個連接埠。",
        "port_fallback": "連接埠 {p} 已被佔用，已改用系統指派的連接埠 {q}（如需固定請用 -p 指定）。",
        "mc_port_busy": "群播連接埠 53317 已被佔用（通常是與 LocalSend 桌面版共存）；已跳過群播監聽，HTTP 掃描探索仍可用。加 --no-multicast 可關閉此提示。",
        "fg_hint": "前景接收已啟動，按 Ctrl+C 停止並返回選單",
        "send_how": "1. 自動掃描附近裝置\n2. 手動輸入 IP 位址", "send_choose": "請選擇 [1-2]: ",
        "prompt_ip": "目標 IP（如 192.168.1.10）：", "input_error": "輸入錯誤：{e}",
        "menu_banner": "lspy — LocalSend 相容命令列工具",
        "menu_devices": "附近裝置", "no_devices_yet": "尚未掃描，選擇 2 開始掃描",
    },
    "es": {
        "lang_name": "Español", "menu_title": "lspy — CLI compatible con LocalSend",
        "menu_info": "Mostrar info del equipo", "menu_scan": "Buscar dispositivos cercanos",
        "menu_serve": "Iniciar servicio de recepción (primer plano)", "menu_send": "Enviar archivos a un dispositivo",
        "menu_cross_send": "Envío entre redes (ntfy.sh)", "menu_cross_recv": "Recepción entre redes (ntfy.sh)",
        "menu_history": "Historial", "menu_config": "Ajustes", "menu_exit": "Salir",
        "choose_prompt": "Selecciona [{choices}]: ", "invalid_option": "Opción no válida",
        "bye": "Adiós", "scanning_short": "Buscando en la LAN...", "scanning_long": "Buscando en la LAN (límite {t}s)...",
        "scan_none": "No se encontraron dispositivos", "scan_found_n": "{n} dispositivo(s) encontrados:", "found_device": "Encontrado: {d}",
        "scan_target": "Buscando el dispositivo destino...", "device_not_found": "Dispositivo no encontrado: {n}",
        "specify_device_or_ip": "Indica --device o --ip",
        "multicast_send_fail": "Fallo al enviar multicast: {e}", "multicast_listen_fail": "Fallo al escuchar multicast: {e}",
        "http_listening": "HTTP escuchando en {h}:{p}", "https_listening": "HTTPS escuchando en {h}:{p}",
        "save_dir": "Carpeta de destino: {d}", "pin_enabled": "PIN activo: {p}", "mc_listening": "Multicast {g}:{p}",
        "mc_reply": "Respuesta MC: {a} @ {ip}", "stopping": "Deteniendo...",
        "ask_receive": "De [{a}] @ {ip}: {n} archivo(s). ¿Aceptar? [Y/n]: ",
        "session_created": "Sesión {s} esperando {n} archivo(s)", "receive_done": "Recibido: {f} -> {p}",
        "receive_progress": "{f}: {p}% ({r}/{t})", "write_fail": "Fallo de escritura: {e}",
        "send_preparing": "Enviando {n} archivo(s) ({s} bytes) -> {d}", "pin_required": "El destino exige PIN (--pin)",
        "conn_fail": "Error de conexión: {e}", "send_rejected": "Rechazado (HTTP {c})",
        "no_session": "Respuesta no válida: falta sessionId", "send_started": "Sesión {s}... subiendo",
        "send_progress": "Subida: {p}% ({s}/{t})", "send_fail": "Fallo al subir {f}: {e}",
        "send_done": "Hecho {a}/{b} archivo(s)", "https_unsupported": "El destino usa HTTPS (no admitido al enviar)",
        "skip_missing": "Omitido: {p}", "no_files": "Sin archivos",
        "cross_pin": "PIN entre redes: {p}  (recepción: lspy cross-recv {p})", "packing": "Empaquetando...",
        "packed": "Empaquetado: {n} bytes", "cross_progress": "Envío: {s}/{t} ({p}%)",
        "chunk_fail": "Bloque {i} falló: {e}", "cross_sent": "Enviado", "listening_pin": "Escuchando PIN: {p}",
        "cross_recv_progress": "{n} bytes recibidos", "cross_timeout": "Tiempo agotado", "no_data": "Sin datos",
        "saved": "Guardado: {p} ({n} bytes)", "unzip_ok": "Extraído: {d}", "unzip_fail": "Fallo al extraer: {e}",
        "blocked_ext": "Bloqueado: {f}", "blocked_list": "Bloqueado por lista negra: {a}",
        "invalid_port": "Puerto no válido", "invalid_input": "Entrada no válida", "index_out_of_range": "Fuera de rango",
        "no_files_provided": "No se indicaron archivos", "pin_empty": "PIN vacío", "no_file_selected": "Ningún archivo seleccionado",
        "no_device_scan": "Sin dispositivos, comprueba el servicio del otro lado", "prompt_files": "Rutas (separadas por comas): ",
        "prompt_save_dir": "Carpeta de destino [{d}]: ", "prompt_pin_off": "PIN (vacío=desactivado): ",
        "prompt_pin_on": "PIN (vacío={p}): ", "prompt_ask_each": "¿Preguntar en cada recepción? [y/N] (actual: {v}): ",
        "prompt_target_pin": "PIN del destino (vacío=ninguno): ", "prompt_cross_pin": "PIN (vacío=aleatorio): ",
        "prompt_cross_recv_pin": "PIN de 6 dígitos: ", "prompt_pick_device": "Selecciona [1-{n}]: ",
        "pick_files_title": "Seleccionar archivos", "yes": "sí", "no": "no",
        "stun_probing": "Consultando STUN...", "stun_result": "Dirección pública: {r}", "stun_fail": "Fallo de STUN: {e}",
        "history_empty": "Sin historial", "history_entry": "[{t}] {f} ({s} bytes) receive={r}",
        "history_cleared": "Historial borrado", "history_deleted": "Eliminado: {f}",
        "history_bad_index": "No existe esa entrada: {n}", "history_missing": "El archivo ya no existe: {p}",
        "not_zip": "No es un ZIP: {p}",
        "cfg_title": "Configuración actual", "cfg_alias": "Alias", "cfg_port": "Puerto", "cfg_savedir": "Carpeta de destino",
        "cfg_pin": "PIN por defecto", "cfg_auto": "Aceptar automáticamente", "cfg_topic": "Tema NTFY", "cfg_fp": "Huella",
        "cfg_lang": "Idioma", "cfg_none": "(ninguno)", "cfg_default": "(por defecto)",
        "cfg_menu_alias": "Cambiar alias", "cfg_menu_port": "Cambiar puerto", "cfg_menu_savedir": "Cambiar carpeta de destino",
        "cfg_menu_pin": "Cambiar PIN", "cfg_menu_auto": "Alternar aceptación automática", "cfg_menu_topic": "Cambiar tema NTFY",
        "cfg_menu_regen_fp": "Regenerar huella", "cfg_menu_reset": "Restablecer configuración", "cfg_menu_lang": "Cambiar idioma",
        "cfg_menu_back": "Volver", "cfg_prompt_alias": "Nuevo alias [{d}]: ", "cfg_prompt_port": "Nuevo puerto [{d}]: ",
        "cfg_prompt_savedir": "Nueva carpeta [{d}]: ", "cfg_prompt_pin": "Nuevo PIN [{d}]: ",
        "cfg_prompt_topic": "Nuevo tema [{d}]: ", "cfg_confirm_reset": "¿Restablecer todo? [y/N]: ",
        "cfg_reset_done": "Configuración restablecida", "cfg_not_exist": "Configuración no encontrada",
        "cfg_set_done": "{k} = {v} establecido", "cfg_unset_done": "{u} borrado",
        "cfg_invalid_port": "Puerto 1-65535", "cfg_invalid_set": "Formato: --set k=v",
        "cfg_invalid_lang": "Idioma no admitido: {l}", "cfg_lang_choice": "Idioma [{choices}]: ",
        "cfg_file": "Archivo de configuración", "help_text": "Ayuda", "confirm_receive_30s": "¿Recibir de [{a}]? (rechazo automático en 30 s) [Y/n]: ",
        "firewall_tip": "\n💡 Consejo: si el servicio del otro lado está activo, comprueba:\n  1. Si el firewall de Windows bloquea el programa (permite Python en los ajustes)\n  2. Si ambos equipos están en la misma LAN (¿aislamiento AP del router?)\n  3. Si sigue fallando, prueba la opción 4 -> 2 para escribir la IP manualmente.\n",
        "deep_scanning": "🌐 Tiempo UDP agotado, iniciando escaneo HTTP profundo en {ip}.1/24 ...",
        "web_title": "lspy — estado de recepción", "web_alias": "Alias", "web_port": "Puerto",
        "web_fp": "Huella", "web_recent": "Recibido recientemente", "web_none": "Aún no se ha recibido nada",
        "web_hint": "Mantén este servicio en marcha. Los archivos enviados desde LocalSend se guardan automáticamente.",
        "reg_fail": "Fallo al registrarse en el receptor: {e}", "register_ok": "Anunciado al receptor",
        "send_fallback": "El destino no tiene endpoint v2.1; se usa prepare-upload",
        "files_skipped": "{n} archivo(s) omitido(s) por la política de extensiones", "https_send": "TLS activado para el destino",
        "unzip_unsafe": "Extracción rechazada: entrada insegura {p}", "http_scan_https": "También sondeando hosts HTTPS",
        "bound_port": "Vinculado al puerto {p}", "no_write_perm": "No se puede escribir en {p}: {e}",
        "integrity_fail": "Fallo de integridad para {f}", "chunk_hash": "Suma del bloque {i} incorrecta, reintentando",
        "version": "Versión", "web_alone": "Página web en {u}",
        "web_tab_upload": "Enviar a este dispositivo", "web_tab_download": "Descargar desde este dispositivo", "web_tab_text": "Mensaje de texto",
        "web_upload_hint": "Arrastra archivos aquí o haz clic para elegirlos. Se guardan en la carpeta de recepción.", "web_download_empty": "Aún no se ha recibido nada", "web_text_hint": "El texto se copia al portapapeles o se guarda como .txt si no está disponible.",
        "web_send": "Enviar", "web_clip_btn": "Leer portapapeles", "web_pin_prompt": "PIN de acceso",
        "web_up_ok": "Subido", "web_text_ok": "Texto enviado", "web_pin_bad": "Se requiere PIN",
        "web_uploaded": "Subido: {f}",
        "menu_serve_fg": "Pasar al servicio en primer plano (progreso detallado)",
        "auto_start": "Iniciando receptor en segundo plano...", "auto_start_fail": "Fallo del inicio automático: {e}",
        "port_in_use": "Puerto {p} no disponible: {e}",
        "port_in_use_tip": "Probablemente la app LocalSend o una segunda instancia de lspy ocupa este puerto. Ciérrala o elige otro con -p 0 / -p 53318.",
        "port_fallback": "El puerto {p} está ocupado; se cambió al puerto {q} asignado por el sistema (usa -p para fijarlo).",
        "mc_port_busy": "El puerto multicast 53317 está ocupado (normalmente LocalSend escritorio al lado); se omitió la escucha multicast y el descubrimiento HTTP sigue funcionando. Añade --no-multicast para silenciarlo.",
        "fg_hint": "Receptor en primer plano activo; Ctrl+C lo detiene y vuelve al menú",
        "send_how": "1. Buscar dispositivos automáticamente\n2. Escribir la IP manualmente", "send_choose": "Selecciona [1-2]: ",
        "prompt_ip": "IP de destino (p. ej. 192.168.1.10): ", "input_error": "Error de entrada: {e}",
        "menu_banner": "lspy — CLI compatible con LocalSend",
        "menu_devices": "Dispositivos cercanos", "no_devices_yet": "Aún sin escanear; elige 2 para buscar",
    },
    "ru": {
        "lang_name": "Русский", "menu_title": "lspy — CLI, совместимый с LocalSend",
        "menu_info": "Показать сведения об устройстве", "menu_scan": "Поиск устройств рядом",
        "menu_serve": "Запустить службу приёма (передний план)", "menu_send": "Отправить файлы на устройство",
        "menu_cross_send": "Отправка между сетями (ntfy.sh)", "menu_cross_recv": "Приём между сетями (ntfy.sh)",
        "menu_history": "История", "menu_config": "Настройки", "menu_exit": "Выход",
        "choose_prompt": "Выбор [{choices}]: ", "invalid_option": "Неверный вариант",
        "bye": "Выход выполнен", "scanning_short": "Сканирование локальной сети...", "scanning_long": "Сканирование сети (таймаут {t}с)...",
        "scan_none": "Устройства не найдены", "scan_found_n": "Найдено устройств: {n}", "found_device": "Найдено: {d}",
        "scan_target": "Поиск целевого устройства...", "device_not_found": "Устройство не найдено: {n}",
        "specify_device_or_ip": "Укажите --device или --ip",
        "multicast_send_fail": "Ошибка отправки multicast: {e}", "multicast_listen_fail": "Ошибка прослушивания multicast: {e}",
        "http_listening": "HTTP слушает {h}:{p}", "https_listening": "HTTPS слушает {h}:{p}",
        "save_dir": "Папка сохранения: {d}", "pin_enabled": "PIN включён: {p}", "mc_listening": "Multicast {g}:{p}",
        "mc_reply": "Ответ MC: {a} @ {ip}", "stopping": "Остановка...",
        "ask_receive": "От [{a}] @ {ip}: файлов — {n}. Принять? [Y/n]: ",
        "session_created": "Сеанс {s} ожидает файлов: {n}", "receive_done": "Получено: {f} -> {p}",
        "receive_progress": "{f}: {p}% ({r}/{t})", "write_fail": "Ошибка записи: {e}",
        "send_preparing": "Отправка файлов ({n}) на {d}, {s} байт", "pin_required": "Удалённая сторона требует PIN (--pin)",
        "conn_fail": "Ошибка подключения: {e}", "send_rejected": "Отклонено (HTTP {c})",
        "no_session": "Некорректный ответ: нет sessionId", "send_started": "Сеанс {s}... загрузка",
        "send_progress": "Загрузка: {p}% ({s}/{t})", "send_fail": "Ошибка загрузки {f}: {e}",
        "send_done": "Готово {a}/{b} файл(ов)", "https_unsupported": "Цель использует HTTPS (отправка не поддерживается)",
        "skip_missing": "Пропущено: {p}", "no_files": "Нет файлов",
        "cross_pin": "PIN между сетями: {p}  (приём: lspy cross-recv {p})", "packing": "Упаковка...",
        "packed": "Упаковано: {n} байт", "cross_progress": "Отправка: {s}/{t} ({p}%)",
        "chunk_fail": "Блок {i} не удался: {e}", "cross_sent": "Отправлено", "listening_pin": "Ожидание PIN: {p}",
        "cross_recv_progress": "Получено {n} байт", "cross_timeout": "Таймаут", "no_data": "Нет данных",
        "saved": "Сохранено: {p} ({n} байт)", "unzip_ok": "Распаковано: {d}", "unzip_fail": "Ошибка распаковки: {e}",
        "blocked_ext": "Заблокировано: {f}", "blocked_list": "Заблокировано чёрным списком: {a}",
        "invalid_port": "Неверный порт", "invalid_input": "Неверный ввод", "index_out_of_range": "Вне диапазона",
        "no_files_provided": "Файлы не указаны", "pin_empty": "PIN пуст", "no_file_selected": "Файл не выбран",
        "no_device_scan": "Устройств нет, проверьте службу на другой стороне", "prompt_files": "Пути к файлам (через запятую): ",
        "prompt_save_dir": "Папка сохранения [{d}]: ", "prompt_pin_off": "PIN (пусто=выключен): ",
        "prompt_pin_on": "PIN (пусто=использовать {p}): ", "prompt_ask_each": "Спрашивать при каждом приёме? [y/N] (сейчас: {v}): ",
        "prompt_target_pin": "PIN цели (пусто=нет): ", "prompt_cross_pin": "PIN (пусто=случайный): ",
        "prompt_cross_recv_pin": "6-значный PIN: ", "prompt_pick_device": "Выбор [1-{n}]: ",
        "pick_files_title": "Выбор файлов", "yes": "да", "no": "нет",
        "stun_probing": "Запрос STUN...", "stun_result": "Публичный адрес: {r}", "stun_fail": "Ошибка STUN: {e}",
        "history_empty": "История пуста", "history_entry": "[{t}] {f} ({s} байт) receive={r}",
        "history_cleared": "История очищена", "history_deleted": "Удалено: {f}",
        "history_bad_index": "Нет такой записи: {n}", "history_missing": "Файл не найден: {p}",
        "not_zip": "Это не ZIP-файл: {p}",
        "cfg_title": "Текущая конфигурация", "cfg_alias": "Псевдоним", "cfg_port": "Порт", "cfg_savedir": "Папка сохранения",
        "cfg_pin": "PIN по умолчанию", "cfg_auto": "Автоприём", "cfg_topic": "Тема NTFY", "cfg_fp": "Отпечаток",
        "cfg_lang": "Язык", "cfg_none": "(не задано)", "cfg_default": "(по умолчанию)",
        "cfg_menu_alias": "Изменить псевдоним", "cfg_menu_port": "Изменить порт", "cfg_menu_savedir": "Изменить папку сохранения",
        "cfg_menu_pin": "Изменить PIN", "cfg_menu_auto": "Переключить автоприём", "cfg_menu_topic": "Изменить тему NTFY",
        "cfg_menu_regen_fp": "Пересоздать отпечаток", "cfg_menu_reset": "Сбросить конфигурацию", "cfg_menu_lang": "Изменить язык",
        "cfg_menu_back": "Назад", "cfg_prompt_alias": "Новый псевдоним [{d}]: ", "cfg_prompt_port": "Новый порт [{d}]: ",
        "cfg_prompt_savedir": "Новая папка [{d}]: ", "cfg_prompt_pin": "Новый PIN [{d}]: ",
        "cfg_prompt_topic": "Новая тема [{d}]: ", "cfg_confirm_reset": "Сбросить всё? [y/N]: ",
        "cfg_reset_done": "Конфигурация сброшена", "cfg_not_exist": "Файл конфигурации не найден",
        "cfg_set_done": "Установлено {k} = {v}", "cfg_unset_done": "Удалено {u}",
        "cfg_invalid_port": "Порт 1-65535", "cfg_invalid_set": "Формат: --set k=v",
        "cfg_invalid_lang": "Неподдерживаемый язык: {l}", "cfg_lang_choice": "Язык [{choices}]: ",
        "cfg_file": "Файл конфигурации", "help_text": "Справка", "confirm_receive_30s": "Принять от [{a}]? (через 30 с — автоотклонение) [Y/n]: ",
        "firewall_tip": "\n💡 Совет: если служба на другой стороне запущена, проверьте:\n  1. Не блокирует ли программу брандмауэр Windows (разрешите Python в настройках)\n  2. В одной ли локальной сети устройства (изоляция AP в роутере?)\n  3. Если не помогает — вариант 4 -> 2, введите IP вручную.\n",
        "deep_scanning": "🌐 Таймаут UDP, запускаю глубокое HTTP-сканирование {ip}.1/24 ...",
        "web_title": "lspy — состояние приёма", "web_alias": "Псевдоним", "web_port": "Порт",
        "web_fp": "Отпечаток", "web_recent": "Последние приёмы", "web_none": "Пока ничего не получено",
        "web_hint": "Оставьте службу запущенной. Файлы из LocalSend сохраняются автоматически.",
        "reg_fail": "Не удалось зарегистрироваться у получателя: {e}", "register_ok": "Объявлено получателю",
        "send_fallback": "У цели нет эндпоинта v2.1, переход на prepare-upload",
        "files_skipped": "Пропущено файлов по политике расширений: {n}", "https_send": "Для цели включён TLS",
        "unzip_unsafe": "Распаковка отклонена: небезопасная запись {p}", "http_scan_https": "Проверяются и HTTPS-хосты",
        "bound_port": "Привязано к порту {p}", "no_write_perm": "Нет прав на запись в {p}: {e}",
        "integrity_fail": "Проверка целостности не пройдена для {f}", "chunk_hash": "Несовпадение контрольной суммы блока {i}, повтор",
        "version": "Версия", "web_alone": "Веб-страница: {u}",
        "web_tab_upload": "Отправить на это устройство", "web_tab_download": "Скачать с этого устройства", "web_tab_text": "Текстовое сообщение",
        "web_upload_hint": "Перетащите файлы сюда или нажмите для выбора. Они сохраняются в папке приёма.", "web_download_empty": "Пока ничего не получено", "web_text_hint": "Текст копируется в буфер обмена или сохраняется в файл .txt, если буфер недоступен.",
        "web_send": "Отправить", "web_clip_btn": "Прочитать буфер", "web_pin_prompt": "PIN доступа",
        "web_up_ok": "Загружено", "web_text_ok": "Текст отправлен", "web_pin_bad": "Требуется PIN",
        "web_uploaded": "Загружено: {f}",
        "menu_serve_fg": "Перейти в службу переднего плана (подробный прогресс)",
        "auto_start": "Запуск фонового приёмника...", "auto_start_fail": "Ошибка автозапуска: {e}",
        "port_in_use": "Порт {p} недоступен: {e}",
        "port_in_use_tip": "Скорее всего порт занят приложением LocalSend или другим экземпляром lspy. Закройте его или выберите другой порт: -p 0 / -p 53318.",
        "port_fallback": "Порт {p} занят, переключено на назначенный системой порт {q} (для фиксации используйте -p).",
        "mc_port_busy": "Порт multicast 53317 занят (обычно рядом работает LocalSend для компьютера); прослушивание multicast пропущено, обнаружение по HTTP работает. Добавьте --no-multicast, чтобы скрыть сообщение.",
        "fg_hint": "Приёмник в переднем плане запущен, Ctrl+C останавливает его и возвращает в меню",
        "send_how": "1. Автоматически найти устройства\n2. Ввести IP вручную", "send_choose": "Выбор [1-2]: ",
        "prompt_ip": "IP цели (например 192.168.1.10): ", "input_error": "Ошибка ввода: {e}",
        "menu_banner": "lspy — CLI, совместимый с LocalSend",
        "menu_devices": "Устройства рядом", "no_devices_yet": "Ещё не сканировали, выберите 2 для поиска",
    },
    "pt": {
        "lang_name": "Português", "menu_title": "lspy — CLI compatível com LocalSend",
        "menu_info": "Mostrar informações do dispositivo", "menu_scan": "Procurar dispositivos próximos",
        "menu_serve": "Iniciar serviço de receção (primeiro plano)", "menu_send": "Enviar ficheiros para um dispositivo",
        "menu_cross_send": "Envio entre redes (ntfy.sh)", "menu_cross_recv": "Receção entre redes (ntfy.sh)",
        "menu_history": "Histórico", "menu_config": "Definições", "menu_exit": "Sair",
        "choose_prompt": "Escolha [{choices}]: ", "invalid_option": "Opção inválida",
        "bye": "Até à próxima", "scanning_short": "A procurar na LAN...", "scanning_long": "A procurar na LAN (limite {t}s)...",
        "scan_none": "Nenhum dispositivo encontrado", "scan_found_n": "{n} dispositivo(s) encontrados:", "found_device": "Encontrado: {d}",
        "scan_target": "A procurar o dispositivo de destino...", "device_not_found": "Dispositivo não encontrado: {n}",
        "specify_device_or_ip": "Indique --device ou --ip",
        "multicast_send_fail": "Falha no envio multicast: {e}", "multicast_listen_fail": "Falha na escuta multicast: {e}",
        "http_listening": "HTTP à escuta em {h}:{p}", "https_listening": "HTTPS à escuta em {h}:{p}",
        "save_dir": "Pasta de destino: {d}", "pin_enabled": "PIN ativo: {p}", "mc_listening": "Multicast {g}:{p}",
        "mc_reply": "Resposta MC: {a} @ {ip}", "stopping": "A parar...",
        "ask_receive": "De [{a}] @ {ip}: {n} ficheiro(s). Aceitar? [Y/n]: ",
        "session_created": "Sessão {s} à espera de {n} ficheiro(s)", "receive_done": "Recebido: {f} -> {p}",
        "receive_progress": "{f}: {p}% ({r}/{t})", "write_fail": "Falha de escrita: {e}",
        "send_preparing": "A enviar {n} ficheiro(s) ({s} bytes) -> {d}", "pin_required": "O destino exige PIN (--pin)",
        "conn_fail": "Falha na ligação: {e}", "send_rejected": "Rejeitado (HTTP {c})",
        "no_session": "Resposta inválida: falta sessionId", "send_started": "Sessão {s}... a enviar",
        "send_progress": "Envio: {p}% ({s}/{t})", "send_fail": "Falha ao enviar {f}: {e}",
        "send_done": "Concluído {a}/{b} ficheiro(s)", "https_unsupported": "O destino usa HTTPS (não suportado no envio)",
        "skip_missing": "Ignorado: {p}", "no_files": "Sem ficheiros",
        "cross_pin": "PIN entre redes: {p}  (receção: lspy cross-recv {p})", "packing": "A compactar...",
        "packed": "Compactado: {n} bytes", "cross_progress": "Envio: {s}/{t} ({p}%)",
        "chunk_fail": "Bloco {i} falhou: {e}", "cross_sent": "Enviado", "listening_pin": "À escuta do PIN: {p}",
        "cross_recv_progress": "{n} bytes recebidos", "cross_timeout": "Tempo esgotado", "no_data": "Sem dados",
        "saved": "Guardado: {p} ({n} bytes)", "unzip_ok": "Extraído: {d}", "unzip_fail": "Falha ao extrair: {e}",
        "blocked_ext": "Bloqueado: {f}", "blocked_list": "Bloqueado pela lista negra: {a}",
        "invalid_port": "Porta inválida", "invalid_input": "Entrada inválida", "index_out_of_range": "Fora do intervalo",
        "no_files_provided": "Nenhum ficheiro indicado", "pin_empty": "PIN vazio", "no_file_selected": "Nenhum ficheiro selecionado",
        "no_device_scan": "Sem dispositivos, verifique o serviço do outro lado", "prompt_files": "Caminhos dos ficheiros (separados por vírgulas): ",
        "prompt_save_dir": "Pasta de destino [{d}]: ", "prompt_pin_off": "PIN (vazio=desativado): ",
        "prompt_pin_on": "PIN (vazio={p}): ", "prompt_ask_each": "Perguntar em cada receção? [y/N] (atual: {v}): ",
        "prompt_target_pin": "PIN do destino (vazio=nenhum): ", "prompt_cross_pin": "PIN (vazio=aleatório): ",
        "prompt_cross_recv_pin": "PIN de 6 dígitos: ", "prompt_pick_device": "Escolha [1-{n}]: ",
        "pick_files_title": "Selecionar ficheiros", "yes": "sim", "no": "não",
        "stun_probing": "A consultar STUN...", "stun_result": "Endereço público: {r}", "stun_fail": "Falha STUN: {e}",
        "history_empty": "Sem histórico", "history_entry": "[{t}] {f} ({s} bytes) receive={r}",
        "history_cleared": "Histórico apagado", "history_deleted": "Removido: {f}",
        "history_bad_index": "Não existe essa entrada: {n}", "history_missing": "O ficheiro já não existe: {p}",
        "not_zip": "Não é um ficheiro ZIP: {p}",
        "cfg_title": "Configuração atual", "cfg_alias": "Alias", "cfg_port": "Porta", "cfg_savedir": "Pasta de destino",
        "cfg_pin": "PIN predefinido", "cfg_auto": "Aceitar automaticamente", "cfg_topic": "Tópico NTFY", "cfg_fp": "Impressão digital",
        "cfg_lang": "Idioma", "cfg_none": "(nenhum)", "cfg_default": "(predefinido)",
        "cfg_menu_alias": "Alterar alias", "cfg_menu_port": "Alterar porta", "cfg_menu_savedir": "Alterar pasta de destino",
        "cfg_menu_pin": "Alterar PIN", "cfg_menu_auto": "Alternar aceitação automática", "cfg_menu_topic": "Alterar tópico NTFY",
        "cfg_menu_regen_fp": "Regenerar impressão digital", "cfg_menu_reset": "Repor configuração", "cfg_menu_lang": "Alterar idioma",
        "cfg_menu_back": "Voltar", "cfg_prompt_alias": "Novo alias [{d}]: ", "cfg_prompt_port": "Nova porta [{d}]: ",
        "cfg_prompt_savedir": "Nova pasta [{d}]: ", "cfg_prompt_pin": "Novo PIN [{d}]: ",
        "cfg_prompt_topic": "Novo tópico [{d}]: ", "cfg_confirm_reset": "Repor tudo? [y/N]: ",
        "cfg_reset_done": "Configuração reposta", "cfg_not_exist": "Configuração não encontrada",
        "cfg_set_done": "{k} = {v} definido", "cfg_unset_done": "{u} limpo",
        "cfg_invalid_port": "Porta 1-65535", "cfg_invalid_set": "Formato: --set k=v",
        "cfg_invalid_lang": "Idioma não suportado: {l}", "cfg_lang_choice": "Idioma [{choices}]: ",
        "cfg_file": "Ficheiro de configuração", "help_text": "Ajuda", "confirm_receive_30s": "Receber de [{a}]? (rejeição automática em 30 s) [Y/n]: ",
        "firewall_tip": "\n💡 Dica: se o serviço do outro lado está ativo, verifique:\n  1. Se a firewall do Windows bloqueia o programa (permita o Python nas definições)\n  2. Se ambos os equipamentos estão na mesma LAN (isolamento AP do router?)\n  3. Se continuar a falhar, experimente a opção 4 -> 2 para introduzir o IP manualmente.\n",
        "deep_scanning": "🌐 UDP esgotado, a iniciar varrimento HTTP profundo em {ip}.1/24 ...",
        "web_title": "lspy — estado de receção", "web_alias": "Alias", "web_port": "Porta",
        "web_fp": "Impressão digital", "web_recent": "Recebido recentemente", "web_none": "Ainda não recebeu nada",
        "web_hint": "Mantenha este serviço em execução. Os ficheiros enviados pelo LocalSend são guardados automaticamente.",
        "reg_fail": "Falha ao registar no recetor: {e}", "register_ok": "Anunciado ao recetor",
        "send_fallback": "O destino não tem endpoint v2.1; a usar prepare-upload",
        "files_skipped": "{n} ficheiro(s) ignorado(s) pela política de extensões", "https_send": "TLS ativado para o destino",
        "unzip_unsafe": "Extração recusada: entrada insegura {p}", "http_scan_https": "Também a sondar anfitriões HTTPS",
        "bound_port": "Ligado à porta {p}", "no_write_perm": "Não é possível escrever em {p}: {e}",
        "integrity_fail": "Falha de integridade em {f}", "chunk_hash": "Soma de verificação do bloco {i} não corresponde, a repetir",
        "version": "Versão", "web_alone": "Página web em {u}",
        "web_tab_upload": "Enviar para este dispositivo", "web_tab_download": "Descarregar deste dispositivo", "web_tab_text": "Mensagem de texto",
        "web_upload_hint": "Arraste ficheiros para aqui ou clique para escolher. São guardados na pasta de receção.", "web_download_empty": "Ainda nada recebido", "web_text_hint": "O texto é copiado para a área de transferência ou guardado como .txt se esta não estiver disponível.",
        "web_send": "Enviar", "web_clip_btn": "Ler área de transferência", "web_pin_prompt": "PIN de acesso",
        "web_up_ok": "Enviado", "web_text_ok": "Texto enviado", "web_pin_bad": "PIN necessário",
        "web_uploaded": "Enviado: {f}",
        "menu_serve_fg": "Passar ao serviço em primeiro plano (progresso detalhado)",
        "auto_start": "A iniciar o recetor em segundo plano...", "auto_start_fail": "Falha no arranque automático: {e}",
        "port_in_use": "Porta {p} indisponível: {e}",
        "port_in_use_tip": "Provavelmente a app LocalSend ou uma segunda instância do lspy ocupa esta porta. Feche-a ou escolha outra com -p 0 / -p 53318.",
        "port_fallback": "A porta {p} está ocupada; mudei para a porta {q} atribuída pelo sistema (use -p para fixar).",
        "mc_port_busy": "A porta multicast 53317 está ocupada (normalmente o LocalSend de secretária ao lado); escuta multicast ignorada, a descoberta HTTP continua a funcionar. Adicione --no-multicast para silenciar.",
        "fg_hint": "Recetor em primeiro plano ativo; Ctrl+C pára-o e volta ao menu",
        "send_how": "1. Procurar dispositivos automaticamente\n2. Introduzir o IP manualmente", "send_choose": "Escolha [1-2]: ",
        "prompt_ip": "IP de destino (ex. 192.168.1.10): ", "input_error": "Erro de entrada: {e}",
        "menu_banner": "lspy — CLI compatível com LocalSend",
        "menu_devices": "Dispositivos próximos", "no_devices_yet": "Ainda não procurou, escolha 2 para procurar",
    },
}
# 所有 SUPPORTED_LANGS 都必须是内嵌的真实词表：不再用英文副本冒充其它语言，
# 缺失会在导入时直接报错，避免"菜单能选但界面还是英文"的静默缺陷。
_MISSING_LANGS = [lg for lg in SUPPORTED_LANGS if lg not in I18N]
if _MISSING_LANGS:
    raise RuntimeError(f"内置翻译缺失：{', '.join(_MISSING_LANGS)}")

_current_lang = "en"
# 调试键模式（移植自 watchsend 的 Debug Keys Mode）：打开后界面直接显示 i18n 原始键名，
# 一眼就能看出哪些文案没翻译，比对着词表逐条数更省事。
_debug_keys = False

def _normalize_lang(code):
    if not code: return None
    code = code.strip().lower().replace("-", "_")
    if not code or code in ("c", "posix"): return None
    if code.startswith("zh"):
        if any(x in code for x in ("tw", "hk", "mo", "hant")): return "zh_TW"
        return "zh"
    for prefix, lang in (("ja", "ja"), ("ko", "ko"), ("de", "de"), ("fr", "fr"), ("es", "es"), ("ru", "ru"), ("pt", "pt"), ("en", "en")):
        if code.startswith(prefix): return lang
    # locale.getlocale() 在 Windows 上返回的是本地化长名（如 "Chinese (Simplified)_China"），
    # 只有语言代码前缀匹配不到，这里按全名再认一次。
    if "chinese" in code:
        return "zh_TW" if any(x in code for x in ("traditional", "taiwan", "hong kong", "macau")) else "zh"
    for word, lang in (("japanese", "ja"), ("korean", "ko"), ("german", "de"), ("french", "fr"),
                       ("spanish", "es"), ("russian", "ru"), ("portuguese", "pt"), ("english", "en")):
        if word in code: return lang
    return None

_WEB_LANG_TAG = {"zh": "zh-CN", "zh_TW": "zh-Hant", "en": "en", "ja": "ja", "ko": "ko",
                 "de": "de", "fr": "fr", "es": "es", "ru": "ru", "pt": "pt"}

def pick_accept_language(header, fallback=None):
    """按 Accept-Language 的 q 权重挑一门内置语言；浏览器带了多门时优先高权重的那门。

    移植自 watchsend 的「Web 10-Language Adaptive」：网页不该被服务端 CLI 的语言绑死。
    """
    if not header: return fallback
    best, best_q = None, -1.0
    for part in str(header).split(","):
        bits = part.split(";")
        tag = bits[0].strip()
        q = 1.0
        for b in bits[1:]:
            b = b.strip().lower()
            if b.startswith("q="):
                try: q = float(b[2:])
                except ValueError: q = 0.0
        if q <= 0: continue
        n = _normalize_lang(tag)
        if n and (q > best_q or (q == best_q and best is None)):
            best, best_q = n, q
    return best or fallback

def _lang_from_env():
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var)
        if v:
            for part in v.split(":"):
                n = _normalize_lang(part)
                if n: return n
    return None

def _locale_default_name():
    """locale.getdefaultlocale() 在 3.15 会被移除，调用时还会往 stderr 打 DeprecationWarning。"""
    fn = getattr(locale, "getdefaultlocale", None)
    if fn is None: return None
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            return fn()[0]
        except Exception:
            return None

def _lang_from_locale():
    for getter in (lambda: locale.getlocale()[0], _locale_default_name):
        try:
            loc = getter()
        except Exception:
            continue
        n = _normalize_lang(loc) if loc else None
        if n: return n
    return None

def _lang_from_windows():
    if sys.platform != "win32": return None
    try:
        import winreg
        # PyHKEY 只有 Close()，写成 k.close() 会抛 AttributeError 并被吞掉，曾导致
        # Windows 上 auto 永远回退到英文。用 with 托管句柄，别手动关。
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\International") as k:
            loc = winreg.QueryValueEx(k, "LocaleName")[0]
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

def _t_for(lang, key, **kwargs):
    """按指定语言取词条，不依赖全局 _current_lang；Web 页要按浏览器语言单独渲染。"""
    s = I18N.get(lang, {}).get(key)
    if s is None: s = I18N["en"].get(key, key)
    if kwargs:
        try: return s.format(**kwargs)
        except Exception: return s
    return s

def t(key, **kwargs):
    if _debug_keys: return f"⟦{key}⟧"
    return _t_for(_current_lang, key, **kwargs)

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
def history_file_label(name):
    """ZIP 在历史里标 📦（沿用 watchsend 的习惯），一眼看出这条能直接解压。"""
    s = str(name or "")
    return f"{s} 📦" if s.lower().endswith(".zip") else s

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

def history_entries_all():
    """按列表顺序（最新在前）返回全部记录，供 --delete / --unzip 按序号定位。"""
    return read_history(10 ** 9)

def rewrite_history(entries):
    """把「最新在前」的列表按旧到新写回；先写临时文件再替换，避免写一半把历史丢了。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = HISTORY_FILE.with_name(HISTORY_FILE.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for e in reversed(entries):
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    os.replace(tmp, HISTORY_FILE)

def delete_history_entry(index):
    """删除列表中第 index 条（1 基，最新在前），返回被删的记录；越界返回 None。"""
    entries = history_entries_all()
    if not 1 <= index <= len(entries): return None
    removed = entries.pop(index - 1)
    rewrite_history(entries)
    return removed

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

# ================== Web 分享（移植自 watchsend WebShareHandler） ==================
WEB_MAX_UPLOAD = 2 * 1024 * 1024 * 1024   # 单次浏览器上传上限 2 GiB
WEB_LIST_LIMIT = 500                      # 文件列表最多返回条数
WEB_LIST_DEPTH = 4                        # 相对 save_dir 的最大展示深度


def web_safe_path(base, rel):
    """把浏览器给的相对路径解析到 base 之内；越界（../、绝对路径、跨盘）返回 None。"""
    if not rel: return None
    raw = str(rel).replace("\\", "/").replace("\x00", "")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"): return None
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts): return None
    base_r = Path(base).expanduser().resolve()
    target = (base_r / Path(*parts)).resolve() if parts else base_r
    try:
        if os.path.commonpath([str(base_r), str(target)]) != str(base_r): return None
    except ValueError: return None
    return target


def web_list_files(base, limit=WEB_LIST_LIMIT, depth=WEB_LIST_DEPTH):
    """列出接收目录内的文件（相对路径），供网页「下载」页签使用。"""
    out, base = [], Path(base).expanduser()
    try:
        for root, dirs, files in os.walk(base):
            rel_root = Path(root).relative_to(base)
            if len(rel_root.parts) >= depth: dirs[:] = []
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in files:
                if fn.startswith("."): continue
                p = Path(root) / fn
                try: st = p.stat()
                except OSError: continue
                out.append({"name": str((rel_root / fn).as_posix()), "size": st.st_size,
                            "mtime": int(st.st_mtime)})
                if len(out) >= limit: return out
    except OSError: pass
    return out


def _clipboard_get():
    """读取本机剪贴板；无 GUI/tkinter 环境返回空串（不抛异常）。"""
    try:
        import tkinter
        r = tkinter.Tk(); r.withdraw()
        try: return str(r.clipboard_get() or "")
        finally: r.destroy()
    except Exception: return ""


def _clipboard_set(text):
    """写入本机剪贴板；失败返回 False，由调用方改用落盘兜底。"""
    try:
        import tkinter
        r = tkinter.Tk(); r.withdraw()
        try:
            r.clipboard_clear(); r.clipboard_append(text); r.update()
            return True
        finally: r.destroy()
    except Exception: return False


_WEB_PAGE_TEMPLATE = """<!DOCTYPE html><html lang="@@LANG@@"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>@@TITLE@@</title><style>
:root{--bg:#f6f7f9;--card:#ffffff;--line:#e5e7eb;--txt:#1f2430;--muted:#6b7280;--acc:#2563eb}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;max-width:860px;margin:0 auto;padding:20px;background:var(--bg);color:var(--txt)}
h1{font-size:20px;margin:0 0 4px} h2{font-size:15px;margin:0 0 12px;font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:14px}
.k{display:inline-block;min-width:92px;color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid #f0f1f4;font-size:13px;word-break:break-all}
code{color:#4b5563;font-size:12px}
.muted{color:var(--muted);font-size:12px}
.tabs{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.tab{padding:8px 16px;border-radius:999px;border:1px solid var(--line);background:#fff;cursor:pointer;font-size:13px;color:var(--muted)}
.tab.on{background:var(--acc);border-color:var(--acc);color:#fff}
.panel{display:none} .panel.on{display:block}
.zone{border:2px dashed #d7dbe2;border-radius:10px;padding:26px;text-align:center;cursor:pointer;color:var(--muted);background:#fbfcfe}
.zone.hot{border-color:var(--acc);background:#eff5ff}
.bar{height:6px;background:#eef0f4;border-radius:3px;overflow:hidden;margin-top:6px}
.fill{height:100%;width:0;background:var(--acc);transition:width .15s}
.row{display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid #f0f1f4;font-size:13px;align-items:center}
a.dl{color:var(--acc);text-decoration:none;font-size:13px;white-space:nowrap}
.btn{padding:9px 18px;border:0;border-radius:9px;background:var(--acc);color:#fff;font-size:14px;cursor:pointer}
.btn.ghost{background:#fff;border:1px solid var(--line);color:var(--txt)}
textarea{width:100%;min-height:130px;border:1px solid var(--line);border-radius:10px;padding:12px;font-size:14px;font-family:inherit;resize:vertical}
input[type=password]{width:100%;padding:9px;border:1px solid var(--line);border-radius:9px;margin-top:6px}
.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);background:#1f2430;color:#fff;padding:10px 18px;border-radius:999px;font-size:13px;opacity:0;transition:opacity .25s;pointer-events:none}
.toast.on{opacity:1}
</style></head><body>
<h1>@@TITLE@@</h1>
<p class="muted">@@HINT@@</p>

<div class="card" id="pin-card" style="display:none">
<h2>@@PIN_PROMPT@@</h2>
<input type="password" id="pin-input" placeholder="PIN" onchange="savePin(this.value)">
</div>

<div class="card">
<div><span class="k">@@ALIAS@@</span>@@ALIAS_V@@</div>
<div><span class="k">@@PORT@@</span>@@PORT_V@@</div>
<div><span class="k">@@FP@@</span><code>@@FP_V@@</code></div>
<div><span class="k">ver</span>@@VER@@</div>
</div>

<div class="tabs">
<button class="tab on" onclick="switchTab('upload',this)">@@TAB_UP@@</button>
<button class="tab" onclick="switchTab('download',this)">@@TAB_DOWN@@</button>
<button class="tab" onclick="switchTab('text',this)">@@TAB_TEXT@@</button>
</div>

<div class="card panel on" id="p-upload">
<h2>@@TAB_UP@@</h2>
<div class="zone" id="zone" onclick="document.getElementById('file-input').click()">@@UP_HINT@@</div>
<input type="file" id="file-input" multiple style="display:none" onchange="handleFiles(this.files)">
<div id="up-list" style="margin-top:12px"></div>
</div>

<div class="card panel" id="p-download">
<h2>@@TAB_DOWN@@</h2>
<div id="dl-list"><p class="muted">…</p></div>
</div>

<div class="card panel" id="p-text">
<h2>@@TAB_TEXT@@</h2>
<textarea id="text-input" placeholder="@@TEXT_HINT@@"></textarea>
<div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap">
<button class="btn" onclick="sendText()">@@SEND@@</button>
<button class="btn ghost" onclick="readClip()">@@CLIP@@</button>
</div>
</div>

<div class="card"><h2>@@RECENT@@</h2>
<table><thead><tr><th>Time</th><th>File</th><th>Path</th></tr></thead><tbody>@@ROWS@@</tbody></table>
</div>

<div class="toast" id="toast"></div>
<script>
var PIN_REQ = @@PIN_REQ@@;
var MSG = {up_ok:"@@UP_OK@@", text_ok:"@@TEXT_OK@@", pin_bad:"@@PIN_BAD@@"};
function pin(){ return localStorage.getItem('lspy_pin') || ''; }
function savePin(v){ localStorage.setItem('lspy_pin', v); if (v) loadFiles(); }
function withPin(url){ var p = pin(); if (!p) return url; return url + (url.indexOf('?') >= 0 ? '&' : '?') + 'pin=' + encodeURIComponent(p); }
function toast(msg){ var el = document.getElementById('toast'); el.textContent = msg; el.className = 'toast on'; setTimeout(function(){ el.className = 'toast'; }, 2200); }
function needPin(r){ if (r.status === 401){ document.getElementById('pin-card').style.display = 'block'; throw new Error(MSG.pin_bad); } if (!r.ok) throw new Error('HTTP ' + r.status); return r; }
function switchTab(name, btn){
  ['upload','download','text'].forEach(function(n){ document.getElementById('p-' + n).className = 'card panel' + (n === name ? ' on' : ''); });
  var tabs = document.querySelectorAll('.tab'); for (var i = 0; i < tabs.length; i++) tabs[i].className = 'tab';
  btn.className = 'tab on';
  if (name === 'download') loadFiles();
}
function fmtSize(b){ if (b < 1024) return b + ' B'; if (b < 1048576) return (b / 1024).toFixed(1) + ' KB'; if (b < 1073741824) return (b / 1048576).toFixed(1) + ' MB'; return (b / 1073741824).toFixed(2) + ' GB'; }
function loadFiles(){
  var box = document.getElementById('dl-list');
  fetch(withPin('/web/files')).then(needPin).then(function(r){ return r.json(); }).then(function(d){
    if (!d.files || !d.files.length){ box.innerHTML = '<p class="muted">@@DL_EMPTY@@</p>'; return; }
    var html = '';
    d.files.forEach(function(f){
      html += '<div class="row"><span>' + f.name.replace(/</g,'&lt;') + ' <span class="muted">' + fmtSize(f.size) + '</span></span>'
            + '<a class="dl" href="' + withPin('/web/download?name=' + encodeURIComponent(f.name)) + '">↓</a></div>';
    });
    box.innerHTML = html;
  }).catch(function(e){ box.innerHTML = '<p class="muted">' + e.message + '</p>'; });
}
function upOne(file, idx){
  return new Promise(function(resolve){
    var xhr = new XMLHttpRequest();
    var row = document.getElementById('u-' + idx);
    xhr.open('POST', withPin('/web/upload?name=' + encodeURIComponent(file.name)));
    xhr.upload.onprogress = function(ev){ if (ev.lengthComputable){ var pct = Math.round(ev.loaded * 100 / ev.total); row.querySelector('.fill').style.width = pct + '%'; row.querySelector('.pct').textContent = pct + '%'; } };
    xhr.onload = function(){ if (xhr.status === 401){ document.getElementById('pin-card').style.display = 'block'; row.querySelector('.pct').textContent = MSG.pin_bad; } else if (xhr.status >= 200 && xhr.status < 300){ row.querySelector('.pct').textContent = '100%'; row.querySelector('.fill').style.width = '100%'; } else { row.querySelector('.pct').textContent = 'HTTP ' + xhr.status; } resolve(); };
    xhr.onerror = function(){ row.querySelector('.pct').textContent = 'ERR'; resolve(); };
    xhr.send(file);
  });
}
async function handleFiles(files){
  if (!files || !files.length) return;
  var list = document.getElementById('up-list');
  list.innerHTML = '';
  for (var i = 0; i < files.length; i++){
    var div = document.createElement('div');
    div.className = 'row';
    div.id = 'u-' + i;
    div.innerHTML = '<span>' + files[i].name.replace(/</g,'&lt;') + ' <span class="muted">' + fmtSize(files[i].size) + '</span></span><span class="pct">0%</span><div class="bar" style="flex:1 1 100%;max-width:none"><div class="fill"></div></div>';
    div.style.flexWrap = 'wrap';
    list.appendChild(div);
  }
  for (var j = 0; j < files.length; j++){ await upOne(files[j], j); }
  toast(MSG.up_ok);
  loadFiles();
}
function sendText(){
  var text = document.getElementById('text-input').value;
  if (!text){ return; }
  fetch(withPin('/web/text'), {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text:text})})
    .then(needPin).then(function(){ toast(MSG.text_ok); })
    .catch(function(e){ toast(e.message); });
}
function readClip(){
  fetch(withPin('/web/clipboard')).then(needPin).then(function(r){ return r.text(); }).then(function(txt){
    if (txt){ document.getElementById('text-input').value = txt; } else { toast(MSG.text_ok); }
  }).catch(function(e){ toast(e.message); });
}
var z = document.getElementById('zone');
['dragenter','dragover'].forEach(function(ev){ z.addEventListener(ev, function(e){ e.preventDefault(); z.className = 'zone hot'; }); });
['dragleave','drop'].forEach(function(ev){ z.addEventListener(ev, function(e){ e.preventDefault(); z.className = 'zone'; }); });
z.addEventListener('drop', function(e){ handleFiles(e.dataTransfer.files); });
if (PIN_REQ){ document.getElementById('pin-card').style.display = 'block'; }
if (PIN_REQ && !pin()){ } else { loadFiles(); }
</script></body></html>"""


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

    def _web_page_html(self, lang=None):
        # 按调用方选定的语言渲染，让浏览器语言与 CLI 语言互不干扰
        lang = lang or _current_lang
        def tr(key, **kw): return _t_for(lang, key, **kw)
        import html as _html
        info = build_self_info(port=self.bound_port,
                               protocol="https" if self._use_https else "http")
        rows = []
        for e in read_history(30):
            rows.append(
                "<tr><td>{}</td><td>{}</td><td><code>{}</code></td></tr>".format(
                    _html.escape(str(e.get("time", ""))),
                    _html.escape(history_file_label(e.get("file", ""))),
                    _html.escape(str(e.get("path", "")))))
        body = "".join(rows) or f"<tr><td colspan=3>{_html.escape(tr('web_none'))}</td></tr>"
        page = _WEB_PAGE_TEMPLATE
        for token, value in (
            ("@@TITLE@@", _html.escape(tr("web_title"))),
            ("@@TAB_UP@@", _html.escape(tr("web_tab_upload"))),
            ("@@TAB_DOWN@@", _html.escape(tr("web_tab_download"))),
            ("@@TAB_TEXT@@", _html.escape(tr("web_tab_text"))),
            ("@@UP_HINT@@", _html.escape(tr("web_upload_hint"))),
            ("@@DL_EMPTY@@", _html.escape(tr("web_download_empty"))),
            ("@@TEXT_HINT@@", _html.escape(tr("web_text_hint"))),
            ("@@SEND@@", _html.escape(tr("web_send"))),
            ("@@CLIP@@", _html.escape(tr("web_clip_btn"))),
            ("@@PIN_PROMPT@@", _html.escape(tr("web_pin_prompt"))),
            ("@@UP_OK@@", _html.escape(tr("web_up_ok"))),
            ("@@TEXT_OK@@", _html.escape(tr("web_text_ok"))),
            ("@@PIN_BAD@@", _html.escape(tr("web_pin_bad"))),
            ("@@ALIAS@@", _html.escape(tr("web_alias"))),
            ("@@ALIAS_V@@", _html.escape(str(info["alias"]))),
            ("@@PORT@@", _html.escape(tr("web_port"))),
            ("@@PORT_V@@", str(info["port"])),
            ("@@FP@@", _html.escape(tr("web_fp"))),
            ("@@FP_V@@", _html.escape(str(info["fingerprint"])[:32])),
            ("@@LANG@@", _WEB_LANG_TAG.get(lang, "en")),
            ("@@VER@@", _html.escape(VERSION)),
            ("@@HINT@@", _html.escape(tr("web_hint"))),
            ("@@RECENT@@", _html.escape(tr("web_recent"))),
            ("@@ROWS@@", body),
            ("@@PIN_REQ@@", "true" if self.pin else "false"),
        ):
            page = page.replace(token, value)
        return page

    def _web_files_payload(self):
        return {"files": web_list_files(self.save_dir), "dir": str(self.save_dir.resolve()),
                "pin": bool(self.pin)}

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
                if not server.pin: return True
                given = qs.get("pin", [None])[0] or self.headers.get("X-LocalSend-Pin")
                return given == server.pin

            def _unauthorized(self):
                self.send_response(401); self.send_header("X-LocalSend-Pin", "true")
                self.send_header("Content-Length", "0"); self.send_header("Connection", "close")
                self.end_headers(); self.close_connection = True

            def _text(self, body, ctype="text/plain; charset=utf-8"):
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers(); self.wfile.write(body); self.close_connection = True

            def _send_file(self, target):
                """流式下载，支持 Range 之外的简单 GET；不整块读入内存。"""
                size = target.stat().st_size
                name = urllib.parse.quote(target.name)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(size))
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{name}")
                self.send_header("Connection", "close")
                self.end_headers()
                with open(target, "rb") as f:
                    shutil.copyfileobj(f, self.wfile)
                self.close_connection = True

            def _html_page(self):
                # 浏览器语言优先：先看 Accept-Language，认不出来才回退到 CLI 当前语言
                lang = pick_accept_language(self.headers.get("Accept-Language"), _current_lang)
                body = server._web_page_html(lang).encode("utf-8")
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
                if path.startswith("/web/"):
                    if not server.web_enable: self._json(404, {"error": "web disabled"}); return
                    if path == "/web/info":
                        info = build_self_info(port=server.bound_port,
                                               protocol="https" if server._use_https else "http")
                        info["web"] = True; info["pinRequired"] = bool(server.pin)
                        info["files"] = len(web_list_files(server.save_dir))
                        self._json(200, info); return
                    if not self._pin_ok(peer_qs): self._unauthorized(); return
                    if path == "/web/files":
                        payload = server._web_files_payload()
                        payload.pop("pin", None)
                        self._json(200, payload); return
                    if path == "/web/clipboard":
                        self._text(_clipboard_get().encode("utf-8")); return
                    if path == "/web/download":
                        rel = peer_qs.get("name", [""])[0]
                        target = web_safe_path(server.save_dir, rel)
                        if not target or not target.is_file():
                            self._json(404, {"error": "not found"}); return
                        try: self._send_file(target)
                        except OSError: self._json(404, {"error": "gone"})
                        return
                    self._json(404, {"error": "not found"}); return
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

                if path.startswith("/web/"):
                    if not server.web_enable: self._json(404, {"error": "web disabled"}); return
                    if not self._pin_ok(qs): self._unauthorized(); return
                    if path == "/web/upload":
                        name = safe_filename(qs.get("name", [""])[0] or f"web_{int(time.time())}")
                        if _is_blocked_ext(name):
                            print("\n⛔ " + t("blocked_ext", f=name))
                            self._json(403, {"error": "blocked"}); return
                        try: length = int(self.headers.get("Content-Length", "0") or 0)
                        except (TypeError, ValueError): length = 0
                        if length <= 0: self._json(411, {"error": "length required"}); return
                        if length > WEB_MAX_UPLOAD:
                            self._json(413, {"error": "too large"}); return
                        tdir, safe_name = choose_target_dir(name, server.save_dir)
                        try:
                            tdir.mkdir(parents=True, exist_ok=True)
                            target = unique_path(tdir, safe_name)
                            received = 0
                            with open(target, "wb") as f:
                                remaining = length
                                while remaining > 0:
                                    chunk = self.rfile.read(min(65536, remaining))
                                    if not chunk: break
                                    f.write(chunk); received += len(chunk); remaining -= len(chunk)
                        except OSError as e:
                            self._json(507, {"error": str(e)}); return
                        if received != length:
                            try: target.unlink()
                            except OSError: pass
                            self._json(400, {"error": "incomplete"}); return
                        print("📤 " + t("web_uploaded", f=target.name))
                        append_history(target.name, target, received, True)
                        threading.Thread(target=server._post_process, args=(target,),
                                         daemon=True).start()
                        self._json(200, {"status": "ok", "name": target.name,
                                         "path": str(target)}); return
                    if path == "/web/text":
                        try: o = json.loads(self._read_body().decode("utf-8") or "{}")
                        except Exception: o = {}
                        text = str((o or {}).get("text", "") or "")
                        if not text.strip():
                            self._json(400, {"error": "empty"}); return
                        clip = _clipboard_set(text)
                        saved = None
                        if not clip:
                            stamp = time.strftime("%Y%m%d-%H%M%S")
                            target = unique_path(server.save_dir, f"web-text-{stamp}.txt")
                            try:
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_text(text, "utf-8"); saved = str(target)
                                append_history(target.name, target, len(text.encode("utf-8")), True)
                            except OSError as e:
                                self._json(507, {"error": str(e)}); return
                        self._json(200, {"status": "ok", "clipboard": clip, "saved": saved}); return
                    self._json(404, {"error": "not found"}); return

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
    if getattr(args, "clear", False):
        if not HISTORY_FILE.exists(): print(t("history_empty")); return
        try:
            HISTORY_FILE.unlink(); print("✅ " + t("history_cleared"))
        except Exception as e: print("⚠️ " + t("input_error", e=e))
        return
    idx = getattr(args, "delete", None)
    if idx is not None:
        removed = delete_history_entry(idx)
        if removed is None: print("⚠️ " + t("history_bad_index", n=idx)); return
        print("✅ " + t("history_deleted", f=removed.get("file")))
        return
    idx = getattr(args, "unzip", None)
    if idx is not None:
        entries = history_entries_all()
        if not 1 <= idx <= len(entries): print("⚠️ " + t("history_bad_index", n=idx)); return
        src = Path(str(entries[idx - 1].get("path") or ""))
        if not src.is_file(): print("⚠️ " + t("history_missing", p=src)); return
        if src.suffix.lower() != ".zip": print("⚠️ " + t("not_zip", p=src)); return
        out = src.parent / src.stem
        if safe_unzip(src, out): print("✅ " + t("unzip_ok", d=out.resolve()))
        return
    entries = read_history(args.n)
    if not entries: print(t("history_empty")); return
    for e in entries:
        print(t("history_entry", t=e.get("time"), f=history_file_label(e.get("file")),
                s=e.get("size"), r=e.get("receive")))

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
                       "auto_accept_whitelist", "debug_keys"):
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
    parser.add_argument("--debug-keys", action="store_true",
                        help="print raw i18n keys instead of translations (spot missing strings)")
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

    p = sub.add_parser("history", help="show / manage transfer history")
    p.add_argument("-n", type=int, default=20, help="how many entries to list")
    p.add_argument("--delete", type=int, metavar="N", help="delete entry N (1 = newest), like watchsend's long-press delete")
    p.add_argument("--unzip", type=int, metavar="N", help="extract entry N if it is a ZIP (Zip Slip guarded)")
    p.add_argument("--clear", action="store_true", help="wipe the whole history file")
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
    global _debug_keys
    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_stdio()
    init_lang(); setup_logging()
    # 命令行开关只作用于本次运行；要长期打开就用 config --set debug_keys=true
    _debug_keys = bool(getattr(args, "debug_keys", False)) or bool(get_config("debug_keys"))
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
