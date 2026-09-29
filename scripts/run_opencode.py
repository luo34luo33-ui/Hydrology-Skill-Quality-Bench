"""HSQB wrapper for a single non-interactive OpenCode invocation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from harness.agent_wrapper import generate_agents_md, install_skill_snapshot


def build_opencode_command(model: str | None, effort: str | None, use_skills: bool) -> list[str]:
    prompt = "Complete the task described in AGENTS.md and create every required artifact."
    if use_skills:
        prompt = "Read the relevant skill instructions, then complete the task in AGENTS.md and create every required artifact."
    command = [shutil.which("opencode") or "opencode", "--pure", "run", "--auto"]
    if model:
        command.extend(["--model", model])
    if effort:
        command.extend(["--variant", effort])
    command.append(prompt)
    return command


def build_opencode_config(skill_names: list[str]) -> dict:
    skill_permissions = {"*": "deny"}
    skill_permissions.update({name: "allow" for name in skill_names})
    return {
        "permission": {
            "*": "allow",
            "external_directory": "deny",
            "question": "deny",
            "skill": skill_permissions,
        }
    }


def main() -> int:
    workspace = Path(os.environ["HSQB_WORKSPACE"]).resolve()
    task_path = Path(os.environ["HSQB_TASK_JSON"]).resolve()
    task = json.loads(task_path.read_text(encoding="utf-8"))
    skills_source = os.environ.pop("BENCHMARK_SKILLS_PATH", None)
    skill_names = install_skill_snapshot(skills_source, workspace)
    (workspace / "AGENTS.md").write_text(generate_agents_md(task, bool(skill_names)), encoding="utf-8")
    command = build_opencode_command(
        os.environ.get("BENCHMARK_MODEL"),
        os.environ.get("BENCHMARK_EFFORT"),
        bool(skill_names),
    )
    child_env = os.environ.copy()
    child_env.update(
        {
            "OPENCODE_AUTO_SHARE": "false",
            "OPENCODE_DISABLE_AUTOUPDATE": "true",
            "OPENCODE_DISABLE_CLAUDE_CODE": "true",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
            "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
            "OPENCODE_CONFIG_CONTENT": json.dumps(build_opencode_config(skill_names)),
        }
    )
    with tempfile.TemporaryDirectory(prefix="hsqb-opencode-") as config_dir:
        child_env["OPENCODE_CONFIG_DIR"] = config_dir
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=child_env,
            stdin=subprocess.DEVNULL,
            shell=os.name == "nt",
            check=False,
        )
    return int(completed.returncode)


if __name__ == "__main__":
    sys.exit(main())
