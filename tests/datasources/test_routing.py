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

    def test_istic_routes_to_doi_meta(self):
        """ISTIC（中文 DOI）走内容协商取题录——此前是空路由、整源跳过。

        改动前这里断言 `sources == []`，依据是「注册机构未提供免费元数据 API」。那个断言
        经实测为假：`10.11821/dlxb202001001` 的内容协商回完整 CSL-JSON（见 test_doi_meta）。
        """
        t = _transport([FakeResponse(200, [{"DOI": "10.3969", "RA": "ISTIC"}])])
        plan = route("10.3969/j.issn.1000-0054.2020.01.001", t, self.cache)
        self.assertEqual(plan.doi_ra, "ISTIC")
        self.assertEqual(plan.sources, ["doi_meta"])
        self.assertIn("ISTIC", plan.route_note)

    def test_cnki_is_a_registrant_not_unknown(self):
        """知网自己就是 DOI 注册机构，不该落 unknown 走保守路由。

        实测 `10.16511/j.cnki.qhdxxb.2020.22.001` 的 agency 为 CNKI。落 unknown 会去查
        crossref/openalex——它们按定义不收录别家注册的 DOI，两次必然 miss，还会把
        「英文库没有」混进中文条目的证据链。
        """
        t = _transport([FakeResponse(200, [{"DOI": "10.16511", "RA": "CNKI"}])])
        plan = route("10.16511/j.cnki.qhdxxb.2020.22.001", t, self.cache)
        self.assertEqual(plan.doi_ra, "CNKI")
        self.assertEqual(plan.sources, ["doi_meta"])
        self.assertIn("不作编造嫌疑处理", plan.route_note)

    def test_cn_notes_claim_prefix_only_not_doi_existence(self):
        """两条中文 note 只能声称「前缀已注册」，不得声称这一条 DOI 存在。

        RA 判别是前缀级的：实测编造后缀 `10.11821/dlxb209999999` 的前缀照样报 ISTIC。
        把 note 写成「DOI 合法存在」＝替一个可能编造的 DOI 作存在性担保，违反不编造底线。
        这条断言是防措辞漂回去的锁。
        """
        from paper_shared.datasources.routing import CNKI_NOTE, ISTIC_NOTE
        for note in (ISTIC_NOTE, CNKI_NOTE):
            self.assertIn("前缀", note)
            self.assertNotIn("DOI 合法存在", note)
            self.assertNotIn("文献真实存在", note)

    def test_cn_doi_ra_never_routes_to_english_sources(self):
        """中文 RA 一律不叠加 crossref / openalex（省两次必然 miss 的请求）。"""
        from paper_shared.datasources.routing import CN_DOI_RA, RA_ROUTES
        for ra in CN_DOI_RA:
            self.assertEqual(RA_ROUTES[ra], ["doi_meta"], ra)

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
