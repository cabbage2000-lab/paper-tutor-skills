"""开放获取（OA）可得性字段的三源提取 + 契约形状 + 缓存往返。

医学生场景的真实断点：检索结果里看不出**哪篇能合法拿到全文**。三个源的 OA 字段全部
来自已经拿回来、但此前被 `_metadata` 丢弃的字段，零额外 HTTP 请求。

本文件守四件事（每条都对着一个会让用户误判的真相）：
  1. 三源同形——六个键一个不少（少一个键，呈现层静默取到 None，看着像「源没给」）；
  2. `pdf_url` 为 null 时降级到 `landing_page_url`（实测常态，只取 pdf_url 会让大量
     真有开放版本的文献显示成「无链接」）；
  3. 源没给 OA 信息时 `oa is None`，**不是 `status="closed"`**——「没查到开放版本」与
     「确认没有开放版本」是两件事，混同会让用户放弃本来能拿到的文献；
  4. 缓存往返后字段仍在（防 `_trim` 白名单漏加：首次有、二次没有，极难自查）。

字段路径取自 2026-08-04 对真实 API 的实测（见内部稿·医学检索增强实现计划的实测记录节）。
"""
from __future__ import annotations

import pathlib
import tempfile
import unittest

from paper_shared.datasources.cache import Cache
from paper_shared.datasources.clients.arxiv import ArxivClient
from paper_shared.datasources.clients.base import OA_KEYS, oa_record
from paper_shared.datasources.clients.openalex import OpenAlexClient
from paper_shared.datasources.clients.pubmed import PubMedClient
from paper_shared.datasources.registry import Registry
from paper_shared.datasources.transport import Throttle, Transport
from tests.datasources.fakes import FakeOpener, FakeResponse

# 实测样本 10.1056/NEJMoa2034577（2026-08-04）：pdf_url 为 null、landing_page_url 有值，
# 且 OA 版是 **投稿版**（这条 NEJM 论文的开放版不是最终发表版）。
_NEJM = {
    "id": "https://openalex.org/W3110381201",
    "doi": "https://doi.org/10.1056/NEJMoa2034577",
    "display_name": "Safety and Efficacy of the BNT162b2 mRNA Covid-19 Vaccine",
    "publication_year": 2020,
    "type": "article",
    "open_access": {"is_oa": True, "oa_status": "green",
                    "oa_url": "https://arca.fiocruz.br/handle/icict/46039",
                    "any_repository_has_fulltext": True},
    "best_oa_location": {"is_oa": True,
                         "landing_page_url": "https://arca.fiocruz.br/handle/icict/46039",
                         "pdf_url": None,
                         "source": {"display_name": "Fiocruz Repository",
                                    "type": "repository"},
                         "license": "other-oa", "version": "submittedVersion",
                         "raw_type": "repository"},
}

_EFETCH_MIN = """<?xml version="1.0"?>
<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID Version="1">33301246</PMID>
</MedlineCitation></PubmedArticle></PubmedArticleSet>
"""

_ARXIV_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v5</id>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is All You Need</title>
    <summary>We propose a new simple network architecture.</summary>
    <author><name>Ashish Vaswani</name></author>
    <link href="http://arxiv.org/abs/1706.03762v5" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/1706.03762v5" rel="related"
          type="application/pdf"/>
    <arxiv:primary_category term="cs.CL"/>
  </entry>
