"""Validate upfront inputs and honestly report live-agent feasibility."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness import runner,schemas,reporter
from harness.composite_grader import get
from harness.composite_runtime import preflight


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--lock',default='runtime/experiment.unattended-v2.lock.json')
    parser.add_argument('--runs-dir',default='results/composite-unattended-v2-r4')
    args=parser.parse_args()
    rows=[]
    for item in runner.discover_tasks(suite='composite'):
        task=item['task'];data=item['task_dir']/'data'
        spec=json.loads((item['task_dir']/task['evaluation_reference']).read_text(encoding='utf-8'))
        scenario=json.loads((data/'scenario.json').read_text(encoding='utf-8'))
        interfaces=json.loads((data/'output_interfaces.json').read_text(encoding='utf-8'))
        problems=schemas.validate_task(task,item['task_dir'])
        sections=['variables','time','task_science','model_initialization','baseflow_initialization',
            'forcing_selection','quality_control','alignment','evaluation','implementation_choices','scientific_constraints']
        if task['id']=='hydrochain-model-010':sections.append('routing_stability_audit')
        if task['id'] in {'hydrochain-model-011','hydrochain-model-012'}:sections.append('calibration')
        if task['id']=='hydrochain-analysis-004':sections.append('review')
        for section in sections:
            if section not in scenario:problems.append('missing scientific section: '+section)
        if scenario.get('interaction_mode')!='none' or spec.get('confirmations'):problems.append('interactive dependency')
        for setting in spec['provided_settings']:
            value=get(json.loads((data/setting['source']).read_text(encoding='utf-8')),setting['field'])
            if any(value!=b['expected'] for b in setting['bindings']):problems.append('invisible scientific fact: '+setting['key'])
        # Invariants may not silently consume undeclared candidate output files.
        for gate in spec['gates']:
            for criterion in gate['criteria']:
                paths=[criterion.get(k) for k in ['target','series','markdown']]+criterion.get('targets',[])
                for rel in paths:
                    if isinstance(rel,str) and rel not in task['data_files'] and rel not in interfaces['outputs']:
                        problems.append('undeclared output: '+rel)
        rows.append({'task_id':task['id'],'task_version':task['task_version'],
            'task_revision':task['task_revision'],'active_forward_model':scenario['task_science']['active_forward_model'],
            'scientific_sections':sections,
            'outcome_goal':task['outcome_goal'],'interaction_mode':task['interaction_mode'],
            'input_files':len(task['data_files']),'outputs':len(task['required_outputs']),
            'provided_settings':[x['key'] for x in spec['provided_settings']],
            'complete':not problems,'problems':problems})
    infrastructure=[]
    # CLI executables live in the frozen image. Host CLI inventory is diagnostic only.
    commands={name:bool(shutil.which(name)) for name in ['docker','codex','opencode','qwen']}
    user_docker=Path.home()/'AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe'
    docker=shutil.which('docker') or (str(user_docker) if user_docker.is_file() else None)
    commands['docker']=bool(docker)
    if not docker:infrastructure.append('Docker executable is unavailable in this host environment')
    else:
        try:
            probe=subprocess.run([docker,'version','--format','{{.Server.Version}}'],capture_output=True,text=True,timeout=15)
            if probe.returncode:infrastructure.append('Docker daemon is unavailable')
        except (OSError,subprocess.TimeoutExpired):infrastructure.append('Docker is installed but cannot be accessed by this process; run with the authorised Docker execution context')
    check=preflight(args.lock,['codex','opencode','qwen'])
    infrastructure+=check['issues']
    from harness.overnight import latest_records
    runs=Path(args.runs_dir);schedule_path=runs/'schedule.json'
    records=[]
    if schedule_path.is_file():
        scheduled=json.loads(schedule_path.read_text(encoding='utf-8'))
        if scheduled.get('task_version')!='composite-unattended-v2' or scheduled.get('task_revision',1)!=4:raise ValueError('Old live runs cannot certify this task revision')
        records,_,_,_=latest_records(runs,scheduled['pairs'])
    started=[r for r in records if r.get('eligible',False)]
    live_status=('completed' if len(records)==144 and len(started)==144 else
        'partial' if records else 'ready_not_executed' if not infrastructure else 'not_executed_environment_unavailable')
    report={'task_version':'composite-unattended-v2','interaction_mode':'none','tasks':rows,
        'complete_tasks':sum(r['complete'] for r in rows),
        'real_agent_validation':{'planned_runs':144,'recorded_runs':len(records),'real_agents_run':len(started),
            'successful_runs':sum(bool(r.get('task_success')) for r in started),'status':live_status,
            'host_commands_available':commands,'preflight':check,'blocking_items':infrastructure,
            'note':'This audit does not invoke agents. Reference computations are separate evidence.'}}
    reporter.write_json(ROOT/'docs/composite-unattended-audit.json',report)
    lines=['# 24 题启动前资料完整性审计','',
        '| 任务 | 目标 | 完整 | 有效前向模型 | 输入／公开输出数 | 提前提供且检查落实的设定 |','|---|---|---|---|---|---|']
    lines += [f"| {r['task_id']} | {r['outcome_goal']} | {r['complete']} | {r['active_forward_model']} | {r['input_files']} / {r['outputs']} | {', '.join(r['provided_settings'])} |" for r in rows]
    lines+=['','全部任务均提供变量、单位、时间、状态组织、空间资料、权限与公开输出接口；逐项问题见 JSON。','',
        f'真实 Agent 验证计划 144 次；已记录 {len(records)} 次，实际启动 {len(started)} 次。此审计本身不启动 Agent。',*['- '+p for p in infrastructure]]
    (ROOT/'docs/composite-unattended-inputs.zh-CN.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'complete_tasks':report['complete_tasks'],'real_agents_run':len(started),'live_ready':not infrastructure},ensure_ascii=False))
    if report['complete_tasks']!=24:raise SystemExit(1)


if __name__=='__main__':main()
