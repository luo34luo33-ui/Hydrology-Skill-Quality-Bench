"""Run the evaluation-diagnostics and ML residual-correction tasks with the real HydroTune example scripts and grade them."""

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
    "hydroanalysis-event-metrics-",
    "hydroanalysis-series-metrics-",
    "hydroanalysis-aggregate-metrics-",
    "hydroanalysis-ml-correct-",
)


def commands_for(task_id: str, workspace: Path, skills: Path) -> tuple[list[tuple[list[str], int]], list[str]]:
    number = int(task_id.rsplit("-", 1)[1])
    if task_id.startswith("hydroanalysis-event-metrics-"):
        script = skills / "evaluation-diagnostics/compute-event-flood-metrics/examples/compute_event_metrics.py"
        command = [
            sys.executable, str(script),
            "--events-dir", "events", "--timestep-hours", "1", "--thresholds", "thresholds.json",
            "--output-format", "csv", "--output-dir", str(workspace / "event-metrics"),
        ]
        code = 2 if number == 3 else 0
        # The native error mode still writes the partial table for healthy events.
        return [(command, code)], []
    if task_id.startswith("hydroanalysis-series-metrics-"):
        script = skills / "evaluation-diagnostics/compute-continuous-series-metrics/examples/compute_series_metrics.py"
        command = [
            sys.executable, str(script),
            "--series", "series.csv", "--timestep-hours", "1",
            "--output-format", "csv", "--output-dir", str(workspace / "series-metrics"),
        ]
        code = 2 if number == 3 else 0
        return [(command, code)], ["series-metrics/series_metrics.csv"]
    if task_id.startswith("hydroanalysis-aggregate-metrics-"):
        script = skills / "evaluation-diagnostics/aggregate-event-metrics/examples/aggregate_event_metrics.py"
        command = [
            sys.executable, str(script),
            "--metrics-table", "event_metrics.csv", "--value-columns", "nse,volume_error_relative",
        ]
        if number == 1:
            command += ["--group-by", "catchment", "--pass-columns", "qualified_volume,qualified_peak", "--pass-thresholds", "thresholds.json"]
        if number == 3:
            command += ["--statistics", "mean,p25"]
        command += ["--output-format", "csv", "--output-dir", str(workspace / "aggregate-metrics")]
        code = 1 if number == 3 else 0
        return [(command, code)], ["aggregate-metrics/aggregate_metrics.csv"]
    script = skills / "post-processing/correct-residual-with-ml/examples/correct_residual_ml.py"
    train = [
        sys.executable, str(script),
        "--mode", "train", "--table", "train_table.csv", "--time-column", "time",
        "--base-column", "Q_total", "--observed-column", "Q_obs", "--feature-columns", "P,Qt",
        "--backend", "ridge", "--hyperparameters", "hyperparameters.json",
        "--split", "chronological", "--test-size", "0.25",
    ]
    if number < 3:
        train += ["--random-state", "20260928"]
    if number == 2:
        train += ["--lag-spec", "Qt:1"]
    train += ["--output-format", "csv", "--output-dir", str(workspace / "ml-train")]
    if number == 1:
        predict = [
            sys.executable, str(script),
            "--mode", "predict", "--table", "predict_table.csv", "--time-column", "time",
            "--base-column", "Q_total", "--model-in", str(workspace / "ml-train" / "model.joblib"),
            "--output-format", "csv", "--output-dir", str(workspace / "ml-predict"),
        ]
        return [(train, 0), (predict, 0)], []
    code = 1 if number == 3 else 0
    forbidden = ["ml-train/corrected_series.csv", "ml-train/model_card.json", "ml-train/model.joblib"]
    return [(train, code)], forbidden


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS)
    args = parser.parse_args()
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hsqb-diagnostics-verify-") as temporary:
        root = Path(temporary)
        for item in runner.discover_tasks("tests", domain="results-analysis"):
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
    print("All diagnostics tasks passed real-script verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
