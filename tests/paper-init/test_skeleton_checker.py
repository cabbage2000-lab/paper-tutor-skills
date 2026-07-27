"""paper-init 骨架校验器的正反测试。

golden = 完全合规的单项目骨架（校验器不误报）；catches = 逐种红线违规各造一个
反例（校验器都能抓到）。正反两侧保证校验器有判别力、又不误伤合规产物——
这样即便 golden 是程序化构造的，校验器的价值也由违规样本独立背书。
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import skeleton_checker  # noqa: E402
from skeleton_checker import check_skeleton  # noqa: E402


def _make_golden(root) -> pathlib.Path:
    """程序化构造一个完全合规的单项目骨架。"""
    p = pathlib.Path(root) / "效率研究"
    for d in skeleton_checker.STANDARD_DIRS:
        (p / d).mkdir(parents=True)
    (p / "README.md").write_text(
        "# 效率研究\n本目录由 paper-init 于 2026-07-23 创建。\n", encoding="utf-8")
    (p / ".gitignore").write_text(
        "# 杂项\n.DS_Store\nliterature/pdfs/\n", encoding="utf-8")
    (p / "project.paper.yaml").write_text(
        'project_name: "效率研究"\ncreated_at: "2026-07-23"\ncreated_by: "paper-init"\n'
        'user_role: ""\ndiscipline: ""\ncurrent_stage: ""\n'
        'citation_style: ""\nlanguage_pref: ""\n', encoding="utf-8")
    return p


class TestSkeletonCheckerGolden(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = _make_golden(self.tmp.name)

    def test_golden_passes(self):
        self.assertEqual(check_skeleton(self.p), [], "完全合规的骨架不应有任何违规")

    def test_host_file_is_allowed(self):
        # CLAUDE.md 属骨架白名单（可选宿主文件），不应被当成多余产物
        (self.p / "CLAUDE.md").write_text("# 效率研究\nPaper 协作边界\n", encoding="utf-8")
        self.assertEqual(check_skeleton(self.p), [])


class TestSkeletonCheckerCatches(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p = _make_golden(self.tmp.name)

    def _assert_flag(self, needle):
        v = check_skeleton(self.p)
        self.assertTrue(any(needle in x for x in v),
                        f"应报含「{needle}」的违规，实际得到：{v}")

    def test_catches_prebuilt_paper_dir(self):
        (self.p / ".paper").mkdir()
        self._assert_flag(".paper")

    def test_catches_missing_standard_dir(self):
        shutil.rmtree(self.p / "submission")
        self._assert_flag("submission")

    def test_catches_skill_artifact_in_subdir(self):
        (self.p / "topic" / "RQ澄清记录.md").write_text("x", encoding="utf-8")
        self._assert_flag("非骨架文件")

    def test_catches_stray_top_level_file(self):
        (self.p / "draft.docx").write_text("x", encoding="utf-8")
        self._assert_flag("非骨架文件")

    def test_catches_gitignore_ignoring_paper(self):
        (self.p / ".gitignore").write_text("literature/pdfs/\n.paper/\n", encoding="utf-8")
        self._assert_flag(".paper")

    def test_catches_gitignore_ignoring_project_yaml(self):
        (self.p / ".gitignore").write_text(
            "literature/pdfs/\nproject.paper.yaml\n", encoding="utf-8")
        self._assert_flag("project.paper.yaml")

    def test_catches_gitignore_ignoring_data(self):
        (self.p / ".gitignore").write_text("literature/pdfs/\ndata/\n", encoding="utf-8")
        self._assert_flag("data")

    def test_catches_gitignore_missing_pdfs(self):
        (self.p / ".gitignore").write_text(".DS_Store\n", encoding="utf-8")
        self._assert_flag("pdfs")

    def test_catches_yaml_missing_field(self):
        (self.p / "project.paper.yaml").write_text(
            'created_by: "paper-init"\nuser_role: ""\n', encoding="utf-8")
        self._assert_flag("discipline")

    def test_catches_yaml_missing_created_by(self):
        (self.p / "project.paper.yaml").write_text(
            'user_role: ""\ndiscipline: ""\ncurrent_stage: ""\n'
            'citation_style: ""\nlanguage_pref: ""\n', encoding="utf-8")
        self._assert_flag("created_by")

    def test_catches_residual_angle_brackets_in_readme(self):
        (self.p / "README.md").write_text("# <项目名>\n未替换\n", encoding="utf-8")
        self._assert_flag("尖括号")

    def test_catches_residual_angle_brackets_in_yaml(self):
        (self.p / "project.paper.yaml").write_text(
            'project_name: "<项目名>"\ncreated_by: "paper-init"\n'
            'user_role: ""\ndiscipline: ""\ncurrent_stage: ""\n'
            'citation_style: ""\nlanguage_pref: ""\n', encoding="utf-8")
        self._assert_flag("尖括号")


if __name__ == "__main__":
    unittest.main()
