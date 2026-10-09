# 模型计算组合测试

本域包含 12 道组合题，按业务成果检查真实科学处理链及来源。
[覆盖矩阵](../../docs/composite-coverage.zh-CN.md)列出能力、依赖及确认项；
[开发规则](../DEVELOPMENT_RULES.md)规定隐藏参考和生成验证。

开发阶段仅执行确定性科学程序与自测，不运行真实 Agent。正式提示不点名
Skill；正常題至少三种不同科学能力，报告、图册和重复调用不计入最低数量。

使用 `python -m harness.cli validate --suite composite --domain model-computation`
校验本域。全套验收使用 `scripts/verify_composite_tasks.py` 和
`scripts/check_composite_repeatability.py`。
