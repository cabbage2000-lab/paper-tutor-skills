"""batch 层缓存命中率统计的端到端集成测试。

补 test_cache_integration 未覆盖的后半段：SourceHit.from_cache 经 BatchEngine._assemble
聚合成 BatchResult.stats.cache_hits / cache_hit_rate。走真实 facade fetch_batch（engine.run
的并发 _dispatch + _assemble），同一 Ref 连续两次共享持久化缓存：首次全走网络
（cache_hits==0），二次全缓存命中（cache_hits>0、cache_hit_rate 升到 1.0）。另断言
SourceHit.raw 不含 _from_cache 残留键（历史 bug：曾把内部标志塞进 raw dict）。
"""
from __future__ import annotations

import pathlib
import tempfile
import unittest

from paper_shared import datasources
from paper_shared.datasources.cache import Cache
from paper_shared.datasources.models import Ref
from paper_shared.datasources.registry import Registry
from paper_shared.datasources.transport import Transport
from tests.datasources.fakes import FakeResponse

_CROSSREF = {"status": "ok",
             "message": {"DOI": "10.1038/nature12373",
                         "title": ["Nanometre-scale thermometry in a living cell"],
                         "author": [], "issued": {"date-parts": [[2013]]},
                         "container-title": ["Nature"], "type": "journal-article"}}
_OPENALEX = {"id": "https://openalex.org/W2755950973",
             "doi": "https://doi.org/10.1038/nature12373",
             "display_name": "Nanometre-scale thermometry in a living cell",
             "publication_year": 2013, "type": "article",
             "authorships": [], "primary_location": {}}


class _RoutingOpener:
    """按 URL 路由、无状态的 opener（batch 多 worker 并发下天然线程安全）。
    /ra/ 判 Crossref → 源为 crossref + openalex，两源各给一个可命中的响应。"""

    def __call__(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "doi.org/ra/" in url:
            return FakeResponse(200, [{"DOI": "10.1038", "RA": "Crossref"}])
        if "api.crossref.org" in url:
            return FakeResponse(200, _CROSSREF)
        if "api.openalex.org" in url:
            return FakeResponse(200, _OPENALEX)
        return FakeResponse(200, {})


class TestBatchCacheStats(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Cache(pathlib.Path(self.tmp.name) / "c.db")

    def _fetch(self):
        # 每次新建 transport（新 opener），复用同一持久化 cache——命中来自缓存文件、
        # 而非同一实例内存态，贴近 verify 跨批次续跑的真实形态。
        transport = Transport(user_agent="Paper-test/0", opener=_RoutingOpener(),
                              sleep=lambda s: None)
        return datasources.fetch_batch(
            [Ref(id="r1", doi="10.1038/nature12373")],
            _registry=Registry.load(), _transport=transport, _cache=self.cache)

    def test_cache_hits_zero_first_then_full_second(self):
        first = self._fetch()
        self.assertEqual(first.stats["cache_hits"], 0, "首次全走网络，cache_hits 应为 0")
        self.assertEqual(first.stats["cache_hit_rate"], 0.0)

        second = self._fetch()   # 同一 cache：doi_ra 与两源 lookup 全部命中缓存
        self.assertEqual(second.stats["cache_hits"], 2, "二次两源都命中，cache_hits 应为 2")
        self.assertEqual(second.stats["cache_hit_rate"], 1.0)

    def test_source_hits_carry_from_cache_flag(self):
        self._fetch()
        ev = self._fetch().evidences["r1"]
        self.assertTrue(ev.hits, "应有命中")
        self.assertTrue(all(h.from_cache for h in ev.hits),
                        "第二次所有命中都应标 from_cache=True")

    def test_raw_has_no_from_cache_residue(self):
        ev = self._fetch().evidences["r1"]
        self.assertTrue(ev.hits)
        for hit in ev.hits:
            self.assertNotIn("_from_cache", hit.raw, "raw 不应残留内部 _from_cache 标志")


if __name__ == "__main__":
    unittest.main()
