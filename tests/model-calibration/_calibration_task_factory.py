"""Deterministic fixtures for atomic model-calibration benchmark tasks."""

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


ROOT = Path(__file__).resolve().parent
DEFAULT_SKILLS_ROOT = Path(r"E:\HydroTune-Skills（仿BioSkills版）")

ALGORITHMS: dict[str, dict[str, Any]] = {
    "de": {
        "skill": "model-calibration/calibrate-model-de",
        "folder": "calibrate-model-de",
        "script": "calibrate_model_de.py",
        "output": "calibration-de",
    },
    "ga": {
        "skill": "model-calibration/calibrate-model-ga",
        "folder": "calibrate-model-ga",
        "script": "calibrate_model_ga.py",
        "output": "calibration-ga",
    },
    "pso": {
        "skill": "model-calibration/calibrate-model-pso",
        "folder": "calibrate-model-pso",
        "script": "calibrate_model_pso.py",
        "output": "calibration-pso",
    },
    "sce-ua": {
        "skill": "model-calibration/calibrate-model-sce-ua",
        "folder": "calibrate-model-sce-ua",
        "script": "calibrate_model_sce_ua.py",
        "output": "calibration-sce",
    },
    "two-stage": {
        "skill": "model-calibration/calibrate-model-two-stage",
        "folder": "calibrate-model-two-stage",
        "script": "calibrate_model_two_stage.py",
        "output": "calibration-two-stage",
    },
}

ADAPTER_SOURCE = '''"""Deterministic calibration evaluator used by HSQB fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


class Evaluator:
    def __init__(self, problem, problem_dir):
        reference = next(item for item in problem["inputs"] if item["id"] == "fixture")
        self.fixture = json.loads((Path(problem_dir) / reference["path"]).read_text(encoding="utf-8"))
        self.calls = 0

    def _loss(self, parameters, split):
        target_key = "calibration_target" if split == "calibration" else "validation_target"
        target = self.fixture.get(target_key, self.fixture["calibration_target"])
        weights = self.fixture.get("weights", {})
        return float(sum(float(weights.get(name, 1.0)) * (float(value) - float(target[name])) ** 2 for name, value in parameters.items()))

    def _payload(self, parameters, split):
        loss = self._loss(parameters, split)
        direction = self.fixture["direction"]
        objective = loss if direction == "minimize" else 1.0 - loss
        return {"objective": objective, "metrics": {"objective": objective, "rmse": loss ** 0.5}}

    def evaluate(self, parameters, split):
        if split != "calibration":
            raise ValueError("search evaluate must use calibration split only")
        self.calls += 1
        if self.calls in set(self.fixture.get("fail_on_calls", [])):
            raise RuntimeError(f"synthetic evaluator failure at call {self.calls}")
        return self._payload(parameters, split)

    def materialize(self, parameters, split):
        payload = self._payload(parameters, split)
        observed = np.linspace(1.0, 2.1, 12) + (0.25 if split == "validation" else 0.0)
        target_key = "calibration_target" if split == "calibration" else "validation_target"
        target = self.fixture.get(target_key, self.fixture["calibration_target"])
        shift = sum(float(parameters[name]) - float(target[name]) for name in parameters)
        series = pd.DataFrame({
            "time": pd.date_range("2024-01-01" if split == "calibration" else "2025-01-01", periods=12, freq="D"),
            "observed": observed,
            "simulated": observed + shift,
            "scored": [False, False] + [True] * 10,
        })
        return {**payload, "series": series}


def create_evaluator(problem, problem_dir):
    return Evaluator(problem, problem_dir)
'''


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
    _write_bytes(path, _stable_json(value))


