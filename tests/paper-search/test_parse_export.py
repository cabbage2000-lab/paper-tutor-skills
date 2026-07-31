"""paper-search scripts/parse_export.py 的确定性逻辑单测：BibTeX / RIS 解析、水印清洗、
输出契约同形。

导入范式同 test_search_pipeline.py（sys.path 加 _shared 与 skill scripts 后 import）。
验证外部可观察行为，不测实现细节。
"""
from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "_shared"))
sys.path.insert(0, str(_REPO / "skills" / "paper-search" / "scripts"))

import parse_export  # noqa: E402

# 知网页面 / 导出里实测到的不可见水印字符（各 Cf 类一枚，含 JS `\s` 会误吃的 U+FEFF）
_WM = "​‏⁠﻿⁭"


class TestStripInvisible(unittest.TestCase):
    def test_removes_format_chars(self):
        self.assertEqual(parse_export.strip_invisible(f"大语言{_WM}模型"), "大语言模型")

    def test_feff_inside_word_does_not_become_space(self):
        """回归：U+FEFF 落在单词内部时必须被删除，不能替换成空格。

        opencli 的 cnki adapter 就是先做 `\\s+ → ' '` 折叠再取文本，而 JS 正则的 `\\s`
        涵盖 U+FEFF，于是 `content` 被打成 `c ontent` —— 假词边界不可逆，题名就废了。
        本测试锁死「先删 Cf、再折叠空白」的顺序。"""
        self.assertEqual(parse_export.strip_invisible("c﻿ontent"), "content")
        self.assertEqual(parse_export.strip_invisible("mod​el-⁯dri​ven"),
                         "model-driven")

    def test_collapses_real_whitespace(self):
        self.assertEqual(parse_export.strip_invisible("  a   b \n c "), "a b c")


class TestWatermarkWarning(unittest.TestCase):
    def test_visible_watermark_warns_but_not_deleted(self):
        entries = [{"title": "A 版权Study of NLP"}]
        w = parse_export.watermark_warning(entries)
        self.assertIsNotNone(w)
        self.assertIn("版权", w)

    def test_clean_titles_no_warning(self):
        self.assertIsNone(parse_export.watermark_warning([{"title": "干净的题名"}]))

    def test_watermark_word_is_never_stripped_from_title(self):
        """可见水印词只告警不删：真实题名里「版权」可能是正文，删了就破坏题名（红线 1
        的判断归用户）。"""
        bib = "@article{k, title = {数字出版版权保护研究}, year = {2024},}"
        entries, _ = parse_export.parse_bibtex(bib)
        self.assertEqual(entries[0]["title"], "数字出版版权保护研究")


class TestParseBibtex(unittest.TestCase):
    def test_nested_braces_in_value(self):
        bib = "@article{k, title = {A {BERT} Study of {Chinese} NLP}, year = {2025},}"
        entries, skipped = parse_export.parse_bibtex(bib)
        self.assertEqual(entries[0]["title"], "A BERT Study of Chinese NLP")
        self.assertEqual(skipped, [])

    def test_chinese_authors_split_and_not_reordered(self):
        bib = "@article{k, title = {T}, author = {张三 and 李四 and Wang, Wu},}"
        entries, _ = parse_export.parse_bibtex(bib)
        # `Wang, Wu` 原样保留——姓名重排是 paper-format 的职责，检索层重排会把中文名倒过来
        self.assertEqual(entries[0]["authors"], ["张三", "李四", "Wang, Wu"])

    def test_type_mapping_and_doi_normalized(self):
        bib = ("@inproceedings{k, title = {T}, booktitle = {会议}, "
               "doi = {https://doi.org/10.1/AB},}")
        entries, _ = parse_export.parse_bibtex(bib)
        self.assertEqual(entries[0]["type"], "conference-paper")
        self.assertEqual(entries[0]["venue"], "会议")
        self.assertEqual(entries[0]["doi"], "10.1/ab")

    def test_quoted_value_and_year_extraction(self):
        bib = '@article{k, title = "带引号的题名", year = "2023", journal = {刊},}'
        entries, _ = parse_export.parse_bibtex(bib)
        self.assertEqual(entries[0]["title"], "带引号的题名")
        self.assertEqual(entries[0]["year"], 2023)

    def test_unclosed_entry_skipped_not_swallowed(self):
        bib = "@article{ok, title = {好条目}, year = {2024},}\n@article{bad, author = {残"
        entries, skipped = parse_export.parse_bibtex(bib)
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(skipped), 1)
        self.assertIn("未闭合", skipped[0])

    def test_watermark_chars_cleaned_in_title(self):
        bib = "@article{k, title = {大语言%s模型研究}, year = {2026},}" % _WM
        entries, _ = parse_export.parse_bibtex(bib)
        self.assertEqual(entries[0]["title"], "大语言模型研究")


