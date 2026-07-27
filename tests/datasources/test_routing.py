from __future__ import annotations

import pathlib
import tempfile
import unittest

from paper_shared.datasources.cache import Cache
from paper_shared.datasources.routing import RoutePlan, doi_prefix, route
from paper_shared.datasources.transport import Transport
from tests.datasources.fakes import FakeOpener, FakeResponse


def _transport(script):
    return Transport(user_agent="Paper-test/0", opener=FakeOpener(script),
                     sleep=lambda s: None, rand=lambda: 0.0)


class TestRouting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Cache(pathlib.Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_doi_prefix(self):
        self.assertEqual(doi_prefix("10.3969/j.issn.1000"), "10.3969")

    def test_crossref_route(self):
        t = _transport([FakeResponse(200, [{"DOI": "10.1038", "RA": "Crossref"}])])
        plan = route("https://doi.org/10.1038/NATURE12373", t, self.cache)
        self.assertEqual(plan, RoutePlan(doi_ra="Crossref",
                                         sources=["crossref", "openalex"], route_note=None))

    def test_istic_route_no_sources_with_note(self):
        t = _transport([FakeResponse(200, [{"DOI": "10.3969", "RA": "ISTIC"}])])
        plan = route("10.3969/j.issn.1000-0054.2020.01.001", t, self.cache)
        self.assertEqual(plan.doi_ra, "ISTIC")
        self.assertEqual(plan.sources, [])
        self.assertIn("ISTIC", plan.route_note)

    def test_datacite_route(self):
        t = _transport([FakeResponse(200, [{"DOI": "10.48550", "RA": "DataCite"}])])
        plan = route("10.48550/arXiv.2605.07723", t, self.cache)
        self.assertEqual(plan.sources, ["openalex", "arxiv"])

    def test_other_ra_conservative(self):
        t = _transport([FakeResponse(200, [{"DOI": "10.7567", "RA": "JaLC"}])])
        plan = route("10.7567/xxx", t, self.cache)
        self.assertEqual(plan.doi_ra, "unknown")
        self.assertEqual(plan.sources, ["crossref", "openalex"])
        self.assertIn("JaLC", plan.route_note)

    def test_prefix_cached_second_call_no_http(self):
        opener = FakeOpener([FakeResponse(200, [{"DOI": "10.3969", "RA": "ISTIC"}])])
        t = Transport(user_agent="t", opener=opener, sleep=lambda s: None)
        route("10.3969/a", t, self.cache)
        route("10.3969/b", t, self.cache)     # 同前缀第二次：命中前缀级缓存
        self.assertEqual(len(opener.calls), 1)

    def test_ra_unreachable_conservative(self):
        import socket
        t = _transport([socket.timeout()] * 5)
        plan = route("10.9999/xxx", t, self.cache)
        self.assertEqual(plan.doi_ra, "ra_unreachable")
        self.assertEqual(plan.sources, ["crossref", "openalex"])
        self.assertIsNotNone(plan.route_note)

    def test_prefix_not_registered_404(self):
        """doi.org/ra/{prefix} 返回 404 → 前缀未注册 → not_registered，不查任何源。

        编造的 DOI 前缀（如 10.9999）在任一注册机构都未注册，是 NOT_FOUND 的最强信号
        （paper-verify 据此径直落 NOT_FOUND，见 verify spec §4.2/§6）。
        """
        from tests.datasources.fakes import http_error
        t = _transport([http_error("https://doi.org/ra/10.9999", 404)])
        plan = route("10.9999/fake.0001", t, self.cache)
        self.assertEqual(plan.doi_ra, "not_registered")
        self.assertEqual(plan.sources, [])
        self.assertIsNotNone(plan.route_note)

    def test_prefix_not_registered_empty_body(self):
        """RA 端点 200 但返回空（无 RA 字段）→ 同样视为前缀未注册。"""
        t = _transport([FakeResponse(200, [])])
        plan = route("10.9999/fake.0002", t, self.cache)
        self.assertEqual(plan.doi_ra, "not_registered")
        self.assertEqual(plan.sources, [])


if __name__ == "__main__":
    unittest.main()
