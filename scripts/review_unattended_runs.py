"""Summarize actual unattended runs; flag visible requests for human review."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness.overnight import latest_records


def assistant_text(event):
    if event.get('type')=='item.completed':
        item=event.get('item',{})
        return item.get('text','') if item.get('type')=='agent_message' else ''
    if event.get('type')=='assistant':
        return '\n'.join(p.get('text','') for p in event.get('message',{}).get('content',[]) if p.get('type')=='text')
    if event.get('type')=='text':
        return event.get('part',{}).get('text','')
    return ''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--runs-dir',default='results/composite-unattended-v2-r4')
    args=parser.parse_args();runs=ROOT/args.runs_dir
    schedule=json.loads((runs/'schedule.json').read_text(encoding='utf-8'))
    if schedule.get('task_revision')!=4 or schedule.get('task_version')!='composite-unattended-v2':
        raise ValueError('Only the current revision can certify this repair')
    records,_,_,_=latest_records(runs,schedule['pairs'])
    cases=[];violations=[];requests=[]
    request=re.compile(r'(?:please|could you|can you|need you to)\s+(?:provide|confirm|clarify|supply|tell|upload)|(?:请|需要您|需要用户)(?:提供|确认|补充|澄清)',re.I)
    for record in records:
        case={k:record.get(k) for k in ['cli','test_id','condition','eligible','task_success','task_revision']}
        pair=f"{record['cli']}-r1-{record['test_id']}"
        attempts=sorted((runs/pair).glob('attempt-*'),key=lambda p:int(p.name.split('-')[1]))
        task_dir=attempts[-1]/record['condition']/'tasks'/record['test_id']
        execution_path=task_dir/'execution.json'
        execution=json.loads(execution_path.read_text(encoding='utf-8')) if execution_path.is_file() else {}
        case['diagnostic_category']=execution.get('diagnostic_category','not_started')
        case['execution_status']=record.get('execution',{})
        case['confirmation_service_started']=execution.get('confirmation_service_started')
        case['confirmation_requests']=execution.get('confirmation_requests')
        case['failed_gates']=[g['id'] for g in record.get('scientific_gates',[]) if not g['passed']]
        case['failed_criteria']=dict(Counter(c.get('details','unknown') for g in record.get('scientific_gates',[]) for c in g.get('criteria',[]) if c.get('score')!=1.0))
        gateway=task_dir/'model_gateway_audit.jsonl'
        statuses=Counter()
        if gateway.is_file():
            for line in gateway.read_text(encoding='utf-8').splitlines():
                try: statuses[str(json.loads(line).get('status','unknown'))]+=1
                except ValueError: continue
        case['gateway_status_counts']=dict(statuses)
        case['upstream_errors_observed']=any(k.isdigit() and int(k)>=400 for k in statuses)
        categories=set()
        if not case['task_success'] and case['execution_status'].get('return_code',0)!=0:
            categories.add('execution_or_budget_failure')
        for detail in case['failed_criteria']:
            if detail.startswith('grading error:') and ('subpath' in detail or 'absolute' in detail):
                categories.add('artifact_reference_outside_workspace')
            elif detail in ['manifest_integrity','json_contract','markdown_json_consistency']:
                categories.add('public_artifact_contract')
            elif 'figure contract' in detail:
                categories.add('public_figure_contract')
            elif detail.startswith('matched_cells=') or 'recompute' in detail or detail=='geometry differs':
                categories.add('scientific_value_or_semantics_mismatch')
            else: categories.add('other_requires_review')
        case['failure_categories']=sorted(categories)
        case['visible_assistant_messages']=0
        if execution.get('confirmation_service_started') or execution.get('confirmation_requests',0):
            violations.append({**case,'reason':'confirmation channel used'})
        log=task_dir/'stdout.log'
        if log.is_file():
            for line in log.read_text(encoding='utf-8',errors='replace').splitlines():
                try:text=assistant_text(json.loads(line))
                except ValueError:continue
                case['visible_assistant_messages']+=bool(text.strip())
                if request.search(text):requests.append({'cli':case['cli'],'task_id':case['test_id'],'condition':case['condition'],'text':text[:1200],'status':'requires_review; keyword match is not proof of missing information'})
        cases.append(case)
    by_cli={cli:{'recorded':sum(c['cli']==cli for c in cases),'started':sum(c['cli']==cli and bool(c['eligible']) for c in cases),'successful':sum(c['cli']==cli and bool(c['task_success']) for c in cases)} for cli in ['codex','opencode','qwen']}
    failure_categories=dict(Counter(k for c in cases for k in c['failure_categories']))
    report={'task_version':schedule['task_version'],'task_revision':4,'planned_runs':144,'recorded_runs':len(cases),'by_cli':by_cli,'failure_categories':failure_categories,'upstream_error_cases':sum(c['upstream_errors_observed'] for c in cases),'confirmation_channel_violations':violations,'visible_request_candidates':requests,'cases':cases,'note':'Failure categories describe observed checks, not a blanket attribution to the Agent. Scientific failures are allowed. Keyword candidates require inspection, and cannot by themselves establish a task-design defect. Some CLI streams emit tool events without assistant text; a zero keyword count only describes the visible emitted text. Service isolation and no supplemental input are audited separately.'}
    (ROOT/'docs/composite-unattended-live-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 真实 Agent 无交互验证','',f'当前修订计划 144 次，已记录 {len(cases)} 次。','', '| CLI | 已记录 | 实际模型启动 | 科学成功 |','|---|---:|---:|---:|']
    lines += [f"| {cli} | {counts['recorded']} | {counts['started']} | {counts['successful']} |" for cli,counts in by_cli.items()]
    lines+=['',f'确认入口使用违规：{len(violations)}。可见求助关键词候选：{len(requests)}，须独立检查上下文。','部分 CLI 流仅输出工具事件，没有可见回复文本；零关键词只说明实际输出文本中未发现候选，不能据此推断未输出的内容。确认服务隔离与运行期间无信息补充另有执行审计。','', '逐次失败闸门与执行诊断见 [机器报告](composite-unattended-live-review.json)。','参考计算与真实执行分别报告；科学失败不自动说明资料缺失。']
    lines+=['', '失败证据分类（同一次运行可有多类；分类不等同于责任归因）：','', '| 类别 | 涉及运行数 |','|---|---:|']
    lines += [f'| {category} | {count} |' for category,count in sorted(failure_categories.items())]
    lines += ['', f"当前选定运行中出现上游 HTTP 错误：{report['upstream_error_cases']} 次。被重试替代的启动失败仍保留在原 attempt 目录，不计为已完成科学验证。"]
    (ROOT/'docs/composite-unattended-live-review.zh-CN.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'recorded':len(cases),'by_cli':by_cli,'confirmation_violations':len(violations),'request_candidates':len(requests)}))


if __name__=='__main__':main()
