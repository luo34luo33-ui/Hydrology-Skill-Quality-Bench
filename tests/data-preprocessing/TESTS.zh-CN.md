# 数据预处理测试说明

本文档说明 `tests/data-preprocessing/` 中当前每个 benchmark task 主要在测试什么，便于审查覆盖面、定位失败原因和设计新题。实际执行和评分仍以各任务的 `task.json`、`data/` 与 `expected/` 为准；本文档不是评分配置。

## 目录约定

每个可执行任务通常包含：

- `task.json`：任务提示、Skill、必需输出和评分规则。
- `generate_data.py`：确定性生成输入数据与 golden workspace。
- `data/`：Agent 能看到的输入。
- `expected/`：评分器使用的预期结果或隐藏参考。

失败场景通常只要求生成原生 `result.json`，并检查正常成果文件没有被错误创建。

## 流量时序标准化

目标 Skill：`data-processing/prepare-discharge-timeseries`

这一组测试覆盖时间解析、时区、单位换算、缺测、重复值、规则步长和最小数据量等输入质量问题。成功或警告场景输出到 `prepared/`；拒绝场景不得生成标准时序与 metadata。

| 测试 ID | 输入情景 | 主要测试点 | 预期 |
|---|---|---|---|
| `hydrodata-timeseries-001` | UTC 小时时序被打乱，流量单位为 `cfs`，含附加列 `source_id` | 按时间排序；转为 `Asia/Shanghai`；`cfs` 换算为 `m3/s`；附加列必须跟随原记录而不是错位 | `success` |
| `hydrodata-timeseries-002` | XLSX 中包含目标 sheet、干扰 sheet、Excel serial 日期和 `L/s` 流量 | 只读取指定 sheet；正确解释 Excel 日期；换算为 `m3/s`；保留 `quality_code`；记录 naive 时区风险 | `warning` |
| `hydrodata-timeseries-003` | 序列内部恰有两个连续缺测点 | 在已授权的 2 小时上限内做线性插值；只把补出的行标记为 `is_imputed=true` | `warning` |
| `hydrodata-timeseries-004` | 开头两个、结尾三个流量值缺失 | 只裁切边缘缺测；禁止首尾外推；保留剩余行的 `sensor_state` | `warning` |
| `hydrodata-timeseries-005` | 一个时间戳重复且两行流量不同 | 按文件顺序保留最后一条；不能排序后误判“最后”记录；保留对应 `sample_id` | `warning` |
| `hydrodata-timeseries-006` | 重复时间戳，但没有授权去重策略 | 使用默认拒绝策略；不能擅自保留第一条、最后一条或聚合 | `error` |
| `hydrodata-timeseries-007` | 三个连续内部缺测点，超过 2 小时上限 | 整个缺口拒绝；不能只填其中一部分 | `error` |
| `hydrodata-timeseries-008` | 单点偏移造成 90/30 分钟相邻步长 | 识别不规则时间步长；禁止重采样、改时间或拆分序列 | `error` |
| `hydrodata-timeseries-009` | 含负流量 | 识别物理无效值；禁止删除、截断为零或替换 | `error` |
| `hydrodata-timeseries-010` | 内部流量字段含非数值文本 | 数值解析后按内部缺测处理；在未授权插值时拒绝 | `error` |
| `hydrodata-timeseries-011` | 一个时间字符串无法解析 | 报告无效时间；禁止丢行或猜测日期 | `error` |
| `hydrodata-timeseries-012` | 只有 9 个有效规则点 | 执行最小有效点数约束；禁止补点、复制或合成记录 | `error` |

评分重点包括：标准表逐行内容、时间排序与规范化、数值容差、布尔标记、附加列对齐、metadata、原生状态和错误场景下的文件缺失。

## Eckhardt 基流分割

目标 Skill：`data-processing/separate-baseflow-eckhardt`

这一组直接提供已经校验且哈希有效的上游 `prepared/` artifacts，只测试基流分割 Skill。正常成果写入 `components/`。

