"""Resume a paused CLI after an external service change, retaining prior attempts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness import runner
from harness.composite_runtime import preflight
from harness.overnight import atomic_json,failure_row,run_guard,keep_awake


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='results/composite-unattended-v2-r4')
    parser.add_argument('--lock',default='runtime/experiment.unattended-v2.lock.json')
    parser.add_argument('--cli',required=True,choices=['codex','opencode','qwen'])
    args=parser.parse_args();root=(ROOT/args.output).resolve();root.relative_to(ROOT)
    lock=ROOT/args.lock;doc=json.loads((root/'schedule.json').read_text(encoding='utf-8'))
    state=json.loads((root/'dispatcher.json').read_text(encoding='utf-8'))
    if doc.get('interaction_mode')!='none':raise ValueError('Only unattended schedules can recover')
    if state['runtime_lock_sha256']!=hashlib.sha256(lock.read_bytes()).hexdigest():raise ValueError('Frozen runtime changed')
    if any(v['cli']==args.cli and v['status']=='running' for v in state['pairs'].values()):raise ValueError('CLI lane still active')
    if sum(v['status']=='running' for v in state['pairs'].values())>2:raise ValueError('Recovery would exceed three candidate workers')
    tasks={x['task']['id']:x for x in runner.discover_tasks(suite='composite')}
    for identity,digest in doc['task_hashes'].items():
        if runner._sha256_tree(tasks[identity]['task_dir'])!=digest:raise ValueError('Frozen task changed: '+identity)
    check=preflight(lock,[args.cli])
    if not check['ready']:raise ValueError('Runtime is not ready: '+str(check['issues']))
    receipt=root/f'recovery-{args.cli}.json';runs=[]
    with run_guard(root/f'recovery-{args.cli}'),keep_awake():
        atomic_json(receipt,{'state':'running','cli':args.cli,'reason':'external usage-window reset; same frozen tasks and runtime','runs':runs})
        for pair in [p for p in doc['pairs'] if p['cli']==args.cli]:
            base=root/pair['pair_id'];attempts=sorted(base.glob('attempt-*'),key=lambda p:int(p.name.split('-')[-1]))
            if attempts:
                rows=[json.loads(p.read_text(encoding='utf-8')) for p in attempts[-1].glob('*/experiment_result.json')]
                if len(rows)==2 and all(r.get('eligible',False) for r in rows):continue
            attempt=int(attempts[-1].name.split('-')[-1])+1 if attempts else 1
            rows=[]
            for condition in pair['conditions']:
                output=base/f'attempt-{attempt}'/condition;output.mkdir(parents=True,exist_ok=False)
                try:
                    result=runner.run_benchmark(suite='composite',test_id=pair['task_id'],runtime_lock=lock,
                        composite_cli=args.cli,skills_path=ROOT/'runtime/skills' if condition=='with-skills' else None,output=output)
                    row=result['results'][0]
                except Exception as error:row=failure_row(pair,condition,attempt,error)
                row.update(cli=args.cli,condition=condition,repetition=pair['repetition'],attempt=attempt)
                atomic_json(output/'experiment_result.json',row);rows.append(row)
                summary={k:row.get(k) for k in ['test_id','condition','attempt','eligible','task_success']}
                runs.append(summary);atomic_json(receipt,{'state':'running','cli':args.cli,'runs':runs})
                print(json.dumps(summary),flush=True)
            if not all(r.get('eligible',False) for r in rows):
                atomic_json(receipt,{'state':'paused_environment_unavailable','cli':args.cli,'runs':runs})
                return
        atomic_json(receipt,{'state':'completed','cli':args.cli,'runs':runs})


if __name__=='__main__':main()
