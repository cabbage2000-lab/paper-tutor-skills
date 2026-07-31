"""paper-search scripts/search.py 的确定性逻辑单测：去重 / 排序 / 分页 / 组装。

导入范式同 tests/paper-doctor/test_doctor.py（sys.path 加 _shared 与 skill scripts 后 import）。
验证外部可观察行为，不测实现细节。
"""
from __future__ import annotations

import pathlib
import sys
import unittest

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "_shared"))
sys.path.insert(0, str(_REPO / "skills" / "paper-search" / "scripts"))

import render_html  # noqa: E402
import search  # noqa: E402

from paper_shared.datasources.models import Evidence, Ref, SearchResult, SourceHit  # noqa: E402


_UNSET = object()


def _hit(source, doi=None, title="T", year=2020, typ="journal-article", venue="V",
         from_cache=False, date=None, cited=_UNSET, abstract=_UNSET, direction=None,
         details=_UNSET):
    """cited / abstract / details 默认**不设键**（模拟 arxiv、pubmed 这类不给该字段的源）。
    显式传 None 与不传是两种情形，测试要能分开构造。"""
    meta = {"title": title, "doi": doi, "year": year, "venue": venue,
            "type": typ, "authors": ["X"], "date": date}
    if cited is not _UNSET:
        meta["cited_by_count"] = cited
    if abstract is not _UNSET:
        meta["abstract"] = abstract
    if details is not _UNSET:
        meta["author_details"] = details
    if direction:
        meta["snowball_direction"] = direction
    return SourceHit(source=source, metadata=meta,
                     fetched_at="2026-01-01T00:00:00Z", from_cache=from_cache)


class TestDedup(unittest.TestCase):
    def test_same_doi_merged_authority_order(self):
        # 大小写不同的同一 DOI，normalize 后归并；主源取权威序最高的 crossref
        items = [_hit("openalex", doi="10.1/a"), _hit("crossref", doi="10.1/A")]
        m = search.dedup_hits(items)
        self.assertEqual(len(m), 1)
        self.assertEqual(set(m[0]["sources"]), {"crossref", "openalex"})
        self.assertEqual(m[0]["primary_source"], "crossref")

    def test_no_doi_same_title_merged(self):
        items = [_hit("arxiv", doi=None, title="Deep Learning!"),
                 _hit("eric", doi=None, title="deep  learning")]
        self.assertEqual(len(search.dedup_hits(items)), 1)

    def test_different_doi_not_merged(self):
        items = [_hit("crossref", doi="10.1/a"), _hit("crossref", doi="10.2/b")]
        self.assertEqual(len(search.dedup_hits(items)), 2)

    def test_no_doi_no_title_independent(self):
        items = [_hit("arxiv", doi=None, title=None), _hit("arxiv", doi=None, title=None)]
        self.assertEqual(len(search.dedup_hits(items)), 2)

    def test_url_from_doi(self):
        m = search.dedup_hits([_hit("crossref", doi="10.1/a")])
        self.assertEqual(m[0]["url"], "https://doi.org/10.1/a")


def _det(name, orcid=None, affs=None):
    return {"name": name, "orcid": orcid, "affiliations": affs or [], "orcid_verified": None}


class TestAuthorDetailsMerge(unittest.TestCase):
    """作者标识跨源合并。核心不变量：取覆盖最好的源，且整份取、绝不跨源拼。"""

    def test_richer_source_wins_over_authority_order(self):
        """实测 crossref 的 ORCID 覆盖 4%、openalex 78%，而 crossref 权威序最高——
        按权威序取会让绝大多数条目的 ORCID 凭空消失。"""
        items = [_hit("crossref", doi="10.1/a", details=[_det("A")]),
                 _hit("openalex", doi="10.1/a",
                      details=[_det("A", "0000-0002-1825-0097", ["NYU"])])]
        m = search.dedup_hits(items)[0]
        self.assertEqual(m["primary_source"], "crossref")      # 题录仍归主源
        self.assertEqual(m["author_details_source"], "openalex")
        self.assertEqual(m["author_details"][0]["orcid"], "0000-0002-1825-0097")

    def test_empty_details_do_not_shadow_a_populated_source(self):
        # crossref 权威序更高但给了空列表，不能盖掉 openalex 真有的内容
        items = [_hit("crossref", doi="10.1/a", details=[]),
                 _hit("openalex", doi="10.1/a", details=[_det("A", affs=["NYU"])])]
        m = search.dedup_hits(items)[0]
        self.assertEqual(m["author_details_source"], "openalex")

    def test_none_when_no_source_gives_identifiers(self):
        # null = 各源都没给标识，与「这些作者没有 ORCID」是两件事
        m = search.dedup_hits([_hit("arxiv", doi="10.1/a")])[0]
        self.assertIsNone(m["author_details"])
        self.assertIsNone(m["author_details_source"])

    def test_tie_broken_by_authority_order_reproducibly(self):
        # 带 ORCID 数相同 → 权威序在前的胜出，结果可复现
        items = [_hit("openalex", doi="10.1/a", details=[_det("A", "0000-0002-1825-0097")]),
                 _hit("crossref", doi="10.1/a", details=[_det("A", "0000-0001-5109-3700")])]
        m = search.dedup_hits(items)[0]
        self.assertEqual(m["author_details_source"], "crossref")

    def test_taken_whole_never_spliced_across_sources(self):
        """整份取、不跨源拼：按名字把两个源的标识拼起来，就是在判定「这两条是不是同一个
        人」——那是 L2/L3 的事，本层不做。"""
        items = [_hit("crossref", doi="10.1/a", details=[_det("A", "0000-0002-1825-0097")]),
                 _hit("openalex", doi="10.1/a", details=[_det("A"), _det("B", affs=["MIT"])])]
        m = search.dedup_hits(items)[0]
        # crossref 那份带 1 个 ORCID 胜出，openalex 的 B 与机构不会被拼进来
        self.assertEqual([d["name"] for d in m["author_details"]], ["A"])


