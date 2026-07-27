"""commands.yaml 单一事实来源的一致性守卫。

CLAUDE.md 硬规则 1 把 `skills/_shared/commands.yaml` 定为命令主清单的单一事实
来源，硬规则 2 要求「`name` = 目录名 = 命令名」。但在本文件之前没有任何机制
保证这些约定成立——下列漂移都会无声发生：

  1. 新增 skill 目录忘了在主清单登记（paper-help 的命令总表就漏掉它）；
  2. 主清单写了 `status: released` 但 skill 目录 / SKILL.md 不存在（宿主报错）；
  3. SKILL.md 的 frontmatter `name` 与目录名不一致（宿主按 name 注册，命令名对不上）；
  4. 内建子命令（无独立目录，入口寄生在宿主 skill 里）与独立命令在清单里
     无法区分，于是 1 与 2 都没法机械校验。

第 4 项是建模缺失：`paper-format` / `paper-claim` 内建于 `paper-verify`，
按设计就不该有独立目录，但清单里它们与独立命令长得一模一样。本文件要求这类
命令显式声明 `builtin_in: <宿主命令名>`，契约才可机械校验。

纯标准库 + pyyaml，秒级跑完（CLAUDE.md 基本测试原则）。
"""
from __future__ import annotations

import pathlib
import re

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
MANIFEST_PATH = SKILLS_DIR / "_shared" / "commands.yaml"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.S)


def load_manifest() -> list[dict]:
    """读命令主清单。"""
    return yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_frontmatter(skill_md: pathlib.Path) -> dict:
    """读 SKILL.md 的 YAML frontmatter；无 frontmatter 则返回空 dict。"""
    m = _FRONTMATTER_RE.match(skill_md.read_text(encoding="utf-8"))
    if not m:
        return {}
    return yaml.safe_load(m.group(1)) or {}


def disk_skill_dirs() -> set[str]:
    """磁盘上的 skill 目录名集合（_shared 不是 skill）。"""
    return {
        p.name
        for p in SKILLS_DIR.iterdir()
        if p.is_dir() and p.name.startswith("paper-")
    }


MANIFEST = load_manifest()
STANDALONE = [c for c in MANIFEST if not c.get("builtin_in")]
BUILTIN = [c for c in MANIFEST if c.get("builtin_in")]


def test_主清单可解析且每条都有必需字段():
    """每条命令都要有 name / phase / stage_zh / status / intent_zh。"""
    required = {"name", "phase", "stage_zh", "status", "intent_zh"}
    for cmd in MANIFEST:
        missing = required - set(cmd)
        assert not missing, f"{cmd.get('name', '<无 name>')} 缺字段：{sorted(missing)}"


def test_命令名唯一():
    names = [c["name"] for c in MANIFEST]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"主清单有重复命令名：{sorted(dupes)}"


def test_每个独立命令都有对应的skill目录():
    """非内建命令必须有独立目录——否则宿主装不上、命令不存在。

    内建子命令（声明了 builtin_in）不在此列，见 test_内建子命令不应有独立目录。
    """
    on_disk = disk_skill_dirs()
    missing = [c["name"] for c in STANDALONE if c["name"] not in on_disk]
    assert not missing, (
        f"主清单登记了但磁盘上没有目录：{missing}。"
        f"若这些是内建于其它 skill 的子命令，请在主清单为它们加 "
        f"`builtin_in: <宿主命令名>` 字段。"
    )


def test_每个skill目录都在主清单里登记():
    """磁盘上有目录、清单里没登记 → paper-help / paper-init 都会漏掉它。"""
    names = {c["name"] for c in MANIFEST}
    unregistered = sorted(disk_skill_dirs() - names)
    assert not unregistered, f"磁盘上有 skill 目录但主清单未登记：{unregistered}"


def test_内建子命令不应有独立目录且宿主命令存在():
    """builtin_in 的语义：无独立目录，入口寄生在宿主 skill 的 SKILL.md 里。"""
    on_disk = disk_skill_dirs()
    names = {c["name"] for c in MANIFEST}
    for cmd in BUILTIN:
        host = cmd["builtin_in"]
        assert cmd["name"] not in on_disk, (
            f"{cmd['name']} 声明了 builtin_in 却有独立目录——"
            f"要么删掉 builtin_in（它是独立 skill），要么删掉目录。"
        )
        assert host in names, f"{cmd['name']} 的宿主命令 {host} 不在主清单里"
        assert host in on_disk, f"{cmd['name']} 的宿主命令 {host} 没有 skill 目录"


