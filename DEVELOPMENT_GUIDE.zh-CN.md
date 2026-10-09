# HSQB Benchmark 通用测试开发指南

本文档规定如何从给定的 HydroTune Skill 目录读取能力契约，并在本仓库中开发可复现的 benchmark tests。它适用于现有的 `hydrodata`、`hydromodel`、`hydroanalysis`，也适用于未来新增的任何测试家族。流程来自数据处理、空间分析、模型率定和结果诊断任务的实际开发经验。

本流程只用于**测试开发与本地验收**。开发过程中禁止运行任何真实 Agent。

原子题遵循下文的单技能隔离规则。`composite_tests/` 的 `hydrochain-data`、
`hydrochain-model`、`hydrochain-analysis` 家族遵循独立的
[组合开发规则](composite_tests/DEVELOPMENT_RULES.md)：允许真实处理链，必要事实和权限
在启动前提供，运行中不补充用户信息，要求至少三种核心科学能力和成果依赖，提示不得点名 Skill。组合题不改变
原子覆盖口径，两类开发阶段都禁止运行真实 Agent。

## 1. 核心原则

1. 一题只测试一个目标 Skill；上游链路通过预置、哈希有效的 artifacts 隔离。
2. 一题只引入一个主要变量，避免错误优先级遮蔽待测行为。
3. Prompt 明确已经确认的列、单位、CRS、时区、阈值、sheet、出口数和 QC 策略，禁止 Agent 猜测。
4. 评分 artifacts，不评分自然语言回答。
5. Golden 必须确定、可复现，并与真实 Skill 脚本交叉验证。
6. 错误题保留原生 `result.json`，并检查禁止交付的正常成果不存在。
7. 外部 Skill 目录只读；测试、输入、oracle 和 grader 都放在本仓库。

## 2. 开发阶段禁止运行实际 Agent

开发期间禁止：

- `hydroSkillBench run ...`
- `python scripts/run_codex.py ...`
- `codex exec ...`
- 任何带 `--agent-cmd` 或 `--skills-path` 的 benchmark run
- 创建或续跑 with-skills、no-skills、Agent smoke run 或其他 Agent 批次
- 通过桌面任务、子任务或其他模型代替 CLI Agent 执行测试

允许：读取 Skill 文件、运行确定性的 Skill Python 示例脚本、运行生成器、调用 grader、执行 `python -m pytest` 和 `hydroSkillBench validate`。

这项限制只适用于测试的开发、调试和本地验收阶段。开发完成并通过本指南的验收清单后，任务仍然必须能够由 `hydroSkillBench run` 正常执行；届时可以在单独的正式评测阶段运行 with-skills、no-skills 和配对比较。开发指南不会禁用、删除或绕过项目的 Agent runner。

开发计划、进度说明和完成报告都应明确写出：**开发阶段未运行实际 Agent 批次**。

## 3. Skill 路径与发现

默认 Skill 根目录：

```text
E:\HydroTune-Skills（仿BioSkills版）
```

调用者既可以传入根目录，也可以直接传入某个 Skill 目录。路径处理规则：

1. 去掉输入首尾的引号和空格，不把尾随空格视为目录名的一部分。
2. 环境变量 `HYDROTUNE_SKILLS_ROOT` 优先于默认目录。
3. `task.json.primary_skill` 使用相对 Skill 根目录的规范引用，例如：

```text
data-processing/prepare-discharge-timeseries
spatial-analysis/build-hydrological-topology
```

4. `primary_skill` 禁止写绝对路径或 Codex 安装后的本地 Skill 名称。
5. 生成器可以借助 `HYDROTUNE_SKILLS_ROOT` 查找真实脚本，但提交后的 `data/`、`expected/` 和评分流程不得依赖外部目录才能读取。

## 4. 必须读取的 Skill 资料

对每个目标 Skill，依次完整读取：

1. `SKILL.md`
2. `usage-guide.md`（如有）
3. `data-contract.yaml`（如有）
4. `examples/` 中对应的 Python 脚本
5. Skill 仓库内相关测试或 fixture（如有）

读取后先整理契约：

