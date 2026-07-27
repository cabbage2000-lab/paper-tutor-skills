"""paper-verify scripts/format_check.py 确定性单测——5 类 GB/T 7714 扣分项。"""
from __future__ import annotations

import pathlib
import sys
import unittest

_REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "skills" / "_shared"))
sys.path.insert(0, str(_REPO / "skills" / "paper-verify" / "scripts"))

import format_check  # noqa: E402
import parse_refs  # noqa: E402


def _cats(issues):
    return [i.category for i in issues]


class TestFormatCheck(unittest.TestCase):
    def test_well_formed_no_issues(self):
        text = "[1] Smith, J. AI in Education[J]. Journal of Tech, 2020, 15(3): 100-115. DOI: 10.1/x"
        self.assertEqual(format_check.check_format("r1", text), [])

    def test_missing_type_tag(self):
        text = "[1] Smith, J. AI in Education. Journal of Tech, 2020, 15(3): 100-115."
        self.assertIn("type_tag", _cats(format_check.check_format("r1", text)))

    def test_fullwidth_punctuation_flagged(self):
        text = "[1] Smith，J. AI in Education[J]. 学报，2020，15(3): 100-115."
        self.assertIn("punctuation", _cats(format_check.check_format("r1", text)))

    def test_halfwidth_punctuation_ok(self):
        text = "[1] Smith, J. AI in Education[J]. Journal, 2020, 15(3): 100-115."
        self.assertNotIn("punctuation", _cats(format_check.check_format("r1", text)))

    def test_eb_ol_missing_access_date(self):
        text = "[2] Some Online Resource[EB/OL]. https://example.com. DOI: 10.1/y"
        self.assertIn("eb_ol", _cats(format_check.check_format("r1", text)))

    def test_eb_ol_with_access_date_ok(self):
        text = "[2] Some Online Resource[EB/OL]. [2026-07-25]. https://example.com."
        self.assertNotIn("eb_ol", _cats(format_check.check_format("r1", text)))

    def test_authors_four_without_et_al(self):
        parsed = parse_refs.ParsedRef(id="r1", authors=["Smith, Jones, Brown, White"])
        text = "[1] Smith, Jones, Brown, White. Title[J]. J, 2020, 1(1): 1-9."
        self.assertIn("authors", _cats(format_check.check_format("r1", text, parsed=parsed)))

    def test_authors_three_ok(self):
        parsed = parse_refs.ParsedRef(id="r1", authors=["Smith, Jones, Brown"])
        text = "[1] Smith, Jones, Brown. Title[J]. J, 2020, 1(1): 1-9."
        self.assertNotIn("authors", _cats(format_check.check_format("r1", text, parsed=parsed)))

    def test_journal_missing_pages(self):
        text = "[1] Smith, J. Title[J]. Journal, 2020."
        self.assertIn("pages", _cats(format_check.check_format("r1", text)))

    def test_journal_with_pages_ok(self):
        text = "[1] Smith, J. Title[J]. Journal, 2020, 15(3): 100-115."
        self.assertNotIn("pages", _cats(format_check.check_format("r1", text)))

    def test_every_issue_carries_clause_and_suggestion(self):
        # 每条 issue 必须带国标条款 + 规范化示例（spec §10.2）
        text = "[1] Smith，J. Title. Journal, 2020."
        for issue in format_check.check_format("r1", text):
            self.assertTrue(issue.clause)
            self.assertTrue(issue.suggestion)

    def test_check_all_batch(self):
        items = [
            ("r1", "[1] Smith, J. Title[J]. J, 2020, 1(1): 1-9.", None),
            ("r2", "[2] No Type Tag Here. Journal, 2020.", None),
        ]
        all_issues = format_check.check_all(items)
        self.assertEqual([i.ref_id for i in all_issues if i.category == "type_tag"], ["r2"])


if __name__ == "__main__":
    unittest.main()
