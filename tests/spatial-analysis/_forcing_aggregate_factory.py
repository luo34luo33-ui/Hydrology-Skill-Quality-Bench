"""Deterministic fixtures for the forcing-aggregation benchmark tasks (hydrodata-forcing-aggregate-001..003)."""

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
import rasterio
from rasterio.transform import from_origin


ROOT = Path(__file__).resolve().parent
DEFAULT_SKILLS_ROOT = Path(r"E:\HydroTune-Skills（仿BioSkills版）")
SKILL_REF = "spatial-analysis/aggregate-forcing-to-model-units"
SKILL_FOLDER = "spatial-analysis/aggregate-forcing-to-model-units"
SKILL_SCRIPT = "aggregate_forcing_to_model_units.py"
OUTPUT_DIR = "aggregate-out"
TASK_IDS = [f"hydrodata-forcing-aggregate-{index:03d}" for index in (1, 2, 3)]

CRS = "EPSG:32649"
TRANSFORM = from_origin(500000.0, 4000000.0, 1.0, 1.0)
STATION_COORDS = pd.DataFrame(
    {
        "source_id": ["A", "B"],
        "x": [500001.2, 500006.5],
        "y": [3999994.3, 3999994.7],
    }
)
STEPS = 12


def _index(task_id: str) -> int:
    if task_id not in TASK_IDS:
        raise ValueError(f"unsupported forcing-aggregate task id: {task_id}")
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
        raise FileNotFoundError(f"forcing-aggregate skill script not found: {script}")
    return script


def _times() -> list[str]:
    return [stamp.strftime("%Y-%m-%dT%H:%M:%S+08:00") for stamp in pd.date_range("2020-07-01 00:00", periods=STEPS, freq="D")]


def _station_series(station: str, offset: float) -> np.ndarray:
    days = np.arange(STEPS, dtype=float)
    return np.round(offset + 1.5 * np.sin(2.0 * np.pi * days / STEPS), 3)


def _forcing_csv(data_dir: Path, name: str, variable: str, index: int) -> None:
    frames = []
    for station, offset in (("A", 3.0), ("B", 2.0)):
        values = _station_series(station, offset)
        frames.append(pd.DataFrame({"time": _times(), "source_id": station, "variable": variable, "depth_mm": values}))
    frame = pd.concat(frames, ignore_index=True)
    if index == 3 and variable == "E0":
        # Confirmed broken source: station B misses the final step, so the two
        # station axes disagree and the skill must reject the aggregation.
        frame = frame[~((frame.source_id == "B") & (frame.time == _times()[-1]))]
    _write_csv(data_dir / name, frame)


def _upstream_result(path: Path, skill: str, key: str, artifact_name: str) -> None:
    document = {
        "schema_version": "1.0",
        "skill": skill,
        "status": "success",
        "artifacts": {key: {"path": artifact_name, "sha256": _sha256(path.parent / artifact_name)}},
        "checks": [{"check": "synthetic_upstream", "status": "PASS", "details": "deterministic benchmark fixture"}],
    }
    _write_json(path, document)


