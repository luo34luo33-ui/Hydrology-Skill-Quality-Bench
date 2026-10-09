"""Deterministic fixtures for the lumped TOPMODEL benchmark tasks (hydromodel-topmodel-001..003)."""

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
SKILL_REF = "hydrological-modeling/run-lumped-topmodel"
SKILL_FOLDER = "hydrological-modeling/run-lumped-topmodel"
SKILL_SCRIPT = "run_lumped_topmodel.py"
TERRAIN_FOLDER = "spatial-analysis/derive-topmodel-terrain-inputs"
OUTPUT_DIR = "topmodel-run"
TASK_IDS = [f"hydromodel-topmodel-{index:03d}" for index in (1, 2, 3)]
STEPS = 8


def _index(task_id: str) -> int:
    if task_id not in TASK_IDS:
        raise ValueError(f"unsupported topmodel task id: {task_id}")
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


def _skill_root() -> Path:
    configured = os.environ.get("HYDROTUNE_SKILLS_ROOT", "").strip().strip('"')
    return Path(configured) if configured else DEFAULT_SKILLS_ROOT


def _run_terrain_script(work: Path, output: Path) -> None:
    script = _skill_root() / TERRAIN_FOLDER / "examples" / "derive_topmodel_terrain_inputs.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--stream-result",
            "stream_result.json",
            "--topology-result",
            "build_result.json",
            "--topology-qc-result",
            "topology_qc_result.json",
            "--classes",
            "10",
            "--distance-bins",
            "10",
            "--minimum-slope",
            "1e-4",
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
    if completed.returncode != 0:
        raise RuntimeError(f"terrain fixture run failed: {completed.stderr}")


def _build_terrain_fixture(data_dir: Path) -> None:
    """Build the hash-linked terrain fixture (including its own outputs) in data/."""
    with tempfile.TemporaryDirectory(prefix="hsqb-topmodel-terrain-") as raw_temp:
        work = Path(raw_temp) / "workspace"
        work.mkdir(parents=True)
        sys.path.insert(0, str(ROOT.parent / "spatial-analysis"))
        from _terrain_topidx_task_factory import _dem, _pointer, _accumulation, _subbasins, _write_raster, RASTER_NAMES, SUBBASIN_RASTER
        sys.path.pop(0)

        data_dir.mkdir(parents=True, exist_ok=True)

        def reference(path: Path) -> dict[str, Any]:
            return {"path": path.name, "sha256": _sha256(path)}

        artifacts = {}
        for key, (name, dtype, nodata) in RASTER_NAMES.items():
            data = _dem(1) if key == "filled_dem" else (_pointer(1) if key == "d8_pointer" else _accumulation())
            _write_raster(work / name, data, dtype, nodata)
            artifacts[key] = reference(work / name)
        stream = {
            "schema_version": "1.0",
            "skill": "spatial-analysis/extract-dem-stream-network",
            "status": "success",
            "artifacts": artifacts,
            "checks": [{"check": "synthetic_upstream", "status": "PASS", "details": "deterministic benchmark fixture"}],
        }
        _write_json(work / "stream_result.json", stream)
        _write_raster(work / SUBBASIN_RASTER[0], _subbasins(), SUBBASIN_RASTER[1], SUBBASIN_RASTER[2])
        _write_csv(work / "subbasins_table.csv", pd.DataFrame({"sub_id": [1], "area_km2": [9.6e-5], "outlet_reach_ids": ["1"]}))
        build = {
            "schema_version": "1.0",
            "skill": "spatial-analysis/build-hydrological-topology",
            "status": "success",
            "inputs": {key: reference(work / name) for key, (name, _, _) in RASTER_NAMES.items()},
            "artifacts": {
                "subbasins_clipped": {"path": SUBBASIN_RASTER[0], "sha256": _sha256(work / SUBBASIN_RASTER[0])},
                "subbasins_table": {"path": "subbasins_table.csv", "sha256": _sha256(work / "subbasins_table.csv")},
            },
            "checks": [{"check": "synthetic_upstream", "status": "PASS", "details": "deterministic benchmark fixture"}],
        }
        _write_json(work / "build_result.json", build)
        qc = {
            "schema_version": "1.0",
            "skill": "spatial-analysis/validate-hydrological-topology",
            "status": "success",
            "parameters": {"expected_outlets": 1},
            "inputs": {"build_result": {"path": "build_result.json", "sha256": _sha256(work / "build_result.json")}},
            "checks": [{"check": "expected_outlets", "status": "PASS", "details": "single outlet confirmed"}],
        }
        _write_json(work / "topology_qc_result.json", qc)
        _run_terrain_script(work, work / "terrain-out")
        result_path = work / "terrain-out" / "result.json"
        document = json.loads(result_path.read_text(encoding="utf-8-sig"))
        for section in ("inputs", "artifacts"):
            for reference in document.get(section, {}).values():
                if isinstance(reference, dict) and isinstance(reference.get("path"), str):
                    value = Path(reference["path"])
                    if value.is_absolute() or ".." in value.parts or len(value.parts) > 1:
                        reference["path"] = value.name
        document["provenance"] = {"generator": "HydroTune skill script; runtime versions normalized for the golden oracle"}
        result_path.write_bytes(_stable_json(document))
        for source in sorted((work / "terrain-out").iterdir()):
            if source.is_file():
                _write_bytes(data_dir / source.name, source.read_bytes())
        for name in (
            "stream_result.json",
            "build_result.json",
            "topology_qc_result.json",
            "subbasins_table.csv",
            "subbasins_clipped.tif",
            *(name for name, _, _ in RASTER_NAMES.values()),
        ):
            _write_bytes(data_dir / name, (work / name).read_bytes())


