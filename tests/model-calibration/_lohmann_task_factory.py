"""Deterministic fixtures for the Lohmann channel-routing benchmark tasks (hydromodel-lohmann-001..003)."""

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
SKILL_REF = "hydrological-modeling/route-lohmann-channel"
SKILL_FOLDER = "hydrological-modeling/route-lohmann-channel"
SKILL_SCRIPT = "route_lohmann.py"
OUTPUT_DIR = "lohmann-run"
TASK_IDS = [f"hydromodel-lohmann-{index:03d}" for index in (1, 2, 3)]

FLOWLEN_M = 100000.0
ROUTE_PARAMETERS: dict[str, Any] = {"N": 2.0, "K": 2.0, "VELO": 1.0, "DIFF": 800.0}
# K=10 widens the Gamma unit hydrograph so a short sustained series retains
# enough volume in the registers to trigger the native volume_difference warning.
ROUTE_WARNING_PARAMETERS: dict[str, Any] = {**ROUTE_PARAMETERS, "K": 10.0}


def _index(task_id: str) -> int:
    if task_id not in TASK_IDS:
        raise ValueError(f"unsupported lohmann task id: {task_id}")
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
        raise FileNotFoundError(f"lohmann skill script not found: {script}")
    return script


def _inflow_frame(index: int) -> pd.DataFrame:
    if index == 1 or index == 3:
        # 240 daily steps; both components fall silent for the final 110 steps so
        # the 107-step composite unit hydrograph fully drains and the routed
        # volume difference stays inside the default tolerance.
        t = np.arange(240, dtype=float)
        direct = 5.0 + 45.0 * np.exp(-(((t - 60.0) / 20.0) ** 2)) + 30.0 * np.exp(-(((t - 120.0) / 15.0) ** 2))
        direct[t >= 130] = 0.0
        base = np.where(t < 130, 2.0, 0.0)
    elif index == 2:
        # 60 daily steps with sustained inflow to the end and the widened K=10
        # Gamma UH: enough inflow volume stays inside the unit-hydrograph
        # registers to natively trigger the volume_difference warning.
        t = np.arange(60, dtype=float)
        direct = 5.0 + 25.0 * np.exp(-(((t - 30.0) / 15.0) ** 2))
        base = np.full(60, 2.0)
    else:
        raise ValueError(f"unsupported lohmann index: {index}")
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2024-08-01 00:00", periods=len(t), freq="D"),
            "direct": direct,
            "base": base,
        }
    )
    if index == 3:
        frame.loc[100, "base"] = np.nan
    return frame


def _route_parameters(index: int) -> dict[str, Any]:
    return ROUTE_WARNING_PARAMETERS if index == 2 else dict(ROUTE_PARAMETERS)


def _titles() -> dict[int, str]:
    return {
        1: "Route two discharge components through a Lohmann channel",
        2: "Report the retained unit-hydrograph volume on a short sustained series",
        3: "Reject Lohmann routing when a component contains missing values",
    }


def _prompts() -> dict[int, str]:
    return {
        1: (
            "Use inflow.csv and route_params.json exactly as supplied to run hydrological-modeling/route-lohmann-channel. "
            "The inflow table is daily with two discharge components in the direct and base columns (pass --direct-column direct "
            "and --base-column base); the flow length is 100000 m and the timestep is 24 h. "
            "Write the native outputs (routed_lohmann.csv, lohmann_unit_hydrographs.json, result.json) under lohmann-run/. "
            "Do not modify the routing parameters, rescale the components, or substitute another routing method."
        ),
        2: (
            "Use inflow.csv and route_params.json exactly as supplied to run hydrological-modeling/route-lohmann-channel. "
            "The series is deliberately short (60 daily steps) with sustained inflow to the end, and the confirmed routing "
            "parameters widen the Gamma unit hydrograph (K=10), so a measurable share of the inflow volume stays inside the "
            "unit-hydrograph registers; this is a confirmed user decision and documented native behaviour. "
            "Run verbatim with --direct-column direct, --base-column base, flow length 100000 m, timestep 24 h. "
            "Write the native outputs (routed_lohmann.csv, lohmann_unit_hydrographs.json, result.json) under lohmann-run/. "
            "The volume_difference warning must be preserved natively in result.json, never hidden by shortening or rescaling the series."
        ),
        3: (
            "Use inflow.csv and route_params.json exactly as supplied to run hydrological-modeling/route-lohmann-channel. "
            "The base component contains at least one missing value; run the routing verbatim with --direct-column direct, "
            "--base-column base, flow length 100000 m, timestep 24 h, and only the native result.json under lohmann-run/. "
            "Do not fill, interpolate, or drop the missing value; do not rerun with repaired data; the script must reject the input "
            "itself. No routed_lohmann.csv or lohmann_unit_hydrographs.json may remain in lohmann-run/."
        ),
    }


