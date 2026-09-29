# Codex Prompt — Hydrology Skill Quality Benchmark (HSQB)

你是一名资深 AI Agent Benchmark、Python 工程和水文模拟评测框架开发者。

请设计并实现一个新的轻量级开源项目：

# Hydrology Skill Quality Benchmark (HSQB)

HSQB 是 **HydroTune-skills** 测试链中的 **Level 1**。

它的目标不是评价完整桌面 Agent 平台，也不是执行真实流域端到端案例，而是通过：

- 自动化；
- 无交互；
- CLI Agent；
- artifact-based evaluation；
- deterministic grading；

来验证 **HydroTune-skills 中单个或局部 Skill 的质量**。

核心研究问题是：

> 当保持 Agent 模型、推理强度、输入数据、软件环境、Task prompt、timeout 和 grader 不变时，引入 HydroTune-skills 是否能够稳定提高通用 Agent 完成水文专业任务的能力？

请重点参考 GPTomics/bioTaskBench 的设计思想与工程结构：

https://github.com/GPTomics/bioTaskBench

但不要机械复制代码。原则是：

> **Task-rich, Harness-light.**

复杂性应主要存在于：

- Task 设计；
- 测试数据；
- hidden expected；
- 科学 grader；

而不是复杂的软件架构。

---

# 1. 项目边界

HSQB 只实现整个 HydroTune-skills 测试链中的 Level 1。

完整测试链为：

```text
Level 1 — Task
Hydrology Skill Quality Benchmark
自动化 / CLI / 无交互
验证单个或局部 Skill 是否有效

Level 2 — Pipeline
人工测试多个可交互桌面 Agent 平台
验证 HydroTune-skills 与通用 Agent 平台的调用、组合和交互兼容性

Level 3 — Case
真实流域案例
展示 HydroTune-skills 在完整水文模拟中的实际使用过程
```

本项目 **不要实现 Level 2 或 Level 3**。

不要加入：

- 桌面自动化；
- 人工测试管理；
- 会话轨迹分析；
- GUI；
- Web dashboard；
- LLM-as-a-judge；
- 复杂 workflow engine。

---

# 2. 核心实验设计

HSQB 最基本的实验是：

```text
                       Fixed
            ┌───────────────────────────┐
            │ Agent model               │
            │ reasoning effort          │
            │ runtime environment       │
            │ task prompt               │
            │ input data                │
            │ timeout                   │
            │ deterministic grader      │
            └─────────────┬─────────────┘
                          │
                ┌─────────┴─────────┐
                │                   │
            No Skill           With Skill
                │                   │
                ▼                   ▼
             Score A             Score B
                │                   │
                └─────────┬─────────┘
                          ▼
                   Skill uplift
                    Δ = B - A
```

因此 HSQB 是：

```text
HydroTune-skills quality benchmark
```

而不是单纯的：

```text
hydrology knowledge benchmark
```

Task 应尽量要求 Agent 真正：

- 查看输入数据；
- 编写 Python / R / Shell；
- 调用预安装工具；
- 执行计算；
- 处理运行错误；
- 生成指定 scientific artifacts；
- 由 grader 对 artifacts 自动评分。

避免以知识问答为主要形式。

---

# 3. 参考 BioTaskBench 的核心设计原则

请优先继承以下思想。

## 3.1 每个 Task 独立执行

每个测试都是一次独立 Agent invocation：

```text
Task 001
→ fresh workspace
→ one Agent invocation
→ grade
→ finish

Task 002
→ fresh workspace
→ one Agent invocation
→ grade
→ finish
```

不同 Task 不共享 conversation state。

---

## 3.2 Non-interactive

Level 1 为无交互 benchmark。

Agent 运行时不允许依赖真人继续回答问题。

建议 runner 使用类似：

```python
stdin=subprocess.DEVNULL
```

Task author 必须保证完成该 Task 所需的信息已经提供。

如果 Task 因关键信息缺失而无法完成，应视为 Task authoring 问题，而不是依赖测试人员补充。

---

## 3.3 Artifact-based evaluation

