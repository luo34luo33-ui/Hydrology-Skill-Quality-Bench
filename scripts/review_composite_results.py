"""Explicit offline scoring replay; never edits original results or runs agents."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from harness import grader,reporter,runner
from harness.filesystem import filesystem_path,normal_path
from harness.source_references import PUBLIC_CONTEXT,SCORING_VERSION

def main():
    p=argparse.ArgumentParser()
    p.add_argument('runs',nargs='+',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--public-root',type=Path,default=ROOT/'runtime/public')
    a=p.parse_args()
    destination=a.output or ROOT/'results'/('scoring-review-'+SCORING_VERSION)
    destination=Path(filesystem_path(destination))
    if destination.exists():raise ValueError('Use a new correction directory; original results are never overwritten')
    public=Path(filesystem_path(a.public_root));public_hash=runner._sha256_tree(public)
    sources={'root':str(normal_path(public)),'files':{x.relative_to(public).as_posix():runner._sha256_file(x) for x in public.rglob('*') if x.is_file() and '__pycache__' not in x.parts and x.suffix not in {'.pyc','.pyo'}}}
    prepared=[]
    for raw in a.runs:
        run=Path(filesystem_path(raw));meta=json.loads((run/'run_metadata.json').read_text(encoding='utf-8'))
        if meta.get('runtime_controls',{}).get('public_programs_sha256')!=public_hash:
            raise ValueError('Public sources differ from the run lock; provide the matching frozen bundle')
        tasks={x['task']['id']:x for x in runner.discover_tasks(meta['tests_root'],suite='composite')}
        paths=list((run/'tasks').glob('*/result.json'))
        for path in paths:
            item=tasks[path.parent.name]
            if runner._sha256_file(item['task_path'])!=meta['task_hashes'][path.parent.name]:
                raise ValueError('Task changed since original run; provide its original task root')
        prepared.append((run,tasks,paths))
    destination.mkdir(parents=True)
    comparison=[];token=PUBLIC_CONTEXT.set(sources)
    try:
        for run,tasks,paths in prepared:
            for path in paths:
                previous=json.loads(path.read_text(encoding='utf-8'));item=tasks[path.parent.name]
                result=grader.grade_task(item['task'],path.parent/'workspace',item['task_dir'])
                execution=json.loads((path.parent/'execution.json').read_text(encoding='utf-8'))
                if execution.get('return_code')!=0 or execution.get('termination_reason') or not execution.get('eligible',True):result['task_success']=False
                for field in ['resource_usage','execution','eligible']:
                    if field in previous:result[field]=previous[field]
                result['correction']={'source_run':str(normal_path(run)),'source_result_sha256':runner._sha256_file(path),'scoring_version':SCORING_VERSION}
                reporter.write_json(destination/run.name/path.parent.name/'result.json',result)
                before={g['id']:g.get('passed') for g in previous.get('scientific_gates',[])}
                changes=[{'gate':g['id'],'before':before.get(g['id']),'after':g['passed']} for g in result.get('scientific_gates',[]) if before.get(g['id'])!=g['passed']]
                comparison.append({'run':run.name,'task':path.parent.name,'success_before':previous.get('task_success'),'success_after':result['task_success'],'gate_changes':changes,'source_errors':result.get('source_errors',[])})
    finally:PUBLIC_CONTEXT.reset(token)
    reporter.write_json(destination/'comparison.json',{'scoring_version':SCORING_VERSION,'public_sha256':public_hash,'tasks':comparison})
    print(str(normal_path(destination)))

if __name__=='__main__':main()