def _cand(name="Shenghua Zhou", orcid=None, eid="A1", works=10, aff=None, topics=None,
          exact=True):
    from paper_shared.datasources.models import AuthorCandidate
    return AuthorCandidate(
        source="openalex", name=name, entity_ids=[eid], orcid=orcid, works_count=works,
        affiliations=[{"name": a, "years": [2024]} for a in (aff or [])],
        topics=list(topics or []), name_variants=[], exact_name_match=exact)


class TestAuthorCandidateMerge(unittest.TestCase):
    """同名候选归并。核心不变量：ORCID 是唯一允许的归并键。"""

    def test_same_orcid_merged_across_entities(self):
        """源会把同一个人拆开：实测 0000-0003-3871-9099 → 99 篇 + 6 篇两个实体。
        不合并会让用户以为是两个人。"""
        out = search.merge_author_candidates([
            _cand(orcid="0000-0003-3871-9099", eid="A5100765488", works=99,
                  aff=["Planetary Science Institute"]),
            _cand(orcid="0000-0003-3871-9099", eid="A5041699772", works=6,
                  aff=["University of Hong Kong"]),
        ])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["merged_entities"], 2)
        # 实体间不重叠，加总即真实篇数（99 + 6 = 105 = 按 ORCID 过滤的总数）
        self.assertEqual(out[0]["works_count"], 105)
        self.assertEqual(out[0]["entity_ids"], ["A5100765488", "A5041699772"])
        self.assertEqual([a["name"] for a in out[0]["affiliations"]],
                         ["Planetary Science Institute", "University of Hong Kong"])

    def test_different_orcid_never_merged(self):
        out = search.merge_author_candidates([
            _cand(orcid="0000-0001-5388-7766", eid="A1"),
            _cand(orcid="0000-0002-0404-5260", eid="A2"),
        ])
        self.assertEqual(len(out), 2)

    def test_no_orcid_stays_independent_even_if_same_name_and_place(self):
        """同名 + 同机构 + 同领域也不合并——那是概率推断，判错会把别人的成果算到某人头上。
        实测 "Shenghua Zhou" 有 4 个不同 ORCID 的人同在中南大学。"""
        out = search.merge_author_candidates([
            _cand(eid="A1", aff=["Central South University"], topics=["Cardiology"]),
            _cand(eid="A2", aff=["Central South University"], topics=["Cardiology"]),
        ])
        self.assertEqual(len(out), 2)
        self.assertTrue(all(c["merged_entities"] == 1 for c in out))

    def test_works_key_prefers_orcid(self):
        """ORCID 能穿透源的实体拆分，有就必须用它——按实体查会漏掉一整块。"""
        out = search.merge_author_candidates([_cand(orcid="0000-0001-5388-7766", eid="A9"),
                                              _cand(eid="A8")])
        keys = {c["works_key"] for c in out}
        self.assertEqual(keys, {"orcid:0000-0001-5388-7766", "entity:A8"})

    def test_sorted_by_works_count_reproducibly(self):
        out = search.merge_author_candidates([_cand(eid="A1", works=5, name="B"),
                                              _cand(eid="A2", works=99, name="A")])
        self.assertEqual([c["works_count"] for c in out], [99, 5])

    def test_any_exact_match_makes_the_merged_row_exact(self):
        out = search.merge_author_candidates([
            _cand(orcid="0000-0001-5388-7766", eid="A1", exact=False),
            _cand(orcid="0000-0001-5388-7766", eid="A2", exact=True)])
        self.assertTrue(out[0]["exact_name_match"])


class TestAuthorKeyParsing(unittest.TestCase):
    def test_four_accepted_forms(self):
        self.assertEqual(search.parse_author_key("orcid:0000-0002-1825-0097"),
                         ("0000-0002-1825-0097", None))
        self.assertEqual(search.parse_author_key("entity:A5041699772"),
                         (None, "A5041699772"))
        # 裸 ORCID：用户多半直接粘
        self.assertEqual(search.parse_author_key("0000-0002-1825-0097"),
                         ("0000-0002-1825-0097", None))
        self.assertEqual(search.parse_author_key("A5041699772"), (None, "A5041699772"))

    def test_blank_is_rejected(self):
        self.assertEqual(search.parse_author_key("   "), (None, None))


