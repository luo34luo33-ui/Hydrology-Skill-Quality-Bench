"""Aggregation, serialization, and paired run comparison."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable


def _stats(results: list[dict[str, Any]]) -> dict[str, Any]:
    attempted = [item for item in results if item.get("attempted", False)]
    scores = [float(item.get("score", 0.0)) for item in results]
    attempted_scores = [float(item.get("score", 0.0)) for item in attempted]
    total = len(results)
    stats = {
        "tests_total": total,
        "tests_attempted": len(attempted),
        "coverage": len(attempted) / total if total else 0.0,
        "score_attempted": mean(attempted_scores) if attempted_scores else 0.0,
        "score_overall": mean(scores) if scores else 0.0,
    }
    composite=[r for r in results if r.get('task_kind')=='composite' and r.get('eligible',True)]
    modes={r.get('interaction_mode','confirmation') for r in results if r.get('task_kind')=='composite'}
    if len(modes)>1:raise ValueError('Cannot aggregate legacy confirmation and unattended results together')
    revisions={r.get('task_revision',1) for r in results if r.get('task_kind')=='composite' and r.get('interaction_mode')=='none'}
    if len(revisions)>1:raise ValueError('Cannot aggregate different unattended task revisions')
    if any(r.get("task_kind")=="composite" for r in results):
        from harness.resource_usage import resource_summary
        stats['resource_usage']=resource_summary(results)
        n=len(composite);success=sum(bool(r.get('task_success')) for r in composite);wrong=sum(bool(r.get('critical_errors')) for r in composite)
        confirmations=[c for r in composite for c in r.get('confirmation_results',[])];confirmed=sum(bool(c['passed']) for c in confirmations)
        stats.update({'task_runs':n,'successful_task_runs':success,'task_success_rate':success/n if n else None,'critical_error_task_runs':wrong,'critical_scientific_error_rate':wrong/n if n else None,'scientifically_unassessable_task_runs':sum(r.get('assessability')!='assessed' for r in composite),'necessary_information_items':len(confirmations),'confirmed_and_implemented_items':confirmed,'necessary_information_confirmation_rate':confirmed/len(confirmations) if confirmations else None})
        stats['scientifically_unassessable_rate']=stats['scientifically_unassessable_task_runs']/n if n else None
        if modes=={'none'}:
            for key in ['necessary_information_items','confirmed_and_implemented_items','necessary_information_confirmation_rate']:stats.pop(key,None)
            settings=[s for r in composite for s in r.get('provided_setting_results',[])]
            implemented=sum(bool(s['passed']) for s in settings)
            stats.update(interaction_mode='none',task_version='composite-unattended-v2',task_revision=next(iter(revisions)) if revisions else None,provided_setting_items=len(settings),correctly_used_setting_items=implemented,provided_setting_usage_rate=implemented/len(settings) if settings else None)
    return stats


def _group(results: list[dict[str, Any]], key: Callable[[dict[str, Any]], str]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        grouped[key(result)].append(result)
    return {name: _stats(items) for name, items in sorted(grouped.items())}


def aggregate_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _stats(results)
    summary.update(
        {
            "tasks": {
                result["test_id"]: {
                    "score": float(result.get("score", 0.0)),
                    "attempted": bool(result.get("attempted", False)),
                    "domain": result.get("domain"),
                    "difficulty": result.get("difficulty"),
                    "primary_skill": result.get("primary_skill"),
                    **({k:result[k] for k in ['task_success','critical_errors','confirmation_results','provided_setting_results','task_version','task_revision','interaction_mode','assessability','resource_usage'] if k in result} if result.get('task_kind')=='composite' else {}),
                }
                for result in sorted(results, key=lambda item: item["test_id"])
            },
            "skills": _group(results, lambda item: item["primary_skill"]),
            "domains": _group(results, lambda item: item["domain"]),
            "difficulties": _group(results, lambda item: item["difficulty"]),
            "outcomes": _group(results, lambda item: item.get('outcome_goal','atomic')),
        }
    )
    return summary


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    from harness.filesystem import filesystem_path
    destination = Path(filesystem_path(path))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return destination


def load_run(run_dir: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    from harness.filesystem import filesystem_path
    root = Path(filesystem_path(run_dir))
    if root.is_file():
        root = root.parent
    metadata = json.loads((root / "run_metadata.json").read_text(encoding="utf-8"))
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    return metadata, summary


def _assert_comparable(left: dict[str, Any], right: dict[str, Any]) -> None:
    keys = ("model", "effort", "agent_cmd", "task_hashes", "timeouts", "environment", "suite", "runtime_lock_sha256", "runtime_controls", "experiment_version", "public_contract_hashes", "runtime", "atomic_runtime_controls")
    differences = [key for key in keys if left.get(key) != right.get(key)]
    if differences:
        raise ValueError("runs are not comparable; metadata differs: " + ", ".join(differences))
    if left.get('programs_available') and right.get('programs_available') and left.get('public_programs_sha256') != right.get('public_programs_sha256'):
        raise ValueError('public program bundles differ')
    if left.get('experiment_version') in {'atomic-three-arm-v1', 'atomic-three-arm-v2'}:
        for metadata in (left, right):
            c = metadata.get('condition')
            if c not in {'no-skills', 'programs-only', 'with-skills'} or bool(metadata.get('programs_available')) != (c != 'no-skills'):
                raise ValueError('invalid three-arm provenance')


def _delta(a: float, b: float) -> dict[str, float]:
    return {"run_a": float(a), "run_b": float(b), "absolute_uplift": float(b) - float(a)}


def _group_deltas(left: dict[str, Any], right: dict[str, Any], group: str) -> dict[str, Any]:
    left_group = left.get(group, {})
    right_group = right.get(group, {})
    if set(left_group) != set(right_group):
        raise ValueError(f"runs contain different {group} groups")
    return {
        name: {
            "score_overall": _delta(left_group[name]["score_overall"], right_group[name]["score_overall"]),
            "coverage": _delta(left_group[name]["coverage"], right_group[name]["coverage"]),
        }
        for name in sorted(left_group)
    }


def compare_runs(run_a: str | Path, run_b: str | Path) -> dict[str, Any]:
    metadata_a, summary_a = load_run(run_a)
    metadata_b, summary_b = load_run(run_b)
    _assert_comparable(metadata_a, metadata_b)
    task_ids_a = set(summary_a.get("tasks", {}))
    task_ids_b = set(summary_b.get("tasks", {}))
    if task_ids_a != task_ids_b:
        raise ValueError("runs contain different task IDs")
    return {
        "run_a": str(Path(run_a)),
        "run_b": str(Path(run_b)),
        "conditions": {
            "run_a": metadata_a.get("skill_condition"),
            "run_b": metadata_b.get("skill_condition"),
            "skill_suite_a": metadata_a.get("skill_suite"),
            "skill_suite_b": metadata_b.get("skill_suite"),
        },
        "overall": {
            "score_overall": _delta(summary_a["score_overall"], summary_b["score_overall"]),
            "score_attempted": _delta(summary_a["score_attempted"], summary_b["score_attempted"]),
            "coverage": _delta(summary_a["coverage"], summary_b["coverage"]),
        },
        "tasks": {
            test_id: {
                "score": _delta(summary_a["tasks"][test_id]["score"], summary_b["tasks"][test_id]["score"]),
                "attempted_a": summary_a["tasks"][test_id]["attempted"],
                "attempted_b": summary_b["tasks"][test_id]["attempted"],
            }
            for test_id in sorted(task_ids_a)
        },
        "skills": _group_deltas(summary_a, summary_b, "skills"),
        "domains": _group_deltas(summary_a, summary_b, "domains"),
        "difficulties": _group_deltas(summary_a, summary_b, "difficulties"),
    }


def format_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"tests: {summary['tests_attempted']}/{summary['tests_total']}",
        f"coverage: {summary['coverage']:.3f}",
        f"score_attempted: {summary['score_attempted']:.3f}",
        f"score_overall: {summary['score_overall']:.3f}",
    ]
    if 'task_runs' in summary:
        setting_line=(f"provided settings correctly used: {summary['correctly_used_setting_items']}/{summary['provided_setting_items']}" if summary.get('interaction_mode')=='none' else f"necessary confirmations implemented: {summary['confirmed_and_implemented_items']}/{summary['necessary_information_items']}")
        lines += [f"task success: {summary['successful_task_runs']}/{summary['task_runs']}",f"critical scientific error tasks: {summary['critical_error_task_runs']}/{summary['task_runs']}",setting_line,f"scientifically unassessable: {summary['scientifically_unassessable_task_runs']}/{summary['task_runs']}"]
    for group_name in ("domains", "skills", "difficulties"):
        lines.append(f"{group_name}:")
        for name, values in summary.get(group_name, {}).items():
            lines.append(
                f"  {name}: score={values['score_overall']:.3f}, "
                f"coverage={values['coverage']:.3f}"
            )
    return "\n".join(lines)

