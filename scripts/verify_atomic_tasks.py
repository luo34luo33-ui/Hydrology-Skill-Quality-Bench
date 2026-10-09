"""Run native tools in fresh workspaces; never run an Agent."""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import grader, runner
from atomic_tasks import DEFAULT_SKILLS, GROUPS, execute
from atomic_fixture_support import read, write

def main(family=None):
    parser=argparse.ArgumentParser();parser.add_argument('--skills-root',type=Path,default=DEFAULT_SKILLS);parser.add_argument('--task-id');args=parser.parse_args()
    selected=[]
    for item in runner.discover_tasks('tests'):
        group=item['task']['id'].rsplit('-',1)[0]
        if group not in GROUPS: continue
        if family=='bma' and group!='hydroanalysis-bma': continue
        if family=='atlas' and not group.startswith('hydrovisual'): continue
        if family=='report' and not group.startswith('hydroreport'): continue
        if args.task_id and item['task']['id']!=args.task_id: continue
        selected.append(item)
    if not selected: raise ValueError('No matching atomic tasks')
    failures=[];records=[]
    for item in selected:
        task,folder=item['task'],item['task_dir'];recipe=read(folder/'expected/recipe.json')
        try:
            with tempfile.TemporaryDirectory(prefix='hsqb-native-verify-') as temp:
                workspace=Path(temp);shutil.copytree(folder/'data',workspace,dirs_exist_ok=True)
                execute(recipe['group'],recipe['steps'],workspace,args.skills_root)
                result=grader.grade_task(task,workspace,folder)
                print(task['id'],f"score={result['score']:.8f}",flush=True)
                records.append(dict(task_id=task['id'],score=round(result['score'],12),raw_score=result['score'],exit_codes=[s['code'] for s in recipe['steps']]))
                if result['score']<1-1e-12:
                    failures.append(task['id']+': '+str(result))
        except Exception as exc: failures.append(task['id']+': '+str(exc))
    if failures:
        print('\n'.join(failures),file=sys.stderr);return 1
    write(Path(__file__).resolve().parents[1]/'docs'/f"atomic-native-{family or 'all'}.json",dict(method='Unchanged native entrypoints through documented XML/Matplotlib compatibility bootstrap; fresh workspaces; no Agent.',acceptance_tolerance=1e-12,tasks=records))
    print(f'{len(selected)} native-script tasks passed; no Agent batches run.');return 0

if __name__=='__main__': raise SystemExit(main())
