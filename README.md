# Hydrology Skill Quality Benchmark (HSQB)

The atomic suite now supports `no-skills`, `programs-only`, and `with-skills`, sharing public input/output contracts. See [three-arm implementation and acceptance](docs/ATOMIC_THREE_ARM.zh-CN.md). Formal execution fails closed while native task/program conflicts, negative-control gaps, or provider certifications remain unresolved. Legacy two-arm runs are not pooled with this experiment.

[English](README.md) | [简体中文](README.zh-CN.md)

## Repository distribution and external resources

This repository includes benchmark code, task definitions, all test inputs and hidden scoring references in `tests/`, `composite_tests/`, and `composite_tests_v3/`. Test `result.json`, `expected/`, and `golden_workspace/` files are fixtures and remain versioned. Hidden references must never be staged into a candidate agent workspace.

Actual run outputs, host acceptance/certification reports, provider configurations, frozen skills/programs, third-party binaries, and `composite_assets/` are not distributed. A fresh clone therefore cannot run the complete experiment or every software test until external resources have been prepared. See [external resource preparation](docs/EXTERNAL_RESOURCES.md) for paths, versions, preparation commands, and validation limits. No previous host's certification is transferable to a fresh installation.


HSQB measures whether a hydrology skill suite improves a general CLI agent's scientific task completion. It includes 183 deterministic atomic tasks and 24 multi-step composite tasks. Both run in fresh non-interactive workspaces and are graded from scientific artifacts. Composite v2 supplies all facts and permissions upfront, with no user information added during execution.

HSQB is not a desktop-agent evaluation, a human test manager, a full basin workflow, a web dashboard, or an LLM-as-a-judge system. Level 2 platform integration and Level 3 real-basin case studies are intentionally outside this repository.

## Design lineage

