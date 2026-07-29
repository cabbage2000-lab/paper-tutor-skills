"""`_shared/paper_shared/citations.py` 单测——两个消费者的口径差异与顺序依赖。

本文件**不重复** `tests/paper-style/test_style_metrics.py` 已覆盖的切句与预处理
断言（那 51 条是搬迁的等价性安全网，已在原地全绿）。这里只测：

  · `paper-anchor` 侧新增的四个计数函数与 `split_paragraphs`；
  · `drop_blockquote` 参数化开关的两种口径；
  · **三条顺序依赖**——锚点链接、⚠️ 标记、行内引用各自对「原始文本 / 已剥文本」
    的要求相反，搞反不报错、只静默算错，故每条都要有回归测试钉住；
  · 一条防「第二份真相复活」的守卫：`paper-style` 用的必须是同一个实现对象。
"""
from __future__ import annotations

import pathlib
import sys
import unittest

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "_shared"))

from paper_shared import citations  # noqa: E402


class TestBlockquoteSwitch(unittest.TestCase):
    """`drop_blockquote`：style 剥引用块、anchor 保留并计数（口径相反）。"""

    RAW = "我的观点如此。\n\n> 被引作者的长句引文在此。\n\n后续论述。"

    def test_默认剥引用块_style口径(self):
        clean = citations.strip_markdown(self.RAW)
        self.assertNotIn("被引作者", clean)
        self.assertIn("我的观点", clean)

    def test_关掉开关则保留引用块正文_anchor口径(self):
        clean = citations.strip_markdown(self.RAW, drop_blockquote=False)
        self.assertIn("被引作者的长句引文在此", clean)
        self.assertNotIn(">", clean)          # 只去前缀、留正文

    def test_多级引用前缀也剥干净(self):
        clean = citations.strip_markdown(">> 嵌套引文。", drop_blockquote=False)
        self.assertEqual(clean, "嵌套引文。")

    def test_空引用行不产空段(self):
        clean = citations.strip_markdown(">\n> 正文。", drop_blockquote=False)
        self.assertEqual(clean, "正文。")


class TestAnchorLinks(unittest.TestCase):
    """指向 `literature/` 的 markdown 链接 = 挂上的文献锚点。"""

    def test_命中笔记表锚点(self):
        raw = "见 [Smith 2023](literature/文献笔记表.md#smith2023) 的结论。"
        self.assertEqual(citations.count_anchor_links(raw), 1)

    def test_相对前缀不影响命中(self):
        # 产物落在 manuscript/ 还是项目根，相对深度不同
        for target in ("literature/n.md", "./literature/n.md", "../literature/n.md"):
            with self.subTest(target=target):
                self.assertEqual(
                    citations.count_anchor_links(f"见 [X]({target})#a 的结论。"), 1)

    def test_外链不算锚点(self):
        self.assertEqual(
            citations.count_anchor_links("见 [Smith 2023](https://example.com)。"), 0)

    def test_指向manuscript的链接不算锚点(self):
        # 内部交叉引用不是文献支撑
        self.assertEqual(citations.count_anchor_links("见 [图 1](manuscript/图.png)。"), 0)

    def test_一段多个锚点各自计数(self):
        raw = ("[A 2020](literature/n.md#a) 与 [B 2021](literature/n.md#b) 均有此结论。")
        self.assertEqual(citations.count_anchor_links(raw), 2)

    def test_顺序依赖_必须用原始文本(self):
        """剥完 markdown 再数一律为 0，且不报错——本模块最容易踩的坑。"""
        raw = "见 [Smith 2023](literature/文献笔记表.md#smith2023)。"
        self.assertEqual(citations.count_anchor_links(raw), 1)
        self.assertEqual(
            citations.count_anchor_links(citations.strip_markdown(raw)), 0)


class TestWarningMarks(unittest.TestCase):
    """既有缺口标记（draft / outline 已标在正文里的 ⚠️）。"""

    def test_提取未经文献支撑(self):
        raw = "本段论述。⚠️ 未经文献支撑（锚点 Lee 2024 未在 literature/）"
        marks = citations.find_warning_marks(raw)
        self.assertEqual(len(marks), 1)
        self.assertIn("未经文献支撑", marks[0])

    def test_提取纯结构占位(self):
        marks = citations.find_warning_marks("- ⚠️ 某要点 · 纯结构占位（无文献支撑）")
        self.assertEqual(len(marks), 1)

    def test_两种标记同时出现(self):
        raw = "⚠️ 未经文献支撑\n\n⚠️ 纯结构占位"
        self.assertEqual(len(citations.find_warning_marks(raw)), 2)

    def test_无标记返回空(self):
        self.assertEqual(citations.find_warning_marks("普通正文一句。"), [])

    def test_顺序依赖_必须用原始文本(self):
        """`_strip_inline` 会剥掉 ⚠️（在 `_LAYER_MARKS` 里），剥完就找不到了。"""
        raw = "本段论述。⚠️ 未经文献支撑"
        self.assertEqual(len(citations.find_warning_marks(raw)), 1)
        self.assertEqual(
            citations.find_warning_marks(citations.strip_markdown(raw)), [])


