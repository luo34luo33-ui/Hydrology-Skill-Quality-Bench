# 水文技能质量基准（HSQB）

[English](README.md) | [简体中文](README.zh-CN.md)

## 仓库发布范围与外部资源

仓库保留基准代码、任务定义，以及 `tests/`、`composite_tests/`、`composite_tests_v3/` 中全部测试输入和隐藏评分参考。测试内的 `result.json`、`expected/`、`golden_workspace/` 属于固定测试资产，随仓库上传；隐藏参考仍不得提供给候选 Agent。

实际运行结果、宿主机验收／认证报告、provider 配置、冻结技能／程序、第三方二进制和 `composite_assets/` 不随仓库发布。因此，克隆后须另行准备资源，才能运行完整实验及全部软件测试。准备入口、路径、版本和验证限制见[外部资源准备说明](docs/EXTERNAL_RESOURCES.md)。原宿主机的认证不能作为新环境的认证。


HSQB 用于衡量水文技能套件能否提升通用 CLI Agent 完成科学任务的能力，包含 183 道确定性原子题和 24 道多步骤组合题。两类均在全新、无交互的 workspace 中执行并按科学成果评分；组合题 v2 启动前提供完备资料，运行中不补充用户信息。

原子套件新增 `no-skills / programs-only / with-skills` 三组入口及共享公共契约。实现、命令和实际验收阻断项见 [原子三组对照说明](docs/ATOMIC_THREE_ARM.zh-CN.md)。正式运行须通过新的独立认证；旧两组结果不并入新实验。

HSQB 不是桌面 Agent 评测系统、人工测试管理工具、完整流域工作流、Web dashboard，也不使用 LLM-as-a-judge。Level 2 平台集成测试和 Level 3 真实流域案例不属于本仓库范围。

## 设计来源

