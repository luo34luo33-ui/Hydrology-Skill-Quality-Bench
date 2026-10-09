"""No-model checks for three-arm visibility, fairness and reporting."""
import json
from pathlib import Path
import sys

import pytest

from harness import reporter, runner, schemas
from harness.atomic_contracts import CONDITIONS, VERSION, resolve_condition, tree_digest
from harness.atomic_experiment import execute_block, schedule, summarize
from harness.atomic_runtime import candidate_argv, preflight
from tests_harness.test_schemas import make_task


def fixture_task(tmp_path):
    task, folder = make_task(tmp_path)
    contract = {'version': VERSION, 'task_id': task['id'], 'inputs': task['data_files'], 'outputs': task['required_outputs']}
    reporter.write_json(folder / 'public_contract.json', contract)
    task['public_contract'] = 'public_contract.json'
    reporter.write_json(folder / 'task.json', task)
    return folder, task


@pytest.mark.parametrize('condition,skills,programs', [
    ('no-skills', 'secret', None), ('no-skills', None, 'programs'),
    ('programs-only', 'secret', 'programs'), ('with-skills', None, 'programs'),
    (None, None, 'programs')])
def test_conflicting_conditions_rejected(condition, skills, programs):
    with pytest.raises(ValueError): resolve_condition(condition, skills, programs)


def test_three_arms_identical_contracts_and_conditional_resources(tmp_path, monkeypatch):
    folder, task = fixture_task(tmp_path)
    public = tmp_path / 'bundle'; public.mkdir()
    reporter.write_json(public / 'programs.json', {'fixture': {}})
    (public / 'PROGRAM_INTERFACES.md').write_text('common programs')
    (public / 'science.py').write_text('fixture = 1\n')
    skills = tmp_path / 'skills'; (skills / 'fixture').mkdir(parents=True)
    (skills / 'fixture/SKILL.md').write_text('---\nname: fixture\ndescription: fixture\n---\n')
    script = tmp_path / 'agent.py'
    script.write_text('''import json,os,pathlib
w=pathlib.Path.cwd()
pathlib.Path('inspection.json').write_text(json.dumps({'programs':(w/'public/science.py').is_file(), 'skills':bool(os.environ.get('BENCHMARK_SKILLS_PATH'))}))
''')
    monkeypatch.setenv('BENCHMARK_SKILLS_PATH', 'must-not-leak')
    monkeypatch.setattr(runner, 'environment_metadata', lambda: {'fixture': True})
    docs, instructions = [], []
    from harness.agent_wrapper import generate_agents_md
    for condition in CONDITIONS:
        output = tmp_path / condition
        result = runner.run_benchmark(tests_root=folder.parent.parent, agent_cmd=f'"{sys.executable}" "{script}"',
            condition=condition, skills_path=skills if condition == 'with-skills' else None,
            programs_path=public if condition != 'no-skills' else None, output=output)
        work = output / 'tasks' / task['id'] / 'workspace'
        inspection = json.loads((work / 'inspection.json').read_text())
        assert inspection == {'programs': condition != 'no-skills', 'skills': condition == 'with-skills'}
        docs.append((work / 'public_contract.json').read_bytes())
        instructions.append(generate_agents_md(schemas.public_task(task), condition == 'with-skills'))
        assert not (work / 'expected').exists()
        assert result['metadata']['experiment_version'] == VERSION
    assert docs[0] == docs[1] == docs[2]
    assert instructions[0] == instructions[1] == instructions[2]


def test_container_mounts_do_not_expose_host_or_oracles(tmp_path):
    lock = {'clis': {'codebuddy': {'model': 'fixture', 'effort': 'provider-default'}},
            'image_digest': 'sha256:fixture', 'common_config_dir': str(tmp_path / 'provider'),
            'public_programs_dir': str(tmp_path / 'bundle'), 'skills_dir': str(tmp_path / 'skills')}
    for condition in CONDITIONS:
        args = candidate_argv(lock, 'codebuddy', condition, tmp_path / 'work', 'internal', 'candidate', 'identical')
        mounts = [args[i + 1] for i, x in enumerate(args) if x == '--mount']
        assert all('expected' not in x and 'USERPROFILE' not in x for x in mounts)
        assert any('target=/work/public,readonly' in x for x in mounts) == (condition != 'no-skills')
        assert any('target=/home/agent/.agents/skills,readonly' in x for x in mounts) == (condition == 'with-skills')
        assert args[-1] == 'identical'
        assert '--read-only' in args and '--privileged' not in args


