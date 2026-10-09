"""Run the Muskingum and Xinanjiang tasks with the real HydroTune example scripts and grade them."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from harness import grader, runner


DEFAULT_SKILLS = Path(r"E:\HydroTune-Skills（仿BioSkills版）")
TASK_PREFIXES = (
    "hydromodel-muskingum-", "hydromodel-xaj-", "hydromodel-dhf-", "hydromodel-gr4j-",
    "hydromodel-hbv-", "hydromodel-lohmann-", "hydromodel-sacsma-", "hydromodel-tank-",
    "hydromodel-xaj-sd-", "hydromodel-swat-sd-",
)


def commands_for(task_id: str, workspace: Path, skills: Path) -> tuple[list[tuple[list[str], int]], list[str]]:
    number = int(task_id.rsplit("-", 1)[1])
    if task_id.startswith("hydromodel-gr4j-"):
        script = skills / "hydrological-modeling/run-lumped-gr4j-model/examples/run_lumped_gr4j.py"
        command = [
            sys.executable, str(script),
            "--forcing", "forcing.csv", "--time-column", "time", "--pet-column", "E0",
            "--params", "parameters.json", "--area-km2", "640", "--timestep-hours", "24",
            "--mode", "continuous", "--warmup-steps", "12", "--balance-tolerance-fraction", "0.2",
            "--output-format", "csv", "--output-dir", str(workspace / "gr4j-run"),
        ]
        code = 2 if number == 3 else 0
        return [(command, code)], ["gr4j-run/lumped_gr4j_runoff.csv"]
    if task_id.startswith("hydromodel-sacsma-"):
        script = skills / "hydrological-modeling/run-lumped-sacsma-model/examples/run_lumped_sacsma.py"
        command = [
            sys.executable, str(script),
            "--forcing", "forcing.csv", "--time-column", "time", "--pet-column", "E0",
            "--params", "parameters.json", "--area-km2", "640", "--timestep-hours", "24",
            "--mode", "continuous", "--warmup-steps", "12", "--balance-tolerance-fraction", "4.5",
            "--output-format", "csv", "--output-dir", str(workspace / "sacsma-run"),
        ]
        code = 2 if number == 3 else 0
        return [(command, code)], ["sacsma-run/lumped_sacsma_runoff.csv"]
    if task_id.startswith("hydromodel-lohmann-"):
        script = skills / "hydrological-modeling/route-lohmann-channel/examples/route_lohmann.py"
        command = [
            sys.executable, str(script),
            "--inflow", "inflow.csv", "--time-column", "time", "--direct-column", "direct",
            "--base-column", "base", "--flowlen-m", "100000", "--route-params", "route_params.json",
            "--timestep-hours", "24", "--output-format", "csv", "--output-dir", str(workspace / "lohmann-run"),
        ]
        code = 2 if number == 3 else 0
        return [(command, code)], ["lohmann-run/routed_lohmann.csv", "lohmann-run/lohmann_unit_hydrographs.json"]
    if task_id.startswith("hydromodel-xaj-sd-"):
        script = skills / "hydrological-modeling/run-semi-distributed-xaj-model/examples/run_semi_distributed_xaj.py"
        command = [
            sys.executable, str(script),
            "--topology-result", "build_result.json", "--topology-qc-result", "topology_qc_result.json",
            "--forcing", "forcing.csv", "--params", "params.json",
            "--output-dir", str(workspace / "xaj-sd-run"),
        ]
        code = 2 if number == 3 else 0
        return [(command, code)], ["xaj-sd-run/subbasin_process.csv", "xaj-sd-run/reach_process.csv", "xaj-sd-run/outlet_flow.csv"]
    if task_id.startswith("hydromodel-swat-sd-"):
        script = skills / "hydrological-modeling/run-semi-distributed-swat-model/examples/run_semi_distributed_swat.py"
        command = [
            sys.executable, str(script),
            "--topology-result", "build_result.json", "--topology-qc-result", "topology_qc_result.json",
            "--hru-table", "hru_table.csv", "--forcing", "forcing.csv", "--params", "params.json",
            "--output-dir", str(workspace / "swat-sd-run"),
        ]
        code = 2 if number == 3 else 0
        return [(command, code)], ["swat-sd-run/hru_process.csv", "swat-sd-run/subbasin_process.csv", "swat-sd-run/reach_process.csv", "swat-sd-run/outlet_flow.csv"]
    if task_id.startswith("hydromodel-dhf-"):
        script = skills / "hydrological-modeling/run-lumped-dhf-model/examples/run_lumped_dhf.py"
        command = [
            sys.executable, str(script),
            "--forcing", "forcing.csv", "--time-column", "time", "--pet-column", "E0",
            "--params", "parameters.json", "--area-km2", "640", "--river-length-km", "20",
            "--timestep-hours", "1", "--mode", "continuous", "--warmup-steps", "12",
            "--balance-tolerance-fraction", "0.05", "--output-format", "csv",
            "--output-dir", str(workspace / "dhf-run"),
        ]
        code = 2 if number == 3 else 0
        return [(command, code)], ["dhf-run/lumped_dhf_runoff.csv"]
    if task_id.startswith("hydromodel-hbv-"):
        script = skills / "hydrological-modeling/run-lumped-hbv-model/examples/run_lumped_hbv.py"
        command = [
            sys.executable, str(script),
            "--forcing", "forcing.csv", "--time-column", "time",
            "--params", "parameters.json", "--area-km2", "640",
            "--timestep-hours", "1", "--mode", "continuous", "--warmup-steps", "12",
            "--balance-tolerance-fraction", "6.5", "--output-format", "csv",
            "--output-dir", str(workspace / "hbv-run"),
        ]
        code = 2 if number == 3 else 0
        return [(command, code)], ["hbv-run/lumped_hbv_runoff.csv"]
    if task_id.startswith("hydromodel-tank-"):
        script = skills / "hydrological-modeling/run-lumped-tank-model/examples/run_lumped_tank.py"
        command = [
            sys.executable, str(script),
            "--forcing", "forcing.csv", "--time-column", "time",
            "--params", "parameters.json", "--area-km2", "640",
            "--timestep-hours", "1", "--mode", "continuous", "--warmup-steps", "12",
            "--output-format", "csv", "--output-dir", str(workspace / "tank-run"),
        ]
        code = 2 if number == 3 else 0
        return [(command, code)], ["tank-run/lumped_tank_runoff.csv"]
    if task_id.startswith("hydromodel-muskingum-"):
        script = skills / "hydrological-modeling/route-muskingum-channel/examples/route_muskingum.py"
        command = [
            sys.executable, str(script),
            "--inflow", "inflow.csv", "--time-column", "time", "--timestep-hours", "1",
            "--route-spec", "route_spec.json", "--combine", "sum", "--output-column", "Q_total",
            "--output-format", "csv", "--output-dir", str(workspace / "routed"),
        ]
        code = 2 if number == 3 else 0
        forbidden = ["routed/routed_flow.csv", "routed/route_coefficients.json"]
        return [(command, code)], forbidden
    script = skills / "hydrological-modeling/run-lumped-xaj-model/examples/run_lumped_xaj.py"
    command = [
        sys.executable, str(script),
        "--forcing", "forcing.csv", "--time-column", "time", "--params", "parameters.json",
        "--area-km2", "640", "--timestep-hours", "1", "--mode", "continuous", "--warmup-steps", "12",
        "--output-format", "csv", "--output-dir", str(workspace / "xaj-run"),
    ]
    code = 2 if number == 3 else 0
    forbidden = ["xaj-run/lumped_xaj_runoff.csv"]
    return [(command, code)], forbidden


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS)
    args = parser.parse_args()
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hsqb-modeling-verify-") as temporary:
        root = Path(temporary)
        for item in runner.discover_tasks("tests", domain="model-calibration"):
            task, task_dir = item["task"], item["task_dir"]
            if not task["id"].startswith(TASK_PREFIXES):
                continue
            workspace = root / task["id"]
            shutil.copytree(task_dir / "data", workspace)
            runs, forbidden = commands_for(task["id"], workspace, args.skills_root)
            return_code = None
            failed = False
            for command, expected_code in runs:
                completed = subprocess.run(command, cwd=workspace, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, check=False)
                return_code = completed.returncode
                if completed.returncode != expected_code:
                    failures.append(f"{task['id']}: exit {completed.returncode}, expected {expected_code}")
                    failed = True
                    break
            if failed:
                continue
            if len(task["required_outputs"]) == 1:
                for rel in forbidden:
                    path = workspace / rel
                    if path.is_file():
                        path.unlink()
            score = grader.grade_task(task, workspace, task_dir)["score"]
            print(f"{task['id']}: exit={return_code}, score={score:.6f}")
            if score < 1.0 - 1e-12:
                failures.append(f"{task['id']}: score={score:.6f}")
    if failures:
        print("Failures:", *failures, sep="\n- ", file=sys.stderr)
        return 1
    print("All modeling tasks passed real-script verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
