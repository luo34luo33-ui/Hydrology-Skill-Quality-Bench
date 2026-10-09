"""Generate and verify the 43 missing atomic benchmarks using deterministic tools."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET  # Load stdlib expat before spatial DLLs.

import numpy as np
import pandas as pd

import atomic_fixture_support as f

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SKILLS = Path(r'E:\HydroTune-Skills（仿BioSkills版）')
GROUPS = {
    'hydroanalysis-bma': ('post-processing/ensemble-discharge-with-bma', 'ensemble_discharge_bma.py', 8),
    'hydrovisual-dem-atlas': ('visualization-reporting/visualize-dem-hydrology-atlas', 'render_dem_hydrology_atlas.py', 4),
    'hydrovisual-flood-atlas': ('visualization-reporting/visualize-flood-event-atlas', 'render_flood_event_atlas.py', 4),
    'hydrovisual-hydrobase-atlas': ('visualization-reporting/visualize-hydrobase-atlas', 'render_hydrobase_atlas.py', 4),
    'hydrovisual-calibration-atlas': ('visualization-reporting/visualize-model-calibration', 'render_model_calibration_atlas.py', 5),
    'hydroreport-timeseries': ('visualization-reporting/generate-timeseries-data-processing-report', 'generate_timeseries_data_processing_report.py', 3),
    'hydroreport-spatial': ('visualization-reporting/generate-spatial-data-processing-report', 'generate_spatial_data_processing_report.py', 3),
    'hydroreport-study': ('visualization-reporting/generate-hydrological-study-report', 'generate_hydrological_study_report.py', 5),
    'hydroreport-review': ('visualization-reporting/review-hydrological-study-report', 'review_hydrological_study_report.py', 7),
}
SCENARIOS = {
 'hydroanalysis-bma': ['continuous train and predict', 'complete event train and predict', 'duplicate member warning', 'overlapping prediction period', 'missing fixed member', 'member hash mismatch', 'constant observations', 'nonconvergence diagnostics'],
 'hydrovisual-dem-atlas': ['full four maps', 'prepare only two maps', 'upstream warning', 'upstream hash mismatch'],
 'hydrovisual-flood-atlas': ['confirmed basin rainfall', 'partial rainfall coverage', 'zero events', 'upstream hash mismatch'],
 'hydrovisual-hydrobase-atlas': ['three maps', 'upstream warning', 'scientific FAIL dashboard only', 'upstream hash mismatch'],
 'hydrovisual-calibration-atlas': ['continuous calibration', 'event collection', 'comparison and continuous event slices', 'missing rainfall', 'comparison coverage mismatch'],
 'hydroreport-timeseries': ['explicit classes and significant peaks', 'unavailable analysis without parameters', 'damaged upstream'],
 'hydroreport-spatial': ['topology and independent validation', 'missing independent validation', 'damaged upstream'],
 'hydroreport-study': ['process-supported controlled narrative', 'missing process evidence', 'incomplete narrative', 'overlapping splits', 'immutable evidence modified'],
 'hydroreport-review': ['study report passes', 'timeseries report passes', 'spatial report passes', 'missing semantic review', 'numeric tampering', 'unsupported narrative', 'source hash mismatch'],
}

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def script(skills, group):
    ref, name, _ = GROUPS[group]
    return skills / ref / 'examples' / name

def invoke(path, args, cwd, code=0):
    completed = f.run(path, *args, cwd=cwd)
    if completed.returncode != code:
        diagnostic=''
        if '--output-dir' in args:
            out=cwd/args[args.index('--output-dir')+1]
            if (out/'review.json').exists(): diagnostic=json.dumps(f.read(out/'review.json').get('findings'),ensure_ascii=False)[:6000]
        raise RuntimeError(f'{path.name}: exit {completed.returncode}, expected {code}\n{completed.stderr[-6000:]}\n{diagnostic}')

def normalize_tree(root):
    """Relativize local JSON references; repair hashes after changing referenced JSON."""
    root = root.resolve()
    files = sorted(root.rglob('*.json'))
    def transform(value, folder):
        if isinstance(value, dict): return {k: transform(v, folder) for k,v in value.items()}
        if isinstance(value, list): return [transform(v, folder) for v in value]
        if isinstance(value, str):
            path = Path(value)
            if path.is_absolute():
                try:
                    path.relative_to(root)
                    return os.path.relpath(path, folder).replace('\\','/')
                except ValueError: pass
        return value
    for path in files: f.write(path, transform(f.read(path), path.parent))
    def rehash(value, folder):
        if isinstance(value, dict):
            if isinstance(value.get('path'), str) and 'sha256' in value:
                target = folder / value['path']
                if target.is_file(): value['sha256'] = digest(target)
            for v in value.values(): rehash(v, folder)
        elif isinstance(value, list):
            for v in value: rehash(v, folder)
    for _ in range(12):
        changed = False
        for path in files:
            before = path.read_bytes(); doc=f.read(path); rehash(doc,path.parent); f.write(path,doc)
            changed |= before != path.read_bytes()
        if not changed: break

def damage_reference(result):
    doc=f.read(result)
    next(iter(doc['artifacts'].values()))['sha256']='0'*64
    f.write(result,doc)

def portable_report(root, restore=False):
    """Rebind only administrative absolute paths in a staged report package.

    Native report v2 embeds absolute evidence locators. Preserve scientific
    fields and paragraph text; use a public relocation marker for portability.
    """
    folder=root/'report'
    def convert(value):
        if isinstance(value,dict): return {k:convert(v) for k,v in value.items()}
        if isinstance(value,list): return [convert(v) for v in value]
        if isinstance(value,str):
            if restore: return value.replace('@WORKSPACE@',str(root.resolve()))
            return value.replace(str(root.resolve()),'@WORKSPACE@').replace(root.resolve().as_posix(),'@WORKSPACE@')
        return value
    for path in folder.glob('*.json'): f.write(path,convert(f.read(path)))
    for path in folder.glob('*.csv'):
        text=path.read_text(encoding='utf-8-sig')
        path.write_text(convert(text),encoding='utf-8-sig')
    doc=f.read(folder/'report.json');mapping={}
    for evidence in doc['evidence']:
        if evidence['id'].startswith('ev-'):
            identity=f"{evidence['source_id']}|{evidence['artifact']}|{evidence['locator']}"
            mapping[evidence['id']]='ev-'+hashlib.sha256(identity.encode()).hexdigest()[:20]
    for path in list(folder.glob('*.json'))+list(folder.glob('*.csv'))+list(folder.glob('*.md')):
        text=path.read_text(encoding='utf-8-sig')
        for old,new in mapping.items(): text=text.replace(old,new)
        path.write_text(text,encoding='utf-8-sig' if path.suffix=='.csv' else 'utf-8')
    # Native report-result artifact references must match this package's bytes.
    result=folder/'result.json';doc=f.read(result)
    for reference in doc.get('artifacts',{}).values():
        path=folder/reference['path']
        if path.exists(): reference['sha256']=digest(path)
    f.write(result,doc)

def spatial_fixture(root, skills):
    import geopandas as gpd
    import rasterio
    from rasterio.transform import from_origin
    from shapely.geometry import box
    root.mkdir(parents=True)
    # Reuse the committed native Whitebox fixture: atlas tasks do not test
    # extraction, and do not need a network download of the Whitebox binary.
    upstream=REPO/'tests/spatial-analysis/hydrodata-stream-network-001'
    shutil.copyfile(upstream/'data/analysis_dem.tif',root/'dem.tif')
    shutil.copytree(upstream/'expected/golden_workspace/hydrology',root/'extract')
    with rasterio.open(root/'dem.tif') as src:
        b=src.bounds; margin=abs(src.res[0]); crs=src.crs
    gpd.GeoDataFrame({'basin_id':[1]},geometry=[box(b.left+margin,b.bottom+margin,b.right-margin,b.top-margin)],crs=crs).to_file(root/'basin.gpkg',layer='basin',driver='GPKG')
    doc=f.read(root/'extract/result.json');doc['inputs']['analysis_dem']={'path':'../dem.tif','sha256':digest(root/'dem.tif')};f.write(root/'extract/result.json',doc)
    calls=[('prepare-dem-analysis-grid','prepare_dem_analysis_grid.py',['--dem','dem.tif','--basin','basin.gpkg','--analysis-buffer-km',str(margin/1000),'--vertical-unit','m','--output-dir','prepare']),
           ('build-hydrological-topology','build_hydrological_topology.py',['--basin','prepare/basin_normalized.gpkg','--dem-filled','extract/dem_filled.tif','--d8-pointer','extract/d8_pointer.tif','--flow-accumulation','extract/flow_accumulation_cells.tif','--stream-links','extract/stream_links.tif','--stream-order','extract/strahler_order.tif','--subbasins','extract/subbasins.tif','--cell-inclusion','center','--upstream-result','prepare/result.json','--upstream-result','extract/result.json','--output-dir','build'])]
    for ref,name,args in calls:
        invoke(skills/'spatial-analysis'/ref/'examples'/name,args,root)
        if ref=='prepare-dem-analysis-grid':
            with rasterio.open(root/'dem.tif') as a, rasterio.open(root/'prepare/dem_analysis_buffer.tif') as b:
                if a.transform!=b.transform or a.crs!=b.crs or not np.array_equal(a.read(),b.read()):
                    raise ValueError('Reused native extraction does not match prepared scientific grid')
            doc=f.read(root/'extract/result.json');doc['inputs']['analysis_dem']={'path':'../prepare/dem_analysis_buffer.tif','sha256':digest(root/'prepare/dem_analysis_buffer.tif')};f.write(root/'extract/result.json',doc)
    reaches=gpd.read_file(root/'build/reaches_clipped.gpkg',layer='reaches')
    invoke(skills/'spatial-analysis/validate-hydrological-topology/examples/validate_hydrological_topology.py',['--build-result','build/result.json','--expected-outlets',str(int(reaches.is_outlet.sum())),'--output-dir','validate'],root)
    normalize_tree(root)

def cache_fixture(kind, skills):
    cache=REPO/'.cache/atomic-fixtures'/kind
    if not (cache/'ready.json').exists():
        if cache.exists(): shutil.rmtree(cache)
        if kind=='spatial': spatial_fixture(cache,skills)
        elif kind=='flood':
            f._pipeline(skills,cache)
            # Stable, simple names for task consumers.
            for old,new in [('01 准备（结果）','prepare'),('02 基流（结果）','baseflow'),('03 事件（结果）','events')]:
                (cache/old).rename(cache/new)
            # Existing absolute references contain pre-rename names.
            for p in cache.rglob('*.json'):
                text=p.read_text(encoding='utf-8')
                for old,new in [('01 准备（结果）','prepare'),('02 基流（结果）','baseflow'),('03 事件（结果）','events')]: text=text.replace(old,new)
                p.write_text(text,encoding='utf-8')
            normalize_tree(cache)
        else:
            cache.mkdir(parents=True)
            shape='event_collection' if kind=='calibration-event' else 'continuous'
            problem,config=f._write_fixture(cache,'ga',shape)
            invoke(skills/'model-calibration/calibrate-model-ga/examples/calibrate_model_ga.py',['--problem',problem.name,'--optimizer-config',config.name,'--output-dir','calibration'],cache)
            normalize_tree(cache)
        f.write(cache/'ready.json',{'fixture':kind})
    return cache

def copy_fixture(kind, dest, skills):
    shutil.copytree(cache_fixture(kind,skills),dest,dirs_exist_ok=True)
    (dest/'ready.json').unlink()

def add_step(steps, args, code=0, action=None):
    steps.append(dict(args=list(map(str,args)),code=code,action=action))

def setup_bma(data, n, skills):
    mode='event' if n==2 else 'continuous'
    invoke(skills/'post-processing/ensemble-discharge-with-bma/examples/make_synthetic_example.py',['--output-dir',str(data),'--mode',mode],REPO)
    normalize_tree(data)
    if n==5:
        table=pd.read_csv(data/'HBV.csv');table['Q']=0.8*table['Q']+4;table.to_csv(data/'Alt.csv',index=False)
        doc=f.read(data/'HBV-result.json');doc['artifacts']['simulation_table']={'path':'Alt.csv','sha256':digest(data/'Alt.csv')};f.write(data/'Alt-result.json',doc)
        manifest=f.read(data/'members.json');manifest['members'].append(dict(model_id='HBV-alt',outlet_id='synthetic-outlet',simulation_result='Alt-result.json'));f.write(data/'members.json',manifest)
    if n==3:
        shutil.copyfile(data/'HBV.csv',data/'Tank.csv')
        normalize_tree(data)
    if n==6: damage_reference(data/'HBV-result.json')
    if n==7:
        table=pd.read_csv(data/'observed.csv');table['discharge_m3_s']=1;table.to_csv(data/'observed.csv',index=False);normalize_tree(data)
    selectors=['--events','flood-001','flood-002'] if mode=='event' else ['--start','2020-01-01T00:00:00+08:00','--end','2020-01-10T23:00:00+08:00']
    train=['--mode','train','--members','members.json','--observed-result','observed-result.json','--random-state','2026','--output-dir','fit',*selectors]
    if n==8: train+=['--max-iter','1','--tol','1e-15']
    steps=[];add_step(steps,train,2 if n in (6,7,8) else 0)
    if n in (1,2,4,5):
        selectors=['--events','flood-003'] if mode=='event' else ['--start','2020-01-11T00:00:00+08:00','--end','2020-01-15T23:00:00+08:00']
        if n==4: selectors=['--start','2020-01-10T00:00:00+08:00','--end','2020-01-15T23:00:00+08:00']
        members='members.json'
        if n==5:
            manifest=f.read(data/'members.json');manifest['members']=manifest['members'][:2];f.write(data/'prediction-members.json',manifest);members='prediction-members.json'
        add_step(steps,['--mode','predict','--members',members,'--model-result','fit/result.json','--output-dir','forecast',*selectors],2 if n in (4,5) else 0)
    return steps, ['fit','forecast'] if len(steps)>1 else ['fit']

def setup_atlas(data, group, n, skills):
    steps=[];args=[];code=0
    language='zh' if n%2 else 'en'
    if group in ('hydrovisual-dem-atlas','hydrovisual-hydrobase-atlas'):
        copy_fixture('spatial',data,skills)
        if group=='hydrovisual-dem-atlas':
            args=['--prepare-result','prepare/result.json']
            if n!=2: args+=['--extract-result','extract/result.json']
            result=data/'prepare/result.json'
            if n==3:
                doc=f.read(result);doc['status']='warning';doc['warnings']=['Synthetic upstream quality warning'];f.write(result,doc);normalize_tree(data)
        else:
            args=['--build-result','build/result.json','--validation-result','validate/result.json'];result=data/'build/result.json'
            if n==2:
                doc=f.read(data/'validate/result.json');doc['status']='warning';doc['warnings']=['Synthetic upstream QC evidence']
                doc['checks'][0]['status']='WARN';doc['message']='Synthetic upstream warning fixture';f.write(data/'validate/result.json',doc);normalize_tree(data)
            if n==3:
                import geopandas as gpd
                reaches=gpd.read_file(data/'build/reaches_clipped.gpkg',layer='reaches')
                shutil.rmtree(data/'validate')
                invoke(skills/'spatial-analysis/validate-hydrological-topology/examples/validate_hydrological_topology.py',['--build-result','build/result.json','--expected-outlets',str(int(reaches.is_outlet.sum())+1),'--output-dir','validate'],data,2)
                normalize_tree(data);code=2
        if n==4: damage_reference(result);code=1
    elif group=='hydrovisual-flood-atlas':
        copy_fixture('flood',data,skills)
        args=['--extract-result','events/result.json','--rainfall','流域 雨量.csv','--rainfall-metadata','雨量 元数据.json']
        if n==2:
            rain=pd.read_csv(data/'流域 雨量.csv').iloc[50:55].copy();rain.iloc[2,1]=np.nan;rain.to_csv(data/'流域 雨量.csv',index=False)
        if n==3:
            # Re-run extraction with a confirmed threshold that excludes all events.
            import yaml
            config=data/'事件 参数（显式）.yaml';doc=yaml.safe_load(config.read_text(encoding='utf-8'));doc['filters']['min_peak_flow_m3_s']=1e9;config.write_text(yaml.safe_dump(doc,sort_keys=False),encoding='utf-8')
            shutil.rmtree(data/'events')
            invoke(skills/'data-processing/extract-flood-events/examples/extract_flood_events.py',['--baseflow-result','baseflow/result.json','--config',config.name,'--rainfall','流域 雨量.csv','--rainfall-metadata','雨量 元数据.json','--output-format','csv','--per-event-format','csv','--output-dir','events'],data)
        normalize_tree(data)
        if n==4: damage_reference(data/'events/result.json');code=1
    else:
        copy_fixture('calibration-event' if n==2 else 'calibration',data,skills)
        args=['--calibration-result','calibration/result.json']
        if n==4:
            for path in (data/'calibration').glob('*_series.csv'):
                frame=pd.read_csv(path);frame.drop(columns=['precipitation']).to_csv(path,index=False)
            normalize_tree(data)
        if n in (3,5):
            table=pd.read_csv(data/'calibration/validation_series.csv');comparison=table[['time']].copy();comparison['corrected']=table.observed
            if n==5: comparison=comparison.iloc[:-1]
            comparison.to_csv(data/'comparison.csv',index=False)
            f.write(data/'comparisons.json',dict(schema_version='1.0',join_on=['time'],series=[dict(label='Corrected',path='comparison.csv',column='corrected',unit='m3/s',split='validation')]))
            args+=['--comparison-manifest','comparisons.json']
            if n==3:
                pd.DataFrame([dict(event_id='validation-event',start=table.time.iloc[2],end=table.time.iloc[7])]).to_csv(data/'validation-events.csv',index=False)
                f.write(data/'events.json',dict(schema_version='1.0',step_seconds=86400,events=dict(path='validation-events.csv',sha256=digest(data/'validation-events.csv'))))
                args+=['--event-manifest','events.json']
            else: code=1
    add_step(steps,[*args,'--language',language,'--output-dir','atlas'],code)
    return steps,['atlas']

def fill_narrative(workspace, skills, modify=None):
    f.GEN=skills/'visualization-reporting/generate-hydrological-study-report'
    path=workspace/'draft/report.json';doc=f.read(path)
    evidence=next(e for e in doc['evidence'] if e.get('kind')=='table_value' and e.get('locator','').endswith('/nse'))
    for sid in ('overview','evaluation','discussion','limitations'):
        next(s for s in doc['sections'] if s['id']==sid)['paragraphs']=[dict(id=sid,kind='inference',text='Conclusions apply only to the declared validation samples; missing process evidence limits attribution.',evidence_ids=[evidence['id']],numeric_bindings=[])]
    for diag in doc['analysis']['details']['diagnostics']:
        if not diag['available']: continue
        ev=next(e for e in doc['evidence'] if e['id'].startswith('process-') and e['value']['event_id']==diag['event_id'])
        next(s for s in doc['sections'] if s['id']=='discussion')['paragraphs'].append(dict(id='diagnosis-'+diag['event_id'],kind='inference',text='A timing mismatch is possible; routing causation remains unconfirmed.',evidence_ids=[ev['id']],numeric_bindings=[],diagnosis=dict(run=diag['run'],evaluation=diag['evaluation'],event_id=diag['event_id']),hypotheses=[dict(candidate='A routing timing mismatch is possible.',support='Linked observed and simulated peaks occur at different times.',limitations='Routing state evidence is unavailable.',validation='Inspect routing parameters and rainfall timestamps.')]))
    doc['narrative_provenance']=dict(author='deterministic-fixture-author',method='agent',completed=modify!='incomplete')
    if modify=='evidence': doc['evidence'][0]['value']='modified immutable evidence'
    f.write(path,doc)
    if modify is None:
        f.write(workspace/'conclusions.json',dict(evaluation_scope='validation',causal_status='unconfirmed',
            worst_event_ids=[e['event_id'] for e in doc['analysis']['details']['worst_events']],
            process_event_ids=[e['event_id'] for e in doc['analysis']['details']['diagnostics'] if e.get('available')]))

def execute(group, steps, workspace, skills):
    for step in steps:
        action=step.get('action')
        if action=='relocate-report': portable_report(workspace,restore=True)
        if action and action.startswith('narrative'): fill_narrative(workspace,skills,action.split(':')[-1] if ':' in action else None)
        if action and action.startswith('semantic'):
            fp=f.read(workspace/'review-initial/review.json')['package_fingerprint']
            path=f.semantic_file(workspace,workspace/'report',fp)
            if action=='semantic:unsupported':
                doc=f.read(path)
                for paragraph in doc['paragraphs']:
                    if paragraph['id']=='overview': paragraph['verdict']='unsupported'
                f.write(path,doc)
        invoke(script(skills,group),step['args'],workspace,step['code'])

def setup_report(data,group,n,skills):
    data.mkdir(parents=True,exist_ok=True);steps=[]
    f.GEN=skills/'visualization-reporting/generate-hydrological-study-report'
    if group=='hydroreport-timeseries':
        f.floods(data)
        if n==2:
            doc=f.read(data/'manifest.json');del doc['analysis'];f.write(data/'manifest.json',doc)
        normalize_tree(data)
        if n==3: damage_reference(data/'flow/result.json')
        add_step(steps,['--processing-manifest','manifest.json','--output-dir','report'],1 if n==3 else 0)
    elif group=='hydroreport-spatial':
        copy_fixture('spatial',data,skills)
        sources=[dict(id='topo',stage='spatial',result='build/result.json')]
        if n!=2: sources.append(dict(id='qc',stage='spatial',result='validate/result.json'))
        f.write(data/'manifest.json',dict(schema_version='1.0',title='Spatial processing',language='en' if n==2 else 'zh',required_sources=['topo'],sources=sources))
        normalize_tree(data)
        if n==3: damage_reference(data/'build/result.json')
        add_step(steps,['--spatial-manifest','manifest.json','--output-dir','report'],1 if n==3 else 0)
    elif group=='hydroreport-study':
        f.event_study(data)
        if n!=2: f.linked(data/'manifest.json',data)
        if n==4:
            doc=f.read(data/'manifest.json');doc['split_periods']['calibration']=doc['split_periods']['validation'];f.write(data/'manifest.json',doc)
        normalize_tree(data)
        add_step(steps,['prepare','--study-manifest','manifest.json','--output-dir','draft'],1 if n==4 else 0)
        if n!=4:
            action='narrative:incomplete' if n==3 else ('narrative:evidence' if n==5 else 'narrative')
            add_step(steps,['finalize','--study-manifest','manifest.json','--report-json','draft/report.json','--output-dir','report'],1 if n in (3,5) else 0,action)
    else:
        subgroup='hydroreport-timeseries' if n==2 else ('hydroreport-spatial' if n==3 else 'hydroreport-study')
        substeps,_=setup_report(data,subgroup,1,skills)
        execute(subgroup,substeps,data,skills)
        if (data/'draft').exists(): shutil.rmtree(data/'draft')
        portable_report(data)
        if n==5:
            doc=f.read(data/'report/report.json');ev=next(e for e in doc['evidence'] if e.get('locator','').endswith('/nse'));ev['value']=str(float(ev['value'])+0.25);f.write(data/'report/report.json',doc)
        if n==6:
            doc=f.read(data/'report/report.json');paragraph=next(s for s in doc['sections'] if s['id']=='overview')['paragraphs'][0]
            old=paragraph['text'];paragraph['text']='This validation proves that routing parameters caused all errors and the model will perform perfectly in every future flood.'
            f.write(data/'report/report.json',doc)
            markdown=data/'report/report.md';markdown.write_text(markdown.read_text(encoding='utf-8').replace(old,paragraph['text']),encoding='utf-8')
        if n==7: damage_reference(data/'sim/result.json')
        flag='--processing-manifest' if n==2 else ('--spatial-manifest' if n==3 else '--study-manifest')
        args=[flag,'manifest.json','--report-dir','report']
        add_step(steps,[*args,'--output-dir','review-initial'],1 if n==7 else 2,'relocate-report')
        if n in (1,2,3,6): add_step(steps,[*args,'--semantic-review','semantic.json','--output-dir','review-final'],2 if n==6 else 0,'semantic:unsupported' if n==6 else 'semantic')
    outputs=['review-initial','review-final'] if group=='hydroreport-review' and len(steps)>1 else (['review-initial'] if group=='hydroreport-review' else (['draft'] if group=='hydroreport-study' and n==4 else ['report']))
    return steps,outputs

def build(task_id, skills=DEFAULT_SKILLS, destination=None):
    group,n=task_id.rsplit('-',1);n=int(n)
    if group not in GROUPS or not 1<=n<=GROUPS[group][2]: raise ValueError(task_id)
    domain='results-analysis' if group=='hydroanalysis-bma' else 'visualization-reporting'
    task_dir=Path(destination) if destination else REPO/'tests'/domain/task_id
    task_dir.mkdir(parents=True,exist_ok=True)
    data=task_dir/'data'
    if data.exists(): shutil.rmtree(data)
    if group=='hydroanalysis-bma': steps,outputs=setup_bma(data,n,skills)
    elif group.startswith('hydrovisual'): steps,outputs=setup_atlas(data,group,n,skills)
    else: steps,outputs=setup_report(data,group,n,skills)
    with tempfile.TemporaryDirectory(prefix='hsqb-atomic-') as tmp:
        ws=Path(tmp);shutil.copytree(data,ws,dirs_exist_ok=True)
        execute(group,steps,ws,skills)
        golden=task_dir/'expected/golden_workspace'
        if golden.exists(): shutil.rmtree(golden)
        golden.mkdir(parents=True)
        for folder in outputs:
            if (ws/folder).exists(): shutil.copytree(ws/folder,golden/folder)
        # Include semantic artifacts required from the Agent, not supplied in data.
        if (ws/'semantic.json').exists(): shutil.copyfile(ws/'semantic.json',golden/'semantic.json')
        if group=='hydroreport-study' and n in (1,2): shutil.copyfile(ws/'conclusions.json',golden/'conclusions.json')
        from atomic_oracles import make_grading
        required,grading=make_grading(group,ws,outputs,task_dir)
    actions=''
    if group=='hydroreport-study': actions=' Between prepare and finalize, read the evidence, fill overview/evaluation/discussion/limitations paragraphs and narrative_provenance. Use stable paragraph IDs matching section IDs; for each available selected process add diagnosis-<event_id> with diagnosis and hypotheses (candidate/support/limitations/validation). State fact versus conditional inference and evidence gaps. Do not modify machine evidence. On completed-report cases also write conclusions.json with evaluation_scope (calibration/validation/combined), causal_status (established/unconfirmed), worst_event_ids in rank order, and process_event_ids with available selected process evidence. Derive these judgments from supplied evidence. For the incomplete-narrative case leave completed=false; for the immutable-evidence rejection case change only the first evidence value to a nonnumeric string before finalize.'
    if group=='hydroreport-review': actions=' Before review, replace the administrative @WORKSPACE@ relocation marker in report JSON/CSV with the absolute current workspace path. For each ev-* evidence ID recompute ev- plus the first 20 hex characters of SHA256(source_id + "|" + artifact_absolute_path + "|" + locator), and replace its references throughout report JSON/CSV/Markdown. Refresh report/result.json artifact hashes. This restores native absolute evidence locators and administrative IDs; change no scientific value, paragraph text or upstream file. Independently read every report paragraph and its original evidence. After initial review, create semantic.json outside report and review folders using the current package_fingerprint, exactly one verdict per paragraph, all original evidence_ids and a substantive rationale. Determine supported/unsupported/uncertain from evidence, then rerun when requested. After relocation do not modify the supplied report or sources.'
    commands='\n'.join('Stage '+str(i+1)+': '+(' '.join(step['args'])) for i,step in enumerate(steps))
    prompt=f'Use the {GROUPS[group][0]} capability on the supplied synthetic artifacts. Scenario: {SCENARIOS[group][n-1]}. Source outlet, units, timezone, splits and parameters in the explicit manifests are confirmed. Upstream inputs are read-only; do not rerun upstream models, infer missing settings, interpolate or repair failed evidence. Perform these stages using the native interface:\n{commands}\n'+actions+' Preserve native result status, diagnostic evidence and artifact hashes. On rejection remove partial normal deliverables prohibited by the skill, preserving its failure result and allowed diagnostics. Produce all applicable native outputs. Runtime compatibility: load stdlib pyexpat before rasterio; if Matplotlib removed boxplot labels, map that deprecated keyword to tick_labels without changing the data or plot.'
    task=dict(id=task_id,title=SCENARIOS[group][n-1],domain=domain,difficulty='advanced' if group in ('hydroanalysis-bma','hydroreport-study','hydroreport-review') else 'intermediate',primary_skill=GROUPS[group][0],secondary_skills=[],prompt=prompt,data_description='Deterministic synthetic evidence; upstream stages isolated by precomputed artifacts.',data_files=[p.relative_to(data).as_posix() for p in sorted(data.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc', '.pyo'}],required_outputs=required,setup_notes=['No hidden expected files are staged. Parameters are explicitly confirmed for this synthetic task.'],timeout_seconds=900 if group=='hydroanalysis-bma' else 600,grading=grading)
    f.write(task_dir/'task.json',task);f.write(task_dir/'expected/recipe.json',dict(group=group,steps=steps,outputs=outputs))
    factory='_bma_task_factory' if group=='hydroanalysis-bma' else ('_atlas_task_factory' if group.startswith('hydrovisual') else '_report_task_factory')
    generator=f'from pathlib import Path\nimport sys\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\nfrom {factory} import generate\nif __name__ == "__main__":\n    generate(Path(__file__).resolve().parent.name)\n'
    (task_dir/'generate_data.py').write_text(generator,encoding='utf-8')
    print(task_id, 'generated', flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skills-root',type=Path,default=Path(os.environ.get('HYDROTUNE_SKILLS_ROOT',str(DEFAULT_SKILLS)).strip().strip('"')));parser.add_argument('--group',choices=GROUPS);parser.add_argument('--task-id');args=parser.parse_args()
    if args.task_id: build(args.task_id,args.skills_root)
    else:
        for group in ([args.group] if args.group else GROUPS):
            for n in range(1,GROUPS[group][2]+1): build(f'{group}-{n:03}',args.skills_root)

if __name__=='__main__': main()
