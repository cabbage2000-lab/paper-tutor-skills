from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from paper_shared.datasources.cache import Cache
from paper_shared.datasources.clients import CLIENT_CLASSES
from paper_shared.datasources.clients.pubmed import PubMedClient
from paper_shared.datasources.clients.eric import EricClient
from paper_shared.datasources.registry import Registry
from paper_shared.datasources.transport import Throttle, Transport
from tests.datasources.fakes import FakeOpener, FakeResponse, http_error

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "api_responses"

# efetch 的真实形状：结构化摘要拆成多个带 Label 的 AbstractText，且正文里嵌了行内标签
# （<i>）——只取 .text 会在 <i> 处截断，所以解析走 itertext()。
_EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">2386</PMID>
      <Article>
        <Abstract>
          <AbstractText Label="BACKGROUND">Sensing temperature in cells.</AbstractText>
          <AbstractText Label="METHODS">We used NV centres in <i>nano</i>diamond.</AbstractText>
        </Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


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


class TestPubMed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_registered(self):
        self.assertIs(CLIENT_CLASSES["pubmed"], PubMedClient)

    def test_lookup_doi_parses_esummary(self):
        client, _ = make(PubMedClient, "pubmed",
                         [FakeResponse(200, {"esearchresult": {"idlist": ["2386"]}}),
                          FakeResponse(200, load_fixture("pubmed_summaries.json")),
                          FakeResponse(200, _EFETCH_XML)],
                         self.tmp.name)
        hit = client.lookup_doi("10.1038/nature12373")
        self.assertEqual(hit.source, "pubmed")
        self.assertEqual(hit.metadata["title"], "Nanometre-scale thermometry in a living cell")
        self.assertEqual(hit.metadata["authors"], ["Kucsko G", "Maurer PC"])
        self.assertEqual(hit.metadata["year"], 2013)
        self.assertEqual(hit.metadata["venue"], "Nature")
        self.assertEqual(hit.metadata["doi"], "10.1038/nature12373")
        # esummary 不给摘要，摘要来自随后的 efetch；结构化多段带 Label 前缀拼接
        self.assertEqual(hit.metadata["abstract"],
                         "BACKGROUND: Sensing temperature in cells. "
                         "METHODS: We used NV centres in nanodiamond.")
        # PubMed 不给被引数——不设键（不是 0），「未知」不能说成「零被引」
        self.assertIsNone(hit.metadata.get("cited_by_count"))

    def test_efetch_failure_keeps_metadata(self):
        # 摘要是附属字段：efetch 挂了不能把整条题录拖没（否则次要字段的失败被升级成主能力失败）
        client, _ = make(PubMedClient, "pubmed",
                         [FakeResponse(200, {"esearchresult": {"idlist": ["2386"]}}),
                          FakeResponse(200, load_fixture("pubmed_summaries.json"))]
                         # 500 可重试，退避跑满 RetryPolicy.max_attempts 次才抛
                         + [http_error("https://eutils/efetch.fcgi", 500)] * 5,
                         self.tmp.name)
        hit = client.lookup_doi("10.1038/nature12373")
        self.assertEqual(hit.metadata["title"], "Nanometre-scale thermometry in a living cell")
        self.assertIsNone(hit.metadata["abstract"])

    def test_efetch_does_not_overwrite_cache_flag(self):
        # from_cache 报的必须是题录（esummary）的来源，不是最后一次 HTTP（efetch）的
        client, _ = make(PubMedClient, "pubmed",
                         [FakeResponse(200, {"esearchresult": {"idlist": ["2386"]}}),
                          FakeResponse(200, load_fixture("pubmed_summaries.json")),
                          FakeResponse(200, _EFETCH_XML)],
                         self.tmp.name)
        self.assertFalse(client.lookup_doi("10.1038/nature12373").from_cache)

    def test_lookup_doi_no_results_returns_none(self):
        client, _ = make(PubMedClient, "pubmed",
                         [FakeResponse(200, {"result": {"uids": []}})],
                         self.tmp.name)
        self.assertIsNone(client.lookup_doi("10.9999/nope"))

    def test_api_key_in_url(self):
        client, transport = make(PubMedClient, "pubmed",
                                 [FakeResponse(200, {"result": {"uids": []}})],
                                 self.tmp.name, api_key="NCBI123")
        client.lookup_doi("10.1038/nature12373")
        url, _ = transport._opener.calls[0]
        self.assertIn("api_key=NCBI123", url)


class TestEric(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_registered(self):
        self.assertIs(CLIENT_CLASSES["eric"], EricClient)

    def test_search_parses_docs(self):
        client, _ = make(EricClient, "eric",
                         [FakeResponse(200, load_fixture("eric_search.json"))],
                         self.tmp.name)
        hits = client.search("ChatGPT education")
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(hit.metadata["title"], "ChatGPT and undergraduate writing efficiency")
        self.assertEqual(hit.metadata["authors"], ["Zhang W", "Li M"])
        self.assertEqual(hit.metadata["year"], 2024)
        self.assertEqual(hit.metadata["doi"], "10.1234/jet.2024.001")

    def test_search_no_results(self):
        client, _ = make(EricClient, "eric",
                         [FakeResponse(200, {"response": {"numFound": 0, "docs": []}})],
                         self.tmp.name)
        self.assertEqual(client.search("zzz"), [])


if __name__ == "__main__":
    unittest.main()
