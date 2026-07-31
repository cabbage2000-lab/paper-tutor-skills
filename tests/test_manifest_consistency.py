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


def test_两个README安装提示词里的skill数量与磁盘一致():
    """安装提示词让智能体照数字自检「装全了没」——数字漂了，自检就成了误导。

    提示词是给别的 agent 执行的，用户复制粘贴后不会逐条核对。写「23 个 paper-*」而实际
    有 24 个，agent 装完 23 个就会报告成功，缺的那个要等用户敲命令发现不存在才暴露。
    这类数字比命令表更容易忘同步：加 skill 时谁都会想到改命令表，没人会想到改提示词。
    """
    expected = len([d for d in disk_skill_dirs() if d.startswith("paper-")])
    patterns = [
        ("README.md", r"(\d+)\s*个 paper-\*"),
        ("README.en.md", r"(\d+)\s*paper-\*"),
    ]
    for readme_name, pattern in patterns:
        text = (REPO_ROOT / readme_name).read_text(encoding="utf-8")
        found = re.findall(pattern, text)
        assert found, (
            f"{readme_name} 的安装提示词里找不到 {pattern!r} 形式的 skill 数量声明。"
            f"若改了措辞，请同步改本守卫的正则——别让守卫失效。"
        )
        for n in found:
            assert int(n) == expected, (
                f"{readme_name} 的安装提示词声明 {n} 个 paper-* skill，磁盘实际是 "
                f"{expected} 个——照这段提示词装的人会漏装或误判装全了。"
            )


# ── paper-init 的命令发布映射表 ↔ 主清单 ──────────────────────────────
# CLAUDE.md 硬规则 1 把这张表定为主清单的「派生呈现」，但本守卫落地前它一个断言都
# 没有，于是漂了：v0.1.6 时表停在 18 行，漏了 paper-style / paper-typeset /
# paper-anchor 三条。代价不止表本身不准——paper-init/SKILL.md 明写 README 的
# 「谁写入」列「只准从本表推导」，所以真机生成的 README 里 manuscript/ 与
# submission/ 两行各漏标了一个写入者，而用户没法从 README 本身看出漏了什么。
#
# 与 skills/README.md 的守卫策略不同：那份的判据是「不许有第二份清单」，这份表
# 删不得（它额外承载落盘目录 / README「下一步」行 / 交接语三个 paper-init 专属
# 字段，主清单里没有），所以走「允许存在，但要求与主清单一致」这条路，同根 README。

INIT_SKILL_MD = SKILLS_DIR / "paper-init" / "SKILL.md"
_MAPPING_HEADING = "## 命令发布映射表"
# 主清单里落盘目录非空的条目才该进映射表：init / help / doctor 无产物目录
DIR_COMMANDS = {c["name"]: c for c in MANIFEST if c.get("dir")}


