from __future__ import annotations

import pathlib
import tempfile
import unittest

from paper_shared.datasources.cache import Cache
from paper_shared.datasources.clients import CLIENT_CLASSES
from paper_shared.datasources.clients.arxiv import ArxivClient
from paper_shared.datasources.registry import Registry
from paper_shared.datasources.transport import Throttle, Transport
from tests.datasources.fakes import FakeOpener, FakeResponse

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "api_responses"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def make(script, tmpdir):
    cfg = Registry.load().get("arxiv")
    transport = Transport(user_agent="Paper-test/0", opener=FakeOpener(script),
                          sleep=lambda s: None)
    cache = Cache(pathlib.Path(tmpdir) / "arxiv.db")
    throttle = Throttle(0.0, clock=lambda: 0.0, sleep=lambda s: None)
    return ArxivClient(cfg, transport, cache, throttle,
                       now_iso=lambda: "2026-07-22T00:00:00Z"), transport


class TestArxiv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_registered(self):
        self.assertIs(CLIENT_CLASSES["arxiv"], ArxivClient)

    def test_doi_to_arxiv_id(self):
        client, _ = make([], self.tmp.name)
        self.assertEqual(client.doi_to_arxiv_id("10.48550/arXiv.1706.03762"), "1706.03762")
        self.assertEqual(client.doi_to_arxiv_id("10.48550/arXiv.2605.07723"), "2605.07723")
        self.assertIsNone(client.doi_to_arxiv_id("10.1038/nature12373"))

    def test_lookup_arxiv_id_parses_atom(self):
        client, _ = make([FakeResponse(200, read_fixture("arxiv_atom.xml"),
                                       headers={"Content-Type": "application/atom+xml"})],
                         self.tmp.name)
        hit = client.lookup_arxiv_id("1706.03762")
        self.assertEqual(hit.source, "arxiv")
        self.assertEqual(hit.metadata["title"], "Attention Is All You Need")
        self.assertEqual(hit.metadata["authors"], ["Ashish Vaswani", "Noam Shazeer"])
        self.assertEqual(hit.metadata["year"], 2017)
        self.assertEqual(hit.metadata["doi"], "10.48550/arxiv.1706.03762")
        self.assertEqual(hit.metadata["type"], "preprint")

    def test_lookup_doi_converts_to_arxiv_id(self):
        client, transport = make([FakeResponse(200, read_fixture("arxiv_atom.xml"),
                                               headers={"Content-Type": "application/atom+xml"})],
                                 self.tmp.name)
        hit = client.lookup_doi("10.48550/arXiv.1706.03762")
        self.assertIsNotNone(hit)
        url, _ = transport._opener.calls[0]
        self.assertIn("id_list=1706.03762", url)

    def test_lookup_doi_non_datacite_returns_none(self):
        client, transport = make([], self.tmp.name)
        self.assertIsNone(client.lookup_doi("10.1038/nature12373"))
        self.assertEqual(len(transport._opener.calls), 0)

    def test_search_returns_multiple(self):
        client, _ = make([FakeResponse(200, read_fixture("arxiv_search_atom.xml"),
                                       headers={"Content-Type": "application/atom+xml"})],
                         self.tmp.name)
        hits = client.search("attention transformer")
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0].metadata["title"], "Attention Is All You Need")
        self.assertEqual(hits[1].metadata["title"],
                         "BERT: Pre-training of Deep Bidirectional Transformers")

    def test_metadata_carries_day_level_date(self):
        """published 的日级日期必须带进 metadata——paper-daily 的时间窗靠它判定。
        此前 published 只用来算 year、归一化时被丢掉，宿主拿不到日级粒度。"""
        client, _ = make([FakeResponse(200, read_fixture("arxiv_atom.xml"),
                                       headers={"Content-Type": "application/atom+xml"})],
                         self.tmp.name)
        hit = client.lookup_arxiv_id("1706.03762")
        self.assertEqual(hit.metadata["date"], "2017-06-12")
        self.assertEqual(hit.metadata["year"], 2017)          # 与 year 并存、不互相取代

    def test_date_none_when_published_absent(self):
        """无 published 的 entry：date 为 None，不拿 year 凑一个假日期。"""
        feed = ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">'
                '<entry><id>http://arxiv.org/abs/2601.00001v1</id>'
                '<title>No Date Here</title></entry></feed>').encode()
        client, _ = make([FakeResponse(200, feed,
                                       headers={"Content-Type": "application/atom+xml"})],
                         self.tmp.name)
        hit = client.lookup_arxiv_id("2601.00001")
        self.assertIsNone(hit.metadata["date"])

    def test_search_url_unchanged_without_date_window(self):
        """无日期窗口时 URL 与历史写法逐字节一致：既有缓存与回放测试不能因本次改动而破。"""
        client, transport = make([FakeResponse(200, read_fixture("arxiv_search_atom.xml"),
                                               headers={"Content-Type": "application/atom+xml"})],
                                 self.tmp.name)
        client.search("attention transformer", limit=20)
        url = transport._opener.calls[0][0]
        self.assertIn("search_query=all:attention%20transformer&max_results=20", url)
        self.assertNotIn("submittedDate", url)
        self.assertNotIn("sortBy", url)

    def test_search_pushes_date_window_natively(self):
        """有日期窗口时下推 arXiv 原生能力：submittedDate 闭区间 + 按提交时间倒序。
        少了 sortBy，「拉回前 N 篇」是按相关度的 N 篇、不是最新的 N 篇。"""
        client, transport = make([FakeResponse(200, read_fixture("arxiv_search_atom.xml"),
                                               headers={"Content-Type": "application/atom+xml"})],
                                 self.tmp.name)
        client.search("llm feedback", filters={"date_from": "2026-07-28",
                                               "date_to": "2026-07-29"}, limit=50)
        url = transport._opener.calls[0][0]
        self.assertIn("submittedDate%3A%5B202607280000%20TO%20202607292359%5D", url)
        self.assertIn("sortBy=submittedDate", url)
        self.assertIn("sortOrder=descending", url)

    def test_search_window_uses_boolean_terms(self):
        """窗口下必须把词袋拆成 `(all:w1 AND all:w2 ...)`。裸多词与 AND 同时出现时
        arXiv 只认第一个词，返回的是窗口内全站新发——2026-07-29 对真实 API 实测确认。"""
        client, transport = make([FakeResponse(200, read_fixture("arxiv_search_atom.xml"),
                                               headers={"Content-Type": "application/atom+xml"})],
                                 self.tmp.name)
        client.search("llm feedback programming", filters={"date_from": "2026-07-29"})
        url = transport._opener.calls[0][0]
        self.assertIn("%28all%3Allm%20AND%20all%3Afeedback%20AND%20all%3Aprogramming%29", url)

    def test_boolean_terms_strips_parser_breaking_chars(self):
        from paper_shared.datasources.clients.arxiv import _boolean_terms
        self.assertEqual(_boolean_terms('llm (feedback) "code":x'),
                         "(all:llm AND all:feedback AND all:codex)")

    def test_boolean_terms_all_punctuation_falls_back_to_phrase(self):
        """切不出词时退回精确短语（大概率 0 命中），绝不只剩日期条件——
        那会把窗口内全站新发当成用户主题的新发。短语里的破坏字符也要剔除，
        否则残留引号会让表达式失衡。"""
        from paper_shared.datasources.clients.arxiv import _boolean_terms
        expr = _boolean_terms('()"')
        self.assertNotIn("(", expr)
        self.assertEqual(expr.count('"'), 2)      # 只有短语自身那对引号，未失衡

    def test_usable_terms_counts_only_searchable(self):
        from paper_shared.datasources.clients.arxiv import usable_terms
        self.assertEqual(usable_terms("llm feedback programming"), 3)
        self.assertEqual(usable_terms('()" :'), 0)

    def test_search_single_sided_window_uses_sentinel(self):
        """arXiv 不接受开区间，单边窗口用哨兵补齐另一端。"""
        client, transport = make([FakeResponse(200, read_fixture("arxiv_search_atom.xml"),
                                               headers={"Content-Type": "application/atom+xml"})],
                                 self.tmp.name)
        client.search("q", filters={"date_from": "2026-07-01"})
        url = transport._opener.calls[0][0]
        self.assertIn("202607010000%20TO%20209912312359", url)

    def test_search_date_window_filters_results(self):
        """原生下推之后仍过一遍客户端兜底：fixture 里两篇是 2017/2018，窗口设 2026 应全滤掉。"""
        client, _ = make([FakeResponse(200, read_fixture("arxiv_search_atom.xml"),
                                       headers={"Content-Type": "application/atom+xml"})],
                         self.tmp.name)
        hits = client.search("attention", filters={"date_from": "2026-07-01",
                                                   "date_to": "2026-07-31"})
        self.assertEqual(hits, [])

    def test_lookup_missing_id_returns_none(self):
        # 空结果：feed 无 entry 子元素
        empty_feed = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        client, _ = make([FakeResponse(200, empty_feed,
                                       headers={"Content-Type": "application/atom+xml"})],
                         self.tmp.name)
        self.assertIsNone(client.lookup_arxiv_id("0000.00000"))

    def test_probe_ok(self):
        client, _ = make([FakeResponse(200, read_fixture("arxiv_atom.xml"),
                                       headers={"Content-Type": "application/atom+xml"})],
                         self.tmp.name)
        pr = client.probe()
        self.assertEqual((pr.source, pr.status, pr.role), ("arxiv", "ok", "core"))


if __name__ == "__main__":
    unittest.main()
