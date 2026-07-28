"""paper-verify scripts/parse_refs.py 确定性单测。

导入范式同 tests/paper-search/test_search_pipeline.py（sys.path 加 _shared 与 scripts）。
验证外部可观察行为（解析得什么字段、parse_status 标记得对不对），不测实现细节。
"""
from __future__ import annotations

import pathlib
import sys
import unittest

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "_shared"))
sys.path.insert(0, str(_REPO / "skills" / "paper-verify" / "scripts"))

import parse_refs  # noqa: E402


class TestParseBib(unittest.TestCase):
    def test_single_entry_full_fields(self):
        bib = ('@article{smith2020,\n'
               '  title = {AI in Education},\n'
               '  author = {Smith, John and Doe, Jane},\n'
               '  year = {2020},\n'
               '  journal = {Journal of Tech},\n'
               '  doi = {10.1038/nature12373}}')
        refs = parse_refs.parse_bib(bib)
        self.assertEqual(len(refs), 1)
        r = refs[0]
        self.assertEqual(r.doi, "10.1038/nature12373")
        self.assertEqual(r.title, "AI in Education")
        self.assertEqual(r.year, 2020)
        self.assertEqual(r.venue, "Journal of Tech")
        self.assertEqual(r.authors, ["Smith, John", "Doe, Jane"])
        self.assertEqual(r.parse_status, "ok")

    def test_multiple_entries(self):
        bib = '@article{a, title={T1}, doi={10.1/a}}\n@article{b, title={T2}, doi={10.1/b}}'
        refs = parse_refs.parse_bib(bib)
        self.assertEqual(len(refs), 2)
        self.assertEqual([r.doi for r in refs], ["10.1/a", "10.1/b"])

    def test_value_with_inner_comma_not_truncated(self):
        # {} 包裹的值内含逗号，不应被提前截断（朴素正则用 \} 闭合处理）
        bib = '@article{x, title={A, B and C}, author={Smith, J and Doe, R}, year={2019}}'
        refs = parse_refs.parse_bib(bib)
        self.assertEqual(refs[0].title, "A, B and C")
        self.assertEqual(refs[0].authors, ["Smith, J", "Doe, R"])


class TestParseSingle(unittest.TestCase):
    def test_single_doi(self):
        r = parse_refs.parse_single("10.1038/nature12373")
        self.assertEqual(r.doi, "10.1038/nature12373")
        self.assertEqual(r.parse_status, "ok")

    def test_single_doi_with_url_prefix(self):
        r = parse_refs.parse_single("https://doi.org/10.1038/nature12373")
        self.assertEqual(r.doi, "10.1038/nature12373")

    def test_single_doi_with_parentheses(self):
        """回归：Lancet / Elsevier 老式 DOI 含成对括号，不得截断。

        截断成 '10.1016/S0140-6736(97' 会查不到，让真实文献落 NOT_FOUND
        「疑似不存在的引用」——把真文献误指为假，比漏检更坏。
        """
        for raw in ("10.1016/S0140-6736(97)11096-0",
                    "https://doi.org/10.1016/S0140-6736(97)11096-0",
                    "https://doi.org/10.1016/S0140-6736(97)11096-0."):
            with self.subTest(raw=raw):
                self.assertEqual(parse_refs.parse_single(raw).doi,
                                 "10.1016/S0140-6736(97)11096-0")

    def test_single_doi_trailing_unpaired_paren(self):
        # markdown 链接的收尾括号不属于 DOI
        self.assertEqual(parse_refs.parse_single("[DOI](https://doi.org/10.1234/abc)").doi,
                         "10.1234/abc")

    def test_single_title(self):
        r = parse_refs.parse_single("Some Research Title Here")
        self.assertEqual(r.title, "Some Research Title Here")
        self.assertIsNone(r.doi)

    def test_empty(self):
        r = parse_refs.parse_single("")
        self.assertEqual(r.parse_status, "unparsed")


