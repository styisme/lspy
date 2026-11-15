#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lspy 单元 + 端到端测试（stdlib unittest，不依赖第三方库）。

运行： python -m unittest discover -s tests -v
"""

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

TEST_HOME = tempfile.mkdtemp(prefix="lspy_test_home_")
os.environ["HOME"] = TEST_HOME
os.environ["USERPROFILE"] = TEST_HOME
if sys.platform == "win32":
    os.environ["HOMEDRIVE"], os.environ["HOMEPATH"] = os.path.splitdrive(TEST_HOME)[0], os.path.splitdrive(TEST_HOME)[1]
os.environ.setdefault("LANG", "en")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lspy  # noqa: E402

# 测试里把真实剪贴板写入换成桩：跑一遍测试不该动用户的剪贴板内容。
# 需要验证真实通道的用例直接用 _win32_clipboard_set/_clipboard_get（见 TestReceiveClipboard）。
REAL_CLIPBOARD_SET = lspy._clipboard_set
lspy._clipboard_set = lambda text: True


def tearDownModule():
    shutil.rmtree(TEST_HOME, ignore_errors=True)


class ServerPair:
    """在后台线程启动一个接收端，供协议测试使用。"""

    def __init__(self, **kwargs):
        self.tmp = tempfile.mkdtemp(prefix="lspy_test_recv_")
        opts = dict(host="127.0.0.1", port=0, save_dir=self.tmp, auto_accept=True,
                    multicast=False, web_enable=True)
        opts.update(kwargs)
        self.server = lspy.LspyServer(**opts)

    def __enter__(self):
        self.server.start(blocking=False)
        return self

    def __exit__(self, *exc):
        self.server.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    @property
    def base(self):
        return f"http://127.0.0.1:{self.server.bound_port}"

    def device(self):
        return lspy.Device(alias="loopback", ip="127.0.0.1", port=self.server.bound_port)


class TestFileSafety(unittest.TestCase):
    def test_safe_filename_strips_traversal(self):
        self.assertEqual(lspy.safe_filename("../../etc/passwd"), "passwd")
        self.assertEqual(lspy.safe_filename("..\\..\\windows\\system32\\cmd.exe"), "cmd.exe")
        self.assertEqual(lspy.safe_filename("a:b?c*.txt"), "a_b_c_.txt")
        self.assertTrue(lspy.safe_filename("").startswith("unnamed"))

    def test_safe_filename_strips_nul_and_absolute(self):
        self.assertEqual(lspy.safe_filename("/tmp/x\x00.png"), "x.png")

    def test_unique_path_never_reuses(self):
        d = Path(tempfile.mkdtemp(prefix="lspy_unique_"))
        try:
            first = lspy.unique_path(d, "a.txt")
            first.write_text("x")
            second = lspy.unique_path(d, "a.txt")
            self.assertNotEqual(first, second)
            self.assertFalse(second.exists())
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_safe_unzip_blocks_traversal(self):
        d = Path(tempfile.mkdtemp(prefix="lspy_zip_"))
        try:
            zp = d / "evil.zip"
            with zipfile.ZipFile(zp, "w") as zf:
                zf.writestr("../escaped.txt", "boom")
            self.assertFalse(lspy.safe_unzip(zp, d / "out"))
            zp2 = d / "ok.zip"
            with zipfile.ZipFile(zp2, "w") as zf:
                zf.writestr("sub/ok.txt", "fine")
            self.assertTrue(lspy.safe_unzip(zp2, d / "out2"))
            self.assertTrue((d / "out2" / "sub" / "ok.txt").exists())
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestConfigAndI18n(unittest.TestCase):
    def setUp(self):
        lspy.reset_config()

    def test_defaults_and_set(self):
        self.assertEqual(lspy.get_config("port"), lspy.DEFAULT_PORT)
        lspy.set_config("alias", "unit-test")
        self.assertEqual(lspy.get_alias(), "unit-test")
        lspy.set_config("alias", None)
        self.assertEqual(lspy.get_alias(), lspy.__dict__["socket"].gethostname())

    def test_fingerprint_is_stable(self):
        fp1 = lspy.get_fingerprint()
        fp2 = lspy.get_fingerprint()
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 40)

    def test_i18n_fallback(self):
        lspy.init_lang()
        self.assertIn(lspy.t("menu_scan"), (lspy.I18N["en"]["menu_scan"], lspy.I18N["zh"]["menu_scan"]))
        self.assertIsInstance(lspy.t("definitely_missing_key"), str)

    def test_lang_normalize(self):
        self.assertEqual(lspy._normalize_lang("zh-Hant-HK"), "zh_TW")
        self.assertEqual(lspy._normalize_lang("zh-CN"), "zh")
        self.assertEqual(lspy._normalize_lang("ja_JP.UTF-8"), "ja")
        self.assertIsNone(lspy._normalize_lang(""))

    def test_lang_normalize_locale_long_names(self):
        """locale.getlocale() 在 Windows 上给的是本地化长名，必须也认得出（回归：auto 曾永远回退 en）。"""
        self.assertEqual(lspy._normalize_lang("Chinese (Simplified)_China"), "zh")
        self.assertEqual(lspy._normalize_lang("Chinese (Traditional)_Taiwan"), "zh_TW")
        self.assertEqual(lspy._normalize_lang("German_Austria"), "de")
        self.assertEqual(lspy._normalize_lang("English_United States"), "en")
        self.assertEqual(lspy._normalize_lang("Portuguese_Brazil"), "pt")

    def test_lang_from_windows_uses_context_manager(self):
        """winreg 的 PyHKEY 只有 Close()，旧实现 k.close() 抛错被吞 → auto 失效。"""
        import types
        from unittest import mock

        class FakeKey:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def close(self): raise AttributeError("no close()")   # 旧实现会踩这个

        fake = types.ModuleType("winreg")
        fake.HKEY_CURRENT_USER = object()
        fake.OpenKey = lambda *a, **k: FakeKey()
        fake.QueryValueEx = lambda k, name: ("zh-TW", 1)
        with mock.patch.dict(sys.modules, {"winreg": fake}), \
             mock.patch.object(lspy.sys, "platform", "win32"):
            self.assertEqual(lspy._lang_from_windows(), "zh_TW")

    def test_auto_lang_never_returns_none(self):
        self.addCleanup(lspy.set_config, "lang", None)
        lspy.set_config("lang", "auto")
        self.assertIn(lspy.detect_lang(), lspy.SUPPORTED_LANGS)

    def test_locale_probe_does_not_leak_deprecation_warning(self):
        """getdefaultlocale() 的 DeprecationWarning 曾直接打到 CLI 输出里。"""
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            lspy._lang_from_locale()
        msgs = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertEqual([m for m in msgs if "getdefaultlocale" in m], [])

    def test_every_supported_lang_has_own_catalog(self):
        """每个受支持语言都必须有独立完整词表，不能是英文副本（回归：语言菜单曾全部显示 English）。"""
        en = lspy.I18N["en"]
        for lg in lspy.SUPPORTED_LANGS:
            with self.subTest(lang=lg):
                self.assertIn(lg, lspy.I18N)
                cat = lspy.I18N[lg]
                self.assertEqual(set(cat), set(en), f"{lg} 键集合与 en 不一致")
                for k, v in cat.items():
                    self.assertIsInstance(v, str, f"{lg}.{k} 不是字符串")
                    self.assertTrue(v.strip(), f"{lg}.{k} 为空")
                if lg != "en":
                    self.assertNotEqual(cat, en, f"{lg} 仍然是英文副本")

    def test_lang_names_are_native_and_unique(self):
        names = {}
        for lg in lspy.SUPPORTED_LANGS:
            name = lspy.I18N[lg]["lang_name"].strip()
            self.assertTrue(name, f"{lg} 缺少 lang_name")
            names[lg] = name
        self.assertEqual(len(set(names.values())), len(names), f"语言名重复：{names}")
        self.assertNotIn("English", {names[lg] for lg in lspy.SUPPORTED_LANGS if lg != "en"})
        self.assertEqual(names["zh_TW"], "繁體中文")

    def test_placeholders_match_english(self):
        """译文必须保留每个键原有占位符，否则运行时 format 会报错。"""
        import re as _re
        ph = lambda s: set(_re.findall(r"\{(\w+)\}", s))  # noqa: E731
        for lg in lspy.SUPPORTED_LANGS:
            for k, src in lspy.I18N["en"].items():
                with self.subTest(lang=lg, key=k):
                    self.assertEqual(ph(lspy.I18N[lg][k]), ph(src), f"{lg}.{k} 占位符不一致")

    def test_switching_lang_changes_ui_text(self):
        # addCleanup 是后进先出：先登记 init_lang，才能保证清掉配置后再刷新语言
        self.addCleanup(lspy.init_lang)
        self.addCleanup(lspy.set_config, "lang", None)
        lspy.set_config("lang", "ja")
        lspy.init_lang()
        self.assertEqual(lspy.t("menu_scan"), lspy.I18N["ja"]["menu_scan"])
        self.assertNotEqual(lspy.t("menu_scan"), lspy.I18N["en"]["menu_scan"])
        lspy.set_config("lang", "de")
        lspy.init_lang()
        self.assertEqual(lspy.t("menu_config"), lspy.I18N["de"]["menu_config"])


class TestInfoAndWeb(unittest.TestCase):
    def test_info_reports_real_port(self):
        with ServerPair() as sp:
            with urllib.request.urlopen(f"{sp.base}/api/localsend/v2/info", timeout=5) as resp:
                body = json.loads(resp.read().decode())
            self.assertEqual(resp.status, 200)
            self.assertEqual(body["port"], sp.server.bound_port)
            self.assertEqual(body["version"], lspy.VERSION)

    def test_web_status_page(self):
        with ServerPair() as sp:
            with urllib.request.urlopen(f"{sp.base}/", timeout=5) as resp:
                html = resp.read().decode("utf-8")
            self.assertEqual(resp.status, 200)
            self.assertIn("lspy", html.lower())

    def test_web_disabled_returns_404(self):
        with ServerPair(web_enable=False) as sp:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"{sp.base}/", timeout=5)
            self.assertEqual(ctx.exception.code, 404)

    def test_unknown_endpoint_404(self):
        with ServerPair() as sp:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(f"{sp.base}/api/localsend/v2/nope", timeout=5)
            self.assertEqual(ctx.exception.code, 404)


class TestWebShare(unittest.TestCase):
    """移植自 watchsend 的浏览器分享页：上传 / 下载 / 文本 三件套。"""

    def _get(self, url):
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read()

    def _post(self, url, data, headers=None):
        req = urllib.request.Request(url, data=data, method="POST", headers=headers or {})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read()

    def test_page_has_three_tabs(self):
        with ServerPair() as sp:
            _, raw = self._get(f"{sp.base}/")
            html = raw.decode("utf-8")
            self.assertIn("/web/upload", html)
            self.assertIn("/web/files", html)
            self.assertIn("/web/text", html)
            for key in ("web_tab_upload", "web_tab_download", "web_tab_text"):
                self.assertNotIn(key, html)  # 文案必须真实本地化，不能漏出 key
            self.assertNotIn("@@", html)  # 模板占位符必须全部替换

    def test_info_endpoint(self):
        with ServerPair() as sp:
            _, raw = self._get(f"{sp.base}/web/info")
            info = json.loads(raw.decode())
            self.assertTrue(info["web"])
            self.assertEqual(info["port"], sp.server.bound_port)
            self.assertFalse(info["pinRequired"])

    def test_files_lists_received_files(self):
        with ServerPair() as sp:
            (Path(sp.tmp) / "hello.txt").write_text("abc", encoding="utf-8")
            _, raw = self._get(f"{sp.base}/web/files")
            files = json.loads(raw.decode())["files"]
            names = [f["name"] for f in files]
            self.assertIn("hello.txt", names)
            self.assertEqual([f["size"] for f in files if f["name"] == "hello.txt"], [3])

    def test_upload_saves_into_save_dir(self):
        with ServerPair() as sp:
            status, raw = self._post(f"{sp.base}/web/upload?name=from-web.txt", b"payload")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw.decode())["name"], "from-web.txt")
            target = Path(json.loads(raw.decode())["path"])
            self.assertTrue(target.exists())
            self.assertEqual(target.read_bytes(), b"payload")
            self.assertTrue(str(target.resolve()).startswith(str(Path(sp.tmp).resolve())))

    def test_upload_blocks_extension_policy(self):
        with ServerPair() as sp:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self._post(f"{sp.base}/web/upload?name=evil.exe", b"MZ")
            self.assertEqual(ctx.exception.code, 403)
            self.assertFalse(any(p.suffix == ".exe" for p in Path(sp.tmp).iterdir()))

    def test_download_returns_bytes(self):
        with ServerPair() as sp:
            (Path(sp.tmp) / "dl.bin").write_bytes(b"\x00\x01\x02")
            status, raw = self._get(f"{sp.base}/web/download?name=dl.bin")
            self.assertEqual(status, 200)
            self.assertEqual(raw, b"\x00\x01\x02")

    def test_download_blocks_traversal(self):
        with ServerPair() as sp:
            secret = Path(sp.tmp).parent / "outside.txt"
            secret.write_text("secret", encoding="utf-8")
            try:
                for bad in ("../outside.txt", "..%2Foutside.txt", "sub/../../outside.txt"):
                    with self.assertRaises(urllib.error.HTTPError) as ctx:
                        self._get(f"{sp.base}/web/download?name={bad}")
                    self.assertIn(ctx.exception.code, (400, 404))
            finally:
                secret.unlink()

    def test_upload_blocks_traversal_name(self):
        with ServerPair() as sp:
            _, raw = self._post(f"{sp.base}/web/upload?name=../../escape.txt", b"x")
            saved = Path(json.loads(raw.decode())["path"])
            self.assertTrue(str(saved.resolve()).startswith(str(Path(sp.tmp).resolve())))
            self.assertEqual(saved.name, "escape.txt")

    def test_pin_protects_web_api(self):
        with ServerPair(pin="2468") as sp:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self._get(f"{sp.base}/web/files")
            self.assertEqual(ctx.exception.code, 401)
            _, raw = self._get(f"{sp.base}/web/files?pin=2468")
            self.assertIn("files", json.loads(raw.decode()))
            with self.assertRaises(urllib.error.HTTPError) as ctx2:
                self._post(f"{sp.base}/web/upload?name=x.txt", b"data")
            self.assertEqual(ctx2.exception.code, 401)
            status, _ = self._post(f"{sp.base}/web/upload?name=x.txt&pin=2468", b"data")
            self.assertEqual(status, 200)

    def test_text_endpoint_saves_when_no_clipboard(self):
        with ServerPair() as sp:
            status, raw = self._post(f"{sp.base}/web/text",
                                     json.dumps({"text": "note to self"}).encode(),
                                     {"Content-Type": "application/json"})
            body = json.loads(raw.decode())
            self.assertEqual(status, 200)
            self.assertIn("clipboard", body)
            if not body["clipboard"]:
                self.assertTrue(body["saved"] and Path(body["saved"]).exists())

    def test_text_endpoint_rejects_empty(self):
        with ServerPair() as sp:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self._post(f"{sp.base}/web/text", b"{}")
            self.assertEqual(ctx.exception.code, 400)


class TestWebSafePath(unittest.TestCase):
    def test_blocks_escape(self):
        base = tempfile.mkdtemp(prefix="lspy_web_")
        try:
            self.assertIsNone(lspy.web_safe_path(base, "../x.txt"))
            self.assertIsNone(lspy.web_safe_path(base, "/etc/passwd"))
            self.assertIsNone(lspy.web_safe_path(base, "C:\\Windows\\win.ini"))
            self.assertIsNone(lspy.web_safe_path(base, ""))
            ok = lspy.web_safe_path(base, "sub/a.txt")
            self.assertEqual(ok, (Path(base).resolve() / "sub" / "a.txt"))
        finally:
            shutil.rmtree(base, ignore_errors=True)


class TestPortConflict(unittest.TestCase):
    """Windows 把端口占用报成 WinError 10013，必须仍能识别为冲突并给出回退。"""

    def test_wsaacces_10013_is_conflict(self):
        e = OSError(13, "access denied")
        e.winerror = 10013
        self.assertTrue(lspy.LspyServer._is_port_conflict(e))

    def test_eaddrinuse_is_conflict(self):
        self.assertTrue(lspy.LspyServer._is_port_conflict(OSError(lspy.errno.EADDRINUSE, "in use")))

    def test_other_oserror_is_not_conflict(self):
        self.assertFalse(lspy.LspyServer._is_port_conflict(OSError(lspy.errno.EADDRNOTAVAIL, "bad addr")))

    def test_busy_default_port_falls_back_to_ephemeral(self):
        class FakeHttpd:
            server_address = ("0.0.0.0", 55555)
            def serve_forever(self): pass
            def shutdown(self): pass
            def server_close(self): pass

        srv = lspy.LspyServer(save_dir=tempfile.mkdtemp(), multicast=False, web_enable=False,
                              auto_accept=True)
        srv.port = lspy.DEFAULT_PORT
        tried = []

        def fake_bind(port):
            tried.append(port)
            if port == lspy.DEFAULT_PORT:
                raise OSError(lspy.errno.EADDRINUSE, "in use")
            srv.httpd = FakeHttpd()

        srv._bind_httpd = fake_bind
        srv.start(blocking=True)

        self.assertEqual(tried, [lspy.DEFAULT_PORT, 0])
        self.assertEqual(srv.port, 55555)


class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        lspy.reset_config()

    def _send_and_check(self, payload, filename="hello.bin"):
        with ServerPair() as sp:
            src = Path(sp.tmp).parent / filename
            src.write_bytes(payload)
            try:
                ok = lspy.send_files(sp.device(), [str(src)])
            finally:
                src.unlink(missing_ok=True)
            self.assertTrue(ok)
            received = [p for p in Path(sp.tmp).rglob(filename)]
            self.assertTrue(received, "file not saved")
            self.assertEqual(received[0].read_bytes(), payload)

    def test_roundtrip_small_file(self):
        self._send_and_check(b"lspy e2e payload \x00\x01\x02")

    def test_roundtrip_resume_offset_gt_size(self):
        # 大文件走多块进度路径
        self._send_and_check(b"x" * (1024 * 512), "big.bin")

    def test_same_name_not_overwritten(self):
        with ServerPair() as sp:
            src = Path(sp.tmp).parent / "dup.txt"
            src.write_text("first")
            try:
                self.assertTrue(lspy.send_files(sp.device(), [str(src)]))
                self.assertTrue(lspy.send_files(sp.device(), [str(src)]))
            finally:
                src.unlink(missing_ok=True)
            files = sorted(p.name for p in Path(sp.tmp).rglob("dup*.txt"))
            self.assertEqual(len(files), 2, files)
            self.assertIn("dup.txt", files)


class TestProtocol(unittest.TestCase):
    def setUp(self):
        lspy.reset_config()

    def _post(self, url, body):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            return e.code, None

    def _files_body(self, name, size):
        return {"info": {"alias": "tester", "fingerprint": "fp-test"},
                "files": {"f1": {"id": "f1", "fileName": name, "size": size,
                                 "fileType": "application/octet-stream"}}}

    def test_send_request_v21_flow(self):
        with ServerPair() as sp:
            status, resp = self._post(f"{sp.base}/api/localsend/v2/send-request",
                                      self._files_body("v21.txt", 5))
            self.assertEqual(status, 200)
            sid = resp["sessionId"]; token = resp["files"]["f1"]
            url = f"{sp.base}/api/localsend/v2/send?sessionId={sid}&fileId=f1&token={token}"
            req = urllib.request.Request(url, data=b"hello", method="POST")
            req.add_header("Content-Type", "application/octet-stream")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(r.status, 200)
            self.assertTrue(any(p.read_text() == "hello"
                                for p in Path(sp.tmp).rglob("v21.txt")))

    def test_pin_required_and_accepted(self):
        with ServerPair(pin="246810") as sp:
            status, _ = self._post(f"{sp.base}/api/localsend/v2/prepare-upload",
                                   self._files_body("pin.txt", 3))
            self.assertEqual(status, 401)
            status, resp = self._post(f"{sp.base}/api/localsend/v2/prepare-upload?pin=246810",
                                      self._files_body("pin.txt", 3))
            self.assertEqual(status, 200)
            self.assertIn("sessionId", resp)

    def test_pin_change_applies_to_running_server(self):
        """设置面板改了 PIN 要立刻生效，不能等下一次重启服务。"""
        with ServerPair(pin=None) as sp:
            status, _ = self._post(f"{sp.base}/api/localsend/v2/prepare-upload",
                                   self._files_body("a.txt", 3))
            self.assertEqual(status, 200)          # 改之前不设防
            lspy.set_config("pin", "5678")
            lspy._apply_server_config(sp.server)
            self.assertEqual(sp.server.pin, "5678")
            status, _ = self._post(f"{sp.base}/api/localsend/v2/prepare-upload",
                                   self._files_body("b.txt", 3))
            self.assertEqual(status, 401)
            status, resp = self._post(f"{sp.base}/api/localsend/v2/prepare-upload?pin=5678",
                                      self._files_body("c.txt", 3))
            self.assertEqual(status, 200)
            self.assertIn("sessionId", resp)

    def test_pin_accepts_header_form(self):
        """v1 时代的老客户端只发 X-LocalSend-Pin 头，这条通道也要认。"""
        with ServerPair(pin="1357") as sp:
            req = urllib.request.Request(
                f"{sp.base}/api/localsend/v2/prepare-upload",
                data=json.dumps(self._files_body("h.txt", 2)).encode(), method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("X-LocalSend-Pin", "1357")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(r.status, 200)

    def test_pin_rejection_reads_body_first(self):
        """PIN 不对也要先读完请求体再回 401。

        直接关连接的话，对端还在写 body，拿到的会是连接重置而不是 401，
        官方客户端就不会弹 PIN 输入框。
        """
        with ServerPair(pin="9999") as sp:
            body = self._files_body("big.txt", 3)
            body["pad"] = "z" * 200000        # 把请求体撑到比内核缓冲大
            status, _ = self._post(f"{sp.base}/api/localsend/v2/prepare-upload", body)
            self.assertEqual(status, 401)

    def test_blacklist_rejects(self):
        lspy.set_config("blacklist", ["fp-bad"])
        with ServerPair() as sp:
            body = self._files_body("x.txt", 1)
            body["info"]["fingerprint"] = "fp-bad"
            status, _ = self._post(f"{sp.base}/api/localsend/v2/prepare-upload", body)
            self.assertEqual(status, 403)

    def test_blocked_extension_partial_skip(self):
        lspy.set_config("filter_ext", "exe,bat")
        with ServerPair() as sp:
            body = {"info": {"alias": "tester", "fingerprint": "fp2"},
                    "files": {"a": {"id": "a", "fileName": "evil.exe", "size": 10},
                              "b": {"id": "b", "fileName": "good.txt", "size": 10}}}
            status, resp = self._post(f"{sp.base}/api/localsend/v2/prepare-upload", body)
            self.assertEqual(status, 200)
            self.assertNotIn("a", resp["files"])
            self.assertIn("b", resp["files"])

    def test_all_blocked_returns_403(self):
        lspy.set_config("filter_ext", "exe")
        with ServerPair() as sp:
            body = {"info": {"alias": "t"}, "files": {"a": {"id": "a", "fileName": "x.exe", "size": 1}}}
            status, _ = self._post(f"{sp.base}/api/localsend/v2/prepare-upload", body)
            self.assertEqual(status, 403)

    def test_bad_token_forbidden(self):
        with ServerPair() as sp:
            status, resp = self._post(f"{sp.base}/api/localsend/v2/prepare-upload",
                                      self._files_body("t.txt", 2))
            sid = resp["sessionId"]
            url = f"{sp.base}/api/localsend/v2/upload?sessionId={sid}&fileId=f1&token=wrong"
            req = urllib.request.Request(url, data=b"xx", method="POST")
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(ctx.exception.code, 403)

    def test_cancel_removes_session(self):
        with ServerPair() as sp:
            status, resp = self._post(f"{sp.base}/api/localsend/v2/prepare-upload",
                                      self._files_body("c.txt", 2))
            sid = resp["sessionId"]
            with urllib.request.urlopen(f"{sp.base}/api/localsend/v2/cancel?sessionId={sid}", timeout=5):
                pass
            self.assertNotIn(sid, sp.server.sessions)


class TestHelpers(unittest.TestCase):
    def test_progress_line_non_tty(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            lspy._progress_line("⬆️", "50%", 50)
        self.assertIn("50%", buf.getvalue())

    def test_local_ipv4_returns_list(self):
        ips = lspy.local_ipv4_addresses()
        self.assertIsInstance(ips, list)
        for ip in ips:
            self.assertFalse(ip.startswith("127."))

    def test_cross_chunk_fits_ntfy_limit(self):
        import base64
        encoded = base64.b64encode(b"a" * lspy.CROSS_CHUNK)
        self.assertLess(len(encoded), 4096)


class TestWebLanguage(unittest.TestCase):
    """Web 页跟着浏览器语言走（移植自 watchsend 的 Web 10-Language Adaptive）。"""

    def test_accept_language_picks_highest_q(self):
        self.assertEqual(lspy.pick_accept_language("zh-CN,zh;q=0.9,en;q=0.8"), "zh")
        self.assertEqual(lspy.pick_accept_language("fr;q=0.5,de;q=0.9"), "de")

    def test_accept_language_skips_zero_q_and_unknown(self):
        self.assertEqual(lspy.pick_accept_language("de;q=0, ja-JP"), "ja")
        self.assertIsNone(lspy.pick_accept_language("xx-YY,zz;q=0.5"))

    def test_accept_language_falls_back_to_cli_lang(self):
        self.assertEqual(lspy.pick_accept_language("", "ko"), "ko")
        self.assertEqual(lspy.pick_accept_language(None, "ko"), "ko")

    def test_page_renders_in_browser_language(self):
        import urllib.request
        with ServerPair() as pair:
            req = urllib.request.Request(pair.base + "/", headers={"Accept-Language": "ja-JP,ja;q=0.9"})
            with urllib.request.urlopen(req, timeout=5) as r:
                html = r.read().decode("utf-8")
            self.assertIn('lang="ja"', html)
            self.assertIn(lspy._t_for("ja", "web_title"), html)
            self.assertIn(lspy._t_for("ja", "web_tab_upload"), html)

    def test_page_falls_back_when_browser_lang_unknown(self):
        import urllib.request
        with ServerPair() as pair:
            req = urllib.request.Request(pair.base + "/", headers={"Accept-Language": "xx-YY"})
            with urllib.request.urlopen(req, timeout=5) as r:
                html = r.read().decode("utf-8")
            lang = lspy._current_lang
            self.assertIn(lspy._t_for(lang, "web_title"), html)


class TestDebugKeys(unittest.TestCase):
    """调试键模式：打开后界面直接显示原始 i18n key（watchsend 的 Debug Keys Mode）。"""

    def tearDown(self):
        lspy._debug_keys = False

    def test_debug_keys_returns_raw_key(self):
        lspy._debug_keys = True
        self.assertEqual(lspy.t("history_empty"), "⟦history_empty⟧")
        self.assertEqual(lspy.t("history_entry", t="x", f="y", s=1, r=True), "⟦history_entry⟧")

    def test_debug_keys_off_returns_translation(self):
        lspy._debug_keys = False
        self.assertEqual(lspy.t("history_empty"), lspy._t_for(lspy._current_lang, "history_empty"))

    def test_cli_flag_turns_every_label_into_a_key(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            lspy.main(["--debug-keys", "history"])
        self.assertIn("⟦history_empty⟧", buf.getvalue())


class TestHistoryManage(unittest.TestCase):
    """历史快速管理：删除单条 / 清空 / 解压 ZIP（含 Zip Slip 防护）。"""

    def setUp(self):
        self._history_enable = lspy.get_config("history_enable")
        lspy.set_config("history_enable", True)
        if lspy.HISTORY_FILE.exists():
            lspy.HISTORY_FILE.unlink()

    def tearDown(self):
        if self._history_enable is None:
            lspy.set_config("history_enable", None)
        else:
            lspy.set_config("history_enable", self._history_enable)
        if lspy.HISTORY_FILE.exists():
            lspy.HISTORY_FILE.unlink()

    def _seed(self, names):
        for i, name in enumerate(names):
            lspy.append_history(name, f"/tmp/{name}", i, True)

    def test_zip_entries_are_marked_in_listing(self):
        self.assertEqual(lspy.history_file_label("a.zip"), "a.zip 📦")
        self.assertEqual(lspy.history_file_label("a.txt"), "a.txt")
        self.assertEqual(lspy.history_file_label(None), "")

    def test_delete_removes_the_entry_the_user_saw(self):
        self._seed(["a.txt", "b.zip", "c.txt"])
        self.assertEqual([e["file"] for e in lspy.history_entries_all()], ["c.txt", "b.zip", "a.txt"])
        removed = lspy.delete_history_entry(2)
        self.assertEqual(removed["file"], "b.zip")
        self.assertEqual([e["file"] for e in lspy.history_entries_all()], ["c.txt", "a.txt"])

    def test_delete_out_of_range_returns_none_and_keeps_file(self):
        self._seed(["a.txt"])
        self.assertIsNone(lspy.delete_history_entry(0))
        self.assertIsNone(lspy.delete_history_entry(99))
        self.assertEqual(len(lspy.history_entries_all()), 1)

    def test_clear_wipes_the_file(self):
        import argparse
        from contextlib import redirect_stdout
        self._seed(["a.txt", "b.txt"])
        buf = __import__("io").StringIO()
        with redirect_stdout(buf):
            lspy.cmd_history(argparse.Namespace(n=20, clear=True, delete=None, unzip=None))
        self.assertFalse(lspy.HISTORY_FILE.exists())

    def test_unzip_from_history(self):
        import argparse
        from contextlib import redirect_stdout
        tmp = tempfile.mkdtemp(prefix="lspy_test_zip_")
        self.addCleanup(shutil.rmtree, tmp, True)
        zip_path = Path(tmp) / "bundle.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("inner.txt", "hello")
        lspy.append_history("bundle.zip", str(zip_path), zip_path.stat().st_size, True)
        buf = __import__("io").StringIO()
        with redirect_stdout(buf):
            lspy.cmd_history(argparse.Namespace(n=20, clear=False, delete=None, unzip=1))
        self.assertTrue((Path(tmp) / "bundle" / "inner.txt").is_file())

    def test_unzip_rejects_non_zip_entry(self):
        import argparse
        from contextlib import redirect_stdout
        tmp = tempfile.mkdtemp(prefix="lspy_test_zip_")
        self.addCleanup(shutil.rmtree, tmp, True)
        plain = Path(tmp) / "plain.txt"
        plain.write_text("x", encoding="utf-8")
        lspy.append_history("plain.txt", str(plain), 1, True)
        buf = __import__("io").StringIO()
        with redirect_stdout(buf):
            lspy.cmd_history(argparse.Namespace(n=20, clear=False, delete=None, unzip=1))
        self.assertIn(lspy._t_for(lspy._current_lang, "not_zip")[:6], buf.getvalue())

    def test_unzip_refuses_zip_slip(self):
        import argparse
        from contextlib import redirect_stdout
        tmp = tempfile.mkdtemp(prefix="lspy_test_zip_")
        self.addCleanup(shutil.rmtree, tmp, True)
        evil = Path(tmp) / "evil.zip"
        with zipfile.ZipFile(evil, "w") as zf:
            zf.writestr("../escape.txt", "boom")
        lspy.append_history("evil.zip", str(evil), evil.stat().st_size, True)
        buf = __import__("io").StringIO()
        with redirect_stdout(buf):
            lspy.cmd_history(argparse.Namespace(n=20, clear=False, delete=None, unzip=1))
        self.assertFalse((Path(tmp).parent / "escape.txt").exists())
        self.assertIn(lspy._t_for(lspy._current_lang, "unzip_unsafe")[:4], buf.getvalue())


class TestReceiveClipboard(unittest.TestCase):
    """收到 ≤10KB 的 .txt 自动进剪贴板（对应 watchsend UploadHandler 的行为）。"""

    def setUp(self):
        self._cfg = lspy.get_config("clipboard_text")
        lspy.set_config("clipboard_text", True)
        self._orig = lspy._clipboard_set

    def tearDown(self):
        lspy._clipboard_set = self._orig
        lspy.set_config("clipboard_text", self._cfg)

    def test_small_txt_goes_to_clipboard(self):
        tmp = tempfile.mkdtemp(prefix="lspy_test_clip_")
        self.addCleanup(shutil.rmtree, tmp, True)
        f = Path(tmp) / "code.txt"
        f.write_text("123456", encoding="utf-8")
        captured = []
        lspy._clipboard_set = lambda text: captured.append(text) or True
        self.assertTrue(lspy._maybe_clipboard_text(f))
        self.assertEqual(captured, ["123456"])

    def test_non_txt_and_oversize_are_ignored(self):
        tmp = tempfile.mkdtemp(prefix="lspy_test_clip_")
        self.addCleanup(shutil.rmtree, tmp, True)
        captured = []
        lspy._clipboard_set = lambda text: captured.append(text) or True
        mp4 = Path(tmp) / "clip.mp4"; mp4.write_bytes(b"x" * 8)
        big = Path(tmp) / "big.txt"; big.write_bytes(b"y" * (lspy.CLIPBOARD_TEXT_MAX + 1))
        self.assertFalse(lspy._maybe_clipboard_text(mp4))
        self.assertFalse(lspy._maybe_clipboard_text(big))
        self.assertEqual(captured, [])

    def test_disabled_by_config(self):
        tmp = tempfile.mkdtemp(prefix="lspy_test_clip_")
        self.addCleanup(shutil.rmtree, tmp, True)
        f = Path(tmp) / "note.txt"; f.write_text("hi", encoding="utf-8")
        lspy.set_config("clipboard_text", False)
        lspy._clipboard_set = lambda text: self.fail("不应写入剪贴板")
        self.assertFalse(lspy._maybe_clipboard_text(f))

    def test_web_upload_of_txt_reaches_clipboard(self):
        """走真实 HTTP 上传，确认 _post_process 的接线真的连上了。"""
        captured = []
        lspy._clipboard_set = lambda text: captured.append(text) or True
        with ServerPair() as sp:
            req = urllib.request.Request(f"{sp.base}/web/upload?name=web-note.txt",
                                         data="从浏览器发来".encode("utf-8"), method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
            for _ in range(40):
                if captured: break
                threading.Event().wait(0.05)
        self.assertEqual(captured, ["从浏览器发来"])

    @unittest.skipUnless(sys.platform == "win32", "只有 Windows 走 Win32 剪贴板通道")
    def test_win32_native_clipboard_roundtrip(self):
        """回归：tkinter 缺 init.tcl 时剪贴板整体失效，必须由 Win32 API 通道兜住。"""
        old = lspy._win32_clipboard_get()
        self.addCleanup(lambda: lspy._win32_clipboard_set(old) if old else None)
        probe = "lspy 剪贴板 probe · 42"
        self.assertTrue(lspy._win32_clipboard_set(probe))
        self.assertEqual(lspy._win32_clipboard_get(), probe)

    def test_clipboard_cmd_failure_is_not_success(self):
        """回归：命令存在但退出码非 0（如 xclip 拿不到 X display）必须算失败。"""
        ok, out = lspy._run_clipboard_cmd(("definitely-not-a-clipboard-tool", []), text="x")
        self.assertFalse(ok)
        self.assertEqual(out, "")

    @unittest.skipIf(sys.platform == "win32", "用一个真实 POSIX 命令验证成功路径")
    def test_clipboard_cmd_success_needs_zero_exit_code(self):
        ok, _ = lspy._run_clipboard_cmd(("cat", []), text="abc")
        self.assertTrue(ok)


class TestHistoryTrim(unittest.TestCase):
    """历史条数上限（watchsend HistoryStore 只留最新 100 条）。"""

    def setUp(self):
        self._limit = lspy.get_config("history_max")
        self._enable = lspy.get_config("history_enable")
        lspy.set_config("history_enable", True)
        if lspy.HISTORY_FILE.exists(): lspy.HISTORY_FILE.unlink()

    def tearDown(self):
        lspy.set_config("history_max", self._limit)
        lspy.set_config("history_enable", self._enable)
        if lspy.HISTORY_FILE.exists(): lspy.HISTORY_FILE.unlink()

    def test_old_entries_are_dropped(self):
        lspy.set_config("history_max", 3)
        for i in range(6):
            lspy.append_history(f"f{i}.txt", f"/tmp/f{i}.txt", i, True)
        self.assertEqual([e["file"] for e in lspy.history_entries_all()],
                         ["f5.txt", "f4.txt", "f3.txt"])
        self.assertEqual(len(lspy.HISTORY_FILE.read_text("utf-8").splitlines()), 3)

    def test_zero_disables_trimming(self):
        lspy.set_config("history_max", 0)
        for i in range(5):
            lspy.append_history(f"g{i}.txt", f"/tmp/g{i}.txt", i, True)
        self.assertEqual(len(lspy.HISTORY_FILE.read_text("utf-8").splitlines()), 5)

    def test_trim_keeps_file_parseable(self):
        lspy.set_config("history_max", 2)
        for i in range(4):
            lspy.append_history(f"h{i}.txt", f"/tmp/h{i}.txt", i, True)
        for line in lspy.HISTORY_FILE.read_text("utf-8").splitlines():
            json.loads(line)  # 每行都还是完整 JSON，没被截断


class TestInfoIPv6(unittest.TestCase):
    """info 里补充可直连的 IPv6 地址（对应 watchsend CrossNetActivity 的 [IPv6]:53317）。"""

    def test_prints_bracketed_direct_address(self):
        import argparse
        from contextlib import redirect_stdout
        import io
        orig = lspy.local_ipv6_addresses
        lspy.local_ipv6_addresses = lambda: ["2001:db8::1", "2001:db8::2"]
        self.addCleanup(setattr, lspy, "local_ipv6_addresses", orig)
        buf = io.StringIO()
        with redirect_stdout(buf):
            lspy.cmd_info(argparse.Namespace())
        out = buf.getvalue()
        self.assertIn("IPv6: [2001:db8::1]:", out)
        self.assertIn("[2001:db8::2]", out)

    def test_says_so_when_no_ipv6(self):
        import argparse
        from contextlib import redirect_stdout
        import io
        orig = lspy.local_ipv6_addresses
        lspy.local_ipv6_addresses = lambda: []
        self.addCleanup(setattr, lspy, "local_ipv6_addresses", orig)
        buf = io.StringIO()
        with redirect_stdout(buf):
            lspy.cmd_info(argparse.Namespace())
        self.assertIn(lspy._t_for(lspy._current_lang, "ipv6_not_found")[:4], buf.getvalue())

    def test_enumeration_skips_loopback_and_link_local(self):
        for ip in lspy.local_ipv6_addresses():
            low = ip.lower()
            self.assertFalse(low.startswith("fe8"), ip)
            self.assertNotIn(low, ("::1", "::"))
            self.assertNotIn("%", ip)  # 带 zone id 的链路本地地址不能拿来直连


class TestDialogPicker(unittest.TestCase):
    """随仓库附带的 cfdialog：可选依赖，缺了就降级，不能把菜单弄崩。"""

    class _FakeCf:
        def __init__(self, files=None, folder=None, boom=False):
            self.files, self.folder, self.boom = files, folder, boom
            self.lang = None

        def set_auto_elevate(self, enabled):
            self.auto_elevate = enabled

        def set_language(self, code):
            self.lang = code

        def pick_file(self, **kwargs):
            if self.boom: raise RuntimeError("boom")
            return self.files

        def pick_folder(self, **kwargs):
            if self.boom: raise RuntimeError("boom")
            return self.folder

    def _install(self, fake):
        orig = lspy._CFDIALOG
        lspy._CFDIALOG = fake
        self.addCleanup(setattr, lspy, "_CFDIALOG", orig)

    def test_returns_none_without_library(self):
        self._install(False)
        self.assertIsNone(lspy._cfdialog())
        self.assertIsNone(lspy._dialog_pick_files())
        self.assertIsNone(lspy._dialog_pick_folder())

    def test_module_loader_disables_auto_elevation(self):
        """默认提权会重启整个进程，菜单里用了就是炸给你看。"""
        orig = lspy._CFDIALOG
        lspy._CFDIALOG = None
        self.addCleanup(setattr, lspy, "_CFDIALOG", orig)
        cf = lspy._cfdialog()
        self.assertIsNotNone(cf, "仓库里带了 cfdialog.py，应能加载")
        self.assertFalse(cf._AUTO_ELEVATE)

    def test_multiple_paths_become_strings(self):
        self._install(self._FakeCf(files=[Path("/a/one.txt"), Path("/a/two.txt")]))
        got = lspy._dialog_pick_files()
        self.assertEqual(got, [Path("/a/one.txt"), Path("/a/two.txt")])

    def test_single_path_is_wrapped(self):
        self._install(self._FakeCf(files=Path("/a/one.txt")))
        self.assertEqual(len(lspy._dialog_pick_files(multiple=False)), 1)

    def test_cancel_and_error_mean_nothing_picked(self):
        self._install(self._FakeCf(files=None))
        self.assertEqual(lspy._dialog_pick_files(), [])
        self._install(self._FakeCf(boom=True))
        self.assertEqual(lspy._dialog_pick_files(), [])
        self.assertIsNone(lspy._dialog_pick_folder())

    def test_pick_files_falls_back_to_typed_paths(self):
        """没有 tkinter、没有 cfdialog 时仍能手敲逗号分隔的路径。"""
        from unittest import mock
        self._install(False)
        orig_tk = sys.modules.get("tkinter")
        sys.modules["tkinter"] = None          # 让 import tkinter 直接失败
        self.addCleanup(lambda: sys.modules.__setitem__("tkinter", orig_tk) if orig_tk else sys.modules.pop("tkinter", None))
        with mock.patch.object(lspy, "_prompt", lambda prompt="": 'a.txt, "b c.txt"'):
            self.assertEqual(lspy.pick_files(), ["a.txt", "b c.txt"])

    def test_language_map_matches_cfdialog_packs(self):
        """映射必须是 lspy 语言的子集，且只能映射 cfdialog 真有的语言包。"""
        packs = {"zh_CN", "zh_TW", "en", "ja", "ko", "ru", "fr", "es", "ar"}
        self.assertTrue(set(lspy._CFDIALOG_LANG) <= set(lspy.SUPPORTED_LANGS))
        self.assertEqual(lspy._CFDIALOG_LANG["zh"], "zh_CN")
        self.assertEqual(lspy._CFDIALOG_LANG["zh_TW"], "zh_TW")
        for code in lspy._CFDIALOG_LANG.values():
            self.assertIn(code, packs)


    def test_force_cfdialog_skips_tkinter(self):
        """打开 force_cfdialog 后，即使 tkinter 能导入也不许弹它。"""
        import types
        stub = types.ModuleType("tkinter")

        def _boom(*a, **k):
            raise AssertionError("force_cfdialog 开着还去用 tkinter")

        stub.Tk = _boom
        fake_fd = types.ModuleType("tkinter.filedialog")
        fake_fd.askopenfilenames = _boom
        stub.filedialog = fake_fd

        orig_tk = sys.modules.get("tkinter")
        orig_fd = sys.modules.get("tkinter.filedialog")
        sys.modules["tkinter"] = stub
        sys.modules["tkinter.filedialog"] = fake_fd

        def restore():
            for name, old in (("tkinter", orig_tk), ("tkinter.filedialog", orig_fd)):
                if old is None: sys.modules.pop(name, None)
                else: sys.modules[name] = old

        self.addCleanup(restore)
        self._install(self._FakeCf(files=[Path("/a/one.txt")]))
        lspy.set_config("force_cfdialog", True)
        self.addCleanup(lspy.set_config, "force_cfdialog", None)
        self.assertEqual(lspy.pick_files(), [str(Path("/a/one.txt"))])

    def test_force_cfdialog_still_allows_typed_paths(self):
        """强制 cfdialog 不等于把用户锁死：库没了照样能手敲。"""
        from unittest import mock
        self._install(False)
        orig_tk = sys.modules.get("tkinter")
        sys.modules["tkinter"] = None
        self.addCleanup(lambda: sys.modules.__setitem__("tkinter", orig_tk) if orig_tk else sys.modules.pop("tkinter", None))
        lspy.set_config("force_cfdialog", True)
        self.addCleanup(lspy.set_config, "force_cfdialog", None)
        with mock.patch.object(lspy, "_prompt", lambda prompt="": 'x.bin'):
            self.assertEqual(lspy.pick_files(), ["x.bin"])

    def test_force_cfdialog_is_a_real_config_key(self):
        """开关得能从 CONFIG_DEFAULTS 和 config --set 两个方向进来。"""
        import contextlib
        import io
        self.assertFalse(lspy.CONFIG_DEFAULTS["force_cfdialog"])
        args = type("A", (), {"reset": False, "show": False, "set": "force_cfdialog=1"})()
        lspy.set_config("force_cfdialog", None)
        # 用 StringIO 收口：CI 的 Windows 控制台是 cp1252，✅ 会触发 UnicodeEncodeError
        with contextlib.redirect_stdout(io.StringIO()):
            lspy.cmd_config(args)
        self.assertTrue(lspy.get_config("force_cfdialog"))


    def test_android_is_detected_from_env_marks(self):
        """Android 判定只看环境标记；Termux / 系统变量 / sys.platform 任一条命中即可。"""
        import os as _os
        from unittest import mock
        orig = lspy._IS_ANDROID
        lspy._IS_ANDROID = None
        self.addCleanup(setattr, lspy, "_IS_ANDROID", orig)

        def probe(env, platform="linux"):
            lspy._IS_ANDROID = None
            base = {k: v for k, v in _os.environ.items()
                    if k not in ("TERMUX_VERSION", "PREFIX", "ANDROID_ROOT", "ANDROID_DATA")}
            base.update(env)
            with mock.patch.dict(_os.environ, base, clear=True), \
                 mock.patch.object(sys, "platform", platform):
                return lspy._is_android()

        self.assertTrue(probe({"TERMUX_VERSION": "0.118"}))
        self.assertTrue(probe({"PREFIX": "/data/data/com.termux/files/usr"}))
        self.assertTrue(probe({"ANDROID_ROOT": "/system"}))
        self.assertTrue(probe({}, platform="android"))
        self.assertFalse(probe({"PREFIX": "/usr"}))

    def test_android_skips_tkinter_and_uses_cfdialog(self):
        """Android 上不许 import tkinter，选文件要直接落到 cfdialog。"""
        import types
        from unittest import mock
        stub = types.ModuleType("tkinter")

        def _boom(*a, **k):
            raise AssertionError("Android 上不该 import tkinter")

        stub.Tk = _boom
        fake_fd = types.ModuleType("tkinter.filedialog")
        fake_fd.askopenfilenames = _boom
        stub.filedialog = fake_fd
        self._install(self._FakeCf(files=[Path("/sdcard/one.txt")]))
        with mock.patch.object(lspy, "_is_android", lambda: True), \
             mock.patch.dict(sys.modules, {"tkinter": stub, "tkinter.filedialog": fake_fd}):
            self.assertEqual(lspy.pick_files(), [str(Path("/sdcard/one.txt"))])

    def test_android_without_library_still_types_paths(self):
        """Android 上没有 cfdialog 时，落到手敲路径而不是崩。"""
        from unittest import mock
        self._install(False)
        with mock.patch.object(lspy, "_is_android", lambda: True), \
             mock.patch.dict(sys.modules, {"tkinter": None}), \
             mock.patch.object(lspy, "_prompt", lambda prompt="": '/sdcard/a.txt,/sdcard/b.txt'):
            self.assertEqual(lspy.pick_files(), ["/sdcard/a.txt", "/sdcard/b.txt"])


class _FakeServer:
    """只为调用 LspyServer 的接收确认逻辑，不真的开端口。"""

    def __init__(self):
        import threading
        self.quiet_receive = False
        self.lock = threading.Lock()
        self.sessions = {}
        self.save_dir = "downloads"

    _accept_request = lspy.LspyServer._accept_request


class _FakeTTY:
    def isatty(self): return True
    def readline(self): return ""


class TestInteractiveInvite(unittest.TestCase):
    """任意界面的接收申请：等输入时弹申请、接受后进详情、回车回到原问题。"""

    def setUp(self):
        import queue
        from unittest import mock
        self._saved = (lspy._INVITE_Q, lspy.INTERACTIVE, lspy._read_line_task)
        lspy._INVITE_Q = queue.Queue()
        lspy.INTERACTIVE = True
        p = mock.patch.object(sys, "stdin", _FakeTTY())
        p.start(); self.addCleanup(p.stop)
        self.addCleanup(self._restore)

    def _restore(self):
        lspy._INVITE_Q, lspy.INTERACTIVE, lspy._read_line_task = self._saved

    def _reader(self, lines):
        """按顺序吐行的假 reader；用尽后返回空串（相当于 EOF）。"""
        import concurrent.futures
        box = list(lines)
        def make():
            f = concurrent.futures.Future()
            f.set_result(box.pop(0) if box else "")
            return f
        return make

    def _invite(self, srv, auto=False, sid="sid123"):
        return {"alias": "phone", "ip": "192.168.1.9", "count": 2,
                "names": ["a.txt", "b.txt"], "total": 30, "auto": auto,
                "accepted": False, "decision": threading.Event(),
                "server": srv, "sid": sid}

    def test_human_size(self):
        self.assertEqual(lspy._fmt_size(0), "0 B")
        self.assertEqual(lspy._fmt_size(1536), "1.5 KB")
        self.assertEqual(lspy._fmt_size(5 * 1024 * 1024), "5.0 MB")
        self.assertEqual(lspy._fmt_size(2 * 1024 ** 3), "2.0 GB")

    def test_enter_accepts_and_r_rejects(self):
        from unittest import mock
        cases = [("", True), ("r", False), ("R", False), ("no", False)]
        with mock.patch.object(lspy, "_read_line_task", self._reader(["\n", "r", "R", "no"])):
            self.assertTrue(lspy._ask_invite(timeout=2))
            self.assertFalse(lspy._ask_invite(timeout=2))
            self.assertFalse(lspy._ask_invite(timeout=2))
            self.assertFalse(lspy._ask_invite(timeout=2))

    def test_eof_counts_as_reject(self):
        from unittest import mock
        with mock.patch.object(lspy, "_read_line_task", self._reader([])):
            self.assertFalse(lspy._ask_invite(timeout=2))

    def test_cmdline_serve_keeps_terminal_confirmation(self):
        """没有交互菜单（serve 子命令）时不该把申请塞进菜单队列。"""
        lspy.INTERACTIVE = False
        srv = _FakeServer()
        inv = srv._accept_request("phone", "192.168.1.9",
                                  {"a": {"fileName": "a.txt", "size": 3}}, auto=True)
        self.assertTrue(inv["accepted"])
        self.assertEqual(lspy._INVITE_Q.qsize(), 0)

    def test_auto_accept_goes_straight_to_details(self):
        """开了自动接收：不问就直接进详情（邀请入队，由菜单画进度）。"""
        srv = _FakeServer()
        inv = srv._accept_request("phone", "192.168.1.9",
                                  {"a": {"fileName": "a.txt", "size": 3}}, auto=True)
        self.assertTrue(inv["accepted"])
        self.assertEqual(lspy._INVITE_Q.qsize(), 1)

    def test_invite_pops_up_while_answering_another_prompt(self):
        """正等着用户回答别的问题时，邀请先弹出来；接受后进详情，回车后回到原问题。"""
        import contextlib
        import io
        from unittest import mock
        srv = _FakeServer()
        lspy._INVITE_Q.put(self._invite(srv))
        # 第一次读到的行当作接受（空行），第二次供详情回车，第三次是原问题答案
        with mock.patch.object(lspy, "_read_line_task", self._reader(["\n", "\n", "2"])):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(lspy._prompt("choose: "), "2")
        out = buf.getvalue()
        self.assertIn("📥", out)
        self.assertIn("a.txt", out)
        self.assertIn(lspy.t("recv_detail_done").split("{")[0].strip(), out)

    def test_reject_skips_details_and_returns_to_prompt(self):
        import contextlib
        import io
        from unittest import mock
        srv = _FakeServer()
        lspy._INVITE_Q.put(self._invite(srv))
        with mock.patch.object(lspy, "_read_line_task", self._reader(["r", "3"])):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(lspy._prompt("choose: "), "3")
        self.assertIn(lspy.t("invite_rejected"), buf.getvalue())

    def test_non_tty_input_still_works(self):
        """管道/重定向下退回普通 input()，不启动轮询。"""
        import builtins
        from unittest import mock
        class _Piped:
            def isatty(self): return False
            def readline(self): return ""
        with mock.patch.object(sys, "stdin", _Piped()), \
             mock.patch.object(builtins, "input", lambda prompt="": "typed"):
            self.assertEqual(lspy._prompt("q: "), "typed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
