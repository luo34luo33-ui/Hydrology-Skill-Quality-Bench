"""Refresh a three-arm lock; no credentials, model calls or fabricated certifications."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.atomic_contracts import VERSION, digest, tree_digest
from harness import runner, reporter


def freeze(existing, image_digest=None, versions=None):
    lock = dict(existing)
    lock.update(experiment_version=VERSION, runtime_mode='atomic-isolated-relay', status='awaiting_certification')
    if image_digest: lock['image_digest'] = image_digest
    for name, relative in [('tests_root', 'tests'), ('public_programs_dir', 'runtime/atomic-public'),
                           ('skills_dir', 'runtime/atomic-skills'), ('common_config_dir', 'runtime/atomic-provider-config')]:
        lock.setdefault(name, str(ROOT / relative))
    for name, hash_name in [('public_programs_dir', 'public_programs_sha256'), ('skills_dir', 'skills_sha256'),
                            ('common_config_dir', 'common_config_sha256')]:
        lock[hash_name] = tree_digest(Path(lock[name]))
    lock['host_runtime_sha256'] = tree_digest(ROOT / 'harness')
    lock['public_contract_hashes'] = {i['task']['id']: digest(i['task_dir'] / i['task']['public_contract'])
                                     for i in runner.discover_tasks(Path(lock['tests_root']))}
    lock['atomic_budget'] = {'agent_rounds': 60, 'tool_calls': 120}
    for cli in ['codex', 'opencode', 'qwen', 'codebuddy']:
        cfg = lock.setdefault('clis', {}).setdefault(cli, {'model': None, 'effort': None, 'version': None})
        cfg['config_sha256'] = tree_digest(Path(lock['common_config_dir']) / cli)
        if versions and cli in versions: cfg['version'] = versions[cli]
    # Attach actual host receipts only; runtime checks their contents, not this status.
    certifications = {}
    for kind, filename in [('contracts', 'atomic-three-arm-acceptance.json'), ('isolation', 'atomic-isolation-certification.json'),
                            ('provider', 'atomic-provider-certification.json')]:
        path = ROOT / 'docs' / filename
        if path.is_file(): certifications[kind] = {'path': str(path), 'sha256': digest(path)}
    lock['certifications'] = certifications
    return lock


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, default=ROOT / 'runtime/atomic-experiment.lock.example.json')
    p.add_argument('--output', type=Path, default=ROOT / 'runtime/atomic-experiment.lock.example.json')
    p.add_argument('--image-digest'); p.add_argument('--versions', type=Path)
    args = p.parse_args()
    original = json.loads(args.source.read_text(encoding='utf-8')) if args.source.is_file() else {}
    versions = json.loads(args.versions.read_text(encoding='utf-8')) if args.versions else None
    lock = freeze(original, args.image_digest, versions)
    reporter.write_json(args.output, lock)
    print(json.dumps({'output': str(args.output), 'status': lock['status'], 'tasks': len(lock['public_contract_hashes'])}))


if __name__ == '__main__': main()
