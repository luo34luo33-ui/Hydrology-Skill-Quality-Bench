"""Internal file operations that support long Windows experiment paths."""
from __future__ import annotations

import os
from pathlib import Path
import shutil


def filesystem_path(path: str | Path) -> str:
    """Use extended absolute paths internally, leaving public paths unchanged."""
    value = os.fspath(path)
    if os.name != "nt" or value.startswith("\\\\?\\"):
        return value
    value = str(Path(value).resolve())
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value[2:]
    return "\\\\?\\" + value


def copy_tree(source: str | Path, destination: str | Path, **kwargs):
    return shutil.copytree(filesystem_path(source), filesystem_path(destination), **kwargs)


def copy_file(source: str | Path, destination: str | Path):
    return shutil.copy2(filesystem_path(source), filesystem_path(destination))


def normal_path(path: str | Path) -> Path:
    """Canonical display/Docker path; never use a Win32 prefix in mount strings."""
    value=str(Path(path).resolve())
    if value.startswith('\\\\?\\UNC\\'):value='\\\\'+value[8:]
    elif value.startswith('\\\\?\\'):value=value[4:]
    return Path(value)


def execution_workspace(requested: Path, project: Path, relative_budget: int) -> Path:
    """Select a short host workspace in every Windows arm, including custom roots."""
    requested=normal_path(requested)
    if os.name!='nt' or len(str(requested))+1+relative_budget<240:return requested
    import tempfile
    import uuid
    identity=uuid.uuid4().hex[:12]
    for base in [normal_path(project)/'.cache'/'w',Path(tempfile.gettempdir())/'hsqb']:
        candidate=base/identity
        if len(str(candidate))+1+relative_budget<240:return candidate
    raise ValueError('Task relative paths exceed the safe Windows execution path budget; use a shorter project/TEMP directory')
