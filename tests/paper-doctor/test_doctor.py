from __future__ import annotations

import sys
import os
import unittest
from unittest import mock

# 把 skills/_shared 加进 path，使 doctor.py 能 import _shared（与 doctor.py 自身引导头同源）
import pathlib
import tempfile
_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "_shared"))
sys.path.insert(0, str(_REPO / "skills" / "paper-doctor" / "scripts"))

import doctor  # noqa: E402

from paper_shared.datasources.cache import Cache  # noqa: E402
from paper_shared.datasources.transport import Transport  # noqa: E402
from tests.datasources.fakes import FakeResponse, http_error  # noqa: E402


def _build_ok_transport():
    """无限返回 HTTP 200 的 fake transport（arXiv 走空 Atom，其余走空 JSON），
    sleep no-op 绕过退避。提到模块级以便 run_all / main 路径的测试复用，
    避免这些测试退化成真实网络依赖（离线挂起、CI 脆弱）。"""
    _ARXIV_ATOM = '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'

    def _open(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        body = _ARXIV_ATOM if "arxiv.org" in url else {}
        return FakeResponse(200, body)

    return Transport(user_agent="test", opener=_open, sleep=lambda s: None)


class TestCheckPythonVersion(unittest.TestCase):
    def test_ok_when_311(self):
        with mock.patch.object(doctor, "sys") as m_sys:
            m_sys.version_info = (3, 11, 5, "final", 0)
            r = doctor.check_python_version()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["check"], "python_version")
        self.assertIn("3.11", r["detail"])

    def test_fail_when_38(self):
        with mock.patch.object(doctor, "sys") as m_sys:
            m_sys.version_info = (3, 8, 10, "final", 0)
            r = doctor.check_python_version()
        self.assertEqual(r["status"], "fail")
        self.assertIsNone(r["fix"])  # 版本是用户环境，doctor 不给改法，只报


class TestCheckSqlite3(unittest.TestCase):
    def test_ok(self):
        r = doctor.check_sqlite3()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["check"], "sqlite3")


class TestCheckSharedImport(unittest.TestCase):
    def test_ok(self):
        r = doctor.check_shared_import()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["check"], "shared_import")

    def test_fail_when_shared_unimportable(self):
        # check_shared_import 的 except 分支：模拟 _shared 导入失败，须报 fail 不崩。
        # 不能靠坏路径——本测试文件顶部已把真实 _shared 注入 sys.path，
        # 故用 mock __import__ 强制 import paper_shared.datasources 抛错。
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "paper_shared.datasources":
                raise ImportError("模拟 _shared 不可导入")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = fake_import
        try:
            r = doctor.check_shared_import()
        finally:
            builtins.__import__ = real_import
        self.assertEqual(r["status"], "fail")
        self.assertIsNotNone(r["fix"])
        self.assertIn("detail", r)


