#!/usr/bin/env python3
"""校验本仓库的结构完整性：skills/ 内容质量 + plugin 清单一致性 + 仓库健康。

skill 结构检查（validate）：
1. 每个 skill 目录含 SKILL.md，frontmatter 的 name 与目录名一致、description ≥ 50 字符
2. description ≤ 1024 字符（Claude Code 对 frontmatter description 的硬限制）
3. frontmatter 仅含白名单字段（防手误写入无效字段被静默忽略）
4. SKILL.md ≤ 500 行（渐进披露预算：超限内容应下沉到 references/）
5. 所有 .md 文件不含占位符（TBD/TODO/FIXME/XXX/待补充/占位）
6. 所有 .md 中引用的 references/ 相对路径（含多级 ../ 跨 skill）都存在
7. references/ 及其子目录下每个 .md 实质内容 ≥ 500 字节

SkillHub 元数据检查（validate_skillhub_metadata）：
8. 每个 SKILL.md 的 frontmatter 含 slug / displayName / version / summary
9. slug 必须与目录名逐字相同（CLI 安装落盘为 <install_root>/<slug>/）
10. version 必须与 .claude-plugin/plugin.json 的 version 一致
11. displayName 必须以「学术辅导」开头

plugin 清单检查（validate_manifests）：两个宿主各要一套清单，格式不同不能合并，
只能各写一份 + 在此守住四份不背离（同一份元数据抄四处，必然漂移）：
12. 四份清单都存在且可解析——Claude Code 读 .claude-plugin/{plugin,marketplace}.json，
   Codex 读 .codex-plugin/plugin.json + .agents/plugins/marketplace.json
13. 四份清单的 name / version / description / license 一致
14. 各宿主专有字段合规：Codex 的 skills 指针指向 ./skills/、interface 必填字段齐全

仓库健康检查（validate_repo_health）：
15. .gitignore 不得忽略 .claude-plugin / .codex-plugin / .agents
16. 两个 .*-plugin/ 目录只放清单文件——skills/ 必须在仓库根

用法：python3 scripts/validate_skills.py [skills_root]
"""
import json
import re
import sys
from pathlib import Path

# 占位符模式：只匹配独立的占位符标记，不匹配「标占位」「占位符」等合法用词
PLACEHOLDER_PATTERNS = [
    r"\bTBD\b", r"\bTODO\b", r"\bFIXME\b", r"\bXXX\b",
    r"\b待补充\b",
]
MIN_DESCRIPTION_LEN = 50
MAX_DESCRIPTION_LEN = 1024
MAX_SKILL_MD_LINES = 500
MIN_REFERENCE_BYTES = 500

# 四个宿主会读取的 frontmatter 字段之并集；并集外的字段处处被静默忽略，写了等于埋雷。
# 前 7 个是 Claude Code / Codex / WorkBuddy 读的；后 3 个是 SkillHub 发布必填/建议项
# （slug 与 displayName 缺失会被 `skillhub publish` 直接拒绝），对其余宿主无副作用。
ALLOWED_FRONTMATTER_KEYS = {
    "name", "description", "version", "license", "allowed-tools",
    "compatibility", "metadata",
    "slug", "displayName", "summary",
}

# 匹配 markdown 链接中的路径：[text](path) 或 `path`
# 只匹配括号内的路径，不匹配反引号中的显示文本
REF_LINK_RE = re.compile(r"\]\(((?:\.\./)*(?:[\w-]+/)*references/[\w./-]+?\.md)\)")

# 各宿主的 plugin 清单里必须逐字一致的字段（同一个 plugin 分两处发行，元信息只有一份事实）
MIRRORED_FIELDS = ("name", "version", "description", "license")

# Codex 官方摄取校验（plugin-creator/validate_plugin.py）要求的 interface 必填字段
CODEX_INTERFACE_REQUIRED = (
    "displayName", "shortDescription", "longDescription", "developerName",
    "category", "capabilities", "defaultPrompt",
)

# 分发清单所在目录：被 .gitignore 掉就等于没发布，且新增清单文件会静默丢失
MANIFEST_DIRS = (".claude-plugin", ".codex-plugin", ".agents")

