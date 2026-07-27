#!/usr/bin/env python3
"""paper-style 风格特征内核——markdown 预处理 / 切句 / 五类特征 / 章节间偏移。

设计要点：风格特征一律**算出来**，不是感觉出来的。LLM 只解读本脚本输出的数字，
不得给「读起来像 / 不像 AI」这类无依据判断。两项近似值（术语密度、四字格）在
输出里带 `approximate: true` 与中文声明，**不得被当成精确值使用**——不引 jieba
是既定技术栈约束（`_shared/README.md`），近似就如实说近似。

纯标准库（零第三方运行时依赖，最低 Python 3.9）。
"""
from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# ── 词表（权威在此，references 不复制副本：两份必然漂移）────────────────────
# 选词依据：中文学术写作常见连接与限定成分，取自写作惯例；**不取自任何 AIGC
# 检测器的特征工程**——本命令不服务规避检测（见 references/误判申诉口径.md）。
_FUNCTION_WORDS: Tuple[str, ...] = (
    "值得注意的是", "需要指出的是", "综上所述", "由此可见", "换言之", "也就是说",
    "一方面", "另一方面", "除此之外", "与此同时", "在此基础上", "总的来说",
    "然而", "因此", "此外", "首先", "其次", "再者", "最后", "总之", "同时",
    "另外", "但是", "尽管", "虽然", "即使", "因为", "所以", "于是", "从而",
    "进而", "鉴于", "基于", "其中", "并且", "而且", "不仅", "以及", "且",
    "However", "Therefore", "Moreover", "Furthermore", "In addition",
    "Nevertheless", "Consequently", "Accordingly", "Specifically",
    "In particular", "On the other hand", "In conclusion", "Thus", "Hence",
)

# 常见学术四字格。**固定词表、非全量识别**——无分词做不到全量，故此项为近似值。
_QUAD_PHRASES: Tuple[str, ...] = (
    "至关重要", "不可忽视", "值得关注", "日益增长", "广泛应用", "深入研究",
    "显著提升", "显著提高", "有效促进", "充分发挥", "全面分析", "系统梳理",
    "详细阐述", "深刻影响", "重要意义", "关键作用", "核心要素", "内在逻辑",
    "客观规律", "长期以来", "与日俱增", "错综复杂", "行之有效", "势在必行",
)

_PERSON_WORDS: Tuple[str, ...] = (
    "本研究", "本课题", "本文", "笔者", "我们", "该研究", "作者认为", "本人",
)
# 先屏蔽再计数：不屏蔽「本文献」会让「本文」多计一次（长词优先的边界情形）。
_PERSON_MASK: Tuple[str, ...] = ("本文献", "本文件", "本文档")

# 术语密度近似路径的通用词黑名单——这些词高频但不是术语，不屏蔽会把密度顶高。
_COMMON_NOISE: Tuple[str, ...] = (
    "研究", "方法", "问题", "分析", "结果", "数据", "影响", "作用", "发展",
    "提高", "进行", "通过", "以及", "可以", "能够", "这些", "其中", "不同",
    "相关", "重要", "情况", "内容", "方面", "过程", "基础", "工作", "存在",
)

# 近似术语候选的首 / 尾字剪除表：不剪的话「神经网络的」会因为出现 3 次、且比
# 「神经网络」更长而胜出（长串优先），把结构助词粘进术语。两表分开是必要的——
# 「中」作尾字（研究中）是噪声、作首字（中位数）是术语；「一」两侧都不剪，
# 否则「一致性」这类真术语会被误杀。
_TRIM_HEAD = set("的了着地得和与及或把被对从向为以在是也就都而其此该那之等个们")
_TRIM_TAIL = set("的了着地得和与及或把被对从向为以在是也就都而其此该这那之等中上下时后前里")

_SENT_END = "。！？；…!?;"
_ABBREV = frozenset(
    ("al", "e", "g", "i", "cf", "fig", "eq", "vs", "dr", "no", "etc", "ca",
     "approx", "ed", "eds", "vol", "pp", "st", "mr", "ms", "prof")
)
_OPEN_PAIRS = "「『（《〈【〔(（[{“‘"
_CLOSE_PAIRS = "」』）》〉】〕)）]}”’"
_LAYER_MARKS = "👤📋🪞❓⚠️✍️🤖✅❌⏸📌🔎🛡️"

