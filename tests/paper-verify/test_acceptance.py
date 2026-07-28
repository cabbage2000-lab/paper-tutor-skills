"""paper-verify 行为验收 + 量化门槛（spec §14 专属发布门）。

≥40 条混合样本（虚构 / 真实 / 中文 / 撤稿 / 不符），每条构造离线 Evidence fixture
+ 期望六态，跑 judge 统计三项门槛：
  - 虚构引用检出率 ≥ 95%（虚构样本判 NOT_FOUND 比例）
  - 真实引用误报率 ≤ 5%（真实样本误判非 VERIFIED 比例）
  - 真实中文文献误伤 = 0（中文样本绝不进 NOT_FOUND，硬约束⑤铁律）

离线确定性（不联网）——验证判定规则对各场景正确；真实 API 端到端 + 裸模型对比
见 evals/paper-verify/。样本即 tests/fixtures 核验语料的可执行规约。
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


def _hit(doi=None, title="T", year=2020, authors=None, retraction=None):
    return SourceHit(source="crossref",
                     metadata={"title": title, "doi": doi, "year": year, "venue": "V",
                               "type": "journal-article", "authors": authors or ["X"]},
                     fetched_at="2026-01-01T00:00:00Z", retraction=retraction)


def _q(source, outcome):
    return SourceQuery(source=source, query_kind="doi", outcome=outcome)


def _ev(rid, doi_ra=None, hits=None, queries=None, doi=None):
    return Evidence(ref_id=rid, input=Ref(id=rid, doi=doi), doi_ra=doi_ra,
                    hits=hits or [], queries=queries or [])


def _build_samples():
    """返回 [(ParsedRef, Evidence, expected_status, category), ...]，≥40 条。"""
    s = []

    # ── 虚构样本（期望 NOT_FOUND）——检出率分母 ──
    # 编造 DOI 前缀（10.9999 未注册）
    for i in range(5):
        p = parse_refs.ParsedRef(id=f"fA{i}", doi=f"10.9999/fake.{i:04d}",
                                 title=f"Fake Paper {i}", authors=["Nobody"], year=2020)
        s.append((p, _ev(p.id, doi_ra="not_registered", doi=p.doi), "NOT_FOUND", "fabricated"))
    # 编造 Crossref DOI 号码（注册机构自证不存在）
    for i in range(5):
        p = parse_refs.ParsedRef(id=f"fB{i}", doi=f"10.1038/nature99{i}",
                                 title=f"Fake Nature {i}", authors=["Ghost"], year=2020)
        s.append((p, _ev(p.id, doi_ra="Crossref",
                         queries=[_q("crossref", "miss"), _q("openalex", "miss")], doi=p.doi),
                 "NOT_FOUND", "fabricated"))

    # ── 真实样本（期望 VERIFIED）——误报率分母 ──
    # 源侧作者一律用**真实 API 的 given-first 形状**（Crossref/OpenAlex/S2/arXiv 给
    # "John Smith"，不是 "Smith, John"），引用侧保持学术惯例的 family-first。两侧写成
    # 同一格式会让误报率门槛虚过——这正是 given-first 误报 bug 曾逃过 42 条样本的原因。
    for i in range(8):
        doi = f"10.1000/real{i}"
        p = parse_refs.ParsedRef(id=f"rA{i}", doi=doi, title="Real Research on AI",
                                 authors=["Smith, John"], year=2020)
        h = _hit(doi=doi, title="Real Research on AI", authors=["John Smith"], year=2020)
        s.append((p, _ev(p.id, doi_ra="Crossref", hits=[h], doi=doi), "VERIFIED", "real"))
    # 合法小差异（年份差 1 / 标题子集 / 作者缩写写法不一）——仍应 VERIFIED，不误报
    p = parse_refs.ParsedRef(id="rB1", doi="10.1000/realB1", title="AI in Education",
                             authors=["Doe, Jane"], year=2021)
    h = _hit(doi="10.1000/realB1", title="AI in Education and Learning",
             authors=["Jane Doe"], year=2020)
    s.append((p, _ev(p.id, doi_ra="Crossref", hits=[h], doi="10.1000/realB1"), "VERIFIED", "real"))
    p = parse_refs.ParsedRef(id="rB2", doi="10.1000/realB2", title="Deep Learning Methods",
                             authors=["Lee, Bob"], year=2019)
    h = _hit(doi="10.1000/realB2", title="Deep Learning Methods",
             authors=["Bob Lee"], year=2019)
    s.append((p, _ev(p.id, doi_ra="Crossref", hits=[h], doi="10.1000/realB2"), "VERIFIED", "real"))
    p = parse_refs.ParsedRef(id="rB3", doi="10.1000/realB3", title="Quantum Computing",
                             authors=["Wang, X"], year=2022)
    h = _hit(doi="10.1000/realB3", title="Quantum Computing",
             authors=["X Wang"], year=2022)     # 缩写在前（S2 常见）
    s.append((p, _ev(p.id, doi_ra="Crossref", hits=[h], doi="10.1000/realB3"), "VERIFIED", "real"))
    p = parse_refs.ParsedRef(id="rB4", doi="10.1000/realB4", title="Climate Change Analysis",
                             authors=["Brown, K"], year=2018)
    h = _hit(doi="10.1000/realB4", title="Climate Change Analysis",
             authors=["Brown K"], year=2018)    # 缩写在后（PubMed 形状）
    s.append((p, _ev(p.id, doi_ra="Crossref", hits=[h], doi="10.1000/realB4"), "VERIFIED", "real"))

    # ── 中文样本（期望 PENDING_MANUAL）——中文误伤分母 ──
    for i in range(5):
        p = parse_refs.ParsedRef(id=f"cA{i}", doi=f"10.3969/x.{i}",
                                 title="某某中文实证研究", authors=["王明"], year=2020)
        s.append((p, _ev(p.id, doi_ra="ISTIC", doi=p.doi), "PENDING_MANUAL", "chinese"))
    for i in range(5):
        p = parse_refs.ParsedRef(id=f"cB{i}", doi=None,
                                 title=f"无 DOI 中文文献第 {i} 种", authors=["李华"], year=2019)
        s.append((p, _ev(p.id, doi_ra=None), "PENDING_MANUAL", "chinese"))

    # ── 撤稿（期望 RETRACTED）──
    # 源标题带 Crossref 真实的 "RETRACTED: " 前缀，retraction 用真实契约形状
    # （type/label/date_parts/source）。注意本层在 judge 入口注入已解析好的 Evidence，
    # **不覆盖客户端的字段解析**——updated-by 读错那类 bug 须由 tests/datasources/
    # 的 fixture 用例（按真实响应形状构造 + 反向用例）拦住。
    for i in range(4):
        p = parse_refs.ParsedRef(id=f"rt{i}", doi=f"10.1000/retracted{i}",
                                 title="A Retracted Study", authors=["Fraud, F."], year=2018)
        h = _hit(doi=p.doi, title="RETRACTED: A Retracted Study",
                 authors=["F. Fraud"], year=2018,
                 retraction={"type": "retraction", "label": "Retraction",
                             "date_parts": [[2020, 5, 1]], "source": "retraction-watch"})
        s.append((p, _ev(p.id, doi_ra="Crossref", hits=[h], doi=p.doi), "RETRACTED", "retracted"))

    # ── 元数据不符（期望 METADATA_MISMATCH）──
    # 年份差 ≥ 2（2 条）
    for i, (py, sy) in enumerate([(2020, 2017), (2019, 2022)]):
        p = parse_refs.ParsedRef(id=f"mY{i}", doi=f"10.1000/my{i}", title="Some Title",
                                 authors=["A"], year=py)
        h = _hit(doi=f"10.1000/my{i}", title="Some Title", authors=["A"], year=sy)
        s.append((p, _ev(p.id, doi_ra="Crossref", hits=[h], doi=f"10.1000/my{i}"),
                 "METADATA_MISMATCH", "mismatch"))
    # DOI 不符（2 条）
    for i in range(2):
        p = parse_refs.ParsedRef(id=f"mD{i}", doi=f"10.1000/md{i}", title="Title Q",
                                 authors=["B"], year=2020)
        h = _hit(doi=f"10.1000/wrong{i}", title="Title Q", authors=["B"], year=2020)
        s.append((p, _ev(p.id, doi_ra="Crossref", hits=[h], doi=f"10.1000/md{i}"),
                 "METADATA_MISMATCH", "mismatch"))
    # 标题低重叠（1 条）
    p = parse_refs.ParsedRef(id="mT", doi="10.1000/mt", title="Deep Learning Survey",
                             authors=["C"], year=2020)
    h = _hit(doi="10.1000/mt", title="Natural Language Processing", authors=["C"], year=2020)
    s.append((p, _ev(p.id, doi_ra="Crossref", hits=[h], doi="10.1000/mt"),
             "METADATA_MISMATCH", "mismatch"))
    # 第一作者不符（1 条）
    p = parse_refs.ParsedRef(id="mA", doi="10.1000/ma", title="Title Z",
                             authors=["Smith, John"], year=2020)
    h = _hit(doi="10.1000/ma", title="Title Z", authors=["Jones, Bob"], year=2020)
    s.append((p, _ev(p.id, doi_ra="Crossref", hits=[h], doi="10.1000/ma"),
             "METADATA_MISMATCH", "mismatch"))
    return s


class TestQuantitativeGates(unittest.TestCase):
    """三项专属发布门（spec §14）：检出率 ≥95% / 误报率 ≤5% / 中文误伤 = 0。"""

    def setUp(self):
        self.samples = _build_samples()
        self.results = [(cat, judge.judge(p, e).status, exp)
                        for p, e, exp, cat in self.samples]

    def test_sample_count_at_least_40(self):
        self.assertGreaterEqual(len(self.samples), 40,
                                f"混合样本应 ≥40 条，实际 {len(self.samples)}")

    def test_fabrication_detection_rate_ge_95(self):
        fab = [got for cat, got, _ in self.results if cat == "fabricated"]
        detected = sum(1 for g in fab if g == "NOT_FOUND")
        rate = detected / len(fab)
        self.assertGreaterEqual(rate, 0.95,
                                f"虚构引用检出率 {rate:.0%}（{detected}/{len(fab)}）< 95%")

    def test_real_false_positive_rate_le_5(self):
        real = [got for cat, got, _ in self.results if cat == "real"]
        fp = sum(1 for g in real if g != "VERIFIED")
        rate = fp / len(real)
        self.assertLessEqual(rate, 0.05,
                             f"真实引用误报率 {rate:.0%}（{fp}/{len(real)}）> 5%")

    def test_chinese_zero_false_accusation(self):
        cn = [got for cat, got, _ in self.results if cat == "chinese"]
        not_found = sum(1 for g in cn if g == "NOT_FOUND")
        self.assertEqual(not_found, 0,
                         f"真实中文文献误伤 {not_found} 条进 NOT_FOUND（硬约束⑤铁律违反）")

    def test_every_sample_matches_expected(self):
        # 每条样本判定与期望一致（量化门槛的逐条基础）
        for cat, got, exp in self.results:
            self.assertEqual(got, exp, f"[{cat}] 期望 {exp}，实得 {got}")

    def test_category_coverage(self):
        cats = {cat for cat, _, _ in self.results}
        for required in ("fabricated", "real", "chinese", "retracted", "mismatch"):
            self.assertIn(required, cats, f"样本缺 {required} 类别")


if __name__ == "__main__":
    unittest.main()
