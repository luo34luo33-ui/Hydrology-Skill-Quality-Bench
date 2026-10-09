"""Deterministic fixtures for Muskingum channel routing benchmark tasks."""

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
SKILL_REF = "hydrological-modeling/route-muskingum-channel"
SKILL_FOLDER = "hydrological-modeling/route-muskingum-channel"
SKILL_SCRIPT = "route_muskingum.py"
OUTPUT_DIR = "routed"
TASK_IDS = [f"hydromodel-muskingum-{index:03d}" for index in (1, 2, 3)]


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
        raise FileNotFoundError(f"muskingum skill script not found: {script}")
    return script


def _inflow_hours(count: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-07-01 00:00", periods=count, freq="h")


def _inflow_frame(task_id: str) -> pd.DataFrame:
    if task_id == "hydromodel-muskingum-001":
        hours = np.arange(48, dtype=float)
        mainstem = 50.0 + 80.0 * np.exp(-(((hours - 20.0) / 8.0) ** 2))
        tributary = 20.0 + 35.0 * np.exp(-(((hours - 26.0) / 6.0) ** 2))
        return pd.DataFrame(
            {
                "time": _inflow_hours(48),
                "mainstem_q": mainstem,
                "tributary_q": tributary,
            }
        )
    if task_id == "hydromodel-muskingum-002":
        hours = np.arange(60, dtype=float)
        channel = 100.0 + 400.0 * np.exp(-(((hours - 25.0) / 10.0) ** 2))
        return pd.DataFrame({"time": _inflow_hours(60), "channel_q": channel})
    if task_id == "hydromodel-muskingum-003":
        frame = _inflow_frame("hydromodel-muskingum-001").copy()
        frame.loc[30, "mainstem_q"] = np.nan
        return frame
    raise ValueError(f"unsupported muskingum task id: {task_id}")


def _route_spec(task_id: str) -> dict[str, Any]:
    if task_id == "hydromodel-muskingum-001":
        return {
            "schema_version": "1.0",
            "routes": [
                {"id": "mainstem", "column": "mainstem_q", "layout": "single", "k": 2.0, "x": 0.25},
                {
                    "id": "tributary",
                    "column": "tributary_q",
                    "layout": "cascade",
                    "k": 1.0,
                    "x": 0.35,
                    "reaches": 3,
                    "output_level": "final",
                },
            ],
        }
    if task_id == "hydromodel-muskingum-002":
        return {
            "schema_version": "1.0",
            "routes": [
                {
                    "id": "unstable_cascade",
                    "column": "channel_q",
                    "layout": "cascade",
                    "k": 1.0,
                    "x": 0.0,
                    "reaches": 4,
                    "output_level": "final",
                }
            ],
        }
    if task_id == "hydromodel-muskingum-003":
        return _route_spec("hydromodel-muskingum-001")
    raise ValueError(f"unsupported muskingum task id: {task_id}")


def _task_parts(task_id: str) -> int:
    if task_id not in TASK_IDS:
        raise ValueError(f"unsupported muskingum task id: {task_id}")
    return int(task_id.rsplit("-", 1)[1])


def _route_ids(index: int) -> list[str]:
    if index == 2:
        return ["unstable_cascade"]
    return ["mainstem", "tributary"]


def _titles() -> dict[int, str]:
    return {
        1: "Route two inflow sources with single and cascaded Muskingum channels",
        2: "Preserve the negative equivalent X of an unstable cascaded Muskingum configuration",
        3: "Reject Muskingum routing when the inflow series contains missing values",
    }


def _positive_grading(route_ids: list[str]) -> list[dict[str, Any]]:
    golden = f"expected/golden_workspace/{OUTPUT_DIR}"
    result = f"{OUTPUT_DIR}/result.json"
    routed_columns = ["time"] + [f"routed_{route_id}" for route_id in route_ids] + ["Q_total"]
    return [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": [f"{OUTPUT_DIR}/routed_flow.csv", f"{OUTPUT_DIR}/route_coefficients.json", result],
            "required_columns": {
                f"{OUTPUT_DIR}/routed_flow.csv": routed_columns,
                f"{OUTPUT_DIR}/route_coefficients.json": route_ids,
                result: ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"],
            },
            "weight": 0.10,
        },
        {
            "name": "routed_flow",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/routed_flow.csv",
            "reference": f"{golden}/routed_flow.csv",
            "datetime_columns": ["time"],
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.25,
        },
        {
            "name": "route_coefficients",
            "type": "exact_match",
            "target": f"{OUTPUT_DIR}/route_coefficients.json",
            "reference": f"{golden}/route_coefficients.json",
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
            "required_keys": ["routed_table", "route_coefficients"],
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
            "targets": [f"{OUTPUT_DIR}/routed_flow.csv", f"{OUTPUT_DIR}/route_coefficients.json"],
            "weight": 0.20,
        },
    ]


