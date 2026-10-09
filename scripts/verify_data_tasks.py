"""Run the ETo, forcing-standardization, and discharge-alignment tasks with the real HydroTune example scripts and grade them."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from harness import grader, runner


DEFAULT_SKILLS = Path(r"E:\HydroTune-Skills（仿BioSkills版）")
SKILL_SCRIPTS = {
    "hydrodata-eto-faopm-": ("data-processing/derive-potential-evapotranspiration/examples/derive_potential_evapotranspiration.py", "eto-out"),
    "hydrodata-forcing-standardize-": ("data-processing/prepare-model-forcing-timeseries/examples/prepare_model_forcing_timeseries.py", "forcing-out"),
    "hydroanalysis-align-discharge-": ("post-processing/align-observed-simulated-discharge/examples/align_observed_simulated_discharge.py", "align-out"),
}


def command_for(task_id: str, workspace: Path, skills: Path) -> tuple[list[str], int]:
    number = int(task_id.rsplit("-", 1)[1])
    if task_id.startswith("hydrodata-eto-faopm-"):
        script, output = skills / SKILL_SCRIPTS[task_id.rsplit("-", 1)[0] + "-"][0], workspace / "eto-out"
        command = [sys.executable, str(script), "--source", "met.csv", "--stations", "stations.csv", "--config", "config.json", "--output-dir", str(output)]
        return command, 2 if number == 3 else 0
    if task_id.startswith("hydrodata-forcing-standardize-"):
        script = skills / SKILL_SCRIPTS["hydrodata-forcing-standardize-"][0]
        source = "rain.csv" if number == 1 else "gauge.csv"
        command = [sys.executable, str(script), "--source", source, "--config", "config.json", "--output-dir", str(workspace / "forcing-out")]
        return command, 2 if number == 3 else 0
    script = skills / SKILL_SCRIPTS["hydroanalysis-align-discharge-"][0]
    command = [
        sys.executable, str(script),
        "--observed-result", "observed_result.json", "--simulation-result", "simulation_result.json",
        "--output-dir", str(workspace / "align-out"),
    ]
    return command, 2 if number == 3 else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS)
    args = parser.parse_args()
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hsqb-data-verify-") as temporary:
        root = Path(temporary)
        for item in runner.discover_tasks("tests"):
            task, task_dir = item["task"], item["task_dir"]
            if not any(task["id"].startswith(prefix) for prefix in SKILL_SCRIPTS):
                continue
            workspace = root / task["id"]
            shutil.copytree(task_dir / "data", workspace)
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
    print("All data-processing tasks passed real-script verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
