#!/usr/bin/env python3
"""Install the complete bundle; back up owned folders before replacing old entries.

No network or third-party dependencies. Unrelated skills are never removed.
"""
from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from pathlib import Path

from validate_commands import validate

SOURCE = Path(__file__).resolve().parents[1] / "skills"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", ".pytest_cache")


def owned(path: Path) -> bool:
    if path.is_symlink() or not path.is_dir():
        return False
    if path.name == "_shared":
        return all((path / name).exists() for name in ("VERSION", "commands.yaml", "paper_shared"))
    skill = path / "SKILL.md"
    if skill.is_file() and not skill.is_symlink():
        text = skill.read_text(encoding="utf-8")
        return bool(
            re.search(rf"^name: {re.escape(path.name)}$", text, re.M)
            and re.search(r"^displayName: 学术辅导", text, re.M)
            and re.search(r"^summary: .*学术辅导套件", text, re.M)
        )
    workflow = path / "WORKFLOW.md"
    if workflow.is_file() and not workflow.is_symlink():
        text = workflow.read_text(encoding="utf-8")
        return f"内部流程 `{path.name}`" in text
    return False


def install(target: Path, *, source: Path = SOURCE, dry_run: bool = False) -> Path | None:
    target = target.expanduser().absolute()
    source = source.resolve()
    resolved = target.resolve()
    if target.is_symlink() or resolved == source or source in resolved.parents or resolved in source.parents:
        raise ValueError("Target must be separate from source and must not be a symlink")
    # Host configuration/skills paths with symlinked parents are ambiguous; do not modify them.
    if any(parent.is_symlink() for parent in target.parents):
        raise ValueError("Target has a symlinked parent; use the real path explicitly")
    if target.exists() and not target.is_dir():
        raise ValueError(f"Target is not a directory: {target}")
    errors = validate(source)
    if errors:
        raise ValueError("Invalid source bundle: " + "; ".join(errors))
    packages = sorted(p for p in source.iterdir() if p.is_dir() and not p.name.startswith("."))
    # Preflight every collision before creating a directory or moving an old package.
    existing = []
    for package in packages:
        dest = target / package.name
        if dest.exists() or dest.is_symlink():
            if not owned(dest):
                raise ValueError(f"Unrecognized or symlinked package, left untouched: {dest}")
            existing.append(dest)
    print(f"Target: {target}\nPublic entries: 5; package directories: {len(packages)}")
    print("Replace with backup: " + (", ".join(p.name for p in existing) or "none"))
    if dry_run:
        return None
    # Stage the entire new bundle first, so copy failures cannot disturb an old install.
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".paper-tutor-stage-", dir=target.parent) as temporary:
        staging = Path(temporary)
        for package in packages:
            shutil.copytree(package, staging / package.name, ignore=IGNORE)
        staged_errors = validate(staging)
        if staged_errors:
            raise ValueError("Invalid staged bundle: " + "; ".join(staged_errors))
        backup = None
        if existing:
            backup_root = target.parent / ".paper-tutor-backups"
            if backup_root.is_symlink():
                raise ValueError("Backup directory must not be a symlink")
            backup_root.mkdir(exist_ok=True)
            backup = Path(tempfile.mkdtemp(prefix="install-", dir=backup_root))
        target.mkdir(exist_ok=True)
        moved, installed = [], []
        try:
            for dest in existing:
                shutil.move(str(dest), str(backup / dest.name))
                moved.append(dest)
            for package in packages:
                dest = target / package.name
                shutil.move(str(staging / package.name), str(dest))
                installed.append(dest)
        except Exception:
            # Only newly installed directories are removed. Original folders are restored.
            for dest in installed:
                shutil.rmtree(dest)
            for dest in reversed(moved):
                shutil.move(str(backup / dest.name), str(dest))
            raise
    print(f"Installed. Backup: {backup or 'none (new installation)'}")
    print("Open a new host session to reload the five entries.")
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True, help="Host skills directory")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without changing files")
    args = parser.parse_args()
    try:
        install(args.target, dry_run=args.dry_run)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Installation stopped: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
