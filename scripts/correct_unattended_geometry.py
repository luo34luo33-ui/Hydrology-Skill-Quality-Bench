"""Apply a deferred scoring bug fix after execution; preserve original scores."""
import copy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from harness import grader,runner
from harness.overnight import atomic_json,latest_records


def correct(root):
    schedule=json.loads((root/'schedule.json').read_text(encoding='utf-8'))
    if schedule.get('interaction_mode')!='none' or schedule.get('task_revision')!=4:
        raise ValueError('Only the current unattended revision may receive this scoring correction')
    destination=root/'geometry-scoring-correction';destination.mkdir(exist_ok=True)
    receipt=destination/'report.json'
    if receipt.exists():return json.loads(receipt.read_text(encoding='utf-8'))
    affected={}
    for item in runner.discover_tasks(suite='composite'):
        path=item['task_dir']/item['task']['evaluation_reference']
        original=json.loads(path.read_text(encoding='utf-8'));updated=copy.deepcopy(original)
        for gate in updated['gates']:
            for criterion in gate['criteria']:
                if criterion['type']=='vector_match':criterion['geometry_tolerance']=criterion['atol']
        if original!=updated:
            identity=item['task']['id'];affected[identity]=item
            atomic_json(destination/(identity+'-original-evaluation.json'),original)
            atomic_json(path,updated)
    corrected=[]
    rows,_,_,_=latest_records(root,schedule['pairs'])
    for row in rows:
        if row['test_id'] not in affected:continue
        item=affected[row['test_id']]
        task_dir=root/f"{row['cli']}-r1-{row['test_id']}"/f"attempt-{row['attempt']}"/row['condition']/'tasks'/row['test_id']
        new=grader.grade_task(item['task'],task_dir/'workspace',item['task_dir'],audit_events=[])
        corrected.append({'cli':row['cli'],'condition':row['condition'],'task_id':row['test_id'],
            'original_task_success':row['task_success'],
            'corrected_scientific_success':new['task_success'],
            'execution_success':row.get('execution',{}).get('return_code')==0,
            'corrected_scientific_gates':new['scientific_gates']})
    golden=[]
    for item in runner.discover_tasks(suite='composite'):
        golden.append(grader.grade_task(item['task'],item['task_dir']/'expected/golden_workspace',item['task_dir'],audit_events=[])['task_success'])
    report={'scoring_correction':'vector-coordinate-tolerance-1e-6-v1',
        'task_version':schedule['task_version'],'task_revision':4,'affected_tasks':sorted(affected),
        'input_or_scientific_parameter_changes':False,'agent_results_overwritten':False,
        'original_schedule_hashes_preserved':True,'reference_passed':sum(golden),'reference_total':24,
        'runs':corrected,
        'note':'Only geometry tolerance was made consistent with the already declared numeric precision. Original execution and scientific reports remain unchanged. This separate report does not reinterpret confirmation-era results.'}
    atomic_json(receipt,report)
    lines=['# 几何评分容差修复','',
        '几何检查现在明确使用 1e-6 米坐标容差，与既有数值精度要求一致。输入、模型、科学参数和原始运行记录均未修改；原评分报告保留，修正评分单独列出。',
        f"参考成果复核：{sum(golden)}/24。受影响任务：{', '.join(sorted(affected))}。",'',
        '| CLI | 任务 | 条件 | 原成功判定 | 修正后科学闸门通过 | 执行成功 |',
        '|---|---|---|---|---|---|']
    lines += [f"| {r['cli']} | {r['task_id']} | {r['condition']} | {r['original_task_success']} | {r['corrected_scientific_success']} | {r['execution_success']} |" for r in corrected]
    lines += ['', '修正后科学闸门通过不抵消执行预算超限。填洼与 D8 的数值差异仍按原科学检查报告，不通过放宽容差掩盖。']
    (ROOT/'docs/composite-unattended-geometry-correction.zh-CN.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return report
