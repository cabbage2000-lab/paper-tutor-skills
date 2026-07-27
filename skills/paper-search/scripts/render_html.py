#!/usr/bin/env python3
"""文献笔记表.md → HTML 视图（纯格式转换，零依赖）。

定位：MD → HTML 的确定性转换（类比编译器），不产生任何研究内容，故允许直接写 .html
（paper-search spec §3）。渲染可点击 DOI 链接、覆盖方式色标、撤稿高亮。
"""
from __future__ import annotations

import argparse
import html
import pathlib
import re
import sys

_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_COVERAGE_CLASS = {"自动检索": "auto", "用户回填": "manual", "未覆盖": "none"}

_CSS = """
body{font-family:-apple-system,'Segoe UI',sans-serif;margin:2rem;color:#1a1a1a;line-height:1.5}
h1{font-size:1.5rem}h2{font-size:1.1rem;margin-top:1.4rem}
.notice{background:#fff8e1;border-left:4px solid #f6a609;padding:.75rem 1rem;margin:1rem 0}
table{border-collapse:collapse;width:100%;font-size:.9rem;margin:.6rem 0}
th,td{border:1px solid #ddd;padding:.4rem .6rem;text-align:left;vertical-align:top}
th{background:#f5f5f5}
.auto{color:#137333;font-weight:600}.manual{color:#b06000;font-weight:600}.none{color:#888}
.retracted{background:#fce8e6;color:#c5221f;font-weight:600}
footer{margin-top:1.5rem;color:#666;font-style:italic;font-size:.85rem}
"""


def _md_inline(text):
    """行内 Markdown：链接 [t](u) → <a>，其余 HTML 转义。"""
    out, last = [], 0
    for m in _LINK.finditer(text):
        out.append(html.escape(text[last:m.start()]))
        label, url = html.escape(m.group(1)), html.escape(m.group(2), quote=True)
        out.append(f'<a href="{url}" target="_blank" rel="noopener">{label}</a>')
        last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out)


def _render_row(cells, headers):
    tds = []
    for i, c in enumerate(cells):
        head = headers[i] if i < len(headers) else ""
        cls = _COVERAGE_CLASS.get(c.strip(), "") if head == "覆盖方式" else ""
        if "撤" in c or "retract" in c.lower():
            cls = "retracted"
        inner = _md_inline(c)
        tds.append(f'<td class="{cls}">{inner}</td>' if cls else f"<td>{inner}</td>")
    return "<tr>" + "".join(tds) + "</tr>"


def md_to_html(md):
    body, headers, in_table = [], [], False
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):        # 表格分隔行，跳过
                continue
            if not in_table:
                headers = cells
                body.append("<table><thead><tr>"
                            + "".join(f"<th>{_md_inline(c)}</th>" for c in cells)
                            + "</tr></thead><tbody>")
                in_table = True
            else:
                body.append(_render_row(cells, headers))
            continue
        if in_table:
            body.append("</tbody></table>")
            in_table = False
        if s.startswith("# "):
            body.append(f"<h1>{_md_inline(s[2:])}</h1>")
        elif s.startswith("## "):
            body.append(f"<h2>{_md_inline(s[3:])}</h2>")
        elif s.startswith("⚠️") or "不等于" in s:
            body.append(f'<div class="notice">{_md_inline(s)}</div>')
        elif s.startswith("*") and s.endswith("*") and len(s) > 2:
            body.append(f"<footer>{_md_inline(s.strip('*'))}</footer>")
        elif s and not s.startswith("---"):
            body.append(f"<p>{_md_inline(s)}</p>")
    if in_table:
        body.append("</tbody></table>")
    return ("<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>"
            "<title>文献笔记表</title><style>" + _CSS + "</style></head><body>"
            + "".join(body) + "</body></html>")


def main(argv=None):
    p = argparse.ArgumentParser(description="文献笔记表.md → HTML 视图（纯转换）。")
    p.add_argument("--in", dest="src", required=True, help="输入 Markdown 文件")
    p.add_argument("--out", dest="dst", help="输出 HTML（默认同名 .html）")
    args = p.parse_args(argv)
    src = pathlib.Path(args.src)
    dst = pathlib.Path(args.dst) if args.dst else src.with_suffix(".html")
    dst.write_text(md_to_html(src.read_text(encoding="utf-8")), encoding="utf-8")
    sys.stderr.write(f"已生成 {dst}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
