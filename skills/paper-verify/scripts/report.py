#!/usr/bin/env python3
"""paper-verify 核验报告渲染（spec §7 / §9）——JSON + Markdown 双产物。

JSON 机器可读（断点续验复用、下游消费、manual_result 回填载体）；Markdown 人读
（<details> 折叠证据链、六态 emoji 扫读、PENDING_MANUAL 内嵌人工核对包、人机分工页脚）。
纯渲染、无网络、无判定逻辑——输入是 verify.py 组装好的 payload dict。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

# 六态顺序（报告分布表排列）+ emoji + 中文标签（spec §4.1，CLAUDE.md 语言规范）
STATUS_ORDER = ["VERIFIED", "METADATA_MISMATCH", "RETRACTED",
                "NOT_FOUND", "UNVERIFIED", "PENDING_MANUAL"]
STATUS_LABEL = {
    "VERIFIED": ("✅", "已核实"),
    "METADATA_MISMATCH": ("⚠️", "元数据不符"),
    "RETRACTED": ("🚫", "已撤稿"),
    "NOT_FOUND": ("❓", "未找到（疑似不存在）"),
    "UNVERIFIED": ("⏳", "无法核实"),
    "PENDING_MANUAL": ("🔍", "待人工核对"),
}
# 需优先关注的态（投稿前必处理）
PRIORITY_STATUSES = ("NOT_FOUND", "RETRACTED", "METADATA_MISMATCH")
# 降级明标文案（代码层红线：API 失败必须显式声明，绝不静默用模型记忆顶替）。
# report_html 直接 import 本字典——MD 与 HTML 两版对同一次降级说同一句话。
NETWORK_BANNER = {
    "offline": ("核验不可用：核心数据源全不可达（疑似断网）",
                "本次未取得有效 API 响应，报告中的判定不足以支撑任何存在性结论。"
                "建议先跑 /paper-doctor 排查网络，再重跑核验。"),
    "degraded": ("部分降级：有数据源未查成",
                 "标「无法核实」的条目是「没查成」而非「查了没有」，与「疑似不存在」性质不同。"
                 "网络恢复后重跑即可（断点续验会跳过已完成条目）。"),
}


def build_json_payload(meta: Dict[str, Any], items: List[Dict[str, Any]],
                       stats: Dict[str, Any]) -> Dict[str, Any]:
    """组装完整 JSON payload（spec §7.1）。"""
    return {
        "run_id": meta["run_id"],
        "created_at": meta["created_at"],
        "input_fingerprint": meta["fingerprint"],
        "network_status": meta["network_status"],
        "stats": stats,
        "sources_checked": meta["sources_checked"],
        "items": items,
    }


def build_markdown(payload: Dict[str, Any]) -> str:
    """把 JSON payload 渲染成人读 Markdown 报告（spec §9）。"""
    lines: List[str] = []
    created = payload.get("created_at", "")
    lines.append(f"# 引用核验报告 · {created[:10] if created else ''}")
    lines.append("")

    _render_network(lines, payload)
    _render_distribution(lines, payload)
    _render_priority(lines, payload)
    _render_sources(lines, payload)
    _render_items(lines, payload)
    _render_footer(lines)
    return "\n".join(lines)


def _render_network(lines, payload):
    """降级明标——network_status 非 ok 时置于报告最前，不藏在 JSON 里。"""
    status = payload.get("network_status", "ok")
    banner = NETWORK_BANNER.get(status)
    if not banner:
        return
    title, detail = banner
    lines.append(f"> **⚠️ 降级声明（network_status={status}）：{title}**")
    lines.append(f"> {detail}")
    lines.append("")


def _render_distribution(lines, payload):
    lines.append("## 六态分布")
    lines.append("| 态 | 数量 | 占比 |")
    lines.append("|---|---|---|")
    total = payload.get("stats", {}).get("total", 0)
    by_status = payload.get("stats", {}).get("by_status", {})
    for status in STATUS_ORDER:
        n = by_status.get(status, 0)
        if not n:
            continue
        emoji, label = STATUS_LABEL[status]
        pct = f"{n / total * 100:.0f}%" if total else "0%"
        lines.append(f"| {emoji} {label} | {n} | {pct} |")
    lines.append("")


def _render_priority(lines, payload):
    priority = [it for it in payload.get("items", [])
                if it.get("status") in PRIORITY_STATUSES]
    if not priority:
        return
    lines.append("## 需优先关注")
    for it in priority:
        emoji, label = STATUS_LABEL[it["status"]]
        lines.append(f"- {emoji} **{it['ref_id']} · {label}** —— {it.get('evidence_summary', '')}")
    lines.append("")


def _render_sources(lines, payload):
    lines.append("## 已查源清单")
    auto = [s["name_zh"] for s in payload.get("sources_checked", []) if s.get("coverage") == "自动核验"]
    guided = [s["name_zh"] for s in payload.get("sources_checked", []) if s.get("coverage") == "待人工核对"]
    parts = []
    if auto:
        parts.append("、".join(auto) + "（自动核验）")
    if guided:
        parts.append("、".join(guided) + "（待人工核对）")
    lines.append("；".join(parts) if parts else "（无）")
    lines.append("")


def _render_items(lines, payload):
    lines.append("## 逐条详情")
    lines.append("")
    for it in payload.get("items", []):
        lines.extend(_render_item(it))
        lines.append("")


def _render_item(it):
    status = it.get("status", "")
    emoji, label = STATUS_LABEL.get(status, ("•", status))
    out = [f"### {it['ref_id']} · {emoji} {label}"]
    if it.get("raw_text"):
        out.append(f"> {it['raw_text']}")
    out.append("")
    if it.get("evidence_summary"):
        out.append(f"**{it['evidence_summary']}**")
        out.append("")
    # 字段级标注
    for fn in it.get("field_notes", []) or []:
        sev = "不符" if fn.get("severity") == "mismatch" else "提示"
        out.append(f"- {fn.get('field')}：引用 {fn.get('ref_value')} / 源 {fn.get('source_value')}"
                   f"（{sev}）{fn.get('detail', '')}")
    if it.get("field_notes"):
        out.append("")
    # 证据链折叠
    out.append("<details><summary>证据链</summary>")
    ev = it.get("evidence") or {}
    if ev.get("doi_ra"):
        out.append(f"- DOI 路由：{ev['doi_ra']}")
    if ev.get("route_note"):
        out.append(f"- {ev['route_note']}")
    for q in ev.get("queries", []) or []:
        suffix = f"（{q['error']}）" if q.get("error") else ""
        out.append(f"- {q.get('source')}：{q.get('outcome')}{suffix}")
    for h in ev.get("hits", []) or []:
        out.append(f"- {h.get('source')} 命中")
    out.append("</details>")
    out.append("")
    # 人工核对包（PENDING_MANUAL）
    if status == "PENDING_MANUAL":
        out.append("**人工核对包**：")
        out.append("- 检索方案（知网）：标题 + 作者 + 年份 → "
                   "[知网高级检索](https://kns.cnki.net/kns8/AdvSearch)")
        out.append("- 检索方案（万方）：标题 + 作者 + 年 → "
                   "[万方检索](https://www.wanfangdata.com.cn/index.html)")
        out.append("- 核对要点：找到后回填 DOI / 卷期页 / 文献类型")
        out.append("- 回填指引：在本报告同名 JSON 的该条 `manual_result` 字段填 "
                   "`{verified:true, doi:\"...\", note:\"...\", checked_at:\"...\"}`，"
                   "重跑 verify 即升级为已核实")
        out.append("")
    # 出口建议
    if it.get("exit_guidance"):
        out.append(f"**建议**：{it['exit_guidance']}")
        out.append("")
    # 格式问题
    if it.get("format_issues"):
        out.append("**格式提示**：")
        for fi in it["format_issues"]:
            out.append(f"- {fi['problem']}（{fi['clause']}）—— {fi['suggestion']}")
        out.append("")
    return out


def _render_footer(lines):
    lines.append("---")
    lines.append("")
    lines.append("> **人机分工**：本报告由 AI 自动取证（真实 API 响应）+ 规则判定（六态映射），"
                 "「疑似不存在」「元数据不符」均为客观证据推断、非动机指控；"
                 "最终判断（是否编造、如何处理）由用户负责。")


def write_outputs(payload: Dict[str, Any], json_path, md_path) -> None:
    """把 payload 落盘为 JSON + Markdown（verify.py 调用）。"""
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(payload), encoding="utf-8")
