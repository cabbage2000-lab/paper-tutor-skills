"""paper-verify scripts/report_html.py 渲染单测——结构、转义、降级明标、零外部依赖。

HTML 是给人读的主产物，这里守的是「读者能看到的东西不出错」：
六态如实呈现、用户输入被转义（报告会被转发给导师/同行）、降级横幅不许缺、
不许偷偷引入 CDN（产物脱离 skill 包后必须离线可读）。
"""
from __future__ import annotations

import pathlib
import re
import sys
import tempfile
import unittest

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "_shared"))
sys.path.insert(0, str(_REPO / "skills" / "paper-verify" / "scripts"))

import report  # noqa: E402
import report_html  # noqa: E402


def _payload(**over):
    p = {
        "run_id": "verify-20260728-1400",
        "created_at": "2026-07-28T14:00:00Z",
        "input_fingerprint": "sha256:abc",
        "network_status": "ok",
        "stats": {"total": 4,
                  "by_status": {"VERIFIED": 1, "RETRACTED": 1, "NOT_FOUND": 1,
                                "PENDING_MANUAL": 1},
                  "elapsed_s": 5.0, "sources_queried": ["crossref", "openalex"]},
        "sources_checked": [
            {"source": "crossref", "name_zh": "Crossref", "role": "core", "coverage": "自动核验"},
            {"source": "cnki", "name_zh": "中国知网", "role": "guided", "coverage": "待人工核对"},
        ],
        "items": [
            {"ref_id": "r1", "raw_text": "[1] Smith. Title[J]. J, 2020.", "status": "VERIFIED",
             "parsed": {"doi": "10.1234/ok", "title": "Title", "year": 2020,
                        "authors": ["Smith J"], "parse_status": "ok"},
             "field_notes": [], "evidence_summary": "已在 crossref 找到且元数据一致",
             "exit_guidance": None,
             "evidence": {"doi_ra": "Crossref",
                          "queries": [{"source": "crossref", "outcome": "hit",
                                       "query_kind": "doi"}],
                          "hits": [{"source": "crossref", "fetched_at": "2026-07-28T13:59:00Z",
                                    "metadata": {"title": "Title", "year": 2020,
                                                 "doi": "10.1234/ok", "authors": ["Smith J"]}}]},
             "format_issues": [], "manual_result": None},
            {"ref_id": "r2", "raw_text": "[2] Retracted paper", "status": "RETRACTED",
             "parsed": {"doi": "10.1016/x", "parse_status": "ok"},
             "field_notes": [], "evidence_summary": "该引用已被标记撤稿（数据源 crossref）",
             "exit_guidance": "投稿前必处理：替换该引用或在文中说明撤稿情况",
             "evidence": {"doi_ra": "Crossref", "queries": [], "hits": []},
             "format_issues": [], "manual_result": None},
            {"ref_id": "r3", "raw_text": "[3] Fake. DOI: 10.9999/x", "status": "NOT_FOUND",
             "parsed": {"doi": "10.9999/x", "parse_status": "ok"},
             "field_notes": [{"field": "year", "ref_value": 2001, "source_value": 2017,
                              "severity": "mismatch", "detail": "年份差 16"}],
             "evidence_summary": "DOI 前缀未注册——疑似不存在的引用",
             "exit_guidance": "复核：doi.org 手查",
             "evidence": {"doi_ra": "not_registered", "queries": [], "hits": []},
             "format_issues": [{"problem": "缺文献类型标识", "clause": "GB/T 7714-2015 §8.1",
                                "suggestion": "补 [J]"}],
             "manual_result": None},
            {"ref_id": "r4", "raw_text": "[4] 王明. 中文研究[J]. 电化教育研究, 2022.",
             "status": "PENDING_MANUAL",
             "parsed": {"title": "中文研究", "authors": ["王明"], "year": 2022,
                        "parse_status": "ok"},
             "field_notes": [], "evidence_summary": "开放 API 未命中，待人工核对",
             "exit_guidance": "人工核对包：知网/万方检索方案",
             "evidence": {"doi_ra": "ISTIC", "queries": [], "hits": []},
             "format_issues": [], "manual_result": None},
        ],
    }
    p.update(over)
    return p


