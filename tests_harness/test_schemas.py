from __future__ import annotations

import json
from pathlib import Path

from harness import runner, schemas


def make_task(root: Path, domain: str = "data-preprocessing", task_id: str = "demo-001") -> tuple[dict, Path]:
    task_dir = root / domain / task_id
    (task_dir / "data").mkdir(parents=True)
    (task_dir / "data" / "input.csv").write_text("value\n1\n", encoding="utf-8")
    task = {
        "id": task_id,
        "title": "Demo",
        "domain": domain,
        "difficulty": "basic",
        "primary_skill": "demo-skill",
        "secondary_skills": [],
        "prompt": "Create output.txt.",
        "data_files": ["input.csv"],
        "required_outputs": ["output.txt"],
        "timeout_seconds": 10,
        "grading": [{"name": "file", "type": "file_check", "target": "output.txt", "weight": 1.0}],
    }
    (task_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")
    return task, task_dir


def test_valid_task_and_public_projection(tmp_path: Path) -> None:
    task, task_dir = make_task(tmp_path)
    assert schemas.validate_task(task, task_dir) == []
    public = schemas.public_task(task)
    assert "grading" not in public
    assert "primary_skill" not in public
    assert public["required_outputs"] == ["output.txt"]


def test_schema_rejects_path_traversal_unknown_grader_and_bad_weights(tmp_path: Path) -> None:
    task, task_dir = make_task(tmp_path)
    task["data_files"] = ["../expected/secret.csv"]
    task["grading"] = [{"name": "bad", "type": "mystery", "target": "../x", "weight": 0.4}]
    errors = schemas.validate_task(task, task_dir)
    joined = " | ".join(errors)
    assert "unsafe data_files path" in joined
    assert "unknown grader type" in joined
    assert "grading weights must sum" in joined


def test_validation_detects_duplicate_ids(tmp_path: Path) -> None:
    make_task(tmp_path, "data-preprocessing", "same-001")
    make_task(tmp_path, "results-analysis", "same-001")
    errors = runner.validate_tests(tmp_path)
    assert any("duplicate task id" in item["error"] for item in errors)


def test_repository_tasks_validate() -> None:
    assert runner.validate_tests("tests") == []


def test_example_template_is_not_discovered_as_a_runnable_task() -> None:
    discovered = runner.discover_tasks("tests")
    ids = {item["task"]["id"] for item in discovered}
    template = Path("examples/tasks/hydrodata-example")
    assert (template / "task.example.json").is_file()
    assert not (template / "task.json").exists()
    assert "hydrodata-example" not in ids
    assert "hydrodata-001" not in ids
    assert {f"hydrodata-timeseries-{index:03d}" for index in range(1, 13)} <= ids
    assert {f"hydrodata-baseflow-{index:03d}" for index in range(1, 9)} <= ids
    assert {f"hydrodata-flood-events-{index:03d}" for index in range(1, 11)} <= ids
    assert {f"hydrodata-dem-grid-{index:03d}" for index in range(1, 9)} <= ids
    assert {f"hydrodata-stream-network-{index:03d}" for index in range(1, 9)} <= ids
    assert {f"hydrodata-topology-build-{index:03d}" for index in range(1, 10)} <= ids
    assert {f"hydrodata-topology-validate-{index:03d}" for index in range(1, 11)} <= ids
    assert {
        f"hydromodel-{algorithm}-{index:03d}"
        for algorithm in ("de", "dhf", "ga", "gr4j", "hbv", "lohmann", "muskingum", "pso", "sacsma", "sce-ua", "swat-sd", "tank", "topmodel", "two-stage", "xaj", "xaj-sd")
        for index in range(1, 4)
    } <= ids
    assert {f"hydrodata-eto-faopm-{index:03d}" for index in range(1, 4)} <= ids
    assert {f"hydrodata-forcing-standardize-{index:03d}" for index in range(1, 4)} <= ids
    assert {f"hydrodata-terrain-topidx-{index:03d}" for index in range(1, 4)} <= ids
    assert {f"hydrodata-forcing-aggregate-{index:03d}" for index in range(1, 4)} <= ids
    assert {f"hydroanalysis-align-discharge-{index:03d}" for index in range(1, 4)} <= ids
    assert {f"hydroanalysis-event-metrics-{index:03d}" for index in range(1, 4)} <= ids
    assert {f"hydroanalysis-series-metrics-{index:03d}" for index in range(1, 4)} <= ids
    assert {f"hydroanalysis-aggregate-metrics-{index:03d}" for index in range(1, 4)} <= ids
    assert {f"hydroanalysis-ml-correct-{index:03d}" for index in range(1, 4)} <= ids
