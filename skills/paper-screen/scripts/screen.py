#!/usr/bin/env python3
"""paper-screen PRISMA 2020 筛选台账内核——解析 / 分级计数 / 守恒校验 / 流程图渲染。

设计要点：流程图的每一个数字都由本脚本从台账机械算出，LLM 不手写任何数字。
任一守恒等式不成立即报错、**不产出流程图**——一张数字对不上的 PRISMA 图
比没有图更糟：它会被审稿人当作方法学缺陷。

纯标准库（`_shared/README.md` 已决：零第三方运行时依赖，最低 Python 3.9）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

# 台账列序（与 references/纳排标准与排除理由码.md 的字段定义一致）
# field / Dict 供 Task 2 的 StageCounts.exclude_reasons 使用。
_COLS = ("序号", "题录锚点", "来源库", "去重", "标摘筛", "全文筛", "排除理由码", "备注")


@dataclass
class LedgerRow:
    """筛选台账的一行 = 一条被识别的记录。"""
    seq: int
    anchor: str
    source_db: str
    dedup: str
    ta_screen: str
    ft_screen: str
    exclude_code: str
    note: str = ""


def _split_cells(line: str) -> List[str]:
    """把一行 markdown 表格切成单元格。

    只剥掉首尾各**一个**分隔符——不能用 `strip("|")`，那会把末列为空时的
    连续 `|||` 一并吃掉，让 `| 4 | … | 纳入 | | |` 这种合法的紧凑写法被算成
    6 列而丢弃。空单元格是有意义的（备注列常为空）。
    """
    parts = line.split("|")
    if parts and parts[0].strip() == "":
        parts = parts[1:]
    if parts and parts[-1].strip() == "":
        parts = parts[:-1]
    return [c.strip() for c in parts]


def malformed_lines(text: str) -> List[tuple]:
    """找出「意图是数据行但列数不足」的行，返回 [(行号, 原文), …]。

    为什么必须单独报出来而不能静默跳过：`count_stages` 的 identified 只数
    解析成功的行，被丢掉的行不进任何一级，于是三条守恒等式会在**缩水后的
    集合**上照样成立——脚本不报错、图照出、数字全错。那正是本命令要防的
    「数字对不上的 PRISMA 图」，只不过错得更隐蔽。

    判据取「首列为纯数字」= 用户意图写一条数据行；表头、分隔行、说明表、
    合计行的首列都不是数字，不会误报。
    """
    out: List[tuple] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = _split_cells(s)
        if not cells or not cells[0].isdigit():
            continue
        if len(cells) < 8:
            out.append((lineno, s))
    return out


def parse_ledger(text: str) -> List[LedgerRow]:
    """解析筛选台账 markdown 表格。

    只取「首列为纯数字」的行——表头、分隔行、合计行、正文段落一律跳过。
    列数不足 8 的行在此跳过，但**不是静默丢弃**：`malformed_lines()` 会把它们
    找出来，CLI 据此报错并拒绝出图（见该函数的 docstring）。
    """
    rows: List[LedgerRow] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = _split_cells(line)
        if len(cells) < 8:
            continue
        if not cells[0].isdigit():
            continue
        rows.append(
            LedgerRow(
                seq=int(cells[0]),
                anchor=cells[1],
                source_db=cells[2],
                dedup=cells[3],
                ta_screen=cells[4],
                ft_screen=cells[5],
                exclude_code=cells[6],
                note=cells[7],
            )
        )
    return rows


@dataclass
class StageCounts:
    """PRISMA 2020 流程图各级计数。ft_assessed 为派生值（sought - not_retrieved）。"""
    identified: int = 0
    duplicates_removed: int = 0
    after_dedup: int = 0
    ta_excluded: int = 0
    sought: int = 0
    not_retrieved: int = 0
    ft_assessed: int = 0
    ft_excluded: int = 0
    included: int = 0
    exclude_reasons: Dict[str, int] = field(default_factory=dict)


def count_stages(rows: List[LedgerRow]) -> StageCounts:
    """按台账逐行归入 PRISMA 各级。

    归类只认精确取值（「保留」「进入全文」「纳入」…）——取值写错的行会落在
    任何一档之外，于是守恒等式不成立，由 check_conservation 抓出来。这是有意的：
    宁可报错，不可静默归错档。
    """
    c = StageCounts()
    c.identified = len(rows)
    c.duplicates_removed = sum(1 for r in rows if r.dedup.startswith("重复"))
    c.after_dedup = sum(1 for r in rows if r.dedup == "保留")
    kept = [r for r in rows if r.dedup == "保留"]
    c.ta_excluded = sum(1 for r in kept if r.ta_screen == "排除")
    c.sought = sum(1 for r in kept if r.ta_screen == "进入全文")
    sought_rows = [r for r in kept if r.ta_screen == "进入全文"]
    c.not_retrieved = sum(1 for r in sought_rows if r.ft_screen == "全文不可得")
    c.ft_excluded = sum(1 for r in sought_rows if r.ft_screen == "排除")
    c.included = sum(1 for r in sought_rows if r.ft_screen == "纳入")
    c.ft_assessed = c.sought - c.not_retrieved
    reasons: Dict[str, int] = {}
    for r in sought_rows:
        if r.ft_screen == "排除" and r.exclude_code:
            reasons[r.exclude_code] = reasons.get(r.exclude_code, 0) + 1
    c.exclude_reasons = dict(sorted(reasons.items()))
    return c


def check_conservation(c: StageCounts) -> List[str]:
    """校验三条守恒等式，返回不平项的中文描述（空列表 = 守恒）。

    等式取自 PRISMA 2020 流程图的结构约束——每一级的去向必须穷尽且互斥。
    """
    errs: List[str] = []
    d1 = c.identified - (c.duplicates_removed + c.after_dedup)
    if d1 != 0:
        errs.append(
            f"识别总数({c.identified}) ≠ 去重删除({c.duplicates_removed})"
            f" + 去重后({c.after_dedup})，差 {d1}"
        )
    d2 = c.after_dedup - (c.ta_excluded + c.sought)
    if d2 != 0:
        errs.append(
            f"去重后({c.after_dedup}) ≠ 标摘排除({c.ta_excluded})"
            f" + 进入全文({c.sought})，差 {d2}"
        )
    d3 = c.sought - (c.not_retrieved + c.ft_excluded + c.included)
    if d3 != 0:
        errs.append(
            f"进入全文({c.sought}) ≠ 全文不可得({c.not_retrieved})"
            f" + 全文排除({c.ft_excluded}) + 纳入({c.included})，差 {d3}"
        )
    return errs


def logical_conflicts(rows: List[LedgerRow]) -> List[str]:
    """抓守恒等式抓不到的取值组合矛盾。

    守恒校验只能发现「取值落在规定取值之外」的行。取值都合法、但组合矛盾的行
    会让某条记录被静默丢掉，而三条等式照样成立——例：某行标摘筛已填「排除」、
    全文筛却又填了「纳入」，count_stages 按标摘筛把它归入 ta_excluded，那个
    「纳入」凭空消失，用户却以为它进了综述。这类静默丢失比不平衡更危险。
    """
    out: List[str] = []
    for r in rows:
        if r.dedup.startswith("重复") and (r.ta_screen or r.ft_screen):
            out.append(
                f"序号 {r.seq}：已标为重复，不应再填标摘筛 / 全文筛"
                f"（现填「{r.ta_screen or '—'} / {r.ft_screen or '—'}」）"
            )
        if r.ta_screen in ("排除", "待定") and r.ft_screen:
            out.append(
                f"序号 {r.seq}：标摘筛为「{r.ta_screen}」，不应有全文筛结果"
                f"（现填「{r.ft_screen}」）——该行会被静默丢出流程图"
            )
        if r.ft_screen == "排除" and not r.exclude_code:
            out.append(f"序号 {r.seq}：全文阶段排除必须填理由码（PRISMA 硬要求）")
    return out


def pending_seqs(rows: List[LedgerRow]) -> List[int]:
    """返回筛选尚未完成的行序号。

    与 check_conservation / logical_conflicts 区分：待定是正常的中途状态
    （用户还没筛完），不是台账错误。都不出图，但提示语与下一步动作不同。
    """
    out: List[int] = []
    for r in rows:
        if r.dedup != "保留":
            continue
        if r.ta_screen in ("", "待定"):
            out.append(r.seq)
        elif r.ta_screen == "进入全文" and r.ft_screen in ("", "待定"):
            # 全文筛也认「待定」：它在标摘筛列是合法取值，用户照猫画虎写到
            # 全文筛列很自然。不认的话该行会落在三档去向之外、让守恒等式不平，
            # 于是一次正常的「还没筛完」被报成「台账有错」。
            out.append(r.seq)
    return out


def _reason_detail(c: StageCounts) -> str:
    """把排除理由码分布拼成一行（如「E1 × 1；E4 × 1」）。

    理由码列脚本不校验取值（见 references），自由文本会原样进来；`"` 会破坏
    Mermaid 的节点标签语法，故在此统一替成全角引号，两个渲染器共用本函数、
    防护一致。
    """
    if not c.exclude_reasons:
        return "未填理由码"
    return "；".join(
        f'{k.replace(chr(34), "＂")} × {v}' for k, v in c.exclude_reasons.items()
    )


# 识别框不写「数据库检索记录」——台账的「来源库」列支持手工补充的学位论文 /
# 会议集等「其他来源」（见 references 的中文库回填一节）。写死成数据库检索会
# 让含其他来源的台账产出一张与事实不符的图，而 PRISMA 第 16 项要报的正是它。
# 拆「数据库检索 / 其他来源」两栏留后续，当前先如实说「记录总数」。
_IDENTIFY_LABEL = "识别：记录总数"


def render_mermaid(c: StageCounts) -> str:
    """产 PRISMA 2020 流程图的 Mermaid 文本（供 markdown 产物用）。"""
    return f"""flowchart TB
    A["{_IDENTIFY_LABEL}<br/>n = {c.identified}"] --> B["标题摘要筛选<br/>n = {c.after_dedup}"]
    A --> A2["去重删除<br/>n = {c.duplicates_removed}"]
    B --> C["寻求全文<br/>n = {c.sought}"]
    B --> B2["标题摘要阶段排除<br/>n = {c.ta_excluded}"]
    C --> D["全文评估合格性<br/>n = {c.ft_assessed}"]
    C --> C2["全文不可得<br/>n = {c.not_retrieved}"]
    D --> E["纳入综述<br/>n = {c.included}"]
    D --> D2["全文阶段排除<br/>n = {c.ft_excluded}<br/>{_reason_detail(c)}"]
