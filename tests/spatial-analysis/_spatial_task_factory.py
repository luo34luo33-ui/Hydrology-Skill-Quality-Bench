"""Generate deterministic spatial benchmark fixtures and golden workspaces."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import Affine, from_origin
from shapely.geometry import Polygon, box


ROOT = Path(__file__).resolve().parent
SKILLS_ROOT = Path(os.environ.get("HYDROTUNE_SKILLS_ROOT", r"E:\HydroTune-Skills（仿BioSkills版）"))
SCRIPTS = {
    "dem-grid": SKILLS_ROOT / "spatial-analysis/prepare-dem-analysis-grid/examples/prepare_dem_analysis_grid.py",
    "stream-network": SKILLS_ROOT / "spatial-analysis/extract-dem-stream-network/examples/extract_dem_stream_network.py",
    "topology-build": SKILLS_ROOT / "spatial-analysis/build-hydrological-topology/examples/build_hydrological_topology.py",
    "topology-validate": SKILLS_ROOT / "spatial-analysis/validate-hydrological-topology/examples/validate_hydrological_topology.py",
}
SKILL_REFS = {
    "dem-grid": "spatial-analysis/prepare-dem-analysis-grid",
    "stream-network": "spatial-analysis/extract-dem-stream-network",
    "topology-build": "spatial-analysis/build-hydrological-topology",
    "topology-validate": "spatial-analysis/validate-hydrological-topology",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_raster(
    path: Path, values: np.ndarray, transform: Affine, crs: str | None,
    *, nodata: float | int = -9999, dtype: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    array = np.asarray(values)
    if array.ndim == 2:
        array = array[np.newaxis, ...]
    output_dtype = dtype or str(array.dtype)
    profile: dict[str, Any] = {
        "driver": "GTiff", "height": array.shape[1], "width": array.shape[2],
        "count": array.shape[0], "dtype": output_dtype, "transform": transform,
        "nodata": nodata, "compress": "lzw",
    }
    if crs is not None:
        profile["crs"] = crs
    with rasterio.open(path, "w", **profile) as target:
        target.write(array.astype(output_dtype))


def write_vector(path: Path, geometries: list[Any], crs: str | None, *, layer: str = "basin", **columns: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    frame = gpd.GeoDataFrame(columns or {"basin_id": list(range(1, len(geometries) + 1))}, geometry=geometries, crs=crs)
    frame.to_file(path, layer=layer, driver="GPKG")
    stabilize_gpkg(path)


def stabilize_gpkg(path: Path) -> None:
    """Remove creation-time drift from a GeoPackage and normalize SQLite pages."""
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE gpkg_contents SET last_change = '2000-01-01T00:00:00.000Z'")
        connection.commit()
        connection.execute("VACUUM")


def stabilize_output_artifacts(output_dir: Path, gpkg_names: list[str]) -> None:
    for name in gpkg_names:
        path = output_dir / name
        if path.is_file():
            stabilize_gpkg(path)
    result_path = output_dir / "result.json"
    if not result_path.is_file():
        return
    document = json.loads(result_path.read_text(encoding="utf-8"))
    for reference in document.get("artifacts", {}).values():
        if isinstance(reference, dict) and isinstance(reference.get("path"), str):
            path = output_dir / reference["path"]
            if path.is_file():
                reference["sha256"] = sha256(path)
    write_json(result_path, document)


def run_script(group: str, arguments: list[str], expected_code: int) -> None:
    script = SCRIPTS[group]
    if not script.is_file():
        raise FileNotFoundError(f"HydroTune skill script missing: {script}")
    completed = subprocess.run(
        [sys.executable, str(script), *arguments], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=300, check=False,
    )
    if completed.returncode != expected_code:
        raise RuntimeError(
            f"{group} expected exit {expected_code}, got {completed.returncode}\n"
            f"stdout:\n{completed.stdout[-2000:]}\nstderr:\n{completed.stderr[-2000:]}"
        )


def clean_task(task_dir: Path) -> tuple[Path, Path]:
    data = task_dir / "data"
    golden = task_dir / "expected/golden_workspace"
    for path in (data, golden):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)
    return data, golden


def public_data_files(data: Path) -> list[str]:
    return sorted(path.relative_to(data).as_posix() for path in data.rglob("*") if path.is_file())


def exact_reference(name: str, target: str, field: str, reference: str, weight: float) -> dict[str, Any]:
    return {"name": name, "type": "exact_match", "target": target, "field": field, "reference": reference, "weight": weight}


def error_grading(output_dir: str, absent: list[str]) -> list[dict[str, Any]]:
    result = f"{output_dir}/result.json"
    reference = f"expected/golden_workspace/{result}"
    return [
        {"name": "error_result", "type": "file_check", "target": result, "weight": 0.10},
        exact_reference("error_status", result, "status", reference, 0.35),
        exact_reference("error_message", result, "message", reference, 0.25),
        exact_reference("empty_artifacts", result, "artifacts", reference, 0.10),
        {"name": "no_forbidden_artifacts", "type": "file_absence_check", "targets": absent, "weight": 0.20},
    ]


def write_task(
    task_dir: Path, group: str, title: str, prompt: str, required: list[str],
    grading: list[dict[str, Any]], difficulty: str = "advanced",
) -> None:
    task_id = task_dir.name
    data = task_dir / "data"
    write_json(task_dir / "task.json", {
        "id": task_id, "title": title, "domain": "spatial-analysis", "difficulty": difficulty,
        "primary_skill": SKILL_REFS[group], "secondary_skills": [], "prompt": prompt,
        "data_description": title, "data_files": public_data_files(data), "required_outputs": required,
        "setup_notes": [
            "Python, NumPy, pandas, rasterio, GeoPandas, Shapely, matplotlib, Pillow, and WhiteboxTools are available.",
            "Use only the explicitly confirmed spatial parameters and preserve the native skill result.json.",
        ],
        "timeout_seconds": 600, "grading": grading,
    })
    wrapper = (
        "from pathlib import Path\nimport sys\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
        "from _spatial_task_factory import build_task\n"
        "build_task(Path(__file__).resolve().parent.name)\n"
    )
    (task_dir / "generate_data.py").write_text(wrapper, encoding="utf-8")


def prepare_inputs(case: int, data: Path) -> tuple[list[str], str, str, int, Path]:
    dem = data / "source_dem.tif"
    basin = data / "basin.gpkg"
    values = (500.0 - np.add.outer(np.arange(30) * 2.0, np.arange(30) * 0.5)).astype("float32")
    transform = from_origin(500000, 4103000, 100, 100)
    crs: str | None = "EPSG:32650"
    basin_crs: str | None = crs
    geometries = [box(500600, 4101000, 501500, 4102200), box(501500, 4101000, 502300, 4102200)]
    args = ["--analysis-buffer-km", "0.2", "--vertical-unit", "m"]
    status = "success"
    exit_code = 0
    if case == 2:
        transform = from_origin(119.985, 30.015, 0.001, 0.001)
        crs = basin_crs = "EPSG:4326"
        geometries = [box(119.992, 29.992, 120.008, 30.008)]
        args += ["--auto-utm"]
    elif case == 3:
        transform = from_origin(119.985, 30.015, 0.001, 0.001)
        crs = basin_crs = "EPSG:4326"
        values = values / 0.3048
        geometries = [box(119.992, 29.992, 120.008, 30.008)]
        args = ["--analysis-buffer-km", "0.1", "--vertical-unit", "ft", "--target-crs", "EPSG:32651"]
    elif case == 4:
        values = values[:10, :10]
        geometries = [box(500200, 4102200, 500800, 4102800)]
        args = ["--analysis-buffer-km", "0.5", "--vertical-unit", "m"]
        status = "warning"
    elif case == 5:
        crs = None
        exit_code = 1
        status = "error"
    elif case == 6:
        basin_crs = None
        basin = data / "basin_no_crs.shp"
        exit_code = 1
        status = "error"
    elif case == 7:
        geometries = [box(502500, 4101000, 503500, 4102200)]
        exit_code = 1
        status = "error"
    elif case == 8:
        values = np.stack([values, values + 1.0])
        exit_code = 1
        status = "error"
    write_raster(dem, values, transform, crs, dtype="float32")
    if case == 6:
        frame = gpd.GeoDataFrame({"basin_id": list(range(1, len(geometries) + 1))}, geometry=geometries)
        frame.to_file(basin, driver="ESRI Shapefile")
        basin.with_suffix(".prj").unlink(missing_ok=True)
    else:
        write_vector(basin, geometries, basin_crs)
    return args, status, f"Prepare DEM grid case {case}", exit_code, basin


def prepare_grading(status: str) -> tuple[list[str], list[dict[str, Any]]]:
    outputs = ["prepared/dem_metric.tif", "prepared/dem_analysis_buffer.tif", "prepared/basin_normalized.gpkg", "prepared/result.json"]
    if status == "error":
        return ["prepared/result.json"], error_grading("prepared", outputs[:-1])
    ref = "expected/golden_workspace/prepared"
    grading: list[dict[str, Any]] = [
        {"name": "artifacts", "type": "file_check", "targets": outputs, "weight": 0.10},
        {"name": "metric_dem", "type": "raster_match", "target": outputs[0], "reference": f"{ref}/dem_metric.tif", "atol": 1e-5, "rtol": 1e-6, "weight": 0.20},
        {"name": "analysis_dem", "type": "raster_match", "target": outputs[1], "reference": f"{ref}/dem_analysis_buffer.tif", "atol": 1e-5, "rtol": 1e-6, "weight": 0.20},
        {"name": "basin", "type": "vector_match", "target": outputs[2], "reference": f"{ref}/basin_normalized.gpkg", "layer": "basin", "key_columns": ["basin_id"], "columns": ["basin_id"], "geometry_tolerance": 1e-5, "weight": 0.15},
        exact_reference("status", outputs[3], "status", f"{ref}/result.json", 0.10),
        exact_reference("warnings", outputs[3], "warnings", f"{ref}/result.json", 0.05),
        exact_reference("parameters", outputs[3], "parameters", f"{ref}/result.json", 0.05),
        {"name": "artifact_integrity", "type": "artifact_reference_check", "target": outputs[3], "required_keys": ["metric_dem", "analysis_dem", "normalized_basin"], "weight": 0.15},
    ]
    return outputs, grading


def build_dem_grid(case: int, task_dir: Path) -> None:
    data, golden = clean_task(task_dir)
    args, status, title, exit_code, basin = prepare_inputs(case, data)
    output = golden / "prepared"
    run_script("dem-grid", ["--dem", str(data / "source_dem.tif"), "--basin", str(basin), *args, "--output-dir", str(output)], exit_code)
    if status == "error":
        for name in ("dem_metric.tif", "dem_analysis_buffer.tif", "basin_normalized.gpkg"):
            (output / name).unlink(missing_ok=True)
    else:
        stabilize_output_artifacts(output, ["basin_normalized.gpkg"])
    required, grading = prepare_grading(status)
    prompt_args = " ".join(args)
    write_task(task_dir, "dem-grid", title,
               f"Prepare source_dem.tif and {basin.name} using the confirmed options: {prompt_args}. Write all outputs under prepared/. Do not infer missing CRS, change units, or relax coverage checks. If validation rejects the input, preserve result.json but remove partial declared artifacts.",
               required, grading)


def stream_dem(case: int, data: Path) -> tuple[float, str, int]:
    rows = cols = 32
    rr, cc = np.indices((rows, cols))
    values = (1200.0 - rr * 5.0 + np.abs(cc - 16) * 2.0).astype("float32")
    values[10:13, 14:18] -= 8.0
    transform = from_origin(500000, 4100000, 30, 30)
    crs = "EPSG:32650"
    threshold = 0.0031
    exit_code = 0
    if case == 2:
        transform = from_origin(500000, 4100000, 20, 40)
    elif case == 3:
        values[4:12, 8:24] = 1120.0
        values[12, 16] = 1110.0
    elif case == 4:
        threshold = 100.0
        exit_code = 1
    elif case == 5:
        crs = "EPSG:4326"
        transform = from_origin(120, 30, 0.001, 0.001)
        exit_code = 1
    elif case == 6:
        crs = "EPSG:2263"
        transform = from_origin(1000000, 200000, 100, 100)
        exit_code = 1
    elif case == 7:
        values = np.stack([values, values + 1])
        exit_code = 1
    elif case == 8:
        threshold = 0.0
        exit_code = 1
    write_raster(data / "analysis_dem.tif", values, transform, crs, dtype="float32")
    return threshold, ("success" if exit_code == 0 else "error"), exit_code


def stream_grading(status: str) -> tuple[list[str], list[dict[str, Any]]]:
    names = ["dem_filled.tif", "d8_pointer.tif", "flow_accumulation_cells.tif", "streams.tif", "stream_links.tif", "strahler_order.tif", "subbasins.tif", "streams.gpkg", "result.json"]
    outputs = [f"hydrology/{name}" for name in names]
    if status == "error":
        return [outputs[-1]], error_grading("hydrology", outputs[:-1])
    ref = "expected/golden_workspace/hydrology"
    grading: list[dict[str, Any]] = [{"name": "artifacts", "type": "file_check", "targets": outputs, "weight": 0.10}]
    categorical = {"d8_pointer.tif", "streams.tif", "stream_links.tif", "strahler_order.tif", "subbasins.tif"}
    for index, name in enumerate(names[:7]):
        grading.append({
            "name": f"raster_{index}", "type": "raster_match", "target": f"hydrology/{name}",
            "reference": f"{ref}/{name}", "categorical": name in categorical,
            "atol": 1e-5, "rtol": 1e-6, "weight": 0.07,
        })
    grading.extend([
        {"name": "streams_vector", "type": "vector_match", "target": "hydrology/streams.gpkg", "reference": f"{ref}/streams.gpkg", "layer": "streams", "geometry_tolerance": 1e-5, "weight": 0.06},
        exact_reference("status", outputs[-1], "status", f"{ref}/result.json", 0.05),
        exact_reference("parameters", outputs[-1], "parameters", f"{ref}/result.json", 0.10),
        {"name": "artifact_integrity", "type": "artifact_reference_check", "target": outputs[-1], "required_keys": ["filled_dem", "d8_pointer", "flow_accumulation", "streams", "stream_links", "stream_order", "subbasins", "streams_vector"], "weight": 0.20},
    ])
    return outputs, grading


def build_stream_network(case: int, task_dir: Path) -> None:
    data, golden = clean_task(task_dir)
    threshold, status, exit_code = stream_dem(case, data)
    output = golden / "hydrology"
    run_script("stream-network", ["--analysis-dem", str(data / "analysis_dem.tif"), "--stream-init-area-km2", str(threshold), "--output-dir", str(output)], exit_code)
    if status == "error":
        for name in ("dem_filled.tif", "d8_pointer.tif", "flow_accumulation_cells.tif", "streams.tif", "stream_links.tif", "strahler_order.tif", "subbasins.tif", "streams.gpkg"):
            (output / name).unlink(missing_ok=True)
    else:
        stabilize_output_artifacts(output, ["streams.gpkg"])
    required, grading = stream_grading(status)
    write_task(task_dir, "stream-network", f"Extract DEM stream network case {case}",
               f"Extract the network from analysis_dem.tif with the confirmed stream initiation area {threshold} km2. Write outputs under hydrology/. Do not change the threshold or D8 encoding. If validation rejects the input, preserve result.json but remove partial declared artifacts.",
               required, grading)


def topology_arrays(case: int, data: Path) -> tuple[list[str], str, int]:
    shape = (7, 7)
    transform = from_origin(0, 210, 30, 30)
    dem = np.add.outer(1000.0 - np.arange(7) * 10.0, np.zeros(7)).astype("float32")
    pointer = np.zeros(shape, dtype="int16")
    accumulation = np.ones(shape, dtype="float32")
    links = np.zeros(shape, dtype="int32")
    order = np.zeros(shape, dtype="int16")
    subbasins = np.zeros(shape, dtype="int32")
    cells = {1: [(1, 1), (2, 2)], 2: [(1, 5), (2, 4)], 3: [(3, 3), (4, 3)], 4: [(5, 3), (6, 3)]}
    codes = {1: [4, 4], 2: [16, 16], 3: [8, 8], 4: [8, 0]}
    orders = {1: 1, 2: 1, 3: 2, 4: 2}
    for reach_id, reach_cells in cells.items():
        for index, (row, col) in enumerate(reach_cells):
            links[row, col] = reach_id
            pointer[row, col] = codes[reach_id][index]
            accumulation[row, col] = reach_id * 10 + index
            order[row, col] = orders[reach_id]
            subbasins[row, col] = reach_id
    basin_geom = box(0, 0, 210, 210)
    cell_inclusion = "center"
    upstream: list[str] = []
    status = "success"
    exit_code = 0
    if case == 2:
        basin_geom = box(0, 60.1, 210, 210)
    elif case == 3:
        basin_geom = box(29.9, 29.9, 180.1, 180.1)
        cell_inclusion = "all-touched"
    elif case == 4:
        upstream_path = data / "prepare_result.json"
        write_json(upstream_path, {"status": "warning", "warnings": ["DEM 未完整覆盖分析 buffer；边界附近拓扑和出口判定可能不可靠。"]})
        upstream = ["--upstream-result", str(upstream_path)]
        status = "warning"
    elif case == 5:
        dem[4, 3] = dem[3, 3] + 5.0
        status = "warning"
    elif case == 6:
        pass
    elif case == 7:
        pointer[1, 1] = 3
        status = "error"
        exit_code = 1
    elif case == 8:
        links.fill(0); pointer.fill(0); accumulation.fill(1); order.fill(0); subbasins.fill(0)
        links[3, 3], links[3, 4] = 1, 2
        pointer[3, 3], pointer[3, 4] = 2, 32
        accumulation[3, 3], accumulation[3, 4] = 10, 11
        order[3, 3], order[3, 4] = 1, 1
        subbasins[3, 3], subbasins[3, 4] = 1, 2
        status = "error"
        exit_code = 1
    elif case == 9:
        for row, col in cells[1]:
            subbasins[row, col] = 0
        status = "error"
        exit_code = 1
    paths = {
        "dem_filled.tif": (dem, "float32"), "d8_pointer.tif": (pointer, "int16"),
        "flow_accumulation_cells.tif": (accumulation, "float32"), "stream_links.tif": (links, "int32"),
        "strahler_order.tif": (order, "int16"), "subbasins.tif": (subbasins, "int32"),
    }
    for name, (values, dtype) in paths.items():
        raster_transform = transform * Affine.translation(0.5, 0) if case == 6 and name == "strahler_order.tif" else transform
        write_raster(data / name, values, raster_transform, "EPSG:32650", dtype=dtype)
    if case == 6:
        status = "error"
        exit_code = 1
    write_vector(data / "basin.gpkg", [basin_geom], "EPSG:32650")
    args = ["--cell-inclusion", cell_inclusion, *upstream]
    return args, status, exit_code


def topology_grading(status: str) -> tuple[list[str], list[dict[str, Any]]]:
    names = ["subbasins.csv", "reaches.csv", "topology.csv", "reaches_clipped.gpkg", "stream_links_clipped.tif", "stream_order_clipped.tif", "subbasins_clipped.tif", "result.json"]
    outputs = [f"hydrobase/{name}" for name in names]
    if status == "error":
        return [outputs[-1]], error_grading("hydrobase", outputs[:-1])
    ref = "expected/golden_workspace/hydrobase"
    grading: list[dict[str, Any]] = [{"name": "artifacts", "type": "file_check", "targets": outputs, "weight": 0.10}]
    for name in names[:3]:
        grading.append({"name": f"table_{name}", "type": "table_match", "target": f"hydrobase/{name}", "reference": f"{ref}/{name}", "atol": 1e-6, "rtol": 1e-8, "weight": 0.10})
    grading.extend([
        {"name": "reaches_vector", "type": "vector_match", "target": outputs[3], "reference": f"{ref}/{names[3]}", "layer": "reaches", "key_columns": ["reach_id"], "geometry_tolerance": 1e-6, "atol": 1e-6, "rtol": 1e-8, "weight": 0.10},
        {"name": "links", "type": "raster_match", "target": outputs[4], "reference": f"{ref}/{names[4]}", "categorical": True, "weight": 0.05},
        {"name": "orders", "type": "raster_match", "target": outputs[5], "reference": f"{ref}/{names[5]}", "categorical": True, "weight": 0.05},
        {"name": "subbasins", "type": "raster_match", "target": outputs[6], "reference": f"{ref}/{names[6]}", "categorical": True, "weight": 0.05},
        exact_reference("status", outputs[7], "status", f"{ref}/result.json", 0.10),
        exact_reference("warnings", outputs[7], "warnings", f"{ref}/result.json", 0.05),
        {"name": "artifact_integrity", "type": "artifact_reference_check", "target": outputs[7], "required_keys": ["subbasins_table", "reaches_table", "topology_table", "reaches_vector", "stream_links_clipped", "stream_order_clipped", "subbasins_clipped"], "weight": 0.20},
    ])
    return outputs, grading


def build_topology(case: int, task_dir: Path) -> None:
    data, golden = clean_task(task_dir)
    args, status, exit_code = topology_arrays(case, data)
    output = golden / "hydrobase"
    command = [
        "--basin", str(data / "basin.gpkg"), "--dem-filled", str(data / "dem_filled.tif"),
        "--d8-pointer", str(data / "d8_pointer.tif"), "--flow-accumulation", str(data / "flow_accumulation_cells.tif"),
        "--stream-links", str(data / "stream_links.tif"), "--stream-order", str(data / "strahler_order.tif"),
        "--subbasins", str(data / "subbasins.tif"), *args, "--output-dir", str(output),
    ]
    run_script("topology-build", command, exit_code)
    if status != "error":
        stabilize_output_artifacts(output, ["reaches_clipped.gpkg"])
    required, grading = topology_grading(status)
    prompt_args = " ".join(args)
    write_task(task_dir, "topology-build", f"Build hydrological topology case {case}",
               f"Build HydroBase from the supplied basin and six aligned hydrology rasters. Confirmed options: {prompt_args}. Write outputs under hydrobase/. Do not infer topology from clipped line contact or repair rejected inputs.",
               required, grading)


def copy_valid_hydrobase(data: Path) -> Path:
    source_task = ROOT / "hydrodata-topology-build-001"
    if not (source_task / "expected/golden_workspace/hydrobase/result.json").is_file():
        build_topology(1, source_task)
    target = data / "hydrobase"
    shutil.copytree(source_task / "expected/golden_workspace/hydrobase", target)
    shutil.copy2(source_task / "data/basin.gpkg", target / "basin.gpkg")
    result_path = target / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result.setdefault("inputs", {})["basin_boundary"] = {"path": "basin.gpkg", "sha256": sha256(target / "basin.gpkg")}
    for reference in result["artifacts"].values():
        reference["path"] = Path(reference["path"]).name
    write_json(result_path, result)
    return target


def refresh_build_hashes(hydrobase: Path, *, skip: str | None = None) -> None:
    result_path = hydrobase / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    for key, reference in result["artifacts"].items():
        if key != skip:
            reference["sha256"] = sha256(hydrobase / reference["path"])
    write_json(result_path, result)


def mutate_validation(case: int, hydrobase: Path) -> tuple[int, int, str]:
    expected_outlets = 1
    exit_code = 0
    status = "success"
    reaches_path = hydrobase / "reaches.csv"
    topology_path = hydrobase / "topology.csv"
    subbasins_path = hydrobase / "subbasins.csv"
    reaches = pd.read_csv(reaches_path)
    topology = pd.read_csv(topology_path)
    if case == 2:
        expected_outlets = 2
        reaches.loc[reaches.reach_id == 3, ["downstream_reach_id", "downstream_sub_id", "is_outlet"]] = [0, 0, 1]
        reaches.loc[reaches.reach_id == 4, ["upstream_count", "upstream_reach_ids", "topo_level", "is_headwater"]] = [0, "", 1, 1]
        topology = reaches[["sub_id", "reach_id", "upstream_count", "upstream_reach_ids", "downstream_sub_id", "downstream_reach_id", "topo_level", "is_headwater", "is_outlet"]]
    elif case == 3:
        result_path = hydrobase / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["status"] = "warning"
        result["warnings"] = ["negative elevation steps=1"]
        result["checks"].append({"check": "negative_elevation_steps", "status": "WARN", "details": "negative elevation steps=1"})
        write_json(result_path, result)
        reaches.loc[reaches.index[0], "negative_elevation_step_count"] = 1
        status = "warning"
    elif case == 4:
        expected_outlets = 2
        exit_code = 2
        status = "error"
    elif case == 5:
        reaches = pd.concat([reaches, reaches.iloc[[0]]], ignore_index=True)
        exit_code = 2; status = "error"
    elif case == 6:
        reaches.loc[reaches.reach_id == 1, "downstream_reach_id"] = 99
        topology.loc[topology.reach_id == 1, "downstream_reach_id"] = 99
        exit_code = 2; status = "error"
    elif case == 7:
        reaches.loc[reaches.reach_id == 4, ["downstream_reach_id", "downstream_sub_id", "is_outlet"]] = [3, 3, 0]
        topology.loc[topology.reach_id == 4, ["downstream_reach_id", "downstream_sub_id", "is_outlet"]] = [3, 3, 0]
        exit_code = 2; status = "error"
    elif case == 8:
        subbasins = pd.read_csv(subbasins_path)
        subbasins.loc[subbasins.index[0], "area_km2"] += 1.0
        subbasins.to_csv(subbasins_path, index=False)
        exit_code = 2; status = "error"
    elif case == 9:
        path = hydrobase / "stream_order_clipped.tif"
        with rasterio.open(path) as source:
            values, profile = source.read(), source.profile.copy()
        profile["transform"] = profile["transform"] * Affine.translation(0.5, 0)
        with rasterio.open(path, "w", **profile) as target:
            target.write(values)
        exit_code = 2; status = "error"
    elif case == 10:
        refresh_build_hashes(hydrobase)
        result_path = hydrobase / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["artifacts"]["reaches_table"]["sha256"] = "0" * 64
        write_json(result_path, result)
        return 1, expected_outlets, "error"
    reaches.to_csv(reaches_path, index=False)
    topology.to_csv(topology_path, index=False)
    refresh_build_hashes(hydrobase)
    return exit_code, expected_outlets, status


def validation_grading(case: int, status: str) -> tuple[list[str], list[dict[str, Any]]]:
    outputs = ["topology-qc/topology_checks.csv", "topology-qc/topology_check_report.txt", "topology-qc/network_topology_check.png", "topology-qc/result.json"]
    if case == 10:
        return [outputs[-1]], error_grading("topology-qc", outputs[:-1])
    ref = "expected/golden_workspace/topology-qc"
    return outputs, [
        {"name": "artifacts", "type": "file_check", "targets": outputs, "weight": 0.10},
        {"name": "checks_table", "type": "table_match", "target": outputs[0], "reference": f"{ref}/topology_checks.csv", "columns": ["check", "status", "count", "details"], "weight": 0.55},
        exact_reference("status", outputs[3], "status", f"{ref}/result.json", 0.10),
        exact_reference("warnings", outputs[3], "warnings", f"{ref}/result.json", 0.05),
        exact_reference("checks", outputs[3], "checks", f"{ref}/result.json", 0.05),
        {"name": "artifact_integrity", "type": "artifact_reference_check", "target": outputs[3], "required_keys": ["topology_checks", "topology_report", "topology_figure"], "weight": 0.15},
    ]


def build_validation(case: int, task_dir: Path) -> None:
    data, golden = clean_task(task_dir)
    hydrobase = copy_valid_hydrobase(data)
    exit_code, expected_outlets, status = mutate_validation(case, hydrobase)
    output = golden / "topology-qc"
    run_script("topology-validate", ["--build-result", str(hydrobase / "result.json"), "--expected-outlets", str(expected_outlets), "--output-dir", str(output)], exit_code)
    required, grading = validation_grading(case, status)
    write_task(task_dir, "topology-validate", f"Validate hydrological topology case {case}",
               f"Independently validate hydrobase/result.json with the confirmed expected outlet count {expected_outlets}. Write all QC evidence under topology-qc/. Do not modify or repair the supplied HydroBase.",
               required, grading)


def build_task(task_id: str) -> None:
    task_dir = ROOT / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    if task_id.startswith("hydrodata-dem-grid-"):
        build_dem_grid(int(task_id.rsplit("-", 1)[1]), task_dir)
    elif task_id.startswith("hydrodata-stream-network-"):
        build_stream_network(int(task_id.rsplit("-", 1)[1]), task_dir)
    elif task_id.startswith("hydrodata-topology-build-"):
        build_topology(int(task_id.rsplit("-", 1)[1]), task_dir)
    elif task_id.startswith("hydrodata-topology-validate-"):
        build_validation(int(task_id.rsplit("-", 1)[1]), task_dir)
    else:
        raise ValueError(f"unknown spatial task: {task_id}")


def build_all() -> None:
    groups = (("dem-grid", 8), ("stream-network", 8), ("topology-build", 9), ("topology-validate", 10))
    for group, count in groups:
        for index in range(1, count + 1):
            task_id = f"hydrodata-{group}-{index:03d}"
            print(f"generating {task_id}", flush=True)
            build_task(task_id)


if __name__ == "__main__":
    build_all()
