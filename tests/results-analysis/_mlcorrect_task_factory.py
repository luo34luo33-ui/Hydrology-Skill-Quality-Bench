"""Deterministic fixtures for the ML residual-correction benchmark tasks (hydroanalysis-ml-correct-001..003)."""

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


ROOT = Path(__file__).resolve().parent
DEFAULT_SKILLS_ROOT = Path(r"E:\HydroTune-Skills（仿BioSkills版）")
SKILL_REF = "post-processing/correct-residual-with-ml"
SKILL_FOLDER = "post-processing/correct-residual-with-ml"
SKILL_SCRIPT = "correct_residual_ml.py"
TRAIN_OUTPUT = "ml-train"
PREDICT_OUTPUT = "ml-predict"
RANDOM_STATE = 20260928
TASK_IDS = [f"hydroanalysis-ml-correct-{index:03d}" for index in (1, 2, 3)]


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


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = frame.to_csv(
        index=False,
        float_format="%.12g",
        lineterminator="\n",
        encoding="utf-8",
        date_format="%Y-%m-%d %H:%M:%S",
    ).encode("utf-8")
    _write_bytes(path, content)


def _skill_script() -> Path:
    configured = os.environ.get("HYDROTUNE_SKILLS_ROOT", "").strip().strip('"')
    skills_root = Path(configured) if configured else DEFAULT_SKILLS_ROOT
    script = skills_root / SKILL_FOLDER / "examples" / SKILL_SCRIPT
    if not script.is_file():
        raise FileNotFoundError(f"ml-correct skill script not found: {script}")
    return script


def _index(task_id: str) -> int:
    if task_id not in TASK_IDS:
        raise ValueError(f"unsupported ml-correct task id: {task_id}")
    return int(task_id.rsplit("-", 1)[1])


def _train_table() -> pd.DataFrame:
    t = np.arange(120, dtype=float)
    qt = 20.0 + 60.0 * np.exp(-(((t - 50.0) / 15.0) ** 2)) + 5.0 * np.sin(t / 4.0)
    precipitation = np.where((t >= 30) & (t < 40), 6.0, 0.0) + np.where((t >= 60) & (t < 68), 9.0, 0.0)
    residual = 1.5 + 0.06 * qt + 4.0 * np.sin(2.0 * np.pi * t / 24.0)
    return pd.DataFrame(
        {
            "time": pd.date_range("2024-10-01 00:00", periods=120, freq="h"),
            "P": precipitation,
            "Qt": qt,
            "Q_total": qt,
            "Q_obs": qt + residual,
        }
    )


def _predict_table() -> pd.DataFrame:
    t = np.arange(96, dtype=float)
    qt = 25.0 + 70.0 * np.exp(-(((t - 30.0) / 12.0) ** 2)) + 4.0 * np.sin(t / 4.0)
    precipitation = np.where((t >= 10) & (t < 18), 7.0, 0.0)
    return pd.DataFrame(
        {
            "time": pd.date_range("2024-10-06 00:00", periods=96, freq="h"),
            "P": precipitation,
            "Qt": qt,
            "Q_total": qt,
        }
    )


def _data_frames(task_id: str) -> dict[str, pd.DataFrame]:
    index = _index(task_id)
    frames = {"train_table.csv": _train_table()}
    if index == 1:
        frames["predict_table.csv"] = _predict_table()
    return frames


def _extra_files(task_id: str) -> dict[str, dict[str, Any]]:
    return {"hyperparameters.json": {"alpha": 1.0}}


def _train_command(task_id: str, work: Path) -> list[str]:
    index = _index(task_id)
    args = [
        sys.executable,
        str(_skill_script()),
        "--mode",
        "train",
        "--table",
        "train_table.csv",
        "--time-column",
        "time",
        "--base-column",
        "Q_total",
        "--observed-column",
        "Q_obs",
        "--feature-columns",
        "P,Qt",
        "--backend",
        "ridge",
        "--hyperparameters",
        "hyperparameters.json",
        "--split",
        "chronological",
        "--test-size",
        "0.25",
    ]
    if index < 3:
        args += ["--random-state", str(RANDOM_STATE)]
    if index == 2:
        args += ["--lag-spec", "Qt:1"]
    args += ["--output-format", "csv", "--output-dir", str(work / TRAIN_OUTPUT)]
    return args