def section_table_rows(path: pathlib.Path, heading: str) -> list[list[str]]:
    """抽某个 `## 小节` 内全部 markdown 表格的数据行，每行为单元格列表。

    按小节切分而非全文扫表格：这两份 SKILL.md 里还有边界表、字段表等别的表格，
    全文扫会把它们行文中提到的命令名也算进清单，守卫就成了误报机器。
    三级标题（`### `）不会被切断——切分模式要求 `## ` 后紧跟空格。
    """
    text = path.read_text(encoding="utf-8")
    assert heading in text, (
        f"{path.parent.name}/{path.name} 里找不到 {heading!r} 小节——"
        f"改了标题请同步本守卫，别让守卫静默失效。"
    )
    body = text.split(heading, 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not re.search(r"/paper-[a-z]+", cells[0]):
            continue  # 表头行与 |---| 分隔行
        rows.append(cells)
    assert rows, (
        f"{path.parent.name}/{path.name} 的 {heading!r} 小节解析出 0 行——"
        f"表格结构变了，请同步本守卫"
    )
    return rows


MAPPING_ROWS = section_table_rows(INIT_SKILL_MD, _MAPPING_HEADING)


def test_paper_init映射表覆盖主清单全部有落盘目录的命令():
    """漏一条 → 生成的 README 在该落盘目录行漏标写入者，用户看不出漏了什么。

    未发布命令也要在表里（状态写「未发布」）：表的维护说明要求发布时只改一个状态格，
    前提是行本身已经在。
    """
    listed: set[str] = set()
    for cells in MAPPING_ROWS:
        listed |= set(re.findall(r"/(paper-[a-z]+)", cells[0]))
    expected = set(DIR_COMMANDS)
    assert listed == expected, (
        f"paper-init 命令发布映射表与主清单不一致："
        f"漏 {sorted(expected - listed)}、多 {sorted(listed - expected)}。"
        f"新增命令时须同步补进该表（落盘目录 / 「下一步」行 / 交接语一并预填）。"
    )


def test_paper_init映射表的落盘目录与发布状态与主清单一致():
    """落盘目录错 → README 把写入者标到错误的目录行；状态错 → 把未发布命令当可用推给用户。"""
    for cells in MAPPING_ROWS:
        names = re.findall(r"/(paper-[a-z]+)", cells[0])
        assert len(cells) >= 3, f"映射表这行列数不足：{cells}"
        unknown = [n for n in names if n not in DIR_COMMANDS]
        assert not unknown, f"映射表这行的命令不在主清单（或主清单里 dir 为空）：{unknown}"

        dirs = {DIR_COMMANDS[n]["dir"] for n in names}
        statuses = {DIR_COMMANDS[n]["status"] for n in names}
        # 一行含多个命令（如 verify 含 format / claim）时，它们必须同目录同状态，
        # 否则这一行的目录格与状态格无法同时说对，就不该合并成一行。
        assert len(dirs) == 1, f"合并成一行的命令落盘目录不同：{names} → {sorted(dirs)}"
        assert len(statuses) == 1, f"合并成一行的命令发布状态不同：{names} → {sorted(statuses)}"

        expected_status = "已发布" if statuses == {"released"} else "未发布"
        assert cells[1] == dirs.pop(), (
            f"{names[0]} 在映射表里的落盘目录是 {cells[1]!r}，"
            f"主清单是 {DIR_COMMANDS[names[0]]['dir']!r}"
        )
        assert cells[2] == expected_status, (
            f"{names[0]} 在映射表里标 {cells[2]!r}，主清单 status="
            f"{DIR_COMMANDS[names[0]]['status']!r} → 应标 {expected_status!r}"
        )


def test_paper_init映射表的下一步列不含尖括号():
    """本列整句抄进 README 正文，而 README 的实例化自检是 grep 尖括号期望零命中。

    表里原有 `<你的 RQ>`（故意留给读者填的占位符），与实例化规则「尖括号项全部替换为
    真实值」正面冲突：替换掉是错的（该由读者填），留着则自检必然误报——真机在生成的
    README 第 32 行命中过。需要读者自填的占位符一律写成「你的 RQ」这类中文引号形态。

    只约束「下一步」列：交接语列的 `<项目目录路径>` 只打印在对话里、不进 README，
    本就该替换成真实路径。
    """
    for cells in MAPPING_ROWS:
        if len(cells) < 4:
            continue
        assert not re.search(r"[<>]", cells[3]), (
            f"映射表 {cells[0]} 的「下一步」列含尖括号：{cells[3]!r}。"
            f"该列会被抄进 README 正文，触发 grep '[<>]' 自检误报——"
            f"需读者自填的占位符请改写成「你的 RQ」这类中文引号形态。"
        )


def test_README模板的零尖括号自检判据仍在():
    """与上一条测试成对：上一条保证映射表守判据，这一条保证判据本身没被删。

    判据的价值在于零例外、可机械执行。措辞若要改，两处一起改。
    """
    text = INIT_SKILL_MD.read_text(encoding="utf-8")
    for needle in ("grep '[<>]' README.md", "正文不应含任何尖括号"):
        assert needle in text, (
            f"paper-init/SKILL.md 里找不到 {needle!r}——README 模板的零尖括号自检"
            f"判据被删或改了措辞。若确要改，请同步 "
            f"test_paper_init映射表的下一步列不含尖括号。"
        )


# ── paper-help 的命令总表 ↔ 主清单 ────────────────────────────────────
# 与 paper-init 映射表同类问题、判据不同：这张表是导航器的全貌视图，覆盖主清单
# **全部**命令（含 infra、含未发布），未发布的标「🔧 开发中」——paper-help/SKILL.md
# 明写「不把未发布命令说成可用、不漏标开发中命令的状态」。
#
# 漏一条的后果比表本身不准更实际：导航器看不见那个命令。用户问到对应环节时会被
# 告知「该环节命令开发中」却给不出名字，或者干脆推荐一个不相关的替代——paper-anchor
# 就这样在总表外待了一整个开发周期。

HELP_SKILL_MD = SKILLS_DIR / "paper-help" / "SKILL.md"
HELP_TABLE_ROWS = section_table_rows(HELP_SKILL_MD, "## 命令总表（按研究阶段分组）")
_HELP_RELEASED = "✅ 已发布"
_HELP_WIP = "🔧 开发中"


def test_paper_help命令总表覆盖主清单全部命令():
    """全貌视图要「全」：infra 与未发布命令都算，后者标 🔧 开发中而非省略。

    与 paper-init 映射表的判据差一处：那张表只收落盘目录非空的命令（它推导的是
    README 的目录行），这张表是命令全貌，init / help / doctor 也要在。
    """
    listed: set[str] = set()
    for cells in HELP_TABLE_ROWS:
        listed |= set(re.findall(r"/(paper-[a-z]+)", cells[0]))
    expected = {c["name"] for c in MANIFEST}
    assert listed == expected, (
        f"paper-help 命令总表与主清单不一致："
        f"漏 {sorted(expected - listed)}、多 {sorted(listed - expected)}。"
        f"新增命令时须同步补进该表（未发布的标 {_HELP_WIP}）。"
    )


def test_paper_help命令总表的状态标记与主清单一致():
    """标错的方向决定了后果：未发布标成已发布 → 用户照着敲会撞空；反之则命令白白藏着。"""
    for cells in HELP_TABLE_ROWS:
        names = re.findall(r"/(paper-[a-z]+)", cells[0])
        assert len(cells) >= 3, f"总表这行列数不足：{cells}"
        by_name = {c["name"]: c for c in MANIFEST}
        unknown = [n for n in names if n not in by_name]
        assert not unknown, f"总表这行的命令不在主清单：{unknown}"

        statuses = {by_name[n]["status"] for n in names}
        # 一行含多个命令（verify 含 format / claim）时它们必须同状态，否则这一行
        # 的状态格无法同时说对，就不该合并成一行。
        assert len(statuses) == 1, f"合并成一行的命令发布状态不同：{names} → {sorted(statuses)}"
        expected = _HELP_RELEASED if statuses == {"released"} else _HELP_WIP
        assert cells[2] == expected, (
            f"{names[0]} 在 paper-help 总表里标 {cells[2]!r}，主清单 status="
            f"{by_name[names[0]]['status']!r} → 应标 {expected!r}"
        )


def test_paper_help的状态标记图例与守卫用的字面量一致():
    """图例是给模型读的口径，守卫用的是同两个字面量——改一处不改另一处就会错判。"""
    text = HELP_SKILL_MD.read_text(encoding="utf-8")
    legend = f"**状态标记**：{_HELP_RELEASED} ｜ {_HELP_WIP}"
    assert legend in text, (
        f"paper-help/SKILL.md 里找不到状态标记图例 {legend!r}。"
        f"若改了标记措辞，请同步本文件的 _HELP_RELEASED / _HELP_WIP。"
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
