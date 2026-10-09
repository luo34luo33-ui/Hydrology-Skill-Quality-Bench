"""Deterministic fixtures for separate-baseflow-eckhardt benchmark tasks."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
PREPARE_SKILL = "data-processing/prepare-discharge-timeseries"
BASEFLOW_SKILL = "data-processing/separate-baseflow-eckhardt"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _write_text(path: Path, text: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise RuntimeError(f"refusing to overwrite non-matching deterministic artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    # Retain the independently authored public interface when regenerating fixtures.
    if path.name == "task.json" and isinstance(value, dict):
        canonical = Path(__file__).resolve().parent / value["id"] / "public_contract.json"
        if canonical.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            destination = path.parent / "public_contract.json"
            if canonical.resolve() != destination.resolve():
                destination.write_bytes(canonical.read_bytes())
            value = dict(value, public_contract="public_contract.json")
    _write_text(path, json.dumps(_json_safe(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, lineterminator="\n", float_format="%.15g")
    _write_text(path, buffer.getvalue())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _eckhardt(discharge: np.ndarray, alpha: float, bfi_max: float) -> np.ndarray:
    baseflow = np.empty_like(discharge, dtype=float)
    baseflow[0] = discharge[0]
    denominator = 1.0 - alpha * bfi_max
    for index in range(1, len(discharge)):
        value = ((1.0 - bfi_max) * alpha * baseflow[index - 1] + (1.0 - alpha) * bfi_max * discharge[index]) / denominator
        baseflow[index] = min(max(value, 0.0), discharge[index])
    return baseflow


def _estimate_alpha(discharge: np.ndarray) -> tuple[float, int]:
    previous = discharge[:-1]
    current = discharge[1:]
    mask = np.isfinite(previous) & np.isfinite(current) & (previous > 0) & (current > 0) & (current < previous)
    ratios = current[mask] / previous[mask]
    ratios = ratios[(ratios > 0) & (ratios < 1)]
    if len(ratios) < 20:
        raise ValueError(f"自动 alpha 的有效递减流量对不足 20 个: {len(ratios)}")
    return float(np.clip(float(np.quantile(ratios, 0.90)), 0.80, 0.9999)), int(len(ratios))


def _upstream(task_dir: Path, frame: pd.DataFrame, warnings: list[str]) -> None:
    prepared = task_dir / "data" / "prepared"
    table = prepared / "discharge_timeseries.csv"
    metadata = prepared / "series_metadata.json"
    _write_csv(table, frame)
    _write_json(metadata, {
        "schema_version": "1.0", "time_column": "time", "flow_column": "discharge_m3_s",
        "source_format": "csv", "source_flow_unit": "m3/s", "standard_flow_unit": "m3/s",
        "unit_scale": 1.0, "timezone": "UTC", "timestep_seconds": 3600.0,
        "time_regularity": 1.0, "row_count": len(frame),
        "start_time": frame["time"].iloc[0], "end_time": frame["time"].iloc[-1],
        "additional_columns": [], "additional_column_semantics": "unconfirmed",
    })
    status = "warning" if warnings else "success"
    _write_json(prepared / "result.json", {
        "schema_version": "1.0", "skill": PREPARE_SKILL, "status": status,
        "message": "discharge time series prepared" if status == "success" else "discharge time series prepared with warnings",
        "parameters": {}, "inputs": {},
        "artifacts": {
            "discharge_timeseries": {"path": "discharge_timeseries.csv", "sha256": _sha256(table)},
            "series_metadata": {"path": "series_metadata.json", "sha256": _sha256(metadata)},
        },
        "checks": [], "warnings": warnings, "provenance": {"generator": "HSQB deterministic upstream"},
    })


def _result(task_dir: Path, status: str, message: str, warnings: list[str], artifacts: bool) -> dict[str, Any]:
    artifact_map: dict[str, Any] = {}
    if artifacts:
        output = task_dir / "expected" / "golden_workspace" / "components"
        artifact_map = {
            "flow_components": {"path": "flow_components.csv", "sha256": _sha256(output / "flow_components.csv")},
            "baseflow_metadata": {"path": "baseflow_metadata.json", "sha256": _sha256(output / "baseflow_metadata.json")},
        }
    return {
        "schema_version": "1.0", "skill": BASEFLOW_SKILL, "status": status, "message": message,
        "parameters": {}, "inputs": {}, "artifacts": artifact_map, "checks": [],
        "warnings": warnings, "provenance": {"generator": "HSQB deterministic oracle"},
    }


def _positive_grading(columns: list[str], row_count: int) -> list[dict[str, Any]]:
    golden = "expected/golden_workspace/components"
    result = "components/result.json"
    metadata = "components/baseflow_metadata.json"
    return [
        {
            "name": "artifact_schema", "type": "file_check",
            "targets": ["components/flow_components.csv", metadata, result],
            "required_columns": {
                "components/flow_components.csv": columns,
                metadata: ["method", "alpha", "alpha_decision", "recession_pair_count", "bfi_max", "row_count"],
                result: ["skill", "status", "message", "artifacts", "warnings"],
            },
            "expected_rows": {"components/flow_components.csv": row_count, metadata: 1, result: 1},
            "required_values": {metadata: {"method": "Eckhardt digital filter", "flow_unit": "m3/s"}},
            "artifact_references": {result: ["baseflow_metadata", "flow_components"]},
            "weight": 0.10,
        },
        {
            "name": "flow_components", "type": "table_match", "target": "components/flow_components.csv",
            "reference": f"{golden}/flow_components.csv", "columns": columns,
            "datetime_columns": ["time"], "atol": 1e-9, "rtol": 1e-9, "weight": 0.60,
        },
        *[
            {
                "name": f"metadata_{field}", "type": "exact_match", "target": metadata, "field": field,
                "reference": f"{golden}/baseflow_metadata.json", "weight": 0.05,
            }
            for field in ("alpha", "alpha_decision", "recession_pair_count", "bfi_max")
        ],
        {"name": "result_skill", "type": "exact_match", "target": result, "field": "skill", "reference": f"{golden}/result.json", "weight": 0.02},
        {"name": "result_status", "type": "exact_match", "target": result, "field": "status", "reference": f"{golden}/result.json", "weight": 0.04},
        {"name": "result_warnings", "type": "exact_match", "target": result, "field": "warnings", "reference": f"{golden}/result.json", "weight": 0.04},
    ]


def _negative_grading() -> list[dict[str, Any]]:
    target = "components/result.json"
    golden = "expected/golden_workspace/components/result.json"
    return [
        {"name": "result_schema", "type": "file_check", "target": target, "required_columns": ["skill", "status", "message", "artifacts"], "expected_rows": {target: 1}, "weight": 0.15},
        {"name": "result_skill", "type": "exact_match", "target": target, "field": "skill", "reference": golden, "weight": 0.10},
        {"name": "result_status", "type": "exact_match", "target": target, "field": "status", "reference": golden, "weight": 0.25},
        {"name": "failure_reason", "type": "exact_match", "target": target, "field": "message", "reference": golden, "weight": 0.25},
        {"name": "empty_artifacts", "type": "exact_match", "target": target, "field": "artifacts", "reference": golden, "weight": 0.10},
        {"name": "no_standard_outputs", "type": "file_absence_check", "targets": ["components/flow_components.csv", "components/flow_components.parquet", "components/flow_components.xlsx", "components/baseflow_metadata.json"], "weight": 0.15},
    ]


def _task(task_id: str, title: str, difficulty: str, prompt: str, description: str, positive: bool, columns: list[str] | None = None, row_count: int = 0) -> dict[str, Any]:
    required = ["components/result.json"]
    if positive:
        required = ["components/flow_components.csv", "components/baseflow_metadata.json", *required]
    return {
        "id": task_id, "title": title, "domain": "data-preprocessing", "difficulty": difficulty,
        "primary_skill": BASEFLOW_SKILL, "secondary_skills": [], "prompt": prompt,
        "data_description": description,
        "data_files": ["prepared/result.json", "prepared/discharge_timeseries.csv", "prepared/series_metadata.json"],
        "required_outputs": required,
        "setup_notes": [
            "The prepared/ directory is a complete, hash-verifiable prepare-discharge-timeseries result. Do not rerun the upstream skill.",
            "Write native separate-baseflow-eckhardt outputs under components/ and do not substitute another baseflow method.",
        ],
        "timeout_seconds": 300,
        "grading": _positive_grading(columns or [], row_count) if positive else _negative_grading(),
    }


def _base_frame(discharge: np.ndarray, start: str) -> pd.DataFrame:
    return pd.DataFrame({
        "time": pd.date_range(start, periods=len(discharge), freq="h", tz="UTC"),
        "discharge_m3_s": discharge,
        "is_imputed": False,
    })


def _write_positive(task_dir: Path, task: dict[str, Any], frame: pd.DataFrame, bfi_max: float, alpha: float, decision: str, pairs: int, warnings: list[str]) -> None:
    _write_json(task_dir / "task.json", task)
    _upstream(task_dir, frame, warnings)
    staged = pd.read_csv(task_dir / "data" / "prepared" / "discharge_timeseries.csv")
    discharge = staged["discharge_m3_s"].to_numpy(dtype=float)
    if decision == "estimated-90th-quantile-of-recession-ratios":
        alpha, pairs = _estimate_alpha(discharge)
    baseflow = _eckhardt(discharge, alpha, bfi_max)
    quickflow = np.maximum(discharge - baseflow, 0.0)
    ratio = np.divide(quickflow, discharge, out=np.zeros_like(quickflow), where=discharge > 0)
    output = staged.copy()
    output["baseflow_m3_s"] = baseflow
    output["quickflow_m3_s"] = quickflow
    output["quickflow_fraction"] = ratio
    golden = task_dir / "expected" / "golden_workspace" / "components"
    _write_csv(golden / "flow_components.csv", output)
    _write_json(golden / "baseflow_metadata.json", {
        "schema_version": "1.0", "method": "Eckhardt digital filter", "alpha": alpha,
        "alpha_decision": decision, "recession_pair_count": pairs, "bfi_max": bfi_max,
        "flow_unit": "m3/s", "row_count": len(output), "upstream_series_metadata": {},
    })
    status = "warning" if warnings else "success"
    message = "Eckhardt baseflow separated" if status == "success" else "Eckhardt baseflow separated with upstream warnings"
    _write_json(golden / "result.json", _result(task_dir, status, message, warnings, True))


def _write_negative(task_dir: Path, task: dict[str, Any], frame: pd.DataFrame, message: str) -> None:
    _write_json(task_dir / "task.json", task)
    _upstream(task_dir, frame, [])
    golden = task_dir / "expected" / "golden_workspace" / "components"
    _write_json(golden / "result.json", _result(task_dir, "error", message, [], False))


def generate_task(task_id: str) -> None:
    task_dir = ROOT / task_id
    explicit_prompt = "Use prepared/result.json as the verified upstream result. The confirmed Eckhardt parameters are {params}. Write CSV outputs under components/."

    if task_id == "hydrodata-baseflow-001":
        discharge = np.array([12, 13, 16, 25, 45, 30, 22, 18, 15, 14, 16, 28, 55, 36, 25, 20, 17, 15, 14, 13], dtype=float)
        frame = _base_frame(discharge, "2024-01-01")
        prompt = explicit_prompt.format(params="alpha=0.95 and BFImax=0.80; do not estimate alpha")
        task = _task(task_id, "Separate a multi-peak hydrograph with explicit Eckhardt parameters", "basic", prompt, "A regular nonnegative multi-peak discharge hydrograph.", True, [*frame.columns, "baseflow_m3_s", "quickflow_m3_s", "quickflow_fraction"], len(frame))
        _write_positive(task_dir, task, frame, 0.80, 0.95, "user-provided", 0, [])
        return

    if task_id == "hydrodata-baseflow-002":
        discharge = np.array([8, 6, 3, 0, 0, 4, 12, 7, 2, 0, 0, 5, 9, 4, 1, 0], dtype=float)
        frame = _base_frame(discharge, "2024-02-01")
        warnings = ["timezone explicitly recorded as naive"]
        prompt = explicit_prompt.format(params="alpha=0.92 and BFImax=0.75; do not estimate alpha") + " Preserve the upstream warning and handle zero discharge without division errors."
        task = _task(task_id, "Handle zero-flow intervals and propagate an upstream warning", "intermediate", prompt, "A discharge series with zero-flow intervals and a valid upstream warning.", True, [*frame.columns, "baseflow_m3_s", "quickflow_m3_s", "quickflow_fraction"], len(frame))
        _write_positive(task_dir, task, frame, 0.75, 0.92, "user-provided", 0, warnings)
        return

    auto_specs = {
        "hydrodata-baseflow-003": (0.93, 0.80, "Estimate recession alpha from more than twenty identical recession ratios", "A long geometric recession with sufficient alpha evidence.", "2024-03-01"),
        "hydrodata-baseflow-004": (0.70, 0.80, "Clip a rapidly estimated recession alpha to the lower bound", "A rapid geometric recession whose raw alpha estimate is below 0.80.", "2024-04-01"),
        "hydrodata-baseflow-005": (0.99995, 0.80, "Clip a slowly estimated recession alpha to the upper bound", "A very slow geometric recession whose raw alpha estimate exceeds 0.9999.", "2024-05-01"),
    }
    if task_id in auto_specs:
        ratio, bfi_max, title, description, start = auto_specs[task_id]
        discharge = 100.0 * ratio ** np.arange(30)
        frame = _base_frame(discharge, start)
        alpha, pairs = _estimate_alpha(discharge)
        prompt = explicit_prompt.format(params=f"BFImax={bfi_max:.2f} and automatic alpha estimation; do not provide or invent an explicit alpha")
        task = _task(task_id, title, "intermediate", prompt, description, True, [*frame.columns, "baseflow_m3_s", "quickflow_m3_s", "quickflow_fraction"], len(frame))
        _write_positive(task_dir, task, frame, bfi_max, alpha, "estimated-90th-quantile-of-recession-ratios", pairs, [])
        return

    if task_id == "hydrodata-baseflow-006":
        frame = _base_frame(10.0 + np.arange(25), "2024-06-01")
        prompt = explicit_prompt.format(params="BFImax=0.80 and automatic alpha estimation") + " Do not use a fallback alpha when recession evidence is insufficient."
        task = _task(task_id, "Reject automatic alpha estimation with insufficient recession evidence", "intermediate", prompt, "A monotonically rising series with no valid recession pairs.", False)
        _write_negative(task_dir, task, frame, "自动 alpha 的有效递减流量对不足 20 个: 0")
        return

    if task_id == "hydrodata-baseflow-007":
        discharge = 20.0 + np.arange(12, dtype=float)
        discharge[6] = np.inf
        frame = _base_frame(discharge, "2024-07-01")
        prompt = explicit_prompt.format(params="alpha=0.95 and BFImax=0.80") + " Reject non-finite discharge; do not remove or replace the affected row."
        task = _task(task_id, "Reject non-finite discharge in a hash-valid upstream artifact", "basic", prompt, "A hash-valid prepared artifact containing one positive-infinite discharge value.", False)
        _write_negative(task_dir, task, frame, "流量必须是至少两个有限非负值")
        return

    if task_id == "hydrodata-baseflow-008":
        frame = _base_frame(np.array([10, 12, 18, 25, 20, 16, 14, 13, 12, 11, 10, 9], dtype=float), "2024-08-01")
        prompt = explicit_prompt.format(params="alpha=0.95 and BFImax=1.0") + " Do not clamp or replace the explicitly supplied BFImax."
        task = _task(task_id, "Reject an out-of-range BFImax", "basic", prompt, "A valid hydrograph paired with an explicitly invalid BFImax.", False)
        _write_negative(task_dir, task, frame, "bfi-max 必须属于 (0, 1)")
        return

    raise KeyError(f"unknown task id: {task_id}")
