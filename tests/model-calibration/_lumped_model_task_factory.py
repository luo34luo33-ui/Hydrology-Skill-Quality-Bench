"""Deterministic fixtures for the lumped DHF / HBV / Tank forward-simulation benchmark tasks.

Covers three capabilities of the model-calibration domain:

- ``hydromodel-dhf-001..003``  -> run-lumped-dhf-model
- ``hydromodel-hbv-001..003``  -> run-lumped-hbv-model
- ``hydromodel-tank-001..003`` -> run-lumped-tank-model
"""

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
FOLDER = "hydrological-modeling"

CAPABILITIES: dict[str, dict[str, Any]] = {
    "dhf": {
        "skill": "hydrological-modeling/run-lumped-dhf-model",
        "script": "run_lumped_dhf.py",
        "output": "dhf-run",
        "table": "lumped_dhf_runoff.csv",
        "columns": [
            "time", "is_warmup", "P", "PET", "E", "PE", "PC", "Y0", "EU", "EL", "RR", "Y", "YU",
            "YL", "RUNOFF", "QS", "QL", "Q", "SA", "UA", "YA", "EB",
        ],
    },
    "hbv": {
        "skill": "hydrological-modeling/run-lumped-hbv-model",
        "script": "run_lumped_hbv.py",
        "output": "hbv-run",
        "table": "lumped_hbv_runoff.csv",
        "columns": [
            "time", "is_warmup", "P", "PET", "EA", "SM", "RECHARGE", "SUZ", "SLZ", "Q0", "Q1", "Q2", "Q",
        ],
    },
    "tank": {
        "skill": "hydrological-modeling/run-lumped-tank-model",
        "script": "run_lumped_tank.py",
        "output": "tank-run",
        "table": "lumped_tank_runoff.csv",
        "columns": [
            "time", "is_warmup", "P", "EVAP", "NET", "S0", "S1", "S2", "S3",
            "QS0_LO", "QS0_UO", "QS1", "QS2", "QS3", "QB0", "QB1", "QB2", "Q",
        ],
    },
    "gr4j": {
        "skill": "hydrological-modeling/run-lumped-gr4j-model",
        "script": "run_lumped_gr4j.py",
        "output": "gr4j-run",
        "table": "lumped_gr4j_runoff.csv",
        "timestep": 24,
        "columns": [
            "time", "is_warmup", "P", "PET", "EA", "PS", "PERC", "PR", "UH1_IN", "UH2_IN", "GW",
            "QR", "QD", "Q_MM", "PROD_STORE", "ROUT_STORE", "Q",
        ],
    },
    "sacsma": {
        "skill": "hydrological-modeling/run-lumped-sacsma-model",
        "script": "run_lumped_sacsma.py",
        "output": "sacsma-run",
        "table": "lumped_sacsma_runoff.csv",
        "timestep": 24,
        "columns": [
            "time", "is_warmup", "P", "PET", "ET1", "ET2", "ET3", "ET4", "ET5", "TET", "ROIMP",
            "SSUR", "SIF", "SDRO", "SURF", "BASE", "PERC", "Q_MM", "UZTWC", "UZFWC", "LZTWC",
            "LZFSC", "LZFPC", "ADIMC", "Q",
        ],
    },
}

TASK_IDS = [
    f"hydromodel-{capability}-{index:03d}"
    for capability in ("dhf", "gr4j", "hbv", "sacsma", "tank")
    for index in (1, 2, 3)
]

AREA_KM2 = 640.0
RIVER_LENGTH_KM = 20.0
WARMUP_STEPS = 12

