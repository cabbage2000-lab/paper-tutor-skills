from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from paper_shared.datasources.cache import Cache
from paper_shared.datasources.clients import CLIENT_CLASSES
from paper_shared.datasources.clients.base import restore_inverted_abstract
from paper_shared.datasources.clients.openalex import OpenAlexClient
from paper_shared.datasources.clients.semantic_scholar import SemanticScholarClient
from paper_shared.datasources.registry import Registry
from paper_shared.datasources.transport import Throttle, Transport
from tests.datasources.fakes import FakeOpener, FakeResponse

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "api_responses"


def load_fixture(name: str):
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


def make(cls, source_id, script, tmpdir, **kw):
    cfg = Registry.load().get(source_id)
    transport = Transport(user_agent="Paper-test/0", opener=FakeOpener(script),
                          sleep=lambda s: None)
    cache = Cache(pathlib.Path(tmpdir) / f"{source_id}.db")
    throttle = Throttle(0.0, clock=lambda: 0.0, sleep=lambda s: None)
    return cls(cfg, transport, cache, throttle,
               now_iso=lambda: "2026-07-22T00:00:00Z", **kw), transport


class TestOpenAlex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_registered(self):
        self.assertIs(CLIENT_CLASSES["openalex"], OpenAlexClient)

    def test_lookup_doi_normalizes(self):
        client, transport = make(OpenAlexClient, "openalex",
                                 [FakeResponse(200, load_fixture("openalex_hit.json"))],
                                 self.tmp.name)
        hit = client.lookup_doi("10.1038/nature12373")
        self.assertEqual(hit.metadata["title"], "Nanometre-scale thermometry in a living cell")
        self.assertEqual(hit.metadata["doi"], "10.1038/nature12373")   # 去 URL 前缀
        self.assertEqual(hit.metadata["venue"], "Nature")
        url, _ = transport._opener.calls[0]
        self.assertIn("/works/doi:10.1038/nature12373", url)

    def test_no_retraction_on_normal_work(self):
        client, _ = make(OpenAlexClient, "openalex",
                         [FakeResponse(200, load_fixture("openalex_hit.json"))],
                         self.tmp.name)
        self.assertIsNone(client.lookup_doi("10.1038/nature12373").retraction)

    def test_is_retracted_extracted(self):
        """OpenAlex is_retracted → retraction，给撤稿检测加一路不依赖 Crossref 的冗余。"""
        client, _ = make(OpenAlexClient, "openalex",
                         [FakeResponse(200, load_fixture("openalex_retracted.json"))],
                         self.tmp.name)
        hit = client.lookup_doi("10.5555/retracted-example")
        self.assertIsNotNone(hit.retraction)
        self.assertEqual(hit.retraction["type"], "retraction")
        self.assertEqual(hit.retraction["source"], "openalex")
        # 布尔标记而已：无撤稿日期、无撤稿声明 DOI，不可伪造
        self.assertIsNone(hit.retraction["date_parts"])
        self.assertIsNone(hit.retraction["doi"])


class TestInvertedAbstract(unittest.TestCase):
    """OpenAlex 只给 abstract_inverted_index，摘要要按位置铺回原序。"""

    def test_restores_word_order(self):
        idx = {"the": [0, 3], "cat": [1], "sat": [2], "mat": [4]}
        self.assertEqual(restore_inverted_abstract(idx), "the cat sat the mat")

    def test_position_order_not_dict_order(self):
        # 键的插入序与位置序无关，还原必须按位置排，不能靠 dict 顺序
        self.assertEqual(restore_inverted_abstract({"world": [1], "hello": [0]}),
                         "hello world")

    def test_gap_is_skipped_not_padded(self):
        """位置有洞（源数据缺词）时跳过、不填占位符——宁可句子短一截，不编内容。"""
        self.assertEqual(restore_inverted_abstract({"a": [0], "c": [5]}), "a c")

    def test_empty_and_none(self):
        for bad in (None, {}, {"w": []}, {"w": None}):
            self.assertIsNone(restore_inverted_abstract(bad))

    def test_illegal_positions_ignored(self):
        # 负数 / 非整数 / bool 都不是位置；全非法等同没给摘要
        self.assertIsNone(restore_inverted_abstract({"a": [-1], "b": ["x"], "c": [True]}))

    def test_non_dict_input(self):
        self.assertIsNone(restore_inverted_abstract("not an index"))


