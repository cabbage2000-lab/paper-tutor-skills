"""paper-search 依赖的 _shared 增强：filters 落地 + 门面 search 韧性。

覆盖 paper-search spec §8.3（filters 分层）与 §8.5（门面韧性）。回放离线，不碰真实网络。
"""
from __future__ import annotations

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from paper_shared import datasources
from paper_shared.datasources.cache import Cache
from paper_shared.datasources.clients.base import SourceClient
from paper_shared.datasources.models import SourceHit
from paper_shared.datasources.registry import Registry
from paper_shared.datasources.transport import Transport
from tests.datasources.fakes import FakeOpener, FakeResponse, http_error


def _hit(year=None, typ=None, doi=None, title="T", source="x", date=None):
    return SourceHit(source=source,
                     metadata={"title": title, "year": year, "type": typ, "doi": doi,
                               "date": date},
                     fetched_at="2026-01-01T00:00:00Z")


class TestSearchCacheKey(unittest.TestCase):
    """filters 空时缓存键与既有逐字节一致（回放不破）；非空时带稳定指纹。"""

    def test_none_unchanged(self):
        self.assertEqual(SourceClient._search_cache_key("Test Query", 20, None),
                         "search:test query:20")

    def test_empty_dict_unchanged(self):
        self.assertEqual(SourceClient._search_cache_key("Test", 20, {}), "search:test:20")

    def test_with_filters_fingerprint(self):
        key = SourceClient._search_cache_key(
            "Test", 20, {"year_from": 2018, "year_to": 2026, "type": "journal-article"})
        self.assertEqual(key, "search:test:20:f=2018-2026-journal-article")

    def test_no_date_segment_when_window_absent(self):
        """无日期窗口时不追加 `:d=` 段——否则既有缓存键整体位移、已缓存检索全失效。"""
        self.assertEqual(SourceClient._search_cache_key("Test", 20, {"year_from": 2018}),
                         "search:test:20:f=2018-None-None")

    def test_date_window_in_fingerprint(self):
        key = SourceClient._search_cache_key(
            "Test", 20, {"date_from": "2026-07-28", "date_to": "2026-07-29"})
        self.assertEqual(key, "search:test:20:f=None-None-None:d=2026-07-28-2026-07-29")

    def test_date_window_differs_from_no_window(self):
        """带窗口 / 不带窗口两次检索不得共用缓存键（否则窗口结果串味）。"""
        base = SourceClient._search_cache_key("Q", 20, {"year_from": 2026})
        windowed = SourceClient._search_cache_key("Q", 20, {"year_from": 2026,
                                                            "date_from": "2026-07-29"})
        self.assertNotEqual(base, windowed)


class TestPostfilter(unittest.TestCase):
    def test_none_is_noop(self):
        hits = [_hit(year=2000), _hit(year=2020)]
        self.assertEqual(SourceClient._postfilter(hits, None), hits)

    def test_year_range(self):
        hits = [_hit(year=2015), _hit(year=2020), _hit(year=2025)]
        out = SourceClient._postfilter(hits, {"year_from": 2018, "year_to": 2024})
        self.assertEqual([h.metadata["year"] for h in out], [2020])

    def test_year_missing_excluded_when_bound_set(self):
        self.assertEqual(SourceClient._postfilter([_hit(year=None)], {"year_from": 2018}), [])

    def test_type_filters_out_mismatch(self):
        hits = [_hit(typ="preprint"), _hit(typ="journal-article")]
        out = SourceClient._postfilter(hits, {"type": "journal-article"})
        self.assertEqual([h.metadata["type"] for h in out], ["journal-article"])

    def test_type_unknown_not_dropped(self):
        # 归一不了的 type 保留（宁松勿误杀）
        self.assertEqual(len(SourceClient._postfilter([_hit(typ="某中文类型")],
                                                      {"type": "journal-article"})), 1)

    def test_date_range_closed_interval(self):
        hits = [_hit(date="2026-07-27"), _hit(date="2026-07-28"), _hit(date="2026-07-29"),
                _hit(date="2026-07-30")]
        out = SourceClient._postfilter(hits, {"date_from": "2026-07-28",
                                              "date_to": "2026-07-29"})
        self.assertEqual([h.metadata["date"] for h in out], ["2026-07-28", "2026-07-29"])

    def test_date_single_day_window(self):
        """--days 1 的落地形态：起止同一天，只留当天。"""
        hits = [_hit(date="2026-07-28"), _hit(date="2026-07-29")]
        out = SourceClient._postfilter(hits, {"date_from": "2026-07-29",
                                              "date_to": "2026-07-29"})
        self.assertEqual([h.metadata["date"] for h in out], ["2026-07-29"])

    def test_date_missing_excluded_when_window_set(self):
        """日期缺失在设了窗口时排除（同 year、不同于 type）：否则窗口外文献会被当成新发。"""
        self.assertEqual(SourceClient._postfilter([_hit(date=None)],
                                                  {"date_from": "2026-07-29"}), [])

    def test_date_accepts_full_timestamp(self):
        """metadata.date 万一带了完整时间戳，按前 10 位比较、不误杀。"""
        out = SourceClient._postfilter([_hit(date="2026-07-29T17:36:22Z")],
                                       {"date_from": "2026-07-29", "date_to": "2026-07-29"})
        self.assertEqual(len(out), 1)

    def test_date_window_and_year_compose(self):
        hits = [_hit(year=2026, date="2026-07-29"), _hit(year=2025, date="2025-07-29")]
        out = SourceClient._postfilter(hits, {"year_from": 2026, "date_from": "2026-07-01"})
        self.assertEqual([h.metadata["year"] for h in out], [2026])


