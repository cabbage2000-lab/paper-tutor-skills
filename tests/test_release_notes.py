"""Release notes 提取链路的守卫（`scripts/extract_changelog_notes.py`）。

这个脚本是发版链路上唯一的关键脚本——`release.yml` 靠它把 CHANGELOG 对应版本段
变成 GitHub Release 正文——却长期零单测。补测的直接动因是 0.1.5 发版时的一次实况：
CHANGELOG 的 0.1.5 段落到打 tag 前仍是开发骨架（顶着「发版前必须改写」的警告块、
摘要句是「（待填：…）」），而当时脚本只拦「段落找不到」与「段落为空」两种情形，
占位符两道都过——差一步就把骨架发到 GitHub Release 上，靠人肉复核才发现。

于是脚本补了第三道检查（`find_blockers`：哨兵 + HTML 注释），本文件守它。

**本文件有意不断言「CHANGELOG 最新版本段落可以发布」。** 那等于把发版时刻的检查
搬进每次 push 都跑的 tests.yml：骨架在开发期是合法状态（开完骨架要一路累加条目），
断言它可发布会让整个开发周期 CI 长红，而长红会让人对红灯脱敏——比没有守卫更危险。
最新段落由 `release.yml` 在打 tag 那一刻检查，那才是它从合法变成错误的时点。
已发布的历史段落则**必须**干净，见本文件最后一条。

纯标准库，秒级跑完（CLAUDE.md 基本测试原则）。
"""
from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "extract_changelog_notes.py"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

# 与 test_plugin_manifest.py 同一口径：只认数字版本标题，`## [Unreleased]` 天然跳过
VERSION_HEADING_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)


def _load_script():
    """按路径加载 scripts/ 下的脚本（那是 CLI 脚本、不是包，不能直接 import）。"""
    spec = importlib.util.spec_from_file_location("extract_changelog_notes", SCRIPT)
    assert spec is not None and spec.loader is not None, f"无法加载 {SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


notes = _load_script()


SAMPLE = """# 变更日志

---

## [0.2.0] — 2026-08-01

**本版摘要句。**

### 新增（Added）

- 条目甲

---

## [0.1.9] — 2026-07-01

**上一版摘要句。**

- 条目乙
"""


def test_按版本号切出对应段落():
    section = notes.extract_section(SAMPLE, "0.2.0")
    assert section is not None
    assert "本版摘要句" in section
    assert "条目甲" in section


def test_段落不吃进下一个版本的内容():
    """切段边界错会让 Release notes 把上一版的内容也发一遍。"""
    section = notes.extract_section(SAMPLE, "0.2.0")
    assert "上一版摘要句" not in section
    assert "条目乙" not in section
    assert "0.1.9" not in section


def test_段落末尾的分隔线不进正文():
    section = notes.extract_section(SAMPLE, "0.2.0")
    assert not section.endswith("-")


def test_找不到版本时返回None():
    """找不到即发布失败——宁可不发，也不发空白 Release。"""
    assert notes.extract_section(SAMPLE, "9.9.9") is None


def test_最后一个版本段落取到文件末尾():
    section = notes.extract_section(SAMPLE, "0.1.9")
    assert section is not None
    assert "条目乙" in section


def test_干净段落没有阻塞项():
    section = notes.extract_section(SAMPLE, "0.2.0")
    assert notes.find_blockers(section) == []


def test_哨兵在则拒绝发布():
    section = f"<!-- {notes.SKELETON_SENTINEL} 本段落仍是开发骨架 -->\n\n**（待填）**"
    blockers = notes.find_blockers(section)
    assert blockers, "留着骨架哨兵必须拦下发布"
    assert any(notes.SKELETON_SENTINEL in b for b in blockers), (
        f"报错里要点出哨兵名 {notes.SKELETON_SENTINEL}，否则发版时看不懂该删什么"
    )


def test_哨兵检查不依赖骨架的措辞():
    """哨兵是机器可读契约，骨架提示语随便改都得拦住。

    这正是不用「待填」「开发中骨架」这类字面量黑名单的理由：黑名单一改措辞就静默
    失效，等于又造一份会漂移的真相。下面这段与仓库当前骨架用词完全不同。
    """
    section = (
        f"<!-- {notes.SKELETON_SENTINEL}: draft, do not ship -->\n\n"
        "**Summary pending.**"
    )
    assert notes.find_blockers(section), "换一套措辞后哨兵仍须生效"


def test_正文里提到哨兵名不算骨架():
    """哨兵只在 HTML 注释块内才算哨兵，正文提到这个名字不该拦下发布。

    0.1.6 发版时真踩到：那一版的 CHANGELOG 段落正文在讲这套哨兵机制本身、写出了
    哨兵名，而检查是整段搜字面量，于是被自己的检查拦住。改措辞躲开不算修——
    CLAUDE.md 的发版流程与后续 CHANGELOG 都会提到这个名字。
    """
    section = (
        "**本版摘要句。**\n\n"
        f"- 补第三道检查：段落里留着 `{notes.SKELETON_SENTINEL}` 哨兵即拒绝发布。"
    )
    assert notes.find_blockers(section) == [], "正文提到哨兵名不是骨架残留"


def test_未闭合的注释里的哨兵仍拦得住():
    """骨架注释写坏了（漏了 `-->`）也不能漏拦。"""
    section = f"<!-- {notes.SKELETON_SENTINEL} 本段落仍是开发骨架\n\n**（待填）**"
    assert notes.find_blockers(section), "未闭合注释里的哨兵仍须生效"


def test_残留HTML注释即拒绝发布():
    """兜底：万一开骨架时忘了写哨兵，脚手架注释还在就仍拦得住。

    0.1.5 的骨架段落末尾就有这样一块「其他分类按需增补……」的开发者注释。
    """
    section = "**摘要句。**\n\n<!-- 其他分类按需增补：### 变更（Changed） -->"
    blockers = notes.find_blockers(section)
    assert blockers, "发布文本里不该留给开发者看的 HTML 注释"
    assert any("<!--" in b or "注释" in b for b in blockers)


def test_两类阻塞项会一并报出():
    """一次把该改的都说清，免得删了哨兵重打 tag 又栽在注释上。"""
    section = f"<!-- {notes.SKELETON_SENTINEL} -->\n\n**（待填）**\n\n<!-- 待办 -->"
    assert len(notes.find_blockers(section)) == 2


def _released_versions() -> list[str]:
    """CHANGELOG 里除最新段之外的版本号——它们都已发布，内容是历史事实。"""
    return VERSION_HEADING_RE.findall(CHANGELOG.read_text(encoding="utf-8"))[1:]


def test_已发布的历史段落全部干净():
    """已发版的段落必须是可发布状态——它们的内容已经进了 GitHub Release。

    这条与 release.yml 互补：release.yml 事前拦（打 tag 那一刻），这条事后抓
    （下个版本开发时立刻红）。若某次发版真把骨架发出去了，这里会指名道姓。
    最新段落有意排除在外，理由见模块 docstring。
    """
    versions = _released_versions()
    assert versions, "CHANGELOG 里至少该有一个已发布版本段"
    changelog_text = CHANGELOG.read_text(encoding="utf-8")
    for version in versions:
        section = notes.extract_section(changelog_text, version)
        assert section, f"CHANGELOG 的 [{version}] 段落为空"
        blockers = notes.find_blockers(section)
        assert not blockers, (
            f"已发布版本 [{version}] 的段落里还有发布阻塞项：{blockers}"
            f"——这段内容已经进了 GitHub Release，说明那次发版漏了收口。"
        )
