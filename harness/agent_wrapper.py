"""Shared helpers for concrete CLI-agent wrappers."""

from __future__ import annotations

from pathlib import Path
from harness.filesystem import copy_tree, filesystem_path


def generate_agents_md(task: dict, use_skills: bool) -> str:
    sections = [f"# Task: {task['id']}", task["prompt"]]
    if task.get('interaction_mode')=='none':
        sections.append('## Unattended execution\n\nAll scientific facts and permissions are supplied in scenario.json and INPUT_GUIDE.md. Read OUTPUT_INTERFACES.md and output_interfaces.json. No user answers or clarification service are available. Choose tools and equivalent implementations autonomously within the declared scientific constraints and budget.')
    if task.get("data_description"):
        sections.extend(["## Available data", task["data_description"]])
    if task.get("data_files"):
        sections.append("## Input files\n\n" + "\n".join(f"- `{name}`" for name in task["data_files"]))
    sections.append("## Required outputs\n\n" + "\n".join(f"- `{name}`" for name in task["required_outputs"]))
    notes = task.get("setup_notes", [])
    if isinstance(notes, str):
        notes = [notes]
    if notes:
        sections.append("## Runtime notes\n\n" + "\n".join(f"- {note}" for note in notes))
    if task.get('public_contract'):
        sections.append("## Public interfaces\n\nRead `PUBLIC_CONTRACT.md` and `public_contract.json`. "
                        "Inspect the resources available in this workspace yourself. "
                        "Produce artifacts conforming to the shared input/output contract.")
    if use_skills and not task.get('public_contract'):
        sections.append(
            "## Skills\n\nRelevant skills are available under `.agents/skills/`. Read the applicable "
            "`SKILL.md` and follow it while completing this task."
        )
    sections.append(
        "## Execution\n\nWork only in this directory. Use the provided files and installed tools. "
        "The benchmark is run from the `HydroTune-eval` Python environment; use its active Python and "
        "installed packages without creating or switching environments. Do not ask for human input. "
        "Completion is judged from the required artifacts, not the final message."
    )
    return "\n\n".join(sections) + "\n"


def install_skill_snapshot(source_value: str | None, workspace: Path) -> list[str]:
    """Copy a skill suite into the workspace and return its local skill IDs."""
    if not source_value:
        return []
    source = Path(filesystem_path(source_value)).resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"skills path is not a directory: {source}")
    destination = Path(filesystem_path(workspace)) / ".agents" / "skills"
    destination.mkdir(parents=True, exist_ok=False)
    if (source / "SKILL.md").is_file():
        copy_tree(source, destination / source.name)
        return [source.name]
    skill_dirs = [child for child in sorted(source.iterdir()) if child.is_dir() and (child / "SKILL.md").is_file()]
    if not skill_dirs:
        raise ValueError(f"no skills found under {source}")
    for child in skill_dirs:
        copy_tree(child, destination / child.name)
    return [child.name for child in skill_dirs]
