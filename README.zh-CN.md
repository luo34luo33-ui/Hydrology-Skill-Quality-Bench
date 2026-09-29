# 水文技能质量基准（HSQB）

[English](README.md) | [简体中文](README.zh-CN.md)

HSQB 是一个轻量、确定性的 Level-1 基准，用于衡量水文技能套件能否提升通用 CLI Agent 完成科学任务的能力。每道任务都在全新、无交互的 workspace 中独立运行一次，并根据 Agent 生成的 artifacts 评分，而不是根据最终的自然语言回答评分。

HSQB 不是桌面 Agent 评测系统、人工测试管理工具、完整流域工作流、Web dashboard，也不使用 LLM-as-a-judge。Level 2 平台集成测试和 Level 3 真实流域案例不属于本仓库范围。

## 设计来源

HSQB 借鉴了 [GPTomics/bioTaskBench](https://github.com/GPTomics/bioTaskBench) 中适合轻量 Benchmark 的设计：每个 Task 独立调用、显式 staging 输入数据、确定性加权评分、Agent 执行失败后仍对已有 artifacts 评分，以及将覆盖率和质量分数分开统计。

本项目有意不实现外部测试集 adapter、manifest、断点恢复、重复运行与稳定性管理，以及额外的报告服务。HSQB 仅增加研究问题直接需要的能力：`primary_skill`/`secondary_skills`、Skill 级聚合、水文指标、成对 Skill uplift，以及严格的 hidden expected 隔离。与参考项目的 Codex wrapper 不同，HSQB 对每道任务只启动一次 Agent invocation。

项目原则是：**Task-rich, Harness-light**。科学复杂性应存在于 Task 数据、hidden expected 和确定性 grader 中，而不是存在于复杂的框架抽象中。

## 项目结构

```text
harness/         Task 校验、执行、评分、聚合与 CLI
scripts/         具体 CLI Agent 的启动 wrapper
tests/           Benchmark Tasks、可见数据、生成脚本和 hidden expected
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
- `hydromodel-de-001` 至 `003`、`hydromodel-ga-001` 至 `003`、`hydromodel-pso-001` 至 `003`、`hydromodel-sce-ua-001` 至 `003` 和 `hydromodel-two-stage-001` 至 `003`：分别覆盖五种率定器的确定性成功、可恢复 warning 与非法配置拒绝，并检查独立验证。
- `hydromodel-muskingum-001` 至 `003`：马斯京根河道演算，覆盖单段与 cascade 布局、确认负等价 X 的保留 warning，以及缺测入流拒绝。
- `hydromodel-xaj-001` 至 `003`：集总式新安江连续前向模拟，覆盖 warm-up、原生数值裁剪 warning 与缺测蒸发强迫拒绝。
- `hydromodel-dhf-001` 至 `003`：集总式 DHF 连续模拟（真两段 warm-up），覆盖确认越界参数的原生 `parameter_range` warning 与缺测蒸发强迫拒绝。
- `hydromodel-gr4j-001` 至 `003`：集总式 GR4J 日尺度连续模拟，覆盖确认负地下水交换触发的原生裁剪 warning 与缺测潜在蒸发拒绝。
- `hydromodel-sacsma-001` 至 `003`：集总式 Sacramento 日尺度连续模拟，覆盖确认旱段河岸带需求触发的原生裁剪 warning 与缺测降雨拒绝。
- `hydromodel-lohmann-001` 至 `003`：Lohmann 河道演算（双分量日尺度入流），覆盖短序列单位线尾部滞留的原生 `volume_difference` warning 与缺测分量拒绝。
- `hydromodel-hbv-001` 至 `003`：集总式 HBV 连续模拟，覆盖结构性水量损耗的确认容差、确认越界 `fc` 的原生 warning 与缺测蒸发强迫拒绝。
- `hydromodel-tank-001` 至 `003`：集总式 Tank 连续模拟，覆盖旱段负净雨驱动的原生裁剪 warning 与缺测蒸发强迫拒绝。
- `hydroanalysis-event-metrics-001` 至 `003`：逐场次洪水指标，覆盖确认阈值合格判定、并列峰取首峰的原生处理与部分场次 QC 失败的原生部分表模式。
- `hydroanalysis-series-metrics-001` 至 `003`：连续序列指标，覆盖显式步长、退化方差处理（`nse` 记 unavailable）与缺测拒绝。
- `hydroanalysis-aggregate-metrics-001` 至 `003`：等权分组汇总与合格率，覆盖空表 warning 语义与未知统计量拒绝。
- `hydroanalysis-ml-correct-001` 至 `003`：确定性 ridge 残差校正 train/predict 双模式，覆盖滞后行丢弃 warning 与缺 `random-state` 拒绝。
- `hydroanalysis-001`：水文指标计算和系统性洪峰延迟诊断。

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