class TestParseText(unittest.TestCase):
    def test_gbt_line_extracts_all_fields(self):
        line = "[1] 王明, 李华. 某某研究[J]. 学报, 2020, 15(3): 1-9. DOI: 10.1038/xxx"
        refs = parse_refs.parse_text(line)
        self.assertEqual(len(refs), 1)
        r = refs[0]
        self.assertEqual(r.doi, "10.1038/xxx")
        self.assertEqual(r.year, 2020)
        self.assertEqual(r.type, "[J]")
        self.assertEqual(r.authors, ["王明, 李华"])
        self.assertEqual(r.title, "某某研究")

    def test_apa_line_extracts_all_fields(self):
        line = ("Smith, J. (2020). AI in Education. Journal of Tech, 15(3), "
                "100-115. https://doi.org/10.1038/yyy")
        refs = parse_refs.parse_text(line)
        r = refs[0]
        self.assertEqual(r.doi, "10.1038/yyy")
        self.assertEqual(r.year, 2020)
        self.assertEqual(r.authors, ["Smith, J"])
        self.assertEqual(r.title, "AI in Education")

    def test_apa_spaced_initials_do_not_break_title(self):
        """回归：APA 把缩写写成 'A. J.'（点后带空格）时，作者段不得切在人名中间。

        按句号切会得到 authors=['Wakefield, A'] / title='J., Murch, S'，一条正确
        引用于是误报 title 与 first_author 不符。改用 '(年份).' 锚点切分。
        """
        line = ("Wakefield, A. J., Murch, S. H., Anthony, A., et al. (1998). "
                "Ileal-lymphoid-nodular hyperplasia, non-specific colitis, and "
                "pervasive developmental disorder in children. The Lancet, 351(9103), 637-641.")
        r = parse_refs.parse_text(line)[0]
        self.assertEqual(r.title, "Ileal-lymphoid-nodular hyperplasia, non-specific "
                                  "colitis, and pervasive developmental disorder in children")
        self.assertTrue(r.authors[0].startswith("Wakefield, A. J."))
        self.assertEqual(r.year, 1998)

    def test_apa_year_suffix_letter(self):
        # APA 同年多篇用 '(2020a)'，锚点须一并识别
        r = parse_refs.parse_text("Doe, J. A. (2020a). A study of things. J. Examples.")[0]
        self.assertEqual(r.title, "A study of things")
        self.assertEqual(r.authors, ["Doe, J. A"])

    def test_gbt_still_uses_dot_split(self):
        # 无 '(年份)' 锚点 → 退回句号切分，行为不变
        r = parse_refs.parse_text("Smith, J. The title here. Journal Name, 2020.")[0]
        self.assertEqual(r.authors, ["Smith, J"])
        self.assertEqual(r.title, "The title here")

    def test_multiline_gbt_each_line_one_ref(self):
        text = "[1] 张三. 研究一[J]. 学报, 2019.\n[2] 李四. 研究二[M]. 出版社, 2020."
        refs = parse_refs.parse_text(text)
        self.assertEqual(len(refs), 2)
        self.assertEqual(refs[0].year, 2019)
        self.assertEqual(refs[1].year, 2020)
        self.assertEqual(refs[1].type, "[M]")

    def test_bib_detected_via_parse_text(self):
        text = "@article{x, title={T}, doi={10.1/x}}"
        refs = parse_refs.parse_text(text)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].doi, "10.1/x")

    def test_empty_and_whitespace(self):
        self.assertEqual(parse_refs.parse_text(""), [])
        self.assertEqual(parse_refs.parse_text("   \n  "), [])

    def test_unparsable_garbage_marked(self):
        # 无 DOI、无可识别标题的乱码 → unparsed（不硬凑字段）
        refs = parse_refs.parse_text(",,, ;;; 123")
        self.assertEqual(refs[0].parse_status, "unparsed")


class TestParsedRefContract(unittest.TestCase):
    def test_to_ref_dict_drops_venue_type(self):
        # 送 fetch_batch 的字段集不含 venue/type/parse_status（取证层不需要）
        r = parse_refs.ParsedRef(id="r1", doi="10.1/x", title="T", authors=["A"],
                                 year=2020, venue="V", type="[J]", raw_text="raw")
        d = r.to_ref_dict()
        self.assertEqual(d, {"id": "r1", "doi": "10.1/x", "title": "T",
                             "authors": ["A"], "year": 2020, "raw_text": "raw"})
        self.assertNotIn("venue", d)
        self.assertNotIn("type", d)


if __name__ == "__main__":
    unittest.main()
