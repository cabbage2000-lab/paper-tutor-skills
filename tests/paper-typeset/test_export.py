"""paper-typeset scripts/export.py 与 _shared toolchain 的确定性单测。

**全程 mock `subprocess`，不真跑 pandoc / xelatex**（spec §9 已定）：本机未装这
两个二进制，而单测必须秒级跑完、不依赖外部环境。真实端到端转换未覆盖，已如实
登记为已知观察项。
"""
from __future__ import annotations

import json
import pathlib
import shlex
import sys
import tempfile
import types
import unittest
from unittest import mock

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "_shared"))
sys.path.insert(0, str(_REPO / "skills" / "paper-typeset" / "scripts"))

import export  # noqa: E402
from paper_shared import toolchain  # noqa: E402

SRC_MD = """---
title: 测试稿
---

# 第一章 引言

近年来该领域快速发展。已有研究指出这一趋势（Smith, 2023）。

<!-- 这条注释里的汉字不会进 tex，校验前须剥离 -->

本文尝试回答该问题。
"""


def fake_probe(pandoc: bool = True, xelatex: bool = True,
               fonts: bool = True) -> dict:
    return {
        "pandoc": {"name": "pandoc", "available": pandoc,
                   "version": "pandoc 3.1.11" if pandoc else None,
                   "path": "/opt/bin/pandoc" if pandoc else None,
                   "fix": None if pandoc else "未检测到 pandoc；安装：brew install pandoc"},
        "xelatex": {"name": "xelatex", "available": xelatex,
                    "version": "XeTeX 3.14" if xelatex else None,
                    "path": "/opt/bin/xelatex" if xelatex else None,
                    "fix": None if xelatex else "未检测到 xelatex；安装：mactex"},
        "cjk_fonts": {"available": fonts,
                      "fonts": ["Songti SC", "PingFang SC"] if fonts else [],
                      "source": "test", "fix": None if fonts else "装 Noto CJK"},
    }


def _runner(returncode: int = 0, tex_body: str | None = None):
    """造一个 subprocess.run 替身：顺便把 -o 指定的产物写出来（mock 不会真产文件）。"""
    def _run(cmd, **kwargs):
        if returncode == 0:
            out = pathlib.Path(cmd[cmd.index("-o") + 1])
            if out.suffix == ".tex":
                out.write_text(tex_body if tex_body is not None else
                               _tex_from(SRC_MD), encoding="utf-8")
            else:
                out.write_bytes(b"PK\x03\x04binary-ish")
        return types.SimpleNamespace(returncode=returncode, stdout="",
                                     stderr="! LaTeX Error: something\n")
    return _run


def _tex_from(md: str) -> str:
    """造一份「汉字序列与源一致」的假 tex：LaTeX 命令是 ASCII，不影响汉字序列。"""
    body = export.cjk_sequence(export.strip_html_comments(md))
    return "\\documentclass{article}\n\\begin{document}\n" + body + "\n\\end{document}\n"


# ── 共享探测层 ─────────────────────────────────────────────────────────────
class TestToolchain(unittest.TestCase):
    def test_不存在的二进制返回不可用且带安装指引(self):
        r = toolchain.probe_binary("definitely-not-a-real-binary-xyz")
        self.assertFalse(r["available"])
        self.assertIsNone(r["path"])
        self.assertIn("未检测到", r["fix"])

    def test_存在的二进制返回可用且有版本(self):
        r = toolchain.probe_binary(pathlib.Path(sys.executable).name)
        self.assertTrue(r["available"])
        self.assertTrue(r["version"])
        self.assertIsNone(r["fix"])

    def test_字体探测返回族名而非文件名(self):
        r = toolchain.probe_cjk_fonts()
        if not r["available"]:
            self.skipTest("本机无中文字体")
        for f in r["fonts"]:
            self.assertFalse(f.endswith((".ttc", ".ttf", ".otf")), f)
            # 以点开头的是系统内部字体，XeLaTeX 拿不到，必须已被过滤
            self.assertFalse(f.startswith("."), f)

    def test_字体排序把宋体系排在黑体系之前(self):
        ranked = toolchain._rank_families(["Heiti TC", "PingFang SC", "Songti SC"])
        self.assertEqual(ranked[0], "Songti SC")
        self.assertLess(ranked.index("PingFang SC"), ranked.index("Heiti TC"))

    def test_未知字体保持原相对顺序并排在后面(self):
        ranked = toolchain._rank_families(["某未知字体甲", "Songti SC", "某未知字体乙"])
        self.assertEqual(ranked[0], "Songti SC")
        self.assertLess(ranked.index("某未知字体甲"), ranked.index("某未知字体乙"))