class TestSkeleton(unittest.TestCase):
    def setUp(self):
        self.h = report_html.build_html(_payload())

    def test_is_standalone_document(self):
        self.assertTrue(self.h.startswith("<!DOCTYPE html>"))
        self.assertIn('<html lang="zh-CN">', self.h)
        self.assertIn("</html>", self.h)

    def test_引入tailwind_cdn与typography插件(self):
        """与 13 个提示词型模板 skill 同一技术栈（报告组件库 §0.2 的引入方式）。"""
        self.assertIn('<script src="https://cdn.tailwindcss.com?plugins=typography">', self.h)

    def test_样式块必须是tailwindcss类型(self):
        """普通 <style> 不会被 Tailwind 编译——@apply / theme() 会原样留在 CSS 里失效。"""
        self.assertIn('<style type="text/tailwindcss">', self.h)

    def test_config原样内联而非相对路径引用(self):
        """产物落在 .paper/review/ 后 ../../_shared/tailwind.config.js 指不到 skill 包，
        必须内联；且内联的是 _shared 那份文件本身，不在 HTML 侧复制一份。"""
        # 不许出现真实生效的本地 config 引用（config 注释里那行示例已被转义成
        # `<\/script>`，不会匹配；有人改回 src 引用则会被抓到）
        self.assertNotIn('tailwind.config.js"></script>', self.h,
                         "config 走内联——产物脱离 skill 包后本地相对路径必然断链")
        self.assertLess(self.h.index(report_html.TAILWIND_CDN),
                        self.h.index("tailwind.config = {"),
                        "config 必须在 CDN 之后（组件库 §0.2 的引入顺序）")
        cfg = report_html.TAILWIND_CONFIG.read_text(encoding="utf-8")
        self.assertIn(cfg.replace("</", r"<\/"), self.h, "内联的应是 _shared 那份文件原文")

    def test_内联config已转义闭合标签(self):
        """config 注释里有 `</script>` 示例——不转义会提前闭合标签、让 config 静默失效
        （四层色 class 全部回落默认主题，但页面照样渲染出来，极难自查）。"""
        head = self.h.split("<body>")[0]
        scripts = re.findall(r"<script>(.*?)</script>", head, re.S)
        self.assertEqual(len(scripts), 1, "head 里应恰好一段内联 config script")
        self.assertIn(r"<\/script>", scripts[0])       # 已转义
        self.assertNotIn("</script>", scripts[0])      # 未转义的不许出现

    def test_四层色值不在CSS侧复制一份(self):
        """色值唯一来源是 _shared/tailwind.config.js（产品死线），CSS 只用 theme() 取。

        判据落在 _CSS 常量上——HTML 里出现这些 hex 是正常的（内联 config 本身就是
        色值的定义处）。红黄绿三档是「对应度」视觉编码、非语义色，按组件库 §1.4
        允许就地内联，故不在此列。
        """
        for hexv in ("#2b4a6f", "#7a6230", "#4a6b5c", "#9a3b2e",
                     "#e6edf4", "#f0e9d8", "#e4ece8", "#f3e3df",
                     "#f6f2ea", "#1f1b16", "#c9bfa8"):
            self.assertNotIn(hexv, report_html._CSS,
                             f"四层/纸墨色 {hexv} 被硬编码进 CSS——应走 theme() 取自 config")
        self.assertIn("theme('colors.l4.DEFAULT')", self.h)
        self.assertIn("theme('fontFamily.serif')", self.h)

    def test_config缺失时留可诊断注释而不兜第二份色值(self):
        import unittest.mock
        with unittest.mock.patch.object(report_html, "TAILWIND_CONFIG",
                                        pathlib.Path("/nonexistent/tailwind.config.js")):
            h = report_html.build_html(_payload())
        self.assertIn("未找到 _shared/tailwind.config.js", h)
        self.assertNotIn("#9a3b2e", h)      # 不在此处兜色值（那就是第二份真相）

    def test_六态标签与顺序取自report模块(self):
        """标签不在 HTML 侧重复定义：改 report.STATUS_LABEL 应同时改到两版报告。"""
        for status, (emoji, label) in report.STATUS_LABEL.items():
            self.assertIn(label, self.h, f"缺六态中文标签：{label}")
            self.assertIn(emoji, self.h, f"缺六态符号：{emoji}")

    def test_人机分工页脚与非动机指控声明(self):
        self.assertIn("人机分工", self.h)
        self.assertIn("非动机指控", self.h)
        self.assertIn("不指控动机", self.h)

    def test_不出现动机指控词(self):
        """红线 1：措辞用「疑似不存在」，禁「编造 / 虚假 / 伪造」等动机词。

        例外：明确否定这些词的句子（「不是编造指控」「勿据此判定编造」）——
        检查「指控性用法」而非字面出现。
        """
        for bad in ("你编造", "系已编造", "虚假引用", "伪造引用"):
            self.assertNotIn(bad, self.h)


