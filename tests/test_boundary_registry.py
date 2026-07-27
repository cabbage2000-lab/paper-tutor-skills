"""边界拒绝清单的一致性守卫（清单 ↔ README ↔ PRD 三处不背离）。

本仓库的「不做」此前散在三处、且都是声明式——README 的能做/不做表、PRD
「边界即产品」7 条、各 skill SKILL.md 的红线段。三处没有任何对齐机制：新增
一条「不做」可能只改 README，改了措辞也无人知道，而各 skill 的红线与前两者
从未对表。

代价不是假设。`skills/_shared/commands.yaml:80-83` 记着「paper-pipeline 已
取消……详见 memory: paper-pipeline-wontdo」——那份 memory 已不存在，取消一个
核心架构组件的完整论证只剩注释里三行摘要。

本文件守四件事：
  1. 结构完整性——每条 key 唯一、必填字段齐全（A 类七字段 / B 类五字段）；
  2. 正向锁——README 不做表每格、PRD 边界即产品每条，都有条目认领；
  3. 反向锁——每个同步锚点确实出现在它声明的文件里；
  4. 判据措辞唯一权威——主问句在别处复述时不被改写。

与 `test_shared_conventions.py` 分开：后者守「符号与字段名不漂移」，本文守
「三处清单不背离」，失败诊断路径不同。

纯标准库，秒级跑完（CLAUDE.md 基本测试原则）。
"""
from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "skills" / "_shared" / "references" / "边界拒绝清单.md"
README = REPO_ROOT / "README.md"
PRD = REPO_ROOT / "docs" / "prd" / "paper-tutor-skills-prd-v1.md"

# A / B 两类条目的必填字段。A 类记产品边界（对外承诺），B 类记评估过并拒绝的
# 机制（工程决策），字段不同是有意的——B 类的价值在「替代方案」一栏。
A_FIELDS = ("拒绝什么", "判据命中", "依据", "出口指引", "落实处", "状态", "同步锚点")
B_FIELDS = ("评估过什么", "拒绝理由", "替代方案", "判据关系", "决策日期与出处")

# 二级标题带编号（`## 3. A 类 · 产品边界`），所以按「包含」判定而不是 startswith
SECTION_A = "A 类 · 产品边界"
SECTION_B = "B 类 · 拒绝的机制"

ENTRY_RE = re.compile(r"^### `([^`]+)`\s+(.+)$")
FIELD_RE = re.compile(r"^- \*\*(.+?)\*\*：(.*)$")
ANCHOR_RE = re.compile(r"`([^`]+)`「([^」]+)」")

KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def normalize(text: str) -> str:
    """归一化：去空白、去 markdown 强调符、全角标点转半角。

    正向锁要匹配的两端天然不同形——README 是面向读者的短语「代跑实验 / 代码」，
    PRD 是完整句「不代跑实验 / 代码；」，要求逐字相同不合理。反向锁不用本函数
    （锚点必须逐字抄原文）。
    """
    text = re.sub(r"[*_`]", "", text)
    text = re.sub(r"\s+", "", text)
    for full, half in (("（", "("), ("）", ")"), ("，", ","), ("；", ";"), ("：", ":")):
        text = text.replace(full, half)
    return text


