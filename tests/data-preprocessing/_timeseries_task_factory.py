"""Deterministic fixtures for prepare-discharge-timeseries benchmark tasks."""

from __future__ import annotations

from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
SKILL = "data-processing/prepare-discharge-timeseries"
CFS_TO_M3_S = 0.028316846592


def _json_safe(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
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
    text = json.dumps(_json_safe(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _write_text(path, text)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, lineterminator="\n", float_format="%.12g")
    _write_text(path, buffer.getvalue())


def _write_xlsx(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    if path.exists():
        existing = pd.read_excel(path, sheet_name=None)
        if list(existing) != list(sheets):
            raise RuntimeError(f"refusing to overwrite non-matching deterministic artifact: {path}")
        for name, expected in sheets.items():
            pd.testing.assert_frame_equal(existing[name], expected, check_dtype=False)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        writer.book.set_properties({"created": datetime(2024, 1, 1), "modified": datetime(2024, 1, 1)})
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _metadata(
    *,
    time_column: str,
    flow_column: str,
    source_format: str,
    source_unit: str,
    unit_scale: float,
    timezone: str,
    timestep_seconds: float,
    output: pd.DataFrame,
    extras: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "time_column": time_column,
        "flow_column": flow_column,
        "source_format": source_format,
        "source_flow_unit": source_unit,
        "standard_flow_unit": "m3/s",
        "unit_scale": unit_scale,
        "timezone": timezone,
        "timestep_seconds": timestep_seconds,
        "time_regularity": 1.0,
        "row_count": len(output),
        "start_time": output["time"].iloc[0],
        "end_time": output["time"].iloc[-1],
        "additional_columns": extras,
        "additional_column_semantics": "unconfirmed",
    }


def _result(
    *,
    task_dir: Path,
    status: str,
    message: str,
    warnings: list[str],
    artifacts: bool,
) -> dict[str, Any]:
    prepared = task_dir / "expected" / "golden_workspace" / "prepared"
    artifact_map: dict[str, Any] = {}
    if artifacts:
        artifact_map = {
            "discharge_timeseries": {
                "path": "discharge_timeseries.csv",
                "sha256": _sha256(prepared / "discharge_timeseries.csv"),
            },
            "series_metadata": {
                "path": "series_metadata.json",
                "sha256": _sha256(prepared / "series_metadata.json"),
            },
        }
    return {
        "schema_version": "1.0",
        "skill": SKILL,
        "status": status,
        "message": message,
        "parameters": {},
        "inputs": {},
        "artifacts": artifact_map,
        "checks": [],
        "warnings": warnings,
        "provenance": {"generator": "HSQB deterministic oracle"},
    }


def _positive_grading(columns: list[str], expected_rows: int) -> list[dict[str, Any]]:
    golden = "expected/golden_workspace/prepared"
    metadata_target = "prepared/series_metadata.json"
    result_target = "prepared/result.json"
    return [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": ["prepared/discharge_timeseries.csv", metadata_target, result_target],
            "required_columns": {
                "prepared/discharge_timeseries.csv": columns,
                metadata_target: ["source_flow_unit", "standard_flow_unit", "timezone", "timestep_seconds", "row_count"],
                result_target: ["skill", "status", "message", "artifacts", "warnings"],
            },
            "expected_rows": {"prepared/discharge_timeseries.csv": expected_rows, metadata_target: 1, result_target: 1},
            "weight": 0.10,
        },
        {
            "name": "prepared_table",
            "type": "table_match",
            "target": "prepared/discharge_timeseries.csv",
            "reference": f"{golden}/discharge_timeseries.csv",
            "columns": columns,
            "datetime_columns": ["time"],
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.55,
        },
        *[
            {
                "name": f"metadata_{field}",
                "type": "exact_match",
                "target": metadata_target,
                "field": field,
                "reference": f"{golden}/series_metadata.json",
                "weight": 0.04,
            }
            for field in ("source_flow_unit", "standard_flow_unit", "timezone", "timestep_seconds", "row_count")
        ],
        {
            "name": "result_skill",
            "type": "exact_match",
            "target": result_target,
            "field": "skill",
            "reference": f"{golden}/result.json",
            "weight": 0.03,
        },
        {
            "name": "result_status",
            "type": "exact_match",
            "target": result_target,
            "field": "status",
            "reference": f"{golden}/result.json",
            "weight": 0.07,
        },
        {
            "name": "result_warnings",
            "type": "exact_match",
            "target": result_target,
            "field": "warnings",
            "reference": f"{golden}/result.json",
            "weight": 0.05,
        },
    ]


def _negative_grading() -> list[dict[str, Any]]:
    golden = "expected/golden_workspace/prepared/result.json"
    target = "prepared/result.json"
    return [
        {
            "name": "result_schema",
            "type": "file_check",
            "target": target,
            "required_columns": ["skill", "status", "message", "artifacts", "warnings"],
            "expected_rows": {target: 1},
            "weight": 0.15,
        },
        {"name": "result_skill", "type": "exact_match", "target": target, "field": "skill", "reference": golden, "weight": 0.10},
        {"name": "result_status", "type": "exact_match", "target": target, "field": "status", "reference": golden, "weight": 0.25},
        {"name": "failure_reason", "type": "exact_match", "target": target, "field": "message", "reference": golden, "weight": 0.25},
        {"name": "empty_artifacts", "type": "exact_match", "target": target, "field": "artifacts", "reference": golden, "weight": 0.10},
        {
            "name": "no_standard_outputs",
            "type": "file_absence_check",
            "targets": [
                "prepared/discharge_timeseries.csv",
                "prepared/discharge_timeseries.parquet",
                "prepared/discharge_timeseries.xlsx",
                "prepared/series_metadata.json",
            ],
            "weight": 0.15,
        },
    ]


def _task_document(
    *,
    task_id: str,
    title: str,
    difficulty: str,
    prompt: str,
    description: str,
    input_name: str,
    positive: bool,
    columns: list[str] | None = None,
    expected_rows: int | None = None,
) -> dict[str, Any]:
    required = ["prepared/result.json"]
    if positive:
        required = ["prepared/discharge_timeseries.csv", "prepared/series_metadata.json", *required]
    return {
        "id": task_id,
        "title": title,
        "domain": "data-preprocessing",
        "difficulty": difficulty,
        "primary_skill": SKILL,
        "secondary_skills": [],
        "prompt": prompt,
        "data_description": description,
        "data_files": [input_name],
        "required_outputs": required,
        "setup_notes": [
            "Python, NumPy, pandas, SciPy, openpyxl, and xlsxwriter are available.",
            "Write all outputs under prepared/. Always preserve the native prepare-discharge-timeseries result.json, including for rejected inputs.",
        ],
        "timeout_seconds": 300,
        "grading": _positive_grading(columns or [], int(expected_rows or 0)) if positive else _negative_grading(),
    }


def _write_positive(
    task_dir: Path,
    *,
    task: dict[str, Any],
    input_name: str,
    source: pd.DataFrame | None,
    output: pd.DataFrame,
    metadata: dict[str, Any],
    status: str,
    warnings: list[str],
    xlsx_sheets: dict[str, pd.DataFrame] | None = None,
) -> None:
    _write_json(task_dir / "task.json", task)
    if xlsx_sheets is not None:
        _write_xlsx(task_dir / "data" / input_name, xlsx_sheets)
    elif source is not None:
        _write_csv(task_dir / "data" / input_name, source)
    prepared = task_dir / "expected" / "golden_workspace" / "prepared"
    _write_csv(prepared / "discharge_timeseries.csv", output)
    _write_json(prepared / "series_metadata.json", metadata)
    message = "discharge time series prepared" if status == "success" else "discharge time series prepared with warnings"
    _write_json(prepared / "result.json", _result(task_dir=task_dir, status=status, message=message, warnings=warnings, artifacts=True))


def _write_negative(
    task_dir: Path,
    *,
    task: dict[str, Any],
    input_name: str,
    source: pd.DataFrame,
    message: str,
) -> None:
    _write_json(task_dir / "task.json", task)
    _write_csv(task_dir / "data" / input_name, source)
    prepared = task_dir / "expected" / "golden_workspace" / "prepared"
    _write_json(prepared / "result.json", _result(task_dir=task_dir, status="error", message=message, warnings=[], artifacts=False))


def _base_output(time: pd.Series | pd.DatetimeIndex, discharge: Any, **extras: Any) -> pd.DataFrame:
    frame = pd.DataFrame({"time": time, "discharge_m3_s": np.asarray(discharge, dtype=float), "is_imputed": False})
    for name, values in extras.items():
        frame[name] = values
    return frame


def generate_task(task_id: str) -> None:
    task_dir = ROOT / task_id
    if task_id == "hydrodata-timeseries-001":
        times = pd.date_range("2024-01-01", periods=24, freq="h", tz="UTC")
        flows = 45.0 + np.arange(24) * 1.75
        source_ids = [f"sample-{index:02d}" for index in range(24)]
        source = pd.DataFrame({"observed_at": times.strftime("%Y-%m-%dT%H:%M:%SZ"), "flow_cfs": flows, "source_id": source_ids})
        source = source.sample(frac=1.0, random_state=20260921).reset_index(drop=True)
        local_times = times.tz_convert("Asia/Shanghai")
        output = _base_output(local_times, flows * CFS_TO_M3_S, source_id=source_ids)
        metadata = _metadata(time_column="observed_at", flow_column="flow_cfs", source_format="csv", source_unit="cfs", unit_scale=CFS_TO_M3_S, timezone="Asia/Shanghai", timestep_seconds=3600.0, output=output, extras=["source_id"])
        prompt = "Prepare flow_cfs from shuffled_flow.csv as a continuous discharge series. observed_at is the confirmed instantaneous time column, flow_cfs is confirmed in cfs, and the required timezone is Asia/Shanghai. Do not assign hydrologic meaning to source_id, but preserve it row by row. Missing and duplicate timestamps must use the default error policies. Write CSV outputs under prepared/."
        task = _task_document(task_id=task_id, title="Standardize shuffled cfs discharge with timezone conversion", difficulty="intermediate", prompt=prompt, description="Shuffled hourly UTC discharge observations in cfs with an unconfirmed identifier column.", input_name="shuffled_flow.csv", positive=True, columns=list(output.columns), expected_rows=len(output))
        _write_positive(task_dir, task=task, input_name="shuffled_flow.csv", source=source, output=output, metadata=metadata, status="success", warnings=[])
        return

    if task_id == "hydrodata-timeseries-002":
        times = pd.date_range("2024-02-01", periods=12, freq="D")
        serial = (times - pd.Timestamp("1899-12-30")) / pd.Timedelta(days=1)
        flows = 1250.0 + np.arange(12) * 37.5
        quality = ["A" if index % 3 else "B" for index in range(12)]
        observations = pd.DataFrame({"serial_date": serial.astype(float), "flow_l_s": flows, "quality_code": quality})
        decoy = pd.DataFrame({"note": ["Use the observations sheet; this sheet is not data."]})
        output = _base_output(times, flows * 0.001, quality_code=quality)
        metadata = _metadata(time_column="serial_date", flow_column="flow_l_s", source_format="xlsx", source_unit="L/s", unit_scale=0.001, timezone="naive", timestep_seconds=86400.0, output=output, extras=["quality_code"])
        prompt = "Prepare the observations sheet from serial_dates.xlsx. serial_date is the confirmed instantaneous time column using Excel serial dates, flow_l_s is confirmed in L/s, and timezone is explicitly naive. Preserve quality_code without assigning semantics. Use default error policies and write CSV outputs under prepared/."
        task = _task_document(task_id=task_id, title="Read Excel serial dates from a named worksheet", difficulty="intermediate", prompt=prompt, description="An XLSX workbook with a decoy first sheet and valid daily observations in a named sheet.", input_name="serial_dates.xlsx", positive=True, columns=list(output.columns), expected_rows=len(output))
        _write_positive(task_dir, task=task, input_name="serial_dates.xlsx", source=None, output=output, metadata=metadata, status="warning", warnings=["timezone explicitly recorded as naive"], xlsx_sheets={"README": decoy, "observations": observations})
        return

    if task_id == "hydrodata-timeseries-003":
        times = pd.date_range("2024-03-01", periods=18, freq="h")
        flows = 10.0 + np.arange(18) * 2.0
        source_flows = flows.copy()
        source_flows[[6, 7]] = np.nan
        source = pd.DataFrame({"timestamp": times, "discharge": source_flows})
        output = _base_output(times, flows)
        output.loc[[6, 7], "is_imputed"] = True
        metadata = _metadata(time_column="timestamp", flow_column="discharge", source_format="csv", source_unit="m3/s", unit_scale=1.0, timezone="UTC", timestep_seconds=3600.0, output=output, extras=[])
        prompt = "Prepare discharge from bounded_gap.csv. timestamp is the confirmed instantaneous time column, discharge is confirmed in m3/s, and timezone is UTC. Explicitly interpolate internal gaps up to 2 hours; edge missing and duplicate timestamps must error. Write CSV outputs under prepared/."
        task = _task_document(task_id=task_id, title="Interpolate an internal gap exactly at the authorized limit", difficulty="intermediate", prompt=prompt, description="Regular hourly discharge with one two-step internal gap.", input_name="bounded_gap.csv", positive=True, columns=list(output.columns), expected_rows=len(output))
        _write_positive(task_dir, task=task, input_name="bounded_gap.csv", source=source, output=output, metadata=metadata, status="warning", warnings=["interpolated interior discharge values=2"])
        return

    if task_id == "hydrodata-timeseries-004":
        times = pd.date_range("2024-04-01", periods=18, freq="h")
        flows = 20.0 + np.arange(18) * 0.75
        source_flows = flows.copy()
        source_flows[[0, 1, 15, 16, 17]] = np.nan
        states = [f"state-{index:02d}" for index in range(18)]
        source = pd.DataFrame({"time_recorded": times, "q": source_flows, "sensor_state": states})
        output = _base_output(times[2:15], flows[2:15], sensor_state=states[2:15])
        metadata = _metadata(time_column="time_recorded", flow_column="q", source_format="csv", source_unit="m3/s", unit_scale=1.0, timezone="UTC", timestep_seconds=3600.0, output=output, extras=["sensor_state"])
        prompt = "Prepare q from edge_missing.csv. time_recorded is the confirmed instantaneous time column, q is confirmed in m3/s, and timezone is UTC. Explicitly trim leading and trailing missing discharge; do not extrapolate. Interior missing and duplicates must error. Preserve sensor_state without interpreting it. Write CSV outputs under prepared/."
        task = _task_document(task_id=task_id, title="Trim leading and trailing discharge gaps without extrapolation", difficulty="intermediate", prompt=prompt, description="Hourly discharge with missing values only at both series edges.", input_name="edge_missing.csv", positive=True, columns=list(output.columns), expected_rows=len(output))
        _write_positive(task_dir, task=task, input_name="edge_missing.csv", source=source, output=output, metadata=metadata, status="warning", warnings=["trimmed edge missing rows=5"])
        return

    if task_id == "hydrodata-timeseries-005":
        times = pd.date_range("2024-05-01", periods=14, freq="h")
        flows = 30.0 + np.arange(14)
        rows = []
        for index, (timestamp, flow) in enumerate(zip(times, flows, strict=True)):
            rows.append({"timestamp": timestamp, "flow": flow, "sample_id": f"original-{index:02d}"})
            if index == 6:
                rows.append({"timestamp": timestamp, "flow": 99.0, "sample_id": "replacement-06"})
        source = pd.DataFrame(rows)
        expected_flows = flows.copy()
        expected_flows[6] = 99.0
        ids = [f"original-{index:02d}" for index in range(14)]
        ids[6] = "replacement-06"
        output = _base_output(times, expected_flows, sample_id=ids)
        metadata = _metadata(time_column="timestamp", flow_column="flow", source_format="csv", source_unit="m3/s", unit_scale=1.0, timezone="UTC", timestep_seconds=3600.0, output=output, extras=["sample_id"])
        prompt = "Prepare flow from duplicate_last.csv. timestamp is the confirmed instantaneous time column, flow is confirmed in m3/s, and timezone is UTC. Resolve duplicate timestamps by retaining the last occurrence in file order. Missing values must error. Preserve sample_id without interpreting it. Write CSV outputs under prepared/."
        task = _task_document(task_id=task_id, title="Resolve duplicate discharge timestamps by keeping the last row", difficulty="intermediate", prompt=prompt, description="Hourly discharge with one duplicated timestamp whose second row is the authorized value.", input_name="duplicate_last.csv", positive=True, columns=list(output.columns), expected_rows=len(output))
        _write_positive(task_dir, task=task, input_name="duplicate_last.csv", source=source, output=output, metadata=metadata, status="warning", warnings=["duplicate timestamps resolved with policy=last; affected_rows=2"])
        return

    negative_specs: dict[str, tuple[str, str, str, pd.DataFrame, str, str]] = {}
    times = pd.date_range("2024-06-01", periods=14, freq="h")
    duplicate_rows = pd.DataFrame({"timestamp": list(times[:6]) + [times[5]] + list(times[6:]), "flow": list(40.0 + np.arange(6)) + [88.0] + list(46.0 + np.arange(8))})
    negative_specs["hydrodata-timeseries-006"] = ("Reject duplicate timestamps without an authorized policy", "basic", "duplicate_error.csv", duplicate_rows, "发现 2 行重复时间", "Duplicate hourly timestamp with no authorized resolution policy.")
    gap_flows = 50.0 + np.arange(16, dtype=float)
    gap_flows[[5, 6, 7]] = np.nan
    gap = pd.DataFrame({"timestamp": pd.date_range("2024-07-01", periods=16, freq="h"), "flow": gap_flows})
    negative_specs["hydrodata-timeseries-007"] = ("Reject an internal gap longer than the interpolation limit", "intermediate", "overlong_gap.csv", gap, "内部缺口超过允许长度: [(5, 7)]", "Regular hourly discharge with a three-step internal gap and a two-hour interpolation limit.")
    irregular_times = list(pd.date_range("2024-08-01", periods=20, freq="h"))
    irregular_times[10] = irregular_times[10] + pd.Timedelta(minutes=30)
    irregular = pd.DataFrame({"timestamp": irregular_times, "flow": 60.0 + np.arange(20)})
    negative_specs["hydrodata-timeseries-008"] = ("Reject an irregular discharge time axis", "intermediate", "irregular_time.csv", irregular, "时间序列不规则，规则度=89.474%", "Mostly hourly discharge with one shifted timestamp producing 90- and 30-minute steps.")
    negative_flows = 70.0 + np.arange(14, dtype=float)
    negative_flows[8] = -2.5
    negative = pd.DataFrame({"timestamp": pd.date_range("2024-09-01", periods=14, freq="h"), "flow": negative_flows})
    negative_specs["hydrodata-timeseries-009"] = ("Reject negative discharge observations", "basic", "negative_flow.csv", negative, "发现负流量", "Regular hourly discharge containing one negative observation.")
    nonnumeric_values: list[Any] = list(80.0 + np.arange(14))
    nonnumeric_values[6] = "sensor_error"
    nonnumeric = pd.DataFrame({"timestamp": pd.date_range("2024-10-01", periods=14, freq="h"), "flow": nonnumeric_values})
    negative_specs["hydrodata-timeseries-010"] = ("Reject non-numeric discharge without interpolation authority", "basic", "nonnumeric_flow.csv", nonnumeric, "存在 1 个内部流量缺测", "Regular hourly discharge with one non-numeric internal value.")
    bad_times = [timestamp.isoformat() for timestamp in pd.date_range("2024-11-01", periods=14, freq="h")]
    bad_times[4] = "not-a-date"
    unparseable = pd.DataFrame({"timestamp": bad_times, "flow": 90.0 + np.arange(14)})
    negative_specs["hydrodata-timeseries-011"] = ("Reject an unparseable discharge timestamp", "basic", "bad_time.csv", unparseable, "存在 1 个无法解析的时间值", "Hourly discharge containing one unparseable timestamp string.")
    short = pd.DataFrame({"timestamp": pd.date_range("2024-12-01", periods=9, freq="h"), "flow": 100.0 + np.arange(9)})
    negative_specs["hydrodata-timeseries-012"] = ("Reject a discharge series with fewer than ten valid points", "basic", "short_series.csv", short, "有效数据点少于 10 个", "A regular discharge series containing only nine valid observations.")

    if task_id not in negative_specs:
        raise KeyError(f"unknown task id: {task_id}")
    title, difficulty, input_name, source, message, description = negative_specs[task_id]
    policy_by_id = {
        "hydrodata-timeseries-006": "Use the default duplicate error policy; do not choose first, last, or aggregation.",
        "hydrodata-timeseries-007": "Interpolation is authorized only for internal gaps up to 2 hours; do not partially fill a longer gap.",
        "hydrodata-timeseries-008": "Do not resample, interpolate timestamps, or split the series.",
        "hydrodata-timeseries-009": "Do not delete, clip, replace, or otherwise repair negative discharge.",
        "hydrodata-timeseries-010": "Use the default missing-value error policy; interpolation is not authorized.",
        "hydrodata-timeseries-011": "Do not drop the bad row or guess its date.",
        "hydrodata-timeseries-012": "Do not pad, duplicate, or synthesize observations.",
    }
    prompt = f"Inspect {input_name} using timestamp as the confirmed instantaneous time column and flow as discharge confirmed in m3/s with timezone UTC. {policy_by_id[task_id]} Write the native error result to prepared/result.json and do not create a standardized time series or metadata when the contract rejects the input."
    task = _task_document(task_id=task_id, title=title, difficulty=difficulty, prompt=prompt, description=description, input_name=input_name, positive=False)
    _write_negative(task_dir, task=task, input_name=input_name, source=source, message=message)