# ── CSL 解析 ───────────────────────────────────────────────────────────────
class TestResolveCsl(unittest.TestCase):
    def test_两个简写都命中真实存在的内置文件(self):
        for alias in ("numeric", "author-date"):
            p = export.resolve_csl(alias)
            self.assertTrue(p.is_file(), alias)
            text = p.read_text(encoding="utf-8")
            self.assertIn("GB/T 7714-2015", text)
            self.assertIn("by-sa/3.0", text)

    def test_路径不存在时抛错而不静默跳过(self):
        with self.assertRaises(FileNotFoundError):
            export.resolve_csl("/nonexistent/never.csl")

    def test_未指定返回None(self):
        self.assertIsNone(export.resolve_csl(None))


# ── 命令组装 ───────────────────────────────────────────────────────────────
class TestBuildCmd(unittest.TestCase):
    def setUp(self):
        self.src = pathlib.Path("manuscript/正文.md")
        self.out = pathlib.Path("submission/正文.docx")

    def test_docx_基本命令(self):
        cmd = export.build_cmd(self.src, self.out, "docx")
        self.assertEqual(cmd[0], "pandoc")
        self.assertIn("-o", cmd)
        self.assertNotIn("--standalone", cmd)

    def test_tex_必须带standalone(self):
        cmd = export.build_cmd(self.src, pathlib.Path("o.tex"), "tex")
        self.assertIn("--standalone", cmd)

    def test_pdf_必须带xelatex引擎(self):
        cmd = export.build_cmd(self.src, pathlib.Path("o.pdf"), "pdf")
        self.assertIn("--pdf-engine=xelatex", cmd)

    def test_给bib才启用citeproc(self):
        with_bib = export.build_cmd(self.src, self.out, "docx",
                                    bib=pathlib.Path("refs.bib"))
        self.assertIn("--citeproc", with_bib)
        self.assertIn("--bibliography=refs.bib", with_bib)
        without = export.build_cmd(self.src, self.out, "docx")
        self.assertNotIn("--citeproc", without)

    def test_csl只在有bib时附加(self):
        csl = pathlib.Path("gb.csl")
        cmd = export.build_cmd(self.src, self.out, "docx", csl=csl,
                               bib=pathlib.Path("refs.bib"))
        self.assertIn("--csl=gb.csl", cmd)

    def test_中文字体只对tex与pdf生效(self):
        tex = export.build_cmd(self.src, pathlib.Path("o.tex"), "tex",
                               cjk_font="Songti SC")
        self.assertIn("CJKmainfont=Songti SC", tex)
        docx = export.build_cmd(self.src, self.out, "docx", cjk_font="Songti SC")
        self.assertNotIn("CJKmainfont=Songti SC", docx)

    def test_V与其值是两个argv元素(self):
        """合并成一个元素会让 subprocess 与「手工可执行命令」双双失效。"""
        cmd = export.build_cmd(self.src, pathlib.Path("o.pdf"), "pdf",
                               cjk_font="Songti SC")
        i = cmd.index("-V")
        self.assertEqual(cmd[i + 1], "CJKmainfont=Songti SC")

    def test_打印出的命令是可直接执行的shell语法(self):
        """--dry-run 打印的命令是三条不变②对用户的承诺，必须真能跑。"""
        cmd = export.build_cmd(self.src, pathlib.Path("o.pdf"), "pdf",
                               cjk_font="Songti SC")
        printed = shlex.join(cmd)
        # 复制回 shell 解析一遍，应还原成与原 argv 完全一致的列表
        self.assertEqual(shlex.split(printed), cmd)


