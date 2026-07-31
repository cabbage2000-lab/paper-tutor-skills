#!/usr/bin/env python3
"""题录字段比对内核——`paper-verify` 与 `paper-search` 的共享内核。

**为什么在共享层**：两个 skill 都要回答「手里这条题录与源返回的元数据是不是同一篇」。

| 消费者 | 场景 | 拿比对结果做什么 |
| --- | --- | --- |
| `paper-verify` | 解析出的引用 × 各源命中 | 升 `METADATA_MISMATCH` 态（六态判定第 5 条） |
| `paper-search` | 中文导出条目回填 × `--lookup-doi` 命中 | 只如实转述给用户，**不判态**（存在性判定归 verify） |

各存一份必然漂移，而漂移的表现是同一条题录在两个命令下一个说「元数据不符」、另一个说没问题，
谁对谁错无从判断（硬规则 1 反对第二份真相）。

**阈值的出处**是 paper-verify 的判定 spec §4.3，搬到共享层不改数值：标题重叠 < 0.8、
年份差 ≥ 2 升 mismatch；venue 仅记 hint 不升态。改这里的任何阈值都会同时改变 verify 的
六态判定，先读 `tests/paper-verify/test_judge.py` 再动。

**duck typing 契约**：`compare_fields` / `pick_best_hit` 的 `parsed` 接受任何具备
`doi` / `title` / `authors` / `year` 属性的对象——`paper-verify` 传 `ParsedRef`、
`paper-search` 传 `_shared.Ref` 或等价对象。`venue` 走 `getattr(..., None)` 取，
因为 `_shared.Ref` 没有这个字段而 `ParsedRef` 有；缺 venue 只是少比一项 hint，
不影响任何升态判断。

纯标准库（零第三方运行时依赖，最低 Python 3.9）。
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from .datasources.models import normalize_doi

__all__ = ["FieldNote", "compare_fields", "pick_best_hit", "title_overlap",
           "surname_candidates", "normalize_str"]

# 标题比对的英文停用词（中文引用在 verify 侧走 PENDING_MANUAL 不比标题，此处服务英文）
_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "for", "and", "or", "to", "with",
    "from", "by", "at", "as", "is", "are", "via", "using", "into",
}


@dataclass
class FieldNote:
    """单字段比对结果。severity=mismatch 在 verify 侧升 MISMATCH 态；hint 仅记录不升态。

    search 侧两种 severity 都只如实转述、都不升态——它没有态可升。
    """
    field: str
    ref_value: Any
    source_value: Any
    severity: str          # mismatch | hint
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


def normalize_str(s: str) -> str:
    """归一化字符串：去所有非字母数字、小写（用于姓 / venue 比对）。"""
    return re.sub(r"[\W_]+", "", (s or ""), flags=re.UNICODE).lower()


def is_initials(tok: str) -> bool:
    """纯首字母缩写 token：'A' / 'A.' / 'A.J.' / 'AJ'——去点后全大写且 ≤3 字符。

    不能用长度阈值替代大写判断：中文罗马化姓多为 2 字符（Li / Wu / Xu），
    按长度切会把姓当成缩写丢掉。
    """
    t = tok.replace(".", "").strip()
    return bool(t) and t.isupper() and len(t) <= 3


def surname_candidates(raw: str) -> set:
    """第一作者的姓氏候选集合（归一化）。

    各源作者名格式不统一且无法归一：Crossref / OpenAlex / Semantic Scholar / arXiv
    给 given-first（'Yann LeCun'），PubMed / ERIC 给 family-first（'Wakefield AJ'）。
    无逗号时哪个 token 是姓无从判断，故返回候选集合、比对用相交而非相等——宁可少量
    漏报，也绝不让一条正确引用误报元数据不符（spec §4.3 以低误报为先）。
    """
    s = (raw or "").strip()
    if not s:
        return set()
    if re.search(r"[,，]", s):        # 有逗号 → 逗号前即姓（'Smith, John' / '王明, 李华'）
        s = re.split(r"[,，]", s)[0]
    else:                             # 无逗号 → 去掉缩写 token（缩写必是名），余下皆为候选
        full = [t for t in s.split() if not is_initials(t)]
        s = " ".join(full) if full else s
    return {n for n in (normalize_str(t) for t in s.split()) if n}


def title_tokens(title: str) -> set:
    t = re.sub(r"[^\w\s]", " ", (title or "").lower())
    return {w for w in t.split() if w and w not in _STOPWORDS}


def title_overlap(a: str, b: str) -> float:
    """重叠系数 = |交集| / min(|A|, |B|)——引用标题常是源标题子集（省略副标题），
    重叠系数比 Jaccard 更宽容合法省略（spec §4.3）。"""
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def compare_fields(parsed, hit) -> List[FieldNote]:
    """对照一条题录与一个 SourceHit 的元数据，返回逐字段比对（spec §4.3）。

    只在「题录与源都有该字段」时比对——避免题录没填 venue 却报不符。venue/type
    不符仅记 hint、不升态（源间口径差异大，升态会拉高误报）。

    `parsed` 见模块 docstring 的 duck typing 契约；`venue` 缺失即跳过该项。
    """
    notes: List[FieldNote] = []
    meta = hit.metadata or {}
    # DOI：归一化精确相等
    if parsed.doi and meta.get("doi"):
        if normalize_doi(parsed.doi) != normalize_doi(meta["doi"]):
            notes.append(FieldNote("doi", parsed.doi, meta["doi"], "mismatch", "DOI 不一致"))
    # 年份：差 ≥ 2 升态
    if parsed.year and meta.get("year"):
        diff = abs(int(parsed.year) - int(meta["year"]))
        if diff >= 2:
            notes.append(FieldNote("year", parsed.year, meta["year"], "mismatch", f"年份差 {diff}"))
    # 标题：重叠 < 0.8 升态
    if parsed.title and meta.get("title"):
        ov = title_overlap(parsed.title, meta["title"])
        if ov < 0.8:
            notes.append(FieldNote("title", parsed.title, meta["title"], "mismatch",
                                   f"标题重叠 {ov:.2f}（阈值 0.8）"))
    # 第一作者姓：候选集合无交集才升态（各源 given/family 顺序不一，见 surname_candidates）
    if parsed.authors and meta.get("authors"):
        ref_c = surname_candidates(parsed.authors[0])
        src_c = surname_candidates(str(meta["authors"][0]))
        if ref_c and src_c and not (ref_c & src_c):
            notes.append(FieldNote("first_author", parsed.authors[0], meta["authors"][0],
                                   "mismatch", "第一作者姓不一致"))
    # venue：仅提示（包含关系即视为一致，容忍缩写）。Ref 没有这个字段，缺了就跳过。
    parsed_venue = getattr(parsed, "venue", None)
    if parsed_venue and meta.get("venue"):
        a, b = normalize_str(parsed_venue), normalize_str(str(meta["venue"]))
        if a and b and a not in b and b not in a:
            notes.append(FieldNote("venue", parsed_venue, meta["venue"], "hint", "期刊名写法不一（仅提示）"))
    return notes


def pick_best_hit(parsed, hits) -> Any:
    """多 hit 时选最匹配的：DOI 相等优先；否则标题重叠最高；否则第一个。"""
    if parsed.doi:
        nd = normalize_doi(parsed.doi)
        for h in hits:
            hd = h.metadata.get("doi")
            if hd and normalize_doi(hd) == nd:
                return h
    if parsed.title:
        return max(hits, key=lambda h: title_overlap(parsed.title, h.metadata.get("title") or ""))
    return hits[0]
