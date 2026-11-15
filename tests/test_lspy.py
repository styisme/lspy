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


if __name__ == "__main__":
    unittest.main(verbosity=2)
