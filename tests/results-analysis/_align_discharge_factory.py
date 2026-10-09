"""Deterministic fixtures for the discharge alignment benchmark tasks (hydroanalysis-align-discharge-001..003)."""

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
SKILL_REF = "post-processing/align-observed-simulated-discharge"
SKILL_FOLDER = "post-processing/align-observed-simulated-discharge"
SKILL_SCRIPT = "align_observed_simulated_discharge.py"
OUTPUT_DIR = "align-out"
TASK_IDS = [f"hydroanalysis-align-discharge-{index:03d}" for index in (1, 2, 3)]


def _index(task_id: str) -> int:
    if task_id not in TASK_IDS:
        raise ValueError(f"unsupported align task id: {task_id}")
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
        raise FileNotFoundError(f"align skill script not found: {script}")
    return script


def _timestamps(count: int) -> list[str]:
    return [f"2020-01-01T{hour:02d}:00:00+08:00" for hour in range(1, count + 1)]


def _observed_frame() -> pd.DataFrame:
    values = [1.0, 2.0, 1.5, 1.2, 1.8, 0.9]
    return pd.DataFrame({"time": _timestamps(6), "discharge_m3_s": values})


def _simulation_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": _timestamps(6),
            "Q": [1.1, 1.8, 1.6, 1.3, 1.9, 1.0],
            "is_warmup": [True, True, False, False, False, False],
        }
    )


def _upstream_result(skill: str, key: str, artifact_name: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "skill": skill,
        "status": "success",
        "artifacts": {key: {"path": artifact_name, "sha256": None}},
        "checks": [{"check": "synthetic_upstream", "status": "PASS", "details": "deterministic benchmark fixture"}],
    }


def _write_upstream_pair(data_dir: Path, result_name: str, skill: str, key: str, csv_name: str, frame: pd.DataFrame) -> None:
    _write_csv(data_dir / csv_name, frame)
    document = _upstream_result(skill, key, csv_name)
    document["artifacts"][key]["sha256"] = _sha256(data_dir / csv_name)
    _write_json(data_dir / result_name, document)


def _data_files(index: int) -> None:
    task_dir = ROOT / f"hydroanalysis-align-discharge-{index:03d}"
    data_dir = task_dir / "data"
    if index < 3:
        _write_upstream_pair(data_dir, "observed_result.json", "data-processing/prepare-discharge-timeseries", "discharge_timeseries", "observed.csv", _observed_frame())
        _write_upstream_pair(data_dir, "simulation_result.json", "hydrological-modeling/run-lumped-hbv-model", "simulation_table", "simulated.csv", _simulation_frame())
        return
    # 003: the confirmed simulation artifact claims lumped XAJ, whose Qt is the
    # channel entry flow; the skill must reject it outright.
    _write_upstream_pair(data_dir, "observed_result.json", "data-processing/prepare-discharge-timeseries", "discharge_timeseries", "observed.csv", _observed_frame())
    _write_upstream_pair(data_dir, "simulation_result.json", "hydrological-modeling/run-lumped-xaj-model", "simulation_table", "simulated.csv", _simulation_frame())


def _titles() -> dict[int, str]:
    return {
        1: "Align observed discharge with an HBV outlet simulation",
        2: "Exclude warm-up steps and unmatched observations during alignment",
        3: "Reject lumped XAJ output as an alignment simulation source",
    }


def _prompts() -> dict[int, str]:
    return {
        1: (
            "Use observed_result.json and simulation_result.json exactly as supplied to run "
            "post-processing/align-observed-simulated-discharge. The observed artifact is a prepare-discharge-timeseries result and "
            "the simulation artifact is a lumped HBV result; both are hash-checked by the skill. "
            "Write the native outputs (aligned_discharge.csv, evaluation_discharge.csv, excluded_observations.csv, "
            "alignment_qc.json, result.json) under align-out/. "
            "Do not modify the upstream artifacts or relax the hash checks."
        ),
        2: (
            "Use observed_result.json and simulation_result.json exactly as supplied to run "
            "post-processing/align-observed-simulated-discharge. The simulation flags its first two steps as warm-up, and the "
            "observations deliberately cover two extra timestamps beyond the simulation window; the native alignment must exclude "
            "warm-up rows from the evaluation table and record the unmatched observations in excluded_observations.csv. "
            "Write the native outputs (aligned_discharge.csv, evaluation_discharge.csv, excluded_observations.csv, "
            "alignment_qc.json, result.json) under align-out/. "
            "Do not trim the inputs yourself or force the extra timestamps into the evaluation table."
        ),
        3: (
            "Use observed_result.json and simulation_result.json exactly as supplied to run "
            "post-processing/align-observed-simulated-discharge. The simulation artifact is deliberately declared as lumped XAJ, "
            "whose Qt is the channel entry flow rather than an outlet discharge; run the skill verbatim and only the native "
            "result.json under align-out/. "
            "Do not relabel the artifact or substitute another adapter; the skill must reject the source itself. "
            "No aligned_discharge.csv, evaluation_discharge.csv, excluded_observations.csv, or alignment_qc.json may remain in align-out/."
        ),
    }


