"""Markdown → HTML 结构渲染 —— 纯格式转换，不产生任何内容。

定位同 `paper-search/scripts/render_html.py`（"MD → HTML 的确定性转换，类比编译器"），
逐行状态机起家，补齐产物 MD 实际用到的结构：`###`/`####` 标题、嵌套列表、有序列表、
`>` 引用、`**粗体**`、`` `code` ``、水平线。

产物 MD 有一套真实存在的公共骨架（13/13 份模板一致），本模块据此认三个特殊位置：

* `# 一级标题` → 档案标题（`.doc-title`）
* 紧随其后的 `| 项 | 内容 |` 两列元表 → 档案头元信息（`.doc-meta`）；其中标注行
  （`| 内容标注 | 👤 …　·　📋 … |`）单独抽出渲染成四层图例（`.legend`）
* 末尾的斜体单行 → 人机分工页脚（`<footer>`）

其余一律按通用块渲染——**不匹配块标题文案**。块标题跨 skill 有三套命名风格
（裸语义名 / 中文数字序号 / emoji 前缀），匹配文案必然漂移。
"""
from __future__ import annotations

import html
import re
from typing import Dict, List, Tuple

from . import annotate

# 行内语法一遍过：code 优先（保护其中的 * 不被当格式），再链接，再粗体，再斜体
_INLINE = re.compile(
    r"`([^`]+)`"                        # 1 code
    r"|\[([^\]]*)\]\(([^)\s]+)\)"       # 2 链接文字 3 URL
    r"|\*\*([^*]+)\*\*"                 # 4 粗体
    r"|(?<!\*)\*([^*\n]+)\*(?!\*)"      # 5 斜体
)

# URL 白名单。`render_html.py:36` 只做 escape，`[x](javascript:alert(1))` 会产出活链接
_SAFE_SCHEME = re.compile(r"^(?:https?:|mailto:|#|/|\./|\.\./|[\w./-]+(?:#|$))", re.I)

_SEP_CHARS = set("-: |")


def _safe_url(url: str) -> str:
    """通过白名单的返回转义后的 URL，否则返回空串（调用方降级为纯文本）。"""
    u = url.strip()
    if not u or not _SAFE_SCHEME.match(u):
        return ""
    return html.escape(u, quote=True)


def inline(text: str, mapping: Dict[str, str]) -> str:
    """行内渲染：转义 → 格式化 → 四层符号染色。"""
    out: List[str] = []
    last = 0
    for m in _INLINE.finditer(text):
        out.append(html.escape(text[last:m.start()]))
        code, label, url, bold, ital = m.groups()
        if code is not None:
            out.append(f"<code>{html.escape(code)}</code>")
        elif url is not None:
            safe = _safe_url(url)
            inner = html.escape(label or url)
            if safe:
                out.append(f'<a href="{safe}" target="_blank" rel="noopener">{inner}</a>')
            else:
                # 协议不在白名单：只留文字，不产出可点链接
                out.append(inner)
        elif bold is not None:
            out.append(f"<strong>{html.escape(bold)}</strong>")
        else:
            out.append(f"<em>{html.escape(ital)}</em>")
        last = m.end()
    out.append(html.escape(text[last:]))
    return annotate.apply("".join(out), mapping)


def _is_table_row(s: str) -> bool:
    return s.startswith("|") and s.endswith("|") and len(s) > 1


def _cells(s: str) -> List[str]:
    return [c.strip() for c in s.strip("|").split("|")]


def _is_sep_row(cells: List[str]) -> bool:
    joined = "".join(cells)
    return bool(joined) and set(joined) <= _SEP_CHARS


