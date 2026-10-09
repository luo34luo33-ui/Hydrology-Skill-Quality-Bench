# Composite task development rules

These rules apply only to `composite_tests/`. The single-skill isolation rules for
the 183 atomic tasks under `tests/` remain in force.

- Keep IDs continuous: data 001–008, model 001–012, analysis 001–004.
- A deliverable task needs at least three distinct scientific capabilities and
  verifiable consumption of upstream artifacts. Repeated execution, reports,
  figures and questions do not count toward this minimum.
- Define the scientific DAG, source provenance, numerical tolerances, provided
  setting bindings and critical-error predicates in
  `expected/evaluation.json`. Never stage this file or the generator for an Agent.
- Public prompts describe business requests and artifact interfaces. They must
  not name a Skill or prescribe implementation order. Provide every necessary
  fact and permission in scenario.json before execution. All 24 v2 tasks support
  normal delivery; tools, code and equivalent implementations are agent choices.
- Use unchanged supplied observations. Mark every synthetic supplement. A blank
  rainfall record is missing data; only explicit test supplements may replace it.
- Source datasets and external skills are read-only. Freeze their SHA-256 hashes;
  changes require a new source receipt and regenerated references.
- Preserve the real basin boundary and independently validate spatial products.
  Do not relax QC or alter topology to make a normal reference pass.
- The old four blocked cases are normal v2 scenarios. An early block does not
  satisfy the requested normal delivery. Missing outputs, ordinary rounding and missing evidence are
  task failures or unassessable cases, not automatic critical errors.
- interaction_mode=none: no user answers, confirmation server, credentials or
  confirmation tool. Grade correct application of upfront scientific settings;
  never require or fabricate confirmation events. Expose every required output
  and its schema in the public output interfaces. Factory scaffolding is optional.
- Grade scientific artifacts and dependencies, not Skill invocations. Native
  execution traces document reference construction only.
- Use trusted graders and independent numerical replay. Never run candidate
  grading code or an LLM judge. Structured claims and their evidence are graded;
  arbitrary prose's scientific correctness is not certified.
- Development uses `HydroTune-eval`, native scientific programs, fake processes
  and recorded events. Do not launch a real CLI Agent during development.
- Keep atomic coverage separate from workflow/composite coverage. Default CLI
  discovery remains `atomic`; use `--suite composite` or `--suite all` explicitly.

Required verification:

```powershell
conda activate HydroTune-eval
python scripts/verify_composite_tasks.py
python scripts/check_composite_repeatability.py
python -m pytest -q
python -m harness.cli validate --suite all
```

The first verifier grades canonical references. `--native` regenerates all 24
references through real scientific programs; `--refresh` regenerates input,
output and hidden contracts together. Review any contract change before freezing a formal
experiment. The repeatability verifier regenerates all cases in two temporary
trees and compares scientific meaning and actual file-reference integrity.