def _golden_runs(task_id: str, work: Path) -> list[tuple[list[str], int]]:
    index = _index(task_id)
    runs = [(_train_command(task_id, work), 1 if index == 3 else 0)]
    if index == 1:
        predict = [
            sys.executable,
            str(_skill_script()),
            "--mode",
            "predict",
            "--table",
            "predict_table.csv",
            "--time-column",
            "time",
            "--base-column",
            "Q_total",
            "--model-in",
            str(work / TRAIN_OUTPUT / "model.joblib"),
            "--output-format",
            "csv",
            "--output-dir",
            str(work / PREDICT_OUTPUT),
        ]
        runs.append((predict, 0))
    return runs


def _titles() -> dict[int, str]:
    return {
        1: "Train a deterministic ridge residual correction and apply it to a new period",
        2: "Preserve the native lag-row warning when training with lagged features",
        3: "Reject a residual-correction training run without a random state",
    }


def _prompts() -> dict[int, str]:
    return {
        1: (
            "Use train_table.csv, predict_table.csv, and hyperparameters.json exactly as supplied to run "
            "post-processing/correct-residual-with-ml. All tables are hourly; Q_total and Q_obs are discharge in m3/s and P is "
            "precipitation in mm/h. Train with --base-column Q_total, --observed-column Q_obs, --feature-columns P,Qt, backend ridge, "
            "the confirmed hyperparameters, random-state 20260928, split chronological, and test-size 0.25; then predict on "
            "predict_table.csv with --model-in pointing at the trained model.joblib. "
            "Write the native train outputs (corrected_series.csv, model_card.json, model.joblib, result.json) under ml-train/ and the "
            "native predict outputs (corrected_series.csv, result.json) under ml-predict/. "
            "Do not change the residual definition, flip its sign, alter lag configuration, or invent hyperparameters."
        ),
        2: (
            "Use train_table.csv and hyperparameters.json exactly as supplied to run post-processing/correct-residual-with-ml in train "
            "mode with --base-column Q_total, --observed-column Q_obs, --feature-columns P,Qt, --lag-spec Qt:1 (drop policy), backend "
            "ridge, the confirmed hyperparameters, random-state 20260928, split chronological, and test-size 0.25. "
            "The lag configuration necessarily discards the first rows; keep the native lag_rows_dropped warning in result.json. "
            "Write the native outputs (corrected_series.csv, model_card.json, model.joblib, result.json) under ml-train/. "
            "Do not switch to a fill policy, trim the series yourself, or suppress the warning."
        ),
        3: (
            "Use train_table.csv and hyperparameters.json exactly as supplied to run post-processing/correct-residual-with-ml in train "
            "mode with --base-column Q_total, --observed-column Q_obs, --feature-columns P,Qt, backend ridge, and the confirmed "
            "hyperparameters. No random state is provided anywhere in the task, and none may be invented. "
            "Run the skill verbatim; it must reject the training request itself and write only the native result.json under ml-train/. "
            "No corrected_series.csv, model_card.json, or model.joblib may remain in ml-train/."
        ),
    }