class TestAuthorWarnings(unittest.TestCase):
    """四条如实声明，每条对应一个会让用户误判的真实陷阱。"""

    def _cands(self, **kw):
        return search.merge_author_candidates([_cand(**kw)])

    def test_truncation_declared(self):
        # 实测 "Wei Wang" 有 9757 个候选，截断必须说清楚
        w = search.author_warnings("Wei Wang", self._cands(orcid="0000-0001-5388-7766"),
                                   9757, 1)
        self.assertTrue(any("9757" in x for x in w))

    def test_approximate_name_declared(self):
        """实测搜「周生华」会返回「周华生」——字序颠倒的另一个人。"""
        w = search.author_warnings("周生华", self._cands(name="周华生", exact=False,
                                                       orcid="0000-0001-5388-7766"), 1, 1)
        self.assertTrue(any("周华生" in x for x in w))

    def test_missing_orcid_declared(self):
        w = search.author_warnings("X", self._cands(), 1, 1)
        self.assertTrue(any("没有 ORCID" in x for x in w))

    def test_split_entity_merge_declared(self):
        cands = search.merge_author_candidates([
            _cand(orcid="0000-0003-3871-9099", eid="A1", works=99),
            _cand(orcid="0000-0003-3871-9099", eid="A2", works=6)])
        w = search.author_warnings("X", cands, 2, 1)
        self.assertTrue(any("多个作者实体" in x for x in w))

    def test_entity_key_lookup_declares_possible_incompleteness(self):
        """按实体 ID 取论文只覆盖一个实体，可能不是全部——必须说。有 ORCID 时不必。"""
        self.assertTrue(search.author_works_warnings(None))
        self.assertEqual(search.author_works_warnings("0000-0003-3871-9099"), [])


class TestCitedByMerge(unittest.TestCase):
    """被引数跨源合并。核心不变量：缺失 ≠ 0——「源不给这个数」不能显示成「零被引」。"""

    def test_takes_max_and_records_source(self):
        # 各库口径不同（Crossref 只数注册 DOI 的引用，S2 收灰色文献），取最大是下界陈述
        items = [_hit("crossref", doi="10.1/a", cited=10),
                 _hit("semantic_scholar", doi="10.1/a", cited=42)]
        m = search.dedup_hits(items)[0]
        self.assertEqual(m["cited_by_count"], 42)
        self.assertEqual(m["cited_by_source"], "semantic_scholar")

    def test_missing_stays_none_not_zero(self):
        # arxiv 不设该键 → 合并后仍是 None，绝不落成 0
        m = search.dedup_hits([_hit("arxiv", doi="10.1/a")])[0]
        self.assertIsNone(m["cited_by_count"])
        self.assertIsNone(m["cited_by_source"])

    def test_real_zero_is_kept(self):
        # 真实的 0（确实零被引）要留住，不能被当成缺失丢掉
        m = search.dedup_hits([_hit("crossref", doi="10.1/a", cited=0)])[0]
        self.assertEqual(m["cited_by_count"], 0)
        self.assertEqual(m["cited_by_source"], "crossref")

    def test_missing_source_does_not_beat_present(self):
        items = [_hit("arxiv", doi="10.1/a"), _hit("openalex", doi="10.1/a", cited=7)]
        m = search.dedup_hits(items)[0]
        self.assertEqual(m["cited_by_count"], 7)

    def test_bool_is_not_a_count(self):
        # bool 是 int 的子类：True 不能被当成被引数 1
        m = search.dedup_hits([_hit("crossref", doi="10.1/a", cited=True)])[0]
        self.assertIsNone(m["cited_by_count"])


class TestAbstractMerge(unittest.TestCase):
    def test_falls_back_to_other_source(self):
        """Crossref 为主源但本项目不解析它的摘要——必须能从别的源补，否则起草档少一批条目。"""
        items = [_hit("crossref", doi="10.1/a", abstract=None),
                 _hit("openalex", doi="10.1/a", abstract="真实摘要")]
        m = search.dedup_hits(items)[0]
        self.assertEqual(m["abstract"], "真实摘要")
        self.assertEqual(m["abstract_source"], "openalex")
        self.assertEqual(m["primary_source"], "crossref")   # 题录仍归权威源

    def test_authority_order_wins_among_present(self):
        items = [_hit("semantic_scholar", doi="10.1/a", abstract="S2 摘要"),
                 _hit("openalex", doi="10.1/a", abstract="OA 摘要")]
        self.assertEqual(search.dedup_hits(items)[0]["abstract_source"], "openalex")

    def test_blank_counts_as_missing(self):
        items = [_hit("crossref", doi="10.1/a", abstract="   "),
                 _hit("openalex", doi="10.1/a", abstract="真实摘要")]
        self.assertEqual(search.dedup_hits(items)[0]["abstract"], "真实摘要")

    def test_none_when_no_source_has_one(self):
        m = search.dedup_hits([_hit("arxiv", doi="10.1/a")])[0]
        self.assertIsNone(m["abstract"])
        self.assertIsNone(m["abstract_source"])


class TestSnowballDirections(unittest.TestCase):
    def test_both_directions_kept_when_mutually_cited(self):
        """同一篇既是参考文献又是被引文献时，两向都留——「它引的」与「引它的」是两件事。"""
        items = [_hit("openalex", doi="10.1/a", direction="references"),
                 _hit("semantic_scholar", doi="10.1/a", direction="cited_by")]
        m = search.dedup_hits(items)[0]
        self.assertEqual(sorted(m["snowball_directions"]), ["cited_by", "references"])

    def test_absent_key_for_plain_search(self):
        # 普通检索结果不带这个键，笔记表不该凭空多一列
        self.assertNotIn("snowball_directions", search.dedup_hits([_hit("crossref")])[0])


