"""Local synthetic fixture helpers adapted from HydroTune's acceptance examples.

These helpers create data, never invoke an Agent. Runtime roots are supplied by
the caller; no source-repository imports are used by committed task grading.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def write(path, value):
    path = Path(path)
    if path.name == 'task.json' and isinstance(value, dict):
        canonical = Path(__file__).resolve().parents[1] / 'tests' / value['domain'] / value['id'] / 'public_contract.json'
        if canonical.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            destination = path.parent / 'public_contract.json'
            if canonical.resolve() != destination.resolve(): destination.write_bytes(canonical.read_bytes())
            value = dict(value, public_contract='public_contract.json')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def run(script, *args, cwd=None):
    env = dict(os.environ, PYTHONUTF8="1", MPLBACKEND="Agg")
    # rasterio's bundled expat can shadow Conda's XML DLL on Windows. Load
    # stdlib XML first, then execute the unchanged native entrypoint.
    bootstrap = Path(__file__).with_name('atomic_native_bootstrap.py')
    return subprocess.run([sys.executable, "-X", "utf8", str(bootstrap), str(script), *map(str, args)], cwd=cwd,
                          capture_output=True, text=True, encoding="utf-8", env=env, timeout=900)

def source(tmp, sid, skill, artifacts, parameters=None):
    folder = tmp / sid
    folder.mkdir(parents=True, exist_ok=True)
    refs = {}
    for name, content in artifacts.items():
        path = folder / name
        path.write_text(content, encoding="utf-8")
        refs[name.replace('.', '_')] = {'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    path = folder / 'result.json'
    write(path, dict(schema_version='1.0', skill=skill, status='success', message='Synthetic benchmark evidence',
                     parameters=parameters or {}, inputs={}, artifacts=refs, checks=[], warnings=[], provenance={'fixture': True}))
    return path

def series_binding(path, column='Q'):
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), time_column='time', simulated_column=column, unit='m3/s')

def evaluation_input(result_path, content):
    path = result_path.parent / 'scored-input.csv'
    path.write_text(content, encoding='utf-8')
    doc = read(result_path)
    doc['inputs']['series'] = dict(path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    write(result_path, doc)

SPLIT_PERIODS = {'calibration': {'start': '2019-01-01T00:00:00Z', 'end': '2019-12-31T23:59:59Z'},
                 'validation': {'start': '2020-01-01T00:00:00Z', 'end': '2020-12-31T23:59:59Z'}}

def semantic_file(tmp, report, fingerprint, verdict='supported'):
    path = tmp / 'semantic.json'
    paragraphs = [p for s in read(report / 'report.json')['sections'] for p in s['paragraphs']]
    write(path, dict(schema_version='1.0', package_fingerprint=fingerprint, reviewer='deterministic-fixture-reviewer',
                     paragraphs=[dict(id=p['id'], evidence_ids=p['evidence_ids'], verdict=verdict,
                                      rationale='Checked the synthetic source value, scope and stated limitations.') for p in paragraphs]))
    return path

import yaml


def processing(tmp):
    source(tmp,'flow','data-processing/prepare-discharge-timeseries',{'series_metadata.json':'{"timezone":"Asia/Shanghai","standard_flow_unit":"m3/s","timestep_seconds":3600}'})
    p=tmp/'manifest.json'; write(p,dict(schema_version='1.0',title='预分析',required_sources=['flow'],sources=[dict(id='flow',stage='preprocessing',result='flow/result.json')]))
    return p


def floods(tmp):
    p=processing(tmp); summary='event_id,start_time,end_time,peak_flow_m3_s,total_volume_m3,duration_hours,n_local_peaks\n'
    process='event_id,time,discharge_m3_s,is_warmup\n'
    vals=[[0,2,1.9,2.1,0],[0,4,0,4,0],[5,4,3,2,1],[0,1,1,1,0]]
    for i,v in enumerate(vals):
        summary+=f'{i:04},2020-01-01T00:00:00,2020-01-01T04:00:00,{[9,10,20,30][i]},{[100,99,200,300][i]},4,99\n'
        process+=f'{i:04},2019-12-31T23:00:00,100,true\n'
        for h,q in enumerate(v): process+=f'{i:04},2020-01-01T0{h}:00:00,{q},false\n'
    source(tmp,'events','data-processing/extract-flood-events',{'event_summary.csv':summary,'event_process.csv':process})
    m=read(p);m['sources'].append(dict(id='events',stage='preprocessing',result='events/result.json'));m['required_sources'].append('events')
    m['analysis']=dict(peak_thresholds_m3_s=[10,20],volume_thresholds_m3=[100,200],significant_peaks=dict(prominence_m3_s=.5,minimum_spacing_hours=1))
    write(p,m);return p


def spatial(tmp):
    source(tmp,'topo','spatial-analysis/build-hydrological-topology',{
      'subbasins.csv':'sub_id,area_km2,reach_count\n1,2,2\n2,3,1\n',
      'reaches.csv':'reach_id,sub_id,length_m,downstream_reach_id,topo_level,strahler_order\n1,1,100,3,1,1\n2,1,200,3,1,1\n3,2,300,0,2,2\n',
      'topology.csv':'reach_id,sub_id,downstream_reach_id,topo_level\n1,1,3,1\n2,1,3,1\n3,2,0,2\n'},dict(crs='EPSG:32650',cell_area_m2=900))
    p=tmp/'manifest.json';write(p,dict(schema_version='1.0',title='空间报告',required_sources=['topo'],sources=[dict(id='topo',stage='spatial',result='topo/result.json')]))
    return p


def event_study(tmp):
    source(tmp,'sim','hydrological-modeling/run-lumped-hbv-model',{'simulation_table.csv':'time,Q\n2020-01-01T00:00:00Z,2\n2020-01-01T01:00:00Z,3\n2020-01-01T02:00:00Z,4\n'})
    scores=[-.5,-2,.3,-2,.8,None,.1]
    metrics='event_id,start,end,nse,peak_error_relative,volume_error_relative,peak_time_error_hours\n'
    for i,n in enumerate(scores):metrics+=f'e{i},2020-01-01T00:00:00Z,2020-01-01T02:00:00Z,{n if n is not None else "unavailable"},-0.1,0.2,1\n'
    source(tmp,'eval','evaluation-diagnostics/compute-event-flood-metrics',{'event_metrics.csv':metrics},dict(volume_unit='m3',timestep_hours=1))
    rows='event_id,time,Q_obs,Q_total\n'+''.join(f'e{i},2020-01-01T0{h}:00:00Z,{o},{s}\n' for i in range(7) for h,o,s in [(0,1,2),(1,4,3),(2,2,4)])
    evaluation_input(tmp/'eval/result.json',rows)
    p=tmp/'manifest.json';write(p,dict(schema_version='2.0',split_periods=SPLIT_PERIODS,title='Simulation',language='en',sources=[dict(id='sim',stage='simulation',result='sim/result.json'),dict(id='eval',stage='evaluation',result='eval/result.json',context=dict(mode='event_collection',split='validation',period=dict(start='2020-01-01T00:00:00Z',end='2020-01-01T02:00:00Z'),event_ids=[f'e{i}' for i in range(7)]))],runs=[dict(id='run',name='HBV',kind='baseline',series=series_binding(tmp/'sim/simulation_table.csv'),simulation='sim',evaluations=['eval'])]))
    return p


def prepare(p,out):
    r=run(GEN/'examples/generate_hydrological_study_report.py','prepare','--study-manifest',p,'--output-dir',out);assert r.returncode==0,r.stderr
    d=read(out/'report.json'); ev=next(e for e in d['evidence'] if e['kind']=='table_value' and e['locator'].endswith('/nse'))
    for sid in ('overview','evaluation','discussion','limitations'):
        next(s for s in d['sections'] if s['id']==sid)['paragraphs']=[dict(id=sid,kind='inference',text='Conclusions are restricted to the explicitly declared validation scope.',evidence_ids=[ev['id']],numeric_bindings=[])]
    for diag in d['analysis']['details']['diagnostics']:
        if not diag['available']:continue
        process=next(e for e in d['evidence'] if e['id'].startswith('process-') and e['value']['event_id']==diag['event_id'])
        next(s for s in d['sections'] if s['id']=='discussion')['paragraphs'].append(dict(id='diagnosis-'+diag['event_id'],kind='inference',text='The process suggests a possible response timing mismatch.',evidence_ids=[process['id']],numeric_bindings=[],diagnosis=dict(run=diag['run'],evaluation=diag['evaluation'],event_id=diag['event_id']),hypotheses=[dict(candidate='A routing timing mismatch is possible.',support='The linked hydrograph shows differing peak timing.',limitations='Rainfall timing and routing states are unavailable.',validation='Inspect rainfall timestamps and routing parameters before attributing cause.')]))
    d['narrative_provenance']=dict(author='fixture-agent',method='agent',completed=True);write(out/'report.json',d);return out/'report.json'


def linked(p,tmp):
    f=tmp/'process.csv';f.write_text('time,observed,simulated,is_warmup,scored,rain\n2019-12-31T23:00:00Z,100,0,true,false,0\n2020-01-01T00:00:00Z,1,2,false,true,1\n2020-01-01T01:00:00Z,4,3,false,true,0\n2020-01-01T02:00:00Z,2,4,false,true,0\n',encoding='utf-8')
    m=read(p);m['analysis']=dict(worst_event_count=1,event_processes=[dict(run_id='run',evaluation_source='eval',event_id='e1',path='process.csv',sha256=hashlib.sha256(f.read_bytes()).hexdigest(),time_column='time',observed_column='observed',simulated_column='simulated',warmup_column='is_warmup',scored_column='scored',precipitation_column='rain',precipitation_unit='mm/step')]);write(p,m);return f


ALGORITHMS = {
    "de": ("calibrate-model-de", "calibrate_model_de.py", {
        "population_multiplier": 3, "mutation_factor": 0.8, "crossover_probability": 0.7,
        "max_generations": 4, "tolerance": 1e-6, "polish": False,
    }),
    "ga": ("calibrate-model-ga", "calibrate_model_ga.py", {
        "population_size": 8, "max_generations": 4, "tournament_size": 3, "elite_count": 1,
        "crossover_probability": 0.8, "mutation_probability": 0.4, "gene_mutation_probability": 0.5,
    }),
    "pso": ("calibrate-model-pso", "calibrate_model_pso.py", {
        "particle_count": 8, "max_iterations": 5, "inertia_weight": 0.7,
        "cognitive_coefficient": 1.5, "social_coefficient": 1.5, "velocity_limit_fraction": 0.5,
    }),
    "sce-ua": ("calibrate-model-sce-ua", "calibrate_model_sce_ua.py", {
        "complex_count": 2, "points_per_complex": 4, "evolution_steps": 2, "max_loops": 3,
        "reflection_coefficient": 1.0, "contraction_coefficient": 0.5, "stall_loops": 3,
        "objective_tolerance": 1e-12,
    }),
    "two-stage": ("calibrate-model-two-stage", "calibrate_model_two_stage.py", {
        "annealing_max_evaluations": 30, "local_max_evaluations": 20,
        "annealing_max_iterations": 4, "local_max_iterations": 10, "initial_temperature": 5230.0,
        "restart_temperature_ratio": 0.0001, "visit": 2.62, "accept": -5.0, "local_ftol": 1e-7,
    }),
}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fixture(root: Path, algorithm: str, data_shape: str = "continuous") -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    adapter = root / "synthetic_adapter.py"
    adapter.write_text(
        """from __future__ import annotations