HSQB borrows the useful small-core patterns from [GPTomics/bioTaskBench](https://github.com/GPTomics/bioTaskBench): independent task invocation, explicit data staging, deterministic weighted criteria, grading after failed execution, and separate coverage and quality scores.

The atomic suite keeps a small execution core. The separate composite suite adds three CLI event adapters, isolated container execution, paired repetitions and scientific-gate reporting. Shared features include: `primary_skill`/`secondary_skills`, skill-level aggregation, hydrology metrics, paired skill uplift, and strict hidden-expected isolation. Unlike the reference Codex wrapper, HSQB starts exactly one agent invocation per task.

The guiding principle is **Task-rich, Harness-light**. Scientific difficulty belongs in task data, hidden expected outputs, and deterministic graders—not in framework abstractions.

## Project layout

```text
harness/         task validation, execution, grading, aggregation, CLI
scripts/         concrete CLI-agent wrappers
tests/           183 atomic tasks (default suite)
composite_tests/  24 composite tasks with hidden scientific DAGs
composite_tests_v3/  revision 5 composite tasks and scoring references
runtime/         build files and templates; external programs/skills prepared locally
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

### Qwen / CodeBuddy atomic adapters

Use `--agent-cmd "python scripts/run_qwen.py"` or `--agent-cmd "python scripts/run_codebuddy.py"` with `--suite atomic`. Both adapters consume the benchmark model, reasoning effort and skill snapshot, create a fresh temporary configuration, and preserve stream-json output and the CLI exit code. Run each script with `--check` to check installed CLI flags without model calls; authentication and model access are not checked.

See the [PowerShell atomic CLI guide](docs/ATOMIC_CLI_RUN.zh-CN.md) for paired examples, authentication and batch selection. These local adapters isolate configuration, not filesystem or network access. They preserve the existing atomic timeout and grading contract and do not change the composite runtime.

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
- `hydrodata-eto-faopm-001` through `003`: FAO-56 daily ETo for two stations, confirmed floor_zero clipping of negative mapped PET, and rejection of missing meteorology.
- `hydrodata-forcing-standardize-001` through `003`: step-depth standardization, running-cumulative gauges with explicit resets, and rejection of an unmarked cumulative reset.
- `hydrodata-terrain-topidx-001` through `003`: TOPMODEL terrain inputs from a hash-linked single-outlet HydroBase chain, recorded slope clipping on a confirmed flat plateau, and rejection of two exit cells.
- `hydrodata-forcing-aggregate-001` through `003`: Thiessen aggregation over validated subbasins, whole-basin aggregation, and rejection of a station missing a forcing step.
- `hydromodel-de-001` through `003`, `hydromodel-ga-001` through `003`, `hydromodel-pso-001` through `003`, `hydromodel-sce-ua-001` through `003`, and `hydromodel-two-stage-001` through `003`: atomic optimizer contracts covering deterministic success, recoverable warning, and rejected configuration cases with independent validation.
- `hydromodel-muskingum-001` through `003`: Muskingum channel routing across single and cascaded layouts, preservation of a confirmed negative equivalent X, and rejection of missing inflow.
- `hydromodel-xaj-001` through `003`: continuous lumped Xinanjiang runs with warm-up, native numerical-clipping warnings, and rejection of missing evaporation forcing.
- `hydromodel-dhf-001` through `003`: continuous lumped DHF runs with two-segment warm-up, confirmed out-of-soft-range parameters reported natively, and rejection of missing evaporation forcing.
- `hydromodel-gr4j-001` through `003`: continuous daily lumped GR4J runs, native clipping from a confirmed negative groundwater exchange, and rejection of missing potential evaporation.
- `hydromodel-sacsma-001` through `003`: continuous daily lumped Sacramento runs, native clipping from riparian demand in a confirmed dry spell, and rejection of missing precipitation.
- `hydromodel-topmodel-001` through `003`: lumped TOPMODEL runs on a hash-checked terrain product, the confirmed Green-Ampt infiltration-excess branch, and rejection of a gapped forcing time axis.
- `hydromodel-xaj-sd-001` through `003`: semi-distributed Xinanjiang over a validated two-reach network, the native lag-tail warning, and rejection of incomplete forcing coverage.
- `hydromodel-swat-sd-001` through `003`: semi-distributed SWAT daily runs over a validated network, the native Muskingum stability warning, and rejection of HRU areas that disagree with the subbasin table.
- `hydromodel-lohmann-001` through `003`: daily Lohmann routing of two discharge components, the documented unit-hydrograph retention warning on a short sustained series, and rejection of missing component values.
- `hydromodel-hbv-001` through `003`: continuous lumped HBV runs with a structurally confirmed wide balance tolerance, confirmed out-of-range `fc` reported natively, and rejection of missing evaporation forcing.
- `hydromodel-tank-001` through `003`: continuous lumped Tank runs, dry-spell negative net rain driving the native clipping warning, and rejection of missing evaporation forcing.
- `hydroanalysis-event-metrics-001` through `003`: per-event flood metrics with confirmed qualification thresholds, tied-peak resolution at the first maximum, and the native partial-table QC-failure mode.
- `hydroanalysis-series-metrics-001` through `003`: continuous series metrics with an explicit timestep, degenerate-variance handling (`nse` unavailable), and missing-value rejection.
- `hydroanalysis-aggregate-metrics-001` through `003`: equal-weight aggregation by group with qualification rates, the warned empty-table result, and unknown-statistic rejection.
- `hydroanalysis-ml-correct-001` through `003`: deterministic ridge residual correction in train/predict modes, native lag-row warnings, and rejection of a missing random state.
- `hydroanalysis-align-discharge-001` through `003`: hash-checked discharge alignment against an HBV outlet result, warm-up and unmatched-observation exclusion, and rejection of lumped XAJ output as a simulation source.

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

## Atomic skill completion (2026-10-04)

183 runnable tasks cover all 41 atomic skills. This completion adds 43 tasks for BMA and eight visualization/reporting skills; the historical composite diagnostic task is now a non-running template. See [resource preparation and local report generation](docs/EXTERNAL_RESOURCES.md). Development does not run actual Agent batches.

New graders: `figure_contract_check` and `report_contract_check`, each with a task-local hidden `reference`. Figures are checked by decoded dimensions, metadata and scientific SVG geometry; reports by source evidence, scoped tables, controlled conclusions and paragraph review binding. Neither grader executes candidate code or uses an LLM judge. Native verification: `scripts/verify_bma_tasks.py`, `scripts/verify_atlas_tasks.py`, `scripts/verify_report_tasks.py`, using `HydroTune-eval`.


## Composite benchmark (2026-10-05, v2)

24 tasks cover data preparation (8), model computation (12), and results analysis
(4): all 24 support normal delivery. Tasks need at least
three distinct scientific capabilities with actual artifact dependencies. Prompts
name no Skill and reveal no hidden answers. Atomic coverage remains 41/41.

```powershell
conda activate HydroTune-eval
python -m harness.cli validate --suite all
python scripts/verify_composite_tasks.py
python scripts/check_composite_repeatability.py
python -m pytest -q
python scripts/freeze_composite_unattended.py
python scripts/audit_composite_unattended.py
python -m harness.experiment --repetitions 1 --output results/composite-unattended-v2-r4
```

The last command creates a deterministic 144-run schedule without launching an
Agent. `--suite atomic|composite|all` defaults to `atomic`. Composite outcomes use
all-gate task success, task-level critical scientific errors, and information-item
provided-setting usage counts; weighted scores remain diagnostic. No confirmation service is started. Agents may choose tools, code, execution order and equivalent implementations within the declared scientific constraints.

The source datasets remain read-only. Supplemented values are labelled synthetic
test data, with original missing records preserved. Both arms have identical
scientific programs and basic interfaces; the skill arm additionally mounts the
frozen 41 atomic skills and 3 workflows. Reference artifacts and hidden evaluation
are never staged. Candidate-authored grading code and LLM judges are not used.

See the [unattended v2 guide](docs/COMPOSITE_UNATTENDED_V2.zh-CN.md),
[resource preparation](docs/EXTERNAL_RESOURCES.md), and
[development rules](composite_tests/DEVELOPMENT_RULES.md).
Install Docker separately and ensure it is available on PATH with the required execution permissions. New unattended smoke, isolation and budget certifications are separate from old certificates. Actual Agent runs are reported separately from reference computations.
