# 结果分析测试说明

本文档说明 `tests/results-analysis/` 中当前 benchmark task 的测试目的，并提供后续扩展模板。实际执行和评分以任务的 `task.json`、`data/` 与 `expected/` 为准。

## 目录约定

每个任务通常包含：

- `task.json`：诊断要求、指标定义、必需输出和评分规则。
- `generate_data.py`：确定性生成观测与模拟序列。
- `data/`：Agent 可见的观测和模拟结果。
- `expected/`：精确指标与主诊断类别参考。

## 当前测试

| 测试 ID | 输入情景 | 主要测试点 | 主要评分 |
|---|---|---|---|
| `hydroanalysis-001` | 一组观测流量与一组模拟流量，合成数据中刻意设置一个占主导的洪峰时间滞后问题 | 先按时间戳对齐；严格按指定公式计算 7 个指标；正确解释峰值时间误差正负号；从限定类别中识别主问题为 `peak_timing_delay` | 输出文件 10%；NSE、KGE、PBIAS、RMSE、MAE、R² 各 8.33%；峰时误差 20%；主诊断类别 20% |
| `hydroanalysis-event-metrics-001` | 三场洪水（逐小时 CSV）+ 确认的 thresholds.json | 按场计算原生 19 列指标表；误差符号固定（体积/洪峰=观测−模拟，峰时=模拟−观测）；按阈值给出合格列 | 文件结构 10%；指标表 25%；result 语义 30%；artifact 哈希 30% |
| `hydroanalysis-event-metrics-002` | event_01 的观测与模拟峰均并列 | 并列峰取首个最大值并保留原生 `peak_tie` warning，不得扰动序列 | 同上（warnings 权重 10%） |
| `hydroanalysis-event-metrics-003` | event_02 的 Q_obs 含缺测 | 原生部分表模式：健康场次照常计入，QC FAIL 记入 error result.json；不得填充或修复 | 文件结构 15%；部分表 20%；skill/status/错误原因 40%；artifact 哈希 25% |
| `hydroanalysis-series-metrics-001` | 96 步连续序列（Q_obs/Q_total） | 默认六指标长表（metric/value/unit/status）；volume_bias 用显式 dt 换算 | 文件结构 10%；指标表 25%；result 语义 30%；artifact 哈希 30% |
| `hydroanalysis-series-metrics-002` | 观测序列为常数 50.0 | 方差退化：`nse` 记 `unavailable`、`r2` 按 sklearn 约定给边界值、保留 `variance_available` warning | 同上（warnings 权重 10%） |
| `hydroanalysis-series-metrics-003` | Q_total 含缺测 | 脚本必须拒绝输入；不产出指标表；不得填充后计算 | 文件结构 15%；skill/status/错误原因 75%；禁止成果缺失 20% |
| `hydroanalysis-aggregate-metrics-001` | 六场逐场指标表 + catchment 分组列 | 按 catchment 等权聚合三个数值列并计算两个合格率；不重算上游指标 | 文件结构 10%；汇总表 25%；result 语义 30%；artifact 哈希 30% |
| `hydroanalysis-aggregate-metrics-002` | 空指标表（仅表头） | 原生空表语义：`row_count` warning + 空聚合结果 + 退出码 0，不得当错误处理 | 同上（warnings 权重 10%） |
| `hydroanalysis-aggregate-metrics-003` | `--statistics mean,p25` | 未知统计量必须被拒绝（退出码 1）；不得映射到其他统计量 | 文件结构 15%；skill/status/错误原因 85%；禁止成果缺失 20% |
| `hydroanalysis-ml-correct-001` | train_table + predict_table + ridge 配置（random_state=20260928，chronological） | train 后用模型卡预测新时段；残差恒等式 observed−base、corrected=base+predicted_residual；model_card 关键字段与 test_r2 容差校验 | 文件结构 10%；两段校正序列 30%；model_card 25%；状态与 artifact 哈希 35% |
| `hydroanalysis-ml-correct-002` | 同 001 但 `--lag-spec Qt:1` | 滞后行丢弃必须保留原生 `lag_rows_dropped` warning；不得改用 fill 策略 | 文件结构 10%；校正序列 20%；model_card 30%；状态/warnings/checks 25%；artifact 哈希 15% |
| `hydroanalysis-ml-correct-003` | 同 001 但不提供 random_state 且禁止自造 | train 必须拒绝执行（退出码 1）；不产出 corrected_series/model_card/model | 文件结构 15%；skill/status/错误原因 85%；禁止成果缺失 20% |

### `hydroanalysis-001` 具体检查内容

- `metrics.json` 必须给出数值型 `NSE`、`KGE`、`PBIAS`、`RMSE`、`MAE`、`R2` 和 `peak_timing_error_steps`。
- KGE 使用 2009 版本，并在变异项中使用样本标准差。
- PBIAS 定义为 `100 * sum(simulated - observed) / sum(observed)`。
- R² 使用 Pearson 相关系数的平方。
- 正的 `peak_timing_error_steps` 表示模拟全局峰晚于观测全局峰。
- `diagnosis.json` 的 `primary_category` 必须从给定枚举中选择，不能自由发明标签。

## 新增测试模板

后续增加结果分析任务时，建议复制下表并补充一行：

```markdown
| `hydroanalysis-XXX` | 序列特征以及刻意构造的主导偏差或异常 | 时间对齐、指标公式、符号约定、主次问题判别 | 指标精度；事件/峰值检查；诊断类别 |
```

确定性脚本交叉验证（开发验收用，不得运行 Agent）：

```powershell
python scripts/verify_diagnostics_tasks.py --skills-root "E:\HydroTune-Skills（仿BioSkills版）"
```

建议每题明确记录：

- 时间粒度、时间戳是否完全对齐，以及缺测和重复时间的处理规则。
- 指标的精确定义、标准差约定、分母方向和容差。
- 峰值并列时的处理方式及时间误差符号。
- 候选诊断类别与“主问题”的判定优先级。
- 是否测试幅值偏差、总量偏差、峰时提前、峰时滞后或无明显病态。

设计时应让合成数据具有清晰且唯一的主导问题，避免多个同等严重的异常使诊断类别产生歧义。