def split_meta(md: str) -> Tuple[str, List[Tuple[str, str]], List[str]]:
    """切出 (h1 标题, 元表键值对, 余下行)。

    元表 = h1 之后遇到的第一张两列表。找不到就返回空表，余下行原样——`paper-daily`
    用 `>` blockquote 代替元表，`paper-screen`/`paper-style` 目前没有 MD 模板，
    都会走这条兜底路径，不能因此崩。
    """
    lines = md.splitlines()
    title = ""
    meta: List[Tuple[str, str]] = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("# "):
            title = s[2:].strip()
            i += 1
            break
        if s:
            break                      # h1 之前就有正文，不找元表
        i += 1
    # 跳过空行找元表
    j = i
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j < len(lines) and _is_table_row(lines[j].strip()):
        rows: List[List[str]] = []
        k = j
        while k < len(lines) and _is_table_row(lines[k].strip()):
            c = _cells(lines[k].strip())
            if not _is_sep_row(c):
                rows.append(c)
            k += 1
        # 只认两列表，且首行是表头（`| 项 | 内容 |`）
        if rows and all(len(r) == 2 for r in rows):
            meta = [(r[0], r[1]) for r in rows[1:]]
            i = k
    return title, meta, lines[i:]


# 独占一行的图片语法。`paper-screen` 靠它引 PRISMA 流程图：MD 里是普通图片引用
# （单独看也成立），渲染时若 `--embed-svg` 提供了该文件内容就整段内嵌、产物自包含
_FIGURE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)$")