DHF_SUCCESS_PARAMETERS: dict[str, Any] = {
    "S0": 50.0, "U0": 90.0, "D0": 100.0, "KC": 0.8, "KW": 0.5, "K2": 0.4, "KA": 0.7,
    "G": 0.1, "A": 0.5, "B": 1.5, "B0": 1.0, "K0": 0.3, "N": 3, "DD": 1.2, "CC": 2.0,
    "COE": 0.4, "DDL": 1.0, "CCL": 2.0,
}
# Confirmed out-of-soft-range parameters: U0=100 exceeds [0, 90] and B=0.6 falls
# below [1, 3], which natively triggers the parameter_range warning.
DHF_WARNING_PARAMETERS: dict[str, Any] = {**DHF_SUCCESS_PARAMETERS, "U0": 100.0, "B": 0.6}
HBV_PARAMETERS: dict[str, Any] = {
    "fc": 195.0, "beta": 2.6, "c": 0.07, "k0": 0.163, "l": 4.87,
    "k1": 0.029, "k2": 0.049, "kp": 0.050, "lp": 0.5,
}
# fc=250 exceeds the [100, 200] soft range and natively triggers parameter_range.
HBV_WARNING_PARAMETERS: dict[str, Any] = {**HBV_PARAMETERS, "fc": 250.0}
TANK_PARAMETERS: dict[str, Any] = {
    "t0_is": 10.0, "t0_boc": 0.3, "t0_soc_uo": 0.4, "t0_soc_lo": 0.3,
    "t0_soh_uo": 80.0, "t0_soh_lo": 30.0, "t1_is": 10.0, "t1_boc": 0.25,
    "t1_soc": 0.25, "t1_soh": 50.0, "t2_is": 10.0, "t2_boc": 0.15,
    "t2_soc": 0.15, "t2_soh": 35.0, "t3_is": 10.0, "t3_soc": 0.02,
}
GR4J_PARAMETERS: dict[str, Any] = {"X1": 350.0, "X2": 0.0, "X3": 90.0, "X4": 1.7}
# X2<0 is a legal exchange value, but with a small routing store it drives the
# native floor-zero clipping of ROUT_STORE and QD.
GR4J_WARNING_PARAMETERS: dict[str, Any] = {**GR4J_PARAMETERS, "X2": -5.0}
SACSMA_PARAMETERS: dict[str, Any] = {
    "UZTWM": 150.0, "UZFWM": 50.0, "LZTWM": 800.0, "LZFPM": 800.0, "LZFSM": 200.0,
    "ADIMP": 0.1, "UZK": 0.2, "LZPK": 0.01, "LZSK": 0.3, "ZPERC": 20.0, "REXP": 1.5,
    "PCTIM": 0.02, "PFREE": 0.3, "RIVA": 0.0, "SIDE": 0.0, "RSERV": 0.3,
}
# RIVA>0 with a strong-evaporation dry spell drives the native tot_outflow<0
# clipping (riparian demand exceeds the outflow available).
SACSMA_WARNING_PARAMETERS: dict[str, Any] = {**SACSMA_PARAMETERS, "RIVA": 0.05}


def _capability(task_id: str) -> str:
    stem = task_id.removeprefix("hydromodel-").rsplit("-", 1)[0]
    if stem not in CAPABILITIES:
        raise ValueError(f"unsupported lumped model task id: {task_id}")
    return stem


def _index(task_id: str) -> int:
    if task_id not in TASK_IDS:
        raise ValueError(f"unsupported lumped model task id: {task_id}")
    return int(task_id.rsplit("-", 1)[1])


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


def _skill_script(capability: str) -> Path:
    configured = os.environ.get("HYDROTUNE_SKILLS_ROOT", "").strip().strip('"')
    skills_root = Path(configured) if configured else DEFAULT_SKILLS_ROOT
    meta = CAPABILITIES[capability]
    script = skills_root / FOLDER / f"run-lumped-{capability}-model" / "examples" / meta["script"]
    if not script.is_file():
        raise FileNotFoundError(f"{capability} skill script not found: {script}")
    return script


def _forcing_frame(capability: str, index: int) -> pd.DataFrame:
    if capability in ("gr4j", "sacsma"):
        return _daily_forcing_frame(capability, index)
    return _hourly_forcing_frame(capability, index)


