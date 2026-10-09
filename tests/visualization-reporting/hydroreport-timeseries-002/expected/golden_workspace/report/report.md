# 预分析

<!-- section:overview -->
## 资料与时段概况

<!-- paragraph:overview-count kind:fact -->
本次资料包含 4 场已提取洪水；以下按明确的统计口径概括规模和峰型。

表 1 · 资料概况 / Data coverage

| 项目 | 数值 | 单位 | 资料集合 |
| --- | --- | --- | --- |
| standard_flow_unit | m3/s | unspecified | flow |
| timestep_seconds | 3600 | unspecified | flow |
| timezone | Asia/Shanghai | unspecified | flow |
| row_count | 24 | count | 洪水场次数 |
| start | 2019-12-31T23:00:00 | unspecified | 洪水场次数 |
| end | 2020-01-01T04:00:00 | unspecified | 洪水场次数 |
| row_count | 4 | count | 洪水场次数 |

表 2 · 洪水总数 / Event count

| 项目 | 数值 | 单位 |
| --- | --- | --- |
| 洪水场次数 | 4 | count |

<!-- section:sizes -->
## 洪水规模分布

<!-- section:shapes -->
## 洪峰形态

表 3 · 显著峰型 / Significant peaks

| 有效数量 | 比例（%） | 比例分母 | 峰型 |
| --- | --- | --- | --- |
| 0 | 不可用 / unavailable | 0 | 单峰 |
| 0 | 不可用 / unavailable | 0 | 多峰 |
| 4 | 不可用 / unavailable | 0 | 无法分类 |

图 1 · 显著峰型 / Significant peaks

![显著峰型 / Significant peaks](figures/distribution-2.svg)

<!-- section:events -->
## 事件总体特征

表 4 · 事件分布 / Event distributions

| 单位 | 有效数量 | 指标 | 均值 | 中位数 | P10 | P90 | 最小值 | 最大值 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m3/s | 4 | 洪峰流量 | 17.250 | 15.000 | 9.300 | 27.000 | 9.000 | 30.000 |
| m3 | 4 | 总洪量 | 174.750 | 150.000 | 99.300 | 270.000 | 99.000 | 300.000 |
| hours | 4 | 历时 | 4.000 | 4.000 | 4.000 | 4.000 | 4.000 | 4.000 |

表 5 · 月份分布 / Months

| 有效数量 | 月份 |
| --- | --- |
| 4 | 01 |

图 2 · 月份分布 / Months

![月份分布 / Months](figures/distribution-4.svg)

<!-- section:limitations -->
## 限制与建议

<!-- paragraph:limitation-0 kind:fact -->
peak_flow_m3_s 未提供阈值，未分级。

<!-- paragraph:limitation-1 kind:fact -->
total_volume_m3 未提供阈值，未分级。

<!-- paragraph:limitation-2 kind:fact -->
未提供显著峰参数，峰型比例不可用。

<!-- paragraph:limitation-3 kind:fact -->
分级仅表示调用方阈值下的相对规模，不是工程等级。月份分布仅描述现有时段，不代表长期气候规律。

部分资料未提供，相关分析范围受限；详见资料缺口附件。

