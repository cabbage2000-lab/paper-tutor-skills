"""开放获取（OA）可得性的跨源合并（search.py·_merge_oa）。

同一篇文献常被多源命中，各源的 OA 信息完整度差很远：Crossref（权威序最高的主源）
压根不给 OA 字段，OpenAlex 给状态 + 版本 + 链接，PubMed 只在有 PMC 时给。所以合并
**不按源权威序取，而按信息完整度取**——OA 的价值在「能不能点开、点开是不是最终版」，
跟元数据权威不权威无关。

守四件事：
  1. 有链接的胜过没链接的（状态说「理论上开放」，链接才是「现在能点开」）；
  2. 同为有链接时 publishedVersion 胜过 accepted / submitted；
  3. `oa` 为 None（该源未给出）的 hit 不参与竞争——否则「未知」会盖掉真链接；
  4. 全源都没给 → (None, None)，呈现层写「未知（各源未给出）」而**不是 closed**。
"""
from __future__ import annotations

import pathlib
import sys
import unittest

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "_shared"))
sys.path.insert(0, str(_REPO / "skills" / "paper-search" / "scripts"))

import search  # noqa: E402

from paper_shared.datasources.clients.base import oa_record  # noqa: E402
from paper_shared.datasources.models import SourceHit  # noqa: E402

_UNSET = object()


def _hit(source, oa=_UNSET, doi="10.1/a"):
    """oa 默认**不设键**（模拟 crossref / s2 这类不给 OA 字段的源）。
    显式传 None 与不传都表示「该源未给出」，两者都不该参与竞争。"""
    meta = {"title": "T", "doi": doi, "year": 2020, "venue": "V", "type": "journal-article",
            "authors": ["X"]}
    if oa is not _UNSET:
        meta["oa"] = oa
    return SourceHit(source=source, metadata=meta, fetched_at="2026-08-04T00:00:00Z")


def _oa(**kw):
    return oa_record(**kw)


class TestMergeOaPriority(unittest.TestCase):
    def test_linked_beats_unlinked_even_from_lower_authority_source(self):
        """crossref 权威序最高但不给 OA；openalex 给了链接 → 取 openalex。
        按权威序取会让整列消失。"""
        hits = [_hit("crossref"),
                _hit("openalex", _oa(status="green", url="https://r.org/a",
                                     url_kind="landing", version="submittedVersion"))]
        oa, src = search._merge_oa(hits)
        self.assertEqual(src, "openalex")
        self.assertEqual(oa["url"], "https://r.org/a")

    def test_status_only_loses_to_a_real_link(self):
        hits = [_hit("openalex", _oa(status="bronze")),
                _hit("pubmed", _oa(status="green", host="pmc", url_kind="landing",
                                   url="https://pmc.ncbi.nlm.nih.gov/articles/PMC1/"))]
        oa, src = search._merge_oa(hits)
        self.assertEqual(src, "pubmed")
        self.assertEqual(oa["host"], "pmc")

    def test_published_version_beats_submitted(self):
        """两边都有链接时看版本：投稿版与最终发表版在页码甚至结论表述上都可能不同。"""
        hits = [_hit("openalex", _oa(status="green", url="https://r.org/preprint.pdf",
                                     url_kind="pdf", version="submittedVersion")),
                _hit("pubmed", _oa(status="green", url="https://pmc.example/PMC1/",
                                   url_kind="landing", version="publishedVersion"))]
        oa, src = search._merge_oa(hits)
        self.assertEqual(src, "pubmed")
        self.assertEqual(oa["version"], "publishedVersion")

    def test_accepted_beats_submitted(self):
        hits = [_hit("arxiv", _oa(status="green", url="https://arxiv.org/pdf/1",
                                  url_kind="pdf", version="submittedVersion")),
                _hit("openalex", _oa(status="green", url="https://repo/2.pdf",
                                     url_kind="pdf", version="acceptedVersion"))]
        _, src = search._merge_oa(hits)
        self.assertEqual(src, "openalex")

    def test_tie_breaks_by_source_authority_order(self):
        """信息完整度相同 → 按既有源权威序，结果可复现（openalex 1 < pubmed 4）。"""
        same = dict(status="green", url_kind="pdf", version="publishedVersion")
        hits = [_hit("pubmed", _oa(url="https://b.org/b.pdf", **same)),
                _hit("openalex", _oa(url="https://a.org/a.pdf", **same))]
        oa, src = search._merge_oa(hits)
        self.assertEqual(src, "openalex")
        self.assertEqual(oa["url"], "https://a.org/a.pdf")

    def test_unknown_version_loses_to_known_version(self):
        hits = [_hit("openalex", _oa(status="green", url="https://a/1", url_kind="pdf")),
                _hit("pubmed", _oa(status="green", url="https://b/2", url_kind="landing",
                                   version="acceptedVersion"))]
        _, src = search._merge_oa(hits)
        self.assertEqual(src, "pubmed")


