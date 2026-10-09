"""Three-arm task blocking, balanced order, resume and task-cluster summaries."""
from __future__ import annotations
import argparse
import csv
from itertools import permutations
import json
from pathlib import Path
import random

from harness.atomic_contracts import CONDITIONS, VERSION, digest, tree_digest
from harness import reporter, runner
from harness.filesystem import filesystem_path


def schedule(task_ids, clis, repetitions=1, seed=20261005):
    if repetitions < 1: raise ValueError('repetitions must be positive')
    orders = list(permutations(CONDITIONS)); records = []
    for cli in clis:
        for repetition in range(repetitions):
            ids = sorted(task_ids); random.Random(seed + repetition).shuffle(ids)
            for position, task_id in enumerate(ids):
                records.append({'cli': cli, 'task_id': task_id, 'repetition': repetition,
                                'conditions': list(orders[(position + repetition) % 6])})
    return records


def execute_block(root, block, execute):
    """At most one infrastructure retry, archiving the complete three-arm unit."""
    root=Path(filesystem_path(root))
    folder = root / block['cli'] / f"r{block['repetition']}" / block['task_id']
    checkpoint = folder / 'triple-attempt.json'
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else {'retries': 0}
    folder.mkdir(parents=True, exist_ok=True)
    while True:
        partial_infrastructure = False
        for condition in block['conditions']:
            output = folder / condition
            if (output / 'summary.json').is_file(): continue
            if output.exists():
                evidence = output / 'tasks' / block['task_id'] / 'execution.json'
                if evidence.is_file() and json.loads(evidence.read_text()).get('infrastructure_failure'):
                    partial_infrastructure = True
                    break
                raise ValueError('partial execution retained; cannot classify or rerun it automatically: ' + str(output))
            execute(condition, output)
        failures = []
        for condition in block['conditions']:
            evidence = folder / condition / 'tasks' / block['task_id'] / 'execution.json'
            if evidence.is_file() and json.loads(evidence.read_text()).get('infrastructure_failure'):
                failures.append(condition)
        if not failures and not partial_infrastructure: return
        if state['retries'] >= 1: return  # Preserve failures; never retry indefinitely.
        archive = folder / 'archived-attempt-0'
        archive.mkdir(exist_ok=False)
        for condition in block['conditions']:
            source = folder / condition
            if source.exists():
                source.resolve().relative_to(root.resolve())
                (archive/condition).resolve().relative_to(root.resolve())
                source.rename(archive / condition)
        state = {'retries': 1, 'reason': 'infrastructure_failure', 'failed_conditions': failures,
                 'archived_attempt': str(archive)}
        reporter.write_json(checkpoint, state)


