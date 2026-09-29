"""Generate a hydrograph pair with a deterministic two-day timing delay."""

from __future__ import annotations

import io
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
SEED = 20260919


def write_text(path: Path, text: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise RuntimeError(f"refusing to overwrite non-matching deterministic artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, lineterminator="\n", float_format="%.8f")
    write_text(path, buffer.getvalue())


def metrics(observed: np.ndarray, simulated: np.ndarray) -> dict[str, float]:
    residual = simulated - observed
    correlation = float(np.corrcoef(observed, simulated)[0, 1])
    alpha = float(np.std(simulated, ddof=1) / np.std(observed, ddof=1))
    beta = float(np.mean(simulated) / np.mean(observed))
    return {
        "NSE": 1.0 - float(np.sum(residual**2) / np.sum((observed - np.mean(observed)) ** 2)),
        "KGE": 1.0 - math.sqrt((correlation - 1.0) ** 2 + (alpha - 1.0) ** 2 + (beta - 1.0) ** 2),
        "PBIAS": 100.0 * float(np.sum(residual) / np.sum(observed)),
        "RMSE": float(np.sqrt(np.mean(residual**2))),
        "MAE": float(np.mean(np.abs(residual))),
        "R2": correlation**2,
        "peak_timing_error_steps": int(np.argmax(simulated) - np.argmax(observed)),
    }


def main() -> None:
    rng = np.random.default_rng(SEED)
    days = 140
    x = np.arange(days)
    observed = 1.8 + 0.15 * np.sin(x / 8.0)
    for center, height, width in ((24, 7.0, 3.5), (61, 12.0, 4.0), (103, 22.0, 3.0)):
        observed += height * np.exp(-0.5 * ((x - center) / width) ** 2)
    observed += rng.normal(0.0, 0.015, days)
    simulated = np.empty_like(observed)
    simulated[:2] = observed[0]
    simulated[2:] = observed[:-2]
    timestamps = pd.date_range("2021-01-01", periods=days, freq="D").strftime("%Y-%m-%d")
    write_csv(ROOT / "data" / "observed.csv", pd.DataFrame({"timestamp": timestamps, "observed": observed}))
    write_csv(ROOT / "data" / "simulated.csv", pd.DataFrame({"timestamp": timestamps, "simulated": simulated}))
    expected_metrics = metrics(observed, simulated)
    write_text(ROOT / "expected" / "metrics_expected.json", json.dumps(expected_metrics, indent=2) + "\n")
    write_text(
        ROOT / "expected" / "diagnosis_expected.json",
        json.dumps({"primary_category": "peak_timing_delay"}, indent=2) + "\n",
    )


if __name__ == "__main__":
    main()

