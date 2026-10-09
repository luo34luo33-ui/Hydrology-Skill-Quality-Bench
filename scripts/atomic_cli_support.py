"""Local atomic CLI support. Configuration isolation is not a security sandbox."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from harness.agent_wrapper import generate_agents_md, install_skill_snapshot
from harness.filesystem import copy_tree

START_PROMPT = "Complete the task described in AGENTS.md and create every required artifact."
EFFORTS = {"minimal", "low", "medium", "high", "xhigh", "max"}
CODEBUDDY_AUTH_ENV = {
    "CODEBUDDY_API_KEY", "CODEBUDDY_BASE_URL", "CODEBUDDY_INTERNET_ENVIRONMENT", "CODEBUDDY_AUTH_TOKEN",
}
CODEBUDDY_DENIED_TOOLS = ["WebFetch", "WebSearch", "Agent", "Task", "AskUserQuestion", "AskUserForStructuredInput"]
CODEBUDDY_RUNTIME_NOTE = (
    "## Local command interface\n\n"
    "File creation and edits are permitted inside this task workspace. "
    "For computation, write a Python script named `task_compute.py` in the workspace, "
    "then invoke the following exact command through the indicated tool:\n\n"
    "Bash: `{bash_command}`\n\nPowerShell: `{powershell_command}`\n\n"
    "These commands use the same Python interpreter as the benchmark adapter. "
    "Do not use inline Python, shell pipelines, package installation or searches outside this workspace.\n"
)


def is_node_entry(path: Path) -> bool:
    if path.suffix.lower() in {".js", ".mjs", ".cjs"}:
        return True
    if path.suffix or not path.is_file():
        return False
    with path.open("rb") as stream:
        header = stream.readline(256).decode("utf-8", errors="replace").strip()
    return bool(re.fullmatch(r"#!\s*(?:/usr/bin/env\s+node|[^\s]+/node)(?:\s.*)?", header))


def resolve_cli(cli: str) -> list[str]:
    """Launch npm Windows shims through Node, without shell argument interpolation."""
    configured = os.environ.get(f"HSQB_{cli.upper()}_BINARY")
    binary = configured or shutil.which(cli)
    if not binary and cli == "codebuddy":
        binary = shutil.which("cbc")
    if not binary:
        raise ValueError(f"{cli} CLI not found; install it or set HSQB_{cli.upper()}_BINARY")
    path = Path(binary)
    if path.suffix.lower() in {".cmd", ".bat"}:
        text = path.read_text(encoding="utf-8")
        entry = re.search(r'"%dp0%[\\/]([^"\r\n]+)"\s+%\*', text, re.IGNORECASE)
        if not entry:
            raise ValueError(f"{cli}: unsupported Windows shim; set the binary override to its JS entry or EXE")
        script = path.parent / Path(entry.group(1).replace("\\", "/"))
        if not is_node_entry(script):
            raise ValueError(f"{cli}: Windows shim does not point to a Node CLI entry; select its JS entry or EXE")
        node = path.parent / "node.exe"
        executable = str(node) if node.is_file() else shutil.which("node")
        if not executable or not script.is_file():
            raise ValueError(f"{cli}: Node executable or npm entry is missing")
        return [executable, str(script.resolve())]
    if is_node_entry(path):
        node = shutil.which("node")
        if not node or not path.is_file():
            raise ValueError(f"{cli}: Node executable or JS entry is missing")
        return [node, str(path.resolve())]
    if path.suffix.lower() == ".ps1":
        raise ValueError(f"{cli}: select its .cmd, .exe or JS entry instead of a PowerShell shim")
    return [binary]


def read_settings(cli: str) -> tuple[dict, Path]:
    default_dir = Path(os.environ.get("QWEN_HOME", str(Path.home() / ".qwen"))) if cli == "qwen" else Path(
        os.environ.get("CODEBUDDY_CONFIG_DIR", str(Path.home() / ".codebuddy")))
    override = os.environ.get(f"HSQB_{cli.upper()}_SETTINGS")
    source = Path(override).expanduser().resolve() if override else default_dir / "settings.json"
    if not source.is_file():
        if override:
            raise ValueError(f"{cli}: explicit settings file does not exist")
        return {}, default_dir
    try:
        settings = json.loads(source.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError):
        raise ValueError(f"{cli}: settings must be a readable JSON object") from None
    if not isinstance(settings, dict):
        raise ValueError(f"{cli}: settings must be a JSON object")
    return settings, source.parent


def validate_effort(effort: str | None, cli: str) -> None:
    if effort and effort != "provider-default" and effort not in EFFORTS:
        raise ValueError(f"{cli}: unsupported reasoning effort; use low/medium/high/xhigh/max or provider-default")
    if cli == "qwen" and effort == "minimal":
        raise ValueError("qwen: minimal is not a supported model.reasoningEffort value")


def qwen_settings(source: dict, model: str | None, effort: str | None, use_skills: bool) -> dict:
    validate_effort(effort, "qwen")
    for key in ("model", "modelProviders", "security", "env"):
        if key in source and not isinstance(source[key], dict):
            raise ValueError(f"qwen: {key} must be a JSON object")
    # Only retain provider/authentication and model generation settings, never hooks/MCP/context.
    auth = source.get("security", {}).get("auth", {})
    if not isinstance(auth, dict):
        raise ValueError("qwen: security.auth must be a JSON object")
    settings = {
        "modelProviders": source.get("modelProviders", {}),
        "model": {k: v for k, v in source.get("model", {}).items()
                  if k in {"name", "generationConfig", "reasoningEffort"}},
        "security": {"auth": {k: v for k, v in auth.items()
                              if k in {"selectedType", "apiKey", "baseUrl", "useExternal"}}},
        "general": {"enableAutoUpdate": False, "enableUpdateNag": False},
        "telemetry": {"enabled": False}, "mcpServers": {},
        "mcp": {"allowed": []},
        "skills": {"disabledLevels": ["user", "extension", "bundled"] + ([] if use_skills else ["project"])},
        "memory": {"enableManagedAutoMemory": False, "enableManagedAutoDream": False,
                   "enableAutoSkill": False, "enableTeamMemory": False},
        "tools": {"exclude": ["web_search", "web_fetch", "task", "ask_user_question"]},
    }
    # Legacy OpenAI-compatible Qwen configurations are still accepted by the CLI.
    for key in ("selectedAuthType", "apiKey", "baseUrl"):
        if key in source:
            settings[key] = source[key]
    auth_env = {"OPENAI_API_KEY", "OPENAI_BASE_URL", "DASHSCOPE_API_KEY", "DEEPSEEK_API_KEY", "QWEN_API_KEY"}
    for providers in settings["modelProviders"].values():
        if not isinstance(providers, list):
            raise ValueError("qwen: each modelProviders entry must be an array")
        for provider in providers:
            if not isinstance(provider, dict):
                raise ValueError("qwen: provider entries must be JSON objects")
            name = provider.get("envKey")
            if isinstance(name, str):
                if name.startswith(("HSQB_", "BENCHMARK_", "QWEN_CODE_")) or name == "QWEN_HOME":
                    raise ValueError("qwen: provider envKey conflicts with adapter control variables")
                auth_env.add(name)
    settings["env"] = {k: v for k, v in source.get("env", {}).items() if k in auth_env}
    if model:
        settings["model"]["name"] = model
    if effort and effort != "provider-default":
        settings["model"]["reasoningEffort"] = effort
    elif effort == "provider-default":
        settings["model"].pop("reasoningEffort", None)
    return settings


def codebuddy_settings(source: dict, model: str | None, effort: str | None) -> dict:
    validate_effort(effort, "codebuddy")
    if "env" in source and not isinstance(source["env"], dict):
        raise ValueError("codebuddy: env must be a JSON object")
    settings = {k: v for k, v in source.items() if k in {"model", "reasoningEffort"}}
    settings.update({"env": {k: v for k, v in source.get("env", {}).items() if k in CODEBUDDY_AUTH_ENV},
                     "enabledPlugins": {}, "hooks": {}, "mcpServers": {},
                     "memory": {"autoMemoryEnabled": False, "memoryExtraction": False,
                                "teamMemory": {"enabled": False}},
                     "promptSuggestionEnabled": False})
    if model:
        settings["model"] = model
    if effort and effort != "provider-default":
        settings["reasoningEffort"] = effort
    elif effort == "provider-default":
        settings.pop("reasoningEffort", None)
    return settings


def codebuddy_compute_commands() -> tuple[str, str]:
    python = Path(sys.executable).resolve().as_posix()
    if any(character in python for character in ('"', "'", '`', '$', '\n', '\r')):
        raise ValueError("codebuddy: Python executable path contains unsupported shell characters")
    return f'"{python}" ./task_compute.py', f"& '{python}' ./task_compute.py"


def codebuddy_permissions(workspace: Path, skill_names: list[str]) -> dict:
    """Task-scoped file grants and one fixed Python script command, not whole-shell grants."""
    import yaml

    # CodeBuddy 2.161.2 normalizes file arguments to absolute paths, but leaves
    # patterns beginning with '.' unresolved. './**' consequently never matches.
    pattern = workspace.resolve().as_posix() + "/**"
    if any(character in pattern[:-3] for character in ('*', '?', '[', ']', '(', ')', '{', '}')):
        raise ValueError("codebuddy: workspace path contains permission pattern metacharacters")
    bash_command, powershell_command = codebuddy_compute_commands()
    allow = [f"Read({pattern})", f"Write({pattern})", f"Edit({pattern})",
             f"Bash({bash_command})", f"PowerShell({powershell_command})",
             # Native command parsing can strip the PowerShell invocation operator.
             f"PowerShell({powershell_command.removeprefix('& ')})"]
    for directory_name in skill_names:
        contents = (workspace / ".agents/skills" / directory_name / "SKILL.md").read_text(encoding="utf-8")
        if contents.startswith("---"):
            frontmatter = yaml.safe_load(contents.split("---", 2)[1]) or {}
            name = frontmatter.get("name") if isinstance(frontmatter, dict) else None
            if isinstance(name, str) and re.fullmatch(r"[a-zA-Z0-9_-]+", name):
                allow.append(f"Skill({name})")
    return {"defaultMode": "dontAsk", "allow": allow,
            "deny": list(CODEBUDDY_DENIED_TOOLS), "ask": [],
            "disableBypassPermissionsMode": "disable"}


def child_environment(cli: str, temporary_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("HSQB_", "BENCHMARK_", "QWEN_", "CODEBUDDY_")):
            if cli == "codebuddy" and key in CODEBUDDY_AUTH_ENV:
                continue
            env.pop(key, None)
    env.pop("PYTHONPATH", None)
    env.update({"HOME": str(temporary_home), "USERPROFILE": str(temporary_home),
                "XDG_CONFIG_HOME": str(temporary_home / ".config"),
                "XDG_CACHE_HOME": str(temporary_home / ".cache"),
                "XDG_DATA_HOME": str(temporary_home / ".local/share")})
    if cli == "codebuddy" and os.environ.get("HSQB_CODEBUDDY_INHERIT_LOGIN") == "1":
        # CodeBuddy FileAuthenticationStorage uses the OS HOME's shared Data/Public/auth,
        # not CODEBUDDY_CONFIG_DIR. Leave login handling and encrypted credentials to the CLI.
        env["HOME"] = os.environ.get("HOME", str(Path.home()))
        env["USERPROFILE"] = os.environ.get("USERPROFILE", str(Path.home()))
    return env


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_cli(cli: str, required_flags: list[str]) -> int:
    prefix = resolve_cli(cli)
    help_result = subprocess.run(prefix + ["--help"], stdin=subprocess.DEVNULL, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=30, check=False)
    help_text = help_result.stdout + help_result.stderr
    if help_result.returncode or any(flag not in help_text for flag in required_flags):
        raise ValueError(f"{cli}: installed CLI lacks required headless flags; inspect its --help")
    version = subprocess.run(prefix + ["--version"], stdin=subprocess.DEVNULL, capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=30, check=False)
    if version.returncode:
        raise ValueError(f"{cli}: version check failed")
    print(json.dumps({"cli": cli, "version": version.stdout.strip(), "headless_flags": "supported",
                      "authentication": "not tested", "model_access": "not tested"}, ensure_ascii=False))
    return 0


def run_wrapper(cli: str, build_command) -> int:
    prefix = resolve_cli(cli)
    source, auth_dir = read_settings(cli)
    model = os.environ.get("BENCHMARK_MODEL")
    effort = os.environ.get("BENCHMARK_EFFORT")
    validate_effort(effort, cli)
    workspace = Path(os.environ["HSQB_WORKSPACE"]).resolve()
    task = json.loads(Path(os.environ["HSQB_TASK_JSON"]).read_text(encoding="utf-8"))
    if task.get("task_kind") == "composite":
        raise ValueError("This wrapper supports atomic tasks only; use the isolated composite runtime")
    skills = install_skill_snapshot(os.environ.get("BENCHMARK_SKILLS_PATH"), workspace)
    # The public instructions and startup prompt are identical in the two conditions.
    instructions = generate_agents_md(task, False)
    if cli == "codebuddy":
        bash_command, powershell_command = codebuddy_compute_commands()
        instructions += "\n" + CODEBUDDY_RUNTIME_NOTE.format(
            bash_command=bash_command, powershell_command=powershell_command)
    (workspace / "AGENTS.md").write_text(instructions, encoding="utf-8")
    native = workspace / (".qwen" if cli == "qwen" else ".codebuddy")
    native.mkdir(exist_ok=True)
    if skills:
        copy_tree(workspace / ".agents/skills", native / "skills")
    (workspace / ("QWEN.md" if cli == "qwen" else "CODEBUDDY.md")).write_text(instructions, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix=f"hsqb-atomic-{cli}-") as directory:
        temporary_home = Path(directory)
        env = child_environment(cli, temporary_home)
        if cli == "qwen":
            config = qwen_settings(source, model, effort, bool(skills))
            config_dir = temporary_home / ".qwen"
            for providers in config["modelProviders"].values():
                for provider in providers:
                    name = provider.get("envKey")
                    if isinstance(name, str) and name in os.environ:
                        env[name] = os.environ[name]
            if "QWEN_API_KEY" in os.environ:
                env["QWEN_API_KEY"] = os.environ["QWEN_API_KEY"]
            env.update({k: str(v) for k, v in config["env"].items() if k not in env})
            env["QWEN_HOME"] = str(config_dir)
            settings_path = config_dir / "settings.json"
            write_json(settings_path, config)
            # Only the OAuth credential cache is retained, never history or user skills.
            if (auth_dir / "oauth_creds.json").is_file():
                shutil.copyfile(auth_dir / "oauth_creds.json", config_dir / "oauth_creds.json")
            env["QWEN_CODE_SYSTEM_SETTINGS_PATH"] = str(settings_path)
            defaults = temporary_home / "system-defaults.json"
            write_json(defaults, {})
            env["QWEN_CODE_SYSTEM_DEFAULTS_PATH"] = str(defaults)
        else:
            config = codebuddy_settings(source, model, effort)
            config["permissions"] = codebuddy_permissions(workspace, skills)
            config_dir = temporary_home / ".codebuddy"
            settings_path = config_dir / "settings.json"
            write_json(settings_path, config)
            # Login inheritance (opt-in) keeps the OS HOME, while configuration stays temporary.
            # Never copy/decrypt credentials or import personal .codebuddy settings/history/skills.
            env.update({k: str(v) for k, v in config["env"].items() if k not in env})
            env.update({"CODEBUDDY_CONFIG_DIR": str(config_dir), "CODEBUDDY_DISABLE_AUTO_MEMORY": "1",
                        "CODEBUDDY_CODE_DISABLE_AUTO_MEMORY": "1", "CODEBUDDY_DISABLE_CRON": "1",
                        "CODEBUDDY_DISABLE_BACKGROUND_TASKS": "1", "CODEBUDDY_RETRY_WATCHDOG": "0",
                        "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1", "DISABLE_AUTOUPDATER": "1"})
        command = prefix + build_command(model, effort, bool(skills))[1:]
        if cli == "codebuddy":
            command.extend(["--settings", str(settings_path)])
        write_json(workspace / ".hsqb-adapter.json", {
            "cli": cli, "model": config.get("model", {}).get("name") if cli == "qwen" else config.get("model"), "requested_effort": effort,
            "effective_effort": config.get("model", {}).get("reasoningEffort") if cli == "qwen" else config.get("reasoningEffort"),
            "skills": skills, "startup_prompt_sha256": hashlib.sha256(START_PROMPT.encode()).hexdigest(),
            "personal_login_home": cli == "codebuddy" and os.environ.get("HSQB_CODEBUDDY_INHERIT_LOGIN") == "1",
            "tool_permissions": config.get("permissions") if cli == "codebuddy" else None,
            "compute_python": str(Path(sys.executable).resolve()) if cli == "codebuddy" else None,
            "instructions_sha256": hashlib.sha256(instructions.encode()).hexdigest(),
            "isolation": "local configuration only; no filesystem/network sandbox",
        })
        completed = subprocess.run(command, cwd=workspace, env=env, stdin=subprocess.DEVNULL,
                                   shell=False, check=False)
        return int(completed.returncode)


def entrypoint(cli: str, build_command, flags: list[str]) -> int:
    try:
        if sys.argv[1:] == ["--check"]:
            return check_cli(cli, flags)
        if sys.argv[1:]:
            raise ValueError("Use --check, or invoke this wrapper via python -m harness.cli run")
        return run_wrapper(cli, build_command)
    except (ValueError, OSError, KeyError, subprocess.TimeoutExpired) as exc:
        # JSON/config parse errors may contain credentials; never dump their payloads.
        message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else type(exc).__name__
        print(f"{cli} atomic adapter failed: {message}", file=sys.stderr)
        return 2
