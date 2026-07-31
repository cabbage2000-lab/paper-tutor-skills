"""doi_meta（DOI 内容协商）客户端：CSL-JSON 解析 + 各注册机构支持度差异。

样本取自真实响应（`https://doi.org/10.11821/dlxb202001001`，《地理学报》，ISTIC 注册），
包括它实测投递的 HTML 实体标题与 HTML 片段摘要——这两处不处理就会把 `&#x0201C;` 和
`<p id="C2">` 原样带进笔记表。
"""
from __future__ import annotations

import pathlib
import tempfile
import unittest

from paper_shared.datasources.cache import Cache
from paper_shared.datasources.clients.base import canonical_type
from paper_shared.datasources.clients.doi_meta import CSL_JSON_ACCEPT, DoiMetaClient
from paper_shared.datasources.registry import Registry
from paper_shared.datasources.transport import Throttle, Transport, TransportError
from tests.datasources.fakes import FakeOpener, FakeResponse, http_error

# 真实响应（ISTIC）——标题带 HTML 实体、摘要是 HTML 片段、作者整名落在 given
ISTIC_CSL = {
    "DOI": "10.11821/dlxb202001001",
    "URL": "http://www.geog.com.cn/CN/10.11821/dlxb202001001",
    "title": "理解地理&#x0201C;耦合&#x0201D;实现地理&#x0201C;集成&#x0201D;",
    "abstract": "<p id=\"C2\">&#x0201C;耦合&#x0201D;作为物理学的经典概念,为许多学科提供了思路。</p>",
    "author": [{"given": "宋长青"}],
    "container-title": "地理学报",
    "issued": {"date-parts": [[2020]]},
    "volume": "75", "issue": "1", "page": "3",
    "type": "article-journal",
}

# CNKI 注册的 DOI 实测回「多重解析地址选择页」HTML，不回 CSL-JSON
CNKI_HTML = ("<!DOCTYPE html><html><body><div class=\"fbHd\">多重解析地址选择页面</div>"
             "</body></html>")


def _client(script, fresh=False):
    tmp = tempfile.TemporaryDirectory()
    cache = Cache(pathlib.Path(tmp.name) / "t.db")
    opener = FakeOpener(script)
    transport = Transport(user_agent="Paper-test/0", opener=opener,
                          sleep=lambda s: None, rand=lambda: 0.0)
    cfg = Registry.load().get("doi_meta")
    c = DoiMetaClient(cfg, transport, cache, Throttle(0.0, sleep=lambda s: None), fresh=fresh)
    c._tmp, c._opener = tmp, opener      # 持有引用，避免 tmpdir 被提前回收
    return c


class TestIsticParsing(unittest.TestCase):
    def test_full_bibliographic_record(self):
        """ISTIC 的 CSL-JSON → 完整题录。这是本次改动的核心价值。"""
        c = _client([FakeResponse(200, ISTIC_CSL)])
        hit = c.lookup_doi("10.11821/dlxb202001001")
        self.assertIsNotNone(hit)
        m = hit.metadata
        self.assertEqual(m["title"], "理解地理“耦合”实现地理“集成”")   # 实体已反转义
        self.assertEqual(m["authors"], ["宋长青"])                     # given 单字段
        self.assertEqual(m["venue"], "地理学报")
        self.assertEqual(m["year"], 2020)
        self.assertEqual(m["doi"], "10.11821/dlxb202001001")
        self.assertEqual(hit.source, "doi_meta")

    def test_abstract_html_cleaned(self):
        """摘要是 HTML 片段，须剥标签 + 反转义（复用 clean_jats_abstract）。"""
        c = _client([FakeResponse(200, ISTIC_CSL)])
        abstract = c.lookup_doi("10.11821/dlxb202001001").metadata["abstract"]
        self.assertNotIn("<p", abstract)
        self.assertNotIn("&#x", abstract)
        self.assertTrue(abstract.startswith("“耦合”作为物理学的经典概念"))

    def test_csl_type_normalizes(self):
        """CSL 的 `article-journal` 与 Crossref 的 `journal-article` 词序相反，须归一。"""
        c = _client([FakeResponse(200, ISTIC_CSL)])
        self.assertEqual(canonical_type(c.lookup_doi("10.1/x").metadata["type"]),
                         "journal-article")

    def test_sends_csl_accept_header(self):
        """不带 CSL Accept 头，doi.org 会 302 到出版商页面而不是回题录。"""
        c = _client([FakeResponse(200, ISTIC_CSL)])
        c.lookup_doi("10.11821/dlxb202001001")
        _, headers = c._opener.calls[0]
        self.assertEqual(headers.get("Accept"), CSL_JSON_ACCEPT)

    def test_doi_slash_not_escaped(self):
        """DOI 的 `/` 是内容协商路径的一部分，转义掉会 404。"""
        c = _client([FakeResponse(200, ISTIC_CSL)])
        c.lookup_doi("10.11821/dlxb202001001")
        self.assertIn("/10.11821/dlxb202001001", c._opener.calls[0][0])
        self.assertNotIn("%2F", c._opener.calls[0][0])

    def test_cited_by_count_is_none_not_zero(self):
        """CSL-JSON 不含被引数——None（未知）≠ 0（零被引）。"""
        c = _client([FakeResponse(200, ISTIC_CSL)])
        self.assertIsNone(c.lookup_doi("10.1/x").metadata["cited_by_count"])


