#!/usr/bin/env python3
"""从 CHANGELOG.md 摘取指定版本对应的段落，供 release workflow 生成 Release notes。

CHANGELOG.md 遵循 Keep a Changelog 格式：每个版本一个 `## [x.y.z] — date` 标题，
版本段的边界就是相邻两个 `## [` 标题行之间的区间（分隔符用短横还是破折号都不影响）。

用法：python3 scripts/extract_changelog_notes.py <version>
<version> 不带 v 前缀（如 0.1.0），与 CHANGELOG 里 `[0.1.0]` 的写法一致。

找不到对应版本段、摘取内容为空白、或段落仍是开发骨架，都以非 0 退出码结束并向
stderr 报错——Release notes 宁可不发，也不发空白或残缺的。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ANY_VERSION_HEADING_RE = re.compile(r"^## \[", re.MULTILINE)

# 开版本骨架时写进段落的哨兵，发版收口时删掉。见到它即拒绝出 Release notes。
#
# 为什么这道检查在本脚本、而不是 pytest：骨架在开发期是**合法**状态（开完骨架要一路
# 累加条目，中间每次 push 都跑 tests.yml），它只在发版这一刻才变成错误。做成 pytest
# 断言会让整个开发周期 CI 长红，而长红会让人对红灯脱敏——比没有守卫更危险。本脚本
# 只被 release.yml 调用，正好卡在状态翻转的那一刻。
#
# 为什么用哨兵、而不是「待填」「开发中骨架」这类字面量黑名单：黑名单一改措辞就静默
# 失效，等于又造一份会漂移的真相。哨兵是机器可读契约，骨架措辞可以随便改；删掉哨兵
# 是一个有意识的「我确认这段收口了」的动作。
SKELETON_SENTINEL = "RELEASE-BLOCKER"

# 兜底：发布文本里不该有给开发者看的 HTML 注释（骨架脚手架、待办提示）。
# 这条不依赖任何约定措辞，所以万一开骨架时忘了写哨兵，只要脚手架注释还在就仍拦得住。
HTML_COMMENT_RE = re.compile(r"<!--")


def extract_section(changelog_text: str, version: str) -> str | None:
    """返回 version 对应的段落正文（不含标题行本身）；找不到返回 None。"""
    heading_re = re.compile(r"^## \[" + re.escape(version) + r"\].*$", re.MULTILINE)
    m = heading_re.search(changelog_text)
    if m is None:
        return None
    start = m.end()
    next_heading = ANY_VERSION_HEADING_RE.search(changelog_text, pos=start)
    end = next_heading.start() if next_heading else len(changelog_text)
    # 段末的 `---` 分隔线属于排版、不属于内容，去掉
    return changelog_text[start:end].strip().rstrip("-").strip()


def find_blockers(section: str) -> list[str]:
    """返回阻止本段落发布的理由；返回空列表表示可以发。"""
    blockers = []
    if SKELETON_SENTINEL in section:
        blockers.append(
            f"段落里还留着 {SKELETON_SENTINEL} 哨兵，说明它仍是开发骨架"
            "——发版前请写好摘要句、删掉哨兵注释块"
        )
    if HTML_COMMENT_RE.search(section):
        blockers.append(
            "段落里还有 HTML 注释（`<!--`）——那是给开发者看的脚手架，不该进 Release notes"
        )
    return blockers


def main() -> int:
    if len(sys.argv) != 2:
        print("用法：python3 scripts/extract_changelog_notes.py <version>", file=sys.stderr)
        return 1
    version = sys.argv[1]
    changelog_path = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    if not changelog_path.is_file():
        print(f"❌ 找不到 {changelog_path}", file=sys.stderr)
        return 1
    section = extract_section(changelog_path.read_text(encoding="utf-8"), version)
    if section is None:
        print(f"❌ CHANGELOG.md 中找不到版本 [{version}] 对应的段落", file=sys.stderr)
        return 1
    if not section:
        print(f"❌ CHANGELOG.md 中版本 [{version}] 对应的段落内容为空", file=sys.stderr)
        return 1
    blockers = find_blockers(section)
    if blockers:
        print(f"❌ CHANGELOG.md 中版本 [{version}] 的段落还不能发布：", file=sys.stderr)
        for reason in blockers:
            print(f"   - {reason}", file=sys.stderr)
        return 1
    print(section)
    return 0


if __name__ == "__main__":
    sys.exit(main())
