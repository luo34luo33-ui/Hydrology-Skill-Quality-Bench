"""Host-only native verification from public code, using existing trusted recipes."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'scripts'))
from harness import grader, runner, reporter
from harness.atomic_contracts import tree_digest, VERSION, digest
from scripts import verify_data_tasks as data_tools, verify_modeling_tasks as model_tools, verify_hydrobase_tasks as spatial_tools
import atomic_tasks


def factory(domain, name):
    path = ROOT / 'tests' / domain / (name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return module


def layout(public, destination):
    index = json.loads((public / 'programs.json').read_text(encoding='utf-8'))
    for ref in index:
        shutil.copytree(public / 'programs' / ref, destination / ref / 'examples')
        assets = public / 'programs' / ref.split('/')[0] / 'assets'
        if assets.is_dir(): shutil.copytree(assets, destination / ref / 'assets')
    return index


def run_command(command, workspace, public, records):
    script = Path(command[1])
    command = [sys.executable, '-X', 'utf8', str(public / 'native_bootstrap.py'), str(script), *map(str, command[2:])]
    env = dict(os.environ, PYTHONUTF8='1', MPLBACKEND='Agg')
    wbt = ROOT / '.cache/whitebox/extracted/WhiteboxTools_win_amd64/WBT'
    if (wbt / 'whitebox_tools.exe').is_file():
        env['WBT_PATH'] = str(wbt); env['HSQB_WHITEBOX_DIR'] = str(wbt)
        if script.name == 'extract_dem_stream_network.py' and '--whitebox-dir' not in command:
            command.extend(['--whitebox-dir', str(wbt.resolve())])
    p = subprocess.run(command, cwd=workspace, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900)
    records.append({'entrypoint': script.name, 'exit_code': p.returncode,
                    'stderr': p.stderr[-1600:] if p.returncode else '', 'stdout': p.stdout[-600:] if p.returncode else ''})
    return p.returncode


def commands(task, ws, skills, scratch):
    tid = task['id']; group, number = tid.rsplit('-', 1); n = int(number)
    if tid.startswith(model_tools.TASK_PREFIXES): return [c for c, _ in model_tools.commands_for(tid, ws, skills)[0]]
    if any(tid.startswith(k) for k in data_tools.SKILL_SCRIPTS): return [data_tools.command_for(tid, ws, skills)[0]]
    if tid.startswith(spatial_tools.TASK_PREFIXES):
        if tid.startswith('hydromodel-topmodel-'):
            terrain = [sys.executable, str(skills / spatial_tools.TERRAIN_SCRIPT), '--stream-result', 'stream_result.json',
                       '--topology-result', 'build_result.json', '--topology-qc-result', 'topology_qc_result.json',
                       '--classes', '10', '--distance-bins', '10', '--minimum-slope', '1e-4', '--output-dir', str(ws / 'terrain-run')]
            return [terrain, spatial_tools.command_for(tid, ws, skills)[0]]
        return [spatial_tools.command_for(tid, ws, skills)[0]]
    index = json.loads((ROOT / 'runtime/atomic-public/programs.json').read_text(encoding='utf-8'))
    ref = task['primary_skill']; script = skills / ref / 'examples' / index[ref]['entrypoint']
    base = [sys.executable, str(script)]
    if group == 'hydrodata-baseflow':
        alpha = re.search(r'alpha=(\d+(?:\.\d+)?)', task['prompt']); bfi = re.search(r'BFImax=(\d+(?:\.\d+)?)', task['prompt'])
        args = ['--prepare-result', 'prepared/result.json', '--bfi-max', bfi.group(1), '--output-dir', 'components']
        args += ['--alpha', alpha.group(1)] if alpha else ['--estimate-alpha']
        return [base + args]
    if group == 'hydrodata-flood-events':
        return [base + ['--baseflow-result', 'components/result.json', '--config', 'event_config.yaml',
                        '--rainfall', 'rainfall.csv', '--rainfall-metadata', 'rainfall_metadata.json',
                        '--output-format', 'csv', '--per-event-format', 'csv', '--event-filename-by',
                        'peak-time' if n == 4 else 'event-id', '--output-dir', 'events']]
    if group == 'hydrodata-timeseries':
        table = task['data_files'][0]
        time_col = {1: 'observed_at', 2: 'serial_date', 4: 'time_recorded'}.get(n, 'timestamp')
        flow_col = {1: 'flow_cfs', 2: 'flow_l_s', 3: 'discharge', 4: 'q'}.get(n, 'flow')
        args = ['--input', table, '--time-column', time_col, '--flow-column', flow_col,
                '--flow-unit', {1: 'cfs', 2: 'L/s'}.get(n, 'm3/s'),
                '--timezone', {1: 'Asia/Shanghai', 2: 'naive'}.get(n, 'UTC'), '--output-dir', 'prepared']
        if n == 2: args += ['--sheet', 'observations']
        if n in (3, 7): args += ['--missing-policy', 'interpolate', '--max-interpolation-gap-hours', '2']
        if n == 4: args += ['--edge-missing', 'trim']
        if n == 5: args += ['--duplicate-policy', 'last']
        return [base + args]
    if group.startswith('hydroanalysis-'):
        if group == 'hydroanalysis-ml-correct':
            m = factory('results-analysis', '_mlcorrect_task_factory'); runs = m._golden_runs(tid, ws)
        else:
            m = factory('results-analysis', '_diagnostics_task_factory'); runs = [m._golden_command(tid)]
            output = m.CAPABILITIES[m._capability(tid)]['output']
            runs[0][0].extend(['--output-dir', str(ws / output)])
        return [[sys.executable, str(script), *c[2:]] for c, _ in runs]
    if ref.startswith('model-calibration/'):
        output = next(p.split('/')[0] for p in task['required_outputs'])
        return [base + ['--problem', 'calibration-problem.json', '--optimizer-config', 'optimizer-config.json', '--output-dir', output]]
    if ref.startswith('spatial-analysis/'):
        m = factory('spatial-analysis', '_spatial_task_factory'); data = scratch / 'data'; data.mkdir()
        if group == 'hydrodata-dem-grid':
            args, _, _, _, basin = m.prepare_inputs(n, data)
            return [base + ['--dem', 'source_dem.tif', '--basin', basin.name, *args, '--output-dir', 'prepared']]
        if group == 'hydrodata-stream-network':
            threshold, _, _ = m.stream_dem(n, data)
            return [base + ['--analysis-dem', 'analysis_dem.tif', '--stream-init-area-km2', str(threshold), '--output-dir', 'hydrology']]
        if group == 'hydrodata-topology-build':
            args, _, _ = m.topology_arrays(n, data)
            args = [str(x).replace(str(data), str(ws)) for x in args]
            return [base + ['--basin', 'basin.gpkg', '--dem-filled', 'dem_filled.tif', '--d8-pointer', 'd8_pointer.tif',
                           '--flow-accumulation', 'flow_accumulation_cells.tif', '--stream-links', 'stream_links.tif',
                           '--stream-order', 'strahler_order.tif', '--subbasins', 'subbasins.tif', *args, '--output-dir', 'hydrobase']]
        if group == 'hydrodata-topology-validate':
            count = re.search(r'outlet count (\d+)', task['prompt']).group(1)
            return [base + ['--build-result', 'hydrobase/result.json', '--expected-outlets', count, '--output-dir', 'topology-qc']]
    raise ValueError('No trusted verification recipe: ' + tid)


def main():
    p = argparse.ArgumentParser(); p.add_argument('--task-id'); p.add_argument('--resume', action='store_true'); args = p.parse_args()
    public = ROOT / 'runtime/atomic-public'; receipt_path = ROOT / 'docs/atomic-public-native.json'
    results = []
    if args.resume and receipt_path.exists():
        old = json.loads(receipt_path.read_text(encoding='utf-8'))
        if old['public_programs_sha256'] != tree_digest(public): raise ValueError('public bundle changed; cannot resume')
        results = old['tasks']
    with tempfile.TemporaryDirectory(prefix='hsqb-public-native-', ignore_cleanup_errors=True) as temporary:
        temp = Path(temporary); skills = temp / 'skills'; layout(public, skills)
        for item in runner.discover_tasks(ROOT / 'tests', test_id=args.task_id):
            task = item['task']; tid = task['id']; group = tid.rsplit('-', 1)[0]
            task_binding = {'task': digest(item['task_path']), 'data': tree_digest(item['task_dir'] / 'data'),
                            'expected': tree_digest(item['task_dir'] / 'expected'), 'grader': digest(ROOT / 'harness/grader.py')}
            if any(r['task_id'] == tid and r.get('passed') and r.get('task_binding') == task_binding for r in results): continue
            results = [r for r in results if r['task_id'] != tid]
            workspace = temp / tid; shutil.copytree(item['task_dir'] / 'data', workspace)
            scratch = temp / (tid + '-scratch'); scratch.mkdir(); executions = []
            try:
                if group in atomic_tasks.GROUPS:
                    recipe = json.loads((item['task_dir'] / 'expected/recipe.json').read_text(encoding='utf-8'))
                    original_invoke = atomic_tasks.invoke
                    def invoke(script, arguments, directory, expected=0):
                        code = run_command([sys.executable, str(script), *arguments], directory, public, executions)
                        if code != expected: raise RuntimeError(f'native exit {code}, expected {expected}: ' + executions[-1]['stderr'])
                    atomic_tasks.invoke = invoke
                    try: atomic_tasks.execute(group, recipe['steps'], workspace, skills)
                    finally: atomic_tasks.invoke = original_invoke
                else:
                    for command in commands(task, workspace, skills, scratch): run_command(command, workspace, public, executions)
                result = grader.grade_task(task, workspace, item['task_dir'])
                record = {'task_id': tid, 'score': result['score'], 'passed': result['score'] >= 1 - 1e-12, 'executions': executions}
                if not record['passed']: record['criteria'] = result['criteria']
            except Exception as exc:
                record = {'task_id': tid, 'passed': False, 'error': str(exc), 'executions': executions}
            results.append(record)
            record['task_binding'] = task_binding
            reporter.write_json(receipt_path, {'method': 'Public code, existing host-only recipes, fresh copies of original input; no Agent/API.',
                'version': VERSION, 'public_programs_sha256': tree_digest(public), 'tasks': results,
                'passed': sum(r['passed'] for r in results), 'total': len(results), 'real_agent_runs': 0})
            print(tid, 'PASS' if record['passed'] else 'FAIL', flush=True)
    return 0 if all(r['passed'] for r in results) else 1


if __name__ == '__main__': raise SystemExit(main())