class TestReadingAids(unittest.TestCase):
    """阅读体验组件：裁决横幅 / 筛选轨 / 优先关注锚点 / 状态说明。"""

    def setUp(self):
        self.h = report_html.build_html(_payload())

    def test_裁决横幅先说有几条要动手(self):
        self.assertIn("本次核验裁决", self.h)
        # fixture 的 priority 态：RETRACTED + NOT_FOUND（PENDING_MANUAL 不属优先处理）
        self.assertIn("2 条需优先处理", self.h)
        self.assertIn("已撤稿 1 条", self.h)
        self.assertIn("不是编造指控", self.h)

    def test_全部已核实时裁决横幅转为无需优先处理(self):
        p = _payload(stats={"total": 1, "by_status": {"VERIFIED": 1}})
        p["items"] = [it for it in p["items"] if it["status"] == "VERIFIED"]
        h = report_html.build_html(p)
        self.assertIn("无需优先处理的条目", h)
        self.assertNotIn("二、需优先关注", h)     # 节标题；字样也出现在 CSS/JS 注释里

    def test_筛选轨每个出现的态一个复选框(self):
        boxes = re.findall(r'<input type="checkbox" value="(\w+)"', self.h)
        self.assertEqual(set(boxes),
                         {"VERIFIED", "RETRACTED", "NOT_FOUND", "PENDING_MANUAL"})
        self.assertNotIn('value="UNVERIFIED"', self.h)   # 未出现的态不摆空控件

    def test_优先关注条目锚点直达详情卡片(self):
        self.assertIn('href="#ref-r2"', self.h)
        self.assertIn('id="ref-r2"', self.h)
        self.assertIn('href="#ref-r3"', self.h)

    def test_逐条卡片带data_status供筛选(self):
        self.assertIn('data-status="RETRACTED"', self.h)
        self.assertIn('data-status="PENDING_MANUAL"', self.h)

    def test_每态附一句意味着什么(self):
        self.assertIn("这一态意味着什么", self.h)
        self.assertIn("英文库查不到不等于不存在", self.h)

    def test_doi渲染为可点链接(self):
        self.assertIn('href="https://doi.org/10.1234/ok"', self.h)

    def test_字段对照表逐字段摆引用值与源值(self):
        self.assertIn("引用里写的", self.h)
        self.assertIn("数据源里的", self.h)
        self.assertIn("年份差 16", self.h)

    def test_待人工核对条目带核对包与可点检索入口(self):
        self.assertIn("人工核对包", self.h)
        self.assertIn("kns.cnki.net", self.h)
        self.assertIn("wanfangdata.com.cn", self.h)
        self.assertIn("manual_result", self.h)
        self.assertIn('data-copy="中文研究 王明 2022"', self.h)   # 检索词可一键复制

    def test_格式提示带条款与规范化示例(self):
        self.assertIn("GB/T 7714-2015 §8.1", self.h)
        self.assertIn("补 [J]", self.h)

    def test_证据链折叠且标命中未命中未查成(self):
        self.assertIn("<details>", self.h)
        self.assertIn("证据链（命中 1 · 未命中 0 · 未查成 0）", self.h)
        self.assertIn("DOI 注册机构路由：Crossref", self.h)

    def test_打印规则去筛选轨并展开证据链(self):
        self.assertIn("@media print", self.h)
        self.assertIn("details > summary ~ *{display:block!important}", self.h)

    def test_动画尊重reduced_motion(self):
        self.assertIn("prefers-reduced-motion:no-preference", self.h)


