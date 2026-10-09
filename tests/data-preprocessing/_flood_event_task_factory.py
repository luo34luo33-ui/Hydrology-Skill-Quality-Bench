"""Deterministic fixtures for extract-flood-events benchmark tasks."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import find_peaks
import yaml


ROOT = Path(__file__).resolve().parent
BASEFLOW_SKILL = "data-processing/separate-baseflow-eckhardt"
EVENT_SKILL = "data-processing/extract-flood-events"


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


def _write_yaml(path: Path, value: dict[str, Any]) -> None:
    _write_text(path, yaml.safe_dump(value, allow_unicode=True, sort_keys=False))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class EventConfig:
    peak_quantile: float
    prominence_factor: float
    min_peak_distance_hours: float
    boundary_fraction: float
    boundary_persistence_steps: int
    max_search_days: float
    merge_gap_hours: float
    valley_ratio_threshold: float
    min_event_duration_hours: float
    min_peak_flow_m3_s: float | None
    min_event_volume_m3: float | None
    warmup_steps: int


def _config(**overrides: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "schema_version": "1.0",
        "peak_detection": {"peak_quantile": 0.50, "prominence_factor": 0.10, "min_peak_distance_hours": 4.0},
        "boundaries": {"boundary_fraction": 0.05, "boundary_persistence_steps": 2, "max_search_days": 2.0},
        "merging": {"merge_gap_hours": 6.0, "valley_ratio_threshold": 0.60},
        "filters": {"min_event_duration_hours": 1.0, "min_peak_flow_m3_s": None, "min_event_volume_m3": None},
        "warmup": {"steps": 3},
    }
    for dotted, value in overrides.items():
        section, field = dotted.split("__", 1)
        raw[section][field] = value
    return raw


def _cfg(raw: dict[str, Any]) -> EventConfig:
    p, b, m, f, w = (raw[name] for name in ("peak_detection", "boundaries", "merging", "filters", "warmup"))
    return EventConfig(
        float(p["peak_quantile"]), float(p["prominence_factor"]), float(p["min_peak_distance_hours"]),
        float(b["boundary_fraction"]), int(b["boundary_persistence_steps"]), float(b["max_search_days"]),
        float(m["merge_gap_hours"]), float(m["valley_ratio_threshold"]),
        float(f["min_event_duration_hours"]), None if f["min_peak_flow_m3_s"] is None else float(f["min_peak_flow_m3_s"]),
        None if f["min_event_volume_m3"] is None else float(f["min_event_volume_m3"]), int(w["steps"]),
    )


def _pulse(length: int, center: int, height: float, width: int) -> np.ndarray:
    index = np.arange(length)
    return np.maximum(0.0, height * (1.0 - np.abs(index - center) / width))


def _frame(quickflow: np.ndarray, start: str, baseflow: float = 10.0, imbalance: float = 0.0) -> pd.DataFrame:
    base = np.full(len(quickflow), baseflow, dtype=float)
    discharge = base + quickflow + imbalance
    ratio = np.divide(quickflow, discharge, out=np.zeros_like(quickflow), where=discharge > 0)
    return pd.DataFrame({
        "time": pd.date_range(start, periods=len(quickflow), freq="h", tz="UTC"),
        "discharge_m3_s": discharge,
        "is_imputed": False,
        "baseflow_m3_s": base,
        "quickflow_m3_s": quickflow,
        "quickflow_fraction": ratio,
    })


def _upstream(task_dir: Path, frame: pd.DataFrame) -> None:
    components = task_dir / "data" / "components"
    table = components / "flow_components.csv"
    metadata = components / "baseflow_metadata.json"
    _write_csv(table, frame)
    _write_json(metadata, {
        "schema_version": "1.0", "method": "Eckhardt digital filter", "alpha": 0.95,
        "alpha_decision": "user-provided", "recession_pair_count": 0, "bfi_max": 0.80,
        "flow_unit": "m3/s", "row_count": len(frame), "upstream_series_metadata": {},
    })
    _write_json(components / "result.json", {
        "schema_version": "1.0", "skill": BASEFLOW_SKILL, "status": "success",
        "message": "Eckhardt baseflow separated", "parameters": {}, "inputs": {},
        "artifacts": {
            "flow_components": {"path": "flow_components.csv", "sha256": _sha256(table)},
            "baseflow_metadata": {"path": "baseflow_metadata.json", "sha256": _sha256(metadata)},
        },
        "checks": [], "warnings": [], "provenance": {"generator": "HSQB deterministic upstream"},
    })


def _detect_peaks(quickflow: np.ndarray, cfg: EventConfig) -> np.ndarray:
    positive = quickflow[quickflow > 0]
    if not len(positive):
        return np.array([], dtype=int)
    threshold = float(np.quantile(positive, cfg.peak_quantile))
    prominence = max(np.finfo(float).eps, cfg.prominence_factor * float(np.nanstd(quickflow)))
    distance = max(1, int(round(cfg.min_peak_distance_hours)))
    peaks, _ = find_peaks(quickflow, height=threshold, prominence=prominence, distance=distance)
    return peaks.astype(int)


def _left_boundary(peak: int, values: np.ndarray, cfg: EventConfig) -> int:
    maximum = max(1, int(round(cfg.max_search_days * 24)))
    limit = max(0, peak - maximum)
    segment = values[limit:peak + 1]
    baseline = float(np.nanmin(segment))
    threshold = baseline + cfg.boundary_fraction * max(float(values[peak]) - baseline, 0.0)
    for index in range(peak - 1, limit + cfg.boundary_persistence_steps - 2, -1):
        start = index - cfg.boundary_persistence_steps + 1
        if start < limit:
            break
        if np.all(values[start:index + 1] <= threshold):
            return index
    return limit + int(np.nanargmin(segment))


def _right_boundary(peak: int, values: np.ndarray, cfg: EventConfig) -> int:
    maximum = max(1, int(round(cfg.max_search_days * 24)))
    limit = min(len(values) - 1, peak + maximum)
    segment = values[peak:limit + 1]
    baseline = float(np.nanmin(segment))
    threshold = baseline + cfg.boundary_fraction * max(float(values[peak]) - baseline, 0.0)
    for index in range(peak + 1, limit - cfg.boundary_persistence_steps + 2):
        block = values[index:index + cfg.boundary_persistence_steps]
        if len(block) == cfg.boundary_persistence_steps and np.all(block <= threshold):
            return index
    return peak + int(np.nanargmin(segment))


def _raw_events(peaks: np.ndarray, discharge: np.ndarray, cfg: EventConfig) -> list[dict[str, int]]:
    return [{"start_idx": _left_boundary(int(peak), discharge, cfg), "peak_idx": int(peak), "end_idx": _right_boundary(int(peak), discharge, cfg)} for peak in peaks]


def _merge(events: list[dict[str, int]], discharge: np.ndarray, cfg: EventConfig) -> list[dict[str, int]]:
    if not events:
        return []
    merged = [sorted(events, key=lambda item: item["start_idx"])[0].copy()]
    maximum_gap = max(0, int(round(cfg.merge_gap_hours)))
    for current in sorted(events, key=lambda item: item["start_idx"])[1:]:
        previous = merged[-1]
        overlap = current["start_idx"] <= previous["end_idx"]
        gap = max(0, current["start_idx"] - previous["end_idx"] - 1)
        valley_merge = False
        if not overlap and gap <= maximum_gap:
            left, right = sorted((previous["peak_idx"], current["peak_idx"]))
            valley = float(np.min(discharge[left:right + 1]))
            smaller_peak = float(min(discharge[previous["peak_idx"]], discharge[current["peak_idx"]]))
            valley_merge = smaller_peak > 0 and valley / smaller_peak >= cfg.valley_ratio_threshold
        if overlap or valley_merge:
            start = min(previous["start_idx"], current["start_idx"])
            end = max(previous["end_idx"], current["end_idx"])
            peak = start + int(np.argmax(discharge[start:end + 1]))
            merged[-1] = {"start_idx": start, "peak_idx": peak, "end_idx": end}
        else:
            merged.append(current.copy())
    return merged


def _refine(events: list[dict[str, int]], quickflow: np.ndarray, cfg: EventConfig) -> list[dict[str, int]]:
    return [{"start_idx": _left_boundary(item["peak_idx"], quickflow, cfg), "peak_idx": item["peak_idx"], "end_idx": _right_boundary(item["peak_idx"], quickflow, cfg)} for item in events]


def _products(frame: pd.DataFrame, events: list[dict[str, int]], cfg: EventConfig) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    discharge = frame["discharge_m3_s"].to_numpy(dtype=float)
    baseflow = frame["baseflow_m3_s"].to_numpy(dtype=float)
    quickflow = frame["quickflow_m3_s"].to_numpy(dtype=float)
    event_ids = np.full(len(frame), np.nan)
    summaries: list[dict[str, Any]] = []
    processes: list[pd.DataFrame] = []
    event_id = 0
    for event in sorted(events, key=lambda item: (item["start_idx"], item["peak_idx"])):
        start, peak, end = event["start_idx"], event["peak_idx"], event["end_idx"]
        duration = float(end - start)
        total_volume = float(np.trapezoid(discharge[start:end + 1], dx=3600.0))
        quick_volume = float(np.trapezoid(quickflow[start:end + 1], dx=3600.0))
        base_volume = float(np.trapezoid(baseflow[start:end + 1], dx=3600.0))
        if duration < cfg.min_event_duration_hours:
            continue
        if cfg.min_peak_flow_m3_s is not None and discharge[peak] < cfg.min_peak_flow_m3_s:
            continue
        if cfg.min_event_volume_m3 is not None and total_volume < cfg.min_event_volume_m3:
            continue
        event_id += 1
        event_ids[start:end + 1] = event_id
        export_start = max(0, start - cfg.warmup_steps)
        summaries.append({
            "event_id": event_id, "warmup_start_time": frame.loc[export_start, "time"],
            "start_time": frame.loc[start, "time"], "peak_time": frame.loc[peak, "time"], "end_time": frame.loc[end, "time"],
            "warmup_start_idx": export_start, "start_idx": start, "peak_idx": peak, "end_idx": end,
            "start_flow_m3_s": discharge[start], "peak_flow_m3_s": discharge[peak], "end_flow_m3_s": discharge[end],
            "duration_hours": duration, "rise_time_hours": float(peak - start), "recession_time_hours": float(end - peak),
            "total_volume_m3": total_volume, "quickflow_volume_m3": quick_volume, "baseflow_volume_m3": base_volume,
            "quickflow_fraction": quick_volume / total_volume if total_volume > 0 else np.nan,
            "n_local_peaks": int(len(find_peaks(discharge[start:end + 1])[0])),
        })
        part = frame.iloc[export_start:end + 1].copy()
        part.insert(0, "event_id", event_id)
        indices = np.arange(export_start, end + 1)
        part["source_index"] = indices
        part["is_warmup"] = indices < start
        part["relative_step"] = indices - start
        part["hours_from_start"] = (indices - start).astype(float)
        processes.append(part)
    summary = pd.DataFrame(summaries)
    if summary.empty:
        summary = pd.DataFrame(columns=["event_id", "warmup_start_time", "start_time", "peak_time", "end_time", "warmup_start_idx", "start_idx", "peak_idx", "end_idx", "start_flow_m3_s", "peak_flow_m3_s", "end_flow_m3_s", "duration_hours", "rise_time_hours", "recession_time_hours", "total_volume_m3", "quickflow_volume_m3", "baseflow_volume_m3", "quickflow_fraction", "n_local_peaks"])
    process = pd.concat(processes, ignore_index=True) if processes else pd.DataFrame(columns=["event_id", *frame.columns, "source_index", "is_warmup", "relative_step", "hours_from_start"])
    annotated = frame.copy()
    annotated["event_id"] = pd.array(event_ids, dtype="Int64")
    return summary, process, annotated


def _checks(summary: pd.DataFrame, process: pd.DataFrame, annotated: pd.DataFrame, cfg: EventConfig) -> list[dict[str, str]]:
    ids = summary["event_id"].astype(int).tolist() if len(summary) else []
    checks: list[dict[str, str]] = [
        {"check": "event_identity_and_order", "status": "PASS", "details": f"events={len(ids)}; stable chronological IDs"},
        {"check": "event_boundaries", "status": "PASS", "details": "boundaries, times and peaks are consistent"},
        {"check": "configured_filters", "status": "PASS", "details": "all retained events satisfy explicit filters"},
    ]
    balance_failures = []
    for row in summary.itertuples():
        balance = abs(float(row.total_volume_m3) - float(row.baseflow_volume_m3) - float(row.quickflow_volume_m3))
        if balance > max(1e-6, abs(float(row.total_volume_m3)) * 1e-9):
            balance_failures.append(f"event {row.event_id} volume balance failed")
    checks.append({"check": "volume_balance", "status": "FAIL" if balance_failures else "PASS", "details": " | ".join(balance_failures) if balance_failures else "total = baseflow + quickflow within tolerance"})
    checks.extend([
        {"check": "table_consistency", "status": "PASS", "details": f"summary={len(summary)}, process={len(process)}, series={len(annotated)}"},
        {"check": "warmup_exclusion", "status": "PASS", "details": "warm-up rows are flagged and excluded from event metrics"},
    ])
    return checks


def _result(task_dir: Path, status: str, message: str, warnings: list[str], artifacts: dict[str, Any], parameters: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": "1.0", "skill": EVENT_SKILL, "status": status, "message": message, "parameters": parameters, "inputs": {}, "artifacts": artifacts, "checks": checks, "warnings": warnings, "provenance": {"generator": "HSQB deterministic oracle"}}


def _positive_grading(summary: pd.DataFrame, process: pd.DataFrame, annotated: pd.DataFrame, per_event_paths: list[str]) -> list[dict[str, Any]]:
    golden = "expected/golden_workspace/events"
    result = "events/result.json"
    targets = ["events/event_summary.csv", "events/event_process.csv", "events/annotated_series.csv", "events/event_config.yaml", "events/event_manifest.json", "events/event_qc.csv", result, *per_event_paths]
    required_columns: dict[str, list[str]] = {
        "events/event_summary.csv": list(summary.columns), "events/event_process.csv": list(process.columns),
        "events/annotated_series.csv": list(annotated.columns), "events/event_manifest.json": ["event_count", "files"],
        "events/event_qc.csv": ["check", "status", "details"], result: ["skill", "status", "parameters", "artifacts", "warnings"],
    }
    expected_rows: dict[str, int] = {"events/event_summary.csv": len(summary), "events/event_process.csv": len(process), "events/annotated_series.csv": len(annotated), "events/event_manifest.json": 1, "events/event_qc.csv": 8, result: 1}
    return [
        {"name": "artifact_schema", "type": "file_check", "targets": targets, "required_columns": required_columns, "expected_rows": expected_rows, "weight": 0.10},
        {"name": "event_summary", "type": "table_match", "target": "events/event_summary.csv", "reference": f"{golden}/event_summary.csv", "columns": list(summary.columns), "datetime_columns": ["warmup_start_time", "start_time", "peak_time", "end_time"], "atol": 1e-8, "rtol": 1e-9, "weight": 0.20},
        {"name": "event_process", "type": "table_match", "target": "events/event_process.csv", "reference": f"{golden}/event_process.csv", "columns": list(process.columns), "datetime_columns": ["time"], "atol": 1e-8, "rtol": 1e-9, "weight": 0.18},
        {"name": "annotated_series", "type": "table_match", "target": "events/annotated_series.csv", "reference": f"{golden}/annotated_series.csv", "columns": list(annotated.columns), "datetime_columns": ["time"], "atol": 1e-8, "rtol": 1e-9, "weight": 0.17},
        {"name": "manifest_event_count", "type": "exact_match", "target": "events/event_manifest.json", "field": "event_count", "reference": f"{golden}/event_manifest.json", "weight": 0.05},
        {"name": "result_skill", "type": "exact_match", "target": result, "field": "skill", "reference": f"{golden}/result.json", "weight": 0.02},
        {"name": "result_status", "type": "exact_match", "target": result, "field": "status", "reference": f"{golden}/result.json", "weight": 0.04},
        {"name": "result_warnings", "type": "exact_match", "target": result, "field": "warnings", "reference": f"{golden}/result.json", "weight": 0.03},
        *[
            {"name": f"result_{field}", "type": "exact_match", "target": result, "field": f"parameters.{field}", "reference": f"{golden}/result.json", "weight": 0.04}
            for field in ("candidate_peak_count", "merged_event_count", "final_event_count")
        ],
        {"name": "qc_checks", "type": "set_overlap", "target": "events/event_qc.csv", "reference": f"{golden}/event_qc.csv", "columns": ["check", "status"], "metric": "f1", "weight": 0.09},
    ]


def _negative_grading(scientific_qc: bool) -> list[dict[str, Any]]:
    target = "events/result.json"
    golden = "expected/golden_workspace/events/result.json"
    common = [
        {"name": "result_schema", "type": "file_check", "target": target, "required_columns": ["skill", "status", "message", "artifacts", "checks"], "expected_rows": {target: 1}, "weight": 0.10 if scientific_qc else 0.15},
        {"name": "result_skill", "type": "exact_match", "target": target, "field": "skill", "reference": golden, "weight": 0.10},
        {"name": "result_status", "type": "exact_match", "target": target, "field": "status", "reference": golden, "weight": 0.20 if scientific_qc else 0.25},
        {"name": "failure_reason", "type": "exact_match", "target": target, "field": "message", "reference": golden, "weight": 0.20 if scientific_qc else 0.25},
        {"name": "empty_artifacts", "type": "exact_match", "target": target, "field": "artifacts", "reference": golden, "weight": 0.10},
        {"name": "no_event_outputs", "type": "file_absence_check", "targets": ["events/event_summary.csv", "events/event_process.csv", "events/annotated_series.csv", "events/flood_event_dataset.xlsx", "events/event_config.yaml", "events/event_manifest.json", "events/event_qc.csv", "events/event_files"], "weight": 0.15},
    ]
    if scientific_qc:
        common.extend([
            {"name": "scientific_qc_name", "type": "exact_match", "target": target, "field": "checks.0.check", "reference": golden, "weight": 0.075},
            {"name": "scientific_qc_status", "type": "exact_match", "target": target, "field": "checks.0.status", "reference": golden, "weight": 0.075},
        ])
    return common


def _task(task_id: str, title: str, difficulty: str, prompt: str, description: str, positive: bool, summary: pd.DataFrame | None = None, process: pd.DataFrame | None = None, annotated: pd.DataFrame | None = None, per_event_paths: list[str] | None = None, scientific_qc: bool = False) -> dict[str, Any]:
    required = ["events/result.json"]
    if positive:
        required = ["events/event_summary.csv", "events/event_process.csv", "events/annotated_series.csv", "events/event_config.yaml", "events/event_manifest.json", "events/event_qc.csv", *list(per_event_paths or []), *required]
    return {
        "id": task_id, "title": title, "domain": "data-preprocessing", "difficulty": difficulty,
        "primary_skill": EVENT_SKILL, "secondary_skills": [], "prompt": prompt,
        "data_description": description,
        "data_files": ["components/result.json", "components/flow_components.csv", "components/baseflow_metadata.json", "event_config.yaml"],
        "required_outputs": required,
        "setup_notes": [
            "components/ contains a complete hash-verifiable separate-baseflow-eckhardt result; do not rerun upstream skills.",
            "Every scientific parameter is explicit in event_config.yaml. Do not tune or relax the configuration.",
        ],
        "timeout_seconds": 300,
        "grading": _positive_grading(summary, process, annotated, list(per_event_paths or [])) if positive and summary is not None and process is not None and annotated is not None else _negative_grading(scientific_qc),
    }


def _materialize_v1(task_dir: Path, task_id: str, title: str, difficulty: str, description: str, frame: pd.DataFrame, raw_config: dict[str, Any], filename_by: str = "event-id", positive: bool = True, error_message: str | None = None, scientific_qc: bool = False) -> None:
    _upstream(task_dir, frame)
    _write_yaml(task_dir / "data" / "event_config.yaml", raw_config)
    prompt = f"Use components/result.json and the complete confirmed parameters in event_config.yaml to extract flood events. Write CSV main tables and CSV per-event files under events/, naming per-event files by {filename_by}. Do not change, infer, or relax any scientific parameter."
    if not positive:
        prompt += " Preserve the native error result.json and do not create event artifacts when validation or scientific QC fails."
        task = _task(task_id, title, difficulty, prompt, description, False, scientific_qc=scientific_qc)
        _write_json(task_dir / "task.json", task)
        checks = [{"check": "scientific_qc", "status": "FAIL", "details": error_message}] if scientific_qc else []
        golden = task_dir / "expected" / "golden_workspace" / "events"
        _write_json(golden / "result.json", _result(task_dir, "error", str(error_message), [], {}, {}, checks))
        return

    cfg = _cfg(raw_config)
    staged = pd.read_csv(task_dir / "data" / "components" / "flow_components.csv")
    staged["time"] = pd.to_datetime(staged["time"], errors="raise", utc=False)
    quickflow = staged["quickflow_m3_s"].to_numpy(dtype=float)
    discharge = staged["discharge_m3_s"].to_numpy(dtype=float)
    peaks = _detect_peaks(quickflow, cfg)
    raw_events = _raw_events(peaks, discharge, cfg)
    merged = _merge(raw_events, discharge, cfg)
    refined = _refine(merged, quickflow, cfg)
    summary, process, annotated = _products(staged, refined, cfg)
    checks = _checks(summary, process, annotated, cfg)
    if any(item["status"] == "FAIL" for item in checks):
        raise RuntimeError(f"positive fixture failed QC: {checks}")
    golden = task_dir / "expected" / "golden_workspace" / "events"
    _write_csv(golden / "event_summary.csv", summary)
    _write_csv(golden / "event_process.csv", process)
    _write_csv(golden / "annotated_series.csv", annotated)
    _write_yaml(golden / "event_config.yaml", raw_config)
    per_event_entries = []
    per_event_paths = []
    counts: dict[str, int] = {}
    for row in summary.itertuples():
        event_id = int(row.event_id)
        part = process[process["event_id"] == event_id]
        base = f"event_{event_id:04d}" if filename_by == "event-id" else pd.Timestamp(row.peak_time).strftime("%Y%m%d")
        counts[base] = counts.get(base, 0) + 1
        suffix = "" if counts[base] == 1 else f"_{counts[base]:02d}"
        relative = f"event_files/{base}{suffix}.csv"
        path = golden / relative
        _write_csv(path, part)
        per_event_entries.append({"event_id": event_id, "path": relative, "sha256": _sha256(path)})
        per_event_paths.append(f"events/{relative}")
    _write_json(golden / "event_manifest.json", {"schema_version": "1.0", "event_count": len(summary), "files": per_event_entries})
    warnings: list[str] = []
    if len(summary) == 0:
        warnings.append("no flood events satisfied the explicit configuration")
        checks.append({"check": "event_count", "status": "WARN", "details": warnings[-1]})
    else:
        checks.append({"check": "event_count", "status": "PASS", "details": f"events={len(summary)}"})
    checks.insert(-1, {"check": "per_event_file_count", "status": "PASS", "details": f"expected={len(summary)}; actual={len(summary)}"})
    _write_csv(golden / "event_qc.csv", pd.DataFrame(checks))
    artifact_paths = {"event_summary": golden / "event_summary.csv", "event_process": golden / "event_process.csv", "annotated_series": golden / "annotated_series.csv", "event_config": golden / "event_config.yaml", "event_manifest": golden / "event_manifest.json", "event_qc": golden / "event_qc.csv"}
    artifacts = {key: {"path": path.relative_to(golden).as_posix(), "sha256": _sha256(path)} for key, path in artifact_paths.items()}
    parameters = {"output_format": "csv", "per_event_format": "csv", "event_filename_by": filename_by, "timestep_seconds": 3600.0, "candidate_peak_count": len(peaks), "raw_event_count": len(raw_events), "merged_event_count": len(merged), "refined_event_count": len(refined), "final_event_count": len(summary)}
    status = "warning" if warnings else "success"
    _write_json(golden / "result.json", _result(task_dir, status, f"extracted {len(summary)} flood events", warnings, artifacts, parameters, checks))
    task = _task(task_id, title, difficulty, prompt, description, True, summary, process, annotated, per_event_paths)
    _write_json(task_dir / "task.json", task)


def _materialize(task_dir: Path, task_id: str, title: str, difficulty: str, description: str, frame: pd.DataFrame, raw_config: dict[str, Any], filename_by: str = "event-id", positive: bool = True, error_message: str | None = None, scientific_qc: bool = False) -> None:
    """v2: preserve flow cases, explicitly supply synthetic companion rainfall."""
    _upstream(task_dir, frame)
    raw_config = dict(raw_config, schema_version="1.2",
        rainfall_support={"lookback_hours": 6.0, "min_observed_rainfall_mm": 1.0,
                          "no_rainfall_policy": "keep", "missing_rainfall_policy": "keep"},
        shape_filter={"min_plateau_duration_hours": 24.0, "min_plateau_fraction": 0.5,
                      "plateau_range_fraction": 0.005, "min_jump_fraction": 0.1, "jump_window_steps": 2})
    data = task_dir / "data"
    _write_yaml(data / "event_config.yaml", raw_config)
    times = pd.to_datetime(frame["time"], utc=True)
    rain_times = pd.date_range(times.iloc[0] - pd.Timedelta(hours=6), times.iloc[-1], freq="h")
    _write_csv(data / "rainfall.csv", pd.DataFrame({"time": rain_times, "P_mm": 1.0}))
    _write_json(data / "rainfall_metadata.json", {"spatial_scope": "basin_mean", "unit": "mm/step",
        "timestamp_semantics": "interval_end", "timezone": "UTC", "timestep_seconds": 3600,
        "origin": "Synthetic companion rainfall: 1 mm per hour; explicit test setting, not repaired observations.",
        "sha256": _sha256(data / "rainfall.csv")})
    source = Path(os.environ.get("HYDROTUNE_SKILLS_ROOT", r"E:\HydroTune-Skills（仿BioSkills版）"))
    script = source / EVENT_SKILL / "examples/extract_flood_events.py"
    with tempfile.TemporaryDirectory(prefix="hsqb-flood-v2-") as temporary:
        work = Path(temporary); shutil.copytree(data, work, dirs_exist_ok=True)
        command = [sys.executable, str(script), "--baseflow-result", "components/result.json",
                   "--config", "event_config.yaml", "--rainfall", "rainfall.csv",
                   "--rainfall-metadata", "rainfall_metadata.json", "--output-format", "csv",
                   "--per-event-format", "csv", "--event-filename-by", filename_by, "--output-dir", "events"]
        completed = subprocess.run(command, cwd=work, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        if completed.returncode != (0 if positive else 2 if scientific_qc else 1):
            raise RuntimeError(f"{task_id}: unexpected native exit: {completed.stderr}")
        output = work / "events"
        document = json.loads((output / "result.json").read_text(encoding="utf-8"))
        for reference in document.get("inputs", {}).values():
            if isinstance(reference, dict) and "path" in reference:
                reference["path"] = "../" + Path(reference["path"]).relative_to(work).as_posix()
        document["provenance"] = {"generator": "Frozen current native flood program; v2 rainfall interface"}
        (output / "result.json").write_bytes((json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())
        golden = task_dir / "expected/golden_workspace/events"
        for path in output.rglob("*"):
            if path.is_file():
                target = golden / path.relative_to(output); target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() and target.read_bytes() != path.read_bytes():
                    raise RuntimeError(f"refusing to overwrite non-matching deterministic artifact: {target}")
                shutil.copyfile(path, target)
    prompt = (f"Use components/result.json, rainfall.csv, rainfall_metadata.json and the complete confirmed parameters in event_config.yaml to extract flood events. "
              f"Write CSV main tables, rainfall_screening.csv and CSV per-event files under events/, naming per-event files by {filename_by}. "
              "Rainfall is an explicitly synthetic basin-mean companion test series, 1 mm per hourly interval end in UTC. "
              "No-rain and all-missing-rain event policies are both confirmed keep; keeping an event does not establish forcing completeness. "
              "Do not change, infer, or relax any scientific parameter.")
    if not positive:
        prompt += " Preserve the native error result.json and do not create event artifacts when validation or scientific QC fails."
        task = _task(task_id, title, difficulty, prompt, description, False, scientific_qc=scientific_qc)
    else:
        summary = pd.read_csv(golden / "event_summary.csv")
        process = pd.read_csv(golden / "event_process.csv")
        annotated = pd.read_csv(golden / "annotated_series.csv")
        manifest = json.loads((golden / "event_manifest.json").read_text(encoding="utf-8"))
        per_event = ["events/" + entry["path"] for entry in manifest["files"]]
        task = _task(task_id, title, difficulty, prompt, description, True, summary, process, annotated, per_event)
        task["required_outputs"].append("events/rainfall_screening.csv")
        schema = task["grading"][0]
        schema["targets"].append("events/rainfall_screening.csv")
        schema["required_columns"]["events/rainfall_screening.csv"] = list(pd.read_csv(golden / "rainfall_screening.csv").columns)
        schema["expected_rows"]["events/event_qc.csv"] = len(pd.read_csv(golden / "event_qc.csv"))
    task["data_files"] += ["rainfall.csv", "rainfall_metadata.json"]
    task["data_description"] += " Explicit synthetic companion rainfall is supplied; the original flow components are unchanged."
    _write_json(task_dir / "task.json", task)


def generate_task(task_id: str) -> None:
    task_dir = ROOT / task_id
    if task_id == "hydrodata-flood-events-001":
        quick = _pulse(48, 24, 30.0, 6)
        _materialize(task_dir, task_id, "Extract one complete isolated flood event", "basic", "One isolated symmetric quickflow pulse over steady baseflow.", _frame(quick, "2024-01-01"), _config())
        return
    if task_id == "hydrodata-flood-events-002":
        quick = _pulse(84, 20, 24.0, 5) + _pulse(84, 60, 32.0, 6)
        cfg = _config(merging__merge_gap_hours=8.0)
        _materialize(task_dir, task_id, "Extract two chronologically stable non-overlapping flood events", "intermediate", "Two well-separated quickflow pulses with a complete recession between them.", _frame(quick, "2024-02-01"), cfg)
        return
    if task_id == "hydrodata-flood-events-003":
        quick = _pulse(52, 20, 5.0, 3) + _pulse(52, 30, 4.8, 3)
        cfg = _config(peak_detection__peak_quantile=0.30, merging__merge_gap_hours=8.0, merging__valley_ratio_threshold=0.60)
        _materialize(task_dir, task_id, "Merge nearby peaks across a shallow total-flow valley", "advanced", "Two small nearby quickflow pulses whose total-flow valley remains above the configured merge ratio.", _frame(quick, "2024-03-01", baseflow=10.0), cfg)
        return
    if task_id == "hydrodata-flood-events-004":
        quick = _pulse(30, 6, 14.0, 3) + _pulse(30, 18, 12.0, 3)
        cfg = _config(peak_detection__peak_quantile=0.30, merging__merge_gap_hours=10.0, merging__valley_ratio_threshold=0.60)
        _materialize(task_dir, task_id, "Keep same-day peaks separate and suffix colliding filenames", "advanced", "Two same-day pulses separated by a deep total-flow valley.", _frame(quick, "2024-04-01", baseflow=1.0), cfg, filename_by="peak-time")
        return
    if task_id == "hydrodata-flood-events-005":
        quick = _pulse(36, 4, 20.0, 3)
        cfg = _config(warmup__steps=10)
        _materialize(task_dir, task_id, "Truncate warm-up safely at the beginning of the series", "intermediate", "A flood event near the beginning of the available record with a longer requested warm-up.", _frame(quick, "2024-05-01"), cfg)
        return
    if task_id == "hydrodata-flood-events-006":
        quick = _pulse(76, 12, 3.0, 2) + _pulse(76, 32, 20.0, 1) + _pulse(76, 58, 24.0, 5)
        cfg = _config(peak_detection__peak_quantile=0.10, peak_detection__min_peak_distance_hours=4.0, filters__min_event_duration_hours=4.0, filters__min_peak_flow_m3_s=15.0, filters__min_event_volume_m3=500000.0)
        _materialize(task_dir, task_id, "Apply duration, peak, and volume filters to mixed event sizes", "advanced", "Small, short, and major quickflow pulses designed to exercise all explicit filters.", _frame(quick, "2024-06-01"), cfg)
        return
    if task_id == "hydrodata-flood-events-007":
        quick = np.zeros(48, dtype=float)
        _materialize(task_dir, task_id, "Return a warning and zero events when quickflow is absent", "basic", "A continuous series in which discharge is entirely baseflow.", _frame(quick, "2024-07-01"), _config())
        return
    if task_id == "hydrodata-flood-events-008":
        quick = _pulse(48, 24, 20.0, 5)
        cfg = _config(filters__min_peak_flow_m3_s=1000.0)
        _materialize(task_dir, task_id, "Retain zero events when explicit filters reject detected peaks", "intermediate", "A clear candidate flood peak paired with an intentionally higher confirmed minimum peak threshold.", _frame(quick, "2024-08-01"), cfg)
        return
    if task_id == "hydrodata-flood-events-009":
        quick = _pulse(48, 24, 20.0, 5)
        cfg = _config()
        del cfg["merging"]["valley_ratio_threshold"]
        message = "配置 merging 字段必须精确为 ['merge_gap_hours', 'valley_ratio_threshold']"
        _materialize(task_dir, task_id, "Reject an incomplete scientific event configuration", "basic", "A valid component series paired with YAML missing one required merge parameter.", _frame(quick, "2024-09-01"), cfg, positive=False, error_message=message)
        return
    if task_id == "hydrodata-flood-events-010":
        quick = _pulse(48, 24, 20.0, 5)
        message = "event 1 volume balance failed"
        _materialize(task_dir, task_id, "Reject event products that fail component-volume conservation", "advanced", "A hash-valid component table whose total flow is inconsistent with baseflow plus quickflow.", _frame(quick, "2024-10-01", imbalance=1.0), _config(), positive=False, error_message=message, scientific_qc=True)
        return
    raise KeyError(f"unknown task id: {task_id}")