不要主要根据 Agent 最后的自然语言回答评分。

主要检查其最终生成的：

- CSV；
- JSON；
- TXT；
- GeoJSON；
- Raster；
- NetCDF；
- 参数文件；
- 模型配置；
- 时间序列；
- 模型输出；
- 运行日志；
- 其他科学计算 artifact。

Agent 即使说“任务完成”，但 artifact 缺失或错误，也不能获得高分。

---

## 3.4 Deterministic grading

v1 不使用 LLM judge 作为核心评分器。

优先使用：

```text
file existence
schema validation
exact match
range check
numeric tolerance
correlation
set overlap
hydrological metrics
physical consistency
spatial comparison
```

要求同一 artifact 重复评分得到相同结果。

---

## 3.5 Tool-agnostic

除非 Task 本身就是测试特定软件接口，否则不要规定 Agent 必须使用某个具体工具。

原则：

```text
不同合理工具 / 方法
只要产生科学上等价的结果
应获得相近评分
```

例如：

```text
Python
R
GDAL
模型自带工具
其他合理实现
```

都可以。

---

## 3.6 Hidden expected

Agent workspace 只能获得：

- task description；
- allowed input data；
- runtime notes。

不能获得：

- hidden truth；
- expected output；
- reference answer；
- grader 内部阈值或答案信息。

`expected/` 只允许 grader 访问。

必须写 Harness 单元测试，确保 `expected/` 永远不会被复制到 Agent workspace。

---

## 3.7 Partial credit

单个 Task 不应只做 pass/fail。

Task 由多个 grading criteria 组成：

```text
TaskScore = Σ criterion_score_i × weight_i
```

要求：

```text
0 <= TaskScore <= 1
```

各 criterion 权重总和必须为 1。

---

# 4. Task 是 HSQB 的核心

HSQB 的研究价值主要来自 `tests/`，而不是一个复杂 Harness。

一个好的 Task 应满足：

```text
明确输入
+
明确专业目标
+
明确输出 artifact
+
明确 deterministic grader
```

Task 应尽量隔离一个主要 HydroTune-skills 能力。

不要把：

```text
原始 DEM
→ 数据预处理
→ 模型构建
→ 率定
→ 验证
→ 报告
```

全部塞进一个 Level-1 Task。

---

# 5. Task 必须从 HydroTune-skills 的能力声明反推

不要先问：

> 水文学里有哪些知识可以出题？

而要按：

```text
HydroTune Skill
↓
Claimed capability
↓
Skill 想避免的典型 failure mode
↓
Test family
↓
多个 test instances
```

例如：

```text
Skill:
meteorological-qc

Capabilities:
- time-axis validation
- missing value detection
- invalid precipitation detection
- unit consistency
- anomaly handling

Tests:
hydrodata-001
hydrodata-002
hydrodata-003
```

不要采用：

```text
1 Skill = 1 Test
```

应允许一个 Skill 对应多个不同 test instances，用于验证其泛化能力。

---

# 6. 项目结构：尽量学习 BioTaskBench

第一版项目结构控制在以下范围：

```text
Hydrology-Skill-Quality-Benchmark/
│
├── README.md
├── LICENSE
├── pyproject.toml
├── .gitignore
│
├── harness/
│   ├── __init__.py
│   ├── cli.py
│   ├── runner.py
│   ├── grader.py
│   ├── reporter.py
│   └── schemas.py
│
├── scripts/
│   └── run_codex.py
│
├── tests/
│   ├── data-preprocessing/
│   │   ├── hydrodata-001/
│   │   └── ...
│   │
│   ├── model-calibration/
│   │   ├── hydromodel-de-001/
│   │   └── ...
│   │
│   └── results-analysis/
│       ├── hydroanalysis-001/
│       └── ...
│
└── tests_harness/
    ├── test_runner.py
    ├── test_grader.py
    ├── test_reporter.py
    └── test_schemas.py
```

不要在 v0.1 创建以下额外层：

```text
hsqb/
docs/
adapters/
benchmark/
metrics/
registry/
workspace/
```