import numpy as np
import pandas as pd

class Evaluator:
    def __init__(self, problem): self.problem = problem
    def evaluate(self, parameters, split):
        if split != 'calibration': raise ValueError('search evaluate must use calibration split only')
        loss = (parameters['x'] - 0.25) ** 2 + (parameters['y'] - 0.75) ** 2
        score = 1.0 - loss
        return {'objective': score, 'metrics': {'score': score, 'rmse': loss ** 0.5}}
    def materialize(self, parameters, split):
        loss = (parameters['x'] - 0.25) ** 2 + (parameters['y'] - 0.75) ** 2
        score = 1.0 - loss
        result = {'objective': score, 'metrics': {'score': score, 'rmse': loss ** 0.5}}
        observed = np.linspace(1.0, 2.0, 12)
        shift = (parameters['x'] - 0.25) + (parameters['y'] - 0.75)
        frame = pd.DataFrame({'observed': observed, 'simulated': observed + shift, 'scored': [False, False] + [True] * 10, 'precipitation': np.linspace(0, 5, 12)})
        if self.problem['data_shape'] == 'continuous': frame.insert(0, 'time', pd.date_range('2020-01-01' if split == 'calibration' else '2021-01-01', periods=12, freq='D', tz='UTC'))
        else:
            frame.insert(0, 'event_id', (['C01'] * 6 + ['C02'] * 6) if split == 'calibration' else (['E01'] * 6 + ['E02'] * 6))
            frame.insert(1, 'step', list(range(6)) * 2)
        return {**result, 'series': frame}

