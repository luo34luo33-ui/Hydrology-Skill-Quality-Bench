# 组合测试用时与 token 统计

每次组合运行的 result.json、experiment_result.json 和汇总 JSON 增加 resource_usage。逐次 CSV 增加 wall_seconds、agent_seconds、input_tokens、output_tokens、total_tokens 和 token_measurement。

- wall_seconds：包含任务准备、环境建立、Agent 执行、清理、归档与科学评分的总耗时；不包含调度排队。
- agent_seconds：运行器监控 Agent 的实际经过时间。进程失败或预算耗尽也保留。
- reported：模型接口提供的 usage；reported_cli：历史 CLI 明确输出的 usage。
- estimated：没有 usage 时，用请求 JSON 和响应文本估算，汉字约每字符 1 token，其他字符约每 4 字符 1 token。
- mixed：部分字段或部分请求使用报告值，其余使用估算值。unavailable：历史记录无法恢复，值为 null，CSV 留空。

输入统计累加每次请求，包含重复历史上下文与缓存 token；cached_input_tokens 单列。reasoning_output_tokens 是已报告输出的一部分，不重复相加。字符估算不包含不可见推理，不等于实际计费 token，也不用于计算账单。异常超大响应导致解析截断时，accounting_truncated 为 true。

科学成绩不因新增统计改变。汇总只使用已知数值，并提供 observed_runs，未知运行不填零。主报告统计各条件的平均用时与已记录 token 合计；all_attempt_resource_usage 包括保留的重试记录。当前目录 resource_usage.csv 列出所有尝试，scientific_results CSV 列出当前选定尝试。

为已有运行补充记录，无需重新执行或重新评分：

```powershell
python scripts/backfill_composite_usage.py --runs-dir results/composite-unattended-v2-r4
```

历史运行没有记录准备、清理与评分总耗时，wall_seconds 保留 null；没有模型请求 usage 或完整 CLI usage 的历史运行不凭日志文件大小伪造 token 数。若原 CSV 被 Excel 等程序占用，带新字段的文件另存为 scientific_results.with-usage.csv。

新接口改变了宿主运行器代码，正式隔离运行前需要重新完成并冻结运行认证；保留旧锁与旧运行证据，不能仅更改哈希绕过认证。