class TestOpenAlexSnowball(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _work(**kw):
        w = {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/seed",
             "display_name": "Seed", "publication_year": 2020, "type": "article"}
        w.update(kw)
        return w

    @staticmethod
    def _results(*titles):
        return {"results": [{"id": f"https://openalex.org/W{i}", "display_name": t,
                             "publication_year": 2010 + i, "cited_by_count": i}
                            for i, t in enumerate(titles, start=10)]}

    def test_references_two_hops(self):
        """后向是两跳：referenced_works 只给 ID，题录要再批量取一次。"""
        client, transport = make(
            OpenAlexClient, "openalex",
            [FakeResponse(200, self._work(referenced_works=["https://openalex.org/W10",
                                                            "https://openalex.org/W11"])),
             FakeResponse(200, self._results("经典甲", "经典乙"))],
            self.tmp.name)
        hits = client.references("10.1/seed")
        self.assertEqual([h.metadata["title"] for h in hits], ["经典甲", "经典乙"])
        # 第二跳用短 ID 的 OR 过滤，不是逐条查（`|` 保持裸字符，OpenAlex 文档即此写法）
        self.assertIn("filter=openalex_id:W10|W11", transport._opener.calls[1][0])

    def test_references_batches_over_or_limit(self):
        """`filter=openalex_id:` 的 OR 上限是 50，参考文献常超过——必须分批。"""
        ids = [f"https://openalex.org/W{i}" for i in range(60)]
        client, transport = make(
            OpenAlexClient, "openalex",
            [FakeResponse(200, self._work(referenced_works=ids)),
             FakeResponse(200, self._results(*[f"t{i}" for i in range(50)])),
             FakeResponse(200, self._results(*[f"t{i}" for i in range(10)]))],
            self.tmp.name)
        hits = client.references("10.1/seed", limit=60)
        self.assertEqual(len(hits), 60)
        self.assertEqual(len(transport._opener.calls), 3)     # 1 跳 + 2 批

    def test_references_respects_limit(self):
        ids = [f"https://openalex.org/W{i}" for i in range(60)]
        client, transport = make(
            OpenAlexClient, "openalex",
            [FakeResponse(200, self._work(referenced_works=ids)),
             FakeResponse(200, self._results("只要两条", "第二条"))],
            self.tmp.name)
        client.references("10.1/seed", limit=2)
        self.assertIn("openalex_id:W0|W1&", transport._opener.calls[1][0])

    def test_references_empty_when_none_recorded(self):
        client, transport = make(OpenAlexClient, "openalex",
                                 [FakeResponse(200, self._work())], self.tmp.name)
        self.assertEqual(client.references("10.1/seed"), [])
        self.assertEqual(len(transport._opener.calls), 1)     # 没有第二跳

    def test_cited_by_uses_short_id(self):
        client, transport = make(
            OpenAlexClient, "openalex",
            [FakeResponse(200, self._work()),
             FakeResponse(200, self._results("新跟进"))],
            self.tmp.name)
        hits = client.cited_by("10.1/seed")
        self.assertEqual(hits[0].metadata["title"], "新跟进")
        self.assertIn("filter=cites:W1", transport._opener.calls[1][0])

    def test_snowball_reuses_lookup_cache_key(self):
        """第一跳与 lookup_doi 共用缓存键：先 lookup 再滚雪球不该重打第一跳。"""
        client, transport = make(
            OpenAlexClient, "openalex",
            [FakeResponse(200, self._work(referenced_works=["https://openalex.org/W10"])),
             FakeResponse(200, self._results("经典甲"))],
            self.tmp.name)
        client.lookup_doi("10.1/seed")
        client.references("10.1/seed")
        self.assertEqual(len(transport._opener.calls), 2)   # 不是 3


class TestSemanticScholar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_registered(self):
        self.assertIs(CLIENT_CLASSES["semantic_scholar"], SemanticScholarClient)

    def test_lookup_sends_api_key_header(self):
        client, transport = make(SemanticScholarClient, "semantic_scholar",
                                 [FakeResponse(200, load_fixture("s2_hit.json"))],
                                 self.tmp.name, api_key="SECRET")
        hit = client.lookup_doi("10.1038/nature12373")
        self.assertEqual(hit.metadata["year"], 2013)
        _, headers = transport._opener.calls[0]
        self.assertEqual(headers.get("X-api-key", headers.get("X-API-KEY")), "SECRET")

    def test_probe_partial_without_key(self):
        client, _ = make(SemanticScholarClient, "semantic_scholar",
                         [FakeResponse(200, load_fixture("s2_hit.json"))],
                         self.tmp.name, api_key=None)
        pr = client.probe()
        self.assertEqual(pr.status, "partial")
        self.assertIn("API key", pr.reason)

    def test_probe_ok_with_key(self):
        client, _ = make(SemanticScholarClient, "semantic_scholar",
                         [FakeResponse(200, load_fixture("s2_hit.json"))],
                         self.tmp.name, api_key="SECRET")
        self.assertEqual(client.probe().status, "ok")

    def test_requests_citation_count_and_abstract(self):
        client, transport = make(SemanticScholarClient, "semantic_scholar",
                                 [FakeResponse(200, load_fixture("s2_hit.json"))],
                                 self.tmp.name)
        client.lookup_doi("10.1038/nature12373")
        url = transport._opener.calls[0][0]
        self.assertIn("citationCount", url)
        self.assertIn("abstract", url)

    def test_cache_key_is_fields_versioned(self):
        """缓存键不含 fields，而 fields 是 URL 的一部分。扩了字段却不换键，旧缓存会照命中
        并回缺字段的 payload——用户看到「一部分条目有被引数、一部分没有」且查不出原因。"""
        client, _ = make(SemanticScholarClient, "semantic_scholar",
                         [FakeResponse(200, {"title": "T", "year": 2020,
                                             "citationCount": 5})],
                         self.tmp.name)
        client.lookup_doi("10.1038/nature12373")
        keys = []
        with client.cache._conn() as c:
            keys = [r[0] for r in c.execute("SELECT key FROM cache")]
        self.assertTrue(keys)
        # 老键（无版本段）不得命中：换了 fields 就该让老缓存自然作废
        self.assertNotIn("doi:10.1038/nature12373", keys)
        self.assertTrue(any(k.startswith("doi:10.1038/nature12373:") for k in keys))

    def test_snowball_unwraps_edge_objects(self):
        """S2 的两向响应是**边**对象，题录裹在 citedPaper / citingPaper 里，要剥一层。"""
        client, transport = make(
            SemanticScholarClient, "semantic_scholar",
            [FakeResponse(200, {"data": [
                {"citedPaper": {"title": "经典甲", "year": 1989, "citationCount": 900}},
                {"citedPaper": {"paperId": None}},       # 已知存在但未收录元数据
            ]})],
            self.tmp.name)
        hits = client.references("10.1/seed")
        self.assertEqual([h.metadata["title"] for h in hits], ["经典甲"])   # 空壳被跳过
        self.assertEqual(hits[0].metadata["cited_by_count"], 900)
        self.assertIn("/references", transport._opener.calls[0][0])

    def test_cited_by_uses_citations_endpoint(self):
        client, transport = make(
            SemanticScholarClient, "semantic_scholar",
            [FakeResponse(200, {"data": [{"citingPaper": {"title": "新跟进", "year": 2026}}]})],
            self.tmp.name)
        hits = client.cited_by("10.1/seed")
        self.assertEqual(hits[0].metadata["title"], "新跟进")
        self.assertIn("/citations", transport._opener.calls[0][0])

    def test_snowball_limit_capped_at_api_max(self):
        # S2 的 limit 上限 1000，超了它自己报 400——夹住而不是把错误甩给用户
        client, transport = make(SemanticScholarClient, "semantic_scholar",
                                 [FakeResponse(200, {"data": []})], self.tmp.name)
        client.references("10.1/seed", limit=99999)
        self.assertIn("limit=1000", transport._opener.calls[0][0])


if __name__ == "__main__":
    unittest.main()