class TestParseRis(unittest.TestCase):
    def _ris(self, body):
        return parse_export.parse_ris(body)

    def test_basic_fields_and_multi_authors(self):
        ris = ("TY  - JOUR\nTI  - 题名\nAU  - 甲\nAU  - 乙\nJO  - 刊名\n"
               "PY  - 2026/07//\nVL  - 25\nIS  - 7\nSP  - 45\nEP  - 52\n"
               "DO  - 10.1/x\nER  - \n")
        entries, skipped = self._ris(ris)
        e = entries[0]
        self.assertEqual((e["title"], e["venue"], e["year"]), ("题名", "刊名", 2026))
        self.assertEqual(e["authors"], ["甲", "乙"])
        self.assertEqual((e["volume"], e["issue"], e["pages"]), ("25", "7", "45-52"))
        self.assertEqual(e["type"], "journal-article")
        self.assertEqual(skipped, [])

    def test_chinese_continuation_joins_without_space(self):
        """中文折行续行不补空格：题名是无 DOI 时的去重主键，多一个空格就跟 API 侧对不上。"""
        ris = "TY  - JOUR\nTI  - 基于大语言模型的案例检索研究\n      与实证分析\nER  - \n"
        entries, _ = self._ris(ris)
        self.assertEqual(entries[0]["title"], "基于大语言模型的案例检索研究与实证分析")

    def test_english_continuation_joins_with_space(self):
        ris = "TY  - JOUR\nTI  - A Study of Large Language\n      Models in Education\nER  - \n"
        entries, _ = self._ris(ris)
        self.assertEqual(entries[0]["title"],
                         "A Study of Large Language Models in Education")

    def test_entry_without_title_skipped(self):
        ris = "TY  - JOUR\nAU  - 无题名\nER  - \n"
        entries, skipped = self._ris(ris)
        self.assertEqual(entries, [])
        self.assertIn("题名", skipped[0])

    def test_last_entry_without_er_still_parsed(self):
        """导出文件被截断时能救回的条目要救——缺 ER 不等于该条不存在。"""
        ris = "TY  - JOUR\nTI  - 第一条\nER  - \nTY  - JOUR\nTI  - 末条无 ER\n"
        entries, _ = self._ris(ris)
        self.assertEqual([e["title"] for e in entries], ["第一条", "末条无 ER"])

    def test_type_mapping_thesis(self):
        entries, _ = self._ris("TY  - THES\nTI  - 学位论文\nER  - \n")
        self.assertEqual(entries[0]["type"], "thesis")

    def test_unknown_ty_leaves_type_none(self):
        """映射不了就是 None——猜一个类型会污染下游的 type 筛选。"""
        entries, _ = self._ris("TY  - XXXX\nTI  - 未知类型\nER  - \n")
        self.assertIsNone(entries[0]["type"])


class TestDetectFormat(unittest.TestCase):
    def test_detects_ris_and_bibtex(self):
        self.assertEqual(parse_export.detect_format("TY  - JOUR\nTI  - x\n"), "ris")
        self.assertEqual(parse_export.detect_format("@article{k, title={x}}"), "bibtex")

    def test_unknown_returns_none(self):
        """判不出返回 None：猜错会把整份文件解析成 0 条，让人误以为导出里没文献。"""
        self.assertIsNone(parse_export.detect_format("张三. 题名[J]. 刊, 2024, 1(2): 3."))


