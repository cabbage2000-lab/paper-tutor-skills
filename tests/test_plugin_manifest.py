"""Claude Code plugin 清单的一致性守卫（plugin.json ↔ marketplace.json ↔ CHANGELOG）。

启用插件分发后，版本号一下子有了三处写法：`.claude-plugin/plugin.json` 的 version、
`.claude-plugin/marketplace.json` 里 plugin 条目的 version、CHANGELOG 的最新版本段。
描述与许可证同理，plugin.json 与 marketplace.json 各存一份。这正是本仓库反复吃过亏的
「第二份真相必然漂移」——`skills/README.md` 那份命令清单停在 6 个命令、漂了 14 条才被
发现（见 test_manifest_consistency 的同款守卫）。

发版时最容易漏的就是 plugin.json 的 version：CHANGELOG 写了新版本、tag 也打了，
plugin 清单还停在旧版本号，而装插件的人看到的是清单里的那个。

本文件守四件事：
  1. 两份清单可解析、必填字段齐全；
  2. 三处版本号一致（以 CHANGELOG 最新版本段为准）；
  3. marketplace 的 plugin 条目与 plugin.json 对同一字段的写法不背离；
  4. plugin 根布局合规——`.claude-plugin/` 里只放清单，skills/ 必须在仓库根
     （官方明确警告过的坑，放错位置插件加载不到任何 skill）。

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
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

# CHANGELOG 里非 Unreleased 的第一个版本标题即当前版本
VERSION_HEADING_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)

PLUGIN_REQUIRED_FIELDS = ("name", "description", "version", "license", "author")
# 两份清单都写、必须一字不差的字段
MIRRORED_FIELDS = ("name", "description", "version", "license")


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def plugin() -> dict:
    return _load(PLUGIN_JSON)


@pytest.fixture(scope="module")
def marketplace() -> dict:
    return _load(MARKETPLACE_JSON)


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
