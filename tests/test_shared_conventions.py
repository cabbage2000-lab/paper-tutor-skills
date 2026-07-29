"""跨 skill 共享约定的一致性守卫（四层内容标注 / 学科三梯队 / 留痕契约）。

三个概念被 9-18 个 skill 复用，但在本文件之前 `_shared/` 里都没有权威定义：

  - **四层内容标注**（👤/📋/🪞/❓）：被 11+ 个 skill 的产物使用，是读者判断
    「这句话来自谁」的锚点，也是 paper-disclose 汇编、paper-help 全貌
    视图跨产物对齐的依据。定义此前只在 `_shared/references/报告组件库.md`
    的组件示例里隐含，没有独立权威——结果 paper-figure 的产物模板把第三层
    写成了别的符号，同一 skill 的 SKILL.md 与它自己的产物模板互相矛盾。
  - **学科三梯队**：源自 PRD·学科适配，被 9+ 个 skill 复用。但 PRD 是内部稿、
    不随仓库发布（README 明示），于是分发单元 `skills/` 里没有任何权威定义，
    各 skill 只能各自复述——复述就会漂移，且新 skill 无处可抄。
  - **留痕契约**（`.paper/` 使用记录字段）：有两个消费者（paper-disclose
    汇编、paper-help 全貌视图的 progress_parser），18 个生产者，字段一致
    此前全靠复制粘贴维持，没有定义、没有校验。

本文件不强求各 skill 的**领域适配表述**统一（figure 按图类需求、submit 按
期刊生态各自调整三梯队，那是有意差异），只守三件事：共享定义存在、其中的
产品立场不被改写、以及全仓库的**符号与字段名**不漂移。

纯标准库，秒级跑完（CLAUDE.md 基本测试原则）。
"""
from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SHARED_REF = REPO_ROOT / "skills" / "_shared" / "references"
TAGS_DOC = SHARED_REF / "四层内容标注.md"
TIERS_DOC = SHARED_REF / "学科三梯队.md"
TRACE_DOC = SHARED_REF / "留痕契约.md"

# 四层的语义名（用于在正文里定位「符号 + 语义名」组合）。
# 语义名本身在各 skill 里有措辞变体（如「待用户决定」/「待用户验证」），
# 那是文案自由；符号不是，符号是跨产物对齐的锚点。
LAYER_NAMES = ["用户原话", "常见事实", "系统归纳", "待用户决定", "待用户验证"]


def is_emoji(ch: str) -> bool:
    """判断单个字符是否落在 emoji 码位区间。

    必须排除汉字（U+4E00-U+9FFF）与全角标点（U+FF00-U+FFEF）——语义名前面
    紧邻的往往是正文汉字或括号，把它们当成「非权威符号」是误报。
    四层符号实际码位：👤 U+1F464 · 📋 U+1F4CB · 🪞 U+1FA9E · ❓ U+2753。
    """
    cp = ord(ch)
    return (
        0x1F000 <= cp <= 0x1FAFF      # 主 emoji 区（含 🪞 🧠 👤 📋）
        or 0x2600 <= cp <= 0x27BF     # 杂项符号与装饰符（含 ❓ ✅ ⚠ 的基码位邻域）
        or 0x2B00 <= cp <= 0x2BFF     # 杂项符号与箭头
    )

# 扫描范围：分发单元 skills/ 下的全部 md 与 html（含产物模板与样例）
def iter_skill_docs():
    skills = REPO_ROOT / "skills"
    for pattern in ("**/*.md", "**/*.html"):
        for p in skills.glob(pattern):
            yield p


def authoritative_symbols() -> dict[str, str]:
    """从共享定义文件解析四层的权威符号。

    定义文件里每层一行，形如：
        | t1 | 👤 | 用户原话 | ... |
    返回 {"t1": "👤", ...}
    """
    text = TAGS_DOC.read_text(encoding="utf-8")
    found = {}
    for m in re.finditer(r"^\|\s*(t[1-4])\s*\|\s*(\S+?)\s*\|", text, re.MULTILINE):
        found[m.group(1)] = m.group(2)
    return found


# ── 四层内容标注 ────────────────────────────────────────────────────────────


def test_四层内容标注有共享权威定义():
    assert TAGS_DOC.exists(), (
        f"缺共享定义 {TAGS_DOC.relative_to(REPO_ROOT)}——"
        f"四层标注被 11+ 个 skill 使用，必须有单一权威，否则符号会漂移。"
    )


