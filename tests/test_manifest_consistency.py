"""Public discovery, complete capability routing, compatibility, and docs guards."""
from pathlib import Path
import re
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / 'skills'
PUBLIC = yaml.safe_load((SKILLS / '_shared/commands.yaml').read_text())
WORKFLOWS = yaml.safe_load((SKILLS / '_shared/workflows.yaml').read_text())
BY_ID = {row['name']: row for row in WORKFLOWS}
PUBLIC_NAMES = {row['name'] for row in PUBLIC}
# The pre-consolidation capability contract. Removing a menu must not remove its work.
LEGACY_IDS = {'paper-' + word for word in (
    'init help doctor daily topic search screen method proposal outline draft logic '
    'anchor abstract import figure plot style verify format claim review revise disclose submit typeset'
).split()}


def test_discovery_matches_exactly_five_public_entries():
    discovered = {p.relative_to(SKILLS).as_posix() for p in SKILLS.rglob('SKILL.md')}
    assert len(PUBLIC_NAMES) == len(PUBLIC) == 5
    assert discovered == {f'{name}/SKILL.md' for name in PUBLIC_NAMES}


def test_all_original_capabilities_have_exactly_one_owner():
    assert len(BY_ID) == len(WORKFLOWS)
    assert set(BY_ID) == LEGACY_IDS
    routed = [name for entry in PUBLIC for name in entry['workflows']]
    assert len(routed) == len(set(routed))
    assert set(routed) == LEGACY_IDS
    for entry in PUBLIC:
        assert entry['status'] == 'released'
        for name in entry['workflows']:
            assert BY_ID[name]['entry'] == entry['name']


@pytest.mark.parametrize('entry', PUBLIC, ids=lambda row: row['name'])
def test_public_entry_metadata_and_routes(entry):
    path = SKILLS / entry['name'] / 'SKILL.md'
    text = path.read_text()
    fm = yaml.safe_load(re.match(r'^---\n(.*?)\n---', text, re.S)[1])
    assert fm['name'] == fm['slug'] == entry['name']
    assert 50 <= len(fm['description']) <= 1024
    assert fm['version'] == (SKILLS / '_shared/VERSION').read_text().strip()
    assert fm['displayName'].startswith('学术辅导')
    assert len(text.splitlines()) <= 500
    for name in entry['workflows']:
        assert BY_ID[name]['workflow'] in text


@pytest.mark.parametrize('flow', WORKFLOWS, ids=lambda row: row['name'])
def test_internal_workflow_exists_and_retains_status(flow):
    assert {'name', 'phase', 'stage_zh', 'status', 'intent_zh', 'entry', 'request_zh', 'workflow'} <= flow.keys()
    assert flow['entry'] in PUBLIC_NAMES
    path = SKILLS / flow['workflow']
    assert path.is_file()
    assert not path.read_text().startswith('---\n'), 'Internal workflows must not carry skill metadata'
    assert flow['status'] == ('planned' if flow['name'] == 'paper-anchor' else 'released')
    if flow.get('builtin_in'):
        assert flow['workflow'] == BY_ID[flow['builtin_in']]['workflow']
        assert not (SKILLS / flow['name']).exists()
    else:
        assert flow['workflow'] == f"{flow['name']}/WORKFLOW.md"


def test_all_package_directories_are_registered():
    directories = {p.name for p in SKILLS.iterdir() if p.is_dir() and not p.name.startswith('.')}
    assert directories == PUBLIC_NAMES | {c['name'] for c in WORKFLOWS if not c.get('builtin_in')} | {'_shared'}


def test_user_facing_skill_instructions_only_invoke_public_commands():
    for path in (p for p in SKILLS.rglob('*') if p.suffix in {'.md', '.html', '.py'}):
        names = set(re.findall(r'(?<![\w./-])/(paper-[a-z]+)(?![a-z/:-])', path.read_text()))
        assert not names - PUBLIC_NAMES - {'paper-xxx', 'paper-word'}, (path, names - PUBLIC_NAMES)


@pytest.mark.parametrize('name', ['README.md', 'README.en.md'])
def test_readme_public_commands_match_registry(name):
    text = (ROOT / name).read_text()
    commands = set(re.findall(r'(?<![\w./-])/(paper-[a-z]+)(?![a-z/:-])', text))
    assert commands == PUBLIC_NAMES
    tables = re.findall(r'(?:^\|.*\|[ \t]*\n)+', text, re.M)
    assert any(set(re.findall(r'/(paper-[a-z]+)', table)) == PUBLIC_NAMES for table in tables)
    assert 'scripts/install_skills.py' in text
    assert '--dry-run' in text


def test_shared_stage_names_and_historical_progress_remain_compatible():
    sys.path.insert(0, str(ROOT / 'tests/paper-help'))
    try:
        from progress_parser import _PHASE_STAGE_ZH, parse_trace_entries, compute_stage_progress
    finally:
        sys.path.pop(0)
    seen = {}
    for flow in WORKFLOWS:
        phase = flow['phase']
        assert _PHASE_STAGE_ZH[phase] == flow['stage_zh']
        assert seen.setdefault(phase, flow['stage_zh']) == flow['stage_zh']
    trace = '## 2026-07-22 · paper-topic 选题\n- 产物：topic/rq.md\n\n## 2026-07-23 · paper-search 检索\n- 产物：literature/notes.md\n'
    entries = parse_trace_entries(trace)
    assert len(entries) == 2
    assert {e.command for e in entries} == {'paper-topic', 'paper-search'}
    progress = compute_stage_progress(entries, BY_ID)
    stage = next(s for s in progress.stages if s.phase == 'A')
    assert set(stage.done_commands) == {'paper-topic', 'paper-search'}
    assert progress.total_entries == 2
    assert progress.covered_phases == 1


def test_init_uses_live_workflow_metadata_and_keeps_template_check():
    text = (SKILLS / 'paper-init/WORKFLOW.md').read_text()
    assert '../_shared/workflows.yaml' in text
    assert "grep '[<>]' README.md" in text
    assert '正文不应含任何尖括号' in text


def test_standalone_distribution_validator():
    sys.path.insert(0, str(ROOT / 'scripts'))
    try:
        from validate_commands import validate
        assert validate(SKILLS) == []
    finally:
        sys.path.pop(0)
