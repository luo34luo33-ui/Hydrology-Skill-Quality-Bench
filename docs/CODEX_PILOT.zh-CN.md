# Codex 单题无技能联调

本入口只执行一题、一个无技能条件，结果标记 `formal_eligible=false`，不进入正式对照。旧确认式组合题的联调不能代替现行无交互任务认证。

先按[外部资源说明](EXTERNAL_RESOURCES.md)准备程序、容器和本机模型认证。在仓库根目录、`HydroTune-eval` 环境中，使用本机已构建的镜像及明确配置的模型：

```powershell
python -m harness.pilot --image $Image --test-id hydrochain-data-001 --model $Model --effort $Effort --output results/pilot-next
```

每次使用新的输出目录。候选工作区不得挂载隐藏答案、其他任务或宿主机根目录；真实凭证留在宿主机中继。联调保存元数据、执行状态、评分、CLI 日志与路由审计，均只在本地保存。完整网络、原生技能发现和预算认证仍须独立执行。