def summarize(root: Path, blocks: list[dict], seed=20261005):
    root=Path(filesystem_path(root))
    import numpy as np
    records, complete = [], {}
    for block in blocks:
        arms = {}
        arm_metadata = {}
        for condition in block['conditions']:
            folder = root / block['cli'] / f"r{block['repetition']}" / block['task_id'] / condition
            path = folder / 'tasks' / block['task_id'] / 'result.json'
            if not path.is_file(): continue
            metadata = json.loads((folder / 'run_metadata.json').read_text(encoding='utf-8'))
            if metadata.get('experiment_version') != VERSION or metadata.get('condition') != condition:
                raise ValueError('legacy/wrong-condition result cannot enter this experiment')
            result = json.loads(path.read_text(encoding='utf-8'))
            execution = json.loads((path.parent / 'execution.json').read_text(encoding='utf-8'))
            infrastructure = bool(execution.get('infrastructure_failure'))
            record = {**{k: block[k] for k in ['cli', 'task_id', 'repetition']}, 'condition': condition,
                      'score': result['score'], 'attempted': result['attempted'],
                      'full_score': result['score'] >= 1 - 1e-12, 'timed_out': execution.get('timed_out', False),
                      'infrastructure_failure': infrastructure}
            records.append(record)
            if not infrastructure: arms[condition] = record
            arm_metadata[condition] = metadata
        if set(arms) == set(CONDITIONS): complete[(block['cli'], block['task_id'], block['repetition'])] = arms
        for left, right in [('no-skills', 'programs-only'), ('programs-only', 'with-skills')]:
            if left in arm_metadata and right in arm_metadata:
                reporter._assert_comparable(arm_metadata[left], arm_metadata[right])
    def group_summary(values, planned):
        eligible = [r for r in values if not r['infrastructure_failure']]
        n = len(eligible)
        return {'completed': len(values), 'eligible': n, 'planned': planned,
            'attempted': sum(r['attempted'] for r in eligible),
            'coverage': sum(r['attempted'] for r in eligible) / n if n else None,
            'mean_score': float(np.mean([r['score'] for r in eligible])) if n else None,
            'full_score_tasks': sum(r['full_score'] for r in eligible),
            'full_score_rate': sum(r['full_score'] for r in eligible) / n if n else None,
            'timeouts': sum(r['timed_out'] for r in values), 'infrastructure_failures': len(values) - n}
    groups, paired_groups, differences = {}, {}, {}
    for cli in sorted({b['cli'] for b in blocks}):
        groups[cli] = {}
        for condition in CONDITIONS:
            values = [r for r in records if r['cli'] == cli and r['condition'] == condition]
            groups[cli][condition] = group_summary(values, sum(b['cli'] == cli for b in blocks))
        paired = [(key, arms) for key, arms in complete.items() if key[0] == cli]
        paired_groups[cli] = {c: group_summary([arms[c] for _, arms in paired], len(paired)) for c in CONDITIONS}
        differences[cli] = {}
        for before, after in [('no-skills', 'programs-only'), ('programs-only', 'with-skills'), ('no-skills', 'with-skills')]:
            task_values = {}
            for key, arms in paired:
                task_values.setdefault(key[1], []).append([
                    arms[after]['score'] - arms[before]['score'],
                    int(arms[after]['full_score']) - int(arms[before]['full_score'])])
            values = np.array([np.mean(v, axis=0) for v in task_values.values()])
            interval = None
            if len(values) >= 2:
                rng = np.random.default_rng(seed)
                draws = values[rng.integers(0, len(values), size=(2000, len(values)))].mean(axis=1)
                interval = np.quantile(draws, [0.025, 0.975], axis=0).T.tolist()
            differences[cli][after + ' minus ' + before] = {'complete_triples': len(paired),
                'task_clusters': len(task_values), 'metrics': ['mean_score', 'full_score_rate'],
                'difference': values.mean(axis=0).tolist() if len(values) else None,
                'estimand': 'Equal weight per task; average complete repetitions within each task.',
                'task_cluster_bootstrap_95pct': interval}
    archives = list(root.glob('*/r*/*/archived-attempt-*'))
    archived_infrastructure = sum(bool(json.loads(p.read_text()).get('infrastructure_failure'))
        for archive in archives for p in archive.glob('*/tasks/*/execution.json'))
    summary = {'experiment_version': VERSION, 'groups': groups, 'complete_triple_groups': paired_groups, 'differences': differences,
               'archived_triple_attempts': len(archives), 'archived_infrastructure_runs': archived_infrastructure,
               'attempt_scope': 'Latest whole-triple attempt; archived original attempts are retained separately.',
               'planned_runs': len(blocks) * 3, 'completed_runs': len(records),
               'complete_triples': len(complete), 'incomplete_runs': len(blocks) * 3 - len(records)}
    reporter.write_json(root / 'three-arm-summary.json', summary)
    with (root / 'three-arm-results.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['cli', 'task_id', 'repetition', 'condition', 'score', 'attempted', 'full_score', 'timed_out', 'infrastructure_failure'])
        writer.writeheader(); writer.writerows(records)
    lines = ['# 三组原子实验截止快照', '', f"计划 {summary['planned_runs']} 次，完成 {len(records)} 次，完整三组配对 {len(complete)} 个。", '',
             '未启动任务不计为科学失败；满分率指通过原有全部评分，不等同于独立科学错误率。', '',
             '统计详情见 three-arm-summary.json；逐次记录见 three-arm-results.csv。']
    def table(name, data):
        lines.extend(['', '## ' + name, '', '| CLI | 条件 | 完成/计划 | 有效 | 均分 | 满分数 | 超时 | 基础设施失败 |',
                      '|---|---|---:|---:|---:|---:|---:|---:|'])
        for cli, conditions in data.items():
            for c, v in conditions.items():
                mean = f"{v['mean_score']:.4f}" if v['mean_score'] is not None else '待运行'
                lines.append(f"| {cli} | {c} | {v['completed']}/{v['planned']} | {v['eligible']} | {mean} | {v['full_score_tasks']} | {v['timeouts']} | {v['infrastructure_failures']} |")
    table('全部已完成运行（当前尝试）', groups)
    table('仅完整三组配对', paired_groups)
    lines.extend(['', f'归档三组尝试 {len(archives)} 个，其中基础设施失败运行 {archived_infrastructure} 次；不与当前尝试重复计入主指标。'])
    (root / 'three-arm-summary.zh-CN.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--clis', default='codex,opencode,qwen,codebuddy')
    p.add_argument('--output', type=Path, required=True); p.add_argument('--lock', type=Path)
    p.add_argument('--repetitions', type=int, default=1); p.add_argument('--seed', type=int, default=20261005)
    p.add_argument('--test-id'); p.add_argument('--resume', action='store_true'); p.add_argument('--execute', action='store_true')
    args = p.parse_args(); args.output=Path(filesystem_path(args.output)); clis = args.clis.split(',')
    if len(set(clis)) != len(clis) or any(c not in {'codex', 'opencode', 'qwen', 'codebuddy'} for c in clis): raise ValueError('invalid CLI list')
    tasks = runner.discover_tasks(test_id=args.test_id)
    blocks = schedule([x['task']['id'] for x in tasks], clis, args.repetitions, args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {'experiment_version': VERSION, 'seed': args.seed, 'blocks': blocks}
    existing = args.output / 'schedule.json'
    if existing.exists():
        if not args.resume: raise ValueError('existing experiment requires --resume')
        if json.loads(existing.read_text()) != manifest: raise ValueError('schedule changed on resume')
    else: reporter.write_json(existing, manifest)
    if args.execute:
        if not args.lock: raise ValueError('--execute requires a certified --lock')
        from harness.atomic_runtime import preflight, load_lock
        for cli in clis:
            ready = preflight(args.lock, cli)
            if not ready['ready']: raise ValueError(cli + ': ' + str(ready['issues']))
        binding = {'lock_sha256': digest(args.lock), 'tasks': {i['task']['id']: {
            'definition_sha256': digest(i['task_path']), 'inputs_sha256': tree_digest(i['task_dir'] / 'data')}
            for i in tasks}}
        bound_path = args.output / 'execution-binding.json'
        if bound_path.exists() and json.loads(bound_path.read_text()) != binding:
            raise ValueError('lock, task definition or input data changed on resume')
        reporter.write_json(bound_path, binding)
        for block in blocks:
            lock = load_lock(args.lock, block['cli'])
            def execute(condition, output):
                runner.run_benchmark(test_id=block['task_id'], runtime='isolated', atomic_cli=block['cli'], runtime_lock=args.lock,
                    condition=condition, skills_path=lock['skills_dir'] if condition == 'with-skills' else None,
                    programs_path=lock['public_programs_dir'] if condition != 'no-skills' else None, output=output)
                summarize(args.output, blocks, args.seed)
            execute_block(args.output, block, execute)
            summarize(args.output, blocks, args.seed)
    result = summarize(args.output, blocks, args.seed)
    print(json.dumps({'planned_runs': result['planned_runs'], 'completed_runs': result['completed_runs']}))


if __name__ == '__main__': main()