def _hydrobase(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    basins = np.zeros((12, 8), dtype="int32")
    basins[:, 0:4] = 1
    basins[:, 4:8] = 2
    with rasterio.open(
        data_dir / "subbasins_clipped.tif",
        "w",
        driver="GTiff",
        height=12,
        width=8,
        count=1,
        dtype="int32",
        crs=CRS,
        transform=TRANSFORM,
        nodata=0,
    ) as dataset:
        dataset.write(basins, 1)
    table = pd.DataFrame({"sub_id": [1, 2], "area_km2": [4.8e-5, 4.8e-5]})
    _write_csv(data_dir / "subbasins_table.csv", table)
    document = {
        "schema_version": "1.0",
        "skill": "spatial-analysis/build-hydrological-topology",
        "status": "success",
        "artifacts": {
            "subbasins_clipped": {"path": "subbasins_clipped.tif", "sha256": _sha256(data_dir / "subbasins_clipped.tif")},
            "subbasins_table": {"path": "subbasins_table.csv", "sha256": _sha256(data_dir / "subbasins_table.csv")},
        },
        "checks": [{"check": "synthetic_upstream", "status": "PASS", "details": "deterministic benchmark fixture"}],
    }
    _write_json(data_dir / "build_result.json", document)
    qc = {
        "schema_version": "1.0",
        "skill": "spatial-analysis/validate-hydrological-topology",
        "status": "success",
        "parameters": {"expected_outlets": 1},
        "inputs": {"build_result": {"path": "build_result.json", "sha256": _sha256(data_dir / "build_result.json")}},
        "checks": [{"check": "expected_outlets", "status": "PASS", "details": "single outlet confirmed"}],
    }
    _write_json(data_dir / "topology_qc_result.json", qc)


def _titles() -> dict[int, str]:
    return {
        1: "Aggregate station forcing to subbasin model units with Thiessen weights",
        2: "Aggregate station forcing to the whole-basin unit",
        3: "Reject aggregation when a station misses a forcing step",
    }


def _prompts() -> dict[int, str]:
    return {
        1: (
            "Use build_result.json, topology_qc_result.json, and source_config.json exactly as supplied to run "
            "spatial-analysis/aggregate-forcing-to-model-units with --target subbasin. "
            "The P layer comes from a prepare-model-forcing result and the E0 layer from a derive-potential-evapotranspiration "
            "result (both hash-checked); station coordinates are confirmed in EPSG:32649. "
            "Write the native outputs (subbasin_forcing.csv, weights.csv, coverage.csv, result.json) under aggregate-out/. "
            "Do not modify the upstream artifacts, redistribute weights, or fill missing values."
        ),
        2: (
            "Use build_result.json, topology_qc_result.json, and source_config.json exactly as supplied to run "
            "spatial-analysis/aggregate-forcing-to-model-units with --target basin. "
            "The P layer comes from a prepare-model-forcing result and the PET layer from a derive-potential-evapotranspiration "
            "result (both hash-checked); the confirmed target merges both subbasins into one basin unit. "
            "Write the native outputs (basin_forcing.csv, weights.csv, coverage.csv, result.json) under aggregate-out/. "
            "Do not modify the upstream artifacts or aggregate with weights of your own."
        ),
        3: (
            "Use build_result.json, topology_qc_result.json, and source_config.json exactly as supplied to run "
            "spatial-analysis/aggregate-forcing-to-model-units with --target subbasin. "
            "The E0 source deliberately misses the final step for station B; run the skill verbatim and only the native result.json "
            "under aggregate-out/. "
            "Do not drop the step, interpolate, or repair the source; the script must reject the input itself. "
            "No subbasin_forcing.csv, weights.csv, or coverage.csv may remain in aggregate-out/."
        ),
    }


def _positive_grading() -> list[dict[str, Any]]:
    golden = f"expected/golden_workspace/{OUTPUT_DIR}"
    result = f"{OUTPUT_DIR}/result.json"
    forcing_name = "subbasin_forcing.csv"
    return [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": [f"{OUTPUT_DIR}/{forcing_name}", f"{OUTPUT_DIR}/weights.csv", f"{OUTPUT_DIR}/coverage.csv", result],
            "required_columns": {
                f"{OUTPUT_DIR}/{forcing_name}": ["time", "sub_id", "P_mm", "E0_mm"],
                f"{OUTPUT_DIR}/weights.csv": ["unit_id", "source_id", "weight", "area_m2", "variable"],
                f"{OUTPUT_DIR}/coverage.csv": ["variable", "unit_id", "coverage_fraction", "covered_area_m2", "unit_area_m2"],
                result: ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"],
            },
            "weight": 0.10,
        },
        {
            "name": "forcing_table",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/{forcing_name}",
            "reference": f"{golden}/{forcing_name}",
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.30,
        },
        {
            "name": "weights_table",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/weights.csv",
            "reference": f"{golden}/weights.csv",
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.10,
        },
        {
            "name": "coverage_table",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/coverage.csv",
            "reference": f"{golden}/coverage.csv",
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.10,
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
            "required_keys": ["forcing", "weights", "coverage"],
            "weight": 0.15,
        },
    ]


