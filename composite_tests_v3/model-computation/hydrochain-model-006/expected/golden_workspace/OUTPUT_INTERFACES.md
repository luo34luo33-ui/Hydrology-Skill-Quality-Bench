# 公开成果接口

output_interfaces.json 给出全部必需成果的路径、表列及 JSON 字段结构，这些是科学交换接口，不限制工具或实现。表格交付须保持时间、事件和空间单元的对应关系。所有输出时间字段须带时区偏移，原始无时区时间先按 Asia/Shanghai 本地化；UTC Z 与 +08:00 的同一时刻等价。按 scenario.json 的 forcing_selection 选择实际驱动字段、空间代表性、source_id 和 E0/PET 变量；其它可用列不代表本题要求使用。JSON 的参数取值来自 scenario.json；计算结果必须来自实际计算。元数据中的消息、生成时间、工具名称不要求复制任何参考值。

中间输入可自行命名；result.json 的 inputs 和 artifacts 保持声明的科学角色，optional_input_roles 所列临时配置／适配器引用可以省略，无需保留参考程序的配置文件；引用相对文件路径及实际 SHA-256。不要伪造程序运行状态。decision.json 使用公开的 status/reason，说明科学限制和实现选择，引用实际证据。

若交付 analysis-001/002/003 的 conclusions.json，causality=not_established，scoring=same_samples_excluding_warmup，units=m3/s；independent_prediction 仅 analysis-003 为 true。比较题 ranking_rmse 按实际公平评分后的 RMSE 排序。report.md 以 JSON 代码块绑定 conclusions.json，并列出 decision.json 的证据路径与哈希。