def _task_parts(task_id: str) -> tuple[str, int]:
    if not task_id.startswith("hydromodel-"):
        raise ValueError(f"unsupported calibration task id: {task_id}")
    stem, raw_index = task_id.rsplit("-", 1)
    algorithm = stem.removeprefix("hydromodel-")
    if algorithm not in ALGORITHMS or raw_index not in {"001", "002", "003"}:
        raise ValueError(f"unsupported calibration task id: {task_id}")
    return algorithm, int(raw_index)


def _base_config(algorithm: str) -> dict[str, Any]:
    common = {"schema_version": "1.0", "algorithm": algorithm, "seed": 42, "max_evaluations": 100, "max_failed_evaluations": 2}
    specific = {
        "de": {"population_multiplier": 3, "mutation_factor": 0.8, "crossover_probability": 0.7, "max_generations": 3, "tolerance": 1e-9, "polish": False},
        "ga": {"population_size": 6, "max_generations": 2, "tournament_size": 3, "elite_count": 1, "crossover_probability": 1.0, "mutation_probability": 0.4, "gene_mutation_probability": 0.5},
        "pso": {"particle_count": 6, "max_iterations": 3, "inertia_weight": 0.7, "cognitive_coefficient": 1.5, "social_coefficient": 1.5, "velocity_limit_fraction": 0.2},
        "sce-ua": {"complex_count": 2, "points_per_complex": 3, "evolution_steps": 2, "max_loops": 2, "reflection_coefficient": 1.0, "contraction_coefficient": 0.5, "stall_loops": 3, "objective_tolerance": 1e-12},
        "two-stage": {"annealing_max_evaluations": 20, "local_max_evaluations": 10, "annealing_max_iterations": 50, "local_max_iterations": 20, "initial_temperature": 5230.0, "restart_temperature_ratio": 0.0001, "visit": 2.62, "accept": -5.0, "local_ftol": 1e-9},
    }[algorithm]
    return {**common, **specific}


def _spec(task_id: str) -> dict[str, Any]:
    algorithm, index = _task_parts(task_id)
    parameters = [
        {"name": "x", "lower": -2.0, "upper": 2.0},
        {"name": "y", "lower": 10.0, "upper": 30.0},
    ]
    target = {"x": 0.35, "y": 22.0}
    weights = {"x": 1.0, "y": 0.01}
    config = _base_config(algorithm)
    direction = "minimize" if algorithm in {"pso", "two-stage"} else "maximize"
    fixture: dict[str, Any] = {"direction": direction, "calibration_target": target, "validation_target": target, "weights": weights, "fail_on_calls": []}

    success_titles = {
        "de": "Calibrate an interior optimum with differential evolution",
        "ga": "Calibrate a one-parameter model with genetic crossover enabled",
        "pso": "Apply span-scaled particle velocity limits",
        "sce-ua": "Evolve minimally sized shuffled complexes",
        "two-stage": "Calibrate with annealing followed by L-BFGS-B",
    }
    warning_titles = {
        "de": "Return the best DE solution at the hard evaluation budget",
        "ga": "Count GA elite reevaluation against the hard budget",
        "pso": "Continue PSO after a bounded failed evaluation",
        "sce-ua": "Return the best SCE-UA solution at the hard budget",
        "two-stage": "Retain the annealing solution after a local evaluation failure",
    }
    error_titles = {
        "de": "Reject a DE config missing mutation_factor",
        "ga": "Reject a GA tournament larger than its population",
        "pso": "Reject a zero PSO velocity limit fraction",
        "sce-ua": "Reject an undersized SCE-UA complex",
        "two-stage": "Reject two-stage budgets exceeding the global budget",
    }

    if algorithm == "ga" and index == 1:
        parameters = [{"name": "x", "lower": -2.0, "upper": 2.0}]
        target, weights = {"x": 0.35}, {"x": 1.0}
        fixture.update({"calibration_target": target, "validation_target": target, "weights": weights})
    if index == 2:
        if algorithm == "de":
            config["max_evaluations"] = 5
        elif algorithm == "ga":
            config.update({"max_generations": 3, "max_evaluations": 10})
        elif algorithm == "pso":
            fixture["fail_on_calls"] = [1]
        elif algorithm == "sce-ua":
            config["max_evaluations"] = 8
        elif algorithm == "two-stage":
            config.update({"annealing_max_evaluations": 12, "local_max_evaluations": 1, "max_evaluations": 20})
            fixture["fail_on_calls"] = [13]
    if index == 3:
        if algorithm == "de":
            config.pop("mutation_factor")
        elif algorithm == "ga":
            config["tournament_size"] = 7
        elif algorithm == "pso":
            config["velocity_limit_fraction"] = 0.0
        elif algorithm == "sce-ua":
            config["points_per_complex"] = 2
        elif algorithm == "two-stage":
            config.update({"max_evaluations": 20, "annealing_max_evaluations": 15, "local_max_evaluations": 10})

    title = (success_titles if index == 1 else warning_titles if index == 2 else error_titles)[algorithm]
    return {"algorithm": algorithm, "index": index, "parameters": parameters, "fixture": fixture, "config": config, "title": title}