HSQB 借鉴了 [GPTomics/bioTaskBench](https://github.com/GPTomics/bioTaskBench) 中适合轻量 Benchmark 的设计：每个 Task 独立调用、显式 staging 输入数据、确定性加权评分、Agent 执行失败后仍对已有 artifacts 评分，以及将覆盖率和质量分数分开统计。

原子套件保留轻量执行核心；独立的组合套件增加三种 CLI 的事件适配、隔离容器执行、配对重复及科学闸门统计。共享能力包括：`primary_skill`/`secondary_skills`、Skill 级聚合、水文指标、成对 Skill uplift，以及严格的 hidden expected 隔离。与参考项目的 Codex wrapper 不同，HSQB 对每道任务只启动一次 Agent invocation。

项目原则是：**Task-rich, Harness-light**。科学复杂性应存在于 Task 数据、hidden expected 和确定性 grader 中，而不是存在于复杂的框架抽象中。

## 项目结构

```text
harness/         Task 校验、执行、评分、聚合与 CLI
scripts/         具体 CLI Agent 的启动 wrapper
tests/           183 道原子题（默认套件）
composite_tests/  24 道组合题、可见输入和隐藏科学依赖
composite_tests_v3/  修订号 5 组合题及评分参考
runtime/         构建文件和配置模板；程序与技能另行准备
examples/        不参与运行的 Task 模板与参考 artifacts
tests_harness/   Benchmark 软件自身的测试
```

新增或扩展任何测试（包括 `hydrodata`、`hydromodel`、`hydroanalysis` 和未来测试家族）前，请先阅读 [HSQB Benchmark 通用测试开发指南](DEVELOPMENT_GUIDE.zh-CN.md)。该指南规定 Skill 目录读取、家族命名、fixture/oracle、grader 和真实脚本验证流程；开发阶段禁止运行实际 Agent，但开发完成后仍可正常执行正式 Agent 评测。

每道 Benchmark Task 使用以下结构：

```text
tests/<domain>/<task-id>/
├── task.json
├── generate_data.py
├── data/       # 会复制到 Agent workspace
└── expected/   # 仅供 grader 使用，绝不复制给 Agent
```

## 统一测试环境

本项目的开发检查和 Benchmark 运行统一使用现有 Conda 环境 `HydroTune-eval`。安装、测试、校验 Task 或启动 Benchmark 前必须先激活该环境：

```bash
conda activate HydroTune-eval
python -m pip install -e .
python -m pip install -e ".[dev]"
```

不要从 `base` 环境运行项目测试，也不要静默创建其他环境。如果自动化主机无法执行 shell activation，可使用等价形式 `conda run -n HydroTune-eval <command>`。

HSQB 要求 Python 3.11 或更高版本；当前配置环境使用 Python 3.11。除 NumPy、pandas 和 SciPy 外，空间测试使用 rasterio、GeoPandas、Shapely、pyproj、matplotlib、Pillow 和 WhiteboxTools。

## 校验 Tasks

```bash
conda activate HydroTune-eval
hydroSkillBench validate
hydroSkillBench validate --domain model-calibration
hydroSkillBench validate --test-id hydromodel-de-001
```

校验内容包括 Task ID、domain、difficulty、Skill 元数据、路径安全、可见数据、隐藏 reference、grader 类型、required outputs 和 criterion 权重。所选 Task 集合中的 ID 必须全局唯一。

## 无 Skills 与有 Skills 运行

每道匹配的 Task 只执行一次 Agent 命令，并关闭标准输入。即使 Agent 返回非零退出码或超时，Harness 仍会对已经生成的 artifacts 评分。

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

可以使用 `--domain`、`--test-id` 和 `--skill` 筛选 Task。`--timeout` 会覆盖 Task 自带的超时设置。`--workspace-root` 可将运行中的 workspace 放到另一个磁盘，但运行结果目录中仍会保留审计副本。

Codex wrapper 会生成 `AGENTS.md`，将适用 Skills 快照复制到 `.agents/skills/`，从子进程环境中移除原始 Skill 路径，并通过 workspace-write sandbox 和自动审批检查启动唯一一次、临时的 `codex exec`。

### OpenCode

OpenCode 复用相同的 Task 发现、workspace staging、Skill 快照、超时、评分和结果目录。请先安装并登录 `opencode` CLI；模型名称使用 OpenCode 的 `provider/model` 格式。不加筛选参数时会运行全部 Task。

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

OpenCode wrapper 会为每道 Task 启动一次全新、无交互的 `opencode run`。它会隔离全局配置，关闭外部插件、Claude 兼容配置、自动分享、自动更新和 LSP 下载，禁止访问 Task workspace 之外的路径及向用户提问，并只开放本次快照中的 Skills。`--effort` 会作为 OpenCode 的 provider-specific model variant 传入。

### Qwen / CodeBuddy 原子适配器

已增加 `scripts/run_qwen.py` 和 `scripts/run_codebuddy.py`，可作为原子套件的 `--agent-cmd` 使用。两者支持模型、推理强度、技能快照、临时配置和 stream-json 日志；运行 `python scripts/run_qwen.py --check` 或 `python scripts/run_codebuddy.py --check` 可检查本机 CLI 参数兼容性。认证和模型访问需要另外验证。

完整 PowerShell 单题、有／无技能、批量命令及认证配置见 [原子 CLI 操作说明](docs/ATOMIC_CLI_RUN.zh-CN.md)。这些入口只提供本机配置隔离，不提供文件或网络安全隔离，不改变原子任务超时与评分契约。

## 运行产物

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

`run_metadata.json` 记录 Task hashes、运行环境、Agent 配置、超时设置和 Skill 快照 hash。原始 Task 定义和 grader 配置不会放入 Agent workspace。`result.json` 是每道 Task 的权威评分 artifact。

运行元数据还会记录当前 Conda 环境和 prefix。环境信息参与 `compare` 的可比性检查，因此从 `HydroTune-eval` 生成的 run 不会被静默地视为与其他环境生成的 run 等价。

## 评分模型

每个 criterion 都会生成 raw value 和一个裁剪到 `[0, 1]` 的 score。所有 criterion 权重之和必须严格为 1，Task Score 是各 criterion score 的加权和。连续指标使用 Task 定义的 `zero_at` 与 `one_at` 进行线性插值，不在 Harness 中硬编码全局水文阈值。

通用 graders：

- `file_check`、`file_absence_check`、`column_check`、`exact_match`、`range_check`
- `set_overlap`、`numeric_correlation`、`code_executes`
- `table_match`：将目标表与 hidden reference 按行、按单元格比较，支持 `columns`、可选 `datetime_columns` 以及数值 `atol`/`rtol`
- `raster_match`：比较 CRS、仿射网格、波段、NoData、掩膜和像元值，支持连续值容差与分类值精确匹配
- `vector_match`：按稳定主键或顺序无关集合比较 CRS、属性和规范化几何
- `artifact_reference_check`：验证 `result.json` 中 artifact 的安全相对路径、存在性和 SHA-256

`file_absence_check` 接受 `target` 或 `targets`，按不存在的路径比例评分；空文件仍视为已存在。

水文 graders：

- `hydro_metric`：NSE、KGE 2009、PBIAS、RMSE、MAE、R²
- `timeseries_match`、`peak_check`、`volume_check`
- `water_balance_check`、`parameter_range`

覆盖率和分数分别统计：

- `attempted`：至少一个 required output 存在且非空。
- `coverage`：已尝试 Task 数除以 Task 总数。
- `score_attempted`：已尝试 Task 的平均分。
- `score_overall`：全部 Task 的平均分，未尝试 Task 按 0 分计算。

结果按 Task、primary skill、domain、difficulty 和 overall 聚合。v0.1 中 secondary skills 仅用于描述，不计入主要 Skill 聚合分数。

## 比较与重新评分

```bash
conda activate HydroTune-eval
hydroSkillBench compare results/no-skills results/with-skills
hydroSkillBench regrade results/with-skills
```

`compare` 会报告成对的 Task、Skill、Domain、Difficulty、Overall 和 Coverage 差异。如果 model、effort、Agent 命令、Task hashes、timeout 或记录的软件环境不同，命令会拒绝将两个 run 标记为可比。Skill condition、Skill 路径和 Skill 快照 hash 是预期的实验差异。

`regrade` 使用当前 grader 重新评价已保留的 workspace，不重新运行 Agent；execution 元数据和日志保持不变。

## Task schema

`task.json` 是 Task 定义的单一事实来源。必填字段为：

```text
id, title, domain, difficulty, primary_skill, prompt,
data_files, required_outputs, timeout_seconds, grading
```

可选字段为 `secondary_skills`、`data_description` 和 `setup_notes`。所有路径必须是相对路径；绝对路径和 `..` 会被拒绝。可见输入相对于 `data/`；隐藏的 `reference` 和 `expected_file` 必须位于 `expected/` 下。

新增 Task 的步骤：

1. 从某个 Skill 声明的能力和具体 failure mode 反推 Task。
2. 确保 prompt 无交互，并明确要求没有歧义的输出 artifacts。
3. 添加固定随机种子的 `generate_data.py`，分别写出可见数据与隐藏数据。
4. 优先使用多个连续、确定性的 criteria，并确保权重之和为 1。
5. 运行 `hydroSkillBench validate`，并为该 Task 添加 golden Harness test。

新增 grader 时，在 `harness/grader.py` 中实现并注册到 `GRADERS`，将名称加入 `harness.schemas.GRADER_TYPES`，在本文档中说明 criterion 字段，并测试成功、失败和边界行为。在单文件确实无法维护之前，不要提前创建 grader package。

## 内置 synthetic Tasks

- `hydrodata-timeseries-001` 至 `hydrodata-timeseries-012`：覆盖流量时序排序、单位及时区换算、XLSX serial 日期、显式修复策略和必须拒绝的异常输入。
- `hydrodata-baseflow-001` 至 `hydrodata-baseflow-008`：覆盖 Eckhardt 显式/自动退水参数、上下限裁剪、零流量、证据门槛和非法输入拒绝。
- `hydrodata-flood-events-001` 至 `hydrodata-flood-events-010`：覆盖单峰与复峰、事件合并、warm-up、规模过滤、零事件 warning、配置拒绝和洪量守恒科学 QC。
- `hydrodata-dem-grid-001` 至 `008`：覆盖 CRS、UTM、垂直单位、buffer 覆盖和非法 DEM/流域输入。
- `hydrodata-stream-network-001` 至 `008`：覆盖 Whitebox D8 链、面积阈值换算、平坦区、空河网和非法分析 DEM。
- `hydrodata-topology-build-001` 至 `009`：覆盖完整 buffer 追踪、边界纳入、warning、网格错位、D8、循环和子流域映射。
- `hydrodata-topology-validate-001` 至 `010`：覆盖单/多出口、引用互反、循环、面积、网格、哈希和科学 QC 退出码。
- `hydrodata-eto-faopm-001` 至 `003`：FAO-56 日尺度 ETo 双站推导、确认 floor_zero 裁剪负映射 PET 与缺测气象拒绝。
- `hydrodata-forcing-standardize-001` 至 `003`：step_depth 标准化、带显式 reset 的累计雨量计换算与漏标复位拒绝。
- `hydrodata-terrain-topidx-001` 至 `003`：哈希互链单出口 HydroBase 链的 TOPMODEL 地形输入、确认平地的坡度裁剪记录与双出口拒绝。
- `hydrodata-forcing-aggregate-001` 至 `003`：泰森权重聚合到已验证子流域、全流域聚合与站点缺时步拒绝。
- `hydromodel-de-001` 至 `003`、`hydromodel-ga-001` 至 `003`、`hydromodel-pso-001` 至 `003`、`hydromodel-sce-ua-001` 至 `003` 和 `hydromodel-two-stage-001` 至 `003`：分别覆盖五种率定器的确定性成功、可恢复 warning 与非法配置拒绝，并检查独立验证。
- `hydromodel-muskingum-001` 至 `003`：马斯京根河道演算，覆盖单段与 cascade 布局、确认负等价 X 的保留 warning，以及缺测入流拒绝。
- `hydromodel-xaj-001` 至 `003`：集总式新安江连续前向模拟，覆盖 warm-up、原生数值裁剪 warning 与缺测蒸发强迫拒绝。
- `hydromodel-dhf-001` 至 `003`：集总式 DHF 连续模拟（真两段 warm-up），覆盖确认越界参数的原生 `parameter_range` warning 与缺测蒸发强迫拒绝。
- `hydromodel-gr4j-001` 至 `003`：集总式 GR4J 日尺度连续模拟，覆盖确认负地下水交换触发的原生裁剪 warning 与缺测潜在蒸发拒绝。
- `hydromodel-sacsma-001` 至 `003`：集总式 Sacramento 日尺度连续模拟，覆盖确认旱段河岸带需求触发的原生裁剪 warning 与缺测降雨拒绝。
- `hydromodel-topmodel-001` 至 `003`：消费哈希校验地形产品的集总式 TOPMODEL 模拟、确认 Green-Ampt 入渗超渗分支与强迫时间轴缺口拒绝。
- `hydromodel-xaj-sd-001` 至 `003`：已验证双河段网络上的半分布式新安江模拟、原生滞后尾 warning 与强迫覆盖缺失拒绝。
- `hydromodel-swat-sd-001` 至 `003`：已验证网络上的半分布式 SWAT 日尺度模拟、原生 Muskingum 稳定性 warning 与 HRU 面积失配拒绝。
- `hydromodel-lohmann-001` 至 `003`：Lohmann 河道演算（双分量日尺度入流），覆盖短序列单位线尾部滞留的原生 `volume_difference` warning 与缺测分量拒绝。
- `hydromodel-hbv-001` 至 `003`：集总式 HBV 连续模拟，覆盖结构性水量损耗的确认容差、确认越界 `fc` 的原生 warning 与缺测蒸发强迫拒绝。
- `hydromodel-tank-001` 至 `003`：集总式 Tank 连续模拟，覆盖旱段负净雨驱动的原生裁剪 warning 与缺测蒸发强迫拒绝。
- `hydroanalysis-event-metrics-001` 至 `003`：逐场次洪水指标，覆盖确认阈值合格判定、并列峰取首峰的原生处理与部分场次 QC 失败的原生部分表模式。
- `hydroanalysis-series-metrics-001` 至 `003`：连续序列指标，覆盖显式步长、退化方差处理（`nse` 记 unavailable）与缺测拒绝。
- `hydroanalysis-aggregate-metrics-001` 至 `003`：等权分组汇总与合格率，覆盖空表 warning 语义与未知统计量拒绝。
- `hydroanalysis-ml-correct-001` 至 `003`：确定性 ridge 残差校正 train/predict 双模式，覆盖滞后行丢弃 warning 与缺 `random-state` 拒绝。
- `hydroanalysis-align-discharge-001` 至 `003`：哈希校验的观测—模拟对齐（HBV 出口结果）、预热与未匹配观测剔除、集总式 XAJ 输出作为模拟源的原生拒绝。

`examples/tasks/hydrodata-example/task.example.json` 将原降雨 QC Task 保留为非运行模板。它位于 `tests/` 之外且文件名不是 `task.json`，因此不会被发现、校验、执行或聚合。

在仓库根目录重新生成数据：

```bash
conda activate HydroTune-eval
for script in tests/data-preprocessing/hydrodata-*/generate_data.py; do python "$script"; done
for script in tests/spatial-analysis/hydrodata-*/generate_data.py; do python "$script"; done
for script in tests/model-calibration/hydromodel-*-*/generate_data.py; do python "$script"; done
for script in tests/results-analysis/hydroanalysis-*/generate_data.py; do python "$script"; done
```

生成脚本不会使用不同内容覆盖已有的确定性 artifact，从而使意外的 truth 变化能够被明确发现。

## 开发检查

```bash
conda activate HydroTune-eval
python -m pytest
hydroSkillBench validate
```

测试套件覆盖 hidden expected 隔离、执行与超时行为、部分分评分、水文与空间 grader 边界情况、结果聚合、成对比较、重新评分，以及全部内置 Task 的 golden checks。

## 原子技能补齐（2026-10-04）

183道可执行任务覆盖全部41个原子技能。本次新增43题，覆盖BMA和8个图册／报告技能；旧综合诊断题已移为非运行模板。详见[外部资源准备与本地报告生成](docs/EXTERNAL_RESOURCES.md)。开发阶段未运行实际Agent批次。

新增 `figure_contract_check` 和 `report_contract_check`，均使用任务本地隐藏 `reference`。图件检查解码尺寸、元数据及SVG科学图层；报告检查原始证据、时段表格、受控结论和逐段审查绑定。评分器不执行候选代码，不使用模型裁判。使用 `HydroTune-eval` 运行 `scripts/verify_bma_tasks.py`、`scripts/verify_atlas_tasks.py`、`scripts/verify_report_tasks.py` 完成确定性原生脚本验收。


## 组合任务与技能对照（2026-10-05，v2）

数据处理 8、模型计算 12、结果分析 4，共 24 道组合题，全部正常交付。
正常题至少需要三种不同科学能力及真实成果依赖。公开提示不点名 Skill、不提供
隐藏答案。原子覆盖仍独立保持 41/41，总计 207 道定义。

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

最后一条仅生成 144 次固定配对调度，不启动 Agent。`--suite atomic|composite|all`
默认 `atomic`。新版不启动确认服务，评分检查任务成功、关键科学错误和已提供设定的正确使用。
工具、代码、步骤和等价实现可自主选择，指定模型、参数、评价目标与预算保持约束。

详见[无交互 v2 说明](docs/COMPOSITE_UNATTENDED_V2.zh-CN.md)和[本地报告生成与资源准备](docs/EXTERNAL_RESOURCES.md)。Docker 须另外安装，并提供其 PATH 和所需执行权限。
新版已有独立的无交互烟雾、网络隔离与预算认证；旧版认证不能用于新版。
真实 Agent 验证情况单列，参考计算不代替真实运行。
