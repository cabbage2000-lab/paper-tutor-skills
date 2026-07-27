from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from paper_shared.datasources.cache import Cache
from paper_shared.datasources.clients import CLIENT_CLASSES
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


if __name__ == "__main__":
    unittest.main()