_MIN_SENTENCES_FOR_STD = 5  # 少于这么多句，标准差不具解释力 → reliable=False


# ── Task 1：markdown 预处理 ────────────────────────────────────────────────
def strip_markdown(text: str) -> str:
    """剥离非正文噪声，返回纯正文。

    为什么必须剥：本命令的输入常是 `paper-draft` 的产物，里面有元信息表格、
    四层标注符号、`## 第 N 段` 标题。表格行的短片段会把句长均值拉低一大截，
    而句长是本命令最基础的特征——不剥等于所有数字都偏。

    **引用块（`> `）也剥掉**，理由不是"格式噪声"而是"那是别人的话"：长引文
    算进用户风格基线会污染基线，让 `paper-draft` 去对齐被引作者的文风。
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
        if s.startswith(">"):            # 引用块 = 他人文字
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


# ── Task 1：引号感知切句 ───────────────────────────────────────────────────
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


# ── Task 2：五类特征 ───────────────────────────────────────────────────────
def count_words(text: str, words: Sequence[str],
                mask: Sequence[str] = ()) -> Dict[str, int]:
    """长词优先计数：先数长词并把命中区间置为占位，再数短词。

    不这么做，「值得注意的是」会同时被自己和「注意」各计一次，虚词密度虚高。
    `mask` 里的词只屏蔽、不计入结果（如「本文献」屏蔽掉，防「本文」误命中）。
    """
    work = text
    for m in sorted(mask, key=len, reverse=True):
        work = work.replace(m, "\x00" * len(m))
    counts: Dict[str, int] = {}
    for w in sorted(words, key=len, reverse=True):
        c = work.count(w)
        if c:
            counts[w] = c
            work = work.replace(w, "\x00" * len(w))
    return counts


_CITE_PATTERNS = (
    # 著者-出版年制：括号内含 4 位年份（中英文括号皆可）
    re.compile(r"[（(][^（()）]{0,60}?(?:19|20)\d{2}[^（()）]{0,20}?[)）]"),
    # 顺序编码制：[1] / [1,2] / [1-3]
    re.compile(r"\[\d+(?:\s*[,\-–，]\s*\d+)*\]"),
)


def citation_positions(sentences: Sequence[str]) -> Dict[str, int]:
    """统计引用在句中的位置分布。

    markdown 链接 `[文字](url)` 与顺序编码 `[N]` 形似——`strip_markdown` 已把
    链接转成纯文字，故到这里的 `[N]` 只会是真引用。这个顺序依赖要记住。
    """
    pos = {"句首": 0, "句中": 0, "句末": 0}
    for s in sentences:
        body = s.rstrip("".join(_SENT_END) + "." + _CLOSE_PAIRS)
        span = max(1, len(body))
        for pat in _CITE_PATTERNS:
            for m in pat.finditer(s):
                if len(body) - m.end() <= 2:
                    pos["句末"] += 1          # 两端都像时算句末（更常见）
                elif m.start() <= 8 or m.start() / span <= 0.15:
                    pos["句首"] += 1
                else:
                    pos["句中"] += 1
    return pos


def approximate_terms(text: str, terms: Optional[Sequence[str]] = None
                      ) -> Tuple[Dict[str, int], str]:
    """术语计数。返回 (计数字典, 来源说明)。

    用户给术语表 → 精确计数。没给 → 退到「文中重复出现 ≥3 次的 2–6 字汉字串」
    近似，**这是不引 jieba 的直接后果，必须如实标注为近似值**（CLAUDE.md 唯一
    保留的代码层约束：降级必须明确标注，不静默）。近似路径会把「研究」这类
    常用词误当术语，故先过 `_COMMON_NOISE` 黑名单减噪，但**减不干净**。
    """
    if terms:
        return count_words(text, terms), "用户术语表"
    freq: Dict[str, int] = {}
    for run in re.findall(r"[一-鿿]{2,}", text):
        for length in range(2, 7):
            for k in range(len(run) - length + 1):
                sub = run[k:k + length]
                freq[sub] = freq.get(sub, 0) + 1
    blocked = set(_COMMON_NOISE) | set(_FUNCTION_WORDS) | set(_PERSON_WORDS)
    cands = [
        (w, c) for w, c in freq.items()
        if c >= 3 and w not in blocked
        and w[0] not in _TRIM_HEAD and w[-1] not in _TRIM_TAIL
        and not any(b in w for b in _PERSON_WORDS)
    ]
    # 长串优先：短串若只是某个已选长串的一部分（计数也不更高），是同一个术语的碎片
    cands.sort(key=lambda kv: (-len(kv[0]), -kv[1]))
    picked: Dict[str, int] = {}
    for w, c in cands:
        if any(w in p and c <= pc for p, pc in picked.items()):
            continue
        picked[w] = c
        if len(picked) >= 20:
            break
    return picked, "重复串近似"


@dataclass
class SectionMetrics:
    """一个章节的风格特征向量。`reliable=False` 时标准差不具解释力。"""
    name: str
    char_count: int = 0
    sentence_count: int = 0
    len_mean: float = 0.0
    len_median: float = 0.0
    len_std: float = 0.0
    function_word_per_100: float = 0.0
    function_word_top: List[Tuple[str, int]] = field(default_factory=list)
    citation_pos: Dict[str, int] = field(default_factory=dict)
    citation_end_ratio: float = 0.0
    person_counts: Dict[str, int] = field(default_factory=dict)
    person_per_1000: float = 0.0
    quad_per_1000: float = 0.0
    quad_top: List[Tuple[str, int]] = field(default_factory=list)
    term_density_per_100: float = 0.0
    term_top: List[Tuple[str, int]] = field(default_factory=list)
    term_source: str = ""
    reliable: bool = False

    def to_dict(self) -> Dict:
        d = dict(self.__dict__)
        d["function_word_top"] = [list(x) for x in self.function_word_top]
        d["quad_top"] = [list(x) for x in self.quad_top]
        d["term_top"] = [list(x) for x in self.term_top]
        d["approximate"] = {"term_density_per_100": True, "quad_per_1000": True}
        return d


def measure_section(name: str, text: str,
                    terms: Optional[Sequence[str]] = None) -> SectionMetrics:
    """算一个章节的全部特征。`text` 须是已 `strip_markdown` 的纯正文。"""
    m = SectionMetrics(name=name)
    sents = split_sentences(text)
    m.sentence_count = len(sents)
    m.char_count = effective_chars(text)
    if not sents:
        return m
    lens = [effective_chars(s) for s in sents]
    lens = [x for x in lens if x] or [0]
    m.len_mean = round(statistics.fmean(lens), 2)
    m.len_median = round(statistics.median(lens), 2)
    # 总体标准差：样本标准差在 5–10 句时虚高，而这里要的是"这一章内部的离散度"
    m.len_std = round(statistics.pstdev(lens), 2) if len(lens) > 1 else 0.0
    m.reliable = m.sentence_count >= _MIN_SENTENCES_FOR_STD

    fw = count_words(text, _FUNCTION_WORDS)
    fw_total = sum(fw.values())
    m.function_word_per_100 = _per(fw_total, m.char_count, 100)
    m.function_word_top = sorted(fw.items(), key=lambda kv: -kv[1])[:5]

    m.citation_pos = citation_positions(sents)
    cite_total = sum(m.citation_pos.values())
    m.citation_end_ratio = (
        round(m.citation_pos["句末"] / cite_total, 4) if cite_total else 0.0
    )

    pc = count_words(text, _PERSON_WORDS, mask=_PERSON_MASK)
    m.person_counts = pc
    m.person_per_1000 = _per(sum(pc.values()), m.char_count, 1000)

    qc = count_words(text, _QUAD_PHRASES)
    m.quad_per_1000 = _per(sum(qc.values()), m.char_count, 1000)
    m.quad_top = sorted(qc.items(), key=lambda kv: -kv[1])[:5]

    tc, src = approximate_terms(text, terms)
    m.term_source = src
    m.term_density_per_100 = _per(sum(tc.values()), m.char_count, 100)
    m.term_top = sorted(tc.items(), key=lambda kv: -kv[1])[:8]
    return m


def _per(count: int, chars: int, base: int) -> float:
    return round(count / chars * base, 2) if chars else 0.0


# ── Task 3：章节切分与偏移 ─────────────────────────────────────────────────
def split_sections(text: str) -> List[Tuple[str, str]]:
    """按 ATX 标题切章：取**第一个能切出 ≥2 节的最浅层级**。无标题则整篇一节。

    不写死 `##`：`paper-draft` 产物用 `## 第 N 段`，用户手写论文常用 `# 第一章`，
    写死任一个都会在另一种输入上切出荒谬的章节数。

    但也不能一律取最浅层级——论文最常见的形态恰恰是单文件、一个 `# 论文题目`
    带一串 `## 第 N 章`：取最浅就只有 1 节，章节间偏移直接失效（本命令模式 a
    的全部价值所在）。故逐层下探到第一个能切出 ≥2 节的层级。
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