除非在实现过程中出现非常明确、无法避免的工程需求。

如果确实要增加目录，必须先在 README 或代码注释中说明为什么当前简单结构已经无法支撑该职责。

原则：

> 能放进现有 6 个 Harness 文件，就不要提前抽象。

---

# 7. 各目录职责

## `tests/`

回答：

> 测什么？

它是整个项目最重要的目录。

每个 test 包含任务、输入数据、hidden expected 和数据生成逻辑。

---

## `harness/`

回答：

> 怎么组织、运行和评分这些测试？

Harness 必须保持轻量。

---

## `scripts/`

回答：

> 具体怎么启动某个 CLI Agent？

Harness 不应硬编码 Codex。

使用：

```bash
--agent-cmd "python scripts/run_codex.py"
```

以后如果需要 Claude Code，再增加：

```text
scripts/run_claude.py
```

不要提前设计复杂 Agent Adapter class hierarchy。

---

## `tests_harness/`

回答：

> Benchmark 自己有没有 bug？

它不是水文测试集，而是 Harness 的软件单元测试。

---

# 8. 单个 Test 的标准结构

严格采用接近 BioTaskBench 的模式：

```text
tests/model-calibration/hydromodel-003/
├── task.json
├── generate_data.py
├── data/
│   ├── forcing.csv
│   ├── observed.csv
│   └── parameter_ranges.json
└── expected/
    ├── hidden_validation.csv
    └── grading_targets.json
```

## `task.json`

定义：

- 测试目标；
- Agent 可见任务描述；
- 输入文件；
- 所测试 Skill；
- expected outputs；
- grading criteria。

## `generate_data.py`

负责：

- 生成 synthetic data；
- 下载或裁剪公开数据；
- 生成 hidden truth；
- 生成 expected；
- 固定随机种子；
- 保证任务可复现。

## `data/`

允许复制给 Agent。

## `expected/`

严禁复制给 Agent。

只允许 grader 访问。

---

# 9. `task.json` 保持简洁

参考结构：

```json
{
  "id": "hydromodel-003",
  "title": "Calibrate a rainfall-runoff model",
  "domain": "model-calibration",
  "difficulty": "intermediate",
  "primary_skill": "model-calibration",
  "secondary_skills": [],
  "prompt": "Calibrate the supplied rainfall-runoff model using the provided observations and produce the requested outputs.",
  "data_description": "Synthetic rainfall-runoff calibration problem.",
  "data_files": [
    "forcing.csv",
    "observed.csv",
    "parameter_ranges.json"
  ],
  "required_outputs": [
    "parameters.json",
    "simulation.csv"
  ],
  "setup_notes": [
    "Required scientific tools are pre-installed.",
    "Do not install additional software unless necessary."
  ],
  "timeout_seconds": 600,
  "grading": [
    {
      "name": "simulation_output",
      "type": "file_check",
      "target": "simulation.csv",
      "weight": 0.10
    },
    {
      "name": "hydrograph_fit",
      "type": "hydro_metric",
      "metric": "KGE",
      "target": "simulation.csv",
      "reference": "expected/hidden_validation.csv",
      "weight": 0.45
    },
    {
      "name": "volume_bias",
      "type": "hydro_metric",
      "metric": "PBIAS",
      "weight": 0.25
    },
    {
      "name": "parameter_validity",
      "type": "range_check",
      "weight": 0.20
    }
  ]
}
```

第一版只额外增加与 BioTaskBench 相比真正必要的 Skill 字段：

```text
primary_skill
secondary_skills
```

不要额外建立独立 `skill_coverage.yaml`。

Harness 通过扫描所有 `task.json` 自动反向得到 Skill → Tests 关系。

保持 single source of truth。

---

# 10. Domain

第一版只使用三个 domain：

```text
data-preprocessing
model-calibration
results-analysis
```

这些只是 Level-1 Task 的分类标签。

它们不是 Level-2 Pipeline 实现。

---

# 11. Difficulty

参考 BioTaskBench，只保留：

