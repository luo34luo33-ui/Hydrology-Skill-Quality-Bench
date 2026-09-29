"""Loading and validation for the deliberately small HSQB task schema."""

from __future__ import annotations

import json
import math
from pathlib import Path, PurePosixPath
from typing import Any


DOMAINS = {"data-preprocessing", "model-calibration", "results-analysis", "spatial-analysis"}
DIFFICULTIES = {"basic", "intermediate", "advanced"}
GRADER_TYPES = {
    "file_check",
    "file_absence_check",
    "column_check",
    "exact_match",
    "range_check",
    "set_overlap",
    "numeric_correlation",
    "code_executes",
    "hydro_metric",
    "timeseries_match",
    "table_match",
    "peak_check",
    "volume_check",
    "water_balance_check",
    "parameter_range",
    "raster_match",
    "vector_match",
    "artifact_reference_check",
}
REQUIRED_FIELDS = {
    "id",
    "title",
    "domain",
    "difficulty",
    "primary_skill",
    "prompt",
    "data_files",
    "required_outputs",
    "timeout_seconds",
    "grading",
}


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    return not path.is_absolute() and ".." not in path.parts and path.parts[0] not in {"", "."}


def _contained(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _reference_paths(criterion: dict[str, Any]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for key in ("reference", "expected_file", "ranges_file"):
        value = criterion.get(key)
        if isinstance(value, str):
            found.append((key, value))
    return found


def validate_task(task: dict[str, Any], task_dir: str | Path) -> list[str]:
    """Return all validation errors for one canonical task definition."""

    errors: list[str] = []
    task_dir = Path(task_dir)
    missing = sorted(REQUIRED_FIELDS - set(task))
    if missing:
        errors.append(f"missing required fields: {missing}")
        return errors

    task_id = task.get("id")
    if not isinstance(task_id, str) or not task_id.strip():
        errors.append("id must be a non-empty string")
    elif task_dir.name != task_id:
        errors.append(f"id must match task directory name: {task_dir.name}")
    if task.get("domain") not in DOMAINS:
        errors.append(f"invalid domain: {task.get('domain')}")
    elif task_dir.parent.name != task.get("domain"):
        errors.append(f"domain must match parent directory: {task_dir.parent.name}")
    if task.get("difficulty") not in DIFFICULTIES:
        errors.append(f"invalid difficulty: {task.get('difficulty')}")
    if not isinstance(task.get("primary_skill"), str) or not task["primary_skill"].strip():
        errors.append("primary_skill must be a non-empty string")
    secondary = task.get("secondary_skills", [])
    if not isinstance(secondary, list) or not all(isinstance(item, str) and item for item in secondary):
        errors.append("secondary_skills must be a list of non-empty strings")
    if not isinstance(task.get("prompt"), str) or not task["prompt"].strip():
        errors.append("prompt must be a non-empty string")
    timeout = task.get("timeout_seconds")
    if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
        errors.append("timeout_seconds must be a positive integer")

    data_files = task.get("data_files")
    if not isinstance(data_files, list) or not data_files:
        errors.append("data_files must be a non-empty list")
    else:
        for rel in data_files:
            if not _safe_relative(rel):
                errors.append(f"unsafe data_files path: {rel!r}")
                continue
            source = task_dir / "data" / rel
            if not _contained(task_dir / "data", source):
                errors.append(f"data file escapes data/: {rel}")
            elif not source.is_file():
                errors.append(f"data file missing: data/{rel}")

    outputs = task.get("required_outputs")
    if not isinstance(outputs, list) or not outputs:
        errors.append("required_outputs must be a non-empty list")
    else:
        for rel in outputs:
            if not _safe_relative(rel):
                errors.append(f"unsafe required_outputs path: {rel!r}")
            elif PurePosixPath(rel.replace("\\", "/")).parts[0] in {"data", "expected"}:
                errors.append(f"required output uses reserved directory: {rel}")
        if len(outputs) != len(set(outputs)):
            errors.append("required_outputs contains duplicates")

    grading = task.get("grading")
    if not isinstance(grading, list) or not grading:
        errors.append("grading must be a non-empty list")
        return errors
    names: set[str] = set()
    weights: list[float] = []
    for index, criterion in enumerate(grading):
        prefix = f"grading[{index}]"
        if not isinstance(criterion, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = criterion.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{prefix}.name must be a non-empty string")
        elif name in names:
            errors.append(f"duplicate grading criterion name: {name}")
        else:
            names.add(name)
        grader_type = criterion.get("type")
        if grader_type not in GRADER_TYPES:
            errors.append(f"unknown grader type: {grader_type}")
        weight = criterion.get("weight")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool) or not math.isfinite(float(weight)) or weight < 0:
            errors.append(f"{prefix}.weight must be a finite non-negative number")
        else:
            weights.append(float(weight))
        for key in ("target", "target_file", "script"):
            value = criterion.get(key)
            if value is not None and not _safe_relative(value):
                errors.append(f"unsafe {prefix}.{key} path: {value!r}")
        targets = criterion.get("targets")
        if targets is not None:
            if not isinstance(targets, list) or not targets:
                errors.append(f"{prefix}.targets must be a non-empty list")
            else:
                for value in targets:
                    if not _safe_relative(value):
                        errors.append(f"unsafe {prefix}.targets path: {value!r}")
        for key, rel in _reference_paths(criterion):
            if not _safe_relative(rel):
                errors.append(f"unsafe {prefix}.{key} path: {rel!r}")
                continue
            parts = PurePosixPath(rel.replace("\\", "/")).parts
            if key in {"reference", "expected_file"} and parts[0] != "expected":
                errors.append(f"{prefix}.{key} must be under expected/: {rel}")
            if key == "ranges_file" and parts[0] not in {"data", "expected"}:
                errors.append(f"{prefix}.ranges_file must be under data/ or expected/: {rel}")
            path = task_dir / Path(*parts)
            if not _contained(task_dir, path) or not path.is_file():
                errors.append(f"reference file missing: {rel}")
    if weights and abs(sum(weights) - 1.0) > 1e-9:
        errors.append(f"grading weights must sum to 1.0, found {sum(weights):.12g}")
    return errors


def public_task(task: dict[str, Any]) -> dict[str, Any]:
    """Return the only task metadata that an evaluated agent may see."""

    keys = (
        "id",
        "title",
        "prompt",
        "data_description",
        "data_files",
        "required_outputs",
        "setup_notes",
        "timeout_seconds",
    )
    return {key: task[key] for key in keys if key in task}
