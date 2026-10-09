# 24 道组合任务无交互 v2

现行版本为 `composite-unattended-v2`，修订号 4，`interaction_mode=none`。数据处理 8、模型计算 12、结果分析 4，全部以正常计算交付为目标。原子任务的定义和本机安装技能未在本次修改中调整。

每题 `scenario.json` 提供变量、单位、时间、组织模式、DEM 和流域 CRS、初始状态、warm-up、模型参数、蒸散映射、率定划分、评价策略与权限。`INPUT_GUIDE.md` 和 `input_inventory.json` 说明计算资料、原始观测、合成补充及其哈希；`OUTPUT_INTERFACES.md` 和 `output_interfaces.json` 公开成果路径、表列、JSON 结构和引用规则。没有隐藏的用户答案依赖。

Agent 可自主选择工具、代码、步骤、等价实现以及预算内的排错重试。指定模型、参数、状态组织、评分样本和原始资料保持约束。已有合成补充可用于计算，原始缺测必须保留，不能将补充描述为实测修复。

## 原 4 道阻断题的转换

| 任务 | 启动前修复 | 正常交付 |
|---|---|---|
| data-002 | 使用现有标注补充的计算资料，另保留原始缺测 | 事件库、驱动标准化与就绪检查 |
| data-008 | 固定测试流域的预期出口明确为 1 | 构建空间成果并独立验收 |
| model-010 | 使用稳定的 `KE=1.5, XE=0.2` 及小时步长 | 重算稳定性系数并完成出口模拟 |
| analysis-004 | 率定评分行 12–499，验证评分行 500 起；零基索引，前 12 步为 warm-up | 实际评分样本独立性核查与审查通过证据 |

样本独立性审查只说明评分集合不重叠，不证明模型准确或因果关系。

## 评分与版本隔离

新版评分检查科学成果、完整性、不可变来源、实际引用和 SHA-256，以及 `provided_setting_results`。报告指标为 `provided_setting_usage_rate`；不要求提问、答复或先后时序，不生成确认事件。旧版确认率可用于旧结果查看，但不能与新版汇总或配对比较。旧版结果不能针对新版题目重新评分。

中间转换文件可自主命名；参考程序的输入拆分文件、配置文件、元数据消息、事件诊断计数和固定优化轨迹不作为参考相等条件。公开的科学成果交换接口保持固定。率定必须提供预算内、可独立重算的目标记录及锁定参数后的验证序列，不要求某条参考搜索轨迹。

运行器只建立执行审计，不启动确认服务，不注入确认凭据；公开程序包没有 `confirm_user.py`，中继在无确认上游时拒绝 `/confirm`。模型服务、资源限额和执行日志保留。

## 验证与运行

在 `HydroTune-eval` 中运行：

```powershell
python scripts/verify_composite_tasks.py --native
python scripts/check_composite_repeatability.py
python -m pytest tests_harness -q
python scripts/audit_composite_unattended.py
```

参考计算验收见 `composite-acceptance.json`，两轮临时目录重新生成见 `composite-repeatability.json`，逐题完整性和真实运行状态见 `composite-unattended-audit.json`。参考计算和烟雾认证均不计为 144 次科学任务验证。

实际 lock 不随仓库上传。先以 `runtime/experiment.template.json` 准备本机模型、镜像和配置，保存为本地 `runtime/experiment.lock.json`；新版再生成独立 `runtime/experiment.unattended-v2.lock.json`。必须重新认证，不能借用旧认证：

```powershell
# Ensure Docker is available on PATH.
python scripts/freeze_composite_unattended.py
python scripts/certify_overnight.py --lock runtime/experiment.unattended-v2.lock.json
python scripts/certify_budgets.py --lock runtime/experiment.unattended-v2.lock.json
python scripts/finalize_overnight_lock.py --lock runtime/experiment.unattended-v2.lock.json --smoke results/unattended-v2-certification/certification.json --budget results/unattended-v2-budget-certification/certification.json
python -m harness.experiment --lock runtime/experiment.unattended-v2.lock.json --repetitions 1 --workers 3 --output results/composite-unattended-v2-r4 --execute
```

新版独立目录中的 `schedule.json` 冻结任务版本与哈希；已有调度不一致时拒绝运行。中断后保持题目与冻结配置不变，用 `--resume` 恢复；任务设计改变时使用新结果目录重新运行。认证命令同样应使用新的输出目录，避免覆盖既有证据。

## 公开契约与修订隔离

公开配置显式提供 forcing_selection、canonical source_ids、事件输入／输出前缀、带偏移的时间格式、模型初始状态、warm-up、水量平衡容差及 Eckhardt 初始状态和裁剪规则。参考程序的非科学临时配置不强制相等，科学来源、实际成果和独立复算仍须检查。

路由稳定性审计按每题有效模型确定 KE/XE、步长和系数顺序；独立河道参数不参与内部半分布式路由审计。BMA 训练期按实际时间比较，允许等价时区偏移，并按候选拟合参数独立复算预测和指标。

不同任务修订号的结果不能混算或重新评分。`composite_tests/` 与 `composite_tests_v3/` 都保留在仓库，后者须使用单独的本地 lock、认证和输出目录；不能沿用前者的运行认证。实际运行记录与验收报告只保留在本地，资源准备及报告入口见[外部资源说明](EXTERNAL_RESOURCES.md)。