def _basin_grading() -> list[dict[str, Any]]:
    criteria = _positive_grading()
    for criterion in criteria:
        if criterion["name"] == "artifact_schema":
            criterion["required_columns"].pop(f"{OUTPUT_DIR}/subbasin_forcing.csv", None)
            criterion["required_columns"][f"{OUTPUT_DIR}/basin_forcing.csv"] = ["time", "P", "PET"]
            criterion["targets"] = [f"{OUTPUT_DIR}/basin_forcing.csv", f"{OUTPUT_DIR}/weights.csv", f"{OUTPUT_DIR}/coverage.csv", f"{OUTPUT_DIR}/result.json"]
        elif criterion["name"] == "forcing_table":
            criterion["target"] = f"{OUTPUT_DIR}/basin_forcing.csv"
            criterion["reference"] = f"expected/golden_workspace/{OUTPUT_DIR}/basin_forcing.csv"
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
            "targets": [f"{OUTPUT_DIR}/subbasin_forcing.csv", f"{OUTPUT_DIR}/weights.csv", f"{OUTPUT_DIR}/coverage.csv"],
            "weight": 0.20,
        },
    ]


def _build_task(task_id: str) -> dict[str, Any]:
    index = _index(task_id)
    positive = index < 3
    basin = index == 2
    required = [f"{OUTPUT_DIR}/result.json"]
    if positive:
        forcing_name = "basin_forcing.csv" if basin else "subbasin_forcing.csv"
        required = [f"{OUTPUT_DIR}/{forcing_name}", f"{OUTPUT_DIR}/weights.csv", f"{OUTPUT_DIR}/coverage.csv", *required]
    return {
        "id": task_id,
        "title": _titles()[index],
        "domain": "spatial-analysis",
        "difficulty": "intermediate" if index < 3 else "basic",
        "primary_skill": SKILL_REF,
        "secondary_skills": [],
        "prompt": _prompts()[index],
        "data_description": "A deterministic station-forcing aggregation fixture over a hash-checked two-subbasin HydroBase.",
        "data_files": [
            "build_result.json",
            "topology_qc_result.json",
            "subbasins_clipped.tif",
            "subbasins_table.csv",
            "stations.csv",
            "p_result.json",
            "p_forcing.csv",
            "evap_result.json",
            "evap_forcing.csv",
            "source_config.json",
        ],
        "required_outputs": required,
        "setup_notes": [
            "The upstream results and the source config are consumed by native hash checks; they must not be altered.",
            "Station coordinates are confirmed in EPSG:32649 and the Thiessen weights follow from them.",
            "Do not install software or implement a replacement aggregation.",
        ],
        "timeout_seconds": 300,
        "grading": (_basin_grading() if basin else _positive_grading()) if positive else _error_grading(),
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
                "--source-config",
                "source_config.json",
                "--target",
                "basin" if index == 2 else "subbasin",
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
    _hydrobase(data_dir)
    _write_csv(data_dir / "stations.csv", STATION_COORDS)
    evap_variable = "PET" if index == 2 else "E0"
    _forcing_csv(data_dir, "p_forcing.csv", "P", index)
    _forcing_csv(data_dir, "evap_forcing.csv", evap_variable, index)
    _upstream_result(data_dir / "p_result.json", "data-processing/prepare-model-forcing-timeseries", "forcing", "p_forcing.csv")
    _upstream_result(data_dir / "evap_result.json", "data-processing/derive-potential-evapotranspiration", "mapped_evap", "evap_forcing.csv")
    config = {
        "min_coverage_fraction": 0.999999,
        "layers": {
            "P": {"kind": "station", "variable": "P", "result": "p_result.json", "stations": "stations.csv", "station_crs": CRS},
            "evap": {"kind": "station", "variable": evap_variable, "result": "evap_result.json", "stations": "stations.csv", "station_crs": CRS},
        },
    }
    _write_json(data_dir / "source_config.json", config)
    _generate_golden(task_dir, task_id)
    _write_json(task_dir / "task.json", _build_task(task_id))
