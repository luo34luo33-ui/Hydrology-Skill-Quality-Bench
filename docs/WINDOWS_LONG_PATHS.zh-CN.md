# Windows 长路径统一修复

原子与组合测试共用路径处理，不再仅对 programs-only 的程序复制作局部修复。

## 覆盖范围

- 原子本地：no-skills、programs-only、with-skills，以及 legacy-no-skills、legacy-with-skills。
- 原子隔离：Codex、OpenCode、Qwen、CodeBuddy 的三种实验条件。
- 组合隔离：Codex、OpenCode、Qwen 的有技能与无技能条件。
- 默认结果目录、自定义工作目录、输入复制、公开程序、技能快照及 CLI 技能镜像、结果归档、评分和报告读取。

Windows 内部文件操作使用绝对扩展路径。执行目录预计过长时，所有模式自动选择项目 `.cache/w` 下的短目录，必要时使用 TEMP 下的 `hsqb` 目录；结果仍归档到指定结果目录。`execution.json` 记录实际和请求的工作目录。Docker 挂载使用普通绝对宿主路径，容器内路径保持稳定。路径越界检查继续生效。

## 验证

`tests_harness/test_long_path_modes.py` 的 29 项 Windows 专项检查覆盖上述模式和自定义长目录，以及输入、输出、技能复制和越界拒绝。隔离模式的模型执行被替换为测试执行器，因此这些检查不能代表真实模型能力实验。

真实 Docker 使用冻结镜像进行无网络、无模型的输入读取、输出写入和结果归档检查，成功归档到 389 字符路径。记录见 `.cache/windows-long-path-docker.json`。包含新增专项的完整回归为 314 项通过、2 项跳过，另有一个既有 rasterio 弃用提示。

不改本机技能或科学输入，不重新解释已有实验结果。本轮宿主运行器修改会改变冻结运行器哈希；正式隔离模型实验须重新完成运行环境认证并生成有效锁文件，不能直接改旧锁中的哈希绕过认证。本轮未重跑完整模型实验。