```text
basic
intermediate
advanced
```

定义：

## Basic

标准、明确、方法基本确定的任务。

主要测试 Agent 能否正确执行已有专业流程。

## Intermediate

需要明显水文领域推理，例如：

- 异常类型判断；
- 时间尺度处理；
- 参数选择；
- 多指标综合；
- 物理合理性判断。

## Advanced

需要：

- 多步骤推理；
- 多工具操作；
- 优化；
- 隐式约束；
- 多目标权衡；
- 更强的专业诊断。

不要按代码行数定义 difficulty。

---

# 12. Harness 文件职责

## `harness/cli.py`

只负责 CLI argument parsing。

第一版只需要：

```bash
hydroSkillBench validate
hydroSkillBench run
hydroSkillBench compare
hydroSkillBench regrade
```

不要先做：

```text
list
dashboard
export
stability server
web UI
```

CLI 优先使用标准库 `argparse`，避免引入不必要 CLI framework。

---

## `harness/runner.py`

职责仅限：

```text
发现 Task
↓
读取并验证 task.json
↓
创建 fresh workspace
↓
复制允许的 data 文件
↓
设置环境变量
↓
启动 --agent-cmd
↓
等待 / timeout
↓
记录 stdout / stderr / exit code
↓
调用 grader
↓
保存 result
```

即使 Agent 返回非零 exit code，也必须继续尝试 grade 已经产生的 artifacts。

---

## `harness/grader.py`

第一版所有 grader 都先放在一个文件中。

不要提前拆成复杂 registry/package。

例如：

```python
def grade_file_check(...):
    ...

def grade_column_check(...):
    ...

def grade_range_check(...):
    ...

def grade_numeric_correlation(...):
    ...

def grade_hydro_metric(...):
    ...

def grade_timeseries_match(...):
    ...

GRADERS = {
    "file_check": grade_file_check,
    "column_check": grade_column_check,
    "range_check": grade_range_check,
    "numeric_correlation": grade_numeric_correlation,
    "hydro_metric": grade_hydro_metric,
    "timeseries_match": grade_timeseries_match,
}
```

然后统一：

```python
def grade_task(...):
    ...
```

未来 grader.py 真正变得难以维护时再拆。

---

## `harness/reporter.py`

负责：

```text
Task Score
Skill Score
Domain Score
Difficulty Score
Overall Score
Coverage
No-Skill vs With-Skill comparison
```

不要额外创建 comparator.py。

`compare` 逻辑可以直接放 reporter.py。

---

## `harness/schemas.py`

保持简单。

不使用 Pydantic。

实现类似：

```python
def validate_task(task, task_dir):
    ...
```

至少检查：

- id 是否存在且唯一；
- domain 是否合法；
- difficulty 是否合法；
- primary_skill 是否存在；
- data_files 是否存在；
- required_outputs 是否合理；
- grader type 是否已实现；
- grading weights 是否总和为 1；
- reference/expected target 是否存在。

---

# 13. 第一版 Grader 类型

优先复用 BioTaskBench 风格的通用 grader，再增加少量水文 grader。

## Generic

至少支持：

```text
file_check
column_check
exact_match
range_check
set_overlap
numeric_correlation
code_executes
```

---

## Hydrology-specific

第一版只实现真正需要的：

```text
hydro_metric
timeseries_match
peak_check
volume_check
water_balance_check
parameter_range
```

不要第一版就实现大量 GIS / raster grader，除非示例 Task 真正需要。

---

# 14. `hydro_metric`

至少支持：

```text
NSE
KGE
PBIAS
RMSE
MAE
R²
```

不要把 raw metric 直接作为 0–1 Task criterion score。

允许 task.json 定义简单 normalization。

例如：

```json
{
  "type": "hydro_metric",
  "metric": "KGE",
  "scoring": {
    "zero_at": 0.2,
    "one_at": 0.8
  }
}
```

中间线性插值并 clip 到 0–1。

避免把大量水文阈值硬编码在 grader.py。

---

# 15. Calibration Task 的特殊原则

