#!/usr/bin/env python3
"""Validate the five-entry distribution using only the standard library."""
from __future__ import annotations

import re
import sys
from pathlib import Path


def registry_names(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    names = re.findall(r"^- name: (paper-[a-z]+)$", text, re.M)
    if not names or len(names) != len(set(names)):
        raise ValueError(f"Empty or duplicate registry names: {path}")
    return set(names)


def validate(root: Path) -> list[str]:
    errors = []
    try:
        public = registry_names(root / "_shared/commands.yaml")
        internal = registry_names(root / "_shared/workflows.yaml")
    except (OSError, ValueError) as exc:
        return [str(exc)]
    discovered = {p.relative_to(root).as_posix() for p in root.rglob("SKILL.md")}
    expected = {f"{name}/SKILL.md" for name in public}
    if len(public) != 5 or discovered != expected:
        errors.append(f"Expected exactly five registered entries; discovered {sorted(discovered)}")
    for name in public:
        path = root / name / "SKILL.md"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n") or not re.search(rf"^name: {name}$", text, re.M):
            errors.append(f"Invalid entry metadata: {path}")
    workflow_text = (root / "_shared/workflows.yaml").read_text(encoding="utf-8")
    for block in re.split(r"(?=^- name: )", workflow_text, flags=re.M)[1:]:
        entry = re.search(r"^  entry: (paper-[a-z]+)$", block, re.M)
        workflow = re.search(r"^  workflow: (paper-[a-z]+/WORKFLOW.md)$", block, re.M)
        if not entry or entry[1] not in public or not workflow or not (root / workflow[1]).is_file():
            errors.append(f"Invalid workflow route: {block.splitlines()[0]}")
    for directory in root.iterdir():
        if directory.is_dir() and not directory.name.startswith("."):
            if directory.name not in public | internal | {"_shared"}:
                errors.append(f"Unregistered package directory: {directory.name}")
    # Check links to the internal flows and entry routing contract after installation too.
    for path in root.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            target = target.split("#", 1)[0]
            if target.endswith(("WORKFLOW.md", "入口路由约定.md")):
                if not (path.parent / target).is_file():
                    errors.append(f"Broken workflow link: {path}: {target}")
    return errors


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "skills"
    errors = validate(root)
    print("\n".join(errors) if errors else "OK: five public entries and all internal workflow routes resolve")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
