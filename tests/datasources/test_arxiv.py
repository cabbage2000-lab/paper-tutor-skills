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