@pytest.mark.parametrize("skill_dir", sorted(disk_skill_dirs()))
def test_frontmatter的name等于目录名(skill_dir: str):
    """CLAUDE.md 硬规则 2：name = 目录名 = 命令名。"""
    skill_md = SKILLS_DIR / skill_dir / "SKILL.md"
    assert skill_md.exists(), f"{skill_dir} 缺 SKILL.md"
    fm = load_frontmatter(skill_md)
    assert fm, f"{skill_dir}/SKILL.md 没有可解析的 frontmatter"
    assert fm.get("name") == skill_dir, (
        f"{skill_dir}/SKILL.md 的 frontmatter name={fm.get('name')!r}，与目录名不一致"
    )


@pytest.mark.parametrize("skill_dir", sorted(disk_skill_dirs()))
def test_SKILL_md非空且有description(skill_dir: str):
    """CLAUDE.md 硬规则 2：空 SKILL.md 会被宿主误识别为可用 skill。"""
    skill_md = SKILLS_DIR / skill_dir / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    assert len(text.strip()) > 200, f"{skill_dir}/SKILL.md 内容过短，疑似空壳"
    fm = load_frontmatter(skill_md)
    assert fm.get("description"), f"{skill_dir}/SKILL.md 缺 description（宿主靠它触发）"


def test_阶段中文名在主清单内自洽():
    """同一个 phase 在主清单里必须始终对应同一个 stage_zh。"""
    seen: dict[str, str] = {}
    for cmd in MANIFEST:
        phase, stage_zh = cmd["phase"], cmd["stage_zh"]
        if phase in seen:
            assert seen[phase] == stage_zh, (
                f"phase={phase} 在主清单里有两个中文名："
                f"{seen[phase]!r} 与 {stage_zh!r}"
            )
        else:
            seen[phase] = stage_zh


def test_开发规范里提到的命令都真实存在():
    """skills/README.md 引用的每个 /paper-xxx 都必须在主清单里。

    防「文档提到一个不存在的命令」——读者照着试会撞空。
    """
    readme = SKILLS_DIR / "README.md"
    names = {c["name"] for c in MANIFEST}
    # 文档里的占位符写法不是命令引用
    placeholders = {"paper-xxx", "paper-word"}
    referenced = set(re.findall(r"/(paper-[a-z]+)", readme.read_text(encoding="utf-8")))
    unknown = sorted(referenced - names - placeholders)
    assert not unknown, f"skills/README.md 提到了主清单里没有的命令：{unknown}"


def test_开发规范不另存一份命令清单表():
    """skills/README.md 不得用表格维护第二份命令清单——那是第二份真相。

    主清单的 status 字段是唯一事实来源（CLAUDE.md 硬规则 1）。README 再抄一份，
    每次发布命令就要改两处，漏改必然发生：本守卫落地前该表停在 Phase 1 的 6 个
    命令，而实际已发布 20 个，漂了 14 个都没人发现。

    判据取「表格形态」而非标题措辞——换个标题就能绕过的守卫等于没有。行内文字
    提及若干命令（举例、陈述历史）不算清单；一个表格里出现 5 个以上不同命令，
    就是在维护清单，那它必须与主清单一致（或干脆别列）。
    """
    readme_text = (SKILLS_DIR / "README.md").read_text(encoding="utf-8")
    released = {c["name"] for c in MANIFEST if c["status"] == "released"}
    placeholders = {"paper-xxx", "paper-word"}

    # 连续的 | 起始行 = 一个 markdown 表格块
    for table in re.findall(r"(?:^\|.*\|[ \t]*\n)+", readme_text, re.MULTILINE):
        listed = set(re.findall(r"/(paper-[a-z]+)", table)) - placeholders
        if len(listed) < 5:
            continue  # 举例性质，不是清单
        assert listed == released, (
            f"skills/README.md 有一个表格在维护第二份命令清单，与主清单不符："
            f"漏 {sorted(released - listed)}、多 {sorted(listed - released)}。"
            f"改为指向 _shared/commands.yaml，别维护第二份。"
        )


# ── 根 README（对外门面）↔ 主清单 ──────────────────────────────────────
# skills/README.md 的策略是「不许有第二份清单」（见上一条测试）。根 README 不同：
# 它的阶段能力表是对外门面、有展示价值，删不得。所以这里的守卫取另一条路——
# 允许存在，但要求与主清单**完全一致**。
#
# 这两条守卫是补漏：v0.1.0 收口时发现根 README 与 README.en.md 双双停在
# 「20 个 skill」，阶段表漏了 daily / screen / style / typeset 四个命令，而当时
# 全部守卫只盯 skills/README.md，对仓库最显眼的门面文件毫无覆盖。