def _times() -> list[str]:
    return [stamp.strftime("%Y-%m-%dT%H:%M:%S+08:00") for stamp in pd.date_range("2020-08-01 00:00", periods=STEPS, freq="D")]


def _forcing_frame(index: int) -> pd.DataFrame:
    days = np.arange(STEPS, dtype=float)
    precipitation = np.round(np.where((days >= 2) & (days < 5), 18.0, 0.0), 3)
    frame = pd.DataFrame({"time": _times(), "P": precipitation, "PET": np.round(3.0 + 0.4 * np.sin(days), 3)})
    if index == 3:
        # Confirmed broken forcing: the step at index 4 is missing, so the time
        # axis has a gap and the skill must reject the run.
        frame = frame.drop(index=4).reset_index(drop=True)
    return frame


def _config(index: int) -> dict[str, Any]:
    times = _times()
    parameters: dict[str, Any] = {
        "qs0": 0.05, "lnTe": 2.0, "m": 0.02, "Sr0": 0.05, "Srmax": 0.2,
        "td": 10.0, "vch": 2000.0, "vr": 5000.0, "infiltration_excess": index == 2,
    }
    if index == 2:
        parameters.update({"K0": 50.0, "psi": 0.1, "dtheta": 0.3})
    return {
        "schema_version": "1.0",
        "timestep_hours": 24,
        "timezone": "Asia/Shanghai",
        "timestamp_semantics": "interval_end",
        "forcing_unit": "mm/step",
        "warmup_steps": 2,
        "simulation_start": times[2],
        "simulation_end": times[-1],
        "water_balance_tolerance_m": 1e-6,
        "parameters": parameters,
    }


def _titles() -> dict[int, str]:
    return {
        1: "Run a lumped TOPMODEL simulation on a validated terrain distribution",
        2: "Run TOPMODEL with the confirmed Green-Ampt infiltration-excess branch",
        3: "Reject a TOPMODEL run whose forcing time axis has a gap",
    }


def _prompts() -> dict[int, str]:
    return {
        1: (
            "Use terrain_result.json, forcing.csv, and params.json exactly as supplied to run "
            "hydrological-modeling/run-lumped-topmodel. The terrain result is a hash-checked single-outlet "
            "derive-topmodel-terrain-inputs product (its own HydroBase provenance ships alongside); the forcing is daily with "
            "strict columns time,P,PET (+08:00, mm/step, interval end). "
            "Write the native outputs (process.csv, final_state.json, model_config.json, result.json) under topmodel-run/. "
            "Do not modify the terrain chain, the config, or the forcing."
        ),
        2: (
            "Use terrain_result.json, forcing.csv, and params.json exactly as supplied to run "
            "hydrological-modeling/run-lumped-topmodel. The confirmed configuration enables the Green-Ampt infiltration-excess "
            "branch (parameters K0, psi, dtheta alongside td); run it verbatim. "
            "Write the native outputs (process.csv, final_state.json, model_config.json, result.json) under topmodel-run/. "
            "Do not disable the branch, drop the Green-Ampt parameters, or substitute another runoff partition."
        ),
        3: (
            "Use terrain_result.json, forcing.csv, and params.json exactly as supplied to run "
            "hydrological-modeling/run-lumped-topmodel. The forcing deliberately misses one daily step, leaving a gap in the time "
            "axis; run the skill verbatim and only the native result.json under topmodel-run/. "
            "Do not fill the gap or alter the forcing; the script must reject the run itself. No process.csv, final_state.json, or "
            "model_config.json may remain in topmodel-run/."
        ),
    }


