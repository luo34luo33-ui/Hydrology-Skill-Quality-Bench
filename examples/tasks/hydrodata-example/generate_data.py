"""Generate deterministic precipitation QC inputs and hidden expected outputs."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
SEED = 20260919


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, lineterminator="\n", float_format="%.6f")
    text = buffer.getvalue()
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise RuntimeError(f"refusing to overwrite non-matching deterministic artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    rng = np.random.default_rng(SEED)
    dates = pd.date_range("2020-01-01", periods=90, freq="D")
    precipitation = rng.gamma(shape=1.4, scale=4.0, size=len(dates))
    precipitation[rng.random(len(dates)) < 0.42] = 0.0
    base = pd.DataFrame({"timestamp": dates.strftime("%Y-%m-%d"), "precipitation_mm": precipitation})

    missing_indices = [8, 27, 44, 61, 79]
    negative_indices = [13, 35, 55, 84]
    duplicate_indices = [5, 31, 70]
    base.loc[negative_indices, "precipitation_mm"] = [-1.2, -0.4, -3.5, -0.8]
    visible = base.drop(index=missing_indices).copy()
    rows: list[dict[str, object]] = []
    duplicate_set = set(duplicate_indices)
    for index, row in visible.iterrows():
        rows.append(row.to_dict())
        if index in duplicate_set:
            duplicate = row.to_dict()
            duplicate["precipitation_mm"] = float(row["precipitation_mm"]) + 7.0
            rows.append(duplicate)
    raw = pd.DataFrame(rows)

    flags = []
    for index in duplicate_indices:
        flags.append({"timestamp": base.loc[index, "timestamp"], "issue": "duplicate_timestamp"})
    for index in negative_indices:
        flags.append({"timestamp": base.loc[index, "timestamp"], "issue": "negative_precipitation"})
    for index in missing_indices:
        flags.append({"timestamp": base.loc[index, "timestamp"], "issue": "missing_timestamp"})
    flags_frame = pd.DataFrame(flags).sort_values(["timestamp", "issue"]).reset_index(drop=True)

    cleaned = base.copy()
    cleaned.loc[negative_indices + missing_indices, "precipitation_mm"] = np.nan
    valid_expected = cleaned.dropna(subset=["precipitation_mm"]).reset_index(drop=True)

    write_csv(ROOT / "data" / "raw_precipitation.csv", raw)
    write_csv(ROOT / "expected" / "qc_flags_expected.csv", flags_frame)
    write_csv(ROOT / "expected" / "cleaned_valid_expected.csv", valid_expected)


if __name__ == "__main__":
    main()