def _daily_forcing_frame(capability: str, index: int) -> pd.DataFrame:
    days = np.arange(72)
    # Daily wet fixture with a dry tail that drains the unit hydrograph and the
    # lower-zone stores so the structural balance residual stays inside tolerance.
    precipitation = np.full(72, 0.5)
    precipitation[(days >= 8) & (days < 30)] = 12.0
    precipitation[(days >= 44) & (days < 58)] = 6.0
    evaporation = np.full(72, 2.0)
    if index == 2 and capability == "sacsma":
        # Strong-evaporation dry spell with RIVA>0 drives the native
        # tot_outflow<0 clipping (riparian demand exceeds available outflow).
        precipitation[40:52] = 0.0
        evaporation[40:52] = 8.0
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2024-08-01 00:00", periods=72, freq="D"),
            "P": precipitation,
            "E0": evaporation,
        }
    )
    if index == 3:
        # Sacramento's error task plants the missing value in the precipitation
        # column; GR4J plants it in the potential evaporation column.
        if capability == "sacsma":
            frame.loc[40, "P"] = np.nan
        else:
            frame.loc[40, "E0"] = np.nan
    return frame


def _hourly_forcing_frame(capability: str, index: int) -> pd.DataFrame:
    hours = np.arange(72)
    # Wet fixture: a permanent drizzle above the potential evaporation keeps
    # HBV soil storage and Tank boxes clear of the zero floors.
    precipitation = np.full(72, 0.6)
    precipitation[(hours >= 12) & (hours < 22)] = 12.0
    precipitation[(hours >= 36) & (hours < 44)] = 9.0
    evaporation = np.full(72, 0.35)
    if capability == "dhf":
        # Long sustained storms keep the DHF free-water storage from draining
        # through zero, which avoids the native negative-state clamping.
        precipitation = np.full(72, 0.6)
        precipitation[(hours >= 8) & (hours < 40)] = 12.0
        precipitation[(hours >= 44) & (hours < 60)] = 6.0
    if index == 2 and capability == "tank":
        # Dry spell with strong evaporation turns the net rain negative and
        # drives the tanks into the native numerical-clipping regime.
        precipitation[40:52] = 0.0
        evaporation[40:52] = 0.9
    frame = pd.DataFrame(
        {
            "time": pd.date_range("2024-08-01 00:00", periods=72, freq="h"),
            "P": precipitation,
            "E0": evaporation,
        }
    )
    if index == 3:
        frame.loc[40, "E0"] = np.nan
    return frame


def _parameters(capability: str, index: int) -> dict[str, Any]:
    if capability == "dhf":
        return DHF_WARNING_PARAMETERS if index == 2 else DHF_SUCCESS_PARAMETERS
    if capability == "gr4j":
        return GR4J_WARNING_PARAMETERS if index == 2 else dict(GR4J_PARAMETERS)
    if capability == "hbv":
        return HBV_WARNING_PARAMETERS if index == 2 else dict(HBV_PARAMETERS)
    if capability == "sacsma":
        return SACSMA_WARNING_PARAMETERS if index == 2 else dict(SACSMA_PARAMETERS)
    if capability == "tank":
        return dict(TANK_PARAMETERS)
    raise ValueError(f"unsupported capability: {capability}")


