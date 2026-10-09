"""Deterministic fixtures for the TOPMODEL terrain-input benchmark tasks (hydrodata-terrain-topidx-001..003)."""

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
import rasterio
from rasterio.transform import from_origin


ROOT = Path(__file__).resolve().parent
DEFAULT_SKILLS_ROOT = Path(r"E:\HydroTune-Skills（仿BioSkills版）")
SKILL_REF = "spatial-analysis/derive-topmodel-terrain-inputs"
SKILL_FOLDER = "spatial-analysis/derive-topmodel-terrain-inputs"
SKILL_SCRIPT = "derive_topmodel_terrain_inputs.py"
OUTPUT_DIR = "terrain-out"
TASK_IDS = [f"hydrodata-terrain-topidx-{index:03d}" for index in (1, 2, 3)]

CRS = "EPSG:32649"
TRANSFORM = from_origin(500000.0, 4000000.0, 1.0, 1.0)
RASTER_NAMES = {
    "filled_dem": ("filled_dem.tif", "float32", -9999.0),
    "d8_pointer": ("d8_pointer.tif", "int32", 0),
    "flow_accumulation": ("flow_accumulation_cells.tif", "int32", -9999),
}
SUBBASIN_RASTER = ("subbasins_clipped.tif", "int32", 0)


def _index(task_id: str) -> int:
    if task_id not in TASK_IDS:
        raise ValueError(f"unsupported terrain task id: {task_id}")
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


def _skill_script() -> Path:
    configured = os.environ.get("HYDROTUNE_SKILLS_ROOT", "").strip().strip('"')
    skills_root = Path(configured) if configured else DEFAULT_SKILLS_ROOT
    script = skills_root / SKILL_FOLDER / "examples" / SKILL_SCRIPT
    if not script.is_file():
        raise FileNotFoundError(f"terrain skill script not found: {script}")
    return script


def _dem(index: int) -> np.ndarray:
    elevation = np.zeros((12, 8), dtype=float)
    for row in range(11):
        elevation[row] = 11.0 - row
    elevation[11] = (7.0 - np.arange(8)) * 0.1
    if index == 2:
        # Confirmed flat plateau: the D8 drops vanish, so the skill records the
        # slope_clipped_cells count while still returning status success.
        elevation[3:6] = 9.0
    return elevation


def _pointer(index: int) -> np.ndarray:
    pointer = np.full((12, 8), 8, dtype="int32")  # code 8: flow south
    pointer[11, 0:7] = 2  # code 2: flow east along the bottom row
    if index == 3:
        # Confirmed broken D8: the bottom-left cell also leaves the grid, so the
        # basin has two exit cells and the skill must reject it.
        pointer[11, 0] = 8
    return pointer


def _accumulation() -> np.ndarray:
    rows, cols = np.mgrid[0:12, 0:8]
    return (50 + rows * 8 + cols).astype("int32")


def _subbasins() -> np.ndarray:
    basins = np.zeros((12, 8), dtype="int32")
    basins[:, 0:4] = 1
    basins[:, 4:8] = 2
    return basins


def _write_raster(path: Path, data: np.ndarray, dtype: str, nodata: float | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype=dtype,
        crs=CRS,
        transform=TRANSFORM,
        nodata=nodata,
    ) as dataset:
        dataset.write(data, 1)


def _reference(path: Path, base: Path) -> dict[str, Any]:
    return {"path": path.relative_to(base).as_posix(), "sha256": _sha256(path)}


def _stream_result(data_dir: Path, index: int) -> None:
    artifacts = {}
    for key, (name, dtype, nodata) in RASTER_NAMES.items():
        data = _dem(index) if key == "filled_dem" else (_pointer(index) if key == "d8_pointer" else _accumulation())
        _write_raster(data_dir / name, data, dtype, nodata)
        artifacts[key] = _reference(data_dir / name, data_dir)
    document = {
        "schema_version": "1.0",
        "skill": "spatial-analysis/extract-dem-stream-network",
        "status": "success",
        "artifacts": artifacts,
        "checks": [{"check": "synthetic_upstream", "status": "PASS", "details": "deterministic benchmark fixture"}],
    }
    _write_json(data_dir / "stream_result.json", document)


