#!/usr/bin/env python3
"""引用识别与文本切分——`paper-style` 与 `paper-anchor` 的共享内核。

为什么在共享层：两个 skill 都要认「哪里有引用」。各存一份正则必然漂移（硬规则 1
反对第二份真相），而漂移的表现是两个命令对同一段文本报出不同的引用数，谁对谁错
无从判断。

**两个消费者对「什么是噪声」的定义相反**，故预处理必须参数化：

| 元素 | `paper-style`（算风格特征） | `paper-anchor`（找支撑缺口） |
| --- | --- | --- |
| 引用块 `> ` | 剥掉——他人文字算进风格基线会让 `paper-draft` 去对齐被引作者的文风 | **保留并计数**——长引文正是支撑证据（人文的文本引证尤其如此） |
| markdown 链接 | 转成纯文字——只关心句长与虚词 | **先计数再转**——`[Smith 2023](literature/…)` 就是挂上的锚点 |
| 四层标注 emoji | 剥掉 | **先提取再剥**——`⚠️ 未经文献支撑` 是既有缺口标记 |
| 空行 | 无所谓（按标题切章） | **必须保留**——按空行分段是段落粒度的唯一依据 |

由此产生一条调用方必须遵守的**顺序依赖**：凡要数锚点链接、提 ⚠️ 标记、按空行分段
的，一律在**原始文本**上先做，再 `strip_markdown()`。顺序反了不会报错，只会让计数
静默归零——`paper-anchor/scripts/anchor_scan.py` 把这个顺序写在了它的 docstring 里，
改那个文件前先读。

纯标准库（零第三方运行时依赖，最低 Python 3.9）。
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Sequence, Tuple

_SENT_END = "。！？；…!?;"
_ABBREV = frozenset(
    ("al", "e", "g", "i", "cf", "fig", "eq", "vs", "dr", "no", "etc", "ca",
     "approx", "ed", "eds", "vol", "pp", "st", "mr", "ms", "prof")
)
_OPEN_PAIRS = "「『（《〈【〔(（[{“‘"
_CLOSE_PAIRS = "」』）》〉】〕)）]}”’"
_LAYER_MARKS = "👤📋🪞❓⚠️✍️🤖✅❌⏸📌🔎🛡️"

# 行内引用两制式。与 `paper-format` 支持的两种著录制式对齐。
CITE_PATTERNS: Tuple[re.Pattern, ...] = (
    # 著者-出版年制：括号内含 4 位年份（中英文括号皆可）
    re.compile(r"[（(][^（()）]{0,60}?(?:19|20)\d{2}[^（()）]{0,20}?[)）]"),
    # 顺序编码制：[1] / [1,2] / [1-3]
    re.compile(r"\[\d+(?:\s*[,\-–，]\s*\d+)*\]"),
)

# 指向 `literature/` 的 markdown 链接 = `paper-outline` / `paper-draft` 约定的
# 文献锚点格式（`[Smith 2023](literature/文献笔记表.md#smith2023)`）。允许 `./`
# `../` 前缀：产物落在 manuscript/ 还是项目根，相对深度不同。
# 只认 `literature/`——指向 manuscript/ 的链接是内部交叉引用，不是文献支撑。
ANCHOR_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(\s*(?:\.{1,2}/)*literature/[^)]*\)")

# 既有缺口标记的关键词：`paper-draft` 标「⚠️ 未经文献支撑」、`paper-outline` 标
# 「⚠️ 纯结构占位」。
#
# 为什么按**行**匹配而不是让 ⚠️ 紧邻关键词：两个生产者的格式不同——draft 写
# `⚠️ 未经文献支撑（锚点 X 未在 literature/）`（紧邻），outline 写
# `- ⚠️ <要点 bullet> · 纯结构占位（无文献支撑）`（中间隔着要点正文）。要求紧邻
# 会静默漏掉 outline 的全部标记。
WARNING_KEYWORDS: Tuple[str, ...] = ("未经文献支撑", "无文献支撑", "纯结构占位")
_WARNING_LINE_MAX = 120     # 整行过长则截断——产物要显示它，不能被一整段灌爆

# 标记文本本身（关键词 + 紧跟的括号补充），用于把它从正文里剔掉。见
# `strip_warning_marks()` 的 docstring——括号里的年份会被著者-出版年制正则命中。
_WARNING_TEXT_PATTERN = re.compile(
    "(?:" + "|".join(WARNING_KEYWORDS) + r")\s*(?:[（(][^）)]*[）)])?")


# ── markdown 预处理 ────────────────────────────────────────────────────────
def strip_markdown(text: str, *, drop_blockquote: bool = True) -> str:
    """剥离非正文噪声，返回纯正文。

    为什么必须剥：输入常是 `paper-draft` 的产物，里面有元信息表格、四层标注符号、
    `## 第 N 段` 标题。表格行的短片段会把句长均值拉低一大截，而句长是 `paper-style`
    最基础的特征——不剥等于所有数字都偏。

    `drop_blockquote=True`（默认，`paper-style` 口径）剥掉引用块（`> `），理由不是
    "格式噪声"而是"那是别人的话"：长引文算进用户风格基线会污染基线，让 `paper-draft`
    去对齐被引作者的文风。

    `drop_blockquote=False`（`paper-anchor` 口径）保留引用块正文、只去 `> ` 前缀——
    在找支撑缺口的语境里长引文恰恰是最明确的支撑证据，剥掉会让一段全是文本引证的
    人文段落被判成零引用。
    """
    out: List[str] = []
    lines = text.splitlines()
    i = 0
    # YAML front matter：仅当首行恰为 --- 时才算，避免把正文里的分割线当开头
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        i += 1
    in_fence = False
    in_comment = False
    while i < len(lines):
        raw = lines[i]
        i += 1
        s = raw.strip()
        if in_comment:
            if "-->" in s:
                in_comment = False
            continue
        if s.startswith("<!--"):
            if "-->" not in s:
                in_comment = True
            continue
        if s.startswith("```") or s.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not s:
            continue
        if s.startswith("|"):            # 表格行
            continue
        if s.startswith("#"):            # ATX 标题（章节切分已在此之前做完）
            continue
        # 脚注定义 `[^1]: 张三. 某文. 2020.` = 参考文献条目，不是正文。必须在
        # `_strip_inline` 之前判——它会剥掉 `[^1]` 标记，剥完就认不出是定义行了。
        # 对两个消费者都对：`paper-style` 算句长时它是噪声，`paper-anchor` 会把它
        # 当成一个零引用段而误报。
        if re.match(r"^\[\^[^\]]*\]:", s):
            continue
        if s.startswith(">"):            # 引用块 = 他人文字
            if drop_blockquote:
                continue
            s = re.sub(r"^>+\s*", "", s)   # 保留正文、只去引用前缀
            if not s:
                continue
        if re.fullmatch(r"([-*_=])\1{2,}", s):   # 水平分割线
            continue
        s = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", s)   # 列表标记
        out.append(_strip_inline(s))
    return "\n".join(x for x in out if x.strip())


def _strip_inline(s: str) -> str:
    """剥行内标记。顺序有讲究：图片必须先于链接（`![]()` 内含 `[]()`）。"""
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)          # 图片（alt 非正文）
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)      # 链接留文字
    s = re.sub(r"\[\^[^\]]*\]", "", s)                  # 脚注引用
    s = re.sub(r"`[^`]*`", "", s)                       # 行内代码非正文
    s = re.sub(r"<[^>]+>", "", s)                       # 裸 HTML 标签
    s = re.sub(r"(\*\*|__|~~|\*|_)", "", s)             # 强调标记
    for ch in _LAYER_MARKS:
        s = s.replace(ch, "")
    s = s.replace("️", "")                         # emoji 变体选择符
    return re.sub(r"[ \t]{2,}", " ", s).strip()


# ── 引号感知切句 ───────────────────────────────────────────────────────────
def split_sentences(text: str) -> List[str]:
    """引号感知切句。返回非空句子列表（保留原标点，引用位置计算需要）。

    `re.split(r"[。！？；]")` 这种一行实现会在三处出错，本函数逐一处理：
      · 引号内的句号被当句末——「他说：「这是对的。」然后走了。」应是 2 句；
      · 中文省略号 `……` 被切成两句；
      · 英文小数点（3.14）与缩写（et al.）被切开。

    英文单引号 `'` **不追踪**：`don't` / `researchers'` 会让配对失衡，追踪它
    的代价大于收益。后人勿"顺手补上"。
    """
    sents: List[str] = []
    buf: List[str] = []
    depth = 0
    dq_open = False          # 英文直双引号无开闭之分，只能 toggle
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        buf.append(ch)
        if ch == '"':
            dq_open = not dq_open
            i += 1
            continue
        if ch in _OPEN_PAIRS:
            depth += 1
            i += 1
            continue
        if ch in _CLOSE_PAIRS:
            depth = max(0, depth - 1)
            i += 1
            continue
        if ch == "\n":
            i += 1
            continue
        if depth > 0 or dq_open:
            i += 1
            continue
        if ch == "." and not _dot_is_sentence_end(text, i):
            i += 1
            continue
        if ch in _SENT_END or ch == ".":
            j = i + 1
            # 连续句末标点合并为一个边界：「？！」「……」「......」
            while j < n and (text[j] in _SENT_END or text[j] == "."):
                buf.append(text[j])
                j += 1
            # 句末标点后的收尾引号 / 括号归入本句
            while j < n and text[j] in _CLOSE_PAIRS:
                buf.append(text[j])
                depth = max(0, depth - 1)
                j += 1
            sents.append("".join(buf).strip())
            buf = []
            i = j
            continue
        i += 1
    tail = "".join(buf).strip()
    if tail:
        sents.append(tail)
    return [s for s in sents if s]


def _dot_is_sentence_end(text: str, i: int) -> bool:
    """判断位置 i 的英文句点是不是句末。连续点（省略号）在调用方合并，此处返回 True。"""
    nxt = text[i + 1] if i + 1 < len(text) else ""
    if nxt == ".":
        return True                                   # 省略号，算边界
    prev = text[i - 1] if i else ""
    if prev.isdigit() and nxt.isdigit():
        return False                                  # 小数点
    m = re.search(r"([A-Za-z]+)$", text[max(0, i - 12):i])
    if m and m.group(1).lower() in _ABBREV:
        return False                                  # 缩写
    return True


# ── 字数：统一口径 ─────────────────────────────────────────────────────────
def effective_chars(text: str) -> int:
    """有效字符数——剔除标点、空白、控制符。

    句长若含标点，「标点多的句子」会被算成「长句子」。归一化分母（每百字 /
    每千字）与句长必须同口径，否则两个数字不可互相印证。
    """
    return sum(
        1 for c in text
        if not unicodedata.category(c).startswith(("P", "Z", "C"))
    )


# ── 引用计数与位置 ─────────────────────────────────────────────────────────
def citation_positions(sentences: Sequence[str]) -> Dict[str, int]:
    """统计引用在句中的位置分布。

    markdown 链接 `[文字](url)` 与顺序编码 `[N]` 形似——`strip_markdown` 已把
    链接转成纯文字，故到这里的 `[N]` 只会是真引用。这个顺序依赖要记住。
    """
    pos = {"句首": 0, "句中": 0, "句末": 0}
    for s in sentences:
        body = s.rstrip("".join(_SENT_END) + "." + _CLOSE_PAIRS)
        span = max(1, len(body))
        for pat in CITE_PATTERNS:
            for m in pat.finditer(s):
                if len(body) - m.end() <= 2:
                    pos["句末"] += 1          # 两端都像时算句末（更常见）
                elif m.start() <= 8 or m.start() / span <= 0.15:
                    pos["句首"] += 1
                else:
                    pos["句中"] += 1
    return pos


def count_inline_citations(text: str) -> Dict[str, int]:
    """数行内两制式引用。返回 `{"著者-出版年制": n, "顺序编码制": n}`。

    **必须传已 `strip_markdown` 的文本**：`[1](url)` 这种以数字为链接文字的
    markdown 链接会被顺序编码制正则命中，不先剥就会虚高。
    """
    labels = ("著者-出版年制", "顺序编码制")
    return {lab: len(pat.findall(text))
            for lab, pat in zip(labels, CITE_PATTERNS)}


def count_anchor_links(text: str) -> int:
    """数指向 `literature/` 的 markdown 锚点链接。

    **必须传原始文本**（未 `strip_markdown`）：`_strip_inline` 会把链接转成纯
    文字，剥完再数一律为 0，且不报错。这是本模块最容易踩的顺序依赖。
    """
    return len(ANCHOR_LINK_PATTERN.findall(text))


def count_blockquote_lines(text: str) -> int:
    """数引用块行（`> ` 起始，fenced code block 内不算）。

    在 `paper-anchor` 语境里引用块是支撑形态之一（文本引证），故要计数而非剥掉。
    按**行**数而非按块数：一段引文占几行是排版问题，但行数至少与引文体量成正比，
    而"块"的边界（连续引用行算一块还是几块）没有可辩护的定义。
    """
    n = 0
    in_fence = False
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if s.startswith(">"):
            n += 1
    return n


def find_warning_marks(text: str) -> List[str]:
    """提取既有缺口标记所在行（`⚠️ 未经文献支撑` / `⚠️ 纯结构占位`）。

    判据是「同一行内既有 ⚠️ 又有关键词」：⚠️ 单独出现可能是别的警示（如
    `paper-figure` 的视觉可靠性提示），关键词单独出现可能是正文在讨论这件事
    （如本仓库的文档）；两者同行才是生产者留下的缺口标记。

    ⚠️ 的判断只认 U+26A0 本体、不要求变体选择符 U+FE0F——用户手打时两种都有。

    **必须传原始文本**：`_strip_inline` 会剥掉 `_LAYER_MARKS` 里的 ⚠️，剥完只剩
    关键词、同行判据不再成立。同 `count_anchor_links` 的顺序依赖。
    """
    out: List[str] = []
    for raw in text.splitlines():
        if "⚠" not in raw:
            continue
        if not any(k in raw for k in WARNING_KEYWORDS):
            continue
        line = raw.strip()
        if len(line) > _WARNING_LINE_MAX:
            line = line[:_WARNING_LINE_MAX] + "…"
        out.append(line)
    return out


def strip_warning_marks(text: str) -> str:
    """剔除缺口标记文本本身，**保留同行的正文**。

    为什么必须剔：`paper-draft` 的标记写成
    `⚠️ 未经文献支撑（锚点 Lee 2024 未在 literature/）`——括号里含 4 位年份，会被
    著者-出版年制正则命中，于是**明确标了缺支撑的那一段反而被算成有引用**、不进零引用
    清单。这是最讽刺的一种误判（真实语料上撞到过）。

    为什么只剔关键词与紧跟的括号、不剔整行：`paper-outline` 的格式是
    `- ⚠️ <要点正文> · 纯结构占位（无文献支撑）`，标记在行首、正文在中间，整行剔会把
    要点正文一起丢掉——那会让这一段变空、被过滤掉，缺口**漏报**，比误判更糟。

    调用时机：在 `strip_markdown()` **之前**、`find_warning_marks()` **之后**
    （后者要在原始文本上认标记）。
    """
    return _WARNING_TEXT_PATTERN.sub("", text)


# ── 切分：章节与段落 ───────────────────────────────────────────────────────
def split_sections(text: str) -> List[Tuple[str, str]]:
    """按 ATX 标题切章：取**第一个能切出 ≥2 节的最浅层级**。无标题则整篇一节。

    不写死 `##`：`paper-draft` 产物用 `## 第 N 段`，用户手写论文常用 `# 第一章`，
    写死任一个都会在另一种输入上切出荒谬的章节数。

    但也不能一律取最浅层级——论文最常见的形态恰恰是单文件、一个 `# 论文题目`
    带一串 `## 第 N 章`：取最浅就只有 1 节，章节间偏移直接失效（`paper-style`
    模式 a 的全部价值所在）。故逐层下探到第一个能切出 ≥2 节的层级。
    """
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        start = 1
        while start < len(lines) and lines[start].strip() != "---":
            start += 1
        start += 1
    heads: List[Tuple[int, int, str]] = []
    in_fence = False
    for idx in range(start, len(lines)):
        s = lines[idx].strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        mt = re.match(r"^(#{1,6})\s+(.+)$", s)
        if mt:
            heads.append((idx, len(mt.group(1)), mt.group(2).strip()))
    if not heads:
        return [("全文", "\n".join(lines[start:]))]
    levels = sorted({h[1] for h in heads})
    cuts = [h for h in heads if h[1] == levels[0]]
    for lvl in levels:
        same = [h for h in heads if h[1] == lvl]
        if len(same) >= 2:
            cuts = same
            break
    out: List[Tuple[str, str]] = []
    lead = "\n".join(lines[start:cuts[0][0]])
    if strip_markdown(lead).strip():
        out.append(("（篇首）", lead))
    for k, (idx, _lvl, title) in enumerate(cuts):
        end = cuts[k + 1][0] if k + 1 < len(cuts) else len(lines)
        out.append((title, "\n".join(lines[idx:end])))
    return out


def split_paragraphs(text: str) -> List[str]:
    """按空行切段，返回**未经 strip 的原始段落文本**。

    为什么返回原始文本：调用方要在原始文本上数锚点链接、提 ⚠️ 标记（见模块
    docstring 的顺序依赖）。段内 markdown 由调用方按需剥。

    为什么不能先 `strip_markdown` 再切：那个函数把空行全丢了（`if not s:
    continue`），切出来只会是一整段。

    fenced code block 内的空行**不分段**——否则一段代码会被切成若干「段落」，
    每段都零引用，把零引用段计数顶高。

    标题行、表格行也会成段（本函数只做机械的空行切分，不判断"什么是正文"）。
    调用方须自行过滤无正文的段——`paper-anchor` 的做法是 strip 后为空则跳过，
    同 `paper-style` 对空章节的处理。
    """
    lines = text.splitlines()
    i = 0
    if lines and lines[0].strip() == "---":       # YAML front matter
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        i += 1
    paras: List[str] = []
    buf: List[str] = []
    in_fence = False
    while i < len(lines):
        raw = lines[i]
        i += 1
        s = raw.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_fence = not in_fence
            buf.append(raw)
            continue
        if in_fence:
            buf.append(raw)
            continue
        if not s:
            if buf:
                paras.append("\n".join(buf))
                buf = []
            continue
        buf.append(raw)
    if buf:
        paras.append("\n".join(buf))
    return [p for p in paras if p.strip()]