def _positive_grading() -> list[dict[str, Any]]:
    golden = f"expected/golden_workspace/{OUTPUT_DIR}"
    result = f"{OUTPUT_DIR}/result.json"
    return [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": [f"{OUTPUT_DIR}/process.csv", f"{OUTPUT_DIR}/final_state.json", f"{OUTPUT_DIR}/model_config.json", result],
            "required_columns": {
                f"{OUTPUT_DIR}/process.csv": ["time", "warmup", "P_mm", "PET_mm", "outlet_m3_s", "water_balance_residual_mm"],
                f"{OUTPUT_DIR}/final_state.json": ["mean_deficit_m", "root_deficit_m", "routing_m", "routing_storage_m"],
                f"{OUTPUT_DIR}/model_config.json": ["schema_version", "timestep_hours", "timezone", "timestamp_semantics", "forcing_unit", "warmup_steps", "simulation_start", "simulation_end", "water_balance_tolerance_m", "parameters"],
                result: ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"],
            },
            "weight": 0.10,
        },
        {
            "name": "process_table",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/process.csv",
            "reference": f"{golden}/process.csv",
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
            "required_keys": ["process.csv", "final_state.json", "model_config.json"],
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
            "required_columns": ["schema_version", "skill", "status", "message", "inputs", "artifacts", "checks", "warnings"],
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
            "targets": [f"{OUTPUT_DIR}/process.csv", f"{OUTPUT_DIR}/final_state.json", f"{OUTPUT_DIR}/model_config.json"],
            "weight": 0.20,
        },
    ]


def _build_task(task_id: str) -> dict[str, Any]:
    index = _index(task_id)
    positive = index < 3
    required = [f"{OUTPUT_DIR}/result.json"]
    if positive:
        required = [
            f"{OUTPUT_DIR}/process.csv",
            f"{OUTPUT_DIR}/final_state.json",
            f"{OUTPUT_DIR}/model_config.json",
            *required,
        ]
    data_files = [
        "terrain_result.json",
        "topographic_index.tif",
        "topographic_index_classes.csv",
        "distance_area.csv",
        "stream_result.json",
        "build_result.json",
        "topology_qc_result.json",
        "subbasins_table.csv",
        "subbasins_clipped.tif",
        "filled_dem.tif",
        "d8_pointer.tif",
        "flow_accumulation_cells.tif",
        "forcing.csv",
        "params.json",
    ]
    return {
        "id": task_id,
        "title": _titles()[index],
        "domain": "model-calibration",
        "difficulty": "intermediate" if index < 3 else "basic",
        "primary_skill": SKILL_REF,
        "secondary_skills": [],
        "prompt": _prompts()[index],
        "data_description": "A deterministic lumped TOPMODEL fixture consuming a hash-checked terrain product and its HydroBase provenance.",
        "data_files": data_files,
        "required_outputs": required,
        "setup_notes": [
            "The terrain chain and the model configuration are confirmed by the user and must not be altered.",
            "Forcing timestamps carry explicit +08:00 offsets with interval_end semantics.",
            "Do not install software or implement a replacement TOPMODEL.",
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
                str(_skill_root() / SKILL_FOLDER / "examples" / SKILL_SCRIPT),
                "--terrain-result",
                "terrain_result.json",
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
    if data_dir.exists():
        shutil.rmtree(data_dir)
    _build_terrain_fixture(data_dir)
    shutil.copy(data_dir / "result.json", data_dir / "terrain_result.json")
    _write_csv(data_dir / "forcing.csv", _forcing_frame(index))
    _write_json(data_dir / "params.json", _config(index))
    _generate_golden(task_dir, task_id)
    _write_json(task_dir / "task.json", _build_task(task_id))
