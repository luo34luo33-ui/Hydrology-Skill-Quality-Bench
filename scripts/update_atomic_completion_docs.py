"""Refresh task-local grading contracts and the completion coverage documents."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness import runner
from atomic_tasks import GROUPS, REPO
from atomic_fixture_support import read, write
from atomic_oracles import make_grading

def main():
    found=runner.discover_tasks(REPO/'tests');new=[]
    for item in found:
        task,folder=item['task'],item['task_dir'];group=task['id'].rsplit('-',1)[0]
        if group not in GROUPS: continue
        recipe=read(folder/'expected/recipe.json')
        required,grading=make_grading(group,folder/'expected/golden_workspace',recipe['outputs'],folder)
        task['required_outputs']=required;task['grading']=grading;write(folder/'task.json',task);new.append(item)
        factory='_bma_task_factory' if group=='hydroanalysis-bma' else ('_atlas_task_factory' if group.startswith('hydrovisual') else '_report_task_factory')
        (folder/'generate_data.py').write_text(f'from pathlib import Path\nimport sys\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\nfrom {factory} import generate\nif __name__ == "__main__":\n    generate(Path(__file__).resolve().parent.name)\n',encoding='utf-8')
    rows=['| Task | 场景 | 原生状态 | 退出码序列 |','|---|---|---|---|']
    for item in new:
        task,folder=item['task'],item['task_dir'];recipe=read(folder/'expected/recipe.json')
        statuses=[read(folder/'expected/golden_workspace'/out/'result.json')['status'] for out in recipe['outputs']]
        rows.append(f"| `{task['id']}` | {task['title']} | {' → '.join(statuses)} | {','.join(str(s['code']) for s in recipe['steps'])} |")
    header='# 原子任务补齐测试矩阵\n\n新增43题，固定上游输入；只调用确定性技能脚本，不运行Agent。每题结构、文件及科学契约由 task.json 定义。普通拒绝保留原生失败结果和允许的诊断，禁止正常成果；科学QC失败图册只发布失败看板。\n\n'
    visual=[row for row in rows[2:] if 'hydroanalysis-bma-' not in row]
    path=REPO/'tests/visualization-reporting/TESTS.zh-CN.md';path.write_text(header+'\n'.join(rows[:2]+visual)+'\n',encoding='utf-8')
    data_path=REPO/'tests/results-analysis/TESTS.zh-CN.md'
    text=data_path.read_text(encoding='utf-8');marker='\n## BMA 原子任务补齐\n'
    text=text.split(marker)[0]+marker+'\n'+ '\n'.join(rows[:2]+[row for row in rows[2:] if 'hydroanalysis-bma-' in row])+'\n'
    data_path.write_text(text,encoding='utf-8')
    catalog=read(REPO/'docs/atomic-skill-catalog.json')
    coverage=['# 原子技能覆盖矩阵','', '以2026-10-04源目录文件哈希快照为准；排除workflows。183道任务覆盖41个原子技能。','', '| 原子技能 | task数量 | task ID |','|---|---:|---|']
    for entry in catalog['atomic_skills']:
        ids=sorted(i['task']['id'] for i in found if i['task']['primary_skill']==entry['skill'])
        coverage.append(f"| `{entry['skill']}` | {len(ids)} | {', '.join(ids)} |")
    coverage+=['','旧综合题迁移到 `examples/tasks/hydroanalysis-legacy-template/task.example.json`，不参与发现和原子覆盖统计。','', '新任务的可见输入只包含预置科学成果和报告迁移标记；hidden expected、语义判定真值和执行recipe均不进入Agent工作区。']
    (REPO/'docs/atomic-coverage.zh-CN.md').write_text('\n'.join(coverage)+'\n',encoding='utf-8')
    for name in ('README.md','README.zh-CN.md'):
        path=REPO/name;text=path.read_text(encoding='utf-8')
        text='\n'.join(line for line in text.splitlines() if not line.startswith('- `hydroanalysis-001`'))+'\n'
        marker='\n## Atomic skill completion (2026-10-04)\n'
        text=text.split(marker)[0].split('\n## 原子技能补齐（2026-10-04）\n')[0]
        if name=='README.zh-CN.md':
            text+='\n## 原子技能补齐（2026-10-04）\n\n183道可执行任务覆盖全部41个原子技能。本次新增43题，覆盖BMA和8个图册／报告技能；旧综合诊断题已移为非运行模板。详见[覆盖矩阵](docs/atomic-coverage.zh-CN.md)与[验收记录](docs/atomic-completion-acceptance.zh-CN.md)。开发阶段未运行实际Agent批次。\n\n新增 `figure_contract_check` 和 `report_contract_check`，均使用任务本地隐藏 `reference`。图件检查解码尺寸、元数据及SVG科学图层；报告检查原始证据、时段表格、受控结论和逐段审查绑定。评分器不执行候选代码，不使用模型裁判。使用 `HydroTune-eval` 运行 `scripts/verify_bma_tasks.py`、`scripts/verify_atlas_tasks.py`、`scripts/verify_report_tasks.py` 完成确定性原生脚本验收。\n'
        else:
            text+=marker+'\n183 runnable tasks cover all 41 atomic skills. This completion adds 43 tasks for BMA and eight visualization/reporting skills; the historical composite diagnostic task is now a non-running template. See [coverage matrix](docs/atomic-coverage.zh-CN.md) and [acceptance record](docs/atomic-completion-acceptance.zh-CN.md). Development does not run actual Agent batches.\n\nNew graders: `figure_contract_check` and `report_contract_check`, each with a task-local hidden `reference`. Figures are checked by decoded dimensions, metadata and scientific SVG geometry; reports by source evidence, scoped tables, controlled conclusions and paragraph review binding. Neither grader executes candidate code or uses an LLM judge. Native verification: `scripts/verify_bma_tasks.py`, `scripts/verify_atlas_tasks.py`, `scripts/verify_report_tasks.py`, using `HydroTune-eval`.\n'
        path.write_text(text,encoding='utf-8')
    print(len(found),'tasks;',len(new),'new grading contracts refreshed')

if __name__=='__main__': main()
