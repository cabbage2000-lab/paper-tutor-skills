"""paper-screen scripts/screen.py 确定性单测——解析 / 计数 / 守恒 / 渲染。"""
from __future__ import annotations

import pathlib
import re
import sys
import tempfile
import unittest

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "_shared"))
sys.path.insert(0, str(_REPO / "skills" / "paper-screen" / "scripts"))

import screen  # noqa: E402

LEDGER_MIN = """# 筛选台账

| 序号 | 题录锚点 | 来源库 | 去重 | 标摘筛 | 全文筛 | 排除理由码 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 12 | Crossref | 保留 | 进入全文 | 纳入 |  |  |
| 2 | 13 | 知网 | 重复（与序号 1） |  |  |  |  |
| 3 | 14 | OpenAlex | 保留 | 排除 |  |  | 主题不符 |
"""

LEDGER_OK = """
| 序号 | 题录锚点 | 来源库 | 去重 | 标摘筛 | 全文筛 | 排除理由码 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | Crossref | 保留 | 进入全文 | 纳入 |  |  |
| 2 | 2 | Crossref | 保留 | 进入全文 | 纳入 |  |  |
| 3 | 3 | 知网 | 重复（与序号 1） |  |  |  |  |
| 4 | 4 | OpenAlex | 保留 | 排除 |  |  | 主题不符 |
| 5 | 5 | OpenAlex | 保留 | 进入全文 | 排除 | E4 |  |
| 6 | 6 | 万方 | 保留 | 进入全文 | 全文不可得 |  |  |
| 7 | 7 | PubMed | 保留 | 进入全文 | 排除 | E1 |  |
"""

# 第 2 行「去重」列写成规定取值之外的「去除」——既不计入重复、也不计入保留
LEDGER_BROKEN = """
| 序号 | 题录锚点 | 来源库 | 去重 | 标摘筛 | 全文筛 | 排除理由码 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | Crossref | 保留 | 进入全文 | 纳入 |  |  |
| 2 | 2 | Crossref | 去除 |  |  |  | 取值写错 |
"""

# 三条守恒等式全部成立，但第 2 行标摘筛已「排除」却又填了全文筛「纳入」
#（那篇「纳入」被静默丢掉）、第 3 行全文排除漏填理由码——守恒校验抓不到这两类
LEDGER_CONFLICT = """
| 序号 | 题录锚点 | 来源库 | 去重 | 标摘筛 | 全文筛 | 排除理由码 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | Crossref | 保留 | 进入全文 | 纳入 |  |  |
| 2 | 2 | Crossref | 保留 | 排除 | 纳入 |  | 手滑填错 |
| 3 | 3 | Crossref | 保留 | 进入全文 | 排除 |  | 忘填理由码 |
"""

LEDGER_PENDING = """
| 序号 | 题录锚点 | 来源库 | 去重 | 标摘筛 | 全文筛 | 排除理由码 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | Crossref | 保留 | 进入全文 | 纳入 |  |  |
| 2 | 2 | Crossref | 保留 | 待定 |  |  |  |
| 3 | 3 | Crossref | 保留 | 进入全文 |  |  |  |
"""


class TestParseLedger(unittest.TestCase):
    def test_skips_header_and_separator_rows(self):
        rows = screen.parse_ledger(LEDGER_MIN)
        self.assertEqual(len(rows), 3)

    def test_fields_map_to_columns(self):
        rows = screen.parse_ledger(LEDGER_MIN)
        self.assertEqual(rows[0].seq, 1)
        self.assertEqual(rows[0].anchor, "12")
        self.assertEqual(rows[0].source_db, "Crossref")
        self.assertEqual(rows[0].dedup, "保留")
        self.assertEqual(rows[0].ta_screen, "进入全文")
        self.assertEqual(rows[0].ft_screen, "纳入")
        self.assertEqual(rows[0].exclude_code, "")

    def test_ignores_non_table_lines(self):
        rows = screen.parse_ledger("随便一段话\n\n" + LEDGER_MIN + "\n尾注文字")
        self.assertEqual(len(rows), 3)

    def test_skips_rows_with_non_numeric_seq(self):
        bad = LEDGER_MIN + "| 合计 | — | — | — | — | — | — | — |\n"
        self.assertEqual(len(screen.parse_ledger(bad)), 3)

    def test_skips_rows_with_too_few_columns(self):
        """列数不足 8 的行视作格式不完整——docstring 承诺的分支，须有覆盖。"""
        short = LEDGER_MIN + "| 4 | 15 | Crossref | 保留 |\n"
        self.assertEqual(len(screen.parse_ledger(short)), 3)