def test_四层权威定义恰好定义四层符号():
    syms = authoritative_symbols()
    assert set(syms) == {"t1", "t2", "t3", "t4"}, (
        f"共享定义应恰好定义 t1-t4 四层，实际解析到：{sorted(syms)}"
    )
    assert len(set(syms.values())) == 4, f"四层符号必须互不相同：{syms}"


@pytest.mark.parametrize("doc", sorted(iter_skill_docs(), key=lambda p: str(p)))
def test_四层标注符号不漂移(doc: pathlib.Path):
    """任何「<符号> 系统归纳」类组合里的符号，必须是共享定义里那一个。

    这条抓的是真实 bug：同一 skill 的 SKILL.md 用 A 符号、产物模板用 B 符号，
    生成的产物就与其他 skill 的产物对不齐，disclose / help 跨产物汇编时断链。
    """
    syms = authoritative_symbols()
    # 语义名 → 权威符号
    expected_for = {
        "用户原话": syms["t1"],
        "常见事实": syms["t2"],
        "系统归纳": syms["t3"],
        "待用户决定": syms["t4"],
        "待用户验证": syms["t4"],
    }
    text = doc.read_text(encoding="utf-8")
    rel = doc.relative_to(REPO_ROOT)
    violations = []
    for name in LAYER_NAMES:
        # 捕获语义名前紧邻的单个非空白、非标签字符（即那个 emoji）
        for m in re.finditer(rf"([^\s>|＝=:：\"'])\s*{name}", text):
            sym = m.group(1)
            want = expected_for[name]
            # 只在捕获到的字符本身是四层符号之一时才判定（避免把普通汉字当符号）
            if sym in set(syms.values()) and sym != want:
                violations.append(f"「{sym} {name}」应为「{want} {name}」")
            # 捕获到错误变体（是 emoji，但不在权威集里）
            elif sym not in set(syms.values()) and is_emoji(sym):
                violations.append(f"「{sym} {name}」用了非权威符号，应为「{want}」")
    assert not violations, f"{rel} 四层标注符号漂移：" + "；".join(sorted(set(violations)))


# ── 学科三梯队 ──────────────────────────────────────────────────────────────


def test_学科三梯队有共享权威定义():
    assert TIERS_DOC.exists(), (
        f"缺共享定义 {TIERS_DOC.relative_to(REPO_ROOT)}——三梯队源自 PRD，"
        f"但 PRD 是内部稿不随仓库发布，分发单元里必须有一份权威。"
    )


def test_三梯队定义覆盖PRD的三档与判定依据():
    text = TIERS_DOC.read_text(encoding="utf-8")
    for tier in ["第一梯队", "第二梯队", "第三梯队"]:
        assert tier in text, f"三梯队定义缺 {tier}"
    # PRD·学科适配：梯队由「文献基础设施 × 论文形态」两因素相乘决定
    for factor in ["文献基础设施", "论文形态"]:
        assert factor in text, f"三梯队定义缺判定依据「{factor}」（PRD·学科适配）"


def test_三梯队定义保留不是价值排序的产品立场():
    """PRD 明确「梯队是现实描述、不是价值排序」，这条立场必须传达到分发层。

    丢掉它，第三梯队（人文学科）用户读到的就是一句「你的学科排第三」。
    """
    text = TIERS_DOC.read_text(encoding="utf-8")
    assert "不是价值排序" in text, "三梯队定义必须保留 PRD 的「不是价值排序」声明"


# ── 留痕契约 ────────────────────────────────────────────────────────────────


def test_留痕契约有共享权威定义():
    assert TRACE_DOC.exists(), (
        f"缺共享定义 {TRACE_DOC.relative_to(REPO_ROOT)}——"
        f"`.paper/` 留痕有 2 个消费者、18 个生产者，字段必须有权威定义。"
    )


def test_留痕契约定义了消费者依赖的全部字段():
    """两个消费者各自依赖的字段都必须在契约里。

    - paper-disclose 按「辅助级别」分桶到 PRD 四级；
    - progress_parser 解析「产物」路径与标题行的日期 + 命令名。
    """
    text = TRACE_DOC.read_text(encoding="utf-8")
    for field in ["辅助级别", "AI 承担", "用户决定", "产物", "环节"]:
        assert field in text, f"留痕契约缺字段定义：{field}"


