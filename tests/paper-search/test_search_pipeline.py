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


def _hit(source, doi=None, title="T", year=2020, typ="journal-article", venue="V",
         from_cache=False, date=None):
    return SourceHit(source=source,
                     metadata={"title": title, "doi": doi, "year": year, "venue": venue,
                               "type": typ, "authors": ["X"], "date": date},
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

    def test_truncation_emits_warning(self):
        """截断必须自报。判据一直在 stats 里，但宿主不会主动比 after_dedup 与 shown——
        实况是示例的 --limit 30 被照抄，74 条只呈现 30 条、整两年文献静默消失。"""
        items = [_hit("crossref", doi=f"10.1/{i}", year=2000 + i) for i in range(5)]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        w = search.build_payload("q", None, result, limit=3)["warnings"]
        self.assertEqual(len(w), 1)
        self.assertIn("5", w[0])            # 去重后总数，告诉宿主该把 --limit 调到多少
        self.assertIn("--limit", w[0])

    def test_no_warning_when_nothing_truncated(self):
        items = [_hit("crossref", doi=f"10.1/{i}", year=2000 + i) for i in range(3)]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        self.assertEqual(search.build_payload("q", None, result, limit=3)["warnings"], [])

    def test_limit_zero_means_no_truncation(self):
        items = [_hit("crossref", doi=f"10.1/{i}", year=2000 + i) for i in range(5)]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        p = search.build_payload("q", None, result, limit=0)
        self.assertEqual(p["stats"]["shown"], 5)
        self.assertEqual(p["stats"]["after_dedup"], 5)
        self.assertEqual(p["warnings"], [])       # 没截断就没这条 warning
        self.assertEqual([r["rank"] for r in p["results"]], [1, 2, 3, 4, 5])

    def test_truncation_warning_does_not_mutate_caller_warnings(self):
        """传入的 warnings 是调用方的 list，截断声明不得就地追加进去。"""
        items = [_hit("crossref", doi=f"10.1/{i}", year=2000 + i) for i in range(5)]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        caller = ["原有声明"]
        p = search.build_payload("q", None, result, limit=2, warnings=caller)
        self.assertEqual(caller, ["原有声明"])
        self.assertEqual(len(p["warnings"]), 2)
        self.assertEqual(p["warnings"][0], "原有声明")   # 原有的排在前，不被顶掉

    def test_result_carries_day_level_date(self):
        """输出契约必须带 date：paper-daily 靠它判时间窗。给不出的源为 None，不用 year 凑。"""
        items = [_hit("arxiv", doi="10.48550/arxiv.2607.00001", date="2026-07-29"),
                 _hit("crossref", doi="10.1/b")]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        p = search.build_payload("q", None, result)
        by_doi = {r["doi"]: r for r in p["results"]}
        self.assertEqual(by_doi["10.48550/arxiv.2607.00001"]["date"], "2026-07-29")
        self.assertIsNone(by_doi["10.1/b"]["date"])

    def test_warnings_default_empty(self):
        result = SearchResult(items=[], coverage=[], network_status="ok")
        self.assertEqual(search.build_payload("q", None, result)["warnings"], [])


class TestDateWindow(unittest.TestCase):
    """「最近 N 天」的换算与入参校验。宿主 agent 自己算日期易错，这一步收进脚本。"""

    def test_days_one_is_today(self):
        import datetime
        today = datetime.date(2026, 7, 29)
        self.assertEqual(search.window_from_days(1, today=today),
                         ("2026-07-29", "2026-07-29"))

    def test_days_seven_is_closed_interval_including_today(self):
        import datetime
        today = datetime.date(2026, 7, 29)
        self.assertEqual(search.window_from_days(7, today=today),
                         ("2026-07-23", "2026-07-29"))

    def test_days_crosses_month_boundary(self):
        import datetime
        today = datetime.date(2026, 3, 2)
        self.assertEqual(search.window_from_days(5, today=today),
                         ("2026-02-26", "2026-03-02"))

    def test_days_below_one_rejected(self):
        with self.assertRaises(ValueError):
            search.window_from_days(0)

    def test_iso_date_validation(self):
        self.assertTrue(search._valid_iso_date("2026-07-29"))
        self.assertFalse(search._valid_iso_date("2026/07/29"))
        self.assertFalse(search._valid_iso_date("20260729"))
        self.assertFalse(search._valid_iso_date("2026-13-01"))    # 非法月份

    def test_warning_when_window_meets_dateless_sources(self):
        """给不提供日期的源加窗口会 0 命中——提前说清是「源不给日期」而非「当期无新发」。"""
        w = search.date_window_warnings(["crossref", "arxiv"], "2026-07-29", "2026-07-29")
        self.assertEqual(len(w), 1)
        self.assertIn("crossref", w[0])
        self.assertNotIn("arxiv 在本次窗口", w[0])

    def test_no_warning_for_arxiv_only(self):
        self.assertEqual(search.date_window_warnings(["arxiv"], "2026-07-29", "2026-07-29"), [])

    def test_no_warning_without_window(self):
        self.assertEqual(search.date_window_warnings(["crossref"], None, None), [])

    def test_default_sources_warned_generically(self):
        w = search.date_window_warnings(None, "2026-07-29", None)
        self.assertEqual(len(w), 1)
        self.assertIn("默认核心源", w[0])

    def test_many_terms_warned_under_window(self):
        """窗口下走逐词 AND，词太多会 0 命中——实测 7 词 0 条、5 词 10 条。
        不提醒的话，宿主会把「查询太严」读成「当期无新发」。"""
        w = search.date_window_warnings(["arxiv"], "2026-07-20", "2026-07-29",
                                        "large language model feedback programming "
                                        "assignments students")
        self.assertEqual(len(w), 1)
        self.assertIn("7 个词", w[0])

    def test_few_terms_not_warned(self):
        self.assertEqual(
            search.date_window_warnings(["arxiv"], "2026-07-20", "2026-07-29",
                                        "llm feedback programming"), [])

    def test_term_warning_only_under_window(self):
        """无窗口时逐词 AND 不生效（走松散匹配），不该提醒。"""
        self.assertEqual(
            search.date_window_warnings(["arxiv"], None, None,
                                        "a b c d e f g h"), [])


class TestCliDateArgs(unittest.TestCase):
    """CLI 层的互斥与非法值：宁可退出码 2 报错，也不静默用一个错窗口去检索。"""

    def _run(self, argv):
        return search.main(argv)

    def test_days_and_explicit_dates_are_mutually_exclusive(self):
        self.assertEqual(self._run(["--query", "q", "--days", "3",
                                    "--date-from", "2026-07-01"]), 2)

    def test_bad_date_format_rejected(self):
        self.assertEqual(self._run(["--query", "q", "--date-from", "2026/07/01"]), 2)

    def test_reversed_window_rejected(self):
        self.assertEqual(self._run(["--query", "q", "--date-from", "2026-07-29",
                                    "--date-to", "2026-07-01"]), 2)

    def test_days_zero_rejected(self):
        self.assertEqual(self._run(["--query", "q", "--days", "0"]), 2)

    def test_window_with_no_usable_terms_rejected(self):
        """带窗口但切不出检索词：报错退出，不能只留日期条件去查
        （那会把窗口内全站新发当成用户主题的新发）。"""
        self.assertEqual(self._run(["--query", '()"', "--days", "1"]), 2)

    def test_negative_limit_rejected(self):
        """0 = 不截断是明确语义，负数只可能是手滑。"""
        self.assertEqual(self._run(["--query", "q", "--limit", "-1"]), 2)


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

    def test_not_registered_note_differs_from_plain_miss(self):
        """前缀未注册与「各源未命中」证据强度不同，note 不能共用一句。"""
        ev = Evidence(ref_id="single", input=Ref(id="single", doi="10.9999/fake"),
                      doi_ra="not_registered",
                      route_note="DOI 前缀未在任一注册机构注册——DOI 不存在的强信号", hits=[])
        p = search.build_lookup_payload("10.9999/fake", ev)
        self.assertFalse(p["found"])
        self.assertIn("人工核对", p["note"])          # 仍不判 NOT_FOUND
        self.assertIn("未在任一注册机构注册", p["note"])
        miss = search.build_lookup_payload("10.9/z", Evidence(
            ref_id="s", input=Ref(id="s", doi="10.9/z"), doi_ra="Crossref", hits=[]))
        self.assertNotEqual(p["note"], miss["note"])


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