class TestCountStages(unittest.TestCase):
    def setUp(self):
        self.c = screen.count_stages(screen.parse_ledger(LEDGER_OK))

    def test_stage_counts(self):
        self.assertEqual(self.c.identified, 7)
        self.assertEqual(self.c.duplicates_removed, 1)
        self.assertEqual(self.c.after_dedup, 6)
        self.assertEqual(self.c.ta_excluded, 1)
        self.assertEqual(self.c.sought, 5)
        self.assertEqual(self.c.not_retrieved, 1)
        self.assertEqual(self.c.ft_assessed, 4)
        self.assertEqual(self.c.ft_excluded, 2)
        self.assertEqual(self.c.included, 2)

    def test_exclude_reason_distribution(self):
        self.assertEqual(self.c.exclude_reasons, {"E1": 1, "E4": 1})

    def test_conservation_empty_when_balanced(self):
        self.assertEqual(screen.check_conservation(self.c), [])


class TestConservation(unittest.TestCase):
    def test_illegal_value_breaks_conservation(self):
        c = screen.count_stages(screen.parse_ledger(LEDGER_BROKEN))
        errs = screen.check_conservation(c)
        self.assertTrue(errs, "取值落在规定取值之外却判定守恒——这正是本脚本要防的事")
        self.assertTrue(any("去重后" in e for e in errs))

    def test_error_message_includes_delta(self):
        c = screen.count_stages(screen.parse_ledger(LEDGER_BROKEN))
        self.assertTrue(any("差" in e for e in screen.check_conservation(c)))


class TestLogicalConflicts(unittest.TestCase):
    """守恒等式的盲区：取值都合法、但组合自相矛盾的行。"""

    def test_catches_conflict_conservation_misses(self):
        rows = screen.parse_ledger(LEDGER_CONFLICT)
        self.assertEqual(
            screen.check_conservation(screen.count_stages(rows)),
            [],
            "此台账三条守恒等式本就成立——正是 logical_conflicts 要补的盲区",
        )
        self.assertTrue(any("序号 2" in x for x in screen.logical_conflicts(rows)))

    def test_catches_missing_exclude_code(self):
        conflicts = screen.logical_conflicts(screen.parse_ledger(LEDGER_CONFLICT))
        self.assertTrue(any("序号 3" in x and "理由码" in x for x in conflicts))

    def test_clean_ledger_has_no_conflicts(self):
        self.assertEqual(screen.logical_conflicts(screen.parse_ledger(LEDGER_OK)), [])


class TestPending(unittest.TestCase):
    def test_pending_and_unfilled_both_count(self):
        rows = screen.parse_ledger(LEDGER_PENDING)
        self.assertEqual(screen.pending_seqs(rows), [2, 3])

    def test_no_pending_when_complete(self):
        rows = screen.parse_ledger(LEDGER_OK)
        self.assertEqual(screen.pending_seqs(rows), [])


class TestRender(unittest.TestCase):
    def setUp(self):
        self.c = screen.count_stages(screen.parse_ledger(LEDGER_OK))

    def test_mermaid_contains_real_counts(self):
        m = screen.render_mermaid(self.c)
        self.assertIn("n = 7", m)   # 识别
        self.assertIn("n = 6", m)   # 去重后
        self.assertIn("n = 2", m)   # 纳入
        self.assertIn("flowchart", m)

    def test_mermaid_lists_exclude_reasons(self):
        m = screen.render_mermaid(self.c)
        self.assertIn("E1", m)
        self.assertIn("E4", m)

    def test_svg_is_self_contained(self):
        s = screen.render_svg(self.c)
        self.assertTrue(s.startswith("<svg"))
        self.assertNotIn("<script", s)
        # xmlns="http://www.w3.org/2000/svg" 是 SVG 命名空间声明、不是外链，
        # 摘掉它再查——否则离线检查会对每一张合法 SVG 误报。
        body = s.replace('xmlns="http://www.w3.org/2000/svg"', "")
        self.assertNotIn("http://", body)
        self.assertNotIn("https://", body)

    def test_svg_contains_real_counts(self):
        s = screen.render_svg(self.c)
        for n in ("7", "6", "5", "4", "2"):
            self.assertIn(f"n = {n}", s)


