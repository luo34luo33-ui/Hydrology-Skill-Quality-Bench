"""Regression attacks against the versioned interface and scientific graders."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import grader, reporter
from harness.atomic_contracts import VERSION


def mutate(workspace, case):
    if case == 'wrong_field':
        p = workspace / 'components/flow_components.csv'
        p.write_text(p.read_text().replace('baseflow_m3_s', 'wrong_baseflow_field'))
        return
    p = workspace / ('components/result.json' if case in {'wrong_status', 'wrong_hierarchy', 'stale_hash'} else 'components/baseflow_metadata.json')
    obj = json.loads(p.read_text())
    if case == 'wrong_status': obj['status'] = 'success'
    elif case == 'wrong_hierarchy': obj = {'unrelated': obj}
    elif case == 'stale_hash':
        for value in obj['artifacts'].values():
            if isinstance(value, dict) and 'sha256' in value: value['sha256'] = '0' * 64
    elif case == 'wrong_unit': obj['flow_unit'] = 'mm'
    elif case == 'wrong_algorithm_identity': obj['method'] = 'Eckhardt forward-backward double pass'
    p.write_text(json.dumps(obj), encoding='utf-8')


def main():
    directory = ROOT / 'tests/data-preprocessing/hydrodata-baseflow-002'
    task = json.loads((directory / 'task.json').read_text(encoding='utf-8'))
    records = []
    for case in ['wrong_field', 'wrong_unit', 'wrong_hierarchy', 'wrong_algorithm_identity', 'wrong_status', 'stale_hash']:
        with tempfile.TemporaryDirectory(prefix='hsqb-negative-') as tmp:
            workspace = Path(tmp)
            shutil.copytree(directory / 'expected/golden_workspace', workspace, dirs_exist_ok=True)
            mutate(workspace, case)
            result = grader.grade_task(task, workspace, directory)
            records.append({'task_id': task['id'], 'mutation': case, 'score': result['score'],
                            'rejected_by_original_grader': result['score'] < 1 - 1e-12})
    result = {'version': VERSION, 'criteria_unchanged': False, 'weights_unchanged': True, 'cases': records,
              'passed': all(x['rejected_by_original_grader'] for x in records),
              'scope': 'Representative legacy baseflow grader; does not certify every scientific predicate.'}
    reporter.write_json(ROOT / 'docs/atomic-negative-controls.json', result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