| 项目 | 必须记录的内容 |
|---|---|
| Skill 引用 | `primary_skill` 的精确字符串 |
| 输入 | 文件、字段、单位、CRS、时区、哈希、上游状态 |
| 用户确认项 | 不能猜测或没有默认值的参数 |
| 输出 | 文件名、目录、格式、关键列和 artifact key |
| 状态 | `success`、`warning`、`error` 的触发条件 |
| 停止条件 | 输入错误、证据不足、科学 QC 失败等 |
| 退出码 | 成功、普通错误、科学 QC 错误 |
| 不变量 | 守恒、规则步长、网格一致、拓扑互反等 |
| 禁止行为 | 猜测、自动修复、降低阈值、回退参数等 |
| 非目标能力 | 本组明确不覆盖的功能 |

如果文档与真实脚本不一致，先记录差异，再在测试契约中明确选择；不得静默掩盖。

## 5. Domain、目录和命名

当前 domain：

```text
data-preprocessing
spatial-analysis
model-calibration
results-analysis
visualization-reporting
```

任务路径统一为：

```text
tests/<domain>/<task-id>/
```

任务 ID 按测试家族选择前缀：

| 测试家族 | 适用范围 | 命名形式 | 当前示例 |
|---|---|---|---|
| `hydrodata` | 数据整理、事件、空间输入和其他模型前数据 | `hydrodata-<capability>-NNN` | `hydrodata-timeseries-001` |
| `hydromodel` | 模型构建、运行、率定和模型参数任务 | `hydromodel-NNN`；同域出现多个明确子能力时可用 `hydromodel-<capability>-NNN` | `hydromodel-de-001` |
| `hydroanalysis` | 指标计算、结果诊断和模拟分析 | `hydroanalysis-NNN`；同域出现多个明确子能力时可用 `hydroanalysis-<capability>-NNN` | `hydroanalysis-001` |
| 未来家族 | 无法归入现有家族的新任务 | 先确定稳定的 `hydro<family>` 前缀，再使用 `hydro<family>-NNN` 或 `hydro<family>-<capability>-NNN` | 尚无 |
| `hydrovisual` | 固定图册和结果绘图 | `hydrovisual-<capability>-NNN` | `hydrovisual-dem-atlas-001` |
| `hydroreport` | 结构化报告生成及独立审查 | `hydroreport-<capability>-NNN` | `hydroreport-review-001` |

通用规则：

- 前缀和 `<capability>` 使用稳定、简短的小写连字符名称。
- `NNN` 从 `001` 连续编号，同一任务组不跳号。
- 名称描述任务家族或能力，不描述某一道题的具体异常。
- 优先延续同一 domain 已有的命名方式，不能把所有新任务都强制命名为 `hydrodata-*`。
- 不复用已经删除或转为模板的可执行 ID。

现有 `hydrodata` 能力名包括 `timeseries`、`baseflow`、`flood-events`、`dem-grid`、`stream-network`、`topology-build` 和 `topology-validate`；模型和分析任务分别使用 `hydromodel` 与 `hydroanalysis` 家族。

新增 domain 时同时修改 `harness.schemas.DOMAINS`、发现测试、中英文 README，并创建该 domain 的 `TESTS.zh-CN.md`。

非运行模板放入 `examples/tasks/<template-id>/`，使用 `task.example.json`；模板目录不能包含 `task.json`。

## 6. 测试矩阵设计

每组至少考虑：

- **Success**：最小完整输入和一个非平凡科学案例。
- **Warning**：成果仍可用，但风险证据必须保留或从上游传播。
- **Error**：普通输入拒绝和按需单独覆盖的科学 QC 失败。

奇怪输入可从以下候选中选择：

- 缺失、重复、乱序、非数值、负值、非有限值。
- 恰好达到上限、刚超过上限、零值、极端值。
- 错误或缺失 CRS、时区、单位、sheet、字段或配置项。
- 不规则步长、边缘缺测、内部长缺口。
- 多出口、循环、自环、悬空引用、层级不一致。
- 栅格错位、非正方形像元、多波段、NoData、空网络。
- 有候选但被最终阈值全部筛除。
- 上游 warning/error 或 artifact 哈希错误。

每个失败任务只放一个主要异常，并确认它确实是脚本遇到的第一个主要失败原因。

## 7. 固定任务结构

```text
tests/<domain>/<task-id>/
├── task.json
├── generate_data.py
├── data/                       # Agent 可见
└── expected/
    └── golden_workspace/       # 仅 grader 可见
```

同组任务使用共享 factory；文件名按任务家族或能力命名：

