from __future__ import annotations

import json
import pathlib
import tempfile
import unittest
import urllib.parse

from paper_shared.datasources.cache import Cache
from paper_shared.datasources.clients import CLIENT_CLASSES
from paper_shared.datasources.clients.base import (clean_jats_abstract as C,
                                                   normalize_orcid,
                                                   restore_inverted_abstract)
from paper_shared.datasources.clients.crossref import CrossrefClient
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

    def test_no_retraction_on_normal_work(self):
        client, _ = make(OpenAlexClient, "openalex",
                         [FakeResponse(200, load_fixture("openalex_hit.json"))],
                         self.tmp.name)
        self.assertIsNone(client.lookup_doi("10.1038/nature12373").retraction)

    def test_is_retracted_extracted(self):
        """OpenAlex is_retracted → retraction，给撤稿检测加一路不依赖 Crossref 的冗余。"""
        client, _ = make(OpenAlexClient, "openalex",
                         [FakeResponse(200, load_fixture("openalex_retracted.json"))],
                         self.tmp.name)
        hit = client.lookup_doi("10.5555/retracted-example")
        self.assertIsNotNone(hit.retraction)
        self.assertEqual(hit.retraction["type"], "retraction")
        self.assertEqual(hit.retraction["source"], "openalex")
        # 布尔标记而已：无撤稿日期、无撤稿声明 DOI，不可伪造
        self.assertIsNone(hit.retraction["date_parts"])
        self.assertIsNone(hit.retraction["doi"])


class TestInvertedAbstract(unittest.TestCase):
    """OpenAlex 只给 abstract_inverted_index，摘要要按位置铺回原序。"""

    def test_restores_word_order(self):
        idx = {"the": [0, 3], "cat": [1], "sat": [2], "mat": [4]}
        self.assertEqual(restore_inverted_abstract(idx), "the cat sat the mat")

    def test_position_order_not_dict_order(self):
        # 键的插入序与位置序无关，还原必须按位置排，不能靠 dict 顺序
        self.assertEqual(restore_inverted_abstract({"world": [1], "hello": [0]}),
                         "hello world")

    def test_gap_is_skipped_not_padded(self):
        """位置有洞（源数据缺词）时跳过、不填占位符——宁可句子短一截，不编内容。"""
        self.assertEqual(restore_inverted_abstract({"a": [0], "c": [5]}), "a c")

    def test_empty_and_none(self):
        for bad in (None, {}, {"w": []}, {"w": None}):
            self.assertIsNone(restore_inverted_abstract(bad))

    def test_illegal_positions_ignored(self):
        # 负数 / 非整数 / bool 都不是位置；全非法等同没给摘要
        self.assertIsNone(restore_inverted_abstract({"a": [-1], "b": ["x"], "c": [True]}))

    def test_non_dict_input(self):
        self.assertIsNone(restore_inverted_abstract("not an index"))