水文参数率定存在 equifinality。

因此不要把：

```text
estimated parameters == hidden true parameters
```

作为主要评分标准。

主要评价：

```text
hydrograph performance
hidden validation performance
water balance
peak reproduction
volume reproduction
parameter physical range
```

hidden true parameter 可以作为辅助诊断，不应默认作为主分数。

---

# 16. Hidden validation 必须被原生支持

框架应支持这种测试：

Agent 可见：

```text
calibration forcing
calibration observations
validation forcing
```

Agent 不可见：

```text
validation observations
```

Agent：

```text
calibrate
→ freeze parameters
→ run validation forcing
→ output validation_sim.csv
```

grader：

```text
validation_sim.csv
vs
expected/hidden_validation_obs.csv
```

这是验证 HydroTune-skills 是否真正提升专业泛化能力的重要模式。

---

# 17. Continuous scoring 优先

尽量避免：

```text
KGE >= 0.7 → 1
KGE < 0.7 → 0
```

优先：

```text
KGE <= 0.2 → 0
KGE >= 0.8 → 1
中间线性插值
```

类似地：

```text
|PBIAS| <= 5% → 1
|PBIAS| >= 40% → 0
中间线性插值
```

保证 Task Score 能反映部分完成质量。

---

# 18. Coverage 和 Score 分离

至少报告：

```text
tests_total
tests_attempted
coverage
score_attempted
score_overall
```

建议：

```text
coverage = attempted / total
```

attempted 定义为：

> 至少产生一个该 Task 要求的主要 artifact。

```text
score_attempted = mean(score of attempted tasks)
```

```text
score_overall = sum(all task scores) / total
```

没有任何可评分 artifact：

```text
score = 0
```

不要把：

```text
score > 0
```

命名为“完全成功”。

---

# 19. Skill-level aggregation

这是 HSQB 相比普通水文 benchmark 最重要的新增逻辑。

每个 Task 在 `task.json` 中声明：

```text
primary_skill
```

因此 reporter 可以自动聚合：

```text
hydrodata-001 ─┐
hydrodata-002 ─┼→ meteorological-qc score
hydrodata-003 ─┘

hydromodel-de-001 ─┐
hydromodel-de-002 ─┼→ calibrate-model-de score
hydromodel-de-003 ─┘
```

定义：

```text
Skill Score = mean(Task Scores whose primary_skill == this skill)
```

第一版不要创建独立 skill coverage 配置文件。

---

# 20. No-Skill vs HydroTune-skills A/B

必须支持：

```bash
hydroSkillBench run \
  --agent-cmd "python scripts/run_codex.py" \
  --output results/no-skills
```

以及：

```bash
hydroSkillBench run \
  --agent-cmd "python scripts/run_codex.py" \
  --skills-path /path/to/HydroTune-skills \
  --output results/with-skills
```

然后：

```bash
hydroSkillBench compare \
  results/no-skills \
  results/with-skills
```

输出至少包括：

```text
Overall Score
Domain Score
Skill Score
Task Score
Coverage
Absolute uplift
```

例如：

```text
model-calibration

No Skill      0.41
With Skill    0.73
Δ            +0.32
```

Skill uplift 是本项目最重要的结果之一。

---

# 21. 不要把 HydroTune-skills 名字硬编码进 Harness

Harness 参数保持通用：

```text
--skills-path
```

但在 run metadata 中记录：

```json
{
  "skill_suite": "HydroTune-skills",
  "skills_path": "...",
  "skill_condition": "with-skills"
}
```

原因：

- 可以比较 HydroTune-skills v1 / v2；
- Harness 代码保持干净；
- 以后可以用于消融实验。

---

# 22. `scripts/run_codex.py`

参考 BioTaskBench 的 Agent wrapper 设计。

它负责：

1. 读取当前 Task 信息；
2. 在 workspace 中生成 Codex 可读取的任务说明，例如 `AGENTS.md`；
3. 如果设置了 `BENCHMARK_SKILLS_PATH`，以 Codex 原生 Skill 目录方式暴露 HydroTune-skills；
4. 启动 Codex CLI；
5. 让 Codex 在当前 workspace 中完成任务。

