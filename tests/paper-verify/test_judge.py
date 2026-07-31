"""paper-verify scripts/judge.py 确定性单测——六态判定全覆盖。

每态构造 ParsedRef + Evidence fixture，断言 StatusRecord.status 与字段级标注。
中文轨不进 NOT_FOUND（硬约束⑤）是重点验证项。
"""
from __future__ import annotations

import pathlib
import sys
import unittest

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "_shared"))
sys.path.insert(0, str(_REPO / "skills" / "paper-verify" / "scripts"))

import judge  # noqa: E402
import parse_refs  # noqa: E402
from paper_shared.datasources.models import Evidence, Ref, SourceHit, SourceQuery  # noqa: E402
# 字段比对内核在共享层（paper-verify 与 paper-search 共用）。本文件测它，是因为 verify 的
# 第 5 条判定直接架在这些阈值上——阈值一变，六态判定就变。
from paper_shared import matching  # noqa: E402


def _parsed(rid="r1", doi=None, title="T", authors=None, year=2020, venue=None,
            status="ok"):
    return parse_refs.ParsedRef(id=rid, doi=doi, title=title, authors=authors or [],
                                year=year, venue=venue, parse_status=status)


def _hit(source="crossref", doi=None, title="T", year=2020, venue="V",
         authors=None, retraction=None):
    return SourceHit(source=source,
                     metadata={"title": title, "doi": doi, "year": year, "venue": venue,
                               "type": "journal-article", "authors": authors or ["X"]},
                     fetched_at="2026-01-01T00:00:00Z", retraction=retraction)


def _ev(rid="r1", doi_ra=None, hits=None, queries=None, doi=None):
    return Evidence(ref_id=rid, input=Ref(id=rid, doi=doi), doi_ra=doi_ra,
                    hits=hits or [], queries=queries or [])


def _q(source, outcome):
    return SourceQuery(source=source, query_kind="doi", outcome=outcome)


