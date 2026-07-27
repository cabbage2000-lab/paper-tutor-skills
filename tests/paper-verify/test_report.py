"""paper-verify scripts/report.py 渲染单测——JSON 组装 + Markdown 关键节。"""
from __future__ import annotations

import pathlib
import sys
import unittest

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "_shared"))
sys.path.insert(0, str(_REPO / "skills" / "paper-verify" / "scripts"))

import report  # noqa: E402


def _sample_payload():
    return {
        "run_id": "verify-20260725-1400",
        "created_at": "2026-07-25T14:00:00Z",
        "input_fingerprint": "sha256:abc",
        "network_status": "ok",
        "stats": {"total": 3, "by_status": {"VERIFIED": 1, "NOT_FOUND": 1, "PENDING_MANUAL": 1},
                  "elapsed_s": 5.0, "sources_queried": ["crossref"]},
        "sources_checked": [
            {"source": "crossref", "name_zh": "Crossref", "role": "core", "coverage": "自动核验"},
            {"source": "cnki", "name_zh": "中国知网", "role": "guided", "coverage": "待人工核对"},
        ],
        "items": [
            {"ref_id": "r1", "raw_text": "[1] Smith. Title[J]. J, 2020.", "status": "VERIFIED",
             "field_notes": [], "evidence_summary": "已在 crossref 找到且元数据一致",
             "exit_guidance": None,
             "evidence": {"doi_ra": "Crossref", "queries": [{"source": "crossref", "outcome": "hit"}], "hits": []},
             "format_issues": [], "manual_result": None},
            {"ref_id": "r2", "raw_text": "[2] Fake. DOI: 10.9999/x", "status": "NOT_FOUND",
             "field_notes": [], "evidence_summary": "DOI 前缀未注册——疑似不存在的引用",
             "exit_guidance": "复核：doi.org 手查",
             "evidence": {"doi_ra": "not_registered", "queries": [], "hits": []},
             "format_issues": [], "manual_result": None},
            {"ref_id": "r3", "raw_text": "[3] 王某. 中文研究[J].", "status": "PENDING_MANUAL",
             "field_notes": [], "evidence_summary": "ISTIC 中文 DOI，待人工核对",
             "exit_guidance": "核对包",
             "evidence": {"doi_ra": "ISTIC", "queries": [], "hits": []},
             "format_issues": [], "manual_result": None},
        ],
    }


class TestBuildJsonPayload(unittest.TestCase):
    def test_payload_has_all_top_keys(self):
        meta = {"run_id": "v", "created_at": "2026-07-25T00:00:00Z", "fingerprint": "f",
                "network_status": "ok", "sources_checked": []}
        payload = report.build_json_payload(meta, [], {"total": 0})
        for k in ("run_id", "created_at", "input_fingerprint", "network_status",
                  "stats", "sources_checked", "items"):
            self.assertIn(k, payload)


class TestBuildMarkdown(unittest.TestCase):
    def setUp(self):
        self.md = report.build_markdown(_sample_payload())

    def test_has_title_and_distribution(self):
        self.assertIn("引用核验报告", self.md)
        self.assertIn("六态分布", self.md)
        self.assertIn("已核实", self.md)
        self.assertIn("未找到（疑似不存在）", self.md)

    def test_priority_section_lists_not_found(self):
        self.assertIn("需优先关注", self.md)
        self.assertIn("r2", self.md)

    def test_sources_section_lists_auto_and_guided(self):
        self.assertIn("已查源清单", self.md)
        self.assertIn("Crossref", self.md)
        self.assertIn("中国知网", self.md)
        self.assertIn("待人工核对", self.md)

    def test_pending_item_has_manual_checklist(self):
        self.assertIn("人工核对包", self.md)
        self.assertIn("知网高级检索", self.md)
        self.assertIn("manual_result", self.md)

    def test_has_human_machine_footer(self):
        self.assertIn("人机分工", self.md)
        self.assertIn("非动机指控", self.md)

    def test_evidence_chain_collapsible(self):
        self.assertIn("<details>", self.md)
        self.assertIn("DOI 路由", self.md)

    def test_no_priority_section_when_none(self):
        payload = _sample_payload()
        payload["items"] = [it for it in payload["items"] if it["status"] == "VERIFIED"]
        payload["stats"]["by_status"] = {"VERIFIED": 1}
        md = report.build_markdown(payload)
        self.assertNotIn("需优先关注", md)


class TestWriteOutputs(unittest.TestCase):
    def test_writes_both_files(self):
        import tempfile
        d = tempfile.mkdtemp()
        jp = pathlib.Path(d) / "v.json"
        mp = pathlib.Path(d) / "v.md"
        report.write_outputs(_sample_payload(), jp, mp)
        self.assertTrue(jp.exists())
        self.assertTrue(mp.exists())
        import json
        loaded = json.loads(jp.read_text(encoding="utf-8"))
        self.assertEqual(loaded["run_id"], "verify-20260725-1400")
        self.assertIn("引用核验报告", mp.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
