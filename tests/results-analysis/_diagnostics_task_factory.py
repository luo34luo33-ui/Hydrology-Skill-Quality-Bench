"""Deterministic fixtures for evaluation-diagnostics benchmark tasks.

Covers three capabilities of the results-analysis domain:

- ``hydroanalysis-event-metrics-001..003``  -> compute-event-flood-metrics
- ``hydroanalysis-series-metrics-001..003`` -> compute-continuous-series-metrics
- ``hydroanalysis-aggregate-metrics-001..003`` -> aggregate-event-metrics
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
DEFAULT_SKILLS_ROOT = Path(r"E:\HydroTune-Skills（仿BioSkills版）")

CAPABILITIES: dict[str, dict[str, Any]] = {
    "event-metrics": {
        "skill": "evaluation-diagnostics/compute-event-flood-metrics",
        "folder": "evaluation-diagnostics/compute-event-flood-metrics",
        "script": "compute_event_metrics.py",
        "output": "event-metrics",
        "table": "event_metrics.csv",
        "artifact": "event_metrics",
    },
    "series-metrics": {
        "skill": "evaluation-diagnostics/compute-continuous-series-metrics",
        "folder": "evaluation-diagnostics/compute-continuous-series-metrics",
        "script": "compute_series_metrics.py",
        "output": "series-metrics",
        "table": "series_metrics.csv",
        "artifact": "series_metrics",
    },
    "aggregate-metrics": {
        "skill": "evaluation-diagnostics/aggregate-event-metrics",
        "folder": "evaluation-diagnostics/aggregate-event-metrics",
        "script": "aggregate_event_metrics.py",
        "output": "aggregate-metrics",
        "table": "aggregate_metrics.csv",
        "artifact": "aggregate_metrics",
    },
}

TASK_IDS = [
    f"hydroanalysis-event-metrics-{index:03d}" for index in (1, 2, 3)
] + [
    f"hydroanalysis-series-metrics-{index:03d}" for index in (1, 2, 3)
] + [
    f"hydroanalysis-aggregate-metrics-{index:03d}" for index in (1, 2, 3)
]


def _capability(task_id: str) -> str:
    stem = task_id.removeprefix("hydroanalysis-").rsplit("-", 1)[0]
    if stem not in CAPABILITIES:
        raise ValueError(f"unsupported diagnostics task id: {task_id}")
    return stem


def _index(task_id: str) -> int:
    return int(task_id.rsplit("-", 1)[1])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_bytes(path: Path, content: bytes) -> None:
    if path.exists() and path.read_bytes() != content:
        raise RuntimeError(f"refusing to overwrite non-matching deterministic artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_json(path: Path, value: Any) -> None:
    _write_bytes(path, _stable_json(value))


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = frame.to_csv(
        index=False,
        float_format="%.12g",
        lineterminator="\n",
        encoding="utf-8",
        date_format="%Y-%m-%d %H:%M:%S",
    ).encode("utf-8")
    _write_bytes(path, content)


def _skill_script(capability: str) -> Path:
    configured = os.environ.get("HYDROTUNE_SKILLS_ROOT", "").strip().strip('"')
    skills_root = Path(configured) if configured else DEFAULT_SKILLS_ROOT
    meta = CAPABILITIES[capability]
    script = skills_root / meta["folder"] / "examples" / meta["script"]
    if not script.is_file():
        raise FileNotFoundError(f"diagnostics skill script not found: {script}")
    return script


def _hydrograph(steps: int, base: float, amp: float, peak: float, width: float) -> np.ndarray:
    t = np.arange(steps, dtype=float)
    return base + amp * np.exp(-(((t - peak) / width) ** 2))


def _event_frame(event_id: str, day: str, observed: np.ndarray, simulated: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": pd.date_range(day, periods=len(observed), freq="h"),
            "event_id": event_id,
            "Q_obs": observed,
            "Q_total": simulated,
        }
    )


def _thresholds() -> dict[str, float]:
    return {"relative_volume_error": 0.2, "relative_peak_error": 0.2, "peak_time_error_hours": 3.0}


def _event_data(task_id: str) -> dict[str, pd.DataFrame]:
    if task_id == "hydroanalysis-event-metrics-001":
        observed_1 = _hydrograph(24, 20.0, 60.0, 10.0, 4.0)
        simulated_1 = observed_1 * 1.02
        observed_2 = _hydrograph(24, 15.0, 80.0, 8.0, 5.0)
        simulated_2 = observed_2 * 0.65
        observed_3 = _hydrograph(24, 18.0, 70.0, 12.0, 5.0)
        simulated_3 = np.concatenate([np.full(5, observed_3[0]), observed_3[:-5]]) + 0.4 * np.sin(np.arange(24) * 1.7)
        return {
            "events/event_01.csv": _event_frame("event_01", "2024-07-01", observed_1, simulated_1),
            "events/event_02.csv": _event_frame("event_02", "2024-07-05", observed_2, simulated_2),
            "events/event_03.csv": _event_frame("event_03", "2024-07-09", observed_3, simulated_3),
        }
    if task_id == "hydroanalysis-event-metrics-002":
        t = np.arange(24, dtype=float)
        observed_1 = 20.0 + 50.0 * np.exp(-(((t - 8.0) / 2.5) ** 2)) + 50.0 * np.exp(-(((t - 16.0) / 2.5) ** 2))
        simulated_1 = observed_1 * 1.01
        observed_2 = _hydrograph(24, 22.0, 65.0, 9.0, 4.5)
        simulated_2 = observed_2 * 0.97 + 0.3 * np.sin(t)
        return {
            "events/event_01.csv": _event_frame("event_01", "2024-07-01", observed_1, simulated_1),
            "events/event_02.csv": _event_frame("event_02", "2024-07-05", observed_2, simulated_2),
        }
    if task_id == "hydroanalysis-event-metrics-003":
        observed_1 = _hydrograph(24, 20.0, 60.0, 10.0, 4.0)
        simulated_1 = observed_1 * 1.02
        observed_2 = _hydrograph(24, 15.0, 80.0, 8.0, 5.0)
        observed_2 = observed_2.copy()
        observed_2[12] = np.nan
        simulated_2 = observed_2 * 0.9
        return {
            "events/event_01.csv": _event_frame("event_01", "2024-07-01", observed_1, simulated_1),
            "events/event_02.csv": _event_frame("event_02", "2024-07-05", observed_2, simulated_2),
        }
    raise ValueError(f"unsupported diagnostics task id: {task_id}")


def _series_data(task_id: str) -> pd.DataFrame:
    t = np.arange(96, dtype=float)
    if task_id == "hydroanalysis-series-metrics-001":
        observed = 25.0 + 90.0 * np.exp(-(((t - 40.0) / 12.0) ** 2)) + 8.0 * np.sin(t * 1.3)
        simulated = np.concatenate([[observed[0]], observed[:-1]]) * 1.05 + 0.8
        return pd.DataFrame(
            {
                "time": pd.date_range("2024-09-01 00:00", periods=96, freq="h"),
                "Q_obs": observed,
                "Q_total": simulated,
            }
        )
    if task_id == "hydroanalysis-series-metrics-002":
        observed = np.full(96, 50.0)
        simulated = 47.0 + 1.5 * np.sin(t / 3.0)
        return pd.DataFrame(
            {
                "time": pd.date_range("2024-09-01 00:00", periods=96, freq="h"),
                "Q_obs": observed,
                "Q_total": simulated,
            }
        )
    if task_id == "hydroanalysis-series-metrics-003":
        observed = 25.0 + 90.0 * np.exp(-(((t - 40.0) / 12.0) ** 2)) + 8.0 * np.sin(t * 1.3)
        simulated = np.concatenate([[observed[0]], observed[:-1]]) * 1.05 + 0.8
        simulated[40] = np.nan
        return pd.DataFrame(
            {
                "time": pd.date_range("2024-09-01 00:00", periods=96, freq="h"),
                "Q_obs": observed,
                "Q_total": simulated,
            }
        )
    raise ValueError(f"unsupported diagnostics task id: {task_id}")


def _aggregate_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_id": ["event_01", "event_02", "event_03", "event_04", "event_05", "event_06"],
            "catchment": ["upstream", "upstream", "upstream", "downstream", "downstream", "downstream"],
            "nse": [0.85, 0.62, 0.41, 0.78, 0.55, 0.66],
            "volume_error_relative": [0.05, 0.12, 0.35, 0.08, 0.25, 0.11],
            "peak_error_relative": [0.03, 0.18, 0.10, 0.22, 0.06, 0.15],
            "qualified_volume": ["是", "是", "否", "是", "否", "是"],
            "qualified_peak": ["是", "是", "是", "否", "是", "是"],
        }
    )


def _empty_aggregate_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_id": pd.Series([], dtype=object),
            "nse": pd.Series([], dtype=float),
            "volume_error_relative": pd.Series([], dtype=float),
        }
    )


def _data_frames(task_id: str) -> dict[str, pd.DataFrame]:
    capability = _capability(task_id)
    if capability == "event-metrics":
        return _event_data(task_id)
    if capability == "series-metrics":
        return {"series.csv": _series_data(task_id)}
    if task_id == "hydroanalysis-aggregate-metrics-002":
        return {"event_metrics.csv": _empty_aggregate_table()}
    return {"event_metrics.csv": _aggregate_table()}


def _extra_files(task_id: str) -> dict[str, dict[str, Any]]:
    capability = _capability(task_id)
    if capability == "event-metrics":
        return {"thresholds.json": _thresholds()}
    if task_id == "hydroanalysis-aggregate-metrics-001":
        return {"thresholds.json": {"qualified_volume": 0.2, "qualified_peak": 0.2}}
    return {}


def _golden_command(task_id: str) -> tuple[list[str], int]:
    capability = _capability(task_id)
    index = _index(task_id)
    meta = CAPABILITIES[capability]
    args = [sys.executable, str(_skill_script(capability))]
    if capability == "event-metrics":
        args += ["--events-dir", "events", "--timestep-hours", "1", "--thresholds", "thresholds.json"]
    elif capability == "series-metrics":
        args += ["--series", "series.csv", "--timestep-hours", "1"]
    else:
        args += ["--metrics-table", "event_metrics.csv", "--value-columns", "nse,volume_error_relative"]
        if index == 1:
            args += ["--group-by", "catchment", "--pass-columns", "qualified_volume,qualified_peak", "--pass-thresholds", "thresholds.json"]
        if index == 3:
            args += ["--statistics", "mean,p25"]
    args += ["--output-format", "csv"]
    expected_code = 0 if index < 3 else (2 if capability != "aggregate-metrics" else 1)
    return args, expected_code


def _titles() -> dict[str, str]:
    return {
        "hydroanalysis-event-metrics-001": "Score three flood events against confirmed qualification thresholds",
        "hydroanalysis-event-metrics-002": "Resolve tied flood peaks at the first maximum with a native warning",
        "hydroanalysis-event-metrics-003": "Reject event metrics when one event contains missing observations",
        "hydroanalysis-series-metrics-001": "Compute the full continuous series metric set with explicit timestep",
        "hydroanalysis-series-metrics-002": "Report NSE as unavailable for a constant observed series",
        "hydroanalysis-series-metrics-003": "Reject series metrics when the input contains missing values",
        "hydroanalysis-aggregate-metrics-001": "Aggregate event metrics by catchment with qualification rates",
        "hydroanalysis-aggregate-metrics-002": "Aggregate an empty metrics table into a warned empty result",
        "hydroanalysis-aggregate-metrics-003": "Reject an aggregate run that requests an unknown statistic",
    }


def _prompts() -> dict[str, str]:
    return {
        "hydroanalysis-event-metrics-001": (
            "Use the three event tables under events/ exactly as supplied to run evaluation-diagnostics/compute-event-flood-metrics. "
            "Every event has hourly time, Q_obs, and Q_total columns in m3/s; the timestep is 1 h. "
            "Use the confirmed thresholds.json (relative_volume_error=0.2, relative_peak_error=0.2, peak_time_error_hours=3.0) and keep the "
            "default error sign convention (observed minus simulated; simulated minus observed for peak time). "
            "Write the native outputs (event_metrics.csv, result.json) under event-metrics/. "
            "Do not invent thresholds, flip error signs, or fill missing values."
        ),
        "hydroanalysis-event-metrics-002": (
            "Use the two event tables under events/ exactly as supplied to run evaluation-diagnostics/compute-event-flood-metrics. "
            "Event 01 deliberately contains tied observed and simulated peaks; run the skill verbatim with --timestep-hours 1 and the "
            "confirmed thresholds.json. Keep the native tie handling (first maximum wins) and preserve the native warnings in result.json. "
            "Write the native outputs (event_metrics.csv, result.json) under event-metrics/. "
            "Do not perturb the series to break the tie or suppress the warning."
        ),
        "hydroanalysis-event-metrics-003": (
            "Use the two event tables under events/ exactly as supplied to run evaluation-diagnostics/compute-event-flood-metrics. "
            "Event 02 contains missing Q_obs values; run the skill verbatim with --timestep-hours 1 and thresholds.json. "
            "The native contract scores the healthy event, records the QC failure for the broken one, and reports an error result.json "
            "alongside the partial event_metrics.csv under event-metrics/. "
            "Do not fill, interpolate, or drop the missing values; do not repair event 02; do not suppress the QC failure. "
            "Keep the native partial outputs exactly as the script produces them."
        ),
        "hydroanalysis-series-metrics-001": (
            "Use series.csv exactly as supplied to run evaluation-diagnostics/compute-continuous-series-metrics. "
            "The table has hourly time, Q_obs, and Q_total columns in m3/s; the timestep is 1 h. "
            "Compute the default metric set (nse, rmse, mae, r2, volume_bias, relative_volume_bias) and write the native outputs "
            "(series_metrics.csv, result.json) under series-metrics/. "
            "Do not change the metric set, round values, or substitute a different volume conversion."
        ),
        "hydroanalysis-series-metrics-002": (
            "Use series.csv exactly as supplied to run evaluation-diagnostics/compute-continuous-series-metrics. "
            "The observed column is deliberately constant; run the skill verbatim with --timestep-hours 1 and keep the native handling of the "
            "degenerate variance (NSE recorded as unavailable, R2 at its boundary value, warning preserved). "
            "Write the native outputs (series_metrics.csv, result.json) under series-metrics/. "
            "Do not perturb the observed series or replace 'unavailable' with a numeric placeholder."
        ),
        "hydroanalysis-series-metrics-003": (
            "Use series.csv exactly as supplied to run evaluation-diagnostics/compute-continuous-series-metrics. "
            "The simulated column contains missing values; run the skill verbatim with --timestep-hours 1 and only the native result.json "
            "under series-metrics/. "
            "Do not fill, interpolate, or drop the missing values; the script must reject the input itself. "
            "No series_metrics.csv may remain in series-metrics/."
        ),
        "hydroanalysis-aggregate-metrics-001": (
            "Use event_metrics.csv exactly as supplied to run evaluation-diagnostics/aggregate-event-metrics. "
            "The table holds per-event metrics; group by catchment, aggregate the value columns nse, volume_error_relative, and "
            "peak_error_relative, and compute qualification rates for qualified_volume and qualified_peak with the confirmed thresholds.json. "
            "Write the native outputs (aggregate_metrics.csv, result.json) under aggregate-metrics/. "
            "Do not add weighting, recompute upstream metrics, or alter the qualification columns."
        ),
        "hydroanalysis-aggregate-metrics-002": (
            "Use event_metrics.csv exactly as supplied to run evaluation-diagnostics/aggregate-event-metrics. "
            "The table is confirmed to contain zero data rows; run the skill verbatim with value columns nse and volume_error_relative. "
            "The native behaviour is a warning with an empty aggregate result, not a failure: preserve it. "
            "Write the native outputs (aggregate_metrics.csv, result.json) under aggregate-metrics/. "
            "Do not treat the empty table as an error or fabricate metric values."
        ),
        "hydroanalysis-aggregate-metrics-003": (
            "Use event_metrics.csv exactly as supplied to run evaluation-diagnostics/aggregate-event-metrics with "
            "--value-columns nse,volume_error_relative and --statistics mean,p25. "
            "p25 is not part of the supported statistic set; run the skill verbatim and only the native result.json under aggregate-metrics/. "
            "Do not map p25 to another statistic or add implementations; the script must reject the request itself. "
            "No aggregate_metrics.csv may remain in aggregate-metrics/."
        ),
    }


def _positive_grading(capability: str, task_id: str) -> list[dict[str, Any]]:
    meta = CAPABILITIES[capability]
    output = meta["output"]
    golden = f"expected/golden_workspace/{output}"
    result = f"{output}/result.json"
    aggregate_columns = ["group", "events", "nse_mean", "nse_count", "volume_error_relative_mean"]
    if task_id == "hydroanalysis-aggregate-metrics-001":
        aggregate_columns += ["qualified_volume_qualified_rate", "qualified_peak_qualified_rate"]
    required_columns: dict[str, list[str]] = {
        f"{output}/{meta['table']}": {
            "event-metrics": [
                "event_id", "rows", "start", "end", "observed_volume", "simulated_volume", "volume_error_relative",
                "observed_peak", "simulated_peak", "peak_error_relative", "peak_time_error_hours", "peak_tie_count",
                "nse", "r2", "rmse", "mae", "qualified_volume", "qualified_peak", "qualified_peak_time",
            ],
            "series-metrics": ["metric", "value", "unit", "status"],
            "aggregate-metrics": aggregate_columns,
        }[capability],
        result: ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"],
    }
    return [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": [f"{output}/{meta['table']}", result],
            "required_columns": required_columns,
            "weight": 0.10,
        },
        {
            "name": "metrics_table",
            "type": "table_match",
            "target": f"{output}/{meta['table']}",
            "reference": f"{golden}/{meta['table']}",
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.25,
        },
        {"name": "result_skill", "type": "exact_match", "target": result, "field": "skill", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_status", "type": "exact_match", "target": result, "field": "status", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_message", "type": "exact_match", "target": result, "field": "message", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_warnings", "type": "exact_match", "target": result, "field": "warnings", "reference": f"{golden}/result.json", "weight": 0.10},
        {"name": "result_checks", "type": "exact_match", "target": result, "field": "checks", "reference": f"{golden}/result.json", "weight": 0.10},
        {
            "name": "artifact_references",
            "type": "artifact_reference_check",
            "target": result,
            "required_keys": [meta["artifact"]],
            "weight": 0.30,
        },
    ]


def _partial_error_grading() -> list[dict[str, Any]]:
    """Grading for the native 'some events fail, others are still scored' error mode."""

    meta = CAPABILITIES["event-metrics"]
    output = meta["output"]
    golden = f"expected/golden_workspace/{output}"
    result = f"{output}/result.json"
    return [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": [f"{output}/{meta['table']}", result],
            "required_columns": {
                f"{output}/{meta['table']}": ["event_id", "rows", "start", "end", "observed_volume", "simulated_volume", "volume_error_relative", "qualified_volume"],
                result: ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"],
            },
            "weight": 0.15,
        },
        {
            "name": "partial_metrics_table",
            "type": "table_match",
            "target": f"{output}/{meta['table']}",
            "reference": f"{golden}/{meta['table']}",
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.20,
        },
        {"name": "result_skill", "type": "exact_match", "target": result, "field": "skill", "reference": f"{golden}/result.json", "weight": 0.10},
        {"name": "result_status", "type": "exact_match", "target": result, "field": "status", "reference": f"{golden}/result.json", "weight": 0.10},
        {"name": "failure_reason", "type": "exact_match", "target": result, "field": "message", "reference": f"{golden}/result.json", "weight": 0.20},
        {
            "name": "artifact_references",
            "type": "artifact_reference_check",
            "target": result,
            "required_keys": [meta["artifact"]],
            "weight": 0.25,
        },
    ]


def _error_grading(capability: str) -> list[dict[str, Any]]:
    meta = CAPABILITIES[capability]
    output = meta["output"]
    result = f"{output}/result.json"
    golden = f"expected/golden_workspace/{output}/result.json"
    return [
        {
            "name": "result_schema",
            "type": "file_check",
            "target": result,
            "required_columns": ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"],
            "expected_rows": {result: 1},
            "weight": 0.15,
        },
        {"name": "result_skill", "type": "exact_match", "target": result, "field": "skill", "reference": golden, "weight": 0.10},
        {"name": "result_status", "type": "exact_match", "target": result, "field": "status", "reference": golden, "weight": 0.20},
        {"name": "failure_reason", "type": "exact_match", "target": result, "field": "message", "reference": golden, "weight": 0.25},
        {"name": "empty_artifacts", "type": "exact_match", "target": result, "field": "artifacts", "reference": golden, "weight": 0.10},
        {
            "name": "no_standard_outputs",
            "type": "file_absence_check",
            "targets": [f"{output}/{meta['table']}"],
            "weight": 0.20,
        },
    ]


def _build_task(task_id: str) -> dict[str, Any]:
    capability = _capability(task_id)
    index = _index(task_id)
    meta = CAPABILITIES[capability]
    positive = index < 3
    partial_error = task_id == "hydroanalysis-event-metrics-003"
    data_files = sorted(_data_frames(task_id)) + sorted(_extra_files(task_id))
    required = [f"{meta['output']}/result.json"]
    if positive or partial_error:
        required = [f"{meta['output']}/{meta['table']}", *required]
    return {
        "id": task_id,
        "title": _titles()[task_id],
        "domain": "results-analysis",
        "difficulty": "intermediate" if index == 2 or (index == 1 and capability != "series-metrics") else "basic",
        "primary_skill": meta["skill"],
        "secondary_skills": [],
        "prompt": _prompts()[task_id],
        "data_description": "A deterministic evaluation-diagnostics fixture with confirmed columns, units, and (where applicable) qualification thresholds.",
        "data_files": data_files,
        "required_outputs": required,
        "setup_notes": [
            "All input columns and thresholds are confirmed by the user and must not be altered.",
            "Error conventions follow the skill contract; error signs must never be flipped.",
            "Do not install software or reimplement the metric formulas.",
        ],
        "timeout_seconds": 300,
        "grading": _positive_grading(capability, task_id) if positive else (_partial_error_grading() if partial_error else _error_grading(capability)),
    }


def _normalize_result(path: Path) -> None:
    if not path.is_file():
        return
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    inputs = document.get("inputs")
    if isinstance(inputs, dict):
        for reference in inputs.values():
            if isinstance(reference, dict) and isinstance(reference.get("path"), str):
                reference["path"] = Path(reference["path"]).name
    document["provenance"] = {"generator": "HydroTune skill script; runtime versions normalized for the golden oracle"}
    path.write_bytes(_stable_json(document))


def _generate_golden(task_dir: Path, task_id: str) -> None:
    capability = _capability(task_id)
    meta = CAPABILITIES[capability]
    args, expected_code = _golden_command(task_id)
    with tempfile.TemporaryDirectory(prefix=f"hsqb-{task_dir.name}-") as raw_temp:
        temp = Path(raw_temp)
        work = temp / "workspace"
        shutil.copytree(task_dir / "data", work)
        output = work / meta["output"]
        command = [*args, "--output-dir", str(output)]
        completed = subprocess.run(
            command,
            cwd=work,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )
        if completed.returncode != expected_code:
            raise RuntimeError(f"{task_dir.name}: expected exit {expected_code}, got {completed.returncode}: {completed.stderr}")
        _normalize_result(output / "result.json")
        golden = task_dir / "expected" / "golden_workspace" / meta["output"]
        for source in sorted(output.iterdir()):
            if source.is_file():
                _write_bytes(golden / source.name, source.read_bytes())


def generate_task(task_id: str) -> None:
    if task_id not in TASK_IDS:
        raise ValueError(f"unsupported diagnostics task id: {task_id}")
    task_dir = ROOT / task_id
    data_dir = task_dir / "data"
    for name, frame in _data_frames(task_id).items():
        _write_csv(data_dir / name, frame)
    for name, value in _extra_files(task_id).items():
        _write_json(data_dir / name, value)
    _generate_golden(task_dir, task_id)
    _write_json(task_dir / "task.json", _build_task(task_id))