def create_evaluator(problem, problem_dir): return Evaluator(problem)
""",
        encoding="utf-8",
    )
    model_input = root / "input.json"
    model_input.write_text('{"fixture": true}\n', encoding="utf-8")
    problem = {
        "schema_version": "1.0", "adapter": {"path": adapter.name, "sha256": _hash(adapter)},
        "inputs": [{"id": "fixture", "path": model_input.name, "sha256": _hash(model_input)}],
        "parameters": [{"name": "x", "lower": 0.0, "upper": 1.0}, {"name": "y", "lower": 0.0, "upper": 1.0}],
        "objective": {"metric": "score", "direction": "maximize"},
        "splits": {"calibration": "calibration", "validation": "validation"},
        "data_shape": data_shape, "warmup": {"confirmed": True, "semantics": "first two rows are unscored"},
        "variables": {"observed": {"semantics": "observed flow", "units": "m3/s"}, "simulated": {"semantics": "simulated flow", "units": "m3/s"}},
        "objective_consistency_tolerance": 1e-12,
    }
    problem_path = root / "calibration-problem.json"
    problem_path.write_text(json.dumps(problem, ensure_ascii=False, indent=2), encoding="utf-8")
    _, _, specific = ALGORITHMS[algorithm]
    config = {"schema_version": "1.0", "algorithm": algorithm, "seed": 42, "max_evaluations": 100, "max_failed_evaluations": 3, **specific}
    config_path = root / "optimizer-config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return problem_path, config_path


SCRIPTS = {
    "prepare": Path("data-processing/prepare-discharge-timeseries/examples/prepare_discharge_timeseries.py"),
    "baseflow": Path("data-processing/separate-baseflow-eckhardt/examples/separate_baseflow_eckhardt.py"),
    "extract": Path("data-processing/extract-flood-events/examples/extract_flood_events.py"),
    "atlas": Path("visualization-reporting/visualize-flood-event-atlas/examples/render_flood_event_atlas.py"),
}


def _source_frame(rows: int = 240) -> pd.DataFrame:
    index = np.arange(rows, dtype=float)
    discharge = 18.0 + 0.006 * index
    discharge += 170.0 * np.exp(-0.5 * ((index - 70.0) / 7.0) ** 2)
    discharge += 125.0 * np.exp(-0.5 * ((index - 175.0) / 10.0) ** 2)
    return pd.DataFrame({
        "when": pd.date_range("2020-01-01", periods=rows, freq="h"),
        "flow": discharge,
        "station_note": ["unconfirmed"] * rows,
    })


def _write_config(path: Path) -> None:
    document = {
        "schema_version": "1.2",
        "peak_detection": {"peak_quantile": 0.7, "prominence_factor": 0.05, "min_peak_distance_hours": 24},
        "boundaries": {"boundary_fraction": 0.05, "boundary_persistence_steps": 2, "max_search_days": 4},
        "merging": {"merge_gap_hours": 12, "valley_ratio_threshold": 0.8},
        "filters": {"min_event_duration_hours": 1, "min_peak_flow_m3_s": None, "min_event_volume_m3": None},
        "warmup": {"steps": 12},
        "rainfall_support": {"lookback_hours": 24, "min_observed_rainfall_mm": 5,
                             "no_rainfall_policy": "exclude", "missing_rainfall_policy": "exclude"},
    }
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _pipeline(repo: Path, root: Path, output_format: str = "csv") -> tuple[Path, Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    source = root / "输入 时序（合成）.csv"
    _source_frame().to_csv(source, index=False, encoding="utf-8-sig")
    prepare_dir = root / "01 准备（结果）"
    prepared = _run(
        repo, "prepare", "--input", source, "--time-column", "when", "--flow-column", "flow",
        "--flow-unit", "m3/s", "--timezone", "UTC", "--output-format", output_format,
        "--output-dir", prepare_dir,
    )
    assert prepared.returncode == 0, prepared.stderr
    baseflow_dir = root / "02 基流（结果）"
    separated = _run(
        repo, "baseflow", "--prepare-result", prepare_dir / "result.json", "--bfi-max", "0.8",
        "--alpha", "0.95", "--output-format", output_format, "--output-dir", baseflow_dir,
    )
    assert separated.returncode == 0, separated.stderr
    config = root / "事件 参数（显式）.yaml"
    _write_config(config)
    rainfall = root / "流域 雨量.csv"
    pd.DataFrame({"time": pd.date_range("2019-12-31", periods=264, freq="h", tz="UTC"),
                  "P_mm": np.ones(264)}).to_csv(rainfall, index=False)
    rain_meta = root / "雨量 元数据.json"
    rain_meta.write_text(json.dumps({"spatial_scope": "basin_mean", "unit": "mm/step", "timezone": "UTC",
                                    "timestep_seconds": 3600, "timestamp_semantics": "interval_end"}), encoding="utf-8")
    event_dir = root / "03 事件（结果）"
    extracted = _run(
        repo, "extract", "--baseflow-result", baseflow_dir / "result.json", "--config", config,
        "--rainfall", rainfall, "--rainfall-metadata", rain_meta,
        "--output-format", output_format, "--per-event-format", "csv", "--output-dir", event_dir,
    )
    assert extracted.returncode == 0, extracted.stderr
    return prepare_dir, baseflow_dir, event_dir

def _run(repo, key, *args):
    return run(repo / SCRIPTS[key], *args)