class TestJudgeSixStates(unittest.TestCase):
    # 0. 人工回填优先
    def test_manual_verified_overrides(self):
        p = _parsed(doi="10.3969/x")           # 本会走 ISTIC/中文轨的条目
        e = _ev(doi_ra="ISTIC", doi="10.3969/x")
        rec = judge.judge(p, e, manual_result={"verified": True, "checked_at": "2026-07-26"})
        self.assertEqual(rec.status, "VERIFIED")
        self.assertIn("人工核对", rec.evidence_summary)

    # 1. 解析失败
    def test_unparsed_to_pending(self):
        p = _parsed(status="unparsed")
        rec = judge.judge(p, _ev())
        self.assertEqual(rec.status, "PENDING_MANUAL")
        self.assertIsNotNone(rec.exit_guidance)

    # 2a. ISTIC 中文轨
    def test_istic_to_pending(self):
        p = _parsed(doi="10.3969/x")
        rec = judge.judge(p, _ev(doi_ra="ISTIC", doi="10.3969/x"))
        self.assertEqual(rec.status, "PENDING_MANUAL")

    # 2b. 无 DOI 中文
    def test_no_doi_chinese_to_pending(self):
        p = _parsed(doi=None, title="某某中文研究")
        rec = judge.judge(p, _ev(doi_ra=None))
        self.assertEqual(rec.status, "PENDING_MANUAL")

    # 3. 前缀未注册 → NOT_FOUND
    def test_not_registered_to_not_found(self):
        p = _parsed(doi="10.9999/fake")
        rec = judge.judge(p, _ev(doi_ra="not_registered", doi="10.9999/fake"))
        self.assertEqual(rec.status, "NOT_FOUND")
        self.assertIn("疑似不存在", rec.evidence_summary)

    # 4. 撤稿
    def test_retracted(self):
        p = _parsed(doi="10.1/a")
        h = _hit(doi="10.1/a", retraction={"type": "retraction", "label": "Retraction",
                                           "date_parts": [[2010, 2, 6]],
                                           "source": "retraction-watch"})
        rec = judge.judge(p, _ev(doi_ra="Crossref", hits=[h], doi="10.1/a"))
        self.assertEqual(rec.status, "RETRACTED")
        self.assertIn("2010-02-06", rec.evidence_summary)
        self.assertIn("retraction-watch", rec.evidence_summary)

    def test_retracted_provenance_not_hardcoded(self):
        """OpenAlex 只给布尔标记（无日期、非 Retraction Watch）→ 不得谎称来自它。"""
        p = _parsed(doi="10.1/a")
        h = _hit(source="openalex", doi="10.1/a",
                 retraction={"type": "retraction", "label": "Retraction",
                             "date_parts": None, "source": "openalex", "doi": None})
        rec = judge.judge(p, _ev(doi_ra="Crossref", hits=[h], doi="10.1/a"))
        self.assertEqual(rec.status, "RETRACTED")
        self.assertNotIn("Retraction Watch", rec.evidence_summary)
        self.assertNotIn("撤稿日期", rec.evidence_summary)

    def test_retracted_prefers_hit_with_date(self):
        """多源都报撤稿 → 展示信息最全的那条（带日期的 Crossref），但列出全部源。"""
        p = _parsed(doi="10.1/a")
        oa = _hit(source="openalex", doi="10.1/a",
                  retraction={"type": "retraction", "date_parts": None, "source": "openalex"})
        cr = _hit(source="crossref", doi="10.1/a",
                  retraction={"type": "retraction", "date_parts": [[2010, 2, 6]],
                              "source": "retraction-watch"})
        rec = judge.judge(p, _ev(doi_ra="Crossref", hits=[oa, cr], doi="10.1/a"))
        self.assertEqual(rec.status, "RETRACTED")
        self.assertIn("2010-02-06", rec.evidence_summary)
        self.assertIn("crossref", rec.evidence_summary)
        self.assertIn("openalex", rec.evidence_summary)

    # 5a. 字段全一致 → VERIFIED
    def test_verified_consistent(self):
        p = _parsed(doi="10.1/a", title="AI in Education", authors=["Smith, John"], year=2020)
        h = _hit(doi="10.1/a", title="AI in Education", authors=["Smith, John"], year=2020)
        rec = judge.judge(p, _ev(doi_ra="Crossref", hits=[h], doi="10.1/a"))
        self.assertEqual(rec.status, "VERIFIED")
        self.assertEqual(rec.field_notes, [])

    def test_verified_given_first_source_authors(self):
        """回归：Crossref / OpenAlex / S2 / arXiv 的作者是 given-first（'Yann LeCun'），
        引用是 'LeCun, Yann'。同一个人，绝不能误报 first_author 不符——否则任何一条
        正确引用只要走这些源命中就落 METADATA_MISMATCH，VERIFIED 态几乎不可达。"""
        for src_author in ("Yann LeCun", "Y. LeCun", "LeCun Y.", "LeCun, Yann"):
            with self.subTest(src_author=src_author):
                p = _parsed(doi="10.1/a", title="Deep learning",
                            authors=["LeCun, Yann"], year=2015)
                h = _hit(doi="10.1/a", title="Deep learning",
                         authors=[src_author], year=2015)
                rec = judge.judge(p, _ev(doi_ra="Crossref", hits=[h], doi="10.1/a"))
                self.assertEqual(rec.status, "VERIFIED")

    def test_verified_retracted_prefix_in_source_title(self):
        """回归：撤稿论文的 Crossref 标题带 'RETRACTED: ' 前缀，不得因此误报标题不符。"""
        p = _parsed(doi="10.1/a", title="A retracted study",
                    authors=["Doe, J."], year=2019)
        h = _hit(doi="10.1/a", title="RETRACTED: A retracted study",
                 authors=["J. Doe"], year=2019)
        rec = judge.judge(p, _ev(doi_ra="Crossref", hits=[h], doi="10.1/a"))
        self.assertEqual(rec.status, "VERIFIED")

    # 5b. 年份差 ≥ 2 → MISMATCH
    def test_mismatch_year(self):
        p = _parsed(doi="10.1/a", title="AI in Education", authors=["Smith, John"], year=2020)
        h = _hit(doi="10.1/a", title="AI in Education", authors=["Smith, John"], year=2018)
        rec = judge.judge(p, _ev(doi_ra="Crossref", hits=[h], doi="10.1/a"))
        self.assertEqual(rec.status, "METADATA_MISMATCH")
        self.assertEqual(len(rec.field_notes), 1)
        self.assertEqual(rec.field_notes[0].field, "year")

    # 5c. DOI 不符 → MISMATCH
    def test_mismatch_doi(self):
        p = _parsed(doi="10.1/a", title="AI in Education", authors=["Smith, John"], year=2020)
        h = _hit(doi="10.1/b", title="AI in Education", authors=["Smith, John"], year=2020)
        rec = judge.judge(p, _ev(doi_ra="Crossref", hits=[h], doi="10.1/a"))
        self.assertEqual(rec.status, "METADATA_MISMATCH")
        self.assertEqual(rec.field_notes[0].field, "doi")

    # 5d. 标题重叠低 → MISMATCH
    def test_mismatch_title(self):
        p = _parsed(doi="10.1/a", title="Deep Learning Survey", authors=["Smith, John"], year=2020)
        h = _hit(doi="10.1/a", title="Natural Language Processing", authors=["Smith, John"], year=2020)
        rec = judge.judge(p, _ev(doi_ra="Crossref", hits=[h], doi="10.1/a"))
        self.assertEqual(rec.status, "METADATA_MISMATCH")
        self.assertEqual(rec.field_notes[0].field, "title")

    # 5e. 第一作者姓不符 → MISMATCH
    def test_mismatch_author(self):
        p = _parsed(doi="10.1/a", title="AI in Education", authors=["Smith, John"], year=2020)
        h = _hit(doi="10.1/a", title="AI in Education", authors=["Jones, Robert"], year=2020)
        rec = judge.judge(p, _ev(doi_ra="Crossref", hits=[h], doi="10.1/a"))
        self.assertEqual(rec.status, "METADATA_MISMATCH")
        self.assertEqual(rec.field_notes[0].field, "first_author")

    # 5f. venue 不符仅 hint，不升态
    def test_venue_hint_does_not_escalate(self):
        p = _parsed(doi="10.1/a", title="AI in Education", authors=["Smith, John"],
                    year=2020, venue="J. Tech")
        h = _hit(doi="10.1/a", title="AI in Education", authors=["Smith, John"],
                 year=2020, venue="Journal of Technology")
        rec = judge.judge(p, _ev(doi_ra="Crossref", hits=[h], doi="10.1/a"))
        self.assertEqual(rec.status, "VERIFIED")          # venue 不升态
        fields = [n.field for n in rec.field_notes]
        self.assertIn("venue", fields)
        self.assertEqual(rec.field_notes[0].severity, "hint")

    # 6. 全源 miss + error → UNVERIFIED
    def test_unverified_on_error(self):
        p = _parsed(doi="10.1/a", title="AI in Education", authors=["Smith, John"], year=2020)
        e = _ev(doi_ra="Crossref", queries=[_q("crossref", "error"), _q("openalex", "error")], doi="10.1/a")
        rec = judge.judge(p, e)
        self.assertEqual(rec.status, "UNVERIFIED")

    # 7. 全源 miss + 注册机构自证 → NOT_FOUND（覆盖编造 DOI 号码）
    def test_not_found_ra_self_proof(self):
        p = _parsed(doi="10.1038/nature99999", title="Fake Survey", authors=["X"], year=2020)
        e = _ev(doi_ra="Crossref",
                queries=[_q("crossref", "miss"), _q("openalex", "miss")],
                doi="10.1038/nature99999")
        rec = judge.judge(p, e)
        self.assertEqual(rec.status, "NOT_FOUND")
        self.assertIn("疑似不存在", rec.evidence_summary)

    # 8. 其余 miss（无 DOI 英文）→ PENDING_MANUAL
    def test_pending_no_doi_english(self):
        p = _parsed(doi=None, title="Some Obscure English Title", authors=["Nobody"], year=2020)
        e = _ev(doi_ra=None, queries=[_q("crossref", "miss")])
        rec = judge.judge(p, e)
        self.assertEqual(rec.status, "PENDING_MANUAL")

    # 中文 ISTIC 即使全 miss 也绝不 NOT_FOUND（硬约束⑤铁律）
    def test_chinese_istic_never_not_found(self):
        p = _parsed(doi="10.3969/j.issn.1000-0054.2020.01.001", title="某某研究",
                    authors=["王明"], year=2020)
        e = _ev(doi_ra="ISTIC", doi="10.3969/j.issn.1000-0054.2020.01.001")
        rec = judge.judge(p, e)
        self.assertEqual(rec.status, "PENDING_MANUAL")
        self.assertNotEqual(rec.status, "NOT_FOUND")


