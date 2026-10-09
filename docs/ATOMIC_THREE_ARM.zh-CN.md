# 原子任务三组对照：实现与验收

实验版本为 `atomic-three-arm-v2`。183 道原子题分别进入 `no-skills`、`programs-only`、`with-skills`；原来的两组及 v1 记录属于旧实验，不能改标签后并入新实验。24 道组合题保持原来的独立入口。

| 条件 | 相同输入、业务正文、公共契约 | 科学程序和调用说明 | 技能资料 |
|---|---|---|---|
| no-skills | 有 | 无 | 无 |
| programs-only | 有 | 有 | 无 |
| with-skills | 有 | 与 programs-only 相同 | 有 |

`programs-only − no-skills` 是程序及说明增益；`with-skills − programs-only` 是同一程序条件下的技能增益；`with-skills − no-skills` 是总增益。分别在同一 CLI、同一模型、推理设置和重复轮次内计算。

## 本地验收要求

运行结果与宿主机认证不随仓库分发。资源准备见[外部资源说明](EXTERNAL_RESOURCES.md)。在本机重新生成契约审计、负例检查、隔离和 provider 认证；所有必需检查通过后才可正式运行。配置模板不代表已通过认证。

## 公开包和隐藏材料

`docs/atomic-public-contracts/` 保存 41 份源接口；每题的 `public_contract.json` 为任务实例。staging 将它们提供为 `public_contract.json` 和可读的 `PUBLIC_CONTRACT.md`。三组文档字节相同，提供接口结构、源合同中的单位、缺测、时间语义和不变量，及从序列化源码提取的字段、结构和分支。字段目录不是对任意自由文本或全部科学语义的独立认证。

契约构建器只从冻结的源数据合同、公开程序、任务公开字段及输入表头生成说明。hidden expected 只计算基线哈希；隐藏 grader 仅参与宿主机遗漏与冲突审计，不用于生成公开的参考值、预期分支、误差定位或容差。

`runtime/atomic-public/` 包含 41 个公开科学程序、依赖模块、schema、模板资产及 `PROGRAM_INTERFACES.md`。它不含技能说明、workflow、测试、合成数据生成器或隐藏答案。该说明仅在后两组提供，包含通用入口和参数接口，不含逐题选程序、填参数或执行顺序。

`runtime/atomic-skills/` 保存冻结的 41 个原子技能和 3 个 workflow。保留的科学 Python 文件及 schema／模板资产都必须在公共程序中有相同 SHA-256，见 `atomic-program-equivalence.json`。生成器和示例数据文件不挂载给候选。原始技能目录始终只读；审计核对了原冻结清单的 308 个文件。

科学程序和技能中的共享代码及运行资产必须保持 SHA-256 一致；重复构建后应比较程序、技能和公开契约哈希。审计结果只在本地保存。

## 可用入口

在 PowerShell 中使用：

```powershell
conda activate HydroTune-eval
# Run from the repository root
python -m harness.cli validate --suite all
python scripts/audit_atomic_contracts.py --golden
python scripts/audit_atomic_negative_controls.py
```

以检查的实际退出状态和诊断为准；不能省略失败检查或伪造通过记录。

只生成调度清单和空统计，**不会运行 Agent**：

```powershell
python -m harness.atomic_experiment `
  --clis codex,opencode,qwen,codebuddy `
  --repetitions 1 `
  --output results/atomic-three-arm-plan-20261005 `
  --resume
```

此清单共有 2,196 个运行位置；每个 CLI 为 183 个三组单元、549 个运行。`--test-id hydrodata-baseflow-002` 可生成单题清单。六种条件排列循环平衡，任务顺序由种子 20261005 冻结。

正式入口在验收完成后使用以下形式。当前运行会被预检阻断：

```powershell
python -m harness.atomic_experiment `
  --lock runtime/atomic-experiment.lock.json `
  --clis codex,opencode,qwen,codebuddy `
  --repetitions 1 `
  --output results/atomic-three-arm-r1 `
  --resume --execute
```

执行时写入 `execution-binding.json`，冻结 lock、题定义和输入哈希；恢复时变化即拒绝。已完成条件不重跑；基础设施故障按完整三组单元最多重跑一次，原始三组记录保存在 `archived-attempt-0/`。科学失败和超时不重跑；无法判定的残缺执行必须人工检查，不能自动冒充基础设施故障。

本机兼容入口增加 `--condition` 和 `--programs-path`。下列形式用于联调；本机进程仍可访问主机其他目录，不能作为正式隔离比较：

```powershell
# 公共参数：--suite atomic --test-id <ID> --agent-cmd <wrapper> --model <固定模型> --effort <固定设置>
python -m harness.cli run <公共参数> --condition no-skills --output <独立目录>
python -m harness.cli run <公共参数> --condition programs-only --programs-path runtime/atomic-public --output <独立目录>
python -m harness.cli run <公共参数> --condition with-skills --programs-path runtime/atomic-public --skills-path runtime/atomic-skills --output <独立目录>
```

以上尖括号是说明占位符，不能直接复制执行。四个 wrapper 分别为 `scripts/run_codex.py`、`run_opencode.py`、`run_qwen.py`、`run_codebuddy.py`。`no-skills` 拒绝程序或技能路径；`programs-only` 拒绝技能；`with-skills` 要求技能及程序。旧入口未指定条件时记录为 `legacy`。

## 冻结与容器

容器必须记录实际构建的镜像 digest 和各 CLI 的安装版本；本仓库不提供可直接复用的认证镜像。镜像不预装 HydroTune 科学程序，程序与技能分别只读挂载。

`scripts/freeze_atomic_experiment.py` 刷新模板哈希和实际认证文件引用，不执行认证，也不自动选择模型。需要在不含真实密钥的 `runtime/atomic-provider-config/` 中明确配置模型和有效推理设置，再重新冻结；真实凭证只供宿主机模型中继使用。

```powershell
python scripts/freeze_atomic_experiment.py `
  --output runtime/atomic-experiment.lock.json `
  --image-digest $ImageDigest `
  --versions $CliVersionsJson
python scripts/certify_atomic_isolation.py --lock runtime/atomic-experiment.lock.json
```

每次运行新容器、新 HOME、新会话；4 CPU、8 GB；使用每题原超时和冻结的 60 决策请求／120 工具调用上限。内部网络只连接允许的模型中继；主机保存隐藏参考与评分。原子题不启用组合题答案表。所有 CLI 使用条件无关的启动提示；CodeBuddy 的受限 Python 调用规则在三个条件中相同。

正式运行前须完成模型连接、原生技能发现和 CLI 预算事件认证；不支持的配置应阻断。真实凭证由宿主机保管，不复制个人 HOME 到候选容器。

## 报告口径

`three-arm-summary.json`、`three-arm-results.csv` 和中文快照报告每组计划、完成、有效运行、覆盖、均分、满分数、超时和基础设施失败。完整三组配对单独给出三项差异与按任务聚类的 bootstrap 区间；少于两个任务簇不报告区间。部分完成与未启动单独记录；归档重跑原始文件保留。原子题不套用组合题的信息确认率或关键科学错误率。

一轮只是固定 CLI／模型配置下的三组消融实验。不同 CLI 如使用不同模型，应分别报告，不能将模型差异归因于 CLI。
