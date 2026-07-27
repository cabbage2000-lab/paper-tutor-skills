"""progress_parser 的正反测试。

golden = 标准格式留痕样本（解析器正确识别所有字段）；
catches = 残缺 / 异常格式样本（解析器降级处理、不抛异常）。
依据：docs/plans/2026-07-26-paper-help-overview-design.md §4 扫描规则。
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import progress_parser  # noqa: E402
from progress_parser import parse_trace_entries, TraceEntry  # noqa: E402


def test_single_well_formed_entry():
    """标准格式单条留痕：字段全解析。"""
    md = """## 2026-07-21 14:30 · paper-topic 选题澄清

- 环节：阶段 A｜选题与立项
- 辅助级别：构思讨论
- AI 承担：一步步引导
- 用户决定：RQ 表述
- 产物：topic/研究问题澄清报告.html
"""
    entries = parse_trace_entries(md)
    assert len(entries) == 1
    e = entries[0]
    assert e.command == "paper-topic"
    assert e.date == "2026-07-21"
    assert e.product_path == "topic/研究问题澄清报告.html"
    assert e.description == "选题澄清"


def test_multiple_entries_in_one_file():
    """同一文件多条留痕：全识别、按出现顺序、各自取自己的产物字段。"""
    md = """## 2026-07-21 · paper-topic 选题澄清

- 产物：topic/a.html

## 2026-07-22 · paper-search 文献检索

- 产物：literature/b.md

## 2026-07-24 · paper-search 文献检索（补）

- 产物：literature/c.md
"""
    entries = parse_trace_entries(md)
    assert len(entries) == 3
    assert [e.command for e in entries] == [
        "paper-topic", "paper-search", "paper-search"]
    assert [e.date for e in entries] == [
        "2026-07-21", "2026-07-22", "2026-07-24"]
    assert [e.product_path for e in entries] == [
        "topic/a.html", "literature/b.md", "literature/c.md"]
    assert entries[2].description == "文献检索（补）"


def test_entry_without_product_field():
    """留痕无 `- 产物：` 行：条目照常入列表、product_path=None。"""
    md = """## 2026-07-21 · paper-topic 选题澄清

- 环节：阶段 A
- AI 承担：引导
"""
    entries = parse_trace_entries(md)
    assert len(entries) == 1
    assert entries[0].command == "paper-topic"
    assert entries[0].product_path is None


def test_non_matching_text_is_silently_skipped():
    """非留痕文本（普通 markdown 标题/正文）：不识别、不报错、不入列表。"""
    md = """# AI 使用说明

## 元信息

这是普通段落，没有 paper- 命令。

## 2026-07-21 · 备注（无命令名）

