"""Unattended task completeness, autonomy, isolation and version separation."""
from contextlib import contextmanager
import copy
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import urllib.error
import urllib.request

import pytest

from harness import runner,schemas,reporter
from harness.confirmation import AuditTrail
from harness.experiment import summarize
from harness.isolated_runtime import run_isolated,candidate_argv
from runtime.provider_relay import Handler
from test_composite import copied,grade


ROOT=Path(__file__).resolve().parents[1]


def test_all_upfront_settings_are_public_and_no_hidden_confirmation():
    for item in runner.discover_tasks(suite='composite'):
        task=item['task'];data=item['task_dir']/'data'
        spec=json.loads((item['task_dir']/task['evaluation_reference']).read_text(encoding='utf-8'))
        assert spec['task_version']==task['task_version']=='composite-unattended-v2'
        assert spec['interaction_mode']==task['interaction_mode']=='none'
        assert not spec.get('confirmations')
        assert not schemas.validate_task(task,item['task_dir'])
        public=schemas.public_task(task)
        assert public['interaction_mode']=='none' and public['task_version']==task['task_version']
        assert {'scenario.json','INPUT_GUIDE.md','OUTPUT_INTERFACES.md','output_interfaces.json','input_inventory.json'}<=set(task['data_files'])
        assert '缺失的必要信息请向用户确认' not in task['prompt']
        scenario=json.loads((data/'scenario.json').read_text(encoding='utf-8'))
        assert scenario['time']['output_timezone_mode']=='offset_aware'
        assert scenario['forcing_selection']['rainfall_variable']=='P'
        assert scenario['task_science']['active_forward_model']
        assert scenario['model_initialization']['gr4j']['production_store']==0
        assert scenario['model_initialization']['dhf']['warmup_initial_states']['ya0']==0.5
        if task['id']=='hydrochain-model-010':
            audit=scenario['routing_stability_audit']
            assert audit['K_source']=='semi_parameters.xaj.KE'
            assert audit['X_source']=='semi_parameters.xaj.XE'
            assert audit['step_source']=='semi_parameters.time.step_seconds'
        if task['id']=='hydrochain-model-004':
            assert scenario['forcing_selection']['source_ids']==['basin']
            assert scenario['forcing_selection']['rainfall_columns']=='avg_rain'
            assert scenario['forcing_selection']['evaporation_output_variable']=='E0'


def test_equivalent_input_names_and_metadata_are_not_factory_requirements(tmp_path):
    import sys
    sys.path.insert(0,str(ROOT/'scripts'))
    from composite_common import portable_tree
    item,w,_=copied(tmp_path,'hydrochain-model-001')
    assert 'rain_source.csv' not in item['task']['required_outputs']
    (w/'rain_source.csv').rename(w/'custom_rain_input.csv')
    (w/'rain_config.json').rename(w/'custom_rain_config.json')
    p=w/'rain/result.json';doc=json.loads(p.read_text(encoding='utf-8'))
    doc['inputs']['source']['path']='../custom_rain_input.csv'
    doc['inputs']['config']['path']='../custom_rain_config.json'
    doc['message']='Independent equivalent implementation'
    doc['parameters']['columns']={'time':'timestamp','source_id':'station','value':'depth'}
    p.write_text(json.dumps(doc),encoding='utf-8');portable_tree(w)
    assert grade(item,w,[])['task_success']


def test_equivalent_implementation_needs_no_factory_config_files(tmp_path):
    import sys
    sys.path.insert(0,str(ROOT/'scripts'))
    from composite_common import portable_tree
    item,w,_=copied(tmp_path,'hydrochain-model-001')
    interfaces=json.loads((w/'output_interfaces.json').read_text(encoding='utf-8'))
    removed=[]
    for rel,interface in interfaces['outputs'].items():
        roles=interface.get('optional_input_roles',[])
        if not roles:continue
        p=w/rel;doc=json.loads(p.read_text(encoding='utf-8'))
        for role in roles:
            reference=doc['inputs'].pop(role)
            temporary=(p.parent/reference['path']).resolve()
            temporary.relative_to(w.resolve())
            if temporary.is_file() and temporary.relative_to(w.resolve()).as_posix() not in item['task']['data_files']:
                temporary.unlink();removed.append(temporary.name)
        p.write_text(json.dumps(doc),encoding='utf-8')
    assert removed
    portable_tree(w)
    assert grade(item,w,[])['task_success']