```text
tests/<domain>/_<task-family>_task_factory.py
```

每题的 `generate_data.py` 只导入共享 factory 并传入当前 ID。禁止在几十个任务中复制生成逻辑。

## 8. task.json 规范

必填字段：

```text
id, title, domain, difficulty, primary_skill, prompt,
data_files, required_outputs, timeout_seconds, grading
```

建议始终显式填写 `secondary_skills`、`data_description` 和 `setup_notes`。

### Prompt

必须写清：输入入口、确认参数、允许的修复、禁止行为、输出目录与格式，以及错误时是否清理部分成果。不得泄漏 hidden expected、golden 数值或 grader 权重。

### data_files

- 相对于 `data/`。
- 逐个列出实际文件，包括 Shapefile sidecars 和嵌套上游 artifacts。
- 禁止绝对路径和 `..`。

### required_outputs

- 相对于 Agent workspace。
- 正常和 warning 题列出全部正式成果。
- 普通 error 题通常只列出 `<output-dir>/result.json`。
- 科学 QC 失败若按契约仍生成检查表、报告或图，这些文件仍应列出。

### secondary_skills

上游 artifacts 已预置时使用空列表。只有 Agent 在本题确实需要运用另一个 Skill 时才填写，不要因为数据来源于上游 Skill 就自动填写。

## 9. Fixture 和上游 artifact

### 确定性要求

- 固定随机种子、时间戳、CRS、仿射变换和 NoData。
- JSON 使用 UTF-8、稳定缩进和排序键。
- CSV 固定列顺序、换行和浮点格式。
- XLSX 固定 workbook 元数据。
- GeoPackage 固定 `gpkg_contents.last_change`，必要时执行 SQLite `VACUUM`。
- ID、列表和文件名按稳定规则排序。

### 上游 artifacts

预置上游成果包括正式数据、metadata、原生 `result.json`、相对 artifact 路径和真实 SHA-256。除专门的篡改题外，不得写占位哈希或伪造成功状态。

### 二进制文件

GeoPackage、GeoTIFF、PNG 和 XLSX 应尽量固定元数据，但评分优先比较科学语义。候选 `result.json` 中的 SHA-256 必须匹配候选文件自身，不要求等于 golden 二进制文件哈希。

## 10. Golden oracle

可使用：

1. 独立、确定性的公式实现；或
2. 真实 Skill Python 脚本生成，再用独立不变量和 grader 检查。

无论哪种方式，golden 必须提交到本仓库，正常评分不依赖外部 Skill 目录。不要评分绝对路径、动态 provenance 或外部工具安装位置；重点评分稳定的 status、parameters、checks、warnings、表格、栅格、矢量和科学不变量。

## 11. Grader 选择

| 成果 | 推荐 grader |
|---|---|
| 文件存在/表结构 | `file_check` |
| 禁止文件不存在 | `file_absence_check` |
| JSON/YAML 字段 | `exact_match`、`range_check` |
| CSV/TSV | `table_match` |
| 时序和水文指标 | `hydro_metric`、`timeseries_match`、`peak_check`、`volume_check` |
| 参数范围 | `parameter_range` |
| GeoTIFF | `raster_match` |
| GeoPackage/矢量 | `vector_match` |
| artifact 路径与哈希 | `artifact_reference_check` |
| 图件尺寸、元数据、SVG科学图层 | `figure_contract_check` |
| 报告证据、受控结论、逐段审查绑定 | `report_contract_check` |

正常题覆盖文件结构、核心科学内容、metadata/parameters/checks、status/warnings 和 artifact 完整性。错误题覆盖 `status=error`、原生原因、artifact map 和禁止成果缺失。

新增 grader 时必须：在 `harness/grader.py` 实现并注册、加入 `harness.schemas.GRADER_TYPES`、编写成功/偏差/缺失/安全边界单测、更新中英文 README。所有 criterion 权重之和严格为 `1.0`。

## 12. 真实 Skill 脚本验证

真实脚本验证不是 Agent 测试。标准流程：

1. 把任务 `data/` 复制到临时 workspace。
2. 使用 prompt 中确认的参数直接运行目标 Skill Python 脚本。
3. 检查预期退出码。
4. 按任务契约清理脚本报错前留下、但不允许交付的部分成果。
5. 调用 harness grader，要求得分 `1.0`。

空间任务示例：

