from __future__ import annotations
import json
import hashlib
from pathlib import Path
import shutil
import sys

import pytest
from PIL import Image

from harness import grader, runner, schemas

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from atomic_tasks import GROUPS

def tasks():
    return [item for item in runner.discover_tasks(ROOT/'tests') if item['task']['id'].rsplit('-',1)[0] in GROUPS]

def staged(item, workspace):
    shutil.copytree(item['task_dir']/'data',workspace,dirs_exist_ok=True)
    shutil.copytree(item['task_dir']/'expected/golden_workspace',workspace,dirs_exist_ok=True)

def rehash_outputs(workspace):
    for result in workspace.rglob('result.json'):
        doc=json.loads(result.read_text(encoding='utf-8'))
        for reference in doc.get('artifacts',{}).values():
            if isinstance(reference,dict) and isinstance(reference.get('path'),str):
                path=result.parent/reference['path']
                if path.is_file(): reference['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        result.write_text(json.dumps(doc),encoding='utf-8')

def test_completion_inventory():
    found=runner.discover_tasks(ROOT/'tests')
    assert len(found)==183
    assert len(tasks())==43
    skills={item['task']['primary_skill'] for item in found}
    catalog=json.loads((ROOT/'docs/atomic-skill-catalog.json').read_text(encoding='utf-8'))
    assert skills=={s['skill'] for s in catalog['atomic_skills']}
    assert len(skills)==41
    for prefix,(_,_,count) in GROUPS.items():
        assert {i['task']['id'] for i in tasks() if i['task']['id'].startswith(prefix+'-')}=={f'{prefix}-{n:03}' for n in range(1,count+1)}
    assert not (ROOT/'examples/tasks/hydroanalysis-legacy-template/task.json').exists()
    assert 'hydroanalysis-001' not in {i['task']['id'] for i in found}
    assert runner.validate_tests(ROOT/'tests')==[]

def test_all_183_repository_golden_workspaces(tmp_path):
    for item in runner.discover_tasks(ROOT/'tests'):
        workspace=tmp_path/item['task']['id'];staged(item,workspace)
        result=grader.grade_task(item['task'],workspace,item['task_dir'])
        assert result['score']==pytest.approx(1),result

@pytest.mark.parametrize('item',tasks(),ids=lambda item:item['task']['id'])
def test_new_golden_full_score(item,tmp_path):
    staged(item,tmp_path)
    result=grader.grade_task(item['task'],tmp_path,item['task_dir'])
    assert result['score']==pytest.approx(1),result

def figure_item():
    return next(i for i in tasks() if i['task']['id']=='hydrovisual-flood-atlas-001')

@pytest.mark.parametrize('failure',['blank','size','svg','metadata','layer','hash'])
def test_figure_forgeries_lose_score(tmp_path,failure):
    item=figure_item();staged(item,tmp_path)
    reference=json.loads((item['task_dir']/'expected/figure-contract.json').read_text(encoding='utf-8'))
    fig=reference['figures'][0];png=tmp_path/fig['png'];svg=tmp_path/fig['svg'];meta=tmp_path/fig['metadata']
    if failure=='blank': Image.new('RGB',fig['size'],'white').save(png)
    elif failure=='size':
        with Image.open(png) as im: im.resize((100,100)).save(png)
    elif failure=='svg': svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>',encoding='utf-8')
    elif failure=='hash':
        with png.open('ab') as handle: handle.write(b'changed')
    else:
        doc=json.loads(meta.read_text(encoding='utf-8'))
        if failure=='metadata': doc['language']='wrong'
        else: doc['layers']=[]
        meta.write_text(json.dumps(doc),encoding='utf-8')
    if failure!='hash': rehash_outputs(tmp_path)
    assert grader.grade_task(item['task'],tmp_path,item['task_dir'])['score']<1

@pytest.mark.parametrize('failure',['value','split','claim','markdown','numeric_binding'])
def test_report_changes_lose_score(tmp_path,failure):
    item=next(i for i in tasks() if i['task']['id']=='hydroreport-study-001');staged(item,tmp_path)
    path=tmp_path/'report/report.json';doc=json.loads(path.read_text(encoding='utf-8'))
    if failure=='value': doc['evidence'][0]['value']=99999
    elif failure=='split': doc['analysis']['details']['worst_events'][0]['split']='calibration'
    elif failure=='claim':
        p=tmp_path/'conclusions.json';value=json.loads(p.read_text(encoding='utf-8'));value['causal_status']='established';p.write_text(json.dumps(value),encoding='utf-8')
    elif failure=='numeric_binding':
        p=next(s for s in doc['sections'] if s['id']=='overview')['paragraphs'][0]
        p['numeric_bindings']=[dict(evidence_id=p['evidence_ids'][0],text='9999.000')]
    else: (tmp_path/'report/report.md').write_text('Unsupported replacement',encoding='utf-8')
    if failure in ('value','split','numeric_binding'): path.write_text(json.dumps(doc),encoding='utf-8')
    rehash_outputs(tmp_path)
    assert grader.grade_task(item['task'],tmp_path,item['task_dir'])['score']<1

@pytest.mark.parametrize('failure',['missing','duplicate','stale','unsupported','binding'])
def test_semantic_review_changes_lose_score(tmp_path,failure):
    item=next(i for i in tasks() if i['task']['id']=='hydroreport-review-001');staged(item,tmp_path)
    path=tmp_path/'semantic.json';doc=json.loads(path.read_text(encoding='utf-8'))
    if failure=='missing': doc['paragraphs'].pop()
    elif failure=='duplicate': doc['paragraphs'].append(doc['paragraphs'][0])
    elif failure=='stale': doc['package_fingerprint']='0'*64
    elif failure=='unsupported': doc['paragraphs'][0]['verdict']='unsupported'
    else: doc['paragraphs'][0]['evidence_ids']=[]
    path.write_text(json.dumps(doc),encoding='utf-8')
    assert grader.grade_task(item['task'],tmp_path,item['task_dir'])['score']<1

def test_new_graders_path_safety(tmp_path):
    for name in ('figure_contract_check','report_contract_check'):
        result=grader.grade_criterion({'type':name,'target':'../outside','reference':'../outside'},tmp_path,tmp_path)
        assert result['score']==0

def test_bma_quantiles_checked_against_independent_cdf(tmp_path):
    import pandas as pd
    item=next(i for i in tasks() if i['task']['id']=='hydroanalysis-bma-001');staged(item,tmp_path)
    path=tmp_path/'forecast/ensemble_discharge.csv';frame=pd.read_csv(path)
    # Preserve nonnegative ordered quantiles while making the CDF wrong.
    frame['p95_m3_s']+=20;frame.to_csv(path,index=False);rehash_outputs(tmp_path)
    criterion=next(c for c in item['task']['grading'] if c['name']=='evidence_and_scientific_contract')
    assert grader.grade_criterion(criterion,tmp_path,item['task_dir'])['score']<1

def test_error_reason_and_empty_forbidden_file(tmp_path):
    item=next(i for i in tasks() if i['task']['id']=='hydroanalysis-bma-008');staged(item,tmp_path)
    path=tmp_path/'fit/result.json';doc=json.loads(path.read_text(encoding='utf-8'));doc['message']='Unrelated failure';path.write_text(json.dumps(doc),encoding='utf-8')
    (tmp_path/'fit/bma_model.json').write_bytes(b'')
    assert grader.grade_task(item['task'],tmp_path,item['task_dir'])['score']<1