def parse_registry() -> dict:
    """解析清单为 {key: {"kind": "A"|"B", "name": str, "fields": {...}}}。

    重复 key 会在解析阶段就抛出，而不是被 dict 静默覆盖——漏掉重复 key 正是
    这份守卫要防的事情之一。

    `### ` 标题行同理：在 A / B 类区域内，只要不匹配 ENTRY_RE 就在此处显式报
    错，绝不静默降级成「孤儿字段行」。旧实现会在标题行匹配失败时把该行的字段
    悄悄记到 current 仍指向的上一条目上——那一条目从 entries 里消失，它的字
    段还会覆盖前一条目的同名字段，是比「少一条」更隐蔽的数据污染。key 是否
    为 kebab-case 不在这里判断——ENTRY_RE 的 key 捕获组故意宽进（`[^`]+`），
    合法性交给 test_keys_are_kebab_case 里的 KEBAB_RE，两处职责分开。

    这条严格校验只在 A / B 类区域内生效（`if kind:` 挡在 assert 之前）——第
    1/2/5/6 节是叙述性文字，文档增长时在里面加个 `### 常见问题` 之类的小标题
    是正常编辑，不代表要声明条目，不该被当条目格式的错误来报。这样收窄不会
    放回污染 bug：`current` 只有两处来源——进入任何 `## ` 二级标题时无条件重
    置为 None，以及在 A/B 区域内成功解析条目标题时被设为该 key。kind 为 None
    时 current 必然也是 None（唯一能把 current 设为非 None 的分支就在
    `if kind:` 内部），下面 `if m and current` 天然不会触发，污染的前提「
    current 指向一个真实存在的条目」在非 A/B 区域根本不成立。
    """
    assert REGISTRY.exists(), f"边界拒绝清单缺失：{REGISTRY}"
    entries: dict = {}
    kind = None
    current = None
    for raw in REGISTRY.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            if SECTION_A in line:
                kind = "A"
            elif SECTION_B in line:
                kind = "B"
            else:
                kind = None                 # 其余二级标题（判据 / 增删规则等）
            current = None
            continue
        if line.startswith("### "):
            if kind:
                m = ENTRY_RE.match(line)
                assert m, f"条目标题行格式错误，应为「### `key` 中文名」：{line!r}"
                key, name = m.group(1), m.group(2).strip()
                assert key not in entries, f"条目 key 重复：{key}"
                entries[key] = {"kind": kind, "name": name, "fields": {}}
                current = key
            continue
        m = FIELD_RE.match(line)
        if m and current:
            entries[current]["fields"][m.group(1).strip()] = m.group(2).strip()
    return entries


def parse_anchors(value: str) -> list:
    """把同步锚点字段拆成 [(文件路径, 原文短语), ...]。格式：`路径`「短语」，多个用 · 分隔。"""
    return ANCHOR_RE.findall(value)


def test_registry_has_both_sections():
    heads = [
        l for l in REGISTRY.read_text(encoding="utf-8").splitlines() if l.startswith("## ")
    ]
    assert any(SECTION_A in h for h in heads), f"缺二级标题「{SECTION_A}」，解析器按它定 A 类"
    assert any(SECTION_B in h for h in heads), f"缺二级标题「{SECTION_B}」，解析器按它定 B 类"


def test_keys_are_kebab_case():
    """依赖 ENTRY_RE 对 key 宽进（`[^`]+`）——它只管「像不像标题行」，key 是否
    合法交给这里的 KEBAB_RE 判。若 ENTRY_RE 收紧成只认小写，大写 key 会在解析
    阶段就从 entries 消失，这条测试反而会因为遍历不到而误报通过。
    """
    for key in parse_registry():
        assert KEBAB_RE.match(key), f"条目 key 须为 kebab-case：{key}"


def test_entry_counts():
    entries = parse_registry()
    a = [k for k, v in entries.items() if v["kind"] == "A"]
    b = [k for k, v in entries.items() if v["kind"] == "B"]
    assert len(a) >= 8, f"A 类产品边界应至少 8 条，实得 {len(a)}：{a}"
    assert len(b) >= 4, f"B 类拒绝的机制应至少 4 条，实得 {len(b)}：{b}"


def test_required_fields_present():
    for key, entry in parse_registry().items():
        required = A_FIELDS if entry["kind"] == "A" else B_FIELDS
        missing = [f for f in required if not entry["fields"].get(f)]
        assert not missing, f"条目 {key}（{entry['kind']} 类）缺字段：{missing}"


def test_a_entries_have_exit_guidance():
    """PRD 执行规则 2「每条不做配出口指引」的机制化——空话不算数，得有实质内容。"""
    for key, entry in parse_registry().items():
        if entry["kind"] != "A":
            continue
        exit_text = entry["fields"]["出口指引"]
        assert len(exit_text) >= 15, f"条目 {key} 的出口指引过短、看不出该去哪：{exit_text}"


