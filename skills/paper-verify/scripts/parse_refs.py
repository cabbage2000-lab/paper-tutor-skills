#!/usr/bin/env python3
"""paper-verify 引用解析：参考文献文本 / .bib / 单条 DOI|标题 → ParsedRef[]。

Phase 1 覆盖三种格式（paper-verify spec §5）：GB/T 7714 顺序编码制、APA、.bib。
解析不求完美——DOI 提取最优先（有 DOI 核验最准），年份 / 标题次之，作者最难故容错。
解析不出的条目标 parse_status="unparsed"，verify 据此附出口建议、不硬猜（spec §5.3）。

ParsedRef 比 _shared.Ref 多 venue / type / parse_status：venue/type 供元数据比对的
「仅提示」字段（spec §4.3），parse_status 供 verify 标出口；送 fetch_batch 时用 to_ref_dict()
降级回 _shared.Ref 的字段集（丢 venue/type，取证层不需要）。

纯文本解析、无网络、无第三方依赖，可确定性单测。
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# DOI 正则（Crossref 推荐格式简化）：10. + 4 位以上注册机构码 + / + 非空白（不含分隔符）。
# 右括号**不排除**：合法 DOI 可含成对括号（Lancet 'S0140-6736(97)11096-0'、
# Wiley '10.1002/(SICI)…'），排除会把这类 DOI 截断、让真实文献落 NOT_FOUND
# 「疑似不存在」。尾随的不成对括号交给 _trim_doi 回退。
# 已知限制：分号仍排除（常用于分隔多条引用），故 Wiley SICI 式 DOI 里的 ';2-H' 尾巴会丢。
_DOI_RE = re.compile(r"10\.\d{4,}/[^\s,;\]]+", re.IGNORECASE)
# 四位年份（18xx-2099），前后不贴数字避免误匹配页码 / 卷期
_YEAR_RE = re.compile(r"(?<!\d)(1[89]\d{2}|20\d{2})(?!\d)")
_BIB_ENTRY_RE = re.compile(r"@\w+\s*\{", re.IGNORECASE)
# APA 风格作者段的收尾锚点：'(1998).' / '（2020a）'。比句号切分可靠——APA 常把
# 首字母缩写写成 'A. J.'（点后带空格），按句号切会切在人名中间，标题错取成
# 'J., Murch, S'，进而让一条正确引用误报元数据不符。有此锚点时优先用它。
_APA_YEAR_SPLIT_RE = re.compile(r"[（(]\s*(?:1[89]\d{2}|20\d{2})[a-z]?\s*[）)]\s*\.?\s*")
# .bib 字段：key = {value} 或 key = "value"——{...} 包裹允许值内含逗号（朴素但覆盖常见 .bib）
_BIB_FIELD_RE = re.compile(r"(\w+)\s*=\s*(?:\{(.*?)\}|\"(.*?)\")", re.DOTALL)
_GBT_NUM_RE = re.compile(r"^\s*\[(\d+)\]\s*")           # 顺序编码标号 [1]
_GBT_TYPE_RE = re.compile(r"\[([JMDCNRSPG]|EB/OL|J/OL)\]", re.IGNORECASE)  # 文献类型标识


@dataclass
class ParsedRef:
    """verify 层解析结构——比 _shared.Ref 多 venue / type / parse_status。"""

    id: str
    doi: Optional[str] = None
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    year: Optional[int] = None
    venue: Optional[str] = None
    type: Optional[str] = None       # GB/T 7714 标识 [J]/[M]... 或解析得的类型标记
    raw_text: Optional[str] = None
    parse_status: str = "ok"         # ok | unparsed

    def to_ref_dict(self) -> Dict[str, Any]:
        """转 _shared.Ref 字段集（送 fetch_batch，丢 venue/type/parse_status）。"""
        return {"id": self.id, "doi": self.doi, "title": self.title,
                "authors": list(self.authors), "year": self.year,
                "raw_text": self.raw_text}

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


def _trim_doi(s: str) -> str:
    """剪掉 DOI 尾部的句读与**不成对**的右括号，保留成对括号（见 _DOI_RE 注释）。

    'S0140-6736(97)11096-0.' → 'S0140-6736(97)11096-0'（括号成对，保留）
    '10.1234/abc)'           → '10.1234/abc'（markdown 链接的收尾括号，剪掉）
    """
    s = s.rstrip(".,;:")
    while s and s[-1] == ")" and s.count("(") < s.count(")"):
        s = s[:-1].rstrip(".,;:")
    return s


def _extract_doi(text: str) -> Optional[str]:
    m = _DOI_RE.search(text or "")
    return _trim_doi(m.group(0)) if m else None


def _extract_year(text: str) -> Optional[int]:
    m = _YEAR_RE.search(text or "")
    return int(m.group(1)) if m else None


def _find_dot(s: str) -> int:
    """第一个后接空格/换行/行尾的半角句号位置（避开年份小数 / 缩写里的点）。"""
    for i, ch in enumerate(s):
        if ch == "." and (i + 1 >= len(s) or s[i + 1] in " \n"):
            return i
    return -1


def _valid_title(t: str) -> bool:
    """标题有效性：长度 ≥ 3 且含至少一个字母字符（过滤纯标点 / 纯数字垃圾）。"""
    return bool(t) and len(t) >= 3 and any(c.isalpha() for c in t)


def _take_title(rest: str) -> str:
    """从「作者后」片段取标题候选：到类型标识或下一个句号前。"""
    if not rest:
        return ""
    m = _GBT_TYPE_RE.search(rest)
    if m:
        return rest[:m.start()].strip(" .,，")
    d = _find_dot(rest)
    if d > 0:
        return rest[:d].strip(" .,，")
    return rest.strip(" .,，")


def parse_single(token: str) -> ParsedRef:
    """单条输入：整串是 DOI 则填 doi；.bib 单条则按 bib 解析；否则按自由行解析。"""
    token = (token or "").strip()
    if not token:
        return ParsedRef(id="r1", raw_text=token, parse_status="unparsed")
    doi = _extract_doi(token)
    if doi and token.strip(".,;) ").lower() == doi.lower():
        return ParsedRef(id="r1", doi=doi, raw_text=token)
    if _BIB_ENTRY_RE.match(token):
        refs = parse_bib(token)
        if refs:
            return refs[0]
        return ParsedRef(id="r1", raw_text=token, parse_status="unparsed")
    return _parse_freeform_line(token, "r1")


def _parse_freeform_line(line: str, idx: str) -> ParsedRef:
    """启发式解析一行自由文本（GB/T 7714 / APA 混杂）。

    有 APA 的 '(年份).' 锚点时按它切分作者段与标题段；否则退回句号切分（GB/T 风格，
    作者取第一个句号前的片段——两种格式作者都在开头）。标题取作者后、去年份括号、到
    类型标识或下一个句号前。作者提取最不可靠，仅尽力——judge 比对第一作者姓时再归一化。
    """
    doi = _extract_doi(line)
    year = _extract_year(line)
    mtype = _GBT_TYPE_RE.search(line)
    type_code = mtype.group(0) if mtype else None
    body = _GBT_NUM_RE.sub("", line.strip()).strip()
    body = _DOI_RE.sub("", body).strip()            # 去 DOI 串避免干扰句号定位
    authors: List[str] = []
    m_apa = _APA_YEAR_SPLIT_RE.search(body)
    if m_apa and m_apa.start() > 0:
        # APA：作者段以 '(年份).' 收尾，不会切在 'A. J.' 中间（见 _APA_YEAR_SPLIT_RE）。
        # 多作者段可以很长，故此路径不套用句号路径的 80 字上限。
        head = body[:m_apa.start()].strip(" ,，.")
        if head and not head[0].isdigit() and len(head) < 300:
            authors = [head]
        rest = body[m_apa.end():].strip()
    else:
        first_dot = _find_dot(body)
        if first_dot > 0:
            head = body[:first_dot].strip(" ,，")
            if head and not head[0].isdigit() and len(head) < 80:
                authors = [head]
            rest = body[first_dot + 1:].strip()
        else:
            rest = body
    rest = _YEAR_RE.sub("", rest).strip(" .,，()")   # 标题区去年份 / 括号
    raw_title = _take_title(rest)
    title = raw_title if _valid_title(raw_title) else None
    return ParsedRef(id=idx, doi=doi, title=title, authors=authors, year=year,
                     type=type_code, raw_text=line,
                     parse_status="ok" if (doi or title) else "unparsed")


def _parse_bib_fields(chunk: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for m in _BIB_FIELD_RE.finditer(chunk):
        key = m.group(1).lower()
        val = m.group(2) if m.group(2) is not None else m.group(3)
        if val is not None and key not in fields:
            fields[key] = val.strip()
    return fields


def _split_bib_authors(raw: str) -> List[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    return [a.strip() for a in re.split(r"\s+and\s+", raw) if a.strip()]


def parse_bib(text: str) -> List[ParsedRef]:
    """解析 .bib：按 @entry 切分，提取 title / author / year / doi / venue。最可靠的结构化格式。

    用计数器（非 enumerate）编号：re.split 在首个 @entry 前会产生空串，enumerate 会
    把空串计入导致 id 偏移（r2/r3 而非 r1/r2）——计数器只在有效条目时递增。
    """
    refs: List[ParsedRef] = []
    idx = 0
    for chunk in re.split(r"(?=@\w+\s*\{)", text or ""):
        chunk = chunk.strip()
        if not chunk.startswith("@"):
            continue
        f = _parse_bib_fields(chunk)
        if not f:
            continue
        idx += 1
        year_raw = (f.get("year") or "").strip()
        year = int(year_raw) if year_raw.isdigit() else _extract_year(year_raw)
        venue = (f.get("journal") or f.get("booktitle") or "").strip() or None
        refs.append(ParsedRef(
            id=f"r{idx}", doi=(f.get("doi") or "").strip() or None,
            title=(f.get("title") or "").strip() or None,
            authors=_split_bib_authors(f.get("author") or ""),
            year=year, venue=venue, raw_text=chunk,
            parse_status="ok" if (f.get("doi") or f.get("title")) else "unparsed"))
    return refs


def parse_text(text: str) -> List[ParsedRef]:
    """自动检测格式并解析：.bib（@entry）优先；否则多行每行一条；单行按单条。"""
    stripped = (text or "").strip()
    if not stripped:
        return []
    if _BIB_ENTRY_RE.search(stripped):
        refs = parse_bib(stripped)
        if refs:
            return refs
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if len(lines) > 1:
        return [_parse_freeform_line(ln, f"r{i}") for i, ln in enumerate(lines, 1)]
    return [parse_single(stripped)]


if __name__ == "__main__":
    import json
    import sys
    json.dump([r.to_dict() for r in parse_text(sys.stdin.read())],
              sys.stdout, ensure_ascii=False, indent=2)