def _positive_grading(index: int) -> list[dict[str, Any]]:
    golden_train = f"expected/golden_workspace/{TRAIN_OUTPUT}"
    train_result = f"{TRAIN_OUTPUT}/result.json"
    corrected_columns = ["time", "Q_total", "Q_obs", "residual", "predicted_residual", "corrected", "P", "Qt"]
    model_card_keys = [
        "skill", "backend", "hyperparameters", "random_state", "split", "test_size", "base_column", "observed_column",
        "output_column", "feature_columns", "lag_spec", "residual_definition", "train_rows", "test_rows", "train_r2",
        "train_rmse", "test_r2", "test_rmse", "backend_version",
    ]
    result_keys = ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"]
    criteria: list[dict[str, Any]] = [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": [f"{TRAIN_OUTPUT}/corrected_series.csv", f"{TRAIN_OUTPUT}/model_card.json", f"{TRAIN_OUTPUT}/model.joblib", train_result],
            "required_columns": {
                f"{TRAIN_OUTPUT}/corrected_series.csv": corrected_columns,
                f"{TRAIN_OUTPUT}/model_card.json": model_card_keys,
                train_result: result_keys,
            },
            "weight": 0.10,
        },
        {
            "name": "train_corrected_series",
            "type": "table_match",
            "target": f"{TRAIN_OUTPUT}/corrected_series.csv",
            "reference": f"{golden_train}/corrected_series.csv",
            "atol": 1e-6,
            "rtol": 1e-6,
            "weight": 0.20,
        },
        {"name": "model_card_backend", "type": "exact_match", "target": f"{TRAIN_OUTPUT}/model_card.json", "field": "backend", "reference": f"{golden_train}/model_card.json", "weight": 0.05},
        {"name": "model_card_random_state", "type": "exact_match", "target": f"{TRAIN_OUTPUT}/model_card.json", "field": "random_state", "reference": f"{golden_train}/model_card.json", "weight": 0.05},
        {"name": "model_card_split", "type": "exact_match", "target": f"{TRAIN_OUTPUT}/model_card.json", "field": "split", "reference": f"{golden_train}/model_card.json", "weight": 0.05},
        {"name": "model_card_features", "type": "exact_match", "target": f"{TRAIN_OUTPUT}/model_card.json", "field": "feature_columns", "reference": f"{golden_train}/model_card.json", "weight": 0.05},
        {"name": "model_card_residual_definition", "type": "exact_match", "target": f"{TRAIN_OUTPUT}/model_card.json", "field": "residual_definition", "reference": f"{golden_train}/model_card.json", "weight": 0.05},
        {
            "name": "model_card_test_r2",
            "type": "range_check",
            "target": f"{TRAIN_OUTPUT}/model_card.json",
            "field": "test_r2",
            "reference": f"{golden_train}/model_card.json",
            "tolerance": 0.05,
            "weight": 0.05 if index == 1 else 0.10,
        },
        {"name": "train_status", "type": "exact_match", "target": train_result, "field": "status", "reference": f"{golden_train}/result.json", "weight": 0.05},
        {
            "name": "train_artifact_references",
            "type": "artifact_reference_check",
            "target": train_result,
            "required_keys": ["corrected_table", "model_card", "model"],
            "weight": 0.10,
        },
    ]
    if index == 1:
        criteria += [
            {
                "name": "predict_corrected_series",
                "type": "table_match",
                "target": f"{PREDICT_OUTPUT}/corrected_series.csv",
                "reference": f"expected/golden_workspace/{PREDICT_OUTPUT}/corrected_series.csv",
                "atol": 1e-6,
                "rtol": 1e-6,
                "weight": 0.10,
            },
            {"name": "predict_status", "type": "exact_match", "target": f"{PREDICT_OUTPUT}/result.json", "field": "status", "reference": f"expected/golden_workspace/{PREDICT_OUTPUT}/result.json", "weight": 0.05},
            {
                "name": "predict_artifact_references",
                "type": "artifact_reference_check",
                "target": f"{PREDICT_OUTPUT}/result.json",
                "required_keys": ["corrected_table"],
                "weight": 0.10,
            },
        ]
    else:
        criteria += [
            {"name": "result_warnings", "type": "exact_match", "target": train_result, "field": "warnings", "reference": f"{golden_train}/result.json", "weight": 0.10},
            {"name": "result_checks", "type": "exact_match", "target": train_result, "field": "checks", "reference": f"{golden_train}/result.json", "weight": 0.10},
        ]
    total = sum(criterion["weight"] for criterion in criteria)
    if abs(total - 1.0) > 1e-9:
        raise RuntimeError(f"ml-correct-{index:03d} grading weights sum to {total}")
    return criteria


def _error_grading() -> list[dict[str, Any]]:
    result = f"{TRAIN_OUTPUT}/result.json"
    golden = f"expected/golden_workspace/{TRAIN_OUTPUT}/result.json"
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
            "targets": [f"{TRAIN_OUTPUT}/corrected_series.csv", f"{TRAIN_OUTPUT}/model_card.json", f"{TRAIN_OUTPUT}/model.joblib"],
            "weight": 0.20,
        },
    ]