def _build_result(data_dir: Path) -> None:
    _write_raster(data_dir / SUBBASIN_RASTER[0], _subbasins(), SUBBASIN_RASTER[1], SUBBASIN_RASTER[2])
    artifacts = {"subbasins_clipped": _reference(data_dir / SUBBASIN_RASTER[0], data_dir)}
    inputs = {}
    for key, (name, _, _) in RASTER_NAMES.items():
        inputs[key] = _reference(data_dir / name, data_dir)
    document = {
        "schema_version": "1.0",
        "skill": "spatial-analysis/build-hydrological-topology",
        "status": "success",
        "inputs": inputs,
        "artifacts": artifacts,
        "checks": [{"check": "synthetic_upstream", "status": "PASS", "details": "deterministic benchmark fixture"}],
    }
    _write_json(data_dir / "build_result.json", document)


def _qc_result(data_dir: Path) -> None:
    document = {
        "schema_version": "1.0",
        "skill": "spatial-analysis/validate-hydrological-topology",
        "status": "success",
        "parameters": {"expected_outlets": 1},
        "inputs": {"build_result": _reference(data_dir / "build_result.json", data_dir)},
        "checks": [{"check": "expected_outlets", "status": "PASS", "details": "single outlet confirmed"}],
    }
    _write_json(data_dir / "topology_qc_result.json", document)


def _titles() -> dict[int, str]:
    return {
        1: "Derive TOPMODEL terrain inputs for a single-outlet funnel basin",
        2: "Record slope clipping on a confirmed flat plateau",
        3: "Reject a basin whose D8 pointers leave two exit cells",
    }


def _prompts() -> dict[int, str]:
    return {
        1: (
            "Use stream_result.json, build_result.json, and topology_qc_result.json exactly as supplied to run "
            "spatial-analysis/derive-topmodel-terrain-inputs with --classes 10, --distance-bins 10, and --minimum-slope 1e-4. "
            "The three upstream results form a hash-checked single-outlet HydroBase chain on a 12x8 metre grid. "
            "Write the native outputs (topographic_index.tif, topographic_index_classes.csv, distance_area.csv, result.json) under "
            "terrain-out/. "
            "Do not modify the upstream artifacts or relax the hash checks."
        ),
        2: (
            "Use stream_result.json, build_result.json, and topology_qc_result.json exactly as supplied to run "
            "spatial-analysis/derive-topmodel-terrain-inputs with --classes 10, --distance-bins 10, and --minimum-slope 1e-4. "
            "The DEM deliberately contains a flat plateau (rows 4-6); the D8 drops vanish there, so the skill clips those slopes to "
            "the confirmed minimum and records slope_clipped_cells in result.json while still returning success. "
            "Write the native outputs (topographic_index.tif, topographic_index_classes.csv, distance_area.csv, result.json) under "
            "terrain-out/. "
            "Do not perturb the plateau or suppress the recorded clipping."
        ),
        3: (
            "Use stream_result.json, build_result.json, and topology_qc_result.json exactly as supplied to run "
            "spatial-analysis/derive-topmodel-terrain-inputs with --classes 10, --distance-bins 10, and --minimum-slope 1e-4. "
            "The D8 pointer grid deliberately lets two cells leave the basin; run the skill verbatim and only the native result.json "
            "under terrain-out/. "
            "Do not repair the pointer grid; the script must reject the input itself. No topographic_index.tif, "
            "topographic_index_classes.csv, or distance_area.csv may remain in terrain-out/."
        ),
    }


