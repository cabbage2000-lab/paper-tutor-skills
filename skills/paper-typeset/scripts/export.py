#!/usr/bin/env python3
"""paper-typeset 转换内核——探测 / 组装 / 执行 / 正文一致性校验 / 降级报告。

设计要点：**只换容器、不改一个字**。转换后对 `.tex` 做正文汉字序列逐字比对；
`.docx` / `.pdf` 是二进制，**校验不到就如实说校验不到**——对它们谎称做过字符级
校验比不校验更坏，用户会以为有保障。

环境缺失一律走结构化降级：报「未生成什么 · 为什么 · 装什么 · 手工命令是什么」，
**绝不假装成功、绝不用模型生成一个"看起来像"的产物**（CLAUDE.md 唯一保留的
代码层约束）。

pandoc / xelatex 是外部二进制（`subprocess`），非 Python 包依赖。纯标准库，3.9+。
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import shlex
import subprocess
import sys
from typing import Dict, List, Optional, Sequence, Tuple

# 标准三行引导头（同 paper-doctor/scripts/doctor.py）：parents[2] = skills/，其下 _shared/
_SKILLS = pathlib.Path(__file__).resolve().parents[2]
if str(_SKILLS / "_shared") not in sys.path:
    sys.path.insert(0, str(_SKILLS / "_shared"))

from paper_shared import toolchain  # noqa: E402

_SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
_CSL_DIR = _SKILL_ROOT / "references" / "csl"
_CSL_ALIASES = {
    "numeric": "gbt7714-2015-numeric.csl",
    "author-date": "gbt7714-2015-author-date.csl",
}

# 退出码。五个码对应五个互不相同的处置动作，故不合并（见 SKILL.md 处置表）。
EXIT_OK = 0
EXIT_RUN_FAILED = 1        # pandoc/xelatex 跑了、返回非零
EXIT_DEGRADED = 2          # 环境缺失，部分或全部未生成
EXIT_INPUT = 3             # 读不到输入 / 输出目录不可写 / CSL 路径错
EXIT_VERIFY_FAILED = 4     # 正文一致性校验失败——最严重：转换改动了正文

_FORMAT_DEPS = {
    "docx": ("pandoc",),
    "tex": ("pandoc",),
    "pdf": ("pandoc", "xelatex"),
}

_CJK_RE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


# ── 组装层（纯函数，最该单测：组装错了会静默产出错误格式）─────────────────
def resolve_csl(spec: Optional[str]) -> Optional[pathlib.Path]:
    """把 `numeric` / `author-date` 简写或路径解析成 CSL 文件路径。

    路径不存在时**抛错而非静默跳过**：跳过 CSL 会产出非国标著录，而用户正是
    为了国标才来的——静默降级在这里等于交付一个错东西。
    """
    if not spec:
        return None
    if spec in _CSL_ALIASES:
        p = _CSL_DIR / _CSL_ALIASES[spec]
        if not p.is_file():
            raise FileNotFoundError(f"内置 CSL 缺失：{p}")
        return p
    p = pathlib.Path(spec)
    if not p.is_file():
        raise FileNotFoundError(f"CSL 文件不存在：{spec}")
    return p


def build_cmd(src: pathlib.Path, out: pathlib.Path, fmt: str,
              csl: Optional[pathlib.Path] = None,
              bib: Optional[pathlib.Path] = None,
              cjk_font: Optional[str] = None) -> List[str]:
    """组装 pandoc 命令。不碰文件系统、不执行。"""
    cmd = ["pandoc", str(src), "-o", str(out)]
    if bib:
        # pandoc 2.11+ 起 --csl / --bibliography **不再自动启用 citeproc**，
        # 只给这两个参数会让引用原样输出成 [@key]——产物"生成成功"了、
        # 参考文献却没渲染。本命令最容易静默错的一处，故 --citeproc 显式给。
        cmd.append("--citeproc")
        cmd.append(f"--bibliography={bib}")
        if csl:
            cmd.append(f"--csl={csl}")
    if fmt == "tex":
        # 不加 --standalone 产出的是无导言区的片段，没法单独编译
        cmd.append("--standalone")
    if fmt == "pdf":
        cmd.append("--pdf-engine=xelatex")
    if fmt in ("tex", "pdf") and cjk_font:
        # 中文 PDF 最常踩的坑：缺 CJKmainfont 会整篇缺字或直接编译失败。
        # `-V` 与其值**必须是两个 argv 元素**：合并成 `"-V CJKmainfont=…"` 一个元素
        # 时，subprocess 会把整串当一个参数交给 pandoc（pandoc 不认），而
        # `shlex.join` 又会把它整体加引号——于是 --dry-run 打印出的"可手工执行的
        # 完整命令"复制去 shell 里同样跑不通。而那条命令是三条不变②对用户的承诺。
        cmd.extend(["-V", f"CJKmainfont={cjk_font}"])
    return cmd


# ── 一致性校验（三条不变①的可执行落点）────────────────────────────────────
def strip_html_comments(text: str) -> str:
    """剥 HTML 注释。pandoc 默认丢弃 `<!-- -->`，不剥会把注释里的汉字算成"丢失"。"""
    return _HTML_COMMENT_RE.sub("", text)


def cjk_sequence(text: str) -> str:
    """按序抽出全部汉字拼成一串。

    校验依据：**LaTeX 命令与结构标记都是 ASCII**，不含汉字。所以源正文的汉字
    序列应当原样出现在 `.tex` 里；一旦不一致，说明转换动了正文。
    """
    return "".join(_CJK_RE.findall(text))


def verify_tex(src_text: str, tex_text: str, has_bib: bool) -> Dict:
    """校验 .tex 的正文汉字序列。返回 {ok, mode, detail}。

    有 bib 时判据必须放宽为「子串」而非「相等」：参考文献条目由 CSL 生成并追加，
    产出的汉字必然多于源。要求相等会把一次正确的转换报成正文被改。
    """
    src_seq = cjk_sequence(strip_html_comments(src_text))
    out_seq = cjk_sequence(tex_text)
    if not src_seq:
        return {"ok": True, "mode": "skipped",
                "detail": "源文件无汉字，跳过汉字序列比对（非中文稿件）"}
    if has_bib:
        ok = src_seq in out_seq
        return {"ok": ok, "mode": "substring",
                "detail": ("正文汉字序列一致；参考文献条目为 CSL 生成的新增内容"
                           if ok else
                           f"正文汉字序列未原样出现在产物中（源 {len(src_seq)} 字 / "
                           f"产物 {len(out_seq)} 字）")}
    ok = src_seq == out_seq
    if ok:
        return {"ok": True, "mode": "exact",
                "detail": f"正文汉字序列逐字比对一致（{len(src_seq)} 字）"}
    return {"ok": False, "mode": "exact",
            "detail": f"正文汉字序列不一致：源 {len(src_seq)} 字、产物 {len(out_seq)} 字，"
                      f"首个差异位置 {_first_diff(src_seq, out_seq)}"}


def _first_diff(a: str, b: str) -> str:
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return f"第 {i + 1} 字（源「{x}」/ 产物「{y}」）"
    return f"第 {min(len(a), len(b)) + 1} 字（一方到此结束）"


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


# ── 执行层 ────────────────────────────────────────────────────────────────
def _missing_deps(fmt: str, probe: Dict) -> List[str]:
    return [d for d in _FORMAT_DEPS[fmt] if not probe[d]["available"]]


def run_export(src: pathlib.Path, outdir: pathlib.Path, formats: Sequence[str],
               csl: Optional[pathlib.Path] = None,
               bib: Optional[pathlib.Path] = None,
               cjk_font: Optional[str] = None,
               probe: Optional[Dict] = None,
               dry_run: bool = False,
               stem: str = "正文") -> Dict:
    """逐格式转换。返回结构化报告 dict（不打印、不决定退出码，便于单测）。"""
    probe = probe or toolchain.probe_all()
    src_text = src.read_text(encoding="utf-8")
    src_md5_before = _md5(src.read_bytes())
    has_cjk = bool(cjk_sequence(src_text))
    if cjk_font is None and probe["cjk_fonts"]["available"]:
        cjk_font = probe["cjk_fonts"]["fonts"][0]

    items: List[Dict] = []
    for fmt in formats:
        out = outdir / f"{stem}.{fmt}"
        cmd = build_cmd(src, out, fmt, csl=csl, bib=bib, cjk_font=cjk_font)
        item: Dict = {"format": fmt, "output": str(out),
                      "command": shlex.join(cmd), "status": None}

        missing = _missing_deps(fmt, probe)
        # 中文稿 + 无中文字体 + 出 PDF = 一份整篇方框的 PDF。那是「假装成功」，
        # 宁可不产：把它归入降级、报清原因，比交付一个不可用的 PDF 诚实。
        if fmt == "pdf" and has_cjk and not probe["cjk_fonts"]["available"]:
            missing = missing + ["中文字体"]
        if missing and not dry_run:
            fixes = [probe[m]["fix"] for m in missing if m in probe]
            if "中文字体" in missing:
                fixes.append(probe["cjk_fonts"]["fix"])
            item.update(status="skipped", missing=missing,
                        reason="未检测到：" + "、".join(missing),
                        fix=[f for f in fixes if f])
            items.append(item)
            continue

        if dry_run:
            item.update(status="dry_run",
                        reason="仅组装命令，未执行（--dry-run）")
            items.append(item)
            continue

        try:
            proc = subprocess.run(cmd, capture_output=True,
                                  text=True, errors="replace", timeout=300)
        except (OSError, subprocess.SubprocessError) as e:
            item.update(status="failed", returncode=None,
                        stderr=f"{type(e).__name__}: {e}")
            items.append(item)
            continue

        if proc.returncode != 0:
            item.update(status="failed", returncode=proc.returncode,
                        stderr=(proc.stderr or proc.stdout or "").strip()[:2000])
            items.append(item)
            continue

        if not out.is_file() or out.stat().st_size == 0:
            # pandoc 返回 0 却没产出文件（罕见，但静默过去等于谎称成功）
            item.update(status="failed", returncode=0,
                        stderr="pandoc 返回 0 但未产出非空文件")
            items.append(item)
            continue

        item.update(status="ok", size=out.stat().st_size)
        if fmt == "tex":
            item["verify"] = verify_tex(src_text,
                                        out.read_text(encoding="utf-8",
                                                      errors="replace"),
                                        has_bib=bool(bib))
            if not item["verify"]["ok"]:
                item["status"] = "verify_failed"
        else:
            item["verify"] = {
                "ok": None, "mode": "unavailable",
                "detail": f"{fmt} 是二进制产物，无法做字符级比对；"
                          f"已校验源文件转换前后 md5 未变、产物非空",
            }
        items.append(item)

    src_md5_after = _md5(src.read_bytes())
    return {
        "input": str(src),
        "outdir": str(outdir),
        "source_md5": {"before": src_md5_before, "after": src_md5_after,
                       "unchanged": src_md5_before == src_md5_after},
        "cjk_font_used": cjk_font,
        "csl": str(csl) if csl else None,
        "bibliography": str(bib) if bib else None,
        "environment": probe,
        "items": items,
    }


def decide_exit(report: Dict) -> int:
    """由报告决定退出码。优先级：校验失败 > 执行失败 > 降级 > 正常。"""
    statuses = {i["status"] for i in report["items"]}
    if not report["source_md5"]["unchanged"]:
        # 源文件在转换过程中被改了——不该发生，但若发生必须最高优先级报出
        return EXIT_VERIFY_FAILED
    if "verify_failed" in statuses:
        return EXIT_VERIFY_FAILED
    if "failed" in statuses:
        return EXIT_RUN_FAILED
    if "skipped" in statuses:
        return EXIT_DEGRADED
    return EXIT_OK


def render_report(report: Dict) -> str:
    """人类可读报告。降级项必须给「未生成什么 · 为什么 · 装什么 · 手工命令」四件套。"""
    lines = [f"输入：{report['input']}", f"输出目录：{report['outdir']}"]
    if report["cjk_font_used"]:
        lines.append(f"中文字体：{report['cjk_font_used']}")
    if report["csl"]:
        lines.append(f"著录样式（CSL）：{report['csl']}")
    lines.append(f"源文件 md5 转换前后：{'未变 ✅' if report['source_md5']['unchanged'] else '已变 ⚠️'}")
    lines.append("")
    for it in report["items"]:
        fmt, st = it["format"], it["status"]
        if st == "ok":
            lines.append(f"✅ {fmt}：已生成 {it['output']}（{it['size']} 字节）")
            lines.append(f"   正文校验：{it['verify']['detail']}")
        elif st == "verify_failed":
            lines.append(f"⚠️ {fmt}：已生成但**正文校验未通过**——该产物不可信，勿直接投稿")
            lines.append(f"   {it['verify']['detail']}")
        elif st == "skipped":
            lines.append(f"⛔ {fmt}：未生成 · 原因：{it['reason']}")
            for f in it.get("fix", []):
                lines.append(f"   安装指引：{f}")
            lines.append(f"   装好后可手工执行：{it['command']}")
        elif st == "failed":
            rc = it.get("returncode")
            lines.append(f"❌ {fmt}：转换失败（退出码 {rc}）")
            lines.append(f"   命令：{it['command']}")
            for ln in (it.get("stderr") or "").splitlines()[:12]:
                lines.append(f"   | {ln}")
        elif st == "dry_run":
            lines.append(f"🔍 {fmt}：{it['command']}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI。退出码：0 全部成功 / 1 执行失败 / 2 环境缺失降级 / 3 输入问题 / 4 校验失败。"""
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Markdown → LaTeX / DOCX / PDF 转换管线")
    ap.add_argument("--input", help="源 markdown 路径")
    ap.add_argument("--outdir", default="submission", help="输出目录（默认 submission/）")
    ap.add_argument("--to", default="docx", help="目标格式，逗号分隔：docx,tex,pdf")
    ap.add_argument("--csl", help="numeric / author-date（内置国标）或 CSL 文件路径")
    ap.add_argument("--bib", help="BibTeX 文件路径（给了才启用 citeproc）")
    ap.add_argument("--cjk-font", dest="cjk_font", help="中文字体族名（不给则自动探测）")
    ap.add_argument("--stem", default="正文", help="输出文件主名（默认「正文」）")
    ap.add_argument("--probe", action="store_true", help="只探测环境并输出 JSON，不转换")
    ap.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="只组装并打印命令，不执行")
    ap.add_argument("--json", dest="json_out", help="结构化报告输出路径")
    args = ap.parse_args(argv)

    if args.probe:
        json.dump(toolchain.probe_all(), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return EXIT_OK

    if not args.input:
        print("未指定输入：用 --input <markdown 路径>（或 --probe 只看环境）。")
        return EXIT_INPUT
    src = pathlib.Path(args.input)
    if not src.is_file():
        print(f"读不到输入文件：{src}")
        print("请确认路径正确；manuscript/ 尚无正文则先用 /paper-draft 起草。")
        return EXIT_INPUT

    formats: List[str] = []
    for f in args.to.split(","):
        f = f.strip().lower()
        if not f:
            continue
        if f not in _FORMAT_DEPS:
            print(f"不支持的目标格式：{f}（支持 docx / tex / pdf）")
            return EXIT_INPUT
        if f not in formats:
            formats.append(f)
    if not formats:
        print("未指定目标格式：--to docx,tex,pdf")
        return EXIT_INPUT

    try:
        csl = resolve_csl(args.csl)
    except FileNotFoundError as e:
        # CSL 找不到不静默跳过——跳过等于产出非国标著录，而用户是为国标来的
        print(str(e))
        print("可用简写：numeric（顺序编码制）/ author-date（著者-出版年制）")
        return EXIT_INPUT

    bib = None
    if args.bib:
        bib = pathlib.Path(args.bib)
        if not bib.is_file():
            print(f"读不到 BibTeX 文件：{bib}")
            return EXIT_INPUT

    outdir = pathlib.Path(args.outdir)
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"输出目录不可写：{outdir}")
        print(f"  原因：{e.strerror or e}")
        return EXIT_INPUT

    report = run_export(src, outdir, formats, csl=csl, bib=bib,
                        cjk_font=args.cjk_font, dry_run=args.dry_run,
                        stem=args.stem)
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(render_report(report))
    return EXIT_OK if args.dry_run else decide_exit(report)


if __name__ == "__main__":
    raise SystemExit(main())