# 各 .*-plugin/ 目录允许出现的文件——skills/ 必须留在仓库根（plugin 根）
MANIFEST_DIR_ALLOWED = {
    ".claude-plugin": {"plugin.json", "marketplace.json"},
    ".codex-plugin": {"plugin.json"},
}


def parse_frontmatter(text: str) -> dict | None:
    """解析 YAML frontmatter（简化版，不引入第三方依赖）。

    支持 YAML 多行字符串格式：>- (折叠换行) 和 | (保留换行)。
    """
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return None
    fm = {}
    current_key = None
    current_value = []
    multiline_mode = None  # None, '>-', '|'

    for line in m.group(1).splitlines():
        # 检查是否是新字段
        if ":" in line and not line.startswith((" ", "\t")):
            # 保存上一个字段
            if current_key:
                if multiline_mode:
                    # 多行字符串：合并行
                    if multiline_mode == ">-":
                        fm[current_key] = " ".join(current_value).strip()
                    else:  # '|'
                        fm[current_key] = "\n".join(current_value).strip()
                else:
                    fm[current_key] = " ".join(current_value).strip()

            # 开始新字段
            key, value = line.split(":", 1)
            current_key = key.strip()
            value = value.strip()

            # 检查是否是多行字符串标记
            if value in (">-", "|", ">", "|+"):
                multiline_mode = value
                current_value = []
            else:
                multiline_mode = None
                current_value = [value] if value else []
        elif current_key and (line.startswith("  ") or line.startswith("\t")):
            # 多行字符串的续行
            current_value.append(line.strip())

    # 保存最后一个字段
    if current_key:
        if multiline_mode:
            if multiline_mode == ">-":
                fm[current_key] = " ".join(current_value).strip()
            else:
                fm[current_key] = "\n".join(current_value).strip()
        else:
            fm[current_key] = " ".join(current_value).strip()

    return fm


def check_skill_md(skill_dir: Path, errors: list[str]) -> None:
    """校验单个 skill 的 SKILL.md 结构与内容。"""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        errors.append(f"{skill_dir.name}: 缺少 SKILL.md")
        return

    text = skill_md.read_text(encoding="utf-8")
    lines = text.splitlines()

    # 行数预算
    if len(lines) > MAX_SKILL_MD_LINES:
        errors.append(
            f"{skill_dir.name}/SKILL.md: {len(lines)} 行，超出预算 {MAX_SKILL_MD_LINES} "
            f"行——详细内容应下沉到 references/"
        )

    fm = parse_frontmatter(text)
    if fm is None:
        errors.append(f"{skill_dir.name}/SKILL.md: 无可解析的 frontmatter")
        return

    # name 必须等于目录名
    if fm.get("name") != skill_dir.name:
        errors.append(
            f"{skill_dir.name}/SKILL.md: frontmatter name={fm.get('name')!r} "
            f"与目录名不一致"
        )

    # description 长度
    desc = fm.get("description", "")
    if len(desc) < MIN_DESCRIPTION_LEN:
        errors.append(
            f"{skill_dir.name}/SKILL.md: description 过短（{len(desc)} 字符），"
            f"至少 {MIN_DESCRIPTION_LEN} 字符"
        )
    if len(desc) > MAX_DESCRIPTION_LEN:
        errors.append(
            f"{skill_dir.name}/SKILL.md: description 超长（{len(desc)} 字符），"
            f"上限 {MAX_DESCRIPTION_LEN} 字符"
        )

    # frontmatter 字段白名单
    unknown_keys = set(fm.keys()) - ALLOWED_FRONTMATTER_KEYS
    if unknown_keys:
        errors.append(
            f"{skill_dir.name}/SKILL.md: 未知 frontmatter 字段 {sorted(unknown_keys)}，"
            f"允许字段：{sorted(ALLOWED_FRONTMATTER_KEYS)}"
        )