# ── 正文一致性校验 ─────────────────────────────────────────────────────────
class TestVerify(unittest.TestCase):
    def test_cjk序列只取汉字且保序(self):
        self.assertEqual(export.cjk_sequence("a甲b乙, 丙!"), "甲乙丙")

    def test_剥离html注释(self):
        self.assertEqual(
            export.strip_html_comments("正文<!-- 注释汉字 -->继续"), "正文继续")

    def test_一致时exact通过(self):
        r = export.verify_tex(SRC_MD, _tex_from(SRC_MD), has_bib=False)
        self.assertTrue(r["ok"])
        self.assertEqual(r["mode"], "exact")

    def test_不一致时失败并给出首个差异位置(self):
        bad = _tex_from(SRC_MD).replace("近年来", "近年間")
        r = export.verify_tex(SRC_MD, bad, has_bib=False)
        self.assertFalse(r["ok"])
        self.assertIn("第", r["detail"])

    def test_有bib时产物多出汉字仍算通过(self):
        more = _tex_from(SRC_MD).replace("\\end{document}", "参考文献条目汉字\n\\end{document}")
        r = export.verify_tex(SRC_MD, more, has_bib=True)
        self.assertTrue(r["ok"])
        self.assertEqual(r["mode"], "substring")

    def test_有bib但正文缺字仍算失败(self):
        broken = _tex_from(SRC_MD).replace("近年来该领域", "")
        r = export.verify_tex(SRC_MD, broken, has_bib=True)
        self.assertFalse(r["ok"])

    def test_源无汉字时跳过比对(self):
        r = export.verify_tex("Pure English text.", "\\documentclass{article}",
                              has_bib=False)
        self.assertTrue(r["ok"])
        self.assertEqual(r["mode"], "skipped")


# ── 转换与退出码 ───────────────────────────────────────────────────────────
class TestRunExport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.src = self.root / "正文.md"
        self.src.write_text(SRC_MD, encoding="utf-8")
        self.outdir = self.root / "submission"
        self.outdir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_缺pandoc时全部降级且退出码2(self):
        rep = export.run_export(self.src, self.outdir, ["docx"],
                                probe=fake_probe(pandoc=False))
        self.assertEqual(rep["items"][0]["status"], "skipped")
        self.assertIn("pandoc", rep["items"][0]["missing"])
        self.assertTrue(rep["items"][0]["fix"])
        self.assertEqual(export.decide_exit(rep), export.EXIT_DEGRADED)

    def test_缺xelatex时docx成功pdf降级且分项列出(self):
        with mock.patch.object(export.subprocess, "run", _runner(0)):
            rep = export.run_export(self.src, self.outdir, ["docx", "pdf"],
                                    probe=fake_probe(xelatex=False))
        by_fmt = {i["format"]: i for i in rep["items"]}
        self.assertEqual(by_fmt["docx"]["status"], "ok")
        self.assertEqual(by_fmt["pdf"]["status"], "skipped")
        self.assertIn("xelatex", by_fmt["pdf"]["missing"])
        self.assertEqual(export.decide_exit(rep), export.EXIT_DEGRADED)

    def test_中文稿无中文字体时pdf不产出(self):
        """宁可不产，也不交付一份整篇方框的 PDF——那就是「假装成功」。"""
        with mock.patch.object(export.subprocess, "run", _runner(0)):
            rep = export.run_export(self.src, self.outdir, ["pdf"],
                                    probe=fake_probe(fonts=False))
        self.assertEqual(rep["items"][0]["status"], "skipped")
        self.assertIn("中文字体", rep["items"][0]["missing"])

    def test_pandoc返回非零时退出码1且转述stderr(self):
        with mock.patch.object(export.subprocess, "run", _runner(1)):
            rep = export.run_export(self.src, self.outdir, ["docx"],
                                    probe=fake_probe())
        self.assertEqual(rep["items"][0]["status"], "failed")
        self.assertIn("LaTeX Error", rep["items"][0]["stderr"])
        self.assertEqual(export.decide_exit(rep), export.EXIT_RUN_FAILED)

    def test_全部成功时退出码0(self):
        with mock.patch.object(export.subprocess, "run", _runner(0)):
            rep = export.run_export(self.src, self.outdir, ["docx", "tex"],
                                    probe=fake_probe())
        self.assertEqual({i["status"] for i in rep["items"]}, {"ok"})
        self.assertEqual(export.decide_exit(rep), export.EXIT_OK)

    def test_tex校验失败时退出码4(self):
        bad = "\\documentclass{article}\n被换掉的正文\n"
        with mock.patch.object(export.subprocess, "run", _runner(0, tex_body=bad)):
            rep = export.run_export(self.src, self.outdir, ["tex"],
                                    probe=fake_probe())
        self.assertEqual(rep["items"][0]["status"], "verify_failed")
        self.assertEqual(export.decide_exit(rep), export.EXIT_VERIFY_FAILED)

    def test_二进制产物如实声明无法字符级校验(self):
        with mock.patch.object(export.subprocess, "run", _runner(0)):
            rep = export.run_export(self.src, self.outdir, ["docx"],
                                    probe=fake_probe())
        v = rep["items"][0]["verify"]
        self.assertIsNone(v["ok"])
        self.assertEqual(v["mode"], "unavailable")
        self.assertIn("无法做字符级比对", v["detail"])

    def test_源文件md5转换前后未变(self):
        with mock.patch.object(export.subprocess, "run", _runner(0)):
            rep = export.run_export(self.src, self.outdir, ["docx"],
                                    probe=fake_probe())
        self.assertTrue(rep["source_md5"]["unchanged"])

    def test_pandoc返回0但没产文件算失败(self):
        def _liar(cmd, **kw):
            return types.SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(export.subprocess, "run", _liar):
            rep = export.run_export(self.src, self.outdir, ["docx"],
                                    probe=fake_probe())
        self.assertEqual(rep["items"][0]["status"], "failed")
        self.assertIn("未产出非空文件", rep["items"][0]["stderr"])

    def test_自动选用首个探测到的中文字体(self):
        with mock.patch.object(export.subprocess, "run", _runner(0)):
            rep = export.run_export(self.src, self.outdir, ["tex"],
                                    probe=fake_probe())
        self.assertEqual(rep["cjk_font_used"], "Songti SC")

    def test_dry_run不执行也不因缺环境降级(self):
        rep = export.run_export(self.src, self.outdir, ["pdf"], dry_run=True,
                                probe=fake_probe(pandoc=False, xelatex=False))
        self.assertEqual(rep["items"][0]["status"], "dry_run")
        self.assertIn("pandoc", rep["items"][0]["command"])

    def test_降级报告含四件套(self):
        rep = export.run_export(self.src, self.outdir, ["docx"],
                                probe=fake_probe(pandoc=False))
        text = export.render_report(rep)
        self.assertIn("未生成", text)
        self.assertIn("原因", text)
        self.assertIn("安装指引", text)
        self.assertIn("可手工执行", text)


