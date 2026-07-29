"""产物 Markdown → 学术档案风 HTML 的共享渲染器（纯转换、零依赖、断网可用）。

**为什么存在**：各 skill 的 HTML 报告原先由宿主 agent 逐字手写（读 200–600 行样式模板
再吐出等量 HTML），而同时落盘的 `.md` 兜底版承载完全相同的信息——SKILL.md 明文要求
「两份内容 N 块一致」，四层标注在 MD 里以 emoji 行内保留。HTML 因此是 MD 的机械投影，
交给脚本渲染即可，不该花模型的 token。

**定位**：与 `paper-search/scripts/render_html.py` 同性质——"MD → HTML 的确定性转换
（类比编译器），不产生任何研究内容"，故允许直接写文件、无需用户确认停点。

**产物零外部依赖**：样式内联，不引 CDN、不引 JS。这满足各 skill SKILL.md 里
「`grep -iE "https?://|<script src|cdn"` 期望 0 命中」的原始意图，也让产物落进用户
项目后断网照常打开。四层色值不在本包硬编码，全部由 `tokens.load()` 从
`_shared/tailwind.config.js` 解析（那里是产品死线的唯一权威）。

**不做的事**：不还原各 skill 的专属视觉组件（事实卡、四链卡、时间线、徽章族）。那些
承载的信息在 MD 里已由 emoji 完整保留，色带与卡片只是同一信息的第二种编码。渲染器
统一给「档案纸面骨架 + 表格 + 列表 + 四层染色」。
"""
from __future__ import annotations

import html
import pathlib
from typing import Dict, List, Optional, Tuple

from . import annotate, css, markdown
from .tokens import TokenError, load as load_tokens

__all__ = ["render", "write", "TokenError"]


def _doc_head(title: str, meta: List[Tuple[str, str]], label: str,
              mapping: Dict[str, str]) -> Tuple[str, str]:
    """档案头 + 四层图例。标注行从元表里摘出来单独做图例，不混在元信息里。"""
    parts: List[str] = []
    legend_row = ""
    legend_key = "内容标注"
    rows: List[Tuple[str, str]] = []
    for k, v in meta:
        if any(rk in k for rk in annotate.READER_KEYS) or "内容标注" in k:
            legend_row = v
            legend_key = k
        else:
            rows.append((k, v))

    parts.append("<header>")
    parts.append(f'<div class="doc-eyebrow">{html.escape(label)}</div>')
    if title:
        parts.append(f'<h1 class="doc-title">{markdown.inline(title, mapping)}</h1>')
    if rows:
        cells = "".join(
            f'<span><b class="k">{markdown.inline(k, mapping)}</b>'
            f"{markdown.inline(v, mapping)}</span>"
            for k, v in rows
        )
        parts.append(f'<div class="doc-meta">{cells}</div>')
    parts.append("</header>")

    if not legend_row:
        return "\n".join(parts), ""

    items = annotate.swatches(legend_row, mapping)
    if not items:
        return "\n".join(parts), ""
    lis = "".join(
        f'<li><span class="sw {cls}"></span>{html.escape(sym)} {html.escape(name)}</li>'
        for sym, name, cls in items
    )
    # 「没有第五层」这句只对四层轴成立；读者轴是另一个轴，不套这句（四层内容标注.md）
    is_reader = any(c.startswith("r") for c in mapping.values())
    note = ("" if is_reader else
            '<div class="legend-note">本报告不含「AI 的新判断」层 —— '
            "凡无法归入上述四层者即越界。</div>")
    legend = (
        f'<section class="legend">'
        f'<div class="legend-title">{html.escape(legend_key)} · Content Provenance</div>'
        f"<ul>{lis}</ul>{note}</section>"
    )
    return "\n".join(parts), legend


def render(md_text: str, skill: Optional[str] = None,
           svg: Optional[Dict[str, str]] = None,
           config_path: Optional[pathlib.Path] = None) -> str:
    """把产物 Markdown 渲染成单文件 HTML。

    skill：`.page` 右上角档案条的前缀（如 `paper-logic`）；省略则只用标题。
    svg：{文件名: SVG 文本}，供 MD 里独占一行的 `![说明](x.svg)` 内嵌自包含图形。
    """
    tokens = load_tokens(config_path)
    title, meta, rest = markdown.split_meta(md_text)
    mapping = annotate.axis([k for k, _ in meta])
    label = f"{skill} · {title}" if skill and title else (skill or title or "Paper Report")
    head, legend = _doc_head(title, meta, label, mapping)
    body, footer_lines = markdown.render_blocks(rest, mapping, svg)

    foot = ""
    if footer_lines:
        ps = "".join(f"<p>{markdown.inline(t, mapping)}</p>" for t in footer_lines)
        foot = ('<footer><div class="seal">Human–AI Division of Labor</div>'
                f"{ps}</footer>")

    doc_title = title or (skill or "Paper Report")
    return "\n".join([
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>{html.escape(doc_title)}</title>",
        "<style>" + css.build(tokens) + "</style>",
        "</head>",
        "<body>",
        f'<article class="page" data-label="{html.escape(label)}">',
        head,
        legend,
        body,
        foot,
        "</article>",
        "</body>",
        "</html>",
    ])


def write(md_path: pathlib.Path, html_path: Optional[pathlib.Path] = None,
          skill: Optional[str] = None,
          svg: Optional[Dict[str, str]] = None) -> pathlib.Path:
    """读 MD 文件、渲染、写同名 `.html`（或指定路径），返回产物路径。"""
    md_path = pathlib.Path(md_path)
    dst = pathlib.Path(html_path) if html_path else md_path.with_suffix(".html")
    dst.write_text(render(md_path.read_text(encoding="utf-8"), skill=skill, svg=svg),
                   encoding="utf-8")
    return dst