ROOT_READMES = ["README.md", "README.en.md"]


@pytest.mark.parametrize("readme_name", ROOT_READMES)
def test_根README的命令表与主清单一致(readme_name: str):
    """根 README 的阶段能力表列的命令，必须正好是主清单里 released 的那些。

    漏列 → 新命令对外不可见（用户不知道有这个命令）；
    多列 → 用户照着试会撞空。两者都发生过。
    """
    text = (REPO_ROOT / readme_name).read_text(encoding="utf-8")
    released = {c["name"] for c in MANIFEST if c["status"] == "released"}

    listed: set[str] = set()
    for table in re.findall(r"(?:^\|.*\|[ \t]*\n)+", text, re.MULTILINE):
        found = set(re.findall(r"/(paper-[a-z]+)", table))
        if len(found) >= 5:  # 举例性质的小表不算清单
            listed |= found

    assert listed, f"{readme_name} 里找不到命令能力表——它是对外门面，不该没有"
    assert listed == released, (
        f"{readme_name} 的命令表与主清单不一致："
        f"漏 {sorted(released - listed)}、多 {sorted(listed - released)}。"
        f"发布新命令时请一并更新（中英文两份都要）。"
    )


def test_根README声明的命令数与主清单一致():
    """README 正文里的「N 个命令入口 / N 个 skill 目录 / N 个研究命令」必须算得对。

    数字比表格更容易忘——表格漏一行还看得出来，正文里的「20 个」谁都不会去数。
    每条模式要求至少命中一次：句子被整段删掉也算漂移（对外承诺凭空消失）。
    """
    released = [c for c in MANIFEST if c["status"] == "released"]
    expectations = [
        ("README.md", r"(\d+)\s*个命令入口", len(released), "released 命令入口数"),
        ("README.md", r"(\d+)\s*个 skill 目录", len(disk_skill_dirs()), "skill 目录数"),
        (
            "README.md",
            r"(\d+)\s*个研究命令",
            len([c for c in released if c["phase"] != "infra"]),
            "非 infra 的研究命令数",
        ),
        ("README.en.md", r"(\d+)\s*command entry points", len(released), "released 命令入口数"),
        (
            "README.en.md",
            r"(\d+)\s*skill directories",
            len(disk_skill_dirs()),
            "skill 目录数",
        ),
        (
            "README.en.md",
            r"(\d+)\s*research commands",
            len([c for c in released if c["phase"] != "infra"]),
            "非 infra 的研究命令数",
        ),
    ]
    for readme_name, pattern, expected, desc in expectations:
        text = (REPO_ROOT / readme_name).read_text(encoding="utf-8")
        found = re.findall(pattern, text)
        assert found, (
            f"{readme_name} 里找不到 {pattern!r} 形式的声明（{desc}）。"
            f"若改了措辞，请同步改本守卫的正则——别让守卫失效。"
        )
        for n in found:
            assert int(n) == expected, (
                f"{readme_name} 声明 {n}（{desc}），主清单实际是 {expected}"
            )


def test_阶段中文名与paper_help解析器不漂移():
    """progress_parser 硬编码了一份 _PHASE_STAGE_ZH，必须与主清单一致。

    commands.yaml 是单一事实来源，而 paper-help 全貌视图的解析器又存了一份
    阶段中文名。两份真相必须锁在一起，否则改了主清单、全貌视图仍显示旧名。
    """
    import sys

    parser_dir = REPO_ROOT / "tests" / "paper-help"
    sys.path.insert(0, str(parser_dir))
    try:
        from progress_parser import _PHASE_STAGE_ZH  # noqa: PLC0415
    finally:
        sys.path.remove(str(parser_dir))

    manifest_map = {c["phase"]: c["stage_zh"] for c in MANIFEST}
    for phase, stage_zh in manifest_map.items():
        assert phase in _PHASE_STAGE_ZH, (
            f"主清单有 phase={phase}，progress_parser._PHASE_STAGE_ZH 里没有"
        )
        assert _PHASE_STAGE_ZH[phase] == stage_zh, (
            f"phase={phase} 阶段名漂移：主清单={stage_zh!r}，"
            f"progress_parser={_PHASE_STAGE_ZH[phase]!r}"
        )
