"""HSQB wrapper for a single non-interactive Codex invocation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from harness.agent_wrapper import generate_agents_md, install_skill_snapshot


def build_codex_command(model: str | None, effort: str | None, use_skills: bool) -> list[str]:
    prompt = "Complete the task described in AGENTS.md and create every required artifact."
    if use_skills:
        prompt = "Read the relevant skill instructions, then complete the task in AGENTS.md and create every required artifact."
    command = [
        "codex",
        "exec",
        prompt,
        "--skip-git-repo-check",
        "--ephemeral",
        "--ignore-user-config",
        "--approve-for-me",
    ]
    if model:
        command.extend(["--model", model])
    if effort:
        command.extend(["--config", f'model_reasoning_effort="{effort}"'])
    return command


def main() -> int:
    workspace = Path(os.environ["HSQB_WORKSPACE"]).resolve()
    task_path = Path(os.environ["HSQB_TASK_JSON"]).resolve()
    task = json.loads(task_path.read_text(encoding="utf-8"))
    skills_source = os.environ.pop("BENCHMARK_SKILLS_PATH", None)
    skill_names = install_skill_snapshot(skills_source, workspace)
    use_skills = bool(skill_names)
    (workspace / "AGENTS.md").write_text(generate_agents_md(task, use_skills), encoding="utf-8")
    command = build_codex_command(
        os.environ.get("BENCHMARK_MODEL"),
        os.environ.get("BENCHMARK_EFFORT"),
        use_skills,
    )
    completed = subprocess.run(command, cwd=workspace, stdin=subprocess.DEVNULL, check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    sys.exit(main())
