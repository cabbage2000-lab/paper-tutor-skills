"""paper-help 全貌视图的确定性纯函数。

把 .paper/ 留痕（markdown 文本）解析成结构化条目，并按 commands.yaml 派生的
命令-阶段映射算出每阶段进度（X/Y、徽章颜色、未跑命令列表）。

依据：docs/plans/2026-07-26-paper-help-overview-design.md（设计文档）。
纯标准库、无副作用、可独立单测。本模块只负责"客观陈列"——不判完成度、不下价值结论。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TraceEntry:
    """一条 .paper/ 留痕的解析结果。

    字段缺失用空值（空字符串 / None）表示，不抛异常——降级陈列精神
    （设计文档 §4.6）。
    """
    command: str                          # 如 "paper-topic"；识别不出则条目不入列表
    date: str                             # 如 "2026-07-21"；缺失则空串
    product_path: Optional[str]           # 如 "topic/xxx.html"；缺失则 None
    description: str = ""                 # 如 "选题澄清"；缺失则空串


# 留痕条目标题行正则：## <日期> · paper-<command> <描述>
# - 日期取日期粒度（YYYY-MM-DD）
# - 命令名 = paper- 前缀 + 字母/数字/连字符
# - 描述 = 标题行 · 之后、命令名之后的剩余文本（去首尾空白）
_ENTRY_TITLE_RE = re.compile(
    r"^##\s+(\d{4}-\d{2}-\d{2}).*?·\s*(paper-[\w-]+)(?:[^\n]*)?$",
    re.MULTILINE,
)

# 产物字段正则：- 产物：<路径>（路径不含空白）
_PRODUCT_RE = re.compile(r"^-\s*产物[：:]\s*(\S+)", re.MULTILINE)


def parse_trace_entries(md_text: str) -> List[TraceEntry]:
    """解析单个 .paper/ md 文件文本，返回所有可识别的留痕条目。

    识别规则（设计文档 §4.3）：
      1. 条目以 `## <日期> · paper-<cmd> <描述>` 标题行起始；
      2. 命令名提取自标题；日期提取自标题开头；描述提取自标题 · 之后命令名之后；
      3. 产物路径提取自该条目区块内的 `- 产物：` 行；
      4. 识别不出命令名的段落直接跳过（设计文档 §4.6 残缺处理）。

    Args:
        md_text: 单个 md 文件的完整文本。

    Returns:
        按出现顺序的 TraceEntry 列表；md_text 为空 / 全无可识别条目则返回空列表。
    """
    if not md_text:
        return []

    entries: List[TraceEntry] = []
    matches = list(_ENTRY_TITLE_RE.finditer(md_text))
    for i, m in enumerate(matches):
        command = m.group(2)
        date = m.group(1)
        # 描述：标题行里 "paper-xxx" 之后到行尾的文本
        title_line = m.group(0)
        # 标题行结构：## <日期> ... · paper-<cmd> <描述>
        # 用 · 切，右段去掉命令名前缀
        after_dot = title_line.split("·", 1)[-1] if "·" in title_line else ""
        # 去掉命令名前缀、去首尾空白
        description = after_dot.replace(command, "", 1).strip()

        # 产物路径：在该条目区块内查找（到下一个条目或文件末尾）
        block_start = m.end()
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        block = md_text[block_start:block_end]
        product_match = _PRODUCT_RE.search(block)
        product_path: Optional[str] = product_match.group(1) if product_match else None

        entries.append(TraceEntry(
            command=command,
            date=date,
            product_path=product_path,
            description=description,
        ))
    return entries


# ── 阶段进度算法 ────────────────────────────────────────────────────────────


@dataclass
class StageProgress:
    """单个阶段的进度信息。

    unreleased_with_status: List[(command_name, status_zh)] —— 未跑命令 + 状态文案，
        供"下一步弱导航"取候选池用。
    """
    phase: str                              # "A"/"B"/"C"/"D"/"E"/"infra"
    stage_zh: str                           # 中文阶段名
    total_released: int = 0                 # 该阶段已发布命令数
    done_commands: List[str] = field(default_factory=list)             # 已跑命令（去重）
    unreleased: List[str] = field(default_factory=list)                # 未跑命令名
    unreleased_with_status: List[tuple] = field(default_factory=list)  # [(cmd, status_zh)]


@dataclass
class OverallProgress:
    """整体进度：所有阶段 + infra 区。"""
    stages: List[StageProgress] = field(default_factory=list)  # A/B/C/D/E 五阶段
    infra_progress: Optional[StageProgress] = None             # infra 区（init/daily 计入）
    total_entries: int = 0          # 识别出的留痕条目总数
    covered_phases: int = 0         # 至少有一条留痕的研究阶段数（A-E 计 5、infra 不计）


# 全貌视图固定的阶段顺序（A → C → D → E，跳过 B——B 不设命令）
# infra 单独处理；B 在列表里但 total_released=0、走固定文案
_RESEARCH_PHASES = ["A", "B", "C", "D", "E"]
_PHASE_STAGE_ZH = {
    "A": "选题与立项",
    "B": "执行研究",
    "C": "成文",
    "D": "评审与修订",
    "E": "发表与发表后",
    "infra": "跨阶段基础设施",
}
# infra 区只计入 init / daily（设计文档 §5.3：help / doctor 是"工具的维护工具"、不计入）
_INFRA_TRACKED = {"paper-init", "paper-daily"}


def badge_color(done: int, total: int) -> str:
    """阶段徽章颜色（设计文档 §5.2）。

    - 阶段无已发布命令（total=0）→ "none"（不出徽章、出固定文案）
    - 比例 0 → "red"
    - 1/3 ≤ 比例 < 2/3 → "yellow"
    - 比例 ≥ 2/3 → "green"
    """
    if total <= 0:
        return "none"
    ratio = done / total
    if ratio == 0:
        return "red"
    if ratio >= 2 / 3:
        return "green"
    return "yellow"


def compute_stage_progress(
    entries: List[TraceEntry],
    command_meta: Dict[str, dict],
) -> OverallProgress:
    """条目 + commands.yaml 派生的 command_meta → 整体进度。

    Args:
        entries: parse_trace_entries 的输出（多个 md 文件汇总）。
        command_meta: 从 commands.yaml 派生，形如
            {"paper-topic": {"phase": "A", "stage_zh": "...", "status": "released"}, ...}

    Returns:
        OverallProgress —— 五个研究阶段（A-E）+ infra 区 + 总条目数 + 覆盖阶段数。
    """
    # 1. 统计每个命令被跑过的去重集合
    done_set_by_phase: Dict[str, set] = {p: set() for p in _RESEARCH_PHASES + ["infra"]}
    for e in entries:
        meta = command_meta.get(e.command)
        if meta is None:
            continue  # 陌生命令：不计入阶段进度（但 total_entries 仍计入）
        phase = meta["phase"]
        if phase not in done_set_by_phase:
            continue
        # infra 区只统计 _INFRA_TRACKED 内的命令
        if phase == "infra" and e.command not in _INFRA_TRACKED:
            continue
        done_set_by_phase[phase].add(e.command)

    # 2. 算每个阶段的 StageProgress
    stages: List[StageProgress] = []
    for phase in _RESEARCH_PHASES:
        # 该阶段的已发布命令（按 command_meta 筛选）
        released_in_phase = sorted([
            cmd for cmd, m in command_meta.items()
            if m["phase"] == phase and m["status"] == "released"
        ])
        done = sorted(done_set_by_phase.get(phase, set()))
        unreleased = [c for c in released_in_phase if c not in set(done)]
        unreleased_with_status = [
            (c, command_meta[c].get("status", "")) for c in unreleased
        ]
        stages.append(StageProgress(
            phase=phase,
            stage_zh=_PHASE_STAGE_ZH[phase],
            total_released=len(released_in_phase),
            done_commands=done,
            unreleased=unreleased,
            unreleased_with_status=unreleased_with_status,
        ))

    # 3. infra 区
    released_infra_tracked = sorted([
        cmd for cmd, m in command_meta.items()
        if m["phase"] == "infra"
        and m["status"] == "released"
        and cmd in _INFRA_TRACKED
    ])
    done_infra = sorted(done_set_by_phase.get("infra", set()))
    unreleased_infra = [c for c in released_infra_tracked if c not in set(done_infra)]
    infra_progress = StageProgress(
        phase="infra",
        stage_zh=_PHASE_STAGE_ZH["infra"],
        total_released=len(released_infra_tracked),
        done_commands=done_infra,
        unreleased=unreleased_infra,
        unreleased_with_status=[(c, "released") for c in unreleased_infra],
    )

    # 4. 总条目数 & 覆盖阶段数
    total_entries = len(entries)
    covered_phases = sum(
        1 for p in _RESEARCH_PHASES if done_set_by_phase.get(p)
    )

    return OverallProgress(
        stages=stages,
        infra_progress=infra_progress,
        total_entries=total_entries,
        covered_phases=covered_phases,
    )
