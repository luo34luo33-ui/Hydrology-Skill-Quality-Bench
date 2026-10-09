"""Deterministic fixtures for the semi-distributed SWAT benchmark tasks (hydromodel-swat-sd-001..003)."""

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
SKILL_REF = "hydrological-modeling/run-semi-distributed-swat-model"
SKILL_FOLDER = "hydrological-modeling/run-semi-distributed-swat-model"
SKILL_SCRIPT = "run_semi_distributed_swat.py"
OUTPUT_DIR = "swat-sd-run"
TASK_IDS = [f"hydromodel-swat-sd-{index:03d}" for index in (1, 2, 3)]

STEPS = 30


def _index(task_id: str) -> int:
    if task_id not in TASK_IDS:
        raise ValueError(f"unsupported swat-sd task id: {task_id}")
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
        raise FileNotFoundError(f"swat-sd skill script not found: {script}")
    return script


def _times() -> list[str]:
    return [stamp.strftime("%Y-%m-%dT%H:%M:%S+08:00") for stamp in pd.date_range("2020-07-01 00:00", periods=STEPS, freq="D")]


def _hydrobase(data_dir: Path, index: int) -> None:
    sub_area = [1.0, 1.0] if index < 3 else [1.0, 1.0]
    subbasins = pd.DataFrame({"sub_id": [1, 2], "area_km2": sub_area, "outlet_reach_ids": ["1", "2"]})
    reaches = pd.DataFrame({"reach_id": [1, 2], "sub_id": [1, 2], "downstream_reach_id": [2, 0]})
    topology = pd.DataFrame({"reach_id": [1, 2], "sub_id": [1, 2], "downstream_reach_id": [2, 0]})
    _write_csv(data_dir / "subbasins_table.csv", subbasins)
    _write_csv(data_dir / "reaches_table.csv", reaches)
    _write_csv(data_dir / "topology_table.csv", topology)
    artifacts = {
        key: {"path": f"{key}.csv", "sha256": _sha256(data_dir / f"{key}.csv")}
        for key in ("subbasins_table", "reaches_table", "topology_table")
    }
    build = {
        "schema_version": "1.0",
        "skill": "spatial-analysis/build-hydrological-topology",
        "status": "success",
        "artifacts": artifacts,
        "checks": [{"check": "synthetic_upstream", "status": "PASS", "details": "deterministic benchmark fixture"}],
    }
    _write_json(data_dir / "build_result.json", build)
    qc = {
        "schema_version": "1.0",
        "skill": "spatial-analysis/validate-hydrological-topology",
        "status": "success",
        "parameters": {"expected_outlets": 1},
        "inputs": {"build_result": {"path": "build_result.json", "sha256": _sha256(data_dir / "build_result.json")}},
        "checks": [{"check": "expected_outlets", "status": "PASS", "details": "single outlet confirmed"}],
    }
    _write_json(data_dir / "topology_qc_result.json", qc)


def _hru_frame(index: int) -> pd.DataFrame:
    common = {
        "cn2": [75.0, 78.0], "canmx_mm": [2.0, 2.0], "brt": [0.5, 0.5], "latq_co": [0.05, 0.05],
        "lat_ttime_days": [3.0, 3.0], "slope_m_m": [0.05, 0.07], "lat_len_m": [50.0, 60.0],
        "perco_lim": [0.5, 0.5], "cn3_swf": [0.5, 0.5], "esco": [0.95, 0.95], "ep_frac": [0.85, 0.85],
        "aquifer_alpha": [0.05, 0.05], "aquifer_seep_frac": [0.4, 0.4], "aquifer_specific_yield": [0.15, 0.15],
        "aquifer_dep_bot_m": [5.0, 5.0], "aquifer_flo_min_m": [1.0, 1.0], "aquifer_revap_co": [0.05, 0.05],
        "aquifer_revap_min_m": [1.0, 1.0],
        "soil_1_thickness_mm": [800.0, 800.0], "soil_1_fc_mm": [300.0, 300.0], "soil_1_ul_mm": [350.0, 350.0],
        "soil_1_wp_mm_per_mm": [0.15, 0.15], "soil_1_ksat_mm_hr": [10.0, 10.0],
    }
    area = [1.0, 1.0] if index < 3 else [1.2, 1.0]
    frame = pd.DataFrame({"hru_id": [1, 2], "sub_id": [1, 2], "area_km2": area, **common})
    if index == 3:
        # Confirmed broken HRU table: the HRU areas no longer sum to the
        # subbasins_table areas, which the skill must reject.
        frame.loc[0, "area_km2"] = 1.2
    return frame