class TestCLI(unittest.TestCase):
    def test_missing_ledger_returns_3_not_1(self):
        """读不到文件必须与「台账有错」(1) 区分——否则误导调用方去查数据。"""
        self.assertEqual(
            screen.main(["--ledger", "/nonexistent/dir/筛选台账.md"]), 3
        )


def _run_cli(ledger_text: str):
    """把台账写进临时目录跑 CLI，返回 (退出码, 是否产出了 svg)。

    「报错就不出图」是本命令的立身之本，必须直接断言产物有没有落地——
    只断言退出码的话，把 return 1 改成 return 0 的变异照样能过。
    """
    with tempfile.TemporaryDirectory() as d:
        dp = pathlib.Path(d)
        led = dp / "筛选台账.md"
        led.write_text(ledger_text, encoding="utf-8")
        svg = dp / "out.svg"
        code = screen.main(["--ledger", str(led), "--svg", str(svg)])
        return code, svg.exists()


class TestCLIExitCodes(unittest.TestCase):
    """四态退出码 + 「报错就不出图」的端到端断言。"""

    def test_clean_ledger_exits_0_and_writes_svg(self):
        self.assertEqual(_run_cli(LEDGER_OK), (0, True))

    def test_conservation_failure_exits_1_and_writes_nothing(self):
        self.assertEqual(_run_cli(LEDGER_BROKEN), (1, False))

    def test_logical_conflict_exits_1_and_writes_nothing(self):
        """此台账三条守恒等式全部成立——只有组合矛盾检查能拦下它。

        若把 main() 里的 logical_conflicts(rows) 拆掉，本例会变成 (0, True)。
        """
        self.assertEqual(_run_cli(LEDGER_CONFLICT), (1, False))

    def test_pending_exits_2_and_writes_nothing(self):
        self.assertEqual(_run_cli(LEDGER_PENDING), (2, False))

    def test_malformed_row_exits_1_and_writes_nothing(self):
        """列数不足的行若被静默跳过，守恒等式会在缩水后的集合上照样成立——
        脚本不报错、图照出、数字全错。这是比不平衡更隐蔽的失败。"""
        short = LEDGER_OK + "| 8 | 8 | Crossref | 保留 |\n"
        self.assertEqual(_run_cli(short), (1, False))

    def test_trailing_empty_cells_are_not_malformed(self):
        """末两列为空的紧凑写法是合法的 8 列，不得误报为格式不完整。"""
        compact = LEDGER_OK + "|8|8|Crossref|保留|进入全文|纳入|||\n"
        self.assertEqual(screen.malformed_lines(compact), [])
        self.assertEqual(len(screen.parse_ledger(compact)), 8)

    def test_列数阈值锁死在8列(self):
        """恰好 7 列也必须报——契约是「8 列」，不是「明显太短」。
        缺了这条，把阈值从 8 调成 7 的变异能存活。"""
        seven = LEDGER_OK + "| 8 | 8 | Crossref | 保留 | 进入全文 | 纳入 |  |\n"
        self.assertEqual(len(screen.malformed_lines(seven)), 1)

    def test_malformed_report_carries_line_number(self):
        short = LEDGER_OK + "| 8 | 8 | Crossref | 保留 |\n"
        bad = screen.malformed_lines(short)
        self.assertEqual(len(bad), 1)
        self.assertIsInstance(bad[0][0], int)
        self.assertIn("Crossref", bad[0][1])


def _make_ledger(ta_ex=2, not_ret=3, ft_ex=4, incl=5, dup=1) -> str:
    """按各级目标计数造台账。

    默认参数让九个级别的数字**两两不同**（15/1/14/2/12/3/9/4/5）——
    LEDGER_OK 里去重删除与标摘排除恰好都是 1，用它做按框断言时
    「两个框的数字对调」这类变异抓不到。
    """
    head = (
        "| 序号 | 题录锚点 | 来源库 | 去重 | 标摘筛 | 全文筛 | 排除理由码 | 备注 |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
    )
    rows: list = []

    def add(dedup, ta, ft, code=""):
        seq = len(rows) + 1
        rows.append(f"| {seq} | {seq} | Crossref | {dedup} | {ta} | {ft} | {code} |  |")

    for _ in range(ta_ex):
        add("保留", "排除", "")
    for _ in range(not_ret):
        add("保留", "进入全文", "全文不可得")
    for _ in range(ft_ex):
        add("保留", "进入全文", "排除", "E4")
    for _ in range(incl):
        add("保留", "进入全文", "纳入")
    for _ in range(dup):
        add("重复（与序号 1）", "", "")
    return head + "\n".join(rows) + "\n"