def _positive_grading() -> list[dict[str, Any]]:
    golden = f"expected/golden_workspace/{OUTPUT_DIR}"
    result = f"{OUTPUT_DIR}/result.json"
    return [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": [f"{OUTPUT_DIR}/topographic_index_classes.csv", f"{OUTPUT_DIR}/distance_area.csv", result],
            "required_columns": {
                f"{OUTPUT_DIR}/topographic_index_classes.csv": ["class_id", "ti_lower", "ti_upper", "ti_mean", "cell_count", "area_fraction"],
                f"{OUTPUT_DIR}/distance_area.csv": ["bin_id", "distance_m", "cumulative_cells", "cumulative_area_m2", "cumulative_fraction"],
                result: ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"],
            },
            "weight": 0.10,
        },
        {
            "name": "topographic_index_raster",
            "type": "raster_match",
            "target": f"{OUTPUT_DIR}/topographic_index.tif",
            "reference": f"{golden}/topographic_index.tif",
            "atol": 1e-6,
            "rtol": 1e-9,
            "weight": 0.25,
        },
        {
            "name": "classes_table",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/topographic_index_classes.csv",
            "reference": f"{golden}/topographic_index_classes.csv",
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.15,
        },
        {
            "name": "distance_table",
            "type": "table_match",
            "target": f"{OUTPUT_DIR}/distance_area.csv",
            "reference": f"{golden}/distance_area.csv",
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.15,
        },
        {"name": "result_skill", "type": "exact_match", "target": result, "field": "skill", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_status", "type": "exact_match", "target": result, "field": "status", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_message", "type": "exact_match", "target": result, "field": "message", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_checks", "type": "exact_match", "target": result, "field": "checks", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_warnings", "type": "exact_match", "target": result, "field": "warnings", "reference": f"{golden}/result.json", "weight": 0.05},
        {
            "name": "artifact_references",
            "type": "artifact_reference_check",
            "target": result,
            "required_keys": ["topographic_index.tif", "topographic_index_classes.csv", "distance_area.csv"],
            "weight": 0.10,
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
            "targets": [f"{OUTPUT_DIR}/topographic_index.tif", f"{OUTPUT_DIR}/topographic_index_classes.csv", f"{OUTPUT_DIR}/distance_area.csv"],
            "weight": 0.20,
        },
    ]


def _build_task(task_id: str) -> dict[str, Any]:
    index = _index(task_id)
    positive = index < 3
    required = [f"{OUTPUT_DIR}/result.json"]
    if positive:
        required = [
            f"{OUTPUT_DIR}/topographic_index.tif",
            f"{OUTPUT_DIR}/topographic_index_classes.csv",
            f"{OUTPUT_DIR}/distance_area.csv",
            *required,
        ]
    return {
        "id": task_id,
        "title": _titles()[index],
        "domain": "spatial-analysis",
        "difficulty": "intermediate" if index < 3 else "basic",
        "primary_skill": SKILL_REF,
        "secondary_skills": [],
        "prompt": _prompts()[index],
        "data_description": "A deterministic single-outlet HydroBase fixture with hash-linked stream, build, and QC results.",
        "data_files": [
            "filled_dem.tif",
            "d8_pointer.tif",
            "flow_accumulation_cells.tif",
            "subbasins_clipped.tif",
            "stream_result.json",
            "build_result.json",
            "topology_qc_result.json",
        ],
        "required_outputs": required,
        "setup_notes": [
            "The upstream result chain is consumed by its native hash checks; it must not be altered.",
            "The grid is EPSG:32649 with 1 m pixels and whitebox-default non-ESRI D8 encoding.",
            "Do not install software or implement a replacement terrain analysis.",
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
                    # Upstream result references and cross-directory artifact
                    # paths keep only the file name so the golden stays
                    # deterministic; sha256 values are untouched.
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
    _stream_result(data_dir, index)
    _build_result(data_dir)
    _qc_result(data_dir)
    _generate_golden(task_dir, task_id)
    _write_json(task_dir / "task.json", _build_task(task_id))
