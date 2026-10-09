"""Regenerate every case in two temporary trees and grade scientific equivalence."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import pyexpat
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from composite_tasks import generate
from composite_common import ROOT,write_json
from harness import runner,grader

def run_case(item,base):
    task=item['task'];family=task['id'].split('-')[1];n=int(task['id'].split('-')[2]);d=generate(family,n,base/task['domain']/task['id'])
    canonical=item['task_dir'];audit=[] if task.get('interaction_mode')=='none' else json.loads((canonical/'expected/audit_fixture.json').read_text(encoding='utf-8'))['events']
    r=grader.grade_task(task,d/'expected/golden_workspace',canonical,audit_events=audit)
    # Stable text contracts exclude location hashes/provenance; actual file references
    # are separately verified against each regenerated workspace by the grader.
    return {'task_id':task['id'],'score':r['score'],'scientifically_equivalent':r['task_success'],'failed_gates':[g for g in r['scientific_gates'] if not g['passed']]}

def main():
    items=runner.discover_tasks(ROOT/'tests',suite='composite');rounds=[]
    for iteration in range(2):
        with tempfile.TemporaryDirectory(prefix='hsqb-composite-',dir=ROOT/'.cache') as temp:
            with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda x:run_case(x,Path(temp)),items))
            rounds.append({'iteration':iteration+1,'results':results,'passed':sum(r['scientifically_equivalent'] for r in results)})
            print('round',iteration+1,'passed',rounds[-1]['passed'],flush=True)
    write_json(ROOT/'docs/composite-repeatability.json',{'task_version':'composite-unattended-v2','interaction_mode':'none','rounds':rounds,'real_agents_run':0,'confirmation_events_used':0,'comparison':'Scientific contracts, table numeric/temporal semantics, raster/vector geometry, scientific figure layers, dependencies, and independently recomputed invariants; not container paths or binary hashes.'})
    if any(r['passed']!=24 for r in rounds):raise SystemExit(1)
if __name__=='__main__':main()