Harness 本身不应该知道 Codex 的 Skill 目录细节。

建议 runner 通过环境变量提供：

```text
HSQB_TASK_JSON
HSQB_TEST_DIR
HSQB_WORKSPACE
BENCHMARK_MODEL
BENCHMARK_EFFORT
BENCHMARK_SKILLS_PATH
```

---

# 23. CLI 第一版

## Validate

```bash
hydroSkillBench validate
```

验证所有 Task：

- JSON 格式；
- data；
- expected；
- grader；
- weights；
- primary_skill。

---

## Run

全部：

```bash
hydroSkillBench run \
  --agent-cmd "python scripts/run_codex.py" \
  --output results/run01
```

单 domain：

```bash
hydroSkillBench run \
  --domain model-calibration \
  --agent-cmd "python scripts/run_codex.py"
```

单 Task：

```bash
hydroSkillBench run \
  --test-id hydromodel-003 \
  --agent-cmd "python scripts/run_codex.py"
```

按 Skill：

```bash
hydroSkillBench run \
  --skill model-calibration \
  --agent-cmd "python scripts/run_codex.py"
```

支持：

```text
--model
--effort
--skills-path
--timeout
--workspace-root
--output
```

---

## Compare

```bash
hydroSkillBench compare RUN_A RUN_B
```

主要用于 No-Skill / With-Skill paired comparison。

---

## Regrade

```bash
hydroSkillBench regrade results/run01
```

使用当前 grader 重新评分已有 workspace，不重新运行 Agent。

---

# 24. 第一版不要实现 `--repeats`

与 BioTaskBench 一样：

> 一次 benchmark run 中，每个 Task 默认执行 1 次。

如果论文实验需要 3 次或 5 次重复，就运行多个独立 run：

```text
run01
run02
run03
```

第一版 Harness 不承担完整实验重复管理。

保持实现简单。

未来有明确需要时再增加 stability 分析。

---

# 25. Run 输出

建议：

```text
results/run01/
├── run_metadata.json
├── summary.json
└── tasks/
    └── hydromodel-003/
        ├── result.json
        ├── execution.json
        ├── stdout.log
        ├── stderr.log
        └── workspace/
```

运行结束后保留 workspace，便于：

- audit；
- debugging；
- regrade；
- 论文结果检查。

`results/` 加入 `.gitignore`，不需要提交空目录。

---

# 26. Result schema

示例：

```json
{
  "test_id": "hydromodel-003",
  "domain": "model-calibration",
  "difficulty": "intermediate",
  "primary_skill": "model-calibration",
  "attempted": true,
  "score": 0.81,
  "criteria": {
    "simulation_output": {
      "raw_value": 1,
      "score": 1.0
    },
    "hydrograph_fit": {
      "raw_value": 0.78,
      "score": 0.83
    }
  },
  "execution": {
    "return_code": 0,
    "timed_out": false
  }
}
```

---

# 27. 初始示例 Task

不要第一版就实现几十个真实复杂 Task。

先实现 3 个 synthetic example tests，用于证明整个 Harness 正常工作。

## `hydrodata-001`

主要 Skill：

```text
meteorological-qc
```

输入 synthetic precipitation time series，其中包含：

```text
duplicate timestamps
negative precipitation
known missing records
```

要求 Agent 输出：

```text
cleaned.csv
qc_flags.csv
```

grader：

```text
file/schema
anomaly detection F1
cleaned series numerical match
```

---

## `hydromodel-de-001`

主要 Skill：

```text
model-calibration/calibrate-model-de
```

提供一个带显式边界、目标方向、率定/验证 split、seed 和完整 DE 配置的确定性率定问题。

提供：

```text
calibration-problem.json
optimizer-config.json
fixture.json
synthetic_adapter.py
```

Agent 输出：

```text
best_parameters.json
calibration_trace.csv
calibration_metrics.json
validation_metrics.json
calibration_series.csv
validation_series.csv
result.json
```

