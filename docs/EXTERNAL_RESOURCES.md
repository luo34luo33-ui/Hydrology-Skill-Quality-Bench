# External resources / 外部资源准备

The GitHub distribution contains the benchmark software and all fixtures in
`tests/`, `composite_tests/`, and `composite_tests_v3/`, including input data,
`expected/`, `golden_workspace/`, and test `result.json` files. Those references
are grader-only and must never be exposed to candidate agents.

仓库保留上述三套测试的完整输入与标准答案，包括测试内的实测水文数据副本。
它不包含实际运行结果、宿主机验收报告、认证回执、模型凭证或下列外部资源。
克隆后可以检查任务结构；完整运行、科学程序复验和资源相关软件测试需要另备资源。

## Runtime paths and versions / 路径与版本

| Local path (not distributed) | Preparation and requirement |
|---|---|
| `runtime/skills/` | Frozen HydroTune skills from an independently supplied source checkout. Preserve the category/skill source layout when preparing it. The atomic suite describes 41 atomic skills and 3 workflows. |
| `runtime/public/` | Composite scientific programs, schemas and assets extracted from that same source. Generate with `scripts/prepare_composite_runtime.py`. |
| `docs/composite-contracts/` | A full source skill copy produced by the same preparation script, including Python programs. This is external source material, not just an interface document; do not upload it. |
| `runtime/atomic-public/`, `runtime/atomic-skills/` | Atomic program and skill bundles produced by `scripts/prepare_atomic_contracts.py` from the composite bundles and source inventory. Shared programs/assets must have identical hashes. |
| `runtime/vendor/linux/` | WhiteboxTools Linux executable and its required distribution assets, supplied locally for the Docker build. Scientific fixtures were developed with WhiteboxTools **2.4.0** and `max_procs=1`; the Python package version is separate. |
| `composite_assets/` | Shared raw/supplemented data and reference seeds for fixture regeneration. These are unnecessary for merely validating the already included task fixtures, but regeneration requires the original data and seed resources. |
| `runtime/atomic-provider-config/`, `runtime/composite-provider-config/` | Host-created, condition-independent CLI configuration. Never commit real credentials or copy a personal CLI HOME into a candidate container. |

Use Python **3.11+** in `HydroTune-eval`. Python dependency versions for the
container are recorded in `runtime/requirements.lock.txt`; development package
constraints are in `pyproject.toml`. Build inputs such as base-image digest,
Node.js and CLI versions must be explicitly chosen and recorded on the new host.
The Dockerfile does not supply defaults for a certified image. This release
does not distribute a runnable image, a source skill revision, or a public
download for the original basin data. Obtain these resources separately from
their owner; a similarly named or newer skill bundle is not evidence of exact
scientific reproducibility. Record source revisions and SHA-256 hashes locally.

Some legacy generators and launchers retain the author's Windows paths as
fallback defaults. Override them explicitly: use `HYDROTUNE_SKILLS_ROOT`,
`HSQB_LUMPED_INPUT`, `HSQB_SEMI_INPUT`, or the script's source-path argument.
For `scripts/start_overnight.ps1`, pass `-Python` with the active
`HydroTune-eval` interpreter and set your own deadline/output directory; install
Docker on PATH. Absolute paths inside committed fixture metadata are historical
provenance, not an instruction to access the author's filesystem. The harness
stages/rebases local artifact references; keep source evidence intact.

本仓库没有提供上述技能和原始流域资料的公开下载地址，也不保证可以自动获取。
当前测试资产含所需输入与参考值，但重建它们仍需要原始资料、参考种子和匹配的
科学程序。不能把缺少资源的检查标为通过，也不能用新版本程序覆盖固定参考值。

## Prepare an independently supplied skill checkout / 准备技能与程序

Run from the repository root in the designated environment. Replace the source
path with the independently obtained checkout. These commands create ignored
local resources and inventories; the atomic contract builder also regenerates
versioned public contracts, so review its diff before committing anything.

```powershell
conda activate HydroTune-eval
$env:HYDROTUNE_SKILLS_ROOT = 'D:/external/HydroTune-Skills'
python scripts/prepare_composite_runtime.py --skills-root $env:HYDROTUNE_SKILLS_ROOT
python scripts/capture_atomic_catalog.py $env:HYDROTUNE_SKILLS_ROOT
python scripts/prepare_atomic_contracts.py
```

保留并对比已提交任务和契约；如果来源资源无法匹配，停止正式比较，查清版本差异。
`docs/atomic-public-contracts/` 是可上传的公开接口说明；不要把它误当作运行程序。

