# Qwen / CodeBuddy 原子任务运行

新增入口为 `scripts/run_qwen.py` 和 `scripts/run_codebuddy.py`，通过现有原子 Harness 完成输入 staging、每题一次新进程、Task 超时、日志保存和隐藏评分。无需 Docker，也不读取组合任务的 `runtime/experiment.lock.json`。本次验收使用假进程，没有发起真实模型调用。

## 准备和无 API 预检

```powershell
conda activate HydroTune-eval
# Run from the repository root
python -m harness.cli validate --suite atomic
python scripts/run_qwen.py --check
python scripts/run_codebuddy.py --check
```

`--check` 仅检查 CLI 可执行文件、版本和必要的无头参数，不验证认证或模型访问，不产生模型费用。请在本机执行预检并记录实际 CLI 版本。可通过 `HSQB_QWEN_BINARY` / `HSQB_CODEBUDDY_BINARY` 指定 EXE 或 Node 入口。Windows npm `.cmd` 支持 `.js`、`.mjs`、`.cjs` 以及带 Node shebang 的无后缀入口（如 CodeBuddy 的 `bin/codebuddy`），解析为 Node + 文件路径的参数列表启动，不通过 shell 拼接提示词。

Qwen 默认从 `QWEN_HOME/settings.json` 或 `~/.qwen/settings.json` 读取模型提供商、认证和生成参数；也可将 `HSQB_QWEN_SETTINGS` 指向独立 JSON 配置。只复制必要认证/模型设置及可用的 `oauth_creds.json` 到临时 HOME，个人技能、MCP、hooks、历史、记忆和回退模型不复制。使用自定义 `envKey` 时，相应密钥环境变量必须已设置。

CodeBuddy 默认从 `CODEBUDDY_CONFIG_DIR/settings.json` 或 `~/.codebuddy/settings.json` 读取模型、推理强度及允许的认证环境字段；可用 `HSQB_CODEBUDDY_SETTINGS` 指定独立配置。支持 `CODEBUDDY_API_KEY`、`CODEBUDDY_BASE_URL`、`CODEBUDDY_INTERNET_ENVIRONMENT`、`CODEBUDDY_AUTH_TOKEN`。默认不继承个人登录状态；需要 API-key 或平台 token 认证，或显式开启下面的个人登录继承。密钥请由本机秘密存储或环境注入，不写入命令、仓库或结果目录。不要将本机运行标记为 `CODEBUDDY_IS_SANDBOX=1`；适配器会移除该标记。

### 继承个人 CodeBuddy CLI 登录

先在同一个 Windows 用户下启动 `codebuddy`，在 CLI 内执行 `/login` 完成登录，然后退出。在运行 Harness 的 PowerShell 中设置：

```powershell
$env:HSQB_CODEBUDDY_INHERIT_LOGIN = '1'

python -m harness.cli run `
  --suite atomic `
  --test-id hydrodata-baseflow-002 `
  --agent-cmd "python scripts/run_codebuddy.py" `
  --model hy3 `
  --effort provider-default `
  --output results/atomic-codebuddy-login-check-001
```

`hy3` 对应此前用户运行日志中的模型，仍需账号具备访问权限。国内／国际登录环境必须与个人 CLI 一致，必要时通过 `CODEBUDDY_INTERNET_ENVIRONMENT` 指定，不自动替换。

适配器此时保留个人 `HOME` / `USERPROFILE`，让 CodeBuddy 原生认证实现读取共享登录凭据并处理加密及刷新。`CODEBUDDY_CONFIG_DIR` 仍指向每题独立临时配置；不复制个人技能、插件、MCP、历史或记忆文件，也不提取或打印登录 token。每题仍是新进程，不恢复聊天会话。workspace 的 `.hsqb-adapter.json` 记录 `personal_login_home: true`。登录有效性与模型调用必须通过真实单题验证，`--check` 不验证登录。

保留个人 HOME 同时允许 CLI 访问共享缓存，因此它并非“仅有认证文件可见”的安全隔离。有／无技能两组应使用相同的开关和认证环境。不要直接将 `CODEBUDDY_CONFIG_DIR` 改成个人配置来实现继承，这会带入额外设置。

取消继承：

```powershell
Remove-Item Env:HSQB_CODEBUDDY_INHERIT_LOGIN -ErrorAction SilentlyContinue
```

## 单题有 / 无技能

```powershell
# Qwen，无技能
python -m harness.cli run `
  --suite atomic `
  --test-id hydrodata-timeseries-001 `
  --agent-cmd "python scripts/run_qwen.py" `
  --model deepseek-v4-pro `
  --effort provider-default `
  --output results/atomic-qwen-no-skills-001

# Qwen，有技能
python -m harness.cli run `
  --suite atomic `
  --test-id hydrodata-timeseries-001 `
  --agent-cmd "python scripts/run_qwen.py" `
  --model deepseek-v4-pro `
  --effort provider-default `
  --skills-path runtime/skills `
  --output results/atomic-qwen-with-skills-001

# CodeBuddy，无技能；YOUR_MODEL_ID 替换为已配置且可用的模型 ID
python -m harness.cli run `
  --suite atomic `
  --test-id hydrodata-timeseries-001 `
  --agent-cmd "python scripts/run_codebuddy.py" `
  --model YOUR_MODEL_ID `
  --effort provider-default `
  --output results/atomic-codebuddy-no-skills-001

# CodeBuddy，有技能
python -m harness.cli run `
  --suite atomic `
  --test-id hydrodata-timeseries-001 `
  --agent-cmd "python scripts/run_codebuddy.py" `
  --model YOUR_MODEL_ID `
  --effort provider-default `
  --skills-path runtime/skills `
  --output results/atomic-codebuddy-with-skills-001
```

