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
        h = _hit(doi="10.1/a", retraction={"reason": "misconduct"})
        rec = judge.judge(p, _ev(doi_ra="Crossref", hits=[h], doi="10.1/a"))
        self.assertEqual(rec.status, "RETRACTED")

    # 5a. 字段全一致 → VERIFIED
    def test_verified_consistent(self):
        p = _parsed(doi="10.1/a", title="AI in Education", authors=["Smith, John"], year=2020)
        h = _hit(doi="10.1/a", title="AI in Education", authors=["Smith, John"], year=2020)
        rec = judge.judge(p, _ev(doi_ra="Crossref", hits=[h], doi="10.1/a"))
        self.assertEqual(rec.status, "VERIFIED")
        self.assertEqual(rec.field_notes, [])

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


class TestCompareHelpers(unittest.TestCase):
    def test_title_overlap_subset_is_one(self):
        # 引用标题是源标题子集（省略副标题）→ 重叠系数 1.0，视为一致
        self.assertEqual(judge._title_overlap("AI in Education", "AI in Education and Learning"), 1.0)

    def test_title_overlap_disjoint_is_zero(self):
        self.assertEqual(judge._title_overlap("Deep Learning", "Quantum Computing"), 0.0)

    def test_first_author_surname(self):
        self.assertEqual(judge._first_author_surname("Smith, John"), "smith")
        self.assertEqual(judge._first_author_surname("Smith John"), "smith")
        self.assertEqual(judge._first_author_surname("王明, 李华"), "王明")


if __name__ == "__main__":
    unittest.main()