def _golden_command(capability: str, index: int, output: Path) -> list[str]:
    meta = CAPABILITIES[capability]
    args = [
        sys.executable,
        str(_skill_script(capability)),
        "--forcing",
        "forcing.csv",
        "--time-column",
        "time",
        "--params",
        "parameters.json",
        "--area-km2",
        str(AREA_KM2),
        "--timestep-hours",
        str(meta.get("timestep", 1)),
        "--mode",
        "continuous",
        "--warmup-steps",
        str(WARMUP_STEPS),
    ]
    if meta.get("pet_column") or capability in ("dhf", "gr4j", "sacsma"):
        args += ["--pet-column", "E0"]
    if capability == "dhf":
        args += ["--river-length-km", str(RIVER_LENGTH_KM), "--balance-tolerance-fraction", "0.05"]
    elif capability == "gr4j":
        # The groundwater-exchange bookkeeping closes only approximately, so the
        # user confirms a balance tolerance that covers the structural residual.
        args += ["--balance-tolerance-fraction", "0.2"]
    elif capability == "sacsma":
        # The source Sacramento subtracts ET4 from the outflow instead of the
        # stores, so the user confirms a wide tolerance for this structural loss.
        args += ["--balance-tolerance-fraction", "4.5"]
    elif capability == "hbv":
        # The source HBV never deducts Q0 from SM and loses water between the
        # effective-rainfall and recharge steps; the user confirms a wide
        # balance tolerance that accommodates this structural loss.
        args += ["--balance-tolerance-fraction", "6.5"]
    args += ["--output-format", "csv", "--output-dir", str(output)]
    return args


def _titles() -> dict[str, str]:
    return {
        "hydromodel-dhf-001": "Run a continuous lumped DHF simulation with two-segment warm-up",
        "hydromodel-dhf-002": "Report out-of-range DHF parameters instead of silently accepting them",
        "hydromodel-dhf-003": "Reject a DHF run with missing evaporation forcing",
        "hydromodel-hbv-001": "Run a continuous lumped HBV simulation",
        "hydromodel-hbv-002": "Report numerical clipping caused by a dry spell instead of hiding it",
        "hydromodel-hbv-003": "Reject an HBV run with missing evaporation forcing",
        "hydromodel-tank-001": "Run a continuous lumped Tank model simulation",
        "hydromodel-tank-002": "Report numerical clipping caused by negative net rain instead of hiding it",
        "hydromodel-tank-003": "Reject a Tank run with missing evaporation forcing",
        "hydromodel-gr4j-001": "Run a continuous daily lumped GR4J simulation",
        "hydromodel-gr4j-002": "Report the native clipping caused by a negative groundwater exchange",
        "hydromodel-gr4j-003": "Reject a GR4J run with missing potential evaporation",
        "hydromodel-sacsma-001": "Run a continuous daily lumped Sacramento simulation",
        "hydromodel-sacsma-002": "Report the native clipping caused by riparian demand in a dry spell",
        "hydromodel-sacsma-003": "Reject a Sacramento run with missing precipitation",
    }


