#!/usr/bin/env python3
"""paper-anchor 支撑缺口扫描内核——按段落数引用密度、定位零引用段与既有 ⚠️ 标记。

**本脚本只定位「哪里引用密度为零」，绝不判断「这里是否需要引用」。** 方法章的操作
步骤本来就可以零引用；一段有三个引用的文字里仍可能有一句无据的强论断。「需不需要
引用」是模型陈列 + 用户拍板的事，脚本给的是**机械事实**。

所以输出里没有一个判定词：没有「缺支撑」「不足」「偏低」，只有计数与密度。产物侧
一律写「📋 机械定位：本段引用数 0」，不写「本段缺文献支撑」——两者的距离由 SKILL.md
的措辞承担（同 `paper-style`「脚本只排序、不下结论」）。

支撑形态四种，缺一种都会让某类写法被误判成零引用：

  1. 锚点链接 —— `[Smith 2023](literature/文献笔记表.md#smith2023)`，outline / draft 的约定格式
  2. 著者-出版年制 —— `（张三, 2020）` / `(Smith et al., 2019)`
  3. 顺序编码制 —— `[3]` / `[1,2]` / `[5-7]`
  4. 引用块 —— `> 引文`，人文学科的文本引证（`paper-style` 剥掉它，本命令必须留）

**引用块自成一档、不计入 `total_citations`**（真实语料上验证出来的）：markdown 的
`>` 在中文写作里既用于文本引证、也大量用于**排版强调框**，机器分不清这两者。计入
就会把强调框虚报成支撑、让缺口漏报（比误判零引用更坏——用户以为这里有支撑）；不计
又会把人文的文本引证段误判成零引用。故两边都不选：只有引用块的段落单列进
`blockquote_only_indices`，交用户逐段确认。这条与 `paper-verify` 的「待人工核对」
态同源——**机器分不清的，如实说分不清，不替用户选一边**。

**顺序依赖（改本文件前先读）**：`_shared/paper_shared/citations.py` 的两类函数对
输入的要求相反——

    ① 在**原始段落文本**上做：`count_anchor_links` / `find_warning_marks` /
       `count_blockquote_lines`（剥完 markdown 后链接被转成纯文字、⚠️ 被剥掉，
       一律归零且不报错）
    ② 在**已 strip 的文本**上做：`count_inline_citations` / `split_sentences` /
       `effective_chars`（不先剥，`[1](url)` 这类链接会被顺序编码制正则命中而虚高）

把 ①② 的顺序调换不会报错，只会让计数静默错——`_stat_paragraph()` 里的两段注释
标了分界线，勿合并。

纯标准库（零第三方运行时依赖，最低 Python 3.9）。
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# 标准三行引导头（同 paper-doctor/scripts/doctor.py）：parents[2] = skills/，其下 _shared/
_SKILLS = pathlib.Path(__file__).resolve().parents[2]
if str(_SKILLS / "_shared") not in sys.path:
    sys.path.insert(0, str(_SKILLS / "_shared"))
from paper_shared.citations import (  # noqa: E402
    count_anchor_links, count_blockquote_lines, count_inline_citations,
    effective_chars, find_warning_marks, split_paragraphs, split_sentences,
    strip_markdown, strip_warning_marks,
)

_FIRST_SENTENCE_CHARS = 30      # 首句摘要长度：够对位，又不至于把整段灌进产物


@dataclass
class ParagraphStat:
    """一个段落的支撑事实。字段全是计数，没有判定。"""
    index: int                      # 全局序号，从 1 起（人读用）
    source: str                     # 来源文件名
    first_sentence: str             # 首句前 N 字，供用户对位到正文
    char_count: int
    anchor_links: int = 0
    inline_citations: Dict[str, int] = field(default_factory=dict)
    blockquote_lines: int = 0
    total_citations: int = 0
    existing_warnings: List[str] = field(default_factory=list)
    followed_by_blockquote: bool = False

    def to_dict(self) -> Dict:
        return dict(self.__dict__)


def _first_sentence(clean: str) -> str:
    """取首句前 N 字。切不出句子（无标点的短语段）时退到取正文前 N 字。"""
    sents = split_sentences(clean)
    head = sents[0] if sents else clean
    head = " ".join(head.split())          # 段内换行压成一行
    return head[:_FIRST_SENTENCE_CHARS] + ("…" if len(head) > _FIRST_SENTENCE_CHARS else "")


def _stat_paragraph(index: int, source: str, raw: str, clean: str) -> ParagraphStat:
    """算一个段落的四形态引用数。`raw` 是原始文本、`clean` 是已 strip 的文本。

    两个参数都要，不是冗余——见模块 docstring 的顺序依赖。
    """
    # ① 原始文本上做（剥完就找不到了）
    anchors = count_anchor_links(raw)
    warnings = find_warning_marks(raw)
    bq_lines = count_blockquote_lines(raw)

    # ② 已 strip 的文本上做（不剥会虚高）
    inline = count_inline_citations(clean)

    # 引用块**不计入** total——它可能是文本引证也可能是排版强调框，机器分不清
    # （见模块 docstring）。行数如实留在 blockquote_lines 里，由 `scan()` 把
    # 「只有引用块」的段单列出来交用户确认。
    total = anchors + sum(inline.values())
    return ParagraphStat(
        index=index,
        source=source,
        first_sentence=_first_sentence(clean),
        char_count=effective_chars(clean),
        anchor_links=anchors,
        inline_citations=inline,
        blockquote_lines=bq_lines,
        total_citations=total,
        existing_warnings=warnings,
    )


def scan(docs: List[Tuple[str, str]]) -> Dict:
    """扫描多份文档。`docs` 是 [(文件名, 原始文本)]。返回结构化事实。

    无正文的段（纯标题、纯表格、纯分割线）不计入——`split_paragraphs` 只做机械
    空行切分，过滤是调用方的责任（同 `paper-style` 对空章节的处理）。不过滤会让
    每个章节标题都成为一个「零引用段」，把计数顶得毫无意义。
    """
    stats: List[ParagraphStat] = []
    idx = 0
    for name, text in docs:
        raws = split_paragraphs(text)
        # 先剔缺口标记文本再 strip：标记里的「（锚点 Lee 2024 未在 literature/）」含
        # 4 位年份，会被著者-出版年制正则命中，把标了缺支撑的段算成有引用。
        cleans = [strip_markdown(strip_warning_marks(p), drop_blockquote=False)
                  for p in raws]
        # 相邻关系要在过滤前算：引文段常自成一段，它前面那段多是引导句
        # （「张三指出：」）。脚本只陈列「下一段是引用块」这个**事实**，
        # 不推断「所以这段有支撑」——那是模型与用户的判断。
        for k, (raw, clean) in enumerate(zip(raws, cleans)):
            if not clean.strip():
                continue
            idx += 1
            st = _stat_paragraph(idx, name, raw, clean)
            nxt = raws[k + 1] if k + 1 < len(raws) else ""
            st.followed_by_blockquote = bool(nxt) and count_blockquote_lines(nxt) > 0
            stats.append(st)

    # 零引用 = 无锚点、无行内引用、**也无引用块**。有引用块的段落归入
    # blockquote_only（机器分不清引证还是强调框），不并进零引用、也不算有支撑。
    zero = [s.index for s in stats
            if s.total_citations == 0 and not s.blockquote_lines]
    bq_only = [s.index for s in stats
               if s.total_citations == 0 and s.blockquote_lines]
    marks = [{"paragraph": s.index, "source": s.source, "line": line}
             for s in stats for line in s.existing_warnings]

    forms: List[str] = []
    if any(s.anchor_links for s in stats):
        forms.append("锚点链接")
    for label in ("著者-出版年制", "顺序编码制"):
        if any(s.inline_citations.get(label) for s in stats):
            forms.append(label)
    if any(s.blockquote_lines for s in stats):
        forms.append("引用块")

    chars = sum(s.char_count for s in stats)
    cites = sum(s.total_citations for s in stats)
    notes: List[str] = []
    # 判据只看**真引用形态**（锚点 / 两制式）——引用块是歧义形态，有它不等于有引用。
    # 一篇全脚注制的论文若同时用 `>` 做排版，forms 会非空，据此判「检出了引用」就
    # 会漏掉这条声明。
    if stats and not [f for f in forms if f != "引用块"]:
        notes.append(
            "未检出任何锚点链接或行内引用形态。若本文使用全脚注制（`[^1]`）或尾注，"
            "本脚本认不出，引用密度一项须声明「不可用」，不得据此说正文没有引用。")
    if any("纯结构占位" in ln for s in stats for ln in s.existing_warnings):
        notes.append("检出 `⚠️ 纯结构占位` 标记——来自 /paper-outline 的大纲产物，"
                     "指该要点当时未挂锚点。")
    if bq_only:
        notes.append(
            f"有 {len(bq_only)} 段只含引用块（`>`）而无其他引用形态。markdown 的 `>` "
            "既用于文本引证、也常用作排版强调框，本脚本分不清——这些段落既未计入"
            "零引用、也未计入有引用，须逐段人工确认是引证还是强调。")
    return {
        "paragraphs": [s.to_dict() for s in stats],
        "zero_citation_indices": zero,
        "blockquote_only_indices": bq_only,
        "warning_marks": marks,
        "citation_forms_found": forms,
        "coverage": {
            "total_paragraphs": len(stats),
            "zero_citation_count": len(zero),
            "blockquote_only_count": len(bq_only),
            "warning_count": len(marks),
            "total_citations": cites,
            "char_count": chars,
            # 密度只是「每千有效字有几处引用」，不是达标线——本项目无引用密度阈值，
            # 判定即价值结论（三条不变①）。
            "citation_density_per_1000": round(cites / chars * 1000, 2) if chars else 0.0,
        },
        "notes": notes,
    }


# ── CLI ────────────────────────────────────────────────────────────────────
def _render_text(payload: Dict) -> str:
    """人类可读输出。宿主 agent 转录数字时用 --json 更稳，这里供人工核对。"""
    cov = payload["coverage"]
    out = [
        f"段落：{cov['total_paragraphs']}　有效字：{cov['char_count']}",
        f"引用合计：{cov['total_citations']}　"
        f"每千字 {cov['citation_density_per_1000']}",
        f"零引用段：{cov['zero_citation_count']}　"
        f"仅含引用块（待人工确认）：{cov['blockquote_only_count']}　"
        f"既有 ⚠️ 标记：{cov['warning_count']}",
        f"检出的引用形态：{'、'.join(payload['citation_forms_found']) or '（无）'}",
        "",
    ]
    for p in payload["paragraphs"]:
        if p["total_citations"] == 0 and p["blockquote_lines"]:
            flag = "  ← 仅含引用块，待确认是引证还是强调"
        elif p["total_citations"] == 0:
            flag = "  ← 引用数 0"
        else:
            flag = ""
        out.append(f"[{p['index']}] {p['source']}｜{p['first_sentence']}{flag}")
        detail = (f"    引用 {p['total_citations']}"
                  f"（锚点 {p['anchor_links']}"
                  f" / 著者年 {p['inline_citations'].get('著者-出版年制', 0)}"
                  f" / 编码 {p['inline_citations'].get('顺序编码制', 0)}"
                  f" / 引文行 {p['blockquote_lines']}）"
                  f"　{p['char_count']} 字")
        if p["followed_by_blockquote"]:
            detail += "　下一段是引用块"
        out.append(detail)
        for ln in p["existing_warnings"]:
            out.append(f"    ⚠️ 既有标记：{ln}")
    if payload["notes"]:
        out.append("\n须如实声明的事项：")
        for n in payload["notes"]:
            out.append(f"  · {n}")
    out.append("\n本脚本只算引用密度，不判断哪里「需要」引用——需不需要由你与导师判断。")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI。退出码：0 算出结果 / 2 样本不足（切不出正文段）/ 3 读不到输入。

    只有三个码是有意的：本命令没有 `paper-screen` 那样的守恒等式，不存在「算得出
    但不可信」的中间态，样本不足是唯一必须拒绝出数的情形。不凑第四个。
    """
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="支撑缺口扫描：按段落数引用密度、定位零引用段与既有 ⚠️ 标记。")
    ap.add_argument("--input", action="append", default=[],
                    help="正文 markdown 路径（可重复）")
    ap.add_argument("--dir", help="目录，扫其中 *.md（按文件名排序）")
    ap.add_argument("--json", dest="json_out", help="JSON 输出路径（省略则打印文本）")
    args = ap.parse_args(argv)

    paths: List[pathlib.Path] = [pathlib.Path(p) for p in args.input]
    if args.dir:
        d = pathlib.Path(args.dir)
        if not d.is_dir():
            print(f"读不到目录：{args.dir}")
            print("请确认路径正确；manuscript/ 尚无正文则先用 /paper-draft 起草。")
            return 3
        paths.extend(sorted(d.glob("*.md")))
    if not paths:
        print("未指定输入：用 --input <文件> 或 --dir <目录>。")
        return 3

    docs: List[Tuple[str, str]] = []
    for p in paths:
        try:
            docs.append((p.name, p.read_text(encoding="utf-8")))
        except OSError as e:
            # 读不到是环境 / 输入问题，与「样本不足」区分：后者路径没错、只是字太少
            print(f"读不到输入文件：{p}")
            print(f"  原因：{e.strerror or e}")
            return 3

    payload = scan(docs)
    if payload["coverage"]["total_paragraphs"] == 0:
        print("样本不足：剥离标题 / 表格 / 代码块后切不出任何正文段落，不产扫描结果。")
        print(f"  输入：{'、'.join(p.name for p in paths)}")
        print("这不是错误——是可分析的正文太少。请补正文，或换一个包含正文的范围。")
        return 2

    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(_render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