class TestInlineCitations(unittest.TestCase):
    """行内两制式引用计数。"""

    def test_著者出版年制(self):
        got = citations.count_inline_citations("已有研究表明此点（张三, 2020）。")
        self.assertEqual(got["著者-出版年制"], 1)
        self.assertEqual(got["顺序编码制"], 0)

    def test_顺序编码制(self):
        got = citations.count_inline_citations("已有研究表明此点[3]。")
        self.assertEqual(got["顺序编码制"], 1)

    def test_顺序编码制多号(self):
        got = citations.count_inline_citations("综合来看[1,2][5-7]。")
        self.assertEqual(got["顺序编码制"], 2)

    def test_英文著者年(self):
        got = citations.count_inline_citations("This holds (Smith et al., 2019).")
        self.assertEqual(got["著者-出版年制"], 1)

    def test_全脚注制检不出_须如实声明不可用(self):
        """继承 style 已知项：全脚注制正文两制式皆为 0，产物须声明该项不可用。"""
        got = citations.count_inline_citations("此点已有研究[^1]。")
        self.assertEqual(sum(got.values()), 0)

    def test_脚注定义行不算正文(self):
        """`[^1]: 张三…` 是参考文献条目——style 算句长时是噪声，anchor 会误报零引用。"""
        clean = citations.strip_markdown("正文一句[^1]。\n\n[^1]: 张三. 某文. 2020.")
        self.assertIn("正文一句", clean)
        self.assertNotIn("张三", clean)

    def test_顺序依赖_必须先剥markdown(self):
        """`[1](url)` 这种以数字为链接文字的链接会被顺序编码制正则命中而虚高。"""
        raw = "见 [1](https://example.com) 的说明。"
        self.assertEqual(citations.count_inline_citations(raw)["顺序编码制"], 1)
        clean = citations.strip_markdown(raw)
        self.assertEqual(citations.count_inline_citations(clean)["顺序编码制"], 0)

    def test_锚点链接与行内引用互不干扰(self):
        raw = "见 [Smith 2023](literature/n.md#s) 与另一研究（李四, 2021）。"
        self.assertEqual(citations.count_anchor_links(raw), 1)
        clean = citations.strip_markdown(raw)
        self.assertEqual(citations.count_inline_citations(clean)["著者-出版年制"], 1)


class TestBlockquoteLines(unittest.TestCase):

    def test_按行计数(self):
        self.assertEqual(
            citations.count_blockquote_lines("> 引文一。\n> 引文二。\n\n正文。"), 2)

    def test_代码块内的引用符号不算(self):
        raw = "> 真引文。\n\n```\n> 这是代码里的。\n```\n"
        self.assertEqual(citations.count_blockquote_lines(raw), 1)

    def test_无引用块为零(self):
        self.assertEqual(citations.count_blockquote_lines("正文一句。"), 0)


class TestSplitParagraphs(unittest.TestCase):

    def test_空行分段(self):
        paras = citations.split_paragraphs("段一。\n\n段二。\n\n段三。")
        self.assertEqual(len(paras), 3)

    def test_连续多空行只算一个分隔(self):
        paras = citations.split_paragraphs("段一。\n\n\n\n段二。")
        self.assertEqual(len(paras), 2)

    def test_段内换行不分段(self):
        paras = citations.split_paragraphs("段一第一行。\n段一第二行。\n\n段二。")
        self.assertEqual(len(paras), 2)
        self.assertIn("第二行", paras[0])

    def test_代码块内空行不分段(self):
        raw = "段一。\n\n```python\nx = 1\n\ny = 2\n```\n\n段二。"
        self.assertEqual(len(citations.split_paragraphs(raw)), 3)

    def test_剥front_matter(self):
        raw = "---\nname: 正文\n---\n\n段一。\n\n段二。"
        paras = citations.split_paragraphs(raw)
        self.assertEqual(len(paras), 2)
        self.assertNotIn("name:", paras[0])

    def test_返回原始文本未剥markdown(self):
        """契约：返回原始文本，供调用方在其上数锚点与标记。"""
        paras = citations.split_paragraphs("见 [Smith](literature/n.md#s)。")
        self.assertIn("literature/", paras[0])

    def test_标题自成一段_由调用方过滤(self):
        """本函数只做机械空行切分，不判断「什么是正文」。"""
        paras = citations.split_paragraphs("## 第一章\n\n正文一句。")
        self.assertEqual(len(paras), 2)
        self.assertEqual(citations.strip_markdown(paras[0]), "")   # 调用方据此过滤

    def test_空输入返回空列表(self):
        self.assertEqual(citations.split_paragraphs(""), [])
        self.assertEqual(citations.split_paragraphs("\n\n\n"), [])


class TestNoSecondSourceOfTruth(unittest.TestCase):
    """防「第二份真相复活」——style 必须用共享层的同一个实现对象。"""

    def test_style用的是共享层同一实现(self):
        sys.path.insert(0, str(_REPO / "skills" / "paper-style" / "scripts"))
        import style_metrics as sm

        for name in ("strip_markdown", "split_sentences", "split_sections",
                     "effective_chars", "citation_positions"):
            with self.subTest(fn=name):
                self.assertIs(getattr(sm, name), getattr(citations, name),
                              f"{name} 在 paper-style 里被重新实现了——"
                              "两份实现必然漂移，请改回 import 共享层")


if __name__ == "__main__":
    unittest.main()
