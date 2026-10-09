# 完整输入资料

本题所有必要事实与授权在启动前提供，运行中没有用户信息补充。

读取 scenario.json 的变量、时间、空间、模型、初始状态与评价设定；input_inventory.json 列出各资料的角色、列名和 SHA-256。raw.csv 或 raw_events/*.csv 是允许使用合成补充的计算资料；original.csv 或 original_events/*.csv 是只读原始观测，缺测必须保留。补充值逐项记录在 supplements 文件，不能称为实测。

已有空间成果与 members 中的物理模型成果属于题目输入，可以读取，不是本题标准答案。新成果按 OUTPUT_INTERFACES.md 与 output_interfaces.json 输出。

模型及指定参数、单位、warm-up、组织模式和评分样本不能自行改变；可自行实现等价计算并排错重试。可用程序及其接口在 /public，不要求调用某个程序。工具文档中的确认要求由本题启动前的显式设定满足。


workflow_requirements.json 列明本题工作流能力和跨步骤一致性要求，不包含参考答案。