class TestChineseDoiWithMetadata(unittest.TestCase):
    """中文 DOI 取到题录后照常核验——本次改动修的就是「降级降得过早」。

    改动前第 2 条判定无条件拦截 ISTIC，于是 doi_meta 即使拿到完整 CSL-JSON 题录，条目也
    照样落待人工核对：已经核验成功了还要请用户去知网手查一遍。现在只在**无 hit**时拦截。
    """

    def _cn_hit(self, **kw):
        return _hit(source="doi_meta", doi="10.11821/dlxb202001001",
                    title="理解地理“耦合”实现地理“集成”", year=2020,
                    venue="地理学报", authors=["宋长青"], **kw)

    def _cn_parsed(self, **kw):
        base = dict(doi="10.11821/dlxb202001001", title="理解地理“耦合”实现地理“集成”",
                    authors=["宋长青"], year=2020)
        base.update(kw)
        return _parsed(**base)

    def test_istic_with_hit_verifies(self):
        rec = judge.judge(self._cn_parsed(),
                          _ev(doi_ra="ISTIC", doi="10.11821/dlxb202001001",
                              hits=[self._cn_hit()], queries=[_q("doi_meta", "hit")]))
        self.assertEqual(rec.status, "VERIFIED")
        self.assertIn("doi_meta", rec.evidence_summary)

    def test_istic_with_hit_mismatch_is_reported(self):
        """题录取到了就要真比对——年份差太多必须报不符，不能一律放过。"""
        rec = judge.judge(self._cn_parsed(year=1999),
                          _ev(doi_ra="ISTIC", doi="10.11821/dlxb202001001",
                              hits=[self._cn_hit()], queries=[_q("doi_meta", "hit")]))
        self.assertEqual(rec.status, "METADATA_MISMATCH")

    def test_istic_retraction_still_wins(self):
        """撤稿优先于一切——中文条目也不例外。"""
        rec = judge.judge(self._cn_parsed(),
                          _ev(doi_ra="ISTIC", doi="10.11821/dlxb202001001",
                              hits=[self._cn_hit(retraction={"type": "retraction"})]))
        self.assertEqual(rec.status, "RETRACTED")

    def test_istic_without_hit_still_pending(self):
        """无 hit 时行为不变：仍落 PENDING_MANUAL，绝不 NOT_FOUND。"""
        rec = judge.judge(self._cn_parsed(),
                          _ev(doi_ra="ISTIC", doi="10.11821/dlxb202001001",
                              queries=[_q("doi_meta", "miss")]))
        self.assertEqual(rec.status, "PENDING_MANUAL")

    def test_pending_summary_claims_prefix_only(self):
        """判据精度：只说「前缀已注册」，不替可能编造的 DOI 担保存在性。

        实测编造后缀 `10.11821/dlxb209999999` 的前缀照样报 ISTIC 且落本分支——此时对用户
        说「DOI 合法存在」就是一句错话。
        """
        rec = judge.judge(_parsed(doi="10.11821/dlxb209999999", title="编造的中文文献",
                                  authors=["无名"], year=2099),
                          _ev(doi_ra="ISTIC", doi="10.11821/dlxb209999999",
                              queries=[_q("doi_meta", "miss")]))
        self.assertEqual(rec.status, "PENDING_MANUAL")
        self.assertIn("前缀", rec.evidence_summary)
        self.assertNotIn("DOI 合法存在", rec.evidence_summary)

    def test_cnki_without_hit_never_not_found(self):
        """CNKI 的内容协商回 HTML → 恒 miss。这条最容易被误判成编造，铁律必须守住。"""
        p = _parsed(doi="10.16511/j.cnki.qhdxxb.2020.22.001", title="某某研究",
                    authors=["王明"], year=2020)
        rec = judge.judge(p, _ev(doi_ra="CNKI", doi="10.16511/j.cnki.qhdxxb.2020.22.001",
                                 queries=[_q("doi_meta", "miss")]))
        self.assertEqual(rec.status, "PENDING_MANUAL")
        self.assertIn("CNKI", rec.evidence_summary)
        self.assertIsNotNone(rec.exit_guidance)

    def test_cnki_with_hit_verifies(self):
        """个别知网 DOI 若能回题录，同样照常核验（不写死成必然 miss）。"""
        p = _parsed(doi="10.16511/j.cnki.qhdxxb.2020.22.001", title="T",
                    authors=["X"], year=2020)
        rec = judge.judge(p, _ev(doi_ra="CNKI", doi="10.16511/j.cnki.qhdxxb.2020.22.001",
                                 hits=[_hit(source="doi_meta",
                                            doi="10.16511/j.cnki.qhdxxb.2020.22.001")],
                                 queries=[_q("doi_meta", "hit")]))
        self.assertEqual(rec.status, "VERIFIED")