def _forcing_frame() -> pd.DataFrame:
    days = np.arange(STEPS, dtype=float)
    frames = []
    for sub_id, phase in ((1, 0.0), (2, np.pi / 2.0)):
        precipitation = np.round(np.where((days >= 5) & (days < 9), 20.0, 0.0) + np.where((days >= 15) & (days < 18), 12.0, 0.0) + phase * 0.0, 3)
        evaporation = np.round(3.0 + 0.4 * np.sin(2.0 * np.pi * days / STEPS + phase), 3)
        frames.append(pd.DataFrame({"time": _times(), "sub_id": sub_id, "P_mm": precipitation, "E0_mm": evaporation}))
    return pd.concat(frames, ignore_index=True)


def _config(index: int) -> dict[str, Any]:
    times = _times()
    channel_profile = "muskingum" if index == 2 else "linear_storage"
    musk_k = 10.0 if index == 2 else 18.0
    return {
        "schema_version": "1.0",
        "time": {"step_seconds": 86400, "timezone": "Asia/Shanghai", "timestamp_meaning": "interval_end"},
        "swat": {"profile": "simplified", "cn_mode": "static", "channel_profile": channel_profile},
        "initial": {"soil_fraction": 0.4},
        "reach_params_by_id": {
            "1": {"musk_k_hr": musk_k, "musk_x": 0.2, "ttime_hr": 4.0, "scoef": 1.0, "trans_loss_m3_day": 0.0, "evap_m3_day": 0.0},
            "2": {"musk_k_hr": musk_k, "musk_x": 0.2, "ttime_hr": 4.0, "scoef": 1.0, "trans_loss_m3_day": 0.0, "evap_m3_day": 0.0},
        },
        "parameter_overrides": {},
        "warmup_steps": 5,
        "simulation": {"start": times[5], "end": times[-1]},
    }


def _titles() -> dict[int, str]:
    return {
        1: "Run a semi-distributed SWAT simulation over a two-reach network",
        2: "Preserve the native Muskingum stability warning on the daily channel",
        3: "Reject a SWAT run whose HRU areas disagree with the subbasin table",
    }


def _prompts() -> dict[int, str]:
    return {
        1: (
            "Use build_result.json, topology_qc_result.json, hru_table.csv, forcing.csv, and params.json exactly as supplied to run "
            "hydrological-modeling/run-semi-distributed-swat-model. The HydroBase chain is a hash-checked two-subbasin, two-reach "
            "serial network; the HRU table assigns one HRU per subbasin and the forcing is daily (columns time,sub_id,P_mm,E0_mm, "
            "+08:00). "
            "Write the native outputs (hru_process.csv, subbasin_process.csv, reach_process.csv, outlet_flow.csv, "
            "water_balance.json, model_config.json, result.json) under swat-sd-run/. "
            "Do not modify the topology, HRU table, parameters, or forcing."
        ),
        2: (
            "Use build_result.json, topology_qc_result.json, hru_table.csv, forcing.csv, and params.json exactly as supplied to run "
            "hydrological-modeling/run-semi-distributed-swat-model. The confirmed configuration selects channel_profile=muskingum "
            "with musk_k_hr=10 on a daily step, which makes the Muskingum C3 coefficient negative; the skill must report the native "
            "muskingum_daily_stability warning while still writing every artifact. "
            "Write the native outputs (hru_process.csv, subbasin_process.csv, reach_process.csv, outlet_flow.csv, "
            "water_balance.json, model_config.json, result.json) under swat-sd-run/. "
            "Do not switch to linear_storage, raise musk_k_hr, or suppress the warning."
        ),
        3: (
            "Use build_result.json, topology_qc_result.json, hru_table.csv, forcing.csv, and params.json exactly as supplied to run "
            "hydrological-modeling/run-semi-distributed-swat-model. The HRU table deliberately disagrees with the subbasin areas "
            "(HRU 1 area 1.2 km2 vs subbasin 1.0 km2); run the skill verbatim and only the native result.json under swat-sd-run/. "
            "Do not rebalance the areas; the script must reject the input itself. No hru_process.csv, subbasin_process.csv, "
            "reach_process.csv, or outlet_flow.csv may remain in swat-sd-run/."
        ),
    }


