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
    return {
        "tests_total": total,
        "tests_attempted": len(attempted),
        "coverage": len(attempted) / total if total else 0.0,
        "score_attempted": mean(attempted_scores) if attempted_scores else 0.0,
        "score_overall": mean(scores) if scores else 0.0,
    }


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
                }
                for result in sorted(results, key=lambda item: item["test_id"])
            },
            "skills": _group(results, lambda item: item["primary_skill"]),
            "domains": _group(results, lambda item: item["domain"]),
            "difficulties": _group(results, lambda item: item["difficulty"]),
        }
    )
    return summary


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return destination


def load_run(run_dir: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = Path(run_dir)
    if root.is_file():
        root = root.parent
    metadata = json.loads((root / "run_metadata.json").read_text(encoding="utf-8"))
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    return metadata, summary


def _assert_comparable(left: dict[str, Any], right: dict[str, Any]) -> None:
    keys = ("model", "effort", "agent_cmd", "task_hashes", "timeouts", "environment")
    differences = [key for key in keys if left.get(key) != right.get(key)]
    if differences:
        raise ValueError("runs are not comparable; metadata differs: " + ", ".join(differences))


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
    for group_name in ("domains", "skills", "difficulties"):
        lines.append(f"{group_name}:")
        for name, values in summary.get(group_name, {}).items():
            lines.append(
                f"  {name}: score={values['score_overall']:.3f}, "
                f"coverage={values['coverage']:.3f}"
            )
    return "\n".join(lines)

