"""Deterministic fixtures for the FAO-56 ETo benchmark tasks (hydrodata-eto-faopm-001..003)."""

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
SKILL_REF = "data-processing/derive-potential-evapotranspiration"
SKILL_FOLDER = "data-processing/derive-potential-evapotranspiration"
SKILL_SCRIPT = "derive_potential_evapotranspiration.py"
OUTPUT_DIR = "eto-out"
TASK_IDS = [f"hydrodata-eto-faopm-{index:03d}" for index in (1, 2, 3)]

STATIONS = pd.DataFrame(
    {
        "source_id": ["A", "B"],
        "latitude_deg": [50.8, 45.2],
        "elevation_m": [100.0, 250.0],
    }
)


def _index(task_id: str) -> int:
    if task_id not in TASK_IDS:
        raise ValueError(f"unsupported eto task id: {task_id}")
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
        raise FileNotFoundError(f"eto skill script not found: {script}")
    return script


def _met_frame(index: int) -> pd.DataFrame:
    days = np.arange(30, dtype=float)
    frames = []
    for station, phase in (("A", 0.0), ("B", np.pi / 3.0)):
        temperature = np.round(15.0 + 8.0 * np.sin(2.0 * np.pi * days / 30.0 + phase), 2)
        frame = pd.DataFrame(
            {
                "time": pd.date_range("2020-07-01 00:00", periods=30, freq="D").strftime("%Y-%m-%d %H:%M:%S"),
                "source_id": station,
                "t_c": temperature,
                "tmax_c": temperature + 5.0,
                "tmin_c": temperature - 5.0,
                "rn_mj_m2_day": np.round(10.0 + 6.0 * np.sin(2.0 * np.pi * days / 30.0 + phase), 2),
                "ea_kpa": np.round(1.0 + 0.3 * np.sin(2.0 * np.pi * days / 30.0 + phase), 3),
                "u2_m_s": np.round(2.0 + 0.5 * np.cos(2.0 * np.pi * days / 30.0 + phase), 2),
            }
        )
        frames.append(frame)
    met = pd.concat(frames, ignore_index=True)
    if index == 2:
        # Confirmed cold humid block: the FAO-56 term with negative net radiation
        # turns ETo negative, which the floor_zero mapping policy clips to zero.
        cold = (met.source_id == "A") & met.time.isin(["2020-07-21 00:00", "2020-07-22 00:00", "2020-07-23 00:00"])
        met.loc[cold, ["t_c", "tmax_c", "tmin_c", "rn_mj_m2_day", "ea_kpa", "u2_m_s"]] = [5.0, 6.0, 4.0, -1.5, 0.92, 2.0]
    if index == 3:
        met.loc[15, "rn_mj_m2_day"] = np.nan
    return met


def _config(index: int) -> dict[str, Any]:
    mapping = None
    if index < 3:
        mapping = {"target": "PET", "factor": 1.0, "negative_policy": "floor_zero"}
    config: dict[str, Any] = {
        "scale": "daily",
        "timestep_seconds": 86400,
        "timezone": "Asia/Shanghai",
        "source_timezone_mode": "local_naive",
        "timestamp_semantics": "interval_end",
        "columns": {
            "time": "time",
            "source_id": "source_id",
            "t_c": "t_c",
            "tmax_c": "tmax_c",
            "tmin_c": "tmin_c",
            "rn_mj_m2_step": "rn_mj_m2_day",
            "ea_kpa": "ea_kpa",
            "u2_m_s": "u2_m_s",
        },
        "units": {
            "t_c": "degC",
            "tmax_c": "degC",
            "tmin_c": "degC",
            "rn_mj_m2_step": "MJ/m2/step",
            "ea_kpa": "kPa",
            "u2_m_s": "m/s",
        },
    }
    if mapping is not None:
        config["mapping"] = mapping
    return config


def _titles() -> dict[int, str]:
    return {
        1: "Derive FAO-56 daily ETo for two stations and map it to PET",
        2: "Clip negative mapped evapotranspiration with the confirmed floor_zero policy",
        3: "Reject ETo derivation when meteorology contains missing values",
    }


