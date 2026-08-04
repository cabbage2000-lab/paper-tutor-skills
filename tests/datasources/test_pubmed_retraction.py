"""PubMed 撤稿信号（两路）+ 方向陷阱 + 关注声明的归属。

医学是撤稿重灾区，而此前撤稿检测只有 Crossref（Retraction Watch）与 OpenAlex
（布尔 `is_retracted`）两源，都不接 PubMed。PubMed 给的信息量更大：撤稿声明所在的
期刊、卷期页、DOI 与 PMID。两路都是零额外请求——`pubtype` 在 esummary 里，
`CommentsCorrections` 在 `_fetch_details` 已经在调的那份 efetch XML 里。

本文件守四件事：
  1. 快路径（esummary 的 `pubtype`）单独可用——efetch 挂了也不能把撤稿事实丢掉；
  2. 详情解析出 RefSource / PMID / DOI；
  3. **方向陷阱**：`RetractionOf`（本文是那份撤稿声明）不得触发撤稿态。读反则撤稿态
     永不触发，与 crossref 的 update-to / updated-by 是同一个坑；
  4. 关注声明（Expression of Concern）**不混入 `retraction`**——它非空即被
     paper-verify 判 RETRACTED（judge.py 第 4 步），把「期刊存疑」说成「已撤稿」
     是替期刊下结论。

样本取自 2026-08-04 对真实 API 的实测（PMID 42371203 是一条真撤稿文献）。
"""
from __future__ import annotations

import pathlib
import tempfile
import unittest

from paper_shared.datasources.cache import Cache
from paper_shared.datasources.clients.pubmed import PubMedClient
from paper_shared.datasources.registry import Registry
from paper_shared.datasources.transport import Throttle, Transport
from tests.datasources.fakes import FakeOpener, FakeResponse, http_error

# 真实形状：撤稿声明的 RefSource 是「期刊. 年 月 日;卷(期):页. doi: …」整句
_RETRACTION_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">42371203</PMID>
      <Article>
        <PublicationTypeList>
          <PublicationType UI="D016428">Journal Article</PublicationType>
          <PublicationType UI="D016441">Retracted Publication</PublicationType>
        </PublicationTypeList>
      </Article>
      <CommentsCorrectionsList>
        <CommentsCorrections RefType="RetractionIn">
          <RefSource>Vet Res Commun. 2026 Jul 27;50(5):485. doi: 10.1007/s11259-026-11432-9.</RefSource>
          <PMID Version="1">42507066</PMID>
        </CommentsCorrections>
      </CommentsCorrectionsList>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""

# 方向陷阱：本文**就是**那份撤稿声明（RefType=RetractionOf），它自己没被撤稿
_RETRACTION_OF_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">42507066</PMID>
      <CommentsCorrectionsList>
        <CommentsCorrections RefType="RetractionOf">
          <RefSource>Vet Res Commun. 2025 Mar 1;49(2):101.</RefSource>
          <PMID Version="1">42371203</PMID>
        </CommentsCorrections>
      </CommentsCorrectionsList>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""

_EOC_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID Version="1">30000001</PMID>
      <CommentsCorrectionsList>
        <CommentsCorrections RefType="ExpressionOfConcernIn">
          <RefSource>Lancet. 2026 Feb 3;407(10420):512. doi: 10.1016/S0140-6736(26)00123-4.</RefSource>
          <PMID Version="1">42600001</PMID>
        </CommentsCorrections>
      </CommentsCorrectionsList>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>