class TestAdvisories(unittest.TestCase):
    """分布 advisory：给比例与证据，不给结论（红线 1 的量化形态）。"""

    @staticmethod
    def _rows(n, **kw):
        base = {"year": 2020, "venue": "V", "type": "journal-article",
                "primary_source": "crossref"}
        base.update(kw)
        return [dict(base) for _ in range(n)]

    def test_fires_at_threshold(self):
        # 7/10 = 70%，正好达阈值即触发
        rows = self._rows(7) + [dict(year=1990 + i * 6, venue=f"W{i}", type="book",
                                     primary_source="openalex") for i in range(3)]
        dims = {a["dimension"]: a for a in search.distribution_advisories(rows)}
        self.assertIn("发表期刊 / 来源", dims)
        self.assertEqual(dims["发表期刊 / 来源"]["pct"], 70)
        self.assertEqual(dims["发表期刊 / 来源"]["count"], 7)

    def test_silent_below_threshold(self):
        rows = self._rows(6) + [dict(year=1990 + i * 6, venue=f"W{i}", type="book",
                                     primary_source="openalex") for i in range(4)]
        self.assertEqual(search.distribution_advisories(rows), [])

    def test_denominator_is_known_not_total(self):
        """分母是该维度**有值**的条目数。拿总条数当分母，缺失值会把真实集中稀释到阈值以下。"""
        rows = self._rows(6) + [dict(year=2020, venue=None, type=None, primary_source=None)
                                for _ in range(6)]
        dims = {a["dimension"]: a for a in search.distribution_advisories(rows)}
        self.assertEqual(dims["发表期刊 / 来源"]["known"], 6)     # 不是 12
        self.assertEqual(dims["发表期刊 / 来源"]["pct"], 100)

    def test_too_few_known_stays_silent(self):
        # 4 条样本算比例只是噪声
        self.assertEqual(search.distribution_advisories(self._rows(4)), [])

    def test_year_is_bucketed_by_five(self):
        """年份按 5 年一档：单一年份占七成几乎只在结果极少时出现，
        「七成挤在最近 5 年」才对得上 Gap 的「时间缺失」。"""
        rows = [dict(year=2020 + i % 5, venue=f"V{i}", type=None, primary_source=None)
                for i in range(8)]
        dims = {a["dimension"]: a for a in search.distribution_advisories(rows)}
        self.assertEqual(dims["发表年份（5 年一档）"]["value"], "2020–2024")
        self.assertEqual(dims["发表年份（5 年一档）"]["pct"], 100)

    def test_text_states_signal_not_defect(self):
        """措辞是产品边界的一部分：不能读成「你的检索有缺陷」。"""
        text = search.distribution_advisories(self._rows(6))[0]["text"]
        self.assertIn("这是分布信号，不是缺陷", text)
        self.assertIn("由你判断", text)

    def test_type_dialects_are_normalized_before_counting(self):
        """Crossref 说 journal-article、OpenAlex 说 article——同一类型的两种源方言。
        不归一就把真实集中劈成两半：真机 20 条里 10+9 条全是期刊论文（95%），
        分方言统计后最高只有 50%，advisory 直接漏报。"""
        rows = ([dict(year=2000 + i, venue=f"刊{i}", type="journal-article",
                      primary_source="crossref") for i in range(10)]
                + [dict(year=2000 + i, venue=f"誌{i}", type="article",
                        primary_source="openalex") for i in range(9)]
                + [dict(year=1999, venue="其他", type="book", primary_source="openalex")])
        dims = {a["dimension"]: a for a in search.distribution_advisories(rows)}
        self.assertIn("文献类型", dims)
        self.assertEqual(dims["文献类型"]["value"], "journal-article")
        self.assertEqual(dims["文献类型"]["count"], 19)
        self.assertEqual(dims["文献类型"]["pct"], 95)

    def test_unknown_type_kept_not_dropped(self):
        """归一不了的类型保留原值。丢掉会缩小分母——又是一次稀释。"""
        rows = [dict(year=2000 + i, venue=f"刊{i}", type="某种没见过的类型",
                     primary_source="crossref") for i in range(6)]
        dims = {a["dimension"]: a for a in search.distribution_advisories(rows)}
        self.assertEqual(dims["文献类型"]["known"], 6)
        self.assertEqual(dims["文献类型"]["value"], "某种没见过的类型")

    def test_empty_input(self):
        self.assertEqual(search.distribution_advisories([]), [])


class TestRank(unittest.TestCase):
    def test_year_desc_none_last(self):
        merged = [{"year": 2019, "sources": ["a"]}, {"year": 2023, "sources": ["b"]},
                  {"year": None, "sources": ["c"]}]
        out = search.rank_hits(merged, "year_desc")
        self.assertEqual([m["year"] for m in out], [2023, 2019, None])

    def test_source_count_desc(self):
        merged = [{"year": 2020, "sources": ["a"]}, {"year": 2019, "sources": ["a", "b", "c"]}]
        out = search.rank_hits(merged, "source_count")
        self.assertEqual(len(out[0]["sources"]), 3)