@pytest.mark.parametrize('task,path,field,value',[
    ('hydrochain-data-003','prepared/result.json','vertical_unit','ft'),
    ('hydrochain-data-008','topology-qc/result.json','expected_outlets',2),
])
def test_wrong_supplied_setting_fails_even_without_questions(tmp_path,task,path,field,value):
    item,w,_=copied(tmp_path,task);p=w/path;doc=json.loads(p.read_text(encoding='utf-8'))
    doc['parameters'][field]=value;p.write_text(json.dumps(doc),encoding='utf-8')
    result=grade(item,w,[])
    assert not result['task_success']
    assert any(not s['passed'] for s in result['provided_setting_results'])


def test_wrong_evaporation_mapping_fails(tmp_path):
    item,w,_=copied(tmp_path,'hydrochain-model-005');p=w/'evaporation_mapping.json'
    doc=json.loads(p.read_text());doc['mapping']['factor']=0.5;p.write_text(json.dumps(doc))
    assert not grade(item,w,[])['task_success']


def test_stability_audit_must_use_declared_semi_model_scope(tmp_path):
    item,w,_=copied(tmp_path,'hydrochain-model-010')
    scenario=json.loads((w/'scenario.json').read_text(encoding='utf-8'))
    k,x=scenario['route_k_hours'],scenario['route_x']
    dt=scenario['semi_parameters']['time']['step_seconds']/3600
    den=k*(1-x)+dt/2
    audit=w/'routing_audit.json'
    doc=json.loads(audit.read_text(encoding='utf-8'))
    doc['coefficients']=[(dt/2-k*x)/den,(dt/2+k*x)/den,(k*(1-x)-dt/2)/den]
    audit.write_text(json.dumps(doc),encoding='utf-8')
    result=grade(item,w,[])
    assert not result['task_success']
    assert any(g['id']=='routing_stability' and not g['passed'] for g in result['scientific_gates'])


def test_equivalent_timezone_metadata_preserves_scientific_instants(tmp_path):
    import pandas as pd
    import sys
    sys.path.insert(0,str(ROOT/'scripts'))
    from composite_common import portable_tree
    item,w,_=copied(tmp_path,'hydrochain-model-007');p=w/'model/result.json'
    doc=json.loads(p.read_text(encoding='utf-8'))
    for key in ['start','end']:
        doc['parameters']['simulation'][key]=pd.Timestamp(doc['parameters']['simulation'][key]).tz_convert('UTC').isoformat()
    p.write_text(json.dumps(doc),encoding='utf-8');portable_tree(w)
    assert grade(item,w,[])['task_success']


def test_bma_training_metadata_accepts_equivalent_timezone_offsets(tmp_path):
    import pandas as pd
    import sys
    sys.path.insert(0,str(ROOT/'scripts'))
    from composite_common import portable_tree
    item,w,_=copied(tmp_path,'hydrochain-analysis-003');p=w/'fit/bma_model.json'
    before=json.loads((w/'decision.json').read_text(encoding='utf-8'))
    doc=json.loads(p.read_text(encoding='utf-8'))
    for key in ['training_start','training_end']:
        doc[key]=pd.Timestamp(doc[key]).tz_convert('Asia/Shanghai').isoformat()
    p.write_text(json.dumps(doc),encoding='utf-8');portable_tree(w)
    after=json.loads((w/'decision.json').read_text(encoding='utf-8'))
    report=w/'report.md';text=report.read_text(encoding='utf-8')
    for old,new in zip(before['evidence'],after['evidence']):text=text.replace(old['sha256'],new['sha256'])
    report.write_text(text,encoding='utf-8')
    assert grade(item,w,[])['task_success']