class TestOutputContract(unittest.TestCase):
    def test_result_shape_matches_search_py(self):
        """与 search.py 的 dedup_hits 输出同形，宿主才能并进同一张表、走同一套去重。"""
        import search  # noqa: WPS433 — 同目录脚本，验证契约同形
        entries, _ = parse_export.parse_bibtex(
            "@article{k, title = {T}, author = {甲}, year = {2024}, doi = {10.1/x},}")
        r = parse_export.to_result(entries[0], "cnki")
        hit = search.dedup_hits([_fake_hit()])[0]
        for key in ("title", "authors", "year", "date", "venue", "doi", "type", "url",
                    "sources", "primary_source", "from_cache", "retraction"):
            self.assertIn(key, r, f"results 缺 search.py 契约字段 {key}")
            self.assertIn(key, hit)

    def test_date_and_retraction_always_none(self):
        """导出只给到年 → date 恒 None（不用 year 凑）；导出无撤稿信息 → retraction 恒
        None（「没查过」≠「没被撤稿」，撤稿判定归 /paper-verify）。"""
        entries, _ = parse_export.parse_bibtex("@article{k, title={T}, year={2024},}")
        r = parse_export.to_result(entries[0], "cnki")
        self.assertIsNone(r["date"])
        self.assertIsNone(r["retraction"])
        self.assertEqual(r["coverage_mode"], "user_export")

    def test_payload_declares_user_export_not_auto_search(self):
        """覆盖方式必须是 user_export：把导出说成自动检索会违反红线 2 的如实声明。"""
        entries, skipped = parse_export.parse_bibtex(
            "@article{k, title={T}, year={2024}, doi={10.1/x},}")
        p = parse_export.build_payload("f.bib", "bibtex", "cnki", entries, skipped)
        self.assertEqual(p["coverage"][0]["mode"], "user_export")
        self.assertEqual(p["coverage"][0]["hit_count"], 1)
        self.assertEqual(p["stats"], {"parsed": 1, "skipped": 0})

    def test_skipped_reasons_surface_in_warnings(self):
        """跳过的条目不许静默丢弃——同 search.py 的 truncation_warning 精神。"""
        entries, skipped = parse_export.parse_bibtex(
            "@article{ok, title={好}, year={2024}, doi={10.1/x},}\n@article{bad, a = {残")
        p = parse_export.build_payload("f.bib", "bibtex", "cnki", entries, skipped)
        self.assertTrue(any("未闭合" in w for w in p["warnings"]))

    def test_no_doi_warning_does_not_imply_nonexistence(self):
        entries, skipped = parse_export.parse_bibtex("@article{k, title={无DOI}, year={2024},}")
        p = parse_export.build_payload("f.bib", "bibtex", "cnki", entries, skipped)
        self.assertTrue(any("不得据此判定文献不存在" in w for w in p["warnings"]))


class TestCli(unittest.TestCase):
    def test_gbk_encoded_file_is_read(self):
        """知网 / 万方导出偶为 GBK：解码失败不是「文件没内容」，如实换码重试。"""
        with tempfile.NamedTemporaryFile("wb", suffix=".bib", delete=False) as f:
            f.write("@article{k, title = {中文题名}, year = {2024},}".encode("gbk"))
            path = f.name
        try:
            text = pathlib.Path(path).read_text(encoding="gbk")
            entries, _ = parse_export.parse_bibtex(text)
            self.assertEqual(entries[0]["title"], "中文题名")
        finally:
            pathlib.Path(path).unlink()

    def test_unparsable_format_exits_nonzero(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as f:
            f.write("张三. 题名[J]. 刊名, 2024, 1(2): 3-4.\n")
            path = f.name
        try:
            self.assertEqual(parse_export.main(["--in", path]), 2)
        finally:
            pathlib.Path(path).unlink()


def _fake_hit():
    from paper_shared.datasources.models import SourceHit
    return SourceHit(source="crossref",
                     metadata={"title": "T", "doi": "10.1/x", "year": 2024,
                               "venue": "V", "type": "journal-article",
                               "authors": ["甲"], "date": None},
                     fetched_at="2026-01-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
