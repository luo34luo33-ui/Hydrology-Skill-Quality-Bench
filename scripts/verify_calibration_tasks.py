"""Run deterministic calibration skill scripts against HSQB tasks; never runs an Agent."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILLS_ROOT = Path(r"E:\HydroTune-Skills（仿BioSkills版）")
SCRIPT_NAMES = {
    "model-calibration/calibrate-model-de": ("calibrate-model-de", "calibrate_model_de.py"),
    "model-calibration/calibrate-model-ga": ("calibrate-model-ga", "calibrate_model_ga.py"),
    "model-calibration/calibrate-model-pso": ("calibrate-model-pso", "calibrate_model_pso.py"),
    "model-calibration/calibrate-model-sce-ua": ("calibrate-model-sce-ua", "calibrate_model_sce_ua.py"),
    "model-calibration/calibrate-model-two-stage": ("calibrate-model-two-stage", "calibrate_model_two_stage.py"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", type=Path)
    args = parser.parse_args()
    configured = os.environ.get("HYDROTUNE_SKILLS_ROOT", "").strip().strip('"')
    skills_root = (args.skills_root or (Path(configured) if configured else DEFAULT_SKILLS_ROOT)).resolve()
    sys.path.insert(0, str(ROOT))
    from harness.grader import grade_task

    task_dirs = sorted((ROOT / "tests" / "model-calibration").glob("hydromodel-*-???"))
    if len(task_dirs) != 15:
        raise RuntimeError(f"expected 15 atomic calibration tasks, found {len(task_dirs)}")
    for task_dir in task_dirs:
        task = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
        folder, script_name = SCRIPT_NAMES[task["primary_skill"]]
        script = skills_root / "model-calibration" / folder / "examples" / script_name
        output_name = task["required_outputs"][-1].split("/", 1)[0]
        expected_code = 1 if task["id"].endswith("-003") else 0
        with tempfile.TemporaryDirectory(prefix=f"verify-{task['id']}-") as raw_temp:
            workspace = Path(raw_temp) / "workspace"
            shutil.copytree(task_dir / "data", workspace)
            completed = subprocess.run(
                [sys.executable, str(script), "--problem", str(workspace / "calibration-problem.json"), "--optimizer-config", str(workspace / "optimizer-config.json"), "--output-dir", str(workspace / output_name)],
                cwd=workspace,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=120,
            )
            if completed.returncode != expected_code:
                raise RuntimeError(f"{task['id']}: expected exit {expected_code}, got {completed.returncode}: {completed.stderr}")
            score = grade_task(task, workspace, task_dir)["score"]
            if abs(score - 1.0) > 1e-12:
                raise RuntimeError(f"{task['id']}: golden verification score was {score}")
        print(f"PASS {task['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
