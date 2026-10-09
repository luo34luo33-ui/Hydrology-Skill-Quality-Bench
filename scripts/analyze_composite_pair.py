"""Create a diagnostic task matrix from two existing runs; launches no agents."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.filesystem import filesystem_path
from harness.reporter import write_json


def load_run(path):
    root=Path(filesystem_path(path)).resolve()
    summary=json.loads((root/'summary.json').read_text(encoding='utf-8'))
    metadata=json.loads((root/'run_metadata.json').read_text(encoding='utf-8'))
    rows={}
    for result_path in (root/'tasks').glob('*/result.json'):
        result=json.loads(result_path.read_text(encoding='utf-8'))
        execution_path=result_path.parent/'execution.json'
        execution=json.loads(execution_path.read_text(encoding='utf-8')) if execution_path.is_file() else {}
        stdout=result_path.parent/'stdout.log'
        rows[result['test_id']]={'result':result,'execution':execution,'stdout':stdout}
    return root,summary,metadata,rows


def classify(row,skills_enabled):
    result=row['result'];text=' '.join(str(x) for x in result.get('scientific_gates',[]))
    causes=[]
    if skills_enabled and row['stdout'].is_file() and 'ripgrep execution failed' in row['stdout'].read_text(encoding='utf-8',errors='replace').lower():
        causes.append('skill_deployment')
    if result.get('source_errors') or 'not in the subpath' in text or 'grading error:' in text:
        causes.append('scoring_or_source_interface')
    if result.get('critical_errors'):
        causes.append('scientific_error')
    if result.get('assessability')=='insufficient_evidence':
        causes.append('missing_or_insufficient_evidence')
    return ', '.join(causes) if causes else 'agent_or_task_execution'


def main():
    p=argparse.ArgumentParser();p.add_argument('--no-skills',required=True);p.add_argument('--with-skills',required=True)
    p.add_argument('--output',required=True);a=p.parse_args()
    left_path,left_summary,left_meta,left=load_run(a.no_skills);right_path,right_summary,right_meta,right=load_run(a.with_skills)
    ids=sorted(set(left)|set(right));rows=[]
    for task_id in ids:
        l=left.get(task_id);r=right.get(task_id)
        rows.append({'task_id':task_id,
            'no_skills_success':bool(l and l['result'].get('task_success')),
            'with_skills_success':bool(r and r['result'].get('task_success')),
            'no_skills_score':l['result'].get('score') if l else None,
            'with_skills_score':r['result'].get('score') if r else None,
            'no_skills_failure_class':classify(l,False) if l and not l['result'].get('task_success') else None,
            'with_skills_failure_class':classify(r,True) if r and not r['result'].get('task_success') else None,
            'no_skills_failed_gates':[g['id'] for g in l['result'].get('scientific_gates',[]) if not g.get('passed')] if l else [],
            'with_skills_failed_gates':[g['id'] for g in r['result'].get('scientific_gates',[]) if not g.get('passed')] if r else [],
            'no_skills_termination':l['execution'].get('termination_reason') if l else None,
            'with_skills_termination':r['execution'].get('termination_reason') if r else None,
            'no_skills_resource_usage':l['result'].get('resource_usage') if l else None,
            'with_skills_resource_usage':r['result'].get('resource_usage') if r else None})
    paired={'both_success':sum(x['no_skills_success'] and x['with_skills_success'] for x in rows),
        'no_skills_only':sum(x['no_skills_success'] and not x['with_skills_success'] for x in rows),
        'with_skills_only':sum(not x['no_skills_success'] and x['with_skills_success'] for x in rows),
        'neither':sum(not x['no_skills_success'] and not x['with_skills_success'] for x in rows)}
    report={'analysis_type':'descriptive_failure_attribution','task_version':left_summary.get('task_version'),
        'task_revision':left_summary.get('task_revision'),'no_skills_run':str(left_path),'with_skills_run':str(right_path),
        'run_compatibility':{'same_task_ids':set(left)==set(right),'same_count':len(left)==len(right),
            'task_revisions_match':left_meta.get('task_revision')==right_meta.get('task_revision'),
            'skill_groups_distinct':left_meta.get('skill_condition')!=right_meta.get('skill_condition'),
            'no_skills_condition':left_meta.get('skill_condition'),'with_skills_condition':right_meta.get('skill_condition')},
        'no_skills_success_rate':left_summary.get('task_success_rate'),
        'with_skills_success_rate':right_summary.get('task_success_rate'),'paired_outcomes':paired,'tasks':rows,
        'notice':'Descriptive only. Does not establish causality or recalculate scores.'}
    output=Path(filesystem_path(a.output));output.mkdir(parents=True,exist_ok=False)
    write_json(output/'pair_attribution.json',report)
    lines=['# 配对任务失败归因','',f"无技能成功率：{report['no_skills_success_rate']}",
        f"有技能成功率：{report['with_skills_success_rate']}",'',
        f"配对结果：{paired}",'','| Task | no-skills | with-skills | no-skills 失败归因 / 门槛 | with-skills 失败归因 / 门槛 |',
        '|---|---:|---:|---|---|']
    short_gates=lambda gates: ', '.join(gates[:4])+(f' … (+{len(gates)-4})' if len(gates)>4 else '')
    lines.extend(f"| {x['task_id']} | {x['no_skills_success']} | {x['with_skills_success']} | {x['no_skills_failure_class'] or '—'} / {short_gates(x['no_skills_failed_gates']) or '—'} | {x['with_skills_failure_class'] or '—'} / {short_gates(x['with_skills_failed_gates']) or '—'} |" for x in rows)
    lines+=['','失败分类只用于定位问题；原始分数和运行记录未修改。']
    (output/'pair_attribution.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(output)


if __name__=='__main__':main()
