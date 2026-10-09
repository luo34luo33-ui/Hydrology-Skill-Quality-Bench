"""Public interface staging for the three-arm atomic experiment (no oracle reads)."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from harness.filesystem import copy_tree, filesystem_path

VERSION = "atomic-three-arm-v2"
CONDITIONS = ("no-skills", "programs-only", "with-skills")


def digest(path: Path) -> str:
    return hashlib.sha256(Path(filesystem_path(path)).read_bytes()).hexdigest()


def tree_digest(path: Path) -> str:
    path=Path(filesystem_path(path))
    h = hashlib.sha256()
    for p in sorted(p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts):
        h.update(p.relative_to(path).as_posix().encode()); h.update(b'\0'); h.update(p.read_bytes())
    return h.hexdigest()


def resolve_condition(condition: str | None, skills_path, programs_path) -> str | None:
    if condition is None:
        if programs_path:
            raise ValueError("--programs-path requires an explicit --condition")
        return None  # Legacy execution stays distinguishable from the new experiment.
    if condition not in CONDITIONS:
        raise ValueError("invalid atomic condition")
    if condition != 'with-skills' and skills_path:
        raise ValueError("this condition must not receive skills")
    if condition == 'with-skills' and not skills_path:
        raise ValueError("with-skills requires a frozen --skills-path")
    if condition == 'no-skills' and programs_path:
        raise ValueError("no-skills must not receive programs")
    return condition


def load_contract(task, task_dir: Path) -> dict:
    path = Path(filesystem_path(task_dir)) / task['public_contract']
    document = json.loads(path.read_text(encoding='utf-8'))
    if document.get('task_id') != task['id'] or document.get('version') != VERSION:
        raise ValueError("public contract task/version mismatch")
    return document


def render(contract: dict) -> str:
    return ('# Public input/output contract\n\n'
            'Identical in all three conditions. Describes interfaces, not expected results.\n\n'
            'Preserve double precision (17 significant digits for computed CSV numbers). '
            'Resolve manifest artifact paths relative to the manifest directory; bind files by SHA-256. '
            'Choose the applicable outcome branch from the evidence; no branch is preselected.\n\n'
            '```json\n' + json.dumps(contract, ensure_ascii=False, indent=2) + '\n```\n')


def stage_contract(task: dict, task_dir: Path, workspace: Path) -> str | None:
    workspace=Path(filesystem_path(workspace))
    if not task.get('public_contract'):
        return None
    contract = load_contract(task, task_dir)
    target = workspace / 'public_contract.json'
    target.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (workspace / 'PUBLIC_CONTRACT.md').write_text(render(contract), encoding='utf-8')
    return digest(target)


def stage_programs(source: Path, workspace: Path) -> str:
    source=Path(filesystem_path(source));workspace=Path(filesystem_path(workspace))
    if not (source / 'programs.json').is_file() or not (source / 'PROGRAM_INTERFACES.md').is_file():
        raise ValueError("public program bundle is incomplete")
    if (workspace / 'public').exists():
        raise ValueError("public program destination already exists")
    copy_tree(source, workspace / 'public', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return tree_digest(source)
