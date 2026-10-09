"""Loading and validation for the deliberately small HSQB task schema."""

from __future__ import annotations

import json
import math
from pathlib import Path, PurePosixPath
from typing import Any


DOMAINS = {"data-preprocessing", "model-calibration", "model-computation", "results-analysis", "spatial-analysis", "visualization-reporting"}
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
    "figure_contract_check",
    "report_contract_check",
    "composite_contract_check",
    "scientific_invariant",
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
    from harness.filesystem import filesystem_path
    with Path(filesystem_path(path)).open(encoding="utf-8") as handle:
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
    from harness.filesystem import filesystem_path
    task_dir = Path(filesystem_path(task_dir))
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
    contract = task.get('public_contract')
    if contract is not None:
        if not _safe_relative(contract) or not (task_dir / str(contract)).is_file():
            errors.append('public_contract must be a safe existing relative file')
        else:
            try:
                from harness.atomic_contracts import load_contract
                load_contract(task, task_dir)
            except (ValueError, KeyError, OSError):
                errors.append('invalid public contract')
    if not isinstance(secondary, list) or not all(isinstance(item, str) and item for item in secondary):
        errors.append("secondary_skills must be a list of non-empty strings")
    if task.get('task_kind', 'atomic') not in {'atomic','composite'}:
        errors.append('invalid task_kind')
    if task.get('task_kind') == 'composite':
        if task.get('outcome_goal') not in {'deliverable','blocked'}: errors.append('invalid outcome_goal')
        reference=task.get('evaluation_reference')
        if not _safe_relative(reference) or not str(reference).startswith('expected/') or not (task_dir/str(reference)).is_file():
            errors.append('evaluation_reference must exist under expected/')
        core=task.get('core_capabilities',[])
        if not isinstance(core,list) or not all(isinstance(c,str) and c for c in core) or len(set(core))<3: errors.append('composite requires at least three distinct scientific capabilities')
        if _safe_relative(reference) and (task_dir/reference).is_file():
            try:
                hidden=load_json(task_dir/reference);graph=hidden['scientific_graph'];nodes=graph['nodes'];edges=graph['edges']
                ids={n['id'] for n in nodes}
                if len(ids)!=len(nodes) or {n['capability'] for n in nodes}!=set(core):errors.append('scientific graph must account for each distinct core capability')
                if any(not _safe_relative(n['artifact']) for n in nodes):errors.append('unsafe graph artifact')
                if any(e['from'] not in ids or e['to'] not in ids or e['from']==e['to'] for e in edges):errors.append('invalid scientific dependency edge')
                remaining=set(ids)
                while remaining:
                    ready={n for n in remaining if not any(e['to']==n and e['from'] in remaining for e in edges)}
                    if not ready:errors.append('scientific dependency graph contains a cycle');break
                    remaining-=ready
                for gate in hidden['gates']:
                    if not gate.get('criteria'):errors.append('empty scientific gate')
                    for c in gate['criteria']:
                        if c.get('type') not in GRADER_TYPES:errors.append('unknown hidden grader')
                        for _,rel in _reference_paths(c):
                            if not _safe_relative(rel) or not str(rel).startswith('expected/') or not _contained(task_dir,task_dir/rel) or not (task_dir/rel).is_file():errors.append('unsafe or missing hidden grader reference')
                if task.get('interaction_mode')=='none':
                    from harness.composite_grader import get
                    if task.get('task_version')!='composite-unattended-v2' or hidden.get('task_version')!=task['task_version'] or hidden.get('interaction_mode')!='none':errors.append('unattended task version mismatch')
                    if task.get('outcome_goal')!='deliverable' or hidden.get('confirmations'):errors.append('unattended v2 must be deliverable without confirmations')
                    scenario=load_json(task_dir/'data/scenario.json')
                    interfaces=load_json(task_dir/'data/output_interfaces.json')
                    if set(interfaces['outputs'])!=set(task['required_outputs']):errors.append('required outputs missing from public interfaces')
                    for setting in hidden.get('provided_settings',[]):
                        if setting['source'] not in task['data_files'] or not _safe_relative(setting['source']):errors.append('setting source is not visible')
                        value=get(load_json(task_dir/'data'/setting['source']),setting['field'])
                        if not setting.get('bindings') or any(value!=b['expected'] for b in setting['bindings']):errors.append('hidden setting differs from upfront source')
                    for field in ['timezone','time','variables','task_science','organization_mode','evaporation_mapping','forcing_selection','repair_authorized','parameter_change_authorized','synthetic_supplements_authorized','alignment']:
                        if field not in scenario:errors.append('incomplete upfront scenario: '+field)
            except (OSError,ValueError,KeyError,TypeError):errors.append('invalid hidden composite contract')
        budget=task.get('resource_budget',{})
        for key in ('cpus','memory_mb','agent_rounds','tool_calls'):
            if not isinstance(budget.get(key),int) or isinstance(budget.get(key),bool) or budget[key]<=0:errors.append('invalid resource_budget.'+key)
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
        for option in ('required_values', 'artifact_references'):
            mapping = criterion.get(option)
            if mapping is not None:
                if grader_type != 'file_check' or not isinstance(mapping, dict):
                    errors.append(f"{prefix}.{option} requires file_check and an object")
                else:
                    declared_targets = criterion.get('targets') or [criterion.get('target')]
                    for rel, fields in mapping.items():
                        if not _safe_relative(rel) or rel not in declared_targets:
                            errors.append(f"{prefix}.{option}: unsafe or undeclared target")
                        if option == 'required_values' and (not isinstance(fields, dict) or not fields):
                            errors.append(f"{prefix}.{option}: nonempty field map required")
                        if option == 'artifact_references' and (not isinstance(fields, list) or not fields or
                                any(not isinstance(f, str) or not f for f in fields) or len(fields) != len(set(fields))):
                            errors.append(f"{prefix}.{option}: distinct artifact keys required")
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
        "task_kind",
        "task_version",
        "task_revision",
        "interaction_mode",
        "resource_budget",
        "public_contract",
    )
    return {key: task[key] for key in keys if key in task}