def _prompts() -> dict[str, str]:
    return {
        "hydromodel-dhf-001": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-dhf-model. "
            "The forcing table is hourly; P and the potential evaporation column (pass --pet-column E0) are instantaneous "
            "rates in mm/h on a gap-free axis. The 18-parameter set is confirmed; area is 640 km2, river length is 20 km, "
            "timestep is 1 h, mode is continuous, warm-up is 12 steps, and the user confirms a water-balance tolerance of "
            "0.05 to account for the unit-hydrograph end truncation. "
            "Write the native outputs (lumped_dhf_runoff.csv, result.json) under dhf-run/. "
            "Do not modify parameters, fill missing values, change the warm-up, or substitute another model implementation."
        ),
        "hydromodel-dhf-002": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-dhf-model. "
            "The parameter set deliberately contains values outside the documented soft ranges (U0=100, B=0.6); this is a "
            "confirmed user decision, and the skill must accept the run and natively report the parameter_range warning. "
            "Run verbatim with --pet-column E0, area 640 km2, river length 20 km, timestep 1 h, mode continuous, warm-up 12 steps, "
            "balance tolerance 0.05, and write the native outputs (lumped_dhf_runoff.csv, result.json) under dhf-run/. "
            "Do not 'fix' the parameters to the soft ranges or suppress the warning."
        ),
        "hydromodel-dhf-003": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-dhf-model. "
            "The forcing table is hourly and contains at least one missing value in the evaporation column (pass --pet-column E0). "
            "Run the simulation verbatim with area 640 km2, river length 20 km, timestep 1 h, mode continuous, warm-up 12 steps, "
            "balance tolerance 0.05, and only the native result.json under dhf-run/. "
            "Do not fill, interpolate, or drop the missing value; do not rerun with repaired data; the script must reject the input "
            "itself. No lumped_dhf_runoff.csv may remain in dhf-run/."
        ),
        "hydromodel-hbv-001": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-hbv-model. "
            "The forcing table is hourly; P and E0 are instantaneous rates in mm/h on a gap-free axis. "
            "The 9-parameter set is confirmed; area is 640 km2, timestep is 1 h, mode is continuous, warm-up is 12 steps, and the "
            "user confirms a water-balance tolerance of 6.5 because the source HBV structurally loses water (Q0 is not deducted "
            "from SM and the effective-rainfall to recharge step discards a fraction). "
            "Write the native outputs (lumped_hbv_runoff.csv, result.json) under hbv-run/. "
            "Do not modify parameters, fill missing values, change the warm-up, or substitute another model implementation."
        ),
        "hydromodel-hbv-002": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-hbv-model. "
            "The parameter set deliberately contains fc=250, outside the documented [100, 200] soft range; this is a confirmed "
            "user decision, and the skill must accept the run and natively report the parameter_range warning. "
            "Run verbatim with area 640 km2, timestep 1 h, mode continuous, warm-up 12 steps, balance tolerance 6.5, and write the "
            "native outputs (lumped_hbv_runoff.csv, result.json) under hbv-run/. "
            "Do not 'fix' the parameters to the soft ranges or suppress the warning."
        ),
        "hydromodel-hbv-003": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-hbv-model. "
            "The forcing table is hourly and contains at least one missing E0 value. "
            "Run the simulation verbatim with area 640 km2, timestep 1 h, mode continuous, warm-up 12 steps, balance tolerance 6.5, "
            "and only the native result.json under hbv-run/. "
            "Do not fill, interpolate, or drop the missing evaporation value; do not rerun with repaired data; the script must reject "
            "the input itself. No lumped_hbv_runoff.csv may remain in hbv-run/."
        ),
        "hydromodel-tank-001": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-tank-model. "
            "The forcing table is hourly; P and E0 are instantaneous rates in mm/h on a gap-free axis. "
            "The 16-parameter set is confirmed; area is 640 km2, timestep is 1 h, mode is continuous, and warm-up is 12 steps. "
            "Write the native outputs (lumped_tank_runoff.csv, result.json) under tank-run/. "
            "Do not modify parameters, fill missing values, change the warm-up, or substitute another model implementation."
        ),
        "hydromodel-tank-002": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-tank-model. "
            "The forcing deliberately contains a dry spell (hours 40-51: P=0, E0=0.9 mm/h) that turns the net rain negative and "
            "drives the tanks into the native numerical-clipping regime; this is a confirmed user decision. "
            "Run verbatim with area 640 km2, timestep 1 h, mode continuous, warm-up 12 steps, and write the native outputs "
            "(lumped_tank_runoff.csv, result.json) under tank-run/. "
            "Numerical clipping must be reported natively in result.json, never hidden or corrected by altering parameters or forcing. "
            "Do not 'improve' the configuration to avoid the warning."
        ),
        "hydromodel-tank-003": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-tank-model. "
            "The forcing table is hourly and contains at least one missing E0 value. "
            "Run the simulation verbatim with area 640 km2, timestep 1 h, mode continuous, warm-up 12 steps, and only the native "
            "result.json under tank-run/. "
            "Do not fill, interpolate, or drop the missing evaporation value; do not rerun with repaired data; the script must reject "
            "the input itself. No lumped_tank_runoff.csv may remain in tank-run/."
        ),
        "hydromodel-gr4j-001": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-gr4j-model. "
            "The forcing table is daily; P and the potential evaporation column (pass --pet-column E0) are depths in mm per day on a "
            "gap-free axis. The 4-parameter set is confirmed; area is 640 km2, timestep is 24 h, mode is continuous, warm-up is "
            "12 steps, and the user confirms a water-balance tolerance of 0.2 for the approximate groundwater-exchange closure. "
            "Write the native outputs (lumped_gr4j_runoff.csv, result.json) under gr4j-run/. "
            "Do not modify parameters, fill missing values, change the warm-up, or substitute another model implementation."
        ),
        "hydromodel-gr4j-002": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-gr4j-model. "
            "The confirmed parameter set uses X2=-5.0: a legal negative groundwater exchange that drives the routing store into the "
            "native numerical-clipping regime during the dry tail. Run it verbatim with --pet-column E0, area 640 km2, timestep 24 h, "
            "mode continuous, warm-up 12 steps, balance tolerance 0.2. "
            "Write the native outputs (lumped_gr4j_runoff.csv, result.json) under gr4j-run/. "
            "Numerical clipping must be reported natively in result.json, never hidden or corrected by altering parameters or forcing. "
            "Do not 'improve' the configuration to avoid the warning."
        ),
        "hydromodel-gr4j-003": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-gr4j-model. "
            "The forcing table is daily and contains at least one missing value in the potential evaporation column (pass "
            "--pet-column E0). "
            "Run the simulation verbatim with area 640 km2, timestep 24 h, mode continuous, warm-up 12 steps, balance tolerance 0.2, "
            "and only the native result.json under gr4j-run/. "
            "Do not fill, interpolate, or drop the missing value; do not rerun with repaired data; the script must reject the input "
            "itself. No lumped_gr4j_runoff.csv may remain in gr4j-run/."
        ),
        "hydromodel-sacsma-001": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-sacsma-model. "
            "The forcing table is daily; P and the potential evaporation column (pass --pet-column E0) are depths in mm per day on a "
            "gap-free axis. The 16-parameter set is confirmed; area is 640 km2, timestep is 24 h, mode is continuous, warm-up is "
            "12 steps, and the user confirms a water-balance tolerance of 4.5 because the source Sacramento subtracts ET4 from the "
            "outflow instead of the stores. "
            "Write the native outputs (lumped_sacsma_runoff.csv, result.json) under sacsma-run/. "
            "Do not modify parameters, fill missing values, change the warm-up, or substitute another model implementation."
        ),
        "hydromodel-sacsma-002": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-sacsma-model. "
            "The confirmed parameter set uses RIVA=0.05, and the forcing deliberately contains a strong-evaporation dry spell "
            "(days 40-52: P=0, E0=8 mm/day) that drives the riparian demand into the native numerical-clipping regime. "
            "Run verbatim with --pet-column E0, area 640 km2, timestep 24 h, mode continuous, warm-up 12 steps, balance tolerance 4.5. "
            "Write the native outputs (lumped_sacsma_runoff.csv, result.json) under sacsma-run/. "
            "Numerical clipping must be reported natively in result.json, never hidden or corrected by altering parameters or forcing. "
            "Do not 'improve' the configuration to avoid the warning."
        ),
        "hydromodel-sacsma-003": (
            "Use forcing.csv and parameters.json exactly as supplied to run hydrological-modeling/run-lumped-sacsma-model. "
            "The forcing table is daily and contains at least one missing P value. "
            "Run the simulation verbatim with area 640 km2, timestep 24 h, mode continuous, warm-up 12 steps, balance tolerance 4.5, "
            "and only the native result.json under sacsma-run/. "
            "Do not fill, interpolate, or drop the missing precipitation value; do not rerun with repaired data; the script must reject "
            "the input itself. No lumped_sacsma_runoff.csv may remain in sacsma-run/."
        ),
    }


