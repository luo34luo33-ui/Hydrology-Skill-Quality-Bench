"""Offline adapter checks: no API calls, personal credentials or real agents."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts import atomic_cli_support as support
from scripts.run_qwen import build_qwen_command
from scripts.run_codebuddy import build_codebuddy_command

ROOT = Path(__file__).resolve().parents[1]


def test_installed_codebuddy_native_permissions_without_model(tmp_path):
    if not shutil.which("node") or not shutil.which("codebuddy"):
        pytest.skip("Installed CodeBuddy Node package required for native matcher regression")
    from scripts.verify_codebuddy_permissions import verify
    result = verify(tmp_path)
    assert result["passed"] and len(result["checks"]) >= 40


def test_codebuddy_absolute_python_survives_stale_path(tmp_path):
    if os.name != "nt":
        pytest.skip("Windows PowerShell execution check")
    (tmp_path / "task_compute.py").write_text("import sys\nprint(sys.executable)\n")
    _, powershell = support.codebuddy_compute_commands()
    shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    env = os.environ.copy()
    env["PATH"] = str(Path(sys.executable).parent.parent)  # Deliberately omit the interpreter directory.
    result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command", powershell],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == Path(sys.executable).resolve()


@pytest.mark.parametrize("builder", [build_qwen_command, build_codebuddy_command])
def test_identical_start_and_model_mapping(builder):
    without = builder("test-model", "high", False)
    with_skills = builder("test-model", "high", True)
    assert without == with_skills
    assert without[without.index("--model") + 1] == "test-model"
    assert without[without.index("-p") + 1] == support.START_PROMPT
    assert "--continue" not in without and "--resume" not in without
    assert without[without.index("--output-format") + 1] == "stream-json"


def test_codebuddy_permissions_are_scoped_and_include_powershell(tmp_path):
    config = support.codebuddy_permissions(tmp_path, [])
    pattern = tmp_path.resolve().as_posix() + "/**"
    bash, powershell = support.codebuddy_compute_commands()
    assert config["allow"] == [f"Read({pattern})", f"Write({pattern})", f"Edit({pattern})",
                               f"Bash({bash})", f"PowerShell({powershell})",
                               f"PowerShell({powershell.removeprefix('& ')})"]
    assert config["disableBypassPermissionsMode"] == "disable"
    assert "Write" not in config["allow"] and "Bash" not in config["allow"]
    args = build_codebuddy_command("hy3", None, False)
    assert "--allowedTools" not in args
    assert "PowerShell" in args[args.index("--tools") + 1]
    assert "--dangerously-skip-permissions" not in args


def test_provider_settings_kept_customizations_removed():
    source = {"model": {"name": "configured", "reasoningEffort": "low", "generationConfig": {"temperature": 0}},
              "modelProviders": {"openai": [{"id": "configured", "envKey": "TEST_API_KEY"}]},
              "security": {"auth": {"selectedType": "openai"}},
              "env": {"TEST_API_KEY": "fake-test-key", "QWEN_HOME": "evil", "OTHER_SETTING": "evil"},
              "hooks": {"before": "evil"}, "skills": {"directories": ["secret"]}, "mcpServers": {"bad": {}},
              "memory": {"enableManagedAutoMemory": True}, "modelFallbacks": ["other"]}
    qwen = support.qwen_settings(source, "override", "high", True)
    assert qwen["model"] == {"name": "override", "reasoningEffort": "high", "generationConfig": {"temperature": 0}}
    assert qwen["modelProviders"] == source["modelProviders"]
    assert qwen["env"] == {"TEST_API_KEY": "fake-test-key"}
    assert "hooks" not in qwen and "modelFallbacks" not in qwen
    assert qwen["mcpServers"] == {} and qwen["skills"]["disabledLevels"] == ["user", "extension", "bundled"]
    assert "project" in support.qwen_settings(source, None, None, False)["skills"]["disabledLevels"]
    assert "reasoningEffort" not in support.qwen_settings(source, None, "provider-default", False)["model"]
    cb = support.codebuddy_settings({"model": "configured", "reasoningEffort": "low",
         "env": {"CODEBUDDY_API_KEY": "fake-test-key", "CODEBUDDY_IS_SANDBOX": "1"},
         "enabledPlugins": {"evil": True}, "hooks": {"bad": "evil"}}, "override", "high")
    assert cb["model"] == "override" and cb["reasoningEffort"] == "high"
    assert cb["env"] == {"CODEBUDDY_API_KEY": "fake-test-key"}
    assert cb["hooks"] == {} and cb["enabledPlugins"] == {}
    assert "reasoningEffort" not in support.codebuddy_settings(cb, None, "provider-default")


@pytest.mark.parametrize("cli,effort", [("qwen", "ultra"), ("codebuddy", "ultra"), ("qwen", "minimal")])
def test_unsupported_effort_rejected(cli, effort):
    with pytest.raises(ValueError, match="supported"):
        support.validate_effort(effort, cli)


def test_environment_does_not_expose_benchmark_paths_or_stale_customizations(tmp_path, monkeypatch):
    monkeypatch.delenv("HSQB_CODEBUDDY_INHERIT_LOGIN", raising=False)
    for key in ("HSQB_TASK_JSON", "BENCHMARK_SKILLS_PATH", "QWEN_HOME", "QWEN_CODE_RELAUNCH_ARGS",
                "CODEBUDDY_IS_SANDBOX", "CODEBUDDY_MODEL", "PYTHONPATH"):
        monkeypatch.setenv(key, "hidden-path")
    monkeypatch.setenv("CODEBUDDY_API_KEY", "fake-key")
    env = support.child_environment("codebuddy", tmp_path)
    assert env["USERPROFILE"] == str(tmp_path)
    assert env["CODEBUDDY_API_KEY"] == "fake-key"
    assert "CODEBUDDY_IS_SANDBOX" not in env and "PYTHONPATH" not in env
    assert not any(k.startswith(("HSQB_", "BENCHMARK_", "QWEN_")) for k in env)


def test_codebuddy_can_keep_login_home_without_importing_personal_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HSQB_CODEBUDDY_INHERIT_LOGIN", "1")
    monkeypatch.setenv("HOME", "personal-home")
    monkeypatch.setenv("USERPROFILE", "personal-profile")
    monkeypatch.setenv("CODEBUDDY_CONFIG_DIR", "personal-config")
    monkeypatch.setenv("CODEBUDDY_AUTH_TOKEN", "fake-auth-token")
    env = support.child_environment("codebuddy", tmp_path)
    assert env["HOME"] == "personal-home" and env["USERPROFILE"] == "personal-profile"
    assert env["CODEBUDDY_AUTH_TOKEN"] == "fake-auth-token"
    assert "CODEBUDDY_CONFIG_DIR" not in env  # run_wrapper installs the temporary config dir afterwards.
    assert "HSQB_CODEBUDDY_INHERIT_LOGIN" not in env
    qwen_env = support.child_environment("qwen", tmp_path)
    assert qwen_env["USERPROFILE"] == str(tmp_path)


def test_platform_auth_token_can_be_passed_without_copying_settings_hooks():
    config = support.codebuddy_settings({"env": {"CODEBUDDY_AUTH_TOKEN": "fake-auth-token",
                       "CODEBUDDY_IS_SANDBOX": "1"}}, "hy3", None)
    assert config["env"] == {"CODEBUDDY_AUTH_TOKEN": "fake-auth-token"}


def test_missing_binary_fails_with_actionable_error(monkeypatch):
    monkeypatch.delenv("HSQB_CODEBUDDY_BINARY", raising=False)
    monkeypatch.setattr(support.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="HSQB_CODEBUDDY_BINARY"):
        support.resolve_cli("codebuddy")


@pytest.mark.parametrize("entry_name", ["cli-entry.js", "cli-entry.mjs", "cli-entry.cjs", "codebuddy"])
def test_windows_npm_shim_is_resolved_without_a_shell(tmp_path, monkeypatch, entry_name):
    entry = tmp_path / f"node_modules/package/bin/{entry_name}"
    entry.parent.mkdir(parents=True)
    entry.write_text("#!/usr/bin/env node\n// fake")
    shim = tmp_path / "qwen.cmd"
    shim.write_text(f'"%_prog%" "%dp0%\\node_modules\\package\\bin\\{entry_name}" %*')
    monkeypatch.setenv("HSQB_QWEN_BINARY", str(shim))
    monkeypatch.setattr(support.shutil, "which", lambda name: "/fake/node" if name == "node" else None)
    assert support.resolve_cli("qwen") == ["/fake/node", str(entry.resolve())]


def test_direct_extensionless_node_override(tmp_path, monkeypatch):
    entry = tmp_path / "codebuddy"
    entry.write_text("#!/usr/bin/env node\n// fake")
    monkeypatch.setenv("HSQB_CODEBUDDY_BINARY", str(entry))
    monkeypatch.setattr(support.shutil, "which", lambda name: "/fake/node")
    assert support.resolve_cli("codebuddy") == ["/fake/node", str(entry.resolve())]


def test_extensionless_non_node_shim_rejected(tmp_path, monkeypatch):
    entry = tmp_path / "ide-launcher"
    entry.write_text("#!/bin/sh\nlaunch-desktop")
    shim = tmp_path / "codebuddy.cmd"
    shim.write_text('"node" "%dp0%\\ide-launcher" %*')
    monkeypatch.setenv("HSQB_CODEBUDDY_BINARY", str(shim))
    with pytest.raises(ValueError, match="does not point to a Node CLI"):
        support.resolve_cli("codebuddy")


@pytest.mark.parametrize("cli", ["qwen", "codebuddy"])
@pytest.mark.parametrize("use_skills", [False, True])
@pytest.mark.parametrize("inherit_login", [False, True])
def test_real_fake_process_workspace_config_stdout_and_exit(tmp_path, cli, use_skills, inherit_login):
    if not shutil.which("node"):
        pytest.skip("Node required for the fake npm CLI")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    task = {"id": "adapter-001", "prompt": "Write output.txt.", "required_outputs": ["output.txt"], "data_files": []}
    support.write_json(workspace / "task_public.json", task)
    source = tmp_path / "source"
    source.mkdir()
    support.write_json(source / "settings.json", {
        "model": {"name": "configured"} if cli == "qwen" else "configured",
        "modelProviders": {"openai": [{"id": "configured"}]},
        "security": {"auth": {"selectedType": "openai", "apiKey": "fake-test-key"}},
        "env": {"CODEBUDDY_API_KEY": "fake-test-key"},
        "hooks": {"mustNotRun": "evil"}, "mcpServers": {"mustNotRun": {}},
    })
    # Personal skills and history must not be copied into the fresh HOME.
    (source / "skills/personal").mkdir(parents=True)
    (source / "skills/personal/SKILL.md").write_text("personal")
    (source / "history.json").write_text("private-history")
    support.write_json(source / "oauth_creds.json", {"access_token": "fake-oauth"})
    skill = tmp_path / "fixture-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: fixture-skill\ndescription: test\n---\n")
    fake = tmp_path / "fake-cli.js"
    fake.write_text('''const fs = require('fs'), path = require('path');
const cli = process.env.QWEN_HOME ? 'qwen' : 'codebuddy';
const dir = process.env.QWEN_HOME || process.env.CODEBUDDY_CONFIG_DIR;
const config = JSON.parse(fs.readFileSync(path.join(dir,'settings.json'),'utf8'));
if (process.argv.includes('--help')) { console.log('--output-format --yolo --advisor --model --permission-mode --strict-mcp-config --no-session-persistence --setting-sources'); process.exit(0); }
if (process.argv.includes('--version')) { console.log('fake-1.0'); process.exit(0); }
fs.writeFileSync('output.txt','done');
fs.writeFileSync('fake-inspection.json',JSON.stringify({args:process.argv.slice(2),
  configDir:dir, model: cli === 'qwen' ? config.model.name : config.model,
  effort:cli === 'qwen' ? config.model.reasoningEffort : config.reasoningEffort,
  skill:fs.existsSync(path.join(process.cwd(),'.'+cli,'skills','fixture-skill','SKILL.md')),
  personal:fs.existsSync(path.join(dir,'skills','personal','SKILL.md')),
  history:fs.existsSync(path.join(dir,'history.json')),
  oauth:fs.existsSync(path.join(dir,'oauth_creds.json')),
  hidden:!!process.env.HSQB_TASK_JSON || !!process.env.BENCHMARK_SKILLS_PATH,
  sandboxClaim:process.env.CODEBUDDY_IS_SANDBOX || null,permissions:config.permissions || null}));
console.log(JSON.stringify({type:'result',result:'fixture complete'}));
console.error('fixture stderr'); process.exit(7);
''', encoding="utf-8")
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("HSQB_", "BENCHMARK_")):
            env.pop(key)
    env.update({f"HSQB_{cli.upper()}_BINARY": str(fake), f"HSQB_{cli.upper()}_SETTINGS": str(source / "settings.json"),
                "HSQB_WORKSPACE": str(workspace), "HSQB_TASK_JSON": str(workspace / "task_public.json"),
                "BENCHMARK_MODEL": "frozen-model", "BENCHMARK_EFFORT": "high", "CODEBUDDY_IS_SANDBOX": "1"})
    if inherit_login:
        env["HSQB_CODEBUDDY_INHERIT_LOGIN"] = "1"
    if use_skills:
        env["BENCHMARK_SKILLS_PATH"] = str(skill)
    # Run the script directly, from another cwd, without relying on PYTHONPATH.
    result = subprocess.run([sys.executable, str(ROOT / f"scripts/run_{cli}.py")], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 7, result.stderr
    assert json.loads(result.stdout)["type"] == "result" and "fixture stderr" in result.stderr
    inspection = json.loads((workspace / "fake-inspection.json").read_text())
    assert inspection["model"] == "frozen-model" and inspection["effort"] == "high"
    if cli == "codebuddy":
        assert inspection["args"][inspection["args"].index("--settings") + 1] == str(Path(inspection["configDir"]) / "settings.json")
        assert inspection["permissions"]["allow"][1] == f"Write({workspace.resolve().as_posix()}/**)"
        assert ("Skill(fixture-skill)" in inspection["permissions"]["allow"]) == use_skills
        bash, powershell = support.codebuddy_compute_commands()
        assert support.CODEBUDDY_RUNTIME_NOTE.format(bash_command=bash, powershell_command=powershell) in (workspace / "AGENTS.md").read_text()
    assert inspection["skill"] == use_skills
    assert not inspection["personal"] and not inspection["history"] and not inspection["hidden"]
    assert inspection["sandboxClaim"] is None
    assert inspection["oauth"] == (cli == "qwen")
    assert not Path(inspection["configDir"]).exists()  # Temporary config is cleaned up after normal exit.
    manifest = json.loads((workspace / ".hsqb-adapter.json").read_text())
    assert manifest["startup_prompt_sha256"] == hashlib.sha256(support.START_PROMPT.encode()).hexdigest()
    assert manifest["personal_login_home"] == (cli == "codebuddy" and inherit_login)
    assert "fake-test-key" not in (workspace / ".hsqb-adapter.json").read_text()
    assert "fake-test-key" not in (workspace / "AGENTS.md").read_text()
    assert (workspace / "AGENTS.md").read_text() == (workspace / ("QWEN.md" if cli == "qwen" else "CODEBUDDY.md")).read_text()
    assert "## Skills" not in (workspace / "AGENTS.md").read_text()