class TestRunProbeFresh(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache_path = pathlib.Path(self.tmp.name) / "p.db"
        # SemanticScholarClient.probe() 无 key 时自报 partial（走 1 req/s 慢速档），
        # 会把 overall 拉到 degraded。设 fixture key 让 S2 走 with-credential 档报 ok，
        # 以测 brief 的「核心全可达 → overall=ok」语义。offline 测试不受影响
        # （503 → TransportError → unavailable，partial 降级只在 status==ok 时触发）。
        self._env_patch = mock.patch.dict(
            os.environ, {"SEMANTIC_SCHOLAR_API_KEY": "fixture-test-key"})
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def _ok_transport(self):
        """见模块级 _build_ok_transport——probe 含重试时永不耗尽 opener、
        代表服务可达空结果，probe 判 ok。"""
        return _build_ok_transport()

    def _fail_transport(self):
        """恒抛 HTTP 503 的 transport——核心源 probe 全部退避耗尽 → unavailable → offline。"""
        def _fail(req, timeout=None):
            url = req.full_url if hasattr(req, "full_url") else "https://x"
            raise http_error(url, 503)
        return Transport(user_agent="test", opener=_fail, sleep=lambda s: None)

    def test_all_ok(self):
        t = self._ok_transport()
        results, overall = doctor.run_probe_fresh(transport=t, cache=Cache(self.cache_path))
        self.assertEqual(overall, "ok")
        self.assertTrue(len(results) >= 4)
        self.assertTrue(all(r["status"] in ("ok", "unavailable", "partial") for r in results))

    def test_all_core_unavailable_is_offline(self):
        t = self._fail_transport()
        results, overall = doctor.run_probe_fresh(transport=t, cache=Cache(self.cache_path))
        self.assertEqual(overall, "offline")
        # 核心源全 unavailable
        core = [r for r in results if r["source"] in
                ("crossref", "openalex", "semantic_scholar", "arxiv")]
        self.assertTrue(all(r["status"] == "unavailable" for r in core))

    def test_supplementary_does_not_lower_overall(self):
        # 核心 ok 即 overall=ok；补充源状态不拉低（overall 仅看 CORE_IDS）
        t = self._ok_transport()
        results, overall = doctor.run_probe_fresh(transport=t, cache=Cache(self.cache_path))
        self.assertEqual(overall, "ok")

    def test_returns_to_dict_shape(self):
        t = self._ok_transport()
        results, overall = doctor.run_probe_fresh(transport=t, cache=Cache(self.cache_path))
        for r in results:
            self.assertIn("source", r)
            self.assertIn("status", r)
            self.assertIn("role", r)

    def test_no_trace_when_cache_is_none(self):
        # 回归 SKILL.md 红线 1 / spec §7.1「全程零文件系统改动」：
        # 默认 CLI 路径（cache=None）不得在用户 cache 目录建库留痕。
        # 设 PAPER_CACHE_DIR 指向一个不存在的干净目录，调 run_probe_fresh(cache=None)，
        # 断言该目录未被创建、无 datasources.db——临时 Cache 须在探测后清理。
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "paper_fresh"  # 不存在的子目录
            self.assertFalse(target.exists())
            with mock.patch.dict(os.environ, {"PAPER_CACHE_DIR": str(target)}):
                results, overall = doctor.run_probe_fresh(
                    transport=self._ok_transport(), cache=None)
            self.assertFalse(target.exists(),
                             "默认探测路径不应在用户 cache 目录建库留痕")
            self.assertFalse((target / "datasources.db").exists())
            self.assertTrue(len(results) >= 4)  # 探测本身仍正常完成


class TestCheckCredentials(unittest.TestCase):
    def test_all_present(self):
        with mock.patch.dict("os.environ",
                             {"PAPER_MAILTO": "a@b.c", "SEMANTIC_SCHOLAR_API_KEY": "k",
                              "NCBI_API_KEY": "n"}, clear=False):
            r = doctor.check_credentials()
        self.assertEqual(len(r), 3)
        self.assertTrue(all(item["status"] == "ok" for item in r))
        self.assertTrue(all("impact" in item and "fix" in item for item in r))

    def test_all_missing(self):
        # 临时清空三件套
        env_backup = {k: __import__("os").environ.pop(k, None)
                      for k in ("PAPER_MAILTO", "SEMANTIC_SCHOLAR_API_KEY", "NCBI_API_KEY")}
        try:
            r = doctor.check_credentials()
        finally:
            for k, v in env_backup.items():
                if v is not None:
                    __import__("os").environ[k] = v
        self.assertTrue(all(item["status"] == "missing" for item in r))

    def test_returns_three_known(self):
        r = doctor.check_credentials()
        names = {item["check"] for item in r}
        self.assertEqual(names, {"PAPER_MAILTO", "SEMANTIC_SCHOLAR_API_KEY", "NCBI_API_KEY"})


class TestCheckCache(unittest.TestCase):
    def test_ok_writable(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.dict("os.environ", {"PAPER_CACHE_DIR": d}, clear=False):
                r = doctor.check_cache()
            self.assertEqual(r["status"], "ok")
            self.assertIn("path", r)

    def test_fail_unwritable(self):
        # 指向一个只读目录（无写权限）。用 TemporaryDirectory 兜底清理。
        with tempfile.TemporaryDirectory() as d:
            os.chmod(d, 0o555)
            try:
                with mock.patch.dict("os.environ", {"PAPER_CACHE_DIR": d}, clear=False):
                    r = doctor.check_cache()
            finally:
                os.chmod(d, 0o755)  # 恢复写权限以便 TemporaryDirectory 清理
            self.assertEqual(r["status"], "fail")

    def test_no_trace_when_creating_cache_dir(self):
        # PAPER_CACHE_DIR 指向不存在的目录：诊断后不应留下新建的 cache 目录痕迹
        # （Important：check_cache 的「无副作用诊断」约束）
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "paper_fresh"  # 不存在的子目录
            self.assertFalse(target.exists())
            with mock.patch.dict("os.environ", {"PAPER_CACHE_DIR": str(target)}, clear=False):
                r = doctor.check_cache()
            self.assertEqual(r["status"], "ok")
            self.assertFalse(target.exists(), "诊断不应留下新建的 cache 目录")


class TestInferNetwork(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(doctor.infer_network("ok")["status"], "ok")

    def test_offline(self):
        self.assertEqual(doctor.infer_network("offline")["status"], "offline")

    def test_degraded_treated_as_ok(self):
        # degraded = 部分源可达，网络本身在线
        self.assertEqual(doctor.infer_network("degraded")["status"], "ok")

    def test_unknown_when_datasources_none(self):
        self.assertEqual(doctor.infer_network(None)["status"], "unknown")


class TestComputeOverall(unittest.TestCase):
    def _rt(self, status):
        return [{"check": "x", "status": status, "detail": "", "fix": None}]

    def test_blocked_when_runtime_fail(self):
        self.assertEqual(
            doctor.compute_overall(self._rt("fail"), "ok", "ok", False), "blocked")

    def test_offline_when_network_offline(self):
        self.assertEqual(
            doctor.compute_overall(self._rt("ok"), "offline", "offline", False), "offline")

    def test_offline_when_datasources_offline(self):
        # 区别于 test_offline_when_network_offline：网络推断 ok 但核心数据源全 offline，
        # 独立覆盖 compute_overall 的 OR 另一支（datasources_overall=="offline"）。
        # compute_overall 是纯函数、独立测其分支——infer_network 实际会把 ds_offline
        # 推断为 network offline，但本测试不经过 infer_network。
        self.assertEqual(
            doctor.compute_overall(self._rt("ok"), "ok", "offline", False), "offline")

    def test_degraded_when_datasources_degraded(self):
        self.assertEqual(
            doctor.compute_overall(self._rt("ok"), "ok", "degraded", False), "degraded")

    def test_ok_when_all_green(self):
        self.assertEqual(
            doctor.compute_overall(self._rt("ok"), "ok", "ok", False), "ok")

    def test_ok_with_supp_unavailable(self):
        # 补充源不可达不拉低到 offline；但算 degraded（spec §4 表注：补充源 unavailable
        # → ok 降到 degraded）。注意：这与 probe.overall() 不完全一致——probe 的 overall
        # 对 supp 不可达判 ok；doctor 在其上叠一层：有 supp unavailable 则 degraded。
        self.assertEqual(
            doctor.compute_overall(self._rt("ok"), "ok", "ok", True), "degraded")

    def test_blocked_priority_over_offline(self):
        # runtime fail 同时 datasources offline → blocked 优先（_shared 不可导入时
        # datasources_overall 为 None，但 runtime 已 fail，取 blocked）
        self.assertEqual(
            doctor.compute_overall(self._rt("fail"), "unknown", None, False), "blocked")


class TestRunAll(unittest.TestCase):
    def test_returns_full_contract(self):
        # 注入 fake transport——否则 run_all() 默认自建真实 Transport 探测 6 源，
        # 离线/受限网下退避重试挂起（CI 有网也脆弱）。生产代码本就支持依赖注入。
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.dict("os.environ", {"PAPER_CACHE_DIR": d}, clear=False):
                report = doctor.run_all(transport=_build_ok_transport(),
                                        cache=Cache(pathlib.Path(d) / "c.db"))
        for key in ("overall", "runtime", "credentials", "network",
                    "cache", "datasources", "datasources_overall"):
            self.assertIn(key, report)
        self.assertIn(report["overall"], ("blocked", "offline", "degraded", "ok"))


class TestCLIMain(unittest.TestCase):
    def test_stdout_is_valid_json(self):
        import io
        import json
        from contextlib import redirect_stdout
        buf = io.StringIO()
        # main() 无 transport 注入点——打桩 run_probe_fresh 使 CLI 路径离线，
        # 只验证 stdout 是合法 JSON 且含 overall（探测逻辑由 TestRunProbeFresh 覆盖）。
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict("os.environ", {"PAPER_CACHE_DIR": d}, clear=False), \
                mock.patch.object(doctor, "run_probe_fresh",
                                  lambda transport=None, cache=None: ([], "ok")), \
                redirect_stdout(buf):
            doctor.main()
        data = json.loads(buf.getvalue())
        self.assertIn("overall", data)


class TestSkillMdStructure(unittest.TestCase):
    def test_skill_md_exists_and_has_frontmatter(self):
        skill_path = _REPO / "skills" / "paper-doctor" / "SKILL.md"
        self.assertTrue(skill_path.exists(), "skills/paper-doctor/SKILL.md 应存在")
        text = skill_path.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"), "SKILL.md 须以 frontmatter 开头")
        self.assertIn("name: paper-doctor", text)
        self.assertIn("description:", text)

    def test_skill_md_has_redlines_and_report(self):
        text = (_REPO / "skills" / "paper-doctor" / "SKILL.md").read_text(encoding="utf-8")
        # 三条红线关键词
        self.assertIn("只体检不代修", text)
        self.assertIn("脚本真实结果", text)
        self.assertIn("越界", text)
        # 四态中文映射
        for cn in ("环境未就绪", "核验不可用", "可用但有降级", "就绪"):
            self.assertIn(cn, text)


if __name__ == "__main__":
    unittest.main()