def _positive_grading(output: str) -> list[dict[str, Any]]:
    golden = f"expected/golden_workspace/{output}"
    result = f"{output}/result.json"
    return [
        {
            "name": "artifact_schema", "type": "file_check",
            "targets": [f"{output}/best_parameters.json", f"{output}/calibration_trace.csv", f"{output}/calibration_metrics.json", f"{output}/validation_metrics.json", f"{output}/calibration_series.csv", f"{output}/validation_series.csv", result],
            "required_columns": {
                f"{output}/best_parameters.json": ["schema_version", "algorithm", "parameters"],
                f"{output}/calibration_trace.csv": ["evaluation", "stage", "objective", "loss", "status", "message", "best_so_far"],
                f"{output}/calibration_metrics.json": ["schema_version", "split", "objective", "metrics"],
                f"{output}/validation_metrics.json": ["schema_version", "split", "objective", "metrics"],
                f"{output}/calibration_series.csv": ["time", "observed", "simulated", "scored"],
                f"{output}/validation_series.csv": ["time", "observed", "simulated", "scored"],
                result: ["skill", "status", "algorithm", "artifacts", "checks", "warnings", "termination_reason", "evaluation_count"],
            },
            "weight": 0.10,
        },
        {"name": "best_parameters", "type": "exact_match", "target": f"{output}/best_parameters.json", "field": "parameters", "reference": f"{golden}/best_parameters.json", "weight": 0.15},
        {"name": "search_trace", "type": "table_match", "target": f"{output}/calibration_trace.csv", "reference": f"{golden}/calibration_trace.csv", "atol": 1e-10, "rtol": 1e-10, "weight": 0.15},
        {"name": "calibration_metrics", "type": "exact_match", "target": f"{output}/calibration_metrics.json", "reference": f"{golden}/calibration_metrics.json", "weight": 0.05},
        {"name": "validation_metrics", "type": "exact_match", "target": f"{output}/validation_metrics.json", "reference": f"{golden}/validation_metrics.json", "weight": 0.05},
        {"name": "calibration_series", "type": "table_match", "target": f"{output}/calibration_series.csv", "reference": f"{golden}/calibration_series.csv", "datetime_columns": ["time"], "atol": 1e-10, "rtol": 1e-10, "weight": 0.075},
        {"name": "validation_series", "type": "table_match", "target": f"{output}/validation_series.csv", "reference": f"{golden}/validation_series.csv", "datetime_columns": ["time"], "atol": 1e-10, "rtol": 1e-10, "weight": 0.075},
        {"name": "result_status", "type": "exact_match", "target": result, "field": "status", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_warnings", "type": "exact_match", "target": result, "field": "warnings", "reference": f"{golden}/result.json", "weight": 0.04},
        {"name": "termination_reason", "type": "exact_match", "target": result, "field": "termination_reason", "reference": f"{golden}/result.json", "weight": 0.04},
        {"name": "evaluation_count", "type": "exact_match", "target": result, "field": "evaluation_count", "reference": f"{golden}/result.json", "weight": 0.03},
        {"name": "failed_evaluation_count", "type": "exact_match", "target": result, "field": "failed_evaluation_count", "reference": f"{golden}/result.json", "weight": 0.02},
        {"name": "result_checks", "type": "exact_match", "target": result, "field": "checks", "reference": f"{golden}/result.json", "weight": 0.02},
        {"name": "artifact_references", "type": "artifact_reference_check", "target": result, "required_keys": ["best_parameters", "calibration_trace", "calibration_metrics", "validation_metrics", "calibration_series", "validation_series"], "weight": 0.15},
    ]


def _error_grading(output: str) -> list[dict[str, Any]]:
    result = f"{output}/result.json"
    golden = f"expected/golden_workspace/{output}/result.json"
    return [
        {"name": "result_schema", "type": "file_check", "target": result, "required_columns": ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"], "expected_rows": {result: 1}, "weight": 0.15},
        {"name": "result_skill", "type": "exact_match", "target": result, "field": "skill", "reference": golden, "weight": 0.10},
        {"name": "result_status", "type": "exact_match", "target": result, "field": "status", "reference": golden, "weight": 0.20},
        {"name": "failure_reason", "type": "exact_match", "target": result, "field": "message", "reference": golden, "weight": 0.25},
        {"name": "empty_artifacts", "type": "exact_match", "target": result, "field": "artifacts", "reference": golden, "weight": 0.10},
        {"name": "no_standard_outputs", "type": "file_absence_check", "targets": [f"{output}/best_parameters.json", f"{output}/calibration_trace.csv", f"{output}/calibration_metrics.json", f"{output}/validation_metrics.json", f"{output}/calibration_series.csv", f"{output}/validation_series.csv"], "weight": 0.20},
    ]


def _build_task(task_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    meta = ALGORITHMS[spec["algorithm"]]
    output = meta["output"]
    positive = spec["index"] < 3
    behavior = "Complete the configured search and preserve the independent validation split."
    if spec["index"] == 2:
        behavior = "Preserve the best feasible solution and report the native warning without changing algorithms or budgets."
    elif spec["index"] == 3:
        behavior = "Reject the invalid optimizer config, write only the native error result.json, and leave no normal calibration artifacts."
    prompt = (
        f"Use calibration-problem.json and optimizer-config.json exactly as supplied to run {meta['skill']}. "
        "All parameter bounds, objective direction, split labels, variable units, hashes, and warm-up semantics are confirmed in the problem file. "
        "Use calibration only for search and evaluate validation only after parameters are locked. Do not repair the optimizer config, alter its seed or budget, switch optimizers, or use validation for selection. "
        f"Write the native outputs under {output}/. {behavior}"
    )
    required = [f"{output}/result.json"]
    if positive:
        required = [f"{output}/best_parameters.json", f"{output}/calibration_trace.csv", f"{output}/calibration_metrics.json", f"{output}/validation_metrics.json", f"{output}/calibration_series.csv", f"{output}/validation_series.csv", *required]
    return {
        "id": task_id,
        "title": spec["title"],
        "domain": "model-calibration",
        "difficulty": "advanced" if spec["algorithm"] in {"sce-ua", "two-stage"} else "intermediate",
        "primary_skill": meta["skill"],
        "secondary_skills": [],
        "prompt": prompt,
        "data_description": "A deterministic continuous two-split calibration problem with an explicit hashed Python evaluator and versioned optimizer configuration.",
        "data_files": ["calibration-problem.json", "optimizer-config.json", "fixture.json", "synthetic_adapter.py"],
        "required_outputs": required,
        "setup_notes": [
            "The evaluator contract implements create_evaluator(), evaluate(), and materialize(); no upstream skill is required.",
            "The first two rows of each materialized split are confirmed warm-up rows with scored=false.",
            "Do not install software or substitute another optimization algorithm.",
        ],
        "timeout_seconds": 300,
        "grading": _positive_grading(output) if positive else _error_grading(output),
    }


def _normalize_result(path: Path) -> None:
    if not path.is_file():
        return
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    inputs = document.get("inputs")
    if isinstance(inputs, dict):
        for reference in inputs.values():
            if isinstance(reference, dict) and isinstance(reference.get("path"), str):
                reference["path"] = Path(reference["path"]).name
    document["provenance"] = {"generator": "HydroTune skill script; runtime versions normalized for the golden oracle"}
    path.write_bytes(_stable_json(document))


def _skill_script(algorithm: str) -> Path:
    configured = os.environ.get("HYDROTUNE_SKILLS_ROOT", "").strip().strip('"')
    skills_root = Path(configured) if configured else DEFAULT_SKILLS_ROOT
    meta = ALGORITHMS[algorithm]
    script = skills_root / "model-calibration" / meta["folder"] / "examples" / meta["script"]
    if not script.is_file():
        raise FileNotFoundError(f"calibration skill script not found: {script}")
    return script


def _generate_golden(task_dir: Path, spec: dict[str, Any]) -> None:
    meta = ALGORITHMS[spec["algorithm"]]
    expected_code = 1 if spec["index"] == 3 else 0
    with tempfile.TemporaryDirectory(prefix=f"hsqb-{task_dir.name}-") as raw_temp:
        temp = Path(raw_temp)
        work = temp / "workspace"
        shutil.copytree(task_dir / "data", work)
        output = work / meta["output"]
        completed = subprocess.run(
            [sys.executable, str(_skill_script(spec["algorithm"])), "--problem", str(work / "calibration-problem.json"), "--optimizer-config", str(work / "optimizer-config.json"), "--output-dir", str(output)],
            cwd=work,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )
        if completed.returncode != expected_code:
            raise RuntimeError(f"{task_dir.name}: expected exit {expected_code}, got {completed.returncode}: {completed.stderr}")
        _normalize_result(output / "result.json")
        golden = task_dir / "expected" / "golden_workspace" / meta["output"]
        for source in sorted(output.iterdir()):
            if source.is_file():
                _write_bytes(golden / source.name, source.read_bytes())


def generate_task(task_id: str) -> None:
    spec = _spec(task_id)
    task_dir = ROOT / task_id
    data_dir = task_dir / "data"
    _write_bytes(data_dir / "synthetic_adapter.py", ADAPTER_SOURCE.encode("utf-8"))
    _write_json(data_dir / "fixture.json", spec["fixture"])
    adapter = data_dir / "synthetic_adapter.py"
    fixture = data_dir / "fixture.json"
    problem = {
        "schema_version": "1.0",
        "adapter": {"path": adapter.name, "sha256": _sha256(adapter)},
        "inputs": [{"id": "fixture", "path": fixture.name, "sha256": _sha256(fixture)}],
        "parameters": spec["parameters"],
        "objective": {"metric": "objective", "direction": spec["fixture"]["direction"]},
        "splits": {"calibration": "calibration", "validation": "validation"},
        "data_shape": "continuous",
        "warmup": {"confirmed": True, "semantics": "the first two rows of each split are unscored warm-up rows"},
        "variables": {
            "observed": {"semantics": "synthetic observed discharge", "units": "m3/s"},
            "simulated": {"semantics": "synthetic simulated discharge", "units": "m3/s"},
        },
        "objective_consistency_tolerance": 1e-12,
    }
    _write_json(data_dir / "calibration-problem.json", problem)
    _write_json(data_dir / "optimizer-config.json", spec["config"])
    _generate_golden(task_dir, spec)
    _write_json(task_dir / "task.json", _build_task(task_id, spec))

