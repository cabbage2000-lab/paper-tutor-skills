"""缓存命中的 from_cache 端到端传播集成测试。

传播链：base._cached_json 命中缓存时置 _last_from_cache=True → _hit() 读取该标记
→ SourceHit.from_cache。此前 test_cache 只测 Cache 键值层、test_facade 只走首次请求，
test_crossref.test_lookup_uses_cache_second_call 只断言「第二次不再发请求」而不看
from_cache 标记——该标记（供缓存命中率统计）的 miss→False / hit→True 端到端传播
无集成测试覆盖。本文件补这一层。
"""
from __future__ import annotations

import pathlib
import tempfile
import unittest

from paper_shared.datasources.cache import Cache
from paper_shared.datasources.clients.crossref import CrossrefClient
from paper_shared.datasources.registry import Registry
from paper_shared.datasources.transport import Throttle, Transport
from tests.datasources.fakes import FakeOpener, FakeResponse

_HIT = {"status": "ok",
        "message": {"DOI": "10.1038/nature12373",
                    "title": ["Nanometre-scale thermometry"],
                    "author": [], "issued": {"date-parts": [[2013]]},
                    "container-title": ["Nature"], "type": "journal-article"}}


def _client(script, tmpdir, cache=None, fresh=False):
    """构造走 FakeOpener 的 crossref client（离线、no-op 退避）。
    cache 可外部传入以在多个 client 间共享同一持久化缓存。"""
    cfg = Registry.load().get("crossref")
    transport = Transport(user_agent="Paper-test/0", opener=FakeOpener(script),
                          sleep=lambda s: None)
    cache = cache or Cache(pathlib.Path(tmpdir) / "t.db")
    throttle = Throttle(0.0, clock=lambda: 0.0, sleep=lambda s: None)
    return CrossrefClient(cfg, transport, cache, throttle, fresh=fresh,
                          now_iso=lambda: "2026-07-22T00:00:00Z"), transport


class TestFromCachePropagation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_miss_then_hit_sets_from_cache(self):
        # 单请求脚本：第二次必须走缓存（脚本耗尽，若再发请求 FakeOpener 会 IndexError）
        client, transport = _client([FakeResponse(200, _HIT)], self.tmp.name)
        first = client.lookup_doi("10.1038/nature12373")
        second = client.lookup_doi("10.1038/nature12373")
        self.assertFalse(first.from_cache, "首次为网络命中，from_cache 应为 False")
        self.assertTrue(second.from_cache, "第二次为缓存命中，from_cache 应为 True")
        self.assertEqual(len(transport._opener.calls), 1, "第二次不应再发请求")

    def test_fresh_bypass_is_never_from_cache(self):
        # fresh=True 跳过缓存读，即使库里已有值也走网络 → from_cache 恒 False
        client, _ = _client([FakeResponse(200, _HIT), FakeResponse(200, _HIT)],
                            self.tmp.name, fresh=True)
        first = client.lookup_doi("10.1038/nature12373")
        second = client.lookup_doi("10.1038/nature12373")
        self.assertFalse(first.from_cache)
        self.assertFalse(second.from_cache, "fresh 模式绕过缓存读，命中也应为 False")

    def test_from_cache_survives_new_client_same_cache(self):
        # 端到端：换一个新 client 实例、共享同一持久化 Cache（模拟跨会话/跨批次），
        # 命中时 from_cache 仍为 True——传播来自持久化缓存，不依赖实例内存态。
        cache = Cache(pathlib.Path(self.tmp.name) / "shared.db")
        c1, _ = _client([FakeResponse(200, _HIT)], self.tmp.name, cache=cache)
        c1.lookup_doi("10.1038/nature12373")               # 写入共享缓存（发 1 请求）
        c2, t2 = _client([], self.tmp.name, cache=cache)   # 空脚本：只能靠缓存命中
        hit = c2.lookup_doi("10.1038/nature12373")
        self.assertTrue(hit.from_cache)
        self.assertEqual(len(t2._opener.calls), 0, "命中共享缓存的新 client 不应发请求")


if __name__ == "__main__":
    unittest.main()
