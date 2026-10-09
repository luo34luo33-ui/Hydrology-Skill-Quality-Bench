"""Deterministic generic and hydrology-specific artifact graders."""

from __future__ import annotations

import json
import hashlib
import math
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from harness.filesystem import filesystem_path

import numpy as np
import pandas as pd
from scipy import stats


EPS = 1e-12


def _clip(value: float) -> float:
    if not math.isfinite(float(value)):
        return 0.0
    return float(min(1.0, max(0.0, value)))


def _native(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _linear_score(value: float, scoring: dict[str, Any] | None, default: float | None = None) -> float:
    if not scoring:
        return _clip(value if default is None else default)
    scored = abs(float(value)) if scoring.get("absolute", False) else float(value)
    zero_at = float(scoring["zero_at"])
    one_at = float(scoring["one_at"])
    if math.isclose(zero_at, one_at):
        return 1.0 if math.isclose(scored, one_at) else 0.0
    return _clip((scored - zero_at) / (one_at - zero_at))


def _workspace_path(workspace: Path, rel: str) -> Path:
    workspace=Path(filesystem_path(workspace))
    path = Path(filesystem_path(workspace / rel)).resolve()
    path.relative_to(workspace.resolve())
    return path


def _reference_path(test_dir: Path, rel: str) -> Path:
    test_dir=Path(filesystem_path(test_dir))
    path = Path(filesystem_path(test_dir / rel)).resolve()
    path.relative_to(test_dir.resolve())
    return path


def _target_name(criterion: dict[str, Any]) -> str:
    target = criterion.get("target", criterion.get("target_file"))
    if not isinstance(target, str):
        raise ValueError("criterion requires target or target_file")
    return target


def _read_table(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path.name)
    suffix = path.suffix.lower()
    if suffix in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t")
    if suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, list):
            return pd.DataFrame(value)
        if isinstance(value, dict):
            return pd.DataFrame([value])
        raise ValueError(f"unsupported JSON table root in {path.name}")
    return pd.read_csv(path)


def _json_field(path: Path, field: str | None) -> Any:
    value: Any = json.loads(path.read_text(encoding="utf-8"))
    if not field:
        return value
    for part in field.split("."):
        if isinstance(value, list) and part.isdigit():
            value = value[int(part)]
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise KeyError(field)
    return value


def _extract_value(path: Path, field: str | None) -> Any:
    if path.suffix.lower() == ".json":
        return _json_field(path, field)
    frame = _read_table(path)
    if field == "row_count":
        return len(frame)
    if field is None:
        if frame.size != 1:
            raise ValueError("field is required for non-scalar table")
        return frame.iloc[0, 0]
    if field not in frame.columns or frame.empty:
        raise KeyError(field)
    row = int(0)
    return frame.iloc[row][field]


def _aligned_series(
    criterion: dict[str, Any], workspace: Path, test_dir: Path
) -> tuple[np.ndarray, np.ndarray, int, int]:
    target = _read_table(_workspace_path(workspace, _target_name(criterion)))
    reference = _read_table(_reference_path(test_dir, criterion["reference"]))
    time_column = criterion.get("time_column", "timestamp")
    target_column = criterion.get("target_column", "simulated")
    reference_column = criterion.get("reference_column", "observed")
    for frame, column, label in (
        (target, time_column, "target time"),
        (reference, time_column, "reference time"),
        (target, target_column, "target value"),
        (reference, reference_column, "reference value"),
    ):
        if column not in frame.columns:
            raise KeyError(f"missing {label} column: {column}")
    if target[time_column].duplicated().any() or reference[time_column].duplicated().any():
        raise ValueError("duplicate timestamps are not gradable")
    target = target[[time_column, target_column]].copy().rename(columns={target_column: "__target_value"})
    reference = reference[[time_column, reference_column]].copy().rename(columns={reference_column: "__reference_value"})
    target[time_column] = pd.to_datetime(target[time_column], errors="coerce", utc=True)
    reference[time_column] = pd.to_datetime(reference[time_column], errors="coerce", utc=True)
    if target[time_column].isna().any() or reference[time_column].isna().any():
        raise ValueError("unparseable timestamps")
    merged = reference.merge(target, on=time_column, how="inner")
    merged["__reference_value"] = pd.to_numeric(merged["__reference_value"], errors="coerce")
    merged["__target_value"] = pd.to_numeric(merged["__target_value"], errors="coerce")
    merged = merged.dropna(subset=["__reference_value", "__target_value"]).sort_values(time_column)
    if merged.empty:
        raise ValueError("no valid aligned values")
    return (
        merged["__reference_value"].to_numpy(dtype=float),
        merged["__target_value"].to_numpy(dtype=float),
        len(merged),
        len(reference),
    )