To regenerate shared basin inputs, set `HSQB_LUMPED_INPUT` and
`HSQB_SEMI_INPUT` to the separately supplied original data roots. The ingestion
entry point is `prepare_shared_inputs()` in `scripts/composite_inputs.py`.
It expects the original event CSVs, station/boundary spatial files, DEM tiles,
and continuous XLSX structure, rather than arbitrary replacement data.
`scripts/composite_tasks.py` additionally consumes
`composite_assets/reference_seeds/`, which must be supplied separately.
Do not regenerate committed fixtures merely to make an upload validation pass.

## Templates and local certification / 模板与本机认证

Keep `runtime/experiment.template.json` and
`runtime/atomic-experiment.lock.example.json` as unconfigured templates.
The example atomic lock has relative paths, no actual image/hash/credentials,
and no certification. Supply host CLI configurations and a JSON object mapping
CLI names to actual installed version strings. After setting model/effort and
building the image, generate a separate local lock:

```powershell
python scripts/freeze_atomic_experiment.py --source runtime/atomic-experiment.lock.example.json --output runtime/atomic-experiment.lock.json --image-digest $ImageDigest --versions $CliVersionsJson
python scripts/audit_atomic_contracts.py --golden
python scripts/audit_atomic_negative_controls.py
python scripts/certify_atomic_isolation.py --lock runtime/atomic-experiment.lock.json
```

The CLI-version file, image digest and model settings are local inputs, not
values furnished by this release. Contract, isolation, provider connection,
native skill discovery and budget-event evidence must all be regenerated and
reviewed on the new host. Freeze again after certification to bind receipts.
The scripts above are only part of that process; do not treat their presence
as certification or change pass flags to bypass missing evidence. For composite
runs, start from `runtime/experiment.template.json` and follow
[the composite guide](COMPOSITE_UNATTENDED_V2.zh-CN.md).

## Checks available after cloning / 克隆后的检查

```powershell
conda activate HydroTune-eval
python -m harness.cli validate --suite atomic
python -m harness.cli validate --tests-root composite_tests --suite composite
python -m harness.cli validate --tests-root composite_tests_v3 --suite composite
```

Software tests using only temporary synthetic fixtures can run without the
external bundles. Some tests import `runtime/public/`, inspect frozen skills,
read local inventories/reports, or launch the native scientific programs; the
complete `python -m pytest -q` suite requires the relevant resources. Keep such
failures separate from resource-independent checks. Never silently certify the
complete suite from a resource-limited run.

The preserved revision-4 composite reference manifests also contain source
paths that the current `composite-scientific-v3` resolver rejects as
`unsafe_source_path`. This is a pre-existing compatibility issue distinct from
missing external bundles; obtaining those bundles alone does not resolve it.
The upload preserves those references and the current scorer. Revision 5 has a
separate suite and must be independently verified before formal comparison.
Legacy manifest-scope tests may still expect parent traversal that the current
resolver forbids, and a pilot test expects older certification error wording.
These compatibility expectations are preserved for a separate maintenance
change; this publication does not relax path validation or certification.

## Reports stay local / 报告仅本地保留

`result/`, `results/`, caches, logs, host locks, actual provider configurations,
copied skill inventories and explicitly listed reports under `docs/` are ignored.
Report references in procedural documents describe files to generate locally,
not files included in the repository. Regeneration entry points include:

| Local evidence | Generator (resources must already be prepared) |
|---|---|
| Atomic source inventory | `scripts/capture_atomic_catalog.py <skills-root>` |
| Public program build/equivalence | `scripts/prepare_atomic_contracts.py` |
| Contract acceptance, negative controls | `scripts/audit_atomic_contracts.py --golden`, `scripts/audit_atomic_negative_controls.py` |
| Public program scientific verification | `scripts/verify_public_atomic.py` |
| Atomic build repeatability | `scripts/verify_atomic_public_build.py` |
| Composite source/fixture verification | `scripts/verify_composite_tasks.py`, `scripts/check_composite_repeatability.py` |
| Isolation probes | `scripts/certify_atomic_isolation.py --lock <local-lock>` |
| Experiment reports | The relevant `harness.atomic_experiment` / `harness.experiment` entry point with a local lock and a fresh `results/` output directory |

Some regeneration scripts depend on previous inventories, source assets or
certifications. Read their prerequisites and retain failures as failures.
Generate reports locally; do not upload them with the benchmark fixtures.
