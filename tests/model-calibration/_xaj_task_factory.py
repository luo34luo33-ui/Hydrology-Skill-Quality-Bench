"""Deterministic fixtures for lumped Xinanjiang forward-simulation benchmark tasks."""

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
SKILL_REF = "hydrological-modeling/run-lumped-xaj-model"
SKILL_FOLDER = "hydrological-modeling/run-lumped-xaj-model"
SKILL_SCRIPT = "run_lumped_xaj.py"
OUTPUT_DIR = "xaj-run"
TASK_IDS = [f"hydromodel-xaj-{index:03d}" for index in (1, 2, 3)]

BASE_PARAMETERS: dict[str, Any] = {
    "K": 0.5,
    "B": 0.3,
    "C": 0.12,
    "WM": 120.0,
    "WUM": 20.0,
    "WLM": 60.0,
    "IM": 0.02,
    "SM": 25.0,
    "EX": 1.2,
    "KG": 0.35,
    "KI": 0.3,
    "CG": 0.95,
    "CI": 0.6,
    "CS": 0.2,
    "L": 2,
    "WUM_init": 15.0,
    "WLM_init": 45.0,
    "WDM_init": 30.0,
    "S1": 5.0,
    "FR1": 0.4,
    "Q": 15.0,
}

# SM=4.0 keeps rs_raw non-negative under the heavy storm, giving a clean success run;
# the moderate forcing with SM=25.0 instead triggers repeated numerical clipping.
SUCCESS_PARAMETERS: dict[str, Any] = {**BASE_PARAMETERS, "SM": 4.0}


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


def _skill_script() -> Path:
    configured = os.environ.get("HYDROTUNE_SKILLS_ROOT", "").strip().strip('"')
    skills_root = Path(configured) if configured else DEFAULT_SKILLS_ROOT
    script = skills_root / SKILL_FOLDER / "examples" / SKILL_SCRIPT
    if not script.is_file():
        raise FileNotFoundError(f"xaj skill script not found: {script}")
    return script


def _forcing_frame(task_id: str) -> pd.DataFrame:
    hours = np.arange(72)
    if task_id == "hydromodel-xaj-001":
        precipitation = np.where((hours >= 12) & (hours < 23), 15.0, 0.0)
    elif task_id == "hydromodel-xaj-002":
        precipitation = np.where((hours >= 12) & (hours < 20), 4.0, 0.0)
        precipitation = np.where((hours >= 32) & (hours < 39), 6.0, precipitation)
    elif task_id == "hydromodel-xaj-003":
        precipitation = np.where((hours >= 12) & (hours < 20), 4.0, 0.0)
        precipitation = np.where((hours >= 32) & (hours < 39), 6.0, precipitation)
    else:
        raise ValueError(f"unsupported xaj task id: {task_id}")
    evaporation = np.full(72, 0.35)
    # Confirmed dry hours with zero potential evaporation at the balance window
    # boundaries keep the native water-balance check well posed for this fixture.
    evaporation[11] = 0.0
    evaporation[71] = 0.0
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2024-08-01 00:00", periods=72, freq="h"),
            "P": precipitation.astype(float),
            "E0": evaporation,
        }
    )
    if task_id == "hydromodel-xaj-003":
        frame.loc[40, "E0"] = np.nan
    return frame


def _parameters(task_id: str) -> dict[str, Any]:
    if task_id == "hydromodel-xaj-001":
        return SUCCESS_PARAMETERS
    if task_id == "hydromodel-xaj-002":
        return BASE_PARAMETERS
    return BASE_PARAMETERS


def _task_parts(task_id: str) -> int:
    if task_id not in TASK_IDS:
        raise ValueError(f"unsupported xaj task id: {task_id}")
    return int(task_id.rsplit("-", 1)[1])


def _titles() -> dict[int, str]:
    return {
        1: "Run a continuous lumped Xinanjiang simulation with warm-up",
        2: "Report numerical clipping instead of hiding it in a Xinanjiang run",
        3: "Reject a Xinanjiang run with missing evaporation forcing",
    }


