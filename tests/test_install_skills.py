"""Exercise actual bundle copying and upgrades in isolated host directories."""
from pathlib import Path
import shutil
import sys
import subprocess
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
try:
    import install_skills as installer
    from validate_commands import validate
finally:
    sys.path.pop(0)


def target_path(tmp_path):
    return tmp_path.resolve() / '.codex/skills'


def old_skill(target, name):
    path = target / name
    path.mkdir(parents=True, exist_ok=True)
    (path / 'SKILL.md').write_text(
        f'---\nname: {name}\nslug: {name}\ndisplayName: 学术辅导·旧版\n'
        'summary: 学术辅导套件的一员，需成套安装。\n---\n旧版流程\n'
    )
    return path


def assert_five(target):
    assert len(list(target.rglob('SKILL.md'))) == 5
    assert validate(target) == []


def test_fresh_install_is_complete_and_repeatable(tmp_path):
    target = target_path(tmp_path)
    assert installer.install(target) is None
    assert_five(target)
    assert (target / 'paper-verify/scripts/verify.py').is_file()
    assert (target / 'paper-typeset/references/转换方案与环境准备.md').is_file()
    for name in ('gbt7714-2015-numeric.csl', 'gbt7714-2015-author-date.csl', 'LICENSE'):
        assert (target / 'paper-typeset/references/csl' / name).is_file()
    for script in ('paper-verify/scripts/verify.py', 'paper-search/scripts/search.py',
                   'paper-typeset/scripts/export.py', 'paper-style/scripts/style_metrics.py'):
        result = subprocess.run([sys.executable, str(target / script), '--help'],
                                cwd=tmp_path, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    (target / 'paper-search/user-note.txt').write_text('local note')
    backup = installer.install(target)
    assert_five(target)
    assert (backup / 'paper-search/user-note.txt').read_text() == 'local note'
    assert not (target / 'paper-search/user-note.txt').exists()
    assert target not in backup.parents


def test_upgrade_removes_all_old_discovery_files_and_preserves_other_skills(tmp_path):
    target = target_path(tmp_path)
    workflows = list(installer.SOURCE.glob('*/WORKFLOW.md'))
    for flow in workflows:
        old_skill(target, flow.parent.name)
    unrelated = target / 'paper-unrelated'
    unrelated.mkdir()
    (unrelated / 'SKILL.md').write_text('third-party content')
    (target / 'user-config.txt').write_text('keep me')
    backup = installer.install(target)
    discovered = {p.parent.name for p in target.rglob('SKILL.md')}
    assert discovered == {'paper-help', 'paper-research', 'paper-write', 'paper-check', 'paper-submit', 'paper-unrelated'}
    assert (backup / 'paper-init/SKILL.md').is_file()
    assert (unrelated / 'SKILL.md').read_text() == 'third-party content'
    assert (target / 'user-config.txt').read_text() == 'keep me'
    assert not (target / 'paper-init/SKILL.md').exists()


def test_dry_run_writes_nothing(tmp_path):
    target = target_path(tmp_path)
    installer.install(target, dry_run=True)
    assert not target.parent.exists()


def test_conflict_is_detected_before_any_changes(tmp_path):
    target = target_path(tmp_path)
    previous = old_skill(target, 'paper-init')
    conflict = target / 'paper-write'
    conflict.mkdir()
    (conflict / 'SKILL.md').write_text('third party')
    with pytest.raises(ValueError, match='Unrecognized'):
        installer.install(target)
    assert (previous / 'SKILL.md').is_file()
    assert (conflict / 'SKILL.md').read_text() == 'third party'
    assert not (target.parent / '.paper-tutor-backups').exists()


def test_copy_failure_does_not_touch_previous_install(tmp_path):
    target = target_path(tmp_path)
    previous = old_skill(target, 'paper-init')
    with patch.object(installer.shutil, 'copytree', side_effect=OSError('disk full')):
        with pytest.raises(OSError, match='disk full'):
            installer.install(target)
    assert (previous / 'SKILL.md').is_file()
    assert not (target.parent / '.paper-tutor-backups').exists()


def test_move_failure_restores_backed_up_directories(tmp_path):
    target = target_path(tmp_path)
    previous = old_skill(target, 'paper-init')
    original_move = shutil.move

    def failing_move(src, dst):
        if Path(src).parent.name.startswith('.paper-tutor-stage-') and Path(src).name == 'paper-check':
            raise OSError('interrupted move')
        return original_move(src, dst)

    with patch.object(installer.shutil, 'move', side_effect=failing_move):
        with pytest.raises(OSError, match='interrupted move'):
            installer.install(target)
    assert (previous / 'SKILL.md').is_file()
    assert {p.name for p in target.iterdir()} == {'paper-init'}


def test_symlinked_collision_is_not_followed(tmp_path):
    target = target_path(tmp_path)
    target.mkdir(parents=True)
    external = tmp_path / 'external'
    external.mkdir()
    (external / 'important.txt').write_text('unchanged')
    (target / 'paper-init').symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match='symlinked'):
        installer.install(target)
    assert (external / 'important.txt').read_text() == 'unchanged'


def test_invalid_source_with_extra_skill_is_rejected(tmp_path):
    source = tmp_path / 'source'
    shutil.copytree(installer.SOURCE, source, ignore=installer.IGNORE)
    (source / 'paper-init/SKILL.md').write_text('accidentally restored old entry')
    with pytest.raises(ValueError, match='five'):
        installer.install(target_path(tmp_path), source=source)
    assert not target_path(tmp_path).exists()
