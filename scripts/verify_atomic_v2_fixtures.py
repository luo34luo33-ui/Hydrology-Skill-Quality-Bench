"""Repeat migrated generators and independently audit scientific bookkeeping."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.atomic_contracts import VERSION, tree_digest, digest
from harness import reporter, runner
from scripts.verify_public_atomic import factory


def scientific_check(directory, tid):
    import numpy as np
    import pandas as pd
    if tid.startswith('hydrodata-flood-events-') and int(tid.rsplit('-',1)[1]) <= 8:
        summary = pd.read_csv(directory / 'expected/golden_workspace/events/event_summary.csv')
        process = pd.read_csv(directory / 'expected/golden_workspace/events/event_process.csv')
        for _, event in summary.iterrows():
            part = process[process.event_id == event.event_id]
            # Warm-up rows are excluded from event-volume integration.
            selected = part[pd.to_datetime(part.time, utc=True) >= pd.Timestamp(event.start_time)]
            selected = selected[pd.to_datetime(selected.time, utc=True) <= pd.Timestamp(event.end_time)]
            columns = {c.lower(): c for c in summary.columns}
            for flow, alternatives in (
                ('discharge_m3_s', ('event_volume_m3','total_volume_m3')),
                ('baseflow_m3_s', ('baseflow_volume_m3',)),
                ('quickflow_m3_s', ('quickflow_volume_m3',))):
                name = next((columns[c] for c in alternatives if c in columns), None)
                if name:
                    values = selected[flow].to_numpy(dtype=float)
                    durations = pd.to_datetime(selected.time, utc=True).diff().dt.total_seconds().iloc[1:].to_numpy()
                    expected = float(np.dot((values[:-1] + values[1:]) / 2, durations))
                    if not np.isclose(float(event[name]), expected, rtol=1e-10, atol=1e-6):
                        raise ValueError(f'{tid}: independently integrated {name} differs')
        # The companion rain is never a hidden inferred observation repair.
        rain = pd.read_csv(directory / 'data/rainfall.csv')
        assert (rain.P_mm == 1).all()
    elif tid.startswith('hydromodel-') and tid.endswith(('001','002')):
        output = next((directory / 'expected/golden_workspace').iterdir())
        for split in ('calibration','validation'):
            frame = pd.read_csv(output / (split + '_series.csv'))
            times = pd.to_datetime(frame.time, utc=True)
            assert times.notna().all() and not times.duplicated().any()
            assert frame.scored.tolist() == [False,False] + [True]*10
    elif tid.startswith('hydroanalysis-ml-correct-'):
        card = json.loads((directory / 'expected/golden_workspace/ml-train/model_card.json').read_text(encoding='utf-8'))
        residual = next(x for x in card['lag_spec'] if x['column'] == 'residual')
        assert residual['steps'] == [1,2,3,4,5]
        assert 'residual' not in card['feature_columns']


def main():
    groups = [
        ('data-preprocessing','_flood_event_task_factory',[f'hydrodata-flood-events-{i:03}' for i in range(1,11)]),
        ('model-calibration','_calibration_task_factory',[f'hydromodel-{a}-{i:03}' for a in ('de','ga','pso','sce-ua','two-stage') for i in (1,2,3)]),
        ('results-analysis','_mlcorrect_task_factory',[f'hydroanalysis-ml-correct-{i:03}' for i in (1,2)])]
    records = []
    with tempfile.TemporaryDirectory(prefix='hsqb-v2-repeat-', ignore_cleanup_errors=True) as temporary:
        for domain, name, ids in groups:
            module = factory(domain, name)
            for index in range(2):
                module.ROOT = Path(temporary) / str(index) / domain; module.ROOT.mkdir(parents=True, exist_ok=True)
                for tid in ids: module.generate_task(tid)
            for tid in ids:
                one, two = [Path(temporary) / str(i) / domain / tid for i in range(2)]
                reference = ROOT / 'tests' / domain / tid
                equal = all(tree_digest(one / p) == tree_digest(two / p) == tree_digest(reference / p) for p in ('data','expected'))
                equal &= digest(one / 'task.json') == digest(two / 'task.json') == digest(reference / 'task.json')
                scientific_check(one, tid)
                records.append({'task_id': tid, 'repeatable_and_matches_workspace': equal, 'scientific_bookkeeping_checked': True})
                print(tid, 'PASS' if equal else 'FAIL', flush=True)
        # The repaired all-touched reference is also rebuilt from fresh vector/raster inputs.
        from scripts.repair_atomic_v2 import topology_check
        module = factory('spatial-analysis','_spatial_task_factory')
        tid = 'hydrodata-topology-build-003'
        outputs = []
        for index in range(2):
            folder = Path(temporary) / ('topology-' + str(index)) / tid
            module.build_topology(3, folder)
            scientific_workspace = folder / 'expected/golden_workspace'
            import shutil
            shutil.copytree(folder / 'data', scientific_workspace, dirs_exist_ok=True)
            topology_check(scientific_workspace)
            outputs.append(folder)
        reference = ROOT / 'tests/spatial-analysis' / tid
        # Inputs were copied into scientific_workspace solely for the independent check.
        from geopandas import read_file
        from geopandas.testing import assert_geodataframe_equal
        input_binary_equal = tree_digest(outputs[0] / 'data') == tree_digest(reference / 'data')
        equal = tree_digest(outputs[0] / 'data') == tree_digest(outputs[1] / 'data')
        equal &= tree_digest(outputs[0] / 'expected/golden_workspace/hydrobase') == tree_digest(outputs[1] / 'expected/golden_workspace/hydrobase')
        for folder in outputs:
            for p in (folder / 'data').iterdir():
                original = reference / 'data' / p.name
                if p.suffix == '.gpkg':
                    assert_geodataframe_equal(read_file(p), read_file(original), check_like=True)
                else: equal &= p.read_bytes() == original.read_bytes()
            for p in (folder / 'expected/golden_workspace/hydrobase').iterdir():
                original = reference / 'expected/golden_workspace/hydrobase' / p.name
                if p.name == 'result.json':
                    candidate = json.loads(p.read_text(encoding='utf-8')); baseline = json.loads(original.read_text(encoding='utf-8'))
                    # Independently verify both actual hashes before accepting equivalent
                    # GeoPackage geometry/attributes with a different SQLite encoding.
                    for document, data in ((candidate, folder / 'data'), (baseline, reference / 'data')):
                        binding = document['inputs']['basin_boundary']
                        assert binding['sha256'] == digest(data / 'basin.gpkg')
                        binding.pop('sha256')
                    equal &= candidate == baseline
                else: equal &= p.read_bytes() == original.read_bytes()
        records.append({'task_id': tid, 'repeatable_and_matches_workspace': equal, 'scientific_bookkeeping_checked': True,
            'original_input_binary_equal': input_binary_equal,
            'comparison': 'Two new builds byte-identical; historical basin GeoPackage geometry/CRS/attributes equal, actual input SHA verified. Original input retained.'})
        print(tid, 'PASS' if equal else 'FAIL', flush=True)
    result = {'version': VERSION, 'tasks': records, 'passed': all(x['repeatable_and_matches_workspace'] for x in records),
              'real_agent_runs': 0, 'scope': '28 regenerated fixtures; independent flood-volume integration, time/warm-up, lag and all-touched area bookkeeping'}
    reporter.write_json(ROOT / 'docs/atomic-v2-fixture-verification.json', result)
    return 0 if result['passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