def _build_task(task_id: str) -> dict[str, Any]:
    index = _index(task_id)
    data_files = sorted(_data_frames(task_id)) + sorted(_extra_files(task_id))
    if index == 1:
        required = [
            f"{TRAIN_OUTPUT}/corrected_series.csv",
            f"{TRAIN_OUTPUT}/model_card.json",
            f"{TRAIN_OUTPUT}/model.joblib",
            f"{TRAIN_OUTPUT}/result.json",
            f"{PREDICT_OUTPUT}/corrected_series.csv",
            f"{PREDICT_OUTPUT}/result.json",
        ]
        grading = _positive_grading(index)
    elif index == 2:
        required = [
            f"{TRAIN_OUTPUT}/corrected_series.csv",
            f"{TRAIN_OUTPUT}/model_card.json",
            f"{TRAIN_OUTPUT}/model.joblib",
            f"{TRAIN_OUTPUT}/result.json",
        ]
        grading = _positive_grading(index)
    else:
        required = [f"{TRAIN_OUTPUT}/result.json"]
        grading = _error_grading()
    return {
        "id": task_id,
        "title": _titles()[index],
        "domain": "results-analysis",
        "difficulty": "intermediate" if index < 3 else "basic",
        "primary_skill": SKILL_REF,
        "secondary_skills": [],
        "prompt": _prompts()[index],
        "data_description": "A deterministic ML residual-correction fixture with confirmed columns, backend, hyperparameters, and split; training is reproducible from the provided random state.",
        "data_files": data_files,
        "required_outputs": required,
        "setup_notes": [
            "scikit-learn is pre-installed in the evaluation environment.",
            "The backend, hyperparameters, random state, split, and columns are confirmed and must not be altered.",
            "The residual is observed minus base and the correction is base plus the predicted residual.",
        ],
        "timeout_seconds": 300,
        "grading": grading,
    }


def _normalize_result(path: Path) -> None:
    if not path.is_file():
        return
    document = json.loads(path.read_text(encoding="utf-8-sig"))

    def normalize_references(section: Any) -> None:
        if not isinstance(section, dict):
            return
        for reference in section.values():
            if isinstance(reference, dict) and isinstance(reference.get("path"), str):
                value = Path(reference["path"])
                if value.is_absolute() or ".." in value.parts:
                    # Cross-directory references (e.g. the model reused by predict mode)
                    # keep only the file name so the golden oracle stays deterministic.
                    reference["path"] = value.name

    normalize_references(document.get("inputs"))
    normalize_references(document.get("artifacts"))
    document["provenance"] = {"generator": "HydroTune skill script; runtime versions normalized for the golden oracle"}
    path.write_bytes(_stable_json(document))


def _generate_golden(task_dir: Path, task_id: str) -> None:
    with tempfile.TemporaryDirectory(prefix=f"hsqb-{task_dir.name}-") as raw_temp:
        temp = Path(raw_temp)
        work = temp / "workspace"
        shutil.copytree(task_dir / "data", work)
        for args, expected_code in _golden_runs(task_id, work):
            completed = subprocess.run(
                args,
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
        for output in (TRAIN_OUTPUT, PREDICT_OUTPUT):
            source_dir = work / output
            if not source_dir.is_dir():
                continue
            _normalize_result(source_dir / "result.json")
            golden = task_dir / "expected" / "golden_workspace" / output
            for source in sorted(source_dir.iterdir()):
                if source.is_file():
                    _write_bytes(golden / source.name, source.read_bytes())


def generate_task(task_id: str) -> None:
    _index(task_id)
    task_dir = ROOT / task_id
    data_dir = task_dir / "data"
    for name, frame in _data_frames(task_id).items():
        _write_csv(data_dir / name, frame)
    for name, value in _extra_files(task_id).items():
        _write_json(data_dir / name, value)
    _generate_golden(task_dir, task_id)
    _write_json(task_dir / "task.json", _build_task(task_id))
