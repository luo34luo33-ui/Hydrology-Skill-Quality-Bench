"""Deterministic fixtures for the model-forcing standardization benchmark tasks (hydrodata-forcing-standardize-001..003)."""

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
SKILL_REF = "data-processing/prepare-model-forcing-timeseries"
SKILL_FOLDER = "data-processing/prepare-model-forcing-timeseries"
SKILL_SCRIPT = "prepare_model_forcing_timeseries.py"
OUTPUT_DIR = "forcing-out"
TASK_IDS = [f"hydrodata-forcing-standardize-{index:03d}" for index in (1, 2, 3)]

STATION_IDS = ("A", "B")


def _index(task_id: str) -> int:
    if task_id not in TASK_IDS:
        raise ValueError(f"unsupported forcing-standardize task id: {task_id}")
    return int(task_id.rsplit("-", 1)[1])


def _stable_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_bytes(path: Path, content: bytes) -> None:
    if path.exists() and path.read_bytes() != content:
        raise RuntimeError(f"refusing to overwrite non-matching deterministic artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _write_json(path: Path, value: Any) -> None:
    # Retain the independently authored public interface when regenerating fixtures.
    if path.name == "task.json" and isinstance(value, dict):
        canonical = Path(__file__).resolve().parent / value["id"] / "public_contract.json"
        if canonical.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            destination = path.parent / "public_contract.json"
            if canonical.resolve() != destination.resolve():
                destination.write_bytes(canonical.read_bytes())
            value = dict(value, public_contract="public_contract.json")
    _write_bytes(path, _stable_json(value))


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = frame.to_csv(index=False, float_format="%.12g", lineterminator="\n", encoding="utf-8").encode("utf-8")
    _write_bytes(path, content)


def _skill_script() -> Path:
    configured = os.environ.get("HYDROTUNE_SKILLS_ROOT", "").strip().strip('"')
    skills_root = Path(configured) if configured else DEFAULT_SKILLS_ROOT
    script = skills_root / SKILL_FOLDER / "examples" / SKILL_SCRIPT
    if not script.is_file():
        raise FileNotFoundError(f"forcing-standardize skill script not found: {script}")
    return script


def _depths(index: int) -> np.ndarray:
    hours = np.arange(48, dtype=float)
    depth = np.round(1.5 + 1.2 * np.sin(2.0 * np.pi * hours / 24.0), 3)
    return depth


def _source_frame(index: int) -> pd.DataFrame:
    if index == 1:
        depth = _depths(index)
        time = pd.date_range("2020-07-01 00:00", periods=48, freq="h").strftime("%Y-%m-%d %H:%M")
        frames = [pd.DataFrame({"time": time, "source_id": station, "rain_mm": depth}) for station in STATION_IDS]
        return pd.concat(frames, ignore_index=True)
    depth = _depths(index)
    time = pd.date_range("2020-07-01 00:00", periods=48, freq="h").strftime("%Y-%m-%d %H:%M")
    frames = []
    for station in STATION_IDS:
        blocks = np.concatenate([depth[0:12], depth[12:24], depth[24:36], depth[36:48]])
        cumulative = np.cumsum(blocks)
        reset = np.zeros(48, dtype=int)
        reset[12] = 1
        reset[24] = 1
        reset[36] = 1
        frame = pd.DataFrame({"time": time, "source_id": station, "cum_mm": np.round(cumulative, 3), "reset_flag": reset})
        if index == 3:
            # The reset at step 24 is left unmarked, so the cumulative series
            # shows a negative difference that the skill must reject.
            frame.loc[24, "reset_flag"] = 0
            frame.loc[24, "cum_mm"] = frame.loc[23, "cum_mm"] - 0.5
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _config(index: int) -> dict[str, Any]:
    if index == 1:
        return {
            "schema_version": "1.0",
            "variable": "P",
            "columns": {"time": "time", "source_id": "source_id", "value": "rain_mm"},
            "unit": "mm/step",
            "value_semantics": "step_depth",
            "timezone": "Asia/Shanghai",
            "source_timezone_mode": "local_naive",
            "timestamp_semantics": "interval_end",
            "timestep_seconds": 3600,
        }
    return {
        "schema_version": "1.0",
        "variable": "P",
        "columns": {"time": "time", "source_id": "source_id", "value": "cum_mm", "reset": "reset_flag"},
        "unit": "mm/step",
        "value_semantics": "running_cumulative",
        "timezone": "Asia/Shanghai",
        "source_timezone_mode": "local_naive",
        "timestamp_semantics": "interval_end",
        "timestep_seconds": 3600,
    }


def _titles() -> dict[int, str]:
    return {
        1: "Standardize step-depth precipitation for two stations",
        2: "Convert a running cumulative gauge with explicit resets into step depths",
        3: "Reject a cumulative gauge with an unmarked reset",
    }


def _prompts() -> dict[int, str]:
    return {
        1: (
            "Use rain.csv and config.json exactly as supplied to run data-processing/prepare-model-forcing-timeseries. "
            "The source table is hourly for two stations; the config confirms variable P, step_depth semantics in mm/step, the "
            "column mapping, timezone, and interval_end semantics. "
            "Write the native outputs (prepared_forcing.csv, series_metadata.json, result.json) under forcing-out/. "
            "Do not alter the config, fill missing values, or invent a different unit conversion."
        ),
        2: (
            "Use gauge.csv and config.json exactly as supplied to run data-processing/prepare-model-forcing-timeseries. "
            "The source is a running cumulative gauge (running_cumulative in mm/step) with an explicit reset_flag column; the "
            "confirmed resets at steps 12, 24, and 36 restart the counter, and the skill converts it into interval-end step depths. "
            "Write the native outputs (prepared_forcing.csv, series_metadata.json, result.json) under forcing-out/. "
            "Do not relabel the semantics, diff the series yourself, or alter the reset flags."
        ),
        3: (
            "Use gauge.csv and config.json exactly as supplied to run data-processing/prepare-model-forcing-timeseries. "
            "The cumulative gauge contains an unmarked reset (a negative difference at step 24); run the skill verbatim and only "
            "the native result.json under forcing-out/. "
            "Do not insert a reset flag, drop the step, or rerun with repaired data; the script must reject the input itself. "
            "No prepared_forcing.csv or series_metadata.json may remain in forcing-out/."
        ),
    }


def _positive_grading() -> list[dict[str, Any]]:
    golden = f"expected/golden_workspace/{OUTPUT_DIR}"
    result = f"{OUTPUT_DIR}/result.json"
    return [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": [f"{OUTPUT_DIR}/prepared_forcing.csv", f"{OUTPUT_DIR}/series_metadata.json", result],
            "required_columns": {
                f"{OUTPUT_DIR}/prepared_forcing.csv": ["time", "source_id", "variable", "depth_mm"],
                f"{OUTPUT_DIR}/series_metadata.json": ["schema_version", "variable", "unit", "timestamp_semantics", "timezone", "timestep_seconds", "source_count", "steps"],
                result: ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"],
            },
            "weight": 0.10,
        },
        {
            "name": "forcing_table",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/prepared_forcing.csv",
            "reference": f"{golden}/prepared_forcing.csv",
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.35,
        },
        {"name": "result_skill", "type": "exact_match", "target": result, "field": "skill", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_status", "type": "exact_match", "target": result, "field": "status", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_message", "type": "exact_match", "target": result, "field": "message", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_warnings", "type": "exact_match", "target": result, "field": "warnings", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_checks", "type": "exact_match", "target": result, "field": "checks", "reference": f"{golden}/result.json", "weight": 0.05},
        {
            "name": "artifact_references",
            "type": "artifact_reference_check",
            "target": result,
            "required_keys": ["forcing", "metadata"],
            "weight": 0.30,
        },
    ]


