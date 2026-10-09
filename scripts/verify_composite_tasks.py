"""Deterministic native acceptance; no CLI agent or model service is launched."""
import argparse
import json
import pyexpat
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from composite_common import ROOT,write_json
from composite_tasks import generate
from harness import runner,grader

def refresh():
    # Regenerate input and public output contracts together; a partial refresh
    # would leave the visible interfaces out of sync with the hidden checker.
    for x in runner.discover_tasks(ROOT/'tests',suite='composite'):
        task=x['task'];generate(task['id'].split('-')[1],int(task['id'].split('-')[2]))

def main():
    p=argparse.ArgumentParser();p.add_argument('--native',action='store_true');p.add_argument('--refresh',action='store_true');a=p.parse_args()
    if a.native:
        for x in runner.discover_tasks(ROOT/'tests',suite='composite'):
            t=x['task'];generate(t['id'].split('-')[1],int(t['id'].split('-')[2]))
    if a.refresh and not a.native:refresh()
    errors=runner.validate_tests(ROOT/'tests',suite='all')
    if errors:raise RuntimeError(errors)
    results=[]
    for x in runner.discover_tasks(ROOT/'tests',suite='composite'):
        d=x['task_dir'];events=[] if x['task'].get('interaction_mode')=='none' else json.loads((d/'expected/audit_fixture.json').read_text(encoding='utf-8'))['events']
        r=grader.grade_task(x['task'],d/'expected/golden_workspace',d,audit_events=events);results.append(r)
        print(r['test_id'],r['score'],r['task_success'],flush=True)
        if not r['task_success']:print([g for g in r['scientific_gates'] if not g['passed']],flush=True)
    report={'task_version':'composite-unattended-v2','interaction_mode':'none','all_definitions':len(runner.discover_tasks(ROOT/'tests',suite='all')),'atomic_definitions':len(runner.discover_tasks(ROOT/'tests')),'composite_definitions':len(results),'golden_passed':sum(r['task_success'] for r in results),'native_rerun_this_invocation':a.native or a.refresh,'real_agents_run':0,'confirmation_events_used':0,'results':results}
    write_json(ROOT/'docs/composite-acceptance.json',report)
    if report['golden_passed']!=24:raise SystemExit(1)
if __name__=='__main__':main()
