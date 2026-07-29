"""paper-anchor scripts/anchor_scan.py 确定性单测——四形态计数 / 零引用定位 / 退出码。

两条**最高优先级回归**（对应实现计划里记的冲突 A / B，搞错则「已经做对的段落」被
判成缺支撑，且不报错）：

  · `test_只有引用块的段不算零引用` —— 人文的文本引证（冲突 A）
  · `test_只有锚点链接的段不算零引用` —— outline / draft 的锚点格式（冲突 B）

还有一条产品底线的守卫：`test_输出不含任何判定词`——脚本只出计数，判定归模型与用户。
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "paper-anchor" / "scripts"))

import anchor_scan  # noqa: E402

DOC = """# 第一章 引言

近年来该现象日益普遍，已有研究表明此点（张三, 2020）。

本研究采用 Z 量表测量该变量。

综合来看，多项研究支持这一结论[1,2]。

参见 [Smith 2023](literature/文献笔记表.md#smith2023) 的论述。

> 被引作者的长句引文在此，占两行。
> 第二行引文在此。

| 表头 | 表头 |
| --- | --- |
| 数据 | 数据 |
"""


class TestScanBasics(unittest.TestCase):

    def setUp(self):
        self.payload = anchor_scan.scan([("正文.md", DOC)])
        self.paras = self.payload["paragraphs"]

    def test_标题与表格不计入段落(self):
        # 5 段正文：著者年 / 零引用 / 编码 / 锚点 / 引用块
        self.assertEqual(self.payload["coverage"]["total_paragraphs"], 5)

    def test_序号连续从1起(self):
        self.assertEqual([p["index"] for p in self.paras], [1, 2, 3, 4, 5])

    def test_著者出版年制计数(self):
        self.assertEqual(self.paras[0]["inline_citations"]["著者-出版年制"], 1)
        self.assertEqual(self.paras[0]["total_citations"], 1)

    def test_顺序编码制计数(self):
        self.assertEqual(self.paras[2]["inline_citations"]["顺序编码制"], 1)

    def test_只有锚点链接的段不算零引用(self):
        """冲突 B 回归：`[X](literature/…)` 就是挂上的锚点，不是噪声。"""
        p = self.paras[3]
        self.assertEqual(p["anchor_links"], 1)
        self.assertEqual(p["total_citations"], 1)
        self.assertNotIn(p["index"], self.payload["zero_citation_indices"])

    def test_只有引用块的段两边都不归_单列待确认(self):
        """冲突 A 回归 + 真实语料验证出的歧义：`>` 既是文本引证也是排版强调框。

        两边都不选：不进零引用（人文的文本引证不该被判缺支撑），也不计入
        total_citations（排版强调框不该被虚报成支撑）。同 verify 的「待人工核对」。
        """
        p = self.paras[4]
        self.assertEqual(p["blockquote_lines"], 2)
        self.assertEqual(p["total_citations"], 0)
        self.assertNotIn(p["index"], self.payload["zero_citation_indices"])
        self.assertIn(p["index"], self.payload["blockquote_only_indices"])

    def test_引用块歧义须在notes里声明(self):
        self.assertTrue(any("排版强调" in n for n in self.payload["notes"]))

    def test_零引用段定位(self):
        self.assertEqual(self.payload["zero_citation_indices"], [2])
        self.assertIn("Z 量表", self.paras[1]["first_sentence"])

    def test_四形态全部检出(self):
        self.assertEqual(
            self.payload["citation_forms_found"],
            ["锚点链接", "著者-出版年制", "顺序编码制", "引用块"])

    def test_引导句段标出下一段是引用块(self):
        """机械事实，供模型解读；脚本不推断「所以这段有支撑」。"""
        self.assertTrue(self.paras[3]["followed_by_blockquote"])
        self.assertFalse(self.paras[0]["followed_by_blockquote"])

    def test_覆盖统计(self):
        cov = self.payload["coverage"]
        self.assertEqual(cov["zero_citation_count"], 1)
        self.assertEqual(cov["blockquote_only_count"], 1)
        # 锚点 1 + 著者年 1 + 编码 1；引用块不计入（歧义，单列）
        self.assertEqual(cov["total_citations"], 3)
        self.assertGreater(cov["char_count"], 0)
        self.assertGreater(cov["citation_density_per_1000"], 0)

    def test_输出不含任何判定词(self):
        """脚本只出计数——「缺支撑 / 不足 / 建议补」是模型与用户的判断，不是它的。"""
        blob = json.dumps(self.payload, ensure_ascii=False)
        for word in ("缺支撑", "缺文献", "支撑不足", "不足", "偏低", "偏少",
                     "需要引用", "建议补", "应当引"):
            with self.subTest(word=word):
                self.assertNotIn(word, blob)


class TestWarningMarks(unittest.TestCase):

    def test_提取draft既有标记(self):
        doc = ("本段论述某观点。⚠️ 未经文献支撑（锚点 Lee 2024 未在 literature/）\n\n"
               "另一段正文（张三, 2020）。")
        payload = anchor_scan.scan([("正文.md", doc)])
        self.assertEqual(payload["coverage"]["warning_count"], 1)
        mark = payload["warning_marks"][0]
        self.assertEqual(mark["paragraph"], 1)
        self.assertEqual(mark["source"], "正文.md")
        self.assertIn("未经文献支撑", mark["line"])

    def test_标记里的年份不被当成引用(self):
        """draft 的标记含「（锚点 Lee 2024 未在 literature/）」——括号里有 4 位年份，
        不剔就会被著者-出版年制正则命中，让标了缺支撑的段反而算成有引用（真实语料撞到过）。
        """
        doc = "本段讨论样本差异。⚠️ 未经文献支撑（锚点 Lee 2024 未在 literature/）"
        payload = anchor_scan.scan([("正文.md", doc)])
        p = payload["paragraphs"][0]
        self.assertEqual(p["inline_citations"]["著者-出版年制"], 0)
        self.assertEqual(p["total_citations"], 0)
        self.assertEqual(payload["zero_citation_indices"], [1])
        # 正文仍在（不是整行剔掉）、标记也仍被记录
        self.assertIn("样本差异", p["first_sentence"])
        self.assertEqual(payload["coverage"]["warning_count"], 1)

    def test_outline格式剔标记但保留要点正文(self):
        """`- ⚠️ <要点> · 纯结构占位（无文献支撑）`——整行剔会丢要点、让缺口漏报。"""
        payload = anchor_scan.scan(
            [("大纲.md", "- ⚠️ 混合式学习的长期效应 · 纯结构占位（无文献支撑）")])
        self.assertEqual(payload["coverage"]["total_paragraphs"], 1)
        self.assertIn("混合式学习", payload["paragraphs"][0]["first_sentence"])
        self.assertEqual(payload["zero_citation_indices"], [1])

    def test_提取outline纯结构占位并附说明(self):
        doc = "- ⚠️ 某要点 · 纯结构占位（无文献支撑）\n\n正文一句。"
        payload = anchor_scan.scan([("大纲.md", doc)])
        self.assertEqual(payload["coverage"]["warning_count"], 1)
        self.assertTrue(any("纯结构占位" in n for n in payload["notes"]))


class TestDegradation(unittest.TestCase):

    def test_全脚注制须声明不可用(self):
        doc = "此点已有研究[^1]。\n\n另一段亦然[^2]。"
        payload = anchor_scan.scan([("正文.md", doc)])
        self.assertEqual(payload["citation_forms_found"], [])
        self.assertEqual(payload["coverage"]["zero_citation_count"], 2)
        self.assertTrue(any("全脚注制" in n for n in payload["notes"]))

    def test_代码块不计入段落(self):
        doc = "正文一句（张三, 2020）。\n\n```python\nx = 1\n\ny = 2\n```\n"
        payload = anchor_scan.scan([("正文.md", doc)])
        self.assertEqual(payload["coverage"]["total_paragraphs"], 1)

    def test_纯标题输入无正文段(self):
        payload = anchor_scan.scan([("空.md", "# 标题\n\n## 二级标题\n")])
        self.assertEqual(payload["coverage"]["total_paragraphs"], 0)

    def test_首句过长截断(self):
        doc = "这" * 100 + "。"
        payload = anchor_scan.scan([("正文.md", doc)])
        self.assertTrue(payload["paragraphs"][0]["first_sentence"].endswith("…"))
        self.assertLessEqual(len(payload["paragraphs"][0]["first_sentence"]), 31)


class TestMultiFile(unittest.TestCase):

    def test_多文件序号全局连续且标来源(self):
        payload = anchor_scan.scan([
            ("一章.md", "甲段正文（张三, 2020）。"),
            ("二章.md", "乙段正文。\n\n丙段正文[3]。"),
        ])
        self.assertEqual([p["index"] for p in payload["paragraphs"]], [1, 2, 3])
        self.assertEqual([p["source"] for p in payload["paragraphs"]],
                         ["一章.md", "二章.md", "二章.md"])
        self.assertEqual(payload["zero_citation_indices"], [2])


class TestCLI(unittest.TestCase):

    def test_正常输入退出0并写json(self):
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "正文.md"
            src.write_text(DOC, encoding="utf-8")
            out = pathlib.Path(td) / "scan.json"
            code = anchor_scan.main(["--input", str(src), "--json", str(out)])
            self.assertEqual(code, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["coverage"]["total_paragraphs"], 5)

    def test_目录输入(self):
        with tempfile.TemporaryDirectory() as td:
            (pathlib.Path(td) / "a.md").write_text("甲段（张三, 2020）。", encoding="utf-8")
            (pathlib.Path(td) / "b.md").write_text("乙段无引用。", encoding="utf-8")
            code = anchor_scan.main(["--dir", td])
            self.assertEqual(code, 0)

    def test_样本不足退出2(self):
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "空.md"
            src.write_text("# 只有标题\n", encoding="utf-8")
            self.assertEqual(anchor_scan.main(["--input", str(src)]), 2)

    def test_读不到输入退出3(self):
        self.assertEqual(anchor_scan.main(["--input", "/nonexistent/x.md"]), 3)

    def test_读不到目录退出3(self):
        self.assertEqual(anchor_scan.main(["--dir", "/nonexistent/dir"]), 3)

    def test_未指定输入退出3(self):
        self.assertEqual(anchor_scan.main([]), 3)


if __name__ == "__main__":
    unittest.main()