def _positive_grading(capability: str) -> list[dict[str, Any]]:
    meta = CAPABILITIES[capability]
    output = meta["output"]
    golden = f"expected/golden_workspace/{output}"
    result = f"{output}/result.json"
    return [
        {
            "name": "artifact_schema",
            "type": "file_check",
            "targets": [f"{output}/{meta['table']}", result],
            "required_columns": {
                f"{output}/{meta['table']}": meta["columns"],
                result: ["schema_version", "skill", "status", "message", "parameters", "inputs", "artifacts", "checks", "warnings", "provenance"],
            },
            "weight": 0.10,
        },
        {
            "name": "simulation_table",
            "type": "table_match",
            "target": f"{output}/{meta['table']}",
            "reference": f"{golden}/{meta['table']}",
            "datetime_columns": ["time"],
            "atol": 1e-9,
            "rtol": 1e-9,
            "weight": 0.30,
        },
        {"name": "result_skill", "type": "exact_match", "target": result, "field": "skill", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_status", "type": "exact_match", "target": result, "field": "status", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_message", "type": "exact_match", "target": result, "field": "message", "reference": f"{golden}/result.json", "weight": 0.05},
        {"name": "result_warnings", "type": "exact_match", "target": result, "field": "warnings", "reference": f"{golden}/result.json", "weight": 0.10},
        {"name": "result_checks", "type": "exact_match", "target": result, "field": "checks", "reference": f"{golden}/result.json", "weight": 0.05},
        {
            "name": "artifact_references",
            "type": "artifact_reference_check",
            "target": result,
            "required_keys": ["simulation_table"],
            "weight": 0.30,
        },
    ]


