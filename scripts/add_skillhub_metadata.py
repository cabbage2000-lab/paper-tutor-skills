#!/usr/bin/env python3
"""批量为所有 SKILL.md 添加 Skillhub 元数据。

读取元数据映射文件，为每个 skill 的 frontmatter 添加：
- slug: 与目录名相同
- displayName: 学术辅导·<功能名>
- version: 与 plugin.json 保持一致
- summary: 断链警告 + 一句话定位
"""
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPO_ROOT / "skills"
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"

# 元数据映射：skill 目录名 → (displayName, 一句话定位)
METADATA = {
    "paper-init": ("学术辅导·项目初始化", "为研究项目搭建标准科研工作目录的脚手架命令"),
    "paper-help": ("学术辅导·命令导航器", "帮你找到当下该用哪个 paper 命令"),
    "paper-doctor": ("学术辅导·环境体检", "检查 Paper 核验/检索环境就绪度"),
    "paper-daily": ("学术辅导·每日进展", "研究日志与进展追踪"),
    "paper-topic": ("学术辅导·选题澄清", "把模糊研究方向聚焦成研究问题"),
    "paper-search": ("学术辅导·文献检索", "多数据源文献检索与整理"),
    "paper-screen": ("学术辅导·系统综述", "PRISMA 2020 筛选台账与流程图"),
    "paper-method": ("学术辅导·研究设计", "方法-RQ 匹配检查与引导"),
    "paper-proposal": ("学术辅导·开题报告", "多源汇聚组装开题材料"),
    "paper-outline": ("学术辅导·大纲设计", "带文献锚点的章节大纲共写"),
    "paper-draft": ("学术辅导·正文共写", "基于大纲逐段起草正文初稿"),
    "paper-style": ("学术辅导·风格校准", "全文风格一致性与 AIGC 误判申诉"),
    "paper-logic": ("学术辅导·论证检查", "RQ-方法-结果-结论四要素结构对应"),
    "paper-anchor": ("学术辅导·支撑补齐", "论断与文献支撑对照器"),
    "paper-abstract": ("学术辅导·摘要提炼", "从正文提炼摘要与关键词"),
    "paper-import": ("学术辅导·题录导入", "题录整理与草稿引用一致性核对"),
    "paper-figure": ("学术辅导·图表诊断", "图表类/图注/配色/工具陈列"),
    "paper-plot": ("学术辅导·绘图代码", "生成 matplotlib/ggplot2 绘图代码"),
    "paper-verify": ("学术辅导·引用核验", "引用存在性核验与格式检查"),
    "paper-review": ("学术辅导·模拟评审", "多视角模拟审稿意见"),
    "paper-revise": ("学术辅导·修订辅助", "修订建议对照表与回复信起草"),
    "paper-disclose": ("学术辅导·AI披露", "汇编 AI 使用说明"),
    "paper-submit": ("学术辅导·投稿准备", "投稿材料清单与期刊要求陈列"),
    "paper-typeset": ("学术辅导·出版转换", "Markdown 转 LaTeX/DOCX/PDF"),
}


def parse_frontmatter(text: str) -> tuple[dict, str, str]:
    """解析 frontmatter，返回 (元数据字典, frontmatter原文, 正文)。"""
    m = re.match(r"^(---\n.*?\n---\n)(.*)", text, re.DOTALL)
    if not m:
        return {}, "", text
    fm_text = m.group(1)
    body = m.group(2)

    # 解析 frontmatter 字段
    fm = {}
    for line in fm_text.splitlines()[1:-1]:  # 跳过首尾的 ---
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            fm[key.strip()] = value.strip()

    return fm, fm_text, body


def add_skillhub_metadata(skill_dir: Path, version: str) -> bool:
    """为单个 SKILL.md 添加 Skillhub 元数据。返回是否成功。"""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return False

    text = skill_md.read_text(encoding="utf-8")
    fm, fm_text, body = parse_frontmatter(text)

    # 检查是否已有 Skillhub 元数据
    if "slug" in fm:
        print(f"  ⏭️  {skill_dir.name}: 已有 slug 字段，跳过")
        return False

    # 获取元数据
    display_name, summary_suffix = METADATA.get(skill_dir.name, (None, None))
    if not display_name:
        print(f"  ⚠️  {skill_dir.name}: 未在元数据映射中找到，跳过")
        return False

    # 构建 summary
    summary = f"学术辅导套件的一员，需与其他 paper-* skill 同级安装。{summary_suffix}。"

    # 构建新的 frontmatter
    new_fm_lines = [fm_text.rstrip(" \n")]
    new_fm_lines.append(f"slug: {skill_dir.name}")
    new_fm_lines.append(f"displayName: {display_name}")
    new_fm_lines.append(f"version: {version}")
    new_fm_lines.append(f"summary: {summary}")
    new_fm_text = "\n".join(new_fm_lines) + "\n---\n"

    # 写回文件
    new_text = new_fm_text + body
    skill_md.write_text(new_text, encoding="utf-8")
    print(f"  ✅ {skill_dir.name}: 已添加 Skillhub 元数据")
    return True


def main():
    # 加载 plugin.json 获取版本号
    if not PLUGIN_JSON.exists():
        print(f"❌ {PLUGIN_JSON} 不存在")
        return

    plugin = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
    version = plugin.get("version")
    print(f"当前版本：{version}\n")

    # 遍历所有 skill 目录
    print("开始添加 Skillhub 元数据...\n")
    updated_count = 0
    for skill_dir in sorted(SKILLS_ROOT.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
            continue
        if add_skillhub_metadata(skill_dir, version):
            updated_count += 1

    print(f"\n✅ 完成！共更新 {updated_count} 个 SKILL.md 文件")


if __name__ == "__main__":
    main()
