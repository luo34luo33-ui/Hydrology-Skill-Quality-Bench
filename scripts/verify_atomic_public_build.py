"""Rebuild in two clean roots with no hidden references; check factory compatibility."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import prepare_atomic_contracts as builder
from harness.atomic_contracts import digest, tree_digest
from harness import reporter, runner


def main():
    records = []
    original_root = builder.ROOT
    with tempfile.TemporaryDirectory(prefix='hsqb-public-repeat-') as temporary:
        for index in range(2):
            destination = Path(temporary) / str(index); destination.mkdir()
            for directory in ['runtime/public', 'runtime/skills', 'docs/composite-contracts']:
                shutil.copytree(ROOT / directory, destination / directory, ignore=shutil.ignore_patterns('__pycache__'))
            (destination / 'docs').mkdir(exist_ok=True)
            for name in ['atomic-skill-catalog.json', 'atomic-three-arm-baseline.json']:
                shutil.copyfile(ROOT / 'docs' / name, destination / 'docs' / name)
            for item in runner.discover_tasks(ROOT / 'tests'):
                target = destination / item['task_dir'].relative_to(ROOT)
                target.mkdir(parents=True)
                shutil.copyfile(item['task_path'], target / 'task.json')
                shutil.copytree(item['task_dir'] / 'data', target / 'data')
                # expected/ is deliberately absent in these builds.
            builder.ROOT = destination
            try: builder.main()
            finally: builder.ROOT = original_root
            records.append({'programs_sha256': tree_digest(destination / 'runtime/atomic-public'),
                            'skills_sha256': tree_digest(destination / 'runtime/atomic-skills'),
                            'capabilities_sha256': tree_digest(destination / 'docs/atomic-public-contracts'),
                            'task_contracts': {i['task']['id']: digest(i['task_dir'] / 'public_contract.json')
                                               for i in runner.discover_tasks(destination / 'tests')}})
        factory_path = ROOT / 'tests/data-preprocessing/_baseflow_task_factory.py'
        spec = importlib.util.spec_from_file_location('baseflow_repeat', factory_path)
        factory = importlib.util.module_from_spec(spec); spec.loader.exec_module(factory)
        factory.ROOT = Path(temporary) / 'factory'
        factory.generate_task('hydrodata-baseflow-001')
        reference = ROOT / 'tests/data-preprocessing/hydrodata-baseflow-001'
        generated = factory.ROOT / 'hydrodata-baseflow-001'
        factory_equal = all(tree_digest(generated / d) == tree_digest(reference / d) for d in ['data', 'expected'])
        factory_equal &= digest(generated / 'public_contract.json') == digest(reference / 'public_contract.json')
        factory_equal &= digest(generated / 'task.json') == digest(reference / 'task.json')
    result = {'builds': records, 'repeated_builds_identical': records[0] == records[1],
              'matches_workspace_public': records[0]['programs_sha256'] == tree_digest(ROOT / 'runtime/atomic-public'),
              'representative_factory_compatible': factory_equal, 'hidden_references_available_to_builds': False,
              'real_agent_runs': 0}
    reporter.write_json(ROOT / 'docs/atomic-public-repeatability.json', result)
    print({k: v for k, v in result.items() if k != 'builds'})
    return 0 if all(result[k] for k in ['repeated_builds_identical', 'matches_workspace_public', 'representative_factory_compatible']) else 1


if __name__ == '__main__': raise SystemExit(main())