不应被识别。
"""
    entries = parse_trace_entries(md)
    assert entries == []


def test_empty_input_returns_empty_list():
    """空字符串：返回空列表、不抛异常。"""
    assert parse_trace_entries("") == []
    assert parse_trace_entries("   \n\n  ") == []


# ── compute_stage_progress 测试 ─────────────────────────────────────────────


from progress_parser import (  # noqa: E402
    compute_stage_progress, badge_color, OverallProgress, StageProgress,
)


def test_badge_thresholds():
    """徽章颜色阈值（设计文档 §5.2）：≥2/3 绿、[1/3, 2/3) 黄、0 红、total=0 无徽章。"""
    assert badge_color(0, 0) == "none"      # 无已发布命令
    assert badge_color(0, 3) == "red"       # 0%
    assert badge_color(1, 3) == "yellow"    # 33%（边界含）
    assert badge_color(2, 3) == "green"     # 66%（边界含）
    assert badge_color(3, 3) == "green"     # 100%
    assert badge_color(0, 4) == "red"
    assert badge_color(1, 4) == "yellow"    # 25%
    assert badge_color(2, 4) == "yellow"    # 50%
    assert badge_color(3, 4) == "green"     # 75%


# 派生自 commands.yaml（截至 2026-07-26 已发布命令）的最小 command_meta 测试样本
# 真实 commands.yaml 解析在宿主 agent 一侧（SKILL.md 描述）；本测试只验算法
_TEST_COMMAND_META = {
    "paper-init":     {"phase": "infra", "stage_zh": "跨阶段基础设施", "status": "released"},
    "paper-help":     {"phase": "infra", "stage_zh": "跨阶段基础设施", "status": "released"},
    "paper-doctor":   {"phase": "infra", "stage_zh": "跨阶段基础设施", "status": "released"},
    "paper-daily":    {"phase": "infra", "stage_zh": "跨阶段基础设施", "status": "released"},
    "paper-topic":    {"phase": "A", "stage_zh": "选题与立项", "status": "released"},
    "paper-search":   {"phase": "A", "stage_zh": "选题与立项", "status": "released"},
    "paper-method":   {"phase": "A", "stage_zh": "选题与立项", "status": "released"},
    "paper-proposal": {"phase": "A", "stage_zh": "选题与立项", "status": "released"},
    "paper-outline":  {"phase": "C", "stage_zh": "成文", "status": "released"},
    # D 阶段故意不放已发布命令，验"全未发布"边界
}


def test_compute_progress_partial_coverage():
    """部分覆盖：A 跑了 topic+search（含 search 两次去重）、C 未跑、D 无已发布命令。"""
    entries = [
        TraceEntry("paper-topic",  "2026-07-21", "topic/a.html", "选题澄清"),
        TraceEntry("paper-search", "2026-07-22", "lit/b.md", "文献检索"),
        TraceEntry("paper-search", "2026-07-24", "lit/c.md", "文献检索（补）"),
        TraceEntry("paper-init",   "2026-07-20", "README.md", "脚手架"),
    ]
    overall = compute_stage_progress(entries, _TEST_COMMAND_META)

    assert overall.total_entries == 4
    # covered_phases：A 有留痕、C/D/E 无；infra 不计 → 1
    assert overall.covered_phases == 1

    # A 阶段：4 已发布、2 跑过（search 去重）→ yellow（2/4=50%）
    stage_a = next(s for s in overall.stages if s.phase == "A")
    assert stage_a.total_released == 4
    assert set(stage_a.done_commands) == {"paper-topic", "paper-search"}
    assert set(stage_a.unreleased) == {"paper-method", "paper-proposal"}
    assert badge_color(len(stage_a.done_commands), stage_a.total_released) == "yellow"

    # C 阶段：1 已发布、0 跑过 → red
    stage_c = next(s for s in overall.stages if s.phase == "C")
    assert stage_c.total_released == 1
    assert stage_c.done_commands == []
    assert badge_color(0, 1) == "red"

    # B 阶段：固定文案、无已发布命令 → badge none
    stage_b = next(s for s in overall.stages if s.phase == "B")
    assert stage_b.total_released == 0
    assert badge_color(0, 0) == "none"

    # D 阶段：测试样本里无已发布命令 → badge none、total_released=0
    stage_d = next(s for s in overall.stages if s.phase == "D")
    assert stage_d.total_released == 0
    assert badge_color(0, 0) == "none"

    # infra 区：init 跑过、daily 未跑、help/doctor 不计入 done（仅 init/daily 计入全貌）
    assert overall.infra_progress is not None
    assert "paper-init" in overall.infra_progress.done_commands
    assert "paper-daily" in overall.infra_progress.unreleased
    # help/doctor 既不在 done 也不在 unreleased（设计文档 §5.3 排除）
    assert "paper-help" not in overall.infra_progress.done_commands
    assert "paper-help" not in overall.infra_progress.unreleased
    assert "paper-doctor" not in overall.infra_progress.done_commands
    assert "paper-doctor" not in overall.infra_progress.unreleased


def test_compute_progress_all_done():
    """全跑过：所有已发布命令都有留痕、徽章全绿。"""
    entries = [
        TraceEntry("paper-topic",   "2026-07-21", "topic/a.html", ""),
        TraceEntry("paper-search",  "2026-07-22", "lit/b.md", ""),
        TraceEntry("paper-method",  "2026-07-23", "topic/c.html", ""),
        TraceEntry("paper-proposal","2026-07-24", "topic/d.html", ""),
        TraceEntry("paper-outline", "2026-07-25", "ms/e.md", ""),
        TraceEntry("paper-init",    "2026-07-20", "README.md", ""),
        TraceEntry("paper-daily",   "2026-07-26", "daily/f.html", ""),
    ]
    overall = compute_stage_progress(entries, _TEST_COMMAND_META)
    stage_a = next(s for s in overall.stages if s.phase == "A")
    assert badge_color(len(stage_a.done_commands), stage_a.total_released) == "green"
    stage_c = next(s for s in overall.stages if s.phase == "C")
    assert badge_color(len(stage_c.done_commands), stage_c.total_released) == "green"


def test_compute_progress_unknown_command_ignored():
    """留痕里的命令不在 command_meta（陌生命令）：跳过、不影响阶段计数。"""
    entries = [
        TraceEntry("paper-future", "2026-07-21", "x.md", ""),
        TraceEntry("paper-topic",  "2026-07-22", "topic/a.html", ""),
    ]
    overall = compute_stage_progress(entries, _TEST_COMMAND_META)
    # 总条目数：所有识别出的条目（含陌生命令，因为它是真实跑过的痕迹）
    assert overall.total_entries == 2
    stage_a = next(s for s in overall.stages if s.phase == "A")
    assert stage_a.done_commands == ["paper-topic"]


def test_compute_progress_empty_entries():
    """空条目列表：所有阶段 red / none、total=0、covered=0。"""
    overall = compute_stage_progress([], _TEST_COMMAND_META)
    assert overall.total_entries == 0
    assert overall.covered_phases == 0
    stage_a = next(s for s in overall.stages if s.phase == "A")
    assert stage_a.done_commands == []
    assert badge_color(0, stage_a.total_released) == "red"
