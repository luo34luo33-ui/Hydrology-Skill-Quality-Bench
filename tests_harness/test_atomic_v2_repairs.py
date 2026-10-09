"""Scientific/interface regression tests; no evaluated Agent or model API."""
import importlib.util
import json
from pathlib import Path
import shutil

import pandas as pd
import pytest

from harness import grader, runner, schemas
from scripts.audit_atomic_negative_controls import mutate

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('number', range(1, 6))
@pytest.mark.parametrize('attack', ['wrong_unit', 'wrong_algorithm_identity', 'stale_hash'])
def test_baseflow_interface_attacks_rejected(number, attack, tmp_path):
    item = runner.discover_tasks(ROOT / 'tests', test_id=f'hydrodata-baseflow-{number:03}')[0]
    shutil.copytree(item['task_dir'] / 'expected/golden_workspace', tmp_path, dirs_exist_ok=True)
    assert grader.grade_task(item['task'], tmp_path, item['task_dir'])['score'] == pytest.approx(1)
    mutate(tmp_path, attack)
    # Rehashing cannot hide a false method/unit label.
    if attack != 'stale_hash':
        import hashlib
        result = tmp_path / 'components/result.json'; doc = json.loads(result.read_text())
        doc['artifacts']['baseflow_metadata']['sha256'] = hashlib.sha256((tmp_path / 'components/baseflow_metadata.json').read_bytes()).hexdigest()
        result.write_text(json.dumps(doc))
    assert grader.grade_task(item['task'], tmp_path, item['task_dir'])['score'] < 1


@pytest.mark.parametrize('attack', ['missing', 'traversal', 'symlink'])
def test_artifact_manifest_cannot_bypass_checks(attack, tmp_path):
    item = runner.discover_tasks(ROOT / 'tests', test_id='hydrodata-baseflow-002')[0]
    shutil.copytree(item['task_dir'] / 'expected/golden_workspace', tmp_path, dirs_exist_ok=True)
    result = tmp_path / 'components/result.json'; doc = json.loads(result.read_text())
    if attack == 'missing': del doc['artifacts']['baseflow_metadata']
    elif attack == 'traversal': doc['artifacts']['baseflow_metadata']['path'] = '../../outside.json'
    else:
        path = tmp_path / 'components/baseflow_metadata.json'
        outside = tmp_path.parent / 'outside-metadata.json'; outside.write_bytes(path.read_bytes()); path.unlink()
        try: path.symlink_to(outside)
        except OSError: pytest.skip('host cannot create symlinks')
    result.write_text(json.dumps(doc))
    assert grader.grade_task(item['task'], tmp_path, item['task_dir'])['score'] < 1


def load_factory(domain, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tests' / domain / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def test_ml_features_are_strictly_past_residuals():
    module = load_factory('results-analysis', '_mlcorrect_task_factory')
    args = module._train_command('hydroanalysis-ml-correct-001', ROOT)
    assert 'residual:1,2,3,4,5' in args and args[args.index('--lag-policy')+1] == 'drop'
    frame = module._predict_table()
    features = pd.concat([frame['residual'].shift(lag) for lag in range(1,6)], axis=1)
    modified = frame.copy(); modified.loc[20:, 'residual'] += 10000
    changed = pd.concat([modified['residual'].shift(lag) for lag in range(1,6)], axis=1)
    pd.testing.assert_frame_equal(features.iloc[:21], changed.iloc[:21])


def test_versioned_migration_preserves_weights_budgets_and_flow():
    original = json.loads((ROOT / 'docs/atomic-three-arm-baseline.json').read_text(encoding='utf-8'))['tasks']
    for item in runner.discover_tasks(ROOT / 'tests'):
        task = item['task']; old = original[task['id']]
        assert task['timeout_seconds'] == old['timeout_seconds']
        assert {c['name']: c['weight'] for c in task['grading']} == {c['name']: c['weight'] for c in old['grading']}
        for c, before in zip(task['grading'], old['grading']):
            for key in ('atol', 'rtol', 'tolerance'):
                assert c.get(key) == before.get(key)
    archive = ROOT / '.cache/atomic-v1-migration'
    for number in range(1,11):
        tid = f'hydrodata-flood-events-{number:03}'
        assert (ROOT / 'tests/data-preprocessing' / tid / 'data/components/flow_components.csv').read_bytes() == (archive / tid / 'data/components/flow_components.csv').read_bytes()


@pytest.mark.parametrize('ref,script', [
    ('prepare-dem-analysis-grid','prepare_dem_analysis_grid.py'),
    ('extract-dem-stream-network','extract_dem_stream_network.py')])
def test_rejected_spatial_run_removes_only_declared_partial_outputs(ref, script, tmp_path, monkeypatch):
    import pyexpat
    import runpy
    namespace = runpy.run_path(str(ROOT / 'runtime/public/programs/spatial-analysis' / ref / script))
    main = namespace['main']; globals_ = main.__globals__
    def fail(args):
        for name in globals_['DECLARED_OUTPUTS']:
            if name != 'result.json': (args.output_dir / name).write_bytes(b'partial')
        (args.output_dir / 'unrelated.txt').write_text('retain')
        raise RuntimeError('controlled failure')
    monkeypatch.setitem(globals_, 'run', fail)
    args = ['--output-dir', str(tmp_path)]
    args += ['--dem','unused','--basin','unused','--analysis-buffer-km','1','--vertical-unit','m','--auto-utm'] if ref.startswith('prepare') else ['--analysis-dem','unused','--stream-init-area-km2','1']
    assert main(args) == 1
    assert json.loads((tmp_path / 'result.json').read_text())['status'] == 'error'
    assert (tmp_path / 'unrelated.txt').read_text() == 'retain'
    assert all(not (tmp_path / name).exists() for name in globals_['DECLARED_OUTPUTS'] if name != 'result.json')
    # Nonempty output rejection must not remove existing files.
    protected = tmp_path / globals_['DECLARED_OUTPUTS'][0]; protected.write_bytes(b'existing')
    assert main(args) == 1 and protected.read_bytes() == b'existing'


def test_interface_schema_rejects_undeclared_targets(tmp_path):
    item = runner.discover_tasks(ROOT / 'tests', test_id='hydrodata-baseflow-001')[0]
    task = json.loads(json.dumps(item['task']))
    task['grading'][0]['required_values']['../outside.json'] = {'method': 'fake'}
    assert any('unsafe or undeclared target' in x for x in schemas.validate_task(task, item['task_dir']))
