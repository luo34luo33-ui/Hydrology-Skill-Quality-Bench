> 这是旧版确认式组合测试的历史记录。现行无交互 v2 见 [新版说明](COMPOSITE_UNATTENDED_V2.zh-CN.md)；新版结果与认证不能和此记录混用。

# 2026-10-04 夜间组合评测

计划：24题 × 2条件 × 3CLI × 1轮 = 144次。北京时间2026-10-05 10:00截止；09:00后不启动新配对。各CLI最多一个候选，全局最多三个，配对内顺序交替。

## 运行前准备

这是旧版确认式调度的操作说明，不提供任何运行结果或既有认证。请先按[外部资源说明](EXTERNAL_RESOURCES.md)准备资源，在本机生成并审查实际 lock 和认证。示例日期是历史调度参数，重新运行时须替换截止时间与输出目录。

## 连接实施和验收完成后的操作

PowerShell中执行：

```powershell
# Run from the repository root
conda activate HydroTune-eval
# Ensure Docker is available on PATH.
python -c "from harness.composite_runtime import preflight; import json; print(json.dumps(preflight('runtime/experiment.lock.json'),ensure_ascii=False,indent=2))"
```

只有ready为true后启动：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_overnight.ps1
```

后台启动脚本保存PID、stdout和stderr；若预检未通过不会启动进程。调度器临时阻止系统自动睡眠，退出后释放。已运行时不要重复启动；同一输出目录有操作系统互斥锁保护。

直接前台执行等价命令：

```powershell
python -m harness.experiment --lock runtime/experiment.lock.json --clis codex,opencode,qwen --workers 3 --output results/overnight-20261004 --deadline "2026-10-05T10:00:00+08:00" --resume --execute
```

仅生成计划不调用Agent：

```powershell
python -m harness.experiment --lock runtime/experiment.lock.json --output results/overnight-20261004
```

恢复使用原始lock和输出目录。修改模型、资源、程序或提示词后不得恢复同一实验。完成的有效配对跳过；未完成配对保留旧记录并从新attempt整对重跑。启动失败最多重试一次，连续失败暂停对应CLI。科学失败、超时和预算耗尽不自动重跑。

原始指标按有效完成运行统计；配对差异只使用两个条件均有效完成的配对。旧attempt单列，未执行任务不计为科学失败。不同基础模型之间不作CLI能力比较。

## 查看结果

结果目录包含 `progress.json`、`dispatcher.json`、`scientific_report.json`、`scientific_results.csv` 和 `RESULTS.zh-CN.md`。调度器每分钟刷新，完成每个条件后保存结果，结束时生成最终快照。只有一轮时不报告重复波动。

```powershell
Get-Content results/overnight-20261004/progress.json
python -m harness.experiment --lock runtime/experiment.lock.json --output results/overnight-20261004 --report-only
```

未完成全部计划时报告须注明截止快照。独立冒烟和预算测试不混入科学评测，CLI／模型／推理设置须在本机明确冻结。
