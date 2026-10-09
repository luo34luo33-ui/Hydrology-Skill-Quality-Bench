"""Offline paired regrade into a new directory; leaves both source runs untouched."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.filesystem import copy_tree,filesystem_path
from harness.reporter import write_json,aggregate_results
from harness import grader,schemas,runner
from harness.source_references import SCORING_VERSION


def regrade_lane(source,target,task_root):
    source=Path(filesystem_path(source)).resolve();target=Path(filesystem_path(target))
    metadata=json.loads((source/'run_metadata.json').read_text(encoding='utf-8'))
    source_summary=json.loads((source/'summary.json').read_text(encoding='utf-8'))
    source_revision=source_summary.get('task_revision')
    copy_tree(source,target)
    results=[];changes=[]
    for output in sorted((target/'tasks').glob('*/result.json')):
        previous=json.loads(output.read_text(encoding='utf-8'));task_id=previous['test_id']
        candidates=runner.discover_tasks(task_root,test_id=task_id,suite='composite')
        if len(candidates)!=1:raise ValueError('Expected exactly one canonical task for '+task_id)
        task=schemas.load_json(candidates[0]['task_path'])
        if task.get('task_revision')!=source_revision:
            raise ValueError('Source task revision differs from the run: '+task_id)
        audit_path=output.parent/'host_audit.jsonl'
        events=[json.loads(line) for line in audit_path.read_text(encoding='utf-8').splitlines()] if audit_path.is_file() else None
        current=grader.grade_task(task,output.parent/'workspace',candidates[0]['task_dir'],audit_events=events)
        current['execution']=previous.get('execution',{})
        if 'resource_usage' in previous:current['resource_usage']=previous['resource_usage']
        execution_path=output.parent/'execution.json'
        execution=json.loads(execution_path.read_text(encoding='utf-8')) if execution_path.is_file() else {}
        current['eligible']=execution.get('eligible',True)
        if execution.get('return_code',1)!=0 or execution.get('termination_reason'):current['task_success']=False
        if abs(float(previous.get('score',0))-float(current.get('score',0)))>1e-12 or previous.get('task_success')!=current.get('task_success'):
            changes.append({'task_id':task_id,'old_score':previous.get('score'),'new_score':current.get('score'),
                'old_task_success':previous.get('task_success'),'new_task_success':current.get('task_success'),
                'source_errors':current.get('source_errors',[])})
        write_json(output,current);results.append(current)
    summary=aggregate_results(results);write_json(target/'summary.json',summary)
    write_json(target/'regrade_manifest.json',{'source_run':str(source),'task_root':str(task_root),
        'scoring_version':SCORING_VERSION,'source_task_revision':source_revision,
        'source_results_preserved':True,'changed_tasks':changes})
    return summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--no-skills',required=True);p.add_argument('--with-skills',required=True)
    p.add_argument('--task-root',default='composite_tests');p.add_argument('--output',required=True);a=p.parse_args()
    output=Path(filesystem_path(a.output))
    if output.exists():raise ValueError('Regrade output exists; choose a fresh directory')
    output.mkdir(parents=True)
    task_root=Path(filesystem_path(a.task_root))
    left=regrade_lane(a.no_skills,output/'no-skills',task_root)
    right=regrade_lane(a.with_skills,output/'with-skills',task_root)
    write_json(output/'paired_summary.json',{'scoring_version':SCORING_VERSION,
        'no_skills_success_rate':left.get('task_success_rate'),'with_skills_success_rate':right.get('task_success_rate'),
        'no_skills_tasks':left.get('task_runs'),'with_skills_tasks':right.get('task_runs'),
        'notice':'New offline scoring in copied directories; source results are unchanged. Interpret only after attribution review.'})
    print(output)


if __name__=='__main__':main()