</feed>
"""


def make(cls, source_id, script, tmpdir, cache=None, **kw):
    cfg = Registry.load().get(source_id)
    transport = Transport(user_agent="Paper-test/0", opener=FakeOpener(script),
                          sleep=lambda s: None)
    cache = cache or Cache(pathlib.Path(tmpdir) / f"{source_id}.db")
    throttle = Throttle(0.0, clock=lambda: 0.0, sleep=lambda s: None)
    return cls(cfg, transport, cache, throttle,
               now_iso=lambda: "2026-08-04T00:00:00Z", **kw), transport


class TestOaRecordContract(unittest.TestCase):
    """六键固定形状。少一个键就会静默变成「源没给」，与真的没给分不开。"""

    def test_all_six_keys_always_present(self):
        rec = oa_record(status="gold")
        self.assertEqual(set(rec), set(OA_KEYS))
        self.assertEqual(len(OA_KEYS), 6)
        # 没传的键一律 None，不缺席
        self.assertIsNone(rec["url"])
        self.assertIsNone(rec["version"])

    def test_unknown_key_raises_not_silently_dropped(self):
        # 拼错键名（licence / oa_url）会让整列凭空消失，所以宁可炸在这里
        with self.assertRaises(ValueError):
            oa_record(status="gold", licence="cc-by")


class TestOpenAlexOa(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_extracts_status_version_host_license(self):
        client, _ = make(OpenAlexClient, "openalex", [FakeResponse(200, _NEJM)], self.tmp.name)
        oa = client.lookup_doi("10.1056/NEJMoa2034577").metadata["oa"]
        self.assertEqual(oa["status"], "green")
        # 投稿版：必须带出来，否则用户会拿投稿版当最终发表版引
        self.assertEqual(oa["version"], "submittedVersion")
        # host 来自 best_oa_location.source.type（**不是不存在的 host_type**）
        self.assertEqual(oa["host"], "repository")
        self.assertEqual(oa["license"], "other-oa")

    def test_falls_back_from_pdf_url_to_landing_page(self):
        """实测 pdf_url 常为 null 而 landing_page_url 有值——只取 pdf_url 会让大量真有
        开放版本的文献显示成「无链接」。"""
        client, _ = make(OpenAlexClient, "openalex", [FakeResponse(200, _NEJM)], self.tmp.name)
        oa = client.lookup_doi("10.1056/NEJMoa2034577").metadata["oa"]
        self.assertEqual(oa["url"], "https://arca.fiocruz.br/handle/icict/46039")
        self.assertEqual(oa["url_kind"], "landing")

    def test_pdf_url_wins_when_present(self):
        work = dict(_NEJM)
        work["best_oa_location"] = dict(_NEJM["best_oa_location"],
                                        pdf_url="https://repo.example.org/x.pdf")
        client, _ = make(OpenAlexClient, "openalex", [FakeResponse(200, work)], self.tmp.name)
        oa = client.lookup_doi("10.1056/NEJMoa2034577").metadata["oa"]
        self.assertEqual(oa["url"], "https://repo.example.org/x.pdf")
        self.assertEqual(oa["url_kind"], "pdf")

    def test_oa_url_is_last_resort_with_unknown_kind(self):
        """只剩 open_access.oa_url 时也要给链接，但源没说它是 PDF 还是落地页 → kind 未知。"""
        work = {k: v for k, v in _NEJM.items() if k != "best_oa_location"}
        client, _ = make(OpenAlexClient, "openalex", [FakeResponse(200, work)], self.tmp.name)
        oa = client.lookup_doi("10.1056/NEJMoa2034577").metadata["oa"]
        self.assertEqual(oa["url"], "https://arca.fiocruz.br/handle/icict/46039")
        self.assertIsNone(oa["url_kind"])

    def test_journal_source_type_maps_to_publisher(self):
        work = dict(_NEJM)
        work["best_oa_location"] = {"pdf_url": "https://publisher.example.org/a.pdf",
                                    "source": {"type": "journal"},
                                    "version": "publishedVersion"}
        client, _ = make(OpenAlexClient, "openalex", [FakeResponse(200, work)], self.tmp.name)
        self.assertEqual(client.lookup_doi("10.1056/x").metadata["oa"]["host"], "publisher")

    def test_unknown_source_type_is_none_not_guessed(self):
        work = dict(_NEJM)
        work["best_oa_location"] = {"landing_page_url": "https://x.org/a",
                                    "source": {"type": "某种新类型"}}
        client, _ = make(OpenAlexClient, "openalex", [FakeResponse(200, work)], self.tmp.name)
        self.assertIsNone(client.lookup_doi("10.1056/x").metadata["oa"]["host"])

    def test_missing_oa_fields_is_none_not_closed(self):
        """源没给 open_access → `oa is None`（未知），**绝不是 closed**。

        「没查到开放版本」与「确认没有开放版本」差着一件事：后者会让用户放弃一篇本来
        能从别处拿到的文献。同 cited_by_count 不补 0 的既有立场。
        """
        work = {k: v for k, v in _NEJM.items()
                if k not in ("open_access", "best_oa_location")}
        client, _ = make(OpenAlexClient, "openalex", [FakeResponse(200, work)], self.tmp.name)
        self.assertIsNone(client.lookup_doi("10.1056/NEJMoa2034577").metadata["oa"])

    def test_closed_status_is_kept_as_closed(self):
        """源**明确说** closed 时照实写 closed——那是源的判断，不是我们的推断。"""
        work = dict(_NEJM, open_access={"is_oa": False, "oa_status": "closed",
                                        "oa_url": None}, best_oa_location=None)
        client, _ = make(OpenAlexClient, "openalex", [FakeResponse(200, work)], self.tmp.name)
        oa = client.lookup_doi("10.1056/NEJMoa2034577").metadata["oa"]
        self.assertEqual(oa["status"], "closed")
        self.assertIsNone(oa["url"])
        self.assertIsNone(oa["url_kind"])

    def test_oa_survives_cache_roundtrip(self):
        """`_trim` 白名单漏加的表现是「有时有链接有时没有」——首次请求有、二次读缓存没有。

        换一个新 client 实例、共享同一持久化缓存（模拟跨会话），断言 metadata 与 raw
        两处都还在：raw 是 verify 逐字段比对的取证底本，OA 结论的原始依据不留在 raw 里，
        用户就无从复核这个链接是哪来的。
        """
        cache = Cache(pathlib.Path(self.tmp.name) / "shared.db")
        c1, _ = make(OpenAlexClient, "openalex", [FakeResponse(200, _NEJM)],
                     self.tmp.name, cache=cache)
        first = c1.lookup_doi("10.1056/NEJMoa2034577")
        c2, t2 = make(OpenAlexClient, "openalex", [], self.tmp.name, cache=cache)
        second = c2.lookup_doi("10.1056/NEJMoa2034577")     # 空脚本：只能靠缓存
        self.assertEqual(len(t2._opener.calls), 0)
        self.assertTrue(second.from_cache)
        self.assertEqual(second.metadata["oa"], first.metadata["oa"])
        for hit in (first, second):
            self.assertIn("open_access", hit.raw)
            self.assertIn("best_oa_location", hit.raw)


class TestPubMedOa(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def _summary(articleids, **kw):
        doc = {"uid": "33301246", "title": "Safety and Efficacy of BNT162b2",
               "pubdate": "2020 Dec 31", "fulljournalname": "New England Journal of Medicine",
               "authors": [{"name": "Polack FP"}], "articleids": articleids,
               "pubtype": ["Clinical Trial, Phase II", "Clinical Trial, Phase III",
                           "Journal Article", "Randomized Controlled Trial"]}
        doc.update(kw)
        return {"result": {"33301246": doc}}

    def _lookup(self, articleids, **kw):
        client, _ = make(PubMedClient, "pubmed",
                         [FakeResponse(200, {"esearchresult": {"idlist": ["33301246"]}}),
                          FakeResponse(200, self._summary(articleids, **kw)),
                          FakeResponse(200, _EFETCH_MIN)],
                         self.tmp.name)
        return client.lookup_doi("10.1056/NEJMoa2034577")

    def test_pmc_id_becomes_green_pmc_link(self):
        hit = self._lookup([{"idtype": "pubmed", "value": "33301246"},
                            {"idtype": "pmc", "value": "PMC7745181"},
                            {"idtype": "doi", "value": "10.1056/NEJMoa2034577"}])
        oa = hit.metadata["oa"]
        self.assertEqual(oa["status"], "green")
        self.assertEqual(oa["host"], "pmc")
        # 2026-08-04 实测：旧写法 www.ncbi.nlm.nih.gov/pmc/articles/… 回 301 跳到这个域
        self.assertEqual(oa["url"], "https://pmc.ncbi.nlm.nih.gov/articles/PMC7745181/")
        self.assertEqual(oa["url_kind"], "landing")
        # PMC 既存出版商终版也存作者稿，源不说是哪种就不猜
        self.assertIsNone(oa["version"])

    def test_dirty_pmcid_idtype_is_not_used(self):
        """必须用 `idtype == "pmc"`，不要用 `"pmcid"`——后者实测是
        `"pmc-id: PMC7745181;"`，拼进 URL 就是个 404 链接。"""
        hit = self._lookup([{"idtype": "pmcid", "value": "pmc-id: PMC7745181;"},
                            {"idtype": "doi", "value": "10.1056/NEJMoa2034577"}])
        self.assertIsNone(hit.metadata["oa"])

    def test_no_pmc_is_none_not_closed(self):
        """不在 PMC ≠ 没有开放版本：出版商自家 OA 与机构仓储都不进 PMC。"""
        hit = self._lookup([{"idtype": "doi", "value": "10.1056/NEJMoa2034577"}])
        self.assertIsNone(hit.metadata["oa"])

    def test_full_pubtype_array_kept_while_type_unchanged(self):
        """`type` 仍取首项（既有行为不变），但完整数组要留——实测首项是
        "Clinical Trial, Phase II"，只取首项就丢了 RCT 这个最有价值的证据类型标签。"""
        hit = self._lookup([{"idtype": "doi", "value": "10.1056/NEJMoa2034577"}])
        self.assertEqual(hit.metadata["type"], "Clinical Trial, Phase II")
        self.assertIn("Randomized Controlled Trial", hit.metadata["pubtypes"])
        self.assertEqual(len(hit.metadata["pubtypes"]), 4)


class TestArxivOa(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_preprint_is_always_open_with_pdf_link(self):
        client, _ = make(ArxivClient, "arxiv", [FakeResponse(200, _ARXIV_ATOM)], self.tmp.name)
        oa = client.lookup_arxiv_id("1706.03762").metadata["oa"]
        self.assertEqual(oa["status"], "green")
        self.assertEqual(oa["host"], "preprint")
        # 链接用 Atom 里 arXiv 自己给的 PDF href，不自己拼路径
        self.assertEqual(oa["url"], "http://arxiv.org/pdf/1706.03762v5")
        self.assertEqual(oa["url_kind"], "pdf")

    def test_version_is_conservatively_submitted(self):
        """arXiv 不透出是否已过同行评审，故按预印本惯例取最保守的一档——宁可让用户
        多核对一次版本，也不能把投稿版说成最终发表版。"""
        client, _ = make(ArxivClient, "arxiv", [FakeResponse(200, _ARXIV_ATOM)], self.tmp.name)
        self.assertEqual(client.lookup_arxiv_id("1706.03762").metadata["oa"]["version"],
                         "submittedVersion")

    def test_falls_back_to_landing_page_without_pdf_link(self):
        atom = _ARXIV_ATOM.replace(
            '<link title="pdf" href="http://arxiv.org/pdf/1706.03762v5" rel="related"\n'
            '          type="application/pdf"/>', "")
        client, _ = make(ArxivClient, "arxiv", [FakeResponse(200, atom)], self.tmp.name)
        oa = client.lookup_arxiv_id("1706.03762").metadata["oa"]
        self.assertEqual(oa["url"], "http://arxiv.org/abs/1706.03762v5")
        self.assertEqual(oa["url_kind"], "landing")


class TestThreeSourcesSameShape(unittest.TestCase):
    """三源同形：呈现层与 _merge_oa 都按键名读，某源少一个键就静默取到 None。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_all_three_sources_emit_the_same_key_set(self):
        oa_openalex = OpenAlexClient._oa(_NEJM)
        oa_pubmed = PubMedClient._oa({"articleids": [{"idtype": "pmc",
                                                      "value": "PMC7745181"}]})
        oa_arxiv = ArxivClient._oa({"full_id": "http://arxiv.org/abs/1706.03762v5",
                                    "pdf_url": None})
        for oa in (oa_openalex, oa_pubmed, oa_arxiv):
            self.assertEqual(set(oa), set(OA_KEYS))


if __name__ == "__main__":
    unittest.main()