def check_references(skill_dir: Path, skills_root: Path, errors: list[str]) -> None:
    """校验 skill 内所有 .md 文件的 references/ 引用与 references/ 目录内容。"""
    for md_file in skill_dir.rglob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        # 占位符检查
        for pattern in PLACEHOLDER_PATTERNS:
            if re.search(pattern, text):
                errors.append(f"{md_file.relative_to(skills_root)}: 含占位符 {pattern!r}")

        # 引用路径检查：相对于当前文件所在目录解析
        for ref_path in REF_LINK_RE.findall(text):
            # 先尝试从当前文件位置解析
            resolved = (md_file.parent / ref_path).resolve()
            if resolved.is_file():
                continue

            # 跨 skill 引用（../paper-xxx/references/...）从 skills/ 根解析
            if ref_path.startswith("../"):
                # 去掉前导的 ../，从 skills/ 根开始解析
                relative_path = re.sub(r"^\.\./", "", ref_path)
                alt_resolved = (skills_root / relative_path).resolve()
                if alt_resolved.is_file():
                    continue

            errors.append(
                f"{md_file.relative_to(skills_root)}: 引用不存在的路径 {ref_path!r}"
            )

    # references/ 目录内容检查
    ref_dir = skill_dir / "references"
    if ref_dir.is_dir():
        for ref_file in ref_dir.rglob("*.md"):
            if ref_file.stat().st_size < MIN_REFERENCE_BYTES:
                errors.append(
                    f"{ref_file.relative_to(skills_root)}: 实质内容不足 "
                    f"{MIN_REFERENCE_BYTES} 字节"
                )


def validate_skillhub_metadata(
    skills_root: Path, plugin: dict, errors: list[str]
) -> None:
    """校验 SkillHub 元数据：slug / displayName / version / summary。

    SkillHub 把版本号读在每个 SKILL.md 里，等于版本真相多了 24 个副本。
    本函数把这 24 处钉在 plugin.json 的 version 上，让漏升变成校验失败。
    """
    expected_version = plugin.get("version")
    if not skills_root.is_dir():
        return

    for skill_dir in sorted(d for d in skills_root.iterdir() if d.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue

        fm = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        if fm is None:
            continue

        # slug 必须与目录名相同
        slug = fm.get("slug")
        if slug != skill_dir.name:
            errors.append(
                f"{skill_dir.name}/SKILL.md: slug={slug!r} 与目录名不一致"
                f"（SkillHub CLI 安装落盘为 <install_root>/<slug>/，"
                f"只有 slug 与目录名一致，跨 skill 引用才解析得到）"
            )

        # displayName 必须以「学术辅导」开头
        display_name = fm.get("displayName", "")
        if not display_name.startswith("学术辅导"):
            errors.append(
                f"{skill_dir.name}/SKILL.md: displayName={display_name!r} "
                f"未以「学术辅导」开头（这是 SkillHub 唯一的检索杠杆）"
            )

        # version 必须与 plugin.json 一致
        version = fm.get("version")
        if version != expected_version:
            errors.append(
                f"{skill_dir.name}/SKILL.md: version={version!r} 与 plugin.json 的 "
                f"{expected_version!r} 不一致（发版时所有 SKILL.md 需一起升版）"
            )

        # summary 必须存在
        summary = fm.get("summary", "")
        if not summary:
            errors.append(
                f"{skill_dir.name}/SKILL.md: 缺 summary 字段"
                f"（SkillHub 建议填写，平台卡片可能展示）"
            )


def validate_manifests(repo_root: Path, plugin: dict) -> list[str]:
    """校验两个宿主的四份 plugin 清单。"""
    errors: list[str] = []

    # Claude Code 侧两份
    claude_plugin = _load_json(
        repo_root / ".claude-plugin" / "plugin.json", errors,
        ".claude-plugin/plugin.json"
    )
    claude_market = _load_json(
        repo_root / ".claude-plugin" / "marketplace.json", errors,
        ".claude-plugin/marketplace.json"
    )

    # Codex 侧两份
    codex_plugin = _load_json(
        repo_root / ".codex-plugin" / "plugin.json", errors,
        ".codex-plugin/plugin.json"
    )
    codex_market = _load_json(
        repo_root / ".agents" / "plugins" / "marketplace.json", errors,
        ".agents/plugins/marketplace.json"
    )

    if not all([claude_plugin, claude_market, codex_plugin, codex_market]):
        return errors

    # 跨清单字段一致性
    for field in MIRRORED_FIELDS:
        if claude_plugin.get(field) != plugin.get(field):
            errors.append(
                f".claude-plugin/plugin.json 的 {field} 与 plugin.json 的 "
                f"{plugin.get(field)!r} 不一致"
            )
        if claude_market.get("plugins", [{}])[0].get(field) != plugin.get(field):
            errors.append(
                f".claude-plugin/marketplace.json 的 {field} 与 plugin.json 的 "
                f"{plugin.get(field)!r} 不一致"
            )
        if codex_plugin.get(field) != plugin.get(field):
            errors.append(
                f".codex-plugin/plugin.json 的 {field} 与 plugin.json 的 "
                f"{plugin.get(field)!r} 不一致"
            )

    # Codex 专有字段
    if codex_plugin.get("skills") != "./skills/":
        errors.append(
            f".codex-plugin/plugin.json: skills 指针为 {codex_plugin.get('skills')!r}，"
            f"应为 './skills/'"
        )

    interface = codex_plugin.get("interface", {})
    for field in CODEX_INTERFACE_REQUIRED:
        if field not in interface:
            errors.append(
                f".codex-plugin/plugin.json: interface 缺必填字段 {field!r}"
            )

    return errors


def validate_repo_health(repo_root: Path) -> list[str]:
    """校验仓库健康：分发清单不被忽略、清单目录只放清单文件。"""
    errors: list[str] = []

    # .gitignore 检查
    gitignore = repo_root / ".gitignore"
    if gitignore.is_file():
        gitignore_text = gitignore.read_text(encoding="utf-8")
        for manifest_dir in MANIFEST_DIRS:
            if manifest_dir in gitignore_text:
                errors.append(
                    f".gitignore 忽略了 {manifest_dir}/——分发清单必须入库，"
                    f"否则 plugin 装不出去"
                )

    # 清单目录内容检查（只检查 .*-plugin 目录，不检查 .agents）
    for manifest_dir in [d for d in MANIFEST_DIRS if d.endswith("-plugin")]:
        manifest_path = repo_root / manifest_dir
        if manifest_path.is_dir():
            allowed = MANIFEST_DIR_ALLOWED.get(manifest_dir, set())
            for item in manifest_path.iterdir():
                if item.name not in allowed:
                    errors.append(
                        f"{manifest_dir}/{item.name}: 不允许出现在清单目录——"
                        f"skills/ 必须在仓库根（plugin 根），塞进清单目录会导致"
                        f"一个 skill 都加载不到"
                    )

    return errors


def _load_json(path: Path, errors: list[str], label: str) -> dict | None:
    """加载 JSON 文件，失败时记录错误并返回 None。"""
    if not path.is_file():
        errors.append(f"{label}: 文件不存在")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"{label}: JSON 解析失败——{e}")
        return None