class TestDegradeBanner(unittest.TestCase):
    """降级明标（代码层红线：绝不静默用模型记忆顶替）。"""

    def test_offline横幅声明核验不可用(self):
        h = report_html.build_html(_payload(network_status="offline"))
        self.assertIn("network_status=offline", h)
        self.assertIn("核验不可用", h)
        self.assertIn("paper-doctor", h)

    def test_degraded横幅区分没查成与查了没有(self):
        h = report_html.build_html(_payload(network_status="degraded"))
        self.assertIn("部分降级", h)
        self.assertIn("「没查成」而非「查了没有」", h)

    def test_ok时不摆降级横幅(self):
        self.assertNotIn("降级声明", report_html.build_html(_payload()))

    def test_html与markdown用同一份降级文案(self):
        """两版报告对同一次降级必须说同一句话——文案只在 report.py 定义一份。"""
        for status in ("offline", "degraded"):
            title, detail = report.NETWORK_BANNER[status]
            md = report.build_markdown(_payload(network_status=status))
            html = report_html.build_html(_payload(network_status=status))
            for text in (title, detail):
                self.assertIn(text, md)
                self.assertIn(text, html)


class TestEscaping(unittest.TestCase):
    """引用原文来自用户粘贴，报告会被转发——注入必须被转义，不能破坏文档结构。"""

    def test_用户输入里的标签被转义(self):
        p = _payload()
        p["items"][0]["raw_text"] = '<script>alert(1)</script> & "quoted" <b>x</b>'
        h = report_html.build_html(p)
        self.assertNotIn("<script>alert(1)</script>", h)
        self.assertIn("&lt;script&gt;", h)
        self.assertIn("&amp;", h)

    def test_恶意doi不逃出属性(self):
        p = _payload()
        p["items"][0]["parsed"]["doi"] = '10.1/x" onmouseover="evil()'
        h = report_html.build_html(p)
        self.assertNotIn('onmouseover="evil()"', h)

    def test_检索词里的引号不破坏data属性(self):
        p = _payload()
        p["items"][3]["parsed"]["title"] = 'A "quoted" 标题'
        h = report_html.build_html(p)
        self.assertNotIn('data-copy="A "quoted"', h)
        self.assertIn("&quot;quoted&quot;", h)


class TestWriteHtml(unittest.TestCase):
    def test_落盘可读且是utf8(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "v.html"
            report_html.write_html(_payload(), path)
            text = path.read_text(encoding="utf-8")
            self.assertIn("引用存在性核验报告", text)
            self.assertIn("已撤稿", text)

    def test_cli_从json渲染html(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / "verify-x.json"
            src.write_text(json.dumps(_payload(), ensure_ascii=False), encoding="utf-8")
            import io
            from contextlib import redirect_stderr
            with redirect_stderr(io.StringIO()):
                rc = report_html.main(["--in", str(src)])
            self.assertEqual(rc, 0)
            self.assertTrue((pathlib.Path(d) / "verify-x.html").exists())


class TestEmptyAndMinimal(unittest.TestCase):
    def test_空报告不炸(self):
        h = report_html.build_html({"run_id": "v", "created_at": "", "network_status": "ok",
                                    "stats": {"total": 0, "by_status": {}},
                                    "sources_checked": [], "items": []})
        self.assertIn("</html>", h)
        self.assertIn("无需优先处理的条目", h)

    def test_缺字段的条目不炸(self):
        h = report_html.build_html({
            "stats": {"total": 1, "by_status": {"UNVERIFIED": 1}},
            "items": [{"ref_id": "r1", "status": "UNVERIFIED"}],
        })
        self.assertIn("无法核实", h)
        self.assertIn('id="ref-r1"', h)


if __name__ == "__main__":
    unittest.main()
