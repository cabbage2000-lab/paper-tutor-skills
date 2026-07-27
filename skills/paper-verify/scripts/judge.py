#!/usr/bin/env python3
"""paper-verify 六态判定（spec §4）——本 skill 的核心新增价值。

输入 ParsedRef（parse_refs 产出）+ Evidence（fetch_batch 产出）+ 可选 manual_result
（人工回填），输出 StatusRecord。判定是**确定性 Python 规则**：无 LLM、无网络，
全部依据 Evidence 里的证据。这是 verify 区别于 claim 的关键，也是量化门槛可客观
验收的基础（judge 可被确定性单测完全覆盖）。

判定优先级（首条命中）——设计意图见 spec §4：
  0. manual_result.verified   → VERIFIED（人工核对确认，核对劳动沉淀）
  1. parse_status=unparsed    → PENDING_MANUAL（解析失败出口）
  2. ISTIC / 无 DOI 中文       → PENDING_MANUAL（中文轨最先拦截，绝不进 NOT_FOUND）
  3. doi_ra=not_registered    → NOT_FOUND（前缀未注册，DOI 不存在的最强信号）
  4. 有 hit 带 retraction      → RETRACTED（撤稿优先于存在性）
  5. 有 hit                    → 字段比对 → VERIFIED / METADATA_MISMATCH
  6. 全源 miss + error         → UNVERIFIED（查不成，区分 miss ≠ error）
  7. 全源 miss + 注册机构源 miss → NOT_FOUND（注册机构自证不存在，覆盖编造 DOI 号码）
  8. 其余 miss                  → PENDING_MANUAL（不轻易 NOT_FOUND，防误伤）
"""
from __future__ import annotations

import dataclasses
import pathlib
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
from paper_shared.datasources.models import Evidence, normalize_doi  # noqa: E402

# 标题比对的英文停用词（中文走 PENDING_MANUAL 不比标题，此处服务英文）
_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "for", "and", "or", "to", "with",
    "from", "by", "at", "as", "is", "are", "via", "using", "into",
}


@dataclass
class FieldNote:
    """单字段比对结果。severity=mismatch 升 MISMATCH 态；hint 仅记录不升态。"""
    field: str
    ref_value: Any
    source_value: Any
    severity: str          # mismatch | hint
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class StatusRecord:
    """一条引用的判定结果。"""
    ref_id: str
    status: str            # VERIFIED | METADATA_MISMATCH | RETRACTED | NOT_FOUND | UNVERIFIED | PENDING_MANUAL
    field_notes: List[FieldNote] = field(default_factory=list)
    evidence_summary: str = ""
    exit_guidance: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ref_id": self.ref_id,
            "status": self.status,
            "field_notes": [n.to_dict() for n in self.field_notes],
            "evidence_summary": self.evidence_summary,
            "exit_guidance": self.exit_guidance,
        }


# ---- 字段比对（spec §4.3 阈值表）----

def _is_cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in (text or ""))


def _normalize_str(s: str) -> str:
    """归一化字符串：去所有非字母数字、小写（用于姓 / venue 比对）。"""
    return re.sub(r"[\W_]+", "", (s or ""), flags=re.UNICODE).lower()


def _first_author_surname(raw: str) -> str:
    """提取第一作者姓：逗号前为姓（西文 'Smith, John'）/ 第一作者（中文 '王明, 李华'）；
    无逗号取首个 token。归一化后返回。"""
    s = (raw or "").strip()
    if not s:
        return ""
    before = re.split(r"[,，]", s)[0].strip()
    parts = before.split()
    token = parts[0] if parts else before
    return _normalize_str(token)


def _title_tokens(title: str) -> set:
    t = re.sub(r"[^\w\s]", " ", (title or "").lower())
    return {w for w in t.split() if w and w not in _STOPWORDS}