class _Blocks:
    """块级状态机。列表用缩进栈支持嵌套；表格按行累积。"""

    def __init__(self, mapping: Dict[str, str], svg: Dict[str, str] = None):
        self.map = mapping
        self.svg = svg or {}
        self.out: List[str] = []
        # 每层 [缩进, ul|ol, 该层是否有未闭合的 li]。li 延迟闭合，子列表才能嵌在
        # 父 li 内部——嵌套 ul 直接挂在 ul 下不合 HTML 规范
        self.stack: List[List] = []
        self.headers: List[str] = []
        self.in_table = False
        self.in_quote = False
        # 每个 `##` 块包一个 <section>。若把所有块平铺成 .page 的直接子元素，
        # §2.7 的 rise 错峰动画级数会爆到几十级（末尾元素要等一秒多才淡入），
        # 且丢掉章节的语义分组——原模板就是 <section> 分块的
        self.in_section = False

    # ── 收尾 ────────────────────────────────────────────────
    def _close_lists(self, to_indent: int = -1) -> None:
        while self.stack and self.stack[-1][0] > to_indent:
            _, tag, li_open = self.stack.pop()
            if li_open:
                self.out.append("</li>")
            self.out.append(f"</{tag}>")

    def _close_table(self) -> None:
        if self.in_table:
            self.out.append("</tbody></table></div>")
            self.in_table = False
            self.headers = []

    def _close_quote(self) -> None:
        if self.in_quote:
            self.out.append("</blockquote>")
            self.in_quote = False

    def _close_all(self, lists: bool = True) -> None:
        self._close_table()
        self._close_quote()
        if lists:
            self._close_lists()

    # ── 行处理 ──────────────────────────────────────────────
    def feed(self, raw: str) -> None:
        s = raw.strip()
        indent = len(raw) - len(raw.lstrip(" \t"))

        if _is_table_row(s):
            self._row(s)
            return
        self._close_table()

        if not s:
            # 空行只断段落与引用，不断列表——MD 的 loose list 语义
            self._close_quote()
            return

        m = re.match(r"(#{1,6})\s+(.*)", s)
        if m:
            self._close_all()
            self._heading(len(m.group(1)), m.group(2))
            return

        m = _FIGURE.match(s)
        if m:
            self._close_lists()
            self._figure(m.group(1), m.group(2))
            return

        if s.startswith(">"):
            self._close_lists()
            if not self.in_quote:
                self.out.append("<blockquote>")
                self.in_quote = True
            self.out.append(f"<p>{inline(s.lstrip('> ').strip(), self.map)}</p>")
            return
        self._close_quote()

        if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", s):
            self._close_lists()
            self.out.append("<hr>")
            return

        m = re.match(r"(?:[-*+]|(\d+)[.)])\s+(.*)", s)
        if m:
            self._item(indent, "ol" if m.group(1) else "ul", m.group(2))
            return

        self._close_lists()
        self.out.append(f"<p>{inline(s, self.map)}</p>")

    def _close_section(self) -> None:
        if self.in_section:
            self.out.append("</section>")
            self.in_section = False

    def _heading(self, level: int, text: str) -> None:
        # 产物内所有 `##` 都是章节块标题；h1 已被 split_meta 摘走，重复出现降级为 h2
        tag = "h2" if level <= 2 else f"h{min(level, 6)}"
        if tag == "h2":
            self._close_section()
            self.out.append("<section>")
            self.in_section = True
            self.out.append(f'<h2 class="section">{inline(text, self.map)}</h2>')
            return
        self.out.append(f"<{tag}>{inline(text, self.map)}</{tag}>")

    def _figure(self, alt: str, src: str) -> None:
        """独占一行的图片。SVG 内容已提供则整段内嵌（产物自包含、断网可看），
        否则退化为 `<img>` 外链引用——**不静默丢图**。"""
        cap = f"<figcaption>{inline(alt, self.map)}</figcaption>" if alt else ""
        body = self.svg.get(src) or self.svg.get(src.rsplit("/", 1)[-1])
        if body:
            self.out.append(f"<figure>{body}{cap}</figure>")
            return
        safe = _safe_url(src)
        if safe:
            self.out.append(
                f'<figure><img src="{safe}" alt="{html.escape(alt)}">{cap}</figure>')
        elif cap:
            self.out.append(f"<figure>{cap}</figure>")

    def _item(self, indent: int, tag: str, text: str) -> None:
        self._close_lists(indent)
        if not self.stack or self.stack[-1][0] < indent:
            # 新开一层。父层的 li 故意不关——子列表要落在它内部
            self.out.append(f"<{tag}>")
            self.stack.append([indent, tag, False])
        elif self.stack[-1][1] != tag:
            # 同缩进换了列表类型（ul ↔ ol）
            _, old, li_open = self.stack.pop()
            if li_open:
                self.out.append("</li>")
            self.out.append(f"</{old}>")
            self.out.append(f"<{tag}>")
            self.stack.append([indent, tag, False])
        elif self.stack[-1][2]:
            self.out.append("</li>")
            self.stack[-1][2] = False
        self.out.append(f"<li>{inline(text, self.map)}")
        self.stack[-1][2] = True

    def _row(self, s: str) -> None:
        cells = _cells(s)
        if _is_sep_row(cells):
            return
        if not self.in_table:
            self._close_lists()
            self._close_quote()
            self.headers = cells
            head = "".join(f"<th>{inline(c, self.map)}</th>" for c in cells)
            self.out.append(f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>')
            self.in_table = True
            return
        tds = "".join(f"<td>{inline(c, self.map)}</td>" for c in cells)
        self.out.append(f"<tr>{tds}</tr>")

    def finish(self) -> str:
        self._close_all()
        self._close_section()
        return "\n".join(self.out)


def render_blocks(lines: List[str], mapping: Dict[str, str],
                  svg: Dict[str, str] = None) -> Tuple[str, List[str]]:
    """渲染正文块，并把末尾的斜体单行摘成页脚返回。"""
    body = list(lines)
    footer: List[str] = []
    while body:
        s = body[-1].strip()
        if not s or re.fullmatch(r"-{3,}", s):
            body.pop()
            continue
        if len(s) > 2 and s.startswith("*") and s.endswith("*") and not s.startswith("**"):
            footer.insert(0, s.strip("*").strip())
            body.pop()
            continue
        break
    m = _Blocks(mapping, svg)
    for line in body:
        m.feed(line)
    return m.finish(), footer