class TestCompareHelpers(unittest.TestCase):
    def test_title_overlap_subset_is_one(self):
        # 引用标题是源标题子集（省略副标题）→ 重叠系数 1.0，视为一致
        self.assertEqual(matching.title_overlap("AI in Education", "AI in Education and Learning"), 1.0)

    def test_title_overlap_disjoint_is_zero(self):
        self.assertEqual(matching.title_overlap("Deep Learning", "Quantum Computing"), 0.0)

    def test_surname_candidates_comma_form_is_exact(self):
        # 有逗号 → 逗号前即姓，候选唯一
        self.assertEqual(matching.surname_candidates("Smith, John"), {"smith"})
        self.assertEqual(matching.surname_candidates("王明, 李华"), {"王明"})

    def test_surname_candidates_drops_initials(self):
        # 缩写必是名 → 剔除后候选精确，given-first / family-first 都对
        self.assertEqual(matching.surname_candidates("AJ Wakefield"), {"wakefield"})
        self.assertEqual(matching.surname_candidates("Wakefield AJ"), {"wakefield"})
        self.assertEqual(matching.surname_candidates("A. J. Wakefield"), {"wakefield"})

    def test_surname_candidates_keeps_short_cjk_romanized(self):
        # 中文罗马化姓多为 2 字符，不得当成缩写丢掉（故按大写判断而非长度）
        self.assertIn("li", matching.surname_candidates("Li Wang"))
        self.assertIn("wang", matching.surname_candidates("Li Wang"))

    def test_surname_candidates_full_names_ambiguous(self):
        # 两个都是全名 → 顺序无从判断，两者皆为候选
        self.assertEqual(matching.surname_candidates("Yann LeCun"), {"yann", "lecun"})


if __name__ == "__main__":
    unittest.main()