class TestOpenAlexAuthorSearch(unittest.TestCase):
    """作者检索（capability: search_author）。只有 OpenAlex 提供免费作者实体端点。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _client(self, script):
        return make(OpenAlexClient, "openalex", script, self.tmp.name)

    def test_capability_declared_in_registry(self):
        self.assertIn("search_author", Registry.load().get("openalex").capabilities)

    def test_parses_candidate_and_reports_total(self):
        body = {"meta": {"count": 33}, "results": [{
            "id": "https://openalex.org/A5100765488",
            "display_name": "Shenghua Zhou",
            "orcid": "https://orcid.org/0000-0003-3871-9099",
            "works_count": 99,
            "affiliations": [{"institution": {"display_name": "Shanghai University"},
                              "years": [2025, 2024]}],
            "last_known_institutions": [{"display_name": "Jiangsu University of Technology"}],
            "topics": [{"display_name": "Membrane Separation Technologies"}],
            "display_name_alternatives": ["S. Zhou", "Zhou, Shenghua"],
        }]}
        client, _ = self._client([FakeResponse(200, body)])
        cands, total = client.find_authors("Shenghua Zhou", limit=5)
        # total 与 len(cands) 分开记：实测 "Wei Wang" 有 9757 个候选，必须截断呈现
        self.assertEqual(total, 33)
        c = cands[0]
        self.assertEqual(c.entity_ids, ["A5100765488"])
        self.assertEqual(c.orcid, "0000-0003-3871-9099")
        # 历年 affiliations（带年份），不是 last_known_institutions——后者实测常年失准
        self.assertEqual(c.affiliations, [{"name": "Shanghai University",
                                           "years": [2025, 2024]}])
        self.assertEqual(c.topics, ["Membrane Separation Technologies"])
        self.assertTrue(c.exact_name_match)

    def test_fuzzy_name_flagged_not_filtered(self):
        """实测搜「周生华」会返回「周华生」。如实标记，但**不替调用方滤掉**——
        英文库里中文名的姓名顺序本就混乱，滤掉就是替用户做判断。"""
        body = {"meta": {"count": 2}, "results": [
            {"id": "https://openalex.org/A1", "display_name": "周生华", "works_count": 8},
            {"id": "https://openalex.org/A2", "display_name": "周华生", "works_count": 1}]}
        client, _ = self._client([FakeResponse(200, body)])
        cands, _ = client.find_authors("周生华")
        self.assertEqual(len(cands), 2)                       # 没被滤掉
        self.assertEqual([c.exact_name_match for c in cands], [True, False])

    def test_works_by_author_prefers_orcid_filter(self):
        """有 ORCID 就必须用 author.orcid 过滤：它在 works 层生效，能穿透源的实体拆分
        （实测 105 篇 = 被拆开的 99 + 6），按 author.id 查会漏掉一整块。"""
        client, transport = self._client([FakeResponse(200, {"results": []})])
        client.works_by_author(orcid="0000-0003-3871-9099", entity_id="A5041699772")
        url = transport._opener.calls[-1][0]
        self.assertIn("author.orcid:0000-0003-3871-9099", urllib.parse.unquote(url))
        self.assertNotIn("author.id:", urllib.parse.unquote(url))

    def test_works_by_author_falls_back_to_entity_id(self):
        client, transport = self._client([FakeResponse(200, {"results": []})])
        client.works_by_author(entity_id="A5041699772")
        self.assertIn("author.id:A5041699772",
                      urllib.parse.unquote(transport._opener.calls[-1][0]))

    def test_works_by_author_requires_a_key(self):
        client, _ = self._client([])
        with self.assertRaises(ValueError):
            client.works_by_author()

    def test_year_filter_merges_into_same_filter_segment(self):
        """筛选要并进同一个 filter 段（逗号 = AND），另起 &filter= 会被服务端覆盖掉。"""
        client, transport = self._client([FakeResponse(200, {"results": []})])
        client.works_by_author(orcid="0000-0003-3871-9099", filters={"year_from": 2020})
        url = urllib.parse.unquote(transport._opener.calls[-1][0])
        self.assertEqual(url.count("filter="), 1)
        self.assertIn("author.orcid:0000-0003-3871-9099,from_publication_date:2020-01-01", url)


class TestOrcidNormalization(unittest.TestCase):
    """各源给的 ORCID 是完整 URI 且 scheme 不一，必须剥成裸 ID 才跨源比得起来。"""

    def test_strips_https_and_http_prefix(self):
        # OpenAlex 给 https、Crossref 给 http（历史形式），归一后必须相同
        for raw in ("https://orcid.org/0000-0002-1825-0097",
                    "http://orcid.org/0000-0002-1825-0097",
                    "0000-0002-1825-0097"):
            self.assertEqual(normalize_orcid(raw), "0000-0002-1825-0097")

    def test_checksum_x_is_kept_and_uppercased(self):
        # 末位校验位可能是 X，小写形式也要认
        self.assertEqual(normalize_orcid("https://orcid.org/0000-0002-1694-233x"),
                         "0000-0002-1694-233X")

    def test_unrecognized_returns_none(self):
        for bad in (None, "", "   ", "not-an-orcid", "0000-0002-1825", "12345"):
            self.assertIsNone(normalize_orcid(bad))


class TestAuthorDetails(unittest.TestCase):
    """作者标识只做提取与陈列，不做任何跨作者归并（消歧归用户，见 SKILL.md）。"""

    def test_openalex_extracts_orcid_and_affiliations(self):
        w = {"authorships": [
            {"author": {"display_name": "Yann LeCun",
                        "orcid": "https://orcid.org/0000-0002-1825-0097"},
             "institutions": [{"display_name": "New York University"},
                              {"display_name": "Meta AI"}]},
        ]}
        d = OpenAlexClient._author_details(w)[0]
        self.assertEqual(d["name"], "Yann LeCun")
        self.assertEqual(d["orcid"], "0000-0002-1825-0097")
        # 机构全留、不截断——呈现层要几个自己取
        self.assertEqual(d["affiliations"], ["New York University", "Meta AI"])
        # OpenAlex 不透出验证状态 → None（未知），不能假装成 False
        self.assertIsNone(d["orcid_verified"])

    def test_empty_when_no_author_carries_any_identifier(self):
        """全员无 ORCID 无机构 → []，不返回一串空壳。

        空壳会让下游把「源没给标识」显示成「这个人没有 ORCID」。
        """
        w = {"authorships": [{"author": {"display_name": "张三"}, "institutions": []},
                             {"author": {"display_name": "李四"}}]}
        self.assertEqual(OpenAlexClient._author_details(w), [])

    def test_openalex_skips_nameless_author_slot(self):
        w = {"authorships": [{"author": {}, "institutions": [{"display_name": "X"}]},
                             {"author": {"display_name": "王五"},
                              "institutions": [{"display_name": "Y"}]}]}
        out = OpenAlexClient._author_details(w)
        self.assertEqual([d["name"] for d in out], ["王五"])

    def test_crossref_authenticated_orcid_is_tristate(self):
        """authenticated-orcid 是全部源里唯一的「经作者本人验证」信号，三态不能压平。"""
        msg = {"author": [
            {"given": "A", "family": "One", "ORCID": "http://orcid.org/0000-0002-1825-0097",
             "authenticated-orcid": True},
            {"given": "B", "family": "Two", "ORCID": "http://orcid.org/0000-0001-5109-3700",
             "authenticated-orcid": False},
            {"given": "C", "family": "Three", "ORCID": "http://orcid.org/0000-0002-1694-233X"},
        ]}
        out = CrossrefClient._author_details(msg)
        self.assertEqual([d["orcid_verified"] for d in out], [True, False, None])

    def test_crossref_institutional_author_without_name_skipped(self):
        # 机构作者只有 name 字段、没有 given/family
        msg = {"author": [{"name": "WHO Collaborating Group",
                           "affiliation": [{"name": "WHO"}]},
                          {"given": "D", "family": "Four", "affiliation": [{"name": "MIT"}]}]}
        out = CrossrefClient._author_details(msg)
        self.assertEqual([d["name"] for d in out], ["D Four"])

    def test_crossref_authors_list_unchanged_by_details(self):
        """`authors`（List[str]）是既有契约，matching.py 拿 authors[0] 比对第一作者——
        加 author_details 绝不能改它的形状。"""
        msg = {"title": ["T"], "author": [{"given": "E", "family": "Five"}]}
        self.assertEqual(CrossrefClient._metadata(msg)["authors"], ["E Five"])


class TestJatsAbstract(unittest.TestCase):
    """Crossref 的 abstract 是 JATS XML 片段。全部用例取自真实响应形态（DOI 见注释）。"""

    def test_simple_paragraph(self):
        self.assertEqual(C("<jats:p>E-commerce websites are widely used.</jats:p>"),
                         "E-commerce websites are widely used.")

    def test_prefix_is_not_always_jats(self):
        """实测同一字段出现过 jats:p、无前缀的 p、以及 ns3:p 三种写法，且都不声明 xmlns
        ——直接喂 ET.fromstring 会报 unbound prefix。所以统一剥前缀，不声明某个命名空间。"""
        for raw in ("<jats:p>Body text.</jats:p>", "<p>Body text.</p>",
                    "<ns3:p>Body text.</ns3:p>"):
            self.assertEqual(C(raw), "Body text.")

    def test_inline_tags_do_not_truncate(self):
        # 只取 .text 会在第一个行内标签处截断，把摘要砍掉半句
        self.assertEqual(C("<jats:p>Ratio <jats:italic>k</jats:italic> at <jats:sup>2</jats:sup> m.</jats:p>"),
                         "Ratio k at 2 m.")

    def test_abstract_label_dropped_body_kept(self):
        # 「Abstract」是标签不是内容（实测 61/240 条带它）
        self.assertEqual(C("<jats:title>Abstract</jats:title>\n<jats:p>Real body.</jats:p>"),
                         "Real body.")

    def test_only_abstract_label_is_no_abstract(self):
        self.assertIsNone(C("<jats:title>Abstract</jats:title>"))

    def test_structured_sections_keep_their_titles(self):
        """结构化摘要拼成 `Methods: …`，与 PubMed efetch 同一口径（10.1093/tropej/fmab009）。"""
        raw = ("<jats:title>Abstract</jats:title><jats:sec><jats:title>Introduction</jats:title>"
               "<jats:p>Birth asphyxia may cause impairment.</jats:p></jats:sec>"
               "<jats:sec><jats:title>Objective</jats:title>"
               "<jats:p>To assess music therapy.</jats:p></jats:sec>")
        self.assertEqual(C(raw), "Introduction: Birth asphyxia may cause impairment. "
                                 "Objective: To assess music therapy.")

    def test_bare_text_is_not_lost(self):
        """有出版商直接投递纯文本。只遍历子元素会把整段摘要丢成 None。"""
        self.assertEqual(C("Just plain text, no markup."), "Just plain text, no markup.")
        self.assertEqual(C("Lead. <jats:p>Middle.</jats:p> Trail."), "Lead. Middle. Trail.")

    def test_double_escaped_tag(self):
        """10.5539/hes.v6n3p72：出版商把 HTML 的 <p> 转义成 &lt;p&gt; 塞进 <jats:p>。
        XML 解析忠实还原成字面 "<p>"（语义上正确），但字面标签会破 markdown 表格、
        进 HTML 视图会真的插进 DOM，所以要在输出边界再剥一道。"""
        self.assertEqual(C("<jats:p>&lt;p&gt;The main aim is a model.&lt;/p&gt;</jats:p>"),
                         "The main aim is a model.")

    def test_double_escaped_entities(self):
        # 10.47310/jpms202514s0159（&amp;amp;）与 10.2196/preprints.65269（&amp;lt;）
        self.assertEqual(C("<jats:p>Background &amp;amp; Objectives: ok.</jats:p>"),
                         "Background & Objectives: ok.")
        self.assertEqual(C("<jats:p>Correlation (P &amp;lt;.001) held.</jats:p>"),
                         "Correlation (P <.001) held.")

    def test_math_comparators_survive(self):
        """摘要里的 `p < 0.05` 是正文，不是标签——曾用「含任何 `<` 就判脏」，会整条丢掉。"""
        self.assertEqual(C("<jats:p>Significant at p &lt; 0.05 here.</jats:p>"),
                         "Significant at p < 0.05 here.")

    def test_malformed_fallback_keeps_content(self):
        """降级路径不许静默吞正文。贪婪的 `<[^>]*>` 会从 `<` 一路吃到下一个 `>`，
        把 "0.05 with unclosed" 整段吞掉——静默残缺比留个孤立尖括号有害得多。"""
        out = C("<jats:p>Significant at p < 0.05 with unclosed <jats:bold>bold")
        self.assertIn("0.05", out)
        self.assertIn("unclosed", out)
        self.assertNotIn("jats:", out)

    def test_punctuation_only_is_no_abstract(self):
        """10.18502/kss.v3i6.2443 投递的 abstract 就是一个句点。把它当摘要交给三格起草档
        等于请 AI 对着句点编方法学。判据是「有没有词」，不是主观长度阈值。"""
        self.assertIsNone(C("<jats:p>.</jats:p>"))
        self.assertIsNone(C("<jats:p>  --- 123 ---  </jats:p>"))

    def test_cjk_counts_as_meaningful(self):
        self.assertEqual(C("<jats:p>本文研究技术接受模型。</jats:p>"), "本文研究技术接受模型。")

    def test_empty_inputs(self):
        for bad in (None, "", "   \n  ", 123):
            self.assertIsNone(C(bad))

    def test_crossref_metadata_wires_it_up(self):
        client, _ = make(CrossrefClient, "crossref",
                         [FakeResponse(200, {"message": {
                             "DOI": "10.1/a", "title": ["T"], "author": [],
                             "issued": {"date-parts": [[2020]]}, "type": "journal-article",
                             "is-referenced-by-count": 7,
                             "abstract": "<jats:p>Clean body here.</jats:p>"}})],
                         self.tmp.name)
        hit = client.lookup_doi("10.1/a")
        self.assertEqual(hit.metadata["abstract"], "Clean body here.")
        self.assertEqual(hit.metadata["cited_by_count"], 7)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()


class TestOpenAlexSnowball(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _work(**kw):
        w = {"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/seed",
             "display_name": "Seed", "publication_year": 2020, "type": "article"}
        w.update(kw)
        return w

    @staticmethod
    def _results(*titles):
        return {"results": [{"id": f"https://openalex.org/W{i}", "display_name": t,
                             "publication_year": 2010 + i, "cited_by_count": i}
                            for i, t in enumerate(titles, start=10)]}

    def test_references_two_hops(self):
        """后向是两跳：referenced_works 只给 ID，题录要再批量取一次。"""
        client, transport = make(
            OpenAlexClient, "openalex",
            [FakeResponse(200, self._work(referenced_works=["https://openalex.org/W10",
                                                            "https://openalex.org/W11"])),
             FakeResponse(200, self._results("经典甲", "经典乙"))],
            self.tmp.name)
        hits = client.references("10.1/seed")
        self.assertEqual([h.metadata["title"] for h in hits], ["经典甲", "经典乙"])
        # 第二跳用短 ID 的 OR 过滤，不是逐条查（`|` 保持裸字符，OpenAlex 文档即此写法）
        self.assertIn("filter=openalex_id:W10|W11", transport._opener.calls[1][0])

    def test_references_batches_over_or_limit(self):
        """`filter=openalex_id:` 的 OR 上限是 50，参考文献常超过——必须分批。"""
        ids = [f"https://openalex.org/W{i}" for i in range(60)]
        client, transport = make(
            OpenAlexClient, "openalex",
            [FakeResponse(200, self._work(referenced_works=ids)),
             FakeResponse(200, self._results(*[f"t{i}" for i in range(50)])),
             FakeResponse(200, self._results(*[f"t{i}" for i in range(10)]))],
            self.tmp.name)
        hits = client.references("10.1/seed", limit=60)
        self.assertEqual(len(hits), 60)
        self.assertEqual(len(transport._opener.calls), 3)     # 1 跳 + 2 批

    def test_references_respects_limit(self):
        ids = [f"https://openalex.org/W{i}" for i in range(60)]
        client, transport = make(
            OpenAlexClient, "openalex",
            [FakeResponse(200, self._work(referenced_works=ids)),
             FakeResponse(200, self._results("只要两条", "第二条"))],
            self.tmp.name)
        client.references("10.1/seed", limit=2)
        self.assertIn("openalex_id:W0|W1&", transport._opener.calls[1][0])

    def test_references_empty_when_none_recorded(self):
        client, transport = make(OpenAlexClient, "openalex",
                                 [FakeResponse(200, self._work())], self.tmp.name)
        self.assertEqual(client.references("10.1/seed"), [])
        self.assertEqual(len(transport._opener.calls), 1)     # 没有第二跳

    def test_cited_by_uses_short_id(self):
        client, transport = make(
            OpenAlexClient, "openalex",
            [FakeResponse(200, self._work()),
             FakeResponse(200, self._results("新跟进"))],
            self.tmp.name)
        hits = client.cited_by("10.1/seed")
        self.assertEqual(hits[0].metadata["title"], "新跟进")
        self.assertIn("filter=cites:W1", transport._opener.calls[1][0])

    def test_snowball_reuses_lookup_cache_key(self):
        """第一跳与 lookup_doi 共用缓存键：先 lookup 再滚雪球不该重打第一跳。"""
        client, transport = make(
            OpenAlexClient, "openalex",
            [FakeResponse(200, self._work(referenced_works=["https://openalex.org/W10"])),
             FakeResponse(200, self._results("经典甲"))],
            self.tmp.name)
        client.lookup_doi("10.1/seed")
        client.references("10.1/seed")
        self.assertEqual(len(transport._opener.calls), 2)   # 不是 3


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

    def test_requests_citation_count_and_abstract(self):
        client, transport = make(SemanticScholarClient, "semantic_scholar",
                                 [FakeResponse(200, load_fixture("s2_hit.json"))],
                                 self.tmp.name)
        client.lookup_doi("10.1038/nature12373")
        url = transport._opener.calls[0][0]
        self.assertIn("citationCount", url)
        self.assertIn("abstract", url)

    def test_cache_key_is_fields_versioned(self):
        """缓存键不含 fields，而 fields 是 URL 的一部分。扩了字段却不换键，旧缓存会照命中
        并回缺字段的 payload——用户看到「一部分条目有被引数、一部分没有」且查不出原因。"""
        client, _ = make(SemanticScholarClient, "semantic_scholar",
                         [FakeResponse(200, {"title": "T", "year": 2020,
                                             "citationCount": 5})],
                         self.tmp.name)
        client.lookup_doi("10.1038/nature12373")
        keys = []
        with client.cache._conn() as c:
            keys = [r[0] for r in c.execute("SELECT key FROM cache")]
        self.assertTrue(keys)
        # 老键（无版本段）不得命中：换了 fields 就该让老缓存自然作废
        self.assertNotIn("doi:10.1038/nature12373", keys)
        self.assertTrue(any(k.startswith("doi:10.1038/nature12373:") for k in keys))

    def test_snowball_unwraps_edge_objects(self):
        """S2 的两向响应是**边**对象，题录裹在 citedPaper / citingPaper 里，要剥一层。"""
        client, transport = make(
            SemanticScholarClient, "semantic_scholar",
            [FakeResponse(200, {"data": [
                {"citedPaper": {"title": "经典甲", "year": 1989, "citationCount": 900}},
                {"citedPaper": {"paperId": None}},       # 已知存在但未收录元数据
            ]})],
            self.tmp.name)
        hits = client.references("10.1/seed")
        self.assertEqual([h.metadata["title"] for h in hits], ["经典甲"])   # 空壳被跳过
        self.assertEqual(hits[0].metadata["cited_by_count"], 900)
        self.assertIn("/references", transport._opener.calls[0][0])

    def test_cited_by_uses_citations_endpoint(self):
        client, transport = make(
            SemanticScholarClient, "semantic_scholar",
            [FakeResponse(200, {"data": [{"citingPaper": {"title": "新跟进", "year": 2026}}]})],
            self.tmp.name)
        hits = client.cited_by("10.1/seed")
        self.assertEqual(hits[0].metadata["title"], "新跟进")
        self.assertIn("/citations", transport._opener.calls[0][0])

    def test_snowball_limit_capped_at_api_max(self):
        # S2 的 limit 上限 1000，超了它自己报 400——夹住而不是把错误甩给用户
        client, transport = make(SemanticScholarClient, "semantic_scholar",
                                 [FakeResponse(200, {"data": []})], self.tmp.name)
        client.references("10.1/seed", limit=99999)
        self.assertIn("limit=1000", transport._opener.calls[0][0])


if __name__ == "__main__":
    unittest.main()
