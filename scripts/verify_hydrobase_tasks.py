"""Run the terrain, forcing-aggregation, and TOPMODEL tasks with the real HydroTune example scripts and grade them."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from harness import grader, runner


DEFAULT_SKILLS = Path(r"E:\HydroTune-Skills（仿BioSkills版）")
TERRAIN_SCRIPT = "spatial-analysis/derive-topmodel-terrain-inputs/examples/derive_topmodel_terrain_inputs.py"
AGGREGATE_SCRIPT = "spatial-analysis/aggregate-forcing-to-model-units/examples/aggregate_forcing_to_model_units.py"
TOPMODEL_SCRIPT = "hydrological-modeling/run-lumped-topmodel/examples/run_lumped_topmodel.py"
TASK_PREFIXES = ("hydrodata-terrain-topidx-", "hydrodata-forcing-aggregate-", "hydromodel-topmodel-")


def run_terrain_fixture(workspace: Path, skills: Path, task_id: str) -> None:
    """Reproduce the terrain product that the TOPMODEL tasks consume."""
    if not task_id.startswith("hydromodel-topmodel-"):
        return
    script = skills / TERRAIN_SCRIPT
    completed = subprocess.run(
        [
            sys.executable, str(script),
            "--stream-result", "stream_result.json",
            "--topology-result", "build_result.json",
            "--topology-qc-result", "topology_qc_result.json",
            "--classes", "10", "--distance-bins", "10", "--minimum-slope", "1e-4",
            "--output-dir", str(workspace / "terrain-run"),
        ],
        cwd=workspace, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"terrain fixture run failed: {completed.stderr}")


def command_for(task_id: str, workspace: Path, skills: Path) -> tuple[list[str], int]:
    number = int(task_id.rsplit("-", 1)[1])
    if task_id.startswith("hydrodata-terrain-topidx-"):
        command = [
            sys.executable, str(skills / TERRAIN_SCRIPT),
            "--stream-result", "stream_result.json", "--topology-result", "build_result.json",
            "--topology-qc-result", "topology_qc_result.json",
            "--classes", "10", "--distance-bins", "10", "--minimum-slope", "1e-4",
            "--output-dir", str(workspace / "terrain-out"),
        ]
        return command, 2 if number == 3 else 0
    if task_id.startswith("hydrodata-forcing-aggregate-"):
        target = "basin" if number == 2 else "subbasin"
        command = [
            sys.executable, str(skills / AGGREGATE_SCRIPT),
            "--topology-result", "build_result.json", "--topology-qc-result", "topology_qc_result.json",
            "--source-config", "source_config.json", "--target", target,
            "--output-dir", str(workspace / "aggregate-out"),
        ]
        return command, 2 if number == 3 else 0
    command = [
        sys.executable, str(skills / TOPMODEL_SCRIPT),
        "--terrain-result", "terrain_result.json", "--forcing", "forcing.csv", "--params", "params.json",
        "--output-dir", str(workspace / "topmodel-run"),
    ]
    return command, 2 if number == 3 else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS)
    args = parser.parse_args()
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hsqb-hydrobase-verify-") as temporary:
        root = Path(temporary)
        for item in runner.discover_tasks("tests"):
            task, task_dir = item["task"], item["task_dir"]
            if not task["id"].startswith(TASK_PREFIXES):
                continue
            workspace = root / task["id"]
            shutil.copytree(task_dir / "data", workspace)
            run_terrain_fixture(workspace, args.skills_root, task["id"])
            command, expected_code = command_for(task["id"], workspace, args.skills_root)
            completed = subprocess.run(command, cwd=workspace, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, check=False)
            if completed.returncode != expected_code:
                failures.append(f"{task['id']}: exit {completed.returncode}, expected {expected_code}")
                continue
            score = grader.grade_task(task, workspace, task_dir)["score"]
            print(f"{task['id']}: exit={completed.returncode}, score={score:.6f}")
            if score < 1.0 - 1e-12:
                failures.append(f"{task['id']}: score={score:.6f}")
    if failures:
        print("Failures:", *failures, sep="\n- ", file=sys.stderr)
        return 1
    print("All HydroBase-chain tasks passed real-script verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
