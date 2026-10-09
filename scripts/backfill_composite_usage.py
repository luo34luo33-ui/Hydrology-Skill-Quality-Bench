"""Append recoverable resource statistics without regrading scientific results."""
import argparse
import csv
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.overnight import atomic_json,write_reports
from harness.resource_usage import resource_fields,usage_from_logs
from harness import reporter


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runs-dir',default='results/composite-unattended-v2-r4')
    args=parser.parse_args();root=(ROOT/args.runs_dir).resolve();root.relative_to(ROOT/'results')
    records=[];run_dirs=set()
    for path in sorted(root.glob('*/attempt-*/*/tasks/*/result.json')):
        row=json.loads(path.read_text(encoding='utf-8'))
        if row.get('task_kind')!='composite':continue
        task_dir=path.parent;execution_path=task_dir/'execution.json'
        execution=json.loads(execution_path.read_text(encoding='utf-8')) if execution_path.exists() else {}
        resources=row.get('resource_usage',{})
        tokens=usage_from_logs(task_dir)
        if tokens['measurement']=='unavailable':tokens=resources.get('tokens') or execution.get('token_usage') or tokens
        resources.update(wall_seconds=resources.get('wall_seconds'),
            agent_seconds=resources.get('agent_seconds',execution.get('duration_seconds')),
            tokens=tokens)
        if resources['wall_seconds'] is None:
            resources['historical_wall_time_note']='Total preparation/cleanup/grading time was not recorded in older runs; null is not zero.'
        row['resource_usage']=resources;atomic_json(path,row)
        experiment_path=task_dir.parents[1]/'experiment_result.json'
        run_dirs.add(task_dir.parents[1])
        if experiment_path.exists():
            experiment=json.loads(experiment_path.read_text(encoding='utf-8'))
            experiment['resource_usage']=resources;atomic_json(experiment_path,experiment)
        records.append({'task_id':row['test_id'],'run':path.relative_to(root).as_posix(),**resource_fields(row)})
    for directory in run_dirs:
        rows=[json.loads(p.read_text(encoding='utf-8')) for p in (directory/'tasks').glob('*/result.json')]
        atomic_json(directory/'summary.json',reporter.aggregate_results(rows))
    output=root/'resource_usage.csv'
    with output.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['task_id','run','wall_seconds','agent_seconds','input_tokens','output_tokens','total_tokens','token_measurement'])
        writer.writeheader();writer.writerows(records)
    schedule=json.loads((root/'schedule.json').read_text(encoding='utf-8'))
    write_reports(root,schedule['pairs'])
    print(json.dumps({'updated_attempt_runs':len(records),'reported_token_runs':sum(r['token_measurement']=='reported_cli' for r in records),'statistics_csv':str(output)}))


if __name__=='__main__':main()
