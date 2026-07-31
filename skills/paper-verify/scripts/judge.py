#!/usr/bin/env python3
"""paper-verify 六态判定（spec §4）——本 skill 的核心新增价值。

输入 ParsedRef（parse_refs 产出）+ Evidence（fetch_batch 产出）+ 可选 manual_result
（人工回填），输出 StatusRecord。判定是**确定性 Python 规则**：无 LLM、无网络，
全部依据 Evidence 里的证据。这是 verify 区别于 claim 的关键，也是量化门槛可客观
验收的基础（judge 可被确定性单测完全覆盖）。

判定优先级（首条命中）——设计意图见 spec §4：
  0. manual_result.verified   → VERIFIED（人工核对确认，核对劳动沉淀）
  1. parse_status=unparsed    → PENDING_MANUAL（解析失败出口）
  2. 中文 DOI 无题录 / 无 DOI 中文 → PENDING_MANUAL（中文轨最先拦截，绝不进 NOT_FOUND）
     中文 DOI（ISTIC / CNKI）**取到题录则不在此拦截**，照第 4/5 步正常核验
  3. doi_ra=not_registered    → NOT_FOUND（前缀未注册，DOI 不存在的最强信号）
  4. 有 hit 带 retraction      → RETRACTED（撤稿优先于存在性）
  5. 有 hit                    → 字段比对 → VERIFIED / METADATA_MISMATCH
  6. 全源 miss + error         → UNVERIFIED（查不成，区分 miss ≠ error）
  7. 全源 miss + 注册机构源 miss → NOT_FOUND（注册机构自证不存在，覆盖编造 DOI 号码）
  8. 其余 miss                  → PENDING_MANUAL（不轻易 NOT_FOUND，防误伤）
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "_shared"))
from paper_shared.datasources.models import Evidence  # noqa: E402
# 中文 DOI 注册机构名单在 routing（单一事实来源，硬规则 6）——新增一家中文 RA 只改那边
from paper_shared.datasources.routing import CN_DOI_RA  # noqa: E402
# 字段比对内核在共享层（paper-verify 与 paper-search 两个消费者，硬规则 6）。
# 阈值（标题重叠 0.8 / 年份差 2）与作者姓候选集合的实现都在那边，改那里会同时改本模块的
# 第 5 条判定——动之前先读 tests/paper-verify/test_judge.py 里的比对内核用例。
from paper_shared.matching import (  # noqa: E402
    FieldNote,
    compare_fields,
    pick_best_hit as _pick_best_hit,
)


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


# ---- 判定辅助（字段比对本身在 paper_shared.matching，阈值表见 spec §4.3）----

def _is_cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in (text or ""))


def _fmt_date_parts(dp: Any) -> str:
    """Crossref date-parts（[[2010, 2, 6]]）→ '2010-02-06'；缺月日则只到已有精度。"""
    if not isinstance(dp, list) or not dp or not isinstance(dp[0], list):
        return ""
    parts = [p for p in dp[0] if isinstance(p, int)]
    return "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts))


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
    #
    # 关键条件是 `not evidence.hits`：中文 DOI 现在走 doi_meta 的内容协商，**取到题录就该
    # 正常核验**（往下走第 4/5 步的撤稿检查与字段比对）。此前这里无条件拦截，于是即使拿到
    # 了完整题录也照样落待人工核对——把已经核验成功的条目退回人工，是降级降得过早。
    # 无 hit 时行为不变：仍落 PENDING_MANUAL，绝不进 NOT_FOUND。
    if evidence.doi_ra in CN_DOI_RA and not evidence.hits:
        # 只说「前缀已注册」：RA 判别是前缀级的，说成「DOI 合法存在」等于替一个可能编造的
        # DOI 作存在性担保（实测编造后缀的前缀照样报 ISTIC）。判据精度必须如实。
        return StatusRecord(rid, "PENDING_MANUAL", [],
                            f"{evidence.doi_ra}（中文 DOI）注册：DOI 前缀已注册、本条题录未取到，"
                            "待人工核对",
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
        # 溯源如实取自响应，不硬编码 Retraction Watch——OpenAlex 的 is_retracted
        # 不经 Retraction Watch，写死会让来源标注失真（硬约束④：降级与出处不美化）。
        best = max(retracted, key=lambda h: bool((h.retraction or {}).get("date_parts")))
        r = best.retraction or {}
        extra = [x for x in (f"撤稿日期 {_fmt_date_parts(r.get('date_parts'))}"
                             if r.get("date_parts") else "",
                             f"撤稿数据来自 {r['source']}" if r.get("source") else "") if x]
        srcs = "、".join(sorted({h.source for h in retracted}))
        return StatusRecord(rid, "RETRACTED", [],
                            f"该引用已被标记撤稿（数据源 {srcs}"
                            + ("；" + "；".join(extra) if extra else "") + "）",
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