def _build_task(task_id: str) -> dict[str, Any]:
    index = _task_parts(task_id)
    positive = index < 3
    if index == 1:
        prompt = (
            "Use inflow.csv and route_spec.json exactly as supplied to run hydrological-modeling/route-muskingum-channel. "
            "The inflow table is hourly, gap-free, and both columns are instantaneous discharge in m3/s. "
            "The route spec confirms K, X, layout, reaches, and output_level for each route; use --timestep-hours 1, "
            "--combine sum, and the default Q_total output column. "
            "Write the native outputs (routed_flow.csv, route_coefficients.json, result.json) under routed/. "
            "Do not modify the route parameters, clip or repair any computed value, or substitute another routing method."
        )
    elif index == 2:
        prompt = (
            "Use inflow.csv and route_spec.json exactly as supplied to run hydrological-modeling/route-muskingum-channel. "
            "The route spec deliberately declares a cascaded configuration (X=0, reaches=4) provided by the user; run it verbatim "
            "with --timestep-hours 1 and write the native outputs (routed_flow.csv, route_coefficients.json, result.json) under routed/. "
            "The negative equivalent X of this cascade is a confirmed user decision: keep it unclipped, keep every clipped negative "
            "outflow value clipped to zero as the script does, and report the native warnings in result.json. "
            "Do not 'fix' the configuration, raise X, reduce reaches, or suppress the warnings."
        )
    else:
        prompt = (
            "Use inflow.csv and route_spec.json exactly as supplied to run hydrological-modeling/route-muskingum-channel. "
            "The inflow table is hourly discharge in m3/s and contains at least one missing value in an inflow column. "
            "Run the routing verbatim with --timestep-hours 1 and only the native result.json under routed/. "
            "Do not fill, interpolate, or drop the missing value; do not rerun with repaired data; the script must reject the input itself. "
            "No routed_flow.csv or route_coefficients.json may remain in routed/."
        )
    required = [f"{OUTPUT_DIR}/result.json"]
    if positive:
        required = [f"{OUTPUT_DIR}/routed_flow.csv", f"{OUTPUT_DIR}/route_coefficients.json", *required]
    return {
        "id": task_id,
        "title": _titles()[index],
        "domain": "model-calibration",
        "difficulty": "intermediate" if index < 3 else "basic",
        "primary_skill": SKILL_REF,
        "secondary_skills": [],
        "prompt": prompt,
        "data_description": "A deterministic hourly Muskingum routing problem with a confirmed route specification and gap-free (or explicitly broken) inflow table.",
        "data_files": ["inflow.csv", "route_spec.json"],
        "required_outputs": required,
        "setup_notes": [
            "The route specification is confirmed by the user and must not be altered.",
            "All inflow values are instantaneous discharge in m3/s on a regular hourly axis.",
            "Do not install software or implement a replacement routing routine.",
        ],
        "timeout_seconds": 300,
        "grading": _positive_grading(_route_ids(index)) if positive else _error_grading(),
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
                "--inflow",
                "inflow.csv",
                "--time-column",
                "time",
                "--timestep-hours",
                "1",
                "--route-spec",
                "route_spec.json",
                "--combine",
                "sum",
                "--output-column",
                "Q_total",
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
    _write_csv(data_dir / "inflow.csv", _inflow_frame(task_id))
    _write_json(data_dir / "route_spec.json", _route_spec(task_id))
    _generate_golden(task_dir, task_id)
    _write_json(task_dir / "task.json", _build_task(task_id))
