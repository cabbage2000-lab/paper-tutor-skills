"""paper-verify scripts/verify.py 编排测试——mock fetch_batch，验证解析→判定→报告→落盘拼装。

不联网：fetch 注入构造好的 BatchResult。judge / report / parse 的细节已各有单测，
本测试只验编排（输入到产物）是否正确串联。
"""
from __future__ import annotations

import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "_shared"))
sys.path.insert(0, str(_REPO / "skills" / "paper-verify" / "scripts"))

import verify  # noqa: E402
from paper_shared.datasources.models import BatchResult, Evidence, Ref  # noqa: E402


def _fake_fetch(evidences, network_status="ok"):
    batch = BatchResult(evidences=evidences, stats={}, network_status=network_status)
    return lambda *a, **k: batch


class TestVerifyEndToEnd(unittest.TestCase):
    def test_not_found_and_pending_mocked_fetch(self):
        bib = ('@article{a, title={A Fake}, doi={10.9999/fake.0001}}\n'
               '@article{b, title={中文研究}, doi={10.3969/x}}')
        evidences = {
            "r1": Evidence(ref_id="r1", input=Ref(id="r1", doi="10.9999/fake.0001"),
                           doi_ra="not_registered"),
            "r2": Evidence(ref_id="r2", input=Ref(id="r2", doi="10.3969/x"),
                           doi_ra="ISTIC"),
        }
        with tempfile.TemporaryDirectory() as d:
            args = verify._parse_args(["--text", bib, "--out-dir", d, "--no-format"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = verify.run(args, fetch=_fake_fetch(evidences))
            self.assertEqual(rc, 0)

            jsons = sorted(pathlib.Path(d).glob("verify-*.json"))
            mds = sorted(pathlib.Path(d).glob("verify-*.md"))
            self.assertEqual(len(jsons), 1)
            self.assertEqual(len(mds), 1)

            data = json.loads(jsons[0].read_text(encoding="utf-8"))
            self.assertEqual(data["stats"]["total"], 2)
            self.assertEqual(data["stats"]["by_status"].get("NOT_FOUND"), 1)
            self.assertEqual(data["stats"]["by_status"].get("PENDING_MANUAL"), 1)

            md = mds[0].read_text(encoding="utf-8")
            self.assertIn("疑似不存在", md)
            self.assertIn("人工核对包", md)          # PENDING_MANUAL 条目内嵌核对包

            summary = json.loads(buf.getvalue())
            self.assertEqual(summary["total"], 2)
            self.assertEqual(summary["report_json"], str(jsons[0]))

    def test_manual_result_upgrades_to_verified(self):
        # 旧报告 r2 的 manual_result 标 verified=True → 重跑升级为 VERIFIED
        bib = '@article{b, title={中文研究}, doi={10.3969/x}}'
        evidences = {"r1": Evidence(ref_id="r1", input=Ref(id="r1", doi="10.3969/x"),
                                    doi_ra="ISTIC")}
        with tempfile.TemporaryDirectory() as d:
            manual_path = pathlib.Path(d) / "old.json"
            manual_path.write_text(json.dumps({
                "items": [{"ref_id": "r1",
                           "manual_result": {"verified": True, "checked_at": "2026-07-26"}}]
            }), encoding="utf-8")
            args = verify._parse_args(
                ["--text", bib, "--out-dir", d, "--apply-manual", str(manual_path), "--no-format"])
            with redirect_stdout(io.StringIO()):
                rc = verify.run(args, fetch=_fake_fetch(evidences))
            self.assertEqual(rc, 0)
            data = json.loads(next(pathlib.Path(d).glob("verify-2*.json")).read_text(encoding="utf-8"))
            self.assertEqual(data["items"][0]["status"], "VERIFIED")

    def test_no_input_returns_error(self):
        args = verify._parse_args([])
        with redirect_stderr(io.StringIO()):
            rc = verify.run(args, fetch=lambda *a, **k: None)
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
