"""共享报告渲染器单测（MD → HTML）。

导入范式同 tests/datasources（包 __init__ 注入 _shared 到 sys.path 后 import）。
验证外部可观察行为：产物自包含、色值单一来源、四层染色与色轴切换、转义、畸形输入不崩。
"""
from __future__ import annotations

import io
import pathlib
import re
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stderr

from paper_shared.report import annotate, css, markdown, render, write
from paper_shared.report.tokens import TokenError, load

# 各 skill 产物 MD 的公共骨架：h1 → 两列元表（末行标注轴）→ `##` 块 → 斜体页脚
_MD = """# 论证链检查

| 项 | 内容 |
| --- | --- |
| 日期 | 2026-07-29 |
| 研究问题（RQ） | 「算法如何影响睡眠？」 |
| 内容标注 | 👤 用户原话　·　📋 常见事实　·　🪞 系统归纳（可追溯）　·　❓ 待用户验证 |

## 用户拍板的研究问题（RQ）　👤 用户原话

「算法如何影响睡眠？」

## 四链对应图

### 链 1：RQ ↔ 方法　[对应度：7/10 · 绿]

- RQ 端　👤：关键词
- 方法端　🪞：方法章 2 条要点
  - 问卷 N=250 · 锚点 [Smith 2023](literature/笔记表.md#smith2023)
  - 无锚点
- 缺项　📋：无
- 疑问句　❓：能测量吗？

## 汇总　❓ 待用户验证

| 维度 | 评分 | 依据 |
|---|---|---|
| 新颖性 | 6/10 | 见 §2 |

---

*本检查由 AI 解析结构，不判断论证是否成立。判断由用户做出。*
"""


class TestSelfContained(unittest.TestCase):
    """产物必须是零外部依赖的单文件——这正是各 skill SKILL.md 自检命令要的。"""

    def setUp(self):
        self.h = render(_MD, skill="paper-logic")

    def test_standalone_document(self):
        self.assertTrue(self.h.startswith("<!DOCTYPE html>"))
        self.assertIn('<html lang="zh-CN">', self.h)
        self.assertTrue(self.h.rstrip().endswith("</html>"))
        self.assertIn("<style>", self.h)

    def test_no_external_reference(self):
        """对应 SKILL.md 的 `grep -iE "https?://|<script src|cdn"` 期望 0 命中。"""
        self.assertNotIn("<script", self.h)
        self.assertNotIn("cdn.", self.h.lower())
        self.assertNotIn("tailwindcss.com", self.h)
        # 正文里的锚点是相对路径，不该出现任何 http 外链（本 fixture 未放外链）
        self.assertNotIn("http://", self.h)
        self.assertNotIn("https://", self.h)

    def test_page_children_bounded(self):
        """`.page` 直接子元素应是 header/section*/footer 少数几个——若把块平铺，
        §2.7 rise 错峰动画级数会爆到几十级，末尾元素要等一秒多才淡入。"""
        inner = self.h.split("data-label", 1)[1].split(">", 1)[1].split("</article>")[0]
        depth, tops = 0, []
        for m in re.finditer(r"</?(\w+)[^>]*>", inner):
            if m.group(0).startswith("</"):
                depth -= 1
            else:
                if depth == 0:
                    tops.append(m.group(1))
                if m.group(1) not in ("br", "hr", "img", "meta"):
                    depth += 1
        self.assertLess(len(tops), 12, f".page 子元素过多：{tops}")
        self.assertEqual(tops[0], "header")
        self.assertEqual(tops[-1], "footer")


class TestDesignTokens(unittest.TestCase):
    """四层语义色是产品死线，唯一权威是 _shared/tailwind.config.js。"""

    DEADLINE_HEX = ("#2b4a6f", "#7a6230", "#4a6b5c", "#9a3b2e",
                    "#e6edf4", "#f0e9d8", "#e4ece8", "#f3e3df",
                    "#f6f2ea", "#ece5d6", "#c9bfa8", "#1f1b16")

    def test_hex_not_hardcoded_in_source(self):
        """色值不许在 Python 源码里出现第二份——config 改了产物必须跟着改。"""
        src = pathlib.Path(css.__file__).read_text(encoding="utf-8")
        for hexv in self.DEADLINE_HEX:
            self.assertNotIn(hexv, src,
                             f"{hexv} 被硬编码进 css.py——应从 tokens.load() 取")

    def test_hex_present_in_output(self):
        h = render(_MD)
        for hexv in self.DEADLINE_HEX:
            self.assertIn(hexv, h, f"产物缺四层/纸墨色 {hexv}")

    def test_missing_config_raises_not_fallback(self):
        """config 缺失时报错、不兜色值（兜一份就是第二份真相）。"""
        with self.assertRaises(TokenError):
            load(pathlib.Path("/nonexistent/tailwind.config.js"))
        with unittest.mock.patch("paper_shared.report.tokens.CONFIG",
                                 pathlib.Path("/nonexistent/tailwind.config.js")):
            with self.assertRaises(TokenError):
                render(_MD)

    def test_required_tokens_complete(self):
        t = load()
        for key in ("l1", "l1-bg", "l4", "l4-bg", "paper", "ink", "font-serif"):
            self.assertIn(key, t)


