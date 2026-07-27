#!/usr/bin/env python3
"""paper-verify GB/T 7714-2015 著录格式检查（spec §10）——纯规则、不依赖 API。

聚焦学位论文盲审 / 查重最常扣分的 5 类（spec §10.1），启发式检查 + 问题点 + 国标
条款依据 + 规范化示例。格式是规则不是研究内容，给示例不算代笔（spec §10.2）。
检查是「提示性」的——issue 表示「建议核对」，不等于确定性错误；低频规则不强行判定。

5 类：文献类型标识 / 全角标点 / 电子文献访问日期 / 著者 3 名规则 / 期刊页码。
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import List, Optional

# 文献类型标识（与 parse_refs 一致）
_TYPE_TAG_RE = re.compile(r"\[([JMDCNRSPG]|EB/OL|J/OL)\]", re.IGNORECASE)
# 应改半角的常见全角标点（GB/T 7714 著录用半角）
_FULLWIDTH = "。，；：！？（）、"
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_PAGES_RE = re.compile(r"\d+\s*[-–—]\s*\d+")
_ACCESS_DATE_RE = re.compile(r"\[\d{4}-\d{2}-\d{2}\]")


@dataclass
class FormatIssue:
    """一条格式问题：问题点 + 国标条款 + 规范化示例。"""
    ref_id: str
    category: str        # type_tag | punctuation | eb_ol | authors | pages
    problem: str
    clause: str          # GB/T 7714-2015 条款
    suggestion: str      # 规范化示例

    def to_dict(self):
        return dataclasses.asdict(self)


def check_format(ref_id: str, raw_text: str,
                  parsed=None) -> List[FormatIssue]:
    """对一条引用文本做 5 类格式检查。parsed 为可选的 parse_refs.ParsedRef（提供 authors）。"""
    text = raw_text or ""
    issues: List[FormatIssue] = []
    upper = text.upper()

    # 1. 文献类型标识缺失（最高频扣分）
    if not _TYPE_TAG_RE.search(text):
        issues.append(FormatIssue(
            ref_id, "type_tag", "题名后缺文献类型标识（如 [J]/[M]/[D]/[C]）",
            "GB/T 7714-2015 §8.1",
            "在题名后补文献类型标识——期刊论文 [J]、专著 [M]、学位论文 [D]、会议论文 [C]"))

    # 2. 全角标点误用（应改半角）
    found = [c for c in _FULLWIDTH if c in text]
    if found:
        issues.append(FormatIssue(
            ref_id, "punctuation",
            f"含全角标点 {''.join(found)}，国标著录用半角",
            "GB/T 7714-2015 §7",
            f"将 {''.join(found)} 改为对应半角标点（. , ; : ! ? ( )）"))

    # 3. 电子文献 [EB/OL] 缺访问日期
    is_eb = "[EB/OL]" in upper or "[J/OL]" in upper
    if is_eb and not _ACCESS_DATE_RE.search(text):
        issues.append(FormatIssue(
            ref_id, "eb_ol", "电子文献 [EB/OL] 缺访问日期",
            "GB/T 7714-2015 §8.4",
            "在 [EB/OL] 后补访问日期，如 [2026-07-25]"))

    # 4. 著者 3 名规则（≥4 名应用「等」/「et al」）——启发式
    if parsed and getattr(parsed, "authors", None):
        author_str = parsed.authors[0]
        names = [n.strip() for n in re.split(r"[,，]", author_str) if n.strip()]
        if (len(names) >= 4
                and "等" not in author_str
                and "et al" not in author_str.lower()):
            issues.append(FormatIssue(
                ref_id, "authors",
                f"著者列了 {len(names)} 名但未用「等」/「et al」",
                "GB/T 7714-2015 §6（著者 ≤3 全列，≥4 列前 3 + 等）",
                "保留前 3 名作者，后加「, 等」（中文）或「, et al」（西文）"))

    # 5. 期刊 [J] 似缺页码（启发式）
    if "[J]" in upper and _YEAR_RE.search(text) and not _PAGES_RE.search(text):
        issues.append(FormatIssue(
            ref_id, "pages", "期刊文献 [J] 似缺页码",
            "GB/T 7714-2015 §8.2",
            "补全出版项：刊名, 年, 卷(期): 起止页码"))

    return issues


def check_all(items) -> List[FormatIssue]:
    """批量：items 为 (ref_id, raw_text, parsed_or_None) 三元组可迭代。"""
    out: List[FormatIssue] = []
    for ref_id, raw_text, parsed in items:
        out.extend(check_format(ref_id, raw_text, parsed))
    return out


if __name__ == "__main__":
    import json
    import sys

    import parse_refs  # noqa: E402  同目录

    text = sys.stdin.read()
    issues: List[FormatIssue] = []
    for r in parse_refs.parse_text(text):
        issues.extend(check_format(r.id, r.raw_text or "", parsed=r))
    json.dump([i.to_dict() for i in issues], sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