def test_formal_runtime_rejects_uncertified_lock(tmp_path):
    path = tmp_path / 'lock.json'
    reporter.write_json(path, {'experiment_version': VERSION, 'runtime_mode': 'atomic-isolated-relay', 'image_digest': 'latest'})
    assert not preflight(path, 'codebuddy')['ready']


def test_six_permutations_balanced_and_reproducible():
    blocks = schedule([f'task-{i}' for i in range(183)], ['qwen'])
    from collections import Counter
    counts = Counter(tuple(b['conditions']) for b in blocks)
    assert len(blocks) == 183 and len(counts) == 6
    assert max(counts.values()) - min(counts.values()) <= 1
    assert blocks == schedule([f'task-{i}' for i in range(183)], ['qwen'])


def test_partial_runs_not_counted_as_failed_and_legacy_cannot_pool(tmp_path):
    blocks = schedule(['one', 'two'], ['qwen'])
    condition = blocks[0]['conditions'][0]
    root = tmp_path / 'qwen/r0/one' / condition
    reporter.write_json(root / 'run_metadata.json', {'experiment_version': VERSION, 'condition': condition})
    reporter.write_json(root / 'tasks/one/result.json', {'score': 1.0, 'attempted': True})
    reporter.write_json(root / 'tasks/one/execution.json', {'return_code': 0, 'timed_out': False})
    result = summarize(tmp_path, blocks)
    assert result['completed_runs'] == 1 and result['incomplete_runs'] == 5
    assert result['complete_triples'] == 0
    assert result['groups']['qwen'][condition]['full_score_rate'] == 1
    reporter.write_json(root / 'run_metadata.json', {'condition': condition})
    with pytest.raises(ValueError, match='legacy'): summarize(tmp_path, blocks)


def test_hidden_reference_change_does_not_change_staged_contract(tmp_path):
    folder, task = fixture_task(tmp_path)
    left, right = tmp_path / 'left', tmp_path / 'right'
    runner.stage_workspace(task, folder, left)
    (folder / 'expected').mkdir(exist_ok=True)
    (folder / 'expected/secret.json').write_text('{"answer": 123456789}')
    runner.stage_workspace(task, folder, right)
    assert (left / 'public_contract.json').read_bytes() == (right / 'public_contract.json').read_bytes()
    assert '123456789' not in (right / 'PUBLIC_CONTRACT.md').read_text()


def test_four_cli_start_prompts_condition_independent():
    from scripts.run_codex import build_codex_command
    from scripts.run_opencode import build_opencode_command
    from scripts.run_qwen import build_qwen_command
    from scripts.run_codebuddy import build_codebuddy_command
    for build in [build_codex_command, build_opencode_command, build_qwen_command, build_codebuddy_command]:
        assert build('fixture', 'high', False) == build('fixture', 'high', True)


def test_whole_triple_infrastructure_retry_preserves_original(tmp_path):
    block = schedule(['one'], ['qwen'])[0]
    calls = []
    def execute(condition, output):
        calls.append(condition)
        reporter.write_json(output / 'summary.json', {})
        reporter.write_json(output / 'tasks/one/execution.json', {'infrastructure_failure': condition == 'programs-only'})
    execute_block(tmp_path, block, execute)
    assert len(calls) == 6  # One whole triple retry, despite repeat infrastructure failure.
    base = tmp_path / 'qwen/r0/one'
    assert all((base / 'archived-attempt-0' / c / 'tasks/one/execution.json').is_file() for c in CONDITIONS)
    execute_block(tmp_path, block, execute)
    assert len(calls) == 6


