"""Offline-testable paired dispatcher, recovery and honest cutoff reporting."""
import csv
import datetime as dt
import json
import os
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from harness.filesystem import filesystem_path


def parse_deadline(value):
    if not value:return None
    result=dt.datetime.fromisoformat(value)
    if result.tzinfo is None:raise ValueError('Deadline requires timezone offset')
    return result


def atomic_json(path, value):
    path=Path(filesystem_path(path));path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.tmp-'+str(threading.get_ident()))
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.replace(temp,path)


@contextmanager
def run_guard(root):
    """OS lock is automatically released on crash; PID files alone are insufficient."""
    path=Path(filesystem_path(root))/'run.lock';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        if f.tell()==0:f.write(b'0');f.flush()
        f.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:raise RuntimeError('Another dispatcher owns this output directory') from exc
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)


@contextmanager
def keep_awake():
    if os.name=='nt':
        import ctypes
        if not ctypes.windll.kernel32.SetThreadExecutionState(0x80000001):
            raise RuntimeError('Cannot prevent automatic sleep')
    try:yield
    finally:
        if os.name=='nt':ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


def failure_row(pair, condition, attempt, error):
    # Exception details may contain credentials; only exception class is persisted.
    row={'test_id':pair['task_id'],'cli':pair['cli'],'condition':condition,
        'repetition':pair['repetition'],'attempt':attempt,'task_kind':'composite',
        'eligible':False,'attempted':False,'score':0,'task_success':False,
        'critical_errors':[],'confirmation_results':[],'assessability':'unassessable',
        'domain':'startup-failure','primary_skill':'workflow','difficulty':'advanced',
        'outcome_goal':'infrastructure','startup_error_type':type(error).__name__,
        'resource_usage':{'wall_seconds':None,'agent_seconds':None,
            'tokens':{'measurement':'unavailable','input_tokens':None,'output_tokens':None,'total_tokens':None}}}
    if pair.get('interaction_mode')=='none':
        row.pop('confirmation_results');row.update(interaction_mode='none',task_version=pair['task_version'],task_revision=pair.get('task_revision',1),provided_setting_results=[])
    return row


def latest_records(root, pairs):
    selected=[];all_rows=[];complete=0;pending=[]
    for pair in pairs:
        base=Path(filesystem_path(root))/pair['pair_id']
        attempts=sorted((p for p in base.glob('attempt-*') if p.is_dir()),key=lambda p:int(p.name.split('-')[-1]))
        rows=[]
        for directory in attempts:
            current=[]
            for condition in pair['conditions']:
                path=directory/condition/'experiment_result.json'
                if path.exists():current.append(json.loads(path.read_text(encoding='utf-8')))
            all_rows.extend(current)
            rows=current
        selected.extend(rows)
        if len(rows)==2 and all(r.get('eligible',True) for r in rows):complete+=1
        if len(rows)<2:pending.append(pair['pair_id'])
    return selected,all_rows,complete,pending