```powershell
python scripts/verify_spatial_tasks.py `
  --skills-root "E:\HydroTune-Skills（仿BioSkills版）"
```

新组验证器命名为 `scripts/verify_<task-family>_tasks.py`。验证器只能运行确定性工具，禁止在开发阶段调用 `hydroSkillBench run`、`run_codex.py` 或任何 Agent。

## 13. Harness 自测与文档

至少增加：

- 任务数量、连续 ID 和 Skill/domain 发现测试。
- 整组 golden workspace 满分测试。
- 新 grader 的成功、失败与边界测试。
- 模板不被发现的测试。
- 错误题文件缺失测试；空文件仍视为存在。

每次新增任务组同步更新：

- `README.md`
- `README.zh-CN.md`
- 对应 domain 的 `TESTS.zh-CN.md`

`TESTS.zh-CN.md` 应逐题写明输入情景、主要测试点、预期 status/退出码和成果规则。

## 14. 推荐实施顺序

1. 完整读取 Skill 说明、契约、示例和相关测试。
2. 检查现有 domain、grader 和依赖。
3. 先写测试矩阵，锁定任务前缀和题数。
4. 实现共享 fixture factory。
5. 生成薄 `generate_data.py`、输入和 golden。
6. 编写 `task.json` 与评分规则。
7. 让每个 golden workspace 得分为 `1.0`。
8. 增加真实脚本临时 workspace 验证。
9. 增加 harness 单测与发现测试。
10. 更新 README 和 `TESTS.zh-CN.md`。
11. 连续运行生成器两次并比较稳定性。
12. 完成本地验收。

不要先批量生成任务再补科学定义；测试矩阵和 Skill 契约必须先确定。

## 15. 最终验收

```powershell
conda activate HydroTune-eval
python -m pytest
hydroSkillBench validate
```

按需运行对应的真实脚本验证器。**不要执行 `hydroSkillBench run`。**

完成检查：

- [ ] 已完整读取 Skill 资料并记录契约。
- [ ] `primary_skill` 是规范相对引用。
- [ ] ID 符合所属家族的命名形式（如 `hydrodata-*`、`hydromodel-*`、`hydroanalysis-*`）且连续。
- [ ] 每题只有一个主要行为或异常。
- [ ] Prompt 明确科学确认和禁止行为。
- [ ] 上游 artifacts 使用相对路径和真实 SHA-256。
- [ ] `data/` 不含 hidden expected。
- [ ] 每个 golden workspace 得分为 `1.0`。
- [ ] 生成器连续运行两次无文本或科学语义漂移。
- [ ] 真实 Skill 脚本在临时 workspace 中通过。
- [ ] `python -m pytest` 全部通过。
- [ ] `hydroSkillBench validate` 通过。
- [ ] README 与 domain 测试说明已更新。
- [ ] 开发阶段未运行实际 Agent 测试，同时没有破坏正式 Agent runner 的可执行性。

## 16. 完成报告模板

```markdown
已新增 <数量> 个 `<task-family>` 测试：

- success：<数量>
- warning：<数量>
- error：<数量>
- golden workspace：全部 1.0
- 真实 Skill 脚本交叉验证：全部通过
- pytest：<数量> passed
- hydroSkillBench validate：通过
- 生成器重复运行：无语义漂移
- 开发阶段实际 Agent 批次：未运行
- 正式 Agent 评测兼容性：保留，可在开发验收后运行
```

## 原子三组公共契约补充规则

原子三组实验版本为 `atomic-three-arm-v1`，操作与当前验收结果见 `docs/ATOMIC_THREE_ARM.zh-CN.md`。
公开合同只从冻结源数据合同、序列化接口和公开输入生成；不得从 hidden expected 或评分容差生成答案。
所有原子生成器必须保留 `public_contract` 引用并将 canonical 契约复制到临时生成目录。
`scripts/prepare_atomic_contracts.py` 不改输入、参考、评分或超时；`scripts/audit_atomic_contracts.py` 核对基线及字段遗漏。
科学代码和运行资产若只存在于技能组，则不得发布：必须在公共程序组提供同哈希版本，或阻断实验。
原程序、旧题及评分之间的冲突必须记录；不得补造缺测、选择预期分支或放宽 grader。
本机联调不算容器隔离认证。开发验收只使用可信科学程序、假进程和无模型容器探针；不启动真实 Agent 批次。
