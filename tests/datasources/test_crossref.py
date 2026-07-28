from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from paper_shared.datasources.cache import Cache
from paper_shared.datasources.clients import CLIENT_CLASSES
from paper_shared.datasources.clients.crossref import CrossrefClient
from paper_shared.datasources.registry import Registry
from paper_shared.datasources.transport import Throttle, Transport
from tests.datasources.fakes import FakeOpener, FakeResponse, http_error

FIXTURES = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "api_responses"


def load_fixture(name: str):
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


def make_client(script, fresh=False, tmpdir=None):
    cfg = Registry.load().get("crossref")
    transport = Transport(user_agent="Paper-test/0", opener=FakeOpener(script),
                          sleep=lambda s: None)
    cache = Cache(pathlib.Path(tmpdir) / "t.db")
    throttle = Throttle(0.0, clock=lambda: 0.0, sleep=lambda s: None)
    return CrossrefClient(cfg, transport, cache, throttle, fresh=fresh,
                          now_iso=lambda: "2026-07-22T00:00:00Z"), transport


class TestCrossref(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_registered_in_client_classes(self):
        self.assertIs(CLIENT_CLASSES["crossref"], CrossrefClient)

    def test_lookup_doi_hit_normalizes_metadata(self):
        client, _ = make_client([FakeResponse(200, load_fixture("crossref_hit.json"))],
                                tmpdir=self.tmp.name)
        hit = client.lookup_doi("10.1038/nature12373")
        self.assertEqual(hit.source, "crossref")
        self.assertEqual(hit.metadata["title"], "Nanometre-scale thermometry in a living cell")
        self.assertEqual(hit.metadata["authors"], ["G. Kucsko", "P. C. Maurer"])
        self.assertEqual(hit.metadata["year"], 2013)
        self.assertEqual(hit.metadata["venue"], "Nature")
        self.assertEqual(hit.metadata["doi"], "10.1038/nature12373")
        self.assertIsNone(hit.retraction)
        self.assertEqual(hit.fetched_at, "2026-07-22T00:00:00Z")

    def test_lookup_doi_404_returns_none(self):
        client, _ = make_client([http_error("https://api.crossref.org", 404)],
                                tmpdir=self.tmp.name)
        self.assertIsNone(client.lookup_doi("10.9999/nonexistent"))

    def test_retraction_extracted(self):
        """被撤稿的论文：撤稿信息在 updated-by（fixture 按真实响应形状构造）。"""
        client, _ = make_client([FakeResponse(200, load_fixture("crossref_retracted.json"))],
                                tmpdir=self.tmp.name)
        hit = client.lookup_doi("10.5555/retracted-example")
        self.assertIsNotNone(hit.retraction)
        self.assertEqual(hit.retraction["type"], "retraction")
        self.assertEqual(hit.retraction["date_parts"], [[2021, 3, 2]])
        self.assertEqual(hit.retraction["source"], "retraction-watch")
        # updated-by 指向的是撤稿声明，不是本文自己
        self.assertEqual(hit.retraction["doi"], "10.5555/the-retraction-notice")

    def test_retraction_notice_itself_not_flagged(self):
        """反向回归：本文**是**那份撤稿声明（只有 update-to）→ 不得判为已撤稿。

        update-to 与 updated-by 方向相反，读错会让 RETRACTED 态永不触发；这条锁住
        方向，防止改回 update-to（那样只有本用例的撤稿声明会被误标为已撤稿）。
        """
        client, _ = make_client(
            [FakeResponse(200, load_fixture("crossref_retraction_notice.json"))],
            tmpdir=self.tmp.name)
        hit = client.lookup_doi("10.5555/the-retraction-notice")
        self.assertIsNone(hit.retraction)

    def test_lookup_uses_cache_second_call(self):
        body = load_fixture("crossref_hit.json")
        client, transport = make_client([FakeResponse(200, body)], tmpdir=self.tmp.name)
        client.lookup_doi("10.1038/nature12373")
        hit2 = client.lookup_doi("10.1038/nature12373")   # FakeOpener 脚本已空：走缓存
        self.assertEqual(hit2.metadata["year"], 2013)
        self.assertEqual(len(transport._opener.calls), 1)

    def test_fresh_bypasses_cache_read(self):
        body = load_fixture("crossref_hit.json")
        client, transport = make_client([FakeResponse(200, body), FakeResponse(200, body)],
                                        fresh=True, tmpdir=self.tmp.name)
        client.lookup_doi("10.1038/nature12373")
        client.lookup_doi("10.1038/nature12373")
        self.assertEqual(len(transport._opener.calls), 2)

    def test_match_returns_hits(self):
        client, _ = make_client([FakeResponse(200, load_fixture("crossref_match.json"))],
                                tmpdir=self.tmp.name)
        hits = client.match("Nanometre-scale thermometry in a living cell")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].metadata["doi"], "10.1038/nature12373")

    def test_probe_ok(self):
        client, _ = make_client([FakeResponse(200, load_fixture("crossref_hit.json"))],
                                tmpdir=self.tmp.name)
        pr = client.probe()
        self.assertEqual((pr.source, pr.status, pr.role), ("crossref", "ok", "core"))

    def test_probe_unavailable_with_reason(self):
        import socket
        client, _ = make_client([socket.timeout()] * 5, tmpdir=self.tmp.name)
        pr = client.probe()
        self.assertEqual(pr.status, "unavailable")
        self.assertIn("TIMEOUT", pr.reason)


if __name__ == "__main__":
    unittest.main()