LEDGER_DISTINCT = _make_ledger()


def _mermaid_nodes(m: str) -> dict:
    """从 mermaid 文本抽出 {框标签: 计数}。"""
    return {lbl: int(n) for lbl, n in re.findall(r'\["([^"<]+)<br/>n = (\d+)', m)}


def _svg_boxes(s: str) -> dict:
    """从 SVG 抽出 {框标签: 计数}——_box() 产出的标签与数字是相邻两个 text。"""
    return {
        lbl: int(n)
        for lbl, n in re.findall(r">([^<>]+)</text><text[^>]*>n = (\d+)</text>", s)
    }


class TestRenderBoxMapping(unittest.TestCase):
    """按框校验每个数字——只断言「数字出现在字符串里」的话，
    把两个框的数字对调这种变异抓不到。"""

    # 九个数字两两不同（见 _make_ledger 的 docstring）——用 LEDGER_OK 的话
    # 去重删除与标摘排除都是 1，对调后测试照样通过。
    EXPECTED = {
        "识别：记录总数": 15,
        "去重删除": 1,
        "标题摘要筛选": 14,
        "标题摘要阶段排除": 2,
        "寻求全文": 12,
        "全文不可得": 3,
        "全文评估合格性": 9,
        "全文阶段排除": 4,
        "纳入综述": 5,
    }

    def setUp(self):
        self.c = screen.count_stages(screen.parse_ledger(LEDGER_DISTINCT))

    def test_fixture各级计数两两不同(self):
        """这个 fixture 的价值全在「九个数字互不相同」——一旦被改回有重复值，
        按框断言就会退化成抓不到对调的空转测试。"""
        vals = list(self.EXPECTED.values())
        self.assertEqual(len(vals), len(set(vals)))
        self.assertEqual(screen.check_conservation(self.c), [])

    def test_mermaid_每个数字进对框(self):
        self.assertEqual(_mermaid_nodes(screen.render_mermaid(self.c)), self.EXPECTED)

    def test_svg_每个数字进对框(self):
        self.assertEqual(_svg_boxes(screen.render_svg(self.c)), self.EXPECTED)

    def test_识别框不写死数据库检索(self):
        """台账的来源库列支持手工补充的其他来源；写死「数据库检索」会让含
        其他来源的台账产出与事实不符的图，而 PRISMA 第 16 项要报的正是它。"""
        for r in (screen.render_mermaid(self.c), screen.render_svg(self.c)):
            self.assertNotIn("数据库检索", r)


class TestConservationEachEquation(unittest.TestCase):
    """三条守恒等式各自都要有用例——只测第 1 条的话，删掉第 2/3 条的变异能存活。"""

    def _counts(self, rows_md: str):
        return screen.count_stages(screen.parse_ledger(rows_md))

    def test_第2条等式_去重后不等于标摘排除加进入全文(self):
        c = self._counts(LEDGER_OK)
        c.ta_excluded += 1  # 人为破坏第 2 条，不动第 1、3 条
        errs = screen.check_conservation(c)
        self.assertTrue(any("去重后" in e and "标摘排除" in e for e in errs))

    def test_第3条等式_进入全文不等于三项之和(self):
        c = self._counts(LEDGER_OK)
        c.included += 1  # 人为破坏第 3 条
        errs = screen.check_conservation(c)
        self.assertTrue(any("进入全文" in e and "纳入" in e for e in errs))


class TestPendingBlankCell(unittest.TestCase):
    def test_留空与待定同义(self):
        """references 明写「留空与待定同义」——两者都算筛选未完成。"""
        blank = """
| 序号 | 题录锚点 | 来源库 | 去重 | 标摘筛 | 全文筛 | 排除理由码 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | Crossref | 保留 |  |  |  |  |
"""
        self.assertEqual(screen.pending_seqs(screen.parse_ledger(blank)), [1])