def hydro_metric(observed: np.ndarray, simulated: np.ndarray, metric: str) -> float:
    observed = np.asarray(observed, dtype=float)
    simulated = np.asarray(simulated, dtype=float)
    if observed.size != simulated.size or observed.size < 2:
        raise ValueError("metric requires at least two paired values")
    residual = simulated - observed
    name = metric.upper()
    if name == "NSE":
        denominator = float(np.sum((observed - np.mean(observed)) ** 2))
        if denominator <= EPS:
            raise ValueError("NSE undefined for constant observations")
        return 1.0 - float(np.sum(residual**2)) / denominator
    if name == "KGE":
        if np.std(observed, ddof=1) <= EPS or abs(float(np.mean(observed))) <= EPS:
            raise ValueError("KGE undefined for constant or zero-mean observations")
        correlation = float(np.corrcoef(observed, simulated)[0, 1])
        if not math.isfinite(correlation):
            raise ValueError("KGE correlation is undefined")
        alpha = float(np.std(simulated, ddof=1) / np.std(observed, ddof=1))
        beta = float(np.mean(simulated) / np.mean(observed))
        return 1.0 - math.sqrt((correlation - 1.0) ** 2 + (alpha - 1.0) ** 2 + (beta - 1.0) ** 2)
    if name == "PBIAS":
        denominator = float(np.sum(observed))
        if abs(denominator) <= EPS:
            raise ValueError("PBIAS undefined for zero observed volume")
        return 100.0 * float(np.sum(residual)) / denominator
    if name == "RMSE":
        return float(np.sqrt(np.mean(residual**2)))
    if name == "MAE":
        return float(np.mean(np.abs(residual)))
    if name in {"R2", "R²"}:
        if np.std(observed) <= EPS or np.std(simulated) <= EPS:
            raise ValueError("R2 undefined for constant series")
        return float(np.corrcoef(observed, simulated)[0, 1] ** 2)
    raise ValueError(f"unsupported hydro metric: {metric}")


def _grade_file_check(criterion: dict[str, Any], workspace: Path, _: Path) -> dict[str, Any]:
    targets = criterion.get("targets") or [_target_name(criterion)]
    required = criterion.get("required_columns", {})
    expected_rows = criterion.get("expected_rows", {})
    passed = 0
    details: list[str] = []
    for rel in targets:
        path = _workspace_path(workspace, rel)
        ok = path.is_file() and path.stat().st_size > 0
        columns = required.get(rel, []) if isinstance(required, dict) else required
        if ok and columns:
            try:
                missing = [column for column in columns if column not in _read_table(path).columns]
                ok = not missing
                if missing:
                    details.append(f"{rel}: missing columns {missing}")
            except Exception as exc:
                ok = False
                details.append(f"{rel}: {exc}")
        row_count = expected_rows.get(rel) if isinstance(expected_rows, dict) else None
        if ok and row_count is not None:
            try:
                actual_rows = len(_read_table(path))
                ok = actual_rows == int(row_count)
                if not ok:
                    details.append(f"{rel}: expected {row_count} rows, found {actual_rows}")
            except Exception as exc:
                ok = False
                details.append(f"{rel}: {exc}")
        if ok:
            try:
                for field, expected in criterion.get("required_values", {}).get(rel, {}).items():
                    if _extract_value(path, field) != expected:
                        ok = False
                        details.append(f"{rel}: invalid interface value for {field}")
                keys = criterion.get("artifact_references", {}).get(rel)
                if keys is not None:
                    integrity = _grade_artifact_reference_check(
                        {"target": rel, "required_keys": keys}, workspace, workspace)
                    if integrity["score"] != 1.0:
                        ok = False
                        details.append(f"{rel}: {integrity['details']}")
            except Exception as exc:
                ok = False
                details.append(f"{rel}: {exc}")
        if ok:
            passed += 1
        elif not any(item.startswith(f"{rel}:") for item in details):
            details.append(f"{rel}: missing or empty")
    score = passed / len(targets) if targets else 0.0
    return {"raw_value": passed, "score": score, "details": "; ".join(details) or "all files valid"}


def _grade_file_absence_check(criterion: dict[str, Any], workspace: Path, _: Path) -> dict[str, Any]:
    targets = criterion.get("targets") or [_target_name(criterion)]
    absent = 0
    present: list[str] = []
    for rel in targets:
        path = _workspace_path(workspace, rel)
        if path.exists():
            present.append(rel)
        else:
            absent += 1
    score = absent / len(targets) if targets else 0.0
    return {
        "raw_value": absent,
        "score": score,
        "details": "all targets absent" if not present else f"unexpectedly present: {present}",
    }


def _grade_column_check(criterion: dict[str, Any], workspace: Path, _: Path) -> dict[str, Any]:
    frame = _read_table(_workspace_path(workspace, _target_name(criterion)))
    required = criterion["required_columns"]
    present = sum(column in frame.columns for column in required)
    return {
        "raw_value": present,
        "score": present / len(required) if required else 1.0,
        "details": f"{present}/{len(required)} required columns present",
    }