def test_review_cannot_approve_scoring_overlap(tmp_path):
    import pandas as pd
    from harness.grader import grade_criterion
    item,w,_=copied(tmp_path,'hydrochain-analysis-004')
    cal=pd.read_csv(w/'calibration_scored.csv');val=pd.read_csv(w/'validation_scored.csv')
    val.loc[0,'time']=cal.time.iloc[0];val.to_csv(w/'validation_scored.csv',index=False)
    criterion={'type':'scientific_invariant','check':'split_audit_recompute','target':'split_audit.json','targets':['calibration_scored.csv','validation_scored.csv']}
    assert not grade_criterion(criterion,w,item['task_dir'])['score']
    assert not grade(item,w,[])['task_success']


def test_relay_rejects_confirmation_post_without_upstream(monkeypatch):
    monkeypatch.delenv('CONFIRMATION_UPSTREAM',raising=False)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/confirm',data=b'{}')
        with pytest.raises(urllib.error.HTTPError) as error:urllib.request.urlopen(request,timeout=3)
        assert error.value.code==403
    finally:server.shutdown();server.server_close();thread.join(timeout=3)


def test_runtime_starts_no_answer_service_or_credentials(tmp_path,monkeypatch):
    import harness.isolated_runtime as module
    public=tmp_path/'runtime/public';public.mkdir(parents=True)
    skills=tmp_path/'runtime/skills';skills.mkdir()
    workspace=tmp_path/'workspace';workspace.mkdir()
    output=tmp_path/'output';output.mkdir()
    task={'task_version':'composite-unattended-v2','interaction_mode':'none',
        'resource_budget':{'agent_rounds':60,'tool_calls':120},'timeout_seconds':900}
    lock={'public_programs_sha256':runner._sha256_tree(public),'skills_sha256':runner._sha256_tree(skills),
        'clis':{'codex':{'model':'fixture','effort':'medium','version':'fixture'}},
        'image_digest':'sha256:fixture','common_config_dir':str(tmp_path/'config')}
    @contextmanager
    def relay(lock,cli,audit,*args,**kwargs):
        assert isinstance(audit,AuditTrail) and audit.token is None and not hasattr(audit,'start')
        yield 'internal','candidate',SimpleNamespace(events=[{'method':'POST','path':'/backend-api/codex/responses','status':200}],decision_requests=1,budget_denied=False)
    def monitor(argv,*args,**kwargs):
        assert not any('HSQB_CONFIRMATION' in v for v in argv)
        return {'return_code':0,'timed_out':False,'termination_reason':None}
    monkeypatch.setattr(module,'relay_session',relay);monkeypatch.setattr(module,'monitor',monitor)
    execution,events=run_isolated(task,workspace,tmp_path,output,lock,'codex','no-skills',tmp_path)
    assert execution['eligible'] and execution['confirmation_service_started'] is False
    assert not events


def test_unattended_reports_do_not_mix_confirmation_metrics():
    rows=[]
    for condition in ['no-skills','with-skills']:
        rows.append({'test_id':'one','cli':'codex','condition':condition,'repetition':1,
            'task_kind':'composite','task_version':'composite-unattended-v2','interaction_mode':'none',
            'task_success':True,'critical_errors':[],'provided_setting_results':[{'key':'timezone','passed':True}],
            'assessability':'assessed','domain':'model-computation','primary_skill':'workflow','difficulty':'advanced','outcome_goal':'deliverable'})
    report=summarize(rows)
    summary=report['groups']['codex/no-skills']
    assert summary['provided_setting_usage_rate']==1
    assert 'necessary_information_confirmation_rate' not in summary
    assert report['paired_differences']['codex']['metrics'][-1]=='provided_setting_usage_rate'
    reporter.format_summary(summary)
    old=copy.deepcopy(rows[0]);old.pop('interaction_mode');old.pop('provided_setting_results');old['confirmation_results']=[]
    with pytest.raises(ValueError,match='legacy'):summarize(rows+[old])


def test_old_result_cannot_be_regraded_as_v2(tmp_path):
    output=tmp_path/'tasks/hydrochain-model-001';output.mkdir(parents=True)
    (tmp_path/'run_metadata.json').write_text(json.dumps({'tests_root':str(ROOT/'tests'),'suite':'composite'}))
    (output/'result.json').write_text(json.dumps({'test_id':'hydrochain-model-001','score':1}))
    with pytest.raises(ValueError,match='different task version'):runner.regrade_run(tmp_path)