"""


# ── SVG 渲染（离线自包含，供 HTML 报告内嵌）──────────────────────────────
_SVG_W, _SVG_H = 780, 600
_MAIN_X, _MAIN_W = 40, 320
_SIDE_X, _SIDE_W = 450, 290
_BOX_H, _ROW_STEP, _TOP = 76, 116, 24
_INK, _LINE, _FILL = "#2b2724", "#8a827a", "#f7f5f2"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _box(x: int, y: int, w: int, lines: List[str]) -> str:
    """一个圆角框 + 居中多行文字。"""
    out = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{_BOX_H}" rx="6" '
        f'fill="{_FILL}" stroke="{_LINE}" stroke-width="1.2"/>'
    ]
    start = y + _BOX_H / 2 - (len(lines) - 1) * 9
    for i, ln in enumerate(lines):
        out.append(
            f'<text x="{x + w / 2}" y="{start + i * 18 + 5}" text-anchor="middle" '
            f'font-size="13" fill="{_INK}">{_esc(ln)}</text>'
        )
    return "".join(out)


def _arrow_down(x: int, y1: int, y2: int) -> str:
    return (
        f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" stroke="{_LINE}" '
        f'stroke-width="1.2" marker-end="url(#ah)"/>'
    )


def _arrow_right(y: int, x1: int, x2: int) -> str:
    return (
        f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{_LINE}" '
        f'stroke-width="1.2" marker-end="url(#ah)"/>'
    )


def render_svg(c: StageCounts) -> str:
    """产 PRISMA 2020 流程图 SVG——离线自包含，无外链、无脚本。"""
    main = [
        [_IDENTIFY_LABEL, f"n = {c.identified}"],
        ["标题摘要筛选", f"n = {c.after_dedup}"],
        ["寻求全文", f"n = {c.sought}"],
        ["全文评估合格性", f"n = {c.ft_assessed}"],
        ["纳入综述", f"n = {c.included}"],
    ]
    side = [
        ["去重删除", f"n = {c.duplicates_removed}"],
        ["标题摘要阶段排除", f"n = {c.ta_excluded}"],
        ["全文不可得", f"n = {c.not_retrieved}"],
        ["全文阶段排除", f"n = {c.ft_excluded}", _reason_detail(c)],
    ]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_SVG_W} {_SVG_H}" '
        f'width="{_SVG_W}" height="{_SVG_H}" role="img" '
        f'aria-label="PRISMA 2020 筛选流程图">',
        '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{_LINE}"/></marker></defs>',
        f'<rect width="{_SVG_W}" height="{_SVG_H}" fill="#ffffff"/>',
    ]
    for i, lines in enumerate(main):
        y = _TOP + i * _ROW_STEP
        parts.append(_box(_MAIN_X, y, _MAIN_W, lines))
        if i < len(main) - 1:
            parts.append(
                _arrow_down(_MAIN_X + _MAIN_W // 2, y + _BOX_H, y + _ROW_STEP - 2)
            )
    for i, lines in enumerate(side):
        y = _TOP + i * _ROW_STEP
        parts.append(_box(_SIDE_X, y, _SIDE_W, lines))
        parts.append(_arrow_right(y + _BOX_H // 2, _MAIN_X + _MAIN_W, _SIDE_X - 2))
    parts.append("</svg>")
    return "".join(parts)


def main(argv: List[str] | None = None) -> int:
    """CLI。退出码：0 正常 / 1 台账有错 / 2 筛选未完成 / 3 台账读不到。"""
    import argparse
    import pathlib

    ap = argparse.ArgumentParser(description="PRISMA 筛选台账计数与流程图生成")
    ap.add_argument("--ledger", required=True, help="筛选台账 markdown 路径")
    ap.add_argument("--mermaid", help="Mermaid 输出路径（省略则打印到 stdout）")
    ap.add_argument("--svg", help="SVG 输出路径")
    args = ap.parse_args(argv)

    try:
        raw = pathlib.Path(args.ledger).read_text(encoding="utf-8")
    except OSError as e:
        # 读不到台账是环境/输入问题，不是台账内容有错——必须与退出码 1 区分开，
        # 否则调用方会把「路径写错」当成「筛选数据自相矛盾」去排查。
        print(f"读不到筛选台账：{args.ledger}")
        print(f"  原因：{e.strerror or e}")
        print("请确认路径正确、文件存在且可读。")
        return 3
    bad = malformed_lines(raw)
    if bad:
        # 必须在守恒校验之前拦下：被丢掉的行不进任何一级，三条等式会在缩水后的
        # 集合上照样成立——脚本不报错、图照出、数字全错，比不平衡更隐蔽。
        print("台账有格式不完整的数据行（列数不足 8），不产出流程图：")
        for lineno, txt in bad:
            print(f"  · 第 {lineno} 行：{txt}")
        print("这些行不会计入任何一级，留着会让流程图数字凭空缩水。")
        print("请补齐到 8 列：序号 | 题录锚点 | 来源库 | 去重 | 标摘筛 | 全文筛 | 排除理由码 | 备注")
        return 1

    rows = parse_ledger(raw)
    if not rows:
        print("台账中没有可解析的数据行——请确认表格首列为数字序号。")
        return 2

    pend = pending_seqs(rows)
    if pend:
        print(f"筛选未完成：还有 {len(pend)} 条待定（序号 {pend}）。")
        print("这不是台账错误，是筛选还没做完——补完这些行的判定后再跑一次。")
        return 2

    counts = count_stages(rows)
    errs = check_conservation(counts) + logical_conflicts(rows)
    if errs:
        print("台账校验失败，不产出流程图——数字对不上的 PRISMA 图会被当作方法学缺陷：")
        for e in errs:
            print(f"  · {e}")
        print("请核对台账中「去重 / 标摘筛 / 全文筛 / 排除理由码」四列的取值与组合。")
        return 1

    mm = render_mermaid(counts)
    if args.mermaid:
        pathlib.Path(args.mermaid).write_text(mm, encoding="utf-8")
    else:
        print(mm)
    if args.svg:
        pathlib.Path(args.svg).write_text(render_svg(counts), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
