"""Noninteractive CodeBuddy Code adapter for the atomic benchmark."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.atomic_cli_support import START_PROMPT, CODEBUDDY_DENIED_TOOLS, entrypoint, validate_effort


def build_codebuddy_command(model: str | None, effort: str | None, use_skills: bool) -> list[str]:
    validate_effort(effort, "codebuddy")
    command = ["codebuddy", "-p", START_PROMPT, "--output-format", "stream-json", "--verbose",
               "--permission-mode", "dontAsk", "--tools", "Read,Write,Edit,Glob,Grep,Bash,PowerShell,Skill",
               "--disallowedTools", *CODEBUDDY_DENIED_TOOLS,
               "--strict-mcp-config", "--no-session-persistence", "--setting-sources", "user"]
    if model:
        command.extend(["--model", model])
    return command


def main() -> int:
    return entrypoint("codebuddy", build_codebuddy_command,
                      ["--output-format", "--permission-mode", "--strict-mcp-config", "--no-session-persistence", "--setting-sources", "--settings", "--tools"])


if __name__ == "__main__":
    sys.exit(main())
