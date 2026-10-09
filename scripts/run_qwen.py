"""Noninteractive Qwen Code adapter for the atomic benchmark."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.atomic_cli_support import START_PROMPT, entrypoint, validate_effort


def build_qwen_command(model: str | None, effort: str | None, use_skills: bool) -> list[str]:
    validate_effort(effort, "qwen")
    command = ["qwen", "-p", START_PROMPT, "--output-format", "stream-json", "--yolo", "--advisor", "off"]
    if model:
        command.extend(["--model", model])
    return command


def main() -> int:
    return entrypoint("qwen", build_qwen_command, ["--output-format", "--yolo", "--advisor", "--model"])


if __name__ == "__main__":
    sys.exit(main())
