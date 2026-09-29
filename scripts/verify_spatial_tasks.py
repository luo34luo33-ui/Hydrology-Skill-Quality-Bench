"""Run every spatial task with the real HydroTune example script and grade it."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from harness import grader, runner


DEFAULT_SKILLS = Path(r"E:\HydroTune-Skills（仿BioSkills版）")


def command_for(task_id: str, workspace: Path, skills: Path) -> tuple[list[str], int, list[str]]:
    number = int(task_id.rsplit("-", 1)[1])
    if "dem-grid" in task_id:
        script = skills / "spatial-analysis/prepare-dem-analysis-grid/examples/prepare_dem_analysis_grid.py"
        basin = workspace / ("basin_no_crs.shp" if number == 6 else "basin.gpkg")
        options = ["--analysis-buffer-km", "0.2", "--vertical-unit", "m"]
        if number == 2:
            options += ["--auto-utm"]
        elif number == 3:
            options = ["--analysis-buffer-km", "0.1", "--vertical-unit", "ft", "--target-crs", "EPSG:32651"]
        elif number == 4:
            options = ["--analysis-buffer-km", "0.5", "--vertical-unit", "m"]
        code = 0 if number <= 4 else 1
        return [sys.executable, str(script), "--dem", str(workspace / "source_dem.tif"), "--basin", str(basin), *options, "--output-dir", str(workspace / "prepared")], code, ["prepared/dem_metric.tif", "prepared/dem_analysis_buffer.tif", "prepared/basin_normalized.gpkg"]
    if "stream-network" in task_id:
        script = skills / "spatial-analysis/extract-dem-stream-network/examples/extract_dem_stream_network.py"
        threshold = 100.0 if number == 4 else (0.0 if number == 8 else 0.0031)
        code = 0 if number <= 3 else 1
        return [sys.executable, str(script), "--analysis-dem", str(workspace / "analysis_dem.tif"), "--stream-init-area-km2", str(threshold), "--output-dir", str(workspace / "hydrology")], code, [f"hydrology/{name}" for name in ("dem_filled.tif", "d8_pointer.tif", "flow_accumulation_cells.tif", "streams.tif", "stream_links.tif", "strahler_order.tif", "subbasins.tif", "streams.gpkg")]
    if "topology-build" in task_id:
        script = skills / "spatial-analysis/build-hydrological-topology/examples/build_hydrological_topology.py"
        options = ["--cell-inclusion", "all-touched" if number == 3 else "center"]
        if number == 4:
            options += ["--upstream-result", str(workspace / "prepare_result.json")]
        code = 0 if number <= 5 else 1
        command = [sys.executable, str(script), "--basin", str(workspace / "basin.gpkg"), "--dem-filled", str(workspace / "dem_filled.tif"), "--d8-pointer", str(workspace / "d8_pointer.tif"), "--flow-accumulation", str(workspace / "flow_accumulation_cells.tif"), "--stream-links", str(workspace / "stream_links.tif"), "--stream-order", str(workspace / "strahler_order.tif"), "--subbasins", str(workspace / "subbasins.tif"), *options, "--output-dir", str(workspace / "hydrobase")]
        forbidden = [f"hydrobase/{name}" for name in ("subbasins.csv", "reaches.csv", "topology.csv", "reaches_clipped.gpkg", "stream_links_clipped.tif", "stream_order_clipped.tif", "subbasins_clipped.tif")]
        return command, code, forbidden
    script = skills / "spatial-analysis/validate-hydrological-topology/examples/validate_hydrological_topology.py"
    outlets = 2 if number in {2, 4} else 1
    code = 0 if number <= 3 else (1 if number == 10 else 2)
    return [sys.executable, str(script), "--build-result", str(workspace / "hydrobase/result.json"), "--expected-outlets", str(outlets), "--output-dir", str(workspace / "topology-qc")], code, [f"topology-qc/{name}" for name in ("topology_checks.csv", "topology_check_report.txt", "network_topology_check.png")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS)
    args = parser.parse_args()
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hsqb-spatial-verify-") as temporary:
        root = Path(temporary)
        for item in runner.discover_tasks("tests", domain="spatial-analysis"):
            task, task_dir = item["task"], item["task_dir"]
            workspace = root / task["id"]
            shutil.copytree(task_dir / "data", workspace)
            command, expected_code, partials = command_for(task["id"], workspace, args.skills_root)
            completed = subprocess.run(command, cwd=workspace, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, check=False)
            if completed.returncode != expected_code:
                failures.append(f"{task['id']}: exit {completed.returncode}, expected {expected_code}")
                continue
            if len(task["required_outputs"]) == 1:
                for rel in partials:
                    path = workspace / rel
                    if path.is_file():
                        path.unlink()
            score = grader.grade_task(task, workspace, task_dir)["score"]
            print(f"{task['id']}: exit={completed.returncode}, score={score:.6f}")
            if score < 1.0 - 1e-12:
                failures.append(f"{task['id']}: score={score:.6f}")
    if failures:
        print("Failures:", *failures, sep="\n- ", file=sys.stderr)
        return 1
    print("All spatial tasks passed real-script verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
