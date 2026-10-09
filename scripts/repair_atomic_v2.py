"""Explicit, host-only v1 -> v2 fixture migration. No Agent, API or source edits."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import runner, reporter
from harness.atomic_contracts import tree_digest, digest, VERSION
from scripts.verify_public_atomic import factory, layout, commands, run_command

ARCHIVE = ROOT / '.cache/atomic-v1-migration'
LEDGER = ROOT / 'docs/atomic-v2-migration.json'


def state(item):
    t = item['task']; d = item['task_dir']
    return {k: t[k] for k in ('grading', 'required_outputs', 'data_files', 'timeout_seconds')} | {
        'task_sha256': digest(d / 'task.json'), 'data_sha256': tree_digest(d / 'data'),
        'expected_sha256': tree_digest(d / 'expected')}


def archive():
    if ARCHIVE.exists():
        raise ValueError('Migration archive exists. Do not overwrite history.')
    ARCHIVE.mkdir(parents=True)
    for item in runner.discover_tasks(ROOT / 'tests'):
        shutil.copytree(item['task_dir'], ARCHIVE / item['task']['id'])
    for name in ('atomic-three-arm-baseline.json', 'atomic-public-native.json', 'atomic-contract-conflicts.json',
                 'atomic-negative-controls.json', 'atomic-three-arm-acceptance.json'):
        shutil.copyfile(ROOT / 'docs' / name, ARCHIVE / name)


def patch_cleanup():
    records = []
    for ref, script in (
        ('spatial-analysis/prepare-dem-analysis-grid', 'prepare_dem_analysis_grid.py'),
        ('spatial-analysis/extract-dem-stream-network', 'extract_dem_stream_network.py')):
        public = ROOT / 'runtime/public/programs' / ref / script
        skills = ROOT / 'runtime/skills' / ref.replace('/', '-') / 'examples' / script
        original = public.read_bytes()
        if original != skills.read_bytes(): raise ValueError('pre-patch program parity failed')
        text = original.decode('utf-8')
        if 'HSQB v2 packaging fix' in text:
            source = Path(json.loads((ROOT / 'docs/atomic-skill-catalog.json').read_text(encoding='utf-8'))['source_root']) / ref / 'examples' / script
            records.append({'program': ref, 'before_sha256': digest(source), 'after_sha256': digest(public),
                            'change': 'remove declared partial outputs on error, retain native error result and exit code'})
            continue
        old = '        if prepared:\n'
        replacement = '''        if prepared:
            # HSQB v2 packaging fix: rejected computations cannot leave deliverable artifacts.
            # prepare_output_dir checked/cleared every declared name before execution.
            for name in DECLARED_OUTPUTS:
                if name != "result.json":
                    partial = args.output_dir / name
                    if partial.is_file() or partial.is_symlink():
                        partial.unlink()
'''
        if text.count(old) != 1: raise ValueError('unexpected cleanup patch context')
        text = text.replace(old, replacement)
        for destination in (public, skills): destination.write_text(text, encoding='utf-8', newline='\n')
        records.append({'program': ref, 'before_sha256': hashlib.sha256(original).hexdigest(),
                        'after_sha256': digest(public), 'change': 'remove declared partial outputs on error, retain native error result and exit code'})
    return records


def generate_family(module, ids, temporary):
    original_root = module.ROOT
    module.ROOT = temporary / module.__name__; module.ROOT.mkdir()
    try:
        for tid in ids:
            module.generate_task(tid)
            generated = module.ROOT / tid
            existing = next(x['task_dir'] for x in runner.discover_tasks(ROOT / 'tests', test_id=tid))
            for name in ('data', 'expected'):
                (existing / name).resolve().relative_to(ROOT.resolve())
                shutil.rmtree(existing / name)
                shutil.copytree(generated / name, existing / name)
            shutil.copyfile(generated / 'task.json', existing / 'task.json')
    finally: module.ROOT = original_root


def topology_check(workspace):
    """Independent positive-area pixel/polygon intersection for all-touched case."""
    import pyexpat
    import geopandas as gpd
    import numpy as np
    import pandas as pd
    import rasterio
    from shapely.geometry import Polygon
    basin = gpd.read_file(workspace / 'basin.gpkg').geometry.union_all()
    with rasterio.open(workspace / 'subbasins.tif') as raster:
        array = raster.read(1); area = abs(raster.transform.a * raster.transform.e)
        counts = {}
        for row, col in np.argwhere(array > 0):
            corners = [raster.transform * (col + x, row + y) for x, y in ((0,0),(1,0),(1,1),(0,1))]
            if basin.intersection(Polygon(corners)).area > 0:
                key = int(array[row, col]); counts[key] = counts.get(key, 0) + 1
    frame = pd.read_csv(workspace / 'hydrobase/subbasins.csv')
    # The native contract records contributing grid-cell area, not clipped vector area.
    area_column = next(c for c in frame if c in ('area_km2', 'subbasin_area_km2'))
    id_column = next(c for c in frame if c in ('sub_id', 'subbasin_id', 'reach_id', 'id'))
    for _, record in frame.iterrows():
        expected = counts[int(record[id_column])] * area / 1e6
        if not np.isclose(record[area_column], expected, rtol=0, atol=1e-12):
            raise ValueError('independent all-touched area verification failed')
    return {'all_touched_cells_by_id': counts, 'cell_area_m2': area, 'independent_area_check': True}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--record', action='store_true'); p.add_argument('--resume', action='store_true'); args = p.parse_args()
    if args.record:
        previous = json.loads(LEDGER.read_text(encoding='utf-8'))
        previous['current_tasks'] = {x['task']['id']: state(x) for x in runner.discover_tasks(ROOT / 'tests')}
        reporter.write_json(LEDGER, previous); return
    if not args.resume: archive()
    elif not ARCHIVE.is_dir(): raise ValueError('resume requires original archive')
    patches = patch_cleanup()
    with tempfile.TemporaryDirectory(prefix='hsqb-migration-v2-', ignore_cleanup_errors=True) as directory:
        temporary = Path(directory)
        generate_family(factory('data-preprocessing', '_flood_event_task_factory'),
                        [f'hydrodata-flood-events-{i:03}' for i in range(1,11)], temporary)
        generate_family(factory('model-calibration', '_calibration_task_factory'),
                        [f'hydromodel-{a}-{i:03}' for a in ('de','ga','pso','sce-ua','two-stage') for i in (1,2,3)], temporary)
        generate_family(factory('results-analysis', '_mlcorrect_task_factory'),
                        [f'hydroanalysis-ml-correct-{i:03}' for i in (1,2)], temporary)
        module = factory('data-preprocessing', '_baseflow_task_factory')
        for item in runner.discover_tasks(ROOT / 'tests'):
            if item['task']['id'] in {f'hydrodata-baseflow-{i:03}' for i in range(1,6)}:
                task = item['task']; criterion = task['grading'][0]
                criterion['required_values'] = {'components/baseflow_metadata.json': {'method': 'Eckhardt digital filter', 'flow_unit': 'm3/s'}}
                criterion['artifact_references'] = {'components/result.json': ['baseflow_metadata', 'flow_components']}
                reporter.write_json(item['task_path'], task)
        public = ROOT / 'runtime/public'; skills = temporary / 'skills'; layout(public, skills)
        item = runner.discover_tasks(ROOT / 'tests', test_id='hydrodata-topology-build-003')[0]
        work = temporary / 'topology'; shutil.copytree(item['task_dir'] / 'data', work)
        scratch = temporary / 'scratch'; scratch.mkdir(); executions = []
        for c in commands(item['task'], work, skills, scratch):
            if run_command(c, work, public, executions): raise ValueError('topology native failed')
        spatial = topology_check(work)
        module = factory('spatial-analysis', '_spatial_task_factory')
        module.stabilize_output_artifacts(work / 'hydrobase', ['reaches_clipped.gpkg'])
        result_path = work / 'hydrobase/result.json'
        document = json.loads(result_path.read_text(encoding='utf-8'))
        for reference in document.get('inputs', {}).values():
            if isinstance(reference, dict) and 'path' in reference:
                reference['path'] = '../' + Path(reference['path']).name
        module.write_json(result_path, document)
        golden = item['task_dir'] / 'expected/golden_workspace/hydrobase'
        golden.resolve().relative_to(ROOT.resolve())
        shutil.rmtree(golden); shutil.copytree(work / 'hydrobase', golden)
    reporter.write_json(LEDGER, {'from_version': 'atomic-three-arm-v1', 'version': VERSION,
        'authorization': 'User explicitly requested repair of compatibility conflicts and scoring vulnerabilities.',
        'historical_baseline_sha256': digest(ROOT / 'docs/atomic-three-arm-baseline.json'),
        'archive': ARCHIVE.relative_to(ROOT).as_posix(), 'packaging_patches': patches, 'spatial_verification': spatial,
        'original_observations_replaced': False, 'tolerances_or_weights_relaxed': False, 'real_agent_runs': 0,
        'changes': {'flood': 'schema 1.2 with explicitly synthetic companion rainfall, original flow unchanged',
                    'calibration': 'UTC test timestamps, same evaluator objective/values/search budget',
                    'ml': 'causal residual lags 1..5, historical synthetic residual context, no contemporaneous target feature',
                    'spatial': 'declared error artifact cleanup; independent all-touched area verified',
                    'grading': 'validate baseflow method, flow unit and actual artifact digests without changing weights'},
        'current_tasks': {x['task']['id']: state(x) for x in runner.discover_tasks(ROOT / 'tests')}})


if __name__ == '__main__': main()