class TestPayload(unittest.TestCase):
    def test_stats_dedup_rank_and_passthrough(self):
        items = [_hit("crossref", doi="10.1/a", year=2020),
                 _hit("openalex", doi="10.1/a", year=2020),
                 _hit("arxiv", doi="10.3/c", year=2023)]
        result = SearchResult(items=items,
                              coverage=[{"source": "crossref", "coverage": "自动检索"}],
                              network_status="ok")
        p = search.build_payload("q", {"year_from": 2018}, result, sort="year_desc", limit=30)
        self.assertEqual(p["stats"]["raw_hits"], 3)
        self.assertEqual(p["stats"]["after_dedup"], 2)     # 10.1/a 两源合并
        self.assertEqual(p["results"][0]["rank"], 1)
        self.assertEqual(p["results"][0]["year"], 2023)    # year_desc：2023 在前
        self.assertEqual(p["network_status"], "ok")
        self.assertEqual(p["coverage"][0]["source"], "crossref")
        self.assertEqual(p["filters"], {"year_from": 2018})

    def test_limit_truncates(self):
        items = [_hit("crossref", doi=f"10.1/{i}", year=2000 + i) for i in range(5)]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        p = search.build_payload("q", None, result, limit=3)
        self.assertEqual(p["stats"]["shown"], 3)
        self.assertEqual(len(p["results"]), 3)
        self.assertEqual(p["filters"], {})       # None → {}

    def test_truncation_emits_warning(self):
        """截断必须自报。判据一直在 stats 里，但宿主不会主动比 after_dedup 与 shown——
        实况是示例的 --limit 30 被照抄，74 条只呈现 30 条、整两年文献静默消失。"""
        items = [_hit("crossref", doi=f"10.1/{i}", year=2000 + i) for i in range(5)]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        w = search.build_payload("q", None, result, limit=3)["warnings"]
        self.assertEqual(len(w), 1)
        self.assertIn("5", w[0])            # 去重后总数，告诉宿主该把 --limit 调到多少
        self.assertIn("--limit", w[0])

    def test_no_warning_when_nothing_truncated(self):
        items = [_hit("crossref", doi=f"10.1/{i}", year=2000 + i) for i in range(3)]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        self.assertEqual(search.build_payload("q", None, result, limit=3)["warnings"], [])

    def test_limit_zero_means_no_truncation(self):
        items = [_hit("crossref", doi=f"10.1/{i}", year=2000 + i) for i in range(5)]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        p = search.build_payload("q", None, result, limit=0)
        self.assertEqual(p["stats"]["shown"], 5)
        self.assertEqual(p["stats"]["after_dedup"], 5)
        self.assertEqual(p["warnings"], [])       # 没截断就没这条 warning
        self.assertEqual([r["rank"] for r in p["results"]], [1, 2, 3, 4, 5])

    def test_truncation_warning_does_not_mutate_caller_warnings(self):
        """传入的 warnings 是调用方的 list，截断声明不得就地追加进去。"""
        items = [_hit("crossref", doi=f"10.1/{i}", year=2000 + i) for i in range(5)]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        caller = ["原有声明"]
        p = search.build_payload("q", None, result, limit=2, warnings=caller)
        self.assertEqual(caller, ["原有声明"])
        self.assertEqual(len(p["warnings"]), 2)
        self.assertEqual(p["warnings"][0], "原有声明")   # 原有的排在前，不被顶掉

    def test_result_carries_day_level_date(self):
        """输出契约必须带 date：paper-daily 靠它判时间窗。给不出的源为 None，不用 year 凑。"""
        items = [_hit("arxiv", doi="10.48550/arxiv.2607.00001", date="2026-07-29"),
                 _hit("crossref", doi="10.1/b")]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        p = search.build_payload("q", None, result)
        by_doi = {r["doi"]: r for r in p["results"]}
        self.assertEqual(by_doi["10.48550/arxiv.2607.00001"]["date"], "2026-07-29")
        self.assertIsNone(by_doi["10.1/b"]["date"])

    def test_warnings_default_empty(self):
        result = SearchResult(items=[], coverage=[], network_status="ok")
        self.assertEqual(search.build_payload("q", None, result)["warnings"], [])

    def test_default_limit_does_not_truncate(self):
        """默认不截断。此前默认是 30，示例被照抄后整两年文献静默消失——默认值本身是病根。"""
        items = [_hit("crossref", doi=f"10.1/{i}", year=2000 + i) for i in range(40)]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        p = search.build_payload("q", None, result)      # 不传 limit
        self.assertEqual(p["stats"]["shown"], 40)
        self.assertEqual(p["warnings"], [])

    def test_advisories_separate_from_warnings(self):
        """advisories 与 warnings 是两个字段：一个说结果长什么样，一个说这次检索出了问题。
        混在一起宿主会把分布特征当异常念。"""
        items = [_hit("crossref", doi=f"10.1/{i}", year=2020, venue="同一刊")
                 for i in range(6)]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        p = search.build_payload("q", None, result, limit=3)
        self.assertEqual(len(p["warnings"]), 1)                  # 截断声明
        self.assertTrue(p["advisories"])                         # 分布信号
        self.assertIn("--limit", p["warnings"][0])
        self.assertNotIn("--limit", p["advisories"][0]["text"])

    def test_advisories_computed_before_truncation(self):
        """分布算在截断前的全量上。算在 shown 上时，`--limit N` 配 year_desc 会必然报出
        「年份高度集中」——那个集中是 limit 造出来的假信号，不是检索的事实。"""
        # 20 条跨 20 个年份、20 个刊：全量看年份与刊都不集中，
        # 但截到最新 3 条后年份会挤进同一 5 年档、刊也只剩 3 个
        items = [_hit("crossref", doi=f"10.1/{i}", year=2000 + i, venue=f"刊{i}")
                 for i in range(20)]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        p = search.build_payload("q", None, result, limit=3)
        self.assertEqual(p["stats"]["shown"], 3)
        fired = {a["dimension"] for a in p["advisories"]}
        self.assertNotIn("发表年份（5 年一档）", fired)
        self.assertNotIn("发表期刊 / 来源", fired)
        # 分母也必须是全量数，不是 shown
        rows = [_hit("crossref", doi=f"10.2/{i}", year=2020, venue="同一刊")
                for i in range(12)]
        p2 = search.build_payload("q", None, SearchResult(items=rows, coverage=[]), limit=2)
        self.assertEqual(p2["advisories"][0]["known"], 12)

    def test_mode_defaults_to_search(self):
        result = SearchResult(items=[], coverage=[], network_status="ok")
        self.assertEqual(search.build_payload("q", None, result)["mode"], "search")

    def test_snowball_payload_is_same_shape(self):
        """滚雪球与检索输出同形——两者要能并进同一张笔记表，同形是前提。"""
        items = [_hit("openalex", doi="10.1/a", direction="references")]
        result = SearchResult(items=items, coverage=[], network_status="ok")
        p = search.build_payload("10.9/seed", {"direction": "both"}, result, mode="snowball")
        self.assertEqual(p["mode"], "snowball")
        self.assertEqual(set(p) - {"mode"},
                         set(search.build_payload("q", None,
                                                  SearchResult(items=[], coverage=[]))) - {"mode"})
        self.assertEqual(p["results"][0]["snowball_directions"], ["references"])


