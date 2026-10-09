import datetime as dt
import json
import threading
import time
from pathlib import Path

import pytest
from harness.experiment import schedule
from harness.overnight import parse_deadline, run_schedule, write_reports


def fake_row(pair,condition,attempt,out):
    return {'test_id':pair['task_id'],'eligible':True,'attempted':True,'score':1,
        'task_kind':'composite','task_success':True,'critical_errors':[],
        'confirmation_results':[{'passed':True}], 'assessability':'assessed',
        'domain':'data-preprocessing','difficulty':'advanced','primary_skill':'workflow','outcome_goal':'deliverable'}


def test_schedule_144_and_selected_cli():
    ids=[f't{i}' for i in range(24)]
    assert len(schedule(ids,repetitions=1))*2==144
    assert len(schedule(ids,repetitions=1,clis=['qwen']))*2==48


def test_parallel_lanes_same_cli_serial_resume(tmp_path):
    pairs=schedule(['a','b'],repetitions=1);active=set();lock=threading.Lock();calls=[]
    def execute(pair,condition,attempt,out):
        with lock:
            assert pair['cli'] not in active
            active.add(pair['cli']);calls.append((pair['pair_id'],condition))
            assert len(active)<=3
        time.sleep(.01)
        with lock:active.remove(pair['cli'])
        return fake_row(pair,condition,attempt,out)
    run_schedule(tmp_path,pairs,execute,lock_hash='same')
    assert len(calls)==12
    run_schedule(tmp_path,pairs,execute,resume=True,lock_hash='same')
    assert len(calls)==12
    report=json.loads((tmp_path/'scientific_report.json').read_text())
    assert report['completed_pairs']==6 and report['planned_runs']==12
    assert all('repeat_success_rate_range' not in g for g in report['groups'].values())
    with pytest.raises(ValueError,match='changed'):
        run_schedule(tmp_path,pairs,execute,resume=True,lock_hash='changed')


def test_scientific_failure_never_retried(tmp_path):
    pairs=schedule(['a'],repetitions=1,clis=['qwen']);calls=[]
    def execute(*args):
        calls.append(1);row=fake_row(*args);row['task_success']=False;return row
    run_schedule(tmp_path,pairs,execute)
    assert len(calls)==2


def test_infrastructure_retry_whole_pair_and_pause(tmp_path):
    pairs=schedule(['a','b'],repetitions=1,clis=['qwen']);calls=[]
    def execute(pair,condition,attempt,out):
        calls.append((attempt,condition));raise RuntimeError('sk-private-do-not-log')
    run_schedule(tmp_path,pairs,execute)
    assert len(calls)==4
    report=json.loads((tmp_path/'scientific_report.json').read_text())
    assert report['startup_failures']==2 and report['recorded_attempt_runs']==4
    assert report['completed_pairs']==0
    assert report['groups']['qwen/no-skills']['task_runs']==0
    assert 'sk-private-do-not-log' not in ''.join(p.read_text(encoding='utf-8') for p in tmp_path.rglob('*.json'))


def test_cutoff_defers_without_failure(tmp_path):
    deadline=parse_deadline('2026-10-05T10:00:00+08:00')
    pairs=schedule(['a'],repetitions=1,clis=['codex'])
    state=run_schedule(tmp_path,pairs,lambda *a:pytest.fail('must not start'),
        deadline=deadline,now=lambda:deadline-dt.timedelta(minutes=59))
    assert all(s['status']=='deferred_deadline' for s in state['pairs'].values())
    report=json.loads((tmp_path/'scientific_report.json').read_text())
    assert report['runs']==0 and report['unrecorded_planned_runs']==2
    with pytest.raises(ValueError):parse_deadline('2026-10-05T10:00:00')


def test_incomplete_arm_in_all_results_not_paired_difference(tmp_path):
    pairs=schedule(['a'],repetitions=1,clis=['opencode']);pair=pairs[0]
    out=tmp_path/pair['pair_id']/'attempt-1'/'no-skills';out.mkdir(parents=True)
    row=fake_row(pair,'no-skills',1,out)
    row.update(cli='opencode',condition='no-skills',repetition=1,attempt=1)
    (out/'experiment_result.json').write_text(json.dumps(row))
    report=write_reports(tmp_path,pairs)
    assert report['runs']==1 and report['completed_pairs']==0
    assert report['paired_differences']=={}


def test_damaged_event_stream_rejected(tmp_path):
    import sys
    from harness.composite_runtime import monitor
    result=monitor([sys.executable,'-c','print("not an audit stream")'],'qwen',
        {'agent_rounds':60,'tool_calls':120},2,tmp_path/'out',tmp_path/'err',lambda _:None,lambda:None)
    assert result['termination_reason']=='unauditable_events'


def test_gateway_decisions_replace_message_count(tmp_path):
    import sys
    from harness.composite_runtime import monitor
    script='import json; print(json.dumps({"type":"step_start","part":{"id":"one"}}))'
    result=monitor([sys.executable,'-c',script],'opencode',{'agent_rounds':60,'tool_calls':120},
        2,tmp_path/'out',tmp_path/'err',lambda _:None,lambda:None,decision_count=lambda:3)
    assert result['agent_rounds']==3 and result['native_event_rounds']==1