"""


def _summary(uid, pubtype, **kw):
    doc = {"uid": uid, "title": "Effect of X on Y", "pubdate": "2025 Mar 1",
           "fulljournalname": "Veterinary Research Communications",
           "authors": [{"name": "Li Q"}], "pubtype": list(pubtype),
           "articleids": [{"idtype": "pubmed", "value": uid},
                          {"idtype": "doi", "value": "10.1007/s11259-025-10001-x"}]}
    doc.update(kw)
    return {"result": {uid: doc}}


def make(script, tmpdir):
    cfg = Registry.load().get("pubmed")
    transport = Transport(user_agent="Paper-test/0", opener=FakeOpener(script),
                          sleep=lambda s: None)
    cache = Cache(pathlib.Path(tmpdir) / "pubmed.db")
    throttle = Throttle(0.0, clock=lambda: 0.0, sleep=lambda s: None)
    return PubMedClient(cfg, transport, cache, throttle,
                        now_iso=lambda: "2026-08-04T00:00:00Z"), transport


class TestRetractionFastPath(unittest.TestCase):
    """快路径：esummary 的 pubtype 数组，题录已经在手、无需 efetch。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_retracted_publication_pubtype_flags_retraction(self):
        client, _ = make([FakeResponse(200, {"esearchresult": {"idlist": ["42371203"]}}),
                          FakeResponse(200, _summary("42371203",
                                                     ["Journal Article", "Case Reports",
                                                      "Retracted Publication"])),
                          FakeResponse(200, _RETRACTION_XML)],
                         self.tmp.name)
        r = client.lookup_doi("10.1007/s11259-025-10001-x").retraction
        self.assertIsNotNone(r)
        self.assertEqual(r["type"], "retraction")
        self.assertEqual(r["source"], "pubmed")

    def test_normal_article_has_no_retraction(self):
        client, _ = make([FakeResponse(200, {"esearchresult": {"idlist": ["42371203"]}}),
                          FakeResponse(200, _summary("42371203", ["Journal Article"])),
                          FakeResponse(200, "<PubmedArticleSet/>")],
                         self.tmp.name)
        self.assertIsNone(client.lookup_doi("10.1007/s11259-025-10001-x").retraction)

    def test_efetch_failure_keeps_the_retraction_fact(self):
        """详情拿不到不能把撤稿事实丢掉——那是把次要字段的失败升级成主要事实的失败。"""
        client, _ = make([FakeResponse(200, {"esearchresult": {"idlist": ["42371203"]}}),
                          FakeResponse(200, _summary("42371203",
                                                     ["Journal Article",
                                                      "Retracted Publication"]))]
                         # 500 可重试，退避跑满 RetryPolicy.max_attempts 次才抛
                         + [http_error("https://eutils/efetch.fcgi", 500)] * 5,
                         self.tmp.name)
        r = client.lookup_doi("10.1007/s11259-025-10001-x").retraction
        self.assertIsNotNone(r)
        self.assertEqual(r["label"], "Retracted Publication")   # 只有快路径的粗标签
        self.assertIsNone(r["doi"])
        self.assertIsNone(r["notice_pmid"])


class TestRetractionDetail(unittest.TestCase):
    """详情：CommentsCorrections[RefType=RetractionIn]，信息量超过现有两源。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_parses_refsource_pmid_and_doi(self):
        client, _ = make([FakeResponse(200, {"esearchresult": {"idlist": ["42371203"]}}),
                          FakeResponse(200, _summary("42371203",
                                                     ["Journal Article",
                                                      "Retracted Publication"])),
                          FakeResponse(200, _RETRACTION_XML)],
                         self.tmp.name)
        r = client.lookup_doi("10.1007/s11259-025-10001-x").retraction
        self.assertIn("Vet Res Commun", r["label"])
        # 句末的句点不属于 DOI
        self.assertEqual(r["doi"], "10.1007/s11259-026-11432-9")
        self.assertEqual(r["notice_pmid"], "42507066")
        # PubMed 不给结构化撤稿日期；RefSource 里那个日期是声明的刊期，不硬解析
        self.assertIsNone(r["date_parts"])

    def test_detail_alone_is_enough_without_pubtype_flag(self):
        """有 RetractionIn 就说明存在撤稿声明——即使 esummary 的 pubtype 还没更新。"""
        client, _ = make([FakeResponse(200, {"esearchresult": {"idlist": ["42371203"]}}),
                          FakeResponse(200, _summary("42371203", ["Journal Article"])),
                          FakeResponse(200, _RETRACTION_XML)],
                         self.tmp.name)
        r = client.lookup_doi("10.1007/s11259-025-10001-x").retraction
        self.assertIsNotNone(r)
        self.assertEqual(r["notice_pmid"], "42507066")

    def test_no_extra_request_for_details(self):
        """详情搭 efetch 的车：一共 3 次请求（esearch + esummary + efetch），不是 4 次。"""
        client, transport = make(
            [FakeResponse(200, {"esearchresult": {"idlist": ["42371203"]}}),
             FakeResponse(200, _summary("42371203", ["Retracted Publication"])),
             FakeResponse(200, _RETRACTION_XML)],
            self.tmp.name)
        client.lookup_doi("10.1007/s11259-025-10001-x")
        self.assertEqual(len(transport._opener.calls), 3)

    def test_malformed_xml_returns_empty_not_raise(self):
        self.assertEqual(PubMedClient._parse_corrections("<not xml"), {})
        self.assertEqual(PubMedClient._parse_corrections(""), {})

    def test_refsource_without_doi_leaves_doi_none(self):
        """取不到 DOI 就是 None——绝不从卷期页文本里凑一个出来。"""
        xml = _RETRACTION_XML.replace(
            " doi: 10.1007/s11259-026-11432-9.", "")
        got = PubMedClient._parse_corrections(xml)["42371203"]["retraction_in"]
        self.assertIsNone(got["doi"])
        self.assertEqual(got["pmid"], "42507066")


class TestDirectionTrap(unittest.TestCase):
    """`…Of` 是「本文就是那份声明」，`…In` 才是「本文被撤稿」。读反则撤稿态永不触发。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_retraction_of_is_not_parsed_as_being_retracted(self):
        self.assertEqual(PubMedClient._parse_corrections(_RETRACTION_OF_XML), {})

    def test_retraction_of_does_not_trigger_retracted_state(self):
        """撤稿声明本身进检索结果时（医学检索常见），绝不能被标成「已撤稿」。"""
        client, _ = make([FakeResponse(200, {"esearchresult": {"idlist": ["42507066"]}}),
                          FakeResponse(200, _summary("42507066",
                                                     ["Journal Article", "Retraction of Publication"])),
                          FakeResponse(200, _RETRACTION_OF_XML)],
                         self.tmp.name)
        self.assertIsNone(client.lookup_doi("10.1007/s11259-026-11432-9").retraction)

    def test_other_reftypes_are_ignored(self):
        xml = _RETRACTION_XML.replace('RefType="RetractionIn"', 'RefType="ErratumIn"')
        self.assertEqual(PubMedClient._parse_corrections(xml), {})


