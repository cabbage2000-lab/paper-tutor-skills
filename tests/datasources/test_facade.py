from __future__ import annotations

import pathlib
import tempfile
import unittest

from paper_shared import datasources
from paper_shared.datasources.cache import Cache
from paper_shared.datasources.models import Evidence, Ref, SourceHit
from paper_shared.datasources.registry import Registry
from paper_shared.datasources.transport import Transport
from tests.datasources.fakes import FakeOpener, FakeResponse, http_error

_CROSSREF_MSG = {"status": "ok",
                 "message": {"DOI": "10.1038/nature12373",
                             "title": ["Nanometre-scale thermometry"],
                             "author": [], "issued": {"date-parts": [[2013]]},
                             "container-title": ["Nature"],
                             "type": "journal-article"}}


class _RoutingOpener:
    """按 URL 路由返回不同响应的测试 opener——lookup 完整流程含 RA 判别 +
    多源查询，需按 URL 区分响应而非 FIFO 消费。"""

    def __init__(self):
        self.calls = []

    def __call__(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        self.calls.append(url)
        if "doi.org/ra/" in url:
            return FakeResponse(200, [{"DOI": "10.1038", "RA": "Crossref"}])
        if "api.crossref.org" in url:
            return FakeResponse(200, _CROSSREF_MSG)
        if "api.openalex.org" in url:
            raise http_error(url, 404)
        return FakeResponse(200, {})


class TestFacadeAPI(unittest.TestCase):
    def test_lookup_no_doi_no_title_raises(self):
        with self.assertRaises(ValueError):
            datasources.lookup()

    def test_lookup_returns_evidence(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            reg = Registry.load()
            transport = Transport(user_agent="t", opener=_RoutingOpener(),
                                  sleep=lambda s: None)
            cache = Cache(pathlib.Path(tmp.name) / "c.db")
            ev = datasources.lookup(doi="10.1038/nature12373", _registry=reg,
                                    _transport=transport, _cache=cache)
            self.assertIsInstance(ev, Evidence)
            self.assertEqual(ev.doi_ra, "Crossref")
            self.assertEqual(len(ev.hits), 1)
        finally:
            tmp.cleanup()

    def test_search_coverage_includes_guided(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            reg = Registry.load()
            transport = Transport(user_agent="t",
                                  opener=FakeOpener([FakeResponse(200, {"results": []})]),
                                  sleep=lambda s: None)
            cache = Cache(pathlib.Path(tmp.name) / "c.db")
            result = datasources.search("test query", sources=["openalex"],
                                        _registry=reg, _transport=transport, _cache=cache)
            source_ids_in_coverage = {c["source"] for c in result.coverage}
            self.assertIn("openalex", source_ids_in_coverage)
            # guided 源出现在覆盖声明中
            self.assertIn("cnki", source_ids_in_coverage)
        finally:
            tmp.cleanup()

    # ---- related()：滚雪球门面 ----

    def _related(self, opener, **kw):
        tmp = tempfile.TemporaryDirectory()
        try:
            transport = Transport(user_agent="t", opener=opener, sleep=lambda s: None)
            return datasources.related(
                "10.1/seed", _registry=Registry.load(), _transport=transport,
                _cache=Cache(pathlib.Path(tmp.name) / "c.db"), **kw)
        finally:
            tmp.cleanup()

    def test_related_rejects_unknown_direction(self):
        with self.assertRaises(ValueError):
            datasources.related("10.1/seed", direction="sideways")

    def test_related_marks_direction_on_hits(self):
        """方向要落到 metadata：「它引的」与「引它的」对用户是两件事，去重后仍需分辨。"""
        result = self._related(
            FakeOpener([FakeResponse(200, {"data": [{"citedPaper": {"title": "经典"}}]})]),
            direction="backward", sources=["semantic_scholar"])
        self.assertEqual([h.metadata["snowball_direction"] for h in result.items],
                         ["references"])

    def test_related_one_direction_failing_keeps_the_other(self):
        """逐源逐向容错：后向挂了不该把前向也判成未覆盖。"""
        class _Opener:
            def __init__(self):
                self.calls = []

            def __call__(self, req, timeout=None):
                url = req.full_url
                self.calls.append(url)
                if "/references" in url:
                    raise http_error(url, 500)
                return FakeResponse(200, {"data": [{"citingPaper": {"title": "新跟进"}}]})

        result = self._related(_Opener(), direction="both", sources=["semantic_scholar"])
        rows = {c["direction"]: c for c in result.coverage if c["source"] == "semantic_scholar"}
        self.assertEqual(len(rows), 2)                       # 每向各一行，不合并
        back = [c for c in rows.values() if "后向" in c["direction"]][0]
        fwd = [c for c in rows.values() if "前向" in c["direction"]][0]
        self.assertEqual(back["outcome"], "error")
        self.assertEqual(fwd["outcome"], "ok")
        self.assertEqual(result.network_status, "degraded")   # 部分失败
        self.assertEqual(len(result.items), 1)               # 前向结果照常返回

    def test_related_coverage_includes_guided_placeholder(self):
        """中文库不支持滚雪球，但覆盖声明不能因为换了模式就少一块。"""
        result = self._related(FakeOpener([FakeResponse(200, {"data": []})]),
                               direction="forward", sources=["semantic_scholar"])
        cnki = [c for c in result.coverage if c["source"] == "cnki"]
        self.assertEqual(len(cnki), 1)
        self.assertIn("滚雪球不适用", cnki[0]["coverage"])

    def test_related_default_sources_have_the_capability(self):
        """不传 sources 时只选声明了对应能力的核心源——不能把 crossref/arxiv 也算进去。"""
        result = self._related(
            FakeOpener([FakeResponse(200, {"results": []}),      # openalex 第一跳
                        FakeResponse(200, {"data": []})]),       # s2
            direction="forward")
        api_rows = {c["source"] for c in result.coverage if c["direction"] != "—"}
        self.assertEqual(api_rows, {"openalex", "semantic_scholar"})

    def test_related_all_failing_is_offline(self):
        result = self._related(
            FakeOpener([http_error("u", 500)] * 5),
            direction="backward", sources=["semantic_scholar"])
        self.assertEqual(result.network_status, "offline")
        self.assertEqual(result.items, [])

    def test_probe_all_returns_list(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            reg = Registry.load()
            transport = Transport(user_agent="t",
                                  opener=FakeOpener([FakeResponse(200, {})] * 10),
                                  sleep=lambda s: None)
            cache = Cache(pathlib.Path(tmp.name) / "c.db")
            results = datasources.probe_all(_registry=reg, _transport=transport, _cache=cache)
            self.assertGreater(len(results), 0)
            self.assertTrue(all(r.source for r in results))
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
