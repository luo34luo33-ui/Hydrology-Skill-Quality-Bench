# Hydrology Skill Quality Benchmark (HSQB)

[English](README.md) | [简体中文](README.zh-CN.md)

HSQB is a lightweight, deterministic Level-1 benchmark for measuring whether a hydrology skill suite improves a general CLI agent's ability to complete scientific tasks. Each task runs once in a fresh, non-interactive workspace and is scored from produced artifacts rather than the agent's final prose.

HSQB is not a desktop-agent evaluation, a human test manager, a full basin workflow, a web dashboard, or an LLM-as-a-judge system. Level 2 platform integration and Level 3 real-basin case studies are intentionally outside this repository.

## Design lineage

HSQB borrows the useful small-core patterns from [GPTomics/bioTaskBench](https://github.com/GPTomics/bioTaskBench): independent task invocation, explicit data staging, deterministic weighted criteria, grading after failed execution, and separate coverage and quality scores.

It deliberately omits external-suite adapters, manifests, resume logic, repeat/stability management, and extra reporting services. HSQB adds only what its research question needs: `primary_skill`/`secondary_skills`, skill-level aggregation, hydrology metrics, paired skill uplift, and strict hidden-expected isolation. Unlike the reference Codex wrapper, HSQB starts exactly one agent invocation per task.

The guiding principle is **Task-rich, Harness-light**. Scientific difficulty belongs in task data, hidden expected outputs, and deterministic graders—not in framework abstractions.

## Project layout

```text
harness/         task validation, execution, grading, aggregation, CLI
scripts/         concrete CLI-agent wrappers
tests/           benchmark tasks, visible data, generators, hidden expected
examples/        non-runnable task templates and reference artifacts
tests_harness/   tests for the benchmark software itself
```

Before adding or extending any task family—including `hydrodata`, `hydromodel`, `hydroanalysis`, and future families—follow the Chinese [general HSQB benchmark development guide](DEVELOPMENT_GUIDE.zh-CN.md). It defines Skill discovery, family-specific naming, fixtures/oracles, graders, and direct script verification. Real agents are prohibited during development, while formal agent evaluation remains supported after development acceptance.

Every benchmark task has this shape:

```text
tests/<domain>/<task-id>/
├── task.json
├── generate_data.py
├── data/       # copied to the agent workspace
└── expected/   # grader-only; never staged for the agent
```

## Standard test environment

All development checks and benchmark runs for this project use the existing Conda environment `HydroTune-eval`. Activate it before installing, testing, validating tasks, or launching benchmark runs:

```bash
conda activate HydroTune-eval
python -m pip install -e .
python -m pip install -e ".[dev]"
```

Do not run project tests from `base` or silently create another environment. On automation hosts where shell activation is unavailable, `conda run -n HydroTune-eval <command>` is the equivalent execution form. HSQB requires Python 3.11 or newer. Spatial tasks additionally use rasterio, GeoPandas, Shapely, pyproj, matplotlib, Pillow, and WhiteboxTools.

## Validate tasks

```bash
conda activate HydroTune-eval
hydroSkillBench validate
hydroSkillBench validate --domain model-calibration
hydroSkillBench validate --test-id hydromodel-de-001
```

Validation checks task IDs, domains, difficulties, skill metadata, safe paths, visible data, hidden references, grader types, required outputs, and criterion weights. IDs must be unique across the selected task set.

## Run without and with skills

The agent command is run once per matching task with standard input closed. A non-zero exit or timeout does not suppress grading of artifacts already produced.

```bash
conda activate HydroTune-eval
hydroSkillBench run \
  --agent-cmd "python scripts/run_codex.py" \
  --model YOUR_MODEL \
  --effort medium \
  --output results/no-skills

hydroSkillBench run \
  --agent-cmd "python scripts/run_codex.py" \
  --model YOUR_MODEL \
  --effort medium \
  --skills-path /path/to/HydroTune-skills \
  --output results/with-skills
```

Filters are available through `--domain`, `--test-id`, and `--skill`. `--timeout` overrides task timeouts. `--workspace-root` can place live workspaces on another volume; an audit copy is still retained under the run output.

The Codex wrapper creates `AGENTS.md`, snapshots applicable skills under `.agents/skills/`, removes the source skill path from the child environment, and launches a single ephemeral `codex exec` with a workspace-write sandbox and automatic approval review.

### OpenCode

OpenCode uses the same task discovery, workspace staging, skill snapshots, timeouts, grading, and result layout. Install and authenticate the `opencode` CLI first, then select a model in its `provider/model` format. Omitting all filters runs every task.

```bash
hydroSkillBench run \
  --agent-cmd "python scripts/run_opencode.py" \
  --model provider/model \
  --effort high \
  --output results/opencode-no-skills

hydroSkillBench run \
  --agent-cmd "python scripts/run_opencode.py" \
  --model provider/model \
  --effort high \
  --skills-path /path/to/HydroTune-skills \
  --output results/opencode-with-skills
```

The OpenCode wrapper starts one fresh non-interactive `opencode run` per task. It isolates global configuration, disables external plugins, Claude compatibility, auto-sharing, auto-updates, and LSP downloads; denies access outside the task workspace and interactive questions; and exposes only the snapshotted benchmark skills. `--effort` is passed to OpenCode as the provider-specific model variant.

## Run artifacts

```text
results/my-run/
├── run_metadata.json
├── summary.json
└── tasks/<task-id>/
    ├── result.json
    ├── execution.json
    ├── stdout.log
    ├── stderr.log
    └── workspace/
```

`run_metadata.json` records the task hashes, runtime, agent configuration, timeouts, and skill snapshot hash. The canonical task and grader configuration are not placed in the agent workspace. `result.json` is the authoritative per-task grading artifact.

The runtime metadata includes the active Conda environment and prefix. Because environment metadata participates in `compare` compatibility checks, a run from `HydroTune-eval` cannot silently be compared as equivalent to a run produced from another environment.

## Grading model

Each criterion produces a raw value and a score clipped to `[0, 1]`. Criterion weights sum to exactly 1 and the task score is their weighted sum. Continuous metrics use task-defined `zero_at` and `one_at` interpolation rather than global hard-coded hydrology thresholds.

Generic graders:

- `file_check`, `file_absence_check`, `column_check`, `exact_match`, `range_check`
- `set_overlap`, `numeric_correlation`, `code_executes`
- `table_match`: positional row/cell comparison against a hidden table, with `columns`, optional `datetime_columns`, and numeric `atol`/`rtol`
- `raster_match`: semantic comparison of CRS, affine grid, bands, NoData, masks, and pixel values
- `vector_match`: keyed or order-independent comparison of CRS, attributes, and normalized geometries
- `artifact_reference_check`: safe relative-path, existence, and SHA-256 validation for result artifacts

`file_absence_check` accepts `target` or `targets` and scores the fraction of paths that do not exist. Empty files count as present.

Hydrology graders:

- `hydro_metric`: NSE, KGE 2009, PBIAS, RMSE, MAE, R²
- `timeseries_match`, `peak_check`, `volume_check`
- `water_balance_check`, `parameter_range`

Coverage and score are distinct:

- `attempted`: at least one required output exists and is non-empty.
- `coverage`: attempted tasks divided by total tasks.
- `score_attempted`: mean score over attempted tasks.
- `score_overall`: mean score over all tasks, with unattempted tasks scoring zero.

Results are aggregated by task, primary skill, domain, difficulty, and overall. Secondary skills are descriptive and do not receive primary aggregation credit in v0.1.

## Compare and regrade

```bash
conda activate HydroTune-eval
hydroSkillBench compare results/no-skills results/with-skills
hydroSkillBench regrade results/with-skills
```

`compare` reports paired task, skill, domain, difficulty, overall, and coverage deltas. It refuses to label runs comparable when the model, effort, command, task hashes, timeouts, or recorded software environment differ. Skill condition, path, and snapshot hash are the intended experimental difference.

`regrade` applies the current grader to retained workspaces without running the agent again. Execution metadata and logs remain unchanged.

## Task schema

`task.json` is the single source of truth. Required fields are:

```text
id, title, domain, difficulty, primary_skill, prompt,
data_files, required_outputs, timeout_seconds, grading
```

Optional fields are `secondary_skills`, `data_description`, and `setup_notes`. Paths are relative; absolute paths and `..` are rejected. Visible inputs are relative to `data/`. Hidden `reference` and `expected_file` paths must be under `expected/`.

To add a task:

1. Derive it from a claimed skill capability and a concrete failure mode.
2. Make the prompt non-interactive and specify unambiguous output artifacts.
3. Add a fixed-seed `generate_data.py` that writes visible and hidden artifacts separately.
4. Prefer several continuous, deterministic criteria and ensure weights sum to 1.
5. Run `hydroSkillBench validate` and add a golden Harness test.

To add a grader, implement it in `harness/grader.py`, register it in `GRADERS`, add its name to `harness.schemas.GRADER_TYPES`, document its criterion fields here, and test success, failure, and boundary behavior. Do not introduce a grader package until this single file becomes demonstrably unmaintainable.

## Included synthetic tasks

- `hydrodata-timeseries-001` through `hydrodata-timeseries-012`: discharge standardization across sorting, unit/timezone conversion, XLSX serial dates, authorized repairs, and contract-required rejection cases.
- `hydrodata-baseflow-001` through `hydrodata-baseflow-008`: Eckhardt separation with explicit and estimated recession parameters, clipping bounds, zero flow, evidence checks, and invalid-input rejection.
- `hydrodata-flood-events-001` through `hydrodata-flood-events-010`: isolated and compound peaks, merging, warm-up, filtering, zero-event warnings, configuration rejection, and scientific volume-balance QC.
- `hydrodata-dem-grid-001` through `008`: CRS, UTM, vertical units, buffer coverage, and rejected DEM/basin inputs.
- `hydrodata-stream-network-001` through `008`: the Whitebox D8 chain, area-threshold conversion, flats, empty networks, and invalid analysis DEMs.
- `hydrodata-topology-build-001` through `009`: full-buffer tracing, boundary inclusion, warnings, grid alignment, D8 validity, cycles, and subbasin mapping.
- `hydrodata-topology-validate-001` through `010`: single/multiple outlets, reciprocal references, cycles, area/grid consistency, hashes, and scientific-QC exit codes.
- `hydromodel-de-001` through `003`, `hydromodel-ga-001` through `003`, `hydromodel-pso-001` through `003`, `hydromodel-sce-ua-001` through `003`, and `hydromodel-two-stage-001` through `003`: atomic optimizer contracts covering deterministic success, recoverable warning, and rejected configuration cases with independent validation.
- `hydromodel-muskingum-001` through `003`: Muskingum channel routing across single and cascaded layouts, preservation of a confirmed negative equivalent X, and rejection of missing inflow.
- `hydromodel-xaj-001` through `003`: continuous lumped Xinanjiang runs with warm-up, native numerical-clipping warnings, and rejection of missing evaporation forcing.
- `hydromodel-dhf-001` through `003`: continuous lumped DHF runs with two-segment warm-up, confirmed out-of-soft-range parameters reported natively, and rejection of missing evaporation forcing.
- `hydromodel-gr4j-001` through `003`: continuous daily lumped GR4J runs, native clipping from a confirmed negative groundwater exchange, and rejection of missing potential evaporation.
- `hydromodel-sacsma-001` through `003`: continuous daily lumped Sacramento runs, native clipping from riparian demand in a confirmed dry spell, and rejection of missing precipitation.
- `hydromodel-lohmann-001` through `003`: daily Lohmann routing of two discharge components, the documented unit-hydrograph retention warning on a short sustained series, and rejection of missing component values.
- `hydromodel-hbv-001` through `003`: continuous lumped HBV runs with a structurally confirmed wide balance tolerance, confirmed out-of-range `fc` reported natively, and rejection of missing evaporation forcing.
- `hydromodel-tank-001` through `003`: continuous lumped Tank runs, dry-spell negative net rain driving the native clipping warning, and rejection of missing evaporation forcing.
- `hydroanalysis-event-metrics-001` through `003`: per-event flood metrics with confirmed qualification thresholds, tied-peak resolution at the first maximum, and the native partial-table QC-failure mode.
- `hydroanalysis-series-metrics-001` through `003`: continuous series metrics with an explicit timestep, degenerate-variance handling (`nse` unavailable), and missing-value rejection.
- `hydroanalysis-aggregate-metrics-001` through `003`: equal-weight aggregation by group with qualification rates, the warned empty-table result, and unknown-statistic rejection.
- `hydroanalysis-ml-correct-001` through `003`: deterministic ridge residual correction in train/predict modes, native lag-row warnings, and rejection of a missing random state.
- `hydroanalysis-001`: metric calculation and diagnosis of a systematic peak delay.

`examples/tasks/hydrodata-example/task.example.json` preserves the former precipitation-QC task as a non-runnable template. Because it is outside `tests/` and is not named `task.json`, it is never discovered, validated, executed, or aggregated.

Regenerate them from the repository root:

```bash
conda activate HydroTune-eval
for script in tests/data-preprocessing/hydrodata-*/generate_data.py; do python "$script"; done
for script in tests/spatial-analysis/hydrodata-*/generate_data.py; do python "$script"; done
for script in tests/model-calibration/hydromodel-*-*/generate_data.py; do python "$script"; done
for script in tests/results-analysis/hydroanalysis-*/generate_data.py; do python "$script"; done
```

Generators refuse to overwrite a deterministic artifact with different content, making accidental truth changes explicit.

## Development checks

```bash
conda activate HydroTune-eval
python -m pytest
hydroSkillBench validate
```

The test suite includes hidden-expected isolation, execution and timeout behavior, partial-credit grading, hydrology and spatial grader edge cases, aggregation, paired comparison, regrade behavior, and golden checks for all built-in tasks.