def test_b_entries_have_alternative():
    """B 类的价值全在「替代方案」——它想解决的问题被什么覆盖了，没有这栏就只是拍脑袋。"""
    for key, entry in parse_registry().items():
        if entry["kind"] != "B":
            continue
        alt = entry["fields"]["替代方案"]
        assert len(alt) >= 15, f"条目 {key} 的替代方案过短：{alt}"


# ── 双向锁：清单 ↔ README ↔ PRD ──────────────────────────────────────
# 正向锁防「新增了一条不做而清单漏收」，反向锁防「README / PRD 改了措辞而清单
# 不知道」。两把锁的匹配严格度有意不同：正向锁归一化后单向子串——锚点须是目标
# 文本（README 短语 / PRD 整句）的子串（含相等），不允许反过来（锚点比目标更
# 宽）；否则「按顿号切分逐段认领」形同虚设，见 test_overbroad_anchor_does_not_
# claim_segment。反向锁精确 in（锚点必须逐字抄原文）。

SEGMENT_SEP = re.compile(r"[、；;]")


def split_segments(text: str) -> list:
    """按顿号 / 分号切分。

    README 有两格各含两条边界——「代跑实验 / 代码、编造数据与引用」是
    no-experiment-execution + no-fabrication 两条，「做规避 AI 检测、出具伦理
    豁免判断」是 no-detection-evasion + no-ethics-waiver 两条。逐段要求认领，
    不允许一格只匹配上半句就算过。
    """
    return [s.strip() for s in SEGMENT_SEP.split(text) if s.strip()]


def readme_donot_cells() -> list:
    """取 README「⛔ Paper-Tutor-Skills 不做的」列的每格文本。"""
    cells = []
    in_table = False
    for line in README.read_text(encoding="utf-8").splitlines():
        if "⛔ Paper-Tutor-Skills 不做的" in line:
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 2 or set(cols[1]) <= {"-", " "}:   # 跳过 | --- | --- |
            continue
        cells.append(cols[1])
    assert cells, "没能从 README 解析出「不做的」列——表头或表格结构变了"
    return cells


def prd_boundary_items() -> list:
    """取 PRD「边界即产品」小节下第一个无序列表的各条。"""
    items = []
    in_section = False
    started = False
    for line in PRD.read_text(encoding="utf-8").splitlines():
        if line.startswith("### 边界即产品"):
            in_section = True
            continue
        if not in_section:
            continue
        if line.startswith("### ") or line.startswith("## "):
            break
        if line.startswith("- "):
            started = True
            items.append(line[2:].strip().rstrip("；;。"))
        elif started and not line.strip():
            continue
        elif started and not line.startswith("- "):
            break
    assert items, "没能从 PRD 解析出「边界即产品」清单——章节标题或列表结构变了"
    return items


def all_anchor_phrases() -> list:
    return [
        phrase
        for entry in parse_registry().values()
        for _, phrase in parse_anchors(entry["fields"].get("同步锚点", ""))
    ]


def claimed_by_some_anchor(segment: str, phrases: list) -> bool:
    """锚点须是目标文本的子串（含相等），单向——不允许锚点比目标更宽。

    早前误写成双向子串（`seg in normalize(p) or normalize(p) in seg`），会让
    「比 segment 还宽的锚点」也算认领：把两个条目的 README 锚点都抄成整格
    「代跑实验 / 代码、编造数据与引用」，`seg in normalize(p)` 那个方向仍会
    判真，逐段切分检查形同虚设。收窄为单向后，只保留「短锚点匹配长目标」这个
    真实需要的方向（如锚点「不接收他人在审稿件」匹配 PRD 整句）。
    """
    seg = normalize(segment)
    return any(normalize(p) in seg for p in phrases)


def test_readme_donot_cells_all_claimed():
    """正向锁 · README：每格（含顿号切分后的每段）都要有条目认领。"""
    phrases = all_anchor_phrases()
    for cell in readme_donot_cells():
        for seg in split_segments(cell):
            assert claimed_by_some_anchor(seg, phrases), (
                f"README 不做表的「{seg}」在边界拒绝清单里没有条目认领——"
                f"新增了一条「不做」就要同时立条目"
            )