def validate(skills_root: Path) -> list[str]:
    """校验 skills/ 目录的结构完整性。"""
    errors: list[str] = []
    if not skills_root.is_dir():
        errors.append(f"{skills_root}: 目录不存在")
        return errors

    for skill_dir in sorted(d for d in skills_root.iterdir() if d.is_dir()):
        if skill_dir.name.startswith("_"):
            continue  # 跳过 _shared 等非 skill 目录
        check_skill_md(skill_dir, errors)
        check_references(skill_dir, skills_root, errors)

    return errors


def main():
    repo_root = Path(__file__).resolve().parents[1]
    skills_root = repo_root / "skills"

    if len(sys.argv) > 1:
        skills_root = Path(sys.argv[1])

    print(f"校验目录：{skills_root}")
    errors = validate(skills_root)

    # 加载 plugin.json 用于 SkillHub 元数据校验
    plugin_path = repo_root / ".claude-plugin" / "plugin.json"
    if plugin_path.is_file():
        plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
        validate_skillhub_metadata(skills_root, plugin, errors)
        errors.extend(validate_manifests(repo_root, plugin))
    else:
        errors.append(f"{plugin_path}: 文件不存在")

    errors.extend(validate_repo_health(repo_root))

    if errors:
        print(f"\n发现 {len(errors)} 个错误：\n")
        for error in errors:
            print(f"  ❌ {error}")
        sys.exit(1)
    else:
        print("\n✅ 所有校验通过")


if __name__ == "__main__":
    main()