| 测试 ID | 输入情景 | 主要测试点 | 预期 |
|---|---|---|---|
| `hydrodata-baseflow-001` | 规则、非负、多峰流量；显式 `alpha=0.95`、`BFImax=0.80` | Eckhardt 递推逐行正确；`baseflow` 与 `quickflow` 边界有效；两者之和守恒 | `success` |
| `hydrodata-baseflow-002` | 含零流量区段，上游结果本身带 warning；显式参数 | 零流量处各分量和 quickflow fraction 均为零；不得除零；继承上游 warning | `warning` |
| `hydrodata-baseflow-003` | 至少 20 个有效退水对；自动估计 alpha | 使用退水比率的 90% 分位值；记录证据对数与正确决策来源 | `success` |
| `hydrodata-baseflow-004` | 快速退水令原始 alpha 估计低于允许范围 | 将估计值裁剪到下限 `0.80`；分量仍然守恒 | `success` |
| `hydrodata-baseflow-005` | 极慢退水令原始 alpha 估计高于允许范围 | 将估计值裁剪到上限 `0.9999`；不得产生 NaN 或无穷值 | `success` |
| `hydrodata-baseflow-006` | 有效递减流量对少于 20 个；要求自动估计 | 证据不足时拒绝；不能回退到经验 alpha | `error` |
| `hydrodata-baseflow-007` | 上游哈希有效，但流量表含非有限值 | 执行“至少两个有限非负流量值”约束；禁止删除或替换坏行 | `error` |
| `hydrodata-baseflow-008` | 显式传入 `BFImax=1.0` | 参数越界时拒绝；不能静默裁剪或替换参数 | `error` |

评分重点包括：分量表逐行数值、`0 <= baseflow <= discharge`、`quickflow >= 0`、流量守恒、alpha 及其来源、证据数量、warning 传播、错误原因和失败时禁止成果文件存在。

## 洪水事件提取

目标 Skill：`data-processing/extract-flood-events`

这一组直接提供已经校验且哈希有效的 `components/` artifacts 和显式 YAML 参数，只测试洪水事件提取 Skill。正常成果写入 `events/`。

| 测试 ID | 输入情景 | 主要测试点 | 预期 |
|---|---|---|---|
| `hydrodata-flood-events-001` | 单个孤立且完整的洪峰 | 事件起止、峰值、历时、总洪量、基流/直接径流洪量、比例和单场文件全部正确 | `success` |
| `hydrodata-flood-events-002` | 两个相隔较远的洪峰 | 保持为两个不重叠事件；事件 ID 按时间稳定编号为 1、2 | `success` |
| `hydrodata-flood-events-003` | 两个相近峰，中间总流量谷值较浅 | valley ratio 满足阈值时合并为一个复峰事件；主峰取合并窗口最大值 | `success` |
| `hydrodata-flood-events-004` | 同日两个相近峰，中间谷值较深 | 不合并；按峰现时间命名时，同日第二个文件使用稳定 `_02` 后缀 | `success` |
| `hydrodata-flood-events-005` | 洪峰靠近序列开头 | warm-up 安全截断到索引 0；负相对步长只作预热，不计入事件历时、峰值和洪量 | `success` |
| `hydrodata-flood-events-006` | 同时含小洪峰、过短事件和一个主事件 | 依次执行历时、峰值和洪量门槛；只保留全部合格的主事件 | `success` |
| `hydrodata-flood-events-007` | 全部流量均为基流，quickflow 为零 | 不自动降低检测阈值；输出零事件的空 summary/process、完整 annotated series | `warning` |
| `hydrodata-flood-events-008` | 存在候选洪峰，但显式规模门槛筛除全部事件 | 区分“检测到候选但最终为零”与“没有 quickflow”两种路径 | `warning` |
| `hydrodata-flood-events-009` | YAML 缺少一个必需科学参数 | 配置校验失败；禁止用默认值补齐；不生成事件成果 | `error` |
| `hydrodata-flood-events-010` | 总流量、基流和 quickflow 的事件洪量不守恒 | 科学 QC 必须失败；保留原生错误结果；不交付事件成果 | `error`，原生脚本退出码 2 |

评分重点包括：summary、process 和 annotated series 的逐行内容，事件边界、主峰、稳定 ID、warm-up 排除、洪量守恒、manifest、逐场文件集合、配置回写、QC 状态，以及失败场景的成果缺失。

## 新增测试时的记录模板

新增任务后，请同步补充一行：

```markdown
| `任务-ID` | 输入数据中刻意构造的情景 | 只描述该题希望识别的行为与禁止的错误修复 | `success` / `warning` / `error` |
```

设计原则：一题尽量只引入一个主要变量；明确哪些修复得到授权；失败题避免被更早的无关错误遮蔽；生成器应可重复运行且输出稳定。