def _title_overlap(a: str, b: str) -> float:
    """重叠系数 = |交集| / min(|A|, |B|)——引用标题常是源标题子集（省略副标题），
    重叠系数比 Jaccard 更宽容合法省略（spec §4.3）。"""
    ta, tb = _title_tokens(a), _title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def compare_fields(parsed, hit) -> List[FieldNote]:
    """对照 ParsedRef 与一个 SourceHit 的元数据，返回逐字段比对（spec §4.3）。

    只在「引用与源都有该字段」时比对——避免引用没填 venue 却报不符。venue/type
    不符仅记 hint、不升态（源间口径差异大，升态会拉高误报）。
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
        ov = _title_overlap(parsed.title, meta["title"])
        if ov < 0.8:
            notes.append(FieldNote("title", parsed.title, meta["title"], "mismatch",
                                   f"标题重叠 {ov:.2f}（阈值 0.8）"))
    # 第一作者姓：归一化后不等升态
    if parsed.authors and meta.get("authors"):
        ref_s = _first_author_surname(parsed.authors[0])
        src_s = _first_author_surname(str(meta["authors"][0]))
        if ref_s and src_s and ref_s != src_s:
            notes.append(FieldNote("first_author", parsed.authors[0], meta["authors"][0],
                                   "mismatch", "第一作者姓不一致"))
    # venue：仅提示（包含关系即视为一致，容忍缩写）
    if parsed.venue and meta.get("venue"):
        a, b = _normalize_str(parsed.venue), _normalize_str(str(meta["venue"]))
        if a and b and a not in b and b not in a:
            notes.append(FieldNote("venue", parsed.venue, meta["venue"], "hint", "期刊名写法不一（仅提示）"))
    return notes


def _pick_best_hit(parsed, hits) -> Any:
    """多 hit 时选最匹配的：DOI 相等优先；否则标题重叠最高；否则第一个。"""
    if parsed.doi:
        nd = normalize_doi(parsed.doi)
        for h in hits:
            hd = h.metadata.get("doi")
            if hd and normalize_doi(hd) == nd:
                return h
    if parsed.title:
        return max(hits, key=lambda h: _title_overlap(parsed.title, h.metadata.get("title") or ""))
    return hits[0]


def _summarize_mismatch(notes: List[FieldNote]) -> str:
    fields = [n.field for n in notes if n.severity == "mismatch"]
    return "元数据不符：" + "、".join(fields) if fields else "元数据不符"


# ---- 主判定 ----

def judge(parsed, evidence: Evidence,
          manual_result: Optional[Dict[str, Any]] = None) -> StatusRecord:
    """六态判定主入口。parsed 为 parse_refs.ParsedRef（duck-typed，避免循环 import）。"""
    rid = parsed.id

    # 0. 人工回填优先（核对劳动沉淀，spec §7.2）
    if manual_result and manual_result.get("verified"):
        at = manual_result.get("checked_at", "")
        return StatusRecord(rid, "VERIFIED", [],
                            f"人工核对确认存在{(' @ ' + at) if at else ''}",
                            None)

    # 1. 解析失败
    if parsed.parse_status == "unparsed":
        return StatusRecord(rid, "PENDING_MANUAL", [],
                            "引用未能自动解析",
                            "解析失败出口：改贴 .bib 导出，或拆成单条 DOI/标题核验")

    # 2. 中文轨（最先拦截——合法中文文献绝不进 NOT_FOUND，硬约束⑤）
    if evidence.doi_ra == "ISTIC":
        return StatusRecord(rid, "PENDING_MANUAL", [],
                            "ISTIC（中文 DOI）注册：DOI 合法、元数据 API 不可达，待人工核对",
                            "人工核对包：知网/万方检索方案 + manual_result 回填指引")
    if not parsed.doi and _is_cjk(parsed.title or ""):
        return StatusRecord(rid, "PENDING_MANUAL", [],
                            "无 DOI 的中文文献：开放 API 未覆盖，待人工核对",
                            "人工核对包：知网/万方检索方案 + manual_result 回填指引")

    # 3. 前缀未注册 → NOT_FOUND（DOI 不存在的最强信号，spec §4.2 条件3a）
    if evidence.doi_ra == "not_registered":
        return StatusRecord(rid, "NOT_FOUND", [],
                            "DOI 前缀未在任一注册机构注册——疑似不存在的引用",
                            "其他可能：DOI 抄写错误 / 预印本未注册；复核：doi.org 手查")

    # 4. 撤稿（优先于存在性：撤稿论文「存在但已撤」）
    retracted = [h for h in evidence.hits if h.retraction]
    if retracted:
        src = retracted[0].source
        return StatusRecord(rid, "RETRACTED", [],
                            f"该引用已被标记撤稿（数据源 {src} / Retraction Watch）",
                            "投稿前必处理：替换该引用或在文中说明撤稿情况")

    # 5. 有 hit → 字段比对 → VERIFIED / METADATA_MISMATCH
    if evidence.hits:
        best = _pick_best_hit(parsed, evidence.hits)
        notes = compare_fields(parsed, best)
        if any(n.severity == "mismatch" for n in notes):
            return StatusRecord(rid, "METADATA_MISMATCH", notes,
                                _summarize_mismatch(notes),
                                "核对不符字段是否抄写有误；venue/type 仅提示不升态")
        sources = sorted({h.source for h in evidence.hits})
        return StatusRecord(rid, "VERIFIED", notes,
                            f"已在 {', '.join(sources)} 找到且关键元数据一致",
                            None)

    # 6. 全源 miss + 有 error → UNVERIFIED（区分 miss ≠ error，误报率 ≤5% 的关键）
    if any(q.outcome == "error" for q in evidence.queries):
        return StatusRecord(rid, "UNVERIFIED", [],
                            "查询未完成（网络 / 超时 / 退避耗尽），无法核实",
                            "网络恢复后重跑（断点续验会跳过已完成条目）")

    # 7. 注册机构自证不存在 → NOT_FOUND（覆盖编造 DOI 号码，spec §4.2 条件3b/3c）
    if parsed.doi and evidence.doi_ra in ("Crossref", "DataCite"):
        return StatusRecord(rid, "NOT_FOUND", [],
                            f"DOI 注册机构 {evidence.doi_ra} 及各开放源均查无此文——疑似不存在的引用",
                            "其他可能：DOI 号码抄写错误 / 收录延迟；复核：doi.org 手查")

    # 8. 其余 miss → PENDING_MANUAL（不轻易 NOT_FOUND，防误伤）
    return StatusRecord(rid, "PENDING_MANUAL", [],
                        "开放 API 未命中（可能中文库文献或元数据未收录），待人工核对",
                        "人工核对包：知网/万方检索方案 + manual_result 回填指引；勿据此判定编造")