class TestDateWindow(unittest.TestCase):
    """「最近 N 天」的换算与入参校验。宿主 agent 自己算日期易错，这一步收进脚本。"""

    def test_days_one_is_today(self):
        import datetime
        today = datetime.date(2026, 7, 29)
        self.assertEqual(search.window_from_days(1, today=today),
                         ("2026-07-29", "2026-07-29"))

    def test_days_seven_is_closed_interval_including_today(self):
        import datetime
        today = datetime.date(2026, 7, 29)
        self.assertEqual(search.window_from_days(7, today=today),
                         ("2026-07-23", "2026-07-29"))

    def test_days_crosses_month_boundary(self):
        import datetime
        today = datetime.date(2026, 3, 2)
        self.assertEqual(search.window_from_days(5, today=today),
                         ("2026-02-26", "2026-03-02"))

    def test_days_below_one_rejected(self):
        with self.assertRaises(ValueError):
            search.window_from_days(0)

    def test_iso_date_validation(self):
        self.assertTrue(search._valid_iso_date("2026-07-29"))
        self.assertFalse(search._valid_iso_date("2026/07/29"))
        self.assertFalse(search._valid_iso_date("20260729"))
        self.assertFalse(search._valid_iso_date("2026-13-01"))    # 非法月份

    def test_warning_when_window_meets_dateless_sources(self):
        """给不提供日期的源加窗口会 0 命中——提前说清是「源不给日期」而非「当期无新发」。"""
        w = search.date_window_warnings(["crossref", "arxiv"], "2026-07-29", "2026-07-29")
        self.assertEqual(len(w), 1)
        self.assertIn("crossref", w[0])
        self.assertNotIn("arxiv 在本次窗口", w[0])

    def test_no_warning_for_arxiv_only(self):
        self.assertEqual(search.date_window_warnings(["arxiv"], "2026-07-29", "2026-07-29"), [])

    def test_no_warning_without_window(self):
        self.assertEqual(search.date_window_warnings(["crossref"], None, None), [])

    def test_default_sources_warned_generically(self):
        w = search.date_window_warnings(None, "2026-07-29", None)
        self.assertEqual(len(w), 1)
        self.assertIn("默认核心源", w[0])

    def test_many_terms_warned_under_window(self):
        """窗口下走逐词 AND，词太多会 0 命中——实测 7 词 0 条、5 词 10 条。
        不提醒的话，宿主会把「查询太严」读成「当期无新发」。"""
        w = search.date_window_warnings(["arxiv"], "2026-07-20", "2026-07-29",
                                        "large language model feedback programming "
                                        "assignments students")
        self.assertEqual(len(w), 1)
        self.assertIn("7 个词", w[0])

    def test_few_terms_not_warned(self):
        self.assertEqual(
            search.date_window_warnings(["arxiv"], "2026-07-20", "2026-07-29",
                                        "llm feedback programming"), [])

    def test_term_warning_only_under_window(self):
        """无窗口时逐词 AND 不生效（走松散匹配），不该提醒。"""
        self.assertEqual(
            search.date_window_warnings(["arxiv"], None, None,
                                        "a b c d e f g h"), [])


