from __future__ import annotations

import pathlib
import tempfile
import unittest
from unittest import mock

from paper_shared.datasources.cache import Cache
from paper_shared.datasources.models import ProbeResult
from paper_shared.datasources.probe import ProbeEngine
from paper_shared.datasources.registry import Registry
from paper_shared.datasources.transport import Transport
from tests.datasources.fakes import FakeOpener, FakeResponse


class TestProbeOverall(unittest.TestCase):
    def test_all_core_ok(self):
        results = [
            ProbeResult("crossref", "ok", "core"),
            ProbeResult("openalex", "ok", "core"),
            ProbeResult("semantic_scholar", "ok", "core"),
            ProbeResult("arxiv", "ok", "core"),
        ]
        self.assertEqual(ProbeEngine.overall(results), "ok")

    def test_supplementary_unavailable_does_not_lower(self):
        results = [
            ProbeResult("crossref", "ok", "core"),
            ProbeResult("openalex", "ok", "core"),
            ProbeResult("semantic_scholar", "ok", "core"),
            ProbeResult("arxiv", "ok", "core"),
            ProbeResult("pubmed", "unavailable", "supplementary"),
            ProbeResult("eric", "unavailable", "supplementary"),
        ]
        self.assertEqual(ProbeEngine.overall(results), "ok")

    def test_core_partial_is_degraded(self):
        results = [
            ProbeResult("crossref", "ok", "core"),
            ProbeResult("openalex", "ok", "core"),
            ProbeResult("semantic_scholar", "partial", "core"),
            ProbeResult("arxiv", "ok", "core"),
        ]
        self.assertEqual(ProbeEngine.overall(results), "degraded")

    def test_all_core_offline(self):
        results = [
            ProbeResult("crossref", "unavailable", "core"),
            ProbeResult("openalex", "unavailable", "core"),
            ProbeResult("semantic_scholar", "unavailable", "core"),
            ProbeResult("arxiv", "unavailable", "core"),
        ]
        self.assertEqual(ProbeEngine.overall(results), "offline")


class TestProbeRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = Registry.load()

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_calls_each_client_probe(self):
        engine = ProbeEngine(self.registry,
                             transport=Transport(user_agent="t",
                                                 opener=FakeOpener([FakeResponse(200, {})] * 20),
                                                 sleep=lambda s: None),
                             cache=Cache(pathlib.Path(self.tmp.name) / "p.db"))
        # 每个客户端的 probe() 被调用；mock 掉 _make_clients 注入受控 client
        from paper_shared.datasources.clients.base import SourceClient

        class FakeClient:
            def __init__(self, src_id, status):
                self.id = src_id
                self._status = status

            def probe(self):
                role = "core" if self.id in ("crossref", "openalex",
                                             "semantic_scholar", "arxiv") else "supplementary"
                return ProbeResult(self.id, self._status, role)

        engine._make_clients = lambda: {
            sid: FakeClient(sid, "ok") for sid in
            ("crossref", "openalex", "semantic_scholar", "arxiv",
             "pubmed", "eric", "doi_ra", "doi_meta")
        }
        results = engine.run()
        self.assertEqual(len(results), 8)
        self.assertEqual([r.source for r in results],
                         ["crossref", "openalex", "semantic_scholar", "arxiv",
                          "pubmed", "eric", "doi_ra", "doi_meta"])
        self.assertEqual(engine.overall(results), "ok")

    def test_exclude_supplementary(self):
        engine = ProbeEngine(self.registry, include_supplementary=False,
                             transport=Transport(user_agent="t",
                                                 opener=FakeOpener([]),
                                                 sleep=lambda s: None),
                             cache=Cache(pathlib.Path(self.tmp.name) / "p.db"))
        engine._make_clients = lambda: {}
        # _run 无 client 时只探测注册表中的 api 源
        results = engine.run()
        self.assertNotIn("pubmed", [r.source for r in results])
        self.assertNotIn("eric", [r.source for r in results])
        self.assertIn("crossref", [r.source for r in results])


if __name__ == "__main__":
    unittest.main()
