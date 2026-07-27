#!/usr/bin/env python3
"""
check_templates.py — Paper-Tutor-Skills 报告模板结构校验
====================================================================
扫描 skills/paper-*/references/报告样式模板.html + 样例.html，
按设计稿 §7.2 的 9 项检查 PASS/FAIL。

用法：
    python skills/_shared/scripts/check_templates.py

退出码：全 PASS → 0；有 FAIL → 1。
纯标准库（re + pathlib），无第三方依赖。
"""

import re
import sys
from pathlib import Path

# 项目根（脚本位于 skills/_shared/scripts/，往上 3 级）
ROOT = Path(__file__).resolve().parent.parent.parent.parent
SKILLS = ROOT / "skills"

# 需要 ECharts 的 skill（设计稿 §4.2：目前仅 review）
ECHARTS_SKILLS = {"paper-review"}

# 13 个有报告模板的 skill
TEMPLATE_SKILLS = sorted(
    d.name for d in SKILLS.iterdir()
    if d.is_dir() and (d / "references" / "报告样式模板.html").exists()
)


def check_basic(template: str) -> dict:
    """检查全 13 模板必备的 6 项（#1-#6）。"""
    return {
        "#1 Tailwind CDN":      "cdn.tailwindcss.com" in template,
        "#2 typography 插件":    "plugins=typography" in template,
        "#3 tailwind.config.js": "../../_shared/tailwind.config.js" in template,
        "#4 设计底线 5 条":      bool(re.search(r"设计底线.*1\..*2\..*3\..*4\..*5\.", template, re.DOTALL)),
        "#5 四层色 utility":     all(cls in template for cls in ["text-l1", "bg-l1-bg"]),
        "#6 样例.html 存在":     True,  # 在 caller 里单独检查文件存在
    }


def check_echarts(template: str) -> dict:
    """检查仅 review 必备的 3 项（#7-#9）。"""
    return {
        "#7 ECharts CDN":        "echarts.min.js" in template,
        "#8 echarts-theme.js":   "../../_shared/echarts-theme.js" in template,
        "#9 雷达容器":            'id="reviewRadar"' in template,
    }


def main() -> int:
    total_pass = 0
    total_fail = 0

    for skill in TEMPLATE_SKILLS:
        tpl_path = SKILLS / skill / "references" / "报告样式模板.html"
        sample_path = SKILLS / skill / "references" / "样例.html"
        template = tpl_path.read_text(encoding="utf-8")

        results = check_basic(template)
        results["#6 样例.html 存在"] = sample_path.exists()

        if skill in ECHARTS_SKILLS:
            results.update(check_echarts(template))

        passed = sum(results.values())
        total = len(results)
        status = "PASS" if passed == total else "FAIL"
        if status == "PASS":
            total_pass += 1
        else:
            total_fail += 1
            failed_names = [k for k, v in results.items() if not v]
            print(f"[{status}] {skill:<20} {passed}/{total}  — missing: {', '.join(failed_names)}")
            continue
        print(f"[{status}] {skill:<20} {passed}/{total}")

    print(f"\nSummary: {total_pass}/{total_pass + total_fail} skills PASS")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
