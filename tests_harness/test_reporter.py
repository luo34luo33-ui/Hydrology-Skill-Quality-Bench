from __future__ import annotations

from pathlib import Path

import pytest

from harness import reporter


def sample_results(delta: float = 0.0) -> list[dict]:
    return [
        {
            "test_id": "a",
            "domain": "data-preprocessing",
            "difficulty": "basic",
            "primary_skill": "qc",
            "attempted": True,
            "score": 0.5 + delta,
        },
        {
            "test_id": "b",
            "domain": "model-calibration",
            "difficulty": "advanced",
            "primary_skill": "calibration",
            "attempted": False,
            "score": 0.0,
        },
    ]


def metadata() -> dict:
    return {
        "model": "model",
        "effort": "medium",
        "agent_cmd": "agent",
        "task_hashes": {"a": "1", "b": "2"},
        "timeouts": {"a": 10, "b": 10},
        "environment": {"python": "3.13"},
        "skill_condition": "no-skills",
        "skill_suite": None,
    }


def write_run(root: Path, results: list[dict], meta: dict) -> None:
    reporter.write_json(root / "run_metadata.json", meta)
    reporter.write_json(root / "summary.json", reporter.aggregate_results(results))


def test_coverage_and_score_are_separate() -> None:
    summary = reporter.aggregate_results(sample_results())
    assert summary["coverage"] == 0.5
    assert summary["score_attempted"] == 0.5
    assert summary["score_overall"] == 0.25
    assert summary["skills"]["qc"]["score_overall"] == 0.5


def test_compare_reports_paired_uplift(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    meta_left = metadata()
    meta_right = metadata()
    meta_right["skill_condition"] = "with-skills"
    meta_right["skill_suite"] = "suite"
    write_run(left, sample_results(), meta_left)
    write_run(right, sample_results(0.25), meta_right)
    comparison = reporter.compare_runs(left, right)
    assert comparison["overall"]["score_overall"]["absolute_uplift"] == pytest.approx(0.125)
    assert comparison["tasks"]["a"]["score"]["absolute_uplift"] == pytest.approx(0.25)


def test_compare_rejects_confounded_runs(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    meta_left = metadata()
    meta_right = metadata()
    meta_right["model"] = "different"
    write_run(left, sample_results(), meta_left)
    write_run(right, sample_results(), meta_right)
    with pytest.raises(ValueError, match="model"):
        reporter.compare_runs(left, right)

