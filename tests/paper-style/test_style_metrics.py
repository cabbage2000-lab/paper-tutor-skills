"""paper-style scripts/style_metrics.py 确定性单测——切句 / 特征 / 偏移 / CLI。"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "paper-style" / "scripts"))

import style_metrics as sm  # noqa: E402

DOC_TWO_SECTIONS = """---
name: 正文草稿
---

# 第一章 引言

近年来该领域快速发展。已有研究指出这一趋势（Smith, 2023）。本文尝试回答该问题。
研究方法尚未统一。因此有必要梳理。此外还需考虑边界条件。

| 项 | 内容 |
| --- | --- |
| 日期 | 2026-07-27 |

# 第二章 方法

本研究采用问卷调查，样本量为 3.14 万人。数据来自公开数据库[1]。
笔者认为该方法可行。我们进一步做了稳健性检验。这一点至关重要。
"""


class TestSplitSentences(unittest.TestCase):
    def test_句号在引号内不切句(self):
        """朴素 re.split 会在这里切出 2 句——这是最典型的错法。"""
        s = sm.split_sentences("他说：「这是对的。」然后走了。")
        self.assertEqual(len(s), 1)

    def test_引号后的主句标点照常切句(self):
        """引号内的句号不切，主句的两个句末标点各切一次 → 2 句。"""
        s = sm.split_sentences("他说：「这是对的。」我不同意。他走了。")
        self.assertEqual(len(s), 2)
        self.assertIn("「这是对的。」", s[0])

    def test_中文省略号算一个边界(self):
        s = sm.split_sentences("研究尚未定论……有待验证。")
        self.assertEqual([x for x in s], ["研究尚未定论……", "有待验证。"])

    def test_六点省略号也算一个边界(self):
        s = sm.split_sentences("结论未定......需要更多证据。")
        self.assertEqual(len(s), 2)

    def test_小数点不切句(self):
        s = sm.split_sentences("样本量为 3.14 万人。")
        self.assertEqual(len(s), 1)

    def test_英文缩写不切句(self):
        self.assertEqual(len(sm.split_sentences("见 Smith et al. 的研究。")), 1)
        self.assertEqual(len(sm.split_sentences("如 e.g. 这种情况。")), 1)

    def test_连续句末标点合并为一个边界(self):
        s = sm.split_sentences("真的吗？！确实。")
        self.assertEqual(len(s), 2)

    def test_分号切句且括号序号不干扰(self):
        s = sm.split_sentences("结论如下：（1）A；（2）B。")
        self.assertEqual(len(s), 2)

    def test_收尾引号归入前句(self):
        s = sm.split_sentences("他说：「对。」")
        self.assertTrue(s[0].endswith("」"))

    def test_英文句末照常切句(self):
        s = sm.split_sentences("This is one. That is two.")
        self.assertEqual(len(s), 2)


class TestStripMarkdown(unittest.TestCase):
    def test_剥离front_matter与表格与标题(self):
        clean = sm.strip_markdown(DOC_TWO_SECTIONS)
        self.assertNotIn("name: 正文草稿", clean)
        self.assertNotIn("| 日期 |", clean)
        self.assertNotIn("第一章 引言", clean)
        self.assertIn("近年来该领域快速发展", clean)

    def test_剥离代码块内容(self):
        clean = sm.strip_markdown("正文一句。\n\n```python\nx = 1  # 注释。\n```\n\n正文二句。")
        self.assertNotIn("x = 1", clean)
        self.assertEqual(len(sm.split_sentences(clean)), 2)

    def test_引用块被剥离因为那是他人文字(self):
        clean = sm.strip_markdown("我的观点如此。\n\n> 被引作者的长句引文在此。\n")
        self.assertNotIn("被引作者", clean)

    def test_链接保留文字图片整体剥离(self):
        clean = sm.strip_markdown("参见[该研究](literature/notes.md)的结论。\n\n![图1](f.png)")
        self.assertIn("该研究", clean)
        self.assertNotIn("literature/notes.md", clean)
        self.assertNotIn("图1", clean)

    def test_剥离四层标注符号(self):
        clean = sm.strip_markdown("👤 用户原话：这段是我写的。")
        self.assertNotIn("👤", clean)
        self.assertIn("这段是我写的", clean)


class TestEffectiveChars(unittest.TestCase):
    def test_标点与空白不计入字数(self):
        self.assertEqual(sm.effective_chars("你好，世界！"), 4)
        self.assertEqual(sm.effective_chars("a b\tc\n"), 3)


class TestCountWords(unittest.TestCase):
    def test_长词优先不重复计数(self):
        c = sm.count_words("除此之外，还有别的。此外，另有一点。", sm._FUNCTION_WORDS)
        self.assertEqual(c.get("除此之外"), 1)
        self.assertEqual(c.get("此外"), 1)

    def test_mask屏蔽后短词不误命中(self):
        c = sm.count_words("本文献综述表明，本文认为该问题成立。",
                           sm._PERSON_WORDS, mask=sm._PERSON_MASK)
        self.assertEqual(c.get("本文"), 1)


class TestCitationPositions(unittest.TestCase):
    def test_著者出版年制在句首(self):
        p = sm.citation_positions(["（Smith, 2023）指出该问题长期存在。"])
        self.assertEqual(p["句首"], 1)

    def test_著者出版年制在句末(self):
        p = sm.citation_positions(["该问题已有充分讨论（Smith, 2023）。"])
        self.assertEqual(p["句末"], 1)

    def test_顺序编码制在句中(self):
        p = sm.citation_positions(["多项针对不同人群的调查研究[1]表明了这一趋势的存在。"])
        self.assertEqual(p["句中"], 1)

    def test_顺序编码制支持多个与区间(self):
        p = sm.citation_positions(["已有工作对此有讨论[1,2]。", "另有综述[3-5]。"])
        self.assertEqual(p["句末"], 2)

    def test_非引用括号不误计(self):
        p = sm.citation_positions(["该方法（详见附录）不适用于本场景。"])
        self.assertEqual(sum(p.values()), 0)


class TestApproximateTerms(unittest.TestCase):
    def test_有术语表走精确路径(self):
        counts, src = sm.approximate_terms("神经网络很重要。神经网络需要数据。", ["神经网络"])
        self.assertEqual(src, "用户术语表")
        self.assertEqual(counts["神经网络"], 2)

    def test_无术语表走近似路径且标注来源(self):
        text = "神经网络的训练依赖数据。神经网络的结构复杂。神经网络的应用广泛。"
        counts, src = sm.approximate_terms(text)
        self.assertEqual(src, "重复串近似")
        self.assertIn("神经网络", counts)

    def test_近似路径屏蔽常用噪声词(self):
        text = "研究表明如此。研究表明依然。研究表明仍旧。"
        counts, _src = sm.approximate_terms(text)
        self.assertNotIn("研究", counts)


class TestMeasureSection(unittest.TestCase):
    def setUp(self):
        clean = sm.strip_markdown(DOC_TWO_SECTIONS)
        self.m = sm.measure_section("全文", clean)

    def test_句子数与字数为正(self):
        self.assertGreater(self.m.sentence_count, 5)
        self.assertGreater(self.m.char_count, 50)

    def test_句长三个统计量都算出(self):
        self.assertGreater(self.m.len_mean, 0)
        self.assertGreater(self.m.len_median, 0)
        self.assertGreaterEqual(self.m.len_std, 0)

    def test_样本足够时reliable为真(self):
        self.assertTrue(self.m.reliable)

    def test_样本不足时reliable为假(self):
        m = sm.measure_section("短", "一句话。两句话。三句话。四句话。")
        self.assertEqual(m.sentence_count, 4)
        self.assertFalse(m.reliable)

    def test_单句时标准差为零而不报错(self):
        m = sm.measure_section("单句", "只有一句话。")
        self.assertEqual(m.len_std, 0.0)

    def test_空文本不崩且各项为零(self):
        m = sm.measure_section("空", "")
        self.assertEqual(m.sentence_count, 0)
        self.assertEqual(m.len_mean, 0.0)

    def test_to_dict带近似值标记(self):
        d = self.m.to_dict()
        self.assertTrue(d["approximate"]["term_density_per_100"])
        self.assertTrue(d["approximate"]["quad_per_1000"])


class TestSplitSections(unittest.TestCase):
    def test_同层级有多节时按该层级切章(self):
        secs = sm.split_sections(DOC_TWO_SECTIONS)
        self.assertEqual([n for n, _b in secs], ["第一章 引言", "第二章 方法"])

    def test_只有二级标题时按二级切(self):
        text = "## 第 1 段\n\n正文甲。\n\n## 第 2 段\n\n正文乙。\n"
        self.assertEqual([n for n, _b in sm.split_sections(text)],
                         ["第 1 段", "第 2 段"])

    def test_单个顶级题目时下探到二级切章(self):
        """论文最常见形态：一个 `# 题目` + 一串 `## 第 N 章`。

        取最浅层级会只切出 1 节、让章节间偏移彻底失效——必须下探。
        """
        text = ("# 论文题目\n\n## 第一章 引言\n\n引言正文一句。引言正文二句。\n\n"
                "## 第二章 方法\n\n方法正文一句。方法正文二句。\n")
        self.assertEqual([n for n, _b in sm.split_sections(text)],
                         ["第一章 引言", "第二章 方法"])

    def test_无标题时整篇一节(self):
        secs = sm.split_sections("就是一段正文。没有任何标题。")
        self.assertEqual(len(secs), 1)
        self.assertEqual(secs[0][0], "全文")

    def test_标题前的正文单独成篇首节(self):
        secs = sm.split_sections("这是导语一句。\n\n# 第一章\n\n正文。")
        self.assertEqual(secs[0][0], "（篇首）")

    def test_代码块内的井号不当标题(self):
        text = "# 真标题\n\n正文。\n\n```sh\n# 这是注释不是标题\n```\n"
        self.assertEqual(len(sm.split_sections(text)), 1)


class TestCompareSections(unittest.TestCase):
    def test_单章节时不产偏移(self):
        c = sm.compare_sections([sm.measure_section("只此一节", "一句。两句。")])
        self.assertFalse(c["available"])
        self.assertIn("≥2", c["note"])

    def test_两章节产各特征极差与cv(self):
        a = sm.measure_section("短句章", "很短。也短。仍短。都短。挺短。")
        b = sm.measure_section(
            "长句章",
            "这一章的每个句子都写得相当冗长以至于句长均值会明显高于前一章的水平。"
            "本句同样刻意拉长用来把这一章的句长均值稳定地抬到一个更高的位置上。"
            "第三句依旧保持这种偏长的写法以避免样本量过小导致统计量不稳定。"
            "第四句继续维持相同的冗长风格从而让章节间的差异清晰可见。"
            "第五句用于把句子数补足到可以计算标准差的最低门槛之上。")
        c = sm.compare_sections([a, b])
        self.assertTrue(c["available"])
        f = c["per_feature"]["len_mean"]
        self.assertEqual(f["min_section"], "短句章")
        self.assertEqual(f["max_section"], "长句章")
        self.assertGreater(f["range"], 0)
        self.assertGreater(f["cv"], 0)

    def test_ranked按cv降序(self):
        a = sm.measure_section("甲", "很短。也短。仍短。都短。挺短。")
        b = sm.measure_section("乙", "此句略长一些但仍属中等长度范围之内。"
                                     "第二句同样属于中等长度的写法。"
                                     "第三句维持中等长度。第四句也是。第五句收尾。")
        ranked = sm.compare_sections([a, b])["ranked_by_cv"]
        cvs = [r["cv"] for r in ranked]
        self.assertEqual(cvs, sorted(cvs, reverse=True))


class TestCli(unittest.TestCase):
    def _write(self, tmp: str, name: str, text: str) -> str:
        p = pathlib.Path(tmp) / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_退出码0并产出可解析json(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._write(tmp, "正文.md", DOC_TWO_SECTIONS)
            out = str(pathlib.Path(tmp) / "m.json")
            self.assertEqual(sm.main(["--input", src, "--json", out]), 0)
            data = json.loads(pathlib.Path(out).read_text(encoding="utf-8"))
            self.assertEqual(data["mode"], "compare")
            self.assertEqual(len(data["sections"]), 2)
            self.assertTrue(data["comparison"]["available"])
            self.assertIn("term_density_per_100", data["approximate_notes"])

    def test_退出码2样本不足(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 全是表格与代码，剥离后无正文——不是错误，是可分析的正文太少
            src = self._write(tmp, "空.md", "| a | b |\n| --- | --- |\n\n```\nx=1\n```\n")
            self.assertEqual(sm.main(["--input", src]), 2)

    def test_退出码3读不到输入(self):
        self.assertEqual(sm.main(["--input", "/nonexistent/never.md"]), 3)

    def test_退出码3未指定输入(self):
        self.assertEqual(sm.main([]), 3)

    def test_退出码3目录不存在(self):
        self.assertEqual(sm.main(["--dir", "/nonexistent/dir"]), 3)

    def test_baseline模式合并成一份全局基线(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._write(tmp, "正文.md", DOC_TWO_SECTIONS)
            out = str(pathlib.Path(tmp) / "b.json")
            self.assertEqual(
                sm.main(["--input", src, "--json", out, "--baseline"]), 0)
            data = json.loads(pathlib.Path(out).read_text(encoding="utf-8"))
            self.assertEqual(data["mode"], "baseline")
            self.assertEqual(len(data["sections"]), 1)
            self.assertEqual(data["sections"][0]["name"], "全局基线")
            self.assertFalse(data["comparison"]["available"])

    def test_dir模式多文件按文件名排序且节名带文件名(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "b章.md", "# 乙\n\n乙章正文一句。乙章正文二句。")
            self._write(tmp, "a章.md", "# 甲\n\n甲章正文一句。甲章正文二句。")
            out = str(pathlib.Path(tmp) / "m.json")
            self.assertEqual(sm.main(["--dir", tmp, "--json", out]), 0)
            data = json.loads(pathlib.Path(out).read_text(encoding="utf-8"))
            names = [s["name"] for s in data["sections"]]
            self.assertEqual(names, ["a章.md · 甲", "b章.md · 乙"])

    def test_terms参数走精确术语路径(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._write(tmp, "正文.md", "神经网络很重要。神经网络需要数据。")
            terms = self._write(tmp, "terms.txt", "神经网络\n")
            out = str(pathlib.Path(tmp) / "m.json")
            self.assertEqual(
                sm.main(["--input", src, "--terms", terms, "--json", out]), 0)
            data = json.loads(pathlib.Path(out).read_text(encoding="utf-8"))
            self.assertEqual(data["sections"][0]["term_source"], "用户术语表")

    def test_终端文本输出不崩(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._write(tmp, "正文.md", DOC_TWO_SECTIONS)
            self.assertEqual(sm.main(["--input", src]), 0)


if __name__ == "__main__":
    unittest.main()
