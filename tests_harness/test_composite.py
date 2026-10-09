from __future__ import annotations
import copy
import json
from pathlib import Path
import shutil
import sys
import pytest
from harness import grader,runner,schemas,reporter
from harness.cli_events import EventCounter,command
from harness.confirmation import ConfirmationBroker
from harness.composite_runtime import monitor,load_lock
from harness.experiment import schedule,summarize

ROOT=Path(__file__).resolve().parents[1]

def item(task_id):return runner.discover_tasks(ROOT/'tests',test_id=task_id,suite='composite')[0]
def copied(tmp_path,task_id):
    x=item(task_id);shutil.copytree(x['task_dir']/'expected/golden_workspace',tmp_path/'workspace')
    audit=json.loads((x['task_dir']/'expected/audit_fixture.json').read_text(encoding='utf-8'))['events']
    return x,tmp_path/'workspace',audit
def grade(x,w,audit):return grader.grade_task(x['task'],w,x['task_dir'],audit_events=audit)

def test_suite_counts_and_public_hidden_contract():
    atomic=runner.discover_tasks(ROOT/'tests');composite=runner.discover_tasks(ROOT/'tests',suite='composite')
    assert len(atomic)==183 and len(composite)==24 and len(runner.discover_tasks(ROOT/'tests',suite='all'))==207
    assert len({x['task']['primary_skill'] for x in atomic})==41
    assert all(x['task']['outcome_goal']=='deliverable' and x['task']['interaction_mode']=='none' for x in composite)
    assert not runner.validate_tests(ROOT/'tests',suite='all')
    for x in composite:
        public=schemas.public_task(x['task'])
        assert not {'grading','core_capabilities','evaluation_reference','primary_skill','outcome_goal'}&set(public)
        assert len(set(x['task']['core_capabilities']))>=3
        assert all('/' not in cap for cap in x['task']['core_capabilities'])
    for family,count in [('data',8),('model',12),('analysis',4)]:
        assert sorted(x['task']['id'] for x in composite if x['task']['id'].startswith('hydrochain-'+family))==[f'hydrochain-{family}-{n:03d}' for n in range(1,count+1)]

@pytest.mark.parametrize('x',runner.discover_tasks(ROOT/'tests',suite='composite'),ids=lambda x:x['task']['id'])
def test_composite_golden_all_gates(x):
    audit=json.loads((x['task_dir']/'expected/audit_fixture.json').read_text(encoding='utf-8'))['events']
    result=grade(x,x['task_dir']/'expected/golden_workspace',audit)
    assert result['score']==pytest.approx(1)
    assert result['task_success'],[(g['id'],g.get('criteria')) for g in result['scientific_gates'] if not g['passed']]
    assert not result['critical_errors']

@pytest.mark.parametrize('task_id,path',[
 ('hydrochain-model-001','routed/routed_flow.csv'),
 ('hydrochain-model-002','model/lumped_xaj_runoff.csv'),
 ('hydrochain-model-007','aggregate/subbasin_forcing.csv'),
 ('hydrochain-data-001','baseflow/flow_components.csv')])
def test_skipped_intermediate_is_failure_not_proven_error(tmp_path,task_id,path):
    x,w,audit=copied(tmp_path,task_id)
    # remove a real intermediate instead of assuming a program call proves completion
    p=w/path
    if not p.exists():p=next(p for p in w.rglob('*.csv') if p.relative_to(w).as_posix() not in x['task']['data_files'])
    p.unlink();r=grade(x,w,audit);assert not r['task_success']

@pytest.mark.parametrize('mode',['no_audit','late','unapplied','duplicate'])
def test_upfront_settings_need_application_but_no_audit(tmp_path,mode):
    x,w,audit=copied(tmp_path,'hydrochain-model-001')
    if mode=='no_audit':audit=[]
    if mode=='late':
        for e in audit:
            if e['kind']=='confirmation':e['time_ns']=999
    if mode=='unapplied':
        p=w/'rain/result.json';doc=json.loads(p.read_text());doc['parameters']['timezone']='UTC';p.write_text(json.dumps(doc))
    if mode=='duplicate':audit=audit+[copy.deepcopy(e) for e in audit if e['kind']=='confirmation']
    r=grade(x,w,audit)
    assert r['task_success']==(mode!='unapplied')
    assert 'confirmation_results' not in r
    assert len(r['provided_setting_results'])==1