class _Facade(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.reg = Registry.load()

    def tearDown(self):
        self.tmp.cleanup()

    def _search(self, opener, **kw):
        transport = Transport(user_agent="t", opener=opener, sleep=lambda s: None)
        cache = Cache(pathlib.Path(self.tmp.name) / "c.db")
        return datasources.search(_registry=self.reg, _transport=transport, _cache=cache, **kw)


class TestClientFilterURL(_Facade):
    """filters 非空时各源方言映射进 URL；filters 空时无 filter 段。"""

    def test_crossref_none_no_filter_param(self):
        op = FakeOpener([FakeResponse(200, {"message": {"items": []}})])
        self._search(op, query="test", sources=["crossref"])
        url = op.calls[0][0]
        self.assertIn("query=test", url)
        self.assertNotIn("filter", url)

    def test_crossref_native_year_type(self):
        op = FakeOpener([FakeResponse(200, {"message": {"items": []}})])
        self._search(op, query="test", sources=["crossref"],
                     filters={"year_from": 2018, "year_to": 2026, "type": "journal-article"})
        url = op.calls[0][0]
        self.assertIn("from-pub-date:2018-01-01", url)
        self.assertIn("until-pub-date:2026-12-31", url)
        self.assertIn("type:journal-article", url)

    def test_openalex_native_year_type(self):
        op = FakeOpener([FakeResponse(200, {"results": []})])
        self._search(op, query="test", sources=["openalex"],
                     filters={"year_from": 2018, "type": "journal-article"})
        url = op.calls[0][0]
        self.assertIn("from_publication_date:2018-01-01", url)
        self.assertIn("type:article", url)

    def test_s2_native_year_types(self):
        op = FakeOpener([FakeResponse(200, {"data": []})])
        self._search(op, query="test", sources=["semantic_scholar"],
                     filters={"year_from": 2018, "year_to": 2026, "type": "journal-article"})
        url = op.calls[0][0]
        self.assertIn("year=2018-2026", url)
        self.assertIn("publicationTypes=JournalArticle", url)


def _routing(crossref_ok=True, openalex_ok=True):
    """按 URL 路由的 opener：crossref / openalex 各自可切成 500 故障。"""
    def op(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "crossref" in url:
            if crossref_ok:
                return FakeResponse(200, {"message": {"items": [
                    {"DOI": "10.1/a", "title": ["A"], "issued": {"date-parts": [[2020]]},
                     "type": "journal-article"}]}})
            raise http_error(url, 500)
        if "openalex" in url:
            if openalex_ok:
                return FakeResponse(200, {"results": [
                    {"display_name": "B", "publication_year": 2021,
                     "doi": "https://doi.org/10.2/b", "type": "article"}]})
            raise http_error(url, 500)
        return FakeResponse(200, {})
    return op


class TestFacadeResilience(_Facade):
    def test_single_source_error_does_not_crash(self):
        r = self._search(_routing(crossref_ok=False, openalex_ok=True),
                         query="test", sources=["crossref", "openalex"])
        cov = {c["source"]: c for c in r.coverage}
        self.assertEqual(cov["crossref"]["coverage"], "未覆盖")
        self.assertEqual(cov["crossref"]["outcome"], "error")
        self.assertEqual(cov["crossref"]["error"], "SERVER_ERROR")
        self.assertEqual(cov["openalex"]["coverage"], "自动检索")
        self.assertEqual(r.network_status, "degraded")
        self.assertEqual(len(r.items), 1)   # openalex 结果仍返回，未被单源故障拖垮

    def test_all_core_fail_offline(self):
        r = self._search(_routing(crossref_ok=False, openalex_ok=False),
                         query="test", sources=["crossref", "openalex"])
        self.assertEqual(r.network_status, "offline")
        self.assertEqual(r.items, [])

    def test_coverage_fields_present_and_guided(self):
        r = self._search(_routing(), query="test", sources=["crossref", "openalex"])
        for c in r.coverage:
            self.assertIn("hit_count", c)
            self.assertIn("outcome", c)
            self.assertIn("applied_filters", c)
        guided = [c for c in r.coverage if c["coverage"] == "需用户回填"]
        self.assertTrue(guided)                                  # cnki / wanfang 恒声明
        self.assertTrue(all(c["outcome"] == "n/a" for c in guided))

    def test_empty_vs_error_distinction(self):
        # 查过、0 命中 → outcome empty、coverage 自动检索（≠ 未覆盖）
        r = self._search(FakeOpener([FakeResponse(200, {"results": []})]),
                         query="test", sources=["openalex"])
        cov = {c["source"]: c for c in r.coverage}
        self.assertEqual(cov["openalex"]["outcome"], "empty")
        self.assertEqual(cov["openalex"]["coverage"], "自动检索")


class TestS2Degraded(_Facade):
    def test_no_key_with_hits_marks_degraded(self):
        with mock.patch.dict(os.environ, {}, clear=True):   # 确保无 SEMANTIC_SCHOLAR_API_KEY
            r = self._search(
                FakeOpener([FakeResponse(200, {"data": [
                    {"title": "X", "year": 2020, "externalIds": {}, "authors": []}]})]),
                query="test", sources=["semantic_scholar"])
        cov = {c["source"]: c for c in r.coverage}
        self.assertEqual(cov["semantic_scholar"]["outcome"], "degraded")
        self.assertEqual(r.network_status, "degraded")


if __name__ == "__main__":
    unittest.main()