def _prompts() -> dict[int, str]:
    return {
        1: (
            "Use met.csv, stations.csv, and config.json exactly as supplied to run data-processing/derive-potential-evapotranspiration. "
            "The meteorology table is daily for two stations in July 2020; all columns, units, timezone, and the PET mapping "
            "(factor 1.0, negative_policy floor_zero) are confirmed in the config. "
            "Write the native outputs (eto.csv, mapped_evap.csv, result.json) under eto-out/. "
            "Do not alter the config, fill missing values, or substitute another evapotranspiration formula."
        ),
        2: (
            "Use met.csv, stations.csv, and config.json exactly as supplied to run data-processing/derive-potential-evapotranspiration. "
            "Station A deliberately contains a cold, humid block (2020-07-21..23) whose FAO-56 ETo is negative; the confirmed mapping "
            "policy floor_zero requires those mapped PET depths to be clipped to zero while eto.csv keeps the raw values. "
            "Write the native outputs (eto.csv, mapped_evap.csv, result.json) under eto-out/. "
            "Do not switch the policy to error, drop the rows, or 'repair' the meteorology."
        ),
        3: (
            "Use met.csv, stations.csv, and config.json exactly as supplied to run data-processing/derive-potential-evapotranspiration. "
            "The meteorology table contains at least one missing value; run the skill verbatim and only the native result.json under "
            "eto-out/. "
            "Do not fill, interpolate, or drop the missing value; do not rerun with repaired data; the script must reject the input "
            "itself. No eto.csv or mapped_evap.csv may remain in eto-out/."
        ),
    }


def _positive_grading() -> list[dict[str, Any]]:
    golden = f"expected/golden_workspace/{OUTPUT_DIR}"
    result = f"{OUTPUT_DIR}/result.json"
    return [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": [f"{OUTPUT_DIR}/eto.csv", f"{OUTPUT_DIR}/mapped_evap.csv", result],
            "required_columns": {
                f"{OUTPUT_DIR}/eto.csv": ["time", "source_id", "ETo_mm"],
                f"{OUTPUT_DIR}/mapped_evap.csv": ["time", "source_id", "variable", "depth_mm"],
                result: ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"],
            },
            "weight": 0.10,
        },
        {
            "name": "eto_table",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/eto.csv",
            "reference": f"{golden}/eto.csv",
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.30,
        },
        {
            "name": "mapped_table",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/mapped_evap.csv",
            "reference": f"{golden}/mapped_evap.csv",
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.05,
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
            "required_keys": ["eto", "mapped_evap"],
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
            "targets": [f"{OUTPUT_DIR}/eto.csv", f"{OUTPUT_DIR}/mapped_evap.csv"],
            "weight": 0.20,
        },
    ]


def _build_task(task_id: str) -> dict[str, Any]:
    index = _index(task_id)
    positive = index < 3
    required = [f"{OUTPUT_DIR}/result.json"]
    if positive:
        required = [f"{OUTPUT_DIR}/eto.csv", f"{OUTPUT_DIR}/mapped_evap.csv", *required]
    return {
        "id": task_id,
        "title": _titles()[index],
        "domain": "data-preprocessing",
        "difficulty": "intermediate" if index < 3 else "basic",
        "primary_skill": SKILL_REF,
        "secondary_skills": [],
        "prompt": _prompts()[index],
        "data_description": "A deterministic FAO-56 daily meteorology fixture for two stations with a fully confirmed config.",
        "data_files": ["met.csv", "stations.csv", "config.json"],
        "required_outputs": required,
        "setup_notes": [
            "The config (columns, canonical units, timezone, mapping policy) is confirmed by the user and must not be altered.",
            "Meteorology values are instantaneous daily aggregates; ETo follows FAO-56 Penman-Monteith.",
            "Do not install software or implement a replacement formula.",
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
                "met.csv",
                "--stations",
                "stations.csv",
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
    _write_csv(data_dir / "met.csv", _met_frame(index))
    _write_csv(data_dir / "stations.csv", STATIONS)
    _write_json(data_dir / "config.json", _config(index))
    _generate_golden(task_dir, task_id)
    _write_json(task_dir / "task.json", _build_task(task_id))
