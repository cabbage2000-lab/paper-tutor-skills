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
