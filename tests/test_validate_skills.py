"""validate_skills.py 的单元测试。

测试校验脚本的核心功能：
1. frontmatter 字段白名单校验
2. SkillHub 元数据校验（slug / displayName / version / summary）
3. 版本一致性校验
4. SKILL.md 基础结构校验
"""
from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

# 导入被测试的脚本
import sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from validate_skills import (  # noqa: E402
    validate,
    validate_skillhub_metadata,
    ALLOWED_FRONTMATTER_KEYS,
)


def make_skill(
    root: pathlib.Path,
    name: str,
    *,
    frontmatter_name: str | None = None,
    description: str = "这是一段足够长的描述文字，超过五十个字符，用于通过校验脚本的最小长度检查。",
    body: str = "# 正文\n内容充实。\n",
    extra_frontmatter: str = "",
    version: str = "0.1.8",
) -> pathlib.Path:
    """创建一个测试用的 skill 目录和 SKILL.md。"""
    d = root / name
    (d / "references").mkdir(parents=True, exist_ok=True)
    fm_name = frontmatter_name if frontmatter_name is not None else name
    (d / "SKILL.md").write_text(
        f"---\nname: {fm_name}\ndescription: {description}\n"
        f"{extra_frontmatter}---\n\n{body}",
        encoding="utf-8",
    )
    return d


def make_plugin_json(root: pathlib.Path, version: str = "0.1.8") -> None:
    """创建测试用的 plugin.json。"""
    plugin_dir = root / ".claude-plugin"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({
            "name": "test-plugin",
            "version": version,
            "description": "测试 plugin",
            "license": "MIT"
        }),
        encoding="utf-8",
    )


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class ValidateSkillsTest(TempDirTest):
    """测试基础的 SKILL.md 校验。"""

    def test_valid_skill_passes(self):
        """合法的 skill 应该通过校验。"""
        make_skill(
            self.root, "good-skill",
            description="这是一段足够长的描述文字，必须超过五十个字符才能通过校验脚本的最小长度检查要求，所以现在继续添加更多文字。",
            body="# 说明\n详见 [规范](references/style.md)。\n"
        )
        (self.root / "good-skill" / "references" / "style.md").write_text(
            "# 规范\n" + "实质内容。" * 100, encoding="utf-8"
        )
        errors = validate(self.root)
        self.assertEqual(errors, [])

    def test_missing_skill_md(self):
        """缺少 SKILL.md 应该报错。"""
        (self.root / "empty-skill").mkdir()
        errors = validate(self.root)
        self.assertTrue(any("缺少 SKILL.md" in e for e in errors))

    def test_frontmatter_name_mismatch(self):
        """frontmatter name 与目录名不一致应该报错。"""
        make_skill(self.root, "skill-a", frontmatter_name="skill-b")
        errors = validate(self.root)
        self.assertTrue(any("与目录名不一致" in e for e in errors))

    def test_short_description_rejected(self):
        """description 过短应该报错。"""
        make_skill(self.root, "skill-a", description="太短")
        errors = validate(self.root)
        self.assertTrue(any("过短" in e for e in errors))

    def test_overlong_description_rejected(self):
        """description 超长应该报错。"""
        make_skill(self.root, "skill-a", description="长" * 1025)
        errors = validate(self.root)
        self.assertTrue(any("超长" in e for e in errors))

    def test_unknown_frontmatter_key_rejected(self):
        """未知 frontmatter 字段应该报错。"""
        make_skill(self.root, "skill-a", extra_frontmatter="trigger: always\n")
        errors = validate(self.root)
        self.assertTrue(any("未知 frontmatter 字段" in e for e in errors))


class ValidateSkillhubMetadataTest(TempDirTest):
    """测试 SkillHub 元数据校验。"""

    def test_valid_metadata_passes(self):
        """合法的 SkillHub 元数据应该通过校验。"""
        make_skill(
            self.root, "paper-init",
            extra_frontmatter=(
                "slug: paper-init\n"
                "displayName: 学术辅导·项目初始化\n"
                "version: 0.1.8\n"
                "summary: 学术辅导套件的一员\n"
            ),
        )
        make_plugin_json(self.root, "0.1.8")
        plugin = json.loads((self.root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        errors = []
        validate_skillhub_metadata(self.root / "skills" if (self.root / "skills").exists() else self.root, plugin, errors)
        self.assertEqual(errors, [])

    def test_slug_mismatch_detected(self):
        """slug 与目录名不一致应该报错。"""
        make_skill(
            self.root, "paper-init",
            extra_frontmatter="slug: wrong-name\n",
        )
        make_plugin_json(self.root)
        plugin = json.loads((self.root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        errors = []
        validate_skillhub_metadata(self.root, plugin, errors)
        self.assertTrue(any("slug" in e and "与目录名不一致" in e for e in errors))

    def test_display_name_without_prefix_detected(self):
        """displayName 未以「学术辅导」开头应该报错。"""
        make_skill(
            self.root, "paper-init",
            extra_frontmatter="displayName: 错误的名字\n",
        )
        make_plugin_json(self.root)
        plugin = json.loads((self.root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        errors = []
        validate_skillhub_metadata(self.root, plugin, errors)
        self.assertTrue(any("displayName" in e and "未以「学术辅导」开头" in e for e in errors))

    def test_version_mismatch_detected(self):
        """version 与 plugin.json 不一致应该报错。"""
        make_skill(
            self.root, "paper-init",
            extra_frontmatter="version: 0.1.7\n",
        )
        make_plugin_json(self.root, "0.1.8")
        plugin = json.loads((self.root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        errors = []
        validate_skillhub_metadata(self.root, plugin, errors)
        self.assertTrue(any("version" in e and "不一致" in e for e in errors))

    def test_missing_summary_detected(self):
        """缺少 summary 字段应该报错。"""
        make_skill(
            self.root, "paper-init",
            extra_frontmatter="slug: paper-init\n",
        )
        make_plugin_json(self.root)
        plugin = json.loads((self.root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        errors = []
        validate_skillhub_metadata(self.root, plugin, errors)
        self.assertTrue(any("缺 summary" in e for e in errors))


class AllowedFrontmatterKeysTest(unittest.TestCase):
    """测试 frontmatter 白名单。"""

    def test_skillhub_keys_in_allowed_set(self):
        """SkillHub 必需的字段应该在白名单中。"""
        required_keys = {"slug", "displayName", "version", "summary"}
        self.assertTrue(required_keys.issubset(ALLOWED_FRONTMATTER_KEYS))

    def test_standard_keys_in_allowed_set(self):
        """标准字段应该在白名单中。"""
        standard_keys = {"name", "description", "license"}
        self.assertTrue(standard_keys.issubset(ALLOWED_FRONTMATTER_KEYS))


if __name__ == "__main__":
    unittest.main()
