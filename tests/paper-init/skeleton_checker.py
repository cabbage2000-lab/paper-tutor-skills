"""paper-init 单项目骨架校验器。

把 tests/paper-init/README（脚手架行为验收清单·场景 1b 红线断言）里那批只读核查命令，
固化成可复用、可回归的自动化校验：输入一个 paper-init 产出的单项目骨架目录，
返回违规描述列表（空列表 = 完全合规）。将来 paper-init 端到端跑出真实产物后，
可直接调用本校验器自动核验红线，不必逐条手敲 shell。

依据：skills/paper-init/SKILL.md（四条红线、两种布局、.gitignore 与 project.paper.yaml 模板）。
纯标准库、只读目标目录、无副作用。工作区模式暂不覆盖（本版聚焦单项目骨架）。
"""
from __future__ import annotations

import pathlib
import re
from typing import List, Union

STANDARD_DIRS = ["topic", "literature", "data", "analysis",
                 "manuscript", "review", "submission"]
ALLOWED_TOP_FILES = {"README.md", ".gitignore", "project.paper.yaml",
                     "CLAUDE.md", "AGENTS.md"}
REQUIRED_YAML_FIELDS = ["user_role", "discipline", "current_stage",
                        "citation_style", "language_pref"]
# .gitignore 三条明文禁令（SKILL.md）：绝不忽略这三者
GITIGNORE_FORBIDDEN = {".paper", "data", "project.paper.yaml"}


def _has_angle_brackets(text: str) -> bool:
    """SKILL.md 自检约定：实例化后正文 `grep '[<>]'` 应为 0。"""
    return bool(re.search(r"[<>]", text))


def check_skeleton(project_dir: Union[str, pathlib.Path]) -> List[str]:
    """校验单项目骨架，返回违规描述列表（空 = 合规）。"""
    p = pathlib.Path(project_dir)
    v: List[str] = []

    if not p.is_dir():
        return [f"项目目录不存在：{p}"]

    # 红线：七个标准目录齐备
    for d in STANDARD_DIRS:
        if not (p / d).is_dir():
            v.append(f"缺少标准目录：{d}/")

    # 红线 2：严禁预建 .paper/
    if (p / ".paper").exists():
        v.append("红线违规：预建了 .paper/（应由各命令会话首次使用时创建）")

    # 红线 2：只建骨架——除顶层白名单外不得有任何文件（七目录应为空、无 skill 产物）
    for f in p.rglob("*"):
        if ".git" in f.parts:            # git 内部不计
            continue
        if not f.is_file():
            continue
        rel = f.relative_to(p)
        if len(rel.parts) == 1 and rel.name in ALLOWED_TOP_FILES:
            continue
        v.append(f"骨架含非骨架文件（疑为 skill 产物或多余文件）：{rel.as_posix()}")

    # .gitignore：忽略 literature/pdfs/，绝不忽略 .paper / data / project.paper.yaml
    gi = p / ".gitignore"
    if not gi.is_file():
        v.append("缺少 .gitignore")
    else:
        text = gi.read_text(encoding="utf-8")
        if "literature/pdfs/" not in text:
            v.append(".gitignore 未忽略 literature/pdfs/")
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.rstrip("/") in GITIGNORE_FORBIDDEN:
                v.append(f"红线违规：.gitignore 忽略了 {s}"
                         "（.paper/ data/ project.paper.yaml 必须随仓库入库）")

    # project.paper.yaml：created_by、五字段、无残留尖括号
    pac = p / "project.paper.yaml"
    if not pac.is_file():
        v.append("缺少 project.paper.yaml")
    else:
        text = pac.read_text(encoding="utf-8")
        if not re.search(r'created_by:\s*"?paper-init"?', text):
            v.append('project.paper.yaml 缺少 created_by: "paper-init"')
        for key in REQUIRED_YAML_FIELDS:
            if not re.search(rf"^\s*{re.escape(key)}\s*:", text, re.MULTILINE):
                v.append(f"project.paper.yaml 缺少字段：{key}")
        if _has_angle_brackets(text):
            v.append("project.paper.yaml 残留未替换的尖括号占位")

    # README.md：存在、无残留尖括号
    readme = p / "README.md"
    if not readme.is_file():
        v.append("缺少 README.md")
    elif _has_angle_brackets(readme.read_text(encoding="utf-8")):
        v.append("README.md 残留未替换的尖括号占位")

    return v
