#!/usr/bin/env python3
"""批量发布所有 paper-* skill 到 SkillHub。

注意：
- 发布限频约每分钟 3 次，连发后报 429 需隔 80 秒重试
- 需要先在浏览器完成实名认证和创建 API Token
"""
import subprocess
import sys
import time
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"

# 24 个要发布的 skill（按字母顺序）
SKILLS_TO_PUBLISH = [
    "paper-abstract",
    "paper-anchor",
    "paper-daily",
    "paper-disclose",
    "paper-doctor",
    "paper-draft",
    "paper-figure",
    "paper-help",
    "paper-import",
    "paper-init",
    "paper-logic",
    "paper-method",
    "paper-outline",
    "paper-plot",
    "paper-proposal",
    "paper-review",
    "paper-revise",
    "paper-screen",
    "paper-search",
    "paper-style",
    "paper-submit",
    "paper-topic",
    "paper-typeset",
    "paper-verify",
]


def publish_skill(skill_name: str, dry_run: bool = False) -> bool:
    """发布单个 skill 到 SkillHub。返回是否成功。"""
    skill_path = SKILLS_ROOT / skill_name
    if not skill_path.is_dir():
        print(f"  ❌ {skill_name}: 目录不存在")
        return False

    cmd = ["skillhub", "publish", str(skill_path)]
    if dry_run:
        cmd.append("--dry-run")

    print(f"  发布 {skill_name}...")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"  ✅ {skill_name}: 发布成功")
        return True
    else:
        print(f"  ❌ {skill_name}: 发布失败")
        print(f"     stdout: {result.stdout}")
        print(f"     stderr: {result.stderr}")
        return False


def main():
    dry_run = "--dry-run" in sys.argv

    print(f"开始{'预检' if dry_run else '发布'} {len(SKILLS_TO_PUBLISH)} 个 skill...\n")

    success_count = 0
    failed_skills = []

    for i, skill_name in enumerate(SKILLS_TO_PUBLISH, 1):
        print(f"[{i}/{len(SKILLS_TO_PUBLISH)}]", end="")
        if publish_skill(skill_name, dry_run=dry_run):
            success_count += 1
        else:
            failed_skills.append(skill_name)

        # 限频：每 3 个暂停 80 秒（避免 429 错误）
        if i % 3 == 0 and i < len(SKILLS_TO_PUBLISH) and not dry_run:
            print(f"\n  ⏸️  已发布 {i} 个，暂停 80 秒避免限频...\n")
            time.sleep(80)

    print(f"\n{'='*60}")
    print(f"{'预检' if dry_run else '发布'}完成！")
    print(f"  成功：{success_count}/{len(SKILLS_TO_PUBLISH)}")
    if failed_skills:
        print(f"  失败：{', '.join(failed_skills)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