def _positive_grading() -> list[dict[str, Any]]:
    golden = f"expected/golden_workspace/{OUTPUT_DIR}"
    result = f"{OUTPUT_DIR}/result.json"
    return [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": [
                f"{OUTPUT_DIR}/hru_process.csv",
                f"{OUTPUT_DIR}/outlet_flow.csv",
                f"{OUTPUT_DIR}/water_balance.json",
                f"{OUTPUT_DIR}/model_config.json",
                result,
            ],
            "required_columns": {
                f"{OUTPUT_DIR}/hru_process.csv": ["time", "hru_id"],
                f"{OUTPUT_DIR}/outlet_flow.csv": ["time", "outlet_reach_id", "Q_m3s"],
                f"{OUTPUT_DIR}/water_balance.json": ["tolerances", "max_abs_residual", "basin_fluxes_m3", "checks"],
                f"{OUTPUT_DIR}/model_config.json": ["schema_version", "time", "swat", "initial", "reach_params_by_id", "parameter_overrides", "warmup_steps", "simulation"],
                result: ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"],
            },
            "weight": 0.10,
        },
        {
            "name": "outlet_flow",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/outlet_flow.csv",
            "reference": f"{golden}/outlet_flow.csv",
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
            "required_keys": ["hru_process", "subbasin_process", "reach_process", "outlet_flow", "water_balance", "model_config"],
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
            "targets": [f"{OUTPUT_DIR}/hru_process.csv", f"{OUTPUT_DIR}/subbasin_process.csv", f"{OUTPUT_DIR}/reach_process.csv", f"{OUTPUT_DIR}/outlet_flow.csv"],
            "weight": 0.20,
        },
    ]


def _build_task(task_id: str) -> dict[str, Any]:
    index = _index(task_id)
    positive = index < 3
    required = [f"{OUTPUT_DIR}/result.json"]
    if positive:
        required = [
            f"{OUTPUT_DIR}/hru_process.csv",
            f"{OUTPUT_DIR}/subbasin_process.csv",
            f"{OUTPUT_DIR}/reach_process.csv",
            f"{OUTPUT_DIR}/outlet_flow.csv",
            f"{OUTPUT_DIR}/water_balance.json",
            f"{OUTPUT_DIR}/model_config.json",
            *required,
        ]
    return {
        "id": task_id,
        "title": _titles()[index],
        "domain": "model-calibration",
        "difficulty": "intermediate" if index < 3 else "basic",
        "primary_skill": SKILL_REF,
        "secondary_skills": [],
        "prompt": _prompts()[index],
        "data_description": "A deterministic semi-distributed SWAT fixture over a hash-checked two-reach HydroBase network.",
        "data_files": ["build_result.json", "topology_qc_result.json", "hru_table.csv", "forcing.csv", "params.json"],
        "required_outputs": required,
        "setup_notes": [
            "The HydroBase chain, HRU table, and SWAT configuration are confirmed by the user and must not be altered.",
            "The SWAT core is an LGPL-2.1-derived simplification; provenance in result.json records NOT VERIFIED by design.",
            "Do not install software or implement a replacement model.",
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
                value = Path(reference["path"])
                if value.is_absolute() or ".." in value.parts or len(value.parts) > 1:
                    reference["path"] = value.name
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
                "--topology-result",
                "build_result.json",
                "--topology-qc-result",
                "topology_qc_result.json",
                "--hru-table",
                "hru_table.csv",
                "--forcing",
                "forcing.csv",
                "--params",
                "params.json",
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
    index = _index(task_id)
    task_dir = ROOT / task_id
    data_dir = task_dir / "data"
    _hydrobase(data_dir, index)
    _write_csv(data_dir / "hru_table.csv", _hru_frame(index))
    _write_csv(data_dir / "forcing.csv", _forcing_frame())
    _write_json(data_dir / "params.json", _config(index))
    _generate_golden(task_dir, task_id)
    _write_json(task_dir / "task.json", _build_task(task_id))