def test_留痕契约的四级辅助级别与PRD一致():
    text = TRACE_DOC.read_text(encoding="utf-8")
    for level in ["构思讨论", "大纲结构", "成句生成", "语言润色"]:
        assert level in text, f"留痕契约缺 PRD 四级辅助级别：{level}"


def test_留痕契约的标题行格式与解析器一致():
    """契约声明的标题行格式，必须能被 progress_parser 的正则实际解析。

    这是契约与实现的锁——契约写一套、解析器认另一套，等于没有契约。
    """
    import sys

    parser_dir = REPO_ROOT / "tests" / "paper-help"
    sys.path.insert(0, str(parser_dir))
    try:
        from progress_parser import parse_trace_entries  # noqa: PLC0415
    finally:
        sys.path.remove(str(parser_dir))

    text = TRACE_DOC.read_text(encoding="utf-8")
    # 契约文件里的示例留痕（```md 代码块）必须能被解析出至少一条完整条目
    blocks = re.findall(r"```(?:md|markdown)?\n(.*?)```", text, re.S)
    assert blocks, "留痕契约必须给一个可解析的示例留痕代码块"
    parsed = [e for b in blocks for e in parse_trace_entries(b)]
    assert parsed, (
        "留痕契约里的示例留痕无法被 progress_parser 解析——"
        "契约格式与解析器实现不一致。"
    )
    assert any(e.product_path for e in parsed), (
        "示例留痕的「产物」字段没被解析出来，契约示例格式与解析器不符"
    )


# `- 产物：<值>` 形式的留痕模板行（缩进任意、全角或半角冒号皆可，同契约声明）
_PRODUCT_FIELD = re.compile(r"^\s*-\s*产物[：:]\s*(.+?)\s*$")


def test_留痕契约示例的产物路径不被解析器截断():
    """契约示例是各 skill 的抄写源——示例错一次会传染全仓库（已实际发生）。

    上一条测试只验「产物字段能被解析出来」，不验解析出的**是不是原样**。于是
    契约示例长期写着 `manuscript/摘要.md（+ .html）`，解析器按空白切分只取到
    `manuscript/摘要.md（+`，测试却照过——15 个 skill 抄了这个示例。本条补上
    「解析结果必须与字面一致」这一层。
    """
    import sys

    parser_dir = REPO_ROOT / "tests" / "paper-help"
    sys.path.insert(0, str(parser_dir))
    try:
        from progress_parser import parse_trace_entries  # noqa: PLC0415
    finally:
        sys.path.remove(str(parser_dir))

    text = TRACE_DOC.read_text(encoding="utf-8")
    blocks = re.findall(r"```(?:md|markdown)?\n(.*?)```", text, re.S)
    checked = 0
    for block in blocks:
        written = [m.group(1) for m in
                   (_PRODUCT_FIELD.match(ln) for ln in block.splitlines()) if m]
        if not written:
            continue
        entries = parse_trace_entries(block)
        if not entries:
            continue
        assert entries[0].product_path == written[0], (
            f"契约示例的产物路径被截断：字面是「{written[0]}」、"
            f"解析出「{entries[0].product_path}」。"
            f"这份示例是各 skill 的抄写源，错一次传染全仓库。"
        )
        checked += 1
    assert checked, "留痕契约里找不到带「产物」字段的示例留痕块"


def test_全部SKILL的产物字段不含空白():
    """`产物` 字段被 progress_parser 按空白切分取第一段——含空白即被截断。

    截断后的路径（如 `manuscript/摘要.md（+`）不存在，全貌视图照它去找产物会
    判成「产物缺失」。2026-07-29 用真实解析器实测发现 15 个 skill 全中，统一修正。

    正确写法见留痕契约「`产物` 字段为什么必须不含空白」：多产物用顿号连、
    中间不留空格；`.html` 是 `.md` 的机械投影，不必进这个字段。
    """
    bad = []
    for skill_md in sorted((REPO_ROOT / "skills").glob("*/SKILL.md")):
        for lineno, line in enumerate(
                skill_md.read_text(encoding="utf-8").splitlines(), 1):
            m = _PRODUCT_FIELD.match(line)
            if m and re.search(r"\s", m.group(1)):
                bad.append(f"{skill_md.parent.name}/SKILL.md:{lineno} → 「{m.group(1)}」")
    assert not bad, (
        "这些留痕模板的「产物」字段含空白，会被 progress_parser 截断：\n  "
        + "\n  ".join(bad)
        + "\n\n多产物用顿号连（不留空格）；`.html` / `.md` 视图不必写进这个字段。"
    )