class TestAnnotation(unittest.TestCase):
    """四层符号是死线（references/四层内容标注.md），按符号染色。"""

    def test_four_layers_coloured(self):
        h = render(_MD)
        for cls in ("t1", "t2", "t3", "t4"):
            self.assertIn(f'class="tag-inline {cls}"', h)

    def test_legend_swatch_uses_real_variable(self):
        """图例色块的档名是 t1-t4，而 config 里的色变量是 l1-l4——别写成 var(--t1)。"""
        h = render(_MD)
        self.assertIn('class="sw t1"', h)
        self.assertNotIn("var(--t1)", h)
        self.assertIn(".legend .sw.t1{background:var(--l1)}", h)

    def test_legend_keeps_wording_variants(self):
        """语义名允许措辞变体（review 的 t2 是「模拟常见审稿维度」），不得抹平。"""
        md = _MD.replace("📋 常见事实", "📋 模拟常见审稿维度（非推荐）")
        self.assertIn("模拟常见审稿维度（非推荐）", render(md))

    def test_reader_axis_switch(self):
        """paper-disclose 的 👤 是「导师带教」，与四层语义不同，必须切 r1-r4。"""
        md = _MD.replace(
            "| 内容标注 | 👤 用户原话　·　📋 常见事实　·　🪞 系统归纳（可追溯）　·　❓ 待用户验证 |",
            "| 读者导引 | 👤 导师带教　·　📋 研究生院合规　·　🔎 期刊投稿　·　🛡️ AIGC 检测应对 |",
        )
        h = render(md, skill="paper-disclose")
        self.assertIn('class="tag-inline r1"', h)
        self.assertIn('class="sw r3"', h)
        self.assertNotIn('class="tag-inline t1"', h)
        # 「没有第五层」只对四层轴成立，读者轴是另一个轴
        self.assertNotIn("AI 的新判断", h)

    def test_draft_private_symbols(self):
        """paper-draft 的 ⚠️/✍️/🤖 是四层之外的补充轴，也要染色。"""
        h = render(_MD.replace("- 无锚点", "- ⚠️ 未经文献支撑 ✍️ 模仿用户风格 🤖 中性默认"))
        self.assertIn("⚠️</span>", h)
        self.assertIn("✍️</span>", h)
        self.assertIn("🤖</span>", h)

    def test_import_three_layers_ok(self):
        """paper-import 只有 📋/🪞/❓ 三枚（改用 .st 徽章族），缺 👤 不该出问题。"""
        md = _MD.replace("👤 用户原话　·　", "").replace("　👤 用户原话", "").replace("👤：", "：")
        h = render(md, skill="paper-import")
        self.assertIn('class="tag-inline t2"', h)
        self.assertNotIn('class="sw t1"', h)


class TestStructure(unittest.TestCase):
    def test_nested_list_inside_li(self):
        """子列表必须落在父 <li> 内——直接挂在 <ul> 下不合 HTML 规范。"""
        h = render(_MD)
        self.assertNotIn("</li>\n<ul>", h)
        self.assertRegex(h, r"方法章 2 条要点\s*<ul>")

    def test_table_wrapped_for_narrow_screen(self):
        h = render(_MD)
        self.assertIn('<div class="table-wrap"><table>', h)
        self.assertIn("<th>维度</th>", h)
        self.assertIn("<td>6/10</td>", h)

    def test_meta_and_legend_split(self):
        h = render(_MD)
        self.assertIn('<b class="k">日期</b>2026-07-29', h)
        self.assertIn('<section class="legend">', h)
        # 标注行不该同时留在元信息里
        self.assertNotIn('<b class="k">内容标注</b>', h)

    def test_footer_from_trailing_italic(self):
        h = render(_MD)
        self.assertIn("<footer>", h)
        self.assertIn("Human–AI Division of Labor", h)
        self.assertIn("判断由用户做出", h)

    def test_archive_label(self):
        h = render(_MD, skill="paper-logic")
        self.assertIn('data-label="paper-logic · 论证链检查"', h)
        self.assertIn("content:attr(data-label)", h)

    def test_headings_and_inline(self):
        h = render(_MD)
        self.assertIn('<h2 class="section">', h)
        self.assertIn("<h3>", h)
        self.assertIn('<a href="literature/笔记表.md#smith2023"', h)