# ── CLI ────────────────────────────────────────────────────────────────────
class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.src = self.root / "正文.md"
        self.src.write_text(SRC_MD, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_输入不存在返回3(self):
        self.assertEqual(export.main(["--input", "/nope/never.md"]),
                         export.EXIT_INPUT)

    def test_未指定输入返回3(self):
        self.assertEqual(export.main([]), export.EXIT_INPUT)

    def test_不支持的格式返回3(self):
        self.assertEqual(
            export.main(["--input", str(self.src), "--to", "epub"]),
            export.EXIT_INPUT)

    def test_csl路径错返回3(self):
        self.assertEqual(
            export.main(["--input", str(self.src), "--csl", "/nope.csl"]),
            export.EXIT_INPUT)

    def test_bib路径错返回3(self):
        self.assertEqual(
            export.main(["--input", str(self.src), "--bib", "/nope.bib"]),
            export.EXIT_INPUT)

    def test_probe只探测返回0(self):
        self.assertEqual(export.main(["--probe"]), export.EXIT_OK)

    def test_dry_run返回0并打印命令(self):
        rc = export.main(["--input", str(self.src), "--outdir",
                          str(self.root / "sub"), "--to", "docx,tex,pdf",
                          "--dry-run"])
        self.assertEqual(rc, export.EXIT_OK)

    def test_json输出可解析且含环境与校验(self):
        out = self.root / "r.json"
        with mock.patch.object(export.toolchain, "probe_all",
                               lambda: fake_probe()), \
             mock.patch.object(export.subprocess, "run", _runner(0)):
            rc = export.main(["--input", str(self.src), "--outdir",
                              str(self.root / "sub"), "--to", "docx",
                              "--json", str(out)])
        self.assertEqual(rc, export.EXIT_OK)
        data = json.loads(out.read_text(encoding="utf-8"))
        self.assertIn("environment", data)
        self.assertIn("verify", data["items"][0])
        self.assertTrue(data["source_md5"]["unchanged"])

    def test_输出目录自动创建(self):
        target = self.root / "a" / "b" / "submission"
        with mock.patch.object(export.toolchain, "probe_all",
                               lambda: fake_probe(pandoc=False)):
            export.main(["--input", str(self.src), "--outdir", str(target)])
        self.assertTrue(target.is_dir())


if __name__ == "__main__":
    unittest.main()