def _positive_grading(index: int) -> list[dict[str, Any]]:
    golden = f"expected/golden_workspace/{OUTPUT_DIR}"
    result = f"{OUTPUT_DIR}/result.json"
    criteria: list[dict[str, Any]] = [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": [f"{OUTPUT_DIR}/aligned_discharge.csv", f"{OUTPUT_DIR}/evaluation_discharge.csv", f"{OUTPUT_DIR}/alignment_qc.json", result],
            "required_columns": {
                f"{OUTPUT_DIR}/aligned_discharge.csv": ["time", "simulated_m3_s", "observed_m3_s", "matched", "excluded_reason"],
                f"{OUTPUT_DIR}/evaluation_discharge.csv": ["time", "observed_m3_s", "simulated_m3_s"],
                f"{OUTPUT_DIR}/alignment_qc.json": ["model", "simulation_rows", "matched_rows", "warmup_excluded", "evaluation_rows"],
                result: ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"],
            },
            "weight": 0.10,
        },
        {
            "name": "aligned_table",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/aligned_discharge.csv",
            "reference": f"{golden}/aligned_discharge.csv",
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.20,
        },
        {
            "name": "evaluation_table",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/evaluation_discharge.csv",
            "reference": f"{golden}/evaluation_discharge.csv",
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.15,
        },
        {
            "name": "excluded_observations",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/excluded_observations.csv",
            "reference": f"{golden}/excluded_observations.csv",
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.10,
        },
        {"name": "alignment_qc", "type": "exact_match", "target": f"{OUTPUT_DIR}/alignment_qc.json", "reference": f"{golden}/alignment_qc.json", "weight": 0.10},
        {"name": "result_skill", "type": "exact_match", "target": result, "field": "skill", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_status", "type": "exact_match", "target": result, "field": "status", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_message", "type": "exact_match", "target": result, "field": "message", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_checks", "type": "exact_match", "target": result, "field": "checks", "reference": f"{golden}/result.json", "weight": 0.05},
        {
            "name": "artifact_references",
            "type": "artifact_reference_check",
            "target": result,
            "required_keys": ["aligned", "evaluation", "excluded_observations", "qc"],
            "weight": 0.15,
        },
    ]
    total = sum(criterion["weight"] for criterion in criteria)
    if abs(total - 1.0) > 1e-9:
        raise RuntimeError(f"align-{index:03d} grading weights sum to {total}")
    return criteria


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
            "targets": [
                f"{OUTPUT_DIR}/aligned_discharge.csv",
                f"{OUTPUT_DIR}/evaluation_discharge.csv",
                f"{OUTPUT_DIR}/excluded_observations.csv",
                f"{OUTPUT_DIR}/alignment_qc.json",
            ],
            "weight": 0.20,
        },
    ]


def _build_task(task_id: str) -> dict[str, Any]:
    index = _index(task_id)
    positive = index < 3
    required = [f"{OUTPUT_DIR}/result.json"]
    if positive:
        required = [
            f"{OUTPUT_DIR}/aligned_discharge.csv",
            f"{OUTPUT_DIR}/evaluation_discharge.csv",
            f"{OUTPUT_DIR}/excluded_observations.csv",
            f"{OUTPUT_DIR}/alignment_qc.json",
            *required,
        ]
    data_files = ["observed.csv", "observed_result.json", "simulated.csv", "simulation_result.json"]
    return {
        "id": task_id,
        "title": _titles()[index],
        "domain": "results-analysis",
        "difficulty": "intermediate" if index < 3 else "basic",
        "primary_skill": SKILL_REF,
        "secondary_skills": [],
        "prompt": _prompts()[index],
        "data_description": "A deterministic discharge-alignment fixture with hash-verified synthetic upstream results.",
        "data_files": data_files,
        "required_outputs": required,
        "setup_notes": [
            "The upstream results are consumed by their native adapters and hash checks; they must not be altered.",
            "Timestamps carry explicit +08:00 offsets on a complete hourly axis.",
            "Do not install software or implement a replacement alignment.",
        ],
        "timeout_seconds": 300,
        "grading": _positive_grading(index) if positive else _error_grading(),
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
                "--observed-result",
                "observed_result.json",
                "--simulation-result",
                "simulation_result.json",
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
    index = _index(task_id)
    task_dir = ROOT / task_id
    _data_files(index)
    _generate_golden(task_dir, task_id)
    _write_json(task_dir / "task.json", _build_task(task_id))