def write_reports(root,pairs):
    from harness.experiment import summarize
    from harness import reporter
    root=Path(filesystem_path(root));selected,all_rows,complete,pending=latest_records(root,pairs)
    report=summarize(selected)
    from harness.resource_usage import resource_fields, resource_summary
    report['all_attempt_resource_usage']=resource_summary(all_rows)
    report.update({'planned_runs':len(pairs)*2,'recorded_attempt_runs':len(all_rows),
        'completed_pairs':complete,'pending_pairs':pending,'completed_runs':len(selected),
        'unrecorded_planned_runs':len(pairs)*2-len(selected),
        'excluded_superseded_attempt_runs':len(all_rows)-len(selected),
        'single_round':all(p['repetition']==1 for p in pairs),
        'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'comparison_scope':'within CLI/model only; completed eligible pairs for paired differences'})
    atomic_json(root/'scientific_report.json',report)
    unattended=all(p.get('interaction_mode')=='none' for p in pairs)
    result_field='provided_setting_results' if unattended else 'confirmation_results'
    passed_field='provided_setting_passed' if unattended else 'confirmation_passed'
    total_field='provided_setting_total' if unattended else 'confirmation_total'
    fields=['cli','condition','test_id','task_version','interaction_mode','repetition','attempt','eligible','task_success',
        'critical_error',passed_field,total_field,'assessability','domain','outcome_goal',
        'wall_seconds','agent_seconds','input_tokens','output_tokens','total_tokens','token_measurement']
    temp=root/'scientific_results.csv.tmp'
    with temp.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in selected:
            writer.writerow({**{k:row.get(k) for k in fields if k in row},
                'critical_error':bool(row.get('critical_errors')),
                **resource_fields(row),
                passed_field:sum(c['passed'] for c in row.get(result_field,[])),
                total_field:len(row.get(result_field,[]))})
    csv_path=root/'scientific_results.csv'
    try:os.replace(temp,csv_path)
    except PermissionError:
        # Excel and desktop previews may keep the old CSV open on Windows.
        csv_path=root/'scientific_results.with-usage.csv'
        os.replace(temp,csv_path)
    report['scientific_results_csv']=csv_path.name
    atomic_json(root/'scientific_report.json',report)
    lines=['# 固定 CLI／模型配置下的一轮配对技能消融实验',
        f'计划 {len(pairs)*2} 次；当前完成记录 {len(selected)} 次；完成有效配对 {complete}/{len(pairs)}。',
        '未执行任务不计为科学失败；基础设施失败单列。不同模型的CLI不作能力排名。',
        '', '| CLI／条件 | 有效运行 | 成功任务 | 关键错误任务 | '+('已提供设定正确使用' if unattended else '必要确认落实')+' |',
        '|---|---:|---:|---:|---:|']
    for key,group in report['groups'].items():
        used=group['correctly_used_setting_items'] if unattended else group['confirmed_and_implemented_items']
        total=group['provided_setting_items'] if unattended else group['necessary_information_items']
        lines.append(f"| {key} | {group['task_runs']} | {group['successful_task_runs']} | {group['critical_error_task_runs']} | {used}/{total} |")
    lines += ['',f"基础设施失败：{report['startup_failures']}；未记录计划运行：{report['unrecorded_planned_runs']}。",
        'JSON 中提供按领域、正常／阻断题分组指标，以及完整有效配对的任务聚类区间。',
        '只有一轮时不报告重复波动。未完成全部计划时，本报告是截止快照。']
    lines += ['', '| CLI／条件 | 平均总用时（秒） | 平均 Agent 用时（秒） | 已记录 token 合计 | token 可统计运行数 |',
        '|---|---:|---:|---:|---:|']
    for key,group in report['groups'].items():
        usage=group['resource_usage']
        def display(value):return '不可恢复' if value is None else f'{value:.2f}'
        lines.append(f"| {key} | {display(usage['wall_seconds']['mean'])} | {display(usage['agent_seconds']['mean'])} | {display(usage['total_tokens']['sum'])} | {usage['total_tokens']['observed_runs']} |")
    lines += ['', 'token 来源在 CSV 的 token_measurement 中标明：reported／reported_cli 为上游或 CLI 报告值，estimated 为字符启发式估算，mixed 为混合，unavailable 为日志不足。',
        '输入累计包含重复上下文与缓存 token；reasoning 计入报告的 output，不重复相加。估算不包含未输出的隐式推理，不作为账单。重试总开销见 JSON 的 all_attempt_resource_usage；未知值不按零计算。']
    lines += ['',f'[含用时与 token 的逐次结果 CSV]({csv_path.name})']
    temp=root/'RESULTS.zh-CN.md.tmp';temp.write_text('\n'.join(lines)+'\n',encoding='utf-8');os.replace(temp,root/'RESULTS.zh-CN.md')
    return report


def run_schedule(root,pairs,execute,workers=3,resume=False,deadline=None,pair_id=None,attempt=1,lock_hash=None,now=None):
    if not 1<=workers<=3:raise ValueError('Workers must be 1..3')
    root=Path(filesystem_path(root));root.mkdir(parents=True,exist_ok=True)
    now=now or (lambda:dt.datetime.now(dt.timezone.utc))
    sync=threading.RLock();stop=threading.Event()
    state_path=root/'dispatcher.json'
    existing=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else None
    if existing and not resume:raise FileExistsError('Existing dispatcher state; use --resume')
    if existing and existing.get('runtime_lock_sha256')!=lock_hash:raise ValueError('Frozen runtime changed; resume refused')
    states={p['pair_id']:{'status':'pending','cli':p['cli']} for p in pairs}
    state={'pid':os.getpid(),'runtime_lock_sha256':lock_hash,'deadline':deadline.isoformat() if deadline else None,'pairs':states}
    def update(pair=None,status=None,**extra):
        with sync:
            if pair:states[pair['pair_id']].update(status=status,**extra)
            state['updated_at']=now().isoformat();atomic_json(state_path,state)
            atomic_json(root/'progress.json',{
                'updated_at':state['updated_at'],'pid':os.getpid(),
                'completed_pairs':sum(x['status']=='completed' for x in states.values()),
                'running_pairs':sum(x['status']=='running' for x in states.values()),
                'pending_pairs':sum(x['status']=='pending' for x in states.values()),
                'pairs':states})
    def refresh():
        while not stop.wait(60):
            with sync:update();write_reports(root,pairs)
    def lane(cli):
        for pair in [p for p in pairs if p['cli']==cli and (not pair_id or p['pair_id']==pair_id)]:
            base=root/pair['pair_id'];dirs=list(base.glob('attempt-*'))
            current=max([attempt-1]+[int(p.name.split('-')[-1]) for p in dirs])
            if current>=attempt:
                rows=[json.loads(p.read_text(encoding='utf-8')) for p in (base/f'attempt-{current}').glob('*/experiment_result.json')]
                if len(rows)==2 and all(r.get('eligible',True) for r in rows):update(pair,'completed',attempt=current);continue
                if current>=2:update(pair,'infrastructure_failed',attempt=current);return
            for index in range(max(attempt,current+1),3):
                if deadline and now()>=deadline-dt.timedelta(hours=1):update(pair,'deferred_deadline');break
                update(pair,'running',attempt=index)
                rows=[]
                for condition in pair['conditions']:
                    out=base/f'attempt-{index}'/condition;out.mkdir(parents=True,exist_ok=False)
                    try:row=execute(pair,condition,index,out)
                    except Exception as error:row=failure_row(pair,condition,index,error)
                    row.update(cli=cli,condition=condition,repetition=pair['repetition'],attempt=index)
                    atomic_json(out/'experiment_result.json',row);rows.append(row)
                    with sync:write_reports(root,pairs)
                if all(r.get('eligible',True) for r in rows):update(pair,'completed',attempt=index);break
                if index==2:
                    update(pair,'infrastructure_failed',attempt=index)
                    # Two whole-pair startup failures pause this CLI, others continue.
                    return
    with run_guard(root),keep_awake():
        update();thread=threading.Thread(target=refresh,daemon=True);thread.start()
        try:
            with ThreadPoolExecutor(max_workers=min(workers,len({p['cli'] for p in pairs}))) as pool:
                futures=[pool.submit(lane,cli) for cli in dict.fromkeys(p['cli'] for p in pairs)]
                for future in futures:future.result()
        finally:
            stop.set();thread.join(timeout=5)
            with sync:update();write_reports(root,pairs)
    return state