def _grade_exact_match(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    actual = _extract_value(_workspace_path(workspace, _target_name(criterion)), criterion.get("field"))
    if "reference" in criterion:
        expected = _extract_value(_reference_path(test_dir, criterion["reference"]), criterion.get("reference_field", criterion.get("field")))
    else:
        expected = criterion["expected"]
    case_sensitive = criterion.get("case_sensitive", True)
    left, right = actual, expected
    if not case_sensitive and isinstance(left, str) and isinstance(right, str):
        left, right = left.casefold(), right.casefold()
    score = 1.0 if left == right else 0.0
    return {"raw_value": _native(actual), "score": score, "details": f"expected {expected!r}"}


def _grade_range_check(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    value = float(_extract_value(_workspace_path(workspace, _target_name(criterion)), criterion.get("field")))
    if "reference" in criterion:
        expected = float(
            _extract_value(
                _reference_path(test_dir, criterion["reference"]),
                criterion.get("reference_field", criterion.get("field")),
            )
        )
        error = abs(value - expected)
        tolerance = float(criterion.get("tolerance", 0.0))
        score = 1.0 if error <= tolerance else _linear_score(error, criterion.get("scoring"), 0.0)
        return {
            "raw_value": value,
            "score": score,
            "details": f"expected={expected}, absolute_error={error}",
        }
    bounds = criterion.get("range", [criterion.get("min"), criterion.get("max")])
    low, high = float(bounds[0]), float(bounds[1])
    score = 1.0 if low <= value <= high else 0.0
    if score == 0.0 and "scoring" in criterion:
        distance = low - value if value < low else value - high
        score = _linear_score(distance, criterion["scoring"])
    return {"raw_value": value, "score": score, "details": f"accepted range [{low}, {high}]"}


def _row_keys(frame: pd.DataFrame, columns: list[str]) -> set[tuple[str, ...]]:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise KeyError(f"missing set columns: {missing}")
    return {tuple(str(value) for value in row) for row in frame[columns].itertuples(index=False, name=None)}


def _grade_set_overlap(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    target = _read_table(_workspace_path(workspace, _target_name(criterion)))
    reference = _read_table(_reference_path(test_dir, criterion["reference"]))
    target_columns = criterion.get("target_columns", criterion.get("columns"))
    reference_columns = criterion.get("reference_columns", target_columns)
    predicted = _row_keys(target, target_columns)
    truth = _row_keys(reference, reference_columns)
    overlap = len(predicted & truth)
    metric = criterion.get("metric", "f1").lower()
    if metric == "jaccard":
        denominator = len(predicted | truth)
        value = overlap / denominator if denominator else 1.0
    elif metric == "f1":
        denominator = len(predicted) + len(truth)
        value = 2 * overlap / denominator if denominator else 1.0
    else:
        raise ValueError(f"unsupported overlap metric: {metric}")
    return {"raw_value": value, "score": _clip(value), "details": f"{overlap} shared rows"}


def _grade_numeric_correlation(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    observed, simulated, count, _ = _aligned_series(criterion, workspace, test_dir)
    if np.std(observed) <= EPS or np.std(simulated) <= EPS:
        raise ValueError("correlation undefined for constant series")
    method = criterion.get("metric", "pearson").lower()
    if method == "pearson":
        value = float(stats.pearsonr(observed, simulated).statistic)
    elif method == "spearman":
        value = float(stats.spearmanr(observed, simulated).statistic)
    else:
        raise ValueError(f"unsupported correlation metric: {method}")
    return {"raw_value": value, "score": _linear_score(value, criterion.get("scoring"), value), "details": f"{count} aligned values"}


def _grade_code_executes(criterion: dict[str, Any], workspace: Path, _: Path) -> dict[str, Any]:
    script_name = criterion.get("script")
    if not script_name:
        script_name = _target_name(criterion)
    script = _workspace_path(workspace, script_name)
    command = [sys.executable, str(script), *[str(arg) for arg in criterion.get("args", [])]]
    completed = subprocess.run(
        command,
        cwd=workspace,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=int(criterion.get("timeout_seconds", 30)),
        check=False,
    )
    return {
        "raw_value": completed.returncode,
        "score": 1.0 if completed.returncode == 0 else 0.0,
        "details": completed.stderr[-500:] if completed.returncode else "script completed",
    }


def _grade_hydro_metric(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    observed, simulated, count, _ = _aligned_series(criterion, workspace, test_dir)
    value = hydro_metric(observed, simulated, criterion["metric"])
    score = _linear_score(value, criterion.get("scoring"), value)
    return {"raw_value": _native(value), "score": score, "details": f"{count} aligned values"}


def _grade_timeseries_match(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    observed, simulated, count, reference_count = _aligned_series(criterion, workspace, test_dir)
    atol = float(criterion.get("atol", 0.0))
    rtol = float(criterion.get("rtol", 0.0))
    matches = np.abs(simulated - observed) <= atol + rtol * np.abs(observed)
    fraction = float(np.mean(matches))
    coverage = count / reference_count if reference_count else 0.0
    score = fraction * coverage
    return {"raw_value": fraction, "score": score, "details": f"coverage={coverage:.6f}"}


def _booleanish(series: pd.Series) -> bool:
    values = series.dropna().tolist()
    if not values:
        return False
    return all(isinstance(value, (bool, np.bool_)) or str(value) in {"True", "False"} for value in values)


def _grade_table_match(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    target = _read_table(_workspace_path(workspace, _target_name(criterion)))
    reference = _read_table(_reference_path(test_dir, criterion["reference"]))
    columns = criterion.get("columns", list(reference.columns))
    if not isinstance(columns, list) or not columns:
        raise ValueError("table_match columns must be a non-empty list")
    missing_target = [column for column in columns if column not in target.columns]
    missing_reference = [column for column in columns if column not in reference.columns]
    if missing_target or missing_reference:
        raise KeyError(f"missing target columns={missing_target}; missing reference columns={missing_reference}")

    datetime_columns = set(criterion.get("datetime_columns", []))
    atol = float(criterion.get("atol", 0.0))
    rtol = float(criterion.get("rtol", 0.0))
    compared_rows = min(len(target), len(reference))
    matches = 0
    mismatches: dict[str, int] = {}

    for column in columns:
        left = target[column].iloc[:compared_rows].reset_index(drop=True)
        right = reference[column].iloc[:compared_rows].reset_index(drop=True)
        if column in datetime_columns:
            left_values = pd.to_datetime(left, errors="coerce", utc=True)
            right_values = pd.to_datetime(right, errors="coerce", utc=True)
            valid_left = ~left.isna()
            valid_right = ~right.isna()
            equal = (left_values == right_values) | (~valid_left & ~valid_right)
            equal &= ~(valid_left & left_values.isna())
            equal &= ~(valid_right & right_values.isna())
        elif _booleanish(right):
            equal = pd.Series(
                [
                    (pd.isna(a) and pd.isna(b)) or (not pd.isna(a) and not pd.isna(b) and str(a) == str(b))
                    for a, b in zip(left, right, strict=True)
                ]
            )
        else:
            left_numeric = pd.to_numeric(left, errors="coerce")
            right_numeric = pd.to_numeric(right, errors="coerce")
            left_bad = left.notna() & left_numeric.isna()
            right_bad = right.notna() & right_numeric.isna()
            numeric = not left_bad.any() and not right_bad.any() and (left.notna().any() or right.notna().any())
            if numeric:
                equal = pd.Series(
                    np.isclose(
                        left_numeric.to_numpy(dtype=float),
                        right_numeric.to_numpy(dtype=float),
                        atol=atol,
                        rtol=rtol,
                        equal_nan=True,
                    )
                )
            else:
                equal = pd.Series(
                    [
                        (pd.isna(a) and pd.isna(b)) or (not pd.isna(a) and not pd.isna(b) and str(a) == str(b))
                        for a, b in zip(left, right, strict=True)
                    ]
                )
        column_matches = int(equal.sum())
        matches += column_matches
        if column_matches != compared_rows:
            mismatches[column] = compared_rows - column_matches

    total_cells = max(len(target), len(reference)) * len(columns)
    score = matches / total_cells if total_cells else 1.0
    details = f"matched_cells={matches}/{total_cells}; target_rows={len(target)}; reference_rows={len(reference)}"
    if mismatches:
        details += f"; mismatches={mismatches}"
    return {"raw_value": matches, "score": score, "details": details}


def _grade_peak_check(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    if criterion.get("field"):
        actual = float(_extract_value(_workspace_path(workspace, _target_name(criterion)), criterion["field"]))
        expected = float(_extract_value(_reference_path(test_dir, criterion["reference"]), criterion.get("reference_field", criterion["field"])))
        error = abs(actual - expected)
        score = 1.0 if error <= float(criterion.get("tolerance", 0.0)) else _linear_score(error, criterion.get("scoring"), 0.0)
        return {"raw_value": actual, "score": score, "details": f"expected={expected}, absolute_error={error}"}
    observed, simulated, _, _ = _aligned_series(criterion, workspace, test_dir)
    measure = criterion.get("measure", "lag_steps")
    if measure == "lag_steps":
        value = int(np.argmax(simulated) - np.argmax(observed))
    elif measure == "relative_magnitude_error":
        peak = float(np.max(observed))
        if abs(peak) <= EPS:
            raise ValueError("peak magnitude error undefined for zero peak")
        value = abs(float(np.max(simulated)) - peak) / abs(peak)
    else:
        raise ValueError(f"unsupported peak measure: {measure}")
    scored_value = abs(value) if criterion.get("absolute", True) else value
    return {"raw_value": value, "score": _linear_score(scored_value, criterion.get("scoring"), 0.0), "details": measure}


def _grade_volume_check(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    observed, simulated, count, _ = _aligned_series(criterion, workspace, test_dir)
    observed_volume = float(np.sum(observed))
    if abs(observed_volume) <= EPS:
        raise ValueError("volume error undefined for zero observed volume")
    error = abs(float(np.sum(simulated)) - observed_volume) / abs(observed_volume)
    return {"raw_value": error, "score": _linear_score(error, criterion.get("scoring"), 1.0 - error), "details": f"{count} aligned values"}


def _grade_water_balance_check(criterion: dict[str, Any], workspace: Path, _: Path) -> dict[str, Any]:
    frame = _read_table(_workspace_path(workspace, _target_name(criterion)))
    columns = criterion.get("columns", {})
    precipitation = float(pd.to_numeric(frame[columns.get("precipitation", "precipitation")], errors="coerce").sum())
    discharge = float(pd.to_numeric(frame[columns.get("discharge", "discharge")], errors="coerce").sum())
    evapotranspiration = float(pd.to_numeric(frame[columns.get("evapotranspiration", "evapotranspiration")], errors="coerce").sum())
    storage_column = columns.get("storage_change")
    storage_change = float(pd.to_numeric(frame[storage_column], errors="coerce").sum()) if storage_column else float(criterion.get("storage_change", 0.0))
    closure = abs(precipitation - discharge - evapotranspiration - storage_change) / max(abs(precipitation), EPS)
    return {"raw_value": closure, "score": _linear_score(closure, criterion.get("scoring"), 1.0 - closure), "details": "relative water-balance closure error"}


def _grade_parameter_range(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    parameters = _json_field(_workspace_path(workspace, _target_name(criterion)), criterion.get("field"))
    ranges_path = _reference_path(test_dir, criterion["ranges_file"])
    ranges = _json_field(ranges_path, criterion.get("ranges_field"))
    if "parameters" in ranges and isinstance(ranges["parameters"], dict):
        ranges = ranges["parameters"]
    if not isinstance(parameters, dict) or not isinstance(ranges, dict) or not ranges:
        raise ValueError("parameters and ranges must be non-empty JSON objects")
    valid = 0
    checked = 0
    for name, bounds in ranges.items():
        checked += 1
        if name not in parameters:
            continue
        if isinstance(bounds, dict):
            low, high = bounds["min"], bounds["max"]
        else:
            low, high = bounds
        try:
            value = float(parameters[name])
            valid += int(float(low) <= value <= float(high))
        except (TypeError, ValueError):
            continue
    return {"raw_value": valid, "score": valid / checked, "details": f"{valid}/{checked} parameters in range"}


def _grade_raster_match(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    import rasterio

    target_path = _workspace_path(workspace, _target_name(criterion))
    reference_path = _reference_path(test_dir, criterion["reference"])
    atol = float(criterion.get("atol", 0.0))
    rtol = float(criterion.get("rtol", 0.0))
    categorical = bool(criterion.get("categorical", False))
    checks: list[bool] = []
    details: list[str] = []
    with rasterio.open(target_path) as target, rasterio.open(reference_path) as reference:
        metadata = {
            "count": target.count == reference.count,
            "shape": (target.height, target.width) == (reference.height, reference.width),
            "crs": target.crs == reference.crs,
            "transform": target.transform.almost_equals(reference.transform),
            "nodata": (
                target.nodata == reference.nodata
                or (
                    target.nodata is not None and reference.nodata is not None
                    and math.isclose(float(target.nodata), float(reference.nodata), rel_tol=0.0, abs_tol=atol)
                )
            ),
        }
        for name, passed in metadata.items():
            checks.append(passed)
            if not passed:
                details.append(f"{name} differs")
        if metadata["count"] and metadata["shape"]:
            target_values = target.read(masked=True)
            reference_values = reference.read(masked=True)
            masks_equal = np.array_equal(np.ma.getmaskarray(target_values), np.ma.getmaskarray(reference_values))
            checks.append(masks_equal)
            if not masks_equal:
                details.append("valid-data mask differs")
            common = ~(np.ma.getmaskarray(target_values) | np.ma.getmaskarray(reference_values))
            if common.any():
                left = np.asarray(target_values.data)[common]
                right = np.asarray(reference_values.data)[common]
                values_equal = bool(np.array_equal(left, right)) if categorical else bool(
                    np.allclose(left, right, atol=atol, rtol=rtol, equal_nan=True)
                )
            else:
                values_equal = True
            checks.append(values_equal)
            if not values_equal:
                details.append("pixel values differ")
    score = sum(checks) / len(checks) if checks else 0.0
    return {"raw_value": sum(checks), "score": score, "details": "; ".join(details) or "raster semantics match"}


def _grade_vector_match(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    import geopandas as gpd
    from shapely import normalize

    target_path = _workspace_path(workspace, _target_name(criterion))
    reference_path = _reference_path(test_dir, criterion["reference"])
    target = gpd.read_file(target_path, layer=criterion.get("target_layer", criterion.get("layer")))
    reference = gpd.read_file(reference_path, layer=criterion.get("reference_layer", criterion.get("layer")))
    keys = criterion.get("key_columns", [])
    columns = criterion.get("columns", [column for column in reference.columns if column != reference.geometry.name])
    missing = [column for column in [*keys, *columns] if column not in target.columns or column not in reference.columns]
    if missing:
        raise KeyError(f"missing vector columns: {sorted(set(missing))}")
    if keys:
        target = target.sort_values(keys, kind="stable").reset_index(drop=True)
        reference = reference.sort_values(keys, kind="stable").reset_index(drop=True)
    else:
        target = target.assign(__wkb=target.geometry.map(lambda geom: normalize(geom).wkb_hex if geom is not None else "")).sort_values("__wkb").drop(columns="__wkb").reset_index(drop=True)
        reference = reference.assign(__wkb=reference.geometry.map(lambda geom: normalize(geom).wkb_hex if geom is not None else "")).sort_values("__wkb").drop(columns="__wkb").reset_index(drop=True)
    checks = [target.crs == reference.crs, len(target) == len(reference)]
    details: list[str] = []
    if not checks[0]:
        details.append("CRS differs")
    if not checks[1]:
        details.append(f"feature count differs: {len(target)} != {len(reference)}")
    if len(target) == len(reference):
        table_criterion = {
            "type": "table_match", "target": "unused", "reference": "unused",
            "columns": columns, "atol": criterion.get("atol", 0.0), "rtol": criterion.get("rtol", 0.0),
        }
        # Reuse table semantics without temporary files.
        compared = 0
        total = max(1, len(target) * max(1, len(columns)))
        for column in columns:
            left = target[column].reset_index(drop=True)
            right = reference[column].reset_index(drop=True)
            left_numeric = pd.to_numeric(left, errors="coerce")
            right_numeric = pd.to_numeric(right, errors="coerce")
            numeric = not (left.notna() & left_numeric.isna()).any() and not (right.notna() & right_numeric.isna()).any()
            if numeric:
                compared += int(np.isclose(left_numeric, right_numeric, atol=float(table_criterion["atol"]), rtol=float(table_criterion["rtol"]), equal_nan=True).sum())
            else:
                compared += sum((pd.isna(a) and pd.isna(b)) or str(a) == str(b) for a, b in zip(left, right, strict=True))
        attributes_ok = compared == total
        checks.append(attributes_ok)
        if not attributes_ok:
            details.append(f"attribute cells matched {compared}/{total}")
        tolerance = float(criterion.get("geometry_tolerance", 0.0))
        geometry_ok = all(
            (a is None and b is None)
            or (a is not None and b is not None and normalize(a).equals_exact(normalize(b), tolerance))
            for a, b in zip(target.geometry, reference.geometry, strict=True)
        )
        checks.append(geometry_ok)
        if not geometry_ok:
            details.append("geometry differs")
    return {"raw_value": sum(checks), "score": sum(checks) / len(checks), "details": "; ".join(details) or "vector semantics match"}


def _grade_artifact_reference_check(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    result_path = _workspace_path(workspace, _target_name(criterion))
    document = json.loads(result_path.read_text(encoding="utf-8-sig"))
    artifacts = document.get(criterion.get("field", "artifacts"), {})
    required = criterion.get("required_keys", [])
    if not isinstance(artifacts, dict):
        raise ValueError("artifact field must be an object")
    checked = 0
    passed = 0
    failures: list[str] = []
    for key in required:
        checked += 1
        reference = artifacts.get(key)
        if not isinstance(reference, dict) or not isinstance(reference.get("path"), str):
            failures.append(f"{key}: missing reference")
            continue
        from harness.source_references import verify_reference, SourceReferenceError
        try:
            path = verify_reference(workspace,result_path.parent,reference,test_dir)
        except SourceReferenceError as exc:
            raise SourceReferenceError(exc.code,f'{key}: {exc}') from exc
        if not path.is_file() or path.stat().st_size == 0:
            failures.append(f"{key}: missing or empty")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != reference.get("sha256"):
            failures.append(f"{key}: sha256 mismatch")
            continue
        passed += 1
    score = passed / checked if checked else 1.0
    return {"raw_value": passed, "score": score, "details": "; ".join(failures) or "artifact references valid"}


def _contract_stable(value: Any) -> Any:
    """Remove run-location/prose metadata while retaining scientific content."""
    if isinstance(value, dict):
        return {k: _contract_stable(v) for k, v in value.items()
                if k not in {"provenance", "sha256", "package_fingerprint", "author", "reviewer", "rationale", "text", "message", "path", "result_path", "result", "source_results", "sources"} and not k.endswith("_path")}
    if isinstance(value, list):
        return [_contract_stable(v) for v in value]
    if isinstance(value, str):
        import re
        if Path(value).is_absolute(): return Path(value).name
        return re.sub(r"ev-[0-9a-f]{20}", "ev-location-id", value)
    return value


def _contract_equal(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and _contract_equal(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(_contract_equal(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            return math.isclose(float(actual), float(expected), rel_tol=1e-6, abs_tol=1e-6)
        except (ValueError, TypeError):
            return False
    return actual == expected


def _grade_figure_contract(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    import xml.etree.ElementTree as ET
    from PIL import Image
    reference = json.loads(_reference_path(test_dir, criterion["reference"]).read_text(encoding="utf-8"))
    checks: list[bool] = []
    for fig in reference["figures"]:
        try:
            png = _workspace_path(workspace, fig["png"])
            with Image.open(png) as img:
                img.load()
                checks += [list(img.size) == fig["size"], float(np.asarray(img.convert("RGB"), dtype=float).std()) > 5]
            meta = json.loads(_workspace_path(workspace, fig["metadata"]).read_text(encoding="utf-8"))
            checks.append(_contract_equal(_contract_stable(meta), fig["metadata_contract"]))
            size = meta.get("pixel_size", {})
            if size:
                checks.append([size.get("width"), size.get("height")] == fig["size"])
            svg = ET.parse(_workspace_path(workspace, fig["svg"])).getroot()
            checks.append(svg.tag.endswith("svg"))
            graphic_tags = {"path", "image", "polyline", "polygon", "circle", "rect"}
            graphics = [e for e in svg.iter() if e.tag.rsplit("}", 1)[-1] in graphic_tags]
            checks.append(len(graphics) >= fig.get("minimum_graphics", 10))
            svg_text = _workspace_path(workspace, fig["svg"]).read_text(encoding="utf-8")
            checks.append(all(token in svg_text for token in fig.get("svg_tokens", [])))
            geometry = []
            for element in svg.iter():
                if element.tag.endswith("g") and element.get("id", "").startswith(("line2d_", "LineCollection_", "PathCollection_", "patch_")):
                    geometry.extend(e.get("d") for e in element.iter() if e.tag.endswith("path") and e.get("d"))
            for path_geometry in fig.get("geometry", []):
                checks.append(path_geometry in geometry)
        except (OSError, ValueError, KeyError, ET.ParseError):
            checks.append(False)
    score = sum(checks) / len(checks) if checks else 0.0
    return {"raw_value": score, "score": score, "details": f"{sum(checks)}/{len(checks)} figure contract checks"}


def _grade_report_contract(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    reference = json.loads(_reference_path(test_dir, criterion["reference"]).read_text(encoding="utf-8"))
    checks: list[bool] = []
    for rel, expected in reference.get("files", {}).items():
        try:
            doc = json.loads(_workspace_path(workspace, rel).read_text(encoding="utf-8"))
            actual = _contract_stable(doc)
            if not isinstance(expected, dict):
                checks.append(_contract_equal(actual, expected))
                continue
            if rel.endswith("report.json"):
                actual["sections"] = [{k: v for k, v in s.items() if k != "paragraphs"} for s in actual.get("sections", [])]
            for key, value in expected.items():
                if key == "error_reason_contains":
                    checks.append(value in str(doc.get("message", "")))
                elif key == "narrative_required":
                    if value:
                        checks.append(doc.get("narrative_provenance", {}).get("completed") is True)
                        evidence = {e["id"] for e in doc.get("evidence", [])}
                        evidence_values = {e["id"]: e.get("value") for e in doc.get("evidence", [])}
                        checks.append(len(evidence_values) == len(doc.get("evidence", [])))
                        all_paragraphs = [p for s in doc["sections"] for p in s.get("paragraphs", [])]
                        checks.append(len({p["id"] for p in all_paragraphs}) == len(all_paragraphs))
                        for sid in ("overview", "evaluation", "discussion", "limitations"):
                            section = next((s for s in doc["sections"] if s["id"] == sid), {})
                            paragraphs = section.get("paragraphs", [])
                            checks.append(bool(paragraphs))
                            for paragraph in paragraphs:
                                checks += [bool(paragraph.get("text", "").strip()), bool(paragraph.get("evidence_ids")), set(paragraph.get("evidence_ids", [])) <= evidence,
                                           paragraph.get("kind") in {"fact", "inference", "recommendation", "pending"}]
                                for binding in paragraph.get("numeric_bindings", []):
                                    eid=binding.get("evidence_id"); rendered=str(binding.get("text", "")); original=evidence_values.get(eid)
                                    allowed={str(original)}
                                    try:
                                        number=float(original)
                                        allowed.update(f"{number:.{precision}f}" for precision in (0,1,3,6))
                                    except (ValueError,TypeError): pass
                                    checks.append(eid in paragraph.get("evidence_ids", []) and rendered in allowed and rendered in paragraph.get("text", ""))
                        for diag in doc.get("analysis", {}).get("details", {}).get("diagnostics", []):
                            if not diag.get("available"): continue
                            paragraphs = [p for s in doc["sections"] for p in s.get("paragraphs", [])]
                            matched = [p for p in paragraphs if p.get("diagnosis") == {k: diag[k] for k in ("run", "evaluation", "event_id")}]
                            checks.append(bool(matched) and all(p.get("kind") == "inference" and p.get("hypotheses") and all(all(h.get(k) for k in ("candidate", "support", "limitations", "validation")) for h in p["hypotheses"]) for p in matched))
                else:
                    checks.append(key in actual and _contract_equal(actual[key], value))
        except (OSError, ValueError, KeyError, TypeError):
            checks.append(False)
    if "semantic_verdicts" in reference:
        try:
            semantic = json.loads(_workspace_path(workspace, "semantic.json").read_text(encoding="utf-8"))
            initial = json.loads(_workspace_path(workspace, "review-initial/review.json").read_text(encoding="utf-8"))
            paragraphs = semantic["paragraphs"]
            checks += [semantic["package_fingerprint"] == initial["package_fingerprint"], len({p["id"] for p in paragraphs}) == len(paragraphs),
                       {p["id"]: p["verdict"] for p in paragraphs} == reference["semantic_verdicts"], all(bool(p.get("rationale", "").strip()) for p in paragraphs)]
            report = json.loads(_workspace_path(workspace, "report/report.json").read_text(encoding="utf-8")) if (workspace/"report/report.json").exists() else None
            # Review-task reports are visible staged inputs, so they are present
            # in native verification workspaces and real Agent workspaces.
            if report:
                expected_ids = {p["id"]: p.get("evidence_ids", []) for s in report["sections"] for p in s["paragraphs"]}
                checks.append(_contract_stable({p["id"]: p.get("evidence_ids", []) for p in paragraphs}) == _contract_stable(expected_ids))
        except (OSError, ValueError, KeyError, TypeError): checks.append(False)
    for rel, lines in reference.get("markdown", {}).items():
        try:
            actual_lines = _workspace_path(workspace, rel).read_text(encoding="utf-8").splitlines()
            checks.extend(line in actual_lines for line in lines)
        except OSError: checks.append(False)
    if reference.get("kind") == "bma" and (workspace/"fit/bma_model.json").exists():
        try:
            model = json.loads((workspace/"fit/bma_model.json").read_text(encoding="utf-8"))
            weights = np.asarray(model["weights"], dtype=float); theta = np.asarray(model["theta"], dtype=float)
            checks += [np.isfinite(weights).all(), np.isfinite(theta).all(), bool((weights >= 0).all()), np.isclose(weights.sum(), 1), theta.shape == (len(weights), 3), bool((theta[:, 1] >= 0).all()), bool((theta[:, 2] > 0).all()), model["scale_m3_s"] > 0]
        except (OSError, ValueError, KeyError, TypeError, IndexError): checks.append(False)
    if reference.get("kind") == "bma" and (workspace/"forecast/ensemble_discharge.csv").exists():
        try:
            from scipy.stats import norm
            components = pd.read_csv(workspace/"forecast/component_predictions.csv")
            forecast = pd.read_csv(workspace/"forecast/ensemble_discharge.csv")
            checks.append(bool(len(forecast)))
            checks.append(bool(np.isfinite(forecast.select_dtypes(include="number")).all().all()))
            checks.append(bool((forecast.filter(regex="p[0-9]+_m3_s").diff(axis=1).iloc[:, 1:] >= 0).all().all()))
            # Column names follow the native BMA component contract.
            mu = components["corrected_center_m3_s"].to_numpy(); sigma = components["sigma_m3_s"].to_numpy(); weights = components["weight"].to_numpy()
            key = [k for k in ("event_id", "time") if k in forecast]
            components = components.assign(_mean=weights*(sigma*norm.pdf(mu/sigma)+mu*norm.cdf(mu/sigma)), _zero=weights*norm.cdf(-mu/sigma))
            summed = components.groupby(key, sort=False)[["_mean", "_zero", "weight"]].sum().reset_index()
            joined = forecast.merge(summed, on=key, validate="one_to_one")
            checks += [len(joined)==len(forecast), np.allclose(joined["ensemble_mean_m3_s"], joined["_mean"], rtol=1e-6), np.allclose(joined["probability_zero"],joined["_zero"],rtol=1e-6), np.allclose(joined["weight"],1), bool((sigma>0).all()), bool((weights>=0).all())]
            model = json.loads((workspace/"fit/bma_model.json").read_text(encoding="utf-8"))
            checks.append(bool((pd.to_datetime(forecast["time"], utc=True) > pd.Timestamp(model["training_end"])).all()))
            if "event_id" in forecast:
                checks.append(not (set(forecast.event_id) & set(model["training_events"])))
            components_by_key = {k if isinstance(k, tuple) else (k,): v for k, v in components.groupby(key, sort=False)}
            quantile_checks=[]
            for _, row in forecast.iterrows():
                component = components_by_key[tuple(row[k] for k in key)]
                center=component.corrected_center_m3_s.to_numpy(); spread=component.sigma_m3_s.to_numpy(); w=component.weight.to_numpy()
                for column in forecast.filter(regex="p[0-9]+_m3_s"):
                    probability = float(column[1:column.index("_")]) / 100
                    q = row[column]; cdf=float(np.sum(w*norm.cdf((q-center)/spread)))
                    quantile_checks.append(q>=0 and (cdf>=probability-1e-6 if q==0 else abs(cdf-probability)<1e-6))
            checks.append(all(quantile_checks))
        except (OSError, ValueError, KeyError, TypeError): checks.append(False)
    score = sum(checks) / len(checks) if checks else 0.0
    return {"raw_value": score, "score": score, "details": f"{sum(checks)}/{len(checks)} evidence contract checks"}


from harness.composite_grader import criterion as _grade_composite_contract
from harness.scientific_checks import grade as _grade_scientific_invariant

GRADERS = {
    "file_check": _grade_file_check,
    "file_absence_check": _grade_file_absence_check,
    "column_check": _grade_column_check,
    "exact_match": _grade_exact_match,
    "range_check": _grade_range_check,
    "set_overlap": _grade_set_overlap,
    "numeric_correlation": _grade_numeric_correlation,
    "code_executes": _grade_code_executes,
    "hydro_metric": _grade_hydro_metric,
    "timeseries_match": _grade_timeseries_match,
    "table_match": _grade_table_match,
    "peak_check": _grade_peak_check,
    "volume_check": _grade_volume_check,
    "water_balance_check": _grade_water_balance_check,
    "parameter_range": _grade_parameter_range,
    "raster_match": _grade_raster_match,
    "vector_match": _grade_vector_match,
    "artifact_reference_check": _grade_artifact_reference_check,
    "figure_contract_check": _grade_figure_contract,
    "report_contract_check": _grade_report_contract,
    "composite_contract_check": _grade_composite_contract,
    "scientific_invariant": _grade_scientific_invariant,
}


def grade_criterion(criterion: dict[str, Any], workspace: Path, test_dir: Path) -> dict[str, Any]:
    try:
        workspace=Path(filesystem_path(workspace));test_dir=Path(filesystem_path(test_dir))
        result = GRADERS[criterion["type"]](criterion, workspace, test_dir)
        result["score"] = _clip(float(result.get("score", 0.0)))
        result["raw_value"] = _native(result.get("raw_value"))
        return result
    except Exception as exc:
        from harness.source_references import SourceReferenceError
        if isinstance(exc,SourceReferenceError):
            return {"raw_value":None,"score":0.0,"details":f"source reference error: {exc}","diagnostic_type":exc.code}
        if isinstance(exc,FileNotFoundError):
            return {"raw_value":None,"score":0.0,"details":f"missing evidence: {exc}","diagnostic_type":"missing_evidence"}
        return {"raw_value": None, "score": 0.0, "details": f"grading error: {exc}"}


def detect_attempted(task: dict[str, Any], workspace: str | Path) -> bool:
    root = Path(filesystem_path(workspace))
    return any(
        (root / rel).is_file() and (root / rel).stat().st_size > 0
        for rel in task.get("required_outputs", [])
    )


def grade_task(task: dict[str, Any], workspace: str | Path, test_dir: str | Path, *, audit_events: list | None = None) -> dict[str, Any]:
    workspace_path = Path(filesystem_path(workspace))
    test_path = Path(filesystem_path(test_dir))
    criteria: dict[str, Any] = {}
    score = 0.0
    for criterion in task["grading"]:
        result = grade_criterion(criterion, workspace_path, test_path)
        criteria[criterion["name"]] = result
        score += float(criterion["weight"]) * result["score"]
    result = {
        "test_id": task["id"],
        "domain": task["domain"],
        "difficulty": task["difficulty"],
        "primary_skill": task["primary_skill"],
        "attempted": detect_attempted(task, workspace_path),
        "score": _clip(score),
        "criteria": criteria,
    }
    if task.get('task_kind') == 'composite':
        from harness.composite_grader import evaluate
        result.update(evaluate(task,workspace_path,test_path,audit_events))
    return result
