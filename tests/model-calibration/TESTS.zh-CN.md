# 模型率定测试说明

本目录为十四个原子模型 Skill（五个率定器、马斯京根/Lohmann 河道演算、集总式新安江/DHF/HBV/Tank/GR4J/Sacramento 前向模拟）提供 39 道独立 benchmark task。评分对象均为 artifacts；validation 只允许在参数锁定后运行。

## 公共输入与成果

新任务均提供带真实 SHA-256 的 `calibration-problem.json`、`optimizer-config.json`、`fixture.json` 和 `synthetic_adapter.py`。问题文件明确参数边界、目标方向、率定/验证 split、变量单位和 warm-up 语义，Agent 不需要也不得猜测这些信息。

正常和 warning 题要求原生七项成果：`best_parameters.json`、`calibration_trace.csv`、两份 metrics、两份 series 和 `result.json`。error 题只允许交付 `result.json`，其余六项成果必须不存在。

## 任务矩阵

| 测试 ID | 输入情景与主要测试点 | 预期状态 / 退出码 |
|---|---|---|
| `hydromodel-de-001` | 二参数内部最优；完整 DE 配置；validation 不参与搜索 | `success` / 0 |
| `hydromodel-de-002` | 初始种群期间达到硬评估预算；保留当前最佳可行解 | `warning` / 0，`evaluation_budget_exhausted` |
| `hydromodel-de-003` | DE 配置缺少 `mutation_factor`；不得补默认值 | `error` / 1 |
| `hydromodel-ga-001` | 单参数且交叉概率为 1；必须跳过无效单点交叉；精英仍重新评估 | `success` / 0 |
| `hydromodel-ga-002` | 后续代内耗尽预算；精英重评估计入预算 | `warning` / 0，`evaluation_budget_exhausted` |
| `hydromodel-ga-003` | 锦标赛规模大于种群 | `error` / 1 |
| `hydromodel-pso-001` | 参数跨度不对称；速度上限按各参数跨度计算并只裁剪一次 | `success` / 0 |
| `hydromodel-pso-002` | 第一次目标评估确定性失败，但未超过失败上限 | `warning` / 0，失败计数为 1 |
| `hydromodel-pso-003` | `velocity_limit_fraction=0` | `error` / 1 |
| `hydromodel-sce-ua-001` | 每个复形恰为 `参数维度+1` 个点；检查排序、轮转分组、演化和洗牌轨迹 | `success` / 0，`max_loops_reached` |
| `hydromodel-sce-ua-002` | 复形演化期间耗尽全局预算 | `warning` / 0，`evaluation_budget_exhausted` |
| `hydromodel-sce-ua-003` | 每个复形点数小于 `参数维度+1` | `error` / 1 |
| `hydromodel-two-stage-001` | dual annealing 后接 L-BFGS-B；轨迹必须包含两个阶段 | `success` / 0，`two_stages_completed` |
| `hydromodel-two-stage-002` | 首次局部阶段评估失败；保留退火阶段最佳解 | `warning` / 0，失败计数为 1 |
| `hydromodel-two-stage-003` | 两阶段预算之和超过全局预算 | `error` / 1 |
| `hydromodel-muskingum-001` | 双入流（单段 + cascade x_l=0.05）正常演算；C0+C1+C2=1、`route_coefficients.json`、体积差在容差内 | `success` / 0 |
| `hydromodel-muskingum-002` | 用户确认 cascade X=0、n=4（x_l=-1.5）；负等价 X 不得裁剪，负出流按源码行为裁剪并计数 | `warning` / 0，`unstable_cascade:stability_range` |
| `hydromodel-muskingum-003` | 入流列含缺测；不得填充或插值，脚本必须拒绝 | `error` / 2，`no_missing_inflow` FAIL，不产出演进表 |
| `hydromodel-xaj-001` | 大暴雨 + SM=4.0 连续模拟（72 步，warm-up 12）；水量平衡 PASS、无数值裁剪、W≤WM | `success` / 0 |
| `hydromodel-xaj-002` | 中等雨强 + SM=25 触发数值裁剪；必须原生报告，不得修改参数规避 | `warning` / 0，`continuous:numerical_clipping` |
| `hydromodel-xaj-003` | E0 含缺测；不得填充，脚本必须拒绝 | `error` / 2，`no_missing_forcing` FAIL，不产出模拟表 |
| `hydromodel-dhf-001` | 长暴雨 + 全软范围内参数（CC=2.0/COE=0.4 消除单位线 NaN）；--pet-column E0、river-length 20、平衡容差 0.05；水量平衡 PASS、零裁剪 | `success` / 0 |
| `hydromodel-dhf-002` | 确认越界参数 U0=100、B=0.6；必须原生报告 `parameter_range` warning，不得改参规避 | `warning` / 0，`continuous:parameter_range` |
| `hydromodel-dhf-003` | PET 列（E0）含缺测；不得填充，脚本必须拒绝 | `error` / 2，`no_missing_forcing` FAIL，不产出模拟表 |
| `hydromodel-hbv-001` | 湿润 forcing + 示例参数；平衡容差 6.5（源码 HBV 的 Q0 不从 SM 扣水、effective→recharge 有消减，属结构性损耗） | `success` / 0 |
| `hydromodel-hbv-002` | 确认越界参数 fc=250；必须原生报告 `parameter_range` warning，不得改参规避 | `warning` / 0，`continuous:parameter_range` |
| `hydromodel-hbv-003` | E0 含缺测；不得填充，脚本必须拒绝 | `error` / 2，`no_missing_forcing` FAIL，不产出模拟表 |
| `hydromodel-tank-001` | 湿润 forcing + 示例参数；四箱不触零地板、水量平衡 PASS | `success` / 0 |
| `hydromodel-tank-002` | 旱段（P=0、E0=0.9）使净雨为负，触发四箱 floor 裁剪；必须原生报告，不得改参规避 | `warning` / 0，`continuous:numerical_clipping` |
| `hydromodel-tank-003` | E0 含缺测；不得填充，脚本必须拒绝 | `error` / 2，`no_missing_forcing` FAIL，不产出模拟表 |
| `hydromodel-gr4j-001` | 日尺度湿润 forcing（尾段旱日排空 UH）+ 示例参数 X1=350/X2=0/X3=90/X4=1.7；--pet-column E0、平衡容差 0.2（地下水交换项近似闭合） | `success` / 0 |
| `hydromodel-gr4j-002` | 确认 X2=-5（合法负交换）在旱段触发 routing_store/qd floor 裁剪；必须原生报告，不得改参规避 | `warning` / 0，`continuous:numerical_clipping` |
| `hydromodel-gr4j-003` | PET 列（E0）含缺测；不得填充，脚本必须拒绝 | `error` / 2，`no_missing_forcing` FAIL，不产出模拟表 |
| `hydromodel-sacsma-001` | 24h 日步长（避开 daily_timestep WARN）+ 16 示例参数（RIVA=0/SIDE=0）；平衡容差 4.5（源码 ET4 扣出流属结构性损耗） | `success` / 0 |
| `hydromodel-sacsma-002` | 确认 RIVA=0.05 + 旱段 E0=8 mm/day；河岸带需求超过可用出流触发 tot_outflow&lt;0 裁剪；必须原生报告 | `warning` / 0，`continuous:numerical_clipping` |
| `hydromodel-sacsma-003` | P 列含缺测；不得填充，脚本必须拒绝 | `error` / 2，`no_missing_forcing` FAIL，不产出模拟表 |
| `hydromodel-lohmann-001` | 240 日双分量入流（direct/base），末端 110 日静默使 107 步合成 UH 完全排空；flowlen 100000 m、K=2 | `success` / 0 |
| `hydromodel-lohmann-002` | 确认 K=10 加宽 Gamma UH + 60 日持续入流短序列；direct 分量尾部滞留超容差属文档预期行为，必须原生保留 | `warning` / 0，`volume_difference:direct` |
| `hydromodel-lohmann-003` | base 列含缺测；不得填充，脚本必须拒绝 | `error` / 2，`no_missing_inflow` FAIL，不产出路由表 |

## 评分与已知脚本差异

正常和 warning 题按文件结构 10%、参数与搜索轨迹 30%、split 指标和序列 25%、结果语义 20%、artifact 路径与哈希 15% 评分。error 题检查原生错误原因、空 artifact map 和禁止成果缺失。

当前公共错误 helper 从 Skill 名最后一个连字符后推导 `algorithm`，导致 SCE-UA 和 two-stage 的 error 结果分别写成 `ua` 和 `stage`。本 benchmark 记录该差异，但不对 error 结果的 `algorithm` 字段评分；`skill`、`status`、错误原因和成果清理仍严格评分。

开发阶段禁止运行任何实际 Agent。确定性脚本交叉验证使用：

```powershell
python scripts/verify_calibration_tasks.py --skills-root "E:\HydroTune-Skills（仿BioSkills版）"
python scripts/verify_modeling_tasks.py --skills-root "E:\HydroTune-Skills（仿BioSkills版）"
```