_COMPARE_FEATURES = (
    ("len_mean", "句长均值"),
    ("len_median", "句长中位数"),
    ("len_std", "句长标准差"),
    ("function_word_per_100", "虚词密度（每百字）"),
    ("citation_end_ratio", "引用置句末占比"),
    ("person_per_1000", "人称密度（每千字）"),
    ("quad_per_1000", "四字格密度（每千字·近似）"),
    ("term_density_per_100", "术语密度（每百字·近似）"),
)


def compare_sections(ms: Sequence[SectionMetrics]) -> Dict:
    """算章节间偏移：每个特征的 min / max / 极差 / 标准差 / 变异系数（CV）。

    为什么要 CV：句长（几十字）与虚词密度（每百字几次）量纲不同，直接比极差
    会把「句长差 8 字」说成比「虚词密度差 3 次」更重要。CV = 标准差 / 均值，
    无量纲，是「哪个特征在章节间抖得最厉害」的唯一可辩护排序依据。

    **脚本只排序、不下结论**——「所以第 3 章要改」是用户的研究判断，不是本
    脚本的输出（三条不变①）。
    """
    if len(ms) < 2:
        return {"available": False,
                "note": "只有一个章节，无章节间偏移可算——需 ≥2 个章节"}
    per: Dict[str, Dict] = {}
    for key, label in _COMPARE_FEATURES:
        vals = [getattr(m, key) for m in ms]
        mean = statistics.fmean(vals)
        std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        lo, hi = min(vals), max(vals)
        per[key] = {
            "label": label,
            "min": round(lo, 4), "max": round(hi, 4),
            "range": round(hi - lo, 4),
            "mean": round(mean, 4), "std": round(std, 4),
            "cv": round(std / mean, 4) if mean else 0.0,
            "min_section": ms[vals.index(lo)].name,
            "max_section": ms[vals.index(hi)].name,
        }
    ranked = sorted(per.items(), key=lambda kv: -kv[1]["cv"])
    return {
        "available": True,
        "per_feature": per,
        "ranked_by_cv": [{"key": k, **v} for k, v in ranked],
    }