def _error_grading(capability: str) -> list[dict[str, Any]]:
    meta = CAPABILITIES[capability]
    output = meta["output"]
    result = f"{output}/result.json"
    golden = f"expected/golden_workspace/{output}/result.json"
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
            "targets": [f"{output}/{meta['table']}"],
            "weight": 0.20,
        },
    ]


def _build_task(task_id: str) -> dict[str, Any]:
    capability = _capability(task_id)
    index = _index(task_id)
    meta = CAPABILITIES[capability]
    positive = index < 3
    required = [f"{meta['output']}/result.json"]
    if positive:
        required = [f"{meta['output']}/{meta['table']}", *required]
    return {
        "id": task_id,
        "title": _titles()[task_id],
        "domain": "model-calibration",
        "difficulty": "intermediate" if index < 3 else "basic",
        "primary_skill": meta["skill"],
        "secondary_skills": [],
        "prompt": _prompts()[task_id],
        "data_description": "A deterministic continuous lumped-model problem with a complete confirmed parameter set and an hourly forcing table.",
        "data_files": ["forcing.csv", "parameters.json"],
        "required_outputs": required,
        "setup_notes": [
            "The parameter set, area, timestep, mode, and warm-up are confirmed by the user and must not be altered.",
            "P and the evaporation column are instantaneous rates in mm/h; discharge outputs are in m3/s.",
            "Do not install software or implement a replacement model.",
        ],
        "timeout_seconds": 300,
        "grading": _positive_grading(capability) if positive else _error_grading(capability),
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


def _generate_golden(task_dir: Path, task_id: str) -> None:
    capability = _capability(task_id)
    index = _index(task_id)
    meta = CAPABILITIES[capability]
    expected_code = 2 if index == 3 else 0
    with tempfile.TemporaryDirectory(prefix=f"hsqb-{task_dir.name}-") as raw_temp:
        temp = Path(raw_temp)
        work = temp / "workspace"
        shutil.copytree(task_dir / "data", work)
        output = work / meta["output"]
        completed = subprocess.run(
            _golden_command(capability, index, output),
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
    _index(task_id)
    capability = _capability(task_id)
    index = _index(task_id)
    task_dir = ROOT / task_id
    data_dir = task_dir / "data"
    _write_csv(data_dir / "forcing.csv", _forcing_frame(capability, index))
    _write_json(data_dir / "parameters.json", _parameters(capability, index))
    _generate_golden(task_dir, task_id)
    _write_json(task_dir / "task.json", _build_task(task_id))