class TestCliDateArgs(unittest.TestCase):
    """CLI 层的互斥与非法值：宁可退出码 2 报错，也不静默用一个错窗口去检索。"""

    def _run(self, argv):
        return search.main(argv)

    def test_days_and_explicit_dates_are_mutually_exclusive(self):
        self.assertEqual(self._run(["--query", "q", "--days", "3",
                                    "--date-from", "2026-07-01"]), 2)

    def test_bad_date_format_rejected(self):
        self.assertEqual(self._run(["--query", "q", "--date-from", "2026/07/01"]), 2)

    def test_reversed_window_rejected(self):
        self.assertEqual(self._run(["--query", "q", "--date-from", "2026-07-29",
                                    "--date-to", "2026-07-01"]), 2)

    def test_days_zero_rejected(self):
        self.assertEqual(self._run(["--query", "q", "--days", "0"]), 2)

    def test_window_with_no_usable_terms_rejected(self):
        """带窗口但切不出检索词：报错退出，不能只留日期条件去查
        （那会把窗口内全站新发当成用户主题的新发）。"""
        self.assertEqual(self._run(["--query", '()"', "--days", "1"]), 2)

    def test_negative_limit_rejected(self):
        """0 = 不截断是明确语义，负数只可能是手滑。"""
        self.assertEqual(self._run(["--query", "q", "--limit", "-1"]), 2)


class TestLookupPayload(unittest.TestCase):
    """回填补全（--lookup-doi）：命中给元数据；ISTIC / miss 标人工核对，绝不 NOT_FOUND。"""

    def test_found_returns_metadata(self):
        ev = Evidence(ref_id="single", input=Ref(id="single", doi="10.1/a"), doi_ra="Crossref",
                      hits=[SourceHit(source="crossref", metadata={"title": "T", "year": 2020},
                                      fetched_at="2026-01-01T00:00:00Z")])
        p = search.build_lookup_payload("10.1/a", ev)
        self.assertTrue(p["found"])
        self.assertEqual(p["metadata"]["title"], "T")
        self.assertIsNone(p["note"])

    def test_istic_flagged_manual_not_notfound(self):
        ev = Evidence(ref_id="single", input=Ref(id="single", doi="10.3969/x"),
                      doi_ra="ISTIC", route_note="ISTIC 注册", hits=[])
        p = search.build_lookup_payload("10.3969/x", ev)
        self.assertFalse(p["found"])
        self.assertEqual(p["doi_ra"], "ISTIC")
        self.assertIn("人工核对", p["note"])

    def test_miss_flagged_not_fabrication(self):
        ev = Evidence(ref_id="single", input=Ref(id="single", doi="10.9/z"),
                      doi_ra="Crossref", hits=[])
        p = search.build_lookup_payload("10.9/z", ev)
        self.assertFalse(p["found"])
        self.assertIn("人工核对", p["note"])

    def test_not_registered_note_differs_from_plain_miss(self):
        """前缀未注册与「各源未命中」证据强度不同，note 不能共用一句。"""
        ev = Evidence(ref_id="single", input=Ref(id="single", doi="10.9999/fake"),
                      doi_ra="not_registered",
                      route_note="DOI 前缀未在任一注册机构注册——DOI 不存在的强信号", hits=[])
        p = search.build_lookup_payload("10.9999/fake", ev)
        self.assertFalse(p["found"])
        self.assertIn("人工核对", p["note"])          # 仍不判 NOT_FOUND
        self.assertIn("未在任一注册机构注册", p["note"])
        miss = search.build_lookup_payload("10.9/z", Evidence(
            ref_id="s", input=Ref(id="s", doi="10.9/z"), doi_ra="Crossref", hits=[]))
        self.assertNotEqual(p["note"], miss["note"])