class TestUnsupportedRegistrant(unittest.TestCase):
    def test_html_response_is_miss_not_error(self):
        """CNKI 回 HTML → miss（该 RA 不支持内容协商），不是 error。

        混同两者会让知网条目在核验报告里显示成网络故障，而它其实是「查了，这条通路没有」。
        """
        c = _client([FakeResponse(200, CNKI_HTML)])
        self.assertIsNone(c.lookup_doi("10.16511/j.cnki.qhdxxb.2020.22.001"))

    def test_404_is_miss(self):
        c = _client([http_error("https://doi.org/10.9999/x", 404)])
        self.assertIsNone(c.lookup_doi("10.9999/x"))

    def test_real_failure_still_raises(self):
        """超时 / 5xx 是真故障，必须上抛让 batch 记 error（区分 miss ≠ error）。"""
        import socket
        c = _client([socket.timeout()] * 5)
        with self.assertRaises(TransportError):
            c.lookup_doi("10.11821/x")

    def test_empty_json_is_miss(self):
        c = _client([FakeResponse(200, {})])
        self.assertIsNone(c.lookup_doi("10.11821/x"))


class TestFieldEdgeCases(unittest.TestCase):
    def test_literal_institutional_author(self):
        """机构作者用 CSL 的 `literal` 字段，不是 given/family。"""
        c = _client([FakeResponse(200, dict(ISTIC_CSL,
                                           author=[{"literal": "中国科学院地理科学与资源研究所"}]))])
        self.assertEqual(c.lookup_doi("10.1/x").metadata["authors"],
                         ["中国科学院地理科学与资源研究所"])

    def test_given_and_family_joined(self):
        c = _client([FakeResponse(200, dict(ISTIC_CSL,
                                           author=[{"given": "Chang-Qing", "family": "Song"}]))])
        self.assertEqual(c.lookup_doi("10.1/x").metadata["authors"], ["Chang-Qing Song"])

    def test_title_as_list(self):
        """个别 RA 把 title 投成数组（Crossref 风格），两种形态都要收。"""
        c = _client([FakeResponse(200, dict(ISTIC_CSL, title=["数组形态的标题"]))])
        self.assertEqual(c.lookup_doi("10.1/x").metadata["title"], "数组形态的标题")

    def test_string_year_coerced(self):
        c = _client([FakeResponse(200, dict(ISTIC_CSL,
                                           issued={"date-parts": [["2019"]]}))])
        self.assertEqual(c.lookup_doi("10.1/x").metadata["year"], 2019)

    def test_unparseable_year_is_none(self):
        """年份给不出就留 None，不塞脏值。"""
        c = _client([FakeResponse(200, dict(ISTIC_CSL,
                                           issued={"date-parts": [["n.d."]]}))])
        self.assertIsNone(c.lookup_doi("10.1/x").metadata["year"])

    def test_no_author_details(self):
        """内容协商不提供 ORCID / 机构，如实给空，不造空壳。"""
        c = _client([FakeResponse(200, ISTIC_CSL)])
        self.assertEqual(c.lookup_doi("10.1/x").metadata["author_details"], [])


if __name__ == "__main__":
    unittest.main()