class TestMergeOaUnknownHandling(unittest.TestCase):
    def test_missing_key_and_explicit_none_both_sit_out(self):
        """「该源未给出」不参与竞争——参与就会用「未知」盖掉另一源给出的真链接。"""
        hits = [_hit("crossref"), _hit("semantic_scholar", None),
                _hit("openalex", _oa(status="gold", url="https://p.org/a.pdf",
                                     url_kind="pdf", version="publishedVersion"))]
        oa, src = search._merge_oa(hits)
        self.assertEqual(src, "openalex")
        self.assertEqual(oa["status"], "gold")

    def test_all_sources_silent_yields_none_not_closed(self):
        """全源都没给 → (None, None)。呈现层据此写「未知（各源未给出）」，
        绝不是 closed——那会让用户放弃本来能拿到的文献。"""
        oa, src = search._merge_oa([_hit("crossref"), _hit("semantic_scholar", None)])
        self.assertIsNone(oa)
        self.assertIsNone(src)

    def test_closed_from_source_is_kept_not_dropped(self):
        """源明确说 closed 时要留着——它与「未知」是两个不同的事实。"""
        oa, src = search._merge_oa([_hit("openalex", _oa(status="closed"))])
        self.assertEqual(oa["status"], "closed")
        self.assertEqual(src, "openalex")


class TestDedupWiring(unittest.TestCase):
    """去重结果行必须带 oa / oa_source 两个字段（呈现层按名字读）。"""

    def test_merged_row_exposes_oa_and_source(self):
        merged = search.dedup_hits([
            _hit("crossref"),
            _hit("openalex", _oa(status="green", url="https://r.org/a", url_kind="landing",
                                 version="submittedVersion", host="repository")),
        ])
        self.assertEqual(len(merged), 1)
        row = merged[0]
        self.assertEqual(row["primary_source"], "crossref")      # 题录仍跟主源
        self.assertEqual(row["oa_source"], "openalex")           # OA 跟给得出的源
        self.assertEqual(row["oa"]["host"], "repository")

    def test_row_has_null_oa_when_no_source_gives_it(self):
        row = search.dedup_hits([_hit("crossref")])[0]
        self.assertIsNone(row["oa"])
        self.assertIsNone(row["oa_source"])

    def test_no_cited_by_style_sort_key_for_oa(self):
        """OA 是陈列列、不是排序键（同被引数，红线 1）——排序参数集里不许出现它。"""
        merged = search.dedup_hits([
            _hit("openalex", _oa(status="closed"), doi="10.1/a"),
            _hit("openalex", _oa(status="gold", url="https://x/y", url_kind="pdf"),
                 doi="10.1/b"),
        ])
        # 默认 year_desc：两条同年，顺序由稳定排序决定，与 OA 状态无关
        self.assertEqual([r["doi"] for r in search.rank_hits(merged)], ["10.1/a", "10.1/b"])


if __name__ == "__main__":
    unittest.main()