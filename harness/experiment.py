"""Paired serial experiment scheduling and task-clustered reporting."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import random
import numpy as np
from harness import reporter,runner

def schedule(task_ids,seed=20261004,repetitions=3,clis=None):
    rng=random.Random(seed);pairs=[]
    for cli in clis or ['codex','opencode','qwen']:
        for repetition in range(1,repetitions+1):
            order=sorted(task_ids);rng.shuffle(order)
            for i,task in enumerate(order):
                conditions=['no-skills','with-skills'] if (i+repetition)%2 else ['with-skills','no-skills']
                pairs.append({'pair_id':f'{cli}-r{repetition}-{task}','cli':cli,'repetition':repetition,'task_id':task,'conditions':conditions})
    return pairs

def summarize(records,seed=20261004):
    out={'runs':len(records),'startup_failures':sum(not r.get('eligible',True) for r in records),'groups':{},'paired_differences':{}}
    modes={r.get('interaction_mode','confirmation') for r in records}
    if len(modes)>1:raise ValueError('Cannot compare legacy and unattended experiments')
    revisions={r.get('task_revision',1) for r in records if r.get('interaction_mode')=='none'}
    if len(revisions)>1:raise ValueError('Cannot compare different unattended task revisions')
    unattended=modes=={'none'}
    for cli in ['codex','opencode','qwen']:
        for condition in ['no-skills','with-skills']:
            rows=[r for r in records if r['cli']==cli and r['condition']==condition]
            if rows:
                summary=reporter.aggregate_results(rows)
                from harness.resource_usage import resource_summary
                summary['resource_usage']=resource_summary(rows)
                summary['repetitions']={str(rep):reporter._stats([r for r in rows if r['repetition']==rep]) for rep in sorted({r['repetition'] for r in rows})}
                rates=[x['task_success_rate'] for x in summary['repetitions'].values() if x.get('task_success_rate') is not None]
                if len(summary['repetitions'])>1 or not rows:
                    summary['repeat_success_rate_range']=[min(rates),max(rates)] if rates else [None,None]
                elif not rates:
                    summary['repeat_success_rate_range']=[None,None]
                out['groups'][cli+'/'+condition]=summary
        pairs={}
        for r in records:
            if r['cli']==cli and r.get('eligible',True):pairs.setdefault((r['test_id'],r['repetition']),{})[r['condition']]=r
        differences={}
        for (task,_),arms in pairs.items():
            if set(arms)=={'no-skills','with-skills'}:
                a,b=arms['no-skills'],arms['with-skills']
                field='provided_setting_results' if unattended else 'confirmation_results'
                ca,cb=a[field],b[field]
                if len(ca)!=len(cb):raise ValueError('paired confirmation denominators differ')
                delta_confirmed=sum(x['passed'] for x in cb)-sum(x['passed'] for x in ca)
                differences.setdefault(task,[]).append([int(b['task_success'])-int(a['task_success']),int(bool(b['critical_errors']))-int(bool(a['critical_errors'])),delta_confirmed,len(ca)])
        if differences:
            # Task-cluster resampling retains repetitions and confirmation-item weights.
            values=np.array([np.sum(v,axis=0).tolist()+[len(v)] for v in differences.values()],dtype=float)
            def estimates(sample):
                totals=sample.sum(axis=0)
                return [totals[0]/totals[4],totals[1]/totals[4],totals[2]/totals[3] if totals[3] else None]
            rng=np.random.default_rng(seed)
            draws=np.array([[np.nan if v is None else v for v in estimates(values[rng.integers(0,len(values),len(values))])] for _ in range(2000)])
            intervals=[]
            for col in draws.T:
                finite=col[np.isfinite(col)];intervals.append(np.quantile(finite,[.025,.975]).tolist() if len(finite) else [None,None])
            out['paired_differences'][cli]={'paired_tasks':len(values),'paired_runs':sum(len(v) for v in differences.values()),'direction':'with-skills minus no-skills','metrics':['task_success_rate','critical_scientific_error_rate','provided_setting_usage_rate' if unattended else 'necessary_information_confirmation_rate'],'mean':estimates(values),'task_cluster_bootstrap_95pct':np.array(intervals,dtype=object).T.tolist()}

    return out

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--lock',default='runtime/experiment.unattended-v2.lock.json');p.add_argument('--output',default='results/composite-unattended-v2-r4');p.add_argument('--execute',action='store_true');p.add_argument('--pair-id');p.add_argument('--attempt',type=int,default=1);p.add_argument('--report-only',action='store_true')
    p.add_argument('--repetitions',type=int,default=None)
    p.add_argument('--clis',default='codex,opencode,qwen');p.add_argument('--workers',type=int,default=1)
    p.add_argument('--resume',action='store_true');p.add_argument('--deadline')
    a=p.parse_args(argv)
    clis=a.clis.split(',')
    if len(set(clis))!=len(clis) or not clis or any(c not in {'codex','opencode','qwen'} for c in clis):p.error('Invalid --clis')
    if not 1<=a.workers<=3:p.error('--workers must be 1..3')
    from harness.overnight import run_schedule, write_reports, parse_deadline
    deadline=parse_deadline(a.deadline)
    root=Path(a.output);root.mkdir(parents=True,exist_ok=True)
    lock=json.loads(Path(a.lock).read_text(encoding='utf-8'));tasks=runner.discover_tasks(suite='composite')
    repetitions=a.repetitions if a.repetitions is not None else lock['repetitions']
    if repetitions<1:p.error('--repetitions must be positive')
    versions={x['task'].get('task_version') for x in tasks}
    if versions!={'composite-unattended-v2'}:raise ValueError('Only unattended v2 tasks are scheduled')
    pairs=schedule([x['task']['id'] for x in tasks],lock['seed'],repetitions,clis)
    revisions={x['task'].get('task_revision',1) for x in tasks}
    if len(revisions)!=1:raise ValueError('Mixed task revisions cannot be scheduled')
    revision=revisions.pop()
    for pair in pairs:pair.update(task_version='composite-unattended-v2',task_revision=revision,interaction_mode='none')
    schedule_path=root/'schedule.json';doc={'task_version':'composite-unattended-v2','task_revision':revision,'interaction_mode':'none','task_hashes':{x['task']['id']:runner._sha256_tree(x['task_dir']) for x in tasks},'seed':lock['seed'],'repetitions':repetitions,'pairs':pairs,'runs':len(pairs)*2}
    if schedule_path.exists() and json.loads(schedule_path.read_text(encoding='utf-8'))!=doc:raise ValueError('existing schedule differs')
    reporter.write_json(schedule_path,doc)
    if a.execute:
        from harness.composite_runtime import preflight
        check=preflight(a.lock,clis)
        if not check['ready']:raise ValueError('formal runtime not ready: '+str(check['issues']))
        def execute(pair,condition,attempt,out):
            result=runner.run_benchmark(suite='composite',test_id=pair['task_id'],runtime_lock=a.lock,
                composite_cli=pair['cli'],skills_path='runtime/skills' if condition=='with-skills' else None,output=out)
            return {**result['results'][0],'cli':pair['cli'],'condition':condition,
                'repetition':pair['repetition'],'attempt':attempt}
        import hashlib
        run_schedule(root,pairs,execute,workers=a.workers,resume=a.resume,deadline=deadline,
            pair_id=a.pair_id,attempt=a.attempt,lock_hash=hashlib.sha256(Path(a.lock).read_bytes()).hexdigest())
    if a.report_only or a.execute:
        write_reports(root,pairs)
    print(json.dumps({'schedule_runs':len(pairs)*2,'real_agents_executed':a.execute},ensure_ascii=False))
if __name__=='__main__':main()
