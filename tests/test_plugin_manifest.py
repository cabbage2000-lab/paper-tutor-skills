"""插件清单的一致性守卫（Claude Code 与 Codex 四份清单 ↔ CHANGELOG）。

启用插件分发后，版本号一下子有了多处写法：`.claude-plugin/plugin.json` 的 version、
`.claude-plugin/marketplace.json` 里 plugin 条目的 version、`.codex-plugin/plugin.json`
的 version、CHANGELOG 的最新版本段。描述与许可证同理，各清单各存一份。这正是本仓库
反复吃过亏的「第二份真相必然漂移」——`skills/README.md` 那份命令清单停在 6 个命令、
漂了 14 条才被发现（见 test_manifest_consistency 的同款守卫）。

发版时最容易漏的就是 plugin.json 的 version：CHANGELOG 写了新版本、tag 也打了，
plugin 清单还停在旧版本号，而装插件的人看到的是清单里的那个。

两个宿主的清单格式不同、不能共用一份：Claude Code 读 `.claude-plugin/`，Codex 读
`.codex-plugin/plugin.json` 与 `.agents/plugins/marketplace.json`，且 Codex 的
plugin.json 多要 `skills` 指针与一整块 `interface`，marketplace 的条目结构也不一样
（`source` 是对象、必带 `policy`）。所以只能各写一份 + 本文件守住不背离。

本文件守六件事：
  1. 四份清单可解析、必填字段齐全；
  2. 版本号处处一致（以 CHANGELOG 最新版本段为准）；
  3. 同一字段在各清单里的写法不背离（跨宿主也不许漂）；
  4. Codex plugin 的 skills 指针与 interface 必填字段符合官方摄取口径；
  5. plugin 根布局合规——两个 `.*-plugin/` 里只放清单，skills/ 必须在仓库根
     （官方明确警告过的坑，放错位置插件加载不到任何 skill）；
  6. 两个根 README 的版本号跟得上发版——第 2 条原先只管清单层，README 反而漂了
     三个版本（停在 v0.1.2 直到 0.1.5）才被发现。

纯标准库，秒级跑完（CLAUDE.md·开发流程：单测只覆盖核心确定性逻辑）。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO_ROOT / ".claude-plugin"
PLUGIN_JSON = PLUGIN_DIR / "plugin.json"
MARKETPLACE_JSON = PLUGIN_DIR / "marketplace.json"
CODEX_PLUGIN_DIR = REPO_ROOT / ".codex-plugin"
CODEX_PLUGIN_JSON = CODEX_PLUGIN_DIR / "plugin.json"
CODEX_MARKETPLACE_JSON = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
# skills/_shared/VERSION：随 skills/ 安装走的版本标识（散装安装无清单文件，
# 用户装完后只能从此处确认版本）。与清单层的 version 同源、同守卫。
SHARED_VERSION = REPO_ROOT / "skills" / "_shared" / "VERSION"

READMES = ("README.md", "README.en.md")

# CHANGELOG 里非 Unreleased 的第一个版本标题即当前版本
VERSION_HEADING_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)

# 两个根 README 里三处「当前版本」的写法。每处都必须命中至少一次：
# 句子被整段删掉也算漂移（对外的版本承诺凭空消失）。
README_VERSION_PATTERNS = (
    (r"status-v(\d+\.\d+\.\d+)-blue", "顶部 status badge"),
    (r"\*\*v(\d+\.\d+\.\d+)\*\*", "简介段的「当前 vX.Y.Z」"),
    (r"[（(]v(\d+\.\d+\.\d+)", "快速开始段的「N 个命令入口已发布（vX.Y.Z）」"),
)

PLUGIN_REQUIRED_FIELDS = ("name", "description", "version", "license", "author")
# 两份清单都写、必须一字不差的字段
MIRRORED_FIELDS = ("name", "description", "version", "license")
# Codex 官方摄取要求的 interface 必填字段（见 plugin-creator/validate_plugin.py）
CODEX_INTERFACE_REQUIRED = (
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
    "capabilities",
    "defaultPrompt",
)


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def plugin() -> dict:
    return _load(PLUGIN_JSON)


@pytest.fixture(scope="module")
def marketplace() -> dict:
    return _load(MARKETPLACE_JSON)


@pytest.fixture(scope="module")
def codex_plugin() -> dict:
    return _load(CODEX_PLUGIN_JSON)


@pytest.fixture(scope="module")
def codex_marketplace() -> dict:
    return _load(CODEX_MARKETPLACE_JSON)


@pytest.fixture(scope="module")
def changelog_version() -> str:
    m = VERSION_HEADING_RE.search(CHANGELOG.read_text(encoding="utf-8"))
    assert m is not None, "CHANGELOG.md 里找不到形如 `## [0.1.0]` 的版本标题"
    return m.group(1)


def test_两份清单存在且可解析(plugin: dict, marketplace: dict):
    assert plugin, f"{PLUGIN_JSON} 为空"
    assert marketplace, f"{MARKETPLACE_JSON} 为空"


@pytest.mark.parametrize("field", PLUGIN_REQUIRED_FIELDS)
def test_plugin清单必填字段齐全(plugin: dict, field: str):
    assert field in plugin, f"plugin.json 缺字段 {field}"
    assert plugin[field], f"plugin.json 的 {field} 为空"


def test_shared_version与CHANGELOG最新版本一致(changelog_version: str):
    """skills/_shared/VERSION 是散装安装后唯一的版本来源，须与 CHANGELOG 同步。

    sync_skills.py 只复制 skills/，不带清单文件——散装安装的用户只能读此文件
    确认版本（paper-help 会读它显示）。漏改会让用户看到旧版本号。
    """
    assert SHARED_VERSION.is_file(), (
        f"{SHARED_VERSION} 不存在——paper-help 读不到版本号、散装安装后无法确认版本。"
    )
    version = SHARED_VERSION.read_text(encoding="utf-8").strip()
    assert version == changelog_version, (
        f"_shared/VERSION 的 {version!r} 与 CHANGELOG 最新版本 {changelog_version!r} "
        f"不一致——发版时漏改 VERSION，散装安装的用户会看到旧版本号。"
    )


@pytest.mark.parametrize("readme_name", READMES)
def test_两个README的版本号与CHANGELOG最新版本一致(readme_name: str, changelog_version: str):
    """README 是对外门面，它写的版本号是用户判断「我装的是不是最新」的唯一依据。

    这里真漂过：README 的版本号停在 v0.1.2，而 0.1.3、0.1.4 两次发版都只改了
    CHANGELOG 与四份清单——连漂三个版本没人发现，因为当时没有守卫盯 README。
    清单层的版本号有本文件其余测试守着，README 反而是最显眼、也最容易忘的那处。
    """
    text = (REPO_ROOT / readme_name).read_text(encoding="utf-8")
    for pattern, where in README_VERSION_PATTERNS:
        found = re.findall(pattern, text)
        assert found, (
            f"{readme_name} 里找不到 {pattern!r}（{where}）形式的版本声明。"
            f"若改了措辞，请同步改本守卫的正则——别让守卫失效。"
        )
        for version in found:
            assert version == changelog_version, (
                f"{readme_name} 的{where}写着 v{version}，CHANGELOG 最新版本是 "
                f"{changelog_version}——用户照 README 判断版本，会以为自己装旧了。"
            )


def test_marketplace恰好登记一个plugin(marketplace: dict):
    plugins = marketplace.get("plugins")
    assert isinstance(plugins, list), "marketplace.json 的 plugins 必须是数组"
    assert len(plugins) == 1, (
        f"marketplace.json 登记了 {len(plugins)} 个 plugin；本仓库按设计只分发一个 "
        "(paper-tutor)。真要加第二个，请连同本测试一起改，别默默加。"
    )


def test_plugin版本号与CHANGELOG最新版本一致(plugin: dict, changelog_version: str):
    assert plugin["version"] == changelog_version, (
        f"plugin.json 的 version={plugin['version']} 与 CHANGELOG 最新版本 "
        f"{changelog_version} 不一致——发版时漏改 plugin 清单，装插件的人看到的是旧版本号。"
    )


@pytest.mark.parametrize("field", MIRRORED_FIELDS)
def test_两份清单同名字段不背离(plugin: dict, marketplace: dict, field: str):
    entry = marketplace["plugins"][0]
    assert entry.get(field) == plugin.get(field), (
        f"marketplace.json 的 plugins[0].{field} 与 plugin.json 的 {field} 不一致：\n"
        f"  marketplace: {entry.get(field)!r}\n  plugin:      {plugin.get(field)!r}"
    )


def test_声明的许可证与LICENSE文件一致(plugin: dict):
    first_line = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8").splitlines()[0]
    # "# PolyForm Noncommercial License 1.0.0" → 清单里写 SPDX 式 PolyForm-Noncommercial-1.0.0
    assert "PolyForm Noncommercial" in first_line and "1.0.0" in first_line, (
        f"LICENSE 首行是 {first_line!r}，与清单声明的 {plugin['license']!r} 对不上"
    )
    assert plugin["license"] == "PolyForm-Noncommercial-1.0.0"


def test_claude_plugin目录只放清单文件():
    """官方明确警告：skills/ 等必须在 plugin 根，塞进 .claude-plugin/ 会加载不到。"""
    allowed = {"plugin.json", "marketplace.json"}
    actual = {p.name for p in PLUGIN_DIR.iterdir() if not p.name.startswith(".")}
    assert actual <= allowed, (
        f".claude-plugin/ 里出现了不该有的内容：{sorted(actual - allowed)}。"
        "该目录只放 plugin.json 与 marketplace.json，skills/ 必须在仓库根。"
    )


def test_codex_plugin目录只放清单文件():
    """同 .claude-plugin：Codex 的 plugin 根也是仓库根，skills/ 不能塞进清单目录。"""
    actual = {p.name for p in CODEX_PLUGIN_DIR.iterdir() if not p.name.startswith(".")}
    assert actual == {"plugin.json"}, (
        f".codex-plugin/ 里出现了不该有的内容：{sorted(actual - {'plugin.json'})}。"
        "该目录只放 plugin.json；Codex 的 marketplace 清单在 .agents/plugins/。"
    )


@pytest.mark.parametrize("field", PLUGIN_REQUIRED_FIELDS)
def test_codex_plugin清单必填字段齐全(codex_plugin: dict, field: str):
    assert field in codex_plugin, f".codex-plugin/plugin.json 缺字段 {field}"
    assert codex_plugin[field], f".codex-plugin/plugin.json 的 {field} 为空"


@pytest.mark.parametrize("field", MIRRORED_FIELDS)
def test_两宿主plugin清单同名字段不背离(
    plugin: dict, codex_plugin: dict, field: str
):
    """同一个 plugin 分两个宿主发行，元信息必须是同一份事实。"""
    assert codex_plugin.get(field) == plugin.get(field), (
        f".codex-plugin/plugin.json 的 {field} 与 .claude-plugin/plugin.json 不一致：\n"
        f"  codex : {codex_plugin.get(field)!r}\n  claude: {plugin.get(field)!r}"
    )


def test_codex_plugin指向仓库根的skills目录(codex_plugin: dict):
    """Codex 靠 skills 指针发现 skill；指错则一个命令都不出现。"""
    assert codex_plugin.get("skills") == "./skills/", (
        f"Codex plugin.json 的 skills={codex_plugin.get('skills')!r}，"
        "必须是 './skills/'——plugin 根即仓库根，skills/ 就在根下。"
    )


@pytest.mark.parametrize("field", CODEX_INTERFACE_REQUIRED)
def test_codex_plugin的interface必填字段齐全(codex_plugin: dict, field: str):
    """缺任一字段，官方摄取校验（plugin-creator/validate_plugin.py）会判整个 plugin 非法。"""
    interface = codex_plugin.get("interface")
    assert isinstance(interface, dict), "Codex plugin.json 缺 interface 块"
    assert interface.get(field), f"Codex plugin.json 的 interface.{field} 缺失或为空"


def test_codex_marketplace恰好登记一个plugin(codex_marketplace: dict):
    plugins = codex_marketplace.get("plugins")
    assert isinstance(plugins, list), "Codex marketplace.json 的 plugins 必须是数组"
    assert len(plugins) == 1, (
        f"Codex marketplace.json 登记了 {len(plugins)} 个 plugin；本仓库按设计只分发一个 "
        "(paper-tutor)。真要加第二个，请连同本测试一起改，别默默加。"
    )


def test_codex_marketplace条目结构合规(
    codex_marketplace: dict, codex_plugin: dict
):
    """Codex 的条目格式与 Claude 版不同：source 是对象、policy 必带，且指向仓库根。"""
    entry = codex_marketplace["plugins"][0]
    assert entry.get("name") == codex_plugin["name"], (
        f"marketplace 条目名 {entry.get('name')!r} 与 plugin.json 的 "
        f"{codex_plugin['name']!r} 不一致——`codex plugin add` 按名字找不到就装不上。"
    )
    source = entry.get("source")
    assert isinstance(source, dict), "Codex marketplace 条目的 source 必须是对象"
    assert source.get("source") == "local" and source.get("path") == "./", (
        f"source={source!r}；仓库自身即 plugin，路径必须是 './'。"
    )
    policy = entry.get("policy")
    assert isinstance(policy, dict), "Codex marketplace 条目必须带 policy 块"
    assert policy.get("installation") == "AVAILABLE", (
        f"policy.installation={policy.get('installation')!r}，必须是 AVAILABLE，"
        "否则用户在市场里装不了。"
    )


def test_plugin根布局正确():
    """仓库根即 plugin 根，skills/ 在根下且每个子目录含 SKILL.md（_shared 除外）。"""
    skills_dir = REPO_ROOT / "skills"
    assert skills_dir.is_dir(), "仓库根缺 skills/——plugin 根布局要求 skills/ 在根"
    missing = [
        d.name
        for d in sorted(skills_dir.iterdir())
        if d.is_dir() and not d.name.startswith("_") and not (d / "SKILL.md").is_file()
    ]
    assert not missing, f"这些 skill 目录缺 SKILL.md，插件加载时会被跳过：{missing}"