def _error_grading() -> list[dict[str, Any]]:
    result = f"{OUTPUT_DIR}/result.json"
    golden = f"expected/golden_workspace/{OUTPUT_DIR}/result.json"
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
            "targets": [f"{OUTPUT_DIR}/prepared_forcing.csv", f"{OUTPUT_DIR}/series_metadata.json"],
            "weight": 0.20,
        },
    ]


def _build_task(task_id: str) -> dict[str, Any]:
    index = _index(task_id)
    positive = index < 3
    required = [f"{OUTPUT_DIR}/result.json"]
    if positive:
        required = [f"{OUTPUT_DIR}/prepared_forcing.csv", f"{OUTPUT_DIR}/series_metadata.json", *required]
    source = "rain.csv" if index == 1 else "gauge.csv"
    return {
        "id": task_id,
        "title": _titles()[index],
        "domain": "data-preprocessing",
        "difficulty": "intermediate" if index < 3 else "basic",
        "primary_skill": SKILL_REF,
        "secondary_skills": [],
        "prompt": _prompts()[index],
        "data_description": "A deterministic precipitation standardization fixture with a fully confirmed config.",
        "data_files": [source, "config.json"],
        "required_outputs": required,
        "setup_notes": [
            "The config (variable, semantics, unit, column mapping, timezone) is confirmed by the user and must not be altered.",
            "Depths are interval-end mm/step values on a complete hourly axis.",
            "Do not install software or implement a replacement conversion.",
        ],
        "timeout_seconds": 300,
        "grading": _positive_grading() if positive else _error_grading(),
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
    index = _index(task_id)
    expected_code = 2 if index == 3 else 0
    with tempfile.TemporaryDirectory(prefix=f"hsqb-{task_dir.name}-") as raw_temp:
        temp = Path(raw_temp)
        work = temp / "workspace"
        shutil.copytree(task_dir / "data", work)
        output = work / OUTPUT_DIR
        completed = subprocess.run(
            [
                sys.executable,
                str(_skill_script()),
                "--source",
                "rain.csv" if index == 1 else "gauge.csv",
                "--config",
                "config.json",
                "--output-dir",
                str(output),
            ],
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
        golden = task_dir / "expected" / "golden_workspace" / OUTPUT_DIR
        for source in sorted(output.iterdir()):
            if source.is_file():
                _write_bytes(golden / source.name, source.read_bytes())


def generate_task(task_id: str) -> None:
    _index(task_id)
    index = _index(task_id)
    task_dir = ROOT / task_id
    data_dir = task_dir / "data"
    _write_csv(data_dir / ("rain.csv" if index == 1 else "gauge.csv"), _source_frame(index))
    _write_json(data_dir / "config.json", _config(index))
    _generate_golden(task_dir, task_id)
    _write_json(task_dir / "task.json", _build_task(task_id))