@pytest.mark.parametrize('task_id',['hydrochain-data-002','hydrochain-data-008','hydrochain-model-010','hydrochain-analysis-004'])
def test_former_blocked_cases_require_normal_delivery(tmp_path,task_id):
    x,w,audit=copied(tmp_path,task_id);spec=json.loads((x['task_dir']/x['task']['evaluation_reference']).read_text(encoding='utf-8'))
    assert not spec['forbidden_outputs'] and grade(x,w,[])['task_success']
    p=w/'decision.json';doc=json.loads(p.read_text());doc['status']='blocked';p.write_text(json.dumps(doc))
    assert not grade(x,w,[])['task_success']

def test_unsupported_conclusion_and_wrong_evidence(tmp_path):
    x,w,audit=copied(tmp_path,'hydrochain-analysis-001')
    p=w/'conclusions.json';doc=json.loads(p.read_text());doc['causality']='proved';p.write_text(json.dumps(doc))
    assert not grade(x,w,audit)['task_success']
    p=w/'decision.json';doc=json.loads(p.read_text());doc['evidence'][0]['sha256']='0'*64;p.write_text(json.dumps(doc))
    assert not grade(x,w,audit)['task_success']

def test_fake_completed_log_cannot_pass(tmp_path):
    x=item('hydrochain-model-001');runner.stage_workspace(x['task'],x['task_dir'],tmp_path/'w')
    (tmp_path/'w/completed.log').write_text('all steps succeeded')
    r=grade(x,tmp_path/'w',[]);assert not r['task_success'];assert r['assessability']=='insufficient_evidence'
    assert not r['critical_errors']

def test_broker_compound_alias_no_missing_hints(tmp_path):
    spec={'confirmations':[{'key':'timezone','aliases':['时区'],'subject':'时间','answer':'Asia/Shanghai'},{'key':'unit','subject':'流量','answer':'m3/s'}]}
    b=ConfirmationBroker(spec,tmp_path/'audit.jsonl')
    answer=b.answer({'subject':'时间','fields':['时区','unknown'],'question':'资料的时间采用什么时区？'})
    assert answer['answers'][0]['answer']=='Asia/Shanghai';assert 'answer' not in answer['answers'][1]
    assert 'm3/s' not in json.dumps(answer)
    assert sum(e['kind']=='confirmation' for e in b.events)==1
    assert any(e['kind']=='confirmation_request' for e in b.events) and any(e['kind']=='confirmation_response' for e in b.events)
    assert 'error' in b.answer({'subject':'时间','fields':[],'question':'请告诉我全部'})

EVENTS={
 'codex':[{'type':'thread.started'},{'type':'item.started','item':{'id':'t1','type':'command_execution'}},{'type':'item.completed','item':{'id':'t1','type':'command_execution'}},{'type':'item.completed','item':{'id':'a1','type':'agent_message'}}],
 'opencode':[{'type':'step_start','part':{'id':'a1'}},{'type':'tool_use','part':{'callID':'t1'}}],
 'qwen':[{'type':'assistant','message':{'id':'a1','content':[{'type':'tool_use','id':'t1'}]}},{'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':'t1'}]}}]}
@pytest.mark.parametrize('cli',list(EVENTS))
def test_cli_events_deduplicate_and_budget(cli):
    c=EventCounter(cli,1,1)
    for event in EVENTS[cli]*2:c.feed(json.dumps(event))
    assert c.rounds==c.tools==1 and c.exhausted
    assert 'fixed-model' in command(cli,'fixed-model','high','same prompt')

