"""paper-search scripts/search.py 的确定性逻辑单测：去重 / 排序 / 分页 / 组装。

导入范式同 tests/paper-doctor/test_doctor.py（sys.path 加 _shared 与 skill scripts 后 import）。
验证外部可观察行为，不测实现细节。
"""
from __future__ import annotations

import pathlib
import sys
import unittest

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "_shared"))
sys.path.insert(0, str(_REPO / "skills" / "paper-search" / "scripts"))

import render_html  # noqa: E402
import search  # noqa: E402

from paper_shared.datasources.models import Evidence, Ref, SearchResult, SourceHit  # noqa: E402


def _hit(source, doi=None, title="T", year=2020, typ="journal-article", venue="V", from_cache=False):
    return SourceHit(source=source,
                     metadata={"title": title, "doi": doi, "year": year, "venue": venue,
                               "type": typ, "authors": ["X"]},
                     fetched_at="2026-01-01T00:00:00Z", from_cache=from_cache)


class TestDedup(unittest.TestCase):
    def test_same_doi_merged_authority_order(self):
        # 大小写不同的同一 DOI，normalize 后归并；主源取权威序最高的 crossref
        items = [_hit("openalex", doi="10.1/a"), _hit("crossref", doi="10.1/A")]
        m = search.dedup_hits(items)
        self.assertEqual(len(m), 1)
        self.assertEqual(set(m[0]["sources"]), {"crossref", "openalex"})
        self.assertEqual(m[0]["primary_source"], "crossref")

    def test_no_doi_same_title_merged(self):
        items = [_hit("arxiv", doi=None, title="Deep Learning!"),
                 _hit("eric", doi=None, title="deep  learning")]
        self.assertEqual(len(search.dedup_hits(items)), 1)

    def test_different_doi_not_merged(self):
        items = [_hit("crossref", doi="10.1/a"), _hit("crossref", doi="10.2/b")]
        self.assertEqual(len(search.dedup_hits(items)), 2)

    def test_no_doi_no_title_independent(self):
        items = [_hit("arxiv", doi=None, title=None), _hit("arxiv", doi=None, title=None)]
        self.assertEqual(len(search.dedup_hits(items)), 2)

    def test_url_from_doi(self):
        m = search.dedup_hits([_hit("crossref", doi="10.1/a")])
        self.assertEqual(m[0]["url"], "https://doi.org/10.1/a")


class TestRank(unittest.TestCase):
    def test_year_desc_none_last(self):
        merged = [{"year": 2019, "sources": ["a"]}, {"year": 2023, "sources": ["b"]},
                  {"year": None, "sources": ["c"]}]
        out = search.rank_hits(merged, "year_desc")
        self.assertEqual([m["year"] for m in out], [2023, 2019, None])

    def test_source_count_desc(self):
        merged = [{"year": 2020, "sources": ["a"]}, {"year": 2019, "sources": ["a", "b", "c"]}]
        out = search.rank_hits(merged, "source_count")
        self.assertEqual(len(out[0]["sources"]), 3)


class TestPayload(unittest.TestCase):
    def test_stats_dedup_rank_and_passthrough(self):
        items = [_hit("crossref", doi="10.1/a", year=2020),
                 _hit("openalex", doi="10.1/a", year=2020),
                 _hit("arxiv", doi="10.3/c", year=2023)]
        result = SearchResult(items=items,
                              coverage=[{"source": "crossref", "coverage": "自动检索"}],
                              network_status="ok")
        p = search.build_payload("q", {"year_from": 2018}, result, sort="year_desc", limit=30)
        self.assertEqual(p["stats"]["raw_hits"], 3)
        self.assertEqual(p["stats"]["after_dedup"], 2)     # 10.1/a 两源合并
        self.assertEqual(p["results"][0]["rank"], 1)
        self.assertEqual(p["results"][0]["year"], 2023)    # year_desc：2023 在前
        self.assertEqual(p["network_status"], "ok")
        self.assertEqual(p["coverage"][0]["source"], "crossref")
        self.assertEqual(p["filters"], {"year_from": 2018})

    def test_limit_truncates(self):
        items = [_hit("crossref", doi=f"10.1/{i}", year=2000 + i) for i in range(5)]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        p = search.build_payload("q", None, result, limit=3)
        self.assertEqual(p["stats"]["shown"], 3)
        self.assertEqual(len(p["results"]), 3)
        self.assertEqual(p["filters"], {})       # None → {}


class TestLookupPayload(unittest.TestCase):
    """回填补全（--lookup-doi）：命中给元数据；ISTIC / miss 标人工核对，绝不 NOT_FOUND。"""

    def test_found_returns_metadata(self):
        ev = Evidence(ref_id="single", input=Ref(id="single", doi="10.1/a"), doi_ra="Crossref",
                      hits=[SourceHit(source="crossref", metadata={"title": "T", "year": 2020},
                                      fetched_at="2026-01-01T00:00:00Z")])
        p = search.build_lookup_payload("10.1/a", ev)
        self.assertTrue(p["found"])
        self.assertEqual(p["metadata"]["title"], "T")
        self.assertIsNone(p["note"])

    def test_istic_flagged_manual_not_notfound(self):
        ev = Evidence(ref_id="single", input=Ref(id="single", doi="10.3969/x"),
                      doi_ra="ISTIC", route_note="ISTIC 注册", hits=[])
        p = search.build_lookup_payload("10.3969/x", ev)
        self.assertFalse(p["found"])
        self.assertEqual(p["doi_ra"], "ISTIC")
        self.assertIn("人工核对", p["note"])

    def test_miss_flagged_not_fabrication(self):
        ev = Evidence(ref_id="single", input=Ref(id="single", doi="10.9/z"),
                      doi_ra="Crossref", hits=[])
        p = search.build_lookup_payload("10.9/z", ev)
        self.assertFalse(p["found"])
        self.assertIn("人工核对", p["note"])


class TestRenderHtml(unittest.TestCase):
    def test_table_link_and_coverage_class(self):
        md = ("# 文献笔记表\n\n"
              "| 标题（含链接） | 覆盖方式 |\n| --- | --- |\n"
              "| [A](https://doi.org/10.1/a) | 自动检索 |\n"
              "| B（知网） | 用户回填 |\n")
        h = render_html.md_to_html(md)
        self.assertIn("<table>", h)
        self.assertIn('<a href="https://doi.org/10.1/a"', h)   # 链接可点击
        self.assertIn('class="auto"', h)                       # 自动检索色标
        self.assertIn('class="manual"', h)                     # 用户回填色标

    def test_notice_block(self):
        md = "⚠️ 覆盖提示：英文库没检索到不等于没人研究过\n"
        self.assertIn('class="notice"', render_html.md_to_html(md))

    def test_html_escaped(self):
        h = render_html.md_to_html("| 标题 |\n| --- |\n| a<script>b |\n")
        self.assertNotIn("<script>", h)                        # 转义防注入
        self.assertIn("&lt;script&gt;", h)


if __name__ == "__main__":
    unittest.main()