APPROXIMATE_NOTES = {
    "term_density_per_100":
        "术语密度为近似值：技术栈约定零第三方依赖（不引 jieba 分词），"
        "无用户术语表时退到「文中重复出现 ≥3 次的 2–6 字汉字串」估算，"
        "会把部分常用词误当术语。产物引用此项须标注「近似」。",
    "quad_per_1000":
        "四字格密度为近似值：基于固定词表命中计数，非全量四字格识别。"
        "产物引用此项须标注「近似」。",
}


# ── CLI ────────────────────────────────────────────────────────────────────
def _render_text(payload: Dict) -> str:
    """人类可读输出。宿主 agent 转录数字时用 --json 更稳，这里供人工核对。"""
    out = [f"模式：{payload['mode']}",
           f"输入：{'、'.join(payload['inputs'])}",
           f"合计：{payload['total']['char_count']} 有效字符 / "
           f"{payload['total']['sentence_count']} 句", ""]
    for s in payload["sections"]:
        flag = "" if s["reliable"] else "  ⚠️ 句子数 < 5，标准差不具解释力"
        out.append(f"【{s['name']}】{s['char_count']} 字 / "
                   f"{s['sentence_count']} 句{flag}")
        out.append(f"  句长 均值 {s['len_mean']} / 中位 {s['len_median']} / "
                   f"标准差 {s['len_std']}")
        out.append(f"  虚词 每百字 {s['function_word_per_100']}"
                   f"（前 5：{s['function_word_top']}）")
        out.append(f"  引用位置 {s['citation_pos']}")
        out.append(f"  人称 每千字 {s['person_per_1000']}（{s['person_counts']}）")
        out.append(f"  四字格 每千字 {s['quad_per_1000']}（近似）")
        out.append(f"  术语 每百字 {s['term_density_per_100']}"
                   f"（近似·来源：{s['term_source']}）")
    cmp_ = payload["comparison"]
    if cmp_.get("available"):
        out.append("\n章节间偏移（按变异系数 CV 降序，只排序不下结论）：")
        for r in cmp_["ranked_by_cv"]:
            out.append(f"  · {r['label']}：CV {r['cv']}，"
                       f"{r['min_section']} {r['min']} → {r['max_section']} {r['max']}")
    else:
        out.append("\n" + cmp_["note"])
    out.append("\n近似值声明：")
    for v in payload["approximate_notes"].values():
        out.append(f"  · {v}")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI。退出码：0 算出结果 / 2 样本不足（切不出句子）/ 3 读不到输入。

    只有三个码是有意的：本命令没有 `paper-screen` 那样的守恒等式，不存在
    「算得出但不可信」的中间态，样本不足是唯一必须拒绝出数的情形。不凑第四个。
    """
    import argparse
    import json
    import pathlib

    ap = argparse.ArgumentParser(description="风格特征计算与章节间偏移")
    ap.add_argument("--input", action="append", default=[],
                    help="正文 markdown 路径（可重复）")
    ap.add_argument("--dir", help="目录，扫其中 *.md（按文件名排序）")
    ap.add_argument("--terms", help="术语表文件，一行一术语（给了则术语密度为精确值）")
    ap.add_argument("--json", dest="json_out", help="JSON 输出路径（省略则打印文本）")
    ap.add_argument("--baseline", action="store_true",
                    help="模式 b：合并全部输入算一份全局基线，不做章节比对")
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

    raw: List[Tuple[str, str]] = []
    for p in paths:
        try:
            raw.append((p.name, p.read_text(encoding="utf-8")))
        except OSError as e:
            # 读不到是环境 / 输入问题，与「样本不足」区分：后者路径没错、只是字太少
            print(f"读不到输入文件：{p}")
            print(f"  原因：{e.strerror or e}")
            return 3

    terms: Optional[List[str]] = None
    if args.terms:
        try:
            terms = [ln.strip() for ln in
                     pathlib.Path(args.terms).read_text(encoding="utf-8").splitlines()
                     if ln.strip()]
        except OSError as e:
            print(f"读不到术语表：{args.terms}")
            print(f"  原因：{e.strerror or e}")
            return 3

    multi = len(raw) > 1
    sections: List[SectionMetrics] = []
    if args.baseline:
        merged = "\n\n".join(strip_markdown(t) for _n, t in raw)
        sections.append(measure_section("全局基线", merged, terms))
    else:
        for fname, text in raw:
            for name, body in split_sections(text):
                clean = strip_markdown(body)
                if not clean.strip():
                    continue
                label = f"{fname} · {name}" if multi else name
                sections.append(measure_section(label, clean, terms))

    total_sents = sum(s.sentence_count for s in sections)
    if total_sents == 0:
        print("样本不足：剥离表格 / 代码 / 引用块后切不出任何句子，不产特征。")
        print(f"  输入：{'、'.join(p.name for p in paths)}")
        print("这不是错误——是可分析的正文太少。请补正文，或换一个包含正文的范围。")
        return 2

    payload = {
        "mode": "baseline" if args.baseline else "compare",
        "inputs": [p.name for p in paths],
        "total": {
            "char_count": sum(s.char_count for s in sections),
            "sentence_count": total_sents,
            "section_count": len(sections),
        },
        "approximate_notes": APPROXIMATE_NOTES,
        "sections": [s.to_dict() for s in sections],
        "comparison": ({"available": False, "note": "模式 b 只算全局基线，不做章节比对"}
                       if args.baseline else compare_sections(sections)),
    }
    if args.json_out:
        pathlib.Path(args.json_out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(_render_text(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