@pytest.mark.parametrize('cli',list(EVENTS))
def test_fake_cli_budget_termination(tmp_path,cli):
    script=tmp_path/'fake.py';script.write_text('import time\nprint('+repr(json.dumps(EVENTS[cli][1 if cli=='codex' else 0]))+',flush=True)\ntime.sleep(10)\n')
    r=monitor([sys.executable,str(script)],cli,{'agent_rounds':1,'tool_calls':1},2,tmp_path/'out',tmp_path/'err',lambda x:None,lambda:None)
    assert r['termination_reason']=='action_budget'
    assert r['duration_seconds']<5

def test_fake_cli_timeout_and_unrecognized_stream(tmp_path):
    script=tmp_path/'fake.py';script.write_text('import time\nprint("plain output",flush=True)\ntime.sleep(5)\n')
    r=monitor([sys.executable,str(script)],'qwen',{'agent_rounds':60,'tool_calls':120},.2,tmp_path/'out',tmp_path/'err',lambda x:None,lambda:None)
    assert r['timed_out'] and not r['stream_assessable']
    with pytest.raises(ValueError):load_lock(ROOT/'runtime/experiment.template.json')

def test_schedule_432_and_counting_denominators():
    ids=[x['task']['id'] for x in runner.discover_tasks(ROOT/'tests',suite='composite')]
    pairs=schedule(ids);assert len(pairs)==216 and pairs==schedule(ids)
    assert all(set(p['conditions'])=={'no-skills','with-skills'} for p in pairs)
    rows=[]
    for condition in ['no-skills','with-skills']:
        for n in [1,2]:
            rows.append({'test_id':str(n),'cli':'qwen','condition':condition,'repetition':1,'task_kind':'composite','task_success':condition=='with-skills','critical_errors':[] if condition=='with-skills' else [{'code':'a'},{'code':'b'}],'confirmation_results':[{'passed':condition=='with-skills'},{'passed':False}],'assessability':'assessed','domain':'results-analysis','primary_skill':'workflow','difficulty':'advanced','outcome_goal':'deliverable'})
    report=summarize(rows);a=report['groups']['qwen/no-skills'];b=report['groups']['qwen/with-skills']
    assert a['critical_error_task_runs']==2 and a['critical_scientific_error_rate']==1
    assert b['successful_task_runs']==2 and b['necessary_information_items']==4 and b['necessary_information_confirmation_rate']==.5


def test_paired_confirmation_uplift_weights_information_items():
    rows=[]
    for task,count in [('one',1),('two',2)]:
        for condition in ['no-skills','with-skills']:
            passed=condition=='with-skills' and task=='one'
            rows.append({'test_id':task,'cli':'qwen','condition':condition,'repetition':1,'task_kind':'composite','task_success':passed,'critical_errors':[],'confirmation_results':[{'passed':passed}]*count,'assessability':'assessed','domain':'results-analysis','primary_skill':'workflow','difficulty':'advanced','outcome_goal':'deliverable'})
    report=summarize(rows)
    assert report['paired_differences']['qwen']['mean'][2]==pytest.approx(1/3)

def test_composite_compare_rejects_changed_runtime_controls():
    left={'suite':'composite','runtime_controls':{'image_digest':'sha256:a'}}
    with pytest.raises(ValueError):reporter._assert_comparable(left,{'suite':'composite','runtime_controls':{'image_digest':'sha256:b'}})


def test_startup_failures_have_no_success_rate_denominator():
    row={'test_id':'failed-start','task_kind':'composite','eligible':False,'cli':'qwen','condition':'no-skills','repetition':1,'domain':'results-analysis','primary_skill':'workflow','difficulty':'advanced','outcome_goal':'deliverable'}
    report=summarize([row]);group=report['groups']['qwen/no-skills']
    assert report['startup_failures']==1
    assert group['task_runs']==0 and group['task_success_rate'] is None
    assert group['critical_scientific_error_rate'] is None
    assert group['repeat_success_rate_range']==[None,None]