class TestExpressionOfConcern(unittest.TestCase):
    """关注声明是撤稿的中间态：单独成键陈列，不进 retraction、不新增第七态。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _hit(self):
        client, _ = make([FakeResponse(200, {"esearchresult": {"idlist": ["30000001"]}}),
                          FakeResponse(200, _summary("30000001", ["Journal Article"])),
                          FakeResponse(200, _EOC_XML)],
                         self.tmp.name)
        return client.lookup_doi("10.1007/s11259-025-10001-x")

    def test_eoc_never_becomes_a_retraction(self):
        """SourceHit.retraction 非空即被 judge.py 判 RETRACTED——把「期刊存疑、尚未定论」
        说成「已撤稿」是替期刊下结论。"""
        self.assertIsNone(self._hit().retraction)

    def test_eoc_is_reported_under_its_own_metadata_key(self):
        eoc = self._hit().metadata["expression_of_concern"]
        self.assertIn("Lancet", eoc["label"])
        self.assertEqual(eoc["doi"], "10.1016/s0140-6736(26)00123-4")
        self.assertEqual(eoc["pmid"], "42600001")

    def test_key_absent_when_no_notice(self):
        """缺键 = 没查到或没查过，绝不表述为「确认无关注声明」。"""
        client, _ = make([FakeResponse(200, {"esearchresult": {"idlist": ["30000001"]}}),
                          FakeResponse(200, _summary("30000001", ["Journal Article"])),
                          FakeResponse(200, "<PubmedArticleSet/>")],
                         self.tmp.name)
        meta = client.lookup_doi("10.1007/s11259-025-10001-x").metadata
        self.assertNotIn("expression_of_concern", meta)

    def test_eoc_and_retraction_coexist(self):
        """同一篇既被出具关注声明、后又被撤稿：两个事实各自陈列，互不覆盖。"""
        both = _RETRACTION_XML.replace(
            "</CommentsCorrectionsList>",
            '<CommentsCorrections RefType="ExpressionOfConcernIn">'
            "<RefSource>Vet Res Commun. 2026 Jan 5;50(1):9.</RefSource>"
            "<PMID Version=\"1\">42400777</PMID>"
            "</CommentsCorrections></CommentsCorrectionsList>")
        client, _ = make([FakeResponse(200, {"esearchresult": {"idlist": ["42371203"]}}),
                          FakeResponse(200, _summary("42371203",
                                                     ["Retracted Publication"])),
                          FakeResponse(200, both)],
                         self.tmp.name)
        hit = client.lookup_doi("10.1007/s11259-025-10001-x")
        self.assertEqual(hit.retraction["notice_pmid"], "42507066")
        self.assertEqual(hit.metadata["expression_of_concern"]["pmid"], "42400777")


class TestSearchPathCarriesRetraction(unittest.TestCase):
    """检索路径（match/search，医学检索走的就是它）同样要带上撤稿标记。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_search_hits_carry_retraction_and_oa(self):
        client, _ = make([FakeResponse(200, {"esearchresult": {"idlist": ["42371203"]}}),
                          FakeResponse(200, _summary(
                              "42371203", ["Journal Article", "Retracted Publication"],
                              articleids=[{"idtype": "pmc", "value": "PMC9999999"},
                                          {"idtype": "doi",
                                           "value": "10.1007/s11259-025-10001-x"}])),
                          FakeResponse(200, _RETRACTION_XML)],
                         self.tmp.name)
        hits = client.search("retracted vet study")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].retraction["notice_pmid"], "42507066")
        self.assertEqual(hits[0].metadata["oa"]["host"], "pmc")


if __name__ == "__main__":
    unittest.main()