class TestLookupCrossCheck(unittest.TestCase):
    """回填补全的交叉核验：DOI 查得到 ≠ 就是这一篇。堵「DOI 抄错一位 / 题录张冠李戴」。

    比对内核在 paper_shared.matching（与 paper-verify 共用），此处只测 search 侧的接线与
    三态语义：null=未比对 / true=比对一致 / false=比对不一致。**任何一条都不许出现态码**。
    """

    @staticmethod
    def _ev(doi="10.1/a", hits=None, doi_ra="Crossref", route_note=None):
        return Evidence(ref_id="single", input=Ref(id="single", doi=doi), doi_ra=doi_ra,
                        route_note=route_note, hits=hits or [])

    @staticmethod
    def _h(title="Deep learning", year=2015, doi="10.1/a", source="crossref"):
        return SourceHit(source=source,
                         metadata={"title": title, "year": year, "doi": doi,
                                   "authors": ["Y. LeCun"]},
                         fetched_at="2026-01-01T00:00:00Z")

    def test_no_ref_is_null_not_false(self):
        """不传 ref（旧调用方式）→ 未比对。null 与 false 是两件事，不许合并。"""
        p = search.build_lookup_payload("10.1/a", self._ev(hits=[self._h()]))
        self.assertTrue(p["found"])
        self.assertIsNone(p["metadata_consistent"])
        self.assertIsNone(p["field_notes"])
        self.assertIsNone(p["note"])

    def test_ref_without_title_is_null(self):
        """给了 ref 但没标题 → 仍是未比对，绝不拿源自己的标题自比出一个假的 True。"""
        p = search.build_lookup_payload("10.1/a", self._ev(hits=[self._h()]),
                                        Ref(id="lookup", doi="10.1/a", title=None))
        self.assertIsNone(p["metadata_consistent"])

    def test_title_matches(self):
        p = search.build_lookup_payload(
            "10.1/a", self._ev(hits=[self._h()]),
            Ref(id="lookup", doi="10.1/a", title="Deep learning", year=2015))
        self.assertTrue(p["metadata_consistent"])
        self.assertEqual(p["field_notes"], [])
        self.assertIsNone(p["note"])           # 一致时不额外唠叨

    def test_title_mismatch_reports_but_does_not_judge(self):
        """核心场景：DOI 真、指向的却是另一篇。报比对结果 + 出口指引，**不判存在性**。"""
        p = search.build_lookup_payload(
            "10.1/a", self._ev(hits=[self._h()]),
            Ref(id="lookup", doi="10.1/a", title="Attention Is All You Need", year=2017))
        self.assertTrue(p["found"])            # 查得到就是查得到
        self.assertFalse(p["metadata_consistent"])
        fields = {n["field"] for n in p["field_notes"]}
        self.assertIn("title", fields)
        self.assertIn("year", fields)          # 年份差 2 也升 mismatch
        self.assertIn("/paper-verify", p["note"])
        # 红线：本命令只陈列，不判态、不判编造
        for banned in ("NOT_FOUND", "VERIFIED", "MISMATCH", "编造"):
            self.assertNotIn(banned, p["note"])

    def test_miss_with_title_stays_null(self):
        """没查到 + 给了标题 → 仍是未比对（没有可比的对象），不得报 false。"""
        p = search.build_lookup_payload("10.9/z", self._ev(doi="10.9/z", hits=[]),
                                        Ref(id="lookup", doi="10.9/z", title="T"))
        self.assertFalse(p["found"])
        self.assertIsNone(p["metadata_consistent"])
        self.assertIn("人工核对", p["note"])    # 原三档 note 不被交叉核验挤掉

    def test_istic_note_survives_cross_check(self):
        """ISTIC 中文 DOI：查不到元数据，交叉核验不得改写它那句话（红线 3）。"""
        p = search.build_lookup_payload(
            "10.3969/x", self._ev(doi="10.3969/x", doi_ra="ISTIC", hits=[]),
            Ref(id="lookup", doi="10.3969/x", title="某某中文研究"))
        self.assertIn("ISTIC", p["note"])
        self.assertIsNone(p["metadata_consistent"])

    def test_picks_best_hit_by_title_not_first(self):
        """多源命中且都没回 DOI 字段时，按标题选最匹配的那条，不是 hits[0]。"""
        wrong = self._h(title="Quantum computing", doi=None, source="s2")
        right = self._h(title="Deep learning", doi=None, source="openalex")
        p = search.build_lookup_payload(
            "10.1/a", self._ev(hits=[wrong, right]),
            Ref(id="lookup", doi="10.1/a", title="Deep learning", year=2015))
        self.assertEqual(p["metadata"]["title"], "Deep learning")
        self.assertTrue(p["metadata_consistent"])

    def test_cli_accepts_title_and_ref_year(self):
        args = search._parse_args(["--lookup-doi", "10.1/a", "--title", "T",
                                   "--ref-year", "2020"])
        self.assertEqual(args.title, "T")
        self.assertEqual(args.ref_year, 2020)

    def test_cli_ref_year_is_not_year_from(self):
        """--ref-year 是比对用的题录年份，与检索筛选的 --year-from 不是一回事。"""
        args = search._parse_args(["--query", "q", "--year-from", "2018"])
        self.assertIsNone(args.ref_year)
        self.assertEqual(args.year_from, 2018)


class TestRenderHtml(unittest.TestCase):
    def test_table_link_and_coverage_class(self):
        md = ("# 文献笔记表\n\n"
              "| 标题（含链接） | 覆盖方式 |\n| --- | --- |\n"
              "| [A](https://doi.org/10.1/a) | 自动检索 |\n"
              "| B（知网） | 用户回填 |\n")
        h = render_html.md_to_html(md)
        self.assertIn("<table>", h)
        self.assertIn('<a href="https://doi.org/10.1/a"', h)   # 链接可点击
        self.assertIn('class="auto"', h)                       # 自动检索色标
        self.assertIn('class="manual"', h)                     # 用户回填色标

    def test_notice_block(self):
        md = "⚠️ 覆盖提示：英文库没检索到不等于没人研究过\n"
        self.assertIn('class="notice"', render_html.md_to_html(md))

    def test_html_escaped(self):
        h = render_html.md_to_html("| 标题 |\n| --- |\n| a<script>b |\n")
        self.assertNotIn("<script>", h)                        # 转义防注入
        self.assertIn("&lt;script&gt;", h)


if __name__ == "__main__":
    unittest.main()