两条件使用逐字相同的启动提示、`AGENTS.md` 和 CLI 原生任务说明。技能快照复制到 `.agents/skills/`，并另放入 Qwen 的 `.qwen/skills/` 或 CodeBuddy 的 `.codebuddy/skills/` 以供原生发现。无技能时没有快照；Qwen 同时禁用项目、用户、扩展和内置技能发现，有技能时仅开放项目层。源目录请使用已展平的 `runtime/skills` 或一个含 `SKILL.md` 的单技能目录。

`--effort high` 等值分别映射到 Qwen 的 `model.reasoningEffort` 和 CodeBuddy 的 `reasoningEffort`。省略参数继承过滤后配置的强度；`provider-default` 明确清除该强度覆盖。Qwen 支持 low/medium/high/xhigh/max，CodeBuddy 另支持 minimal；其他值会报错。提供商可能限制可用强度，离线测试不能证明远端实际采纳。

## 批量与比较

### CodeBuddy 非交互工具权限

适配器将权限写入每题临时 `settings.json`，并通过 `--settings <文件>` 显式加载，不依赖仅在 CLI 上传入工具名称来放行。保留 `dontAsk`，禁止全面绕过权限模式；工作区中 `.hsqb-adapter.json` 记录本题的 `tool_permissions`。

文件允许规则使用本题工作区的绝对路径，例如 `Write(E:/.../workspace/**)`，Read、Edit 同理。CodeBuddy 2.161.2 不会将 `./**` 转换为绝对路径，所以旧规则无法匹配 Write 的实际文件参数。Agent 被告知将计算代码保存为工作区内的 `task_compute.py`，通过说明中指定的绝对 Python 路径运行。解释器与适配器的 `sys.executable` 相同，不再依赖 shell 的 PATH；必须用 HydroTune-eval 的 Python 启动 Harness 和适配器。不能直接使用 `python -c`、任意 shell 命令或扫描本机目录。有技能时仅增加当前快照的 `Skill(<name>)` 规则。工具集合限定为 Read、Write、Edit、Glob、Grep、Bash、PowerShell、Skill；联网工具、子代理和交互提问被禁用。

这些规则是 CLI 层的允许配置，并非操作系统级隔离；Python 脚本本身仍运行于当前用户权限之下。`python -m scripts.verify_codebuddy_permissions` 不启动 Agent，直接在内存中加载已安装版本的原生匹配器，验证相对／绝对文件参数、嵌套目录、工作区外拒绝及固定命令匹配。原生匹配和适配器回归须在本机执行，包含 PATH 缺少解释器目录时的实际执行检查。此前仅 `config get permissions` 的验证不能证明工具授权成功。新配置尚未重跑真实模型。

2026-10-05 修改了公共运行说明和工具规则；有／无技能应一起使用新版本，旧权限故障记录不与新执行混为同一配置的实验结果。无需修改个人全局权限。

去掉 `--test-id` 即串行执行全部 183 道原子任务；添加 `--domain data-preprocessing` 等参数可按类别选择。每次使用新的空输出目录。不要传 `--suite composite`，这两个入口仅用于原子任务。

```powershell
python -m harness.cli compare `
  results/atomic-qwen-no-skills-001 `
  results/atomic-qwen-with-skills-001
```

输出包含 `summary.json`、逐题 `result.json`、`execution.json`、`stdout.log` 和 `stderr.log`。CLI 的 stream-json 原样进入 stdout 日志；非零退出和超时由现有 Harness 记录，并对已生成产物继续评分。workspace 中 `.hsqb-adapter.json` 记录模型 ID、配置强度、技能目录、相同启动提示及任务说明的哈希，不含认证配置或密钥。评分仍采用原子任务契约，不引入组合套件的三项统计或自动确认服务。

## 范围和边界

默认每题使用临时 HOME 与配置目录；CodeBuddy 可显式继承个人登录 HOME，配置目录仍是临时的。不自动恢复会话；正常退出会清理临时认证配置。强制杀进程可能遗留系统临时目录，应按本机凭据管理规则处理。Qwen 使用 `--yolo`，CodeBuddy 使用 `dontAsk` + 工作区文件规则和固定 Python 脚本命令，无 stdin 人工交互。任务超时和进程树终止复用 Harness；未增加或宣称统一回合/工具预算审计。

本机适配器提供配置隔离，**没有操作系统级文件或网络隔离**：同一用户的进程仍可能读取其他目录或通过 shell 访问网络。不要将其视为隐藏参考不可访问的正式对照容器。CodeBuddy 的内置技能/系统策略是否额外生效，以及所有远端认证、模型参数和原生技能发现，仍需安装对应版本后做真实冒烟验证。现有 OpenCode/Codex 适配器的提示与权限行为没有被本次修改，也不能直接假定与新增入口完全一致。

官方依据：[Qwen 无头运行](https://qwenlm.github.io/qwen-code-docs/en/users/features/headless/)、[Qwen 配置](https://qwenlm.github.io/qwen-code-docs/en/users/configuration/settings/)、[CodeBuddy CLI](https://www.codebuddy.ai/docs/cli/cli-reference)、[CodeBuddy 配置](https://www.codebuddy.ai/docs/cli/settings)、[CodeBuddy 技能](https://www.codebuddy.ai/docs/cli/skills)、[CodeBuddy 环境变量](https://www.codebuddy.ai/docs/cli/env-vars)。
