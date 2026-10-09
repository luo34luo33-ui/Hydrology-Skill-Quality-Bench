"""Deterministic calibration evaluator used by HSQB fixtures."""
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
            "time": pd.date_range("2024-01-01" if split == "calibration" else "2025-01-01", periods=12, freq="D", tz="UTC"),
            "observed": observed,
            "simulated": observed + shift,
            "scored": [False, False] + [True] * 10,
        })
        return {**payload, "series": series}


def create_evaluator(problem, problem_dir):
    return Evaluator(problem, problem_dir)
