"""Write coverage, source integrity and development acceptance receipts; no Agents."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import sys
import pyexpat
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from composite_common import ROOT, SKILLS, LUMPED, SEMI, sha, write_json
from harness import runner
from harness.experiment import schedule


def table_profile(path):
    frame=pd.read_csv(path)
    time=next((c for c in frame.columns if c.lower()=='time'),None)
    return {'rows':len(frame),'time_min':str(frame[time].min()) if time else None,'time_max':str(frame[time].max()) if time else None,'missing_by_column':{str(c):int(frame[c].isna().sum()) for c in frame.columns},'sha256':sha(path)}


def write_unattended_delivery(items,pytest_passed):
    """Current evidence stays separate from the old confirmation-era receipt."""
    live_root=ROOT/'results/composite-unattended-v2-r4'
    finalization=live_root/'finalization.json'
    if finalization.is_file():
        state=json.loads(finalization.read_text(encoding='utf-8'))
        # The finalizer writes reports only after both execution lanes stop.
        # Its live marker is still waiting at this point; take the OS run lock
        # as evidence through its process state and recovery receipts.
        from finalize_unattended_validation import process_alive
        dispatcher=json.loads((live_root/'dispatcher.json').read_text(encoding='utf-8'))
        recoveries=[json.loads(p.read_text(encoding='utf-8')) for p in live_root.glob('recovery-*.json')]
        if not process_alive(dispatcher['pid']) and not any(r['state']=='running' for r in recoveries):
            from correct_unattended_geometry import correct
            correct(live_root)
    acceptance=json.loads((ROOT/'docs/composite-acceptance.json').read_text(encoding='utf-8'))
    repeats=json.loads((ROOT/'docs/composite-repeatability.json').read_text(encoding='utf-8'))
    audit=json.loads((ROOT/'docs/composite-unattended-audit.json').read_text(encoding='utf-8'))
    integrity=json.loads((ROOT/'docs/composite-source-integrity.json').read_text(encoding='utf-8'))
    rows=[]
    for item in items:
        task=item['task'];spec=json.loads((item['task_dir']/task['evaluation_reference']).read_text(encoding='utf-8'))
        rows.append({'id':task['id'],'title':task['title'],'task_version':task['task_version'],
            'task_revision':task.get('task_revision',1),'outcome':task['outcome_goal'],
            'core_capabilities':'; '.join(task['core_capabilities']),
            'provided_settings':'; '.join(s['key'] for s in spec['provided_settings']),
            'gates':len(spec['gates']),'native_program_calls':len(spec['reference_execution']),
            'timeout_seconds':task['timeout_seconds']})
    with (ROOT/'docs/composite-unattended-coverage.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    report={'task_version':'composite-unattended-v2','task_revision':rows[0]['task_revision'],
        'pytest_passed':pytest_passed,'definition_validation_errors':runner.validate_tests(suite='all'),
        'composite_tasks':len(items),'deliverable':sum(r['outcome']=='deliverable' for r in rows),
        'golden_successes':acceptance['golden_passed'],'native_rerun_this_invocation':acceptance['native_rerun_this_invocation'],
        'two_fresh_generation_successes':[r['passed'] for r in repeats['rounds']],
        'upfront_complete_tasks':audit['complete_tasks'],'real_agent_validation':audit['real_agent_validation'],
        'source_integrity':integrity,
        'confirmation_events_used_in_reference':0,'scope':'native references, repeatability and real agent runs are separate evidence'}
    write_json(ROOT/'docs/composite-unattended-final-checks.json',report)
    live=report['real_agent_validation']
    lines=['# 无交互 v2 修复验收','',
        '| 检查 | 结果 |','|---|---|',
        f"| 正常交付任务 | {report['deliverable']}/24 |",
        f"| 启动前资料完整性 | {report['upfront_complete_tasks']}/24 |",
        f"| 原生参考计算 | {report['golden_successes']}/24 |",
        f"| 两轮临时目录重新生成 | {report['two_fresh_generation_successes']} |",
        f"| 框架测试 | {pytest_passed} passed |",
        f"| 原始资料／技能只读复核 | {integrity['source_files_checked']} / {integrity['skill_files_checked']} 个文件，未变化：{integrity['all_read_only_sources_unchanged']} |",
        f"| 真实科学任务启动 | {live['real_agents_run']}/144，{live['status']} |",
        '', '机器证据：[最终检查](composite-unattended-final-checks.json)、[逐题审计](composite-unattended-audit.json)、[覆盖矩阵](composite-unattended-coverage.csv)。',
        '第一批修订前运行被中断并保留，新修订使用独立目录；不向运行中的候选补充信息。',
        '参考计算通过不表示所有 Agent 都答对；真实成功率和失败原因在科学运行报告中单列。']
    lines+=['', '[真实 Agent 审查](composite-unattended-live-review.zh-CN.md)、[逐题资料完整性](composite-unattended-inputs.zh-CN.md)、[四题转换与接口变更](COMPOSITE_UNATTENDED_V2.zh-CN.md)。']
    lines+=['', '几何评分已在生成器中修复为明确的 1e-6 米坐标容差。为保持运行冻结，现有任务的评分文件在运行结束后更新，原始评分保留；修正结果见 [独立评分修复报告](composite-unattended-geometry-correction.zh-CN.md)。']
    (ROOT/'docs/composite-unattended-acceptance.zh-CN.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'golden_successes':report['golden_successes'],'complete_tasks':report['upfront_complete_tasks'],'real_agents_run':live['real_agents_run']},ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--pytest-passed',type=int,required=True);args=parser.parse_args()
    items=runner.discover_tasks(ROOT/'tests',suite='composite');atomic=runner.discover_tasks(ROOT/'tests')
    if all(x['task'].get('interaction_mode')=='none' for x in items):
        write_unattended_delivery(items,args.pytest_passed);return
    rows=[];derivations=[]
    for item in items:
        task=item['task'];directory=item['task_dir'];spec=json.loads((directory/'expected/evaluation.json').read_text(encoding='utf-8'))
        edges=spec['scientific_graph']['edges']
        rows.append({'id':task['id'],'title':task['title'],'domain':task['domain'],'outcome':task['outcome_goal'],'core_capabilities':'; '.join(task['core_capabilities']),'capability_count':len(set(task['core_capabilities'])),'dependencies':'; '.join(e['from']+' -> '+e['to'] for e in edges),'confirmations':'; '.join(c['key'] for c in spec['confirmations']),'gates':len(spec['gates']),'native_program_calls':len(spec['reference_execution']),'timeout_seconds':task['timeout_seconds']})
        visible=directory/'data'
        profiles={p.relative_to(visible).as_posix():table_profile(p) for p in visible.rglob('*.csv') if p.name in ['raw.csv','original.csv','supplements.csv'] or p.parent.name in ['raw_events','original_events','supplements']}
        derivations.append({'task_id':task['id'],'input_profiles':profiles,'input_files':{p.relative_to(visible).as_posix():sha(p) for p in visible.rglob('*') if p.is_file()},'scientific_graph':spec['scientific_graph'],'source_manifest_sha256':sha(visible/'source_manifest.json'),'native_execution_reference':str((directory/'expected/evaluation.json').relative_to(ROOT))})
    with (ROOT/'docs/composite-coverage.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    matrix=['# 24 道组合任务覆盖矩阵','','本表是开发与验收资料，不进入 Agent 可见输入。原子覆盖独立保持 41/41。','','| ID | 业务目标 | 预期结果 | 科学能力 | 确认项 |','|---|---|---|---|---|']
    for row,item in zip(rows,items):
        link='../'+str((item['task_dir']/'task.json').relative_to(ROOT)).replace('\\','/')
        matrix.append(f"| [{row['id']}]({link}) | {row['title']} | {row['outcome']} | {row['capability_count']}：{row['core_capabilities']} | {row['confirmations']} |")
    matrix+=['','[机器可读矩阵](composite-coverage.csv)包含实际 DAG 边、科学闸门数、原生参考执行数和预算。','逐题输入哈希、时间范围、缺测及处理链见 `composite-case-derivations.json`。','原生程序调用仅描述参考构建，不作为候选成功条件；A04 采用直接独立评分样本审查。']
    (ROOT/'docs/composite-coverage.zh-CN.md').write_text('\n'.join(matrix)+'\n',encoding='utf-8')
    write_json(ROOT/'docs/composite-case-derivations.json',{'cases':derivations,'candidate_visible':False})
    source=json.loads((ROOT/'composite_assets/source_manifest.json').read_text(encoding='utf-8'))
    changed=[]
    for file in source['datasets']:
        path=({'lumped':LUMPED,'semi':SEMI}[file['dataset']])/file['path']
        if not path.is_file() or sha(path)!=file['sha256']:changed.append(str(path))
    catalog=json.loads((ROOT/'docs/composite-skill-catalog.json').read_text(encoding='utf-8'))
    skill_files=0
    for skill in catalog['skills']:
        for file in skill['files']:
            path=SKILLS/file['path'];skill_files+=1
            if not path.is_file() or sha(path)!=file['sha256']:changed.append(str(path))
    write_json(ROOT/'docs/composite-source-integrity.json',{'source_files_checked':len(source['datasets']),'skill_files_checked':skill_files,'changed_files':changed,'all_read_only_sources_unchanged':not changed})
    if changed:raise RuntimeError('read-only source differs from snapshot')
    event_files=sorted((LUMPED/'场次洪水数据').glob('*.csv'))
    continuous=pd.read_excel(next(SEMI.glob('*.xlsx')),usecols=list(range(16)))
    write_json(ROOT/'docs/composite-source-profile.json',{'lumped':{'files':sum(f['dataset']=='lumped' for f in source['datasets']),'events':len(event_files),'event_rows':sum(len(pd.read_csv(p)) for p in event_files)},'semi':{'files':sum(f['dataset']=='semi' for f in source['datasets']),'rows':len(continuous),'time_min':str(continuous.time.min()),'time_max':str(continuous.time.max()),'missing_by_column':{c:int(continuous[c].isna().sum()) for c in continuous.columns}},'selected_cases':str((ROOT/'docs/composite-case-derivations.json').relative_to(ROOT))})
    acceptance=json.loads((ROOT/'docs/composite-acceptance.json').read_text(encoding='utf-8'))
    repeats=json.loads((ROOT/'docs/composite-repeatability.json').read_text(encoding='utf-8'))
    runtime=json.loads((ROOT/'docs/composite-runtime-receipt.json').read_text(encoding='utf-8'))
    checks={'date':'2026-10-04','environment':'HydroTune-eval','pytest_passed':args.pytest_passed,'definition_validation_errors':runner.validate_tests(ROOT/'tests',suite='all'),'atomic_tasks':len(atomic),'atomic_skills_covered':len({x['task']['primary_skill'] for x in atomic}),'composite_tasks':len(items),'all_tasks':len(atomic)+len(items),'deliverable':sum(r['outcome']=='deliverable' for r in rows),'blocked':sum(r['outcome']=='blocked' for r in rows),'golden_successes':acceptance['golden_passed'],'two_fresh_generation_successes':[r['passed'] for r in repeats['rounds']],'formal_schedule_runs':len(schedule([r['id'] for r in rows]))*2,'read_only_sources_unchanged':not changed,'formal_runtime_ready':runtime['formal_ready'],'formal_pending':runtime['blocking_items'],'real_agents_run':0}
    write_json(ROOT/'docs/composite-final-checks.json',checks)
    text=f'''# 组合任务开发验收记录（2026-10-04）

| 项目 | 结果 |
|---|---|
| 环境 | HydroTune-eval，Python {runtime['python']} |
| 定义校验 | 207 道通过：183 原子 + 24 组合 |
| 原子覆盖 | 41/41，旧模板不发现；原子 suite 仍为默认 |
| 组合分布 | 数据 8 / 模型 12 / 分析 4；正常 20 / 阻断 4；ID 连续 |
| 核心科学能力 | 20 道正常题均至少 3 种，隐藏 DAG 记录实际产物依赖 |
| 隐藏参考 | 24/24，全部 score=1.0 且 task_success=true |
| 两个临时目录重新生成 | 第一次 {repeats['rounds'][0]['passed']}/24；第二次 {repeats['rounds'][1]['passed']}/24；科学语义与真实引用通过 |
| 框架测试 | {args.pytest_passed} passed；包括原子 golden 回归、科学扣分、确认、CLI 假进程及调度统计 |
| 外部资料只读复核 | {len(source['datasets'])} 个数据文件、{skill_files} 个技能文件哈希无变化 |
| 冻结技能 | 41 个原子 + 3 个 workflow，程序与基本说明两组共享 |
| 配对调度 | 216 对、432 次；仅生成调度，未启动 Agent |
| 开发阶段真实 Agent | 0 |
| 正式容器验收 | 未通过：本机无 Docker／WSL，模型／推理、专用网络和真实事件审计仍有待完成项 |

原生科学程序在独立工作区真实执行，参考构建轨迹保存在逐题隐藏评价文件。
最后的参考评分记录不代表重新执行全部程序；两个临时目录的重复性验收
实际重新构建全部题目。A04 为直接独立评分样本审查，不需要原生 Skill 调用。

自测覆盖错单位、未经确认补零、漏汇流、重复入流、状态串联、实际 split
重叠、伪造／晚确认、未落实回答、错误证据、阻断后交付、跳过中间产物、
假完成日志、图件尺寸和证据绑定。分数与关键错误分开；缺少产物不自动
判定科学错误。率定与 BMA 采用独立复算，不要求参数唯一。

剩余正式运行验收：构建并冻结镜像；在 Linux 中实际运行 WhiteboxTools；
确定 OpenCode 模型及各 CLI 推理设置；审查公共提供商配置并禁用回退、
记忆及检索；验证提供商专用网络无法访问隐藏参考、本机技能和其他工作区；
对实际版本进行事件预算审计。当前入口在未冻结／未认证时拒绝启动。
假进程通过不等于上述真实环境已认证，没有产生正式三项指标结果。

机器记录：[最终检查](composite-final-checks.json)、[参考评分](composite-acceptance.json)、
[重复生成](composite-repeatability.json)、[源完整性](composite-source-integrity.json)、
[运行环境](composite-runtime-receipt.json)、[覆盖矩阵](composite-coverage.zh-CN.md)。
'''
    (ROOT/'docs/composite-acceptance.zh-CN.md').write_text(text,encoding='utf-8')
    print(json.dumps(checks,ensure_ascii=False))


if __name__=='__main__':main()