grader：

```text
parameter and trace match
split metrics and series match
status and termination semantics
artifact path and SHA-256 integrity
```

validation 不得参与搜索或参数选择。

---

## `hydroanalysis-001`

主要 Skill：

```text
hydrologic-diagnostics
```

提供：

```text
observed.csv
simulated.csv
```

人工构造一个明确 pathology，例如：

```text
systematic peak timing delay
```

要求输出：

```text
metrics.json
diagnosis.json
```

grader：

```text
NSE/KGE/PBIAS numerical accuracy
peak timing error
primary diagnosis category match
```

---

# 28. tests_harness

至少测试：

```text
task loading
task validation
hidden expected isolation
workspace creation
agent execution
timeout
nonzero exit code
partial artifact grading
criterion weighting
score clipping
coverage
regrade
compare
skill filtering
domain filtering
result serialization
```

尤其确保：

```text
expected/
```

不会进入 Agent workspace。

---

# 29. pyproject.toml

项目使用：

```text
Python >= 3.11
```

尽量减少核心依赖。

推荐核心只需要：

```text
numpy
pandas
scipy
pytest
```

如无必要，不引入大型 framework。

CLI 使用标准库 `argparse`。

提供 console script：

```text
hydroSkillBench = harness.cli:main
```

GIS heavy dependencies 第一版不要加入核心安装。

---

# 30. README 必须承担主要文档职责

第一版不创建独立 `docs/`。

README 至少说明：

```text
What HSQB is
What HSQB is not
Relationship with HydroTune-skills
Why Task-level Skill evaluation
Project structure
Task format
Grading model
Run without Skills
Run with HydroTune-skills
Compare
Regrade
How to add a new Task
How to add a new grader
Result interpretation
```

如果未来 README 明显过长，再拆 docs。

---

# 31. 开发顺序

不要一次性铺很大。

## Phase 1 — 分析 BioTaskBench

先阅读并总结：

```text
harness/runner.py
harness/grader.py
harness/reporter.py
harness/schemas.py
harness/cli.py
scripts/run_codex.py
tests/*/*/task.json
```

输出简短设计说明：

- 哪些模式直接借鉴；
- 哪些不适合 HSQB；
- HSQB 为什么只增加 `primary_skill` / Skill aggregation / hydrology graders。

## Phase 2 — Skeleton

创建最小项目骨架。

## Phase 3 — Harness core

实现：

```text
schemas
runner
grader
reporter
cli
run_codex
```

## Phase 4 — Three example tasks

实现前述 3 个 synthetic examples。

## Phase 5 — Harness tests

完成 tests_harness。

## Phase 6 — README and cleanup

确保项目简单、可读、可复现。

---

# 32. 验收标准

完成后必须能够执行：

```bash
pytest
```

并通过 Harness 测试。

然后：

```bash
hydroSkillBench validate
```

通过全部示例 Task。

然后能跑单题：

```bash
hydroSkillBench run \
  --test-id hydrodata-001 \
  --agent-cmd "python scripts/run_codex.py" \
  --output results/test-run
```

然后：

```bash
hydroSkillBench regrade results/test-run
```

成功。

并支持：

```bash
hydroSkillBench compare \
  results/no-skills \
  results/with-skills
```

输出 Task、Skill、Domain、Overall 的差异。

---

# 33. 最终工程原则

始终遵循：

```text
Task-rich
Harness-light
```

HSQB 的重点不是创造一个通用 Agent evaluation framework。

重点是：

```text
HydroTune Skill
      ↓
multiple atomic tests
      ↓
CLI Agent
      ↓
scientific artifacts
      ↓
deterministic hydrology grader
      ↓
Task Score
      ↓
Skill Score
      ↓
No-Skill vs With-Skill uplift
```

如果一个新 abstraction、directory、class hierarchy 或 dependency 不能直接帮助以上流程，就不要在 v0.1 中加入。

最终代码风格和目录组织应尽量保持接近 BioTaskBench 的轻量、直接、可审计特征。