class TestEscaping(unittest.TestCase):
    def test_html_escaped(self):
        h = render("# T\n\n| a |\n| --- |\n| x<script>alert(1)</script> |\n")
        self.assertNotIn("<script>alert", h)
        self.assertIn("&lt;script&gt;", h)

    def test_javascript_url_not_linkified(self):
        """render_html.py 只做 escape，会产出活的 javascript: 链接——本渲染器白名单。"""
        h = render("# T\n\n[点我](javascript:alert(1))\n")
        self.assertNotIn("javascript:", h)
        self.assertIn("点我", h)

    def test_attribute_quotes_escaped(self):
        h = render('# 标题"含引号\n')
        self.assertNotIn('data-label="标题"含', h)
        self.assertIn("&quot;", h)

    def test_relative_and_https_links_kept(self):
        h = render("# T\n\n[a](literature/x.md#k) [b](https://doi.org/10.1/x)\n")
        self.assertIn('href="literature/x.md#k"', h)
        self.assertIn('href="https://doi.org/10.1/x"', h)


class TestDegenerateInput(unittest.TestCase):
    """paper-daily 用 blockquote 代替元表、screen/style 暂无 MD 模板，都不能崩。"""

    def test_empty(self):
        h = render("")
        self.assertTrue(h.startswith("<!DOCTYPE html>"))

    def test_no_meta_table(self):
        md = "# 日报\n\n> RQ: 一句话\n> 时间窗: 今日\n\n## 概览\n\n- 一条\n"
        h = render(md, skill="paper-daily")
        self.assertIn("<blockquote>", h)
        self.assertIn('<h2 class="section">概览</h2>', h)
        self.assertNotIn('<section class="legend">', h)

    def test_ragged_table(self):
        h = render("# T\n\n| a | b | c |\n|---|---|---|\n| 1 |\n| 1 | 2 | 3 | 4 |\n")
        self.assertIn("<table>", h)

    def test_no_h1(self):
        h = render("## 只有二级标题\n\n正文\n")
        self.assertIn("只有二级标题", h)

    def test_ordered_and_mixed_lists(self):
        h = render("# T\n\n1. 甲\n2. 乙\n\n- 丙\n")
        self.assertIn("<ol>", h)
        self.assertIn("<ul>", h)


class TestFigureEmbed(unittest.TestCase):
    """paper-screen 的 PRISMA 流程图：SVG 内嵌则产物自包含。"""

    SVG = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'

    def test_svg_inlined(self):
        h = render("# T\n\n![PRISMA 流程图](prisma.svg)\n", svg={"prisma.svg": self.SVG})
        self.assertIn("<figure>", h)
        self.assertIn("<rect", h)
        self.assertIn("<figcaption>PRISMA 流程图</figcaption>", h)
        self.assertNotIn("<img", h)

    def test_missing_svg_degrades_to_img_not_dropped(self):
        h = render("# T\n\n![图](prisma.svg)\n")
        self.assertIn('<img src="prisma.svg"', h)


class TestWriteAndCli(unittest.TestCase):
    def test_write_creates_utf8_sibling(self):
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / "论证链检查.md"
            src.write_text(_MD, encoding="utf-8")
            dst = write(src, skill="paper-logic")
            self.assertEqual(dst.name, "论证链检查.html")
            self.assertIn("论证链检查", dst.read_text(encoding="utf-8"))

    def test_cli_end_to_end(self):
        import importlib.util
        cli_path = (pathlib.Path(__file__).resolve().parents[2] / "skills" / "_shared"
                    / "scripts" / "render_report.py")
        spec = importlib.util.spec_from_file_location("render_report_cli", cli_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / "r.md"
            src.write_text(_MD, encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                rc = mod.main(["--in", str(src), "--skill", "paper-logic"])
            self.assertEqual(rc, 0)
            self.assertTrue((pathlib.Path(d) / "r.html").is_file())

    def test_cli_missing_input_exits_2_without_artifact(self):
        import importlib.util
        cli_path = (pathlib.Path(__file__).resolve().parents[2] / "skills" / "_shared"
                    / "scripts" / "render_report.py")
        spec = importlib.util.spec_from_file_location("render_report_cli2", cli_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with redirect_stderr(io.StringIO()) as err:
            rc = mod.main(["--in", "/nonexistent/x.md"])
        self.assertEqual(rc, 2)
        self.assertIn("读不到输入文件", err.getvalue())


class TestUnits(unittest.TestCase):
    def test_axis_selection(self):
        self.assertIs(annotate.axis(["日期", "读者导引"]), annotate.READER)
        self.assertEqual(annotate.axis(["日期", "内容标注"])["👤"], "t1")

    def test_split_meta(self):
        title, meta, rest = markdown.split_meta(_MD)
        self.assertEqual(title, "论证链检查")
        self.assertEqual(meta[0], ("日期", "2026-07-29"))
        self.assertTrue(any("四链对应图" in line for line in rest))

    def test_swatches_order(self):
        row = "🪞 系统归纳　·　👤 用户原话　·　❓ 待验证　·　📋 常见事实"
        got = [c for _, _, c in annotate.swatches(row, dict(annotate.LAYER))]
        self.assertEqual(got, ["t1", "t2", "t3", "t4"], "图例应按 t1-t4 权威顺序")


if __name__ == "__main__":
    unittest.main()