def _positive_grading() -> list[dict[str, Any]]:
    golden = f"expected/golden_workspace/{OUTPUT_DIR}"
    result = f"{OUTPUT_DIR}/result.json"
    return [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": [f"{OUTPUT_DIR}/routed_lohmann.csv", f"{OUTPUT_DIR}/lohmann_unit_hydrographs.json", result],
            "required_columns": {
                f"{OUTPUT_DIR}/routed_lohmann.csv": ["time", "routed_direct", "routed_base", "Q_total"],
                f"{OUTPUT_DIR}/lohmann_unit_hydrographs.json": ["parameters", "flowlen_m", "uh_river_days", "uh_direct_steps", "uh_base_steps", "uh_hru_direct_days"],
                result: ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"],
            },
            "weight": 0.10,
        },
        {
            "name": "routed_flow",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/routed_lohmann.csv",
            "reference": f"{golden}/routed_lohmann.csv",
            "datetime_columns": ["time"],
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.25,
        },
        {
            "name": "unit_hydrographs",
            "type": "exact_match",
            "target": f"{OUTPUT_DIR}/lohmann_unit_hydrographs.json",
            "reference": f"{golden}/lohmann_unit_hydrographs.json",
            "weight": 0.15,
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
            "required_keys": ["routed_table", "unit_hydrographs"],
            "weight": 0.20,
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
            "targets": [f"{OUTPUT_DIR}/routed_lohmann.csv", f"{OUTPUT_DIR}/lohmann_unit_hydrographs.json"],
            "weight": 0.20,
        },
    ]


def _build_task(task_id: str) -> dict[str, Any]:
    index = _index(task_id)
    positive = index < 3
    required = [f"{OUTPUT_DIR}/result.json"]
    if positive:
        required = [f"{OUTPUT_DIR}/routed_lohmann.csv", f"{OUTPUT_DIR}/lohmann_unit_hydrographs.json", *required]
    return {
        "id": task_id,
        "title": _titles()[index],
        "domain": "model-calibration",
        "difficulty": "intermediate" if index < 3 else "basic",
        "primary_skill": SKILL_REF,
        "secondary_skills": [],
        "prompt": _prompts()[index],
        "data_description": "A deterministic daily Lohmann routing problem with two confirmed discharge components and routing parameters.",
        "data_files": ["inflow.csv", "route_params.json"],
        "required_outputs": required,
        "setup_notes": [
            "The routing parameters, flow length, timestep, and component columns are confirmed by the user and must not be altered.",
            "Component values pass through the routing in their input units; no area conversion is applied.",
            "Do not install software or implement a replacement routing routine.",
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
                "--inflow",
                "inflow.csv",
                "--time-column",
                "time",
                "--direct-column",
                "direct",
                "--base-column",
                "base",
                "--flowlen-m",
                str(FLOWLEN_M),
                "--route-params",
                "route_params.json",
                "--timestep-hours",
                "24",
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
            timeout=180,
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
    task_dir = ROOT / task_id
    data_dir = task_dir / "data"
    _write_csv(data_dir / "inflow.csv", _inflow_frame(_index(task_id)))
    _write_json(data_dir / "route_params.json", _route_parameters(_index(task_id)))
    _generate_golden(task_dir, task_id)
    _write_json(task_dir / "task.json", _build_task(task_id))