def test_scientific_failure_and_timeout_are_not_retried(tmp_path):
    block = schedule(['one'], ['qwen'])[0]; calls = []
    def execute(condition, output):
        calls.append(condition)
        reporter.write_json(output / 'summary.json', {})
        reporter.write_json(output / 'tasks/one/execution.json', {'timed_out': True, 'infrastructure_failure': False})
    execute_block(tmp_path, block, execute)
    assert len(calls) == 3
    assert not (tmp_path / 'qwen/r0/one/archived-attempt-0').exists()


def test_complete_triple_statistics_and_provenance(tmp_path):
    blocks = schedule(['one', 'two'], ['codebuddy'])
    for b in blocks:
        for c, score in zip(CONDITIONS, [0.0, 0.5, 1.0]):
            root = tmp_path / 'codebuddy/r0' / b['task_id'] / c
            reporter.write_json(root / 'run_metadata.json', {'experiment_version': VERSION, 'condition': c,
                'programs_available': c != 'no-skills', 'public_programs_sha256': 'same' if c != 'no-skills' else None})
            reporter.write_json(root / 'tasks' / b['task_id'] / 'result.json', {'score': score, 'attempted': True})
            reporter.write_json(root / 'tasks' / b['task_id'] / 'execution.json', {'timed_out': False})
    r = summarize(tmp_path, blocks)
    assert r['complete_triples'] == 2
    assert r['differences']['codebuddy']['with-skills minus programs-only']['difference'] == [0.5, 1.0]
    bad = tmp_path / 'codebuddy/r0/one/programs-only/run_metadata.json'
    value = json.loads(bad.read_text()); value['public_programs_sha256'] = 'changed'
    reporter.write_json(bad, value)
    with pytest.raises(ValueError, match='bundles differ'): summarize(tmp_path, blocks)


def test_codebuddy_initialization_is_not_a_model_decision():
    from harness.cli_events import EventCounter
    counter = EventCounter('codebuddy')
    counter.feed('{"type":"system","subtype":"init"}')
    assert counter.started and counter.rounds == counter.tools == 0


@pytest.mark.parametrize('events,termination,infrastructure', [
    ([], 'timeout', True),
    ([{'method': 'POST', 'path': '/v1/chat/completions', 'status': 401}], 'timeout', True),
    ([{'method': 'POST', 'path': '/v1/chat/completions', 'status': 200}], 'timeout', False),
    ([{'method': 'POST', 'path': '/v1/chat/completions?trace=1', 'status': 200}], 'timeout', False),
    ([{'method': 'POST', 'path': '/v1/chat/completions', 'status': 200}], 'unauditable_events', True),
    ([{'method': 'GET', 'path': '/health', 'status': 200}], 'timeout', True),
])
def test_timeout_before_and_after_model_start_are_distinguished(tmp_path, monkeypatch, events, termination, infrastructure):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from harness.atomic_runtime import run_isolated_atomic
    import harness.isolated_runtime as isolated
    import harness.composite_runtime as composite
    _, task = fixture_task(tmp_path)
    workspace = tmp_path / 'work'; workspace.mkdir()
    output = tmp_path / 'output'; output.mkdir()
    gateway = SimpleNamespace(events=events, decision_requests=1, budget_denied=False)
    @contextmanager
    def relay(*args, **kwargs): yield 'internal', 'fixture', gateway
    monkeypatch.setattr(isolated, 'relay_session', relay)
    monkeypatch.setattr(composite, 'monitor', lambda *args, **kwargs: {
        'return_code': 1, 'timed_out': termination == 'timeout', 'termination_reason': termination})
    lock = {'clis': {'qwen': {'model': 'fixture', 'effort': 'provider-default'}},
            'image_digest': 'sha256:fixture', 'common_config_dir': str(tmp_path / 'config')}
    result = run_isolated_atomic(task, workspace, output, lock, 'qwen', 'no-skills', tmp_path)
    assert result['infrastructure_failure'] == infrastructure
