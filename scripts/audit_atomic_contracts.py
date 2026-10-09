"""Host-only completeness/leakage audit. Never publishes reference values."""
from __future__ import annotations
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import grader, runner
from harness.atomic_contracts import VERSION, digest, tree_digest
from harness.reporter import write_json


def audit(check_golden=False):
    baseline = json.loads((ROOT / 'docs/atomic-three-arm-baseline.json').read_text(encoding='utf-8'))
    migration_path = ROOT / 'docs/atomic-v2-migration.json'
    migration = json.loads(migration_path.read_text(encoding='utf-8')) if migration_path.exists() else {}
    gaps, unchanged, golden, authorized = [], [], [], []
    if migration and migration.get('historical_baseline_sha256') != digest(ROOT / 'docs/atomic-three-arm-baseline.json'):
        unchanged.append({'issue': 'immutable historical baseline changed'})
    items = runner.discover_tasks(ROOT / 'tests')
    for item in items:
        task, folder = item['task'], item['task_dir']
        original = baseline['tasks'][task['id']]
        amended = migration.get('current_tasks', {}).get(task['id'], {})
        for key in ('grading', 'required_outputs', 'data_files', 'timeout_seconds'):
            if task[key] != original[key]:
                row = {'task': task['id'], 'changed': key}
                (authorized if task[key] == amended.get(key) else unchanged).append(row)
        for name in ('data', 'expected'):
            actual = tree_digest(folder / name)
            if actual != original[name + '_sha256']:
                row = {'task': task['id'], 'changed': name}
                (authorized if actual == amended.get(name + '_sha256') else unchanged).append(row)
        document = json.loads((folder / task['public_contract']).read_text(encoding='utf-8'))
        text = json.dumps(document, ensure_ascii=False)
        if 'expected/' in text or 'golden_workspace' in text:
            gaps.append({'task': task['id'], 'issue': 'hidden path in public contract'})
        fields = set(document['capability']['serialization']['field_names'])
        fields.update(document.get('input_field_names', []))
        patterns = document['capability']['serialization'].get('dynamic_field_patterns', [])
        for c in task['grading']:
            required = []
            columns_spec = c.get('required_columns', {})
            if isinstance(columns_spec, dict):
                for columns in columns_spec.values(): required.extend(columns)
            elif isinstance(columns_spec, list): required.extend(columns_spec)
            required.extend(c.get('columns', []))
            if c.get('field'): required.extend(c['field'].split('.'))
            missing = sorted({f for f in required if f not in fields and not str(f).isdigit() and not any(re.fullmatch(p, f) for p in patterns)})
            if missing: gaps.append({'task': task['id'], 'criterion': c['name'], 'missing_interface_fields': missing})
        if check_golden:
            result = grader.grade_task(task, folder / 'expected/golden_workspace', folder)
            golden.append({'task_id': task['id'], 'score': result['score']})
    public = ROOT / 'runtime/atomic-public'
    forbidden = [p.relative_to(public).as_posix() for p in public.rglob('*') if p.is_file() and
                 (p.name == 'SKILL.md' or p.name.startswith(('make_', 'test_')) or
                  any(part in {'expected', 'golden_workspace', 'workflows'} for part in p.parts))]
    native_path = ROOT / 'docs/atomic-public-native.json'
    native = json.loads(native_path.read_text(encoding='utf-8')) if native_path.is_file() else {}
    native_ready = native.get('public_programs_sha256') == tree_digest(public) and native.get('passed') == 183 and native.get('total') == 183
    bindings = {item['task']['id']: {'task': digest(item['task_path']), 'data': tree_digest(item['task_dir'] / 'data'),
                'expected': tree_digest(item['task_dir'] / 'expected'), 'grader': digest(ROOT / 'harness/grader.py')} for item in items}
    rows = native.get('tasks', [])
    native_ready &= len(rows) == len(bindings) and {r['task_id'] for r in rows} == set(bindings)
    native_ready &= all(r.get('passed') and r.get('task_binding') == bindings.get(r['task_id']) for r in rows)
    isolation_path = ROOT / 'docs/atomic-isolation-certification.json'
    isolation = json.loads(isolation_path.read_text(encoding='utf-8')) if isolation_path.is_file() else {}
    isolation_ready = isolation.get('passed') is True and isolation.get('public_programs_sha256') == tree_digest(public)
    catalog = json.loads((ROOT / 'docs/atomic-skill-catalog.json').read_text(encoding='utf-8'))
    source = Path(catalog['source_root'])
    source_changes = [f['path'] for skill in catalog['atomic_skills'] for f in skill['files']
                      if not (source / f['path']).is_file() or digest(source / f['path']) != f['sha256']]
    conflicts = []
    for row in native.get('tasks', []):
        if row['passed']: continue
        tid = row['task_id']
        category = ('rainfall_contract' if tid.startswith('hydrodata-flood-events-') else
                    'timezone_contract' if tid.startswith('hydromodel-') else
                    'residual_lag_contract' if tid.startswith('hydroanalysis-ml-correct-') else
                    'failure_artifact_cleanup' if tid.startswith(('hydrodata-dem-grid-', 'hydrodata-stream-network-')) else
                    'spatial_grid_mask')
        conflicts.append({'task_id': tid, 'category': category, 'native_score': row.get('score'),
            'executions': row.get('executions', []),
            'failed_criteria': {k: v['details'] for k, v in row.get('criteria', {}).items() if v['score'] < 1},
            'resolution': 'Blocked. Reconcile source/task version explicitly; do not amend inputs, oracle or tolerances silently.'})
    write_json(ROOT / 'docs/atomic-contract-conflicts.json', {'version': VERSION,
        'public_programs_sha256': tree_digest(public), 'blocking_conflicts': conflicts,
        'source_snapshot': catalog['snapshot_date'], 'current_source_changes': source_changes,
        'changed_scientific_truth': bool(authorized), 'migration_ledger': 'docs/atomic-v2-migration.json' if migration else None})
    negative_path = ROOT / 'docs/atomic-negative-controls.json'
    negative = json.loads(negative_path.read_text(encoding='utf-8')) if negative_path.is_file() else {}
    result = {'version': VERSION, 'tasks': len(items), 'capabilities': len({x['task']['primary_skill'] for x in items}),
              'baseline_changes': unchanged, 'authorized_migration_changes': authorized, 'interface_gaps': gaps, 'public_forbidden_files': forbidden,
              'golden': golden, 'contracts_ready': not gaps and not unchanged and not forbidden and not source_changes and len(items) == 183,
              'negative_controls_ready': negative.get('passed') is True and negative.get('version') == VERSION,
              'native_programs_ready': native_ready, 'native_programs_passed': native.get('passed', 0),
              'isolation_ready': isolation_ready, 'provider_ready': False, 'formal_ready': False,
              'source_files_checked': sum(len(s['files']) for s in catalog['atomic_skills']),
              'source_changes': source_changes, 'blocking_native_conflicts': len(conflicts),
              'real_agent_runs': 0, 'public_programs_sha256': tree_digest(public)}
    write_json(ROOT / 'docs/atomic-three-arm-acceptance.json', result)
    return result


if __name__ == '__main__':
    result = audit('--golden' in sys.argv)
    print(json.dumps({k: len(v) if isinstance(v, list) else v for k, v in result.items() if k not in {'public_programs_sha256'}}, ensure_ascii=False))