def test_overbroad_anchor_does_not_claim_segment():
    """锚点抄整格（比 segment 宽）不算认领——否则「按顿号切分逐段认领」形同虚设。

    README 有两格各含两条边界，设计要求四个条目各抄自己那半句。若匹配放宽成
    双向子串，两个条目都抄整格也能全绿，切分检查就成了摆设。
    """
    whole = "代跑实验 / 代码、编造数据与引用"
    for seg in split_segments(whole):
        assert not claimed_by_some_anchor(seg, [whole]), f"过宽锚点「{whole}」不应认领「{seg}」"
    assert claimed_by_some_anchor("代跑实验 / 代码", ["代跑实验 / 代码"])


def test_prd_boundary_items_all_claimed():
    """正向锁 · PRD：边界即产品每条都要有条目认领。"""
    phrases = all_anchor_phrases()
    for item in prd_boundary_items():
        assert claimed_by_some_anchor(item, phrases), (
            f"PRD 边界即产品的「{item}」在边界拒绝清单里没有条目认领"
        )


def test_anchors_exist_in_declared_files():
    """反向锁：每个同步锚点必须逐字出现在它声明的文件里。"""
    for key, entry in parse_registry().items():
        if entry["kind"] != "A":
            continue
        raw = entry["fields"]["同步锚点"]
        pairs = parse_anchors(raw)
        assert pairs, f"条目 {key} 的同步锚点无法解析（格式应为 `路径`「短语」）：{raw}"
        for rel_path, phrase in pairs:
            target = REPO_ROOT / rel_path
            assert target.exists(), f"条目 {key} 的锚点指向不存在的文件：{rel_path}"
            assert phrase in target.read_text(encoding="utf-8"), (
                f"条目 {key} 的锚点「{phrase}」在 {rel_path} 里找不到——"
                f"要么文件改了措辞、要么锚点没抄原文"
            )


# ── 判据措辞唯一权威 ──────────────────────────────────────────────────
# 四问是给全部 skill 用的公共尺子。尺子被各处复述时改写，就等于有了几把不同的
# 尺子——这正是 test_shared_conventions.py 守四层标注符号时踩过的坑（paper-figure
# 把第三层写成了别的符号）。当前尚无别处复述，本组是给后续引用兜底的。
#
# 本组测试的边界：test_main_question_not_paraphrased_elsewhere 只能抓住「保留了
# MAIN_FRAGMENT（"研究决策还在用户手里"这十个字）子串的措辞漂移」——如「吗」改
# 「么」、标点变体；抓不住彻底重写成不含该子串的复述（例如改写成「决策权是否仍
# 归用户？」）。这是纯标准库 + 秒级跑完约束下的取舍，不是遗漏——真做语义级复述
# 检测要上 NLP，超出这份约束。真正的防线是新功能评审时人工对照清单第 2 节四问。

MAIN_QUESTION = "这一步之后，研究决策还在用户手里吗？"
MAIN_FRAGMENT = "研究决策还在用户手里"
CRITERIA_NAMES = ("归属", "可溯", "可见", "责任")


def iter_repo_docs():
    """扫分发单元 skills/ 下的全部 md、仓库根 README、PRD（清单自身除外）。"""
    for path in (REPO_ROOT / "skills").glob("**/*.md"):
        if path != REGISTRY:
            yield path
    yield README
    yield PRD


def test_main_question_defined_once_in_registry():
    text = REGISTRY.read_text(encoding="utf-8")
    assert text.count(MAIN_QUESTION) == 1, (
        f"主问句应在清单第 2 节定义且仅定义一次，实得 {text.count(MAIN_QUESTION)} 次"
    )


def test_four_criteria_names_present():
    text = REGISTRY.read_text(encoding="utf-8")
    for name in CRITERIA_NAMES:
        assert f"| {name} |" in text, f"判据表缺「{name}」一行——四问是固定的四个"


def test_main_question_not_paraphrased_elsewhere():
    for path in iter_repo_docs():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if MAIN_FRAGMENT in line:
                assert MAIN_QUESTION in line, (
                    f"{path.relative_to(REPO_ROOT)}:{lineno} 复述主问句时改写了措辞，"
                    f"应逐字用「{MAIN_QUESTION}」：{line.strip()}"
                )