def _positive_grading() -> list[dict[str, Any]]:
    golden = f"expected/golden_workspace/{OUTPUT_DIR}"
    result = f"{OUTPUT_DIR}/result.json"
    columns = [
        "time",
        "is_warmup",
        "P",
        "E0",
        "P_perv",
        "P_im",
        "WU",
        "WL",
        "WD",
        "EP",
        "EU",
        "EL",
        "ED",
        "E",
        "PE",
        "W",
        "R",
        "FR",
        "S1",
        "RS",
        "RI",
        "RG",
        "QS",
        "QI",
        "QG",
        "QT",
        "Qt",
        "R_im",
    ]
    return [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": [f"{OUTPUT_DIR}/lumped_xaj_runoff.csv", result],
            "required_columns": {
                f"{OUTPUT_DIR}/lumped_xaj_runoff.csv": columns,
                result: ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"],
            },
            "weight": 0.10,
        },
        {
            "name": "simulation_table",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/lumped_xaj_runoff.csv",
            "reference": f"{golden}/lumped_xaj_runoff.csv",
            "datetime_columns": ["time"],
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.30,
        },
        {"name": "result_skill", "type": "exact_match", "target": result, "field": "skill", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_status", "type": "exact_match", "target": result, "field": "status", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_message", "type": "exact_match", "target": result, "field": "message", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_warnings", "type": "exact_match", "target": result, "field": "warnings", "reference": f"{golden}/result.json", "weight": 0.10},
        {"name": "result_checks", "type": "exact_match", "target": result, "field": "checks", "reference": f"{golden}/result.json", "weight": 0.05},
        {
            "name": "artifact_references",
            "type": "artifact_reference_check",
            "target": result,
            "required_keys": ["simulation_table"],
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
            "targets": [f"{OUTPUT_DIR}/lumped_xaj_runoff.csv"],
            "weight": 0.20,
        },
    ]


def _build_task(task_id: str) -> dict[str, Any]:
    index = _task_parts(task_id)
    positive = index < 3
    if index == 1:
        prompt = (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-xaj-model. "
            "The forcing table is hourly; P and E0 are instantaneous rates in mm/h on a gap-free axis; the two zero-E0 hours are confirmed and intentional. "
            "The 21-parameter set is confirmed; area is 640 km2, timestep is 1 h, mode is continuous, and warm-up is 12 steps. "
            "Write the native outputs (lumped_xaj_runoff.csv, result.json) under xaj-run/. "
            "Do not modify parameters, fill missing values, change the warm-up, or substitute another model implementation."
        )
    elif index == 2:
        prompt = (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-xaj-model. "
            "The confirmed parameter set and the forcing pattern are deliberate user decisions; run them verbatim with "
            "area 640 km2, timestep 1 h, mode continuous, and warm-up 12 steps. "
            "Write the native outputs (lumped_xaj_runoff.csv, result.json) under xaj-run/. "
            "Numerical clipping may occur: it must be reported natively in result.json, never hidden or corrected by altering "
            "parameters, forcing, or the model equations. Do not 'improve' the configuration to avoid the warning."
        )
    else:
        prompt = (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-xaj-model. "
            "The forcing table is hourly and contains at least one missing E0 value. "
            "Run the simulation verbatim with area 640 km2, timestep 1 h, mode continuous, warm-up 12 steps, and only the native "
            "result.json under xaj-run/. "
            "Do not fill, interpolate, or drop the missing evaporation value; do not rerun with repaired data; the script must "
            "reject the input itself. No lumped_xaj_runoff.csv may remain in xaj-run/."
        )
    required = [f"{OUTPUT_DIR}/result.json"]
    if positive:
        required = [f"{OUTPUT_DIR}/lumped_xaj_runoff.csv", *required]
    return {
        "id": task_id,
        "title": _titles()[index],
        "domain": "model-calibration",
        "difficulty": "intermediate" if index < 3 else "basic",
        "primary_skill": SKILL_REF,
        "secondary_skills": [],
        "prompt": prompt,
        "data_description": "A deterministic continuous lumped Xinanjiang problem with a complete 21-parameter set and an hourly forcing table.",
        "data_files": ["forcing.csv", "parameters.json"],
        "required_outputs": required,
        "setup_notes": [
            "The parameter set, area, timestep, mode, and warm-up are confirmed by the user and must not be altered.",
            "P and E0 are instantaneous rates in mm/h; discharge outputs are in m3/s.",
            "Do not install software or implement a replacement Xinanjiang model.",
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
    index = _task_parts(task_id)
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
                "--forcing",
                "forcing.csv",
                "--time-column",
                "time",
                "--params",
                "parameters.json",
                "--area-km2",
                "640",
                "--timestep-hours",
                "1",
                "--mode",
                "continuous",
                "--warmup-steps",
                "12",
                "--output-format",
                "csv",
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
    _task_parts(task_id)
    task_dir = ROOT / task_id
    data_dir = task_dir / "data"
    _write_csv(data_dir / "forcing.csv", _forcing_frame(task_id))
    _write_json(data_dir / "parameters.json", _parameters(task_id))
    _generate_golden(task_dir, task_id)
    _write_json(task_dir / "task.json", _build_task(task_id))
