from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import geopandas as gpd
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString

from harness import grader, schemas


def test_hydrology_metric_formulas_and_edge_cases() -> None:
    observed = np.array([1.0, 2.0, 3.0, 4.0])
    assert grader.hydro_metric(observed, observed, "NSE") == pytest.approx(1.0)
    assert grader.hydro_metric(observed, observed, "KGE") == pytest.approx(1.0)
    assert grader.hydro_metric(observed, observed, "PBIAS") == pytest.approx(0.0)
    assert grader.hydro_metric(observed, observed, "RMSE") == pytest.approx(0.0)
    assert grader.hydro_metric(observed, observed, "MAE") == pytest.approx(0.0)
    assert grader.hydro_metric(observed, observed, "R2") == pytest.approx(1.0)
    with pytest.raises(ValueError):
        grader.hydro_metric(np.ones(4), np.ones(4), "NSE")


def test_every_registered_grader_has_deterministic_behavior(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    test_dir = tmp_path / "task"
    expected = test_dir / "expected"
    data = test_dir / "data"
    workspace.mkdir()
    expected.mkdir(parents=True)
    data.mkdir()
    timestamps = pd.date_range("2020-01-01", periods=4, freq="D").strftime("%Y-%m-%d")
    target = pd.DataFrame({"timestamp": timestamps, "simulated": [1.0, 2.0, 3.0, 4.0], "id": ["a", "b", "c", "d"]})
    reference = pd.DataFrame({"timestamp": timestamps, "observed": [1.0, 2.0, 3.0, 4.0], "id": ["a", "b", "c", "d"]})
    target.to_csv(workspace / "series.csv", index=False)
    reference.to_csv(expected / "series.csv", index=False)
    target.to_csv(expected / "table.csv", index=False)
    (workspace / "value.json").write_text(json.dumps({"answer": "delay", "number": 2, "parameters": {"k": 0.5}}))
    (expected / "value.json").write_text(json.dumps({"answer": "delay", "number": 2}))
    (data / "ranges.json").write_text(json.dumps({"parameters": {"k": {"min": 0.0, "max": 1.0}}}))
    (workspace / "balance.csv").write_text("precipitation,discharge,evapotranspiration\n10,6,4\n")
    (workspace / "script.py").write_text("raise SystemExit(0)\n")
    (expected / 'composite.json').write_text(json.dumps({'gates':[{'criteria':[{'type':'file_check','target':'series.csv'}]}]}),encoding='utf-8')

    base_series = {
        "target": "series.csv",
        "reference": "expected/series.csv",
        "time_column": "timestamp",
        "target_column": "simulated",
        "reference_column": "observed",
    }
    criteria = [
        {"type": "file_check", "target": "series.csv"},
        {"type": "file_absence_check", "targets": ["absent.txt", "also_absent.txt"]},
        {"type": "column_check", "target": "series.csv", "required_columns": ["timestamp", "simulated"]},
        {"type": "exact_match", "target": "value.json", "field": "answer", "reference": "expected/value.json"},
        {"type": "range_check", "target": "value.json", "field": "number", "range": [1, 3]},
        {"type": "set_overlap", "target": "series.csv", "reference": "expected/series.csv", "target_columns": ["id"], "reference_columns": ["id"]},
        {"type": "numeric_correlation", **base_series},
        {"type": "code_executes", "script": "script.py"},
        {"type": "hydro_metric", "metric": "KGE", "scoring": {"zero_at": 0.2, "one_at": 0.8}, **base_series},
        {"type": "timeseries_match", "atol": 0.0, "rtol": 0.0, **base_series},
        {
            "type": "table_match",
            "target": "series.csv",
            "reference": "expected/table.csv",
            "columns": ["timestamp", "simulated", "id"],
            "datetime_columns": ["timestamp"],
            "atol": 0.0,
            "rtol": 0.0,
        },
        {"type": "peak_check", "measure": "lag_steps", "scoring": {"zero_at": 2, "one_at": 0}, **base_series},
        {"type": "volume_check", "scoring": {"zero_at": 0.4, "one_at": 0.0}, **base_series},
        {"type": "water_balance_check", "target": "balance.csv", "scoring": {"zero_at": 0.2, "one_at": 0.0}},
        {"type": "parameter_range", "target": "value.json", "field": "parameters", "ranges_file": "data/ranges.json"},
        {'type':'scientific_invariant','check':'nonnegative_finite','target':'balance.csv','columns':['precipitation','discharge','evapotranspiration']},
        {'type':'composite_contract_check','reference':'expected/composite.json'},
    ]
    assert {criterion["type"] for criterion in criteria} | {
        "raster_match", "vector_match", "artifact_reference_check", "figure_contract_check", "report_contract_check"
    } == set(grader.GRADERS)
    for criterion in criteria:
        result = grader.grade_criterion(criterion, workspace, test_dir)
        assert result["score"] == pytest.approx(1.0), (criterion["type"], result)


def test_table_match_detects_order_rows_booleans_and_text(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    expected = tmp_path / "task" / "expected"
    workspace.mkdir()
    expected.mkdir(parents=True)
    reference = pd.DataFrame(
        {
            "time": ["2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z"],
            "value": [1.0, 2.0],
            "flag": [False, True],
            "label": ["a", "b"],
        }
    )
    reference.to_csv(expected / "reference.csv", index=False)
    criterion = {
        "type": "table_match",
        "target": "target.csv",
        "reference": "expected/reference.csv",
        "columns": ["time", "value", "flag", "label"],
        "datetime_columns": ["time"],
        "atol": 1e-6,
        "rtol": 0.0,
    }

    equivalent = reference.copy()
    equivalent["time"] = ["2024-01-01T08:00:00+08:00", "2024-01-01T09:00:00+08:00"]
    equivalent["value"] = [1.0 + 5e-7, 2.0]
    equivalent.to_csv(workspace / "target.csv", index=False)
    assert grader.grade_criterion(criterion, workspace, tmp_path / "task")["score"] == pytest.approx(1.0)

    reference.iloc[::-1].to_csv(workspace / "target.csv", index=False)
    assert grader.grade_criterion(criterion, workspace, tmp_path / "task")["score"] < 1.0

    wrong = reference.iloc[:1].copy()
    wrong.loc[0, "flag"] = True
    wrong.loc[0, "label"] = "wrong"
    wrong.to_csv(workspace / "target.csv", index=False)
    result = grader.grade_criterion(criterion, workspace, tmp_path / "task")
    assert 0.0 < result["score"] < 1.0

    extra = pd.concat([reference, reference.iloc[[1]]], ignore_index=True)
    extra.to_csv(workspace / "target.csv", index=False)
    assert grader.grade_criterion(criterion, workspace, tmp_path / "task")["score"] < 1.0

    with_missing = reference.copy()
    with_missing.loc[1, "value"] = np.nan
    with_missing.to_csv(expected / "reference.csv", index=False)
    with_missing.to_csv(workspace / "target.csv", index=False)
    assert grader.grade_criterion(criterion, workspace, tmp_path / "task")["score"] == pytest.approx(1.0)

    with_missing.drop(columns=["label"]).to_csv(workspace / "target.csv", index=False)
    assert grader.grade_criterion(criterion, workspace, tmp_path / "task")["score"] == pytest.approx(0.0)


def test_file_absence_check_treats_empty_files_as_present(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    criterion = {"type": "file_absence_check", "targets": ["missing.txt", "empty.txt"]}
    assert grader.grade_criterion(criterion, workspace, tmp_path)["score"] == pytest.approx(1.0)
    (workspace / "empty.txt").touch()
    result = grader.grade_criterion(criterion, workspace, tmp_path)
    assert result["score"] == pytest.approx(0.5)


def test_raster_match_checks_grid_mask_and_values(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    expected = tmp_path / "task/expected"
    workspace.mkdir()
    expected.mkdir(parents=True)
    profile = {
        "driver": "GTiff", "height": 2, "width": 2, "count": 1, "dtype": "float32",
        "crs": "EPSG:32650", "transform": from_origin(0, 60, 30, 30), "nodata": -9999.0,
    }
    values = np.array([[1.0, 2.0], [3.0, -9999.0]], dtype="float32")
    for path in (workspace / "actual.tif", expected / "reference.tif"):
        with rasterio.open(path, "w", **profile) as target:
            target.write(values, 1)
    criterion = {"type": "raster_match", "target": "actual.tif", "reference": "expected/reference.tif", "atol": 1e-5}
    assert grader.grade_criterion(criterion, workspace, tmp_path / "task")["score"] == pytest.approx(1.0)
    with rasterio.open(workspace / "actual.tif", "r+") as target:
        changed = target.read(1)
        changed[0, 0] = 10
        target.write(changed, 1)
    assert grader.grade_criterion(criterion, workspace, tmp_path / "task")["score"] < 1.0


def test_vector_match_is_keyed_and_detects_geometry_changes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    expected = tmp_path / "task/expected"
    workspace.mkdir()
    expected.mkdir(parents=True)
    reference = gpd.GeoDataFrame(
        {"reach_id": [1, 2], "order": [1, 2]},
        geometry=[LineString([(0, 0), (1, 1)]), LineString([(1, 1), (2, 1)])], crs="EPSG:32650",
    )
    reference.to_file(expected / "reference.gpkg", layer="reaches", driver="GPKG")
    reference.iloc[::-1].to_file(workspace / "actual.gpkg", layer="reaches", driver="GPKG")
    criterion = {
        "type": "vector_match", "target": "actual.gpkg", "reference": "expected/reference.gpkg",
        "layer": "reaches", "key_columns": ["reach_id"], "columns": ["reach_id", "order"],
    }
    assert grader.grade_criterion(criterion, workspace, tmp_path / "task")["score"] == pytest.approx(1.0)
    changed = reference.copy()
    changed.loc[changed.reach_id == 2, "geometry"] = LineString([(1, 1), (3, 1)])
    (workspace / "actual.gpkg").unlink()
    changed.to_file(workspace / "actual.gpkg", layer="reaches", driver="GPKG")
    assert grader.grade_criterion(criterion, workspace, tmp_path / "task")["score"] < 1.0


def test_artifact_reference_check_rejects_bad_hash_and_unsafe_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact = workspace / "artifact.txt"
    artifact.write_text("spatial", encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    result = workspace / "result.json"
    criterion = {"type": "artifact_reference_check", "target": "result.json", "required_keys": ["item"]}
    result.write_text(json.dumps({"artifacts": {"item": {"path": "artifact.txt", "sha256": digest}}}), encoding="utf-8")
    assert grader.grade_criterion(criterion, workspace, tmp_path)["score"] == pytest.approx(1.0)
    result.write_text(json.dumps({"artifacts": {"item": {"path": "artifact.txt", "sha256": "0" * 64}}}), encoding="utf-8")
    assert grader.grade_criterion(criterion, workspace, tmp_path)["score"] == pytest.approx(0.0)
    result.write_text(json.dumps({"artifacts": {"item": {"path": "../artifact.txt", "sha256": digest}}}), encoding="utf-8")
    assert grader.grade_criterion(criterion, workspace, tmp_path)["score"] == pytest.approx(0.0)


def test_partial_credit_weighting_and_attempted(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "one.txt").write_text("x")
    task = {
        "id": "task",
        "domain": "data-preprocessing",
        "difficulty": "basic",
        "primary_skill": "skill",
        "required_outputs": ["one.txt", "missing.txt"],
        "grading": [
            {"name": "present", "type": "file_check", "target": "one.txt", "weight": 0.4},
            {"name": "missing", "type": "file_check", "target": "missing.txt", "weight": 0.6},
        ],
    }
    result = grader.grade_task(task, workspace, tmp_path)
    assert result["attempted"]
    assert result["score"] == pytest.approx(0.4)


def test_example_tasks_golden_outputs_score_full(tmp_path: Path) -> None:
    root = Path.cwd()

    data_root = root / "tests/data-preprocessing"
    task_groups = {
        "hydrodata-timeseries-*": 12,
        "hydrodata-baseflow-*": 8,
        "hydrodata-flood-events-*": 10,
        "hydrodata-eto-faopm-*": 3,
        "hydrodata-forcing-standardize-*": 3,
    }
    for pattern, expected_count in task_groups.items():
        task_dirs = sorted(data_root.glob(pattern))
        assert len(task_dirs) == expected_count
        for data_task_dir in task_dirs:
            data_task = schemas.load_json(data_task_dir / "task.json")
            data_ws = tmp_path / data_task["id"]
            shutil.copytree(data_task_dir / "expected/golden_workspace", data_ws)
            assert grader.grade_task(data_task, data_ws, data_task_dir)["score"] == pytest.approx(1.0)

    spatial_root = root / "tests/spatial-analysis"
    spatial_groups = {
        "hydrodata-dem-grid-*": 8,
        "hydrodata-stream-network-*": 8,
        "hydrodata-topology-build-*": 9,
        "hydrodata-topology-validate-*": 10,
        "hydrodata-terrain-topidx-*": 3,
        "hydrodata-forcing-aggregate-*": 3,
    }
    for pattern, expected_count in spatial_groups.items():
        task_dirs = sorted(spatial_root.glob(pattern))
        assert len(task_dirs) == expected_count
        for spatial_task_dir in task_dirs:
            spatial_task = schemas.load_json(spatial_task_dir / "task.json")
            spatial_ws = tmp_path / spatial_task["id"]
            shutil.copytree(spatial_task_dir / "expected/golden_workspace", spatial_ws)
            assert grader.grade_task(spatial_task, spatial_ws, spatial_task_dir)["score"] == pytest.approx(1.0)

    event_expectations = {
        "hydrodata-flood-events-001": (1, 1, 1),
        "hydrodata-flood-events-002": (2, 2, 2),
        "hydrodata-flood-events-003": (2, 1, 1),
        "hydrodata-flood-events-004": (2, 2, 2),
        "hydrodata-flood-events-005": (1, 1, 1),
        "hydrodata-flood-events-006": (3, 3, 1),
        "hydrodata-flood-events-007": (0, 0, 0),
        "hydrodata-flood-events-008": (1, 1, 0),
    }
    for task_id, expected_counts in event_expectations.items():
        result = json.loads(
            (data_root / task_id / "expected/golden_workspace/events/result.json").read_text(encoding="utf-8")
        )
        parameters = result["parameters"]
        actual = (
            parameters["candidate_peak_count"],
            parameters["merged_event_count"],
            parameters["final_event_count"],
        )
        assert actual == expected_counts

    analysis_task_dir = root / "examples/tasks/hydroanalysis-legacy-template"
    analysis_task = schemas.load_json(analysis_task_dir / "task.example.json")
    analysis_ws = tmp_path / "analysis"
    analysis_ws.mkdir()
    shutil.copy2(analysis_task_dir / "expected/metrics_expected.json", analysis_ws / "metrics.json")
    shutil.copy2(analysis_task_dir / "expected/diagnosis_expected.json", analysis_ws / "diagnosis.json")
    assert grader.grade_task(analysis_task, analysis_ws, analysis_task_dir)["score"] == pytest.approx(1.0)


def test_atomic_calibration_golden_outputs_score_full(tmp_path: Path) -> None:
    root = Path.cwd()
    task_dirs = sorted((root / "tests/model-calibration").glob("hydromodel-*-???"))
    assert len(task_dirs) == 48
    for task_dir in task_dirs:
        task = schemas.load_json(task_dir / "task.json")
        workspace = tmp_path / task["id"]
        shutil.copytree(task_dir / "expected/golden_workspace", workspace)
        assert grader.grade_task(task, workspace, task_dir)["score"] == pytest.approx(1.0)


def test_modeling_golden_outputs_score_full(tmp_path: Path) -> None:
    root = Path.cwd()
    modeling_groups = {
        "hydromodel-dhf-*": 3,
        "hydromodel-gr4j-*": 3,
        "hydromodel-hbv-*": 3,
        "hydromodel-lohmann-*": 3,
        "hydromodel-muskingum-*": 3,
        "hydromodel-sacsma-*": 3,
        "hydromodel-swat-sd-*": 3,
        "hydromodel-tank-*": 3,
        "hydromodel-topmodel-*": 3,
        "hydromodel-xaj-0*": 3,
        "hydromodel-xaj-sd-*": 3,
    }
    for pattern, expected_count in modeling_groups.items():
        task_dirs = sorted((root / "tests/model-calibration").glob(pattern))
        assert len(task_dirs) == expected_count
        for task_dir in task_dirs:
            task = schemas.load_json(task_dir / "task.json")
            workspace = tmp_path / task["id"]
            shutil.copytree(task_dir / "expected/golden_workspace", workspace)
            assert grader.grade_task(task, workspace, task_dir)["score"] == pytest.approx(1.0)


def test_diagnostics_golden_outputs_score_full(tmp_path: Path) -> None:
    root = Path.cwd()
    diagnostics_groups = {
        "hydroanalysis-event-metrics-*": 3,
        "hydroanalysis-series-metrics-*": 3,
        "hydroanalysis-aggregate-metrics-*": 3,
        "hydroanalysis-ml-correct-*": 3,
        "hydroanalysis-align-discharge-*": 3,
    }
    for pattern, expected_count in diagnostics_groups.items():
        task_dirs = sorted((root / "tests/results-analysis").glob(pattern))
        assert len(task_dirs) == expected_count
        for task_dir in task_dirs:
            task = schemas.load_json(task_dir / "task.json")
            workspace = tmp_path / task["id"]
            shutil.copytree(task_dir / "expected/golden_workspace", workspace)
            assert grader.grade_task(task, workspace, task_dir)["score"] == pytest.approx(1.0)
