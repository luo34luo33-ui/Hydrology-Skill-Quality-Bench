import json
from pathlib import Path
import shutil
import sys
import pandas as pd
import pytest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from composite_common import portable_tree,sha
from test_composite import copied,grade,item
from harness import runner

@pytest.mark.parametrize('task,path,column',[
 ('hydrochain-model-001','routed/routed_flow.csv','Q_total'),
 ('hydrochain-model-004','routed/routed_flow.csv','Q_total'),
 ('hydrochain-model-002','model/lumped_xaj_runoff.csv','Qt'),
 ('hydrochain-model-008','model/outlet_flow.csv','Q_m3s'),
 ('hydrochain-data-001','baseflow/flow_components.csv','quickflow_m3_s')])
def test_material_scientific_errors_even_after_rehash(tmp_path,task,path,column):
    x,w,audit=copied(tmp_path,task);p=w/path
    if not p.exists():p=next(p for p in w.rglob('*.csv') if column in pd.read_csv(p,nrows=0).columns)
    f=pd.read_csv(p);f.loc[len(f)//2,column]=float(f.loc[len(f)//2,column])*2+100;f.to_csv(p,index=False)
    portable_tree(w);r=grade(x,w,audit)
    assert not r['task_success'];assert any(e['code']=='material_scientific_numeric_error' for e in r['critical_errors'])

def test_wrong_units_after_rehash(tmp_path):
    x,w,audit=copied(tmp_path,'hydrochain-model-001');p=w/'rain/result.json';d=json.loads(p.read_text(encoding='utf-8'));d['parameters']['unit']='cm/step';p.write_text(json.dumps(d),encoding='utf-8');portable_tree(w)
    r=grade(x,w,audit);assert not r['task_success'];assert any(e['code']=='wrong_units_or_scientific_organization' for e in r['critical_errors'])

def test_unauthorized_missing_rain_zero_fill(tmp_path):
    x,w,audit=copied(tmp_path,'hydrochain-data-002');p=w/'original.csv';f=pd.read_csv(p);f.avg_rain=f.avg_rain.fillna(0);f.to_csv(p,index=False);portable_tree(w)
    r=grade(x,w,audit);assert not r['task_success'];assert any(e['code']=='unauthorized_missing_rain_fill' for e in r['critical_errors'])

def test_scoring_overlap_and_locked_parameters(tmp_path):
    x,w,audit=copied(tmp_path,'hydrochain-model-011');p=w/'calibration/validation_series.csv';f=pd.read_csv(p);cal=pd.read_csv(w/'calibration/calibration_series.csv');f.loc[f.index[f.scored][0],'time']=cal.loc[cal.scored,'time'].iloc[0];f.to_csv(p,index=False);portable_tree(w)
    r=grade(x,w,audit);assert not r['task_success'];assert any(e['code']=='physical_state_or_split_error' for e in r['critical_errors'])

def test_wrong_figure_size_even_with_fresh_hash(tmp_path):
    x,w,audit=copied(tmp_path,'hydrochain-analysis-002');p=next((w/'atlas').glob('*.png'))
    with Image.open(p) as im:im.resize((100,100)).save(p)
    portable_tree(w);r=grade(x,w,audit);assert not r['task_success'];assert not next(g for g in r['scientific_gates'] if g['id']=='figure_contract')['passed']

@pytest.mark.parametrize('task',['hydrochain-data-002','hydrochain-model-010'])
def test_early_block_no_longer_satisfies_normal_delivery(tmp_path,task):
    x=item(task);w=tmp_path/'workspace';runner.stage_workspace(x['task'],x['task_dir'],w);gold=x['task_dir']/'expected/golden_workspace'
    proof='readiness.json' if task.endswith('data-002') else 'routing_audit.json'
    shutil.copyfile(gold/proof,w/proof);decision=json.loads((gold/'decision.json').read_text(encoding='utf-8'));decision['evidence']=[{'path':proof,'sha256':sha(w/proof)}];(w/'decision.json').write_text(json.dumps(decision),encoding='utf-8')
    audit=json.loads((x['task_dir']/'expected/audit_fixture.json').read_text(encoding='utf-8'))['events'];r=grade(x,w,audit)
    assert not r['task_success']


def test_omitting_channel_routing_is_critical(tmp_path):
    x,w,audit=copied(tmp_path,'hydrochain-model-001')
    model=pd.read_csv(w/'model/lumped_xaj_runoff.csv');p=w/'routed/routed_flow.csv';routed=pd.read_csv(p)
    # A plausible but scientifically wrong delivery: label the upstream output
    # as the downstream result without applying the supplied channel routing.
    routed['routed_local']=model.Qt.to_numpy();routed['Q_total']=model.Qt.to_numpy();routed.to_csv(p,index=False)
    portable_tree(w);result=grade(x,w,audit)
    assert not result['task_success'] and result['critical_errors']

def test_reservoir_release_counted_twice_is_critical(tmp_path):
    x,w,audit=copied(tmp_path,'hydrochain-model-004');p=w/'routed/routed_flow.csv';f=pd.read_csv(p)
    f['Q_total']=f.routed_local+2*f.routed_reservoir;f.to_csv(p,index=False)
    portable_tree(w);result=grade(x,w,audit)
    assert not result['task_success'] and result['critical_errors']

def test_event_state_carryover_is_critical(tmp_path):
    x,w,audit=copied(tmp_path,'hydrochain-model-002');p=w/'model/lumped_xaj_runoff.csv';f=pd.read_csv(p)
    previous=f.event_id.iloc[0];following=next(e for e in f.event_id.unique() if e!=previous)
    previous_final=f.loc[f.event_id==previous].iloc[-1]
    index=f.index[f.event_id==following][0]
    # Carry the previous flood's ending stores into the next independent flood.
    for field in ['WU','WL','WD','W','S1']:f.loc[index,field]=previous_final[field]
    f.to_csv(p,index=False);portable_tree(w);result=grade(x,w,audit)
    assert not result['task_success'] and result['critical_errors']


def test_malformed_delivery_is_unassessable_not_proven_scientific_error(tmp_path):
    x,w,audit=copied(tmp_path,'hydrochain-model-001')
    (w/'routed/routed_flow.csv').write_text('unrecognized_column\nnot_a_number\n',encoding='utf-8')
    portable_tree(w)  # isolate formatting from an independently false hash claim
    result=grade(x,w,audit)
    assert not result['task_success']
    assert result['assessability']=='insufficient_evidence'
    assert not result['critical_errors']
